#!/usr/bin/env python3
"""Regenerates the tiny map package the VRAM-texture tests load.

    python godot-client/tests/fixtures/vram/make_fixture.py

Writes, beside this script:
  world.glb, world.json        one map package whose images are external,
                               content-addressed files (no mimeType, as the
                               continent chunks write them), plus one embedded
                               bufferView image the client must leave alone
  shared-assets/<sha256>.<ext> the external images, 64 px unless stated:
      opaque base (JPEG), MASK base with real alpha (PNG), normal (PNG),
      ORM shared by metallicRoughness and occlusion (JPEG), a 62 px base
      (JPEG, not a multiple of 4), an image used as base colour in one
      material and as a normal map in another (PNG, a role conflict), and a
      data image no material samples (PNG)

  stale_roles.glb, .json        a second package over the same images whose
                               materials changed after the sidecars were made:
                               the opaque base is now a MASK cutout and the
                               ORM map is also sampled as base colour. It is
                               not named world.json, so the tool never sees it
                               (the index stays as the tool made it from
                               world.glb) and the client must refuse those two
                               sidecars for it. `--stale-roles` rewrites only
                               this package, from the committed world.glb.

The sidecars under shared-assets/vram/ are made by the real tool afterwards:

    python godot-client/tools/build_vram_textures.py \
        --maps godot-client/tests/fixtures/vram \
        --cache <a scratch directory> --no-prune

The folder holds a .gdignore so the editor never imports it; the tests read
it with FileAccess and GLTFDocument like any map package. Needs numpy and
Pillow. Outputs are committed; re-running on another Pillow may change the
JPEG bytes (and so every sha), which is fine as long as the sidecars are
rebuilt with it.
"""
import hashlib
import io
import json
import os
import struct

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(HERE, "shared-assets")
RNG = np.random.default_rng(20261002)


def smooth_noise(size, cells, channels):
    coarse = RNG.random((cells + 1, cells + 1, channels))
    image = Image.fromarray((coarse * 255).astype(np.uint8).squeeze())
    return np.asarray(image.resize((size, size), Image.BICUBIC)).astype(np.float64).reshape(size, size, channels)


def opaque_base(size):
    y, x = np.mgrid[0:size, 0:size] / max(size - 1, 1)
    base = np.dstack([0.45 + 0.35 * x, 0.35 + 0.3 * y, 0.25 + 0.2 * (1 - x)]) * 255
    return np.clip(base + (smooth_noise(size, 6, 3) - 128) * 0.35, 0, 255).astype(np.uint8)


def mask_base(size):
    rgb = opaque_base(size)
    y, x = np.mgrid[0:size, 0:size] - (size - 1) / 2
    leaf = np.hypot(x * 1.4, y) < size * 0.38
    alpha = np.where(leaf, 255, 0).astype(np.uint8)
    return np.dstack([rgb, alpha])


def normal_map(size):
    height = smooth_noise(size, 5, 1)[..., 0] / 255.0
    gy, gx = np.gradient(height * 6.0)
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.clip((n * 0.5 + 0.5) * 255 + 0.5, 0, 255).astype(np.uint8)


def orm_map(size):
    occlusion = 200 + smooth_noise(size, 4, 1)[..., 0] * 0.2
    roughness = 120 + smooth_noise(size, 7, 1)[..., 0] * 0.5
    metallic = np.zeros((size, size))
    return np.clip(np.dstack([occlusion, roughness, metallic]), 0, 255).astype(np.uint8)


