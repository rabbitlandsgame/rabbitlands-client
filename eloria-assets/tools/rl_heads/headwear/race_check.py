"""How the shipped circlet variants sit on the other race heads (current state)."""
import json, sys
import numpy as np, trimesh
import hwlib as h, ringfit as rf, fit_open_headwear as F

def race_skin(slug):
    path = h.CLIENT + '/assets/actors/native/races/%s.glb' % slug
    g, b = h.glbkit.read(path)
    joints = [g['nodes'][j]['name'] for j in g['skins'][0]['joints']]
    head_j = joints.index('Head')
    Ps, Is, n, eyes = [], [], 0, None
    for ni, node in enumerate(g['nodes']):
        if 'mesh' not in node or node.get('name') not in ('body', 'scalp', 'eyes'):
            continue
        for prim in g['meshes'][node['mesh']]['primitives']:
            P = h.glbkit.accessor(g, b, prim['attributes']['POSITION'])
            sk = h._skinned_rest(g, b, ni, prim, P)
            P = sk if sk is not None else P
            I = h.glbkit.accessor(g, b, prim['indices']).astype(int).reshape(-1, 3)
            J = h.glbkit.accessor(g, b, prim['attributes']['JOINTS_0']).astype(int)
            W = h.glbkit.accessor(g, b, prim['attributes']['WEIGHTS_0'])
            w = (W * (J == head_j)).sum(1)
            keep = w[I].mean(1) > 0.5
            if node['name'] == 'eyes':
                eyes = P[np.unique(I[keep])]
                continue
            Ps.append(P); Is.append(I[keep] + n); n += len(P)
    return dict(P=np.concatenate(Ps), I=np.concatenate(Is)), float(eyes[:, 1].mean())


class RaceHead(rf.Head):
    def __init__(self, slug):
        skin, eye_y = race_skin(slug)
        self.sex, self.kind, self.hair_style = slug, 'race', None
        self.eye_y = eye_y; self.skin = skin
        y = eye_y + 0.035
        mesh = trimesh.Trimesh(skin['P'], skin['I'], process=False)
        fz, _, _ = rf._cast(mesh, np.array([0, y, 0.0]), np.array([[0, 0, 1.0], [0, 0, -1.0]]))
        self.C = np.array([0.0, y, (fz[0] - fz[1]) / 2])
        A, E = np.meshgrid(rf.AZ, rf.EL, indexing='ij')
        first, last, _ = rf._cast(mesh, self.C, rf.sph(A.ravel(), E.ravel()))
        self.R_skin = first.reshape(A.shape); self.R_skin_last = last.reshape(A.shape)
        self._fill(self.R_skin)
        self.R_hair = None; self.lift = np.zeros_like(self.R_skin)
        self.R = self.R_skin + rf.CLEAR_SKIN
        self._interp = self._make_interp(self.R); self._interp_skin = self._make_interp(self.R_skin)
        self._landmarks()

eq = h.equipment()
for slug in sys.argv[1].split(','):
    race, sex = slug.rsplit('_', 1)
    H = RaceHead(slug)
    for v in [111, 119]:
        m = dict(eq['models']['3:%d' % v]); var = m['variants'].get('canonical_%s' % slug)
        if var is None:
            print(slug, v, 'no own variant'); continue
        prims = h.glb_primitives(h.res(var['scene']))
        off = np.array(var['socket']['offset']); o = h.body_rest(sex)['Head'][:3, 3]  # same skeleton
        P = np.concatenate([p['P'] for p in prims]) + o + off
        I = np.concatenate([p['I'] for p in prims])
        Q = trimesh.sample.sample_surface(trimesh.Trimesh(P, I, process=False), 8000, seed=3)[0]
        gaps, ys = rf.band_bins(H, Q, 72)
        cen = (np.arange(72) + .5) * 5
        out = []
        for z in ('front', 'left', 'back', 'right'):
            msk = np.array([rf.zone_of(a) == z for a in cen]) & np.isfinite(gaps)
            out.append('%s %.0f/%.0f' % (z[0].upper(), np.nanmin(gaps[msk]) * 1000, np.nanmedian(gaps[msk]) * 1000))
        print('%-18s 3:%d  min/median gap mm %s | skull x%.2f' % (slug, v, '  '.join(out), F._band_ratio(H, Q, H)))
