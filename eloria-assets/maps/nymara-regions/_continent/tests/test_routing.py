"""Road alignment: retained solids are impassable, steep traverses are avoided, road ends stay exact."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import world_layout as W


def make_world(size=240):
    world=W.World.__new__(W.World)
    world.x=np.arange(0,size+1,W.CELL,dtype=float);world.z=np.arange(0,size+1,W.CELL,dtype=float)
    world.x0,world.z0=0.,0.;world.x1,world.z1=float(size),float(size)
    world.gx,world.gz=np.meshgrid(world.x,world.z)
    world.height=np.full(world.gx.shape,10.);world.original_height=world.height.copy()
    world.owner=np.zeros((len(world.z)-1,len(world.x)-1),int);world.ids=['test']
    world.obstacles=np.zeros(world.gx.shape,bool);world.solids=np.zeros(world.gx.shape,bool)
    world.routing=[];world.plan={}
    return world


def samples(points,step=1.):
    dense=[]
    for a,b in zip(points,points[1:]):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/step)))
        dense.extend(a+(b-a)*k/count for k in range(count))
    return np.vstack([dense,points[-1]])


def inside(points,low,high):
    return (points[:,0]>=low[0])&(points[:,0]<=high[0])&(points[:,1]>=low[1])&(points[:,1]<=high[1])


class RoutingTests(unittest.TestCase):
    def test_a_compact_solid_is_impassable_for_stations_and_edges(self):
        world=make_world()
        world.structure_obstacle([110,0,90],[126,8,150])   # a 16 x 60 m hall across the direct line
        self.assertTrue(world.solids.any())
        points=world.route([20,120],[220,120],region='test')
        np.testing.assert_allclose(points[0],[20,120]);np.testing.assert_allclose(points[-1],[220,120])
        margin=W.SOLID_MARGIN_METRES
        self.assertFalse(inside(samples(points),[110-margin,90-margin],[126+margin,150+margin]).any())
        self.assertFalse(world.routing[-1]['solidFallback'])

    def test_a_thin_solid_between_stations_is_seen_on_the_edge(self):
        world=make_world()
        world.structure_obstacle([120,0,60],[121,8,180])   # a 1 m wall the 6 m stride would step over
        points=world.route([20,120],[220,120],region='test')
        self.assertFalse(inside(samples(points,.5),[119,59],[122,181]).any())
        self.assertFalse(world.routing[-1]['solidFallback'])

    def test_large_boxes_keep_the_soft_clearance_only(self):
        world=make_world()
        world.structure_obstacle([100,0,60],[160,8,180])   # a 60 x 120 m plaza (7200 square metres): an enclosure, not a solid
        self.assertTrue(world.obstacles.any());self.assertFalse(world.solids.any())
        points=world.route([20,120],[220,120],region='test')
        np.testing.assert_allclose(points[-1],[220,120])

    def test_a_road_end_inside_a_solid_is_reachable_without_fallback(self):
        world=make_world()
        world.structure_obstacle([150,0,100],[180,8,140])   # a 30 x 40 m lodge; the door road ends inside it
        points=world.route([20,120],[165,120],region='test')
        np.testing.assert_allclose(points[-1],[165,120])
        self.assertFalse(world.routing[-1]['solidFallback'])
        # A different solid on the way is still avoided.
        world.structure_obstacle([80,0,100],[96,8,140])
        points=world.route([20,120],[165,120],region='test')
        self.assertFalse(inside(samples(points),[78,98],[98,142]).any())
        self.assertFalse(world.routing[-1]['solidFallback'])

    def test_a_sealed_road_end_gets_a_straight_entry_from_open_ground(self):
        world=make_world()
        # A terminal inside a ruined watch-post: towers and camps seal it beyond the 6 m own radius.
        world.structure_obstacle([196,0,114],[210,8,126])   # the tower holding the terminal
        for box in (([184,0,100],[196,8,112]),([210,0,100],[222,8,112]),([184,0,128],[196,8,140]),([210,0,128],[222,8,140]),
                    ([184,0,112],[190,8,128]),([216,0,112],[222,8,128]),([196,0,100],[210,8,108]),([196,0,132],[210,8,140])):
            world.structure_obstacle(*box)
        points=world.route([20,120],[203,120],region='test')
        record=world.routing[-1]
        np.testing.assert_allclose(points[-1],[203,120])
        self.assertFalse(record['solidFallback']);self.assertGreater(record['entryMetres'],0)
        # Only the entry leg, within its recorded reach of the goal, lies inside the watch-post.
        dense=samples(points,.5);within=inside(dense,[183,99],[223,141])
        self.assertTrue(np.all(np.linalg.norm(dense[within]-[203,120],axis=1)<=record['entryMetres']+6))

    def test_a_seam_crossing_avoids_terminals_in_solids(self):
        world=make_world(size=300)
        # plan_connections indexes every desired pair, so all twelve names exist; only two own ground here.
        world.ids=['whitehorn_range','grey_moors','amberwood','amethyst_barrens','mirrorhold','sunmane_steppe','four_gates',
                   'westhaven','manymouth_delta','crownwater','verdant_stair','ssarathi_ruins']
        world.centers=np.full((12,2),-1000.);world.centers[2]=[75.,150.];world.centers[4]=[225.,150.]
        world.owner=np.where(world.gx[:-1,:-1]<150,2,4)
        world.plan={'connection_sites':{}};world.connections=[]
        world.height_at=lambda x,z:np.zeros_like(np.asarray(x,float))
        # A ruin stands on the seam at the natural crossing (z 150); with the seam-terminal term on, the crossing moves along the seam.
        world.structure_obstacle([146,0,140],[154,8,160])
        with patch.object(W.L,'water_fields',side_effect=lambda x,z,**k:{'depth':np.zeros(len(np.atleast_1d(x))),'mask':np.zeros(len(np.atleast_1d(x)),bool)}),\
             patch.object(W,'SEAM_TERMINAL_SOLID_PENALTY',60.):
            world.plan_connections()
        link=next(c for c in world.connections if c['id']=='amberwood--mirrorhold')
        anchor=np.asarray(link['anchor']);normal=np.asarray(link['normal'])
        self.assertGreater(abs(anchor[1]-150),8)
        for point in (anchor-normal*9,anchor,anchor+normal*9):
            self.assertFalse(world.solids[world.cell_of(point)])

    def test_an_entry_leg_threads_the_gap_between_tents(self):
        world=make_world()
        # A camp: the goal's hut, a wall of tents on the direct line with a 6 m gap off to one side,
        # and a ring of large solids beyond 30 m so no clean open ground is in reach.
        world.structure_obstacle([161,0,116],[169,8,124])
        world.structure_obstacle([140,0,80],[146,8,114]);world.structure_obstacle([140,0,130],[146,8,160])   # tents wall to wall, gap vertices z 120..126
        for box in (([125,0,60],[205,8,80]),([125,0,160],[205,8,180]),([185,0,80],[205,8,160])):
            world.structure_obstacle(*box)
        points=world.route([20,120],[165,120],region='test')
        np.testing.assert_allclose(points[-1],[165,120])
        dense=samples(points,.5)
        self.assertFalse(inside(dense,[139,79],[147,115]).any());self.assertFalse(inside(dense,[139,129],[147,161]).any())
        self.assertTrue(inside(dense,[139,116],[147,128]).any())

    def test_an_entry_leg_never_doubles_back_past_the_goal(self):
        world=make_world()
        world.structure_obstacle([161,0,116],[169,8,124])   # the goal's hut, open ground all round
        points=world.route([20,120],[165,120],region='test')
        self.assertGreater(world.routing[-1]['entryMetres'],0)
        self.assertLessEqual(points[:,0].max(),165.5)   # the alignment and its leg stay on the start's side of the hut

    def test_gate_towers_flanking_a_road_end_are_its_own(self):
        world=make_world()
        # A seam terminal between two towers 5 m apart: both towers are the road's own, the approach threads between them.
        world.structure_obstacle([200,0,108],[206,8,114]);world.structure_obstacle([200,0,126],[206,8,132])
        self.assertEqual(len(world.solids_at_ends([203,120])),2)
        points=world.route([20,120],[203,120],region='test')
        np.testing.assert_allclose(points[-1],[203,120])
        self.assertFalse(world.routing[-1]['solidFallback'])

    def test_a_sealed_goal_is_entered_by_a_straight_leg_from_open_ground(self):
        world=make_world()
        world.structure_obstacle([155,0,110],[175,8,130])   # the lodge holding the goal
        for box in (([147,0,102],[155,8,138]),([175,0,102],[183,8,138]),([147,0,102],[183,8,110]),([147,0,130],[183,8,138])):
            world.structure_obstacle(*box)
        self.assertEqual(int(world.solid_ids.max()),5)
        # The goal's own solid is exempt, but the ring of separate solids touching it is not: the
        # alignment stays outside the ring and a straight leg enters from the nearest open ground.
        points=world.route([20,120],[165,120],region='test')
        np.testing.assert_allclose(points[-1],[165,120])
        record=world.routing[-1]
        self.assertFalse(record['solidFallback']);self.assertGreater(record['entryMetres'],10)
        dense=samples(points,.5);within=inside(dense,[146,101],[184,139])
        self.assertTrue(np.all(np.linalg.norm(dense[within]-[165,120],axis=1)<=record['entryMetres']+6))

    def test_an_end_with_no_open_ground_in_reach_falls_back_to_the_soft_alignment(self):
        world=make_world()
        # A hut holds the goal; a ring of large solids beyond the 6 m own radius tiles the ground out to 40 m,
        # farther than the exit search reaches, leaving only a sealed pocket around the hut.
        world.structure_obstacle([161,0,116],[169,8,124])
        for box in (([125,0,70],[165,8,108]),([165,0,70],[205,8,108]),([125,0,132],[165,8,170]),([165,0,132],[205,8,170]),
                    ([125,0,108],[153,8,132]),([177,0,108],[205,8,132])):
            world.structure_obstacle(*box)
        for candidate in world.open_ground_candidates([165,120],'test'):
            self.assertTrue(inside(np.asarray([candidate]),[153,108],[177,132]).all())
        points=world.route([20,120],[165,120],region='test')
        np.testing.assert_allclose(points[-1],[165,120]);np.testing.assert_allclose(points[0],[20,120])
        self.assertTrue(world.routing[-1]['solidFallback'])

    def test_a_narrow_gap_is_threaded_with_closer_stations(self):
        world=make_world()
        # A wall across the whole map with a gap that holds no 6 m station (vertices z 116 and 118 only) but does hold a 4 m one.
        world.structure_obstacle([120,0,0],[121,8,111.5])
        world.structure_obstacle([120,0,122.5],[121,8,240])
        self.assertFalse(world.solids[world.cell_of([120,116])]);self.assertTrue(world.solids[world.cell_of([120,114])])
        self.assertTrue(world.solids[world.cell_of([120,120])])
        points=world.route([20,120],[220,120],region='test')
        record=world.routing[-1]
        self.assertFalse(record['solidFallback']);self.assertEqual(record['stationMetres'],4.)
        self.assertFalse(inside(samples(points,.5),[119,0],[122,112.5]).any())
        self.assertFalse(inside(samples(points,.5),[119,121.5],[122,240]).any())

    def test_a_hub_inside_a_hall_starts_its_road_at_the_open_side(self):
        world=make_world()
        world.structure_obstacle([90,0,100],[120,8,140])   # the hub's hall
        world.structure_obstacle([124,0,96],[130,8,144])   # a house beside it
        points=world.route([100,120],[220,120],region='test')
        record=world.routing[-1]
        np.testing.assert_allclose(points[0],[100,120]);np.testing.assert_allclose(points[-1],[220,120])
        self.assertFalse(record['solidFallback']);self.assertGreater(record['exitMetres'],0)
        self.assertFalse(inside(samples(points[1:],.5),[122,94],[132,146]).any())
        np.testing.assert_allclose(world.open_ground_near([200,20],'test'),[200,20])

    def test_a_sealed_end_is_entered_across_the_nearest_wall(self):
        world=make_world()
        # A goal sealed by a ring: the straight entry crosses the thin near wall, not the thick far one.
        world.structure_obstacle([150,0,100],[180,8,140])
        for box in (([146,0,80],[150,8,160]),([180,0,80],[198,8,160]),([146,0,60],[198,8,80]),([146,0,160],[198,8,180])):
            world.structure_obstacle(*box)
        self.assertEqual(int(world.solid_ids.max()),5)
        points=world.route([20,120],[165,120],region='test')
        self.assertFalse(world.routing[-1]['solidFallback']);self.assertGreater(world.routing[-1]['entryMetres'],0)
        dense=samples(points,.5)
        self.assertTrue(inside(dense,[145,79],[151,161]).any())
        self.assertFalse(inside(dense,[179,79],[199,161]).any())

    def test_a_steep_traverse_is_left_for_the_gentle_ground(self):
        world=make_world()
        # A 1:1 hillside band between z 90 and 110 with flat ground either side; the ends sit mid-slope.
        world.height=10+np.clip(world.gz-90,0,20)*1.0
        world.original_height=world.height.copy()
        with patch.object(W,'ROUTE_CROSS_SLOPE_LINEAR',25.),patch.object(W,'ROUTE_CROSS_SLOPE_SQUARE',40.):
            points=world.route([20,100],[220,100],region='test')
        interior=points[3:-3]
        self.assertGreater(np.mean(np.abs(interior[:,1]-100)>12),.5)
        # The ends sit mid-slope, so the road leaves the band and rejoins it; the middle half runs on the flat.
        middle=points[len(points)//4:-len(points)//4]
        self.assertTrue(np.all(np.abs(middle[:,1]-100)>12))
        with patch.object(W,'ROUTE_CROSS_SLOPE_LINEAR',0.),patch.object(W,'ROUTE_CROSS_SLOPE_SQUARE',0.):
            straight=world.route([20,100],[220,100],region='test')
        self.assertLessEqual(np.max(np.abs(straight[:,1]-100)),6.)

    def test_a_slot_gorge_between_stations_is_crossed_where_it_is_shallow(self):
        world=make_world()
        # A 4 m wide, 30 m deep slot across the whole map at x 121..125, between the station columns at 120 and 126.
        slot=(world.gx>=121)&(world.gx<=125)
        world.height=np.where(slot,-20.,10.);world.height[slot&(world.gz>=196)&(world.gz<=204)]=9.   # a shallow sill at z 200
        world.original_height=world.height.copy()
        with patch.object(W,'ROUTE_RELIEF_PENALTY',25.):
            points=world.route([20,120],[220,120],region='test')
        crossing=points[(points[:,0]>114)&(points[:,0]<132)]
        self.assertTrue(len(crossing));self.assertGreater(crossing[:,1].min(),190)
        # Without the relief and cross-slope penalties the stations, 6 m apart, never see the slot and the road runs straight.
        with patch.object(W,'ROUTE_RELIEF_PENALTY',0.),patch.object(W,'ROUTE_CROSS_SLOPE_LINEAR',0.),patch.object(W,'ROUTE_CROSS_SLOPE_SQUARE',0.):
            straight=world.route([20,120],[220,120],region='test')
        self.assertLessEqual(np.max(np.abs(straight[:,1]-120)),6.)

    def test_a_road_bed_through_shallow_water_stays_wadeable(self):
        world=make_world()
        world.height[:]=2.;world.original_height=world.height.copy()
        world.roads=[];world.road_distance=np.full(world.height.shape,np.inf);world.road_nearest=np.full(world.height.shape,np.inf);world.road_target=world.height.copy()
        # A pond 0.2 m deep over x 60..120 (surface 2.2) on a road whose ends sit 0.6 m lower than its middle.
        def water_fields(x,z,height=None,plan=None):
            x=np.atleast_1d(np.asarray(x,float));inside=(x>=60)&(x<=120)
            return {'mask':inside,'depth':np.where(inside,.2,0.),'surface':np.where(inside,2.2,0.)}
        world.height_at=lambda x,z:np.where((np.asarray(x)>=60)&(np.asarray(x)<=120),2.,1.4)
        with patch.object(W.L,'water_fields',side_effect=water_fields):
            world.add_road(np.array([[20.,100.],[220.,100.]]),width=1.65,name='ford')
        profile=np.asarray(world.roads[-1]['points'])
        pond=profile[(profile[:,0]>=60)&(profile[:,0]<=120),1]
        self.assertGreaterEqual(pond.min(),2.2-W.ROAD_WADE_DEPTH_METRES-1e-9)

    def test_flat_ground_keeps_a_direct_alignment_with_exact_ends(self):
        world=make_world()
        points=world.route([20,50],[220,50],region='test')
        np.testing.assert_allclose(points[0],[20,50]);np.testing.assert_allclose(points[-1],[220,50])
        self.assertLess(np.sum(np.linalg.norm(np.diff(points,axis=0),axis=1)),204.)
        self.assertEqual(world.routing_report()['routes'],1)

    def test_solid_crossings_reports_metres_inside_each_structure(self):
        world=make_world()
        world.roads=[{'id':'through','points':[[0,10,120],[240,10,120]],'width':4.},
                     {'id':'clear','points':[[0,10,20],[240,10,20]],'width':4.}]
        report=world.solid_crossings([('test','Hall',[100,0,100],[130,8,140]),('test','Hut',[10,0,200],[14,8,204])])
        self.assertEqual([(c['road'],c['node']) for c in report],[('through','Hall')])
        self.assertGreaterEqual(report[0]['metres'],30)

    def test_a_caller_may_name_the_own_solids_a_road_may_cross(self):
        world=make_world()
        world.structure_obstacle([60,0,-10],[64,8,250])   # a wall across the whole map, far from both ends
        world.route([26,120],[120,120],region='test')
        self.assertTrue(world.routing[-1]['solidFallback'])   # no hard alignment exists: the fallback crosses it as a heavy penalty
        world.routing=[]
        # A trail names the solids of its site as its own; a caller naming the wall lets the alignment through it.
        through=world.route([26,120],[120,120],region='test',own=world.solids_at_ends([62,120]))
        self.assertFalse(world.routing[-1]['solidFallback']);self.assertTrue(inside(samples(through,.5),[57,0],[67,240]).any())
        self.assertEqual(world.solids_at_ends([120,120]),set())

    def test_the_station_terrain_terms_are_per_territory(self):
        # The wild territories take the measured weights; the six with tuned sites and any test territory keep the module weights.
        self.assertEqual(W.terrain_terms('grey_moors'),(25.,40.,25.,600.))
        for region in [r for r in ('mirrorhold','ssarathi_ruins','amberwood','four_gates','whitehorn_range','manymouth_delta','westhaven') if r not in W.ROUTE_TERRAIN_TERMS]+['test']:
            self.assertEqual(W.terrain_terms(region),(W.ROUTE_CROSS_SLOPE_LINEAR,W.ROUTE_CROSS_SLOPE_SQUARE,W.ROUTE_RELIEF_PENALTY,W.ROUTE_STEP_PENALTY))
        with patch.object(W,'ROUTE_CROSS_SLOPE_LINEAR',25.):
            self.assertEqual(W.terrain_terms('test')[0],25.)


if __name__=='__main__':
    unittest.main()
