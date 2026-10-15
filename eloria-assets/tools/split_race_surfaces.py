"""Split a race body's fused mesh into the named appearance surfaces.

The runtime's appearance system tints and toggles by mesh-node name --
``body``, ``eyes``, ``hair``, ``wardrobe_shirt``, ``wardrobe_pants``,
``wardrobe_boots`` -- but the luminous bodies ship as one fused primitive
called ``char1``, so the skin, eye and head options match nothing, the
built-in hair cannot be hidden under a chosen style, and the painted
outfit cannot be recoloured.

The split shares every vertex attribute: each surface becomes its own
mesh node carrying the SAME position/normal/uv/skin accessors and only
its own index buffer, so the geometry is bit-identical and the fitter's
measurements do not move.  Faces are classified by the texel under their
UV centroid plus height priors.  The wardrobe surfaces get a grayscale
copy of the texture so the runtime's albedo colour multiplies into true
cloth colours; a plain band and cap are generated for the head styles
the runtime already knows how to toggle.

Usage:
    python split_race_surfaces.py [--race luminous_male] [--calibrate]
"""
from __future__ import annotations

import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent
RACES = (TOOLS.parent.parent / "godot-client" / "assets" / "actors"
         / "native" / "races")

CLASSES = ("body", "eyes", "hair", "wardrobe_shirt", "wardrobe_pants",
           "wardrobe_boots")
CLASS_COLOURS = {
    "body": (205, 170, 140), "eyes": (0, 255, 255), "hair": (255, 0, 255),
    "wardrobe_shirt": (40, 160, 220), "wardrobe_pants": (60, 60, 200),
    "wardrobe_boots": (200, 120, 40),
}


def read_glb(path: Path):
    data = path.read_bytes()
    assert data[:4] == b"glTF", path
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    assert json_type == b"JSON"
    document = json.loads(data[20:20 + json_len])
    binary = bytearray(data[20 + json_len:])
    assert binary[4:7] == b"BIN"
    return document, binary


def write_glb(path: Path, document, binary) -> None:
    struct.pack_into("<I", binary, 0, len(binary) - 8)
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    out = bytearray(b"glTF")
    out += struct.pack("<II", 2, 12 + 8 + len(payload) + len(binary))
    out += struct.pack("<I4s", len(payload), b"JSON")
    out += payload
    out += binary
    path.write_bytes(bytes(out))


def accessor_array(document, binary, index):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    comp = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32,
            5126: np.float32}[acc["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
         "MAT4": 16}[acc["type"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    raw = np.frombuffer(bytes(binary[offset:offset
                                     + acc["count"] * n * np.dtype(comp).itemsize]),
                        dtype=comp)
    out = raw.reshape(acc["count"], n).astype(np.float64)
    if acc.get("normalized"):
        out = out / np.iinfo(comp).max
    return out


def append_view(document, binary, payload: bytes, target=None) -> int:
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary) - 8
    binary.extend(payload)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
    if target:
        view["target"] = target
    document["bufferViews"].append(view)
    return len(document["bufferViews"]) - 1


def append_accessor(document, binary, array, ctype, atype,
                    target=None) -> int:
    payload = np.ascontiguousarray(array).tobytes()
    view = append_view(document, binary, payload, target)
    accessor = {"bufferView": view, "componentType": ctype,
                "count": int(len(array)), "type": atype}
    if atype == "VEC3" and ctype == 5126:
        accessor["min"] = [float(v) for v in array.min(axis=0)]
        accessor["max"] = [float(v) for v in array.max(axis=0)]
    document["accessors"].append(accessor)
    return len(document["accessors"]) - 1


def classify(positions, uvs, indices, texture: Image.Image):
    tex = np.asarray(texture.convert("RGB")).astype(np.float64) / 255.0
    height, width = tex.shape[:2]
    faces = indices.reshape(-1, 3)
    centroids = positions[faces].mean(axis=1)
    uv = uvs[faces].mean(axis=1)
    px = np.clip((uv[:, 0] % 1.0) * (width - 1), 0, width - 1).astype(int)
    py = np.clip((uv[:, 1] % 1.0) * (height - 1), 0, height - 1).astype(int)
    rgb = tex[py, px]
    mx = rgb.max(axis=1)
    mn = rgb.min(axis=1)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-9), 0)
    hue = np.zeros(len(rgb))
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    m = (mx == g) & (delta > 0)
    hue[m] = (2.0 + (b - r)[m] / delta[m]) / 6.0
    m = (mx == b) & (delta > 0)
    hue[m] = (4.0 + (r - g)[m] / delta[m]) / 6.0
    m = (mx == r) & (delta > 0)
    hue[m] = (((g - b)[m] / delta[m]) / 6.0) % 1.0
    y = centroids[:, 1]

    teal = (hue > 0.40) & (hue < 0.62) & (sat > 0.25)
    dark = mx < 0.32
    labels = np.full(len(faces), "body", dtype=object)
    labels[(y < 0.34)] = "wardrobe_boots"
    pantsish = (y >= 0.30) & (y < 1.12) & ((mx < 0.45) | (sat < 0.22))
    labels[pantsish] = "wardrobe_pants"
    labels[teal & (y >= 0.85) & (y < 1.58)] = "wardrobe_shirt"
    # Eyes are teal too, but only inside the face box -- the shirt's
    # V-collar reaches past 1.52 and grabbed the class before the box.
    eye_zone = teal & (y >= 1.58) & (np.abs(centroids[:, 0]) < 0.09)
    labels[eye_zone] = "eyes"
    labels[teal & (y >= 1.58) & ~eye_zone] = "wardrobe_shirt"
    labels[dark & (y >= 1.45) & ~teal] = "hair"
    return faces, labels


