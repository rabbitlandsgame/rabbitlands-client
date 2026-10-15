"""The authored 396m Westhaven region plan.

Coordinates are Godot metres, Y up and north toward -Z. One metre equals one
server tile, with origin (120,172), so world_x=tile_x-120 and world_z=172-tile_y.
The main arrival is world (34,3.4,6), tile (154,166).

Native harbour architecture and the continuous sea floor are retained. The
explicit compact anchors, roads, service and habitat plans are applied from
landscape_plan.configure; layout.prepare builds the connected terrain before
population. Historical concept-space constants below remain inputs for retained
architecture and are overridden where the compact composition needs new ground.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER
from amberwood import routecraft as RC

# `Placement` and `RegionBuild` are the toolkit's shared build containers, not
# anything Amberwood-specific, and every region needs them. Re-exported here so
# this module is the whole namespace a Westhaven build script has to import.
from amberwood.region import Placement, RegionBuild  # noqa: F401

# ---------------------------------------------------------------- extents
# The arrival datum is at server (174, 250), not the (174, 174) the five
# finished regions share. That is a deliberate departure and the reason is the
# concept: Westhaven is 40% water, and (174, 174) puts only 30% of the map south
# of the spawn. A harbour city whose spawn is on the quay cannot then have more
# sea than that, so the harbour, both lighthouse rocks and the open water all
# get squeezed into a third of the frame while the upland gets more room than
# the painting gives it.
#
# Moving the datum 76 cells south makes the painting map 1:1 onto the playable
# square on *both* axes - its west and east edges are the playable west and east
# edges, its top edge is z = -325 and its bottom edge is z = +250 - so nothing
# has to be invented past the concept and nothing has to be trimmed out of it.
# `serverOrigin` is manifest data, read by `coordinate_adapter.gd`, and the
# server's `ARRIVAL_TILES` is a per-region table, so this costs one entry on
# each side and no code.
SERVER_ORIGIN = (120.0, 172.0)
SERVER_CELLS = 396
METRES_PER_TILE = 1.0

# The composition is written in a 192 m design space and scaled up here, so the
# aerial's layout is preserved rather than stretched. Same convention and same
# constant as Crownwater, for the same reason: one number changes the extent.
SCALE = 2.0625

# Distances between places scale with the region; the places themselves do not.
# A quay is sized by the ships along it and a market square by the stalls in it,
# so anything sized by its contents is measured in LOCAL, not SCALE.
LOCAL = 1.5

PLAY_MIN_X = -SERVER_ORIGIN[0] * METRES_PER_TILE
PLAY_MAX_X = (SERVER_CELLS - 1 - SERVER_ORIGIN[0]) * METRES_PER_TILE
PLAY_MIN_Z = -(SERVER_CELLS - 1 - SERVER_ORIGIN[1]) * METRES_PER_TILE
PLAY_MAX_Z = SERVER_ORIGIN[1] * METRES_PER_TILE

MARGIN = 48.0
TERRAIN_X0 = PLAY_MIN_X - MARGIN
TERRAIN_Z0 = PLAY_MIN_Z - MARGIN
TERRAIN_SIZE_X = (PLAY_MAX_X - PLAY_MIN_X) + MARGIN * 2.0
TERRAIN_SIZE_Z = (PLAY_MAX_Z - PLAY_MIN_Z) + MARGIN * 2.0

SEA_LEVEL = 0.0
TERRAIN_CELL = 2.0

# ------------------------------------------------------- surface language
# Westhaven's ground is a port's ground: granite setts on the quays and streets,
# tide-washed shingle at the water line, salt turf on the headland, and bare
# sea rock on the cliffs and the two lighthouse masses. The surface-class table
# is shared by every region, so this repoints its own entries at build time
# rather than editing the toolkit - the same reason `havenkit.register` extends
# the material table in memory instead of appending to `materials.SPECS`.
TER.SURFACE_MATERIALS[TER.PAVING] = "westhaven_sett"
TER.SURFACE_MATERIALS[TER.PATH] = "westhaven_track"
TER.SURFACE_MATERIALS[TER.SHORE] = "westhaven_tide_shingle"
TER.SURFACE_MATERIALS[TER.MEADOW] = "westhaven_dry_pasture"
TER.SURFACE_MATERIALS[TER.FOREST] = "westhaven_salt_turf"
TER.SURFACE_MATERIALS[TER.ROCK] = "westhaven_sea_rock"

# PATH is Westhaven's country cart track - the upland roads and the shore track
# round the east bay. It used to be pointed at the pier decking, which planked
# every road on the map like a ship's deck; the one place decking on the ground
# was right is the shipyard slipway, and that is authored as PAVING now. A track
# is worn, not laid, so it is left out of UNDITHERED_SURFACES and its edge gets
# to break up like the ground it is worn into.

# --------------------------------------------------------------- levels
# The five terrace bands of the city, plus the water and the outworks. Authored
# absolutely rather than derived, because the whole point of the composition is
# that the bands are at *known* heights with retaining walls between them: read
# from noise they drift, and the skyline stops reading as a staircase.
LEVEL = {
    "sea_floor": -17.0,     # open sea, south and west
    "harbour_floor": -7.5,  # inside the mole: dredged, not deep
    "slip": -3.2,           # the shipyard slipway's underwater end
    "quay": 3.4,            # the working waterfront - one deck, whole harbour
    "lower_town": 8.4,      # fish market, warehouses, the first street back
    "mid_town": 14.0,       # the main east-west street and its arcades
    "upper_town": 21.0,     # the dense roofs of the painting's middle band
    "citadel": 28.0,        # cathedral precinct and the campanile's footing
    "crown": 36.0,          # the highest civic terrace, the brass dome
    "headland": 78.0,       # the north-west cliff mass
    "upland": 34.0,         # the open country north and east of the city
    "ridge": 88.0,          # the northern and eastern world boundary
    "mole": 5.2,            # the harbour mole's deck
    "gull_isle": 31.0,      # the south-west island's crown
    "lamp_rock": 24.0,      # the south-east lighthouse mass
}


# ------------------------------------------------------------ composition
def cell(u: float, v: float) -> tuple[float, float]:
    """A point on the aerial's 8x8 reading grid, in design space.

    `u` runs west to east across the painting, `v` north to south. The offsets
    put design (0, 0) - and therefore the Godot origin and the server arrival
    datum - on the quayside street at the head of the main quay, which is where
    the painting's own centre of gravity is.

    The constants are what make the mapping 1:1. 24 design metres per reading
    cell at SCALE 3 is 72 world metres, so the painting's eight cells are 576 m,
    exactly the playable extent. -58.0 puts u = 0 on x = -174 and u = 8 on
    x = 402; -108.24 puts v = 0 on z = -325 and v = 7.98 on z = +250. The
    painting's four edges are the map's four edges.
    """
    return (u * 24.0 - 58.0, v * 24.0 - 108.24)


def _design_to_world(point: tuple[float, float]) -> tuple[float, float]:
    return (point[0] * SCALE, point[1] * SCALE)


# The coastline, read straight off the painting. This is the single most
# load-bearing piece of data in the region: it decides what is land, and every
# terrace, road and quay is placed relative to it.
#
# Runs clockwise from beyond the north-west corner, south along the west cliff,
# east along the working waterfront, round the east bay, and north up the east
# shore, closing across the top. Points outside the playable square on purpose:
# the land has to continue past the border, not stop at it.
_COAST_CELLS = [
    (-1.4, -1.8), (-1.4, 0.42), (-0.95, 0.86), (-0.42, 1.24),
    (-0.10, 1.72), (0.02, 2.28), (0.20, 2.86), (0.48, 3.28),
    (0.62, 3.70),
    # the working waterfront: nearly straight, because it is built, not eroded
    (0.94, 4.04), (1.18, 4.40), (1.72, 4.60), (2.32, 4.65),
    (2.96, 4.67), (3.56, 4.69), (4.16, 4.71), (4.72, 4.69),
    (5.22, 4.63), (5.64, 4.54),
    # the shipyard point, then the east bay bites back into the land
    (5.98, 4.62), (6.22, 4.92), (6.58, 5.06), (6.98, 5.02),
    (7.32, 4.80), (7.64, 4.46), (7.98, 4.22),
    (8.9, 4.05), (8.9, -1.8),
]

# The two rock masses out in the water. Gullstone is a true island; Lamp Rock is
# joined to the east shore by a neck the surf breaks over, which is how the
# painting has it - it reads as an islet from the harbour, which is panel 2's
# framing, and it is walkable, which is what makes the lighthouse a place a
# player can actually go rather than scenery.
_GULLSTONE_CELLS = [
    (0.62, 5.42), (1.30, 5.30), (2.10, 5.46), (2.78, 5.86),
    (3.32, 6.34), (3.28, 6.92), (2.72, 7.34), (1.94, 7.46),
    (1.20, 7.28), (0.72, 6.86), (0.48, 6.24), (0.50, 5.72),
]
_LAMP_ROCK_CELLS = [
    (5.30, 5.94), (5.96, 5.66), (6.64, 5.52), (7.28, 5.66),
    (7.72, 6.06), (7.86, 6.62), (7.62, 7.16), (7.06, 7.46),
    (6.36, 7.44), (5.76, 7.10), (5.36, 6.58),
]
# The neck. Two cells wide at design scale, awash at high water.
_LAMP_NECK = [(7.62, 5.72), (7.90, 4.90)]

# The city's own footprint, as distinct from the mainland. A wedge: broad along
# the water and narrowing as it climbs, which is what the painting shows and
# what a port hemmed in by its own hillside actually looks like. The terrace
# staircase is cut inside this and nowhere else - applied to the whole mainland
# it banded the open upland into contour stripes twenty kilometres wide.
_CITY_CELLS = [
    (0.16, 4.66), (0.72, 4.68), (1.60, 4.66), (2.60, 4.66), (3.60, 4.68),
    (4.60, 4.66), (5.36, 4.60), (5.72, 4.30), (5.42, 3.72), (5.06, 3.04),
    (4.78, 2.30), (4.62, 1.52), (4.16, 0.96), (3.22, 0.78), (2.28, 0.94),
    (1.46, 1.42), (0.78, 2.20), (0.34, 3.16), (0.14, 4.00),
]


def _poly(cells) -> np.ndarray:
    """Reading-grid cells to a world-metre polygon.

    Scaled here, not at the point of use: the masks are tested against the
    terrain grid, which is in world metres, and a polygon left in design space
    silently shrinks the whole region to a sixth of its area without erroring.
    """
    return np.asarray([_design_to_world(cell(u, v)) for u, v in cells],
                      dtype=np.float64)


COAST = _poly(_COAST_CELLS)
GULLSTONE = _poly(_GULLSTONE_CELLS)
LAMP_ROCK = _poly(_LAMP_ROCK_CELLS)
CITY = _poly(_CITY_CELLS)


# ------------------------------------------------------------- anchors
# Named places, in the painting's grid coordinates. Every one of them is a thing
# visible in the aerial or the subject of a detail-board panel; the comment says
# which, so a later pass can check the map against the board rather than against
# somebody's memory of it.
_ANCHOR_CELLS: dict[str, tuple[float, float]] = {
    # --- the waterfront, west to east (panels 3, 4, 5, 6, 7, 10)
    "harbour_gate": (0.98, 4.02),      # panel 1: the arched span over the west inlet
    # On the quay, at 3.40 m. This anchor was at (0.72, 4.28) from the first
    # build and had been sitting in sixteen metres of water the whole time -
    # the coast at that v runs through u = 1.11, and everything west of it is
    # sea. Nothing caught it until the walkable-cell check was added, and even
    # then the nudge quietly relocated the berth portal 16 m each build rather
    # than reporting the anchor as wrong. Probed against the built terrain
    # rather than guessed a second time.
    "west_quay": (1.34, 4.34),         # aerial D0/E0: the big moored ship
    "custom_house": (1.42, 4.34),
    "fish_market": (2.34, 4.42),       # panel 7: stalls under awnings
    "market_stair": (2.30, 4.18),      # panel 3: the cobbled street and its arch
    "quay_arch": (2.06, 4.24),         # panel 3's arch, at the street's foot
    "main_quay": (2.90, 4.60),         # the arrival datum sits here
    "cargo_pier": (3.62, 4.86),        # panel 4: ship alongside, gantry
    "crane_pier": (4.34, 4.88),        # panel 5: the timber cargo crane
    "chandlery": (4.06, 4.50),         # panel 10: the dockside still-life
    "shipyard": (5.34, 4.66),          # panel 6: a hull on the stocks
    "shipyard_slip": (5.46, 4.94),
    "ropewalk": (5.02, 4.44),
    # --- the mole and its bastion (panel 8)
    "mole_root": (1.06, 4.62),
    "mole_bastion": (1.62, 5.02),      # panel 8: banner, surf on the outer face
    "mole_head": (4.62, 5.18),
    "harbour_mouth": (5.08, 5.10),
    # --- the city, climbing north (panel 9)
    "warehouse_row": (1.86, 4.02),
    "lower_square": (2.72, 4.02),
    "guild_hall": (3.42, 3.94),
    "city_gate": (2.32, 3.42),         # aerial D2: the big arched gate
    "mid_street": (3.10, 3.30),
    "arcade": (2.62, 2.46),            # aerial C2/C3: the long arcaded terrace
    "cathedral": (3.24, 2.62),         # aerial C3: the citadel mass
    "campanile": (2.30, 1.62),         # aerial B2: the dark bell tower
    "high_spire": (4.20, 2.40),        # aerial C4: the tall pale spire
    "brass_dome": (3.52, 1.82),        # panel 9: the terrace and its brass dome
    "crown_terrace": (3.30, 1.52),     # panel 9's viewpoint
    "north_gate": (4.34, 1.66),
    # --- the upland, north and east
    "upland_chapel": (6.28, 0.58),     # aerial A6: the small roadside chapel
    "upland_farm": (5.42, 0.96),
    "hill_estate": (7.18, 3.58),       # aerial D7: the villa on the hillside
    "east_watch": (6.86, 2.34),
    "crossroads": (5.58, 2.62),
    "east_bay_beach": (6.72, 4.92),
    # --- the water
    "gullstone": (1.86, 6.34),         # the south-west island's crown
    "gullstone_watch": (1.34, 5.94),   # aerial F1: its tower
    "gullstone_arch": (2.96, 6.42),    # aerial G3: the sea arch
    "lamp_rock": (6.58, 6.44),
    "lighthouse": (6.62, 6.18),        # panel 2: the great lighthouse
    # The yard beside the tower, not the tower itself. A spawn or an
    # interactive placed on the lighthouse anchor lands under the tower's own
    # gallery - which is a walk surface 28 m up - and the client's grounding ray
    # snaps the actor onto the gallery instead of the rock.
    "lighthouse_yard": (6.52, 6.18),
    "farm_door": (5.42, 1.10),
    "estate_door": (7.00, 3.68),
    "watch_door": (6.86, 2.49),
}

ANCHORS: dict[str, tuple[float, float]] = {
    name: _design_to_world(cell(u, v)) for name, (u, v) in _ANCHOR_CELLS.items()
}

SPAWN = ANCHORS["main_quay"]
SPAWN_MARKET = ANCHORS["fish_market"]
SPAWN_CROWN = ANCHORS["crown_terrace"]
SPAWN_LIGHTHOUSE = ANCHORS["lighthouse_yard"]


def _route(*names) -> np.ndarray:
    """A polyline through named anchors, in world metres."""
    return np.asarray([ANCHORS[n] for n in names], dtype=np.float64)


def _route_cells(*cells) -> np.ndarray:
    return np.asarray([_design_to_world(cell(u, v)) for u, v in cells],
                      dtype=np.float64)


# ---------------------------------------------------------------- routes
# The street network. `QUAYSIDE` is the one continuous level run in the region
# and the spine everything else hangs off; the climbs are the ramp streets that
# connect one terrace band to the next. Their heights are given explicitly so
# each one lands exactly on its terrace instead of wherever the noise put it.
QUAYSIDE = _route("harbour_gate", "custom_house", "main_quay", "chandlery",
                  "ropewalk", "shipyard")
QUAYSIDE_HEIGHTS = [LEVEL["quay"]] * 6

MARKET_CLIMB = _route("main_quay", "quay_arch", "market_stair", "lower_square")
MARKET_CLIMB_HEIGHTS = [LEVEL["quay"], LEVEL["quay"] + 2.2,
                        LEVEL["lower_town"] - 1.0, LEVEL["lower_town"]]

GATE_CLIMB = _route("lower_square", "city_gate", "mid_street")
GATE_CLIMB_HEIGHTS = [LEVEL["lower_town"], LEVEL["mid_town"] - 3.0,
                      LEVEL["mid_town"]]

ARCADE_WALK = _route("mid_street", "arcade", "cathedral")
ARCADE_WALK_HEIGHTS = [LEVEL["mid_town"], LEVEL["upper_town"],
                       LEVEL["citadel"] - 2.0]

CROWN_CLIMB = _route("cathedral", "campanile", "crown_terrace")
CROWN_CLIMB_HEIGHTS = [LEVEL["citadel"] - 2.0, LEVEL["citadel"] + 4.0,
                       LEVEL["crown"]]

# Out of the north gate and into the open country. This is the road the painting
# shows switchbacking up the hillside on the right.
NORTH_ROAD = _route_cells((4.34, 1.66), (4.62, 1.18), (5.14, 1.12), (5.42, 1.20),
                          (5.94, 0.72), (6.28, 0.58), (6.90, 0.44))
NORTH_ROAD_HEIGHTS = [LEVEL["crown"] - 4.0, LEVEL["upland"] + 12.0,
                      LEVEL["upland"] + 6.0, LEVEL["upland"] + 4.0,
                      LEVEL["upland"] + 8.0, LEVEL["upland"] + 10.0,
                      LEVEL["upland"] + 16.0]

EAST_ROAD = _route_cells((4.34, 1.66), (5.02, 2.06), (5.58, 2.62), (6.20, 2.98),
                         (6.86, 3.28), (7.00, 3.78), (7.44, 4.10))
EAST_ROAD_HEIGHTS = [LEVEL["crown"] - 4.0, LEVEL["upland"] + 6.0,
                     LEVEL["upland"] + 2.0, LEVEL["upland"] - 2.0,
                     LEVEL["upland"] - 6.0, LEVEL["upland"] - 9.0, 7.0]

# The shore track from the shipyard round the east bay to the lighthouse neck.
BAY_TRACK = _route_cells((5.64, 4.58), (6.06, 4.78), (6.58, 5.00), (7.06, 4.92),
                         (7.48, 4.72), (7.86, 4.92), (7.72, 5.62), (6.90, 6.02),
                         (6.62, 6.18))
BAY_TRACK_HEIGHTS = [LEVEL["quay"], 5.0, 2.6, 2.6, 5.0, 4.3, 2.5,
                     LEVEL["lamp_rock"] - 11.0, LEVEL["lamp_rock"] - 6.0]

ROADS: dict[str, np.ndarray] = {
    "quayside": QUAYSIDE,
    "market_climb": MARKET_CLIMB,
    "gate_climb": GATE_CLIMB,
    "arcade_walk": ARCADE_WALK,
    "crown_climb": CROWN_CLIMB,
    "north_road": NORTH_ROAD,
    "east_road": EAST_ROAD,
    "bay_track": BAY_TRACK,
}
ROAD_HEIGHTS: dict[str, list[float]] = {
    "quayside": QUAYSIDE_HEIGHTS,
    "market_climb": MARKET_CLIMB_HEIGHTS,
    "gate_climb": GATE_CLIMB_HEIGHTS,
    "arcade_walk": ARCADE_WALK_HEIGHTS,
    "crown_climb": CROWN_CLIMB_HEIGHTS,
    "north_road": NORTH_ROAD_HEIGHTS,
    "east_road": EAST_ROAD_HEIGHTS,
    "bay_track": BAY_TRACK_HEIGHTS,
}
# Road corridor widths, in design metres before SCALE. The quayside is the
# widest because it is a working apron with cargo on it, not a street.
ROAD_WIDTH: dict[str, float] = {
    "quayside": 7.0, "market_climb": 3.4, "gate_climb": 3.8,
    "arcade_walk": 3.4, "crown_climb": 2.8, "north_road": 3.0,
    "east_road": 3.0, "bay_track": 2.4,
}
ROAD_SURFACE: dict[str, int] = {
    "quayside": TER.PAVING, "market_climb": TER.PAVING,
    "gate_climb": TER.PAVING, "arcade_walk": TER.PAVING,
    "crown_climb": TER.PAVING, "north_road": TER.PATH,
    "east_road": TER.PATH, "bay_track": TER.PATH,
}

# Surveyed service roads. The upper route closes the missing link between
# the civic terrace and the north gate; the cart climb makes a loop from the
# quay through the farmland instead of ending at the back of the city.
ROADS.update({
    "cart_climb": _route_cells((3.10, 4.59), (3.75, 4.15), (4.62, 3.90),
                               (5.10, 3.40), (5.52, 2.92), (5.58, 2.62)),
    "crown_link": _route_cells((3.30, 1.52), (3.90, 1.34), (4.34, 1.66)),
    "farm_lane": _route_cells((5.42, 1.20), (5.42, 1.10)),
    "watch_lane": _route_cells((5.58, 2.62), (6.28, 2.62),
                               (6.68, 2.52), (6.86, 2.49)),
    "coast_descent": _route_cells((7.44, 4.10), (7.25, 4.40), (7.48, 4.72)),
})
ROAD_HEIGHTS.update({
    "cart_climb": [3.4, 9.5, 13.0, 23.0, 32.0, 36.0],
    "crown_link": [52.0, 51.0, 48.0], "farm_lane": [38.0, 38.0],
    "watch_lane": [36.0, 44.0, 52.0, 56.5],
    "coast_descent": [7.0, 6.0, 5.0],
})
for _name in ("cart_climb", "crown_link", "farm_lane", "watch_lane", "coast_descent"):
    ROAD_WIDTH[_name] = 2.4
    ROAD_SURFACE[_name] = TER.PAVING if _name in ("cart_climb", "crown_link") else TER.PATH

# Two short raised crossings follow the existing shore route. The first spans
# the shipyard gully; the second keeps the lamp road above the tidal saddle.
SHORE_CROSSINGS = {
    "yard-bridge": ([(232.1, 3.58, 5.0), (262.3, 5.18, 19.4), (284.0, 2.78, 28.6)], 6.0),
    "lamp-causeway": ([(377.0, 4.80, 21.6), (391.9, 4.48, 29.5),
                       (381.8, 2.68, 79.9), (371.0, 4.75, 85.2)], 5.5),
}
# Small enclosed strips below the farmhouse, served by the well and the lane.
FARM_FIELDS = [(212.0, -224.0, 35.0), (240.0, -234.0, 36.0)]

# The mole: a built breakwater, so it is a route with a deck, not a road graded
# into the ground. The terrain only needs to know where it runs so it can hold
# the harbour floor up under it; the masonry itself is built in populate.
MOLE = _route("mole_root", "mole_bastion", "mole_head")


# ------------------------------------------------------------------ masks
def _polygon_mask(t: TER.Terrain, polygon: np.ndarray, warp: float = 0.0,
                  seed: int = 0) -> np.ndarray:
    """Even-odd point-in-polygon over the whole terrain grid.

    Mirrorhold builds its lake the same way, with a bespoke mask in its own
    region module rather than a toolkit operator, because the shape of a
    coastline is composition and belongs with the composition. Vectorised over
    edges rather than cells: 318x318 cells against 29 edges is 29 array passes,
    which is instant, where a per-cell loop is not.

    `warp` displaces the sample points by an fBm field before the test, which
    roughens the resulting boundary without needing a hand-drawn point for every
    inlet. A coastline traced from a painting with 29 points is a smooth curve,
    and a smooth curve at 576 m reads as a drawn line rather than as a shore.
    The built waterfront is authored over the top of this afterwards, so the
    quay stays straight where a quay should be straight.
    """
    if warp > 0.0:
        px = t.gx + (N.fbm(t.gx * 0.010, t.gz * 0.010, octaves=4,
                           seed=seed) - 0.5) * 2.0 * warp
        pz = t.gz + (N.fbm(t.gx * 0.010, t.gz * 0.010, octaves=4,
                           seed=seed + 7) - 0.5) * 2.0 * warp
    else:
        px, pz = t.gx, t.gz
    inside = np.zeros(px.shape, dtype=bool)
    count = polygon.shape[0]
    for i in range(count):
        ax, az = polygon[i]
        bx, bz = polygon[(i + 1) % count]
        if az == bz:
            continue
        straddles = (az > pz) != (bz > pz)
        # x of the edge at this z, guarded against the horizontal case above
        crossing_x = ax + (pz - az) * (bx - ax) / (bz - az)
        inside ^= straddles & (px < crossing_x)
    return inside


def _feather(mask: np.ndarray, t: TER.Terrain, distance: float) -> np.ndarray:
    """A 0..1 ramp that is 1 inside `mask` and falls off over `distance`.

    Used to soften a hard coastline into a beach rather than a wall. Done with
    repeated box blur rather than a real distance transform, because scipy is
    not available and the exactness buys nothing here.
    """
    field = mask.astype(np.float64)
    passes = max(int(round(distance / t.cell)), 1)
    for _ in range(passes):
        padded = np.pad(field, 1, mode="edge")
        field = (padded[:-2, 1:-1] + padded[2:, 1:-1]
                 + padded[1:-1, :-2] + padded[1:-1, 2:] + field * 2.0) / 6.0
    return np.clip(field * 1.35, 0.0, 1.0)


def land_masks(t: TER.Terrain, seed: int = 20260829) -> dict[str, np.ndarray]:
    """The three land bodies and the city footprint, as boolean grids.

    The two rocks are warped harder than the mainland: they are bare stone in
    open water and their outlines should be ragged, where the mainland's
    southern edge is a built quay and wants to stay a line.
    """
    return {
        "mainland": _polygon_mask(t, COAST, warp=15.0, seed=seed + 3),
        "gullstone": _polygon_mask(t, GULLSTONE, warp=20.0, seed=seed + 11),
        "lamp_rock": _polygon_mask(t, LAMP_ROCK, warp=20.0, seed=seed + 19),
        "city": _polygon_mask(t, CITY, warp=14.0, seed=seed + 23),
    }


# ---------------------------------------------------------------- terrain
def _ramp(edge0: np.ndarray, edge1: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Smoothstep whose edges may be arrays.

    `terrain._smoothstep` takes scalar edges; the terrace bands need a wobbling
    edge so the retaining lines are not ruler-straight, which makes both edges
    full grids. Same curve, same guard against a zero-width span - and the same
    trap the guide records: the span must be taken with its sign, because a
    reversed pair divided by a clamped 1e-9 evaluates to 1 everywhere and lifts
    the whole terrain by the band height.
    """
    span = edge1 - edge0
    span = np.where(np.abs(span) < 1e-9, 1e-9, span)
    t = np.clip((x - edge0) / span, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _terrace_band(t: TER.Terrain, mask: np.ndarray, v_south: float, v_north: float,
                  level: float, edge: float, seed: int) -> np.ndarray:
    """One level band of the city, between two rows of the reading grid.

    The band is a z-slice of the mainland rather than a disc, because the city's
    terraces are lines of retaining wall running along the contour, not circular
    platforms. Returns the blend weight so the caller can see what it claimed.

    `v_south` is the larger v - the reading grid runs north to south - which in
    world z is the *greater* value, because north is -Z. Getting that backwards
    inverts the staircase and puts the citadel at the water's edge.
    """
    z_south = cell(0.0, v_south)[1] * SCALE
    z_north = cell(0.0, v_north)[1] * SCALE
    wobble = (N.fbm(t.gx * 0.012, t.gz * 0.012, seed=seed) - 0.5) * 2.0 * edge * 0.9
    inside = (_ramp(z_north - edge + wobble, z_north + edge + wobble, t.gz)
              * (1.0 - _ramp(z_south - edge + wobble, z_south + edge + wobble, t.gz)))
    blend = inside * mask
    t.height = t.height * (1.0 - blend) + level * blend
    return blend


def build_terrain(seed: int = 20260829) -> TER.Terrain:
    """The heightfield, before anything is built on it.

    Order matters: sea floor, then the land bodies lifted out of it, then the
    city's terrace staircase cut into the mainland, then the harbour dredged
    back out of the result. Each step is written so it cannot silently undo the
    one before it - the terraces multiply by the land mask, the dredge is a
    minimum against the existing floor.
    """
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)
    masks = land_masks(t, seed)
    mainland = masks["mainland"]

    # 1. the sea floor: a shelving bed, deeper to the south and west, with
    #    enough relief that the water reads as sea rather than as a swimming
    #    pool wherever it is shallow enough to see through.
    t.height += LEVEL["sea_floor"]
    t.base_noise(2.4, 0.0125, seed=seed, octaves=5, warp=0.9)
    t.base_noise(0.8, 0.048, seed=seed + 17, octaves=4)
    # shelve up toward the coast so the drop-off is offshore, not at the beach
    shelf = _feather(mainland | masks["gullstone"] | masks["lamp_rock"], t, 70.0)
    t.height += shelf * 9.0

    # 2. the land bodies. Each is lifted to a base level inside its own mask
    #    with a feathered apron, so the coast is a beach rather than a cliff
    #    everywhere except where a cliff is wanted.
    for name, level, apron in (("mainland", 16.0, 26.0),
                               ("gullstone", LEVEL["gull_isle"] * 0.55, 12.0),
                               ("lamp_rock", LEVEL["lamp_rock"] * 0.55, 11.0)):
        ramp = _feather(masks[name], t, apron)
        t.height = t.height * (1.0 - ramp) + level * ramp

    # 2b. the two rocks are *rocks*, not green pancakes. Lifted flat out of the
    #     sea they read as pond lilies from every camera; what panel 2 shows is
    #     a broken stone mass with a crown high enough to stand a lighthouse on
    #     and flanks steep enough for the surf to break against. Ridges plus a
    #     crowning dome, all multiplied by the island's own mask so none of it
    #     leaks into the water around it.
    for name, key, ridges in (
            ("gullstone", "gull_isle", (
                (((0.80, 5.70), (1.90, 6.10), (2.90, 6.70)), 20.0, 30.0),
                (((1.10, 6.90), (2.10, 6.60), (2.60, 5.90)), 13.0, 22.0))),
            ("lamp_rock", "lamp_rock", (
                (((5.60, 6.40), (6.40, 6.00), (7.30, 5.90)), 16.0, 28.0),
                (((6.10, 7.10), (7.10, 6.90), (7.60, 6.30)), 11.0, 20.0)))):
        island = masks[name]
        before = t.height.copy()
        for points, rise, width in ridges:
            t.add_ridge(_route_cells(*points), rise, width,
                        seed=seed + N.stable_hash(name + str(rise)) % 307,
                        roughness=0.45, power=1.4)
        crest = _ANCHOR_CELLS["gullstone" if name == "gullstone" else "lamp_rock"]
        t.add_dome(_design_to_world(cell(*crest)), 74.0, LEVEL[key] * 0.5,
                   power=1.6, noise_seed=seed + 67, noise_amount=0.30)
        t.height = np.where(island, t.height, before)

    # 3. the mainland's own relief: the headland high in the north-west, the
    #    open upland rising to the north and east, and the long fall toward the
    #    waterfront that the city is terraced into.
    t.add_dome(_design_to_world(cell(0.15, 0.55)), 132.0, 43.0,
               power=1.7, noise_seed=seed + 31, noise_amount=0.22)
    t.add_dome(_design_to_world(cell(6.60, 1.20)), 206.0, 30.0,
               power=1.9, noise_seed=seed + 43, noise_amount=0.26)
    t.add_dome(_design_to_world(cell(7.90, 2.60)), 138.0, 23.0,
               power=2.1, noise_seed=seed + 47, noise_amount=0.24)
    # The upland's own texture: heath and pasture, not a smooth dome, and not a
    # rockscape either. Long wavelength and few octaves on purpose - the
    # painting's north-east is rolling grazing country with tree belts on it,
    # and at five octaves over 26 m of amplitude it came out as broken ground
    # that `assign_surface_by_rule` then correctly called rock.
    upland_noise = N.warped_fbm(t.gx * 0.0060, t.gz * 0.0060, warp=0.8,
                                octaves=3, seed=seed + 59)
    t.height += mainland * (upland_noise - 0.5) * 9.0
    # a second, finer pass only where the ground is already gentle, so pasture
    # gets texture without the cliffs gaining more
    fine = N.fbm(t.gx * 0.021, t.gz * 0.021, octaves=3, seed=seed + 61)
    t.height += mainland * (fine - 0.5) * 3.0

    # The north-west headland's seaward face. The painting opens on a cliff, and
    # a dome alone gives a rounded hill; this cuts the western flank away so the
    # mass ends in rock above the water instead of shelving into it.
    cliff = _ramp(np.full_like(t.gx, cell(1.15, 0.0)[0] * SCALE),
                  np.full_like(t.gx, cell(0.10, 0.0)[0] * SCALE), t.gx)
    north = 1.0 - _ramp(np.full_like(t.gz, cell(0.0, 1.05)[1] * SCALE),
                        np.full_like(t.gz, cell(0.0, 1.85)[1] * SCALE), t.gz)
    t.height += mainland * cliff * north * 22.0

    # 4. the world boundary. North and east are closed by rising ground, which
    #    is what the painting shows anyway; south and west are closed by open
    #    sea and need no wall. A rim on all four sides reads from any elevated
    #    camera as a dark slab floating at the map edge.
    # Open geographic boundary: coastal land continues beyond the playable frame.

    # 5. the city's terrace staircase, cut into the mainland only. Five bands
    #    from the waterfront up to the crown, each an absolute level so the
    #    retaining walls in `populate` have a known height to be.
    # The city footprint is its own polygon, feathered so the top terrace melts
    # into the upland instead of ending at a step. Multiplying the band blend by
    # a soft mask rather than intersecting a hard one is what keeps the join
    # walkable: a hard edge here is a vertical metre of wall with no ramp.
    city = _feather(masks["city"] & mainland, t, 30.0)
    for v0, v1, key, edge in (
            (4.72, 4.02, "quay", 9.0),
            (4.02, 3.36, "lower_town", 11.0),
            (3.36, 2.72, "mid_town", 12.0),
            (2.72, 2.04, "upper_town", 13.0),
            (2.04, 1.40, "citadel", 13.0),
            (1.40, 0.86, "crown", 14.0)):
        _terrace_band(t, city, v0, v1, LEVEL[key], edge,
                      seed + N.stable_hash(key) % 211)

    # 6. the harbour basin: dredged back out of the shelf, inside the mole. A
    #    minimum, not a subtraction, so it cannot cut a trench through the
    #    quay if the shelf above happens to be shallow there.
    basin = _polygon_mask(t, _poly([
        (0.70, 4.72), (5.30, 4.72), (5.30, 5.30), (4.40, 5.34),
        (2.60, 5.24), (1.20, 5.06), (0.72, 4.94)]))
    basin_ramp = _feather(basin, t, 22.0)
    # Blended toward the dredged level, not clamped below it: a dredged harbour
    # is a *maintained* bed, shallower than the sea outside the mole, so the
    # operation has to be able to raise the floor as well as lower it. `minimum`
    # here left the basin at the -18 m open-sea floor and the mole with nothing
    # to stand on.
    t.height = t.height * (1.0 - basin_ramp) + LEVEL["harbour_floor"] * basin_ramp

    # 7. The west inlet under the harbour gate. Panel 1 is a gate with ships
    #    passing beneath it, and the build's stood with its feet on dry ground
    #    at the edge of a bay - a gatehouse rather than a water gate. This cuts
    #    a short channel north from the harbour through the gate line so there
    #    is actually water under the arch.
    #
    #    The gate's own roadway is a walk surface, so the route west along the
    #    quay crosses on top of it instead of being severed. Without that the
    #    west quay becomes an island.
    t.carve_channel(_route_cells((0.98, 4.74), (0.98, 3.80)),
                    7.0 * LOCAL, 9.0, bank=1.9, seed=seed + 79,
                    floor_height=[-4.2, -3.4])

    # 8. the lighthouse neck: a low saddle joining Lamp Rock to the east shore,
    #    high enough to walk and low enough that the surf breaks over it.
    neck = _route_cells(*_LAMP_NECK)
    t.grade_path(neck, 9.0 * LOCAL, heights=[1.6, 2.4], shoulder=2.0,
                 surface=TER.SHORE, seed=seed + 73, flatten=0.85)

    t.erode(iterations=12, strength=0.26)
    t.smooth(iterations=2, weight=0.30)
    return t


