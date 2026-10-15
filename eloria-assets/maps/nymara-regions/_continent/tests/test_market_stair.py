"""The Amberwood market stair descends from the canopy deck along its authored line to the actual ground."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import amberwood_access as A


class MarketStairTests(unittest.TestCase):
    landing=np.array([510.,541.5]);direction=np.array([7.,-15.5])/np.hypot(7.,15.5)

    def test_a_low_deck_keeps_the_shortest_run(self):
        length,start,ground=A.market_stair_run(lambda x,z:50.,self.landing,self.direction,55.)
        self.assertEqual(length,A.MARKET_STAIR_MINIMUM_METRES)
        np.testing.assert_allclose(start,self.landing-self.direction*length)
        self.assertAlmostEqual(ground,50.025)

    def test_a_high_deck_lengthens_the_run_until_the_grade_is_walkable(self):
        length,start,ground=A.market_stair_run(lambda x,z:43.85-.025,self.landing,self.direction,57.54)
        rise=57.54-43.85
        self.assertLessEqual(rise/(length-A.MARKET_STAIR_LEVEL_METRES),A.MARKET_STAIR_GRADE)
        self.assertGreater(rise/(length-2-A.MARKET_STAIR_LEVEL_METRES),A.MARKET_STAIR_GRADE)
        self.assertEqual(length,29.)

    def test_ground_falling_away_faster_than_the_stair_is_rejected(self):
        # Every extra metre of run loses a metre of ground: no length keeps the grade.
        def height_at(x,z):
            return 57.54-14.-1.*np.linalg.norm(np.array([x,z])-self.landing)
        with self.assertRaises(ValueError):
            A.market_stair_run(height_at,self.landing,self.direction,57.54)


if __name__=='__main__':
    unittest.main()
