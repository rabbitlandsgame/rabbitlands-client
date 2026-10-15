"""The authored Crownwater region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 396-cell grid at one metre per tile with the arrival datum at
server (120, 120), which lands on the Godot origin:

    godot_x = server_x - 120        godot_z = 120 - server_y

so the reachable area is x in [-120, 275] and z in [-275, 120]. The terrain is
cut larger than that on every side, and the surplus is drowned or walled so a
player can never walk off the authored world.

Composition follows the aerial concept, which is not a landscape with a lake in
it but a *lagoon with a city in it*: a broad shallow turquoise basin, a single
large crowned island at its centre carrying the domed cathedral complex, a ring
of eight smaller pavilion islets around it, a wider scatter of outer islets, and
stone causeways stitching the whole thing together over open water.

The one structural decision that follows from that reading: **the lagoon floor
is terrain, not a hole.** The client grounds actors by casting a ray down at
every server tile, not only walkable ones, so a region whose middle is water
still needs a continuous surface underneath it. Crownwater's heightfield covers
the entire footprint and simply sits below sea level across most of it. That is
what makes zero grounding misses achievable on a map that is mostly sea.
"""
from __future__ import annotations

import math
import coastal_plan as COAST

import numpy as np

from amberwood import noise as N
from amberwood import terrain as TER
from amberwood import routecraft as RC

# `Placement` and `RegionBuild` are the toolkit's shared build containers, not
# anything Amberwood-specific, and every region needs them. Re-exported here so
# this module is the whole namespace a Crownwater build script has to import.
# (A toolkit refactor moving them to their own module is in flight in another
# session; `amberwood.region` re-exports them either way, so this import holds.)
from amberwood.region import Placement, RegionBuild  # noqa: F401

# ---------------------------------------------------------------- extents
# Crownwater is authored at 576 m x 576 m, matching Amberwood, so the server map
# is 96x96 ELM tiles (576 height cells) at one metre per tile. The arrival datum
# keeps the same 30%-in-from-the-south-west position Amberwood uses.
SERVER_ORIGIN = COAST.SERVER_ORIGIN
SERVER_CELLS = COAST.SERVER_CELLS
METRES_PER_TILE = 1.0

# The composition is written in a 192 m design space and scaled up here, so the
# aerial concept's layout is preserved rather than stretched.
SCALE = 2.0

# Distances between places scale with the region; the places themselves do not.
# A plaza is sized by the buildings around it, a quay by the boats along it.
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

# Crownwater's built ground uses its mosaic and sand palette. Bind the shared
# paving and shore classes for this build; material recipes are registered by
# amberwood.crownmaterials through the crownkit compatibility entry point.
TER.SURFACE_MATERIALS[TER.PAVING] = "cobble_paving"
TER.SURFACE_MATERIALS[TER.SHORE] = "crownwater_sand"

# The lagoon floor datum. Everything starts here and islands are lifted out of
# it, which is the inverse of Amberwood's "land, then cut a sea into it".
LAGOON_FLOOR = -5.0
CHANNEL_FLOOR = -9.5
SHALLOWS = -1.35

# The sunken court's floor. Shallow enough that its tiling and glyph read clearly
# from a boat above it, deep enough that it is unmistakably drowned. At -1.90 it
# was invisible in client capture: even at the lagoon's 0.70 alpha, two metres of
# water washed the mosaic out completely. A metre of clear water is enough to say
# "submerged" and little enough to see through.
SUNKEN_COURT_LEVEL = -1.05

# ------------------------------------------------------------ composition
# The archipelago is centred on the middle of the playable footprint rather than
# on the origin, because the origin is the arrival datum and arriving *inside*
# the cathedral plaza wastes the approach the concept is built around. Placing
# the centre here puts the SW inner-ring islet almost exactly on the origin, so
# a player spawns on the harbour islet with the whole city across the water to
# the north-east - which is the framing of detail-board panel 1.
CENTRE = (38.0, -38.0)

INNER_RADIUS = 54.0
OUTER_RADIUS = 88.0


def _ring(centre, radius, count, phase_degrees=0.0):
    """Evenly spaced points on a ring, in design space."""
    out = []
    for i in range(count):
        angle = math.radians(phase_degrees + 360.0 * i / count)
        out.append((centre[0] + radius * math.cos(angle),
                    centre[1] + radius * math.sin(angle)))
    return out


# Eight pavilion islets. Index 3 (135 degrees) lands on the design origin and is
# the harbour: that is not a coincidence, it is chosen so the arrival datum sits
# on authored ground rather than wherever the ring happened to fall.
_INNER = _ring(CENTRE, INNER_RADIUS, 8)
_OUTER = _ring(CENTRE, OUTER_RADIUS, 8, phase_degrees=22.5)

