#!/usr/bin/env python3
"""Deterministic close-detail pass for the Four Gates concept-art map.

The pass keeps the cardinal roads and plaza spawn clear while adding a second
readable scale: gate jewellery, planted civic beds, lived-in market dressing,
residential balconies, bespoke broadleaf planting, and rocky/foamy waterfall
edges.  All generated nodes use the ``Detail_`` prefix so compact LOD2 can
discard them without brittle mesh-index assumptions.
"""

import json
import math
import random
import struct
from pathlib import Path

import numpy as np


PACKAGE = Path("four-gates-city-package")
GLB = PACKAGE / "four-gates-city.glb"
raw = GLB.read_bytes()
json_length = struct.unpack_from("<I", raw, 12)[0]
document = json.loads(raw[20:20 + json_length])
binary_offset = 20 + json_length
binary_length = struct.unpack_from("<I", raw, binary_offset)[0]
binary = bytearray(raw[binary_offset + 8:binary_offset + 8 + binary_length])

nodes = document["nodes"]
node_ids = {node.get("name"): index for index, node in enumerate(nodes)}
mesh_ids = {mesh["name"]: index for index, mesh in enumerate(document["meshes"])}
material_ids = {material["name"]: index for index, material in enumerate(document["materials"])}
random.seed(904)


def align_binary():
    while len(binary) % 4:
        binary.append(0)


def add_view(data, target=None):
    align_binary()
    offset = len(binary)
    binary.extend(data)
    item = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
    if target:
        item["target"] = target
    document["bufferViews"].append(item)
    return len(document["bufferViews"]) - 1


def add_accessor(values, kind, component=5126, target=34962):
    array = np.asarray(values, np.float32 if component == 5126 else np.uint32)
    item = {
        "bufferView": add_view(array.tobytes(), target),
        "componentType": component,
        "count": len(array),
        "type": kind,
        "min": array.min(0).tolist() if array.ndim > 1 else [int(array.min())],
        "max": array.max(0).tolist() if array.ndim > 1 else [int(array.max())],
    }
    document["accessors"].append(item)
    return len(document["accessors"]) - 1


def baked_city_uv(material, uv):
    rectangles = {
        "stone": (0, 0), "dark-stone": (1, 0), "paving": (2, 0), "rock": (3, 0),
        "roof": (0, 1), "bronze": (1, 1), "wood": (3, 1), "plaster": (0, 2),
        "soil": (1, 2), "grass": (2, 2), "snow": (3, 2), "water": (0, 3),
        "blue-crystal": (1, 3), "waterfall": (2, 3), "vegetation": (3, 3),
    }
    column, row = rectangles[material]
    inset = 1.0 / 1024.0
    return [column * .25 + inset + (uv[0] % 1.0) * (.25 - inset * 2.0),
            row * .25 + inset + (uv[1] % 1.0) * (.25 - inset * 2.0)]


def add_faceted_mesh(name, rings, material, segments=10):
    positions, normals, uvs, indices = [], [], [], []
    for ring_index, (height, radius) in enumerate(rings):
        for segment in range(segments):
            angle = math.tau * segment / segments
            positions.append([radius * math.cos(angle), height, radius * math.sin(angle)])
            radial = np.asarray([math.cos(angle), .18, math.sin(angle)], np.float32)
            radial /= np.linalg.norm(radial)
            normals.append(radial.tolist())
            uvs.append(baked_city_uv(material, [segment / segments, ring_index / max(1, len(rings) - 1)]))
    for ring_index in range(len(rings) - 1):
        for segment in range(segments):
            following = (segment + 1) % segments
            a = ring_index * segments + segment
            b = ring_index * segments + following
            c = (ring_index + 1) * segments + following
            d = (ring_index + 1) * segments + segment
            indices.extend((a, b, c, a, c, d))
    normal_array = np.asarray(normals, np.float32)
    tangents = np.cross(np.tile([0., 1., 0.], (len(normal_array), 1)), normal_array)
    weak = np.linalg.norm(tangents, axis=1) < 1e-5
    tangents[weak] = [1, 0, 0]
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-6)
    tangents = np.column_stack((tangents, np.ones(len(tangents), np.float32)))
    primitive = {
        "attributes": {
            "POSITION": add_accessor(positions, "VEC3"),
            "NORMAL": add_accessor(normal_array, "VEC3"),
            "TEXCOORD_0": add_accessor(uvs, "VEC2"),
            "TANGENT": add_accessor(tangents, "VEC4"),
        },
        "indices": add_accessor(indices, "SCALAR", 5125, 34963),
        "material": material_ids[material],
    }
    document["meshes"].append({"name": name, "primitives": [primitive]})
    mesh_ids[name] = len(document["meshes"]) - 1


