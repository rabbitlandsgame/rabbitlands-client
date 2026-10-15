#!/usr/bin/env python3
"""Compare a baked Sunmane snapshot with the certified migration inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


TRANSLATION = np.array([1200.0, 0.0, 720.0])
SECTIONS = {
    "spawnPoints": "spawns", "portals": "portals",
    "interactives": "interactives", "landmarks": "landmarks",
    "harvestables": "harvestables", "npcMarkers": "npcMarkers",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(value: list[float]) -> np.ndarray:
    return np.array(value, dtype=float).reshape(4, 4).T


def max_polyline_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Symmetric point-to-segment Hausdorff distance in X/Z."""
    def directed(points, line):
        maximum = 0.0
        for point in points:
            starts = line[:-1]
            delta = line[1:] - starts
            lengths = np.sum(delta * delta, axis=1)
            amount = np.divide(np.sum((point - starts) * delta, axis=1), lengths,
                               out=np.zeros_like(lengths), where=lengths > 1e-12)
            nearest = starts + np.clip(amount, 0.0, 1.0)[:, None] * delta
            maximum = max(maximum, float(np.min(np.linalg.norm(nearest - point, axis=1))))
        return maximum
    return max(directed(first, second), directed(second, first))


def max_profile_difference(source: np.ndarray, sampled: np.ndarray) -> float:
    maximum = 0.0
    starts = sampled[:-1]
    delta = sampled[1:] - starts
    lengths = np.sum(delta[:, [0, 2]] * delta[:, [0, 2]], axis=1)
    for point in source:
        amount = np.divide(
            np.sum((point[[0, 2]] - starts[:, [0, 2]]) * delta[:, [0, 2]], axis=1),
            lengths, out=np.zeros_like(lengths), where=lengths > 1e-12)
        amount = np.clip(amount, 0.0, 1.0)
        nearest = starts + amount[:, None] * delta
        index = int(np.argmin(np.linalg.norm(nearest[:, [0, 2]] - point[[0, 2]], axis=1)))
        maximum = max(maximum, abs(float(nearest[index, 1] - point[1])))
    return maximum


def route_report(snapshot: dict, roads_path: Path, plan_path: Path) -> dict:
    legacy_roads = {record["id"]: record for record in
                    json.loads(roads_path.read_text(encoding="utf-8"))["roads"]}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    river = next(record for record in plan["rivers"] if record["id"] == "southern_river")
    source = {}
    for identity in snapshot["replacements"]["routeIds"]:
        points = np.array(legacy_roads[identity]["points"], dtype=float)
        points[:, [0, 2]] -= TRANSLATION[[0, 2]]
        source[identity] = points
    source["southern_river"] = np.array(
        [[point[0] - TRANSLATION[0], point[2], point[1] - TRANSLATION[2]]
         for point in river["points"]], dtype=float)
    actual = {record["id"]: np.array([point["position"] for point in record["points"]],
                                      dtype=float) for record in snapshot["paths"]}
    records = []
    for identity in sorted(source):
        expected = source[identity]
        observed = actual[identity]
        records.append({
            "id": identity,
            "sourcePoints": len(expected),
            "snapshotPoints": len(observed),
            "maxXzPolylineMetres": max_polyline_distance(
                expected[:, (0, 2)], observed[:, (0, 2)]),
            "maxEndpointMetres": max(
                float(np.linalg.norm(expected[0] - observed[0])),
                float(np.linalg.norm(expected[-1] - observed[-1]))),
            "maxSourcePointHeightMetres": max_profile_difference(expected, observed),
        })
    return {
        "sourceIds": len(source), "snapshotIds": len(actual),
        "missingIds": sorted(set(source) - set(actual)),
        "unexpectedIds": sorted(set(actual) - set(source)),
        "maxXzPolylineMetres": max(record["maxXzPolylineMetres"] for record in records),
        "maxEndpointMetres": max(record["maxEndpointMetres"] for record in records),
        "maxSourcePointHeightMetres": max(
            record["maxSourcePointHeightMetres"] for record in records),
        "records": records,
    }


