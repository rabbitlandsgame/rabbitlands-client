"""Focused shader-policy and ray-hit regressions for authored soft hair roots."""
import unittest
import numpy as np
import coverage


class SoftRoots(unittest.TestCase):
    def test_reference_shading_requires_explicit_capability(self):
        old = {'name': 'rl_hair_clump', 'extras': {'referenceSurface': True, 'softHairline': True}}
        self.assertFalse(coverage.uses_root_coverage(old))
        new = {'name': 'rl_hair_clump', 'extras': {**old['extras'], 'softRootCoverage': True}}
        self.assertTrue(coverage.uses_root_coverage(new))
        new['extras']['softHairline'] = False
        self.assertFalse(coverage.uses_root_coverage(new))

    def test_cards_keep_their_own_colour_semantics(self):
        self.assertFalse(coverage.uses_root_coverage({'name': 'rl_hair_card', 'extras': {
            'softHairline': True, 'softRootDetails': True}}))
        self.assertTrue(coverage.uses_root_coverage({'name': 'rl_hair_clump', 'extras': {'softHairline': True}}))
        self.assertFalse(coverage.uses_root_coverage({'name': 'rl_hair_clump'}))

    def test_scissor_boundary_and_texture_multiply(self):
        alpha = coverage.root_alpha(np.array([-.1, 0., .249, .25, .5, 1.]))
        np.testing.assert_allclose(alpha[[0, 1, 3, 4, 5]], [0., 0., .5, 1., 1.])
        self.assertLess(alpha[2], coverage.ALPHA_SCISSOR)
        self.assertLess(float(coverage.root_alpha(.25)) * .8, coverage.ALPHA_SCISSOR)
        self.assertGreater(float(coverage.root_alpha(.4)) * .8, coverage.ALPHA_SCISSOR)

    def test_rays_use_interpolated_coverage_not_a_triangle_average(self):
        try:
            coverage._bvh()
        except ImportError as error:
            self.skipTest('BVH backend unavailable: ' + str(error))
        key = 'soft-root-regression-atlas'
        previous = coverage._TEX.get(key)
        coverage._TEX[key] = np.full((1, 1), .8)
        try:
            hair = {'P': np.array([[-1., 0., -1.], [1., 0., -1.], [0., 0., 1.]]),
                    'T': np.array([[0, 1, 2]]), 'UV': np.array([[0., 0.], [1., 0.], [.5, 1.]]),
                    'A': np.ones(3), 'R': np.array([0., .5, .5]), 'tex': np.array([key]),
                    'root_coverage': np.array([True]), 'targets': {}}
            origins = np.array([[0., -1., 0.], [0., -1., -.8]])
            scene = coverage._Scene(hair, np.zeros((0, 3)), np.zeros((0, 3), int), {}, 0.)
            np.testing.assert_array_equal(scene.escapes(origins, [0., 1., 0.]), [False, True])
            hair['root_coverage'][:] = False
            scene = coverage._Scene(hair, np.zeros((0, 3)), np.zeros((0, 3), int), {}, 0.)
            np.testing.assert_array_equal(scene.escapes(origins, [0., 1., 0.]), [False, False])
        finally:
            if previous is None:coverage._TEX.pop(key, None)
            else:coverage._TEX[key] = previous


if __name__ == '__main__':
    unittest.main()
