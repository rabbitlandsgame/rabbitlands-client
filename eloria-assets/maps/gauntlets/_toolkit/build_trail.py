#!/usr/bin/env python3
"""Build a trail gauntlet's grey-box client package from its source layout.

    python eloria-assets/maps/gauntlets/_toolkit/build_trail.py harrowcrag_gauntlet --server <eloria-server checkout>

One layout (``<route>/source/layout.json``) drives the terrain, the walk grids,
the grey-box dressing, the markers and the ``gauntlet`` block the server's
authoring tool reads (TRAIL_FORMAT.md). The walkable ground is exactly the
route network: trail corridors, arenas, their creature mouths, the side
pocket, the checkpoint clearings, the camp and the vault. Everything else is
banks, cliffs and woods, so the road has no shortcut by construction and the
package test proves it.

Plan coordinates are metres with x east and y SOUTH (the layout's frame).
Server tiles have y north: tile (x, y) is the plan cell [x, x+1) x
[H-1-y, H-y). Godot positions are (x, height, plan y), the frame
build_underground.py uses with serverOrigin [0, H] and invertServerY.
"""
from __future__ import annotations

import argparse
import os
import dataclasses
import hashlib
import importlib.util
import json
import math
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
GAUNTLETS = HERE.parent
CHECKOUT = HERE.parents[3]
TOOLKIT = CHECKOUT / "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(TOOLKIT))
from amberwood import gltf as G, mesh as M, materials as MAT, textures as T  # noqa: E402
sys.path.insert(0, str(HERE))
from kits import KitLibrary  # noqa: E402
from landforms import Land  # noqa: E402

