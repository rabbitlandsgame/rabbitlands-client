"""Build progress and composition freshness, the two records an editor reads.

Neither may ever stop a build: progress warns on an unwritable path and the
freshness report answers with the same digests the stages refuse to work
without, including digests a sibling branch recorded that this one cannot map.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import build_continent as B
import build_progress as P
import audit_continent as A
import river_crossings as RC


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ProgressRecordTests(unittest.TestCase):
    def test_composition_certificate_covers_fixed_shaping_data(self):
        certified={B.source_key(path) for path in B.composition_certificate_paths()}
        self.assertLessEqual(B.shaping_source_keys(),certified)
        self.assertEqual(set(B.SHAPING_SOURCES),set(A.SHAPING_SOURCES))
        self.assertEqual(set(B.EXPORT_SOURCES),A.EXPORT_SOURCES)
        for name in ('saved-seam-grey-whitehorn-v1.json','saved-seam-post-support-v1.json'):
            self.assertIn(B.source_key(B.HERE/name),certified)

    def test_saved_seam_retries_an_infeasible_terminal_on_neighbor_owned_ground(self):
        class World:
            ids=['neighbor','sunmane'];routing=[]
            def hub(self,region):return np.array([0.,0.])
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def height_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=float)
            def solids_at_ends(self,point):return None
            def road_profile(self,path):
                points=np.asarray(path,float)
                distance=np.linalg.norm(np.diff(points,axis=0),axis=1)
                return points,np.r_[0.,np.cumsum(distance)*.1]
        world=World();world.routing=[]
        def route(_world,legs,*args,**kwargs):
            _world.routing.append({'earthworks':{'excessAt':[[96.,0.]] if len(legs)==2 else []}})
            return np.asarray(legs,float)
        link={'id':'neighbor--sunmane','regions':['neighbor','sunmane']}
        path,report=B.route_saved_seam_neighbour(world,link,'neighbor',
            np.array([100.,0.]),np.array([1.,0.]),route,lambda w:None,lambda w,c:None,start=np.array([0.,0.]))
        self.assertEqual(report['attempts'],3);self.assertEqual(report['waypoint'],[96.,24.])
        self.assertEqual(path[-2:].tolist(),[[100.,0.],[104.,0.]])

    def test_saved_seam_tries_the_certified_deeper_straight_corridor(self):
        class World:
            ids=['neighbor','saved'];routing=[]
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def height_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=float)
            def solids_at_ends(self,point):return None
            def road_profile(self,path):
                points=np.asarray(path,float)
                return points,np.zeros(len(points))
        world=World();attempts=[]
        def route(_world,legs,*args,**kwargs):
            attempts.append(np.asarray(legs,float));_world.routing.append({'earthworks':{'excessAt':[]}})
            return attempts[-1]
        def feasible(_world,path,_anchor,_routing):
            # The published Grey/Whitehorn approach reaches the seam from the
            # straight 12 m terminal; lateral candidates are not substitutes.
            return any(np.allclose(point,[88.,0.]) for point in np.asarray(path,float)) and \
                not any(abs(point[1])>1e-9 for point in np.asarray(path,float))
        link={'id':'neighbor--saved','regions':['neighbor','saved']}
        with patch.object(B,'_seam_approach_feasible',side_effect=feasible):
            _path,report=B.route_saved_seam_neighbour(
                world,link,'neighbor',np.array([100.,0.]),np.array([1.,0.]),route,
                lambda _world:None,lambda _world,_claims:None,start=np.array([0.,0.]))
        self.assertEqual(report['depth'],12.)
        self.assertIsNone(report['waypoint'])
        self.assertTrue(any(np.allclose(call[-1],[88.,0.]) for call in attempts))

    def test_saved_seam_rejects_a_profiled_route_with_a_steep_emitted_ground_station(self):
        class World:
            ids=['neighbor','saved']
            def __init__(self):self.routing=[]
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def height_at(self,x,z):
                x=np.asarray(x);z=np.asarray(z)
                return np.where((x>=90.)&(x<=92.)&(np.abs(z)<1.),2.,0.)
            def solids_at_ends(self,point):return None
            def road_profile(self,path):
                path=np.asarray(path,float);dense=[]
                for a,b in zip(path,path[1:]):
                    count=max(1,int(np.ceil(np.linalg.norm(b-a)/2.)))
                    dense.extend(a+(b-a)*t for t in np.arange(count)/count)
                points=np.vstack((dense,path[-1]))
                return points,np.zeros(len(points))
        world=World();attempts=[]
        def route(_world,legs,*args,**kwargs):
            terminal=np.asarray(legs[-1],float);attempts.append(terminal.tolist())
            _world.routing.append({'earthworks':{'excessAt':[]}})
            if terminal[0]==91.:
                return np.asarray([legs[0],terminal],float)
            return np.asarray([legs[0],[0.,10.],[terminal[0],10.],terminal],float)
        link={'id':'neighbor--saved','regions':['neighbor','saved']}
        with patch.object(B,'_reconcile_terminal_reroute'):
            _path,report=B.route_saved_seam_neighbour(
                world,link,'neighbor',np.array([100.,0.]),np.array([1.,0.]),route,
                lambda _world:None,lambda _world,_claims:None,start=np.array([0.,0.]))
        self.assertEqual(report['attempts'],2)
        self.assertEqual(report['depth'],4.)
        self.assertEqual(attempts[:2],[[91.,0.],[96.,0.]])

    def test_saved_seam_can_follow_a_short_owned_contour_at_the_ring(self):
        class World:
            ids=['neighbor','saved']
            def __init__(self):self.routing=[]
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def height_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=float)
            def solids_at_ends(self,point):return None
            def road_profile(self,path):
                points=np.asarray(path,float)
                return points,np.zeros(len(points))
        world=World();attempts=[]
        def route(_world,legs,*args,**kwargs):
            attempts.append(np.asarray(legs,float))
            _world.routing.append({'earthworks':{'excessAt':[]}})
            return attempts[-1]
        def feasible(_world,path,_anchor,_routing):
            return any(np.allclose(point,[102.,6.]) for point in np.asarray(path,float))
        link={'id':'neighbor--saved','regions':['neighbor','saved']}
        with (patch.object(B,'_owned_approach',side_effect=lambda _w,_r,waypoint,_end:
                    np.allclose(waypoint,[102.,6.])),
              patch.object(B,'_seam_approach_feasible',side_effect=feasible),
              patch.object(B,'_reconcile_terminal_reroute')):
            _path,report=B.route_saved_seam_neighbour(
                world,link,'neighbor',np.array([100.,0.]),np.array([1.,0.]),route,
                lambda _world:None,lambda _world,_claims:None,start=np.array([0.,0.]))
        self.assertEqual(report['waypoint'],[102.,6.])
        self.assertEqual(report['depth'],4.)
        self.assertEqual(report['attempts'],5)

    def test_saved_seam_grade_follows_the_lane_not_the_transverse_bank(self):
        class World:
            ids=['neighbor','sunmane']
            # The exported collision contract checks that a lane exists across
            # the road width.  This preflight measures only travel along it.
            def height_at(self,x,z):return np.asarray(x)*.6+np.asarray(z)*10.
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
        road={'points':[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]}
        self.assertAlmostEqual(B.saved_seam_approach_grade(
            World(),road,'neighbor',np.array([2.,0.])),.6)

    def test_saved_seam_keeps_the_initial_route_until_terrain_is_settled(self):
        class World:
            def hub(self,region):return np.array([0.,0.])
            def solids_at_ends(self,point):return 'hub solids'
            def road_profile(self,path):raise AssertionError('unsettled terrain must not be inspected')
        calls=[]
        def route(world,legs,region,**options):
            calls.append((np.asarray(legs).tolist(),region,options))
            return np.asarray(legs,float)
        link={'id':'saved-link'}
        path,marker,count=B.route_initial_seam_neighbour(
            World(),link,'neighbor',np.array([10.,0.]),np.array([1.,0.]),[np.array([4.,3.])],route,saved=True)
        self.assertEqual(calls[0][0],[[0.,0.],[4.,3.],[1.,0.]])
        self.assertEqual(path[-3:].tolist(),[[6.,0.],[10.,0.],[14.,0.]])
        self.assertEqual(marker,{'depth':9.,'waypoint':None,'attempts':0})
        self.assertEqual(count,3)

    def test_final_saved_seam_gate_rejects_a_genuinely_steep_boundary(self):
        class World:
            ids=['neighbor','sunmane']
            connections=[{'id':'saved-link','anchor':[2.,0.]}]
            saved_seam_approaches=[{'id':'saved-link','region':'neighbor'}]
            roads=[{'id':'saved-link-neighbor','points':[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]]}]
            def height_at(self,x,z):return np.asarray(x)*.7
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
        with self.assertRaisesRegex(ValueError,'final saved seam neighbour approach is too steep'):
            B.validate_saved_seam_approaches(World())

    def test_saved_seam_terminal_repair_does_not_resettle_unrelated_ground(self):
        class World:
            ids=['neighbor','sunmane']
            connections=[{'id':'saved-link','anchor':[100.,0.],'normal':[1.,0.],
                          'regions':['neighbor','sunmane']}]
            saved_seam_approaches=[{'id':'saved-link','region':'neighbor'}]
            roads=[{'id':'unrelated','points':[[40.,7.,40.],[41.,7.,40.]],'width':4.},
                   {'id':'saved-link-neighbor','points':[[0.,0.,0.],[60.,0.,0.],[70.,0.,0.],
                                                        [80.,0.,0.],[90.,0.,0.],[100.,0.,0.]],
                    'width':4.}]
            height=np.array([[7.,8.],[9.,10.]])
            sample_heights={(0.,0.):0.,(60.,0.):0.,(70.,0.):9.,(80.,0.):18.,
                            (90.,0.):21.,(100.,0.):12.,(70.,10.):3.,(80.,15.):6.,
                            (90.,10.):9.,(96.,4.):11.,(104.,0.):13.2}
            def height_at(self,x,z):
                return np.array([self.sample_heights[(float(a),float(b))]
                                 for a,b in zip(np.atleast_1d(x),np.atleast_1d(z))])
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def add_road(self,path,width,name):
                self.roads.append({'id':name,'points':np.asarray(path,float),'width':width})
            def settle_roads(self):
                raise AssertionError('a terminal repair must not grade the global road network again')
        world=World();before=world.height.copy();unrelated=np.asarray(world.roads[0]['points']).copy()
        all_existing=[np.asarray(road['points']).copy() for road in world.roads]
        replacement=np.array([[0.,0.,0.],[60.,0.,0.],[70.,0.,10.],[80.,0.,15.],
                              [90.,0.,10.],[96.,0.,4.],[100.,0.,0.],[104.,0.,0.]])
        report={'depth':9.,'waypoint':[90.,10.],'attempts':1}
        before_grade=B.saved_seam_approach_grade(
            world,world.roads[1],'neighbor',np.array([100.,0.]))
        with (patch.object(B,'route_saved_seam_neighbour',return_value=(replacement,report)),
              patch.object(B.AUTHORING,'_register_road_fields')):
            repairs=B.repair_saved_seam_approaches(
                world,None,None,lambda _world:None,lambda _world,_claims:None)
        self.assertTrue(np.array_equal(world.height,before))
        self.assertTrue(np.array_equal(np.asarray(world.roads[0]['points']),unrelated))
        self.assertTrue(np.array_equal(all_existing[0],np.asarray(world.roads[0]['points'])))
        self.assertTrue(np.array_equal(all_existing[1][:2],replacement[:2]))
        after_grade=B.saved_seam_approach_grade(
            world,world.roads[-1],'neighbor',np.array([100.,0.]))
        self.assertAlmostEqual(before_grade,.9);self.assertLessEqual(after_grade,B.SERVED_MAX_GRADE)
        self.assertEqual(repairs,[{'id':'saved-link','region':'neighbor','beforeMaximumGrade':.9,
                                  **report,'afterMaximumGrade':round(after_grade,6)}])
        self.assertTrue(np.array_equal(np.asarray(world.roads[-1]['points']),replacement))
        self.assertEqual(B.validate_saved_seam_approaches(world)[0]['maximumGrade'],after_grade)

    def test_saved_terminal_reroute_replaces_claims_and_rolls_back_failed_candidate(self):
        def site(identity,key,x):
            return {'id':identity,'key':key,'river':'test','region':'neighbor','lastResort':True,
                    'routeLandings':[[x,-2.],[x,2.]]}
        name='saved-link-neighbor'
        class World:
            ids=['neighbor','sunmane']
            crossing_sites=[site(0,'prefix',5.),site(1,'obsolete',20.),site(2,'unrelated',40.)]
            crossing_site_use={0:1,1:1,2:1}
            crossing_site_roads={0:{name},1:{name},2:{'other-road'}}
            crossing_version=1
            river_crossings={'lastResortClaims':[{'site':0,'key':'prefix','road':name},
                                                  {'site':1,'key':'obsolete','road':name},
                                                  {'site':2,'key':'unrelated','road':'other-road'}]}
            routing=[{'name':name,'region':'neighbor','crossings':['prefix','obsolete'],'sites':[0,1],
                      'earthworks':{'passes':1,'excessMetres':2.,'excessAt':[]},
                      'solidFallback':False,'lastResortSearch':True},
                     {'name':'other-road','region':'neighbor','crossings':['unrelated'],'sites':[2],
                      'earthworks':{'passes':0,'excessMetres':0.,'excessAt':[]}}]
            roads=[{'id':name,'points':[[0.,0.,0.],[5.,0.,0.],[10.,0.,0.],[15.,0.,0.]],'width':4.}]
            def owner_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=int)
            def height_at(self,x,z):return np.zeros(np.asarray(x).shape,dtype=float)
            def solids_at_ends(self,point):return None
            def road_profile(self,path):
                points=np.asarray(path,float).reshape(-1,2)
                return points,np.zeros(len(points))
        world=World();calls=[]
        def route(_world,legs,*args,**kwargs):
            number=len(calls)+1;calls.append(number);identity=len(_world.crossing_sites)
            candidate=site(identity,f'candidate-{number}',12.+number)
            _world.crossing_sites.append(candidate);_world.crossing_site_use[identity]=1
            _world.crossing_site_roads[identity]={name}
            _world.river_crossings['lastResortClaims'].append(
                {'site':identity,'key':candidate['key'],'road':name})
            _world.routing.append({'name':name,'region':'neighbor','earthworks':{
                'passes':0,'excessMetres':0.,'excessAt':[]},'solidFallback':False,
                'lastResortSearch':True,'crossings':[candidate['key']],'sites':[identity]})
            return np.asarray(legs,float)
        link={'id':'saved-link','regions':['neighbor','sunmane']}
        with patch.object(B,'_seam_approach_feasible',side_effect=(False,True)):
            _path,report=B.route_saved_seam_neighbour(
                world,link,'neighbor',np.array([20.,0.]),np.array([1.,0.]),route,
                RC.snapshot_claims,RC.restore_claims,start=np.array([10.,0.]),
                prefix=np.array([[0.,0.],[5.,0.]]))
        self.assertEqual(report['attempts'],2)
        self.assertEqual([row['key'] for row in world.crossing_sites],
                         ['prefix','unrelated','candidate-2'])
        self.assertEqual(world.crossing_site_roads,
                         {0:{name},1:{'other-road'},2:{name}})
        self.assertEqual(world.crossing_site_use,{0:1,1:1,2:1})
        self.assertEqual([(row['site'],row['key'],row['road'])
                          for row in world.river_crossings['lastResortClaims']],
                         [(0,'prefix',name),(1,'unrelated','other-road'),(2,'candidate-2',name)])
        self.assertEqual(sum(row.get('name')==name for row in world.routing),1)
        self.assertEqual(sum(row.get('name')=='other-road' for row in world.routing),1)
        route=next(row for row in world.routing if row.get('name')==name)
        self.assertEqual(route['crossings'],['prefix','candidate-2'])
        self.assertEqual(route['sites'],[0,2])
        other=next(row for row in world.routing if row.get('name')=='other-road')
        self.assertEqual(other['crossings'],['unrelated']);self.assertEqual(other['sites'],[1])

    def test_a_stage_records_the_documented_shape_and_clamps_its_fraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'generated/progress.json';progress=P.Progress(path)
            progress.start('compose',4)
            record=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(tuple(record),P.KEYS)
            self.assertEqual(record['stage'],'compose');self.assertEqual(record['step'],'')
            self.assertEqual(record['fraction'],0);self.assertEqual(record['status'],'running')
            self.assertIsNone(record['exit']);self.assertEqual(record['pid'],os.getpid())
            self.assertTrue(record['startedAt'].endswith('Z'),record['startedAt'])
            self.assertGreaterEqual(record['updatedAt'],record['startedAt'])
            progress.step('roads and routing',1,4)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['fraction'],.25)
            progress.step('counted against the stage total')
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['fraction'],.5)
            for done,total,expected in ((9,4,1),(-3,4,0),(1,0,0)):
                progress.step('clamped',done,total)
                current=json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(current['fraction'],expected,(done,total))
                self.assertEqual(current['step'],'clamped');self.assertEqual(current['status'],'running')
            progress.start('a stage with no inner steps');progress.step('unknown total',1)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['fraction'],0)
            # A replaced record is the only file left: readers never see a partial write.
            self.assertEqual([p.name for p in path.parent.iterdir()],['progress.json'])

    def test_finishing_records_the_exit_code_and_its_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json';progress=P.Progress(path)
            progress.start('geometry',12);progress.step('whitehorn_range',3,12)
            progress.finish(3)
            failed=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(failed['status'],'failed');self.assertEqual(failed['exit'],3)
            self.assertEqual(failed['fraction'],.25);self.assertEqual(failed['step'],'whitehorn_range')
            started=failed['startedAt']
            progress.finish(0)
            done=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(done['status'],'done');self.assertEqual(done['exit'],0)
            self.assertEqual(done['fraction'],1);self.assertEqual(done['startedAt'],started)
            self.assertIn(done['status'],P.STATUSES)

    def test_a_failed_build_is_recorded_by_the_installed_exception_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'progress.json';progress=P.Progress(path);chained=[]
            hook=sys.excepthook
            try:
                sys.excepthook=lambda *arguments:chained.append(arguments)
                progress.watch();progress.start('publish')
                sys.excepthook(subprocess.CalledProcessError,subprocess.CalledProcessError(7,'publish'),None)
            finally:sys.excepthook=hook
            self.assertEqual(len(chained),1,'the previous exception hook must still run')
            record=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(record['status'],'failed');self.assertEqual(record['exit'],7)
            self.assertEqual(record['stage'],'publish')

    def test_an_unwritable_record_warns_instead_of_stopping_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocked=Path(tmp)/'progress.json';blocked.mkdir()
            progress=P.Progress(blocked);output=io.StringIO()
            with redirect_stdout(output):
                progress.start('compose',4);progress.step('roads and routing',1,4);progress.finish(1)
            self.assertEqual(output.getvalue().count('Warning: build progress not written'),3)
            self.assertTrue(blocked.is_dir())
            # The temporary files it could not move into place are cleaned up.
            self.assertEqual(list(Path(tmp).iterdir()),[blocked])

    def test_an_inert_record_writes_nothing_and_says_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            progress=P.Progress(None);output=io.StringIO()
            with redirect_stdout(output):
                progress.start('compose',4);progress.step('roads',1,4);progress.finish(0)
            self.assertEqual(output.getvalue(),'')
            self.assertEqual(list(Path(tmp).iterdir()),[])
            path=Path(tmp)/'progress.json'
            progress.attach(path).finish(0)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['status'],'done')


class CompositionFreshnessTests(unittest.TestCase):
    def fixture(self,root):
        """The records prepare() writes, for a client tree of fixture sources."""
        client=root/'client';continent=client/'eloria-assets/maps/nymara-regions/_continent'
        generated=continent/'generated';generated.mkdir(parents=True)
        plan=continent/'diagonal-plan.json';plan.write_text('{"regions": []}\n',encoding='utf-8')
        sources={}
        for name in B.SHAPING_SOURCES:
            source=continent/name;source.parent.mkdir(parents=True,exist_ok=True)
            source.write_text(f'# fixture {name}\n',encoding='utf-8')
            sources[source.resolve().relative_to(client.resolve()).as_posix()]=digest(source)
        for name in B.EXPORT_SOURCES:
            source=continent/name
            if not source.exists():
                source.parent.mkdir(parents=True,exist_ok=True)
                source.write_text(f'# fixture {name}\n',encoding='utf-8')
        builder=continent/'build_continent.py';builder.write_text('# fixture builder\n',encoding='utf-8')
        sources[str(builder.relative_to(client))]=digest(builder)
        profile=continent/'legacy-server-profile/config/eloria/maps.txt'
        profile.parent.mkdir(parents=True);profile.write_text('# fixture entrances\n',encoding='utf-8')
        self.write(generated/'composition.json',{'schema':1,'planSha256':digest(plan),
            'entranceProfileSha256':digest(profile),'compositionAlgorithmSha256':B.composition_algorithm_sha(),
            'geometryDependencies':B.geometry_dependencies(),
            'continentAuthoring':{'schema':3,'regions':{}},
            'library':{},'sources':sources,'objects':3,'roads':7})
        return client,continent,generated

    def write(self,path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

    def freshness(self,client,continent,generated):
        with patch.object(B,'HERE',continent),patch.object(B,'CLIENT',client),\
             patch.object(B.AUTHORING,'load_snapshots',return_value=()):
            return B.composition_freshness(generated)

    def test_an_untouched_composition_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            state=self.freshness(client,continent,generated)
            self.assertTrue(state['fresh'],state);self.assertTrue(state['composed'])
            self.assertEqual((state['changed'],state['missing'],state['unknown']),([],[],[]))
            self.assertEqual(state['recorded'],state['current'])
            self.assertEqual(state['recorded']['plan'],digest(continent/'diagonal-plan.json'))
            self.assertIn('eloria-assets/maps/nymara-regions/_continent/landscape.py',state['recorded'])
            # Sources the composition records but the stages do not gate on stay out of it.
            self.assertNotIn('eloria-assets/maps/nymara-regions/_continent/build_continent.py',state['recorded'])

    def test_an_edited_plan_or_shaping_source_reads_as_stale(self):
        for name,expected in (('diagonal-plan.json','plan'),
                               ('content.py','eloria-assets/maps/nymara-regions/_continent/content.py'),
                               ('bridge_prepare.py','eloria-assets/maps/nymara-regions/_continent/bridge_prepare.py'),
                               ('../_northern/requirements.txt','eloria-assets/maps/nymara-regions/_northern/requirements.txt'),
                              ('legacy-server-profile/config/eloria/maps.txt','entranceProfile')):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                client,continent,generated=self.fixture(Path(tmp))
                (continent/name).write_text('# edited by the plan editor\n',encoding='utf-8')
                state=self.freshness(client,continent,generated)
                self.assertFalse(state['fresh'])
                self.assertEqual(state['changed'],[expected],state['changed'])
                self.assertEqual(state['missing'],[])
                self.assertNotEqual(state['recorded'][expected],state['current'][expected])

    def test_a_missing_required_shaping_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            composition=json.loads((generated/'composition.json').read_text(encoding='utf-8'))
            requirement='eloria-assets/maps/nymara-regions/_northern/requirements.txt'
            composition['sources'].pop(requirement)
            self.write(generated/'composition.json',composition)
            state=self.freshness(client,continent,generated)
            self.assertFalse(state['fresh']);self.assertIn(requirement,state['missing'])
            with patch.object(B,'HERE',continent),patch.object(B,'CLIENT',client),\
                 patch.object(B.AUTHORING,'load_snapshots',return_value=()):
                with self.assertRaisesRegex(ValueError,'missing shaping source certificates.*requirements.txt'):
                    B.load_composed(generated,Path(tmp)/'library')

    def test_a_requirements_only_change_invalidates_composition_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            requirement=continent/'../_northern/requirements.txt'
            export_sources={name:(digest(continent/name) if (continent/name).exists() else '0'*64)
                            for name in B.EXPORT_SOURCES}
            self.write(generated/'export.json',{'compositionSha256':digest(generated/'composition.json'),
                'geometrySources':export_sources,'geometryDependencies':B.geometry_dependencies()})
            requirement.write_text('# changed requirement\n',encoding='utf-8')
            state=self.freshness(client,continent,generated)
            self.assertFalse(state['fresh'])
            self.assertEqual(state['changed'],['eloria-assets/maps/nymara-regions/_northern/requirements.txt'])
            with patch.object(B,'HERE',continent),patch.object(B,'CLIENT',client),\
                 patch.object(B.AUTHORING,'load_snapshots',return_value=()):
                with self.assertRaisesRegex(ValueError,'requirements.txt: landscape composition changed'):
                    B.load_composed(generated,Path(tmp)/'library')
                with self.assertRaisesRegex(ValueError,'requirements.txt: geometry export source changed'):
                    B.verify_geometry_export(generated)

    def test_a_runtime_dependency_mismatch_invalidates_composition_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            changed={'shapely':'2.1.2','geos':'3.10.0-test'}
            with patch.object(B,'geometry_dependencies',return_value=changed):
                state=self.freshness(client,continent,generated)
                self.assertFalse(state['fresh']);self.assertEqual(state['changed'],['geometryDependencies'])
                with patch.object(B,'HERE',continent),patch.object(B,'CLIENT',client),\
                     patch.object(B.AUTHORING,'load_snapshots',return_value=()):
                    with self.assertRaisesRegex(ValueError,'Geometry dependencies changed'):
                        B.load_composed(generated,Path(tmp)/'library')
            self.write(generated/'export.json',{'compositionSha256':digest(generated/'composition.json'),
                'geometrySources':{name:'0'*64 for name in B.EXPORT_SOURCES},
                'geometryDependencies':changed})
            with patch.object(B,'HERE',continent):
                with self.assertRaisesRegex(ValueError,'Geometry export dependencies changed'):
                    B.verify_geometry_export(generated)

    def test_a_deleted_input_is_missing_rather_than_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            (continent/'hull_settle.py').unlink()
            composition=json.loads((generated/'composition.json').read_text(encoding='utf-8'))
            composition['objectEditsSha256']='4'*64
            self.write(generated/'composition.json',composition)
            state=self.freshness(client,continent,generated)
            self.assertFalse(state['fresh'])
            self.assertEqual(state['missing'],['eloria-assets/maps/nymara-regions/_continent/hull_settle.py'])
            # A deleted edit file is the empty edit set, so a composition made with edits reads as changed.
            self.assertEqual(state['changed'],['objectEdits'])
            self.assertEqual(state['current']['objectEdits'],B.EMPTY_SHA256)

    def test_an_absent_edit_file_is_the_empty_edit_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            # A composition from before object edits existed records no digest: fresh without a file.
            self.assertTrue(self.freshness(client,continent,generated)['fresh'])
            composition=json.loads((generated/'composition.json').read_text(encoding='utf-8'))
            composition['objectEditsSha256']=B.EMPTY_SHA256
            self.write(generated/'composition.json',composition)
            state=self.freshness(client,continent,generated)
            self.assertTrue(state['fresh']);self.assertEqual(state['current']['objectEdits'],B.EMPTY_SHA256)
            # Edits written after the compose read as changed.
            self.write(continent/'continent-edits.json',{'version':1,'objects':[]})
            state=self.freshness(client,continent,generated)
            self.assertFalse(state['fresh']);self.assertEqual(state['changed'],['objectEdits'])

    def test_a_recorded_digest_from_another_branch_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            client,continent,generated=self.fixture(Path(tmp))
            composition=json.loads((generated/'composition.json').read_text(encoding='utf-8'))
            composition['tideTableSha256']='9'*64
            composition['objectEditsSha256']=digest(continent/'diagonal-plan.json')
            self.write(generated/'composition.json',composition)
            (continent/'continent-edits.json').write_bytes((continent/'diagonal-plan.json').read_bytes())
            state=self.freshness(client,continent,generated)
            self.assertEqual(state['unknown'],['tideTableSha256'])
            self.assertEqual(state['recorded']['tideTableSha256'],'9'*64)
            self.assertEqual(state['changed'],[]);self.assertEqual(state['missing'],[])
            # An optional input this branch does know is checked like any other.
            self.assertEqual(state['recorded']['objectEdits'],state['current']['objectEdits'])
            self.assertFalse(state['fresh'])

    def test_an_uncomposed_output_reports_nothing_composed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=B.composition_freshness(Path(tmp))
            self.assertEqual(state,{'fresh':False,'composed':False,'changed':[],'missing':[],
                                    'unknown':[],'recorded':{},'current':{}})

    def test_the_switch_reports_without_a_library_and_exits_by_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            done=subprocess.run([sys.executable,str(HERE/'build_continent.py'),'--freshness','--output',tmp],
                                capture_output=True,text=True,cwd=str(HERE))
            self.assertEqual(done.returncode,2,done.stderr)
            self.assertFalse(json.loads(done.stdout)['composed'])
            self.assertEqual(list(Path(tmp).iterdir()),[])


if __name__=='__main__':
    unittest.main()
