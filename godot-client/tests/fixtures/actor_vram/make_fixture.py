#!/usr/bin/env python3
"""Regenerates the tiny actor tree the actor-sidecar tests plan (build_vram_textures.py --actor-dir).

    python godot-client/tests/fixtures/actor_vram/make_fixture.py

Writes, beside this script, a client-shaped tree (the tests point the tool's
ACTORS_ROOT at assets/actors and its RETIRED_INDEX at data/assets/...):

  assets/actors/native/
    creatures/wolf.glb              opaque base (JPEG), normal (PNG), ORM sampled
                                    as metallicRoughness and occlusion (JPEG)
    creatures/retired_beast.glb     one base image; retired (never planned)
    creatures/basic_expansion/fox.glb
                                    wolf's base bytes again (its own directory,
                                    its own index) and a MASK cutout (alphaCutoff
                                    0.45) whose PNG has real alpha
    races/human_male.glb            the shared atlas (JPEG) plus two DIFFERENT
                                    images of EQUAL byte length (PNG, level 0):
                                    an eye colour (base) and a normal map, so a
                                    reader that maps parse calls to images by
                                    byteLength must take them in image order
    races/human_female.glb          the same atlas bytes (one record, two GLBs)
    hair/short.glb                  one base (JPEG)
    hair/fitted/short_fitted.glb    the same bytes in a nested directory
    mounts/rat.glb                  a normal (PNG) whose BC5 error at mip 0
                                    (p99 3.2 deg) is over the map floor (3 deg)
                                    but within the plan's proposed actor floors
                                    (8 deg); a 62 px base (JPEG, not a
                                    multiple of 4); an image sampled as base in
                                    one material and as normal in another (PNG,
                                    role conflict); an image no material samples
    equipment/sword.glb             an embedded base (JPEG) and a URI image
                                    (textures/sword_engraving.png), which the
                                    tool leaves alone
    rl_heads/hair/rl_style.glb      an embedded base (rl_heads is never planned)
  data/assets/retired_procedural_models.json
                                    runtimePaths: creatures/retired_beast.glb
  fixture.json                      every image's key, sha256, size, kind and
                                    the GLBs that embed it, for the tests

Every GLB has one quad per material (POSITION, NORMAL, TEXCOORD_0, indices),
so it parses as a scene. Images are 64 px unless stated, made like
tests/fixtures/vram's, which pass the map floors. The folder holds a
.gdignore: the editor never imports it, and GDScript tests can still read
the GLBs with FileAccess/GLTFDocument. Needs numpy and Pillow. Outputs are
committed; re-running on another Pillow may change the JPEG bytes (and so
the shas), which fixture.json records.
"""
import hashlib
import io
import json
import os
import shutil
import struct

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.join(HERE, "assets", "actors", "native")
RNG = np.random.default_rng(20261103)


def smooth_noise(size, cells, channels):
    coarse = RNG.random((cells + 1, cells + 1, channels))
    image = Image.fromarray((coarse * 255).astype(np.uint8).squeeze())
    return np.asarray(image.resize((size, size), Image.BICUBIC)).astype(np.float64).reshape(size, size, channels)


def opaque_base(size, tint=(0.45, 0.35, 0.25)):
    y, x = np.mgrid[0:size, 0:size] / max(size - 1, 1)
    base = np.dstack([tint[0] + 0.35 * x, tint[1] + 0.3 * y, tint[2] + 0.2 * (1 - x)]) * 255
    return np.clip(base + (smooth_noise(size, 6, 3) - 128) * 0.35, 0, 255).astype(np.uint8)


def mask_base(size):
    rgb = opaque_base(size, (0.3, 0.45, 0.2))
    y, x = np.mgrid[0:size, 0:size] - (size - 1) / 2
    leaf = np.hypot(x * 1.4, y) < size * 0.38
    return np.dstack([rgb, np.where(leaf, 255, 0).astype(np.uint8)])


def normal_map(size, cells=5):
    height = smooth_noise(size, cells, 1)[..., 0] / 255.0
    gy, gx = np.gradient(height * 6.0)
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.clip((n * 0.5 + 0.5) * 255 + 0.5, 0, 255).astype(np.uint8)


def orm_map(size):
    occlusion = 200 + smooth_noise(size, 4, 1)[..., 0] * 0.2
    roughness = 120 + smooth_noise(size, 7, 1)[..., 0] * 0.5
    return np.clip(np.dstack([occlusion, roughness, np.zeros((size, size))]), 0, 255).astype(np.uint8)