_INNER_NAMES = ["pavilion_east", "pavilion_southeast", "pavilion_south",
                "harbour_isle", "pavilion_west", "pavilion_northwest",
                "pavilion_north", "pavilion_northeast"]
_OUTER_NAMES = ["outer_east", "outer_southeast", "outer_south", "outer_southwest",
                "outer_west", "outer_northwest", "outer_north", "outer_northeast"]

_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    "crown_isle": CENTRE,
    "cathedral": (CENTRE[0], CENTRE[1] - 6.0),
    "crown_plaza": (CENTRE[0], CENTRE[1] + 9.0),
    "crown_quay_south": (CENTRE[0] + 1.0, CENTRE[1] + 27.0),
    "crown_quay_north": (CENTRE[0] - 2.0, CENTRE[1] - 27.0),
    "crown_garden": (CENTRE[0] - 17.0, CENTRE[1] + 4.0),
    "crown_campanile": (CENTRE[0] + 16.0, CENTRE[1] - 12.0),
}
_DESIGN_ANCHORS.update(dict(zip(_INNER_NAMES, _INNER)))
_DESIGN_ANCHORS.update(dict(zip(_OUTER_NAMES, _OUTER)))

# Named places that hang off the ring islets. Each is offset from its islet so
# it reads as a place on an island rather than as the island itself.
_DESIGN_ANCHORS.update({
    # the arrival islet: quay, bollards, moored boats (panels 2, 6 and 10)
    "harbour_quay": (_DESIGN_ANCHORS["harbour_isle"][0] + 9.0,
                     _DESIGN_ANCHORS["harbour_isle"][1] - 7.0),
    "harbour_lamp_walk": (_DESIGN_ANCHORS["harbour_isle"][0] + 2.0,
                          _DESIGN_ANCHORS["harbour_isle"][1] - 11.0),
    "harbour_market": (_DESIGN_ANCHORS["harbour_isle"][0] - 8.0,
                       _DESIGN_ANCHORS["harbour_isle"][1] + 3.0),
    # the garden islet of panel 8: concentric planting beds around a fountain
    "garden_isle": _DESIGN_ANCHORS["pavilion_west"],
    "garden_fountain": (_DESIGN_ANCHORS["pavilion_west"][0],
                        _DESIGN_ANCHORS["pavilion_west"][1]),
    # The sunken court of panel 7, deliberately below the water line. Sited in
    # the shallow gap between the harbour islet and the west pavilion, where the
    # two shelves overlap: it has to be shallow enough to read through the water,
    # and far enough from the harbour that its terrace does not overwrite the
    # quay - which is exactly the bug an earlier placement caused.
    "sunken_court": (CENTRE[0] - 40.0, CENTRE[1] + 12.0),
    # the bonded warehouse behind the quay - the door to the customs hall
    "customs_house": (_DESIGN_ANCHORS["harbour_isle"][0] + 7.4,
                      _DESIGN_ANCHORS["harbour_isle"][1] - 1.0),
    "watch_tower": _DESIGN_ANCHORS["outer_northeast"],
    "lighthouse": _DESIGN_ANCHORS["outer_southwest"],
})

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()
}

ANCHORS.update(COAST.ANCHORS)
_DESIGN_ANCHORS.update({k:(x/SCALE,z/SCALE) for k,(x,z) in ANCHORS.items()})

SPAWN = ANCHORS["harbour_isle"]
SPAWN_PLAZA = ANCHORS["crown_plaza"]
SPAWN_GARDEN = ANCHORS["garden_isle"]


def _route(*points) -> np.ndarray:
    return np.asarray([(x * SCALE, z * SCALE) for x, z in points], dtype=np.float64)


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


# ------------------------------------------------------------- causeways
# Every causeway is a spoke from the crown isle to a pavilion islet, plus a
# partial outer ring. These are the *routes*; the bridge geometry that spans the
# open water between islands is built in populate.py. The terrain only needs to
# know where they land, so it can flatten a landing and mark it as built.
CAUSEWAYS: dict[str, np.ndarray] = {}
CAUSEWAY_ENDS: dict[str, tuple[str, str]] = {}
"""Which two islands each causeway joins.

Kept beside the routes because the population pass needs the *islands*, not just
the polyline: a causeway spans the open water between two island edges, so its
length and its deck level come from the island geometry at each end.
"""


def _causeway(name: str, a: str, b: str) -> None:
    CAUSEWAYS[name] = _route(_design(a), _design(b))
    CAUSEWAY_ENDS[name] = (a, b)


for _name in _INNER_NAMES:
    _causeway(f"spoke_{_name}", "crown_isle", _name)
for _i, _name in enumerate(_INNER_NAMES):
    _next = _INNER_NAMES[(_i + 1) % len(_INNER_NAMES)]
    _causeway(f"ring_{_name}_{_next}", _name, _next)
