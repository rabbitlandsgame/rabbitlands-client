"""A seam is crossed wherever both maps can be stood on, not only at its gate."""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import crossings as C
import collision_export as CE
from test_partition_pipeline import FlatWorld

GATED = ('east--west',)
SHIPPED = C.GATED_SEAMS


def step(heights, y, x, dy, dx):
    """The server's step rule on level ground: both tiles open, no corner cut."""
    rows, columns = heights.shape
    def ok(ny, nx):
        return 0 <= ny < rows and 0 <= nx < columns and bool(heights[y, x]) and bool(heights[ny, nx])
    if not ok(y + dy, x + dx):
        return False
    return not (dy and dx) or (ok(y + dy, x) and ok(y, x + dx))


def served(west=None, east=None, world=None):
    """Each map's own ground on two level grids, or the grids given."""
    world = world or FlatWorld()
    grids = {'west': west, 'east': east}
    return {region: C.own_ground(world, region,
                                 np.ones((48, 48), np.uint8) if grids[region] is None else grids[region].astype(np.uint8))
            for region in ('west', 'east')}


class SeamLaneTests(unittest.TestCase):
    def setUp(self):
        self.world = FlatWorld()
        self.link = self.world.connections[0]

    def lanes(self, grids, side=0):
        return C.crossing_lanes(self.world, self.link, side, grids, step)

    def test_every_tile_of_the_border_both_maps_can_stand_on_is_a_lane(self):
        lanes = self.lanes(served())
        self.assertGreater(len(lanes), 20, 'a twenty-metre border offers more than a gate')
        for lane in lanes:
            departure = C.global_tile(self.world, 'west', lane['tile'])
            arrival = C.global_tile(self.world, 'west', lane['arrival'])
            # Stood on the neighbour's first tile across the boundary, with this
            # territory's own ground one step behind it.
            self.assertAlmostEqual(float(departure[0]), 20.5)
            self.assertAlmostEqual(float(arrival[0]), 19.5)
            self.assertEqual(max(abs(lane['tile'][0] - lane['arrival'][0]),
                                 abs(lane['tile'][1] - lane['arrival'][1])), 1)
        self.assertEqual(len({tuple(lane['tile']) for lane in lanes}), len(lanes))

    def test_a_lane_needs_the_ground_on_both_sides_of_it(self):
        self.assertEqual(self.lanes(served(east=np.zeros((48, 48), bool))), [],
                         'ground the neighbour refuses is no crossing')
        self.assertEqual(self.lanes(served(west=np.zeros((48, 48), bool))), [],
                         'ground this map refuses is no crossing either')
        # One blocked tile on the far side closes its lane and no other.
        east = np.ones((48, 48), bool)
        whole = {tuple(lane['tile']) for lane in self.lanes(served())}
        closed = sorted(whole)[3]
        far = C.tiles_at(self.world, 'east', *C.global_tile(self.world, 'west', list(closed)))
        east[int(far[1]), int(far[0])] = False
        self.assertEqual({tuple(lane['tile']) for lane in self.lanes(served(east=east))},
                         whole - {closed})

    def test_a_pocket_its_own_hub_cannot_reach_is_still_a_way_across(self):
        # The east strip beside the border is cut off from the rest of the east map
        # by a river two tiles in (the Manymouth strip under the Four Gates south
        # wall): still walkable on both sides of the border, so still crossable.
        east = np.ones((48, 48), bool)
        border_x = int(C.tiles_at(self.world, 'east', 20.5, 10.)[0])
        east[:, border_x + 2] = False
        strip = {tuple(lane['tile']) for lane in self.lanes(served(east=east))}
        self.assertEqual(strip, {tuple(lane['tile']) for lane in self.lanes(served())},
                         'a river behind the strip closes no crossing onto it')
        back = self.lanes(served(east=east), side=1)
        self.assertTrue(back, 'and a walker in the strip can always step back')

    def test_the_two_sides_of_a_seam_name_the_same_ground(self):
        west = {tuple(C.global_tile(self.world, 'west', lane['tile']).round(3))
                for lane in self.lanes(served())}
        east = {tuple(C.global_tile(self.world, 'east', lane['arrival']).round(3))
                for lane in self.lanes(served(), side=1)}
        self.assertEqual(west, east, 'what one map departs from is what the other arrives at')

    def test_a_widened_seam_keeps_the_lanes_of_the_gate_it_had(self):
        world = self.world
        C.prepare_contracts(world)
        connections = world.publication_connections
        gate = [[tuple(lane['tile']) for lane in end['lanes']] for end in connections[0]['ends']]
        report = C.widen_seams(world, connections, served(world=world), step, gated=())
        self.assertEqual([end['gateLanes'] + end['gateLanesMoved'] for end in report[0]['ends']], [7, 7])
        # The survey lays the west gate's lanes on the second tile beyond the border
        # and the east gate's on the first: a walker can only reach the west ones over
        # the border's own first-tile lanes, which fire first and take their offsets;
        # the east ones are border lanes already.
        self.assertEqual([end['gateLanesMoved'] for end in report[0]['ends']], [7, 0])
        for side, end in enumerate(connections[0]['ends']):
            tiles = [tuple(lane['tile']) for lane in end['lanes']]
            self.assertGreater(len(tiles), 7, 'the seam gained the rest of its border')
            self.assertEqual(len(set(tiles)), len(tiles), 'no lane is declared twice')
            offsets = sorted(lane['gate'] for lane in end['lanes'] if 'gate' in lane)
            self.assertEqual(offsets, list(range(-3, 4)), 'every lane of the gate survives, by its offset')
            for lane in end['lanes']:
                self.assertEqual(max(abs(lane['tile'][0] - lane['arrival'][0]),
                                     abs(lane['tile'][1] - lane['arrival'][1])), 1,
                                 'every lane is stepped onto from the tile beside it')
            self.assertEqual(tiles, sorted(tiles, key=lambda t: (t[1], t[0])))
        self.assertTrue(set(gate[1]) <= {tuple(lane['tile']) for lane in connections[0]['ends'][1]['lanes']},
                        'a gate on the first tile keeps its own lanes')

    def test_no_cell_is_a_departure_of_both_maps_where_the_border_steps_by_the_gate(self):
        world = self.world
        # The border steps two metres east for one metre of its length beside the
        # anchor, so one of the seven offsets of the west gate lands on west ground.
        def owner_at(x, z):
            x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
            step = (x < 22) & (z >= 10) & (z < 11)
            return ((x >= 20) & ~step).astype(int)
        world.owner_at = owner_at
        C.prepare_contracts(world)
        connections = world.publication_connections
        C.widen_seams(world, connections, served(world=world), step, gated=())
        west, east = connections[0]['ends']
        for end in (west, east):
            self.assertEqual(sorted(lane['gate'] for lane in end['lanes'] if 'gate' in lane), list(range(-3, 4)),
                             'every offset of the gate is carried by a lane of the border')
        for end in (west, east):
            for lane in end['lanes']:
                self.assertTrue(C.departs_outward(world, end['region'], lane), end['region'])
        cells = [{tuple(C.global_tile(world, end['region'], lane['tile']).round(3)) for lane in end['lanes']}
                 for end in (west, east)]
        self.assertFalse(cells[0] & cells[1], 'an arrival would trigger the crossing back at once')
        # Each end's own crossing - where a walker to the neighbour is sent - is one of its lanes.
        for end in (west, east):
            self.assertIn(end['tile'], [lane['tile'] for lane in end['lanes']])

    def test_an_end_whose_middle_lane_is_dropped_is_reseated_on_the_nearest_lane(self):
        world = self.world
        def owner_at(x, z):
            x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
            return ((x >= 20) & ~((x < 22) & (z >= 9) & (z < 12))).astype(int)
        world.owner_at = owner_at
        C.prepare_contracts(world)
        west = world.publication_connections[0]['ends'][0]
        middle = list(west['tile'])
        C.widen_seams(world, world.publication_connections, served(world=world), step, gated=())
        self.assertNotEqual(west['tile'], middle, 'the middle lane stood on west ground and was dropped')
        self.assertIn(west['tile'], [lane['tile'] for lane in west['lanes']])
        point = C.global_tile(world, 'west', west['tile'])
        self.assertEqual(west['position'][0], float(point[0] - 10))
        self.assertEqual(west['position'][2], float(point[1] - 10))

    def test_a_gated_seam_keeps_its_gate_alone(self):
        world = self.world
        C.prepare_contracts(world)
        connections = world.publication_connections
        self.assertEqual(C.widen_seams(world, connections, served(world=world), step, gated=GATED), [])
        self.assertEqual([len(end['lanes']) for end in connections[0]['ends']], [7, 7])


