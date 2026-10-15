"""Trails reach authored resource sites on steep ground that no road corridor serves."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import resource_trails as R
import world_layout as W


class FakeContent:
    def __init__(self,center):
        self.center=np.asarray(center,float)
    def mapped_server_point(self,region,tile,roads=False):
        # A tile is a metre east and a metre south of the territory centre per unit.
        return np.array([self.center[0]+tile[0],0.,self.center[1]-tile[1]])


def fake_add_road(world):
    def add_road(path,width=3.5,name='road'):
        path=np.asarray(path,float);world.roads.append({'id':name,'points':np.c_[path[:,0],np.zeros(len(path)),path[:,1]].tolist(),'width':width})
    return add_road


def make_world(size=240):
    world=W.World.__new__(W.World)
    world.x=np.arange(0,size+1,W.CELL,dtype=float);world.z=np.arange(0,size+1,W.CELL,dtype=float)
    world.x0,world.z0=0.,0.;world.x1,world.z1=float(size),float(size)
    world.gx,world.gz=np.meshgrid(world.x,world.z)
    # Flat ground west of x 120, a 1:1 hillside east of it.
    world.height=10+np.clip(world.gx-120,0,None)*1.0;world.original_height=world.height.copy()
    world.owner=np.zeros((len(world.z)-1,len(world.x)-1),int);world.ids=['test']
    world.obstacles=np.zeros(world.gx.shape,bool);world.solids=np.zeros(world.gx.shape,bool)
    world.routing=[];world.plan={};world.regions={'test':{'center':[0,0]}}
    world.roads=[{'id':'public','points':[[20.,10.,40.],[116.,10.,40.]],'width':4.}]
    return world


class ResourceTrailTests(unittest.TestCase):
    def test_profile_rows_and_rules_read_the_vendored_formats(self):
        harvest='node | whitehorn_range | 39 | 225 | 55 | Peat\n# comment\n\nnode | other | 1 | 2 | 3 | Ore\n'
        territories='whitehorn_range | Whitehorn Range | whitehorn_range | potion | 39 |  81 | 124 | 277 | 124 | 147 |  |\n'
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'harvesting.txt').write_text(harvest,encoding='utf-8')
            (Path(folder)/'territories.txt').write_text(territories,encoding='utf-8')
            sites=R.authored_sites(folder,['whitehorn_range'])
        self.assertEqual([site[1] for site in sites['whitehorn_range']],[[225,55],[39,81],[124,277],[124,147]])

    def test_rules_match_the_publisher_when_it_is_available(self):
        module=Path(__file__).resolve().parents[3]/'tools'/'publish_continent_geography.py'
        if not module.exists():
            self.skipTest('publisher not beside this checkout')
        import importlib.util
        spec=importlib.util.spec_from_file_location('publish_continent_geography',module);published=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(published)
        for name,rules in R.RULES.items():
            if name in published.RULES:self.assertEqual([tuple(r) for r in published.RULES[name]],rules)

    def test_a_steep_far_site_gets_a_trail_and_near_or_flat_sites_do_not(self):
        world=make_world();content=FakeContent([0,0])
        # steep-far stands on the hillside 88 m from the road; steep-near on the hillside 24 m from its end (inside the budget); flat on the plain.
        sites={'test':[('steep-far',[180,-100]),('flat',[60,-100]),('steep-near',[140,-40])]}
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=lambda a,b,region=None,**kw:np.vstack([a,b])) as route,\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual(len(report['trails']),1)
        self.assertEqual(report['trails'][0]['sites'],['steep-far'])
        np.testing.assert_allclose(report['trails'][0]['to'],[180,100])
        self.assertEqual(report['steepSites'],2);self.assertEqual(report['servedSites'],1)
        self.assertEqual(world.roads[-1]['id'],'trail-test-0');self.assertEqual(world.roads[-1]['width'],R.TRAIL_WIDTH_METRES)
        np.testing.assert_allclose(route.call_args[0][0],[116,40])

    def test_a_post_out_of_walkable_reach_gets_a_trail_and_posts_beside_or_level_with_a_road_do_not(self):
        world=make_world();content=FakeContent([0,0])
        # post-hill stands 24 m past the road's end and 20 m above it (a 1:1 hillside), outside the 12 m budget and beyond
        # walkable reach; post-near stands 8 m from the road end; post-level stands 26 m from the road end on the plain;
        # post-far-level stands 80 m from any station on the plain.
        harvest_site=('steep-near',[140,-40],'site')
        sites={'test':[('post-hill',[140,-40],'post'),('post-near',[124,-40],'post'),('post-level',[100,-60],'post'),('post-far-level',[60,-120],'post'),harvest_site]}
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=lambda a,b,region=None,**kw:np.vstack([a,b])),\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual([t['sites'] for t in report['trails']],[['post-hill']])
        self.assertEqual((report['postsRead'],report['postsServed'],report['postsOutOfReach']),(4,3,1))   # the far level post stands on ground the placer serves
        self.assertEqual((report['sitesRead'],report['steepSites'],report['servedSites']),(1,1,1))   # the site beside a road keeps its 30 m rule

    def test_npc_posts_are_read_from_the_vendored_profile_only_when_switched_on(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'npcs.txt').write_text('npc | Motherroot Voice Sillow | amberwood | 227 | 235 | dialogue | actor_type=373 | text\n',encoding='utf-8')
            self.assertEqual(R.authored_sites(folder,['amberwood'])['amberwood'],[])
            with patch.object(R,'READ_POSTS',True):
                self.assertEqual(R.authored_sites(folder,['amberwood'])['amberwood'],[('npcs.txt:1:3',[227,235],'post')])

    def test_a_trail_without_an_alignment_is_recorded_not_fatal(self):
        world=make_world();content=FakeContent([0,0])
        sites={'test':[('lost',[180,-100])]}
        def no_route(a,b,region=None,**kw):
            raise ValueError('No road alignment')
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=no_route),\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual(report['trails'],[]);self.assertEqual(report['skipped'][0]['sites'],['lost'])
        self.assertEqual(len(world.roads),1)

    def test_a_trail_that_winds_far_around_for_a_short_gap_is_skipped(self):
        world=make_world();content=FakeContent([0,0])
        sites={'test':[('far',[180,-100])]}
        def winding(a,b,region=None,**kw):
            a=np.asarray(a,float);b=np.asarray(b,float)
            return np.vstack([a,a+[0,150],b+[0,150],b])   # three times the gap and more
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=winding),\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual(report['trails'],[]);self.assertIn('gap',report['skipped'][0]['reason'])
        self.assertEqual(len(world.roads),1)

    def test_a_cluster_centroid_outside_the_territory_aims_at_its_inside_site(self):
        world=make_world();content=FakeContent([0,0])
        world.owner[:, :]=0;world.owner[45:55, 92:95]=1;world.ids=['test','other']   # a notch of foreign ground at x 184..190, z 90..110
        sites={'test':[('in',[180,-100]),('far',[196,-100])]}   # both inside; their centroid (188,100) is in the notch
        targets=[]
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=lambda a,b,region=None,**kw:(targets.append(np.asarray(b)),np.vstack([a,b]))[1]),\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual(len(report['trails']),1)
        np.testing.assert_allclose(targets[0],[180,100])

    def test_sites_within_twenty_metres_share_one_trail(self):
        world=make_world();content=FakeContent([0,0])
        sites={'test':[('a',[180,-100]),('b',[192,-108]),('c',[180,-170])]}
        with patch.object(R,'authored_sites',return_value=sites),patch.object(world,'route',side_effect=lambda a,b,region=None,**kw:np.vstack([a,b])),\
             patch.object(world,'add_road',side_effect=fake_add_road(world)):
            report=R.prepare_resource_trails(world,content,'unused')
        self.assertEqual(sorted(len(t['sites']) for t in report['trails']),[1,2])
        self.assertEqual(R.cluster([[0,0],[5,0],[40,0]],20.),[[0,1],[2]])


if __name__=='__main__':
    unittest.main()