for _inner_name, _outer_name in (("pavilion_east", "outer_east"),
                                 ("pavilion_southeast", "outer_southeast"),
                                 ("pavilion_south", "outer_south"),
                                 ("pavilion_west", "outer_west"),
                                 ("pavilion_northwest", "outer_northwest"),
                                 ("pavilion_north", "outer_north"),
                                 ("harbour_isle", "outer_southwest"),
                                 ("pavilion_northeast", "outer_northeast")):
    _causeway(f"reach_{_outer_name}", _inner_name, _outer_name)

# The ring of open water between the crown isle and its pavilions. Sized to sit
# outside the crown isle's own radius (30) and inside the pavilion shelves, so
# it separates the centre from the ring without cutting into either.
MOAT_RADIUS = 37.0
MOAT_WIDTH = 8.0


def _ring_route(centre, radius, count) -> np.ndarray:
    """A closed ring as a polyline, in world metres."""
    points = _ring(centre, radius, count)
    points.append(points[0])
    return np.asarray([(x * SCALE, z * SCALE) for x, z in points], dtype=np.float64)


def _approach_route(gap_degrees: float, entry) -> np.ndarray:
    """A navigable channel from open sea into the moat, through a ring gap.

    Aimed at the midpoint between two pavilion islets rather than at an islet,
    so the approach never cuts the ground out from under a pavilion.
    """
    angle = math.radians(gap_degrees)
    direction = (math.cos(angle), math.sin(angle))
    gap = (CENTRE[0] + INNER_RADIUS * direction[0],
           CENTRE[1] + INNER_RADIUS * direction[1])
    mouth = (CENTRE[0] + MOAT_RADIUS * direction[0],
             CENTRE[1] + MOAT_RADIUS * direction[1])
    midway = ((entry[0] + gap[0]) * 0.5, (entry[1] + gap[1]) * 0.5)
    return _route(entry, midway, gap, mouth)


# Clearance from sea level to the underside of a causeway deck. Boats pass under
# these in the concept, so the deck cannot simply skim the water.
CAUSEWAY_CLEARANCE = 3.4
# The waterline a landing is measured against - the same bar the landing apron
# uses, so a span ends where the apron begins.
CAUSEWAY_SHORE = SEA_LEVEL + 0.4
# How far a deck runs back onto each landing, so it sits *on* the ground rather
# than beside it. Short: at four metres, with the span rounded up to its length
# class on top, the decks ran ten metres up onto the paving and read as roads
# with a bridge in the middle rather than as bridges.
CAUSEWAY_OVERLAP = 1.6
# The steepest a deck is built. A stone bridge takes up a metre or two between
# two islands over its own length and still reads as architecture; past this it
# reads as a ramp, so the deck goes level at the higher landing instead and the
# lower bridgehead takes the difference.
CAUSEWAY_GRADE = 0.09
# How far inboard of a landing the bridgehead is graded, and the width of that
# ramp. A deck that slopes meets each shore at that shore's own height, so this
# only has to carry the last of the difference - the clearance a deck keeps
# over the water where a landing is lower than that - rather than the whole
# drop between two islands.
CAUSEWAY_RAMP = 8.0
# Water this wide, crossed in a straight line, ends an island. Anything shorter
# is a puddle in the shore, not the lagoon, and a span that stopped at one would
# land in the shallows.
CAUSEWAY_CHANNEL = 5.0


def _shore_along(t, origin, direction, limit: float) -> float:
    """How far from `origin` the island's ground reaches before the water.

    Walks out along the route and returns the last point standing above the
    waterline before the first real stretch of water. The island's nominal
    radius will not do: it is the radius of the island's *core*, and the
    sculpted ground has fallen to the lagoon well inside it - by up to ten
    metres, which is how eight causeways came to end offshore.
    """
    shore = 0.0
    wet = 0.0
    step = 1.0
    distance = 0.0
    while distance <= limit:
        height = float(t.height_at(origin[0] + direction[0] * distance,
                                   origin[1] + direction[1] * distance))
        if height > CAUSEWAY_SHORE:
            shore = distance
            wet = 0.0
        else:
            wet += step
            if wet >= CAUSEWAY_CHANNEL and shore > 0.0:
                break
        distance += step
    return shore


def causeway_span(t, name: str):
    """(the two ends of a causeway's built span), in world metres, or None.

    A route runs island centre to island centre; the span only crosses the open
    water between them, from one shoreline to the other with a short overlap
    onto each landing.
    """
    if hasattr(t, "_crown_spans") and name in t._crown_spans:
        return t._crown_spans[name]
    a_name, b_name = CAUSEWAY_ENDS[name]
    a = ISLAND_GEOM[a_name]["centre"]
    b = ISLAND_GEOM[b_name]["centre"]
    delta = (b[0] - a[0], b[1] - a[1])
    length = math.hypot(delta[0], delta[1])
    if length < 1e-6:
        return None
    unit = (delta[0] / length, delta[1] / length)
    start = max(0.0, _shore_along(t, a, unit, length) - CAUSEWAY_OVERLAP)
    end = min(length, length - _shore_along(t, b, (-unit[0], -unit[1]), length) + CAUSEWAY_OVERLAP)
    if end - start < 8.0:
        return None                       # the islands already touch
    return ((a[0] + unit[0] * start, a[1] + unit[1] * start),
            (a[0] + unit[0] * end, a[1] + unit[1] * end))


