"""Independent qualification rejects damaged proposals even with fresh hashes."""

import json

import numpy as np
import pytest

from pack_creature_storage import prepare
from qualify_creature_storage import exact_source, witness
from test_creature_storage import fixture
from video_motion.asset import digest, read_glb, write_glb
from video_motion.packing import append_array


def job_fixture(tmp_path, mode="normal"):
    document, binary, add = fixture()
    if mode == "all_gone":
        document["animations"][0]["samplers"][0]["output"] = add(np.zeros((9, 1)))
        document["animations"][0]["channels"] = document["animations"][0]["channels"][
            :1
        ]
        document["animations"][0]["samplers"] = document["animations"][0]["samplers"][
            :1
        ]
    if mode == "no_morph":
        document["meshes"][0]["primitives"][0].pop("targets")
        document["meshes"][0].pop("weights")
        document["meshes"][0]["extras"].pop("targetNames")
        document["nodes"][0].pop("weights")
        document["animations"][0]["channels"] = document["animations"][0]["channels"][
            1:
        ]
    source, candidate = tmp_path / "source.glb", tmp_path / "candidate.glb"
    write_glb(source, document, binary)
    report = prepare(source, candidate)
    receipt = tmp_path / "prepare.json"
    receipt.write_text(json.dumps(report))
    return dict(
        source=str(source),
        candidate=str(candidate),
        preparation=str(receipt),
        output=str(tmp_path / "proof"),
    )


@pytest.mark.parametrize("mode", ["normal", "all_gone", "no_morph"])
def test_independently_proves_exact_reductions(tmp_path, mode):
    assert exact_source(job_fixture(tmp_path, mode))["passed"]


@pytest.mark.parametrize(
    "damage",
    [
        "geometry",
        "normal",
        "curve",
        "clock",
        "duplicate_clock",
        "mesh_name",
        "mesh_extras",
        "channel_metadata",
        "sampler_metadata",
        "accessor_bounds",
    ],
)
def test_modified_retained_bits_rejected_even_with_updated_hash(tmp_path, damage):
    job = job_fixture(tmp_path)
    document, binary = read_glb(job["candidate"])
    binary = bytearray(binary)
    primitive = document["meshes"][0]["primitives"][0]
    sampler = document["animations"][0]["samplers"][0]
    if damage in ("geometry", "normal"):
        key = "POSITION" if damage == "geometry" else "NORMAL"
        primitive["attributes"][key] = append_array(
            document, binary, np.ones((3, 3)), "VEC3"
        )
    elif damage in ("clock", "curve", "duplicate_clock"):
        if damage == "clock":
            sampler["input"] = append_array(
                document, binary, np.array([[0], [0.251], [1]]), "SCALAR"
            )
        elif damage == "duplicate_clock":
            sampler["input"] = append_array(
                document, binary, np.array([[0], [0], [1]]), "SCALAR"
            )
        else:
            sampler["output"] = append_array(
                document, binary, np.array([[0.1], [0.7], [-0.2]]), "SCALAR"
            )
    elif damage == "mesh_name":
        document["meshes"][0]["name"] = "ChangedName"
    elif damage == "mesh_extras":
        document["meshes"][0]["extras"]["other"] = 43
    elif damage == "channel_metadata":
        document["animations"][0]["channels"][0]["extras"] = {"changed": True}
    elif damage == "sampler_metadata":
        sampler["extras"] = {"changed": True}
    elif damage == "accessor_bounds":
        document["accessors"][primitive["attributes"]["POSITION"]]["min"] = [
            -123.0,
            0.0,
            0.0,
        ]
    write_glb(job["candidate"], document, binary)
    receipt = json.loads(open(job["preparation"]).read())
    receipt["candidate_sha256"] = digest(job["candidate"])
    with open(job["preparation"], "w") as handle:
        json.dump(receipt, handle)
    with pytest.raises(AssertionError):
        exact_source(job)


