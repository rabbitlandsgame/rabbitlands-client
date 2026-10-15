"""_continent_v2/export_collision.py on a two-territory fixture.

Two square maps, "west" and "east", meet along continent x 100 on one shared terrain function (as the isles' bakes
are crops of one base): flat ground at 10 m carrying a 0.65 ramp along the diagonal, a 0.66 ramp, a sea inlet and a
wadeable shelf, a walk deck 3 m over its bed and a lake on the west; a solid box, a box on the border, a box whose
body reaches 1.4 m over the border onto the west's own ground, three open (not watertight) wall rings - a house, a
house with a doorway and a parapet round its own deck - a deep and a shallow river and a plateau at 104.8 m
(code 4096) on the east. A third, one-map group stands at -96.8 m and -93.6 m
(codes 64 and 128) under a sea level below them.

The served-grid codec, the sync's package reader and the server's CollisionMap come from the server checkout named
by ELORIA_SERVER_ROOT (the exporter's --server); without it these tests skip.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import frames as F  # noqa: E402
import export_collision as X  # noqa: E402

SERVER = os.environ.get("ELORIA_SERVER_ROOT")
pytestmark = pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout with "
                                                   "eloria/served_grid.py")
CELLS = 72
WEST = F.Frame("west", "West", (34, 34), (CELLS, CELLS), (70.0, 0.0, 30.0))      # lattice x 36, south edge z 64
EAST = F.Frame("east", "East", (34, 34), (CELLS, CELLS), (130.0, 0.0, 30.0))     # lattice x 96, south edge z 64
DECK = (70.0, 80.0, 30.0, 40.0, 13.0)          # continent x0, x1, z0, z1 and the deck's height over a 10 m bed
LAKE = ((50.0, 45.0), (5.0, 4.0), 12.0)        # continent centre, radii, level (2 m over the bed)
BOX = (120.0, 124.0, 10.0, 14.0)
BORDER_BOX = (100.2, 101.8, 54.0, 56.0)
STRADDLE_BOX = (98.6, 101.4, 48.0, 50.0)   # an east placement 1.4 m over the border onto west's own ground
DEEP_RIVER = ((110.0, 46.0), (150.0, 46.0), 4.0, 11.0)        # from, to, width, surface: 1 m deep
SHALLOW_RIVER = ((110.0, 30.0), (150.0, 30.0), 3.0, 10.2)     # 0.2 m deep: wadeable
HOUSE = (104.0, 110.0, 4.0, 10.0)          # four walls, no roof or floor: a Meshy shell
DOORWAY_HOUSE = (104.0, 110.0, 14.0, 20.0)  # the same with a 2.8 m doorway in its south wall
PARAPET = (113.0, 119.0, 4.0, 10.0)        # a 1 m wall round the placement's own deck
HARVEST = (126.5, 20.5)                    # a harvest node on open flat ground, continent metres


def ground(x, z):
    """The shared terrain, continent metres."""
    x = np.asarray(x, float)
    z = np.asarray(z, float)
    h = np.full(np.broadcast(x, z).shape, 10.0)
    ramp = (x >= 44) & (x <= 60) & (z >= 4) & (z <= 20)
    h = np.where(ramp, 10 + 0.65 * ((x - 44) + (z - 4)) / math.sqrt(2), h)       # grade exactly 0.65, diagonal
    steep = (x >= 64) & (x <= 76) & (z >= 4) & (z <= 20)
    h = np.where(steep, 10 + 0.66 * (x - 64), h)
    h = np.where((x >= 84) & (x <= 92) & (z >= 4) & (z <= 12), -2.0, h)          # a sea inlet, 2 m deep
    h = np.where((x >= 84) & (x <= 92) & (z >= 16) & (z <= 24), -0.2, h)         # a shelf, 0.2 m deep
    h = np.where((x >= 140) & (x <= 156) & (z >= 4) & (z <= 16), 104.8, h)       # code 4096
    return h


def terrain(frame, function=ground):
    """A 41 x 41 vertex terrain at 2 m around the frame's centre, sampled from the shared function."""
    origin = (-40.0, -40.0)
    xs = origin[0] + np.arange(41) * 2.0 + frame.translation[0]
    zs = origin[1] + np.arange(41) * 2.0 + frame.translation[2]
    xx, zz = np.meshgrid(xs, zs)
    return function(xx, zz), origin


