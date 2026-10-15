"""The Amberwood root ramp: a timber deck at the walking grade over the Great Tree's ungradable root flank, which
the collision export serves as a deck, so the root plateau joins the village floor."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np
from scipy.ndimage import label

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import amberwood_access as A
import collision_export as C
import scene_io as S


def flank(x,z):
    """The village floor at 41 m west of x 492, the root plateau at 50 m east of x 506, a smooth flank between."""
    t=np.clip((np.asarray(x,float)-492.)/14.,0.,1.)
    return 41.+9.*t*t*(3.-2.*t)+0.*np.asarray(z,float)


class RootRampTests(unittest.TestCase):
    world=SimpleNamespace(height_at=flank,regions={'amberwood':{'center':[510.,540.]}},ids=['amberwood'])
    content=SimpleNamespace(documents={'amberwood':({},b'')},objects=[])

    def deck(self):
        foot,head=A.root_ramp_line(self.world)
        return A.ramp_mesh(self.world,self.content,foot,head,'timber',half_width=A.ROOT_RAMP_HALF_WIDTH,region='amberwood')

    def test_the_line_starts_on_the_flat_yard_and_stops_beside_the_post(self):
        foot,head=A.root_ramp_line(self.world)
        np.testing.assert_allclose(foot,[484.,472.]);np.testing.assert_allclose(head,[505.,472.])
        self.assertLess(float(np.linalg.norm(np.array([506.55,471.26])-head)),3.)   # the Motherroot Voice's post
        self.assertEqual(float(flank(*foot)),41.)

    def test_the_deck_keeps_the_grade_and_meets_the_ground_at_both_ends(self):
        deck,report=self.deck()
        self.assertLessEqual(report['maximumGrade'],.47)
        self.assertLessEqual(max(report['contactLift']),.08)
        self.assertGreater(report['maximumSupportHeight'],1.)
        lift=deck.positions[:,1]-flank(deck.positions[:,0],deck.positions[:,2])
        self.assertGreaterEqual(float(lift.min()),.0249)
        self.assertGreater(float(deck.positions[:,1].max()-deck.positions[:,1].min()),8.5)

    def test_the_served_fold_joins_the_yard_to_the_plateau_only_over_the_deck(self):
        deck,_=self.deck();triangles=deck.positions[deck.indices.reshape(-1,3)]
        x0,z1,cell=470.,490.,C.CELL;width,rows=int(50/cell),int(30/cell)   # x 470..520, z 460..490
        gx,gz=np.meshgrid(x0+(np.arange(width)+.5)*cell,z1-(np.arange(rows)+.5)*cell)
        surface=flank(gx,gz);grade=np.hypot(flank(gx+.5,gz)-flank(gx-.5,gz),flank(gx,gz+.5)-flank(gx,gz-.5))
        covered,top=S.GR.rasterise(triangles,width,rows,x0,z1,cell,upward=1/np.sqrt(1+C.MAX_GRADE**2)-1e-9)
        support=covered&(top>=surface-.03)
        def tiles(walkable):
            return walkable.reshape(rows//2,2,width//2,2).all(axis=(1,3))
        def joined(mask):
            labels,_=label(mask);yard=labels[int(z1-472.5),int(486.5-x0)];plateau=labels[int(z1-472.5),int(508.5-x0)]
            return bool(yard) and yard==plateau
        self.assertGreater(float(grade[(gx>495)&(gx<501)&(np.abs(gz-472)<1)].min()),C.MAX_GRADE)   # the bare flank blocks
        self.assertFalse(joined(tiles(grade<=C.MAX_GRADE)))
        self.assertTrue(joined(tiles((grade<=C.MAX_GRADE)|support)))

    def test_posts_stand_in_the_ground_and_rails_run_along_the_deck_edges(self):
        deck,_=self.deck();posts,rails=A.root_ramp_rails(self.world,deck,22)
        self.assertLess(float((posts.positions[:,1]-flank(posts.positions[:,0],posts.positions[:,2])).min()),0.)
        self.assertGreater(float(rails.positions[:,1].min()-deck.positions[:,1].min()),.8)
        self.assertTrue(np.all(np.abs(np.abs(rails.positions[:,2]-472.)-A.ROOT_RAMP_HALF_WIDTH)<1e-6))
        self.assertEqual(len(posts.positions),2*8*len(A.M.box((1.,1.,1.)).positions))   # eight posts a side, one box each

    def test_the_motherroot_voice_stands_in_front_of_the_root_hatch(self):
        post=A.motherroot_voice_post(self.world);hatch=np.array([512.,513.])
        distance=float(np.linalg.norm(post[[0,2]]-hatch))
        self.assertGreater(distance,2.);self.assertLess(distance,6.)   # in the yard the door road serves, clear of the threshold
        self.assertLess(float(post[0]),512.-1.4)   # west of the east-facing door's frame
        self.assertEqual(float(post[1]),float(flank(post[0],post[2])))

    def test_the_reserve_covers_the_deck_and_its_clearance(self):
        foot,head=A.root_ramp_line(self.world);low,high=A.root_ramp_reserve(foot,head)
        np.testing.assert_allclose(low,[484.-4.4,472.-4.4]);np.testing.assert_allclose(high,[505.+4.4,472.+4.4])

    def test_loose_props_are_moved_off_the_strip_and_assemblies_stay(self):
        def prop(node,x,z,**extra):
            return {'region':'amberwood','node':node,'kind':'prop','shift':np.zeros(3),
                    'low':np.array([x-.5,41.,z-.5]),'high':np.array([x+.5,42.,z+.5]),**extra}
        content=SimpleNamespace(objects=[prop('Prop_Crate_1',490.,473.),prop('Prop_Crate_2',490.,480.),
                                         prop('Prop_Tent_1',495.,472.,assembly='amberwood.ridge-camp')],mapping={},bounds_by_name={})
        foot,head=A.root_ramp_line(self.world);direction=(head-foot)/np.linalg.norm(head-foot)
        cleared=A.clear_strip_props(content,foot,direction,0.,21.,A.ROOT_RAMP_HALF_WIDTH+A.ROOT_RAMP_CLEARANCE_METRES)
        self.assertEqual([c['node'] for c in cleared],['Prop_Crate_1'])
        self.assertGreater(float(content.objects[0]['low'][2]),472.+A.ROOT_RAMP_HALF_WIDTH+A.ROOT_RAMP_CLEARANCE_METRES-1e-9)
        self.assertEqual(content.mapping[('amberwood','Prop_Crate_1')].tolist(),content.objects[0]['shift'].tolist())
        np.testing.assert_array_equal(content.objects[1]['low'],[489.5,41.,479.5])
        np.testing.assert_array_equal(content.objects[2]['low'],[494.5,41.,471.5])


if __name__=='__main__':
    unittest.main()
