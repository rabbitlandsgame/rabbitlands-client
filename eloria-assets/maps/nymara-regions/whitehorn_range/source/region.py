"""Whitehorn Range: composition, extents and terrain sculpting.

The region-specific half of the map. Everything else comes from the shared
toolkit in `../../_toolkit/`.

Composition authority is `eloria-assets/concepts/nymara-regions/
whitehorn_range_region_concept.png`: a high alpine bowl with a strong
south-to-north rise. The approach climbs from a low southern gate through
cairn-lined switchbacks, crosses a gorge on rope bridges, and ends at a glacier
temple standing on a shelf below the head of the ice. An ice cave opens in the
west, a worked mine in the east, and frozen cascades hang off the shoulders of
the central glacier.

Player-scale authority is the ten-panel concept detail board.

As in Amberwood, the whole composition is written in a fixed 192 m design space
and scaled by SCALE, so changing the region's extent is one constant rather
than a rewrite.
"""
from __future__ import annotations

import numpy as np

from amberwood import mesh as M  # noqa: F401  (re-exported for populate)
from amberwood import noise as N
from amberwood import terrain as TER

# ---------------------------------------------------------------- extents
# 576 m x 576 m on a 96x96-tile server map at one metre per tile, matching
# Amberwood. The arrival datum sits at server (174, 174) so it lands on the
# Godot origin, 30% in from the south-west.
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# Anchors, routes and watercourses below are written in a 192 m design space
# and scaled here. The aerial's layout is preserved rather than stretched.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A temple forecourt is sized by the temple standing in it, a mine head by its
# gantry. Scaling those with the map would give a bigger map with the same
# picture on it and enormous empty ground between.
LOCAL = 1.5

PLAY_MIN_X = -SERVER_ORIGIN[0] * METRES_PER_TILE
PLAY_MAX_X = (SERVER_CELLS - 1 - SERVER_ORIGIN[0]) * METRES_PER_TILE
PLAY_MIN_Z = -(SERVER_CELLS - 1 - SERVER_ORIGIN[1]) * METRES_PER_TILE
PLAY_MAX_Z = SERVER_ORIGIN[1] * METRES_PER_TILE

# Whitehorn has no coast: all four sides are closed by mountain wall, so the
# margin carries a rim rather than a shelf.
MARGIN = 30.0
TERRAIN_X0 = PLAY_MIN_X - MARGIN
TERRAIN_Z0 = PLAY_MIN_Z - MARGIN
TERRAIN_SIZE_X = (PLAY_MAX_X - PLAY_MIN_X) + MARGIN * 2.0
TERRAIN_SIZE_Z = (PLAY_MAX_Z - PLAY_MIN_Z) + MARGIN * 2.0

# There is no sea. The datum is the southern valley floor, which the build
# holds at about +6 m so that meltwater channels have somewhere to cut to.
VALLEY_FLOOR = 6.0
TERRAIN_CELL = 2.0

# Snow lies above this height, on ground that is not too steep to hold it.
# Turf survives below this; everything above is snow unless it is too
# steep to hold it. Low, because the concept is a white region.
SNOW_LINE = 30.0
# The glacier surface: authored, not derived from height.
GLACIER_WIDTH = 15.0

# ---------------------------------------------------------------- anchors
# Design space. Playable design coords run x in [-58, 134], z in [-134, 58];
# north is -Z, so the southern approach is at positive Z.
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # the southern approach, low ground
    "arrival": (0.0, 0.0),
    "south_gate": (-4.0, 28.0),
    "gate_shrine": (-11.0, 33.0),
    "lower_cairns": (6.0, 13.0),
    "pine_shelf": (-26.0, 18.0),
    "south_camp": (24.0, 22.0),
    # the gorge and its crossings
    "gorge_west": (-34.0, -20.0),
    "gorge_east": (108.0, -30.0),
    "rope_bridge": (17.0, -25.0),
    "rope_bridge_upper": (62.0, -33.0),
    "bridge_watch": (30.0, -18.0),
    # the glacier and the temple above it
    "glacier_head": (34.0, -112.0),
    "glacier_snout": (16.0, 4.0),
    "temple": (34.0, -103.0),
    "temple_forecourt": (34.0, -91.0),
    "temple_stair": (34.0, -80.0),
    "north_shrine": (9.0, -119.0),
    "frozen_falls": (26.0, -58.0),
    "upper_falls": (44.0, -74.0),
    # west: the ice cave and the cairn ridge
    "ice_cave": (-38.0, -14.0),
    "cairn_ridge": (-29.0, -68.0),
    "west_watch": (-44.0, -44.0),
    # east: the mine and its road
    "mine": (96.0, -46.0),
    "mine_yard": (89.0, -40.0),
    "east_camp": (110.0, -6.0),
    "overlook": (74.0, 9.0),
    "east_shrine": (118.0, -64.0),
    # the three ways out of the range, each through a notch in its rim: the
    # south march down to Mirrorhold, the west pass to the Amberwood beyond
    # the ice cave, the east pass to the Barrens beyond the mine road
    "south_march": (0.0, 51.0),
    "west_pass": (-51.0, -12.0),
    "east_pass": (125.0, -4.0),
}

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()
}

