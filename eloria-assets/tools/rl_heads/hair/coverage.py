"""coverage -- does any scalp show through an RL hair module?

Ray-casts from scalp samples (head skin inside the style's hairline, at least
--margin degrees of true angular distance in from it) toward a sphere of view
directions, and reports the samples an outside viewpoint sees through the hair.
The runtime model (rl_hair.gdshader + the hair_detail contract): clumps and cards
are drawn double-sided and alpha-tested at 0.5 against their texture
(hair_clump.png / hair_strands.png, UV wrapped), and a vertex with
COLOR_0.A < 1 - level is discarded. Detail level 0 is the worst case (only core
A = 1 geometry is drawn; every other level only adds hair). The head itself (ears
included) occludes; the body does not (conservative). View directions stop at
elevation --min-el (a camera below the shoulders cannot look up at the scalp).

An escaped ray counts only when it is robust (2 of 4 rays from origins jittered by
0.25 mm escape too: one ray slipping through a shared triangle edge is not a hole)
and is then classified:
  hole  the ray climbs 10 mm off the skin while still 6 deg or more inside the
        hairline: the viewer looks through a gap in the hair (a FAIL);
  edge  it runs out under the hairline edge first, grazing the skin: the natural
        view under a fringe, over an ear or up at a nape line (reported only).
Cases: rest, the grooming extremes and pairs, all_id_p / all_id_n (alone and with
hl_volume_n + hl_length_n) and four random identity mixes, on every LOD.

Usage:
  python coverage.py <hair.glb> --sex male [--style styles/x.json] [--lods 0,1,2]
         [--level 0] [--cases rest,hl_volume_n] [--json out.json] [--map out.png]
--map draws an equirectangular lon/lat map per case (red: holes, orange: edge).
Exit status 1 when any case has a hole (validate.py gates rest + hl_*_n only and
reports the identity cases as warnings).
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths      # noqa: E402
import rlglb      # noqa: E402
import headref    # noqa: E402
import hairgen    # noqa: E402

ALPHA_SCISSOR = 0.5
_TEX = {}


def _alpha(name):
    if name not in _TEX:
        from PIL import Image
        p = name if os.path.isabs(name) else os.path.join(paths.HAIR_TEX, name)
        if not os.path.exists(p):
            p = os.path.join(paths.BEARD_TEX, os.path.basename(name))
        im = Image.open(p).convert('RGBA')
        _TEX[name] = np.asarray(im, np.float32)[:, :, 3] / 255.0
    return _TEX[name]


def load_hair(path):
    """-> {lod: {'P','T','UV','A','tex' (per tri),'targets': {name: D}}}"""
    J, B = rlglb.read(path)[:2]
    out = {}
    for m in J['meshes']:
        name = m['name']
        if not name.startswith(('hair_lod', 'beard_lod')):
            continue
        lod = int(name.rsplit('lod', 1)[1])
        names = m.get('extras', {}).get('targetNames', [])
        Ps, Ts, UVs, As, texs, D = [], [], [], [], [], {n: [] for n in names}
        off = 0
        for pr in m['primitives']:
            a = pr['attributes']
            P = np.asarray(rlglb.accessor(J, B, a['POSITION']), np.float64)
            T = np.asarray(rlglb.accessor(J, B, pr['indices']), np.int64).reshape(-1, 3)
            UV = np.asarray(rlglb.accessor(J, B, a['TEXCOORD_0']), np.float64)
            C = np.asarray(rlglb.accessor(J, B, a['COLOR_0']), np.float64)
            if C.max() > 1.5:
                C = C / 255.0
            A = C[:, 3] if C.shape[1] > 3 else np.ones(len(P))
            mat = J['materials'][pr['material']]
            tex = (mat.get('extras') or {}).get('texture', 'hair_clump.png')
            for n, t in zip(names, pr.get('targets', [])):
                D[n].append(np.asarray(rlglb.accessor(J, B, t['POSITION']), np.float64))
            Ps.append(P); Ts.append(T + off); UVs.append(UV); As.append(A)
            texs += [tex] * len(T)
            off += len(P)
        out[lod] = {'P': np.concatenate(Ps), 'T': np.concatenate(Ts), 'UV': np.concatenate(UVs),
                    'A': np.concatenate(As), 'tex': np.array(texs),
                    'targets': {n: np.concatenate(v) for n, v in D.items() if v}}
    return J, out


def inside_by(scalp, lon, lat, margin_deg):
    """Inside the hairline by at least margin_deg of true angular distance to the hairline
    curve (a latitude margin alone is far too lax where the hairline runs steeply, as
    behind the ears and at the nape corners)."""
    lon = np.atleast_1d(np.asarray(lon, np.float64)); lat = np.atleast_1d(np.asarray(lat, np.float64))
    ins = scalp.inside(lon, lat, 0.0)
    if margin_deg <= 0 or not ins.any():
        return ins
    key = id(scalp)
    if key not in _HL:
        hl = np.arange(-180, 180, 0.5)
        _HL[key] = hairgen.lonlat_dir(hl, scalp.hairline(hl))
    H = _HL[key]
    D = hairgen.lonlat_dir(lon[ins], lat[ins])
    cos = np.clip((D @ H.T).max(1), -1, 1)
    out = ins.copy()
    out[ins] = np.degrees(np.arccos(cos)) >= margin_deg
    return out


_HL = {}


def fib_dirs(n, min_el_deg):
    i = np.arange(n) + 0.5
    y = 1 - 2 * i / n
    r = np.sqrt(1 - y * y)
    phi = i * np.pi * (3 - np.sqrt(5))
    d = np.stack([r * np.cos(phi), y, r * np.sin(phi)], 1)
    return d[d[:, 1] >= np.sin(np.radians(min_el_deg))]


def scalp_samples(head, scalp, n, margin_deg, seed=5):
    """Area-uniform samples on the skin (ears excluded) inside the hairline."""
    rng = np.random.default_rng(seed)
    P, T = head.P, head.T_noear
    X = P[T]
    area = np.linalg.norm(np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]), axis=1) * 0.5
    cen = X.mean(1)
    lon, lat = hairgen.dir_lonlat(cen - scalp.C)
    ok = scalp.inside(lon, lat, 0.0) & (area > 0)
    tri = np.flatnonzero(ok)
    pick = rng.choice(tri, size=n * 3, p=area[tri] / area[tri].sum())
    u, v = rng.random((2, len(pick)))
    sw = u + v > 1
    u[sw], v[sw] = 1 - u[sw], 1 - v[sw]
    bc = np.stack([1 - u - v, u, v], 1)
    pts = (P[T[pick]] * bc[:, :, None]).sum(1)
    lon, lat = hairgen.dir_lonlat(pts - scalp.C)
    keep = inside_by(scalp, lon, lat, margin_deg)
    pick, bc = pick[keep][:n], bc[keep][:n]
    return T[pick], bc


def _morph(base, deltas, weights):
    X = base.copy()
    for n, w in weights.items():
        if w and n in deltas:
            X += w * deltas[n]
    return X


def default_configs(id_names, seed=11):
    cfg = [('rest', {}), ('hl_volume_n', {'hl_volume_n': 1}), ('hl_length_n', {'hl_length_n': 1}),
           ('hl_volume_n+hl_length_n', {'hl_volume_n': 1, 'hl_length_n': 1}),
           ('hl_volume_p', {'hl_volume_p': 1}), ('hl_length_p', {'hl_length_p': 1}),
           ('all_id_p', {n: 1 for n in id_names if n.endswith('_p')}),
           ('all_id_n', {n: 1 for n in id_names if n.endswith('_n')}),
           ('all_id_n+hl_volume_n+hl_length_n', dict({n: 1 for n in id_names if n.endswith('_n')},
                                                     hl_volume_n=1, hl_length_n=1)),
           ('all_id_p+hl_volume_n+hl_length_n', dict({n: 1 for n in id_names if n.endswith('_p')},
                                                     hl_volume_n=1, hl_length_n=1))]
    rng = np.random.default_rng(seed)
    bases = sorted({n[:-2] for n in id_names if n.endswith(('_p', '_n'))})
    for k in range(4):
        w = {}
        for b in bases:
            x = rng.uniform(-1, 1)
            w[b + ('_p' if x > 0 else '_n')] = abs(x)
        cfg.append((f'mix{k}', w))
    return cfg


def _bvh():
    try:
        from mathutils.bvhtree import BVHTree
    except ImportError:          # the pip bpy module ships mathutils behind bpy
        import bpy  # noqa: F401
        from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    return BVHTree, Vector


class _Scene:
    """Hair (detail-filtered, morphed) + head as one BVH, with the alpha-test model."""

    def __init__(self, hair, HP, head_T, weights, level):
        BVHTree, self.Vector = _bvh()
        self.XP = _morph(hair['P'], hair['targets'], weights)
        keep = hair['A'][hair['T']].min(1) >= 1.0 - level - 1e-4
        # a tri with any discarded corner is cut by the per-fragment test where A
        # interpolates below 1 - level: conservative, count it only when all corners survive
        self.Th = hair['T'][keep]; self.texs = hair['tex'][keep]; self.UV = hair['UV']
        nh = len(self.XP)
        verts = np.concatenate([self.XP, HP]); polys = np.concatenate([self.Th, head_T + nh])
        self.is_head = np.concatenate([np.zeros(len(self.Th), bool), np.ones(len(head_T), bool)])
        self.tree = BVHTree.FromPolygons(verts.tolist(), polys.tolist(), all_triangles=True)
        self.alphas = {t: _alpha(t) for t in np.unique(self.texs)}

    def escapes(self, O, D, layers=16):
        """Rays O + t D: True where no opaque hair texel and no head surface is hit."""
        V = self.Vector
        org = np.array(O, np.float64); n = len(org)
        D = np.broadcast_to(D, org.shape)
        last = np.full(n, -1, np.int64)
        active = np.ones(n, bool); out = np.zeros(n, bool)
        for _ in range(layers):
            idx = np.flatnonzero(active)
            if not len(idx):
                break
            hit_tri = np.full(len(idx), -1, np.int64); hit_loc = np.zeros((len(idx), 3))
            for k, i in enumerate(idx):
                o = org[i]; dv = V(D[i].tolist())
                loc, _n, ti, _dist = self.tree.ray_cast(V(o.tolist()), dv)
                # after a transparent texel the ray steps on by a hair's breadth only (a
                # surface crossing right there, a clump through the shell, is not
                # skipped); re-hitting the same triangle steps a little further
                for _r in range(3):
                    if loc is None or ti != last[i]:
                        break
                    o = np.asarray(loc) + D[i] * 2e-5
                    loc, _n, ti, _dist = self.tree.ray_cast(V(o.tolist()), dv)
                if loc is not None:
                    hit_tri[k] = ti; hit_loc[k] = loc
            miss = hit_tri < 0
            out[idx[miss]] = True; active[idx[miss]] = False
            h = ~miss
            if not h.any():
                break
            hi = idx[h]; ht = hit_tri[h]; hl = hit_loc[h]
            head_hit = self.is_head[ht]
            active[hi[head_hit]] = False           # the head (an ear, the other side) blocks
            hk = np.flatnonzero(~head_hit)
            if len(hk):
                tt = self.Th[ht[hk]]
                b = headref.barycentric(hl[hk], self.XP[tt[:, 0]], self.XP[tt[:, 1]], self.XP[tt[:, 2]])
                uv = (self.UV[tt] * b[:, :, None]).sum(1)
                opaque = np.zeros(len(hk), bool)
                tx = self.texs[ht[hk]]
                for tname, al in self.alphas.items():
                    s = tx == tname
                    if not s.any():
                        continue
                    hgt, wid = al.shape
                    px = (np.floor((uv[s, 0] % 1.0) * wid).astype(int)) % wid
                    py = (np.floor((uv[s, 1] % 1.0) * hgt).astype(int)) % hgt
                    opaque[s] = al[py, px] >= ALPHA_SCISSOR
                active[hi[hk[opaque]]] = False
                cont = hi[hk[~opaque]]
                org[cont] = hl[hk[~opaque]] + D[cont] * 1e-7
                last[cont] = ht[hk[~opaque]]
        return out          # rays still passing layers after `layers` hits count as covered


def visibility(hair, head, tri_s, bc_s, weights, level, dirs, min_cos=0.2, lift=0.0006, jitter=0.00025):
    """-> per-sample count of view directions that see the scalp sample, the samples,
    the escaped (sample, direction) pairs and the morphed skin. An escape counts only
    when it is robust: at least 2 of 4 rays from origins jittered by `jitter` escape as
    well (a single ray slipping through a shared triangle edge is not a hole)."""
    HP = _morph(head.P, head.deltas, {n: w for n, w in weights.items() if n.startswith('id_')})
    S = (HP[tri_s] * bc_s[:, :, None]).sum(1)
    tn = np.cross(HP[tri_s[:, 1]] - HP[tri_s[:, 0]], HP[tri_s[:, 2]] - HP[tri_s[:, 0]])
    Nn = tn / np.maximum(np.linalg.norm(tn, axis=1, keepdims=True), 1e-12)
    sc = _Scene(hair, HP, head.T, weights, level)
    O = S + Nn * lift
    es, ed = [], []
    for di, d in enumerate(dirs):
        facing = np.flatnonzero(Nn @ d > min_cos)
        if not len(facing):
            continue
        e = sc.escapes(O[facing], d)
        if e.any():
            es.append(facing[e]); ed.append(np.full(int(e.sum()), di))
    es = np.concatenate(es) if es else np.zeros(0, int); ed = np.concatenate(ed) if ed else np.zeros(0, int)
    robust = np.zeros(len(es), bool)
    if len(es):
        D = dirs[ed]
        a1 = np.cross(D, Nn[es]); a1 /= np.maximum(np.linalg.norm(a1, axis=1, keepdims=True), 1e-9)
        a2 = np.cross(D, a1)
        votes = np.zeros(len(es), int)
        for off in (a1, -a1, a2, -a2):
            Oj = S[es] + Nn[es] * lift + off * jitter
            votes += sc.escapes(Oj, D)
        robust = votes >= 2
    es, ed = es[robust], ed[robust]
    cnt = np.bincount(es, minlength=len(S)).astype(np.int32)
    return cnt, S, (es, ed), HP


def skin_radius(head, scalp, HP=None, step=2.0):
    """Outermost skin radius from the frame centre C on a lon/lat grid (ears excluded),
    for the rest skin or a morphed one (HP)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    HP = head.P if HP is None else HP
    lo = np.arange(-180, 180 + step, step); la = np.arange(-90, 90 + step, step)
    LO, LA = np.meshgrid(lo, la, indexing='ij')
    D = hairgen.lonlat_dir(LO.ravel(), LA.ravel())
    tree = BVHTree.FromPolygons(HP.tolist(), head.T_noear.tolist(), all_triangles=True)
    r = np.full(len(D), np.nan)
    far = 0.3
    for k, d in enumerate(D):
        loc, _n, _i, dist = tree.ray_cast(Vector((scalp.C + d * far).tolist()), Vector((-d).tolist()))
        if loc is not None:
            r[k] = far - dist
    r = r.reshape(LO.shape)
    for i in range(r.shape[0]):
        col = r[i]; bad = np.isnan(col)
        if bad.any() and (~bad).any():
            col[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), col[~bad])
    return lo, la, r


