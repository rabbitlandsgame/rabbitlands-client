"""Fresh-import finite-animation checks, without equivalence or visual approval.

Blender --background --python check_creature_runtime_blender.py -- --job jobs.json
    [--report summary.json]

The job file is a list, or {"jobs": [...]}. Each record supplies actor, variant,
path, sha256 and report_folder. Relative paths resolve against the job file.
An optional top-level report names the aggregate JSON. Successful individual
reports resume only with matching input, implementation, options and Blender.
Every file receives a factory-empty scene and a new GLB import at 30 FPS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time
import traceback

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.blender_vertex_identity import document, array
from video_motion.blender_object_rest import animated_armature_rest

_FRACTIONS = (0., .11337, .38196601125, .73119, .95131, 1.)
_FPS = 30
_FILES = [Path(__file__), *(Path(__file__).parent / "video_motion" / name
           for name in ("blender_vertex_identity.py", "blender_object_rest.py"))]
_TOOL_SHA = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in _FILES)).hexdigest()
_BLENDER = {"version": bpy.app.version_string,
            "build_hash": bpy.app.build_hash.decode(errors="replace")}
_OPTIONS = {"fps": _FPS, "fps_base": 1., "merge_vertices": False,
            "factory_empty_per_file": True, "query_fractions": list(_FRACTIONS)}


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=path.stem + "-", suffix=".json",
                                     dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(record, handle, indent=2, allow_nan=False)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def source_inventory(d, blob):
    """Describe the GLB itself, including active-channel rather than unused clocks."""
    require(d.get("asset", {}).get("version") == "2.0", "Expected glTF 2.0")
    require(all("bufferView" in im and "uri" not in im for im in d.get("images", [])),
            "Fresh self-contained checking requires embedded images")
    meshes, maximum_influences, budgets = [], 0, []
    for mi, mesh in enumerate(d.get("meshes", [])):
        for pi, primitive in enumerate(mesh["primitives"]):
            attrs = primitive["attributes"]
            positions = array(d, blob, attrs["POSITION"])
            require(len(positions) > 0 and np.isfinite(positions).all(), "Nonfinite/empty source geometry")
            for ai in list(attrs.values()) + [i for t in primitive.get("targets", []) for i in t.values()]:
                require(np.isfinite(array(d, blob, ai)).all(), "Nonfinite source vertex/target field")
            sets = sorted(int(k.split("_")[1]) for k in attrs if k.startswith("JOINTS_"))
            maximum, budget, sum_error = 0, 0, None
            if sets:
                require(sets in ([0], [0, 1]) and all(f"WEIGHTS_{i}" in attrs for i in sets),
                        "Unsupported source influence layout")
                for i in sets:
                    spec = d["accessors"][attrs[f"JOINTS_{i}"]]
                    require(spec["componentType"] in (5121, 5123) and not spec.get("normalized"),
                            "Joint indices must be unsigned integers")
                weights = np.concatenate([array(d, blob, attrs[f"WEIGHTS_{i}"]) for i in sets], axis=1)
                require(np.isfinite(weights).all() and np.all(weights >= 0), "Invalid source weights")
                budget = 4 * len(sets)
                maximum = int((weights > 0).sum(1).max())
                sum_error = float(np.abs(weights.sum(1) - 1).max())
                require(maximum <= budget, "Source exceeds its influence budget")
                maximum_influences = max(maximum_influences, maximum)
                budgets.append(budget)
            material = primitive.get("material")
            require(material is None or 0 <= material < len(d.get("materials", [])), "Invalid source material index")
            meshes.append({"mesh": mi, "primitive": pi, "vertices": len(positions),
                           "targets": len(primitive.get("targets", [])), "influence_budget": budget,
                           "maximum_positive_influences": maximum, "weight_sum_maximum_error": sum_error,
                           "material": material})
    require(meshes, "No source mesh primitives")
    clips = []
    for animation in d.get("animations", []):
        name = animation.get("name")
        require(isinstance(name, str) and name, "Unnamed animation")
        used = sorted({c["sampler"] for c in animation.get("channels", [])})
        require(used, "Cannot infer duration for a clip with no active channels")
        times = [array(d, blob, animation["samplers"][i]["input"]).ravel() for i in used]
        require(all(len(t) and np.isfinite(t).all() and np.all(np.diff(t) >= 0) for t in times),
                "Invalid active animation clock")
        for i in used:
            require(np.isfinite(array(d, blob, animation["samplers"][i]["output"])).all(),
                    "Nonfinite source animation values")
        start, end = min(float(t[0]) for t in times), max(float(t[-1]) for t in times)
        require(start >= 0 and end >= start, "Negative/invalid clip timeline")
        clips.append({"name": name, "active_start_seconds": start, "active_end_seconds": end,
                      "active_duration_seconds": end - start, "active_sampler_count": len(used),
                      "unreferenced_sampler_count": len(animation["samplers"]) - len(used),
                      "channels": len(animation["channels"])})
    require(clips and len({c["name"] for c in clips}) == len(clips), "Requires unique named clips")
    return {"primitives": meshes, "unique_mesh_vertices": sum(m["vertices"] for m in meshes),
            "instanced_vertices": sum(sum(d["accessors"][p["attributes"]["POSITION"]]["count"]
                for p in d["meshes"][node["mesh"]]["primitives"]) for node in d["nodes"] if "mesh" in node),
            "unique_skin_joint_nodes": len({j for skin in d.get("skins", []) for j in skin["joints"]}),
            "skin_joint_counts": [len(skin["joints"]) for skin in d.get("skins", [])],
            "maximum_positive_influences": maximum_influences,
            "maximum_influence_budget": max(budgets, default=0),
            "materials": len(d.get("materials", [])), "images": len(d.get("images", [])), "clips": clips}


def data_blocks(objects):
    result, seen = [], set()
    for item in objects + [ob.data.shape_keys for ob in objects if ob.type == "MESH" and ob.data.shape_keys]:
        if item.as_pointer() not in seen:
            result.append(item)
            seen.add(item.as_pointer())
    return result


def action_bindings(blocks, clip_names):
    """Use actual imported action slots/NLA labels; never infer a missing action."""
    result = {name: {} for name in clip_names}
    observed = []

    def matches(name, clip):
        return name == clip or re.fullmatch(re.escape(clip) + r"\.\d{3,}", name) is not None

    for block in blocks:
        ad = block.animation_data
        if ad is None:
            continue
        entries = []
        if ad.action is not None:
            entries.append((None, ad.action, ad.action_slot))
        for track in ad.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    entries.append((track.name, strip.action, strip.action_slot))
            track.mute = True
        for label, action, slot in entries:
            exact = [name for name in clip_names if label == name]
            if not exact:
                exact = [name for name in clip_names if action.name == name]
            names = exact or [name for name in clip_names if matches(label or "", name) or matches(action.name, name)]
            require(len(names) == 1, f"Ambiguous/unrecognized imported action {action.name!r} / NLA {label!r}")
            require(slot is not None or len(action.slots) == 0, f"Missing imported action slot: {action.name}")
            clip = names[0]
            old = result[clip].get(block.as_pointer())
            require(old is None or old[1].as_pointer() == action.as_pointer()
                    and (old[2].as_pointer() if old[2] else None) == (slot.as_pointer() if slot else None),
                    f"Conflicting imported slots on {block.name!r} for {clip!r}")
            result[clip][block.as_pointer()] = (block, action, slot)
            observed.append({"clip": clip, "data": block.name, "action": action.name,
                             "slot": slot.identifier if slot is not None else None, "nla_track": label})
        ad.action = None
    for name in clip_names:
        require(result[name], f"Native clip has no bound imported action: {name}")
    return result, observed


def authored_shape_defaults(d, blob, objects):
    candidates = []
    lower, upper = -10., 10.
    for node in d["nodes"]:
        if "mesh" not in node:
            continue
        mesh = d["meshes"][node["mesh"]]
        counts = {len(p.get("targets", [])) for p in mesh["primitives"]}
        require(len(counts) == 1, "Inconsistent source target counts")
        count = counts.pop()
        values = node.get("weights", mesh.get("weights", [0.] * count))
        require(len(values) == count and np.isfinite(values).all(), "Invalid authored shape defaults")
        if count:
            candidates.append({"node": node.get("name"), "mesh": mesh.get("name"), "weights": values})
    for animation in d["animations"]:
        for channel in animation["channels"]:
            if channel["target"]["path"] == "weights":
                sampler = animation["samplers"][channel["sampler"]]
                values = array(d, blob, sampler["output"])
                require(float(values.min()) >= lower and float(values.max()) <= upper,
                        "Source shape values exceed Blender's supported [-10,10] slider domain")
    defaults, records = {}, []
    for ob in objects:
        if ob.type != "MESH" or not ob.data.shape_keys:
            continue
        key = ob.data.shape_keys
        require(key.use_relative, "Only relative imported shape keys are supported")
        count = len(key.key_blocks) - 1
        possible = [c for c in candidates if len(c["weights"]) == count]
        named = [c for c in possible if c["node"] == ob.name or c["mesh"] == ob.data.name]
        chosen = named or possible
        require(chosen and all(c["weights"] == chosen[0]["weights"] for c in chosen),
                f"Cannot bind authored shape defaults without guessing: {ob.name}")
        values = np.array(chosen[0]["weights"], float)
        require(np.all(values >= lower) and np.all(values <= upper), "Shape defaults exceed Blender slider domain")
        old = defaults.get(key.as_pointer())
        require(old is None or np.array_equal(old[1], values), "Shared Key data has conflicting authored defaults")
        defaults[key.as_pointer()] = (key, values)
        for block in list(key.key_blocks)[1:]:
            block.slider_min, block.slider_max = lower, upper
        records.append({"object": ob.name, "key_data": key.name, "count": count, "defaults": values.tolist(),
                        "binding": "source node/mesh name and target count" if named else "identical source defaults for this target count",
                        "slider_min": lower, "slider_max": upper})
    expected = sum(len(d["meshes"][n["mesh"]]["primitives"][0].get("targets", [])) > 0
                   for n in d["nodes"] if "mesh" in n)
    require(not expected or records, "Source corrective shapes missing after import")
    return defaults, records


def evaluate(objects, arms, depsgraph):
    vertices, bounds, bones = 0, [], 0
    for ob in objects:
        evaluated = ob.evaluated_get(depsgraph)
        world = np.asarray(evaluated.matrix_world, dtype=float)
        require(np.isfinite(world).all(), f"Nonfinite object transform: {ob.name}")
        if ob.type != "MESH":
            continue
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            require(len(mesh.vertices) == len(ob.data.vertices), "Unexpected evaluated topology change")
            points, normals = np.empty(len(mesh.vertices) * 3), np.empty(len(mesh.vertices) * 3)
            mesh.vertices.foreach_get("co", points)
            mesh.vertices.foreach_get("normal", normals)
            require(np.isfinite(points).all() and np.isfinite(normals).all(), f"Nonfinite evaluated mesh: {ob.name}")
            points = points.reshape(-1, 3) @ world[:3, :3].T + world[:3, 3]
            require(np.isfinite(points).all(), f"Nonfinite world mesh: {ob.name}")
            require(len(points), "Empty evaluated mesh")
            vertices += len(points)
            bounds.append((points.min(0), points.max(0)))
            for poly in mesh.polygons:
                require(0 <= poly.material_index < max(1, len(mesh.materials)), "Invalid imported material slot")
        finally:
            evaluated.to_mesh_clear()
    for arm in arms:
        evaluated = arm.evaluated_get(depsgraph)
        for bone in evaluated.pose.bones:
            require(np.isfinite(np.asarray(evaluated.matrix_world @ bone.matrix)).all(),
                    f"Nonfinite bone transform: {arm.name}/{bone.name}")
            bones += 1
    require(bounds, "No evaluated geometry")
    return {"vertices": vertices, "bones": bones,
            "world_min": np.min([x[0] for x in bounds], axis=0).tolist(),
            "world_max": np.max([x[1] for x in bounds], axis=0).tolist(), "finite": True}


def inspect_file(path):
    d, blob = document(path)  # Confirms the GLB2 header and exact file length.
    inventory = source_inventory(d, blob)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = _FPS, 1.
    result = bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False)
    require("FINISHED" in result, "GLB import did not finish")
    objects = list(bpy.data.objects)
    arms = [ob for ob in objects if ob.type == "ARMATURE"]
    blocks = data_blocks(objects)
    bindings, observed = action_bindings(blocks, [c["name"] for c in inventory["clips"]])
    shapes, shape_records = authored_shape_defaults(d, blob, objects)
    rest = animated_armature_rest(d, [{"name": ob.name, "type": ob.type} for ob in objects])
    object_defaults = {ob.as_pointer(): ob.matrix_basis.copy() for ob in objects}
    for record in rest:
        ob = next(ob for ob in objects if ob.name == record["blender_object"])
        object_defaults[ob.as_pointer()] = Matrix(record["blender_local_matrix"])

    def reset():
        for block in blocks:
            if block.animation_data:
                block.animation_data.action = None
                for track in block.animation_data.nla_tracks:
                    track.mute = True
        for ob in objects:
            ob.matrix_basis = object_defaults[ob.as_pointer()].copy()
        for arm in arms:
            for bone in arm.pose.bones:
                bone.matrix_basis = Matrix.Identity(4)
        for key, values in shapes.values():
            for block, value in zip(list(key.key_blocks)[1:], values, strict=True):
                block.value = float(value)
        bpy.context.view_layer.update()

    reset()
    neutral = evaluate(objects, arms, bpy.context.evaluated_depsgraph_get())
    imported_influences = []
    for ob in objects:
        if ob.type != "MESH":
            continue
        bone_names = {b.name for m in ob.modifiers if m.type == "ARMATURE" and m.object
                      for b in m.object.data.bones}
        groups = {g.index for g in ob.vertex_groups if g.name in bone_names}
        maximum = max((sum(g.group in groups and g.weight > 0 for g in v.groups) for v in ob.data.vertices), default=0)
        require(maximum <= 8, "Imported mesh exceeds eight positive bone groups")
        imported_influences.append({"object": ob.name, "maximum_positive_bone_groups": maximum})
    clips = []
    for clip in inventory["clips"]:
        chosen = bindings[clip["name"]]
        actions = {action.as_pointer(): action for block, action, slot in chosen.values()}
        ranges = [{"action": action.name, "frame_range": list(map(float, action.frame_range))}
                  for action in actions.values()]
        begin = min(r["frame_range"][0] for r in ranges)
        end = max(r["frame_range"][1] for r in ranges)
        native = np.array([clip["active_start_seconds"], clip["active_end_seconds"]]) * _FPS
        tolerance = max(1e-5, 8 * abs(float(np.spacing(np.float32(max(1., float(np.abs(native).max())))))))
        require(abs(begin - native[0]) <= tolerance and abs(end - native[1]) <= tolerance,
                f"Imported action range does not match active native clocks: {clip['name']} {(begin, end)} vs {native.tolist()}")
        poses = []
        for fraction in _FRACTIONS:
            reset()
            for block, action, slot in chosen.values():
                block.animation_data_create()
                block.animation_data.action = action
                if slot is not None:
                    block.animation_data.action_slot = slot
            seconds = clip["active_end_seconds"] * fraction
            frame = seconds * _FPS
            scene.frame_set(math.floor(frame), subframe=frame - math.floor(frame))
            bpy.context.view_layer.update()
            poses.append({"seconds": seconds, "frame": frame,
                          **evaluate(objects, arms, bpy.context.evaluated_depsgraph_get())})
        clips.append({**clip, "imported_frame_range": [begin, end], "bound_action_ranges": ranges,
                      "frame_timing_tolerance": tolerance, "data_bindings": len(chosen), "poses": poses, "finite": True})
    reset()
    reset_geometry = evaluate(objects, arms, bpy.context.evaluated_depsgraph_get())
    require(neutral == reset_geometry, "Neutral finite geometry/reset bounds changed after clip checks")
    material_records = []
    for material in bpy.data.materials:
        images = []
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    image = node.image
                    require(all(int(n) > 0 for n in image.size), f"Texture failed to load: {image.name}")
                    images.append({"name": image.name, "size": list(image.size), "packed": image.packed_file is not None})
        material_records.append({"name": material.name, "use_nodes": material.use_nodes, "images": images})
    return {"source_inventory": inventory, "imported": {"objects": len(objects),
            "mesh_objects": sum(ob.type == "MESH" for ob in objects),
            "armatures": [{"name": arm.name, "bones": len(arm.pose.bones)} for arm in arms],
            "total_bones": sum(len(arm.pose.bones) for arm in arms),
            "total_vertices": neutral["vertices"], "materials": material_records,
            "influences": imported_influences, "shape_defaults": shape_records},
            "action_bindings": observed, "animated_armature_object_rest": rest,
            "default_geometry": neutral, "post_clip_reset_geometry": reset_geometry, "clips": clips,
            "poses_evaluated": sum(len(c["poses"]) for c in clips), "all_clips_finite": True,
            "scope": "Fresh Blender GLB2 import and finite action/geometry validation only. No source/candidate equivalence, contact, engine, render, artistic or installation approval.",
            "default_state_scope": "Authored shape defaults and uniquely named animated Armature object rest; other object bases are imported snapshots. No physical correspondence claim."}


def run(job_path, summary=None):
    job_path = Path(job_path).resolve()
    plan = json.loads(job_path.read_text(encoding="utf-8"))
    records = plan if isinstance(plan, list) else plan.get("jobs", plan.get("records", [plan]))
    require(isinstance(records, list) and records, "Job records must be a nonempty list")
    summary = Path(summary or (plan.get("report") if isinstance(plan, dict) else None)
                   or job_path.with_name(job_path.stem + ".blender-results.json"))
    if not summary.is_absolute():
        summary = job_path.parent / summary
    summary = summary.resolve()
    protected = {job_path}
    for job in records:
        if isinstance(job, dict) and job.get("path"):
            path = Path(job["path"])
            protected.add((path if path.is_absolute() else job_path.parent / path).resolve())
    require(summary not in protected, "Summary must not overwrite an input/job file")
    results = []
    receipts = set()
    for index, job in enumerate(records):
        started = time.perf_counter()
        row = {"actor": job.get("actor") if isinstance(job, dict) else None,
               "variant": job.get("variant") if isinstance(job, dict) else None, "job_index": index,
               "validator_sha256": _TOOL_SHA, "blender": _BLENDER, "options": _OPTIONS}
        receipt, receipt_safe = None, False
        try:
            require(isinstance(job, dict), "Each job must be an object")
            require(all(isinstance(job.get(key), str) and job[key] for key in ("actor", "variant")),
                    "Each record needs explicit actor and variant")
            folder = job.get("report_folder", job.get("reportfolder"))
            require(folder is not None, "Each record must explicitly supply report_folder")
            folder = Path(folder)
            if not folder.is_absolute():
                folder = job_path.parent / folder
            receipt = (folder / "blender-validation.json").resolve()
            require(receipt not in protected and receipt != summary,
                    "Individual report must not overwrite an input/job/summary file")
            require(receipt not in receipts, "Two jobs must not share one report folder")
            receipts.add(receipt)
            receipt_safe = True
            path = Path(job["path"])
            if not path.is_absolute():
                path = job_path.parent / path
            path = path.resolve()
            expected = job.get("sha256", job.get("expected_sha256", job.get("SHA")))
            require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "Explicit lowercase SHA-256 required")
            actual = sha(path)
            row.update(path=str(path), sha256=actual, expected_sha256=expected)
            require(actual == expected, "Source SHA-256 mismatch")
            signature = {key: row[key] for key in ("actor", "variant", "path", "sha256", "validator_sha256", "blender", "options")}
            if receipt.exists():
                old = json.loads(receipt.read_text(encoding="utf-8"))
                if old.get("status") == "passed_fresh_import_finite_only" and old.get("signature") == signature:
                    row.update(status=old["status"], resumed=True, report=str(receipt), report_sha256=sha(receipt),
                               seconds=time.perf_counter() - started)
                    results.append(row)
                    save(summary, {"job_sha256": sha(job_path), "results": results, "complete": False})
                    print(json.dumps(row), flush=True)
                    continue
            row.update(inspect_file(path))
            require(sha(path) == actual, "Input changed during Blender validation")
            row.update(status="passed_fresh_import_finite_only", signature=signature, resumed=False)
        except Exception as error:
            row.update(status="error", error=str(error), traceback=traceback.format_exc(), resumed=False)
        row["seconds"] = time.perf_counter() - started
        if receipt_safe:
            save(receipt, row)
        results.append({key: row[key] for key in ("actor", "variant", "status", "seconds", "resumed", "path", "sha256")
                        if key in row} | {"report": str(receipt) if receipt_safe else None,
                                          "report_sha256": sha(receipt) if receipt_safe else None})
        save(summary, {"job_sha256": sha(job_path), "results": results, "complete": False})
        print(json.dumps(results[-1]), flush=True)
    aggregate = {"job_sha256": sha(job_path), "validator_sha256": _TOOL_SHA, "blender": _BLENDER,
                 "results": results, "complete": True, "passed": all(r["status"] != "error" for r in results),
                 "scope": "Fresh import/finite actions only; no equivalence or visual acceptance."}
    save(summary, aggregate)
    return aggregate


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_path", nargs="?", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(arguments)
    job = args.job or args.job_path
    require(job is not None, "Pass --job jobs.json")
    result = run(job, args.report)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