def object_report(snapshot: dict, source_world: Path, source_manifest: dict,
                  glb_reader, importer) -> dict:
    document, _ = glb_reader.load(source_world)
    matrices, _ = glb_reader.hierarchy(document)
    objects, _ = importer.object_records(
        document, matrices, set(source_manifest["collision"]["nodeNames"]))
    expected = {record["id"]: record for record in objects}
    actual = {record["id"]: record for record in snapshot["objects"]}
    errors = []
    xz_errors = []
    y_shifts = []
    delta_metadata_errors = []
    collision_mismatches = []
    for identity in sorted(set(expected) & set(actual)):
        expected_matrix = expected[identity]["matrix"]
        actual_matrix = matrix(actual[identity]["matrix"])
        errors.append(float(np.max(np.abs(expected_matrix[:3, :3] -
                                          actual_matrix[:3, :3]))))
        xz_errors.append(float(np.max(np.abs(
            expected_matrix[[0, 2], 3] - actual_matrix[[0, 2], 3]))))
        y_shift = float(actual_matrix[1, 3] - expected_matrix[1, 3])
        y_shifts.append(y_shift)
        saved_delta = actual[identity].get("metadata", {}).get("migrationYDelta")
        if saved_delta is not None:
            delta_metadata_errors.append(abs(y_shift - float(saved_delta)))
        if expected[identity]["collisionRole"] != actual[identity]["collisionRole"]:
            collision_mismatches.append(identity)
    return {
        "sourceIds": len(expected), "snapshotIds": len(actual),
        "missingIds": sorted(set(expected) - set(actual)),
        "unexpectedIds": sorted(set(actual) - set(expected)),
        "maxBasisElementError": max(errors, default=math.inf),
        "maxXzPositionErrorMetres": max(xz_errors, default=math.inf),
        "verticalMigration": {
            "minimumMetres": min(y_shifts, default=math.nan),
            "maximumMetres": max(y_shifts, default=math.nan),
            "meanAbsoluteMetres": float(np.mean(np.abs(y_shifts)))
            if y_shifts else math.nan,
            "maxSavedMetadataErrorMetres": max(delta_metadata_errors, default=math.nan),
        },
        "collisionRoleMismatches": collision_mismatches,
    }


def normalized_gameplay(record: dict, section: str) -> dict:
    output = dict(record)
    output.pop("serverTile", None)
    output.pop("center", None)
    output.pop("assetId", None)
    if "position" not in output and "center" in record:
        output["position"] = record["center"]
    if "label" not in output and "name" in output:
        output["label"] = output.pop("name")
    elif output.get("name") == output.get("label"):
        output.pop("name", None)
    if output.get("key") == "":
        output.pop("key")
    if section == "spawnPoints" and output.get("default") is False:
        output.pop("default")
    if section != "spawnPoints":
        output.pop("default", None)
        output.pop("facing", None)
    return output


def values_equal(left, right) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool) and \
            isinstance(right, (int, float)) and not isinstance(right, bool):
        return abs(float(left) - float(right)) <= 2e-5
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return all(values_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict) and set(left) == set(right):
        return all(values_equal(left[key], right[key]) for key in left)
    return left == right


def field_mismatches(expected: dict, actual: dict) -> list[str]:
    differences = []
    for key in sorted(set(expected) | set(actual)):
        if key in ("assetId", "position"):
            continue
        left = expected.get(key, "<missing>")
        right = actual.get(key, "<missing>")
        if not values_equal(left, right):
            differences.append(key)
    return differences


