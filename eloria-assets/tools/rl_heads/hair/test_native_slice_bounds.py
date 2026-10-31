import unittest
from pathlib import Path
import tempfile
import numpy as np
import trimesh
from native_hair_fixtures import EvaluatedNativeSurface,load_fixture,sha
from native_slice_bounds import HorizontalSliceBounds


class HorizontalSliceTests(unittest.TestCase):
    def stacked(self):
        body=trimesh.creation.box(extents=[2,1,1])
        head=trimesh.creation.box(extents=[.2,1,.2]);head.apply_translation([0,1,0])
        return trimesh.util.concatenate([body,head])

    def tetra(self):
        mesh=trimesh.Trimesh([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
            [[0,2,1],[0,1,3],[0,3,2],[1,2,3]],process=False)
        mesh.fix_normals();return mesh

    def test_closed_cube_inside_and_outside(self):
        mesh=trimesh.creation.box(extents=[.2,.2,.2]);bounds=HorizontalSliceBounds(mesh)
        np.testing.assert_array_equal(bounds.outside(np.array([[.2,.02,0],[0,.02,0],[.099,.02,.099]])),[True,False,False])

    def test_tetra_cross_section_is_tighter_than_whole_mesh(self):
        mesh=self.tetra();bounds=HorizontalSliceBounds(mesh)
        points=np.array([[.6,.8,.1],[.05,.8,.05]])
        self.assertTrue(((points>=mesh.bounds[0])&(points<=mesh.bounds[1])).all())
        np.testing.assert_array_equal(bounds.outside(points),[True,False])

    def test_skew_cross_section_tracks_interpolated_edges(self):
        mesh=self.tetra();P=mesh.vertices.copy();P[:,0]+=P[:,1]*.5;P[:,2]+=P[:,1]*.2
        mesh.vertices=P;bounds=HorizontalSliceBounds(mesh)
        np.testing.assert_array_equal(bounds.outside(np.array([[.7,.8,.2],[.45,.8,.2]])),[True,False])

    def test_varying_crosssection_does_not_use_whole_mesh_bounds(self):
        bounds=HorizontalSliceBounds(self.stacked())
        np.testing.assert_array_equal(bounds.outside(np.array([[.5,1.1,0],[.5,.1,0],[.09,1.1,0]])),[True,False,False])

    def test_empty_coplanar_and_near_coplanar_planes_fall_back(self):
        bounds=HorizontalSliceBounds(self.stacked())
        points=np.array([[2,10,0],[2,.5,0],[2,.5+1e-10,0]])
        np.testing.assert_array_equal(bounds.outside(points),[False,False,False])
        self.assertEqual(bounds.last_query['valid_planes'],0)

    def test_planar_mesh_provides_no_volumetric_proof(self):
        mesh=trimesh.Trimesh([[-1,0,0],[1,0,0],[0,0,1]],[[0,1,2]],process=False)
        np.testing.assert_array_equal(HorizontalSliceBounds(mesh).outside(np.array([[3,0,0],[0,-.1,0]])),[False,False])

    def test_optional_rule_changes_only_proven_outside_sign(self):
        mesh=self.stacked();N=np.tile([-1.,0,0],(len(mesh.vertices),1))
        old=EvaluatedNativeSurface(mesh.vertices,N,mesh.faces)
        new=EvaluatedNativeSurface(mesh.vertices,N,mesh.faces,horizontal_slice_proof=True,complete_fixture_mesh=mesh)
        points=np.array([[.3,1.1,0],[.08,1.1,0]])
        before=old.signed(points);after=new.signed(points)
        self.assertLess(before[0][0],0);self.assertGreater(after[0][0],0)
        self.assertEqual(before[0][1],after[0][1])
        np.testing.assert_array_equal(np.abs(after[0]),np.abs(before[0]))
        np.testing.assert_array_equal(after[1],before[1]);np.testing.assert_array_equal(after[2],before[2])

    def test_real_inside_contact_and_default_path_are_retained(self):
        mesh=self.stacked();P=np.array([[.09,1.1,0]])
        old=EvaluatedNativeSurface(mesh.vertices,mesh.vertex_normals,mesh.faces)
        new=EvaluatedNativeSurface(mesh.vertices,mesh.vertex_normals,mesh.faces,horizontal_slice_proof=True,complete_fixture_mesh=mesh)
        self.assertLess(old.signed(P)[0][0],0)
        for a,b in zip(old.signed(P),new.signed(P)):np.testing.assert_array_equal(a,b)

    def test_explicit_complete_fixture_is_required(self):
        mesh=self.stacked()
        with self.assertRaisesRegex(AssertionError,'complete verified'):
            EvaluatedNativeSurface(mesh.vertices,mesh.vertex_normals,mesh.faces,horizontal_slice_proof=True)

    def test_plane_cache_is_exact_and_bounded(self):
        mesh=self.tetra();memo=HorizontalSliceBounds(mesh,cache_planes=2);uncached=HorizontalSliceBounds(mesh,cache_planes=0)
        points=np.array([[.7,.8,.05],[.8,.1,.05],[.5,.6,.05]])
        np.testing.assert_array_equal(memo.outside(points),uncached.outside(points))
        self.assertLessEqual(len(memo.cache),2)
        np.testing.assert_array_equal(memo.outside(points),uncached.outside(points))

    def test_fixture_proof_retains_the_unfiltered_complete_surface(self):
        mesh=self.stacked()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'body.npz'
            np.savez(path,P=mesh.vertices,N=mesh.vertex_normals,I=mesh.faces)
            record={'parts':[{'mesh':'body','file':path.name,'sha256':sha(path)}]}
            surface=load_fixture(Path(directory)/'manifest.json',record,horizontal_slice_proof=True)
            self.assertEqual(len(surface._slice_bounds.mesh.faces),len(mesh.faces))
            self.assertLess(len(surface.T),len(mesh.faces))
            self.assertGreater(surface._slice_bounds.mesh.bounds[1,0],surface.mesh.bounds[1,0])


if __name__=='__main__':unittest.main()
