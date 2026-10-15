"""The authored Ssarathi Ruins region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side and the surplus is raised into jungle-clad
valley walls, so a player can never walk off the authored world.

WHAT THE PAINTING ACTUALLY SHOWS
--------------------------------
Not a grey ruin field. The aerial is a *drowned serpent city in a flooded
jungle basin*: shallow turquoise water covering almost the whole floor, lily
pads across it, and a grid of raised stone causeways and platforms standing a
metre or two out of it, all in verdigris jade and gilt under heavy vine and
root overgrowth. A stepped ziggurat temple dominates the north-centre with
waterfalls coming off the cliffs behind it, and a single broad causeway runs
dead north up the middle to its foot. Round colonnaded pool-courts sit either
side of that axis. Timber docks and a small canvas market fringe the east and
south. Jungle closes every horizon.

THE ONE STRUCTURAL DECISION EVERYTHING ELSE FOLLOWS FROM
---------------------------------------------------------
The client grounds actors by casting a ray straight down at every server tile,
not only the walkable ones, so a region whose middle is water still needs
continuous ground under it. Ssarathi's heightfield therefore covers the entire
footprint and simply sits below the waterline across most of it - the basin
floor is *terrain*, not a hole.

The second half of that decision is what the causeways are made of. Crownwater
spans its open water with built bridge decks, because its islands stand in deep
lagoon. Ssarathi's water is ankle-to-knee deep almost everywhere, and the
concept's causeways are plainly solid stone embankments retained by walls at
the waterline - masonry fill, not viaduct. So they are built as *terrain
plateaus* carrying a paved surface class, not as `Walk_` decks over a void.

That is the safe choice for grounding as well as the accurate one: the walkable
city is terrain, which the ray cannot miss, and only the handful of genuine
spans over carved channels - panel 4's arch bridge and its siblings - are
authored decks that own their server cells.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER

# `Placement` and `RegionBuild` are the toolkit's shared build containers, not
# anything Amberwood-specific. Re-exported here so this module is the whole
# namespace a Ssarathi build script has to import.
from amberwood.region import Placement, RegionBuild  # noqa: F401

# ---------------------------------------------------------------- extents
# Authored at 576 m x 576 m, matching Amberwood, Mirrorhold, Whitehorn,
# Amethyst Barrens and Crownwater, so the server map is 96x96 ELM tiles at one
# metre per tile and the arrival datum moves from (58, 58) to (174, 174).
SERVER_ORIGIN = (116.0, 116.0)
SERVER_CELLS = 384
METRES_PER_TILE = 1.0

# The composition is written in a 192 m design space and scaled up here, so the
# aerial's layout is preserved rather than stretched.
SCALE = 2.0

# Distances between places scale with the region; the places themselves do not.
# A pool court is sized by the columns around it, a causeway by its balustrade.
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

TERRAIN_CELL = 1.0

# ------------------------------------------------------------------ datums
WATER_LEVEL = 0.0

# The flooded floor. Shallow on purpose: at -4 the water reads as a lake and
# the lily pads and drowned paving disappear into it. At -1.5 you can see the
# silt and the sunken kerbs through it, which is the concept's whole character.
BASIN_FLOOR = -1.55
# Navigable water. The channels the concept's boats and its arched bridges
# imply, cut deeper so they read as water you could not simply wade.
CHANNEL_FLOOR = -4.60
# The drowned lower terraces - paving that is under water but visibly paving.
DROWNED_STEP = -0.70

# The city's walkable stone. One metre eighty out of the water: high enough to
# stand clear and read as a retained embankment, low enough that a player on it
# is still down among the lilies rather than looking at them from a wall.
DECK = 1.80

# The temple's tiers, absolute metres. The silhouette is the region's one piece
# of real verticality; the rest of the composition is deliberately flat, as the
# painting is.
# Raised with the temple. At 5.2/10.4/16.2 over a 48 m-wide top tier the
# precinct was smaller than the ziggurat standing on it, so the lower stages
# were buried in the mound and the whole thing read as a small pagoda on a hill
# rather than as the region's dominant silhouette.
TIER_1 = 6.00
TIER_2 = 13.00
TIER_3 = 21.00

STELA_KNOLL = 13.50

SEA_LEVEL = WATER_LEVEL  # the toolkit's surface rules speak in this name


# ------------------------------------------------------- surface classes
# Surface-class ids are allocated in per-region blocks so concurrent region
# work does not collide: 7-10 Mirrorhold, 11-14 Whitehorn, 15-18 Amethyst
# Barrens, 19-22 Crownwater. Ssarathi takes 23-26.
#
# Registered into the toolkit's tables *at import time* rather than by editing
# `terrain.py`, which is the same build-time extension `crownkit.register` uses
# for materials and for the same reason: `build_meshes` iterates SURFACE_NAMES,
# so appending here is sufficient and leaves the shared file untouched.
SILT = 23           # the drowned basin floor
JADE_PAVING = 24    # the city's laid stone, jade flags with gilt inlay
JUNGLE = 25         # leaf litter, roots, the basin's dry ground
MOSS_STONE = 26     # ruined paving gone back to moss

TER.SURFACE_NAMES.update({
    SILT: "Silt",
    JADE_PAVING: "JadePaving",
    JUNGLE: "JungleFloor",
    MOSS_STONE: "MossStone",
})
TER.SURFACE_MATERIALS.update({
    SILT: "ssarathi_silt",
    JADE_PAVING: "ssarathi_jade_paving",
    JUNGLE: "ssarathi_jungle_floor",
    MOSS_STONE: "ssarathi_moss_stone",
})
# Paving and mossy paving are placed deliberately; the slope and shore rules in
# `assign_surface_by_rule` must not overwrite them. Silt is *not* authored: it
# is what the rule should be free to spread across the drowned floor.
TER.AUTHORED_SURFACES.update({JADE_PAVING, MOSS_STONE})
# Laid stone keeps a crisp border. Moss does not - that edge should crumble.
TER.UNDITHERED_SURFACES.add(JADE_PAVING)


# ------------------------------------------------------------ composition
# The axis is the composition. Everything is measured off it.
#
# It runs due north at design x = AXIS_X, from the south water gate up to the
# foot of the temple stair. Placing it at 20 rather than at the centre of the
# playable box is deliberate: it leaves 78 design metres of region west of the
# axis for the docks and the drowned quarter, and 114 east for the market, the
# jungle and the root-grown arch, which is the asymmetry the aerial has.
AXIS_X = 20.0

SOUTH_GATE_Z = 16.0        # the gate itself, north of the approach bridge
CAUSEWAY_SOUTH_END_Z = 40.0  # where the great causeway starts, south of it
TEMPLE_FOOT_Z = -70.0      # where it ends, at the bottom step
TEMPLE_Z = -88.0           # the ziggurat's own centre

# The arrival datum is design (0, 0) and it is not on the axis. A player
# arriving *on* the great causeway has already had the approach the concept is
# built around. Arriving on a landing quay to the south-west, with the axis a
# short walk east and the temple visible up it, is panel 1.
ARRIVAL = (0.0, 0.0)


def _w(point: tuple[float, float]) -> tuple[float, float]:
    """Design space to world metres."""
    return (point[0] * SCALE, point[1] * SCALE)


def _route(*points) -> np.ndarray:
    return np.asarray([_w(p) for p in points], dtype=np.float64)


# Named places, in design space. Converted to world once, below.
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # the axis
    "arrival_quay":     ARRIVAL,
    "south_gate":       (AXIS_X, SOUTH_GATE_Z),
    "causeway_south":   (AXIS_X, 8.0),
    "causeway_mid":     (AXIS_X, -20.0),
    "channel_bridge":   (AXIS_X, -34.0),     # panel 4
    "causeway_north":   (AXIS_X, -52.0),
    "temple_foot":      (AXIS_X, -60.0),
    "temple":           (AXIS_X, -91.0),   # panel 2
    "vault_door":       (32.0, -63.25),        # east basement court
    "temple_terrace":   (AXIS_X, -49.0),

    # the two pool courts either side of the axis
    "lily_court":       (-16.0, -30.0),       # panel 6, west
    "ritual_plaza":     (56.0, -26.0),        # panel 5, east

    # the stela on its knoll, high and alone
    "sun_stela":        (70.0, -75.0),        # panel 7

    # the overgrown broken arch out in the jungle
    "root_arch":        (78.0, 22.0),         # panel 8

    # the working edges of the city
    "market":           (73.0, 10.0),
    "east_dock":        (95.0, 4.0),
    "west_dock":        (-30.0, 14.0),
    "south_dock":       (6.0, 44.0),
    "drowned_quarter":  (-34.0, -20.0),
    "serpent_gate":     (AXIS_X, -6.0),

    # outliers that give the basin depth beyond the core
    "north_falls":      (-14.0, -112.0),
    "east_falls":       (96.0, -84.0),
    "west_shrine":      (-39.0, -54.0),
    "east_shrine":      (100.0, -44.0),
    "south_shrine":     (-8.0, 46.0),
    "far_causeway_e":   (104.0, -14.0),
    "far_causeway_w":   (-44.0, 2.0),
    "north_terrace":    (64.0, -95.0),
    "west_terrace":     (-24.0, -74.0),
}

ANCHORS: dict[str, tuple[float, float]] = {
    name: _w(point) for name, point in _DESIGN_ANCHORS.items()
}

SPAWN = ANCHORS["arrival_quay"]
SPAWN_CAUSEWAY = ANCHORS["causeway_mid"]
SPAWN_TEMPLE = ANCHORS["temple_terrace"]


def design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


# ---------------------------------------------------------- the causeways
# The great axis, and the lateral streets that cross it. These are *routes*;
# what the terrain does with them is raise a paved embankment along each one.
#
# Widths are LOCAL-scaled, not SCALE-scaled: widening the region must not widen
# the street. The great causeway is 9 world metres of deck, the laterals 6, the
# spurs 4.5 - a causeway you can walk two abreast down with a balustrade either
# side, which is what the painting shows.
# The gate sits *north* of where `channel_south` crosses the axis, not on it:
# an earlier version put the gate terrace on the crossing, and the bridge recut
# dropped the whole gate to the channel floor. Arriving over a bridge and then
# through a gate is also simply the better sequence.
GREAT_CAUSEWAY = _route((AXIS_X, CAUSEWAY_SOUTH_END_Z),
                        (AXIS_X, 8.0),
                        (AXIS_X, -20.0),
                        (AXIS_X, -34.0),
                        (AXIS_X, -52.0),
                        (AXIS_X, TEMPLE_FOOT_Z))

CAUSEWAY_WIDTH = 9.0 * LOCAL / 2.0      # half-width, world metres
LATERAL_WIDTH = 6.0 * LOCAL / 2.0
SPUR_WIDTH = 4.5 * LOCAL / 2.0

LATERALS: dict[str, np.ndarray] = {
    # west-east streets crossing the axis, at the two pool courts and the market
    "street_courts": _route((-24.0, -30.0), (AXIS_X, -28.0), (56.0, -26.0)),
    "street_market": _route((-30.0, 12.0), (AXIS_X, 6.0), (66.0, 4.0)),
    "street_north":  _route((-24.0, -74.0), (AXIS_X, -62.0), (44.0, -66.0)),
    "street_far_e":  _route((56.0, -26.0), (84.0, -18.0), (104.0, -14.0)),
    "street_far_w":  _route((-30.0, 12.0), (-40.0, 6.0), (-44.0, 2.0)),
}

SPURS: dict[str, np.ndarray] = {
    "spur_arrival":   _route(ARRIVAL, (8.0, 4.0), (AXIS_X, 8.0)),
    "spur_west_dock": _route((-30.0, 14.0), (-26.0, 8.0), (-24.0, 4.0)),
    "spur_east_dock": _route((84.0, -6.0), (76.0, -2.0), (66.0, 4.0)),
    "spur_south_dock": _route((6.0, 44.0), (6.0, 38.0), (AXIS_X, 36.0)),
    "spur_stela":     _route((56.0, -26.0), (60.0, -44.0), (62.0, -60.0)),
    "spur_drowned":   _route((-24.0, -30.0), (-30.0, -24.0), (-34.0, -20.0)),
    "spur_root_arch": _route((66.0, 4.0), (74.0, 14.0), (78.0, 22.0)),
    "spur_west_shrine": _route((-24.0, -74.0), (-38.0, -60.0), (-46.0, -54.0)),
    "spur_east_shrine": _route((104.0, -14.0), (102.0, -30.0), (100.0, -44.0)),
    "spur_south_shrine": _route((AXIS_X, 36.0), (4.0, 44.0), (-8.0, 46.0)),
    "spur_north_terrace": _route((AXIS_X, -62.0), (32.0, -80.0), (44.0, -92.0)),
}


# ------------------------------------------------------------- the water
# The carved channels. These are the deep water: navigable, bridged where a
# street crosses one, and the reason the region has arch bridges at all.
#
# Routed deliberately *between* the built platforms. An early version ran the
# main channel up the middle and cut the great causeway in half.
CHANNELS: dict[str, np.ndarray] = {
    "channel_main": _route((-58.0, 8.0), (-30.0, -10.0), (0.0, -26.0),
                           (AXIS_X, -34.0), (44.0, -40.0), (80.0, -52.0),
                           (110.0, -70.0), (130.0, -92.0)),
    "channel_south": _route((-52.0, 44.0), (-20.0, 34.0), (10.0, 28.0),
                            (40.0, 26.0), (72.0, 30.0), (104.0, 40.0)),
    "channel_east": _route((118.0, -6.0), (96.0, -14.0), (74.0, -24.0),
                           (56.0, -38.0), (44.0, -40.0)),
}

CHANNEL_WIDTH = 9.0        # design metres; scaled inside build_terrain

# Where a street crosses a channel it is a bridge, not an embankment. Those
# crossings are *computed* from the two polylines rather than written down: an
# earlier version listed them by hand, and three of the five were nowhere near
# the channel they were supposed to span - one of them re-cut the west dock to
# the channel floor. `bridge_spans()` below intersects the routes.
CROSSING_HALF_SPAN = 7.0    # design metres either side of the intersection

# Clearance from the waterline to the underside of a bridge deck. Low: these
# are ruin-city footbridges over drainage channels, not sea viaducts.
BRIDGE_CLEARANCE = 1.65


# ------------------------------------------------------------ pool courts
# The two round colonnaded courts of panels 5 and 6. Radii are LOCAL-scaled -
# a court is sized by its colonnade, not by the map.
COURTS: dict[str, dict] = {
    "lily_court": {
        "radius": 26.0 * LOCAL,
        "pool_radius": 15.0 * LOCAL,
        "pool_level": -0.85,
        "rim_level": DECK + 0.25,
    },
    "ritual_plaza": {
        "radius": 32.0 * LOCAL,
        "pool_radius": 19.0 * LOCAL,
        "pool_level": -1.05,
        "rim_level": DECK + 0.45,
    },
}


# ---------------------------------------------------------------- crossings
def _segments(points: np.ndarray):
    for i in range(len(points) - 1):
        yield points[i], points[i + 1]


def _intersect(a0, a1, b0, b1):
    """World-space intersection of two segments, or None."""
    r = a1 - a0
    s = b1 - b0
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) < 1e-9:
        return None
    d = b0 - a0
    t = (d[0] * s[1] - d[1] * s[0]) / denominator
    u = (d[0] * r[1] - d[1] * r[0]) / denominator
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return a0 + r * t, r
    return None


def street_routes() -> dict[str, np.ndarray]:
    """Every route the city walks on, keyed by name."""
    routes = {"great_causeway": GREAT_CAUSEWAY}
    routes.update(LATERALS)
    routes.update(SPURS)
    return routes


def crossings() -> list[dict]:
    """Where each street actually crosses each channel.

    Computed from the polylines. Listing them by hand is how a bridge ends up
    spanning solid fill while a dock two hundred metres away gets cut down to
    the channel floor.
    """
    out: list[dict] = []
    for street, route in street_routes().items():
        half_width = (CAUSEWAY_WIDTH if street == "great_causeway"
                      else LATERAL_WIDTH if street in LATERALS
                      else SPUR_WIDTH)
        for channel, points in CHANNELS.items():
            for a0, a1 in _segments(route):
                for b0, b1 in _segments(points):
                    hit = _intersect(a0, a1, b0, b1)
                    if hit is None:
                        continue
                    point, direction = hit
                    length = float(np.hypot(direction[0], direction[1]))
                    if length < 1e-6:
                        continue
                    heading = (float(direction[0] / length),
                               float(direction[1] / length))
                    # one bridge per street-channel pair: a street that clips a
                    # meander twice within a span length is one crossing
                    duplicate = False
                    for existing in out:
                        if existing["street"] != street:
                            continue
                        if np.hypot(existing["centre"][0] - point[0],
                                    existing["centre"][1] - point[1]) <                                 CROSSING_HALF_SPAN * SCALE * 1.6:
                            duplicate = True
                            break
                    if duplicate:
                        continue
                    out.append({
                        "name": f"{street}__{channel}",
                        "street": street,
                        "channel": channel,
                        "centre": (float(point[0]), float(point[1])),
                        "half_span": CROSSING_HALF_SPAN * SCALE,
                        "half_width": half_width,
                        "heading": heading,
                        "deck": DECK,
                    })
    out.sort(key=lambda entry: entry["name"])
    return out


# ---------------------------------------------------------------- terrain
def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.030) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.85, octaves=4,
                        seed=seed)


def _smoothstep_a(edge0, edge1, x):
    """Smoothstep with per-cell edges.

    The toolkit's `_smoothstep` takes scalar edges and guards a zero span with
    `abs(span) < 1e-9`, which is a scalar test; an embankment whose width
    wobbles per cell needs array edges. Same curve, same guard, elementwise -
    and the guard matters here for exactly the reason the production guide
    warns about: a zero or reversed span silently evaluates the mask to 1
    everywhere and lifts the whole basin.
    """
    span = np.asarray(edge1, dtype=np.float64) - np.asarray(edge0, dtype=np.float64)
    span = np.where(np.abs(span) < 1e-9, 1e-9, span)
    tt = np.clip((np.asarray(x, dtype=np.float64) - edge0) / span, 0.0, 1.0)
    return tt * tt * (3.0 - 2.0 * tt)


def _embankment(t: TER.Terrain, points: np.ndarray, half_width: float,
                level: float, seed: int, surface: int = JADE_PAVING,
                shoulder: float = 1.9) -> None:
    """Raise a retained stone embankment along a route.

    Not `grade_path`: that levels a corridor into existing ground and is right
    for a road cut through a hillside. A Ssarathi causeway is fill *added* to a
    flooded floor, so this sets an absolute level with a short battered shoulder
    dropping back into the water, which is what a retaining wall at the
    waterline looks like from above.
    """
    from amberwood.terrain import _polyline_distance

    d, _ = _polyline_distance(t.gx, t.gz, points)
    wobble = (N.fbm(t.gx * 0.10, t.gz * 0.10, seed=seed) - 0.5) * 2.0
    effective = half_width * (1.0 + 0.10 * wobble)
    # 1 inside the deck, falling to 0 across the shoulder
    blend = 1.0 - _smoothstep_a(effective, effective * shoulder, d)
    t.height = t.height * (1.0 - blend) + level * blend
    t.surface = np.where(blend > 0.62, surface, t.surface)
    t.tree_block |= d < effective * shoulder + 2.0


def build_terrain(seed: int = 20260829) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # 1. the flooded floor: a broad shallow pan, not a flat plane
    t.height += BASIN_FLOOR
    t.base_noise(0.85, 0.0125, seed=seed, octaves=5, warp=1.05)
    t.base_noise(0.34, 0.052, seed=seed + 17, octaves=4)
    t.surface[:] = SILT

    # 2. the jungle rim. The basin is closed on all four sides - it is a valley
    #    with a lake in it, not a coast - so ground rises out of the water
    #    toward every edge and keeps rising into the cliffs of step 3.
    edge = np.minimum.reduce([
        t.gx - t.x0, (t.x0 + t.size_x) - t.gx,
        t.gz - t.z0, (t.z0 + t.size_z) - t.gz])
    # Measured from the terrain boundary inward. The reach is the whole
    # water/land balance of the region and it is the number to turn: at 210 m
    # the rim reached the middle and the basin came out 80% dry, which is a
    # jungle valley with ponds in it, not the flooded city in the painting.
    # At 115 m the floor stays under water across the centre and the ground
    # only climbs in the outer fifth, which is what the aerial shows.
    RIM_REACH = 82.0
    rise = np.clip(1.0 - edge / RIM_REACH, 0.0, 1.0)
    rim_noise = region_noise(t, seed + 53, frequency=0.019)
    t.height += (rise ** 2.0) * 30.0 * (0.72 + 0.56 * rim_noise)

    # dry jungle ground wherever the rim has come out of the water
    dry = t.height > WATER_LEVEL + 0.25
    t.surface = np.where(dry, JUNGLE, t.surface)

    # 3. the valley walls. Amberwood walls three sides and leaves the sea open;
    #    Crownwater walls none and closes with the collision grid. Ssarathi is a
    #    sunken basin, so all four sides are closed by rock - and the north wall
    #    is the tallest, because the waterfalls of panels 2 and 9 come off it.
    t.clamp_edges(MARGIN + 24.0, 32.0)
    t.clamp_edges(MARGIN + 42.0, 26.0, sides=("north",))

    # 4. the navigable channels, cut into the floor before anything is built on
    #    top of it
    for name, points in CHANNELS.items():
        t.carve_channel(points, CHANNEL_WIDTH * SCALE * 0.5,
                        abs(CHANNEL_FLOOR - BASIN_FLOOR), bank=2.1,
                        seed=seed + N.stable_hash(name) % 97)

    # 5. the waterfall shelves. Two notches in the north wall where water comes
    #    down into the basin, plus the pools they land in.
    for name, anchor, radius, depth in (
            ("north_falls", ANCHORS["north_falls"], 34.0 * LOCAL, 2.4),
            ("east_falls", ANCHORS["east_falls"], 26.0 * LOCAL, 1.9)):
        t.add_dome(anchor, radius * 2.4, -depth, power=1.5,
                   noise_seed=seed + N.stable_hash(name) % 61, noise_amount=0.18)

    t.erode(iterations=9, strength=0.22)
    t.smooth(iterations=2, weight=0.30)
    return t


def apply_built_ground(t: TER.Terrain, seed: int = 20260829) -> None:
    """The city: causeways, plazas, the temple's tiers and the pool courts.

    Runs after `build_terrain`, so every level it sets is absolute and nothing
    depends on where the noise happened to land - which is what keeps a plaza
    from hovering when the basin seed changes.
    """
    # --- the great axis and its streets ---------------------------------
    _embankment(t, GREAT_CAUSEWAY, CAUSEWAY_WIDTH, DECK, seed + 11)
    for name, points in LATERALS.items():
        _embankment(t, points, LATERAL_WIDTH, DECK,
                    seed + N.stable_hash(name) % 131)
    for name, points in SPURS.items():
        _embankment(t, points, SPUR_WIDTH, DECK,
                    seed + N.stable_hash(name) % 149)

    # --- the arrival quay ------------------------------------------------
    # Absolute, and a touch lower than the causeway so stepping up onto the
    # axis is a step the player feels.
    t.rect_terrace(ANCHORS["arrival_quay"], 13.0 * LOCAL, 9.0 * LOCAL,
                   DECK - 0.35, 0.0, JADE_PAVING)

    # --- the south water gate -------------------------------------------
    t.terrace(ANCHORS["south_gate"], 15.0 * LOCAL, DECK + 0.30,
              surface=JADE_PAVING)
    t.terrace(ANCHORS["serpent_gate"], 12.0 * LOCAL, DECK + 0.15,
              surface=JADE_PAVING)

    # --- the pool courts of panels 5 and 6 -------------------------------
    for name, court in COURTS.items():
        centre = ANCHORS[name]
        # the ring of paving first
        t.terrace(centre, court["radius"], court["rim_level"],
                  surface=JADE_PAVING)
        # then the pool sunk into the middle of it. Shallow and clear: the
        # point of both panels is that you see the tiled floor and the lilies
        # through the water, not that you see water.
        t.terrace(centre, court["pool_radius"], court["pool_level"],
                  surface=MOSS_STONE)

    # --- the drowned quarter --------------------------------------------
    # Paving that is under the water rather than out of it: the concept's
    # sunken lower town, read as kerbs and floor patterns beneath the surface.
    t.terrace(ANCHORS["drowned_quarter"], 30.0 * LOCAL, DROWNED_STEP,
              surface=MOSS_STONE)
    for i, offset in enumerate(((-14.0, -8.0), (10.0, -12.0), (-6.0, 12.0),
                                (16.0, 6.0))):
        centre = (ANCHORS["drowned_quarter"][0] + offset[0] * LOCAL * 2.0,
                  ANCHORS["drowned_quarter"][1] + offset[1] * LOCAL * 2.0)
        t.rect_terrace(centre, 7.0 * LOCAL, 6.0 * LOCAL,
                       DROWNED_STEP - 0.18 * (i % 3), 0.0, MOSS_STONE)

    # --- the market and the docks ---------------------------------------
    t.terrace(ANCHORS["market"], 18.0 * LOCAL, DECK + 0.10, surface=JADE_PAVING)
    for dock in ("east_dock", "west_dock", "south_dock"):
        t.rect_terrace(ANCHORS[dock], 10.0 * LOCAL, 7.0 * LOCAL,
                       DECK - 0.55, 0.0, MOSS_STONE)

    # --- the shrines and far terraces ------------------------------------
    for name, radius in (("west_shrine", 11.0), ("east_shrine", 11.0),
                         ("south_shrine", 10.0), ("far_causeway_e", 9.0),
                         ("far_causeway_w", 9.0), ("west_terrace", 13.0),
                         ("north_terrace", 15.0)):
        level = max(float(t.height_at(*ANCHORS[name])), DECK)
        t.terrace(ANCHORS[name], radius * LOCAL, level, surface=JADE_PAVING)

    # --- the stela knoll of panel 7 --------------------------------------
    # A rock knoll lifted out of the basin, not a building: panel 7 puts the
    # stela high and alone with the city small behind it.
    t.plateau(ANCHORS["sun_stela"], 20.0 * LOCAL, STELA_KNOLL, edge=30.0,
              surface=TER.ROCK, seed=seed + 71, irregular=0.22)
    t.terrace(ANCHORS["sun_stela"], 9.0 * LOCAL, STELA_KNOLL + 0.4,
              surface=JADE_PAVING)

    # --- the root-grown arch of panel 8 ----------------------------------
    # Dry ground in the jungle, raised clear of the water so the rubble field
    # and the roots read against earth rather than against a pond.
    t.plateau(ANCHORS["root_arch"], 22.0 * LOCAL, DECK + 1.9, edge=22.0,
              surface=JUNGLE, seed=seed + 83, irregular=0.30)

    # --- the temple precinct, panels 2 and 3 -----------------------------
    # The one place the region goes vertical. Three concentric tiers, each a
    # hard terrace so the ziggurat reads as built steps rather than a hill,
    # with the stair corridor cut down the axis by populate.py.
    # Radii are LOCAL-scaled, so the precinct keeps its own size when the
    # region's extent changes. The first version used 74/52/34 * LOCAL - a
    # 222 m-wide temple that reached across a third of the basin and swallowed
    # the north waterfall. In the aerial the complex is about a fifth of the
    # frame, which is 115 m across at this extent.
    #
    # The edges are deliberately short. A wide edge makes a smooth cone that is
    # walkable everywhere and reads as a hill; a ziggurat needs a step you can
    # see, so the faces are steep and the axis ramps below are what actually
    # carry the player up.
    temple = ANCHORS["temple"]
    t.plateau(temple, 88.0, TIER_1, edge=8.0, surface=JADE_PAVING,
              seed=seed + 97, irregular=0.09)
    t.plateau(temple, 68.0, TIER_2, edge=7.0, surface=JADE_PAVING,
              seed=seed + 101, irregular=0.06)
    t.plateau(temple, 50.0, TIER_3, edge=6.0, surface=JADE_PAVING,
              seed=seed + 103, irregular=0.04)

    # the terrace at the foot of the stair, where the causeway arrives
    t.rect_terrace(ANCHORS["temple_terrace"], 20.0 * LOCAL, 11.0 * LOCAL,
                   DECK + 0.40, 0.0, JADE_PAVING)
    # a wider apron between the terrace and the first ramp, so the approach does
    # not narrow to the causeway's width right where the precinct opens out
    t.rect_terrace((ANCHORS["temple_terrace"][0], ANCHORS["temple_terrace"][1] - 26.0),
                   26.0 * LOCAL, 13.0 * LOCAL, DECK + 0.40, 0.0, JADE_PAVING)
    # the vault-door forecourt of panel 3: a flat landing cut into the tier-2
    # face, which the second ramp arrives on and the third leaves from
    t.rect_terrace(ANCHORS["vault_door"], 14.0 * LOCAL, 9.0 * LOCAL,
                   TIER_2, 0.0, JADE_PAVING)

    # --- ramps ------------------------------------------------------------
    # The tiers must be climbable, or the temple is scenery. A graded ramp up
    # the axis on each tier boundary, wide enough to walk and shallow enough to
    # stay under the walk-slope limit. Stair geometry sits on top of these in
    # populate.py; the ramp is what actually carries the player.
    # Surveyed processional ascent. Preserve the 72m temple and its vault
    # relationship; shorter streets must not shorten the actual stair clearances.
    from amberwood import routecraft as RC
    surveys = [
        ([(40,-126),(16,-130),(9,-149),(24,-149),(40,-145)],[13,13,21,21,21],5.5),
        ([(40,-126),(64,-130),(71,-149),(56,-149),(40,-145)],[13,13,21,21,21],5.5),
        ([(120,-114),(138,-126),(152,-142),(140,-150)],[2.2,6,10.5,13.9],6.0),
        # Reapply the main ascent after the side landing feathers.
        ([(40,-80),(40,-94),(40,-107),(40,-118)],[2.2,8,14,21],10.0),
    ]
    for points,heights,width in surveys:
        RC.grade_road(t,points,heights,width=width,shoulder=3,
                      surface=JADE_PAVING,clearance=3)

    # --- protect the plateaus ----------------------------------------------
    # `terrace` and `rect_terrace` mark their footprint in `tree_block`;
    # `plateau` does not. The massing pass tests that mask to decide where it
    # may build, so without this the temple precinct, the stela knoll and the
    # root-arch mound are all fair game - and a ruin block duly landed on the
    # temple summit and dropped it from 16.2 m to -0.84 m.
    t.mark_blocked_disc(ANCHORS["temple"], 104.0)
    # 60 m, not 36: at 36 the clearance stopped trees standing *at* the
    # panel-7 camera but not their canopies, which spread nine metres and put a
    # leaf card on the lens.
    t.mark_blocked_disc(ANCHORS["sun_stela"], 60.0)
    t.mark_blocked_disc(ANCHORS["root_arch"], 26.0 * LOCAL)
    for name in ("north_falls", "east_falls"):
        t.mark_blocked_disc(ANCHORS[name], 34.0 * LOCAL)

    # --- the quarters between the streets ----------------------------------
    # After the streets and plazas, so `tree_block` already records what they
    # claimed and nothing lands on a causeway; before the bridge recuts, so a
    # block that strayed over a channel is opened back up with it.
    _quarters(t, seed)

    # --- bridge landings ---------------------------------------------------
    # Where a street crosses a channel the embankment above has already filled
    # the channel in. Re-cut it, so the span has water under it again.
    for span in crossings():
        _recut_crossing(t, span["centre"], span["half_span"])

    _classify_surfaces(t, seed)
    t.dither_boundaries(seed=seed + 5, amount=0.45)


def _classify_surfaces(t: TER.Terrain, seed: int) -> None:
    """Ssarathi's own ground rule, in place of `assign_surface_by_rule`.

    The toolkit's rule ends with an unconditional
    `surface = where(height < sea_level - 1.0, SHORE, surface)`, with no
    authored-class guard on that last line. In a region whose *subject* is
    drowned paving that is exactly wrong: it turned the ritual plaza's pool
    floor and the whole drowned quarter into beach shingle. A flooded basin
    needs a rule of its own, and writing it here rather than adding a fifth
    branch to the shared one is what the region file is for.

    The rule, in order of precedence:
      1. anything authored as laid stone stays laid stone;
      2. steep ground is rock, wherever it is;
      3. ground under water is silt;
      4. ground just above the waterline is a muddy fringe;
      5. everything else dry is jungle floor.
    """
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)
    authored = np.isin(t.surface, sorted(TER.AUTHORED_SURFACES))

    surface = t.surface.copy()
    dry = t.height > WATER_LEVEL
    surface = np.where(dry & ~authored, JUNGLE, surface)
    surface = np.where(~dry & ~authored, SILT, surface)

    # the fringe: a broken band of mud and moss where the water meets the land,
    # noise-broken so it does not read as a contour line
    fringe_noise = N.fbm(t.gx * 0.16, t.gz * 0.16, seed=seed + 4242)
    fringe = (t.height > WATER_LEVEL - 0.55) & (t.height < WATER_LEVEL + 0.85)
    surface = np.where(fringe & ~authored & (fringe_noise > 0.42),
                       MOSS_STONE, surface)

    # Rock wins over everything except laid stone - but the threshold is high.
    # At 0.95 the whole valley wall classified as rock, the vegetation pass
    # skipped it, and the region's horizon was a ring of bare brown dirt above
    # the tree line. This is a rainforest basin: only a genuine cliff face is
    # bare, and the jungle climbs everything short of one.
    surface = np.where((slope > 1.45) & ~authored, TER.ROCK, surface)
    t.surface = surface


# --------------------------------------------------------------- massing
# The quarters between the streets.
#
# The first build had a correct street plan standing in an empty lake: about
# half the basin was open water and almost none of it had anything in it. The
# aerial is the opposite - the water in the painting is *interstitial*, the
# gaps between dense masses of ruined building and tree-covered ground, and
# reading it as "a lake with causeways on it" gets the region backwards.
#
# So the basin is filled: ruin blocks in the built quarters near the axis, and
# jungle islets further out. Both are terrain, which means they also give the
# vegetation pass ground to plant on - with only the outer rim above water,
# every tree in the region was stuck in a border band.
RUIN_REACH = 210.0        # design metres from the city centre
ISLET_REACH = 320.0

CITY_CENTRE = (AXIS_X + 8.0, -26.0)

RUIN_BLOCKS: list[dict] = []
"""Every standing block the massing pass raised, in world metres.

