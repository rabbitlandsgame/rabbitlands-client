"""The RL head as a linear shape model for fitting.

  S(v) = P + sum_j max(v_j, 0) * Dp_j + max(-v_j, 0) * Dn_j     (runtime semantics)

With z = [a_1..a_21, b_1..b_21] (a = max(v,0), b = max(-v,0)) the skin is
exactly linear: S(z) = P + D z, D = [Dp; Dn] of shape (42, n, 3).

Also: anatomical regions per skin vertex (forehead, brow, eyes, nose, cheeks,
mouth, jaw, chin, ears, neck, cranium), landmarks, region weights, a dense
area-uniform surface sample for fast closest-point queries, and the beard
region.
"""
import functools
import numpy as np
from scipy.spatial import cKDTree

import fitcommon
from fitcommon import kdq, control_names, unit
import headref
from headref import Head, vertex_normals, dir_lonlat

REGIONS = ['forehead', 'brow', 'eyes', 'nose', 'cheeks', 'mouth', 'jaw', 'chin', 'ears', 'neck', 'cranium']
FACE_REGIONS = ['forehead', 'brow', 'nose', 'cheeks', 'jaw', 'chin']          # face_rms (reliable, no eyes/lips)
DEFAULT_WEIGHTS = {'forehead': 1.0, 'brow': 0.8, 'eyes': 0.3, 'nose': 1.0, 'cheeks': 1.0, 'mouth': 0.45,
                   'jaw': 1.0, 'chin': 1.0, 'ears': 0.5, 'neck': 0.35, 'cranium': 0.6, 'eyeballs': 0.5}
# controls that act on each region (for gap notes)
REGION_CONTROLS = {
    'forehead': ['brow_ridge'], 'brow': ['brow_height', 'brow_ridge'],
    'eyes': ['eye_size', 'eye_tilt', 'eye_spacing', 'eyelid'],
    'nose': ['nose_width', 'nose_length', 'nose_bridge', 'nose_tip', 'nose_depth'],
    'cheeks': ['cheekbones', 'cheek_fullness'], 'mouth': ['lip_fullness', 'mouth_width', 'cupid_bow'],
    'jaw': ['jaw_width'], 'chin': ['chin_length', 'chin_projection', 'chin_width'], 'ears': ['ear_size'],
    'neck': [], 'cranium': []}
LANDMARK_NAMES = ['eye_l', 'eye_r', 'nose_tip', 'chin', 'mouth', 'ear_l', 'ear_r']
import os as _os
EYE_MATERIALS = tuple(_os.environ.get('RL_FIT_EYE_MATERIALS', 'rl_eye').split(','))


def _neighbors(T, n):
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    return e


def dilate(mask, edges, rings=1):
    m = mask.copy()
    for _ in range(rings):
        nm = m.copy()
        nm[edges[m[edges[:, 0]], 1]] = True
        m = nm
    return m


def closest_on_triangles(X, A, B, C):
    """Closest points on triangles (A,B,C) (row-wise) to X; returns point and barycentrics (Ericson)."""
    ab = B - A; ac = C - A; ap = X - A
    d1 = (ab * ap).sum(1); d2 = (ac * ap).sum(1)
    bp = X - B; d3 = (ab * bp).sum(1); d4 = (ac * bp).sum(1)
    cp = X - C; d5 = (ab * cp).sum(1); d6 = (ac * cp).sum(1)
    vc = d1 * d4 - d3 * d2; vb = d5 * d2 - d1 * d6; va = d3 * d6 - d5 * d4
    n = len(X)
    bary = np.zeros((n, 3))
    done = np.zeros(n, bool)

    def setb(m, b0, b1, b2):
        m = m & ~done
        bary[m, 0] = b0[m] if np.ndim(b0) else b0
        bary[m, 1] = b1[m] if np.ndim(b1) else b1
        bary[m, 2] = b2[m] if np.ndim(b2) else b2
        done[m] = True

    one = np.ones(n); zero = np.zeros(n)
    setb((d1 <= 0) & (d2 <= 0), one, zero, zero)
    setb((d3 >= 0) & (d4 <= d3), zero, one, zero)
    with np.errstate(divide='ignore', invalid='ignore'):
        v = d1 / (d1 - d3)
        setb((vc <= 0) & (d1 >= 0) & (d3 <= 0), 1 - v, v, zero)
        setb((d6 >= 0) & (d5 <= d6), zero, zero, one)
        w = d2 / (d2 - d6)
        setb((vb <= 0) & (d2 >= 0) & (d6 <= 0), 1 - w, zero, w)
        w2 = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        setb((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), zero, 1 - w2, w2)
        den = 1.0 / (va + vb + vc)
        vv = vb * den; ww = vc * den
        setb(np.ones(n, bool), 1 - vv - ww, vv, ww)
    bary = np.nan_to_num(bary)
    P = A * bary[:, :1] + B * bary[:, 1:2] + C * bary[:, 2:3]
    return P, bary


