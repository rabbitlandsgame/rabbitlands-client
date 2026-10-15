#!/usr/bin/env python3
"""Deterministically migrate certified Amethyst Barrens into authoring.

This adapter deliberately preserves the eight bespoke bridge/ferry assemblies
as ordinary editable assets.  Their visual, solid and Walk_* descendants move
together under one saved AssetControl transform; no generic bridge geometry is
substituted for the published structures.
"""
from __future__ import annotations

import argparse
import copy
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys

import numpy as np

from import_sunmane_authoring import (
    clean_extras, gd_float, godot_string, godot_value, node_name, repo_path,
    sha256, slug, transform3d, write_curve, write_surface,
)


REGION_ID = "amethyst_barrens"
IMMUTABLE_PROFILE_PREFIX = (
    "eloria-assets/maps/nymara-regions/_continent/legacy-server-profile/"
)
TRANSLATION = np.array([950.0, 0.0, 400.0])
GRID_SHAPE = (370, 370)
GRID_BYTES = GRID_SHAPE[0] * GRID_SHAPE[1] * 4
OWNED_ROUTE_IDS = tuple(sorted((
    "amethyst_barrens--whitehorn_range-amethyst_barrens",
    "amethyst_barrens--mirrorhold-amethyst_barrens",
    "amethyst_barrens--sunmane_steppe-amethyst_barrens",
    "door-amethyst_barrens-resonant-vault-stair",
    "door-amethyst_barrens-geode-hollow-mouth",
    "door-amethyst_barrens-shardworks-headframe",
    "door-amethyst_barrens-storm-barrow-stair",
    "door-amethyst_barrens-sour-cut-mouth",
    "door-amethyst_barrens-measure-house-door",
    "door-amethyst_barrens-counting-house-door",
    *(f"discovery-amethyst_barrens-{number}" for number in range(699, 709)),
    "discovery-amethyst_barrens-710",
    "discovery-amethyst_barrens-1276",
)))
REQUIRED_ROUTE_IDS = tuple(identity for identity in OWNED_ROUTE_IDS
                           if not identity.startswith("discovery-"))
GAMEPLAY = (
    ("spawnPoints", "Spawns", "spawn"),
    ("portals", "Portals", "portal"),
    ("interactives", "Interactives", "interactive"),
    ("landmarks", "Landmarks", "landmark"),
    ("harvestables", "Harvestables", "harvestable"),
    ("npcMarkers", "NpcMarkers", "npc_marker"),
)
OUTPUT_SECTIONS = {
    "spawn": "spawnPoints", "portal": "portals",
    "interactive": "interactives", "landmark": "landmarks",
    "harvestable": "harvestables", "npc_marker": "npcMarkers",
    "ambient_population": "ambientPopulation", "runtime_point": "runtimePoints",
}
RUNTIME_GROUPS = {
    "return": "Returns", "interactive": "Interactions", "npc": "Npcs",
    "harvest": "Harvestables", "spawn": "CreatureSpawns",
    "territory": "TerritoryPoints",
}
CROSSING_ASSETS = {
    "bridge_massif": ("Landmark_SurveyedBridge_0",
                       "Walk_Landmark_SurveyedBridge_0__alpine_gravel"),
    "bridge_basin": ("Landmark_SurveyedBridge_1",
                      "Walk_Landmark_SurveyedBridge_1__alpine_gravel"),
    "bridge_river_north": ("Landmark_SurveyedBridge_2",
                            "Walk_Landmark_SurveyedBridge_2__alpine_gravel"),
    "bridge_river_south": ("Landmark_SurveyedBridge_3",
                            "Walk_Landmark_SurveyedBridge_3__alpine_gravel"),
    "bridge_east": ("Landmark_SurveyedBridge_4",
                     "Walk_Landmark_SurveyedBridge_4__alpine_gravel"),
    "bridge_gully_west": ("Landmark_SurveyedBridge_5",
                           "Walk_Landmark_SurveyedBridge_5__alpine_gravel"),
    "bridge_gully_north": ("Landmark_SurveyedBridge_6",
                            "Walk_Landmark_SurveyedBridge_6__alpine_gravel"),
    "ferry_jetty": ("Landmark_SurveyedBridge_7",
                     "Walk_Landmark_SurveyedBridge_7__timber_grey"),
}


def descendants(document: dict, root: int) -> list[int]:
    result, stack = [], [root]
    while stack:
        index = stack.pop()
        result.append(index)
        stack.extend(reversed(document["nodes"][index].get("children", ())))
    return result


