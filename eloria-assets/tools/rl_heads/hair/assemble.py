"""Shared output stage for hair and beard modules: surface binding, morph
transfer, clearance checks, vertex colours and GLB writing (via scripts/glbw.py).

Morph transfer (per target, per vertex):
    d_own  = barycentric delta of the closest head-skin point (bound at rest)
    d_root = the same for the lock's root point on the scalp
    w      = 1 within follow_mm of the skin, smoothstep down to 0 at follow_mm + fade_mm
    d      = w * d_own + (1 - w) * d_root            (locks move rigidly with their root)
    keep-clear: if the skin under a vertex would overtake it (normal component of
    d_own minus the vertex's rest clearance), the shortfall is added along the skin
    normal with a soft max, so big cranium shapes (id_brow_ridge_*) never swallow hair.
"""
import os, json, math, hashlib
import numpy as np
from scipy.spatial import cKDTree
import trimesh

import headref
from headref import unit
import rlglb
import glbwriter as glbw  # vendored copy of the RL head build writer


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------- binding
class Binding:
    """Rest binding of a vertex set to the head skin + per-vertex lock roots."""

    def __init__(self, head, P, root_pts, follow=0.015, fade=0.015, T=None, stretch=0.5, no_ears=True):
        self.head = head
        self.P = P
        self.v = head.bind(P, no_ears=no_ears)
        sd, _, _, rim = head.signed(P, with_rim=True)
        self.sd = sd
        self.rim = rim
        self.dist = self.v['dist']
        self.n = head.bound_normal(self.v)
        self.r = head.bind(root_pts, no_ears=no_ears)
        self.follow, self.fade, self.stretch = follow, fade, stretch
        self.adj = adjacency(T, len(P)) if T is not None else None
        self.force = None                   # optional per-vertex minimum follow weight

    def weight(self, d_own, d_root):
        """Follow weight: 1 within follow (+ stretch x the local skin/root disagreement),
        smoothstep to 0 over fade. For the usual few-mm identity shapes this is the plain
        follow/fade rule; for cranium-wide shapes the hair near the skull follows it."""
        grow = self.stretch * np.linalg.norm(d_own - d_root, axis=1)
        w = 1.0 - smoothstep((self.dist - self.follow - grow) / np.maximum(self.fade, 1e-6))
        if self.force is not None:
            w = np.maximum(w, self.force)
        return w

    def delta(self, D, keep_clear=True, margin=0.0025, soft=0.002, exact=True):
        d_own = self.head.bound_delta(self.v, D)
        d_root = self.head.bound_delta(self.r, D)
        w = self.weight(d_own, d_root)
        d = w[:, None] * d_own + (1 - w[:, None]) * d_root
        if keep_clear:
            # required normal displacement so the clearance stays >= margin
            out_n = (d_own * self.n).sum(1)
            need = out_n - np.maximum(self.sd - margin, 0.0)
            have = (d * self.n).sum(1)
            short = need - have
            f = lambda x: 0.5 * (x + np.sqrt(x * x + soft * soft))
            add = np.maximum(f(short) - f(-3 * soft), 0.0)
            add = np.where(out_n > 1e-5, add, 0.0)
            d = d + self.n * add[:, None]
        if exact and np.abs(D).max() > 1e-6:
            d = self.exact_clear(D, d, margin)
        return d

    def exact_clear(self, D, d, margin, iters=6):
        """Measure the morphed clearance against the morphed skin and push any vertex
        closer than `margin` out along the morphed normal; the correction is spread
        over mesh neighbours (max-preserving) so locks bend instead of kinking."""
        head = self.head
        mv = np.linalg.norm(D, axis=1)
        moving = mv > 1e-5
        if not moving.any():
            return d
        tree = cKDTree(head.P[moving])
        dd, _ = tree.query(self.P, distance_upper_bound=mv.max() + 0.04)
        cand = np.nonzero(np.isfinite(dd))[0]
        if not len(cand):
            return d
        mesh = trimesh.Trimesh(head.P + D, head.T, process=False)
        # push direction: the morphed normal at the vertex's OWN bound skin point
        # (stable on thin features such as the lips, where the closest point flips)
        Nm = headref.vertex_normals(head.P + D, head.T, head.weld)
        tb = self.v['tv'][cand]
        nb = unit((Nm[tb] * self.v['bc'][cand][:, :, None]).sum(1))
        for _ in range(iters):
            sd, cp, n, rim = head.signed(self.P[cand] + d[cand], D=D, mesh=mesh, with_rim=True)
            bad = (sd < margin + 0.0002) & ~rim
            if not bad.any():
                break
            use = np.where(((n * nb).sum(1) > 0.3)[:, None], n, nb)
            corr = np.zeros_like(d)
            corr[cand[bad]] = use[bad] * (margin + 0.0006 - sd[bad])[:, None]
            if self.adj is not None:
                corr = spread(corr, self.adj, 6)
            d = d + corr
        return d


