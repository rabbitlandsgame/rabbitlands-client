"""Fit the RL head's 21 identity controls (+ colours, hair envelope, beard) to a
Meshy-style reference bust/head GLB.

    python fit_reference.py <reference.glb> --sex male|female --out <dir>
        [--landmarks <json>] [--up auto|y|z|-y|-z|x|-x] [--yaw auto|0|90|180|270]
        [--weights <json>] [--no-envelope] [--quick] [--gap-targets] [--label NAME]
        [--weak auto|fit|off] [--strict] [--seed N] [--quiet]

Writes <dir>/fit.json, envelope.npz (when hair is found and --no-envelope is not
given), front.png, profile.png, three_quarter.png, segmentation.png, report.md.
See README.md for the method and the exact output definitions.
"""
import os, sys, json, argparse, time, traceback, hashlib, re
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fitcommon  # noqa: E402  (sets up sys.path for headref)
from fitcommon import (kdq, Sim, Timer, log, LOG, control_names, presets, BASE_PRESET, r3, rot_angle_deg, rot_y, unit,
                       srgb_to_lab)  # noqa: E402
import rlmodel, register, segment, solve, analysis, envelope, fitviz  # noqa: E402
from rlmodel import REGIONS, FACE_REGIONS, REGION_CONTROLS  # noqa: E402
from refmesh import RefMesh, Cloud  # noqa: E402
from segment import SKIN, HAIR, OTHER, BEARD  # noqa: E402
from register import UP, up_of_rotation  # noqa: E402