def subtree_signature(document: dict, index: int, *, root: bool = True):
    node = document["nodes"][index]
    transform = () if root else tuple(
        (field, tuple(node[field]) if isinstance(node.get(field), list) else node.get(field))
        for field in ("matrix", "translation", "rotation", "scale") if field in node)
    return (
        node.get("mesh"), node.get("camera"), node.get("skin"), transform,
        tuple((document["nodes"][child].get("name", ""),
               subtree_signature(document, child, root=False))
              for child in node.get("children", ())),
    )


def object_records(document: dict, matrices: dict[int, np.ndarray], library: dict):
    by_name = defaultdict(list)
    for index, node in enumerate(document.get("nodes", ())):
        by_name[node.get("name", "")].append(index)
    crossings = {entry["id"]: entry for entry in library["crossings"]}
    crossing_by_node = {node: (identity, walk) for identity, (node, walk)
                        in CROSSING_ASSETS.items()}
    if set(crossings) != set(CROSSING_ASSETS):
        raise ValueError("Certified crossing identities differ from the eight reviewed assemblies")
    records, families = [], defaultdict(list)
    for placement in library["placements"]:
        identity = str(placement["node"])
        matches = by_name.get(identity, ())
        if len(matches) != 1:
            raise ValueError(f"Placement {identity!r} resolves to {len(matches)} source nodes")
        root = matches[0]
        matrix = np.asarray(matrices[root], dtype=float)
        angle = float(placement.get("rotation_y", 0.0))
        scale = float(placement.get("scale", 1.0))
        cosine, sine = math.cos(angle), math.sin(angle)
        declared = np.eye(4)
        declared[:3, :3] = scale * np.asarray(
            [[cosine, 0.0, sine], [0.0, 1.0, 0.0], [-sine, 0.0, cosine]])
        declared[:3, 3] = np.asarray(placement["position"], float)
        if not np.allclose(matrix, declared, rtol=0.0, atol=1e-8):
            raise ValueError(f"{identity}: source GLB transform disagrees with certified placement")
        signature = subtree_signature(document, root)
        family = f"{slug(str(placement.get('mesh', identity)))}-{hashlib.sha256(repr(signature).encode()).hexdigest()[:12]}"
        metadata = {key: copy.deepcopy(value) for key, value in placement.items()
                    if key not in ("node", "position", "collides", "walk_surface") and value is not None}
        record = {
            "id": identity, "nodeName": identity, "sourceRoot": root,
            "family": family, "matrix": matrix,
            "collisionRole": "solid" if placement.get("collides") else
                             "walk_surface" if placement.get("walk_surface") else "none",
            "metadata": metadata,
        }
        if identity in crossing_by_node:
            crossing_id, walk_node = crossing_by_node[identity]
            names = {document["nodes"][item].get("name") for item in descendants(document, root)}
            if walk_node not in names:
                raise ValueError(f"{crossing_id}: reviewed walk node {walk_node!r} is absent")
            inverse = np.linalg.inv(matrix)
            local_endpoints = []
            for endpoint in crossings[crossing_id]["endpoints"]:
                local_endpoints.append((inverse @ np.asarray([*endpoint, 1.0]))[:3].tolist())
            record["metadata"]["authoredCrossing"] = {
                "id": crossing_id, "walkNode": walk_node,
                "localEndpoints": local_endpoints,
            }
            restored = [
                (matrix @ np.asarray([*point, 1.0]))[:3].tolist()
                for point in local_endpoints
            ]
            if not np.allclose(restored, crossings[crossing_id]["endpoints"],
                               rtol=0.0, atol=1e-8):
                raise ValueError(f"{crossing_id}: local endpoint transform does not restore")
        records.append(record)
        families[family].append(record)
    if len(records) != 378 or len({entry["id"] for entry in records}) != 378:
        raise ValueError("Certified Amethyst source must contain 378 unique placements")
    return sorted(records, key=lambda entry: entry["id"]), families


