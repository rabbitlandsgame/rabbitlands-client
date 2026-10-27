"""Exact attribute/skin preservation and conservative partition boundaries."""
import copy

import numpy as np
import pytest

from test_crystalback_correctives import source_fixture
from video_motion.asset import read_glb
from video_motion.partial_correctives import raw_array, split_corrective_partition


def fixture(tmp_path, zero=True):
    path, _ = source_fixture(tmp_path)
    document, binary = read_glb(path)
    binary = bytearray(binary)
    target = document['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    spec = document['accessors'][target]
    view = document['bufferViews'][spec['bufferView']]
    if zero:
        np.ndarray((6, 3), '<f4', binary, offset=view['byteOffset'])[3:] = 0
    profile = {'source_node': 1, 'primitive': 0, 'vertex_ids': [3, 4, 5],
               'mode': 'preserve_skin', 'coat_pattern_height': 3.125}
    return document, binary, profile


def test_zero_partition_preserves_geometry_skin_and_target_bits(tmp_path):
    d, b, profile = fixture(tmp_path)
    original = copy.deepcopy(d)
    new, blob, report = split_corrective_partition(d, b, profile)
    assert d == original
    assert report['all_candidate_original_vertex_ids'] == list(range(6))
    assert new['nodes'][1] == d['nodes'][1]
    assert new['nodes'][2]['children'] == [0, 1, 3]
    old = d['meshes'][0]['primitives'][0]
    for mesh, ids in zip(new['meshes'], [np.arange(3), np.arange(3, 6)]):
        assert mesh['extras']['rabbitlands_coat_pattern_height'] == 3.125
        primitive = mesh['primitives'][0]
        for field, old_index in old['attributes'].items():
            index = primitive['attributes'][field]
            assert new['accessors'][index]['componentType'] == d['accessors'][old_index]['componentType']
            assert raw_array(new, blob, index).tobytes() == raw_array(d, b, old_index)[ids].tobytes()
    assert 'targets' not in new['meshes'][1]['primitives'][0]
    assert 'weights' not in new['nodes'][3]
    remainder_layout = new['meshes'][0]['extras']['rabbitlands_surface_partition_v1']
    selected_layout = new['meshes'][1]['extras']['rabbitlands_surface_partition_v1']
    assert remainder_layout['selected_triangles'] == selected_layout['selected_triangles'] == [1]
    assert remainder_layout['source_vertices'] == 6 and remainder_layout['source_triangles'] == 2
    assert remainder_layout['role'] == 'remainder' and selected_layout['role'] == 'selected'
    assert remainder_layout['group'] == selected_layout['group']
    target = new['meshes'][0]['primitives'][0]['targets'][0]['POSITION']
    assert raw_array(new, blob, target).tobytes() == raw_array(d, b, old['targets'][0]['POSITION'])[:3].tobytes()


def test_raw_normalized_integer_storage_is_not_rounded():
    values = np.array([[1, 32768], [65535, 12345]], '<u2')
    d = {'accessors': [{'componentType': 5123, 'count': 2, 'type': 'VEC2', 'normalized': True, 'bufferView': 0}],
         'bufferViews': [{'buffer': 0, 'byteLength': values.nbytes}]}
    assert raw_array(d, values.tobytes(), 0).tobytes() == values.tobytes()


@pytest.mark.parametrize('change', ['nonzero', 'triangle', 'duplicate', 'order', 'whole', 'mode', 'height', 'shared'])
def test_unsafe_partitions_fail_closed(tmp_path, change):
    d, b, p = fixture(tmp_path, zero=change != 'nonzero')
    if change == 'triangle': p['vertex_ids'] = [2, 4, 5]
    if change == 'duplicate': p['vertex_ids'] = [3, 3, 5]
    if change == 'order': p['vertex_ids'] = [5, 4, 3]
    if change == 'whole': p['vertex_ids'] = list(range(6))
    if change == 'mode': p['mode'] = 'guess'
    if change == 'height': p['coat_pattern_height'] = float('nan')
    if change == 'shared': d['nodes'].append(dict(d['nodes'][1]))
    with pytest.raises(ValueError): split_corrective_partition(d, b, p)


def test_arbitrary_existing_owner_keeps_source_hierarchy(tmp_path):
    d, b, p = fixture(tmp_path, zero=False)
    p.update(mode='rigid', owner_joint=0)
    new, blob, _ = split_corrective_partition(d, b, p)
    pr = new['meshes'][1]['primitives'][0]
    assert np.all(raw_array(new, blob, pr['attributes']['JOINTS_0']) == 0)
    np.testing.assert_array_equal(raw_array(new, blob, pr['attributes']['WEIGHTS_0']), np.tile([1, 0, 0, 0], (3, 1)))
    assert new['skins'] == d['skins']


def test_eight_influence_attributes_are_retained(tmp_path):
    d, b, p = fixture(tmp_path)
    pr = d['meshes'][0]['primitives'][0]
    for field, values, component in [('JOINTS_1', np.zeros((6, 4), 'u1'), 5121), ('WEIGHTS_1', np.tile([.5, 0, 0, 0], (6, 1)).astype('<f4'), 5126)]:
        b.extend(b'\0' * (-len(b) % 4))
        d['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': values.nbytes})
        b.extend(values.tobytes())
        d['accessors'].append({'bufferView': len(d['bufferViews']) - 1, 'componentType': component, 'count': 6, 'type': 'VEC4'})
        pr['attributes'][field] = len(d['accessors']) - 1
    new, blob, _ = split_corrective_partition(d, b, p)
    free = new['meshes'][1]['primitives'][0]
    assert raw_array(new, blob, free['attributes']['JOINTS_1']).dtype == np.dtype('u1')
    np.testing.assert_array_equal(raw_array(new, blob, free['attributes']['WEIGHTS_1']), np.tile([.5, 0, 0, 0], (3, 1)))


