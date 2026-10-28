"""Developer self-test for the fitter: synthetic Meshy-like references built from
the RL head itself with KNOWN controls, then fitted and scored.

    python selftest.py build --case female_long --out <dir>
    python selftest.py run   [--cases female_long,male_beard] [--quick] [--rebuild] [--extra "<fitter args>"]
                             [--out-root <dir>]
    python selftest.py eval  --truth <dir>/truth.json --fit <fitdir>/fit.json

Cases: female_long, male_beard, female_bald_nm (no hair/beard, smooth off-model displacement),
male_short_dense, male_bald_clean (bald and clean-shaven, in-model: no hair or beard point at all).
`run` prints a PASS/FAIL summary (hair/beard presence, scale < 2 %, rotation < 3 deg, status not fail,
reliable-control RMSE <= 0.12 on in-model cases) and exits 1 if any case fails or crashes.

A reference is: the RL skin morphed by random controls, eyeballs fused into the
eye sockets, a fused hair shell over the scalp (the skin under it removed),
optionally a long back drape and/or a beard shell over the jaw/chin/upper lip,
a crude neck and shoulders in clothing, colours with baked lighting (texture
atlas or COLOR_0), a random similarity transform, up-axis convention, yaw
quadrant and tilt (partly in the node matrix), optionally a smooth
non-model displacement and noise. truth.json records the controls, the
reference->game similarity, the albedo colours and the ground-truth hair
envelope (same definition as the fitter's).
(The official acceptance harness is a separate tool in synth/.)
"""
import os, sys, io, json, time, argparse, subprocess
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fitcommon import (Sim, rot_x, rot_y, rot_axis_angle, unit, srgb_to_linear, linear_to_srgb, srgb_to_lab,
                    control_names, DEV_DIR, rot_angle_deg, r3)
import rlmodel, gltfio, envelope
from rlmodel import REGIONS
from headref import lonlat_dir, dir_lonlat, vertex_normals
from register import UP

CASES = {
    'female_long': dict(sex='female', seed=11, hair='long', beard=False, up='z', yaw=90, tilt=6.0,
                        scale=0.42, texture=True, nonmodel_mm=0.0, noise_mm=0.15, ctrl_amp=0.8),
    'male_beard': dict(sex='male', seed=23, hair='short', beard=True, up='y', yaw=180, tilt=4.0,
                       scale=3.7, texture=False, nonmodel_mm=0.0, noise_mm=0.15, ctrl_amp=0.8),
    'female_bald_nm': dict(sex='female', seed=5, hair='none', beard=False, up='y', yaw=0, tilt=3.0,
                           scale=1.0, texture=True, nonmodel_mm=1.2, noise_mm=0.2, ctrl_amp=0.7),
    'male_short_dense': dict(sex='male', seed=31, hair='short', beard=False, up='-z', yaw=270, tilt=5.0,
                             scale=11.0, texture=True, nonmodel_mm=0.6, noise_mm=0.1, ctrl_amp=0.7, subdiv=2, grid_step=0.75),
    # bald and clean-shaven: no hair and no beard anywhere (the segmentation finds no hair point at all; this
    # crashed the fitter with KeyError 'in_seeded' before 2026-10-27 v3); in-model, vertex colours
    'male_bald_clean': dict(sex='male', seed=41, hair='none', beard=False, up='y', yaw=0, tilt=2.0,
                            scale=1.0, texture=False, nonmodel_mm=0.0, noise_mm=0.1, ctrl_amp=0.6),
}

SKIN = {'female': [0.88, 0.68, 0.56], 'male': [0.72, 0.52, 0.38]}
HAIRC = {'female': [0.55, 0.22, 0.08], 'male': [0.20, 0.13, 0.08]}
LIPC = {'female': [0.78, 0.38, 0.36], 'male': [0.62, 0.36, 0.30]}
BROWC = {'female': [0.36, 0.18, 0.10], 'male': [0.14, 0.09, 0.06]}
EYEC = {'female': [0.25, 0.45, 0.30], 'male': [0.30, 0.20, 0.10]}
CLOTH = [0.20, 0.36, 0.30]