def final_object_records(content, objects: tuple[dict, ...], library: dict):
    """Convert exact post-composition objects into saved editable controls."""
    import glb_reader
    crossings = {entry["id"]: entry for entry in library["crossings"]}
    crossing_by_node = {node: (identity, walk) for identity, (node, walk)
                        in CROSSING_ASSETS.items()}
    if set(crossings) != set(CROSSING_ASSETS):
        raise ValueError("Certified crossing identities differ from the eight reviewed assemblies")
    records, families = [], defaultdict(list)
    for obj in objects:
        source_region = obj.get("libraryRegion", REGION_ID)
        if source_region != REGION_ID:
            raise ValueError(
                f"{obj.get('node')}: final foreign-source object needs an explicit region adapter")
        roots = list(obj.get("indices", [obj["index"]]))
        if len(roots) != 1:
            raise ValueError(
                f"{obj.get('node')}: final companion roots need grouped prototype capture")
        document, _body = content.documents[source_region]
        matrices, _parents = glb_reader.hierarchy(document)
        root = roots[0]
        identity = str(obj["node"])
        matrix = np.asarray(matrices[root], dtype=float).copy()
        matrix[:3, 3] += np.asarray(obj["shift"], dtype=float) - TRANSLATION
        signature = subtree_signature(document, root)
        family = f"{slug(identity)}-{hashlib.sha256(repr(signature).encode()).hexdigest()[:12]}"
        source = obj.get("source", {})
        metadata = {key: copy.deepcopy(value) for key, value in source.items()
                    if key not in ("node", "position", "collides", "walk_surface") and value is not None}
        metadata["composedSourceRegion"] = source_region
        record = {
            "id": identity, "nodeName": identity, "sourceRoot": root,
            "sourceRegion": source_region, "family": family, "matrix": matrix,
            "collisionRole": "solid" if obj.get("collides") else
                             "walk_surface" if obj.get("walk") else "none",
            "metadata": metadata,
        }
        if identity in crossing_by_node:
            crossing_id, walk_node = crossing_by_node[identity]
            names = {document["nodes"][item].get("name")
                     for item in descendants(document, root)}
            if walk_node not in names:
                raise ValueError(f"{crossing_id}: reviewed walk node {walk_node!r} is absent")
            inverse = np.linalg.inv(np.asarray(matrices[root], dtype=float))
            local_endpoints = [
                (inverse @ np.asarray([*endpoint, 1.0]))[:3].tolist()
                for endpoint in crossings[crossing_id]["endpoints"]
            ]
            record["metadata"]["authoredCrossing"] = {
                "id": crossing_id, "walkNode": walk_node,
                "localEndpoints": local_endpoints,
            }
        records.append(record)
        families[family].append(record)
    if len(records) != 124 or len({entry["id"] for entry in records}) != 124:
        raise ValueError(
            f"Certified final Amethyst composition must contain 124 unique objects, got {len(records)}")
    return sorted(records, key=lambda entry: entry["id"]), families


def write_prototypes(document: dict, body: bytes, families: dict, output: Path,
                     resource_root: str, scene_io) -> dict[str, dict]:
    prototype_dir = output / "assets/prototypes"
    texture_dir = output / "assets/textures"
    prototype_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for family in sorted(families):
        representative = min(families[family], key=lambda entry: entry["id"])
        private = copy.deepcopy(document)
        root = representative["sourceRoot"]
        for field in ("matrix", "translation", "rotation", "scale"):
            private["nodes"][root].pop(field, None)
        target = prototype_dir / f"{family}.glb"
        exporter = scene_io.Exporter(target, shared_images=texture_dir)
        exporter.add(private, body, [root], root_names={root: family})
        stats = exporter.write()
        records[family] = {
            "path": f"{resource_root}/assets/prototypes/{target.name}",
            "sha256": sha256(target), "representative": representative["id"],
            "instances": len(families[family]), "stats": stats,
        }
    return records


def prune_generated_assets(output: Path, prototypes: dict[str, dict]) -> None:
    """Remove only obsolete adapter-owned prototype and shared-image files."""
    keep_prototypes = {Path(record["path"]).name for record in prototypes.values()}
    keep_textures = {
        Path(relative).name
        for record in prototypes.values()
        for relative in record["stats"].get("externalResources", {})
    }
    for path in (output / "assets/prototypes").glob("*.glb"):
        if path.name not in keep_prototypes:
            path.unlink()
            path.with_name(path.name + ".import").unlink(missing_ok=True)
    for path in (output / "assets/textures").iterdir():
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg") \
                and path.name not in keep_textures:
            path.unlink()
            path.with_name(path.name + ".import").unlink(missing_ok=True)
    # A prior forced bootstrap may already have removed the source before this
    # cleanup learned about Godot sidecars.  Only these adapter-owned folders
    # are considered, and an import sidecar survives exactly when its sibling
    # source is still part of the current capture.
    for folder in (output / "assets/prototypes", output / "assets/textures"):
        for sidecar in folder.glob("*.import"):
            source = sidecar.with_name(sidecar.name.removesuffix(".import"))
            if not source.is_file():
                sidecar.unlink()


