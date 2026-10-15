"""Extra ownership sites: a territory owns the ground nearest any of them, not only its centre.

The same partition, module level: ``ownership_map`` at any cell spacing is what the World
constructor scores its own grid with, and ``owner_components`` shows a territory that a site
has split into a body and an island the traced polygon cannot reach.
"""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import landscape as L
import world_layout as W

# The smallest plan World can be built from: two territories on 40 by 40 metres of
# inland ground, no ridges, islands, rivers or lakes, and a coastline far offshore.
PLAN={'name':'ownership probe','seed':7,'sea_level':0.,'bounds':[0,0,40,40],
    'coastline':[[-400,-400],[440,-400],[440,440],[-400,440]],
    'ridges':[],'islands':[],'rivers':[],'lakes':[],
    'regions':[{'id':'west','center':[10,20]},{'id':'east','center':[30,20]}]}
TAIL=[30.,36.]   # A second Westhaven-style site in the far corner of its neighbour.
FAR=[38.,20.]    # A site past the neighbour's own centre: the ground it wins is cut off.


class OwnershipSiteTests(unittest.TestCase):
    def world(self,**extra):
        return W.World(dict(PLAN,**extra))

    def cell_centres(self,world):
        return np.meshgrid(world.x[:-1]+W.CELL*.5,world.z[:-1]+W.CELL*.5)

    def test_a_second_site_takes_the_ground_nearest_it_and_no_other_ground(self):
        plain=self.world();world=self.world(ownership_sites={'west':[TAIL]})
        west,east=world.ids.index('west'),world.ids.index('east')
        cx,cz=self.cell_centres(world)
        # Two regions, so each cell falls to whichever site is nearest; the scoring loop
        # leaves a tie with the earlier region, which is how the plain world is scored too.
        to_centre=(cx-10)**2+(cz-20)**2;to_tail=(cx-TAIL[0])**2+(cz-TAIL[1])**2
        to_east=(cx-30)**2+(cz-20)**2
        np.testing.assert_array_equal(plain.owner,np.where(to_east<to_centre,east,west))
        np.testing.assert_array_equal(world.owner,np.where(to_east<np.minimum(to_centre,to_tail),east,west))
        changed=world.owner!=plain.owner
        self.assertTrue(changed.any())
        # Everything that changed hands went to the region that declared the site, and only
        # where that site is nearer than the centre that held the ground before.
        self.assertEqual(set(world.owner[changed].tolist()),{west})
        self.assertTrue((to_tail<to_east)[changed].all())
        self.assertFalse(changed[to_tail>=to_east].any())
        # Ground nearest either centre is untouched, including the far side of the site.
        for x,z in ((5.,5.),(15.,35.),(31.,5.),(39.,19.),(19.,29.)):
            self.assertEqual(int(world.owner_at(x,z)),int(plain.owner_at(x,z)))

    def test_owner_at_agrees_with_the_grid_over_the_new_ground(self):
        plain=self.world();world=self.world(ownership_sites={'west':[TAIL]})
        west,east=world.ids.index('west'),world.ids.index('east')
        for x,z in ((31.,35.),(39.,39.),(21.,29.),(31.,27.),(25.,15.),(1.,1.)):
            self.assertEqual(int(world.owner_at(x,z)),int(world.owner[int(z/W.CELL),int(x/W.CELL)]),(x,z))
        self.assertEqual(int(world.owner_at(*TAIL)),west)
        self.assertEqual(int(plain.owner_at(*TAIL)),east)
        # Outside the world nobody owns anything, sites or no sites.
        self.assertEqual(int(world.owner_at(-1.,20.)),-1)

    def test_the_tail_is_part_of_the_regions_polygon_and_its_address(self):
        plain=self.world();world=self.world(ownership_sites={'west':[TAIL]})
        polygon=np.array(world.polygons['west'])
        self.assertTrue(bool(L._polygon_inside(np.array(TAIL[0]),np.array(TAIL[1]),polygon)))
        self.assertFalse(bool(L._polygon_inside(np.array(TAIL[0]),np.array(TAIL[1]),np.array(plain.polygons['west']))))
        # The traced boundary now reaches the eastern world edge; the plain one stops at 20 m.
        np.testing.assert_allclose(world.bounds('west')[1],[40.,40.])
        np.testing.assert_allclose(plain.bounds('west')[1],[20.,40.])
        np.testing.assert_allclose(world.bounds('east')[1],[40.,28.])
        # Its map address still covers the whole territory, tail included.
        origin,cells=world.address('west');centre=world.centers[world.ids.index('west')]
        low,high=world.bounds('west')
        self.assertTrue(origin[0]>=centre[0]-low[0] and cells[0]>=high[0]-low[0])

    def test_a_site_must_name_a_region_of_this_plan_and_stand_inside_its_bounds(self):
        with self.assertRaisesRegex(ValueError,"no region 'north'"):
            self.world(ownership_sites={'north':[[10.,10.]]})
        with self.assertRaisesRegex(ValueError,'outside the plan bounds'):
            self.world(ownership_sites={'west':[TAIL,[41.,10.]]})
        # The constructor reads exactly this helper; a plan with no sites declares none.
        self.assertEqual(W.ownership_sites(PLAN,['west','east']),{})
        np.testing.assert_allclose(W.ownership_sites(dict(PLAN,ownership_sites={'east':[TAIL]}),
            ['west','east'])['east'],[TAIL])


