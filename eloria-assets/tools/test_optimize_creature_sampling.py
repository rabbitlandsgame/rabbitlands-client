"""Sampling semantics, immutable static fields, failures and resumable evidence."""
import copy

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from optimize_creature_sampling import sample, uniform_clock, resample, verify_static
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_storage import _array
from video_motion.packing import append_array


def fixture(tmp_path, fps=120):
    d = {"asset": {"version": "2.0", "extras": {"rabbitlands_animation_bake_fps": fps, "human_approved": False}},
         "buffers": [{"byteLength": 0}], "bufferViews": [], "accessors": [], "scene": 0,
         "scenes": [{"nodes": [0]}], "nodes": [
             {"name": "Root", "children": [1, 2, 3]},
             {"name": "Tip", "translation": [0, .5, 0]},
             {"name": "Body", "mesh": 0, "skin": 0, "weights": [.1]},
             {"name": "UnskinnedProp", "mesh": 0, "translation": [.3, 0, 0]}],
         "materials": [{"name": "Original", "extras": {"review": "pending"}}], "animations": []}
    b = bytearray()
    position = append_array(d, b, [[-.2, 0, 0], [.2, 0, 0], [.2, 1, 0], [-.2, 1, 0]], "VEC3")
    normal = append_array(d, b, [[0, 0, 1]] * 4, "VEC3")
    uv = append_array(d, b, [[0, 0], [1, 0], [1, 1], [0, 1]], "VEC2")
    joints0 = append_array(d, b, [[0, 1, 0, 1]] * 4, "VEC4")
    joints1 = append_array(d, b, [[1, 0, 0, 0]] * 4, "VEC4")
    # Test both influence sets including repeated positive slots.
    weights0 = append_array(d, b, [[.2, .3, .1, .1]] * 4, "VEC4")
    weights1 = append_array(d, b, [[.2, .1, 0, 0]] * 4, "VEC4")
    mp = append_array(d, b, [[.01, 0, .02], [0, 0, .01], [0, .02, .03], [0, .01, .01]], "VEC3")
    mn = append_array(d, b, [[.02, .01, 0]] * 4, "VEC3")
    mt = append_array(d, b, [[0, .01, 0]] * 4, "VEC3")
    d["meshes"] = [{"name": "FrozenMesh", "extras": {"targetNames": ["Corrective"], "original": 7},
        "weights": [.15], "primitives": [{"attributes": {"POSITION": position, "NORMAL": normal, "TEXCOORD_0": uv,
        "JOINTS_0": joints0, "WEIGHTS_0": weights0, "JOINTS_1": joints1, "WEIGHTS_1": weights1},
        "targets": [{"POSITION": mp, "NORMAL": mn, "TANGENT": mt}], "material": 0}]}]
    binds = np.tile(np.eye(4), (2, 1, 1))
    binds[1, 1, 3] = -.5
    ibm = append_array(d, b, binds.transpose(0, 2, 1).reshape(2, 16), "MAT4")
    d["skins"] = [{"joints": [0, 1], "inverseBindMatrices": ibm, "name": "OriginalSkin"}]
    b.extend(b"\0" * (-len(b) % 4))
    d["bufferViews"].append({"buffer": 0, "byteOffset": len(b), "byteLength": 12})
    b.extend(b"image-bytes!")
    d["images"] = [{"name": "OriginalImage", "mimeType": "image/png", "bufferView": len(d["bufferViews"]) - 1}]
    for name in ("Walk", "Death_A"):
        times = np.linspace(0, 1, fps + 1, dtype="<f4")
        clock = append_array(d, b, times[:, None], "SCALAR")
        rot = Rotation.from_rotvec(np.c_[times * 0, times * 0, .5 * np.sin(times * 5)]).as_quat()
        rotation = append_array(d, b, rot, "VEC4")
        shape = append_array(d, b, (.3 + .3 * np.sin(times * 9))[:, None], "SCALAR")
        sparse = append_array(d, b, [[0], [1]], "SCALAR")
        trans = append_array(d, b, [[0., -0., 0.], [.01, 0., 0.]], "VEC3")
        step = append_array(d, b, [[0], [.017], [1]], "SCALAR")
        scale = append_array(d, b, [[1, 1, 1], [1.01, 1.01, 1.01], [1, 1, 1]], "VEC3")
        d["animations"].append({"name": name, "extras": {"loop": name == "Walk", "events": {"impact_seconds": .413}},
            "channels": [{"target": {"node": 1, "path": "rotation"}, "sampler": 0},
                         {"target": {"node": 2, "path": "weights"}, "sampler": 1},
                         {"target": {"node": 0, "path": "translation"}, "sampler": 2},
                         {"target": {"node": 0, "path": "scale"}, "sampler": 3}],
            "samplers": [{"input": clock, "output": rotation, "extras": {"keep": 1}},
                         {"input": clock, "output": shape}, {"input": sparse, "output": trans},
                         {"input": step, "output": scale, "interpolation": "STEP"}]})
    source = tmp_path / "source.glb"
    write_glb(source, d, b)
    return source


