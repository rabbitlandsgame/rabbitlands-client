"""Discard unreferenced hair authoring payloads without changing live bytes.

This deliberately supports the generated RL hair graph only. It is not a
general glTF optimiser: unsupported extensions, animations and external buffers
fail before output. Keep the unmodified authoring source in private storage.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import glbwriter
import rlglb


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _without_extensions(value):
    if isinstance(value, dict):
        assert 'extensions' not in value, 'Extensions need an explicit reference policy'
        for key, child in value.items():
            if key != 'extras':
                _without_extensions(child)
    elif isinstance(value, list):
        for child in value:
            _without_extensions(child)


def compact_document(document, blob):
    """Return a new known hair graph, binary and exact old-to-new reference maps."""
    allowed = {'asset', 'scene', 'scenes', 'nodes', 'meshes', 'skins', 'materials',
               'textures', 'samplers', 'images', 'accessors', 'bufferViews', 'buffers',
               'animations', 'extensionsUsed', 'extensionsRequired'}
    assert set(document) <= allowed, 'Unknown top-level reference graph'
    assert document.get('asset', {}).get('extras', {}).get('rlHair'), 'Expected an RL hair asset'
    assert not document.get('animations'), 'Animation accessors need an explicit policy'
    assert not document.get('extensionsUsed') and not document.get('extensionsRequired')
    _without_extensions(document)
    assert len(document['buffers']) == 1 and 'uri' not in document['buffers'][0]
    result = copy.deepcopy(document)
    accessors = set()
    for mesh in result['meshes']:
        for primitive in mesh['primitives']:
            accessors.update(primitive['attributes'].values())
            if 'indices' in primitive:
                accessors.add(primitive['indices'])
            for target in primitive.get('targets', []):
                accessors.update(target.values())
    for skin in result.get('skins', []):
        if 'inverseBindMatrices' in skin:
            accessors.add(skin['inverseBindMatrices'])
    assert accessors and all(isinstance(a, int) and 0 <= a < len(result['accessors']) for a in accessors)
    accessor_map = {old: new for new, old in enumerate(sorted(accessors))}
    live_accessors = [copy.deepcopy(result['accessors'][a]) for a in sorted(accessors)]
    views = set()
    for accessor in live_accessors:
        if 'bufferView' in accessor:
            views.add(accessor['bufferView'])
        if 'sparse' in accessor:
            views.add(accessor['sparse']['indices']['bufferView'])
            views.add(accessor['sparse']['values']['bufferView'])
    for image in result.get('images', []):
        assert 'bufferView' in image and 'uri' not in image, 'Expected embedded hair images'
        views.add(image['bufferView'])
    assert all(isinstance(v, int) and 0 <= v < len(result['bufferViews']) for v in views)
    view_map = {old: new for new, old in enumerate(sorted(views))}
    packed = bytearray()
    live_views = []
    for index in sorted(views):
        view = copy.deepcopy(result['bufferViews'][index])
        assert view.get('buffer', 0) == 0
        start = view.get('byteOffset', 0)
        length = view['byteLength']
        assert start >= 0 and length >= 0 and start + length <= len(blob)
        while len(packed) % 4:
            packed.append(0)
        view['buffer'] = 0
        view['byteOffset'] = len(packed)
        packed.extend(blob[start:start + length])
        live_views.append(view)
    while len(packed) % 4:
        packed.append(0)
    for accessor in live_accessors:
        if 'bufferView' in accessor:
            accessor['bufferView'] = view_map[accessor['bufferView']]
        if 'sparse' in accessor:
            for field in ['indices', 'values']:
                sparse = accessor['sparse'][field]
                sparse['bufferView'] = view_map[sparse['bufferView']]
    for mesh in result['meshes']:
        for primitive in mesh['primitives']:
            primitive['attributes'] = {name: accessor_map[a] for name, a in primitive['attributes'].items()}
            if 'indices' in primitive:
                primitive['indices'] = accessor_map[primitive['indices']]
            primitive['targets'] = [{name: accessor_map[a] for name, a in target.items()}
                                    for target in primitive.get('targets', [])]
    for skin in result.get('skins', []):
        if 'inverseBindMatrices' in skin:
            skin['inverseBindMatrices'] = accessor_map[skin['inverseBindMatrices']]
    for image in result.get('images', []):
        image['bufferView'] = view_map[image['bufferView']]
    result['accessors'] = live_accessors
    result['bufferViews'] = live_views
    result['buffers'][0]['byteLength'] = len(packed)
    # This includes sparse/normalised integer data, with no float re-encoding.
    for old, new in accessor_map.items():
        before = rlglb.accessor(document, blob, old, normalize=False)
        after = rlglb.accessor(result, packed, new, normalize=False)
        np.testing.assert_array_equal(before, after)
    for old, new in view_map.items():
        a, b = document['bufferViews'][old], result['bufferViews'][new]
        assert blob[a.get('byteOffset', 0):a.get('byteOffset', 0) + a['byteLength']] == packed[b['byteOffset']:b['byteOffset'] + b['byteLength']]
    return result, bytes(packed), {'accessors': accessor_map, 'bufferViews': view_map}


def compact_detail_vertices(document, blob):
    """Remove only unindexed rows in explicitly identified hair-card streams.

    The returned per-stream map permits private root-binding records to follow
    the vertex renumbering. No indexed attribute or shape value is altered.
    """
    # Validate the known reference graph before appending selected accessors.
    compact_document(document, blob)
    writer = glbwriter.GLB()
    writer.g, writer.blob = copy.deepcopy(document), bytearray(blob)
    reports = []
    for mi, mesh in enumerate(document['meshes']):
        for pi, primitive in enumerate(mesh['primitives']):
            material = document.get('materials', [])[primitive['material']] if 'material' in primitive else {}
            if material.get('name') != 'rl_hair_card':
                continue
            ranges = primitive.get('extras', {}).get('partVertexRanges', {})
            count = document['accessors'][primitive['attributes']['POSITION']]['count']
            assert ranges == {'detail': [0, count]}, 'Expected a separate, full detail stream'
            assert primitive.get('mode', 4) == 4 and 'indices' in primitive
            old_indices = rlglb.accessor(document, blob, primitive['indices'], normalize=False).astype(np.int64)
            assert old_indices.size and old_indices.size % 3 == 0
            assert old_indices.min() >= 0 and old_indices.max() < count
            used = np.unique(old_indices)
            remap = np.full(count, -1, dtype=np.int64)
            remap[used] = np.arange(len(used))
            report = {'mesh': mesh['name'], 'primitive': pi, 'old_count': count,
                      'new_count': len(used), 'old_to_new': remap.tolist()}
            reports.append(report)
            if len(used) == count:
                continue
            destination = writer.g['meshes'][mi]['primitives'][pi]

            def select(index, target=False):
                accessor = document['accessors'][index]
                assert accessor['count'] == count
                assert set(accessor) <= {'bufferView', 'byteOffset', 'componentType', 'count', 'type',
                                         'normalized', 'min', 'max', 'sparse'}, 'Unknown vertex accessor metadata'
                data = rlglb.accessor(document, blob, index, normalize=False)
                values = data[used]
                if target:
                    assert accessor['componentType'] == 5126 and accessor['type'] == 'VEC3'
                    assert not accessor.get('normalized')
                    if ((values == 0) & np.signbit(values)).any():
                        out = writer.accessor(values, 'VEC3', minmax='min' in accessor)
                    else:
                        out = writer.sparse_vec3(values, eps=0, minmax='min' in accessor)
                else:
                    assert accessor['componentType'] in {5121, 5123, 5125, 5126}
                    out = writer.accessor(values, accessor['type'], accessor['componentType'],
                                          target=34962, minmax='min' in accessor,
                                          normalized=accessor.get('normalized', False))
                actual = rlglb.accessor(writer.g, writer.blob, out, normalize=False)
                dtype = rlglb.COMPONENT[accessor['componentType']]
                assert np.asarray(actual, dtype=dtype).tobytes() == np.asarray(values, dtype=dtype).tobytes()
                return out

            destination['attributes'] = {name: select(index) for name, index in primitive['attributes'].items()}
            destination['targets'] = [{name: select(index, True) for name, index in shape.items()}
                                      for shape in primitive.get('targets', [])]
            index_type = document['accessors'][primitive['indices']]['componentType']
            assert index_type in {5121, 5123, 5125}
            destination['indices'] = writer.accessor(remap[old_indices].reshape(-1), 'SCALAR', index_type, target=34963)
            destination['extras']['partVertexRanges'] = {'detail': [0, len(used)]}
            # An indexed corner retains every exact source field, including skin
            # integers, sparse targets and normalised colour/weight payloads.
            for old_group, new_group in [(primitive['attributes'], destination['attributes'])] + list(zip(primitive.get('targets', []), destination.get('targets', []))):
                for name, index in old_group.items():
                    before = rlglb.accessor(document, blob, index, normalize=False)[old_indices.reshape(-1)]
                    after = rlglb.accessor(writer.g, writer.blob, new_group[name], normalize=False)[remap[old_indices].reshape(-1)]
                    dtype = rlglb.COMPONENT[document['accessors'][index]['componentType']]
                    assert np.asarray(before, dtype=dtype).tobytes() == np.asarray(after, dtype=dtype).tobytes()
    if any(r['old_count'] != r['new_count'] for r in reports):
        native_meshes = [mesh for mesh in writer.g['meshes']
                         if 'hl_native_fit' in mesh.get('extras', {}).get('targetNames', [])]
        if native_meshes:
            assert len(native_meshes) == len(writer.g['meshes']), 'Inconsistent Native corrective layout'
            metadata = writer.g['asset']['extras']['rlHair'].get('nativeFit', {})
            assert metadata.get('shape') == 'hl_native_fit' and 'deltaSHA256' in metadata
            digest = hashlib.sha256()
            for mesh in writer.g['meshes']:
                names = mesh['extras']['targetNames']
                assert names.count('hl_native_fit') == 1
                target_index = names.index('hl_native_fit')
                for pi, primitive in enumerate(mesh['primitives']):
                    target = primitive['targets'][target_index]
                    count = writer.g['accessors'][primitive['attributes']['POSITION']]['count']
                    digest.update(json.dumps([mesh['name'], pi], separators=(',', ':')).encode())
                    for name in ['POSITION', 'NORMAL']:
                        data = rlglb.accessor(writer.g, writer.blob, target[name], normalize=False) if name in target else np.zeros((count, 3))
                        assert data.shape == (count, 3) and np.isfinite(data).all()
                        digest.update(name.encode())
                        digest.update(np.asarray(data.shape, dtype='<i8').tobytes())
                        digest.update(np.ascontiguousarray(data, dtype='<f4').tobytes())
            metadata['layoutSourceDeltaSHA256'] = metadata['deltaSHA256']
            metadata['deltaSHA256'] = digest.hexdigest()
            metadata['layoutToolSHA256'] = sha(__file__)
    writer.g['buffers'][0]['byteLength'] = len(writer.blob)
    return writer.g, bytes(writer.blob), reports


def compact(source, output, prune_detail_vertices=False):
    source, output = Path(source), Path(output)
    assert source.resolve() != output.resolve() and not output.exists()
    assert source.name == output.name, 'Preserve the runtime asset and relative atlas names'
    document, blob = rlglb.read(str(source))
    working, working_blob = document, blob
    detail_report = []
    if prune_detail_vertices:
        working, working_blob, detail_report = compact_detail_vertices(document, blob)
    result, packed, maps = compact_document(working, working_blob)
    atlas = source.with_suffix('.png')
    if atlas.exists():
        assert not output.with_suffix('.png').exists()
    result['asset']['extras']['rlHair']['compaction'] = {
        'sourceSHA256': sha(source), 'toolSHA256': sha(__file__),
        'method': 'Remove unreferenced authoring payloads; every live buffer-view byte retained'}
    if prune_detail_vertices:
        result['asset']['extras']['rlHair']['compaction']['unusedDetailRowsRemoved'] = sum(r['old_count'] - r['new_count'] for r in detail_report)
        result['asset']['extras']['rlHair']['compaction']['indexedValuesExact'] = True
    writer = glbwriter.GLB()
    writer.g, writer.blob = result, bytearray(packed)
    # The vendored writer removes empty optional arrays when saving.
    writer.g.setdefault('skins', [])
    writer.g.setdefault('materials', [])
    output.parent.mkdir(parents=True, exist_ok=True)
    writer.save(str(output))
    if atlas.exists():
        shutil.copy2(atlas, output.with_suffix('.png'))
    report = {'source_sha256': sha(source), 'output_sha256': sha(output),
              'source_bytes': source.stat().st_size, 'output_bytes': output.stat().st_size,
              'live_accessors': len(maps['accessors']), 'live_buffer_views': len(maps['bufferViews']),
              'removed_accessors': len(document['accessors']) - len(maps['accessors']),
              'removed_buffer_views': len(document['bufferViews']) - len(maps['bufferViews']),
              'live_payload_bytes_exact': True, 'authoring_source_preserved': True}
    if prune_detail_vertices:
        report['detail_vertex_streams'] = detail_report
        report['indexed_values_exact'] = True
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True, help='Ignored/private preservation receipt')
    parser.add_argument('--prune-unused-detail-vertices', action='store_true',
                        help='Explicitly compact unindexed rows in separate rl_hair_card streams')
    args = parser.parse_args()
    receipt = compact(args.source, args.out, prune_detail_vertices=args.prune_unused_detail_vertices)
    Path(args.report).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
