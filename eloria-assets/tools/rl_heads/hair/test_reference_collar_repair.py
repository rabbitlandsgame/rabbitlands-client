import unittest
from types import SimpleNamespace
import numpy as np
from reference_collar_repair import repair

class Collar(unittest.TestCase):
    def setUp(self):
        self.head=SimpleNamespace(C=np.array([0,1.65,0]),eye_mid=np.array([0,1.64,0]))
        self.P=np.array([[.08,1.50,.10],[.09,1.50,.10],[.085,1.51,.10],[.085,1.504,.11]])
        self.N=np.tile([0.,0.,-1.],(4,1));self.UV=np.array([[.4,.4],[.41,.4],[.405,.41],[.405,.405]])
        self.T=np.array([[0,1,3],[1,2,3],[2,0,3]])
        self.config={'below_eye_mm':[80,200],'abs_x_mm':[50,180],'front_z_mm':0,'hole_span_mm':30,'hole_vertices':12,'uv_span':.05,'round_iterations':0,'round_limit_mm':2.5}

    def test_closes_only_compact_painted_orientable_hole(self):
        P,N,T,proof=repair(self.head,self.P,self.N,self.UV,self.T,{'collar_repair':self.config},np.full((100,100),255,np.uint8))
        edge,count=np.unique(np.sort(T[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1),axis=0,return_counts=True)
        self.assertTrue((count==2).all());self.assertEqual(proof['added_triangles'],1)
        np.testing.assert_array_equal(P,self.P)
        np.testing.assert_array_equal(T[:3],self.T)

    def test_tip_window_and_ambiguous_uv_chart_are_retained(self):
        low=self.P.copy();low[:,1]-=.3
        _,_,T,proof=repair(self.head,low,self.N,self.UV,self.T,{'collar_repair':self.config})
        np.testing.assert_array_equal(T,self.T);self.assertEqual(proof['added_triangles'],0)
        bad_uv=self.UV.copy();bad_uv[1]=[.9,.9]
        _,_,T,proof=repair(self.head,self.P,self.N,bad_uv,self.T,{'collar_repair':self.config})
        np.testing.assert_array_equal(T,self.T);self.assertEqual(proof['added_triangles'],0)

    def test_disabled_profile_is_exact(self):
        result=repair(self.head,self.P,self.N,self.UV,self.T,{})
        self.assertIs(result[0],self.P);self.assertIs(result[1],self.N);self.assertIs(result[2],self.T)

    def test_boundary_rounding_rule_is_symmetric_and_bounded(self):
        right=np.array([[.06,1.49,.10],[.12,1.49,.10],[.12,1.54,.10],[.07,1.535,.10]])
        left=right*np.array([-1,1,1]);P=np.vstack([right,left]);N=np.tile([0.,0.,1.],(8,1));UV=np.tile(self.UV,(2,1))
        T=np.array([[0,1,2],[0,2,3],[4,6,5],[4,7,6]])
        config=self.config|{'hole_vertices':3,'round_iterations':6}
        Q,_,_,proof=repair(self.head,P,N,UV,T,{'collar_repair':config})
        np.testing.assert_allclose(Q[:4]*np.array([-1,1,1]),Q[4:],atol=1e-12)
        self.assertGreater(proof['changed_vertices'],0);self.assertLessEqual(proof['round_max_mm'],2.500001)

if __name__=='__main__':unittest.main()
