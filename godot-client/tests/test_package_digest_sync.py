"""A rebuilt package replaces an already-published map digest."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "eloria-assets/tools/sync_package_content.py"
SPEC = importlib.util.spec_from_file_location("package_digest_sync", SOURCE)
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


@pytest.mark.parametrize("entry", [
    {"id": "demo", "arrival": [2, 3], "packageSha256": "0" * 64},
    {"id": "demo", "packageSha256": "0" * 64, "arrival": [2, 3]},
    {"id": "demo", "packageSha256": "0" * 64},
])
def test_rebuilt_package_replaces_existing_digest_and_then_settles(tmp_path, monkeypatch, entry):
    manifest = tmp_path / "world.json"
    manifest.write_bytes(b'{"asset":{"glb":"world.glb"}}\r\n')
    (tmp_path / "world.glb").write_bytes(b"rebuilt geometry")
    monkeypatch.setattr(sync, "registry_packages", lambda: {"demo": manifest})
    original = {"maps": [copy.deepcopy(entry)], "unrelated": {"post": [4, 5]}}
    text, published, missing, count = sync.publish_digests(original)
    assert text is not None
    updated = json.loads(text)
    assert updated["maps"][0]["packageSha256"] == sync.digest_for(manifest)
    assert updated["unrelated"] == {"post": [4, 5]}
    assert not missing and count == 1
    again, _, _, _ = sync.publish_digests(updated)
    assert again is None


def test_compact_marker_uses_final_floor_even_when_old_location_has_no_ground(tmp_path):
    sys.path.insert(0, str(SOURCE.parents[1] / 'maps/nymara-regions/_toolkit'))
    from amberwood import gltf as G, mesh as M
    builder = G.GltfBuilder()
    builder.add_material(G.Material('stone'))
    floor = M.quad([[0,7,0],[8,7,0],[8,7,-8],[0,7,-8]],material='stone')
    builder.add_mesh('floor',floor)
    builder.add_node(G.Node('Walk_NewCourtyard',mesh='floor'))
    builder.write_glb(str(tmp_path / 'world.glb'))
    data = {'landscapeRevision':'compact-test','coordinateTransform':{
        'serverOrigin':[0,0],'metresPerTile':1},'npcMarkers':[
            {'id':'keeper','position':[99,140,-99],'serverTile':[99,99]}]}
    (tmp_path / 'world.json').write_text(json.dumps(data),encoding='utf-8')
    def retired_factory():
        pytest.fail('The legacy landform is not the compact map floor.')
    section = sync.Section('posts',('npcMarkers',))
    result = sync.sync(tmp_path,[section],retired_factory,
        {'posts':[{'id':'keeper','serverTile':[3,4]}]},[])
    updated = json.loads(result)
    assert updated['npcMarkers'][0] == {'id':'keeper','position':[3,7,-4],'serverTile':[3,4]}
    (tmp_path / 'world.json').write_text(result,encoding='utf-8')
    assert sync.sync(tmp_path,[section],retired_factory,
        {'posts':[{'id':'keeper','serverTile':[3,4]}]},[]) is None
