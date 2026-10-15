"""The shipped west-gate ramp has aligned, joined decks at both module seams."""
from pathlib import Path
import json
import re
import struct
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import export_collision as X
import ownership as O

CHECKOUT = HERE.parents[3]
CATALOG = CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json"

NAMES = [
    'Authored_sw_isle_kit_sw_causeway_arch_ramp_g053_001',
    'Authored_sw_isle_kit_sw_causeway_arch_ramp_g053_002',
    'Authored_sw_isle_kit_sw_causeway_arch_ramp_g037_001',
]


def glb_document(path):
    """Read only the JSON header while searching; load triangle buffers only for matching decks."""
    with path.open('rb') as handle:
        magic, version, _length, size, kind = struct.unpack('<4sIIII', handle.read(20))
        assert magic == b'glTF' and version == 2 and kind == 0x4E4F534A, path
        return json.loads(handle.read(size))


def find_placements(packages, names):
    matches = {name: [] for name in names}
    for region, manifest_path in packages.items():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['streamingChunks']['chunks'], region
        for chunk in manifest['streamingChunks']['chunks']:
            child_path = manifest_path.parent / chunk['manifest']
            child = json.loads(child_path.read_text(encoding='utf-8'))
            glb_path = child_path.parent / child['asset']['glb']
            document = glb_document(glb_path)
            for index, node in enumerate(document.get('nodes', [])):
                if node.get('name') in matches:
                    matches[node['name']].append((region, manifest, glb_path, index))
    for name, found in matches.items():
        assert len(found) == 1, (name, 'must be published exactly once across active packages',
                                 [(region, str(path)) for region, _manifest, path, _index in found])
    return {name: found[0] for name, found in matches.items()}


@pytest.fixture(scope='module')
def decks():
    entries = json.loads(CATALOG.read_text(encoding='utf-8'))['entries']
    # node_name is the retained-library identity, independent of the scene wrapper's renamed path.
    owners = {name: [] for name in NAMES}
    packages = {}
    for entry in entries:
        region = entry['id']
        packages[region] = HERE.parent / region / 'client/world.json'
        scene = CHECKOUT / 'godot-client' / entry['scenePath'].removeprefix('res://')
        source = scene.read_text(encoding='utf-8')
        for name in NAMES:
            occurrences = re.findall(r'^node_name = ' + re.escape(json.dumps(name)) + r'$', source, re.M)
            owners[name].extend([region] * len(occurrences))
    for name, regions in owners.items():
        assert len(regions) == 1, (name, 'must have one active authored owner', regions)
    located = find_placements(packages, NAMES)
    result = []
    for name in NAMES:
        region, manifest, path, root = located[name]
        assert region == owners[name][0], (name, 'published owner differs from authored owner')
        document, body = X.GR.load(path)
        matrices, parents = X.GR.hierarchy(document)
        nodes = document['nodes']
        meshes = []
        for i, node in enumerate(nodes):
            if 'mesh' not in node:
                continue
            current, walk = i, False
            while True:
                walk |= nodes[current].get('name', '').startswith('Walk_')
                if current == root:
                    if walk:
                        meshes.append(i)
                    break
                if current not in parents:
                    break
                current = parents[current]
        assert meshes, name
        translation = np.asarray(manifest['continentGeography']['translation'], dtype=float)
        origin = matrices[root][:3, 3] + translation
        from shapely.geometry import Point
        assert O.geometry(O.rings(manifest['continentGeography'])).covers(Point(origin[0], origin[2])), name
        # Chunk geometry is territory-local; compare modules in a common continent frame.
        points = X.GR.triangles(document, body, meshes).reshape(-1, 3) + translation
        axis = matrices[root][[0, 2], 0]
        axis = axis / np.linalg.norm(axis)
        across = np.array([-axis[1], axis[0]])
        distance = points[:, [0, 2]] @ axis
        result.append(dict(axis=axis, centre=origin[[0, 2]] @ across,
                           low=distance.min(), high=distance.max(),
                           low_height=np.median(points[np.isclose(distance, distance.min(), atol=1e-4,
                                                                 rtol=0), 1]),
                           high_height=np.median(points[np.isclose(distance, distance.max(), atol=1e-4,
                                                                  rtol=0), 1])))
    return result


def tiny_package(root, region, chunk, names):
    """Minimal declared chunk inventory, deliberately unrelated to the historical lattice cell."""
    package = root / region
    folder = package / 'chunks' / chunk
    folder.mkdir(parents=True)
    document = json.dumps({'asset': {'version': '2.0'}, 'nodes': [{'name': name} for name in names]}).encode()
    document += b' ' * (-len(document) % 4)
    (folder / 'decks.glb').write_bytes(struct.pack('<4sIIII', b'glTF', 2, 20 + len(document),
                                                len(document), 0x4E4F534A) + document)
    (folder / 'piece.json').write_text(json.dumps({'asset': {'glb': 'decks.glb'}}), encoding='utf-8')
    path = package / 'world.json'
    path.write_text(json.dumps({'streamingChunks': {'chunks': [
        {'id': chunk, 'manifest': f'chunks/{chunk}/piece.json'}]}}), encoding='utf-8')
    return path


def test_ramp_search_follows_declared_chunks_across_maps(tmp_path):
    a = tiny_package(tmp_path, 'new_owner_a', '91_06', NAMES[:1])
    b = tiny_package(tmp_path, 'new_owner_b', '00_73', NAMES[1:])
    found = find_placements({'new_owner_a': a, 'new_owner_b': b}, NAMES)
    assert [found[name][0] for name in NAMES] == ['new_owner_a', 'new_owner_b', 'new_owner_b']
    assert found[NAMES[0]][2].name == 'decks.glb'


@pytest.mark.parametrize('fault', ['missing', 'duplicate'])
def test_ramp_search_refuses_lost_or_duplicated_placements(tmp_path, fault):
    a = tiny_package(tmp_path, 'new_owner_a', '91_06', NAMES if fault == 'duplicate' else NAMES[1:])
    packages = {'new_owner_a': a}
    if fault == 'duplicate':
        packages['new_owner_b'] = tiny_package(tmp_path, 'new_owner_b', '00_73', NAMES[:1])
    with pytest.raises(AssertionError, match='must be published exactly once'):
        find_placements(packages, NAMES)


@pytest.mark.parametrize('joint', [0, 1])
def test_published_decks_meet_without_a_gap_or_sideways_offset(decks, joint):
    lower, upper = decks[joint:joint + 2]
    np.testing.assert_allclose(lower['axis'], upper['axis'], atol=1e-5)
    assert abs(lower['centre'] - upper['centre']) < .01
    assert abs(upper['low'] - lower['high']) < .01
    assert abs(upper['low_height'] - lower['high_height']) < .04
