"""Measure source/candidate motion through the actual raw-client creature actor.

No universal tolerance or promotion is implied. The output is a numerical
headless reconstruction of native renderer inputs, not a GPU/image test or an
editor PackedScene test. Python requires numpy. A prepared isolated project can
be reused for a series of jobs; call prepare_project again after client changes.

CLI example (paths may be absolute):
  python eloria-assets/tools/check_creature_runtime_client.py --actor ACTOR \
    --source ORIGINAL.glb --candidate PROPOSAL.glb --output .local/client-qa/ACTOR \
    --client-root CLIENT_CHECKOUT --project .local/client-qa/project

API: check(actor, source, candidate, output, *, client_root=None, godot=None,
           project=None, config=None, candidate_vertex_ids=None,
           prepare=True, position_limit_mm=None, normal_limit_degrees=None,
           source_sha256=None, candidate_sha256=None, dto=None).
Explicit candidate_vertex_ids maps each candidate vertex to its source ordinal,
e.g. a proven partition processing report's all_candidate_original_vertex_ids.
Without it, matching native surface identities and unchanged glTF topology are
required. This probe measures motion; it does not prove materials or skin fixes.
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GODOT = Path("C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe")
PROBE = ROOT / "godot-client/tests/probe_creature_runtime_optimization.gd"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def glb(path):
    data = Path(path).read_bytes()
    magic, version, size = struct.unpack_from("<III", data)
    if (magic, version, size) != (0x46546C67, 2, len(data)):
        raise ValueError("Invalid GLB: " + str(path))
    document, binary, offset = None, b"", 12
    while offset < size:
        length, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + length
    if document is None:
        raise ValueError("Missing GLB JSON")
    return document, binary


def topology(document, binary):
    result = []
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            n = document["accessors"][primitive["attributes"]["POSITION"]]["count"]
            if "indices" not in primitive:
                values = np.arange(n, dtype=np.int64)
            else:
                accessor = document["accessors"][primitive["indices"]]
                if "sparse" in accessor:
                    raise ValueError("Sparse topology needs explicit correspondence")
                view = document["bufferViews"][accessor["bufferView"]]
                dtype = {5121: "u1", 5123: "<u2", 5125: "<u4"}[accessor["componentType"]]
                stride = view.get("byteStride", np.dtype(dtype).itemsize)
                values = np.ndarray((accessor["count"],), dtype=dtype, buffer=binary,
                                    offset=view.get("byteOffset", 0) + accessor.get("byteOffset", 0),
                                    strides=(stride,)).astype(np.int64)
            result.append((n, primitive.get("mode", 4), digest_bytes(values.astype("<i8").tobytes())))
    return result


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def prepare_project(project, client_root, godot=GODOT):
    """Copy only client code/data/UI into a dedicated, reusable .local project."""
    project, client_root = Path(project).resolve(), Path(client_root).resolve()
    if ".local" not in project.parts or project == client_root / "godot-client":
        raise ValueError("The isolated project must be under an ignored .local directory")
    project.mkdir(parents=True, exist_ok=True)
    marker = project / "runtime-client-project.json"
    if (project / "project.godot").exists() and not marker.exists():
        raise ValueError("Refusing to overwrite an unrelated project")
    source = client_root / "godot-client"
    for relative in ("src", "data", "addons", "assets/ui"):
        shutil.copytree(source / relative, project / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", ".git", ".godot"))
    (project / "tests").mkdir(exist_ok=True)
    shutil.copy2(PROBE, project / "tests" / PROBE.name)
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="RL isolated creature runtime QA"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
    files = {str(p.relative_to(project)).replace("\\", "/"): digest(p)
             for folder in ("src", "data", "addons") for p in sorted((project / folder).rglob("*")) if p.is_file()}
    write_json(marker, {"client_root": str(client_root), "probe_sha256": digest(PROBE),
                        "client_file_hashes": files,
                        "scope": "Code/data/UI only; no autoloads, enabled plugins, network or player state"})
    run_godot(godot, project, project / "import", ["--editor", "--import"], timeout=300)
    return project


def run_godot(godot, project, log, arguments, timeout=300):
    log = Path(log)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="2", OMP_NUM_THREADS="2")
    for key, sub in (("APPDATA", "roaming"), ("LOCALAPPDATA", "local")):
        env[key] = str(Path(project) / "profile" / sub)
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    with Path(str(log) + ".stdout.log").open("w", encoding="utf-8") as stdout, \
            Path(str(log) + ".stderr.log").open("w", encoding="utf-8") as stderr:
        result = subprocess.run([str(godot), "--headless", "--path", str(project), *arguments],
                                stdout=stdout, stderr=stderr, env=env, timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    combined = Path(str(log) + ".stdout.log").read_text(encoding="utf-8") + Path(str(log) + ".stderr.log").read_text(encoding="utf-8")
    if result.returncode or any(token in combined for token in ("SCRIPT ERROR:", "Parse Error:", "ERROR:", "Assertion failed")):
        raise RuntimeError(f"Godot failed ({result.returncode}); inspect {log}.*.log")


def matrices(rows):
    rows = np.asarray(rows, dtype=np.float64)
    result = np.broadcast_to(np.eye(4), (*rows.shape[:-1], 4, 4)).copy()
    result[..., :3, :] = rows.reshape(*rows.shape[:-1], 3, 4)
    return result


def unit(values):
    lengths = np.linalg.norm(values, axis=-1, keepdims=True)
    if np.any(lengths <= 1e-30):
        raise ValueError("Zero-length normal has no defined direction")
    return values / lengths


def read_groups(description):
    result = []
    for meta in description["meshes"]:
        prefix, n, k = meta["prefix"], meta["vertices"], meta["targets"]
        def read(suffix, dtype="<f4"):
            return np.fromfile(prefix + suffix, dtype)
        base = read("-positions.f32").reshape(n, 3).astype(float)
        normal = unit(read("-normals.f32").reshape(n, 3).astype(float))
        sp = read("-shape-positions.f32").reshape(k, n, 3).astype(float)
        sn = read("-shape-normals.f32").reshape(k, n, 3).astype(float)
        if meta["mode"] == 0:  # Godot normalized mode stores absolute endpoints.
            sp -= base
            if k:
                sn = unit(sn) - normal
        joints, weights = read("-joints.i32", "<i4"), read("-weights.f32")
        if len(joints):
            slots = len(joints) // n
            if slots not in (4, 8):
                raise ValueError("Unsupported influence width")
            packed = read("-skin.bin", "<u2")
            if len(packed) != n * slots * 2:
                raise ValueError("Unexpected native packed skin layout")
            packed = packed.reshape(n, slots * 2)
            joints = joints.reshape(n, slots)
            if not np.array_equal(joints, packed[:, :slots]):
                raise ValueError("Native skin joint layout differs from surface arrays")
            # Use actual GPU u16 weights, without inventing sum renormalization.
            weights = packed[:, slots:].astype(float) / 65535.0
            if np.max(abs(weights - read("-weights.f32").reshape(n, slots))) > 2 / 65535:
                raise ValueError("Native skin weight layout differs from surface arrays")
            if np.max(joints) >= len(meta["bones"]):
                raise ValueError("Skin joint exceeds palette")
        else:
            joints = np.empty((n, 0), int)
            weights = np.empty((n, 0), float)
        result.append(dict(meta=meta, base=base, normal=normal, sp=sp.reshape(k, n * 3),
                           sn=sn.reshape(k, n * 3), joints=joints, weights=weights,
                           binds=matrices(np.asarray(meta["binds"]).reshape(-1, 12))))
    return result


def evaluate(groups, row, bone_count, skeleton_count=0):
    world = matrices(row[:bone_count * 12].reshape(bone_count, 12))
    skeletons = matrices(row[bone_count * 12:(bone_count + skeleton_count) * 12].reshape(skeleton_count, 12))
    cursor, points, normals = (bone_count + skeleton_count) * 12, [], []
    for group in groups:
        n, k = group["meta"]["vertices"], group["meta"]["targets"]
        values = np.array(row[cursor:cursor + k], dtype=float)
        values[abs(values) < float(np.float32(.0001))] = 0  # Shader float32 equality remains active.
        cursor += k
        transform = matrices(row[cursor:cursor + 12])
        cursor += 12
        p = group["base"] + (values @ group["sp"]).reshape(n, 3)
        normal = group["normal"] + (values @ group["sn"]).reshape(n, 3)
        if group["joints"].shape[1]:
            palette = world[group["meta"]["bones"]] @ group["binds"]
            outp, outn = np.zeros_like(p), np.zeros_like(normal)
            for slot in range(group["joints"].shape[1]):
                pose = palette[group["joints"][:, slot]]
                w = group["weights"][:, slot, None]
                outp += (np.einsum("vab,vb->va", pose[:, :3, :3], p) + pose[:, :3, 3]) * w
                outn += np.einsum("vab,vb->va", pose[:, :3, :3], normal) * w
            if skeleton_count:
                # Skin transforms normals linearly in skeleton space; the world
                # model normal matrix then uses inverse transpose (important
                # for nonuniform placement). Undo G already in world palettes.
                inverse = np.linalg.inv(skeletons[group["meta"]["skeleton_index"], :3, :3])
                outn = outn @ (inverse.T @ inverse).T
        else:
            outp = p @ transform[:3, :3].T + transform[:3, 3]
            outn = normal @ np.linalg.inv(transform[:3, :3])
        points.append(outp)
        normals.append(unit(outn))
    if cursor != len(row):
        raise ValueError("State layout mismatch")
    return np.concatenate(points), np.concatenate(normals)


def analyze(output, candidate_vertex_ids=None, position_limit_mm=None, normal_limit_degrees=None):
    output = Path(output)
    metadata = json.loads((output / "client/metadata.json").read_text())
    descriptions, records = metadata["descriptions"], metadata["records"]
    widths = [(d["bone_count"] + len(d["skeletons"])) * 12 + sum(m["targets"] + 12 for m in d["meshes"]) for d in descriptions]
    states = np.memmap(output / "client/states.f32", "<f4", mode="r", shape=(len(records), sum(widths)))
    counts = [sum(m["vertices"] for m in d["meshes"]) for d in descriptions]
    if counts[0] != counts[1]:
        raise ValueError("Vertex counts differ; surface reconstruction requires an explicit external validator")
    n = counts[0]
    mapping = np.arange(n) if candidate_vertex_ids is None else np.asarray(candidate_vertex_ids, dtype=int)
    if mapping.shape != (n,) or not np.array_equal(np.sort(mapping), np.arange(n)):
        raise ValueError("Candidate-to-source mapping must be a complete vertex permutation")
    reorder = np.argsort(mapping)
    if candidate_vertex_ids is None:
        identities = [[(m["path"], m["surface"], m["vertices"]) for m in d["meshes"]] for d in descriptions]
        if identities[0] != identities[1]:
            raise ValueError("Native surface identities changed; supply proven candidate_vertex_ids")
    groups = [read_groups(d) for d in descriptions]
    summaries, samples = {}, []
    for index, record in enumerate(records):
        a, an = evaluate(groups[0], states[index, :widths[0]], descriptions[0]["bone_count"], len(descriptions[0]["skeletons"]))
        b, bn = evaluate(groups[1], states[index, widths[0]:], descriptions[1]["bone_count"], len(descriptions[1]["skeletons"]))
        errors = np.linalg.norm(b[reorder] - a, axis=1) * 1000
        # atan2 avoids arccos's nonzero near-identical rounding floor.
        angles = np.degrees(np.arctan2(np.linalg.norm(np.cross(an, bn[reorder]), axis=1),
                                      np.einsum("vi,vi->v", an, bn[reorder])))
        if not np.isfinite(errors).all() or not np.isfinite(angles).all():
            raise ValueError("Nonfinite evaluation")
        sample = dict(record, maximum_position_mm=float(errors.max()), rms_position_mm=float(np.sqrt(np.mean(errors**2))),
                      maximum_normal_degrees=float(angles.max()), rms_normal_degrees=float(np.sqrt(np.mean(angles**2))),
                      worst_position_vertex=int(errors.argmax()), worst_normal_vertex=int(angles.argmax()))
        samples.append(sample)
        for category in ("all", record["category"]):
            bucket = summaries.setdefault(category, {"states": 0, "position_square_sum": 0., "normal_square_sum": 0.,
                                                    "maximum_position_mm": -1., "maximum_normal_degrees": -1.})
            bucket["states"] += 1
            bucket["position_square_sum"] += float(np.sum(errors**2))
            bucket["normal_square_sum"] += float(np.sum(angles**2))
            for metric, vertex in (("maximum_position_mm", "worst_position_vertex"), ("maximum_normal_degrees", "worst_normal_vertex")):
                if sample[metric] > bucket[metric]:
                    bucket[metric] = sample[metric]
                    bucket["worst_" + metric] = {"label": record["label"], "source_vertex": sample[vertex]}
    for bucket in summaries.values():
        bucket["rms_position_mm"] = float(np.sqrt(bucket.pop("position_square_sum") / (bucket["states"] * n)))
        bucket["rms_normal_degrees"] = float(np.sqrt(bucket.pop("normal_square_sum") / (bucket["states"] * n)))
    placement = {field + "_equal": descriptions[0][field] == descriptions[1][field]
                 for field in ("actor_global", "model_global", "selection")}
    report = {"actor": metadata["job"]["actor"], "models": [{"sha256": d["sha256"], "load_proof": d["load_proof"],
               "bones": d["bone_count"], "surfaces": len(d["meshes"]), "vertices": counts[i],
               "blend_buffer_bytes": sum(m["blend_buffer_bytes"] for m in d["meshes"])} for i, d in enumerate(descriptions)],
              "summary": summaries, "samples": samples, "engine": metadata["engine"], "placement": placement,
              "native_clips": descriptions[0]["clips"], "all_directed_switch_pairs": len(descriptions[0]["clips"]) * (len(descriptions[0]["clips"]) - 1),
              "position_limit_mm": position_limit_mm, "normal_limit_degrees": normal_limit_degrees,
              "within_requested_limits": None if position_limit_mm is None and normal_limit_degrees is None else
                                         (position_limit_mm is None or summaries["all"]["maximum_position_mm"] <= position_limit_mm) and
                                         (normal_limit_degrees is None or summaries["all"]["maximum_normal_degrees"] <= normal_limit_degrees),
              "scope": "Actual configured raw-client actor; every native clip, shifted samples, directed switches, nonlooping held endpoints, configured default and RESET; all native vertices/normals, quantized four/eight-influence skin. Float64 reconstruction of renderer inputs, not GPU pixels, imported PackedScenes, artistic acceptance or exhaustive continuous-time proof.",
              "provenance": {"probe_sha256": metadata["probe_sha256"], "checker_sha256": digest(__file__),
                             "metadata_sha256": digest(output / "client/metadata.json"), "states_sha256": digest(output / "client/states.f32"),
                             "candidate_vertex_mapping_sha256": digest_bytes(mapping.astype("<i8").tobytes())}}
    write_json(output / "client-validation.json", report)
    return report


def check(actor, source, candidate, output, *, client_root=None, godot=None, project=None,
          config=None, candidate_vertex_ids=None, prepare=True,
          position_limit_mm=None, normal_limit_degrees=None,
          source_sha256=None, candidate_sha256=None, dto=None):
    client_root, source, candidate, output = map(lambda p: Path(p).resolve(), (client_root or ROOT, source, candidate, output))
    godot, project = Path(godot or GODOT), Path(project or output / "project").resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "client/metadata.json").exists():
        raise ValueError("Use a new versioned output directory; existing evidence is immutable")
    for path, expected in ((source, source_sha256), (candidate, candidate_sha256)):
        if expected is not None and digest(path) != expected:
            raise ValueError("Fixture does not match requested SHA256: " + str(path))
    for limit in (position_limit_mm, normal_limit_degrees):
        if limit is not None and (not np.isfinite(limit) or limit < 0):
            raise ValueError("Requested limits must be finite and nonnegative")
    source_doc, source_bin = glb(source)
    candidate_doc, candidate_bin = glb(candidate)
    clips = [a.get("name", "") for a in source_doc.get("animations", []) if a.get("name") != "RESET"]
    other_clips = [a.get("name", "") for a in candidate_doc.get("animations", []) if a.get("name") != "RESET"]
    if not clips or "" in clips or len(set(clips)) != len(clips) or set(clips) != set(other_clips):
        raise ValueError("Native clip inventories differ or contain unnamed/duplicate clips")
    if candidate_vertex_ids is None and topology(source_doc, source_bin) != topology(candidate_doc, candidate_bin):
        raise ValueError("Topology changed; supply proven candidate_vertex_ids")
    if config is None:
        config = json.loads((client_root / "godot-client/data/actors/models.json").read_text(encoding="utf-8"))["models"][actor]
    original_map = client_root / "godot-client" / config["animationMap"].removeprefix("res://")
    mapping = json.loads(original_map.read_text(encoding="utf-8"))
    for index, clip in enumerate(clips):
        mapping["actions"]["__qa_native_" + str(index)] = clip
    write_json(output / "qa-animation-map.json", mapping)
    job = {"actor": actor, "output": str(output), "config": config, "all_native_clips": clips, "probe_sha256": digest(PROBE),
           "qa_animation_map_path": str(output / "qa-animation-map.json"),
           "original_animation_map_sha256": digest(original_map),
           "sample_fractions": [0., .03713, .13947, .25719, .38173, .49913, .61729, .73129, .85937, .93317, 1.],
           "switch_times": [.071, .193],
           "actor_fixtures": [{"name": name, "path": str(path), "sha256": digest(path)}
                              for name, path in (("source", source), ("candidate", candidate))]}
    if dto is not None:
        job["dto"] = dto
    write_json(output / "job.json", job)
    if prepare:
        prepare_project(project, client_root, godot)
    elif not (project / "runtime-client-project.json").exists() or digest(project / "tests" / PROBE.name) != digest(PROBE):
        raise ValueError("Project was not prepared with this version of the probe")
    run_godot(godot, project, output / "probe", ["--script", "res://tests/" + PROBE.name, "--", str(output / "job.json")])
    for fixture in job["actor_fixtures"]:
        if digest(fixture["path"]) != fixture["sha256"]:
            raise ValueError("Fixture changed during probe")
    report = analyze(output, candidate_vertex_ids, position_limit_mm, normal_limit_degrees)
    report["provenance"]["prepared_project_manifest_sha256"] = digest(project / "runtime-client-project.json")
    report["provenance"]["prepared_project"] = str(project)
    write_json(output / "client-validation.json", report)
    if not all(report["placement"].values()):
        raise ValueError("Actual client collider/default placement changed; measured report retained")
    return report


def self_test():
    """Exercise packed4/8 skin, >21 bones, morph cutoff and multi-surface math."""
    import tempfile
    scratch = ROOT / ".local/runtime-client-self-test"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        meshes = []
        for surface, slots in enumerate((4, 8)):
            prefix = str(Path(directory) / str(surface))
            def save(suffix, values, dtype="<f4"):
                np.asarray(values, dtype=dtype).tofile(prefix + suffix)
            save("-positions.f32", [[1, 0, 0]])
            save("-normals.f32", [[0, 2, 0]])
            save("-shape-positions.f32", [[[2, 0, 0]]])
            save("-shape-normals.f32", [[[0, 3, 0]]])
            joints = np.zeros((1, slots), int)
            joints[0, 0] = 29
            weights = np.zeros((1, slots))
            weights[0, 0] = 1
            save("-joints.i32", joints, "<i4")
            save("-weights.f32", weights)
            save("-skin.bin", np.c_[joints, weights * 65535], "<u2")
            bind = np.tile(np.eye(4)[:3].reshape(12), (30, 1)).tolist()
            meshes.append(dict(prefix=prefix, vertices=1, targets=1, mode=0, bones=list(range(30)), binds=bind))
        groups = read_groups({"meshes": meshes})
        world = np.tile(np.eye(4)[:3].reshape(12), (30, 1))
        world[29, 3] = 7
        transform = np.eye(4)[:3].reshape(12)
        cutoff = np.float32(.0001)
        row = np.r_[world.ravel(), cutoff, transform, np.nextafter(cutoff, np.float32(0)), transform]
        p, n = evaluate(groups, row, 30)
        np.testing.assert_allclose(p, [[8 + float(cutoff), 0, 0], [8, 0, 0]], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(n, [[0, 1, 0], [0, 1, 0]])
        # A quantized fractional skin weight must not silently normalize to1.
        groups[1]["weights"][0, 0] = 32768 / 65535
        p, _ = evaluate(groups, row, 30)
        np.testing.assert_allclose(p[1, 0], 8 * 32768 / 65535, rtol=0, atol=1e-12)
        unskinned = dict(groups[0], joints=np.empty((1, 0), int))
        transform = np.diag([2., 1., 1., 1.])[:3].reshape(12)
        unskinned["normal"] = unit(np.array([[1., 1., 0.]]))
        unskinned["sn"] = np.zeros((1, 3))
        _, n = evaluate([unskinned], np.r_[world.ravel(), 0, transform], 30)
        np.testing.assert_allclose(n[0], unit(np.array([[.5, 1., 0.]]))[0], atol=1e-12)
    return {"passed": True, "checks": ["four/eight packed influences", "30 bone palette", "multiple surfaces",
            "float32 cutoff equality and below", "normalized normal endpoints", "unrenormalized quantized weights", "unskinned inverse-transpose normals"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("actor", "source", "candidate", "output", "client-root", "project", "godot", "candidate-vertex-ids", "source-sha256", "candidate-sha256"):
        parser.add_argument("--" + name)
    parser.add_argument("--reuse-project", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--position-limit-mm", type=float)
    parser.add_argument("--normal-limit-degrees", type=float)
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0
    if not all((args.actor, args.source, args.candidate, args.output)):
        parser.error("--actor, --source, --candidate and --output are required")
    ids = json.loads(Path(args.candidate_vertex_ids).read_text()) if args.candidate_vertex_ids else None
    report = check(args.actor, args.source, args.candidate, args.output, client_root=args.client_root,
                   project=args.project, godot=args.godot, candidate_vertex_ids=ids, prepare=not args.reuse_project,
                   position_limit_mm=args.position_limit_mm, normal_limit_degrees=args.normal_limit_degrees,
                   source_sha256=args.source_sha256, candidate_sha256=args.candidate_sha256)
    print(json.dumps({"summary": report["summary"], "within_requested_limits": report["within_requested_limits"]}, indent=2))
    return 1 if report["within_requested_limits"] is False else 0


if __name__ == "__main__":
    sys.exit(main())
