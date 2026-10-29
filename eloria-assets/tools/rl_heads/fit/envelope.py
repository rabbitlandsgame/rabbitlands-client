"""Hair envelope in headref's frame, and the same envelope for existing RL / legacy hair GLBs.

Definition (also in README.md); game space, metres:
  grid      lon_deg (L=120,) bin centres -178.5 .. 178.5 step 3 (lon 0 = face/+Z, +90 = character's
            left/+X); lat_deg (M=50,) bin centres -58.5 .. 88.5 step 3 (lat +90 = top/+Y)
  rays      from headref's cranium centre C (Head(sex).C) in direction headref.lonlat_dir(lon, lat)
  skin      rho_skin_m[lat, lon] = distance from C to the outermost hit of the bin-centre ray on the
            RL skin without ears (headref's 'noear' triangles) - for a fit, the skin morphed by the
            fitted controls. NaN where the ray misses the skin (below the neck rim).
  hair      every hair point p (beard excluded) gets its own radial height above the skin in its own
            direction, h_p = |p - C| - rho_skin(dir(p - C)) (rho_skin bilinear on a 2-degree grid), so
            sloping skin inside a bin does not bias it; thickness_m[lat, lon] = max(98th percentile of
            h_p over the points in the bin (max for < 10 points), 0).
            NaN where no hair point falls in the bin, where the outermost surface in the bin is not hair
            (skin / clothing more than 3 mm beyond the hair), or where the ray misses the skin. Empty
            bins whose 8-neighbourhood is >= 5/8 hair are filled with the neighbour mean.
  outer     rho_outer_m = rho_skin_m + thickness_m: the outer hair surface is at
            C + lonlat_dir(lon, lat) * rho_outer_m (radial placement; exact by construction).
  normal    height_normal_m[lat, lon] = height of the outer hair surface along the skin normal at the
            bin's skin point S = C + dir * rho_skin, i.e. what Head.frame_point(lon, lat, height=...) needs;
            finite exactly where thickness_m is finite; height_normal_src says how (see height_normal()).
  state     state[lat, lon] int8: 0 no hair, 1 hair measured, 2 hair filled from neighbours,
            3 covered by other geometry (clothing/skin outside the hair), 4 ray misses the skin.
  count     count[lat, lon] = hair points in the bin (confidence).
  drape     hair below the head, as a cylinder around the vertical axis through C:
            drape_lon_deg (K=72,) sector centres -177.5 .. 177.5 step 5 of atan2(x - Cx, z - Cz);
            drape_y_m (Y=60,) slice centres C_y - 0.045 - 0.01 k; drape_r_outer_m / drape_r_inner_m
            (Y, K) = 98th / 2nd percentile of the horizontal distance from the axis of the hair points
            in the cell (max / min for < 10 points), NaN = no hair; drape_count (Y, K).
            drape_lowest_y (K,) = 1st percentile of the game Y of the hair points in the sector
            (NaN for < 30 points). hair.lowest_y = min over sectors of drape_lowest_y.
  hair_points (N <= 20000, 3): the hair points (connected to the scalp hair; beard excluded).
Beard points are not hair here.
"""
import os, json, hashlib
import numpy as np
import trimesh
from scipy.spatial import cKDTree

from fitcommon import unit, CACHE_DIR, HAIR_DIR, LEGACY_HAIR_DIR, kdq, log
from headref import lonlat_dir, dir_lonlat

LON = np.arange(-180.0, 180.0, 3.0) + 1.5
LAT = np.arange(-60.0, 90.0, 3.0) + 1.5
DRAPE_LON = np.arange(-180.0, 180.0, 5.0) + 2.5
DRAPE_DY = 0.01
DRAPE_NY = 60
DRAPE_TOP = 0.04            # first slice starts this far below C
FINE = 2.0                  # deg, skin-radius lookup grid for per-point heights (lat >= FINE_LAT0)
FINE_LAT0 = -80.0
STATE = {'none': 0, 'hair': 1, 'filled': 2, 'covered': 3, 'no_skin': 4}


