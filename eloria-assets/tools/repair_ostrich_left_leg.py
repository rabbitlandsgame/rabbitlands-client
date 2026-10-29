#!/usr/bin/env python3
"""Reproduce the bounded, skin-only Ostrich left-leg repair draft.

This authoring tool writes a new GLB; it never installs or approves it. Inputs
are the frozen corrective reference and the separately reviewed zero-shape bake.
The recipe keeps geometry, original curves, binds and all exterior skin rows.
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
from scipy.optimize import nnls
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

from optimize_creature_sampling import _field_sampler
from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.creature_storage import _append, _array, _compact_reachable
from video_motion.native_shapes import NativeShapeAsset

REFERENCE_SHA = "2c5d7c1fa448079dbfc956565c05197db473b885918baa35ccf0e41ac640ae2f"
BASELINE_SHA = "b41f786ebd08aff62b3669d492e7932d84fcfb9c8c5d643cbcdbf4b6250e64cd"
COMMENT_TIME = 0.733304000000001


def repair(reference: Path, baseline: Path, output: Path, report: Path) -> dict:
    """Apply the pinned anatomical recipe; fail closed on other source versions."""
    if digest(reference) != REFERENCE_SHA or digest(baseline) != BASELINE_SHA:
        raise ValueError("The recipe requires its exact frozen reference/bake pair")
    inputs = (reference.resolve(), baseline.resolve())
    if (output.exists() or report.exists() or output.resolve() in inputs
            or report.resolve() in inputs or output.resolve() == report.resolve()):
        raise ValueError("GLB and report must be separate new files, outside both inputs")
    source, baked = NativeShapeAsset(reference), NativeShapeAsset(baseline)
    if len(source.parts) != 1 or len(baked.parts) != 1:
        raise ValueError("Recipe requires its original single primitive")
    part, source_part = baked.parts[0], source.parts[0]
    if not np.array_equal(part["nodes"], source_part["nodes"]):
        raise ValueError("Original joint palette changed")
    primitive = baked.d["meshes"][baked.d["nodes"][part["node"]]["mesh"]]["primitives"][0]
    faces = accessor(baked.d, baked.b, primitive["indices"]).astype(int).reshape(-1, 3)
    edges = np.unique(np.sort(np.r_[faces[:, :2], faces[:, 1:], faces[:, [2, 0]]], axis=1), axis=0)
    poses = []
    for clip in source.animations:
        duration = source.duration(clip)
        times = np.unique(np.r_[0., duration, (np.arange(17) + .38196601125) / 17 * duration,
                                [COMMENT_TIME] if clip == "Sword_Attack" else []])
        poses.extend((clip, float(time)) for time in times)
    poses.append(("DEFAULT", 0.))
    fields = {}
    for label, asset in (("reference", source), ("baseline", baked)):
        sampler = _field_sampler(asset)
        positions, normals, palettes = [], [], []
        for clip, time in poses:
            if clip == "DEFAULT":
                world, morph = asset.rest, asset.default_weights
            else:
                t, q, scale, weights = asset.sample(clip, [time])
                world = asset.world(t[0], q[0], scale[0])
                morph = {node: values[0] for node, values in weights.items()}
            p, n = sampler(world, morph)
            positions.append(p)
            normals.append(n)
            palettes.append(world[part["nodes"]] @ part["bind"])
        fields[label] = np.array(positions), np.array(normals), np.array(palettes)
    original, original_normals, _ = fields["reference"]
    previous, _, palettes = fields["baseline"]
    at = poses.index(("Sword_Attack", COMMENT_TIME))
    source_length = np.linalg.norm(original[:, edges[:, 1]] - original[:, edges[:, 0]], axis=2)
    old_length = np.linalg.norm(previous[:, edges[:, 1]] - previous[:, edges[:, 0]], axis=2)
    strain = np.where(source_length > 1e-5, abs(old_length / np.maximum(source_length, 1e-30) - 1), -1)
    region = ((source.own([0, 1, 2]) > .25) & (source.vertices[:, 0] > .025)
              & (source.vertices[:, 1] > .12) & (source.vertices[:, 1] < .38))
    seeds = region & (np.linalg.norm(previous[at] - original[at], axis=1) > .015)
    critical = np.unique(edges[strain[at] > .20])
    seeds[critical] = region[critical]
    ring = np.unique(faces[np.isin(faces, np.flatnonzero(seeds)).any(1)])
    mask = seeds.copy()
    mask[ring] = region[ring]
    groups = {}
    for i, row in enumerate(source_part["position"][:, :3]):
        groups.setdefault(tuple(row), []).append(i)
    members = list(groups.values())
    membership = np.empty(len(source.vertices), int)
    for i, ids in enumerate(members):
        membership[ids] = i
    chosen = np.array([i for i, ids in enumerate(members) if mask[ids].any()])
    selected = np.array(sorted(i for group in chosen for i in members[group]))
    reps = np.array([members[group][0] for group in chosen])
    physical_edges = np.unique(np.sort(membership[edges], axis=1), axis=0)
    adjacency = [set() for _ in members]
    for i, j in physical_edges[physical_edges[:, 0] != physical_edges[:, 1]]:
        adjacency[i].add(j)
        adjacency[j].add(i)
    local = {group: i for i, group in enumerate(chosen)}
    matrix = np.zeros((len(chosen), len(chosen)))
    rhs = np.zeros((len(chosen), len(poses), 3))
    for group, i in local.items():
        matrix[i, i] = len(adjacency[group])
        for other in adjacency[group]:
            if other in local:
                matrix[i, local[other]] -= 1
            else:
                rhs[i] += previous[:, members[other]].mean(1) - original[:, members[other]].mean(1)
    offset = spsolve(csr_matrix(matrix), rhs.reshape(len(chosen), -1))
    offset = offset.reshape(len(chosen), len(poses), 3).transpose(1, 0, 2)
    goals = original[:, reps] + offset
    columns = np.einsum("tjab,vb->tvja", palettes, part["position"][reps])[:, :, :, :3]
    raw_normals = accessor(baked.d, baked.b, primitive["attributes"]["NORMAL"])
    normal_columns = np.einsum("tjab,vb->tvja", palettes[:, :, :3, :3], raw_normals[reps])
    n, joint_count = len(source.vertices), len(part["nodes"])
    old_weights, source_weights = np.zeros((n, joint_count)), np.zeros((n, joint_count))
    for target, p in ((old_weights, part), (source_weights, source_part)):
        for slot in range(p["weights"].shape[1]):
            np.add.at(target, (np.arange(n), p["joints"][:, slot]), p["weights"][:, slot])
    lookup = {int(node): i for i, node in enumerate(part["nodes"])}
    budget = part["weights"].shape[1]
    fitted = []
    for i, vertex in enumerate(reps):
        support = np.unique(np.r_[np.flatnonzero(source_weights[vertex] > 1e-7),
                                  np.flatnonzero(old_weights[vertex] > 1e-7),
                                  [lookup[j] for j in [0, 1, 2, 14, 15]]]).astype(int)
        def solve(ids):
            design = np.r_[columns[:, i, ids].transpose(0, 2, 1).reshape(-1, len(ids)),
                           .01 * normal_columns[:, i, ids].transpose(0, 2, 1).reshape(-1, len(ids)),
                           np.ones((1, len(ids))) * 10]
            target = np.r_[goals[:, i].ravel(), .01 * original_normals[:, vertex].ravel(), 10.]
            return nnls(design, target)[0]
        values = solve(support)
        if np.count_nonzero(values > 1e-8) > budget:
            support = support[np.argsort(values)[-budget:]]
            values = solve(support)
        row = np.zeros(joint_count)
        row[support] = values / values.sum()
        fitted.append(row)
    if not np.isfinite(fitted).all():
        raise ValueError("Nonfinite constrained fit")
    document, binary = read_glb(baseline)
    old_document, old_binary = copy.deepcopy(document), bytes(binary)
    binary = bytearray(binary)
    primitive = document["meshes"][document["nodes"][part["node"]]["mesh"]]["primitives"][0]
    sets = sorted(int(key.split("_")[1]) for key in primitive["attributes"] if key.startswith("JOINTS_"))
    joints = np.c_[tuple(_array(document, binary, primitive["attributes"][f"JOINTS_{k}"]) for k in sets)]
    weights = np.c_[tuple(_array(document, binary, primitive["attributes"][f"WEIGHTS_{k}"]) for k in sets)]
    for row, representative in zip(fitted, reps):
        positive = np.flatnonzero(row > 1e-9)
        positive = positive[np.argsort(row[positive])[::-1]]
        if len(positive) > budget:
            raise ValueError("Influence budget exceeded")
        ids = groups[tuple(source_part["position"][representative, :3])]
        joints[ids], weights[ids] = 0, 0
        joints[np.ix_(ids, np.arange(len(positive)))] = positive
        weights[np.ix_(ids, np.arange(len(positive)))] = row[positive]
    for index, k in enumerate(sets):
        for field, values in (("JOINTS", joints), ("WEIGHTS", weights)):
            key = f"{field}_{k}"
            primitive["attributes"][key] = _append(document, binary, values[:, index * 4:index * 4 + 4],
                                                    document["accessors"][primitive["attributes"][key]])
    document, binary = _compact_reachable(document, binary)
    outside = np.setdiff1d(np.arange(n), selected)
    old_primitive = old_document["meshes"][old_document["nodes"][part["node"]]["mesh"]]["primitives"][0]
    new_primitive = document["meshes"][document["nodes"][part["node"]]["mesh"]]["primitives"][0]
    for key, index in old_primitive["attributes"].items():
        before, after = _array(old_document, old_binary, index), _array(document, binary, new_primitive["attributes"][key])
        if before[outside].tobytes() != after[outside].tobytes():
            raise ValueError(f"Exterior {key} changed")
        if not key.startswith(("JOINTS_", "WEIGHTS_")) and before.tobytes() != after.tobytes():
            raise ValueError(f"Geometry attribute {key} changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(output, document, binary)
    receipt = {"actor": "ostrich", "status": "unapproved_partial_repair_draft", "source_sha256": digest(reference),
               "baseline_sha256": digest(baseline), "candidate_sha256": digest(output), "bytes": output.stat().st_size,
               "changed_original_vertex_ids": selected.tolist(), "changed_physical_groups": len(chosen),
               "unchanged_vertices": len(outside), "training_poses": len(poses), "extra_bones": 0, "extra_draws": 0,
               "influence_budget": budget, "limitations": "Partial reduction of leg shear; no exact source fidelity or runtime replacement."}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.reference, args.baseline, args.output, args.report)))