TOOL = "eloria-assets/maps/gauntlets/_toolkit/build_trail.py"
SCHEMA = "eloria-trail-gauntlet-v1"
DEEP_RIVER = -4.6          # river bed outside the ford: not walkable
FORD_DEPTH = 0.35          # water over the ford's gravel


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def seeded(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF


# ---------------------------------------------------------------- noise
def value_noise(px, py, scale, seed, octaves=3):
    """Smooth value noise at arbitrary points (deterministic, numpy only)."""
    rng = np.random.default_rng(seed)
    out = np.zeros_like(px, dtype=np.float64)
    amp, freq = 1.0, 1.0 / scale
    for _ in range(octaves):
        grid = rng.standard_normal((int(600 * freq) + 4, int(600 * freq) + 4))
        fx, fy = px * freq, py * freq
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = grid[y0, x0] * (1 - tx) + grid[y0, x0 + 1] * tx
        b = grid[y0 + 1, x0] * (1 - tx) + grid[y0 + 1, x0 + 1] * tx
        out += amp * (a * (1 - ty) + b * ty)
        amp *= 0.5
        freq *= 2.0
    return out


def box_blur(a, r):
    for axis in (0, 1):
        pad = np.pad(a, [(r, r) if i == axis else (0, 0) for i in range(2)], mode="edge")
        cs = np.insert(np.cumsum(pad, axis=axis), 0, 0, axis=axis)
        n = a.shape[axis]
        a = (np.take(cs, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
             - np.take(cs, np.arange(0, n), axis=axis)) / (2 * r + 1)
    return a


# ---------------------------------------------------------------- the layout as features
def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def ellipse_rim(sec, bearing_deg):
    """Distance from an ellipse's centre to its rim along a bearing (plan degrees)."""
    r = math.radians(sec.get("rot", 0))
    b = math.radians(bearing_deg)
    ux, uy = math.cos(b), math.sin(b)
    lx = ux * math.cos(r) + uy * math.sin(r)
    ly = -ux * math.sin(r) + uy * math.cos(r)
    return 1.0 / math.sqrt((lx / sec["rx"]) ** 2 + (ly / sec["ry"]) ** 2)


def ellipse_d(sec, px, py):
    cx, cy = sec["at"]
    r = math.radians(sec.get("rot", 0))
    ux = (px - cx) * math.cos(r) + (py - cy) * math.sin(r)
    uy = -(px - cx) * math.sin(r) + (py - cy) * math.cos(r)
    k = np.hypot(ux / sec["rx"], uy / sec["ry"])
    return (k - 1.0) * min(sec["rx"], sec["ry"])


class Layout:
    """The route network: every walkable feature with its signed distance and elevation."""

    def __init__(self, data):
        self.data = data
        self.W, self.H = data["size"]
        self.sections = {s["id"]: s for s in data["sections"]}
        self.order = [s["id"] for s in data["sections"]]
        defaults = data.get("mouthDefaults", {})
        # resolve mouths into concrete pockets (centre, radius, elevation, link)
        self.mouths = []
        for s in data["sections"]:
            for m in s.get("mouths", []):
                kind = m.get("kind", "pocket")
                entry = {"id": m["id"], "section": s["id"], "kind": kind}
                if kind == "floor":
                    entry["ring"] = m["ring"]
                else:
                    out = m.get("out", defaults.get("out", 6))
                    radius = m.get("radius", defaults.get("radius", 7))
                    rim = ellipse_rim(s, m["bearing"])
                    b = math.radians(m["bearing"])
                    cx, cy = s["at"]
                    entry["rimPoint"] = (cx + math.cos(b) * (rim - 2), cy + math.sin(b) * (rim - 2))
                    entry["at"] = (cx + math.cos(b) * (rim + out + radius), cy + math.sin(b) * (rim + out + radius))
                    entry["radius"] = radius
                    entry["elev"] = s["elev"] + (m.get("rise", 4) if kind == "ledge" else 0)
                    entry["width"] = m.get("linkWidth", defaults.get("linkWidth", 5))
                self.mouths.append(entry)
        self.paths = []
        for p in data["paths"]:
            a, b = self.sections[p["from"]], self.sections[p["to"]]
            pts = [(a["at"][0], a["at"][1], a["elev"])] + [tuple(q) for q in p["points"]] + \
                  [(b["at"][0], b["at"][1], b["elev"])]
            self.paths.append({"from": p["from"], "to": p["to"], "width": p["width"], "points": pts})

    def features(self, px, py):
        """Yield (name, kind, signed distance, elevation) over the point arrays."""
        for s in self.data["sections"]:
            d = ellipse_d(s, px, py)
            e = s["elev"] + 0.45 * value_noise(px, py, 16, seeded(s["id"]), 2)
            yield s["id"], s["kind"], d, e
        for p in self.paths:
            half = p["width"] / 2.0
            pts = p["points"]
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                d, t = seg_dist(px, py, a[:2], b[:2])
                yield f"path:{p['from']}-{p['to']}:{i}", "path", d - half, a[2] + (b[2] - a[2]) * t
        for m in self.mouths:
            if m["kind"] == "floor":
                continue
            d = np.hypot(px - m["at"][0], py - m["at"][1]) - m["radius"]
            yield m["id"], "mouth", d, np.full_like(px, m["elev"])
            sec = self.sections[m["section"]]
            dl, t = seg_dist(px, py, m["rimPoint"], m["at"])
            yield m["id"] + ":link", "mouth", dl - m["width"] / 2.0, sec["elev"] + (m["elev"] - sec["elev"]) * t
        for side in self.data.get("sides", []):
            d = np.hypot(px - side["at"][0], py - side["at"][1]) - side["radius"]
            yield side["id"], "side", d, np.full_like(px, side["elev"])
            fx, fy, fe = side["from"]
            dl, t = seg_dist(px, py, (fx, fy), side["at"])
            yield side["id"] + ":link", "side", dl - side["width"] / 2.0, fe + (side["elev"] - fe) * t
        for cp in self.data.get("checkpoints", []):
            d = np.hypot(px - cp["at"][0], py - cp["at"][1]) - 5.0
            yield cp["id"], "checkpoint", d, np.full_like(px, cp["elev"])

    def field(self, px, py):
        """(signed distance to the network, blended walking elevation, owning feature index, names)."""
        names, kinds, ds, es = [], [], [], []
        for name, kind, d, e in self.features(px, py):
            names.append(name)
            kinds.append(kind)
            ds.append(d)
            es.append(e)
        D = np.stack(ds)
        E = np.stack(es)
        dmin = D.min(axis=0)
        owner = D.argmin(axis=0)
        # soft-min blend of elevations so joins between features are smooth
        w = np.exp(-(np.clip(D, -6, None) - np.clip(dmin, -6, None)[None]) / 1.2)
        w = np.where(D <= dmin[None] + 4.0, w, 0.0)
        elev = (w * E).sum(axis=0) / np.maximum(w.sum(axis=0), 1e-9)
        return dmin, elev, owner, names, kinds


# ---------------------------------------------------------------- terrain
def build_terrain(layout: Layout, step: float):
    """Heights and network data on a lattice of the given spacing covering [0, W] x [0, H]."""
    W, H = layout.W, layout.H
    xs = np.arange(0, W + 1e-9, step)
    ys = np.arange(0, H + 1e-9, step)
    px, py = np.meshgrid(xs, ys)
    d, elev, owner, names, kinds = layout.field(px, py)
    walk = d <= 0
    if "land" in layout.data:
        return land_terrain(layout, step, px, py, d, elev, owner, names, kinds, walk)
    # ground round the road follows the ring's level, smoothed, and rises toward the frame
    ring_ids = [i for i, n in enumerate(names) if not n.startswith(("w5", "boss", "vault", "path:w5", "path:w4-w5", "path:boss", "court"))]
    e_ring = np.where(np.isin(owner, ring_ids), elev, np.nan)
    e_ring = np.where(np.isnan(e_ring), np.nanmedian(e_ring), e_ring)
    r = max(2, int(18 / step))
    for _ in range(3):
        e_ring = box_blur(e_ring, r)
    hills = e_ring + 3.6 + 3.4 * value_noise(px, py, 60, 11) + 1.6 * value_noise(px, py, 18, 12)
    edge = np.minimum.reduce([px, py, W - px, H - py])
    hills += np.clip(30 - edge, 0, None) * 0.55
    hills += np.clip(30 - py, 0, None) * 0.8
    c = layout.data["crag"]
    kc = np.hypot((px - c["centre"][0]) / c["rx"], (py - c["centre"][1]) / c["ry"])
    crag_top = c["top"] + 1.0 * value_noise(px, py, 10, 21, 2)
    cliff = np.clip((kc - 1.0) * min(c["rx"], c["ry"]) / 14.0, 0, 1)
    crag = crag_top - cliff ** 0.6 * (crag_top + 6)
    land = np.maximum(hills, crag)
    # carve: cut banks rise over ~8 m from the road's edge, fill edges fall over ~3 m
    dd = np.clip(d, 0, None)
    cut = land >= elev
    reach = np.where(cut, 12.0, 3.0)
    t = np.clip(dd / reach, 0, 1)
    t = t * t * (3 - 2 * t)
    height = np.where(walk, elev, elev * (1 - t) + land * t)
    # the road's edge is always a lip of at least ~1.2 m, so off-road ground never reads as road
    lip = np.clip(dd, 0, 3.0) * 0.4
    height = np.where(~walk & (dd <= 10), np.maximum(height, elev + lip), height)
    height = np.where(dd > 10, land, height)
    # the river: deep outside the ford arena, a shallow gravel bar inside it
    river = layout.data["river"]
    rd = np.full(px.shape, 1e9)
    for a, b in zip(river["points"], river["points"][1:]):
        dist, _ = seg_dist(px, py, a, b)
        rd = np.minimum(rd, dist)
    wet = rd < river["width"] / 2.0
    ford_sec = layout.sections[river["ford"]]
    in_ford = ellipse_d(ford_sec, px, py) < -1.0
    bank = (rd < river["width"] / 2.0 + 3.0) & ~wet & ~walk
    height = np.where(bank, np.minimum(height, -1.6), height)
    deep = wet & ~in_ford
    height = np.where(deep, DEEP_RIVER, height)
    ford = wet & in_ford
    height = np.where(ford, ford_sec["elev"] - FORD_DEPTH * 0.5, height)
    walk = walk & ~deep
    return {"px": px, "py": py, "height": height, "walk": walk, "d": d, "elev": elev,
            "owner": owner, "names": names, "kinds": kinds, "wet": wet, "ford": ford, "rd": rd, "kc": kc}


def land_terrain(layout: Layout, step, px, py, d, elev, owner, names, kinds, walk):
    """The road carved into a layout's own `land` (landforms.py), for every route but the crag's."""
    land = Land(layout)
    base = land.base(px, py, step, elev, owner)
    dd = np.clip(d, 0, None)
    cut = base >= elev
    reach = np.where(cut, land.spec.get("cut", 12.0), 3.0)
    t = np.clip(dd / reach, 0, 1)
    t = t * t * (3 - 2 * t)
    height = np.where(walk, elev, elev * (1 - t) + base * t)
    if not land.water_mode:
        # the road's edge is a lip of ground above it, so off-road never reads as road
        lip = np.clip(dd, 0, 3.0) * 0.4
        height = np.where(~walk & (dd <= 10), np.maximum(height, elev + lip), height)
    height = np.where(dd > 10, base, height)
    height, feats = land.carve(px, py, height, walk)
    wet = (feats["lake"] | feats["river"] | feats["canal"]) & ~(walk & feats["keep"])
    walk = walk & ~feats["deep"]
    return {"px": px, "py": py, "height": height, "walk": walk, "d": d, "elev": elev, "owner": owner,
            "names": names, "kinds": kinds, "wet": wet, "features": feats, "land": land,
            "kc": np.full(px.shape, 9.0)}


# ---------------------------------------------------------------- dressing
class Props:
    """Grey-box primitives: what they look like and which ground they close."""

    def __init__(self, height_at):
        self.height_at = height_at
        self.pieces = []           # (bucket, Mesh)
        self.solids = []           # ("box", cx, cy, hx, hy, rot) | ("disc", cx, cy, r)
        self.lights = []
        self.notes = set()
        self.counts = {}

    def _z(self, x, y, z):
        return self.height_at(x, y) if z is None else z

    def box(self, x, y, sx, sy, sz, rot=0.0, mat="ashlar", solid=True, z=None, bucket="Props", sink=0.3):
        z0 = self._z(x, y, z) - sink
        piece = M.box((sx, sz + sink, sy), (0, (sz + sink) / 2, 0), uv_scale=0.35, material=mat)
        piece.rotate_y(-math.radians(rot)).translate(x, z0, y)
        self.pieces.append((bucket, piece))
        if solid:
            self.solids.append(("box", x, y, sx / 2, sy / 2, math.radians(rot)))

    def cyl(self, x, y, r, h, mat="ashlar", solid=True, z=None, top=None, segments=10, bucket="Props", sink=0.3):
        z0 = self._z(x, y, z) - sink
        piece = M.cylinder(r, r if top is None else top, h + sink, segments, material=mat)
        piece.translate(x, z0 + (h + sink) / 2, y)
        self.pieces.append((bucket, piece))
        if solid:
            self.solids.append(("disc", x, y, r))

    def cone(self, x, y, r, h, mat="gb_canopy", z=None, bucket="Trees", segments=7, solid=False):
        z0 = self._z(x, y, z)
        piece = M.cylinder(r, 0.0, h, segments, material=mat)
        piece.translate(x, z0 + h / 2, y)
        self.pieces.append((bucket, piece))
        if solid:
            self.solids.append(("disc", x, y, r * 0.3))

    def tree(self, x, y, s=1.0, kind="fir", solid=False):
        z0 = self.height_at(x, y)
        trunk = M.cylinder(0.35 * s, 0.25 * s, 3.0 * s, 6, material="gb_trunk").translate(x, z0 + 1.4 * s, y)
        self.pieces.append(("Trees", trunk))
        if kind == "fir":
            self.cone(x, y, 2.6 * s, 7.5 * s, z=z0 + 2.2 * s, mat="gb_canopy")
        else:
            ball = M.icosphere(2.8 * s, 1, material="gb_canopy_broad").scale(1, 0.85, 1).translate(x, z0 + 5.0 * s, y)
            self.pieces.append(("Trees", ball))
        if solid:
            self.solids.append(("disc", x, y, 0.45 * s))

    def rock(self, x, y, r, mat="cliff_rock", solid=True, squash=0.6, seed=0):
        z0 = self.height_at(x, y)
        piece = M.icosphere(r, 1, material=mat).scale(1.0, squash, 0.85).rotate_y(seed * 0.7).translate(x, z0 + r * squash * 0.35, y)
        self.pieces.append(("Props", piece))
        if solid:
            self.solids.append(("disc", x, y, r * 0.9))

    def wall(self, points, thick=2.2, high=6.0, mat="ashlar", z=None, gaps=(), solid=True):
        """A wall along a polyline; `gaps` are (x, y, radius) holes."""
        for a, b in zip(points, points[1:]):
            n = max(1, int(math.dist(a, b) / 3.0))
            for i in range(n):
                t0, t1 = i / n, (i + 1) / n
                p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
                p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
                mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
                if any(math.hypot(mx - gx, my - gy) < gr for gx, gy, gr in gaps):
                    continue
                ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
                hh = high * (0.75 + 0.25 * math.sin(mx * 0.31 + my * 0.17))
                self.box(mx, my, math.dist(p0, p1) + 0.3, thick, hh, rot=ang, mat=mat, solid=solid, z=z)

    def light(self, x, y, z, color=(1.0, 0.62, 0.3), energy=2.4, rng=14.0, ident=None):
        self.lights.append({"id": ident or f"light-{len(self.lights):03d}", "position": [x, z, y],
                            "color": list(color), "energyHint": energy, "rangeHint": rng})


def load_dressing(route_dir: Path):
    path = route_dir / "source" / "dressing.py"
    spec = importlib.util.spec_from_file_location("trail_dressing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


# ---------------------------------------------------------------- collision
def solid_mask(solids, cx, cy):
    """Half-metre cells (centres cx, cy) a body stands on: the prism of every solid."""
    mask = np.zeros(cx.shape, bool)
    for s in solids:
        if s[0] == "disc":
            _, x, y, r = s
            mask |= (cx - x) ** 2 + (cy - y) ** 2 < (r + 0.35) ** 2
        else:
            _, x, y, hx, hy, rot = s
            ux = (cx - x) * math.cos(rot) + (cy - y) * math.sin(rot)
            uy = -(cx - x) * math.sin(rot) + (cy - y) * math.cos(rot)
            mask |= (np.abs(ux) < hx + 0.35) & (np.abs(uy) < hy + 0.35)
    return mask


def nearest_open(codes, tile):
    x, y = tile
    if codes[y, x]:
        return (x, y)
    ys, xs = np.nonzero(codes)
    k = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
    return (int(xs[k]), int(ys[k]))


def shortest_path(codes, start, goal, climb):
    """Tiles of a shortest walk under the served rule (8 steps, corner rule)."""
    from collections import deque
    H, W = codes.shape

    def ok(x, y, nx, ny):
        return (0 <= nx < W and 0 <= ny < H and codes[ny, nx] != 0
                and abs(int(codes[ny, nx]) - int(codes[y, x])) <= climb)

    parent = {start: None}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            break
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, -1), (-1, 1)):
            n = (x + dx, y + dy)
            if n in parent or not ok(x, y, *n):
                continue
            if dx and dy and not (ok(x, y, x + dx, y) and ok(x, y, x, y + dy)):
                continue
            parent[n] = (x, y)
            queue.append(n)
    if goal not in parent:
        return []
    out = []
    node = goal
    while node is not None:
        out.append([int(node[0]), int(node[1])])
        node = parent[node]
    return out[::-1]


def reachable(codes, start, climb):
    """The served walk rule from `start` over u16 codes [y, x]: both tiles open, at most
    `climb` codes apart, a diagonal only where both of its straight steps are."""
    from collections import deque
    H, W = codes.shape
    seen = np.zeros(codes.shape, bool)
    if not codes[start[1], start[0]]:
        return seen

    def ok(x, y, nx, ny):
        return (0 <= nx < W and 0 <= ny < H and codes[ny, nx] != 0
                and abs(int(codes[ny, nx]) - int(codes[y, x])) <= climb)

    seen[start[1], start[0]] = True
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < H) or seen[ny, nx] or not ok(x, y, nx, ny):
                continue
            if dx and dy and not (ok(x, y, nx, y) and ok(x, y, x, ny)):
                continue
            seen[ny, nx] = True
            queue.append((nx, ny))
    return seen


