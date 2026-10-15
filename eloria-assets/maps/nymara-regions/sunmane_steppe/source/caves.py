#!/usr/bin/env python3
"""Build the Sunmane cave interior map packages.

Two small explorable interiors sit behind the cave mouths modelled on the
Sunmane Steppe surface map:

    sunmane_wind_caves       a wind-scoured limestone system under the eastern
                             butte, worked and camped in by Orun drovers
    sunmane_crystal_hollow   an amethyst geode opened by prospectors on the
                             edge of the Amethyst badland

Each is exported as its own schema 1.x package - `world.glb`, `world.json`,
`minimap.webp` - so the destinations exist client-side and only need the map
registered on the server.

The cavern shell is not a box with a ceiling on top. The open volume is defined
by a clearance field around a network of chambers and passages; the roof height
is driven by that field, so the roof comes down to meet the floor at the walls
and the cavern reads as one continuous rock surface. The floor carries the
navigation prefix and the roof carries structural collision, which is what stops
a player walking out through a wall.

Run:  python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/caves.py [--output DIR]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit                                           # noqa: E402
import noise as noise_kit                            # noqa: E402
from noise import stable_seed                       # noqa: E402
import settlement                                    # noqa: E402
from build_sunmane import Builder                            # noqa: E402
from glb import Geometry, compose                    # noqa: E402
from shapes import UV_SCALE, oriented_quad, oriented_triangle  # noqa: E402

ASSET_ROOT = HERE.parents[3]
MAP_ROOT = HERE.parents[1] / "interiors"

CELL = 0.5                    # metres between field samples
HALF_EXTENT = 30.0            # metres from the map centre to its edge

## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0
WALL_BLEND = 3.2              # metres over which the roof falls to the wall
WALL_GAP = 0.28               # roof height held at the wall, so no crack forms
# The shell is one continuous rock surface tens of metres across, so its
# texture repeats on a much longer period than a prop does; at the kit's
# stone scale the grain reads as measles across a whole chamber floor.
SHELL_UV = 7.2
RIM_GAP = 0.14                # roof height at the very rim of the cavern
SERVER_ORIGIN = (30.0, 30.0)
METRES_PER_TILE = 1.0
SCHEMA_VERSION = "1.1.0"
ASSET_VERSION = "1.0.0"


# --------------------------------------------------------------------- specs
class Chamber:
    """One rounded room in a cave system."""

    def __init__(self, identifier: str, x: float, z: float, radius: float,
                 floor: float, headroom: float, label: str) -> None:
        self.id = identifier
        self.x = x
        self.z = z
        self.radius = radius
        self.floor = floor
        self.headroom = headroom
        self.label = label


class Passage:
    """A connecting passage between two points."""

    def __init__(self, start, end, half_width: float, headroom: float,
                 props: int = 0) -> None:
        self.start = np.array(start, dtype="float64")
        self.end = np.array(end, dtype="float64")
        self.half_width = half_width
        self.headroom = headroom
        self.props = props


WIND_CAVES = {
    "id": "sunmane_wind_caves",
    "name": "Sunmane Wind Caves",
    "mapPath": "sunmane_wind_caves",
    "returnMap": "sunmane_steppe",
    "returnTile": [128, 175],
    "palette": "limestone",
    "chambers": [
        Chamber("entrance-hall", 0.0, 18.0, 6.6, 0.0, 4.4, "Entrance hall"),
        Chamber("wind-gallery", 0.0, 2.0, 9.0, -1.4, 6.6, "The wind gallery"),
        Chamber("drovers-camp", -16.0, -8.0, 6.2, -1.0, 4.4, "Drovers' camp"),
        Chamber("whistle-shaft", 15.0, -6.0, 5.6, -2.4, 9.0, "The whistle shaft"),
        Chamber("still-pool", 2.0, -18.0, 5.2, -3.2, 4.0, "The still pool"),
    ],
    "passages": [
        Passage((0.0, 18.0), (0.0, 2.0), 2.6, 3.6, props=3),
        Passage((0.0, 2.0), (-16.0, -8.0), 2.2, 3.2, props=2),
        Passage((0.0, 2.0), (15.0, -6.0), 2.4, 3.4, props=0),
        Passage((0.0, 2.0), (2.0, -18.0), 2.0, 3.0, props=2),
    ],
    "water": [(2.0, -18.5, 3.6, -2.75)],
    "camps": [(-16.0, -8.0, 0.6)],
    "crystalChambers": (),
}

CRYSTAL_HOLLOW = {
    "id": "sunmane_crystal_hollow",
    "name": "Amethyst Crystal Hollow",
    "mapPath": "sunmane_crystal_hollow",
    "returnMap": "sunmane_steppe",
    "returnTile": [182, 154],
    "palette": "amethyst",
    "chambers": [
        Chamber("adit-mouth", 0.0, 17.0, 5.2, 0.0, 3.8, "Adit mouth"),
        Chamber("geode-chamber", 0.0, -2.0, 10.5, -2.2, 8.4, "The geode chamber"),
        Chamber("prospect-cut", -15.5, -12.5, 6.6, -1.8, 4.6, "Prospectors' cut"),
        Chamber("violet-gallery", 14.0, -11.0, 6.2, -2.8, 5.6, "The violet gallery"),
        Chamber("shard-store", -13.0, 6.0, 4.4, -0.8, 3.6, "Shard store"),
    ],
    "passages": [
        Passage((0.0, 17.0), (0.0, -2.0), 2.2, 3.0, props=4),
        Passage((0.0, -2.0), (-15.5, -12.5), 2.0, 3.0, props=2),
        Passage((0.0, -2.0), (14.0, -11.0), 2.0, 3.2, props=2),
        Passage((0.0, 8.0), (-13.0, 6.0), 1.9, 2.9, props=2),
    ],
    "water": (),
    "camps": [(-15.5, -12.5, 2.4)],
    "crystalChambers": ("geode-chamber", "violet-gallery", "shard-store"),
}

SYSTEMS = {spec["id"]: spec for spec in (WIND_CAVES, CRYSTAL_HOLLOW)}


# --------------------------------------------------------------- the shell
class Shell:
    """The sampled clearance, floor and roof fields of one cave system."""

    def __init__(self, spec: dict, centre: tuple = (0.0, 0.0)) -> None:
        self.spec = spec
        self.centre = (float(centre[0]), float(centre[1]))
        count = int(round(HALF_EXTENT * 2.0 / CELL)) + 1
        # The sample grid is centred on `centre` rather than on the origin, so
        # a system can be placed anywhere on a shared map. Every chamber and
        # passage coordinate in the spec is already in that same space, and all
        # the field maths below is differences (`self.x - chamber.x`), so
        # nothing else in the sampling has to know where the system sits.
        self.axis_x = np.linspace(self.centre[0] - HALF_EXTENT,
                                  self.centre[0] + HALF_EXTENT, count)
        self.axis_z = np.linspace(self.centre[1] - HALF_EXTENT,
                                  self.centre[1] + HALF_EXTENT, count)
        # Kept only for its size; never read as a coordinate - use axis_x/axis_z.
        self.axis = self.axis_x
        self.x, self.z = np.meshgrid(self.axis_x, self.axis_z)
        rng = np.random.default_rng(stable_seed(spec["id"]))
        relief = noise_kit.fbm(count, 6, 4, rng) - 0.5
        grain = noise_kit.fbm(count, 17, 3, rng) - 0.5

        # Clearance: how far inside the cavern each sample lies. Rooms and
        # passages contribute their own radius, and the largest wins, so
        # overlapping volumes merge into one continuous space.
        clearance = np.full(self.x.shape, -1e9)
        floor = np.zeros_like(self.x)
        headroom = np.zeros_like(self.x)
        # How wide the local volume is, so a narrow passage's roof closes over a
        # short distance while a big chamber's rises gradually. Blending on a
        # single fixed distance made small rooms too low to stand in.
        extent = np.zeros_like(self.x)
        weight = np.zeros_like(self.x)
        for chamber in spec["chambers"]:
            distance = np.hypot(self.x - chamber.x, self.z - chamber.z)
            # A lobed radius keeps the rooms from reading as drawn circles.
            angle = np.arctan2(self.z - chamber.z, self.x - chamber.x)
            radius = chamber.radius * (1.0 + 0.16 * np.sin(angle * 3.0 + chamber.x)
                                       + 0.09 * np.sin(angle * 5.0 - chamber.z))
            local = radius - distance
            clearance = np.maximum(clearance, local)
            share = np.clip(local / np.maximum(radius, 0.1) + 0.35, 0.0, 1.0) ** 2
            floor += chamber.floor * share
            headroom += chamber.headroom * share
            extent += chamber.radius * share
            weight += share
        for passage in spec["passages"]:
            local, along = self._segment(passage)
            clearance = np.maximum(clearance, local)
            share = np.clip(local / passage.half_width + 0.35, 0.0, 1.0) ** 2
            ends = spec["chambers"]
            floor_start = self._floor_at(ends, passage.start)
            floor_end = self._floor_at(ends, passage.end)
            floor += (floor_start + (floor_end - floor_start) * along) * share
            headroom += passage.headroom * share
            extent += passage.half_width * share
            weight += share
        weight = np.maximum(weight, 1e-6)
        self.clearance = clearance
        # Rock is never flat: a low relief on the floor and a coarser one on the
        # roof keep the section from reading as two offset copies of a plan.
        self.floor = floor / weight + relief * 0.75 + grain * 0.22
        self.headroom = headroom / weight
        self.open = clearance > 0.0
        wall_blend = np.clip((extent / weight) * 0.44, 0.8, WALL_BLEND)
        blend = np.clip(clearance / wall_blend, 0.0, 1.0)
        # A high exponent keeps the roof low well into the chamber before it
        # lifts, so the wall curves up out of the floor instead of standing
        # as a ring of tall vertical facets at the rim.
        height = WALL_GAP + (self.headroom - WALL_GAP) * blend ** 1.25
        self.roof = self.floor + np.maximum(height, WALL_GAP) + grain * 0.30 * blend
        # Tie the outermost open samples down to the floor. Without this the
        # cavern ends in a ring of vertical facets stepping along the sample
        # grid; with it the roof surface itself curves down into the floor and
        # the wall is one continuous piece of rock.
        rim = self.open & ~(
            np.pad(self.open[1:, :], ((0, 1), (0, 0)))
            & np.pad(self.open[:-1, :], ((1, 0), (0, 0)))
            & np.pad(self.open[:, 1:], ((0, 0), (0, 1)))
            & np.pad(self.open[:, :-1], ((0, 0), (1, 0))))
        self.roof[rim] = self.floor[rim] + RIM_GAP

    def _segment(self, passage: Passage):
        delta = passage.end - passage.start
        length_squared = float(np.dot(delta, delta))
        px = self.x - passage.start[0]
        pz = self.z - passage.start[1]
        along = np.clip((px * delta[0] + pz * delta[1]) / length_squared, 0.0, 1.0)
        nearest_x = passage.start[0] + delta[0] * along
        nearest_z = passage.start[1] + delta[1] * along
        distance = np.hypot(self.x - nearest_x, self.z - nearest_z)
        # A passage widens a little at its middle, as a natural rift does.
        width = passage.half_width * (1.0 + 0.22 * np.sin(along * math.pi))
        return width - distance, along

    @staticmethod
    def _floor_at(chambers, point) -> float:
        best, best_distance = 0.0, 1e9
        for chamber in chambers:
            distance = math.hypot(chamber.x - point[0], chamber.z - point[1])
            if distance < best_distance:
                best, best_distance = chamber.floor, distance
        return best

    # ---------------------------------------------------------------- sample
    def index_of(self, x: float, z: float) -> tuple[int, int]:
        i = int(round((x - self.centre[0] + HALF_EXTENT) / CELL))
        j = int(round((z - self.centre[1] + HALF_EXTENT) / CELL))
        last = self.axis.size - 1
        return min(max(j, 0), last), min(max(i, 0), last)

    def floor_at(self, x: float, z: float) -> float:
        j, i = self.index_of(x, z)
        return float(self.floor[j, i])

    def roof_at(self, x: float, z: float) -> float:
        j, i = self.index_of(x, z)
        return float(self.roof[j, i])

    def clearance_at(self, x: float, z: float) -> float:
        j, i = self.index_of(x, z)
        return float(self.clearance[j, i])


# ---------------------------------------------------------------- shell mesh
SHELL_CHUNKS = 4


def _chunk_of(index: int, count: int) -> int:
    return min(SHELL_CHUNKS - 1, index * SHELL_CHUNKS // max(count - 1, 1))


def build_shell(builder: Builder, shell: Shell, materials: dict) -> dict:
    """Emit the cavern floor, roof and the wall skirt that closes them."""
    count = shell.axis.size
    floor_parts: dict = {}
    roof_parts: dict = {}
    wall_parts: dict = {}
    emitted = np.zeros((count - 1, count - 1), dtype=bool)
    for j in range(count - 1):
        for i in range(count - 1):
            if not (shell.open[j, i] and shell.open[j, i + 1]
                    and shell.open[j + 1, i + 1] and shell.open[j + 1, i]):
                continue
            emitted[j, i] = True

    scale = SHELL_UV
    for j in range(count - 1):
        for i in range(count - 1):
            if not emitted[j, i]:
                continue
            key = (_chunk_of(i, count), _chunk_of(j, count))
            # Separate axes: `axis` is an alias for `axis_x`, so reading a z
            # coordinate out of it silently placed the whole cavern at
            # +x-range in z. Harmless while both axes were the symmetric
            # -HALF_EXTENT..+HALF_EXTENT and wrong the moment a system moves.
            x0, x1 = float(shell.axis_x[i]), float(shell.axis_x[i + 1])
            z0, z1 = float(shell.axis_z[j]), float(shell.axis_z[j + 1])
            corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
            uvs = [[x0 / scale, z0 / scale], [x1 / scale, z0 / scale],
                   [x1 / scale, z1 / scale], [x0 / scale, z1 / scale]]
            xs = (x0, x1, x1, x0)
            zs = (z0, z0, z1, z1)
            floor = floor_parts.setdefault(key, Geometry())
            oriented_quad(floor,
                          [(xs[c], float(shell.floor[cj, ci]), zs[c])
                           for c, (ci, cj) in enumerate(corners)],
                          uvs, (0.0, 1.0, 0.0))
            roof = roof_parts.setdefault(key, Geometry())
            oriented_quad(roof,
                          [(xs[c], float(shell.roof[cj, ci]), zs[c])
                           for c, (ci, cj) in enumerate(corners)],
                          uvs, (0.0, -1.0, 0.0))
            # Close the rim: any quad edge with no emitted neighbour gets a
            # skirt from floor to roof, facing back into the cavern.
            for edge, (di, dj) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
                ni, nj = i + di, j + dj
                if 0 <= ni < count - 1 and 0 <= nj < count - 1 and emitted[nj, ni]:
                    continue
                a, b = edge, (edge + 1) % 4
                ai, aj = corners[a]
                bi, bj = corners[b]
                ax, az = xs[a], zs[a]
                bx, bz = xs[b], zs[b]
                inward = (float(x0 + x1) * 0.5 - (ax + bx) * 0.5, 0.0,
                          float(z0 + z1) * 0.5 - (az + bz) * 0.5)
                wall = wall_parts.setdefault(key, Geometry())
                span = math.hypot(bx - ax, bz - az)
                oriented_quad(
                    wall,
                    [(ax, float(shell.floor[aj, ai]), az),
                     (bx, float(shell.floor[bj, bi]), bz),
                     (bx, float(shell.roof[bj, bi]), bz),
                     (ax, float(shell.roof[aj, ai]), az)],
                    [[0.0, 0.0], [span / scale, 0.0],
                     [span / scale, 1.0 / scale], [0.0, 1.0 / scale]],
                    inward)

    triangles = 0
    for key in sorted(floor_parts):
        name = "Terrain_CaveFloor_%d_%d" % key
        geometry = floor_parts[key]
        triangles += geometry.triangle_count
        builder.emit(name, [(geometry, materials["floor"])])
    for key in sorted(roof_parts):
        name = "Structure_CaveRoof_%d_%d" % key
        geometry = roof_parts[key]
        triangles += geometry.triangle_count
        builder.emit(name, [(geometry, materials["roof"])], collide=True)
    for key in sorted(wall_parts):
        name = "Structure_CaveWall_%d_%d" % key
        geometry = wall_parts[key]
        triangles += geometry.triangle_count
        builder.emit(name, [(geometry, materials["wall"])], collide=True)
    return {"shellTriangles": triangles,
            "openCells": int(emitted.sum()),
            "shellChunks": len(floor_parts) + len(roof_parts) + len(wall_parts)}


# ------------------------------------------------------------------ dressing
def _mesh_of(builder: Builder, cache: dict, materials: dict, name: str,
             factory) -> int | None:
    """Build one kit asset once and reuse the mesh for every instance."""
    if name in cache:
        return cache[name]
    parts = factory()
    ordered = [(geometry.weld(), materials[key])
               for key, geometry in sorted(parts.items())
               if geometry.triangle_count]
    mesh = builder.glb.mesh(name, ordered) if ordered else None
    cache[name] = mesh
    return mesh


def populate(builder: Builder, shell: Shell, materials: dict,
             kit_materials: dict) -> dict:
    """Place formations, props and the worked timber through the system."""
    spec = shell.spec
    rng = np.random.default_rng(stable_seed(spec["id"] + "props"))
    cache: dict = {}
    instances = 0
    unique = 0
    # Circles the ground clutter must leave alone: the middle of every chamber,
    # so each room keeps open standing room, plus every prop as it is placed.
    keep_out: list[tuple[float, float, float]] = [
        (chamber.x, chamber.z, chamber.radius * 0.42)
        for chamber in spec["chambers"]]

    def place(asset: str, factory, x: float, z: float, *, y: float | None = None,
              rotation: float = 0.0, collide: bool = False,
              landmark: str | None = None, label: str | None = None,
              interactive: dict | None = None) -> str | None:
        nonlocal instances, unique
        before = builder.glb.statistics()["uniqueMeshTriangles"]
        mesh = _mesh_of(builder, cache, kit_materials, asset, factory)
        if mesh is None:
            return None
        unique += builder.glb.statistics()["uniqueMeshTriangles"] - before
        height = shell.floor_at(x, z) if y is None else y
        name = "%s_%s_%03d" % ("Landmark" if landmark else "Detail",
                               asset, instances)
        builder.instance(name, mesh, compose((x, height, z), rotation_y=rotation),
                         collide=collide)
        instances += 1
        if landmark:
            builder.landmarks.append({
                "id": name, "kind": landmark, "node": name,
                "position": [round(x, 2), round(height, 2), round(z, 2)],
                "serverTile": server_tile(x, z), "reachable": True,
                "label": label or landmark})
        if interactive:
            entry = dict(interactive)
            entry.update({"node": name,
                          "position": [round(x, 2), round(height, 2), round(z, 2)],
                          "serverTile": server_tile(x, z)})
            builder.interactives.append(entry)
        return name

    # --- worked timber in the passages ------------------------------------
    for index, passage in enumerate(spec["passages"]):
        for step in range(passage.props):
            t = (step + 1) / (passage.props + 1)
            point = passage.start + (passage.end - passage.start) * t
            heading = math.atan2(passage.end[1] - passage.start[1],
                                 passage.end[0] - passage.start[0])
            width = passage.half_width * 1.7
            place("pit_props_%d" % (index % 2),
                  lambda w=width, h=passage.headroom * 0.78, s=index:
                      kit.pit_props(w, h, s),
                  float(point[0]), float(point[1]),
                  rotation=heading, collide=True)
            keep_out.append((float(point[0]), float(point[1]), width * 0.7)) 

    # --- chamber furniture -------------------------------------------------
    for chamber in spec["chambers"]:
        angle = chamber.x * 0.31 + chamber.z * 0.17
        brazier_x = chamber.x + math.cos(angle) * chamber.radius * 0.45
        brazier_z = chamber.z + math.sin(angle) * chamber.radius * 0.45
        node = place("cave_brazier", kit.cave_brazier, brazier_x, brazier_z,
                     collide=True, landmark="brazier",
                     label=chamber.label + " brazier")
        keep_out.append((brazier_x, brazier_z, 1.6))
        builder.lights.append({
            "id": "Light_Brazier_%s" % chamber.id,
            "kind": "brazier",
            "node": node,
            "position": [round(brazier_x, 2),
                         round(shell.floor_at(brazier_x, brazier_z) + 1.35, 2),
                         round(brazier_z, 2)],
            "color": [1.0, 0.69, 0.40] if spec["palette"] == "limestone"
            else [0.78, 0.61, 1.0],
            "energyHint": 2.1,
            "rangeHint": round(max(chamber.radius * 1.9, 10.0), 2)})

    for camp_x, camp_z, facing in spec["camps"]:
        keep_out.append((camp_x, camp_z, 4.6))
        place("fire_pit", lambda: _wrap(kit.fire_pit, (0.0, 0.0), 0.9),
              camp_x, camp_z, landmark="camp", label="Underground camp")
        place("cart", lambda: _wrap(kit.cart, 0.0, True),
              camp_x + math.cos(facing) * 3.4, camp_z + math.sin(facing) * 3.4,
              rotation=facing, collide=True)
        place("barrel_stack", lambda: _wrap(kit.barrel, (0.0, 0.0), 0.38, 0.9),
              camp_x + math.cos(facing + 1.9) * 2.8,
              camp_z + math.sin(facing + 1.9) * 2.8, collide=True)
        place("hay_bale", lambda: _wrap(kit.hay_bale, (0.0, 0.0), 0.6, 1.2),
              camp_x + math.cos(facing - 1.7) * 2.9,
              camp_z + math.sin(facing - 1.7) * 2.9,
              rotation=facing, collide=True)
        place("tool_rack", kit.tool_rack,
              camp_x + math.cos(facing + 2.9) * 3.1,
              camp_z + math.sin(facing + 2.9) * 3.1,
              rotation=facing + math.pi, collide=True)

    # --- formations along the walls ---------------------------------------
    # Placed last, so the timber sets, the camps and the braziers all keep the
    # floor they need and a stalagmite never grows through a cart.
    crystal_rooms = {c.id for c in spec["chambers"]
                     if c.id in spec["crystalChambers"]}

    def obstructed(x: float, z: float, radius: float) -> bool:
        for cx, cz, keep in keep_out:
            if (x - cx) ** 2 + (z - cz) ** 2 < (keep + radius) ** 2:
                return True
        return False

    attempts = 0
    formations = 0
    while attempts < 6000 and formations < 150:
        attempts += 1
        x = float(rng.uniform(shell.centre[0] - HALF_EXTENT,
                              shell.centre[0] + HALF_EXTENT))
        z = float(rng.uniform(shell.centre[1] - HALF_EXTENT,
                              shell.centre[1] + HALF_EXTENT))
        clearance = shell.clearance_at(x, z)
        if clearance <= 0.35:
            continue
        headroom = shell.roof_at(x, z) - shell.floor_at(x, z)
        roll = float(rng.random())
        seed = int(rng.integers(0, 9999))
        rotation = float(rng.random()) * math.tau
        if clearance < 2.1 and roll < 0.40 and headroom > 1.2:
            # Stalagmites crowd the wall line, where the drip runs down.
            size = min(headroom * 0.55, 0.9 + 1.5 * float(rng.random()))
            if obstructed(x, z, 0.5):
                continue
            place("cave_formation_%d" % (seed % 4),
                  lambda h=size, s=seed: kit.cave_formation(
                      h, 0.16 + h * 0.10, s),
                  x, z, rotation=rotation)
        elif headroom > 3.4 and roll < 0.62:
            # Stalactites hang from the roof, clear of the walking floor.
            drop = min(headroom * 0.40, 0.7 + 1.4 * float(rng.random()))
            place("cave_stalactite_%d" % (seed % 4),
                  lambda h=drop, s=seed: kit.cave_formation(
                      h, 0.15 + h * 0.10, s, hanging=True),
                  x, z, y=shell.roof_at(x, z) - 0.05, rotation=rotation)
        elif headroom > 3.0 and 2.4 < clearance and roll < 0.70:
            if obstructed(x, z, 0.9):
                continue
            place("cave_column_%d" % (seed % 3),
                  lambda h=headroom, s=seed: kit.cave_column(h + 0.1, 0.34, s),
                  x, z, collide=True)
            keep_out.append((x, z, 1.4))
        elif roll < 0.80:
            if obstructed(x, z, 0.8):
                continue
            place("cave_boulder_%d" % (seed % 4),
                  lambda s=seed: kit.shore_rock(0.6 + 0.7 * float(
                      np.random.default_rng(s).random()), s),
                  x, z, y=shell.floor_at(x, z) - 0.22, rotation=rotation,
                  collide=True)
        elif crystal_rooms and roll < 0.92 and _nearest_room(spec, x, z) in crystal_rooms:
            if obstructed(x, z, 0.6):
                continue
            place("crystal_cluster_%d" % (seed % 3),
                  lambda s=seed: kit.crystal_cluster(
                      1.0 + 0.8 * float(np.random.default_rng(s).random()), s),
                  x, z, y=shell.floor_at(x, z) - 0.12, rotation=rotation)
        elif spec["id"] == "sunmane_wind_caves":
            if obstructed(x, z, 0.5):
                continue
            place("bleached_bones_%d" % (seed % 3),
                  lambda s=seed: kit.bleached_bones(s), x, z,
                  y=shell.floor_at(x, z) - 0.04, rotation=rotation)
        else:
            continue
        formations += 1

    # --- the amethyst itself ----------------------------------------------
    # A geode chamber has to be full of crystal, so the crystal rooms get a
    # dedicated pass rather than relying on the general scatter's leftovers.
    for chamber in spec["chambers"]:
        if chamber.id not in spec["crystalChambers"]:
            continue
        lit = 0
        for step in range(30):
            angle = float(rng.random()) * math.tau
            reach = chamber.radius * (0.34 + 0.32 * float(rng.random()))
            x = chamber.x + math.cos(angle) * reach
            z = chamber.z + math.sin(angle) * reach
            if shell.clearance_at(x, z) < 1.2 or obstructed(x, z, 0.7):
                continue
            seed = int(rng.integers(0, 9999))
            scale = 0.7 + 0.8 * float(rng.random())
            place("crystal_cluster_%d" % (seed % 3),
                  lambda v=scale, s=seed: kit.crystal_cluster(v, s),
                  x, z, y=shell.floor_at(x, z) - 0.14,
                  rotation=float(rng.random()) * math.tau)
            keep_out.append((x, z, 0.9))
            if lit < 3 and scale > 1.2:
                lit += 1
                builder.lights.append({
                    "id": "Light_Amethyst_%s_%d" % (chamber.id, lit),
                    "kind": "crystal",
                    "position": [round(x, 2),
                                 round(shell.floor_at(x, z) + scale * 1.1, 2),
                                 round(z, 2)],
                    "color": [0.62, 0.42, 1.0],
                    "energyHint": 1.4,
                    "rangeHint": round(chamber.radius * 1.1, 2)})

    return {"instances": instances, "kitUniqueTriangles": unique,
            "kitAssets": len([m for m in cache.values() if m is not None])}


def _wrap(function, *arguments) -> kit.Parts:
    """Adapt the kit's in-place helpers to the Parts-returning convention."""
    parts = kit.Parts()
    function(parts, *arguments)
    return parts


