"""Shipped Human body (luminous_<sex>.glb) helpers for the RL head build:
rest joints, the head-region skull used for the cranium fit, and the neck-plane
cut whose open rim the head module closes."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import hashlib, os, sys, numpy as np
ROOT = paths.REPO
sys.path.insert(0, ROOT + '/eloria-assets/tools/tpose_bodies/vendor')
import glbkit  # noqa: E402

BODY_MESHES = ('body', 'eyes', 'eyebrows', 'scalp')


def path(sex):
    return f'{ROOT}/godot-client/assets/actors/native/races/luminous_{sex}.glb'


class Body:
    def __init__(self, sex):
        self.sex = sex
        self.path = path(sex)
        self.sha256 = hashlib.sha256(open(self.path, 'rb').read()).hexdigest()
        g, b = glbkit.read(self.path)
        self.gltf, self.blob = g, b
        self.G = glbkit.globals_of(g)
        skin = g['skins'][0]
        self.joint_nodes = skin['joints']
        self.joint_names = [g['nodes'][j]['name'] for j in self.joint_nodes]
        self.ibm = glbkit.accessor(g, b, skin['inverseBindMatrices']).reshape(-1, 4, 4)
        self.meshes = {}
        for ni, n in enumerate(g['nodes']):
            if 'mesh' not in n:
                continue
            p = g['meshes'][n['mesh']]['primitives'][0]
            a = p['attributes']
            self.meshes[n['name']] = dict(
                P=glbkit.accessor(g, b, a['POSITION']).astype(np.float64),
                N=glbkit.accessor(g, b, a['NORMAL']).astype(np.float64),
                UV=glbkit.accessor(g, b, a['TEXCOORD_0']).astype(np.float64),
                J=glbkit.accessor(g, b, a['JOINTS_0']).astype(np.int64),
                W=glbkit.accessor(g, b, a['WEIGHTS_0']).astype(np.float64),
                I=glbkit.accessor(g, b, p['indices']).astype(np.int64).reshape(-1, 3), node=ni)
        self.jpos = {nm: self.G[j][:3, 3] for nm, j in zip(self.joint_names, self.joint_nodes)}
        self.head_axis = self.jpos['Head'] - self.jpos['neck_01']
        self.head_axis = self.head_axis / np.linalg.norm(self.head_axis)

    def joint(self, name):
        return self.joint_names.index(name)

    def weight_of(self, mesh, joint_name):
        m = self.meshes[mesh]
        j = self.joint(joint_name)
        return (m['W'] * (m['J'] == j)).sum(1)

    def plane(self, travel):
        o = self.jpos['neck_01'] + travel * self.head_axis
        return o, self.head_axis

    def skull(self):
        """Vertices + triangles of the visible head shell (body/scalp/eyes/eyebrows, Head-weighted)."""
        P_all = self.meshes['body']['P']
        tris = []
        for name in BODY_MESHES:
            m = self.meshes[name]
            hw = self.weight_of(name, 'Head')
            keep = hw[m['I']].mean(1) > 0.5
            tris.append(m['I'][keep])
        T = np.concatenate(tris)
        return P_all, T

    def cut(self, travel):
        """Hide body triangles entirely above the neck plane. Returns hidden mask and the
        ordered open rim loop (body vertex indices, counter-clockwise seen from above)."""
        m = self.meshes['body']
        o, d = self.plane(travel)
        s = (m['P'] - o) @ d
        hidden = (s[m['I']] > 0).all(1)
        # weld split (UV-seam) vertices by position so the rim is one topological loop
        q = np.round(m['P'] / 1e-5).astype(np.int64)
        _, weld, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
        canon = weld[inv.ravel()]
        Iw = canon[m['I']]
        kept = Iw[~hidden]
        # boundary edges of the kept set that border a hidden face
        from collections import Counter, defaultdict
        def key(a, b):
            return (a, b) if a < b else (b, a)
        kc = Counter()
        for t in kept:
            for i in range(3):
                kc[key(t[i], t[(i + 1) % 3])] += 1
        hc = Counter()
        for t in Iw[hidden]:
            for i in range(3):
                hc[key(t[i], t[(i + 1) % 3])] += 1
        # directed boundary edges of kept faces (orientation from kept triangles)
        nxt = defaultdict(list)
        for t in kept:
            for i in range(3):
                a, b = t[i], t[(i + 1) % 3]
                if kc[key(a, b)] == 1 and hc[key(a, b)] >= 1:
                    nxt[a].append(b)
        # walk the largest loop
        loops, seen = [], set()
        for start in list(nxt):
            if start in seen:
                continue
            loop = [start]; seen.add(start); cur = start
            while True:
                nb = [x for x in nxt[cur] if x not in seen or x == start]
                if not nb:
                    break
                cur = nb[0]
                if cur == start:
                    break
                loop.append(cur); seen.add(cur)
            loops.append(loop)
        loops.sort(key=len, reverse=True)
        return hidden, loops


def clip_patch(body, travel):
    """Exact neck-plane cut of the shipped body.

    Every body triangle with any corner above the plane is hidden; the part of
    each such triangle that lies below the plane is returned as a patch (body
    UVs, normals and weights interpolated on the cut edges), so the visible body
    is unchanged below the plane and ends in one clean planar loop above it.
    Returns hidden-triangle mask, patch dict and the ordered planar loop (patch
    vertex indices sorted by angle about the neck axis)."""
    m = body.meshes['body']
    o, d = body.plane(travel)
    P, N, UV, J, W, I = m['P'], m['N'], m['UV'], m['J'], m['W'], m['I']
    s = (P - o) @ d
    above = s[I] > 0
    hidden = above.any(1)
    out_p, out_n, out_uv, out_w = [], [], [], []
    vid = {}
    nj = len(body.joint_names)
    def dense_w(v):
        w = np.zeros(nj); np.add.at(w, J[v], W[v]); return w
    def keep_vertex(v):
        k = ('v', int(v))
        if k not in vid:
            vid[k] = len(out_p); out_p.append(P[v]); out_n.append(N[v]); out_uv.append(UV[v]); out_w.append(dense_w(v))
        return vid[k]
    def cut_vertex(a, b):
        k = ('e', min(a, b), max(a, b))
        if k not in vid:
            t = s[a] / (s[a] - s[b])
            n = N[a] + t * (N[b] - N[a]); n /= np.linalg.norm(n) + 1e-12
            vid[k] = len(out_p); out_p.append(P[a] + t * (P[b] - P[a])); out_n.append(n)
            out_uv.append(UV[a] + t * (UV[b] - UV[a])); out_w.append(dense_w(a) * (1 - t) + dense_w(b) * t)
        return vid[k]
    tris, on_plane = [], set()
    for ti in np.nonzero(hidden & ~above.all(1))[0]:
        t = I[ti]; poly = []
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            if s[a] <= 0:
                poly.append(keep_vertex(a))
            if (s[a] <= 0) != (s[b] <= 0):
                c = cut_vertex(a, b); poly.append(c); on_plane.add(c)
        for k in range(1, len(poly) - 1):
            tris.append([poly[0], poly[k], poly[k + 1]])
    PP = np.array(out_p)
    loop = np.array(sorted(on_plane))
    r = PP[loop] - o; r -= np.outer(r @ d, d)
    e1 = np.array([1.0, 0, 0]); e1 -= d * (e1 @ d); e1 /= np.linalg.norm(e1); e2 = np.cross(d, e1)
    if e2[2] < 0: e2 = -e2
    th = np.arctan2(r @ e2, r @ e1)
    # collapse coincident cut vertices (UV-seam duplicates) for the loop order
    order = np.argsort(th)
    patch = {'P': PP, 'N': np.array(out_n), 'UV': np.array(out_uv), 'W': np.array(out_w), 'T': np.array(tris)}
    return hidden, patch, loop[order]
