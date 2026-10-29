"""Orientation, scale and pose of the reference relative to the RL head.

1. Up-axis x yaw-quadrant candidates (24 axis-aligned proper rotations, or a
   subset when --up / --yaw are given), each with a few scale guesses from the
   vertical width profile of the bust (head top, neck narrowing, head width).
2. From every start, a trimmed point-to-plane similarity ICP of the RL face,
   ears and upper neck (model -> reference, reference normals) - geometry only,
   so the cranium (usually under hair) does not take part.
3. Each converged start is scored by the weighted fraction of face points with
   a close, normal-compatible reference point; small priors favour Y-up and
   yaw 0 (the likely Meshy convention). Best start wins.
4. A mirror-symmetry plane of the reference face (iterative reflect-and-match)
   corrects small roll/yaw and is kept as a diagnostic.
Landmarks (--landmarks) replace the search by a similarity fit
(Umeyama) to the RL landmarks; ICP still refines it.
"""
import numpy as np
from scipy.spatial import cKDTree

from fitcommon import kdq, Sim, rot_x, rot_y, rot_axis_angle, rot_vec, unit, umeyama, rot_angle_deg, log
from rlmodel import REGIONS

UP = {
    'y': np.eye(3),
    'z': rot_x(-90),          # reference +Z -> game +Y (Blender-style Z up, face toward -Y)
    '-y': rot_x(180),
    '-z': rot_x(90),
    'x': rot_axis_angle([0, 0, 1], np.radians(90)),
    '-x': rot_axis_angle([0, 0, 1], np.radians(-90)),
}
UP_PRIOR = {'y': 0.03, 'z': 0.02, '-y': 0.0, '-z': 0.0, 'x': 0.0, '-x': 0.0}


def up_of_rotation(R):
    """Describe a reference->game rotation R: which reference axis maps (closest) to game +Y, and the
    yaw (deg) of the face in the up-converted reference: the face looks along (sin yaw, 0, cos yaw)
    there (0 = +Z, 90 = +X). For up 'z' the up conversion is Blender's Z-up (face toward -Y at yaw 0)."""
    best = None
    for name, U in UP.items():
        a = U.T @ np.array([0, 1.0, 0])         # reference axis that U sends to +Y
        dot = float((R @ a)[1])
        if best is None or dot > best[1]:
            best = (name, dot)
    name = best[0]
    f = UP[name] @ (R.T @ np.array([0, 0, 1.0]))   # game face direction in up-converted reference coords
    yaw = float(np.degrees(np.arctan2(f[0], f[2]))) % 360.0
    return name, yaw


def yaw_rotation(yaw_desc):
    """Rotation about +Y that turns a face looking along (sin yaw, 0, cos yaw) toward +Z."""
    return rot_y(-yaw_desc)


# ---------------------------------------------------------------- profile
def width_profile(Y, nbins=120):
    """Vertical width profile of points Y (up = +Y): bin centres (top -> bottom), half extent, centre xz."""
    y = Y[:, 1]
    lo, hi = np.percentile(y, 0.05), np.percentile(y, 99.95)
    edges = np.linspace(hi, lo, nbins + 1)
    yc = 0.5 * (edges[:-1] + edges[1:])
    r = np.full(nbins, np.nan); cx = np.full(nbins, np.nan); cz = np.full(nbins, np.nan)
    order = np.argsort(-y)
    ys = y[order]
    for i in range(nbins):
        a = np.searchsorted(-ys, -edges[i]); b = np.searchsorted(-ys, -edges[i + 1])
        if b - a < 12:
            continue
        S = Y[order[a:b]]
        ex = np.percentile(S[:, 0], 97) - np.percentile(S[:, 0], 3)
        ez = np.percentile(S[:, 2], 97) - np.percentile(S[:, 2], 3)
        r[i] = 0.5 * np.sqrt(max(ex, 1e-12) * max(ez, 1e-12))
        cx[i] = 0.5 * (np.percentile(S[:, 0], 97) + np.percentile(S[:, 0], 3))
        cz[i] = 0.5 * (np.percentile(S[:, 2], 97) + np.percentile(S[:, 2], 3))
    return yc, r, cx, cz, hi, lo


