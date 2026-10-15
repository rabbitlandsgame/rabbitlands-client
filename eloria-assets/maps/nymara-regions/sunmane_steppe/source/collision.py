#!/usr/bin/env python3
"""Write Sunmane Steppe's walk grid.

Every other Eloria map package ships a `collision.bin` beside its `world.glb`:
a half-metre grid whose zero bytes are the ground a player cannot stand on. The
steppe never got one, so the server generated its map walkable everywhere and
nothing stopped a player or a creature walking through the camps, into the sea,
or up the badlands.

The grid is the same EWCG version 2 the rest of the packages are moving to: the
map's own server grid at half a metre per cell, taken from `coordinateTransform`
rather than written out again, byte 0 meaning blocked and anything else an
elevation of `value * 0.2 - 2.2` metres.

    python eloria-assets/maps/nymara-regions/sunmane_steppe/source/collision.py [--out <collision.bin>]

Blocked is the union of three things: sea and beach, ground too steep to climb,
and the footprint of every node the manifest declares collision on - the carts,
pavilions and rocks the player can see. The footprints come out of the GLB the
package already ships, so this does not need the rest of the build to run.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import terrain  # noqa: E402

PACKAGE = HERE.parent
CELL_METRES = 0.5
# The steppe's map is 32 ELM tiles of six cells, and its manifest puts the
# origin at (58, 58) of that grid.
SERVER_CELLS = 192
# Sea, and the beach the sea washes over. `terrain.BEACH_LEVEL` is where the
# package itself stops calling the ground sand.
SHORE_CLEARANCE = 0.2
# Gradient a walker will not climb, in metres per metre. The same limit the
# Nymara region packages use, so the steppe reads like its neighbours.
MAX_SLOPE = 1.05
HEIGHT_STEP = 0.2
HEIGHT_ORIGIN = -2.2


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    _, _, length = struct.unpack_from("<III", data, 0)
    offset, gltf, buffer = 12, None, b""
    while offset < length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        body = data[offset + 8:offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A and gltf is None:
            gltf = json.loads(body)
        elif chunk_type == 0x004E4942 and not buffer:
            buffer = body
        offset += 8 + chunk_length + (-chunk_length % 4)
    if gltf is None:
        raise ValueError(f"no JSON chunk in {path}")
    return gltf, buffer


def node_matrix(node: dict) -> np.ndarray:
    """A node's local transform, from either a matrix or TRS."""
    if "matrix" in node:
        # glTF stores matrices column-major.
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    out = np.eye(4)
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        out[:3, :3] = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    if "scale" in node:
        out[:3, :3] = out[:3, :3] @ np.diag(node["scale"])
    if "translation" in node:
        out[:3, 3] = node["translation"]
    return out


def world_transforms(gltf: dict) -> dict[int, np.ndarray]:
    """Every node's world transform, walking down from the scene roots."""
    nodes = gltf["nodes"]
    scene = gltf["scenes"][gltf.get("scene", 0)]
    out: dict[int, np.ndarray] = {}
    stack = [(index, np.eye(4)) for index in scene.get("nodes", ())]
    while stack:
        index, parent = stack.pop()
        world = parent @ node_matrix(nodes[index])
        out[index] = world
        for child in nodes[index].get("children", ()):
            stack.append((child, world))
    return out


COMPONENT_DTYPES = {5120: "<i1", 5121: "<u1", 5122: "<i2",
                    5123: "<u2", 5125: "<u4", 5126: "<f4"}
