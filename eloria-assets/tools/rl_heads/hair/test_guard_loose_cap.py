import unittest
import numpy as np
from guard_loose_cap import pin_nape_height,cap_body_clearance


class Head:
    C=np.array([0.,1.65,0.])
    eye_mid=np.array([0.,1.65,0.])
    P=np.array([[0.,1.6,0.]])
    vgroups={'ears':np.array([True])}


class NapeHeight(unittest.TestCase):
    def fixture(self):
        return np.array([[-.01,1.591,-.08],[.01,1.591,-.08],[-.01,1.626,-.06],[.01,1.626,-.06],[0,1.591,.08],[-.02,1.61,.08],[.02,1.61,.08]]),np.array([[0,1,2],[1,3,2],[4,5,6]])
    def test_low_rear_boundary_uses_declared_physical_height(self):
        P,T=self.fixture();Q,proof=pin_nape_height(Head(),P,T,{'nape_below_lobe_mm':20})
        np.testing.assert_allclose(Q[:2,1],1.58,atol=1e-12)
        np.testing.assert_array_equal(Q[:,[0,2]],P[:,[0,2]])
        np.testing.assert_array_equal(Q[2:],P[2:])
        self.assertEqual(proof['changed_vertices'],2)
        self.assertAlmostEqual(proof['maximum_shift_mm'],11)
    def test_declared_height_changes_nape_without_touching_face(self):
        P,T=self.fixture();Q,_=pin_nape_height(Head(),P,T,{'nape_below_lobe_mm':12})
        np.testing.assert_allclose(Q[:2,1],1.588,atol=1e-12)
        np.testing.assert_array_equal(Q[4:],P[4:])
    def test_correct_boundary_is_exact_noop(self):
        P,T=self.fixture();P[:2,1]=1.575;Q,proof=pin_nape_height(Head(),P,T,{'nape_below_lobe_mm':20})
        np.testing.assert_array_equal(Q,P);self.assertEqual(proof['changed_vertices'],0)
    def test_nape_disabled_profile_is_rejected(self):
        P,T=self.fixture()
        with self.assertRaises(AssertionError):pin_nape_height(Head(),P,T,{'nape':False})
    def test_cap_torso_clearance_preserves_height_and_clear_rows(self):
        P=np.array([[.01,1.55,.015],[.1,1.55,.03]])
        hull=np.array([[1,0,0,-.04],[-1,0,0,-.04],[0,1,0,-1.58],[0,-1,0,1.50],[0,0,1,-.03],[0,0,-1,-.03]])
        Q=cap_body_clearance(Head(),P,hull)
        self.assertGreaterEqual(float((Q[0]@hull[:,:3].T+hull[:,3]).max()),.0035-1e-12)
        np.testing.assert_array_equal(Q[:,1],P[:,1]);np.testing.assert_array_equal(Q[1],P[1])


if __name__=='__main__':unittest.main()
