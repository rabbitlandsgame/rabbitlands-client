"""Blender background helper: preserve the extracted hair UVs and bake three LODs.
blender -b --python decimate_reference_surface.py -- <stage>
"""
import sys,json
from pathlib import Path
import bpy,numpy as np
stage=Path(sys.argv[sys.argv.index('--')+1]);source=np.load(stage/'extracted.npz')
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
mesh=bpy.data.meshes.new('Reference hair only');mesh.from_pydata(source['P'].tolist(),[],source['T'].tolist());mesh.update()
uv=mesh.uv_layers.new(name='UVMap')
uv.data.foreach_set('uv',source['UV'][source['T'].reshape(-1)].astype('f4').reshape(-1))
mesh.polygons.foreach_set('use_smooth',np.ones(len(mesh.polygons),dtype=bool))
print('REFERENCE_HAIR_INPUT',len(mesh.polygons),flush=True)
obj=bpy.data.objects.new('Reference hair only',mesh);bpy.context.collection.objects.link(obj)
budgets=json.loads((stage/'lod-budgets.json').read_text()) if (stage/'lod-budgets.json').exists() else [15800,5800,1700]
for lod,budget in enumerate(budgets):
    candidate=obj.copy();candidate.data=mesh.copy();bpy.context.collection.objects.link(candidate)
    bpy.context.view_layer.objects.active=candidate
    if len(mesh.polygons)>budget:
        mod=candidate.modifiers.new('Measured LOD budget','DECIMATE');mod.ratio=budget/len(mesh.polygons);mod.use_collapse_triangulate=True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    m=candidate.data;m.calc_loop_triangles()
    co=np.empty(len(m.vertices)*3,'f4');normal=co.copy();m.vertices.foreach_get('co',co);m.vertices.foreach_get('normal',normal)
    corners=np.empty(len(m.loop_triangles)*3,np.int32);loops=corners.copy();m.loop_triangles.foreach_get('vertices',corners);m.loop_triangles.foreach_get('loops',loops)
    uvco=np.empty(len(m.loops)*2,'f4');m.uv_layers.active.data.foreach_get('uv',uvco)
    uvco=uvco.reshape(-1,2)[loops]
    keys=np.column_stack([corners,np.round(uvco*1e8).astype(np.int64)])
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    P=co.reshape(-1,3)[corners[first]];N=normal.reshape(-1,3)[corners[first]];UV=uvco[first];T=inverse.reshape(-1,3)
    np.savez_compressed(stage/f'lod{lod}.npz',P=P,N=N,UV=UV,T=T)
    bpy.data.objects.remove(candidate,do_unlink=True)
    print('REFERENCE_HAIR_LOD',lod,len(T),flush=True)
