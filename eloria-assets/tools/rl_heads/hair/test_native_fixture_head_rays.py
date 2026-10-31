import unittest
import numpy as np
from native_fixture_head_rays import fixture_head_part

class HeadRayTests(unittest.TestCase):
    def data(self):
        return {'P':np.array([[0,0,1],[1,0,1],[0,1,1],[0,0,5.]],'f4'),
                'N':np.tile([0,0,1.],(4,1)),
                'I':np.array([[0,2,1],[1,2,3]])}
    def test_semantic_rows_exclude_lower_body_despite_winding(self):
        data=self.data();expected=np.array([[0,1,2],[1,3,2]])
        P,N,T=fixture_head_part(data,expected,[0],4)
        np.testing.assert_array_equal(P[T],data['P'][expected[[0]]])
        self.assertTrue((P[:,2]==1).all());self.assertEqual(len(T),1)
    def test_unknown_row_reordering_fails_closed(self):
        data=self.data();data['I']=data['I'][::-1]
        with self.assertRaises(AssertionError):fixture_head_part(data,np.array([[0,1,2],[1,3,2]]),[0],4)
    def test_wrong_vertex_scope_fails_closed(self):
        with self.assertRaises(AssertionError):fixture_head_part(self.data(),np.array([[0,1,2],[1,3,2]]),[0],5)
    def test_complete_selection_retains_all_original_points(self):
        data=self.data();P,N,T=fixture_head_part(data,np.array([[0,1,2],[1,3,2]]),[0,1],4)
        np.testing.assert_array_equal(P,data['P']);np.testing.assert_array_equal(N,data['N'])

if __name__=='__main__':unittest.main()
