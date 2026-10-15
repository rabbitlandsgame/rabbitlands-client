"""Sculpted terrain for Amberwood.

The heightfield is authored with explicit shaping operators - ridges, basins,
carved watercourses, graded roads, coastal shelves - rather than left as raw
noise, so the aerial composition of the concept survives into the runtime mesh.
Surface material is assigned per grid cell, and the mesh is emitted as one
watertight sub-mesh per material: adjacent sub-meshes share identical vertex
positions, so the terrain has material variety with no cracks and no overlap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import mesh as M
from . import noise as N

# surface classes
FOREST = 0
PATH = 1
PAVING = 2
SHORE = 3
ROCK = 4
SCORCHED = 5
MEADOW = 6
SNOW = 7
ICE = 8
MARBLE = 9
TURF = 10

# -- Amethyst Barrens. Appended, never inserted: see the note on materials.SPECS.
# Classes are allocated in blocks so concurrent region work does not collide:
# 7-10 Mirrorhold, 11-14 Whitehorn, 15-18 Amethyst Barrens, 19-22 Crownwater,
# 23-27 Grey Moors, 28-29 Verdant Stair.
# Grey Moors and Verdant Stair both branched from a develop where 23 was free
# and both claimed it. Verdant Stair moved because Grey Moors needs five and
# this needs two, and because nothing outside terrain.py hardcodes the numbers:
# every reference here and in the region packages goes through these names.
BARRENS = 15
CRYSTAL_FIELD = 16
RESONANT_ROAD = 17
STORM_ROCK = 18

# -- Grey Moors. Five classes rather than four: the region needs a worn track
# distinct from its laid causeway, and reusing the generic PATH would have put
# Amberwood's amber leaf litter down the middle of a moor.
HEATHER_MOOR = 23
PEAT_BOG = 24
CAUSEWAY = 25
BARROW_TURF = 26
MOOR_TRACK = 27

# -- Verdant Stair. The region is a terraced limestone jungle, so its ground
# splits into two classes the existing set cannot express: the mossy cut stone
# of a terrace floor, which is laid rather than grown, and the permanently
# spray-wet rock behind a fall and around the cenote rim. Everything else it
# needs is an existing class carrying a different material.
TERRACE_MOSS = 28
WET_ROCK = 29

# -- Manymouth Delta. Promoted out of the region's own region.py, where it had
# claimed 23 and 24 privately and collided head-on with Grey Moors the moment
# both landed: two regions writing different names and materials into the same
# two slots of a shared table, each correct in isolation and wrong together.
# Every other region's classes live here for exactly that reason.
DELTA_SILT = 30
DELTA_PADDY = 31

SURFACE_NAMES = {
    FOREST: "ForestFloor", PATH: "Trail", PAVING: "Paving", SHORE: "Shore",
    ROCK: "Rock", SCORCHED: "Ash", MEADOW: "Meadow",
    SNOW: "Snow", ICE: "Ice", MARBLE: "Marble", TURF: "AlpineTurf",
    BARRENS: "Barrens", CRYSTAL_FIELD: "CrystalField",
    RESONANT_ROAD: "ResonantRoad", STORM_ROCK: "StormRock",
    HEATHER_MOOR: "HeatherMoor", PEAT_BOG: "PeatBog",
    CAUSEWAY: "Causeway", BARROW_TURF: "BarrowTurf",
    MOOR_TRACK: "MoorTrack",
    DELTA_SILT: "DeltaSilt", DELTA_PADDY: "Paddy",
    TERRACE_MOSS: "TerraceMoss", WET_ROCK: "WetRock",
}
SURFACE_MATERIALS = {
    FOREST: "forest_floor", PATH: "leaf_path", PAVING: "cobble_paving",
    SHORE: "shore_shingle", ROCK: "cliff_rock", SCORCHED: "scorched_ground",
    MEADOW: "meadow_grass",
    SNOW: "snow_pack", ICE: "glacier_ice", MARBLE: "veined_marble",
    TURF: "alpine_turf",
    BARRENS: "amethyst_barrens_dust", CRYSTAL_FIELD: "amethyst_crystal_field",
    RESONANT_ROAD: "amethyst_resonant_road", STORM_ROCK: "amethyst_storm_rock",
    HEATHER_MOOR: "grey_heather_moor", PEAT_BOG: "grey_peat_bog",
    CAUSEWAY: "grey_causeway", BARROW_TURF: "grey_barrow_turf",
    # A worn track is bare wet earth; the toolkit already has that texture, so
    # this class needs no new recipe - only a cooled, darkened material over it.
    MOOR_TRACK: "grey_moor_track",
    # Recipes live in manymouth_delta/source/deltakit.py, as Grey Moors' do in
    # its own kit; the shared table only needs the name.
    DELTA_SILT: "manymouth_silt", DELTA_PADDY: "manymouth_paddy",
    TERRACE_MOSS: "verdant_mossy_stone", WET_ROCK: "verdant_wet_limestone",
}

# Surfaces a region placed deliberately, which the slope and shore rules in
# `assign_surface_by_rule` must not overwrite. A region adding a class that it
# authors by hand adds it here too; extending this set is the supported way to
# do that, so nobody has to edit the rule itself.
AUTHORED_SURFACES: set[int] = {
    PATH, PAVING, SCORCHED, MEADOW,
    RESONANT_ROAD,
    # Grey Moors lays its causeways and cuts its peat by hand; the slope and
    # shore rules must not repaint either. The barrow turf is authored too -
    # a barrow is a built mound, not ground that happened to rise.
    CAUSEWAY, BARROW_TURF, MOOR_TRACK,
    # Verdant Stair lays both of these deliberately: a terrace floor is built,
    # and the wet rock is placed where a fall actually lands, not wherever the
    # slope rule happens to think the ground is steep.
    TERRACE_MOSS, WET_ROCK,
    # Both sit within a metre of the water line, which is exactly the band the
    # shore rule rewrites; without this every paddy terrace and mangrove flat
    # comes back as sand.
    DELTA_SILT, DELTA_PADDY,
}

# Surfaces whose border must stay crisp, so `dither_boundaries` leaves them
# alone. Paving and the resonant roadway read as laid, not grown.
# How much of a road's falloff the cut is feathered over, in `core` units. One
# cell of a 5 m road moves `core` by about 0.4, so this is roughly a cell
# either side of the edge: wide enough that the cut lands between samples
# rather than on one, narrow enough that the road keeps a crisp rim.
EDGE_FEATHER = 0.35

UNDITHERED_SURFACES: set[int] = {PAVING, RESONANT_ROAD, CAUSEWAY, TERRACE_MOSS}


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Smoothstep that also works when edge1 < edge0 (a descending ramp)."""
    span = edge1 - edge0
    if abs(span) < 1e-9:
        span = 1e-9 if span >= 0 else -1e-9
    t = np.clip((x - edge0) / span, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _polyline_distance(px: np.ndarray, pz: np.ndarray,
                       points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distance from each sample to a polyline, plus the arc-length parameter."""
    best = np.full(px.shape, 1e9)
    best_t = np.zeros(px.shape)
    lengths = np.concatenate([[0.0], np.cumsum(
        np.linalg.norm(np.diff(points, axis=0), axis=1))])
    total = max(lengths[-1], 1e-9)
    for i in range(points.shape[0] - 1):
        a = points[i]
        b = points[i + 1]
        ab = b - a
        denominator = float(np.dot(ab, ab))
        if denominator < 1e-12:
            continue
        t = ((px - a[0]) * ab[0] + (pz - a[1]) * ab[1]) / denominator
        t = np.clip(t, 0.0, 1.0)
        cx = a[0] + ab[0] * t
        cz = a[1] + ab[1] * t
        d = np.hypot(px - cx, pz - cz)
        closer = d < best
        best = np.where(closer, d, best)
        best_t = np.where(closer, (lengths[i] + t * math.hypot(*ab)) / total, best_t)
    return best, best_t


@dataclass
class Terrain:
    x0: float
    z0: float
    size_x: float
    size_z: float
    cell: float = 1.0

    def __post_init__(self) -> None:
        self.cols = int(round(self.size_x / self.cell)) + 1
        self.rows = int(round(self.size_z / self.cell)) + 1
        self.xs = self.x0 + np.arange(self.cols) * self.cell
        self.zs = self.z0 + np.arange(self.rows) * self.cell
        self.gx, self.gz = np.meshgrid(self.xs, self.zs)
        self.height = np.zeros((self.rows, self.cols))
        self.surface = np.full((self.rows, self.cols), FOREST, dtype=np.int32)
        # How firmly a sample belongs to its own class, 0 at a class edge and 1
        # well inside one. `build_meshes(blend_edges=True)` turns this into the
        # per-vertex coverage that lets a class boundary be cut where it really
        # falls rather than at the nearest cell corner. Operators that know
        # where their own edge is - a graded road, a plateau - write it; the
        # rest leave it at 1, which puts the cut half way between samples and
        # still reads as a diagonal rather than a staircase.
        self.surface_strength = np.ones((self.rows, self.cols))
        self.water_depth = np.zeros((self.rows, self.cols))
        self.tree_block = np.zeros((self.rows, self.cols), dtype=bool)
        self.wet = np.zeros((self.rows, self.cols))

    # -- shaping ----------------------------------------------------------
    def base_noise(self, amplitude: float, frequency: float, seed: int,
                   octaves: int = 5, warp: float = 0.0) -> None:
        u = self.gx * frequency
        v = self.gz * frequency
        field = N.warped_fbm(u, v, warp=warp, octaves=octaves, seed=seed) if warp > 0 \
            else N.fbm(u, v, octaves=octaves, seed=seed)
        self.height += (field - 0.5) * 2.0 * amplitude

    def add_slope(self, direction: tuple[float, float], gain: float,
                  origin: tuple[float, float] = (0.0, 0.0)) -> None:
        d = np.asarray(direction, dtype=np.float64)
        d /= max(np.linalg.norm(d), 1e-9)
        self.height += ((self.gx - origin[0]) * d[0] + (self.gz - origin[1]) * d[1]) * gain

    def add_dome(self, center: tuple[float, float], radius: float, height: float,
                 power: float = 2.0, noise_seed: int | None = None,
                 noise_amount: float = 0.0) -> None:
        d = np.hypot(self.gx - center[0], self.gz - center[1])
        if noise_seed is not None and noise_amount > 0.0:
            d = d + (N.fbm(self.gx * 0.05, self.gz * 0.05, seed=noise_seed) - 0.5) \
                * 2.0 * noise_amount * radius
        falloff = np.clip(1.0 - d / max(radius, 1e-6), 0.0, 1.0) ** power
        self.height += falloff * height

    def add_ridge(self, points, height: float, width: float, seed: int = 0,
                  roughness: float = 0.35, power: float = 1.6) -> None:
        points = np.asarray(points, dtype=np.float64)
        d, t = _polyline_distance(self.gx, self.gz, points)
        wobble = (N.fbm(self.gx * 0.045, self.gz * 0.045, seed=seed) - 0.5) * 2.0
        effective = width * (1.0 + roughness * wobble)
        profile = np.clip(1.0 - d / np.maximum(effective, 1e-6), 0.0, 1.0) ** power
        crest = 0.72 + 0.42 * N.fbm(t * 9.0, t * 3.0, seed=seed + 5)
        self.height += profile * height * crest

    def carve_channel(self, points, width: float, depth: float, bank: float = 2.4,
                      seed: int = 0, floor_height=None) -> np.ndarray:
        """Cut a watercourse. Returns the channel mask (1 at the thalweg)."""
        points = np.asarray(points, dtype=np.float64)
        d, t = _polyline_distance(self.gx, self.gz, points)
        wobble = (N.fbm(self.gx * 0.09, self.gz * 0.09, seed=seed) - 0.5) * 2.0
        effective = width * (1.0 + 0.30 * wobble)
        core = np.clip(1.0 - d / np.maximum(effective, 1e-6), 0.0, 1.0)
        outer = np.clip(1.0 - d / np.maximum(effective * bank, 1e-6), 0.0, 1.0)
        cut = core ** 0.8 * depth + (outer ** 2.4) * depth * 0.45
        if floor_height is not None:
            target = np.interp(t, np.linspace(0.0, 1.0, len(floor_height)), floor_height)
            blend = core ** 0.7
            self.height = self.height * (1.0 - blend) + target * blend
        else:
            self.height -= cut
        return core

    def grade_path(self, points, width: float, heights=None, shoulder: float = 2.2,
                   surface: int = PATH, seed: int = 0,
                   flatten: float = 0.9) -> np.ndarray:
        """Grade a road or trail: level the corridor and mark its surface class."""
        points = np.asarray(points, dtype=np.float64)
        d, t = _polyline_distance(self.gx, self.gz, points)
        wobble = (N.fbm(self.gx * 0.11, self.gz * 0.11, seed=seed) - 0.5) * 2.0
        effective = width * (1.0 + 0.22 * wobble)
        core = np.clip(1.0 - d / np.maximum(effective, 1e-6), 0.0, 1.0)
        outer = np.clip(1.0 - d / np.maximum(effective * shoulder, 1e-6), 0.0, 1.0)
        if heights is not None:
            target = np.interp(t, np.linspace(0.0, 1.0, len(heights)), heights)
        else:
            target = self._smoothed_along(points, d, t)
        blend = np.clip(core ** 0.55 * flatten + outer ** 3.0 * 0.35, 0.0, 1.0)
        self.height = self.height * (1.0 - blend) + target * blend
        mask = core > 0.32
        self.surface = np.where(mask, surface, self.surface)
        # The road's own edge, in the units the mesh split will cut on. `core`
        # falls off with distance from the centreline and the class changes
        # where it crosses 0.32, so how far a sample sits from that crossing is
        # how firmly it belongs to whichever side it is on.
        self._write_strength(np.abs(core - 0.32) / EDGE_FEATHER, outer > 0.0)
        self.tree_block |= outer > 0.22
        return core


    def _write_strength(self, strength: np.ndarray, where: np.ndarray) -> None:
        """Record how firmly the marked samples belong to their class.

        Written where an operator has a real edge to declare, and only when it
        is more certain than whatever is already there - a road crossing a
        courtyard should not soften the courtyard's own rim.
        """
        clamped = np.clip(strength, 0.0, 1.0)
        self.surface_strength = np.where(
            where, np.minimum(self.surface_strength, clamped), self.surface_strength)

    def _smoothed_along(self, points: np.ndarray, d: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Sample existing height along the polyline and smooth it into a grade."""
        samples = []
        lengths = np.concatenate([[0.0], np.cumsum(
            np.linalg.norm(np.diff(points, axis=0), axis=1))])
        total = max(lengths[-1], 1e-9)
        count = 48
        for i in range(count):
            s = i / (count - 1) * total
            index = int(np.searchsorted(lengths, s, side="right") - 1)
            index = min(max(index, 0), points.shape[0] - 2)
            span = max(lengths[index + 1] - lengths[index], 1e-9)
            local = (s - lengths[index]) / span
            p = points[index] + (points[index + 1] - points[index]) * local
            samples.append(self.height_at(p[0], p[1]))
        samples = np.asarray(samples)
        kernel = np.ones(9) / 9.0
        padded = np.pad(samples, (4, 4), mode="edge")
        smoothed = np.convolve(padded, kernel, mode="valid")
        return np.interp(t, np.linspace(0.0, 1.0, count), smoothed)

    def plateau(self, center: tuple[float, float], radius: float, height: float,
                edge: float = 6.0, surface: int | None = None,
                seed: int = 0, irregular: float = 0.18) -> np.ndarray:
        d = np.hypot(self.gx - center[0], self.gz - center[1])
        if irregular > 0.0:
            d = d * (1.0 + irregular * (N.fbm(self.gx * 0.07, self.gz * 0.07,
                                              seed=seed) - 0.5) * 2.0)
        # A yard's rim is a circle, and a circle cut to cell corners is a
        # staircase; how far a sample sits from that circle is what lets the
        # split put the cut on it.
        self._write_strength(np.abs(d - radius) / max(self.cell, 1e-6),
                             np.abs(d - radius) < self.cell * 2.0)
        blend = 1.0 - _smoothstep(radius - edge, radius + edge, d)
        self.height = self.height * (1.0 - blend) + height * blend
        if surface is not None:
            self.surface = np.where(blend > 0.55, surface, self.surface)
        return blend

    def terrace(self, center: tuple[float, float], radius: float, height: float,
                surface: int | None = None, shoulder: float = 0.0) -> None:
        """Hard-edged terrace with a retaining lip - reads as built, not eroded."""
        d = np.hypot(self.gx - center[0], self.gz - center[1])
        inside = d < radius
        if shoulder > 0:
            from .landscape import feather_level
            feather_level(self, d - radius, height, shoulder)
        else:
            self.height = np.where(inside, height, self.height)
        if surface is not None:
            self.surface = np.where(inside, surface, self.surface)
        self.tree_block |= d < radius + 1.5

    def rect_terrace(self, center: tuple[float, float], half_x: float, half_z: float,
                     height: float, rotation: float = 0.0,
                     surface: int | None = None, shoulder: float = 0.0) -> None:
        dx = self.gx - center[0]
        dz = self.gz - center[1]
        c, s = math.cos(-rotation), math.sin(-rotation)
        rx = dx * c - dz * s
        rz = dx * s + dz * c
        inside = (np.abs(rx) <= half_x) & (np.abs(rz) <= half_z)
        if shoulder > 0:
            from .landscape import feather_level
            feather_level(self, np.hypot(np.maximum(np.abs(rx) - half_x, 0),
                                        np.maximum(np.abs(rz) - half_z, 0)), height, shoulder)
        else:
            self.height = np.where(inside, height, self.height)
        if surface is not None:
            self.surface = np.where(inside, surface, self.surface)
        self.tree_block |= (np.abs(rx) <= half_x + 1.5) & (np.abs(rz) <= half_z + 1.5)

    def sea_shelf(self, shore_x, depth: float = 14.0, slope: float = 0.22,
                  side: str = "west") -> None:
        """Push everything to seaward of the shoreline below sea level.

        `side` names which way the water lies. Amberwood's coast is western;
        Amethyst Barrens' sea bites into the eastern corners, and mirroring the
        comparison is the whole of the difference.
        """
        if side not in ("west", "east"):
            raise ValueError(f"side must be 'west' or 'east', not {side!r}")
        shore = shore_x(self.gz) if callable(shore_x) else np.full(self.gz.shape, shore_x)
        if side == "west":
            offshore = np.clip(shore - self.gx, 0.0, None)
            seaward = self.gx < shore
        else:
            offshore = np.clip(self.gx - shore, 0.0, None)
            seaward = self.gx > shore
        self.height = np.where(
            seaward,
            np.minimum(self.height, -offshore * slope * (1.0 + offshore * 0.012)),
            self.height)
        self.height = np.maximum(self.height, -depth)

    def clamp_edges(self, margin: float, wall_height: float,
                    sides: tuple[str, ...] = ("west", "east", "north", "south")) -> None:
        """Raise a rim outside the playable footprint so nothing reaches a void.

        Sides can be omitted where another natural boundary already closes the
        world - Amberwood leaves the west open because the sea closes it.
        """
        rim = np.zeros_like(self.height)
        if "west" in sides:
            rim = np.maximum(rim, _smoothstep(self.x0 + margin, self.x0, self.gx))
        if "east" in sides:
            rim = np.maximum(rim, _smoothstep(self.x0 + self.size_x - margin,
                                              self.x0 + self.size_x, self.gx))
        if "south" in sides:
            rim = np.maximum(rim, _smoothstep(self.z0 + self.size_z - margin,
                                              self.z0 + self.size_z, self.gz))
        if "north" in sides:
            rim = np.maximum(rim, _smoothstep(self.z0 + margin, self.z0, self.gz))
        self.height += rim * wall_height

    def smooth(self, iterations: int = 1, weight: float = 0.5,
               mask: np.ndarray | None = None) -> None:
        for _ in range(iterations):
            padded = np.pad(self.height, 1, mode="edge")
            average = (padded[:-2, 1:-1] + padded[2:, 1:-1]
                       + padded[1:-1, :-2] + padded[1:-1, 2:]) * 0.25
            blended = self.height * (1.0 - weight) + average * weight
            self.height = np.where(mask, blended, self.height) if mask is not None else blended

    def erode(self, iterations: int = 24, strength: float = 0.35) -> None:
        """Cheap thermal erosion: shed material off slopes steeper than repose."""
        for _ in range(iterations):
            padded = np.pad(self.height, 1, mode="edge")
            deltas = [padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]]
            total = np.zeros_like(self.height)
            for neighbour in deltas:
                difference = self.height - neighbour
                total += np.clip(difference - self.cell * 0.9, 0.0, None)
            self.height -= total * strength * 0.25

    # -- queries ----------------------------------------------------------
    def height_at(self, x, z):
        fx = np.clip((np.asarray(x, dtype=np.float64) - self.x0) / self.cell,
                     0, self.cols - 1.001)
        fz = np.clip((np.asarray(z, dtype=np.float64) - self.z0) / self.cell,
                     0, self.rows - 1.001)
        x0 = fx.astype(int) if np.ndim(fx) else int(fx)
        z0 = fz.astype(int) if np.ndim(fz) else int(fz)
        tx = fx - x0
        tz = fz - z0
        h00 = self.height[z0, x0]
        h10 = self.height[z0, x0 + 1]
        h01 = self.height[z0 + 1, x0]
        h11 = self.height[z0 + 1, x0 + 1]
        return (h00 * (1 - tx) * (1 - tz) + h10 * tx * (1 - tz)
                + h01 * (1 - tx) * tz + h11 * tx * tz)

    def slope_at(self, x, z):
        eps = self.cell
        dx = self.height_at(np.asarray(x) + eps, z) - self.height_at(np.asarray(x) - eps, z)
        dz = self.height_at(x, np.asarray(z) + eps) - self.height_at(x, np.asarray(z) - eps)
        return np.hypot(dx, dz) / (2.0 * eps)

    def mesh_height_at(self, x, z):
        """Height on the triangles emitted by mesh.heightfield.

        Bilinear height_at is useful for terrain shaping, but on a saddle it
        can put a prop above the diagonal of the actual rendered floor.
        """
        fx = np.clip((np.asarray(x, dtype=np.float64) - self.x0) / self.cell,
                     0, self.cols - 1.001)
        fz = np.clip((np.asarray(z, dtype=np.float64) - self.z0) / self.cell,
                     0, self.rows - 1.001)
        ix, iz = np.asarray(fx, dtype=int), np.asarray(fz, dtype=int)
        u, v = fx - ix, fz - iz
        a, b = self.height[iz, ix], self.height[iz, ix + 1]
        c, d = self.height[iz + 1, ix], self.height[iz + 1, ix + 1]
        return np.where(u >= v, a * (1-u) + b * (u-v) + d * v,
                        a * (1-v) + c * (v-u) + d * u)

    def surface_at(self, x, z) -> np.ndarray:
        cx = np.clip(np.round((np.asarray(x) - self.x0) / self.cell).astype(int),
                     0, self.cols - 1)
        cz = np.clip(np.round((np.asarray(z) - self.z0) / self.cell).astype(int),
                     0, self.rows - 1)
        return self.surface[cz, cx]

    def blocked_at(self, x, z) -> np.ndarray:
        cx = np.clip(np.round((np.asarray(x) - self.x0) / self.cell).astype(int),
                     0, self.cols - 1)
        cz = np.clip(np.round((np.asarray(z) - self.z0) / self.cell).astype(int),
                     0, self.rows - 1)
        return self.tree_block[cz, cx]

    def mark_blocked_disc(self, center, radius: float) -> None:
        d = np.hypot(self.gx - center[0], self.gz - center[1])
        self.tree_block |= d < radius

    def assign_surface_by_rule(self, sea_level: float = 0.0) -> None:
        """Rock on steep ground, shore near the water line, keeping authored classes."""
        gradient_z, gradient_x = np.gradient(self.height, self.cell)
        slope = np.hypot(gradient_x, gradient_z)
        authored = np.isin(self.surface, sorted(AUTHORED_SURFACES))
        rocky = (slope > 1.05) & ~authored
        self.surface = np.where(rocky, ROCK, self.surface)
        shore_band = (self.height < sea_level + 1.6) & (self.height > sea_level - 6.0) \
            & ~authored
        noise = N.fbm(self.gx * 0.22, self.gz * 0.22, seed=4242)
        self.surface = np.where(shore_band & (noise > 0.34), SHORE, self.surface)
        self.surface = np.where(self.height < sea_level - 1.0, SHORE, self.surface)

    def dither_boundaries(self, seed: int = 99, amount: float = 0.55) -> None:
        """Break straight material borders into an organic edge."""
        noise = N.fbm(self.gx * 0.55, self.gz * 0.55, seed=seed)
        padded = np.pad(self.surface, 1, mode="edge")
        neighbours = np.stack([padded[:-2, 1:-1], padded[2:, 1:-1],
                               padded[1:-1, :-2], padded[1:-1, 2:]])
        different = neighbours != self.surface[None, :, :]
        boundary = different.any(axis=0)
        pick = np.where(noise > 1.0 - amount * 0.5, 1, 0)
        candidate = np.where(pick > 0, neighbours[0], neighbours[3])
        swap = boundary & (noise > 0.62)
        # never dither a built surface away from a road or courtyard
        protect = np.isin(self.surface, sorted(UNDITHERED_SURFACES))
        self.surface = np.where(swap & ~protect, candidate, self.surface)


    def despeckle_surfaces(self, min_cells: int = 6) -> int:
        """Give every class island smaller than `min_cells` to its surroundings.

        The class field is built by thresholding noise and then dithered at its
        boundaries, and both leave crumbs: a handful of cells of snow marooned
        in rock, a gap of turf in the middle of a road. At whole-quad ownership
        those read as a stray square and were easy to miss. Cut inside the cell
        they read as a deliberate blob, so they are worth clearing.

        Only the drawn class moves. Height does not, and neither does anything
        the walk grid is built from, so a package's collision is untouched.

        Returns the number of islands cleared.
        """
        cleared = 0
        while True:
            labels, counts = self._label_surfaces()
            small = [label for label, count in enumerate(counts)
                     if 0 < count < min_cells]
            if not small:
                return cleared
            moved = False
            for label in small:
                rows, columns = np.nonzero(labels == label)
                if rows.size == 0:
                    continue
                own = self.surface[rows[0], columns[0]]
                # Whatever holds the most of the island's border takes it.
                border: dict[int, int] = {}
                for row, column in zip(rows, columns):
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        r, c = row + dr, column + dc
                        if not (0 <= r < self.rows and 0 <= c < self.cols):
                            continue
                        neighbour = int(self.surface[r, c])
                        if neighbour != own:
                            border[neighbour] = border.get(neighbour, 0) + 1
                if not border:
                    continue
                winner = max(sorted(border), key=lambda key: border[key])
                self.surface[rows, columns] = winner
                cleared += 1
                moved = True
            if not moved:
                return cleared

    def _label_surfaces(self) -> tuple[np.ndarray, list[int]]:
        """Label four-connected runs of one class. Returns labels and sizes."""
        labels = np.full((self.rows, self.cols), -1, dtype=np.int32)
        counts: list[int] = []
        for row in range(self.rows):
            for column in range(self.cols):
                if labels[row, column] >= 0:
                    continue
                own = self.surface[row, column]
                label = len(counts)
                stack = [(row, column)]
                labels[row, column] = label
                size = 0
                while stack:
                    y, x = stack.pop()
                    size += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if not (0 <= ny < self.rows and 0 <= nx < self.cols):
                            continue
                        if labels[ny, nx] >= 0 or self.surface[ny, nx] != own:
                            continue
                        labels[ny, nx] = label
                        stack.append((ny, nx))
                counts.append(size)
        return labels, counts

    # -- export -----------------------------------------------------------
    def build_feathered_meshes(self, base_surface: int, uv_scale: float = .30,
                              materials: dict[int,str] | None = None,
                              feather_metres: float = 1.5) -> dict[str,M.Mesh]:
        """Opaque terrain below soft material coverage, with no possible holes.

        Opt-in for lowland soil/grass transitions. Architecture still uses its
        ordinary opaque material. Overlay vertices carry smoothed coverage;
        the client gives these named materials depth-writing hash coverage.
        Heights are unchanged apart from centimetre offsets avoiding coplanarity.
        """
        from .materials import SOFT_GROUND_SUFFIX
        table=dict(SURFACE_MATERIALS);table.update(materials or {})
        base=M.heightfield(self.height,self.x0,self.z0,self.cell,
            uv_scale=uv_scale,material=table[base_surface])
        base.recompute_normals(180.)
        out={'Terrain_Base':base}
        passes=max(1,round((feather_metres/self.cell)**2*2))
        for order,surface_id in enumerate(sorted(set(np.unique(self.surface))-{base_surface})):
            coverage=(self.surface==surface_id).astype(float)
            # Separable binomial filtering expands the material edge gently.
            # Edge padding keeps the exterior border covered without wrapping.
            for _ in range(passes):
                p=np.pad(coverage,((1,1),(0,0)),mode='edge')
                coverage=(p[:-2]+2*p[1:-1]+p[2:])/4
                p=np.pad(coverage,((0,0),(1,1)),mode='edge')
                coverage=(p[:,:-2]+2*p[:,1:-1]+p[:,2:])/4
            active=coverage>.005
            touched=active[:-1,:-1]|active[1:,:-1]|active[:-1,1:]|active[1:,1:]
            part=M.heightfield(self.height,self.x0,self.z0,self.cell,uv_scale=uv_scale,
                material=table[surface_id]+SOFT_GROUND_SUFFIX,cells=touched)
            part=_compact(part)
            if not part.triangle_count:continue
            columns=np.clip(np.rint((part.positions[:,0]-self.x0)/self.cell).astype(int),0,self.cols-1)
            rows=np.clip(np.rint((part.positions[:,2]-self.z0)/self.cell).astype(int),0,self.rows-1)
            part.colors=np.ones((part.vertex_count,4));part.colors[:,3]=coverage[rows,columns]
            part.positions[:,1]+=.008*(order+1)
            part.recompute_normals(180.)
            out['Terrain_'+SURFACE_NAMES[surface_id]]=part
        return out

    def build_meshes(self, uv_scale: float = 0.30,
                     name_prefix: str = "Terrain_",
                     materials: dict[int, str] | None = None,
                     blend_edges: bool = False,
                     material_suffix: str = "") -> dict[str, M.Mesh]:
        """One sub-mesh per surface class; shared vertices means no cracks.

        `materials` overrides the surface-class to material mapping for regions
        whose ground is not Amberwood's. A snow region's PATH is not a leaf
        path, and the class itself is what the terrain operators speak in.

        `blend_edges` cuts the classes against each other inside the cell
        instead of at its corners. A class then takes every quad it touches
        rather than only the quads it owns, and carries a per-vertex coverage
        in COLOR_0's alpha: 1 where the class holds, 0 where it does not, moved
        off the half-way mark by `surface_strength` wherever an operator knew
        where its own edge was. Drawn with an alpha-tested material, each pixel
        goes to whichever class covers it, so a diagonal road reads as a
        diagonal instead of a flight of two-metre steps. Coverage is
        complementary across a two-class edge, so the pair neither overlap nor
        leave a gap, and the cut is opaque - it writes depth and sorts like any
        other ground. `material_suffix` names the alpha-tested variants.
        """
        table = dict(SURFACE_MATERIALS)
        if materials:
            table.update(materials)
        out: dict[str, M.Mesh] = {}
        for surface_id, label in SURFACE_NAMES.items():
            cells = self.surface == surface_id
            if not cells.any():
                continue
            # Quad selection, not a vertex mask. A quad belongs to the class of
            # its low corner and to no other, so every cell is drawn exactly
            # once across the whole set of sub-meshes. Selecting by vertex
            # instead also emitted every quad whose four corners happened to
            # touch this class - which, after the boundary dither, is most of a
            # class edge - and those duplicates z-fought with the sub-mesh that
            # legitimately owned them. Vertices stay shared, so there are still
            # no cracks between classes.
            material = table[surface_id] + material_suffix
            if blend_edges:
                # Every quad the class touches, not only the ones it owns.
                touched = (cells[:-1, :-1] | cells[:-1, 1:]
                           | cells[1:, :-1] | cells[1:, 1:])
                piece = M.heightfield(self.height, self.x0, self.z0, self.cell,
                                      uv_scale=uv_scale, material=material,
                                      cells=touched)
                piece = _compact(piece)
                if piece.triangle_count == 0:
                    continue
                piece = _with_coverage(piece, self, cells)
            else:
                piece = M.heightfield(self.height, self.x0, self.z0, self.cell,
                                      uv_scale=uv_scale, material=material,
                                      cells=cells[:-1, :-1])
                piece = _compact(piece)
            if piece.triangle_count == 0:
                continue
            piece.recompute_normals(180.0)
            out[f"{name_prefix}{label}"] = piece
        return out


def _with_coverage(mesh: M.Mesh, terrain: "Terrain",
                   cells: np.ndarray) -> M.Mesh:
    """Put this class's per-vertex coverage into the mesh's vertex colours.

    Coverage is 0.5 at the class edge and runs to 1 inside the class and 0
    outside it, so an alpha test at 0.5 cuts exactly on the edge. How fast it
    runs is `surface_strength`: at 1 - no operator had anything to say - the
    cut lands half way between two samples, which turns a corner staircase into
    a diagonal. Where a road or a rim wrote its own distance the cut lands on
    the real edge, and the road keeps its width between the samples.

    Colours are white apart from the alpha: the material multiplies albedo by
    them, and tinting the ground was not the point.
    """
    columns = np.clip(np.round(
        (mesh.positions[:, 0] - terrain.x0) / terrain.cell).astype(int),
        0, terrain.cols - 1)
    rows = np.clip(np.round(
        (mesh.positions[:, 2] - terrain.z0) / terrain.cell).astype(int),
        0, terrain.rows - 1)
    inside = cells[rows, columns]
    strength = terrain.surface_strength[rows, columns]
    coverage = np.where(inside, 0.5 + 0.5 * strength, 0.5 - 0.5 * strength)
    colours = np.ones((mesh.vertex_count, 4), dtype=np.float64)
    colours[:, 3] = coverage
    return M.Mesh(mesh.positions, mesh.normals, mesh.uvs, colours,
                  mesh.indices, mesh.material)


def _compact(mesh: M.Mesh) -> M.Mesh:
    """Drop vertices no triangle references."""
    if mesh.triangle_count == 0:
        return M.Mesh(material=mesh.material)
    used = np.unique(mesh.indices)
    remap = np.full(mesh.vertex_count, -1, dtype=np.int64)
    remap[used] = np.arange(used.shape[0])
    return M.Mesh(mesh.positions[used], mesh.normals[used], mesh.uvs[used],
                  None if mesh.colors is None else mesh.colors[used],
                  remap[mesh.indices], mesh.material)


def water_plane(terrain: Terrain, level: float, x0: float, z0: float, x1: float, z1: float,
                material: str = "water_sea", cell: float = 4.0,
                only_below: bool = True, margin: float = 0.35,
                outside_is_water: bool = False) -> M.Mesh:
    """Water surface clipped to where the terrain is actually below the level.

    `outside_is_water` keeps the surface where the sample falls outside the
    terrain grid, so the open sea can run past the authored coast to a horizon.
    """
    cols = max(int(round((x1 - x0) / cell)) + 1, 2)
    rows = max(int(round((z1 - z0) / cell)) + 1, 2)
    xs = np.linspace(x0, x1, cols)
    zs = np.linspace(z0, z1, rows)
    gx, gz = np.meshgrid(xs, zs)
    heights = np.full((rows, cols), level)
    mask = None
    if only_below:
        ground = terrain.height_at(gx, gz)
        mask = ground < level - margin
        if outside_is_water:
            outside = ((gx < terrain.x0 + 1.0) | (gx > terrain.x0 + terrain.size_x - 1.0)
                       | (gz < terrain.z0 + 1.0) | (gz > terrain.z0 + terrain.size_z - 1.0))
            mask = mask | outside
    piece = M.heightfield(heights, x0, z0, cell, uv_scale=0.09, material=material, mask=mask)
    piece = _compact(piece)
    if piece.triangle_count:
        piece.uvs = np.stack([piece.positions[:, 0] * 0.09, piece.positions[:, 2] * 0.09],
                             axis=-1)
        piece.recompute_normals(180.0)
    return piece


def backdrop(terrain: Terrain, reach: float = 150.0, cell: float = 7.0,
             seed: int = 4242, material: str = "cliff_rock",
             sea_level: float = 0.0, open_side: str | None = "west",
             clip_interior: bool = False) -> M.Mesh:
    """Coarse distant land beyond the authored terrain.

    The playable region is closed by mountain walls and by the sea; this ring
    gives those walls something to stand in front of, so an aerial or a hilltop
    view sees continuing country instead of a cut edge and empty sky. Its inner
    boundary samples the authored terrain's own edge height, so the two meet
    without a seam. It is not a walk surface and is never reachable.
    """
    x0 = terrain.x0 - reach
    z0 = terrain.z0 - reach
    x1 = terrain.x0 + terrain.size_x + reach
    z1 = terrain.z0 + terrain.size_z + reach
    cols = int((x1 - x0) / cell) + 1
    rows = int((z1 - z0) / cell) + 1
    xs = x0 + np.arange(cols) * cell
    zs = z0 + np.arange(rows) * cell
    gx, gz = np.meshgrid(xs, zs)

    inner_x1 = terrain.x0 + terrain.size_x
    inner_z1 = terrain.z0 + terrain.size_z
    dx = np.maximum(np.maximum(terrain.x0 - gx, gx - inner_x1), 0.0)
    dz = np.maximum(np.maximum(terrain.z0 - gz, gz - inner_z1), 0.0)
    outside = np.hypot(dx, dz)
    # Signed version: negative inside the authored terrain. `outside` is
    # clamped at zero, so it cannot express "how far in", which is why the
    # mask below could never exclude the interior.
    inset = np.minimum(np.minimum(gx - terrain.x0, inner_x1 - gx),
                       np.minimum(gz - terrain.z0, inner_z1 - gz))
    signed = np.where(outside > 0.0, outside, -np.maximum(inset, 0.0))

    # nearest point on the authored terrain, clamped just inside its border
    near_x = np.clip(gx, terrain.x0 + 0.5, inner_x1 - 0.5)
    near_z = np.clip(gz, terrain.z0 + 0.5, inner_z1 - 0.5)
    edge_height = terrain.height_at(near_x, near_z)

    ridge = N.ridged(gx * 0.011, gz * 0.011, octaves=5, seed=seed)
    rough = N.fbm(gx * 0.030, gz * 0.030, octaves=4, seed=seed + 11)
    distant = 22.0 + ridge * 56.0 + rough * 12.0
    # A region whose world is open on one side - Amberwood's sea - wants the
    # distant land to fall away there instead of walling the view.
    if open_side == "west":
        fall = np.clip((terrain.x0 + 20.0 - gx) / 70.0, 0.0, 1.0)
    elif open_side == "east":
        fall = np.clip((gx - inner_x1 + 20.0) / 70.0, 0.0, 1.0)
    elif open_side == "north":
        fall = np.clip((terrain.z0 + 20.0 - gz) / 70.0, 0.0, 1.0)
    elif open_side == "south":
        fall = np.clip((gz - inner_z1 + 20.0) / 70.0, 0.0, 1.0)
    else:
        fall = np.zeros_like(gx)
    distant = distant * (1.0 - fall) - 26.0 * fall

    blend = 1.0 - np.exp(-outside / 42.0)
    height = edge_height * (1.0 - blend) + distant * blend
    # tuck the shared border a little under the authored terrain so the two
    # surfaces overlap instead of leaving a hairline of sky between them
    height -= 1.1 * np.exp(-outside / 9.0)

    # Keep a couple of cells of overlap under the authored terrain so the two
    # surfaces meet without a hairline of sky, and - when asked - nothing
    # further in. Without clipping, a region whose border stands higher than
    # its middle has this coarse sheet poking up through its own slopes.
    mask = signed > -cell * 2.2 if clip_interior else np.ones_like(gx, dtype=bool)
    piece = M.heightfield(height, x0, z0, cell, uv_scale=0.05, material=material,
                          mask=mask)
    piece = _compact(piece)
    if piece.triangle_count:
        piece.recompute_normals(180.0)
    return piece
