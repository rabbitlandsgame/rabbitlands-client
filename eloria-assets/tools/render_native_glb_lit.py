#!/usr/bin/env python3
"""Normal-mapped preview of generated native GLBs, for reviewing materials.

`render_native_glb_preview.py` averages every material down to one colour, so
it shows silhouette and topology and cannot show whether a normal map, a
roughness break or a metallic factor is doing anything at all.  That is the
right tool for checking a shape and the wrong one for checking a surface: the
race features shipped untextured for a whole release partly because nothing in
the QA surface could have shown it.

This renders the same GLBs with per-pixel shading -- albedo, normal and
metallic-roughness maps sampled, Cook-Torrance specular with the Smith
height-correlated visibility term, one key light, one fill and a hemisphere
ambient.  It is not the Godot renderer and is not trying to be; it is enough
to tell a surface that answers a light from one that does not.

Dependency-light on purpose: numpy and Pillow, the same as the rest of the
offline asset pipeline.

    python3 eloria-assets/tools/render_native_glb_lit.py \\
        godot-client/assets/actors/native/races/*.glb \\
        --output eloria-assets/qa/native-glb/races-lit.png --columns 4
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from build_native_nymara_glbs import COMPONENT_DTYPES, TYPE_WIDTHS

VIEW = np.array([0., 0., 1.])
KEY = np.array([-.45, .75, .95])
FILL = np.array([.80, .20, -.70])


def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = Path(path).read_bytes()
    size, kind = struct.unpack_from("<II", raw, 12)
    if raw[:4] != b"glTF" or kind != 0x4E4F534A:
        raise ValueError(f"not a GLB 2.0 file: {path}")
    document = json.loads(raw[20:20 + size])
    offset = 20 + size
    length, _ = struct.unpack_from("<II", raw, offset)
    return document, raw[offset + 8:offset + 8 + length]


def accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]])
    width = TYPE_WIDTHS[spec["type"]]
    offset = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=binary, offset=offset,
                      strides=strides).copy().astype(np.float64)


def texture_array(document: dict, binary: bytes, index: int, srgb: bool) -> np.ndarray:
    image = document["images"][document["textures"][index]["source"]]
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    decoded = Image.open(io.BytesIO(binary[start:start + view["byteLength"]]))
    array = np.asarray(decoded.convert("RGB")).astype(np.float32) / 255.
    return array ** 2.2 if srgb else array


def sample(texture: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    height, width = texture.shape[:2]
    x = np.clip((u % 1.) * width, 0, width - 1).astype(np.int32)
    y = np.clip((v % 1.) * height, 0, height - 1).astype(np.int32)
    return texture[y, x]


def render(path: Path, size: int = 512, yaw: float = 0.) -> Image.Image:
    document, binary = read_glb(path)
    materials = document.get("materials", [])
    cache: dict[int, dict] = {}

    def maps(index: int) -> dict:
        if index not in cache:
            material = materials[index]
            pbr = material.get("pbrMetallicRoughness", {})
            entry = {
                "color": np.asarray(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3],
                                    dtype=np.float32) ** 2.2,
                "metal": float(pbr.get("metallicFactor", 1.)),
                "rough": float(pbr.get("roughnessFactor", 1.)),
                "albedo": None, "normal": None, "mr": None,
            }
            if "baseColorTexture" in pbr:
                entry["albedo"] = texture_array(
                    document, binary, pbr["baseColorTexture"]["index"], True)
            if "metallicRoughnessTexture" in pbr:
                entry["mr"] = texture_array(
                    document, binary, pbr["metallicRoughnessTexture"]["index"], False)
            if "normalTexture" in material:
                entry["normal"] = texture_array(
                    document, binary, material["normalTexture"]["index"], False)
            cache[index] = entry
        return cache[index]

    points, normals, coords, owners = [], [], [], []
    for mesh in document.get("meshes", []):
        # Optional creation headwear is hidden for the zero-valued default,
        # matching the software contact sheets.
        if mesh.get("name", "").startswith("Wardrobe_Head_"):
            continue
        for primitive in mesh.get("primitives", []):
            attributes = primitive["attributes"]
            faces = accessor(document, binary,
                             primitive["indices"]).astype(np.int64).reshape(-1, 3)
            points.append(accessor(document, binary, attributes["POSITION"])[faces])
            normals.append(accessor(document, binary, attributes["NORMAL"])[faces])
            coords.append(accessor(document, binary, attributes["TEXCOORD_0"])[faces])
            owners.append(np.full(len(faces), primitive.get("material", 0), np.int32))
    points = np.concatenate(points)
    normals = np.concatenate(normals)
    coords = np.concatenate(coords)
    owners = np.concatenate(owners)

    cos, sin = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    spin = np.array([[cos, 0, sin], [0, 1, 0], [-sin, 0, cos]])
    points = points @ spin.T
    normals = normals @ spin.T

    low = points.reshape(-1, 3).min(axis=0)
    high = points.reshape(-1, 3).max(axis=0)
    span = max(high[0] - low[0], high[1] - low[1]) or 1.
    scale = (size - 40) / span
    middle = (low[0] + high[0]) * .5
    screen_x = (points[..., 0] - middle) * scale + size * .5
    screen_y = size - 20 - (points[..., 1] - low[1]) * scale
    depth = points[..., 2]

    colour = np.zeros((size, size, 3), np.float32)
    zbuffer = np.full((size, size), -1e9, np.float32)
    key = KEY / np.linalg.norm(KEY)
    fill = FILL / np.linalg.norm(FILL)

    for triangle in range(len(points)):
        xs, ys = screen_x[triangle], screen_y[triangle]
        min_x = max(int(np.floor(xs.min())), 0)
        max_x = min(int(np.ceil(xs.max())) + 1, size)
        min_y = max(int(np.floor(ys.min())), 0)
        max_y = min(int(np.ceil(ys.max())) + 1, size)
        if min_x >= max_x or min_y >= max_y:
            continue
        ax, ay = xs[0], ys[0]
        bx, by = xs[1], ys[1]
        cx, cy = xs[2], ys[2]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            continue
        px, py = np.meshgrid(np.arange(min_x, max_x) + .5,
                             np.arange(min_y, max_y) + .5)
        w0 = ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / area
        w1 = ((cx - bx) * (py - by) - (cy - by) * (px - bx)) / area
        w2 = 1. - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        la, lb, lc = w2, w1, w0
        z = la * depth[triangle, 0] + lb * depth[triangle, 1] + lc * depth[triangle, 2]
        window = zbuffer[min_y:max_y, min_x:max_x]
        winner = inside & (z > window)
        if not winner.any():
            continue
        material = maps(owners[triangle])
        u = (la * coords[triangle, 0, 0] + lb * coords[triangle, 1, 0]
             + lc * coords[triangle, 2, 0])
        v = (la * coords[triangle, 0, 1] + lb * coords[triangle, 1, 1]
             + lc * coords[triangle, 2, 1])
        shading = np.stack([
            la * normals[triangle, 0, axis] + lb * normals[triangle, 1, axis]
            + lc * normals[triangle, 2, axis] for axis in range(3)], axis=-1)
        shading /= np.maximum(np.linalg.norm(shading, axis=-1, keepdims=True), 1e-9)
        albedo = np.broadcast_to(material["color"], shading.shape).copy()
        if material["albedo"] is not None:
            albedo = albedo * sample(material["albedo"], u, v)
        rough = np.full(u.shape, material["rough"], np.float32)
        metal = np.full(u.shape, material["metal"], np.float32)
        if material["mr"] is not None:
            packed = sample(material["mr"], u, v)
            rough = rough * packed[..., 1]
            metal = metal * packed[..., 2]
        if material["normal"] is not None:
            edge_a = points[triangle, 1] - points[triangle, 0]
            edge_b = points[triangle, 2] - points[triangle, 0]
            du1 = coords[triangle, 1, 0] - coords[triangle, 0, 0]
            dv1 = coords[triangle, 1, 1] - coords[triangle, 0, 1]
            du2 = coords[triangle, 2, 0] - coords[triangle, 0, 0]
            dv2 = coords[triangle, 2, 1] - coords[triangle, 0, 1]
            determinant = du1 * dv2 - du2 * dv1
            if abs(determinant) > 1e-12:
                tangent = (edge_a * dv2 - edge_b * dv1) / determinant
                length = np.linalg.norm(tangent)
                if length > 1e-9:
                    tangent = tangent / length
                    tangent = tangent - shading * (shading @ tangent)[..., None]
                    tangent /= np.maximum(
                        np.linalg.norm(tangent, axis=-1, keepdims=True), 1e-9)
                    bitangent = np.cross(shading, tangent)
                    tangent_normal = sample(material["normal"], u, v) * 2. - 1.
                    shading = (tangent * tangent_normal[..., 0:1]
                               + bitangent * tangent_normal[..., 1:2]
                               + shading * tangent_normal[..., 2:3])
                    shading /= np.maximum(
                        np.linalg.norm(shading, axis=-1, keepdims=True), 1e-9)

        def lit(direction, strength, tint):
            n_dot_l = np.clip(shading @ direction, 0, 1)[..., None]
            n_dot_v = np.clip(shading @ VIEW, 1e-4, 1)[..., None]
            half = direction + VIEW
            half = half / np.linalg.norm(half)
            n_dot_h = np.clip(shading @ half, 0, 1)[..., None]
            v_dot_h = np.clip(float(VIEW @ half), 0, 1)
            alpha = np.clip(rough, .05, 1.)[..., None] ** 2
            alpha2 = alpha ** 2
            distribution = alpha2 / (math.pi * ((n_dot_h ** 2 * (alpha2 - 1.) + 1.) ** 2)
                                     + 1e-9)
            view_term = n_dot_l * np.sqrt(n_dot_v ** 2 * (1. - alpha2) + alpha2)
            light_term = n_dot_v * np.sqrt(n_dot_l ** 2 * (1. - alpha2) + alpha2)
            visibility = .5 / (view_term + light_term + 1e-6)
            f0 = .04 * (1. - metal[..., None]) + albedo * metal[..., None]
            fresnel = f0 + (1. - f0) * ((1. - v_dot_h) ** 5)
            diffuse = albedo * (1. - metal[..., None]) / math.pi
            return ((diffuse + distribution * visibility * fresnel)
                    * n_dot_l * strength * np.asarray(tint, np.float32))

        sky = np.clip(shading[..., 1:2] * .5 + .5, 0, 1)
        ambient = albedo * (np.array([.13, .15, .18], np.float32) * sky
                            + np.array([.06, .055, .05], np.float32) * (1 - sky))
        shaded = (lit(key, 3.1, (1., .97, .92)) + lit(fill, .85, (.62, .70, .88))
                  + ambient)
        target = colour[min_y:max_y, min_x:max_x]
        target[winner] = shaded[winner]
        window[winner] = z[winner]

    tonemapped = np.clip(colour / (colour + 1.), 0, 1) ** (1 / 2.2)
    lit_image = Image.fromarray((tonemapped * 255).astype(np.uint8))
    canvas = Image.new("RGB", (size, size), (26, 30, 34))
    canvas.paste(lit_image, (0, 0),
                 Image.fromarray(((zbuffer > -1e8) * 255).astype(np.uint8)))
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--size", type=int, default=460)
    parser.add_argument("--yaw", type=float, default=0.,
                        help="turn each model about its vertical axis, in degrees")
    args = parser.parse_args()
    columns = max(1, args.columns)
    rows = math.ceil(len(args.models) / columns)
    tile, label_height = args.size, 34
    sheet = Image.new("RGB", (tile * columns, (tile + label_height) * rows),
                      (23, 29, 31))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for index, path in enumerate(args.models):
        x = index % columns * tile
        y = index // columns * (tile + label_height)
        sheet.paste(render(path, tile, yaw=args.yaw), (x, y))
        draw.text((x + 10, y + tile + 8), path.stem.replace("_", " ").title(),
                  fill=(215, 224, 220), font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)


if __name__ == "__main__":
    main()
