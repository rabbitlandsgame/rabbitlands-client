import unittest
import bpy,bmesh
from split_reference_contacts import split_contacts

class ContactSplit(unittest.TestCase):
    def make(self,points,triangles):
        bm=bmesh.new();vertices=[bm.verts.new(point) for point in points]
        for triangle in triangles:bm.faces.new([vertices[i] for i in triangle])
        bm.faces.ensure_lookup_table();uv=bm.loops.layers.uv.new('UVMap');normal=bm.loops.layers.float_vector.new('authored_normal');identity=bm.faces.layers.int.new('source_face')
        for i,face in enumerate(bm.faces):
            face[identity]=i
            for j,loop in enumerate(face.loops):loop[uv].uv=(i*.1+j*.01,i*.05+j*.02);loop[normal]=(i*.01,0,1)
        return bm,uv,normal,identity

    def test_splits_only_measured_contact_and_preserves_corner_data(self):
        bm,uv,normal,identity=self.make([(0,0,0),(1,0,0),(0,1,0),(0,-1,0),(0,0,1),(3,0,0),(4,0,0),(4,1,0),(3,1,0)],[(0,1,2),(1,0,3),(0,1,4),(5,6,7),(5,7,8)])
        proof=split_contacts(bm,uv,normal,identity)
        self.assertEqual(proof['selected_edges'],1);self.assertTrue(proof['face_corner_positions_uv_normals_exact']);self.assertEqual(proof['faces_before'],proof['faces_after'])
        quad=[edge for edge in bm.edges if all(v.co.x>2 for v in edge.verts) and len(edge.link_faces)==2]
        self.assertEqual(len(quad),1);bm.free()

    def test_ordinary_two_face_uv_seam_is_untouched(self):
        bm,uv,normal,identity=self.make([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1,2),(0,2,3)])
        count=len(bm.verts);proof=split_contacts(bm,uv,normal,identity)
        self.assertEqual(proof['selected_edges'],0);self.assertEqual(len(bm.verts),count);self.assertEqual(sum(len(edge.link_faces)==2 for edge in bm.edges),1);bm.free()

if __name__=='__main__':unittest.main()