def encode_heights(heights, walkable):
    low, high = float(heights[walkable].min()), float(heights[walkable].max())
    step = max(0.2, (high - low) / 253)
    origin = low - step
    values = np.rint((heights - origin) / step)
    inside = (values >= 1) & (values <= 255)
    return (np.where(walkable & inside, np.clip(values, 1, 255), 0).astype(np.uint8),
            {"origin": origin, "step": step, "range": [1, 255]})


# ---------------------------------------------------------------- mesh helpers
def compact(mesh: M.Mesh) -> M.Mesh:
    used, inverse = np.unique(mesh.indices, return_inverse=True)
    out = M.Mesh(positions=mesh.positions[used], normals=mesh.normals[used], uvs=mesh.uvs[used],
                 colors=None if mesh.colors is None else mesh.colors[used],
                 indices=inverse.astype(np.int64), material=mesh.material)
    return out


def terrain_meshes(heights, classes, names_by_class, triplanar=("cliff_rock",)):
    """One mesh per (class) over a 1 m vertex grid; `classes` is per quad."""
    out = {}
    for cls, (bucket, material) in names_by_class.items():
        cells = classes == cls
        if not cells.any():
            continue
        mesh = compact(M.heightfield(heights, 0.0, 0.0, 1.0, uv_scale=0.25, material=material, cells=cells))
        if material in triplanar:
            mesh.project_uv_triplanar(0.18)      # planar UVs stretch into stripes on a cut bank
        out[bucket] = mesh
    return out


# ---------------------------------------------------------------- overlays
def chaikin(points, rounds=3):
    pts = np.asarray(points, dtype=np.float64)
    for _ in range(rounds):
        q = pts[:-1] * 0.75 + pts[1:] * 0.25
        r = pts[:-1] * 0.25 + pts[1:] * 0.75
        mid = np.empty((len(q) * 2, pts.shape[1]))
        mid[0::2], mid[1::2] = q, r
        pts = np.vstack([pts[:1], mid, pts[-1:]])
    return pts


def ribbon(points, width, height_at, lift, material, step=1.0):
    """A strip `width` wide along a polyline (plan x, y), draped on the ground `lift` above it."""
    pts = chaikin(points)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    arc = np.r_[0.0, np.cumsum(seg)]
    samples = np.arange(0.0, arc[-1] + 1e-6, step)
    xs = np.interp(samples, arc, pts[:, 0])
    ys = np.interp(samples, arc, pts[:, 1])
    tx = np.gradient(xs)
    ty = np.gradient(ys)
    norm = np.maximum(np.hypot(tx, ty), 1e-9)
    nx, ny = -ty / norm, tx / norm
    across = np.array([-0.5, -0.25, 0.0, 0.25, 0.5])
    positions, uvs = [], []
    for i in range(len(samples)):
        for a in across:
            x, y = xs[i] + nx[i] * a * width, ys[i] + ny[i] * a * width
            positions.append((x, height_at(x, y) + lift, y))
            uvs.append(((a + 0.5) * width * 0.25, samples[i] * 0.25))
    cols = len(across)
    tris = []
    for i in range(len(samples) - 1):
        for j in range(cols - 1):
            a, b = i * cols + j, i * cols + j + 1
            c, d = a + cols, b + cols
            tris += [a, c, b, b, c, d]
    mesh = M.Mesh(positions=np.array(positions), normals=np.zeros((len(positions), 3)), uvs=np.array(uvs),
                  indices=np.array(tris, dtype=np.int64), material=material)
    mesh.recompute_normals(180.0)
    # the strip faces up whichever way the path runs
    if mesh.normals[:, 1].mean() < 0:
        mesh.flip_winding()
        mesh.recompute_normals(180.0)
    return mesh


def ellipse_floor(sec, shrink, height_at, lift, material, rings=6, around=72):
    cx, cy = sec["at"]
    rot = math.radians(sec.get("rot", 0))
    positions = [(cx, height_at(cx, cy) + lift, cy)]
    uvs = [(cx * 0.25, cy * 0.25)]
    for k in range(1, rings + 1):
        f = k / rings
        for i in range(around):
            a = 2 * math.pi * i / around
            lx, ly = (sec["rx"] - shrink) * f * math.cos(a), (sec["ry"] - shrink) * f * math.sin(a)
            x = cx + lx * math.cos(rot) - ly * math.sin(rot)
            y = cy + lx * math.sin(rot) + ly * math.cos(rot)
            positions.append((x, height_at(x, y) + lift, y))
            uvs.append((x * 0.25, y * 0.25))
    tris = []
    for i in range(around):
        tris += [0, 1 + (i + 1) % around, 1 + i]
    for k in range(rings - 1):
        base, nxt = 1 + k * around, 1 + (k + 1) * around
        for i in range(around):
            a, b = base + i, base + (i + 1) % around
            c, d = nxt + i, nxt + (i + 1) % around
            tris += [a, b, c, b, d, c]
    mesh = M.Mesh(positions=np.array(positions), normals=np.zeros((len(positions), 3)), uvs=np.array(uvs),
                  indices=np.array(tris, dtype=np.int64), material=material)
    mesh.recompute_normals(180.0)
    if mesh.normals[:, 1].mean() < 0:
        mesh.flip_winding()
        mesh.recompute_normals(180.0)
    return mesh


