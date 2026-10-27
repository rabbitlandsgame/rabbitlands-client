"""Remove only bit-identical interior keys inside flat animation runs.

This preserves every run boundary, all clip endpoints, and the original float32
bits, including signed zero. It does not approximate curves or resample joints.
Call packing.compact afterward to discard the now-unreachable old arrays.
"""
import copy

import numpy as np

WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def _float_bits(document, binary, index):
    spec = document['accessors'][index]
    if spec['componentType'] != 5126 or spec.get('normalized') or spec.get('sparse'):
        return None
    width = WIDTHS.get(spec['type'])
    if width is None:
        return None
    count = int(spec['count'])
    if 'bufferView' not in spec:
        return np.zeros((count, width), dtype='<u4')
    view = document['bufferViews'][spec['bufferView']]
    if view.get('buffer', 0) != 0 or view.get('extensions'):
        raise ValueError('Animation packing requires an ordinary embedded buffer view')
    start = int(spec.get('byteOffset', 0))
    stride = int(view.get('byteStride', width * 4))
    end = start + (count - 1) * stride + width * 4 if count else start
    if start < 0 or stride < width * 4 or stride % 4 or end > view['byteLength']:
        raise ValueError('Animation accessor exceeds its buffer view')
    absolute = int(view.get('byteOffset', 0)) + start
    if absolute < 0 or absolute + max(0, end - start) > len(binary):
        raise ValueError('Animation accessor exceeds the embedded buffer')
    return np.ndarray((count, width), dtype='<u4', buffer=binary,
                      offset=absolute, strides=(stride, 4)).copy()


def reduce_constant_runs(document, binary):
    """Return a copy with redundant LINEAR/STEP flat-run interiors removed.

    Morph samplers use a SCALAR accessor flattened over all target weights;
    their complete per-frame vectors are compared together. CUBICSPLINE and
    unsupported encodings are kept unchanged, rather than guessing tangents.
    """
    if len(document.get('buffers', [])) != 1 or document['buffers'][0].get('uri'):
        raise ValueError('Animation packing requires one embedded buffer')
    result = copy.deepcopy(document)
    blob = bytearray(binary)
    changed = []
    skipped = 0

    def append(bits, old_index):
        spec = copy.deepcopy(document['accessors'][old_index])
        spec.pop('byteOffset', None)
        spec.pop('sparse', None)
        blob.extend(b'\0' * (-len(blob) % 4))
        result.setdefault('bufferViews', []).append(
            {'buffer': 0, 'byteOffset': len(blob), 'byteLength': bits.nbytes})
        blob.extend(np.ascontiguousarray(bits, dtype='<u4').tobytes())
        spec['bufferView'] = len(result['bufferViews']) - 1
        spec['count'] = len(bits)
        result['accessors'].append(spec)
        return len(result['accessors']) - 1

    for animation in result.get('animations', []):
        for index, sampler in enumerate(animation['samplers']):
            if sampler.get('interpolation', 'LINEAR') not in ('LINEAR', 'STEP'):
                skipped += 1
                continue
            clock = _float_bits(document, binary, sampler['input'])
            values = _float_bits(document, binary, sampler['output'])
            if clock is None or values is None or clock.shape[1] != 1 or len(clock) < 3:
                skipped += 1
                continue
            times = clock.view('<f4').ravel()
            if not np.all(np.isfinite(times)) or not np.all(np.diff(times) > 0):
                raise ValueError('Animation key times must be finite and strictly increasing')
            if not np.all(np.isfinite(values.view('<f4'))):
                raise ValueError('Animation values must be finite')
            paths = {channel['target']['path'] for channel in animation['channels']
                     if channel['sampler'] == index}
            if 'weights' in paths:
                if paths != {'weights'} or values.shape[1] != 1 or len(values) % len(clock):
                    raise ValueError('Incompatible flattened morph sampler')
                rows = values.reshape(len(clock), -1)
            else:
                if len(values) != len(clock):
                    skipped += 1
                    continue
                rows = values
            equal = np.all(rows[1:] == rows[:-1], axis=1)
            keep = np.ones(len(clock), dtype=bool)
            keep[1:-1] = ~(equal[:-1] & equal[1:])
            if keep.all():
                continue
            old_keys = len(clock)
            sampler['input'] = append(clock[keep], sampler['input'])
            selected = rows[keep].reshape(-1, values.shape[1])
            sampler['output'] = append(selected, sampler['output'])
            changed.append({'clip': animation.get('name', ''), 'sampler': index,
                            'paths': sorted(paths), 'source_keys': old_keys,
                            'packed_keys': int(keep.sum())})
    result['buffers'][0]['byteLength'] = len(blob)
    return result, blob, {'changed_samplers': changed,
                          'removed_keys': sum(x['source_keys'] - x['packed_keys'] for x in changed),
                          'skipped_samplers': skipped,
                          'appended_bytes_before_compaction': len(blob) - len(binary)}