def encode(array, kind, level=6):
    buffer = io.BytesIO()
    image = Image.fromarray(array)
    if kind == "jpg":
        image.save(buffer, "JPEG", quality=92, optimize=False, progressive=False)
    else:
        image.save(buffer, "PNG", optimize=False, compress_level=level)
    return buffer.getvalue()


def pad4(data, fill):
    return data + fill * ((4 - len(data) % 4) % 4)


QUAD = (struct.pack("<12f", -1, 0, -1, 1, 0, -1, 1, 0, 1, -1, 0, 1), struct.pack("<12f", *([0, 1, 0] * 4)),
        struct.pack("<8f", 0, 0, 1, 0, 1, 1, 0, 1), struct.pack("<6H", 0, 2, 1, 0, 3, 2))


def write_glb(relative, images, materials, generator="rabbitlands actor_vram fixture"):
    """images: [(key, bytes, mime) embedded | (key, uri) by URI], in glTF image order; materials name images by
    key in their texture slots (each image gets one texture of the same index)."""
    blob, views = b"", []
    for data, target in zip(QUAD, (34962, 34962, 34962, 34963)):
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob = pad4(blob + data, b"\0")
    gltf_images, index_of = [], {}
    for item in images:
        index_of[item[0]] = len(gltf_images)
        if len(item) == 2:
            gltf_images.append({"uri": item[1], "name": item[0]})
            continue
        key, data, mime = item
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        gltf_images.append({"bufferView": len(views) - 1, "mimeType": mime, "name": key})
        blob = pad4(blob + data, b"\0")

    def slots(value):
        if isinstance(value, dict):
            return {k: ({"index": index_of[v]} if k.endswith("Texture") and isinstance(v, str) else slots(v))
                    for k, v in value.items()}
        return value

    materials = [slots(material) for material in materials]
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-1, 0, -1], "max": [1, 0, 1]},
        {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC3"},
        {"bufferView": 2, "componentType": 5126, "count": 4, "type": "VEC2"},
        {"bufferView": 3, "componentType": 5123, "count": 6, "type": "SCALAR"},
    ]
    attributes = {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}
    meshes = [{"name": "Fixture_" + m["name"], "primitives": [{"attributes": attributes, "indices": 3, "material": i}]}
              for i, m in enumerate(materials)]
    nodes = [{"name": "Fixture_" + m["name"], "mesh": i, "translation": [i * 2.5, 0, 0]}
             for i, m in enumerate(materials)]
    document = {"asset": {"version": "2.0", "generator": generator}, "scene": 0,
                "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
                "materials": materials, "textures": [{"source": i} for i in range(len(gltf_images))],
                "images": gltf_images, "accessors": accessors, "bufferViews": views,
                "buffers": [{"byteLength": len(blob)}]}
    body = pad4(json.dumps(document, separators=(",", ":")).encode("utf-8"), b" ")
    glb = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(body) + 8 + len(blob))
    glb += struct.pack("<I4s", len(body), b"JSON") + body + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    path = os.path.join(NATIVE, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(glb)


def base(key):
    return {"name": key, "pbrMetallicRoughness": {"baseColorTexture": key}}


def main():
    for name in ("assets", "data"):
        shutil.rmtree(os.path.join(HERE, name), ignore_errors=True)
    images = {
        "wolf_base": (encode(opaque_base(64), "jpg"), "image/jpeg"),
        "wolf_normal": (encode(normal_map(64), "png"), "image/png"),
        "wolf_orm": (encode(orm_map(64), "jpg"), "image/jpeg"),
        "fox_cutout": (encode(mask_base(64), "png"), "image/png"),
        "retired_base": (encode(opaque_base(64, (0.2, 0.2, 0.5)), "png"), "image/png"),
        "race_atlas": (encode(opaque_base(64, (0.55, 0.4, 0.35)), "jpg"), "image/jpeg"),
        "race_eyes": (encode(opaque_base(64, (0.2, 0.35, 0.55)), "png", level=0), "image/png"),
        "race_normal": (encode(normal_map(64, 4), "png", level=0), "image/png"),
        "hair_base": (encode(opaque_base(64, (0.35, 0.25, 0.15)), "jpg"), "image/jpeg"),
        "mount_normal": (encode(normal_map(64, 6), "png"), "image/png"),
        "mount_odd": (encode(opaque_base(62, (0.4, 0.4, 0.3)), "jpg"), "image/jpeg"),
        "mount_conflict": (encode(opaque_base(64, (0.5, 0.3, 0.3))[::-1].copy(), "png"), "image/png"),
        "mount_unused": (encode(smooth_noise(64, 3, 1)[..., 0].astype(np.uint8), "png"), "image/png"),
        "sword_base": (encode(opaque_base(64, (0.5, 0.5, 0.55)), "jpg"), "image/jpeg"),
        "rl_base": (encode(opaque_base(64, (0.3, 0.2, 0.1)), "png"), "image/png"),
    }
    eyes, normal = images["race_eyes"][0], images["race_normal"][0]
    if len(eyes) != len(normal) or eyes == normal:
        raise SystemExit(f"race_eyes and race_normal must differ with one byte length: {len(eyes)} / {len(normal)}")
    uri_png = encode(opaque_base(64, (0.6, 0.6, 0.6)), "png")

    def embed(*keys):
        return [(key, *images[key]) for key in keys]

    glbs = {
        "creatures/wolf.glb": (embed("wolf_base", "wolf_normal", "wolf_orm"), [
            {"name": "wolf_body", "pbrMetallicRoughness": {"baseColorTexture": "wolf_base",
                                                           "metallicRoughnessTexture": "wolf_orm"},
             "normalTexture": "wolf_normal", "occlusionTexture": "wolf_orm"}]),
        "creatures/retired_beast.glb": (embed("retired_base"), [base("retired_base")]),
        "creatures/basic_expansion/fox.glb": (embed("wolf_base", "fox_cutout"), [
            base("wolf_base"),
            {"name": "fox_fur_cards", "alphaMode": "MASK", "alphaCutoff": 0.45,
             "pbrMetallicRoughness": {"baseColorTexture": "fox_cutout"}}]),
        "races/human_male.glb": (embed("race_atlas", "race_eyes", "race_normal"), [
            {"name": "body", "pbrMetallicRoughness": {"baseColorTexture": "race_atlas"},
             "normalTexture": "race_normal"},
            base("race_eyes")]),
        "races/human_female.glb": (embed("race_atlas"), [base("race_atlas")]),
        "hair/short.glb": (embed("hair_base"), [base("hair_base")]),
        "hair/fitted/short_fitted.glb": (embed("hair_base"), [base("hair_base")]),
        "mounts/rat.glb": (embed("mount_normal", "mount_odd", "mount_conflict", "mount_unused"), [
            {"name": "rat_body", "pbrMetallicRoughness": {"baseColorTexture": "mount_odd"},
             "normalTexture": "mount_normal"},
            base("mount_conflict"),
            {"name": "rat_conflict_normal", "pbrMetallicRoughness": {"baseColorTexture": "mount_odd"},
             "normalTexture": "mount_conflict"}]),
        "equipment/sword.glb": (embed("sword_base") + [("sword_engraving", "textures/sword_engraving.png")], [
            base("sword_base"), base("sword_engraving")]),
        "rl_heads/hair/rl_style.glb": (embed("rl_base"), [base("rl_base")]),
    }
    record = {"images": {}, "glbs": {}, "uriImages": {}}
    for relative, (embedded, materials) in glbs.items():
        write_glb(relative, embedded, materials)
        record["glbs"][relative] = [item[0] for item in embedded]
    uri = os.path.join(NATIVE, "equipment", "textures", "sword_engraving.png")
    os.makedirs(os.path.dirname(uri), exist_ok=True)
    with open(uri, "wb") as handle:
        handle.write(uri_png)
    record["uriImages"]["equipment/textures/sword_engraving.png"] = hashlib.sha256(uri_png).hexdigest()
    for key, (data, mime) in images.items():
        with Image.open(io.BytesIO(data)) as image:
            size = list(image.size)
        record["images"][key] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "mimeType": mime,
                                 "size": size}
    retired = os.path.join(HERE, "data", "assets", "retired_procedural_models.json")
    os.makedirs(os.path.dirname(retired), exist_ok=True)
    with open(retired, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"schemaVersion": 1, "status": "test fixture",
                   "runtimePaths": ["actors/native/creatures/retired_beast.glb"]}, handle, indent=1)
        handle.write("\n")
    with open(os.path.join(HERE, "fixture.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=1)
        handle.write("\n")
    print(json.dumps({key: value["sha256"][:12] for key, value in record["images"].items()}, indent=1))


if __name__ == "__main__":
    main()
