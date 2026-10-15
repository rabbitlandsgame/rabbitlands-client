"""Reduce an extracted head while retaining a larger budget around facial features."""
import argparse
from pathlib import Path
import sys
import bpy
import bmesh
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path)
parser.add_argument('target',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.context.scene.render.threads_mode='FIXED';bpy.context.scene.render.threads=8
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(args.source))
obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
bpy.context.view_layer.objects.active=obj;obj.select_set(True)
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
bm.to_mesh(obj.data);bm.free()
def regions(points):
    x,forward,height=points[:,0],-points[:,1],points[:,2]
    labels=np.where(height<1.555,0,1)
    face=(abs(x)<.085)&(height>1.565)&(height<1.695)&(forward>.025)
    labels[face]=2
    return labels

# Each region retains its own budget; protecting the face must never consume
# the entire budget and collapse the back of the skull into a few triangles.
for region,budget in [(0,2000),(1,8000),(2,6000)]:
    mesh=obj.data
    points=np.empty(len(mesh.vertices)*3,dtype='f4');mesh.vertices.foreach_get('co',points);points=points.reshape(-1,3)
    faces=np.empty(len(mesh.polygons)*3,dtype='i4');mesh.polygons.foreach_get('vertices',faces);faces=faces.reshape(-1,3)
    count=int((regions(points[faces].mean(1))==region).sum())
    if count<=budget:continue
    group=obj.vertex_groups.new(name='Region'+str(region))
    group.add(np.flatnonzero(regions(points)==region).tolist(),1.0,'REPLACE')
    modifier=obj.modifiers.new('RegionalHeadReduction','DECIMATE')
    modifier.decimate_type='COLLAPSE';modifier.ratio=(len(faces)-count+budget)/len(faces)
    modifier.use_collapse_triangulate=True;modifier.vertex_group=group.name
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    current=obj.vertex_groups.get('Region'+str(region))
    if current is not None:obj.vertex_groups.remove(current)
    print('REGION',region,'budget',budget,'remaining',len(obj.data.polygons),flush=True)
bpy.ops.export_scene.gltf(filepath=str(args.target),export_format='GLB',use_selection=True,
                         export_normals=True,export_texcoords=True,export_animations=False)
print('REDUCED_HEAD',len(obj.data.polygons),str(args.target),flush=True)
