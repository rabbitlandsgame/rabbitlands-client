import copy
import math
import unittest
import continent_approaches as A


class AuthoredApproaches(unittest.TestCase):
    def frame(self):
        return dict(anchor=[42,10,0],outward=[1,0],approachCenterline=dict(
            schemaVersion=1,direction='inland-to-seam',stationHeight='bed',walkingBias=.03,
            stations=[[0,10,0],[8,9,-4.5],[20,9,-4.5],[39,10,0],[42,10,0]],
            collarStartIndex=0,laneHalfWidth=3,physicalHalfWidth=4.25,commonBoundaryLength=3))

    def test_exact_seven_seam_lanes_and_unchanged_three_metre_strip(self):
        f=self.frame();legacy={k:v for k,v in f.items() if k!='approachCenterline'}
        for lane in range(-3,4):
            for depth in (-1,0,1,2,3):self.assertEqual(A.point(f,depth,lane),A.point(legacy,depth,lane))

    def test_actual_bend_and_dense_cells_are_kept(self):
        f=self.frame();self.assertGreater(A.collar_length(f),42)
        self.assertLess(A.point(f,25)[2],-3.)
        for lane in range(-3,4):
            tiles=A.lane_tiles(f,dict(serverOrigin=[50,50]),lane)
            self.assertTrue(all(max(abs(a[0]-b[0]),abs(a[1]-b[1]))<=1 for a,b in zip(tiles,tiles[1:])))

    def test_invalid_narrow_and_short_contracts_are_rejected(self):
        f=self.frame();f['approachCenterline']['physicalHalfWidth']=3.5
        with self.assertRaises(ValueError):A.collar_length(f)
        f=self.frame();f['approachCenterline']['collarStartIndex']=3
        with self.assertRaisesRegex(ValueError,'42 m'):A.collar_length(f)

    def test_legacy_has_exact_same_straight_points(self):
        f=dict(anchor=[2,4,8],outward=[0,-1])
        self.assertEqual(A.point(f,40,3),[5,4.03,48])

    def test_sparse_first_segment_cannot_hide_a_changed_common_strip(self):
        f=self.frame();f['approachCenterline']['stations'][-2]=[37,10,2]
        with self.assertRaisesRegex(ValueError,'common boundary'):A.collar_length(f)


if __name__=='__main__':unittest.main()
