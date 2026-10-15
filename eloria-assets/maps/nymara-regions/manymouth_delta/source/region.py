"""The authored Manymouth Delta region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side, and the surplus is drowned, so a player can
never walk off the authored world.

READING THE PAINTING
--------------------
The aerial is not an island with rivers in it. It is a *braided distributary
fan*: one body of water crossed by hundreds of low silt islands, thinning north-
west into open sea and thickening south-east into jungle. Land is the exception
and water is the rule, which inverts almost every assumption Amberwood's terrain
code was written under.

Three structural decisions follow from that reading:

1. **The delta floor is terrain, not a hole.** The client grounds actors by
   casting a ray down at every server tile, not only the walkable ones, so a
   region that is two-thirds water still needs a continuous surface underneath
   all of it. The heightfield covers the entire footprint and simply sits below
   sea level across most of it. That is what makes zero grounding misses
   achievable on a map that is mostly channel. Crownwater found the same thing
   from the same direction; here it matters more, because there is more water.

2. **The boardwalk network is the road network.** In the concept you do not
   walk between two places, you walk *over water* between them. The terrain
   therefore carries almost no graded paths; the connective tissue is built
   geometry in `populate.py`, decked at a level above the water, and it owns its
   server cells. See `modeling-assumptions.md`.

3. **Land thins toward the north-west.** The painting's sea is the top-left
   corner, and the island density falls off toward it. That is authored as a
   land-probability field rather than a hard coastline, because a delta has no
   coastline - it has a zone where the bars stop being able to hold themselves
   above the water.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER

# `Placement` and `RegionBuild` are the toolkit's shared build containers, not
# anything Amberwood-specific, and every region needs them. Re-exported here so
# this module is the whole namespace a Manymouth build script has to import.
from amberwood.region import Placement, RegionBuild  # noqa: F401

import deltakit as DK

# ---------------------------------------------------------------- extents
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# The composition is written in a 192 m design space and scaled up here, so the
# aerial concept's layout is preserved rather than stretched.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A village square is sized by the huts around it, a market by the boats in it.
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

# ------------------------------------------------------- surface classes
# These two now live in the shared table as `TER.DELTA_SILT` (30) and
# `TER.DELTA_PADDY` (31). They were allocated privately here as 23 and 24, which
# collided head-on with Grey Moors the moment both landed: it claimed 23-27 in
# the toolkit, this claimed 23-24 in a file nobody else reads, and each was
# correct alone and wrong together. Every other region's classes are in the
# toolkit; these are too now.
MM_SILT = TER.DELTA_SILT
MM_PADDY = TER.DELTA_PADDY

# The delta's default ground is jungle litter, and its water-line ground is
# shell sand. Repointed rather than added: the *class* is what the terrain
# operators speak in, and FOREST already means "the vegetated default".
TER.SURFACE_MATERIALS[TER.FOREST] = DK.JUNGLE
TER.SURFACE_MATERIALS[TER.SHORE] = DK.SANDBAR
# The ruins and the temple precinct are the region's only cut stone.
TER.SURFACE_MATERIALS[TER.PAVING] = DK.GLYPH

# ------------------------------------------------------------ water levels
# The delta is shallow almost everywhere. These are the four depths that carry
# the aerial's colour banding: bar, flat, channel, sea.
DELTA_FLOOR = -2.6           # the general silt flat between the bars
CHANNEL_FLOOR = -7.2         # the navigable distributaries
SEA_FLOOR = -17.0            # open water off the north-west
WHIRL_FLOOR = -13.5          # the pit under the great arch

# Typical island freeboard. Deliberately low: these are silt bars held together
# by mangrove root, not rock. The whole region's relief is under 30 m, and
# almost all of that is the temple mount and the one rock headland.
ISLE_LOW = 1.35
ISLE_MID = 2.30
ISLE_HIGH = 3.40

# ------------------------------------------------------------ composition
# Centred on the middle of the playable footprint rather than on the origin: the
# origin is the arrival datum, and arriving on top of the great arch throws away
# the approach the concept is built around. This puts the arch at the centre of
# the map with the arrival village south-west of it, which is the framing of
# panel 9 - two figures on a deck, the whole delta and the far spires beyond.
CENTRE = (38.0, -38.0)

# North-west is -X and -Z. The land-probability field falls off along this axis,
# which is the direction the painting's sea lies in.
SEA_DIRECTION = (-0.62, -0.78)


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


def _route(*points) -> np.ndarray:
    return np.asarray([(x * SCALE, z * SCALE) for x, z in points], dtype=np.float64)


# Named places, in design space. Three rings, as Amberwood's notes recommend:
# the composition the aerial actually shows, then a second and third ring of
# authored places filling the area the 3x enlargement opens up - rather than
# spreading the first ring's objects thinner.
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # --- ring 1: the subject of the aerial -----------------------------
    # The great ring-arch over its whirlpool, dead centre (aerial centre;
    # panel 8 is its drowned interior).
    "great_arch": CENTRE,
    "arch_stair": (CENTRE[0] - 11.0, CENTRE[1] + 7.0),
    # The main stilt town: panels 2, 3 and 4 are all inside it.
    "stilt_town": (12.0, -16.0),
    "town_hall": (10.0, -20.5),          # the gilded tiered hall of panel 2
    "market_hall": (4.5, -9.0),          # the arched market of panel 4
    "town_quay": (18.0, -11.0),          # panel 3's boardwalk junction
    # The canoe market of panel 6, in the sheltered water south-west of town.
    "floating_market": (-12.0, -3.0),
    # The banyan landing of panel 5: a deck built inside aerial roots.
    "banyan_landing": (27.0, -60.0),
    # The overlook of panel 9.
    "overlook": (52.0, 6.0),

    # --- ring 2 --------------------------------------------------------
    # The paddy and lotus terraces of panel 7, on the fresher water inland.
    "paddy_terraces": (-17.0, -86.0),
    "paddy_tower": (-4.0, -92.0),
    "paddy_hamlet": (-28.0, -78.0),
    # The stepped temple on the aerial's east rim.
    "green_temple": (99.0, -103.0),
    "temple_quay": (88.0, -92.0),
    # The mouth of the flooded labyrinth - panel 8's cavern is served by the
    # `manymouth_flooded_labyrinth` interior map, not by this package.
    "cave_mouth": (72.0, -8.0),
    # The mangrove reach of panel 1, dense enough to pole a canoe through.
    "mangrove_reach": (-38.0, -48.0),
    # Where the delta gives out into open sea.
    "sea_landing": (-44.0, -110.0),
    "ruin_stelae": (76.0, -76.0),

    # --- ring 3 --------------------------------------------------------
    "east_hamlet": (117.0, -58.0),
    "south_hamlet": (58.0, 33.0),
    "west_hamlet": (-43.0, 13.0),
    "north_fishing": (34.0, -117.0),
    "boat_yard": (-6.0, 28.0),
    "upper_paddy": (16.0, -110.0),
    "far_bar": (99.0, 19.0),
    "east_watch": (121.0, -12.0),
    "south_shrine": (24.0, 41.0),
    "deep_grove": (68.0, -46.0),
}

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()
}

SPAWN = ANCHORS["stilt_town"]
SPAWN_ARCH = ANCHORS["arch_stair"]
SPAWN_TEMPLE = ANCHORS["temple_quay"]


# -------------------------------------------------------------- islands
# name -> (radius, freeboard, apron radius, edge width) in *design* metres.
# Radii are LOCAL-scaled, not SCALE-scaled: enlarging the region must put more
# water between the islands, not inflate every island to nine times the area.
_NAMED_ISLES: dict[str, tuple[float, float, float, float]] = {
    "great_arch": (17.0, ISLE_MID, 30.0, 9.0),
    "stilt_town": (15.0, ISLE_LOW, 30.0, 8.0),
    "floating_market": (7.0, ISLE_LOW, 20.0, 6.0),
    "banyan_landing": (11.0, ISLE_MID, 21.0, 7.0),
    "overlook": (9.0, ISLE_MID, 18.0, 6.0),
    "paddy_terraces": (21.0, ISLE_MID, 36.0, 11.0),
    "paddy_hamlet": (10.0, ISLE_LOW, 19.0, 6.0),
    "green_temple": (24.0, 9.4, 40.0, 15.0),
    "temple_quay": (9.0, ISLE_LOW, 18.0, 6.0),
    "cave_mouth": (14.0, 7.6, 24.0, 8.0),
    "ruin_stelae": (10.0, ISLE_MID, 19.0, 6.0),
    "east_hamlet": (11.0, ISLE_LOW, 21.0, 7.0),
    "south_hamlet": (11.0, ISLE_LOW, 21.0, 7.0),
    "west_hamlet": (10.0, ISLE_LOW, 19.0, 6.0),
    "north_fishing": (9.0, ISLE_LOW, 18.0, 6.0),
    "boat_yard": (9.0, ISLE_LOW, 18.0, 6.0),
    "upper_paddy": (14.0, ISLE_MID, 25.0, 8.0),
    "far_bar": (12.0, ISLE_LOW, 24.0, 8.0),
    "east_watch": (9.0, ISLE_HIGH, 17.0, 6.0),
    "south_shrine": (8.0, ISLE_MID, 16.0, 5.0),
    "deep_grove": (13.0, ISLE_MID, 24.0, 8.0),
    "mangrove_reach": (12.0, 0.85, 26.0, 9.0),
    "sea_landing": (8.0, ISLE_LOW, 17.0, 6.0),
}


def _design_reach(x: float, z: float) -> float:
    """Distance along the sea axis in design metres. Positive is seaward."""
    return ((x - CENTRE[0]) * SEA_DIRECTION[0]
            + (z - CENTRE[1]) * SEA_DIRECTION[1])


def _land_probability(x: float, z: float) -> float:
    """How likely a bar is to hold itself above water at this design point.

    The painting is *mostly land* - hundreds of small bars packed close enough
    that the water between them reads as channels rather than as sea - and it
    thins only in the top-left corner. So this sits near 0.9 across the fan and
    collapses over the last third of the seaward axis. The first version of this
    field peaked at 0.26 in the middle of the map, which produced two dozen
    isolated discs in an ocean: a lagoon, not a delta.
    """
    reach = _design_reach(x, z)
    return float(np.clip(1.0 / (1.0 + math.exp((reach - 52.0) / 21.0)),
                         0.0, 1.0))


def _scatter_isles(seed: int) -> list[dict]:
    """The unnamed bars, on a jittered lattice filtered by land probability.

    A delta reads as *many* islands. Placing thirty by hand would be thirty
    decisions that all look the same; the lattice gives the count and the
    probability field gives the composition, and the named places above are
    what the player actually arrives at.

    Bars are lens-shaped, not round. A braid bar is deposited by a current, so
    it is drawn out along the flow and blunt across it - that elongation is the
    single strongest read in the aerial, and a field of circles does not look
    like a delta at any density.
    """
    out = []
    step = 10.0
    axis = np.asarray(SEA_DIRECTION, dtype=np.float64)
    x = -64.0
    while x < 142.0:
        z = -142.0
        while z < 64.0:
            # One hash per variate. `stable_hash` is CRC-32, so it tops out
            # near 2.1e9: slicing five decimal digits out of a single key gives
            # the high field a range of 0-2 and every bar comes out the same
            # size. That is not a hypothetical - it is what the first island
            # field did, and it is invisible until you look at the map.
            cell_key = f"bar:{x:.0f}:{z:.0f}"

            def _v(salt: str, key: str = cell_key) -> float:
                return N.stable_hash(f"{key}:{salt}") % 10000 / 10000.0

            jx = x + (_v("jx") - 0.5) * step * 1.25
            jz = z + (_v("jz") - 0.5) * step * 1.25
            if _v("roll") > _land_probability(jx, jz):
                z += step
                continue
            # keep clear of the authored places, which own their own water
            too_close = False
            for name, (ax, az) in _DESIGN_ANCHORS.items():
                clearance = 14.0 if name in _NAMED_ISLES else 7.0
                if math.hypot(jx - ax, jz - az) < clearance:
                    too_close = True
                    break
            if too_close:
                z += step
                continue
            size = _v("size")
            spin = _v("spin")
            radius = 3.6 + size * 5.6
            # the bar's own axis wanders either side of the regional flow
            angle = math.atan2(axis[1], axis[0]) + (spin - 0.5) * 0.85
            out.append({
                "centre": (jx, jz),
                "radius": radius,
                "level": 0.95 + size * 2.10,
                # A thin apron, not a wide one. At 2.1x the bar radius every
                # island came out as a small green dot inside a large pale
                # halo, and the aerial read as shoals rather than as land.
                "apron": radius * 1.34,
                "edge": max(radius * 0.62, 1.6),
                "axis": (math.cos(angle), math.sin(angle)),
                "elongation": 1.45 + spin * 0.95,
                "named": False,
            })
            z += step
        x += step
    return out


def island_table(seed: int) -> dict[str, dict]:
    """Every island in the region, named and unnamed, in world metres.

    Resolved once, here, rather than inside `build_terrain`: the population
    passes need the *same* radii and levels the terrain was actually built from.
    Recomputing the jitter in two places is how a stilt house ends up hovering
    or a jetty lands in open water.
    """
    axis = math.atan2(SEA_DIRECTION[1], SEA_DIRECTION[0])
    table: dict[str, dict] = {}
    for name, (radius, freeboard, apron, edge) in _NAMED_ISLES.items():
        j = N.stable_hash(f"isle:{name}") % 1000 / 1000.0
        angle = axis + (j - 0.5) * 1.2
        table[name] = {
            "centre": ANCHORS[name],
            "radius": radius * LOCAL * (0.88 + 0.24 * j),
            "level": freeboard * (0.92 + 0.18 * j),
            "apron": apron * LOCAL * (0.90 + 0.20 * (1.0 - j)),
            "edge": edge * LOCAL * (0.85 + 0.30 * j),
            "axis": (math.cos(angle), math.sin(angle)),
            # An inhabited bar is the one a village actually fits on, so these
            # stay much rounder than the wild bars around them.
            "elongation": 1.0 + j * 0.45,
            "named": True,
        }
    for index, bar in enumerate(_scatter_isles(seed)):
        table[f"bar_{index:03d}"] = {
            "centre": (bar["centre"][0] * SCALE, bar["centre"][1] * SCALE),
            "radius": bar["radius"] * LOCAL,
            "level": bar["level"],
            "apron": bar["apron"] * LOCAL,
            "edge": max(bar["edge"] * LOCAL, 2.0),
            "axis": bar["axis"],
            "elongation": bar["elongation"],
            "named": False,
        }
    return table


# ----------------------------------------------------------- watercourses
# The distributaries, south-east head to north-west sea. Written as design-space
# polylines and scaled, so changing the region's extent moves them together.
_DISTRIBUTARIES: dict[str, tuple[tuple[float, float], ...]] = {
    "great_mouth": ((132.0, 24.0), (96.0, -6.0), (62.0, -22.0), (30.0, -34.0),
                    (-4.0, -52.0), (-34.0, -78.0), (-58.0, -104.0)),
    "north_mouth": ((128.0, -34.0), (100.0, -52.0), (70.0, -70.0),
                    (36.0, -86.0), (2.0, -104.0), (-32.0, -122.0)),
    "temple_mouth": ((134.0, -76.0), (110.0, -88.0), (78.0, -110.0),
                     (44.0, -126.0), (10.0, -136.0)),
    "south_mouth": ((126.0, 46.0), (88.0, 34.0), (52.0, 22.0), (16.0, 12.0),
                    (-20.0, 4.0), (-52.0, -8.0)),
    "market_reach": ((44.0, -20.0), (18.0, -8.0), (-10.0, 2.0), (-40.0, 10.0)),
    "mangrove_cut": ((14.0, -40.0), (-14.0, -46.0), (-42.0, -52.0),
                     (-60.0, -62.0)),
    "cave_run": ((88.0, -2.0), (70.0, -14.0), (54.0, -28.0)),
}

DISTRIBUTARIES: dict[str, np.ndarray] = {
    name: _route(*points) for name, points in _DISTRIBUTARIES.items()
}

# Which of them are navigable in the fiction, and therefore dredged deeper and
# drawn with the darker water pass. The rest are shallow braid.
DEEP_ROUTES = ("great_mouth", "north_mouth", "temple_mouth", "south_mouth")


# --------------------------------------------------------------- terrain
def build_terrain(seed: int = 20260829) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # 1. The fan itself: a very shallow ramp from the south-east head down to
    #    the north-west sea. Not a hillside - a delta's gradient is a few metres
    #    over half a kilometre, and anything steeper reads as a river valley.
    t.height += DELTA_FLOOR
    t.add_slope(SEA_DIRECTION, -0.0165, origin=(CENTRE[0] * SCALE,
                                                CENTRE[1] * SCALE))

    # 2. Open sea off the north-west. A separate deepening rather than more
    #    slope, so the shelf edge is a place instead of a gradient.
    reach = ((t.gx - CENTRE[0] * SCALE) * SEA_DIRECTION[0]
             + (t.gz - CENTRE[1] * SCALE) * SEA_DIRECTION[1])
    offshore = np.clip((reach - 190.0) / 200.0, 0.0, 1.0)
    t.height -= offshore ** 1.6 * abs(SEA_FLOOR - DELTA_FLOOR)

    # 3. Bed texture. Two octave bands: broad bar-and-swale, then the fine
    #    ripple that keeps the shallows from reading as a painted plane.
    t.base_noise(1.05, 0.0125, seed=seed, octaves=5, warp=1.05)
    t.base_noise(0.38, 0.052, seed=seed + 17, octaves=4)

    # 4. Every island, named and scattered.
    isles = island_table(seed)
    for name, geom in isles.items():
        _island(t, geom, seed + N.stable_hash(name) % 211)

    # 5. The distributaries, cut *after* the bars rather than before them.
    #    Carving first and raising islands afterwards buries the channel
    #    wherever the two overlap, which is everywhere the fan is dense: the
    #    south-east half came back as one merged landmass with no navigable
    #    water in it at all. A distributary is the thing that cuts the bar
    #    field apart, so it has to run last and win.
    for name, points in DISTRIBUTARIES.items():
        deep = name in DEEP_ROUTES
        # `carve_channel`'s width is the half-width at which the cut reaches
        # zero, so a "width" of 9 design metres is a 54 m channel once scaled -
        # about what the aerial's navigable mouths measure against the villages
        # on their banks.
        width = (9.0 if deep else 5.5) * SCALE
        depth = abs(CHANNEL_FLOOR - DELTA_FLOOR) * (1.0 if deep else 0.55)
        t.carve_channel(points, width, depth, bank=2.2,
                        seed=seed + N.stable_hash(name) % 97)

    # 6. The minor braid. The named distributaries are the shipping lanes; what
    #    makes the aerial read as a *delta* rather than as an archipelago is the
    #    hundreds of small threads between the bars. Authoring those as
    #    polylines would be hundreds of arbitrary decisions, so they are cut as
    #    a ridged-noise network instead: ridged noise is exactly a field of
    #    branching lines, and inverting it gives branching channels.
    braid = N.ridged(t.gx * 0.0125, t.gz * 0.0125, octaves=4, seed=seed + 83)
    thread = np.clip((braid - 0.58) / 0.42, 0.0, 1.0)
    t.height -= thread ** 1.4 * 3.6

    # 6. The whirlpool under the great arch. A funnel, not a bowl: the concept
    #    shows water turning down a throat, so the profile has to be steep at
    #    the centre and shallow at the rim.
    t.add_dome(ANCHORS["great_arch"], 26.0 * LOCAL,
               -abs(WHIRL_FLOOR - DELTA_FLOOR), power=3.4)

    # 7. The one piece of rock in the region: the headland the flooded labyrinth
    #    runs into. Everything else here is silt, and a delta with no hard ground
    #    anywhere has nowhere to put a cave mouth.
    t.add_dome(ANCHORS["cave_mouth"], 22.0 * LOCAL, 5.0, power=1.7,
               noise_seed=seed + 41, noise_amount=0.22)

    # 8. No rim wall. Amberwood closes its world with mountains because it is
    #    land; the delta's horizon is open water on three sides and jungle on
    #    the fourth, and a raised rim outside the playable footprint reads from
    #    any elevated camera as a slab floating at the map edge. The world is
    #    closed by the collision grid instead: water is not walkable, the bed
    #    still grounds every tile, and nothing reaches a void.
    #
    #    The exception is the south-east head, where the fan runs back into
    #    jungle. That gets real ground so the horizon in panels 7 and 9 has
    #    something behind it.
    #    Kept low and kept in the corner: the head is a horizon, not a mountain
    #    range, and a delta whose south-east quarter is a hillside is a river
    #    valley with islands in it.
    head = np.clip((-reach - 340.0) / 90.0, 0.0, 1.0)
    head_noise = N.fbm(t.gx * 0.010, t.gz * 0.010, octaves=5, seed=seed + 61)
    t.height += head ** 1.6 * (3.5 + head_noise * 13.0)

    t.erode(iterations=8, strength=0.20)
    t.smooth(iterations=2, weight=0.30)
    return t


def _window(t: TER.Terrain, centre: tuple[float, float], reach: float):
    """The grid slice a local operator needs, plus its coordinate meshes.

    The toolkit's shaping operators all run over the whole heightfield, which is
    right for the handful of large features a land region has. Manymouth places
    four hundred bars, and four hundred full-grid passes over a 319x319 field is
    a minute of numpy for geometry that occupies twenty cells. Restricting each
    bar to its own bounding window makes the cost proportional to the island
    rather than to the map, and produces bit-identical results because every
    cell outside the window is one the operator would have left unchanged.
    """
    col0 = int(max(0, math.floor((centre[0] - reach - t.x0) / t.cell)))
    col1 = int(min(t.cols, math.ceil((centre[0] + reach - t.x0) / t.cell) + 1))
    row0 = int(max(0, math.floor((centre[1] - reach - t.z0) / t.cell)))
    row1 = int(min(t.rows, math.ceil((centre[1] + reach - t.z0) / t.cell) + 1))
    if col1 <= col0 or row1 <= row0:
        return None
    rows = slice(row0, row1)
    cols = slice(col0, col1)
    return rows, cols, t.gx[rows, cols], t.gz[rows, cols]


def _lens_distance(gx, gz, centre, axis, elongation, radius):
    """Distance to a lens: a disc scaled down across its own axis.

    Dividing the across-axis component by the elongation before taking the norm
    turns the circle into an ellipse drawn out along `axis`, which is the shape
    a current actually deposits.
    """
    dx = gx - centre[0]
    dz = gz - centre[1]
    along = dx * axis[0] + dz * axis[1]
    across = -dx * axis[1] + dz * axis[0]
    return np.hypot(along / max(elongation, 1e-6), across)


def _island(t: TER.Terrain, geom: dict, seed: int) -> None:
    """Raise one silt bar out of the delta, with its shoal apron around it.

    Bars are **plateaus with soft edges, not domes.** A dome of the right height
    has almost no usable ground on it - everything but the tip exceeds the
    walkable slope limit - and an archipelago of domes comes out at a few per
    cent walkable. Crownwater recorded the same finding for its islets; it
    applies harder here, because Manymouth has twenty times as many islands and
    they are a third the height.

    The apron matters as much as the bar: it is the pale turquoise halo around
    every island in the painting, and it is what a moored canoe, a mangrove
    stand and a wading heron all need to sit on.
    """
    centre = geom["centre"]
    axis = geom["axis"]
    elongation = geom["elongation"]
    radius = geom["radius"]
    apron = geom["apron"]
    edge = geom["edge"]

    window = _window(t, centre, apron * elongation + t.cell * 2.0)
    if window is None:
        return
    rows, cols, gx, gz = window

    # the shoal first, lifted off the bed toward but not above the water line
    wobble = (N.fbm(gx * 0.05, gz * 0.05, seed=seed + 3) - 0.5) * 2.0
    shoal_d = _lens_distance(gx, gz, centre, axis, elongation, apron) \
        + wobble * 0.26 * apron
    falloff = np.clip(1.0 - shoal_d / max(apron, 1e-6), 0.0, 1.0) ** 1.5
    t.height[rows, cols] += falloff * abs(DELTA_FLOOR) * 0.78

    # then the bar proper, as an absolute level with an organic edge
    irregular = (N.fbm(gx * 0.07, gz * 0.07, seed=seed + 7) - 0.5) * 2.0
    bar_d = _lens_distance(gx, gz, centre, axis, elongation, radius) \
        * (1.0 + 0.30 * irregular)
    blend = 1.0 - TER._smoothstep(radius - edge, radius + edge, bar_d)
    t.height[rows, cols] = t.height[rows, cols] * (1.0 - blend) \
        + geom["level"] * blend
    t.surface[rows, cols] = np.where(blend > 0.55, TER.FOREST,
                                     t.surface[rows, cols])


def apply_built_ground(t: TER.Terrain, seed: int = 20260829) -> None:
    """Terraces, paddies and landings - the worked part of the surface.

    Runs after `build_terrain`, so every level is taken from the sculpted ground
    rather than assumed, which is what keeps a village square from hovering when
    the island noise changes.
    """
    isles = island_table(seed)

    # --- the paddy and lotus terraces of panel 7 -----------------------
    # Stepped, because that is what the panel shows: three levels of standing
    # water held behind low bunds, each a little above the one below, with the
    # bamboo causeway running along the bunds. Authored absolutely rather than
    # read from the terrain: the whole point is that they are level, and a
    # terrace that follows the bar's noise is a marsh, not a paddy.
    paddy_centre = ANCHORS["paddy_terraces"]
    for step, (offset, level, radius) in enumerate((
            ((-14.0, 10.0), 0.55, 17.0),
            ((2.0, 0.0), 1.15, 19.0),
            ((15.0, -11.0), 1.75, 16.0))):
        t.terrace((paddy_centre[0] + offset[0] * LOCAL,
                   paddy_centre[1] + offset[1] * LOCAL),
                  radius * LOCAL, level, surface=MM_PADDY)
    upper = ANCHORS["upper_paddy"]
    for offset, level, radius in (((-9.0, 6.0), 0.65, 12.0),
                                  ((7.0, -6.0), 1.30, 12.0)):
        t.terrace((upper[0] + offset[0] * LOCAL, upper[1] + offset[1] * LOCAL),
                  radius * LOCAL, level, surface=MM_PADDY)

    # --- mangrove flats ------------------------------------------------
    # Silt that is exposed at low water and root-bound: the ground of panels 1
    # and 5, and the material study's floor. Deliberately *below* the walkable
    # threshold, so it reads as ground you pole a canoe over rather than ground
    # you cross on foot.
    for name in ("mangrove_reach", "banyan_landing"):
        centre = ANCHORS[name]
        t.terrace(centre, 15.0 * LOCAL,
                  max(float(t.height_at(*centre)) - 0.55, SEA_LEVEL - 0.85),
                  surface=MM_SILT)

    # --- the temple mount ----------------------------------------------
    # An acropolis, not a building on a lawn: in the aerial the temple stands
    # well above everything around it and is the only thing on the horizon from
    # the middle of the delta. Three concentric steps, each wide enough that its
    # riser stays walkable (9 m of edge for 3 m of rise, a gradient of 0.33).
    temple = ANCHORS["green_temple"]
    base = float(t.height_at(*temple))
    for radius, rise in ((21.0, 2.6), (14.5, 5.4), (8.5, 8.0)):
        t.plateau(temple, radius * LOCAL, base + rise, edge=9.0 * LOCAL,
                  surface=TER.PAVING, seed=seed + 71, irregular=0.08)
    t.terrace(ANCHORS["temple_quay"], 7.0 * LOCAL,
              max(float(t.height_at(*ANCHORS["temple_quay"])), 1.05),
              surface=TER.PAVING)

    # --- the ruin platforms --------------------------------------------
    # The arch stands on a drowned platform. Its top is deliberately just under
    # the water line, so the ring reads as rising *out of* the whirlpool the way
    # the painting shows, rather than off a dry plinth.
    t.terrace(ANCHORS["great_arch"], 13.0 * LOCAL, -0.55, surface=TER.PAVING)
    t.terrace(ANCHORS["arch_stair"], 6.5 * LOCAL, 1.25, surface=TER.PAVING)
    t.terrace(ANCHORS["ruin_stelae"], 7.0 * LOCAL,
              max(float(t.height_at(*ANCHORS["ruin_stelae"])), 1.10),
              surface=TER.PAVING)

    # the labyrinth's mouth: a cut platform at the foot of the rock
    cave = ANCHORS["cave_mouth"]
    t.rect_terrace((cave[0] - 6.0 * LOCAL, cave[1] + 9.0 * LOCAL),
                   9.0 * LOCAL, 6.0 * LOCAL,
                   max(float(t.height_at(cave[0] - 6.0 * LOCAL,
                                         cave[1] + 9.0 * LOCAL)), 1.30),
                   0.0, TER.PAVING)

    # --- village ground -------------------------------------------------
    # Every inhabited bar gets a level pad at its own island's height, so huts,
    # racks and drying frames stand on flat ground instead of on the bar's
    # noise. Read from the island table, not re-derived.
    for name in ("stilt_town", "paddy_hamlet", "east_hamlet", "south_hamlet",
                 "west_hamlet", "north_fishing", "boat_yard", "far_bar",
                 "sea_landing", "overlook", "deep_grove", "south_shrine",
                 "east_watch"):
        geom = isles[name]
        t.terrace(geom["centre"], geom["radius"] * 0.40,
                  float(t.height_at(*geom["centre"])), surface=TER.PATH)

    t.assign_surface_by_rule(sea_level=SEA_LEVEL)

    # Take the bar tops back off the shore rule. `assign_surface_by_rule`
    # paints SHORE over everything within 1.6 m of the water line, which is a
    # sensible default for a region whose land stands well clear of the sea and
    # completely wrong for one whose islands are 1 to 2.5 m of silt: it turned
    # every bar in the delta into a sandbank, and the first in-client aerial
    # came back as a white sand flat where the painting has dense green
    # islands. Sand keeps the last 0.9 m at the water's edge, which is where a
    # beach actually is, and the bar tops go back to jungle.
    bar_top = (t.height > SEA_LEVEL + 0.90) & (t.surface == TER.SHORE)
    t.surface = np.where(bar_top, TER.FOREST, t.surface)

    t.dither_boundaries(seed=seed + 99, amount=0.5)
