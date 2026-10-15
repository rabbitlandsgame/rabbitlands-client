import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "eloria-assets/source/player_models/native"
REQUIRED = {"Idle_A", "Idle_Subtle", "Walk", "Jog", "Fighting_Idle",
            "Sword_Attack", "Spell_Simple_Shoot", "Hit_Chest", "Death_A",
            "Sitting_Enter", "Sitting_Idle", "Sitting_Exit", "Farm_Harvest",
            "PickUp_Table", "Throw_Object"}


def glb_document(path):
    data = path.read_bytes()
    assert data[:4] == b"glTF"
    version, total = struct.unpack_from("<II", data, 4)
    assert version == 2 and total == len(data)
    size, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A
    return json.loads(data[20:20 + size])


def test_native_characters_preserve_original_gltf_resources():
    for sex in ("Female", "Male"):
        document = json.loads((NATIVE / f"Superhero_{sex}_FullBody.gltf").read_text())
        assert len(document["skins"]) == 1
        assert len(document["skins"][0]["joints"]) == 65
        assert len(document["meshes"]) == 3
        assert len(document["materials"]) == 3
        assert len(document["images"]) == 7
        for resource in document["buffers"] + document["images"]:
            assert (NATIVE / resource["uri"]).is_file()


def test_native_animation_library_is_not_rebuilt():
    document = glb_document(NATIVE / "Universal_Animation_Library.glb")
    clips = {animation["name"] for animation in document["animations"]}
    assert len(clips) >= 120 and REQUIRED <= clips
    paths = {channel["target"]["path"] for animation in document["animations"]
             for channel in animation["channels"]}
    assert {"rotation", "translation"} <= paths


def test_the_client_binds_the_clips_it_ships():
    """The action map has to name clips that are actually in the library.

    This held `actor_glb_runtime.cpp` to a required clip list while the C
    client was the one playing them. That client is gone, and the Godot client
    binds actions to clips in `data/animations/luminous.json` instead, so what
    is worth holding is that every clip it names exists in the library it
    loads - a typo there is an action that silently does nothing.
    """
    contract = json.loads((ROOT / "godot-client/data/animations/luminous.json")
                          .read_text(encoding="utf-8"))
    library = glb_document(NATIVE / "Universal_Animation_Library.glb")
    clips = {animation["name"] for animation in library["animations"]}

    named = set(contract.get("loopingClips", []))
    for action in contract.get("actions", {}).values():
        if isinstance(action, str):
            named.add(action)
        elif isinstance(action, dict):
            named.update(str(value) for key, value in action.items()
                         if key in ("clip", "enter", "loop", "exit"))
    assert named, "the animation contract binds no clips at all"
    assert named <= clips, sorted(named - clips)