# ------------------------------------------------------------------ geometry helpers
def sphere(c, r, nu=40, nv=20):
    th = np.linspace(0, np.pi, nv + 1); ph = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing='ij')
    V = np.stack([np.sin(TH) * np.sin(PH), np.cos(TH), np.sin(TH) * np.cos(PH)], -1).reshape(-1, 3) * r + c
    F = []
    for i in range(nv):
        for j in range(nu):
            a = i * nu + j; b = i * nu + (j + 1) % nu; c2 = (i + 1) * nu + j; d = (i + 1) * nu + (j + 1) % nu
            F += [[a, c2, b], [b, c2, d]]
    return V, np.array(F)


def grid_faces(mask):
    """Quads of a (rows, cols) vertex grid (cols wrap) where all four corners are in mask."""
    R, Cc = mask.shape
    F = []
    for i in range(R - 1):
        for j in range(Cc):
            a = i * Cc + j; b = i * Cc + (j + 1) % Cc; c = (i + 1) * Cc + j; d = (i + 1) * Cc + (j + 1) % Cc
            if mask[i, j] and mask[i, (j + 1) % Cc] and mask[i + 1, j] and mask[i + 1, (j + 1) % Cc]:
                F += [[a, b, c], [b, d, c]]
    return np.array(F, np.int64).reshape(-1, 3)


def subdivide(V, F, attrs):
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    u, inv = np.unique(e, axis=0, return_inverse=True)
    inv = inv.ravel()
    nv = len(V)
    mid = nv + np.arange(len(u))
    V2 = np.concatenate([V, 0.5 * (V[u[:, 0]] + V[u[:, 1]])])
    A2 = {k: np.concatenate([a, 0.5 * (a[u[:, 0]] + a[u[:, 1]])]) for k, a in attrs.items()}
    m = len(F)
    m01 = mid[inv[:m]]; m12 = mid[inv[m:2 * m]]; m20 = mid[inv[2 * m:]]
    F2 = np.concatenate([np.stack([F[:, 0], m01, m20], 1), np.stack([m01, F[:, 1], m12], 1),
                         np.stack([m20, m12, F[:, 2]], 1), np.stack([m01, m12, m20], 1)])
    return V2, F2, A2


def smooth_field(n_pts, X, rng, amp, scale=0.03, k=6):
    """Smooth random displacement magnitudes from a few Gaussian bumps."""
    C = X[rng.choice(len(X), k * 4, replace=False)]
    a = rng.normal(0, 1, len(C))
    f = np.zeros(len(X))
    for c, w in zip(C, a):
        f += w * np.exp(-np.sum((X - c) ** 2, 1) / (2 * scale ** 2))
    f *= amp / max(np.sqrt(np.mean(f ** 2)), 1e-9)
    return f


# ------------------------------------------------------------------ build
def hairline(model, margin_deg):
    """lat_min(lon) of the MPFB scalp group (base head), smoothed, per 1 degree of lon."""
    h = model.h
    lo, la = dir_lonlat(h.P[h.vgroups['scalp']] - h.C)
    lons = np.arange(-180, 180, 1.0)
    out = np.full(len(lons), np.nan)
    for i, l in enumerate(lons):
        dl = (lo - l + 180) % 360 - 180
        m = np.abs(dl) < 12
        if m.any():
            out[i] = la[m].min()
    out = np.where(np.isfinite(out), out, np.nanmax(out))
    k = np.ones(15) / 15
    out = np.convolve(np.r_[out[-7:], out, out[:7]], k, mode='valid')
    return lons, out - margin_deg


