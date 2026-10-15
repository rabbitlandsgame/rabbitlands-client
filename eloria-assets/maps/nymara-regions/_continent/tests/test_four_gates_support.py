"""The east approach is visible earthwork, with protected banks and buildings."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import four_gates_support as F
from world_layout import triangle_sample


class FourGatesSupportTests(unittest.TestCase):
    def test_profile_keeps_sound_joins_and_fits_the_climb_in_distance(self):
        points=np.c_[np.linspace(0,80,29),np.zeros(29)]
        levels=np.linspace(20,36,29)-12*np.exp(-((points[:,0]-30)/9)**2)
        profile=F.approach_profile(points,levels)
        np.testing.assert_allclose(profile[[0,-1]],levels[[0,-1]])
        self.assertLess(np.max(np.abs(np.diff(profile))/np.linalg.norm(np.diff(points,axis=0),axis=1)),.45)
        self.assertGreater(profile[11]-levels[11],10)

    def test_short_impossible_ascent_cannot_be_hidden_in_the_ground(self):
        with self.assertRaisesRegex(ValueError,'longer authored climb'):
            F.approach_profile(np.array([[0.,0],[1,0],[2,0]]),np.array([0.,10,20]))

    def test_path_field_projects_safely_and_broadcasts(self):
        h,d,s,length=F.path_field(np.array([[0.,0],[10,0]]),[2.,4.],np.array([-2,5,12]),2.)
        np.testing.assert_allclose(h,[2,3,4]);np.testing.assert_allclose(s,[0,5,10])
        np.testing.assert_allclose(d,[np.sqrt(8),2,np.sqrt(8)]);self.assertEqual(length,10)

    def test_full_width_earthwork_preserves_wet_ground_and_other_region_footings(self):
        x=z=np.arange(0,162,2.);gx,gz=np.meshgrid(x,z)
        natural=20.+(gx-30)*.2
        old=natural-12*np.exp(-((gx-64)/8)**2)*np.exp(-((gz-80)/10)**2)
        points=np.c_[np.linspace(30,110,29),np.zeros(29),np.full(29,80.)]
        wet=(gx>74)&(gx<90)&(gz<62)
        w=SimpleNamespace(ids=['four_gates'],x0=0.,z0=0.,x=x,z=z,gx=gx,gz=gz,height=old.copy(),
            original_height=natural.copy(),assembly_target=old.copy(),water={'mask':wet},
            roads=[{'id':F.ROAD,'width':4.,'points':points.tolist()}])
        w.height_at=lambda x,z:triangle_sample(w.height,x,z)
        points[:,1]=w.height_at(points[:,0],points[:,2]);w.roads[0]['points']=points.tolist()
        obj={'region':'mirrorhold','node':'RealHouse','kind':'building','collides':True,
            'low':np.array([52.,20,96]),'high':np.array([62.,30,104]),'shift':np.zeros(3)}
        c=SimpleNamespace(objects=[obj]);saved=obj['shift'].copy()
        with patch.object(F,'ENTRY',np.array([30.,80.])),patch.object(F,'EXIT',np.array([110.,80.])):
            report=F.apply_four_gates_support(w,c)
        self.assertTrue(report['occupiedFootingsUnchanged']);self.assertTrue(report['waterGroundUnchanged'])
        self.assertLess(report['fullRoadGrades']['after']['maximum'],.45)
        self.assertGreater(report['maximumFill'],10)
        np.testing.assert_array_equal(w.height[wet],old[wet]);np.testing.assert_array_equal(w.height[gz<40],old[gz<40])
        np.testing.assert_array_equal(w.original_height,natural);np.testing.assert_array_equal(saved,obj['shift'])
        np.testing.assert_array_equal(np.array(w.roads[0]['points'])[:,[0,2]],points[:,[0,2]])


if __name__=='__main__':unittest.main()
