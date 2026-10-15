"""Read clipped water geometry, including elevated banks and export seams."""
from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import terrain_export as T
import landscape as L
import scene_io as S
import collision_export as C
from amberwood import mesh as M


def world(x,z,height,plan=None):
    gx,gz=np.meshgrid(np.asarray(x,float),np.asarray(z,float))
    plan=plan or {'seed':2042,'sea_level':0.,'rivers':[],'lakes':[]}
    h=height(gx,gz)
    return SimpleNamespace(x=np.asarray(x),z=np.asarray(z),x0=0.,z0=0.,gx=gx,gz=gz,height=h,
        road_distance=np.full(h.shape,100.),plan=plan,water=L.water_fields(gx,gz,height=h,plan=plan),
        owner=np.zeros((len(z)-1,len(x)-1),int),ids=['west'])


def geometry(w):
    p=np.c_[w.gx.ravel(),w.height.ravel(),w.gz.ravel()]
    row,col=np.indices(w.owner.shape);a=(row*len(w.x)+col).ravel()
    cells=np.stack((a,a+len(w.x),a+1,a+1,a+len(w.x),a+len(w.x)+1),axis=1)
    return T.clipped_water_surface(w,p,cells)


def area(mesh):
    p=mesh['positions'][mesh['triangles']].astype(float)
    return np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,1]*.5


