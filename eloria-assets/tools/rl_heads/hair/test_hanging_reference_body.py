"""Regression cases from imported curly/wavy hanging-hair body support."""
import unittest
import numpy as np
from hanging_reference_body import (assert_local_bound, contact_step,
                                    high_body_triangle_mask,
                                    shared_control_influence, shared_control_vectors,
                                    shared_displacement)


class HangingReferenceBodyTests(unittest.TestCase):
    def test_uv_split_endpoint_gap_is_closed_for_all_four_controls(self):
        # Vertices 1 and 3 are separate UV copies of the same geometric point.
        weld = np.array([0, 1, 2, 1])
        scale = np.array([1., 1., 1., .125])
        fields = [np.tile(v, (4, 1)) for v in
                  [[0, -.04, -.015], [0, .03, 0], [.012, 0, 0], [-.008, 0, 0]]]
        self.assertGreater(np.linalg.norm(fields[0][1] * scale[1]
                                          - fields[0][3] * scale[3]), .03)
        coherent = shared_control_influence(scale, weld)
        for field in fields:
            np.testing.assert_array_equal(field[1] * coherent[1], field[3] * coherent[3])
        # An endpoint triangle contact on one copy reduces both copies together.
        limited = shared_control_influence(coherent, weld, blocked=[False, True, False, False])
        np.testing.assert_array_equal(limited, [1., .0625, 1., .0625])
        # Useful noncontact motion remains unchanged and opposite in direction.
        self.assertGreater(np.linalg.norm(fields[0][0] - fields[1][0]), .07)

    def test_lower_back_contact_does_not_climb_the_shoulder(self):
        # The back point is truly inside by 9.55 mm. An upward step leaves the
        # same depth intersection; an outward step clears its local back plane.
        points = np.array([[0., 1.403, -.120], [.136, 1.46, -.04]])
        closest = np.array([[0., 1.403, -.12955], [.136, 1.478, -.04]])
        step, roof = contact_step(points, closest, [[0, 0, -1], [0, 1, 0]],
                                 [-.00955, -.018], margin_m=.0028,
                                 shoulder_floor_y=1.46, shoulder_ceiling_y=1.56,
                                 maximum_probe_y=1.58)
        np.testing.assert_array_equal(roof, [False, True])
        self.assertEqual(step[0, 1], 0.)
        self.assertLess(step[0, 2], -.012)
        np.testing.assert_array_equal(step[1, [0, 2]], [0., 0.])
        self.assertGreaterEqual((closest[0, 2] - (points[0] + step[0])[2]), .0028 - 1e-12)

    def test_noncontact_and_fixed_cap_groups_remain_exact(self):
        P = np.zeros((5, 3))
        D = np.array([[0, .004, 0], [0, 0, 0], [0, .002, 0], [0, .005, 0], [0, 0, 0]])
        weld = np.array([0, 0, 1, 1, 2])
        coherent = shared_displacement(P, D, weld, fixed=[False, True, False, False, False])
        np.testing.assert_array_equal(coherent[:2], np.zeros((2, 3)))
        np.testing.assert_array_equal(coherent[2:4], [[0, .005, 0], [0, .005, 0]])
        np.testing.assert_array_equal(coherent[4], D[4])

    def test_body_allowance_is_explicit_and_does_not_change_head_bound(self):
        P = np.zeros((1, 3));Q = np.array([[0, .03486, 0]])
        with self.assertRaises(ValueError):
            assert_local_bound(P, Q, maximum_mm=32)
        self.assertAlmostEqual(assert_local_bound(P, Q, maximum_mm=38), 34.86)
        with self.assertRaises(ValueError):
            assert_local_bound(P, Q, maximum_mm=14)

    def test_coincident_contact_uses_valid_actual_surface_normal(self):
        step, roof = contact_step([[0, 1.4, -.12]], [[0, 1.4, -.12]], [[0, 0, -2]],
                                 [0], margin_m=.0028, shoulder_floor_y=1.46,
                                 shoulder_ceiling_y=1.56, maximum_probe_y=1.58)
        np.testing.assert_array_equal(roof, [False])
        np.testing.assert_allclose(step, [[0, 0, -.0028]])
        with self.assertRaises(ValueError):
            shared_control_influence([float('nan')], np.array([0]))

    def test_small_prior_vector_mismatch_is_bounded_and_requires_new_gate(self):
        original = np.array([[.003, .00168, 0], [.003, 0, 0]])
        fixed = shared_control_vectors(original, np.array([0, 0]),
                                       maximum_reconciliation_mm=2)
        np.testing.assert_array_equal(fixed[0], fixed[1])
        np.testing.assert_allclose(fixed[:, 1], [.00084, .00084])
        with self.assertRaises(ValueError):
            shared_control_vectors([[0, -.04, 0], [0, 0, 0]], np.array([0, 0]),
                                   maximum_reconciliation_mm=2)

    def test_high_body_cut_requires_exact_source_and_replacement_patch(self):
        cut = {'bodySHA256': 'actual-source-hash', 'hiddenBodyTriangles': [[1, 2], [5, 1]]}
        keep = high_body_triangle_mask(7, cut, source_sha256='actual-source-hash',
                                       head_materials=['rl_skin', 'rl_bodypatch'])
        np.testing.assert_array_equal(keep, [True, False, False, True, True, False, True])
        with self.assertRaises(ValueError):
            high_body_triangle_mask(7, cut, source_sha256='wrong-source',
                                    head_materials=['rl_skin', 'rl_bodypatch'])
        with self.assertRaises(ValueError):
            high_body_triangle_mask(7, cut, source_sha256='actual-source-hash',
                                    head_materials=['rl_skin'])


if __name__ == '__main__':
    unittest.main()
