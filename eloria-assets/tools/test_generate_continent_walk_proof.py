"""Run with ELORIA_PROOF_SERVER pointing at the paired server checkout.

The production World pathfinder, ELM loader and storage collision participate;
no server process or database is constructed.
"""
import os
import copy
import itertools
import json
import math
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import generate_continent_walk_proof as P


class ServedInstanceExitTests(unittest.TestCase):
    def test_exact_served_identity_join_and_provenance_validation(self):
        import publish_diagonal_continent as publisher
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);relative='config/eloria/instances/arena.def';path=root/relative
            path.parent.mkdir(parents=True)
            text='[instance]\nspawn_name: arena\nexit_map: a\nexit_x: 7\nexit_y: 8\n'
            path.write_text(text)
            identity=json.dumps([relative,'arena','exit_x','exit_y','a'],separators=(',',':'))
            source=publisher.instance_exit_records(relative,text,{'a':{}})[identity]
            source={**source,'originalTile':[1,2],'sha256':'source-sha'}
            entry={'source':source,'tile':[7,8],
                   'authoredBinding':{'source':{'amendmentReport':{'path':'amendment.json'}}}}
            publication={'instanceExitSchema':2,'regions':{'a':{}}};tracked=[]
            with mock.patch.object(publisher,'certified_instance_exit_sources',return_value={identity:source}), \
                    mock.patch.object(publisher,'validate_instance_exit_table',return_value={identity:entry}) as validate:
                result=P.served_instance_exits(root,root,publication,tracked.append)
                self.assertEqual(result,{identity:entry})
                validate.assert_called_once_with(publication['regions'],{identity:source},client=root,require_authored=True)
                self.assertIn(path,tracked);self.assertIn(root/'amendment.json',tracked)
                variants=[text.replace('exit_x: 7','exit_x: 9'),text.replace('spawn_name: arena','spawn_name: other'),
                          text+text,text.replace('exit_map: a','exit_map: b'),'']
                for bad in variants:
                    with self.subTest(definition=bad):
                        path.write_text(bad)
                        with self.assertRaises(P.AuditError):P.served_instance_exits(root,root,publication,lambda _:None)
                path.write_text(text)
                validate.side_effect=ValueError('amendment digest differs')
                with self.assertRaisesRegex(P.AuditError,'amendment digest differs'):
                    P.served_instance_exits(root,root,publication,lambda _:None)

    def test_no_schema_downgrade_or_missing_binding_fallback(self):
        for schema in (None,1,True,3):
            with self.subTest(schema=schema),self.assertRaises(P.AuditError):
                P.served_instance_exits(Path('.'),Path('.'),{'instanceExitSchema':schema},lambda _:None)


class ChunkGraphTests(unittest.TestCase):
    def generator(self):
        g=P.Generator.__new__(P.Generator);g.chunk_mode=True
        polygons={'a':[[0,0],[4,0],[4,4],[0,4]],'b':[[4,0],[8,0],[8,2],[4,2]],
                  'c':[[4,2],[8,2],[8,4],[4,4]]}
        g.geography={'ownershipRasterMetres':2,'regions':{n:{'ownershipPolygon':p} for n,p in polygons.items()},
                     'connections':[{'id':'ab','ends':[{'region':'a'},{'region':'b'}]}]}
        g.landscape_plan={'bounds':[0,0,8,4]}
        g.specs={n:{'translation':[0,0,0],'serverOrigin':[0,0]} for n in polygons}
        edges={('a','b'):[[[4,0],[4,2]]],('a','c'):[[[4,2],[4,4]]],('b','c'):[[[4,2],[8,2]]]}
        def link(identity,pair,visual=False):
            points=edges[pair];anchor=[sum(p[0] for p in points[0])/2,0,sum(p[1] for p in points[0])/2]
            return {'id':identity,'visualOnly':visual,'seamless':True,'ends':[
                {'map':n,'coordinateTransform':{'serverOrigin':[0,0]},'preloadEdges':copy.deepcopy(points),
                 'frame':{'geometryMode':'continent-chunks-v1','anchor':anchor.copy(),'halfWidthTiles':3}}
                for n in pair]}
        g.links=[link('ab',('a','b'))]
        g.visual_links=[link('view-ac',('a','c'),True),link('view-bc',('b','c'),True)]
        g.publication={'connections':[{'id':'ab','type':'walk','ends':[
            {'region':n,'frame':{'halfWidthTiles':3},'lanes':[{'tile':[i,0],'arrival':[i,1]} for i in range(7)]} for n in ('a','b')]},
            {'id':'bc-ferry','type':'ferry','ends':[{'region':'b'},{'region':'c'}]}]}
        return g

    def test_nonlegacy_counts_are_derived_from_complete_ownership(self):
        result=self.generator().graph_integrity()
        self.assertEqual((result['roadPairs'],result['visualPairs'],result['physicalPairs'],result['ferryPairs']),(1,2,3,1))
        self.assertEqual(result['boundarySource'],'independent ownership polygon scan conversion')

    def test_missing_visual_edge_and_false_continuous_span_fail(self):
        g=self.generator();g.visual_links.pop()
        with self.assertRaisesRegex(P.AuditError,'exact remaining owned boundaries'):g.graph_integrity()
        g=self.generator();g.visual_links[0]['ends'][0]['preloadEdges']=[[[4,0],[4,4]]]
        with self.assertRaisesRegex(P.AuditError,'finite preload edges differ'):g.graph_integrity()

    def test_published_road_cannot_be_silently_removed_or_duplicated(self):
        g=self.generator();g.links=[]
        with self.assertRaisesRegex(P.AuditError,'Runtime roads differ'):g.graph_integrity()
        g=self.generator();g.links.append(copy.deepcopy(g.links[0]))
        with self.assertRaisesRegex(P.AuditError,'Runtime roads differ'):g.graph_integrity()

    def test_missing_ferry_leaves_island_unreachable(self):
        g=self.generator();g.publication['connections'].pop()
        with self.assertRaisesRegex(P.AuditError,'no declared continent travel route'):g.graph_integrity()

    def test_ownership_gaps_overlaps_and_displaced_frames_fail(self):
        for change in (-2,2):
            g=self.generator();polygon=g.geography['regions']['a']['ownershipPolygon']
            polygon[1][0]+=change;polygon[2][0]+=change
            with self.assertRaisesRegex(P.AuditError,'Ownership has'):g.graph_integrity()
        g=self.generator()
        for end in g.links[0]['ends']:end['frame']['anchor'][0]=2
        with self.assertRaisesRegex(P.AuditError,'outside its physical boundary'):g.graph_integrity()

    def test_ferry_only_visual_route_is_explicit_and_not_a_walk_claim(self):
        g=self.generator();g.errors=[];g.visual_links=[g.visual_links[1]]
        g.links[0]['ends'][0]['map']='a';g.links[0]['ends'][1]['map']='b'
        result=g.visual_road_requests()
        self.assertEqual(len(result),2);self.assertFalse(g.errors)
        self.assertTrue(all(r['travelMode']=='ferry-required' and not r['oneClickWalkAvailable'] for r in result))
        self.assertTrue(all(r['ferryConnections']==['bc-ferry'] for r in result))


