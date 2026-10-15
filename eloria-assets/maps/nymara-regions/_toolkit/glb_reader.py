#!/usr/bin/env python3
"""Read a packaged map's geometry back out of its GLB.

The build scripts know where they put everything, but the tools that check a
finished package - and the ones that correct its walk grid afterwards - only
have the file. This reads nodes, their world transforms and their triangles,
and rasterises those onto the package's own half-metre collision grid, which
is the grid every other stage speaks in.

Used by `stamp_solid_landmarks.py` and `open_walk_surfaces.py`.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

import numpy as np

# glTF component types: (numpy letter, bytes)
COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
             5125: ("I", 4), 5126: ("f", 4)}
COLUMNS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
# How far up a face has to point to be ground rather than wall. The interiors
# builder uses the same number, so a surface reads the same either side.
UPWARD = 0.55
HEADER = struct.Struct("<4sHHII")


# A binary part a package keeps beside its .glb, named by its own SHA-256 so the
# .glb's JSON (and so its digest) pins the part's bytes. See `scene_io.dump_glb`.
PART_URI = re.compile(r"^[^/\\]+\.part[0-9]+\.([0-9a-f]{64})\.bin$")


def load(path: Path) -> tuple[dict, bytes]:
    """(the glTF document, the binary chunk) of a .glb.

    A region master too large for one file continues its binary in part files
    beside it; those are joined back on, so a reader always sees one buffer.
    """
    raw = path.read_bytes()
    json_length = struct.unpack_from("<II", raw, 12)[0]
    document = json.loads(raw[20:20 + json_length].decode("utf-8"))
    offset = 20 + json_length
    body = b""
    while offset + 8 <= len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        if kind == 0x004E4942:               # 'BIN\0'
            body = raw[offset + 8:offset + 8 + length]
            break
        offset += 8 + length
    if len(document.get("buffers", [])) > 1:
        return join_parts(path, document, body)
    return document, body


def join_parts(path: Path, document: dict, body: bytes) -> tuple[dict, bytes]:
    """One buffer from a .glb whose binary continues in content-addressed parts.

    Each part must match the SHA-256 its name carries and the length the
    document declares. Every buffer view is rebased onto the joined buffer,
    each part starting on a 4-byte boundary as the views inside it do.
    """
    buffers = document["buffers"]
    if "uri" in buffers[0]:
        raise ValueError(f"{path}: the first buffer must be the GLB's own binary chunk")
    joined = bytearray(body[:buffers[0].get("byteLength", len(body))])
    starts = [0]
    for index, buffer in enumerate(buffers[1:], 1):
        match = PART_URI.match(buffer.get("uri", ""))
        if not match:
            raise ValueError(f"{path}: buffer {index} is not a part file: {buffer.get('uri')!r}")
        data = (Path(path).parent / buffer["uri"]).read_bytes()
        if len(data) != buffer["byteLength"] or hashlib.sha256(data).hexdigest() != match.group(1):
            raise ValueError(f"{path}: {buffer['uri']} does not match its name and declared length")
        joined.extend(b"\0" * ((-len(joined)) % 4))
        starts.append(len(joined))
        joined.extend(data)
    for view in document["bufferViews"]:
        view["byteOffset"] = view.get("byteOffset", 0) + starts[view.get("buffer", 0)]
        view["buffer"] = 0
    document["buffers"] = [{"byteLength": len(joined)}]
    return document, bytes(joined)


def accessor(document: dict, body: bytes, index: int) -> np.ndarray:
    """One accessor as (count, columns), interleaving honoured."""
    acc = document["accessors"][index]
    letter, size = COMPONENT[acc["componentType"]]
    columns = COLUMNS[acc["type"]]
    view = document["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or size * columns
    count = acc["count"]
    if stride == size * columns:
        flat = np.frombuffer(body, dtype=np.dtype(letter), count=count * columns, offset=start)
        return flat.reshape(count, columns)
    rows = np.frombuffer(body, dtype=np.uint8, count=count * stride, offset=start).reshape(count, stride)
    return np.frombuffer(rows[:, :size * columns].tobytes(), dtype=np.dtype(letter)).reshape(count, columns)


def local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    translation = np.array(node.get("translation", [0.0, 0.0, 0.0]), dtype=float)
    scale = np.array(node.get("scale", [1.0, 1.0, 1.0]), dtype=float)
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    out = np.eye(4)
    out[:3, :3] = rotation * scale
    out[:3, 3] = translation
    return out


def hierarchy(document: dict) -> tuple[dict[int, np.ndarray], dict[int, int]]:
    """(world matrix per node, parent per node)."""
    nodes = document["nodes"]
    parents: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", ()):
            parents[child] = index
    matrices: dict[int, np.ndarray] = {}

    def resolve(index: int) -> np.ndarray:
        if index not in matrices:
            matrix = local_matrix(nodes[index])
            if index in parents:
                matrix = resolve(parents[index]) @ matrix
            matrices[index] = matrix
        return matrices[index]

    for index in range(len(nodes)):
        resolve(index)
    return matrices, parents


def named(document: dict, prefix: str) -> list[int]:
    """Every node that carries a mesh and has `prefix` somewhere in its ancestry."""
    nodes = document["nodes"]
    _, parents = hierarchy(document)
    out = []
    for index, node in enumerate(nodes):
        if node.get("mesh") is None:
            continue
        walk = index
        while True:
            if nodes[walk].get("name", "").startswith(prefix):
                out.append(index)
                break
            if walk not in parents:
                break
            walk = parents[walk]
    return out


def triangles(document: dict, body: bytes, indices) -> np.ndarray:
    """(n, 3, 3) of world-space triangles for the given mesh nodes."""
    matrices, _ = hierarchy(document)
    out = []
    for index in indices:
        matrix = matrices[index]
        for primitive in document["meshes"][document["nodes"][index]["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:
                continue
            points = accessor(document, body, primitive["attributes"]["POSITION"]).astype(np.float64)
            order = (accessor(document, body, primitive["indices"]).reshape(-1).astype(np.int64)
                     if "indices" in primitive else np.arange(len(points)))
            world = (matrix[:3, :3] @ points.T).T + matrix[:3, 3]
            out.append(world[order].reshape(-1, 3, 3))
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def rasterise(tri: np.ndarray, width: int, height: int, x0: float, z1: float,
              cell: float, *, upward: float = UPWARD) -> tuple[np.ndarray, np.ndarray]:
    """(covered, top) over cells centred on (x0 + (cx+.5)*cell, z1 - (cz+.5)*cell).

    Only faces pointing up count, and a cell takes the highest of them, which is
    what the client's downward ray finds.
    """
    covered = np.zeros((height, width), dtype=bool)
    top = np.full((height, width), -np.inf)
    if len(tri) == 0:
        return covered, top
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    keep = lengths > 1e-9
    tri, normals, lengths = tri[keep], normals[keep], lengths[keep]
    tri = tri[(normals[:, 1] / lengths) > upward]
    if len(tri) == 0:
        return covered, top
    cx0 = np.clip(np.floor((tri[:, :, 0].min(axis=1) - x0) / cell), 0, width - 1).astype(int)
    cx1 = np.clip(np.floor((tri[:, :, 0].max(axis=1) - x0) / cell), 0, width - 1).astype(int)
    cz0 = np.clip(np.floor((z1 - tri[:, :, 2].max(axis=1)) / cell), 0, height - 1).astype(int)
    cz1 = np.clip(np.floor((z1 - tri[:, :, 2].min(axis=1)) / cell), 0, height - 1).astype(int)
    for i in range(len(tri)):
        xs = np.arange(cx0[i], cx1[i] + 1)
        zs = np.arange(cz0[i], cz1[i] + 1)
        if xs.size == 0 or zs.size == 0:
            continue
        gx, gz = np.meshgrid(x0 + (xs + 0.5) * cell, z1 - (zs + 0.5) * cell)
        a, b, c = tri[i, 0], tri[i, 1], tri[i, 2]
        determinant = ((b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]))
        if abs(determinant) < 1e-12:
            continue
        w0 = ((b[2] - c[2]) * (gx - c[0]) + (c[0] - b[0]) * (gz - c[2])) / determinant
        w1 = ((c[2] - a[2]) * (gx - c[0]) + (a[0] - c[0]) * (gz - c[2])) / determinant
        inside = (w0 >= 0.0) & (w1 >= 0.0) & (w0 + w1 <= 1.0)
        if not inside.any():
            continue
        # The height *at* the cell, not the triangle's highest corner. A deck is
        # two triangles the length of the span, so taking the corner recorded a
        # sloping causeway as flat at its top end and put a four-metre step at
        # the bottom of it.
        surface = w0 * a[1] + w1 * b[1] + (1.0 - w0 - w1) * c[1]
        covered[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1] |= inside
        window = top[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1]
        np.copyto(window, surface, where=inside & (window < surface))
    return covered, top


def surface(package: Path, prefix: str, grid_shape, origin, cell: float):
    """(covered, top) for every mesh under a node named `prefix`, on the package grid."""
    document, body = load(package / "world.glb")
    tri = triangles(document, body, named(document, prefix))
    return rasterise(tri, grid_shape[1], grid_shape[0], float(origin[0]), float(origin[1]), cell)


# ------------------------------------------------------------------ the grid
def read_grid(package: Path) -> tuple[np.ndarray, dict]:
    """(the package's own half-metre collision grid, its manifest)."""
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    collision = manifest["collision"]
    raw = (package / collision["binary"]).read_bytes()
    _, _, _, width, height = HEADER.unpack_from(raw, 0)
    return np.frombuffer(raw, dtype=np.uint8, offset=HEADER.size).reshape(height, width), manifest


def grid_origin(manifest: dict) -> tuple[float, float]:
    """The metres at the top-left corner of cell (0, 0).

    A package that records `originMetres` says so; a region does not, and its
    grid starts at the corner of server tile (0, 0), which `serverOrigin` gives.
    """
    collision = manifest.get("collision") or {}
    recorded = collision.get("originMetres")
    if recorded:
        return float(recorded[0]), float(recorded[1])
    ox, oz = manifest["coordinateTransform"]["serverOrigin"]
    return -float(ox), float(oz)


def write_manifest(path: Path, manifest: dict) -> None:
    """Rewrite a manifest keeping its own indent and line endings."""
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    lines = text.splitlines()
    indent = (len(lines[1]) - len(lines[1].lstrip(" "))) if len(lines) > 1 else 2
    newline = "\r\n" if "\r\n" in text else "\n"
    path.write_text(json.dumps(manifest, indent=indent or 2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline=newline)


def write_grid(package: Path, manifest: dict, grid: np.ndarray) -> None:
    binary = package / manifest["collision"]["binary"]
    raw = bytearray(binary.read_bytes())
    magic, version, flags, width, height = HEADER.unpack_from(raw, 0)
    raw[HEADER.size:HEADER.size + width * height] = np.ascontiguousarray(grid, dtype=np.uint8).tobytes()
    binary.write_bytes(bytes(raw))
