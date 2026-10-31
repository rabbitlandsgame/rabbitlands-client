import unittest
import numpy as np
from high_contact_bounds import ContactHead


class Head:
    def __init__(self):
        self.P=np.array([[-1,-1,-1],[1,1,1.]])
        self.T=np.array([[0,1,0]]);self.calls=[]
    def delta(self,name):return np.zeros_like(self.P)
    def signed(self,X,D=None,mesh=None,with_rim=False,T=None):
        self.calls.append((X.copy(),D,mesh,T))
        distance=np.full(len(X),.0004);cp=X.copy();cp[:,0]-=.0004
        normal=np.tile([1.,0,0],(len(X),1));rim=np.zeros(len(X),bool)
        return (distance,cp,normal,rim) if with_rim else (distance,cp,normal)


class ContactBoundsTest(unittest.TestCase):
    def test_only_complete_head_box_clear_points_are_skipped(self):
        head=Head();guard=ContactHead(head,3.2)
        X=np.array([[2.,0,0],[1.001,0,0],[0,0,0]])
        d,cp,N,rim=guard.signed(X,with_rim=True)
        self.assertEqual(d[0],1.)
        np.testing.assert_array_equal(head.calls[0][0],X[1:])
        np.testing.assert_array_equal(d[1:],np.full(2,.0004))
        self.assertEqual(guard.statistics['outside_box_proofs'],1)
        self.assertEqual(guard.statistics['exact_queries'],2)
    def test_current_morphed_bounds_and_exact_arguments_are_used(self):
        head=Head();guard=ContactHead(head);D=np.tile([2.,0,0],(2,1));mesh=object()
        T=np.array([[1,0,1]])
        d,_,_=guard.signed(np.array([[2.,0,0],[-2.,0,0]]),D=D,mesh=mesh,T=T)
        self.assertEqual(d[0],.0004);self.assertEqual(d[1],3.)
        self.assertIs(head.calls[0][1],D);self.assertIs(head.calls[0][2],mesh)
        self.assertIs(head.calls[0][3],T)
    def test_degenerate_bounds_query_every_point(self):
        head=Head();head.P[:,2]=0;guard=ContactHead(head)
        guard.signed(np.array([[0.,0,4.]]))
        self.assertEqual(guard.statistics['outside_box_proofs'],0)
        self.assertEqual(len(head.calls[0][0]),1)

    def test_optional_complete_slice_corrects_only_proven_outside_signs(self):
        import trimesh
        mesh=trimesh.creation.cone(radius=1,height=2,sections=16)
        points=np.asarray(mesh.vertices).copy();points[:,[1,2]]=points[:,[2,1]]
        head=Head();head.P=points;head.T=np.asarray(mesh.faces)
        shape=trimesh.Trimesh(points,head.T,process=False)
        def signed(X,D=None,mesh=None,with_rim=False,T=None):
            cp,distance,tri=trimesh.proximity.closest_point(shape,X)
            result=(-distance,cp,shape.face_normals[tri],np.zeros(len(X),bool))
            return result if with_rim else result[:3]
        head.signed=signed
        X=np.array([[.8,1.7,0],[.1,.3,0]])
        before=ContactHead(head).signed(X,with_rim=True)
        guard=ContactHead(head,horizontal_slice_proof=True);after=guard.signed(X,with_rim=True)
        self.assertLess(before[0][0],0);self.assertGreater(after[0][0],0)
        self.assertLess(after[0][1],0)
        np.testing.assert_array_equal(abs(before[0]),abs(after[0]))
        for a,b in zip(before[1:],after[1:]):np.testing.assert_array_equal(a,b)
        self.assertEqual(guard.statistics['horizontal_slice_sign_proofs'],1)
        self.assertEqual(guard.statistics['outside_box_proofs'],0)


if __name__=='__main__':unittest.main()