def skin_radius(P, T, C, lon=LON, lat=LAT):
    """Outermost ray hit distance from C on the skin (P,T) for the lon/lat grid -> (M,L), NaN = miss."""
    LO, LA = np.meshgrid(lon, lat)
    D = lonlat_dir(LO.ravel(), LA.ravel())
    mesh = trimesh.Trimesh(P, T, process=False)
    O = np.repeat(np.asarray(C)[None], len(D), 0)
    locs, ri, _ = mesh.ray.intersects_location(O, D, multiple_hits=True)
    rho = np.full(len(D), np.nan)
    if len(locs):
        t = ((locs - O[ri]) * D[ri]).sum(1)
        ok = t > 0
        best = np.full(len(D), -np.inf)
        np.maximum.at(best, ri[ok], t[ok])
        rho = np.where(np.isfinite(best), best, np.nan)
    return rho.reshape(len(lat), len(lon))


class SkinRadius:
    """rho_skin(direction) by bilinear interpolation on a fine lon/lat grid (lon wraps)."""

    def __init__(self, P, T, C, step=FINE):
        self.C = np.asarray(C, np.float64)
        self.lon = np.arange(-180.0, 180.0, step) + step / 2
        self.lat = np.arange(FINE_LAT0, 90.0, step) + step / 2
        self.step = step
        self.rho = skin_radius(P, T, C, self.lon, self.lat)

    def __call__(self, X):
        lo, la = dir_lonlat(np.asarray(X) - self.C)
        fx = (lo - self.lon[0]) / self.step
        fy = np.clip((la - self.lat[0]) / self.step, 0, len(self.lat) - 1.000001)
        x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64)
        ax = fx - x0; ay = fy - y0
        L = len(self.lon)
        x0m = x0 % L; x1m = (x0 + 1) % L; y1 = np.minimum(y0 + 1, len(self.lat) - 1)
        r = self.rho
        v = (r[y0, x0m] * (1 - ax) * (1 - ay) + r[y0, x1m] * ax * (1 - ay) + r[y1, x0m] * (1 - ax) * ay + r[y1, x1m] * ax * ay)
        return v


def _bins(X, C, lon=LON, lat=LAT):
    lo, la = dir_lonlat(X - C)
    dl = lon[1] - lon[0]; dla = lat[1] - lat[0]
    i = np.floor((lo - (lon[0] - dl / 2)) / dl).astype(np.int64) % len(lon)
    j = np.floor((la - (lat[0] - dla / 2)) / dla).astype(np.int64)
    ok = (j >= 0) & (j < len(lat))
    return i, j, ok


def _group_percentile(key, val, size, q, small=10, low=False):
    """q-th percentile of val per integer key (NaN where empty; max (min if low) for < small values)."""
    out = np.full(size, np.nan); cnt = np.zeros(size, int)
    ok = np.isfinite(val)
    key = key[ok]; val = val[ok]
    if len(key):
        o = np.lexsort((val, key))
        key = key[o]; val = val[o]
        u, start, c = np.unique(key, return_index=True, return_counts=True)
        cnt[u] = c
        pos = np.where(c >= small, np.floor((c - 1) * q / 100.0).astype(int), 0 if low else c - 1)
        out[u] = val[start + pos]
    return out, cnt


def outer_radius(X, C, lon=LON, lat=LAT, q=98.0):
    """Robust outermost radius per bin of points X -> (M,L) (NaN where empty) and counts."""
    i, j, ok = _bins(X, C, lon, lat)
    rho = np.linalg.norm(X - C, axis=1)
    L, M = len(lon), len(lat)
    out, cnt = _group_percentile((j * L + i)[ok], rho[ok], M * L, q)
    return out.reshape(M, L), cnt.reshape(M, L)


def heights(X, C, srad):
    """Per point radial height above the skin in the point's own direction (NaN where the ray misses)."""
    return np.linalg.norm(X - C, axis=1) - srad(X)


