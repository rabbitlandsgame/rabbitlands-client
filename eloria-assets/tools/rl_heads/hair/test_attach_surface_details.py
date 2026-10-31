import unittest
import numpy as np
from attach_surface_details import root_columns


class SurfaceAttachmentTest(unittest.TestCase):
    def scene(self):
        P=np.array([[0.,0,0],[1,0,0],[0,1,0]]);T=np.array([[0,1,2]])
        D={'id_test_p':np.array([[0,0,.1],[0,.1,.2],[.1,0,.3]]),
           'hl_length_p':np.array([[0,.2,0],[.1,0,0],[0,0,.1]]),
           'hl_native_fit':np.tile([.01,0,0],(3,1))}
        F=np.array([[.1,.1,.02],[.3,.1,.02],[.1,.2,.12],[.3,.2,.12]])
        delta={n:np.arange(12).reshape(4,3)*.001 for n in D}
        return P,T,D,F,delta,np.array([0,1]),np.array([0,1,0,1])
    def test_root_vertices_follow_arbitrary_linear_control_blends_exactly(self):
        P,T,D,F,delta,roots,columns=self.scene();old=F.copy()
        old_parent={n:d.copy() for n,d in D.items()};old_detail={n:d.copy() for n,d in delta.items()}
        Q,motion,proof=root_columns(P,T,D,F,delta,roots,columns)
        tv=np.asarray(proof['parent_triangles']);bc=np.asarray(proof['barycentric'])
        for weights in [[0,0,0],[1,1,1],[.23,.91,1],[-.4,.3,.6]]:
            parent=P+sum((D[n]*v for n,v in zip(D,weights)),np.zeros_like(P))
            detail=Q+sum((motion[n]*v for n,v in zip(D,weights)),np.zeros_like(Q))
            np.testing.assert_allclose(detail[roots],(parent[tv]*bc[:,:,None]).sum(1),atol=1e-14)
        np.testing.assert_array_equal(F,old)
        for name in D:
            np.testing.assert_array_equal(D[name],old_parent[name])
            np.testing.assert_array_equal(delta[name],old_detail[name])
    def test_relative_strand_motion_is_preserved_and_native_columns_are_rigid(self):
        P,T,D,F,delta,roots,columns=self.scene()
        Q,motion,_=root_columns(P,T,D,F,delta,roots,columns)
        for at,root in enumerate(roots):
            group=columns==at
            np.testing.assert_allclose(Q[group]-Q[root],F[group]-F[root])
            for n in ['id_test_p','hl_length_p']:
                np.testing.assert_allclose(motion[n][group]-motion[n][root],delta[n][group]-delta[n][root])
            np.testing.assert_allclose(motion['hl_native_fit'][group],np.repeat(motion['hl_native_fit'][root][None],group.sum(),axis=0))


if __name__=='__main__':unittest.main()