@pytest.mark.parametrize("container", ["nodes", "meshes"])
def test_new_nonzero_default_is_rejected_when_source_used_implicit_zero(
    tmp_path, container
):
    document, binary, _ = fixture()
    for obj in (document["meshes"][0], document["nodes"][0]):
        obj.pop("weights")
    source, candidate = tmp_path / "source.glb", tmp_path / "candidate.glb"
    write_glb(source, document, binary)
    report = prepare(source, candidate)
    document, binary = read_glb(candidate)
    document[container][0]["weights"] = [1.0]
    write_glb(candidate, document, binary)
    report["candidate_sha256"] = digest(candidate)
    receipt = tmp_path / "prepare.json"
    receipt.write_text(json.dumps(report))
    with pytest.raises(AssertionError):
        exact_source(
            dict(
                actor="fixture",
                source=str(source),
                candidate=str(candidate),
                preparation=str(receipt),
                output=str(tmp_path / "proof"),
            )
        )


def test_legacy_physical_observations_keep_their_original_residual(tmp_path):
    job = job_fixture(tmp_path)
    job["witness"] = str(tmp_path / "frozen-source.json")
    witness(job)
    path = tmp_path / "frozen-source.json"
    frozen = json.loads(path.read_text())
    for entries in frozen["clips"].values():
        for entry in entries:
            entry.pop("surface_normals")
            entry["surface"][0][0] += 0.000003
    path.write_text(json.dumps(frozen))
    original = path.read_bytes()
    report = witness(job)
    assert path.read_bytes() == original
    assert report["source_candidate_position_error"] == 0
    assert (
        report["original_witness_position_error_over_height"]
        == report["original_source_witness_position_error_over_height"]
    )
    assert report["original_witness_position_error_over_height"] > 1e-8


def test_preexisting_empty_target_names_on_a_mesh_without_morphs_are_preserved(
    tmp_path,
):
    job = job_fixture(tmp_path, "no_morph")
    for key in ("source", "candidate"):
        document, binary = read_glb(job[key])
        document["meshes"][0].setdefault("extras", {})["targetNames"] = []
        write_glb(job[key], document, binary)
    receipt = json.loads(open(job["preparation"]).read())
    receipt["source_sha256"] = digest(job["source"])
    receipt["candidate_sha256"] = digest(job["candidate"])
    with open(job["preparation"], "w") as handle:
        json.dump(receipt, handle)
    assert exact_source(job)["passed"]


def duplicate_curve_job(tmp_path):
    document, binary, _ = fixture()
    binary = bytearray(binary)
    channel = dict(document["animations"][0]["channels"][-1])
    sampler = dict(document["animations"][0]["samplers"][channel["sampler"]])
    from video_motion.creature_storage import _array

    values = _array(document, binary, sampler["output"]).view("<f4") + np.float32(0.125)
    sampler["output"] = append_array(
        document, binary, values, document["accessors"][sampler["output"]]["type"]
    )
    channel["sampler"] = len(document["animations"][0]["samplers"])
    document["animations"][0]["samplers"].append(sampler)
    document["animations"][0]["channels"].append(channel)
    source, candidate = tmp_path / "source.glb", tmp_path / "candidate.glb"
    write_glb(source, document, binary)
    report = prepare(source, candidate)
    receipt = tmp_path / "prepare.json"
    receipt.write_text(json.dumps(report))
    return dict(
        source=str(source),
        candidate=str(candidate),
        preparation=str(receipt),
        output=str(tmp_path / "proof"),
    )


def test_existing_duplicate_property_occurrences_are_preserved_without_repair(tmp_path):
    job = duplicate_curve_job(tmp_path)
    assert (
        exact_source(job)[
            "preexisting_duplicate_property_curves_preserved_in_occurrence_order"
        ]
        == 1
    )


@pytest.mark.parametrize("damage", ["reorder", "drop", "extra"])
def test_duplicate_property_occurrence_changes_are_rejected(tmp_path, damage):
    job = duplicate_curve_job(tmp_path)
    document, binary = read_glb(job["candidate"])
    channels = document["animations"][0]["channels"]
    if damage == "reorder":
        channels[-2], channels[-1] = channels[-1], channels[-2]
    if damage == "drop":
        channels.pop()
    if damage == "extra":
        channels.append(dict(channels[-1]))
    write_glb(job["candidate"], document, binary)
    receipt = json.loads(open(job["preparation"]).read())
    receipt["candidate_sha256"] = digest(job["candidate"])
    with open(job["preparation"], "w") as handle:
        json.dump(receipt, handle)
    with pytest.raises((AssertionError, KeyError)):
        exact_source(job)
