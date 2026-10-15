#!/usr/bin/env python3
"""Render an instance-aware software QA sheet for Nymara region GLBs."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from render_native_glb_preview import accessor, material_color, read_glb


def transform_positions(values: np.ndarray, node: dict) -> np.ndarray:
    scale = np.asarray(node.get("scale", [1., 1., 1.]), dtype=np.float32)
    translation = np.asarray(node.get("translation", [0., 0., 0.]), dtype=np.float32)
    x, y, z, w = node.get("rotation", [0., 0., 0., 1.])
    rotation = np.asarray([
        [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w],
        [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
        [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]], dtype=np.float32)
    return (values * scale) @ rotation.T + translation


def render(path: Path, size: int = 520) -> Image.Image:
    document, binary = read_glb(path)
    triangles = []
    all_positions = []
    for node in document.get("nodes", []):
        mesh_index = node.get("mesh")
        if mesh_index is None:
            continue
        for primitive in document["meshes"][mesh_index].get("primitives", []):
            positions = transform_positions(
                accessor(document, binary, primitive["attributes"]["POSITION"]), node)
            indices = accessor(document, binary, primitive["indices"]).reshape(-1, 3)
            color = material_color(document, binary, primitive.get("material", 0))
            all_positions.append(positions)
            for face in indices:
                triangles.append((positions[face], color))
    positions = np.concatenate(all_positions)
    projected = np.column_stack((positions[:, 0] - positions[:, 2] * .62,
                                 positions[:, 1] + positions[:, 2] * .30))
    low, high = projected.min(axis=0), projected.max(axis=0)
    scale = (size - 42) / max(float((high - low).max()), .001)

    def point(value: np.ndarray) -> tuple[int, int]:
        px = value[0] - value[2] * .62
        py = value[1] + value[2] * .30
        return int(21 + (px - low[0]) * scale), int(size - 21 - (py - low[1]) * scale)

    canvas = Image.new("RGB", (size, size), (24, 31, 34))
    draw = ImageDraw.Draw(canvas)
    for step in range(0, size, 40):
        draw.line((step, 0, step, size), fill=(29, 38, 41))
        draw.line((0, step, size, step), fill=(29, 38, 41))
    triangles.sort(key=lambda entry: float((entry[0][:, 2] - entry[0][:, 1] * .3).mean()),
                   reverse=True)
    for face, color in triangles:
        normal = np.cross(face[1] - face[0], face[2] - face[0])
        length = np.linalg.norm(normal)
        light = .70 if length < 1e-8 else .54 + .46 * abs(float(normal[1] / length))
        fill = tuple(max(0, min(255, int(component * light))) for component in color)
        edge = tuple(max(0, int(component * .38)) for component in fill)
        draw.polygon([point(vertex) for vertex in face], fill=fill, outline=edge)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()
    columns = max(1, args.columns); rows = math.ceil(len(args.models) / columns)
    tile, label_height = 420, 34
    sheet = Image.new("RGB", (tile * columns, (tile + label_height) * rows), (18, 24, 26))
    draw = ImageDraw.Draw(sheet); font = ImageFont.load_default(size=16)
    for index, path in enumerate(args.models):
        x = index % columns * tile; y = index // columns * (tile + label_height)
        sheet.paste(render(path, tile), (x, y))
        label = path.parent.name.replace("_", " ").title()
        draw.text((x + 10, y + tile + 8), label, fill=(220, 226, 221), font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, optimize=True)


if __name__ == "__main__":
    main()