def _causeway_landfall(span, index: int) -> tuple[float, float]:
    """The point a causeway's bridgehead runs to, inboard of one of its ends."""
    here = span[index]
    other = span[1 - index]
    dx, dz = here[0] - other[0], here[1] - other[1]
    length = math.hypot(dx, dz) or 1.0
    return (here[0] + dx / length * CAUSEWAY_RAMP,
            here[1] + dz / length * CAUSEWAY_RAMP)


def causeway_deck_ends(t, name: str) -> tuple[float, float]:
    """The level the deck stands at over each of its two landings, in metres.

    A causeway meets each island at that island's own level and takes the
    difference up in its own length, the way a bridge over a river does. Each
    end is floored at a fixed clearance so the span always reads as bridging
    water. Where the two differ by more than the deck may slope the span goes
    level at the higher of them and the lower bridgehead takes the rest.

    Reading the two island *centres* instead, as this did until 2026-09-06,
    gave every spoke the height of the crown isle's acropolis and left it a
    flat slab thirteen metres above both the shores it joined.
    """
    if name in t._crown_deck_ends:
        return t._crown_deck_ends[name]
    span = causeway_span(t, name)
    if span is None:
        level = SEA_LEVEL + CAUSEWAY_CLEARANCE
        out = (level, level)
    else:
        # Each end stands at the level of the ground its bridgehead runs to,
        # not at the waterline it lands on: a shoreline is at sea level by
        # definition, so measuring there gave every deck the same clearance
        # over the water and no causeway ever sloped. A pavilion four metres
        # up and one three metres up should be joined by a deck that takes up
        # the metre between them, which is what a bridge is for.
        ends = [max(float(t.height_at(*_causeway_landfall(span, index))),
                    SEA_LEVEL + CAUSEWAY_CLEARANCE)
                for index in (0, 1)]
        length = math.hypot(span[1][0] - span[0][0], span[1][1] - span[0][1])
        if length > 1e-6 and abs(ends[1] - ends[0]) / length > CAUSEWAY_GRADE:
            level = max(ends)
            out = (level, level)
        else:
            out = (ends[0], ends[1])
    t._crown_deck_ends[name] = out
    return out


def causeway_deck_level(t, name: str) -> float:
    """The middle of a causeway's deck, which is where its mesh is placed."""
    ends = causeway_deck_ends(t, name)
    return (ends[0] + ends[1]) * 0.5


ISLANDS: dict[str, tuple[float, float, float]] = {}
"""name -> (radius, level, shelf_radius, edge) in metres, filled below."""

# name -> (radius, deck level above sea, shelf radius, edge width), all metres.
# The levels are deliberately modest and close together: the concept's drama is
# in its architecture and its water, not in its topography, and a lagoon city on
# tall hills would read as a different painting entirely.
ISLANDS["crown_isle"] = (30.0 * SCALE, 7.6, 46.0 * SCALE, 21.0)
for _name in _INNER_NAMES:
    ISLANDS[_name] = (13.0 * SCALE, 4.4, 22.0 * SCALE, 12.0)
for _name in _OUTER_NAMES:
    ISLANDS[_name] = (9.0 * SCALE, 3.2, 16.0 * SCALE, 9.0)


ISLANDS.update(COAST.ISLANDS)

# Each islet is varied so the ring does not read as eight copies of one disc.
# Resolved once, here, rather than inside `build_terrain`: the population passes
# need the *same* radii and levels the terrain was actually built from, and
# recomputing the jitter in two places is how a pavilion ends up hovering or a
# causeway lands in the water.
ISLAND_GEOM: dict[str, dict] = {}
for _name, (_radius, _level, _shelf, _edge) in ISLANDS.items():
    _j = N.stable_hash(_name) % 1000 / 1000.0
    ISLAND_GEOM[_name] = {
        "centre": ANCHORS[_name],
        "radius": _radius,
        "level": _level,
        "shelf": _shelf,
        "edge": _edge,
    }


# ---------------------------------------------------------------- terrain
def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9, octaves=4,
                        seed=seed)


