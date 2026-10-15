"""The authored Mirrorhold region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side and walled, so a player can never walk off
the authored world.

Composition follows the aerial concept, which is a mountain read north to
south:

  * glacier and bare peaks close the north;
  * the observatory citadel sits on the summit massif, crowned by the great
    mirror-sphere in its armillary mount, its terraces holding still reflecting
    basins - the pools are what the region is named for, not the lake;
  * a civic descent of terraces, switchback roads, canals and waterfalls steps
    down the south face, with the stepped cliff town on the west shoulder and
    an aqueduct on the east;
  * the mirror lake fills the southern basin, with the ring - a colonnaded
    island - at its centre on radial causeways, and a harbour on its north
    shore.

Everything is written in a 192 m design space and scaled by SCALE, so the
concept's composition is preserved rather than stretched.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER

# ---------------------------------------------------------------- extents
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# The composition is authored in the original 192 m design space and scaled
# here, so the aerial's layout survives the enlargement.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A courtyard is sized by the buildings standing in it, so terraces, plazas and
# the ring keep a local scale - otherwise a bigger map is the same map inflated.
LOCAL = 1.5

PLAY_MIN_X = -SERVER_ORIGIN[0] * METRES_PER_TILE
PLAY_MAX_X = (SERVER_CELLS - 1 - SERVER_ORIGIN[0]) * METRES_PER_TILE
PLAY_MIN_Z = -(SERVER_CELLS - 1 - SERVER_ORIGIN[1]) * METRES_PER_TILE
PLAY_MAX_Z = SERVER_ORIGIN[1] * METRES_PER_TILE

MARGIN = 30.0
TERRAIN_X0 = PLAY_MIN_X - MARGIN
TERRAIN_Z0 = PLAY_MIN_Z - MARGIN
TERRAIN_SIZE_X = (PLAY_MAX_X - PLAY_MIN_X) + MARGIN * 2.0
TERRAIN_SIZE_Z = (PLAY_MAX_Z - PLAY_MIN_Z) + MARGIN * 2.0

# The lake surface is the datum everything else is measured from. Unlike
# Amberwood there is no sea: the world's low point is inland water.
LAKE_LEVEL = 0.0
LAKE_FLOOR = -11.0
TERRAIN_CELL = 2.0

# ------------------------------------------------------------ elevations
# One table, so the terraces and the buildings that stand on them cannot drift
# apart. Metres above the lake.
LEVEL = {
    "lake": LAKE_LEVEL,
    "quay": 4.5,
    "shore_terrace": 8.0,
    "lower_town": 17.0,
    "mid_town": 31.0,
    "canal_district": 46.0,
    "fountain_plaza": 58.0,
    "upper_terrace": 70.0,
    "citadel_gate": 84.0,
    "citadel_court": 98.0,
    "citadel_high": 112.0,
    "orrery": 124.0,
}

PEAK_NORTH = 196.0
PEAK_FLANK = 168.0
# Snow lies only on the high ground; the civic terraces are below it, or the
# whole city reads as a ski slope instead of a stone city in the mountains.
SNOW_LINE = 150.0
GLACIER_MIN = 128.0

# ------------------------------------------------------------------ plan
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # summit
    "orrery": (54.0, -89.0),
    "citadel": (54.0, -68.0),
    "citadel_gate": (52.0, -52.0),
    "rose_gallery": (40.0, -53.0),
    "lens_tower_west": (34.0, -76.0),
    "lens_tower_east": (74.0, -76.0),
    # the ice
    "glacier_west": (-14.0, -104.0),
    "glacier_east": (100.0, -100.0),
    "peak_north": (55.0, -120.0),
    "peak_west": (-22.0, -78.0),
    "peak_east": (112.0, -76.0),
    # civic descent
    "terrace_overlook": (72.0, -42.0),
    "fountain_plaza": (44.0, -30.0),
    "canal_district": (28.0, -36.0),
    "cliff_town": (-8.0, -18.0),
    "aqueduct": (98.0, -30.0),
    "upper_falls": (18.0, -50.0),
    "east_stair": (80.0, -20.0),
    # the water
    "lake": (52.0, 22.0),
    "ring": (52.0, 20.0),
    "harbour": (66.0, -6.0),
    "west_gorge": (-28.0, 4.0),
    "south_watch": (36.0, 52.0),
    "east_islet": (96.0, 34.0),
    "west_islet": (14.0, 40.0),
    # arrival
    "spawn": (0.0, 0.0),
    "spawn_road": (-6.0, -8.0),
}

ANCHORS = {name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()}


def _design(name: str) -> tuple[float, float]:
    return ANCHORS[name]


def _route(*points) -> np.ndarray:
    """A polyline in design space, returned in world metres."""
    out = []
    for p in points:
        if isinstance(p, str):
            out.append(ANCHORS[p])
        else:
            out.append((p[0] * SCALE, p[1] * SCALE))
    return np.asarray(out, dtype=np.float64)


# The great south road: lake shore up to the citadel gate, switchbacking.
GREAT_ROAD = _route("spawn", (6.0, -6.0), (18.0, -12.0), (24.0, -22.0),
                    (34.0, -26.0), "fountain_plaza", (50.0, -38.0),
                    (46.0, -46.0), "citadel_gate")
# The shore road, west quay round to the harbour.
SHORE_ROAD = _route((-16.0, 16.0), "spawn", (14.0, 2.0), (34.0, -4.0), "harbour")
# The cliff-town stair road on the west shoulder.
TOWN_ROAD = _route("cliff_town", (0.0, -14.0), (10.0, -18.0), (20.0, -24.0))
# The east ascent past the aqueduct.
EAST_ROAD = _route("harbour", (76.0, -8.0), "east_stair", (90.0, -26.0),
                   "aqueduct", (92.0, -38.0), "terrace_overlook")

ROUTES = {
    "great_road": GREAT_ROAD,
    "shore_road": SHORE_ROAD,
    "town_road": TOWN_ROAD,
    "east_road": EAST_ROAD,
}

# Meltwater: the canals and falls that feed the lake.
WATERCOURSES = {
    "upper_cascade": _route("upper_falls", (22.0, -40.0), (26.0, -32.0),
                            (30.0, -20.0)),
    "canal_west": _route((30.0, -20.0), (26.0, -6.0), (22.0, 6.0), (30.0, 16.0)),
    "canal_east": _route("aqueduct", (94.0, -18.0), (84.0, -4.0), (72.0, 10.0)),
}


def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9,
                        octaves=4, seed=seed)


def lake_mask(t: TER.Terrain) -> np.ndarray:
    """The lake's plan shape.

    A broad main basin filling the southern third with a north-west arm
    reaching toward the gorge, softly irregular so the shore is not a circle.
    """
    cx, cz = ANCHORS["lake"]
    wobble = (N.fbm(t.gx * 0.005, t.gz * 0.005, seed=7717) - 0.5) * 2.0
    main = np.hypot((t.gx - cx) * 0.92, (t.gz - cz) * 1.16) / (45.0 * SCALE)
    arm_x, arm_z = 16.0 * SCALE, 34.0 * SCALE
    arm = np.hypot((t.gx - arm_x) * 1.25, (t.gz - arm_z) * 0.95) / (22.0 * SCALE)
    field = np.minimum(main, arm) + wobble * 0.13
    return np.clip(1.0 - field, 0.0, 1.0)


def build_terrain(seed: int = 20260828) -> TER.Terrain:
    """Sculpt the mountain, its terraces and the lake basin.

    Order matters: the massif is raised first, the lake is cut into it, the
    built terraces are stamped last so nothing erodes their edges.
    """
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    cell=TERRAIN_CELL)

    # -- 1. the massif -----------------------------------------------------
    # A broad rise toward the north, so the whole region reads as one mountain
    # rather than a set of unrelated hills.
    t.add_slope((0.0, -1.0), 0.150, origin=(0.0, PLAY_MAX_Z))
    t.base_noise(9.0, 0.0040, seed=seed, octaves=5, warp=0.8)
    t.base_noise(3.4, 0.015, seed=seed + 11, octaves=4)

    # the summit massif the citadel is cut into
    t.add_dome(_design("citadel"), 60.0 * SCALE, 78.0, power=1.70,
               noise_seed=seed + 21, noise_amount=0.16)
    t.add_dome(_design("peak_north"), 42.0 * SCALE, 104.0, power=2.1,
               noise_seed=seed + 23, noise_amount=0.20)

    # flanking ridges and peaks, which also close the north corners
    t.add_ridge(_route("peak_west", (10.0, -96.0), "peak_north",
                       (92.0, -104.0), "peak_east"),
                86.0, 26.0 * SCALE, seed=seed + 31, power=1.5)
    t.add_ridge(_route((-30.0, -34.0), "peak_west", (-26.0, -112.0)),
                66.0, 15.0 * SCALE, seed=seed + 37, power=1.4)
    t.add_ridge(_route((120.0, -24.0), "peak_east", (114.0, -110.0)),
                66.0, 15.0 * SCALE, seed=seed + 41, power=1.4)

    # Spurs running south off the massif. These are what stop the lower half
    # reading as a lawn: they separate the districts and give the roads
    # something to switchback around.
    for name, points, height, width in (
            ("west_spur", _route((-30.0, -60.0), (-22.0, -26.0), (-18.0, 4.0)),
             46.0, 13.0 * SCALE),
            ("town_spur", _route((-2.0, -46.0), (-6.0, -14.0), (-4.0, 12.0)),
             34.0, 10.0 * SCALE),
            ("mid_spur", _route((30.0, -44.0), (26.0, -14.0), (24.0, 8.0)),
             30.0, 9.0 * SCALE),
            ("east_spur", _route((92.0, -52.0), (98.0, -20.0), (104.0, 10.0)),
             42.0, 12.0 * SCALE),
            ("far_east_spur", _route((122.0, -40.0), (126.0, 0.0), (124.0, 34.0)),
             40.0, 12.0 * SCALE)):
        t.add_ridge(points, height, width, seed=seed + N.stable_hash(name) % 83,
                    power=1.45)

    # -- 2. the lake basin -------------------------------------------------
    basin = lake_mask(t)
    # A bowl first: the ground falls toward the water for a good distance
    # beyond the shore, so the lake sits in the landscape instead of being a
    # hole punched in a plain.
    bowl = np.clip(basin * 2.4, 0.0, 1.0)
    t.height -= bowl ** 1.4 * 30.0
    # then the water-filled part is cut to the floor
    t.height = t.height - basin ** 0.80 * (t.height - LAKE_FLOOR + 3.0)

    # islets, so the lake is not an empty disc
    for name, radius, height in (("east_islet", 5.0, 16.0),
                                 ("west_islet", 4.0, 13.0)):
        t.add_dome(_design(name), radius * SCALE * LOCAL, height, power=1.6,
                   noise_seed=seed + 53, noise_amount=0.28)

    t.smooth(iterations=2, weight=0.45)
    t.erode(iterations=14, strength=0.28)

    # -- 3. the built terraces --------------------------------------------
    # Stamped after erosion: these are cut stone and must not be worn away.
    _stamp_citadel(t)
    _stamp_civic_descent(t)
    _stamp_lakeside(t)

    # -- 4. roads ----------------------------------------------------------
    for name, points in ROUTES.items():
        width = 7.0 * LOCAL if name == "great_road" else 5.0 * LOCAL
        # Mirrorhold's roads are laid stone, not the forest trail the toolkit
        # defaults to, so they take the paving surface class.
        t.grade_path(points, width, shoulder=3.4, surface=TER.PAVING,
                     seed=seed + N.stable_hash(name) % 97)

    # -- 5. meltwater ------------------------------------------------------
    for name, points in WATERCOURSES.items():
        t.carve_channel(points, 4.4 * LOCAL, 2.1, bank=2.4,
                        seed=seed + N.stable_hash(name) % 89)

    # -- 6. close the world ------------------------------------------------
    _close_world(t, seed)
    t.height = np.maximum(t.height, LAKE_FLOOR)

    t.smooth(iterations=1, weight=0.30)
    assign_surfaces(t, seed)
    return t


def _close_world(t: TER.Terrain, seed: int) -> None:
    """Wall the region with mountains rather than a rectangular lip.

    `Terrain.clamp_edges` raises a uniform rim, which on a map walled on all
    four sides reads as a box with square corners. Mirrorhold has no coast to
    leave open, so the boundary is the most-looked-at thing in the region from
    any high terrace: it gets ridged relief and an irregular foot instead.
    """
    inset = np.minimum(np.minimum(t.gx - PLAY_MIN_X, PLAY_MAX_X - t.gx),
                       np.minimum(t.gz - PLAY_MIN_Z, PLAY_MAX_Z - t.gz))
    # wander the foot of the wall so it is not a straight line on the ground
    wander = (N.fbm(t.gx * 0.010, t.gz * 0.010, seed=seed + 601) - 0.5) * 34.0
    rim = np.clip((16.0 + wander - inset) / 52.0, 0.0, 1.0) ** 1.7

    ridge = N.ridged(t.gx * 0.0135, t.gz * 0.0135, octaves=5, seed=seed + 611)
    rough = N.fbm(t.gx * 0.045, t.gz * 0.045, octaves=4, seed=seed + 617)
    wall = 44.0 + ridge * 82.0 + rough * 16.0
    # The range closes the northern/eastern cirques. The western gorge and
    # southern lake country continue beyond the served square naturally.
    mountain_side = np.maximum(np.clip((t.gx - (PLAY_MAX_X - 40))/65,0,1),
                               np.clip(((PLAY_MIN_Z + 35) - t.gz)/70,0,1))
    t.height += rim * wall * mountain_side


def _stamp_citadel(t: TER.Terrain) -> None:
    """The summit: three stacked courts and the orrery platform above them."""
    t.rect_terrace(_design("citadel_gate"), 26.0 * LOCAL, 15.0 * LOCAL,
                   LEVEL["citadel_gate"], surface=TER.MARBLE)
    t.rect_terrace(_design("citadel"), 34.0 * LOCAL, 24.0 * LOCAL,
                   LEVEL["citadel_court"], surface=TER.MARBLE)
    t.rect_terrace((ANCHORS["citadel"][0], ANCHORS["citadel"][1] - 16.0 * LOCAL),
                   24.0 * LOCAL, 13.0 * LOCAL,
                   LEVEL["citadel_high"], surface=TER.MARBLE)
    t.terrace(_design("orrery"), 15.0 * LOCAL, LEVEL["orrery"], surface=TER.MARBLE)
    # the lens towers stand on their own small platforms
    for name in ("lens_tower_west", "lens_tower_east"):
        t.terrace(_design(name), 7.0 * LOCAL, LEVEL["citadel_court"] + 6.0,
                  surface=TER.MARBLE)
    t.rect_terrace(_design("rose_gallery"), 16.0 * LOCAL, 9.0 * LOCAL,
                   LEVEL["citadel_court"], surface=TER.MARBLE)


def _stamp_civic_descent(t: TER.Terrain) -> None:
    """The south face: plaza, canal district, overlook and the cliff town."""
    t.rect_terrace(_design("upper_falls"), 13.0 * LOCAL, 10.0 * LOCAL,
                   LEVEL["upper_terrace"], surface=TER.PAVING)
    t.terrace(_design("fountain_plaza"), 19.0 * LOCAL, LEVEL["fountain_plaza"],
              surface=TER.MARBLE)
    t.rect_terrace(_design("terrace_overlook"), 17.0 * LOCAL, 12.0 * LOCAL,
                   LEVEL["upper_terrace"] - 6.0, surface=TER.MARBLE)
    t.rect_terrace(_design("canal_district"), 20.0 * LOCAL, 16.0 * LOCAL,
                   LEVEL["canal_district"], surface=TER.PAVING)
    t.rect_terrace(_design("aqueduct"), 12.0 * LOCAL, 18.0 * LOCAL,
                   LEVEL["canal_district"] - 4.0, surface=TER.PAVING)
    # the cliff town is a stack of narrow shelves, not one platform
    tx, tz = ANCHORS["cliff_town"]
    for index in range(5):
        height = LEVEL["lower_town"] + index * 6.5
        t.rect_terrace((tx + index * 4.0 * LOCAL, tz - index * 7.0 * LOCAL),
                       13.0 * LOCAL, 5.5 * LOCAL, height, surface=TER.PAVING)
    t.rect_terrace(_design("east_stair"), 9.0 * LOCAL, 14.0 * LOCAL,
                   LEVEL["mid_town"], surface=TER.PAVING)


def _stamp_lakeside(t: TER.Terrain) -> None:
    """Quay, shore terraces and the ring's foundation."""
    t.rect_terrace(_design("harbour"), 22.0 * LOCAL, 11.0 * LOCAL,
                   LEVEL["quay"], surface=TER.PAVING)
    t.rect_terrace(_design("spawn_road"), 15.0 * LOCAL, 11.0 * LOCAL,
                   LEVEL["shore_terrace"], surface=TER.PAVING)
    t.rect_terrace(_design("south_watch"), 10.0 * LOCAL, 8.0 * LOCAL,
                   LEVEL["shore_terrace"] + 3.0, surface=TER.PAVING)
    # the ring island: a raised disc the colonnade stands on
    t.terrace(_design("ring"), 15.0 * LOCAL, LEVEL["quay"] - 1.0,
              surface=TER.MARBLE)