COMPONENT_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_accessor(gltf: dict, buffer: bytes, index: int) -> np.ndarray:
    """One accessor's values, honouring its buffer view's stride."""
    accessor = gltf["accessors"][index]
    dtype = np.dtype(COMPONENT_DTYPES[accessor["componentType"]])
    columns = COMPONENT_COUNTS[accessor["type"]]
    count = accessor["count"]
    view = gltf["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or dtype.itemsize * columns
    if stride == dtype.itemsize * columns:
        flat = np.frombuffer(buffer, dtype=dtype, count=count * columns, offset=start)
        return flat.reshape(count, columns)
    raw = np.frombuffer(buffer, dtype=np.uint8,
                        count=stride * count, offset=start).reshape(count, stride)
    return raw[:, :dtype.itemsize * columns].copy().view(dtype).reshape(count, columns)


# Geometry this far above a node's seat is overhead, not an obstacle.
HEAD_ROOM = 2.1


def blocked_by_scenery(package: Path, gx: np.ndarray, gz: np.ndarray,
                       cell: float, landform=None) -> tuple[np.ndarray, int]:
    """Mark every cell the declared collision geometry actually covers.

    Not the bounding box. Half of what the steppe blocks is hollow - the
    palisade is a ring around the camp and the animal pens are fences - so a
    box around each one swallows the ground it encloses. Taking the triangles
    instead leaves the inside of a pen walkable and keeps its rails solid.
    """
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    if landform is None:
        import settlement
        landform=terrain.build(pads=settlement.compose_layout(None).pads())
    wanted = set(manifest.get("collision", {}).get("nodeNames", ()))
    mask = np.zeros(gx.shape, dtype=bool)
    if not wanted:
        return mask, 0
    gltf, buffer = read_glb(package / "world.glb")
    transforms = world_transforms(gltf)
    origin_x, origin_z = gx[0, 0], gz[0, 0]
    rows, columns = gx.shape
    nodes = 0
    for index, node in enumerate(gltf["nodes"]):
        if node.get("name") not in wanted or "mesh" not in node:
            continue
        world = transforms.get(index)
        if world is None:
            continue
        nodes += 1
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:
                continue
            points = read_accessor(gltf, buffer, primitive["attributes"]["POSITION"])
            placed = (world[:3, :3] @ points.T).T + world[:3, 3]
            if "indices" in primitive:
                order = read_accessor(gltf, buffer, primitive["indices"]).ravel()
            else:
                order = np.arange(len(placed))
            triangles = placed[order[:len(order) - len(order) % 3]].reshape(-1, 3, 3)
            # Only what a walker can run into. A gate's lintel, a canopy, a
            # tree's crown all cast a shadow on the ground plane, and stamping
            # those sealed every palisade gate: the opening was open, and the
            # beam above it was not.
            centre=triangles.mean(axis=1)
            base=landform.sample(centre[:,0],centre[:,2])
            triangles=triangles[triangles[:,:,1].min(axis=1)<base+HEAD_ROOM]
            if not len(triangles):
                continue
            _stamp(mask, triangles, origin_x, origin_z, cell, rows, columns)
    return mask, nodes


def _stamp(mask: np.ndarray, triangles: np.ndarray, origin_x: float,
           origin_z: float, cell: float, rows: int, columns: int) -> None:
    """Mark the cells each triangle's x/z shadow falls on.

    The outline is walked as well as the inside filled: a palisade stake is
    thinner than half a metre, and testing cell centres alone would let a
    walker through the gaps between them.
    """
    for triangle in triangles:
        xs, zs = triangle[:, 0], triangle[:, 2]
        # z decreases as the row index rises, so the row of a point is
        # (origin_z - z) / cell.
        low_col = int(np.floor((xs.min() - origin_x) / cell))
        high_col = int(np.ceil((xs.max() - origin_x) / cell))
        low_row = int(np.floor((origin_z - zs.max()) / cell))
        high_row = int(np.ceil((origin_z - zs.min()) / cell))
        low_col, high_col = max(0, low_col), min(columns - 1, high_col)
        low_row, high_row = max(0, low_row), min(rows - 1, high_row)
        if low_col > high_col or low_row > high_row:
            continue
        cols = np.arange(low_col, high_col + 1)
        rws = np.arange(low_row, high_row + 1)
        px = origin_x + cols * cell
        pz = origin_z - rws * cell
        mesh_x, mesh_z = np.meshgrid(px, pz)
        # Barycentric sign test against the triangle's x/z projection.
        x0, z0, x1, z1, x2, z2 = xs[0], zs[0], xs[1], zs[1], xs[2], zs[2]
        area = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2)
        if abs(area) > 1e-9:
            a = ((z1 - z2) * (mesh_x - x2) + (x2 - x1) * (mesh_z - z2)) / area
            b = ((z2 - z0) * (mesh_x - x2) + (x0 - x2) * (mesh_z - z2)) / area
            inside = (a >= 0) & (b >= 0) & (a + b <= 1)
            mask[low_row:high_row + 1, low_col:high_col + 1] |= inside
        for start, end in ((0, 1), (1, 2), (2, 0)):
            length = float(np.hypot(xs[end] - xs[start], zs[end] - zs[start]))
            steps = max(2, int(length / (cell * 0.5)) + 1)
            walk = np.linspace(0.0, 1.0, steps)
            ex = xs[start] + (xs[end] - xs[start]) * walk
            ez = zs[start] + (zs[end] - zs[start]) * walk
            ec = np.clip(np.round((ex - origin_x) / cell).astype(int), 0, columns - 1)
            er = np.clip(np.round((origin_z - ez) / cell).astype(int), 0, rows - 1)
            mask[er, ec] = True


