#!/usr/bin/env python3
"""Create a new whole-strand Storm Chimera mane repair draft, never install it.

The frozen owner profile remains a private input. Complete disconnected mane
pieces recover their source default contour and share one existing neck owner.
Protected face/body components and all original animation curves remain intact.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import numpy as np

from bake_armored_rigid_owners import physical_components
from optimize_creature_sampling import _field_sampler
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_storage import _append, _array, _compact_reachable
from video_motion.native_shapes import NativeShapeAsset

REFERENCE_SHA = "e35e661a2a2ad5987be76c473c916ed17c7692e7d0233277a782903765f909e8"
BASELINE_SHA = "53125895c058ae0f00793b5459325a6f04d0906fbcf8fb1487f0253c82bc93da"
PROFILE_SHA = "9cbf8d9343806d344e4ab8d5995f6d0643112b970afb84cc1923b5292ffba378"


def eligible_component(ids, protected, neck):
    """Select whole small neck pieces; a single protected seam excludes all."""
    return len(ids) <= 100 and not set(ids) & protected and neck[ids].mean() >= .8


def repair(reference: Path, baseline: Path, profile: Path, output: Path, report: Path) -> dict:
    if (digest(reference), digest(baseline), digest(profile)) != (REFERENCE_SHA, BASELINE_SHA, PROFILE_SHA):
        raise ValueError("Recipe requires the exact frozen reference, bake and owner profile")
    inputs = {path.resolve() for path in (reference, baseline, profile)}
    if (output.exists() or report.exists() or output.resolve() in inputs
            or report.resolve() in inputs or output.resolve() == report.resolve()):
        raise ValueError("GLB and report must be separate new files, outside all inputs")
    source, baked = NativeShapeAsset(reference), NativeShapeAsset(baseline)
    if len(source.parts) != 1 or len(baked.parts) != 1:
        raise ValueError("Recipe requires its original single primitive")
    part, source_part = baked.parts[0], source.parts[0]
    if not np.array_equal(part["nodes"], source_part["nodes"]):
        raise ValueError("Original joint palette changed")
    owner = json.loads(profile.read_text(encoding="utf-8"))
    protected = set(owner["head_support_vertex_ids"] + owner["body_support_vertex_ids"])
    document, binary = read_glb(baseline)
    before, old_binary = copy.deepcopy(document), bytes(binary)
    binary = bytearray(binary)
    primitive = document["meshes"][document["nodes"][part["node"]]["mesh"]]["primitives"][0]
    faces = accessor(document, binary, primitive["indices"]).astype(int).reshape(-1, 3)
    components = physical_components(source_part["position"][:, :3], faces)
    poses = []
    for clip in source.animations:
        duration = source.duration(clip)
        times = np.unique(np.r_[0., duration, (np.arange(17) + .38196601125) / 17 * duration,
                                [1.32499957084651] if clip == "Walk" else []])
        poses.extend((clip, float(time)) for time in times)
    poses.append(("DEFAULT", 0.))
    original, palettes = [], []
    sampler = _field_sampler(source)
    for clip, time in poses:
        if clip == "DEFAULT":
            source_world, morph, world = source.rest, source.default_weights, baked.rest
        else:
            t, q, scale, weights = source.sample(clip, [time])
            source_world = source.world(t[0], q[0], scale[0])
            morph = {node: values[0] for node, values in weights.items()}
            t, q, scale, _ = baked.sample(clip, [time])
            world = baked.world(t[0], q[0], scale[0])
        original.append(sampler(source_world, morph)[0])
        palettes.append(world[part["nodes"]] @ part["bind"])
    original, palettes = np.array(original), np.array(palettes)
    rest = baked.rest[part["nodes"]] @ part["bind"]
    arrays = {key: _array(document, binary, index) for key, index in primitive["attributes"].items()}
    _, default_normals = sampler(source.rest, source.default_weights)
    lookup = {int(node): i for i, node in enumerate(part["nodes"])}
    lion, goat = source.own([67, 68, 69, 70]), source.own([71, 72, 73, 74])
    neck = lion + goat
    selected, records = [], []
    for component_id, ids in enumerate(components):
        if not eligible_component(ids, protected, neck):
            continue
        role = "lion" if lion[ids].sum() > goat[ids].sum() else "goat"
        candidates = [65, 66] + ([67, 68, 69, 70] if role == "lion" else [71, 72, 73, 74])
        scores = []
        for node in candidates:
            joint = lookup[node]
            local = (np.linalg.inv(rest[joint]) @ np.c_[source.vertices[ids], np.ones(len(ids))].T).T
            prediction = np.einsum("tab,vb->tva", palettes[:, joint, :3], local)
            scores.append((float(np.mean((prediction - original[:, ids]) ** 2)), node, local))
        mse, node, local = min(scores, key=lambda value: value[0])
        joint = lookup[node]
        arrays["POSITION"][ids] = local[:, :3]
        normals = np.linalg.solve(rest[joint, :3, :3], default_normals[ids].T).T
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-30)
        arrays["NORMAL"][ids] = normals
        for key, values in arrays.items():
            if key.startswith(("JOINTS_", "WEIGHTS_")):
                values[ids] = 0
        arrays["JOINTS_0"][ids, 0] = joint
        arrays["WEIGHTS_0"][ids, 0] = 1.
        selected.extend(ids)
        records.append({"component": component_id, "role": role, "owner_node": node,
                        "original_vertex_ids": ids.tolist(), "fit_rms_model_units": float(np.sqrt(mse * 3))})
    selected = np.array(sorted(selected))
    outside = np.setdiff1d(np.arange(len(source.vertices)), selected)
    order = ["POSITION", "NORMAL", "JOINTS_0", "WEIGHTS_0"]
    order += [key for key in primitive["attributes"] if key.startswith(("JOINTS_", "WEIGHTS_")) and key not in order]
    for key in order:
        primitive["attributes"][key] = _append(document, binary, arrays[key], document["accessors"][primitive["attributes"][key]])
    document, binary = _compact_reachable(document, binary)
    old_primitive = before["meshes"][before["nodes"][part["node"]]["mesh"]]["primitives"][0]
    primitive = document["meshes"][document["nodes"][part["node"]]["mesh"]]["primitives"][0]
    for key, index in old_primitive["attributes"].items():
        old_values, values = _array(before, old_binary, index), _array(document, binary, primitive["attributes"][key])
        if old_values[outside].tobytes() != values[outside].tobytes():
            raise ValueError(f"Exterior {key} changed")
        if key not in order and old_values.tobytes() != values.tobytes():
            raise ValueError(f"Unselected field {key} changed")
    if before["nodes"] != document["nodes"] or before["materials"] != document["materials"]:
        raise ValueError("Original nodes/materials changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(output, document, binary)
    receipt = {"actor": "storm_chimera", "status": "unapproved_whole_strand_repair_draft",
               "source_sha256": digest(reference), "baseline_sha256": digest(baseline),
               "profile_sha256": digest(profile), "candidate_sha256": digest(output), "bytes": output.stat().st_size,
               "changed_original_vertex_ids": selected.tolist(), "unchanged_vertices": len(outside),
               "components": records, "training_poses": len(poses), "extra_bones_vs_commented": 0,
               "extra_draws": 0, "influence_budget": part["weights"].shape[1],
               "limitations": "Whole-strand rigidity approximates source deformation. Active installed model uses a different63joint rig; no runtime cost equivalence claim."}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "baseline", "profile", "output", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.reference, args.baseline, args.profile, args.output, args.report)))
