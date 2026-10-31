import unittest
import numpy as np
from native_hair_clearance import NativeHeadSurface

class NativeContacts(unittest.TestCase):
    def surface(self):return NativeHeadSurface(np.array([[-1.,-1,0],[1.,-1,0],[0,1.,0]]),np.tile([0.,0.,1.],(3,1)),np.array([[0,1,2]]))
    def test_moves_only_actual_contacts(self):
        P=np.array([[0.,0.,-.005],[0.,0.,.006]])
        Q,proof=self.surface().push_out(P)
        self.assertGreaterEqual(Q[0,2],.0028);np.testing.assert_array_equal(Q[1],P[1]);self.assertEqual(proof['contact_vertices'],1)
    def test_large_correction_fails_closed(self):
        with self.assertRaises(AssertionError):self.surface().push_out(np.array([[0.,0.,-.02]]),max_shift_mm=10)

class TiltedNormals(unittest.TestCase):
    def test_smooth_normal_tilt_does_not_prevent_true_clearance(self):
        P=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        N=np.tile([2**-.5,0.,2**-.5],(3,1));T=np.array([[0,1,2]])
        surface=NativeHeadSurface(P,N,T);points=np.array([[.2,.2,-.001],[.4,.4,.01]])
        Q,proof=surface.push_out(points)
        self.assertGreaterEqual(surface.signed(Q)[0].min(),.0028-1e-8)
        np.testing.assert_array_equal(Q[1],points[1]);np.testing.assert_allclose(Q[0,:2],points[0,:2],atol=1e-12,rtol=0)
        self.assertLess(proof['maximum_shift_mm'],14)

    def test_zero_distance_fallback_converges_with_tilted_normals(self):
        P=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        surface=NativeHeadSurface(P,np.tile([2**-.5,0.,2**-.5],(3,1)),np.array([[0,1,2]]))
        Q,proof=surface.push_out(np.array([[.2,.2,0.]]))
        self.assertGreaterEqual(surface.signed(Q)[0].min(),.0028-1e-8)
        self.assertLess(proof['maximum_shift_mm'],14)

if __name__=='__main__':unittest.main()