def path_records(roads_document: dict, output: Path, resource_root: str) -> list[dict]:
    roads = {entry["id"]: entry for entry in roads_document["roads"]}
    if missing := sorted(set(OWNED_ROUTE_IDS) - roads.keys()):
        raise ValueError(f"Published roads are missing Amethyst-owned routes: {missing}")
    result = []
    for identity in OWNED_ROUTE_IDS:
        source = roads[identity]
        points = [[float(point[0] - TRANSLATION[0]), float(point[1]),
                   float(point[2] - TRANSLATION[2])] for point in source["points"]]
        curve = output / "paths" / f"{slug(identity)}.tres"
        write_curve(curve, points)
        result.append({
            "id": identity, "points": points,
            "width": float(source["width"]) * 2.0,
            "routingRole": "required" if identity in REQUIRED_ROUTE_IDS else "decorative",
            "curve": f"{resource_root}/paths/{curve.name}",
            # The published Amethyst ground already contains its legacy global
            # road and crossing settlement.  Preserve that certified heightfield
            # as independent editable terrain and let imported roads follow it.
            # New roads retain the framework default (terrainConform=true), and
            # an imported road may opt into shaping explicitly in the inspector.
            "properties": {"terrainConform": False, "terrainFeather": 2.0},
        })
    return result


def marker_records(manifest: dict, objects: list[dict]) -> list[dict]:
    by_node = {entry["nodeName"]: entry for entry in objects}
    result = []
    for source_key, container, kind in GAMEPLAY:
        for source in manifest.get(source_key, ()):
            position = source.get("position", source.get("center"))
            if position is None:
                raise ValueError(f"Gameplay record {source_key}/{source.get('id')} has no position")
            linked = str(source.get("node", ""))
            followed = by_node.get(linked)
            offset = [0.0, 0.0, 0.0]
            if followed is not None:
                offset = (np.linalg.inv(followed["matrix"]) @
                          np.asarray([*position, 1.0], float))[:3].tolist()
            result.append({
                "container": container, "kind": kind, "id": str(source["id"]),
                "position": [float(value) for value in position],
                "label": str(source.get("label", source.get("name", ""))),
                "destinationMap": str(source.get("destinationMap", "")),
                "destinationSpawn": str(source.get("destinationSpawn", "")),
                "key": str(source.get("key", "")), "default": bool(source.get("default", False)),
                "facing": [float(value) for value in source.get("facing", (0, 0, -1))],
                "node": linked, "followAssetId": followed["id"] if followed else "",
                "followAssetOffset": offset, "extras": clean_extras(source),
                "runtimeBindings": [],
            })
    if len(result) != 171:
        raise ValueError(f"Certified visible gameplay must contain 171 markers, got {len(result)}")
    return sorted(result, key=lambda entry: (entry["container"], entry["id"]))


def runtime_profile_hashes(seed: dict) -> dict[str, tuple[str, str]]:
    """Map logical source paths to portable immutable profile records."""
    result: dict[str, tuple[str, str]] = {}
    for entry in seed.get("provenance", {}).get("profileFiles", ()):
        if not isinstance(entry, dict):
            continue
        stored = str(entry.get("path", ""))
        if not stored.startswith(IMMUTABLE_PROFILE_PREFIX):
            raise ValueError(
                "Runtime identity profile path must use the immutable repo-relative prefix: "
                f"{stored}")
        logical = stored[len(IMMUTABLE_PROFILE_PREFIX):]
        if not logical.startswith("config/eloria/") or logical in result:
            raise ValueError(f"Runtime identity profile path is invalid or duplicated: {stored}")
        result[logical] = (stored, str(entry.get("sha256", "")))
    return result