def _nearest_room(spec: dict, x: float, z: float) -> str:
    best, best_distance = "", 1e9
    for chamber in spec["chambers"]:
        distance = math.hypot(chamber.x - x, chamber.z - z)
        if distance < best_distance:
            best, best_distance = chamber.id, distance
    return best


def server_tile(x: float, z: float) -> list[int]:
    return [int(round(x / METRES_PER_TILE + SERVER_ORIGIN[0])),
            int(round(-z / METRES_PER_TILE + SERVER_ORIGIN[1]))]


# ------------------------------------------------------------------- water
def build_water(builder: Builder, shell: Shell, material: int) -> int:
    """A still pool surface, where the system declares one."""
    triangles = 0
    for index, (x, z, radius, level) in enumerate(shell.spec["water"]):
        geometry = Geometry()
        sides = 22
        for step in range(sides):
            a0 = math.tau * step / sides
            a1 = math.tau * (step + 1) / sides
            oriented_triangle(
                geometry,
                [(x, level, z),
                 (x + math.cos(a0) * radius, level, z + math.sin(a0) * radius),
                 (x + math.cos(a1) * radius, level, z + math.sin(a1) * radius)],
                [[0.5, 0.5],
                 [0.5 + math.cos(a0) * 0.5, 0.5 + math.sin(a0) * 0.5],
                 [0.5 + math.cos(a1) * 0.5, 0.5 + math.sin(a1) * 0.5]],
                (0.0, 1.0, 0.0))
        triangles += geometry.triangle_count
        builder.emit("Water_Pool_%02d" % index, [(geometry, material)], weld=False)
    return triangles


