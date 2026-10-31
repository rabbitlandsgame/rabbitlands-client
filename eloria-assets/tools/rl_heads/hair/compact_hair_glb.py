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


def compact(source, output):
    source, output = Path(source), Path(output)
    assert source.resolve() != output.resolve() and not output.exists()
    assert source.name == output.name, 'Preserve the runtime asset and relative atlas names'
    document, blob = rlglb.read(str(source))
    result, packed, maps = compact_document(document, blob)
    atlas = source.with_suffix('.png')
    if atlas.exists():
        assert not output.with_suffix('.png').exists()
    result['asset']['extras']['rlHair']['compaction'] = {
        'sourceSHA256': sha(source), 'toolSHA256': sha(__file__),
        'method': 'Remove unreferenced authoring payloads; every live buffer-view byte retained'}
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
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True, help='Ignored/private preservation receipt')
    args = parser.parse_args()
    receipt = compact(args.source, args.out)
    Path(args.report).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
