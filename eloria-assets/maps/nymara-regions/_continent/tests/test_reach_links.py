"""Reach links: authored ground written onto the finished composition."""
import types
import unittest

import numpy as np

import landscape as L
import reach_links as R


def world(plan, size=(41, 61), cell=2.):
    rows, cols = size
    x = np.arange(cols) * cell
    z = np.arange(rows) * cell
    gx, gz = np.meshgrid(x, z)
    return types.SimpleNamespace(plan=plan, gx=gx, gz=gz, height=10. + gx * .8)


RAMP = {'id': 'link', 'name': 'a link up the slope', 'op': 'ramp', 'shape': {'polyline': {'points': [[20., 40.], [80., 40.]], 'width': 8.}},
        'heights': [26., 50.], 'feather': 6., 'strength': 1}


class ValidationTests(unittest.TestCase):
    def test_absent_or_empty_links_are_valid(self):
        self.assertEqual(R.validate_reach_links({}), [])
        self.assertEqual(R.validate_reach_links({'reach_links': []}), [])

    def test_links_use_the_terrain_edit_schema_and_say_reach_link(self):
        self.assertEqual(R.validate_reach_links({'reach_links': [RAMP], 'bounds': [0, 0, 200, 200]}), [])
        broken = dict(RAMP, heights=[26.])
        problems = R.validate_reach_links({'reach_links': [broken], 'bounds': [0, 0, 200, 200]})
        self.assertTrue(problems and all('reach link' in p for p in problems), problems)
        self.assertEqual(R.validate_reach_links({'reach_links': {'id': 'x'}}), ["'reach_links' must be a list of links"])


