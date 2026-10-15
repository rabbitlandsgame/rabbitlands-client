import copy, io, json, struct
from pathlib import Path
from PIL import Image

P = Path("four-gates-city-package")
src = P / "four-gates-city.glb"
raw = src.read_bytes()
jl = struct.unpack_from("<I", raw, 12)[0]
g = json.loads(raw[20:20 + jl])
bo = 20 + jl
bl = struct.unpack_from("<I", raw, bo)[0]
oldbin = raw[bo + 8:bo + 8 + bl]

drop = ("Battlement_", "Plaza_Bench_", "Plaza_Lamp_", "Market_", "Farm_Fence_", "Residence_", "Civic_Hall_", "Farmhouse_", "Granary_", "Irrigation_", "Service_", "Ring_", "Vegetation_", "Water_Channel_", "Waterfall_Pool_", "Waterfall_Foam_", "FX_Waterfall_Mist_", "Detail_")
keep = [not n.get("name", "").endswith("_LOD0") and not n.get("name", "").startswith(drop) and "_Authored_Arch_" not in n.get("name", "") and "_Energy_Inlay_" not in n.get("name", "") for n in g["nodes"]]
node_map = {old: new for new, old in enumerate(i for i, yes in enumerate(keep) if yes)}
nodes = []
for old, yes in enumerate(keep):
    if not yes:
        continue
    n = copy.deepcopy(g["nodes"][old])
    if "children" in n:
        n["children"] = [node_map[c] for c in n["children"] if c in node_map]
        if not n["children"]:
            n.pop("children")
    nodes.append(n)

used_meshes = sorted({n["mesh"] for n in nodes if "mesh" in n})
mesh_map = {old: new for new, old in enumerate(used_meshes)}
for n in nodes:
    if "mesh" in n:
        n["mesh"] = mesh_map[n["mesh"]]
meshes = [copy.deepcopy(g["meshes"][i]) for i in used_meshes]

used_materials = sorted({p.get("material") for m in meshes for p in m["primitives"] if "material" in p})
material_map = {old: new for new, old in enumerate(used_materials)}
for m in meshes:
    for p in m["primitives"]:
        if "material" in p:
            p["material"] = material_map[p["material"]]
materials = [copy.deepcopy(g["materials"][i]) for i in used_materials]

used_textures = set()
for m in materials:
    stack = [m]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if "index" in x and set(x).intersection({"index", "texCoord", "extensions", "scale", "strength"}):
                used_textures.add(x["index"])
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
used_textures = sorted(used_textures)
texture_map = {old: new for new, old in enumerate(used_textures)}
def remap_texture_indices(x):
    if isinstance(x, dict):
        if "index" in x and x["index"] in texture_map:
            x["index"] = texture_map[x["index"]]
        for value in x.values(): remap_texture_indices(value)
    elif isinstance(x, list):
        for value in x: remap_texture_indices(value)
for m in materials: remap_texture_indices(m)
textures = [copy.deepcopy(g["textures"][i]) for i in used_textures]
used_images = sorted({t["source"] for t in textures if "source" in t})
image_map = {old: new for new, old in enumerate(used_images)}
for t in textures:
    if "source" in t: t["source"] = image_map[t["source"]]
images = [copy.deepcopy(g["images"][i]) for i in used_images]

used_accessors = set()
for m in meshes:
    for p in m["primitives"]:
        used_accessors.update(p.get("attributes", {}).values())
        if "indices" in p: used_accessors.add(p["indices"])
used_accessors = sorted(used_accessors)
accessor_map = {old: new for new, old in enumerate(used_accessors)}
for m in meshes:
    for p in m["primitives"]:
        p["attributes"] = {k: accessor_map[v] for k, v in p.get("attributes", {}).items()}
        if "indices" in p: p["indices"] = accessor_map[p["indices"]]
accessors = [copy.deepcopy(g["accessors"][i]) for i in used_accessors]