class WaterExportTests(unittest.TestCase):
    def test_curved_river_edges_near_one_dry_corner_share_the_true_profile(self):
        points=[[0.,0.,10.],[2.,3.,10.1],[8.,6.,10.3]]
        plan={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':100.,'points':points}]}
        def bank(x,z):
            level=L._polyline_field(x,z,points)[1]
            return level+np.where((x==2)&(z==2),-.015+.0001,-.5)
        w=world(np.arange(0,7,2.),np.arange(0,7,2.),bank,plan)
        mesh=geometry(w);extra=mesh['positions'][w.height.size:]
        self.assertGreater(len(extra),0)
        expected=L._polyline_field(extra[:,0].astype(float),extra[:,2].astype(float),points)[1]
        np.testing.assert_array_equal(extra[:,1],expected.astype(np.float32))
        faces=mesh['positions'][mesh['triangles']].astype(float)
        normals=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
        grade=np.hypot(normals[:,0],normals[:,2])/normals[:,1]
        self.assertLess(float(grade.max()),.1,'A tiny clipped corner must not become a folded water wall')
        self.assertTrue((normals[:,1]>0).all())

    def test_dry_corner_cannot_borrow_another_water_body_height(self):
        plan={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':.6,'points':[[0.,-10.,5.],[0.,10.,5.]]}]}
        w=world(np.arange(0,5,2.),np.arange(0,5,2.),
            lambda x,z:np.where(x==0,4.,np.where(x==4,-.5,.5)),plan)
        level,_=T.water_vertex_fields(w)
        self.assertEqual(level[1,1],5.,'Fixture must reproduce the wrong nearest-body dry-corner extension')
        mesh=geometry(w);faces=mesh['positions'][mesh['triangles']]
        sea=faces[mesh['sourceCells']%2==1]
        self.assertGreater(len(sea),0)
        np.testing.assert_array_equal(sea[:,:,1],0.)
        self.assertTrue((area(mesh)>0).all())
        x,z=np.meshgrid(np.arange(.1,4,.2),np.arange(.1,4,.2))
        wet,top=T.sample_water_surface(w,x,z)
        np.testing.assert_array_equal(top[wet&(x>=2)],0.)

    def test_collision_depth_matches_actual_clipped_triangles_on_banks(self):
        river={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':1.5,'points':[[1.,-20.,10.],[1.,20.,14.]]}]}
        mixed={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':.6,'points':[[0.,-10.,5.],[0.,10.,5.]]}]}
        bend={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':100.,'points':[[0.,0.,10.],[2.,2.,12.],[8.,8.,12.5]]}]}
        cases=[world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:x-2.8),
               world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:12.+z*.1+np.abs(x-1)-1.3,river),
               world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:np.where(x==0,4.,np.where(x>=4,-.5,.5)),mixed),
               world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:np.where(x<=2,8.,15.),bend)]
        x,z=np.meshgrid(np.arange(.25,8.,.5),np.arange(.25,8.,.5))
        for w in cases:
            with self.subTest(plan=w.plan):
                mesh=geometry(w);triangles=mesh['positions'][mesh['triangles']].astype(float)
                actual=np.full(x.shape,np.nan)
                for a,b,c in triangles:
                    u,v=b[[0,2]]-a[[0,2]],c[[0,2]]-a[[0,2]]
                    determinant=u[0]*v[1]-u[1]*v[0]
                    s=((x-a[0])*v[1]-(z-a[2])*v[0])/determinant
                    t=(u[0]*(z-a[2])-u[1]*(x-a[0]))/determinant
                    inside=(s>=-1e-8)&(t>=-1e-8)&(s+t<=1+1e-8)
                    actual[inside]=a[1]+s[inside]*(b[1]-a[1])+t[inside]*(c[1]-a[1])
                wet,level=C.water_samples(w,x,z)
                np.testing.assert_array_equal(wet,np.isfinite(actual))
                np.testing.assert_allclose(level[wet],actual[wet],atol=2e-6)

    def test_physical_water_cache_invalidates_when_authority_changes(self):
        w=world(np.arange(0,5,2.),np.arange(0,5,2.),lambda x,z:np.full(x.shape,-1.))
        wet,top=T.sample_water_surface(w,[1.],[1.]);self.assertTrue(wet[0]);self.assertEqual(top[0],0.)
        w.plan['sea_level']=2.;w.water=L.water_fields(w.gx,w.gz,height=w.height,plan=w.plan)
        wet,top=T.sample_water_surface(w,[1.],[1.]);self.assertTrue(wet[0]);self.assertEqual(top[0],2.)

    def test_sloping_shore_is_clipped_at_physical_depth_not_a_whole_cell(self):
        w=world(np.arange(0,7,2.),np.arange(0,7,2.),lambda x,z:x-2.8)
        mesh=geometry(w);p=mesh['positions'][mesh['triangles']]
        self.assertAlmostEqual(float(p[:,:,0].max()),2.785,places=5)
        self.assertAlmostEqual(float(area(mesh).sum()),2.785*6,places=5)
        self.assertTrue((area(mesh)>0).all())
        self.assertGreater(mesh['report']['sharedEdgeIntersections'],0)

    def test_elevated_sloping_river_never_folds_to_the_sea_at_dry_bank_corners(self):
        plan={'seed':2042,'sea_level':0.,'lakes':[],
            'rivers':[{'width':1.5,'points':[[1.,-20.,10.],[1.,20.,14.]]}]}
        w=world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:12.+z*.1+np.abs(x-1)-1.3,plan)
        self.assertEqual(float(w.water['surface'][0,2]),0.,'The dry corner has sea level in the authority mask')
        original=w.height.copy();wet=w.water['mask'].copy();surface=w.water['surface'].copy()
        mesh=geometry(w);p=mesh['positions'][mesh['triangles']]
        np.testing.assert_allclose(p[:,:,1],12.+p[:,:,2]*.1,atol=2e-6)
        self.assertAlmostEqual(float(p[:,:,0].max()),2.285,places=5)
        self.assertTrue((area(mesh)>0).all())
        original_vertices=mesh['positions'][:w.height.size]
        np.testing.assert_array_equal(original_vertices[w.water['mask'].ravel(),1],w.water['surface'][w.water['mask']].astype(np.float32))
        np.testing.assert_array_equal(w.height,original);np.testing.assert_array_equal(w.water['mask'],wet)
        np.testing.assert_array_equal(w.water['surface'],surface)

    def test_authored_lake_domain_still_bounds_water_above_lower_surrounding_ground(self):
        plan={'seed':2042,'sea_level':0.,'rivers':[],
            'lakes':[{'center':[6.,6.],'radii':[3.3,3.3],'level':20.,'depth':2.}]}
        w=world(np.arange(0,13,2.),np.arange(0,13,2.),lambda x,z:np.full_like(x,18.),plan)
        mesh=geometry(w);p=mesh['positions'][mesh['triangles']]
        np.testing.assert_allclose(p[:,:,1],20.)
        self.assertAlmostEqual(float(p[:,:,0].min()),2.7,places=5)
        self.assertAlmostEqual(float(p[:,:,0].max()),9.3,places=5)
        self.assertLess(float(area(mesh).sum()),np.pi*3.3**2)

    def test_datum_jump_is_preserved_but_not_extrapolated_into_a_bank(self):
        values=np.array([[0.,12.,12.],[0.,12.,0.],[0.,12.,0.]])
        wet=np.array([[True,True,True],[True,True,False],[True,True,False]])
        derivative=T._wet_gradient(values,wet,1)
        np.testing.assert_array_equal(derivative,0.)
        np.testing.assert_array_equal(values[wet],[0,12,12,0,12,0,12])

    def test_named_and_chunk_boundary_vertices_match_in_actual_glb(self):
        w=world(np.arange(92,101,2.),np.arange(0,9,2.),lambda x,z:z-3.3)
        w.ids=['west','east'];w.owner[:,2:]=1
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'surface.glb';parts=T.partition_surface(w,path)
            doc,body=S.GR.load(path);seams=[]
            for region in w.ids:
                roots=[i for i,n in enumerate(doc['nodes']) if n.get('name','').startswith('Water_'+region+'_')]
                self.assertEqual(len(roots),1)
                primitive=doc['meshes'][doc['nodes'][roots[0]]['mesh']]['primitives'][0]
                attrs={name:S.GR.accessor(doc,body,ref) for name,ref in primitive['attributes'].items()}
                select=attrs['POSITION'][:,0]==96.
                values=np.concatenate([attrs[name][select] for name in ('POSITION','NORMAL','TEXCOORD_0')],axis=1)
                seams.append(values[np.lexsort((values[:,2],values[:,1]))])
            np.testing.assert_array_equal(*seams)
            self.assertTrue(any(abs(row[2]-3.285)<1e-5 for row in seams[0]))
            self.assertEqual(set(parts['west']),{'00_00'});self.assertEqual(set(parts['east']),{'01_00'})

    def test_authored_river_record_cannot_shadow_the_output_path(self):
        river={'id':'authored-river','width':3.,'points':[[2.,0.,2.],[2.,8.,2.]]}
        plan={'seed':2042,'sea_level':0.,'lakes':[],'rivers':[river]}
        w=world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:np.full_like(x,-1.),plan)
        record={'id':'authored-river','kind':'river','replacesPlanFeatureId':'authored-river',
                'surface':{'preset':'Water','rotationDegrees':0.,'materialMode':'surface'}}
        w.authoring_snapshot=SimpleNamespace(document={'paths':[record]},translation=np.zeros(3))
        with tempfile.TemporaryDirectory() as temporary, patch.object(T,'authored_overlays',return_value=[]):
            output=Path(temporary)/'surface.glb'
            T.partition_surface(w,output)
            self.assertTrue(output.is_file())
            self.assertEqual(w.authored_overlay_report['waterMaterials'][0]['id'],'authored-river')

    def test_two_authored_regions_both_supply_river_water_materials(self):
        rivers=[
            {'id':'mirror_outlet','width':2.,'points':[[2.,0.,2.],[2.,8.,2.]]},
            {'id':'horn_tributary','width':2.,'points':[[6.,0.,2.],[6.,8.,2.]]},
        ]
        plan={'seed':2042,'sea_level':-10.,'lakes':[],'rivers':rivers}
        w=world(np.arange(0,9,2.),np.arange(0,9,2.),lambda x,z:np.full_like(x,-1.),plan)
        surface={'preset':'Water','rotationDegrees':0.,'materialMode':'surface'}
        w.authoring_snapshots={
            'mirrorhold':SimpleNamespace(document={'regionId':'mirrorhold','paths':[
                {'id':'mirror-outlet','kind':'river','replacesPlanFeatureId':'mirror_outlet',
                 'surface':surface}]},translation=np.array([840.,0.,650.])),
            'whitehorn_range':SimpleNamespace(document={'regionId':'whitehorn_range','paths':[
                {'id':'horn-tributary','kind':'river','replacesPlanFeatureId':'horn_tributary',
                 'surface':surface}]},translation=np.array([550.,0.,220.])),
        }
        with tempfile.TemporaryDirectory() as temporary, patch.object(T,'authored_overlays',return_value=[]):
            T.partition_surface(w,Path(temporary)/'surface.glb')
        records=w.authored_overlay_report['waterMaterials']
        self.assertEqual([(item['region'],item['id']) for item in records],[
            ('mirrorhold','mirror-outlet'),('whitehorn_range','horn-tributary')])
        self.assertTrue(all(item['triangles']>0 for item in records))

    def test_chunked_authored_road_emits_scalar_triangle_indices(self):
        mesh=M.Mesh(positions=np.array([[0.,0.,0.],[1.,0.,0.],[0.,0.,1.],[1.,0.,1.]]),
            normals=np.tile([0.,1.,0.],(4,1)),uvs=np.zeros((4,2)),
            indices=np.array([0,1,2,1,3,2]),material='road')
        piece=T._mesh_faces(mesh,np.array([0,1]))
        self.assertEqual(piece.indices.ndim,1)
        self.assertEqual(piece.triangle_count,2)
        np.testing.assert_array_equal(piece.positions[piece.indices].reshape(-1,3,3),
                                      mesh.positions[mesh.indices].reshape(-1,3,3))

    def test_each_clipped_face_stays_inside_its_actual_source_cell(self):
        w=world(np.arange(0,11,2.),np.arange(0,11,2.),lambda x,z:x*.6+z*.4-4.1)
        mesh=geometry(w);p=mesh['positions'][mesh['triangles']]
        row,col=np.divmod(mesh['sourceCells'],len(w.x)-1)
        self.assertTrue((p[:,:,0]>=w.x[col,None]-1e-6).all())
        self.assertTrue((p[:,:,0]<=w.x[col+1,None]+1e-6).all())
        self.assertTrue((p[:,:,2]>=w.z[row,None]-1e-6).all())
        self.assertTrue((p[:,:,2]<=w.z[row+1,None]+1e-6).all())
        self.assertTrue((area(mesh)>0).all())

    def test_dry_surface_emits_no_degenerate_water(self):
        w=world([0.,2.,4.],[0.,2.,4.],lambda x,z:np.ones_like(x))
        mesh=geometry(w);self.assertEqual(len(mesh['triangles']),0)


if __name__=='__main__':unittest.main()