def up(triangles):
    triangles = np.asarray(triangles, float)
    normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    flip = normal[:, 1] < 0
    triangles[flip] = triangles[flip][:, [0, 2, 1]]
    return triangles


def rectangle(x0, x1, z0, z1, y):
    return up([[[x0, y, z0], [x0, y, z1], [x1, y, z0]], [[x1, y, z0], [x0, y, z1], [x1, y, z1]]])


def box(x0, x1, z0, z1, y0, y1):
    """A closed box, outward faces."""
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1],
                  [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], float)
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return v[np.array(faces)]


def walls(x0, x1, z0, z1, y0, y1, gap=None):
    """Four vertical walls round a rectangle, open top and bottom (so not a closed mesh); gap (xa, xb) leaves a
    doorway in the south (z0) wall."""
    def wall(a, b):
        (ax, az), (bx, bz) = a, b
        return [[[ax, y0, az], [bx, y0, bz], [bx, y1, bz]], [[ax, y0, az], [bx, y1, bz], [ax, y1, az]]]
    south = [((x0, z0), (gap[0], z0)), ((gap[1], z0), (x1, z0))] if gap else [((x0, z0), (x1, z0))]
    sides = south + [((x1, z0), (x1, z1)), ((x1, z1), (x0, z1)), ((x0, z1), (x0, z0))]
    return np.array([t for a, b in sides for t in wall(a, b)], float)


def local(frame, triangles):
    return np.asarray(triangles, float) - np.asarray(frame.translation)


def river(frame, start, end, width, surface):
    tx, _ty, tz = frame.translation
    return {"id": "fixture-river", "points": [{"position": [start[0] - tx, surface, start[1] - tz], "width": width},
                                              {"position": [end[0] - tx, surface, end[1] - tz], "width": width}]}


def territory(frame, polygon, **extra):
    heights, origin = terrain(frame, extra.pop("function", ground))
    return X.Territory(region=frame.region, frame=frame, polygon=polygon, heights=heights, terrain_origin=origin,
                       sources={"snapshotSha256": hashlib.sha256(frame.region.encode()).hexdigest(),
                                "sceneSha256": "0" * 64}, **extra)


def fixture_territories():
    (lx, lz), (rx, rz), level = LAKE
    west = territory(
        WEST, [[40.0, 0.0], [100.0, 0.0], [100.0, 60.0], [40.0, 60.0]],
        lakes=[{"id": "lake", "center": [lx - 70.0, lz - 30.0], "radii": [rx, rz], "level": level}],
        walk=local(WEST, rectangle(*DECK)), spawn=(60.0 - 70.0, 30.0 - 30.0))
    nothing = np.zeros((0, 3, 3))
    parapet_deck = local(EAST, rectangle(*PARAPET, 10.0))
    east = territory(
        EAST, [[100.0, 0.0], [160.0, 0.0], [160.0, 60.0], [100.0, 60.0]],
        rivers=[river(EAST, *DEEP_RIVER), river(EAST, *SHALLOW_RIVER)],
        walk=parapet_deck,
        solids=[("box", [(local(EAST, box(*BOX, 10.0, 13.0)), True)], nothing),
                ("border-box", [(local(EAST, box(*BORDER_BOX, 10.0, 13.0)), True)], nothing),
                ("straddle-box", [(local(EAST, box(*STRADDLE_BOX, 10.0, 13.0)), True)], nothing),
                ("house", [(local(EAST, walls(*HOUSE, 10.0, 13.0)), False)], nothing),
                ("doorway-house", [(local(EAST, walls(*DOORWAY_HOUSE, 10.0, 13.0, gap=(105.6, 108.4))), False)],
                 nothing),
                ("parapet", [(local(EAST, walls(*PARAPET, 10.0, 11.0)), False)], parapet_deck)],
        spawn=(130.0 - 130.0, 22.0 - 30.0),
        harvest_tiles=[EAST.tile_of_continent(*HARVEST)])
    return [west, east]


@pytest.fixture(scope="module")
def codec():
    return X.server_codec(SERVER)


