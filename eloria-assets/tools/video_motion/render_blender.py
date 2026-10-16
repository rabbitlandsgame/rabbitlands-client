"""Reimport final GLBs and render normal-speed multi-view evidence."""
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
clip='Walk'
selected_views=None
sample_only=False
output_names=None
if '--output-names' in args:
    index=args.index('--output-names');output_names=args[index+1].split(',');args=args[:index]+args[index+2:]
if '--sample-only' in args:
    args.remove('--sample-only');sample_only=True
if '--views' in args:
    index=args.index('--views');selected_views=args[index+1].split(',');args=args[:index]+args[index+2:]
if '--clip' in args:
    index=args.index('--clip');clip=args[index+1];args=args[:index]+args[index+2:]
output = Path(args[0]).resolve()
output.mkdir(parents=True, exist_ok=True)
if output_names and len(output_names)!=len(args[1:]):raise ValueError('One output name is required per imported model')
for file_index,file in enumerate(args[1:]):
    source = Path(file).resolve()
    folder = output / (output_names[file_index] if output_names else source.stem)
    folder.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 24
    bpy.ops.import_scene.gltf(filepath=str(source))
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    shapes = {b.custom_shape for a in arms for b in a.pose.bones}
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o not in shapes and not o.hide_render]
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data.action = None
            for track in obj.animation_data.nla_tracks:
                track.mute = True
    action = bpy.data.actions.get(clip)
    if not action:
        raise RuntimeError(f'{clip} action not found after fresh import')
    for arm in arms:
        arm.animation_data_create()
        arm.animation_data.action = action
        if action.slots:
            arm.animation_data.action_slot = action.slots[0]
    start, end = map(float, action.frame_range)
    source_bytes=source.read_bytes()
    glb_document=json.loads(source_bytes[20:20+int.from_bytes(source_bytes[12:16],'little')])
    clip_document=next(a for a in glb_document['animations'] if a.get('name')==clip)
    loop=bool(clip_document.get('extras',{}).get('loop',clip=='Walk'))
    frame_count=round(end-start)+(0 if loop else 1)
    def vertices(frame):
        scene.frame_set(int(frame), subframe=frame - int(frame))
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        points = []
        for mesh in meshes:
            ev = mesh.evaluated_get(dg)
            data = ev.to_mesh()
            points.extend([ev.matrix_world @ v.co for v in data.vertices])
            ev.to_mesh_clear()
        return np.asarray(points)
    sampled = [vertices(start + (end - start) * u) for u in np.linspace(0, 1, 5)]
    # Full preview cadence determines framing; five validation phases alone
    # can miss an extended swing paw, especially in the tilted game camera.
    bounds = np.concatenate([vertices(start+f) for f in range(frame_count)])
    lo, hi = bounds.min(0), bounds.max(0)
    center = Vector((lo + hi) / 2)
    extent = float(max(hi - lo))
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 480
    scene.render.resolution_y = 270
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.display.render_aa = '8'
    sh = scene.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'TEXTURE'
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_specular_highlight = False
    sh.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('Review background')
    scene.world.color = (.4, .4, .4)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -.001))
    floor = bpy.context.object
    material = bpy.data.materials.new('Ground')
    material.diffuse_color = (.32, .34, .37, 1)
    floor.data.materials.append(material)
    # A separate moving-ground view makes stance locking observable for an
    # in-place clip. Ground travels backwards at the clip's declared speed.
    speed = clip_document.get('extras',{}).get('virtual_forward_speed',0)
    distance = speed * (end-start)/scene.render.fps
    spacing = distance/max(1,round(distance/.25)) if distance else .25
    stripes = []
    stripe_material = bpy.data.materials.new('Ground distance marks')
    stripe_material.diffuse_color = (.15,.17,.20,1)
    for index in range(-25,26):
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,index*spacing,-.001))
        stripe = bpy.context.object
        stripe.scale = (8,.006,.0004)
        stripe.data.materials.append(stripe_material)
        stripe.hide_render = True
        stripes.append((stripe,index*spacing))
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = max((hi[1] - lo[1]) * 1.3, (hi[2] - lo[2]) * 1.78 * 1.25)
    scene.camera = camera
    views = {'side': (5, 0, 0), 'front': (0, -5, .2), 'rear':(0,5,.2), 'game': (4, -5, 3), 'travel':(4,-5,2),
             'other_side':(-4,-5,3), 'tail_view':(-4,5,2.5), 'top':(0,0,5)}
    if selected_views:views={k:v for k,v in views.items() if k in selected_views}
    for view, direction in views.items():
        camera.location = center + Vector(direction) * extent
        camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
        basis = np.asarray(camera.rotation_euler.to_matrix())
        projected = bounds @ basis[:,:2]
        screen_lo,screen_hi = projected.min(0),projected.max(0)
        screen_center = (screen_lo+screen_hi)/2
        offset = basis[:,:2] @ (screen_center-np.asarray(center) @ basis[:,:2])
        camera.location += Vector(offset)
        camera.data.ortho_scale = max(screen_hi[0]-screen_lo[0],
            (screen_hi[1]-screen_lo[1])*scene.render.resolution_x/scene.render.resolution_y)*1.15
        for frame in (sorted(set(round(v) for v in np.linspace(0,frame_count-1,13))) if sample_only else range(frame_count)):
            vertices(start + frame)
            for stripe,base in stripes:
                stripe.hide_render = view != 'travel'
                stripe.location.y = base + speed*frame/scene.render.fps
            scene.render.filepath = str(folder / f'{view}__{frame:04d}.png')
            bpy.ops.render.render(write_still=True)
    record = {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'blender': bpy.app.version_string, 'fps': 24, 'action': clip, 'loop':loop,'frames':frame_count,'frame_range': [start, end],
        'available_actions': sorted(a.name for a in bpy.data.actions),'sample_only':sample_only,
        'sample_phases': np.linspace(0, 1, 5).tolist(),
        'bounds_blender': [[v.min(0).tolist(), v.max(0).tolist()] for v in sampled],
        'finite_geometry': bool(np.isfinite(bounds).all()), 'views':list(views),
        'camera_policy':'Framed across the complete cycle; opposite side and rear quarter reveal laterally curved rest tails.'}
    (folder / 'fresh-import.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print('FRESH_IMPORT_COMPLETE', source.name, flush=True)
