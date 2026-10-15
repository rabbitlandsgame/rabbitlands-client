"""The authored Verdant Stair region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side, and the surplus is drowned to the south-west
or raised into cliff walls, so a player can never walk off the authored world.

Composition follows the aerial concept, which is a diagonal: a turquoise lagoon
in the low south-west corner, and from it a flight of great terraces climbing
north-east, each one a level shelf of cut limestone edged by a cliff riser with
waterfalls pouring off it into the pools of the terrace below, up to the temple
on the highest shelf. That diagonal is the region - the name is literal - so
the terrain is authored as a function of position along it rather than as noise
with places dropped on top.

## The two coordinates that matter

Everything is placed in **stair coordinates**, not in x/z:

    s = (x - z) / 2   how far up the stair, south-west to north-east
    c = (x + z) / 2   how far along a terrace, north-west to south-east

both in the 192 m design space, which `SCALE` maps onto the real extent. `s`
alone decides which terrace a place stands on, so a place can never end up
accidentally halfway down a cliff, and spreading places along one terrace is a
matter of varying `c`. Read `TERRACES` and `_STAIR_ANCHORS` first; everything
else hangs off them.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER

# ---------------------------------------------------------------- extents
# 576 m x 576 m on a 96x96-tile server map at one metre per tile, the shape
# Amberwood, Mirrorhold, Amethyst Barrens and Crownwater already use. The
# arrival datum sits 30% in from the south-west, as theirs do.
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# The whole composition is written in a 192 m design space and scaled here, so
# the aerial concept's layout is preserved rather than stretched. Changing the
# region's extent is this one constant.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A terrace court is sized by the buildings standing on it and by how far a
# player will walk across it, not by how big the map is.
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

SEA_LEVEL = 0.0
TERRAIN_CELL = 2.0

# ------------------------------------------------------------- the stair
# (s_start, s_end, height, name). The gaps between consecutive shelves are the
# risers: the cliff faces that carry the waterfalls.
#
# Riser gaps are deliberately narrow. A 2.5-unit gap is 10.6 m of ground for a
# rise of 17 to 28 m, which is a cliff; the 6-unit gaps of the first draft were
# 25 m of ground for the same rise, which is a 40-degree ramp a player simply
# walks up, and the region stopped reading as a stair at all. The one wide gap
# is seabed to strand, which is a beach and should be a ramp.
#
# Heights are world metres and are NOT scaled with the region. A 24 m cliff is
# a 24 m cliff whether the map is 192 m or 576 m across; doubling relief along
# with area would double every climb a player makes and change no picture.
TERRACES: tuple[tuple[float, float, float, str], ...] = (
    (-58.0, -38.0, -13.0, "seabed"),
    (-31.0, -27.0, 0.4, "strand"),
    (-24.5, -14.0, 7.0, "quay"),
    (-11.5, 4.0, 24.0, "lower"),
    (6.5, 27.0, 46.0, "middle"),
    (29.5, 52.0, 72.0, "upper"),
    (54.5, 80.0, 100.0, "temple"),
    (82.5, 133.0, 124.0, "summit"),
)

# Fraction of a riser rounded off at each end. Small: the middle of a riser has
# to be a genuine cliff, and rounding is what turned it into a ramp before.
RISER_SOFTNESS = 0.18


def stair_axis(x, z):
    """`s`: how far up the stair, in design space."""
    return (np.asarray(x, dtype=np.float64) / SCALE
            - np.asarray(z, dtype=np.float64) / SCALE) * 0.5


def cross_axis(x, z):
    """`c`: how far along a terrace, in design space."""
    return (np.asarray(x, dtype=np.float64) / SCALE
            + np.asarray(z, dtype=np.float64) / SCALE) * 0.5


def stair_height(s) -> np.ndarray:
    """The terrace profile: level shelves joined by steep, rounded risers."""
    s = np.asarray(s, dtype=np.float64)
    out = np.full(np.shape(s), TERRACES[0][2], dtype=np.float64)
    for index in range(len(TERRACES) - 1):
        _, end, low, _ = TERRACES[index]
        start, _, high, _ = TERRACES[index + 1]
        span = max(start - end, 1e-6)
        t = np.clip((s - end) / span, 0.0, 1.0)
        soft = RISER_SOFTNESS
        t = np.clip((t - soft) / max(1.0 - 2.0 * soft, 1e-6), 0.0, 1.0)
        out = out + (high - low) * (t * t * (3.0 - 2.0 * t))
    return out


def terrace_level(name: str) -> float:
    for _, _, height, label in TERRACES:
        if label == name:
            return height
    raise KeyError(name)


def terrace_span(name: str) -> tuple[float, float]:
    for start, end, _, label in TERRACES:
        if label == name:
            return start, end
    raise KeyError(name)


def terrace_of(s: float) -> str:
    """Which shelf an `s` falls on, or the riser below it."""
    for start, end, _, label in TERRACES:
        if start <= s <= end:
            return label
    return "riser"


# ---------------------------------------------------------------- anchors
# (s, c) in design space, grouped by the terrace each one stands on. Placing in
# stair coordinates is the whole point: `s` is checked against the shelf spans
# by `_check_anchors()` at import, so a place that would sit on a cliff face is
# a build-time error rather than something noticed in a capture six hours later.
_STAIR_ANCHORS: dict[str, tuple[float, float]] = {
    # -- seabed: the lagoon itself
    "lagoon": (-46.0, 8.0),
    "lagoon_mouth": (-42.0, -14.0),
    "sea_stacks": (-50.0, 6.0),
    # -- strand: the beach at the foot of the first cliff
    "boat_landing": (-29.0, -6.0),
    "strand_camp": (-28.0, 14.0),
    "mangrove": (-28.0, 28.0),
    # The Westhaven crossing is a sea quay, not a road: this lands exactly on
    # the server's existing verdant_stair/westhaven portal tile, (6, 58) on the
    # 192-cell map, which is (18, 174) at 576 and Godot (-156, 0).
    "westgate": (-28.0, -28.0),
    # -- quay terrace: the region's front door from the water
    "west_quay": (-21.0, -8.0),
    "quay_market": (-19.0, 4.0),
    "quay_falls": (-22.0, 20.0),
    "west_hollow": (-16.0, -28.0),
    # -- lower terrace: arrival, the waygate, the town
    "waygate": (0.0, 0.0),               # server (174, 174), Godot origin
    "lower_plaza": (2.0, 0.0),
    "herbalist": (-2.0, -4.0),           # Tessara, server (156, 180)
    "provisioner": (3.0, 2.0),           # Orru Moss, server (192, 180)
    "lower_pools": (-6.0, 6.0),
    "lower_gardens": (0.0, 12.0),
    "lower_gate": (-9.0, -12.0),
    "south_landing": (-2.0, 24.0),
    "stair_foot": (-2.0, -12.0),
    "south_grove": (-4.0, 40.0),
    "lotus_pools": (-1.0, 34.0),
    "west_ravine": (-10.0, -30.0),
    # -- middle terrace: cenote, canopy village, the gorge crossings
    "stair_head": (14.0, -12.0),
    "cenote": (14.0, -20.0),
    "cenote_court": (16.0, -14.0),
    "canopy_village": (10.0, -32.0),
    "village_landing": (12.0, -24.0),
    "middle_market": (20.0, -4.0),
    "root_crossing": (24.0, 6.0),
    "east_lookout": (25.0, 20.0),
    "fern_hollow": (11.0, -44.0),
    "fern_camp": (8.0, -52.0),
    "rope_crossing_low": (26.0, 18.0),
    "south_watch": (18.0, 40.0),
    "south_quay": (14.0, 54.0),
    "east_grove": (24.0, 44.0),
    "ravine_bridge": (10.5, -61.5),
    # -- upper terrace: the water shrine, the aqueduct, the old terraces
    "water_shrine": (44.0, -6.0),
    "shrine_pool": (42.0, -12.0),
    "upper_court": (40.0, 12.0),
    "orchid_terrace": (45.0, -20.0),
    # The arcade spans the north gorge, which is also where the aerial concept
    # puts it: upper left, north-west, high on the terrace. Sited between two
    # flat anchors it was an arcade standing on level ground with nothing
    # underneath it, which verify_runtime caught as a buried landmark.
    "aqueduct_west": (48.0, -76.0),
    "aqueduct_east": (48.0, -58.0),
    "hanging_gardens": (35.0, 26.0),
    "old_terrace": (46.0, -34.0),
    "north_glade": (32.0, -50.0),
    "north_cenote": (36.0, -62.0),
    "north_watch": (48.0, -44.0),
    "rope_crossing_high": (33.0, 34.0),
    "upper_falls": (50.0, -24.0),
    "stone_ring": (38.0, -72.0),
    "vine_bridge_north": (44.0, -66.0),
    # -- temple terrace: the region's summit landmark
    "temple_stair": (57.0, -6.0),
    "temple_court": (62.0, -2.0),
    "great_temple": (68.0, 2.0),
    "sun_pavilion": (72.0, -10.0),
    "temple_falls": (66.0, -16.0),
    "priest_walk": (64.0, 12.0),
    "high_camp": (74.0, 10.0),
    "far_falls": (58.0, -50.0),
    "deep_jungle": (62.0, -60.0),
    # -- summit ridge and the east pass out to Ssarathi Ruins
    "east_pass": (90.0, 40.0),
    "ridge_shrine": (86.0, 18.0),
    "summit_watch": (92.0, -14.0),
    "cloud_terrace": (96.0, -26.0),
    "quarry": (88.0, 30.0),
    "east_terrace": (95.0, 22.0),
    "kiln_yard": (84.0, 26.0),
    "boundary_shrine": (100.0, 8.0),
    "summit_pools": (98.0, -20.0),
    "north_pass": (90.0, -42.0),
}

# Which terrace each anchor is meant to stand on. Checked at import.
_ANCHOR_TERRACE: dict[str, str] = {
    **{n: "seabed" for n in ("lagoon", "lagoon_mouth", "sea_stacks")},
    **{n: "strand" for n in ("boat_landing", "strand_camp", "mangrove", "westgate")},
    **{n: "quay" for n in ("west_quay", "quay_market", "quay_falls", "west_hollow")},
    **{n: "lower" for n in (
        "waygate", "lower_plaza", "herbalist", "provisioner", "lower_pools",
        "lower_gardens", "lower_gate", "south_landing", "stair_foot",
        "south_grove", "lotus_pools", "west_ravine")},
    **{n: "middle" for n in (
        "stair_head", "cenote", "cenote_court", "canopy_village",
        "village_landing", "middle_market", "root_crossing", "east_lookout",
        "fern_hollow", "fern_camp", "rope_crossing_low", "south_watch",
        "south_quay", "east_grove", "ravine_bridge")},
    **{n: "upper" for n in (
        "water_shrine", "shrine_pool", "upper_court", "orchid_terrace",
        "aqueduct_west", "aqueduct_east", "hanging_gardens", "old_terrace",
        "north_glade", "north_cenote", "north_watch", "rope_crossing_high",
        "upper_falls", "stone_ring", "vine_bridge_north")},
    **{n: "temple" for n in (
        "temple_stair", "temple_court", "great_temple", "sun_pavilion",
        "temple_falls", "priest_walk", "high_camp", "far_falls", "deep_jungle")},
    **{n: "summit" for n in (
        "east_pass", "ridge_shrine", "summit_watch", "cloud_terrace", "quarry",
        "east_terrace", "kiln_yard", "boundary_shrine", "summit_pools",
        "north_pass")},
}


def _design_from_stair(s: float, c: float) -> tuple[float, float]:
    return s + c, c - s


DESIGN_MIN_X, DESIGN_MAX_X = -58.0, 133.0
DESIGN_MIN_Z, DESIGN_MAX_Z = -133.0, 58.0


def _check_anchors() -> None:
    """Every anchor is on the shelf it claims, and inside the design frame."""
    problems = []
    for name, (s, c) in _STAIR_ANCHORS.items():
        want = _ANCHOR_TERRACE.get(name)
        if want is None:
            problems.append(f"{name}: no terrace declared")
            continue
        start, end = terrace_span(want)
        if not start <= s <= end:
            problems.append(
                f"{name}: s={s} is not on '{want}' ({start}..{end}); "
                f"it is on '{terrace_of(s)}'")
        x, z = _design_from_stair(s, c)
        if not DESIGN_MIN_X <= x <= DESIGN_MAX_X or not DESIGN_MIN_Z <= z <= DESIGN_MAX_Z:
            problems.append(f"{name}: design ({x}, {z}) is outside the frame")
    if problems:
        raise ValueError("region anchors are inconsistent:\n  "
                         + "\n  ".join(problems))


_check_anchors()

_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    name: _design_from_stair(s, c) for name, (s, c) in _STAIR_ANCHORS.items()}

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()}

SPAWN_DESIGN = (0.0, 0.0)
SPAWN = (0.0, 0.0)
SPAWN_QUAY = ANCHORS["west_quay"]
SPAWN_TEMPLE = ANCHORS["temple_court"]


def _route(*points) -> np.ndarray:
    """Route points are written in design space and scaled to world metres."""
    return np.array([[float(p[0]) * SCALE, float(p[1]) * SCALE] for p in points])


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


def _via(s: float, c: float) -> tuple[float, float]:
    """An intermediate route point, written in stair coordinates like the rest."""
    return _design_from_stair(s, c)


# ----------------------------------------------------------------- routes
# The stair route is the spine: it climbs the whole diagonal, and everything
# else branches off it. A route that crosses a riser is graded into it, so the
# cliff opens for the road instead of the road floating over the cliff. Those
# climbs are written as switchbacks - two or three points inside the riser at
# different `c` - because a road straight up a 24 m cliff reads as a ramp.
ROUTES: dict[str, np.ndarray] = {
    "strand_path": _route(_design("mangrove"), _design("strand_camp"),
                          _via(-29.0, 4.0), _design("boat_landing"),
                          _design("westgate")),
    # strand to quay: the first climb, out of the beach onto the sea terrace
    "quay_climb": _route(_design("boat_landing"), _via(-27.0, -2.0),
                         _via(-25.5, 4.0), _via(-24.0, -2.0),
                         _design("west_quay")),
    "quay_road": _route(_design("west_hollow"), _design("west_quay"),
                        _design("quay_market"), _design("quay_falls")),
    # quay to lower: a switchback stair up the 17 m sea cliff
    "lower_climb": _route(_design("quay_market"), _via(-14.5, 0.0),
                          _via(-13.0, 8.0), _via(-12.0, 0.0),
                          _design("lower_pools"), _design("waygate")),
    "lower_ring": _route(_design("lower_gate"), _design("waygate"),
                         _design("lower_plaza"), _design("lower_gardens"),
                         _design("south_landing"), _design("lotus_pools"),
                         _design("south_grove")),
    # the Grand Stair: lower to middle, the region's central climb
    "grand_stair": _route(_design("lower_plaza"), _design("stair_foot"),
                          _design("stair_head")),
    "middle_ring": _route(_design("canopy_village"), _design("village_landing"),
                          _design("stair_head"), _design("cenote_court"),
                          _design("middle_market"), _design("east_lookout"),
                          _design("root_crossing")),
    "cenote_path": _route(_design("cenote_court"), _design("cenote")),
    "village_path": _route(_design("village_landing"), _design("canopy_village"),
                           _design("fern_hollow"), _design("fern_camp")),
    # middle to upper, beside the shrine falls
    "shrine_climb": _route(_design("middle_market"), _via(27.5, -6.0),
                           _via(28.5, -12.0), _via(29.5, -8.0),
                           _design("shrine_pool"), _design("water_shrine")),
    "upper_ring": _route(_design("aqueduct_west"), _design("orchid_terrace"),
                         _design("water_shrine"), _design("aqueduct_east"),
                         _design("upper_court"), _design("hanging_gardens")),
    "aqueduct_walk": _route(_design("upper_falls"), _design("old_terrace"),
                            _design("aqueduct_west"), _via(41.0, -18.0),
                            _design("aqueduct_east")),
    # upper to temple: the processional way
    "temple_way": _route(_design("upper_court"), _via(52.5, 6.0),
                         _via(53.5, 0.0), _via(54.5, 4.0),
                         _design("temple_stair"), _design("temple_court"),
                         _design("great_temple")),
    "temple_ring": _route(_design("temple_falls"), _design("temple_court"),
                          _design("priest_walk"), _design("high_camp"),
                          _design("sun_pavilion")),
    # temple to summit, and out east to Sunmane Steppe
    "summit_climb": _route(_design("high_camp"), _via(80.5, 14.0),
                           _via(81.5, 20.0), _via(82.5, 16.0),
                           _design("kiln_yard"), _design("ridge_shrine")),
    "east_road": _route(_design("ridge_shrine"), _design("quarry"),
                        _design("east_terrace"), _design("east_pass")),
    "summit_track": _route(_design("ridge_shrine"), _design("summit_watch"),
                           _design("cloud_terrace"), _design("summit_pools"),
                           _design("north_pass")),
    # --- routes serving the second ring -------------------------------
    "ravine_path": _route(_design("west_hollow"), _design("west_ravine"),
                          _via(-2.0, -46.0), _design("ravine_bridge"),
                          _design("fern_camp")),
    "north_glade_path": _route(_design("fern_hollow"), _via(20.0, -48.0),
                               _via(29.5, -50.0), _design("north_glade"),
                               _design("north_cenote"), _design("stone_ring")),
    "lotus_path": _route(_design("lotus_pools"), _via(6.5, 40.0),
                         _design("south_watch"), _design("south_quay"),
                         _design("east_grove")),
    "east_grove_path": _route(_design("east_grove"), _design("rope_crossing_low"),
                              _via(29.5, 30.0), _design("rope_crossing_high"),
                              _design("hanging_gardens")),
    "old_terrace_path": _route(_design("orchid_terrace"), _design("old_terrace"),
                               _design("north_watch"),
                               _design("vine_bridge_north")),
    "deep_jungle_path": _route(_design("vine_bridge_north"), _via(52.0, -58.0),
                               _via(54.5, -54.0), _design("far_falls"),
                               _design("deep_jungle")),
    "boundary_path": _route(_design("east_pass"), _design("boundary_shrine"),
                            _design("summit_pools")),
    "north_pass_path": _route(_design("deep_jungle"), _via(80.0, -56.0),
                              _via(82.5, -50.0), _design("north_pass")),
}

# --------------------------------------------------------------- water
# Every watercourse runs down the fall line, which on a diagonal stair means
# south-west: decreasing `s` at roughly constant `c`. Where one crosses a riser
# it is a waterfall, and those points are exactly the riser gaps in TERRACES,
# so the geometry pass can find them rather than having them listed by hand.
STREAMS: dict[str, np.ndarray] = {
    "temple_beck": _route(_design("temple_falls"), _via(54.5, -18.0),
                          _design("upper_falls"), _via(29.5, -26.0),
                          _via(20.0, -28.0), _design("cenote_court"),
                          _via(4.0, -16.0), _design("lower_pools"),
                          _via(-14.0, 4.0), _design("quay_falls"),
                          _via(-29.0, 12.0), _design("lagoon")),
    "shrine_rill": _route(_design("sun_pavilion"), _design("water_shrine"),
                          _design("shrine_pool"), _via(29.5, -16.0),
                          _via(20.0, -18.0), _design("cenote")),
    "cenote_outfall": _route(_design("cenote"), _via(9.0, -20.0),
                             _via(4.0, -22.0), _via(-3.0, -20.0),
                             _design("lower_pools"), _via(-11.5, 2.0),
                             _via(-20.0, -2.0), _design("boat_landing"),
                             _design("lagoon_mouth")),
    "east_brook": _route(_design("cloud_terrace"), _design("summit_watch"),
                         _via(80.0, 4.0), _design("priest_walk"),
                         _via(52.0, 14.0), _design("upper_court"),
                         _via(29.5, 22.0), _design("rope_crossing_low"),
                         _design("east_grove"), _design("south_quay")),
    "north_burn": _route(_design("north_pass"), _design("deep_jungle"),
                         _design("far_falls"), _via(52.0, -60.0),
                         _design("stone_ring"), _design("north_cenote"),
                         _via(29.5, -56.0), _design("fern_camp"),
                         _design("ravine_bridge"), _design("west_ravine")),
    "garden_rill": _route(_design("hanging_gardens"), _via(29.5, 30.0),
                          _design("south_watch"), _design("lotus_pools"),
                          _design("south_grove")),
}

# Gorges: cut deeper than a stream and crossed by the region's bridges rather
# than forded. Carved after the stair profile, so they bite through the terrace
# shelves and give the bridges something real to span.
RAVINES: dict[str, np.ndarray] = {
    "west_ravine": _route(_via(12.0, -62.0), _design("ravine_bridge"),
                          _via(0.0, -46.0), _design("west_ravine"),
                          _via(-18.0, -26.0)),
    "root_gorge": _route(_via(29.0, 4.0), _design("root_crossing"),
                         _via(18.0, 10.0), _via(8.0, 16.0)),
    "rope_gorge": _route(_via(38.0, 36.0), _design("rope_crossing_high"),
                         _via(29.0, 26.0), _design("rope_crossing_low"),
                         _via(20.0, 12.0)),
    "north_gorge": _route(_via(52.0, -68.0), _design("vine_bridge_north"),
                          _via(40.0, -64.0), _design("north_cenote")),
}

# (anchor, gorge, style, deck height above the gorge floor). Read by the
# geometry pass; the terrain pass only needs to know where the gorges are.
CROSSINGS: tuple[tuple[str, str, str, float], ...] = (
    ("root_crossing", "root_gorge", "root", 5.0),
    ("rope_crossing_low", "rope_gorge", "rope", 6.5),
    ("rope_crossing_high", "rope_gorge", "rope", 7.5),
    ("ravine_bridge", "west_ravine", "rope", 6.0),
    ("vine_bridge_north", "north_gorge", "rope", 6.0),
)

# Where a stream crosses a riser, water falls. Computed rather than listed so
# adding a stream or moving a terrace cannot leave a fall behind.
def waterfall_sites() -> list[tuple[str, float, float, float, float]]:
    """(stream, world x, world z, top height, drop) for every stream/riser cross."""
    sites = []
    for name, points in STREAMS.items():
        s_values = stair_axis(points[:, 0], points[:, 1])
        for index in range(len(TERRACES) - 1):
            _, end, low, _ = TERRACES[index]
            start, _, high, _ = TERRACES[index + 1]
            mid = (start + end) * 0.5
            for k in range(len(s_values) - 1):
                a, b = float(s_values[k]), float(s_values[k + 1])
                if (a - mid) * (b - mid) > 0.0:
                    continue
                if abs(b - a) < 1e-6:
                    continue
                t = (mid - a) / (b - a)
                x = float(points[k, 0] + (points[k + 1, 0] - points[k, 0]) * t)
                z = float(points[k, 1] + (points[k + 1, 1] - points[k, 1]) * t)
                sites.append((name, x, z, high, high - low))
                break
    return sites


def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9, octaves=4,
                        seed=seed)


def shoreline_s(c):
    """How far up the stair the water reaches, in design-space `s`.

    The lagoon is not a straight coast: it has a deep inlet the boats use, a
    headland between that and the open sea, and a shallow mangrove bight in the
    south. Written against `c` so it keeps its shape at any SCALE.
    """
    c = np.asarray(c, dtype=np.float64)
    base = -34.0
    base = base + 3.2 * np.sin(c * 0.052 + 0.7)
    base = base + 1.8 * np.sin(c * 0.131 + 2.4)
    # the boat inlet, reaching further inland than anywhere else
    base = base + 6.5 * np.exp(-((c - 6.0) ** 2) / (2.0 * 12.0 ** 2))
    # the mangrove bight in the south
    base = base + 4.0 * np.exp(-((c - 44.0) ** 2) / (2.0 * 10.0 ** 2))
    # the headland between them
    base = base - 4.5 * np.exp(-((c - 26.0) ** 2) / (2.0 * 7.0 ** 2))
    return base


# ------------------------------------------------------------------ build
def build_terrain(seed: int = 20260829) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    s = stair_axis(t.gx, t.gz)
    c = cross_axis(t.gx, t.gz)

    # 1. the stair itself. The shelf edges wander so the region does not read as
    #    a set of ruled stripes - which is exactly what four unbroken diagonal
    #    cliffs looked like before this. Two scales of wander: a long one that
    #    swings a whole cliff line tens of metres, and a shorter one that
    #    scallops its edge, so terraces interlock the way the concept's do.
    #    Displacing `s` cannot break the profile: `stair_height` stays monotonic
    #    in its argument, so a shelf still meets its neighbour at a riser, the
    #    riser has just moved.
    #    Frequencies matter more than amplitudes here: at 0.004 the noise field
    #    is under three cells wide across a 635 m map, so it is nearly constant
    #    and the cliffs came out as four ruled lines however large the amplitude.
    wander = ((N.fbm(t.gx * 0.0105, t.gz * 0.0105, octaves=3, seed=seed) - 0.5) * 9.0
              + (N.fbm(t.gx * 0.0290, t.gz * 0.0290, octaves=3, seed=seed + 5) - 0.5) * 3.0)
    t.height = stair_height(s + wander)

    # 2. relief on each shelf: enough to make a shelf a place rather than a
    #    plane, never enough to hide that it is level ground.
    t.base_noise(2.4, 0.0125, seed=seed + 17, octaves=5, warp=1.1)
    t.base_noise(0.8, 0.055, seed=seed + 19, octaves=4)

    # 3. limestone knolls standing on the shelves, which is what puts vertical
    #    interest inside a terrace instead of only at its edge.
    for name, radius, height in (
            ("north_glade", 24.0, 15.0), ("east_grove", 20.0, 12.0),
            ("deep_jungle", 26.0, 20.0), ("south_grove", 18.0, 10.0),
            ("quarry", 16.0, 8.0), ("stone_ring", 18.0, 13.0),
            ("west_hollow", 14.0, 7.0), ("sea_stacks", 12.0, 16.0),
            ("high_camp", 14.0, 9.0), ("north_watch", 15.0, 11.0)):
        t.add_dome(ANCHORS[name], radius * SCALE, height, power=1.6,
                   noise_seed=seed + N.stable_hash(name) % 71, noise_amount=0.24)

    # hollows: the cenotes are basins, not bumps, and the pools are scooped
    for name, radius, depth in (
            ("cenote", 10.0, -14.0), ("north_cenote", 8.0, -11.0),
            ("lower_pools", 13.0, -1.2), ("shrine_pool", 11.0, -2.2),
            ("lotus_pools", 14.0, -2.0), ("summit_pools", 10.0, -4.0),
            ("quay_falls", 10.0, -2.5)):
        t.add_dome(ANCHORS[name], radius * SCALE, depth, power=1.3)

    # 4. the sea. The lagoon fills the low corner past the shoreline, and the
    #    seabed shelves away from it to the region's floor.
    shore = shoreline_s(c)
    offshore = np.clip(shore - s, 0.0, None)
    seaward = s < shore
    t.height = np.where(
        seaward,
        np.minimum(t.height, -offshore * 0.62 * (1.0 + offshore * 0.018)),
        t.height)
    t.height = np.maximum(t.height, -21.0)

    # 5. watercourses. The gorges are NOT cut here: see `carve_ravines`.
    for name, points in STREAMS.items():
        wide = name in ("temple_beck", "east_brook", "north_burn")
        t.carve_channel(points, (3.4 if wide else 2.6) * SCALE,
                        3.0 if wide else 2.2, bank=2.5,
                        seed=seed + N.stable_hash(name) % 97)

    # 6. erosion and a light smooth. Both kept gentle: too much of either
    #    rounds the risers off and the stair stops reading as a stair.
    t.erode(iterations=10, strength=0.20)
    t.smooth(iterations=1, weight=0.28)
    return t


def carve_ravines(t: TER.Terrain, seed: int = 20260829) -> None:
    """Cut the gorges the bridges span - after the built ground, not before.

    This used to run inside `build_terrain`, before the routes were graded.
    Every gorge is a bridge site, so a route runs up to each one, and
    `grade_path` levels its corridor with `flatten=0.90` - which quietly filled
    the gorges back in. The symptom was an aqueduct arcade standing on ground
    a metre below its own deck with nothing under it to span, and rope bridges
    crossing a shallow dip. Cutting last means the road ends at a real edge,
    which is what the bridge is there for.
    """
    for name, points in RAVINES.items():
        core = t.carve_channel(points, 4.6 * SCALE, 11.5, bank=1.8,
                               seed=seed + N.stable_hash(name) % 89)
        # a road surface carried over the void by grade_path is not a road any
        # more; hand the floor and walls back to the rule that paints rock
        inside = core > 0.30
        t.surface = np.where(inside, TER.ROCK, t.surface)
        t.tree_block |= core > 0.15


def apply_built_ground(t: TER.Terrain, seed: int = 20260829) -> None:
    """Terraces, courts and graded routes - the built part of the surface."""
    # -- routes ----------------------------------------------------------
    paved = {"grand_stair", "temple_way", "lower_ring", "lower_climb",
             "quay_climb", "quay_road", "middle_ring", "upper_ring",
             "temple_ring", "east_road", "shrine_climb", "summit_climb"}
    for name, points in ROUTES.items():
        if name in ("grand_stair", "temple_way", "lower_ring"):
            width = 4.6 * LOCAL
        elif name in paved:
            width = 3.8 * LOCAL
        else:
            width = 3.0 * LOCAL
        t.grade_path(points, width, shoulder=2.0,
                     surface=TER.PAVING if name in paved else TER.PATH,
                     seed=seed + N.stable_hash(name) % 89, flatten=0.90)

    # -- the built terraces ----------------------------------------------
    # Each is cut to its own terrace's height rather than to the local ground,
    # so a court is genuinely level even where the shelf under it is not.
    def court(name: str, half_x: float, half_z: float, rotation: float = 0.0,
              surface: int = TER.PAVING, lift: float = 0.0) -> None:
        t.rect_terrace(ANCHORS[name], half_x * LOCAL, half_z * LOCAL,
                       terrace_level(_ANCHOR_TERRACE[name]) + lift, rotation,
                       surface)

    def disc(name: str, radius: float, surface: int = TER.PAVING,
             lift: float = 0.0) -> None:
        t.terrace(ANCHORS[name], radius * LOCAL,
                  terrace_level(_ANCHOR_TERRACE[name]) + lift, surface)

    # strand and quay
    court("boat_landing", 9.0, 7.0, 0.0, TER.SHORE)
    court("strand_camp", 7.0, 6.0, -0.15, TER.SHORE)
    court("mangrove", 9.0, 8.0, 0.0, TER.SHORE)
    court("westgate", 8.0, 9.0, 0.0, TER.SHORE)
    court("west_quay", 13.0, 10.0, 0.0, TER.PAVING)
    court("quay_market", 10.0, 8.0, 0.12, TER.PAVING)
    court("west_hollow", 8.0, 7.0, 0.0, TER.MEADOW)

    # lower terrace: the arrival town
    disc("waygate", 11.0, TER.TERRACE_MOSS)
    court("lower_plaza", 13.0, 10.0, 0.0, TER.PAVING)
    court("herbalist", 6.0, 5.0, 0.10, TER.PAVING)
    court("provisioner", 6.0, 5.0, -0.10, TER.PAVING)
    court("lower_gardens", 11.0, 9.0, 0.0, TER.MEADOW)
    court("lower_gate", 7.0, 8.0, 0.0, TER.PAVING)
    court("south_landing", 9.0, 7.0, 0.0, TER.PAVING)
    court("stair_foot", 9.0, 7.0, 0.0, TER.TERRACE_MOSS)
    court("south_grove", 10.0, 8.0, 0.0, TER.MEADOW)

    # middle terrace
    court("stair_head", 9.0, 7.0, 0.0, TER.TERRACE_MOSS)
    court("cenote_court", 12.0, 10.0, 0.0, TER.TERRACE_MOSS)
    court("middle_market", 10.0, 8.0, 0.15, TER.PAVING)
    court("village_landing", 8.0, 7.0, 0.0, TER.PAVING)
    court("east_lookout", 8.0, 6.0, -0.2, TER.PAVING)
    disc("canopy_village", 9.0, TER.PATH)
    court("fern_camp", 7.0, 6.0, 0.0, TER.PATH)
    court("south_watch", 7.0, 6.0, 0.0, TER.PATH)
    court("south_quay", 8.0, 7.0, 0.0, TER.PAVING)
    court("east_grove", 10.0, 8.0, 0.0, TER.MEADOW)

    # upper terrace
    court("water_shrine", 12.0, 11.0, 0.0, TER.TERRACE_MOSS)
    court("upper_court", 12.0, 10.0, 0.0, TER.PAVING)
    court("orchid_terrace", 10.0, 8.0, 0.1, TER.MEADOW)
    court("aqueduct_west", 7.0, 6.0, 0.0, TER.PAVING)
    court("aqueduct_east", 7.0, 6.0, 0.0, TER.PAVING)
    court("hanging_gardens", 11.0, 9.0, 0.0, TER.MEADOW)
    court("old_terrace", 10.0, 8.0, 0.0, TER.TERRACE_MOSS)
    court("north_glade", 11.0, 9.0, 0.0, TER.MEADOW)
    court("north_watch", 6.0, 6.0, 0.0, TER.PATH)
    court("stone_ring", 9.0, 9.0, 0.0, TER.MEADOW)

    # temple terrace
    court("great_temple", 17.0, 14.0, 0.0, TER.PAVING)
    court("temple_court", 14.0, 12.0, 0.0, TER.PAVING, lift=-1.8)
    court("temple_stair", 9.0, 8.0, 0.0, TER.TERRACE_MOSS, lift=-3.6)
    court("sun_pavilion", 10.0, 9.0, 0.0, TER.PAVING)
    court("priest_walk", 9.0, 7.0, 0.0, TER.PAVING)
    court("high_camp", 7.0, 6.0, 0.0, TER.PATH)
    court("deep_jungle", 11.0, 9.0, 0.0, TER.MEADOW)

    # summit
    court("east_pass", 9.0, 11.0, 0.0, TER.PAVING)
    court("ridge_shrine", 8.0, 7.0, 0.0, TER.TERRACE_MOSS)
    court("summit_watch", 7.0, 6.0, 0.0, TER.PAVING)
    court("cloud_terrace", 10.0, 8.0, 0.0, TER.MEADOW)
    court("quarry", 10.0, 8.0, 0.0, TER.ROCK)
    court("east_terrace", 9.0, 8.0, 0.0, TER.PAVING)
    court("kiln_yard", 8.0, 7.0, 0.0, TER.PATH)
    court("boundary_shrine", 6.0, 6.0, 0.0, TER.TERRACE_MOSS)
    court("north_pass", 8.0, 7.0, 0.0, TER.PATH)

    # -- keep the trees off the built ground -----------------------------
    for name, radius in (
            ("waygate", 13.0), ("lower_plaza", 15.0), ("west_quay", 15.0),
            ("quay_market", 12.0), ("cenote", 14.0), ("cenote_court", 14.0),
            ("great_temple", 20.0), ("temple_court", 16.0),
            ("water_shrine", 14.0), ("upper_court", 14.0),
            ("canopy_village", 12.0), ("east_pass", 12.0),
            ("sun_pavilion", 12.0), ("boat_landing", 11.0), ("westgate", 10.0),
            ("stair_foot", 11.0), ("stair_head", 11.0),
            ("lower_gardens", 13.0), ("hanging_gardens", 13.0),
            ("orchid_terrace", 12.0), ("summit_watch", 9.0),
            ("cloud_terrace", 12.0), ("quarry", 12.0),
            ("ridge_shrine", 10.0), ("old_terrace", 12.0),
            ("middle_market", 12.0), ("south_quay", 10.0),
            ("temple_stair", 11.0), ("priest_walk", 11.0),
            ("east_terrace", 11.0), ("lotus_pools", 16.0),
            ("shrine_pool", 14.0), ("lower_pools", 16.0),
            ("north_cenote", 11.0), ("stone_ring", 11.0),
            ("boundary_shrine", 8.0), ("village_landing", 10.0),
            ("east_lookout", 10.0), ("high_camp", 9.0),
            ("aqueduct_west", 9.0), ("aqueduct_east", 9.0)):
        t.mark_blocked_disc(ANCHORS[name], radius * LOCAL)

    # -- surface classes --------------------------------------------------
    # Ground cover follows wetness rather than being painted on: fern glade in
    # the damp hollows, jungle floor everywhere else.
    ground = t.surface == TER.FOREST
    damp = region_noise(t, seed + 73)
    t.surface = np.where(ground & (damp > 0.74), TER.MEADOW, t.surface)

    # Wet rock only where a fall actually lands. The first draft used the whole
    # riser band and turned a seventh of the map into spray-wet stone; the rule
    # that matters is proximity to a watercourse *and* being on a riser.
    s = stair_axis(t.gx, t.gz)
    riser = np.zeros(t.height.shape, dtype=bool)
    for index in range(len(TERRACES) - 1):
        _, end, _, _ = TERRACES[index]
        start, _, _, _ = TERRACES[index + 1]
        riser |= (s > end - 1.5) & (s < start + 1.5)
    near_water = np.full(t.height.shape, 1e9)
    for points in STREAMS.values():
        distance, _ = TER._polyline_distance(t.gx, t.gz, points)
        near_water = np.minimum(near_water, distance)
    spray = region_noise(t, seed + 91, frequency=0.055)
    protected = np.isin(t.surface, [TER.PAVING, TER.TERRACE_MOSS, TER.PATH])
    t.surface = np.where(riser & (near_water < 26.0) & (spray > 0.42) & ~protected,
                         TER.WET_ROCK, t.surface)

    # The gorges go in after the roads and the terraces, so nothing fills them.
    carve_ravines(t, seed)

    # `grade_path` marks its whole corridor as built surface, including where a
    # route crosses a riser - and PAVING and PATH are AUTHORED_SURFACES, so the
    # slope rule below will not touch them. The result was a six-metre-wide
    # pale ramp painted up every 60-degree cliff face, and those ramps filled
    # half the player-eye captures. A road does not exist on a face a player
    # cannot walk, so hand those cells back to the rock. The climbs are carried
    # by the authored stairs, not by the corridor.
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    too_steep = np.hypot(gradient_x, gradient_z) > 1.15
    built = np.isin(t.surface, [TER.PAVING, TER.PATH, TER.TERRACE_MOSS])
    t.surface = np.where(built & too_steep, TER.ROCK, t.surface)

    t.assign_surface_by_rule(SEA_LEVEL)
    t.dither_boundaries(seed=seed + 97, amount=0.45)

    # Limestone shelves continue into the surrounding jungle and lagoon.
    # Shared surveyed collars own the two roads; no rectangular perimeter rim.


# The surface-class to material mapping for this region. The terrain operators
# speak in classes; a jungle's FOREST is not Amberwood's forest floor, and this
# is the supported way to say so without touching the shared class list.
SURFACE_MATERIALS: dict[int, str] = {
    TER.FOREST: "verdant_jungle_floor",
    TER.PATH: "verdant_jungle_trail",
    TER.PAVING: "verdant_terrace_stone",
    TER.SHORE: "verdant_lagoon_sand",
    TER.ROCK: "verdant_limestone_cliff",
    TER.MEADOW: "verdant_fern_glade",
    TER.TERRACE_MOSS: "verdant_mossy_stone",
    TER.WET_ROCK: "verdant_wet_limestone",
}


# Surveyed foot/head pairs in world metres, with exact walking heights.
# Each spans the whole riser; no flight starts halfway up its cliff.
STAIR_RUNS = {
    "quay-climb": ((-166, 0.44, 0), (-138, 7.04, 0), 6.0),
    "lower-climb": ((-60, 7.04, 60), (-15, 24.04, 15), 7.0),
    "grand-stair": ((-42, 24.04, -30), (6, 46.04, -78), 9.5),
    "shrine-climb": ((39, 46.04, -87), (90, 72.04, -138), 7.5),
    "temple-climb": ((162, 72.04, -114), (216, 100.04, -168), 8.5),
    "summit-climb": ((291, 100.04, -147), (345, 124.04, -201), 7.0),
}
ACCESS_LANES = {
    "temple-road": ([(-168, 0), (-166, 0)], [0.4, 0.4], 6),
    "quay-contour": ([(-138, 0), (-112, 19), (-87, 39), (-60, 60)], [7]*4, 7),
    "quay-arrival": ([(-15, 15), (-12, 8), (-8, 4)], [24]*3, 6),
    "stair-court": ([(0, -14), (-24, -22), (-42, -30)], [24]*3, 7),
    "physick-lane": ([(-24, -22), (-24, -12), (-22.8, -8)], [24]*3, 4),
    "market-court": ([(7, 9), (29, 12)], [24]*2, 9),
    "sanctum-lane": ([(216, -168), (227, -177), (219, -189)], [100]*3, 6),
    "middle-procession": ([(6, -78), (22, -89), (39, -87)], [46]*3, 7),
    "upper-procession": ([(90, -138), (124, -122), (162, -114)], [72]*3, 7),
    "temple-forecourt": ([(216, -168), (194, -168), (170, -179), (180, -192)],
                         [100, 100, 98.2, 98.2], 7),
    "high-procession": ([(216, -168), (256, -154), (279, -141), (291, -147)], [100]*4, 7),
    "quarry-road": ([(345, -201), (335, -180), (338, -163), (370, -159), (390, -150)],
                    [124]*5, 8),
}


def access_distance(x, z):
    distance = float("inf")
    for foot, head, width in STAIR_RUNS.values():
        d, _ = TER._polyline_distance(np.asarray(x), np.asarray(z),
                                     np.asarray([[foot[0], foot[2]], [head[0], head[2]]]))
        distance = min(distance, float(d) - width / 2)
    for points, heights, width in ACCESS_LANES.values():
        d, _ = TER._polyline_distance(np.asarray(x), np.asarray(z), np.asarray(points))
        distance = min(distance, float(d) - width / 2)
    return distance


def prepare_access(t):
    from amberwood import routecraft as RC
    t.plateau((17, 12), 21, 24, edge=8, surface=TER.PAVING)
    t.plateau((330, -174), 9, 124, edge=8, surface=TER.PAVING)
    # Roads follow the shelves. No access lane crosses a carved bridge gorge.
    for points, heights, width in ACCESS_LANES.values():
        RC.grade_road(t, points, heights, width=width, shoulder=8,
                      surface=TER.PAVING, clearance=10)
    from amberwood import junglecraft as JC
    for foot, head, width in STAIR_RUNS.values():
        a, b = np.asarray(foot), np.asarray(head)
        delta = b[[0, 2]] - a[[0, 2]]
        length = float(np.linalg.norm(delta))
        rise = float(b[1] - a[1])
        profile = JC.stair_profile(width, rise, length, 1 if rise < 20 else 2)
        points = a[[0, 2]] + profile[:, :1] * delta / length
        clearance = np.full(len(profile), 0.30)
        clearance[0] = clearance[-1] = 0.04
        heights = a[1] + profile[:, 1] - clearance
        RC.grade_road(t, points, heights, width=width + 2, shoulder=8,
                      surface=TER.ROCK, clearance=12)
    t.plateau((-23, -8), 4.5, 24, edge=3, surface=TER.PAVING)
    d, _ = TER._polyline_distance(t.gx, t.gz, np.asarray(CENOTE_APPROACH)[:, [0, 2]])
    t.tree_block |= d < 7
    t.water_depth = np.clip(SEA_LEVEL - t.height, 0, None)

# Doors are at their visible thresholds. The cenote interior begins at the
# head of its descent, not in the water at the centre of the shaft.
DOOR_POSITIONS = {
    "temple-sanctum-door": (217.35, -193.47),
    "cenote-deeps-stair": (-6.3, -102.0),
    "physick-still-door": (-21.24, -7.32),
}
# An 8 cm threshold clears the spiral's first tread; their tops must not share a plane.
CENOTE_APPROACH = [(6, 46.19, -87), (2, 46.19, -92), (-6.3, 46.19, -102)]
CONTENT_LAYOUT = {
    "services": [
        {"role": "information", "position": [9, 24, 10]},
        {"role": "storage", "position": [16, 24, 11]},
        {"role": "crafting_station", "position": [23, 24, 12]},
        {"role": "training", "position": [29, 24, 12]},
    ],
    "roadClearance": 6.0,
    "wildlife": {
        "canopy_glider": [[55, -25, 32], [-55, -50, 25]],
        "leafwing_owl": [[60, -170, 35], [155, -240, 30]],
        "sapling_sprite": [[60, -25, 30]],
        "thornwood_dryad_queen": [[240, 25, 28]],
        "emerald_canopy_dragon": [[245, -285, 32], [325, -250, 25]],
        "swamp_heron": [[-110, 85, 23], [-35, 36, 22]],
        "moonshadow_lynx": [[130, -220, 25]],
    },
}


def access_waypoints(t):
    roads = [{"id": name, "waypoints": [[x, y, z] for (x, z), y in zip(points, heights)]}
             for name, (points, heights, width) in ACCESS_LANES.items()]
    roads.extend({"id": name, "waypoints": [list(foot), list(head)]}
                 for name, (foot, head, width) in STAIR_RUNS.items())
    roads.append({"id": "cenote-landing", "waypoints": CENOTE_APPROACH})
    return roads

# The compact revision keeps this native geographic vocabulary and kit while
# reauthoring its route surveys, relief and settlement surfaces.
from landscape_plan import configure as _configure_landscape
_configure_landscape(globals())
