"""Dress Ilka's shelf with existing imported magical display pieces.

Retain the potion shelf's wooden frame, excluding its disconnected bottle
components, and instance the existing crystal, orb and lens models on its
three boards. No vertices, textures or sculpted objects are generated. The
apothecary's original potion shelf is never modified.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
import consolidate_map_vertices as G

FOLDER = 'godot-client/assets/world/underground'
INPUTS = ('potion_shelf', 'crystal_cluster', 'crystal_ball_stand', 'lens_tripod')
SCRIPT = 'tools/prepare_magic_shelf.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def frame_faces(document, binary):
    """Select complete imported components; retain their original triangle data."""
    if len(document['meshes']) != 1 or len(document['meshes'][0]['primitives']) != 1:
        raise ValueError('Shelf mesh structure changed; review the component selection.')
    primitive = document['meshes'][0]['primitives'][0]
    vertices = G.accessor(document, binary, primitive['attributes']['POSITION'])
    faces = G.accessor(document, binary, primitive['indices']).reshape(-1, 3)
    if faces.max() > np.iinfo(np.uint16).max:
        raise ValueError('Shelf exceeds the reviewed 16-bit vertex range.')
    # Position seams must not split a bottle from its own cap. This temporary
    # index is used only for connectivity, never written into the model.
    unique, inverse = np.unique(np.round(vertices, 6), axis=0, return_inverse=True)
    joined = inverse[faces]
    edges = joined[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
                       shape=(len(unique), len(unique)))
    count, labels = connected_components(graph, directed=False)
    face_labels = labels[joined[:, 0]]
    assert np.all(labels[joined] == face_labels[:, None])
    keep = np.zeros(len(faces), dtype=bool)
    for component in range(count):
        selected = face_labels == component
        if not selected.any():
            continue
        points = vertices[faces[selected].ravel()]
        low, high = points.min(0), points.max(0)
        # Side posts and their carved trim; full-width boards/back; crest.
        wooden = (low[0] > .38 or high[0] < -.38
                  or high[0] - low[0] > .70 or low[1] > 1.305)
        if wooden:
            keep |= selected
    if not 500 < keep.sum() < len(faces) - 500:
        raise ValueError('Imported shelf topology changed; review the component selection.')
    return faces[keep], {'originalTriangles': len(faces), 'frameTriangles': int(keep.sum()),
                         'removedBottleTriangles': int((~keep).sum())}


def package_magic_shelf(output: Path, root: Path = ROOT):
    sources = {name: root / FOLDER / (name + '.glb') for name in INPUTS}
    raw = {name: path.read_bytes() for name, path in sources.items()}
    document, binary = G.decode(raw['potion_shelf'])
    document = copy.deepcopy(document)
    empty_policy = {'schema': 'rabbitlands-scenery-images-v1', 'mipPolicy': 'full',
                    'resources': {}, 'imagePolicies': {}}
    document.setdefault('extras', {}).setdefault('rabbitlands_scenery_images', copy.deepcopy(empty_policy))
    kept, proof = frame_faces(document, binary)
    blob = bytearray(binary)

    def append_indices(values):
        while len(blob) % 4:
            blob.append(0)
        values = np.asarray(values, dtype='<u2').ravel()
        view = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob),
                                       'byteLength': values.nbytes, 'target': 34963})
        blob.extend(values.tobytes())
        index = len(document['accessors'])
        document['accessors'].append({'bufferView': view, 'componentType': 5123,
                                     'count': len(values), 'type': 'SCALAR',
                                     'min': [int(values.min())], 'max': [int(values.max())]})
        return index

    document['meshes'][0]['primitives'][0]['indices'] = append_indices(kept)
    document['nodes'][0]['name'] = 'Imported_wooden_display_frame'
    roots = list(document['scenes'][document.get('scene', 0)]['nodes'])

    def import_piece(name):
        part, data = G.decode(raw[name])
        if part.get('skins') or part.get('animations'):
            raise ValueError('Only static imported display pieces are supported.')
        policy = document['extras']['rabbitlands_scenery_images']
        incoming = part.get('extras', {}).get('rabbitlands_scenery_images', empty_policy)
        if any('uri' in image and image['uri'] not in incoming['resources']
               for image in part.get('images', [])):
            raise ValueError('External source image is missing its declared texture policy.')
        if policy['schema'] != incoming['schema'] or policy['mipPolicy'] != incoming['mipPolicy']:
            raise ValueError('Imported scenery texture policies disagree.')
        for uri, digest in incoming['resources'].items():
            if uri in policy['resources'] and policy['resources'][uri] != digest:
                raise ValueError('Shared image has conflicting source hashes.')
            policy['resources'][uri] = digest
            policy['imagePolicies'][uri] = sorted(set(policy['imagePolicies'].get(uri, []))
                                                  | set(incoming['imagePolicies'][uri]))
        offsets = {key: len(document.setdefault(key, [])) for key in
                   ('bufferViews', 'accessors', 'images', 'samplers', 'textures', 'materials', 'meshes', 'nodes')}
        while len(blob) % 4:
            blob.append(0)
        binary_offset = len(blob)
        blob.extend(data)
        for view in part.get('bufferViews', []):
            row = copy.deepcopy(view)
            row['byteOffset'] = row.get('byteOffset', 0) + binary_offset
            document['bufferViews'].append(row)
        for accessor in part.get('accessors', []):
            row = copy.deepcopy(accessor)
            if 'sparse' in row:
                raise ValueError('Sparse source needs a separate reviewed adapter.')
            row['bufferView'] += offsets['bufferViews']
            document['accessors'].append(row)
        for image in part.get('images', []):
            row = copy.deepcopy(image)
            if 'bufferView' in row:
                row['bufferView'] += offsets['bufferViews']
            document['images'].append(row)
        document['samplers'].extend(copy.deepcopy(part.get('samplers', [])))
        for texture in part.get('textures', []):
            row = copy.deepcopy(texture)
            row['source'] += offsets['images']
            if 'sampler' in row:
                row['sampler'] += offsets['samplers']
            document['textures'].append(row)

        def textures(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.endswith('Texture') and isinstance(child, dict) and 'index' in child:
                        child['index'] += offsets['textures']
                    else:
                        textures(child)
            elif isinstance(value, list):
                for child in value:
                    textures(child)

        for material in part.get('materials', []):
            row = copy.deepcopy(material)
            textures(row)
            document['materials'].append(row)
        for mesh in part.get('meshes', []):
            row = copy.deepcopy(mesh)
            for primitive in row['primitives']:
                primitive['attributes'] = {key: value + offsets['accessors']
                                           for key, value in primitive['attributes'].items()}
                primitive['indices'] += offsets['accessors']
                primitive['material'] += offsets['materials']
            document['meshes'].append(row)
        for node in part['nodes']:
            row = copy.deepcopy(node)
            if 'mesh' in row:
                row['mesh'] += offsets['meshes']
            if 'children' in row:
                row['children'] = [i + offsets['nodes'] for i in row['children']]
            document['nodes'].append(row)
        for key in ('extensionsUsed', 'extensionsRequired'):
            if key in part:
                document[key] = sorted(set(document.get(key, [])) | set(part[key]))
        return [i + offsets['nodes'] for i in part['scenes'][part.get('scene', 0)]['nodes']]

    templates = {name: import_piece(name) for name in INPUTS[1:]}

    def instance(index):
        # glTF nodes have one parent. Instances share meshes and materials,
        # while every placement gets its own small transform hierarchy.
        row = copy.deepcopy(document['nodes'][index])
        if 'children' in row:
            row['children'] = [instance(child) for child in row['children']]
        result = len(document['nodes'])
        document['nodes'].append(row)
        return result

    kinds = ('lens_tripod', 'crystal_ball_stand', 'crystal_cluster')
    scales = {'lens_tripod': .13, 'crystal_ball_stand': .18, 'crystal_cluster': .14}
    # References share immutable imported meshes. Nine pieces sit on the
    # original boards, inside the shelf's existing width/depth/height bounds.
    for level, height in enumerate((.212, .611, 1.024)):
        for column, x in enumerate((-.30, 0, .30)):
            name = kinds[(column + level) % len(kinds)]
            scale = scales[name]
            children = [instance(index) for index in templates[name]]
            roots.append(len(document['nodes']))
            document['nodes'].append({'name': f'Magical_display_{level}_{column}_{name}',
                                      'children': children, 'translation': [x, height, 0],
                                      'scale': [scale] * 3})
    document['scenes'][document.get('scene', 0)]['nodes'] = roots
    document['buffers'][0]['byteLength'] = len(blob)
    document['asset']['generator'] = 'Rabbit Lands imported magical-display assembly'
    document['asset']['extras'] = {'newModelGeneration': False, 'processing': SCRIPT, **proof}
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'magic_shelf.glb'
    destination.write_bytes(G.encode(document, bytes(blob)))
    if bytes(blob[:len(binary)]) != binary:
        raise ValueError('Original shelf geometry buffer changed.')
    images = []
    for image in document['images']:
        if 'uri' in image:
            path = (root / FOLDER / image['uri']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Image escaped the client checkout.')
            data = path.read_bytes()
            images.append({'sha256': sha(data), 'bytes': len(data), 'uri': image['uri']})
        else:
            view = document['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            data = bytes(blob[start:start + view['byteLength']])
            images.append({'sha256': sha(data), 'bytes': len(data)})
    return {'id': 'magic_shelf', 'source': sources['potion_shelf'].relative_to(root).as_posix(),
            'sourceSha256': sha(raw['potion_shelf']),
            'output': destination.relative_to(root).as_posix(), 'sha256': sha(destination.read_bytes()),
            'sources': [{'source': path.relative_to(root).as_posix(), 'sha256': sha(raw[name])}
                        for name, path in sources.items()],
            'processingScript': SCRIPT, 'processingScriptSha256': sha((root / SCRIPT).read_bytes()),
            'images': images,
            'bounds': [[-.5364752411842346, 0, -.16803336143493652],
                       [.5364752411842346, 1.600000023841858, .16803336143493652]],
            'sourceBinaryPrefixPreserved': True, 'newModelGeneration': False,
            'materialVariant': None, 'selectionProof': proof}


if __name__ == '__main__':
    from prepare_underground_scenery import TOWN_SELECTION
    record = package_magic_shelf(ROOT / FOLDER)
    path = ROOT / 'eloria-assets/source/world_objects/underground/reused-scenery.json'
    report = json.loads(path.read_bytes())
    records = [r for r in report['assets'] if r['id'] != record['id']]
    order = {name: i for i, name in enumerate(TOWN_SELECTION)}
    at = next((i for i, row in enumerate(records)
               if row['id'] in order and order[row['id']] > order[record['id']]), len(records))
    records.insert(at, record)
    report['assets'] = records
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(record['selectionProof']))