def _legacy_apply_built_ground(t: TER.Terrain, seed: int = 20260829) -> None:
    """Quays, squares, roads and the built aprons.

    Runs after `build_terrain`, so every flattened level is either an authored
    LEVEL or read from the sculpted ground, which is what keeps a square from
    hovering when the terrain noise changes.
    """
    # Gullscar occupies a broad sheltered bowl, not isolated flat cuts in
    # broken rock. Its pasture descends gently towards the port road.
    t.plateau((242.0, -222.0), 65.0, 40.0, edge=48.0,
              surface=TER.MEADOW, irregular=0.0)

    # 1. the roads. Graded before the squares so a square can overwrite a road
    #    where the two meet, rather than a road cutting a gutter through a
    #    finished plaza.
    for name, points in ROADS.items():
        t.grade_path(points, ROAD_WIDTH[name] * SCALE,
                     heights=ROAD_HEIGHTS[name],
                     shoulder=2.1,
                     surface=ROAD_SURFACE[name],
                     seed=seed + N.stable_hash(name) % 197,
                     flatten=0.94)

    # 2. the working waterfront. One continuous deck at LEVEL["quay"] along the
    #    whole harbour front - a port's quay is a single datum, because cargo
    #    has to roll along it. Authored as overlapping rectangles rather than
    #    one long one so it can follow the coast's slight bend.
    quay_run = [
        ("harbour_gate", 7.0, 5.0, 0.10),
        ("custom_house", 9.0, 5.5, 0.04),
        ("main_quay", 13.0, 6.5, 0.0),
        ("chandlery", 10.0, 5.5, -0.03),
        ("ropewalk", 9.0, 5.0, -0.06),
        ("shipyard", 11.0, 7.0, -0.10),
    ]
    for name, half_x, half_z, angle in quay_run:
        t.rect_terrace(ANCHORS[name], half_x * LOCAL, half_z * LOCAL,
                       LEVEL["quay"], angle, TER.PAVING)

    # 3. the squares and precincts, each on its own terrace band.
    for name, radius, key in (
            ("fish_market", 11.0, "lower_town"),
            ("lower_square", 13.0, "lower_town"),
            ("warehouse_row", 10.0, "lower_town"),
            ("guild_hall", 9.0, "lower_town"),
            ("mid_street", 11.0, "mid_town"),
            ("arcade", 12.0, "upper_town"),
            ("cathedral", 15.0, "citadel"),
            ("campanile", 7.0, "citadel"),
            ("high_spire", 7.0, "upper_town"),
            ("brass_dome", 9.0, "crown"),
            ("crown_terrace", 12.0, "crown")):
        t.terrace(ANCHORS[name], radius * LOCAL, LEVEL[key], surface=TER.PAVING)

    # 4. the piers. Timber decks over the water, so the terrain under them stays
    #    harbour floor: only the root where they meet the quay is graded.
    for name in ("cargo_pier", "crane_pier"):
        root = ANCHORS[name]
        t.rect_terrace((root[0], root[1] - 6.0 * LOCAL), 5.0 * LOCAL, 6.0 * LOCAL,
                       LEVEL["quay"], 0.0, TER.PAVING)

    # 5. the shipyard slipway: a graded ramp running from the yard apron down
    #    into the water, which is what panel 6's hull is standing on.
    slip = np.asarray([ANCHORS["shipyard"], ANCHORS["shipyard_slip"]],
                      dtype=np.float64)
    t.grade_path(slip, 9.0 * LOCAL, heights=[LEVEL["quay"], LEVEL["slip"]],
                 shoulder=1.6, surface=TER.PAVING, seed=seed + 101, flatten=0.96)

    # 6. the upland's built places, read from the ground rather than authored,
    #    because out here the ground is the subject and the buildings sit on it.
    for name, radius in (("upland_chapel", 7.0), ("upland_farm", 9.0),
                         ("hill_estate", 11.0), ("east_watch", 6.0),
                         ("crossroads", 8.0)):
        level = 38.0 if name == "upland_farm" else float(t.height_at(*ANCHORS[name]))
        t.plateau(ANCHORS[name], radius * LOCAL, level, edge=12.0,
                  surface=TER.PAVING, irregular=0.0)
        t.rect_terrace(ANCHORS[name], radius, radius, level, surface=TER.PAVING)

    # 7. the beach at the head of the east bay, and the two rock crowns.
    t.terrace(ANCHORS["east_bay_beach"], 16.0 * LOCAL, 1.9, surface=TER.SHORE)
    t.terrace(ANCHORS["gullstone_watch"], 6.0 * LOCAL,
              float(t.height_at(*ANCHORS["gullstone_watch"])), surface=TER.PAVING)
    # Wide enough to take the tower, the keeper's house and the yard beside
    # them: at 7.0 the yard fell off the terrace edge and the spawn there had
    # 2.4 m of broken rock within arm's reach.
    t.terrace(ANCHORS["lighthouse"], 9.5 * LOCAL,
              max(float(t.height_at(*ANCHORS["lighthouse"])), 12.0),
              surface=TER.PAVING)

    # A surveyed bed has full width, exact station heights and smooth shoulders.
    # Keep the original civic squares; the new routes meet them at their level.
    for name in ("north_road", "east_road", "bay_track", "cart_climb",
                 "crown_link", "farm_lane", "watch_lane", "coast_descent"):
        RC.grade_road(t, ROADS[name], ROAD_HEIGHTS[name],
                      width=ROAD_WIDTH[name] * SCALE, shoulder=16.0,
                      surface=ROAD_SURFACE[name])
    for x, z, y in FARM_FIELDS:
        t.plateau((x, z), 15.0, y, edge=6.0, surface=TER.MEADOW, irregular=0.0)
        t.rect_terrace((x, z), 9.0, 6.0, y, surface=TER.PATH)
        t.tree_block |= np.hypot(t.gx - x, t.gz - z) < 17.0

    # Rejoin the yard and tide decks on broad, slightly lower stone landings.
    for stations, width in SHORE_CROSSINGS.values():
        for x, y, z in (stations[0], stations[-1]):
            t.plateau((x, z), width * 0.75, y - 0.18, edge=5.0,
                      surface=TER.PAVING, irregular=0.0)
            t.tree_block |= np.hypot(t.gx - x, t.gz - z) < width + 3.0

    t.assign_surface_by_rule(sea_level=SEA_LEVEL)

    # 9. Gullstone and Lamp Rock are bare stone. The slope rule only calls
    #    ground rock above a gradient of 1.05, so their gentler crowns came out
    #    as salt turf and the two of them read from the air as green pancakes
    #    floating in the sea - which is the opposite of panel 2, where the whole
    #    subject is a lighthouse standing on naked rock. Forced to ROCK here,
    #    with turf left only in the hollows where noise says soil could collect.
    masks = land_masks(t, seed)
    mainland = masks["mainland"]
    rocks = masks["gullstone"] | masks["lamp_rock"]
    soil = N.fbm(t.gx * 0.030, t.gz * 0.030, octaves=4, seed=seed + 131)
    authored = np.isin(t.surface, sorted(TER.AUTHORED_SURFACES))
    t.surface = np.where(rocks & ~authored & (soil <= 0.60), TER.ROCK, t.surface)
    t.surface = np.where(rocks & ~authored & (soil > 0.60), TER.MEADOW, t.surface)
    # the tide zone around them stays shingle whatever the noise says
    t.surface = np.where(rocks & (t.height < SEA_LEVEL + 2.2), TER.SHORE,
                         t.surface)

    # 10. The north-west headland is the same story: a cliff mass, not pasture.
    headland = mainland_headland(t)
    t.surface = np.where(headland & ~authored & (t.height > 30.0)
                         & (soil <= 0.52), TER.ROCK, t.surface)

    # 11. The upland patchwork. FOREST and MEADOW both used to point at the one
    #     salt-turf recipe, so the whole of the north-east was a single texture
    #     with noise on it and read uniform from any distance. MEADOW now carries
    #     a dry, bleached pasture, laid against the turf on a long-wavelength
    #     field so the boundary between them is field-sized rather than
    #     noise-sized - which is what the painting's ochre-and-olive patchwork
    #     actually is. Applied last so it cannot overwrite an authored surface.
    pasture = N.warped_fbm(t.gx * 0.0042, t.gz * 0.0042, warp=0.7, octaves=3,
                           seed=seed + 137)
    grain = N.fbm(t.gx * 0.016, t.gz * 0.016, octaves=3, seed=seed + 139)
    dry = (pasture * 0.76 + grain * 0.24) > 0.52
    open_ground = (t.surface == TER.FOREST) & mainland & ~masks["city"]
    t.surface = np.where(open_ground & dry & (t.height > SEA_LEVEL + 3.0),
                         TER.MEADOW, t.surface)

    t.dither_boundaries(seed=seed + 99, amount=0.5)