def test_changed_skin_requires_original_secondary_effect_reference(tmp_path):
    d, b, p = fixture(tmp_path, zero=False)
    d['nodes'].append({'name': 'OtherBone'})
    d['skins'][0]['joints'].append(3)
    p.update(mode='rigid', owner_joint=1)
    with pytest.raises(ValueError, match='secondary effects'):
        split_corrective_partition(d, b, p)


def multi_owner_fixture(tmp_path):
    d, b, p = fixture(tmp_path, zero=False)
    pr = d['meshes'][0]['primitives'][0]
    def append(values, original):
        spec = copy.deepcopy(d['accessors'][original]); values = np.ascontiguousarray(values)
        b.extend(b'\0' * (-len(b) % 4)); offset = len(b); b.extend(values.tobytes())
        d['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': values.nbytes})
        spec.update(bufferView=len(d['bufferViews'])-1, count=len(values)); spec.pop('byteOffset', None)
        d['accessors'].append(spec); return len(d['accessors'])-1
    for name, ai in list(pr['attributes'].items()):
        values = raw_array(d, b, ai); extra = values[3:].copy()
        if name == 'POSITION': extra[:, 0] += 4
        pr['attributes'][name] = append(np.concatenate([values, extra]), ai)
    ai = pr['targets'][0]['POSITION']; values = raw_array(d,b,ai)
    pr['targets'][0]['POSITION'] = append(np.concatenate([values, values[3:]]), ai)
    pr['indices'] = append(np.arange(9, dtype='<u2').reshape(-1,1), pr['indices'])
    d['nodes'].append({'name': 'OtherBone'}); d['skins'][0]['joints'].append(3)
    p.update(vertex_ids=list(range(3,9)), mode='rigid', owner_joints=[0,0,0,1,1,1])
    p['reference_skin'] = {'layout':'godot-four-influences-u16-v1', 'bind_names':['Root','OtherBone'],
        'skin_hex':np.tile([0,0,0,0,65535,0,0,0],(6,1)).astype('<u2').tobytes().hex()}
    return d,b,p


def test_multiple_complete_rigid_islands_share_one_surface_and_reference(tmp_path):
    d,b,p = multi_owner_fixture(tmp_path)
    new,blob,report = split_corrective_partition(d,b,p)
    assert len(new['meshes']) == 2
    free = new['meshes'][1]['primitives'][0]
    np.testing.assert_array_equal(raw_array(new,blob,free['attributes']['JOINTS_0'])[:,0],p['owner_joints'])
    np.testing.assert_array_equal(raw_array(new,blob,free['attributes']['WEIGHTS_0']),np.tile([1,0,0,0],(6,1)))
    assert new['meshes'][1]['extras']['rabbitlands_surface_partition_v1']['reference_skin'] == p['reference_skin']
    assert report['owner_joints'] == p['owner_joints'] and report['owner_joint'] is None
    assert new['skins'] == d['skins']