def build_grid(package: Path) -> tuple[bytes, dict]:
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    transform = manifest["coordinateTransform"]
    origin_x, origin_y = transform["serverOrigin"]
    metres_per_tile = transform["metresPerTile"]
    size = int(round(SERVER_CELLS * metres_per_tile / CELL_METRES))

    tiles = (np.arange(size) + 0.5) * CELL_METRES / metres_per_tile
    xs = (tiles - origin_x) * metres_per_tile
    # invertServerY: the server's y runs north to south, so row 0 is the +Z edge.
    zs = (origin_y - tiles) * metres_per_tile
    gx, gz = np.meshgrid(xs, zs, indexing="xy")

    import settlement
    landform = terrain.build(pads=settlement.compose_layout(None).pads())
    heights = landform.sample(gx.ravel(), gz.ravel()).reshape(gx.shape)

    gradient_z, gradient_x = np.gradient(heights, CELL_METRES)
    slope = np.hypot(gradient_x, gradient_z)
    walkable = (heights > terrain.BEACH_LEVEL + SHORE_CLEARANCE) & (slope < MAX_SLOPE)
    # Water is blocked; the explicit Walk_ decks reopen only their own span.
    import layout as DESIGN
    for x,z,r,level in DESIGN.POOLS:
        walkable &= ~((np.hypot(gx-x,gz-z)<r*1.3)&(heights<level+.08))
    walkable &= ~(terrain._polyline_distance(gx,gz,[(x,z) for x,_,z in DESIGN.STREAM])<1.4)

    scenery, nodes = blocked_by_scenery(package, gx, gz, CELL_METRES, landform)
    walkable &= ~scenery

    encoded = np.clip(np.round((heights - HEIGHT_ORIGIN) / HEIGHT_STEP), 1, 255)
    payload = np.where(walkable, encoded, 0).astype(np.uint8)
    header = struct.pack("<4sHHII", b"EWCG", 2, 0, size, size)
    stats = {
        "cells": size, "cellMetres": CELL_METRES,
        "walkableCells": int(walkable.sum()),
        "walkableFraction": round(float(walkable.mean()), 4),
        "blockedByScenery": int(scenery.sum()),
        "collisionNodes": nodes,
        # Where the grid starts, in world metres: the western edge of column 0
        # and the northern edge of row 0, which is the pair every other region
        # publishes and the client's own check indexes with -
        # column = floor((x - x0) / cell), row = floor((z1 - z) / cell).
        # Without it a reader has to infer the mapping from `serverOrigin` and
        # guess whether the row order is inverted, and the client check skips
        # the package rather than guess.
        "originMetres": [round(-origin_x * metres_per_tile, 4),
                         round(origin_y * metres_per_tile, 4)],
        "heightEncoding": {"origin": HEIGHT_ORIGIN, "step": HEIGHT_STEP,
                           "range": [1, 255], "zeroMeansBlocked": True},
    }
    return header + payload.tobytes(), stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default=str(PACKAGE))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    package = Path(args.package)
    payload, stats = build_grid(package)
    out = Path(args.out) if args.out else package / "collision.bin"
    out.write_bytes(payload)
    print(f"[collision] {out} {len(payload)} bytes, "
          f"{stats['cells']}x{stats['cells']} cells at {stats['cellMetres']} m, "
          f"{stats['walkableFraction'] * 100:.1f}% walkable, "
          f"{stats['collisionNodes']} scenery nodes blocking "
          f"{stats['blockedByScenery']} cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
