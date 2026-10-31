import unittest
import numpy as np
import trimesh
from native_hair_clearance import NativeHeadSurface
from native_cap_fit import fit_cap

class CapFitTests(unittest.TestCase):
    def plane(self):
        P=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],float)
        return NativeHeadSurface(P,np.tile([0,0,1.],(4,1)),np.array([[0,1,2],[0,2,3]]))
    def arrays(self,P):
        return {'P':P,'N':np.tile([0,0,1.],(len(P),1)),
                'UV':P[:,:2].copy(),'J':np.zeros((len(P),4),dtype='u2'),
                'W':np.tile([1.,0,0,0],(len(P),1)),
                'id_test_p':P*.01,'hl_length_p':np.zeros_like(P)}
    def test_seats_cap_and_preserves_high_prefix(self):
        P=np.array([[-.02,-.02,.001],[.02,-.02,.001],[0,.02,.001]])
        arrays=self.arrays(P);before={key:value.copy() for key,value in arrays.items()}
        result,T,D,report=fit_cap(self.plane(),arrays,np.array([[0,1,2]]),[0,0,-.1],0)
        self.assertGreaterEqual(report['minimum_clearance_mm'],2)
        self.assertLess(report['maximum_shift_mm'],14)
        for key,value in before.items():np.testing.assert_array_equal(result[key],value)
        np.testing.assert_array_equal(arrays['P'],P)
        self.assertTrue(np.all(D[:,2]>0))
    def test_total_limit_fails_closed(self):
        P=np.array([[-.02,-.02,-.005],[.02,-.02,-.005],[0,.02,-.005]])
        with self.assertRaises(AssertionError):
            fit_cap(self.plane(),self.arrays(P),np.array([[0,1,2]]),[0,0,-.1],0,max_shift_mm=1)
    def test_small_triangle_still_checks_vertices(self):
        P=np.array([[0,0,.001],[.001,0,.001],[0,.001,.001]])
        _,_,_,report=fit_cap(self.plane(),self.arrays(P),np.array([[0,1,2]]),[0,0,-.1],0)
        self.assertIsNone(report['iterations'][0]['minimum_probe_clearance_mm'])
        self.assertGreaterEqual(report['minimum_clearance_mm'],2)
    def test_explicit_standoff_does_not_change_high_or_bound(self):
        P=np.array([[-.02,-.02,.001],[.02,-.02,.001],[0,.02,.001]])
        arrays=self.arrays(P);result,_,D,report=fit_cap(self.plane(),arrays,np.array([[0,1,2]]),[0,0,-.1],0,radial_stand_off_mm=3,vertex_margin_mm=2.8)
        np.testing.assert_array_equal(result['P'],P)
        self.assertGreaterEqual(report['minimum_clearance_mm'],2.8)
        self.assertEqual(report['limit_mm'],14)
        self.assertEqual(report['radial_stand_off_mm'],3)
    def test_curved_interior_requires_budget_and_keeps_high_surface(self):
        sphere=trimesh.creation.icosphere(subdivisions=2,radius=.1)
        native=NativeHeadSurface(sphere.vertices,sphere.vertex_normals,sphere.faces)
        P=np.array([[-.035,-.02,.095],[.035,-.02,.095],[0,.04,.095]])
        P=P/np.linalg.norm(P,axis=1)[:,None]*.103
        with self.assertRaises(AssertionError):fit_cap(native,self.arrays(P),np.array([[0,1,2]]),[0,0,0],0)
        result,T,D,report=fit_cap(native,self.arrays(P),np.array([[0,1,2]]),[0,0,0],300)
        self.assertGreater(len(T),1);self.assertGreaterEqual(report['minimum_clearance_mm'],2)
        np.testing.assert_array_equal(result['P'][:3],P)
        self.assertLess(report['maximum_shift_mm'],14)

if __name__=='__main__':unittest.main()