class RLModel:
    def __init__(self, sex, n_surface=120_000, with_eyes=True):
        self.sex = sex
        try:
            self.h = h = Head(sex)
        except Exception as ex:
            raise fitcommon.HeadrefError(f'headref.Head({sex!r}) failed ({ex!r}); the hair scripts (RL/scripts/hair) may be '
                                         'mid-edit - retry in a minute') from ex
        fitcommon.check_head(h)
        self.P = h.P.copy()
        self.T = h.T.copy()
        self.n = len(self.P)
        self.weld = h.weld
        self.names = control_names()
        self.Dp = np.stack([h.deltas[f'id_{c}_p'] for c in self.names])
        self.Dn = np.stack([h.deltas[f'id_{c}_n'] for c in self.names])
        self.D = np.concatenate([self.Dp, self.Dn])            # (42, n, 3)
        self.C = h.C.copy(); self.R = h.R
        self.edges = _neighbors(self.T, self.n)
        # triangles usable for projection: exposed skin only (no mouth bag, eye-socket lining hidden
        # behind the eyeballs: the eyeballs are occluders in the visibility test)
        self._eyes = self._read_eyes() if with_eyes else None
        self.hidden = hidden_faces(h, occluders=None if self._eyes is None else (self._eyes[0], self._eyes[1]))
        self._landmarks()
        self._regions()
        self.tri_valid = ~(self.hidden | h.mouth_interior)
        self.n_skin = self.n
        self.n_tri_skin = len(self.T)
        self.rim = h.rim.copy()
        self.lips_front = h.vgroups['lips'] & (h.N[:, 2] > 0.2)
        self.is_eye = np.zeros(self.n, bool)
        if with_eyes and self._eyes is not None:
            self._append_eyes()
        self.N0 = vertex_normals(self.P, self.T, self.weld)
        self.Tv = self.T[self.tri_valid]
        # open boundary of the projection surface (welded): neck rim, mouth slit (the mouth bag is not
        # part of it), eyelid margins. A reference point whose closest point sits on it lies past the edge
        # (e.g. on a fused, filled lip seam) and is not evidence for the skin there.
        Tw = self.weld[self.Tv]
        e = np.sort(np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]), axis=1)
        u, c = np.unique(e, axis=0, return_counts=True)
        self.open_boundary = np.isin(self.weld, np.unique(u[c == 1].ravel())) & ~self.is_eye
        self.Tv_index = np.nonzero(self.tri_valid)[0]
        # one representative vertex per welded position (model->data terms)
        _, first = np.unique(self.weld, return_index=True)
        rep = np.zeros(self.n, bool); rep[first] = True
        used = np.zeros(self.n, bool); used[self.Tv.ravel()] = True
        self.rep = rep & used & ~(self.is_eye & (self.N0[:, 2] < 0.3))
        self._surface_samples(n_surface)

    def _read_eyes(self):
        """The head GLB's eyeball surfaces (LOD0 rl_eye + rl_cornea primitives) with their id_ morph deltas."""
        import rlglb
        h = self.h
        g, b = h.gltf, h.blob
        mesh = g['meshes'][h.mesh_index]
        Ps, Ts, Ds = [], [], []
        off = 0
        for prim in mesh['primitives']:
            mat = g['materials'][prim['material']].get('name', '') if 'material' in prim else ''
            if mat not in EYE_MATERIALS:
                continue
            P = rlglb.accessor(g, b, prim['attributes']['POSITION'])
            I = rlglb.accessor(g, b, prim['indices'], normalize=False).astype(np.int64).reshape(-1, 3)
            dd = {nm: t for nm, t in zip(h.target_names, prim.get('targets', []))}
            D = np.zeros((2 * len(self.names), len(P), 3))
            for k, c in enumerate(self.names):
                for j, pol in enumerate(('p', 'n')):
                    t = dd.get(f'id_{c}_{pol}')
                    if t is not None and 'POSITION' in t:
                        D[j * len(self.names) + k] = rlglb.accessor(g, b, t['POSITION'])
            Ps.append(P); Ts.append(I + off); Ds.append(D)
            off += len(P)
        if not Ps:
            return None
        return np.concatenate(Ps), np.concatenate(Ts), np.concatenate(Ds, axis=1)

    def _append_eyes(self):
        """Append the eyeballs to the model: a Meshy reference has fused eyeballs, and eye_spacing moves them."""
        EP, ET, ED = self._eyes
        ns = self.n
        q = np.round(EP / 1e-6).astype(np.int64)
        _, ew = np.unique(q, axis=0, return_inverse=True)
        self.P = np.concatenate([self.P, EP])
        self.T = np.concatenate([self.T, ET + ns])
        self.D = np.concatenate([self.D, ED], axis=1)
        self.weld = np.concatenate([self.weld, self.weld.max() + 1 + ew.ravel()])
        self.n = len(self.P)
        ne = len(EP)
        pad = lambda a, v=False: np.concatenate([a, np.full(ne, v, dtype=a.dtype)])
        self.region = pad(self.region, REGIONS.index('eyes'))
        self.region_stat = pad(self.region_stat, REGIONS.index('eyes'))
        self.beard_region = pad(self.beard_region)
        self.beard_parts = {k: pad(v) for k, v in self.beard_parts.items()}
        self.scalp = pad(self.scalp)
        self.exposed = pad(self.exposed, True)
        self.rim = pad(self.rim)
        self.lips_front = pad(self.lips_front)
        self.is_eye = pad(self.is_eye, True)
        # eyeball faces facing backward sit inside the socket: never a projection target
        Ne = vertex_normals(EP, ET, ew.ravel())
        fz = Ne[ET].mean(1)[:, 2]
        self.hidden = np.concatenate([self.hidden, fz < -0.05])
        self.tri_valid = np.concatenate([self.tri_valid, fz >= -0.05])
        self.edges = _neighbors(self.T, self.n)

    # ------------------------------------------------------------ geometry
    def z_of(self, v):
        v = np.asarray(v, np.float64)
        return np.concatenate([np.maximum(v, 0), np.maximum(-v, 0)])

    def v_of(self, z):
        k = len(self.names)
        return z[:k] - z[k:]

    def morph(self, v=None, z=None):
        if z is None:
            if v is None:
                return self.P.copy()
            z = self.z_of(v)
        return self.P + np.tensordot(z, self.D, axes=(0, 0))

    def normals(self, Pv):
        return vertex_normals(Pv, self.T, self.weld)

    # ------------------------------------------------------------ landmarks
    def _landmarks(self):
        h = self.h
        P = self.P
        E = h.eyes
        eL = E[E[:, 0] > 0]; eR = E[E[:, 0] < 0]
        # eyeball centre: sphere fit to each eye's proxy points
        def sphere(X):
            A = np.c_[2 * X, np.ones(len(X))]
            f = (X * X).sum(1)
            s, *_ = np.linalg.lstsq(A, f, rcond=None)
            c = s[:3]; r = np.sqrt(s[3] + c @ c)
            return c, r
        cL, rL = sphere(eL); cR, rR = sphere(eR)
        self.eye_centres = np.array([cL, cR]); self.eye_radius = float((rL + rR) / 2)
        self.eye_front = np.array([eL[np.argmax(eL[:, 2])], eR[np.argmax(eR[:, 2])]])
        mid = np.nonzero(np.abs(P[:, 0]) < 2e-4)[0]
        nose = P[mid[np.argmax(P[mid, 2])]]
        lips = h.vgroups['lips']
        Lp = P[lips]
        front = Lp[:, 2] > np.percentile(Lp[:, 2], 40)
        mouth_c = Lp[front].mean(0)
        mid_l = mid[(P[mid, 1] > Lp[:, 1].min() - 0.002) & (P[mid, 1] < Lp[:, 1].max() + 0.002)]
        mouth = np.array([0.0, mouth_c[1], P[mid_l, 2].max() if len(mid_l) else mouth_c[2]])
        ears = h.vgroups['ears']
        earL = P[ears & (P[:, 0] > 0)]; earR = P[ears & (P[:, 0] < 0)]
        chin_c = mid[(P[mid, 2] > nose[2] - 0.06) & (P[mid, 1] < nose[1] - 0.03)]
        menton = P[chin_c[np.argmin(P[chin_c, 1])]]
        self.lm = {'eye_l': (cL + 0) * 1.0, 'eye_r': cR * 1.0, 'nose_tip': nose, 'chin': menton, 'mouth': mouth,
                   'ear_l': earL.mean(0), 'ear_r': earR.mean(0)}
        self.ear_bottom_y = float(min(earL[:, 1].min(), earR[:, 1].min()))
        self.ear_z = float((earL[:, 2].mean() + earR[:, 2].mean()) / 2)
        self.ipd = float(np.linalg.norm(cL - cR))
        self.top_y = float(P[:, 1].max())
        self.lips_y = (float(Lp[:, 1].min()), float(Lp[:, 1].max()))
        self.mouth_corner_x = float(np.abs(Lp[:, 0]).max())

    def landmark_array(self, names=LANDMARK_NAMES):
        return np.array([self.lm[n] for n in names])

    # ------------------------------------------------------------ regions
    def _regions(self):
        h = self.h; P = self.P
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        ax = np.abs(x)
        u = self.ipd / 0.057
        eL = self.eye_centres[0]
        ex, ey, ez = abs(eL[0]), eL[1], self.eye_front[:, 2].mean()
        nose = self.lm['nose_tip']; ny, nz = nose[1], nose[2]
        my = self.lm['mouth'][1]; mz = self.lm['mouth'][2]
        cy, cz = self.lm['chin'][1], self.lm['chin'][2]
        lon, lat = dir_lonlat(P - self.C)
        alon = np.abs(lon)
        ears = dilate(h.vgroups['ears'], self.edges, 1)
        lips = dilate(h.vgroups['lips'], self.edges, 1)
        mi = np.zeros(self.n, bool); mi[self.T[h.mouth_interior].ravel()] = True
        scalp = h.vgroups['scalp']
        # mandible line in profile: menton -> gonion (just in front of / below the ear lobe)
        zg = self.ear_z + 0.012 * u; yg = self.ear_bottom_y - 0.004 * u
        zc = np.clip(z, zg, cz)
        y_mand = cy + (zc - cz) * (yg - cy) / (zg - cz)
        neck = y < y_mand - 0.002 * u
        # back of the head below the occiput: neck when below the ear bottom
        neck |= (z < zg) & (y < yg + 0.004 * u)
        lab = np.full(self.n, -1)

        def put(mask, name):
            m = mask & (lab < 0)
            lab[m] = REGIONS.index(name)

        put(ears, 'ears')
        put(lips | mi, 'mouth')
        put(neck, 'neck')
        front = z > ez - 0.024 * u
        e_ell = ((ax - ex) / (0.021 * u)) ** 2 + ((y - ey + 0.0015 * u) / (0.0125 * u)) ** 2 < 1
        put(e_ell & front, 'eyes')
        # nose: half width grows from the bridge (between the eyes) to the alae
        t = np.clip((ey - y) / max(ey - (ny - 0.012 * u), 1e-6), 0, 1)
        nhw = (0.008 + 0.0135 * t ** 1.5) * u
        put((ax < nhw) & (y > my + 0.008 * u) & (y < ey + 0.006 * u) & (z > nz - 0.034 * u), 'nose')
        put((y >= ey + 0.006 * u) & (y < ey + 0.027 * u) & (ax < ex + 0.034 * u) & front & (alon < 75), 'brow')
        put((y >= ey + 0.027 * u) & (alon < 62) & ~scalp, 'forehead')
        put(scalp | (y >= ey + 0.02 * u), 'cranium')
        chin_hw = 0.024 * u
        put((y < my - 0.006 * u) & (ax < chin_hw) & (z > cz - 0.03 * u), 'chin')
        put((y < my + 0.003 * u) & (alon < 118), 'jaw')
        put((alon < 105) & (y < ey + 0.006 * u), 'cheeks')
        put(np.ones(self.n, bool), 'cranium')
        self.region = lab
        # statistics labels: eyes and mouth grown by two rings (points over a bulging eyeball or the
        # lip seam that land on neighbouring cheek/brow vertices are not face-shape evidence)
        st = lab.copy()
        for name in ('eyes', 'mouth'):
            g = dilate(lab == REGIONS.index(name), self.edges, 2) & (lab != REGIONS.index('ears'))
            st[g & ~np.isin(lab, [REGIONS.index('eyes'), REGIONS.index('mouth')])] = REGIONS.index(name)
        self.region_stat = st
        # beard region: upper lip, chin, jaw, lower cheeks (below the mouth corner -> ear line), front neck
        upper_lip = (y > self.lips_y[1] - 0.002 * u) & (y < ny - 0.010 * u) & (ax < self.mouth_corner_x + 0.006 * u) & (z > mz - 0.02 * u)
        cheek_low = (lab == REGIONS.index('cheeks')) & (y < my + 0.012 * u + (ax - self.mouth_corner_x).clip(0) * 0.5)
        neck_front = (lab == REGIONS.index('neck')) & (z > zg + 0.005) & (y > cy - 0.05 * u)
        beard = upper_lip | np.isin(lab, [REGIONS.index('chin'), REGIONS.index('jaw')]) | cheek_low | neck_front
        beard &= ~(lab == REGIONS.index('mouth')) | upper_lip
        beard &= ~(lab == REGIONS.index('ears'))
        exposed = np.zeros(self.n, bool)
        exposed[self.T[~(self.hidden | h.mouth_interior)].ravel()] = True
        beard &= exposed
        self.exposed = exposed
        self.beard_region = beard
        self.beard_parts = {'moustache': upper_lip & beard, 'chin': (lab == REGIONS.index('chin')) & beard,
                            'chin_front': (lab == REGIONS.index('chin')) & beard & (h.N[:, 2] > 0.5),
                            'jaw': ((lab == REGIONS.index('jaw')) | cheek_low) & beard, 'neck': neck_front & beard}
        self.scalp = scalp

    def region_weights(self, overrides=None):
        w = dict(DEFAULT_WEIGHTS)
        if overrides:
            w.update({k: float(v) for k, v in overrides.items() if k in w})
        vw = np.array([w[REGIONS[r]] for r in self.region])
        vw[self.is_eye] = w.get('eyeballs', w['eyes'])
        return vw, w

    def region_mask(self, *names):
        ids = [REGIONS.index(n) for n in names]
        return np.isin(self.region, ids)

    # ------------------------------------------------------------ surface sample
    def _surface_samples(self, n):
        rng = np.random.default_rng(7)
        P = self.P; T = self.Tv
        a = 0.5 * np.linalg.norm(np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]), axis=1)
        cdf = np.cumsum(a)
        tri = np.minimum(np.searchsorted(cdf, rng.random(n) * cdf[-1]), len(T) - 1)
        r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
        bary = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
        # also each triangle's centroid so no triangle is missed
        tri = np.concatenate([tri, np.arange(len(T))])
        bary = np.concatenate([bary, np.full((len(T), 3), 1 / 3)])
        self.s_tri = tri; self.s_bary = bary
        self.tri_area = a
        va = np.zeros(self.n)
        for c in range(3):
            np.add.at(va, T[:, c], a / 3)
        # welded duplicates share the area of their position
        acc = np.zeros(self.weld.max() + 1)
        np.add.at(acc, self.weld, va)
        self.vertex_area = np.where(self.rep if hasattr(self, 'rep') else True, acc[self.weld], 0.0)

    class Surface:
        pass

    def surface(self, Pv, Nv=None):
        """Projection helper for a (morphed) skin Pv: KD-tree on the dense sample."""
        s = RLModel.Surface()
        s.P = Pv
        s.N = self.normals(Pv) if Nv is None else Nv
        tv = self.Tv[self.s_tri]
        s.S = (Pv[tv] * self.s_bary[:, :, None]).sum(1)
        s.kd = cKDTree(s.S)
        return s

    def project(self, surf, Y, max_dist=np.inf):
        """Closest points on the skin for Y: dict(tri (index into T), tv (3 vertex ids), bary, p, n, d (signed),
        off (in-plane distance to the clamped point: >0 means past an open boundary))."""
        dist, si = kdq(surf.kd, Y, k=1, distance_upper_bound=max_dist)
        ok = np.isfinite(dist)
        si = np.where(ok, si, 0)
        tl = self.s_tri[si]
        tv = self.Tv[tl]
        A = surf.P[tv[:, 0]]; B = surf.P[tv[:, 1]]; Cc = surf.P[tv[:, 2]]
        p, bary = closest_on_triangles(Y, A, B, Cc)
        fn = unit(np.cross(B - A, Cc - A))
        pp = Y - ((Y - A) * fn).sum(1)[:, None] * fn          # plane projection
        off = np.linalg.norm(pp - p, axis=1)
        n = unit((surf.N[tv] * bary[:, :, None]).sum(1))
        d = ((Y - p) * n).sum(1)
        return {'ok': ok, 'tri': self.Tv_index[tl], 'tv': tv, 'bary': bary, 'p': p, 'n': n, 'd': d, 'off': off,
                'dist': np.linalg.norm(Y - p, axis=1)}

    def interp(self, vals, pr):
        """Barycentric interpolation of a per-vertex array at projections."""
        v = np.asarray(vals)
        if v.ndim == 1:
            return (v[pr['tv']] * pr['bary']).sum(1)
        return (v[pr['tv']] * pr['bary'][:, :, None]).sum(1)

    def region_at(self, pr):
        """Region of the nearest corner of each projection."""
        k = np.argmax(pr['bary'], 1)
        return self.region[pr['tv'][np.arange(len(k)), k]]