def headroom(head, P, names, frac=0.5, cap=0.006, no_ears=True):
    """Extra rest clearance per vertex: frac x the summed OUTWARD normal motion of the
    bound skin point over the given shapes (capped). Where several identity shapes can
    push the skin toward the hair at once (brows, cheeks), the hair rests a little
    further out, so stacked shapes stay clear too."""
    b = head.bind(P, no_ears=no_ears)
    n = head.bound_normal(b)
    pot = np.zeros(len(P))
    for nm in names:
        pot += np.maximum((head.bound_delta(b, head.delta(nm)) * n).sum(1), 0.0)
    return np.minimum(pot * frac, cap)


def push_out_var(head, P, margin, iters=6):
    """Push-out with a per-vertex margin (array)."""
    P = np.array(P, np.float64)
    margin = np.broadcast_to(np.asarray(margin, np.float64), (len(P),)).copy()
    for _ in range(iters):
        sd, cp, n = head.signed(P)
        bad = sd < margin
        if not bad.any():
            break
        P[bad] = cp[bad] + n[bad] * margin[bad][:, None]
    return P


def adjacency(T, n):
    from scipy.sparse import coo_matrix
    T = np.asarray(T)
    i = np.concatenate([T[:, 0], T[:, 1], T[:, 2], T[:, 1], T[:, 2], T[:, 0]])
    j = np.concatenate([T[:, 1], T[:, 2], T[:, 0], T[:, 0], T[:, 1], T[:, 2]])
    A = coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    return A, np.maximum(deg, 1)


def spread(c, adj, iters=6, decay=0.85):
    """Max-preserving diffusion of a correction field over the mesh graph."""
    A, deg = adj
    for _ in range(iters):
        avg = (A @ c) / deg[:, None] * decay
        take = np.linalg.norm(avg, axis=1) > np.linalg.norm(c, axis=1)
        c = np.where(take[:, None], avg, c)
    return c


def morph_normals(P, T, N, dP, weld=None):
    """Normal delta for a position delta: geometric change applied to the authored normals."""
    if np.abs(dP).max() < 1e-7:
        return np.zeros_like(N)
    g0 = headref.vertex_normals(P, T, weld)
    g1 = headref.vertex_normals(P + dP, T, weld)
    return unit(N + (g1 - g0)) - N


