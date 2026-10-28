"""Held terminal edits preserve all existing bits and fail closed on ambiguity."""
import copy
import json

import numpy as np
import pytest

from preserve_creature_bake_duration import preserve, _verify
from video_motion.asset import read_glb, write_glb, digest
from video_motion.creature_storage import _array
from video_motion.packing import append_array


def fixture(tmp_path, *, shared=False, mode='LINEAR'):
    d = {'asset': {'version': '2.0', 'extras': {'review': 'unapproved'}},
         'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': [],
         'scene': 0, 'scenes': [{'nodes': [0, 1, 2]}],
         'nodes': [{'name': 'Root'}, {'name': 'Mesh', 'mesh': 0}, {'name': 'Other'}],
         'materials': [{'name': 'Original', 'doubleSided': True}], 'animations': []}
    b = bytearray()
    pos = append_array(d, b, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 'VEC3')
    uv = append_array(d, b, [[0, 0], [1, 0], [0, 1]], 'VEC2')
    d['meshes'] = [{'name': 'Frozen', 'extras': {'preserve': True}, 'primitives': [
        {'attributes': {'POSITION': pos, 'TEXCOORD_0': uv}, 'material': 0}]}]
    clock = append_array(d, b, [[0], [.25], [.5]], 'SCALAR')
    value = append_array(d, b, [[0., -0., 0.], [.1, 0., 0.], [.1, 0., 0.]], 'VEC3')
    other_clock = append_array(d, b, [[0], [1]], 'SCALAR')
    rotation = append_array(d, b, [[0, 0, 0, 1]] * 2, 'VEC4')
    channels = [{'sampler': 0, 'target': {'node': 0, 'path': 'translation'}},
                {'sampler': 1, 'target': {'node': 0, 'path': 'rotation'}}]
    if shared:
        channels.append({'sampler': 0, 'target': {'node': 2, 'path': 'translation'}})
    animation = {'name': 'Death_A', 'extras': {'event': .317}, 'channels': channels,
                 'samplers': [{'input': clock, 'output': value, 'interpolation': mode, 'extras': {'tag': 'keep'}},
                              {'input': other_clock, 'output': rotation}]}
    d['animations'] = [animation]
    source = tmp_path/'baked.glb'
    write_glb(source, d, b)
    rd, rb = copy.deepcopy(d), bytearray(b)
    end = append_array(rd, rb, [[0], [2]], 'SCALAR')
    weights = append_array(rd, rb, [[0], [1]], 'SCALAR')
    morph = append_array(rd, rb, [[0, 0, .01]] * 3, 'VEC3')
    rd['meshes'][0]['primitives'][0]['targets'] = [{'POSITION': morph}]
    rd['animations'][0]['samplers'].append({'input': end, 'output': weights})
    rd['animations'][0]['channels'].append({'sampler': 2, 'target': {'node': 1, 'path': 'weights'}})
    reference = tmp_path/'sampled.glb'
    write_glb(reference, rd, rb)
    return reference, source


@pytest.mark.parametrize('mode', ['LINEAR', 'STEP'])
@pytest.mark.parametrize('shared', [False, True])
def test_existing_prefix_static_and_terminal_bits_preserved(tmp_path, mode, shared):
    reference, source = fixture(tmp_path, mode=mode, shared=shared)
    old_source, old_reference = source.read_bytes(), reference.read_bytes()
    output, report = tmp_path/'baked-duration-v2.glb', tmp_path/'repair.json'
    result = preserve(reference, source, output, report=report,
                      expected_reference_sha256=digest(reference), expected_source_sha256=digest(source))
    assert source.read_bytes() == old_source and reference.read_bytes() == old_reference
    a, ab = read_glb(source)
    c, cb = read_glb(output)
    assert cb[:len(ab)] == ab
    assert result['source_active_ends']['Death_A'] == 1 and result['reference_active_ends']['Death_A'] == 2
    repair = result['repairs'][0]
    assert repair['target']['path'] == 'translation' and repair['cloned_shared_sampler'] == shared
    selected = c['animations'][0]['samplers'][repair['new_sampler']]
    original = a['animations'][0]['samplers'][0]
    for key in ['input', 'output']:
        old, new = _array(a, ab, original[key]), _array(c, cb, selected[key])
        assert old.tobytes() == new[:-1].tobytes()
    assert _array(c, cb, selected['output'])[-1].tobytes() == _array(a, ab, original['output'])[-1].tobytes()
    if shared:
        assert c['animations'][0]['samplers'][:2] == a['animations'][0]['samplers']
        assert c['animations'][0]['channels'][2]['sampler'] == 0
    assert json.loads(report.read_text())['sha256'] == digest(output)


