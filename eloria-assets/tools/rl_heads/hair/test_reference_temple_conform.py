"""Boundary-only temple conformance preserves the rest and source asymmetry."""
import copy,unittest
import numpy as np
import headref
from reference_temple_conform import conform_temples

class Head:
    C=np.zeros(3)
class Scalp:
    def hairline(self,lon):return np.zeros_like(lon)
    def point(self,lon,lat):
        normal=headref.lonlat_dir(lon,lat);return normal*.1,normal

class TempleConformance(unittest.TestCase):
    def fixture(self):
        lon=np.array([-70.,-75,-80,70,75,80,0,180]);lat=np.array([-14.,-3,3,-14,-3,3,30,-30])
        N=headref.lonlat_dir(lon,lat);P=N*.103;P[3:6]*=1.01
        return P,N,np.array([[0,1,2],[3,5,4]]),{'exterior':[0,6]}, {'temple_conform':{'longitude_ramps':[55,70,105,120],'margin_degrees':.5,'softness_degrees':1.5,'max_displacement_mm':30}}
    def test_default_returns_original_arrays(self):
        P,N,T,ranges,_=self.fixture();Q,M,proof=conform_temples(Head(),Scalp(),P,N,T,ranges,{})
        self.assertIs(Q,P);self.assertIs(M,N);self.assertFalse(proof['enabled'])
    def test_local_transport_preserves_unrelated_geometry_and_asymmetry(self):
        P,N,T,ranges,spec=self.fixture();Q,M,proof=conform_temples(Head(),Scalp(),P,N,T,ranges,spec)
        np.testing.assert_array_equal(Q[6:],P[6:]);np.testing.assert_array_equal(M[6:],N[6:])
        np.testing.assert_allclose(np.linalg.norm(M,axis=1),1,atol=1e-12)
        self.assertGreater(Q[0,1],P[0,1]);self.assertGreater(Q[3,1],P[3,1])
        self.assertFalse(np.isclose(np.linalg.norm(Q[0]),np.linalg.norm(Q[3])))
        self.assertTrue(proof['outside_positions_normals_exact'])
    def test_displacement_limit_fails_closed(self):
        P,N,T,ranges,spec=self.fixture();spec=copy.deepcopy(spec);spec['temple_conform']['max_displacement_mm']=1
        with self.assertRaises(AssertionError):conform_temples(Head(),Scalp(),P,N,T,ranges,spec)
    def test_explicit_preserved_cap_is_not_conformed(self):
        P,N,T,ranges,spec=self.fixture();P=np.vstack([P,P[:3]]);N=np.vstack([N,N[:3]])
        T=np.vstack([T,[[8,9,10]]]);ranges['shell']=[8,11];spec['temple_conform']['preserve_parts']=['shell']
        Q,M,_=conform_temples(Head(),Scalp(),P,N,T,ranges,spec)
        np.testing.assert_array_equal(Q[8:],P[8:]);np.testing.assert_array_equal(M[8:],N[8:])
        self.assertGreater(Q[0,1],P[0,1])

if __name__=='__main__':unittest.main()
