"""Blender helper for repair_curly_hairline.py; run -- <ignored stage>."""
import bpy,numpy as np,sys
from pathlib import Path
stage=Path(sys.argv[sys.argv.index('--')+1]);a=np.load(stage/'clipped.npz')
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('Clipped reference curls');mesh.from_pydata(a['POSITION'].tolist(),[],a['T'].tolist());mesh.update()
uv=mesh.uv_layers.new(name='UVMap');uv.data.foreach_set('uv',a['TEXCOORD_0'][a['T'].reshape(-1)].astype('f4').reshape(-1));mesh.polygons.foreach_set('use_smooth',np.ones(len(mesh.polygons),bool))
obj=bpy.data.objects.new('Clipped reference curls',mesh);bpy.context.collection.objects.link(obj)
for lod,budget in enumerate([12000,4300,1300]):
    candidate=obj.copy();candidate.data=mesh.copy();bpy.context.collection.objects.link(candidate);bpy.context.view_layer.objects.active=candidate
    if len(mesh.polygons)>budget:
        mod=candidate.modifiers.new('Curl LOD','DECIMATE');mod.ratio=budget/len(mesh.polygons);mod.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=mod.name)
    m=candidate.data;m.calc_loop_triangles();P=np.empty(len(m.vertices)*3,'f4');m.vertices.foreach_get('co',P);P=P.reshape(-1,3)
    T=np.empty(len(m.loop_triangles)*3,'i4');loops=T.copy();m.loop_triangles.foreach_get('vertices',T);m.loop_triangles.foreach_get('loops',loops)
    uv=np.empty(len(m.loops)*2,'f4');m.uv_layers.active.data.foreach_get('uv',uv);uv=uv.reshape(-1,2)[loops]
    keys=np.c_[T,np.round(uv*1e7).astype(int)];_,take,inv=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    np.savez_compressed(stage/f'lod{lod}.npz',P=P[T[take]],UV=uv[take],T=inv.reshape(-1,3));print('CURL_LOD',lod,len(T)//3,flush=True)
    bpy.data.objects.remove(candidate,do_unlink=True)
