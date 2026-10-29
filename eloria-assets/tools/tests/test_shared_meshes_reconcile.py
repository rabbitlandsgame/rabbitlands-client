"""Reconciliation preserves index newlines while refreshing exact file hashes."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shared_meshes as sm


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_reconcile_preserves_index_format_and_updates_consumers(tmp_path, monkeypatch, newline):
    maps = tmp_path / 'maps'
    pool = maps / '_shared/meshes'
    pool.mkdir(parents=True)
    index = pool / 'index.json'
    data = {'prototypes': {'prop': {'sha256': '0' * 64, 'bytes': 1, 'images': {}}}}
    index.write_bytes((json.dumps(data, indent=2) + '\n').replace('\n', newline).encode())
    payload = sm.write_glb({'asset': {'version': '2.0'},
                            'buffers': [{'byteLength': 4}]}, b'\0' * 4)
    (pool / 'prop.glb').write_bytes(payload)
    directory = maps / 'room'
    directory.mkdir()
    manifest = directory / 'world.json'
    manifest.write_text(json.dumps({'externalMeshes': {'../_shared/meshes/prop.glb': '0' * 64}}))
    monkeypatch.setattr(sm, 'MAPS', maps)
    monkeypatch.setattr(sm, 'POOL', pool)
    monkeypatch.setattr(sm, 'INDEX', index)
    sm.reconcile(prototypes={'prop'}, manifests=[manifest])
    digest = hashlib.sha256(payload).hexdigest()
    result = json.loads(index.read_bytes())['prototypes']['prop']
    assert result['sha256'] == digest and result['bytes'] == len(payload)
    assert result['images'] == {}
    assert json.loads(manifest.read_bytes())['externalMeshes']['../_shared/meshes/prop.glb'] == digest
    raw = index.read_bytes()
    assert (b'\r\n' in raw) == (newline == '\r\n')