FLOOR_DEFAULTS = {"camp": "packed_earth", "vault": "ashlar", "court": "cobble_paving"}


def overlay_meshes(layout, height_at, floors, trail_material="packed_earth", ground="meadow_grass",
                   defaults=FLOOR_DEFAULTS, rings=6, around=72, clip=False):
    """The trail (a ribbon along every path and side link, inside a verge of the network's own
    ground) and every section whose floor is not that ground (an ellipse just inside its rim)."""
    out = {}
    trail = []
    for p in layout.paths:
        pts = [q[:2] for q in p["points"]]
        if clip:
            # the ribbon stops at the rims of the two sections it joins, so it never crosses an
            # arena's floor (or the barrow standing in one)
            ends = [layout.sections[p["from"]], layout.sections[p["to"]]]
            dense = chaikin(pts)
            keep = [q for q in dense if all(ellipse_d(sec, np.array(q[0]), np.array(q[1])) > -0.5 for sec in ends)]
            if len(keep) < 2:
                continue
            pts = keep
        trail.append(ribbon(pts, max(2.5, p["width"] - 1.6), height_at, 0.06, trail_material))
    for side in layout.data.get("sides", []):
        trail.append(ribbon([side["from"][:2], side["at"]], max(2.0, side["width"] - 1.2), height_at, 0.06,
                            trail_material))
    out["Walk_trail"] = M.merge(trail, material=trail_material)
    for sid, sec in layout.sections.items():
        material = floors.get(sid, defaults.get(sec["kind"], ground))
        if material == ground:
            continue
        out[f"Walk_floor_{sid}"] = ellipse_floor(sec, 1.5 if sec["kind"] != "vault" else 0.8, height_at, 0.09,
                                                 material, rings=rings, around=around)
    return out


# ---------------------------------------------------------------- textures
def graded(texture_set, gain):
    """The toolkit's ground images are dark sRGB (meadow about 43,45,21), where the isles'
    Meshy ground is linear vertex colour at much the same numbers, so under the same sun the
    old textures drew about six times darker. Lift each to the isles' effective brightness."""
    base = np.clip(np.asarray(texture_set.base_color, dtype=np.float64) * np.array(gain), 0, 255)
    return dataclasses.replace(texture_set, base_color=base.astype(np.uint8))


def lifted(texture_set, floor=80.0, target=105.0, cap=4.5):
    """graded() for the regions' ground sets: a set darker than `floor` (mean of its channels)
    is lifted evenly to about `target`, the level the Harrowcrag Road's grading settled on."""
    mean = float(np.asarray(texture_set.base_color, dtype=np.float64).mean())
    if mean >= floor:
        return texture_set
    gain = min(cap, target / max(mean, 1.0))
    return graded(texture_set, (gain, gain, gain))


def recoloured(source, name, stops):
    """A ground set's structure (its own light and dark) in another palette, as
    textures.steppe_ground does for the steppe's dust and sward."""
    luminance = np.asarray(source.base_color, dtype=np.float64).mean(axis=2) / 255
    lo, hi = np.percentile(luminance, [2, 98])
    field = np.clip((luminance - lo) / max(hi - lo, 0.001), 0, 1)
    return T.TextureSet(name, T._u8(T._colorize(field, *stops)), source.orm, source.normal)


# Materials no region table has: (roughness, normal scale), drawn from REGION_TEXTURES by name.
CUSTOM_MATERIALS = {"red_sand": (0.98, 0.3), "red_rock": (0.92, 0.6), "red_mesa": (0.97, 0.3),
                    "heather_moor": (0.98, 0.3), "lilac_dust": (0.97, 0.3)}


REGION_TEXTURES = {
    "snow_pack": lambda: T.snow_pack(512), "glacier_ice": lambda: T.glacier_ice(512),
    "alpine_snowfield": lambda: T.alpine_ground("alpine_snowfield", 512),
    "alpine_blue_ice": lambda: T.alpine_ground("alpine_blue_ice", 512),
    "alpine_bedrock": lambda: T.alpine_ground("alpine_bedrock", 512),
    "alpine_turf": lambda: lifted(T.alpine_turf(512)),
    "steppe_dust": lambda: T.steppe_ground("steppe_dust", 512),
    "steppe_sward": lambda: T.steppe_ground("steppe_sward", 512),
    "grey_heather_moor": lambda: lifted(T.grey_heather_moor(512)), "grey_peat_bog": lambda: lifted(T.grey_peat_bog(512)),
    "grey_causeway": lambda: lifted(T.grey_causeway(512)), "grey_barrow_turf": lambda: lifted(T.grey_barrow_turf(512)),
    "grey_moor_granite": lambda: lifted(T.grey_moor_granite(512)), "grey_bog_timber": lambda: lifted(T.grey_bog_timber(512)),
    "grey_carved_stone": lambda: lifted(T.grey_carved_stone(512)), "grey_drystone": lambda: lifted(T.grey_drystone(512)),
    "grey_bog_water": lambda: T.grey_bog_water(512),
    "amethyst_barrens_dust": lambda: T.amethyst_barrens_dust(512),
    "amethyst_storm_rock": lambda: lifted(T.amethyst_storm_rock(512)),
    "amethyst_resonant_road": lambda: T.amethyst_resonant_road(512),
    "amethyst_crystal_field": lambda: T.amethyst_crystal_field(512),
    "amethyst_vault_floor": lambda: lifted(T.amethyst_vault_floor(512)),
    "amethyst_pale_stone": lambda: lifted(T.amethyst_pale_stone(512)), "amethyst_crystal": lambda: T.amethyst_crystal(256),
    "verdant_jungle_floor": lambda: lifted(T.verdant_jungle_floor(512)),
    "verdant_jungle_trail": lambda: lifted(T.verdant_jungle_trail(512)),
    "verdant_lagoon_sand": lambda: T.verdant_lagoon_sand(512),
    "verdant_limestone_cliff": lambda: lifted(T.verdant_limestone_cliff(512)),
    "verdant_terrace_stone": lambda: lifted(T.verdant_terrace_stone(512)),
    "verdant_mossy_stone": lambda: lifted(T.verdant_mossy_stone(512)),
    "verdant_jade": lambda: T.verdant_jade(512), "verdant_carved_jade": lambda: lifted(T.verdant_carved_jade(512)),
    "pale_ashlar": lambda: T.pale_ashlar(512), "veined_marble": lambda: T.veined_marble(512),
    "leaf_path": lambda: lifted(T.leaf_path(512)), "amber_resin": lambda: T.amber_resin(256),
    "lily_pad": lambda: T.lily_pad(256), "gilt_brass": lambda: T.gilt_brass(256),
    "hatchery_eggshell": lambda: T.hatchery_eggshell(256),
    # the red canyon's own: the toolkit's ground recipes recoloured to red sandstone
    "red_sand": lambda: recoloured(T.packed_earth(512, seed=739), "red_sand",
                                   ((0.0, (0.36, 0.17, 0.10)), (0.5, (0.62, 0.33, 0.20)), (1.0, (0.80, 0.50, 0.32)))),
    "red_rock": lambda: recoloured(T.cliff_rock(512, seed=67), "red_rock",
                                   ((0.0, (0.28, 0.12, 0.07)), (0.5, (0.54, 0.26, 0.15)), (1.0, (0.78, 0.46, 0.30)))),
    "heather_moor": lambda: recoloured(T.grey_heather_moor(512), "heather_moor",
                                       ((0.0, (0.20, 0.15, 0.18)), (0.5, (0.38, 0.28, 0.34)), (1.0, (0.56, 0.46, 0.46)))),
    "lilac_dust": lambda: recoloured(T.amethyst_barrens_dust(512), "lilac_dust",
                                     ((0.0, (0.30, 0.26, 0.34)), (0.5, (0.52, 0.46, 0.58)), (1.0, (0.70, 0.64, 0.76)))),
    "red_mesa": lambda: recoloured(T.meadow_grass(512, seed=733), "red_mesa",
                                   ((0.0, (0.40, 0.24, 0.12)), (0.5, (0.62, 0.42, 0.22)), (1.0, (0.78, 0.58, 0.34)))),
    "water_pool": lambda: T.water_surface(512, seed=89, tone="pool"),
    "water_lake": lambda: T.water_surface(512, seed=97, tone="lake"),
    "water_lagoon": lambda: T.water_surface(512, seed=101, tone="lagoon"),
    "water_sea": lambda: T.water_surface(512, seed=103, tone="sea"),
}


# ---------------------------------------------------------------- the build
def tile_of(layout, px, py):
    return [int(math.floor(px)), int(layout.H - 1 - math.floor(py))]


