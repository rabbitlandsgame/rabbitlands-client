"""Export the audited least-squares static tortoise mesh for visual review.

Uses private fixed position/normal fits and optional fitted four-influence skin,
with all seven 30 FPS bone animations. Removes all morphs. Never installs output.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
from video_motion.asset import read_glb, accessor, write_glb, digest
from video_motion.packing import append_array, compact

ROOT = Path(__file__).resolve().parents[2]


def build(fit_mode='original'):
    output = ROOT / '.local/tortoise-corrective-repair'
    source = ROOT / '.local/creature-sampling/crystalback_tortoise/fps-30/crystalback_tortoise_30.glb'
    assert digest(source) == '01b3a309b5fe61ed6c7845aee5bd9552df62496af9d205928b72381a2aeeaf9c'
    fit_names = {'original': 'fit-data', 'refined': 'refined_mesh_and_weights_4', 'robust': 'robust_mesh_weights_4'}
    stem = fit_names[fit_mode]
    fit_path = output / f'{stem}.npz'
    normal_path = output / ('original-normal-fit.npz' if fit_mode == 'original' else f'{stem}-normal-fit.npz')
    fit = np.load(fit_path)
    document, raw = read_glb(source)
    blob = bytearray(raw)
    mesh = document['meshes'][0]
    primitive = mesh['primitives'][0]
    base = accessor(document, raw, primitive['attributes']['POSITION'])
    if fit_mode == 'original':
        assert np.array_equal(base, fit['base'])
    position = base.astype(float) + fit['static'] if fit_mode == 'original' else fit['base']
    normal = np.load(normal_path)['normal']
    assert position.shape == normal.shape == (3328, 3)
    assert np.isfinite(position).all() and np.isfinite(normal).all()
    primitive['attributes']['POSITION'] = append_array(document, blob, position, 'VEC3')
    primitive['attributes']['NORMAL'] = append_array(document, blob, normal, 'VEC3')
    if fit_mode != 'original':
        dense = fit['weights']
        joints = np.argsort(-dense, axis=1, kind='stable')[:, :4]
        weights = np.take_along_axis(dense, joints, axis=1)
        weights /= weights.sum(axis=1, keepdims=True)
        assert joints.max() < 256 and np.isfinite(weights).all()
        packed_joints = np.ascontiguousarray(joints, dtype='u1')
        blob.extend(b'\0' * (-len(blob) % 4))
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': packed_joints.nbytes})
        blob.extend(packed_joints.tobytes())
        document['accessors'].append({'bufferView': len(document['bufferViews']) - 1,
                                      'componentType': 5121, 'count': len(base), 'type': 'VEC4'})
        primitive['attributes']['JOINTS_0'] = len(document['accessors']) - 1
        primitive['attributes']['WEIGHTS_0'] = append_array(document, blob, weights, 'VEC4')
    primitive.pop('targets')
    mesh.pop('weights', None)
    mesh.get('extras', {}).pop('targetNames', None)
    for node in document['nodes']:
        if node.get('mesh') == 0:
            node.pop('weights', None)
    # Preserve the original logical presentation envelope so a different static
    # mesh AABB does not also move the actor's root/ground placement.
    metadata = json.loads((output / 'key-motion/metadata.json').read_text(encoding='utf-8'))
    reference_mesh = metadata['descriptions'][0]['meshes'][0]
    mesh.setdefault('extras', {})['rabbitlands_actor_bounds_v1'] = {
        'position': reference_mesh['aabb_position'], 'size': reference_mesh['aabb_size']}
    for animation in document['animations']:
        channels = [channel for channel in animation['channels'] if channel['target']['path'] != 'weights']
        retained = sorted({channel['sampler'] for channel in channels})
        remap = {index: new for new, index in enumerate(retained)}
        for channel in channels:
            channel['sampler'] = remap[channel['sampler']]
        animation['channels'] = channels
        animation['samplers'] = [animation['samplers'][index] for index in retained]
    document, binary, packing = compact(document, blob)
    suffix = '' if fit_mode == 'original' else f'_{fit_mode}'
    candidate = output / f'crystalback_tortoise_static_bake{suffix}.glb'
    write_glb(candidate, document, binary)
    sys.path.insert(0, str(ROOT / 'godot-client/tools'))
    from creature_compression import encode, decode
    payload = encode(candidate.read_bytes())
    assert decode(payload) == candidate.read_bytes()
    (output / f'static-bake{suffix}.rlcz').write_bytes(payload)
    report = {
        'artifact': candidate.relative_to(ROOT).as_posix(), 'sha256': digest(candidate),
        'label': 'MESH BAKE / Fixed mesh and normals / No corrective shapes' if fit_mode == 'original' else f'BAKE V2 / {fit_mode.title()} mesh + skin / Zero shapes',
        'source_sha256': digest(source), 'fit_sha256': digest(fit_path),
        'normal_fit_sha256': digest(normal_path), 'raw_bytes': candidate.stat().st_size,
        'rlcz_bytes': len(payload), 'corrective_targets': 0, 'corrective_gpu_buffer_bytes': 0,
        'roundtrip_verified': True, 'status': 'visual_experiment_not_installed',
        'method': 'Best constant local vertex displacement from the prior audit, with original-skin fixed normal fit. This is a least-squares mesh across training poses, not a selected single animation frame.' if fit_mode == 'original' else f'{fit_mode.title()} constant mesh and four-influence skin fit across training poses; fixed normal fit for the resulting skin.',
        'fit_mode': fit_mode,
        'preserved': (['original skin weights and joints'] if fit_mode == 'original' else ['four skin influences per vertex']) + ['all original bones, binds and hierarchy',
                      'all seven bone animation curves and timing', 'shell, textures, materials, UVs and triangle indices'],
        'changed': ['body rest positions and normals', 'all runtime morph targets and weight channels removed'] + ([] if fit_mode == 'original' else ['body skin weights and joint assignments']),
        'expected_surface_error': json.loads((output / 'deformation-audit.json').read_text(encoding='utf-8'))['best_static_original_skin'] if fit_mode == 'original' else None,
        'packing': packing}
    (output / f'static-bake{suffix}-build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit', choices=['original', 'refined', 'robust'], default='original')
    build(parser.parse_args().fit)
