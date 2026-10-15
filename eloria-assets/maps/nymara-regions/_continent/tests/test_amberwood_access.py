"""The canopy crossing remains actual continuous geometry; source bytes stay fixed."""
from pathlib import Path
import sys,tempfile,unittest,copy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import amberwood_access as A
import assemblies
from bridge_export import G,M
from ferry_export import ribbon


class AmberAccessTests(unittest.TestCase):
    def test_tiny_floor_does_not_claim_a_distant_point(self):
        floor=np.array([[[0.,0,0],[.0001,0,0],[0,0,.0001]]])
        self.assertIsNone(A.top_at(floor,10,10))
        self.assertAlmostEqual(A.top_at(floor,.00001,.00001),0.)

    def test_camp_layout_changes_source_roots_before_common_placement(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);axis=np.array([-500.,500.])
            np.savez(path/'foundation-samples.npz',x=axis,z=axis,height=np.zeros((2,2)))
            names=[*[f'Prop_Tent_ridge_camp_{i:02d}' for i in range(1,6)],*[f'Brazier_ridge_camp_{i:02d}' for i in range(1,4)]]
            b=G.GltfBuilder('camp');b.add_material(G.Material('timber'))
            for name in names:
                b.add_mesh(name,ribbon(np.array([[160.,-225],[162,-225]]),[0.,0.],np.array([0.,1.]),.4,'timber'),with_tangents=False)
                b.add_node(G.Node(name,mesh=name))
            b.write_glb(str(path/'camp.glb'));doc,body=A.S.GR.load(path/'camp.glb');original=copy.deepcopy(doc)
            metadata={'placements':[{'node':n,'position':[161.,0.,-225.]} for n in names]}
            updated,meta=A.prepare_camp_source(doc,body,metadata,path)
            self.assertEqual(doc,original);self.assertNotIn('continentCampLayout',metadata)
            self.assertEqual(len(meta['continentCampLayout']),8)
            centers=np.array([r['sourceCenter'] for r in meta['continentCampLayout'][:5]])
            distances=np.linalg.norm(centers[:,None]-centers[None,:],axis=2)+np.eye(5)*100
            self.assertGreater(float(distances.min()),5.)

    def test_opening_removes_visible_rail_and_preserves_floor_and_support(self):
        with tempfile.TemporaryDirectory() as d:
            b=G.GltfBuilder('platform');b.add_material(G.Material('timber'))
            root=b.add_node(G.Node('Platform'))
            b.add_mesh('Walk_floor',M.box((8.,.2,8.),center=(0.,9.9,0.),material='timber'),with_tangents=False)
            b.add_node(G.Node('Walk_floor',mesh='Walk_floor'),parent=root)
            rail=M.box((2.,.2,.2),center=(0.,11.,0.),material='timber')
            support=M.box((.3,3.,.3),center=(0.,8.4,0.),material='timber')
            far=M.box((2.,.2,.2),center=(7.,11.,0.),material='timber')
            b.add_mesh('Solid',M.merge([rail,support,far],material='timber'),with_tangents=False)
            b.add_node(G.Node('Solid',mesh='Solid'),parent=root)
            path=Path(d)/'platform.glb';b.write_glb(str(path));doc,body=A.S.GR.load(path)
            before=copy.deepcopy(doc);floor=A.walk_faces(doc,body,root)
            updated,encoded,report=A.open_platform_rail(doc,body,root,np.zeros(2),10.)
            self.assertEqual(doc,before);self.assertEqual(report['removedRailComponents'],1)
            self.assertEqual(report['removedRailTriangles'],12)
            np.testing.assert_array_equal(A.walk_faces(updated,encoded,root),floor)
            self.assertEqual(encoded[:len(body)],body)

    def source(self,folder):
        b=G.GltfBuilder('crossing fixture');b.add_material(G.Material('timber'))
        for name,points,heights,side in [
            ('Walk_upper',np.array([[0.,-20],[0,20]]),[10.,10.],np.array([1.,0.])),
            ('Walk_lower',np.array([[-40.,0],[40,0]]),[4.,4.],np.array([0.,1.]))]:
            # Dense stations model the retained planks and preserve curvature.
            p=np.linspace(points[0],points[1],161);h=np.linspace(*heights,161)
            b.add_mesh(name,ribbon(p,h,side,1.5,'timber'),with_tangents=False);b.add_node(G.Node(name,mesh=name))
        path=Path(folder)/'source.glb';b.write_glb(str(path));return (*A.S.GR.load(path),path.read_bytes())

    def test_junction_keeps_end_levels_and_exact_horizontal_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            doc,body,source=self.source(d);old=A.walk_faces(doc,body,1)
            new,encoded,report=A.join_canopy_crossing(doc,body,0,1,np.zeros(2))
            actual=A.walk_faces(new,encoded,1)
            np.testing.assert_array_equal(actual[:,:,[0,2]],old[:,:,[0,2]])
            endpoints=abs(old[:,:,0])>=27
            np.testing.assert_allclose(actual[:,:,1][endpoints],old[:,:,1][endpoints])
            self.assertAlmostEqual(A.top_at(actual,0,0),10.)
            normal=np.cross(actual[:,1]-actual[:,0],actual[:,2]-actual[:,0])
            grade=np.hypot(normal[:,0],normal[:,2])/abs(normal[:,1])
            self.assertLess(float(grade.max()),.65)
            np.testing.assert_array_equal(A.walk_faces(new,encoded,0),A.walk_faces(doc,body,0))
            self.assertEqual((Path(d)/'source.glb').read_bytes(),source)
            self.assertEqual(report['taperMetres'],27.)

    def test_missing_crossing_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            doc,body,_=self.source(d)
            with self.assertRaisesRegex(ValueError,'no sampled floor'):
                A.join_canopy_crossing(doc,body,0,1,np.array([200.,200.]))

    def test_ridge_camp_retains_all_tents_tower_and_braziers_as_one_transform(self):
        names=['Landmark_Watchtower_1',*[f'Prop_Tent_ridge_camp_{i:02d}' for i in range(1,6)],*[f'Brazier_ridge_camp_{i:02d}' for i in range(1,4)]]
        self.assertEqual({assemblies.placement_group('amberwood',{'node':n,'kind':'prop'}) for n in names},{'amberwood.ridge-camp'})
        self.assertIsNone(assemblies.placement_group('amberwood',{'node':'Landmark_Watchtower_2','kind':'prop'}))
        self.assertEqual(assemblies.placement_group('amberwood',{'node':'Landmark_GreatTree_Wood','kind':'landmark'}),'amberwood.canopy-village')


if __name__=='__main__':unittest.main()