def head_from_profile(Y):
    """Head top, neck height and head half-width of an up-converted point set."""
    yc, r, cx, cz, top, bot = width_profile(Y)
    good = np.isfinite(r)
    rs = r.copy()
    if good.sum() < 5:
        return None
    # smooth
    k = np.ones(5) / 5
    rr = np.where(good, r, np.interp(np.arange(len(r)), np.nonzero(good)[0], r[good]))
    rr = np.convolve(np.pad(rr, 2, mode='edge'), k, mode='valid')
    H = top - bot
    # head max: the largest width in the upper part before a strong narrowing
    imax = None; run_max = 0
    neck = None
    for i in range(len(rr)):
        if rr[i] > run_max:
            run_max = rr[i]; imax = i
        # a neck: width below 78% of the head max, then widening by 20% again (shoulders) or the end
        if imax is not None and rr[i] < 0.78 * run_max and (yc[imax] - yc[i]) > 0.25 * (top - yc[i]) * 0.6:
            j = i
            while j + 1 < len(rr) and rr[j + 1] <= rr[j] * 1.01:
                j += 1
            neck = j
            break
    if neck is None:
        neck = len(rr) - 1
    head_r = float(np.nanmax(rr[: max(neck, 1)]))
    centre = np.array([np.nanmedian(cx[: max(neck, 1)]), np.nanmedian(cz[: max(neck, 1)])])
    neck_c = np.array([cx[neck] if np.isfinite(cx[neck]) else centre[0], cz[neck] if np.isfinite(cz[neck]) else centre[1]])
    return {'top': float(top), 'neck_y': float(yc[neck]), 'head_r': head_r, 'centre_xz': centre, 'neck_xz': neck_c,
            'neck_r': float(rr[neck]), 'bottom': float(bot)}


# ---------------------------------------------------------------- ICP
def _solve_update(rows, rhs, w, damp):
    A = rows * np.sqrt(w)[:, None]
    b = rhs * np.sqrt(w)
    AtA = A.T @ A + np.diag(damp)
    return np.linalg.solve(AtA, A.T @ b)


def icp(model_pts, model_nrm, model_w, ref_kd, ref_X, ref_N, sim, iters=25, trim=(0.9, 0.7), gate=0.03,
        cosmin=0.3, scale=True, centre=None, robust=0.004):
    """Trimmed point-to-plane similarity ICP: model points (game) vs reference points (ref space).
    Returns the updated Sim and the last residual stats."""
    sim = sim.copy()
    c = model_pts.mean(0) if centre is None else centre
    for it in range(iters):
        q = sim.inv(model_pts)
        d, j = kdq(ref_kd, q, k=1, distance_upper_bound=gate / sim.s)
        ok = np.isfinite(d)
        if ok.sum() < 30:
            break
        jj = j[ok]
        Yg = sim(ref_X[jj]); Ng = sim.rot(ref_N[jj])
        M = model_pts[ok]; Nm = model_nrm[ok]; wm = model_w[ok]
        cosv = (Ng * Nm).sum(1)
        keep = cosv > cosmin
        if keep.sum() < 30:
            break
        Yg, Ng, M, wm = Yg[keep], Ng[keep], M[keep], wm[keep]
        r = (Ng * (Yg - M)).sum(1)
        frac = trim[0] + (trim[1] - trim[0]) * min(1.0, it / max(iters * 0.6, 1))
        # one-sided trimming: drop the largest POSITIVE residuals (reference outside the RL skin: hair,
        # beard, clothing lying over the face) but keep the reference-inside evidence, which only real
        # skin can produce; this stops hair/beard from shrinking the reference onto the RL head
        hi = np.quantile(r, frac)
        lo = np.quantile(r, 0.02)
        sel = (r <= max(hi, 0.0005)) & (r >= lo)
        Yg, Ng, M, wm, r = Yg[sel], Ng[sel], M[sel], wm[sel], r[sel]
        qv = Yg - c
        rows = np.c_[np.cross(qv, Ng), Ng, (Ng * qv).sum(1)]
        w = wm / (1 + (r / robust) ** 2)
        damp = np.array([1e-6] * 3 + [1e-6] * 3 + [1e-6 if scale else 1e6]) * w.sum()
        xi = _solve_update(rows, -r, w, damp)
        xi[6] = np.clip(xi[6], -0.15, 0.15)
        sim = sim.update(xi[:3], xi[3:6], xi[6], c)
        if np.linalg.norm(xi[:3]) < 1e-5 and np.linalg.norm(xi[3:6]) < 1e-6 and abs(xi[6]) < 1e-5:
            break
    return sim