def classify(S, esc, dirs, head, scalp, HP=None, cover_mm=10.0, reach_mm=80.0, inside_deg=6.0):
    """Split escaped rays into 'hole' (the ray leaves the hair cover - cover_mm above the
    skin - while still over the scalp, inside_deg in from the hairline, i.e. a viewer looks
    through a gap in the hair) and 'edge' (it runs out under the hairline edge first,
    grazing the skin: the natural view under a fringe or nape line)."""
    lo, la, R = skin_radius(head, scalp, HP)
    si, di = esc
    hole = np.zeros(len(si), bool)
    if not len(si):
        return hole
    X0 = S[si]; D = dirs[di]
    step = lo[1] - lo[0]
    done = np.zeros(len(si), bool)
    for t in np.arange(0.001, reach_mm * 1e-3, 0.001):
        X = X0 + D * t
        V = X - scalp.C
        rr = np.linalg.norm(V, axis=1)
        lon, lat = hairgen.dir_lonlat(V)
        fi = (lon - lo[0]) / step; fj = (lat - la[0]) / step
        i0 = np.clip(np.floor(fi).astype(int), 0, len(lo) - 2); j0 = np.clip(np.floor(fj).astype(int), 0, len(la) - 2)
        a = np.clip(fi - i0, 0, 1); b = np.clip(fj - j0, 0, 1)
        r = (R[i0, j0] * (1 - a) * (1 - b) + R[i0 + 1, j0] * a * (1 - b) + R[i0, j0 + 1] * (1 - a) * b + R[i0 + 1, j0 + 1] * a * b)
        out = ~done & (rr - r >= cover_mm * 1e-3)
        if out.any():
            hole[out] = inside_by(scalp, lon[out], lat[out], inside_deg)
            done |= out
        if done.all():
            break
    return hole


