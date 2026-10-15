"""Dry-end rule: seam terminals, door pins, waypoints, branch and trail starts stand on dry land outside the setback."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import door_approaches as D
import river_crossings as RC
import world_layout as W
from test_river_crossings import river_world


class DryEndTests(unittest.TestCase):
    def setUp(self):
        self.world = river_world(size=(240, 360), width=lambda z: np.full(np.shape(z), 10.))
        RC.prepare_river_crossings(self.world)
        self.setback = RC.setback_metres(RC.policy_of(self.world), 1.65)

    def test_an_end_in_the_water_or_the_setback_moves_to_the_nearest_dry_ground_outside_it(self):
        for point in ([127., 100.], [133., 100.], [107., 200.]):
            end, moved = RC.dry_end(self.world, point, 1.65, 'test')
            self.assertTrue(moved)
            self.assertGreater(float(RC.water_distance_at(self.world, *end)), self.setback)
            self.assertLessEqual(float(np.linalg.norm(end - point)), 12.)
        end, moved = RC.dry_end(self.world, [160., 100.], 1.65, 'test')
        self.assertFalse(moved); np.testing.assert_allclose(end, [160., 100.])

    def test_a_branch_starts_on_its_destination_bank_off_every_bridge_and_outside_the_setback(self):
        world = self.world
        site = min(world.crossing_candidates, key=lambda c: abs(c['centre'][1] - 180.))
        RC.claim(world, [site['key']], 'seam-road', public=True)
        a, b = np.asarray(site['routeLandings'])
        span = a + (b - a) * np.linspace(0, 1, 21)[:, None]
        west = np.c_[np.full(10, 60.), np.linspace(100, 300, 10)]
        east_close = np.array([[134., 190.], [136., 176.]])          # inside the east bank's setback
        east = np.array([[200., 260.]])
        stations = np.vstack([span, west, east_close, east])
        end = np.array([160., 185.])                                  # a discovery on the east bank
        start, gap = RC.branch_start(world, 'test', stations, end, 1.65)
        np.testing.assert_allclose(start, [200., 260.])               # the only dry east-bank station off the bridge
        self.assertGreater(float(RC.water_distance_at(world, *start)), self.setback)
        self.assertFalse(RC.on_span(world, start[None, :])[0])
        # Without an east-bank station the start falls back to the dry west bank, still never the bridge.
        start, _ = RC.branch_start(world, 'test', np.vstack([span, west]), end, 1.65)
        self.assertLess(start[0], 100.)
        # A pinned end keeps the stations on its own side of the portal it serves.
        start, _ = RC.branch_start(world, 'test', np.array([[200., 150.], [200., 230.]]), np.array([200., 200.]), 1.65, toward=np.array([200., 210.]))
        np.testing.assert_allclose(start, [200., 150.])

    def test_door_pins_and_waypoints_inside_the_setback_are_refused(self):
        world = self.world
        world.hub = lambda region: np.array([200., 20.])
        content = SimpleNamespace(door_road_ends={('test', 'door'): np.array([133., 100.])}, server_road_ends={},
                                  door_road_waypoints={}, seam_road_waypoints={})
        with self.assertRaisesRegex(ValueError, 'inside the 6 m river setback'):
            D.validate_river_setbacks(world, content)
        content.door_road_ends = {('test', 'door'): np.array([160., 100.])}
        content.server_road_ends = {('test', 'test', 'test_secrets'): [np.array([60., 100.]), np.array([126., 90.])]}
        with self.assertRaisesRegex(ValueError, 'test->test_secrets road end'):
            D.validate_river_setbacks(world, content)
        content.server_road_ends = {}
        content.seam_road_waypoints = {('test', 'test--other'): [np.array([200., 100.]), np.array([136., 150.])]}
        with self.assertRaisesRegex(ValueError, 'waypoint 1: stands .* inside the 8 m river setback'):
            D.validate_river_setbacks(world, content)
        # A leg across the river is accepted when the territory offers a crossing there, and reported.
        content.seam_road_waypoints = {('test', 'test--other'): [np.array([200., 100.]), np.array([60., 120.])]}
        legs = D.validate_river_setbacks(world, content)
        self.assertEqual(len(legs), 1); self.assertEqual(legs[0]['leg'], 1)
        world.crossing_candidates = []
        with self.assertRaisesRegex(ValueError, 'offers no crossing site'):
            D.validate_river_setbacks(world, content)


class SeamTerminalTests(unittest.TestCase):
    def test_a_seam_crossing_keeps_every_terminal_station_outside_the_river_setback(self):
        # Two territories meet at z = 180; a river runs south across the seam at x = 120, so the cheapest seam
        # station by distance (straight between the centres at x 120) stands in the water.
        world = river_world(size=(240, 360), width=lambda z: np.full(np.shape(z), 10.),
                            owner=lambda w: (w.gz[:-1, :-1] >= 180).astype(int))
        world.ids = ['whitehorn_range', 'grey_moors', 'amberwood', 'amethyst_barrens', 'mirrorhold', 'sunmane_steppe', 'four_gates',
                     'westhaven', 'manymouth_delta', 'crownwater', 'verdant_stair', 'ssarathi_ruins']
        world.owner = np.where(world.gz[:-1, :-1] >= 180, 4, 2)
        world.centers = np.full((12, 2), -1000.); world.centers[2] = [120., 90.]; world.centers[4] = [120., 270.]
        world.regions = {region: {'center': world.centers[i].tolist()} for i, region in enumerate(world.ids)}
        world.plan.update(connection_sites={}, inhabited_hubs={})
        world.connections = []
        RC.prepare_river_crossings(world)
        with patch.object(W.L, 'water_fields', side_effect=lambda x, z, **k: {'depth': np.zeros(len(np.atleast_1d(x))), 'mask': np.zeros(len(np.atleast_1d(x)), bool)}):
            world.plan_connections()
        link = next(c for c in world.connections if c['id'] == 'amberwood--mirrorhold')
        anchor, normal = np.asarray(link['anchor']), np.asarray(link['normal'])
        setback = RC.setback_metres(RC.policy_of(world), W.SEAM_ROAD_WIDTH_METRES)
        for k in (-9., -4., 0., 4., 9.):
            self.assertGreater(float(RC.water_distance_at(world, *(anchor + normal * k))), setback)
        self.assertTrue(link['alternatives'])
        # The alternatives are spread along the seam, never the neighbours of a station that may fail for one reason.
        stations = [anchor] + [np.asarray(a['anchor']) for a in link['alternatives']]
        for i, a in enumerate(stations):
            for b in stations[i + 1:]:
                self.assertGreaterEqual(float(np.linalg.norm(a - b)), W.SEAM_ANCHOR_ALTERNATIVE_SPACING_METRES)


if __name__ == '__main__':
    unittest.main()
