import unittest
import numpy as np
from native_hair_clearance import NativeHeadSurface

class NativeContacts(unittest.TestCase):
    def surface(self):return NativeHeadSurface(np.array([[-1.,-1,0],[1.,-1,0],[0,1.,0]]),np.tile([0.,0.,1.],(3,1)),np.array([[0,1,2]]))
    def test_moves_only_actual_contacts(self):
        P=np.array([[0.,0.,-.005],[0.,0.,.006]])
        Q,proof=self.surface().push_out(P)
        self.assertGreaterEqual(Q[0,2],.0028);np.testing.assert_array_equal(Q[1],P[1]);self.assertEqual(proof['contact_vertices'],1)
    def test_large_correction_fails_closed(self):
        with self.assertRaises(AssertionError):self.surface().push_out(np.array([[0.,0.,-.02]]),max_shift_mm=10)

if __name__=='__main__':unittest.main()
