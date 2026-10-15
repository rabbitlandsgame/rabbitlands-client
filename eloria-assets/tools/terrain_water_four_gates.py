import json, math, random, struct
from pathlib import Path

import numpy as np

P = Path("four-gates-city-package")
F = P / "four-gates-city.glb"
raw = F.read_bytes()
jl, _ = struct.unpack_from("<I4s", raw, 12)
g = json.loads(raw[20:20 + jl])
bo = 20 + jl
bl, _ = struct.unpack_from("<I4s", raw, bo)
buf = bytearray(raw[bo + 8:bo + 8 + bl])


def align():
    while len(buf) % 4:
        buf.append(0)


def view(data, target=None):
    align()
    offset = len(buf)
    buf.extend(data)
    item = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
    if target:
        item["target"] = target
    g["bufferViews"].append(item)
    return len(g["bufferViews"]) - 1


def accessor(a, kind, component=5126, target=34962):
    dtype = np.float32 if component == 5126 else np.uint32
    a = np.asarray(a, dtype=dtype)
    item = {
        "bufferView": view(a.tobytes(), target),
        "componentType": component,
        "count": len(a),
        "type": kind,
        "min": a.min(0).tolist() if a.ndim > 1 else [int(a.min())],
        "max": a.max(0).tolist() if a.ndim > 1 else [int(a.max())],
    }
    g["accessors"].append(item)
    return len(g["accessors"]) - 1


def mesh(name, vertices, faces, normals, uv, material):
    normals = np.asarray(normals, np.float32)
    tangents = np.cross(np.tile([0.0, 1.0, 0.0], (len(normals), 1)), normals)
    weak = np.linalg.norm(tangents, axis=1) < 1e-5
    tangents[weak] = [1, 0, 0]
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-6)
    tangents = np.column_stack((tangents, np.ones(len(tangents), np.float32)))
    primitive = {
        "attributes": {
            "POSITION": accessor(vertices, "VEC3"),
            "NORMAL": accessor(normals, "VEC3"),
            "TEXCOORD_0": accessor(uv, "VEC2"),
            "TANGENT": accessor(tangents, "VEC4"),
        },
        "indices": accessor(np.asarray(faces, np.uint32).reshape(-1), "SCALAR", 5125, 34963),
        "material": material,
    }
    g["meshes"].append({"name": name, "primitives": [primitive]})
    return len(g["meshes"]) - 1


def write(path, doc, binary):
    while len(binary) % 4:
        binary.append(0)
    doc["buffers"][0]["byteLength"] = len(binary)
    jb = json.dumps(doc, separators=(",", ":")).encode()
    jb += b" " * ((-len(jb)) % 4)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binary))
        + struct.pack("<I4s", len(jb), b"JSON") + jb
        + struct.pack("<I4s", len(binary), b"BIN\0") + binary
    )


materials = {m.get("name"): i for i, m in enumerate(g["materials"])}
nodes = g["nodes"]
names = {n.get("name"): i for i, n in enumerate(nodes)}


def add(name, parent, mesh_id=None, translation=(0, 0, 0), scale=(1, 1, 1), rotation=None, extras=None):
    item = {"name": name, "translation": list(map(float, translation)), "scale": list(map(float, scale))}
    if mesh_id is not None:
        item["mesh"] = mesh_id
    if rotation:
        item["rotation"] = rotation
    if extras:
        item["extras"] = extras
    nodes.append(item)
    nodes[names[parent]].setdefault("children", []).append(len(nodes) - 1)
    names[name] = len(nodes) - 1
    return len(nodes) - 1


def radial_band(name, radii, heights, segments, material, seed=606):
    """Concentric irregular band; local mesh centered on the city origin."""
    random.seed(seed)
    v, n, uv, f = [], [], [], []
    jitter = [random.uniform(-5.5, 5.5) for _ in range(segments)]
    for ring, (radius, height) in enumerate(zip(radii, heights)):
        for i in range(segments):
            a = math.tau * i / segments
            r = radius + jitter[i] * (0.25 + ring * 0.2)
            y = height + math.sin(a * 5 + ring) * 1.4 + math.sin(a * 11) * 0.7
            v.append([r * math.cos(a), y, r * math.sin(a)])
            slope = (heights[min(ring + 1, len(heights) - 1)] - heights[max(ring - 1, 0)]) / max(1, radii[min(ring + 1, len(radii) - 1)] - radii[max(ring - 1, 0)])
            nn = np.array([-slope * math.cos(a), 1.0, -slope * math.sin(a)], np.float32)
            nn /= np.linalg.norm(nn)
            n.append(nn.tolist())
            uv.append([i / segments * 8, ring / max(1, len(radii) - 1) * 3])
    for ring in range(len(radii) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a = ring * segments + i
            b = ring * segments + j
            c = (ring + 1) * segments + j
            d = (ring + 1) * segments + i
            f += [[a, b, c], [a, c, d]]
    return mesh(name, v, f, n, uv, material)


def channel_mesh(name, width=13, length=92, drops=8, material=12):
    v, n, uv, f = [], [], [], []
    rows = 10
    for j in range(rows + 1):
        t = j / rows
        z = -length * 0.5 + length * t
        y = 15 - drops * t - 1.2 * math.sin(math.pi * t)
        for side in (-1, 1):
            x = side * width * (0.42 + 0.08 * math.sin(math.pi * t))
            v.append([x, y, z])
            n.append([0, 1, 0])
            uv.append([(side + 1) * 0.5, t * 4])
    for j in range(rows):
        a = j * 2
        f += [[a, a + 1, a + 3], [a, a + 3, a + 2]]
    return mesh(name, v, f, n, uv, material)


def disc_mesh(name, segments, material):
    v = [[0, 0, 0]]
    n = [[0, 1, 0]]
    uv = [[0.5, 0.5]]
    for i in range(segments):
        a = math.tau * i / segments
        r = 1 + 0.1 * math.sin(a * 5)
        v.append([r * math.cos(a), 0, r * math.sin(a)])
        n.append([0, 1, 0])
        uv.append([0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)])
    f = [[0, 1 + i, 1 + ((i + 1) % segments)] for i in range(segments)]
    return mesh(name, v, f, n, uv, material)