def check(glb, sex, style=None, lods=(0, 1, 2), level=0.0, configs=None, n_samples=900, n_dirs=220,
          min_el=-30.0, margin_deg=4.0, quiet=True, keep_points=False):
    J, hair = load_hair(glb)
    head = headref.Head(sex)
    if style is None:
        nm = J['asset'].get('extras', {}).get('rlHair', {}).get('style')
        cand = os.path.join(HERE, 'styles', f'{nm}.json')
        style = cand if os.path.exists(cand) else None
    hl = json.load(open(style)).get('hairline') if style else None
    scalp = hairgen.Scalp(head, hl)
    tri_s, bc_s = scalp_samples(head, scalp, n_samples, margin_deg)
    dirs = fib_dirs(n_dirs, min_el)
    if configs is None:
        configs = default_configs(head.id_names())
    rep = {'samples': int(len(tri_s)), 'directions': int(len(dirs)), 'marginDeg': margin_deg,
           'minElevationDeg': min_el, 'level': level, 'cases': []}
    pts = {}
    for lod in lods:
        if lod not in hair:
            continue
        for cname, w in configs:
            cnt, S, esc, HP = visibility(hair[lod], head, tri_s, bc_s, w, level, dirs)
            hole = classify(S, esc, dirs, head, scalp, HP)
            hcnt = np.bincount(esc[0][hole], minlength=len(S)) if len(esc[0]) else np.zeros(len(S), int)
            vis = cnt > 0; hv = hcnt > 0
            lon, lat = hairgen.dir_lonlat(S[hv] - scalp.C)
            case = {'lod': lod, 'case': cname, 'holeSamples': int(hv.sum()), 'holeFrac': round(float(hv.mean()), 4),
                    'holeRays': int(hcnt.sum()), 'edgeOnlySamples': int((vis & ~hv).sum()),
                    'visibleSamples': int(vis.sum()), 'where': _clusters(lon, lat, hcnt[hv])}
            rep['cases'].append(case)
            if keep_points:
                pts[(lod, cname)] = (S, cnt, hcnt)
            if not quiet:
                print(f"lod{lod} {cname:38s} holes {case['holeSamples']:4d} ({case['holeFrac'] * 100:.1f}%) rays "
                      f"{case['holeRays']:5d} | under-edge only {case['edgeOnlySamples']:3d} {case['where'][:3]}", flush=True)
    rep['ok'] = all(c['holeSamples'] == 0 for c in rep['cases'])
    rep['worst'] = max(rep['cases'], key=lambda c: (c['holeSamples'], c['holeRays'])) if rep['cases'] else None
    return (rep, pts) if keep_points else rep


