import unittest
import numpy as np
from hairgen import shell_boundary_rows,shell_physical_rings


class ShellBoundaryRows(unittest.TestCase):
    def test_old_profiles_retain_the_exact_array(self):
        for rows in [6,9,12]:
            s=np.linspace(0,1,rows+1)
            self.assertIs(shell_boundary_rows(s),s)

    def test_explicit_rows_are_unique_and_keep_all_existing_samples(self):
        s=np.linspace(0,1,7);result=shell_boundary_rows(s,[.97,.99,.97])
        self.assertTrue(np.isin(s,result).all());self.assertTrue((np.diff(result)>0).all())
        np.testing.assert_array_equal(result[-3:],[.97,.99,1.])

    def test_physical_rings_are_exact_and_keep_the_original_boundary(self):
        P=np.array([[0,.1,0],[-.01,.05,0],[.01,.05,0],[-.02,0,0],[.02,0,0]],float)
        N=np.tile([0,0,1.],(5,1));UV=P[:,:2].copy();T=np.array([[0,2,1],[1,2,3],[2,4,3]])
        t=np.array([0,.5,.5,1,1.]);data=(P,N,UV,T,t,t.copy())
        out=shell_physical_rings(data,2,1,1,[1.,2.]);Q=out[0]
        np.testing.assert_array_equal(Q[-2:],P[-2:])
        np.testing.assert_allclose(np.linalg.norm(Q[-2:]-Q[-4:-2],axis=1),.001)
        np.testing.assert_allclose(np.linalg.norm(Q[-2:]-Q[-6:-4],axis=1),.002)
        self.assertTrue(np.isfinite(out[1]).all())
        for invalid in [[0.],[-1.],[1000.],[np.nan]]:
            with self.assertRaises(AssertionError):shell_physical_rings(data,2,1,1,invalid)

    def test_invalid_rows_fail_closed(self):
        for request in [[0],[1],[-.1],[np.nan],[np.inf]]:
            with self.assertRaises(AssertionError):shell_boundary_rows(np.array([0.,1.]),request)


if __name__=='__main__':unittest.main()
