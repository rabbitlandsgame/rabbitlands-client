"""Grey Moors consolidation: exact span retirement, pinned semantics, real floor identities."""
from pathlib import Path
import copy,inspect,sys,tempfile,types,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content as C
import grey_crossings as X
import build_continent as B
import audit_continent as AU
from bridge_export import G,M

REGION='grey_moors'
BOARDWALKS=['gate','centre','bog','west','north','east','south','coast']


def library_placements():
    names=[f'Landmark_boardwalk_{name}' for name in BOARDWALKS]+['Landmark_bridge_black_drain','Landmark_bridge_moor_gate','Secret_moor_boardwalk_cache','Landmark_Croft_1']
    return [{'node':name,'kind':'prop' if name.startswith('Secret_') else 'landmark'} for name in names]


def world_stub(height=5.,owner=None):
    ids=['whitehorn_range',REGION,'amberwood']
    index=ids.index(REGION)
    return types.SimpleNamespace(ids=ids,regions={REGION:{'center':[220.,420.]}},
        owner_at=lambda x,z:index if owner is None else owner(x,z),height_at=lambda x,z:height if not callable(height) else height(x,z))


def scene(path,boxes):
    builder=G.GltfBuilder('grey crossing fixture');builder.add_material(G.Material('timber'))
    roots={}
    for name,size,center in boxes:
        builder.add_mesh(name,M.box(size,center=center,material='timber'),with_tangents=False)
        roots[name]=builder.add_node(G.Node(name,mesh=name))
    builder.write_glb(str(path));doc,body=X.S.GR.load(path)
    return doc,body,roots


class RetirementTests(unittest.TestCase):
    def test_exactly_three_grey_spans_are_retired_before_grouping(self):
        placements=library_placements()
        kept=[p['node'] for p in C.retained_source_placements(REGION,placements)]
        self.assertEqual(kept,['Landmark_boardwalk_bog','Landmark_boardwalk_west','Landmark_boardwalk_north','Landmark_boardwalk_east',
            'Landmark_boardwalk_coast','Landmark_bridge_black_drain','Landmark_bridge_moor_gate','Secret_moor_boardwalk_cache','Landmark_Croft_1'])
        self.assertEqual(len(placements),12,'The immutable library record remains available for provenance')
        self.assertEqual(set(C.RETIRED_GREY_SPANS),{'Landmark_boardwalk_gate','Landmark_boardwalk_centre','Landmark_boardwalk_south'})

    def test_other_regions_keep_identically_named_roots(self):
        placements=library_placements()
        self.assertEqual(C.retained_source_placements('westhaven',placements),placements)
        self.assertEqual(C.retained_source_placements('sunmane_steppe',placements),placements)


