"""Residuals per region, control gaps, colour medians, beard coverage/style."""
import os, hashlib
import numpy as np
from scipy.spatial import cKDTree

from fitcommon import kdq, srgb_to_lab, unit, r3, CACHE_DIR, BEARD_DIR
from rlmodel import REGIONS, FACE_REGIONS, REGION_CONTROLS
from segment import SKIN, HAIR, OTHER, BEARD


# ------------------------------------------------------------------ residuals
def point_residuals(model, Pv, Yg, Ng, gate=0.015):
    """Signed distance (mm, + = reference outside the skin) of reference skin points to the skin Pv,
    with the RL region of each point; invalid matches (past open boundaries, opposed normals) dropped."""
    surf = model.surface(Pv)
    pr = model.project(surf, Yg, max_dist=gate * 1.5)
    cosv = (pr['n'] * Ng).sum(1)
    rimw = (model.open_boundary[pr['tv']] * pr['bary']).sum(1)
    ok = pr['ok'] & (pr['off'] < 0.0015) & (cosv > 0.4) & (np.abs(pr['d']) < gate) & ~((rimw > 0.9) & (pr['off'] > 0.0004))
    reg = np.full(len(Yg), -1)
    k = np.argmax(pr['bary'], 1)
    reg[ok] = model.region_stat[pr['tv'][np.arange(len(k)), k]][ok]
    return pr['d'] * 1000.0, reg, ok, pr


def robust_inliers(x, k=3.5, floor=0.5):
    """Inlier mask of residuals x (mm): within k robust sigmas (1.4826 MAD, at least `floor` mm) of the
    median. Isolated mislabelled points (cavity walls, seams) are outliers; a real shape difference
    moves the whole region and stays in."""
    if len(x) < 5:
        return np.ones(len(x), bool)
    med = np.median(x)
    sig = max(1.4826 * np.median(np.abs(x - med)), floor)
    return np.abs(x - med) <= k * sig


def region_stats(d, reg, ok, regions=REGIONS):
    """Per region (>= 20 points) robust statistics: rms / mean / p90 over the inliers of robust_inliers,
    plus the raw rms and the outlier count. face_rms / face_p90 likewise over FACE_REGIONS."""
    out = {}
    for r in regions:
        m = ok & (reg == REGIONS.index(r))
        if m.sum() >= 20:
            x = d[m]
            inl = robust_inliers(x)
            xi = x[inl]
            out[r] = {'rms': float(np.sqrt(np.mean(xi ** 2))), 'mean': float(np.mean(xi)), 'n': int(m.sum()),
                      'p90': float(np.percentile(np.abs(xi), 90)), 'rms_raw': float(np.sqrt(np.mean(x ** 2))),
                      'outliers': int((~inl).sum())}
    fm = ok & np.isin(reg, [REGIONS.index(r) for r in FACE_REGIONS])
    if fm.sum():
        x = d[fm]
        xi = x[robust_inliers(x)]
        face_rms = float(np.sqrt(np.mean(xi ** 2)))
        face_p90 = float(np.percentile(np.abs(xi), 90))
    else:
        face_rms = face_p90 = float('nan')
    return face_rms, face_p90, out


def residual_block(face_rms, face_p90, stats):
    return {'face_rms': round(face_rms, 3), 'face_p90': round(face_p90, 3),
            'by_region': {r: round(v['rms'], 3) for r, v in stats.items()},
            'outliers_by_region': {r: v['outliers'] for r, v in stats.items() if v.get('outliers')}}


