"""Retained delta houses use hydraulic or soil datums, never old trenches."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assemblies as A
import landscape as L


class ManymouthBanksTests(unittest.TestCase):
    def test_paddy_floor_clears_the_real_raised_distributary(self):
        plan=L.load_plan();site=plan['assembly_sites']['manymouth_delta.paddy_hamlet']
        # Actual source compound dimensions around its unchanged world anchor.
        x,z=np.meshgrid(np.linspace(-18,18,31),np.linspace(-26,26,43))
        x+=site['center'][0];z+=site['center'][1]
        ground=L.height_at(x,z,plan=plan);water=L.water_fields(x,z,height=ground,plan=plan)
        self.assertGreater(np.count_nonzero(water['mask']),300)
        self.assertGreater(float(water['surface'].max()),2.)
        self.assertGreater(site['water_level']+1.75-float(water['surface'].max()),1.)
        self.assertLess(float(ground.max())-(site['water_level']+1.),2.)

    def test_upper_bank_hamlet_uses_soil_with_intact_lorecourt(self):
        names=('east_hamlet_house_00','Lore_stelae_court','Landing_lore_court','Landing_shore_lore_court')
        p=[{'node':n,'kind':'building' if n.endswith('00') else 'structure'} for n in names]
        bounds={n:([290,1.75,-123],[294,5,-119]) for n in names}
        a=A.build_assemblies('manymouth_delta',p,bounds,lambda x,z:-4.31)['manymouth_delta.east_hamlet']
        self.assertEqual(set(a.nodes),set(names))
        self.assertEqual(a.datum,'terrain')
        self.assertEqual(a.reference_y,0.)
        shift=a.shift_to(lambda xz:xz+np.array([420,1200]),lambda x,z:12.6)
        self.assertAlmostEqual(shift[1],12.6)
        self.assertAlmostEqual(1.75+shift[1]-12.6,1.75)


if __name__=='__main__':unittest.main()