def gameplay_section_report(expected_records: list[dict], actual_records: list[dict],
                            section: str) -> dict:
    expected = {record["id"]: normalized_gameplay(record, section)
                for record in expected_records}
    actual = {record["id"]: normalized_gameplay(record, section)
              for record in actual_records}
    common = set(expected) & set(actual)
    mismatches = {identity: field_mismatches(expected[identity], actual[identity])
                  for identity in sorted(common)}
    mismatches = {key: value for key, value in mismatches.items() if value}
    position_errors = []
    xz_errors = []
    y_shifts = []
    for identity in common:
        if "position" in expected[identity] and "position" in actual[identity]:
            source_position = np.array(expected[identity]["position"], dtype=float)
            authored_position = np.array(actual[identity]["position"], dtype=float)
            position_errors.append(float(np.linalg.norm(source_position - authored_position)))
            xz_errors.append(float(np.linalg.norm(
                source_position[[0, 2]] - authored_position[[0, 2]])))
            y_shifts.append(float(authored_position[1] - source_position[1]))
    return {
        "sourceIds": len(expected), "snapshotIds": len(actual),
        "sourceIdTypes": sorted({type(record["id"]).__name__ for record in expected_records}),
        "snapshotIdTypes": sorted({type(record["id"]).__name__ for record in actual_records}),
        "missingIds": sorted(set(expected) - set(actual)),
        "unexpectedIds": sorted(set(actual) - set(expected)),
        "maxPositionMetres": max(position_errors, default=math.inf),
        "maxPositionXzMetres": max(xz_errors, default=math.inf),
        "verticalMigration": {
            "minimumMetres": min(y_shifts, default=math.nan),
            "maximumMetres": max(y_shifts, default=math.nan),
            "meanAbsoluteMetres": float(np.mean(np.abs(y_shifts)))
            if y_shifts else math.nan,
        },
        "fieldMismatches": mismatches,
    }


def gameplay_report(snapshot: dict, source: dict) -> dict:
    reports = {}
    for snapshot_key, source_key in SECTIONS.items():
        reports[snapshot_key] = gameplay_section_report(
            source.get(source_key, ()), snapshot["gameplay"][snapshot_key], snapshot_key)
    expected_records = source.get("ambientPopulation", {}).get("groups", ())
    reports["ambientPopulation"] = gameplay_section_report(
        expected_records, snapshot["gameplay"]["ambientPopulation"],
        "ambientPopulation")
    return reports


def terrain_vertices(document: dict, body: bytes, glb_reader) -> dict[tuple[int, int], list[float]]:
    matrices, _ = glb_reader.hierarchy(document)
    result: dict[tuple[int, int], list[float]] = {}
    for index, node in enumerate(document["nodes"]):
        if not node.get("name", "").startswith("Terrain_") or "mesh" not in node:
            continue
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            vertices = glb_reader.accessor(
                document, body, primitive["attributes"]["POSITION"])
            vertices = vertices @ matrices[index][:3, :3].T + matrices[index][:3, 3]
            for x, y, z in vertices:
                x_index = round((float(x) + 194.0) / 2.0)
                z_index = round((float(z) + 500.0) / 2.0)
                expected_x = -194.0 + x_index * 2.0
                expected_z = -500.0 + z_index * 2.0
                if (0 <= x_index < 397 and 0 <= z_index < 397 and
                        abs(float(x) - expected_x) < 1e-4 and
                        abs(float(z) - expected_z) < 1e-4):
                    result.setdefault((x_index, z_index), []).append(float(y))
    return result


def sample_grid(values, x: float, z: float):
    fx = (x + 194.0) / 2.0
    fz = (z + 500.0) / 2.0
    x0, z0 = math.floor(fx), math.floor(fz)
    if not (0 <= x0 < 396 and 0 <= z0 < 396):
        return None
    tx, tz = fx - x0, fz - z0
    corners = [(x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1)]
    heights = []
    for key in corners:
        if isinstance(values, dict):
            if key not in values:
                return None
            heights.append(max(values[key]))
        else:
            heights.append(float(values[key[1] * 397 + key[0]]))
    return (heights[0] * (1.0 - tx) * (1.0 - tz) +
            heights[1] * tx * (1.0 - tz) +
            heights[2] * (1.0 - tx) * tz + heights[3] * tx * tz)


