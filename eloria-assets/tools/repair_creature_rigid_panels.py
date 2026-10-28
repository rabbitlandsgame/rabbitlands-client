"""Create a review-only rigid-panel repair from explicit anatomical vertex IDs.

Restore the reference panel geometry and drive each intact panel with a new
isolated rigid control. Original controls, skin, clips and all non-panel vertex
attributes remain unchanged. No anatomical regions are inferred automatically.
"""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array, compact
from add_creature_bake_helpers import _check_pair, _states, _kabsch, _append_curve, _write_weights


def repair(reference, baked, regions, output, report):
    reference, baked, regions, output, report = map(lambda p: Path(p).resolve(), (reference, baked, regions, output, report))
    mapping = output.with_suffix('.vertex-ids.json')
    inputs = (reference, baked, regions)
    if len({output, report, mapping}) != 3 or any(p.exists() or p in inputs for p in (output, report, mapping)):
        raise ValueError('Use new versioned output and report paths')
    input_hashes = {p: digest(p) for p in inputs}
    recipe = json.loads(regions.read_text(encoding='utf-8'))
    if recipe['reference_sha256'] != digest(reference) or recipe['baked_sha256'] != digest(baked):
        raise ValueError('Anatomical recipe does not bind the selected inputs')
    source, base = NativeShapeAsset(reference), NativeShapeAsset(baked)
    _check_pair(source, base)
    if len(source.parts) != 1 or len(base.parts) != 1 or len(source.vertices) != len(base.vertices):
        raise ValueError('This panel adapter requires one corresponding primitive')
    part, source_part = base.parts[0], source.parts[0]
    node = part['node']
    document, binary = read_glb(baked)
    blob = bytearray(binary)
    source_primitive = source.d['meshes'][source.d['nodes'][source_part['node']]['mesh']]['primitives'][0]
    primitive = document['meshes'][document['nodes'][node]['mesh']]['primitives'][0]
    if not np.array_equal(accessor(source.d, source.b, source_primitive['indices']), accessor(base.d, base.b, primitive['indices'])):
        raise ValueError('Panel source topology differs')
    scenes = document['scenes']
    if not scenes or any(s.get('nodes', []) != scenes[0].get('nodes', []) for s in scenes):
        raise ValueError('An explicit common scene root set is required')
    panels = recipe['panels']
    if not panels or len({p['name'] for p in panels}) != len(panels):
        raise ValueError('Use nonempty uniquely named anatomical panels')
    for panel in panels:
        if not panel['vertices'] or any(type(v) is not int for v in panel['vertices']):
            raise ValueError('Panel vertex IDs must be explicit integers')
        if np.asarray(panel['root']).shape != (3,) or not np.isfinite(panel['root']).all():
            raise ValueError('Panel root must be a finite three-vector')
    ids = np.concatenate([np.asarray(p['vertices'], int) for p in panels])
    if len(ids) != len(set(ids.tolist())) or np.any(ids < 0) or np.any(ids >= len(base.vertices)):
        raise ValueError('Panel vertex sets must be disjoint valid original IDs')
    outside = np.ones(len(base.vertices), bool)
    outside[ids] = False
    training = _states(source, source, training=True)
    posed = np.asarray([source.skin(w, m) for w, m in zip(training['world'], training['morph'])])
    common = (source.rest[source_part['nodes']] @ source_part['bind'])[0]
    if not np.allclose(source_part['position'] @ common[:3].T, source.vertices, atol=4e-6, rtol=0):
        raise ValueError('Reference rest requires a separately prepared panel base')
    old_count = len(document['nodes'])
    wrapper = old_count
    document['nodes'].append({'name': 'RL_PanelRepair_' + digest(baked)[:8], 'children': list(scenes[0]['nodes'])})
    for scene in scenes:
        scene['nodes'] = [wrapper]
    skin = copy.deepcopy(document['skins'][document['nodes'][node]['skin']])
    binds, added_keys, controls = list(part['bind']), 0, []
    dense = np.zeros((len(base.vertices), len(skin['joints']) + len(recipe['panels'])))
    for slot in range(part['weights'].shape[1]):
        np.add.at(dense, (np.arange(len(base.vertices)), part['joints'][:, slot]), part['weights'][:, slot])
    for ordinal, panel in enumerate(recipe['panels']):
        chosen = np.asarray(panel['vertices'], int)
        rest = source.vertices[chosen]
        neutral = np.eye(4)
        neutral[:3, 3] = panel['root']
        world = np.asarray([_kabsch(rest, target[chosen]) @ neutral for target in posed])
        helper = len(document['nodes'])
        document['nodes'].append({'name': 'RL_PanelRepair_' + panel['name'], 'translation': neutral[:3, 3].tolist(),
                                  'rotation': [0., 0., 0., 1.], 'scale': [1., 1., 1.]})
        document['nodes'][wrapper]['children'].append(helper)
        palette = len(skin['joints'])
        skin['joints'].append(helper)
        binds.append(np.linalg.inv(neutral) @ common)
        dense[chosen] = 0
        dense[chosen, palette] = 1
        rotation = Rotation.from_matrix(world[:, :3, :3]).as_quat()
        for i in range(1, len(rotation)):
            if np.dot(rotation[i], rotation[i - 1]) < 0:
                rotation[i] *= -1
        max_step = 0.
        for animation in document['animations']:
            clock = training['clocks'][animation['name']]
            span = slice(clock['start'], clock['end'])
            for kind, values in [('translation', world[span, :3, 3]), ('rotation', rotation[span]),
                                 ('scale', np.ones((clock['end'] - clock['start'], 3)))]:
                added_keys += _append_curve(document, blob, animation, helper, kind, clock['times'], values)
            q = rotation[span]
            if len(q) > 1:
                max_step = max(max_step, float(np.degrees(2 * np.arccos(np.clip(np.abs(np.sum(q[:-1] * q[1:], axis=1)), 0, 1))).max()))
        # Measure the rigid approximation before interpolation and quantization.
        predicted = np.einsum('tij,vj->tvi', world[:, :3, :3], rest - neutral[:3, 3]) + world[:, None, :3, 3]
        error = np.linalg.norm(predicted - posed[:, chosen], axis=2)
        controls.append({'name': panel['name'], 'node': helper, 'vertices': len(chosen),
                         'training_maximum_position': float(error.max()), 'training_rms_position': float(np.sqrt(np.mean(error**2))),
                         'maximum_key_rotation_step_degrees': max_step})
    for field in ('POSITION', 'NORMAL', 'TANGENT'):
        if field not in primitive['attributes'] or field not in source_primitive['attributes']:
            continue
        values = accessor(base.d, base.b, primitive['attributes'][field])
        values[ids] = accessor(source.d, source.b, source_primitive['attributes'][field])[ids]
        primitive['attributes'][field] = append_array(document, blob, values, 'VEC4' if field == 'TANGENT' else 'VEC3')
    weight_report = _write_weights(document, blob, base, primitive, dense, ids)
    skin['skeleton'] = wrapper
    skin['inverseBindMatrices'] = append_array(document, blob, np.asarray(binds).transpose(0, 2, 1).reshape(-1, 16), 'MAT4')
    document['skins'].append(skin)
    document['nodes'][node]['skin'] = len(document['skins']) - 1
    document, binary, packing = compact(document, blob, collapse_paths=())
    if any(digest(p) != expected for p, expected in input_hashes.items()):
        raise ValueError('Input changed while fitting; no candidate written')
    write_glb(output, document, binary)
    result = NativeShapeAsset(output)
    assert len(result.vertices) == len(base.vertices)
    for key in ('materials', 'textures', 'samplers'):
        assert result.d.get(key) == base.d.get(key)
    for old, new in zip(base.d['animations'], result.d['animations']):
        assert old['channels'] == new['channels'][:len(old['channels'])]
        for a, b in zip(old['samplers'], new['samplers']):
            for key in ('input', 'output'):
                assert np.array_equal(accessor(base.d, base.b, a[key]), accessor(result.d, result.b, b[key]))
    for field, index in base.d['meshes'][base.d['nodes'][node]['mesh']]['primitives'][0]['attributes'].items():
        other = result.d['meshes'][result.d['nodes'][node]['mesh']]['primitives'][0]['attributes'][field]
        assert np.array_equal(accessor(base.d, base.b, index)[outside], accessor(result.d, result.b, other)[outside]), field
    assert np.array_equal(result.rest[:old_count], base.rest)
    # New skin and scene wrapper retain ordinal correspondence, not a guessed nearest-point map.
    mapping.write_text(json.dumps(list(range(len(base.vertices)))) + '\n', encoding='utf-8')
    receipt = {'status': 'review_candidate_requires_client_blender_visual_checks', 'reference_sha256': digest(reference),
               'baked_sha256': digest(baked), 'regions_sha256': digest(regions), 'sha256': digest(output),
               'raw_bytes': output.stat().st_size, 'previous_raw_bytes': baked.stat().st_size, 'added_controls': len(controls),
               'added_keys': added_keys, 'panel_vertices': len(ids), 'nonpanel_attributes_exact': True,
               'original_node_rest_and_animation_curves_exact': True, 'original_vertex_order_and_indices_exact': True,
               'corrective_shapes': 0, 'controls': controls, 'weight_storage': weight_report, 'packing': packing,
               'vertex_mapping_sha256': digest(mapping), 'scope': 'Rigid panel shape repair against explicit source trajectories; all other baked geometry/motion retained. Training fit is not visual acceptance.'}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('reference', 'baked', 'regions', 'output', 'report'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.reference, args.baked, args.regions, args.output, args.report), indent=2))