class RoadlessWorld(FlatWorld):
    """The two territories of FlatWorld with no road between them."""
    connections = []


# Each map's hub, well inside its own ground: FlatWorld's border is at west tile
# 34 / east tile 13 (the neighbour's first tile across it), its own last tiles 33 and 14.
HUBS = {'west': [20, 24], 'east': [28, 24]}


class RoadlessBorderTests(unittest.TestCase):
    def settle(self, grids=None):
        world = RoadlessWorld()
        C.prepare_contracts(world)
        publication = {'connections': [], 'visualConnections': copy.deepcopy(world.visual_connections)}
        settled = C.settle_crossings(world, publication, grids or served(world=world), step, HUBS)
        return world, publication, settled['opened']

    def test_a_border_no_road_crosses_is_opened_wherever_its_ground_meets(self):
        world, publication, opened = self.settle()
        self.assertEqual(world.publication_connections, [], 'no road, deck or marker is built for it')
        self.assertEqual(opened, ['border--west--east'])
        self.assertEqual(publication['visualConnections'], [], 'its view-only twin is withdrawn')
        link, = publication['connections']
        self.assertIs(link['road'], False)
        for end, other in zip(link['ends'], link['ends'][::-1]):
            tiles = [lane['tile'] for lane in end['lanes']]
            self.assertGreater(len(tiles), 7, 'the whole border is crossable, not a gate of it')
            self.assertFalse(any('gate' in lane for lane in end['lanes']), 'and no lane of it is a gate')
            self.assertIn(end['tile'], tiles, 'each end is seated on one of its own lanes')
            self.assertEqual(end['frame']['portal'], 'border-to-' + other['region'])
            self.assertTrue(end['preloadEdges'], 'it ships the border it is crossed along')

    def test_a_border_whose_ground_never_meets_stays_a_view(self):
        world, publication, opened = self.settle(served(east=np.zeros((48, 48), bool), world=RoadlessWorld()))
        self.assertEqual(opened, [])
        self.assertEqual(publication['connections'], [])
        self.assertEqual([v['id'] for v in publication['visualConnections']], ['view--west--east'])

    def test_a_pair_a_road_or_a_boat_joins_is_not_opened_again(self):
        self.assertEqual(C.open_borders(FlatWorld()), [], 'a road already crosses it')
        world = RoadlessWorld()
        world.connections = [{'id': 'east--west', 'type': 'ferry', 'regions': ['west', 'east']}]
        self.assertEqual(C.open_borders(world), [], 'the server tells a boat from a walk by the maps it joins')

    def test_the_anchor_stands_on_the_border(self):
        link, = C.open_borders(RoadlessWorld())
        self.assertEqual(link['anchor'], [20., 10.])
        self.assertEqual(link['normal'], [1., 0.])

    def test_the_collar_opens_a_roadless_border_as_it_opens_a_road_s(self):
        world = RoadlessWorld()
        C.prepare_contracts(world)
        gx, gz = np.meshgrid(np.arange(14.25, 26., .5), np.arange(4.25, 16., .5))
        collar = CE.seam_collar(world, 'west', gx, gz)
        self.assertTrue(collar.any())
        self.assertGreaterEqual(gx[collar].min(), 20.)
        self.assertLessEqual(gx[collar].max(), 21.)