class OwnershipMapTests(unittest.TestCase):
    """The partition on its own: no heights, no water, no sampled continent, any cell spacing."""

    def cell(self,owner,x0,z0,cell,x,z):
        return int(owner[int((z-z0)/cell),int((x-x0)/cell)])

    def test_the_constructor_scores_its_grid_with_the_module_level_partition(self):
        for extra in ({},{'ownership_sites':{'west':[TAIL]}},{'ownership_sites':{'west':[FAR]}},
                      {'ownership_bias':{'east':400}}):
            with self.subTest(**extra):
                plan=dict(PLAN,**extra);world=W.World(plan)
                ids,owner,x0,z0=W.ownership_map(plan)
                self.assertEqual(ids,world.ids);self.assertEqual((x0,z0),(world.x0,world.z0))
                np.testing.assert_array_equal(owner,world.owner)

    def test_a_coarse_map_names_the_same_region_under_every_site(self):
        plan=dict(PLAN,ownership_sites={'west':[TAIL,FAR]})
        ids,fine,x0,z0=W.ownership_map(plan,W.CELL)
        coarse_ids,coarse,cx0,cz0=W.ownership_map(plan,8.)
        self.assertEqual(coarse_ids,ids);self.assertEqual((cx0,cz0),(x0,z0))
        self.assertEqual(coarse.shape,(5,5));self.assertEqual(fine.shape,(20,20))
        for x,z in (TAIL,FAR,[10.,20.],[30.,20.],[1.,39.]):
            self.assertEqual(self.cell(coarse,x0,z0,8.,x,z),self.cell(fine,x0,z0,W.CELL,x,z),(x,z))

    def test_a_site_across_the_neighbour_is_one_island_whose_bounds_hold_it(self):
        plan=dict(PLAN,ownership_sites={'west':[FAR]})
        for cell in (W.CELL,8.):
            with self.subTest(cell=cell):
                ids,owner,x0,z0=W.ownership_map(plan,cell)
                parts=W.owner_components(plan,'west',cell)
                self.assertEqual(len(parts),2)
                self.assertEqual([part.shape for part in parts],[owner.shape]*2)
                self.assertGreater(np.count_nonzero(parts[0]),np.count_nonzero(parts[1]))
                # The masks are a partition of exactly the region's own cells.
                np.testing.assert_array_equal(parts[0]|parts[1],owner==ids.index('west'))
                self.assertFalse((parts[0]&parts[1]).any())
                islands=W.owner_islands(plan,'west',cell)
                self.assertEqual(len(islands),1);np.testing.assert_array_equal(islands[0],parts[1])
                extent=W.component_extent(islands[0],x0,z0,cell)
                self.assertEqual(extent['cells'],int(np.count_nonzero(islands[0])))
                low_x,low_z,high_x,high_z=extent['bounds']
                self.assertTrue(low_x<=FAR[0]<=high_x and low_z<=FAR[1]<=high_z,extent)
                # It is the ground the traced polygon silently leaves out.
                polygon=np.array(W.World(plan).polygons['west'])
                self.assertFalse(bool(L._polygon_inside(np.array(FAR[0]),np.array(FAR[1]),polygon)))

    def test_a_connected_plan_declares_no_islands(self):
        for plan in (PLAN,dict(PLAN,ownership_sites={'west':[TAIL]}),dict(PLAN,ownership_bias={'east':400})):
            for region in ('west','east'):
                with self.subTest(region=region,sites=plan.get('ownership_sites')):
                    self.assertEqual(len(W.owner_components(plan,region)),1)
                    self.assertEqual(W.owner_islands(plan,region),[])
        with self.assertRaisesRegex(ValueError,"no region 'north'"):
            W.owner_components(PLAN,'north')

    def test_the_ids_are_the_plans_order_and_a_tie_keeps_the_region_listed_first(self):
        self.assertEqual(W.ownership_map(PLAN,8.)[0],['west','east'])
        # At 8 m one column of cell centres stands exactly on the bisector: it goes to whoever is listed
        # first, so the same ground changes hands with the order alone.
        ids,owner,_,_=W.ownership_map(PLAN,8.)
        self.assertEqual([ids[value] for value in owner[2]],['west','west','west','east','east'])
        ids,owner,_,_=W.ownership_map(PLAN,8.,['east','west'])
        self.assertEqual([ids[value] for value in owner[2]],['west','west','east','east','east'])
        # Two regions on one point tie everywhere, and every cell falls to the first of them.
        shared=dict(PLAN,regions=[{'id':'west','center':[20,20]},{'id':'east','center':[20,20]}])
        for order in (['west','east'],['east','west']):
            ids,owner,_,_=W.ownership_map(shared,8.,order)
            self.assertEqual(ids,order);self.assertEqual(set(owner.ravel().tolist()),{0})


if __name__=='__main__':
    unittest.main()
