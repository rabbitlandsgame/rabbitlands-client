#!/usr/bin/env python3
"""Deterministically migrate certified Whitehorn Range into authoring.

Whitehorn's current composed output is the bootstrap authority.  The adapter
captures exact final object subtrees, the three published bridge unions, the
resolved height field, and the terrain's RGBA8 paint.  Normal builds consume
only the saved scene and copied assets; they never reopen ``composed.pkl``.
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
    clean_extras, gd_float, godot_string, godot_value, node_name, sha256,
    legacy_curved_points, slug, transform3d, write_curve, write_surface,
)


REGION_ID = "whitehorn_range"
IMMUTABLE_PROFILE_PREFIX = (
    "eloria-assets/maps/nymara-regions/_continent/legacy-server-profile/"
)
TRANSLATION = np.array([550.0, 0.0, 220.0])
GRID_ORIGIN = np.array([-358.0, -220.0])
GRID_SHAPE = (350, 289)  # X vertices, Z vertices.
GRID_BYTES = GRID_SHAPE[0] * GRID_SHAPE[1] * 4
COLOR_BYTES = GRID_BYTES
PREVIEW_UV_DENSITY = 0.17
OWNED_ROUTE_IDS = tuple(sorted((
    "grey_moors--whitehorn_range-whitehorn_range",
    "amberwood--whitehorn_range-whitehorn_range",
    "amethyst_barrens--whitehorn_range-whitehorn_range",
    "door-whitehorn_range-whitehorn-glacier-temple-door",
    "door-whitehorn_range-whitehorn-mine-adit",
    "door-whitehorn_range-whitehorn-ice-cave-mouth",
    "door-whitehorn_range-whitehorn-barrow-door",
    "door-whitehorn_range-snowline-cell-door",
    "door-whitehorn_range-west-watch-cave-mouth",
    "door-whitehorn_range-gate-store-door",
    "discovery-whitehorn_range-516",
    "discovery-whitehorn_range-528",
    "discovery-whitehorn_range-530",
    "discovery-whitehorn_range-531",
    "discovery-whitehorn_range-532",
    "discovery-whitehorn_range-534",
    "discovery-whitehorn_range-535",
    "discovery-whitehorn_range-537",
    "discovery-whitehorn_range-538",
    "discovery-whitehorn_range-539",
    "discovery-whitehorn_range-620",
    "discovery-whitehorn_range-1111",
    "trail-whitehorn_range-0",
)))
REQUIRED_ROUTE_IDS = tuple(identity for identity in OWNED_ROUTE_IDS
                           if not identity.startswith(("discovery-", "trail-")))
RIVER_ID = "horn_tributary"
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
BRIDGE_UNIONS = {
    "horn_tributary@292": "003",
    "horn_tributary@124": "013",
    "horn_tributary@24": "014",
}


def descendants(document: dict, roots: list[int]) -> list[int]:
    result, stack = [], list(reversed(roots))
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


def matrix_list(matrix: np.ndarray) -> list[float]:
    return np.asarray(matrix, dtype=float).T.reshape(-1).tolist()


def final_object_records(content, objects: tuple[dict, ...]):
    """Capture exact post-composition objects, including grouped roots."""
    import glb_reader
    records, families = [], defaultdict(list)
    for obj in objects:
        source_region = str(obj.get("libraryRegion", REGION_ID))
        if source_region != REGION_ID:
            raise ValueError(
                f"{obj.get('node')}: final foreign-source object needs explicit review")
        document, _body = content.documents[source_region]
        matrices, _parents = glb_reader.hierarchy(document)
        roots = list(obj.get("indices", [obj["index"]]))
        if not roots or len(roots) != len(set(roots)):
            raise ValueError(f"{obj.get('node')}: empty or duplicate grouped roots")
        primary = int(obj["index"])
        if primary not in roots:
            raise ValueError(f"{obj.get('node')}: primary root is absent from grouped roots")
        shift = np.asarray(obj["shift"], dtype=float) - TRANSLATION
        control = np.asarray(matrices[primary], dtype=float).copy()
        control[:3, 3] += shift
        relative = {
            root: np.linalg.inv(np.asarray(matrices[primary], dtype=float)) @
                  np.asarray(matrices[root], dtype=float)
            for root in roots
        }
        signatures = tuple(
            (document["nodes"][root].get("name", ""),
             tuple(np.round(relative[root], 12).ravel()),
             subtree_signature(document, root))
            for root in roots)
        identity = str(obj["node"])
        family = f"{slug(identity)}-{hashlib.sha256(repr(signatures).encode()).hexdigest()[:12]}"
        source = obj.get("source", {})
        metadata = {key: copy.deepcopy(value) for key, value in source.items()
                    if key not in ("node", "position", "collides", "walk_surface")
                    and value is not None}
        metadata["composedSourceRegion"] = source_region
        if len(roots) > 1:
            metadata["groupedRootNames"] = [document["nodes"][root].get("name", "")
                                            for root in roots]
        record = {
            "id": identity, "nodeName": identity, "sourceRoots": roots,
            "sourceRegion": source_region, "family": family, "matrix": control,
            "relativeRootMatrices": relative,
            "collisionRole": "solid" if obj.get("collides") else
                             "walk_surface" if obj.get("walk") else "none",
            "metadata": metadata,
        }
        records.append(record)
        families[family].append(record)
    if len(records) != 380 or len({entry["id"] for entry in records}) != 380:
        raise ValueError(
            f"Certified final Whitehorn composition must contain 380 unique objects, got {len(records)}")
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
        roots = representative["sourceRoots"]
        for root in roots:
            node = private["nodes"][root]
            for field in ("translation", "rotation", "scale"):
                node.pop(field, None)
            node["matrix"] = matrix_list(representative["relativeRootMatrices"][root])
        target = prototype_dir / f"{family}.glb"
        exporter = scene_io.Exporter(target, shared_images=texture_dir)
        exporter.add(private, body, roots,
                     root_names={root: private["nodes"][root].get("name", family)
                                 for root in roots})
        stats = exporter.write()
        records[family] = {
            "path": f"{resource_root}/assets/prototypes/{target.name}",
            "sha256": sha256(target), "representative": representative["id"],
            "instances": len(families[family]), "roots": len(roots), "stats": stats,
        }
    return records


def _image_bytes(document: dict, body: bytes, name: str) -> bytes:
    matches = [image for image in document.get("images", ()) if image.get("name") == name]
    if len(matches) != 1 or matches[0].get("mimeType") != "image/png":
        raise ValueError(f"Published master needs one PNG image named {name!r}")
    view = document["bufferViews"][matches[0]["bufferView"]]
    start = int(view.get("byteOffset", 0)); length = int(view["byteLength"])
    result = body[start:start + length]
    if not result.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Published {name!r} payload is not PNG")
    return result


def terrain_colors(world, published_document: dict, published_body: bytes,
                   output: Path) -> dict:
    """Freeze exact current biome/road paint into a full-grid RGBA8 sidecar."""
    import glb_reader
    import landscape as landscape

    global_x = TRANSLATION[0] + GRID_ORIGIN[0] + np.arange(GRID_SHAPE[0]) * 2.0
    global_z = TRANSLATION[2] + GRID_ORIGIN[1] + np.arange(GRID_SHAPE[1]) * 2.0
    x_lookup = {round(float(value), 8): index for index, value in enumerate(world.x)}
    z_lookup = {round(float(value), 8): index for index, value in enumerate(world.z)}
    try:
        x_indices = np.asarray([x_lookup[round(float(value), 8)] for value in global_x])
        z_indices = np.asarray([z_lookup[round(float(value), 8)] for value in global_z])
    except KeyError as error:
        raise ValueError(f"Whitehorn color grid is outside certified composed terrain: {error}")
    gx = world.gx[np.ix_(z_indices, x_indices)]
    gz = world.gz[np.ix_(z_indices, x_indices)]
    height = world.height[np.ix_(z_indices, x_indices)]
    distance = world.road_distance[np.ix_(z_indices, x_indices)]
    colors = landscape.terrain_color(gx, gz, height=height, plan=world.plan)
    road = np.clip(1.0 - landscape.smoothstep(
        .70, 1.28, np.where(np.isfinite(distance), distance, 1000.0)), 0.0, 1.0)
    road_color = np.asarray([.49, .435, .315]) ** 2.2
    colors = colors * (1.0 - road[..., None]) + road_color * road[..., None]
    rgba = np.concatenate([
        np.clip(colors / .92, 0.0, 1.0), np.ones((*colors.shape[:2], 1))], axis=-1)
    rgba8 = np.rint(rgba * 255.0).astype(np.uint8)
    target = output / "base-colors.rgba8"
    target.write_bytes(rgba8.tobytes())
    if target.stat().st_size != COLOR_BYTES:
        raise ValueError("Whitehorn RGBA8 color sidecar length mismatch")

    compared = 0
    max_uv_error = 0.0
    for node in published_document.get("nodes", ()):
        name = str(node.get("name", ""))
        if not name.startswith("Terrain_whitehorn_range_") or "mesh" not in node:
            continue
        primitive = published_document["meshes"][node["mesh"]]["primitives"][0]
        attributes = primitive["attributes"]
        positions = glb_reader.accessor(
            published_document, published_body, attributes["POSITION"])
        actual = glb_reader.accessor(
            published_document, published_body, attributes["COLOR_0"])
        uv = glb_reader.accessor(
            published_document, published_body, attributes["TEXCOORD_0"])
        for position, color, texture_uv in zip(positions, actual, uv):
            column = int(round((float(position[0]) - global_x[0]) / 2.0))
            row = int(round((float(position[2]) - global_z[0]) / 2.0))
            if not (0 <= column < GRID_SHAPE[0] and 0 <= row < GRID_SHAPE[1]):
                raise ValueError(f"Published Whitehorn vertex is outside saved color grid: {position}")
            if not np.array_equal(rgba8[row, column], np.asarray(color, dtype=np.uint8)):
                raise ValueError(f"Published Whitehorn color differs at XZ {position[[0, 2]]}")
            max_uv_error = max(max_uv_error, float(np.max(np.abs(
                np.asarray(texture_uv, float) - position[[0, 2]] * PREVIEW_UV_DENSITY))))
            compared += 1
    if compared == 0 or max_uv_error > 2.0e-5:
        raise ValueError(
            f"Whitehorn published terrain validation failed: vertices={compared}, uv={max_uv_error}")
    texture = output / "assets/textures/continental-ground.png"
    texture.parent.mkdir(parents=True, exist_ok=True)
    texture.write_bytes(_image_bytes(published_document, published_body, "continental-ground"))
    water_texture = output / "assets/textures/continental-water.png"
    water_texture.write_bytes(
        _image_bytes(published_document, published_body, "continental-water"))
    return {
        "path": target.name, "sha256": sha256(target), "encoding": "rgba8-srgb",
        "publishedVerticesCompared": compared, "maximumPublishedUvError": max_uv_error,
        "texturePath": "assets/textures/continental-ground.png",
        "textureSha256": sha256(texture),
        "waterTexturePath": "assets/textures/continental-water.png",
        "waterTextureSha256": sha256(water_texture),
    }


def bridge_records(document: dict, body: bytes, roads: dict, output: Path,
                   resource_root: str, scene_io) -> tuple[list[dict], dict[str, dict]]:
    """Copy the three exact published deck+edge assemblies as grouped assets."""
    import glb_reader
    by_name = {node.get("name", ""): index for index, node in enumerate(document["nodes"])}
    sites = {entry["key"]: entry for entry in roads.get("crossingSites", ())}
    result, prototypes = [], {}
    for stable_id, suffix in sorted(BRIDGE_UNIONS.items()):
        walk = f"Walk_ContinentalBridgeUnion_{suffix}_whitehorn_range"
        edge = f"BridgeUnionTimberEdge_{suffix}_whitehorn_range"
        root_names = [walk + "_WorldPlacement", edge + "_WorldPlacement"]
        roots = [by_name.get(name, -1) for name in root_names]
        if -1 in roots or stable_id not in sites:
            raise ValueError(f"Published bridge assembly {stable_id!r} is incomplete")
        site = sites[stable_id]
        endpoints = [[float(x), float(site["deckLevel"]), float(z)]
                     for x, z in site["routeLandings"]]
        centre = np.mean(np.asarray(endpoints, float), axis=0)
        private = copy.deepcopy(document)
        for root in roots:
            node = private["nodes"][root]
            for field in ("matrix", "rotation", "scale"):
                node.pop(field, None)
            node["translation"] = (-centre).tolist()
        family = f"published-bridge-{slug(stable_id)}"
        target = output / "assets/prototypes" / f"{family}.glb"
        exporter = scene_io.Exporter(target, shared_images=output / "assets/textures")
        exporter.add(private, body, roots,
                     root_names={root: private["nodes"][root]["name"] for root in roots})
        stats = exporter.write()
        asset_id = f"published-bridge-{slug(stable_id)}"
        local_endpoints = [(np.asarray(point) - centre).tolist() for point in endpoints]
        record = {
            "id": asset_id, "nodeName": root_names[0], "family": family,
            "matrix": np.eye(4), "collisionRole": "walk_surface",
            "metadata": {"authoredCrossing": {
                "id": stable_id, "walkNode": walk, "localEndpoints": local_endpoints,
            }},
        }
        record["matrix"][:3, 3] = centre - TRANSLATION
        result.append(record)
        prototypes[family] = {
            "path": f"{resource_root}/assets/prototypes/{target.name}",
            "sha256": sha256(target), "representative": asset_id,
            "instances": 1, "roots": 2, "stats": stats,
        }
    return result, prototypes


def prune_generated_assets(output: Path, prototypes: dict[str, dict]) -> None:
    keep_prototypes = {Path(record["path"]).name for record in prototypes.values()}
    keep_textures = {"continental-ground.png", "continental-water.png"} | {
        Path(relative).name
        for record in prototypes.values()
        for relative in record["stats"].get("externalResources", {})
    }
    for path in (output / "assets/prototypes").glob("*.glb"):
        if path.name not in keep_prototypes:
            path.unlink(); path.with_name(path.name + ".import").unlink(missing_ok=True)
    for path in (output / "assets/textures").iterdir():
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg") \
                and path.name not in keep_textures:
            path.unlink(); path.with_name(path.name + ".import").unlink(missing_ok=True)
    for folder in (output / "assets/prototypes", output / "assets/textures"):
        for sidecar in folder.glob("*.import"):
            source = sidecar.with_name(sidecar.name.removesuffix(".import"))
            if not source.is_file():
                sidecar.unlink()


def path_records(roads_document: dict, plan: dict, output: Path,
                 resource_root: str) -> tuple[list[dict], dict]:
    roads = {entry["id"]: entry for entry in roads_document["roads"]}
    if missing := sorted(set(OWNED_ROUTE_IDS) - roads.keys()):
        raise ValueError(f"Published roads are missing Whitehorn-owned routes: {missing}")
    result = []
    for identity in OWNED_ROUTE_IDS:
        source = roads[identity]
        points = [[float(point[0] - TRANSLATION[0]), float(point[1]),
                   float(point[2] - TRANSLATION[2])] for point in source["points"]]
        curve = output / "paths" / f"{slug(identity)}.tres"
        write_curve(curve, points)
        result.append({
            "id": identity, "kind": "road", "points": points,
            "width": float(source["width"]) * 2.0,
            "routingRole": "required" if identity in REQUIRED_ROUTE_IDS else "decorative",
            "curve": f"{resource_root}/paths/{curve.name}",
            "properties": {"terrainConform": False, "terrainFeather": 2.0},
        })
    rivers = [entry for entry in plan.get("rivers", ()) if entry.get("id") == RIVER_ID]
    if len(rivers) != 1 or len(rivers[0].get("points", ())) != 45:
        raise ValueError("Certified Whitehorn plan must contain one 45-point horn_tributary")
    source = rivers[0]
    river_controls = source["points"]
    river_points = [[float(point[0] - TRANSLATION[0]), float(point[2]),
                     float(point[1] - TRANSLATION[2])]
                    for point in legacy_curved_points(river_controls)]
    curve = output / "paths/horn-tributary.tres"
    write_curve(curve, river_points)
    river = {
        "id": RIVER_ID, "kind": "river", "points": river_points,
        "sourceControlPointCount": len(river_controls),
        "sampling": "legacy-open-catmull-rom-6x-zero-handles",
        "width": float(source["width"]) * 2.0, "routingRole": "decorative",
        "curve": f"{resource_root}/paths/{curve.name}",
        "properties": {
            "terrainConform": False, "terrainFeather": 2.0,
            "name": str(source.get("name", "Hornwater")),
            "channelDepth": float(source["depth"]),
            "valleyWidth": float(source["valley_width"]),
            "bankHeight": float(source["bank_height"]),
            "bankShelfWidth": float(source.get("bank_shelf_width", 0.0)),
            "cutsRelief": bool(source.get("cuts_relief", False)),
            "joins": str(source.get("joins", "")),
        },
    }
    return result, river


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
    if len(result) != 125:
        raise ValueError(f"Certified visible gameplay must contain 125 markers, got {len(result)}")
    return sorted(result, key=lambda entry: (entry["container"], entry["id"]))


def runtime_profile_hashes(seed: dict) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for entry in seed.get("provenance", {}).get("profileFiles", ()):
        if not isinstance(entry, dict):
            continue
        stored = str(entry.get("path", ""))
        if not stored.startswith(IMMUTABLE_PROFILE_PREFIX):
            raise ValueError(f"Runtime identity profile must use immutable prefix: {stored}")
        logical = stored[len(IMMUTABLE_PROFILE_PREFIX):]
        if not logical.startswith("config/eloria/") or logical in result:
            raise ValueError(f"Runtime identity profile path is invalid or duplicated: {stored}")
        result[logical] = (stored, str(entry.get("sha256", "")))
    return result


def validate_runtime_seed_profiles(seed: dict, profile_root: Path) -> None:
    profile_root = profile_root.resolve()
    profiles = runtime_profile_hashes(seed)
    used = {str(binding.get("source", {}).get("path", ""))
            for binding in seed.get("bindings", ())}
    if not used or "" in used or set(profiles) != used:
        raise ValueError("Runtime seed profileFiles must exactly cover every source path")
    texts: dict[str, list[str]] = {}
    for relative in sorted(used):
        stored, expected_sha = profiles[relative]
        path = (profile_root / stored).resolve()
        if not path.is_relative_to(profile_root) or not path.is_file() or \
                sha256(path) != expected_sha:
            raise ValueError(f"Runtime identity profile missing or hash mismatch: {stored}")
        texts[relative] = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    for binding in seed.get("bindings", ()):
        source = binding.get("source", {}); relative = str(source.get("path", ""))
        line = source.get("line"); old = source.get("oldTile")
        if not isinstance(line, int) or line <= 0 or line > len(texts[relative]) or \
                not isinstance(old, list) or len(old) != 2:
            raise ValueError(f"Runtime binding {binding.get('id')} has invalid immutable source")
        row = [value.strip() for value in texts[relative][line - 1].split("|")]
        if REGION_ID not in row or not any(row[i:i + 2] == list(map(str, old))
                                           for i in range(len(row) - 1)):
            raise ValueError(f"Runtime binding {binding.get('id')} mismatches immutable row")
        qualified = (relative, line, tuple(old), str(binding.get("role", "")),
                     str(source.get("recordId", "")))
        if qualified in seen:
            raise ValueError(f"Runtime binding {binding.get('id')} duplicates source identity")
        seen.add(qualified)


def apply_runtime_seed(markers: list[dict], seed: dict) -> None:
    if seed.get("schema") != "eloria-runtime-binding-seed-v1" or \
            seed.get("regionId") != REGION_ID:
        raise ValueError("Runtime binding seed schema/region does not match Whitehorn")
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
        target = binding.get("marker", {}); key = (str(target.get("section", "")),
                                                    str(target.get("id", "")))
        marker = by_target.get(key); offset = binding.get("targetOffset")
        if not isinstance(offset, list) or len(offset) != 3 or \
                not all(isinstance(value, (int, float)) and math.isfinite(float(value))
                        for value in offset) or not math.isclose(float(offset[1]), 0.0, abs_tol=1e-9):
            raise ValueError(f"Runtime binding {identity} needs finite horizontal targetOffset")
        if key[0] == "runtimePoints" and marker is None:
            position = binding.get("initialPosition"); role = str(binding.get("role", ""))
            group = RUNTIME_GROUPS.get(role)
            if not isinstance(position, list) or len(position) != 3 or group is None or \
                    any(not math.isclose(float(value), 0.0, abs_tol=1e-9) for value in offset):
                raise ValueError(f"Runtime point {key[1]} has invalid position/offset")
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
        emitted = copy.deepcopy(binding); emitted.pop("marker", None); emitted.pop("initialPosition", None)
        emitted["targetOffset"] = [float(offset[0]), 0.0, float(offset[2])]
        source_path = str(emitted.get("source", {}).get("path", ""))
        emitted["provenance"] = {
            "sourceReportSha256": report_sha,
            "sourceProfileSha256": profile_hashes.get(source_path, ""),
        }
        if not emitted["provenance"]["sourceProfileSha256"]:
            raise ValueError(f"Runtime binding {identity} has no immutable source hash")
        marker["runtimeBindings"].append(emitted)
    markers.sort(key=lambda entry: (entry["container"], entry["id"]))
    expected = seed.get("counts", {})
    runtime_count = sum(entry["kind"] == "runtime_point" for entry in markers)
    if len(seen) != int(expected.get("bindings", -1)) or \
            runtime_count != int(expected.get("runtimePoints", -1)):
        raise ValueError("Runtime binding seed counts do not match Whitehorn controls")


def canonical_runtime_seed(source: dict) -> dict:
    result = copy.deepcopy(source)
    for binding in result.get("bindings", ()):
        for field in ("targetOffset", "initialPosition"):
            if field in binding:
                binding[field] = [float(gd_float(value)) for value in binding[field]]
    return result


def write_terrain_surface(path: Path, resource_root: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'''[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=4 format=3]

[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]
[ext_resource type="Texture2D" path="{resource_root}/assets/textures/continental-ground.png" id="2_albedo"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_ground"]
albedo_texture = ExtResource("2_albedo")
roughness = 0.95
metallic = 0.0
vertex_color_use_as_albedo = true
uv1_offset = Vector3(0.5, 0.4, 0)
texture_filter = 4
cull_mode = 2

[resource]
resource_local_to_scene = true
script = ExtResource("1_surface")
texture_preset = "Custom"
rotation_degrees = 0.0
source_material = SubResource("StandardMaterial3D_ground")
''', encoding="utf-8", newline="\n")


def write_river_surface(path: Path, resource_root: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'''[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=4 format=3]

[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]
[ext_resource type="Texture2D" path="{resource_root}/assets/textures/continental-water.png" id="2_albedo"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_water"]
albedo_texture = ExtResource("2_albedo")
roughness = 0.55
metallic = 0.0
cull_mode = 2
uv1_scale = Vector3(0.17, 0.17, 0.17)
uv1_offset = Vector3(0.5, 0.4, 0)
texture_filter = 4

[resource]
resource_local_to_scene = true
script = ExtResource("1_surface")
texture_preset = "Custom"
rotation_degrees = 0.0
source_material = SubResource("StandardMaterial3D_water")
''', encoding="utf-8", newline="\n")


def write_scene(output: Path, manifest: dict, objects: list[dict], prototypes: dict,
                paths: list[dict], river: dict, markers: list[dict], resource_root: str,
                runtime_seed_res: str, runtime_seed_sha: str) -> None:
    resources = [
        ("Script", "res://src/dev/map_authoring_region/region_control.gd", "region"),
        ("Script", "res://src/dev/map_authoring_region/terrain_control.gd", "terrain"),
        ("Script", "res://src/dev/map_authoring_region/path_control.gd", "path"),
        ("Script", "res://src/dev/map_authoring_region/asset_control.gd", "asset"),
        ("Script", "res://src/dev/map_authoring_region/gameplay_marker.gd", "marker"),
        ("Resource", f"{resource_root}/surfaces/continental-ground.tres", "terrain_surface"),
        ("Resource", f"{resource_root}/surfaces/road.tres", "road_surface"),
        ("Resource", f"{resource_root}/surfaces/river.tres", "river_surface"),
    ]
    all_paths = paths + [river]
    for index, path in enumerate(all_paths):
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
    lines.extend(("", '[node name="WhitehornRange" type="Node3D"]',
                  'script = ExtResource("region")', f'region_id = "{REGION_ID}"',
                  'continent_translation = Vector3(550, 0, 220)',
                  'metres_per_tile = 1.0', 'server_origin = Vector2i(362, 360)',
                  'server_cells = Vector2i(708, 708)',
                  'collision_origin_metres = Vector2(-362, 360)',
                  f'ownership_polygon_sha256 = "{ownership_sha}"',
                  f'seam_anchors = {godot_value(manifest["streamingBorders"])}',
                  'owned_route_ids = PackedStringArray(' + ", ".join(
                      godot_string(value) for value in OWNED_ROUTE_IDS) + ')',
                  f'owned_plan_feature_ids = PackedStringArray({godot_string(RIVER_ID)})',
                  f'runtime_binding_seed_path = {godot_string(runtime_seed_res)}',
                  f'runtime_binding_seed_sha256 = {godot_string(runtime_seed_sha)}',
                  'export_directory = "res://../eloria-assets/maps/nymara-regions/whitehorn_range/authoring"',
                  "", '[node name="Terrain" type="Node3D" parent="."]',
                  'script = ExtResource("terrain")', 'origin = Vector2(-358, -220)',
                  'cell_metres = 2.0', 'grid_size = Vector2i(350, 289)',
                  f'base_heights_path = "{resource_root}/base-heights.f32le"',
                  f'base_colors_path = "{resource_root}/base-colors.rgba8"',
                  f'preview_uv_metres_inverse = {gd_float(PREVIEW_UV_DENSITY)}',
                  'base_surface = ExtResource("terrain_surface")', "",
                  '[node name="Patches" type="Node3D" parent="Terrain"]', "",
                  '[node name="Ground" type="Node3D" parent="."]', "",
                  '[node name="Regions" type="Node3D" parent="Ground"]', "",
                  '[node name="Roads" type="Node3D" parent="."]', ""))
    for path in paths:
        lines.extend((f'[node name={godot_string(node_name(path["id"]))} type="Path3D" parent="Roads"]',
                      'script = ExtResource("path")', f'curve = ExtResource("{path["resourceId"]}")',
                      f'path_id = {godot_string(path["id"])}', 'kind = "road"',
                      f'routing_role = {godot_string(path["routingRole"])}',
                      f'replaces_route_id = {godot_string(path["id"])}',
                      f'properties = {godot_value(path["properties"])}',
                      f'default_width = {gd_float(path["width"])}',
                      'surface = ExtResource("road_surface")', ""))
    lines.extend(('[node name="Rivers" type="Node3D" parent="."]', "",
                  f'[node name={godot_string(node_name(river["id"]))} type="Path3D" parent="Rivers"]',
                  'script = ExtResource("path")', f'curve = ExtResource("{river["resourceId"]}")',
                  f'path_id = {godot_string(river["id"])}', 'kind = "river"',
                  'routing_role = "decorative"',
                  f'replaces_plan_feature_id = {godot_string(river["id"])}',
                  f'properties = {godot_value(river["properties"])}',
                  f'default_width = {gd_float(river["width"])}',
                  'surface = ExtResource("river_surface")', "",
                  '[node name="Bridges" type="Node3D" parent="."]', "",
                  '[node name="AuthoredAssets" type="Node3D" parent="."]', ""))
    for record in objects:
        prototype = prototypes[record["family"]]
        path = f'AuthoredAssets/{node_name(record["id"])}'
        lines.extend((f'[node name={godot_string(node_name(record["id"]))} type="Node3D" parent="AuthoredAssets"]',
                      'script = ExtResource("asset")', f'transform = {transform3d(record["matrix"])}',
                      f'asset_id = {godot_string(record["id"])}',
                      f'node_name = {godot_string(record["nodeName"])}',
                      f'catalog_asset_id = {godot_string("whitehorn:" + record["family"])}',
                      f'scene_path = {godot_string(prototype["path"])}', 'source_node = "."',
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
    (output / "whitehorn_range.tscn").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n")


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--roads", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--base-heights", type=Path, required=True)
    parser.add_argument("--resolved-heights", type=Path, required=True)
    parser.add_argument("--runtime-bindings", type=Path, required=True)
    parser.add_argument("--runtime-profile-root", type=Path, required=True)
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
    import capture_composed_region

    output = args.output.resolve(); project = (repo / "godot-client").resolve()
    resource_root = "res://" + output.relative_to(project).as_posix()
    scene_path = output / "whitehorn_range.tscn"
    if scene_path.exists() and not args.force:
        raise ValueError("Refusing to overwrite existing Whitehorn scene without --force")
    if args.resolved_heights.stat().st_size != GRID_BYTES:
        raise ValueError(f"Whitehorn resolved grid must contain {GRID_BYTES} bytes")
    if sha256(args.base_heights) != sha256(args.resolved_heights):
        raise ValueError("Whitehorn uses the certified resolved grid as its explicit saved base")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.resolved_heights, output / "base-heights.f32le")
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    roads = json.loads(args.roads.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    capture = capture_composed_region.load(
        REGION_ID, args.composed, args.composition, args.export_ledger,
        args.published_master, args.source_manifest)
    final_document, final_body = capture.content.documents[REGION_ID]
    objects, families = final_object_records(capture.content, capture.objects)
    object_ids = {entry["id"] for entry in objects}
    if "Landmark_ice_cave" not in object_ids or any("MC009" in identity for identity in object_ids):
        raise ValueError("Whitehorn capture must retain the published cave and exclude inactive MC009")
    prototypes = write_prototypes(
        final_document, final_body, families, output, resource_root, scene_io)
    published_document, published_body = glb_reader.load(args.published_master)
    bridges, bridge_prototypes = bridge_records(
        published_document, published_body, roads, output, resource_root, scene_io)
    objects.extend(bridges); objects.sort(key=lambda entry: entry["id"])
    prototypes.update(bridge_prototypes)
    color_record = terrain_colors(
        capture.world, published_document, published_body, output)
    prune_generated_assets(output, prototypes)
    paths, river = path_records(roads, plan, output, resource_root)
    markers = marker_records(manifest, objects)
    defaults = [entry for entry in markers if entry["kind"] == "spawn" and entry["default"]]
    if len(defaults) != 1 or defaults[0]["id"] != "continent-arrival":
        raise ValueError("Whitehorn needs one explicit saved continent-arrival default spawn")
    seed = canonical_runtime_seed(json.loads(args.runtime_bindings.read_text(encoding="utf-8")))
    validate_runtime_seed_profiles(seed, args.runtime_profile_root)
    seed_path = output / "runtime-bindings.seed.json"
    seed_path.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8", newline="\n")
    apply_runtime_seed(markers, seed)
    arrival = next(entry for entry in markers
                   if entry["kind"] == "spawn" and entry["id"] == "continent-arrival")
    if arrival["runtimeBindings"]:
        raise ValueError("Whitehorn continent-arrival has no immutable runtime source binding")
    write_terrain_surface(output / "surfaces/continental-ground.tres", resource_root)
    write_surface(output / "surfaces/road.tres", "Worn earth", road=True)
    write_river_surface(output / "surfaces/river.tres", resource_root)
    seed_res = f"{resource_root}/runtime-bindings.seed.json"
    write_scene(output, manifest, objects, prototypes, paths, river, markers,
                resource_root, seed_res, sha256(seed_path))
    provenance = {
        "schema": "eloria-whitehorn-authoring-migration-v1", "regionId": REGION_ID,
        "inputs": {
            "sourceWorldSha256": sha256(args.source_world),
            "sourceManifestSha256": sha256(args.source_manifest),
            "roadsSha256": sha256(args.roads), "planSha256": sha256(args.plan),
            "certifiedBootstrapHeightsSha256": sha256(args.base_heights),
            "authoredBaseHeightsSha256": sha256(output / "base-heights.f32le"),
            "certifiedResolvedHeightsSha256": sha256(args.resolved_heights),
            "runtimeBindingSeedSha256": sha256(seed_path),
            "baseColors": color_record, **capture.provenance,
        },
        "counts": {
            "objects": 380, "publishedBridgeAssemblies": len(bridges),
            "savedAssetControls": len(objects), "retiredSourcePlacements": 517,
            "prototypeFamilies": len(prototypes), "paths": len(paths),
            "riverControlPoints": river["sourceControlPointCount"],
            "riverCurvePoints": len(river["points"]), "visibleGameplay": 125,
            "runtimeBindings": len(seed.get("bindings", ())),
            "runtimePoints": sum(entry["kind"] == "runtime_point" for entry in markers),
        },
        "crossings": [{"id": entry["metadata"]["authoredCrossing"]["id"],
                       "assetId": entry["id"],
                       "walkNode": entry["metadata"]["authoredCrossing"]["walkNode"]}
                      for entry in bridges],
        "objects": [{"id": entry["id"], "family": entry["family"],
                     "collisionRole": entry["collisionRole"]} for entry in objects],
    }
    provenance["sceneSha256"] = sha256(scene_path)
    (output / "migration-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print(f"whitehorn_authoring_import_ok scene={scene_path} sha256={provenance['sceneSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