# Replace the flat plateau with continuous terraces and a cragged descending shoreline.
terrace = radial_band("authored_city_terraces", [0, 175, 285, 365, 400], [36, 35, 31, 24, 16], 96, materials["grass"])
shore = radial_band("authored_rocky_shore", [365, 395, 420, 454], [24, 14, 2, -7], 128, materials["rock"], 607)
nodes[names["Terrain_City_Plateau"]]["mesh"] = terrace
nodes[names["Terrain_City_Plateau"]]["translation"] = [0, 0, 0]
nodes[names["Terrain_City_Plateau"]]["scale"] = [1, 1, 1]
nodes[names["Terrain_City_Plateau"]].setdefault("extras", {})["authoredGeometry"] = "0.6"
add("Terrain_Shoreline_Sculpt", "Terrain", shore, extras={"lod": "LOD1", "terrainRole": "shore-transition"})

# Existing cliff nodes remain recognizable and become deeper, tangent-aligned buttresses.
for n in nodes:
    name = n.get("name", "")
    if name.startswith("Cliff_") and name[6:].isdigit():
        x, _, z = n["translation"]
        angle = math.atan2(x, z)
        n["rotation"] = [0, math.sin(angle / 2), 0, math.cos(angle / 2)]
        n["scale"] = [48, 48, 18]
        n["translation"][1] = 4
        n.setdefault("extras", {}).update({"authoredGeometry": "0.6", "terrainRole": "cliff-buttress"})

channel = channel_mesh("authored_waterfall_channel", material=materials["water"])
pool = disc_mesh("authored_plunge_pool", 40, materials["water"])
foam = disc_mesh("authored_waterfall_foam", 32, materials["waterfall"])

# Radial channels align with the eight established waterfalls and finish in layered pools.
for i in range(8):
    a = math.radians(25 + i * 45)
    x, z = 337 * math.sin(a), 337 * math.cos(a)
    q = [0, math.sin(a / 2), 0, math.cos(a / 2)]
    add(f"Water_Channel_{i:02}", "Waterfalls", channel, (x, 0, z), rotation=q,
        extras={"effect": "flowing-water", "direction": [math.sin(a), -0.12, math.cos(a)], "shaderHint": "water-channel"})
    px, pz = 405 * math.sin(a), 405 * math.cos(a)
    add(f"Waterfall_Pool_{i:02}", "Waterfalls", pool, (px, -1.0, pz), (25, 1, 18), rotation=q,
        extras={"effect": "plunge-pool", "navigable": False, "shaderHint": "water-turbulence"})
    add(f"Waterfall_Foam_{i:02}", "Waterfalls", foam, (px, 0.15, pz), (15, 1, 10), rotation=q,
        extras={"effect": "foam", "opacity": 0.72, "shaderHint": "alpha-foam"})
    add(f"FX_Waterfall_Mist_{i:02}", "Waterfalls", None, (px, 8, pz), (20, 18, 14), rotation=q,
        extras={"effectType": "mist-emitter", "color": [0.72, 0.9, 1.0], "intensity": 0.65, "direction": [math.sin(a) * 0.18, 0.5, math.cos(a) * 0.18]})

g["asset"]["generator"] = "Eloria Four Gates terrain and water integration pass 0.6"
write(F, g, buf)

meta_path = P / "four-gates-city.json"
m = json.loads(meta_path.read_text())
m["assetVersion"] = "0.6.1"
m["terrain"] = {
    "minimumUsefulElevation": -40.0,
    "cityTerraceNode": "Terrain_City_Plateau",
    "shorelineNode": "Terrain_Shoreline_Sculpt",
    "terraceRadii": [175, 285, 365, 400],
    "shorelineOuterRadius": 454,
    "waterLevel": -2.0,
}
m["waterSystem"] = {
    "waterfallCount": 8,
    "channelNodes": [f"Water_Channel_{i:02}" for i in range(8)],
    "poolNodes": [f"Waterfall_Pool_{i:02}" for i in range(8)],
    "foamNodes": [f"Waterfall_Foam_{i:02}" for i in range(8)],
    "mistLocatorNodes": [f"FX_Waterfall_Mist_{i:02}" for i in range(8)],
    "requiresCustomShaderForBestResult": True,
}
m["effects"].extend([
    {"id": f"waterfall-mist-{i:02}", "node": f"FX_Waterfall_Mist_{i:02}", "type": "mist-emitter", "dimensions": [40, 36, 28], "color": [0.72, 0.9, 1.0], "intensity": 0.65, "fallback": "locator-only"}
    for i in range(8)
])
m["knownLimitations"] = [x for x in m["knownLimitations"] if "cliff" not in x.lower() and "waterfall" not in x.lower()]
m["knownLimitations"].append("Water, waterfall foam, and mist use glTF geometry and locators; animated turbulence, refraction, particles, and depth fade require client shaders.")
meta_path.write_text(json.dumps(m, indent=2) + "\n")

print(json.dumps({"assetVersion": "0.6.1", "nodes": len(nodes), "meshes": len(g["meshes"]), "glbBytes": F.stat().st_size}, indent=2))