def shift_summary(points: list[tuple[str, float, float]], published: dict,
                  resolved: np.ndarray) -> dict:
    records = []
    for identity, x, z in points:
        old = sample_grid(published, x, z)
        new = sample_grid(resolved, x, z)
        if old is not None and new is not None:
            records.append((float(new - old), identity))
    absolute = np.abs([record[0] for record in records])
    most_raised = max(records, default=(math.nan, ""))
    most_lowered = min(records, default=(math.nan, ""))
    return {
        "matched": len(records),
        "meanAbsoluteMetres": float(np.mean(absolute)) if len(absolute) else math.nan,
        "p95AbsoluteMetres": float(np.percentile(absolute, 95)) if len(absolute) else math.nan,
        "over25cm": int(np.count_nonzero(absolute > 0.25)),
        "over1m": int(np.count_nonzero(absolute > 1.0)),
        "maximumBurialMetres": most_raised[0], "maximumBurialId": most_raised[1],
        "maximumFloatMetres": -most_lowered[0], "maximumFloatId": most_lowered[1],
    }


def residual_summary(records: list[tuple[str, float]]) -> dict:
    values = np.array([value for _, value in records], dtype=float)
    if len(values) == 0:
        return {"matched": 0, "meanAbsoluteMetres": math.nan,
                "p95AbsoluteMetres": math.nan, "maxAbsoluteMetres": math.nan,
                "maxAbsoluteId": ""}
    index = int(np.argmax(np.abs(values)))
    return {
        "matched": len(records),
        "meanAbsoluteMetres": float(np.mean(np.abs(values))),
        "p95AbsoluteMetres": float(np.percentile(np.abs(values), 95)),
        "maxAbsoluteMetres": float(abs(values[index])),
        "maxAbsoluteId": records[index][0],
    }