def world_of(layout, tile, height):
    return [tile[0] + 0.5, round(float(height), 3), layout.H - tile[1] - 0.5]


def polygon_ellipse(layout, sec, n=48, grow=0.0):
    cx, cy = sec["at"]
    r = math.radians(sec.get("rot", 0))
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        lx, ly = (sec["rx"] + grow) * math.cos(a), (sec["ry"] + grow) * math.sin(a)
        x = cx + lx * math.cos(r) - ly * math.sin(r)
        y = cy + lx * math.sin(r) + ly * math.cos(r)
        pts.append([round(x, 2), round(layout.H - y, 2)])
    return pts


def polygon_circle(layout, x, y, radius, n=24):
    return [[round(x + radius * math.cos(2 * math.pi * i / n), 2),
             round(layout.H - (y + radius * math.sin(2 * math.pi * i / n)), 2)] for i in range(n)]


def crag_meshes(layout, data, lattice, heights_mesh, quad_slope, tx, ty, qd, rd, floors, height_at, cls):
    """The Harrowcrag Road's ground: its woods, its crag, its cliffs, its river and its ford."""
    H, W = heights_mesh.shape[0] - 1, heights_mesh.shape[1] - 1
    river = data["river"]
    ford_sec = layout.sections[river["ford"]]
    quad_wet = rd.reshape(2 * H, 2 * W)[::2, ::2] < river["width"] / 2.0 + 0.5
    classes = np.zeros((H, W), np.int16)
    C_TRAIL = cls(1, "Walk_trail", "packed_earth")
    # Node names choose how the look pass paints them (LookGround.kind_of): Terrain_ is ground it
    # shades by slope and light, Walk_Terrain_ the same ground the client also stands actors on,
    # and a plain Walk_ (a road, a court, a ford) keeps its own texture.
    C_POCKET = cls(2, "Walk_Terrain_ground", "meadow_grass")
    C_FORD = cls(3, "Walk_ford", "shore_shingle")
    C_BANK = cls(10, "Terrain_woods", "meadow_grass")
    C_MEADOW = cls(11, "Terrain_crag", "meadow_grass")
    C_CLIFF = cls(12, "Terrain_cliff", "cliff_rock")
    C_BED = cls(13, "Terrain_riverbed", "shore_shingle")
    section_class = {}
    next_class = 20
    for sid, sec in layout.sections.items():
        material = floors.get(sid, {"camp": "packed_earth", "vault": "ashlar", "court": "cobble_paving"}.get(sec["kind"], "meadow_grass"))
        prefix = "Walk_Terrain_" if material == "meadow_grass" else "Walk_"
        section_class[sid] = cls(next_class, f"{prefix}{sid}", material)
        next_class += 1
    classes[:] = C_BANK
    on_crag = lattice["kc"][::2, ::2][:-1, :-1] < 1.0
    classes[on_crag] = C_MEADOW
    classes[quad_slope > 0.9] = C_CLIFF
    classes[quad_wet] = C_BED
    # the floor materials follow the route network, so the ground under a piece of cover keeps
    # its arena's floor; only the Walk_ nodes the client stands actors on are open tiles
    network = (qd <= 0) & ~(quad_wet & ~(ellipse_d(ford_sec, tx, ty) < -1.0))
    # the walkable network is meadow on the 1 m grid; the trail and the dirt, cobble and stone
    # floors are drawn over it as smooth overlays (overlay_meshes), so no edge steps with the grid
    classes[network] = C_POCKET
    classes[network & quad_wet] = C_FORD
    meshes = terrain_meshes(heights_mesh, classes, cls.names)
    meshes.update(overlay_meshes(layout, height_at, floors))

    # water surfaces: the river ribbon and the ford
    water = []
    pts = river["points"]
    for a, b in zip(pts, pts[1:]):
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        nx, ny = -math.sin(ang), math.cos(ang)
        half = river["width"] / 2.0 + 1.0

        def level(x, y):
            return ford_sec["elev"] + 0.02 if ellipse_d(ford_sec, np.array(x), np.array(y)) < 2.0 else DEEP_RIVER + 0.9

        ea, eb = level(*a), level(*b)
        quad = M.quad([(a[0] + nx * half, ea, a[1] + ny * half), (b[0] + nx * half, eb, b[1] + ny * half),
                       (b[0] - nx * half, eb, b[1] - ny * half), (a[0] - nx * half, ea, a[1] - ny * half)],
                      uv_scale=0.2, material="water_stream")
        if np.cross(np.subtract(quad.positions[1], quad.positions[0]), np.subtract(quad.positions[2], quad.positions[0]))[1] < 0:
            quad.flip_winding()
        water.append(quad)
    meshes["Water_river"] = M.merge(water, material="water_stream").sanitise_normals()
    colours = {C_CLIFF: (0.46, 0.45, 0.43), C_MEADOW: (0.44, 0.52, 0.32), C_BED: (0.33, 0.55, 0.66),
               C_FORD: (0.33, 0.55, 0.66)}
    return meshes, classes, colours


def land_meshes(layout, land, heights_mesh, quad_slope, tx, ty, qd, floors, height_at, cls):
    """A `land` route's ground: a node per kind of ground, the section floors over the network,
    and its water. Returns the meshes, the per-quad classes, the minimap's material per class
    (resolved to colours once the textures exist) and where water lies over the ground."""
    H, W = heights_mesh.shape[0] - 1, heights_mesh.shape[1] - 1
    g = land.spec.get("ground", {})
    bank = g.get("bank", "meadow_grass")
    network = g.get("network", bank)
    cliff = g.get("cliff", "cliff_rock")
    trail = g.get("trail", "packed_earth")
    cls(1, "Walk_trail", trail)
    C_POCKET = cls(2, "Walk_Terrain_ground", network)
    C_DECK = cls(3, "Walk_deck", g.get("deck", "timber_warm"))
    C_BANK = cls(10, "Terrain_ground", bank)
    C_MESA = cls(11, "Terrain_mesa", g.get("mesa", bank))
    C_CLIFF = cls(12, "Terrain_cliff", cliff)
    C_BED = cls(13, "Terrain_bed", g.get("bed", "shore_shingle"))
    C_CREV = cls(14, "Terrain_crevasse", g.get("crevasse", cliff))
    C_BUND = cls(15, "Terrain_bund", g.get("bund", bank))
    defaults = {**FLOOR_DEFAULTS, **land.spec.get("floorDefaults", {})}
    hq = (heights_mesh[:-1, :-1] + heights_mesh[1:, :-1] + heights_mesh[:-1, 1:] + heights_mesh[1:, 1:]) / 4.0
    f = land.features(tx, ty)
    net = (qd <= 0) & ~f["deep"]
    classes = np.full((H, W), C_BANK, np.int16)
    classes[land.mesa(tx, ty)] = C_MESA
    classes[quad_slope > 0.9] = C_CLIFF
    if land.spec.get("paddies"):
        classes[land.bunds(tx, ty) & (hq > land.water_level + 0.1)] = C_BUND
    water = (f["lake"] | f["river"] | f["canal"]) & ~(net & f["keep"])
    if land.water_mode:
        water |= hq < land.water_level - 0.02
    classes[water | f["dry"]] = C_BED
    classes[f["crevasse"] & ~f["keep"]] = C_CREV
    classes[net] = C_POCKET
    classes[net & f["keep"] & (f["river"] | f["canal"] | f["crevasse"] | f["lakeDeep"])] = C_DECK
    meshes = terrain_meshes(heights_mesh, classes, cls.names,
                            triplanar=("cliff_rock", cliff, g.get("crevasse", cliff)))
    # a finer floor than the crag's: these arenas lie on rougher ground, and a coarse ring
    # lets the ground show through between its rings
    meshes.update(overlay_meshes(layout, height_at, floors, trail, network, defaults, rings=18, around=120,
                                 clip=True))

    parts = defaultdict(list)

    def up(mesh):
        if mesh.normals is not None and len(mesh.normals) and np.cross(
                np.subtract(mesh.positions[1], mesh.positions[0]), np.subtract(mesh.positions[2], mesh.positions[0]))[1] < 0:
            mesh.flip_winding()
        return mesh

    minimap_water = np.zeros((H, W), bool)
    for kind, body in land.water_bodies():
        if kind == "plane":
            level = body["level"]
            material = land.spec.get("water", "water_lake")
            parts[material].append(up(M.quad([(0, level, 0), (W, level, 0), (W, level, H), (0, level, H)],
                                             uv_scale=0.05, material=material)))
            minimap_water |= hq < level - 0.02
        elif kind == "lake":
            material = body.get("material", land.spec.get("lakeWater", "water_pool"))
            parts[material].append(ellipse_floor(body, 0.0, lambda x, y, lv=body["level"]: lv, 0.0, material,
                                                 rings=3, around=48))
            minimap_water |= f["lake"]
        else:
            material = body.get("material", "water_stream")
            pts = body["points"]
            base = land.water_level if land.water_mode else 0.0
            for a, b in zip(pts, pts[1:]):
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                nx, ny = -math.sin(ang), math.cos(ang)
                half = body["width"] / 2.0 + 1.0
                ea = a[2] if len(a) > 2 else base
                eb = b[2] if len(b) > 2 else base
                parts[material].append(up(M.quad(
                    [(a[0] + nx * half, ea, a[1] + ny * half), (b[0] + nx * half, eb, b[1] + ny * half),
                     (b[0] - nx * half, eb, b[1] - ny * half), (a[0] - nx * half, ea, a[1] - ny * half)],
                    uv_scale=0.2, material=material)))
            minimap_water |= f["river"]
    for material, pieces in parts.items():
        meshes[f"Water_{material}"] = M.merge(pieces, material=material).sanitise_normals()
    colours = {C_BANK: bank, C_MESA: g.get("mesa", bank), C_CLIFF: cliff, C_BED: g.get("bed", "shore_shingle"),
               C_CREV: g.get("crevasse", cliff), C_BUND: g.get("bund", bank), "default": bank, "open": trail,
               "water": next(iter(parts), g.get("bed", "shore_shingle"))}
    return meshes, classes, colours, minimap_water