def grayscale_texture(texture: Image.Image) -> bytes:
    tex = np.asarray(texture.convert("RGB")).astype(np.float64) / 255.0
    lum = tex @ np.array([0.299, 0.587, 0.114])
    lifted = np.clip(lum / max(float(np.percentile(lum, 75)), 1e-6), 0, 1)
    img = Image.fromarray((lifted * 255).astype(np.uint8)).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def ring(radius, y0, y1, segments=24):
    verts, norms, uv = [], [], []
    for level, yy in ((0, y0), (1, y1)):
        for s in range(segments):
            a = 2 * np.pi * s / segments
            verts.append([radius * np.sin(a), yy, -radius * np.cos(a)])
            norms.append([np.sin(a), 0.0, -np.cos(a)])
            uv.append([s / segments, level])
    faces = []
    for s in range(segments):
        n = (s + 1) % segments
        faces += [[s, segments + s, segments + n], [s, segments + n, n]]
    return (np.array(verts), np.array(norms), np.array(uv),
            np.array(faces, dtype=np.uint32).reshape(-1))


def dome(radius, y0, segments=24, rows=5):
    verts, norms, uv = [], [], []
    for row in range(rows + 1):
        t = row / rows * (np.pi / 2)
        for s in range(segments):
            a = 2 * np.pi * s / segments
            direction = np.array([np.cos(t) * np.sin(a), np.sin(t),
                                  -np.cos(t) * np.cos(a)])
            verts.append([direction[0] * radius, y0 + direction[1] * radius,
                          direction[2] * radius])
            norms.append(direction)
            uv.append([s / segments, row / rows])
    faces = []
    for row in range(rows):
        for s in range(segments):
            n = (s + 1) % segments
            a0 = row * segments + s
            a1 = row * segments + n
            b0 = (row + 1) * segments + s
            b1 = (row + 1) * segments + n
            faces += [[a0, b0, b1], [a0, b1, a1]]
    return (np.array(verts), np.array(norms), np.array(uv),
            np.array(faces, dtype=np.uint32).reshape(-1))


