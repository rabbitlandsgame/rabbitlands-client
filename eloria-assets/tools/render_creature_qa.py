#!/usr/bin/env python3
"""Dependency-free multi-view QA renderer for creature GLBs.

Unlike ``render_native_glb_preview`` (a painter's-algorithm silhouette tool),
this renderer uses a real depth buffer, per-pixel interpolated normals and
optional base-colour texture sampling, so anatomy, self-occlusion and
material behaviour can be judged honestly against the concept art.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

COMPONENT_DTYPES = {5120: "int8", 5121: "uint8", 5122: "int16",
                    5123: "uint16", 5125: "uint32", 5126: "float32"}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

VIEWS = {
    "front":   (0.0, 0.0),
    "profile": (90.0, 0.0),
    "rear":    (180.0, 0.0),
    "3q_front": (35.0, 14.0),
    "3q_rear": (215.0, 14.0),
    "gameplay": (48.0, 34.0),
}


def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError(f"not a GLB: {path}")
    json_size, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A:
        raise ValueError(f"bad JSON chunk: {path}")
    document = json.loads(raw[20:20 + json_size])
    offset = 20 + json_size
    bin_size, bin_type = struct.unpack_from("<II", raw, offset)
    if bin_type != 0x004E4942:
        raise ValueError(f"no BIN chunk: {path}")
    return document, raw[offset + 8:offset + 8 + bin_size]


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


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=float).reshape(4, 4).T
    matrix = np.eye(4)
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        matrix[:3, :3] = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    if "scale" in node:
        matrix[:3, :3] = matrix[:3, :3] @ np.diag(node["scale"])
    if "translation" in node:
        matrix[:3, 3] = node["translation"]
    return matrix


def world_transforms(document: dict) -> dict[int, np.ndarray]:
    """Resolve every node's world matrix from the default scene."""
    result: dict[int, np.ndarray] = {}
    nodes = document.get("nodes", [])

    def walk(index: int, parent: np.ndarray) -> None:
        current = parent @ node_matrix(nodes[index])
        result[index] = current
        for child in nodes[index].get("children", []):
            walk(child, current)

    scene = document.get("scenes", [{}])[document.get("scene", 0)]
    for root in scene.get("nodes", range(len(nodes))):
        walk(root, np.eye(4))
    return result


def base_texture(document: dict, binary: bytes, material_index: int):
    """Return (texture, colour factor, alpha, emissive) for one material."""
    materials = document.get("materials", [])
    if material_index is None or material_index >= len(materials):
        return None, np.array([.7, .7, .7]), 1.0, np.zeros(3)
    material = materials[material_index]
    pbr = material.get("pbrMetallicRoughness", {})
    raw = pbr.get("baseColorFactor", [1, 1, 1, 1])
    factor = np.asarray(raw[:3], dtype=float)
    alpha = float(raw[3]) if len(raw) > 3 else 1.0
    if material.get("alphaMode") == "OPAQUE":
        alpha = 1.0
    emissive = np.asarray(material.get("emissiveFactor", [0, 0, 0]), dtype=float)
    reference = pbr.get("baseColorTexture", {}).get("index")
    if reference is None:
        return None, factor, alpha, emissive
    source = document["textures"][reference]["source"]
    spec = document["images"][source]
    if "bufferView" not in spec:
        return None, factor, alpha, emissive
    view = document["bufferViews"][spec["bufferView"]]
    start = view.get("byteOffset", 0)
    data = binary[start:start + view["byteLength"]]
    image = Image.open(io.BytesIO(data)).convert("RGB")
    return np.asarray(image, dtype=float) / 255.0, factor, alpha, emissive