# ------------------------------------------------------------- clearance
def clearance(head, P, deltas_head, deltas_hair, names, margin=0.002, combos=None):
    """Signed clearance of hair vertices against the (morphed) head skin.

    deltas_head: {name: skin delta}; deltas_hair: {name: hair delta (len(P))}.
    combos: {label: {name: weight}} extra mixed cases.
    Returns a report dict."""
    sd0, _, _, rim0 = head.signed(P, with_rim=True)
    rep = {'marginMM': margin * 1e3, 'surface': 'head skin lod0; deep inside verdicts confirmed by 14 rays (escape = outside); vsMouthInterior: violating verts whose closest face is mouth interior', 'rest': {'minMM': float(sd0[~rim0].min() * 1e3), 'violations': int((sd0[~rim0] < margin).sum()),
                                              'belowNeckRim': int(rim0.sum())}}
    cases = [(n, {n: 1.0}) for n in names]
    for k, v in (combos or {}).items():
        cases.append((k, v))
    worst = []
    tree_all = cKDTree(head.P)
    for label, mix in cases:
        Dh = sum(w * deltas_head[n] for n, w in mix.items())
        Dv = sum(w * deltas_hair[n] for n, w in mix.items())
        mv = np.linalg.norm(Dh, axis=1)
        if mv.max() < 1e-6:
            if np.abs(Dv).max() < 1e-6:
                continue
            # hair-only shape (grooming): test every vertex against the rest skin
            sd, _, _, rim = head.signed(P + Dv, with_rim=True)
            sd = np.where(rim, np.inf, sd)
            worst.append((float(sd.min()), label, int((sd < margin).sum()), 0))
            continue
        # only vertices that could be reached by the moving skin need a test
        moving = mv > 1e-5
        reach = mv.max() + 0.006
        tm = cKDTree(head.P[moving])
        dd, _ = tm.query(P, distance_upper_bound=reach + 0.03)
        cand = np.nonzero(np.isfinite(dd))[0]
        if not len(cand):
            continue
        sd, _, _, rim = head.signed(P[cand] + Dv[cand], D=Dh, with_rim=True)
        sd = np.where(rim, np.inf, sd)
        bad = sd < margin
        # 'inside' verdicts deeper than 0.5 mm are confirmed with rays: a point from
        # which any of 14 rays escapes the morphed head is outside (the normal-sign test
        # is unreliable in front of the eye sockets / mouth, whose skin folds inward)
        deep = np.nonzero(bad & (sd < -0.0005))[0]
        if len(deep):
            mm = trimesh.Trimesh(head.P + Dh, head.T, process=False)
            X = P[cand[deep]] + Dv[cand[deep]]
            dirs = unit(np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1],
                                  [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1], [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1]], float))
            esc = np.zeros(len(deep), bool)
            for dv_ in dirs:
                esc |= ~mm.ray.intersects_any(X + dv_ * 1e-4, np.tile(dv_, (len(X), 1)))
            sd[deep[esc]] = np.inf
            bad = sd < margin
        n_int = 0
        if bad.any():
            # how many of them are measured against the mouth interior (inner lips /
            # mouth bag, which open-mouth shapes stretch forward) rather than the face
            _, _, tri, _ = head.closest(P[cand[bad]] + Dv[cand[bad]], P=head.P + Dh)
            n_int = int(head.mouth_interior[tri].sum())
        worst.append((float(sd.min()), label, int(bad.sum()), n_int))
    worst.sort()
    rep['morphs'] = {'tested': len(cases), 'minMM': (worst[0][0] * 1e3 if worst else None),
                     'violatingCases': [{'case': l, 'minMM': round(m * 1e3, 2), 'verts': b, 'vsMouthInterior': ni}
                                        for m, l, b, ni in worst if b > 0][:20]}
    return rep


def default_combos(names):
    ids = [n for n in names if n.startswith('id_')]
    pos = {n: 1.0 for n in ids if n.endswith('_p')}
    neg = {n: 1.0 for n in ids if n.endswith('_n')}
    rng = np.random.default_rng(5)
    combos = {'all_id_p': pos, 'all_id_n': neg}
    ctrls = sorted({n[:-2] for n in ids})
    for k in range(8):
        mix = {}
        for c in ctrls:
            r = rng.integers(-1, 2)
            if r > 0:
                mix[c + '_p'] = 1.0
            elif r < 0:
                mix[c + '_n'] = 1.0
        combos['random_%d' % k] = mix
    return combos