Recorded rather than recomputed: `populate.py` puts ruined building geometry on
these, and a second pass that re-rolled the same RNG would put walls where there
is no platform. Same reason `ISLAND_GEOM` exists in Crownwater.
"""


def _footprint_blocked(t: TER.Terrain, px: float, pz: float,
                       half_x: float, half_z: float, rotation: float) -> bool:
    """True if any part of an oriented rectangle lands on claimed ground."""
    c, s = math.cos(rotation), math.sin(rotation)
    for u in (-0.92, -0.46, 0.0, 0.46, 0.92):
        for v in (-0.92, -0.46, 0.0, 0.46, 0.92):
            lx, lz = u * half_x, v * half_z
            wx = px + lx * c - lz * s
            wz = pz + lx * s + lz * c
            if bool(t.blocked_at(wx, wz)):
                return True
    return False


def _quarters(t: TER.Terrain, seed: int) -> None:
    """Ruin blocks and jungle islets filling the basin between the streets."""
    rng = N.Rng(seed + 909)
    RUIN_BLOCKS.clear()

    # 1. ruin blocks: rectangular masses on a jittered grid, skipping anything
    #    already claimed. `tree_block` is the record of what the street and
    #    plaza passes claimed, so it is the correct thing to test - hand-listing
    #    exclusion zones would go stale the moment a street moved.
    step = 11.0
    reach = RUIN_REACH
    cx, cz = _w(CITY_CENTRE)
    x = cx - reach * SCALE / 2.6
    while x < cx + reach * SCALE / 2.6:
        z = cz - reach * SCALE / 2.6
        while z < cz + reach * SCALE / 2.6:
            px = x + float(rng.uniform(-step * 0.45, step * 0.45))
            pz = z + float(rng.uniform(-step * 0.45, step * 0.45))
            z += step
            distance = math.hypot(px - cx, pz - cz)
            if distance > reach * SCALE / 2.4:
                continue
            # density falls off from the centre: the city thins toward the rim
            if float(rng.uniform(0.0, 1.0)) > 1.10 - 0.75 * distance / (reach * SCALE / 2.2):
                continue
            # Smaller than the first pass's 5-13. The footprint test below
            # rejects any block overlapping claimed ground, and a 19 m block
            # between 27 m streets almost always overlaps something - the
            # quarters came out at twenty-one buildings for the whole city.
            # Smaller blocks on a tighter grid fit, and the concept's buildings
            # are individually modest anyway; its density is in their number.
            half_x = float(rng.uniform(3.2, 8.5)) * LOCAL
            half_z = float(rng.uniform(3.2, 8.5)) * LOCAL
            rotation = float(rng.uniform(-0.35, 0.35))
            roll = float(rng.uniform(0.0, 1.0))
            if roll < 0.58:
                # a standing block, out of the water and walkable
                level = DECK + float(rng.uniform(-0.35, 1.30))
                surface = MOSS_STONE if roll < 0.26 else JADE_PAVING
            elif roll < 0.84:
                # a drowned floor: paving visible through the water
                level = DROWNED_STEP + float(rng.uniform(-0.35, 0.20))
                surface = MOSS_STONE
            else:
                # a low mound gone back to jungle
                level = DECK + float(rng.uniform(0.4, 2.4))
                surface = JUNGLE
            # Test the block's whole footprint against the street mask, not
            # just its centre. `blocked_at` on the centre alone let a 19 m
            # block sit 15 m off the axis and overrun the causeway by four
            # metres - which showed up as a wall standing in the middle of the
            # panel-1 shot, and would have been a wall standing in the middle
            # of the road for a player.
            if _footprint_blocked(t, px, pz, half_x, half_z, rotation):
                continue
            t.rect_terrace((px, pz), half_x, half_z, level, rotation, surface)
            if surface != JUNGLE and level > WATER_LEVEL + 0.4:
                RUIN_BLOCKS.append({
                    "centre": (float(px), float(pz)),
                    "half_x": float(half_x), "half_z": float(half_z),
                    "level": float(level), "rotation": float(rotation),
                    "paved": surface == JADE_PAVING,
                })
        x += step

    # 2. jungle islets: rounded rises across the whole basin, denser toward the
    #    rim. These are what carries the canopy out over the water and stops
    #    the middle distance reading as an empty lake.
    step = 34.0
    x = t.x0 + 40.0
    while x < t.x0 + t.size_x - 40.0:
        z = t.z0 + 40.0
        while z < t.z0 + t.size_z - 40.0:
            px = x + float(rng.uniform(-step * 0.45, step * 0.45))
            pz = z + float(rng.uniform(-step * 0.45, step * 0.45))
            z += step
            if bool(t.blocked_at(px, pz)):
                continue
            if t.height_at(px, pz) > WATER_LEVEL + 0.4:
                continue                       # already land
            distance = math.hypot(px - cx, pz - cz)
            # rarer in the ceremonial heart, common out in the basin
            chance = 0.16 + 0.52 * min(distance / (ISLET_REACH * SCALE / 2.2), 1.0)
            if float(rng.uniform(0.0, 1.0)) > chance:
                continue
            radius = float(rng.uniform(9.0, 26.0)) * LOCAL
            rise = float(rng.uniform(1.4, 5.6))
            t.add_dome((px, pz), radius, rise + abs(BASIN_FLOOR), power=1.55,
                       noise_seed=seed + int(px) % 401, noise_amount=0.26)
        x += step


def _ramp(t: TER.Terrain, a: tuple[float, float], b: tuple[float, float],
          level_a: float, level_b: float, half_width: float) -> None:
    """Grade a straight climb between two levels, in design coordinates."""
    points = _route(a, b)
    heights = np.linspace(level_a, level_b, 24)
    t.grade_path(points, half_width * LOCAL, heights=heights, shoulder=1.7,
                 surface=JADE_PAVING, flatten=1.0)


def _recut_crossing(t: TER.Terrain, centre: tuple[float, float],
                    half_span: float) -> None:
    """Open water back up under a bridge span.

    The embankment pass runs along whole routes and does not know where a
    channel is; without this the 'bridges' would span solid fill. Cutting after
    the fill, rather than skipping the fill, keeps the two operations
    independent - the routes do not need to know about the channels, and moving
    a channel does not mean re-cutting a causeway by hand.
    """
    cx, cz = centre
    span = half_span
    d = np.hypot(t.gx - cx, t.gz - cz)
    cut = 1.0 - _smoothstep_a(span * 0.55, span, d)
    t.height = t.height * (1.0 - cut) + CHANNEL_FLOOR * cut
    t.surface = np.where(cut > 0.6, SILT, t.surface)


def bridge_spans() -> list[dict]:
    """The authored spans, in world metres.

    Thin wrapper over `crossings()` so the population pass and the collision
    pass read the same numbers the terrain was actually cut from, and a moved
    channel moves the bridge with it.
    """
    return crossings()


def water_extent() -> tuple[float, float, float, float]:
    """The rectangle the basin's water surface is drawn over."""
    return (TERRAIN_X0, TERRAIN_Z0,
            TERRAIN_X0 + TERRAIN_SIZE_X, TERRAIN_Z0 + TERRAIN_SIZE_Z)
