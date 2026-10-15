"""Correct exposed walking decks without excavating their hidden supports."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mirror_support as M
from world_layout import triangle_sample


def slab(x0,z0,x1,z1,height):
    a,b,c,d=np.array([[x0,height,z0],[x1,height,z0],[x0,height,z1],[x1,height,z1]],float)
    return np.array([[a,c,b],[b,c,d]])


def scene(ground=5.35):
    x=z=np.arange(0,62,2.)
    gx,gz=np.meshgrid(x,z);wet=gx>22
    height=np.where(wet,-2.,ground)
    w=SimpleNamespace(ids=['mirrorhold'],x0=0.,z0=0.,x=x,z=z,gx=gx,gz=gz,height=height,
        original_height=height.copy(),assembly_target=height.copy(),water={'mask':wet.copy()})
    w.height_at=lambda x,z:triangle_sample(w.height,x,z)
    objects=[{'node':name,'region':'mirrorhold','walk':True,'shift':np.zeros(3)} for name in M.LINKS]
    content=SimpleNamespace(objects=objects)
    floors={M.LINKS[0]:np.concatenate((slab(14,14,26,26,5),slab(16,16,24,24,4),slab(25.5,14,26,26,5.8))),
            M.LINKS[1]:slab(40,14,46,26,7)}
    return w,content,floors


class MirrorSupportTests(unittest.TestCase):
    def test_upper_envelope_excludes_covered_sleepers_and_preserves_visible_deck(self):
        triangles=np.concatenate((slab(0,0,10,10,4),slab(0,0,10,10,5)))
        height,distance=M.upper_floor_field(triangles,[2,8,12],[2,8,5])
        np.testing.assert_allclose(height,5)
        np.testing.assert_allclose(distance,[0,0,2])
        visible=M.exposed_triangles(triangles)
        self.assertEqual(len(visible),2)
        np.testing.assert_array_equal(visible[:,:,1],5)

    def test_clear_deck_is_not_excavated_for_its_underground_supports(self):
        w,content,floors=scene(4.5);before=w.height.copy()
        with patch.object(M,'walking_triangles',side_effect=lambda c,o:floors[o['node']]):
            report=M.apply_mirror_support(w,content)
        np.testing.assert_array_equal(before,w.height)
        self.assertTrue(all(link['correctedVertices']==0 for link in report['links']))

    def test_local_bank_cap_preserves_water_and_clears_every_exposed_floor_sample(self):
        w,content,floors=scene();before=w.height.copy();original=w.original_height.copy()
        targets=[o['shift'].copy() for o in content.objects]
        with patch.object(M,'walking_triangles',side_effect=lambda c,o:floors[o['node']]):
            report=M.apply_mirror_support(w,content)
        city,sanctuary=report['links']
        self.assertGreater(city['before']['buriedSamples'],0)
        self.assertEqual(city['after']['buriedSamples'],0)
        self.assertGreaterEqual(city['after']['minimumClearance'],M.GROUND_CLEARANCE-1e-8)
        self.assertLess(city['maximumCut'],.42)
        self.assertEqual(sanctuary['correctedVertices'],0)
        np.testing.assert_array_equal(w.height[w.water['mask']],before[w.water['mask']])
        np.testing.assert_array_equal(w.original_height,original)
        np.testing.assert_array_equal(w.height[w.gx<4],before[w.gx<4])
        for expected,obj in zip(targets,content.objects):np.testing.assert_array_equal(expected,obj['shift'])
        # The apron includes terrain vertices outside the deck's grid cells;
        # higher rail caps cannot leave the adjoining lower floor buried.
        z=np.linspace(14,26,121)
        self.assertTrue((w.height_at(np.full_like(z,21.),z)<=5-M.GROUND_CLEARANCE+1e-8).all())
        profile=w.height[10,:12]
        self.assertLess(float(np.max(np.abs(np.diff(profile[:10])))/2),.15)

    def test_large_mismatch_fails_before_creating_a_deep_cut(self):
        w,content,floors=scene(9.);before=w.height.copy()
        with patch.object(M,'walking_triangles',side_effect=lambda c,o:floors[o['node']]):
            with self.assertRaisesRegex(ValueError,'bounded 2 m'):
                M.apply_mirror_support(w,content)
        np.testing.assert_array_equal(w.height,before)

    def test_city_turnout_is_bounded_cut_only_and_persists_through_assembly(self):
        x=np.arange(884.,908.,2.);z=np.arange(784.,808.,2.);gx,gz=np.meshgrid(x,z)
        height=np.full(gx.shape,86.);wet=np.zeros(gx.shape,bool);wet[3,5]=True
        w=SimpleNamespace(ids=['mirrorhold'],x0=x[0],z0=z[0],x=x,z=z,gx=gx,gz=gz,
                          height=height.copy(),assembly_target=np.full(gx.shape,90.),
                          water={'mask':wet})
        w.owner_at=lambda x,z:np.zeros(np.broadcast(x,z).shape,dtype=int)
        before=w.height.copy();targets=w.assembly_target.copy()
        road_distance,_,_=M._city_road_profile(gx,gz)
        report=M.apply_city_quay_turnout(w)
        changed=np.abs(w.height-before)>1e-8
        self.assertEqual(report['name'],M.CITY_TURNOUT_NAME)
        self.assertGreater(report['changedVertices'],0)
        self.assertLessEqual(report['maximumCut'],M.CITY_TURNOUT_MAX_CUT)
        self.assertEqual(report['maximumFill'],0)
        self.assertEqual(report['changedWetVertices'],0)
        self.assertEqual(report['changedRoadCoreVertices'],0)
        np.testing.assert_array_equal(w.height[wet],before[wet])
        np.testing.assert_array_equal(w.height[road_distance<=M.CITY_TURNOUT_ROAD_HALF_WIDTH],
                                      before[road_distance<=M.CITY_TURNOUT_ROAD_HALF_WIDTH])
        np.testing.assert_array_equal(w.assembly_target[~changed],targets[~changed])
        np.testing.assert_allclose(w.assembly_target[changed],w.height[changed])
        self.assertTrue((w.height<=before+1e-10).all())

    def test_city_turnout_rejects_excessive_mound_before_mutation(self):
        x=np.arange(884.,908.,2.);z=np.arange(784.,808.,2.);gx,gz=np.meshgrid(x,z)
        height=np.full(gx.shape,100.);wet=np.zeros(gx.shape,bool)
        w=SimpleNamespace(ids=['mirrorhold'],x0=x[0],z0=z[0],x=x,z=z,gx=gx,gz=gz,
                          height=height.copy(),assembly_target=np.full(gx.shape,101.),
                          water={'mask':wet})
        w.owner_at=lambda x,z:np.zeros(np.broadcast(x,z).shape,dtype=int)
        before=w.height.copy();targets=w.assembly_target.copy()
        with self.assertRaisesRegex(ValueError,'requested cut exceeds 4 m'):
            M.apply_city_quay_turnout(w)
        np.testing.assert_array_equal(w.height,before)
        np.testing.assert_array_equal(w.assembly_target,targets)


if __name__=='__main__':unittest.main()