@pytest.mark.parametrize("start,end", [(0, 1), (0, 1.03), (.123, 2.718), (0, 30), (0, .01), (0, 0)])
def test_endpoint_distributed_clock_is_bounded_after_float32(start, end):
    start, end = float(np.float32(start)), float(np.float32(end))
    clock = uniform_clock(start, end, 30)
    assert clock[0] == start and clock[-1] == end
    if len(clock) > 1:
        assert np.all(np.diff(clock) > 0)
        if end - start >= 1 / 30:
            assert np.all(np.diff(clock.astype(float)) >= 1 / 30)
    # No appended tiny remainder at the end.
    if len(clock) > 2:
        assert np.ptp(np.diff(clock.astype(float))) < 2 * float(np.spacing(np.float32(max(1, end))))


def test_quaternion_interpolation_is_shortest_path_slerp_not_nlerp():
    q = Rotation.from_rotvec(np.deg2rad([[0, 0, 0], [0, 0, 200]])).as_quat()
    actual = resample(np.array([0., 1.]), q, np.array([.25]), rotation=True)
    expected = Rotation.from_rotvec(np.deg2rad([0, 0, -40]))
    assert (Rotation.from_quat(actual[0]).inv() * expected).magnitude() < 1e-12
    nlerp = q[0] * .75 - q[1] * .25
    assert (Rotation.from_quat(nlerp).inv() * expected).magnitude() > .01


def test_candidate_preserves_static_endpoints_step_sparse_and_measures_all_vertices(tmp_path):
    source = fixture(tmp_path)
    old_bytes = source.read_bytes()
    output, report = tmp_path / "draft.glb", tmp_path / "report.json"
    result = sample(source, output, expected_sha256=digest(source), report=report)
    assert source.read_bytes() == old_bytes
    assert result["candidate_sampler_keys"] < result["source_sampler_keys"]
    assert not result["resumed"] and "approximate" in result["status"]
    a, ab = read_glb(source)
    b, bb = read_glb(output)
    verify_static(a, ab, b, bb, 30)
    assert b["asset"]["extras"]["human_approved"] is False
    for aa, ba in zip(a["animations"], b["animations"]):
        assert aa["extras"] == ba["extras"]
        for si in (2, 3):
            for key in ("input", "output"):
                assert _array(a, ab, aa["samplers"][si][key]).tobytes() == _array(b, bb, ba["samplers"][si][key]).tobytes()
    native = result["native_measurements"]
    assert native["all_surface_vertices"] == 8 and native["normal_vertices"] == 8
    assert native["all_node_transforms"] == 4 and native["skin_joint_nodes"] == 2
    assert set(native["clips"]) == {"Walk", "Death_A"}
    assert all(c["poses"] >= 39 for c in native["clips"].values())
    assert native["maximum"]["max_surface_distance"] > 0
    assert native["maximum"]["max_normal_angle_degrees"] > 0
    assert all(v == 0 for k, v in native["default_reset"].items() if k != "method")
    assert len(native["crossfades"]) == 2 and not native["acceptance_threshold_applied"]
    assert result["clips"][0]["samplers"][3]["cadence_exception"] == "original_STEP_discontinuities_retained"
    resumed = sample(source, output, report=report)
    assert resumed["resumed"] and resumed["candidate_sha256"] == digest(output)
    output.write_bytes(output.read_bytes() + b"stale")
    assert not sample(source, output, report=report)["resumed"]


def test_already_30hz_clocks_and_values_are_retained_exactly(tmp_path):
    source = fixture(tmp_path, fps=30)
    output = tmp_path / "draft.glb"
    result = sample(source, output)
    a, ab = read_glb(source)
    b, bb = read_glb(output)
    assert result["source_sampler_keys"] == result["candidate_sampler_keys"]
    for aa, ba in zip(a["animations"], b["animations"]):
        for sa, sb in zip(aa["samplers"], ba["samplers"]):
            for key in ("input", "output"):
                assert _array(a, ab, sa[key]).tobytes() == _array(b, bb, sb[key]).tobytes()
    assert result["native_measurements"]["maximum"]["max_surface_distance"] == 0