def build(case, out_dir):
    cfg = CASES[case]
    sex = cfg['sex']
    rng = np.random.default_rng(cfg['seed'])
    m = rlmodel.RLModel(sex)
    names = control_names()
    v = np.round(rng.uniform(-cfg['ctrl_amp'], cfg['ctrl_amp'], len(names)), 2)
    v[rng.random(len(names)) < 0.25] = 0.0      # some controls exactly 0
    controls = dict(zip(names, v.tolist()))
    Pfull = m.morph(v)
    h = m.h
    ns, nts = m.n_skin, m.n_tri_skin
    Pv = Pfull[:ns]                                   # skin
    PE = Pfull[ns:]; TE = m.T[nts:] - ns              # RL eyeballs (rl_eye + rl_cornea), morphed
    Tsk = m.T[:nts]; wsk = m.weld[:ns]
    E_sk = np.concatenate([Tsk[:, [0, 1]], Tsk[:, [1, 2]], Tsk[:, [2, 0]]]); E_sk = np.concatenate([E_sk, E_sk[:, ::-1]])
    Nv = vertex_normals(Pv, Tsk, wsk)
    if cfg['nonmodel_mm'] > 0:
        f = smooth_field(len(Pv), Pv, rng, cfg['nonmodel_mm'] / 1000.0)
        Pv = Pv + Nv * f[:, None]
        Nv = vertex_normals(Pv, Tsk, wsk)
    parts = []          # (name, V, F, vcol sRGB)
    skin_col = np.tile(SKIN[sex], (len(Pv), 1)) * (1 + rng.normal(0, 0.015, (len(Pv), 1)))
    skin_col[h.vgroups['lips']] = LIPC[sex]
    brow = m.region_mask('brow')[:ns] & (np.abs(Pv[:, 0]) > 0.008) & (np.abs(Pv[:, 0]) < 0.052)
    eyey = m.eye_centres[0][1]
    brow &= (Pv[:, 1] > eyey + 0.011) & (Pv[:, 1] < eyey + 0.021)
    skin_col[brow] = BROWC[sex]
    T_keep = m.tri_valid[:nts].copy()    # Meshy-like: no mouth bag / eye-socket lining
    hair_X_truth = []
    # ---- hair shell
    if cfg['hair'] != 'none':
        lons, hl = hairline(m, 4.0 if cfg['hair'] == 'long' else -2.0)
        gs = cfg.get('grid_step', 2.0)
        glon = np.arange(-180, 180, gs)
        glat = np.arange(-70, 90.1, gs)
        LO, LA = np.meshgrid(glon, glat)
        hl_at = np.interp(LO.ravel(), lons, hl, period=360).reshape(LO.shape)
        rs = envelope.skin_radius(Pv, h.T_noear, h.C, glon, glat)
        if cfg['hair'] == 'long':
            t = 0.010 + 0.007 * (np.abs(LO) / 180.0) * (1 - np.sin(np.radians(np.clip(LA, 0, 90)))) + 0.004 * np.cos(np.radians(LA))
        else:
            t = 0.006 + 0.002 * (np.abs(LO) > 90) + 0.002 * np.sin(np.radians(np.clip(LA, 0, 90)))
        inside = (LA >= hl_at) & np.isfinite(rs)
        rho = np.where(np.isfinite(rs), rs + t, np.nan)
        Vh = h.C + lonlat_dir(LO.ravel(), LA.ravel()) * np.nan_to_num(rho.ravel(), nan=0.1)[:, None]
        Fh = grid_faces(inside)
        # pole cap: connect the top row (lat 90 is a point; grid already includes lat 90)
        hcol = np.tile(HAIRC[sex], (len(Vh), 1)) * (1 + 0.12 * np.sin(np.radians(LO.ravel()) * 23)[:, None])
        parts.append(('hair', Vh, Fh, hcol))
        hair_X_truth.append(Vh[np.unique(Fh)])
        if cfg['hair'] == 'long':
            # back drape: vertical curtain from the lowest hair row at the back down past the neck
            back = np.abs(glon) >= 110
            ys = []
            first = np.argmax(inside, axis=0)            # first (lowest) inside row per lon
            y_low = h.P[h.rim, 1].min() - 0.09
            rows = 14
            Vd = []
            for j, lo in enumerate(glon):
                i0 = first[j]
                p0 = Vh[i0 * len(glon) + j]
                rh = np.hypot(p0[0] - h.C[0], p0[2] - h.C[2]) + 0.004
                for r in range(rows):
                    y = p0[1] + (y_low - p0[1]) * r / (rows - 1)
                    flare = 0.012 * (r / (rows - 1)) ** 1.5
                    Vd.append([h.C[0] + (rh + flare) * np.sin(np.radians(lo)), y, h.C[2] + (rh + flare) * np.cos(np.radians(lo))])
            Vd = np.array(Vd).reshape(len(glon), rows, 3).transpose(1, 0, 2).reshape(-1, 3)
            md = np.tile(back, (rows, 1))
            Fd = grid_faces(md)
            parts.append(('hair_drape', Vd, Fd, np.tile(HAIRC[sex], (len(Vd), 1))))
            hair_X_truth.append(Vd[np.unique(Fd)])
        # remove skin under the hair
        tc = Pv[Tsk].mean(1)
        tlo, tla = dir_lonlat(tc - h.C)
        under = tla > np.interp(tlo, lons, hl, period=360) + 1.0
        under &= ~h.vgroups['ears'][Tsk].any(1)
        T_keep &= ~under
    # ---- beard shell
    beard_truth = None
    if cfg['beard']:
        breg = m.beard_region[:ns].copy()
        off = breg.astype(float)
        for _ in range(4):        # smooth falloff at the edge
            acc = np.zeros(len(off)); cnt = np.zeros(len(off))
            np.add.at(acc, E_sk[:, 0], off[E_sk[:, 1]]); np.add.at(cnt, E_sk[:, 0], 1)
            off = 0.5 * off + 0.5 * acc / np.maximum(cnt, 1)
        thick = 0.009 * off
        tri_b = (breg[Tsk].sum(1) >= 2) & m.tri_valid[:nts] & ~h.vgroups['lips'][Tsk].all(1)
        Vb = Pv + Nv * thick[:, None]
        Fb = Tsk[tri_b]
        used = np.unique(Fb)
        remap = -np.ones(len(Vb), int); remap[used] = np.arange(len(used))
        parts.append(('beard', Vb[used], remap[Fb], np.tile(HAIRC[sex], (len(used), 1)) * 0.9))
        T_keep &= ~(breg[Tsk].any(1) & m.tri_valid[:nts] & ~h.vgroups['lips'][Tsk].any(1))
        beard_truth = True
    # ---- skin
    used = np.unique(Tsk[T_keep])
    remap = -np.ones(len(Pv), int); remap[used] = np.arange(len(used))
    parts.insert(0, ('skin', Pv[used], remap[Tsk[T_keep]], skin_col[used]))
    # ---- eyes (the RL eyeballs, fused: only the visible front outside the skin)
    if len(PE):
        sd, _, _ = h.signed(PE, D=Pv - h.P)
        fnz = vertex_normals(PE, TE)[TE].mean(1)[:, 2]
        keep_t = (sd[TE] > 0.0002).all(1) & (fnz > 0.0)
        ec = np.zeros((len(PE), 3))
        for side in (1, -1):
            sm = np.sign(PE[:, 0]) == side
            c = PE[sm].mean(0) - np.array([0, 0, 0.004])
            ang = np.degrees(np.arccos(np.clip(unit(PE[sm] - c)[:, 2], -1, 1)))
            ec[sm] = np.where(ang[:, None] < 9, np.array([0.05, 0.04, 0.04]),
                              np.where(ang[:, None] < 26, np.array(EYEC[sex]), np.array([0.92, 0.9, 0.88])))
        used_e = np.unique(TE[keep_t])
        re = -np.ones(len(PE), int); re[used_e] = np.arange(len(used_e))
        parts.append(('eyes', PE[used_e], re[TE[keep_t]], ec[used_e]))
    # ---- neck tube + shoulders (clothing)
    rimP = h.P[h.rim]
    cx, cz = rimP[:, 0].mean(), rimP[:, 2].mean()
    rn = np.mean(np.hypot(rimP[:, 0] - cx, rimP[:, 2] - cz))
    y_sh = rimP[:, 1].min() - 0.10
    ang = np.radians(np.arange(0, 360, 6.0))
    ra = np.arctan2(rimP[:, 0] - cx, rimP[:, 2] - cz)
    o = np.argsort(ra)
    top = np.interp(ang, ra[o] % (2 * np.pi), rimP[o, 1], period=2 * np.pi) + 0.001
    fr = np.linspace(0, 1, 8)
    Vn = np.array([[cx + rn * np.sin(a), yt + (y_sh + 0.075 - yt) * f, cz + rn * np.cos(a)] for f in fr for a, yt in zip(ang, top)])
    Fn = grid_faces(np.ones((len(fr), len(ang)), bool))
    Fn = Fn[:, [0, 2, 1]]
    parts.append(('neck', Vn, Fn, np.tile(SKIN[sex], (len(Vn), 1))))
    Vs, Fs = sphere(np.array([cx, y_sh, cz]), 1.0, nu=72, nv=36)
    Vs = (Vs - [cx, y_sh, cz]) * [0.21, 0.10, 0.12] + [cx, y_sh, cz]
    tcs = Vs[Fs].mean(1)
    keep = (tcs[:, 1] > y_sh - 0.02) & (np.hypot(tcs[:, 0] - cx, tcs[:, 2] - cz) > rn * 0.95)
    parts.append(('shoulders', Vs, Fs[keep], np.tile(CLOTH, (len(Vs), 1))))
    # ---- baked lighting
    L = unit(np.array([0.35, 0.75, 0.6]))
    Nf = vertex_normals(Pv, Tsk, wsk)
    lonf, _ = dir_lonlat(Pv - h.C)
    ndl_ref = float(np.median(Nf[np.abs(lonf) < 60] @ L))
    out_parts = []
    for name, V, F, col in parts:
        Nn = vertex_normals(V, F) if len(F) else np.zeros_like(V)
        H = unit(L + np.array([0, 0, 1.0]))
        spec = np.clip(Nn @ H, 0, 1) ** 40 * (0.18 if name in ('skin', 'hair', 'beard') else 0.05)
        # soft directional light, exposure-neutral on the front of the face (albedo = median there)
        shade = np.clip(1 + 0.55 * (Nn @ L - ndl_ref), 0.45, 1.6)
        lin = srgb_to_linear(np.clip(col, 0, 1)) * shade[:, None] + spec[:, None]
        out_parts.append((name, V, F, linear_to_srgb(np.clip(lin, 0, 1))))
    # ---- noise
    if cfg['noise_mm'] > 0:
        out_parts = [(n, V + rng.normal(0, cfg['noise_mm'] / 1000.0, V.shape), F, c) for n, V, F, c in out_parts]
    # ---- transform: game -> reference file
    U = UP[cfg['up']]
    tilt_axis = unit(np.r_[rng.normal(size=1), 0, rng.normal(size=1)])
    Rt = rot_axis_angle(tilt_axis, np.radians(cfg['tilt']))
    R = Rt @ rot_y(-cfg['yaw']) @ U           # ref -> game rotation (face looks along (sin yaw, 0, cos yaw) in the file)
    s = 1.0 / cfg['scale']                   # game metres per reference unit
    t = np.array([0.0, 1.62, 0.0]) - s * R @ (rng.normal(0, 0.3, 3) * cfg['scale'] + np.array([0, 0.2, 0]) * cfg['scale'])
    sim = Sim(s, R, t)
    # half of the rotation (the up conversion) goes in the node matrix
    Nmat = np.eye(4); Nmat[:3, :3] = U.T                  # node: local -> ref
    gl_parts = []
    all_V = []; all_F = []; all_C = []; off = 0
    for name, V, F, col in out_parts:
        Vref = sim.inv(V)
        Vloc = Vref @ U.T                      # local = U @ ref  (the node matrix maps local -> ref with U^T)
        gl_parts.append({'name': name, 'V': Vloc, 'F': F, 'col': col})
    os.makedirs(out_dir, exist_ok=True)
    glb_path = os.path.join(out_dir, f'{case}.glb')
    if cfg['texture']:
        Vall = np.concatenate([p['V'] for p in gl_parts]); Call = np.concatenate([p['col'] for p in gl_parts])
        Fall = np.concatenate([p['F'] + o for p, o in zip(gl_parts, np.cumsum([0] + [len(p['V']) for p in gl_parts])[:-1])])
        Vt, Ft, UVt, png = atlas(Vall, Fall, Call, size=2048)
        sd = cfg.get('subdiv', 0)
        for _ in range(sd):
            Vt, Ft, A = subdivide(Vt, Ft, {'uv': UVt}); UVt = A['uv']
        size = gltfio.write_glb(glb_path, [{'name': 'reference', 'V': Vt, 'F': Ft, 'UV': UVt, 'png': png}], node_matrix=Nmat)
        ntri = len(Ft)
    else:
        gp = [{'name': p['name'], 'V': p['V'], 'F': p['F'], 'vcol': srgb_to_linear(p['col'])} for p in gl_parts]
        size = gltfio.write_glb(glb_path, gp, node_matrix=Nmat)
        ntri = int(sum(len(p['F']) for p in gp))
    # ---- truth
    hair_truth = None
    if hair_X_truth:
        # dense truth samples of the hair surfaces (game space)
        from refmesh import RefMesh
        hp = [{'name': n, 'V': V, 'F': F, 'UV': None, 'tex': None, 'vcol': None, 'factor': np.ones(4)}
              for n, V, F, c in parts if n.startswith('hair') and len(F)]
        HX = RefMesh(parts=hp).sample(200_000, seed=1).X
        rs = envelope.skin_radius(Pv, h.T_noear, h.C)
        th = envelope.envelope(HX, None, h.C, rs, envelope.SkinRadius(Pv, h.T_noear, h.C))['thickness_m']
        np.savez(os.path.join(out_dir, 'truth_envelope.npz'), lon_deg=envelope.LON, lat_deg=envelope.LAT, thickness_m=th,
                 drape_lowest_y=envelope.drape(HX, h.C)['drape_lowest_y'])
        hair_truth = {'lowest_y': float(HX[:, 1].min()), 'max_thickness_mm': float(np.nanpercentile(th, 99) * 1000)}
    truth = {'case': case, 'sex': sex, 'controls': controls, 'transform': sim.to_json(), 'up': cfg['up'], 'yaw': cfg['yaw'],
             'tilt_deg': cfg['tilt'], 'colours': {'skin_srgb': SKIN[sex], 'hair_srgb': HAIRC[sex] if cfg['hair'] != 'none' or cfg['beard'] else None,
                                                  'lip_srgb': LIPC[sex], 'brow_srgb': BROWC[sex], 'eye_srgb': EYEC[sex]},
             'hair': hair_truth, 'beard': bool(cfg['beard']), 'glb': glb_path, 'triangles': ntri, 'bytes': size, 'config': cfg}
    json.dump(truth, open(os.path.join(out_dir, 'truth.json'), 'w'), indent=1)
    return truth


