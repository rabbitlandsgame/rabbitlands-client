"""Shared helpers for the synthetic fitter acceptance harness (independent of RL/scripts/fit).

Nothing here imports the fitter. Read-only use of RL/scripts/hair/headref.py for the RL head.

Contents
  * paths and the RL Head loader (headref, read-only; no bytecode written into hair/)
  * radial_cast: exact ray/triangle hits for many rays from ONE origin (cube-map binned),
    used for headref-style radial rays (envelope ground truth, skin radius maps)
  * surface_nets: closed quad/triangle surface from a signed-distance grid (new topology)
  * taubin smoothing, smooth 3D noise, colour space helpers, rotation helpers
  * write_glb: minimal glTF 2.0 binary writer (textures, vertex colours, several meshes)
"""
import os, sys, json, struct, io
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, '..', '..'))               # eloria-assets/tools/rl_heads
RL = os.path.abspath(os.environ.get('RL_HEADS_LOCAL') or
                     os.path.join(TOOLS, '..', '..', '..', '.local', 'rl-heads'))
HAIR = os.path.join(TOOLS, 'hair')
SPECS = os.path.join(TOOLS, 'specs')
OUT_ROOT = os.path.join(RL, 'fit', 'synth')
CASES_DIR = os.path.join(OUT_ROOT, 'cases')
WORKTREE = os.path.normpath(os.path.join(TOOLS, '..', '..', '..'))
PRESETS = os.path.join(WORKTREE, 'godot-client', 'data', 'actors', 'rl_head_presets.json')
FITTER = os.path.join(TOOLS, 'fit', 'fit_reference.py')

LOW_OBS = ('eye_tilt', 'eyelid', 'cupid_bow', 'lip_fullness')


def controls_order():
    d = json.load(open(os.path.join(SPECS, 'controls.json'), encoding='utf-8'))
    return [c['name'] for c in d['controls']]


def load_head(sex):
    """headref.Head (read-only import; keeps __pycache__ out of the hair folder)."""
    sys.dont_write_bytecode = True
    if HAIR not in sys.path:
        sys.path.insert(0, HAIR)
    from headref import Head  # noqa
    return Head(sex)


def headref_module():
    sys.dont_write_bytecode = True
    if HAIR not in sys.path:
        sys.path.insert(0, HAIR)
    import headref  # noqa
    return headref


# ----------------------------------------------------------------------------- small math
def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def lonlat_dir(lon, lat):
    lo = np.radians(np.asarray(lon, np.float64)); la = np.radians(np.asarray(lat, np.float64))
    return np.stack([np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)], -1)


def dir_lonlat(d):
    d = unit(d)
    return np.degrees(np.arctan2(d[..., 0], d[..., 2])), np.degrees(np.arcsin(np.clip(d[..., 1], -1, 1)))


def rot_axis(axis, deg):
    a = unit(axis); th = np.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def rot_y(deg):
    return rot_axis([0, 1, 0], deg)


def rot_angle_deg(Ra, Rb):
    M = np.asarray(Ra) @ np.asarray(Rb).T
    c = np.clip((np.trace(M) - 1) / 2, -1, 1)
    return float(np.degrees(np.arccos(c)))


# Y-up (glTF) -> Z-up file convention (Blender-like): up +Y -> +Z, face +Z -> -Y
YUP_TO_ZUP = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


class Noise3:
    """Band-limited smooth 3D noise: a sum of random plane waves, ~unit std."""

    def __init__(self, seed, wl_min=0.006, wl_max=0.06, n=32):
        r = np.random.default_rng(seed)
        self.k = unit(r.normal(size=(n, 3))) * (2 * np.pi / np.exp(r.uniform(np.log(wl_min), np.log(wl_max), n)))[:, None]
        self.ph = r.uniform(0, 2 * np.pi, n)
        self.a = r.uniform(0.5, 1.0, n)
        self.norm = np.sqrt(0.5 * (self.a ** 2).sum())

    def __call__(self, X):
        X = np.asarray(X, np.float64)
        out = np.zeros(len(X))
        for k, ph, a in zip(self.k, self.ph, self.a):
            out += a * np.sin(X @ k + ph)
        return out / self.norm