def terrain_report(snapshot: dict, source_world: Path, source_manifest: dict,
                   snapshot_dir: Path, glb_reader, importer) -> dict:
    terrain = snapshot["terrain"]
    base = np.fromfile(snapshot_dir / terrain["baseHeights"]["path"], dtype="<f4")
    resolved = np.fromfile(snapshot_dir / terrain["resolvedHeights"]["path"], dtype="<f4")
    document, body = glb_reader.load(source_world)
    published = terrain_vertices(document, body, glb_reader)
    source_values = []
    resolved_values = []
    seam_spread = 0.0
    for (x_index, z_index), values in published.items():
        seam_spread = max(seam_spread, max(values) - min(values))
        source_values.append(float(np.mean(values)))
        resolved_values.append(float(resolved[z_index * 397 + x_index]))
    delta = np.array(resolved_values) - np.array(source_values)
    authored = resolved.astype(float) - base.astype(float)
    absolute = np.abs(delta)
    object_points = [(record["id"], float(record["matrix"][12]),
                      float(record["matrix"][14])) for record in snapshot["objects"]]
    gameplay_points = []
    for section in snapshot["gameplay"].values():
        gameplay_points.extend((str(record["id"]), float(record["position"][0]),
                                float(record["position"][2])) for record in section)
    source_matrices, _ = glb_reader.hierarchy(document)
    source_objects, _ = importer.object_records(
        document, source_matrices, set(source_manifest["collision"]["nodeNames"]))
    source_object_by_id = {record["id"]: record for record in source_objects}
    actual_object_by_id = {record["id"]: record for record in snapshot["objects"]}
    object_residuals = []
    object_shifts = {}
    for identity in sorted(set(source_object_by_id) & set(actual_object_by_id)):
        source_matrix = source_object_by_id[identity]["matrix"]
        actual_matrix = matrix(actual_object_by_id[identity]["matrix"])
        actual_shift = float(actual_matrix[1, 3] - source_matrix[1, 3])
        object_shifts[identity] = actual_shift
        old = sample_grid(published, float(source_matrix[0, 3]), float(source_matrix[2, 3]))
        new = sample_grid(resolved, float(source_matrix[0, 3]), float(source_matrix[2, 3]))
        if old is not None and new is not None:
            object_residuals.append((identity, actual_shift - float(new - old)))

    source_gameplay = {}
    for snapshot_key, source_key in SECTIONS.items():
        source_gameplay[snapshot_key] = {
            str(record["id"]): record for record in source_manifest.get(source_key, ())}
    source_gameplay["ambientPopulation"] = {
        str(record["id"]): record
        for record in source_manifest.get("ambientPopulation", {}).get("groups", ())}
    gameplay_residuals = []
    linked_gameplay = 0
    independently_grounded = 0
    for section_name, section in snapshot["gameplay"].items():
        expected_section = source_gameplay[section_name]
        for record in section:
            identity = str(record["id"])
            if identity not in expected_section:
                continue
            source_record = expected_section[identity]
            source_position = source_record.get("position", source_record.get("center"))
            actual_shift = float(record["position"][1] - source_position[1])
            followed = str(record.get("assetId", ""))
            if followed and followed in object_shifts:
                expected_shift = object_shifts[followed]
                linked_gameplay += 1
            else:
                old = sample_grid(published, float(source_position[0]),
                                  float(source_position[2]))
                new = sample_grid(resolved, float(source_position[0]),
                                  float(source_position[2]))
                if old is None or new is None:
                    expected_shift = 0.0
                else:
                    expected_shift = float(new - old)
                    independently_grounded += 1
            gameplay_residuals.append((f"{section_name}/{identity}",
                                       actual_shift - expected_shift))
    return {
        "sourceWorldSha256": sha256(source_world),
        "matchedPublishedGridSamples": len(delta),
        "publishedSeamMaxSpreadMetres": seam_spread,
        "resolvedVsPublished": {
            "meanMetres": float(np.mean(delta)),
            "meanAbsoluteMetres": float(np.mean(absolute)),
            "rootMeanSquareMetres": float(np.sqrt(np.mean(delta * delta))),
            "p95AbsoluteMetres": float(np.percentile(absolute, 95)),
            "maxAbsoluteMetres": float(np.max(absolute)),
        },
        "resolvedVsNaturalBase": {
            "changedSamplesOver1mm": int(np.count_nonzero(np.abs(authored) > 0.001)),
            "meanAbsoluteMetres": float(np.mean(np.abs(authored))),
            "maxAbsoluteMetres": float(np.max(np.abs(authored))),
        },
        "groundingShiftAtObjects": shift_summary(object_points, published, resolved),
        "groundingShiftAtGameplay": shift_summary(gameplay_points, published, resolved),
        "postMigrationGrounding": {
            "objects": residual_summary(object_residuals),
            "gameplay": residual_summary(gameplay_residuals),
            "linkedGameplay": linked_gameplay,
            "independentlyGroundedGameplay": independently_grounded,
        },
    }


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--roads", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "eloria-assets/maps/nymara-regions/_toolkit"))
    sys.path.insert(0, str(repo / "godot-client/tools"))
    import glb_reader
    import import_sunmane_authoring as importer
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    report = {
        "schema": "eloria-sunmane-authoring-migration-compare-v1",
        "inputs": {key: {"path": str(path), "sha256": sha256(path)} for key, path in {
            "snapshot": args.snapshot, "sourceWorld": args.source_world,
            "sourceManifest": args.source_manifest, "roads": args.roads,
            "plan": args.plan,
        }.items()},
        "objects": object_report(snapshot, args.source_world, source_manifest,
                                  glb_reader, importer),
        "paths": route_report(snapshot, args.roads, args.plan),
        "gameplay": gameplay_report(snapshot, source_manifest),
        "terrain": terrain_report(snapshot, args.source_world, source_manifest,
                                  args.snapshot.parent, glb_reader, importer),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output),
                      "terrainMatched": report["terrain"]["matchedPublishedGridSamples"],
                      "maxObjectBasisError": report["objects"]["maxBasisElementError"],
                      "maxObjectXzError": report["objects"]["maxXzPositionErrorMetres"],
                      "maxPathXz": report["paths"]["maxXzPolylineMetres"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
