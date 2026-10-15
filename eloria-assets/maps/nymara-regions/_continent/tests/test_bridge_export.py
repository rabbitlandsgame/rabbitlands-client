"""Read actual exported deck faces: overlap cannot pass as two good ribbons."""
from pathlib import Path
from dataclasses import dataclass,replace
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge_export as B
import build_continent as BC
import coastal_bridge_export as C
import scene_io as S


@dataclass(frozen=True)
class ExportSupport:
    name:str
    footprint_xz:np.ndarray
    top_height_metres:float
    triangles:np.ndarray
    @property
    def encoded_triangles(self):return self.triangles.astype(np.float32).astype(float)


@dataclass(frozen=True)
class ExportClaim:
    claim_id:str
    encoded_floor_triangles:np.ndarray
    supports:tuple
    stairs:tuple=()


def world():
    w=SimpleNamespace(x0=0.,z0=0.,x1=48.,z1=40.,ids=['west','east'],plan={},connections=[
        {'id':'west--east','type':'walk','regions':['west','east'],'anchor':[24,20],'normal':[1,0]}])
    w.height_at=lambda x,z:np.where((np.asarray(x)>=18)&(np.asarray(x)<=30),-2.,2.)+np.asarray(z)*0
    w.owner_at=lambda x,z:np.where(np.asarray(x)<24,0,1)+np.asarray(z,dtype=int)*0
    w.roads=[{'id':'out','width':3.,'points':[[4,900,20],[44,-900,20]]},
             {'id':'back','width':3.,'points':[[44,777,20],[4,-777,20]]}]
    return w


def water(x,z,*,height,plan):
    wet=(np.asarray(x)>=18)&(np.asarray(x)<=30)
    return {'mask':wet,'depth':np.where(wet,2.,0.),'surface':np.zeros(np.shape(height))}