def score_pose(model_pts, model_nrm, model_w, ref_kd, ref_X, ref_N, sim, tol=0.0025, cosmin=0.8):
    q = sim.inv(model_pts)
    d, j = kdq(ref_kd, q, k=1, distance_upper_bound=0.012 / sim.s)
    ok = np.isfinite(d)
    inl = np.zeros(len(q), bool)
    rr = np.full(len(q), np.inf)
    if ok.any():
        jj = j[ok]
        Yg = sim(ref_X[jj]); Ng = sim.rot(ref_N[jj])
        r = (Ng * (Yg - model_pts[ok])).sum(1)
        dist = np.linalg.norm(Yg - model_pts[ok], axis=1)
        cosv = (Ng * model_nrm[ok]).sum(1)
        inl[ok] = (np.abs(r) < tol) & (cosv > cosmin) & (dist < 2.5 * tol + 0.002)
        rr[ok] = np.abs(r)
    frac = float((model_w * inl).sum() / model_w.sum())
    fin = np.sort(rr[np.isfinite(rr)])
    trms = float(np.sqrt(np.mean(fin[: max(1, int(0.7 * len(fin)))] ** 2))) if len(fin) else 1.0
    return frac, trms


def model_points(model, regions, n, seed=0, weights=None):
    """Area-uniform points on the given regions of the zero-control skin, with normals and region weights."""
    rng = np.random.default_rng(seed)
    P = model.P; T = model.Tv
    reg_ok = np.isin(model.region, [REGIONS.index(r) for r in regions])
    tri_ok = reg_ok[T].all(1)
    a = model.tri_area * tri_ok
    cdf = np.cumsum(a)
    tri = np.minimum(np.searchsorted(cdf, rng.random(n) * cdf[-1]), len(T) - 1)
    r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
    bary = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
    tv = T[tri]
    X = (P[tv] * bary[:, :, None]).sum(1)
    N = unit((model.N0[tv] * bary[:, :, None]).sum(1))
    reg = model.region[tv[np.arange(n), np.argmax(bary, 1)]]
    W = np.ones(n) if weights is None else np.array([weights[REGIONS[k]] for k in reg])
    return X, N, W, reg


COARSE_REGIONS = ['forehead', 'brow', 'eyes', 'nose', 'cheeks', 'mouth', 'jaw', 'chin', 'ears', 'neck']
COARSE_WEIGHTS = {'forehead': 1.0, 'brow': 1.0, 'eyes': 0.6, 'nose': 1.5, 'cheeks': 1.0, 'mouth': 0.8, 'jaw': 0.7,
                  'chin': 0.8, 'ears': 0.7, 'neck': 0.3, 'cranium': 0.3}