def _island(t: TER.Terrain, centre: tuple[float, float], radius: float,
            level: float, shelf_radius: float, edge: float, seed: int,
            surface: int = TER.PAVING, axes=(1,1,0)) -> None:
    """Raise one island out of the lagoon, with a shelving apron around it.

    Islands are **plateaus, not domes.** A dome of the right height has almost no
    usable ground on it: everything but the tip exceeds the walkable slope limit,
    and an archipelago built from domes comes out at 5% walkable. The concept's
    islands are built-up platforms held behind retaining walls at the waterline,
    which is a flat top with a defined edge - so that is what this makes.

    The apron matters as much as the island: it is what turns a platform rising
    out of deep water into something a quay, a beach and a moored boat can sit
    against, and it is what the concept's pale turquoise haloes around every
    islet actually are.
    """
    # Elliptical banks follow the prevailing reef, retaining broad shelves.
    saved_x,saved_z=t.gx,t.gz
    sx,sz,yaw=axes
    dx,dz=t.gx-centre[0],t.gz-centre[1]
    t.gx=centre[0]+(dx*math.cos(yaw)-dz*math.sin(yaw))/sx
    t.gz=centre[1]+(dx*math.sin(yaw)+dz*math.cos(yaw))/sz
    # the shelf first: a broad shallow apron lifted off the lagoon floor
    t.add_dome(centre, shelf_radius, abs(LAGOON_FLOOR - SHALLOWS), power=1.35,
               noise_seed=seed + 3, noise_amount=0.20)
    # then the island proper, as an absolute flat level with an organic edge
    t.plateau(centre, radius, level, edge=edge, surface=surface,
              seed=seed + 7, irregular=0.19)
    t.gx,t.gz=saved_x,saved_z


def build_terrain(seed: int = 20260828) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # 1. the lagoon floor: a broad shallow basin, not a flat plane
    t.height += LAGOON_FLOOR
    t.base_noise(1.15, 0.0140, seed=seed, octaves=5, warp=1.15)
    t.base_noise(0.42, 0.055, seed=seed + 17, octaves=4)

    # 2. the deep water. The concept is shallow turquoise almost everywhere, with
    #    a darker ring of open water separating the crowned centre from its ring
    #    of pavilions, and two navigable approaches reaching that ring from the
    #    open sea. Routed deliberately *between* the islands: an earlier version
    #    ran a channel straight through the middle and drowned the crown isle.
    t.carve_channel(_ring_route(CENTRE, MOAT_RADIUS, 64),
                    MOAT_WIDTH * SCALE, abs(CHANNEL_FLOOR - LAGOON_FLOOR),
                    bank=2.0, seed=seed + 31)
    for label, gap_degrees, entry in (("southwest", 157.5, (-58.0, 34.0)),
                                      ("southeast", 67.5, (128.0, 46.0))):
        t.carve_channel(_approach_route(gap_degrees, entry),
                        11.0 * SCALE, abs(CHANNEL_FLOOR - LAGOON_FLOOR) * 0.82,
                        bank=2.2, seed=seed + N.stable_hash(label) % 71)

    # 3. the islands
    for name, geom in ISLAND_GEOM.items():
        # Every island's default ground is planted, not paved. Paving whole
        # islands made the aerial read as one continuous white slab: in the
        # concept the pale stone is the *buildings and their plazas*, and the
        # ground between them is green. Paving is therefore applied by the
        # terraces in `apply_built_ground`, where there is actually something
        # built, and nowhere else.
        surface = TER.MEADOW
        _island(t, geom["centre"], geom["radius"], geom["level"],
                geom["shelf"], geom["edge"],
                seed + N.stable_hash(name) % 211, surface=surface,
                axes=COAST.SHORE_AXES.get(name,(1,1,0)))

    # 4. the sunken court of panel 7 sits in its own shallow pan, so the tiled
    #    platform reads through clear water instead of vanishing into the dark.
    t.add_dome(ANCHORS["sunken_court"], 15.0 * SCALE, 2.6, power=1.4)

    # 5. No rim wall. Amberwood closes its world with mountain walls because it
    #    is land; Crownwater's horizon is open water, and a raised rim outside
    #    the playable footprint reads from any elevated camera as a dark slab
    #    floating at the map edge - which is exactly how the first in-client
    #    aerial came back. The world is closed instead by the collision grid:
    #    water is not walkable, and the lagoon floor still grounds every tile,
    #    so nothing reaches a void without a wall being there.

    # a barrier reef just under the surface around the outer edge: it breaks the
    # empty water at the map border without putting walkable land there
    edge = np.minimum.reduce([
        t.gx - t.x0, (t.x0 + t.size_x) - t.gx,
        t.gz - t.z0, (t.z0 + t.size_z) - t.gz])
    reef_band = np.clip(1.0 - np.abs(edge - 58.0) / 40.0, 0.0, 1.0)
    reef_noise = N.fbm(t.gx * 0.035, t.gz * 0.035, octaves=4, seed=seed + 53)
    t.height += reef_band * (reef_noise - 0.42) * 5.2

    t.erode(iterations=10, strength=0.24)
    t.smooth(iterations=2, weight=0.32)
    return t


