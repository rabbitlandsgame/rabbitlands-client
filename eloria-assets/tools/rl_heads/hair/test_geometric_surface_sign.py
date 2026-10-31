import unittest
import numpy as np
import trimesh
from geometric_surface_sign import GeometricSurfaceSign


class GeometricSignTests(unittest.TestCase):
    def test_face_edge_and_vertex_use_physical_outward_normals(self):
        mesh=trimesh.creation.box();normal=GeometricSurfaceSign(mesh.vertices,mesh.faces)
        points=np.array([[.6,.1,.2],[.6,.6,.1],[.6,.6,.6],[.4,.1,.2],[.4,.4,.1],[.4,.4,.4]])
        closest,distance,faces=trimesh.proximity.closest_point(mesh,points)
        tri=mesh.vertices[mesh.faces[faces]]
        bc=trimesh.triangles.points_to_barycentric(tri,closest)
        signs=((points-closest)*normal.normals(faces,bc)).sum(1)
        np.testing.assert_array_equal(signs>0,[True,True,True,False,False,False])
        self.assertTrue((distance>0).all())
    def test_uv_splits_share_angle_weighted_vertex_and_edge_normals(self):
        mesh=trimesh.creation.box();T=mesh.faces;P=mesh.vertices
        base=GeometricSurfaceSign(P,T);splitP=P[T].reshape(-1,3);splitT=np.arange(len(splitP)).reshape(-1,3)
        split=GeometricSurfaceSign(splitP,splitT)
        for bc in [np.tile([1.,0,0],(len(T),1)),np.tile([.5,.5,0],(len(T),1)),np.full((len(T),3),1/3)]:
            np.testing.assert_allclose(base.normals(np.arange(len(T)),bc),split.normals(np.arange(len(T)),bc),atol=1e-12)
    def test_angle_weight_is_independent_of_triangle_area_at_a_vertex(self):
        P=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[10,0,0],[0,10,0.]])
        a=GeometricSurfaceSign(P,np.array([[0,1,2],[0,3,1]]))
        b=GeometricSurfaceSign(P,np.array([[0,4,5],[0,3,1]]))
        np.testing.assert_allclose(a.vertex[0],b.vertex[0],atol=1e-12)
    def test_explicit_weld_and_repeated_queries_are_deterministic(self):
        mesh=trimesh.creation.icosphere(subdivisions=1);P=mesh.vertices;T=mesh.faces
        _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
        a=GeometricSurfaceSign(P,T,weld);b=GeometricSurfaceSign(P,T)
        indices=np.arange(len(T));bc=np.full((len(T),3),1/3)
        np.testing.assert_array_equal(a.normals(indices,bc),b.normals(indices,bc))
        np.testing.assert_array_equal(a.normals(indices,bc),a.normals(indices,bc))


if __name__=='__main__':unittest.main()
