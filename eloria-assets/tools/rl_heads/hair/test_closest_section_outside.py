import unittest
import numpy as np
import trimesh
from closest_section_outside import ClosestSectionOutside, _simple, fallback_plane_normals
from native_hair_fixtures import EvaluatedNativeSurface, check_hair


def u_mesh():
    parts = []
    for center, size in [((-.75, 0, 0), (.5, 2, .6)),
                         ((.75, 0, 0), (.5, 2, .6)),
                         ((0, -1, 0), (2, .5, .6))]:
        mesh = trimesh.creation.box(extents=size)
        mesh.apply_translation(center)
        parts.append(mesh)
    return trimesh.util.concatenate(parts)


class ClosestSectionCertificates(unittest.TestCase):
    def test_concave_gap_inside_full_bounds_has_complete_outside_certificate(self):
        mesh = u_mesh()
        point = np.array([[.1, .13, .017]])
        cp, _, _ = trimesh.proximity.closest_point(mesh, point)
        self.assertTrue(((point > mesh.bounds[0]) & (point < mesh.bounds[1])).all())
        proof = ClosestSectionOutside(mesh)
        self.assertTrue(proof.outside(point, cp)[0])
        self.assertEqual(proof.last_query['proven_outside_points'], 1)

    def test_inside_points_and_nested_components_do_not_cancel(self):
        outer = trimesh.creation.box(extents=[2, 2, 2])
        inner = trimesh.creation.box(extents=[1, 1, 1])
        mesh = trimesh.util.concatenate([outer, inner])
        points = np.array([[.13, .17, .19], [.73, .11, .13]])
        cp, _, _ = trimesh.proximity.closest_point(mesh, points)
        self.assertFalse(ClosestSectionOutside(mesh).outside(points, cp).any())

    def test_open_and_degenerate_sections_are_withheld(self):
        box = trimesh.creation.box(extents=[2, 2, 2])
        # Remove a side crossed by the supplied plane, leaving an open contour.
        box.update_faces(box.face_normals[:, 2] < .5)
        point = np.array([[.13, 1.3, .17]])
        orientation_seed = point - [1, 0, 0]
        self.assertFalse(ClosestSectionOutside(box).outside(point, orientation_seed)[0])
        flat = trimesh.Trimesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]], process=False)
        self.assertFalse(ClosestSectionOutside(flat).outside([[.1, .1, .1]], [[.1, .1, 0]])[0])

    def test_boundary_coplanar_and_zero_separation_are_withheld(self):
        mesh = trimesh.creation.box(extents=[2, 2, 2])
        points = np.array([[1., .13, .17], [.1, .1, .1], [1., 1., 1.]])
        closest = np.array([[1., .13, .17], [0., .1, .1], [0., 0., 0.]])
        self.assertFalse(ClosestSectionOutside(mesh).outside(points, closest).any())

    def test_self_crossing_and_touching_contours_are_rejected(self):
        self.assertFalse(_simple(np.array([[0., 0.], [2, 2], [0, 2], [2, 0]]), 1e-8))
        self.assertFalse(_simple(np.array([[0., 0.], [2, 0], [1, 1], [1, 0], [0, 1]]), 1e-8))
        self.assertTrue(_simple(np.array([[0., 0.], [1, 0], [2, 0], [2, 1], [0, 1]]), 1e-8))

    def test_native_adapter_is_opt_in_and_preserves_distance_cp_and_normal(self):
        mesh = u_mesh()
        point = np.array([[.1, .13, .017]])
        inward_shading_normals = -mesh.vertex_normals
        old = EvaluatedNativeSurface(mesh.vertices, inward_shading_normals, mesh.faces,
                                     horizontal_slice_proof=True, complete_fixture_mesh=mesh)
        new = EvaluatedNativeSurface(mesh.vertices, inward_shading_normals, mesh.faces,
                                     horizontal_slice_proof=True, complete_fixture_mesh=mesh,
                                     closest_section_proof=True)
        d0, cp0, n0 = old.signed(point)
        d1, cp1, n1 = new.signed(point)
        self.assertLess(d0[0], 0)
        self.assertEqual(d1[0], abs(d0[0]))
        np.testing.assert_array_equal(cp1, cp0)
        np.testing.assert_array_equal(n1, n0)
        with self.assertRaises(AssertionError):
            EvaluatedNativeSurface(mesh.vertices, inward_shading_normals, mesh.faces,
                                   closest_section_proof=True)

    def test_alternative_plane_certifies_after_coplanar_first_plane_withholds(self):
        mesh = trimesh.creation.box(extents=[2, 2, 2])
        point = np.array([[1.3, .13, 1.]])
        seed = point - [0, 0, 1]
        old = ClosestSectionOutside(mesh)
        zero = ClosestSectionOutside(mesh, fallback_plane_count=0)
        new = ClosestSectionOutside(mesh, fallback_plane_count=64)
        self.assertFalse(old.outside(point, seed)[0])
        np.testing.assert_array_equal(old.outside(point, seed), zero.outside(point, seed))
        self.assertEqual(old.last_query, zero.last_query)
        self.assertTrue(new.outside(point, seed)[0])
        self.assertEqual(new.last_query['fallback_plane_count'], 64)

    def test_fixed_schedule_prefix_and_first_valid_stop(self):
        mesh = trimesh.creation.box(extents=[2, 2, 2])
        point = np.array([1.3, .13, 1.])
        calls = []
        proof = ClosestSectionOutside(mesh, fallback_plane_count=3)
        schedule = fallback_plane_normals()
        self.assertEqual(schedule.shape, (64, 3))
        self.assertEqual(schedule[0, 1], 63 / 64)

        def certificate(p, cp):
            normal = p - cp
            calls.append(normal.copy())
            return (bool(np.allclose(normal, schedule[1], atol=1e-14, rtol=0)), 'test')

        proof._certificate = certificate
        self.assertTrue(proof.outside(point[None], (point - [0, 0, 1])[None])[0])
        self.assertEqual(len(calls), 3)  # Original plane, then schedule indices 0/1.
        np.testing.assert_allclose(calls[1:], schedule[:2], atol=1e-15, rtol=0)

    def test_fallback_does_not_certify_inside_nested_or_open_sections(self):
        outer = trimesh.creation.box(extents=[2, 2, 2])
        inner = trimesh.creation.box(extents=[1, 1, 1])
        mesh = trimesh.util.concatenate([outer, inner])
        points = np.array([[.13, .17, .19], [.73, .11, .13]])
        cp, _, _ = trimesh.proximity.closest_point(mesh, points)
        self.assertFalse(ClosestSectionOutside(mesh, fallback_plane_count=64).outside(points, cp).any())
        triangle = trimesh.Trimesh([[0, 0, 0], [1, 0, .2], [0, 1, .4]],
                                   [[0, 1, 2]], process=False)
        self.assertFalse(ClosestSectionOutside(triangle, fallback_plane_count=64)
                         .outside([[.4, .3, .5]], [[0, 0, 0]])[0])

    def test_fallback_validation_and_explicit_adapter_gate(self):
        mesh = trimesh.creation.box()
        for count in [-1, 65, .5, True, '2']:
            with self.assertRaises(AssertionError):
                ClosestSectionOutside(mesh, fallback_plane_count=count)
        with self.assertRaises(AssertionError):
            EvaluatedNativeSurface(mesh.vertices, mesh.vertex_normals, mesh.faces,
                                   complete_fixture_mesh=mesh, closest_section_fallback_planes=1)
        with self.assertRaises(AssertionError):
            check_hair('absent.glb', 'absent.json', closest_section_fallback_planes=64)

    def test_fallback_adapter_retains_original_distance_witness_and_normal(self):
        mesh = u_mesh();point = np.array([[.1, .13, .017]])
        old = EvaluatedNativeSurface(mesh.vertices, -mesh.vertex_normals, mesh.faces,
                                     closest_section_proof=True, complete_fixture_mesh=mesh)
        new = EvaluatedNativeSurface(mesh.vertices, -mesh.vertex_normals, mesh.faces,
                                     closest_section_proof=True, complete_fixture_mesh=mesh,
                                     closest_section_fallback_planes=64)
        for before, after in zip(old.signed(point), new.signed(point)):
            np.testing.assert_array_equal(before, after)


if __name__ == '__main__':
    unittest.main()
