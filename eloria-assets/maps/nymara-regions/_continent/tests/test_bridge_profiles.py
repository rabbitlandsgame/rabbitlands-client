from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge_profiles as P


class BridgeProfileTests(unittest.TestCase):
    def test_canonical_stations_retain_authored_breaklines_once(self):
        stations=P.canonical_stations(-6.,0.,12.,18.)
        self.assertEqual(np.count_nonzero(stations==0.),1)
        self.assertEqual(np.count_nonzero(stations==6.),1)
        self.assertEqual(np.count_nonzero(stations==12.),1)
        self.assertLessEqual(float(np.diff(stations).max()),.5)

    def test_solved_arch_is_flat_by_representation_and_has_one_gentle_crest(self):
        profile=P.solve_arch(np.array([0.,6.,12.]),np.array([.85,.85,.85]),np.full(3,np.inf),
            start=-6.,wet_start=0.,wet_end=12.,end=18.,left_bounds=(2.025,2.025),
            right_bounds=(2.025,2.025),maximum_grade=.64,crown_metres=P.arch_rise(12.,.85,.64))
        slope=np.diff(profile.heights)/np.diff(profile.stations)
        middle=np.searchsorted(profile.stations,profile.middle)
        self.assertTrue((slope[:middle]>=-1e-10).all())
        self.assertTrue((slope[middle:]<=1e-10).all())
        self.assertLess(float(np.abs(slope).max()),.1)
        # Width is absent from the representation: equal stations are exactly equal.
        np.testing.assert_array_equal(profile.at(np.array([4.,4.,4.])),np.repeat(profile.at(4.),3))

    def test_per_station_constraints_bound_grade_and_select_one_crest(self):
        stations=P.canonical_stations(-2.,0.,2.,4.,spacing=1.)
        rows,limits,curvature,middle=P.per_station_single_crest_constraints(stations,1.,.1,.64)
        heights=1.-.1*np.abs(stations-1.)
        self.assertTrue((rows@heights<=limits+1e-10).all())
        self.assertEqual(stations[middle],1.)
        self.assertEqual(len(curvature),len(stations)-2)


if __name__=='__main__':unittest.main()