class ApplyTests(unittest.TestCase):
    def _walls(self, before, after, band):
        """The largest step between neighbouring cells outside the bands, beyond what the ground before allowed."""
        worst = 0.
        for axis in (0, 1):
            step = np.abs(np.diff(after, axis=axis)); natural = np.abs(np.diff(before, axis=axis))
            allowed = np.maximum(R.WALL_METRES, natural + R.CATCH_UP_METRES)
            free = (~band[1:, :] & ~band[:-1, :]) if axis == 0 else (~band[:, 1:] & ~band[:, :-1])
            worst = max(worst, float((step - allowed)[free].max(initial=0.)))
        return worst

    def test_links_blend_the_finished_ground_as_terrain_edits_do_then_smooth_outside_the_band(self):
        w = world({'reach_links': [RAMP]})
        before = w.height.copy()
        blended = L._terrain_edit_height(w.gx, w.gz, before.copy(), {'terrain_edits': [RAMP]})
        band = np.asarray(L._edit_weight(w.gx, w.gz, RAMP)) >= .999
        report = R.apply_reach_links(w)
        # The band keeps the ramp's own surface exactly; on the line it is the ramp's height.
        np.testing.assert_array_equal(w.height[band], blended[band])
        self.assertAlmostEqual(float(w.height[20, 25]), 26. + 24. * (50. - 20.) / 60., places=9)
        self.assertLessEqual(self._walls(before, w.height, band), 1e-9)
        self.assertEqual(float(w.height[0, 0]), 10.)
        self.assertEqual(report['links'], 1)
        self.assertGreater(report['changedCells'], 0)
        self.assertIn('smoothing', report)
        self.assertEqual(w.reach_links, report)

    def test_a_deep_cut_ends_as_a_terrace_not_a_wall(self):
        steep = world({})
        steep.height = 10. + steep.gz * 1.2        # a steep face rising south, 2.4 m between rows
        cut = {'id': 'bench', 'op': 'flatten', 'shape': {'circle': {'center': [60., 40.], 'radius': 4.}}, 'target': 36.,
               'feather': 1., 'strength': 1}
        steep.plan = {'reach_links': [cut]}
        before = steep.height.copy()
        hard = L._terrain_edit_height(steep.gx, steep.gz, before.copy(), {'terrain_edits': [cut]})
        band = np.asarray(L._edit_weight(steep.gx, steep.gz, cut)) >= .999
        self.assertGreater(self._walls(before, hard, band), 5.)
        report = R.apply_reach_links(steep)
        self.assertLessEqual(self._walls(before, steep.height, band), 1e-9)
        np.testing.assert_array_equal(steep.height[band], hard[band])
        self.assertGreater(report['smoothing']['widenedCells'], 0)

    def test_smoothing_never_moves_ground_that_can_carry_walking(self):
        w = world({})
        w.height = np.where(w.gx < 60., 10., 10. + (w.gx - 60.) * 1.5)   # a walkable meadow west, a steep face east
        cut = {'id': 'pit', 'op': 'flatten', 'shape': {'circle': {'center': [60., 40.], 'radius': 6.}}, 'target': 2.,
               'feather': 1., 'strength': 1}
        w.plan = {'reach_links': [cut]}
        linked = L._terrain_edit_height(w.gx, w.gz, w.height.copy(), {'terrain_edits': [cut]})
        walk = R._walk_corners(linked, 2.)
        report = R.apply_reach_links(w)
        np.testing.assert_array_equal(w.height[walk], linked[walk])
        self.assertTrue(R._walk_corners(w.height, 2.)[walk].all())
        smoothing = report['smoothing']
        self.assertGreater(smoothing['widenedCells'], 0)        # the steep face east of the pit is terraced
        self.assertGreater(smoothing['wallsLeft'], 0)           # the pit's wall beside the meadow stays
        self.assertGreater(smoothing['tallestWallLeftMetres'], R.WALL_METRES)

    def test_crowded_legs_share_the_fall_between_them(self):
        w = world({})
        w.height = 10. + w.gz * 2.5                     # a steep face, 5 m between rows
        low = {'id': 'leg-1', 'op': 'ramp', 'shape': {'polyline': {'points': [[10., 30.], [110., 30.]], 'width': 4.}},
               'heights': [85., 85.], 'feather': 1., 'strength': 1}
        high = dict(low, id='leg-2', shape={'polyline': {'points': [[10., 40.], [110., 40.]], 'width': 4.}}, heights=[105., 105.])
        w.plan = {'reach_links': [low, high]}
        linked = L._terrain_edit_height(w.gx, w.gz, w.height.copy(), {'terrain_edits': [low, high]})
        walk = R._walk_corners(linked, 2.)
        report = R.apply_reach_links(w)
        # 20 m between the band edges (rows 16 and 19) cannot fit the natural 5 m + 1 m a row: the passes share it out.
        raw_steps = np.abs(np.diff(linked[16:20, 5:56], axis=0))
        steps = np.abs(np.diff(w.height[16:20, 5:56], axis=0))
        self.assertGreater(float(raw_steps.max()), 9.)
        self.assertLessEqual(float(steps.max()), R.WALL_METRES * R.WALL_GROWTH ** 2 + 1e-9)
        np.testing.assert_allclose(steps.sum(axis=0), 20.)
        np.testing.assert_array_equal(w.height[walk], linked[walk])
        self.assertGreater(report['smoothing']['relaxedCells'], 0)
        self.assertEqual(report['smoothing']['unplacedCells'], 0)

    def test_smoothing_leaves_river_centrelines_and_compound_ground_unchanged(self):
        plan = {'reach_links': [RAMP], 'rivers': [{'id': 'brook', 'points': [[20., 62.], [80., 62.]]}]}
        w = world(plan)
        w.height = 10. + w.gz * 1.5
        before = w.height.copy()
        R.apply_reach_links(w)
        river_row = int(round(62. / 2.))
        np.testing.assert_allclose(w.height[river_row, 10:41], before[river_row, 10:41], atol=1e-9)

    def test_no_links_leave_the_ground_alone(self):
        w = world({})
        before = w.height.copy()
        self.assertEqual(R.apply_reach_links(w), {'links': 0, 'perLink': []})
        np.testing.assert_array_equal(w.height, before)

    def test_a_link_reaching_a_river_centreline_is_refused(self):
        plan = {'reach_links': [RAMP], 'rivers': [{'id': 'brook', 'points': [[50., 30.], [50., 50.]]}]}
        with self.assertRaisesRegex(ValueError, "'link' reaches river centrelines"):
            R.apply_reach_links(world(plan))
        clear = {'reach_links': [RAMP], 'rivers': [{'id': 'brook', 'points': [[50., 70.], [60., 80.]]}]}
        R.apply_reach_links(world(clear))

    def test_a_link_moving_the_ground_under_a_rigid_compound_member_is_refused(self):
        member = {'region': 'test', 'node': 'Hall', 'assembly': 'test.hall', 'low': [44., 0., 45.], 'high': [50., 6., 52.]}
        content = types.SimpleNamespace(objects=[member])
        with self.assertRaisesRegex(ValueError, 'rigid compound members'):
            R.apply_reach_links(world({'reach_links': [RAMP]}), content)
        # A loose placement is regrounded afterwards, so it does not stop the link.
        loose = dict(member, assembly=None)
        R.apply_reach_links(world({'reach_links': [RAMP]}), types.SimpleNamespace(objects=[loose]))
        # Nor does a member whose ground the link moves within the tolerance: a ramp that follows the ground there.
        w = world({})
        gentle = dict(RAMP, heights=[10. + 20. * .8, 10. + 80. * .8])
        w.plan = {'reach_links': [gentle]}
        R.apply_reach_links(w, content)

    def test_a_tree_member_is_judged_at_its_trunk_not_its_canopy(self):
        # A giant tree whose canopy box spans the link but whose trunk stands 20 m clear of it.
        tree = {'region': 'test', 'node': 'Giant', 'kind': 'tree', 'assembly': 'test.village',
                'low': [30., 0., 20.], 'high': [70., 30., 60.], 'sourcePivot': [0., 0., 0.], 'shift': [50., 0., 62.]}
        R.apply_reach_links(world({'reach_links': [RAMP]}), types.SimpleNamespace(objects=[tree]))
        standing = dict(tree, shift=[50., 0., 40.])
        with self.assertRaisesRegex(ValueError, 'rigid compound members'):
            R.apply_reach_links(world({'reach_links': [RAMP]}), types.SimpleNamespace(objects=[standing]))

    def test_an_elevated_walkway_member_does_not_hold_the_ground_under_its_box(self):
        walkway = {'region': 'test', 'node': 'Landmark_CanopyWalkway_9', 'kind': 'landmark', 'assembly': 'test.village',
                   'low': [0., 40., 0.], 'high': [120., 46., 80.]}
        R.apply_reach_links(world({'reach_links': [RAMP]}), types.SimpleNamespace(objects=[walkway]))
        stair = dict(walkway, node='Walk_Prop_SpiralStair_2')
        with self.assertRaisesRegex(ValueError, 'rigid compound members'):
            R.apply_reach_links(world({'reach_links': [RAMP]}), types.SimpleNamespace(objects=[stair]))

    def test_invalid_links_are_refused_before_the_ground_changes(self):
        w = world({'reach_links': [dict(RAMP, op='smooth')]})
        before = w.height.copy()
        with self.assertRaisesRegex(ValueError, 'Reach links'):
            R.apply_reach_links(w)
        np.testing.assert_array_equal(w.height, before)


if __name__ == '__main__':
    unittest.main()
