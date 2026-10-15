import bpy, numpy as np
nc = bpy.data.objects['NC_cape']; me = nc.data
img = next(n.image for n in me.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE')
uvl = me.uv_layers.active.data
uv = np.empty(len(uvl) * 2, np.float32); uvl.foreach_get('uv', uv)
ls = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_start', ls)
lt = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_total', lt)
mi = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('material_index', mi)
np.savez(SCR + '/cape_uv.npz', uv=uv.reshape(-1, 2), ls=ls, lt=lt, mi=mi)
src = img.filepath_raw or ''
if img.packed_file:
    img.filepath_raw = SCR + '/cape_src.png'; img.file_format = 'PNG'; img.save()
result = {"image": img.name, "size": list(img.size), "packed": bool(img.packed_file)}
