"""The RL head module as a reference surface for hair and beard generation.

Loads build/v1/rl_head_<sex>.npz (skin geometry in game space) and
build/v1/rl_head_<sex>.glb (morph targets, skin weights, skeleton), and offers
the queries the generators need:

  * head frame: cranium sphere centre C / radius, eye mid point, Head joint,
    spherical (lon, lat) <-> direction helpers. lon 0 = face (+Z),
    lon +90 = the character's LEFT (+X), lon 180 = back; lat +90 = top (+Y).
  * MPFB vertex groups (scalp, ears, lips) mapped onto head-skin vertices.
  * ray casting from C onto the skin (outermost hit), closest point binding
    (triangle + barycentrics), signed distance (+ outside) with optional
    morph deltas applied to the skin.
  * morph deltas of the skin primitive by target name (dense float64).

Game space: metres, Y up, the face looks toward +Z.
"""
import os, re, ast, functools
import numpy as np
import trimesh

import rlglb

import paths

RL = paths.RL_ROOT                       # .local/rl-heads (or $RL_HEADS_ROOT)
BUILD_V1 = paths.HEADS
MPFB_GROUPS = paths.MPFB_GROUPS


@functools.lru_cache(None)
def mpfb_groups():
    """{name: np.array(vertex ids)} for the MPFB base-mesh extra groups, parsed
    without executing the file."""
    out = {}
    pat = re.compile(r'vertex_group_information\["basemesh"\]\["([A-Za-z_\-]+)"\]\s*=\s*(\[[^\]]*\])')
    txt = open(MPFB_GROUPS, encoding='utf-8').read()
    for m in pat.finditer(txt):
        out[m.group(1)] = np.array(ast.literal_eval(m.group(2)), np.int64)
    return out


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def lonlat_dir(lon, lat):
    """Unit direction(s) for lon/lat in degrees (lon 0 = +Z face, +90 = +X left)."""
    lo = np.radians(np.asarray(lon, np.float64)); la = np.radians(np.asarray(lat, np.float64))
    return np.stack([np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)], -1)


def dir_lonlat(d):
    d = unit(d)
    lon = np.degrees(np.arctan2(d[..., 0], d[..., 2]))
    lat = np.degrees(np.arcsin(np.clip(d[..., 1], -1, 1)))
    return lon, lat


def tri_normals(P, T):
    return np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])


def vertex_normals(P, T, weld=None):
    fn = tri_normals(P, T)
    key = np.arange(len(P)) if weld is None else weld
    acc = np.zeros((int(key.max()) + 1, 3))
    for k in range(3):
        np.add.at(acc, key[T[:, k]], fn)
    return unit(acc)[key]


def barycentric(X, A, B, C):
    v0, v1, v2 = B - A, C - A, X - A
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-20)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    b = np.stack([1 - v - w, v, w], 1)
    b = np.clip(b, 0, 1)
    return b / b.sum(1, keepdims=True)