class ClickFramingTests(unittest.TestCase):
    LINK = {'id': 'manymouth_delta--grey_moors'}
    MANY = {'map': 'manymouth_delta', 'frame': {'outward': [-1, 0]}}
    GREY = {'map': 'grey_moors', 'frame': {'outward': [1, 0]}}

    def generator(self, surface):
        # Exercise fixture emission only; the full occupied path audit remains
        # a separate required gate and is not replaced by these framing tests.
        generator = P.Generator.__new__(P.Generator)
        portal = SimpleNamespace(x=20, y=401, destination_x=403, destination_y=5)
        generator.sorted_lanes = lambda a, b: [portal] * 7
        generator.requests = []
        # Grey tile (403,5) continues one metre beyond the Manymouth trigger (20,401).
        generator.specs = {'manymouth_delta': {'arrival': [60, 401], 'serverOrigin': [0, 0], 'translation': [0, 0, 0]},
                           'grey_moors': {'arrival': [380, 5], 'serverOrigin': [0, 0], 'translation': [-384, 0, -396]}}
        # Route references follow the real server road toward each arrival;
        # a straight stub road reproduces the classic inward offsets exactly.
        def straight(region, start, target, blocked):
            step = 1 if target[0] > start[0] else -1
            return [(x, start[1]) for x in range(start[0] + step, target[0] + step, step)]
        generator.world = SimpleNamespace(find_path=straight)
        generator.audit = SimpleNamespace(exact_path=lambda *args, **kwargs: generator.requests.append((args, kwargs)),
                                          standing=lambda region, tile: True, occupied=lambda region: set(),
                                          automatic={'manymouth_delta': set(), 'grey_moors': set()})
        generator.surface_height = surface
        return generator

    def test_harness_projection_matches_the_gameplay_camera(self):
        focus = (10.0, 5.0, -20.0)
        self.assertEqual(self.generator(lambda region, tile: 0.0).godot_xz('grey_moors', 403.5, 5.5), (19.5, -401.5))
        centre = P.harness_screen_position(focus, 0.0, 32, (10.0, 5.0 + P.HARNESS_AIM_HEIGHT, -20.0))
        self.assertAlmostEqual(centre[0], 720.0); self.assertAlmostEqual(centre[1], 450.0)
        # Yaw 0 puts the camera at +z looking toward -z: points ahead rise on
        # screen, points at the actor's right (+x) land right of centre.
        ahead = P.harness_screen_position(focus, 0.0, 32, (10.0, 5.0, -30.0))
        self.assertAlmostEqual(ahead[0], 720.0); self.assertLess(ahead[1], centre[1])
        self.assertGreater(P.harness_screen_position(focus, 0.0, 32, (14.0, 5.0, -20.0))[0], 720.0)
        # Above and behind the camera (it sits 16 m toward +z, 27.7 m up).
        self.assertIsNone(P.harness_screen_position(focus, 0.0, 32, (10.0, 40.0, 40.0)))
        self.assertLess(P.visible_margin(P.harness_screen_position(focus, 0.0, 32, (10.0, 5.0, -60.0))), 0)
        self.assertEqual(P.visible_margin(None), -math.inf)
        self.assertEqual(P.visible_margin((100.0, 30.0)), 30.0)
        self.assertEqual(P.visible_margin((1430.0, 300.0)), 10.0)

    def test_deep_click_target_is_the_farthest_visible_road_tile(self):
        generator = self.generator(lambda region, tile: 0.0)
        route = generator.click_route(self.LINK, self.MANY, self.GREY, 12)
        identity = 'manymouth_delta--grey_moors-manymouth_delta-click-12'
        steps = route['targetSteps']; target = tuple(route['steps'][0]['tile'])
        self.assertTrue(2 < steps <= 12)
        self.assertEqual(target, (403 - steps, 5))
        self.assertEqual(route, {'id': identity, 'map': 'manymouth_delta', 'start': [28, 401], 'startTolerance': 0,
            'yaw': 90.0, 'distance': 32, 'walkTimeout': 60, 'requestedSteps': 12, 'targetSteps': steps,
            'screenMarginPx': route['screenMarginPx'],
            'steps': [{'tile': list(target), 'destination': 'grey_moors', 'clickNeighbor': True,
                       'label': 'exact visible resident target', 'capture': identity}]})
        self.assertGreaterEqual(route['screenMarginPx'], P.CLICK_VISIBLE_MARGIN_PX)
        if steps < 12:
            deeper = generator.harness_screen('manymouth_delta', (28, 401), 'grey_moors', (403 - steps - 1, 5), 90.0, 32)
            self.assertLess(P.visible_margin(deeper), P.CLICK_VISIBLE_MARGIN_PX)
        self.assertEqual(generator.requests, [
            (('manymouth_delta', (28, 401), (20, 401)), {'allowed': [(20, 401)]}),
            (('grey_moors', (403, 5), target), {})])
        shallow = generator.click_route(self.LINK, self.MANY, self.GREY, 2)
        self.assertEqual((shallow['targetSteps'], shallow['steps'][0]['tile'], shallow['distance']), (2, [401, 5], 32))

    def test_climbing_roads_take_shallower_targets_and_walls_are_rejected(self):
        flat = self.generator(lambda region, tile: 0.0).click_route(self.LINK, self.MANY, self.GREY, 12)
        ramp = self.generator(lambda region, tile: 0.0 if region == 'manymouth_delta' else (403 - tile[0]) * 1.5)
        climbing = ramp.click_route(self.LINK, self.MANY, self.GREY, 12)
        self.assertLess(climbing['targetSteps'], flat['targetSteps'])
        self.assertGreater(climbing['targetSteps'], 2)
        self.assertGreaterEqual(climbing['screenMarginPx'], P.CLICK_VISIBLE_MARGIN_PX)
        wall = self.generator(lambda region, tile: 0.0 if region == 'manymouth_delta' else 60.0)
        with self.assertRaisesRegex(P.AuditError, 'no route tile 3-12 steps beyond \\(403, 5\\) is visible'):
            wall.click_route(self.LINK, self.MANY, self.GREY, 12)
        with self.assertRaisesRegex(P.AuditError, 'no route tile 1-2 steps beyond'):
            wall.click_route(self.LINK, self.MANY, self.GREY, 2)
        missing = self.generator(lambda region, tile: None if tile == (391, 5) else 0.0)
        self.assertNotEqual(missing.click_route(self.LINK, self.MANY, self.GREY, 12)['steps'][0]['tile'], [391, 5])