class BridgeUnionTests(unittest.TestCase):
    def test_authored_bridge_controls_export_from_each_region_without_generated_duplicates(self):
        from amberwood import gltf as G

        class Snapshot:
            def __init__(self,region,translation):
                self.translation=np.asarray(translation,float)
                self.document={'regionId':region,'bridges':[{
                    'id':'shared','start':[0.,1.,0.],'end':[4.,1.,0.],
                    'width':2.,'arch':0.,'waterClearance':0.,
                    'deckTextureRotationDegrees':0.,
                    'deckSurface':{'preset':'Timber','rotationDegrees':0.},
                    'supportSurface':{'preset':'Stone','rotationDegrees':0.}}]}
            def continent_point(self,point):
                return np.asarray(point,float)+self.translation

        snapshots={
            'sunmane_steppe':Snapshot('sunmane_steppe',[10.,0.,0.]),
            'amethyst_barrens':Snapshot('amethyst_barrens',[100.,0.,20.]),
        }
        current=SimpleNamespace(authoring_snapshots=snapshots,
            authoring_snapshot=snapshots['sunmane_steppe'],
            ids=['sunmane_steppe','amethyst_barrens'],plan={'rivers':[]})
        # Midpoint ownership deliberately says Sunmane for both controls. A
        # saved Amethyst control must still remain Amethyst authority.
        current.owner_at=lambda x,z:0
        current.height_at=lambda x,z:np.asarray(x)*0

        parts,triangles,records=B._authored_bridge_geometry(
            current,G.GltfBuilder('two authored regions'))
        walks=[part for part in parts if part[3]]

        self.assertEqual({part[1] for part in walks},{
            'Walk_AuthoredBridge_shared_sunmane_steppe',
            'Walk_AuthoredBridge_amethyst_barrens__shared_amethyst_barrens'})
        self.assertEqual({part[0] for part in walks},
                         {'sunmane_steppe','amethyst_barrens'})
        self.assertEqual({record['id'] for record in records},
                         {'shared','amethyst_barrens__shared'})
        self.assertEqual(len(triangles),2)
        self.assertEqual(sorted(round(float(value[:,:,0].min())) for value in triangles),
                         [10,100])
        authored_owners={current.ids.index(region) for region in snapshots}
        # The corresponding wholly-owned loose components are suppressed, so
        # neither saved control is accompanied by a generated duplicate.
        self.assertTrue(B._suppresses_generated_authored_component(
            {'id':501,'sites':[]},np.array([0,0]),authored_owners))
        self.assertTrue(B._suppresses_generated_authored_component(
            {'id':502,'sites':[]},np.array([1,1]),authored_owners))

    def test_authored_bridge_authority_suppresses_only_fully_saved_loose_components(self):
        owners=np.array([1,1,1])
        self.assertTrue(B._suppresses_generated_authored_component(
            {'id':501,'sites':[]},owners,{1,3}))
        self.assertFalse(B._suppresses_generated_authored_component(
            {'id':15,'sites':[14]},owners,{1,3}),'a stable claimed crossing survives overlap')
        self.assertFalse(B._suppresses_generated_authored_component(
            {'id':502,'sites':[]},np.array([0,1,1]),{1,3}),'mixed neighbour coverage stays whole')
        self.assertTrue(B._suppresses_generated_authored_component(
            {'id':502,'sites':[]},np.array([1,3,1]),{1,3}),
            'two saved slices jointly replace one published component')
        self.assertFalse(B._suppresses_generated_authored_component(
            {'id':501,'sites':[]},owners,set()),'procedural builds retain their component')

    def test_saved_loose_component_is_suppressed_before_equivalent_mesh_clipping(self):
        class FullOutline:
            @staticmethod
            def clip(triangle):return [triangle]

        current=SimpleNamespace(x0=0.,z0=0.)
        current.owner_at=lambda x,z:np.where(np.asarray(x)<1.,0,1)
        component={'id':501,'sites':[],'slice':(slice(0,1),slice(0,2)),
                   'cells':np.ones((1,2),bool),'height':np.zeros((2,3)),
                   'arch':None,'outline':FullOutline()}
        vertices,indices,source_owners=B._component_source_triangles(current,component)
        mesh,emitted_owners=B.deck_mesh(current,component)

        self.assertGreater(len(mesh.indices),0)
        self.assertEqual(source_owners.tolist(),emitted_owners.tolist())
        self.assertTrue(B._suppresses_generated_authored_component_before_mesh(
            current,component,{0,1}))
        self.assertEqual(
            B._suppresses_generated_authored_component(
                component,emitted_owners,{0,1}),
            B._suppresses_generated_authored_component_before_mesh(
                current,component,{0,1}))

    def test_saved_loose_precheck_preserves_mixed_unowned_site_and_empty_failures(self):
        class FullOutline:
            @staticmethod
            def clip(triangle):return [triangle]
        class EmptyOutline:
            @staticmethod
            def clip(triangle):return []

        current=SimpleNamespace(x0=0.,z0=0.)
        current.owner_at=lambda x,z:np.where(np.asarray(x)<1.,0,1)
        base={'id':501,'sites':[],'slice':(slice(0,1),slice(0,2)),
              'cells':np.ones((1,2),bool),'height':np.zeros((2,3)),
              'arch':None,'outline':FullOutline()}
        self.assertFalse(B._suppresses_generated_authored_component_before_mesh(
            current,base,{0}),'mixed saved/procedural coverage must still build')
        self.assertFalse(B._suppresses_generated_authored_component_before_mesh(
            current,base,set()),'an unowned component must still build')
        self.assertFalse(B._suppresses_generated_authored_component_before_mesh(
            current,{**base,'sites':[17]},{0,1}),
            'stable crossing sites use their exact claim path')
        empty={**base,'outline':EmptyOutline()}
        self.assertFalse(B._suppresses_generated_authored_component_before_mesh(
            current,empty,{0,1}))
        with self.assertRaisesRegex(ValueError,'no road-width deck'):
            B.deck_mesh(current,empty)

    def test_saved_asset_crossing_claims_are_stable_across_site_reordering(self):
        def snapshot(region,key,asset):
            return SimpleNamespace(document={'regionId':region,'objects':[{
                'id':asset,'metadata':{'authoredCrossing':{'id':key}}}]})
        current=SimpleNamespace(
            authoring_snapshots={
                'mirrorhold':snapshot('mirrorhold','mirror_outlet@16','mirror-bridge'),
                'whitehorn_range':snapshot(
                    'whitehorn_range','horn_tributary@128','whitehorn-bridge'),
            },
            crossing_sites=[
                {'id':91,'key':'horn_tributary@128'},
                {'id':7,'key':'mirror_outlet@16'},
                {'id':23,'key':'unclaimed@2'},
            ])
        claims=B._authored_crossing_claims(current)
        self.assertEqual(set(claims),{'mirror_outlet@16','horn_tributary@128'})
        self.assertEqual(B._claimed_component_crossings(
            current,{'sites':[91]},claims),('horn_tributary@128',))
        self.assertEqual(B._claimed_component_crossings(
            current,{'sites':[7]},claims),('mirror_outlet@16',))
        self.assertEqual(B._claimed_component_crossings(
            current,{'sites':[23]},claims),())
        with self.assertRaisesRegex(ValueError,'mixes saved and procedural'):
            B._claimed_component_crossings(current,{'sites':[91,23]},claims)

    def test_duplicate_saved_crossing_claims_fail_closed(self):
        def snapshot(region):
            return SimpleNamespace(document={'regionId':region,'objects':[{
                'id':region+'-bridge',
                'metadata':{'authoredCrossing':{'id':'shared-river@8'}}}]})
        current=SimpleNamespace(authoring_snapshots={
            'mirrorhold':snapshot('mirrorhold'),
            'whitehorn_range':snapshot('whitehorn_range'),
        })
        with self.assertRaisesRegex(ValueError,'claimed by both'):
            B._authored_crossing_claims(current)

    def test_keeper_crossing_uses_bounded_asymmetric_landings_after_site_reordering(self):
        w=world();road=w.roads[0]
        for site_id in (13,12):
            with self.subTest(site_id=site_id):
                site={'id':site_id,'key':'horn_tributary@124','wetEdges':[[18.,20.],[30.,20.]]}
                geometry=B._claimed_geometry_v7(w,site,6.,[road])
                self.assertEqual((geometry['leftLandingMetres'],geometry['rightLandingMetres']),(4.,6.))
                self.assertAlmostEqual(geometry['policyStart'],-4.)
                self.assertAlmostEqual(geometry['policyEnd'],18.)
        ordinary=B._claimed_geometry_v7(
            w,{'id':13,'key':'another_crossing@124','wetEdges':[[18.,20.],[30.,20.]]},6.,[road])
        self.assertEqual((ordinary['leftLandingMetres'],ordinary['rightLandingMetres']),(6.,6.))
        saved=B.SITE_BANK_LANDINGS['horn_tributary@124']
        try:
            B.SITE_BANK_LANDINGS['horn_tributary@124']=(0.,6.)
            with self.assertRaisesRegex(B.BP.ProfileError,'positive policy cap'):
                B._claimed_geometry_v7(
                    w,{'id':12,'key':'horn_tributary@124','wetEdges':[[18.,20.],[30.,20.]]},6.,[road])
        finally:
            B.SITE_BANK_LANDINGS['horn_tributary@124']=saved

    def test_a_sliver_outline_is_no_floor_and_a_square_still_triangulates(self):
        # Four vertices a tenth of a millimetre apart: below the collapse threshold's reach, no ear has area.
        sliver=np.array([[1171.39,5.,1421.61],[1171.3901,5.,1421.61],[1171.3901,5.,1421.6101],[1171.39,5.,1421.6101]])
        self.assertEqual(B.triangulate_floor(sliver),[])
        square=np.array([[0.,5.,0.],[0.,5.,4.],[4.,5.,4.],[4.,5.,0.]])
        faces=B.triangulate_floor(square)
        self.assertEqual(len(faces),2)
        self.assertAlmostEqual(sum(abs(B._area_xz(np.asarray(face))) for face in faces),16.)

    def test_float32_retrace_in_clipped_deck_preserves_the_floor(self):
        outline=np.array([
            [535.70195163,160.09912967,270.86097846],
            [535.70194465,160.09912782,270.86098311],
            [535.70193499,160.09912526,270.86098953],
            [535.70192390,160.09912231,270.86099690],
            [535.72059446,160.10407295,270.84858346],
            [535.89778436,160.17541211,270.64747367],
            [535.83373155,160.15842807,270.69006017],
            [535.65653879,160.08708863,270.89117022],
        ])
        faces=B.triangulate_floor(outline)
        self.assertTrue(faces)
        self.assertAlmostEqual(sum(abs(B._area_xz(face)) for face in faces),
                               abs(B._area_xz(outline)),places=8)
        self.assertLess(sum(abs(B._area_xz(face)) for face in faces
                            if abs(B._area_xz(face))<1e-8),1e-8)
        two_retraces=np.array([
            [535.7019516318896,160.09912966755485,270.86097846202097],
            [535.7019238964467,160.09912231349648,270.86099690172836],
            [535.7205944634438,160.10407295012647,270.8485834597882],
            [535.7205669596289,160.10406389485416,270.84860222121523],
            [535.8977843565757,160.17541211193614,270.6474736730304],
            [535.8337315542072,160.1584280708138,270.69006017450533],
            [535.6565387899158,160.08708862923012,270.8911702232607],
        ])
        with self.assertRaisesRegex(ValueError,'could not be triangulated'):
            B.triangulate_floor(two_retraces,minimum_area=0.)
        # A material self-crossing must still fail rather than lose a deck.
        bowtie=np.array([[-.21191726,0.,1.56931111],[1.69286930,0.,.86946590],
                         [1.96348870,0.,1.84700546],[-1.87172593,0.,-1.60839886],
                         [.80992050,0.,2.47169805]])
        with self.assertRaisesRegex(ValueError,'could not be triangulated'):
            B.triangulate_floor(bowtie,minimum_area=0.)

    def test_encoded_pier_cap_stays_under_entire_sloping_floor(self):
        x,z=1000.5,1400.5
        positions=np.array([[x-1,0,z-1],[x+1,0,z-1],[x-1,0,z+1],[x+1,0,z+1]])
        positions[:,1]=82.+.44*(positions[:,0]-x)+.44*(positions[:,2]-z)
        faces=positions[[[0,2,1],[1,2,3]]].astype(np.float32).astype(float)
        minimum=B.pier_floor_minimum(faces,x,z)
        self.assertLess(minimum,82.-.3,'The low footprint corner must govern the cap')
        w=SimpleNamespace(height_at=lambda x,z:70.)
        mesh=B.pier_mesh(w,faces,x,z)
        self.assertIsNotNone(mesh)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'pier.glb';builder=B.G.GltfBuilder()
            builder.add_material(B.G.Material('bridge_stone'))
            builder.add_mesh('pier',mesh,with_tangents=False);builder.add_node(B.G.Node('pier',mesh='pier'))
            builder.write_glb(str(path));doc,body=S.GR.load(path)
            actual=S.GR.triangles(doc,body,[0])
        self.assertLessEqual(float(actual[:,:,1].max()),minimum-.12)
        self.assertGreater(float(actual[:,:,1].max()),81.,'A real visible support must remain')

    def test_pier_minimum_includes_internal_floor_break_and_rejects_partial_support(self):
        p=np.array([[-1.,2.,-1.],[1.,2.,-1.],[1.,2.,1.],[-1.,2.,1.],[0.,1.7,0.]])
        faces=p[[[0,4,1],[1,4,2],[2,4,3],[3,4,0]]].astype(np.float32).astype(float)
        self.assertAlmostEqual(B.pier_floor_minimum(faces,.2,.1),float(np.float32(1.7)),places=6)
        self.assertIsNone(B.pier_floor_minimum(faces,.9,.9),
                          'A pier footprint outside the emitted deck cannot use an invisible extrapolated plane')
        w=SimpleNamespace(height_at=lambda x,z:-2.)
        support,fit=B.fit_pier(w,faces,.9,.9)
        self.assertIsNotNone(support)
        self.assertGreater(fit['shiftMetres'],0)
        self.assertLessEqual(fit['shiftMetres'],1.2)
        self.assertIsNotNone(B.pier_floor_minimum(faces,*fit['position']))
        _,same=B.fit_pier(w,faces,.9,.9)
        self.assertEqual(fit,same,'Edge support fitting must be deterministic')

    def test_opposing_duplicate_roads_export_one_floor_and_identical_thresholds(self):
        w=world();samples=w.height_at(np.arange(48.),20).copy()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'bridges.glb';parts=B.build_bridges(w,path,water_fields=water)
            doc,body=S.GR.load(path)
            ids=[i for i,n in enumerate(doc['nodes']) if n.get('name','').startswith('Walk_ContinentalBridgeUnion_')]
            triangles=S.GR.triangles(doc,body,ids)
            centres=triangles[:,:,[0,2]].mean(axis=1)
            keys=np.round(centres,6)
            self.assertEqual(len(keys),len(np.unique(keys,axis=0)))
            self.assertEqual(len(triangles),w.bridge_report['visibleTriangles'])
            # The conservative solving grid is wider than the authored road.
            self.assertAlmostEqual(triangles[:,:,2].min(),17.)
            self.assertAlmostEqual(triangles[:,:,2].max(),23.)
            np.testing.assert_allclose(triangles[:,:,1],2.025,atol=1e-7)
            self.assertEqual({p['region'] for p in parts if p['node'].startswith('Walk_ContinentalBridgeUnion_')},{'west','east'})
            for i in ids:
                mesh=S.GR.triangles(doc,body,[i]);x=mesh[:,:,0]
                if doc['nodes'][i]['name'].endswith('_west'):self.assertLessEqual(x.max(),24)
                else:self.assertGreaterEqual(x.min(),24)
            thresholds=[i for i,n in enumerate(doc['nodes']) if n.get('name','').startswith('Walk__StreamThreshold_')]
            for i in thresholds:
                mesh=S.GR.triangles(doc,body,[i])
                np.testing.assert_allclose(mesh[:,:,1],B.surface_at(w,mesh[:,:,0],mesh[:,:,2]),atol=1e-6)
        np.testing.assert_array_equal(samples,w.height_at(np.arange(48.),20))

    def test_diagonal_capsule_has_smooth_exact_width_and_conserved_area(self):
        w=world();a=np.array([8.,8.]);b=np.array([40.,32.]);radius=3.
        w.roads=[{'width':radius,'points':[[*a[:1],0,a[1]],[b[0],0,b[1]]]},
                 {'width':radius,'points':[[b[0],80,b[1]],[a[0],-80,a[1]]]}]
        outline=B.RoadOutline(w)
        component={'slice':(slice(0,40),slice(0,48)),'cells':np.ones((40,48),bool),
                   'height':np.full((41,49),2.025),'outline':outline}
        mesh,owners=B.deck_mesh(w,component);triangles=mesh.positions[mesh.indices.reshape(-1,3)]
        area=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,1]*.5
        cap_area=B.CAP_ARC_STEPS*radius**2*np.sin(np.pi/B.CAP_ARC_STEPS)
        self.assertAlmostEqual(float(area.sum()),2*radius*np.linalg.norm(b-a)+cap_area,places=6)
        self.assertTrue((area>0).all())
        # A diagonal shoulder has fractional coordinates, not a staircase.
        p=mesh.positions[:,[0,2]]
        self.assertGreater(np.count_nonzero((np.abs(p[:,0]-np.round(p[:,0]))>.02)&
                                            (np.abs(p[:,1]-np.round(p[:,1]))>.02)),30)
        for owner in (0,1):
            x=triangles[owners==owner,:,0]
            self.assertTrue((x<=24+1e-9).all() if owner==0 else (x>=24-1e-9).all())

    def test_nonconvex_capsule_union_covers_every_road_point_once(self):
        w=world();w.roads=[{'width':3.,'points':[[6,0,7],[41,0,33]]},
                           {'width':3.,'points':[[7,0,30],[42,0,10]]}]
        outline=B.RoadOutline(w)
        component={'slice':(slice(0,40),slice(0,48)),'cells':np.ones((40,48),bool),
                   'height':np.full((41,49),2.025),'outline':outline}
        mesh,_=B.deck_mesh(w,component);triangles=mesh.positions[mesh.indices.reshape(-1,3)][:,:,[0,2]]
        points=np.random.default_rng(129).uniform([0,0],[48,40],(2500,2));coverage=np.zeros(len(points),int)
        for triangle in triangles:
            a,b,c=triangle
            edge1=b-a;edge2=c-a;delta=points-a
            determinant=edge1[0]*edge2[1]-edge1[1]*edge2[0]
            u=(delta[:,0]*edge2[1]-delta[:,1]*edge2[0])/determinant
            v=(edge1[0]*delta[:,1]-edge1[1]*delta[:,0])/determinant
            coverage+=(u>=0)&(v>=0)&(u+v<=1)
        self.assertLessEqual(int(coverage.max()),1,'Overlapping source ribbons survived the union')
        np.testing.assert_array_equal(coverage==1,outline.contains(points[:,0],points[:,1]))
        # Independently check actual authored capsule widths away from cap approximation.
        distance=np.full(len(points),np.inf)
        for road in w.roads:
            a,b=np.asarray(road['points'])[:,[0,2]];delta=b-a
            t=np.clip(np.sum((points-a)*delta,axis=1)/np.dot(delta,delta),0,1)
            distance=np.minimum(distance,np.linalg.norm(points-a-t[:,None]*delta,axis=1))
        self.assertTrue((coverage[distance<2.97]==1).all())
        self.assertTrue((coverage[distance>3.001]==0).all())

    def test_visible_timber_edges_stay_below_floor_and_out_of_bank_joins(self):
        w=world()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'bridges.glb';B.build_bridges(w,path,water_fields=water)
            doc,body=S.GR.load(path)
            timber=[i for i,n in enumerate(doc['nodes']) if n.get('name','').startswith('BridgeUnionTimberEdge_')]
            self.assertTrue(timber)
            triangles=S.GR.triangles(doc,body,timber)
            self.assertAlmostEqual(triangles[:,:,1].max(),2.025,places=6)
            self.assertAlmostEqual(triangles[:,:,1].min(),2.025-.32,places=6)
            self.assertTrue(np.isin(triangles[:,:,2],[17.,23.]).all())
            materials={m['name']:m for m in doc['materials']}
            self.assertIn('baseColorTexture',materials['bridge_timber']['pbrMetallicRoughness'])
            self.assertTrue(doc['images'][0].get('bufferView') is not None)
        # Grid-only cells outside the clipped shoulder cannot report an invisible elevated floor.
        self.assertAlmostEqual(float(B.surface_at(w,24,23.5)),-2.)

    def test_nearly_coincident_caps_export_stable_float32_faces_at_continent_scale(self):
        w=world();w.x0=1000.;w.z0=1300.;w.x1=1048.;w.z1=1340.
        w.owner_at=lambda x,z:np.where(np.asarray(x)<1024,0,1)+np.asarray(z,dtype=int)*0
        w.roads=[{'width':3.,'points':[[1006,0,1307],[1041,0,1333]]},
                 {'width':3.00000005,'points':[[1006.000003,0,1307.000004],[1041,0,1333]]}]
        gx,gz=np.meshgrid(np.arange(49),np.arange(41))
        component={'slice':(slice(0,40),slice(0,48)),'cells':np.ones((40,48),bool),
                   'height':80.+.44*gx+.44*gz,'outline':B.RoadOutline(w)}
        mesh,_=B.deck_mesh(w,component)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'floor.glb';builder=B.G.GltfBuilder()
            builder.add_material(B.G.Material('bridge_timber'))
            builder.add_mesh('floor',mesh,with_tangents=False);builder.add_node(B.G.Node('floor',mesh='floor'))
            builder.write_glb(str(path));doc,body=S.GR.load(path)
            triangles=S.GR.triangles(doc,body,[0])
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        self.assertTrue((normal[:,1]>0).all())
        self.assertLessEqual(float(np.max(np.hypot(normal[:,0],normal[:,2])/normal[:,1])),.65)
        self.assertLess(component['precisionCleanupArea'],.001)

    def test_thin_continent_edge_uses_encoded_xz_before_lifting_onto_floor(self):
        # Regression from the fifth export: a ~2.44 cm² shoulder face is large
        # enough to retain, but independent XYZ rounding makes its grade .659.
        w=world();w.x0=329.;w.z0=1428.
        gradient=.64/np.sqrt(2)
        component={'slice':(slice(0,1),slice(0,1)),'cells':np.ones((1,1),bool),
                   'height':np.array([[1.8-gradient,1.8],[1.8,1.8+gradient]])}
        xz=np.array([[329.,1429.],[330.,1429.],[329.001,1428.99949]])
        original=np.c_[xz[:,0],1.8+(xz-[329.,1429.])@np.array([gradient,gradient]),xz[:,1]]
        independent=original.astype(np.float32).astype(float)
        normal=np.cross(independent[1]-independent[0],independent[2]-independent[0])
        self.assertGreater(np.hypot(normal[0],normal[2])/normal[1],.65)
        self.assertGreater(normal[1]*.5,1e-4,'Regression must not qualify for tiny-face deletion')
        positions=B.encoded_floor_vertices(w,component,xz)
        mesh=B.M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(3,1)),
                      uvs=positions[:,[0,2]],indices=np.array([0,1,2]),material='bridge_timber')
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'floor.glb';builder=B.G.GltfBuilder()
            builder.add_material(B.G.Material('bridge_timber'))
            builder.add_mesh('floor',mesh,with_tangents=False);builder.add_node(B.G.Node('floor',mesh='floor'))
            builder.write_glb(str(path));doc,body=S.GR.load(path)
            triangles=S.GR.triangles(doc,body,[0])
        self.assertEqual(len(triangles),1,'The thin floor must remain present')
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[0]
        self.assertGreater(normal[1],0)
        self.assertLessEqual(np.hypot(normal[0],normal[2])/normal[1],.65)
        expected=1.8+(positions[:,[0,2]]-[329.,1429.])@np.array([gradient,gradient])
        np.testing.assert_allclose(positions[:,1],expected,atol=1e-7)

    def test_conservative_invisible_shoulder_cannot_create_a_bridge_beside_water(self):
        w=world();w.height_at=lambda x,z:np.where(np.asarray(z)>=23.5,-2.,2.)+np.asarray(x)*0
        def beside(x,z,*,height,plan):
            mask=np.asarray(z)>=23.5
            return {'mask':mask,'depth':np.where(mask,2.,0.),'surface':np.asarray(height)*0}
        field=B.common_surface(w,water_fields=beside)
        self.assertEqual(field['components'],[])
        self.assertFalse(field['mask'].any())

    def test_readback_outline_vertices_use_the_visible_floor_after_float32_rounding(self):
        w=world();w.x0=1000.;w.z0=1300.;w.x1=1048.;w.z1=1340.;w.connections=[]
        w.owner_at=lambda x,z:np.where(np.asarray(x)<1024,0,1)+np.asarray(z,dtype=int)*0
        w.height_at=lambda x,z:np.where((np.asarray(x)>=1018)&(np.asarray(x)<=1030),-20.,2.)+np.asarray(z)*0
        w.roads=[{'width':3.,'points':[[1004,0,1304],[1044,0,1336]]}]
        def river(x,z,*,height,plan):
            mask=(np.asarray(x)>=1018)&(np.asarray(x)<=1030)
            return {'mask':mask,'depth':np.where(mask,20.,0.),'surface':np.asarray(height)*0}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'bridges.glb';B.build_bridges(w,path,water_fields=river)
            doc,body=S.GR.load(path)
            ids=[i for i,n in enumerate(doc['nodes']) if n.get('name','').startswith('Walk_ContinentalBridgeUnion_')]
            vertices=S.GR.triangles(doc,body,ids).reshape(-1,3)
        np.testing.assert_allclose(B.surface_at(w,vertices[:,0],vertices[:,2]),vertices[:,1],atol=1e-5)

    def test_road_order_does_not_change_the_deck_and_a_whole_road_floating_is_no_gap(self):
        first=world();second=world();second.roads.reverse()
        for r in second.roads:
            for p in r['points']:p[1]*=-100
        a=B.common_surface(first,water_fields=water);b=B.common_surface(second,water_fields=water)
        np.testing.assert_array_equal(a['mask'],b['mask'])
        np.testing.assert_allclose(a['height'],b['height'],equal_nan=True)

    def test_loose_inventory_is_the_common_surface_wet_authority_with_stable_roads(self):
        w=world();inventory=B.loose_crossing_inventory(w,water_fields=water)
        field=B.common_surface(w,water_fields=water)
        self.assertEqual(inventory['looseWetCellIndices'],field['looseWetCellIndices'])
        self.assertEqual(len(inventory['components']),1)
        component=inventory['components'][0]
        self.assertEqual(component['looseWetCells'],inventory['looseWetCellIndices'])
        self.assertEqual(component['roadIds'],('back','out'))
        self.assertEqual(component['fullWidthWaterRoadIds'],('back','out'))
        self.assertEqual({item['roadId'] for item in component['fullWidthWaterCells']},{'back','out'})
        self.assertEqual(set().union(*(set(item['looseWetCells'])
                                     for item in component['fullWidthWaterCells'])),
                         set(inventory['looseWetCellIndices']))

    def test_prepared_coast_suppresses_legacy_floor_before_surface_construction(self):
        w=world();inventory=B.loose_crossing_inventory(w,water_fields=water)
        floor=np.array([[[18.,2.,17.],[18.,2.,23.],[30.,2.,17.]],
                        [[30.,2.,17.],[18.,2.,23.],[30.,2.,23.]]],np.float32).astype(float)
        w.claimed_coastal_records=(SimpleNamespace(
            claim_id='ordinary-out',encoded_floor_triangles=floor,
            loose_wet_cells=inventory['looseWetCellIndices'],road_ids=('out',),
            wet_extent_metres=(14.,26.),join_stations_metres=(14.,26.),
            surfaces=(SimpleNamespace(name='floor'),),stairs=(),supports=(),
            evidence={'fullWidthJoins':{'acceptanceAuthority':True,'clear':True,
                'maximumGapMetres':.1,'worstBankXZ':[18.,20.]}}),)
        w.claimed_coastal_inventory=C.build_selected_inventory(inventory,w.claimed_coastal_records)
        field=B.common_surface(w,water_fields=water)
        self.assertEqual([component['coastalRecordId'] for component in field['components']],
                         ['ordinary-out'])
        self.assertNotIn('height',field['components'][0])
        self.assertEqual(field['looseWetCellIndices'],inventory['looseWetCellIndices'])
        self.assertEqual(field['trimmedLandingCells'],0)

    def test_selected_coast_retains_unselected_legacy_wet_authority(self):
        w=world();w.height_at=lambda x,z:np.where(
            ((np.asarray(x)>=10)&(np.asarray(x)<=14))|((np.asarray(x)>=30)&(np.asarray(x)<=34)),
            -2.,2.)+np.asarray(z)*0
        def separated(x,z,*,height,plan):
            mask=((np.asarray(x)>=10)&(np.asarray(x)<=14))|((np.asarray(x)>=30)&(np.asarray(x)<=34))
            return {'mask':mask,'depth':np.where(mask,2.,0.),'surface':np.asarray(height)*0}
        inventory=B.loose_crossing_inventory(w,water_fields=separated)
        baseline=B.common_surface(w,water_fields=separated)
        baseline_y=float(B.surface_at(w,32.,20.,field=baseline))
        self.assertEqual(len(inventory['components']),2)
        selected=min(inventory['components'],key=lambda value:value['bounds'][2])
        floor=np.array([[[8.,2.,17.],[8.,2.,23.],[16.,2.,17.]],
                        [[16.,2.,17.],[8.,2.,23.],[16.,2.,23.]]],np.float32).astype(float)
        w.claimed_coastal_records=(SimpleNamespace(
            claim_id='selected-west',encoded_floor_triangles=floor,
            loose_wet_cells=selected['looseWetCells'],road_ids=('out',),
            wet_extent_metres=(10.,14.),join_stations_metres=(8.,16.),
            surfaces=(SimpleNamespace(name='floor'),),stairs=(),supports=(),
            evidence={'fullWidthJoins':{'acceptanceAuthority':True,'clear':True,
                'maximumGapMetres':.1,'worstBankXZ':[8.,20.]}}),)
        w.claimed_coastal_inventory=C.build_selected_inventory(inventory,w.claimed_coastal_records)
        field=B.common_surface(w,water_fields=separated)
        prepared=[value for value in field['components'] if value.get('coastalRecordId')]
        fallback=[value for value in field['components'] if not value.get('sites') and
                  not value.get('coastalRecordId')]
        self.assertEqual([value['coastalRecordId'] for value in prepared],['selected-west'])
        self.assertTrue(fallback)
        self.assertTrue(np.asarray(field['mask']).flat[list(field['legacyLooseWetCellIndices'])].all())
        self.assertEqual(float(B.surface_at(w,32.,20.,field=field)),baseline_y)
        self.assertEqual(field['preparedLooseWetCells']+field['legacyLooseWetCells'],
                         field['looseWetCells'])

    def test_prepared_query_includes_real_encoded_vertex_and_edge_but_not_exterior(self):
        face=np.array([[[529.72802734375,2.1699771881103516,1073.4534912109375],
                        [529.3009033203125,2.1699771881103516,1073.509765625],
                        [528.9029541015625,2.1699771881103516,1073.6746826171875]]],float)
        positions=face.reshape(-1,3)
        mesh=B.M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(3,1)),
                      uvs=positions[:,[0,2]],indices=np.arange(3),material='bridge_stone')
        component={'_preparedMeshCache':(mesh,np.array([0]))}
        vertex=face[0,1,[0,2]];edge=face[0,:2][:,[0,2]].mean(axis=0)
        centre=face[0,:][:,[0,2]].mean(axis=0)
        outward=vertex-centre;outward/=np.linalg.norm(outward)
        exterior=vertex+outward*1e-7
        covered,height=B._prepared_surface_at(world(),component,
            np.array([vertex[0],edge[0],exterior[0]]),
            np.array([vertex[1],edge[1],exterior[1]]))
        np.testing.assert_array_equal(covered,[True,True,False])
        np.testing.assert_allclose(height[:2],face[0,0,1],atol=0.,rtol=0.)
        self.assertEqual(height[2],-np.inf)

    def export_roof_fixture(self,*,top=2.,footprint=None):
        floor=np.array([[[0,top,0],[0,top,1],[1,top,0]],
                        [[1,top,0],[0,top,1],[1,top,1]]],np.float32).astype(float)
        base=floor.copy();base[:,:,1]=0.
        sides=[]
        for a,b in (((0,0),(0,1)),((0,1),(1,1)),((1,1),(1,0)),((1,0),(0,0))):
            sides.extend(([[a[0],0,a[1]],[a[0],top,a[1]],[b[0],0,b[1]]],
                          [[a[0],top,a[1]],[b[0],top,b[1]],[b[0],0,b[1]]]))
        triangles=np.concatenate([floor,base,np.asarray(sides,float)])
        if footprint is None:footprint=np.array([[0,0],[0,1],[1,1],[1,0]],float)
        support=ExportSupport('covered',np.asarray(footprint,float),top,triangles)
        claim=ExportClaim('portable',floor,(support,))
        return SimpleNamespace(claimed_coastal_records=(claim,)),floor,triangles

    def test_export_copy_omits_only_a_fully_covered_support_roof(self):
        world,floor,triangles=self.export_roof_fixture();exported,report=BC.bridge_export_world(world)
        self.assertIsNot(exported,world);self.assertEqual(report[0]['roofTrianglesOmitted'],2)
        np.testing.assert_array_equal(world.claimed_coastal_records[0].supports[0].triangles,triangles)
        actual=exported.claimed_coastal_records[0].supports[0].encoded_triangles
        self.assertEqual(len(actual),10);self.assertFalse(np.any(np.all(actual[:,:,1]==2.,axis=1)))
        np.testing.assert_array_equal(exported.claimed_coastal_records[0].encoded_floor_triangles,floor)

    def test_export_support_roof_fails_closed_on_height_mismatch_or_exterior(self):
        world,floor,_=self.export_roof_fixture(top=3.)
        claim=replace(world.claimed_coastal_records[0],encoded_floor_triangles=floor.copy())
        claim.encoded_floor_triangles[:,:,1]=2.
        world.claimed_coastal_records=(claim,)
        with self.assertRaisesRegex(ValueError,'no identical-height prepared floor'):
            BC.bridge_export_world(world)
        world,_,_=self.export_roof_fixture(footprint=[[0,0],[0,1],[1.1,1],[1.1,0]])
        with self.assertRaisesRegex(ValueError,'not completely covered'):
            BC.bridge_export_world(world)

    def test_bridge_scene_returns_derived_export_state_without_replacing_logical_claim(self):
        world,_,triangles=self.export_roof_fixture()
        logical_claim=world.claimed_coastal_records[0]
        derived_report={'components':1,'supports':[{'name':'covered'}]}
        derived_triangles=np.array([[[0.,2.,0.],[0.,2.,1.],[1.,2.,0.]]])
        derived_field={'components':[{'coastalRecordId':'portable'}]}
        def build(export_world,path):
            self.assertIsNot(export_world,world)
            self.assertEqual(len(export_world.claimed_coastal_records[0].supports[0].encoded_triangles),10)
            export_world.bridge_report=derived_report
            export_world.bridge_triangles=derived_triangles
            export_world.bridge_field=derived_field
            return [{'node':'prepared'}]
        with patch.object(B,'build_bridges',side_effect=build):
            self.assertEqual(BC.bridge_scene(world,Path('unused.glb')),[{'node':'prepared'}])
        self.assertIs(world.claimed_coastal_records[0],logical_claim)
        np.testing.assert_array_equal(logical_claim.supports[0].encoded_triangles,triangles)
        self.assertIs(world.bridge_report,derived_report)
        self.assertIs(world.bridge_triangles,derived_triangles)
        self.assertIs(world.bridge_field,derived_field)

    def test_crossing_roads_share_one_junction_with_bounded_actual_triangle_slopes(self):
        w=world();w.roads.append({'id':'north-south','width':3.,'points':[[24,0,4],[24,0,36]]})
        # A cross-channel has real dry banks on all approaches.
        w.height_at=lambda x,z:np.where((np.abs(np.asarray(x)-24)<5)&(np.abs(np.asarray(z)-20)<5),-2.,2.)+np.asarray(z)*.02
        def wet(x,z,*,height,plan):
            mask=(np.abs(np.asarray(x)-24)<5)&(np.abs(np.asarray(z)-20)<5)
            return {'mask':mask,'depth':np.where(mask,2.,0.),'surface':np.asarray(height)*0}
        field=B.common_surface(w,water_fields=wet)
        self.assertEqual(len(field['components']),1)
        mesh,_=B.deck_mesh(w,field['components'][0]);t=mesh.positions[mesh.indices.reshape(-1,3)]
        normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])
        self.assertTrue((normal[:,1]>0).all())
        self.assertLessEqual(float(np.max(np.hypot(normal[:,0],normal[:,2])/normal[:,1])),.650001)
        self.assertLessEqual(field['maximumBankError'],.12)

    def test_supports_extend_down_to_the_actual_bed(self):
        w=world()
        with tempfile.TemporaryDirectory() as temporary:
            parts=B.build_bridges(w,Path(temporary)/'bridges.glb',water_fields=water)
            piers=[p for p in parts if p['node'].startswith('BridgeUnionPier_')]
            self.assertTrue(piers)
            for p in piers:
                low,high=p['bounds'];x,z=((low+high)*.5)[[0,2]]
                self.assertAlmostEqual(low[1],float(w.height_at(x,z))-.06,places=6)
                self.assertAlmostEqual(high[1],float(B.surface_at(w,x,z))-.12,places=6)

    def test_an_unfittable_bank_is_reported_not_grown_and_the_world_is_unchanged(self):
        # A cliff beside the channel: since the roads pass (R1) a deck is its span plus landings of at most
        # deck_landing_metres; it is never grown up a bank to fit it, and the misfit is reported.
        w=world();w.height_at=lambda x,z:np.where(np.asarray(x)>24,80.,-2.)+np.asarray(z)*0
        w.roads=[{'id':'out','width':3.,'points':[[4,-2,20],[44,-2,20]]}]
        before=w.height_at(np.arange(48.),20).copy()
        field=B.common_surface(w,water_fields=water)
        self.assertGreater(field['maximumBankError'],.12)
        self.assertLessEqual(int(field['mask'][:,31:].any(axis=0).sum()),6)   # at most the six-metre landing beyond the water
        np.testing.assert_array_equal(before,w.height_at(np.arange(48.),20))

    def test_a_dry_gully_or_a_floating_road_profile_builds_no_deck(self):
        # The floating-run span rule is retired: roads are graded into the ground, and only water carries a deck.
        w=world();w.height_at=lambda x,z:np.where((np.asarray(x)>=18)&(np.asarray(x)<=30),.5,2.)+np.asarray(z)*0
        w.roads=[{'id':'out','width':3.,'points':[[4,2.2,20],[44,2.2,20]]}]
        dry=lambda x,z,*,height,plan:{'mask':np.zeros(np.shape(height),bool),'depth':np.zeros(np.shape(height)),'surface':np.zeros(np.shape(height))}
        self.assertFalse(B.common_surface(w,water_fields=dry)['mask'].any())


    def test_precision_remnants_are_the_faces_too_small_or_too_thin_to_carry_a_grade(self):
        sliver=np.array([[600.,67.,556.],[601.,67.6,556.],[600.5,67.3,556.00024]])   # a metre long, a quarter of a millimetre wide
        speck=np.array([[10.,1.,10.],[10.008,1.,10.],[10.,1.,10.008]])               # 32 square millimetres
        narrow=np.array([[20.,1.,20.],[21.,1.6,20.],[20.5,1.3,20.02]])                # a metre long, two centimetres wide: a real face
        square=np.array([[30.,1.,30.],[30.05,1.,30.],[30.,1.,30.05]])                  # five centimetres square: a real face
        faces=np.stack([sliver,speck,narrow,square]);areas=np.array([abs(B._area_xz(f)) for f in faces])
        self.assertEqual(B.precision_remnants(faces,areas).tolist(),[True,True,False,False])


if __name__=='__main__':unittest.main()