add_faceted_mesh("detail_broadleaf_crown",
                 [(-.42, .18), (-.22, .48), (.10, .55), (.34, .36), (.50, .06)],
                 "vegetation", 11)


created = []


def rotation_y(angle):
    return [0.0, math.sin(angle * .5), 0.0, math.cos(angle * .5)]


def add(name, parent, mesh, position, scale, rotation=None, role="ornament"):
    item = {
        "name": name,
        "mesh": mesh_ids[mesh],
        "translation": [float(value) for value in position],
        "scale": [float(value) for value in scale],
        "extras": {"lod": "LOD0", "visualOnly": True, "detailRole": role},
    }
    if rotation:
        item["rotation"] = rotation
    nodes.append(item)
    nodes[node_ids[parent]].setdefault("children", []).append(len(nodes) - 1)
    created.append(name)


# Layer blue-glass and aged-gold ornament onto every traversable gate.  The
# trim stays outside the 26 m-wide clear nav strip along each cardinal axis.
gates = {
    "Gate_South_Outer": (0.0, 570.0, 0.0),
    "Gate_South_Inner": (0.0, 345.0, 0.0),
    "Gate_North": (0.0, -345.0, math.pi),
    "Gate_East": (345.0, 0.0, math.pi / 2),
    "Gate_West": (-345.0, 0.0, -math.pi / 2),
}
for gate, (center_x, center_z, yaw) in gates.items():
    tangent = (math.cos(yaw), -math.sin(yaw))
    facing = (math.sin(yaw), math.cos(yaw))
    short = gate.replace("Gate_", "")
    for side in (-1, 1):
        x = center_x + tangent[0] * 40.0 * side
        z = center_z + tangent[1] * 40.0 * side
        add(f"Detail_Gate_{short}_Crown_{side:+}", gate, "cone_bronze",
            (x, 112.0, z), (6.0, 18.0, 6.0), role="gate-crown")
        add(f"Detail_Gate_{short}_Jewel_{side:+}", gate, "cone_blue-crystal",
            (x, 121.0, z), (3.2, 11.0, 3.2), role="gate-energy-jewel")
        banner_x = center_x + tangent[0] * 76.0 * side + facing[0] * 2.0
        banner_z = center_z + tangent[1] * 76.0 * side + facing[1] * 2.0
        add(f"Detail_Gate_{short}_Banner_Pole_{side:+}", gate, "cube_bronze",
            (banner_x, 72.0, banner_z), (1.2, 42.0, 1.2), rotation_y(yaw), "gate-banner")
        add(f"Detail_Gate_{short}_Banner_Cloth_{side:+}", gate, "cube_roof",
            (banner_x + tangent[0] * 4.0 * side, 78.0, banner_z + tangent[1] * 4.0 * side),
            (8.0, 17.0, .7), rotation_y(yaw), "gate-banner")
    for side in (-1, 1):
        x = center_x + tangent[0] * 32.0 * side + facing[0] * 2.5
        z = center_z + tangent[1] * 32.0 * side + facing[1] * 2.5
        add(f"Detail_Gate_{short}_Energy_Rib_{side:+}", gate, "cube_blue-crystal",
            (x, 70.0, z), (1.5, 37.0, 1.2), rotation_y(yaw), "gate-tracery")


