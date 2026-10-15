#!/usr/bin/env python3
"""One-time, deterministic migration of published Sunmane into Godot authoring.

The generated scene owns editable controls and references reusable prototype
GLBs. It never embeds the composed terrain/water world as an opaque scene.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


REGION_ID = "sunmane_steppe"
TRANSLATION = np.array([1200.0, 0.0, 720.0])
GRID_BYTES = 397 * 397 * 4
EXCLUDED_ROOT_PREFIXES = (
    "sunmane_steppe_Walk_ContinentalBridgeUnion",
    "sunmane_steppe_BridgeUnion",
    "sunmane_steppe_Walk__StreamThreshold",
)
OWNED_ROUTE_IDS = (
    "mirrorhold--sunmane_steppe-sunmane_steppe",
    "amethyst_barrens--sunmane_steppe-sunmane_steppe",
    "sunmane_steppe--verdant_stair-sunmane_steppe",
    "door-sunmane_steppe-cave-wind_caves",
    "door-sunmane_steppe-cave-crystal_hollow",
    *(f"discovery-sunmane_steppe-{index}" for index in range(301, 314)),
    "discovery-sunmane_steppe-713",
)
GAMEPLAY = (
    ("spawns", "Spawns", "spawn"),
    ("portals", "Portals", "portal"),
    ("interactives", "Interactives", "interactive"),
    ("landmarks", "Landmarks", "landmark"),
    ("harvestables", "Harvestables", "harvestable"),
    ("npcMarkers", "NpcMarkers", "npc_marker"),
)
GAMEPLAY_OUTPUT_SECTIONS = {
    "spawn": "spawnPoints", "portal": "portals", "interactive": "interactives",
    "landmark": "landmarks", "harvestable": "harvestables",
    "npc_marker": "npcMarkers", "ambient_population": "ambientPopulation",
    "runtime_point": "runtimePoints",
}
RUNTIME_POINT_GROUPS = {
    "return": "Returns", "interactive": "Interactions", "npc": "Npcs",
    "harvest": "Harvestables", "spawn": "CreatureSpawns",
    "territory": "TerritoryPoints",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "asset"


def repo_path(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.name


def godot_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def godot_value(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return godot_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("Godot values must be finite")
        return format(value, ".12g")
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(godot_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(
            f"{godot_string(str(key))}: {godot_value(value[key])}"
            for key in sorted(value)
        ) + "}"
    raise TypeError(f"Unsupported Godot value {type(value).__name__}")


def gd_float(value: float) -> str:
    if abs(value) < 5e-13:
        value = 0.0
    return format(float(value), ".12g")


def transform3d(matrix: np.ndarray) -> str:
    values = [
        matrix[0, 0], matrix[0, 1], matrix[0, 2],
        matrix[1, 0], matrix[1, 1], matrix[1, 2],
        matrix[2, 0], matrix[2, 1], matrix[2, 2],
        matrix[0, 3], matrix[1, 3], matrix[2, 3],
    ]
    return "Transform3D(" + ", ".join(gd_float(v) for v in values) + ")"


def node_name(value: str) -> str:
    result = re.sub(r"[.:@/\"%\\]+", "", value).strip()
    return result or "Record"


def descendants(document: dict, root: int) -> list[int]:
    result: list[int] = []
    stack = [root]
    while stack:
        index = stack.pop()
        result.append(index)
        stack.extend(reversed(document["nodes"][index].get("children", ())))
    return result


def embed_external_images(document: dict, body: bytes, source_path: Path):
    """Give the certified subtree exporter embedded source images to copy."""
    document = copy.deepcopy(document)
    packed = bytearray(body)
    for index, image in enumerate(document.get("images", ())):
        uri = image.get("uri")
        if uri is None:
            continue
        if uri.startswith("data:"):
            raise ValueError("Data URI images are unsupported in the migration source")
        image_path = (source_path.parent / uri).resolve()
        if not image_path.is_file():
            raise ValueError(f"Source image {index} is missing: {image_path}")
        packed.extend(b"\0" * (-len(packed) % 4))
        offset = len(packed)
        payload = image_path.read_bytes()
        packed.extend(payload)
        document.setdefault("bufferViews", []).append({
            "buffer": 0, "byteOffset": offset, "byteLength": len(payload),
        })
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") \
            else "image/png"
        document["images"][index] = {
            "bufferView": len(document["bufferViews"]) - 1,
            "mimeType": mime,
            "name": image.get("name", image_path.stem),
        }
    return document, bytes(packed)


def prototype_family(document: dict, root: int) -> str:
    names = [document["nodes"][index].get("name", "")
             for index in descendants(document, root)]
    kits = sorted(set(match.group(1) for name in names
                      if (match := re.search(r"__Kit_(.+?)__(?:solid|walk)__", name))))
    if kits:
        return "kit-" + "+".join(kits)
    root_name = document["nodes"][root].get("name", str(root))
    outcrop = re.match(r"Outcrop_\d+_\d+_(.+)", root_name)
    if outcrop:
        return "outcrop-" + outcrop.group(1)
    if re.fullmatch(r"Structure_Bridge_\d+", root_name):
        return "structure-bridge"
    return "root-" + root_name


def object_records(document: dict, matrices: dict[int, np.ndarray], collision: set[str]):
    records = []
    families: dict[str, list[dict]] = defaultdict(list)
    roots = document["scenes"][document.get("scene", 0)]["nodes"]
    for wrapper_index in roots:
        wrapper = document["nodes"][wrapper_index]
        wrapper_name = wrapper.get("name", "")
        if not wrapper_name.startswith("sunmane_steppe_"):
            continue
        if wrapper_name.startswith(EXCLUDED_ROOT_PREFIXES):
            continue
        children = wrapper.get("children", ())
        if len(children) != 1:
            raise ValueError(f"{wrapper_name} must have one source root, got {len(children)}")
        source_root = children[0]
        source_name = document["nodes"][source_root].get("name", "")
        if not source_name:
            raise ValueError(f"{wrapper_name} has no stable source node name")
        family = prototype_family(document, source_root)
        record = {
            "id": source_name,
            "nodeName": source_name,
            "sourceWrapper": wrapper_name,
            "sourceRoot": source_root,
            "family": family,
            "matrix": matrices[source_root],
            "collisionRole": "solid" if source_name in collision else "none",
        }
        records.append(record)
        families[family].append(record)
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Published Sunmane object identities are not unique")
    return sorted(records, key=lambda record: record["id"]), families


def published_terrain_heights(document: dict, body: bytes, matrices: dict[int, np.ndarray],
                              glb_reader) -> dict[tuple[int, int], float]:
    samples: dict[tuple[int, int], list[float]] = defaultdict(list)
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
                if (0 <= x_index < 397 and 0 <= z_index < 397 and
                        abs(float(x) - (-194.0 + x_index * 2.0)) < 1e-4 and
                        abs(float(z) - (-500.0 + z_index * 2.0)) < 1e-4):
                    samples[(x_index, z_index)].append(float(y))
    return {key: max(values) for key, values in samples.items()}


def sample_height(values, x: float, z: float) -> float | None:
    fx = (x + 194.0) / 2.0
    fz = (z + 500.0) / 2.0
    x0, z0 = math.floor(fx), math.floor(fz)
    if not (0 <= x0 < 396 and 0 <= z0 < 396):
        return None
    corners = ((x0, z0), (x0 + 1, z0), (x0, z0 + 1), (x0 + 1, z0 + 1))
    heights = []
    for key in corners:
        if isinstance(values, dict):
            if key not in values:
                return None
            heights.append(float(values[key]))
        else:
            heights.append(float(values[key[1] * 397 + key[0]]))
    tx, tz = fx - x0, fz - z0
    return (heights[0] * (1.0 - tx) * (1.0 - tz) +
            heights[1] * tx * (1.0 - tz) +
            heights[2] * (1.0 - tx) * tz + heights[3] * tx * tz)


def apply_vertical_migration(objects: list[dict], markers: list[dict],
                             published: dict[tuple[int, int], float],
                             resolved: np.ndarray) -> dict:
    """Move initial content with the clean authored terrain once, then save it."""
    object_deltas = {}
    unmatched_objects = []
    for record in objects:
        matrix = record["matrix"]
        old = sample_height(published, float(matrix[0, 3]), float(matrix[2, 3]))
        new = sample_height(resolved, float(matrix[0, 3]), float(matrix[2, 3]))
        if old is None or new is None:
            unmatched_objects.append(record["id"])
            delta = 0.0
        else:
            delta = float(new - old)
            matrix[1, 3] += delta
        record["migrationYDelta"] = delta
        object_deltas[record["id"]] = delta

    unmatched_markers = []
    for record in markers:
        followed = record["followAssetId"]
        if followed:
            delta = object_deltas[followed]
        else:
            x, _, z = record["position"]
            old = sample_height(published, x, z)
            new = sample_height(resolved, x, z)
            if old is None or new is None:
                unmatched_markers.append(f'{record["container"]}/{record["id"]}')
                delta = 0.0
            else:
                delta = float(new - old)
        record["position"][1] += delta
        record["migrationYDelta"] = delta
    return {
        "method": "saved one-time centre vertical shift preserving published clearance",
        "objects": {record["id"]: record["migrationYDelta"] for record in objects},
        "gameplay": {f'{record["container"]}/{record["id"]}':
                     record["migrationYDelta"] for record in markers},
        "unmatchedObjects": unmatched_objects,
        "unmatchedGameplay": unmatched_markers,
    }


def write_prototypes(source_document: dict, source_body: bytes, families: dict,
                     output: Path, resource_root: str, scene_io) -> dict[str, dict]:
    prototype_dir = output / "assets" / "prototypes"
    texture_dir = output / "assets" / "textures"
    prototype_dir.mkdir(parents=True, exist_ok=True)
    expected = set()
    records = {}
    slugs = [slug(family) for family in families]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Prototype family names collide after path normalization")
    for family in sorted(families):
        representative = min(families[family], key=lambda record: record["id"])
        family_slug = slug(family)
        target = prototype_dir / f"{family_slug}.glb"
        expected.add(target.name)
        private_document = copy.deepcopy(source_document)
        source_root = representative["sourceRoot"]
        private_root = private_document["nodes"][source_root]
        for field in ("matrix", "translation", "rotation", "scale"):
            private_root.pop(field, None)
        exporter = scene_io.Exporter(target, shared_images=texture_dir)
        exporter.add(private_document, source_body, [source_root],
                     root_names={source_root: family_slug})
        stats = exporter.write()
        records[family] = {
            "path": f"{resource_root}/assets/prototypes/{target.name}",
            "sha256": sha256(target),
            "representative": representative["id"],
            "instances": len(families[family]),
            "stats": stats,
        }
    for old in prototype_dir.glob("*.glb"):
        if old.name not in expected:
            old.unlink()
    return records


def write_curve(path: Path, points: list[list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    packed = []
    for point in points:
        packed.extend((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, *point))
    tilts = ", ".join("0" for _ in points)
    path.write_text(
        "[gd_resource type=\"Curve3D\" format=3]\n\n"
        "[resource]\nresource_local_to_scene = true\n"
        "_data = {\n\"points\": PackedVector3Array(" +
        ", ".join(gd_float(value) for value in packed) +
        "),\n\"tilts\": PackedFloat32Array(" + tilts + ")\n}\n"
        f"point_count = {len(points)}\n", encoding="utf-8", newline="\n")


def local_road_points(record: dict) -> list[list[float]]:
    return [[float(point[0] - TRANSLATION[0]), float(point[1]),
             float(point[2] - TRANSLATION[2])] for point in record["points"]]


def local_river_points(record: dict) -> list[list[float]]:
    return [[float(point[0] - TRANSLATION[0]), float(point[2]),
             float(point[1] - TRANSLATION[2])] for point in record["points"]]


def legacy_curved_points(points: list[list[float]]) -> list[list[float]]:
    """Freeze landscape.curved_points' six samples per open Catmull-Rom span.

    X/Z follow the legacy horizontal spline while every trailing attribute
    (the river's hydraulic Y here) remains linearly interpolated. Saving these
    exact samples as zero-handle Curve3D points makes the editor preview and
    authored production record the same editable polyline.
    """
    source = np.asarray(points, dtype=np.float64)
    sampled = []
    for index in range(len(source) - 1):
        first, second = source[index], source[index + 1]
        before = source[index - 1] if index else first * 2.0 - second
        after = (source[index + 2] if index + 2 < len(source)
                 else second * 2.0 - first)
        for amount in np.arange(6, dtype=np.float64) / 6.0:
            horizontal = 0.5 * (
                2.0 * first[:2] + (-before[:2] + second[:2]) * amount
                + (2.0 * before[:2] - 5.0 * first[:2]
                   + 4.0 * second[:2] - after[:2]) * amount * amount
                + (-before[:2] + 3.0 * first[:2] - 3.0 * second[:2]
                   + after[:2]) * amount * amount * amount)
            sampled.append(np.concatenate((horizontal,
                first[2:] + amount * (second[2:] - first[2:]))).tolist())
    sampled.append(source[-1].tolist())
    return sampled


def path_records(roads_json: dict, plan_json: dict, output: Path, resource_root: str):
    roads = {record["id"]: record for record in roads_json["roads"]}
    missing = sorted(set(OWNED_ROUTE_IDS) - roads.keys())
    if missing:
        raise ValueError(f"Published roads are missing owned routes: {missing}")
    result = []
    for identity in OWNED_ROUTE_IDS:
        source = roads[identity]
        points = local_road_points(source)
        curve = output / "paths" / f"{slug(identity)}.tres"
        write_curve(curve, points)
        result.append({
            "id": identity,
            "kind": "road",
            "routingRole": "decorative" if identity.startswith("discovery-") else "required",
            "width": float(source["width"]) * 2.0,
            "points": points,
            "curve": f"{resource_root}/paths/{curve.name}",
            "properties": {"terrainConform": True, "terrainFeather": 2.0},
        })
    river = next(record for record in plan_json["rivers"]
                 if record["id"] == "southern_river")
    river_controls = local_river_points(river)
    river_points = local_river_points({"points": legacy_curved_points(river["points"])})
    curve = output / "paths" / "southern-river.tres"
    write_curve(curve, river_points)
    result.append({
        "id": "southern_river",
        "kind": "river",
        "routingRole": "decorative",
        "width": float(river["width"]) * 2.0,
        "points": river_points,
        "sourceControlPointCount": len(river_controls),
        "sampling": "legacy-open-catmull-rom-6x-zero-handles",
        "curve": f"{resource_root}/paths/{curve.name}",
        "properties": {
            "terrainConform": True,
            "terrainFeather": 5.5,
            "channelDepth": float(river["depth"]),
            "valleyWidth": float(river["valley_width"]),
            "bankHeight": float(river["bank_height"]),
            "mouth": river["mouth"],
            "name": river["name"],
        },
    })
    return result


def write_surface(path: Path, preset: str, road: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=2 format=3]',
        '',
        '[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]',
        '',
        '[resource]',
        'resource_local_to_scene = true',
        'script = ExtResource("1_surface")',
    ]
    if road:
        lines.append("material_mode = 1")
    lines.extend((f"texture_preset = {godot_string(preset)}", "rotation_degrees = 0.0", ""))
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_sunmane_desert_surface(path: Path) -> None:
    """Use explicit UVs so the editor preview matches exported terrain."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((
        '[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=6 format=3]',
        '',
        '[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/desert-basecolor.png" id="2_albedo"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-normal.png" id="3_normal"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-orm.png" id="4_orm"]',
        '',
        '[sub_resource type="ORMMaterial3D" id="ORMMaterial3D_desert"]',
        'albedo_color = Color(0.9, 0.82, 0.68, 1)',
        'albedo_texture = ExtResource("2_albedo")',
        'roughness = 1.0',
        'normal_enabled = true',
        'normal_scale = 0.5',
        'normal_texture = ExtResource("3_normal")',
        'orm_texture = ExtResource("4_orm")',
        'uv1_scale = Vector3(0.2, 0.2, 0.2)',
        'uv1_triplanar = false',
        'uv1_world_triplanar = false',
        'texture_filter = 4',
        'cull_mode = 2',
        '',
        '[resource]',
        'resource_local_to_scene = true',
        'script = ExtResource("1_surface")',
        'texture_preset = "Desert"',
        'rotation_degrees = 0.0',
        'source_material = SubResource("ORMMaterial3D_desert")',
        '',
    )), encoding="utf-8", newline="\n")


