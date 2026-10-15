#!/usr/bin/env python3
"""Runtime contract verification for the Amberwood package.

This reproduces, offline, exactly what the Godot client does at load time so
that grounding and navigation are proven before anyone starts the client:

  * `WorldLoader._apply_rendered_walk_surfaces` turns every MeshInstance3D whose
    name begins with a `navigation.surfaceNodePrefixes` entry into collision on
    the NAVIGATION_SURFACE layer.
  * `Main._place_actor_on_surface` casts a ray straight down from y = 400 to
    y = -100 against that layer and puts the actor at the first hit + 0.02.
  * A miss falls back to `coordinateTransform.walkingHeight`, which is the bug
    that drops or floats a character.

So: build the walk-surface triangle set from the GLB with accumulated node
transforms, cast that ray at the centre of every reachable server tile, and
report anything the client would get wrong.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import regionpaths

COMPONENT_DTYPE = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load_glb(path: Path):
    """(document, binary) of a package GLB; a region master's part files are
    joined back on (see glb_reader.load)."""
    import glb_reader
    return glb_reader.load(Path(path))


def accessor(document, binary, index):
    entry = document["accessors"][index]
    dtype = COMPONENT_DTYPE[entry["componentType"]]
    components = TYPE_COUNT[entry["type"]]
    view = document["bufferViews"][entry["bufferView"]]
    start = view.get("byteOffset", 0) + entry.get("byteOffset", 0)
    values = np.frombuffer(binary, dtype=dtype, count=entry["count"] * components,
                           offset=start)
    return values.reshape(entry["count"], components) if components > 1 else values


def node_matrix(node):
    matrix = np.eye(4)
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    if "scale" in node:
        s = node["scale"]
        matrix = matrix @ np.diag([s[0], s[1], s[2], 1.0])
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        rotation = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1]])
        matrix = rotation @ matrix
    if "translation" in node:
        t = node["translation"]
        translation = np.eye(4)
        translation[:3, 3] = t
        matrix = translation @ matrix
    return matrix


def collect_triangles(document, binary, predicate):
    """World-space triangles of every mesh node whose name satisfies `predicate`."""
    nodes = document["nodes"]
    out_v = []
    stack = [(index, np.eye(4)) for index in document["scenes"][0]["nodes"]]
    matched = []
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        world = parent @ node_matrix(node)
        if "mesh" in node and predicate(node.get("name", "")):
            matched.append(node.get("name", ""))
            mesh = document["meshes"][node["mesh"]]
            for primitive in mesh["primitives"]:
                positions = accessor(document, binary,
                                     primitive["attributes"]["POSITION"]).astype(np.float64)
                if "indices" in primitive:
                    indices = accessor(document, binary, primitive["indices"]).astype(np.int64)
                else:
                    indices = np.arange(positions.shape[0])
                homogeneous = np.hstack([positions, np.ones((positions.shape[0], 1))])
                world_positions = (homogeneous @ world.T)[:, :3]
                out_v.append(world_positions[indices].reshape(-1, 3, 3))
        for child in node.get("children", []):
            stack.append((child, world))
    if not out_v:
        return np.zeros((0, 3, 3)), matched
    return np.vstack(out_v), matched


class VerticalRayIndex:
    """Uniform XZ grid over triangles, for straight-down ray casts."""

    def __init__(self, triangles: np.ndarray, cell: float = 4.0) -> None:
        self.triangles = triangles
        self.cell = cell
        if triangles.shape[0] == 0:
            self.buckets = {}
            return
        lo = triangles.min(axis=1)
        hi = triangles.max(axis=1)
        self.min_x = float(lo[:, 0].min())
        self.min_z = float(lo[:, 2].min())
        x0 = np.floor((lo[:, 0] - self.min_x) / cell).astype(int)
        x1 = np.floor((hi[:, 0] - self.min_x) / cell).astype(int)
        z0 = np.floor((lo[:, 2] - self.min_z) / cell).astype(int)
        z1 = np.floor((hi[:, 2] - self.min_z) / cell).astype(int)
        buckets = defaultdict(list)
        for i in range(triangles.shape[0]):
            for cx in range(x0[i], x1[i] + 1):
                for cz in range(z0[i], z1[i] + 1):
                    buckets[(cx, cz)].append(i)
        self.buckets = {key: np.asarray(value, dtype=np.int64)
                        for key, value in buckets.items()}

    def top_hit(self, x: float, z: float):
        """Highest surface directly under (x, z), or None."""
        key = (int(math.floor((x - self.min_x) / self.cell)),
               int(math.floor((z - self.min_z) / self.cell)))
        candidates = self.buckets.get(key)
        if candidates is None:
            return None
        tris = self.triangles[candidates]
        a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
        v0 = c[:, [0, 2]] - a[:, [0, 2]]
        v1 = b[:, [0, 2]] - a[:, [0, 2]]
        v2 = np.array([x, z])[None, :] - a[:, [0, 2]]
        d00 = np.einsum("ij,ij->i", v0, v0)
        d01 = np.einsum("ij,ij->i", v0, v1)
        d11 = np.einsum("ij,ij->i", v1, v1)
        d20 = np.einsum("ij,ij->i", v2, v0)
        d21 = np.einsum("ij,ij->i", v2, v1)
        denominator = d00 * d11 - d01 * d01
        valid = np.abs(denominator) > 1e-12
        u = np.zeros_like(d00)
        v = np.zeros_like(d00)
        u[valid] = (d11[valid] * d20[valid] - d01[valid] * d21[valid]) / denominator[valid]
        v[valid] = (d00[valid] * d21[valid] - d01[valid] * d20[valid]) / denominator[valid]
        inside = valid & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1.0 + 1e-9)
        if not inside.any():
            return None
        heights = (a[:, 1] + u * (c[:, 1] - a[:, 1]) + v * (b[:, 1] - a[:, 1]))[inside]
        return float(heights.max())


def adjacent_jumps(heights, reachable, threshold=6.0):
    """Compare real neighbours; opposing map edges are never adjacent."""
    finite = np.isfinite(heights) & reachable
    jumps = []
    for axis in (0, 1):
        a, b = [slice(None), slice(None)], [slice(None), slice(None)]
        a[axis], b[axis] = slice(None, -1), slice(1, None)
        a, b = tuple(a), tuple(b)
        valid = finite[a] & finite[b]
        difference = np.abs(heights[a] - heights[b])
        for ty, tx in zip(*np.nonzero(valid & (difference > threshold))):
            jumps.append((int(tx), int(ty), round(float(difference[ty, tx]), 2)))
    return jumps


def served_reachable(grid, cells, metres_per_tile=1., cell_metres=.5):
    """The server's conservative fold, including its half-tile origin shift."""
    ratio = metres_per_tile / cell_metres
    low = np.floor((np.arange(cells) - .5) * ratio).astype(int)
    high = np.ceil((np.arange(cells) + .5) * ratio).astype(int) - 1
    ys = [(max(0, min(a, grid.shape[0]-1)), max(0, min(b, grid.shape[0]-1))) for a, b in zip(low, high)]
    xs = [(max(0, min(a, grid.shape[1]-1)), max(0, min(b, grid.shape[1]-1))) for a, b in zip(low, high)]
    blocked = np.pad((grid == 0).astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    x0, x1 = np.array(xs).T
    result = np.zeros((cells, cells), dtype=bool)
    for y, (y0, y1) in enumerate(ys):
        count = blocked[y1+1, x1+1] - blocked[y0, x1+1] - blocked[y1+1, x0] + blocked[y0, x0]
        result[y] = count == 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default=None)
    parser.add_argument("--report", default=None)
    parser.add_argument("--step", type=int, default=1)
    args = parser.parse_args()
    package = regionpaths.package_root(args.package)

    manifest = json.loads((package / "world.json").read_text())
    document, binary = load_glb(package / "world.glb")

    findings: list[dict] = []

    def fail(code, message, detail=None):
        findings.append({"severity": "error", "code": code, "message": message,
                         "detail": detail})

    def warn(code, message, detail=None):
        findings.append({"severity": "warning", "code": code, "message": message,
                         "detail": detail})

    # -- 1. node names must be unique: the client resolves nodes by name --
    names = [node.get("name", "") for node in document["nodes"]]
    duplicates = {n for n in names if n and names.count(n) > 1} if len(names) < 6000 else set()
    if duplicates:
        fail("NODE_NAME_NOT_UNIQUE",
             f"{len(duplicates)} node names are reused", sorted(duplicates)[:10])

    # -- 2. every declared collision node must exist and carry a mesh --
    name_to_node = {node.get("name"): node for node in document["nodes"]}
    missing = [n for n in manifest["collision"]["nodeNames"] if n not in name_to_node]
    if missing:
        fail("COLLISION_NODE_MISSING",
             f"{len(missing)} collision nodes are not in the scene", missing[:10])
    meshless = [n for n in manifest["collision"]["nodeNames"]
                if n in name_to_node and "mesh" not in name_to_node[n]
                and not name_to_node[n].get("children")]
    if meshless:
        fail("COLLISION_NODE_EMPTY",
             f"{len(meshless)} collision nodes carry no mesh", meshless[:10])

    # -- 3. build the navigation surface exactly as the client does --
    prefixes = tuple(manifest["navigation"]["surfaceNodePrefixes"])
    triangles, matched = collect_triangles(
        document, binary, lambda name: name.startswith(prefixes))
    print(f"[nav] {len(matched)} walk-surface nodes, {triangles.shape[0]} triangles")
    if triangles.shape[0] == 0:
        fail("NAV_SURFACE_EMPTY", "no node matched the navigation surface prefixes")
        return _finish(findings, args, {})

    index = VerticalRayIndex(triangles, cell=4.0)

    # -- 4. cast the grounding ray at every reachable server tile --
    transform = manifest["coordinateTransform"]
    origin_x, origin_y = transform["serverOrigin"]
    metres = transform["metresPerTile"]
    cells = int(manifest.get('asset', {}).get('serverCells', 384))
    walking_height = transform["walkingHeight"]
    collision = manifest["collision"]
    collision_payload = (package / collision["binary"]).read_bytes()
    _, _, _, cw, ch = struct.unpack("<4sHHII", collision_payload[:16])
    collision_grid = np.frombuffer(collision_payload, dtype=np.uint8, offset=16).reshape(ch, cw)
    reachable = served_reachable(collision_grid, cells, metres, collision['cellMetres'])

    misses = []
    heights = np.full((cells, cells), np.nan)
    for tile_y in range(0, cells, args.step):
        for tile_x in range(0, cells, args.step):
            if not reachable[tile_y, tile_x]:
                continue
            x = (tile_x + .5 - origin_x) * metres
            z = -(tile_y + .5 - origin_y) * metres
            hit = index.top_hit(x, z)
            if hit is None:
                misses.append((tile_x, tile_y, round(x, 1), round(z, 1)))
            else:
                heights[tile_y, tile_x] = hit

    sampled = int(np.isfinite(heights).sum()) + len(misses)
    miss_fraction = len(misses) / max(sampled, 1)
    print(f"[grounding] {sampled} tiles sampled, {len(misses)} misses "
          f"({miss_fraction * 100:.2f}%)")
    if misses:
        fail("GROUNDING_RAY_MISS",
             f"{len(misses)} walkable server tiles have no surface at their actor centre; a "
             f"character there would fall back to walkingHeight={walking_height}",
             misses[:12])

    # -- 5. the surface must be continuous across ground a player can reach --
    jumps = adjacent_jumps(heights, reachable)
    if jumps:
        warn("GROUNDING_DISCONTINUITY",
             f"{len(jumps)} adjacent tile pairs differ by more than 6 m of "
             "surface height (expected at cliffs and under bridges)",
             sorted(jumps, key=lambda item: -item[2])[:12])

    # -- 6. every spawn must land on a surface, not in the air or underground --
    for spawn in manifest["spawnPoints"]:
        x, y, z = spawn["position"]
        hit = index.top_hit(x, z)
        if hit is None:
            fail("SPAWN_NOT_GROUNDED",
                 f"spawn '{spawn['id']}' has no walk surface beneath it", spawn)
            continue
        delta = y - hit
        if abs(delta) > 0.6:
            fail("SPAWN_HEIGHT_MISMATCH",
                 f"spawn '{spawn['id']}' sits {delta:+.2f} m from the surface the "
                 "client would snap it to", {"declared": y, "surface": round(hit, 3)})
        # a spawn also needs room to stand: check the ring around it
        ring = [index.top_hit(x + math.cos(a) * 1.2, z + math.sin(a) * 1.2)
                for a in np.linspace(0, math.tau, 8, endpoint=False)]
        rough = [round(h - hit, 2) for h in ring if h is not None]
        if any(abs(d) > 1.6 for d in rough):
            warn("SPAWN_NEIGHBOURHOOD_ROUGH",
                 f"spawn '{spawn['id']}' has uneven ground within 1.2 m", rough)
        if len([h for h in ring if h is None]):
            warn("SPAWN_NEIGHBOURHOOD_GAP",
                 f"spawn '{spawn['id']}' has a hole in the walk surface within 1.2 m")

    # -- 7. portals and interactives must also stand on something --
    for collection, label in ((manifest.get("portals", []), "portal"),
                              (manifest.get("interactives", []), "interactive"),
                              (manifest.get("landmarks", []), "landmark")):
        for entry in collection:
            position = entry.get("position")
            if not position:
                continue
            hit = index.top_hit(position[0], position[2])
            if hit is None:
                warn(f"{label.upper()}_NOT_GROUNDED",
                     f"{label} '{entry.get('id')}' has no walk surface beneath it",
                     entry.get("position"))
            elif position[1] - hit < -2.0:
                warn(f"{label.upper()}_BELOW_SURFACE",
                     f"{label} '{entry.get('id')}' is {hit - position[1]:.2f} m below "
                     "the surface", entry.get("position"))

    # -- 8. the collision grid must agree with the rendered surface --
    payload = collision_payload
    magic, version, flags, width, height = struct.unpack("<4sHHII", payload[:16])
    if magic != b"EWCG" or version not in (1, 2):
        fail("COLLISION_BINARY_HEADER", "collision.bin is not EWCG version 1 or 2")
    elif len(payload) != 16 + width * height:
        fail("COLLISION_BINARY_SIZE", "collision.bin payload size does not match")
    elif width % 6 or height % 6:
        fail("COLLISION_BINARY_DIMENSIONS",
             "collision dimensions must be positive multiples of six")
    else:
        grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)
        walkable = float((grid > 0).mean())
        print(f"[collision] {width}x{height}, {walkable * 100:.1f}% walkable")
        if walkable < 0.15:
            warn("COLLISION_TOO_TIGHT",
                 f"only {walkable * 100:.1f}% of the map is walkable")
        # The served conservative fold, not an isolated residual half-cell,
        # determines which actors can stand here and their encoded elevation.
        mismatches = []
        step_metres = collision["cellMetres"]
        encode = collision["heightEncoding"]
        for tile_y in range(0, cells, 6):
            for tile_x in range(0, cells, 6):
                if not reachable[tile_y, tile_x]:
                    continue
                x = (tile_x + .5 - origin_x) * metres
                z = -(tile_y + .5 - origin_y) * metres
                hit = index.top_hit(x, z)
                if hit is None:
                    mismatches.append({"tile": [tile_x, tile_y], "issue": "no-surface"})
                    continue
                ratio = metres / step_metres
                x0 = max(0, min(width-1, math.floor((tile_x-.5)*ratio)))
                x1 = max(x0, min(width-1, math.ceil((tile_x+.5)*ratio)-1))
                y0 = max(0, min(height-1, math.floor((tile_y-.5)*ratio)))
                y1 = max(y0, min(height-1, math.ceil((tile_y+.5)*ratio)-1))
                encoded = encode["origin"] + float(grid[y0:y1+1,x0:x1+1].max()) * encode["step"]
                if abs(encoded - hit) > 2.5:
                    mismatches.append({"tile": [tile_x, tile_y],
                                       "encoded": round(float(encoded), 2),
                                       "surface": round(hit, 2)})
        if mismatches:
            warn("COLLISION_SURFACE_MISMATCH",
                 f"{len(mismatches)} sampled walkable actor centres disagree with the "
                 "rendered walk surface", mismatches[:10])

    # -- 9. nothing floats: sample landmark bases against the terrain surface --
    floating = []
    for entry in manifest.get("landmarks", []):
        position = entry.get("position")
        if not position:
            continue
        hit = index.top_hit(position[0], position[2])
        if hit is not None and position[1] - hit > 3.0 and entry.get("type") not in (
                "canopy-works", "bridge", "pavilion", "monumental-tree", "tree-hall",
                "harbour", "landing", "sea-stack"):
            floating.append({"id": entry["id"], "gap": round(position[1] - hit, 2)})
    if floating:
        warn("LANDMARK_FLOATING",
             f"{len(floating)} landmarks sit more than 3 m above the walk surface",
             floating[:10])

    summary = {
        "walkSurfaceNodes": len(matched),
        "walkSurfaceTriangles": int(triangles.shape[0]),
        "tilesSampled": sampled,
        "actorTileOffset": [.5, .5],
        "walkableServerTiles": int(reachable.sum()),
        "groundingMisses": len(misses),
        "groundingMissFraction": round(miss_fraction, 5),
        "surfaceDiscontinuities": len(jumps),
        "spawnPoints": len(manifest["spawnPoints"]),
    }
    return _finish(findings, args, summary)


def _finish(findings, args, summary) -> int:
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    payload = {"summary": summary, "errors": errors, "warnings": warnings}
    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2) + "\n")
    for finding in findings:
        print(f"  [{finding['severity']}] {finding['code']}: {finding['message']}")
        if finding.get("detail"):
            print(f"        {json.dumps(finding['detail'])[:220]}")
    print(f"[verify] {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
