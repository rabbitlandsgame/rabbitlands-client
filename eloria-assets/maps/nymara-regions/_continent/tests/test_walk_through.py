"""Structures built to be passed are no solids for road alignment; their columns, walls and an archive are."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content as C
import world_layout as W


class WalkThroughTests(unittest.TestCase):
    def test_gates_arches_arcades_and_portals_are_passed_but_their_columns_walls_and_an_archive_are_not(self):
        for name in ('Landmark_GreatArch','Landmark_AncientArch_3','Landmark_ForestGate_1','Gate_East','Landmark_Waygate',
                     'Arcade_UpperCourt','Colonnade_ritual_plaza','Causeway_spoke_harbour_isle','Temple_VaultPortal','RootArch','WaterGate','Landmark_SeaArch'):
            self.assertTrue(C.walk_through(name),name)
        for name in ('Landmark_ArchColumn_0','SerpentGateColumn_1','Landmark_GateWall','Landmark_GateWing_1','House_archive-workers',
                     'Landmark_Building_Lodge_27','Landmark_Watchtower_5','Shopfront_four-gates-reedworks','Landmark_sunmane_march_north-track'):
            self.assertFalse(C.walk_through(name),name)

    def test_a_structure_registered_as_passable_keeps_the_clearance_but_is_no_solid(self):
        world=W.World.__new__(W.World)
        world.x=np.arange(0,101,W.CELL,dtype=float);world.z=np.arange(0,101,W.CELL,dtype=float);world.x0=world.z0=0.
        world.height=np.zeros((len(world.z),len(world.x)));world.obstacles=np.zeros(world.height.shape,bool);world.solids=np.zeros(world.height.shape,bool)
        world.structure_obstacle([40,0,40],[60,8,60],solid=False)
        self.assertTrue(world.obstacles.any());self.assertFalse(world.solids.any())
        world.structure_obstacle([40,0,40],[60,8,60])
        self.assertTrue(world.solids.any())


if __name__=='__main__':
    unittest.main()
