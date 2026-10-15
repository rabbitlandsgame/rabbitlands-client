"""Sculpted terrain, coastline, cliffs and water for the Four Gates region.

The region reads, from the centre outward, as: a walled civic plateau, a ring of
cliffs falling to a turquoise water ring, four causeways crossing it, and an
outer highland rim that rises into an alpine skyline with the northern mountain
sanctuary.  Elevations preserve the established gameplay datum so the existing
server coordinate binding keeps working: plateau walk height Y=31, water Y=-2.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Tuple

import numpy as np

import meshlib as M
from meshlib import Geo

TAU = math.pi * 2.0

# ------------------------------------------------------------------ constants
PLATEAU_Y = 31.0             # city walking datum (registry walkingHeight 31.15)
WATER_Y = -2.0               # turquoise ring surface
SEABED_Y = -26.0
WALL_RADIUS = 352.0          # curtain wall centre line (720 m defensive ring)
PLATEAU_EDGE = 372.0         # top of the cliff
CLIFF_FOOT = 432.0           # where the cliff meets the water
RIM_INNER = 592.0            # inner toe of the outer highland rim
RIM_CREST = 700.0            # rim crest
WORLD_EDGE = 792.0           # outer bound of authored terrain
CAUSEWAY_HALF = 15.0         # half width of the four causeway decks
CAUSEWAY_Y = 29.0
BRIDGE_NEAR = 424.0          # near abutment of each arched span
BRIDGE_FAR = 612.0           # far abutment on the outer rim
RIM_APPROACH_END = 664.0     # where the approach road starts climbing the rim
RIM_ROAD_Y = 62.0            # road level on the rim crest (portal height)
SANCTUARY_SHELF_R = 700.0    # radius of the northern sanctuary shelf
SANCTUARY_Y = 74.0
SANCTUARY_CLIMB_START = 616.0

WATERFALL_COUNT = 8
WATERFALL_START_DEG = 25.0
WATERFALL_STEP_DEG = 45.0


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class TerrainField:
    """Analytic height field with deterministic fractal detail."""

    def __init__(self, seed: int = 20260827):
        rng = np.random.default_rng(seed)
        # a handful of fixed sinusoidal bands gives repeatable, cheap detail
        self._phase = rng.uniform(0.0, TAU, (12,))
        self._freq = np.array([0.0032, 0.0051, 0.0087, 0.0134, 0.0208, 0.0331,
                               0.0043, 0.0069, 0.0112, 0.0177, 0.0281, 0.0412])
        self._dirx = np.cos(rng.uniform(0.0, TAU, (12,)))
        self._dirz = np.sin(rng.uniform(0.0, TAU, (12,)))
        self._amp = np.array([9.0, 6.0, 4.0, 2.4, 1.3, 0.7,
                              7.0, 5.0, 3.0, 1.8, 1.0, 0.5])

    def detail(self, x, z, octaves: int = 12) -> np.ndarray:
        total = np.zeros_like(np.asarray(x, dtype=np.float64))
        for i in range(octaves):
            total += self._amp[i] * np.sin(
                (x * self._dirx[i] + z * self._dirz[i]) * self._freq[i] * TAU
                + self._phase[i])
        return total / 3.2

    # ------------------------------------------------------------------ height
    def height(self, x, z) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        z = np.asarray(z, dtype=np.float64)
        r = np.hypot(x, z)
        theta = np.arctan2(z, x)
        detail = self.detail(x, z)

        # --- civic plateau: dead flat where the city stands, then a lip -------
        h = np.full(r.shape, PLATEAU_Y)

        # gentle terraces outside the wall, before the cliff
        terrace = PLATEAU_Y - 1.6 * _smoothstep(WALL_RADIUS + 4.0, PLATEAU_EDGE, r)
        h = np.where(r > WALL_RADIUS + 4.0, terrace, h)

        # --- cliff face down to the water ------------------------------------
        cliff_t = _smoothstep(PLATEAU_EDGE, CLIFF_FOOT, r)
        # a cubic ease makes the top lip crisp and the toe soft, like the art
        cliff_profile = cliff_t * cliff_t * (3.0 - 2.0 * cliff_t)
        cliff_h = (PLATEAU_Y - 1.6) + (SEABED_Y * 0.55 - (PLATEAU_Y - 1.6)) * cliff_profile
        scallop = np.sin(theta * 14.0) * 5.5 + np.sin(theta * 33.0) * 2.2
        cliff_h = cliff_h + scallop * cliff_t * (1.0 - cliff_t) * 3.4
        h = np.where(r > PLATEAU_EDGE, cliff_h, h)

        # --- basin floor ------------------------------------------------------
        basin = SEABED_Y + detail * 0.5 + 6.0 * np.sin(theta * 5.0) * 0.9
        basin_t = _smoothstep(CLIFF_FOOT, CLIFF_FOOT + 70.0, r)
        h = np.where(r > CLIFF_FOOT, cliff_h * (1.0 - basin_t) + basin * basin_t, h)

        # --- outer highland rim ----------------------------------------------
        rim_t = _smoothstep(RIM_INNER, RIM_CREST, r)
        rim_h = SEABED_Y * 0.5 + (58.0 - SEABED_Y * 0.5) * rim_t
        rim_h = rim_h + detail * rim_t * 1.9
        # scalloped bays and headlands along the rim shoreline
        bay = np.sin(theta * 9.0) * 26.0 + np.sin(theta * 4.0 + 1.1) * 34.0
        rim_shore = RIM_INNER + bay
        rim_t2 = _smoothstep(rim_shore, rim_shore + 96.0, r)
        rim_h2 = WATER_Y - 5.0 + (62.0 - (WATER_Y - 5.0)) * rim_t2 + detail * rim_t2 * 2.2
        rim_h = np.maximum(rim_h, rim_h2)
        h = np.where(r > RIM_INNER - 40.0, np.maximum(h, rim_h), h)

        # --- alpine skyline beyond the rim -----------------------------------
        # the rim swells northward into the massif that carries the sanctuary,
        # so the water ring stays continuous all the way round the island
        north = np.clip(-np.sin(theta), 0.0, 1.0) ** 1.4
        alp_t = _smoothstep(RIM_CREST - 40.0, WORLD_EDGE, r)
        ridges = (np.abs(np.sin(theta * 7.0 + 0.4)) * 0.55
                  + np.abs(np.sin(theta * 13.0 + 2.2)) * 0.3
                  + np.abs(np.sin(theta * 3.0)) * 0.35)
        alpine = (52.0 + alp_t * (52.0 + ridges * 34.0) * (1.0 + 0.50 * north)
                  + alp_t * 28.0 * north + detail * alp_t * 3.0)
        h = np.where(r > RIM_CREST - 40.0, np.maximum(h, alpine), h)

        # the sanctuary itself sits on a carved shelf cut into the massif
        shelf = np.hypot(x, z + 700.0)
        shelf_t = 1.0 - _smoothstep(62.0, 132.0, shelf)
        h = h * (1.0 - shelf_t) + SANCTUARY_Y * shelf_t

        # --- the four causeway embankments ------------------------------------
        h = self._apply_causeways(x, z, r, h)

        # --- world-edge barrier ridge -----------------------------------------
        edge_t = _smoothstep(WORLD_EDGE - 60.0, WORLD_EDGE + 10.0, r)
        h = h + edge_t * 46.0
        return h

    def _apply_causeways(self, x, z, r, h):
        """Flat approach embankments on each cardinal axis.

        The middle of each crossing is deliberately left as open water: the
        arched bridge geometry spans it, matching the concept art rather than
        damming the ring.  The north axis instead climbs the massif to the
        sanctuary shelf.
        """
        for axis in range(4):
            if axis == 0:      # south (+Z)
                across, along = np.abs(x), z
            elif axis == 1:    # north (-Z)
                across, along = np.abs(x), -z
            elif axis == 2:    # east (+X)
                across, along = np.abs(z), x
            else:              # west (-X)
                across, along = np.abs(z), -x
            width_t = 1.0 - _smoothstep(CAUSEWAY_HALF, CAUSEWAY_HALF + 18.0, across)

            far_end = SANCTUARY_CLIMB_START if axis == 1 else RIM_APPROACH_END
            near = (along > PLATEAU_EDGE - 34.0) & (along < BRIDGE_NEAR + 4.0)
            far = (along > BRIDGE_FAR - 4.0) & (along < far_end)
            deck = width_t * (near | far).astype(np.float64)
            h = h * (1.0 - deck) + CAUSEWAY_Y * deck

            if axis == 1:
                # the ceremonial climb to the northern sanctuary shelf: a long,
                # walkable grade rather than a cliff
                climb = _smoothstep(SANCTUARY_CLIMB_START, SANCTUARY_SHELF_R - 10.0,
                                    along)
                target = CAUSEWAY_Y + (SANCTUARY_Y - CAUSEWAY_Y) * climb
                band = width_t * ((along >= SANCTUARY_CLIMB_START)
                                  & (along < SANCTUARY_SHELF_R + 40.0)).astype(np.float64)
                h = h * (1.0 - band) + np.maximum(h, target) * band
            else:
                # the road cuts through the rim crest toward the map portal
                cut = _smoothstep(RIM_APPROACH_END, RIM_CREST + 26.0, along)
                target = CAUSEWAY_Y + (RIM_ROAD_Y - CAUSEWAY_Y) * cut
                band = width_t * ((along >= RIM_APPROACH_END)
                                  & (along < RIM_CREST + 30.0)).astype(np.float64)
                h = h * (1.0 - band) + target * band
        return h

    # --------------------------------------------------------------- surfacing
    def surface_material(self, points: np.ndarray, normals: np.ndarray,
                         mats: Dict[str, int]) -> np.ndarray:
        """Per-face terrain material from height, slope, radius and noise."""
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        slope = np.clip(normals[:, 1], -1.0, 1.0)
        r = np.hypot(x, z)
        theta = np.arctan2(z, x)
        wobble = (np.sin(theta * 11.0) * 7.0 + np.sin(theta * 23.0 + 1.4) * 4.0
                  + np.sin(r * 0.035) * 6.0 + np.sin(theta * 47.0 + 0.7) * 3.0
                  + np.sin(x * 0.021 + z * 0.017) * 8.0
                  + np.sin(x * 0.048 - z * 0.039 + 2.1) * 4.5)
        grain = (np.sin(x * 0.09 + z * 0.07) * 0.5
                 + np.sin(x * 0.031 - z * 0.052 + 1.3) * 0.5)

        out = np.full(x.shape, mats["terrain_grass"], dtype=np.int32)
        # anything meaningfully steep is exposed rock, wherever it is
        out = np.where(slope < 0.74 + grain * 0.06, mats["terrain_rock"], out)
        # shoreline sand where gentle land meets the ring
        sandy = (y < WATER_Y + 3.2 + grain * 1.2) & (y > WATER_Y - 7.0) & (slope > 0.80)
        out = np.where(sandy, mats["terrain_sand"], out)
        # sea floor
        out = np.where(y < WATER_Y - 7.0, mats["terrain_soil"], out)
        # alpine snow only on the high, gentler shoulders
        out = np.where((y > 178.0 + wobble * 2.0) & (slope > 0.55),
                       mats["terrain_snow"], out)
        # the city plateau itself stays dressed grass
        plateau = (r < WALL_RADIUS + 6.0) & (np.abs(y - PLATEAU_Y) < 2.0)
        out = np.where(plateau, mats["terrain_grass"], out)
        # the causeway embankments and the sanctuary shelf read as worn ground
        out = np.where((np.abs(y - CAUSEWAY_Y) < 0.8) & (r > PLATEAU_EDGE),
                       mats["terrain_soil"], out)
        return out


def build_terrain(field: TerrainField, mats: Dict[str, int]) -> Geo:
    """Radial terrain mesh: dense near the city, coarser toward the skyline."""
    inner = np.linspace(0.0, 300.0, 46)                    # plateau
    lip = np.linspace(304.0, PLATEAU_EDGE, 12)             # wall apron
    cliff = np.linspace(PLATEAU_EDGE + 2.0, CLIFF_FOOT + 30.0, 26)
    basin = np.linspace(CLIFF_FOOT + 40.0, RIM_INNER - 30.0, 20)
    rim = np.linspace(RIM_INNER - 24.0, RIM_CREST, 30)
    alpine = np.linspace(RIM_CREST + 12.0, WORLD_EDGE + 18.0, 22)
    radii = np.unique(np.concatenate([inner, lip, cliff, basin, rim, alpine]))
    geo = M.polar_surface(
        radii, 320, field.height,
        material_fn=lambda pts, nrm: field.surface_material(pts, nrm, mats),
        uv_scale=1.0, smooth=True, jitter=0.0)
    return geo


def build_water(mats: Dict[str, int]) -> Geo:
    """Turquoise ring surface plus the flat sea beyond the rim."""
    radii = np.concatenate([np.linspace(PLATEAU_EDGE - 20.0, CLIFF_FOOT, 6),
                            np.linspace(CLIFF_FOOT + 20.0, RIM_INNER + 60.0, 14)])
    ring = M.polar_surface(radii, 192, lambda X, Z: np.full_like(X, WATER_Y),
                           material=mats["water_turquoise"], uv_scale=1.0)
    return ring


def waterfall_positions() -> list:
    out = []
    for i in range(WATERFALL_COUNT):
        angle = math.radians(WATERFALL_START_DEG + WATERFALL_STEP_DEG * i)
        out.append((angle, math.cos(angle), math.sin(angle)))
    return out


def build_waterfall(field: TerrainField, mats: Dict[str, int], angle: float,
                    width: float = 26.0) -> Geo:
    """A sheet of falling water clinging to the sculpted cliff face.

    The sheet is placed by sampling the terrain along the radial line and
    standing it a little proud of the rock, so it never tunnels through the
    cliff or floats away from it.
    """
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    top_r = PLATEAU_EDGE - 6.0
    foot_r = CLIFF_FOOT - 4.0
    steps = 20
    radii = np.linspace(top_r, foot_r, steps + 1)
    heights = field.height(cos_a * radii, sin_a * radii)
    heights = np.minimum.accumulate(heights)          # water only ever falls
    heights = np.maximum(heights, WATER_Y + 0.4)
    proud = 1.6                                        # metres clear of the rock

    verts, faces = [], []
    for i in range(steps + 1):
        r = float(radii[i]) + proud
        y = float(heights[i])
        half = width * (0.5 + 0.34 * (i / steps))
        for side in (-1, 1):
            verts.append((cos_a * r - sin_a * half * side,
                          y, sin_a * r + cos_a * half * side))
    for i in range(steps):
        a0, a1 = i * 2, i * 2 + 1
        b0, b1 = (i + 1) * 2, (i + 1) * 2 + 1
        faces += [(a0, a1, b1), (a0, b1, b0)]
    sheet = M.make(verts, faces, mats["water_foam"], 1.0, smooth=True)
    fall = np.cumsum(np.abs(np.diff(np.concatenate([[heights[0]], heights]))))
    sheet.t = np.stack([
        np.where(np.arange(len(verts)) % 2 == 0, 0.0, 1.6),
        np.repeat(fall / 6.0, 2)], axis=1).astype(np.float32)
    parts = [sheet]

    inner = []
    for i in range(steps + 1):
        r = float(radii[i]) + proud * 0.5
        y = float(heights[i]) + 0.4
        half = width * (0.22 + 0.10 * (i / steps))
        for side in (-1, 1):
            inner.append((cos_a * r - sin_a * half * side,
                          y, sin_a * r + cos_a * half * side))
    jet = M.make(inner, faces, mats["water_foam"], 1.0, smooth=True)
    jet.t = sheet.t.copy()
    parts.append(jet)

    pool_r = width * 0.9
    pool = M.polar_surface(np.linspace(1.0, pool_r, 5), 20,
                           lambda X, Z: np.full_like(X, 0.0),
                           material=mats["water_foam"], uv_scale=4.0)
    pool.translate(cos_a * (foot_r + 6.0), WATER_Y + 0.14,
                   sin_a * (foot_r + 6.0))
    parts.append(pool)
    for k in range(3):
        spray = M.icosphere(5.0 - k * 1.1, 1, mats["water_foam"], 2.0, smooth=True)
        spray.scale(1.5, 0.5, 1.5)
        rr = foot_r + 3.0 + k * 6.0
        parts.append(spray.translate(cos_a * rr, WATER_Y + 0.9, sin_a * rr))

    lip = M.box(width * 1.35, 4.0, 12.0, mats["terrain_rock"], 3.0, origin="corner")
    lip.rotate_y(-angle)
    lip.translate(cos_a * (top_r + 1.0), float(heights[0]) - 3.2,
                  sin_a * (top_r + 1.0))
    parts.append(lip)
    for k in (-1, 1):
        rock = M.icosphere(6.5, 1, mats["terrain_rock"], 3.0, smooth=False)
        rock.scale(1.1, 0.85, 1.5)
        rr = foot_r + 4.0
        parts.append(rock.translate(
            cos_a * rr - sin_a * width * 0.78 * k, WATER_Y + 1.4,
            sin_a * rr + cos_a * width * 0.78 * k))
    return Geo.concat(parts)