SPAWN_DESIGN = (0.0, 0.0)
SPAWN = (-12.0, 69.0)
SPAWN_TEMPLE = (34.0 * SCALE, -88.0 * SCALE)
SPAWN_MINE = (89.0 * SCALE, -38.0 * SCALE)


def _route(*points) -> np.ndarray:
    """Route points are written in design space and scaled to world metres."""
    return np.array([[float(p[0]) * SCALE, float(p[1]) * SCALE] for p in points])


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


# ---------------------------------------------------------------- routes
# The pilgrim road: south gate -> switchbacks -> gorge crossing -> temple.
# This is the spine of the region and every panel of the detail board sits on
# or beside it.
ROUTES: dict[str, np.ndarray] = {
    "approach_road": _route(_design("south_gate"), (-2.0, 20.0),
                            _design("lower_cairns"), (9.0, 4.0),
                            _design("arrival"), (4.0, -8.0),
                            (12.0, -16.0), _design("rope_bridge")),
    "temple_road": _route(_design("rope_bridge"), (20,-34.33), (22.67,-43.67),
                          (19,-51), (18.33,-59.67), (24,-66), (30,-71),
                          (34,-80), (27.33,-84.67), (38.67,-89.67),
                          (29.33,-94.67), (34,-99.67), _design("temple")),
    "mine_road": _route(_design("arrival"), (26,-4), (42,6), (58.67,10),
                        _design("overlook"), (88,-4), _design("east_camp"),
                        (116.67,-19.67), (118.67,-29.33), (115.33,-36.33),
                        (106,-41), _design("mine_yard"), _design("mine")),
    "cave_road": _route(_design("lower_cairns"), (-10.0, 10.0),
                        (-24.0, 2.0), _design("ice_cave")),
    "ridge_path": _route(_design("ice_cave"), (-36.0, -34.0),
                         _design("west_watch"), _design("cairn_ridge")),
    "upper_bridge_path": _route(_design("bridge_watch"), (44.0, -24.0),
                                _design("rope_bridge_upper"), (72.0, -40.0),
                                _design("mine_yard")),
    "pine_track": _route(_design("south_gate"), (-16.0, 24.0),
                         _design("pine_shelf")),
    # out of the range
    "south_march_road": _route(_design("south_gate"), (-3.0, 36.0), (-1.0, 45.0),
                               _design("south_march"), (0.0, 58.0)),
    "west_pass_road": _route(_design("ice_cave"), (-45.0, -13.0),
                             _design("west_pass"), (-58.0, -12.0)),
    "east_pass_road": _route(_design("east_camp"), (117.0, -5.0),
                             _design("east_pass"), (134.0, -4.0)),
}

# The gorge is a single cut across the map that the two rope bridges span.
GORGE = _route(_design("gorge_west"), (-8.0, -26.0), _design("rope_bridge"),
               (40.0, -28.0), _design("rope_bridge_upper"), (86.0, -32.0),
               _design("gorge_east"))

# The glacier runs from its head, past the temple shelf, down to the snout
# where it feeds the gorge. Frozen, so it is ICE surface, not a water plane.
GLACIER = _route(_design("glacier_head"), (33.0, -92.0), (30.0, -70.0),
                 _design("frozen_falls"), (23.0, -42.0), (19.0, -20.0),
                 _design("glacier_snout"))

# Meltwater beds, dry or frozen for most of the year.
STREAMS: dict[str, np.ndarray] = {
    "west_beck": _route((-30.0, -50.0), (-26.0, -30.0), (-20.0, -24.0)),
    "mine_beck": _route((92.0, -40.0), (96.0, -34.0), (100.0, -30.0)),
}