class FerryArrivalFixtureTests(unittest.TestCase):
    def test_published_arrival_uses_destination_tile_center_and_nonzero_transform(self):
        generator=P.Generator.__new__(P.Generator)
        generator.specs={'island':{'arrival':[1,2],'serverOrigin':[20,80],'translation':[350,5,1200]}}
        destination={'region':'island','tile':[15,36],'arrival':[12,34]}
        self.assertEqual(generator.ferry_arrival(destination),{
            'map':'island','tile':[12,34],'global':[342.5,1245.5],
            'units':'metres','point':'tile-center'})
        self.assertEqual(destination['arrival'],[12,34])

    def test_missing_transform_or_fractional_authoritative_tile_is_rejected(self):
        generator=P.Generator.__new__(P.Generator);generator.specs={'island':{}}
        with self.assertRaisesRegex(P.AuditError,'published continent transform'):
            generator.ferry_arrival({'region':'island','arrival':[12,34]})
        with self.assertRaisesRegex(P.AuditError,'exact authoritative tile'):
            generator.ferry_arrival({'region':'island','arrival':[12.5,34]})


@unittest.skipUnless(os.environ.get('ELORIA_PROOF_SERVER'), 'Set ELORIA_PROOF_SERVER to run paired roadless fixtures')
class RoadlessFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R=P.runtime(Path(os.environ['ELORIA_PROOF_SERVER']))

    def world(self,width=100,height=100):
        w=self.R['world'].World.__new__(self.R['world'].World)
        w.settings=SimpleNamespace(max_walk_height_change=2,portal_activation_distance=8)
        w.maps={}
        w.collision_maps={name:self.R['collision'].with_step_mask(
            self.R['collision'].CollisionMap(width,height,bytes([10])*(width*height)),2) for name in ('a','b')}
        w.sessions,w.animals,w.animals_by_map=[],{},{}
        w.npcs={};w._footprint_collision={}
        return w

    def portal(self,source,x,y,destination,dx,dy):
        return self.R['maps'].Portal(source,x,y,destination,dx,dy)

    def roadless_generator(self,surface=lambda region,tile:0.0):
        world=self.world();raw=bytearray(world.collision_maps['a'].heights)
        for y in range(100):raw[y*100+50]=0
        collision=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(100,100,bytes(raw)),2)
        world.collision_maps={'a':collision,'b':collision}
        ys=(20,50,80)
        portals=[]
        for y in ys:
            portals.extend([self.portal('a',82,y,'b',10,y),self.portal('b',8,y,'a',80,y)])
        ends=[{'map':'a','frame':{'outward':[1,0]},'coordinateTransform':{'serverOrigin':[0,0]}},
              {'map':'b','frame':{'outward':[-1,0]},'coordinateTransform':{'serverOrigin':[0,0]}}]
        publication_ends=[
            {'region':'a','lanes':[{'tile':[82,y],'arrival':[81,y]} for y in ys]},
            {'region':'b','lanes':[{'tile':[8,y],'arrival':[9,y]} for y in ys]}]
        g=P.Generator.__new__(P.Generator);g.chunk_mode=True
        g.world,g.portals=world,portals;g.audit=P.WalkAudit(world,portals)
        g.links=[{'id':'a--b-roadless','road':False,'ends':ends}]
        g.publication={'connections':[{'id':'a--b-roadless','type':'walk','road':False,'ends':publication_ends}]}
        g.specs={'a':{'arrival':[2,5],'serverOrigin':[0,0],'translation':[0,0,0]},
                 'b':{'arrival':[90,5],'serverOrigin':[0,0],'translation':[72,0,0]}}
        g.surface_height=surface;g.errors,g.lanes=[],[]
        return g

    def test_roadless_fixtures_cover_both_directions_from_hub_disconnected_pockets(self):
        g=self.roadless_generator()
        with self.assertRaisesRegex(P.AuditError,'no route'):
            g.route_path('a',(82,50),'hub-disconnected policy check')
        centre,shoulders,clicks=g.borders()
        self.assertEqual(g.errors,[]);self.assertEqual(len(g.lanes),6)
        self.assertEqual((len(centre),len(shoulders),len(clicks)),(2,0,6))
        for source,destination in (('a','b'),('b','a')):
            walk=next(route for route in centre if route['map']==source)
            source_clicks=[route for route in clicks if route['map']==source]
            self.assertEqual(len(source_clicks),3)
            click=next(route for route in source_clicks if 'mapClick' not in route['steps'][0])
            crossings=[step for step in walk['steps'] if 'destination' in step]
            self.assertEqual(len(crossings),1);self.assertEqual(crossings[0]['destination'],destination)
            portal=next(p for p in g.portals if p.source==source and (p.x,p.y)==tuple(crossings[0]['tile']))
            target=tuple(click['steps'][0]['tile']);arrival=(portal.destination_x,portal.destination_y)
            self.assertEqual(click['start'],walk['start'])
            self.assertEqual(click['steps'][0]['destination'],destination)
            self.assertTrue(click['steps'][0]['clickNeighbor'])
            self.assertNotIn(target,g.audit.automatic[destination])
            self.assertTrue(3<=click['targetSteps']<=12)
            self.assertEqual(g.audit.exact_path(destination,arrival,target)[-1],target)
            self.assertEqual(walk['steps'][-1]['tile'],list(target))
            self.assertEqual(walk['id'],f'a--b-roadless-{source}-roadless-crossing')
            self.assertEqual(click['id'],f'a--b-roadless-{source}-roadless-click')
            self.assertEqual({route['steps'][0].get('mapClick') for route in source_clicks},{None,'full_map','minimap'})
            self.assertEqual({tuple(route['steps'][0]['tile']) for route in source_clicks},{target})
            self.assertEqual({route['steps'][0]['destination'] for route in source_clicks},{destination})
            self.assertTrue(all(route['steps'][0]['clickNeighbor'] for route in source_clicks))
            self.assertEqual(len({route['id'] for route in source_clicks}),3)
            self.assertEqual(len({route['steps'][0]['capture'] for route in source_clicks}),3)
            self.assertEqual(len({route['steps'][0]['label'] for route in source_clicks}),3)

    def test_roadless_selection_deterministically_tries_an_alternative_unframeable_lane(self):
        surface=lambda region,tile:None if 40<=tile[1]<=60 else 0.0
        routes=[]
        for _ in range(2):
            g=self.roadless_generator(surface);centre,shoulders,clicks=g.borders()
            self.assertEqual(g.errors,[]);self.assertEqual((len(centre),len(shoulders),len(clicks)),(2,0,6))
            chosen=[]
            for route in centre:
                crossing=next(step for step in route['steps'] if 'destination' in step)
                self.assertNotEqual(crossing['tile'][1],50)
                chosen.append((route['id'],route['start'],crossing['tile'],route['steps'][-1]['tile']))
            routes.append(chosen)
        self.assertEqual(routes[0],routes[1])

    def test_roadless_selection_records_actionable_error_when_all_candidates_fail(self):
        g=self.roadless_generator(lambda region,tile:None)
        centre,shoulders,clicks=g.borders()
        self.assertEqual((centre,shoulders,clicks),([],[],[]));self.assertEqual(len(g.lanes),6)
        errors=[item['error'] for item in g.errors if 'roadless representative' in item['route']]
        self.assertEqual(len(errors),2)
        self.assertTrue(all('no usable roadless representative' in error and 'camera margin' in error
                            for error in errors))