# Eight planted beds echo the concept's radial civic gardens.  Their diagonal
# placement leaves the four principal routes and the player start unobstructed.
for index in range(8):
    angle = math.radians(22.5 + index * 45.0)
    x, z = 110.0 * math.sin(angle), 110.0 * math.cos(angle)
    yaw = angle
    add(f"Detail_Civic_Planter_{index:02}_Border", "Props", "cube_dark-stone",
        (x, 33.0, z), (19.0, 3.0, 11.0), rotation_y(yaw), "civic-garden")
    add(f"Detail_Civic_Planter_{index:02}_Soil", "Props", "cube_soil",
        (x, 35.0, z), (16.0, 1.4, 8.0), rotation_y(yaw), "civic-garden")
    tangent = (math.cos(angle), -math.sin(angle))
    for shrub in (-1, 0, 1):
        sx, sz = x + tangent[0] * shrub * 7.0, z + tangent[1] * shrub * 7.0
        add(f"Detail_Civic_Planter_{index:02}_Shrub_{shrub:+}", "Vegetation",
            "detail_broadleaf_crown", (sx, 39.0, sz), (4.2, 7.0, 4.2), role="civic-garden")


# The civic market gains readable stock, barrels, and hanging sapphire signs.
market_stalls = sorted(
    (node for node in nodes if node.get("name", "").startswith("Market_Stall_")),
    key=lambda item: item["name"],
)
for index, stall in enumerate(market_stalls):
    x, y, z = stall["translation"]
    side = -1.0 if x < 0.0 else 1.0
    add(f"Detail_Market_Crate_{index:02}_A", "Props", "cube_wood",
        (x + 9.0 * side, 35.5, z + 7.0), (5.0, 5.0, 5.0), role="market-stock")
    add(f"Detail_Market_Crate_{index:02}_B", "Props", "cube_wood",
        (x + 13.0 * side, 34.0, z + 9.0), (3.5, 3.5, 3.5), role="market-stock")
    add(f"Detail_Market_Barrel_{index:02}", "Props", "cylinder_wood",
        (x + 15.0 * side, 36.0, z + 8.0), (3.6, 7.0, 3.6), role="market-stock")
    add(f"Detail_Market_Sign_Pole_{index:02}", "Props", "cube_bronze",
        (x, 44.0, z - 9.0), (.8, 13.0, .8), role="market-sign")
    add(f"Detail_Market_Sign_{index:02}", "Props", "cube_blue-crystal",
        (x + 3.0 * side, 47.0, z - 9.0), (6.0, 4.5, .7), role="market-sign")


# Selected residences receive actual balcony silhouettes instead of relying on
# the same gable/box language at every gameplay-distance façade.
residences = sorted(
    (node for node in nodes if node.get("name", "").startswith("Residence_") and node.get("name", "").endswith("_Body")),
    key=lambda item: int(item["name"].split("_")[1]),
)
for body in residences[::2]:
    number = body["name"].split("_")[1]
    door = nodes[node_ids[f"Residence_{number}_Door"]]
    bx, by, bz = body["translation"]
    dx, _, dz = door["translation"]
    fx, fz = dx - bx, dz - bz
    length = max(math.hypot(fx, fz), 1.0)
    fx, fz = fx / length, fz / length
    yaw = math.atan2(fx, fz)
    px, pz = bx + fx * (length + 1.8), bz + fz * (length + 1.8)
    add(f"Detail_Residence_{number}_Balcony", "District_Residential", "cube_dark-stone",
        (px, by + 6.0, pz), (10.0, 1.1, 4.0), rotation_y(yaw), "residential-balcony")
    add(f"Detail_Residence_{number}_Balcony_Rail", "District_Residential", "cube_bronze",
        (px + fx * 2.0, by + 9.0, pz + fz * 2.0), (10.0, 4.0, .7), rotation_y(yaw), "residential-balcony")
    add(f"Detail_Residence_{number}_Roof_Finial", "District_Residential", "cone_bronze",
        (bx, by + body["scale"][1] * .5 + 20.0, bz), (2.6, 10.0, 2.6), role="roof-ornament")


