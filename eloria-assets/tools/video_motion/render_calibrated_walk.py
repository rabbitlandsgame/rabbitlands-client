"""Render a clip at the original reference camera and native cadence."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

parser=argparse.ArgumentParser()
parser.add_argument('--model',required=True)
parser.add_argument('--camera',required=True)
parser.add_argument('--out',required=True)
parser.add_argument('--fps',type=int,default=24)
parser.add_argument('--frames',type=int,required=True)
parser.add_argument('--clip',default='Walk')
parser.add_argument('--horizontal-padding',type=int,default=0)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
source=Path(args.model).resolve()
out=Path(args.out).resolve()
out.mkdir(parents=True,exist_ok=True)
calibration=json.loads(Path(args.camera).read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.fps=args.fps
bpy.ops.import_scene.gltf(filepath=str(source))
for obj in bpy.data.objects:
    if obj.animation_data:
        obj.animation_data.action=None
        for track in obj.animation_data.nla_tracks:
            track.mute=True
action=bpy.data.actions.get(args.clip)
if action is None:
    raise RuntimeError(f'No {args.clip} after import')
for obj in bpy.data.objects:
    if obj.type=='ARMATURE':
        obj.animation_data_create()
        obj.animation_data.action=action
        if action.slots:
            obj.animation_data.action_slot=action.slots[0]
width,height=calibration['width']+2*args.horizontal_padding,calibration['height']
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=width
scene.render.resolution_y=height
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.display.render_aa='16'
sh=scene.display.shading
sh.light='STUDIO'
sh.color_type='TEXTURE'
sh.show_shadows=False
sh.show_cavity=False
sh.show_specular_highlight=False
sh.background_type='WORLD'
scene.world=bpy.data.worlds.new('Reference gray')
scene.world.color=(.45,.45,.45)
scene.view_settings.view_transform='Standard'
matrix=np.array(calibration['pixel_matrix_gltf'])
offset=np.array(calibration['pixel_offset'])
offset[0]+=args.horizontal_padding
scale=-matrix[0,2]
if not np.allclose(matrix,[[0,0,-scale],[0,-scale,0]],atol=.0001):
    raise ValueError('This renderer expects the calibrated orthographic +X side camera')
center=Vector((0,(width/2-offset[0])/scale,(offset[1]-height/2)/scale))
bpy.ops.object.camera_add(location=center+Vector((15,0,0)))
camera=bpy.context.object
camera.data.type='ORTHO'
camera.data.ortho_scale=width/scale
camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
scene.camera=camera
bpy.context.view_layer.update()
def project(point):
    uv=world_to_camera_view(scene,camera,Vector((point[0],-point[2],point[1])))
    return np.array([uv.x*width,(1-uv.y)*height])
camera_error=max(np.linalg.norm(project(p)-(matrix@p+offset)) for p in [np.zeros(3),*np.eye(3)])
assert camera_error<.001
start=float(action.frame_range[0])
for frame in range(args.frames):
    scene.frame_set(int(start+frame),subframe=start+frame-int(start+frame))
    scene.render.filepath=str(out/f'{frame:04d}.png')
    bpy.ops.render.render(write_still=True)
record={'model_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'fps':args.fps,'frames':args.frames,'duration_seconds':args.frames/args.fps,
    'sample_times_seconds':[i/args.fps for i in range(args.frames)],
    'camera':calibration,'horizontal_padding_pixels':args.horizontal_padding,'maximum_projection_error_pixels':camera_error,
    'animation_frame_range':list(map(float,action.frame_range)),
    'clip':args.clip,'loop':args.clip=='Walk',
    'time_policy':('Original cadence; matching loop endpoint excluded, no retiming.' if args.clip=='Walk' else 'Complete one-shot at original cadence including its held endpoint; no retiming.')}
(out/'render-evidence.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print('CALIBRATED_COMPARISON_RENDER_COMPLETE',json.dumps(record),flush=True)