# ---------------------------------------------------------------- terrain
def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9,
                        octaves=4, seed=seed)


def build_terrain(seed: int = 20260828) -> TER.Terrain:
    """Sculpt the alpine bowl.

    Order matters: the regional rise and noise first, then the ranges that
    close the world, then the interior massing, then the cuts. Cuts last so a
    ridge raised afterwards cannot fill a gorge back in.
    """
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # The regional rise: south (low, inhabited) to north (high, glaciated).
    # Deliberately gentler than the visual impression of the aerial, because
    # every metre of this is a metre a player has to climb.
    t.add_slope((0.10, -1.0), 0.108, origin=(0.0, 0.0))
    t.base_noise(4.0, 0.008, seed=seed, octaves=3, warp=0.65)
    t.base_noise(0.6, 0.032, seed=seed + 17, octaves=2)
    t.height += VALLEY_FLOOR + 26.0

    # The ranges that close the world. North wall is the highest; the east and
    # west walls step down toward the southern approach so the region reads as
    # a bowl opening south, which is how the aerial is composed.
    t.add_ridge(_route((-58.0, -128.0), (-10.0, -134.0), (40.0, -136.0),
                       (92.0, -132.0), (134.0, -126.0)),
                74.0, 30.0, seed=seed + 3, power=1.30)
    t.add_ridge(_route((-56.0, -110.0), (-54.0, -60.0), (-52.0, -10.0),
                       (-50.0, 40.0)),
                58.0, 25.0, seed=seed + 5, power=1.35)
    t.add_ridge(_route((132.0, -110.0), (128.0, -56.0), (126.0, -6.0),
                       (124.0, 44.0)),
                62.0, 26.0, seed=seed + 7, power=1.35)
    t.add_ridge(_route((-40.0, 52.0), (20.0, 56.0), (80.0, 54.0), (128.0, 50.0)),
                34.0, 22.0, seed=seed + 9, power=1.45)

    # Interior massing: the spurs that separate the glacier trough from the
    # side valleys, and the shoulders the frozen cascades fall from.
    t.add_ridge(_route((-6.0, -104.0), (2.0, -76.0), (6.0, -52.0), (8.0, -30.0)),
                30.0, 16.0, seed=seed + 11, power=1.5)
    t.add_ridge(_route((62.0, -108.0), (66.0, -80.0), (70.0, -56.0),
                       (74.0, -34.0)),
                34.0, 17.0, seed=seed + 13, power=1.5)
    t.add_ridge(_route((-34.0, -86.0), (-24.0, -70.0), (-18.0, -52.0)),
                22.0, 13.0, seed=seed + 15, power=1.55)

    # The cirque the glacier is born in, and the shelf the temple stands on.
    t.add_dome(ANCHORS["glacier_head"], 40.0 * SCALE, 34.0, power=1.5,
               noise_seed=seed + 19, noise_amount=0.18)
    t.add_dome(ANCHORS["mine"], 26.0 * SCALE, 16.0, power=1.6)
    t.add_dome(ANCHORS["cairn_ridge"], 30.0 * SCALE, 20.0, power=1.55,
               noise_seed=seed + 21, noise_amount=0.20)
    t.add_dome(ANCHORS["overlook"], 22.0 * SCALE, 11.0, power=1.7)

    # The southern basin: a shallow bowl that keeps the arrival ground low and
    # sheltered, so the first thing a player sees is the climb ahead of them.
    t.add_dome(ANCHORS["arrival"], 44.0 * SCALE, -14.0, power=1.25)
    t.add_dome(ANCHORS["pine_shelf"], 26.0 * SCALE, -6.0, power=1.4)

    # The notches. The rim walls are what make the range a bowl, and a bowl
    # with no way out is a map a player cannot leave. Each of the three roads
    # that leave has its pass cut level through the rim at the height of the
    # ground it comes from - wide enough for the road and its shoulders, so
    # the floor is walkable to the map edge and the wall still reads as a
    # wall either side. (Bowl-shaped dome cuts here left craters whose slopes
    # nothing could climb.)
    for route_name in ("south_march_road", "west_pass_road", "east_pass_road"):
        points = ROUTES[route_name][-3:]
        floor = float(t.height_at(points[0][0], points[0][1]))
        t.grade_path(points, 5.0 * SCALE, heights=[floor, floor - 1.0, floor - 3.0],
                     shoulder=2.4, surface=TER.PATH, flatten=1.0)

    # The glacier trough: a broad U cut down the centre, which the ice fills.
    t.carve_channel(GLACIER, GLACIER_WIDTH * SCALE, 8.0, bank=2.8,
                    seed=seed + 31)

    # The gorge the rope bridges span. Deep and narrow - this is the one place
    # the region is genuinely impassable without a crossing.
    t.carve_channel(GORGE, 5.4 * SCALE, 10.0, bank=2.8, seed=seed + 37,
                    floor_height=[3,5,7,14,24,30,33])

    for name, points in STREAMS.items():
        t.carve_channel(points, 2.6 * SCALE, 3.2, bank=2.4,
                        seed=seed + N.stable_hash(name) % 97)

    t.erode(iterations=16, strength=0.28)
    t.smooth(iterations=2, weight=0.35)

    # Close the world on all four sides. No coast here, so nothing is left open.
    t.clamp_edges(MARGIN + 14.0, 62.0, sides=("north",))
    return t


