"""Sunmane identity, native scale and actual authored boundary contracts."""
from pathlib import Path
import json,math,sys,unittest
import numpy as np
SOURCE=Path(__file__).resolve().parent;PACKAGE=SOURCE.parent
sys.path[:0]=[str(SOURCE),str(SOURCE.parents[1]/'_toolkit')]
import build_landscape as B
import landscape_plan as P
import glb_reader as G
from verify_runtime import VerticalRayIndex

class InhabitedSunmane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads((PACKAGE/'world.json').read_text(encoding='utf-8'))
        cls.old=json.loads((SOURCE/'legacy-manifest.json').read_text(encoding='utf-8'))
        doc,body=G.load(PACKAGE/'world.glb')
        def indices(prefixes):return [i for i,n in enumerate(doc['nodes'])
            if n.get('name','').startswith(prefixes) and not any(marker in n.get('name','') for marker in ('StreamView_','_StreamThreshold_'))]
        cls.ground=VerticalRayIndex(G.triangles(doc,body,indices(('Terrain_','Walk_'))),cell=4)
        cls.water=VerticalRayIndex(G.triangles(doc,body,indices(('Water_',))),cell=4)

    def test_every_old_landmark_and_interactive_id_survives(self):
        for bucket in ('landmarks','interactives'):
            self.assertEqual({e['id'] for e in self.old[bucket]},
                             {e['id'] for e in self.m[bucket]},bucket)

    def test_original_marker_contract_ids_are_separate_from_runtime_roster(self):
        for old,new in (('npcs','npcMarkers'),('resources','harvestables')):
            self.assertEqual({e['id'] for e in self.old['runtimePopulation'][old]},
                             {e['id'] for e in self.m[new]})

    def test_city_and_native_building_scale_are_preserved(self):
        original=B.N.compose_layout(None);compact,_=B.prepare_layout()
        old={e.name:e for e in original.placements}
        for p in compact.placements:
            self.assertEqual(p.scale,old[p.name].scale,p.name)
            if math.hypot(old[p.name].x,old[p.name].z)<25:
                self.assertEqual((p.x,p.z),(old[p.name].x,old[p.name].z),p.name)

    def test_no_new_eastern_frontier_exit(self):
        self.assertEqual({s['portal'] for s in self.m['streamingBorders']},
                         {'north-track','west-landing','south-track'})
        self.assertFalse(any(e.get('id')=='east-road' for e in self.m['portals']))

    def test_all_lane_actor_centres_have_real_ground_in_the_owning_region(self):
        for s in self.m['streamingBorders']:
            anchor=np.array(s['anchor']);out=np.array(s['outward']);side=np.array([-out[1],out[0]])
            other=s['destination'];regionroot=PACKAGE.parent
            matepackage=regionroot.parent/'four-gates' if other=='four_gates' else regionroot/other
            manifest=json.loads((matepackage/'world.json').read_text(encoding='utf-8'))
            mate=next(e for e in manifest['streamingBorders'] if e['destination']=='sunmane_steppe')
            ma=np.array(mate['anchor']);mo=np.array(mate['outward']);ms=np.array([-mo[1],mo[0]])
            doc,body=G.load(matepackage/'world.glb')
            indexes=[i for i,n in enumerate(doc['nodes']) if 'mesh' in n and n.get('name','').startswith(('Terrain_','Walk_'))
              and not any(marker in n.get('name','') for marker in ('StreamView_','_StreamThreshold_'))]
            triangles=G.triangles(doc,body,indexes)
            low=triangles.min(axis=1);high=triangles.max(axis=1)
            nearby=(low[:,0]<ma[0]+5)&(high[:,0]>ma[0]-5)&(low[:,2]<ma[2]+5)&(high[:,2]>ma[2]-5)
            receiver=VerticalRayIndex(triangles[nearby],cell=4)
            for across in range(-3,4):
                for depth in (-1,1):
                    if depth<0:
                        q=anchor[[0,2]]+out*depth+side*across
                        ground=self.ground.top_hit(*q);expected=anchor[1]
                        water=self.water.top_hit(*q)
                        self.assertTrue(water is None or water<ground-.2,(s['id'],across,depth))
                    else:
                        q=ma[[0,2]]-mo*depth-ms*across
                        ground=receiver.top_hit(*q);expected=ma[1]
                    self.assertIsNotNone(ground,(s['id'],across,depth))
                    self.assertLess(abs(ground-expected),.08)

    def test_border_views_reference_single_stored_cells(self):
        for filename in ('world.glb','world-lod2.glb'):
            doc,_=G.load(PACKAGE/filename)
            names=[e.get('name','') for e in doc['nodes']]
            self.assertFalse(any('StreamView_' in n or '_StreamOverflow_' in n for n in names))
            for spec in self.m['streamingBorders']:
                self.assertEqual(spec['geometryMode'],'continent-owned-v1')
                self.assertTrue(spec['sceneNodes'])
        specs={e['portal']:e for e in self.m['streamingBorders']}
        # The west/south overlap is one stored atom, referenced by both views.
        overlap=set(specs['west-landing']['sceneNodes'])&set(specs['south-track']['sceneNodes'])
        self.assertTrue(overlap)

    def test_compact_datum_and_primary_arrival(self):
        geography=json.loads((PACKAGE.parent/'continent-geography.json').read_text())['regions']['sunmane_steppe']
        frame=self.m['continentGeography']
        self.assertEqual(frame['nativeServerCells'],[384,384])
        self.assertEqual(frame['nativeServerOrigin'],[116,116])
        self.assertEqual(self.m['asset']['serverCells'],geography['serverCells'][0])
        self.assertEqual(self.m['coordinateTransform']['serverOrigin'],geography['serverOrigin'])
        spawn=next(e for e in self.m['spawnPoints'] if e['id']=='server-arrival')
        expected=[value+delta for value,delta in zip([137,95],frame['serverTileShift'])]
        self.assertEqual(spawn['serverTile'],expected)
        self.assertEqual([spawn['position'][0],spawn['position'][2]],[21.,21.])
        self.assertTrue(self.m['contentLayout']['primaryArrivalOnly'])
        self.assertTrue(self.m['contentLayout']['requireFullWildlife'])

    def test_both_cave_doors_target_the_served_combined_map(self):
        doors={p['id']:p for p in self.m['portals']}
        for name,spawn in (('cave-wind_caves','wind-caves-mouth'),('cave-crystal_hollow','crystal-hollow-adit')):
            self.assertEqual(doors[name]['destinationMap'],'sunmane_wind_caves')
            self.assertEqual(doors[name]['destinationSpawn'],spawn)

    def test_fourteen_secrets_and_sap_connection_survive(self):
        secrets=[e for e in self.m['interactives'] if e.get('kind')=='secret']
        self.assertEqual(len(secrets),14)
        sap=next(e for e in secrets if e['id']=='secret-steppe-sap-mouth')
        self.assertEqual(sap['destinationMap'],'amethyst_barrens_secrets')

    def test_cave_noise_seed_is_stable_and_importable(self):
        import caves
        self.assertEqual(caves.stable_seed('sunmane_wind_caves'),caves.noise_kit.stable_seed('sunmane_wind_caves'))

    def test_stream_lighting_uses_numeric_color_and_unit_direction(self):
        environment=B.normalize_environment(self.old['environment'])
        self.assertNotIn('variants',environment)
        for block in (environment,environment['goldenHour']):
            self.assertNotIn('rotationDegrees',block['sun'])
            self.assertAlmostEqual(np.linalg.norm(block['sun']['direction']),1.)
            self.assertEqual(len(block['sun']['color']),3)
            self.assertTrue(all(isinstance(c,float) for c in block['sun']['color']))
        self.assertEqual(B.normalize_environment({'sun':{'rotationDegrees':[0,90,0]}})['sun']['direction'][0],-1.)
        self.assertEqual(B.normalize_environment(environment),environment)

if __name__=='__main__':unittest.main()
