"""Create measured, approximate animation drafts; never install or approve them.

Only dense LINEAR animation samplers are resampled. Sparse clocks and variable
STEP clocks retain their bytes; dense bit-constant STEP uses endpoints.
Unknown extensions and cubic interpolation
fail explicitly. Geometry, both skin influence sets, defaults, clip metadata,
materials and embedded images are verified independently after lossless packing.

The numerical report uses the project's float64 native glTF evaluator, all mesh
vertices, shifted/off-grid times, reset/defaults and deterministic crossfades.
It is an error measurement, not a Godot playback, contact or visual acceptance.
"""
from __future__ import annotations

import os

os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

# Also importable by absolute file path, independent of the working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_storage import _array
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array, compact

SCHEMA = 1
_MATERIAL_EXTENSIONS = {
    "KHR_materials_unlit", "KHR_materials_specular", "KHR_materials_ior",
    "KHR_materials_transmission", "KHR_materials_clearcoat",
    "KHR_texture_transform", "KHR_materials_emissive_strength",
}
_PATH_TYPES = {"translation": "VEC3", "rotation": "VEC4", "scale": "VEC3", "weights": "SCALAR"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _tool_fingerprint():
    paths = [Path(__file__), *(Path(__file__).parent / "video_motion" / name
        for name in ("asset.py", "creature_storage.py", "native_shapes.py", "packing.py"))]
    h = hashlib.sha256()
    for path in paths:
        h.update(path.name.encode())
        h.update(path.read_bytes())
    # Numerical dependencies participate in resume validity too.
    import scipy
    h.update((np.__version__ + scipy.__version__).encode())
    return h.hexdigest()


def _cadence(times, fps):
    delta = np.diff(times.astype(float))
    if not len(delta):
        return {"keys": len(times), "maximum_interval_hz": 0.0, "average_hz": 0.0,
                "within_rate_at_float32_precision": True}
    # A nominal 30 Hz float32 clock can have intervals a few timestamp ULPs
    # shorter than 1/30. Keep it verbatim rather than needlessly sampling it.
    allowance = np.abs(np.spacing(times.astype(np.float32))).astype(float)
    within = np.all(delta + allowance[:-1] + allowance[1:] >= 1.0 / fps)
    return {"keys": len(times), "maximum_interval_hz": float(1.0 / delta.min()),
            "average_hz": float(len(delta) / (times[-1] - times[0])),
            "within_rate_at_float32_precision": bool(within)}


def uniform_clock(start, end, fps):
    """Endpoint-distributed float32 clock, bounded by fps after quantization.

    A span shorter than one frame has two mandatory endpoints. That explicit
    exception is reported, as are retained dense STEP discontinuities.
    """
    _require(math.isfinite(fps) and fps > 0 and end >= start, "Invalid clock/rate")
    if end == start:
        return np.array([start], dtype="<f4")
    intervals = max(1, math.floor((end - start) * fps))
    while True:
        clock = np.linspace(start, end, intervals + 1, dtype="<f4")
        if intervals == 1 or np.all(np.diff(clock.astype(float)) >= 1.0 / fps):
            _require(np.all(np.diff(clock.astype(float)) > 0), "Float32 clock collapsed")
            return clock
        intervals -= 1


def resample(times, values, query, rotation=False):
    """Evaluate LINEAR glTF semantics (shortest-path quaternion SLERP)."""
    if len(times) == 1:
        return np.repeat(values[:1], len(query), axis=0)
    if rotation:
        return Slerp(times, Rotation.from_quat(values))(query).as_quat()
    right = np.clip(np.searchsorted(times, query, side="right"), 1, len(times) - 1)
    left = right - 1
    alpha = ((query - times[left]) / (times[right] - times[left]))[:, None]
    return values[left] * (1 - alpha) + values[right] * alpha


def _extensions(value, *, material=False):
    if isinstance(value, dict):
        names = set(value.get("extensions", {}))
        _require(not names or (material and names <= _MATERIAL_EXTENSIONS),
                 "Unsupported extension context: " + ", ".join(sorted(names)))
        for key, child in value.items():
            # Extras are opaque user metadata, not glTF extension containers.
            if key != "extras":
                _extensions(child, material=material)
    elif isinstance(value, list):
        for child in value:
            _extensions(child, material=material)


def _preflight(d, b):
    _require(d.get("asset", {}).get("version") == "2.0", "Requires glTF 2.0")
    _require(not (set(d.get("extensionsUsed", [])) | set(d.get("extensionsRequired", [])))
             - _MATERIAL_EXTENSIONS, "Unsupported declared extension")
    for key, value in d.items():
        if key != "extras":
            _extensions(value, material=key == "materials")
    _require(not d.get("extensions"), "Unsupported root extension")
    for view in d.get("bufferViews", []):
        _require(view.get("buffer", 0) == 0 and view.get("byteOffset", 0) >= 0
                 and view.get("byteLength", -1) >= 0
                 and view.get("byteOffset", 0) + view["byteLength"] <= len(b),
                 "Invalid buffer view range")
    for index in range(len(d.get("accessors", []))):
        _array(d, b, index)  # Includes range/stride and sparse rejection.
    _require(all("bufferView" in image and "uri" not in image for image in d.get("images", [])),
             "Requires embedded images")
    _require(isinstance(d.get("asset", {}).get("extras", {}), dict), "asset.extras must be an object")
    animations = d.get("animations", [])
    names = [a.get("name") for a in animations]
    _require(animations and all(isinstance(n, str) and n for n in names)
             and len(set(names)) == len(names), "Requires unique named clips")
    for node in d.get("nodes", []):
        _require(not ("matrix" in node and any(k in node for k in ("translation", "rotation", "scale"))),
                 "Node mixes matrix and TRS")
    for skin in d.get("skins", []):
        _require("inverseBindMatrices" in skin, "Implicit inverse binds unsupported by native evaluator")
    for animation in animations:
        _require(animation.get("channels") and animation.get("samplers"), "Empty animation")
        used = set()
        for channel in animation["channels"]:
            node = channel.get("target", {}).get("node")
            kind = channel.get("target", {}).get("path")
            _require(isinstance(node, int) and not isinstance(node, bool) and 0 <= node < len(d["nodes"])
                     and kind in _PATH_TYPES, "Unsupported animation target")
            _require(kind == "weights" or "matrix" not in d["nodes"][node],
                     "Animated matrix/TRS ambiguity requires separate diagnosis")
            si = channel["sampler"]
            _require(isinstance(si, int) and 0 <= si < len(animation["samplers"]), "Invalid sampler")
            used.add(si)
        _require(used == set(range(len(animation["samplers"]))), "Unreferenced animation sampler")
        for si, sampler in enumerate(animation["samplers"]):
            mode = sampler.get("interpolation", "LINEAR")
            _require(mode in ("LINEAR", "STEP"), f"Unsupported interpolation: {mode}")
            kinds = {c["target"]["path"] for c in animation["channels"] if c["sampler"] == si}
            _require(len(kinds) == 1, "Shared sampler uses incompatible target paths")
            kind = next(iter(kinds))
            inp, out = (d["accessors"][sampler[k]] for k in ("input", "output"))
            _require(inp["type"] == "SCALAR" and inp["componentType"] == 5126 and not inp.get("normalized")
                     and out["type"] == _PATH_TYPES[kind] and out["componentType"] == 5126
                     and not out.get("normalized"), "Unsupported animation accessor encoding")
            ts = accessor(d, b, sampler["input"]).ravel()
            values = accessor(d, b, sampler["output"])
            _require(len(ts) > 0 and np.isfinite(ts).all() and ts[0] >= 0
                     and np.all(np.diff(ts) > 0), "Clock must be finite, nonnegative and strictly increasing")
            _require(np.isfinite(values).all(), "Nonfinite animation values")
            if kind == "weights":
                counts = []
                for c in animation["channels"]:
                    if c["sampler"] != si:
                        continue
                    node = d["nodes"][c["target"]["node"]]
                    _require("mesh" in node, "Weights target has no mesh")
                    counts.extend(len(p.get("targets", [])) for p in d["meshes"][node["mesh"]]["primitives"])
                _require(len(set(counts)) == 1 and counts[0] > 0
                         and len(values) == len(ts) * counts[0], "Morph sampler width mismatch")
            else:
                _require(len(values) == len(ts), "Animation sampler length mismatch")
                if kind == "rotation":
                    _require(np.all(np.linalg.norm(values, axis=1) > 1e-12), "Zero quaternion")


def _append_like(d, blob, values, original):
    index = append_array(d, blob, values, original["type"])
    spec = d["accessors"][index]
    for key, value in original.items():
        if key not in ("bufferView", "byteOffset", "count", "min", "max"):
            spec[key] = copy.deepcopy(value)
    return index


def verify_static(a, ab, b, bb, fps):
    """Independent bit-level static proof; excludes only sampled curve payloads."""
    expected_asset = copy.deepcopy(a["asset"])
    expected_asset.setdefault("extras", {})["rabbitlands_animation_bake_fps"] = fps
    _require(expected_asset == b["asset"], "Asset metadata changed beyond bake FPS")
    count = [0]

    def canonical(d, binary):
        result = copy.deepcopy(d)
        cache = {}

        def signature(index):
            if index not in cache:
                spec = copy.deepcopy(d["accessors"][index])
                spec.pop("bufferView", None)
                spec.pop("byteOffset", None)
                cache[index] = {"metadata": spec, "bits": hashlib.sha256(_array(d, binary, index).tobytes()).hexdigest()}
                count[0] += 1
            return cache[index]

        result["asset"] = expected_asset
        for mesh in result.get("meshes", []):
            for primitive in mesh["primitives"]:
                primitive["attributes"] = {k: signature(v) for k, v in primitive["attributes"].items()}
                if "indices" in primitive:
                    primitive["indices"] = signature(primitive["indices"])
                for target in primitive.get("targets", []):
                    for key, value in target.items():
                        target[key] = signature(value)
        for skin in result.get("skins", []):
            if "inverseBindMatrices" in skin:
                skin["inverseBindMatrices"] = signature(skin["inverseBindMatrices"])
        for image in result.get("images", []):
            view = d["bufferViews"][image.pop("bufferView")]
            start = view.get("byteOffset", 0)
            image["embedded_payload"] = {
                "view": {k: v for k, v in view.items() if k not in ("buffer", "byteOffset")},
                "sha256": hashlib.sha256(binary[start:start + view["byteLength"]]).hexdigest()}
        for animation in result["animations"]:
            for sampler in animation["samplers"]:
                sampler["input"] = "sampled_clock"
                sampler["output"] = "sampled_values"
        for key in ("accessors", "bufferViews"):
            result.pop(key, None)
        for buffer in result["buffers"]:
            buffer.pop("byteLength", None)
        return result

    _require(canonical(a, ab) == canonical(b, bb), "Static payload or clip/channel metadata changed")
    for old, new in zip(a["animations"], b["animations"], strict=True):
        for sa, sb in zip(old["samplers"], new["samplers"], strict=True):
            for field in ("input", "output"):
                ignored = {"bufferView", "byteOffset", "count", "min", "max"}
                _require({k: v for k, v in a["accessors"][sa[field]].items() if k not in ignored}
                         == {k: v for k, v in b["accessors"][sb[field]].items() if k not in ignored},
                         "Animation accessor metadata changed")
            ta = _array(a, ab, sa["input"])
            tb = _array(b, bb, sb["input"])
            va = _array(a, ab, sa["output"]).reshape(len(ta), -1)
            vb = _array(b, bb, sb["output"]).reshape(len(tb), -1)
            _require(ta[[0, -1]].tobytes() == tb[[0, -1]].tobytes()
                     and va[[0, -1]].tobytes() == vb[[0, -1]].tobytes(), "Endpoint bits changed")
            constant_step = (sa.get("interpolation", "LINEAR") == "STEP" and len(ta) > 2
                             and not _cadence(ta.ravel(), fps)["within_rate_at_float32_precision"]
                             and all(row.tobytes() == va[0].tobytes() for row in va))
            if constant_step:
                _require(len(tb) == 2, "Bit-constant dense STEP was not reduced to endpoints")
            elif sa.get("interpolation", "LINEAR") == "STEP" or _cadence(ta.ravel(), fps)["within_rate_at_float32_precision"]:
                _require(ta.tobytes() == tb.tobytes() and va.tobytes() == vb.tobytes(),
                         "Sparse or STEP sampler changed")
    return {"static_accessor_signatures_checked": count[0], "preserved": [
        "geometry/topology/UVs/normals/tangents/colors", "all morph POSITION/NORMAL/TANGENT fields",
        "all skin influence sets and inverse binds", "node hierarchy/rest/defaults",
        "materials/texture metadata/embedded image bytes", "clip order/names/metadata/channel order",
        "all sampler endpoint bits", "sparse and variable STEP bits; dense bit-constant STEP endpoints"],
        "event_metadata": "Preserved verbatim; no universal event-knot schema assumed"}


def _field_sampler(asset):
    """Cache flat corrective fields once, never rebuild the full target cube per pose."""
    fields = []
    primitives = [p for node in asset.d["nodes"] if "mesh" in node
                  for p in asset.d["meshes"][node["mesh"]]["primitives"]]
    for part, primitive in zip(asset.parts, primitives, strict=True):
        normal = (accessor(asset.d, asset.b, primitive["attributes"]["NORMAL"])
                  if "NORMAL" in primitive["attributes"] else None)
        targets = None
        if normal is not None and primitive.get("targets"):
            targets = np.array([accessor(asset.d, asset.b, t["NORMAL"]) if "NORMAL" in t
                                else np.zeros_like(normal) for t in primitive["targets"]])
            targets = targets.reshape(len(targets), -1)
        fields.append((part, normal, targets))

    def evaluate(world, morph):
        positions, normals = [], []
        for part, base_normal, normal_targets in fields:
            pos = part["position"].copy()
            normal = None if base_normal is None else base_normal.copy()
            weights = morph.get(part["node"], asset.default_weights[part["node"]])
            active = np.flatnonzero(weights)
            if len(part["targets"]) and len(active):
                targets = part["targets"].reshape(len(weights), -1)
                pos[:, :3] += (weights @ targets if len(active) == len(weights)
                              else weights[active] @ targets[active]).reshape(-1, 3)
            if normal_targets is not None and len(active):
                normal += (weights @ normal_targets if len(active) == len(weights)
                           else weights[active] @ normal_targets[active]).reshape(-1, 3)
            if "joints" not in part:
                out = (world[part["node"]] @ pos.T).T[:, :3]
                out_normal = None if normal is None else normal @ world[part["node"], :3, :3].T
            else:
                transforms = world[part["nodes"]] @ part["bind"]
                out = np.zeros((len(pos), 3))
                out_normal = None if normal is None else np.zeros_like(normal)
                for slot in range(part["joints"].shape[1]):
                    weight = part["weights"][:, slot, None]
                    matrices = transforms[part["joints"][:, slot]]
                    out += np.einsum("vab,vb->va", matrices[:, :3], pos) * weight
                    if normal is not None:
                        out_normal += np.einsum("vab,vb->va", matrices[:, :3, :3], normal) * weight
            positions.append(out)
            if out_normal is not None:
                lengths = np.linalg.norm(out_normal, axis=1)
                _require(np.all(lengths > 1e-20), "Degenerate evaluated normals")
                normals.append(out_normal / lengths[:, None])
        return np.concatenate(positions), np.concatenate(normals) if normals else np.empty((0, 3))

    return evaluate


def _angles(a, b):
    if not len(a):
        return 0.0
    return float(np.rad2deg(np.arctan2(np.linalg.norm(np.cross(a, b), axis=-1),
                                      np.sum(a * b, axis=-1))).max())


def _metrics(pa, pb, na, nb, wa, wb):
    distance = np.linalg.norm(pa - pb, axis=1)
    aa = wa[:, :3, :3].transpose(0, 2, 1).reshape(-1, 3)
    ba = wb[:, :3, :3].transpose(0, 2, 1).reshape(-1, 3)
    la, lb = np.linalg.norm(aa, axis=1), np.linalg.norm(ba, axis=1)
    keep = (la > 1e-20) & (lb > 1e-20)
    return {"max_surface_distance": float(distance.max()), "rms_surface_distance": float(np.sqrt(np.mean(distance ** 2))),
            "max_normal_angle_degrees": _angles(na, nb),
            "max_node_world_matrix_element_error": float(np.abs(wa - wb).max()),
            "max_node_origin_distance": float(np.linalg.norm(wa[:, :3, 3] - wb[:, :3, 3], axis=1).max()),
            "max_node_basis_axis_angle_degrees": _angles(aa[keep] / la[keep, None], ba[keep] / lb[keep, None])}


def _maximum(records):
    return {key: max(r[key] for r in records) for key in records[0]}


def _independent_times(asset, clip):
    duration = asset.duration(clip)
    times = [0.0, duration, *(((np.arange(31) + .3819660112501051) / 31) * duration),
             *(np.array([.019137, .113377, .293819, .531197, .763477, .951317]) * duration)]
    step = []
    for sampler in asset.animations[clip]["samplers"]:
        if sampler.get("interpolation", "LINEAR") == "STEP":
            step.extend(accessor(asset.d, asset.b, sampler["input"]).ravel())
    step = np.unique(step)
    # Full STEP storage is bit-proved separately; bounded event-neighborhood
    # sampling keeps dense discontinuous sources practical to audit.
    if len(step) > 16:
        step = step[np.linspace(0, len(step) - 1, 16, dtype=int)]
    for t in step:
        times.extend([float(t), max(0.0, float(np.nextafter(float(t), -np.inf)))])
    return np.unique(times)


def _blend(a, b, alpha):
    ta, qa, sa, ma = a
    tb, qb, sb, mb = b
    qa = qa / np.linalg.norm(qa, axis=1)[:, None]
    qb = qb / np.linalg.norm(qb, axis=1)[:, None]
    dot = np.sum(qa * qb, axis=1)
    qb = qb * np.where(dot < 0, -1.0, 1.0)[:, None]
    theta = np.arccos(np.clip(np.abs(dot), 0, 1))
    sine = np.sin(theta)
    c0 = np.full(len(qa), 1 - alpha)
    c1 = np.full(len(qa), alpha)
    take = sine > 1e-8
    c0[take] = np.sin((1 - alpha) * theta[take]) / sine[take]
    c1[take] = np.sin(alpha * theta[take]) / sine[take]
    return (ta * (1 - alpha) + tb * alpha, qa * c0[:, None] + qb * c1[:, None],
            sa * (1 - alpha) + sb * alpha,
            {node: ma[node] * (1 - alpha) + mb[node] * alpha for node in ma})


def measure_native(source, candidate):
    a, b = NativeShapeAsset(source), NativeShapeAsset(candidate)
    fa, fb = _field_sampler(a), _field_sampler(b)
    extent = float(np.ptp(a.vertices, axis=0).max())
    clips, all_metrics, states = {}, [], {}

    def compare(x, y):
        wa, wb = a.world(*x[:3]), b.world(*y[:3])
        pa, na = fa(wa, x[3])
        pb, nb = fb(wb, y[3])
        record = _metrics(pa, pb, na, nb, wa, wb)
        _require(all(math.isfinite(v) for v in record.values()), "Nonfinite native measurement")
        all_metrics.append(record)
        return record

    default = compare((a.t, a.q, a.s, a.default_weights), (b.t, b.q, b.s, b.default_weights))
    for clip in a.animations:
        times = _independent_times(a, clip)
        blend_times = np.array([a.duration(clip) * .137, a.duration(clip) * .731])
        query = np.r_[times, blend_times]
        av, bv = a.sample(clip, query), b.sample(clip, query)

        def state(v, index):
            return (*[v[k][index] for k in range(3)], {n: w[index] for n, w in v[3].items()})

        records = [compare(state(av, k), state(bv, k)) for k in range(len(times))]
        states[clip] = [(state(av, -2), state(bv, -2)), (state(av, -1), state(bv, -1))]
        clips[clip] = {"times_seconds": times.tolist(), "poses": len(times), **_maximum(records)}
    blends = []
    names = list(a.animations)
    for previous, following in zip(names, names[1:] + names[:1]):
        metrics = []
        for alpha in (.2, .5, .8):
            metrics.append(compare(_blend(states[previous][1][0], states[following][0][0], alpha),
                                   _blend(states[previous][1][1], states[following][0][1], alpha)))
        blends.append({"from": previous, "to": following, "from_fraction": .731, "to_fraction": .137,
                       "alphas": [.2, .5, .8], **_maximum(metrics)})
    maxima = _maximum(all_metrics)
    return {"evaluator": "float64 NativeShapeAsset plus cached POSITION/NORMAL fields; not an engine import",
            "acceptance_threshold_applied": False, "all_surface_vertices": len(a.vertices),
            "normal_vertices": sum(len(p["position"]) for p, pr in zip(a.parts,
                [p for n in a.d["nodes"] if "mesh" in n for p in a.d["meshes"][n["mesh"]]["primitives"]])
                if "NORMAL" in pr["attributes"]),
            "all_node_transforms": a.n, "skin_joint_nodes": len(a.joints),
            "source_rest_max_axis_extent": extent, "clips": clips, "crossfades": blends,
            "default_reset": {"method": "Stateless authored defaults, including omitted channels; no engine state claim",
                              **default},
            "maximum": {**maxima, "max_surface_distance_over_rest_extent":
                        maxima["max_surface_distance"] / extent if extent > 0 else None},
            "limitations": "Finite independent samples do not bound continuous worst-case error. No contact-field, GPU, gameplay FPS, visual or artistic approval is inferred."}


def sample(source: Path, output: Path, *, fps=30, expected_sha256=None, report: Path = None) -> dict:
    """Write an offline draft and hash-bound measurements, leaving source untouched.

    A matching report resumes only when source/output/tool/dependency hashes and
    settings match. Reports carry errors, never a generic quality pass/fail.
    """
    started = time.perf_counter()
    source, output = Path(source).resolve(), Path(output).resolve()
    report = None if report is None else Path(report).resolve()
    _require(source != output and (not output.exists() or not source.samefile(output)), "Source and output must differ")
    _require(report is None or report not in (source, output), "Report must be separate from GLBs")
    _require(not isinstance(fps, bool) and math.isfinite(fps) and fps > 0, "FPS must be positive and finite")
    fps = int(fps) if float(fps).is_integer() else float(fps)
    source_hash = digest(source)
    _require(expected_sha256 is None or source_hash == expected_sha256, "Source SHA-256 mismatch")
    tool_hash = _tool_fingerprint()
    if report is not None and report.exists() and output.exists():
        try:
            prior = json.loads(report.read_text(encoding="utf-8"))
            if (prior.get("schema") == SCHEMA and prior.get("source_sha256") == source_hash
                    and prior.get("candidate_sha256") == digest(output) and prior.get("fps") == fps
                    and prior.get("tool_sha256") == tool_hash and prior.get("candidate_path") == str(output)
                    and prior.get("source_path") == str(source)
                    and prior.get("status") == "approximate_draft_not_installed_or_approved"):
                return {**prior, "resumed": True}
        except (ValueError, OSError):
            pass
    original, binary = read_glb(source)
    _preflight(original, binary)
    document, blob = copy.deepcopy(original), bytearray(binary)
    clips = []
    for before, animation in zip(original["animations"], document["animations"], strict=True):
        rows = []
        for si, sampler in enumerate(animation["samplers"]):
            old = before["samplers"][si]
            kind = next(c["target"]["path"] for c in animation["channels"] if c["sampler"] == si)
            ts = accessor(original, binary, old["input"]).ravel()
            values = accessor(original, binary, old["output"]).reshape(len(ts), -1)
            cadence = _cadence(ts, fps)
            mode = old.get("interpolation", "LINEAR")
            if (mode == "STEP" and not cadence["within_rate_at_float32_precision"]
                    and len(ts) > 2 and all(row.tobytes() == values[0].tobytes() for row in values)):
                query = ts[[0, -1]]
                value = values[[0, -1]]
                sampler["input"] = _append_like(document, blob, query[:, None], original["accessors"][old["input"]])
                sampler["output"] = _append_like(document, blob, value.reshape(-1, 1) if kind == "weights" else value,
                                                original["accessors"][old["output"]])
                method = "collapse_exact_constant_STEP"
            elif mode == "STEP" or cadence["within_rate_at_float32_precision"]:
                query = ts
                method = "retain_STEP_bits" if mode == "STEP" else "retain_sparse_bits"
            else:
                query = uniform_clock(float(ts[0]), float(ts[-1]), fps)
                value = resample(ts, values, query, kind == "rotation")
                value[0], value[-1] = values[0], values[-1]
                sampler["input"] = _append_like(document, blob, query[:, None], original["accessors"][old["input"]])
                sampler["output"] = _append_like(document, blob, value.reshape(-1, 1) if kind == "weights" else value,
                                                original["accessors"][old["output"]])
                method = "LINEAR_quaternion_SLERP" if kind == "rotation" else "LINEAR_vector"
            after = _cadence(query, fps)
            exception = ("original_STEP_discontinuities_retained" if mode == "STEP" and not after["within_rate_at_float32_precision"]
                         else "mandatory_endpoints_span_less_than_one_frame" if not after["within_rate_at_float32_precision"] else None)
            rows.append({"sampler": si, "path": kind, "interpolation": mode, "method": method,
                         "source": cadence, "candidate": after, "cadence_exception": exception})
        clips.append({"name": animation["name"], "duration_seconds": max(float(accessor(original, binary, s["input"])[-1, 0])
                      for s in before["samplers"]), "samplers": rows,
                      "maximum_continuous_linear_interval_hz": max((r["candidate"]["maximum_interval_hz"] for r in rows
                                                                  if r["interpolation"] == "LINEAR"), default=0.0),
                      "maximum_all_sampler_interval_hz": max(r["candidate"]["maximum_interval_hz"] for r in rows),
                      "source_sampler_keys": sum(r["source"]["keys"] for r in rows),
                      "candidate_sampler_keys": sum(r["candidate"]["keys"] for r in rows)})
    document["asset"].setdefault("extras", {})["rabbitlands_animation_bake_fps"] = fps
    # Only reachable storage removal and byte-identical view deduplication. In
    # particular, sparse clocks must not be changed by constant-track collapse.
    document, blob, packing = compact(document, blob, collapse_paths=())
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.stem + "-", suffix=".glb", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_glb(temporary, document, blob)
        candidate, cb = read_glb(temporary)
        _preflight(candidate, cb)
        structural = verify_static(original, binary, candidate, cb, fps)
        build_seconds = time.perf_counter() - started
        native = measure_native(source, temporary)
        _require(digest(source) == source_hash, "Source changed during sampling")
        result = {"schema": SCHEMA, "status": "approximate_draft_not_installed_or_approved",
                  "source_path": str(source), "candidate_path": str(output), "source_sha256": source_hash,
                  "candidate_sha256": digest(temporary), "source_bytes": source.stat().st_size,
                  "candidate_bytes": temporary.stat().st_size, "fps": fps, "tool_sha256": tool_hash,
                  "source_sampler_keys": sum(c["source_sampler_keys"] for c in clips),
                  "candidate_sampler_keys": sum(c["candidate_sampler_keys"] for c in clips),
                  "maximum_continuous_linear_interval_hz": max(c["maximum_continuous_linear_interval_hz"] for c in clips),
                  "maximum_all_sampler_interval_hz": max(c["maximum_all_sampler_interval_hz"] for c in clips),
                  "cadence_exceptions": [{"clip": c["name"], "sampler": s["sampler"], "path": s["path"],
                                          "reason": s["cadence_exception"]} for c in clips for s in c["samplers"]
                                         if s["cadence_exception"]],
                  "clips": clips, "structural_proof": structural, "native_measurements": native, "packing": packing,
                  "timing_seconds": {"build_and_static_proof": build_seconds,
                                     "native_measurements": time.perf_counter() - started - build_seconds,
                                     "total": time.perf_counter() - started},
                  "scope": "Offline raw GLB draft. Source and external action/event mappings untouched. No installation, engine playback, runtime RAM/CPU/FPS or artistic acceptance claim.",
                  "resumed": False}
        temporary.replace(output)
        if report is not None:
            report.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=report.stem + "-", suffix=".json",
                                             dir=report.parent, delete=False) as handle:
                report_temp = Path(handle.name)
                json.dump(result, handle, indent=2, allow_nan=False)
                handle.write("\n")
            report_temp.replace(report)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=30)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = sample(args.source, args.output, fps=args.fps, expected_sha256=args.expected_sha256, report=args.report)
    print(json.dumps({k: result[k] for k in ("status", "source_sha256", "candidate_sha256", "source_bytes",
                                           "candidate_bytes", "source_sampler_keys", "candidate_sampler_keys", "resumed")}))


if __name__ == "__main__":
    main()