def envelope(hair_X, other_X, C, rho_skin, srad, lon=LON, lat=LAT, skin_N=None, normal_tube=0.003):
    """Envelope arrays per the module definition: dict(thickness_m, rho_skin_m, rho_outer_m,
    height_normal_m, state, count)."""
    M, L = len(lat), len(lon)
    i, j, ok = _bins(hair_X, C, lon, lat)
    h = heights(hair_X, C, srad)
    th, ch = _group_percentile((j * L + i)[ok], h[ok], M * L, 98.0)
    th = th.reshape(M, L); ch = ch.reshape(M, L)
    rh, _ = outer_radius(hair_X, C, lon, lat)
    if other_X is not None and len(other_X):
        ro, _ = outer_radius(other_X, C, lon, lat)
    else:
        ro = np.full_like(rh, np.nan)
    state = np.zeros((M, L), np.int8)
    state[np.isfinite(th)] = STATE['hair']
    covered = np.isfinite(ro) & np.isfinite(rh) & (ro > rh + 0.003)
    th[covered] = np.nan
    state[covered] = STATE['covered']
    # fill sample holes: >= 5 of 8 neighbours hair (lon wraps)
    fin = np.isfinite(th)
    empty = (ch == 0) & ~np.isfinite(ro)
    pad = np.pad(np.where(fin, th, 0.0), ((1, 1), (0, 0)))
    padf = np.pad(fin.astype(float), ((1, 1), (0, 0)))
    s = np.zeros_like(th); n = np.zeros_like(th)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if dj == 0 and di == 0:
                continue
            s += np.roll(pad, di, axis=1)[1 + dj: 1 + dj + M]
            n += np.roll(padf, di, axis=1)[1 + dj: 1 + dj + M]
    fill = empty & ~fin & (n >= 5) & np.isfinite(rho_skin)
    th[fill] = s[fill] / n[fill]
    state[fill] = STATE['filled']
    th = np.where(np.isfinite(th), np.maximum(th, 0.0), np.nan)
    miss = ~np.isfinite(rho_skin)
    th[miss] = np.nan
    state[miss & (state > 0)] = STATE['no_skin']
    out = {'thickness_m': th, 'rho_skin_m': rho_skin.copy(), 'rho_outer_m': rho_skin + th, 'state': state,
           'count': ch.astype(np.int32)}
    hn, src = height_normal(hair_X, C, rho_skin, th, out['rho_outer_m'], skin_N, lon, lat, normal_tube)
    out['height_normal_m'] = hn
    out['height_normal_src'] = src
    return out


HN_SRC = {'none': 0, 'measured': 1, 'surface': 2, 'radial': 3}


def height_normal(hair_X, C, rho_skin, th, rho_outer, skin_N, lon=LON, lat=LAT, tube=0.003):
    """Height of the outer hair surface along the skin normal at each bin's skin point S = C + dir * rho_skin
    (what Head.frame_point(lon, lat, height=...) needs). Finite exactly where th is finite. Per bin:
      1 measured: the largest projection onto the normal of the hair points inside a `tube`-radius cylinder
        around the normal half-line (perpendicular distance < tube; projections clamped at 0). The old
        probe-sphere search reported the last probe position whose sphere touched hair, i.e. up to one tube
        radius beyond the hair (+2 mm on average); projecting the points removes that bias.
      2 surface: no hair point inside the tube (sparse sample, a filled bin, or the normal leaving the hair
        sideways at the edge of the hair): the distance along the normal to the radial outer envelope
        surface C + dir * rho_outer_m (bilinear in lon/lat, first crossing).
      3 radial: the normal never crosses that surface inside the hair region: thickness_m itself.
    Returns (height (M, L) metres, source code (M, L) int8, HN_SRC)."""
    M, L = th.shape
    hn = np.full((M, L), np.nan)
    src = np.zeros((M, L), np.int8)
    sel = np.isfinite(th) & np.isfinite(rho_skin)
    if skin_N is None or not len(hair_X) or not sel.any():
        return hn, src
    LO, LA = np.meshgrid(lon, lat)
    D = lonlat_dir(LO, LA)
    S = C + D * rho_skin[..., None]
    Sp = S[sel]; Np = unit(skin_N[sel])
    kd = cKDTree(hair_X)
    tmax = float(np.nanmax(th[sel])) * 2.0 + 0.02
    step = tube / 3.0
    ts = np.arange(-tube, tmax + step, step)
    last = np.full(len(Sp), np.nan)
    for t in ts:
        d, _ = kdq(kd, Sp + Np * t, k=1, distance_upper_bound=tube)
        last = np.where(np.isfinite(d), t, last)
    meas = np.full(len(Sp), np.nan)
    hit = np.nonzero(np.isfinite(last))[0]
    if len(hit):
        # the outermost tube points lie within ~one tube radius of the last probe that touched hair
        q = Sp[hit] + Np[hit] * last[hit][:, None]
        kk = min(48, len(hair_X))
        dk, jk = kdq(kd, q, k=kk, distance_upper_bound=2.0 * tube)
        dk = dk.reshape(len(hit), -1); jk = jk.reshape(len(hit), -1)
        okk = np.isfinite(dk)
        X = hair_X[np.where(okk, jk, 0)]
        vec = X - Sp[hit][:, None, :]
        along = (vec * Np[hit][:, None, :]).sum(2)
        perp = np.linalg.norm(vec - along[..., None] * Np[hit][:, None, :], axis=2)
        val = okk & (perp < tube)
        a = np.where(val, along, -np.inf).max(1)
        good = np.isfinite(a)
        meas[hit[good]] = np.maximum(a[good], 0.0)
    # fallback: crossing of the normal half-line with the radial outer envelope surface
    need = ~np.isfinite(meas)
    surf = np.full(len(Sp), np.nan)
    if need.any():
        ro = np.where(np.isfinite(rho_outer), rho_outer, np.nan)
        ni = np.nonzero(need)[0]
        dl = lon[1] - lon[0]; dla = lat[1] - lat[0]
        for t in np.arange(0.0, tmax + step, step):
            todo = ni[~np.isfinite(surf[ni])]
            if not len(todo):
                break
            Q = Sp[todo] + Np[todo] * t
            lo_, la_ = dir_lonlat(Q - C)
            fx = (lo_ - lon[0]) / dl; fy = np.clip((la_ - lat[0]) / dla, 0, M - 1.000001)
            x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64)
            ax = fx - x0; ay = fy - y0
            x0m = x0 % L; x1m = (x0 + 1) % L; y1 = np.minimum(y0 + 1, M - 1)
            corners = np.stack([ro[y0, x0m], ro[y0, x1m], ro[y1, x0m], ro[y1, x1m]], 1)
            wts = np.stack([(1 - ax) * (1 - ay), ax * (1 - ay), (1 - ax) * ay, ax * ay], 1)
            fin = np.isfinite(corners)
            wsum = (wts * fin).sum(1)
            r_o = np.where(wsum > 0.25, (np.where(fin, corners, 0.0) * wts).sum(1) / np.maximum(wsum, 1e-12), np.nan)
            crossed = np.isfinite(r_o) & (np.linalg.norm(Q - C, axis=1) >= r_o)
            surf[todo[crossed]] = t
    out = np.where(np.isfinite(meas), meas, surf)
    code = np.where(np.isfinite(meas), HN_SRC['measured'], np.where(np.isfinite(surf), HN_SRC['surface'], HN_SRC['radial']))
    out = np.where(np.isfinite(out), out, th[sel])
    hn[sel] = out
    src[sel] = code
    return hn, src