def assign_surfaces(t: TER.Terrain, seed: int) -> None:
    """Ice, snow, rock, turf and shore by height, slope and position.

    Built surfaces are already stamped by the terrace passes and are preserved.
    """
    built = np.isin(t.surface, (TER.PAVING, TER.MARBLE, TER.PATH))
    height = t.height

    surface = np.full(height.shape, TER.TURF, dtype=np.int32)

    # Steep ground is bare rock whatever its height. This is most of the
    # region: it is a mountain, and turf only holds on the gentler benches.
    gy, gx = np.gradient(height, TERRAIN_CELL)
    steep = np.hypot(gx, gy)
    surface = np.where(steep > 0.42, TER.ROCK, surface)

    # Snow above the line, with only a narrow noisy band of transition so the
    # edge reads as an altitude, not as patches.
    grain = region_noise(t, seed + 61, frequency=0.008)
    line = SNOW_LINE + (grain - 0.5) * 14.0
    surface = np.where(height > line, TER.SNOW, surface)

    # The glaciers: high ground in the two northern cirques only.
    for name, radius in (("glacier_west", 26.0), ("glacier_east", 22.0)):
        cx, cz = ANCHORS[name]
        d = np.hypot(t.gx - cx, t.gz - cz) / (radius * SCALE)
        d = d + (N.fbm(t.gx * 0.004, t.gz * 0.004, seed=seed + 71) - 0.5) * 0.45
        surface = np.where((d < 1.0) & (height > GLACIER_MIN), TER.ICE, surface)

    # Lake margin.
    surface = np.where(height < LAKE_LEVEL + 1.8, TER.SHORE, surface)

    # Everything outside the reachable footprint is the wall that closes the
    # world. It is never walked on, but it is looked at from every high place,
    # so it reads as mountain: bare rock, snow-capped, never turf.
    outside = ((t.gx < PLAY_MIN_X) | (t.gx > PLAY_MAX_X)
               | (t.gz < PLAY_MIN_Z) | (t.gz > PLAY_MAX_Z))
    surface = np.where(outside & (height > SNOW_LINE - 24.0), TER.SNOW,
                       np.where(outside, TER.ROCK, surface))

    t.surface = np.where(built, t.surface, surface)
    t.water_depth = np.clip(LAKE_LEVEL - t.height, 0.0, None)
    t.wet = np.clip(1.0 - (t.height - LAKE_LEVEL) / 3.0, 0.0, 1.0)
    t.tree_block |= t.surface != TER.TURF