class ReachableLaneTests(unittest.TestCase):
    """A lane is kept where a walker from some hub can get onto it and step off where it lands."""
    def prune(self, west=None, east=None):
        world = FlatWorld()
        C.prepare_contracts(world)
        connections = world.publication_connections
        # A served grid is its own territory and the one-tile collar beyond it.
        west = np.ones((48, 48), bool) if west is None else west
        east = np.ones((48, 48), bool) if east is None else east
        west[:, 35:] = False
        east[:, :13] = False
        grids = served(west=west, east=east, world=world)
        C.widen_seams(world, connections, grids, step, gated=())
        before = [{tuple(lane['tile']) for lane in end['lanes']} for end in connections[0]['ends']]
        withdrawn = C.prune_lanes(world, connections, grids, HUBS, 2)
        after = [{tuple(lane['tile']) for lane in end['lanes']} for end in connections[0]['ends']]
        return before, after, withdrawn, connections[0]

    def test_open_ground_keeps_every_lane(self):
        before, after, withdrawn, _ = self.prune()
        self.assertEqual(withdrawn, 0)
        self.assertEqual(before, after)

    def test_ground_no_hub_can_reach_from_either_side_is_no_crossing(self):
        # A wall behind the border on both maps: the strip between is an island.
        west, east = np.ones((48, 48), bool), np.ones((48, 48), bool)
        west[:, 30] = False
        east[:, 17] = False
        before, after, withdrawn, _ = self.prune(west, east)
        self.assertTrue(all(before))
        self.assertEqual(after, [set(), set()])
        self.assertEqual(withdrawn, sum(len(tiles) for tiles in before))

    def test_a_pocket_reached_over_the_border_keeps_its_lanes(self):
        # The Manymouth strip under the Four Gates wall: cut off from its own hub,
        # walked into from the neighbour's, and so crossable both ways.
        west = np.ones((48, 48), bool)
        west[:, 30] = False
        before, after, withdrawn, _ = self.prune(west=west)
        self.assertEqual(withdrawn, 0)
        self.assertEqual(before, after)

    def test_a_landing_with_nowhere_to_go_but_back_is_no_crossing(self):
        # One tile of west ground walled in against the border at (33, 24).
        west = np.ones((48, 48), bool)
        west[19:30, 30:33] = False
        west[19:30, 33] = False
        west[24, 33] = True
        before, after, withdrawn, link = self.prune(west=west)
        self.assertGreater(withdrawn, 0)
        # West's own crossing out of the cell is unreachable from its hub, and
        # east's crossing into it lands with every first step another crossing.
        self.assertNotIn((34, 24), after[0])
        world = FlatWorld()
        into = {tuple(int(v) for v in C.tiles_at(world, 'west', *C.global_tile(world, 'east', tile)))
                for tile in after[1]}
        self.assertNotIn((33, 24), into)
        self.assertTrue(after[0] and after[1], 'the rest of the border is still crossed')
        for end in link['ends']:
            self.assertIn(tuple(end['tile']), {tuple(lane['tile']) for lane in end['lanes']},
                          'each end is reseated on a lane that survives')

    def test_a_road_nobody_can_use_is_refused(self):
        world = FlatWorld()
        C.prepare_contracts(world)
        west, east = np.ones((48, 48), bool), np.ones((48, 48), bool)
        west[:, 30] = False
        east[:, 17] = False
        grids = served(west=west, east=east, world=world)
        publication = {'connections': world.publication_connections, 'visualConnections': []}
        C.widen_seams(world, publication['connections'], grids, step, gated=())
        with self.assertRaisesRegex(ValueError, 'no walker can reach or leave any lane of east--west'):
            C.settle_crossings(world, publication, grids, step, HUBS)


