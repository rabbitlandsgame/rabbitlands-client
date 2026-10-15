"""The authored Amethyst Barrens region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 576-cell grid at one metre per tile with the arrival datum at
server (174, 174), which lands on the Godot origin:

    godot_x = server_x - 174        godot_z = 174 - server_y

so the reachable area is x in [-174, 401] and z in [-401, 174]. The terrain is
cut larger than that on every side, and the surplus is raised or drowned so a
player can never walk off the authored world.

Composition follows the aerial concept (`references/01-concept-aerial-overview.png`):

  * the Glasswarden Observatory on its terrace in the north-west, the armillary
    sphere on its dome the tallest built thing in the region;
  * a great crystal massif erupting from the northern uplands, the pale violet
    shards that dominate the top of the painting;
  * grey mountains closing the north-west and north;
  * sea biting into the north-east and south-east corners, with a dry headland
    of upland rock between them on the east edge;
  * a broad ochre barrens basin filling the middle and south, storm-scoured,
    threaded with resonant roads and veined with amethyst;
  * one river running out of the northern mountains south-east to the sea.

The ten-panel detail board (`references/00-concept-detail-board.png`) is the
player-scale authority and is what the landmark kit is modelled from.
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
# Amethyst Barrens is authored at three times the placeholder's linear extent,
# matching Amberwood: 96x96 ELM tiles (576 height cells) at one metre per tile,
# so movement granularity is unchanged and only the world gets bigger. The
# arrival datum keeps its position relative to the map, at 30% in from the
# south-west, which is server (174, 174).
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# Every anchor, route and watercourse below is written in the placeholder's
# 192 m design space and scaled up here, so the composition of the aerial
# concept is preserved exactly while the world grows.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A courtyard is sized by the buildings standing in it, so those keep a local
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

# The basin floor. Kept deliberately low, because the server's ELM height byte
# is six bits under `elevation = byte * 0.2 - 2.2`, so it can only express
# -2.0 m to 10.4 m. Amberwood's basin sits near 28 m, which saturates that byte
# across almost the whole map and leaves the server with no real elevation at
# all - the client's own verifier skips those cells rather than flagging them.
# The concept here is a flat storm-scoured basin ringed by mountains, so the
# walkable ground can sit inside the encodable band honestly. Ridges and the
# massif still tower over it and still saturate, which is correct: nothing up
# there is walkable.
BASIN_LEVEL = 5.5


# ------------------------------------------------------------- anchors
# Read off the aerial concept on a design-space grid. Design space runs
# x in [-58, 134], z in [-134, 58]; the datum is design (0, 0).
_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    # -- the Glasswarden seat, north-west (panel 2)
    "observatory": (-26.0, -68.0),
    "observatory_court": (-24.0, -48.0),
    "observatory_gate": (-18.0, -36.0),
    "observatory_annexe": (-46.0, -60.0),
    "warden_spire_north": (2.0, -84.0),
    "warden_spire_south": (-2.0, -54.0),

    # -- the crystal massif, north-centre: the painting's tallest feature
    "crystal_massif": (56.0, -110.0),
    "massif_foot": (50.0, -90.0),
    "massif_east": (74.0, -100.0),

    # -- storm ruins (panel 6)
    "ruin_colonnade": (72.0, -56.0),
    "ruin_east_arch": (94.0, -62.0),
    "ruin_basin": (54.0, -24.0),
    "ruin_south": (30.0, 22.0),
    "ruin_west": (-38.0, -6.0),
    "ruin_north": (24.0, -96.0),

    # -- geode caves (panel 4): cut into rising ground, never into the flat
    "geode_north": (-38.0, -102.0),
    "geode_east": (106.0, -34.0),
    "geode_south": (16.0, 38.0),
    "geode_massif": (68.0, -84.0),

    # -- resonant clusters, the worked crystal diggings (panel 7)
    "cluster_court": (46.0, -14.0),
    "cluster_north": (34.0, -78.0),
    "cluster_east": (86.0, -30.0),
    "cluster_south": (48.0, 30.0),
    "cluster_west": (-30.0, -22.0),
    "cluster_far_east": (114.0, 4.0),
    "cluster_mid": (18.0, -14.0),
    "cluster_massif": (62.0, -68.0),
    "cluster_road": (6.0, 6.0),
    "cluster_deep": (78.0, 12.0),

    # -- Glasswarden field stations (panel 8): road-side, tented
    "station_gate": (-8.0, -8.0),
    "station_river": (52.0, -48.0),
    "station_east": (98.0, -6.0),
    "station_south": (26.0, 14.0),
    "station_massif": (57.0, -79.0),
    "station_coast": (108.0, 34.0),

    # -- levitating shard fields (panel 5): the storm set-pieces
    "shards_massif": (58.0, -96.0),
    "shards_basin": (40.0, -40.0),
    "shards_east": (100.0, -46.0),
    "shards_south": (60.0, 40.0),
    "shards_west": (-46.0, -34.0),
    "shards_north": (10.0, -110.0),
    "shards_gate": (-6.0, -8.0),
    "shards_coast": (118.0, -80.0),

    # -- the barrens road furniture
    "watchtower_west": (-49.0, -90.0),
    "watchtower_east": (120.0, -16.0),
    "watchtower_south": (34.0, 46.0),
    "stone_ring": (102.0, 32.0),
    "cliff_overlook": (88.0, -88.0),
    "road_end_east": (116.3333333, 38.0),
    "road_end_south": (10.0, 54.0),
    "arrival": (0.0, 0.0),
    "mirror_gate": (-47.0,-81.0),
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


# ------------------------------------------------------------- routes
# The aerial shows a web, not a tree: roads meet at the observatory gate, at the
# basin diggings and at the eastern ruins. These are the resonant roadways of
# panel 3 - laid stone with crystal grown into the joints.
ROUTES = {
 "arrival_road":_route((0,24),(0,0),(0,-12),(-8,-16),(-16,-24),(-18,-36)),
 "observatory_approach":_route((-18,-36),(-24,-48),(-26,-55),(-26,-61.9)),
 "massif_road":_route((-18,-36),(4,-44),(24,-67),(34,-78),(39,-87),(51,-87),(55,-83),(57,-79)),
 "basin_road":_route((0,0),(18,-6),(36,-9),(44,-21),(49,-32),(63,-32),(68,-46),(69,-51)),
 "survey_road":_route((24,-67),(35,-63),(42,-57),(56,-57),(62,-56),(69,-51),(88,-55),(96,-47),(91,-36),(84,-30)),
 "east_road":_route((84,-30),(82,-18),(79,-8),(89,-1),(103,-2),(115,-8),(120,-9)),
 "river_road":_route((44,-21),(52,-20),(59,-12),(65,-8),(79,-8)),
 "south_road":_route((0,0),(15,11),(24,15),(30,16),(42,24)),
 "coast_road":_route((79,-8),(84,5),(88,12),(102,12),(109,24),(113,28),(116.6666667,39.3333333)),
 "west_road":_route((-16,-24),(-24,-24),(-34,-30),(-42,-38),(-44,-58),(-44,-71),(-47,-81)),
 "north_track":_route((34,-78),(27,-81),(23,-86),(16,-97),(10,-104),(10,-110)),
 "overlook_track":_route((57,-79),(67,-75),(76,-78),(88,-88)),
 "massif_foot_track":_route((57,-79),(63,-88),(57,-96)),
 "annexe_track":_route((-24,-48),(-34,-53),(-43,-58)),
}
BRIDGE_ROUTES = {
 "bridge_massif":_route((39,-87),(51,-87)),
 "bridge_basin":_route((49,-32),(63,-32)),
 "bridge_river_north":_route((42,-57),(56,-57)),
 "bridge_river_south":_route((65,-8),(79,-8)),
 "bridge_east":_route((88,12),(102,12)),
 "bridge_gully_west":_route((-34,-30),(-24,-24)),
 "bridge_gully_north":_route((16,-97),(23,-86)),
}

# One river out of the northern mountains to the south-eastern sea, plus a
# tributary off the north-west range. The bright line running south-east across
# the middle of the aerial is the main course.
STREAMS: dict[str, np.ndarray] = {
    "resonant_river": _route((30.0, -132.0), (38.0, -110.0), (44.0, -88.0),
                             (46.0, -64.0), (54.0, -40.0), (66.0, -18.0),
                             (80.0, 4.0), (96.0, 22.0), (112.0, 40.0),
                             (126.0, 54.0)),
    "mountain_beck": _route((-48.0, -128.0), (-38.0, -110.0), (-24.0, -96.0),
                            (-6.0, -84.0), (10.0, -76.0), (26.0, -74.0),
                            (44.67, -80.0)),
}

# Dry gullies the bridges cross where there is no water.
GULLIES: dict[str, np.ndarray] = {
    "gully_west": _route((-44.0, -44.0), (-32.0, -28.0), (-22.0, -12.0),
                         (-16.0, 6.0)),
    "gully_north": _route((6.0, -100.0), (18.0, -92.0), (30.0, -88.0),
                          (40.0, -90.0)),
    "gully_east": _route((104.0, -22.0), (98.0, 2.0), (94.0, 22.0)),
}


def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9, octaves=4,
                        seed=seed)


def shoreline_x(z):
    """The eastern coast: sea in the two corners, dry headland between them.

    Written in design space and scaled. The base sits outside the playable
    footprint so the middle of the east edge stays land, exactly as the aerial
    shows, and the sea only bites into the north-east and south-east.
    """
    z = np.asarray(z, dtype=np.float64) / SCALE
    base = np.full(np.shape(z), 142.0)
    # the north-eastern bay
    base = base - 50.0 * np.exp(-((z + 122.0) ** 2) / (2.0 * 21.0 ** 2))
    # the south-eastern inlet
    base = base - 34.0 * np.exp(-((z - 46.0) ** 2) / (2.0 * 17.0 ** 2))
    # a rocky headland pushing out between them
    base = base + 6.0 * np.exp(-((z + 30.0) ** 2) / (2.0 * 26.0 ** 2))
    base = base - 3.0 * np.sin(z * 0.085 + 1.1) - 1.5 * np.sin(z * 0.21 + 0.4)
    return base * SCALE


def build_terrain(seed: int = 20260828) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z,
                    TERRAIN_CELL)

    # The basin tilts gently down toward the south-east, which is where the
    # river runs and where the sea is.
    t.add_slope((0.58, 0.81), 0.0092, origin=(0.0, 0.0))
    t.base_noise(2.4, 0.0118, seed=seed, octaves=6, warp=1.30)
    t.base_noise(0.85, 0.049, seed=seed + 17, octaves=4)
    t.height += BASIN_LEVEL

    # -- the closing mountains: north-west corner and the north edge
    t.add_ridge(_route((-58.0, -118.0), (-40.0, -128.0), (-18.0, -134.0),
                       (8.0, -136.0)), 62.0, 30.0, seed=seed + 3, power=1.30)
    t.add_ridge(_route((-58.0, -96.0), (-54.0, -70.0), (-56.0, -40.0),
                       (-58.0, -8.0)), 44.0, 24.0, seed=seed + 5, power=1.35)
    t.add_ridge(_route((60.0, -136.0), (86.0, -130.0), (110.0, -124.0)),
                40.0, 24.0, seed=seed + 7, power=1.40)
    # the eastern headland between the two seas
    t.add_ridge(_route((118.0, -76.0), (124.0, -46.0), (126.0, -16.0),
                       (122.0, 12.0)), 34.0, 22.0, seed=seed + 9, power=1.45)
    # the southern rim
    t.add_ridge(_route((-40.0, 52.0), (10.0, 56.0), (66.0, 54.0), (112.0, 50.0)),
                30.0, 20.0, seed=seed + 11, power=1.40)

    # -- the crystal massif: a rock hill the shards erupt from
    t.add_dome(ANCHORS["crystal_massif"], 34.0 * SCALE, 52.0, power=1.55,
               noise_seed=seed + 13, noise_amount=0.26)
    t.add_dome(ANCHORS["massif_east"], 20.0 * SCALE, 22.0, power=1.7)
    t.add_dome(ANCHORS["cliff_overlook"], 16.0 * SCALE, 18.0, power=1.8)

    # -- the observatory terrace, raised over the basin so it commands it
    t.add_dome(ANCHORS["observatory"], 30.0 * SCALE, 7.5, power=1.6,
               noise_seed=seed + 15, noise_amount=0.14)

    # -- the basin proper: a wide shallow bowl south and east of the seat
    t.add_dome((30.0 * SCALE, -6.0 * SCALE), 56.0 * SCALE, -2.8, power=1.20)
    t.add_dome((74.0 * SCALE, 20.0 * SCALE), 40.0 * SCALE, -1.9, power=1.30)
    t.add_dome((-20.0 * SCALE, 20.0 * SCALE), 34.0 * SCALE, -1.4, power=1.35)

    # -- the sea, east. Applied before the rim so the rim can be trimmed back
    #    out of the water afterwards.
    t.sea_shelf(shoreline_x, depth=22.0, slope=0.26, side="east")

    # -- watercourses and dry gullies
    for name, points in STREAMS.items():
        depth = 2.8 if name == "resonant_river" else 2.0
        width = (4.0 if name == "resonant_river" else 2.8) * SCALE
        t.carve_channel(points, width, depth, bank=2.6,
                        seed=seed + N.stable_hash(name) % 97)
    for name, points in GULLIES.items():
        t.carve_channel(points, 3.4 * SCALE, 4.0, bank=2.0,
                        seed=seed + N.stable_hash(name) % 89)

    t.erode(iterations=16, strength=0.28)
    t.smooth(iterations=2, weight=0.35)
    return t


def close_world(t: TER.Terrain) -> None:
    """Raise a rim in the margin, then let the sea cut back through it.

    `clamp_edges` alone would wall the two sea corners off behind a ridge that
    rises straight out of the water. Re-running the shelf afterwards restores
    them, so the world is closed by mountains where it is land and by open water
    where it is sea.
    """
    t.clamp_edges(MARGIN * 0.9, 46.0)
    t.sea_shelf(shoreline_x, depth=22.0, slope=0.26, side="east")


def apply_built_ground(t: TER.Terrain, seed: int = 20260828) -> None:
    """Roads, terraces and courtyards - the built part of the surface."""
    # every road is a resonant roadway; the tracks are worn barrens
    for name, points in ROUTES.items():
        width = 3.2 * LOCAL
        surface = TER.RESONANT_ROAD
        if name in ("arrival_road", "basin_road", "massif_road"):
            width = 4.4 * LOCAL
        if name in ("overlook_track", "north_track"):
            width = 2.6 * LOCAL
            surface = TER.BARRENS
        t.grade_path(points, width, shoulder=2.2, surface=surface,
                     seed=seed + N.stable_hash(name) % 89, flatten=0.90)

    # the observatory terrace and its forecourt
    obs_y = float(t.height_at(*ANCHORS["observatory"]))
    t.rect_terrace(ANCHORS["observatory"], 17.0 * LOCAL, 14.0 * LOCAL, obs_y, 0.0,
                   TER.BARRENS)
    t.rect_terrace(ANCHORS["observatory_court"], 14.0 * LOCAL, 10.0 * LOCAL,
                   obs_y - 5.0, 0.0, TER.PAVING)
    t.grade_path(_route((-25.0, -58.0), (-25.0, -52.0)), 7.0 * LOCAL,
                 heights=[obs_y - 0.6, obs_y - 5.0], shoulder=1.8,
                 surface=TER.PAVING, seed=seed + 41)
    t.rect_terrace(ANCHORS["observatory_annexe"], 8.0 * LOCAL, 7.0 * LOCAL,
                   obs_y - 2.4, 0.0, TER.BARRENS)

    # the arrival apron: flat, clear, and unambiguously walkable
    t.terrace(ANCHORS["arrival"], 13.0 * LOCAL,
              float(t.height_at(*ANCHORS["arrival"])), surface=TER.RESONANT_ROAD)

    # field stations sit on a graded pad beside their road
    for name in ("station_gate", "station_river", "station_east", "station_south",
                 "station_massif", "station_coast"):
        t.rect_terrace(ANCHORS[name], 7.5 * LOCAL, 6.5 * LOCAL,
                       float(t.height_at(*ANCHORS[name])), 0.0, TER.BARRENS)

    # the diggings are cut into the ground and floored with crystal
    for name in ("cluster_court", "cluster_north", "cluster_east", "cluster_south",
                 "cluster_west", "cluster_far_east", "cluster_mid",
                 "cluster_massif", "cluster_road", "cluster_deep"):
        centre = ANCHORS[name]
        t.terrace(centre, 9.0 * LOCAL, float(t.height_at(*centre)) - 1.6,
                  surface=TER.CRYSTAL_FIELD)

    # ruin platforms
    # The ruins stand on the barrens, not on paving. Using TER.PAVING put
    # Amberwood's grey-brown cobble under them, which reads as a dark slab
    # dropped on the dust; the built stone comes from the ruin meshes.
    for name, half in (("ruin_colonnade", 12.0), ("ruin_east_arch", 9.0),
                       ("ruin_basin", 11.0), ("ruin_south", 9.0),
                       ("ruin_west", 8.0), ("ruin_north", 8.0)):
        centre = ANCHORS[name]
        t.rect_terrace(centre, half * LOCAL, (half - 2.0) * LOCAL,
                       float(t.height_at(*centre)), 0.0, TER.BARRENS)

    t.terrace(ANCHORS["stone_ring"], 10.0 * LOCAL,
              float(t.height_at(*ANCHORS["stone_ring"])), surface=TER.BARRENS)



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

def assign_surfaces(t: TER.Terrain, seed: int = 20260828) -> None:
    """Paint the region's ground classes over everything not authored above."""
    authored = np.isin(t.surface, sorted(TER.AUTHORED_SURFACES))

    # the default ground of the region is barrens dust, not forest floor
    t.surface = np.where(authored, t.surface, TER.BARRENS)

    # crystal grows in fields around the massif, the diggings and the shard
    # sites, and along the resonant river where it has veined the banks
    # Radii are in design-space metres. They were three times this to begin
    # with, which put pale crystal continents over about 40% of the map; the
    # aerial has crystal as scattered accents on an ochre plain, with only the
    # massif reading as a field. Distances between the sites scale with the
    # region, but the sites themselves are sized by what stands in them.
    crystal = np.zeros(t.height.shape, dtype=bool)
    for name, radius in (("crystal_massif", 10.0), ("massif_foot", 4.5),
                         ("massif_east", 4.0), ("shards_massif", 3.2),
                         ("shards_basin", 2.6), ("shards_east", 2.6),
                         ("shards_south", 2.4), ("shards_west", 2.4),
                         ("shards_north", 3.0), ("shards_gate", 2.2),
                         ("shards_coast", 2.4), ("geode_north", 2.8),
                         ("geode_east", 2.8), ("geode_south", 2.4),
                         ("geode_massif", 3.0)):
        cx, cz = ANCHORS[name]
        r = radius * SCALE
        # a strongly modulated edge, so the patch is ragged rather than a disc
        blob = np.hypot(t.gx - cx, t.gz - cz) < r * (
            0.55 + 0.85 * region_noise(t, seed + N.stable_hash(name) % 61, 0.09))
        crystal |= blob
    # the diggings and the roadside are worked ground: crystal follows the river
    # where it has veined the banks, which is what the painting's bright line is
    for points in (ROUTES["basin_road"], STREAMS["resonant_river"]):
        distance = _polyline_distance_xz(t, points)
        vein = distance < 3.2 * SCALE * (
            0.25 + 0.85 * region_noise(t, seed + 313, 0.12))
        crystal |= vein
    t.surface = np.where(crystal & ~authored, TER.CRYSTAL_FIELD, t.surface)

    # storm rock on the steep ground and the high ridges
    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)
    rocky = ((slope > 0.85) | (t.height > BASIN_LEVEL + 13.0)) & ~authored
    t.surface = np.where(rocky, TER.STORM_ROCK, t.surface)

    # shore and shallows around the two sea corners
    shore_band = (t.height < SEA_LEVEL + 1.8) & (t.height > SEA_LEVEL - 7.0) \
        & ~authored
    noise = N.fbm(t.gx * 0.22, t.gz * 0.22, seed=4242)
    t.surface = np.where(shore_band & (noise > 0.30), TER.SHORE, t.surface)
    t.surface = np.where(t.height < SEA_LEVEL - 1.0, TER.SHORE, t.surface)

    # A stronger dither: the surface classes are a hard per-cell choice on a
    # 2 m grid, so a crystal patch with a clean boundary reads in-client as a
    # flat pink polygon laid on the dust. Breaking the edge up, and keeping the
    # patches small, leaves the scattered outcrop meshes to carry the
    # transition - which is how the concept reads at ground level.
    t.dither_boundaries(seed=seed + 7, amount=0.85)
    t.dither_boundaries(seed=seed + 19, amount=0.7)
