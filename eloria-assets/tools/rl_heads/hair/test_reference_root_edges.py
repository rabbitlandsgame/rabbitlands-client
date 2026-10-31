"""A painted UV seam must not become a false open root boundary."""
import unittest
import numpy as np
from types import SimpleNamespace
import headref
from reference_root_edges import geometric_boundary,root_colours

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

class RootProfile(unittest.TestCase):
    def colours(self,lat,spec):
        P=headref.lonlat_dir(np.array([100,101,102]),np.asarray(lat))
        return root_colours(SimpleNamespace(C=np.zeros(3)),SimpleNamespace(hairline=lambda lon:np.zeros_like(lon)),P,np.array([[0,1,2]]),np.ones((3,4)),{'exterior':[0,3],'detail':[3,3]},np.zeros(3),{'soft_hairline_mm':2}|spec)

    def test_temple_sector_requires_explicit_opt_in(self):
        np.testing.assert_array_equal(self.colours([1,2,3],{})[:,0],1)
        np.testing.assert_array_equal(self.colours([1,2,3],{'root_sector_degrees':115})[:,0],0)

    def test_wider_band_requires_explicit_opt_in(self):
        np.testing.assert_array_equal(self.colours([9,10,11],{'root_sector_degrees':115})[:,0],1)
        np.testing.assert_array_equal(self.colours([9,10,11],{'root_sector_degrees':115,'root_band_degrees':12})[:,0],0)

if __name__=='__main__':unittest.main()
