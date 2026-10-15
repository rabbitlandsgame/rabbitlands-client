"""Retained solids reach the router where the structures finally stand, after the prepare stages moved them."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content as C
import world_layout as W


def world():
    w=W.World.__new__(W.World)
    w.x=np.arange(0,201,W.CELL,dtype=float);w.z=np.arange(0,201,W.CELL,dtype=float);w.x0=w.z0=0.
    w.height=np.zeros((len(w.z),len(w.x)));w.obstacles=np.zeros(w.height.shape,bool);w.solids=np.zeros(w.height.shape,bool)
    return w


def structure(node,low,high,collides=True,walk=False):
    return {'region':'amberwood','node':node,'kind':'prop','collides':collides,'walk':walk,'low':np.array(low,float),'high':np.array(high,float)}


class ObstacleRegistrationTests(unittest.TestCase):
    def test_a_stall_moved_by_a_prepare_stage_is_a_solid_where_it_stands_and_not_where_it_stood(self):
        w=world();stall=structure('Prop_MarketStall_6',[40,0,40],[44,3,43])
        content=SimpleNamespace(world=w,objects=[stall,structure('Gate_East',[100,0,100],[110,8,104]),structure('Prop_Sack_1',[150,0,150],[151,1,151],collides=False)])
        # The prepare stage moves the stall 15 m east and 4 m south before anything is registered.
        delta=np.array([15.,0.,4.]);stall['low']+=delta;stall['high']+=delta
        self.assertEqual(C.Content.register_obstacles(content),2)
        self.assertTrue(w.solids[w.cell_of((57.,45.5))])      # where the stall stands now
        self.assertFalse(w.solids[w.cell_of((42.,41.5))])     # where it stood at load: no phantom solid
        self.assertFalse(w.solids[w.cell_of((105.,102.))]);self.assertTrue(w.obstacles[w.cell_of((105.,102.))])   # a gate is passed, with clearance
        self.assertFalse(w.obstacles[w.cell_of((150.5,150.5))])   # a loose sack collides with nothing

    def test_every_retained_solid_is_boxed_for_the_alignment_audit_as_it_is_registered(self):
        w=world();house=structure('House_lineage',[20,0,20],[30,6,28]);house['kind']='building'
        content=SimpleNamespace(world=w,objects=[house])
        C.Content.register_obstacles(content)
        boxes=C.Content.solid_boxes(content)
        self.assertEqual([(r,n) for r,n,_,_ in boxes],[('amberwood','House_lineage')])
        low,high=boxes[0][2],boxes[0][3]
        self.assertTrue(w.solids[w.cell_of(((low[0]+high[0])/2,(low[2]+high[2])/2))])


if __name__=='__main__':
    unittest.main()