# Mirrorhold's ground is stone, ice and thin alpine turf; the toolkit's default
# surface materials are Amberwood's forest ones.
SURFACE_MATERIALS = {
    TER.FOREST: "alpine_turf",
    TER.PATH: "shore_shingle",
    TER.PAVING: "pale_ashlar",
    TER.SHORE: "shore_shingle",
    TER.ROCK: "cliff_rock",
    TER.MEADOW: "alpine_turf",
    TER.SNOW: "snow_pack",
    TER.ICE: "glacier_ice",
    TER.MARBLE: "veined_marble",
    TER.TURF: "alpine_turf",
}


# ------------------------------------------------------ build-script API
# Names the build script and the toolkit expect from a region module.
from regionbuild import Placement, RegionBuild  # noqa: E402,F401

# There is no sea here; the lake surface is the region's water datum, but the
# exporters ask for SEA_LEVEL, so it is the same number under the other name.
SEA_LEVEL = LAKE_LEVEL
STREAMS = WATERCOURSES

SPAWN = ANCHORS["spawn"]
SPAWN_HARBOUR = ANCHORS["harbour"]
SPAWN_CITADEL = ANCHORS["citadel_gate"]


def apply_built_ground(t: TER.Terrain, seed: int = 20260828) -> None:
    """Dress the stamped terraces: paving wear, damp round the basins.

    Kept separate from build_terrain so the heightfield can be rebuilt and
    checked for grounding without the cosmetic pass.
    """
    paved = np.isin(t.surface, (TER.PAVING, TER.MARBLE))
    wear = region_noise(t, seed + 131, frequency=0.030)
    # trodden routes wear through the dressed stone to a plainer paving
    t.surface = np.where(paved & (wear > 0.72) & (t.surface == TER.MARBLE),
                         TER.PAVING, t.surface)
    t.dither_boundaries(seed=seed + 149, amount=0.45)
    # nothing grows on built ground or on ice
    t.tree_block |= np.isin(t.surface, (TER.PAVING, TER.MARBLE, TER.ICE,
                                        TER.SHORE, TER.ROCK))