def skin_normals_at(P, T, weld, C, rho_skin, lon=LON, lat=LAT):
    """Interpolated skin normal at each bin's skin point (for height_normal_m)."""
    from headref import vertex_normals
    LO, LA = np.meshgrid(lon, lat)
    D = lonlat_dir(LO, LA)
    S = C + D * np.nan_to_num(rho_skin)[..., None]
    mesh = trimesh.Trimesh(P, T, process=False)
    cp, _, tri = trimesh.proximity.closest_point(mesh, S.reshape(-1, 3))
    Nv = vertex_normals(P, T, weld)
    t = T[tri]
    from headref import barycentric
    bc = barycentric(cp, P[t[:, 0]], P[t[:, 1]], P[t[:, 2]])
    return unit((Nv[t] * bc[:, :, None]).sum(1)).reshape(len(lat), len(lon), 3)


def drape(hair_X, C, K=DRAPE_LON):
    """Cylindrical drape arrays and the robust lowest Y per sector."""
    ang = np.degrees(np.arctan2(hair_X[:, 0] - C[0], hair_X[:, 2] - C[2]))
    d = K[1] - K[0]
    i = np.floor((ang - (K[0] - d / 2)) / d).astype(int) % len(K)
    low, cnt = _group_percentile(i, hair_X[:, 1], len(K), 1.0, low=True)
    low[cnt < 30] = np.nan
    ys = C[1] - DRAPE_TOP - DRAPE_DY * (np.arange(DRAPE_NY) + 0.5)
    yi = np.floor((C[1] - DRAPE_TOP - hair_X[:, 1]) / DRAPE_DY).astype(int)
    ok = (yi >= 0) & (yi < DRAPE_NY)
    r = np.hypot(hair_X[:, 0] - C[0], hair_X[:, 2] - C[2])
    key = (yi * len(K) + i)[ok]
    ro, c2 = _group_percentile(key, r[ok], DRAPE_NY * len(K), 98.0)
    ri, _ = _group_percentile(key, r[ok], DRAPE_NY * len(K), 2.0, low=True)
    return {'drape_lon_deg': K, 'drape_lowest_y': low, 'drape_y_m': ys,
            'drape_r_outer_m': ro.reshape(DRAPE_NY, len(K)), 'drape_r_inner_m': ri.reshape(DRAPE_NY, len(K)),
            'drape_count': c2.reshape(DRAPE_NY, len(K)).astype(np.int32)}


