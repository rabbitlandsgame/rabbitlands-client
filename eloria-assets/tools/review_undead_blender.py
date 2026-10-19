"""Fresh Blender surface comparison and multi-view gait renders.

Blender --background --python this_file -- STAGE
STAGE contains self-contained candidates and an independent reference.npz.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

stage = Path(sys.argv[sys.argv.index('--')+1]).resolve()
reference = np.load(stage/'reference.npz')
reports = []
for source in sorted(stage.glob('*.glb')):
    actor = source.stem
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    scene = bpy.context.scene
    scene.render.fps = 24
    arms = [o for o in scene.objects if o.type == 'ARMATURE']
    shapes = {bone.custom_shape for arm in arms for bone in arm.pose.bones}
    meshes = [o for o in scene.objects if o.type == 'MESH' and o not in shapes and not o.hide_render]
    def activate(action):
        for obj in bpy.data.objects:
            if obj.animation_data:
                obj.animation_data.action = None
                for track in obj.animation_data.nla_tracks: track.mute = True
        for arm in arms:
            for bone in arm.pose.bones: bone.matrix_basis.identity()
            arm.animation_data_create()
            arm.animation_data.action = action
            arm.animation_data.action_slot = next(s for s in action.slots if s.target_id_type == 'OBJECT')
        for mesh in meshes:
            keys = mesh.data.shape_keys
            if not keys: continue
            for key in keys.key_blocks: key.value = 0
            keys.animation_data_create()
            keys.animation_data.action = action
            keys.animation_data.action_slot = next(s for s in action.slots if s.target_id_type == 'KEY')
    def surface(seconds):
        frame = seconds*24
        scene.frame_set(int(frame), subframe=frame-int(frame))
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        points = []
        for mesh in meshes:
            obj = mesh.evaluated_get(graph)
            data = obj.to_mesh()
            points.extend([obj.matrix_world@v.co for v in data.vertices])
            obj.to_mesh_clear()
        points = np.asarray(points)
        return points[:,[0,2,1]]*np.array([1,1,-1]) # Blender Z-up -> glTF Y-up
    errors = {}
    for action in list(bpy.data.actions):
        activate(action)
        maximum = 0.
        duration = (action.frame_range[1]-action.frame_range[0])/24
        for i,fraction in enumerate((0,.173,.499,.807,1)):
            points = surface(duration*fraction)
            expected = reference[f'{actor}_{action.name}_{i}']
            tree = KDTree(len(expected))
            for index,point in enumerate(expected): tree.insert(point,index)
            tree.balance()
            maximum = max(maximum,max(tree.find(p)[2] for p in points))
        errors[action.name] = maximum
    # A separate implementation/import must agree with the complete skin.
    if max(errors.values()) >= 3e-5:
        np.savez_compressed(stage/f'{actor}-comparison-debug.npz',blender=points,native=expected)
        print('SURFACE_BOUNDS',actor,points.min(0),points.max(0),expected.min(0),expected.max(0),flush=True)
    assert max(errors.values()) < 3e-5, (actor,errors)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x,scene.render.resolution_y = 720,540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.show_shadows = False
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    neutral = reference[f'{actor}_Idle_A_0']
    height = float(np.ptp(neutral[:,1]))
    camera.data.ortho_scale = height*1.6
    scene.camera = camera
    output = stage/'blender-views'/actor
    output.mkdir(parents=True,exist_ok=True)
    for clip in ('Walk','Jog'):
        action = bpy.data.actions[clip]
        activate(action)
        duration = (action.frame_range[1]-action.frame_range[0])/24
        whole_cycle = np.concatenate([surface(duration*phase) for phase in np.linspace(0,1,25)])
        # Camera space is Blender Z-up. Frame the full body, including long
        # tails and multiple heads, across the entire cycle in each view.
        bounds = whole_cycle[:,[0,2,1]]*np.array([1,-1,1])
        for view,direction in {'front':(0,-3,.6),'rear':(0,3,.6),'side':(3,0,.6),'game':(2,-3,2)}.items():
            centre = Vector((0,0,height*.5))
            camera.location = centre+Vector(direction)*height
            camera.rotation_euler = (centre-camera.location).to_track_quat('-Z','Y').to_euler()
            basis = np.asarray(camera.rotation_euler.to_matrix())
            projected = bounds@basis[:,:2]
            low,high = projected.min(0),projected.max(0)
            offset = basis[:,:2]@((low+high)/2-np.asarray(centre)@basis[:,:2])
            camera.location += Vector(offset)
            camera.data.ortho_scale = max(high[0]-low[0],(high[1]-low[1])*720/540)*1.15
            for i,phase in enumerate((.07,.32,.57,.82)):
                surface(duration*phase)
                scene.render.filepath = str(output/f'{clip}-{view}-{i}.png')
                bpy.ops.render.render(write_still=True)
    reports.append({'actor':actor,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'surfaceErrors':errors,'tolerance':3e-5,'blender':bpy.app.version_string})
(stage/'blender-surfaces.json').write_text(json.dumps(reports,indent=2)+'\n')
print('UNDEAD_BLENDER_SURFACES_COMPLETE',flush=True)