def build(route: str, server: Path, out_dir: Path | None = None, registry: bool = True):
    route_dir = GAUNTLETS / route
    source = route_dir / "source" / "layout.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    design_path = route_dir / "source" / "design.json"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    layout = Layout(data)
    W, H = layout.W, layout.H
    out = out_dir or (route_dir / "client")
    out.mkdir(parents=True, exist_ok=True)

    # terrain on a half-metre lattice; the mesh uses every second sample (1 m)
    lattice = build_terrain(layout, 0.5)
    heights_lattice = lattice["height"]

    def height_at(x, y):
        i = min(max(int(round(y * 2)), 0), heights_lattice.shape[0] - 1)
        j = min(max(int(round(x * 2)), 0), heights_lattice.shape[1] - 1)
        return float(heights_lattice[i, j])

    # half-metre cell centres: the collision frame
    hx = (np.arange(2 * W) + 0.5) * 0.5
    hy = (np.arange(2 * H) + 0.5) * 0.5
    cx, cy = np.meshgrid(hx, hy)
    hd, helev, howner, hnames, hkinds = layout.field(cx, cy)
    # heights at cell centres from the lattice (mean of the four corners)
    hl = heights_lattice
    cell_height = (hl[:-1, :-1] + hl[1:, :-1] + hl[:-1, 1:] + hl[1:, 1:]) / 4.0
    walk_half = (hd <= 0)
    land = lattice.get("land")
    if land is not None:
        # water, gaps and barrows the road does not cross on a deck close the ground
        walk_half &= ~land.features(cx, cy)["deep"]
    else:
        # the river outside the ford is deep water
        river = data["river"]
        rd = np.full(cx.shape, 1e9)
        for a, b in zip(river["points"], river["points"][1:]):
            dist, _ = seg_dist(cx, cy, a, b)
            rd = np.minimum(rd, dist)
        ford_sec = layout.sections[river["ford"]]
        wet = rd < river["width"] / 2.0
        deep = wet & ~(ellipse_d(ford_sec, cx, cy) < -1.0)
        walk_half &= ~deep

    dressing, dressing_path = load_dressing(route_dir)
    props = Props(height_at)
    builder = G.GltfBuilder(generator="Eloria trail gauntlet (gauntlets/_toolkit/build_trail.py)")
    root = G.Node(design["name"].replace(" ", "_"))
    kits = KitLibrary(builder)
    groups = {name: G.Node(f"Dress_{name}") for name in ("fort", "camp", "arena", "scenery", "road", "woods",
                                                       "cover", "objects")}
    dressing.dress(props, layout, lattice, kits, groups, dressing.kit_paths(CHECKOUT, route_dir))
    solid = solid_mask(props.solids, cx, cy) | kits.solid_mask(cx, cy)
    for kind, *spec in getattr(props, "clear", []):
        if kind == "ellipse":
            x, y, rx, ry = spec
            solid &= ~(((cx - x) / rx) ** 2 + ((cy - y) / ry) ** 2 <= 1.0)
        else:
            (ax, ay), (bx, by), width = spec
            dist, _ = seg_dist(cx, cy, (ax, ay), (bx, by))
            solid &= ~(dist <= width / 2.0)
    # the server's content contract holds every object tile walkable, whatever stands beside it
    for item in dressing.objects(layout, height_at)["interactives"]:
        tx, ty = item["serverTile"]
        row = (H - 1 - ty) * 2
        solid[row:row + 2, tx * 2:tx * 2 + 2] = False
    open_half = walk_half & ~solid
    if os.environ.get("TRAIL_DEBUG_DIR"):
        np.savez_compressed(Path(os.environ["TRAIL_DEBUG_DIR"]) / "masks.npz", solid=solid, walk=walk_half,
                            kit_solid=kits.solid_mask(cx, cy), prop_solid=solid_mask(props.solids, cx, cy))

    # served grid (server tiles, row 0 south) and the client EWCG grid
    sys.path.insert(0, str(server))
    from eloria import served_grid as SG
    half_heights_server = np.ascontiguousarray(cell_height[::-1])
    half_open_server = np.ascontiguousarray(open_half[::-1])
    grid = SG.fold(half_heights_server, half_open_server)
    codes = np.frombuffer(SG.little_endian_bytes(grid.codes), dtype="<u2").reshape(H, W)
    # islands the arrival cannot walk to (a prop pinching off a few tiles) are closed, so
    # every open tile is part of the road; then fold again so both grids agree
    arrival_plan = layout.sections[layout.order[0]]["at"]
    reach = reachable(codes, (int(arrival_plan[0]), int(H - 1 - math.floor(arrival_plan[1]))),
                      grid.climb_mm // grid.unit_mm)
    stray = (codes != 0) & ~reach
    if stray.any():
        half_open_server = half_open_server & ~np.repeat(np.repeat(stray, 2, axis=0), 2, axis=1)
        open_half = np.ascontiguousarray(half_open_server[::-1])
    served_bytes = SG.fold_and_encode(half_heights_server, half_open_server)
    (out / "served-grid.escg.gz").write_bytes(served_bytes)
    grid = SG.decode_file(served_bytes)
    codes = np.frombuffer(SG.little_endian_bytes(grid.codes), dtype="<u2").reshape(H, W)
    tile_open_server = codes != 0                          # [y, x], y north
    tile_open_plan = tile_open_server[::-1]                # [plan row, x]
    ew_codes, encoding = encode_heights(half_heights_server, half_open_server)
    (out / "collision.bin").write_bytes(struct.pack("<4sHHII", b"EWCG", 2, 0, 2 * W, 2 * H) + ew_codes.tobytes())

    # ---------------------------------------------------------- mesh
    heights_mesh = heights_lattice[::2, ::2]               # 1 m vertices, rows = plan y
    quad_open = tile_open_plan                              # quads == tiles (plan rows)
    tx, ty = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    qd, qelev, qowner, qnames, qkinds = layout.field(tx, ty)
    kind_of = np.array(qkinds)[qowner]
    name_of = np.array(qnames)[qowner]
    gy, gx = np.gradient(heights_mesh)
    slope = np.hypot(gx, gy)
    quad_slope = (slope[:-1, :-1] + slope[1:, :-1] + slope[:-1, 1:] + slope[1:, 1:]) / 4.0
    floors = data.get("floors", {})
    classes = np.zeros((H, W), np.int16)
    names_by_class = {}

    def cls(n, bucket, material):
        names_by_class[n] = (bucket, material)
        return n

    cls.names = names_by_class
    if land is not None:
        meshes, classes, class_colours, minimap_water = land_meshes(layout, land, heights_mesh, quad_slope, tx, ty,
                                                                    qd, floors, height_at, cls)
    else:
        meshes, classes, class_colours = crag_meshes(layout, data, lattice, heights_mesh, quad_slope, tx, ty, qd, rd,
                                                     floors, height_at, cls)
        minimap_water = None

    by_bucket = defaultdict(list)
    for bucket, piece in props.pieces:
        by_bucket[(bucket, piece.material)].append(piece)
    for (bucket, material), pieces in sorted(by_bucket.items()):
        meshes[f"{bucket}_{material}"] = M.merge(pieces, material=material).drop_degenerate().sanitise_normals()
    used = {m.material for m in meshes.values()}
    flat = {
        "gb_canopy": G.Material("gb_canopy", base_color=(0.16, 0.30, 0.13, 1), roughness=0.95),
        "gb_canopy_broad": G.Material("gb_canopy_broad", base_color=(0.27, 0.40, 0.15, 1), roughness=0.95),
        "gb_trunk": G.Material("gb_trunk", base_color=(0.30, 0.21, 0.13, 1), roughness=1.0),
        "gb_waystone": G.Material("gb_waystone", base_color=(0.42, 0.52, 0.72, 1), roughness=0.6, emissive=(0.05, 0.09, 0.2)),
        "gb_fire": G.Material("gb_fire", base_color=(1, 0.5, 0.12, 1), emissive=(1.0, 0.42, 0.06)),
        "gb_banner": G.Material("gb_banner", base_color=(0.55, 0.10, 0.08, 1), roughness=0.9, double_sided=True),
        "gb_hay": G.Material("gb_hay", base_color=(0.78, 0.66, 0.33, 1), roughness=1.0),
        "gb_barn": G.Material("gb_barn", base_color=(0.55, 0.20, 0.14, 1), roughness=0.95),
        "gb_cache": G.Material("gb_cache", base_color=(0.62, 0.48, 0.18, 1), metallic=0.4, roughness=0.5),
    }
    factories = {
        "packed_earth": lambda: graded(T.packed_earth(512, seed=223), (1.95, 1.9, 1.85)),
        "forest_floor": lambda: T.forest_floor(512, seed=71),
        "meadow_grass": lambda: graded(T.meadow_grass(512, seed=131), (2.35, 2.75, 2.7)),
        "cliff_rock": lambda: graded(T.cliff_rock(512, seed=67), (3.4, 3.45, 3.45)),
        "shore_shingle": lambda: graded(T.shore_shingle(512, seed=113), (4.2, 4.3, 4.4)),
        "ashlar": lambda: T.ashlar(512, seed=53),
        "cobble_paving": lambda: graded(T.cobble_paving(512, seed=83), (2.0, 2.0, 2.0)),
        "rubble_stone": lambda: T.rubble_stone(512, seed=61),
        "timber_warm": lambda: T.timber(512, seed=23, tone="warm"), "timber_dark": lambda: T.timber(512, seed=173, tone="dark"),
        "thatch_reed": lambda: T.thatch_reed(512, seed=107), "canvas_awning": lambda: T.canvas_awning(256, seed=139),
        "slate_roof": lambda: T.slate_roof(512, seed=439), "dark_iron": lambda: T.dark_iron(256, seed=101),
        "water_stream": lambda: T.water_surface(512, seed=89, tone="pool"),
        "scorched_ground": lambda: T.scorched_ground(512, seed=109),
    }
    factories.update({k: v for k, v in REGION_TEXTURES.items() if k not in factories})
    # a material names the texture set it draws (materials.py SPECS): most share their name
    wanted = sorted({MAT.BY_NAME[m].texture if m in MAT.BY_NAME else m for m in used - set(flat)})
    missing = sorted(t for t in wanted if t not in factories)
    if missing:
        raise SystemExit(f"no texture for {missing}")
    textures = {}
    for name in wanted:
        texture_set = factories[name]()
        # the image names come from the set's own name; the material names the set it wants
        textures[name] = texture_set if texture_set.name == name else dataclasses.replace(texture_set, name=name)
    MAT.register_gltf_materials(builder, {k: v for k, v in textures.items()}, only=used - set(flat))
    for name in sorted(used & set(CUSTOM_MATERIALS)):
        roughness, normal_scale = CUSTOM_MATERIALS[name]
        images = textures[name].images()
        for image, blob in images.items():
            builder.add_image(image, blob)
        builder.add_material(G.Material(name=name, base_color=(1.0, 1.0, 1.0, 1.0), metallic=0.0, roughness=roughness,
                                        base_color_texture=f"{name}_basecolor", orm_texture=f"{name}_orm",
                                        normal_texture=f"{name}_normal" if f"{name}_normal" in images else None,
                                        normal_scale=normal_scale))
    for name, material in flat.items():
        if name in used:
            builder.add_material(material)
    walk_nodes = []
    all_meshes = []
    for name, mesh in sorted(meshes.items()):
        if mesh.vertex_count == 0:
            continue
        mesh = mesh.sanitise_normals()
        builder.add_mesh(name, mesh, with_tangents=mesh.material not in flat)
        root.add(G.Node(name, mesh=name))
        all_meshes.append(mesh)
        if name.startswith("Walk_"):
            walk_nodes.append(name)
    for group in groups.values():
        if group.children:
            root.add(group)
    builder.add_node(root)
    builder.write_glb(str(out / "world.glb"))
    bounds = M.merge(all_meshes).bounds()

    # ---------------------------------------------------------- markers and the gauntlet block
    def open_tiles_in(mask_plan):
        ys_, xs_ = np.nonzero(mask_plan & tile_open_plan)
        return [[int(x), int(H - 1 - y)] for y, x in zip(ys_, xs_)]

    def nearest_first(tiles, centre_plan):
        cxp, cyp = centre_plan
        return sorted(tiles, key=lambda t: (math.hypot(t[0] + 0.5 - cxp, (H - t[1] - 0.5) - cyp), t[0], t[1]))

    arrival = layout.sections[layout.order[0]]
    arrival_tile = tile_of(layout, *arrival["at"])
    sections_out = []
    for sid in layout.order:
        sec = layout.sections[sid]
        if sec["kind"] not in ("arena", "court"):
            continue
        area_mask = ellipse_d(sec, tx, ty) <= 0
        mouths = []
        for m in layout.mouths:
            if m["section"] != sid:
                continue
            if m["kind"] == "floor":
                rr = np.hypot(tx - sec["at"][0], ty - sec["at"][1])
                ring = (rr >= m["ring"][0]) & (rr <= m["ring"][1])
                spawn = nearest_first(open_tiles_in(ring), sec["at"])
                mouths.append({"id": m["id"], "kind": "floor", "tile": tile_of(layout, *sec["at"]), "spawnTiles": spawn})
                continue
            pocket = np.hypot(tx - m["at"][0], ty - m["at"][1]) <= m["radius"] + 0.5
            spawn = nearest_first(open_tiles_in(pocket), sec["at"])
            mouths.append({"id": m["id"], "kind": m["kind"], "tile": tile_of(layout, *m["at"]), "spawnTiles": spawn})
        sections_out.append({
            "id": sid, "order": sec.get("order"), "kind": sec["kind"], "name": sec["name"],
            "area": polygon_ellipse(layout, sec), "areaTiles": int((area_mask & tile_open_plan).sum()),
            "centre": tile_of(layout, *sec["at"]), "mouths": mouths})
    starved = [s["id"] for s in sections_out if s["areaTiles"] < 0.4 * math.pi * layout.sections[s["id"]]["rx"]
               * layout.sections[s["id"]]["ry"]]
    if starved:
        raise SystemExit(f"{route}: little or no open ground the arrival reaches in {starved}: something walls the road")
    vault = layout.sections["vault"]
    objects = dressing.objects(layout, height_at)
    checkpoints = []
    for cp in data.get("checkpoints", []):
        near = np.hypot(tx - cp["at"][0], ty - cp["at"][1]) <= 6.0
        checkpoints.append({"id": cp["id"], "name": cp["name"], "after": cp["after"],
                            "tile": tile_of(layout, *cp["at"]),
                            "reach": polygon_circle(layout, cp["at"][0], cp["at"][1], cp.get("reach", 9.0)),
                            "respawnTiles": nearest_first(open_tiles_in(near), cp["at"])[:24]})
    sides = []
    for side in data.get("sides", []):
        sides.append({"id": side["id"], "name": side["name"], "tile": tile_of(layout, *side["at"]),
                      "nodeTile": objects["sideTiles"][side["id"]]["node"], "plaqueTile": objects["sideTiles"][side["id"]]["plaque"]})
    # the route: the served grid's shortest walk from the arrival through every section's
    # centre to the vault, so every tile on it is one a walker really stands on
    stops = [arrival_tile] + [s["centre"] for s in sections_out] + [tile_of(layout, *vault["at"])]
    route_tiles = []
    climb = grid.climb_mm // grid.unit_mm
    for a, b in zip(stops, stops[1:]):
        leg = shortest_path(codes, nearest_open(codes, a), nearest_open(codes, b), climb)
        if not leg:
            raise SystemExit(f"no walk from {a} to {b}")
        route_tiles.extend(leg if not route_tiles else leg[1:])
    gauntlet = {
        "schema": SCHEMA, "id": design["id"], "style": "trail", "name": design["name"], "short": design["short"],
        "serverCells": [W, H], "arrival": {"tile": arrival_tile},
        "objects": {k: v for k, v in objects.items() if k != "sideTiles" and k != "interactives"},
        "sections": sections_out, "sides": sides, "checkpoints": checkpoints,
        "vault": {"area": polygon_ellipse(layout, vault), "centre": tile_of(layout, *vault["at"])},
        "route": route_tiles,
    }

    coordinate = {"metresPerTile": 1.0, "serverOrigin": [0, H], "serverCells": [W, H], "origin": [0, 0, 0],
                  "walkingHeight": 0.0, "invertServerY": True, "serverStorageVersion": 1, "serverTileMin": [0, 0]}
    spawns = [{"id": "default", "name": arrival["name"], "default": True,
               "position": world_of(layout, arrival_tile, height_at(*arrival["at"]) + 0.05),
               "serverTile": arrival_tile, "rotationDegrees": 300}]
    vault_tile = tile_of(layout, *vault["at"])
    spawns.append({"id": "vault", "name": vault["name"], "default": False,
                   "position": world_of(layout, vault_tile, height_at(*vault["at"]) + 0.05),
                   "serverTile": vault_tile, "rotationDegrees": 90})
    interactives = []
    for item in objects["interactives"]:
        tile = item["serverTile"]
        interactives.append({**item, "position": world_of(layout, tile, height_at(tile[0] + 0.5, H - tile[1] - 0.5) + 1.0)})
    landmarks = [{"id": sid, "name": sec["name"], "position": world_of(layout, tile_of(layout, *sec["at"]), height_at(*sec["at"]))}
                 for sid, sec in layout.sections.items()]
    manifest = {
        "schemaVersion": "1.1.0", "assetVersion": "0.1.0",
        "asset": {"id": design["id"], "name": design["name"], "glb": "world.glb", "units": "meters",
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"}, "origin": [0, 0, 0],
                  "bounds": {"min": bounds[0].tolist(), "max": bounds[1].tolist()}, "interiorClass": "gauntlet-trail",
                  "serverCells": [W, H]},
        "coordinateTransform": coordinate, "serverCells": [W, H], "spawnPoints": spawns,
        "landmarks": landmarks, "interactives": interactives, "portals": [], "harvestables": [],
        "navigation": {"surfaceNodePrefixes": ["Walk_"], "authority": "server", "defaultSpawn": "default"},
        "collision": {"binary": "collision.bin", "format": "EWCG-v2", "width": 2 * W, "height": 2 * H,
                      "cellMetres": 0.5, "originMetres": [0, H], "heightEncoding": encoding,
                      "gridAlignment": "tile-centres-v1", "sha256": sha(out / "collision.bin"), "nodeNames": walk_nodes,
                      "rowOrder": "south-to-north",
                      "servedGrid": {"binary": "served-grid.escg.gz", "format": "ESCG-v2", "sha256": sha(out / "served-grid.escg.gz"),
                                     "unitMetres": 0.05, "climbMetres": 1.0, "originMetres": -100.0, "width": W, "height": H,
                                     "walkableTiles": int(tile_open_server.sum())}},
        "environment": data.get("environment") or {
            "sky": {"topColor": [0.30, 0.47, 0.70], "horizonColor": [0.86, 0.76, 0.58],
                    "groundBottomColor": [0.18, 0.20, 0.14], "groundHorizonColor": [0.55, 0.52, 0.40]},
            "sun": {"enabled": True, "direction": [0.55, -0.62, 0.56], "color": [1.0, 0.90, 0.74], "energy": 1.7},
            "ambient": {"color": [0.66, 0.70, 0.76], "energy": 0.85, "skyContribution": 0.35},
            "fog": {"enabled": True, "color": [0.80, 0.74, 0.62], "density": 0.0006},
            "tonemap": {"mode": "filmic", "exposure": 1.0, "white": 4.0}},
        "lighting": {"markers": props.lights},
        "minimap": {"file": "minimap.webp", "image": "minimap.webp", "northUp": True, "worldMin": [0, 0],
                    "worldMax": [W, H], "imageSize": [2 * W, 2 * H]},
        "gauntlet": gauntlet,
        "productionStatus": "grey-box",
        "provenance": {"layout": f"gauntlets/{route}/source/layout.json", "layoutSha256": sha(source),
                       "design": f"gauntlets/{route}/source/design.json", "designSha256": sha(design_path),
                       "dressing": f"gauntlets/{route}/source/dressing.py", "dressingSha256": sha(dressing_path),
                       "builder": TOOL, "builderSha256": sha(__file__)},
    }
    write_json(out / "world.json", manifest)

    # ---------------------------------------------------------- minimap (north up, 2 px per tile)
    hm = heights_mesh[:-1, :-1]
    gy2, gx2 = np.gradient(hm)
    az, alt = math.radians(315), math.radians(45)
    sl = np.arctan(np.hypot(gx2, gy2))
    asp = np.arctan2(-gx2, gy2)
    shade = np.clip(np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp), 0, 1)
    if minimap_water is None:
        base = np.where(quad_open[..., None], np.array([0.78, 0.68, 0.48]), np.array([0.30, 0.40, 0.26]))
        for cls_id, colour in class_colours.items():
            base = np.where((classes == cls_id)[..., None], np.array(colour), base)
    else:
        # every ground in its own material's colour, the water over it, and the road on top
        def colour_of(material):
            if material in flat:
                return np.array(flat[material].base_color[:3])
            spec = MAT.BY_NAME.get(material)
            texture = spec.texture if spec else material
            tint = np.array(spec.base_color[:3]) if spec else np.ones(3)
            mean = np.asarray(textures[texture].base_color, dtype=np.float64).reshape(-1, 3).mean(0) / 255
            return np.clip(mean * tint, 0, 1)

        class_colours = {k: colour_of(v) for k, v in class_colours.items()}
        # water textures are deep tints meant to be seen through: on the map they read as holes
        class_colours["water"] = np.clip(class_colours["water"] * 2.2 + np.array([0.05, 0.12, 0.18]), 0, 1)
        base = np.broadcast_to(np.array(class_colours["default"]), (H, W, 3)).copy()
        for cls_id, colour in class_colours.items():
            if isinstance(cls_id, int):
                base = np.where((classes == cls_id)[..., None], np.array(colour), base)
        base = np.where(minimap_water[..., None], np.array(class_colours["water"]), base)
        base = np.where(quad_open[..., None], np.array(class_colours["open"]), base)
    rgb = np.clip(base * (0.45 + 0.7 * shade[..., None]), 0, 1)
    image = Image.fromarray((rgb * 255).astype(np.uint8)).resize((2 * W, 2 * H), Image.NEAREST)
    image.save(out / "minimap.webp", lossless=True)

    if registry:
        reg_path = CHECKOUT / "godot-client/data/maps/registry.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        rel = out.relative_to(CHECKOUT).as_posix()
        reg["maps"][design["id"]] = {"manifest": f"res://../{rel}/world.json", "coordinateTransform": coordinate,
                                     "status": "trail-gauntlet-greybox", "label": design["name"],
                                     "landscapeTransitions": False, "gauntlet": True}
        for n in range(2, design.get("copies", 3) + 1):
            reg["maps"][f"{design['id']}_{n}"] = {"alias": design["id"]}
        write_json(reg_path, reg)

    summary = {"route": design["id"], "walkableTiles": int(tile_open_server.sum()),
               "glbBytes": (out / "world.glb").stat().st_size, "kitModels": len(kits.kits),
               "kitPlacements": kits.placements, "kitTriangles": kits.triangles, "dressing": props.counts,
               "triangles": int(sum(m.triangle_count for m in all_meshes)),
               "sections": {s["id"]: {"areaTiles": s["areaTiles"], "mouths": {m["id"]: len(m["spawnTiles"]) for m in s["mouths"]}}
                            for s in sections_out},
               "heightRange": [round(float(cell_height[open_half].min()), 2), round(float(cell_height[open_half].max()), 2)]}
    print(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("route")
    ap.add_argument("--server", type=Path, required=True, help="an eloria-server checkout (eloria.served_grid)")
    ap.add_argument("--out", type=Path, help="write the package here instead of <route>/client")
    ap.add_argument("--no-registry", action="store_true", help="leave godot-client/data/maps/registry.json alone")
    args = ap.parse_args()
    build(args.route, args.server.resolve(), args.out, registry=not args.no_registry)