def apply_built_ground(t: TER.Terrain, seed: int = 20260828) -> None:
    """Quays, plazas and causeway landings - the built part of the surface.

    Deliberately runs after `build_terrain`, so every flattened level is taken
    from the sculpted ground rather than assumed, which is what keeps a plaza
    from hovering when the island noise changes.
    """
    # Causeway landings only. A causeway is a *bridge*, not a road: its deck is
    # built geometry spanning open water, so grading the terrain along its whole
    # length is wrong twice over - it drags the lagoon floor up into a ridge, and
    # on the island end it pulls the quay down toward the water it crosses. An
    # earlier version did exactly that and put the harbour quay 2.5 m under.
    # The terrain gets a bridgehead at each end and nothing in between.
    #
    # The bridgehead is a ramp, not a terrace. A deck stands at the higher of
    # its two landings and the lower island meets it several metres down, so a
    # flat apron at the deck's level would leave a wall round it and one at the
    # ground's level would leave a step off the deck. Grading from the deck at
    # the landing to the island's own ground a little inboard gives a walker a
    # way on and off, which is the whole point of a bridge.
    t._crown_deck_ends = {}
    t._crown_spans = {name: causeway_span(t, name) for name in CAUSEWAYS}
    for name in CAUSEWAYS:
        causeway_deck_ends(t, name)
    for name, points in CAUSEWAYS.items():
        span = t._crown_spans[name]
        if span is None:
            continue
        levels = causeway_deck_ends(t, name)
        a_name, b_name = CAUSEWAY_ENDS[name]
        for deck, landing, island in zip(levels, span, (a_name, b_name)):
            centre = ISLAND_GEOM[island]["centre"]
            inboard = (centre[0] - landing[0], centre[1] - landing[1])
            reach = math.hypot(inboard[0], inboard[1])
            if reach < 1e-6:
                continue
            inboard = (inboard[0] / reach, inboard[1] / reach)
            head = (landing[0] + inboard[0] * CAUSEWAY_RAMP,
                    landing[1] + inboard[1] * CAUSEWAY_RAMP)
            ground = float(t.height_at(head[0], head[1]))
            # the ramp starts a little out over the water so the deck's own end
            # rests on it rather than on the slope behind it
            foot = (landing[0] - inboard[0] * CAUSEWAY_OVERLAP * 0.5,
                    landing[1] - inboard[1] * CAUSEWAY_OVERLAP * 0.5)
            RC.grade_road(t,[foot,landing,head],
                          [deck,deck,max(ground,SEA_LEVEL+0.6)],
                          width=5.4,shoulder=3.0,surface=TER.PAVING,clearance=2)
        # keep vegetation and props out from under the span without touching height
        for step in np.linspace(0.0, 1.0, 24):
            point = (span[0][0] + (span[1][0] - span[0][0]) * step,
                     span[0][1] + (span[1][1] - span[0][1]) * step)
            t.mark_blocked_disc(point, 3.2 * LOCAL)

    crown_y = float(t.height_at(*ANCHORS["crown_isle"]))

    # The raised civic precinct fits the full-size basilica and tower. Its
    # garden rests on the local bank; wide shoulders make the descent toward
    # the harbour a usable slope instead of a leftover tall terrace lip.
    t.plateau((96,-92), 40.0, 13.5, edge=20.0,
              surface=TER.PAVING, seed=seed + 61, irregular=0.10)
    crown_y = float(t.height_at(*ANCHORS["crown_isle"]))

    t.terrace(ANCHORS["crown_plaza"], 17.0, crown_y + 0.35,
              surface=TER.PAVING, shoulder=10.0)
    t.rect_terrace(ANCHORS["cathedral"], 22.0, 25.0,
                   crown_y + 1.10, 0.0, TER.PAVING, shoulder=6.0)
    t.terrace(ANCHORS["crown_garden"], 9.0 * LOCAL,
              float(t.height_at(*ANCHORS["crown_garden"])),
              surface=TER.MEADOW, shoulder=5.0)
    t.terrace(ANCHORS["crown_campanile"], 6.0 * LOCAL, crown_y + 0.60,
              surface=TER.PAVING, shoulder=8.0)

    for quay in ("crown_quay_south", "crown_quay_north"):
        t.rect_terrace(ANCHORS[quay], 11.0 * LOCAL, 4.0 * LOCAL,
                       max(float(t.height_at(*ANCHORS[quay])), 1.15), 0.0,
                       TER.PAVING)

    for name in _INNER_NAMES:
        level = float(t.height_at(*ANCHORS[name]))
        t.terrace(ANCHORS[name], 7.0 * LOCAL, level, surface=TER.PAVING)
    for name in _OUTER_NAMES:
        level = float(t.height_at(*ANCHORS[name]))
        t.terrace(ANCHORS[name], 5.0 * LOCAL, level, surface=TER.PAVING)

    harbour_y = float(t.height_at(*ANCHORS["harbour_isle"]))
    t.rect_terrace(ANCHORS["harbour_quay"], 10.0 * LOCAL, 5.0 * LOCAL,
                   max(harbour_y - 0.55, 1.05), 0.35, TER.PAVING)
    t.rect_terrace(ANCHORS["harbour_lamp_walk"], 12.0 * LOCAL, 3.2 * LOCAL,
                   max(harbour_y - 0.30, 1.20), 0.0, TER.PAVING)
    t.terrace(ANCHORS["harbour_market"], 7.0 * LOCAL, harbour_y, surface=TER.PAVING)
    t.rect_terrace(ANCHORS["customs_house"], 11.0 * LOCAL, 13.0 * LOCAL,
                   harbour_y, 0.0, TER.PAVING)

    t.terrace(ANCHORS["garden_fountain"], 8.5 * LOCAL,
              float(t.height_at(*ANCHORS["garden_fountain"])), surface=TER.MEADOW)

    # The sunken court is built ground that happens to be underwater. Its level
    # is authored absolutely rather than read from the terrain, because the whole
    # point of panel 7 is that you can see the tiling through clear water: read
    # from the lagoon floor it lands wherever the noise and the nearest channel
    # happen to put it, which was 8 m down and invisible.
    t.rect_terrace(ANCHORS["sunken_court"], 9.0 * LOCAL, 9.0 * LOCAL,
                   SUNKEN_COURT_LEVEL, 0.0, TER.PAVING)

    apply_civic_plan(t)
    import coastal_population
    coastal_population.prepare(t)
    t.assign_surface_by_rule(sea_level=SEA_LEVEL)
    t.dither_boundaries(seed=seed + 99, amount=0.5)