def lowest_y(dr):
    v = dr['drape_lowest_y']
    return float(np.nanmin(v)) if np.isfinite(v).any() else None


def coverage(th, scalp_mask, lat=LAT):
    """cos(lat)-weighted fraction of the scalp bins (mask) with finite thickness."""
    w = np.cos(np.radians(lat))[:, None] * np.ones_like(th)
    m = scalp_mask
    if not m.any():
        return 0.0
    return float((w * (np.isfinite(th) & m)).sum() / (w * m).sum())


def scalp_mask(head, lon=LON, lat=LAT):
    """Grid bins whose ray hits MPFB scalp-group skin (where hair grows), from the base head."""
    LO, LA = np.meshgrid(lon, lat)
    D = lonlat_dir(LO.ravel(), LA.ravel())
    O = np.repeat(head.C[None], len(D), 0)
    locs, ri, ti = head.mesh_noear.ray.intersects_location(O, D, multiple_hits=True)
    m = np.zeros(len(D), bool)
    if len(locs):
        t = ((locs - O[ri]) * D[ri]).sum(1)
        best = {}
        for k in range(len(t)):
            r = ri[k]
            if t[k] > 0 and (r not in best or t[k] > t[best[r]]):
                best[r] = k
        for r, k in best.items():
            tri = head.T_noear[ti[k]]
            m[r] = head.vgroups['scalp'][tri].sum() >= 2
    return m.reshape(len(lat), len(lon))


def implausible_bins(th, rel=2.5, abs_mm=40.0):
    """Bins whose thickness jumps far above their 8-neighbourhood median (> rel x and > abs_mm above):
    isolated spikes from mislabelled geometry. Returns a bool mask."""
    M, L = th.shape
    stack = []
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if dj == 0 and di == 0:
                continue
            sh = np.full_like(th, np.nan)
            src = np.roll(th, di, axis=1)
            if dj < 0:
                sh[:dj] = src[-dj:]
            elif dj > 0:
                sh[dj:] = src[:-dj]
            else:
                sh = src
            stack.append(sh)
    with np.errstate(all='ignore'):
        med = np.nanmedian(np.stack(stack), 0)
    return np.isfinite(th) & np.isfinite(med) & (th > rel * np.maximum(med, 0.004)) & (th - med > abs_mm / 1000.0)


# ------------------------------------------------------------ RL / legacy hair GLB envelopes
def _sample_glb(path, n=150_000, seed=0):
    import gltfio
    from refmesh import RefMesh
    parts = gltfio.read(path, want_texture=False)
    # LOD0 only (mesh names *_lod0) when the file has LODs
    lod0 = [p for p in parts if 'lod0' in p['name']]
    rm = RefMesh(parts=lod0 or parts)
    return rm.sample(n, seed=seed).X


def _file_key(path):
    st = os.stat(path)
    return hashlib.sha1(f'{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}|v3'.encode()).hexdigest()[:16]


def style_files(sex):
    """{style name: (path, sex)}: RL hair modules (any sex; sex from the GLB extras) and the shipped
    legacy fitted hairstyles on the luminous body of `sex` (runtime name legacy:<style>)."""
    import gltfio
    out = {}
    if os.path.isdir(HAIR_DIR):
        for fn in sorted(os.listdir(HAIR_DIR)):
            if fn.endswith('.glb'):
                path = os.path.join(HAIR_DIR, fn)
                try:
                    js = gltfio._read_container(path)[0]
                    s = js.get('asset', {}).get('extras', {}).get('rlHair', {}).get('sex', 'female')
                except Exception:
                    s = 'female'
                out[fn[:-4]] = (path, s)
    if os.path.isdir(LEGACY_HAIR_DIR):
        for fn in sorted(os.listdir(LEGACY_HAIR_DIR)):
            pre = f'luminous_{sex}_'
            if fn.startswith(pre) and fn.endswith(f'_{sex}.glb'):
                style = fn[len(pre):-len(f'_{sex}.glb')]
                out['legacy:' + style] = (os.path.join(LEGACY_HAIR_DIR, fn), sex)
    return out


