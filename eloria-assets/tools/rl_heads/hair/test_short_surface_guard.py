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
