"""Export the audited least-squares static tortoise mesh for visual review.

Uses the private audit's fixed position/normal fits, original skin and all seven
30 FPS bone animations. Removes all runtime morphs. Never installs the output.
"""
from pathlib import Path
import json
import sys
import numpy as np
from video_motion.asset import read_glb, accessor, write_glb, digest
from video_motion.packing import append_array, compact

ROOT = Path(__file__).resolve().parents[2]


def build():
    output = ROOT / '.local/tortoise-corrective-repair'
    source = ROOT / '.local/creature-sampling/crystalback_tortoise/fps-30/crystalback_tortoise_30.glb'
    assert digest(source) == '01b3a309b5fe61ed6c7845aee5bd9552df62496af9d205928b72381a2aeeaf9c'
    fit_path = output / 'fit-data.npz'
    normal_path = output / 'original-normal-fit.npz'
    fit = np.load(fit_path)
    document, raw = read_glb(source)
    blob = bytearray(raw)
    mesh = document['meshes'][0]
    primitive = mesh['primitives'][0]
    base = accessor(document, raw, primitive['attributes']['POSITION'])
    assert np.array_equal(base, fit['base'])
    position = base.astype(float) + fit['static']
    normal = np.load(normal_path)['normal']
    assert position.shape == normal.shape == (3328, 3)
    assert np.isfinite(position).all() and np.isfinite(normal).all()
    primitive['attributes']['POSITION'] = append_array(document, blob, position, 'VEC3')
    primitive['attributes']['NORMAL'] = append_array(document, blob, normal, 'VEC3')
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
    candidate = output / 'crystalback_tortoise_static_bake.glb'
    write_glb(candidate, document, binary)
    sys.path.insert(0, str(ROOT / 'godot-client/tools'))
    from creature_compression import encode, decode
    payload = encode(candidate.read_bytes())
    assert decode(payload) == candidate.read_bytes()
    (output / 'static-bake.rlcz').write_bytes(payload)
    report = {
        'artifact': candidate.relative_to(ROOT).as_posix(), 'sha256': digest(candidate),
        'label': 'MESH BAKE / Fixed mesh and normals / No corrective shapes',
        'source_sha256': digest(source), 'fit_sha256': digest(fit_path),
        'normal_fit_sha256': digest(normal_path), 'raw_bytes': candidate.stat().st_size,
        'rlcz_bytes': len(payload), 'corrective_targets': 0, 'corrective_gpu_buffer_bytes': 0,
        'roundtrip_verified': True, 'status': 'visual_experiment_not_installed',
        'method': 'Best constant local vertex displacement from the prior audit, with original-skin fixed normal fit. This is a least-squares mesh across training poses, not a selected single animation frame.',
        'preserved': ['original skin weights and joints', 'all original bones, binds and hierarchy',
                      'all seven bone animation curves and timing', 'shell, textures, materials, UVs and triangle indices'],
        'changed': ['body rest positions and normals', 'all runtime morph targets and weight channels removed'],
        'expected_surface_error': json.loads((output / 'deformation-audit.json').read_text(encoding='utf-8'))['best_static_original_skin'],
        'packing': packing}
    (output / 'static-bake-build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    build()