@pytest.mark.parametrize('damage',['length','range','float','ambiguous','triangle','coincident','reference'])
def test_multi_owner_partitions_fail_closed(tmp_path,damage):
    d,b,p = multi_owner_fixture(tmp_path)
    if damage == 'length': p['owner_joints'].pop()
    if damage == 'range': p['owner_joints'][-1] = 2
    if damage == 'float': p['owner_joints'][0] = 0.0
    if damage == 'ambiguous': p['owner_joint'] = 0
    if damage == 'triangle': p['owner_joints'][0] = 1
    if damage == 'reference': p.pop('reference_skin')
    if damage == 'coincident':
        pr = d['meshes'][0]['primitives'][0]; ai = pr['attributes']['POSITION']; spec = d['accessors'][ai]
        positions = np.ndarray((9,3),'<f4',b,offset=d['bufferViews'][spec['bufferView']]['byteOffset'])
        positions[6] = positions[3]
    with pytest.raises(ValueError): split_corrective_partition(d,b,p)


@pytest.mark.parametrize('multi', [False, True])
def test_rigid_owner_cannot_wrap_in_retained_eight_bit_storage(tmp_path, multi):
    d,b,p = multi_owner_fixture(tmp_path)
    for i in range(255): d['nodes'].append({'name': 'Extra'+str(i)})
    d['skins'][0]['joints'] = list(range(257))
    if multi: p['owner_joints'] = [256]*6
    else:
        p.pop('owner_joints'); p['owner_joint'] = 256
    with pytest.raises(ValueError, match='joint storage'):
        split_corrective_partition(d,b,p)


def default_bake_fixture(tmp_path):
    from video_motion.packing import append_array
    d,b,p = fixture(tmp_path, zero=True)
    pr = d['meshes'][0]['primitives'][0]
    values = np.zeros((6,3),dtype='<f4'); values[3:,0] = 1e-19
    pr['targets'][0]['NORMAL'] = append_array(d,b,values,'VEC3')
    d['meshes'][0]['weights'] = [1.0]
    p.update(mode='rigid',owner_joint=0,bake_selected_defaults=True)
    return d,b,p


def test_explicit_default_bake_keeps_positions_and_bakes_only_tiny_directions(tmp_path):
    d,b,p = default_bake_fixture(tmp_path)
    new,blob,report = split_corrective_partition(d,b,p)
    before=d['meshes'][0]['primitives'][0];after=new['meshes'][1]['primitives'][0]
    assert raw_array(new,blob,after['attributes']['POSITION']).tobytes() == raw_array(d,b,before['attributes']['POSITION'])[3:].tobytes()
    normals=raw_array(new,blob,after['attributes']['NORMAL'])
    np.testing.assert_array_equal(normals[:,0],np.full(3,np.float32(1e-19)))
    np.testing.assert_array_equal(normals[:,2],np.ones(3))
    assert new['meshes'][0]['weights'] == [1.0]
    assert report['selected_default_bake'][1]['retained_bits_identical'] is True


@pytest.mark.parametrize('damage',['not_explicit','position','direction','preserved_skin','non_bool'])
def test_default_bake_cannot_silently_rebase_geometry_or_large_directions(tmp_path,damage):
    from video_motion.packing import append_array
    d,b,p = default_bake_fixture(tmp_path);pr=d['meshes'][0]['primitives'][0]
    if damage=='not_explicit':p.pop('bake_selected_defaults')
    if damage=='preserved_skin':p['mode']='preserve_skin'
    if damage=='non_bool':p['bake_selected_defaults']=1
    if damage in ('position','direction'):
        field='POSITION' if damage=='position' else 'NORMAL'
        values=np.zeros((6,3),dtype='<f4');values[3:,0]=.001
        pr['targets'][0][field]=append_array(d,b,values,'VEC3')
    with pytest.raises(ValueError):split_corrective_partition(d,b,p)
