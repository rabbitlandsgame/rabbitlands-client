"""Geometric root boundaries must not treat painted UV seams as open edges."""
import unittest
import numpy as np
from build_loose_reference import geometric_boundary

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

if __name__=='__main__':unittest.main()