def atlas(V, F, C, size=2048):
    """Per-triangle texture atlas: each triangle gets its own cell painted with its vertex colours."""
    n = len(F)
    g = int(np.ceil(np.sqrt(n)))
    cell = size // g
    if cell < 4:
        raise ValueError('too many triangles for the atlas')
    tex = np.zeros((size, size, 3), np.float32)
    k = np.arange(n)
    cx = (k % g) * cell; cy = (k // g) * cell
    # triangle corners in texel space: (1,1), (cell-1, 1), (1, cell-1) (pixel-edge coords)
    a0 = np.stack([cx + 1.0, cy + 1.0], 1); a1 = np.stack([cx + cell - 1.0, cy + 1.0], 1); a2 = np.stack([cx + 1.0, cy + cell - 1.0], 1)
    # paint: texel centres in the cell, barycentrics of the right triangle, clamped (dilation)
    ii, jj = np.meshgrid(np.arange(cell), np.arange(cell), indexing='xy')
    px = ii.ravel() + 0.5; py = jj.ravel() + 0.5          # relative to the cell
    span = cell - 2.0
    b1 = np.clip((px - 1.0) / span, 0, 1); b2 = np.clip((py - 1.0) / span, 0, 1)
    over = b1 + b2 > 1
    s = b1 + b2
    with np.errstate(divide='ignore', invalid='ignore'):
        b1 = np.where(over, b1 / s, b1); b2 = np.where(over, b2 / s, b2)
    b0 = 1 - b1 - b2
    cols = C[F]                                            # (n,3,3)
    for start in range(0, n, 20000):
        sl = slice(start, min(n, start + 20000))
        c = cols[sl, 0, None, :] * b0[None, :, None] + cols[sl, 1, None, :] * b1[None, :, None] + cols[sl, 2, None, :] * b2[None, :, None]
        X = (cx[sl, None] + ii.ravel()[None, :]); Y = (cy[sl, None] + jj.ravel()[None, :])
        tex[Y.ravel(), X.ravel()] = c.reshape(-1, 3)
    # per-corner UVs (vertices are split per triangle)
    Vt = V[F].reshape(-1, 3)
    UV = np.stack([a0, a1, a2], 1).reshape(-1, 2) / size
    Ft = np.arange(3 * n).reshape(-1, 3)
    buf = io.BytesIO()
    Image.fromarray((np.clip(tex, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, format='PNG', optimize=False, compress_level=3)
    return Vt, Ft, UV, buf.getvalue()


# ------------------------------------------------------------------ evaluation
RELIABLE = ['brow_ridge', 'brow_height', 'nose_width', 'nose_length', 'nose_bridge', 'nose_tip', 'nose_depth',
            'mouth_width', 'cheekbones', 'cheek_fullness', 'jaw_width', 'chin_length', 'chin_projection', 'chin_width', 'ear_size']
BEARD_HIDDEN = ['jaw_width', 'chin_length', 'chin_projection', 'chin_width', 'mouth_width', 'lip_fullness', 'cupid_bow']


def evaluate(truth, fit, fit_dir=None):
    names = control_names()
    tv = np.array([truth['controls'][n] for n in names]); fv = np.array([fit['controls'][n] for n in names])
    err = fv - tv
    rel = [n for n in RELIABLE if not (truth['beard'] and n in BEARD_HIDDEN)]
    ri = [names.index(n) for n in rel]
    out = {'case': truth['case'], 'control_rmse_all': float(np.sqrt(np.mean(err ** 2))), 'control_max_all': float(np.abs(err).max()),
           'control_rmse_reliable': float(np.sqrt(np.mean(err[ri] ** 2))), 'control_max_reliable': float(np.abs(err[ri]).max()),
           'worst': sorted([(n, round(float(e), 3)) for n, e in zip(names, err)], key=lambda x: -abs(x[1]))[:6]}
    T = truth['transform']; F = fit['transform']
    Rt = np.array(T['R']); Rf = np.array(F['R'])
    out['scale_err_pct'] = float((F['scale'] / T['scale'] - 1) * 100)
    out['rot_err_deg'] = rot_angle_deg(Rf @ Rt.T)
    # translation error at the head centre (game space): map the true head centre back to the reference
    st = Sim(T['scale'], Rt, T['t']); sf = Sim(F['scale'], Rf, F['t'])
    import rlmodel as _rm
    c = np.array([0.0, 1.63, 0.02])
    out['centre_err_mm'] = float(np.linalg.norm(sf(st.inv(c[None]))[0] - c) * 1000)
    out['orientation'] = fit['orientation']
    if truth.get('hair') and fit_dir and os.path.exists(os.path.join(fit_dir, 'envelope.npz')):
        te = np.load(os.path.join(os.path.dirname(truth['glb']), 'truth_envelope.npz'))
        fe = np.load(os.path.join(fit_dir, 'envelope.npz'))
        A = te['thickness_m']; B = fe['thickness_m']
        both = np.isfinite(A) & np.isfinite(B)
        w = np.cos(np.radians(te['lat_deg']))[:, None] * np.ones_like(A)
        iou = (w * both).sum() / max((w * (np.isfinite(A) | np.isfinite(B))).sum(), 1e-9)
        out['envelope_mae_mm'] = float((w[both] * np.abs(A[both] - B[both])).sum() / max(w[both].sum(), 1e-9) * 1000)
        out['envelope_p90_mm'] = float(np.percentile(np.abs(A[both] - B[both]) * 1000, 90)) if both.any() else None
        out['envelope_iou'] = float(iou)
        da = te['drape_lowest_y']; db = fe['drape_lowest_y']
        bb = np.isfinite(da) & np.isfinite(db)
        out['drape_lowest_y_mae_mm'] = float(np.mean(np.abs(da[bb] - db[bb])) * 1000) if bb.any() else None
        out['lowest_y_err_mm'] = float((fit['hair']['lowest_y'] - truth['hair']['lowest_y']) * 1000) if fit['hair']['present'] else None
    out['hair_present'] = fit['hair']['present']; out['beard_present'] = fit['beard']['present']
    out['beard_truth'] = truth['beard']
    out['hair_truth'] = truth.get('hair') is not None
    # pass/fail checks: hair/beard presence, transform, controls the data can resolve
    names_meas = [n for n in names if fit.get('control_reliability', {}).get(n, {}).get('status') in ('measured', 'at_limit')]
    err_meas = [abs(fit['controls'][n] - truth['controls'][n]) for n in names_meas]
    out['checks'] = {'hair_presence': out['hair_present'] == out['hair_truth'],
                     'beard_presence': bool(out['beard_present']) == bool(truth['beard']),
                     'scale_err_lt_2pct': abs(out['scale_err_pct']) < 2.0, 'rot_err_lt_3deg': out['rot_err_deg'] < 3.0,
                     'status_not_fail': fit['quality']['status'] != 'fail'}
    if not truth.get('config', {}).get('nonmodel_mm'):
        # in-model references only (a smooth off-model displacement legitimately moves the controls)
        out['checks']['reliable_rmse_le_0.12'] = out['control_rmse_reliable'] <= 0.12
    out['measured_max_error'] = round(float(max(err_meas)), 3) if err_meas else None
    out['quality_status'] = fit['quality']['status']
    out['pass'] = bool(all(out['checks'].values()))
    col = {}
    for k in ('skin_srgb', 'hair_srgb', 'lip_srgb', 'brow_srgb', 'eye_srgb'):
        a = truth['colours'].get(k); b = fit['colours'].get(k)
        if a is not None and b is not None:
            col[k] = round(float(np.linalg.norm(srgb_to_lab(np.array(a)) - srgb_to_lab(np.array(b)))), 1)
        else:
            col[k] = None if a is None and b is None else f'truth={a is not None} fit={b is not None}'
    out['colour_deltaE'] = col
    out['residual_face_rms_mm'] = fit['residual_mm']['face_rms']
    out['residual_before_face_rms_mm'] = fit['residual_mm_before']['face_rms']
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('--case', required=True); b.add_argument('--out')
    r = sub.add_parser('run'); r.add_argument('--cases', default='female_long,male_beard'); r.add_argument('--quick', action='store_true')
    r.add_argument('--rebuild', action='store_true'); r.add_argument('--extra', default='')
    r.add_argument('--out-root', default=None, help='where fits/<case> and selftest_results*.json go (default RL/fit/dev); '
                                                    'the references are always built in RL/fit/dev/synth/<case>')
    e = sub.add_parser('eval'); e.add_argument('--truth', required=True); e.add_argument('--fit', required=True)
    a = ap.parse_args()
    if a.cmd == 'build':
        out = a.out or os.path.join(DEV_DIR, 'synth', a.case)
        t = time.time()
        tr = build(a.case, out)
        print(json.dumps({k: tr[k] for k in ('glb', 'triangles', 'bytes')}), f'{time.time() - t:.1f}s')
    elif a.cmd == 'eval':
        truth = json.load(open(a.truth)); fit = json.load(open(a.fit))
        print(json.dumps(evaluate(truth, fit, os.path.dirname(a.fit)), indent=1))
    else:
        results = []
        root = a.out_root or DEV_DIR
        for case in a.cases.split(','):
            sd = os.path.join(DEV_DIR, 'synth', case)
            if a.rebuild or not os.path.exists(os.path.join(sd, 'truth.json')):
                build(case, sd)
            truth = json.load(open(os.path.join(sd, 'truth.json')))
            fd = os.path.join(root, 'fits', case + ('_quick' if a.quick else ''))
            cmd = [sys.executable, os.path.join(HERE, 'fit_reference.py'), truth['glb'], '--sex', truth['sex'], '--out', fd]
            if a.quick:
                cmd.append('--quick')
            cmd += [x for x in a.extra.split() if x]
            t = time.time()
            p = subprocess.run(cmd, capture_output=True, text=True)
            dt = time.time() - t
            if p.returncode != 0:
                print(p.stdout[-3000:], p.stderr[-3000:])
                results.append({'case': case, 'error': p.returncode, 'pass': False, 'stderr_tail': p.stderr[-1500:]})
                continue
            open(os.path.join(fd, 'stdout.log'), 'w').write(p.stdout)
            ev = evaluate(truth, json.load(open(os.path.join(fd, 'fit.json'))), fd)
            ev['runtime_s'] = round(dt, 1); ev['triangles'] = truth['triangles']
            results.append(ev)
            print(json.dumps(ev, indent=1))
        os.makedirs(root, exist_ok=True)
        json.dump(results, open(os.path.join(root, 'selftest_results' + ('_quick' if a.quick else '') + '.json'), 'w'), indent=1)
        print('\n=== self-test summary' + (' (--quick)' if a.quick else ''))
        for r_ in results:
            bad = [k for k, ok in r_.get('checks', {}).items() if not ok]
            print(f"  {'PASS' if r_.get('pass') else 'FAIL'}  {r_['case']}: "
                  + (f"exit {r_['error']}" if 'error' in r_ else
                     f"hair {r_['hair_present']}/{r_['hair_truth']} beard {r_['beard_present']}/{r_['beard_truth']} "
                     f"reliable rmse {r_['control_rmse_reliable']:.3f} scale {r_['scale_err_pct']:+.3f}% rot {r_['rot_err_deg']:.2f} deg "
                     f"status {r_['quality_status']} {r_['runtime_s']} s" + (f" failed: {bad}" if bad else '')))
        sys.exit(0 if all(r_.get('pass') for r_ in results) else 1)


if __name__ == '__main__':
    main()
