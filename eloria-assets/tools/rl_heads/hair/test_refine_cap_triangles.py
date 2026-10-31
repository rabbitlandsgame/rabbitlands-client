import unittest
import numpy as np
from refine_cap_triangles import refine_cap

class CapRefinement(unittest.TestCase):
    def arrays(self,P):return {'P':P,'N':np.tile([0.,0.,1.],(len(P),1)),'UV':P[:,:2].copy(),'id_test':P*.2,'J':np.zeros((len(P),4),np.uint8),'W':np.tile([1.,0,0,0],(len(P),1))}
    def test_selected_and_neighboring_edges_stay_conforming(self):
        P=np.array([[0.,0,0],[1.,0,0],[1.,1,0],[0.,1,0]]);T=np.array([[0,1,2],[0,2,3]]);arrays=self.arrays(P)
        out,tri,proof=refine_cap(arrays,T,[0],20)
        self.assertEqual(len(tri),6);self.assertEqual(proof['extra_triangles'],4)
        np.testing.assert_array_equal(out['P'][:4],P);np.testing.assert_allclose(out['id_test'],out['P']*.2)
        edges=np.sort(tri[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1);_,count=np.unique(edges,axis=0,return_counts=True)
        self.assertTrue((count<=2).all())
    def test_uv_seam_twins_receive_matching_geometric_splits(self):
        P=np.array([[0.,0,0],[1.,0,0],[1.,1,0],[0.,0,0],[1.,1,0],[0.,1,0]])
        arrays=self.arrays(P);arrays['UV'][3:]+=[2,0];out,tri,proof=refine_cap(arrays,np.array([[0,1,2],[3,4,5]]),[0],20)
        self.assertEqual(len(tri),6);self.assertGreater(proof['indexed_edge_splits'],proof['geometric_edge_splits'])
        shared=out['P'][6:];self.assertEqual(int(np.all(np.isclose(shared,[.5,.5,0]),axis=1).sum()),2)
    def test_budget_and_nonuniform_skin_fail_closed(self):
        P=np.array([[0.,0,0],[1.,0,0],[0.,1,0]]);arrays=self.arrays(P);T=np.array([[0,1,2]])
        with self.assertRaises(AssertionError):refine_cap(arrays,T,[0],2)
        arrays['W'][1]=[.5,.5,0,0]
        with self.assertRaises(AssertionError):refine_cap(arrays,T,[0],20)

if __name__=='__main__':unittest.main()