def vertex_residuals(model, Pv, Nv, Yg, Ng, lab, smooth=2):
    """Per RL vertex signed residual (mm) from the nearest reference skin point, for the heat map."""
    skin = lab == SKIN
    if skin.sum() < 10:
        return np.zeros(len(Pv)), np.zeros(len(Pv), bool)
    kd = cKDTree(Yg[skin])
    d, j = kdq(kd, Pv, k=1, distance_upper_bound=0.012)
    ok = np.isfinite(d)
    j = np.where(ok, j, 0)
    Ys = Yg[skin][j]; Ns = Ng[skin][j]
    r = ((Ys - Pv) * Nv).sum(1) * 1000.0
    ok &= (Ns * Nv).sum(1) > 0.4
    # nearest reference point of any label must be skin (no residual under hair / beard)
    kda = cKDTree(Yg)
    _, ja = kdq(kda, Pv, k=1)
    ok &= lab[ja] == SKIN
    r = np.where(ok, r, 0.0)
    w = ok.astype(float)
    E = model.edges
    for _ in range(smooth):
        acc = np.zeros(len(r)); cnt = np.zeros(len(r))
        np.add.at(acc, E[:, 0], r[E[:, 1]] * w[E[:, 1]]); np.add.at(cnt, E[:, 0], w[E[:, 1]])
        r = np.where(ok, (r * w + acc) / np.maximum(w + cnt, 1e-9), r)
    # welded duplicates share the value
    acc = np.zeros(model.weld.max() + 1); cnt = np.zeros(model.weld.max() + 1)
    np.add.at(acc, model.weld, r * ok); np.add.at(cnt, model.weld, ok)
    okw = cnt[model.weld] > 0
    return np.where(okw, acc[model.weld] / np.maximum(cnt[model.weld], 1), 0.0), okw


def control_gaps(stats, v, names, beard_present, rms_thresh=1.4, mean_thresh=0.9, hidden=()):
    """Regions whose robust (outlier-trimmed) rms or mean bias after the fit stays large."""
    gaps = []
    for r, s in sorted(stats.items(), key=lambda kv: -kv[1]['rms']):
        if r == 'cranium':
            continue
        if s['n'] - s.get('outliers', 0) < 20:
            continue
        if s['rms'] < rms_thresh and abs(s['mean']) < mean_thresh:
            continue
        ctrls = REGION_CONTROLS.get(r, [])
        at_bound = [f"{c} {v[names.index(c)]:+.2f}" for c in ctrls if abs(v[names.index(c)]) >= 0.98]
        if not ctrls:
            note = f'no identity control acts on the {r}'
        elif at_bound:
            note = 'control(s) at their limit: ' + ', '.join(at_bound)
        else:
            note = 'shape difference not spanned by ' + ', '.join(ctrls)
        if r in ('eyes', 'mouth'):
            note += ' (low-weight region: eyelids/lips are unreliable in Meshy output)'
        if r in ('jaw', 'chin') and beard_present:
            note += ' (partly under the beard)'
        hid = [c for c in ctrls if c in hidden]
        if hid:
            note += f" ({', '.join(hid)} hidden under hair/beard: held at 0, the visible rest of the region is not fitted)"
        gaps.append({'region': r, 'rms_mm': round(s['rms'], 2), 'mean_mm': round(s['mean'], 2),
                     'direction': 'out' if s['mean'] >= 0 else 'in', 'note': note,
                     'points': s['n'], 'outliers': s.get('outliers', 0)})
    return gaps


# ------------------------------------------------------------------ colours
CLIP = 0.98


def _trimmed_median(C, lo=20, hi=80):
    if len(C) == 0:
        return None
    L = srgb_to_lab(C)[:, 0]
    a, b = np.percentile(L, [lo, hi])
    m = (L >= a) & (L <= b)
    if m.sum() < 5:
        m = np.ones(len(C), bool)
    return [round(float(x), 3) for x in np.median(C[m], 0)]


def shading_model(Ng, C, sel, norm_sel):
    """Baked directional light estimated on skin: linear luminance ~ a + b.n (first-order spherical
    harmonics, speculars/shadows trimmed, clipped texels left out), normalised so that the median
    shading over norm_sel (the skin set the skin colour median is taken on) is 1: the correction
    then removes the light's direction-dependent part without changing the exposure of the median.
    Returns s(N) -> per point shading factor (clamped 0.5..1.6) and the fit info."""
    from fitcommon import srgb_to_linear
    idx = np.nonzero(sel & (C.max(1) < CLIP))[0]
    if len(idx) < 200:
        return (lambda N: np.ones(len(N))), {'used': False}
    Y = srgb_to_linear(C[idx]) @ np.array([0.2126, 0.7152, 0.0722])
    A = np.c_[np.ones(len(idx)), Ng[idx]]
    keep = np.ones(len(idx), bool)
    for _ in range(3):
        coef, *_ = np.linalg.lstsq(A[keep], Y[keep], rcond=None)
        r = Y - A @ coef
        lo, hi = np.percentile(r[keep], [5, 95])
        keep = (r > lo) & (r < hi)
    pred = A @ coef
    nidx = np.nonzero(norm_sel)[0]
    ref = float(np.median(coef[0] + Ng[nidx] @ coef[1:])) if len(nidx) > 50 else float(np.median(pred))
    if ref <= 1e-4:
        return (lambda N: np.ones(len(N))), {'used': False}
    r2 = 1 - np.var(Y[keep] - pred[keep]) / max(np.var(Y[keep]), 1e-12)

    strength = float(np.linalg.norm(coef[1:]) / ref)
    if r2 < 0.2 or strength > 1.0:
        # implausible directional light (mislabelled dark/bright regions dominate): leave colours as they are
        return (lambda N: np.ones(len(N))), {'used': False, 'strength': round(strength, 3), 'r2': round(float(r2), 3)}

    def s(N):
        return np.clip((coef[0] + N @ coef[1:]) / ref, 0.5, 1.6)
    return s, {'used': True, 'light_dir': [round(float(x), 3) for x in coef[1:] / max(np.linalg.norm(coef[1:]), 1e-9)],
               'strength': round(float(np.linalg.norm(coef[1:]) / ref), 3), 'r2': round(float(r2), 3)}


