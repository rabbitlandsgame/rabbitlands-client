"""Geometric root boundaries must not treat painted UV seams as open edges."""
import unittest
import numpy as np
from types import SimpleNamespace
from build_loose_reference import geometric_boundary,body_safe,shared_body_correction,curtain_body_safe,fair_body_clearance,coherent_lower_depth

class Boundaries(unittest.TestCase):
    def test_split_uv_centre_is_not_an_open_edge(self):
        P=np.array([[-1,0,-1],[1,0,-1],[1,0,1],[-1,0,1]]+[[0,0,0]]*4,dtype=float)
        T=np.array([[0,1,4],[1,2,5],[2,3,6],[3,0,7]])
        self.assertEqual(geometric_boundary(P,T).tolist(),[0,1,2,3])

    def test_closed_mass_has_no_boundary(self):
        P=np.array([[0,1,0],[-1,0,-1],[1,0,-1],[0,0,1]],dtype=float)
        T=np.array([[0,2,1],[0,3,2],[0,1,3],[1,2,3]])
        self.assertEqual(geometric_boundary(P,T).tolist(),[])

    def test_real_open_strip_retains_its_boundary(self):
        P=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],dtype=float)
        self.assertEqual(geometric_boundary(P,np.array([[0,1,2],[0,2,3]])).tolist(),[0,1,2,3])

class BodyClearance(unittest.TestCase):
    def setUp(self):
        self.head=SimpleNamespace(C=np.array([0.,1.5,0.]),eye_mid=np.array([0.,1.7,0.]))
        self.hull=np.array([[1,0,0,-1],[-1,0,0,-1],[0,1,0,-2],[0,-1,0,0],[0,0,1,-1],[0,0,-1,-1]],float)

    def test_hanging_length_is_unchanged(self):
        P=np.array([[.5,1.3,.1],[-.5,1.1,-.1],[0.,2.4,0.]])
        result=body_safe(self.head,P,self.hull)
        np.testing.assert_array_equal(result[:,0],P[:,0])
        np.testing.assert_array_equal(result[:,1],P[:,1])
        self.assertTrue((np.max(result@self.hull[:,:3].T+self.hull[:,3],axis=1)>=.0035-1e-12).all())
        np.testing.assert_array_equal(result[2],P[2])

    def test_shared_endpoint_correction_clears_both_states(self):
        P=np.array([[.5,1.3,.1],[-.5,1.1,-.1]])
        states=[P+np.array([.2,0,.1]),P-np.array([.2,0,.1])]
        correction=shared_body_correction(self.head,P,states,self.hull)
        np.testing.assert_array_equal(correction[:,1],0)
        for points in states:
            self.assertTrue((np.max((points+correction)@self.hull[:,:3].T+self.hull[:,3],axis=1)>=.0035-1e-12).all())

    def test_curtain_preserves_radial_curl_depth_and_pins_high_roots(self):
        hull=np.array([[1,0,0,-.2],[-1,0,0,-.2],[0,1,0,-1.55],[0,-1,0,1.0],[0,0,1,-.1],[0,0,-1,-.1]],float)
        P=np.array([[.08,1.2,.03],[.12,1.2,.07],[-.08,1.3,-.13],[-.12,1.3,-.17],[.04,1.69,.025]])
        result=curtain_body_safe(self.head,P,hull)
        np.testing.assert_array_equal(result[:,1],P[:,1])
        np.testing.assert_allclose(result[1]-result[0],P[1]-P[0],atol=1e-12)
        np.testing.assert_allclose(result[3]-result[2],P[3]-P[2],atol=1e-12)
        np.testing.assert_array_equal(result[4],P[4])
        self.assertTrue((np.max(result@hull[:,:3].T+hull[:,3],axis=1)>=.0035-1e-12).all())

    def test_continuous_body_field_does_not_tear_across_depth_divide(self):
        hull=np.array([[1,0,0,-.2],[-1,0,0,-.2],[0,1,0,-1.55],[0,-1,0,1.0],[0,0,1,-.1],[0,0,-1,-.1]],float)
        P=np.array([[.16,1.3,-.0501],[.16,1.3,-.0499]])
        result=body_safe(self.head,P,hull,radial=True)
        self.assertLess(np.linalg.norm(result[1]-result[0]),.0004)

    def test_connected_contact_fit_clears_body_and_keeps_roots_and_hanging_length(self):
        hull=np.array([[1,0,0,-.2],[-1,0,0,-.2],[0,1,0,-1.55],[0,-1,0,1.0],[0,0,1,-.1],[0,0,-1,-.1]],float)
        P=np.array([[x,y,.03] for y in np.linspace(1.2,1.7,11) for x in [.08,.10]])
        T=np.array([[i,i+1,i+2] for i in range(0,20,2)]+[[i+1,i+3,i+2] for i in range(0,20,2)])
        Q=fair_body_clearance(self.head,P,T,hull)
        np.testing.assert_array_equal(Q[-2:],P[-2:])
        np.testing.assert_array_equal(Q[P[:,1]<1.46,1],P[P[:,1]<1.46,1])
        points=Q[Q[:,1]<self.head.eye_mid[1]-.055]
        self.assertTrue((np.max(points@hull[:,:3].T+hull[:,3],axis=1)>=.00325-1e-9).all())

    def test_lower_lock_depth_stays_coherent_through_connected_shoulder(self):
        hull=np.array([[1,0,0,-.2],[-1,0,0,-.2],[0,1,0,-1.55],[0,-1,0,1.0],[0,0,1,-.1],[0,0,-1,-.1]],float)
        P=np.array([[.08,1.7,.03],[.10,1.7,.03],[.08,1.2,.03],[.10,1.2,.06],
                    [.08,1.7,-.08],[.10,1.7,-.08],[.08,1.2,-.08],[.10,1.2,-.09]])
        T=np.array([[0,1,2],[1,3,2],[4,6,5],[5,6,7],[0,4,1],[1,4,5]])
        Q,fixed=coherent_lower_depth(self.head,P,T,hull,.0035)
        np.testing.assert_array_equal(Q[:,:2],P[:,:2])
        np.testing.assert_array_equal(Q[[0,1,4,5]],P[[0,1,4,5]])
        np.testing.assert_allclose(Q[3]-Q[2],P[3]-P[2],atol=1e-12)
        np.testing.assert_allclose(Q[7]-Q[6],P[7]-P[6],atol=1e-12)
        self.assertTrue((np.max(Q[fixed]@hull[:,:3].T+hull[:,3],axis=1)>=.0035-1e-12).all())

if __name__=='__main__':unittest.main()
