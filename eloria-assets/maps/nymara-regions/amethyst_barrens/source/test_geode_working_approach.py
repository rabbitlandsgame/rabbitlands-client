"""Actual-package regressions for the geode workers' ordinary bank access.

ELORIA_AMETHYST_PACKAGE may point at an isolated candidate. ELORIA_SERVER_ROOT
selects the paired server whose pure collision/path rules and occupancy apply.
No World constructor, database, served package or profile writes are used.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import math
import os
import sys
import unittest
import numpy as np

SOURCE=Path(__file__).resolve().parent
CLIENT=SOURCE.parents[4]
REGIONS=SOURCE.parents[1]
PACKAGE=Path(os.environ.get('ELORIA_AMETHYST_PACKAGE',str(SOURCE.parent)))
SERVER=Path(os.environ.get('ELORIA_SERVER_ROOT',str(CLIENT.parent/'work-output/southern-rollout/publish/server')))
sys.path[:0]=[str(SOURCE),str(REGIONS/'_toolkit'),str(REGIONS/'_finishing'),str(SERVER),str(SERVER/'tools')]
import glb_reader as G
import connector_finish as F
import geode_working_approach as A
from collision_sources import Source
from sync_authored_collision import choose_stage,rescale
from eloria.collision import CollisionMap,with_step_mask,with_storage_collision
from eloria.world import World
from eloria.npcs import load_npcs
from eloria.interactives import load_interactives
try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
    from eloria import content_overlay
except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
    pass
else:
    content_overlay.configure(False)


class GeodeWorkingAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((PACKAGE/'world.json').read_text(encoding='utf-8'))
        cls.origin=np.asarray(cls.manifest['coordinateTransform']['serverOrigin'])
        n=cls.manifest['asset']['serverCells']
        raw=Source('ewcg','collision.bin').load(PACKAGE,n)
        stage,_,_=choose_stage(raw)
        collision=with_step_mask(CollisionMap(n,n,rescale(raw,stage).tobytes()),2)
        interactives=load_interactives(SERVER/'config/eloria/interactives.txt')
        collision=with_storage_collision(collision,[(p.x,p.y) for p in interactives.values()
            if p.map_id=='amethyst_barrens' and p.role=='storage'])
        cls.world=World.__new__(World)
        cls.world.settings=SimpleNamespace(max_walk_height_change=2)
        cls.world.collision_maps={'amethyst_barrens':collision}
        cls.world._footprint_collision={}
        cls.npcs=[p for p in load_npcs(SERVER/'config/eloria/npcs.txt') if p.map_id=='amethyst_barrens']
        cls.occupied={(p.x,p.y) for p in cls.npcs}
        cls.posts={name:tuple(map(int,np.round([p[0]+cls.origin[0],cls.origin[1]-p[2]])))
            for name,p in cls.manifest['contentLayout']['npcs'].items()
            if name in ('Geode Digger Torvin Slate','Grinder Vell')}
        # Cover both the currently configured bodies and the exact authored
        # posts that the next content publication will use.
        cls.occupied.update(cls.posts.values())
        cls.primary=tuple(map(int,cls.origin+np.array([24,-31])))
        cls.document,cls.body=G.load(PACKAGE/'world.glb')
        triangles=G.triangles(cls.document,cls.body,sorted(set(
            G.named(cls.document,'Terrain_')+G.named(cls.document,'Walk_'))))
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        cls.floor=F.VerticalRayIndex(triangles[normal[:,1]>.001*np.linalg.norm(normal,axis=1)])

    def test_both_workers_are_approachable_from_the_primary_arrival_with_occupancy(self):
        for name,post in self.posts.items():
            with self.subTest(worker=name):
                path=self.world.find_path('amethyst_barrens',self.primary,post,self.occupied)
                self.assertTrue(path)
                self.assertLessEqual(max(abs(path[-1][0]-post[0]),abs(path[-1][1]-post[1])),1)
                self.assertTrue(all(p not in self.occupied for p in path))
        # The local workplace is also the return from the gauntlet; this
        # must connect to ordinary exterior ground rather than seed an island.
        post=tuple(map(int,self.origin+np.array([-75, 217])))
        path=self.world.find_path('amethyst_barrens',self.primary,post,self.occupied)
        self.assertTrue(path)
        self.assertEqual(path[-1],post)

    def test_full_working_width_and_its_fold_samples_have_continuous_upward_ground(self):
        stations,_=F.R._stations(A.CONTROLS,spacing=.25)
        for lane in (-1.5,0.,1.5):
            previous=None
            for i,q in enumerate(stations):
                tangent=stations[min(i+1,len(stations)-1),[0,2]]-stations[max(i-1,0),[0,2]]
                tangent/=np.linalg.norm(tangent)
                xz=q[[0,2]]+lane*np.array([-tangent[1],tangent[0]])
                tile=(math.floor(xz[0]+self.origin[0]),math.floor(self.origin[1]-xz[1]))
                for dx,dz in ((.5,-.5),(-.25,-.25),(-.25,.25),(.25,-.25),(.25,.25)):
                    x=tile[0]-self.origin[0]+dx;z=self.origin[1]-tile[1]+dz
                    self.assertIsNotNone(self.floor.top_hit(x,z),(lane,tile,dx,dz))
                if previous and previous!=tile:
                    for a,b in ((previous,tile),(tile,previous)):
                        self.assertTrue(self.world.step_allowed('amethyst_barrens',*a,b[0]-a[0],b[1]-a[1],
                            self.world.step_mask_at('amethyst_barrens',*a)),(lane,a,b))
                previous=tile

    def test_new_working_skin_faces_up_and_free_mound_no_longer_blocks_the_bank(self):
        triangles=G.triangles(self.document,self.body,G.named(self.document,'Walk_GeodeWorkingApproach_'))
        self.assertGreater(len(triangles),0)
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        self.assertTrue((normal[:,1]>=-1e-9).all())
        # The introduced isolated blade had soil above11m at this position.
        self.assertLess(self.floor.top_hit(-88.,-207.),6.)

    def test_worker_metadata_y_matches_the_final_visible_working_ground(self):
        for name in self.posts:
            x,y,z=self.manifest['contentLayout']['npcs'][name]
            self.assertLess(abs(y-self.floor.top_hit(x,z)),.05,name)


if __name__=='__main__':unittest.main()