class Head:
    def __init__(self, sex, build_dir=BUILD_V1):
        self.sex = sex
        self.npz_path = os.path.join(build_dir, f'rl_head_{sex}.npz')
        self.glb_path = os.path.join(build_dir, f'rl_head_{sex}.glb')
        d = np.load(self.npz_path)
        self.P = d['SP'].astype(np.float64)
        self.T = d['ST'].astype(np.int64)
        self.Sv = d['Sv'].astype(np.int64)
        self.VG = d['VG'].astype(np.float64)
        self.eyes = d['eyes'].astype(np.float64)
        # welded normals (UV splits share a position id)
        q = np.round(self.P / 1e-6).astype(np.int64)
        _, self.weld = np.unique(q, axis=0, return_inverse=True)
        self.weld = self.weld.ravel()
        self.N = vertex_normals(self.P, self.T, self.weld)
        self.mesh = trimesh.Trimesh(self.P, self.T, process=False)
        self._boundary()
        self._read_glb()
        self._groups()
        self._frame()

    def _boundary(self):
        """Open-rim vertices of the skin (the neck seam): edges used by one triangle,
        counted on welded positions so UV splits do not count as borders."""
        Tw = self.weld[self.T]
        e = np.sort(np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]), axis=1)
        u, c = np.unique(e, axis=0, return_counts=True)
        bw = np.unique(u[c == 1].ravel())
        self.rim = np.isin(self.weld, bw)
        self.rim_y = float(self.P[self.rim, 1].max()) if self.rim.any() else -1e9

    # ------------------------------------------------------------------ glb
    def _read_glb(self):
        g, b = rlglb.read(self.glb_path)
        self.gltf, self.blob = g, b
        # the skin is primitive 0 of the highest LOD mesh (rl_head_lod0; older builds: rl_head)
        names = [m.get('name') for m in g['meshes']]
        mi = names.index('rl_head_lod0') if 'rl_head_lod0' in names else (names.index('rl_head') if 'rl_head' in names else 0)
        self.mesh_index = mi
        mesh = g['meshes'][mi]
        self.target_names = list(mesh['extras']['targetNames'])
        prim = mesh['primitives'][0]
        n = len(self.P)
        assert g['accessors'][prim['attributes']['POSITION']]['count'] == n, 'npz/glb skin vertex mismatch'
        Pg = rlglb.accessor(g, b, prim['attributes']['POSITION'])
        self.glb_pos_err = float(np.abs(Pg - self.P).max())
        self.deltas = {}
        self.ndeltas = {}
        for name, t in zip(self.target_names, prim['targets']):
            self.deltas[name] = rlglb.accessor(g, b, t['POSITION'])
            if 'NORMAL' in t:
                self.ndeltas[name] = rlglb.accessor(g, b, t['NORMAL'])
        J = rlglb.accessor(g, b, prim['attributes']['JOINTS_0'], normalize=False).astype(np.int64)
        W = rlglb.accessor(g, b, prim['attributes']['WEIGHTS_0'])
        self.skin_joints = [g['nodes'][j]['name'] for j in g['skins'][0]['joints']]
        Wd = np.zeros((n, len(self.skin_joints)))
        for k in range(4):
            np.add.at(Wd, (np.arange(n), J[:, k]), W[:, k])
        self.W = Wd / np.maximum(Wd.sum(1, keepdims=True), 1e-9)
        self.ibm_flat = rlglb.accessor(g, b, g['skins'][0]['inverseBindMatrices'])  # (3, 16) glTF layout
        self.G = rlglb.globals_of(g)
        self.node_index = {nd.get('name'): i for i, nd in enumerate(g['nodes'])}
        self.head_G = self.G[self.node_index['Head']]

    def id_names(self):
        return [n for n in self.target_names if n.startswith('id_')]

    def delta(self, name):
        return self.deltas[name]

    def mixed_delta(self, weights):
        D = np.zeros_like(self.P)
        for nm, w in weights.items():
            if w:
                D += w * self.deltas[nm]
        return D

    # --------------------------------------------------------------- groups
    def _groups(self):
        groups = mpfb_groups()
        self.vgroups = {}
        for name in ('scalp', 'ears', 'lips'):
            m = np.zeros(len(self.P), bool)
            src = self.Sv >= 0
            m[src] = np.isin(self.Sv[src], groups[name])
            self.vgroups[name] = m
        # mouth interior (inner lips / mouth bag): mouth-region faces hidden behind other
        # skin seen from the front. Used to label clearance results: open-mouth shapes
        # stretch it forward, so hair in front of the mouth can measure 'inside' it.
        lips = self.P[self.vgroups['lips']]
        tc = self.P[self.T].mean(1); tn = unit(self.N[self.T].mean(1))
        reg = (np.abs(tc[:, 0]) < np.abs(lips[:, 0]).max() + 0.006) & (tc[:, 1] > lips[:, 1].min() - 0.012) &               (tc[:, 1] < lips[:, 1].max() + 0.008) & (tc[:, 2] > lips[:, 2].max() - 0.04)
        # interior = mouth-region faces hidden behind other skin when seen from the front
        cand = np.nonzero(reg)[0]
        hidden = np.zeros(len(self.T), bool)
        if len(cand):
            o = tc[cand] + np.array([0, 0, 0.0008])
            hit = self.mesh.ray.intersects_any(o, np.tile([0.0, 0.0, 1.0], (len(cand), 1)))
            hidden[cand] = hit | (tn[cand, 2] < -0.3)
        self.mouth_interior = hidden
        self.T_clear = self.T[~self.mouth_interior]
        Tw = self.weld[self.T_clear]
        e = np.sort(np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]), axis=1)
        u, c = np.unique(e, axis=0, return_counts=True)
        self.rim_clear = np.isin(self.weld, np.unique(u[c == 1].ravel()))
        ear_tri = self.vgroups['ears'][self.T].any(1)
        self.T_noear = self.T[~ear_tri]
        self.mesh_noear = trimesh.Trimesh(self.P, self.T_noear, process=False)

    # ---------------------------------------------------------------- frame
    def _frame(self):
        sc = self.vgroups['scalp']
        X = self.P[sc]
        # algebraic sphere fit to the scalp vertices
        A = np.c_[2 * X, np.ones(len(X))]
        f = (X * X).sum(1)
        sol, *_ = np.linalg.lstsq(A, f, rcond=None)
        c = sol[:3]
        r = np.sqrt(sol[3] + c @ c)
        c[0] = 0.0
        self.C = c
        self.R = float(r)
        self.eye_mid = self.eyes.mean(0) if len(self.eyes) else c + [0, -0.03, 0.08]
        self.head_joint = self.head_G[:3, 3].copy()
        sp = self.P[sc]
        self.scalp_top = sp[np.argmax(sp[:, 1])]
        # scalp-only signed-distance surface for the sphere radius check
        self.lonlat_scalp = dir_lonlat(sp - self.C)

    def frame_point(self, lon, lat, height=0.0, surface='noear'):
        """Skin point (outermost hit) in the lon/lat direction from C, raised by `height` along the normal."""
        dirs = lonlat_dir(np.atleast_1d(lon), np.atleast_1d(lat)).reshape(-1, 3)
        P, N, ok = self.raycast(np.repeat(self.C[None], len(dirs), 0), dirs, surface)
        return P + N * np.reshape(height, (-1, 1)), N, ok

    # ----------------------------------------------------------- geometry
    def raycast(self, origins, dirs, surface='noear', outermost=True):
        """Ray hits on the skin. Returns (points, interpolated normals, ok mask)."""
        mesh = self.mesh_noear if surface == 'noear' else self.mesh
        dirs = unit(dirs)
        locs, ray_idx, tri_idx = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
        n = len(origins)
        P = origins + dirs * self.R  # fallback
        N = dirs.copy()
        ok = np.zeros(n, bool)
        if len(locs):
            t = ((locs - origins[ray_idx]) * dirs[ray_idx]).sum(1)
            best = {}
            for k in range(len(t)):
                r = ray_idx[k]
                if t[k] <= 0:
                    continue
                if r not in best or (t[k] > t[best[r]] if outermost else t[k] < t[best[r]]):
                    best[r] = k
            for r, k in best.items():
                P[r] = locs[k]; ok[r] = True
            if best:
                rs = np.array(list(best.keys())); ks = np.array(list(best.values()))
                tri = mesh.faces[tri_idx[ks]]
                bc = barycentric(locs[ks], self.P[tri[:, 0]], self.P[tri[:, 1]], self.P[tri[:, 2]])
                N[rs] = unit((self.N[tri] * bc[:, :, None]).sum(1))
        return P, N, ok

    def closest(self, X, P=None):
        """Closest point on the (optionally morphed) skin: point, distance, triangle id, barycentrics."""
        X = np.asarray(X, np.float64)
        mesh = self.mesh if P is None else trimesh.Trimesh(P, self.T, process=False)
        cp, dist, tri = trimesh.proximity.closest_point(mesh, X)
        Pv = self.P if P is None else P
        t = self.T[tri]
        bc = barycentric(cp, Pv[t[:, 0]], Pv[t[:, 1]], Pv[t[:, 2]])
        return cp, dist, tri, bc

    def signed(self, X, D=None, mesh=None, with_rim=False, T=None):
        """Signed distance (+ outside) of X to the skin (+ optional per-vertex skin delta D).
        Sign from the barycentric-interpolated vertex normal at the closest point.
        Points whose closest point lies on the open neck rim (beyond the head skin,
        e.g. long tendrils hanging below it) count as outside (+distance);
        with_rim=True also returns that mask."""
        X = np.asarray(X, np.float64)
        P = self.P if D is None else self.P + D
        Tm = self.T if T is None else T
        if mesh is None:
            mesh = self.mesh if (D is None and T is None) else trimesh.Trimesh(P, Tm, process=False)
        cp, dist, tri = trimesh.proximity.closest_point(mesh, X)
        t = Tm[tri]
        bc = barycentric(cp, P[t[:, 0]], P[t[:, 1]], P[t[:, 2]])
        Nv = self.N if D is None else vertex_normals(P, self.T, self.weld)
        n = unit((Nv[t] * bc[:, :, None]).sum(1))
        s = np.sign(((X - cp) * n).sum(1))
        s[s == 0] = 1
        # closest point on a rim edge: barycentric weight of the rim corners ~ 1
        rimw = (bc * self.rim[t]).sum(1)
        on_rim = (rimw > 0.97) & (X[:, 1] < cp[:, 1] + 0.002)
        if T is not None and T is self.T_clear:
            # the clearance surface has a hole where the mouth interior was cut out:
            # points nearest its edge are in front of the mouth, i.e. outside
            on_rim |= ((bc * self.rim_clear[t]).sum(1) > 0.97) & ~self.rim[t].any(1)
        s[on_rim] = 1
        if with_rim:
            return s * dist, cp, n, on_rim
        return s * dist, cp, n

    def push_out(self, X, margin, iters=3):
        """Move points that are closer than `margin` (or inside) to `margin` along the normal."""
        X = np.array(X, np.float64)
        for _ in range(iters):
            sd, cp, n = self.signed(X)
            bad = sd < margin
            if not bad.any():
                break
            X[bad] = cp[bad] + n[bad] * margin
        return X

    def bind(self, X, no_ears=False):
        """Surface binding of points: dict(tv (corner vertex ids), bc, dist, cp).
        no_ears=True binds to the skin without the ears (hair belongs to the scalp:
        an ear shape must not drag hair along; clearance still tests the ears)."""
        X = np.asarray(X, np.float64)
        if no_ears:
            cp, dist, tri = trimesh.proximity.closest_point(self.mesh_noear, X)
            tv = self.T_noear[tri]
        else:
            cp, dist, tri = trimesh.proximity.closest_point(self.mesh, X)
            tv = self.T[tri]
        bc = barycentric(cp, self.P[tv[:, 0]], self.P[tv[:, 1]], self.P[tv[:, 2]])
        return {'tv': tv, 'bc': bc, 'dist': dist, 'cp': cp}

    def bind_split(self, X, side, tri_side):
        """Bind each point only to triangles of its own side (tri_side[t] == side[i]),
        e.g. upper-lip hair to skin above the mouth line, chin hair below it."""
        X = np.asarray(X, np.float64)
        out = {'tv': np.zeros((len(X), 3), np.int64), 'bc': np.zeros((len(X), 3)), 'dist': np.zeros(len(X)),
               'cp': np.zeros((len(X), 3))}
        for sv in np.unique(side):
            sel = side == sv
            T = self.T if sv < 0 else self.T[tri_side == sv]      # side -1: unrestricted
            m = trimesh.Trimesh(self.P, T, process=False)
            cp, dist, tri = trimesh.proximity.closest_point(m, X[sel])
            tv = T[tri]
            out['tv'][sel] = tv; out['dist'][sel] = dist; out['cp'][sel] = cp
            out['bc'][sel] = barycentric(cp, self.P[tv[:, 0]], self.P[tv[:, 1]], self.P[tv[:, 2]])
        return out

    def bound_delta(self, binding, D):
        return (D[binding['tv']] * binding['bc'][:, :, None]).sum(1)

    def bound_weights(self, binding):
        return (self.W[binding['tv']] * binding['bc'][:, :, None]).sum(1)

    def bound_normal(self, binding):
        return unit((self.N[binding['tv']] * binding['bc'][:, :, None]).sum(1))