@pytest.mark.parametrize('fault', ['cubic', 'inventory', 'reference_shorter', 'no_trs'])
def test_unsupported_repairs_fail_without_output(tmp_path, fault):
    reference, source = fixture(tmp_path)
    rd, rb = read_glb(reference)
    d, b = read_glb(source)
    if fault == 'cubic':
        d['animations'][0]['samplers'][0]['interpolation'] = 'CUBICSPLINE'
    elif fault == 'inventory':
        rd['animations'][0]['name'] = 'Different'
    elif fault == 'reference_shorter':
        rb = bytearray(rb)
        for sampler in rd['animations'][0]['samplers']:
            ts = _array(rd, rb, sampler['input'])
            ts *= .1
            sampler['input'] = append_array(rd, rb, ts, 'SCALAR')
    else:
        d['animations'][0]['channels'] = [{'sampler': 0, 'target': {'node': 1, 'path': 'weights'}}]
    write_glb(source, d, b)
    write_glb(reference, rd, rb)
    output = tmp_path/'bad.glb'
    with pytest.raises(ValueError):
        preserve(reference, source, output, report=tmp_path/'bad.json')
    assert not output.exists()


def test_no_input_alias_overwrite_or_unbound_hash(tmp_path):
    reference, source = fixture(tmp_path)
    before = source.read_bytes()
    with pytest.raises(ValueError, match='aliases'):
        preserve(reference, source, source, report=tmp_path/'repair.json')
    with pytest.raises(ValueError, match='aliases'):
        preserve(reference, source, tmp_path/'new.glb', report=source)
    with pytest.raises(ValueError, match='mismatch'):
        preserve(reference, source, tmp_path/'new.glb', report=tmp_path/'repair.json', expected_source_sha256='0'*64)
    output = tmp_path/'exists.glb'
    output.write_bytes(b'keep')
    with pytest.raises(ValueError, match='already exist'):
        preserve(reference, source, output, report=tmp_path/'repair.json')
    assert output.read_bytes() == b'keep' and source.read_bytes() == before


@pytest.mark.parametrize('fault', ['static', 'old_binary', 'new_prefix', 'terminal', 'bounds'])
def test_independent_certificate_rejects_mutations(tmp_path, fault):
    reference, source = fixture(tmp_path)
    output = tmp_path/'repaired.glb'
    r = preserve(reference, source, output, report=tmp_path/'repair.json')
    a, ab = read_glb(source)
    c, cb = read_glb(output)
    cb = bytearray(cb)
    selected = c['animations'][0]['samplers'][r['repairs'][0]['new_sampler']]
    if fault == 'static':
        c['meshes'][0]['name'] = 'changed'
    elif fault == 'old_binary':
        cb[0] ^= 1
    elif fault == 'bounds':
        c['accessors'][selected['input']]['max'] = [999.]
    else:
        spec = c['accessors'][selected['output']]
        view = c['bufferViews'][spec['bufferView']]
        offset = view['byteOffset'] + (spec['count']-1)*12 if fault == 'terminal' else view['byteOffset']
        cb[offset] ^= 1
    with pytest.raises(ValueError):
        _verify(a, ab, c, cb, r['repairs'], r['reference_active_ends'])
