"""The retained tidal compound must occupy a real low estuary bank."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import landscape as L
import assemblies as A


class NorthFishingSiteTests(unittest.TestCase):
    def test_site_is_low_coast_with_no_elevated_river_in_support_apron(self):
        plan=L.load_plan();site=plan['assembly_sites']['manymouth_delta.north_fishing']
        center=np.array(site['center'],float)
        x,z=np.meshgrid(np.arange(-48,49,2),np.arange(-40,41,2))
        x=x+center[0];z=z+center[1]
        ground=L.height_at(x,z,plan=plan);water=L.water_fields(x,z,height=ground,plan=plan)
        self.assertGreater(np.mean(water['mask']),.1)
        self.assertGreater(np.mean((ground>0)&(ground<3)),.1)
        np.testing.assert_allclose(water['surface'][water['mask']],site['water_level'],atol=.01)

    def test_intact_landing_projects_into_natural_water(self):
        plan=L.load_plan();site=plan['assembly_sites']['manymouth_delta.north_fishing']
        # Surveyed source bounds and its same assembly reference; full compose
        # additionally checks all nine actual boxes and linked server points.
        reference=np.array([92.0790836406851,-238.45599668954367])
        landing=np.array([109.78096008300781,-244.65740108857425])
        point=landing-reference+site['center']
        y=L.height_at(*point,plan=plan);water=L.water_fields(*point,height=y,plan=plan)
        self.assertTrue(water['mask'])
        self.assertLess(float(y),-.4)
        self.assertGreater(float(y),-4.)
        self.assertAlmostEqual(float(water['surface']),site['water_level'])
        self.assertEqual(A.placement_group('manymouth_delta',{'node':'Landing_north_fishing'}),'manymouth_delta.north_fishing')
        for i in range(4):
            for kind in ('house','porch'):
                self.assertEqual(A.placement_group('manymouth_delta',{'node':f'north_fishing_{kind}_{i:02d}'}),'manymouth_delta.north_fishing')


if __name__=='__main__':unittest.main()
