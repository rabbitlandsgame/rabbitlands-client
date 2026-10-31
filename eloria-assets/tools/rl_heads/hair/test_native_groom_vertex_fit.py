import unittest
import numpy as np
from native_groom_vertex_fit import fit_vertices,NativeVertexFitFailure


class Sphere:
    def signed(self,P):
        length=np.linalg.norm(P,axis=1);N=P/length[:,None]
        return length-1,N,N


class NativeVertexTest(unittest.TestCase):
    def test_joint_groom_corner_and_seams_without_high_edits(self):
        P=np.array([[0,0,1.007],[0,0,1.007],[.03,0,1.03]],dtype='f4');old=P.copy()
        negative=np.tile([0,0,-.003],(len(P),1));zero=np.zeros_like(P)
        targets={'hl_length_n':negative,'hl_volume_n':negative,'hl_length_p':zero,'hl_volume_p':zero}
        saved={name:value.copy() for name,value in targets.items()}
        D,receipt=fit_vertices(Sphere(),P,targets)
        self.assertGreater(D[0,2],0);np.testing.assert_array_equal(D[0],D[1]);np.testing.assert_array_equal(D[2],0)
        np.testing.assert_array_equal(P,old)
        for name,value in targets.items():np.testing.assert_array_equal(value,saved[name])
        self.assertGreaterEqual((np.linalg.norm(P+D+negative*2,axis=1)-1).min(),.003-1e-7)
        self.assertFalse(receipt['triangle_interiors_checked']);self.assertFalse(receipt['qualified'])
    def test_initial_valid_field_is_retained_and_cases_are_explicit(self):
        P=np.array([[0,0,1.001]],dtype='f4');D=np.array([[0,0,.005]],dtype='f4')
        actual,receipt=fit_vertices(Sphere(),P,{},groom_cases={'neutral':{}},initial_delta=D)
        np.testing.assert_allclose(actual,D,atol=1e-12);self.assertEqual(receipt['changed_vertices'],1)
        with self.assertRaisesRegex(AssertionError,'missing'):fit_vertices(Sphere(),P,{})
    def test_bound_never_accepts_an_unresolved_contact(self):
        P=np.array([[0,0,.995]],dtype='f4')
        with self.assertRaises(NativeVertexFitFailure) as result:fit_vertices(Sphere(),P,{},groom_cases={'neutral':{}},max_shift_mm=1,max_iterations=4)
        self.assertLessEqual(result.exception.receipt['maximum_shift_mm'],1)
        self.assertGreater(result.exception.receipt['iterations'][-1]['contacts'],0)


if __name__=='__main__':unittest.main()
