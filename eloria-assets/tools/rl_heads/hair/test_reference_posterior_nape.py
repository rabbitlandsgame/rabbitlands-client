import unittest
import numpy as np
from reference_posterior_nape import fit_posterior_nape


class SphereHead:
    C=np.array([0.,0.,-.017]);eye_mid=np.array([0.,.04,0.])
    center=np.array([0.,-.06,-.05]);radius=.07
    P=np.array([[-.08,-.06,-.05],[.08,-.06,-.05],[0,.02,-.05],[0,-.14,-.05],[0,-.06,.03],[0,-.06,-.13]])
    def raycast(self,origins,dirs,surface='noear',outermost=True):
        assert surface=='skin' and outermost
        relative=origins-self.center;b=(relative*dirs).sum(1);c=(relative*relative).sum(1)-self.radius**2
        disc=b*b-c;hit=disc>=0;t=-b+np.sqrt(np.maximum(disc,0));points=origins+dirs*t[:,None]
        return points,(points-self.center)/self.radius,hit


class PosteriorSourceTests(unittest.TestCase):
    def setUp(self):
        self.head=SphereHead();self.P=np.array([[-.01,-.07,-.049],[.01,-.07,-.051],[-.01,-.04,-.049],[.01,-.04,-.051],[.12,-.04,.1],[0,-.06,-.15]])
        self.N=np.tile([0.,0.,-1.],(len(self.P),1));self.T=np.array([[0,1,2],[1,3,2]])
        self.spec={'posterior_nape_fit':{'below_eye_mm':[150,40],'half_width_mm':70,'max_z_from_center_mm':30,'rear_margin_mm':5.5,'max_shift_mm':80,'feather_mm':5}}
    def test_absent_is_exact(self):
        Q,M,proof=fit_posterior_nape(self.head,self.P,self.N,self.T,{})
        self.assertIs(Q,self.P);self.assertIs(M,self.N);self.assertFalse(proof['enabled'])
    def test_coherent_rear_branch_keeps_original_chart_and_clear_rows(self):
        old=self.P.copy();Q,M,proof=fit_posterior_nape(self.head,self.P,self.N,self.T,self.spec)
        np.testing.assert_array_equal(self.P,old);np.testing.assert_array_equal(Q[:,:2],old[:,:2])
        np.testing.assert_array_equal(Q[4:],old[4:]);np.testing.assert_array_equal(M[4:],self.N[4:])
        self.assertTrue((Q[:4,2]<-.12).all());self.assertLess(abs(Q[0,2]-Q[1,2]),.001)
        self.assertEqual(proof['changed_rows'],4);np.testing.assert_allclose(np.linalg.norm(M,axis=1),1)
    def test_strict_bound_does_not_mutate_input(self):
        spec={'posterior_nape_fit':dict(self.spec['posterior_nape_fit'],max_shift_mm=20)};old=self.P.copy()
        with self.assertRaisesRegex(AssertionError,'displacement bound'):fit_posterior_nape(self.head,self.P,self.N,self.T,spec)
        np.testing.assert_array_equal(self.P,old)
    def test_no_hit_leaves_source_row_exact(self):
        P=self.P.copy();P[0,0]=.065;P[0,1]=-.10
        Q,M,proof=fit_posterior_nape(self.head,P,self.N,self.T,self.spec)
        np.testing.assert_array_equal(Q[0],P[0]);np.testing.assert_array_equal(M[0],self.N[0]);self.assertGreater(proof['missing_rear_rays'],0)
    def test_open_neck_front_only_hit_cannot_be_a_rear_wall(self):
        class OpenHead(SphereHead):
            def raycast(self,origins,dirs,surface='noear',outermost=True):
                points=origins.copy();points[:,2]=np.where(origins[:,1]<-.067,-.01,-.09)
                normal=np.tile([0.,0.,-1.],(len(origins),1));normal[origins[:,1]<-.067,2]=1
                return points,normal,np.ones(len(origins),bool)
        spec={'posterior_nape_fit':dict(self.spec['posterior_nape_fit'],rear_sample_up_mm=6)}
        Q,_,proof=fit_posterior_nape(OpenHead(),self.P,self.N,self.T,spec)
        self.assertTrue((Q[:4,2]<-.09).all());self.assertEqual(proof['rear_ray_bands'],4)


if __name__=='__main__':unittest.main()