def _clusters(lon, lat, w, cell=(20, 10)):
    if not len(lon):
        return []
    ki = np.floor(lon / cell[0]).astype(int); kj = np.floor(lat / cell[1]).astype(int)
    agg = {}
    for a, b, c in zip(ki, kj, w):
        k = (int(a), int(b)); n, s = agg.get(k, (0, 0)); agg[k] = (n + 1, s + int(c))
    out = sorted(agg.items(), key=lambda kv: -kv[1][1])
    return [{'lon': [k[0] * cell[0], (k[0] + 1) * cell[0]], 'lat': [k[1] * cell[1], (k[1] + 1) * cell[1]],
             'samples': v[0], 'rays': v[1]} for k, v in out]


def lonlat_map(pts, scalp, path, title=''):
    """Equirectangular map (lon -180..180 x lat -40..90) of visible samples per case."""
    from PIL import Image, ImageDraw
    cases = list(pts.items())
    W, H = 540, 230
    im = Image.new('RGB', (W, (H + 18) * len(cases)), (250, 250, 250)); dr = ImageDraw.Draw(im)
    for k, ((lod, cname), (S, cnt, hcnt)) in enumerate(cases):
        y0 = k * (H + 18)
        dr.text((4, y0 + 2), f'{title} lod{lod} {cname}: {int((hcnt > 0).sum())} through-hair holes (red), '
                f'{int(((cnt > 0) & (hcnt == 0)).sum())} under-edge only (orange)', fill=(0, 0, 0))
        y0 += 16
        X = lambda lo: (lo + 180) / 360 * W
        Y = lambda la: y0 + (90 - la) / 130 * H
        hl = np.arange(-180, 181, 2.0)
        dr.line([(X(a), Y(float(scalp.hairline(a)))) for a in hl], fill=(120, 160, 255))
        for a in (-90, 0, 90):
            dr.line([(X(a), y0), (X(a), y0 + H)], fill=(220, 220, 220))
        lon, lat = hairgen.dir_lonlat(S - scalp.C)
        for lo, la, c, hc in zip(lon, lat, cnt, hcnt):
            col = (190, 190, 190) if c == 0 else ((230, 40, 30) if hc else (245, 170, 40))
            r = 1 if c == 0 else 2 + min(3, int(max(hc, 1)) // 4)
            dr.ellipse((X(lo) - r, Y(la) - r, X(lo) + r, Y(la) + r), fill=col)
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('glb'); ap.add_argument('--sex', required=True)
    ap.add_argument('--style'); ap.add_argument('--lods', default='0,1,2')
    ap.add_argument('--level', type=float, default=0.0)
    ap.add_argument('--samples', type=int, default=900); ap.add_argument('--dirs', type=int, default=220)
    ap.add_argument('--margin', type=float, default=4.0); ap.add_argument('--min-el', type=float, default=-30.0)
    ap.add_argument('--cases', default='', help='comma list of case names (default: all)')
    ap.add_argument('--json'); ap.add_argument('--map')
    a = ap.parse_args()
    head_ids = headref.Head(a.sex).id_names()
    cfg = default_configs(head_ids)
    if a.cases:
        want = a.cases.split(',')
        cfg = [c for c in cfg if c[0] in want]
    rep, pts = check(a.glb, a.sex, a.style, [int(x) for x in a.lods.split(',')], a.level, cfg, a.samples,
                     a.dirs, a.min_el, a.margin, quiet=False, keep_points=True)
    if a.json:
        json.dump(rep, open(a.json, 'w'), indent=1)
    if a.map:
        J, _ = load_hair(a.glb)
        nm = J['asset'].get('extras', {}).get('rlHair', {}).get('style')
        st = a.style or os.path.join(HERE, 'styles', f'{nm}.json')
        scalp = hairgen.Scalp(headref.Head(a.sex), json.load(open(st)).get('hairline') if os.path.exists(st) else None)
        lonlat_map(pts, scalp, a.map, os.path.basename(a.glb))
    print(json.dumps({'ok': rep['ok'], 'worst': {k: rep['worst'][k] for k in ('lod', 'case', 'holeSamples', 'holeFrac', 'edgeOnlySamples')}}))
    sys.exit(0 if rep['ok'] else 1)


if __name__ == '__main__':
    main()