# Player-scale civic plan, in world metres. The harbour is safe ground; the
# garden and inner shores teach gathering before the exposed outer islands.
CIVIC_PATHS = {
    "harbour-court": [(-25,10),(-14,3),(0,0),(12,-12),(26,-26)],
    "quay-apron": [(0,0),(5,-18),(14,-22),(30,-22)],
    "customs-race": [(0,0),(7,8),(12,8)],
    "basilica-procession": [(42,-40),(60,-49),(78,-60),(78,-72)],
    "undercroft-turn": [(78,-60),(100,-65),(103,-73)],
    "bell-court": [(103,-73),(118,-92),(126,-105),(126,-110)],
}
DOORS = dict(COAST.DOORS)
CONTENT_LAYOUT = {
    "services": [
        {"role":"information","position":[-5,4.5,-2]},
        {"role":"storage","position":[-10,4.5,9]},
        {"role":"crafting_station","position":[-20,4.5,9]},
        {"role":"training","position":[-20,4.5,-4]},
    ],
    "npcs": {
        "Maelis":[-3,4.5,4], "Daro Pell":[-25,4.5,4],
        "Basilica Sexton Oren Vale":[122,18,-107],
        "Campanile Ringer Iska":[165,17,-144],
        "Customs Officer Hallon Brace":[5,4.5,12],
        "Salvage Mistress Gero Lund":[31,4.5,-17],
        "Sunken Court Diver Teth-Sa":[-37,4.8,-96],
        "Pavilion Cook Mirren Sallow":[-23,4.5,19],
        "Lamp Ferrier Ottick Rue":[3,4.5,-28],
        "Net-Mender Calla Fisk":[-11,4.5,-22],
        "Pearl Diver Ansil Quen":[266,4,-103],
        "Chartsman Devrin Aisle":[270,4,-125],
        "Drowned-Court Claimant Sesh-Va":[135,17,-103],
        "Tollmaster Quent":[15,4.5,-3],
    },
    "roadClearance": 4.0,
    "wildlife": {
        "mirrorfin_otter":[[-56,-98,22]], "river_otter":[[-18,-211,19]],
        "coralcrest_heron":[[92,58,20]], "bronze_tide_crab":[[246,9,22]],
        "crystal_shore_crab":[[291,-98,19]], "bronze_diving_beetle":[[97,-259,19]],
        "luminous_manta_ray":[[-139,-4,24]], "abyssal_armored_fish":[[14,-365,20]],
        "tidecoil_serpent":[[23,-366,20]], "tidal_crystal_lion":[[361,-207,19]],
        "riverglass_otter":[[-22,-235,16]],
        "river_lizardfolk":[[246,9,22]], "river_capybara":[[-60,-104,24]],
        "azure_axolotl":[[95,63,23]], "river_stone_golem":[[276,-137,23]],
        "sunken_stone_colossus":[[6,-358,23]],
        "tidal_claw_construct":[[-137,-14,24]],
        "crownwater_temple_guard":[[355,-213,24]],
    },
    "harvest": {
        "Reed":[[-57,-98,19],[100,62,17]], "Kelp":[[252,14,18]],
        "Shell":[[287,-97,18]], "Watercress":[[-61,-123,17]],
        "Pearl":[[340,-200,20]], "Salt":[[22,-363,19]],
    },
}