# ---------------------------------------------------------------- manifest
def build_manifest(shell: Shell, builder: Builder, statistics: dict) -> dict:
    spec = shell.spec
    entrance = spec["chambers"][0]
    lowest = float(shell.floor[shell.open].min())
    highest = float(shell.roof[shell.open].max())
    amethyst = spec["palette"] == "amethyst"

    spawn_points = []
    for chamber in spec["chambers"][:2]:
        tile = server_tile(chamber.x, chamber.z)
        spawn_points.append({
            "id": chamber.id,
            "node": "Terrain_CaveFloor_%d_%d" % (
                _chunk_of(shell.index_of(chamber.x, chamber.z)[1], shell.axis.size),
                _chunk_of(shell.index_of(chamber.x, chamber.z)[0], shell.axis.size)),
            "serverTile": tile,
            "position": [round(chamber.x, 3),
                         round(shell.floor_at(chamber.x, chamber.z), 3),
                         round(chamber.z, 3)],
            "facing": [0, 0, -1],
            "groundedBy": "navigation-surface-raycast",
            "note": chamber.label})

    span = HALF_EXTENT * 2.0
    # Every Eloria minimap is drawn at one pixel to the metre, so the
    # image is the cave's own size rather than a fixed square.
    image = int(round(span * MINIMAP_PIXELS_PER_METRE))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": spec["id"],
            "name": spec["name"],
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [-HALF_EXTENT, round(lowest - 1.0, 2), -HALF_EXTENT],
                       "max": [HALF_EXTENT, round(highest + 1.0, 2), HALF_EXTENT]},
            "regionSpanMeters": span,
            "interior": True,
        },
        "coordinateTransform": {
            "metresPerTile": METRES_PER_TILE,
            "serverOrigin": list(SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": round(shell.floor_at(entrance.x, entrance.z), 3),
            "invertServerY": True,
            "addressableWorldBounds": {"min": [-HALF_EXTENT, -HALF_EXTENT],
                                       "max": [HALF_EXTENT, HALF_EXTENT]},
        },
        "spawnPoints": spawn_points,
        "collision": {"nodeNames": sorted(set(builder.collision_nodes))},
        "navigation": {
            "surfaceNodePrefixes": ["Terrain_"],
            "walkableAreas": ["cave_floor"],
            "navmesh": {"format": "surface-prefix-v1", "agentRadius": 0.55,
                        "agentHeight": 1.9, "maxSlopeDegrees": 42, "polygons": []},
            "note": ("The cavern floor carries the Terrain_ prefix so the "
                     "grounding raycast lands on it; the roof and the wall "
                     "skirt carry structural collision, which is what keeps a "
                     "player inside the system."),
        },
        "landmarks": builder.landmarks,
        "interactives": builder.interactives,
        "chambers": [{
            "id": chamber.id,
            "label": chamber.label,
            "position": [round(chamber.x, 2),
                         round(shell.floor_at(chamber.x, chamber.z), 2),
                         round(chamber.z, 2)],
            "radius": chamber.radius,
            "headroom": chamber.headroom,
            "serverTile": server_tile(chamber.x, chamber.z),
        } for chamber in spec["chambers"]],
        "materials": {
            "strategy": "shared-tileable-pbr-families-with-world-scale-uvs",
            "channelPacking": {"orm": "R=occlusion,G=roughness,B=metallic"},
            "embedded": True,
        },
        "environment": {
            "profile": "cave-interior",
            "sky": {"topColor": "#05060a", "horizonColor": "#0b0d14",
                    "groundHorizonColor": "#08090d",
                    "groundBottomColor": "#05060a",
                    "curve": 0.4, "sunAngleMax": 2.0, "energy": 0.35},
            "ambient": {"color": "#8a7fa8" if amethyst else "#9a8f7e",
                        "skyContribution": 0.0, "energy": 0.26},
            "sun": {"rotationDegrees": [-62, 8, 0],
                    "color": "#c8b8ff" if amethyst else "#ffd9a8",
                    "energy": 0.22, "indirectEnergy": 0.40, "shadows": False},
            "fog": {"enabled": True,
                    "color": "#241d33" if amethyst else "#241f19",
                    "density": 0.017, "skyAffect": 0.0,
                    "aerialPerspective": 0.30},
            "tonemap": {"mode": "filmic", "exposure": 1.20, "white": 2.0},
            "note": ("An interior profile: no sky contribution, dense short "
                     "fog and a low fill so the brazier and crystal markers "
                     "carry the lighting."),
        },
        "lighting": {
            "markers": builder.lights,
            "note": ("Braziers and, in the hollow, the crystal faces are the "
                     "light sources; they are emitted as named markers so a "
                     "client lighting pass can bind them without the package "
                     "depending on a glTF light extension."),
        },
        "minimap": {
            "image": "minimap.webp",
            "projection": "orthographic-top-down",
            "renderedFrom": "world.glb",
            "generator": ("godot-client/tests/integration/sunmane_cave_minimap.gd, "
                          "rendered through the client's own WorldLoader"),
            "northAxis": "-Z",
            "imageSize": [image, image],
            "worldMin": [-HALF_EXTENT, -HALF_EXTENT],
            "worldMax": [HALF_EXTENT, HALF_EXTENT],
            "pixelsPerMetre": round(image / span, 6),
            "transform": {
                "pixelX": {"scale": round(image / span, 6), "offset": image / 2.0},
                "pixelY": {"scale": round(image / span, 6), "offset": image / 2.0},
                "formula": ("pixel_x = world_x * scale + offset; "
                            "pixel_y = world_z * scale + offset"),
            },
        },
        "portals": [{
            "id": "exit-to-steppe",
            "kind": "map-transition",
            "position": [round(entrance.x, 2),
                         round(shell.floor_at(entrance.x, entrance.z), 2),
                         round(entrance.z + entrance.radius * 0.30, 2)],
            "serverTile": server_tile(entrance.x, entrance.z + entrance.radius * 0.30),
            "destinationMap": spec["returnMap"],
            "destinationTile": spec["returnTile"],
            "label": "Back out to the Sunmane Steppe",
        }],
        "provenance": {
            "generator": "eloria-assets/maps/nymara-regions/sunmane_steppe/source/caves.py",
            "surfaceMap": "eloria-assets/maps/nymara-regions/sunmane_steppe",
            "writtenDescription": [
                "eloria-assets/qa/regions/sunmane-steppe/README.md",
                "eloria-assets/NYMARA_ASSET_MANIFEST.md"],
            "license": "Original Eloria project work, CC-BY-4.0",
            "thirdPartyAssets": "none",
        },
        "statistics": statistics,
    }