def validate_runtime_seed_profiles(seed: dict, profile_root: Path) -> None:
    """Bind runtime identities to the immutable profile, not served positions.

    ``initialPosition`` and ``targetOffset`` deliberately come from the last
    certified publication.  Source line/tile identity is a different concern:
    it must name the immutable profile that the publisher rewrites.  Keeping
    this check at the adapter boundary prevents a served profile from becoming
    a circular authoring input.
    """
    profile_root = profile_root.resolve()
    profiles = runtime_profile_hashes(seed)
    used = {str(binding.get("source", {}).get("path", ""))
            for binding in seed.get("bindings", ())}
    if not used or "" in used or set(profiles) != used:
        raise ValueError("Runtime binding seed profileFiles must exactly cover every source path")

    texts: dict[str, list[str]] = {}
    for relative in sorted(used):
        stored, expected_sha = profiles[relative]
        path = (profile_root / stored).resolve()
        if not path.is_relative_to(profile_root) or not path.is_file():
            raise ValueError(f"Runtime identity profile is missing {stored}")
        actual = sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or actual != expected_sha:
            raise ValueError(f"Runtime identity profile hash mismatch for {stored}")
        texts[relative] = path.read_text(encoding="utf-8").splitlines()

    content_layout = {
        "config/eloria/interactives.txt": (None, 0, 2, 3, 1),
        "config/eloria/npcs.txt": ("npc", 2, 3, 4, 1),
        "config/eloria/harvesting.txt": ("node", 1, 3, 4, 2),
        "config/eloria/spawns.txt": ("spawn", 1, 3, 4, None),
    }
    seen: set[tuple] = set()
    for binding in seed.get("bindings", ()):
        identity = str(binding.get("id", ""))
        source = binding.get("source", {})
        relative = str(source.get("path", ""))
        line = source.get("line")
        old = source.get("oldTile")
        if (not isinstance(line, int) or line <= 0 or line > len(texts[relative]) or
                not isinstance(old, list) or len(old) != 2 or
                not all(isinstance(value, int) and not isinstance(value, bool) for value in old)):
            raise ValueError(f"Runtime binding {identity} has invalid immutable source coordinates")
        fields = [value.strip() for value in texts[relative][line - 1].split("|")]
        if relative in content_layout:
            keyword, region_index, x_index, y_index, identity_index = content_layout[relative]
            if (len(fields) <= max(region_index, x_index, y_index) or
                    keyword is not None and fields[0] != keyword or
                    fields[region_index] != REGION_ID or
                    [int(fields[x_index]), int(fields[y_index])] != old):
                raise ValueError(f"Runtime binding {identity} does not match its immutable content row")
            if identity_index is not None and fields[identity_index] != str(source.get("recordId", "")):
                raise ValueError(f"Runtime binding {identity} recordId changed in the immutable profile")
        elif relative == "config/eloria/maps.txt":
            if not fields or fields[0] != "portal" or len(fields) not in (7, 8):
                raise ValueError(f"Runtime binding {identity} does not name an immutable portal row")
            start = 2 if len(fields) == 7 else 3
            role = str(binding.get("role", ""))
            index = start if role == "door" else start + 3 if role == "return" else -1
            if index < 0 or [int(fields[index]), int(fields[index + 1])] != old:
                raise ValueError(f"Runtime binding {identity} portal role/tile changed")
            record_id = source.get("recordId")
            if record_id is not None:
                actual = fields[2] if len(fields) == 8 else f"{fields[2]}:{fields[3]}"
                if actual != str(record_id):
                    raise ValueError(f"Runtime binding {identity} portal recordId changed")
        elif relative == "config/eloria/territories.txt":
            occurrences = [index for index in range(len(fields) - 1)
                           if fields[index:index + 2] == list(map(str, old))]
            if not fields or fields[0] != REGION_ID or len(occurrences) != 1:
                raise ValueError(f"Runtime binding {identity} territory point is absent or ambiguous")
        else:
            raise ValueError(f"Runtime binding {identity} uses unsupported source {relative}")
        qualified = (relative, line, tuple(old), str(binding.get("role", "")),
                     str(source.get("recordId", "")))
        if qualified in seen:
            raise ValueError(f"Runtime binding {identity} duplicates immutable source identity {qualified}")
        seen.add(qualified)


