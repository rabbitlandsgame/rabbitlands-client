"""Head-skin LODs: Blender collapse decimation with protected regions, then morph
targets, skin weights and normals transferred from LOD0 by closest-point binding.

Protected vertices (seam band, zipper strip, rim, eye openings, lips) are never
collapsed, so the neck rim keeps matching the body patch exactly at every LOD."""
import numpy as np, trimesh


def vertex_normals(P, T, weld):
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    acc = np.zeros((weld.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, weld[T[:, k]], fn)
    acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
    return acc[weld]


def decimate(P, T, UV, weld, protect, ratio):
    import bpy
    uw, first, inv = np.unique(weld, return_index=True, return_inverse=True)
    inv = inv.ravel()
    Pw = P[first]
    Tw = inv[T]
    me = bpy.data.meshes.new('rl_lod')
    me.from_pydata(Pw.tolist(), [], Tw.tolist())
    me.update()
    uvl = me.uv_layers.new(name='UV')
    for poly in me.polygons:
        tri = T[poly.index]
        for k, li in enumerate(poly.loop_indices):
            u = UV[tri[k]]
            uvl.data[li].uv = (float(u[0]), float(1 - u[1]))
    ob = bpy.data.objects.new('rl_lod', me)
    bpy.context.scene.collection.objects.link(ob)
    vg = ob.vertex_groups.new(name='protect')
    pw = np.zeros(len(uw), bool); pw[inv[protect]] = True
    vg.add([int(i) for i in np.nonzero(pw)[0]], 1.0, 'REPLACE')
    md = ob.modifiers.new('dec', 'DECIMATE')
    md.decimate_type = 'COLLAPSE'; md.ratio = ratio
    md.vertex_group = 'protect'; md.invert_vertex_group = True; md.vertex_group_factor = 1000.0
    md.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    m2 = eo.to_mesh()
    m2.calc_loop_triangles()
    uvd = m2.uv_layers[0].data
    keys, outP, outUV, outT, outWeld = {}, [], [], [], []
    for lt in m2.loop_triangles:
        idx = []
        for li in lt.loops:
            v = m2.loops[li].vertex_index
            u = uvd[li].uv
            k = (v, round(u[0], 6), round(u[1], 6))
            if k not in keys:
                keys[k] = len(outP); outP.append(tuple(m2.vertices[v].co)); outUV.append((u[0], 1 - u[1])); outWeld.append(v)
            idx.append(keys[k])
        outT.append(idx)
    eo.to_mesh_clear()
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    return np.array(outP), np.array(outT), np.array(outUV), np.array(outWeld)


def bind(P0, T0, Q):
    """Closest point of each Q on the LOD0 surface -> (triangle, barycentrics)."""
    mesh = trimesh.Trimesh(P0, T0, process=False)
    cp, dist, tri = trimesh.proximity.closest_point(mesh, Q)
    a, b, c = P0[T0[tri, 0]], P0[T0[tri, 1]], P0[T0[tri, 2]]
    bc = trimesh.triangles.points_to_barycentric(np.stack([a, b, c], 1), cp)
    return tri, bc, dist


def make_lod(P, T, UV, N, W, morphs, weld, protect, ratio, fixed_normals=None, keep_free=0.3):
    """Returns (P, N, UV, T, W, morph_list) for one LOD. The collapse ratio is raised when
    the protected share is large so free regions always keep at least `keep_free` of
    their triangles (otherwise the decimator flattens whole unprotected areas)."""
    pf = protect[T].all(1).mean()
    ratio = max(ratio, pf + (1 - pf) * keep_free)
    LP, LT, LUV, Lweld = decimate(P, T, UV, weld, protect, ratio)
    tri, bc, dist = bind(P, T, LP)
    corners = T[tri]
    def interp(A):
        return (A[corners] * bc[..., None]).sum(1)
    LW = interp(W); LW /= LW.sum(1, keepdims=True)
    # normals and morph normals carried over from LOD0 (seam-blended there), so LODs shade alike
    LN = interp(N); LN /= np.maximum(np.linalg.norm(LN, axis=1, keepdims=True), 1e-9)
    if fixed_normals is not None:
        fp, fn = fixed_normals
        d2, idx = trimesh.proximity.ProximityQuery(trimesh.Trimesh(fp[:3], [[0, 1, 2]], process=False)).vertex(LP) if False else (None, None)
        from scipy.spatial import cKDTree
        dd, ii = cKDTree(fp).query(LP)
        hit = dd < 1e-6
        LN[hit] = fn[ii[hit]]
    ml = []
    for dp, dn in morphs:
        ldp = interp(dp)
        Nm = interp(N + dn); Nm /= np.maximum(np.linalg.norm(Nm, axis=1, keepdims=True), 1e-9)
        if fixed_normals is not None:
            Nm[hit] = LN[hit]
        ml.append((ldp, Nm - LN))
    return LP, LN, LUV, LT, LW, ml, {'tris': int(len(LT)), 'verts': int(len(LP)), 'maxBindDist': float(dist.max()), 'ratio': float(ratio), 'protectedShare': float(pf)}
