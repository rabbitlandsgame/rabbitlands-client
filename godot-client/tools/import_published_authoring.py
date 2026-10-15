#!/usr/bin/env python3
"""Capture one published territory through the shared, source-bound adapter.

This bootstrap reads an independently verified final composition exactly once.
The saved scene and copied assets become the normal-build authority thereafter.
Region differences are explicit, validated metadata in the authoring spec.
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


REGION_ID = ""
LABEL = ""
IMMUTABLE_PROFILE_PREFIX = (
    "eloria-assets/maps/nymara-regions/_continent/legacy-server-profile/"
)
TRANSLATION = np.zeros(3)
GRID_ORIGIN = np.zeros(2)
GRID_SHAPE = (0, 0)  # X vertices, Z vertices.
GRID_STEP = 0.0
GRID_BYTES = 0
COLOR_BYTES = 0
PREVIEW_UV_DENSITY = 0.17
OWNED_ROUTE_IDS: tuple[str, ...] = ()
REQUIRED_ROUTE_IDS: tuple[str, ...] = ()
OWNED_PLAN_FEATURE_IDS: tuple[str, ...] = ()
BOOTSTRAP: dict = {}
CONTRACT = None
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
    "door": "Doors", "return": "Returns",
    "interactive": "Interactions", "npc": "Npcs",
    "harvest": "Harvestables", "spawn": "CreatureSpawns",
    "territory": "TerritoryPoints",
}
PUBLISHED_ASSEMBLIES: dict[str, tuple[str, str]] = {}


def configure(spec_path: Path) -> None:
    """Validate the small per-region bootstrap before reading any large source."""
    global REGION_ID, LABEL, TRANSLATION, GRID_ORIGIN, GRID_SHAPE, GRID_STEP
    global GRID_BYTES, COLOR_BYTES, PREVIEW_UV_DENSITY, OWNED_ROUTE_IDS
    global REQUIRED_ROUTE_IDS, OWNED_PLAN_FEATURE_IDS, BOOTSTRAP, CONTRACT
    global PUBLISHED_ASSEMBLIES
    repo = Path(__file__).resolve().parents[2]
    continent = repo / "eloria-assets/maps/nymara-regions/_continent"
    if str(continent) not in sys.path:
        sys.path.insert(0, str(continent))
    import authoring_catalog

    contract = authoring_catalog.load_region_spec(spec_path.resolve(), require_scene=False)
    if contract.adapter != "published-generic-v1":
        raise ValueError(f"{spec_path}: expected published-generic-v1 adapter")
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    bootstrap = raw.get("bootstrap")
    if not isinstance(bootstrap, dict) or bootstrap.get("schema") != \
            "eloria-published-region-bootstrap-v1":
        raise ValueError(f"{spec_path}: invalid published bootstrap schema")
    expected_keys = {
        "schema", "objectCount", "objectIdsSha256", "visibleGameplayCount",
        "assemblies", "water", "bakedTerrainFeatures",
        "previewUvMetresInverse", "baselineProofSha256",
    }
    if set(bootstrap) != expected_keys:
        raise ValueError(f"{spec_path}: bootstrap keys must be {sorted(expected_keys)}")
    for key in ("objectCount", "visibleGameplayCount"):
        if not isinstance(bootstrap[key], int) or bootstrap[key] < 0:
            raise ValueError(f"{spec_path}: bootstrap.{key} must be nonnegative integer")
    for key in ("objectIdsSha256", "baselineProofSha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(bootstrap[key])):
            raise ValueError(f"{spec_path}: bootstrap.{key} must be SHA256")
    uv = bootstrap["previewUvMetresInverse"]
    if not isinstance(uv, (int, float)) or not math.isfinite(float(uv)) or uv <= 0:
        raise ValueError(f"{spec_path}: invalid previewUvMetresInverse")
    assemblies = bootstrap["assemblies"]
    water = bootstrap["water"]
    baked = bootstrap["bakedTerrainFeatures"]
    if not isinstance(assemblies, list) or not isinstance(water, list) or \
            not isinstance(baked, list):
        raise ValueError(f"{spec_path}: assemblies, water, and bakedTerrainFeatures must be arrays")
    assembly_map = {}
    for entry in assemblies:
        if not isinstance(entry, dict) or set(entry) not in (\
                {"id", "walkNode", "supportNode", "kind"},
                {"id", "walkNode", "supportNodes", "kind"}) or \
                entry.get("kind") not in ("crossing", "access") or \
                any(not isinstance(entry.get(key), str) or not entry[key]
                    for key in ("id", "walkNode")):
            raise ValueError(f"{spec_path}: invalid published assembly {entry!r}")
        supports = entry.get("supportNodes", [entry.get("supportNode")])
        if not isinstance(supports, list) or \
                any(not isinstance(node, str) or not node for node in supports) or \
                len(set([entry["walkNode"], *supports])) != len(supports) + 1:
            raise ValueError(f"{spec_path}: invalid assembly support roots {entry!r}")
        if entry["id"] in assembly_map:
            raise ValueError(f"{spec_path}: duplicate assembly {entry['id']}")
        assembly_map[entry["id"]] = entry
    water_ids = []
    for entry in water:
        if not isinstance(entry, dict) or entry.get("kind") not in ("river", "lake") or \
                not isinstance(entry.get("id"), str) or not entry["id"] or \
                not isinstance(entry.get("planFeatureId"), str) or not entry["planFeatureId"]:
            raise ValueError(f"{spec_path}: invalid water record {entry!r}")
        keys = {"id", "kind", "planFeatureId"}
        if entry["kind"] == "lake":
            keys |= {"localCenter", "radii", "displayName", "baselinePlanDepth"}
            if "sourceName" in entry:
                keys.add("sourceName")
            if not isinstance(entry.get("localCenter"), list) or \
                    len(entry["localCenter"]) != 3 or \
                    not isinstance(entry.get("radii"), list) or len(entry["radii"]) != 2 or \
                    any(not isinstance(value, (int, float)) or not math.isfinite(value)
                        for value in entry["localCenter"] + entry["radii"]) or \
                    min(entry["radii"]) <= 0 or \
                    not isinstance(entry.get("displayName"), str) or \
                    ("sourceName" in entry and
                     (not isinstance(entry["sourceName"], str) or
                      not entry["sourceName"].strip())) or \
                    not isinstance(entry.get("baselinePlanDepth"), (int, float)):
                raise ValueError(f"{spec_path}: invalid lake parameters")
        if set(entry) != keys:
            raise ValueError(f"{spec_path}: unexpected {entry['kind']} water keys")
        water_ids.append(entry["planFeatureId"])
    baked_ids = []
    for entry in baked:
        if not isinstance(entry, dict) or set(entry) != {"id", "kind"} or \
                entry.get("kind") != "island" or \
                not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError(f"{spec_path}: invalid baked terrain feature {entry!r}")
        baked_ids.append(entry["id"])
    feature_ids = water_ids + baked_ids
    if len(feature_ids) != len(set(feature_ids)) or \
            set(feature_ids) != set(contract.owned_plan_feature_ids):
        raise ValueError(f"{spec_path}: bootstrap features must exactly cover owned plan features")
    REGION_ID = contract.id
    LABEL = contract.label
    TRANSLATION = np.asarray(contract.continent_translation, dtype=float)
    GRID_ORIGIN = np.asarray(contract.terrain_origin, dtype=float)
    GRID_SHAPE = contract.terrain_vertices
    GRID_STEP = contract.terrain_cell_metres
    GRID_BYTES = GRID_SHAPE[0] * GRID_SHAPE[1] * 4
    COLOR_BYTES = GRID_BYTES
    PREVIEW_UV_DENSITY = float(uv)
    OWNED_ROUTE_IDS = contract.owned_route_ids
    REQUIRED_ROUTE_IDS = contract.required_route_ids
    OWNED_PLAN_FEATURE_IDS = contract.owned_plan_feature_ids
    PUBLISHED_ASSEMBLIES = assembly_map
    BOOTSTRAP = bootstrap
    CONTRACT = contract


def verify_baseline_proof(args: argparse.Namespace) -> dict:
    """Bind every bootstrap input to one independently reviewed baseline."""
    actual_proof = sha256(args.baseline_proof)
    if actual_proof != BOOTSTRAP["baselineProofSha256"]:
        raise ValueError(f"{REGION_ID}: baseline proof hash differs from the region spec")
    proof = json.loads(args.baseline_proof.read_text(encoding="utf-8"))
    if proof.get("schema") != "eloria-published-baseline-proof-v1" or \
            proof.get("publishedClientHead") != \
            "f837588815f165bc5d62e40650d56fc90c9cafc3" or \
            proof.get("publishedServerHead") != \
            "610af2ff24c67f815a957e868023484f0bb9da40":
        raise ValueError(f"{REGION_ID}: baseline proof does not identify the published pair")
    region = proof.get("regions", {}).get(REGION_ID)
    if not isinstance(region, dict):
        raise ValueError(f"{REGION_ID}: baseline proof has no region record")
    paths = {
        "composed": args.composed, "composition": args.composition,
        "exportLedger": args.export_ledger, "publishedMaster": args.published_master,
        "roads": args.roads, "plan": args.plan,
        "crossingReport": args.crossing_report, "ferryFit": args.ferry_fit,
        "sourceWorld": args.source_world, "sourceManifest": args.source_manifest,
        "resolvedHeights": args.resolved_heights,
        "runtimeBindings": args.runtime_bindings, "runtimeReport": args.runtime_report,
    }
    expected = {**proof.get("inputs", {}), **region.get("inputs", {})}
    if set(expected) != set(paths) or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(expected[key])) or
            sha256(path) != expected[key] for key, path in paths.items()):
        raise ValueError(f"{REGION_ID}: bootstrap input differs from the reviewed baseline proof")
    certified_assemblies = region.get("assemblyIds", ())
    if not isinstance(certified_assemblies, list) or \
            len(certified_assemblies) != len(set(certified_assemblies)) or \
            set(certified_assemblies) != set(PUBLISHED_ASSEMBLIES):
        raise ValueError(f"{REGION_ID}: assembly set differs from reviewed source inventory")
    actual_roots = {
        identity: sorted(REGION_ID + "_" + name + "_WorldPlacement_WorldPlacement"
                         for name in (entry["walkNode"],
                                      *entry.get("supportNodes", [entry.get("supportNode")])))
        for identity, entry in PUBLISHED_ASSEMBLIES.items()
    }
    if region.get("assemblyRoots") != actual_roots:
        raise ValueError(f"{REGION_ID}: assembly root membership differs from reviewed master inventory")
    certified_terrain = region.get("bakedTerrainFeatureIds", ())
    declared_terrain = [entry["id"] for entry in BOOTSTRAP["bakedTerrainFeatures"]]
    if not isinstance(certified_terrain, list) or \
            sorted(certified_terrain) != sorted(declared_terrain):
        raise ValueError(f"{REGION_ID}: baked terrain claims differ from source inventory")
    return region


def validate_saved_grid(world, path: Path) -> None:
    """Prove every imported preview vertex is the final composed world sample."""
    x = TRANSLATION[0] + GRID_ORIGIN[0] + np.arange(GRID_SHAPE[0]) * GRID_STEP
    z = TRANSLATION[2] + GRID_ORIGIN[1] + np.arange(GRID_SHAPE[1]) * GRID_STEP
    x_lookup = {round(float(value), 8): index for index, value in enumerate(world.x)}
    z_lookup = {round(float(value), 8): index for index, value in enumerate(world.z)}
    try:
        ix = np.asarray([x_lookup[round(float(value), 8)] for value in x])
        iz = np.asarray([z_lookup[round(float(value), 8)] for value in z])
    except KeyError as error:
        raise ValueError(f"{REGION_ID}: saved grid lies outside final world: {error}")
    saved = np.fromfile(path, dtype="<f4").reshape(GRID_SHAPE[1], GRID_SHAPE[0])
    final = np.asarray(world.height[np.ix_(iz, ix)], dtype="<f4")
    if not np.array_equal(saved, final):
        changed = int(np.count_nonzero(saved != final))
        maximum = float(np.max(np.abs(saved.astype(float) - final.astype(float))))
        raise ValueError(f"{REGION_ID}: {changed} saved height vertices differ from "
                         f"final composed ground; maximum delta {maximum:.9g} m")


def validate_runtime_report(seed: dict, path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    if sha256(path) != seed.get("provenance", {}).get("sourceReportSha256") or \
            report.get("regionId") != REGION_ID or \
            not str(report.get("schema", "")).endswith("runtime-binding-inventory-v1"):
        raise ValueError(f"{REGION_ID}: runtime report identity/hash differs from seed")
    certified_profiles = {(entry.get("path"), entry.get("sha256"))
                          for entry in seed["provenance"]["profileFiles"]}
    if {(entry.get("path"), entry.get("sha256"))
        for entry in report.get("sources", ())} != certified_profiles:
        raise ValueError(f"{REGION_ID}: runtime report profile sources differ")
    def identity(entry: dict) -> tuple:
        source = entry.get("source", {})
        marker = entry.get("marker", {})
        return (entry.get("id"), source.get("path"), source.get("line"),
                tuple(source.get("oldTile", ())), source.get("recordId"),
                marker.get("section"), marker.get("id"),
                entry.get("role"), entry.get("roads"))
    emitted = {identity(entry): entry for entry in seed.get("bindings", ())}
    reviewed = {identity(entry): entry for entry in report.get("bindings", ())}
    if len(emitted) != len(seed.get("bindings", ())) or \
            len(reviewed) != len(report.get("bindings", ())) or set(emitted) != set(reviewed):
        raise ValueError(f"{REGION_ID}: runtime report binding identities/roles differ")
    for key, binding in emitted.items():
        reference = reviewed[key]
        if not np.allclose(binding.get("targetOffset", ()),
                           reference.get("targetOffset", ()), rtol=0, atol=2e-5):
            raise ValueError(f"{REGION_ID}: runtime binding offset differs: {key[0]}")
    counts = report.get("counts", {})
    if counts.get("bindings") != len(emitted) or \
            counts.get("existingMarkerBindings") != CONTRACT.existing_marker_binding_count or \
            counts.get("runtimePoints") != CONTRACT.runtime_point_count:
        raise ValueError(f"{REGION_ID}: runtime report counts differ from spec")


def validate_assembly_coverage(roads: dict, plan: dict, ferry_fit: dict) -> None:
    crossing_ids = {entry["key"] for entry in roads.get("crossingSites", ())
                    if entry.get("region") == REGION_ID}
    declared_crossings = {identity for identity, entry in PUBLISHED_ASSEMBLIES.items()
                          if entry["kind"] == "crossing"}
    if crossing_ids - declared_crossings:
        raise ValueError(f"{REGION_ID}: source crossing sites lack saved Walk assemblies: "
                         f"{sorted(crossing_ids - declared_crossings)}")
    access_walks = {entry["walkNode"] for entry in PUBLISHED_ASSEMBLIES.values()
                    if entry["kind"] == "access"}
    deck_walks = {entry["name"] for entry in plan.get("access_decks", ())
                  if entry.get("region") == REGION_ID}
    if deck_walks - access_walks:
        raise ValueError(f"{REGION_ID}: source access decks lack saved Walk assemblies: "
                         f"{sorted(deck_walks - access_walks)}")
    ferry_rows = [entry for entry in ferry_fit.get("landings", ())
                  if entry.get("region") == REGION_ID]
    source_ferry_walks = {entry["walkNode"] for entry in ferry_rows}
    declared_ferry_walks = {entry["walkNode"] for entry in PUBLISHED_ASSEMBLIES.values()
                            if entry["walkNode"].startswith("Walk_FerryQuay_")}
    if source_ferry_walks != declared_ferry_walks or \
            tuple(sorted({connection for entry in ferry_rows
                          for connection in entry["connectionIds"]})) != \
            getattr(CONTRACT, "owned_ferry_connection_ids", ()):
        raise ValueError(f"{REGION_ID}: saved ferry assemblies/connections differ from source fit")
    island_ids = {entry.get("crownSourceIsland") for entry in plan.get("islands", ())
                  if entry.get("crownSourceIsland")}
    for entry in BOOTSTRAP["bakedTerrainFeatures"]:
        if entry["kind"] == "island" and entry["id"] not in island_ids:
            raise ValueError(f"{REGION_ID}: claimed baked island {entry['id']} absent from source plan")


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
    source_digests = {}
    for obj in objects:
        source_region = str(obj.get("libraryRegion", REGION_ID))
        document, body = content.documents[source_region]
        if source_region not in source_digests:
            hasher = hashlib.sha256(json.dumps(
                document, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode())
            hasher.update(body)
            source_digests[source_region] = hasher.hexdigest()
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
        family_key = (identity, source_region, source_digests[source_region], signatures)
        family = f"{slug(identity)}-{hashlib.sha256(repr(family_key).encode()).hexdigest()[:12]}"
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
    identities = sorted(entry["id"] for entry in records)
    identity_sha = hashlib.sha256(json.dumps(
        identities, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if len(records) != BOOTSTRAP["objectCount"] or \
            len(set(identities)) != len(identities) or \
            identity_sha != BOOTSTRAP["objectIdsSha256"]:
        raise ValueError(
            f"{REGION_ID}: final composition object identities differ from bootstrap: "
            f"count={len(records)}, sha256={identity_sha}")
    return sorted(records, key=lambda entry: entry["id"]), families


def write_prototypes(content, families: dict, output: Path,
                     resource_root: str, scene_io) -> dict[str, dict]:
    prototype_dir = output / "assets/prototypes"
    texture_dir = output / "assets/textures"
    prototype_dir.mkdir(parents=True, exist_ok=True)
    records = {}
    for family in sorted(families):
        representative = min(families[family], key=lambda entry: entry["id"])
        document, body = content.documents[representative["sourceRegion"]]
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

    global_x = TRANSLATION[0] + GRID_ORIGIN[0] + np.arange(GRID_SHAPE[0]) * GRID_STEP
    global_z = TRANSLATION[2] + GRID_ORIGIN[1] + np.arange(GRID_SHAPE[1]) * GRID_STEP
    x_lookup = {round(float(value), 8): index for index, value in enumerate(world.x)}
    z_lookup = {round(float(value), 8): index for index, value in enumerate(world.z)}
    try:
        x_indices = np.asarray([x_lookup[round(float(value), 8)] for value in global_x])
        z_indices = np.asarray([z_lookup[round(float(value), 8)] for value in global_z])
    except KeyError as error:
        raise ValueError(f"{REGION_ID} color grid is outside certified composed terrain: {error}")
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
        raise ValueError(f"{REGION_ID} RGBA8 color sidecar length mismatch")

    compared = 0
    max_uv_error = 0.0
    for node in published_document.get("nodes", ()):
        name = str(node.get("name", ""))
        if not name.startswith(f"Terrain_{REGION_ID}_") or "mesh" not in node:
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
            column = int(round((float(position[0]) - global_x[0]) / GRID_STEP))
            row = int(round((float(position[2]) - global_z[0]) / GRID_STEP))
            if not (0 <= column < GRID_SHAPE[0] and 0 <= row < GRID_SHAPE[1]):
                raise ValueError(f"Published {REGION_ID} vertex is outside saved color grid: {position}")
            if not np.array_equal(rgba8[row, column], np.asarray(color, dtype=np.uint8)):
                raise ValueError(f"Published {REGION_ID} color differs at XZ {position[[0, 2]]}")
            max_uv_error = max(max_uv_error, float(np.max(np.abs(
                np.asarray(texture_uv, float) -
                np.asarray(position[[0, 2]], float) * PREVIEW_UV_DENSITY))))
            compared += 1
    if compared == 0 or max_uv_error > 2.0e-5:
        raise ValueError(
            f"{REGION_ID} published terrain validation failed: vertices={compared}, uv={max_uv_error}")
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
                   resource_root: str, scene_io,
                   ferry_fit: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
    """Copy the exact published bridge and lake-bank assemblies as assets."""
    import glb_reader
    by_name = {node.get("name", ""): index for index, node in enumerate(document["nodes"])}
    matrices, _parents = glb_reader.hierarchy(document)
    sites = {entry["key"]: entry for entry in roads.get("crossingSites", ())}
    result, prototypes = [], {}
    for stable_id, entry in sorted(PUBLISHED_ASSEMBLIES.items()):
        walk = entry["walkNode"]
        supports = entry.get("supportNodes", [entry.get("supportNode")])
        root_names = [name + "_WorldPlacement" for name in (walk, *supports)]
        roots = [by_name.get(name, -1) for name in root_names]
        if -1 in roots:
            raise ValueError(f"Published {REGION_ID} assembly {stable_id!r} is incomplete")
        control = np.asarray(matrices[roots[0]], dtype=float)
        inverse = np.linalg.inv(control)
        private = copy.deepcopy(document)
        for root in roots:
            node = private["nodes"][root]
            for field in ("translation", "rotation", "scale"):
                node.pop(field, None)
            node["matrix"] = matrix_list(inverse @ np.asarray(matrices[root], float))
        family = f"published-{slug(REGION_ID)}-{slug(stable_id)}"
        target = output / "assets/prototypes" / f"{family}.glb"
        exporter = scene_io.Exporter(target, shared_images=output / "assets/textures")
        exporter.add(private, body, roots,
                     root_names={root: private["nodes"][root]["name"] for root in roots})
        stats = exporter.write()
        asset_id = family
        metadata = {"authoredAccessAssembly": {"id": stable_id,
                                                 "walkNode": walk}}
        if entry["kind"] == "crossing":
            if stable_id not in sites:
                raise ValueError(f"{REGION_ID}: crossing {stable_id} missing from roads")
            site = sites[stable_id]
            endpoints = [[float(x), float(site["deckLevel"]), float(z)]
                         for x, z in site["routeLandings"]]
            local_endpoints = [
                (inverse @ np.asarray([*point, 1.0]))[:3].tolist()
                for point in endpoints]
            metadata = {"authoredCrossing": {
                "id": stable_id, "river": str(site.get("river", "")),
                "walkNode": walk, "localEndpoints": local_endpoints}}
        elif stable_id in sites:
            raise ValueError(f"{REGION_ID}: access assembly {stable_id} is a crossing site")
        if walk.startswith("Walk_FerryQuay_"):
            matches = [row for row in (ferry_fit or {}).get("landings", ())
                       if row.get("region") == REGION_ID and row.get("walkNode") == walk]
            if len(matches) != 1:
                raise ValueError(f"{REGION_ID}: ferry quay {walk} lacks one certified source fit")
            row = matches[0]
            local_landing = (inverse @ np.asarray([*row["landing"], 1.0]))[:3].tolist()
            metadata["authoredFerryQuay"] = {
                "connectionIds": row["connectionIds"], "walkNode": walk,
                "localLanding": local_landing}
        record = {
            "id": asset_id, "nodeName": root_names[0], "family": family,
            "matrix": control.copy(),
            "collisionRole": "walk_surface" if walk.startswith("Walk_") else "none",
            "metadata": metadata,
        }
        record["matrix"][:3, 3] -= TRANSLATION
        result.append(record)
        prototypes[family] = {
            "path": f"{resource_root}/assets/prototypes/{target.name}",
            "sha256": sha256(target), "representative": asset_id,
            "instances": 1, "roots": len(roots), "stats": stats,
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
                 resource_root: str) -> tuple[list[dict], list[dict]]:
    roads = {entry["id"]: entry for entry in roads_document["roads"]}
    if missing := sorted(set(OWNED_ROUTE_IDS) - roads.keys()):
        raise ValueError(f"Published roads are missing {REGION_ID}-owned routes: {missing}")
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
    waters = []
    for entry in BOOTSTRAP["water"]:
        identity = entry["planFeatureId"]
        if entry["kind"] == "river":
            matches = [source for source in plan.get("rivers", ())
                       if source.get("id") == identity]
            if len(matches) != 1 or len(matches[0].get("points", ())) < 2:
                raise ValueError(f"{REGION_ID}: plan river {identity} is missing")
            source = matches[0]
            points = [[float(point[0] - TRANSLATION[0]), float(point[2]),
                       float(point[1] - TRANSLATION[2])]
                      for point in legacy_curved_points(source["points"])]
            curve = output / "paths" / f"{slug(entry['id'])}.tres"
            write_curve(curve, points)
            waters.append({
                "id": entry["id"], "kind": "river", "planFeatureId": identity,
                "points": points, "sourceControlPointCount": len(source["points"]),
                "sampling": "legacy-open-catmull-rom-6x-zero-handles",
                "width": float(source["width"]) * 2.0,
                "curve": f"{resource_root}/paths/{curve.name}",
                "properties": {
                    "terrainConform": False, "terrainFeather": 2.0,
                    "name": str(source.get("name", identity)),
                    "channelDepth": float(source["depth"]),
                    "valleyWidth": float(source["valley_width"]),
                    "bankHeight": float(source["bank_height"]),
                    "bankShelfWidth": float(source.get("bank_shelf_width", 0.0)),
                    "cutsRelief": bool(source.get("cuts_relief", False)),
                    "joins": str(source.get("joins", "")),
                },
            })
        else:
            source_name = entry.get("sourceName")
            matches = [source for source in plan.get("lakes", ())
                       if (source.get("id") == identity and source_name is None) or
                       (source_name is not None and "id" not in source and
                        source.get("name") == source_name)]
            if len(matches) != 1:
                raise ValueError(f"{REGION_ID}: plan lake {identity} is missing")
            source = matches[0]
            center = entry["localCenter"]
            expected_center = [float(source["center"][0] - TRANSLATION[0]),
                               float(source["level"]),
                               float(source["center"][1] - TRANSLATION[2])]
            if not np.allclose(center, expected_center, rtol=0, atol=1e-5) or \
                    not np.allclose(entry["radii"], source["radii"], rtol=0, atol=1e-5) or \
                    not math.isclose(float(entry["baselinePlanDepth"]),
                                     float(source["depth"]), abs_tol=1e-5):
                raise ValueError(f"{REGION_ID}: lake {identity} differs from published plan")
            waters.append(entry.copy())
    return result, waters


def marker_records(manifest: dict, objects: list[dict]) -> list[dict]:
    by_node = {entry["nodeName"]: entry for entry in objects}
    result = []
    for source_key, container, kind in GAMEPLAY:
        for source in manifest.get(source_key, ()):
            position = source.get("position", source.get("center", source.get("centre")))
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
    if len(result) != BOOTSTRAP["visibleGameplayCount"]:
        raise ValueError(f"{REGION_ID}: certified visible gameplay count differs: {len(result)}")
    counts = defaultdict(int)
    for entry in result:
        counts[(entry["container"], entry["id"])] += 1
    for entry in result:
        entry["sceneNodeName"] = (entry["id"] + "--" + slug(entry["node"])
                                  if counts[(entry["container"], entry["id"])] > 1
                                  else entry["id"])
    if len({(entry["container"], entry["sceneNodeName"]) for entry in result}) != len(result):
        raise ValueError(f"{REGION_ID}: gameplay marker scene nodes are not unique")
    return sorted(result, key=lambda entry: (entry["container"], entry["id"],
                                              entry["sceneNodeName"]))


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
        raise ValueError(f"Runtime binding seed schema/region does not match {REGION_ID}")
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
    if not seen or len(seen) != int(expected.get("bindings", -1)) or \
            runtime_count != int(expected.get("runtimePoints", -1)):
        raise ValueError(f"Runtime binding seed counts do not match {REGION_ID} controls")


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
uv1_offset = Vector3(0.8, 0.5, 0)
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
uv1_offset = Vector3(0.8, 0.5, 0)
texture_filter = 4

[resource]
resource_local_to_scene = true
script = ExtResource("1_surface")
texture_preset = "Custom"
rotation_degrees = 0.0
source_material = SubResource("StandardMaterial3D_water")
''', encoding="utf-8", newline="\n")


def write_scene(output: Path, manifest: dict, objects: list[dict], prototypes: dict,
                paths: list[dict], waters: list[dict], markers: list[dict], resource_root: str,
                runtime_seed_res: str, runtime_seed_sha: str) -> None:
    resources = [
        ("Script", "res://src/dev/map_authoring_region/region_control.gd", "region"),
        ("Script", "res://src/dev/map_authoring_region/terrain_control.gd", "terrain"),
        ("Script", "res://src/dev/map_authoring_region/path_control.gd", "path"),
        ("Script", "res://src/dev/map_authoring_region/water_region_control.gd", "water"),
        ("Script", "res://src/dev/map_authoring_region/asset_control.gd", "asset"),
        ("Script", "res://src/dev/map_authoring_region/gameplay_marker.gd", "marker"),
        ("Resource", f"{resource_root}/surfaces/continental-ground.tres", "terrain_surface"),
        ("Resource", f"{resource_root}/surfaces/road.tres", "road_surface"),
        ("Resource", f"{resource_root}/surfaces/river.tres", "river_surface"),
    ]
    all_paths = paths + [water for water in waters if water["kind"] == "river"]
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
    scene_root = "".join(part.title() for part in re.split(r"[^A-Za-z0-9]+", LABEL) if part)
    export_path = "res://../" + CONTRACT.snapshot_path.parent.relative_to(
        Path(__file__).resolve().parents[2]).as_posix()
    lines.extend(("", f'[node name={godot_string(scene_root)} type="Node3D"]',
                  'script = ExtResource("region")', f'region_id = "{REGION_ID}"',
                  'continent_translation = Vector3(' + ', '.join(
                      gd_float(value) for value in TRANSLATION) + ')',
                  'metres_per_tile = 1.0',
                  'server_origin = Vector2i(' + ', '.join(map(str, CONTRACT.server_origin)) + ')',
                  'server_cells = Vector2i(' + ', '.join(map(str, CONTRACT.server_cells)) + ')',
                  'collision_origin_metres = Vector2(' + ', '.join(
                      gd_float(value) for value in CONTRACT.collision_origin_metres) + ')',
                  f'ownership_polygon_sha256 = "{ownership_sha}"',
                  f'seam_anchors = {godot_value(manifest["streamingBorders"])}',
                  'owned_route_ids = PackedStringArray(' + ", ".join(
                      godot_string(value) for value in OWNED_ROUTE_IDS) + ')',
                  'owned_plan_feature_ids = PackedStringArray(' + ', '.join(
                      godot_string(value) for value in OWNED_PLAN_FEATURE_IDS) + ')',
                  'owned_ferry_connection_ids = PackedStringArray(' + ', '.join(
                      godot_string(value) for value in
                      getattr(CONTRACT, "owned_ferry_connection_ids", ())) + ')',
                  f'runtime_binding_seed_path = {godot_string(runtime_seed_res)}',
                  f'runtime_binding_seed_sha256 = {godot_string(runtime_seed_sha)}',
                  f'export_directory = {godot_string(export_path)}',
                  "", '[node name="Terrain" type="Node3D" parent="."]',
                  'script = ExtResource("terrain")',
                  'origin = Vector2(' + ', '.join(gd_float(value) for value in GRID_ORIGIN) + ')',
                  f'cell_metres = {gd_float(GRID_STEP)}',
                  'grid_size = Vector2i(' + ', '.join(map(str, GRID_SHAPE)) + ')',
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
    lines.extend(('[node name="Rivers" type="Node3D" parent="."]', ""))
    for river in (entry for entry in waters if entry["kind"] == "river"):
        lines.extend((f'[node name={godot_string(node_name(river["id"]))} type="Path3D" parent="Rivers"]',
                      'script = ExtResource("path")',
                      f'curve = ExtResource("{river["resourceId"]}")',
                      f'path_id = {godot_string(river["id"])}', 'kind = "river"',
                      'routing_role = "decorative"',
                      f'replaces_plan_feature_id = {godot_string(river["planFeatureId"])}',
                      f'properties = {godot_value(river["properties"])}',
                      f'default_width = {gd_float(river["width"])}',
                      'surface = ExtResource("river_surface")', ""))
    lines.extend(('[node name="WaterRegions" type="Node3D" parent="."]', ""))
    for lake in (entry for entry in waters if entry["kind"] == "lake"):
        lines.extend((f'[node name={godot_string(node_name(lake["id"]))} type="Node3D" parent="WaterRegions"]',
                      'script = ExtResource("water")',
                      'position = Vector3(' + ', '.join(
                          gd_float(value) for value in lake["localCenter"]) + ')',
                      f'water_id = {godot_string(lake["id"])}',
                      f'replaces_plan_feature_id = {godot_string(lake["planFeatureId"])}',
                      f'display_name = {godot_string(lake["displayName"])}',
                      'radii = Vector2(' + ', '.join(
                          gd_float(value) for value in lake["radii"]) + ')',
                      f'baseline_plan_depth = {gd_float(lake["baselinePlanDepth"])}', ""))
    lines.extend(('[node name="Bridges" type="Node3D" parent="."]', "",
                  '[node name="AuthoredAssets" type="Node3D" parent="."]', ""))
    for record in objects:
        prototype = prototypes[record["family"]]
        path = f'AuthoredAssets/{node_name(record["id"])}'
        lines.extend((f'[node name={godot_string(node_name(record["id"]))} type="Node3D" parent="AuthoredAssets"]',
                      'script = ExtResource("asset")', f'transform = {transform3d(record["matrix"])}',
                      f'asset_id = {godot_string(record["id"])}',
                      f'node_name = {godot_string(record["nodeName"])}',
                      f'catalog_asset_id = {godot_string(REGION_ID + ":" + record["family"])}',
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
        lines.extend((f'[node name={godot_string(node_name(marker.get("sceneNodeName", marker["id"]))) } type="Marker3D" parent={godot_string(parent)}]',
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
    (output / f"{REGION_ID}.tscn").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n")


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region-spec", type=Path, required=True)
    parser.add_argument("--baseline-proof", type=Path, required=True)
    parser.add_argument("--runtime-report", type=Path, required=True)
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
    parser.add_argument("--crossing-report", type=Path, required=True)
    parser.add_argument("--ferry-fit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    configure(args.region_spec)
    proof_region = verify_baseline_proof(args)
    repo = Path(__file__).resolve().parents[2]
    for path in (repo / "eloria-assets/maps/nymara-regions/_toolkit",
                 repo / "eloria-assets/maps/nymara-regions/_continent"):
        if str(path) not in sys.path: sys.path.insert(0, str(path))
    import glb_reader
    import scene_io
    import capture_composed_region

    output = args.output.resolve(); project = (repo / "godot-client").resolve()
    if output != CONTRACT.scene_path.parent.resolve():
        raise ValueError(f"{REGION_ID}: output differs from declared scene directory")
    resource_root = "res://" + output.relative_to(project).as_posix()
    scene_path = CONTRACT.scene_path
    if scene_path.exists() and not args.force:
        raise ValueError(f"Refusing to overwrite existing {REGION_ID} scene without --force")
    if args.resolved_heights.stat().st_size != GRID_BYTES:
        raise ValueError(f"{REGION_ID} resolved grid must contain {GRID_BYTES} bytes")
    if sha256(args.base_heights) != sha256(args.resolved_heights):
        raise ValueError(f"{REGION_ID} requires the certified resolved grid as saved base")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.resolved_heights, output / "base-heights.f32le")
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    if manifest.get("asset", {}).get("id") != REGION_ID:
        raise ValueError(f"{REGION_ID}: source manifest identity differs")
    roads = json.loads(args.roads.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    ferry_fit = json.loads(args.ferry_fit.read_text(encoding="utf-8"))
    if ferry_fit.get("schema") != "eloria-published-ferry-fit-landings-v1" or \
            ferry_fit.get("composedSha256") != sha256(args.composed) or \
            ferry_fit.get("crossingReportSha256") != sha256(args.crossing_report):
        raise ValueError(f"{REGION_ID}: ferry fit source differs from certified composition")
    validate_assembly_coverage(roads, plan, ferry_fit)
    capture = capture_composed_region.load(
        REGION_ID, args.composed, args.composition, args.export_ledger,
        args.published_master, args.source_manifest)
    validate_saved_grid(capture.world, args.resolved_heights)
    objects, families = final_object_records(capture.content, capture.objects)
    prototypes = write_prototypes(capture.content, families, output, resource_root, scene_io)
    published_document, published_body = glb_reader.load(args.published_master)
    bridges, bridge_prototypes = bridge_records(
        published_document, published_body, roads, output, resource_root,
        scene_io, ferry_fit)
    objects.extend(bridges); objects.sort(key=lambda entry: entry["id"])
    prototypes.update(bridge_prototypes)
    color_record = terrain_colors(
        capture.world, published_document, published_body, output)
    prune_generated_assets(output, prototypes)
    paths, waters = path_records(roads, plan, output, resource_root)
    markers = marker_records(manifest, objects)
    seed = canonical_runtime_seed(json.loads(args.runtime_bindings.read_text(encoding="utf-8")))
    validate_runtime_report(seed, args.runtime_report)
    validate_runtime_seed_profiles(seed, args.runtime_profile_root)
    if len(seed.get("bindings", ())) != CONTRACT.runtime_binding_count or \
            int(seed.get("counts", {}).get("runtimePoints", -1)) != \
            CONTRACT.runtime_point_count or \
            sum(binding.get("marker", {}).get("section") != "runtimePoints"
                for binding in seed.get("bindings", ())) != \
            CONTRACT.existing_marker_binding_count:
        raise ValueError(f"{REGION_ID}: runtime seed counts differ from authoring spec")
    seed_path = output / "runtime-bindings.seed.json"
    seed_path.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8", newline="\n")
    apply_runtime_seed(markers, seed)
    write_terrain_surface(output / "surfaces/continental-ground.tres", resource_root)
    write_surface(output / "surfaces/road.tres", "Worn earth", road=True)
    write_river_surface(output / "surfaces/river.tres", resource_root)
    seed_res = f"{resource_root}/runtime-bindings.seed.json"
    write_scene(output, manifest, objects, prototypes, paths, waters, markers,
                resource_root, seed_res, sha256(seed_path))
    provenance = {
        "schema": "eloria-published-region-authoring-migration-v1", "regionId": REGION_ID,
        "bootstrapSpecSha256": sha256(args.region_spec),
        "baselineProofSha256": sha256(args.baseline_proof),
        "sourceAssemblyIds": proof_region["assemblyIds"],
        "inputs": {
            "sourceWorldSha256": sha256(args.source_world),
            "sourceManifestSha256": sha256(args.source_manifest),
            "roadsSha256": sha256(args.roads), "planSha256": sha256(args.plan),
            "crossingReportSha256": sha256(args.crossing_report),
            "ferryFitSha256": sha256(args.ferry_fit),
            "certifiedBootstrapHeightsSha256": sha256(args.base_heights),
            "authoredBaseHeightsSha256": sha256(output / "base-heights.f32le"),
            "certifiedResolvedHeightsSha256": sha256(args.resolved_heights),
            "runtimeBindingSeedSha256": sha256(seed_path),
            "baseColors": color_record, **capture.provenance,
        },
        "counts": {
            "objects": len(capture.objects), "publishedAssemblies": len(bridges),
            "savedAssetControls": len(objects),
            "prototypeFamilies": len(prototypes), "paths": len(paths),
            "waterFeatures": len(waters),
            "riverControlPoints": sum(w.get("sourceControlPointCount", 0) for w in waters),
            "riverCurvePoints": sum(len(w.get("points", ())) for w in waters),
            "visibleGameplay": BOOTSTRAP["visibleGameplayCount"],
            "runtimeBindings": len(seed.get("bindings", ())),
            "runtimePoints": sum(entry["kind"] == "runtime_point" for entry in markers),
        },
        "crossings": [{"id": entry["metadata"]["authoredCrossing"]["id"],
                       "assetId": entry["id"],
                       "walkNode": entry["metadata"]["authoredCrossing"]["walkNode"]}
                      for entry in bridges if "authoredCrossing" in entry["metadata"]],
        "accessAssemblies": [
            {"id": entry["metadata"]["authoredAccessAssembly"]["id"],
             "assetId": entry["id"],
             "walkNode": entry["metadata"]["authoredAccessAssembly"]["walkNode"]}
            for entry in bridges if "authoredAccessAssembly" in entry["metadata"]],
        "objects": [{"id": entry["id"], "family": entry["family"],
                     "collisionRole": entry["collisionRole"]} for entry in objects],
    }
    provenance["sceneSha256"] = sha256(scene_path)
    (output / "migration-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print(f"published_authoring_import_ok region={REGION_ID} scene={scene_path} "
          f"sha256={provenance['sceneSha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