def hidden_faces(h, ndirs=48, occluders=None):
    """Skin faces not visible from outside in any of ndirs directions (mouth bag, eye-socket lining
    behind the eyeballs), cached per head build in fit/cache. occluders = (P, T) of extra surfaces
    (the eyeballs) that block the view but are not tested themselves."""
    import os, hashlib, trimesh
    from fitcommon import CACHE_DIR
    st = os.stat(h.npz_path)
    gst = os.stat(h.glb_path)
    key = hashlib.sha1(f'{h.npz_path}|{st.st_size}|{int(st.st_mtime)}|{gst.st_size}|{int(gst.st_mtime)}|{ndirs}|'
                       f'occ{0 if occluders is None else len(occluders[0])}'.encode()).hexdigest()[:16]
    cp = os.path.join(CACHE_DIR, f'hidden_{h.sex}_{key}.npy')
    if os.path.exists(cp):
        return np.load(cp)
    tc = h.P[h.T].mean(1)
    tn = unit(np.cross(h.P[h.T[:, 1]] - h.P[h.T[:, 0]], h.P[h.T[:, 2]] - h.P[h.T[:, 0]]))
    if occluders is not None:
        OP, OT = occluders
        mesh = trimesh.Trimesh(np.concatenate([h.P, OP]), np.concatenate([h.T, OT + len(h.P)]), process=False)
    else:
        mesh = h.mesh
    dirs = unit(np.random.default_rng(0).normal(size=(ndirs, 3)))
    vis = np.zeros(len(tc), bool)
    for d in dirs:
        idx = np.nonzero(((tn @ d) > 0.15) & ~vis)[0]
        if len(idx):
            hit = mesh.ray.intersects_any(tc[idx] + tn[idx] * 0.0003, np.tile(d, (len(idx), 1)))
            vis[idx[~hit]] = True
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.save(cp, ~vis)
    return ~vis


@functools.lru_cache(None)
def load(sex):
    return RLModel(sex)