# ----------------------------------------------------------------------------- radial ray cast
def radial_cast(V, F, origin, dirs, mode='outer', chunk=400000):
    """Exact hits of rays origin + t*dirs (t > 0) with triangle mesh (V, F).

    All rays share one origin, so every ray is assigned to a cube-map face by its dominant axis and
    triangles are gnomonically projected onto that face plane (great circles -> straight lines, so the
    projected triangle is exact). Candidate triangles come from a uniform bin grid on the face.
    Returns (t, face): t (n,) distance of the outermost ('outer') or innermost ('inner') hit, NaN when
    the ray misses; face (n,) triangle index or -1.
    """
    V = np.asarray(V, np.float64); F = np.asarray(F, np.int64)
    P = V - np.asarray(origin, np.float64)
    D = unit(dirs).reshape(-1, 3)
    n = len(D)
    best_t = np.full(n, np.nan); best_f = np.full(n, -1, np.int64)
    A = P[F[:, 0]]; B = P[F[:, 1]]; C = P[F[:, 2]]
    Nf = np.cross(B - A, C - A)
    nA = (Nf * A).sum(1)
    rn = np.linalg.norm(P, axis=1)
    main = np.argmax(np.abs(D), 1)
    sgn_main = np.sign(D[np.arange(n), main])
    for ax in range(3):
        a, b = [k for k in range(3) if k != ax]
        for sg in (1.0, -1.0):
            q = np.nonzero((main == ax) & (sgn_main == sg))[0]
            if not len(q):
                continue
            pm = sg * P[:, ax]
            vok = pm > 0.05 * rn
            ti = np.nonzero(vok[F].all(1))[0]
            if not len(ti):
                continue
            with np.errstate(divide='ignore', invalid='ignore'):
                U = np.where(vok, P[:, a] / pm, 0.0); W = np.where(vok, P[:, b] / pm, 0.0)
            tu = U[F[ti]]; tw = W[F[ti]]
            umin, umax = tu.min(1), tu.max(1); wmin, wmax = tw.min(1), tw.max(1)
            keep = (umax >= -1.02) & (umin <= 1.02) & (wmax >= -1.02) & (wmin <= 1.02)
            ti, tu, tw = ti[keep], tu[keep], tw[keep]
            umin, umax, wmin, wmax = umin[keep], umax[keep], wmin[keep], wmax[keep]
            if not len(ti):
                continue
            size = float(np.median(np.maximum(umax - umin, wmax - wmin)))
            nb = int(np.clip(2.0 / max(2.5 * size, 1e-4), 4, 2048))

            def binof(x):
                return np.clip(np.floor((x + 1.0) * 0.5 * nb).astype(np.int64), 0, nb - 1)
            bu0, bu1, bw0, bw1 = binof(umin), binof(umax), binof(wmin), binof(wmax)
            wid = bu1 - bu0 + 1
            cnt = wid * (bw1 - bw0 + 1)
            rep = np.repeat(np.arange(len(ti)), cnt)
            loc = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
            pb = (bu0[rep] + loc % wid[rep]) * nb + (bw0[rep] + loc // wid[rep])
            order = np.argsort(pb, kind='stable')
            pb = pb[order]; ptri = rep[order]
            qd = D[q]
            qu = qd[:, a] / (sg * qd[:, ax]); qw = qd[:, b] / (sg * qd[:, ax])
            qb = binof(qu) * nb + binof(qw)
            s0 = np.searchsorted(pb, qb, 'left'); s1 = np.searchsorted(pb, qb, 'right')
            qc = s1 - s0
            # process in chunks of candidate pairs
            qstart = 0
            while qstart < len(q):
                csum = np.cumsum(qc[qstart:])
                qend = qstart + int(np.searchsorted(csum, chunk, 'right'))
                qend = max(qend, qstart + 1)
                sl = slice(qstart, qend)
                c = qc[sl]
                qrep = np.repeat(np.arange(qstart, qend), c)
                lo = np.arange(c.sum()) - np.repeat(np.cumsum(c) - c, c)
                cand = ptri[np.repeat(s0[sl], c) + lo]
                u0, u1, u2 = tu[cand, 0], tu[cand, 1], tu[cand, 2]
                w0, w1, w2 = tw[cand, 0], tw[cand, 1], tw[cand, 2]
                pu, pw = qu[qrep], qw[qrep]
                det = (u1 - u0) * (w2 - w0) - (u2 - u0) * (w1 - w0)
                okd = np.abs(det) > 1e-14
                det = np.where(okd, det, 1.0)
                l1 = ((pu - u0) * (w2 - w0) - (u2 - u0) * (pw - w0)) / det
                l2 = ((u1 - u0) * (pw - w0) - (pu - u0) * (w1 - w0)) / det
                eps = 1e-9
                ins = okd & (l1 >= -eps) & (l2 >= -eps) & (l1 + l2 <= 1 + eps)
                if ins.any():
                    qi = q[qrep[ins]]; fi = ti[cand[ins]]
                    den = (Nf[fi] * D[qi]).sum(1)
                    with np.errstate(divide='ignore', invalid='ignore'):
                        t = nA[fi] / den
                    good = np.isfinite(t) & (t > 1e-9)
                    qi, fi, t = qi[good], fi[good], t[good]
                    if len(t):
                        o = np.lexsort((t if mode == 'outer' else -t, qi))
                        qi, fi, t = qi[o], fi[o], t[o]
                        last = np.r_[qi[1:] != qi[:-1], True]
                        for qq, ff, tt in ((qi[last], fi[last], t[last]),):
                            cur = best_t[qq]
                            better = np.isnan(cur) | ((tt > cur) if mode == 'outer' else (tt < cur))
                            best_t[qq[better]] = tt[better]; best_f[qq[better]] = ff[better]
                qstart = qend
    return best_t, best_f


# ----------------------------------------------------------------------------- surface nets
def surface_nets(Fg, origin, h):
    """Naive surface nets on a signed distance grid Fg (negative inside), grid point (i,j,k) at
    origin + h*(i,j,k). The outermost grid layer must be positive. Returns (V (m,3), T (k,3)) with
    outward-facing triangles."""
    Fg = np.asarray(Fg, np.float32)
    s = Fg < 0
    nx, ny, nz = s.shape
    # active cells: mixed corner signs
    any_in = np.zeros((nx - 1, ny - 1, nz - 1), bool)
    all_in = np.ones((nx - 1, ny - 1, nz - 1), bool)
    for di in (0, 1):
        for dj in (0, 1):
            for dk in (0, 1):
                c = s[di:nx - 1 + di, dj:ny - 1 + dj, dk:nz - 1 + dk]
                any_in |= c; all_in &= c
    act = any_in & ~all_in
    del any_in, all_in
    ci, cj, ck = np.nonzero(act)
    del act
    lin = (ci * (ny - 1) + cj) * (nz - 1) + ck            # sorted (C order)
    acc = np.zeros((len(ci), 3)); cnt = np.zeros(len(ci))
    corners = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    fv = [Fg[ci + c[0], cj + c[1], ck + c[2]].astype(np.float64) for c in corners]
    for e0, e1 in edges:
        f0, f1 = fv[e0], fv[e1]
        x = (f0 < 0) != (f1 < 0)
        t = np.where(x, f0 / np.where(x, f0 - f1, 1.0), 0.0)
        p = np.array(corners[e0], np.float64)[None] + t[:, None] * (np.array(corners[e1]) - np.array(corners[e0]))[None]
        acc += p * x[:, None]; cnt += x
    V = (np.stack([ci, cj, ck], 1) + acc / np.maximum(cnt, 1)[:, None]) * h + np.asarray(origin, np.float64)

    def cell(i, j, k):
        return np.searchsorted(lin, (i * (ny - 1) + j) * (nz - 1) + k)
    quads = []
    # x edges
    i, j, k = np.nonzero(s[:-1] != s[1:])
    inside_low = s[i, j, k]
    q = np.stack([cell(i, j - 1, k - 1), cell(i, j, k - 1), cell(i, j, k), cell(i, j - 1, k)], 1)
    q[~inside_low] = q[~inside_low][:, ::-1]
    quads.append(q)
    i, j, k = np.nonzero(s[:, :-1] != s[:, 1:])
    inside_low = s[i, j, k]
    q = np.stack([cell(i - 1, j, k - 1), cell(i - 1, j, k), cell(i, j, k), cell(i, j, k - 1)], 1)
    q[~inside_low] = q[~inside_low][:, ::-1]
    quads.append(q)
    i, j, k = np.nonzero(s[:, :, :-1] != s[:, :, 1:])
    inside_low = s[i, j, k]
    q = np.stack([cell(i - 1, j - 1, k), cell(i, j - 1, k), cell(i, j, k), cell(i - 1, j, k)], 1)
    q[~inside_low] = q[~inside_low][:, ::-1]
    quads.append(q)
    Q = np.concatenate(quads)
    # split along the shorter diagonal
    d02 = np.linalg.norm(V[Q[:, 0]] - V[Q[:, 2]], axis=1)
    d13 = np.linalg.norm(V[Q[:, 1]] - V[Q[:, 3]], axis=1)
    a = d02 <= d13
    T = np.concatenate([
        np.where(a[:, None], Q[:, [0, 1, 2]], Q[:, [0, 1, 3]]),
        np.where(a[:, None], Q[:, [0, 2, 3]], Q[:, [1, 2, 3]]),
    ])
    return V, T.astype(np.int64)


def vertex_adjacency(n, T):
    import scipy.sparse as sp
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    return A


def taubin(V, T, iters=3, lam=0.5, mu=-0.53, A=None):
    import scipy.sparse as sp
    A = vertex_adjacency(len(V), T) if A is None else A
    deg = np.asarray(A.sum(1)).ravel()
    Dinv = sp.diags(1.0 / np.maximum(deg, 1))
    M = Dinv @ A
    V = V.copy()
    for _ in range(iters):
        V = V + lam * (M @ V - V)
        V = V + mu * (M @ V - V)
    return V


def vertex_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return unit(N)


def largest_component_faces(nv, T):
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    A = vertex_adjacency(nv, T)
    ncomp, lab = connected_components(A, directed=False)
    if ncomp == 1:
        return T, 1
    fl = lab[T[:, 0]]
    big = np.bincount(fl).argmax()
    return T[fl == big], ncomp


def compact(V, T):
    used = np.unique(T)
    remap = -np.ones(len(V), np.int64); remap[used] = np.arange(len(used))
    return V[used], remap[T], used


# ----------------------------------------------------------------------------- GLB writer
class _Buf:
    def __init__(self):
        self.data = bytearray(); self.views = []; self.accessors = []

    def view(self, raw, target=None):
        while len(self.data) % 4:
            self.data.append(0)
        off = len(self.data); self.data += raw
        v = {'buffer': 0, 'byteOffset': off, 'byteLength': len(raw)}
        if target:
            v['target'] = target
        self.views.append(v)
        return len(self.views) - 1

    def accessor(self, arr, ctype, atype, target=None, minmax=False, normalized=False):
        arr = np.ascontiguousarray(arr)
        vi = self.view(arr.tobytes(), target)
        acc = {'bufferView': vi, 'componentType': ctype, 'count': int(arr.shape[0]), 'type': atype}
        if normalized:
            acc['normalized'] = True
        if minmax:
            a2 = arr.reshape(arr.shape[0], -1)
            acc['min'] = [float(x) for x in a2.min(0)]; acc['max'] = [float(x) for x in a2.max(0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def write_glb(path, prims, images=(), materials=None, generator='rl-synth'):
    """prims: list of dicts {name, P (n,3), N (n,3)|None, UV (n,2)|None, COL (n,3 or 4)|None (linear
    float), T (k,3), material (int)}; each prim becomes its own mesh + node.
    images: list of (bytes, mimeType). materials: list of glTF material dicts (texture indices refer to
    images in order: texture i -> image i)."""
    buf = _Buf()
    meshes, nodes = [], []
    for p in prims:
        attrs = {}
        attrs['POSITION'] = buf.accessor(np.asarray(p['P'], np.float32), 5126, 'VEC3', 34962, minmax=True)
        if p.get('N') is not None:
            attrs['NORMAL'] = buf.accessor(np.asarray(p['N'], np.float32), 5126, 'VEC3', 34962)
        if p.get('UV') is not None:
            attrs['TEXCOORD_0'] = buf.accessor(np.asarray(p['UV'], np.float32), 5126, 'VEC2', 34962)
        if p.get('COL') is not None:
            col = np.asarray(p['COL'], np.float32)
            attrs['COLOR_0'] = buf.accessor(col, 5126, 'VEC3' if col.shape[1] == 3 else 'VEC4', 34962)
        idx = buf.accessor(np.asarray(p['T'], np.uint32).reshape(-1), 5125, 'SCALAR', 34963)
        prim = {'attributes': attrs, 'indices': idx, 'mode': 4}
        if p.get('material') is not None:
            prim['material'] = int(p['material'])
        meshes.append({'name': p.get('name', 'mesh'), 'primitives': [prim]})
        nodes.append({'name': p.get('name', 'mesh'), 'mesh': len(meshes) - 1})
    img_json, tex_json = [], []
    for raw, mime in images:
        vi = buf.view(raw)
        img_json.append({'bufferView': vi, 'mimeType': mime})
        tex_json.append({'source': len(img_json) - 1, 'sampler': 0})
    g = {'asset': {'version': '2.0', 'generator': generator},
         'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}],
         'nodes': nodes, 'meshes': meshes,
         'accessors': buf.accessors, 'bufferViews': buf.views,
         'buffers': [{'byteLength': 0}]}
    if materials:
        g['materials'] = materials
    if img_json:
        g['images'] = img_json; g['textures'] = tex_json
        g['samplers'] = [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}]
    while len(buf.data) % 4:
        buf.data.append(0)
    g['buffers'][0]['byteLength'] = len(buf.data)
    js = json.dumps(g, separators=(',', ':')).encode('utf-8')
    while len(js) % 4:
        js += b' '
    total = 12 + 8 + len(js) + 8 + len(buf.data)
    with open(path, 'wb') as f:
        f.write(struct.pack('<4sII', b'glTF', 2, total))
        f.write(struct.pack('<I4s', len(js), b'JSON')); f.write(js)
        f.write(struct.pack('<I4s', len(buf.data), b'BIN\x00')); f.write(bytes(buf.data))
    return total


def png_bytes(img, fmt='PNG', quality=92):
    from PIL import Image
    im = Image.fromarray(np.asarray(img, np.uint8))
    b = io.BytesIO()
    if fmt == 'JPEG':
        im.save(b, 'JPEG', quality=quality)
    else:
        im.save(b, 'PNG', compress_level=6)
    return b.getvalue()
