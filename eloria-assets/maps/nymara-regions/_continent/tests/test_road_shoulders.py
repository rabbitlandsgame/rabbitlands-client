"""Exterior road banks interpolate without changing any walkable road core."""
from pathlib import Path
import sys,unittest
import numpy as np
from scipy.ndimage import distance_transform_edt
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from world_layout import road_shoulder_field


class RoadShoulderTests(unittest.TestCase):
    def test_different_height_roads_do_not_create_a_nearest_road_wall(self):
        z,x=np.indices((55,65));active=((x>=20)&(x<=22))|((x>=42)&(x<=44))
        base=np.full(x.shape,10.);target=np.where(x<32,20.,60.)
        distance=distance_transform_edt(~active)*2
        result=road_shoulder_field(target,active,base,distance)
        np.testing.assert_array_equal(result[active],target[active])
        np.testing.assert_array_equal(result[distance>=24],base[distance>=24])
        # The previous nearest-index extension jumped40m at this bisector.
        self.assertLess(float(np.max(np.abs(np.diff(result[27,23:42])))),2.5)
        self.assertTrue((np.diff(result[27,23:42])>0).all())

    def test_real_footings_remain_exact_boundary_constraints(self):
        z,x=np.indices((35,45));active=(x>=6)&(x<=8);base=np.full(x.shape,10.)
        fixed=(x>=18)&(x<=20)&(z>=14)&(z<=18);base[fixed]=24.
        distance=distance_transform_edt(~active)*2
        result=road_shoulder_field(np.full(x.shape,15.),active,base,distance,fixed)
        np.testing.assert_array_equal(result[fixed],base[fixed])
        np.testing.assert_array_equal(result[active],15.)
        self.assertGreater(result[16,17],20.)
        self.assertTrue(np.isfinite(result).all())

    def test_empty_bank_is_an_exact_noop(self):
        base=np.arange(36.).reshape(6,6);active=np.zeros_like(base,bool)
        result=road_shoulder_field(base,active,base,np.full(base.shape,50.))
        np.testing.assert_array_equal(result,base)


if __name__=='__main__':unittest.main()