class SeamCollarTests(unittest.TestCase):
    def collar(self, gated):
        world = FlatWorld()
        C.GATED_SEAMS = gated
        try:
            gx, gz = np.meshgrid(np.arange(14.25, 26., .5), np.arange(4.25, 16., .5))
            return CE.seam_collar(world, 'west', gx, gz), gx, gz
        finally:
            C.GATED_SEAMS = SHIPPED

    def test_the_collar_is_one_tile_of_the_neighbour_and_only_for_an_open_seam(self):
        collar, gx, _ = self.collar(())
        self.assertTrue(collar.any(), 'a widened seam opens the first tile across its border')
        opened = gx[collar]
        self.assertGreaterEqual(opened.min(), 20., 'the collar is the neighbour\'s ground, never our own')
        self.assertLessEqual(opened.max(), 21., 'and only the first tile of it')

    def test_a_gated_seam_has_no_collar(self):
        collar, _, _ = self.collar(GATED)
        self.assertFalse(collar.any())


class HeightScaleTests(unittest.TestCase):
    def test_the_collar_cannot_stretch_a_territory_s_height_scale(self):
        heights = np.array([[0., 10., 30.], [5., 40., 200.]])
        own = np.array([[True, True, True], [True, False, False]])
        collar = ~own
        grid, encoding = CE.encode_heights(heights, own | collar, basis=own)
        plain, plain_encoding = CE.encode_heights(heights, own)
        self.assertEqual(encoding, plain_encoding, "the scale is the territory's own")
        self.assertTrue((grid[own] == plain[own]).all(), 'its own ground encodes exactly as before')
        self.assertNotEqual(grid[1, 1], 0, 'neighbouring ground the scale can express is opened')
        self.assertEqual(grid[1, 2], 0, 'ground beyond the scale is left closed, never clamped to its top step')

    def test_a_territory_with_no_collar_keeps_its_scale(self):
        heights = np.array([[0., 10.], [30., 5.]])
        walkable = np.ones((2, 2), bool)
        self.assertEqual(CE.encode_heights(heights, walkable, basis=walkable)[1],
                         CE.encode_heights(heights, walkable)[1])


if __name__ == '__main__':
    unittest.main()
