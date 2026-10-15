"""Later grading must respect both natural banks and actual hard footings."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import world_layout as W


class DrainageApronTests(unittest.TestCase):
    def make_world(self):
        world=W.World.__new__(W.World)
        world.gx,world.gz=np.meshgrid(np.arange(0,162,2),np.arange(0,162,2))
        world.original_height=np.zeros_like(world.gx,dtype=float)
        world.height=np.full_like(world.original_height,8.)
        world.assembly_weight=np.zeros_like(world.height)
        world.quay_contacts=[]
        world.plan={}
        channel=world.gx<=20
        water={'river_mask':channel,'mask':channel,'depth':channel.astype(float)}
        return world,water

    def test_restores_full_ten_metre_bank_and_feathers_outside_it(self):
        world,water=self.make_world()
        original=world.original_height.copy()
        with patch.object(W.L,'water_fields',return_value=water):
            report=world.restore_drainage_corridor('test')
        np.testing.assert_array_equal(world.height[world.gx<=30],0)
        np.testing.assert_array_equal(world.height[world.gx>=62],8)
        profile=world.height[40]
        self.assertTrue((np.diff(profile)>=0).all())
        self.assertLess(np.max(np.abs(np.diff(profile)))/W.CELL,.4)
        np.testing.assert_array_equal(world.original_height,original)
        self.assertEqual(report['conflictingHardVertices'],0)
        self.assertEqual(world.drainage_restoration['test'],report)

    def test_a_graded_road_core_keeps_its_corridor_through_the_bank_apron(self):
        world,water=self.make_world()
        # A 4 m road runs along the bank inside the fully restored 10 m apron, rows 60..100 only.
        core=(world.gx>=24)&(world.gx<=28)&(world.gz>=60)&(world.gz<=100)
        world.roads=[{'id':'bank-road','points':[],'width':4.}]
        world.road_distance=np.where(core,0.,np.inf)
        with patch.object(W.L,'water_fields',return_value=water):
            report=world.restore_drainage_corridor('roads')
        np.testing.assert_array_equal(world.height[core],8.)
        np.testing.assert_array_equal(world.height[water['river_mask']],0.)
        # Away from the road the same bank is restored; beside it the restore fades within 8 m.
        self.assertEqual(float(world.height[10,13]),0.)
        self.assertTrue(0.<float(world.height[40,16])<8.)
        self.assertGreater(report['roadCoreVertices'],0)

    def test_hard_footing_stays_exact_with_continuous_exclusion(self):
        world,water=self.make_world()
        hard=(world.gx>=34)&(world.gx<=42)&(world.gz>=72)&(world.gz<=88)
        world.assembly_weight[hard]=1
        before=world.height.copy()
        with patch.object(W.L,'water_fields',return_value=water):
            report=world.restore_drainage_corridor('test')
        np.testing.assert_array_equal(world.height[hard],before[hard])
        np.testing.assert_array_equal(world.height[water['river_mask']],0)
        self.assertEqual(report['conflictingHardVertices'],int(hard.sum()))
        self.assertEqual(report['maximumRetainedFill'],8)
        # Exclusion rises smoothly towards the actual core, without a hard
        # rectangular one-cell jump between protected and restored terrain.
        dz,dx=np.gradient(world.height,W.CELL)
        near_core=(world.gx>=30)&(world.gx<=46)&(world.gz>=64)&(world.gz<=96)
        self.assertLess(float(np.max(np.hypot(dx,dz)[near_core])),.6)
        self.assertLess(world.height[10,18],world.height[40,18])

    def test_does_not_restore_sea_only_or_non_drainage_land(self):
        world,water=self.make_world()
        water['river_mask']=np.zeros_like(water['river_mask'])
        before=world.height.copy()
        with patch.object(W.L,'water_fields',return_value=water):
            self.assertIsNone(world.restore_drainage_corridor('test'))
        np.testing.assert_array_equal(world.height,before)


if __name__=='__main__':unittest.main()
