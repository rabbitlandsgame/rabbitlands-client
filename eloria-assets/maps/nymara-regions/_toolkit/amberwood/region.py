"""The authored Amberwood region plan.

Coordinates are Godot metres, Y up, north toward -Z. The playable footprint is
the server's 192-cell grid at one metre per tile with the arrival datum at
server (58, 58), which lands on the Godot origin:

    godot_x = server_x - 58        godot_z = 58 - server_y

so the reachable area is x in [-58, 133] and z in [-133, 58]. The terrain is cut
larger than that on every side, and the surplus is raised or drowned so a player
can never walk off the authored world.

Composition follows the aerial concept: sea and rugged coast to the west, the
inhabited amber forest and its water-linked settlement through the middle, the
monumental arch on the central axis, and the burnt barren transition in the east.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import mesh as M
from . import noise as N
from . import terrain as TER

# ---------------------------------------------------------------- extents
# Amberwood is authored at three times its original linear extent. The server
# map grows to 96x96 ELM tiles (576 height cells) and keeps one metre per tile,
# so movement granularity is unchanged; only the world gets bigger. The arrival
# datum keeps its position relative to the map, at 30% in from the south-west.
SERVER_ORIGIN = (174.0, 174.0)
SERVER_CELLS = 576
METRES_PER_TILE = 1.0

# Every anchor, route and watercourse below is written in the original 192 m
# design space and scaled up here, so the composition of the aerial concept is
# preserved exactly while the world doubles.
SCALE = 3.0

# Distances between places scale with the region; the places themselves do not.
# A courtyard, a clearing or a terrace is sized by the buildings standing in it,
# so those keep a local scale - otherwise a bigger map is just the same map with
# everything inflated, and the forest is eaten by enormous empty clearings.
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

_DESIGN_ANCHORS: dict[str, tuple[float, float]] = {
    "harbour": (-45.0, 6.0),
    "harbour_village": (-20.0, 12.0),
    "north_cove": (-20.0, -52.0),
    "south_headland": (-24.0, 44.0),
    "coast_waterfall": (-18.0, -22.0),
    "sea_stacks": (-46.0, -8.0),
    "settlement": (10.0, -58.0),
    "settlement_market": (4.0, -50.0),
    "settlement_north": (18.0, -78.0),
    "great_tree": (26.0, -88.0),
    "moot_hall": (-4.0, -64.0),
    "amber_hall": (22.0, -50.0),
    "mill_pool": (-2.0, -44.0),
    "canopy_camp": (22.0, -70.0),
    "hollow_tree": (-26.0, -86.0),
    "old_bridge": (14.0, -49.0),
    "high_bridge": (40.0, -66.0),
    "north_gate": (24.0, -104.0),
    "great_arch": (58.0, -34.0),
    "arch_forecourt": (58.0, -18.0),
    "garden_terrace": (52.0, 10.0),
    "south_gate": (46.0, 40.0),
    "timber_yard": (72.0, 34.0),
    "charcoal_camp": (84.0, 8.0),
    "east_lodge": (88.0, -46.0),
    "hill_hamlet": (108.0, 30.0),
    "east_watchtower": (86.0, -70.0),
    "north_watchtower": (80.0, -112.0),
    "wayshrine": (36.0, -14.0),
    "forest_gate_west": (-6.0, -26.0),
    "forest_gate_east": (74.0, -30.0),
    "ash_flats": (108.0, -14.0),
    "burnt_stand": (116.0, -60.0),
    "east_road_end": (131.0, -22.0),
    "ash_camp": (100.0, -84.0),
}

# --- places added to fill the enlarged region -----------------------------
# These are authored in the same design space and follow the same rules as the
# original composition: settlements on water and roads, industry near its
# resource, ruins in the deep forest, and the burnt country thinning eastward.
_DESIGN_ANCHORS.update({
    "west_cove": (-26.0, -60.0),
    "cove_huts": (-21.0, -57.0),
    "forest_lake": (-15.0, -85.0),
    "lake_lodge": (-6.0, -80.0),
    "deep_grove": (-20.0, -110.0),
    "amber_diggings": (35.0, -95.0),
    "north_hamlet": (30.0, -118.0),
    "ridge_bridge": (52.0, -100.0),
    "hill_shrine": (70.0, -92.0),
    "orchard": (48.0, 30.0),
    "quarry": (75.0, 52.0),
    "south_watch": (-16.0, 52.0),
    "east_hamlet": (100.0, -60.0),
    "old_battle": (115.0, -40.0),
    "ash_tower": (122.0, 12.0),
    "burnt_mill": (94.0, 30.0),
    # --- a third ring of places, added with the move to 576 m ----------
    "far_grove": (-8.0, -124.0),
    "grove_camp": (-2.0, -128.0),
    "sea_arch": (-14.5, -20.0),
    "kelp_landing": (-31.0, 24.0),
    "south_orchard": (16.0, 46.0),
    "beekeeper": (30.0, 34.0),
    "long_meadow": (-4.0, 8.0),
    "stone_ring": (-17.0, -12.0),
    "west_lodge": (-20.0, -76.0),
    "upper_falls": (18.0, -124.0),
    "coppice": (52.0, -122.0),
    "east_grove": (66.0, -60.0),
    "ridge_camp": (74.0, -110.0),
    "boundary_stone": (96.0, -96.0),
    "ash_chapel": (104.0, -74.0),
    "cinder_field": (126.0, -58.0),
    "smoke_vents": (118.0, -8.0),
    "east_quarry": (116.0, 44.0),
    "far_watch": (128.0, 30.0),
})

ANCHORS: dict[str, tuple[float, float]] = {
    name: (x * SCALE, z * SCALE) for name, (x, z) in _DESIGN_ANCHORS.items()}

SPAWN_DESIGN = (0.0, 0.0)
SPAWN = (0.0, 0.0)
SPAWN_HARBOUR = (-24.0 * SCALE, 8.0 * SCALE)
SPAWN_ARCH = (58.0 * SCALE, -22.0 * SCALE)


def _route(*points) -> np.ndarray:
    """Route points are written in design space and scaled to world metres."""
    return np.array([[float(p[0]) * SCALE, float(p[1]) * SCALE] for p in points])


def _design(name: str) -> tuple[float, float]:
    return _DESIGN_ANCHORS[name]


ROUTES: dict[str, np.ndarray] = {
    "coast_road": _route(_design("south_headland"), (-22.0, 30.0),
                         _design("harbour_village"), (-18.0, -6.0),
                         _design("coast_waterfall"), (-22.0, -40.0),
                         _design("north_cove")),
    "harbour_road": _route(_design("harbour_village"), (-10.0, 4.0), (0.0, -2.0),
                           _design("wayshrine")),
    "arrival_road": _route(SPAWN, (8.0, -10.0), (20.0, -14.0), _design("wayshrine"),
                           (46.0, -16.0), _design("arch_forecourt")),
    "settlement_road": _route(_design("wayshrine"), (28.0, -26.0), _design("old_bridge"),
                              _design("settlement_market"), _design("settlement"),
                              _design("settlement_north"), _design("north_gate")),
    "canopy_road": _route(_design("settlement"), _design("canopy_camp"),
                          _design("great_tree"), (34.0, -98.0),
                          _design("north_watchtower")),
    "hollow_road": _route(_design("settlement"), (-2.0, -70.0), (-14.0, -78.0),
                          _design("hollow_tree"), (-36.0, -94.0)),
    "ridge_road": _route(_design("settlement_north"), (30.0, -72.0),
                         _design("high_bridge"), (52.0, -60.0),
                         _design("east_watchtower")),
    "monument_axis": _route(_design("arch_forecourt"), _design("great_arch"),
                            (58.0, -46.0), _design("forest_gate_east"),
                            (80.0, -38.0), _design("east_lodge")),
    "south_road": _route(_design("arch_forecourt"), (56.0, -4.0),
                         _design("garden_terrace"), (50.0, 26.0),
                         _design("south_gate"), (58.0, 48.0)),
    "timber_road": _route(_design("south_gate"), (58.0, 36.0), _design("timber_yard"),
                          (84.0, 30.0), _design("hill_hamlet")),
    "east_road": _route(_design("forest_gate_east"), (86.0, -26.0),
                        _design("ash_flats"), (120.0, -18.0), _design("east_road_end")),
    "charcoal_track": _route(_design("timber_yard"), (80.0, 20.0),
                             _design("charcoal_camp"), (92.0, -4.0),
                             _design("ash_flats")),
    "burnt_track": _route(_design("east_lodge"), (98.0, -56.0), _design("burnt_stand"),
                          (112.0, -76.0), _design("ash_camp")),
    # --- routes serving the places added for the enlarged region ---------
    "cove_road": _route(_design("north_cove"), _design("west_cove"),
                        _design("cove_huts"), (-24.0, -66.0), _design("hollow_tree")),
    "lake_road": _route(_design("hollow_tree"), (-20.0, -76.0), _design("lake_lodge"),
                        (-8.0, -92.0), _design("deep_grove"), (-26.0, -122.0)),
    "diggings_road": _route(_design("great_tree"), _design("amber_diggings"),
                            (32.0, -106.0), _design("north_hamlet")),
    "north_ridge_road": _route(_design("north_hamlet"), (40.0, -112.0),
                               _design("ridge_bridge"), (62.0, -96.0),
                               _design("hill_shrine"), (80.0, -84.0),
                               _design("east_watchtower")),
    "orchard_road": _route(_design("garden_terrace"), (50.0, 20.0), _design("orchard"),
                           (62.0, 42.0), _design("quarry")),
    "south_coast_road": _route(_design("south_headland"), (-20.0, 50.0),
                               _design("south_watch"), (2.0, 54.0), (24.0, 50.0),
                               _design("south_gate")),
    "east_hamlet_road": _route(_design("east_lodge"), (94.0, -52.0),
                               _design("east_hamlet"), (110.0, -50.0),
                               _design("old_battle"), (124.0, -30.0),
                               _design("ash_flats")),
    "ash_tower_road": _route(_design("ash_flats"), (116.0, 0.0), _design("ash_tower"),
                             (112.0, 26.0), _design("burnt_mill"),
                             _design("hill_hamlet")),
    # --- routes added with the move to 576 m ----------------------------
    "far_grove_road": _route(_design("deep_grove"), (-32.0, -120.0),
                             _design("far_grove"), _design("grove_camp"),
                             (-22.0, -142.0)),
    "west_lodge_road": _route(_design("hollow_tree"), _design("west_lodge"),
                              (-38.0, -66.0), _design("west_cove")),
    "stone_ring_road": _route(_design("harbour_village"), (-26.0, -4.0),
                              _design("stone_ring"), (-18.0, -22.0),
                              _design("forest_gate_west")),
    "meadow_road": _route(SPAWN_DESIGN, _design("long_meadow"), (-14.0, 22.0),
                          _design("kelp_landing")),
    "south_orchard_road": _route(_design("south_gate"), (32.0, 44.0),
                                 _design("south_orchard"), _design("beekeeper"),
                                 _design("garden_terrace")),
    "upper_falls_road": _route(_design("north_gate"), _design("upper_falls"),
                               (30.0, -128.0), _design("coppice"),
                               (66.0, -116.0), _design("ridge_camp")),
    "east_grove_road": _route(_design("east_watchtower"), _design("east_grove"),
                              (72.0, -46.0), _design("east_lodge")),
    "boundary_road": _route(_design("ridge_camp"), _design("boundary_stone"),
                            _design("ash_chapel"), (112.0, -66.0),
                            _design("cinder_field")),
    "vent_road": _route(_design("ash_flats"), _design("smoke_vents"),
                        (122.0, 20.0), _design("east_quarry"),
                        _design("far_watch")),
}

# Surveyed circulation, in world metres. Buildings and water own their places;
# cart routes approach the banks and hill benches rather than their centres.
ROUTES.update({name: np.asarray(points,dtype=float) for name,points in {
 "coast_road":[(-60,120),(-55,84),(-60,36),(-43,7),(-24,-30),(-3,-56),(16,-83),(20,-106),(12,-119)],
 "harbour_road":[(-129,24),(-108,24),(-90,24),(-60,36),(-30,12),(0,-6),(40,-30),(80,-38),(108,-42)],
 "settlement_road":[(108,-42),(89,-69),(63,-99),(46,-122),(43,-135),(39,-159),(24,-171),(31,-198),(45,-218),(54,-234),(72,-312)],
 "ridge_road":[(54,-234),(80,-218),(96,-208),(143,-185),(180,-185),(218,-197),(258,-210)],
 "north_ridge_road":[(90,-354),(112,-345),(131,-330),(173,-284),(192,-281),(210,-276),(240,-243),(258,-210)],
 "cove_road":[(12,-119),(-9,-122),(-23,-137),(-40,-151),(-56,-158),(-63,-171),(-65,-191),(-54,-211),(-60,-228),(-67,-243),(-78,-258)],
 "lake_road":[(-78,-258),(-79,-275),(-65,-284),(-40,-287),(-20,-276),(-13,-255),(-18,-240)],
 "far_grove_road":[(-65,-284),(-50,-307),(-43,-323),(-50,-337),(-24,-354),(-24,-372),(-6,-384)],
 "west_lodge_road":[(-78,-258),(-60,-228),(-54,-211),(-63,-171)],
 "stone_ring_road":[(-60,36),(-43,7),(-45,-16),(-51,-36),(-24,-30)],
 "meadow_road":[(0,0),(-12,24),(-34,46),(-60,67),(-68,72),(-91,72)],
 "south_coast_road":[(-60,120),(-40,137),(-13,136),(17,125),(48,125),(87,118),(138,120)],
 "hollow_road":[(24,-171),(10,-182),(-12,-177),(-28,-176),(-28,-187),(-41,-210),(-36,-218),(-56,-234),(-67,-243),(-78,-258)],
 "diggings_road":[(78,-264),(101,-276),(105,-285),(108,-312),(98,-335),(90,-354)],
 "canopy_road":[(31,-198),(53,-199),(61,-205),(68,-225),(69,-245),(78,-251),(90,-263),(101,-276)],
 "timber_road":[(138,120),(168,117),(193,111),(216,102),(246,108),(271,102),(290,99),(324,90)],
 "orchard_road":[(156,50),(141,69),(138,88),(156,104),(193,111),(210,131),(225,147),(237,155)],
}.items()})

STREAMS: dict[str, np.ndarray] = {
    "north_beck": _route((36.0, -126.0), (30.0, -112.0), (24.0, -96.0), (18.0, -80.0),
                         (12.0, -66.0), (6.0, -54.0), (-2.0, -44.0)),
    "mill_race": _route((-2.0, -44.0), (-8.0, -36.0), (-13.0, -28.0),
                        _design("coast_waterfall"), (-24.0, -20.0)),
    "east_brook": _route((66.0, -96.0), (56.0, -84.0), (46.0, -74.0),
                         _design("high_bridge"), (34.0, -60.0), (24.0, -54.0),
                         (12.0, -50.0), (2.0, -46.0)),
    "garden_rill": _route(_design("great_arch"), (56.0, -22.0), (54.0, -6.0),
                          _design("garden_terrace"), (48.0, 22.0), (40.0, 36.0),
                          (28.0, 46.0), (10.0, 52.0)),
    "lake_outfall": _route((-6.0, -112.0), (-12.0, -100.0), _design("forest_lake"),
                           (-22.0, -74.0), (-32.0, -64.0), _design("west_cove")),
    "ash_burn": _route((118.0, -66.0), (110.0, -50.0), _design("old_battle"),
                       (108.0, -20.0), (112.0, 6.0), _design("burnt_mill"),
                       (88.0, 44.0)),
    "upper_beck": _route((26.0, -138.0), _design("upper_falls"), (12.0, -114.0),
                         (14.0, -100.0), (18.0, -80.0)),
    "meadow_brook": _route(_design("long_meadow"), (-12.0, 14.0), (-22.0, 20.0),
                           _design("kelp_landing")),
    "grove_burn": _route(_design("far_grove"), (-36.0, -114.0), (-34.0, -98.0),
                         _design("west_lodge"), (-38.0, -66.0)),
}

# The beck skirts the inhabited bench and collects at the mill pool.
STREAMS["upper_beck"]=np.asarray([(47,-399),(44,-386),(44,-372),(36,-342),
                                   (42,-300),(54,-240)],dtype=float)
STREAMS["north_beck"]=np.asarray([(108,-378),(90,-336),(72,-288),(54,-240),
                                  (19,-215),(-36,-209),(-32,-172),(-28,-149),(-6,-132)],dtype=float)
STREAMS["mill_race"]=np.asarray([(-6,-132),(-20,-132),(-29,-125),(-29,-112),
                                (-30,-96),(-40,-80),(-54,-66),(-76,-60)],dtype=float)
RAVINE = _route((52.0, -80.0), _design("high_bridge"), (30.0, -58.0))
RAVINE_NORTH = _route((38.0, -122.0), _design("ridge_bridge"), (66.0, -88.0))


# Placement and RegionBuild are shared by every region and now live in
# the toolkit's regionbuild module; re-exported here so existing
# imports from amberwood.region keep working.
from regionbuild import Placement, RegionBuild  # noqa: F401


def region_noise(t: TER.Terrain, seed: int, frequency: float = 0.035) -> np.ndarray:
    return N.warped_fbm(t.gx * frequency, t.gz * frequency, warp=0.9, octaves=4, seed=seed)


def shoreline_x(z):
    """Rugged west coast: headlands, coves and a sheltered harbour bay.

    Written in design space and scaled, so the coast keeps its character
    instead of becoming a smooth curve when the region grows.
    """
    z = np.asarray(z, dtype=np.float64) / SCALE
    base = -20.0
    base = base - 9.0 * np.sin(z * 0.055 + 0.6)
    base = base - 4.5 * np.sin(z * 0.145 + 2.1)
    base = base - 2.0 * np.sin(z * 0.31 + 0.3)
    # the sheltered harbour bay, and a second cove to the north
    base = base - 9.5 * np.exp(-((z - 8.0) ** 2) / (2.0 * 11.0 ** 2))
    base = base - 7.0 * np.exp(-((z + 60.0) ** 2) / (2.0 * 9.0 ** 2))
    # a headland between them, and one in the far south
    base = base + 5.5 * np.exp(-((z + 26.0) ** 2) / (2.0 * 7.0 ** 2))
    base = base + 4.5 * np.exp(-((z - 44.0) ** 2) / (2.0 * 8.0 ** 2))
    return base * SCALE


def build_terrain(seed: int = 20260827) -> TER.Terrain:
    t = TER.Terrain(TERRAIN_X0, TERRAIN_Z0, TERRAIN_SIZE_X, TERRAIN_SIZE_Z, TERRAIN_CELL)

    t.add_slope((0.62, -0.78), 0.108, origin=(0.0, 0.0))
    t.base_noise(3.0, 0.008, seed=seed, octaves=3, warp=0.7)
    t.base_noise(0.45, 0.045, seed=seed + 17, octaves=2)
    t.height += 15.0

    t.add_ridge(_route((-30.0, -140.0), (10.0, -134.0), (54.0, -128.0), (96.0, -124.0),
                       (134.0, -132.0)), 46.0, 26.0, seed=seed + 3, power=1.35)
    t.add_ridge(_route((140.0, -120.0), (146.0, -60.0), (142.0, 0.0), (138.0, 44.0)),
                52.0, 22.0, seed=seed + 5, power=1.3)
    t.add_ridge(_route((-40.0, 66.0), (20.0, 72.0), (86.0, 70.0), (140.0, 62.0)),
                34.0, 20.0, seed=seed + 7, power=1.4)
    t.add_ridge(_route((62.0, -108.0), (72.0, -78.0), (78.0, -50.0), (80.0, -18.0)),
                38.0, 11.0, seed=seed + 9, power=1.6)

    t.add_dome(ANCHORS["settlement"], 62.0 * SCALE, 13.0, power=1.5, noise_seed=seed + 11,
               noise_amount=0.22)
    t.add_dome((44.0 * SCALE, -96.0 * SCALE), 40.0 * SCALE, 14.0, power=1.7)
    t.add_dome(ANCHORS["great_tree"], 26.0 * SCALE, 9.0, power=1.8)
    t.add_dome(ANCHORS["great_arch"], 34.0 * SCALE, 7.0, power=1.9)

    # the burnt basin: a wide shallow bowl, flatter and lower than the forest
    t.add_dome(ANCHORS["ash_flats"], 46.0 * SCALE, -9.0, power=1.25)
    t.add_dome((112.0 * SCALE, -66.0 * SCALE), 38.0 * SCALE, -6.5, power=1.35)
    t.add_dome((112.0 * SCALE, 20.0 * SCALE), 34.0 * SCALE, -5.0, power=1.35)

    t.sea_shelf(shoreline_x, depth=20.0, slope=0.24)
    cliff_band = np.clip((t.gx - shoreline_x(t.gz)) / (12.0 * SCALE), 0.0, 1.0)
    coastal = 1.0 - cliff_band
    t.height += coastal * 5.5 * (0.4 + 0.6 * np.clip(
        np.sin(t.gz * 0.09 / SCALE + 1.2) ** 2, 0.0, 1.0))
    # shelving beaches inside the harbour bay and the northern cove
    for centre_z, centre_x, spread in ((8.0, -27.0, 13.0), (-60.0, -24.0, 10.0)):
        bay = np.exp(-((t.gz - centre_z * SCALE) ** 2) / (2.0 * (spread * SCALE) ** 2))
        beach = bay * np.clip(1.0 - np.abs(t.gx - centre_x * SCALE) / (15.0 * SCALE),
                              0.0, 1.0)
        shelf = -0.9 + (t.gx - (centre_x - 7.0) * SCALE) * 0.20 / SCALE
        t.height = t.height * (1.0 - beach * 0.85) + shelf * beach * 0.85

    for name, points in STREAMS.items():
        depth = 3.8 if name == "north_beck" else 2.8
        width = (2.4 if name == "garden_rill" else 3.2) * SCALE
        t.carve_channel(points, width, depth, bank=2.6, seed=seed + N.stable_hash(name) % 97)
    t.carve_channel(RAVINE, 5.0 * SCALE, 10.5, bank=1.9, seed=seed + 23)
    t.carve_channel(RAVINE_NORTH, 4.2 * SCALE, 8.5, bank=1.9, seed=seed + 27)
    # the forest lake basin
    t.add_dome(ANCHORS["forest_lake"], 22.0 * SCALE, -9.0, power=1.15)

    t.erode(iterations=18, strength=0.30)
    t.smooth(iterations=2, weight=0.35)
    return t


def apply_built_ground(t: TER.Terrain, seed: int = 20260827) -> None:
    """Terraces, courtyards and graded roads - the built part of the surface."""
    for name, points in ROUTES.items():
        width = 3.4 * LOCAL
        surface = TER.PATH
        if name in ("arrival_road", "monument_axis", "south_road"):
            width = 4.6 * LOCAL
        if name in ("burnt_track", "charcoal_track"):
            surface = TER.SCORCHED
        t.grade_path(points, width, shoulder=2.1, surface=surface,
                     seed=seed + N.stable_hash(name) % 89, flatten=0.92)

    t.terrace(ANCHORS["settlement_market"], 11.0 * LOCAL,
              float(t.height_at(*ANCHORS["settlement_market"])), surface=TER.PAVING)
    t.rect_terrace(ANCHORS["moot_hall"], 9.5 * LOCAL, 8.0 * LOCAL,
                   float(t.height_at(*ANCHORS["moot_hall"])) + 0.45, 0.15, TER.PAVING)
    t.rect_terrace(ANCHORS["amber_hall"], 8.0 * LOCAL, 7.0 * LOCAL,
                   float(t.height_at(*ANCHORS["amber_hall"])) + 0.30, -0.22, TER.PAVING)
    t.terrace(ANCHORS["settlement"], 8.0 * LOCAL, float(t.height_at(*ANCHORS["settlement"])),
              surface=TER.PAVING)

    arch_y = float(t.height_at(*ANCHORS["great_arch"]))
    t.rect_terrace(ANCHORS["great_arch"], 14.0 * LOCAL, 9.0 * LOCAL, arch_y, 0.0,
                   TER.PAVING)
    t.rect_terrace(ANCHORS["arch_forecourt"], 13.0 * LOCAL, 9.0 * LOCAL, arch_y - 4.2,
                   0.0, TER.PAVING)
    t.grade_path(_route((58.0, -22.0), (58.0, -26.0)), 7.0 * LOCAL,
                 heights=[arch_y - 4.2, arch_y - 0.4], shoulder=1.6,
                 surface=TER.PAVING, seed=seed + 41)

    garden_y = float(t.height_at(*ANCHORS["garden_terrace"]))
    t.rect_terrace(ANCHORS["garden_terrace"], 13.0 * LOCAL, 10.0 * LOCAL, garden_y,
                   0.0, TER.PAVING)
    t.rect_terrace((ANCHORS["garden_terrace"][0], ANCHORS["garden_terrace"][1] + 13.0),
                   10.0 * LOCAL, 4.0 * LOCAL, garden_y - 1.6, 0.0, TER.PAVING)

    t.rect_terrace(ANCHORS["timber_yard"], 12.0 * LOCAL, 9.0 * LOCAL,
                   float(t.height_at(*ANCHORS["timber_yard"])), 0.1, TER.MEADOW)
    t.rect_terrace(ANCHORS["hill_hamlet"], 11.0 * LOCAL, 9.0 * LOCAL,
                   float(t.height_at(*ANCHORS["hill_hamlet"])), -0.15, TER.MEADOW)
    t.rect_terrace(ANCHORS["harbour_village"], 10.0 * LOCAL, 8.0 * LOCAL,
                   max(float(t.height_at(*ANCHORS["harbour_village"])), 3.2), 0.0,
                   TER.PAVING)
    t.rect_terrace(ANCHORS["charcoal_camp"], 8.0 * LOCAL, 7.0 * LOCAL,
                   float(t.height_at(*ANCHORS["charcoal_camp"])), 0.2, TER.SCORCHED)
    t.rect_terrace(ANCHORS["ash_camp"], 7.0 * LOCAL, 6.0 * LOCAL,
                   float(t.height_at(*ANCHORS["ash_camp"])), 0.0, TER.SCORCHED)
    t.terrace(ANCHORS["east_lodge"], 8.0 * LOCAL, float(t.height_at(*ANCHORS["east_lodge"])),
              surface=TER.MEADOW)

    for name, radius in (("mill_pool", 9.0), ("canopy_camp", 8.0), ("wayshrine", 6.0),
                         ("great_tree", 12.0), ("hollow_tree", 10.0),
                         ("settlement_north", 9.0), ("north_gate", 6.0),
                         ("south_gate", 6.0), ("east_watchtower", 6.0),
                         ("north_watchtower", 6.0), ("west_cove", 9.0),
                         ("cove_huts", 7.0), ("forest_lake", 12.0),
                         ("lake_lodge", 7.0), ("deep_grove", 12.0),
                         ("amber_diggings", 9.0), ("north_hamlet", 9.0),
                         ("ridge_bridge", 8.0), ("hill_shrine", 7.0),
                         ("orchard", 10.0), ("quarry", 11.0), ("south_watch", 6.0),
                         ("east_hamlet", 9.0), ("old_battle", 10.0),
                         ("ash_tower", 6.0), ("burnt_mill", 8.0),
                         ("far_grove", 13.0), ("grove_camp", 7.0),
                         ("sea_arch", 7.0), ("kelp_landing", 8.0),
                         ("south_orchard", 11.0), ("beekeeper", 7.0),
                         ("long_meadow", 12.0), ("stone_ring", 9.0),
                         ("west_lodge", 8.0), ("upper_falls", 9.0),
                         ("coppice", 10.0), ("east_grove", 9.0),
                         ("ridge_camp", 7.0), ("boundary_stone", 6.0),
                         ("ash_chapel", 7.0), ("cinder_field", 10.0),
                         ("smoke_vents", 8.0), ("east_quarry", 10.0),
                         ("far_watch", 6.0)):
        t.mark_blocked_disc(ANCHORS[name], radius * LOCAL)

    # built ground for the places added with the enlargement
    for name, half_x, half_z, surface in (
            ("cove_huts", 8.0, 6.0, TER.PAVING),
            ("lake_lodge", 7.0, 6.0, TER.MEADOW),
            ("north_hamlet", 9.0, 7.0, TER.PAVING),
            ("east_hamlet", 9.0, 7.0, TER.PAVING),
            ("orchard", 11.0, 8.0, TER.MEADOW),
            ("quarry", 10.0, 8.0, TER.ROCK),
            ("burnt_mill", 7.0, 6.0, TER.SCORCHED),
            ("old_battle", 9.0, 8.0, TER.SCORCHED),
            ("amber_diggings", 8.0, 6.0, TER.PATH),
            ("grove_camp", 6.0, 5.0, TER.MEADOW),
            ("west_lodge", 7.0, 6.0, TER.MEADOW),
            ("kelp_landing", 7.0, 6.0, TER.SHORE),
            ("south_orchard", 10.0, 8.0, TER.MEADOW),
            ("beekeeper", 7.0, 6.0, TER.MEADOW),
            ("coppice", 9.0, 7.0, TER.MEADOW),
            ("ridge_camp", 7.0, 6.0, TER.PATH),
            ("east_grove", 8.0, 7.0, TER.MEADOW),
            ("ash_chapel", 7.0, 6.0, TER.SCORCHED),
            ("cinder_field", 10.0, 9.0, TER.SCORCHED),
            ("east_quarry", 9.0, 7.0, TER.ROCK),
            ("smoke_vents", 8.0, 7.0, TER.SCORCHED)):
        centre = ANCHORS[name]
        t.rect_terrace(centre, half_x * LOCAL, half_z * LOCAL,
                       float(t.height_at(*centre)), 0.0, surface, shoulder=12.0)

    # the burnt country starts further east than it did, so the forest keeps
    # more of the enlarged region
    ash = np.clip((t.gx - 104.0 * SCALE) / (20.0 * SCALE), 0.0, 1.0)
    ash_mask = (np.clip(ash + (region_noise(t, seed + 61) - 0.5) * 0.55, 0.0, 1.0) > 0.45)
    protected = np.isin(t.surface, [TER.PAVING])
    t.surface = np.where(ash_mask & ~protected, TER.SCORCHED, t.surface)

    meadow = region_noise(t, seed + 73)
    forest = t.surface == TER.FOREST
    t.surface = np.where(forest & (meadow > 0.78) & (t.gx < 96.0 * SCALE),
                         TER.MEADOW, t.surface)

    t.assign_surface_by_rule(SEA_LEVEL)
    t.dither_boundaries(seed=seed + 91, amount=0.5)
    t.clamp_edges(MARGIN * 0.92, 32.0, sides=("east", "north", "south"))