# -------------------------------------------------------------------- main
def build_system(spec: dict, output: Path, texture_scale: float = 1.0) -> dict:
    started = time.time()
    shell = Shell(spec)
    builder = Builder(texture_scale=texture_scale)
    builder.lights = []
    amethyst = spec["palette"] == "amethyst"

    shell_materials = {
        "floor": builder.material(
            "cave_floor", "cavern",
            base_color=(0.62, 0.58, 0.54, 1.0) if not amethyst
            else (0.58, 0.52, 0.62, 1.0), roughness=0.93, normal_scale=1.0),
        "roof": builder.material(
            "cave_roof", "cavern",
            base_color=(0.44, 0.41, 0.39, 1.0) if not amethyst
            else (0.40, 0.35, 0.48, 1.0), roughness=0.95, normal_scale=1.1),
        "wall": builder.material(
            "cave_wall", "cavern",
            base_color=(0.54, 0.50, 0.46, 1.0) if not amethyst
            else (0.50, 0.44, 0.56, 1.0), roughness=0.94, normal_scale=1.2),
    }

    class _Materials(dict):
        def __missing__(self, key: str) -> int:
            specification = settlement.MATERIALS[key]
            family, color, metallic, roughness, double_sided = specification[:5]
            normal_map = specification[5] if len(specification) > 5 else True
            if len(specification) > 6:
                normal_map = specification[6]
            emissive = None
            if key == kit.CRYSTAL:
                # The amethyst is the hollow's own light: a soft emissive keeps
                # it readable in a chamber lit only by braziers. Underground it
                # is also darker than the sunlit badland crystal, which washes
                # out to white once the crystal lights fall on it.
                emissive = (0.16, 0.07, 0.28)
                color = (0.50, 0.36, 0.70, 1.0)
                roughness = 0.24
            value = builder.material(key, family, base_color=color,
                                     metallic=metallic, roughness=roughness,
                                     double_sided=double_sided,
                                     normal_map=normal_map, emissive=emissive)
            self[key] = value
            return value

    kit_materials = _Materials()
    statistics = build_shell(builder, shell, shell_materials)
    statistics.update(populate(builder, shell, shell_materials, kit_materials))
    if spec["water"]:
        water = builder.glb.material("cave_pool", base_color=(0.06, 0.20, 0.24, 1.0),
                                     metallic=0.05, roughness=0.18)
        statistics["waterTriangles"] = build_water(builder, shell, water)

    output.mkdir(parents=True, exist_ok=True)
    glb_bytes = builder.glb.write(output / "world.glb")
    statistics.update(builder.glb.statistics())
    statistics["glbBytes"] = glb_bytes
    statistics["buildSeconds"] = round(time.time() - started, 1)
    manifest = build_manifest(shell, builder, statistics)
    (output / "world.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "build-statistics.json").write_text(
        json.dumps(statistics, indent=2) + "\n")
    return statistics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=MAP_ROOT)
    parser.add_argument("--system", choices=sorted(SYSTEMS), action="append")
    arguments = parser.parse_args()
    wanted = arguments.system or sorted(SYSTEMS)
    report = {}
    for identifier in wanted:
        statistics = build_system(SYSTEMS[identifier],
                                  arguments.output / identifier)
        report[identifier] = statistics
        print(identifier, json.dumps(statistics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