def colours(model, Pv, Yg, cloud_C, lab, G, gauss_skin=None, Ng=None, hair_gauss=None):
    """Robust colour medians. Clipped texels (any channel >= CLIP) are left out of every median. When
    normals are given, a directional baked-light estimate (from the skin) is divided out first
    (linear RGB), normalised on the skin-colour set, and points the light leaves in deep shadow
    (shading < 0.55) are left out too, so side-lit faces do not bias the medians.
    hair_gauss: hair colour models; lip samples that look like hair (a moustache) are dropped."""
    from fitcommon import srgb_to_linear, linear_to_srgb
    from segment import feats
    out = {}
    reg = G['reg']; d = G['d']
    vnear = G['vnear']
    R = {r: REGIONS.index(r) for r in REGIONS}
    skin_sel = (lab == SKIN) & np.isin(reg, [R['cheeks'], R['forehead']]) & (np.abs(d) < 0.004)
    if skin_sel.sum() < 50:
        skin_sel = (lab == SKIN) & (np.abs(d) < 0.006)
    clipped = cloud_C.max(1) >= CLIP
    out['_clipped_skin_fraction'] = round(float(clipped[skin_sel].mean()), 3) if skin_sel.any() else 0.0
    usable = ~clipped
    out['_shading'] = {'used': False}
    if Ng is not None:
        broad = (lab == SKIN) & np.isin(reg, [R[r] for r in ('cheeks', 'forehead', 'nose', 'jaw', 'chin', 'brow', 'neck')]) & \
            (np.abs(d) < 0.004)
        sfn, sinfo = shading_model(Ng, cloud_C, broad, skin_sel & usable)
        out['_shading'] = sinfo
        if sinfo['used']:
            sh = sfn(Ng)
            usable &= sh > 0.55
            cloud_C = np.clip(linear_to_srgb(srgb_to_linear(cloud_C) / sh[:, None]), 0, 1)
    ss = skin_sel & usable
    if ss.sum() < max(30, 0.2 * skin_sel.sum()) or out['_clipped_skin_fraction'] > 0.5:
        # most of the skin is blown out: the unclipped rest is the shadow side, darker than the albedo;
        # the plain texel median (clipped included) is the less wrong estimate (a warning is raised)
        ss = skin_sel
        out['_skin_from_clipped'] = True
    out['skin_srgb'] = _trimmed_median(cloud_C[ss])
    skin_lab = srgb_to_lab(np.array(out['skin_srgb'])) if out['skin_srgb'] else None
    hair_sel = (lab == HAIR) & ~clipped
    out['hair_srgb'] = _trimmed_median(cloud_C[hair_sel], 15, 85) if hair_sel.sum() >= 50 else None
    if out['hair_srgb'] is None and ((lab == BEARD) & ~clipped).sum() >= 50:
        out['hair_srgb'] = _trimmed_median(cloud_C[(lab == BEARD) & ~clipped], 15, 85)
    # lips: points whose nearest RL vertex is in the lips group, facing forward, not hair; a moustache
    # or beard over the lips (hair-coloured, even where labelled skin) is not lip colour
    lips_v = model.lips_front
    lsel = lips_v[vnear] & (np.abs(d) < 0.004) & ~np.isin(lab, [HAIR, BEARD, OTHER]) & usable
    out['_lip_hairlike_dropped'] = 0
    if hair_gauss and gauss_skin is not None and lsel.any():
        Fl = feats(cloud_C[lsel])
        mh = np.min(np.stack([g_.md(Fl) for g_ in hair_gauss]), 0)
        hairlike = (mh < gauss_skin.md(Fl)) & (mh < 25.0)
        li = np.nonzero(lsel)[0]
        lsel[li[hairlike]] = False
        out['_lip_hairlike_dropped'] = int(hairlike.sum())
    if lsel.sum() >= 30:
        Cl = cloud_C[lsel]
        a = srgb_to_lab(Cl)[:, 1]
        red = a >= np.median(a)
        if skin_lab is not None and np.median(a[red]) < skin_lab[1] + 3:
            out['lip_srgb'] = None                     # lips indistinguishable from skin
        else:
            out['lip_srgb'] = _trimmed_median(Cl[red], 10, 90)
    else:
        out['lip_srgb'] = None
    # brows: band above the eyes, darker than skin
    ey = model.eye_centres[0][1]
    ipd = model.ipd
    ax = np.abs(Yg[:, 0])
    band = (Yg[:, 1] > ey + 0.14 * ipd) & (Yg[:, 1] < ey + 0.45 * ipd) & (ax > 0.15 * ipd) & (ax < 0.95 * ipd) & \
        (Yg[:, 2] > model.lm['eye_l'][2] - 0.01) & (np.abs(d) < 0.006) & np.isin(lab, [SKIN, HAIR, OTHER]) & usable
    out['brow_srgb'] = None
    if band.sum() >= 40 and skin_lab is not None:
        Lb = srgb_to_lab(cloud_C[band])[:, 0]
        dark = Lb < skin_lab[0] - 12
        if dark.sum() >= max(15, 0.06 * band.sum()):
            # the darker half of the dark set: brow edges blend into skin
            out['brow_srgb'] = _trimmed_median(cloud_C[band][dark], 0, 50)
    # eyes: iris area around the front of each eyeball
    out['eye_srgb'] = None
    sel = np.zeros(len(Yg), bool)
    for ef in model.eye_front:
        rr = np.hypot(Yg[:, 0] - ef[0], Yg[:, 1] - ef[1])
        sel |= (rr < 0.42 * model.eye_radius) & (Yg[:, 2] > ef[2] - 0.008) & (Yg[:, 2] < ef[2] + 0.008)
    sel &= ~clipped
    if sel.sum() >= 15:
        Ce = cloud_C[sel]
        Le = srgb_to_lab(Ce)
        chroma = np.hypot(Le[:, 1], Le[:, 2])
        keep = ~((Le[:, 0] > 70) & (chroma < 15))                 # sclera
        if gauss_skin is not None:
            from segment import feats
            keep &= gauss_skin.md(feats(Ce)) > 12                  # eyelid skin
        keep &= Le[:, 0] > 8                                       # pupil
        if keep.sum() >= 10:
            out['eye_srgb'] = [round(float(x), 3) for x in np.median(Ce[keep], 0)]
    return out


