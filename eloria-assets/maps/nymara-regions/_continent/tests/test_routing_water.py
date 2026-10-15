"""River water is impassable: a road crosses a river only on a crossing site's bridge edge, never along the channel."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import river_crossings as RC
import world_layout as W
from test_river_crossings import river_world


def dense(points, step=.5):
    points = np.asarray(points, float)
    out = []
    for a, b in zip(points, points[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.extend(a + (b - a) * k / n for k in range(n))
    return np.vstack([out, points[-1]])


class ChannelTests(unittest.TestCase):
    def sealed_bank(self):
        """The A1/A2 case: a branch's start and goal share the east bank, but retained buildings seal the bank between
        them from the setback's edge to the map edge, so the channel is the only way through that bank."""
        world = river_world(size=(240, 360), width=lambda z: np.full(np.shape(z), 10.))
        for z in (178., 184.):
            world.structure_obstacle([139, 0, z - 2], [240, 8, z + 2])
        RC.prepare_river_crossings(world)
        return world

    def test_a_sealed_bank_sends_the_road_over_two_spaced_bridges_not_down_the_channel(self):
        world = self.sealed_bank()
        start, goal = np.array([160., 60.]), np.array([160., 300.])
        points = world.route(start, goal, region='test', width=1.65, public=True, name='discovery-test')
        record = world.routing[-1]
        np.testing.assert_allclose(points[0], start); np.testing.assert_allclose(points[-1], goal)
        # Two crossings, claimed as sites at least the spacing apart along the river.
        self.assertEqual(len(record['sites']), 2)
        arcs = sorted(world.crossing_sites[i]['arcMetres'] for i in record['sites'])
        self.assertGreaterEqual(arcs[1] - arcs[0], RC.policy_of(world)['minimum_spacing_metres'])
        # Nothing travels over the water or inside the setback except on a site's span.
        samples = dense(points)
        on_bridge = RC.on_span(world, samples, pad=0.)
        wet = RC.water_distance_at(world, samples[:, 0], samples[:, 1]) <= 0.
        self.assertFalse((wet & ~on_bridge).any())
        # A road over the water crosses it square: every wet run is a span of one site.
        runs = np.flatnonzero(np.diff(np.r_[0, wet.astype(int), 0]))
        for a, b in zip(runs[::2], runs[1::2]):
            chord = samples[b - 1] - samples[a]
            self.assertLess(abs(chord[1]), 2., 'a wet run travels along the river')

    def test_without_crossing_sites_the_leg_crosses_the_buildings_as_a_fallback_never_the_channel(self):
        world = self.sealed_bank()
        world.crossing_candidates = []
        points = world.route(np.array([160., 60.]), np.array([160., 300.]), region='test', width=1.65)
        self.assertTrue(world.routing[-1]['solidFallback'])
        samples = dense(points)
        self.assertGreater(float(RC.water_distance_at(world, samples[:, 0], samples[:, 1]).min()), RC.setback_metres(RC.policy_of(world), 1.65))

    def test_a_road_along_a_river_keeps_outside_its_setback_and_pays_for_the_shelf(self):
        world = river_world(size=(240, 360), width=lambda z: np.full(np.shape(z), 10.))
        RC.prepare_river_crossings(world)
        points = world.route(np.array([150., 20.]), np.array([150., 340.]), region='test', width=4.)
        samples = dense(points)
        distance = RC.water_distance_at(world, samples[:, 0], samples[:, 1])
        self.assertGreater(float(distance.min()), RC.setback_metres(RC.policy_of(world), 4.))
        self.assertFalse(world.routing[-1].get('sites'))

    def test_a_shared_bridge_is_cheaper_than_a_new_one(self):
        world = river_world(size=(240, 360), width=lambda z: np.full(np.shape(z), 8.))
        RC.prepare_river_crossings(world)
        world.route(np.array([60., 160.]), np.array([200., 160.]), region='test', width=4., public=True, name='seam-road')
        first = world.routing[-1]['sites']
        self.assertEqual(len(first), 1)
        # A later branch crossing nearby uses the same site rather than claiming another.
        world.route(np.array([60., 190.]), np.array([200., 200.]), region='test', width=1.65, name='discovery-branch')
        self.assertEqual(world.routing[-1]['sites'], first)
        self.assertEqual(len(world.crossing_sites), 1)


if __name__ == '__main__':
    unittest.main()
