"""Author the MPFB Human study meshes in an isolated Blender process.

Run with Blender --background --factory-startup --python this_file -- ... .
MPFB and its CC0 system assets are local authoring dependencies, never runtime
dependencies. Raw meshes, editable presets and .blend stages go to --output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def extract_mesh(obj, prefix, arrays, allowed=None):
    bpy.context.view_layer.update()
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mesh.calc_loop_triangles()
    tris = [t for t in mesh.loop_triangles if allowed is None or all(v in allowed for v in t.vertices)]
    used = sorted({v for t in tris for v in t.vertices})
    remap = {v: i for i, v in enumerate(used)}
    arrays[prefix + '_vertices'] = np.array([obj.matrix_world @ mesh.vertices[v].co for v in used], dtype=np.float32)
    arrays[prefix + '_normals'] = np.array([mesh.vertices[v].normal for v in used], dtype=np.float32)
    arrays[prefix + '_triangles'] = np.array([[remap[v] for v in t.vertices] for t in tris], dtype=np.int32)
    uv = mesh.uv_layers.active
    arrays[prefix + '_uv'] = np.array([[list(uv.data[l].uv) for l in t.loops] for t in tris], dtype=np.float32)
    arrays[prefix + '_source_indices'] = np.array(used, dtype=np.int32)
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mpfb-source', type=Path, required=True, help='MPFB checkout src directory')
    parser.add_argument('--assets', type=Path, required=True, help='Extracted CC0 system asset pack')
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.mpfb_source.resolve()))
    # A source checkout is intentionally loaded for only this background run.
    # Redirect the extension user path rather than installing into player prefs.
    original = bpy.utils.extension_path_user
    bpy.utils.extension_path_user = lambda package, **kw: str(args.output / 'mpfb-profile') if package == 'mpfb' else original(package, **kw)
    bpy.ops.preferences.addon_enable(module='mpfb')
    from mpfb.services.humanservice import HumanService
    from mpfb.services.targetservice import TargetService

    profiles = json.loads(args.profiles.read_text())
    for sex, character in [('male', 'rowan'), ('female', 'mira')]:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        profile = profiles[character]
        macro = TargetService.get_default_macro_info_dict()
        macro.update(profile['macro'])
        body = HumanService.create_human(macro_detail_dict=macro)
        TargetService.bulk_load_targets(body, [{'target': k, 'value': v} for k, v in profile['targets'].items()])
        assets = args.assets.resolve()
        skin = assets / 'skins' / ('young_caucasian_' + sex) / ('young_caucasian_' + sex + '.mhmat')
        HumanService.set_character_skin(str(skin), body, skin_type='GAMEENGINE')
        eyes = HumanService.add_mhclo_asset(str(assets / 'eyes/high-poly/high-poly.mhclo'), body,
            asset_type='Eyes', subdiv_levels=0, material_type='GAMEENGINE', set_up_rigging=False)
        brow_name = 'eyebrow003' if sex == 'female' else 'eyebrow001'
        brows = HumanService.add_mhclo_asset(str(assets / 'eyebrows' / brow_name / (brow_name + '.mhclo')), body,
            asset_type='Eyebrows', subdiv_levels=0, material_type='GAMEENGINE', set_up_rigging=False)
        # Source texture is self-contained in the exported mesh metadata.
        eye_image = assets / 'eyes/materials' / ('green_eye.png' if sex == 'female' else 'brown_eye.png')
        HumanService.serialize_to_json_file(body, str(args.output / (sex + '.json')))
        body.modifiers['Hide helpers'].show_viewport = False
        bpy.context.view_layer.update()
        full = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        groups = {}
        for group in body.vertex_groups:
            groups[group.name] = [v.index for v in body.data.vertices if any(g.group == group.index and g.weight > .5 for g in v.groups)]
        landmarks = {k: list(sum((body.matrix_world @ full.vertices[i].co for i in ids), start=__import__('mathutils').Vector()) / len(ids))
            for k, ids in groups.items() if k.startswith('joint-') and ids}
        body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
        arrays = {}
        extract_mesh(body, 'body', arrays, set(groups['body']))
        extract_mesh(eyes, 'eye', arrays)
        extract_mesh(brows, 'brow', arrays)
        np.savez_compressed(args.output / (sex + '.npz'), **arrays)
        texture = next(n.image.filepath for n in body.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
        brow_texture = next(n.image.filepath for n in brows.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE' and n.image)
        info = {'sex': sex, 'character': character, 'blender': bpy.app.version_string,
            'coordinate_system': 'Blender Xright Yback Zup; meters; evaluated macro and detail shape keys',
            'joint_landmarks': landmarks, 'body_groups': groups, 'skin_texture': bpy.path.abspath(texture),
            'eye_texture': str(eye_image), 'brow_texture': bpy.path.abspath(brow_texture), 'profile': profile,
            'vertex_counts': {p: len(arrays[p + '_vertices']) for p in ['body', 'eye']},
            'triangle_counts': {p: len(arrays[p + '_triangles']) for p in ['body', 'eye']}}
        (args.output / (sex + '-mesh.json')).write_text(json.dumps(info, indent=2))
        body.modifiers['Hide helpers'].show_viewport = True
        bpy.ops.wm.save_as_mainfile(filepath=str(args.output / (sex + '.blend')))
        print('RL_MPFB_AUTHORED', sex, info['vertex_counts'], info['triangle_counts'])


if __name__ == '__main__':
    main()
