"""Small CPU-only rigid-helper feasibility, basis, seam and preservation checks."""
import copy
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_creature_bake_helpers import helper_bake, _append_typed
from video_motion.asset import accessor, read_glb, write_glb, digest
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array, compact


def pair(folder, influences=4):
    document = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
        'bufferViews': [], 'accessors': [], 'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'name': 'placed_nonuniform_parent', 'children': [1, 2],
                   'translation': [3., -2., 1.], 'scale': [2., 3., .5]},
                  {'name': 'original_bone'}, {'name': 'body', 'mesh': 0, 'skin': 0}],
        'skins': [{'joints': [1], 'skeleton': 0}], 'animations': [],
        'materials': [{'name': 'retained', 'pbrMetallicRoughness': {'roughnessFactor': .8}}]}
    blob = bytearray()
    palette = [1]
    if influences == 8:
        palette += list(range(3, 10))
        document['nodes'] += [{'name': f'original_bone_{i}'} for i in range(2, 9)]
        document['nodes'][0]['children'] += list(range(3, 10))
        document['skins'][0]['joints'] = palette
    positions = np.array([[x * .02, y * .02, 0] for y in range(4) for x in range(4)])
    positions = np.r_[positions, positions[:1]]  # A true UV/hard-normal seam.
    normal = np.tile([0., 0, 1], (17, 1))
    normal[-1] = [0, 1, 0]
    attrs = {'POSITION': append_array(document, blob, positions, 'VEC3'),
             'NORMAL': append_array(document, blob, normal, 'VEC3'),
             'TEXCOORD_0': append_array(document, blob, positions[:, :2] / .06, 'VEC2')}
    for k in range(influences // 4):
        joints = np.tile(np.arange(k * 4, k * 4 + 4), (17, 1)).astype('u1') if influences == 8 else np.zeros((17, 4), dtype='u1')
        attrs[f'JOINTS_{k}'] = _append_typed(document, blob, joints,
                                            {'componentType': 5121, 'type': 'VEC4'})
        weights = np.full((17, 4), .125) if influences == 8 else np.tile([1., 0, 0, 0], (17, 1))
        attrs[f'WEIGHTS_{k}'] = append_array(document, blob, weights, 'VEC4')
    indices = []
    for y in range(3):
        for x in range(3):
            a = y * 4 + x
            indices += [a, a + 1, a + 4, a + 1, a + 5, a + 4]
    indices[0] = 16
    index = _append_typed(document, blob, np.array(indices, dtype='<u2')[:, None],
                          {'componentType': 5123, 'type': 'SCALAR'})
    delta = np.zeros_like(positions)
    delta[[0, 1, 4, 5, 16], 2] = .2
    morph = append_array(document, blob, delta, 'VEC3')
    document['meshes'] = [{'primitives': [{'attributes': attrs, 'indices': index,
        'targets': [{'POSITION': morph}], 'material': 0}], 'weights': [0.],
        'extras': {'rabbitlands_actor_bounds_v1': {'position': [0, 0, 0], 'size': [.06, .06, .2]},
                   'retained_mount_fixture': {'unchanged': True}}}]
    document['skins'][0]['inverseBindMatrices'] = append_array(document, blob,
        np.tile(np.eye(4).reshape(1, 16), (len(palette), 1)), 'MAT4')
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\0\xff\xff\xff\xff')) + chunk(b'IEND', b'')
    blob.extend(b'\0' * (-len(blob) % 4))
    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(png)})
    blob.extend(png)
    document['images'] = [{'bufferView': len(document['bufferViews']) - 1, 'mimeType': 'image/png'}]
    document['textures'] = [{'source': 0}]
    document['materials'][0]['pbrMetallicRoughness']['baseColorTexture'] = {'index': 0}
    times = append_array(document, blob, (np.arange(7) / 30)[:, None], 'SCALAR')
    q = Rotation.from_euler('z', np.linspace(-.03, .03, 7)[:, None]).as_quat()
    translation = np.array([3., -2., 1.]) + np.arange(7)[:, None] * [.002, .001, 0]
    for clip in ('Fly', 'Gallop'):
        samplers, channels = [], []
        for path, values in [('translation', translation), ('rotation', q),
                              ('scale', np.tile([2., 3., .5], (7, 1)))]:
            samplers.append({'input': times, 'output': append_array(document, blob, values,
                'VEC4' if path == 'rotation' else 'VEC3')})
            channels.append({'sampler': len(samplers) - 1, 'target': {'node': 0, 'path': path}})
        samplers.append({'input': times, 'output': append_array(document, blob,
            np.array([0., .5, 1., .75, .2, 0, 0])[:, None], 'SCALAR')})
        channels.append({'sampler': len(samplers) - 1, 'target': {'node': 2, 'path': 'weights'}})
        document['animations'].append({'name': clip, 'samplers': samplers, 'channels': channels})
    reference = folder / 'reference-30.glb'
    write_glb(reference, document, blob)
    baked_document = copy.deepcopy(document)
    baked_document['meshes'][0]['primitives'][0].pop('targets')
    baked_document['meshes'][0].pop('weights')
    for animation in baked_document['animations']:
        animation['channels'] = animation['channels'][:3]
        animation['samplers'] = animation['samplers'][:3]
    baked_document, baked_blob, _ = compact(baked_document, blob, collapse_paths=())
    baked = folder / 'baked.glb'
    write_glb(baked, baked_document, baked_blob)
    return reference, baked