def _quat_matrix(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _slerp(a, b, t):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if float(np.dot(a, b)) < 0:
        b = -b
    dot = float(np.clip(np.dot(a, b), -1, 1))
    if dot > .9995:
        out = a + (b - a) * t
    else:
        theta = math.acos(dot)
        out = (a * math.sin((1 - t) * theta) + b * math.sin(t * theta)) / math.sin(theta)
    return out / max(np.linalg.norm(out), 1e-9)


def sample_animation(document, binary, clip_name: str, time: float):
    """Return {node: {path: value}} for one clip sampled at ``time``."""
    pose: dict[int, dict[str, object]] = {}
    for animation in document.get("animations", []):
        if animation.get("name") != clip_name:
            continue
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            times = accessor(document, binary, sampler["input"]).astype(float).reshape(-1)
            values = accessor(document, binary, sampler["output"]).astype(float)
            path = channel["target"]["path"]
            node = channel["target"]["node"]
            if len(times) == 1:
                value = values[0]
            else:
                t = float(np.clip(time, times[0], times[-1]))
                index = int(np.searchsorted(times, t, side="right") - 1)
                index = max(0, min(index, len(times) - 2))
                span = max(times[index + 1] - times[index], 1e-9)
                frac = (t - times[index]) / span
                if path == "rotation":
                    value = _slerp(values[index], values[index + 1], frac)
                else:
                    value = values[index] * (1 - frac) + values[index + 1] * frac
            pose.setdefault(node, {})[path] = value
    return pose


def posed_world_transforms(document: dict, pose: dict) -> dict[int, np.ndarray]:
    nodes = document.get("nodes", [])
    result: dict[int, np.ndarray] = {}

    def local(index: int) -> np.ndarray:
        node = dict(nodes[index])
        override = pose.get(index, {})
        if "translation" in override:
            node["translation"] = list(override["translation"])
        if "rotation" in override:
            node["rotation"] = list(override["rotation"])
        if "scale" in override:
            node["scale"] = list(override["scale"])
        node.pop("matrix", None) if override else None
        return node_matrix(node)

    def walk(index: int, parent: np.ndarray) -> None:
        current = parent @ local(index)
        result[index] = current
        for child in nodes[index].get("children", []):
            walk(child, current)

    scene = document.get("scenes", [{}])[document.get("scene", 0)]
    for root in scene.get("nodes", range(len(nodes))):
        walk(root, np.eye(4))
    return result


def gather(document: dict, binary: bytes, clip: str | None = None, time: float = 0.0):
    """Collect world-space triangles with per-vertex normals and UVs."""
    pose = sample_animation(document, binary, clip, time) if clip else {}
    transforms = posed_world_transforms(document, pose) if pose else world_transforms(document)
    meshes = document.get("meshes", [])
    skin_matrices: dict[int, np.ndarray] = {}
    for skin_index, skin in enumerate(document.get("skins", [])):
        ibm = accessor(document, binary, skin["inverseBindMatrices"]).astype(float)
        ibm = ibm.reshape(-1, 4, 4).transpose(0, 2, 1)
        joints = skin["joints"]
        matrices = np.zeros((len(joints), 4, 4))
        for i, joint in enumerate(joints):
            matrices[i] = transforms.get(joint, np.eye(4)) @ ibm[i]
        skin_matrices[skin_index] = matrices
    batches = []
    for index, node in enumerate(document.get("nodes", [])):
        if "mesh" not in node:
            continue
        matrix = transforms.get(index, np.eye(4))
        # Skinned meshes are authored in skeleton space; the joint hierarchy
        # already carries the bind pose, so the node transform is identity.
        if "skin" in node:
            matrix = np.eye(4)
        normal_matrix = np.linalg.inv(matrix[:3, :3]).T
        for primitive in meshes[node["mesh"]].get("primitives", []):
            attributes = primitive["attributes"]
            positions = accessor(document, binary, attributes["POSITION"]).astype(float)
            normals = (accessor(document, binary, attributes["NORMAL"]).astype(float)
                       if "NORMAL" in attributes else np.zeros_like(positions))
            if "skin" in node and "JOINTS_0" in attributes and node["skin"] in skin_matrices:
                # Linear blend skinning, exactly as the runtime performs it.
                matrices = skin_matrices[node["skin"]]
                joints = accessor(document, binary, attributes["JOINTS_0"]).astype(int)
                weights = accessor(document, binary, attributes["WEIGHTS_0"]).astype(float)
                skinned = np.zeros_like(positions)
                skinned_n = np.zeros_like(normals)
                homogeneous = np.concatenate([positions, np.ones((len(positions), 1))], axis=1)
                for slot in range(joints.shape[1]):
                    weight = weights[:, slot:slot + 1]
                    if not weight.any():
                        continue
                    picked = matrices[np.clip(joints[:, slot], 0, len(matrices) - 1)]
                    skinned += weight * np.einsum("nij,nj->ni", picked, homogeneous)[:, :3]
                    skinned_n += weight * np.einsum("nij,nj->ni", picked[:, :3, :3], normals)
                positions, normals = skinned, skinned_n
            else:
                positions = positions @ matrix[:3, :3].T + matrix[:3, 3]
                normals = normals @ normal_matrix.T
            uvs = (accessor(document, binary, attributes["TEXCOORD_0"]).astype(float)
                   if "TEXCOORD_0" in attributes else np.zeros((len(positions), 2)))
            indices = accessor(document, binary, primitive["indices"]).astype(int).reshape(-1, 3)
            texture, factor, alpha, emissive = base_texture(
                document, binary, primitive.get("material"))
            batches.append((positions, normals, uvs, indices, texture, factor,
                            alpha, emissive))
    return batches


def render(batches, size: int, yaw_deg: float, pitch_deg: float,
           bounds: tuple[np.ndarray, np.ndarray]) -> Image.Image:
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    rot_y = np.array([[math.cos(yaw), 0, math.sin(yaw)],
                      [0, 1, 0],
                      [-math.sin(yaw), 0, math.cos(yaw)]])
    rot_x = np.array([[1, 0, 0],
                      [0, math.cos(pitch), -math.sin(pitch)],
                      [0, math.sin(pitch), math.cos(pitch)]])
    view = rot_x @ rot_y
    low, high = bounds
    centre = (low + high) * .5
    extent = max(float((high - low).max()), 1e-3)
    scale = (size - 2 * int(size * .09)) / extent
    margin = size * .5

    colour = np.zeros((size, size, 3), dtype=float)
    # Neutral studio backdrop with a soft vertical gradient.
    ramp = np.linspace(.30, .19, size)[:, None]
    colour[:] = np.dstack([ramp * .95, ramp * .99, ramp])[0][:, None, :].repeat(size, axis=1) \
        if False else np.stack([np.repeat(ramp, size, 1) * c for c in (.86, .90, .93)], axis=-1)
    depth = np.full((size, size), np.inf)

    key = np.array([.42, .78, .46]); key /= np.linalg.norm(key)
    rim = np.array([-.55, .28, -.72]); rim /= np.linalg.norm(rim)

    # Opaque first with depth writes, then blended surfaces back to front:
    # a translucent elemental has to be judged the way the runtime draws it.
    ordered = sorted(batches, key=lambda b: b[6] >= .995, reverse=True)
    for positions, normals, uvs, indices, texture, factor, alpha, emissive in ordered:
        view_positions = (positions - centre) @ view.T
        screen = np.empty_like(view_positions)
        screen[:, 0] = margin + view_positions[:, 0] * scale
        screen[:, 1] = margin - view_positions[:, 1] * scale
        screen[:, 2] = view_positions[:, 2]
        view_normals = normals @ view.T
        lengths = np.linalg.norm(view_normals, axis=1, keepdims=True)
        view_normals = view_normals / np.maximum(lengths, 1e-8)

        blended = alpha < .995
        if blended:
            depths = view_positions[indices].mean(axis=1)[:, 2]
            indices = indices[np.argsort(-depths)]
        for tri in indices:
            pts = screen[tri]
            min_x = max(int(np.floor(pts[:, 0].min())), 0)
            max_x = min(int(np.ceil(pts[:, 0].max())), size - 1)
            min_y = max(int(np.floor(pts[:, 1].min())), 0)
            max_y = min(int(np.ceil(pts[:, 1].max())), size - 1)
            if min_x > max_x or min_y > max_y:
                continue
            ax, ay = pts[0, 0], pts[0, 1]
            bx, by = pts[1, 0], pts[1, 1]
            cx, cy = pts[2, 0], pts[2, 1]
            area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
            if abs(area) < 1e-9:
                continue
            xs = np.arange(min_x, max_x + 1)
            ys = np.arange(min_y, max_y + 1)
            px, py = np.meshgrid(xs + .5, ys + .5)
            w0 = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
            w1 = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area
            w2 = 1.0 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            # Barycentric order: w2->a, w1->b, w0->c
            z = w2 * pts[0, 2] + w1 * pts[1, 2] + w0 * pts[2, 2]
            window = depth[min_y:max_y + 1, min_x:max_x + 1]
            visible = inside & (z < window)
            if not visible.any():
                continue
            normal = (w2[..., None] * view_normals[tri[0]]
                      + w1[..., None] * view_normals[tri[1]]
                      + w0[..., None] * view_normals[tri[2]])
            norm_len = np.linalg.norm(normal, axis=-1, keepdims=True)
            normal = normal / np.maximum(norm_len, 1e-8)
            # Two-sided shading keeps thin shells readable in QA.
            facing = np.sign(normal[..., 2:3])
            facing[facing == 0] = 1.0
            normal = normal * facing
            lambert = np.clip((normal * key).sum(-1), 0, 1)
            back = np.clip((normal * rim).sum(-1), 0, 1)
            shade = (.30 + .74 * lambert + .26 * back)[..., None]
            if texture is not None:
                uv = (w2[..., None] * uvs[tri[0]] + w1[..., None] * uvs[tri[1]]
                      + w0[..., None] * uvs[tri[2]])
                height, width = texture.shape[:2]
                tx = np.clip((uv[..., 0] % 1.0) * (width - 1), 0, width - 1).astype(int)
                ty = np.clip((1.0 - uv[..., 1] % 1.0) * (height - 1), 0, height - 1).astype(int)
                albedo = texture[ty, tx] * factor
            else:
                albedo = np.broadcast_to(factor, normal.shape).copy()
            shaded = np.clip(albedo * shade + emissive * .85, 0, 1)
            target = colour[min_y:max_y + 1, min_x:max_x + 1]
            if blended:
                target[visible] = (target[visible] * (1.0 - alpha)
                                   + shaded[visible] * alpha)
            else:
                target[visible] = shaded[visible]
                window[visible] = z[visible]

    return Image.fromarray((np.clip(colour, 0, 1) * 255).astype(np.uint8))


def model_bounds(batches) -> tuple[np.ndarray, np.ndarray]:
    stacked = np.concatenate([b[0] for b in batches])
    return stacked.min(axis=0), stacked.max(axis=0)


def sheet(path: Path, size: int, views: list[str], clip: str | None = None,
          times: list[float] | None = None) -> Image.Image:
    document, binary = read_glb(path)
    if clip:
        rest = model_bounds(gather(document, binary))
        panels = []
        for t in (times or [0.0]):
            panels.append((f"{clip} @{t:.2f}s", gather(document, binary, clip, t)))
        label_height = 26
        board = Image.new("RGB", (size * len(panels), size + label_height), (26, 30, 34))
        draw = ImageDraw.Draw(board)
        font = ImageFont.load_default(size=13)
        yaw, pitch = VIEWS[views[0]]
        for index, (name, batches) in enumerate(panels):
            board.paste(render(batches, size, yaw, pitch, rest), (index * size, 0))
            draw.text((index * size + 8, size + 6), name, fill=(206, 214, 220), font=font)
        return board
    batches = gather(document, binary)
    bounds = model_bounds(batches)
    label_height = 26
    board = Image.new("RGB", (size * len(views), size + label_height), (26, 30, 34))
    draw = ImageDraw.Draw(board)
    font = ImageFont.load_default(size=14)
    for index, name in enumerate(views):
        yaw, pitch = VIEWS[name]
        board.paste(render(batches, size, yaw, pitch, bounds), (index * size, 0))
        draw.text((index * size + 8, size + 6), name, fill=(206, 214, 220), font=font)
    draw.text((6, size + 6), "", font=font)
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", type=int, default=260)
    parser.add_argument("--views", default="profile,3q_front,front,rear")
    parser.add_argument("--clip", default=None,
                        help="render this animation clip instead of the bind pose")
    parser.add_argument("--times", default="",
                        help="comma separated sample times for --clip")
    args = parser.parse_args()
    views = [v.strip() for v in args.views.split(",") if v.strip() in VIEWS]
    sheets = []
    font = ImageFont.load_default(size=15)
    for path in args.models:
        times = [float(v) for v in args.times.split(",") if v.strip()] or None
        panel = sheet(path, args.size, views, args.clip, times)
        titled = Image.new("RGB", (panel.width, panel.height + 24), (18, 21, 24))
        titled.paste(panel, (0, 24))
        ImageDraw.Draw(titled).text((8, 5), path.stem.replace("_", " ").title(),
                                    fill=(235, 240, 244), font=font)
        sheets.append(titled)
    width = max(s.width for s in sheets)
    combined = Image.new("RGB", (width, sum(s.height for s in sheets)), (18, 21, 24))
    y = 0
    for s in sheets:
        combined.paste(s, (0, y))
        y += s.height
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.save(args.output, optimize=True)
    print(f"wrote {args.output} ({combined.width}x{combined.height})")


if __name__ == "__main__":
    main()