def candidate_starts(cloud_X, model, ups, yaws, n_scales=5):
    """Initial similarities from the vertical profile for every (up, yaw)."""
    starts = []
    rl_top = model.top_y
    rl_neck = model.lm['chin'][1] - 0.035
    rl_head_r = 0.5 * np.sqrt(np.ptp(model.P[model.region != REGIONS.index('ears'), 0]) *
                              np.ptp(model.P[model.P[:, 1] > model.lm['nose_tip'][1], 2]))
    for up in ups:
        U = UP[up]
        Yu = cloud_X @ U.T
        hp = head_from_profile(Yu)
        if hp is None:
            continue
        H = hp['top'] - hp['neck_y']
        s_h = (rl_top - rl_neck) / max(H, 1e-12)            # hair on top -> underestimate
        s_w = rl_head_r / max(hp['head_r'], 1e-12)          # hair volume -> underestimate
        s0 = np.exp(0.5 * (np.log(s_h) + np.log(s_w))) * 1.08
        if n_scales >= 5:
            mult = [0.72, 0.85, 1.0, 1.17, 1.38]
        elif n_scales >= 3:
            mult = [0.82, 1.0, 1.2]
        else:
            mult = [1.0]
        for yaw in yaws:
            Ry = yaw_rotation(yaw)
            R = Ry @ U
            for m in mult:
                s = s0 * m
                # place: reference head top (minus ~1 cm of hair) at the RL top, head centre over the RL cranium centre
                top_ref_u = hp['top']
                cx, cz = hp['centre_xz']
                # in up-converted coordinates (before yaw) the centre is (cx, ?, cz); after yaw:
                cu = np.array([cx, top_ref_u, cz])
                cg = Ry @ cu * s
                t = np.array([0.0 - cg[0], rl_top + 0.008 - cg[1], model.C[2] + 0.005 - cg[2]])
                starts.append({'up': up, 'yaw': float(yaw), 'mult': m, 'sim': Sim(s, R, t), 'profile': hp})
    return starts


def coarse_register(cloud, model, ups=None, yaws=None, quick=False, init=None, log_fn=log):
    """Search orientation/scale; returns (best dict, list of all scored candidates).
    quick: smaller reference/model samples and fewer refined candidates, but the same 5 scale guesses
    per orientation as the full search (with 3 scales the densest harness case, c08, had no start in
    the right basin and converged 17 deg off). The caller falls back to the full search when the quick
    result is weak (fit_reference.QUICK_REG_MIN_FRAC / QUICK_REG_MIN_MARGIN)."""
    ups = ups or list(UP.keys())
    yaws = yaws if yaws is not None else [0.0, 90.0, 180.0, 270.0]
    rng = np.random.default_rng(1)
    nref = min(len(cloud.X), 45_000 if quick else 70_000)
    idx = rng.choice(len(cloud.X), nref, replace=False)
    RX = cloud.X[idx]; RN = cloud.N[idx]
    kd = cKDTree(RX)
    Mx, Mn, Mw, _ = model_points(model, COARSE_REGIONS, 1200 if quick else 1800, seed=3, weights=COARSE_WEIGHTS)
    Sx, Sn, Sw, _ = model_points(model, COARSE_REGIONS, 4000, seed=4, weights=COARSE_WEIGHTS)
    centre = np.array([0.0, model.lm['nose_tip'][1], model.C[2]])
    results = []
    if init is not None:
        starts = [{'up': 'landmarks', 'yaw': 0.0, 'mult': 1.0, 'sim': init, 'profile': None}]
    else:
        starts = candidate_starts(cloud.X, model, ups, yaws, n_scales=5)
    def scored(st, sim, X, N, W):
        frac, trms = score_pose(X, N, W, kd, RX, RN, sim)
        up_name, yaw = up_of_rotation(sim.R)
        prior = UP_PRIOR.get(up_name, 0) + (0.01 if min(abs(yaw), abs(yaw - 360)) < 30 else 0)
        # trimmed point-to-plane rms in mm, 0.02 per mm: a pose with 1 mm worse rms needs 2 % more inliers
        return dict(st, sim=sim, frac=frac, trms=trms, score=frac - 0.02 * trms * 1000.0 + prior, up_found=up_name, yaw_found=yaw)

    # stage 1: every start, wide gate, short; keep the most promising
    Px, Pn, Pw = Mx[::3], Mn[::3], Mw[::3]
    stage1 = []
    for st in starts:
        sim = icp(Px, Pn, Pw, kd, RX, RN, st['sim'], iters=10, trim=(0.85, 0.7), gate=0.05, cosmin=0.0, robust=0.01, centre=centre)
        stage1.append(scored(st, sim, Mx, Mn, Mw))
    stage1.sort(key=lambda r: -r['score'])
    keep = stage1[: (8 if quick else 12)]
    # stage 2: tighter gate, all model points
    for r in keep:
        sim = icp(Mx, Mn, Mw, kd, RX, RN, r['sim'], iters=12, trim=(0.8, 0.7), gate=0.02, cosmin=0.3, robust=0.004, centre=centre)
        results.append(scored(r, sim, Sx, Sn, Sw))
    results.sort(key=lambda r: -r['score'])
    results += stage1[len(keep):]
    # refine the best few distinct candidates longer, then pick
    finals = []
    seen = []
    for r in results:
        if len(finals) >= 3:
            break
        if any(rot_angle_deg(r['sim'].R @ s.R.T) < 10 and abs(np.log(r['sim'].s / s.s)) < 0.05 for s in seen):
            continue
        seen.append(r['sim'])
        sim = icp(Mx, Mn, Mw, kd, RX, RN, r['sim'], iters=20, trim=(0.75, 0.7), gate=0.012, cosmin=0.5, robust=0.0025,
                  centre=centre)
        finals.append(scored(r, sim, Sx, Sn, Sw))
    finals.sort(key=lambda r: -r['score'])
    best = finals[0]
    if log_fn:
        for r in finals:
            log_fn(f"  candidate up={r['up_found']} yaw={r['yaw_found']:.1f} scale={r['sim'].s:.5g} inliers={r['frac']:.3f} "
                   f"trms={r['trms'] * 1000:.2f}mm score={r['score']:.3f}")
    # margin to the best start that converged somewhere else (different rotation or scale)
    others = [r for r in finals[1:] + results
              if rot_angle_deg(r['sim'].R @ best['sim'].R.T) > 10 or abs(np.log(r['sim'].s / best['sim'].s)) > 0.05]
    margin = best['score'] - max(r['score'] for r in others) if others else 1.0
    best['margin'] = float(margin)
    return best, results