def test_dense_bit_constant_step_collapses_but_signed_zero_is_retained(tmp_path):
    source = fixture(tmp_path)
    d, binary = read_glb(source)
    b = bytearray(binary)
    for animation in d["animations"]:
        step = animation["samplers"][3]
        step["input"] = append_array(d, b, np.linspace(0, 1, 121)[:, None], "SCALAR")
        step["output"] = append_array(d, b, np.ones((121, 3)), "VEC3")
    write_glb(source, d, b)
    result = sample(source, tmp_path / "constant.glb")
    assert all(c["samplers"][3]["candidate"]["keys"] == 2 for c in result["clips"])
    assert not result["cadence_exceptions"]
    signed = np.zeros((121, 3), dtype="<f4")
    signed[33, 0] = -0.
    # Translation keeps the default/evaluated scale nonsingular.
    animation = d["animations"][0]
    animation["channels"][3]["target"]["path"] = "translation"
    animation["samplers"][3]["output"] = append_array(d, b, signed, "VEC3")
    write_glb(source, d, b)
    result = sample(source, tmp_path / "signed.glb")
    assert result["clips"][0]["samplers"][3]["candidate"]["keys"] == 121
    assert result["cadence_exceptions"][0]["reason"] == "original_STEP_discontinuities_retained"


@pytest.mark.parametrize("mutation", ["cubic", "extension", "nested_extension", "duplicate_clock", "matrix_animation", "mixed_sampler"])
def test_unsupported_semantics_fail_before_writing(tmp_path, mutation):
    source = fixture(tmp_path)
    d, b = read_glb(source)
    a = d["animations"][0]
    if mutation == "cubic":
        a["samplers"][0]["interpolation"] = "CUBICSPLINE"
    elif mutation == "extension":
        d["extensionsUsed"] = ["KHR_animation_pointer"]
    elif mutation == "nested_extension":
        a["channels"][0]["extensions"] = {"KHR_unknown": {}}
    elif mutation == "duplicate_clock":
        s = a["samplers"][0]
        times = accessor(d, b, s["input"])
        times[1] = times[0]
        b = bytearray(b)
        s["input"] = append_array(d, b, times, "SCALAR")
    elif mutation == "matrix_animation":
        d["nodes"][1].pop("translation")
        d["nodes"][1]["matrix"] = np.eye(4).ravel().tolist()
    else:
        a["channels"][1]["sampler"] = 0
    write_glb(source, d, b)
    with pytest.raises(ValueError):
        sample(source, tmp_path / "bad.glb")
    assert not (tmp_path / "bad.glb").exists()


def test_hash_and_source_alias_guards(tmp_path):
    source = fixture(tmp_path)
    old = source.read_bytes()
    with pytest.raises(ValueError, match="Source and output"):
        sample(source, source)
    with pytest.raises(ValueError, match="SHA-256"):
        sample(source, tmp_path / "bad.glb", expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="Report must"):
        sample(source, tmp_path / "bad.glb", report=source)
    assert source.read_bytes() == old


@pytest.mark.parametrize("mutation", ["mesh_name", "node_default", "skin_bits", "image_bits", "clip_extra", "sampler_extra", "channel_extra"])
def test_independent_static_proof_rejects_mutations(tmp_path, mutation):
    source = fixture(tmp_path)
    candidate = tmp_path / "draft.glb"
    sample(source, candidate)
    a, ab = read_glb(source)
    b, bb = read_glb(candidate)
    b, bb = copy.deepcopy(b), bytearray(bb)
    if mutation == "mesh_name":
        b["meshes"][0]["name"] += "changed"
    elif mutation == "node_default":
        b["nodes"][2]["weights"] = [.2]
    elif mutation == "skin_bits":
        ai = b["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_1"]
        view = b["bufferViews"][b["accessors"][ai]["bufferView"]]
        bb[view["byteOffset"]] ^= 1
    elif mutation == "image_bits":
        view = b["bufferViews"][b["images"][0]["bufferView"]]
        bb[view["byteOffset"]] ^= 1
    elif mutation == "clip_extra":
        b["animations"][0]["extras"]["events"]["impact_seconds"] += .01
    elif mutation == "sampler_extra":
        b["animations"][0]["samplers"][0]["extras"]["keep"] += 1
    else:
        b["animations"][0]["channels"][0]["extras"] = {"changed": True}
    with pytest.raises(ValueError):
        verify_static(a, ab, b, bb, 30)