# ------------------------------------------------------------------ control support covered by hair / beard
def control_coverage(model, Pv, Yg, lab, v, vw, r=0.002, reach=0.15, layer=0.03):
    """How much of each control's support the reference covers with hair / beard.

    Per exposed RL skin vertex (welded representatives, eyeballs excluded) the outward vertex normal is
    probed from 2 mm inside to `reach` outside in steps of r (probe radius r) against the segmented head-zone
    reference points: the vertex is `seen` when the first reference point met is skin, `covered` when it is
    not skin and hair or beard lies along the normal within `layer` of that first point (fused hair/beard,
    or skin under a separate hair mesh, which the occlusion test labels other).
    Per control two shares of covered vertices, both over the union of its two sides (per vertex the larger
    of the p and n effect, so the test does not depend on the sign a first pass gave a control it cannot see;
    with the active side instead, brow_ridge on the long-hair cases sat at 0.43-0.45 support / 0.51-0.56
    evidence, close to the thresholds, against 0.24 / 0.22 over both sides):
      support  weights |delta| (as the harness ground truth's visible_fraction);
      evidence weights (delta . n)^2 x vertex area x region weight, i.e. what the point-to-plane data term
               could see of the control: tangential motion (mouth corners sliding sideways) counts nothing.
    `v` is kept for the interface (unused). Returns ({control: {'support', 'evidence', 'seen'}}, info)."""
    vi = np.nonzero(model.rep & model.exposed & ~model.is_eye)[0]
    Nv = model.normals(Pv)
    kd = cKDTree(Yg)
    first = np.full(len(vi), -1)
    tfirst = np.full(len(vi), np.inf)
    hairy = np.zeros(len(vi), bool)
    t = -0.002
    while t <= reach + 1e-9:
        q = Pv[vi] + Nv[vi] * t
        d, j = kdq(kd, q, k=1, distance_upper_bound=r)
        h = np.isfinite(d)
        lj = np.where(h, lab[np.where(h, j, 0)], -1)
        new = h & (first < 0)
        first[new] = lj[new]
        tfirst[new] = t
        hairy |= np.isin(lj, [HAIR, BEARD]) & (t - tfirst <= layer)
        t += r
    seen = first == SKIN
    covered = ~seen & hairy
    area = model.vertex_area[vi]
    n_ = Nv[vi]
    k = len(model.names)
    out = {}
    for c, nm in enumerate(model.names):
        Dp = model.D[c][vi]; Dn = model.D[k + c][vi]
        w_s = np.maximum(np.linalg.norm(Dp, axis=1), np.linalg.norm(Dn, axis=1))
        w_e = np.maximum(np.abs((Dp * n_).sum(1)), np.abs((Dn * n_).sum(1))) ** 2 * area * vw[vi]
        sh = lambda w, m: float((w * m).sum() / w.sum()) if w.sum() > 0 else 0.0
        out[nm] = {'support': sh(w_s, covered), 'evidence': sh(w_e, covered), 'seen': sh(w_s, seen)}
    info = {'vertices': int(len(vi)), 'seen': int(seen.sum()), 'covered': int(covered.sum()),
            'other': int(((first >= 0) & ~seen & ~covered).sum()), 'no_hit': int((first < 0).sum()),
            'probe_r_mm': round(r * 1000, 2), 'reach_mm': round(reach * 1000, 1)}
    return out, info


