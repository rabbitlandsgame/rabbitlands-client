"""Blender CPU helper for repair_wave_volume.py's ignored stage."""
import sys
from pathlib import Path
import bpy,numpy as np
stage=Path(sys.argv[sys.argv.index('--')+1]);d=np.load(stage/'volume.npz')
bpy.ops.wm.read_factory_settings(use_empty=True)
m=bpy.data.meshes.new('Closed wave volume');m.from_pydata(d['P'].tolist(),[],d['F'].tolist());m.update()
o=bpy.data.objects.new('Closed wave volume',m);bpy.context.collection.objects.link(o);bpy.context.view_layer.objects.active=o;o.select_set(True)
remesh=o.modifiers.new('Resolve voxel pinches','REMESH');remesh.mode='VOXEL';remesh.voxel_size=.0018;remesh.use_smooth_shade=True;bpy.ops.object.modifier_apply(modifier=remesh.name)
smooth=o.modifiers.new('Round voxel surface','SMOOTH');smooth.factor=.6;smooth.iterations=8;bpy.ops.object.modifier_apply(modifier=smooth.name)
tri=o.modifiers.new('Triangles','TRIANGULATE');bpy.ops.object.modifier_apply(modifier=tri.name)
for lod,budget in enumerate([16000,6000,1850]):
 c=o.copy();c.data=o.data.copy();bpy.context.collection.objects.link(c);bpy.context.view_layer.objects.active=c
 dec=c.modifiers.new('Runtime budget','DECIMATE');dec.ratio=budget/len(c.data.polygons);dec.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=dec.name)
 mesh=c.data;mesh.calc_loop_triangles();P=np.empty(len(mesh.vertices)*3,'f4');mesh.vertices.foreach_get('co',P);T=np.empty(len(mesh.loop_triangles)*3,np.int32);mesh.loop_triangles.foreach_get('vertices',T)
 np.savez_compressed(stage/f'lod{lod}.npz',P=P.reshape(-1,3),T=T.reshape(-1,3));print('CLOSED_WAVE_LOD',lod,len(T)//3,flush=True);bpy.data.objects.remove(c,do_unlink=True)
