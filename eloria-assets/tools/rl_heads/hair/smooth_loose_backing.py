"""Blender background helper for a versioned loose-reference backing stage."""
import json,sys
from pathlib import Path
import bpy,numpy as np
stage=Path(sys.argv[sys.argv.index('--')+1]);source=np.load(stage/'volume.npz');config=json.loads((stage/'config.json').read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('Inset loose-hair backing');mesh.from_pydata(source['P'].tolist(),[],source['F'].tolist());mesh.update()
obj=bpy.data.objects.new('Inset loose-hair backing',mesh);bpy.context.collection.objects.link(obj);bpy.context.view_layer.objects.active=obj;obj.select_set(True)
remesh=obj.modifiers.new('Resolve voxel pinches','REMESH');remesh.mode='VOXEL';remesh.voxel_size=config['pitch'];remesh.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=remesh.name)
smooth=obj.modifiers.new('Round inset backing','SMOOTH');smooth.factor=.6;smooth.iterations=6;bpy.ops.object.modifier_apply(modifier=smooth.name)
tri=obj.modifiers.new('Triangles','TRIANGULATE');bpy.ops.object.modifier_apply(modifier=tri.name)
for lod,budget in enumerate(config['triangles']):
    candidate=obj.copy();candidate.data=obj.data.copy();bpy.context.collection.objects.link(candidate);bpy.context.view_layer.objects.active=candidate
    if len(candidate.data.polygons)>budget:
        modifier=candidate.modifiers.new('Bounded backing detail','DECIMATE');modifier.ratio=budget/len(candidate.data.polygons);modifier.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=modifier.name)
    m=candidate.data;m.calc_loop_triangles();P=np.empty(len(m.vertices)*3,'f4');T=np.empty(len(m.loop_triangles)*3,np.int32);m.vertices.foreach_get('co',P);m.loop_triangles.foreach_get('vertices',T)
    np.savez_compressed(stage/f'lod{lod}.npz',P=P.reshape(-1,3),T=T.reshape(-1,3));print('LOOSE_BACKING_LOD',lod,len(T)//3,flush=True)
    bpy.data.objects.remove(candidate,do_unlink=True)
