"""Earthworks outside footings: cut at most 4 m, fill at most 3 m, written into the ground; beyond them, reroute."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import world_layout as W


def valley(stations, floor=24., rim=74., half=20.):
    """A Grey Moors hub-like profile: a deep, narrow valley between two high rims (the hub descent to the pool)."""
    s = np.asarray(stations, float)
    centre = s[-1] * .5
    return np.where(np.abs(s - centre) <= half, floor + (rim - floor) * (np.abs(s - centre) / half) ** 2, rim)


class ProfileTests(unittest.TestCase):
    def test_a_valley_is_not_bridged_by_the_profile_fill_is_capped_at_three_and_cut_at_four(self):
        s = np.arange(0., 202., 2.)
        ground = valley(s)
        unlimited = W.graded_profile(ground, s, maximum_grade=.35)
        limited = W.graded_profile(ground, s, maximum_grade=W.ROAD_EARTHWORKS_GRADE, cut=W.ROAD_CUT_METRES, fill=W.ROAD_FILL_METRES)
        # The old profile stood tens of metres over the valley floor; the limited one follows the ground within the limits.
        self.assertGreater(float(np.max(unlimited - ground)), 20.)
        self.assertLessEqual(float(np.max(limited - ground)), W.ROAD_FILL_METRES + 1e-9)
        self.assertGreaterEqual(float(np.min(limited - ground)), -W.ROAD_CUT_METRES - 1e-9)
        # Road ends are never lifted or sunk to make a grade.
        self.assertAlmostEqual(limited[0], ground[0])
        self.assertAlmostEqual(limited[-1], ground[-1])

    def test_gentle_ground_is_the_profile_itself(self):
        s = np.arange(0., 100., 2.)
        ground = 10. + .2 * s + np.sin(s / 15.)
        profile = W.graded_profile(ground, s, maximum_grade=W.ROAD_EARTHWORKS_GRADE, cut=4., fill=3.)
        self.assertLess(float(np.max(np.abs(gaussian_free(profile) - gaussian_free(ground)))), 1.)

    def test_a_water_floor_still_lifts_a_span_and_footing_stations_are_free(self):
        s = np.arange(0., 60., 2.)
        ground = np.full(len(s), 2.)
        floor = np.where((s >= 26) & (s <= 34), 2.85, -np.inf)
        profile = W.graded_profile(ground, s, floor, maximum_grade=W.ROAD_EARTHWORKS_GRADE, cut=4., fill=3.)
        self.assertTrue(np.all(profile[(s >= 26) & (s <= 34)] >= 2.85 - 1e-9))
        free = np.zeros(len(s), bool); free[10:20] = True
        pit = ground.copy(); pit[10:20] = -20.
        held = W.graded_profile(pit, s, maximum_grade=W.ROAD_EARTHWORKS_GRADE, cut=4., fill=3., free=free)
        self.assertTrue(np.all(held[:8] - pit[:8] <= 3. + 1e-9))

    def test_the_excess_names_the_stations_no_grade_can_carry_within_the_limits(self):
        s = np.arange(0., 202., 2.)
        ground = valley(s)
        bad = W.earthworks_excess(ground, s)
        self.assertTrue(bad.any())
        centre = s[-1] * .5
        self.assertTrue(np.all(np.abs(s[bad] - centre) <= 26.))   # the walls, and the smoothing beside them
        gentle = 10. + .3 * s
        self.assertFalse(W.earthworks_excess(gentle, s).any())
        # A footing's stations carry no limit.
        self.assertFalse(W.earthworks_excess(ground, s, free=np.ones(len(s), bool)).any())


def gaussian_free(values):
    return np.asarray(values, float)


class CorridorTests(unittest.TestCase):
    def test_the_solved_corridor_and_the_written_ground_stay_within_the_limits_outside_footings(self):
        # A road across a 40 m deep, 30 m wide gully: the network's corridor would fill it; the limits cap the fill.
        x = np.arange(0., 122., 2.)
        ground = np.where(np.abs(x - 60.) <= 15., 10., 50.)
        reference = np.tile(ground, (5, 1))
        active = np.ones(reference.shape, bool)
        target = np.full(reference.shape, 50.)
        limited = np.ones(reference.shape, bool)
        result, report = W.limit_corridor_earthworks(target, active, limited, reference)
        self.assertLessEqual(float(np.max(result - reference)), W.ROAD_FILL_METRES + 1e-9)
        self.assertGreaterEqual(float(np.min(result - reference)), -W.ROAD_CUT_METRES - 1e-9)
        self.assertGreater(report['infeasibleVertices'], 0)
        # A footing (not limited) keeps the solved corridor.
        footing = limited.copy(); footing[:, 25:36] = False
        held, _ = W.limit_corridor_earthworks(target, active, footing, reference)
        np.testing.assert_array_equal(held[:, 25:36], target[:, 25:36])


def slope_world(size=240):
    world = W.World.__new__(W.World)
    world.x = np.arange(0, size + 1, W.CELL, dtype=float); world.z = np.arange(0, size + 1, W.CELL, dtype=float)
    world.x0, world.z0 = 0., 0.; world.x1, world.z1 = float(size), float(size)
    world.gx, world.gz = np.meshgrid(world.x, world.z)
    world.owner = np.zeros((len(world.z) - 1, len(world.x) - 1), int); world.ids = ['test']
    world.obstacles = np.zeros(world.gx.shape, bool); world.solids = np.zeros(world.gx.shape, bool)
    world.foundation_weight = np.zeros(world.gx.shape); world.assembly_weight = np.zeros(world.gx.shape)
    world.routing = []; world.plan = {}
    return world


class RerouteTests(unittest.TestCase):
    def test_a_leg_up_an_escarpment_is_rerouted_onto_the_gentle_ramp_beside_it(self):
        world = slope_world()
        # A 50 m escarpment across the map at z 100..130 (grade 1.7), with a gentle ramp at x 180..220 (grade .4).
        rise = np.clip((world.gz - 100.) / 30., 0, 1) * 50.
        ramp = np.clip((world.gz - 60.) / 125., 0, 1) * 50.
        on_ramp = (world.gx >= 180) & (world.gx <= 220)
        world.height = np.where(on_ramp, ramp, rise)
        world.original_height = world.height.copy()
        points = world.route(np.array([60., 40.]), np.array([60., 200.]), region='test')
        record = world.routing[-1]
        self.assertIn('earthworks', record)
        direct = W.earthworks_excess(W.triangle_sample(world.height, np.full(81, 60.), np.linspace(40, 200, 81)), np.linspace(0, 160, 81))
        self.assertTrue(direct.any())
        self.assertLess(record['earthworks']['excessMetres'], float(direct.sum() * 2.))
        self.assertTrue(np.any((points[:, 0] >= 170) & (points[:, 1] >= 90) & (points[:, 1] <= 140)))


if __name__ == '__main__':
    unittest.main()