def hidden_support_weight(model, hidden_idx, allow_idx, floor_m=0.0005):
    """Per-vertex data-weight multiplier 1 - s for the refinement once controls are hidden (pinned at 0):
    s = H / (H + A + floor^2), H / A = sum of the squared full-range effects of the hidden / still-allowed
    controls at the vertex. Skin that only a hidden control moves (the ear lobes under a bob for ear_size)
    is not explained by the model any more and would otherwise drag the other controls and the pose
    (c05: control RMSE 0.053 -> 0.110 with ear_size pinned and its lobes still weighted); skin that allowed
    controls move as well keeps a share of its weight, skin no control moves keeps all of it."""
    k = len(model.names)
    eff2 = np.maximum((model.D[:k] ** 2).sum(2), (model.D[k:] ** 2).sum(2))      # (k, n) m^2
    H = eff2[list(hidden_idx)].sum(0) if len(hidden_idx) else np.zeros(model.n)
    A = eff2[list(allow_idx)].sum(0) if len(allow_idx) else np.zeros(model.n)
    return 1.0 - H / (H + A + floor_m ** 2)


# ------------------------------------------------------------------ beard
def beard_coverage(model, Pv, Yg, lab, max_dist=0.04, within=None):
    """Area-weighted fraction of the RL beard region (and its parts) whose nearest reference point is
    beard (a fused reference has no skin under the beard). within=r: covered when any beard point
    is closer than r (for separate beard meshes over a skin)."""
    kd = cKDTree(Yg)
    d, j = kdq(kd, Pv, k=1, distance_upper_bound=max_dist)
    ok = np.isfinite(d)
    isb = np.zeros(len(Pv), bool)
    isb[ok] = lab[j[ok]] == BEARD
    if within is not None:
        # separate beard mesh over the skin: covered when beard geometry lies along the vertex normal
        Nv = model.normals(Pv)
        dk, jk = kdq(kd, Pv, k=12, distance_upper_bound=within)
        isb = np.zeros(len(Pv), bool)
        for c in range(dk.shape[1]):
            okc = np.isfinite(dk[:, c])
            if not okc.any():
                continue
            vec = Yg[np.where(okc, jk[:, c], 0)] - Pv
            along = (vec * Nv).sum(1)
            tang = np.linalg.norm(vec - along[:, None] * Nv, axis=1)
            isb |= okc & (tang < 0.0035) & (along > -0.002)
    va = model.vertex_area
    out = {}
    for name, m in [('all', model.beard_region)] + list(model.beard_parts.items()):
        w = va * m
        out[name] = float((w * isb).sum() / max(w.sum(), 1e-12))
    th = d[isb] * 1000 if isb.any() else np.array([0.0])
    return out, float(np.median(th))


