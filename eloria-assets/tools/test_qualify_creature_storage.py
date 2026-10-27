"""Independent qualification rejects damaged proposals even with fresh hashes."""

import json

import numpy as np
import pytest

from pack_creature_storage import prepare
from qualify_creature_storage import exact_source
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


@pytest.mark.parametrize("damage", ["geometry", "normal", "curve", "clock"])
def test_modified_retained_bits_rejected_even_with_updated_hash(tmp_path, damage):
    job = job_fixture(tmp_path)
    document, binary = read_glb(job["candidate"])
    binary = bytearray(binary)
    primitive = document["meshes"][0]["primitives"][0]
    if damage in ("geometry", "normal"):
        key = "POSITION" if damage == "geometry" else "NORMAL"
        primitive["attributes"][key] = append_array(
            document, binary, np.ones((3, 3)), "VEC3"
        )
    else:
        sampler = document["animations"][0]["samplers"][0]
        if damage == "clock":
            sampler["input"] = append_array(
                document, binary, np.array([[0], [0.251], [1]]), "SCALAR"
            )
        else:
            sampler["output"] = append_array(
                document, binary, np.array([[0.1], [0.7], [-0.2]]), "SCALAR"
            )
    write_glb(job["candidate"], document, binary)
    receipt = json.loads(open(job["preparation"]).read())
    receipt["candidate_sha256"] = digest(job["candidate"])
    with open(job["preparation"], "w") as handle:
        json.dump(receipt, handle)
    with pytest.raises(AssertionError):
        exact_source(job)