# Bespoke broadleaf trees soften the inner rings, where the concept shows
# planted civic green rather than an unbroken conifer forest.
for index in range(24):
    angle = math.tau * index / 24.0 + math.radians(7.5)
    radius = 245.0 + (index % 3) * 18.0
    x, z = radius * math.sin(angle), radius * math.cos(angle)
    if min(abs(x), abs(z)) < 30.0:
        continue
    height = 15.0 + (index % 4) * 2.0
    add(f"Detail_Broadleaf_{index:02}_Trunk", "Vegetation", "cylinder_wood",
        (x, 36.0 + height * .32, z), (2.0, height * .64, 2.0), role="bespoke-vegetation")
    add(f"Detail_Broadleaf_{index:02}_Crown", "Vegetation", "detail_broadleaf_crown",
        (x, 40.0 + height * .72, z), (height * .46, height, height * .46), role="bespoke-vegetation")


# Rock clusters integrate each waterfall into the shoreline and two stepped
# foam tongues keep the edge legible before the client effect shader runs.
for index in range(8):
    angle = math.radians(25.0 + index * 45.0)
    radial = (math.sin(angle), math.cos(angle))
    tangent = (math.cos(angle), -math.sin(angle))
    yaw = angle
    for rock in range(4):
        side = -1.0 if rock % 2 else 1.0
        radius = 397.0 + (rock // 2) * 14.0
        x = radial[0] * radius + tangent[0] * side * (18.0 + rock * 2.0)
        z = radial[1] * radius + tangent[1] * side * (18.0 + rock * 2.0)
        add(f"Detail_Waterfall_{index:02}_Rock_{rock}", "Waterfalls", "cylinder_rock",
            (x, 2.0 + rock, z), (7.0 + rock, 7.0 + rock * 1.5, 6.0 + rock),
            rotation_y(yaw + rock * .37), "waterfall-edge")
    for ribbon, radius in enumerate((385.0, 401.0)):
        x, z = radial[0] * radius, radial[1] * radius
        add(f"Detail_Waterfall_{index:02}_Foam_Ribbon_{ribbon}", "Waterfalls", "cube_waterfall",
            (x, 1.0 + ribbon * 1.2, z), (30.0, .45, 7.5), rotation_y(angle), "waterfall-foam")


document["asset"]["generator"] = "Eloria Four Gates concept-art close-detail pass 0.9"
align_binary()
document["buffers"][0]["byteLength"] = len(binary)
encoded = json.dumps(document, separators=(",", ":")).encode()
encoded += b" " * ((-len(encoded)) % 4)
GLB.write_bytes(
    struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(encoded) + 8 + len(binary))
    + struct.pack("<I4s", len(encoded), b"JSON") + encoded
    + struct.pack("<I4s", len(binary), b"BIN\0") + binary
)

metadata_path = PACKAGE / "four-gates-city.json"
metadata = json.loads(metadata_path.read_text())
metadata["assetVersion"] = "0.9.0"
metadata["detailPass"] = {
    "reference": "canonical-four-gates-concept-art",
    "nodePrefix": "Detail_",
    "nodeCount": len(created),
    "detailNodes": created,
    "families": {
        "gates": ["integrated crowns", "energy tracery", "hanging banners"],
        "centralCivic": ["radial planted beds", "broadleaf shrubs"],
        "market": ["stock crates", "barrels", "sapphire signs"],
        "residential": ["balconies", "roof finials"],
        "waterfalls": ["rocky lips", "stepped foam ribbons"],
        "vegetation": ["inner-ring broadleaf trees", "tiered outer evergreens"],
    },
    "routeClearance": {"cardinalHalfWidth": 30.0, "plazaSpawnClear": True},
}
metadata["knownLimitations"] = [
    value for value in metadata["knownLimitations"]
    if "higher-density hero ornament" not in value.lower()
    and "bespoke vegetation" not in value.lower()
    and "lod0 and lod2 are documented but not included" not in value.lower()
    and "water, waterfall foam, and mist use" not in value.lower()
    and "later close-detail pass" not in value.lower()
]
metadata["knownLimitations"].append(
    "General district assets use modular atlas UVs; hero façades and roofs still need bespoke unwraps."
)
metadata["knownLimitations"].append(
    "Water, foam, mist, and energy retain static geometry fallbacks; production refraction, turbulence, depth-fade, and mist particles remain client-shader work."
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

print(json.dumps({
    "assetVersion": metadata["assetVersion"],
    "detailNodes": len(created),
    "nodes": len(nodes),
    "meshes": len(document["meshes"]),
    "glbBytes": GLB.stat().st_size,
}, indent=2))
