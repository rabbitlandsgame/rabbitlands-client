import unittest
import numpy as np
import trimesh
from native_hair_clearance import NativeHeadSurface,NativeFaceGuardFailure

class NativeFaceSupport(unittest.TestCase):
    def fixture(self,angle):
        skin=trimesh.creation.icosphere(subdivisions=2,radius=.1)
        native=NativeHeadSurface(skin.vertices,skin.vertices,skin.faces)
        yaw=np.radians([0,120,240]);theta=np.radians(angle)
        P=np.column_stack([np.sin(theta)*np.cos(yaw),np.sin(theta)*np.sin(yaw),np.full(3,np.cos(theta))])*.104
        P=np.vstack([P,[0,0,.12]])
        return native,P,np.array([[0,1,2]]),{'shell':[0,3],'exterior':[3,4]}
    def test_clear_vertices_do_not_hide_an_interior_contact(self):
        native,P,T,ranges=self.fixture(20);signed,_,_=native.signed(P[:3]);self.assertTrue((signed>.0028).all())
        Q,receipt=native.push_faces(P,T,ranges)
        probes=np.vstack([Q[T].mean(1),Q[T[:,[0,1]]].mean(1),Q[T[:,[0,2]]].mean(1),Q[T[:,[1,2]]].mean(1)])
        distances,_,_=native.signed(probes);self.assertTrue((distances>=.0028-1e-8).all())
        np.testing.assert_array_equal(Q[3:],P[3:]);self.assertTrue(receipt['iterations'][0]['drivers'])
    def test_over_limit_proposal_is_retained_as_failed_evidence(self):
        native,P,T,ranges=self.fixture(40)
        with self.assertRaises(NativeFaceGuardFailure) as context:native.push_faces(P,T,ranges,max_shift_mm=5)
        self.assertFalse(context.exception.receipt['passed']);self.assertGreater(context.exception.receipt['maximum_shift_mm'],5)
    def test_already_clear_faces_remain_exact(self):
        native,P,T,ranges=self.fixture(5);Q,receipt=native.push_faces(P,T,ranges)
        np.testing.assert_array_equal(Q,P);self.assertEqual(receipt['changed_vertices'],0)

if __name__=='__main__':unittest.main()
