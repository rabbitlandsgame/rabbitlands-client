"""Blender UV-only authoring for a new inset reference layer.

blender -b --factory-startup --threads 2 --python-exit-code 1 --python
  unwrap_reference_layer.py -- source.npz fresh-chart.npz

The output contains per-corner UVs only. Source P/T and exterior paint are
never rewritten; the owning builder may split UV attribute seams before skin
and morph authoring, proving triangle positions stay exact.
"""
from pathlib import Path
import hashlib,json,sys,math
import bpy,numpy as np

source,out=map(Path,sys.argv[sys.argv.index('--')+1:]);assert not out.exists()
a=np.load(source);P=a['P'];T=a['T'].astype(int)
assert np.isfinite(P).all() and T.ndim==2 and T.shape[1]==3
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('Inset paint chart');mesh.from_pydata(P.tolist(),[],T.tolist());mesh.update()
obj=bpy.data.objects.new('Inset paint chart',mesh);bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active=obj;obj.select_set(True);mesh.uv_layers.new(name='PaintChart')
before=np.empty(len(mesh.vertices)*3,'f4');mesh.vertices.foreach_get('co',before)
faces=np.array([tuple(face.vertices) for face in mesh.polygons]);assert np.array_equal(faces,T)
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(1),island_margin=.025,area_weight=0.,correct_aspect=True,scale_to_bounds=False)
bpy.ops.object.mode_set(mode='OBJECT')
after=np.empty(len(mesh.vertices)*3,'f4');mesh.vertices.foreach_get('co',after)
assert np.array_equal(before,after) and np.array_equal(np.array([tuple(face.vertices) for face in mesh.polygons]),T)
uv=np.array([[tuple(mesh.uv_layers.active.data[loop].uv) for loop in face.loop_indices] for face in mesh.polygons])
assert uv.shape==(len(T),3,2) and np.isfinite(uv).all() and uv.min()>=-1e-6 and uv.max()<=1+1e-6
uv=.015+.970*np.clip(uv,0,1)
np.savez_compressed(out,corner_uv=uv)
digest=lambda array:hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'triangle_positions_sha256':digest(P[T]),
        'blender_positions_before_sha256':digest(before),'blender_positions_after_sha256':digest(after),
        'triangle_indices_exact':True,'uv_only':True,'chart_angle_degrees':1,'triangles':len(T),'uv_min':uv.min(0).min(0).tolist(),'uv_max':uv.max(0).max(0).tolist(),
        'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print('REFERENCE_LAYER_UV_ONLY',json.dumps(report),flush=True)
