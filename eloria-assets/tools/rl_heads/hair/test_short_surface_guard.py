"""The short guard must catch face dips and keep attribute seams closed."""
import unittest
import numpy as np
import trimesh
from short_surface_guard import guard


class Sphere:
    def __init__(self):
        mesh=trimesh.creation.icosphere(subdivisions=1)
        self.P=mesh.vertices;self.T=mesh.faces;self.C=np.zeros(3)
    def delta(self,name):return np.zeros_like(self.P)
    def signed(self,P,D=None,mesh=None,with_rim=False):
        radius=np.linalg.norm(P,axis=1);normal=P/radius[:,None]
        result=(radius-1,normal,normal)
        return result+(np.zeros(len(P),bool),) if with_rim else result


def triangle(radius=1.003):
    angle=np.array([[-.06,0],[.06,0],[0,.06]])
    P=np.c_[angle,np.ones(3)];P=P/np.linalg.norm(P,axis=1)[:,None]*radius
    return P,np.array([[0,1,2]])


class GuardTest(unittest.TestCase):
    def test_optional_geometric_projection_preserves_tangential_position(self):
        class TiltedPlane(Sphere):
            def signed(self,P,D=None,mesh=None,with_rim=False):
                cp=P.copy();cp[:,2]=0
                result=(P[:,2].copy(),cp,np.tile([.8,0,.6],(len(P),1)))
                return result+(np.zeros(len(P),bool),) if with_rim else result
        P=np.array([[0.,0.,-.002]]);T=np.array([[0,0,0]])
        old,_=guard(TiltedPlane(),P,T,{},[],{})
        explicit_old,_=guard(TiltedPlane(),P,T,{},[],{},geometric_projection=False)
        np.testing.assert_array_equal(old,explicit_old)
        Q,_=guard(TiltedPlane(),P,T,{},[],{},geometric_projection=True)
        np.testing.assert_array_equal(Q[:,:2],P[:,:2])
        self.assertGreaterEqual(Q[0,2],.003)
        self.assertGreater(abs(old[0,0]),.001)
        zero,_=guard(TiltedPlane(),np.zeros((1,3)),T,{},[],{},geometric_projection=True)
        self.assertTrue(np.isfinite(zero).all())
        self.assertGreaterEqual(zero[0,2],.003)

    def test_explicit_limiting_faces_with_remote_corners_are_checked(self):
        P=np.array([[-.24,0,1],[.24,0,1],[0,.24,1.]])
        P=P/np.linalg.norm(P,axis=1)[:,None]*1.025;T=np.array([[0,1,2]])
        untouched,_=guard(Sphere(),P,T,{},[],{})
        np.testing.assert_array_equal(untouched,P)
        self.assertLess(np.linalg.norm(P[T].mean(1),axis=1)[0]-1,.003)
        Q,report=guard(Sphere(),P,T,{},[],{},all_faces=True)
        self.assertGreaterEqual(np.linalg.norm(Q[T].mean(1),axis=1)[0]-1,.003-1e-8)
        self.assertGreater(report['changed_vertices'],0)
        self.assertLessEqual(report['maximum_shift_mm'],14)

    def test_clear_corners_do_not_hide_a_colliding_face(self):
        P,T=triangle();Q,report=guard(Sphere(),P,T,{},[],{},margin=.003)
        self.assertGreaterEqual((np.linalg.norm(P,axis=1)-1).min(),.002999)
        probes=np.vstack([Q,Q[T].mean(1),(Q[T[:,0]]+Q[T[:,1]])/2])
        self.assertGreaterEqual((np.linalg.norm(probes,axis=1)-1).min(),.003-1e-8)
        self.assertGreater(report['changed_vertices'],0)
    def test_uv_split_vertices_receive_identical_displacements(self):
        P,T=triangle();P=np.vstack([P,P]);T=np.vstack([T,T+3])
        Q,_=guard(Sphere(),P,T,{},[],{},margin=.003)
        np.testing.assert_array_equal(Q[:3],Q[3:])
    def test_individual_target_is_checked_without_a_mixed_case(self):
        P,T=triangle(1.007);D=-P/np.linalg.norm(P,axis=1)[:,None]*.005
        Q,report=guard(Sphere(),P,T,{'id_near_p':D},['id_near_p'],{},margin=.003)
        self.assertEqual(report['states'],2)
        self.assertGreaterEqual((np.linalg.norm(Q+D,axis=1)-1).min(),.003-1e-8)
    def test_clear_geometry_stays_exact_and_bound_fails_closed(self):
        P,T=triangle(1.02);Q,_=guard(Sphere(),P,T,{},[],{})
        np.testing.assert_array_equal(P,Q)
        P,T=triangle()
        with self.assertRaisesRegex(AssertionError,'displacement limit'):guard(Sphere(),P,T,{},[],{},max_shift_mm=.01)


if __name__=='__main__':unittest.main()
