import unittest
import numpy as np
import trimesh
from build_loose_reference import BoundedHead
from high_contact_bounds import ContactHead
import headref


def fixture():
    mesh=trimesh.creation.box();head=BoundedHead.__new__(BoundedHead)
    head.P=np.asarray(mesh.vertices);head.T=np.asarray(mesh.faces);head.mesh=mesh
    _,head.weld=np.unique(np.round(head.P/1e-6),axis=0,return_inverse=True)
    head.N=headref.vertex_normals(head.P,head.T,head.weld)
    head.rim=np.zeros(len(head.P),bool)
    return head


class HighGeometricSign(unittest.TestCase):
    def test_geometric_sign_preserves_distances_closest_points_and_rims(self):
        head=fixture();P=np.array([[.6,.1,.2],[.6,.6,.1],[.6,.6,.6],[.4,.1,.2]])
        before=head.signed(P,with_rim=True);after=head.signed(P,with_rim=True,geometric_sign=True)
        np.testing.assert_array_equal(abs(before[0]),abs(after[0]))
        np.testing.assert_array_equal(before[1],after[1]);np.testing.assert_array_equal(before[3],after[3])
        np.testing.assert_array_equal(after[0]>0,[True,True,True,False])
    def test_default_result_is_unchanged_after_opt_in(self):
        head=fixture();P=np.array([[.6,.1,.2],[.4,.1,.2]])
        before=head.signed(P,with_rim=True);head.signed(P,geometric_sign=True);after=head.signed(P,with_rim=True)
        for a,b in zip(before,after):np.testing.assert_array_equal(a,b)
    def test_mutated_mesh_geometry_invalidates_geometric_sign_cache(self):
        head=fixture();head.signed(np.array([[.6,0,0]]),geometric_sign=True);first=head.mesh._rl_geometric_sign
        head.P=head.P.copy();head.P[:,0]*=2;head.mesh.vertices=head.P
        head.signed(np.array([[1.1,0,0]]),geometric_sign=True)
        self.assertIsNot(first,head.mesh._rl_geometric_sign)
    def test_guard_adapter_explicitly_uses_physical_signs(self):
        head=fixture();head.delta=lambda name:np.zeros_like(head.P)
        P=np.array([[.4,.1,.2]])
        d,cp,N=ContactHead(head,geometric_sign=True).signed(P)
        expected=head.signed(P,geometric_sign=True)
        for a,b in zip((d,cp,N),expected):np.testing.assert_array_equal(a,b)


if __name__=='__main__':unittest.main()
