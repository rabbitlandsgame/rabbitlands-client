"""Local channel landscape invariants, independent of a full export."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / '_toolkit'), str(HERE.parents[1] / '_finishing')]
import west_bank_finish as B


class WestBenchTests(unittest.TestCase):
    def test_broad_bank_lowered_and_existing_submerged_channel_unchanged(self):
        points = np.array([[-129.5, 22.04, -85.5], [-129.5, -2., -73.5], [-117.5, 19.06, -53.5]])
        result = B.shape(points)
        self.assertLess(result[0, 1], 6.)
        self.assertEqual(result[1, 1], -2.)
        self.assertLess(result[2, 1], 10.)
        np.testing.assert_array_equal(result[:, [0, 2]], points[:, [0, 2]])

    def test_true_shared_strip_is_exactly_preserved(self):
        z = np.linspace(-99.5, -47.5, 27)
        points = np.c_[np.full(len(z), -149.5), np.full(len(z), 20.), z]
        np.testing.assert_array_equal(B.shape(points), points)

    def test_low_ruin_footing_keeps_its_actual_ground(self):
        polygon = np.array([[-121., -96.], [-103., -96.], [-103., -84.], [-121., -84.]])
        points = np.array([[-119., 2.0846467, -90.], [-117., 15., -87.], [-129.5, 22.04, -85.5]])
        result = B.shape(points, [polygon])
        np.testing.assert_array_equal(result[:2], points[:2])
        self.assertLess(result[2, 1], points[2, 1])

    def test_far_native_core_is_unchanged_and_cap_never_raises_soil(self):
        points = np.array([[0., 12., 0.], [-129.5, 2., -85.5], [-117.5, -1., -61.5]])
        np.testing.assert_array_equal(B.shape(points), points)

    def test_tree_root_uses_actual_trunk_not_low_palm_fronds(self):
        trunk = B.F.M.box((1., 4., 1.), center=(0., 2., 0.), material='bark_pale')
        frond = B.F.M.box((8., 1., 8.), center=(0., -5., 0.), material='ssarathi_palm')
        tree = SimpleNamespace(all_parts=[trunk, frond])
        self.assertEqual(B.root_low_y(tree, 1.2), 0.)

    def test_structural_footing_mask_does_not_depend_on_terrain_lod(self):
        footing = B.F.M.box((3., 1., 4.), center=(0., .5, 0.), material='ashlar')
        roof = B.F.M.box((14., 1., 12.), center=(0., 9., 0.), material='ashlar')
        assembly = SimpleNamespace(all_parts=[footing, roof])
        placement = SimpleNamespace(node='Ruin_0',landmark=None,kind='ruin',collides=True,mesh='ruin',
                                    position=(-110.,2.,-92.),rotation_y=.3,scale=1.)
        build = SimpleNamespace(landmarks=[],placements=[placement],meshes={'ruin':assembly},terrain_meshes={})
        a = B.structural_footings(build)
        build.terrain_meshes={'coarse_fake_roof_height':B.F.M.box((30.,30.,30.))}
        b = B.structural_footings(build)
        self.assertEqual(len(a),len(b))
        for p,q in zip(a,b):
            np.testing.assert_array_equal(p,q)
            self.assertLess(np.ptp(p[:,0]),5.)


if __name__ == '__main__':
    unittest.main()
