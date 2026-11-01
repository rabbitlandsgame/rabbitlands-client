#!/usr/bin/env python3
"""Prepare sparse mounted strain constraints from the approved cape skin.

This selects edges only. It does not modify fitted geometry, weights, binds,
body clips, on-foot motion, or its catalogue. NumPy is an authoring dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


FREE = [1, 2, 3, 5, 6, 7, 9, 10, 11]
SEED = 3100
EDGE_COUNT = 600
ANGLES = [12, 18, 20, 28]
CONTEXTS = "eloria-assets/source/capes/mounted-fit-contexts.json"


def radial_priorities(vertices: np.ndarray, weights: np.ndarray, edges: np.ndarray,
                      idle: np.ndarray, context: dict, original: np.ndarray) -> tuple[np.ndarray, dict]:
    """Prioritize constraints that first bind near the usable strain boundary."""
    rng = np.random.default_rng(3111)
    free = weights[:, FREE]
    difference = free[edges[:, 0]] - free[edges[:, 1]]
    lengths = np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)
    # Fully cape-owned panel edges have a well-defined common shape frame.
    # Mixed collar constraints are supplied by the actual native pose audit.
    shares = weights[:, :12].sum(1)
    panel = ((lengths > .005) & (np.linalg.norm(difference, axis=1) > .0001)
             & (np.minimum(shares[edges[:, 0]], shares[edges[:, 1]]) > .995))
    indices = np.where(panel)[0]
    delta_weights = difference[panel] / lengths[panel, None]
    body = np.zeros_like(vertices)
    for slot, name in enumerate(["spine_03", "clavicle_l", "clavicle_r", "neck_01", "Head"]):
        matrix = np.array(context["body_skin_matrices"][name]).reshape(4, 4)
        body += (vertices @ matrix[:3, :3].T + matrix[:3, 3]) * weights[:, slot + 12, None]
    pivot = np.array([0., 1.49, -.035])
    bases = []
    for angle in ANGLES:
        radians = np.deg2rad(angle)
        rotation = np.array([[1., 0., 0.], [0., np.cos(radians), -np.sin(radians)],
                             [0., np.sin(radians), np.cos(radians)]])
        cape = (vertices - pivot) @ rotation.T + pivot
        base = body + cape * shares[:, None] + (weights[:, :12] @ idle) @ rotation.T
        bases.append((base[edges[panel, 0]] - base[edges[panel, 1]]) / lengths[panel, None])
    # Keep the ray origin inside each sampled panel constraint. Upper mixed
    # seams are audited independently and never made artificially movable.
    inside = np.logical_and.reduce([(base * base).sum(1) < 1.65 ** 2 - 1e-6 for base in bases])
    indices, delta_weights = indices[inside], delta_weights[inside]
    bases = [base[inside] for base in bases]

    def bounds(base: np.ndarray, targets: np.ndarray) -> np.ndarray:
        result = np.empty((len(indices), len(targets)), dtype="f4")
        constant = (base * base).sum(1) - 1.65 ** 2
        for first in range(0, len(targets), 100):
            response = np.einsum("ei,tij->etj", delta_weights, targets[first:first + 100])
            square = (response * response).sum(2)
            linear = 2 * np.einsum("ei,eti->et", base, response)
            alpha = (-linear + np.sqrt(np.maximum(0, linear * linear - 4 * square * constant[:, None]))) / np.maximum(2 * square, 1e-20)
            alpha[square < 1e-14] = 1e9
            result[:, first:first + 100] = alpha
        return result

    train = rng.normal(size=(1536, 9, 3)) * .3
    train[:768] = (train[:768].reshape(-1, 3, 3, 3) * .25
                   + rng.normal(size=(768, 1, 3, 3)) * np.array([.15, .4, .7])[None, None, :, None]).reshape(-1, 9, 3)
    alpha = np.concatenate([bounds(base, train) for base in bases], axis=1)
    full = alpha.min(0)
    first_edge = alpha.argmin(0)
    global_lookup = {tuple(pair): i for i, pair in enumerate(edges)}
    panel_lookup = {int(value): i for i, value in enumerate(indices)}
    priority, seen = [], set()
    for record in context["observed_critical_edges"]:
        edge = global_lookup[tuple(sorted(record["vertices"]))]
        if edge not in seen:
            priority.append(edge)
            seen.add(edge)
    covered = np.full(len(full), 1e9)
    for edge in priority:
        if edge in panel_lookup:
            covered = np.minimum(covered, alpha[panel_lookup[edge]])
    for _ in range(500):
        target = int(np.argmax(covered / full))
        if covered[target] / full[target] < 1.00001:
            break
        local = int(first_edge[target])
        edge = int(indices[local])
        if edge in seen:
            break
        priority.append(edge)
        seen.add(edge)
        covered = np.minimum(covered, alpha[local])
    radial_count = len(priority)
    for edge in original:
        if int(edge) not in seen:
            priority.append(int(edge))
            seen.add(int(edge))
        if len(priority) >= EDGE_COUNT:
            break
    chosen = np.array(priority[:EDGE_COUNT])
    holdout = rng.normal(size=(384, 9, 3)) * .3
    holdout_bounds = [bounds(base, holdout) for base in bases]
    coverage = {}
    for count in [128, 192, 256, 600]:
        local = [panel_lookup[int(edge)] for edge in chosen[:count] if int(edge) in panel_lookup]
        maximum = []
        for base, limits in zip(bases, holdout_bounds):
            selected_limit = limits[local].min(0)
            for first in range(0, len(holdout), 100):
                response = np.einsum("ei,tij->etj", delta_weights, holdout[first:first + 100])
                point = response * selected_limit[None, first:first + 100, None] + base[:, None, :]
                maximum.extend(np.linalg.norm(point, axis=2).max(0))
        coverage[str(count)] = {
            "holdout_targets": len(maximum),
            "full_panel_maximum_when_selected_edges_reach_1_65": float(max(maximum)),
            "full_panel_p99": float(np.quantile(maximum, .99)),
        }
    return chosen, {
        "angles_degrees": ANGLES,
        "training_targets_per_angle": len(train),
        "fixed_native_pose_critical_edges": len(context["observed_critical_edges"]),
        "critical_and_radial_priority_edges": radial_count,
        "prefixes": coverage,
        "scope": "Fully cape-owned panel and actual native mixed-collar critical edges. Coverage is sampled, not a proof for every body pose; dense runtime qualification remains authoritative.",
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_fit(directory: Path, fit: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    path = directory / fit["file"]
    if sha256(path) != fit["sha256"]:
        raise ValueError(f"Fit payload hash differs: {path.name}")
    data = path.read_bytes()
    vertices, weights, edges, counts = [], [], [], []
    offset = 0
    for surface in fit["surfaces"]:
        def array(key: str) -> np.ndarray:
            descriptor = surface[key]
            dtype = "<i4" if descriptor["type"] == "int32" else "<f4"
            return np.frombuffer(data, dtype=dtype, count=descriptor["count"], offset=descriptor["offset"])

        points = array("positions").reshape(-1, 3).astype(float)
        slots = array("bones").reshape(-1, 8)
        shares = np.zeros((len(points), 17))
        np.add.at(shares, (np.repeat(np.arange(len(points)), 8), slots.ravel()), array("weights"))
        triangles = array("indices").reshape(-1, 3) + offset
        pairs = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        vertices.append(points)
        weights.append(shares)
        edges.append(pairs)
        counts.append(len(points))
        offset += len(points)
    return np.concatenate(vertices), np.concatenate(weights), np.unique(np.concatenate(edges), axis=0), counts


def select_edges(directory: Path, catalog: dict, profile: str, rng: np.random.Generator, context: dict) -> dict:
    fit = catalog["fits"][profile]
    vertices, weights, all_edges, counts = read_fit(directory, fit)
    rest_delta = vertices[all_edges[:, 0]] - vertices[all_edges[:, 1]]
    rest_length = np.linalg.norm(rest_delta, axis=1)
    free_weights = weights[:, FREE]
    difference = free_weights[all_edges[:, 0]] - free_weights[all_edges[:, 1]]
    valid = (rest_length > .005) & (np.linalg.norm(difference, axis=1) > .0001)
    indices = np.where(valid)[0]
    difference = difference[valid]
    lengths = rest_length[valid]
    idle = np.array(catalog["motion"]["profiles"][profile]["idle"]).reshape(12, 3)
    base = vertices + weights[:, :12] @ idle
    base_delta = base[all_edges[valid, 0]] - base[all_edges[valid, 1]]

    # Include coherent cloth motion, independent controls and each single
    # degree of freedom. The same seeded generator continues across profiles.
    targets = rng.normal(size=(3200, 3, 3, 3)) * .12
    common = rng.normal(size=(3200, 1, 3, 3)) * np.array([.18, .45, .75])[None, None, :, None]
    targets[:2200] += common[:2200]
    targets[2200:] *= 3
    targets = targets.reshape(-1, 9, 3).astype("f4")
    targets[:27] = 0
    for component in range(27):
        targets[component].flat[component] = .8

    scores = np.empty((len(indices), len(targets)), dtype="f4")
    for first in range(0, len(targets), 100):
        delta = np.einsum("ei,tij->etj", difference, targets[first:first + 100]) + base_delta[:, None, :]
        scores[:, first:first + 100] = np.linalg.norm(delta, axis=2) / lengths[:, None]
    full_max = scores.max(0)
    full_index = scores.argmax(0)
    selected: list[int] = []
    covered = np.ones(len(targets), dtype="f4")
    used = np.zeros(len(indices), dtype=bool)
    for _ in range(400):
        omitted = full_max - covered
        target = int(np.argmax(omitted))
        edge = int(full_index[target])
        if used[edge] or omitted[target] < 1e-5:
            break
        selected.append(edge)
        used[edge] = True
        covered = np.maximum(covered, scores[edge])
    global_support_count = len(selected)

    centre = (vertices[all_edges[valid, 0]] + vertices[all_edges[valid, 1]]) * .5
    region = np.clip(((1.65 - centre[:, 1]) / .15).astype(int), 0, 9) * 3 + np.clip(((centre[:, 0] + .45) / .3).astype(int), 0, 2)
    frequency = np.bincount(full_index, minlength=len(indices)).astype(float)
    for cell in np.unique(region):
        candidates = np.where(region == cell)[0]
        support = candidates[scores[candidates].argmax(0)]
        frequency += np.bincount(support, minlength=len(indices)) * .1
    for edge in np.argsort(frequency)[::-1]:
        if not used[edge]:
            selected.append(int(edge))
            used[edge] = True
        if len(selected) == EDGE_COUNT:
            break
    global_chosen, radial = radial_priorities(vertices, weights, all_edges, idle, context, indices[np.array(selected)])
    valid_lookup = {int(value): i for i, value in enumerate(indices)}
    chosen = np.array([valid_lookup[int(edge)] for edge in global_chosen if int(edge) in valid_lookup])
    training_gap = full_max - scores[chosen].max(0)
    prefix = np.array([valid_lookup[int(edge)] for edge in global_chosen[:128] if int(edge) in valid_lookup])
    training_prefix_gap = full_max - scores[prefix].max(0)

    holdout = rng.normal(size=(1000, 9, 3)) * .28
    holdout_gap = []
    holdout_prefix_gap = []
    for first in range(0, len(holdout), 100):
        delta = np.einsum("ei,tij->etj", difference, holdout[first:first + 100]) + base_delta[:, None, :]
        score = np.linalg.norm(delta, axis=2) / lengths[:, None]
        holdout_gap.extend(score.max(0) - score[chosen].max(0))
        holdout_prefix_gap.extend(score.max(0) - score[prefix].max(0))
    if len(global_chosen) != EDGE_COUNT:
        raise ValueError(f"Sparse edge count failed: {profile}")
    return {
        "fit_file": fit["file"],
        "fit_sha256": fit["sha256"],
        "vertex_count": len(vertices),
        "surface_vertex_counts": counts,
        "edge_count": len(global_chosen),
        "edges": all_edges[global_chosen].tolist(),
        "radial_boundary_coverage": radial,
        "coverage": {
            "full_unique_mesh_edges": len(all_edges),
            "controllable_edges_over_5mm": len(indices),
            "training_targets": len(targets),
            "global_support_edges": global_support_count,
            "training_maximum_omitted_strain": float(max(training_gap)),
            "holdout_targets": len(holdout),
            "holdout_maximum_omitted_strain": float(max(holdout_gap)),
            "holdout_p99_omitted_strain": float(np.quantile(holdout_gap, .99)),
            "diagnostic_prefix_edges": 128,
            "prefix_128_training_maximum_omitted_strain": float(max(training_prefix_gap)),
            "prefix_128_holdout_maximum_omitted_strain": float(max(holdout_prefix_gap)),
            "prefix_128_holdout_p99_omitted_strain": float(np.quantile(holdout_prefix_gap, .99)),
            "free_control_covariance_condition": float(np.linalg.cond(free_weights.T @ free_weights)),
        },
    }


def prepare(root: Path) -> dict:
    directory = root / "godot-client/data/actors/cape_motion"
    catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    contexts = json.loads((root / CONTEXTS).read_text(encoding="utf-8"))
    rng = np.random.default_rng(SEED)
    return {
        "schema_version": 1,
        "product": "Rabbit Lands",
        "purpose": "Sparse actual-skin edge constraints for mounted cape projection",
        "index_space": "Zero-based vertex indices concatenated in runtime fit surface order",
        "coordinate_space": "Approved native-model coordinates, Y up",
        "analysis_free_controls": FREE,
        "analysis_fixed_controls": [0, 4, 8],
        "analysis_skin_policy": "Edge selection uses the original approved geometry and 17 source palette slots; this is the selection search context, not the final mounted attachment policy.",
        "runtime_policy": {
            "attachment_reference": "Canonical skeleton global-rest palettes; independent of first received gait or action",
            "selected_attachment": "spine_neck; body slot 12 uses spine_03 and its original slot-12 bind; slots 13 through 16 use neck_01 and its original slot-15 bind",
            "alternative_adapter_modes": "head_neck, rigid_neck and rigid_spine remain available for comparison; they are not the selected mounted runtime policy",
            "root_controls": [0, 4, 8],
            "root_reference": "Canonical spine skin frame, with zero root translations",
            "root_frame": "G(current body frames) * inverse(G(canonical body frames)) * canonical spine frame",
            "root_blend": {
                "lateral_neck_fraction": .5,
                "centre_neck_fraction": .5,
                "G": "Normalized quaternion blend of Spine and Neck, translated to preserve their blended transformed material centroid",
                "material_centroid": "Mounted rest vertex centroid weighted by that root control, plus its idle translation",
                "canonical_normalization": "The same fraction and material centroid define both current G and canonical G; the canonical root frame remains exactly the source spine frame",
            },
            "free_lower_controls": FREE,
            "mounted_variant": "Pure rebasing preserves the canonical source rendered reference under the Spine/Neck attachment. Runtime-selected shoulder relief then deliberately adds bounded clearance; it is an intentional fit change, separate from rebase precision.",
            "intentional_relief": {
                "wardrobe": {"posterior_m": .008, "upward_m": 0.0},
                "armour": {"posterior_m": .02, "upward_m": .02},
                "coordinate_space": "Original approved native anatomical vertex positions",
                "posterior_direction": "-Z",
                "upward_direction": "+Y",
                "interpolation": "Quintic smootherstep; normals use the warp inverse transpose and tangents its forward Jacobian",
                "posterior_height_range_m": [1.22, 1.38],
                "central_pin_height_range_m": [1.44, 1.53],
                "central_pin_abs_x_range_m": [.035, .11],
                "upward_height_range_m": [1.36, 1.50],
                "upward_abs_x_range_m": [.05, .12],
                "fixed_neckline": "abs(source.x) <= .035 and source.y >= 1.53",
                "fixed_lower_panel": "source.y <= 1.22",
                "fixed_scope": "These regions receive zero deliberate relief; they are not fixed in world space. The neckline follows its anatomical neck skin frame during motion.",
            },
            "error_contract": {
                "pure_rebase_error_m": "Precision of the canonical rebase before intentional relief",
                "reference_error_m": "Precision against the canonical reference plus the explicit intentional relief target",
                "no_relief_default": "The adapter default remains zero relief and preserves the original rendered reference",
            },
            "preserved": "Original eight influence values and bone indices, UVs, topology, materials and body skeleton poses",
            "edge_denominators": "Original approved source positions, not rebased mounted positions",
            "on_foot": "Original approved mesh, skin and motion are restored unchanged",
            "validation": "Dense native geometry qualification of the selected mounted attachment remains authoritative",
        },
        "recipe": {
            "tool": "eloria-assets/tools/prepare_mounted_cape_support_edges.py",
            "tool_sha256": sha256(Path(__file__)),
            "numpy_version": np.__version__,
            "random_seed": SEED,
            "algorithm": "Actual native critical edges, minimax radial support near the 1.65 strain boundary across four cape angles, then broad control-target and material-region support",
            "body_contexts": CONTEXTS,
            "body_contexts_sha256": sha256(root / CONTEXTS),
            "profiles_in_generator_order": ["wardrobe", "armour"],
            "qualification_limit": "Sampling coverage is measured on original approved rest plus idle data with the listed analysis controls. The selected rigid mounted attachment is a separate variant; this selection does not certify arbitrary body poses, full-mesh strain or clearance. Dense native runtime checks remain required.",
        },
        "profiles": {profile: select_edges(directory, catalog, profile, rng, contexts["profiles"][profile]) for profile in ["wardrobe", "armour"]},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute and verify the tracked selection without writing")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, help="Write a separate candidate selection for qualification")
    args = parser.parse_args()
    destination = args.output or args.root / "godot-client/data/actors/cape_motion/mounted-support-edges.json"
    expected = json.dumps(prepare(args.root), indent=2) + "\n"
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != expected:
            raise SystemExit("Mounted cape support edges differ; regenerate and requalify")
        print("Mounted cape support edges match both frozen fit payloads and coverage checks")
    else:
        destination.write_text(expected, encoding="utf-8")
        print(f"Prepared {destination.name}: two profiles, 600 edges each")


if __name__ == "__main__":
    main()
