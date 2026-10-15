#!/usr/bin/env python3
"""Final concept-art visual pass for Four Gates.

This step is intentionally deterministic.  It adds the alpine skyline visible
in the canonical references and records the 0.7 material/geometry contract
after all earlier authored-map passes have completed.
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


def clone_mesh(name, prototype, material):
    if name in mesh_ids:
        return
    source = document["meshes"][mesh_ids[prototype]]
    primitive = dict(source["primitives"][0])
    primitive["attributes"] = dict(source["primitives"][0]["attributes"])
    primitive["material"] = material_ids[material]
    document["meshes"].append({"name": name, "primitives": [primitive]})
    mesh_ids[name] = len(document["meshes"]) - 1


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


def read_float_accessor(accessor_index, components):
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return np.frombuffer(binary, dtype="<f4", count=accessor["count"] * components,
                         offset=offset).reshape(-1, components).copy()


def add_faceted_mesh(name, triangles, material):
    positions, normals, uvs = [], [], []
    for triangle in triangles:
        points = np.asarray(triangle, np.float32)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        normal /= max(float(np.linalg.norm(normal)), 1e-6)
        positions.extend(points.tolist())
        normals.extend([normal.tolist()] * 3)
        uvs.extend([[point[0] + .5, point[1] + .5] for point in points])
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
        "indices": add_accessor(np.arange(len(positions), dtype=np.uint32), "SCALAR", 5125, 34963),
        "material": material_ids[material],
    }
    document["meshes"].append({"name": name, "primitives": [primitive]})
    mesh_ids[name] = len(document["meshes"]) - 1


def ring_mesh(rings, segments=9):
    vertices = []
    for ring_index, (height, radius) in enumerate(rings):
        ring = []
        for segment in range(segments):
            angle = math.tau * segment / segments
            irregularity = 1.0 + .11 * math.sin(segment * 4.7 + ring_index * 1.9)
            ring.append((radius * irregularity * math.cos(angle), height,
                         radius * (2.0 - irregularity) * math.sin(angle)))
        vertices.append(ring)
    triangles = []
    for ring_index in range(len(vertices) - 1):
        for segment in range(segments):
            following = (segment + 1) % segments
            a, b = vertices[ring_index][segment], vertices[ring_index][following]
            c, d = vertices[ring_index + 1][following], vertices[ring_index + 1][segment]
            triangles.extend(((a, b, c), (a, c, d)))
    return triangles


add_faceted_mesh("authored_mountain_rock",
                 ring_mesh([(-.5, .53), (-.18, .46), (.12, .31), (.36, .16), (.5, .025)]),
                 "rock")
add_faceted_mesh("authored_mountain_snowcap",
                 ring_mesh([(.16, .29), (.37, .16), (.505, .028)]), "snow")

evergreen_triangles = []
for base, radius, peak in ((-.42, .48, -.03), (-.16, .38, .23), (.08, .27, .5)):
    ring = [(radius * math.cos(math.tau * segment / 8), base,
             radius * math.sin(math.tau * segment / 8)) for segment in range(8)]
    tip = (0., peak, 0.)
    for segment in range(8):
        evergreen_triangles.append((ring[segment], ring[(segment + 1) % 8], tip))
add_faceted_mesh("authored_evergreen", evergreen_triangles, "vegetation")

for node in nodes:
    if node.get("name", "").startswith("Vegetation_Crown_"):
        node["mesh"] = mesh_ids["authored_evergreen"]


def add(name, parent, mesh, position, scale, extras=None):
    item = {
        "name": name,
        "mesh": mesh_ids[mesh],
        "translation": [float(value) for value in position],
        "scale": [float(value) for value in scale],
    }
    if extras:
        item["extras"] = extras
    nodes.append(item)
    nodes[node_ids[parent]].setdefault("children", []).append(len(nodes) - 1)
    return len(nodes) - 1


# A layered, uneven ring of distant peaks gives every gameplay camera the
# snowy mountain horizon shown in the paintings without adding collision.
random.seed(407)
mountain_nodes = []
for index in range(28):
    angle = math.tau * index / 28 + random.uniform(-0.055, 0.055)
    radius = random.uniform(650.0, 780.0)
    x, z = radius * math.sin(angle), radius * math.cos(angle)
    height = random.uniform(150.0, 285.0)
    width = random.uniform(80.0, 145.0)
    rock_name = f"Mountain_Peak_{index:02}"
    depth = width * random.uniform(.78, 1.14)
    add(rock_name, "Terrain", "authored_mountain_rock", (x, -28.0 + height * 0.5, z),
        (width, height, depth),
        {"visualOnly": True, "terrainRole": "alpine-skyline", "lod": "LOD2"})
    cap_name = f"Mountain_Snowcap_{index:02}"
    add(cap_name, "Terrain", "authored_mountain_snowcap", (x, -28.0 + height * 0.5, z),
        (width * 1.012, height * 1.012, depth * 1.012),
        {"visualOnly": True, "terrainRole": "snowcap", "lod": "LOD2"})
    mountain_nodes.extend((rock_name, cap_name))


# Evergreen clusters break up the bare shore silhouette while leaving every
# cardinal bridge and gate approach visibly clear.
evergreen_nodes = []
for index in range(56):
    angle = math.tau * index / 56 + random.uniform(-.035, .035)
    if min(abs((angle - cardinal + math.pi) % math.tau - math.pi)
           for cardinal in (0, math.pi / 2, math.pi, math.pi * 1.5)) < .11:
        continue
    radius = random.uniform(470.0, 590.0)
    x, z = radius * math.sin(angle), radius * math.cos(angle)
    height = random.uniform(25.0, 54.0)
    name = f"Outer_Evergreen_{index:02}"
    add(name, "Vegetation", "authored_evergreen", (x, 5.0 + height * .5, z),
        (height * .34, height, height * .34),
        {"visualOnly": True, "terrainRole": "outer-forest", "lod": "LOD1"})
    evergreen_nodes.append(name)


# Godot's glTF importer does not consistently apply KHR_texture_transform to
# every generated primitive.  Bake each material's atlas rectangle into that
# primitive's UV accessor so all clients sample the same swatch, then remove
# the now-redundant extension.  A one-texel inset prevents mip bleed.
city_rects = {
    "stone": (0, 0), "dark-stone": (1, 0), "paving": (2, 0), "rock": (3, 0),
    "roof": (0, 1), "bronze": (1, 1), "wood": (3, 1), "plaster": (0, 2),
    "soil": (1, 2), "grass": (2, 2), "snow": (3, 2), "water": (0, 3),
    "blue-crystal": (1, 3), "waterfall": (2, 3), "vegetation": (3, 3),
}
landmark_rects = {
    "landmark-stone": (0, 0), "landmark-bronze": (1, 0),
    "landmark-foundation": (0, 1), "landmark-energy": (1, 1),
}
for mesh in document["meshes"]:
    for primitive in mesh["primitives"]:
        material = document["materials"][primitive["material"]]
        pbr = material.get("pbrMetallicRoughness", {})
        texture_info = pbr.get("baseColorTexture", {})
        transform = texture_info.get("extensions", {}).get("KHR_texture_transform")
        uv_accessor = primitive.get("attributes", {}).get("TEXCOORD_0")
        if transform is None or uv_accessor is None:
            continue
        name = material.get("name", "")
        if name in city_rects:
            column, row = city_rects[name]
            offset = np.asarray([column * .25, row * .25], np.float32)
            scale = np.asarray([.25, .25], np.float32)
        elif name in landmark_rects:
            column, row = landmark_rects[name]
            offset = np.asarray([column * .5, row * .5], np.float32)
            scale = np.asarray([.5, .5], np.float32)
        else:
            offset = np.asarray(transform.get("offset", [0., 0.]), np.float32)
            scale = np.asarray(transform.get("scale", [1., 1.]), np.float32)
        local_uv = np.mod(read_float_accessor(uv_accessor, 2), 1.0)
        inset = np.asarray([1.0 / 1024.0, 1.0 / 1024.0], np.float32)
        baked_uv = offset + inset + local_uv * (scale - inset * 2.0)
        primitive["attributes"]["TEXCOORD_0"] = add_accessor(baked_uv, "VEC2")

for material in document["materials"]:
    infos = [
        material.get("pbrMetallicRoughness", {}).get("baseColorTexture"),
        material.get("pbrMetallicRoughness", {}).get("metallicRoughnessTexture"),
        material.get("normalTexture"), material.get("occlusionTexture"),
        material.get("emissiveTexture"),
    ]
    for texture_info in infos:
        if isinstance(texture_info, dict):
            extensions = texture_info.get("extensions")
            if isinstance(extensions, dict):
                extensions.pop("KHR_texture_transform", None)
                if not extensions:
                    texture_info.pop("extensions", None)
document["extensionsUsed"] = [
    value for value in document.get("extensionsUsed", [])
    if value != "KHR_texture_transform"
]
if not document["extensionsUsed"]:
    document.pop("extensionsUsed", None)


document["asset"]["generator"] = "Eloria Four Gates concept-art visual pass 0.8"
while len(binary) % 4:
    binary += b"\0"
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
metadata["assetVersion"] = "0.8.0"
metadata["materials"]["strategy"] = "embedded-atlas-with-baked-primitive-uvs"
metadata["materials"].pop("extension", None)
metadata["visualDirection"] = {
    "reference": "canonical-four-gates-concept-art",
    "palette": ["warm limestone", "charcoal slate", "aged gold", "sapphire", "turquoise", "alpine green"],
    "materialAtlas": "art-directed-4x4-pbr-basecolor",
    "landmarkAtlas": "art-directed-2x2-pbr-basecolor",
    "alpineSkylineNodes": mountain_nodes,
    "outerEvergreenNodes": evergreen_nodes,
}
metadata["knownLimitations"] = [
    value for value in metadata["knownLimitations"]
    if "bespoke district UVs" not in value.lower()
]
metadata["knownLimitations"].append(
    "General district assets use modular atlas UVs; hero façades and roofs should receive bespoke unwraps in a later close-detail pass."
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

print(json.dumps({
    "assetVersion": metadata["assetVersion"],
    "nodes": len(nodes),
    "mountainNodes": len(mountain_nodes),
    "outerEvergreenNodes": len(evergreen_nodes),
    "glbBytes": GLB.stat().st_size,
}, indent=2))