def mainland_headland(t: TER.Terrain) -> np.ndarray:
    """The north-west cliff mass, as a mask.

    A rectangle in the reading grid rather than a polygon: the headland is a
    corner of the map, and its two open sides are the coast and the city, both
    of which already have their own surfaces authored over the top.
    """
    x1 = cell(1.55, 0.0)[0] * SCALE
    z1 = cell(0.0, 1.95)[1] * SCALE
    return (t.gx < x1) & (t.gz < z1)


# ------------------------------------------------------------------ water
WATER_MARGIN = 240.0
"""How far the open sea runs past the authored terrain.

Westhaven's world is open to the south and west, so the water has to reach a
horizon rather than stop at the map border. Amberwood's sea does the same.
"""


# Shared server authoring reads this spatial brief. All coordinates are world
# metres; services use the same court a player sees in the authored package.
CONTENT_LAYOUT = {
    "services": [
        {"role": "information", "position": [22.0, 3.4, 0.0]},
        {"role": "storage", "position": [34.0, 3.4, -2.0]},
        {"role": "crafting_station", "position": [45.0, 3.4, 0.0]},
        {"role": "training", "position": [48.0, 3.4, 8.0]},
    ],
    "wildlife": {
        "rootback_boar": [[263, -209, 26], [262, -164, 20]],
        "moss_horn_ram": [[240, -221, 22], [276, -245, 23]],
        "bronze_tide_crab": [[316, 25, 16], [347, 37, 16]],
        "coralcrest_heron": [[316, 25, 16]],
        "brambleback_boar": [[-45, 141, 30]],
        "moor_wisp_hound": [[337, -227, 26], [70, -284, 26]],
    },
    "harvest": {
        "Wheat": [[212, -224, 7]],
        "Sage": [[240, -234, 7]],
        "Cotton": [[262, -227, 16]],
        "Kelp": [[338, 31, 14], [365, 22, 12]],
        "Shell": [[310, 30, 14], [365, 20, 14]],
        "Salt": [[287, 23, 13]],
        "Clay": [[284, 5, 14]],
    },
    "roadClearance": 6,
}


# Compact composition overrides are applied before the builder reads anchors.
from landscape_plan import configure as _configure_compact
_configure_compact(globals())

def apply_built_ground(t, seed=20260829):
    import layout
    layout.prepare(t, seed)
