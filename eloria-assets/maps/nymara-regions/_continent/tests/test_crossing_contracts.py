import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_toolkit'))
import crossing_contracts as X
from amberwood import gltf as G, mesh as M

ORIGIN = [10, 10]      # serverOrigin: package x = tile - 10, tile y = 10 - package z
CELLS = [20, 20]


def floor_mesh(x0, x1, z0, z1, height):
    positions = np.array([[x0, height, z0], [x1, height, z0], [x1, height, z1], [x0, height, z1]], float)
    return M.Mesh(positions=positions, normals=np.tile([0., 1., 0.], (4, 1)), uvs=positions[:, [0, 2]],
                  indices=np.array([0, 2, 1, 0, 3, 2]), material='bridge_timber')


def package(floors):
    """A tiny world.glb holding the given union floors, loaded the way the contracts stage loads it."""
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'world.glb'
        builder = G.GltfBuilder()
        builder.add_material(G.Material('bridge_timber'))
        for name, mesh in floors.items():
            builder.add_mesh(name, mesh, with_tangents=False)
            builder.add_node(G.Node(name, mesh=name))
        builder.write_glb(str(path))
        return X.GR.load(path)


def served(level=10):
    grid = np.full((CELLS[1], CELLS[0]), level, dtype=np.uint8)
    heights = np.full((CELLS[1] * 2, CELLS[0] * 2), 5.0, dtype=np.float32)
    return grid, heights


def tile_of(point):
    return int(round(ORIGIN[0] + point[0])), int(round(ORIGIN[1] - point[2]))


class CrossingPointTests(unittest.TestCase):
    def test_declared_point_rounds_to_its_tile_under_the_server_rule(self):
        for tile in ((3, 4), (12, 0), (0, 19), (7, 7)):
            point = X.crossing_point(tile, 5.25, ORIGIN)
            self.assertEqual(tile_of(point), tile)
            self.assertAlmostEqual(point[1], 5.25)
            self.assertLess(abs(point[0] - (tile[0] + .5 - ORIGIN[0])), .5)
            self.assertLess(abs(point[2] - (ORIGIN[1] - tile[1] - .5)), .5)


class SiteTests(unittest.TestCase):
    def test_a_floor_number_names_its_crossing_site_and_decks_away_from_sites_name_none(self):
        self.assertEqual(X.site_of('001'), 0)
        self.assertEqual(X.site_of('042'), 41)
        self.assertIsNone(X.site_of('500'))
        self.assertIsNone(X.site_of('517'))


class DeclareCrossingsTests(unittest.TestCase):
    def test_a_continuous_floor_is_declared_between_its_extreme_served_tiles(self):
        # Package x 2..9 (tiles 12..19 wide? no: tile x = package x + 10 -> 12..18), z -3..-1 (tiles 11..12).
        document, body = package({'Walk_ContinentalBridgeUnion_004_west': floor_mesh(-8, 0, -3, -1, 5.0)})
        grid, heights = served()
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(not_walkable, [])
        self.assertEqual([c['id'] for c in crossings], ['ContinentalBridgeUnion_004'])
        self.assertEqual(crossings[0]['site'], 3)                 # bridge_export numbers a site's deck by its id + 1
        record = declared[0]
        self.assertEqual(record['deckTiles'], 16)                 # 8 tiles long, 2 tiles wide
        self.assertEqual(record['parts'], [16])
        ends = sorted(tile_of(p) for p in crossings[0]['endpoints'])
        self.assertEqual(ends[0][0], 2); self.assertEqual(ends[1][0], 9)
        self.assertEqual(sorted(tuple(t) for t in record['endTiles']), ends)
        for point in crossings[0]['endpoints']:
            self.assertAlmostEqual(point[1], 5.0)

    def test_other_territories_floors_and_unrelated_walk_nodes_are_ignored(self):
        document, body = package({'Walk_ContinentalBridgeUnion_004_east': floor_mesh(-8, 0, -3, -1, 5.0),
                                  'Walk_Landmark_Quay': floor_mesh(2, 8, -3, -1, 5.0)})
        grid, heights = served()
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual((crossings, declared, not_walkable), ([], [], []))

    def test_a_floor_interrupted_by_one_plain_walkable_tile_stays_one_crossing(self):
        # Two floor pieces with a one-tile gap of served ground between them.
        document, body = package({'Walk_ContinentalBridgeUnion_007_west': floor_mesh(-8, -4, -3, -1, 5.0),
                                  'Walk_ContinentalBridgeUnion_007_west_WorldPlacement': floor_mesh(-3, 0, -3, -1, 5.0)})
        grid, heights = served()
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(not_walkable, [])
        self.assertEqual(declared[0]['parts'], [14])
        ends = sorted(tile_of(p) for p in crossings[0]['endpoints'])
        self.assertEqual((ends[0][0], ends[1][0]), (2, 9))

    def test_a_fold_that_blocks_the_middle_reports_the_floor_instead_of_declaring_it(self):
        document, body = package({'Walk_ContinentalBridgeUnion_004_west': floor_mesh(-8, 0, -3, -1, 5.0)})
        grid, heights = served()
        grid[:, 4] = 0; grid[:, 7] = 0   # two blocked columns cut the floor into thirds
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(crossings, [])
        self.assertEqual(not_walkable[0]['parts'], [4, 4, 4])
        self.assertIn('largest walkable part holds 4 of 12 deck tiles', not_walkable[0]['reason'])
        # A short stub beyond a wall leaves the long part declared and the stub reported in its parts.
        grid[:, 4] = 10; grid[:, 7] = 10; grid[:, 8] = 0
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(len(crossings), 1)
        self.assertEqual(declared[0]['parts'], [12, 2])
        self.assertEqual(not_walkable, [])

    def test_a_step_beyond_the_climb_limit_splits_the_floor(self):
        document, body = package({'Walk_ContinentalBridgeUnion_004_west': floor_mesh(-8, 0, -3, -1, 5.0)})
        grid, heights = served()
        grid[:, 6:] = 13          # three stages up from column six onward: two equal halves, neither is the crossing
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(crossings, [])
        self.assertEqual(not_walkable[0]['parts'], [8, 8])
        self.assertIn('holds 8 of 16', not_walkable[0]['reason'])
        grid[:, 6:] = 12          # exactly the climb limit walks
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(declared[0]['parts'], [16])

    def test_floors_the_fold_does_not_serve_at_all_are_reported(self):
        document, body = package({'Walk_ContinentalBridgeUnion_004_west': floor_mesh(-8, 0, -3, -1, 5.0)})
        grid, heights = served(level=0)
        crossings, declared, not_walkable = X.declare_crossings(document, body, 'west', grid, 2, ORIGIN, CELLS, heights)
        self.assertEqual(crossings, [])
        self.assertEqual(not_walkable[0]['reason'], 'no deck tile the fold serves')


if __name__ == '__main__':
    unittest.main()
