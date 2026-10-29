"""Restore a shortened fixed-bake clip with an exact held existing TRS value.

No new channel, bone, default or motion is invented. A LINEAR/STEP node TRS
sampler receives one terminal timestamp and an exact copy of its last value.
Shared samplers are cloned for the selected channel. All previous key bits,
binary storage, static fields, clip metadata and other channels are retained.
This certifies a duration-only edit, not fidelity of the preceding offline bake.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from video_motion.asset import read_glb, write_glb, digest
from video_motion.creature_storage import _array, _append, _check_extensions


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _clock(d, blob, sampler):
    spec = d['accessors'][sampler['input']]
    require(spec['componentType'] == 5126 and spec['type'] == 'SCALAR' and not spec.get('normalized'),
            'Animation clocks must be unnormalized float32 scalars')
    times = _array(d, blob, sampler['input'])
    require(len(times) and np.isfinite(times).all() and times[0, 0] >= 0
            and np.all(np.diff(times.ravel()) > 0), 'Invalid/non-strict animation clock')
    return times


def _durations(d, blob):
    _check_extensions(d)
    names, ends = [], {}
    for animation in d.get('animations', []):
        name = animation.get('name')
        require(isinstance(name, str) and name and name not in names, 'Unique named clips required')
        names.append(name)
        require(animation.get('channels'), 'Cannot infer duration from an unbound clip')
        for sampler in animation['samplers']:
            require(sampler.get('interpolation', 'LINEAR') in ('LINEAR', 'STEP'),
                    'Cubic/unknown interpolation is unsupported')
        used = {channel['sampler'] for channel in animation['channels']}
        require(all(isinstance(i, int) and 0 <= i < len(animation['samplers']) for i in used), 'Invalid sampler index')
        ends[name] = max(float(_clock(d, blob, animation['samplers'][i])[-1, 0]) for i in used)
    require(names, 'No clips')
    return names, ends


def _select(d, blob, animation):
    for path in ('translation', 'scale', 'rotation'):
        for ci, channel in enumerate(animation['channels']):
            target = channel.get('target', {})
            if target.get('path') != path:
                continue
            node = target.get('node')
            if not isinstance(node, int) or not 0 <= node < len(d['nodes']) or 'matrix' in d['nodes'][node]:
                continue
            sampler = animation['samplers'][channel['sampler']]
            times = _clock(d, blob, sampler)
            spec = d['accessors'][sampler['output']]
            require(spec['componentType'] == 5126 and spec['type'] == ('VEC4' if path == 'rotation' else 'VEC3')
                    and not spec.get('normalized'), 'TRS output must be unnormalized float32 vectors')
            values = _array(d, blob, sampler['output'])
            require(len(values) == len(times) and np.isfinite(values).all(), 'Invalid TRS output values')
            return ci, times, values
    raise ValueError('Shortened clip has no existing eligible LINEAR/STEP node TRS sampler; pure-morph anchors are unsupported')


def _verify(original, old_blob, candidate, new_blob, changes, reference_ends):
    """Independent append/prefix and restricted-JSON certificate."""
    require(new_blob[:len(old_blob)] == old_blob, 'Original embedded binary prefix changed')
    require(candidate['accessors'][:len(original['accessors'])] == original['accessors'], 'Existing accessor metadata changed')
    require(candidate['bufferViews'][:len(original['bufferViews'])] == original['bufferViews'], 'Existing buffer view metadata changed')
    require(len(candidate['accessors']) == len(original['accessors']) + 2 * len(changes)
            and len(candidate['bufferViews']) == len(original['bufferViews']) + 2 * len(changes),
            'Unexpected appended storage')
    static = {key: value for key, value in original.items() if key not in ('buffers', 'accessors', 'bufferViews', 'animations')}
    require(static == {key: value for key, value in candidate.items() if key not in ('buffers', 'accessors', 'bufferViews', 'animations')},
            'Static document fields changed')
    require(len(original['buffers']) == len(candidate['buffers']) == 1, 'Single buffer required')
    require({k: v for k, v in original['buffers'][0].items() if k != 'byteLength'}
            == {k: v for k, v in candidate['buffers'][0].items() if k != 'byteLength'}, 'Buffer metadata changed')
    by_animation = {r['animation_index']: r for r in changes}
    proofs = []
    for ai, (old, new) in enumerate(zip(original['animations'], candidate['animations'], strict=True)):
        if ai not in by_animation:
            require(old == new, 'An unrelated clip changed')
            continue
        change = by_animation[ai]
        ci, si = change['channel'], change['original_sampler']
        expected = copy.deepcopy(old)
        selected = copy.deepcopy(old['samplers'][si])
        current = new['samplers'][change['new_sampler']]
        selected['input'], selected['output'] = current['input'], current['output']
        if change['cloned_shared_sampler']:
            require(change['new_sampler'] == len(old['samplers']), 'Unexpected cloned sampler index')
            expected['samplers'].append(selected)
            expected['channels'][ci]['sampler'] = change['new_sampler']
        else:
            require(change['new_sampler'] == si, 'Unexpected selected sampler index')
            expected['samplers'][si] = selected
        require(expected == new, 'Clip/channel/sampler metadata changed beyond the selected clock')
        old_times = _array(original, old_blob, old['samplers'][si]['input'])
        old_values = _array(original, old_blob, old['samplers'][si]['output'])
        times = _array(candidate, new_blob, current['input'])
        values = _array(candidate, new_blob, current['output'])
        require(len(times) == len(old_times) + 1 and len(values) == len(old_values) + 1, 'Not one appended key')
        require(times[:-1].tobytes() == old_times.tobytes() and values[:-1].tobytes() == old_values.tobytes(),
                'Existing selected key prefix changed')
        require(values[-1].tobytes() == old_values[-1].tobytes(), 'Terminal value is not an exact duplicate')
        require(float(times[-1, 0]) == reference_ends[old['name']] and times[-1, 0] > old_times[-1, 0],
                'Invalid appended terminal timestamp')
        for field in ('input', 'output'):
            spec = original['accessors'][old['samplers'][si][field]]
            new_spec = candidate['accessors'][current[field]]
            expected_spec = copy.deepcopy(spec)
            expected_spec.pop('byteOffset', None)
            expected_spec.pop('sparse', None)
            expected_spec['bufferView'] = new_spec.get('bufferView')
            field_values = times if field == 'input' else values
            expected_spec['count'] = len(field_values)
            for key, operation in [('min', np.min), ('max', np.max)]:
                if key in expected_spec:
                    expected_spec[key] = operation(field_values, axis=0).tolist()
            require(expected_spec == new_spec, 'New accessor interpretation/bounds changed')
        proofs.append({**change, 'existing_keys': len(old_times), 'new_keys': len(times),
                       'existing_clock_bits_sha256': hashlib.sha256(old_times.tobytes()).hexdigest(),
                       'existing_output_bits_sha256': hashlib.sha256(old_values.tobytes()).hexdigest(),
                       'terminal_value_bits_hex': old_values[-1].tobytes().hex(),
                       'terminal_clock_bits_hex': times[-1].tobytes().hex(),
                       'existing_prefix_bit_identical': True, 'terminal_value_bit_identical': True})
    require(_durations(candidate, new_blob)[1] == reference_ends, 'Active clip end times do not match reference')
    return proofs


def preserve(reference: Path, source: Path, output: Path, *, report: Path,
             expected_reference_sha256=None, expected_source_sha256=None) -> dict:
    reference, source, output, report = map(lambda p: Path(p).resolve(), (reference, source, output, report))
    require(reference != source and not reference.samefile(source), 'Reference and existing bake must differ')
    require(output not in (reference, source) and report not in (reference, source, output), 'Input/output/report aliases are forbidden')
    require(not output.exists() and not report.exists(), 'Versioned output/report must not already exist')
    source_sha, reference_sha = digest(source), digest(reference)
    require(expected_source_sha256 is None or expected_source_sha256 == source_sha, 'Existing bake SHA-256 mismatch')
    require(expected_reference_sha256 is None or expected_reference_sha256 == reference_sha, 'Reference SHA-256 mismatch')
    rd, rb = read_glb(reference)
    original, old_blob = read_glb(source)
    names, ends = _durations(original, old_blob)
    reference_names, reference_ends = _durations(rd, rb)
    require(names == reference_names, 'Changed clip inventory/order')
    require(all(reference_ends[name] >= ends[name] for name in names), 'Reference ends before the existing candidate; shortening is forbidden')
    candidate, blob = copy.deepcopy(original), bytearray(old_blob)
    changes = []
    for ai, animation in enumerate(original['animations']):
        end = reference_ends[animation['name']]
        if end == ends[animation['name']]:
            continue
        require(float(np.float32(end)) == end, 'Reference terminal time is not exactly representable as float32')
        ci, times, values = _select(original, old_blob, animation)
        si = animation['channels'][ci]['sampler']
        sampler = copy.deepcopy(animation['samplers'][si])
        sampler['input'] = _append(candidate, blob, np.concatenate([times, np.array([[end]], dtype=times.dtype)]),
                                   original['accessors'][animation['samplers'][si]['input']])
        sampler['output'] = _append(candidate, blob, np.concatenate([values, values[-1:]], axis=0),
                                    original['accessors'][animation['samplers'][si]['output']])
        cloned = sum(c['sampler'] == si for c in animation['channels']) > 1
        current = candidate['animations'][ai]
        if cloned:
            new_si = len(current['samplers'])
            current['samplers'].append(sampler)
            current['channels'][ci]['sampler'] = new_si
        else:
            new_si = si
            current['samplers'][si] = sampler
        changes.append({'animation_index': ai, 'clip': animation['name'], 'channel': ci,
                        'target': animation['channels'][ci]['target'], 'original_sampler': si, 'new_sampler': new_si,
                        'interpolation': sampler.get('interpolation', 'LINEAR'), 'cloned_shared_sampler': cloned,
                        'previous_active_end': ends[animation['name']], 'restored_active_end': end})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.stem + '-', suffix='.glb', dir=output.parent, delete=False) as f:
        temporary = Path(f.name)
    try:
        write_glb(temporary, candidate, blob)
        actual, actual_blob = read_glb(temporary)
        proofs = _verify(original, old_blob, actual, actual_blob, changes, reference_ends)
        require(digest(source) == source_sha and digest(reference) == reference_sha, 'An input changed during repair')
        with output.open('xb') as f:
            f.write(temporary.read_bytes())
        require(digest(output) == digest(temporary), 'Output copy did not match the certificate')
        result = {'schema': 1, 'status': 'held_terminal_duration_repair_not_approved',
                  'reference': str(reference), 'reference_sha256': reference_sha,
                  'source': str(source), 'source_sha256': source_sha, 'output': str(output), 'sha256': digest(output),
                  'implementation_sha256': digest(Path(__file__)), 'source_bytes': source.stat().st_size,
                  'output_bytes': output.stat().st_size, 'reference_active_ends': reference_ends,
                  'source_active_ends': ends, 'repairs': proofs,
                  'original_binary_prefix_bytes': len(old_blob),
                  'original_binary_prefix_sha256': hashlib.sha256(old_blob).hexdigest(),
                  'static_fields_and_existing_key_bits_preserved': True,
                  'scope': 'Append one exact held value on an existing node TRS channel to restore active clip duration. No new default, rig, geometry, material, motion or fidelity approval.'}
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open('x', encoding='utf-8', newline='\n') as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write('\n')
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'source', 'output', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-reference-sha256')
    parser.add_argument('--expected-source-sha256')
    args = parser.parse_args()
    result = preserve(args.reference, args.source, args.output, report=args.report,
                      expected_reference_sha256=args.expected_reference_sha256,
                      expected_source_sha256=args.expected_source_sha256)
    print(json.dumps({key: result[key] for key in ('status', 'source_sha256', 'sha256', 'source_bytes', 'output_bytes')}))


if __name__ == '__main__':
    main()
