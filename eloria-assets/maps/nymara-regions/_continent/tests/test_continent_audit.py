"""Regression cases must fail when emitted partition geometry becomes inconsistent."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import audit_continent as A
from amberwood import mesh as M, gltf as G

POLYGONS = {'west':[[0,0],[2,0],[2,4],[0,4]], 'east':[[2,0],[4,0],[4,4],[2,4]]}


def scene(path, *, color=.4, reverse=False, missing=False, regions=('west','east'),translation=(0,0,0)):
    builder = G.GltfBuilder('independent audit fixture')
    builder.add_material(G.Material('continental_ground',roughness=.95))
    for region,x0 in (('west',0),('east',2)):
        if region not in regions: continue
        x,z = np.meshgrid([x0,x0+2],[0,2,4])
        vertices = np.c_[x.ravel(),(x*.1+z*.2).ravel(),z.ravel()]
        indices = np.array([[0,2,1],[1,2,3],[2,4,3],[3,4,5]])
        if reverse: indices = indices[:,::-1]
        if missing and region == 'east': indices = indices[:-1]
        normals = np.tile([-.1,1.,-.2],(6,1));normals/=np.linalg.norm(normals,axis=1,keepdims=True)
        mesh = M.Mesh(positions=vertices-np.asarray(translation),normals=normals,uvs=vertices[:,[0,2]]*.17,
                      colors=np.tile([.3,color,.2,1],(6,1)),indices=indices.ravel(),material='continental_ground')
        name = f'Terrain_{region}_00_00'
        builder.add_mesh(name,mesh,with_tangents=False)
        builder.add_node(G.Node(name,mesh=name))
    builder.write_glb(str(path))


class EmittedPartitionTests(unittest.TestCase):
    def reference(self, folder):
        source = folder/'source.glb';scene(source)
        s = A.Surface([0,0,4,4],POLYGONS,client=folder)
        s.translations = {'west':np.zeros(3),'east':np.zeros(3)}
        s.read(source,s.source_counts,source=True)
        s.complete(s.source_counts,'source')
        return s

    def test_exact_actual_geometry_and_attributes_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'target.glb';scene(target)
            counts=np.zeros_like(s.source_counts);s.read(target,counts);s.complete(counts,'target')
            self.assertEqual(int(counts.sum()),8)

    def test_changed_biome_vertex_colors_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'changed.glb';scene(target,color=.41)
            with self.assertRaisesRegex(A.AuditError,'color changed'):
                s.read(target,np.zeros_like(s.source_counts))

    def test_missing_and_duplicated_actual_triangles_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'missing.glb';scene(target,missing=True)
            counts=np.zeros_like(s.source_counts);s.read(target,counts)
            with self.assertRaisesRegex(A.AuditError,'1 missing'):
                s.complete(counts,'target')
            counts=s.source_counts*2
            with self.assertRaisesRegex(A.AuditError,'8 duplicated'):
                s.complete(counts,'target')

    def test_reversed_visible_terrain_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'backwards.glb';scene(target,reverse=True)
            with self.assertRaisesRegex(A.AuditError,'winding is reversed'):
                s.read(target,np.zeros_like(s.source_counts))

    def test_ownership_gap_and_overlap_cannot_pass_as_valid_counts(self):
        for east in ([[3,0],[4,0],[4,4],[3,4]], [[0,0],[4,0],[4,4],[0,4]]):
            with self.assertRaisesRegex(A.AuditError,'Ownership has'):
                A.ownership_raster({**POLYGONS,'east':east},[0,0,4,4],cell=1)

    def test_loading_bounds_must_cover_actual_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'west.glb';scene(target,regions=('west',))
            with self.assertRaisesRegex(A.AuditError,'outside declared loading bounds'):
                s.read(target,np.zeros_like(s.source_counts),region='west',bounds={'min':[0,0,0],'max':[1,2,4]})

    def test_an_undeclared_or_fictitious_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);s=self.reference(folder)
            target=folder/'target.glb';scene(target)
            with self.assertRaisesRegex(A.AuditError,'external resources differ'):
                s.read(target,np.zeros_like(s.source_counts),manifest={'externalResources':{'missing.png':'0'*64}})

    def test_reciprocal_lane_coordinate_drift_is_rejected(self):
        translations={'west':np.zeros(3),'east':np.array([4,0,0])}
        a={'region':'west','frame':{'id':'road','anchor':[2,0,2],'outward':[1,0]},
           'lanes':[{'tile':[8,y],'arrival':[7,y]} for y in range(7)]}
        b={'region':'east','frame':{'id':'road','anchor':[-2,0,2],'outward':[-1,0]},
           'lanes':[{'tile':[3,y],'arrival':[4,y]} for y in range(7)]}
        manifests={end['region']:{'coordinateTransform':{'serverOrigin':[6,6],'serverCells':[16,16]},
            'streamingBorders':[end['frame']]} for end in (a,b)}
        publication={'connections':[{'id':'road','type':'walk','ends':[a,b]}]}
        self.assertEqual(A.audit_frames(publication,manifests,translations)['checkedLaneDirections'],14)
        # The ground a walker arriving the other way lands on is the tile behind the
        # crossing, beside it. The two sides used to be checked lane against lane, which a
        # border crossed along its length cannot satisfy: a step in the boundary leaves one
        # more tile outside it than inside.
        b['lanes'][0]['arrival'][0]+=2
        with self.assertRaisesRegex(A.AuditError,'not beside each other'):
            A.audit_frames(publication,manifests,translations)
        b['lanes'][0]['arrival'][0]-=2
        # A crossing hands the walker over at the cell they stand on, so a departure that
        # names no cell of the other map is no crossing.
        b['lanes'][0]['tile'][0]-=12
        b['lanes'][0]['arrival'][0]-=12
        with self.assertRaisesRegex(A.AuditError,'global actor coordinates'):
            A.audit_frames(publication,manifests,translations)


class ProvisionalExportTests(unittest.TestCase):
    def fixture(self,folder):
        client=folder/'client';base=client/'eloria-assets/maps/nymara-regions'
        continent=base/'_continent';generated=continent/'generated';generated.mkdir(parents=True)
        def write(path,data):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data),encoding='utf-8')
        digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        plan={'bounds':[0,0,4,4],'regions':[{'id':'west','center':[1,2]},{'id':'east','center':[3,2]}]}
        write(continent/'diagonal-plan.json',plan);plan_sha=digest(continent/'diagonal-plan.json')
        sources={}
        for name in A.SHAPING_SOURCES:
            path=continent/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(f'# fixture {name}\n')
            sources[path.resolve().relative_to(client.resolve()).as_posix()]=digest(path)
        builder=continent/'build_continent.py'
        builder.write_text('def prepare(library, output):\n    return library, output\n\ndef ferry_landing(world, region, toward):\n    return toward\n')
        profile=continent/'legacy-server-profile/config/eloria/maps.txt'
        profile.parent.mkdir(parents=True);profile.write_text('# fixture entrances\n')
        write(generated/'composition.json',{'planSha256':plan_sha,'sources':sources,
              'compositionAlgorithmSha256':A.composition_algorithm_sha(builder),'entranceProfileSha256':digest(profile),
              'geometryDependencies':A.geometry_dependencies()})
        scene(generated/'shared-terrain.glb');scene(generated/'continent.glb')
        master_sha=digest(generated/'continent.glb')
        write(generated/'master-scene.json',{'sha256':master_sha,'regions':['west','east']})
        exports={'masterPath':str(generated/'continent.glb'),'masterSha256':master_sha,'regions':{},
                 'compositionSha256':digest(generated/'composition.json'),'geometryDependencies':A.geometry_dependencies()}
        exports['geometrySources']={}
        for name in A.EXPORT_SOURCES:
            path=continent/name
            if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(f'# fixture {name}\n')
            exports['geometrySources'][name]=digest(path)
        for region,x in (('west',1),('east',3)):
            package=base/region;chunk=package/'chunks/00_00';chunk.mkdir(parents=True)
            translation=[x,0,2];bounds={'min':[-1,0,-2],'max':[1,1.2,2]}
            frame={'metresPerTile':1,'serverOrigin':[2,4],'serverCells':[6,6],'origin':[0,0,0],
                   'invertServerY':True,'addressableWorldBounds':{'min':[-2,-2],'max':[4,4]}}
            m={'asset':{'id':region,'glb':'world.glb'},'coordinateTransform':frame,'externalResources':{},
               'continentGeography':{'geometryMode':'continent-chunks-v1','translation':translation,'ownershipPolygon':POLYGONS[region]},
               'singleContinentSource':{'masterSha256':master_sha,'planSha256':plan_sha},'bounds':bounds}
            scene(package/'world.glb',regions=(region,),translation=translation)
            scene(chunk/'world.glb',regions=(region,),translation=translation)
            child=copy.deepcopy(m);child['asset']['id']=region+'__chunk_00_00';write(chunk/'world.json',child)
            m['streamingChunks']={'chunks':[{'id':'00_00','manifest':'chunks/00_00/world.json','bounds':bounds,
                                            'glbBytes':(chunk/'world.glb').stat().st_size}]}
            write(package/'world.json',m)
            exports['regions'][region]={'world':str(package/'world.json'),'chunks':1}
        write(generated/'export.json',exports)
        return client,generated,base

    def test_geometry_only_proves_actual_unpublished_export_despite_stale_canonical_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);client,generated,base=self.fixture(root)
            canonical=base/'continent-geography.json'
            canonical.write_text(json.dumps({'geometryMode':'legacy','regions':{'retired':{}}}))
            result=A.run(client,generated,root/'report.json',geometry_only=True)
            self.assertTrue(result['passed'],result['errors']);self.assertFalse(result['complete'])
            self.assertFalse(result['publicationVerified'])
            self.assertEqual(result['sourceTerrainTriangles'],8)
            self.assertEqual(sum(r['chunks'] for r in result['regions'].values()),2)
            self.assertNotIn(str(canonical.resolve()),result['inputs'])
            self.assertIn('assemblies.py',result['shapingFreshness']['shapingModules'])
            full=A.run(client,generated,root/'full.json')
            self.assertFalse(full['passed'])
            self.assertTrue(any('canonical continent-chunks-v1' in error for error in full['errors']))

    def test_geometry_only_still_rejects_a_missing_actual_chunk_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);client,generated,base=self.fixture(root)
            chunk=base/'east/chunks/00_00/world.glb'
            scene(chunk,regions=('east',),translation=(3,0,2),missing=True)
            path=base/'east/world.json';manifest=json.loads(path.read_text())
            manifest['streamingChunks']['chunks'][0]['glbBytes']=chunk.stat().st_size
            path.write_text(json.dumps(manifest))
            result=A.run(client,generated,root/'report.json',geometry_only=True)
            self.assertFalse(result['passed'])
            self.assertTrue(any('Streaming chunks: 1 missing' in error for error in result['errors']),result['errors'])

    def test_shaping_and_composition_algorithm_freshness_are_required_in_provisional_mode(self):
        for name in ('assemblies.py','crown_support.py','westhaven_support.py','ferry_support.py','mirror_support.py','manymouth_support.py','mirror_streets.py','four_gates_support.py','amberwood_support.py','amberwood_access.py','mirror_lake_support.py','ssarathi_bank_support.py','manymouth_boats.py','terrain_export.py','scene_io.py','grey_crossings.py','four_gates_sage.py','door_approaches.py','hull_settle.py','resource_trails.py','object_edits.py','winding.py','river_crossings.py','reach_links.py','authored_points.py','bridge_prepare.py','bridge_profiles.py','../_northern/requirements.txt','build_continent.py','legacy-server-profile/config/eloria/maps.txt','continent-edits.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);client,generated,base=self.fixture(root)
                path=base/'_continent'/name
                path.write_text(path.read_text().replace('return toward','return None') if name=='build_continent.py'
                                else '# altered assembly ground reference\n')
                result=A.run(client,generated,root/'report.json',geometry_only=True)
                self.assertFalse(result['passed'])
                self.assertTrue(any('changed after composition' in error for error in result['errors']),result['errors'])

    def test_missing_shaping_certificate_and_runtime_mismatch_are_rejected(self):
        requirement='eloria-assets/maps/nymara-regions/_northern/requirements.txt'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);client,generated,_=self.fixture(root)
            path=generated/'composition.json';composition=json.loads(path.read_text())
            composition['sources'].pop(requirement);path.write_text(json.dumps(composition))
            export=generated/'export.json';ledger=json.loads(export.read_text())
            ledger['compositionSha256']=hashlib.sha256(path.read_bytes()).hexdigest();export.write_text(json.dumps(ledger))
            result=A.run(client,generated,root/'report.json',geometry_only=True)
            self.assertFalse(result['passed'])
            self.assertTrue(any('missing shaping source certificates' in error for error in result['errors']),result['errors'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);client,generated,_=self.fixture(root)
            with patch.object(A,'geometry_dependencies',return_value={'shapely':'2.1.2','geos':'3.10.0-test'}):
                result=A.run(client,generated,root/'report.json',geometry_only=True)
            self.assertFalse(result['passed'])
            self.assertTrue(any('dependencies changed' in error for error in result['errors']),result['errors'])

    def test_provisional_address_and_master_provenance_cannot_be_invented(self):
        for field in ('address','master'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);client,generated,base=self.fixture(root)
                path=base/'east/world.json';manifest=json.loads(path.read_text())
                if field=='address':manifest['coordinateTransform']['serverOrigin'][0]+=1
                else:manifest['singleContinentSource']['masterSha256']='0'*64
                path.write_text(json.dumps(manifest))
                result=A.run(client,generated,root/'report.json',geometry_only=True)
                self.assertFalse(result['passed'])
                self.assertTrue(any(('address bounds' if field=='address' else 'different master') in error for error in result['errors']))

    def test_stale_bridge_export_source_cannot_pass_through_unchanged_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);client,generated,base=self.fixture(root)
            (base/'_continent/bridge_export.py').write_text('# Changed deck profile\n')
            result=A.run(client,generated,root/'report.json',geometry_only=True)
            self.assertFalse(result['passed'])
            self.assertTrue(any('Authored landscape changed after composition' in error for error in result['errors']))



def rule_fixture():
    """A straight river along x = 120 (half width 10, narrowing to 5 over z 96..112), dry banks at 4 m."""
    rivers = [{'id': 'main', 'name': 'Main', 'width': 10., 'points': [[120., 0., 0.], [120., 180., 0.], [120., 360., 0.]]}]
    half = lambda z: np.where((np.asarray(z) >= 96) & (np.asarray(z) <= 112), 5., 10.)
    water = lambda x, z: np.abs(np.asarray(x, float) - 120.) <= half(z)
    ground = lambda x, z: np.where(water(x, z), -1.5, 4.)
    site = {'id': 0, 'river': 'main', 'arcMetres': 104., 'wetEdges': [[115., 104.], [125., 104.]]}
    policy = {'deck_landing_metres': 6., 'minimum_spacing_metres': 100.}
    return rivers, water, ground, site, policy


class RoadRuleTests(unittest.TestCase):
    def test_saved_road_association_uses_certified_alias_xz_and_exact_emitted_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = Path('amberwood/authoring/continent-authoring.json')
            path = root / relative
            path.parent.mkdir(parents=True)
            snapshot = {'regionId': 'amberwood', 'continentTranslation': [10., 0., 20.], 'objects': [],
                        'paths': [{'kind': 'road', 'id': 'local-lane', 'replacesRouteId': 'published-lane',
                                   'points': [{'position': [0., 9., 0.]}, {'position': [4., 9., 0.]}]}]}
            route = {'id': 'published-lane', 'points': [[10., 9., 20.], [14., 9., 20.]]}
            doc = {'nodes': [{'name': 'placement', 'translation': [10., 0., 20.], 'children': [1]},
                             {'name': 'Walk_amberwood_local-lane_amberwood_00_00', 'mesh': 0},
                             {'name': 'Walk_amberwood_local-lane-other_amberwood_00_00', 'mesh': 1}],
                   'accessors': [{'componentType': 5126}, {'componentType': 5125}, {'componentType': 5126}],
                   'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]},
                              {'primitives': [{'attributes': {'POSITION': 2}, 'indices': 1}]}]}
            points = np.array([[0., .055, -1.], [0., .055, 1.], [4., .055, -1.],
                               [4., .055, -1.], [0., .055, 1.], [4., .055, 1.]])
            unrelated = points.copy(); unrelated[:, 1] = 10.
            arrays = {0: points.astype(np.float32), 1: np.arange(6), 2: unrelated.astype(np.float32)}

            def read_surfaces(document, roads, saved=snapshot, stale=False):
                path.write_text(json.dumps(saved))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                certificate = {'continentAuthoring': {'regions': {'amberwood': {
                    'snapshotSha256': digest, 'sources': {relative.as_posix(): digest}}}}}
                if stale:
                    path.write_text(json.dumps(saved) + ' ')
                with patch.object(A.GR, 'load', return_value=(document, b'')), patch.object(A.GR, 'accessor', side_effect=lambda _d, _b, i: arrays[i]):
                    return A.saved_walk_surfaces(root, root, certificate, A.Inputs(), roads)

            decks, surfaces = read_surfaces(doc, [route])
            self.assertEqual(decks, [])
            np.testing.assert_allclose(A.saved_deck_height([[10., 20.], [12., 20.], [14., 20.]], surfaces['published-lane']), .055)
            transformed = copy.deepcopy(doc); transformed['nodes'][0]['scale'] = [2., 1., 4.]
            _, scaled = read_surfaces(transformed, [route])
            encoded = arrays[0]
            half_ulp = np.maximum(np.abs(np.nextafter(encoded, np.float32(np.inf)).astype(float) - encoded),
                                  np.abs(encoded - np.nextafter(encoded, np.float32(-np.inf)).astype(float))) * .5
            eps = np.finfo(float).eps
            expected_error = half_ulp[:, [0, 2]] * [2., 4.]
            expected_error += (4. * eps / (1. - 4. * eps)) * (np.abs(encoded[:, [0, 2]]) * [2., 4.] + [10., 20.])
            np.testing.assert_array_equal(scaled['published-lane'][0][3], expected_error.reshape(2, 3, 2))
            missing = copy.deepcopy(doc); missing['nodes'][1]['name'] = 'Walk_unrelated_amberwood_00_00'
            duplicate = copy.deepcopy(doc); duplicate['nodes'].append(copy.deepcopy(duplicate['nodes'][1]))
            wrong_route = copy.deepcopy(route); wrong_route['points'][1][0] += 1.
            duplicate_saved = copy.deepcopy(snapshot); duplicate_saved['paths'].append(copy.deepcopy(snapshot['paths'][0]))
            cases = [(doc, [], snapshot, False, 'missing from published'),
                     (doc, [route, route], snapshot, False, 'Ambiguous published'),
                     (missing, [route], snapshot, False, 'missing or ambiguous'),
                     (duplicate, [route], snapshot, False, 'missing or ambiguous'),
                     (doc, [wrong_route], snapshot, False, 'route XZ'),
                     (doc, [route], duplicate_saved, False, 'ambiguous saved road'),
                     (doc, [route], snapshot, True, 'changed after composition')]
            for document, roads, saved, stale, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(A.AuditError, message):
                    read_surfaces(document, roads, saved, stale)

    def test_saved_road_rules_measure_actual_surface_and_keep_float_and_water_limits(self):
        road = {'id': 'saved', 'points': [[0., 9., 0.], [4., 9., 0.]]}
        original = copy.deepcopy(road)
        def group(height, low=0., high=4.):
            tri = np.array([[[low, height, -1.], [low, height, 1.], [high, height, -1.]],
                            [[high, height, -1.], [low, height, 1.], [high, height, 1.]]])
            return (np.array([low, -1.]), np.array([high, 1.]), tri)
        ground = lambda x, z: np.zeros_like(x)
        dry = lambda x, z: np.zeros_like(x, dtype=bool)
        policy = {'deck_landing_metres': 6., 'minimum_spacing_metres': 100.}
        for heights, floating in [([.055], False), ([.055, .055], False), ([.055, 3.], True), ([3., .055], True)]:
            with self.subTest(heights=heights):
                result = A.road_rule_findings([road], [], [], policy, ground, dry,
                    saved_road_groups={'saved': [group(h) for h in heights]})
                self.assertEqual(bool(result['violations']), floating)
                if floating:
                    self.assertIn('above the ground', result['violations'][0])
        # A procedural route still measures its original Y, and grounded
        # authored roads over water still require a real crossing span.
        self.assertTrue(A.road_rule_findings([road], [], [], policy, ground, dry)['violations'])
        wet = lambda x, z: np.ones_like(x, dtype=bool)
        self.assertIn('over river water', A.road_rule_findings([road], [], [], policy, ground, wet,
            saved_road_groups={'saved': [group(.055)]})['violations'][0])
        with self.assertRaisesRegex(A.AuditError, 'cover every rule station'):
            A.road_rule_findings([road], [], [], policy, ground, dry,
                saved_road_groups={'saved': [group(.055, low=1.)]})
        self.assertEqual(road, original)

    def test_float32_endpoint_reconciliation_is_bounded_and_never_fills_interior_gaps(self):
        # Actual failing Manymouth endpoint and actual emitted face: its
        # source endpoint lies 60 micrometres outside the encoded triangle.
        triangle = np.array([[544.3297119140625, 3.2324578762054443, 1062.005126953125],
                             [544.1556396484375, 3.190847873687744, 1060.9052734375],
                             [543.8148803710938, 3.1908743381500244, 1061.8115234375]])
        source = np.array([543.8148708343506, 9., 1061.8115844726562])
        encoded = triangle.astype(np.float32)
        error = np.maximum(np.abs(np.nextafter(encoded, np.float32(np.inf)).astype(float) - triangle),
                           np.abs(triangle - np.nextafter(encoded, np.float32(-np.inf)).astype(float)))[:, [0, 2]] * .5
        inside = triangle.mean(axis=0)
        def group(tri):
            return (tri[:, [0, 2]].min(axis=0), tri[:, [0, 2]].max(axis=0), tri[None], error[None])
        stations = np.array([source, inside])
        heights, accepted = A.saved_road_station_heights(stations, [group(triangle)])
        self.assertTrue(np.isfinite(heights).all())
        self.assertEqual(len(accepted), 1)
        self.assertLessEqual(accepted[0]['distanceMetres'], accepted[0]['encodingBoundMetres'])
        np.testing.assert_array_equal(stations[0], source)
        # A displacement even just beyond the vertex encoding box must not
        # become an endpoint exemption. A nearby interior gap is also fatal.
        outside = source.copy(); outside[2] = triangle[2, 2] + error[2, 1] * 1.01
        outside[0] = triangle[2, 0] - error[2, 0] * 1.01
        self.assertFalse(np.isfinite(A.saved_road_station_heights(np.array([outside, inside]), [group(triangle)])[0][0]))
        self.assertFalse(np.isfinite(A.saved_road_station_heights(np.array([inside, source, inside]), [group(triangle)])[0][1]))
        # Highest eligible emitted geometry still fails the original float
        # limit, even when a lower duplicate surface is also present.
        raised = triangle.copy(); raised[:, 1] += 3.
        road = {'id': 'encoded', 'points': stations.tolist()}
        floor = lambda x, z: np.full_like(x, 3.2)
        dry = lambda x, z: np.zeros_like(x, dtype=bool)
        for groups in ([group(triangle), group(raised)], [group(raised), group(triangle)]):
            result = A.road_rule_findings([road], [], [], {}, floor, dry, saved_road_groups={'encoded': groups})
            self.assertTrue(any('above the ground' in v for v in result['violations']))
            self.assertEqual(result['totals']['encodedRoadEndpointsReconciled'], 1)

    def test_saved_walk_floor_uses_certified_wrapper_and_emitted_walkable_triangles(self):
        rivers, water, ground, site, policy = rule_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Path('amberwood/authoring/continent-authoring.json')
            path = root / source
            path.parent.mkdir(parents=True)
            snapshot = {'regionId': 'amberwood', 'objects': [{
                'nodeName': 'Walk_Bridge_WorldPlacement', 'collisionRole': 'walk_surface',
                'metadata': {'authoredCrossing': {'id': 'main@104', 'walkNode': 'Walk_Bridge'}}}]}
            path.write_text(json.dumps(snapshot))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            composition = {'continentAuthoring': {'regions': {'amberwood': {
                'snapshotSha256': digest, 'sources': {source.as_posix(): digest}}}}}
            # A second Walk_Bridge outside the certified wrapper and a roof
            # inside it both stand higher, but neither can support this road.
            nodes = [
                {'name': 'amberwood_Walk_Bridge_WorldPlacement_WorldPlacement', 'children': [1]},
                {'name': 'Walk_Bridge_WorldPlacement', 'children': [2]},
                {'name': 'Walk_Bridge', 'children': [3, 4]},
                {'name': 'deck', 'mesh': 0},
                {'name': 'bridge_roof', 'mesh': 1},
                {'name': 'other_region_Walk_Bridge_WorldPlacement_WorldPlacement', 'children': [6]},
                {'name': 'Walk_Bridge', 'children': [7]},
                {'name': 'alias_deck', 'mesh': 2},
            ]
            doc = {'nodes': nodes, 'meshes': [
                {'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]},
                {'primitives': [{'attributes': {'POSITION': 2}, 'indices': 1}]},
                {'primitives': [{'attributes': {'POSITION': 2}, 'indices': 1}]},
            ]}
            deck = np.array([[112., 3., 104.], [128., 3., 104.], [120., 3., 96.],
                             [112., 3., 104.], [120., 3., 112.], [128., 3., 104.]])
            roof = deck.copy(); roof[:, 1] = 10.
            arrays = {0: deck, 1: np.arange(6), 2: roof}
            with patch.object(A.GR, 'load', return_value=(doc, b'')), patch.object(A.GR, 'accessor', side_effect=lambda _d, _b, i: arrays[i]):
                groups, _ = A.saved_walk_surfaces(root, root, composition, A.Inputs())
            self.assertEqual(len(groups), 1)
            supported = {'id': 'saved-crossing', 'points': [[112., 2.5, 104.], [128., 2.5, 104.]]}
            self.assertEqual(A.road_rule_findings([supported], [], rivers, policy, ground, water,
                                                  saved_deck_groups=groups)['violations'], [])
            # The different wrapper/roof cannot rescue a road above the real deck.
            high = {'id': 'above-deck', 'points': [[112., 4., 104.], [128., 4., 104.]]}
            beside = {'id': 'beside-deck', 'points': [[127., 6., 96.], [127., 6., 112.]]}
            found = A.road_rule_findings([high, beside], [], rivers, policy, ground, water,
                                         saved_deck_groups=groups)
            self.assertIn('above-deck:', ' | '.join(found['violations']))
            self.assertIn('beside-deck:', ' | '.join(found['violations']))
            moved = [(low + np.array([100., 0.]), high + np.array([100., 0.]), tri + np.array([100., 0., 0.]))
                     for low, high, tri in groups]
            self.assertTrue(A.road_rule_findings([supported], [], rivers, policy, ground, water,
                                                 saved_deck_groups=moved)['violations'])
            # A declared active floor missing from the emitted master fails closed.
            missing = copy.deepcopy(doc)
            missing['nodes'][2]['name'] = 'Walk_Deleted'
            with patch.object(A.GR, 'load', return_value=(missing, b'')), patch.object(A.GR, 'accessor', side_effect=lambda _d, _b, i: arrays[i]):
                with self.assertRaisesRegex(A.AuditError, 'saved walk root'):
                    A.saved_walk_surfaces(root, root, composition, A.Inputs())

    def test_a_square_crossing_at_a_site_on_the_ground_passes(self):
        rivers, water, ground, site, policy = rule_fixture()
        road = {'id': 'seam', 'points': [[60., 4., 104.], [114., 4., 104.], [126., .85, 104.], [180., 4., 104.]]}
        found = A.road_rule_findings([road], [site], rivers, policy, ground, water, piers=[{'name': 'BridgeUnionPier_001_120_104', 'height': 2.4}])
        self.assertEqual(found['violations'], [])
        self.assertEqual(found['totals']['crossingRuns'], 1)

    def test_a_road_down_the_channel_or_across_it_obliquely_fails(self):
        rivers, water, ground, site, policy = rule_fixture()
        along = {'id': 'discovery-a1', 'points': [[125., 4., 200.], [122., 4., 320.]]}
        oblique = {'id': 'door-c1', 'points': [[90., 4., 80.], [150., 4., 128.]]}
        found = A.road_rule_findings([along, oblique], [dict(site, wetEdges=[[112., 90.], [128., 118.]])], rivers, policy, ground, water)
        self.assertTrue(any(v.startswith('discovery-a1:') and 'over river water outside every bridge site' in v for v in found['violations']), found['violations'])
        self.assertTrue(any(v.startswith('door-c1:') and 'degrees to the flow' in v for v in found['violations']), found['violations'])

    def test_an_emitted_authored_deck_supports_only_its_triangle_footprint_and_height(self):
        rivers, water, ground, site, policy = rule_fixture()
        # A diagonal deck: its AABB includes (127, 96), but neither triangle
        # does.  The deck top is y=3 throughout its actual footprint.
        deck = np.array([[[112., 3., 104.], [120., 3., 96.], [128., 3., 104.]],
                         [[112., 3., 104.], [128., 3., 104.], [120., 3., 112.]]])
        supported = {'id': 'saved-crossing', 'points': [[112., 2.5, 104.], [128., 2.5, 104.]]}
        found = A.road_rule_findings([supported], [], rivers, policy, ground, water,
                                     authored_deck_triangles=deck)
        self.assertEqual(found['violations'], [])
        beyond = {'id': 'beside-deck', 'points': [[127., 6., 96.], [127., 6., 112.]]}
        high = {'id': 'above-deck', 'points': [[112., 4., 104.], [128., 4., 104.]]}
        found = A.road_rule_findings([beyond, high], [], rivers, policy, ground, water,
                                     authored_deck_triangles=deck)
        text = ' | '.join(found['violations'])
        self.assertIn('beside-deck:', text)
        self.assertIn('above-deck:', text)

    def test_close_sites_tall_piers_floating_stations_and_long_crossings_fail(self):
        rivers, water, ground, site, policy = rule_fixture()
        near = dict(site, id=1, arcMetres=130., wetEdges=[[110., 130.], [130., 130.]])
        floating = {'id': 'hub-road', 'points': [[20., 4., 20.], [60., 7., 20.]]}
        found = A.road_rule_findings([floating], [site, near], rivers, policy, ground, water,
                                     piers=[{'name': 'BridgeUnionPier_002_120_160', 'height': 9.5}])
        text = ' | '.join(found['violations'])
        self.assertIn('bridge sites 26 m apart', text)
        self.assertIn('pier 9.5 m tall', text)
        self.assertIn('hub-road: ', text)
        self.assertIn('crossing 20.5 m against 10.5 m', text)
        # A designed deck carries its own elevated floor.
        found = A.road_rule_findings([floating], [site], rivers, policy, ground, water, designed_boxes=[((10., 10.), (70., 30.))])
        self.assertEqual(found['violations'], [])

    def test_the_local_shortest_ignores_sections_at_a_territory_seam(self):
        rivers, water, ground, site, policy = rule_fixture()
        wide = dict(site, arcMetres=130., wetEdges=[[110., 130.], [130., 130.]])     # 20 m, 26 m from the 10 m reach
        self.assertTrue(any('crossing 20.5 m against 10.5 m' in v for v in A.road_rule_findings([], [wide], rivers, policy, ground, water)['violations']))
        # The narrow reach stands on a territory seam (z 96..112): no bridge is built there, so it is no comparison.
        seam = lambda x, z: (np.asarray(z, float) >= 90) & (np.asarray(z, float) <= 118)
        self.assertEqual(A.road_rule_findings([], [wide], rivers, policy, ground, water, seam_near_at=seam)['violations'], [])

    def test_bridge_floors_may_stand_over_the_span_but_not_over_dry_ground_beyond_it(self):
        rivers, water, ground, site, policy = rule_fixture()
        over_span = np.array([[118., 1., 104.], [131., 3.5, 104.]])
        beyond = np.array([[150., 7., 104.]])
        self.assertEqual(A.road_rule_findings([], [site], rivers, policy, ground, water, union_vertices=over_span)['violations'], [])
        found = A.road_rule_findings([], [site], rivers, policy, ground, water, union_vertices=np.r_[over_span, beyond])
        self.assertTrue(any('bridge floor vertices' in v for v in found['violations']))

if __name__ == '__main__':
    unittest.main()
