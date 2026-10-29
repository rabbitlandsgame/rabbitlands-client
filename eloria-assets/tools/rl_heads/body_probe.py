import sys, json, numpy as np
sys.path.insert(0, 'eloria-assets/tools/tpose_bodies/vendor')
import glbkit
def load(sex):
    g, b = glbkit.read(f'godot-client/assets/actors/native/races/luminous_{sex}.glb')
    G = glbkit.globals_of(g)
    skin = g['skins'][0]; joints = skin['joints']
    names = [g['nodes'][j]['name'] for j in joints]
    meshes = {}
    for ni, n in enumerate(g['nodes']):
        if 'mesh' in n:
            m = g['meshes'][n['mesh']]
            for p in m['primitives']:
                a = p['attributes']
                meshes[n['name']] = dict(P=glbkit.accessor(g, b, a['POSITION']), N=glbkit.accessor(g, b, a['NORMAL']),
                    UV=glbkit.accessor(g, b, a['TEXCOORD_0']), J=glbkit.accessor(g, b, a['JOINTS_0']), W=glbkit.accessor(g, b, a['WEIGHTS_0']),
                    I=glbkit.accessor(g, b, p["indices"]).astype(np.int64).reshape(-1, 3), node=ni)
    jpos = {names[i]: G[j][:3, 3] for i, j in enumerate(joints)}
    return g, b, names, meshes, jpos
if __name__ == '__main__':
    for sex in ('female', 'male'):
        g, b, names, M, jp = load(sex)
        print('==', sex, 'neck_01', jp['neck_01'].round(4), 'Head', jp['Head'].round(4), 'spine_03', jp['spine_03'].round(4))
        # node transforms of mesh nodes
        for k, m in M.items():
            print(k, len(m['I']), 'node matrix ident?', np.allclose(glbkit.globals_of(g)[m['node']], np.eye(4)))
        P = M['body']['P']; I = M['body']['I']
        d = (jp['Head'] - jp['neck_01']); d /= np.linalg.norm(d); o = jp['neck_01'] + 0.075 * d
        s = (P - o) @ d
        above = (s[I] > 0).all(1); cross = (s[I] > 0).any(1) & ~above
        print('plane origin', o.round(4), 'dir', d.round(4), 'faces above', above.sum(), 'crossing', cross.sum())
        hi = np.unique(I[above | cross]); HP = P[hi]
        print('head(above plane) bbox', HP.min(0).round(4), HP.max(0).round(4))
        hw = M['body']['W']; hj = M['body']['J']; hidx = names.index('Head'); nidx = names.index('neck_01')
        ring = np.unique(I[cross]); 
        wh = np.array([(hw[v][hj[v] == hidx]).sum() for v in ring]); wn = np.array([(hw[v][hj[v] == nidx]).sum() for v in ring])
        print('crossing verts', len(ring), 'Head w mean', wh.mean().round(3), 'neck w mean', wn.mean().round(3))
        E = M['eyes']['P']; print('eyes patch bbox', E[np.unique(M['eyes']['I'])].min(0).round(4), E[np.unique(M['eyes']['I'])].max(0).round(4))
        S = M['scalp']['P'][np.unique(M['scalp']['I'])]; print('scalp bbox', S.min(0).round(4), S.max(0).round(4))