# eye and lip controls: they move the surface by a few mm at most, under eyelids / lip seams that
# image-to-3D output renders unreliably; fitted only where the data clearly supports them (--weak auto)
WEAK_CONTROLS = ('eye_size', 'eye_tilt', 'eyelid', 'cupid_bow', 'lip_fullness')
WEAK_SNR = 1.5            # effect / local residual below which a weak control is not measured
WEAK_OBS = 25.0           # e/lambda below which a kept weak control is 'low_observability' (data sd > 0.1) ...
WEAK_SNR_MEASURED = 2.0   # ... or snr below this (kept, 1.5 <= snr < 2: the whole range is < 2x the local residual)
HIDDEN_COVER = 0.5        # share of a control's support (|delta|-weighted) covered by hair/beard: 'hidden' (pinned to 0)
HIDDEN_EVIDENCE = 0.65    # ... or share of its point-to-plane evidence ((delta.n)^2 x area x region weight) covered
BEYOND_LIMIT = 1.15       # relaxed value (bound raised to 2) above which a control at its limit is beyond the RL range
QUICK_REG_MIN_FRAC = 0.4  # --quick: coarse result weaker than this (inlier fraction) or ...
QUICK_REG_MIN_MARGIN = 0.1  # ... with a runner-up this close re-runs the full orientation/scale search
HEAD_ZONE_M = 0.19        # dense resample radius around the cranium centre (game m)
ROT_PRIOR_SD_DEG = 0.5    # rotation prior sd (refinement): lambda_rot = sigma^2 / (N_eff sd^2), see auto_lambda
NEUTRAL_STYLE = {'freckles': 0.0, 'liner': 0.0, 'liner_wing': 0.0, 'brow_style': 'soft', 'brow_thickness': 0.0}


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('reference')
    ap.add_argument('--sex', required=True, choices=['male', 'female'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--landmarks', help='json {eye_l, eye_r, nose_tip, chin, mouth, ear_l, ear_r: [x,y,z]} in reference coordinates')
    ap.add_argument('--up', default='auto', choices=['auto'] + list(UP.keys()))
    ap.add_argument('--yaw', default='auto', choices=['auto', '0', '90', '180', '270'],
                    help='face direction in the up-converted reference: (sin yaw, 0, cos yaw); 0 = +Z, 90 = +X')
    ap.add_argument('--weights', help='json of region weights {region: w} and/or lambda_rel, lambda_abs, scale_prior, rot_prior')
    ap.add_argument('--no-envelope', action='store_true')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--gap-targets', action='store_true', help='also rank MPFB face targets that would reduce the residual')
    ap.add_argument('--label', help='preset label (default: reference file name; pass one when merging several fits)')
    ap.add_argument('--weak', default='auto', choices=['auto', 'fit', 'off'],
                    help='eye/lip controls (%s): auto = fit, then keep only those the data supports '
                         '(effect / local residual >= %.1f); fit = always; off = never (base preset values)' % (', '.join(WEAK_CONTROLS), WEAK_SNR))
    ap.add_argument('--strict', action='store_true', help='exit code 3 when quality.status is "fail"')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--quiet', action='store_true')
    return ap.parse_args(argv)


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    st = os.stat(path)
    return {'sha256': h.hexdigest(), 'bytes': int(st.st_size),
            'mtime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(st.st_mtime))}


def head_cloud(ref, cloud_g, sim, model, n_head, seed):
    """Dense resample of the reference near the head (faces within HEAD_ZONE_M of the RL cranium centre in
    game space) merged with the global sample outside it. Real busts carry a torso and voluminous hair,
    so an area-uniform sample leaves the face with a few per cent of the points."""
    fc = sim(ref.V[ref.F].mean(1))
    near = np.linalg.norm(fc - model.C, axis=1) < HEAD_ZONE_M
    area_g = ref.area * sim.s ** 2
    A_all = float(area_g.sum()); A_head = float(area_g[near].sum())
    info = {'head_zone_area_cm2': round(A_head * 1e4, 1), 'total_area_cm2': round(A_all * 1e4, 1)}
    s_g = np.sqrt(A_all / max(len(cloud_g), 1))
    if A_head <= 0.002 or near.sum() < 100:
        info.update(dense=False, n_head=0)
        return cloud_g, info, float(np.clip(3.5 * s_g, 0.002, 0.008)), float(np.clip(1.6 * s_g, 0.0008, 0.0025))
    dense = ref.sample(n_head, seed=seed + 17, face_mask=near.astype(float))
    gpos = sim(cloud_g.X)
    outside = np.linalg.norm(gpos - model.C, axis=1) >= HEAD_ZONE_M
    cloud = Cloud.concat(dense, cloud_g.subset(np.nonzero(outside)[0]))
    s_h = np.sqrt(A_head / n_head)
    info.update(dense=True, n_head=int(n_head), n_outside=int(outside.sum()), spacing_head_mm=round(s_h * 1000, 3),
                spacing_global_mm=round(s_g * 1000, 3))
    link_r = float(np.clip(3.5 * max(s_g if outside.any() else s_h, s_h), 0.002, 0.008))
    occ_r = float(np.clip(1.6 * s_h, 0.0008, 0.0025))
    info.update(link_r_mm=round(link_r * 1000, 2), occ_r_mm=round(occ_r * 1000, 2))
    return cloud, info, link_r, occ_r


FACE_AREA_MM2 = 20000.0    # area of the fitted face skin (forehead to chin, ear to ear), for N_eff


def auto_lambda(sigma2_parts, ell_mm):
    """Absolute control prior per control part from the residual statistics after the first solve.
    Gaussian control prior with sd 0.5; residuals that are correlated over ell (the residual correlation
    length) give N_eff = FACE_AREA_MM2 / (pi ell^2) independent observations (clipped 30..2000), and
    the residual level that matters for a part is the one where it acts (sigma_j^2: residual weighted
    by that part's squared surface effect). Then
        lambda_j = sigma_j^2 / (N_eff 0.5^2) = 4 sigma_j^2 / N_eff   (mm^2, clipped to [1e-5, 0.5]),
    the MAP prior for that information. Clean in-model data (sigma ~0.1-0.4 mm, ell ~3 mm) gets a
    negligible prior; an off-model reference (sigma ~1 mm, ell ~25 mm: the residual is unmodelled shape,
    not noise) a strong one, so the controls do not chase the mismatch; a control acting where the
    model and reference systematically differ (eyes, lip seam) is held more firmly than one acting
    where they agree."""
    if sigma2_parts is None:
        return 0.001, None
    ell = 3.0 if ell_mm is None or not np.isfinite(ell_mm) else float(ell_mm)
    n_eff = float(np.clip(FACE_AREA_MM2 / (np.pi * ell ** 2), 30.0, 2000.0))
    return np.clip(4.0 * np.asarray(sigma2_parts, float) / n_eff, 1e-5, 0.5), n_eff


def run(a):
    T = Timer()
    LOG['quiet'] = a.quiet
    os.makedirs(a.out, exist_ok=True)
    warnings = []
    names = control_names()
    wcfg = json.load(open(a.weights)) if a.weights else {}
    model = rlmodel.load(a.sex)
    region_w, wmap = model.region_weights(wcfg)
    log(f'[fit] RL head {a.sex}: {model.n} skin vertices; reference {a.reference}')
    fp = fingerprint(a.reference)

    # ---------------------------------------------------------------- load + sample
    ref = RefMesh(a.reference)
    rs = ref.summary()
    log(f"[fit] reference: {rs['triangles']} triangles, {rs['parts']} part(s), colour from {rs['colour_source']}  ({T.mark('load'):.1f}s)")
    if 'factor' in rs['colour_source'] and len(rs['colour_source']) == 1:
        warnings.append('reference has no texture or vertex colours: colours and colour segmentation are unreliable')
    if rs['flipped_parts']:
        warnings.append(f"reference part(s) {rs['flipped_parts']} were inside-out; their normals were flipped")
    n_samp = 110_000 if a.quick else 240_000
    cloud_g = ref.sample(n_samp, seed=a.seed)
    log(f'[fit] sampled {len(cloud_g)} points ({T.mark("sample"):.1f}s)')

    # ---------------------------------------------------------------- orientation / scale
    init = None
    if a.landmarks:
        lm = json.load(open(a.landmarks))
        init, used = register.landmark_init(model, {k: np.asarray(v, float) for k, v in lm.items()})
        log(f'[fit] landmark initialisation from {used}: scale {init.s:.5g}')
    ups = None if a.up == 'auto' else [a.up]
    yaws = None if a.yaw == 'auto' else [float(a.yaw)]
    best, allc = register.coarse_register(cloud_g, model, ups=ups, yaws=yaws, quick=a.quick, init=init)
    reg_info = {'mode': 'quick' if a.quick else 'full', 'quick_fallback': None}
    if a.quick and init is None and (best['frac'] < QUICK_REG_MIN_FRAC or best['margin'] < QUICK_REG_MIN_MARGIN):
        # the quick search is not conclusive: run the full search (more reference/model points, 12 + 3
        # refined candidates) on the same sample and keep the better-scoring pose
        log(f"[fit] quick orientation search inconclusive (inliers {best['frac']:.3f}, margin {best['margin']:.3f}): full search")
        best_f, allc_f = register.coarse_register(cloud_g, model, ups=ups, yaws=yaws, quick=False, init=None)
        reg_info['quick_fallback'] = {'quick': {'inliers': round(best['frac'], 3), 'margin': round(best['margin'], 3),
                                                'scale': best['sim'].s, 'score': round(best['score'], 3)},
                                      'full': {'inliers': round(best_f['frac'], 3), 'margin': round(best_f['margin'], 3),
                                               'scale': best_f['sim'].s, 'score': round(best_f['score'], 3)}}
        if best_f['score'] >= best['score']:
            best, allc = best_f, allc_f
        reg_info['quick_fallback']['used'] = 'full' if best is best_f else 'quick'
    sim = best['sim']
    log(f"[fit] orientation up={best['up_found']} yaw={best['yaw_found']:.1f} scale={sim.s:.6g} inliers={best['frac']:.3f} "
        f"margin={best['margin']:.3f} ({T.mark('register'):.1f}s, {len(allc)} starts)")
    if best['margin'] < 0.05 and init is None:
        warnings.append(f"orientation search: runner-up start scored within {best['margin']:.3f} of the best; check the previews "
                        "or pass --up/--yaw/--landmarks")
    if best['frac'] < 0.35:
        warnings.append(f"low registration inlier fraction after the coarse search ({best['frac']:.2f}): the reference may not be a "
                        "head/bust, or is far from the RL proportions")

    # ---------------------------------------------------------------- symmetry (small roll/yaw correction)
    Xg = sim(cloud_g.X)
    surf0 = model.surface(model.P)
    pr0 = model.project(surf0, Xg, max_dist=0.02)
    facez = pr0['ok'] & (np.abs(pr0['d']) < 0.008) & np.isin(model.region_at(pr0), [REGIONS.index(r) for r in
                                                                                   ('forehead', 'brow', 'eyes', 'nose', 'cheeks', 'mouth', 'chin')])
    sym = None
    if facez.sum() > 2000:
        idx = np.nonzero(facez)[0]
        if len(idx) > 30000:
            idx = np.random.default_rng(0).choice(idx, 30000, replace=False)
        n_sym, d_sym, sym_rms = register.symmetry_plane(Xg[idx])
        ang = float(np.degrees(np.arccos(np.clip(abs(n_sym[0]), -1, 1))))
        sym = {'normal': r3(n_sym), 'offset_m': round(d_sym, 5), 'angle_deg': round(ang, 2), 'mirror_rms_mm': round(sym_rms * 1000, 2)}
        if 0.3 < ang < 8.0:
            axis = np.cross(n_sym * np.sign(n_sym[0]), [1.0, 0, 0])
            if np.linalg.norm(axis) > 1e-9:
                from fitcommon import rot_axis_angle
                Rc = rot_axis_angle(axis, np.radians(ang))
                c = np.array([0.0, model.lm['nose_tip'][1], model.C[2]])
                sim = Sim(sim.s, Rc @ sim.R, Rc @ (sim.t - c) + c)
        log(f"[fit] mirror plane: {ang:.2f} deg from the RL sagittal plane, mirror rms {sym_rms * 1000:.2f} mm")

    # ---------------------------------------------------------------- dense head-zone sample
    cloud, dens, link_r, occ_r = head_cloud(ref, cloud_g, sim, model, 80_000 if a.quick else 160_000, a.seed)
    log(f"[fit] head-zone resample: {dens} -> {len(cloud)} points ({T.mark('resample'):.1f}s)")

    # ---------------------------------------------------------------- segmentation <-> similarity (controls 0)
    def fit_sets(G, lab, info):
        head = (G['dist'] < 0.08) & ~G['past_rim']
        # confident skin only: points near hair/beard/clothing boundaries are left out of the fit
        skin = head & (lab == SKIN) & (info['skin_confidence'] > 0.75)
        return head, skin

    rng = np.random.default_rng(a.seed + 1)
    n_fit = 24_000 if a.quick else 45_000
    n_all = 30_000 if a.quick else 60_000

    def pick(mask, n):
        idx = np.nonzero(mask)[0]
        return idx if len(idx) <= n else rng.choice(idx, n, replace=False)

    seg_kw = dict(link_r=link_r, occ_r=occ_r)
    sim_c = sim
    for rnd in range(3):
        Xg = sim_c(cloud.X); Ng = sim_c.rot(cloud.N)
        lab, prob, G, seginfo = segment.classify(cloud, Xg, Ng, model, surf0, **seg_kw)
        log(f"[fit] segmentation {seginfo['counts']} seeds {seginfo['seeds']} hair pieces {seginfo['hair_components']} "
            f"occluded skin {seginfo['occluded_skin']} ({T.mark('segment'):.1f}s)")
        head, skin = fit_sets(G, lab, seginfo)
        fi = pick(skin, n_fit); ai = pick(head, n_all)
        S0 = solve.Settings(iters=8 if a.quick else 10, controls=False, scale_free=True, robust=(6.0, 3.0), gate=(20.0, 10.0))
        f0 = solve.Fitter(model, cloud.X[fi], cloud.N[fi], sim_c, region_w, S0, Xall=cloud.X[ai], Nall=cloud.N[ai], lab_all=lab[ai])
        log('[fit] similarity refinement, controls 0')
        f0.run(tag='sim ')
        ds = abs(np.log(f0.sim.s / sim_c.s)); dang = rot_angle_deg(f0.sim.R @ sim_c.R.T)
        dt = np.linalg.norm(f0.sim(cloud.X[:1]) - sim_c(cloud.X[:1])) if len(cloud.X) else 0.0
        sim_c = f0.sim
        if ds < 0.01 and dang < 1.0 and dt < 0.003:
            break
        log(f'[fit] pose moved (scale {ds * 100:.1f}%, {dang:.1f} deg): re-segmenting')
    sim0 = f0.sim
    sig0 = f0.residual_sigma()

    # ---------------------------------------------------------------- controls (+ similarity)
    user_lam = 'lambda_abs' in wcfg
    user_rot = 'rot_prior' in wcfg
    rot_prior = float(wcfg['rot_prior']) if user_rot else 0.0      # first pass: rotation free

    def settings(base=None, **kw):
        S = solve.Settings(**({**base.__dict__} if base is not None else {}))
        S.__dict__.update(kw)
        for k_, attr in (('lambda_rel', 'lam_rel'), ('lambda_abs', 'lam_abs'), ('scale_prior', 'lam_scale')):
            if k_ in wcfg:
                setattr(S, attr, float(wcfg[k_]))
        S.R0 = sim0.R.copy()
        if 'lam_rot' not in kw:
            S.lam_rot = rot_prior
        return S

    allow = np.ones(len(names), bool)
    if a.weak == 'off':
        allow[[names.index(c) for c in WEAK_CONTROLS]] = False
    lam1 = float(wcfg['lambda_abs']) if user_lam else 0.001      # first pass: moderate fixed prior
    S1 = settings(iters=10 if a.quick else 16, controls=True, lam_abs=lam1)
    f1 = solve.Fitter(model, cloud.X[fi], cloud.N[fi], sim0, region_w, S1, Xall=cloud.X[ai], Nall=cloud.N[ai], lab_all=lab[ai])
    f1.allow = allow.copy()
    log(f'[fit] control solve (lambda_abs {lam1:.2e} mm^2, rotation prior {rot_prior:g} mm^2/rad^2)')
    f1.run(tag='ctl ')
    # second pass: re-segment against the fitted head, re-solve from the current state
    Pv = model.morph(z=f1.z)
    Xg = f1.sim(cloud.X); Ng = f1.sim.rot(cloud.N)
    surf1 = model.surface(Pv)
    lab, prob, G, seginfo = segment.classify(cloud, Xg, Ng, model, surf1, final=True, **seg_kw)
    head, skin = fit_sets(G, lab, seginfo)
    if skin.sum() < 2000:
        warnings.append(f'only {int(skin.sum())} reference points classified as head skin')
    fi = pick(skin, n_fit); ai = pick(head, n_all)
    # controls whose support the reference covers with hair / beard: unobservable, held at the prior (0)
    coverage, cov_info = analysis.control_coverage(model, Pv, Xg[head], lab[head], f1.v, region_w, r=max(0.002, occ_r))
    hidden = [n for n in names if allow[names.index(n)] and
              (coverage[n]['support'] >= HIDDEN_COVER or coverage[n]['evidence'] >= HIDDEN_EVIDENCE)]
    region_w2 = region_w
    if hidden:
        allow[[names.index(n) for n in hidden]] = False
        hw = analysis.hidden_support_weight(model, [names.index(n) for n in hidden], np.nonzero(allow)[0])
        region_w2 = region_w * hw
        log(f"[fit] hidden under hair/beard (support >= {HIDDEN_COVER:.0%} or evidence >= {HIDDEN_EVIDENCE:.0%} covered): "
            f"{hidden}; held at 0, skin only they move down-weighted")
    sig1 = f1.residual_sigma()
    ell1, _ = f1.residual_correlation()
    lam2, n_eff = (float(wcfg['lambda_abs']), None) if user_lam else auto_lambda(f1.local_sigma2(), ell1)
    # rotation prior toward the controls-0 rotation R0, on the same footing as the control prior
    # (sd ROT_PRIOR_SD_DEG): negligible for in-model data, where the controls-0 rotation is the biased
    # one (control effects tilt it by up to ~0.7 deg) and the data decides; strong for an off-model bust,
    # where pitch would otherwise absorb brow/chin shape
    if user_rot:
        rot2 = rot_prior
    else:
        _ne = n_eff if n_eff else 1000.0
        rot2 = float(np.clip((sig1 or 1.0) ** 2 / _ne / np.radians(ROT_PRIOR_SD_DEG) ** 2, 0.0, 5000.0))

    def refine(z0, side0, allow_):
        S2 = settings(S1, iters=5 if a.quick else 8, robust=(3.5, 3.0), gate=(12.0, 10.0), lam_abs=lam2, lam_rot=rot2)
        f = solve.Fitter(model, cloud.X[fi], cloud.N[fi], f1.sim, region_w2, S2, Xall=cloud.X[ai], Nall=cloud.N[ai], lab_all=lab[ai])
        f.s0 = f1.sim.s                         # scale prior re-anchored on the fitted scale
        f.allow = allow_.copy()
        f.z = np.where(np.r_[allow_, allow_], z0, 0.0); f.side = np.where(allow_, side0, 0)
        f.run(tag='ref ')
        return f

    log(f"[fit] re-segmented {seginfo['counts']}; refining (lambda_abs median {np.median(lam2):.2e} mm^2 from residual sigma "
        f"{sig1 if sig1 is None else round(sig1, 3)} mm, correlation length {ell1 if ell1 is None else round(ell1, 1)} mm, N_eff {n_eff}; "
        f"rotation prior {rot2:.3g} mm^2/rad^2)")
    f2 = refine(f1.z, f1.side, allow)
    snr = f2.control_snr()
    weak_dropped = []
    if a.weak == 'auto':
        weak_dropped = [c for c in WEAK_CONTROLS if allow[names.index(c)] and snr[names.index(c)] < WEAK_SNR]
        if weak_dropped:
            allow2 = allow.copy()
            allow2[[names.index(c) for c in weak_dropped]] = False
            log(f'[fit] weak controls not supported by the data (effect/residual < {WEAK_SNR}): {weak_dropped}; re-solving without them')
            f2 = refine(f2.z, f2.side, allow2)
            allow = allow2
    sim = f2.sim
    z = f2.z
    v = model.v_of(z)
    v_out = np.clip(np.round(v, 2), -1, 1)
    obs = f2.observability()
    snr_final = f2.control_snr()
    ell2, _ = f2.residual_correlation()
    n_eff_sd = n_eff if n_eff else float(np.clip(FACE_AREA_MM2 / (np.pi * (ell2 if ell2 else 3.0) ** 2), 30.0, 2000.0))
    post_sd = f2.posterior_sd(f2.local_sigma2(), n_eff_sd)
    lim_idx = [j for j in range(len(names)) if allow[j] and abs(v[j]) >= 0.98]
    relaxed = {names[j]: round(x, 3) for j, x in f2.relaxed_values(lim_idx).items()}
    T.mark('solve')

    # ---------------------------------------------------------------- residuals (same points before / after), gaps
    Pv = model.morph(z=z); Nv = model.normals(Pv)
    Xg = sim(cloud.X); Ng = sim.rot(cloud.N)
    d_a, reg_a, ok_a, _ = analysis.point_residuals(model, Pv, Xg[skin], Ng[skin])
    X0 = sim0(cloud.X[skin]); N0g = sim0.rot(cloud.N[skin])
    d_b, reg_b, ok_b, _ = analysis.point_residuals(model, model.P, X0, N0g)
    okc = ok_a & ok_b
    frms_a, fp90_a, st_a = analysis.region_stats(d_a, reg_a, okc)
    frms_b, fp90_b, st_b = analysis.region_stats(d_b, reg_b, okc)
    log(f'[fit] face rms (robust) {frms_b:.3f} -> {frms_a:.3f} mm, p90 {fp90_b:.3f} -> {fp90_a:.3f} mm on {int(okc.sum())} points')
    # inlier fraction on reliable skin regions: RL skin samples with a close, normal-compatible reference skin point
    Mx, Mn = _morphed_points(model, z, 4000)
    from scipy.spatial import cKDTree
    kd_s = cKDTree(Xg[skin]); kd_a = cKDTree(Xg[head])
    dd, jj = kdq(kd_s, Mx, k=1)
    _, ja = kdq(kd_a, Mx, k=1)
    visible = lab[head][ja] == SKIN
    rr = ((Xg[skin][jj] - Mx) * Mn).sum(1)
    inl = visible & (np.abs(rr) < 0.002) & ((Ng[skin][jj] * Mn).sum(1) > 0.8) & (dd < 0.004)
    inlier_frac = float(inl.sum() / max(visible.sum(), 1))
    vis_frac = float(visible.mean())
    bpts = Xg[head & (lab == BEARD)]
    if len(bpts) >= 20:
        beard_cov, beard_th = analysis.beard_coverage(model, Pv, bpts, np.full(len(bpts), BEARD), within=0.013)
    else:
        beard_cov, beard_th = {k: 0.0 for k in ['all'] + list(model.beard_parts)}, 0.0
    beard_present = analysis.beard_present(beard_cov)
    gaps = analysis.control_gaps(st_a, v, names, beard_present, hidden=hidden)
    gap_regions = {g['region']: g for g in gaps}

    # ---------------------------------------------------------------- control reliability
    status = {}
    low_obs = []
    for j, n in enumerate(names):
        e_j, l_j = obs[j]
        if n in hidden:
            status[n] = 'hidden'
        elif not allow[j]:
            status[n] = 'not_measured'
        elif e_j < l_j:
            status[n] = 'prior'
        elif abs(v[j]) >= 0.98:
            status[n] = 'at_limit'
        elif n in WEAK_CONTROLS and (e_j < WEAK_OBS * l_j or not snr_final[j] >= WEAK_SNR_MEASURED):
            # an eye/lip control the data pins only loosely (data-only sd 0.5/sqrt(e/lambda) > 0.1, or its full
            # range < 2x the local residual): its error is dominated by how the reference renders lids / the
            # lip seam, not by noise
            status[n] = 'low_observability'
            low_obs.append(n)
        else:
            status[n] = 'measured'
    reliability = {n: {'status': status[n], 'observability': round(obs[j][0] / max(obs[j][1], 1e-12), 2),
                       'snr': round(float(snr_final[j]), 2) if np.isfinite(snr_final[j]) else None,
                       'sd': round(float(post_sd[j]), 3) if np.isfinite(post_sd[j]) else None,
                       'covered': round(coverage[n]['support'], 3), 'covered_evidence': round(coverage[n]['evidence'], 3),
                       'seen': round(coverage[n]['seen'], 3)}
                   for j, n in enumerate(names)}
    if weak_dropped:
        warnings.append('eye/lip controls not measured (the reference does not resolve them; base preset values used): '
                        + ', '.join(weak_dropped))
    if low_obs:
        warnings.append('eye/lip controls only loosely determined by the data (status low_observability; kept in controls, '
                        'left out of the preset): ' + ', '.join(low_obs))

    # ---------------------------------------------------------------- colours
    gsel = skin & (np.abs(G['d']) < 0.004)
    gs = segment.Gauss(segment.feats(cloud.C[gsel])) if gsel.sum() > 30 else None
    cols = analysis.colours(model, Pv, Xg, cloud.C, lab, G, gs, Ng=Ng, hair_gauss=seginfo.get('hair_gauss'))
    if cols['_clipped_skin_fraction'] > 0.5:
        warnings.append(f"{cols['_clipped_skin_fraction']:.0%} of the skin texels are clipped (blown-out baked light): the "
                        "albedo cannot be recovered; the skin colour is the plain texel median (too bright) - set it by hand")
    elif cols['_clipped_skin_fraction'] > 0.2:
        warnings.append(f"{cols['_clipped_skin_fraction']:.0%} of the skin texels are clipped (blown-out baked light): "
                        "colours come from the unclipped part")
    if cols['skin_srgb'] is not None:
        sl = srgb_to_lab(np.array(cols['skin_srgb']))
        if sl[0] > 93 or np.hypot(sl[1], sl[2]) < 6:
            warnings.append(f"skin colour {cols['skin_srgb']} is near white / neutral: check the texture's exposure")
    T.mark('analysis')

    # ---------------------------------------------------------------- hair envelope
    hair_pts = Xg[lab == HAIR]
    hair_present = len(hair_pts) >= 300
    hair = {'present': False, 'coverage': 0.0, 'max_thickness_mm': 0.0, 'lowest_y': None, 'nearest_style': None}
    env = None
    style_scores = {}
    rim_lo = float(model.h.P[model.h.rim, 1].min())
    if hair_present:
        srad = envelope.SkinRadius(Pv, model.h.T_noear, model.C)
        rho_s = envelope.skin_radius(Pv, model.h.T_noear, model.C)
        skin_n = envelope.skin_normals_at(Pv, model.h.T_noear, model.weld, model.C, rho_s)
        other_pts = Xg[head & (lab != HAIR)]
        E = envelope.envelope(hair_pts, other_pts, model.C, rho_s, srad, skin_N=skin_n)
        th = E['thickness_m']
        bad = envelope.implausible_bins(th)
        if bad.any():
            warnings.append(f'{int(bad.sum())} envelope bins jump far above their neighbours (isolated mislabelled geometry?); '
                            'they are left NaN')
            for k_ in ('thickness_m', 'rho_outer_m', 'height_normal_m'):
                E[k_][bad] = np.nan
            E['state'][bad] = envelope.STATE['none']
            E['height_normal_src'][bad] = envelope.HN_SRC['none']
        dr = envelope.drape(hair_pts, model.C)
        sm = envelope.scalp_mask(model.h)
        cov = envelope.coverage(th, sm)
        low = envelope.lowest_y(dr)
        if low is None:
            low = float(np.percentile(hair_pts[:, 1], 1))
        if cov < 0.08 and len(hair_pts) < 3000:
            hair_present = False
            warnings.append(f'hair-coloured points found ({len(hair_pts)}) but they cover only {cov:.2f} of the scalp: reported as no hair')
        else:
            sub = hair_pts if len(hair_pts) <= 20000 else hair_pts[np.random.default_rng(3).choice(len(hair_pts), 20000, replace=False)]
            env = {'lon_deg': envelope.LON, 'lat_deg': envelope.LAT, **E, **dr, 'hair_points': sub,
                   'C': model.C.copy()}
            styles = envelope.style_envelopes(lambda s: rlmodel.load(s).h, a.sex)
            me = {'thickness': th, 'lowest_y': low, 'rim_lo': rim_lo}
            best_style, style_scores, swarn = envelope.nearest_style(me, styles, rim_lo)
            if swarn:
                warnings.append(swarn)
            ranked = sorted(style_scores, key=lambda n_: style_scores[n_]['score'])
            fin = np.isfinite(th)
            hair = {'present': True, 'coverage': round(cov, 3),
                    'max_thickness_mm': round(float(np.nanpercentile(th, 99) * 1000) if fin.any() else 0.0, 1),
                    'lowest_y': round(low, 4), 'nearest_style': best_style,
                    'style_score': style_scores[best_style]['score'] if best_style else None,
                    'style_runner_up': next((n_ for n_ in ranked if n_ != best_style), None)}
            if fin.any() and np.nanmax(th) > 0.12:
                warnings.append(f'hair envelope reaches {np.nanmax(th) * 1000:.0f} mm off the skin: check the segmentation preview '
                                '(clothing or a hat taken as hair?)')
            if low < rim_lo - 0.25:
                warnings.append(f'hair reaches {(rim_lo - low) * 1000:.0f} mm below the neck rim: very long hair, or clothing '
                                'taken as hair - check the previews')
    T.mark('envelope')

    # ---------------------------------------------------------------- beard
    beard_styles = analysis.beard_style_coverages(rlmodel.load) if beard_present else {}
    beard_style, beard_scores = analysis.nearest_beard(beard_cov, beard_styles, beard_th) if beard_present else (None, {})
    beard = {'present': bool(beard_present), 'coverage': round(beard_cov['all'], 3)}
    if beard_present:
        beard['style'] = beard_style
        beard['thickness_mm'] = round(beard_th, 1)
    if seginfo.get('stubble') and not beard_present:
        beard['stubble'] = True
    if hidden:
        warnings.append(f"controls hidden under hair/beard (support >= {HIDDEN_COVER:.0%} or evidence >= {HIDDEN_EVIDENCE:.0%} "
                        "covered; held at 0, left out of the preset): "
                        + ', '.join(f"{n} {coverage[n]['support']:.0%}/{coverage[n]['evidence']:.0%}" for n in hidden))
    if beard_present:
        warnings.append(f"beard covers {beard_cov['all']:.0%} of the jaw/chin/upper-lip region")
    elif beard_cov['all'] > 0.3:
        warnings.append(f"beard-like geometry covers {beard_cov['all']:.0%} of the beard region but not the chin front or upper "
                        "lip (shadow under the jaw / a thicker neck?): reported as no beard")

    # ---------------------------------------------------------------- warnings, status
    at_bound = [n for n, x in zip(names, v) if abs(x) >= 0.98]
    beyond = [n for n in at_bound if abs(relaxed.get(n, 1.0)) > BEYOND_LIMIT]
    if at_bound:
        warnings.append('controls at their limit: ' + ', '.join(f"{n} (unbounded {relaxed[n]:+.2f})" if n in relaxed else n
                                                               for n in at_bound)
                        + (f"; beyond the RL range (the data would take them past +-{BEYOND_LIMIT}): {', '.join(beyond)}" if beyond else
                           '; within the RL range (the data does not push them past it)'))
    if sym and sym['angle_deg'] > 4:
        warnings.append(f"face mirror plane differs {sym['angle_deg']:.1f} deg from the fitted sagittal plane (asymmetric or tilted face)")
    if inlier_frac < 0.5:
        warnings.append(f'registration inlier fraction {inlier_frac:.2f} is low')
    if frms_a > 2.5:
        warnings.append(f'face residual after the fit is large ({frms_a:.2f} mm rms)')
    up_name, yaw = up_of_rotation(sim.R)
    Rq = register.yaw_rotation(round(yaw / 90.0) * 90.0 % 360) @ UP[up_name]
    tilt = rot_angle_deg(sim.R @ Rq.T)
    reasons_fail = []
    if inlier_frac < 0.35:
        reasons_fail.append(f'inlier fraction {inlier_frac:.2f} < 0.35')
    if not np.isfinite(frms_a) or frms_a > 3.0:
        reasons_fail.append(f'face residual {frms_a:.2f} mm > 3 mm')
    if skin.sum() < 1500:
        reasons_fail.append(f'only {int(skin.sum())} skin points')
    reasons_review = []
    if beyond:
        # the reference goes beyond the RL range there (a control sitting exactly at +-1 is not a reason)
        reasons_review.append(f"{len(beyond)} control(s) beyond the RL range ({', '.join(beyond)})")
    if inlier_frac < 0.5:
        reasons_review.append('low inlier fraction')
    for w_ in warnings:
        # informational warnings (no label, partly clipped texels with colours taken from the unclipped part,
        # hidden / loosely determined controls, a beard) do not need a human look by themselves
        if any(k_ in w_ for k_ in ('envelope reaches', 'below the neck rim', 'cannot be recovered', 'near white',
                                   'style match is poor', 'runner-up start', 'mirror plane')):
            reasons_review.append(w_.split(':')[0])
    if hair_present and env is not None and int(bad.sum()) > 2:
        reasons_review.append(f'{int(bad.sum())} envelope bins rejected as spikes')
    q_status = 'fail' if reasons_fail else ('review' if reasons_review else 'ok')

    # ---------------------------------------------------------------- preset
    base = dict(presets().get(BASE_PRESET[a.sex], {}))
    label = a.label or os.path.splitext(os.path.basename(a.reference))[0]
    if not a.label:
        warnings.append(f"no --label given: the preset is labelled '{label}' after the file; pass --label before merging")
    pctrl = {}
    clamped = []
    for j, n in enumerate(names):
        x = float(v_out[j])
        if status[n] not in ('measured', 'at_limit') or abs(x) < 0.05:     # runtime precision ~0.07
            continue
        if status[n] == 'at_limit':
            regs = [r for r, cs in REGION_CONTROLS.items() if n in cs]
            if any(r in gap_regions and gap_regions[r]['rms_mm'] > 1.5 for r in regs):
                x = float(np.sign(x) * 0.5); clamped.append(n)
        pctrl[n] = x
    if clamped:
        warnings.append('controls at their limit next to a remaining shape gap were clamped to +-0.5 in the preset '
                        '(possible registration trade-off): ' + ', '.join(clamped))
    brow = cols['brow_srgb']
    brow_src = 'measured'
    if brow is None and cols['hair_srgb'] is not None:
        brow = [round(x * 0.62, 3) for x in cols['hair_srgb']]; brow_src = '0.62 x hair'
    fallbacks = []
    def pick_col(key, val):
        if val is None:
            fallbacks.append(key)
            return base.get(key)
        return val
    preset = {'sex': a.sex, 'label': label, 'controls': pctrl,
              'skin': pick_col('skin', cols['skin_srgb']),
              'eyes': pick_col('eyes', cols['eye_srgb']),
              'hair_color': pick_col('hair_color', cols['hair_srgb']),
              'brow_color': pick_col('brow_color', brow),
              'lip_tint': pick_col('lip_tint', cols['lip_srgb'])}
    for k, val in NEUTRAL_STYLE.items():
        preset[k] = val
        fallbacks.append(f'{k} (neutral default)')
    preset['hair'] = hair['nearest_style'] if hair['present'] and hair['nearest_style'] else 'none'
    preset['beard'] = beard_style if beard_present and beard_style else ('stubble' if seginfo.get('stubble') else 'none')
    for st_, why in (('hidden', 'hidden under hair/beard'), ('not_measured', 'not resolved by the reference'),
                     ('prior', 'decided by the prior'), ('low_observability', 'only loosely determined')):
        lst = [n for n in names if status[n] == st_]
        if lst:
            fallbacks.append(f"controls {', '.join(lst)} ({why}, status {st_}: base value 0)")
    preset_key = re.sub(r'[^a-z0-9_]+', '_', label.lower()).strip('_') or 'fitted'

    fit = {
        'sex': a.sex, 'reference': os.path.abspath(a.reference), 'reference_fingerprint': fp,
        'controls': {n: float(x) for n, x in zip(names, v_out)},
        'control_reliability': reliability,
        'transform': sim.to_json(),
        'orientation': {'up': up_name, 'yaw_deg': round(yaw, 2), 'tilt_deg': round(tilt, 2),
                        'search': 'landmarks' if init is not None else f"{len(allc)} starts", 'margin': round(best['margin'], 3)},
        'residual_mm': analysis.residual_block(frms_a, fp90_a, st_a),
        'residual_mm_before': analysis.residual_block(frms_b, fp90_b, st_b),
        'control_gaps': gaps,
        'colours': {k: cols[k] for k in ('skin_srgb', 'hair_srgb', 'lip_srgb', 'brow_srgb', 'eye_srgb')},
        'hair': hair,
        'beard': beard,
        'quality': {'registration_inlier_fraction': round(inlier_frac, 3), 'status': q_status,
                    'status_reasons': reasons_fail or reasons_review, 'warnings': warnings},
        'preset': preset,
        'preset_key': preset_key,
        'preset_fallbacks': fallbacks,
        'details': {
            'reference_mesh': rs, 'samples': len(cloud), 'sampling': dens, 'skin_points': int(skin.sum()),
            'segmentation': seginfo['counts'], 'colour_models_lab': seginfo['colour_models'],
            'hair_components': seginfo.get('hair_components'), 'occluded_skin_points': seginfo.get('occluded_skin'),
            'visible_skin_fraction': round(vis_frac, 3), 'symmetry': sym, 'scale_before_controls': sim0.s,
            'rotation_controls0_vs_final_deg': round(rot_angle_deg(sim.R @ sim0.R.T), 3),
            'transform_before_controls': sim0.to_json(),
            'region_weights': wmap, 'controls_unrounded': {n: round(float(x), 4) for n, x in zip(names, v)},
            'lambda_abs_mm2': {'controls': lam1, 'refine': {n: [round(float(np.broadcast_to(lam2, (2 * len(names),))[j]), 6),
                                                                round(float(np.broadcast_to(lam2, (2 * len(names),))[len(names) + j]), 6)]
                                                            for j, n in enumerate(names)}}, 'n_eff': n_eff,
            'residual_sigma_mm': {'controls0': sig0, 'controls': sig1,
                                                                                          'final': f2.residual_sigma()},
            'rotation_prior': {'controls': rot_prior, 'refine': rot2}, 'weak_mode': a.weak, 'weak_dropped': weak_dropped,
            'hidden_controls': hidden, 'coverage': cov_info, 'low_observability': low_obs,
            'limit_test': {'relaxed_values': relaxed, 'beyond': beyond, 'threshold': BEYOND_LIMIT},
            'posterior_sd_n_eff': round(n_eff_sd, 1), 'registration': reg_info,
            'residual_correlation': {'f1': f1.residual_correlation(), 'final': f2.residual_correlation()},
            'residual_mean_mm_after': {r: round(s['mean'], 3) for r, s in st_a.items()},
            'residual_points': int(okc.sum()), 'colour_info': {k: cols[k] for k in cols if k.startswith('_')},
            'baked_light': cols.get('_shading'), 'hair_style_scores': style_scores, 'beard_parts': {k: round(x, 3) for k, x in beard_cov.items()},
            'beard_thickness_mm': round(beard_th, 1) if beard_present else None, 'beard_style_scores': beard_scores,
            'iterations': {'similarity': f0.history, 'controls': f1.history, 'refine': f2.history},
        },
    }
    if a.gap_targets:
        try:
            import gaptargets
            fit['gap_targets'] = gaptargets.rank(model, f2)
            T.mark('gap_targets')
        except Exception as ex:
            fit['gap_targets'] = {'error': repr(ex)}

    # ---------------------------------------------------------------- outputs
    if env is not None and not a.no_envelope:
        np.savez(os.path.join(a.out, 'envelope.npz'), **env)
    vres, vok = analysis.vertex_residuals(model, Pv, Nv, Xg[head], Ng[head], lab[head])
    fc = sim(ref.V[ref.F].mean(1))
    fmask = (np.linalg.norm(fc - np.array([0, model.C[1] - 0.03, model.C[2]]), axis=1) < 0.32)
    seg_rgb = _face_labels(ref, cloud, lab)
    fitviz.write_previews(a.out, model, ref, sim, Pv, Nv, vres, vok, preset['skin'], fmask, seg_face_rgb=seg_rgb,
                          hair_env=env, hair_rgb=preset['hair_color'])
    T.mark('previews')
    fit['details']['timing_s'] = {k: round(t, 2) for k, t in T.marks}
    fit['details']['runtime_s'] = round(T.total(), 2)
    with open(os.path.join(a.out, 'fit.json'), 'w', encoding='utf-8') as fh:
        json.dump(fit, fh, indent=1, default=_json_default)
    write_report(a.out, fit, best)
    log(f'[fit] done in {T.total():.1f}s -> {a.out}  (quality {q_status})')
    return fit


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _morphed_points(model, z, n, seed=9):
    regs = ['forehead', 'brow', 'nose', 'cheeks', 'jaw', 'chin', 'ears', 'neck']
    rng = np.random.default_rng(seed)
    T = model.Tv
    ok = np.isin(model.region, [REGIONS.index(r) for r in regs])[T].all(1)
    a = model.tri_area * ok
    cdf = np.cumsum(a)
    tri = np.minimum(np.searchsorted(cdf, rng.random(n) * cdf[-1]), len(T) - 1)
    r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
    b = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
    Pv = model.morph(z=z); Nv = model.normals(Pv)
    tv = T[tri]
    return (Pv[tv] * b[:, :, None]).sum(1), unit((Nv[tv] * b[:, :, None]).sum(1))


def _face_labels(ref, cloud, lab):
    """Per reference face segmentation colour (majority of its sample points; unsampled faces take
    the label of the nearest sample)."""
    from scipy.spatial import cKDTree
    cols = fitviz.SEG_COL
    nF = len(ref.F)
    votes = np.zeros((nF, 4))
    np.add.at(votes, (cloud.face, lab), 1)
    has = votes.sum(1) > 0
    fl = np.argmax(votes, 1)
    if (~has).any():
        tc = ref.V[ref.F[~has]].mean(1)
        _, j = kdq(cKDTree(cloud.X), tc, k=1)
        fl[~has] = lab[j]
    return cols[fl]


def write_report(out, fit, best):
    o = fit['orientation']; t = fit['transform']; q = fit['quality']
    L = []
    L.append(f"# RL head fit: {fit['preset']['label']}\n")
    L.append(f"Reference: `{fit['reference']}` (sha256 {fit['reference_fingerprint']['sha256'][:12]}..., "
             f"{fit['reference_fingerprint']['bytes']} bytes)  \nSex: {fit['sex']}  \nRuntime: {fit['details']['runtime_s']} s  \n"
             f"Quality: **{q['status']}**" + (f" ({'; '.join(q['status_reasons'])})" if q['status_reasons'] else '') + '\n')
    L.append('## Registration\n')
    L.append(f"- orientation: up = **{o['up']}**, yaw = **{o['yaw_deg']:.1f} deg**, residual tilt {o['tilt_deg']:.1f} deg "
             f"({o['search']}, best-vs-runner-up margin {o['margin']})")
    L.append(f"- scale: **{t['scale']:.6g}** game metres per reference unit (before controls: {fit['details']['scale_before_controls']:.6g}); "
             f"rotation moved {fit['details']['rotation_controls0_vs_final_deg']} deg during the control solve")
    L.append(f"- registration inlier fraction: **{q['registration_inlier_fraction']:.3f}** "
             f"(visible skin fraction {fit['details']['visible_skin_fraction']:.2f}; {fit['details']['skin_points']} confident skin points)")
    sym = fit['details']['symmetry']
    if sym:
        L.append(f"- face mirror plane: {sym['angle_deg']} deg from the RL sagittal plane, mirror rms {sym['mirror_rms_mm']} mm")
    L.append('\n## Controls\n')
    L.append('Status: measured = the data decides; at_limit = |v| >= 0.98; hidden = >= 50 % of its support or >= 65 % of its '
             'evidence covered by hair/beard (held at 0); prior = the prior decides (too small an effect for the data); '
             'low_observability = eye/lip control the data pins only loosely (kept here, not in the preset); not_measured = '
             'eye/lip control the reference does not resolve (held at 0). Only measured / at_limit controls enter the preset. '
             'snr = control effect / local residual; sd = marginal posterior sd; cov = share of the support covered by '
             'hair/beard.\n')
    L.append('| control | value | status | snr | sd | cov |  | control | value | status | snr | sd | cov |')
    L.append('|---|---:|---|---:|---:|---:|---|---|---:|---|---:|---:|---:|')
    items = list(fit['controls'].items())
    rel = fit['control_reliability']
    half = (len(items) + 1) // 2

    def cell(it):
        n, x = it
        r = rel[n]
        return f"{n} | {x:+.2f} | {r['status']} | {r['snr']} | {r.get('sd')} | {r.get('covered', 0):.2f}"
    for i in range(half):
        a = items[i]; b = items[i + half] if i + half < len(items) else None
        L.append(f"| {cell(a)} |  | {cell(b) if b else ' | | | | | '} |")
    rb = fit['residual_mm_before']; ra = fit['residual_mm']
    L.append('\n## Residuals (mm, reference skin to fitted RL skin; robust: isolated outliers trimmed, same points before/after)\n')
    L.append(f"face rms {rb['face_rms']:.2f} -> **{ra['face_rms']:.2f}**, face p90 {rb['face_p90']:.2f} -> **{ra['face_p90']:.2f}** "
             f"({fit['details']['residual_points']} points)\n")
    L.append('| region | before | after | mean after | outliers |')
    L.append('|---|---:|---:|---:|---:|')
    for r in REGIONS:
        if r in ra['by_region'] or r in rb['by_region']:
            L.append(f"| {r} | {rb['by_region'].get(r, float('nan')):.2f} | {ra['by_region'].get(r, float('nan')):.2f} | "
                     f"{fit['details']['residual_mean_mm_after'].get(r, float('nan')):+.2f} | {ra.get('outliers_by_region', {}).get(r, 0)} |")
    L.append('\n## Control gaps\n')
    if fit['control_gaps']:
        for g in fit['control_gaps']:
            L.append(f"- **{g['region']}**: {g['rms_mm']} mm rms, reference {g['direction']} on average ({g['mean_mm']:+.2f} mm); {g['note']}")
    else:
        L.append('- none above threshold (robust 1.4 mm rms / 0.9 mm mean)')
    if 'gap_targets' in fit and isinstance(fit['gap_targets'], list):
        L.append('\nCandidate MPFB targets that would reduce the remaining residual:\n')
        for g in fit['gap_targets'][:10]:
            L.append(f"- `{g['target']}` weight {g['weight']:.2f}: -{g['reduction_mm2']:.3f} mm^2 "
                     f"({g['fraction_of_residual']:.0%} of the remaining energy; {g['region']})")
    c = fit['colours']
    L.append('\n## Colours (sRGB 0-1 medians)\n')
    for k, vv in c.items():
        L.append(f"- {k}: {vv if vv is not None else 'not measured (base preset used)'}")
    h = fit['hair']; b = fit['beard']
    L.append('\n## Hair and beard\n')
    if h['present']:
        sc = fit['details']['hair_style_scores']
        top = sorted(sc, key=lambda n_: sc[n_]['score'])[:4]
        L.append(f"- hair: coverage {h['coverage']:.2f} of the scalp, max thickness {h['max_thickness_mm']} mm, lowest point y = {h['lowest_y']} m, "
                 f"nearest style **{h['nearest_style']}** (score {h['style_score']}; closest: "
                 + ', '.join(f"{n_} {sc[n_]['score']}" for n_ in top) + ')')
    else:
        L.append('- hair: none detected')
    if b['present']:
        L.append(f"- beard: coverage {b['coverage']:.2f} (parts {fit['details']['beard_parts']}), thickness {b.get('thickness_mm')} mm, "
                 f"nearest style **{fit['preset']['beard']}**")
    else:
        L.append(f"- beard: none (coverage {b['coverage']:.2f})" + (' - painted stubble' if b.get('stubble') else ''))
    L.append(f"\nSegmentation counts: {fit['details']['segmentation']}; hair pieces {fit['details']['hair_components']}\n")
    L.append('## Warnings\n')
    L.extend([f'- {w}' for w in q['warnings']] or ['- none'])
    L.append('\n## Preset entry\n')
    L.append(f"Suggested key: `{fit['preset_key']}`. Not measured (fallbacks): {', '.join(fit['preset_fallbacks']) or 'none'}.\n")
    L.append('```json\n' + json.dumps(fit['preset'], indent=1) + '\n```')
    L.append('\nPreviews: front.png, profile.png, three_quarter.png (reference | fitted RL head with the hair envelope | residual), '
             'segmentation.png\n')
    open(os.path.join(out, 'report.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def main(argv=None):
    a = parse(argv)
    try:
        fit = run(a)
    except Exception:
        traceback.print_exc()
        return 1
    if a.strict and fit['quality']['status'] == 'fail':
        print(f"[fit] --strict: quality status 'fail' ({'; '.join(fit['quality']['status_reasons'])})", file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