@pytest.mark.parametrize('influences', [4, 8])
def test_one_helper_explains_local_deformation_preserving_prefix_and_seams(tmp_path, influences):
    reference, baked = pair(tmp_path, influences)
    original_hashes = digest(reference), digest(baked)
    output = tmp_path / 'helper-v1.glb'
    result = helper_bake(reference, baked, output, helper_count=4, report=tmp_path / 'helper.json')
    assert (digest(reference), digest(baked)) == original_hashes
    assert result['added_bones'] == 1
    assert result['before']['all']['maximum_position'] > .09
    assert result['after']['all']['maximum_position'] < .0001
    assert result['after']['neutral']['maximum_position'] < 1e-6
    assert result['maximum_prefix_world_matrix_error'] == 0
    assert result['maximum_prefix_rest_matrix_error'] == 0
    assert result['original_bone_curve_arrays_bit_exact']
    assert result['identity_vertex_mapping']['output_original_vertex_ids'] == list(range(17))
    assert result['identity_proof']['certified_seam_groups_verified'] == 1
    asset = NativeShapeAsset(output)
    original = NativeShapeAsset(baked)
    assert len(asset.d['skins']) == len(original.d['skins']) + 1
    wrapper = result['scene_path_change']['identity_wrapper_node']
    assert asset.d['scenes'][0]['nodes'] == [wrapper]
    helper = result['controls'][0]['node']
    assert asset.d['nodes'][helper]['scale'] == [1., 1., 1.]
    for animation in asset.d['animations']:
        helper_paths = {c['target']['path'] for c in animation['channels'] if c['target']['node'] == helper}
        assert helper_paths == {'translation', 'rotation', 'scale'}
        for c in animation['channels']:
            if c['target']['node'] != helper:
                continue
            times = accessor(asset.d, asset.b, animation['samplers'][c['sampler']]['input']).ravel()
            assert len(times) < 2 or np.diff(times).min() >= 1 / 30 - 2e-5
    part = asset.parts[0]
    assert part['joints'].shape[1] == influences
    assert np.max((part['weights'] > 0).sum(1)) <= influences
    assert np.allclose(part['weights'].sum(1), 1)
    assert np.array_equal(part['joints'][0], part['joints'][16])
    assert np.array_equal(part['weights'][0], part['weights'][16])
    assert not any(p.get('targets') for m in asset.d['meshes'] for p in m['primitives'])
    assert not result['actual_client_validated']
    with pytest.raises(ValueError, match='new version'):
        helper_bake(reference, baked, output)


def test_bad_input_prefix_is_rejected_without_mutation(tmp_path):
    reference, baked = pair(tmp_path)
    document, blob = read_glb(baked)
    document['nodes'][0]['translation'][0] += 1
    write_glb(baked, document, blob)
    before = digest(reference), digest(baked)
    with pytest.raises(ValueError, match='rest mismatch'):
        helper_bake(reference, baked, tmp_path / 'bad.glb')
    assert not (tmp_path / 'bad.glb').exists()
    assert before == (digest(reference), digest(baked))


def test_no_benefit_is_an_exact_copy_not_a_forced_rig_rewrite(tmp_path):
    reference, baked = pair(tmp_path)
    document, blob = read_glb(reference)
    blob = bytearray(blob)
    primitive = document['meshes'][0]['primitives'][0]
    primitive['targets'][0]['POSITION'] = append_array(document, blob, np.zeros((17, 3)), 'VEC3')
    write_glb(reference, document, blob)
    result = helper_bake(reference, baked, tmp_path / 'no-helper.glb')
    assert result['added_bones'] == 0
    assert result['status'] == 'no_beneficial_helper_found'
    assert (tmp_path / 'no-helper.glb').read_bytes() == baked.read_bytes()
