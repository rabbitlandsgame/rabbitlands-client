#!/usr/bin/env python3
"""Report coplanar same-facing surfaces in a world GLB.

Two surfaces that face the same way and sit in the same plane have no stable
depth order, so the rasteriser picks a different winner per pixel and per frame
and the pair shimmers. The client renders through Godot's GL Compatibility
backend, which has a fixed-point 24-bit depth buffer, so a pair does not have to
be exactly coincident to fight: with the camera near plane at N metres the
resolvable depth step at distance z is about ``z^2 / (N * 2^24)`` metres, which
is 0.6 mm at 100 m and 9 mm at 400 m for N = 1.

This reports *overlap area*, not merely "these triangles are near each other".
Two terrain triangles that meet along an edge are coplanar and adjacent, never
in conflict, and a centroid-distance test cannot tell them apart from a decal
lying on a road. Every candidate pair is clipped against the other in-plane and
only real overlap is counted.

Run:  python3 eloria-assets/tools/check_zfighting.py maps/four-gates/world.glb
      python3 eloria-assets/tools/check_zfighting.py --json report.json <glb>...
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import struct
import sys

import numpy as np

COMPONENT = {
    5120: (np.int8, 1), 5121: (np.uint8, 1), 5122: (np.int16, 2),
    5123: (np.uint16, 2), 5125: (np.uint32, 4), 5126: (np.float32, 4),
}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
              "MAT2": 4, "MAT3": 9, "MAT4": 16}

# A pair has to be flatter than this to share a plane at all. 0.03 in a unit
# normal is about 1.7 degrees, which is one step of the terrain's own curvature
# and therefore the coarsest binning that does not merge a hillside into itself.
NORMAL_QUANTUM = 0.03
CELL_METRES = 4.0
# Below this a triangle is trim, and trim that fights is not what a player sees.
MIN_TRIANGLE_AREA = 0.02
# Reported groups need this much real overlap before they are worth a fix.
MIN_REPORT_AREA = 0.25


def parse_glb(path: str):
    data = open(path, "rb").read()
    magic, version, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67 or version != 2 or length != len(data):
        raise ValueError(f"{path}: not a valid GLB 2.0 container")
    offset, document, binary = 12, None, b""
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack("<II", data[offset:offset + 8])
        payload = data[offset + 8:offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A:
            document = json.loads(payload.decode("utf-8"))
        elif chunk_type == 0x004E4942:
            binary = payload
        offset += 8 + chunk_length
    if document is None:
        raise ValueError(f"{path}: no JSON chunk")
    return document, binary


def read_accessor(document, binary, index):
    accessor = document["accessors"][index]
    dtype, size = COMPONENT[accessor["componentType"]]
    components = TYPE_COUNT[accessor["type"]]
    count = accessor["count"]
    if "bufferView" not in accessor:
        return np.zeros((count, components), dtype=dtype)
    view = document["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride")
    width = size * components
    if stride and stride != width:
        raw = np.frombuffer(binary, dtype=np.uint8,
                            count=(count - 1) * stride + width, offset=start)
        picks = (np.arange(count)[:, None] * stride + np.arange(width)[None, :])
        out = raw[picks].tobytes()
        values = np.frombuffer(out, dtype=dtype, count=count * components)
    else:
        values = np.frombuffer(binary, dtype=dtype, count=count * components,
                               offset=start)
    return values.reshape(count, components) if components > 1 else values


def node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    out = np.eye(4)
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        out[:3, :3] = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
    if "scale" in node:
        out[:3, :3] = out[:3, :3] @ np.diag(node["scale"])
    if "translation" in node:
        out[:3, 3] = node["translation"]
    return out


def gather_surfaces(document, binary):
    """World-space triangles, one entry per node primitive that draws."""
    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])
    scene = document.get("scenes", [{}])[document.get("scene", 0)]
    surfaces = []

    def walk(index, parent):
        node = nodes[index]
        world = parent @ node_matrix(node)
        if "mesh" in node:
            mesh = meshes[node["mesh"]]
            for slot, primitive in enumerate(mesh.get("primitives", [])):
                if primitive.get("mode", 4) != 4 or "POSITION" not in primitive.get(
                        "attributes", {}):
                    continue
                position = read_accessor(
                    document, binary, primitive["attributes"]["POSITION"]).astype(
                        np.float64)
                if "indices" in primitive:
                    faces = read_accessor(
                        document, binary, primitive["indices"]).astype(np.int64)
                else:
                    faces = np.arange(len(position), dtype=np.int64)
                faces = faces.reshape(-1, 3)
                if len(faces) == 0:
                    continue
                world_position = position @ world[:3, :3].T + world[:3, 3]
                material = primitive.get("material")
                surfaces.append({
                    "node": node.get("name", f"node_{index}"),
                    "mesh": mesh.get("name", f"mesh_{node['mesh']}"),
                    "primitive": slot,
                    "triangles": world_position[faces],
                    "cut": (material is not None
                            and document["materials"][material].get("alphaMode")
                            == "MASK"
                            and "COLOR_0" in primitive.get("attributes", {})),
                })
        for child in node.get("children", []):
            walk(child, world)

    for root in scene.get("nodes", []):
        walk(root, np.eye(4))
    return surfaces


def hidden_nodes(path):
    """Nodes the client never draws, read from the package manifest beside the GLB.

    A collision proxy and a hidden interior lid are geometry that exists only for
    physics or only to be cut away, so counting their surfaces as fighting would
    report work that does not need doing.
    """
    import os
    directory = os.path.dirname(os.path.abspath(path))
    base = os.path.basename(path)
    names = set()
    for candidate in (base.rsplit(".", 1)[0] + ".json", "world.json"):
        manifest_path = os.path.join(directory, candidate)
        if not os.path.exists(manifest_path):
            continue
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken manifest is not this tool's job
            continue
        if not isinstance(manifest, dict):
            continue
        collision = manifest.get("collision", {})
        if isinstance(collision, dict) and collision.get("nodesAreProxies"):
            names.update(str(n) for n in collision.get("nodeNames", []))
        cutaway = manifest.get("cutaway", {})
        if isinstance(cutaway, dict):
            names.update(str(n) for n in cutaway.get("hideNodes", []))
        break
    return names


def _clip_area(subject, clipper):
    """Area of the intersection of two convex 2D polygons (Sutherland-Hodgman).

    Both polygons must be wound clockwise, so a point is inside an edge when it
    is on the edge's right-hand side, i.e. the cross product is not positive.
    """
    output = list(subject)
    count = len(clipper)
    for i in range(count):
        if not output:
            return 0.0
        ax, ay = clipper[i]
        bx, by = clipper[(i + 1) % count]
        ex, ey = bx - ax, by - ay
        side = [ex * (py - ay) - ey * (px - ax) for px, py in output]
        clipped = []
        for j, (px, py) in enumerate(output):
            k = (j + 1) % len(output)
            qx, qy = output[k]
            here, there = side[j], side[k]
            if here <= 0.0:
                clipped.append((px, py))
            if (here > 0.0) != (there > 0.0):
                t = here / (here - there)
                clipped.append((px + (qx - px) * t, py + (qy - py) * t))
        output = clipped
    if len(output) < 3:
        return 0.0
    area = 0.0
    for i in range(len(output)):
        x0, y0 = output[i]
        x1, y1 = output[(i + 1) % len(output)]
        area += x0 * y1 - x1 * y0
    return abs(area) * 0.5


def _oriented(polygon):
    """Clockwise ordering, which is what `_clip_area`'s inside test assumes."""
    area = 0.0
    for i in range(len(polygon)):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % len(polygon)]
        area += x0 * y1 - x1 * y0
    return polygon if area < 0.0 else polygon[::-1]