def style_envelopes(load_head, sex):
    """Envelopes of the candidate hair styles for a fit of `sex` (cached)."""
    out = {}
    os.makedirs(CACHE_DIR, exist_ok=True)
    for name, (path, s) in style_files(sex).items():
        safe = name.replace(':', '_')
        cp = os.path.join(CACHE_DIR, f'style_{safe}_{s}_{_file_key(path)}.npz')
        if os.path.exists(cp):
            d = np.load(cp, allow_pickle=False)
            out[name] = {k: d[k] for k in d.files}
            out[name]['sex'] = str(d['sex'])
            continue
        h = load_head(s)
        X = _sample_glb(path)
        srad = SkinRadius(h.P, h.T_noear, h.C)
        rs = skin_radius(h.P, h.T_noear, h.C)
        env = envelope(X, None, h.C, rs, srad)
        dr = drape(X, h.C)
        sm = scalp_mask(h)
        rec = {'sex': s, 'thickness': env['thickness_m'], 'drape_lowest_y': dr['drape_lowest_y'],
               'lowest_y': lowest_y(dr) if lowest_y(dr) is not None else float(X[:, 1].min()),
               'rim_lo': float(h.P[h.rim, 1].min()), 'coverage': coverage(env['thickness_m'], sm),
               'max_thickness_mm': float(np.nanpercentile(env['thickness_m'], 99) * 1000) if np.isfinite(env['thickness_m']).any() else 0.0}
        np.savez(cp, **rec)
        out[name] = rec
    return out


STYLE_GOOD = 1.0     # score below this: a good match; above STYLE_POOR: warn


STYLE_POOR = 1.8


def compare(env_a, env_b):
    """Shape distance between two envelopes (smaller = closer):
         mean |thickness difference| / 15 mm over the union of hair bins (a bin without hair counts as
         0 mm; cos-lat weighted, the crown and back (lat > 0 or |lon| > 90) weighted 1.5)
       + 0.5 x (1 - IoU of the hair bins)
       + |difference of the hair's lowest point below the neck rim| / 0.10 m (each clamped at the rim:
         hair ending above the rim counts as ending at the rim, so short styles are compared by shape)."""
    A = env_a['thickness']; B = env_b['thickness']
    w = np.cos(np.radians(LAT))[:, None] * np.ones_like(A)
    LO, LA = np.meshgrid(LON, LAT)
    w = w * np.where((LA > 0) | (np.abs(LO) > 90), 1.5, 1.0)
    fa = np.isfinite(A); fb = np.isfinite(B)
    uni = fa | fb
    inter = (w * (fa & fb)).sum(); un = (w * uni).sum()
    iou = inter / un if un > 0 else 1.0
    A0 = np.where(fa, A, 0.0); B0 = np.where(fb, B, 0.0)
    dt = float((w[uni] * np.abs(A0[uni] - B0[uni])).sum() / max(w[uni].sum(), 1e-9)) if uni.any() else 0.0
    rim_a = float(env_a.get('rim_lo', 1.5)); rim_b = float(env_b.get('rim_lo', 1.5))
    la = min(float(env_a['lowest_y']) - rim_a, 0.0); lb = min(float(env_b['lowest_y']) - rim_b, 0.0)
    dy = abs(la - lb)
    score = float(dt / 0.015 + 0.5 * (1 - iou) + dy / 0.10)
    return score, {'iou': round(float(iou), 3), 'mean_abs_dt_mm': round(dt * 1000, 2), 'below_rim_diff_m': round(dy, 4)}


def nearest_style(me, styles, rim_lo):
    """(best name, scores, warning or None). Hair reaching clearly below the neck rim (> 30 mm) is only
    matched to styles that also reach below it; a poor best score gives a warning."""
    scores = {}
    for nm, se in styles.items():
        sc, det = compare(me, se)
        scores[nm] = dict(score=round(sc, 3), **det)
    if not scores:
        return None, scores, 'no hair style candidates found'
    cand = list(scores)
    long_hair = float(me['lowest_y']) < rim_lo - 0.03
    if long_hair:
        lc = [n for n in cand if float(styles[n]['lowest_y']) < float(styles[n].get('rim_lo', rim_lo)) - 0.005]
        if lc:
            cand = lc
    best = min(cand, key=lambda n: scores[n]['score'])
    warn = None
    if scores[best]['score'] > STYLE_POOR:
        warn = f"hair style match is poor (best {best} score {scores[best]['score']:.2f} > {STYLE_POOR}): check the previews"
    return best, scores, warn