used_views = {a["bufferView"] for a in accessors if "bufferView" in a}
used_views.update(i["bufferView"] for i in images if "bufferView" in i)
used_views = sorted(used_views)
view_map = {old: new for new, old in enumerate(used_views)}
binary = bytearray()
views = []
image_view_ids = {g["images"][old]["bufferView"] for old in used_images}
for old in used_views:
    while len(binary) % 4: binary.append(0)
    source = g["bufferViews"][old]
    start = source.get("byteOffset", 0)
    chunk = oldbin[start:start + source["byteLength"]]
    # The overview LOD does not need close-inspection 1K maps. Re-encode embedded
    # PNGs at 512 px while retaining standard glTF embedded-image semantics.
    if old in image_view_ids:
        image = Image.open(io.BytesIO(chunk)).convert("RGBA" if Image.open(io.BytesIO(chunk)).mode == "RGBA" else "RGB")
        if max(image.size) > 512:
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        encoded = io.BytesIO(); image.save(encoded, format="PNG", optimize=True)
        chunk = encoded.getvalue()
    item = {k: copy.deepcopy(v) for k, v in source.items() if k not in ("byteOffset", "buffer")}
    item["byteLength"] = len(chunk)
    item["buffer"] = 0
    item["byteOffset"] = len(binary)
    views.append(item)
    binary.extend(chunk)
for a in accessors:
    if "bufferView" in a: a["bufferView"] = view_map[a["bufferView"]]
for i in images:
    i["bufferView"] = view_map[i["bufferView"]]

lod = {k: copy.deepcopy(v) for k, v in g.items() if k not in ("nodes", "meshes", "materials", "textures", "images", "accessors", "bufferViews", "animations")}
lod.update({"nodes": nodes, "meshes": meshes, "materials": materials, "textures": textures, "images": images, "accessors": accessors, "bufferViews": views})
lod["scenes"] = [{"name": "Four Gates City LOD2", "nodes": [node_map[0]]}]
lod["asset"]["generator"] = "Eloria Four Gates compact resource-pruned LOD2 0.9"
lod["buffers"] = [{"byteLength": len(binary)}]
while len(binary) % 4: binary.append(0)
lod["buffers"][0]["byteLength"] = len(binary)
jb = json.dumps(lod, separators=(",", ":")).encode(); jb += b" " * ((-len(jb)) % 4)
out = P / "four-gates-city-lod2.glb"
out.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binary)) + struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(binary), b"BIN\0") + binary)

meta = json.loads((P / "four-gates-city.json").read_text())
meta["lodGroups"][0]["levels"][2].update({"glb": out.name, "nodeCount": len(nodes), "meshCount": len(meshes), "materialCount": len(materials), "textureMaxResolution": 512, "animations": 0, "resourcePruned": True})
(P / "four-gates-city.json").write_text(json.dumps(meta, indent=2) + "\n")
lm = copy.deepcopy(meta); lm["asset"]["glb"] = out.name; lm["assetVersion"] = "0.9.0-lod2"; lm["animations"] = []
lod_node_names = {node.get("name") for node in nodes}
def prune_node_references(value, key=None):
    if isinstance(value, dict):
        if isinstance(value.get("node"), str) and value["node"] not in lod_node_names:
            return None
        if isinstance(value.get("targetNode"), str) and value["targetNode"] not in lod_node_names:
            return None
        result = {}
        for child_key, child in value.items():
            pruned = prune_node_references(child, child_key)
            if pruned is not None:
                result[child_key] = pruned
        return result
    if isinstance(value, list):
        if key and key.endswith("Nodes") and all(isinstance(child, str) for child in value):
            return [child for child in value if child in lod_node_names]
        return [pruned for child in value if (pruned := prune_node_references(child, key)) is not None]
    return value
lm = prune_node_references(lm)
if "waterSystem" in lm:
    lm["waterSystem"]["waterfallCount"] = len(lm["waterSystem"].get("channelNodes", []))
(P / "four-gates-city-lod2.json").write_text(json.dumps(lm, indent=2) + "\n")
print(json.dumps({"lod2Nodes": len(nodes), "lod2Meshes": len(meshes), "lod2Materials": len(materials), "lod2Bytes": out.stat().st_size, "reductionPct": round((1 - out.stat().st_size / src.stat().st_size) * 100, 1)}, indent=2))