def analyse(path, *, tolerance, cell, min_area, downward, limit, drawn_only=True):
    document, binary = parse_glb(path)
    surfaces = gather_surfaces(document, binary)
    skip = hidden_nodes(path) if drawn_only else set()

    keep_triangles, owner = [], []
    for index, surface in enumerate(surfaces):
        if surface["node"] in skip:
            continue
        triangles = surface["triangles"]
        cross = np.cross(triangles[:, 1] - triangles[:, 0],
                         triangles[:, 2] - triangles[:, 0])
        length = np.linalg.norm(cross, axis=1)
        wanted = length > min_area * 2.0
        if not wanted.any():
            continue
        keep_triangles.append(triangles[wanted])
        owner.append(np.full(int(wanted.sum()), index, dtype=np.int64))
    if not keep_triangles:
        return {"path": path, "triangles": 0, "groups": [], "area": 0.0}

    triangles = np.vstack(keep_triangles)
    owner = np.concatenate(owner)
    cross = np.cross(triangles[:, 1] - triangles[:, 0],
                     triangles[:, 2] - triangles[:, 0])
    length = np.linalg.norm(cross, axis=1)
    normals = cross / length[:, None]
    if not downward:
        # A pair of down-facing surfaces is under the geometry that carries it:
        # the isometric rig never sees the underside of a plinth or a floor.
        facing = normals[:, 1] > -0.5
        triangles, normals = triangles[facing], normals[facing]
        owner, length = owner[facing], length[facing]
    offsets = np.einsum("ij,ij->i", normals, triangles.mean(axis=1))
    drop = np.argmax(np.abs(normals), axis=1)
    axis_u, axis_v = (drop + 1) % 3, (drop + 2) % 3
    rows = np.arange(len(triangles))
    flat = np.stack([triangles[rows][:, :, 0], triangles[rows][:, :, 1],
                     triangles[rows][:, :, 2]], axis=2)
    projected = np.stack([np.take_along_axis(flat, axis_u[:, None, None]
                                             .repeat(3, 1), axis=2)[:, :, 0],
                          np.take_along_axis(flat, axis_v[:, None, None]
                                             .repeat(3, 1), axis=2)[:, :, 0]],
                         axis=2)
    low = projected.min(axis=1)
    high = projected.max(axis=1)

    direction = np.round(normals / NORMAL_QUANTUM).astype(np.int64)
    buckets = collections.defaultdict(list)
    for index in range(len(triangles)):
        u0, v0 = np.floor(low[index] / cell).astype(np.int64)
        u1, v1 = np.floor(high[index] / cell).astype(np.int64)
        if (u1 - u0 + 1) * (v1 - v0 + 1) > 4096:
            continue        # a single triangle spanning 16 km of plane: skybox
        key_head = (int(direction[index, 0]), int(direction[index, 1]),
                    int(direction[index, 2]), int(drop[index]))
        for u in range(u0, u1 + 1):
            for v in range(v0, v1 + 1):
                buckets[key_head + (u, v)].append(index)

    groups = collections.defaultdict(lambda: {"area": 0.0, "pairs": 0,
                                              "gap": 0.0, "at": None})
    seen = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        for a_pos in range(len(members)):
            a = members[a_pos]
            for b_pos in range(a_pos + 1, len(members)):
                b = members[b_pos]
                if abs(offsets[a] - offsets[b]) >= tolerance:
                    continue
                if owner[a] == owner[b] and a == b:
                    continue
                # Two alpha-tested surfaces carrying per-vertex coverage do not
                # fight: they are the ground's own classes cut against each
                # other inside the cell, and the test hands each pixel to
                # exactly one of them. They overlap by design, and counting
                # that overlap buries the pairs that do fight.
                if surfaces[owner[a]].get("cut") and surfaces[owner[b]].get("cut"):
                    continue
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                seen.add(pair)
                if (low[a] >= high[b]).any() or (low[b] >= high[a]).any():
                    continue
                overlap = _clip_area(_oriented([tuple(p) for p in projected[a]]),
                                     _oriented([tuple(p) for p in projected[b]]))
                if overlap <= 1e-4:
                    continue
                first, second = surfaces[owner[a]], surfaces[owner[b]]
                key = tuple(sorted((f"{first['mesh']}#{first['primitive']}",
                                    f"{second['mesh']}#{second['primitive']}")))
                entry = groups[key]
                entry["area"] += overlap
                entry["pairs"] += 1
                entry["gap"] = max(entry["gap"], abs(offsets[a] - offsets[b]))
                if entry["at"] is None:
                    entry["at"] = [round(float(v), 1)
                                   for v in triangles[a].mean(axis=0)]
                    entry["nodes"] = [first["node"], second["node"]]
                    entry["normal"] = [round(float(v), 2) for v in normals[a]]

    ranked = sorted(groups.items(), key=lambda item: -item[1]["area"])
    ranked = [entry for entry in ranked if entry[1]["area"] >= MIN_REPORT_AREA]
    return {
        "path": path,
        "triangles": int(len(triangles)),
        "area": round(float(sum(e[1]["area"] for e in ranked)), 1),
        "groups": [{"surfaces": list(key), **{k: (round(v, 4)
                                                  if isinstance(v, float) else v)
                                              for k, v in value.items()}}
                   for key, value in ranked[:limit]],
        "groupCount": len(ranked),
        "hiddenNodes": len(skip),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("glb", nargs="+")
    parser.add_argument("--tolerance", type=float, default=0.012,
                        help="plane separation counted as coplanar, metres")
    parser.add_argument("--cell", type=float, default=CELL_METRES)
    parser.add_argument("--min-area", type=float, default=MIN_TRIANGLE_AREA)
    parser.add_argument("--downward", action="store_true",
                        help="also report pairs that only face downward")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--all-nodes", action="store_true",
                        help="include nodes the manifest hides from the client")
    parser.add_argument("--json", default="")
    parser.add_argument("--max-area", type=float, default=-1.0,
                        help="exit non-zero when total overlap exceeds this")
    args = parser.parse_args()

    reports = []
    worst = 0.0
    for path in args.glb:
        report = analyse(path, tolerance=args.tolerance, cell=args.cell,
                         min_area=args.min_area, downward=args.downward,
                         limit=args.limit, drawn_only=not args.all_nodes)
        reports.append(report)
        worst = max(worst, report["area"])
        print(f"{path}: coplanar overlap {report['area']:.1f} m^2 across "
              f"{report['groupCount']} surface pairs "
              f"({report['triangles']} triangles considered)")
        for group in report["groups"]:
            at = group.get("at") or [0, 0, 0]
            print(f"   {group['area']:9.2f} m^2  gap={group['gap']:.4f}  "
                  f"at=({at[0]}, {at[1]}, {at[2]})  "
                  f"{group['surfaces'][0]} || {group['surfaces'][1]}")
    if args.json:
        with open(args.json, "w", newline="\n") as handle:
            json.dump(reports, handle, indent=2)
            handle.write("\n")
    if args.max_area >= 0.0 and worst > args.max_area:
        print(f"FAIL: {worst:.1f} m^2 exceeds --max-area {args.max_area:.1f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
