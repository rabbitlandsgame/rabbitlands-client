"""Region masters past the part size keep their binary in content-addressed part files."""
from pathlib import Path
import hashlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_toolkit'))
import scene_io as S
import glb_reader as GR
import verify_runtime


def scene(meshes=6, triangles=400, seed=7):
    """`meshes` triangle soups, each with its own position and index views."""
    rng = np.random.default_rng(seed)
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': list(range(meshes))}],
           'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': [], 'buffers': []}
    body = bytearray()
    for m in range(meshes):
        points = rng.normal(size=(triangles * 3, 3)).astype(np.float32)
        order = rng.permutation(triangles * 3).astype(np.uint32)
        for data, kind, component in ((points, 'VEC3', 5126), (order, 'SCALAR', 5125)):
            body.extend(b'\0' * ((-len(body)) % 4))
            doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(body), 'byteLength': data.nbytes})
            body.extend(data.tobytes())
            accessor = {'bufferView': len(doc['bufferViews']) - 1, 'componentType': component,
                        'count': len(data), 'type': kind}
            if kind == 'VEC3':
                accessor.update(min=points.min(0).tolist(), max=points.max(0).tolist())
            doc['accessors'].append(accessor)
        doc['meshes'].append({'primitives': [{'attributes': {'POSITION': 2 * m}, 'indices': 2 * m + 1}]})
        doc['nodes'].append({'name': f'Piece_{m}', 'mesh': m})
    doc['buffers'].append({'byteLength': len(body)})
    return doc, bytes(body)


def export(path, part_bytes, **options):
    doc, body = scene(**options)
    exporter = S.Exporter(path, part_bytes=part_bytes)
    exporter.add(doc, body, list(range(len(doc['nodes']))))
    exporter.write()
    return path


def geometry(document, body):
    """Every primitive's positions and indices, in order."""
    return [(GR.accessor(document, body, p['attributes']['POSITION']), GR.accessor(document, body, p['indices']))
            for mesh in document['meshes'] for p in mesh['primitives']]


def parts(folder):
    return sorted(folder.glob('world.part*.bin'))


def test_a_master_under_the_part_size_stays_one_file(tmp_path):
    glb = export(tmp_path / 'world.glb', part_bytes=10 ** 7)
    document, body = GR.load(glb)
    assert parts(tmp_path) == [] and document['buffers'] == [{'byteLength': len(body)}]


def test_a_large_master_splits_and_reads_back_whole(tmp_path):
    whole = export(tmp_path / 'whole' / 'world.glb', part_bytes=None)
    split = export(tmp_path / 'split' / 'world.glb', part_bytes=20000)
    files = parts(split.parent)
    assert len(files) >= 3
    for file in files:
        assert file.stat().st_size <= 20000
        assert file.name.split('.')[2] == hashlib.sha256(file.read_bytes()).hexdigest()
    expected = geometry(*GR.load(whole))
    for reader in (GR.load, verify_runtime.load_glb):
        document, body = reader(split)
        assert len(document['buffers']) == 1 and all(v['buffer'] == 0 for v in document['bufferViews'])
        for (points, order), (want_points, want_order) in zip(geometry(document, body), expected, strict=True):
            np.testing.assert_array_equal(points, want_points)
            np.testing.assert_array_equal(order, want_order)


def test_rewriting_a_master_removes_the_parts_it_no_longer_names(tmp_path):
    glb = export(tmp_path / 'world.glb', part_bytes=20000)
    before = set(parts(tmp_path))
    export(glb, part_bytes=20000, seed=8)
    after = set(parts(tmp_path))
    assert after and not (before & after)
    export(glb, part_bytes=None)
    assert parts(tmp_path) == []


def test_a_changed_part_is_refused(tmp_path):
    glb = export(tmp_path / 'world.glb', part_bytes=20000)
    part = parts(tmp_path)[-1]
    data = bytearray(part.read_bytes())
    data[5] ^= 0xFF
    part.write_bytes(bytes(data))
    with pytest.raises(ValueError, match='does not match'):
        GR.load(glb)


def test_the_master_digest_covers_every_part(tmp_path):
    first = export(tmp_path / 'a' / 'world.glb', part_bytes=20000, seed=7)
    second = export(tmp_path / 'b' / 'world.glb', part_bytes=20000, seed=7)
    assert first.read_bytes() == second.read_bytes()
    tail = parts(second.parent)[-1]
    doc, body = GR.load(second)
    # Rebuild b with only its last view changed: the GLB's own bytes still differ.
    last = max(doc['bufferViews'], key=lambda v: v['byteOffset'])
    changed = bytearray(body)
    changed[last['byteOffset']] ^= 0xFF
    exporter = S.Exporter(second, part_bytes=20000)
    exporter.add(doc, bytes(changed), doc['scenes'][0]['nodes'])
    exporter.write()
    assert not tail.exists()
    assert hashlib.sha256(first.read_bytes()).digest() != hashlib.sha256(second.read_bytes()).digest()
