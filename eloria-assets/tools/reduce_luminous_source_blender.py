"""Run with Blender --background --factory-startup --threads 8 --python ...

Arguments after -- are the original and output GLBs. The next pipeline stage,
rig_luminous_source.py, restores the original source normals before review.
"""
import bpy
import bmesh
import sys
import json
import argparse
import numpy as np
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('source',type=Path)
ap.add_argument('target',type=Path)
ap.add_argument('--protect-face',action='store_true')
args=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
source,target=args.source,args.target
bpy.context.scene.render.threads_mode='FIXED'
bpy.context.scene.render.threads=8
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(source))
obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
bpy.context.view_layer.objects.active=obj
obj.select_set(True)
# Duplicate positions at chart boundaries must collapse together; UV corners
# remain independent. Otherwise decimation creates cracks at chart edges.
bm=bmesh.new();bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000001)
bm.to_mesh(obj.data);bm.free()
if args.protect_face:
    # Separate, explicit regional budgets keep eye detail without spending
    # almost the whole mesh budget on the head. Zero group weights hold the
    # other regions while each pass works on the same connected mesh.
    def regions(points):
        x,y,z=points.T
        height=(z+.9521999955)*(1.7/1.9029639959)
        across=abs(x)*(1.7/1.9029639959)
        forward=(-y+.0030060038)*(1.7/1.9029639959)
        labels=np.where(height>1.46,1,0)
        eyes=(height>1.566)&(height<1.614)&(across>.01)&(across<.064)&(forward>.018)
        labels[eyes]=2
        return labels
    for region,budget in [(0,25000),(1,6000),(2,3500)]:
        mesh=obj.data
        points=np.empty(len(mesh.vertices)*3,dtype='f4');mesh.vertices.foreach_get('co',points);points=points.reshape(-1,3)
        faces=np.empty(len(mesh.polygons)*3,dtype='i4');mesh.polygons.foreach_get('vertices',faces);faces=faces.reshape(-1,3)
        count=int((regions(points[faces].mean(1))==region).sum())
        if count<=budget:
            continue
        group=obj.vertex_groups.new(name='ReduceRegion'+str(region))
        group.add(np.flatnonzero(regions(points)==region).tolist(),1.0,'REPLACE')
        modifier=obj.modifiers.new('RegionalSourceReduction','DECIMATE')
        modifier.decimate_type='COLLAPSE'
        modifier.ratio=(len(faces)-count+budget)/len(faces)
        modifier.use_collapse_triangulate=True
        modifier.vertex_group=group.name
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        current=obj.vertex_groups.get('ReduceRegion'+str(region))
        if current is not None:
            obj.vertex_groups.remove(current)
        print('REGION',region,'budget',budget,'total',len(obj.data.polygons),flush=True)
else:
    modifier=obj.modifiers.new('SourceSilhouetteReduction','DECIMATE')
    modifier.decimate_type='COLLAPSE';modifier.ratio=.018
    modifier.use_collapse_triangulate=True
    bpy.ops.object.modifier_apply(modifier=modifier.name)
bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',
    use_selection=True,export_materials='EXPORT',export_normals=True,
    export_texcoords=True,export_animations=False)
print('REDUCED_RESULT',json.dumps({'vertices':len(obj.data.vertices),
    'polygons':len(obj.data.polygons),'path':str(target)}))