@pytest.fixture(scope="module")
def exported(codec, tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    packages = tmp_path_factory.mktemp("packages")
    report, sidecars = X.run(fixture_territories(), [("east", "west")], codec, out, packages, log=lambda *_: None)
    return {"report": report, "sidecars": sidecars, "out": out, "packages": packages}


def package(exported, region):
    return exported["packages"] / region / "client"


def collision(exported, region):
    data = (package(exported, region) / X.COLLISION_BIN).read_bytes()
    magic, version, _reserved, width, height = struct.unpack_from("<4sHHII", data, 0)
    assert (magic, version) == (b"EWCG", 2)
    return np.frombuffer(data[16:], np.uint8).reshape(height, width)


def served(exported, region, codec):
    grid = codec.served_grid.decode_file((package(exported, region) / X.SERVED_GRID).read_bytes())
    return grid, np.frombuffer(grid.codes, np.uint16).reshape(grid.height, grid.width)


def tile(frame, x, z):
    """The tile of a continent point."""
    return frame.tile_of_continent(x, z)


def code_at(codes, frame, x, z):
    tx, ty = tile(frame, x, z)
    return int(codes[ty, tx])


def collision_map(codec, grid):
    from eloria.collision import CollisionMap
    return CollisionMap.from_grid(grid)


# --- the walk rules ---------------------------------------------------------------------------------------------------

def test_a_deck_three_metres_over_its_bed_is_open_but_its_edge_step_is_refused(exported, codec):
    grid, codes = served(exported, "west", codec)
    x0, x1, z0, z1, y = DECK
    deck = code_at(codes, WEST, x0 + 2.5, z0 + 5.5)
    bed = code_at(codes, WEST, x0 - 2.5, z0 + 5.5)
    assert deck == codec.served_grid.quantise_mm(y * 1000) and bed == codec.served_grid.quantise_mm(10_000)
    assert deck - bed == 60                          # 3 m at 50 mm, against a climb of 20 codes
    edge, outside = tile(WEST, x0 + 0.5, z0 + 5.5), tile(WEST, x0 - 0.5, z0 + 5.5)
    assert codes[edge[1], edge[0]] and codes[outside[1], outside[0]]
    walk = collision_map(codec, grid)
    assert not walk.can_step(*edge, *outside, 2) and not walk.can_step(*outside, *edge, 2)
    assert walk.can_step(*edge, edge[0] + 1, edge[1], 2)        # along the deck
    ac5 = exported["report"]["ac5"]
    assert ac5["legalDeckGroundStepsOver1.05m"] == 0 and ac5["legalStepsOver1.05m"] == 0 and ac5["pass"]
    assert ac5["refusedDeckGroundSteps"] > 0
    # the deck is a step loss: open and step-free reachable from the bed, never served
    patches = exported["report"]["stepLosses"]["largest"]
    assert any(p["map"] == "west" and p["tiles"] == 100 and p["smallestJoinMetres"] == 3.0 for p in patches)


def test_a_065_slope_and_a_09_m_diagonal_are_legal_and_066_is_not(exported, codec):
    grid, codes = served(exported, "west", codec)
    walk = collision_map(codec, grid)
    a = tile(WEST, 50.5, 10.5)
    b = (a[0] + 1, a[1] - 1)                       # one tile east and one south: straight up the gradient
    rise = (int(codes[b[1], b[0]]) - int(codes[a[1], a[0]])) * 0.05
    assert codes[a[1], a[0]] and codes[b[1], b[0]] and 0.85 <= rise <= 1.0
    assert walk.can_step(*a, *b, 2) and walk.can_step(*b, *a, 2)
    for x in np.arange(45.5, 59.5):
        for z in np.arange(5.5, 19.5):
            assert code_at(codes, WEST, x, z), (x, z)
    for x in np.arange(65.5, 75.5):
        for z in np.arange(5.5, 19.5):
            assert code_at(codes, WEST, x, z) == 0, (x, z)


def test_a_lake_blocks(exported, codec):
    _grid, codes = served(exported, "west", codec)
    (cx, cz), (rx, rz), _level = LAKE
    assert code_at(codes, WEST, cx + .5, cz + .5) == 0
    assert code_at(codes, WEST, cx + rx - 1.5, cz + .5) == 0
    assert code_at(codes, WEST, cx + rx + 1.5, cz + .5) != 0
    assert exported["report"]["maps"]["west"]["exportStatistics"]["waterCells"] > 0


def test_the_sea_blocks_deep_water_and_lets_a_shelf_be_waded(exported, codec):
    _grid, codes = served(exported, "west", codec)
    assert all(code_at(codes, WEST, x, z) == 0 for x in (85.5, 88.5, 90.5) for z in (5.5, 8.5, 10.5))
    shelf = code_at(codes, WEST, 88.5, 20.5)
    assert shelf == codec.served_grid.quantise_mm(-200)


def test_a_solid_blocks(exported, codec):
    _grid, codes = served(exported, "east", codec)
    x0, x1, z0, z1 = BOX
    assert all(code_at(codes, EAST, x, z) == 0 for x in np.arange(x0 + .5, x1) for z in np.arange(z0 + .5, z1))
    assert code_at(codes, EAST, x0 - 1.5, z0 + 1.5) and code_at(codes, EAST, x1 + 1.5, z0 + 1.5)
    assert exported["report"]["maps"]["east"]["exportStatistics"]["structuralCells"] >= 64


def test_an_open_shell_blocks_the_ground_it_walls_in(exported, codec):
    """A Meshy house is a shell of walls with no floor or roof (not a closed mesh): its walls alone would leave a
    walkable room inside a ring, so the ground the ring encloses is blocked too."""
    _grid, codes = served(exported, "east", codec)
    x0, x1, z0, z1 = HOUSE
    assert all(code_at(codes, EAST, x, z) == 0 for x in np.arange(x0 + .5, x1) for z in np.arange(z0 + .5, z1))
    assert code_at(codes, EAST, x1 + 1.5, z0 + 2.5) and code_at(codes, EAST, x0 + 2.5, z1 + 1.5)


def test_a_shell_with_a_way_out_or_its_own_deck_inside_stays_open(exported, codec):
    """Ground a doorway lets out of is not walled in, and a placement's own walk surface inside its parapet (a pier or
    causeway deck) stays a walk surface."""
    _grid, codes = served(exported, "east", codec)
    x0, x1, z0, z1 = DOORWAY_HOUSE
    assert all(code_at(codes, EAST, x, z) for x in (106.5, 107.5) for z in (z0 - .5, z0 + .5, z0 + 2.5, z1 - 2.5))
    x0, x1, z0, z1 = PARAPET
    assert all(code_at(codes, EAST, x, z) for x in np.arange(x0 + 1.5, x1 - 1) for z in np.arange(z0 + 1.5, z1 - 1))
    assert code_at(codes, EAST, x0 + .5, z0 + 2.5) == 0                 # the parapet itself still blocks


def test_a_harvest_node_blocks_its_own_tile_and_is_harvested_from_its_ring(exported, codec):
    _grid, codes = served(exported, "east", codec)
    x, z = HARVEST
    assert code_at(codes, EAST, x, z) == 0
    assert all(code_at(codes, EAST, x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz)
    assert exported["report"]["maps"]["east"]["exportStatistics"]["harvestNodeTiles"] == 1


def test_a_solid_tree_blocks_its_trunk_not_its_crown():
    """A leaning palm: a 0.3 m trunk standing 2 m off the model's origin, under a frond crown that droops to 1 m over
    a 3 m radius. Made solid, it blocks the trunk's tile and walks under the fronds."""
    angles = np.linspace(0, 2 * math.pi, 13)[:-1]
    stem = [[[2 + .3 * math.cos(a), y, .3 * math.sin(a)] for a in angles[k:k + 3]] for k in range(0, 10, 3)
            for y in (0.0, 1.0, 2.0, 3.0, 4.0)]
    fronds = [[[2 + r * math.cos(a), 5 - 4 * r / 3, r * math.sin(a)], [2, 5, 0], [2 + r * math.cos(a + .3), 5 - 4 * r / 3,
               r * math.sin(a + .3)]] for a in angles for r in (1.5, 2.5, 3.0)]
    group = X.trunk(np.asarray(stem + fronds, float))
    assert group is not None and len(group) == 1 and group[0][1] is True
    prism = group[0][0]
    assert X.CE.closed_mesh(prism)
    centre = prism.reshape(-1, 3)[:, [0, 2]].mean(axis=0)
    assert abs(centre[0] - 2) < .05 and abs(centre[1]) < .05
    floor = np.zeros((24, 24))                                  # 12 m square, cells centred on -6 + (c + .5) / 2
    blocked = X.CE.structural_mask(group, floor, -6.0, 6.0)
    rows, cols = np.nonzero(blocked)
    xs, zs = -6 + (cols + .5) * X.CELL, 6 - (rows + .5) * X.CELL
    assert len(rows) and np.hypot(xs - 2, zs).max() <= .3 + X.CELL
    assert X.trunk(np.zeros((0, 3, 3))) is None


def test_a_river_ribbon_blocks_and_a_shallow_one_is_waded(exported, codec):
    _grid, codes = served(exported, "east", codec)
    (fx, fz), (tx_, _tz), width, _surface = DEEP_RIVER
    assert all(code_at(codes, EAST, x, fz + dz) == 0 for x in np.arange(fx + .5, tx_) for dz in (-1.5, -.5, .5, 1.5))
    assert code_at(codes, EAST, 130.5, fz + width / 2 + 1.5) and code_at(codes, EAST, 130.5, fz - width / 2 - 1.5)
    (sx, sz), _end, _w, _s = SHALLOW_RIVER
    assert code_at(codes, EAST, 130.5, sz + .5) == codec.served_grid.quantise_mm(10_000)


# --- the collar -------------------------------------------------------------------------------------------------------

def test_the_collar_is_exactly_one_tile_of_the_neighbours_open_ground(exported, codec):
    west, east = collision(exported, "west"), collision(exported, "east")
    # half-cell columns: west x = 36 + (c + .5) / 2, east x = 96 + (c + .5) / 2; rows z 20..28
    rows = range(2 * (64 - 28), 2 * (64 - 20))
    assert west[rows.start:rows.stop, 127].all() and west[rows.start:rows.stop, 128:130].all()
    assert not west[rows.start:rows.stop, 130:].any()
    assert east[rows.start:rows.stop, 8].all() and east[rows.start:rows.stop, 6:8].all()
    assert not east[rows.start:rows.stop, :6].any()
    _g, wcodes = served(exported, "west", codec)
    _g, ecodes = served(exported, "east", codec)
    for z in np.arange(20.5, 28):
        assert code_at(wcodes, WEST, 100.5, z) and not code_at(wcodes, WEST, 101.5, z)
        assert code_at(ecodes, EAST, 99.5, z) and not code_at(ecodes, EAST, 98.5, z)
        # the same ground in both numberings: one code for the shared tile
        assert code_at(wcodes, WEST, 100.5, z) == code_at(ecodes, EAST, 100.5, z)
    # where the neighbour's own export is closed (the border box stands on east's first tile), so is the collar
    assert not west[2 * (64 - 56):2 * (64 - 54), 128:130].any()
    assert west[2 * (64 - 56):2 * (64 - 54), 127].all()
    collar = exported["report"]["maps"]["west"]["seamCollar"]["east"]
    assert collar["walkableCells"] > 0 and collar["closedByTheNeighbour"] >= 8


def test_a_solid_over_the_border_blocks_both_maps(exported, codec):
    """The straddle box is an east placement whose body reaches 1.4 m onto west's own ground: west's own tiles under
    it close as east's collar there does, so no walker on west stands inside a piece the client draws."""
    _g, wcodes = served(exported, "west", codec)
    _g, ecodes = served(exported, "east", codec)
    x0, x1, z0, z1 = STRADDLE_BOX
    for z in np.arange(z0 + .5, z1):
        for x in (98.5, 99.5):                                  # west's own tiles under the box
            assert code_at(wcodes, WEST, x, z) == 0, (x, z)
            assert code_at(ecodes, EAST, x, z) == 0, (x, z)     # east's collar over west's ground agrees
        assert code_at(ecodes, EAST, 100.5, z) == 0 and code_at(wcodes, WEST, 100.5, z) == 0
        assert code_at(wcodes, WEST, 97.5, z) != 0               # beside the box, west stays open
    west = exported["report"]["maps"]["west"]
    assert west["exportStatistics"]["crossSeamSolidCells"] >= 3 * 4          # 3 half-cell columns by 4 rows at least
    assert set(west["crossSeamSolids"]) == {"east"}
    assert west["crossSeamSolids"]["east"]["openCellsClosed"] == west["exportStatistics"]["crossSeamSolidCells"]
    assert west["crossSeamSolids"]["east"]["placements"] >= 1
    # the box's east part is east's own solid; nothing of west's reaches over the border
    assert exported["report"]["maps"]["east"]["crossSeamSolids"] == {}


def test_every_collision_block_records_the_whole_run(exported):
    """groupExport: every map's snapshot and served grid, the same in each block, each map's own entry its own."""
    groups = {region: sidecar["collision"]["groupExport"]["maps"] for region, sidecar in exported["sidecars"].items()}
    assert groups["west"] == groups["east"] and set(groups["west"]) == {"west", "east"}
    for region, sidecar in exported["sidecars"].items():
        block = sidecar["collision"]
        assert groups[region][region] == {"snapshotSha256": block["sourceSnapshotSha256"],
                                          "servedGridSha256": block["servedGrid"]["sha256"]}


def test_a_partial_run_must_write_outside_the_checkout(tmp_path, capsys):
    base = ["--server", SERVER, "--bake", "west=" + str(tmp_path), "--out", str(tmp_path / "out"), "--partial",
            "--checkout", str(tmp_path / "checkout")]
    with pytest.raises(SystemExit):
        X.main(base)
    assert "outside the checkout" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        X.main(base + ["--packages", str(tmp_path / "checkout" / "eloria-assets")])
    assert "outside the checkout" in capsys.readouterr().err


def test_the_reach_is_seeded_from_the_default_spawn():
    doc = {"gameplay": {"spawnPoints": [{"id": "first", "position": [1.0, 0.0, 2.0]},
                                        {"id": "arrival", "default": True, "position": [3.0, 0.0, 4.0]}]}}
    assert X.default_spawn(doc, "west")["id"] == "arrival"
    for spawns in ([], [{"id": "a", "position": [0, 0, 0]}],
                   [{"id": "a", "default": True, "position": [0, 0, 0]}, {"id": "b", "default": True,
                                                                           "position": [0, 0, 0]}]):
        with pytest.raises(X.ExportError, match="marked default"):
            X.default_spawn({"gameplay": {"spawnPoints": spawns}}, "west")


def test_seam_crossings_join_the_two_maps(exported):
    report = exported["report"]
    crossings = {(c["from"], c["to"]): c for c in report["seamCrossings"]}
    assert set(crossings) == {("west", "east"), ("east", "west")}
    assert crossings[("west", "east")]["departureTiles"] > 40
    assert crossings[("west", "east")]["departureTilesReached"] > 40
    assert report["perMap"]["east"]["servedReach"] > 2000 and report["perMap"]["west"]["servedReach"] > 2000
    assert all(seed["open"] for seed in report["seeds"])


# --- the package ------------------------------------------------------------------------------------------------------

def test_the_fold_of_collision_bin_equals_the_served_mask(exported, codec):
    for region in ("west", "east"):
        grid = collision(exported, region)
        _g, codes = served(exported, region, codec)
        folded = (grid.reshape(CELLS, 2, CELLS, 2) != 0).all(axis=(1, 3))
        assert np.array_equal(folded, codes != 0), region


def test_the_servers_package_reader_accepts_the_package(exported, codec):
    for region in ("west", "east"):
        folder = package(exported, region)
        block = exported["sidecars"][region]["collision"]
        (folder / "world.json").write_text(json.dumps({"collision": block}), encoding="utf-8")
        blob, grid, spec = codec.sources.read_served_package(folder / X.COLLISION_BIN, CELLS)
        assert spec["sha256"] == hashlib.sha256(blob).hexdigest() == block["servedGrid"]["sha256"]
        header = codec.served_grid.read_header(gzip.decompress(blob))
        assert (header["climb_mm"], header["unit_mm"], header["datum_mm"]) == (1000, 50, -100_000)
        assert block["gridAlignment"] == "tile-centres-v1" and block["binary"] == X.COLLISION_BIN
        assert block["sha256"] == hashlib.sha256((folder / X.COLLISION_BIN).read_bytes()).hexdigest()
        assert block["sourceSnapshotSha256"] == hashlib.sha256(region.encode()).hexdigest()
        assert (grid.width, grid.height) == (CELLS, CELLS)


def test_a_re_run_is_byte_identical(exported, codec, tmp_path):
    report, _ = X.run(fixture_territories(), [("east", "west")], codec, tmp_path / "out", tmp_path / "packages",
                      log=lambda *_: None)
    for region in ("west", "east"):
        for name in (X.COLLISION_BIN, X.SERVED_GRID):
            assert (tmp_path / "packages" / region / "client" / name).read_bytes() == \
                (package(exported, region) / name).read_bytes(), (region, name)
        assert (tmp_path / "out" / f"{region}.collision.json").read_bytes() == \
            (exported["out"] / f"{region}.collision.json").read_bytes()


def test_codes_64_128_and_4096_count_as_walkable(exported, codec, tmp_path):
    """R2, the `& 0x3F` trap: codes whose low six bits are zero are ordinary ground on a version 2 map."""
    deep = F.Frame("deep", "Deep", (34, 34), (CELLS, CELLS), (70.0, 0.0, 30.0))

    def basin(x, z):
        h = np.full(np.broadcast(np.asarray(x), np.asarray(z)).shape, -96.8)
        return np.where(np.asarray(z) >= 30, -93.6, h)

    t = territory(deep, [[40.0, 0.0], [100.0, 0.0], [100.0, 60.0], [40.0, 60.0]], function=basin,
                  sea_level=-200.0, spawn=(0.0, -10.0))
    report, sidecars = X.run([t], [], codec, tmp_path / "out", tmp_path / "packages", log=lambda *_: None)
    folder = tmp_path / "packages" / "deep" / "client"
    (folder / "world.json").write_text(json.dumps({"collision": sidecars["deep"]["collision"]}), encoding="utf-8")
    _blob, grid, _spec = codec.sources.read_served_package(folder / X.COLLISION_BIN, CELLS)
    codes = np.frombuffer(grid.codes, np.uint16).reshape(CELLS, CELLS)
    low, high = tile(deep, 60.5, 20.5), tile(deep, 60.5, 40.5)
    assert codes[low[1], low[0]] == 64 and codes[high[1], high[0]] == 128
    walk = collision_map(codec, grid)
    assert walk.walkable(*low) and walk.walkable(*high)
    assert walk.can_step(*low, low[0] + 1, low[1], 2)
    # the spawn's basin (code 64) is reached whole; the 128 shelf stands 3.2 m up a cliff
    assert report["perMap"]["deep"]["servedReach"] == int((codes == 64).sum()) > 1500
    assert report["perMap"]["deep"]["openTiles"] == int((codes == 64).sum() + (codes == 128).sum())
    # and 4096 on the east plateau, inside its cliffs
    egrid, ecodes = served(exported, "east", codec)
    plateau = tile(EAST, 148.5, 10.5)
    assert ecodes[plateau[1], plateau[0]] == 4096 and collision_map(codec, egrid).walkable(*plateau)
    assert collision(exported, "east")[2 * plateau[1], 2 * plateau[0]] != 0


# --- the codec guard --------------------------------------------------------------------------------------------------

def test_the_codec_comes_only_from_the_named_server(codec, tmp_path):
    with pytest.raises(X.ExportError):
        X.server_codec(tmp_path)                    # no eloria/served_grid.py
    (tmp_path / "eloria").mkdir()
    (tmp_path / "eloria" / "served_grid.py").write_text("", encoding="utf-8")
    with pytest.raises(X.ExportError):
        X.server_codec(tmp_path)                    # the modules already loaded belong to another checkout
    assert Path(codec.served_grid.__file__).resolve().is_relative_to(Path(SERVER).resolve())


def test_river_ribbons_are_paths_not_water_regions():
    """The exporter's water: lakes from waterRegions (ellipses only, anything else refused), rivers from the paths of
    kind river. A sw_isle bake holds 7 ellipses in waterRegions and its 4 rivers only as paths."""
    t = fixture_territories()[1]
    assert not t.lakes and len(t.rivers) == 2
    zs = np.array([47.0, 46.0, 45.0]) - 30.0
    xs = np.array([129.0, 130.0, 131.0]) - 130.0
    level = X.water_level(t, xs, zs, np.full((3, 3), 10.0))
    assert np.allclose(level, 11.0)
