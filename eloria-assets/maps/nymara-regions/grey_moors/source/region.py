"""The authored Grey Moors region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side, and the surplus is raised or drowned so a
player can never walk off the authored world.

Composition follows the aerial concept (`references/01-concept-aerial-overview.png`):

  * a low ridge across the north-centre carrying the Great Barrow, crowned with
    a stone court - the one thing in the painting that stands above the rest;
  * rings and avenues of standing stones scattered over the whole moor, densest
    around the barrow ridge and in the middle distance;
  * black bog pools and peat cuttings through the low ground, crossed by
    boardwalks and stone causeways;
  * broken towers on the skyline at the west, north-west, north-east and east,
    which is what gives the flat middle distance a horizon;
  * sea biting into the south-west corner only, behind a low rocky coast;
  * a web of tracks, lit at intervals by waymarkers - the small bright points
    scattered all over the aerial.

The ten-panel detail board (`references/00-concept-detail-board.png`) is the
player-scale authority and is what the kit in `_toolkit/amberwood/moorcraft.py`
is modelled from.

Nothing in this region is tall. That is deliberate and it is what the concept
shows: the drama is horizontal, and the only vertical accents are the menhirs,
the tower stumps and one dead tree.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import terrain as TER

# `Placement` and `RegionBuild` are the handoff between a region's composition
# code and the exporters. They carry no region-specific data, so they live in
# the toolkit rather than in any one region's `region.py`; re-exported here so
# a region reads as one module.
from regionbuild import Placement, RegionBuild  # noqa: F401

# ---------------------------------------------------------------- extents
# Three times the placeholder's linear extent, matching every other production
# region: 96x96 ELM tiles (576 height cells) at one metre per tile, so movement
# granularity is unchanged and only the world gets bigger. The arrival datum
# keeps its position relative to the map, at 30% in from the south-west, which
# is server (174, 174).
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# Every anchor, route and watercourse below is written in the placeholder's
# 192 m design space and scaled up here, so the composition of the aerial
# concept is preserved exactly while the world grows.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A stone circle is sized by the stones standing in it, so those keep a local
# scale - otherwise a bigger map is the same map with everything inflated.
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

# The moor surface. The server's ELM height byte is six bits under
# `elevation = byte * 0.2 - 2.2`, so it can only express -2.0 m to 10.4 m.
# A low wet moor is the one biome in Nymara that fits inside that band
# honestly: the whole walkable surface sits between the bog at about 1.2 m and
# the crown of the Great Barrow at about 9.6 m, so nothing a player can stand
# on saturates the byte. The rim hills outside the playable footprint do
# saturate, which is correct - nothing up there is reachable.
MOOR_LEVEL = 3.6

# Standing water in the bog sits below the moor but above the sea. Pools are
# hollowed to this and given their own skins; the ground around them stays
# walkable, because the concept's bog is ground you wade, with the deep parts
# bridged.
BOG_LEVEL = 1.35


# ------------------------------------------------------------- anchors
# Read off the aerial concept on a design-space grid. Design space runs
# x in [-58, 134], z in [-134, 58]; the datum is design (0, 0). A design point
# maps to the 512 px concept as px = (x + 58) * 512 / 192, py = (z + 134) * 512 / 192.
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # -- the barrow ridge, north-centre: the crowned hill in the painting
    "great_barrow": (38.0, -91.0),
    "great_barrow_court": (38.0, -78.0),
    "barrow_ridge_east": (58.0, -86.0),
    "barrow_ridge_west": (16.0, -94.0),

    # -- the six barrows of the brief; the Great Barrow is the sixth
    "barrow_north": (12.0, -116.0),
    "barrow_east": (78.0, -70.0),
    "barrow_west": (-18.0, -74.0),
    "barrow_south": (46.0, -44.0),
    "barrow_far_east": (104.0, -92.0),

    # -- eight standing-stone groups (panel 3)
    "ring_court": (38.0, -91.0),
    "ring_centre": (28.0, -30.0),
    "ring_north": (2.0, -108.0),
    "ring_east": (88.0, -50.0),
    "ring_west": (-34.0, -50.0),
    "ring_south": (52.0, 18.0),
    "ring_coast": (-14.0, 10.0),
    "ring_far_east": (114.0, -24.0),

    # -- four crypt entrances (panel 5): cut into rising ground, never flat bog
    "crypt_great": (44.0, -97.0),
    "crypt_west": (-30.0, -84.0),
    "crypt_east": (96.0, -66.0),
    "crypt_south": (34.0, 6.0),

    # -- six abandoned crofts (panel 6): low ground, near water, never on a ridge
    "croft_coast": (-24.0, 16.0),
    "croft_south": (40.0, 26.0),
    "croft_west": (-40.0, -20.0),
    "croft_east": (100.0, -6.0),
    "croft_north": (-22.0, -107.3333333333),
    "croft_mid": (60.0, -14.0),

    # -- five ritual shrines (the altar slabs, panel 3)
    "shrine_great": (38.0, -74.0),
    "shrine_bog": (25.0, -15.0),
    "shrine_east": (92.0, -34.0),
    "shrine_coast": (-31.0, 20.0),
    "shrine_north": (16.0, -104.0),

    # -- broken towers: the skyline markers all round the edge of the aerial
    "tower_nw": (-36.0, -119.0),
    "tower_west": (-47.0, -63.0),
    "tower_south_west": (-49.0, -35.0),
    "tower_east": (126.0, -63.0),
    "tower_north_east": (96.0, -122.0),
    "tower_south": (66.0, 40.0),

    # -- peat workings (panel 8)
    "peat_west": (-26.0, -6.0),
    "peat_centre": (48.0, -8.0),
    "peat_north": (6.0, -70.0),
    "peat_east": (86.0, -14.0),

    # -- the dead tree of panel 7, and its lesser company
    "hanged_oak": (22.0, -56.0),
    "thorn_north": (0.0, -92.0),
    "thorn_east": (74.0, -30.0),

    # -- route furniture and the coast
    "moor_gate": (8.0, -10.0),
    # the ways off the moor: north into the Amberwood, south down to the
    # delta, and the jetty on the east shore where the Crownwater boat calls
    "north_gate": (-4.0, -128.0),
    "south_gate": (66.0, 50.0),
    "east_jetty": (-20.0, 29.0),
    "coast_head": (-35.0, 20.0),
    "coast_landing": (-20.0, 24.0),
    "bridge_south": (55.0, 1.0),
    "arrival": (0.0, 0.0),
}

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()
}

SPAWN_DESIGN = (0.0, 0.0)
SPAWN = (0.0, 0.0)


def _route(*points) -> np.ndarray:
    """A polyline written in design space, returned in world metres."""
    return np.array([(x * SCALE, z * SCALE) for x, z in points], dtype=np.float64)


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


# Surveyed paths and their actual wet crossings. Points remain in design
# space so the original landmark composition is easy to compare with the board.
ROUTES = {
    "crown_ascent": _route((40,-78),(48,-79),(54,-86),(51,-94),(45,-98),(41,-94)),
    "haven_road": _route((-52,0),(-43,0),(-33,-2),(-22,-1),(-11,0),(0,0)),
    "arrival_causeway": _route((0,0),(3,-4),(8,-10),(9,-13),(25,-27),(28,-30)),
    "barrow_causeway": _route((28,-30),(30,-34),(33,-51),(33,-60),(38,-69),
                              (38,-74),(38,-80),(38,-82)),
    "coast_road": _route((0,0),(-8,8),(-14,10),(-22,13),(-25,17),(-14,25),(-20,24)),
    "coast_beacon": _route((-22,13),(-30,17),(-31,20),(-35,20)),
    "east_road": _route((28,-30),(46,-30),(57,-20),(58,-10),(79,-26),
                        (86,-38),(86,-48),(96,-64),(124,-61)),
    "north_track": _route((38,-80),(27,-83),(16,-94),(16,-104),(2,-108),
                          (-4,-115),(-8,-120),(-4,-128),(-4,-134)),
    "west_track": _route((8,-10),(-7,-27),(-30,-23),(-37,-22),(-36,-42),
                         (-34,-50),(-45,-59),(-42,-92),(-36,-119)),
    "south_road": _route((0,0),(10,16),(21,16),(44,21),(44,26),(52,18),
                         (63,34),(63,41),(66,50),(66,58)),
    "jetty_track": _route((-14,25),(-20,24),(-20,29)),
    "peat_track": _route((-22,-1),(-23,-6),(-23,-15),(-37,-22)),
    "peat_east_track": _route((58,-10),(51,-5),(80,-9),(94,-5),(97,0),(102,-2),
                              (114,-24)),
    "ridge_track": _route((38,-88),(51,-88),(66,-81),(78,-73),(92,-80),
                          (104,-92),(96,-122)),
    "west_barrow_track": _route((38,-80),(27,-83),(16,-94),(-15,-79),(-30,-82)),
    "bog_track": _route((28,-30),(29,-16),(34,4),(50,-2),(60,4),(66,12),(52,18)),
    "north_peat_track": _route((-15,-79),(1,-69),(13,-82),(27,-83)),
    "east_barrow_track": _route((33,-60),(48,-53),(62,-66),(78,-73)),
}
BOARDWALK_ROUTES = {
    "boardwalk_gate": _route((9,-13),(25,-27)),
    "boardwalk_centre": _route((30,-34),(33,-51)),
    "boardwalk_bog": _route((48,-53),(62,-66)),
    "boardwalk_west": _route((-7,-27),(-30,-23)),
    "boardwalk_north": _route((1,-69),(13,-82)),
    "boardwalk_east": _route((58,-10),(79,-26)),
    "boardwalk_south": _route((21,16),(44,21)),
    "boardwalk_coast": _route((-25,17),(-14,25)),
}
BRIDGE_ROUTES = {
    "bridge_black_drain": _route((50,-2),(60,4)),
    "bridge_moor_gate": _route((3,-4),(8,-10)),
    "bridge_east": _route((80,-9),(94,-5)),
}

# Sluggish drains rather than rivers: this moor sheds its water slowly, south
# and west toward the corner sea. The bright threads on the aerial are these.
STREAMS: dict[str, np.ndarray] = {
    "black_drain": _route((30.0, -104.0), (26.0, -80.0), (24.0, -56.0),
                          (20.0, -32.0), (12.0, -10.0), (2.0, 10.0),
                          (-12.0, 26.0), (-28.0, 40.0)),
    "east_drain": _route((100.0, -80.0), (94.0, -56.0), (86.0, -32.0),
                         (74.0, -10.0), (62.0, 8.0), (48.0, 26.0), (32.0, 44.0)),
    "north_drain": _route((-20.0, -126.0), (-10.0, -110.0), (2.0, -96.0),
                          (10.0, -80.0)),
}

# The bog basins: broad shallow hollows that hold black water. Written as
# (design centre, design radius, depth below the surrounding moor).
BOG_BASINS: tuple[tuple[tuple[float, float], float, float], ...] = (
    ((16.0, -18.0), 17.0, 2.5),
    ((28.0, -40.0), 13.0, 2.2),
    ((-18.0, -26.0), 14.0, 2.3),
    ((8.0, -74.0), 12.0, 2.0),
    ((70.0, -18.0), 15.0, 2.4),
    ((34.0, 16.0), 13.0, 2.1),
    ((-16.0, 24.0), 11.0, 1.9),
    ((92.0, -46.0), 12.0, 2.0),
    ((56.0, -60.0), 10.0, 1.8),
    ((-36.0, -60.0), 11.0, 2.0),
    ((108.0, -8.0), 12.0, 2.2),
    ((48.0, 36.0), 10.0, 1.9),
)


def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9, octaves=4,
                        seed=seed)


def shoreline_x(z):
    """The south-west coast: sea in that corner only, land everywhere else.

    Written in design space and scaled. The base sits far west of the terrain
    for most of the map, so `sea_shelf` finds nothing to drown; a single broad
    Gaussian centred in the south brings the shoreline east into the corner,
    which is the only place the aerial shows water.
    """
    z = np.asarray(z, dtype=np.float64) / SCALE
    # Wider and reaching further inland than the first pass, which put only
    # 2.6% of the playable area under water and left the "coastal panorama"
    # looking down a drain channel. The concept gives the south-west corner a
    # real bay - a broad teal wedge, not an inlet.
    bay = np.exp(-((z - 40.0) ** 2) / (2.0 * 34.0 ** 2))
    base = -420.0 + 436.0 * bay
    # a rocky, ragged edge rather than a drawn curve
    base = base + 4.5 * np.sin(z * 0.115 + 0.7) + 2.0 * np.sin(z * 0.27 + 1.9)
    return base * SCALE


def build_terrain(seed: int = 20260829) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # The moor tilts very gently down toward the south-west, which is where the
    # drains run and where the sea is. Shallower than any other region: this is
    # a plain, and the aerial reads as one.
    t.add_slope((-0.62, 0.78), 0.0055, origin=(0.0, 0.0))
    t.base_noise(1.55, 0.0102, seed=seed, octaves=6, warp=1.15)
    t.base_noise(0.62, 0.041, seed=seed + 17, octaves=4)
    t.height += MOOR_LEVEL

    # -- the barrow ridge: the one piece of relief in the middle of the map.
    #    Long and low, running roughly east-west across the north-centre.
    t.add_ridge(_route((4.0, -98.0), (24.0, -94.0), (44.0, -90.0), (66.0, -86.0),
                       (86.0, -84.0)), 4.6, 46.0, seed=seed + 3, power=1.15)

    # Low open moor continues outside the served rectangle. Isolated knolls
    # give tower ruins a skyline; there is no artificial perimeter ridge.
    # -- the barrows themselves are TERRAIN, not meshes: the mound has to be
    #    ground the client's downward ray can hit, or a character walks through
    #    the hill. Only the portal stonework is geometry.
    for name, radius, height in BARROW_MOUNDS:
        t.add_dome(ANCHORS[name], radius * LOCAL, height, power=1.45,
                   noise_seed=seed + N.stable_hash(name) % 71, noise_amount=0.16)

    # -- the coastal headland the shrine stands on, south-west
    t.add_dome(ANCHORS["coast_head"], 15.0 * LOCAL, 7.5, power=1.6,
               noise_seed=seed + 23, noise_amount=0.22)
    t.add_dome(ANCHORS["tower_south_west"], 12.0 * LOCAL, 5.0, power=1.7)

    # -- rises under the towers, so they stand on something
    for name, height in (("tower_nw", 6.5), ("tower_west", 5.5),
                         ("tower_east", 6.0), ("tower_north_east", 6.5),
                         ("tower_south", 5.0)):
        t.add_dome(ANCHORS[name], 13.0 * LOCAL, height, power=1.7)

    # -- the bog basins: broad hollows the black water sits in
    for (cx, cz), radius, depth in BOG_BASINS:
        t.add_dome((cx * SCALE, cz * SCALE), radius * SCALE, -depth, power=1.10)

    # -- the sea, south-west. Applied before the rim so the rim can be trimmed
    #    back out of the water afterwards.
    t.sea_shelf(shoreline_x, depth=16.0, slope=0.22, side="west")

    # -- drains. Shallow and wide: these are moor drains, not river valleys.
    for name, points in STREAMS.items():
        t.carve_channel(points, 3.2 * SCALE, 1.5, bank=1.8,
                        seed=seed + N.stable_hash(name) % 97)

    t.erode(iterations=12, strength=0.22)
    t.smooth(iterations=3, weight=0.40)
    t._moor_pool_levels = [float(t.height_at(cx*SCALE,cz*SCALE))+depth*0.42
                           for (cx,cz),radius,depth in BOG_BASINS]
    return t


# (anchor, design radius, height) for every mound raised into the terrain.
BARROW_MOUNDS: tuple[tuple[str, float, float], ...] = (
    ("great_barrow", 24.0, 12.0),
    ("barrow_north", 11.0, 3.4),
    ("barrow_east", 12.0, 3.8),
    ("barrow_west", 11.0, 3.5),
    ("barrow_south", 10.0, 3.2),
    ("barrow_far_east", 12.0, 3.6),
    ("barrow_ridge_east", 9.0, 2.8),
    ("barrow_ridge_west", 9.0, 2.6),
)


def close_world(t: TER.Terrain) -> None:
    """Raise a rim in the margin, then let the sea cut back through it.

    `clamp_edges` alone would wall the sea corner off behind a ridge rising
    straight out of the water. Re-running the shelf afterwards restores it, so
    the world is closed by higher moor where it is land and by open water where
    it is sea.
    """
    # 30 m of wall inside a 27 m margin read as a sheer stepped cliff standing
    # at the edge of a flat moor. Lower, and left to the distant backdrop and
    # the fog to close the horizon, which is how the concept ends its world.
    # No closing wall: the authored moor and shoreline continue into the margin.
    t.sea_shelf(shoreline_x, depth=16.0, slope=0.22, side="west")


def apply_built_ground(t: TER.Terrain, seed: int = 20260829) -> None:
    """Causeways, barrow crowns, peat cuttings - the worked part of the surface."""
    # The causeways of panel 1 are laid stone; the rest are worn moor tracks.
    laid = {"arrival_causeway", "barrow_causeway", "coast_road", "east_road"}
    for name, points in ROUTES.items():
        if name in laid:
            width, surface = 2.1 * LOCAL, TER.CAUSEWAY
        else:
            width, surface = 2.2 * LOCAL, TER.MOOR_TRACK
        t.grade_path(points, width, shoulder=1.4, surface=surface,
                     seed=seed + N.stable_hash(name) % 89, flatten=0.82)

    # The Great Barrow's crown: a flat court on top of the mound, which is what
    # the aerial's crowned hill is.
    crown_y = float(t.height_at(*ANCHORS["great_barrow"]))
    t.plateau(ANCHORS["great_barrow"], 37.0, crown_y, edge=21.0,
              surface=TER.BARROW_TURF, irregular=0.0)
    court_y = float(t.height_at(*ANCHORS["great_barrow_court"]))
    t.plateau(ANCHORS["great_barrow_court"], 8.0, court_y, edge=4.0,
              surface=TER.CAUSEWAY, irregular=0.0)

    # The lesser barrows keep their turf but get a level top to stand on.
    for name, radius, _height in BARROW_MOUNDS[1:]:
        centre = ANCHORS[name]
        t.terrace(centre, radius * LOCAL * 0.40, float(t.height_at(*centre)),
                  surface=TER.BARROW_TURF)

    # Stone rings stand on a levelled floor, or half the ring is buried.
    for name in ("ring_court", "ring_centre", "ring_north", "ring_east",
                 "ring_west", "ring_south", "ring_coast", "ring_far_east"):
        centre = ANCHORS[name]
        t.terrace(centre, 8.5 * LOCAL, float(t.height_at(*centre)),
                  surface=TER.HEATHER_MOOR)

    # Peat cuttings are cut down into the moor and floored with bare peat.
    for name in ("peat_west", "peat_centre", "peat_north", "peat_east"):
        centre = ANCHORS[name]
        t.rect_terrace(centre, 9.0 * LOCAL, 7.0 * LOCAL,
                       float(t.height_at(*centre)) - 1.1, 0.0, TER.PEAT_BOG)

    # Crofts sit on a levelled yard, as a croft does.
    for name in ("croft_coast", "croft_south", "croft_west", "croft_east",
                 "croft_north", "croft_mid"):
        centre = ANCHORS[name]
        t.rect_terrace(centre, 7.0 * LOCAL, 6.0 * LOCAL,
                       float(t.height_at(*centre)), 0.0, TER.MOOR_TRACK)

    # Shrines get a small flat apron.
    for name in ("shrine_great", "shrine_bog", "shrine_east", "shrine_coast",
                 "shrine_north"):
        centre = ANCHORS[name]
        t.terrace(centre, 5.0 * LOCAL, float(t.height_at(*centre)),
                  surface=TER.CAUSEWAY)

    # The arrival apron: flat, clear, and unambiguously walkable.
    t.terrace(ANCHORS["arrival"], 7.5 * LOCAL,
              float(t.height_at(*ANCHORS["arrival"])), surface=TER.CAUSEWAY)


def _polyline_distance_xz(t: TER.Terrain, points: np.ndarray) -> np.ndarray:
    """Distance from every terrain cell to a polyline, in world metres."""
    best = np.full(t.gx.shape, np.inf)
    pts = np.asarray(points, dtype=np.float64)
    for index in range(len(pts) - 1):
        ax, az = pts[index]
        bx, bz = pts[index + 1]
        dx, dz = bx - ax, bz - az
        length_sq = dx * dx + dz * dz
        if length_sq < 1e-9:
            continue
        u = np.clip(((t.gx - ax) * dx + (t.gz - az) * dz) / length_sq, 0.0, 1.0)
        best = np.minimum(best, np.hypot(t.gx - (ax + u * dx),
                                         t.gz - (az + u * dz)))
    return best


def assign_surfaces(t: TER.Terrain, seed: int = 20260829) -> None:
    """Paint the region's ground classes over everything not authored above."""
    authored = np.isin(t.surface, sorted(TER.AUTHORED_SURFACES))

    # The default ground of the region is heather moor, not forest floor.
    t.surface = np.where(authored, t.surface, TER.HEATHER_MOOR)

    # Peat bog fills the hollows and follows the drains. Driven by height
    # relative to the local moor rather than by an absolute band, because the
    # moor itself tilts and an absolute band would put bog along one edge.
    wet = np.zeros(t.height.shape, dtype=bool)
    for (cx, cz), radius, _depth in BOG_BASINS:
        r = radius * SCALE
        distance = np.hypot(t.gx - cx * SCALE, t.gz - cz * SCALE)
        # a ragged edge, so a basin is not a disc of a different colour
        wet |= distance < r * (0.60 + 0.80 * region_noise(
            t, seed + N.stable_hash(f"bog{cx}{cz}") % 61, 0.075))
    for name, points in STREAMS.items():
        distance = _polyline_distance_xz(t, points)
        wet |= distance < 5.0 * SCALE * (
            0.30 + 0.80 * region_noise(t, seed + N.stable_hash(name) % 53, 0.10))
    # anything genuinely low and flat is bog whether or not it was authored as one
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)
    wet |= (t.height < MOOR_LEVEL - 1.5) & (slope < 0.10) & (t.height > SEA_LEVEL + 0.6)
    t.surface = np.where(wet & ~authored, TER.PEAT_BOG, t.surface)

    # Barrow turf on the mounds, which is greener and closer-cropped than moor.
    for name, radius, _height in BARROW_MOUNDS:
        cx, cz = ANCHORS[name]
        distance = np.hypot(t.gx - cx, t.gz - cz)
        mound = distance < radius * LOCAL * 0.92 * (
            0.72 + 0.52 * region_noise(t, seed + N.stable_hash(name) % 47, 0.09))
        t.surface = np.where(mound & ~authored, TER.BARROW_TURF, t.surface)

    # Rock on the steep ground, the rim and the coastal cliffs.
    rocky = ((slope > 0.90) | (t.height > MOOR_LEVEL + 12.0)) & ~authored
    t.surface = np.where(rocky, TER.ROCK, t.surface)

    # Shore and shallows in the south-west corner.
    shore_band = (t.height < SEA_LEVEL + 1.6) & (t.height > SEA_LEVEL - 6.0) \
        & ~authored
    noise = N.fbm(t.gx * 0.22, t.gz * 0.22, seed=4242)
    t.surface = np.where(shore_band & (noise > 0.28), TER.SHORE, t.surface)
    t.surface = np.where(t.height < SEA_LEVEL - 0.8, TER.SHORE, t.surface)

    # The surface classes are a hard per-cell choice on a 2 m grid, so a bog
    # with a clean boundary reads in-client as a flat black polygon laid on the
    # moor. Breaking the edge up leaves the scrub and pool meshes to carry the
    # transition, which is how the concept reads at ground level.
    # Dither helps when neighbouring classes are close in tone and hurts when
    # they are not: at 0.85 the peat/moor boundary came out as salt-and-pepper
    # rather than as a soft edge. Pulled back now the two materials sit nearer
    # each other.
    t.dither_boundaries(seed=seed + 7, amount=0.55)
    t.dither_boundaries(seed=seed + 19, amount=0.35)