# Exact working posts override the generic migration. Ecology stays near the
# named banks; broad habitat discs allow actual footprint packing off roads.
CONTENT_LAYOUT["npcs"].update({
    "Basilica Sexton Oren Vale":[86,14,-71],
    "Campanile Ringer Iska":[131,14,-108],
    "Sunken Court Diver Teth-Sa":[-28,4.5,-27],
    "Pearl Diver Ansil Quen":[167,4,-69],
    "Chartsman Devrin Aisle":[184,4,-92],
    "Drowned-Court Claimant Sesh-Va":[99,14,-67],
})
CONTENT_LAYOUT["wildlife"]={k:[[round(COAST.map_world(x,z)[0],2),
    round(COAST.map_world(x,z)[1],2),max(17,r*.85)] for x,z,r in v]
    for k,v in CONTENT_LAYOUT["wildlife"].items()}
CONTENT_LAYOUT["harvest"]={k:[[round(COAST.map_world(x,z)[0],2),
    round(COAST.map_world(x,z)[1],2),max(15,r*.85)] for x,z,r in v]
    for k,v in CONTENT_LAYOUT["harvest"].items()}
CONTENT_LAYOUT["requireFullWildlife"]=True
CONTENT_LAYOUT["primaryArrivalOnly"]=True
CONTENT_LAYOUT["wildlife"]["azure_axolotl"]=[[84,48,26],[59,33,22]]
CONTENT_LAYOUT["wildlife"]["barnacle_ogre"]=[[153,90,26]]
CONTENT_LAYOUT["gauntlets"]={"crownwater_gauntlet":{
    "keeperTile":[135,123],"returnTile":[152,122]}}
CONTENT_LAYOUT["landscapeRevision"]="inhabited-crownwater-396-v1"


def apply_civic_plan(t):
    level = float(t.height_at(*SPAWN))
    t.rect_terrace((-15,6), 17, 13, level, 0, TER.PAVING)
    t.rect_terrace((23,8), 12, 10, level, 0, TER.PAVING)
    for name, points in CIVIC_PATHS.items():
        if name == "basilica-procession":
            points = [t._crown_spans["spoke_harbour_isle"][0],*points] if t._crown_spans["spoke_harbour_isle"] else points
        heights = [float(t.height_at(*p)) for p in points]
        if name in ("harbour-court","quay-apron","customs-race"):
            heights = [max(level-0.3,h) for h in heights]
        RC.grade_road(t,points,heights,width=5.5,shoulder=3.5,
                      surface=TER.PAVING,clearance=2)
    for x,z in DOORS.values():
        t.terrace((x,z),4.5,float(t.height_at(x,z)),surface=TER.PAVING)
    for name,span in t._crown_spans.items():
        if span is None:
            continue
        for island,landing in zip(CAUSEWAY_ENDS[name],span):
            if island == "crown_isle":
                continue
            centre = ISLAND_GEOM[island]["centre"]
            dx,dz = centre[0]-landing[0],centre[1]-landing[1]
            distance = math.hypot(dx,dz)
            head = (landing[0]+dx/distance*CAUSEWAY_RAMP,
                    landing[1]+dz/distance*CAUSEWAY_RAMP)
            # Stop at the pavilion's low podium, leaving its floor untouched.
            stop = (centre[0]-dx/distance*8,centre[1]-dz/distance*8)
            if math.hypot(stop[0]-head[0],stop[1]-head[1]) > 2:
                RC.grade_road(t,[head,stop],
                              [float(t.height_at(*head)),float(t.height_at(*stop))],
                              width=4.5,shoulder=2.5,surface=TER.PAVING,clearance=2)
    # The undercroft is entered beside the basilica, never through its solid
    # centre. The two-metre porch lies entirely on this little landing.
    t.rect_terrace((103,-74),4,4,float(t.height_at(103,-73)),0,TER.PAVING)

    # Stone decks sit in shallow rebates at their landings. This only lowers
    # existing land under the exact span; it never raises the lagoon bed.
    # A level bridgehead must not occupy the walking deck's own plane.
    for name,span in t._crown_spans.items():
        if span is None:
            continue
        (ax,az),(bx,bz) = span
        dx,dz = bx-ax,bz-az
        length = math.hypot(dx,dz)
        along = ((t.gx-ax)*dx+(t.gz-az)*dz)/(length*length)
        across = np.abs((t.gx-ax)*dz-(t.gz-az)*dx)/length
        near,far = t._crown_deck_ends[name]
        seat = near+(far-near)*along-0.16
        mask = (along >= 0)&(along <= 1)&(across <= 3.1)
        t.height = np.where(mask,np.minimum(t.height,seat),t.height)