class SemanticPointTests(unittest.TestCase):
    def content(self,extra=()):
        mapping={(REGION,'Secret_moor_boardwalk_cache'):np.zeros(3),(REGION,'Landmark_boardwalk_west'):np.zeros(3)}
        for node in extra:mapping[(REGION,node)]=np.zeros(3)
        return types.SimpleNamespace(mapping=mapping,authored_server_points={('amberwood',(221,320)):np.array([1.,2.,3.])})

    def test_four_targets_are_pinned_exactly_with_terrain_height_and_other_regions_untouched(self):
        world=world_stub(height=lambda x,z:x*.01+z*.02);content=self.content()
        report=X.prepare_grey_crossings(world,content)
        self.assertEqual(report['retiredSpans'],list(C.RETIRED_GREY_SPANS))
        for tile,(x,z) in X.AUTHORED_POINTS.items():
            point=content.authored_server_points[(REGION,tile)]
            self.assertEqual(point.shape,(3,));self.assertEqual((point[0],point[2]),(x,z))
            self.assertAlmostEqual(point[1],x*.01+z*.02)
        np.testing.assert_array_equal(content.authored_server_points[('amberwood',(221,320))],[1.,2.,3.])
        self.assertEqual(set(report['authoredPoints']),{str(list(tile)) for tile in X.AUTHORED_POINTS})
        # Heights follow the final field; XZ never moves.
        world.height_at=lambda x,z:9.25
        X.refresh_grey_crossing_heights(world,content)
        for tile,(x,z) in X.AUTHORED_POINTS.items():
            np.testing.assert_array_equal(content.authored_server_points[(REGION,tile)],[x,9.25,z])
            self.assertEqual(world.grey_crossings['authoredPoints'][str(list(tile))],[x,9.25,z])

    def test_pinned_targets_match_the_handoff_and_stay_within_the_old_span_neighbourhood(self):
        expected={(145,178):(237.635264,373.459628),(152,100):(236.540463,432.749464),
                  (230,86):(314.540463,446.749464),(221,88):(305.540463,444.749464)}
        self.assertEqual(X.AUTHORED_POINTS,expected)

    def test_a_still_placed_retired_span_or_missing_cache_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'still placed: Landmark_boardwalk_south'):
            X.prepare_grey_crossings(world_stub(),self.content(extra=['Landmark_boardwalk_south']))
        content=self.content();del content.mapping[(REGION,'Secret_moor_boardwalk_cache')]
        with self.assertRaisesRegex(ValueError,'must remain a placed discovery'):
            X.prepare_grey_crossings(world_stub(),content)
        with self.assertRaisesRegex(ValueError,'outside its territory'):
            X.prepare_grey_crossings(world_stub(owner=lambda x,z:0 if x>300 else 1),self.content())

    def test_other_worlds_without_grey_moors_are_ignored(self):
        world=types.SimpleNamespace(ids=['a','b']);content=types.SimpleNamespace(mapping={})
        self.assertEqual(X.prepare_grey_crossings(world,content),{})
        self.assertFalse(hasattr(content,'authored_server_points'))


