"""Geometric root boundaries must not treat painted UV seams as open edges."""
import unittest
import numpy as np
from types import SimpleNamespace
from build_loose_reference import geometric_boundary,body_safe,shared_body_correction

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

if __name__=='__main__':unittest.main()
