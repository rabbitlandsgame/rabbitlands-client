import bpy, numpy as np
nc = bpy.data.objects['NC_cape']; me = nc.data
me.calc_loop_triangles()
gi = {g.index: g.name for g in nc.vertex_groups}
nv = len(me.vertices)
co = np.empty(nv * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
W = {}
for v in me.vertices:
    W[v.index] = [(gi[g.group], g.weight) for g in v.groups if g.weight > 1e-4]
uvl = me.uv_layers.active.data
tris = []; 
for t in me.loop_triangles:
    tris.append((t.material_index, [ (t.vertices[k], t.loops[k]) for k in range(3)], [tuple(t.split_normals[k]) for k in range(3)]))
loops_uv = np.empty(len(uvl) * 2, np.float32); uvl.foreach_get('uv', loops_uv); loops_uv = loops_uv.reshape(-1, 2)
names = sorted({n for w in W.values() for n, _ in w})
jw = np.zeros((nv, 4), np.int32); ww = np.zeros((nv, 4), np.float32)
for i in range(nv):
    w = sorted(W[i], key=lambda t: -t[1])[:4]
    s = sum(x for _, x in w) or 1
    for k, (n, x) in enumerate(w): jw[i, k] = names.index(n); ww[i, k] = x / s
tri_mat = np.array([t[0] for t in tris], np.int32)
tri_v = np.array([[a for a, _ in t[1]] for t in tris], np.int32)
tri_l = np.array([[b for _, b in t[1]] for t in tris], np.int32)
tri_n = np.array([t[2] for t in tris], np.float32)
np.savez(SCR + '/cape_mesh.npz', co=co, uv=loops_uv, tri_mat=tri_mat, tri_v=tri_v, tri_l=tri_l, tri_n=tri_n, jw=jw, ww=ww, names=np.array(names))
result = {"verts": nv, "tris": len(tris), "groups": names}