def add_scalp(document, binary) -> int:
    """A skull under the hair: the sculpted hair IS the head's outer
    surface, so hiding it under a chosen style opened a hole.  The scalp
    duplicates the hair surface pulled inward along its normals -- same
    topology, so it meets the face boundary exactly -- with a plain skin
    material the runtime tints with the rest of the body."""
    hair_node = next((n for n in document["nodes"]
                      if n.get("name") == "hair" and "mesh" in n), None)
    if hair_node is None:
        return 0
    prim = document["meshes"][hair_node["mesh"]]["primitives"][0]
    positions = accessor_array(document, binary, prim["attributes"]["POSITION"])
    normals = accessor_array(document, binary, prim["attributes"]["NORMAL"])
    uvs = accessor_array(document, binary, prim["attributes"]["TEXCOORD_0"])
    joints = accessor_array(document, binary, prim["attributes"]["JOINTS_0"])
    weights = accessor_array(document, binary, prim["attributes"]["WEIGHTS_0"])
    indices = accessor_array(document, binary,
                             prim["indices"]).reshape(-1).astype(np.int64)
    # Skull-adjacent faces only: the sculpted hair can carry a ponytail
    # or a crest, and a scalp cloned from those hangs off the head as a
    # skin-coloured streamer.  The hole that needs closing hugs the
    # skull, so faces keep only if every corner sits near the head joint.
    skin = document["skins"][0]
    joints_list = skin["joints"]
    names = [document["nodes"][j].get("name", "") for j in joints_list]
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    head_row = names.index("Head")
    ibm = np.asarray(ibms[head_row], dtype=np.float64).reshape(4, 4).T
    head_global = np.linalg.inv(ibm)[:3, 3]
    # The scalp is a fitted cranium dome, not a shrunk hair clone: tall
    # sculpted hair (the male pompadour, the female tail) reaches far
    # enough from the skull that pulling its shell inward either leaves
    # crown holes or dangles streamers.  A sphere least-squares fitted to
    # the head's own SKIN vertices gives the true cranium; the dome is
    # its upper reach with the rim tucked slightly inward under the
    # hairline.
    body_node = next(n for n in document["nodes"]
                     if n.get("name") == "body" and "mesh" in n)
    body_prim = document["meshes"][body_node["mesh"]]["primitives"][0]
    body_positions = accessor_array(document, binary,
                                    body_prim["attributes"]["POSITION"])
    body_indices = accessor_array(
        document, binary, body_prim["indices"]).reshape(-1).astype(np.int64)
    skin_used = np.unique(body_indices)
    del skin_used
    # The whole hair shell, pulled inward, proved the right scalp -- its
    # seam meets the face exactly and the crown reads as a buzz cut (the
    # painted forehead hairline hides the 12 mm inset fringe).  The one
    # genuine defect was cloning geometry that hangs BELOW the head
    # joint: a ponytail became a skin streamer down the neck.  So: every
    # hair face whose centroid sits above the joint, nothing else.
    faces3 = indices.reshape(-1, 3)
    centroids = positions[faces3].mean(axis=1)
    horizontal = np.linalg.norm(
        centroids[:, [0, 2]] - head_global[[0, 2]], axis=1)
    near = ((centroids[:, 1] > float(head_global[1]) + 0.005)
            & (horizontal < 0.115))
    kept3 = faces3[near]
    # Every piece that hugs the skull, not merely the biggest: a sculpt
    # is many separate locks, so keeping only the largest left an eight
    # centimetre patch instead of a cap.  Each connected piece is judged
    # on its own -- close to the head's axis and not a stray chip.
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in kept3:
        ra, rb, rc = find(int(a)), find(int(b)), find(int(c))
        parent[rb] = ra
        parent[find(rc)] = find(ra)
    groups = {}
    for face_index, face in enumerate(kept3):
        groups.setdefault(find(int(face[0])), []).append(face_index)
    keep_face = np.zeros(len(kept3), dtype=bool)
    for root, members in groups.items():
        block = kept3[members]
        centre = positions[block.reshape(-1)].mean(axis=0)
        reach = float(np.linalg.norm(centre[[0, 2]] - head_global[[0, 2]]))
        if len(members) >= 8 and reach < 0.09:
            keep_face[members] = True
    kept = kept3[keep_face].reshape(-1)
    used = np.unique(kept)
    remap = np.full(len(positions), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    unit = normals[used]
    unit = unit / np.maximum(np.linalg.norm(unit, axis=1, keepdims=True),
                             1e-9)
    scalp_positions = (positions[used] - unit * 0.012).astype(np.float32)
    dome_indices = remap[kept].astype(np.uint32)
    scalp_normals = unit.astype(np.float32)
    scalp_uv = uvs[used].astype(np.float32)
    pos_acc = append_accessor(document, binary, scalp_positions, 5126,
                              "VEC3", 34962)
    norm_acc = append_accessor(document, binary, scalp_normals, 5126,
                               "VEC3", 34962)
    uv_acc = append_accessor(document, binary, scalp_uv, 5126, "VEC2",
                             34962)
    joints_acc = append_accessor(document, binary,
                                 joints[used].astype(np.uint16), 5123,
                                 "VEC4", 34962)
    weights_acc = append_accessor(document, binary,
                                  weights[used].astype(np.float32), 5126,
                                  "VEC4", 34962)
    idx_acc = append_accessor(document, binary, dome_indices, 5125,
                              "SCALAR", 34963)
    document["materials"].append({
        "name": "Scalp",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.78, 0.60, 0.47, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.85,
        },
    })
    mesh_node_skin = next(n["skin"] for n in document["nodes"]
                          if n.get("name") == "hair")
    document["meshes"].append({"name": "scalp", "primitives": [{
        "attributes": {"POSITION": pos_acc, "NORMAL": norm_acc,
                       "TEXCOORD_0": uv_acc, "JOINTS_0": joints_acc,
                       "WEIGHTS_0": weights_acc},
        "indices": idx_acc,
        "material": len(document["materials"]) - 1}]})
    document["nodes"].append({"name": "scalp",
                              "mesh": len(document["meshes"]) - 1,
                              "skin": mesh_node_skin})
    parent = next(i for i, n in enumerate(document["nodes"])
                  if any(document["nodes"][c].get("name") == "hair"
                         for c in n.get("children", [])))
    document["nodes"][parent]["children"].append(len(document["nodes"]) - 1)
    return int(len(scalp_positions))


