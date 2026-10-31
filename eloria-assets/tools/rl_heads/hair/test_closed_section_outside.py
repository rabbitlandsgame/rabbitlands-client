import unittest
import numpy as np
import trimesh
from closed_section_outside import ClosedSectionOutside
from high_contact_bounds import ContactHead


class ClosedSectionTests(unittest.TestCase):
    def box(self, extents=(2, 2, 2), offset=(0, 0, 0)):
        mesh = trimesh.creation.box(extents=extents)
        mesh.apply_translation(offset)
        return mesh

    def test_inside_outside_and_boundary(self):
        proof = ClosedSectionOutside(self.box())
        points = np.array([[0, .123, 0], [1.1, .123, 0], [1, .123, 0]])
        np.testing.assert_array_equal(proof.outside(points), [False, True, False])

    def test_gap_between_independent_contours_inside_combined_bounds(self):
        mesh = trimesh.util.concatenate([self.box((.4, 2, .4), (-.5, 0, 0)), self.box((.4, 2, .4), (.5, 0, 0))])
        np.testing.assert_array_equal(ClosedSectionOutside(mesh).outside(np.array([[0, .123, 0], [-.5, .123, 0]])), [True, False])

    def test_concave_closed_contour(self):
        # L-shaped prism, with a real outside pocket inside its section bounds.
        polygon = np.array([[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2.]])
        vertices = np.array([[x, y, z] for y in [-1, 1] for x, z in polygon])
        faces = []
        for i in range(6):
            j = (i + 1) % 6
            faces += [[i, j, j + 6], [i, j + 6, i + 6]]
        mesh = trimesh.Trimesh(vertices, faces, process=False)
        np.testing.assert_array_equal(ClosedSectionOutside(mesh).outside(np.array([[1.5, .123, 1.5], [.5, .123, 1.5]])), [True, False])

    def test_overlapping_and_nested_contours_cannot_cancel(self):
        mesh = trimesh.util.concatenate([self.box(), self.box((1, 1, 1)), self.box(offset=(.5, 0, .1))])
        np.testing.assert_array_equal(ClosedSectionOutside(mesh).outside(np.array([[0, .123, 0], [.75, .123, 0], [2, .123, 0]])), [False, False, True])

    def test_open_and_branched_sections_provide_no_proof(self):
        mesh = self.box()
        mesh.update_faces(np.arange(len(mesh.faces)) != 0)
        self.assertFalse(ClosedSectionOutside(mesh).outside(np.array([[2, -.5, 0]]))[0])
        touching = trimesh.util.concatenate([self.box(), self.box(offset=(2, 0, 2))])
        self.assertFalse(ClosedSectionOutside(touching).outside(np.array([[4, .123, 0]]))[0])

    def test_empty_and_vertex_planes_provide_no_proof(self):
        points = np.array([[2, 3, 0], [2, 1, 0], [2, 1 - 1e-10, 0]])
        np.testing.assert_array_equal(ClosedSectionOutside(self.box()).outside(points), [False, False, False])

    def test_reversed_winding_has_identical_proof(self):
        mesh = self.box()
        reversed_mesh = trimesh.Trimesh(mesh.vertices, mesh.faces[:, ::-1], process=False)
        points = np.array([[0, .123, 0], [2, .123, 0]])
        np.testing.assert_array_equal(ClosedSectionOutside(mesh).outside(points), ClosedSectionOutside(reversed_mesh).outside(points))

    def test_plane_cache_is_exact_and_bounded(self):
        mesh = self.box()
        cached, plain = ClosedSectionOutside(mesh, cache_planes=2), ClosedSectionOutside(mesh, cache_planes=0)
        points = np.array([[2, .123, 0], [2, .234, 0], [0, .345, 0]])
        for _ in range(2):
            np.testing.assert_array_equal(cached.outside(points), plain.outside(points))
            self.assertLessEqual(len(cached.cache), 2)

    def test_contact_optin_preserves_inside_distance_and_all_witnesses(self):
        mesh = trimesh.util.concatenate([self.box((.4, 2, .4), (-.5, 0, 0)), self.box((.4, 2, .4), (.5, 0, 0))])
        class Head:
            P, T = np.asarray(mesh.vertices), np.asarray(mesh.faces)
            def delta(self, name): return np.zeros_like(self.P)
            def signed(self, X, **kwargs):
                cp, distance, tri = trimesh.proximity.closest_point(mesh, X)
                result = (-distance, cp, mesh.face_normals[tri], np.zeros(len(X), bool))
                return result if kwargs.get('with_rim') else result[:3]
        points = np.array([[0, .123, 0], [-.5, .123, 0]])
        before = ContactHead(Head()).signed(points, with_rim=True)
        after = ContactHead(Head(), closed_section_proof=True).signed(points, with_rim=True)
        self.assertLess(before[0][0], 0)
        self.assertGreater(after[0][0], 0)
        self.assertEqual(before[0][1], after[0][1])
        np.testing.assert_array_equal(abs(before[0]), abs(after[0]))
        for a, b in zip(before[1:], after[1:]):
            np.testing.assert_array_equal(a, b)


if __name__ == '__main__':
    unittest.main()