# The Sanctuary Road approaches across the lake. The side arms are fishing
# piers; the north and south arms join real shore aprons.
LAKE_LINKS = {
    "Sanctuary": [(156, 3.70, 80.8), (156, 4.6, 118),
                   (145, 5.2, 138), (120, 6.06, 158)],
    "City": [(156, 3.70, 39.2), (156, 3.70, 4), (156, 3.70, -16)],
    "WestPier": [(135.2, 3.70, 60), (94.5, 3.70, 60)],
    "EastPier": [(176.8, 3.70, 60), (217.5, 3.70, 60)],
}
# Thresholds sit outside the visible entrance buildings, below the orrery
# platform, beside the plaza and at the foot of Stair Town respectively.
VAULT_ENTRIES = {
    "lens-vault-stair": (137, 112, -256),
    "cistern-door": (151, 58, -84),
    "stair-cellars-door": (-49, 17, -51),
}
CONTENT_LAYOUT = {
    "services": [
        {"role": "information", "position": [122, 58, -77]},
        {"role": "storage", "position": [128, 58, -76]},
        {"role": "crafting_station", "position": [134, 58, -76]},
        {"role": "training", "position": [140, 58, -75]},
    ],
    "roadClearance": 5.0,
}


def prepare_access(t):
    """Surveyed roads meet the lake decks and the three cellar thresholds."""
    from amberwood import routecraft as RC
    t.plateau((120, 158), 10, 6.0, edge=7, surface=TER.PAVING)
    t.plateau((111, 163), 7, 6.0, edge=4, surface=TER.PAVING)
    t.rect_terrace((111, 163), 4, 4, 6.0, surface=TER.PAVING)
    t.plateau((156, -16), 8, 3.52, edge=8, surface=TER.PAVING)
    RC.grade_road(t, [(120, 168), (120, 158)], [5.57, 6.0],
                  width=7, shoulder=8, surface=TER.PAVING)
    RC.grade_road(t, [(156, -16), (168, -20), (182, -18)],
                  [3.52, 4.5, 4.5], width=7, shoulder=7, surface=TER.PAVING)
    # The quay's masonry cap sits above the shore, never on its plane.
    t.rect_terrace((198, -18), 23.5, 5.5, 4.26, surface=TER.PAVING)
    RC.grade_road(t, [(120, 163), (114, 163)], [6.0, 6.0],
                  width=4, shoulder=3, surface=TER.PAVING)
    # A broad court at the foot of Stair Town replaces the pinched cut.
    t.plateau((-40, -40), 25, 17, edge=10, surface=TER.PAVING)
    for x, y, z in VAULT_ENTRIES.values():
        t.plateau((x, z + 1), 5, y, edge=4, surface=TER.PAVING)
        t.rect_terrace((x, z + 1), 4, 5, y, surface=TER.PAVING)
    RC.grade_road(t, [(137, -252), (140, -247), (145, -247)],
                  [112, 112, 112], width=5, shoulder=3, surface=TER.PAVING)
    # Services share the clear south side of the fountain court.
    RC.grade_road(t, [(119, -76), (142, -76)], [58, 58],
                  width=7, shoulder=3, surface=TER.MARBLE)
    # The road descends from the actual arrival elevation, then turns
    # below the houses. Apply it after the aprons so none can raise a hump.
    arrival = float(t.height_at(0, 0))
    RC.grade_road(t, [(0, 0), (-14, -6), (-32, -18), (-48, -32), (-49, -47)],
                  [arrival, 34, 24, 17, 17], width=7, shoulder=12, surface=TER.PAVING)
    t.tree_block |= np.isin(t.surface, (TER.PAVING, TER.MARBLE))
    t.water_depth = np.clip(LAKE_LEVEL - t.height, 0.0, None)


def access_waypoints(t):
    """Publish built approaches so server wildlife stays clear of them."""
    roads = [{"id": "lake-" + name.lower(), "waypoints": stations}
             for name, stations in LAKE_LINKS.items()]
    for name, points in {
        "cellar-lane": [(0, 0), (-14, -6), (-32, -18), (-48, -32), (-49, -47)],
        "quay-approach": [(156, -16), (168, -20), (182, -18)],
        "sanctuary-approach": [(120, 168), (120, 158)],
    }.items():
        roads.append({"id": name, "waypoints": [
            [x, round(float(t.height_at(x, z)), 2), z] for x, z in points]})
    return roads