def apply_built_ground(t: TER.Terrain, seed: int = 20260828) -> None:
    """Graded roads, the temple terraces and the mine yard.

    Everything here flattens ground a player stands on. It runs after the
    natural sculpting and before surface classification, so the roads keep
    their own surface class instead of being reclassified as rock.
    """
    # The pilgrim road and its branches. Graded so the climb is walkable
    # rather than a staircase of noise.
    for name, points in ROUTES.items():
        width = 3.4 if name in ("approach_road", "temple_road") else 2.6
        t.grade_path(points, width * LOCAL, shoulder=8.0, surface=TER.PATH)

    # The temple stands on a cut shelf. Terraces take the natural height at
    # their own centre, so the buildings sit on the mountain rather than
    # floating at an absolute Y that the next terrain change invalidates.
    for name, half_x, half_z, surface in (
            ("temple", 16.0, 11.0, TER.MARBLE),):
        centre = ANCHORS[name]
        t.rect_terrace(centre, half_x * LOCAL, half_z * LOCAL,
                       float(t.height_at(*centre)), 0.0, surface)

    # The mine needs a bench cut in front of its portal, not just a yard
    # 21 m away: the adit sits on the flank of a dome, and a portal built up
    # from y = 0 and dropped on that ground is swallowed by the hillside. The
    # bench is centred between the portal and the yard and takes the yard's
    # height, so the ground in front of the adit is flat while the hill it is
    # cut into still rises behind it.
    mine_x, mine_z = ANCHORS["mine"]
    yard_x, yard_z = ANCHORS["mine_yard"]
    bench = ((mine_x + yard_x) * 0.5, (mine_z + yard_z) * 0.5)
    t.plateau(bench, 22.0 * LOCAL, float(t.height_at(yard_x, yard_z)),
              edge=7.0 * LOCAL, surface=TER.PATH, seed=seed + 57)

    # Shrines, the mine yard and the camps: circular cut ground.
    for name, radius, surface in (
            ("gate_shrine", 15.0, TER.PAVING),
            ("north_shrine", 12.0, TER.PAVING),
            ("east_shrine", 11.0, TER.PAVING),
            ("mine_yard", 18.0, TER.PATH),
            ("south_camp", 13.0, TER.PATH),
            ("east_camp", 13.0, TER.PATH),
            ("bridge_watch", 10.0, TER.PATH),
            ("west_watch", 9.0, TER.PATH),
            ("overlook", 11.0, TER.PATH)):
        centre = ANCHORS[name]
        t.plateau(centre, radius * LOCAL, float(t.height_at(*centre)),
                  edge=4.5 * LOCAL, surface=surface,
                  seed=seed + N.stable_hash(name) % 89)

    # Re-cut the gorge. `grade_path` levels its corridor to a smoothed profile
    # along the route, which happily bridges a 22 m chasm and fills it in - the
    # approach road and the upper path both cross the gorge, so grading them
    # erased the one feature the rope bridges exist to span. The cut has to win
    # over the roads, so it is repeated after them rather than before.
    t.carve_channel(GORGE, 5.4 * SCALE, 10.0, bank=2.8, seed=seed + 37,
                    floor_height=[3,5,7,14,24,30,33])

    # Keep vegetation and scatter out of the built places.
    for name, radius in (("temple", 30.0), ("temple_forecourt", 26.0),
                         ("gate_shrine", 17.0), ("north_shrine", 14.0),
                         ("east_shrine", 13.0), ("mine_yard", 20.0),
                         ("mine", 16.0), ("south_camp", 15.0),
                         ("east_camp", 15.0), ("bridge_watch", 12.0),
                         ("west_watch", 11.0), ("overlook", 13.0),
                         ("ice_cave", 14.0), ("rope_bridge", 12.0),
                         ("rope_bridge_upper", 12.0), ("cairn_ridge", 16.0),
                         ("lower_cairns", 12.0), ("south_gate", 14.0)):
        t.mark_blocked_disc(ANCHORS[name], radius * LOCAL)


