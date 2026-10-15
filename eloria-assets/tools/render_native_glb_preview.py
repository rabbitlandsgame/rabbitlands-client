#!/usr/bin/env python3
"""Render dependency-free contact sheets for generated native GLB assets."""
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


def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    json_size, json_type = struct.unpack_from("<II", raw, 12)
    if raw[:4] != b"glTF" or json_type != 0x4E4F534A:
        raise ValueError(f"not a GLB 2.0 file: {path}")
    document = json.loads(raw[20:20 + json_size])
    binary_offset = 20 + json_size
    binary_size, binary_type = struct.unpack_from("<II", raw, binary_offset)
    if binary_type != 0x004E4942:
        raise ValueError(f"GLB has no binary chunk: {path}")
    return document, raw[binary_offset + 8:binary_offset + 8 + binary_size]


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
                      strides=strides).copy()


def material_color(document: dict, binary: bytes, index: int) -> tuple[int, int, int]:
    material = document.get("materials", [])[index]
    pbr = material.get("pbrMetallicRoughness", {})
    texture = pbr.get("baseColorTexture", {}).get("index")
    if texture is not None:
        image_index = document["textures"][texture]["source"]
        image_spec = document["images"][image_index]
        view = document["bufferViews"][image_spec["bufferView"]]
        start = view.get("byteOffset", 0)
        sample = Image.open(io.BytesIO(binary[start:start + view["byteLength"]])).convert("RGB")
        colors = np.asarray(sample.resize((32, 32))).reshape(-1, 3)
        sampled = np.quantile(colors, .62, axis=0)
        factor = np.asarray(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3])
        return tuple(int(value) for value in np.clip(sampled * factor, 0, 255))
    factor = pbr.get("baseColorFactor", [.68, .72, .72, 1])
    return tuple(int(255 * value) for value in factor[:3])


def render(path: Path, size: int = 480, *, wireframe: bool = True,
           yaw: float = 0.) -> Image.Image:
    """Draw one model.  ``yaw`` turns it about its own vertical axis, in
    degrees, which is the only way to review anatomy that lives in profile --
    a digitigrade leg, a tail, or the depth of a chest all vanish head-on."""
    document, binary = read_glb(path)
    turn = math.radians(yaw)
    spin_cos, spin_sin = math.cos(turn), math.sin(turn)

    def spin(values: np.ndarray) -> np.ndarray:
        x = values[..., 0] * spin_cos - values[..., 2] * spin_sin
        z = values[..., 0] * spin_sin + values[..., 2] * spin_cos
        return np.stack((x, values[..., 1], z), axis=-1)

    triangles = []
    all_positions = []
    for mesh in document.get("meshes", []):
        # Optional creation headwear is hidden for the zero-valued default.
        if mesh.get("name", "").startswith("Wardrobe_Head_"):
            continue
        for primitive in mesh.get("primitives", []):
            positions = spin(accessor(document, binary,
                                      primitive["attributes"]["POSITION"]))
            indices = accessor(document, binary, primitive["indices"]).reshape(-1, 3)
            color = material_color(document, binary, primitive.get("material", 0))
            all_positions.append(positions)
            for face in indices:
                triangles.append((positions[face], color))
    positions = np.concatenate(all_positions)
    # Three-quarter view with Y up; the generated creatures face camera-left.
    projected = np.column_stack((positions[:, 0] - positions[:, 2] * .42,
                                 positions[:, 1] + positions[:, 2] * .10))
    low, high = projected.min(axis=0), projected.max(axis=0)
    scale = (size - 44) / max(float((high - low).max()), .001)

    def point(value: np.ndarray) -> tuple[int, int]:
        x = value[0] - value[2] * .42
        y = value[1] + value[2] * .10
        return int(22 + (x - low[0]) * scale), int(size - 22 - (y - low[1]) * scale)

    canvas = Image.new("RGB", (size, size), (31, 39, 42))
    draw = ImageDraw.Draw(canvas)
    for step in range(0, size, 32):
        draw.line((step, 0, step, size), fill=(35, 45, 48))
        draw.line((0, step, size, step), fill=(35, 45, 48))
    # Source humanoids face +Z. Draw lower-depth triangles first so the final
    # software preview shows the face and concept features, not the back.
    triangles.sort(key=lambda entry: float(entry[0][:, 2].mean()))
    for face, color in triangles:
        points = [point(vertex) for vertex in face]
        normal = np.cross(face[1] - face[0], face[2] - face[0])
        length = np.linalg.norm(normal)
        light = .72 if length < 1e-8 else .62 + .38 * abs(float(normal[1] / length))
        fill = tuple(max(0, min(255, int(component * light))) for component in color)
        edge = tuple(max(0, int(component * .42)) for component in fill)
        draw.polygon(points, fill=fill, outline=edge if wireframe else None)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--solid", action="store_true",
                        help="omit topology edges for a material/silhouette review")
    parser.add_argument("--yaw", type=float, default=0.,
                        help="turn each model about its vertical axis, in degrees")
    args = parser.parse_args()
    columns = max(1, args.columns)
    rows = math.ceil(len(args.models) / columns)
    tile, label_height = 360, 34
    sheet = Image.new("RGB", (tile * columns, (tile + label_height) * rows), (23, 29, 31))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for index, path in enumerate(args.models):
        x = index % columns * tile
        y = index // columns * (tile + label_height)
        sheet.paste(render(path, tile, wireframe=not args.solid, yaw=args.yaw),
                    (x, y))
        label = path.stem.replace("_", " ").title()
        draw.text((x + 10, y + tile + 8), label, fill=(215, 224, 220), font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)


if __name__ == "__main__":
    main()