def landmark_init(model, lm_ref):
    """Similarity from named reference landmarks to the RL landmarks."""
    names = [n for n in lm_ref if n in model.lm]
    if len(names) < 3:
        raise ValueError('need at least 3 known landmarks (%s)' % ', '.join(model.lm))
    A = np.array([lm_ref[n] for n in names], np.float64)
    B = np.array([model.lm[n] for n in names])
    s, R, t = umeyama(A, B)
    return Sim(s, R, t), names


# ---------------------------------------------------------------- symmetry
def symmetry_plane(Xg, iters=12, n0=np.array([1.0, 0, 0]), d0=0.0):
    """Mirror plane (n, d) of points Xg (game space, roughly symmetric about x=0)."""
    kd = cKDTree(Xg)
    n = unit(n0); d = d0
    for _ in range(iters):
        Xm = Xg - 2 * ((Xg @ n) - d)[:, None] * n
        dist, j = kdq(kd, Xm, k=1)
        thr = np.quantile(dist, 0.7)
        sel = dist <= thr
        p = Xg[sel]; q = Xg[j[sel]]
        v = p - q
        # plane normal: dominant direction of p - q, sign toward +x
        lens = np.linalg.norm(v, axis=1)
        m = lens > 1e-4
        if m.sum() < 20:
            break
        vv = v[m] * np.sign((v[m] @ n))[:, None]
        nn = unit(vv.sum(0))
        mid = 0.5 * (p + q)
        dd = float(np.median(mid @ nn))
        if np.degrees(np.arccos(np.clip(nn @ n, -1, 1))) < 0.01 and abs(dd - d) < 1e-5:
            n, d = nn, dd
            break
        n, d = nn, dd
    Xm = Xg - 2 * ((Xg @ n) - d)[:, None] * n
    dist, _ = kdq(kd, Xm, k=1)
    return n, d, float(np.sqrt(np.mean(np.sort(dist)[: int(0.7 * len(dist))] ** 2)))