class LandmarkRemapTests(unittest.TestCase):
    def fixture(self,folder,*,floors=None,centre_center=(50.,0.,12.)):
        library=folder/'library.glb'
        doc,body,_=scene(library,[('Landmark_boardwalk_gate',(20.,1.,4.),(10.,0.,10.)),
                                  ('Landmark_boardwalk_centre',(4.,1.,20.),centre_center),
                                  ('Landmark_boardwalk_south',(20.,1.,4.),(10.,0.,60.)),
                                  ('Landmark_boardwalk_west',(20.,1.,4.),(-80.,0.,10.))])
        bridge=folder/'bridges.glb'
        floors=floors if floors is not None else [
            ('Walk_ContinentalBridgeUnion_002_grey_moors',(10.,1.,30.),(110.,3.,210.)),
            ('BridgeUnionPier_002_1_1',(.8,2.,.8),(110.,1.,200.)),
            ('Walk_ContinentalBridgeUnion_004_grey_moors',(40.,1.,10.),(110.,6.,260.)),
            ('Walk_ContinentalBridgeUnion_009_grey_moors',(10.,1.,10.),(500.,0.,500.)),
            ('Walk_ContinentalBridgeUnion_004_amberwood',(40.,1.,10.),(110.,20.,260.))]
        bridge_doc,bridge_body,roots=scene(bridge,floors)
        bridges=[{'node':name,'roots':[roots[name]]} for name,_,_ in floors]
        content=types.SimpleNamespace(documents={REGION:(doc,body)},mapped_xz=lambda region,p:np.asarray(p,float)+[100.,200.])
        manifest={'landmarks':[
            {'id':'grey-boardwalk-0','node':'Landmark_boardwalk_gate','type':'bridge','name':'Grey Moor Crossing','position':[1.,2.,3.]},
            {'id':'grey-boardwalk-1','node':'Landmark_boardwalk_centre','type':'bridge','name':'Grey Moor Crossing','position':[1.,2.,3.]},
            {'id':'grey-boardwalk-3','node':'Landmark_boardwalk_west','type':'bridge','name':'Grey Moor Crossing','position':[-7.,2.,3.]},
            {'id':'grey-boardwalk-6','node':'Landmark_boardwalk_south','type':'bridge','name':'Grey Moor Crossing','position':[1.,2.,3.]}]}
        return world_stub(),content,manifest,bridge_doc,bridge_body,bridges

    def test_identities_move_onto_the_covering_floor_with_its_node_name_and_height(self):
        with tempfile.TemporaryDirectory() as d:
            world,content,manifest,doc,body,bridges=self.fixture(Path(d))
            report=X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)
            by_id={entry['id']:entry for entry in manifest['landmarks']}
            gate=by_id['grey-boardwalk-0'];south=by_id['grey-boardwalk-6'];centre=by_id['grey-boardwalk-1']
            self.assertEqual(gate['node'],'Walk_ContinentalBridgeUnion_002_grey_moors')
            np.testing.assert_allclose(gate['position'],[110.-220.,3.5,210.-420.])
            self.assertEqual(gate['association']['coveredSamples'],55);self.assertEqual(gate['association']['oldFloorSamples'],105)
            self.assertEqual(south['node'],'Walk_ContinentalBridgeUnion_004_grey_moors')
            np.testing.assert_allclose(south['position'],[110.-220.,6.5,260.-420.])
            self.assertEqual(south['association']['coveredSamples'],105)
            # No floor covers the centre span; the nearest actual floor vertex within 64 m carries it.
            self.assertEqual(centre['node'],'Walk_ContinentalBridgeUnion_002_grey_moors')
            np.testing.assert_allclose(centre['position'],[115.-220.,3.5,225.-420.])
            self.assertAlmostEqual(centre['association']['distanceMetres'],np.hypot(35.,13.))
            self.assertEqual(by_id['grey-boardwalk-3'],{'id':'grey-boardwalk-3','node':'Landmark_boardwalk_west','type':'bridge','name':'Grey Moor Crossing','position':[-7.,2.,3.]})
            self.assertEqual([row['replacedSpan'] for row in report],list(X.RETAINED_IDENTITIES.values()))
            self.assertEqual({entry['replacedSpan'] for entry in (gate,centre,south)},set(C.RETIRED_GREY_SPANS))
            self.assertFalse(any(entry['node'] in C.RETIRED_GREY_SPANS for entry in manifest['landmarks']))
            self.assertEqual(X.remap_grey_crossing_landmarks(world,content,'amberwood',{'landmarks':[]},doc,body,bridges),[])

    def test_association_is_deterministic_and_never_uses_another_territory_or_pier(self):
        with tempfile.TemporaryDirectory() as d:
            world,content,manifest,doc,body,bridges=self.fixture(Path(d))
            first=X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)
            world,content,manifest,doc,body,bridges=self.fixture(Path(d))
            second=X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,list(reversed(bridges)))
            self.assertEqual(first,second)
            self.assertTrue(all(row['node'].endswith('_grey_moors') and row['node'].startswith('Walk_') for row in first))

    def test_a_span_without_any_nearby_floor_fails_instead_of_inventing_a_position(self):
        with tempfile.TemporaryDirectory() as d:
            world,content,manifest,doc,body,bridges=self.fixture(Path(d),centre_center=(80.,0.,12.))
            with self.assertRaisesRegex(ValueError,'within 64 m of the retired span'):
                X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)
        with tempfile.TemporaryDirectory() as d:
            world,content,manifest,doc,body,bridges=self.fixture(Path(d),floors=[('BridgeUnionPier_002_1_1',(.8,2.,.8),(110.,1.,200.))])
            with self.assertRaisesRegex(ValueError,'no continental crossing floor'):
                X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)

    def test_unexpected_records_or_dangling_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            world,content,manifest,doc,body,bridges=self.fixture(Path(d))
            manifest['landmarks'].append({'id':'grey-extra','node':'Landmark_boardwalk_gate','position':[0,0,0]})
            with self.assertRaisesRegex(ValueError,'still referenced by landmarks: grey-extra'):
                X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)
            world,content,manifest,doc,body,bridges=self.fixture(Path(d))
            manifest['landmarks'][0]['node']='Renamed'
            with self.assertRaisesRegex(ValueError,'grey-boardwalk-0: expected the retained landmark record'):
                X.remap_grey_crossing_landmarks(world,content,REGION,manifest,doc,body,bridges)