def beard_style_coverages(load_model):
    """Coverage of the RL beard region by each existing beard module (cached)."""
    import gltfio
    from refmesh import RefMesh
    out = {}
    if not os.path.isdir(BEARD_DIR):
        return out
    os.makedirs(CACHE_DIR, exist_ok=True)
    for fn in sorted(os.listdir(BEARD_DIR)):
        if not fn.endswith('.glb'):
            continue
        path = os.path.join(BEARD_DIR, fn)
        st = os.stat(path)
        key = hashlib.sha1(f'{path}|{st.st_size}|{int(st.st_mtime)}|b3'.encode()).hexdigest()[:16]
        cp = os.path.join(CACHE_DIR, f'beard_{fn[:-4]}_{key}.npz')
        if os.path.exists(cp):
            d = np.load(cp)
            out[fn[:-4]] = {k: float(d[k]) for k in d.files}
            continue
        js = gltfio._read_container(path)[0]
        sex = js.get('asset', {}).get('extras', {}).get('rlBeard', {}).get('sex', 'male')
        m = load_model(sex)
        parts = gltfio.read(path, want_texture=False)
        lod0 = [p for p in parts if 'lod0' in p['name']] or parts
        X = RefMesh(parts=lod0).sample(80_000, seed=2).X
        cov, th = beard_coverage(m, m.P, X, np.full(len(X), BEARD), within=0.013)
        cov['thickness_mm'] = th
        np.savez(cp, **cov)
        out[fn[:-4]] = cov
    return out


def model_skin_points(m, n=60_000):
    rng = np.random.default_rng(5)
    T = m.Tv
    cdf = np.cumsum(m.tri_area)
    tri = np.minimum(np.searchsorted(cdf, rng.random(n) * cdf[-1]), len(T) - 1)
    r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
    b = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
    return (m.P[T[tri]] * b[:, :, None]).sum(1)


BEARD_PART_W = {'moustache': 1.0, 'chin_front': 1.0, 'jaw': 2.0, 'neck': 0.5}
SHORT_BEARD_MM = 3.0


def beard_present(cov):
    """A beard covers > 30 % of the beard region AND the front of the chin or the moustache area: a dark
    band under the jaw or on the front of the neck alone (shadow, a thicker neck) is not a beard."""
    return bool(cov.get('all', 0) > 0.3 and max(cov.get('chin_front', cov.get('chin', 0)), cov.get('moustache', 0)) >= 0.4)


def nearest_beard(cov, styles, thickness_mm=None):
    """Beard module for measured part coverages. Shape decides the family: jaw sides covered (jaw >= 0.6)
    = full/short beard, chin without the jaw sides = goatee, moustache only = moustache; within the
    full-beard family the measured stand-off decides (< SHORT_BEARD_MM = short_beard). Weighted L1 part
    distances to every module are returned as scores (weights BEARD_PART_W, smaller = closer)."""
    scores = {}
    for name, sc in styles.items():
        dist = sum(w * abs(cov.get(p, 0) - sc.get(p, sc.get('chin', 0) if p == 'chin_front' else 0))
                   for p, w in BEARD_PART_W.items())
        scores[name] = round(dist, 3)
    jaw = cov.get('jaw', 0); chin = cov.get('chin_front', cov.get('chin', 0)); mou = cov.get('moustache', 0)
    if jaw >= 0.6:
        fam = 'short_beard' if (thickness_mm is not None and thickness_mm < SHORT_BEARD_MM) else 'full_beard'
    elif chin >= 0.5:
        fam = 'goatee'
    elif mou >= 0.5:
        fam = 'moustache'
    else:
        fam = None
    if fam is not None and (fam in styles or not styles):
        return fam, scores
    best = min(scores, key=scores.get) if scores else fam
    return best, scores