def split(path: Path, calibrate: bool) -> str:
    document, binary = read_glb(path)
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    if int(extras.get("eloriaSurfacesSplit", 0)) >= 14:
        return "already split"
    if extras.get("eloriaSurfacesSplit"):
        # v2's scalp cloned the whole hair; rebuild it skull-only by
        # pointing the existing scalp mesh at freshly written accessors.
        for i, n in enumerate(document["nodes"]):
            if n.get("name") == "scalp" and "mesh" in n:
                scalp_mesh = n["mesh"]
                document["nodes"] = [m for m in document["nodes"]]
                count = add_scalp(document, binary)
                document["meshes"][scalp_mesh]["primitives"] =                     document["meshes"][-1]["primitives"]
                document["meshes"].pop()
                dangling = len(document["nodes"]) - 1
                for m in document["nodes"]:
                    if dangling in m.get("children", []):
                        m["children"].remove(dangling)
                document["nodes"].pop()
                break
        else:
            count = add_scalp(document, binary)
        extras["eloriaSurfacesSplit"] = 14
        write_glb(path, document, binary)
        return "scalp rebuilt (whole shell above the joint, -> v14)"
    mesh_node_index = next(i for i, n in enumerate(document["nodes"])
                           if "mesh" in n and "skin" in n)
    mesh_node = document["nodes"][mesh_node_index]
    prim = document["meshes"][mesh_node["mesh"]]["primitives"][0]
    positions = accessor_array(document, binary, prim["attributes"]["POSITION"])
    uvs = accessor_array(document, binary, prim["attributes"]["TEXCOORD_0"])
    indices = accessor_array(document, binary, prim["indices"]).reshape(-1).astype(np.uint32)
    image = document["images"][0]
    view = document["bufferViews"][image["bufferView"]]
    start = 8 + view.get("byteOffset", 0)
    texture = Image.open(io.BytesIO(bytes(binary[start:start + view["byteLength"]])))

    faces, labels = classify(positions, uvs, indices, texture)
    counts = {c: int((labels == c).sum()) for c in CLASSES}
    if calibrate:
        return "faces per class: %s" % counts

    grey_png = grayscale_texture(texture)
    grey_view = append_view(document, binary, grey_png)
    document["images"].append({"name": "wardrobe_grey",
                               "mimeType": "image/png",
                               "bufferView": grey_view})
    sampler = 0 if document.get("samplers") else None
    document.setdefault("textures", []).append(
        {"source": len(document["images"]) - 1}
        | ({"sampler": sampler} if sampler is not None else {}))
    grey_texture = len(document["textures"]) - 1
    original_material = prim.get("material", 0)
    wardrobe_material = {
        "name": "Wardrobe",
        "pbrMetallicRoughness": {
            "baseColorTexture": {"index": grey_texture},
            "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.9,
        },
    }
    document["materials"].append(wardrobe_material)
    wardrobe_index = len(document["materials"]) - 1
    plain_material = {
        "name": "WardrobePlain",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.9, 0.9, 0.9, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.9,
        },
    }
    document["materials"].append(plain_material)
    plain_index = len(document["materials"]) - 1

    parent = next(i for i, n in enumerate(document["nodes"])
                  if mesh_node_index in n.get("children", []))
    skin_index = mesh_node["skin"]
    scene_children = document["nodes"][parent]["children"]

    def add_mesh_node(name, primitive):
        document["meshes"].append({"name": name, "primitives": [primitive]})
        document["nodes"].append({"name": name,
                                  "mesh": len(document["meshes"]) - 1,
                                  "skin": skin_index})
        scene_children.append(len(document["nodes"]) - 1)

    for cls in CLASSES:
        member = labels == cls
        if not member.any():
            continue
        cls_indices = faces[member].reshape(-1).astype(np.uint32)
        acc = append_accessor(document, binary, cls_indices, 5125, "SCALAR",
                              34963)
        material = (wardrobe_index if cls.startswith("wardrobe_")
                    else original_material)
        add_mesh_node(cls, {"attributes": dict(prim["attributes"]),
                            "indices": acc, "material": material})

    # The head styles the runtime toggles: a plain band and cap, skinned
    # rigid to the Head joint so they ride (and scale) with it.
    joints = document["skins"][skin_index]["joints"]
    names = [document["nodes"][j].get("name", "") for j in joints]
    head_row = names.index("Head")
    for name, (verts, norms, uv, faces_extra) in (
            ("wardrobe_head_band", ring(0.104, 1.655, 1.685)),
            ("wardrobe_head_cap", dome(0.105, 1.665))):
        count = len(verts)
        pos_acc = append_accessor(document, binary,
                                  verts.astype(np.float32), 5126, "VEC3",
                                  34962)
        norm_acc = append_accessor(document, binary,
                                   norms.astype(np.float32), 5126, "VEC3",
                                   34962)
        uv_acc = append_accessor(document, binary, uv.astype(np.float32),
                                 5126, "VEC2", 34962)
        j = np.zeros((count, 4), dtype=np.uint16)
        j[:, 0] = head_row
        joints_acc = append_accessor(document, binary, j, 5123, "VEC4",
                                     34962)
        w = np.zeros((count, 4), dtype=np.float32)
        w[:, 0] = 1.0
        weights_acc = append_accessor(document, binary, w, 5126, "VEC4",
                                      34962)
        idx_acc = append_accessor(document, binary, faces_extra, 5125,
                                  "SCALAR", 34963)
        add_mesh_node(name, {"attributes": {
            "POSITION": pos_acc, "NORMAL": norm_acc, "TEXCOORD_0": uv_acc,
            "JOINTS_0": joints_acc, "WEIGHTS_0": weights_acc},
            "indices": idx_acc, "material": plain_index})

    del mesh_node["mesh"]
    add_scalp(document, binary)
    extras["eloriaSurfacesSplit"] = 14
    write_glb(path, document, binary)
    return "split: %s" % counts


def main() -> int:
    ap = argparse.ArgumentParser(description="split race body surfaces")
    ap.add_argument("--race", default=None)
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args()
    races = ([args.race] if args.race
             else ["luminous_male", "luminous_female"])
    for race in races:
        print("%-18s %s" % (race, split(RACES / (race + ".glb"),
                                        args.calibrate)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
