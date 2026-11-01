import unittest
import numpy as np
from native_authoring_bvh import NativeAuthoringSurface
from native_hair_clearance import NativeHeadSurface


class CountedSource(NativeHeadSurface):
    def __init__(self, P, N, T, outside_policy=False):
        super().__init__(np.array(P, float), np.array(N, float), np.array(T, int))
        self.calls = 0
        self.outside_policy = outside_policy

    def signed(self, P):
        self.calls += len(P)
        distance, closest, normal = super().signed(P)
        if self.outside_policy:
            distance = abs(distance)
        return distance, closest, normal


class NativeAuthoringBVHTests(unittest.TestCase):
    def test_split_hard_normal_vertex_tie_is_exact_at_twelve_mm(self):
        source = CountedSource(
            [[0, 0, 0], [-1, 0, 0], [0, -1, 0],
             [0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, -1]] * 3 + [[0, 0, 1]] * 3,
            [[0, 1, 2], [3, 4, 5]])
        P = np.array([[0, 0, .012]])
        expected = source.signed(P)
        accelerated = NativeAuthoringSurface(source)
        actual = accelerated.signed(P)
        self.assertEqual(accelerated.exact_queries, 1)
        self.assertEqual(accelerated.feature_fallbacks, 1)
        for a, b in zip(expected, actual):
            np.testing.assert_array_equal(a, b)

    def test_shared_edge_tie_delegates_complete_outside_policy(self):
        source = CountedSource(
            [[-1, 0, 0], [1, 0, 0], [0, -1, 0],
             [-1, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 0, -1]] * 3 + [[0, 0, 1]] * 3,
            [[0, 1, 2], [3, 4, 5]], outside_policy=True)
        P = np.array([[0, 0, .012]])
        expected = source.signed(P)
        accelerated = NativeAuthoringSurface(source)
        actual = accelerated.signed(P)
        self.assertEqual(accelerated.feature_fallbacks, 1)
        self.assertGreater(actual[0][0], 0)
        for a, b in zip(expected, actual):
            np.testing.assert_array_equal(a, b)

    def test_unique_far_face_can_remain_accelerated(self):
        source = CountedSource([[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                               [[0, 0, 1]] * 3, [[0, 1, 2]])
        accelerated = NativeAuthoringSurface(source)
        actual = accelerated.signed(np.array([[.2, .3, .02]]))
        self.assertEqual(source.calls, 0)
        self.assertEqual(accelerated.exact_queries, 0)
        self.assertAlmostEqual(actual[0][0], .02, places=7)

    def test_unique_near_face_is_exact(self):
        source = CountedSource([[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                               [[0, 0, 1]] * 3, [[0, 1, 2]])
        P = np.array([[.2, .3, .003]])
        expected = source.signed(P)
        accelerated = NativeAuthoringSurface(source)
        actual = accelerated.signed(P)
        self.assertEqual(accelerated.exact_queries, 1)
        for a, b in zip(expected, actual):
            np.testing.assert_array_equal(a, b)


if __name__ == '__main__':
    unittest.main()
