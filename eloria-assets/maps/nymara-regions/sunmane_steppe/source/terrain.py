"""Sunmane Steppe terrain: heightfield, coastline, mesas and terrain classes.

The region is a 280 m square offset around the server arrival datum (58, 58),
which the client's coordinate adapter maps to Godot (0, 0) at one metre per
tile.  North is -Z.

Composition follows the aerial overview: a broad sunlit grassland carrying the
fortified encampment on a low central rise, flat-topped mesas along the north
and east, a rugged coastline with two bays on the west and south-west, and a
stream chain feeding waterholes across the open steppe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from noise import fbm, normalise
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
import layout as DESIGN

# The world is a square, but it is not centred on the arrival datum. Server
# tiles are non-negative, so with the datum at (58, 58) the addressable band
# runs Godot X -58..133 and Z -133..58. The world is offset to contain that
# band and then extended past it, north and east, for the desert basin and the
# mountain skyline a player can see but never walk into.
CENTRE = (36.0, -36.0)       # world centre in Godot XZ
HALF_EXTENT = 140.0          # metres from CENTRE to the world edge
CELL = 1.4                   # heightfield spacing in metres (201 x 201)
CHUNKS = 10                  # terrain chunks per axis

# Addressable band, so placement code and validation can both check it.
ADDRESSABLE_MIN = (-58.0, -133.0)
ADDRESSABLE_MAX = (133.0, 58.0)
SEA_LEVEL = 0.0
BEACH_LEVEL = 0.9

# Terrain classes, in the order the region description lists them.
# How much of a road's falloff the cut is feathered over. One cell of a road
# moves the falloff by roughly this much, so the cut lands between samples
# rather than on one, and the road keeps a crisp rim.
ROUTE_EDGE_FEATHER = 0.35
# Class islands smaller than this are given to whatever surrounds them. Twelve
# 1.4 m cells is about 24 m2, the same ground a six-cell island covers on the
# two-metre regions - smaller than any surface a player reads as its own thing.
DESPECKLE_MIN_CELLS = 12

CLASS_CLEARING = 0           # packed earth inside the clan camps
CLASS_STEPPE = 1             # open grazing steppe
CLASS_ROAD = 2               # caravan roads and riding trails
CLASS_DRY_GRASS = 3          # sun-bleached dry grass and crop ground
CLASS_ROCK = 4               # mesa tops, cliffs and shore rock
CLASS_SAND = 5               # beaches and dry stream beds
CLASS_DESERT = 6             # the dune field and salt pans north of the steppe
CLASS_BADLAND = 7            # violet Amethyst-influenced badland rock
CLASS_MOUNTAIN = 8           # the mountain boundary's scree and bare stone

CLASS_NAMES = {
    CLASS_CLEARING: "clan_clearing",
    CLASS_STEPPE: "open_steppe",
    CLASS_ROAD: "caravan_road",
    CLASS_DRY_GRASS: "dry_grass",
    CLASS_ROCK: "shore_rock",
    CLASS_SAND: "beach_sand",
    CLASS_DESERT: "desert_sand",
    CLASS_BADLAND: "amethyst_badland",
    CLASS_MOUNTAIN: "mountain_scree",
}

# Base-colour multipliers applied to the shared ground detail map so each class
# reads distinctly while sharing one texture and one texel density.
# glTF requires baseColorFactor in 0..1, so the ground detail map is authored a
# little brighter than final and every class sits at or below unity here.
CLASS_TINT = {
    CLASS_CLEARING: (0.80, 0.68, 0.48, 1.0),
    CLASS_STEPPE: (0.88, 0.82, 0.50, 1.0),
    CLASS_ROAD: (0.92, 0.74, 0.48, 1.0),
    CLASS_DRY_GRASS: (1.00, 0.90, 0.48, 1.0),
    CLASS_ROCK: (0.76, 0.65, 0.50, 1.0),
    CLASS_SAND: (0.98, 0.90, 0.74, 1.0),
    # The desert reads paler and pinker than the steppe; the badlands carry the
    # Amethyst Barrens' violet, muted so it stays a neighbour's influence rather
    # than a second region; the mountains are cool bare stone.
    CLASS_DESERT: (1.00, 0.86, 0.62, 1.0),
    CLASS_BADLAND: (0.78, 0.68, 0.74, 1.0),
    CLASS_MOUNTAIN: (0.60, 0.58, 0.60, 1.0),
}


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - edge0) / max(edge1 - edge0, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _falloff(distance: np.ndarray, inner: float, outer: float) -> np.ndarray:
    """1 inside `inner`, smoothly to 0 by `outer`."""
    return 1.0 - _smoothstep(inner, outer, distance)


@dataclass
class Landform:
    """Sampled terrain: heights, per-vertex class and derived masks."""
    x: np.ndarray                 # (n,) world X coordinates
    z: np.ndarray                 # (n,) world Z coordinates
    height: np.ndarray            # (n, n) elevation
    classes: np.ndarray           # (n, n) terrain class index
    water: np.ndarray             # (n, n) True where sea or pond covers ground
    # How firmly a sample belongs to its own class, 0 at a class edge and 1
    # well inside one. `terrain_mesh.build_chunks` turns this into the
    # per-vertex coverage that lets a class boundary be cut where it really
    # falls rather than at the nearest cell corner. The roads know where their
    # own edge is and write it; everything else leaves it at 1, which puts the
    # cut half way between samples and still reads as a diagonal rather than a
    # staircase.
    strength: np.ndarray = None

    def sample(self, world_x, world_z) -> np.ndarray:
        """Bilinear height lookup in world space."""
        fx = np.clip((np.asarray(world_x, dtype="float64") - self.x[0]) / CELL,
                     0.0, len(self.x) - 1.001)
        fz = np.clip((np.asarray(world_z, dtype="float64") - self.z[0]) / CELL,
                     0.0, len(self.z) - 1.001)
        x0, z0 = fx.astype(int), fz.astype(int)
        tx, tz = fx - x0, fz - z0
        h00 = self.height[z0, x0]
        h10 = self.height[z0, x0 + 1]
        h01 = self.height[z0 + 1, x0]
        h11 = self.height[z0 + 1, x0 + 1]
        return (h00 * (1 - tx) * (1 - tz) + h10 * tx * (1 - tz)
                + h01 * (1 - tx) * tz + h11 * tx * tz)

    def height_at(self, world_x: float, world_z: float) -> float:
        return float(self.sample(world_x, world_z))

    def class_at(self, world_x: float, world_z: float) -> int:
        ix = int(np.clip((world_x - self.x[0]) / CELL, 0, len(self.x) - 1))
        iz = int(np.clip((world_z - self.z[0]) / CELL, 0, len(self.z) - 1))
        return int(self.classes[iz, ix])

    def index_of(self, world_x: float, world_z: float) -> tuple[int, int]:
        """Nearest grid index for a world position, clamped to the grid."""
        return (int(np.clip((world_z - self.z[0]) / CELL, 0, len(self.z) - 1)),
                int(np.clip((world_x - self.x[0]) / CELL, 0, len(self.x) - 1)))


# --------------------------------------------------------------------- routes
# Caravan roads radiating from the ceremonial crossroads at the datum. Each is
# a polyline in world XZ; the settlement ring road closes around the palisade.
CAMP_CENTER = (0.0, 0.0)
CAMP_RADIUS = 30.0

ROADS = DESIGN.ROADS
FIELDS = DESIGN.FIELDS

# Wind-carved badland spires, placed as instanced rock. Terrain only raises a
# low plinth under each one.
SPIRE_SITES = ((118.0, -112.0, 3.4), (126.0, -104.0, 2.8), (100.0, -128.0, 3.0),
               (148.0, -112.0, 3.2), (86.0, -134.0, 2.6), (138.0, -88.0, 2.9),
               (110.0, -76.0, 3.1), (152.0, -136.0, 2.7))

# The four Orun clan camps ring the shared market at the ceremonial crossroads.
CAMP_CLEARINGS = ((-30.0, -40.0, 12.5), (46.0, -26.0, 11.5),
                  (64.0, 20.0, 11.5), (-40.0, 34.0, 11.5))

ROAD_WIDTH = 5.0
TRAIL_WIDTH = 2.6

# Secondary riding trails linking outlying sites to the road network.
TRAILS = DESIGN.TRAILS


def _polyline_distance(px: np.ndarray, pz: np.ndarray, path) -> np.ndarray:
    """Distance from every grid point to a polyline."""
    best = np.full(px.shape, 1e9)
    for index in range(len(path) - 1):
        ax, az = path[index]
        bx, bz = path[index + 1]
        dx, dz = bx - ax, bz - az
        length_squared = dx * dx + dz * dz
        if length_squared < 1e-9:
            continue
        t = np.clip(((px - ax) * dx + (pz - az) * dz) / length_squared, 0.0, 1.0)
        best = np.minimum(best, np.hypot(px - (ax + t * dx), pz - (az + t * dz)))
    return best


def _warp(gx, gz, field, amount: float):
    """Domain-warp a coordinate pair so stamped shapes lose their machined edges."""
    return gx + (field[0] - 0.5) * amount, gz + (field[1] - 0.5) * amount


def _blob_distance(gx, gz, cx, cz, radius, lobes, phase, roughness):
    """Distance to an irregular closed shape, normalised so 1.0 is its edge."""
    dx, dz = gx - cx, gz - cz
    distance = np.hypot(dx, dz)
    angle = np.arctan2(dz, dx)
    modulation = 1.0
    for index, (harmonic, weight) in enumerate(lobes):
        modulation = modulation + weight * np.sin(harmonic * angle + phase * (index + 1))
    modulation = modulation + roughness
    return distance / np.maximum(radius * modulation, 1e-6)


def build(seed: int = 20260827, pads=()) -> Landform:
    """Sculpt the region heightfield and assign terrain classes."""
    count = int(round(HALF_EXTENT * 2 / CELL)) + 1
    x_axis = np.linspace(CENTRE[0] - HALF_EXTENT, CENTRE[0] + HALF_EXTENT, count)
    z_axis = np.linspace(CENTRE[1] - HALF_EXTENT, CENTRE[1] + HALF_EXTENT, count)
    gx, gz = np.meshgrid(x_axis, z_axis)             # gz varies down the rows

    detail = int(2 ** math.ceil(math.log2(count)))

    def noise(period: int, octaves: int, offset: int) -> np.ndarray:
        field = fbm(detail, period, octaves, np.random.default_rng(seed + offset))
        return field[:count, :count]

    # Two warp fields reused throughout so every stamped landform inherits the
    # same organic distortion instead of reading as a stencil.
    warp_a = (noise(6, 4, 101), noise(6, 4, 102))
    warp_b = (noise(14, 4, 103), noise(14, 4, 104))
    wx, wz = _warp(gx, gz, warp_a, 26.0)
    fx, fz = _warp(gx, gz, warp_b, 9.0)

    # --- rolling steppe base -------------------------------------------
    height = 4.0 + noise(4, 5, 1) * 7.0 + noise(11, 4, 2) * 2.4 + noise(27, 3, 3) * 0.9
    # Long shallow swales so the grassland is not a pancake.
    height += np.sin(gx * 0.032 + gz * 0.018 + 0.7) * 1.9
    height += np.cos(gz * 0.041 - gx * 0.012) * 1.4

    # --- low central rise carrying the encampment ----------------------
    camp_distance = np.hypot(gx - CAMP_CENTER[0], gz - CAMP_CENTER[1])
    warped_camp = np.hypot(wx - CAMP_CENTER[0], wz - CAMP_CENTER[1])
    height += 3.8 * _falloff(warped_camp, 28.0, 68.0)
    plateau = _falloff(camp_distance, 24.0, 33.0)
    height = height * (1.0 - plateau) + 9.6 * plateau

    # --- northern and eastern mesas -------------------------------------
    # (x, z, radius, cap fraction, top height, lobe set, phase)
    mesas = (
        (-20.0, -80.0, 27.0, 0.56, 25.5, ((3, 0.16), (5, 0.09), (7, 0.05)), 0.4),
        (18.0, -90.0, 21.0, 0.52, 22.5, ((3, 0.19), (4, 0.11), (8, 0.06)), 2.1),
        (60.0, -68.0, 19.0, 0.50, 21.5, ((2, 0.21), (5, 0.10), (9, 0.05)), 4.3),
        (-64.0, -62.0, 16.0, 0.48, 19.0, ((3, 0.17), (6, 0.12)), 1.2),
        (78.0, -14.0, 17.0, 0.44, 18.5, ((2, 0.24), (5, 0.12)), 3.0),
        (80.0, 30.0, 15.0, 0.42, 16.5, ((3, 0.20), (7, 0.09)), 5.4),
        (68.0, 64.0, 14.0, 0.40, 15.0, ((2, 0.22), (6, 0.10)), 0.9),
    )
    rock_stamp = np.zeros_like(height)
    for mx, mz, radius, inner, top, lobes, phase in mesas:
        roughness = (noise(19, 3, int(abs(mx) + abs(mz)) % 40 + 30) - 0.5) * 0.22
        normalised = _blob_distance(fx, fz, mx, mz, radius, lobes, phase, roughness)
        crown = top + noise(29, 3, 7) * 1.3
        # A mesa is a flat cap, a near-vertical cliff band, then a talus apron -
        # not a smooth dome. Building the profile explicitly is what gives the
        # silhouette the concept's hard eroded edge.
        cap = _falloff(normalised, inner, inner + 0.06)
        cliff = _falloff(normalised, inner + 0.06, 1.0)
        talus = _falloff(normalised, 1.0, 1.62)
        # Stepped benches so the cliff face reads as bedded strata in profile.
        benches = np.clip(normalised - inner, 0.0, 1.0) / max(1.0 - inner, 1e-6)
        stepping = (np.floor(benches * 4.0) + _smoothstep(0.55, 0.95,
                                                          (benches * 4.0) % 1.0)) / 4.0
        cliff_height = crown - (crown - height) * stepping
        profile = np.where(cap > 0.5, crown,
                           np.where(cliff > 0.02,
                                    height + (cliff_height - height) * cliff,
                                    height))
        blend = np.maximum(cap, cliff)
        height = height * (1.0 - blend) + profile * blend
        # Talus fan of shed material around the foot.
        height += (crown - height) * 0.22 * talus * (1.0 - blend)
        rock_stamp = np.maximum(rock_stamp, _falloff(normalised, 1.05, 1.5))

    # --- isolated formations and standing-stone knolls ------------------
    for kx, kz, radius, rise, lobes, phase in (
            (-44.0, -18.0, 10.0, 4.6, ((3, 0.22), (5, 0.12)), 1.1),
            (26.0, 44.0, 9.0, 3.8, ((2, 0.26), (6, 0.10)), 3.7),
            (-70.0, 12.0, 8.0, 3.2, ((3, 0.20), (7, 0.11)), 5.1),
            (46.0, -52.0, 9.0, 4.1, ((2, 0.24), (5, 0.13)), 2.6)):
        normalised = _blob_distance(fx, fz, kx, kz, radius, lobes, phase, 0.0)
        height += rise * _falloff(normalised, 0.35, 1.0)
        rock_stamp = np.maximum(rock_stamp, _falloff(normalised, 0.55, 0.95) * 0.8)

    # --- desert basin north of the steppe --------------------------------
    # The continent master concept puts dry ochre badland between the steppe
    # and the Amethyst Barrens, so the ground grades from grazing steppe into a
    # dune field and salt pans before the mountains close it off.
    desert_front = (-92.0 + (noise(4, 4, 51) - 0.5) * 46.0
                    + (noise(9, 3, 53) - 0.5) * 20.0
                    + 14.0 * np.sin(gx * 0.026 + 1.2))
    into_desert = _smoothstep(0.0, 46.0, desert_front - fz)
    # Sand runs south down the dry washes and grass climbs north between them,
    # so the two grounds interlock rather than meeting at a line.
    for wash in ([(-24, -104), (-18, -86), (-8, -70), (-2, -56)],
                 [(48, -108), (54, -92), (62, -76), (72, -62)],
                 [(94, -116), (88, -98), (80, -84)]):
        into_desert = np.maximum(into_desert, 0.85 * _falloff(
            _polyline_distance(fx, fz, wash), 5.0, 16.0)
            * _smoothstep(-70.0, -100.0, fz + 30.0))
    dunes = np.zeros_like(height)
    swing = 0.34 * np.sin(gx * 0.012) + 0.18 * np.cos(gz * 0.017)
    for period, amplitude, angle, offset in ((17.0, 3.1, 0.35, 0.0),
                                             (31.0, 4.6, 0.22, 1.7),
                                             (9.0, 1.4, 0.48, 3.1)):
        bearing = angle + swing
        along = gx * np.cos(bearing) + gz * np.sin(bearing)
        # Asymmetric dune profile: a long windward back and a short slip face.
        phase = (along / period + offset + noise(9, 3, 52) * 0.6) % 1.0
        dunes += amplitude * np.where(phase < 0.72, (phase / 0.72) ** 1.6,
                                      1.0 - (phase - 0.72) / 0.28)
    height = height * (1.0 - into_desert) + (
        height * 0.35 + 7.0 + dunes) * into_desert
    # Salt pans: dead-flat bright floors between the dune trains.
    pan_mask = np.zeros_like(height)
    for px, pz, radius, lobes, phase in ((6.0, -124.0, 20.0, ((3, 0.24), (5, 0.13)), 1.1),
                                         (62.0, -110.0, 15.0, ((2, 0.28), (6, 0.11)), 3.4),
                                         (-30.0, -132.0, 13.0, ((3, 0.22), (7, 0.10)), 5.2)):
        pan = _falloff(_blob_distance(fx, fz, px, pz, radius, lobes, phase, 0.0),
                       0.62, 1.0) * into_desert
        floor = float(height[landform_index(z_axis, pz), landform_index(x_axis, px)])
        height = height * (1.0 - pan) + (floor - 1.6) * pan
        pan_mask = np.maximum(pan_mask, pan)

    # --- Amethyst badlands in the north-east ------------------------------
    badland_mask = _smoothstep(0.0, 40.0, (gx - 74.0)) * _smoothstep(0.0, 34.0, (-52.0 - gz))
    for bx, bz, radius, top, lobes, phase in (
            (108.0, -96.0, 21.0, 34.0, ((3, 0.20), (5, 0.11), (8, 0.06)), 0.7),
            (140.0, -130.0, 24.0, 40.0, ((2, 0.24), (6, 0.10)), 2.9),
            (96.0, -142.0, 18.0, 33.0, ((3, 0.22), (7, 0.09)), 4.6),
            (132.0, -64.0, 17.0, 27.0, ((2, 0.26), (5, 0.12)), 1.9),
            (70.0, -122.0, 14.0, 24.0, ((3, 0.25), (6, 0.12)), 5.5)):
        normalised = _blob_distance(fx, fz, bx, bz, radius, lobes, phase,
                                    (noise(23, 3, 61) - 0.5) * 0.20)
        crown = top + noise(27, 3, 62) * 2.2
        cap = _falloff(normalised, 0.30, 0.40)
        cliff = _falloff(normalised, 0.40, 1.0)
        talus = _falloff(normalised, 1.0, 1.7)
        benches = np.clip(normalised - 0.30, 0.0, 1.0) / 0.70
        stepping = (np.floor(benches * 5.0)
                    + _smoothstep(0.60, 0.96, (benches * 5.0) % 1.0)) / 5.0
        cliff_height = crown - (crown - height) * stepping
        blend = np.maximum(cap, cliff)
        profile = np.where(cap > 0.5, crown, height + (cliff_height - height) * cliff)
        height = height * (1.0 - blend) + profile * blend
        height += (crown - height) * 0.20 * talus * (1.0 - blend)
        rock_stamp = np.maximum(rock_stamp, _falloff(normalised, 1.05, 1.55))
    # The slender wind-carved spires the Barrens concept repeats are placed as
    # instanced rock rather than sculpted here: at 1.4 m cells they would be two
    # cells wide, which folds the surface over instead of making a spire. Their
    # bases are raised into low plinths so the instances sit on a knoll.
    for sx, sz, radius in SPIRE_SITES:
        plinth = _falloff(np.hypot(gx - sx, gz - sz), radius, radius * 3.2)
        height += 3.2 * plinth
        rock_stamp = np.maximum(rock_stamp, plinth)

    # --- mountain boundary along the north and east -----------------------
    # A real range rather than a raised lip: the world edge on these two sides
    # is the Whitehorn foothills wrapping toward the Barrens, and it is what
    # stops a player leaving the authored ground.
    north_front = -134.0 + (noise(4, 4, 71) - 0.5) * 34.0
    east_front = 128.0 + (noise(4, 4, 72) - 0.5) * 34.0
    into_mountain = np.maximum(_smoothstep(0.0, 52.0, north_front - fz),
                               _smoothstep(0.0, 52.0, fx - east_front))
    # A foothill belt ahead of the range, so the ground climbs into it.
    foothills = np.maximum(_smoothstep(0.0, 74.0, north_front + 26.0 - fz),
                           _smoothstep(0.0, 74.0, fx - east_front + 26.0))
    height += (8.0 + noise(13, 4, 74) * 9.0) * foothills ** 1.7
    # Named summits give the skyline a silhouette instead of a uniform wall.
    peaks = np.zeros_like(height)
    for px, pz, radius, top in ((-52.0, -168.0, 30.0, 66.0), (4.0, -172.0, 34.0, 74.0),
                                (58.0, -164.0, 28.0, 62.0), (112.0, -170.0, 32.0, 70.0),
                                (160.0, -150.0, 30.0, 68.0), (168.0, -96.0, 28.0, 60.0),
                                (166.0, -40.0, 26.0, 54.0), (162.0, 16.0, 24.0, 48.0),
                                (-30.0, -158.0, 20.0, 52.0), (84.0, -156.0, 22.0, 56.0),
                                (140.0, -60.0, 20.0, 47.0)):
        distance = np.hypot(fx - px, fz - pz)
        cone = _falloff(distance, radius * 0.10, radius)
        peaks = np.maximum(peaks, top * cone ** 1.5)
    ridgeline = 24.0 + noise(9, 4, 73) * 20.0
    mountain = np.maximum(peaks, ridgeline * into_mountain ** 1.4)
    height = np.maximum(height, height * (1.0 - into_mountain)
                        + mountain * into_mountain ** 1.2)
    height = np.maximum(height, peaks * _smoothstep(0.0, 0.15, peaks / 80.0))
    rock_stamp = np.maximum(rock_stamp, _smoothstep(0.30, 0.75, into_mountain))
    mountain_mask = np.maximum(_smoothstep(0.30, 0.80, into_mountain),
                               _smoothstep(20.0, 40.0, peaks))

    # --- coastline: western bays and a south-western sound ---------------
    coast_noise = noise(7, 5, 11)
    shore = (-76.0 - 10.0 * np.sin(gz * 0.048 + 0.6) - 7.0 * np.cos(gz * 0.019 + 1.3)
             + (coast_noise - 0.5) * 26.0)
    for bx, bz, radius, depth in ((-90.0, -58.0, 44.0, 16.0), (-84.0, 58.0, 50.0, 22.0),
                                  (-92.0, 8.0, 26.0, 9.0)):
        shore = shore - depth * _falloff(np.hypot(fx - bx, fz - bz), radius * 0.25, radius)
    into_sea = _smoothstep(0.0, 14.0, shore - fx)

    # Southern shore sweeping round the south-west and a south-eastern inlet.
    south_shore = (78.0 + 9.0 * np.sin(gx * 0.041 + 2.1) + (noise(9, 4, 12) - 0.5) * 18.0
                   - 16.0 * _falloff(np.hypot(fx - 82.0, fz - 96.0), 12.0, 44.0))
    into_sea = np.maximum(into_sea, _smoothstep(0.0, 14.0, fz - south_shore))
    seabed = -5.5 - 6.0 * into_sea
    height = height * (1.0 - into_sea) + seabed * into_sea

    # --- coastal cliffs, headlands and sea stacks ------------------------
    coastal = _falloff(np.abs(shore - fx), 2.0, 14.0) * (1.0 - into_sea)
    headland = _falloff(np.hypot(fx + 84.0, fz - 2.0), 10.0, 32.0)
    height += 10.5 * coastal * (0.40 + 0.60 * headland)
    rock_stamp = np.maximum(rock_stamp, coastal)
    for sx, sz, radius, top in ((-88.0, -34.0, 4.0, 9.0), (-93.0, 24.0, 3.4, 7.5),
                                (-86.0, 70.0, 3.8, 8.5), (66.0, 92.0, 4.2, 8.0)):
        stack = _falloff(np.hypot(gx - sx, gz - sz), radius * 0.5, radius)
        height = np.maximum(height, height * (1.0 - stack) + top * stack)
        rock_stamp = np.maximum(rock_stamp, stack)

    # --- world rim: a ragged ring of highland, not a square wall ---------
    # Only the west and south still need the old ridge: the north and east are
    # closed by the mountain range above.
    rim_distance = np.maximum(-58.0 - gx, gz - 58.0)
    ragged = (noise(7, 3, 41) - 0.5) * 7.0 + (noise(19, 3, 42) - 0.5) * 3.0
    rim = _smoothstep(18.0, 44.0, rim_distance + ragged)
    # A ridge line rather than a plateau, so the barrier reads as landscape.
    ridge = 0.70 + 0.30 * np.sin(np.arctan2(gz - CENTRE[1], gx - CENTRE[0]) * 3.0
                                 + noise(5, 3, 43) * 4.0)
    height += 26.0 * rim * ridge * (1.0 - into_sea)
    height -= 9.0 * rim * into_sea
    rock_stamp = np.maximum(rock_stamp, _smoothstep(0.35, 0.85, rim) * (1.0 - into_sea))

    # --- building pads ---------------------------------------------------
    # Structures are authored flat-bottomed, so the ground under each one is
    # levelled to its centre height with a graded skirt. Without this a wide
    # footprint has to be sunk to its lowest corner and the building buries
    # itself in the slope.
    for pad_x, pad_z, pad_radius in pads:
        column = int(np.clip((pad_x - x_axis[0]) / CELL, 0, count - 1))
        row = int(np.clip((pad_z - z_axis[0]) / CELL, 0, count - 1))
        target = float(height[row, column])
        distance = np.hypot(gx - pad_x, gz - pad_z)
        core = _falloff(distance, pad_radius * 0.92, pad_radius * 1.05)
        skirt = _falloff(distance, pad_radius * 1.05, pad_radius * 2.1)
        blended = np.maximum(core, skirt * 0.72)
        height = height * (1.0 - blended) + target * blended

    # --- stream chain and waterholes ------------------------------------
    # Water is cut from frozen downhill surveys by DESIGN.sculpt.
    pond_mask = np.zeros_like(height)
    ponds = [(x,z,r,((3,0.1),),1.0) for x,z,r,_ in DESIGN.POOLS]
    for px, pz, radius, lobes, phase in ponds:
        normalised = _blob_distance(fx, fz, px, pz, radius, lobes, phase, 0.0)
        bowl = _falloff(normalised, 0.3, 1.0)
        # Pool beds share the surveyed water level, rather than a warped centre.
        pond_mask = np.maximum(pond_mask, bowl)

    # --- roads and trails cut a graded corridor -------------------------
    road_mask = np.zeros_like(height)
    for path in ROADS.values():
        road_mask = np.maximum(road_mask, _falloff(
            _polyline_distance(gx, gz, path), ROAD_WIDTH * 0.5, ROAD_WIDTH * 0.5 + 3.0))
    trail_mask = np.zeros_like(height)
    for path in TRAILS.values():
        trail_mask = np.maximum(trail_mask, _falloff(
            _polyline_distance(gx, gz, path), TRAIL_WIDTH * 0.5, TRAIL_WIDTH * 0.5 + 2.4))
    combined_route = np.maximum(road_mask, trail_mask * 0.75)
    smoothed = height.copy()
    for _ in range(7):
        smoothed = (smoothed * 0.2
                    + _shift(smoothed, 1, 0) * 0.2 + _shift(smoothed, -1, 0) * 0.2
                    + _shift(smoothed, 1, 1) * 0.2 + _shift(smoothed, -1, 1) * 0.2)
    height = height * (1.0 - combined_route * 0.88) + smoothed * (combined_route * 0.88)

    # --- crop and pasture blocks ----------------------------------------
    field_mask = np.zeros_like(height)
    for cx, cz, half_x, half_z in FIELDS:
        block = (_falloff(np.abs(fx - cx), half_x - 3.0, half_x)
                 * _falloff(np.abs(fz - cz), half_z - 3.0, half_z))
        field_mask = np.maximum(field_mask, block)
        height = height * (1.0 - block * 0.65) + smoothed * (block * 0.65)

    height = DESIGN.sculpt(gx,gz,height,np.zeros(height.shape,dtype="int8"),CELL)

    # --- slope limiter -----------------------------------------------------
    # Cap the step between neighbouring cells. Beyond roughly 62 degrees a quad
    # can fold past vertical, which makes its face normal disagree with the
    # smoothed vertex normal: the surface then renders back-to-front and stops
    # catching the grounding ray. Cliffs stay dramatic, they just stop folding.
    # 5.5 cells of rise per cell of run is about 80 degrees: still a cliff face,
    # but comfortably short of folding past vertical.
    limit = CELL * 5.5
    for _ in range(60):
        excess = 0.0
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            neighbour = _shift(height, shift, axis)
            over = np.clip(height - neighbour - limit, 0.0, None)
            excess = max(excess, float(over.max()))
            height -= over * 0.45
        if excess < 0.05:
            break

    water = (height < SEA_LEVEL) | (pond_mask > 0.5)

    # --- terrain classification ------------------------------------------
    # The masks that decide ground type are smoothed first. Sculpting wants the
    # sharp wash interlock where the dunes meet the steppe, but thresholding a
    # cell-scale mask assigns neighbouring quads to different classes and the
    # boundary renders as a chequerboard of two tints instead of a shoreline.
    def _settle(mask: np.ndarray, passes: int = 3) -> np.ndarray:
        settled = mask
        for _ in range(passes):
            settled = (settled * 0.36
                       + _shift(settled, 1, 0) * 0.16 + _shift(settled, -1, 0) * 0.16
                       + _shift(settled, 1, 1) * 0.16 + _shift(settled, -1, 1) * 0.16)
        return settled

    into_desert = _settle(into_desert)
    pan_mask = _settle(pan_mask)
    badland_mask = _settle(badland_mask)
    mountain_mask = _settle(mountain_mask)
    rock_stamp = _settle(rock_stamp, 2)
    classes = np.full(height.shape, CLASS_STEPPE, dtype="int8")
    # Sun-bleached patches within the grassland. Sampled on the warped grid and
    # cut against a wandering threshold: a plain value-noise field cut at a fixed
    # level breaks along its own lattice, which on a hillside reads as a
    # chequerboard of two tints rather than as dry ground.
    dry = _settle(_sample(noise(6, 4, 21), fx, fz, x_axis, z_axis)
                  * 0.72 + noise(13, 3, 22) * 0.28)
    wander = _settle(noise(9, 2, 23), 4)
    classes[dry > 0.56 + (wander - 0.5) * 0.12] = CLASS_DRY_GRASS
    classes[field_mask > 0.4] = CLASS_DRY_GRASS
    slope = _slope(height)
    classes[(rock_stamp > 0.62) | (slope > 1.15)] = CLASS_ROCK
    # The three new grounds, applied in order of how strongly each dominates.
    classes[into_desert > 0.45] = CLASS_DESERT
    classes[pan_mask > 0.45] = CLASS_DESERT
    classes[(badland_mask > 0.45) & (rock_stamp > 0.40)] = CLASS_BADLAND
    classes[(badland_mask > 0.60) & (slope > 0.95)] = CLASS_BADLAND
    classes[mountain_mask > 0.45] = CLASS_MOUNTAIN
    classes[camp_distance < 25.0] = CLASS_CLEARING
    for cx, cz, radius in CAMP_CLEARINGS:
        classes[np.hypot(gx - cx, gz - cz) < radius] = CLASS_CLEARING
    classes[trail_mask > 0.5] = CLASS_ROAD
    classes[road_mask > 0.45] = CLASS_ROAD
    # A road is a ribbon around a polyline and its edge is wherever its falloff
    # crosses the threshold above, so how far a sample sits from that crossing
    # is how firmly it belongs to whichever side of the road it is on. Without
    # this the ribbon could only turn on a cell corner, and a caravan road
    # across open steppe read as a flight of 1.4 m steps.
    strength = np.ones(height.shape)
    for mask, level in ((trail_mask, 0.5), (road_mask, 0.45)):
        edge = np.abs(mask - level) / ROUTE_EDGE_FEATHER
        strength = np.where(mask > 0.0, np.minimum(strength, np.clip(edge, 0.0, 1.0)),
                            strength)
    beach = (height > SEA_LEVEL - 0.5) & (height < BEACH_LEVEL + 1.4) & (into_sea > 0.03)
    classes[beach] = CLASS_SAND
    classes[height < SEA_LEVEL - 0.2] = CLASS_SAND

    despeckle(classes, DESPECKLE_MIN_CELLS)
    return Landform(x_axis, z_axis, height.astype("float32"), classes, water,
                    strength)


def despeckle(classes: np.ndarray, min_cells: int = 12) -> int:
    """Give every class island smaller than `min_cells` to its surroundings.

    The class field is thresholded noise, and thresholded noise leaves crumbs:
    a handful of cells of rock marooned in steppe, a gap of sand in the middle
    of a road. Owned whole-quad those read as a stray square and were easy to
    miss. Cut inside the cell they read as a deliberate blob, so they are
    cleared before the ground is meshed. Only the drawn class moves - height
    does not, and neither does anything the walk grid is built from.

    Returns the number of islands cleared.
    """
    rows, columns = classes.shape
    cleared = 0
    while True:
        labels = np.full(classes.shape, -1, dtype="int32")
        islands: list[list[tuple[int, int]]] = []
        for row in range(rows):
            for column in range(columns):
                if labels[row, column] >= 0:
                    continue
                own = classes[row, column]
                label = len(islands)
                stack = [(row, column)]
                labels[row, column] = label
                cells = []
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if not (0 <= ny < rows and 0 <= nx < columns):
                            continue
                        if labels[ny, nx] >= 0 or classes[ny, nx] != own:
                            continue
                        labels[ny, nx] = label
                        stack.append((ny, nx))
                islands.append(cells)
        moved = False
        for cells in islands:
            if len(cells) >= min_cells:
                continue
            own = int(classes[cells[0]])
            border: dict[int, int] = {}
            for y, x in cells:
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < rows and 0 <= nx < columns):
                        continue
                    neighbour = int(classes[ny, nx])
                    if neighbour != own:
                        border[neighbour] = border.get(neighbour, 0) + 1
            if not border:
                continue
            winner = max(sorted(border), key=lambda key: border[key])
            for y, x in cells:
                classes[y, x] = winner
            cleared += 1
            moved = True
        if not moved:
            return cleared


def landform_index(axis, value: float) -> int:
    """Nearest grid index on a monotonic axis."""
    return int(np.clip(round((value - axis[0]) / CELL), 0, len(axis) - 1))


def _sample(field: np.ndarray, sx: np.ndarray, sz: np.ndarray,
            x_axis: np.ndarray, z_axis: np.ndarray) -> np.ndarray:
    """Read `field` at warped world coordinates, nearest sample."""
    columns = np.clip(np.round((sx - x_axis[0]) / (x_axis[1] - x_axis[0])),
                      0, field.shape[1] - 1).astype(int)
    rows = np.clip(np.round((sz - z_axis[0]) / (z_axis[1] - z_axis[0])),
                   0, field.shape[0] - 1).astype(int)
    return field[rows, columns]


def _shift(field: np.ndarray, offset: int, axis: int) -> np.ndarray:
    """Shift by one cell with the edge replicated rather than wrapped.

    `np.roll` wraps, which on a heightfield means the northern edge is averaged
    and slope-limited against the southern one. On this region that is a 38 m
    difference, and the result is a trench dragged all the way round the map:
    the mountain boundary drowned into sea at the very rows that are supposed to
    close the world.
    """
    shifted = np.roll(field, offset, axis=axis)
    if offset > 0:
        index = (slice(0, offset), slice(None)) if axis == 0 else (slice(None), slice(0, offset))
        edge = (slice(offset, offset + 1), slice(None)) if axis == 0 else (slice(None), slice(offset, offset + 1))
    else:
        index = (slice(offset, None), slice(None)) if axis == 0 else (slice(None), slice(offset, None))
        edge = (slice(offset - 1, offset), slice(None)) if axis == 0 else (slice(None), slice(offset - 1, offset))
    shifted[index] = shifted[edge]
    return shifted


def _slope(height: np.ndarray) -> np.ndarray:
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) / (2.0 * CELL)
    dz = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) / (2.0 * CELL)
    return np.hypot(dx, dz)


def slope_field(landform: Landform) -> np.ndarray:
    return _slope(landform.height)
