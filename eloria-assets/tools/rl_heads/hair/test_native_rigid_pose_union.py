import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from native_rigid_pose_union import RigidNativePoseUnion


def record(name, transform):
    return {'sex': 'female', 'quality': 0, 'case': name, 'clip': 'Idle_Subtle',
            'fraction': .5, 'rl_hair_identity_controls': {},
            'bone_deltas': {'Head': np.vstack([transform[:3, :3].T,
                                              transform[:3, 3]]).tolist()}}


class Plane:
    def __init__(self, x, sign=1.):
        self.x = x
        self.sign = sign
        self.queries = []

    def signed(self, points):
        self.queries.append(points.copy())
        cp = points.copy()
        cp[:, 0] = self.x
        return ((points[:, 0] - self.x) * self.sign, cp,
                np.tile([self.sign, 0., 0.], (len(points), 1)))


class RigidPoseUnionTests(unittest.TestCase):
    def make(self, records, surfaces, **kwargs):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        manifest = Path(folder.name) / 'manifest.json'
        manifest.write_text(json.dumps({'hair_identity_policy': 'native_fixed_skull',
                                        'cases': records}))
        calls = []

        def loader(path, rec, **options):
            calls.append(options)
            return surfaces[rec['case']]

        with patch('native_rigid_pose_union.load_fixture', loader), patch(
                'native_rigid_pose_union.verified_fixture_signature',
                lambda path, rec: ('fixture-' + rec['case'], [])):
            union = RigidNativePoseUnion(manifest, 'female', **kwargs)
        return union, calls

    def test_world_query_and_inverse_closest_normal(self):
        transform = np.array([[0., -1., 0., 2.], [1., 0., 0., 3.],
                              [0., 0., 1., 4.], [0., 0., 0., 1.]])
        plane = Plane(1.)
        union, calls = self.make([record('idle', transform)], {'idle': plane},
                                 horizontal_slice_proof=True)
        points = np.array([[.25, .5, .75]])
        d, cp, n = union.signed(points)
        np.testing.assert_array_equal(plane.queries[0], [[1.5, 3.25, 4.75]])
        np.testing.assert_array_equal(d, [.5])
        np.testing.assert_array_equal(cp, [[.25, 1., .75]])
        np.testing.assert_array_equal(n, [[0., -1., 0.]])
        self.assertEqual(calls, [{'horizontal_slice_proof': True}])

    def test_minimum_fixture(self):
        records = [record('a', np.eye(4)), record('b', np.eye(4))]
        union, _ = self.make(records, {'a': Plane(0.), 'b': Plane(.2)})
        d, cp, n = union.signed([[.5, 0., 0.]])
        np.testing.assert_allclose(d, [.3])
        np.testing.assert_array_equal(cp, [[.2, 0., 0.]])
        np.testing.assert_array_equal(n, [[1., 0., 0.]])

    def test_equal_distance_keeps_first_physical_witness(self):
        records = [record('a', np.eye(4)), record('b', np.eye(4))]
        union, _ = self.make(records, {'a': Plane(-.5), 'b': Plane(.5, -1.)})
        d, cp, n = union.signed([[0., 0., 0.]])
        np.testing.assert_array_equal(d, [.5])
        np.testing.assert_array_equal(cp, [[-.5, 0., 0.]])
        np.testing.assert_array_equal(n, [[1., 0., 0.]])

    def test_nonrigid_and_reflected_carriers_fail_closed(self):
        for x in [2., -1.]:
            transform = np.eye(4)
            transform[0, 0] = x
            with self.assertRaises(AssertionError):
                self.make([record('a', transform)], {'a': Plane(0.)})

    def test_explicit_pose_selection_and_missing_pose(self):
        records = [record('a', np.eye(4)), record('b', np.eye(4))]
        union, calls = self.make(records, {'a': Plane(0.), 'b': Plane(1.)}, case_names=['b'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(union.source['poses'][0]['case'], 'b')
        with self.assertRaises(AssertionError):
            self.make(records, {'a': Plane(0.), 'b': Plane(1.)}, case_names=['absent'])

    def test_empty_points_skip_queries(self):
        plane = Plane(0.)
        union, _ = self.make([record('a', np.eye(4))], {'a': plane})
        d, cp, n = union.signed(np.empty((0, 3)))
        self.assertEqual(d.shape, (0,))
        self.assertEqual(cp.shape, (0, 3))
        self.assertEqual(n.shape, (0, 3))
        self.assertEqual(plane.queries, [])

    def test_closest_section_option_is_explicit_and_recorded(self):
        union, calls = self.make([record('a', np.eye(4))], {'a': Plane(0.)},
                                 closest_section_proof=True)
        self.assertEqual(calls, [{'horizontal_slice_proof': False, 'closest_section_proof': True}])
        self.assertTrue(union.source['closest_section_proof'])
        self.assertEqual(len(union.source['closest_section_tool_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