def assign_surfaces(t: TER.Terrain, seed: int = 20260828) -> None:
    """Whitehorn's surface classes.

    `terrain.assign_surface_by_rule` is written for a coastal region: it
    assigns SHORE around a sea level Whitehorn does not have. This is the
    alpine equivalent - snow by altitude and shelter, ice on the glacier,
    rock where snow cannot lie, turf only on the low southern ground.
    """
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)

    authored = np.isin(t.surface, [TER.PATH, TER.PAVING, TER.MARBLE])

    # Snow is the default, not the exception. The concept is a white region:
    # everything holds snow except ground too steep for it to lie on. The
    # first pass of this build made rock the default and snow a high-altitude
    # band, which rendered as a brown bowl with a white rim - the opposite of
    # the painting.
    t.surface = np.where(authored, t.surface, TER.SNOW)

    # Wind-scoured rock breaks through wherever the ground is steep. This is
    # what draws the ridges, the gorge walls and the crags, so it is a slope
    # rule with a noisy threshold rather than a height rule.
    scour = N.fbm(t.gx * 0.030, t.gz * 0.030, seed=seed + 63)
    # High ground holds snow on steeper faces than low ground does, so the
    # peaks and the boundary ridges stay white and only their steepest faces
    # break through as rock. Without this the whole boundary ramp - which is
    # sloped along its entire width - classifies as rock and reads as a brown
    # apron around the map.
    altitude = np.clip((t.height - SNOW_LINE) / 90.0, 0.0, 1.0)
    scour_limit = (0.72 + 0.95 * altitude) + (scour - 0.5) * 0.40
    t.surface = np.where((slope > scour_limit) & ~authored, TER.ROCK,
                         t.surface)

    # Bare turf survives only on the lowest, most sheltered southern ground,
    # below the snow line and out of the wind. It is a small part of the
    # region and should read as an exception to the snow.
    turf_noise = N.fbm(t.gx * 0.016, t.gz * 0.016, seed=seed + 61)
    turf = (t.height < SNOW_LINE) & (slope < 0.52) & ~authored \
        & (turf_noise > 0.62)
    t.surface = np.where(turf, TER.TURF, t.surface)

    # The glacier: authored from the route, not derived from height, so it
    # stays continuous where it drops below the snow line at the snout.
    from amberwood.terrain import _polyline_distance
    distance, _ = _polyline_distance(t.gx, t.gz, GLACIER)
    ice_noise = N.fbm(t.gx * 0.05, t.gz * 0.05, seed=seed + 67)
    ice_width = GLACIER_WIDTH * SCALE * (0.80 + 0.30 * ice_noise)
    t.surface = np.where((distance < ice_width) & ~authored, TER.ICE, t.surface)

    # a light dither only: at a 2 m terrain cell a heavy one reads as
    # stair-stepped rectangles from the air rather than an organic edge
    t.dither_boundaries(seed=seed + 71, amount=0.18)


# Whitehorn's surface-class material overrides. PATH defaults to `leaf_path`,
# which is an autumn-forest recipe and wrong on a snow region; the shared
# `build_meshes(materials=...)` override exists for exactly this.
SURFACE_MATERIALS: dict[int, str] = {
    TER.PATH: "packed_earth",
    TER.PAVING: "pale_ashlar",
    TER.ROCK: "cliff_rock",
    TER.SNOW: "snow_pack",
    TER.ICE: "glacier_ice",
    TER.MARBLE: "veined_marble",
    TER.TURF: "alpine_turf",
}