# ------------------------------------------------------------- colours
def colors_u8(rand, t, ao, detail=None):
    """COLOR_0 = (lock random, position along lock, ao, detail keep-level).
    A = 1 for core geometry; fine detail (flyaway / wisp cards) carries 0.5..0.95:
    the runtime hides a fragment when A < 1 - hair_detail (hair_detail 0..1)."""
    a = np.ones_like(t) if detail is None else detail
    c = np.stack([rand, t, ao, a], 1)
    return np.clip(np.round(c * 255), 0, 255).astype(np.uint8)


# ------------------------------------------------------------- glb
class Writer:
    """Thin layer over glbw.GLB for skinned, morphing LOD meshes."""

    def __init__(self, generator):
        self.g = glbw.GLB()
        self.g.g['asset']['generator'] = generator

    def material(self, name, color, alpha='MASK', cutoff=0.5, double=True, extras=None, roughness=0.65):
        i = self.g.material(name, color, double=double, alpha=alpha, extras=extras)
        m = self.g.g['materials'][i]
        if alpha == 'MASK':
            m['alphaCutoff'] = cutoff
        m['pbrMetallicRoughness']['roughnessFactor'] = roughness
        return i

    def embed_texture(self, mat, png_path):
        g = self.g
        data = open(png_path, 'rb').read()
        bv = g._view(data)
        g.g.setdefault('images', []).append({'bufferView': bv, 'mimeType': 'image/png', 'name': os.path.basename(png_path)})
        g.g.setdefault('samplers', [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}])
        g.g.setdefault('textures', []).append({'sampler': 0, 'source': len(g.g['images']) - 1})
        g.g['materials'][mat]['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(g.g['textures']) - 1}

    def primitive(self, P, N, UV, T, COL, J, W, mat, targets):
        g = self.g
        nv = len(P)
        jcomp = 5121 if J.max() < 256 else 5123
        icomp = 5123 if nv < 65536 else 5125
        pr = {'attributes': {'POSITION': g.accessor(P, 'VEC3', minmax=True, target=34962),
                             'NORMAL': g.accessor(N, 'VEC3', target=34962),
                             'TEXCOORD_0': g.accessor(UV, 'VEC2', target=34962),
                             'COLOR_0': g.accessor(COL, 'VEC4', comp=5121, target=34962, normalized=True),
                             'JOINTS_0': g.accessor(J, 'VEC4', comp=jcomp, target=34962),
                             'WEIGHTS_0': g.accessor(W, 'VEC4', target=34962)},
              'indices': g.accessor(T.reshape(-1), 'SCALAR', comp=icomp, target=34963),
              'material': mat}
        if targets:
            # POSITION-only sparse targets (the runtime keeps base normals for hair);
            # sub-0.05 mm displacements are dropped
            pr['targets'] = [{'POSITION': g.sparse_vec3(np.where(np.abs(dp).max(1, keepdims=True) < 5e-5, 0, dp), eps=1e-9, minmax=True)}
                             for dp, dn in targets]
        return pr

    def mesh(self, name, prims, target_names):
        m = {'name': name, 'primitives': prims}
        if target_names:
            m['extras'] = {'targetNames': list(target_names)}
            m['weights'] = [0.0] * len(target_names)
        self.g.g['meshes'].append(m)
        return len(self.g.g['meshes']) - 1

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return self.g.save(path)


def top4(Wd):
    """Dense weights (n, J) -> JOINTS_0/WEIGHTS_0 (top four, renormalised)."""
    n, J = Wd.shape
    if J <= 4:
        idx = np.tile(np.arange(4), (n, 1)); idx[:, J:] = 0
        W = np.zeros((n, 4)); W[:, :J] = Wd
    else:
        idx = np.argsort(-Wd, axis=1)[:, :4]
        W = np.take_along_axis(Wd, idx, 1)
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
    W[W < 1e-4] = 0
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
    idx = np.where(W > 0, idx, 0)
    return idx.astype(np.uint16), W.astype(np.float32)


def file_sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()
