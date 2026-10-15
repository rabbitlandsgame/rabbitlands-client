"""Regressions for actual exported woodland stream and inlet approaches."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
import numpy as np

CLIENT=Path(__file__).resolve().parents[2]
REGIONS=CLIENT/'eloria-assets/maps/nymara-regions'
sys.path.insert(0,str(REGIONS/'_toolkit'))
import glb_reader as G
from verify_runtime import VerticalRayIndex


class AmberWaterRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc,cls.body=G.load(REGIONS/'amberwood/world.glb')
        cls.named=[(i,n.get('name','')) for i,n in enumerate(cls.doc['nodes']) if 'mesh' in n]
        top=G.triangles(cls.doc,cls.body,[i for i,n in cls.named if n.startswith(('Terrain_','Walk_'))])
        upward=np.cross(top[:,1]-top[:,0],top[:,2]-top[:,0])[:,1]>1e-8
        cls.ground=VerticalRayIndex(top[upward])
        cls.water=VerticalRayIndex(G.triangles(cls.doc,cls.body,[i for i,n in cls.named if n.startswith('Water_')]))

    def test_clipped_crossing_tops_survive_the_upward_collision_raster(self):
        for crossing in ('tower-rill','north-burn','moor-inlet','cinder-rill'):
            with self.subTest(crossing=crossing):
                nodes=[i for i,n in self.named if n.startswith('Walk_StreamBridge_Amber_'+crossing)]
                self.assertTrue(nodes)
                triangles=G.triangles(self.doc,self.body,nodes)
                area=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,1]
                self.assertTrue((area>=-1e-8).all())
                self.assertGreater(int((area>1e-8).sum()),0)

    def test_former_flooded_tower_stream_and_inlet_have_a_dry_floor(self):
        for x,z in ((76.5,-214.5),(38.056366,-259.),(40.9792,-260.9396),(-100.,100.)):
            with self.subTest(x=x,z=z):
                floor=self.ground.top_hit(x,z)
                water=self.water.top_hit(x,z)
                self.assertIsNotNone(floor)
                self.assertIsNotNone(water)
                self.assertGreater(floor,water+.02)

    def test_moor_bridge_meets_its_rising_west_bank_without_a_step(self):
        # The former flat deck ended with a 31 cm lip at x=-131.38.
        for lateral in (-3.,0.,3.):
            samples=np.linspace(-133.,-128.,101)
            heights=[self.ground.top_hit(x,100.+lateral) for x in samples]
            self.assertTrue(all(h is not None for h in heights))
            grades=np.abs(np.diff(heights))/np.diff(samples)
            self.assertLess(float(grades.max()),.4)

    def test_far_tier_does_not_require_omitted_ground_detail(self):
        sys.path.insert(0,str(REGIONS/'amberwood/source'))
        import tower_bypasses
        distant=SimpleNamespace(placements=[])
        tower_bypasses._seat_fallen_tree(distant)
        self.assertEqual(distant.placements,[])


if __name__=='__main__':
    unittest.main()
