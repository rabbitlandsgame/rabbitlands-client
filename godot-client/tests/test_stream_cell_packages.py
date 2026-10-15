"""The emitted files must publish actual shared cells, not empty fresh frames."""
import json
import hashlib
from functools import lru_cache
from pathlib import Path
import struct
import sys

import numpy as np
import pytest

MAPS = Path(__file__).resolve().parents[2] / 'eloria-assets/maps'
REGIONS = ('amberwood','whitehorn_range','grey_moors','mirrorhold',
    'amethyst_barrens','westhaven','four_gates','crownwater',
    'sunmane_steppe','verdant_stair','ssarathi_ruins','manymouth_delta')
sys.path.insert(0, str(MAPS / 'nymara-regions/_toolkit'))
import glb_reader as GLB


def document(path):
    with path.open('rb') as file:
        file.seek(12)
        size,kind=struct.unpack('<II',file.read(8))
        assert kind==0x4e4f534a
        return json.loads(file.read(size))


def triangle_count(doc):
    return sum(doc['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]['count'] // 3
               for node in doc['nodes'] if 'mesh' in node
               for primitive in doc['meshes'][node['mesh']]['primitives'] if primitive.get('mode', 4) == 4)


@lru_cache(maxsize=None)
def texture_record(path):
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n', path
    width, height = struct.unpack('>II', raw[16:24])
    return hashlib.sha256(raw).hexdigest(), (width * height * 16 + 2) // 3


def assert_independent_chunks(package, manifest, full_document):
    stream = manifest['streamingChunks']
    assert stream['schemaVersion'] == '1.0' and stream['coordinateSpace'] == 'territory-local'
    assert 0 < stream['preloadDistance'] < stream['retainDistance']
    assert stream['maximumLoadedChunks'] > 0 and stream['maximumResidentBytes'] > 0
    assert stream['chunks'], (package, 'empty spatial manifest')
    ids, files, triangles = set(), set(), 0
    full_names = {node.get('name', '') for node in full_document['nodes']}
    for cell in stream['chunks']:
        assert cell['id'] not in ids, (package, cell['id'], 'duplicate chunk')
        ids.add(cell['id'])
        source = (package / cell['manifest']).resolve()
        assert source.is_relative_to((package / 'chunks').resolve()), source
        assert source not in files, (source, 'reused manifest')
        files.add(source)
        child = json.loads(source.read_text(encoding='utf-8'))
        assert not child.get('streamingChunks'), (source, 'recursive world import')
        assert child['coordinateTransform'] == manifest['coordinateTransform'], source
        assert child['continentGeography'] == manifest['continentGeography'], source
        glb = (source.parent / child['asset']['glb']).resolve()
        assert glb.is_relative_to(source.parent) and glb != (package / 'world.glb').resolve(), glb
        assert cell.get('glbBytes', cell.get('byteLength')) == glb.stat().st_size, glb
        doc, body = GLB.load(glb)
        mesh_nodes = [index for index, node in enumerate(doc['nodes']) if 'mesh' in node]
        assert mesh_nodes, (glb, 'empty physical chunk')
        assert not {doc['nodes'][i].get('name', '') for i in mesh_nodes} - full_names, glb
        triangles += triangle_count(doc)
        matrices, _ = GLB.hierarchy(doc)
        lower, upper = np.array(cell['bounds']['min']), np.array(cell['bounds']['max'])
        assert (upper >= lower).all(), (glb, 'inverted bounds')
        # Read actual transformed vertices, including props crossing the nominal
        # cell boundary. Centroid-only or terrain-only bounds lose visible props.
        for index in mesh_nodes:
            matrix = matrices[index]
            for primitive in doc['meshes'][doc['nodes'][index]['mesh']]['primitives']:
                points = GLB.accessor(doc, body, primitive['attributes']['POSITION'])
                points = points @ matrix[:3, :3].T + matrix[:3, 3]
                assert (points.min(axis=0) >= lower - .002).all(), (glb, doc['nodes'][index]['name'], 'bounds omit geometry')
                assert (points.max(axis=0) <= upper + .002).all(), (glb, doc['nodes'][index]['name'], 'bounds omit geometry')
        resources = child.get('externalResources', {})
        assert set(resources) == {entry['uri'] for entry in doc.get('images', []) if 'uri' in entry}, glb
        resident = {}
        for relative, expected in resources.items():
            resource = (glb.parent / relative).resolve()
            assert resource.is_relative_to(MAPS.parent.resolve()), resource
            actual, cost = texture_record(resource)
            assert actual == expected, (resource, 'stale external PNG')
            resident[actual] = cost
        assert cell['sharedResourceResidentBytes'] == resident, (glb, 'resident texture estimate differs from actual pixels')
        assert cell['geometryResidentBytes'] >= glb.stat().st_size, glb
        assert cell['estimatedResidentBytes'] >= cell['geometryResidentBytes'] + sum(resident.values()), glb
    assert triangles == triangle_count(full_document), (package, 'chunks lose or duplicate named-territory triangles')


@pytest.mark.parametrize('region',REGIONS)
def test_emitted_region_uses_resolving_single_copy_approaches(region):
    package=MAPS/'four-gates' if region=='four_gates' else MAPS/'nymara-regions'/region
    manifest=json.loads((package/'world.json').read_text(encoding='utf-8'))
    doc=document(package/'world.glb')
    names={n.get('name','') for n in doc['nodes']}
    chunked = manifest.get('continentGeography', {}).get('geometryMode') == 'continent-chunks-v1'
    if chunked:
        assert_independent_chunks(package, manifest, doc)
    for frame in manifest['streamingBorders']:
        assert frame['geometryMode']==('continent-chunks-v1' if chunked else 'continent-owned-v1')
        declared=frame['sceneNodes']
        assert declared or chunked,(region,frame['id'],'empty receiving view')
        assert len(declared)==len(set(declared)),(region,frame['id'],'duplicate membership')
        assert not set(declared)-names,(region,frame['id'],sorted(set(declared)-names))
        if not chunked:
            assert any('_StreamCell_' in name for name in declared)
        translation = frame['globalTranslation']
        assert all(abs(frame['anchor'][i]+translation[i]-frame['globalAnchor'][i])<1e-5 for i in range(3)), (region, frame['id'])
        assert frame['viewHalfWidth'] >= 110 and frame['preloadDistance'] >= 240
    for path in package.glob('world*.glb'):
        assert not [n['name'] for n in document(path)['nodes'] if
            n.get('name','').startswith('StreamView_') or '_StreamOverflow_' in n.get('name','')],path
