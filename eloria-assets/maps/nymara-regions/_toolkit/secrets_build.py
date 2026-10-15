#!/usr/bin/env python3
"""Compose a region's secrets onto one map and write the package.

    python _toolkit/secrets_build.py <region> [--out DIR] [--seed N]

Reads `<region>/source/secrets_design.py` - `REGION`, `NAME`, `PALETTE`,
`SECRETS` - builds every secret with `secretrooms`, lays the rooms out on a
64-tile map with at least twenty metres of void between any two, and writes
`interiors/<region>_secrets/{world.glb,world.json,collision.bin}` plus the
server walk grid `server-collision/<region>_secrets.bin`.

The GLB carries one node per section and material (`Walk_<section>_<mat>`,
`Build_<section>_<mat>`, `Roof_<section>_<mat>`), which is what lets the
client show a player only the secret they are in and black out the rest.
The manifest's `secrets` block is what the server tools read: each section's
arrival tile, the tiles its areas and spawns cover, its harvest nodes and
interactives, and the exits its stones and tunnels open.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import preview                                  # noqa: E402
import validate_gltf                            # noqa: E402
from amberwood import gltf as GLTF              # noqa: E402
from amberwood import materials as MAT          # noqa: E402
from amberwood import mesh as M                 # noqa: E402
from amberwood import stonework as S            # noqa: E402
from amberwood.interiors import Interior        # noqa: E402
import export_insides_collision as EXPORT       # noqa: E402
import secretrooms as SR                        # noqa: E402

TILES = 64                 # server tiles; 384 m
CELL = 72.0                # layout slot, metres
GUTTER = 20.0              # least void between two sections
COLLISION_CELL = 0.5
SERVER_STEP = 0.2            # the elevation step the server reads its walk grids in
MAP_SPAN = TILES * 6.0


def load_design(region: str):
    path = ROOT / region / "source" / "secrets_design.py"
    if not path.is_file():
        # a map with no region source folder of its own (Four Gates) keeps its
        # design beside the toolkit
        path = HERE / "designs" / f"{region}_secrets_design.py"
    spec = importlib.util.spec_from_file_location(f"{region}_secrets_design", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ layout
def _footprint(piece: Interior):
    lo, hi = piece.group.walk_bounds()
    return float(lo[0]), float(lo[2]), float(hi[0]), float(hi[2])


def layout(pieces: list[Interior]) -> dict[str, tuple[float, float]]:
    """Slot each room on a grid; a long room takes the rows it needs."""
    slots = int(MAP_SPAN // CELL)          # 5 x 5
    taken = set()
    offsets = {}
    order = sorted(pieces, key=lambda p: -(_footprint(p)[3] - _footprint(p)[1]))
    for piece in order:
        x0, z0, x1, z1 = _footprint(piece)
        rows = max(1, math.ceil((z1 - z0 + GUTTER) / CELL))
        cols = max(1, math.ceil((x1 - x0 + GUTTER) / CELL))
        placed = False
        for row in range(slots):
            for col in range(slots):
                cells = {(col + i, row + j) for i in range(cols) for j in range(rows)}
                if any(c >= slots or r >= slots for c, r in cells) or cells & taken:
                    continue
                taken |= cells
                # the room's local origin (its landing) sits a little in from
                # the slot's south-west corner; the room extends north from it
                dx = 8.0 + col * CELL - x0 + GUTTER * 0.5
                dz = 8.0 + row * CELL - z0 + GUTTER * 0.5
                offsets[piece.ident] = (round(dx, 2), round(dz, 2))
                placed = True
                break
            if placed:
                break
        if not placed:
            raise SystemExit(f"no room on a {TILES}-tile map for {piece.ident}")
    return offsets


def assert_gutters(footprints: dict[str, tuple]) -> None:
    keys = list(footprints)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ax0, az0, ax1, az1 = footprints[a]
            bx0, bz0, bx1, bz1 = footprints[b]
            gap = max(max(bx0 - ax1, ax0 - bx1), max(bz0 - az1, az0 - bz1))
            if gap < GUTTER:
                raise SystemExit(f"secrets {a!r} and {b!r} are only {gap:.1f} m apart")


# ------------------------------------------------------------------ export
def export_glb(sections: list[tuple[str, S.MeshGroup]], sets, path: Path, package_id: str):
    builder = GLTF.GltfBuilder(generator="Eloria secrets builder")
    used = {piece.material for _, group in sections for piece in group.all_parts}
    MAT.register_gltf_materials(builder, sets, only=used)
    root = GLTF.Node(name=f"Secrets_{package_id}")

    def emit(bucket, prefix, parent):
        for material, piece in sorted(bucket.items()):
            piece = piece.drop_degenerate().sanitise_normals()
            if piece.triangle_count == 0:
                continue
            name = f"{prefix}_{material}"
            builder.add_mesh(name, piece, with_tangents=True)
            parent.add(GLTF.Node(name=name, mesh=name))

    for ident, group in sections:
        node = GLTF.Node(name=f"Section_{ident}")
        emit(group.by_material(overhead=True), f"Roof_{ident}", node)
        emit(group.by_material(walk=False), f"Build_{ident}", node)
        emit(group.by_material(walk=True), f"Walk_{ident}", node)
        root.add(node)
    builder.add_node(root)
    size = builder.write_glb(str(path))
    stats = builder.statistics()
    stats["glbBytes"] = size
    stats["nodeNames"] = [n["name"] for n in builder.to_json()["nodes"]]
    return stats


def build_collision(group: S.MeshGroup, keep_open=(), *, non_blocking_materials=()):
    """The half-metre walk grid of the whole map (EWCG v1), as the insides do.

    `keep_open` is the positions of the things a player uses or harvests - a
    waystone, a cache, a node, a plaque. The tile each stands on stays
    walkable through the obstacle pass, because the server's content contract
    holds every such coordinate walkable and the sync tool opens them anyway;
    a body standing in a chest is the price, as it is everywhere else."""
    lo, hi = group.walk_bounds()
    x0 = math.floor(float(lo[0])) - 2
    z1 = math.ceil(float(hi[2])) + 2
    width = int(math.ceil((math.ceil(float(hi[0])) + 2 - x0) / COLLISION_CELL))
    height = int(math.ceil((z1 - (math.floor(float(lo[2])) - 2)) / COLLISION_CELL))
    width -= width % 6
    height -= height % 6
    walkable = np.zeros((height, width), dtype=bool)
    tops = np.full((height, width), np.nan)
    for piece in group.walk_parts:
        tri = piece.positions[piece.indices].reshape(-1, 3, 3)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = lengths > 1e-9
        tri, normals, lengths = tri[keep], normals[keep], lengths[keep]
        tri = tri[(normals[:, 1] / lengths) > 0.55]
        if len(tri) == 0:
            continue
        cx0 = np.clip(np.floor((tri[:, :, 0].min(axis=1) - x0) / COLLISION_CELL), 0, width - 1).astype(int)
        cx1 = np.clip(np.floor((tri[:, :, 0].max(axis=1) - x0) / COLLISION_CELL), 0, width - 1).astype(int)
        cz0 = np.clip(np.floor((z1 - tri[:, :, 2].max(axis=1)) / COLLISION_CELL), 0, height - 1).astype(int)
        cz1 = np.clip(np.floor((z1 - tri[:, :, 2].min(axis=1)) / COLLISION_CELL), 0, height - 1).astype(int)
        peak = tri[:, :, 1].max(axis=1)
        for i in range(len(tri)):
            zs = np.arange(cz0[i], cz1[i] + 1)
            xs = np.arange(cx0[i], cx1[i] + 1)
            if zs.size == 0 or xs.size == 0:
                continue
            px = x0 + (xs + 0.5) * COLLISION_CELL
            pz = z1 - (zs + 0.5) * COLLISION_CELL
            gx, gz = np.meshgrid(px, pz)
            a, b, c = tri[i, 0], tri[i, 1], tri[i, 2]
            d = ((b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]))
            if abs(d) < 1e-12:
                continue
            w0 = ((b[2] - c[2]) * (gx - c[0]) + (c[0] - b[0]) * (gz - c[2])) / d
            w1 = ((c[2] - a[2]) * (gx - c[0]) + (a[0] - c[0]) * (gz - c[2])) / d
            inside = (w0 >= 0.0) & (w1 >= 0.0) & (w0 + w1 <= 1.0)
            if not inside.any():
                continue
            walkable[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1] |= inside
            heights = tops[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1]
            np.copyto(heights, peak[i], where=inside & (np.isnan(heights) | (heights < peak[i])))
    # What stands on a floor and is not a floor - a pillar, a boulder, a
    # crate, a wall's own face - blocks the cells it stands over or within
    # `reach` of, through the band a body occupies above the walk surface
    # there. The grid used to know only where floor was, so a creature could
    # stand in a pillar and a wave could land inside a boulder. Faces above
    # head height (a vault, a lintel) and below the floor (a pit's water) are
    # not in the band and block nothing.
    band_low, band_high, reach = 0.15, 1.9, 0.3
    obstacle = np.zeros((height, width), dtype=bool)
    for piece in group.parts:
        # Explicit liquid scenery can cover a real walk floor without becoming
        # a solid obstacle. It cannot create ground or reopen a gate cut.
        if piece.material in non_blocking_materials:
            continue
        tri = piece.positions[piece.indices].reshape(-1, 3, 3)
        if len(tri) == 0:
            continue
        cx0 = np.clip(np.floor((tri[:, :, 0].min(axis=1) - reach - x0) / COLLISION_CELL), 0, width - 1).astype(int)
        cx1 = np.clip(np.floor((tri[:, :, 0].max(axis=1) + reach - x0) / COLLISION_CELL), 0, width - 1).astype(int)
        cz0 = np.clip(np.floor((z1 - tri[:, :, 2].max(axis=1) - reach) / COLLISION_CELL), 0, height - 1).astype(int)
        cz1 = np.clip(np.floor((z1 - tri[:, :, 2].min(axis=1) + reach) / COLLISION_CELL), 0, height - 1).astype(int)
        y_low = tri[:, :, 1].min(axis=1)
        y_high = tri[:, :, 1].max(axis=1)
        for i in range(len(tri)):
            zs = np.arange(cz0[i], cz1[i] + 1)
            xs = np.arange(cx0[i], cx1[i] + 1)
            if zs.size == 0 or xs.size == 0:
                continue
            local = tops[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1]
            band = ~np.isnan(local) & (y_low[i] <= local + band_high) & (y_high[i] >= local + band_low)
            if not band.any():
                continue
            gx, gz = np.meshgrid(x0 + (xs + 0.5) * COLLISION_CELL, z1 - (zs + 0.5) * COLLISION_CELL)
            a, b, c = tri[i, 0], tri[i, 1], tri[i, 2]
            near = np.zeros(gx.shape, dtype=bool)
            for p, q in ((a, b), (b, c), (c, a)):
                dx, dz = q[0] - p[0], q[2] - p[2]
                length = dx * dx + dz * dz
                t = np.clip(((gx - p[0]) * dx + (gz - p[2]) * dz) / length, 0.0, 1.0) if length > 1e-12 else 0.0
                near |= np.hypot(gx - (p[0] + t * dx), gz - (p[2] + t * dz)) <= reach
            d = ((b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]))
            if abs(d) > 1e-12:
                w0 = ((b[2] - c[2]) * (gx - c[0]) + (c[0] - b[0]) * (gz - c[2])) / d
                w1 = ((c[2] - a[2]) * (gx - c[0]) + (a[0] - c[0]) * (gz - c[2])) / d
                near |= (w0 >= 0.0) & (w1 >= 0.0) & (w0 + w1 <= 1.0)
            obstacle[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1] |= band & near
    walkable &= ~obstacle
    for position in keep_open:
        tx, tz = int(round(position[0] - x0)), int(round(z1 - position[2]))
        rows, cols = slice(max(2 * tz - 1, 0), 2 * tz + 1), slice(max(2 * tx - 1, 0), 2 * tx + 1)
        walkable[rows, cols] |= ~np.isnan(tops[rows, cols])
    surfaces = tops[~np.isnan(tops)]
    low, high = (float(surfaces.min()), float(surfaces.max())) if surfaces.size else (0.0, 0.0)
    # The server walks in 0.2 m steps and allows two of them between tiles.
    # A grid encoded in some other step is re-quantised to that on the way to
    # the server, and two roundings can turn a 0.375 m riser into three of
    # its steps: the Ice Stair's, fitted at 0.1066 m, came out 0.43 m and shut.
    # So the server's own step is used whenever the relief fits in it, and a
    # fitted one only when it does not (the six-bit byte holds 61 steps).
    span = high - low
    step = SERVER_STEP if span <= SERVER_STEP * 61.0 else max(0.1, span / 61.0)
    origin = low - step
    codes = np.clip(np.round((tops - origin) / step), 1, 63)
    grid = np.where(walkable & ~np.isnan(tops), codes, 0).astype(np.uint8)
    walkable &= grid > 0
    payload = struct.pack("<4sHHII", b"EWCG", 1, 0, width, height) + grid.tobytes()
    stats = {"binary": "collision.bin", "format": "EWCG-v1", "width": width, "height": height,
             "cellMetres": COLLISION_CELL, "originMetres": [float(x0), float(z1)],
             "heightEncoding": {"origin": round(origin, 3), "step": round(step, 4), "range": [1, 63],
                                "zeroMeansBlocked": True},
             "walkableCells": int(walkable.sum()), "blockedCells": int((~walkable).sum()),
             "walkableFraction": round(float(walkable.mean()), 4),
             "rowOrder": "server-tile-y (row 0 is the +Z southern edge)",
             "columnOrder": "server-tile-x (column 0 is the -X western edge)"}
    return payload, stats


# ---------------------------------------------------------------- compose
def _move(point, dx, dz):
    return [round(float(point[0]) + dx, 2), round(float(point[1]), 2), round(float(point[2]) + dz, 2)]


def compose(design, seed: int):
    region = design.REGION
    package_id = f"{region}_secrets"
    palette = design.PALETTE
    pieces = []
    for index, secret in enumerate(design.SECRETS):
        if secret.kind == "mouth":
            continue                     # an entrance on this region into another map's room
        pieces.append(SR.build(secret, palette, seed=seed + index * 17))
    offsets = layout(pieces)
    combined = Interior(package_id, design.NAME, "secrets", "", [0.0, 0.0, 0.0], "default")
    groups = []
    footprints = {}
    sections = []
    for piece in pieces:
        dx, dz = offsets[piece.ident]
        group = piece.group.transformed(M.translation(dx, 0.0, dz))
        groups.append((piece.ident, group))
        combined.group.add(group)
        x0, z0, x1, z1 = _footprint(piece)
        footprints[piece.ident] = (x0 + dx, z0 + dz, x1 + dx, z1 + dz)
        spaces = {}
        for key, space in piece.spaces.items():
            spaces[f"{piece.ident}.{key}"] = {
                "x0": round(space["x0"] + dx, 2), "z0": round(space["z0"] + dz, 2),
                "x1": round(space["x1"] + dx, 2), "z1": round(space["z1"] + dz, 2),
                "floor": round(space["floor"], 2), "height": round(space["height"], 2)}
        combined.spaces.update(spaces)
        for entry in piece.landmarks:
            entry = dict(entry); entry["position"] = _move(entry["position"], dx, dz)
            entry["section"] = piece.ident; entry["space"] = f"{piece.ident}.{entry['space']}"
            combined.landmarks.append(entry)
        for source, target in ((piece.interactives, combined.interactives),
                               (piece.harvestables, combined.harvestables),
                               (piece.npc_markers, combined.npc_markers)):
            for entry in source:
                entry = dict(entry); entry["position"] = _move(entry["position"], dx, dz)
                entry["section"] = piece.ident
                target.append(entry)
        combined.lamps.extend(_move(p, dx, dz) for p in piece.lamps)
        combined.open_to_sky.extend(f"{piece.ident}.{k}" for k in piece.open_to_sky)
        entrance = spaces[f"{piece.ident}.{piece.entrance_space}"]
        arrival = [round((entrance["x0"] + entrance["x1"]) * 0.5, 2), round(entrance["floor"] + 0.05, 2),
                   round((entrance["z0"] + entrance["z1"]) * 0.5, 2)]
        own = [v for k, v in spaces.items()]
        bounds = {"min": [round(min(s["x0"] for s in own) - 1.0, 2), round(min(s["z0"] for s in own) - 1.0, 2)],
                  "max": [round(max(s["x1"] for s in own) + 1.0, 2), round(max(s["z1"] for s in own) + 1.0, 2)]}
        secret = piece.secret
        exits = []
        for exit_ in piece.exits:
            space = spaces[f"{piece.ident}.{exit_['space']}"]
            position = exit_.get("position")
            if position is None:
                position = [round((space["x0"] + space["x1"]) * 0.5, 2), round(space["floor"] + 0.05, 2),
                            round((space["z0"] + space["z1"]) * 0.5, 2)]
            else:
                position = _move(position, dx, dz)
            exits.append({"map": exit_["map"], "spawn": exit_["spawn"], "label": exit_["label"],
                          "space": f"{piece.ident}.{exit_['space']}", "position": position})
        sections.append({
            "id": piece.ident, "name": piece.name, "kind": piece.kind,
            "entranceMap": secret.door_map or region,
            "entranceProp": secret.entrance, "key": secret.key, "label": SR.label_for(secret),
            "offset": [dx, dz], "arrival": arrival, "bounds": bounds,
            "spaces": [f"{piece.ident}.{k}" for k in piece.spaces],
            "areas": [{"kind": a["kind"], "multiplier": a["multiplier"],
                       "spaces": [f"{piece.ident}.{s}" for s in a["spaces"]]} for a in piece.areas],
            "spawns": [{"creature": s["creature"], "count": s["count"],
                        "space": f"{piece.ident}.{s['space']}"} for s in piece.spawns],
            "exits": exits,
            "note": secret.note,
        })
    assert_gutters(footprints)
    combined.spawn_space = f"{pieces[0].ident}.{pieces[0].entrance_space}"
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.10, 0.10, 0.12], "energy": 0.55},
        "fog": {"enabled": True, "colour": [0.02, 0.02, 0.03], "begin": 14.0, "end": 48.0},
    }
    return combined, groups, sections


def tile_of(position, origin):
    return [int(round(position[0] + origin[0])), int(round(origin[1] - position[2]))]


def bounds_tiles(space, origin):
    x0, y1 = tile_of([space["x0"], 0, space["z0"]], origin)
    x1, y0 = tile_of([space["x1"], 0, space["z1"]], origin)
    return {"min": [min(x0, x1), min(y0, y1)], "max": [max(x0, x1), max(y0, y1)]}


def write_manifest(design, combined: Interior, sections, stats, collision_stats, path: Path):
    lo, hi = combined.group.bounds()
    walk_lo, walk_hi = combined.group.walk_bounds()
    origin = [float(-collision_stats["originMetres"][0]), float(collision_stats["originMetres"][1])]
    region = design.REGION
    package_id = f"{region}_secrets"
    for section in sections:
        section["arrivalTile"] = tile_of(section["arrival"], origin)
        section["boundsTiles"] = {"min": tile_of([section["bounds"]["min"][0], 0, section["bounds"]["max"][1]], origin),
                                  "max": tile_of([section["bounds"]["max"][0], 0, section["bounds"]["min"][1]], origin)}
        for area in section["areas"]:
            spaces = [combined.spaces[k] for k in area["spaces"]]
            boxes = [bounds_tiles(s, origin) for s in spaces]
            area["tiles"] = {"min": [min(b["min"][0] for b in boxes), min(b["min"][1] for b in boxes)],
                             "max": [max(b["max"][0] for b in boxes), max(b["max"][1] for b in boxes)]}
        for spawn in section["spawns"]:
            spawn["tiles"] = bounds_tiles(combined.spaces[spawn["space"]], origin)
        for exit_ in section["exits"]:
            exit_["tile"] = tile_of(exit_["position"], origin)
    for entry in combined.harvestables + combined.interactives:
        entry["serverTile"] = tile_of(entry["position"], origin)
    spawn_points = [{"id": "default", "position": sections[0]["arrival"], "rotationDegrees": 0,
                     "surface": "Walk", "section": sections[0]["id"]}]
    for section in sections:
        spawn_points.append({"id": section["id"], "position": section["arrival"], "rotationDegrees": 0,
                             "surface": "Walk", "section": section["id"]})
        for exit_ in section["exits"]:
            # a stone or a tunnel end is also somewhere another map arrives
            spawn_points.append({"id": f"{section['id']}-{exit_['space'].split('.')[-1]}",
                                 "position": exit_["position"], "rotationDegrees": 0,
                                 "surface": "Walk", "section": section["id"]})
    portals = []
    for section in sections:
        portals.append({"id": f"exit-{section['id']}", "name": f"Back up: {section['name']}",
                        "type": "map-transition", "position": section["arrival"], "radius": 2.5,
                        "destinationMap": section["entranceMap"], "destinationSpawn": f"secret-{section['id']}",
                        "section": section["id"], "authority": "server"})
        for exit_ in section["exits"]:
            portals.append({"id": f"link-{section['id']}-{exit_['spawn']}", "name": exit_["label"],
                            "type": "map-transition", "position": exit_["position"], "radius": 2.5,
                            "destinationMap": exit_["map"], "destinationSpawn": exit_["spawn"],
                            "section": section["id"], "authority": "server"})
    doc = {
        "schemaVersion": "1.0.0",
        "assetVersion": "1.0.0",
        "asset": {"id": package_id, "name": design.NAME, "glb": "world.glb", "units": "meters",
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"},
                  "origin": [0, 0, 0],
                  "bounds": {"min": [round(float(v), 2) for v in lo], "max": [round(float(v), 2) for v in hi]},
                  "playableBounds": {"min": [round(float(v), 2) for v in walk_lo],
                                     "max": [round(float(v), 2) for v in walk_hi]},
                  "interiorClass": "secrets", "parentRegion": region,
                  "serverCells": TILES * 6},
        "coordinateTransform": {"metresPerTile": 1.0, "serverOrigin": origin, "origin": [0.0, 0.0, 0.0],
                                "walkingHeight": 0.0, "invertServerY": True},
        "secret": True,
        "spawnPoints": spawn_points,
        "collision": dict(collision_stats, nodeNames=[n for n in stats["nodeNames"] if not n.startswith("Walk_")]),
        "cutaway": {"hideNodes": [n for n in stats["nodeNames"] if n.startswith("Roof_")],
                    "reason": "interior lids; the isometric rig frames the floor, not the roof"},
        "navigation": {"surfaceNodePrefixes": ["Walk_"], "agentRadius": 0.4, "agentHeight": 1.9,
                       "maxSlopeDegrees": 45, "navmesh": {"format": "surface-prefix-v1", "polygons": []}},
        "portals": portals,
        "landmarks": combined.landmarks,
        "interactives": combined.interactives,
        "npcMarkers": combined.npc_markers,
        "harvestables": combined.harvestables,
        "environment": dict(combined.environment, openToSky=combined.open_to_sky,
                            lights=[{"id": f"lamp-{i:03d}", "kind": "point", "position": p,
                                     "color": [1.0, 0.66, 0.32], "range": 14.0, "energy": 3.2,
                                     "attenuation": 1.2} for i, p in enumerate(combined.lamps)]),
        "spaces": {k: {kk: round(float(vv), 2) for kk, vv in v.items()} for k, v in combined.spaces.items()},
        "sections": sections,
        "secrets": {"region": region, "sections": [s["id"] for s in sections],
                    "note": ("Each section is one secret. The client shows a player only the section "
                             "they stand in; the server places the arrival, the areas, the spawns and "
                             "the harvest nodes from this block.")},
        "performance": stats,
        "sources": [{"id": "generator", "file": "_toolkit/secrets_build.py", "role": "reproducible-build",
                     "design": f"{region}/source/secrets_design.py"}],
        "provenance": {"geometry": "authored with the secret rooms kit over the shared toolkit",
                       "license": "CC-BY-4.0"},
        "productionStatus": "authored-geometry-materials-population",
        "notes": [f"{len(sections)} secrets of {design.NAME} on one map with void between them; "
                  "which one a player gets is which feature of the ground above they used."],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("region")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=20260905)
    args = ap.parse_args()
    design = load_design(args.region)
    package_id = f"{design.REGION}_secrets"
    out = Path(args.out) if args.out else ROOT / "interiors" / package_id
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    sets = preview.texture_sets()
    combined, groups, sections = compose(design, args.seed)
    stats = export_glb(groups, sets, out / "world.glb", package_id)
    payload, collision_stats = build_collision(combined.group)
    (out / "collision.bin").write_bytes(payload)
    write_manifest(design, combined, sections, stats, collision_stats, out / "world.json")
    report = validate_gltf.validate(str(out / "world.glb"))
    (out / "world.glb.validator.json").write_text(json.dumps(report.to_dict(), indent=2) + "\n",
                                                 encoding="utf-8")
    errors = report.to_dict()["issues"]["numErrors"]
    grid = EXPORT.export(out, ROOT / "server-collision" / f"{package_id}.bin", TILES, "stride")
    origin = json.loads((out / "world.json").read_text(encoding="utf-8"))["coordinateTransform"]["serverOrigin"]
    blocked = []
    for section in sections:
        tx, ty = section["arrivalTile"]
        if not grid[ty, tx]:
            blocked.append(section["id"])
    print(f"[{package_id}] {len(sections)} secrets, {stats['uniqueTriangles']} tris, "
          f"{stats['glbBytes'] / 1e6:.2f} MB, {collision_stats['walkableCells']} walkable cells, "
          f"glTF {'ok' if errors == 0 else 'ERRORS'} ({time.time() - t0:.1f}s)")
    if blocked:
        print(f"[{package_id}] BLOCKED ARRIVALS: {blocked}")
    return 0 if errors == 0 and not blocked else 1


if __name__ == "__main__":
    sys.exit(main())