def apply_runtime_seed(markers: list[dict], seed: dict) -> None:
    if seed.get("schema") != "eloria-runtime-binding-seed-v1" or seed.get("regionId") != REGION_ID:
        raise ValueError("Runtime binding seed schema/region does not match Amethyst")
    profile_hashes = {logical: record[1]
                      for logical, record in runtime_profile_hashes(seed).items()}
    report_sha = str(seed.get("provenance", {}).get("sourceReportSha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", report_sha):
        raise ValueError("Runtime binding seed needs a certified source report hash")
    by_target = {(OUTPUT_SECTIONS[entry["kind"]], entry["id"]): entry for entry in markers}
    seen = set()
    for binding in seed.get("bindings", ()):
        identity = str(binding.get("id", ""))
        if not identity or identity in seen:
            raise ValueError(f"Runtime binding id is empty or duplicated: {identity}")
        seen.add(identity)
        target = binding.get("marker", {})
        key = (str(target.get("section", "")), str(target.get("id", "")))
        marker = by_target.get(key)
        offset = binding.get("targetOffset")
        if (not isinstance(offset, list) or len(offset) != 3 or
                not all(isinstance(value, (int, float)) and not isinstance(value, bool) and
                        math.isfinite(float(value)) for value in offset) or
                not math.isclose(float(offset[1]), 0.0, abs_tol=1e-9)):
            raise ValueError(f"Runtime binding {identity} needs finite horizontal targetOffset")
        if key[0] == "runtimePoints" and marker is None:
            position = binding.get("initialPosition")
            role = str(binding.get("role", ""))
            group = RUNTIME_GROUPS.get(role)
            if not isinstance(position, list) or len(position) != 3 or group is None:
                raise ValueError(f"Runtime point {key[1]} needs a supported role and initialPosition")
            if any(not math.isclose(float(value), 0.0, abs_tol=1e-9) for value in offset):
                raise ValueError(f"Runtime point binding {identity} targetOffset must be zero")
            marker = {
                "container": f"RuntimePoints/{group}", "kind": "runtime_point",
                "id": key[1], "position": list(map(float, position)),
                "label": str(binding.get("source", {}).get("recordId", identity)),
                "destinationMap": "", "destinationSpawn": "", "key": "",
                "default": False, "facing": [0.0, 0.0, -1.0], "node": "",
                "followAssetId": "", "followAssetOffset": [0.0, 0.0, 0.0],
                "extras": {}, "runtimeBindings": [],
            }
            markers.append(marker); by_target[key] = marker
        if marker is None:
            raise ValueError(f"Runtime binding {identity} targets missing marker {key}")
        emitted = copy.deepcopy(binding)
        emitted.pop("marker", None); emitted.pop("initialPosition", None)
        emitted["targetOffset"] = [float(offset[0]), 0.0, float(offset[2])]
        emitted["provenance"] = {"sourceReportSha256": report_sha}
        source_path = str(emitted.get("source", {}).get("path", ""))
        profile_sha = profile_hashes.get(source_path, "")
        if not profile_sha:
            raise ValueError(f"Runtime binding {identity} has no immutable source profile hash")
        emitted["provenance"]["sourceProfileSha256"] = profile_sha
        marker["runtimeBindings"].append(emitted)
    markers.sort(key=lambda entry: (entry["container"], entry["id"]))
    expected = seed.get("counts", {})
    runtime_count = sum(entry["kind"] == "runtime_point" for entry in markers)
    if len(seen) != int(expected.get("bindings", -1)) or \
            runtime_count != int(expected.get("runtimePoints", -1)):
        raise ValueError("Runtime binding seed counts do not match emitted controls")


def canonical_runtime_seed(source: dict) -> dict:
    """Round mutable coordinates exactly as the text scene stores them.

    The snapshot embeds bindings from the loaded Godot scene and is required
    to equal its hash-bound seed record-for-record.  Godot text resources use
    the same 12-significant-digit representation as ``gd_float``; keeping the
    copied seed at that precision prevents a raw Python double from claiming a
    coordinate the saved scene cannot represent.
    """
    result = copy.deepcopy(source)
    for binding in result.get("bindings", ()):
        for field in ("targetOffset", "initialPosition"):
            if field in binding:
                binding[field] = [float(gd_float(value)) for value in binding[field]]
    return result


def write_scene(output: Path, manifest: dict, provenance: dict, objects: list[dict],
                prototypes: dict, paths: list[dict], markers: list[dict],
                resource_root: str, runtime_seed_res: str, runtime_seed_sha: str) -> None:
    resources = [
        ("Script", "res://src/dev/map_authoring_region/region_control.gd", "region"),
        ("Script", "res://src/dev/map_authoring_region/terrain_control.gd", "terrain"),
        ("Script", "res://src/dev/map_authoring_region/path_control.gd", "path"),
        ("Script", "res://src/dev/map_authoring_region/asset_control.gd", "asset"),
        ("Script", "res://src/dev/map_authoring_region/gameplay_marker.gd", "marker"),
        ("Resource", f"{resource_root}/surfaces/crystal.tres", "terrain_surface"),
        ("Resource", f"{resource_root}/surfaces/road.tres", "road_surface"),
    ]
    for index, path in enumerate(paths):
        path["resourceId"] = f"curve_{index:02d}"
        resources.append(("Curve3D", path["curve"], path["resourceId"]))
    for index, family in enumerate(sorted(prototypes)):
        prototypes[family]["resourceId"] = f"prototype_{index:03d}"
        resources.append(("PackedScene", prototypes[family]["path"],
                          prototypes[family]["resourceId"]))
    lines = [f'[gd_scene load_steps={len(resources) + 1} format=3]', ""]
    lines += [f'[ext_resource type="{kind}" path="{path}" id="{identity}"]'
              for kind, path, identity in resources]
    ownership = manifest["continentGeography"]["ownershipPolygon"]
    ownership_sha = hashlib.sha256(json.dumps(
        ownership, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    lines.extend(("", '[node name="AmethystBarrens" type="Node3D"]',
                  'script = ExtResource("region")', f'region_id = "{REGION_ID}"',
                  'continent_translation = Vector3(950, 0, 400)',
                  'metres_per_tile = 1.0', 'server_origin = Vector2i(182, 166)',
                  'server_cells = Vector2i(738, 738)',
                  'collision_origin_metres = Vector2(-182, 166)',
                  f'ownership_polygon_sha256 = "{ownership_sha}"',
                  f'seam_anchors = {godot_value(manifest["streamingBorders"])}',
                  'owned_route_ids = PackedStringArray(' + ", ".join(
                      godot_string(value) for value in OWNED_ROUTE_IDS) + ')',
                  'owned_plan_feature_ids = PackedStringArray()',
                  f'runtime_binding_seed_path = {godot_string(runtime_seed_res)}',
                  f'runtime_binding_seed_sha256 = {godot_string(runtime_seed_sha)}',
                  'export_directory = "res://../eloria-assets/maps/nymara-regions/amethyst_barrens/authoring"',
                  "", '[node name="Terrain" type="Node3D" parent="."]',
                  'script = ExtResource("terrain")', 'origin = Vector2(-182, -572)',
                  'cell_metres = 2.0', 'grid_size = Vector2i(370, 370)',
                  f'base_heights_path = "{resource_root}/base-heights.f32le"',
                  'base_surface = ExtResource("terrain_surface")', "",
                  '[node name="Patches" type="Node3D" parent="Terrain"]', "",
                  '[node name="Ground" type="Node3D" parent="."]', "",
                  '[node name="Regions" type="Node3D" parent="Ground"]', "",
                  '[node name="Roads" type="Node3D" parent="."]', ""))
    for path in paths:
        lines.extend((f'[node name={godot_string(node_name(path["id"]))} type="Path3D" parent="Roads"]',
                      'script = ExtResource("path")',
                      f'curve = ExtResource("{path["resourceId"]}")',
                      f'path_id = {godot_string(path["id"])}', 'kind = "road"',
                      f'routing_role = {godot_string(path["routingRole"])}',
                      f'replaces_route_id = {godot_string(path["id"])}',
                      f'properties = {godot_value(path["properties"])}',
                      f'default_width = {gd_float(path["width"])}',
                      'surface = ExtResource("road_surface")', ""))
    lines.extend(('[node name="Rivers" type="Node3D" parent="."]', "",
                  '[node name="Bridges" type="Node3D" parent="."]', "",
                  '[node name="AuthoredAssets" type="Node3D" parent="."]', ""))
    for record in objects:
        prototype = prototypes[record["family"]]
        path = f'AuthoredAssets/{node_name(record["id"])}'
        lines.extend((f'[node name={godot_string(node_name(record["id"]))} type="Node3D" parent="AuthoredAssets"]',
                      'script = ExtResource("asset")',
                      f'transform = {transform3d(record["matrix"])}',
                      f'asset_id = {godot_string(record["id"])}',
                      f'node_name = {godot_string(record["nodeName"])}',
                      f'catalog_asset_id = {godot_string("amethyst:" + record["family"])}',
                      f'scene_path = {godot_string(prototype["path"])}',
                      'source_node = "."',
                      f'collision_role = {godot_string(record["collisionRole"])}',
                      f'metadata = {godot_value(record["metadata"])}', "",
                      f'[node name="Content" parent={godot_string(path)} instance=ExtResource("{prototype["resourceId"]}")]', ""))
    lines.extend(('[node name="Gameplay" type="Node3D" parent="."]', ""))
    containers = [entry[1] for entry in GAMEPLAY] + ["AmbientPopulation", "RuntimePoints"]
    for container in containers:
        lines.extend((f'[node name="{container}" type="Node3D" parent="Gameplay"]', ""))
    for group in RUNTIME_GROUPS.values():
        lines.extend((f'[node name="{group}" type="Node3D" parent="Gameplay/RuntimePoints"]', ""))
    for marker in markers:
        parent = f'Gameplay/{marker["container"]}'
        lines.extend((f'[node name={godot_string(node_name(marker["id"]))} type="Marker3D" parent={godot_string(parent)}]',
                      'script = ExtResource("marker")',
                      f'position = Vector3({", ".join(gd_float(value) for value in marker["position"])})',
                      f'record_id = {godot_string(marker["id"])}',
                      f'kind = {godot_string(marker["kind"])}',
                      f'label = {godot_string(marker["label"])}',
                      f'destination_map = {godot_string(marker["destinationMap"])}',
                      f'destination_spawn = {godot_string(marker["destinationSpawn"])}',
                      f'key_id = {godot_string(marker["key"])}',
                      f'default_spawn = {godot_value(marker["default"])}',
                      f'facing = Vector3({", ".join(gd_float(value) for value in marker["facing"])})',
                      f'linked_node_name = {godot_string(marker["node"])}',
                      f'follow_asset_id = {godot_string(marker["followAssetId"])}',
                      f'follow_asset_offset = Vector3({", ".join(gd_float(value) for value in marker["followAssetOffset"])})',
                      f'extras = {godot_value(marker["extras"])}',
                      f'runtime_bindings = {godot_value(marker["runtimeBindings"])}', ""))
    lines.extend(('[node name="GeneratedPreview" type="Node3D" parent="."]', ""))
    (output / "amethyst_barrens.tscn").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--roads", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--base-heights", type=Path, required=True)
    parser.add_argument("--resolved-heights", type=Path, required=True)
    parser.add_argument("--runtime-bindings", type=Path, required=True)
    parser.add_argument("--runtime-profile-root", type=Path, required=True,
                        help="Client repository root resolving immutable repo-relative profile paths")
    parser.add_argument("--composed", type=Path, required=True)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--export-ledger", type=Path, required=True)
    parser.add_argument("--published-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    repo = Path(__file__).resolve().parents[2]
    for path in (repo / "eloria-assets/maps/nymara-regions/_toolkit",
                 repo / "eloria-assets/maps/nymara-regions/_continent"):
        if str(path) not in sys.path: sys.path.insert(0, str(path))
    import glb_reader
    import scene_io

    output = args.output.resolve()
    project = (repo / "godot-client").resolve()
    resource_root = "res://" + output.relative_to(project).as_posix()
    scene_path = output / "amethyst_barrens.tscn"
    if scene_path.exists() and not args.force:
        raise ValueError("Refusing to overwrite existing Amethyst scene without --force")
    if args.base_heights.stat().st_size != GRID_BYTES or args.resolved_heights.stat().st_size != GRID_BYTES:
        raise ValueError(f"Amethyst height grids must each contain {GRID_BYTES} bytes")
    source_library = args.source_world.with_name("library.json")
    if not source_library.is_file():
        raise ValueError("Amethyst source-world must be the certified library.glb beside library.json")
    output.mkdir(parents=True, exist_ok=True)
    # Amethyst's certified resolved grid is the saved terrain authority.  The
    # natural capture is retained only as migration provenance; it is not a
    # hidden correction layer or a build fallback.
    shutil.copyfile(args.resolved_heights, output / "base-heights.f32le")
    document, body = glb_reader.load(args.source_world)
    library = json.loads(source_library.read_text(encoding="utf-8"))
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    roads = json.loads(args.roads.read_text(encoding="utf-8"))
    import capture_composed_region
    capture = capture_composed_region.load(
        REGION_ID, args.composed, args.composition, args.export_ledger,
        args.published_master,
        args.source_manifest)
    final_document, final_body = capture.content.documents[REGION_ID]
    objects, families = final_object_records(capture.content, capture.objects, library)
    prototypes = write_prototypes(
        final_document, final_body, families, output, resource_root, scene_io)
    prune_generated_assets(output, prototypes)
    paths = path_records(roads, output, resource_root)
    markers = marker_records(manifest, objects)
    seed = canonical_runtime_seed(json.loads(args.runtime_bindings.read_text(encoding="utf-8")))
    validate_runtime_seed_profiles(seed, args.runtime_profile_root)
    (output / "runtime-bindings.seed.json").write_text(
        json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    apply_runtime_seed(markers, seed)
    write_surface(output / "surfaces/crystal.tres", "Crystal")
    write_surface(output / "surfaces/road.tres", "Worn earth", road=True)
    provenance = {
        "schema": "eloria-amethyst-authoring-migration-v1", "regionId": REGION_ID,
        "inputs": {
            "sourceWorldSha256": sha256(args.source_world),
            "sourceLibrarySha256": sha256(source_library),
            "sourceManifestSha256": sha256(args.source_manifest),
            "roadsSha256": sha256(args.roads), "planSha256": sha256(args.plan),
            "capturedNaturalHeightsSha256": sha256(args.base_heights),
            "authoredBaseHeightsSha256": sha256(output / "base-heights.f32le"),
            "certifiedResolvedHeightsSha256": sha256(args.resolved_heights),
            "runtimeBindingSeedSha256": sha256(output / "runtime-bindings.seed.json"),
            **capture.provenance,
        },
        "counts": {"objects": len(objects), "retiredSourcePlacements": 254,
                   "finalScatterObjects": 0, "prototypeFamilies": len(prototypes),
                   "paths": len(paths), "crossings": len(CROSSING_ASSETS),
                   "visibleGameplay": 171,
                   "runtimeBindings": len(seed.get("bindings", ())),
                   "runtimePoints": sum(entry["kind"] == "runtime_point" for entry in markers)},
        "crossings": [{"id": identity, "assetId": asset, "walkNode": walk}
                      for identity, (asset, walk) in sorted(CROSSING_ASSETS.items())],
        "objects": [{"id": entry["id"], "family": entry["family"],
                     "collisionRole": entry["collisionRole"]} for entry in objects],
    }
    runtime_seed_res = f"{resource_root}/runtime-bindings.seed.json"
    write_scene(output, manifest, provenance, objects, prototypes, paths, markers,
                resource_root, runtime_seed_res, sha256(output / "runtime-bindings.seed.json"))
    provenance["sceneSha256"] = sha256(scene_path)
    (output / "migration-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"amethyst_authoring_import_ok scene={scene_path} sha256={provenance['sceneSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
