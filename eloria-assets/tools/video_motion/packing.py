"""Lossless single-buffer GLB packing. No approximate animation reduction."""
import copy
import json
import numpy as np
from .asset import accessor


def append_array(document, blob, values, kind):
    values = np.ascontiguousarray(values, dtype='<f4')
    blob.extend(b'\0' * (-len(blob) % 4))
    document.setdefault('bufferViews', []).append({
        'buffer': 0, 'byteOffset': len(blob), 'byteLength': values.nbytes})
    blob.extend(values.tobytes())
    flat = values.reshape(len(values), -1)
    document.setdefault('accessors', []).append({
        'bufferView': len(document['bufferViews']) - 1,
        'componentType': 5126, 'count': len(values), 'type': kind,
        'min': flat.min(0).tolist(), 'max': flat.max(0).tolist()})
    return len(document['accessors']) - 1


def compact(document, binary):
    """Remove unreachable storage; collapse only exactly constant LINEAR/STEP tracks.

    Endpoint timestamps remain intact, including clips with only constant tracks.
    Unknown binary-bearing extensions fail closed rather than losing payload.
    """
    document = copy.deepcopy(document)
    if set(document.get('extensionsUsed', [])) - {'KHR_materials_unlit', 'KHR_materials_specular',
            'KHR_materials_ior', 'KHR_materials_transmission', 'KHR_materials_clearcoat',
            'KHR_texture_transform', 'KHR_materials_emissive_strength'}:
        raise ValueError('Review extension accessor/buffer references before packing')
    if len(document['buffers']) != 1 or document['buffers'][0].get('uri'):
        raise ValueError('Packing requires one embedded buffer')
    blob = bytearray(binary)
    collapsed = 0
    for animation in document.get('animations', []):
        for sampler in animation['samplers']:
            if sampler.get('interpolation', 'LINEAR') not in ('LINEAR', 'STEP'):
                continue
            values = accessor(document, blob, sampler['output'])
            times = accessor(document, blob, sampler['input'])
            bits = values.view(np.uint8).reshape(len(values), -1)
            if len(values) > 2 and len(values) == len(times) and np.all(bits == bits[0]):
                spec = document['accessors'][sampler['output']]
                # Preserve non-float/normalized attributes without conversion.
                if spec['componentType'] != 5126 or spec.get('normalized'):
                    continue
                sampler['input'] = append_array(document, blob, times[[0, -1]], 'SCALAR')
                sampler['output'] = append_array(document, blob, values[[0, -1]], spec['type'])
                collapsed += 1
    refs = []
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            refs.extend((primitive['attributes'], key) for key in primitive['attributes'])
            if 'indices' in primitive:
                refs.append((primitive, 'indices'))
            for target in primitive.get('targets', []):
                refs.extend((target, key) for key in target)
    for skin in document.get('skins', []):
        if 'inverseBindMatrices' in skin:
            refs.append((skin, 'inverseBindMatrices'))
    for animation in document.get('animations', []):
        for sampler in animation['samplers']:
            refs.extend([(sampler, 'input'), (sampler, 'output')])
    kept = sorted({container[key] for container, key in refs})
    remap = {old: new for new, old in enumerate(kept)}
    accessors = [document['accessors'][i] for i in kept]
    views = []
    for spec in accessors:
        if spec.get('sparse'):
            raise ValueError('Expand sparse accessors before packing')
        if 'bufferView' in spec:
            views.append((spec, 'bufferView'))
    for img in document.get('images', []):
        if 'uri' in img:
            raise ValueError('Embedded images are required')
        views.append((img, 'bufferView'))
    view_ids = sorted({container[key] for container, key in views})
    new_blob, new_views, view_map, dedup = bytearray(), [], {}, {}
    for old in view_ids:
        view = copy.deepcopy(document['bufferViews'][old])
        if view.get('buffer', 0) != 0 or view.get('extensions'):
            raise ValueError('Unsupported binary view')
        offset = view.get('byteOffset', 0)
        payload = bytes(blob[offset:offset + view['byteLength']])
        metadata = {k: v for k, v in view.items() if k not in ('byteOffset', 'buffer')}
        key = (json.dumps(metadata, sort_keys=True), payload)
        if key not in dedup:
            new_blob.extend(b'\0' * (-len(new_blob) % 4))
            view.update(buffer=0, byteOffset=len(new_blob))
            new_blob.extend(payload)
            dedup[key] = len(new_views)
            new_views.append(view)
        view_map[old] = dedup[key]
    for container, key in refs:
        container[key] = remap[container[key]]
    for container, key in views:
        container[key] = view_map[container[key]]
    document['accessors'], document['bufferViews'] = accessors, new_views
    document['buffers'][0]['byteLength'] = len(new_blob)
    return document, new_blob, {'constant_samplers_collapsed': collapsed,
        'original_buffer_bytes': len(binary), 'packed_buffer_bytes': len(new_blob)}