def write_sunmane_road_surface(path: Path) -> None:
    """Write Sunmane's readable sand-road override without changing the global preset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((
        '[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=7 format=3]',
        '',
        '[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]',
        '[ext_resource type="Shader" path="res://src/dev/map_authoring_pilot/style/worn_path.gdshader" id="2_shader"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-basecolor.png" id="3_albedo"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-normal.png" id="4_normal"]',
        '[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-orm.png" id="5_orm"]',
        '',
        '[sub_resource type="ShaderMaterial" id="ShaderMaterial_road"]',
        'render_priority = 1',
        'shader = ExtResource("2_shader")',
        'shader_parameter/ground_albedo = ExtResource("3_albedo")',
        'shader_parameter/ground_normal = ExtResource("4_normal")',
        'shader_parameter/ground_orm = ExtResource("5_orm")',
        'shader_parameter/worn_tint = Color(0.9, 0.78, 0.59, 1)',
        'shader_parameter/texture_scale = 1.0',
        'shader_parameter/roughness_multiplier = 1.0',
        'shader_parameter/normal_strength = 0.72',
        'shader_parameter/edge_feather = 0.16',
        '',
        '[resource]',
        'resource_local_to_scene = true',
        'script = ExtResource("1_surface")',
        'material_mode = 1',
        'texture_preset = "Worn earth"',
        'rotation_degrees = 0.0',
        'source_material = SubResource("ShaderMaterial_road")',
        '',
    )), encoding="utf-8", newline="\n")


def write_sunmane_river_surface(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join((
        '[gd_resource type="Resource" script_class="MapAuthoringSurface" load_steps=3 format=3]',
        '',
        '[ext_resource type="Script" path="res://src/dev/map_authoring_pilot/style/map_authoring_surface.gd" id="1_surface"]',
        '',
        '[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_water"]',
        'transparency = 1',
        'albedo_color = Color(0.24, 0.54, 0.62, 0.9)',
        'metallic = 0.0',
        'roughness = 0.45',
        '',
        '[resource]',
        'resource_local_to_scene = true',
        'script = ExtResource("1_surface")',
        'texture_preset = "Custom"',
        'rotation_degrees = 0.0',
        'source_material = SubResource("StandardMaterial3D_water")',
        '',
    )), encoding="utf-8", newline="\n")


def clean_extras(record: dict) -> dict:
    positional = {"id", "position", "center", "serverTile", "default", "facing",
                  "destinationMap", "destinationSpawn", "key", "node", "label"}
    return {key: value for key, value in record.items() if key not in positional}


def marker_records(manifest: dict, objects: list[dict]) -> list[dict]:
    object_by_node = {record["nodeName"]: record for record in objects}
    result = []
    for source_key, container, kind in GAMEPLAY:
        for record in manifest.get(source_key, ()):
            position = record.get("position", record.get("center"))
            if position is None:
                raise ValueError(f"Gameplay record {source_key}/{record.get('id')} has no position")
            linked_node = str(record.get("node", ""))
            followed = object_by_node.get(linked_node)
            offset = [0.0, 0.0, 0.0]
            if followed is not None:
                homogeneous = np.array([*position, 1.0], dtype=float)
                offset = (np.linalg.inv(followed["matrix"]) @ homogeneous)[:3].tolist()
            result.append({
                "container": container,
                "kind": kind,
                "id": str(record["id"]),
                "position": [float(value) for value in position],
                "label": str(record.get("label", record.get("name", ""))),
                "destinationMap": str(record.get("destinationMap", "")),
                "destinationSpawn": str(record.get("destinationSpawn", "")),
                "key": str(record.get("key", "")),
                "default": bool(record.get("default", False)),
                "facing": [float(value) for value in record.get("facing", (0, 0, -1))],
                "node": linked_node,
                "followAssetId": followed["id"] if followed is not None else "",
                "followAssetOffset": offset,
                "extras": clean_extras(record),
                "runtimeBindings": [],
            })
    ambient = manifest.get("ambientPopulation", {}).get("groups", ())
    for record in ambient:
        result.append({
            "container": "AmbientPopulation",
            "kind": "ambient_population",
            "id": str(record["id"]),
            "position": [float(value) for value in record["center"]],
            "label": str(record.get("label", "")),
            "destinationMap": "", "destinationSpawn": "", "key": "",
            "default": False, "facing": [0.0, 0.0, -1.0], "node": "",
            "followAssetId": "", "followAssetOffset": [0.0, 0.0, 0.0],
            "extras": clean_extras(record),
            "runtimeBindings": [],
        })
    return sorted(result, key=lambda record: (record["container"], record["id"]))


def apply_runtime_binding_seed(markers: list[dict], seed: dict) -> None:
    """Attach exact runtime identities and create the missing visible controls."""
    if seed.get("schema") != "eloria-runtime-binding-seed-v1":
        raise ValueError("Runtime binding seed has an unsupported schema")
    if seed.get("regionId") != REGION_ID:
        raise ValueError("Runtime binding seed regionId does not match Sunmane")
    provenance = seed.get("provenance", {})
    report_sha = str(provenance.get("sourceReportSha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", report_sha):
        raise ValueError("Runtime binding seed needs a certified source report hash")
    profile_hashes = {
        str(record.get("path", "")): str(record.get("sha256", ""))
        for record in provenance.get("profileFiles", [])
    }
    by_target = {
        (GAMEPLAY_OUTPUT_SECTIONS[record["kind"]], record["id"]): record
        for record in markers
    }
    binding_ids: set[str] = set()
    for binding in seed.get("bindings", []):
        identity = str(binding.get("id", ""))
        if not identity or identity in binding_ids:
            raise ValueError(f"Runtime binding id is empty or duplicated: {identity}")
        binding_ids.add(identity)
        target = binding.get("marker", {})
        section = str(target.get("section", ""))
        marker_id = str(target.get("id", ""))
        offset = binding.get("targetOffset")
        if (not isinstance(offset, list) or len(offset) != 3 or
                any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(float(value)) for value in offset)):
            raise ValueError(f"Runtime binding {identity} needs finite targetOffset [dx, 0, dz]")
        if not math.isclose(float(offset[1]), 0.0, abs_tol=1e-9):
            raise ValueError(f"Runtime binding {identity} targetOffset must be horizontal")
        if section == "runtimePoints" and any(
                not math.isclose(float(value), 0.0, abs_tol=1e-9) for value in offset):
            raise ValueError(f"Runtime point binding {identity} targetOffset must be zero")
        key = (section, marker_id)
        marker = by_target.get(key)
        if section == "runtimePoints" and marker is None:
            position = binding.get("initialPosition")
            if not isinstance(position, list) or len(position) != 3:
                raise ValueError(f"Runtime point {marker_id} needs initialPosition [x,y,z]")
            role = str(binding.get("role", ""))
            group = RUNTIME_POINT_GROUPS.get(role)
            if group is None:
                raise ValueError(f"Runtime point {marker_id} has unsupported role {role}")
            source = binding.get("source", {})
            marker = {
                "container": f"RuntimePoints/{group}", "kind": "runtime_point",
                "id": marker_id, "position": [float(value) for value in position],
                "label": str(source.get("recordId", identity)),
                "destinationMap": "", "destinationSpawn": "", "key": "",
                "default": False, "facing": [0.0, 0.0, -1.0], "node": "",
                "followAssetId": "", "followAssetOffset": [0.0, 0.0, 0.0],
                "extras": {}, "runtimeBindings": [],
            }
            markers.append(marker)
            by_target[key] = marker
        if marker is None:
            raise ValueError(
                f"Runtime binding {identity} targets missing marker {section}/{marker_id}")
        emitted = copy.deepcopy(binding)
        emitted.pop("marker", None)
        emitted.pop("initialPosition", None)
        emitted["targetOffset"] = [float(offset[0]), 0.0, float(offset[2])]
        emitted["provenance"] = {"sourceReportSha256": report_sha}
        source_path = str(emitted.get("source", {}).get("path", ""))
        profile_sha = profile_hashes.get(source_path, "")
        if not profile_sha:
            profile_sha = next((value for path, value in profile_hashes.items()
                                if path.endswith(source_path)), "")
        if profile_sha:
            emitted["provenance"]["sourceProfileSha256"] = profile_sha
        marker["runtimeBindings"].append(emitted)
    markers.sort(key=lambda record: (record["container"], record["id"]))
    expected = seed.get("counts", {})
    if len(binding_ids) != int(expected.get("bindings", -1)):
        raise ValueError("Runtime binding seed count does not match its bindings")
    runtime_count = sum(record["kind"] == "runtime_point" for record in markers)
    if runtime_count != int(expected.get("runtimePoints", -1)):
        raise ValueError("Runtime binding seed count does not match its RuntimePoints")


def resource_table(prototypes: dict, paths: list[dict], resource_root: str):
    resources = [
        ("Script", "res://src/dev/map_authoring_region/region_control.gd", "region"),
        ("Script", "res://src/dev/map_authoring_region/terrain_control.gd", "terrain"),
        ("Script", "res://src/dev/map_authoring_region/path_control.gd", "path"),
        ("Script", "res://src/dev/map_authoring_region/bridge_control.gd", "bridge"),
        ("Script", "res://src/dev/map_authoring_region/asset_control.gd", "asset"),
        ("Script", "res://src/dev/map_authoring_region/gameplay_marker.gd", "marker"),
        ("Resource", f"{resource_root}/surfaces/desert.tres", "desert"),
        ("Resource", f"{resource_root}/surfaces/worn-earth-road.tres", "road_surface"),
        ("Resource", f"{resource_root}/surfaces/river-water.tres", "river_surface"),
        ("Resource", f"{resource_root}/surfaces/timber.tres", "timber"),
        ("Resource", f"{resource_root}/surfaces/stone.tres", "stone"),
    ]
    for index, path in enumerate(paths):
        path["resourceId"] = f"curve_{index:02d}"
        resources.append(("Curve3D", path["curve"], path["resourceId"]))
    for index, family in enumerate(sorted(prototypes)):
        prototypes[family]["resourceId"] = f"prototype_{index:03d}"
        resources.append(("PackedScene", prototypes[family]["path"], prototypes[family]["resourceId"]))
    return resources


def write_scene(output: Path, world_manifest: dict, provenance: dict,
                objects: list[dict], prototypes: dict, paths: list[dict],
                markers: list[dict], ownership_sha: str, resource_root: str,
                runtime_seed_path: str, runtime_seed_sha: str) -> None:
    resources = resource_table(prototypes, paths, resource_root)
    lines = [f'[gd_scene load_steps={len(resources) + 1} format=3]', ""]
    for kind, path, identity in resources:
        lines.append(f'[ext_resource type="{kind}" path="{path}" id="{identity}"]')
    lines.extend(("", '[node name="SunmaneSteppe" type="Node3D"]',
                  'script = ExtResource("region")', f'region_id = "{REGION_ID}"',
                  'continent_translation = Vector3(1200, 0, 720)',
                  'metres_per_tile = 1.0', 'server_origin = Vector2i(194, 292)',
                  'server_cells = Vector2i(792, 792)',
                  'collision_origin_metres = Vector2(-194, 292)',
                  f'ownership_polygon_sha256 = "{ownership_sha}"',
                  f'seam_anchors = {godot_value(world_manifest["streamingBorders"])}',
                  'owned_route_ids = PackedStringArray(' + ", ".join(
                      godot_string(value) for value in sorted(OWNED_ROUTE_IDS)) + ')',
                  'owned_plan_feature_ids = PackedStringArray("southern_river")',
                  f'runtime_binding_seed_path = {godot_string(runtime_seed_path)}',
                  f'runtime_binding_seed_sha256 = {godot_string(runtime_seed_sha)}',
                  'export_directory = "res://../eloria-assets/maps/nymara-regions/sunmane_steppe/authoring"',
                  "", '[node name="Terrain" type="Node3D" parent="."]',
                  'script = ExtResource("terrain")', 'origin = Vector2(-194, -500)',
                  'cell_metres = 2.0', 'grid_size = Vector2i(397, 397)',
                  f'base_heights_path = "{resource_root}/base-heights.f32le"',
                  'base_surface = ExtResource("desert")', "",
                  '[node name="Patches" type="Node3D" parent="Terrain"]', "",
                  '[node name="Ground" type="Node3D" parent="."]', "",
                  '[node name="Regions" type="Node3D" parent="Ground"]', "",
                  '[node name="Roads" type="Node3D" parent="."]', ""))
    for path in (record for record in paths if record["kind"] == "road"):
        lines.extend((f'[node name={godot_string(node_name(path["id"]))} type="Path3D" parent="Roads"]',
                      'script = ExtResource("path")', f'curve = ExtResource("{path["resourceId"]}")',
                      f'path_id = {godot_string(path["id"])}', 'kind = "road"',
                      f'routing_role = {godot_string(path["routingRole"])}',
                      f'replaces_route_id = {godot_string(path["id"])}',
                      f'properties = {godot_value(path["properties"])}',
                      f'default_width = {gd_float(path["width"])}',
                      'surface = ExtResource("road_surface")', ""))
    lines.extend(('[node name="Rivers" type="Node3D" parent="."]', ""))
    for path in (record for record in paths if record["kind"] == "river"):
        lines.extend((f'[node name={godot_string(node_name(path["id"]))} type="Path3D" parent="Rivers"]',
                      'script = ExtResource("path")', f'curve = ExtResource("{path["resourceId"]}")',
                      f'path_id = {godot_string(path["id"])}', 'kind = "river"',
                      f'routing_role = {godot_string(path["routingRole"])}',
                      'replaces_plan_feature_id = "southern_river"',
                      f'properties = {godot_value(path["properties"])}',
                      f'default_width = {gd_float(path["width"])}',
                      'surface = ExtResource("river_surface")', ""))
    lines.extend(('[node name="Bridges" type="Node3D" parent="."]', "",
                  '[node name="ContinentalBridge008" type="Node3D" parent="Bridges"]',
                  'script = ExtResource("bridge")', 'bridge_id = "continental-bridge-008"',
                  'width = 4.0', 'arch = 0.35', 'water_clearance = 1.1',
                  'deck_surface = ExtResource("timber")',
                  'support_surface = ExtResource("stone")',
                  'metadata = {"legacyNode": "ContinentalBridgeUnion_008", "migration": "published-composition"}',
                  "", '[node name="Start" type="Marker3D" parent="Bridges/ContinentalBridge008"]',
                  'position = Vector3(-10.7, 22.233, 80.7)', "",
                  '[node name="End" type="Marker3D" parent="Bridges/ContinentalBridge008"]',
                  'position = Vector3(11.3, 22.197, 70.7)', "",
                  '[node name="AuthoredAssets" type="Node3D" parent="."]', ""))
    source_sha = provenance["asset"]["sourceWorldSha256"]
    for index, record in enumerate(objects):
        path = f'AuthoredAssets/{node_name(record["id"])}'
        prototype = prototypes[record["family"]]
        lines.extend((f'[node name={godot_string(node_name(record["id"]))} type="Node3D" parent="AuthoredAssets"]',
                      'script = ExtResource("asset")',
                      f'transform = {transform3d(record["matrix"])}',
                      f'asset_id = {godot_string(record["id"])}',
                      f'node_name = {godot_string(record["nodeName"])}',
                      f'catalog_asset_id = {godot_string("sunmane:" + slug(record["family"]))}',
                      f'scene_path = {godot_string(prototype["path"])}',
                      f'collision_role = {godot_string(record["collisionRole"])}',
                      'metadata = ' + godot_value({"migrationYDelta": record["migrationYDelta"],
                                                   "prototypeFamily": record["family"],
                                                   "sourceWrapper": record["sourceWrapper"],
                                                   "sourceWorldSha256": source_sha}), "",
                      f'[node name="Content" parent={godot_string(path)} instance=ExtResource("{prototype["resourceId"]}")]', ""))
    lines.extend(('[node name="Gameplay" type="Node3D" parent="."]', ""))
    containers = [entry[1] for entry in GAMEPLAY] + ["AmbientPopulation", "RuntimePoints"]
    for container in containers:
        lines.extend((f'[node name="{container}" type="Node3D" parent="Gameplay"]', ""))
    for group in RUNTIME_POINT_GROUPS.values():
        lines.extend((f'[node name="{group}" type="Node3D" parent="Gameplay/RuntimePoints"]', ""))
    for marker in markers:
        position = marker["position"]
        parent = f'Gameplay/{marker["container"]}'
        lines.extend((f'[node name={godot_string(node_name(marker["id"]))} type="Marker3D" parent={godot_string(parent)}]',
                      'script = ExtResource("marker")',
                      f'position = Vector3({", ".join(gd_float(v) for v in position)})',
                      f'record_id = {godot_string(marker["id"])}',
                      f'kind = {godot_string(marker["kind"])}',
                      f'label = {godot_string(marker["label"])}',
                      f'destination_map = {godot_string(marker["destinationMap"])}',
                      f'destination_spawn = {godot_string(marker["destinationSpawn"])}',
                      f'key_id = {godot_string(marker["key"])}',
                      f'default_spawn = {godot_value(marker["default"])}',
                      f'facing = Vector3({", ".join(gd_float(v) for v in marker["facing"])})',
                      f'linked_node_name = {godot_string(marker["node"])}',
                      f'follow_asset_id = {godot_string(marker["followAssetId"])}',
                      f'follow_asset_offset = Vector3({", ".join(gd_float(v) for v in marker["followAssetOffset"])})',
                      f'extras = {godot_value(marker["extras"])}',
                      f'runtime_bindings = {godot_value(marker["runtimeBindings"])}', ""))
    lines.extend(('[node name="GeneratedPreview" type="Node3D" parent="."]', ""))
    (output / "sunmane_steppe.tscn").write_text("\n".join(lines),
                                                   encoding="utf-8", newline="\n")


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-world", type=Path, required=True,
                        help="Certified legacy Sunmane world.glb")
    parser.add_argument("--source-manifest", type=Path, required=True,
                        help="Certified legacy Sunmane world.json")
    parser.add_argument("--roads", type=Path, required=True,
                        help="Certified composed roads.json")
    parser.add_argument("--plan", type=Path, required=True,
                        help="Certified continent plan containing southern_river")
    parser.add_argument("--base-heights", type=Path, required=True,
                        help="Certified 397x397 natural grid with owned plan features removed")
    parser.add_argument("--resolved-heights", type=Path, required=True,
                        help="Frozen first authored resolved grid used only for one-time Y migration")
    parser.add_argument("--runtime-bindings", type=Path, required=True,
                        help="Certified exact server-record to gameplay-marker seed")
    parser.add_argument("--output", type=Path,
                        default=repo / f"godot-client/world_authoring/regions/{REGION_ID}")
    parser.add_argument("--force", action="store_true",
                        help="Replace an existing authored scene after explicit review")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    repo = Path(__file__).resolve().parents[2]
    toolkit = repo / "eloria-assets/maps/nymara-regions/_toolkit"
    continent = repo / "eloria-assets/maps/nymara-regions/_continent"
    for path in (toolkit, continent):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import glb_reader
    import scene_io

    output = args.output.resolve()
    project_root = (repo / "godot-client").resolve()
    try:
        resource_root = "res://" + output.relative_to(project_root).as_posix()
    except ValueError as error:
        raise ValueError("--output must stay inside the Godot project") from error
    if (output / "sunmane_steppe.tscn").exists() and not args.force:
        raise ValueError(
            "Refusing to overwrite an existing authored scene; choose a new --output "
            "directory or pass --force after reviewing certified input hashes")
    output.mkdir(parents=True, exist_ok=True)
    base_target = output / "base-heights.f32le"
    if args.base_heights is not None:
        if args.base_heights.stat().st_size != GRID_BYTES:
            raise ValueError(f"Base height grid must be {GRID_BYTES} bytes")
        shutil.copyfile(args.base_heights, base_target)
    if not base_target.exists() or base_target.stat().st_size != GRID_BYTES:
        raise ValueError("Pass --base-heights for the initial certified pre-feature grid")
    if args.resolved_heights.stat().st_size != GRID_BYTES:
        raise ValueError(f"Resolved height grid must be {GRID_BYTES} bytes")

    source_document, source_body = glb_reader.load(args.source_world)
    source_document, source_body = embed_external_images(
        source_document, source_body, args.source_world)
    matrices, _ = glb_reader.hierarchy(source_document)
    world_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    roads_json = json.loads(args.roads.read_text(encoding="utf-8"))
    plan_json = json.loads(args.plan.read_text(encoding="utf-8"))
    collision = set(world_manifest["collision"]["nodeNames"])
    objects, families = object_records(source_document, matrices, collision)
    prototypes = write_prototypes(source_document, source_body, families, output,
                                  resource_root, scene_io)
    paths = path_records(roads_json, plan_json, output, resource_root)
    markers = marker_records(world_manifest, objects)
    runtime_seed = json.loads(args.runtime_bindings.read_text(encoding="utf-8"))
    published_heights = published_terrain_heights(
        source_document, source_body, matrices, glb_reader)
    resolved_heights = np.fromfile(args.resolved_heights, dtype="<f4")
    vertical_migration = apply_vertical_migration(
        objects, markers, published_heights, resolved_heights)
    # Seed positions already come from the certified final resolved grid. Add
    # them after the one-time legacy vertical migration so it cannot compound.
    apply_runtime_binding_seed(markers, runtime_seed)
    write_sunmane_desert_surface(output / "surfaces/desert.tres")
    write_sunmane_road_surface(output / "surfaces/worn-earth-road.tres")
    write_sunmane_river_surface(output / "surfaces/river-water.tres")
    write_surface(output / "surfaces/timber.tres", "Timber")
    write_surface(output / "surfaces/stone.tres", "Stone")
    ownership = world_manifest["continentGeography"]["ownershipPolygon"]
    ownership_sha = hashlib.sha256(json.dumps(ownership, separators=(",", ":"),
                                               ensure_ascii=False).encode()).hexdigest()
    provenance = {
        "schema": "eloria-sunmane-authoring-migration-v1",
        "asset": {
            "sourceWorld": repo_path(args.source_world, repo),
            "sourceWorldSha256": sha256(args.source_world),
            "sourceManifestSha256": sha256(args.source_manifest),
            "roadsSha256": sha256(args.roads),
            "planSha256": sha256(args.plan),
            "baseHeightsSha256": sha256(base_target),
            "initialResolvedHeights": repo_path(args.resolved_heights, repo),
            "initialResolvedHeightsSha256": sha256(args.resolved_heights),
        },
        "counts": {
            "objects": len(objects), "prototypeFamilies": len(prototypes),
            "roads": len(OWNED_ROUTE_IDS), "rivers": 1,
            "gameplay": {container: sum(marker["container"] == container for marker in markers)
                         for container in [entry[1] for entry in GAMEPLAY] + ["AmbientPopulation"]},
            "runtimePoints": sum(marker["kind"] == "runtime_point" for marker in markers),
            "runtimeBindings": sum(len(marker["runtimeBindings"]) for marker in markers),
        },
        "ownedRouteIds": sorted(OWNED_ROUTE_IDS),
        "ownedPlanFeatureIds": ["southern_river"],
        "excludedComposedRoots": list(EXCLUDED_ROOT_PREFIXES),
        "ownershipPolygonSha256": ownership_sha,
        "verticalMigration": vertical_migration,
        "objects": [{"id": record["id"], "family": record["family"],
                     "collisionRole": record["collisionRole"]} for record in objects],
        "prototypes": prototypes,
        "paths": [{"id": record["id"], "kind": record["kind"],
                   "routingRole": record["routingRole"], "width": record["width"],
                   "pointCount": len(record["points"]),
                   **({"sourceControlPointCount": record["sourceControlPointCount"],
                       "sampling": record["sampling"]}
                      if record["kind"] == "river" else {}),
                   "pointsSha256": hashlib.sha256(json.dumps(record["points"],
                       separators=(",", ":")).encode()).hexdigest()} for record in paths],
        "gameplay": [{"section": record["container"], "id": record["id"],
                      "followAssetId": record["followAssetId"]} for record in markers],
        "runtimeBindingSeed": {
            "path": repo_path(args.runtime_bindings, repo),
            "sha256": sha256(args.runtime_bindings),
        },
    }
    runtime_seed_res = "res://" + args.runtime_bindings.resolve().relative_to(
        project_root).as_posix()
    write_scene(output, world_manifest, provenance, objects, prototypes, paths,
                markers, ownership_sha, resource_root, runtime_seed_res,
                sha256(args.runtime_bindings))
    provenance["asset"]["sceneSha256"] = sha256(output / "sunmane_steppe.tscn")
    (output / "migration-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"scene": str(output / "sunmane_steppe.tscn"),
                      "objects": len(objects), "prototypes": len(prototypes),
                      "paths": len(paths), "markers": len(markers)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
