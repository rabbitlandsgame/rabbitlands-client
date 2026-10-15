"""Client delivery contract for the complete reviewed Revision 15 expansion."""
import hashlib
import json
from pathlib import Path
import struct
import sys

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / 'tools'))
import creature_facing


def test_all_expansion_models_preserve_reviewed_assets_and_action_maps():
    manifest = json.loads((CLIENT / 'data/actors/basic_creature_expansion.json').read_text())
    models = json.loads((CLIENT / 'data/actors/models.json').read_text())
    assets = json.loads((CLIENT / 'data/actors/native_asset_catalog.json').read_text())
    assert len(manifest['creatures']) == 100
    assert set(assets['basicCreatureExpansion']) == {e['type'] for e in manifest['creatures']}
    clips_count = 0
    for entry in manifest['creatures']:
        key = entry['type']
        assert models['actorTypes'][str(entry['actor_type'])] == key
        model = models['models'][key]
        data = (CLIENT / model['scene'].removeprefix('res://')).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], key
        size = struct.unpack_from('<I', data, 12)[0]
        gltf = json.loads(data[20:20 + size])
        clips = {c['name'] for c in gltf['animations']}
        assert clips == set(entry['animation_clips'])
        clips_count += len(clips)
        animation_map = json.loads((CLIENT / model['animationMap'].removeprefix('res://')).read_text())
        assert set(animation_map['actions'].values()) <= clips
        assert set(animation_map['loopingClips']) == clips & {'Idle_A', 'Fighting_Idle', 'Walk', 'Jog', 'Fly', 'Swim'}
        assert model['animationLibrary'] == model['scene']
        assert 0 < model['import']['scale'] <= 8
        facing = creature_facing.correction(CLIENT / model['scene'].removeprefix('res://'))
        if facing is not None:
            assert model['import']['forwardAxisCorrectionDegreesY'] == facing, key
        bones = {gltf['nodes'][j]['name'] for j in gltf['skins'][0]['joints']}
        assert set(model['attachments'].values()) <= bones
        assert sum(len(p.get('targets', [])) for m in gltf['meshes'] for p in m['primitives']) == entry['morph_targets']
    assert clips_count == 719
