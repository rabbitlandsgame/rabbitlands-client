"""The optional native outside proof need only visit negative signed rows."""
import unittest
from unittest.mock import patch
import numpy as np
import trimesh
import native_hair_fixtures as fixtures


class NegativeProofTests(unittest.TestCase):
    def surface(self):
        mesh=trimesh.creation.box()
        return fixtures.EvaluatedNativeSurface(mesh.vertices,mesh.vertex_normals,
            mesh.faces,horizontal_slice_proof=True,complete_fixture_mesh=mesh)

    def check_reference(self,distance,outside):
        surface=self.surface();points=np.arange(len(distance)*3,dtype=float).reshape(-1,3)
        closest=points+0.125;normals=np.tile([0.,0,1],(len(points),1))
        reference=np.asarray(distance,float).copy()
        reference[outside]=np.abs(reference[outside])
        calls=[]
        def proof(query):
            calls.append(query.copy())
            indices=np.asarray(query[:,0]/3,dtype=int)
            return np.asarray(outside)[indices]
        with patch.object(fixtures.NativeHeadSurface,'signed',return_value=(
                np.asarray(distance,float).copy(),closest,normals)), \
             patch.object(surface,'proven_outside',side_effect=proof):
            result=surface.signed(points)
        self.assertEqual(result[0].tobytes(),reference.tobytes())
        self.assertIs(result[1],closest);self.assertIs(result[2],normals)
        return points,calls

    def test_mixed_signs_only_query_negative_rows(self):
        points,calls=self.check_reference([.003,-.004,.005,-.006],
                                        [True,True,False,False])
        self.assertEqual(len(calls),1)
        np.testing.assert_array_equal(calls[0],points[[1,3]])

    def test_positive_rows_skip_contour_work(self):
        _,calls=self.check_reference([.003,0.,.005],[True,True,False])
        self.assertEqual(calls,[])

    def test_negative_zero_retains_reference_sign_bit(self):
        points,calls=self.check_reference([0.,-0.,-0.],[True,True,False])
        np.testing.assert_array_equal(calls[0],points[[1,2]])

    def test_empty_rows_do_not_query_proof(self):
        _,calls=self.check_reference([],[])
        self.assertEqual(calls,[])

    def test_default_path_still_passes_every_row_to_bounds(self):
        mesh=trimesh.creation.box();surface=fixtures.EvaluatedNativeSurface(
            mesh.vertices,mesh.vertex_normals,mesh.faces)
        points=np.array([[0.,0,0],[2.,0,0]])
        with patch.object(surface,'proven_outside',wraps=surface.proven_outside) as proof:
            surface.signed(points)
        np.testing.assert_array_equal(proof.call_args.args[0],points)


if __name__=='__main__':unittest.main()
