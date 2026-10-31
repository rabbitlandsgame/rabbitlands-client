import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import trimesh
import native_hair_fixtures as fixtures

class NativeFixtureChecks(unittest.TestCase):
    def test_outside_bounds_proof_preserves_distance_despite_cut_normal(self):
        box=trimesh.creation.box(extents=[2,2,2])
        normals=np.tile([0.,1,0],(len(box.vertices),1))
        original=fixtures.NativeHeadSurface(box.vertices,normals,box.faces)
        evaluated=fixtures.EvaluatedNativeSurface(box.vertices,normals,box.faces)
        point=np.array([[0.,-3,0]])
        before=original.signed(point);after=evaluated.signed(point)
        self.assertLess(before[0][0],0)
        np.testing.assert_allclose(after[0],np.abs(before[0]))
        np.testing.assert_array_equal(after[1],before[1]);np.testing.assert_array_equal(after[2],before[2])

    def test_inside_bounds_and_planar_fixture_signs_remain_strict(self):
        box=trimesh.creation.box(extents=[2,2,2])
        surface=fixtures.EvaluatedNativeSurface(box.vertices,box.vertex_normals,box.faces)
        self.assertLess(surface.signed(np.zeros((1,3)))[0][0],0)
        P=np.array([[-1.,0,0],[1,0,0],[0,1,0]])
        plane=fixtures.EvaluatedNativeSurface(P,np.tile([0.,0,1],(3,1)),np.array([[0,1,2]]))
        self.assertLess(plane.signed(np.array([[0.,.25,-.003]]))[0][0],0)

    def test_old_native_identity_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text(json.dumps({'cases': []}))
            with self.assertRaisesRegex(AssertionError, 'v2 or later'):
                fixtures.check_hair('unused', manifest)

    def test_column_basis_and_eight_influence_pose(self):
        turn = [[0, 1, 0], [-1, 0, 0], [0, 0, 1], [3, 4, 5]]
        stay = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]
        points = np.array([[2., 0, 0]])
        joints = np.array([[0, 1, 0, 1, 0, 1, 0, 1]])
        weights = np.full((1, 8), .125)
        result = fixtures.skin_positions(points, joints, weights, ['Head', 'Neck'], {'Head': turn, 'Neck': stay})
        np.testing.assert_allclose(result, [[2.5, 3., 2.5]])

    def test_signed_controls_and_grooms_mix_before_skin(self):
        controls = fixtures.identity_weights({'jaw_width': -.4, 'nose_depth': .6, 'unused': 0})
        self.assertEqual(controls, {'id_jaw_width_n': .4, 'id_nose_depth_p': .6})
        base = np.zeros((1, 3))
        targets = {'id_jaw_width_n': np.array([[1., 0, 0]]), 'id_nose_depth_p': np.array([[0., 1, 0]]),
                   'hl_length_n': np.array([[0., 0, -1]])}
        np.testing.assert_allclose(fixtures.morph_positions(base, targets, controls | {'hl_length_n': 1}), [[.4, .6, -1]])

    def test_unmapped_skin_joint_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'No evaluated native pose'):
            fixtures.skin_positions(np.zeros((1, 3)), np.zeros((1, 4), int), np.ones((1, 4)) / 4, ['Unknown'], {})

    def test_native_corrective_is_optional_and_adds_to_groom(self):
        base = np.array([[0., 1.6, .001]])
        targets = {'hl_native_fit': np.array([[0., 0, .004]]), 'hl_volume_n': np.array([[0., 0, -.001]])}
        np.testing.assert_allclose(fixtures.morph_positions(base, targets, {'hl_native_fit': 1, 'hl_volume_n': 1}), [[0, 1.6, .004]])
        np.testing.assert_array_equal(fixtures.morph_positions(base, {}, {'hl_native_fit': 1}), base)

    def test_fixture_hash_and_triangle_used_vertices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'mesh.npz'
            P = np.array([[-.1, 1.6, 0], [.1, 1.6, 0], [0, 1.8, 0], [100, 100, 100.]])
            np.savez(path, P=P, N=np.tile([0., 0, 1], (4, 1)), I=np.array([[0, 1, 2]]))
            part = {'mesh': 'body', 'file': path.name, 'sha256': fixtures.sha(path)}
            surface = fixtures.load_fixture(Path(directory) / 'manifest.json', {'parts': [part]})
            self.assertEqual(len(surface.P), 3)
            distance, _, _ = surface.signed(np.array([[0, 1.65, .003], [0, 1.65, -.004]]))
            np.testing.assert_allclose(distance, [.003, -.004])
            part['sha256'] = '0' * 64
            with self.assertRaisesRegex(AssertionError, 'fixture changed'):
                fixtures.load_fixture(Path(directory) / 'manifest.json', {'parts': [part]})

    def test_interior_contacts_and_early_failure_never_qualify(self):
        class Dome:
            def signed(self, points):
                height = np.where(np.linalg.norm(points[:, :2] - [0, 1.6], axis=1) < .02, .004, 0)
                cp = points.copy(); cp[:, 2] = height
                return points[:, 2] - height, cp, np.tile([0., 0, 1], (len(points), 1))
        P = np.array([[-.06, 1.56, .003], [.06, 1.56, .003], [0., 1.68, .003]])
        part = {'P': P, 'T': np.array([[0, 1, 2]]), 'targets': {}, 'J': np.zeros((3, 4), int),
                'W': np.tile([1., 0, 0, 0], (3, 1)), 'names': ['Head'], 'aliases': {}}
        case = {'sex': 'female', 'quality': 0, 'case': 'neutral', 'rl_hair_identity_controls': {},
                'bone_deltas': {'Head': [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]}}
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text(json.dumps({'hair_identity_policy': 'native_fixed_skull', 'cases': [case]}))
            with patch.object(fixtures, 'load_hair', return_value={'sex': 'female', 'sha256': 'test', 'levels': [[part]]}), \
                 patch.object(fixtures, 'load_fixture', return_value=Dome()), patch('builtins.print'):
                result = fixtures.check_hair('unused', manifest, lods=(0,), stop_on_first=True)
            self.assertEqual(result['failures'], 1)
            self.assertFalse(result['complete_requested_scan'])
            self.assertLess(result['cases'][0]['minimum_clearance_mm'], 0)

if __name__ == '__main__': unittest.main()
