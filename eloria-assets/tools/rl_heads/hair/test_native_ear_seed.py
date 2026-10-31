import unittest
import numpy as np
from native_ear_seed import coherent_ear_seed

BANDS={'x':[.045,.060],'y':[1.69,1.72],'z':[-.10,-.075,.010,.035]}

class EarSeedTest(unittest.TestCase):
    def test_side_component_mirrors_and_input_is_unchanged(self):
        P=np.array([[.07,1.67,-.03],[-.07,1.67,-.03]]);before=P.copy()
        D,report=coherent_ear_seed(P,BANDS,[2,8,-5])
        np.testing.assert_array_equal(P,before);np.testing.assert_allclose(D,[[.002,.008,-.005],[-.002,.008,-.005]],atol=1e-15)
        self.assertFalse(report['qualified']);self.assertLess(report['maximum_shift_mm'],14)
    def test_cap_pole_face_and_distant_rows_remain_exact_zero(self):
        P=np.array([[0,1.85,0],[.08,1.73,0],[.08,1.68,.04],[.08,1.68,-.11],[.04,1.68,0]])
        D,report=coherent_ear_seed(P,BANDS,[0,8,-5]);np.testing.assert_array_equal(D,np.zeros_like(P));self.assertEqual(report['changed_vertices'],0)
    def test_boundaries_are_continuous_and_taper_each_band(self):
        P=np.array([[.0525,1.705,-.0875],[.060,1.69,.0225]])
        D,_=coherent_ear_seed(P,BANDS,[0,8,-5])
        np.testing.assert_allclose(D[0],[0,.001,-.000625],atol=1e-15);np.testing.assert_allclose(D[1],[0,.004,-.0025],atol=1e-15)
    def test_malformed_or_over_bound_seed_fails_closed(self):
        P=np.zeros((1,3))
        with self.assertRaisesRegex(AssertionError,'bound'):coherent_ear_seed(P,BANDS,[0,15,0])
        with self.assertRaises(AssertionError):coherent_ear_seed(P,dict(BANDS,x=[.06,.04]),[0,8,-5])

if __name__=='__main__':unittest.main()