class SavedLandmarkAuthorityTests(unittest.TestCase):
    def fixture(self):
        node='Walk_ContinentalBridgeUnion_001_grey_moors'
        landmarks=[{'id':identity,'node':node,'position':[26.,25.5,-12.],
                    'replacedSpan':retired}
                   for identity,retired in X.RETAINED_IDENTITIES.items()]
        snapshot=types.SimpleNamespace(document={'gameplay':{'landmarks':copy.deepcopy(landmarks)}})
        world=world_stub();world.authoring_snapshots={REGION:snapshot}
        content=types.SimpleNamespace(objects=[{'region':REGION,'node':node+'_WorldPlacement',
            'source':{'authoredCrossing':{'id':'moor_tributary@62','walkNode':node}}}])
        manifest={'landmarks':copy.deepcopy(landmarks)}
        return world,content,manifest

    def test_saved_landmarks_keep_exact_nodes_and_positions_without_generated_floor(self):
        world,content,manifest=self.fixture();before=copy.deepcopy(manifest)
        report=B.saved_grey_crossing_landmarks(world,content,REGION,manifest)
        self.assertEqual(manifest,before)
        self.assertEqual(len(report),3)
        self.assertEqual({row['crossingId'] for row in report},{'moor_tributary@62'})
        self.assertEqual({row['authority'] for row in report},{'saved-scene'})
        self.assertTrue(all(row['globalPosition']==[246.,25.5,408.] for row in report))

    def test_deletion_is_authoritative_and_dangling_reference_fails(self):
        world,content,manifest=self.fixture()
        content.objects=[]
        with self.assertRaisesRegex(ValueError,'no active authored crossing Walk root'):
            B.saved_grey_crossing_landmarks(world,content,REGION,manifest)
        world.authoring_snapshots[REGION].document['gameplay']['landmarks']=[]
        manifest['landmarks']=[]
        self.assertEqual(B.saved_grey_crossing_landmarks(world,content,REGION,manifest),[])
        manifest['landmarks']=[{'id':'other','node':'Landmark_boardwalk_gate'}]
        with self.assertRaisesRegex(ValueError,'still referenced by saved landmarks'):
            B.saved_grey_crossing_landmarks(world,content,REGION,manifest)


class CertificateTests(unittest.TestCase):
    def test_helper_is_a_shaping_and_geometry_export_source(self):
        self.assertIn('grey_crossings.py',B.SHAPING_SOURCES)
        self.assertIn('grey_crossings.py',B.EXPORT_SOURCES)
        self.assertIn('EXPORT_SOURCES',inspect.getsource(B.export_geometry))
        self.assertIn('EXPORT_SOURCES',inspect.getsource(B.verify_geometry_export))
        self.assertIn('remap_grey_crossing_landmarks(world,content,region,manifest,bridge_doc,bridge_body,bridges)',inspect.getsource(B.export_geometry))
        self.assertIn('saved_grey_crossing_landmarks(world,content,region,manifest)',inspect.getsource(B.export_geometry))
        self.assertIn('prepare_grey_crossings(world,content)',inspect.getsource(B.prepare))
        self.assertIn('refresh_grey_crossing_heights(world,content)',inspect.getsource(B.prepare))
        self.assertIn('SHAPING_SOURCES',inspect.getsource(AU.audit_shaping))


if __name__=='__main__':
    unittest.main()
