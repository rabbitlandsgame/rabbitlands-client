import unittest
import numpy as np
from fit_reference_high_envelope import transported_normals


class RefitNormals(unittest.TestCase):
    def test_collapsed_support_keeps_finite_authored_shading(self):
        p=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        t=np.array([[0,1,2]]);n=np.tile([0.,0.,1.],(3,1));d=np.zeros_like(p);d[2,1]=-1.
        result=transported_normals(p,t,n,d,np.arange(3))
        self.assertTrue(np.isfinite(result).all())
        np.testing.assert_allclose(np.linalg.norm(result,axis=1),1.)
        np.testing.assert_array_equal(result,n)

    def test_real_surface_motion_still_transports_the_normal(self):
        p=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        t=np.array([[0,1,2]]);n=np.tile([0.,0.,1.],(3,1));d=np.zeros_like(p);d[2,2]=1.
        result=transported_normals(p,t,n,d,np.arange(3))
        np.testing.assert_allclose(result,np.tile([0.,-2**-.5,2**-.5],(3,1)),atol=1e-7)


if __name__=='__main__':unittest.main()