@unittest.skipUnless(os.environ.get('ELORIA_PROOF_SERVER'), 'Set ELORIA_PROOF_SERVER to run paired path regressions')
class PathProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R=P.runtime(Path(os.environ['ELORIA_PROOF_SERVER']))

    def world(self,width=100,height=100):
        w=self.R['world'].World.__new__(self.R['world'].World)
        w.settings=SimpleNamespace(max_walk_height_change=2,portal_activation_distance=8)
        w.maps={}
        w.collision_maps={name:self.R['collision'].with_step_mask(
            self.R['collision'].CollisionMap(width,height,bytes([10])*(width*height)),2) for name in ('a','b')}
        w.sessions,w.animals,w.animals_by_map=[],{},{}
        w.npcs={};w._footprint_collision={}
        return w

    def portal(self,source,x,y,destination,dx,dy):
        return self.R['maps'].Portal(source,x,y,destination,dx,dy)

    def configure_border_fixture(self,g):
        g.specs={'a':{'arrival':[2,50],'serverOrigin':[0,0],'translation':[0,0,0]},
                 'b':{'arrival':[90,50],'serverOrigin':[0,0],'translation':[72,0,0]}}
        g.surface_height=lambda region,tile:0.0

    def test_new_ferry_fixtures_require_actual_dock_access_and_safe_return(self):
        g=P.Generator.__new__(P.Generator);g.chunk_mode=True;g.world=self.world(24,12)
        g.specs={'a':{'arrival':[2,5],'serverOrigin':[1,9],'translation':[-20,0,40]},
                 'b':{'arrival':[2,5],'serverOrigin':[3,12],'translation':[100,0,300]}}
        g.publication={'connections':[{'id':'a-b-ferry','type':'ferry','ends':[
            {'region':name,'tile':[10,5],'arrival':[8,5]} for name in ('a','b')]}]}
        g.portals=[self.portal('a',10,5,'b',8,5),self.portal('b',10,5,'a',8,5)]
        g.audit=P.WalkAudit(g.world,g.portals);g.errors=[]
        routes=g.ferry_routes();self.assertEqual(len(routes),2);self.assertFalse(g.errors)
        self.assertTrue(all(len([s for s in r['steps'] if 'destination' in s])==2 for r in routes))
        self.assertTrue(all(r['travelMode']=='ferry' for r in routes))
        expected={'a':[-12.5,43.5],'b':[105.5,306.5]}
        for route in routes:
            for step in route['steps']:
                if 'destination' not in step:continue
                self.assertEqual(step['expectedArrival'],{'map':step['destination'],'tile':[8,5],
                    'global':expected[step['destination']],'units':'metres','point':'tile-center'})
        self.assertTrue(all(not leg['syntheticBlockers'] for leg in g.audit.legs))
        g.world.npcs={1:(SimpleNamespace(x=8,y=5),'b',0,())};g.errors=[]
        self.assertEqual(g.ferry_routes(),[])
        self.assertTrue(any('ferry arrival cannot safely depart' in e['error'] for e in g.errors))
        g.world.npcs={};g.errors=[]
        raw=bytearray([10])*288
        for y in range(12):raw[y*24+9]=0
        g.world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(24,12,bytes(raw)),2)
        self.assertEqual(g.ferry_routes(),[])
        self.assertTrue(g.errors)

    def test_waypoints_avoid_incidental_door_on_real_unmodified_paths(self):
        world=self.world(24,12)
        door=self.portal('a',10,5,'b',3,3)
        audit=P.WalkAudit(world,[door])
        with self.assertRaisesRegex(P.AuditError,'unintended portal'):
            audit.exact_path('a',(2,5),(20,5))
        steps=audit.movement('a',(2,5),(20,5),'public street')
        self.assertGreater(len(steps),1)
        current=(2,5)
        for step in steps:
            target=tuple(step['tile'])
            actual=world.find_path('a',current,target,world.blocking_tiles('a'))
            self.assertEqual(actual[-1],target)
            self.assertNotIn((10,5),actual)
            current=target
        self.assertEqual(current,(20,5))
        self.assertTrue(all(not leg['syntheticBlockers'] for leg in audit.legs))

    def test_long_route_splits_before_server_512_step_limit(self):
        world=self.world(600,12)
        audit=P.WalkAudit(world,[],max_leg=64)
        with self.assertRaisesRegex(P.AuditError,'512-step'):
            audit.exact_path('a',(1,5),(590,5))
        steps=audit.movement('a',(1,5),(590,5),'long road')
        self.assertEqual(steps[-1]['tile'],[590,5])
        self.assertTrue(all(leg['steps']<=64 for leg in audit.legs))
        self.assertTrue(all(step['walkTimeout']>=20 for step in steps))

    def test_direct_request_measures_truncation_without_repairing_it(self):
        world=self.world(600,12)
        method=type(world).find_path
        audit=P.WalkAudit(world,[],max_leg=64)
        result=audit.one_request('a',(1,5),(590,5),'one user click')
        self.assertEqual(result['requestedSteps'],589)
        self.assertEqual(result['returnedSteps'],512)
        self.assertEqual(result['waypointsAdded'],0)
        self.assertTrue(result['diagnosticUncappedMeasurement'])
        self.assertFalse(result['passes'])
        self.assertIs(type(world).find_path,method)
        self.assertEqual(len(world.find_path('a',(1,5),(590,5),set())),512)
        continued=audit.renewed_intent('a',(1,5),(590,5))
        self.assertTrue(continued['passes'])
        self.assertEqual(continued['renewals'],1)
        self.assertEqual(continued['executedSteps'],589)
        self.assertEqual(continued['fixtureWaypoints'],0)
        self.assertTrue(all(s['requestedTarget']==[590,5] for s in continued['segments']))
        self.assertFalse(audit.renewed_intent('a',(1,5),(590,5),maximum_renewals=0)['passes'])

    def test_visual_shore_route_follows_actual_bfs_and_exposes_incidental_door(self):
        world=self.world()
        world.collision_maps['c']=world.collision_maps['a']
        def end(region,x):
            return {'map':region,'position':[x+.5,0,-50.5],
                    'coordinateTransform':{'serverOrigin':[0,0],'invertServerY':True}}
        links=[{'id':'a-b','seamless':True,'ends':[end('a',82),end('b',8)]},
               {'id':'b-c','seamless':True,'ends':[end('b',82),end('c',8)]}]
        portals=[self.portal('a',82,50,'b',10,50),self.portal('b',8,50,'a',80,50),
                 self.portal('b',82,50,'c',10,50),self.portal('c',8,50,'b',80,50),
                 self.portal('b',45,50,'room',3,3)]
        g=P.Generator.__new__(P.Generator)
        g.links,g.portals,g.world=links,portals,world
        g.visual_links=[{'id':'shore-a-c','ends':[{'map':'a'},{'map':'c'}]}]
        g.specs={'a':{},'b':{},'c':{}}
        g.audit=P.WalkAudit(world,portals,max_leg=2)
        g.errors=[]
        routes=g.visual_road_requests()
        self.assertEqual([r['maps'] for r in routes],[['a','b','c'],['c','b','a']])
        self.assertEqual(len(g.audit.requests),2)
        self.assertEqual(len(g.errors),2)
        for item in g.audit.requests:
            self.assertEqual(item['requestedSteps'],72)
            self.assertEqual(item['unintendedPortals'],[[45,50]])
            self.assertEqual(item['waypointsAdded'],0)
            self.assertFalse(item['syntheticBlockers'])
            self.assertFalse(item['passes'])
        self.assertEqual(g.audit.legs,[])  # The fixture waypoint limit is irrelevant here.

    def test_actual_elm_storage_body_and_npc_occupancy_reject_false_standing_points(self):
        world=self.world(12,12)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'a.elm'
            path.write_bytes(struct.pack('<4sIIII',b'elmf',2,2,0,20)+bytes([10])*144)
            floor=self.R['collision'].load_elm_collision(path)
        world.collision_maps['a']=self.R['collision'].with_storage_collision(floor,[(6,6)])
        npc=SimpleNamespace(x=3,y=3)
        world.npcs={1:(npc,'a',0,())}
        audit=P.WalkAudit(world,[])
        for target in ((5,5),(7,7),(3,3)):
            with self.assertRaisesRegex(P.AuditError,'occupied standing'):
                audit.exact_path('a',(1,1),target)
        target=audit.approach('a',(1,1),(6,6),radius=4)
        self.assertTrue(audit.standing('a',target))
        self.assertLessEqual(max(abs(target[0]-6),abs(target[1]-6)),4)

    def test_inventory_flood_matches_staged_height_and_diagonal_rules(self):
        world=self.world(6,6)
        for masked in (False,True):
            for side in (71,80):
                raw=bytearray(36)
                for x,y,height in ((1,1,70),(2,1,side),(1,2,80),(2,2,70)):
                    raw[y*6+x]=height
                collision=self.R['collision'].CollisionMap(6,6,bytes(raw))
                world.collision_maps['a']=(self.R['collision'].with_step_mask(collision,2) if masked else collision)
                flood=P.AccessFlood(world,'a',(1,1))
                path=world.find_path('a',(1,1),(2,2),set())
                self.assertEqual(flood.reachable((2,2)),bool(path and path[-1]==(2,2)))
                self.assertEqual(flood.reachable((2,2)),side==71)
                if side==71:self.assertEqual(flood.steps[2*6+2],2)  # The diagonal itself cuts a high corner.

    def test_all_content_inventory_reports_islands_and_runtime_approaches_separately(self):
        world=self.world(30,12)
        raw=bytearray(360)
        for x in range(1,29):raw[5*30+x]=10
        world.collision_maps['a']=self.R['collision'].with_step_mask(
            self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        npc=SimpleNamespace(x=4,y=5,name='Guide')
        world.npcs={1:(npc,'a',0,())}
        # A nearby guide can be spoken to; his body blocks the narrow route.
        g=P.Generator.__new__(P.Generator)
        g.world,g.specs=world,{'a':{'arrival':[1,5]}}
        g.audit=P.WalkAudit(world,[])
        g.interactives={1:SimpleNamespace(map_id='a',object_id=1,role='information',x=3,y=5)}
        g.resources={2:SimpleNamespace(map_id='a',object_id=2,resource='Pearl',x=12,y=5)}
        g.spawns=[SimpleNamespace(map_id='a',creature='crab',x=18,y=5)]
        report=g.content_inventory()
        self.assertFalse(report['allAccessible'])
        self.assertEqual(report['counts'],{'npc':1,'interactive':1,'resource':1,'spawn':1})
        self.assertTrue(report['regions']['a']['entries'][0]['accessible'])
        self.assertTrue(all(i['reason']=='static NPC bodies block the approach' for i in report['issues']))
        world.npcs={}
        g.audit=P.WalkAudit(world,[self.portal('a',7,5,'room',3,3)])
        report=g.content_inventory()
        self.assertTrue(all(i['reason']=='access requires crossing an automatic portal' for i in report['issues']))
        raw[5*30+7]=0
        world.collision_maps['a']=self.R['collision'].with_step_mask(
            self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        report=g.content_inventory()
        self.assertTrue(all('no primary-arrival geometry connection' in i['reason'] for i in report['issues']))
        self.assertTrue(all(i['nearestReachable']['tile']==[6,5] for i in report['issues']))
        self.assertTrue(all(i['inheritance'].startswith('unverified') for i in report['issues']))

    def test_actual_package_digest_and_lod_metadata_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manifest=root/'world.json'
            data={'asset':{'glb':'world.glb','serverCells':12},'coordinateTransform':{'serverOrigin':[0,0]},
                  'collision':{'binary':'collision.bin'},'runtimePopulation':{'npcs':[]}}
            manifest.write_text(json.dumps(data),encoding='utf-8')
            (root/'world.glb').write_bytes(b'actual main mesh bytes');(root/'collision.bin').write_bytes(b'collision bytes')
            g=P.Generator.__new__(P.Generator)
            g.inputs={};g.members={'a':{'path':manifest,'canonical':'a','owner':'a'}}
            g.registry={'a':{'coordinateTransform':{'serverOrigin':[0,0],'origin':[0,0,0]}}}
            g.world=self.world(12,12);g.portals=[]
            g.manifest={'maps':[{'id':'a','server_cells':12,'portals':[],'packageSha256':P.digest_for(manifest)}]}
            self.assertTrue(g.publication_integrity()['passed'])
            g.inputs={};g.manifest['maps'][0]['packageSha256']='a'*64
            with self.assertRaisesRegex(P.AuditError,'actual package bytes'):g.publication_integrity()
            g.inputs={};g.manifest['maps'][0]['packageSha256']=P.digest_for(manifest)
            (root/'world-lod2.glb').write_bytes(b'LOD mesh bytes')
            lod=dict(data,asset={'glb':'world-lod2.glb','serverCells':12},runtimePopulation={'npcs':[{'id':99}]})
            (root/'world-lod2.json').write_text(json.dumps(lod),encoding='utf-8')
            with self.assertRaisesRegex(P.AuditError,'stale LOD runtimePopulation'):g.publication_integrity()
            g.inputs={};lod['runtimePopulation']=data['runtimePopulation']
            (root/'world-lod2.json').write_text(json.dumps(lod),encoding='utf-8')
            self.assertEqual(g.publication_integrity()['lodManifestsChecked'],1)
            (root/'world.glb').write_bytes(b'changed mesh during audit')
            with self.assertRaisesRegex(P.AuditError,'changed between reads'):g.publication_integrity()

    def test_all24_published_pairs_require_exact_finite_edge_coverage(self):
        g=P.Generator.__new__(P.Generator)
        names=[str(i) for i in range(12)]
        g.specs={n:{'translation':[int(n)*100,0,0],'serverOrigin':[0,0]} for n in names}
        segments=[];links=[]
        for index,pair in enumerate(list(itertools.combinations(names,2))[:24]):
            lines=[[[index*7,0],[index*7,2]],[[index*7,4],[index*7,6]]]
            segments.extend({'regions':list(pair),'start':line[0],'end':line[1]} for line in lines)
            ends=[]
            for name in pair:
                x=g.specs[name]['translation'][0]
                ends.append({'map':name,'coordinateTransform':{'serverOrigin':[0,0]},
                    'frame':{'geometryMode':'continent-owned-v1','anchor':[index*7-x,0,3]},
                    'preloadEdges':[[[p[0]-x,p[1]] for p in line] for line in lines]})
            links.append({'id':'-'.join(pair),'ends':ends,'visualOnly':index>=17})
        g.geography={'boundaryHeightField':{'segments':segments}}
        g.links,g.visual_links=links[:17],links[17:]
        self.assertEqual(g.graph_integrity()['physicalPairs'],24)
        end=g.visual_links[-1]['ends'][0]
        end['preloadEdges']=[[end['preloadEdges'][0][0],end['preloadEdges'][1][1]]]
        with self.assertRaisesRegex(P.AuditError,'finite preload edges differ'):g.graph_integrity()
        with self.assertRaises(P.AuditError):P.finite_span_union([[[0,0],[float('inf'),1]]])

    def test_family_sections_use_actual_incoming_arrivals_and_never_seed_their_exits(self):
        world=self.world(30,12);raw=bytearray(360)
        for x in list(range(2,6))+list(range(20,24)):raw[5*30+x]=10
        world.collision_maps['b']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        portals=[self.portal('a',3,5,'b',2,5),self.portal('b',5,5,'a',4,5),
                 self.portal('a',10,5,'b',20,5),self.portal('b',23,5,'a',11,5)]
        g=P.Generator.__new__(P.Generator)
        g.world,g.members,g.specs=world,{'a':{},'b':{}},{'a':{'arrival':[1,5]}}
        g.manifest={'maps':[{'id':'a','arrival':[1,5]},{'id':'b','arrival':[2,5]}]}
        g.portals=portals;g.audit=P.WalkAudit(world,portals);g.errors=[]
        self.assertTrue(g.family_portal_access()['passed'])
        g.portals=[p for p in portals if not (p.source=='a' and p.x==10)]
        g.audit=P.WalkAudit(world,g.portals);g.errors=[]
        report=g.family_portal_access()
        self.assertFalse(report['passed'])
        self.assertTrue(any(i.get('tile')==[23,5] and 'disconnected' in i['reason'] for i in report['issues']))
        g.portals=portals;world.npcs={1:(SimpleNamespace(x=2,y=5),'b',0,())}
        g.audit=P.WalkAudit(world,portals);g.errors=[]
        report=g.family_portal_access()
        self.assertTrue(any(i.get('tile')==[2,5] and 'arrival' in i['reason'] for i in report['issues']))

    def test_arrival_on_return_portal_can_depart_but_cannot_cross_another_exit(self):
        world=self.world(20,12)
        doors=[self.portal('b',3,5,'a',3,5),self.portal('b',5,5,'a',8,5)]
        audit=P.WalkAudit(world,doors)
        departure=audit.arrival_departure('b',(3,5))
        self.assertIsNotNone(departure)
        self.assertEqual(audit.exact_path('b',(3,5),departure),[departure])
        with self.assertRaisesRegex(P.AuditError,'unintended portal'):
            audit.exact_path('b',(3,5),(8,5))
        flood=P.AccessFlood(world,'b',(3,5),terminals=audit.automatic['b'],arrival_departure=True)
        self.assertTrue(flood.reachable(departure))
        self.assertFalse(flood.reachable((5,5)))
        # Pin the production contract: arrivals do not trigger an automatic
        # exit until a subsequent move has executed a step.
        import inspect
        self.assertNotIn('check_portal(',inspect.getsource(type(world).change_map))
        self.assertIn('await self.check_portal(session)',inspect.getsource(type(world).move))
        world.npcs={1:(SimpleNamespace(x=3,y=5),'b',0,())}
        self.assertIsNone(audit.arrival_departure('b',(3,5)))

    def test_family_does_not_seed_room_from_an_unreachable_incoming_door(self):
        world=self.world(30,12)
        raw=bytearray(world.collision_maps['a'].heights)
        for y in range(12):raw[y*30+15]=0
        world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        portals=[self.portal('a',23,5,'b',3,5),self.portal('b',3,5,'a',23,5)]
        g=P.Generator.__new__(P.Generator)
        g.world,g.members,g.specs=world,{'a':{},'b':{}},{'a':{}}
        g.manifest={'maps':[{'id':'a','arrival':[2,5]},{'id':'b','arrival':[3,5]}]}
        g.portals=portals;g.audit=P.WalkAudit(world,portals);g.errors=[]
        report=g.family_portal_access()
        self.assertFalse(report['passed'])
        self.assertFalse(any(p['map']=='b' for p in report['entryProvenance']))
        self.assertTrue(any(i['map']=='b' and 'disconnected' in i['reason'] for i in report['issues']))

    def test_outbound_family_portal_requires_real_destination_floor_and_departure(self):
        world=self.world(20,12)
        world.maps={'a':SimpleNamespace(file='a.elm'),'b':SimpleNamespace(file='b.elm')}
        g=P.Generator.__new__(P.Generator)
        g.world,g.members,g.specs=world,{'a':{}},{'a':{}}
        g.manifest={'maps':[{'id':'a','arrival':[2,5]}]}
        g.portals=[self.portal('a',10,5,'b',3,5),self.portal('b',5,5,'a',10,5)]
        g.audit=P.WalkAudit(world,g.portals);g.errors=[]
        report=g.family_portal_access()
        self.assertTrue(report['passed'])
        self.assertEqual(report['mapCount'],1)
        self.assertFalse(report['portalChecks'][0]['destinationInServedFamily'])
        self.assertEqual(report['portalChecks'][0]['externalBoundary']['steps'],2)
        world.npcs={1:(SimpleNamespace(x=5,y=5),'b',0,())};g.errors=[]
        self.assertFalse(g.family_portal_access()['passed'])
        world.npcs={};g.audit=P.WalkAudit(world,g.portals)
        world.collision_maps['b']=self.R['collision'].with_storage_collision(world.collision_maps['b'],[(5,5)])
        self.assertFalse(g.family_portal_access()['passed'])
        del world.collision_maps['b'];g.errors=[]
        self.assertFalse(g.family_portal_access()['passed'])

    def instance_waystone_fixture(self):
        world=self.world(30,12)
        # Decorative stone is isolated; its approach is in the real entry floor.
        raw=bytearray(360)
        for y in range(2,9):
            for x in range(2,9):raw[y*30+x]=10
        raw[5*30+11]=10
        world.collision_maps['b']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        portal=self.portal('b',11,5,'a',3,5)
        g=P.Generator.__new__(P.Generator)
        g.world,g.members,g.specs=world,{'a':{},'b':{}},{'a':{}}
        g.manifest={'maps':[{'id':'a','arrival':[2,5]},{'id':'b','arrival':[3,5]}]}
        g.portals=[portal];g.audit=P.WalkAudit(world,g.portals);g.errors=[]
        g.interactives={('b',None):SimpleNamespace(role='waystone',x=11,y=5)}
        g.instance_entries=[{'definition':'real.def','exitIdentity':'bound-exit','keeper':'Keeper',
                             'source':'a','keeperTile':[5,5],'destination':'b','arrival':[3,5],
                             'exitMap':'a','exitTile':[4,5]}]
        g.instance_exits={'bound-exit':{'source':{'map':'a'},'tile':[4,5]}}
        return g

    def test_instance_exit_is_independent_and_waystone_uses_real_interaction_range(self):
        g=self.instance_waystone_fixture();report=g.family_portal_access()
        self.assertTrue(report['passed'])
        self.assertEqual(report['portalChecks'][0]['sourceApproach'],[8,5])
        self.assertEqual(report['portalChecks'][0]['arrival'],[3,5])  # maps.txt retained separately
        self.assertEqual(report['portalChecks'][0]['activeInstanceReturns'][0]['tile'],[4,5])
        self.assertTrue(report['instanceExitChecks'][0]['publishedHubAccessible'])
        self.assertTrue(any(e['via']=='reachable instance keeper' for e in report['entryProvenance']))

    def test_instance_exit_missing_or_mismatched_binding_fails_closed(self):
        for mutation in ('missing','tile','map','unused'):
            g=self.instance_waystone_fixture()
            if mutation=='missing':g.instance_exits.clear()
            elif mutation=='tile':g.instance_entries[0]['exitTile']=[6,5]
            elif mutation=='map':g.instance_exits['bound-exit']['source']['map']='b'
            else:g.instance_exits['unused']=copy.deepcopy(g.instance_exits['bound-exit'])
            with self.subTest(mutation=mutation),self.assertRaises(P.AuditError):g.family_portal_access()

    def test_actual_instance_exit_blocked_trigger_or_disconnected_fails(self):
        for mutation in ('blocked','trigger','disconnected','no-departure'):
            g=self.instance_waystone_fixture();world=g.world
            if mutation=='trigger':
                g.portals.append(self.portal('a',4,5,'b',3,5));g.audit=P.WalkAudit(world,g.portals)
            else:
                raw=bytearray(world.collision_maps['a'].heights)
                if mutation=='blocked':raw[5*30+4]=0
                elif mutation=='disconnected':
                    for y in range(12):raw[y*30+3]=0
                else:
                    for y in range(4,7):
                        for x in range(3,6):raw[y*30+x]=0
                    raw[5*30+4]=10
                world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
            with self.subTest(mutation=mutation):self.assertFalse(g.family_portal_access()['passed'])

    def test_instance_keeper_approach_and_waystone_range_cannot_be_bypassed(self):
        for mutation in ('keeper','waystone'):
            g=self.instance_waystone_fixture();world=g.world
            if mutation=='keeper':
                raw=bytearray(world.collision_maps['a'].heights)
                for y in range(12):raw[y*30+10]=0
                world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
                g.instance_entries[0]['keeperTile']=[20,5]
            else:world.settings.portal_activation_distance=2
            with self.subTest(mutation=mutation):self.assertFalse(g.family_portal_access()['passed'])

    def test_distinct_maps_row_destination_still_requires_safe_actual_floor(self):
        g=self.instance_waystone_fixture();world=g.world
        raw=bytearray(world.collision_maps['a'].heights);raw[5*30+3]=0
        world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(30,12,bytes(raw)),2)
        report=g.family_portal_access()
        self.assertFalse(report['passed'])
        self.assertTrue(any(i['reason']=='family portal destination cannot depart safely' for i in report['issues']))

    def test_authored_curve_merge_and_lane_cannot_fall_back_to_obstructed_straight_strip(self):
        frame={'id':'a--b','anchor':[81.5,0,-50.5],'outward':[1,0]}
        contract={'schemaVersion':1,'direction':'inland-to-seam','stationHeight':'bed',
                  'laneHalfWidth':3,'physicalHalfWidth':4.25,'commonBoundaryLength':3,'walkingBias':.03,
                  'collarStartIndex':0,'stations':[[36.5,0,-50.5],[45.5,0,-60.5],
                  [65.5,0,-60.5],[76.5,0,-50.5],[81.5,0,-50.5]]}
        package={'streamingBorders':[dict(frame,approachCenterline=contract)]}
        merged=P.Generator.approach_frame(frame,package,'registry-pair-id')
        self.assertNotIn('approachCenterline',frame)
        self.assertEqual(merged['approachCenterline'],contract)
        with self.assertRaisesRegex(P.AuditError,'anchor differs'):
            P.Generator.approach_frame(dict(frame,anchor=[82,0,-50.5]),package,'a--b')
        world=self.world();raw=bytearray(world.collision_maps['a'].heights)
        for x in range(50,62):
            for y in range(46,55):raw[y*100+x]=0
        world.collision_maps['a']=self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(100,100,bytes(raw)),2)
        portals=[]
        for offset in range(-3,4):
            portals.extend([self.portal('a',82,50+offset,'b',10,50+offset),
                            self.portal('b',8,50+offset,'a',80,50+offset)])
        g=P.Generator.__new__(P.Generator)
        g.world,g.portals=world,portals;g.audit=P.WalkAudit(world,portals)
        self.configure_border_fixture(g)
        g.links=[{'id':'a--b','ends':[{'map':'a','frame':merged,'coordinateTransform':{'serverOrigin':[0,0]}},
                                    {'map':'b','frame':{'outward':[-1,0]}}]}]
        g.errors,g.lanes=[],[];g.borders()
        self.assertEqual(g.errors,[])
        self.assertEqual(sum(l['authoredCurve'] for l in g.lanes),7)
        g.links[0]['ends'][0]['frame']=frame;g.errors=[];g.lanes=[];g.borders()
        self.assertTrue(any('blocked receiving strip' in e['error'] for e in g.errors))

    def test_four_service_plan_preserves_three_objects_and_real_tutorial_conversation(self):
        world=self.world(40,16);world.collision_maps['four_gates']=world.collision_maps['a']
        world.npcs={9:(SimpleNamespace(name='Wayfinder Nesh',x=24,y=6),'four_gates',0,())}
        world.npc_roles={9:'tutorial'}
        g=P.Generator.__new__(P.Generator)
        g.world=world;g.specs={'four_gates':{'arrival':[2,6]}}
        g.members={'four_gates':{'path':Path('unused.json')}}
        plan=[{'role':r} for r in ('information','storage','crafting_station')]
        g.json_input=lambda path:{'contentLayout':{'services':plan}}
        g.interactives={i:SimpleNamespace(map_id='four_gates',object_id=i,role=row['role'],x=6+i*5,y=6,text='Actual service')
                        for i,row in enumerate(plan)}
        g.resources={1:SimpleNamespace(map_id='four_gates',object_id=77,resource='Copper',x=30,y=6)}
        g.audit=P.WalkAudit(world,[]);g.coverage={}
        route=g.services('four_gates')
        self.assertEqual([s['useObject'] for s in route['steps'] if 'useObject' in s],[0,1,2])
        conversation=next(s for s in route['steps'] if 'useNpc' in s)
        self.assertEqual(conversation['useNpc'],'Wayfinder Nesh')
        self.assertEqual(conversation['expectDialogueText'],'You already know how to find your feet.')
        self.assertEqual([r['role'] for r in g.coverage['four_gates']['services']],
                         ['information','storage','crafting_station','training'])
        world.npc_roles[9]='dialogue'
        with self.assertRaisesRegex(P.AuditError,'actual Wayfinder Nesh'):g.services('four_gates')
        plan.pop()
        with self.assertRaisesRegex(P.AuditError,'omits a core service'):g.services('four_gates')

    def test_all_seven_reciprocal_lanes_and_distinct_click_targets(self):
        world=self.world()
        portals=[]
        for offset in range(-3,4):
            portals.extend([self.portal('a',82,50+offset,'b',10,50+offset),
                            self.portal('b',8,50+offset,'a',80,50+offset)])
        g=P.Generator.__new__(P.Generator)
        g.world,g.portals=world,portals
        g.audit=P.WalkAudit(world,portals)
        self.configure_border_fixture(g)
        g.links=[{'id':'a--b','ends':[{'map':'a','frame':{'outward':[1,0]}},
                                     {'map':'b','frame':{'outward':[-1,0]}}]}]
        g.errors,g.lanes=[],[]
        centre,shoulders,clicks=g.borders()
        self.assertEqual(g.errors,[])
        self.assertEqual(len(g.lanes),14)
        self.assertEqual((len(centre),len(shoulders),len(clicks)),(1,2,4))
        self.assertTrue(all('roadless' not in route['id'] for route in centre+shoulders+clicks))
        self.assertEqual([s['destination'] for s in centre[0]['steps'] if 'destination' in s],['b','a'])
        far=[r['steps'][0]['tile'] for r in clicks if r['map']=='a']
        self.assertEqual(far,[[12,50],[22,50]])
        self.assertTrue(all(r['steps'][0]['clickNeighbor'] for r in clicks))

    def test_lane_failure_cannot_be_hidden_by_a_path_detour(self):
        world=self.world()
        portals=[self.portal('a',82,50+i,'b',10,50+i) for i in range(-3,4)]
        portals += [self.portal('b',8,50+i,'a',80,50+i) for i in range(-3,4)]
        raw=bytearray(world.collision_maps['a'].heights);raw[47*100+60]=0
        world.collision_maps['a']=self.R['collision'].CollisionMap(100,100,bytes(raw))
        g=P.Generator.__new__(P.Generator)
        g.world,g.portals=world,portals;g.audit=P.WalkAudit(world,portals)
        self.configure_border_fixture(g)
        g.links=[{'id':'a--b','ends':[{'map':'a','frame':{'outward':[1,0]}},
                                     {'map':'b','frame':{'outward':[-1,0]}}]}]
        g.errors,g.lanes=[],[]
        g.borders()
        self.assertTrue(any('blocked receiving strip' in e['error'] for e in g.errors))


if __name__=='__main__':unittest.main()
