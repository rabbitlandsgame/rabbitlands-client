from types import SimpleNamespace
import numpy as np
import pytest

from video_motion import blender_bone_identity as identity


def fixture():
    blob = np.array([0, 1, 0, 0, 0, 1, 0, 0], dtype="<f4").tobytes()
    doc = {
        "nodes": [
            {"name": "A", "children": [1]},
            {"name": "Bone"},
            {"name": "B", "children": [3]},
            {"name": "Bone"},
        ],
        "skins": [{"name": "A", "joints": [1]}, {"name": "B", "joints": [3]}],
        "bufferViews": [
            {"byteOffset": 0, "byteLength": 8},
            {"byteOffset": 8, "byteLength": 24},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "type": "SCALAR", "count": 2},
            {"bufferView": 1, "componentType": 5126, "type": "VEC3", "count": 2},
        ],
        "animations": [
            {
                "name": "Move",
                "samplers": [{"input": 0, "output": 1}],
                "channels": [
                    {"sampler": 0, "target": {"node": n, "path": "translation"}}
                    for n in [1, 3]
                ],
            }
        ],
    }
    return doc, blob


def test_duplicate_joint_world_motion_is_proved_through_ancestors():
    doc, blob = fixture()
    result = identity.prove_duplicate_joint_motion(doc, blob, {"Bone": [1, 3]})
    assert result[0]["original_joint_nodes"] == [1, 3]


@pytest.mark.parametrize("change", ["rest", "curve", "ancestor"])
def test_duplicate_name_alone_cannot_hide_motion_or_rest_changes(change):
    doc, blob = fixture()
    if change == "rest":
        doc["nodes"][3]["translation"] = [1, 0, 0]
    elif change == "ancestor":
        doc["nodes"][2]["scale"] = [2, 1, 1]
    else:
        doc["animations"][0]["channels"].pop()
    with pytest.raises(ValueError):
        identity.prove_duplicate_joint_motion(doc, blob, {"Bone": [1, 3]})


def test_skin_identity_rest_and_every_duplicate_binding_are_retained(monkeypatch):
    doc, blob = fixture()
    monkeypatch.setattr(identity, "document", lambda _: (doc, blob))

    def arm(name):
        bone = SimpleNamespace(name="Bone", head=np.zeros(3), parent=None)
        return SimpleNamespace(
            name=name,
            matrix_world=np.eye(3),
            pose=SimpleNamespace(bones={"Bone": bone}),
        )

    arms = [arm("A"), arm("B")]
    bindings, report = identity.multiple_armature_bindings("unused", arms)
    assert len(bindings["Bone"]) == 2
    assert len(report["original_skin_and_joint_node_bindings"]) == 2
    mapped, _ = identity.multiple_armature_bindings("unused", arms, {"Bone": [3]})
    assert mapped["Bone"] == [(arms[1], arms[1].pose.bones["Bone"])]
    unobserved, full_report = identity.multiple_armature_bindings("unused", arms, {})
    assert unobserved == {}
    assert {
        row["source_joint_node"]
        for row in full_report["original_skin_and_joint_node_bindings"]
    } == {1, 3}
    with pytest.raises(ValueError, match="original named skin"):
        identity.multiple_armature_bindings("unused", arms, {"Bone": [0]})
    arms[1].name = "Unrelated"
    with pytest.raises(ValueError, match="skin identity"):
        identity.multiple_armature_bindings("unused", arms)


def test_observation_matching_requires_entire_immutable_matrix_sequence():
    from video_motion.blender_bone_observations import exact_observation_matches

    old = np.array([np.eye(4), np.eye(4)])
    other = old.copy()
    other[1, 0, 3] = 1e-9
    assert exact_observation_matches({1: old, 2: other}, old) == [1]
    assert exact_observation_matches({2: other}, old) == []


def test_unobserved_duplicate_names_keep_all_nodes_without_a_named_reference(
    tmp_path, monkeypatch
):
    import json
    from video_motion import blender_bone_observations as observations
    from video_motion import native_shapes, asset

    doc, blob = fixture()
    doc["nodes"].append({"name": "Observed"})
    source, witness = tmp_path / "original.glb", tmp_path / "witness.json"
    source.write_bytes(b"immutable original")
    digest = "a" * 64
    frozen = {
        "sha256": digest,
        "clips": {"Move": [{"time": 0.25, "bones": {"Observed": np.eye(4).ravel().tolist()}}]},
    }
    witness.write_text(json.dumps(frozen))
    original_bytes = witness.read_bytes()

    class Source:
        joints = [1, 3, 4]
        names = [node["name"] for node in doc["nodes"]]
        d, b = doc, blob

        def __init__(self, _):
            pass

        def sample(self, *_):
            return np.zeros(1), np.zeros(1), np.zeros(1), {}

        def world(self, *_):
            return np.tile(np.eye(4), (5, 1, 1))

    monkeypatch.setattr(native_shapes, "NativeShapeAsset", Source)
    monkeypatch.setattr(asset, "digest", lambda _: digest)

    def unexpected_alias_proof(*_):
        pytest.fail("An unobserved duplicate name must not choose or prove an alias")

    monkeypatch.setattr(identity, "prove_duplicate_joint_motion", unexpected_alias_proof)
    report = observations.prepare_bone_observations(
        {"source": str(source), "witness": str(witness), "output": str(tmp_path)}
    )
    assert "Bone" not in report["observed_original_joint_nodes"]
    assert report["unobserved_duplicate_joint_groups"] == [
        {"name": "Bone", "original_joint_nodes": [1, 3]}
    ]
    assert witness.read_bytes() == original_bytes