def encode(array, kind):
    buffer = io.BytesIO()
    image = Image.fromarray(array)
    if kind == "jpg":
        image.save(buffer, "JPEG", quality=92, optimize=False, progressive=False)
    else:
        image.save(buffer, "PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def write_shared(array, kind):
    data = encode(array, kind)
    sha = hashlib.sha256(data).hexdigest()
    with open(os.path.join(SHARED, f"{sha}.{kind}"), "wb") as handle:
        handle.write(data)
    return f"shared-assets/{sha}.{kind}", sha


def pad4(data, fill):
    return data + fill * ((4 - len(data) % 4) % 4)


def main():
    os.makedirs(SHARED, exist_ok=True)
    for name in os.listdir(SHARED):
        if os.path.isfile(os.path.join(SHARED, name)):
            os.remove(os.path.join(SHARED, name))
    images = {
        "opaque_base": write_shared(opaque_base(64), "jpg"),
        "mask_base": write_shared(mask_base(64), "png"),
        "normal": write_shared(normal_map(64), "png"),
        "orm": write_shared(orm_map(64), "jpg"),
        "odd_base": write_shared(opaque_base(62), "jpg"),
        "conflict": write_shared(opaque_base(64)[::-1].copy(), "png"),
        "data": write_shared((smooth_noise(64, 3, 1)[..., 0]).astype(np.uint8), "png"),
    }
    embedded = encode(opaque_base(32)[:, ::-1].copy(), "png")

    # One quad, shared by every primitive: POSITION, TEXCOORD_0, NORMAL, indices.
    positions = struct.pack("<12f", -1, 0, -1, 1, 0, -1, 1, 0, 1, -1, 0, 1)
    normals = struct.pack("<12f", *([0, 1, 0] * 4))
    uvs = struct.pack("<8f", 0, 0, 1, 0, 1, 1, 0, 1)
    indices = struct.pack("<6H", 0, 2, 1, 0, 3, 2)
    blob = b""
    views = []
    for data, target in ((positions, 34962), (normals, 34962), (uvs, 34962), (indices, 34963)):
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob = pad4(blob + data, b"\0")
    views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(embedded)})
    blob = pad4(blob + embedded, b"\0")
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-1, 0, -1], "max": [1, 0, 1]},
        {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": 4, "type": "VEC2"},
        {"bufferView": 3, "componentType": 5123, "count": 6, "type": "SCALAR"},
    ]
    order = ["opaque_base", "mask_base", "normal", "orm", "odd_base", "conflict"]
    gltf_images = [{"uri": images[key][0], "name": key} for key in order]
    gltf_images.append({"bufferView": 4, "mimeType": "image/png", "name": "embedded"})
    textures = [{"source": index} for index in range(len(gltf_images))]
    tex = {key: {"index": index} for index, key in enumerate(order + ["embedded"])}
    materials = [
        {"name": "opaque", "pbrMetallicRoughness": {"baseColorTexture": tex["opaque_base"],
            "metallicRoughnessTexture": tex["orm"]}, "normalTexture": tex["normal"],
            "occlusionTexture": tex["orm"]},
        {"name": "cutout", "alphaMode": "MASK", "alphaCutoff": 0.5,
            "pbrMetallicRoughness": {"baseColorTexture": tex["mask_base"]}},
        {"name": "odd", "pbrMetallicRoughness": {"baseColorTexture": tex["odd_base"]}},
        {"name": "conflict_base", "pbrMetallicRoughness": {"baseColorTexture": tex["conflict"]}},
        {"name": "conflict_normal", "pbrMetallicRoughness": {"baseColorTexture": tex["opaque_base"]},
            "normalTexture": tex["conflict"]},
        {"name": "embedded", "pbrMetallicRoughness": {"baseColorTexture": tex["embedded"]}},
    ]
    attributes = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}
    meshes = [{"name": "Fixture_" + m["name"], "primitives": [
        {"attributes": attributes, "indices": 3, "material": index}]} for index, m in enumerate(materials)]
    nodes = [{"name": "Fixture_" + m["name"], "mesh": index, "translation": [index * 2.5, 0, 0]}
             for index, m in enumerate(materials)]
    document = {"asset": {"version": "2.0", "generator": "eloria vram fixture"},
                "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes,
                "meshes": meshes, "materials": materials, "textures": textures, "images": gltf_images,
                "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    body = pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    glb = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(body) + 8 + len(blob))
    glb += struct.pack("<I4s", len(body), b"JSON") + body + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    with open(os.path.join(HERE, "world.glb"), "wb") as handle:
        handle.write(glb)

    manifest = {
        "schemaVersion": "1.0.0",
        "asset": {"id": "vram_fixture", "name": "VRAM texture fixture", "glb": "world.glb",
                  "units": "meters", "origin": [0, 0, 0],
                  "coordinateSystem": {"upAxis": "Y", "northAxis": "-Z", "handedness": "right"},
                  "bounds": {"min": [-1, 0, -1], "max": [14, 0, 1]}},
        "coordinateTransform": {"metresPerTile": 1, "origin": [0, 0, 0], "walkingHeight": 0,
                                "invertServerY": True},
        "spawnPoints": [{"id": "default", "position": [0, 0, 0]}],
        "collision": {"nodeNames": []},
        "navigation": {"surfaceNodePrefixes": ["Terrain_"]},
        "externalResources": {uri: sha for uri, sha in images.values()},
    }
    with open(os.path.join(HERE, "world.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: value[1][:12] for key, value in images.items()}, indent=1))
    write_stale_roles()


def read_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + length].decode("utf-8"))
    blob_length = struct.unpack_from("<I", data, 20 + length)[0]
    return document, data[20 + length + 8:20 + length + 8 + blob_length]


def write_glb(path, document, blob):
    body = pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    glb = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(body) + 8 + len(blob))
    glb += struct.pack("<I4s", len(body), b"JSON") + body + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    with open(path, "wb") as handle:
        handle.write(glb)


def write_stale_roles():
    """world.glb's images and geometry, with materials a later content pass
    changed: the opaque base (image 0) is also a MASK cutout's base colour,
    and the ORM map (image 3) is also sampled as base colour."""
    document, blob = read_glb(os.path.join(HERE, "world.glb"))
    keep = [m for m in document["materials"] if m["name"] in ("opaque", "cutout")]
    keep.append({"name": "became_cutout", "alphaMode": "MASK", "alphaCutoff": 0.5,
                 "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}})
    keep.append({"name": "orm_as_colour", "pbrMetallicRoughness": {"baseColorTexture": {"index": 3}}})
    attributes = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}
    document["materials"] = keep
    document["meshes"] = [{"name": "Fixture_" + m["name"], "primitives": [
        {"attributes": attributes, "indices": 3, "material": index}]} for index, m in enumerate(keep)]
    document["nodes"] = [{"name": "Fixture_" + m["name"], "mesh": index, "translation": [index * 2.5, 0, 0]}
                         for index, m in enumerate(keep)]
    document["scenes"] = [{"nodes": list(range(len(keep)))}]
    write_glb(os.path.join(HERE, "stale_roles.glb"), document, blob)
    with open(os.path.join(HERE, "world.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["asset"]["id"] = "vram_fixture_stale_roles"
    manifest["asset"]["glb"] = "stale_roles.glb"
    with open(os.path.join(HERE, "stale_roles.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print("wrote stale_roles.glb / stale_roles.json")


if __name__ == "__main__":
    import sys
    if "--stale-roles" in sys.argv:
        write_stale_roles()
    else:
        main()
