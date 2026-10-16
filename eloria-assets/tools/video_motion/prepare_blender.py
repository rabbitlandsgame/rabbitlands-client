"""Render a GLB's actual rest geometry and record its orthographic camera.

Run with Blender --background --python this_file -- SOURCE_GLB OUTPUT_DIR.
This creates a new scene and never saves over the supplied model.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def main():
    source, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    for obj in bpy.data.objects:
        if obj.animation_data:
            obj.animation_data.action = None
            for track in obj.animation_data.nla_tracks:
                track.mute = True
        if obj.type == 'ARMATURE':
            obj.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    shapes = {b.custom_shape for a in bpy.data.objects if a.type == 'ARMATURE' for b in a.pose.bones}
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render and o not in shapes]
    dg = bpy.context.evaluated_depsgraph_get()
    vertices = []
    for obj in meshes:
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.to_mesh()
        vertices.extend([evaluated.matrix_world @ v.co for v in mesh.vertices])
        evaluated.to_mesh_clear()
    points = np.asarray(vertices)
    lo, hi = points.min(0), points.max(0)
    center = Vector((lo + hi) / 2)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.display.render_aa = '16'
    sh = scene.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'TEXTURE'
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_specular_highlight = False
    sh.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('Neutral reference background')
    scene.world.color = (.45, .45, .45)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    # ortho_scale is the horizontal extent for a landscape frame.
    camera.data.ortho_scale = max((hi[1] - lo[1]) / .73,
                                 (hi[2] - lo[2]) * 960 / 540 / .76)
    scene.camera = camera
    extent = float(max(hi - lo))
    views = {'side': (5, 0, 0), 'front': (0, -5, 0),
             'rear': (0, 5, 0), 'three_quarter': (4, -5, 2)}
    camera_record = None
    for name, direction in views.items():
        camera.location = center + Vector(direction) * extent
        camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.view_layer.update()
        scene.render.filepath = str(output / ('reference.png' if name == 'side' else name + '.png'))
        bpy.ops.render.render(write_still=True)
        if name == 'side':
            def project_gltf(point):
                # Blender import maps glTF (x,y,z) to Blender (x,-z,y).
                p = Vector((point[0], -point[2], point[1]))
                uv = world_to_camera_view(scene, camera, p)
                return np.array([uv.x * 960, (1 - uv.y) * 540])
            origin = project_gltf((0, 0, 0))
            matrix = np.column_stack([project_gltf(np.eye(3)[i]) - origin for i in range(3)])
            camera_record = {'schema_version': 1, 'width': 960, 'height': 540,
                'projection': 'orthographic', 'pixel_matrix_gltf': matrix.tolist(),
                'pixel_offset': origin.tolist(), 'up_axis': [0, 1, 0],
                'forward_axis': [0, 0, 1], 'depth_axis': [1, 0, 0],
                'gltf_to_blender': [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
                'source_glb': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'blender_version': bpy.app.version_string,
                'bounds_blender': [lo.tolist(), hi.tolist()], 'ortho_scale': camera.data.ortho_scale}
    (output / 'camera.json').write_text(json.dumps(camera_record, indent=2), encoding='utf-8')
    print('REFERENCE_COMPLETE', json.dumps(camera_record), flush=True)


if __name__ == '__main__':
    main()
