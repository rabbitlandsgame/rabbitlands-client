"""Physical lake containment without a hydraulic datum or architecture edit."""
from pathlib import Path
import sys,unittest
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mirror_lake_support as M

LAKE={'center':[0.,0.],'radii':[33.,33.],'level':80.,'depth':4.}
OUTLET={'points':[[-33.,0.,80.],[-100.,0.,70.]],'width':4.}


class MirrorLakeTests(unittest.TestCase):
    def test_low_seabed_gets_a_containing_bank_with_gentle_shoulders(self):
        x=np.linspace(0,95,1901);z=np.zeros_like(x);old=np.full_like(x,69.)
        new,weight,core,opening,distance=M.shore_fields(x,z,old,LAKE,OUTLET)
        self.assertAlmostEqual(float(np.interp(33,x,new)),80.3)
        self.assertGreater(float(np.interp(38,x,new)),80.)
        self.assertLess(float(np.interp(25,x,new)),80.)
        self.assertLess(float(np.max(abs(np.diff(new)/np.diff(x)))),.65)
        np.testing.assert_array_equal(new[distance>=M.FEATHER],old[distance>=M.FEATHER])
        np.testing.assert_array_equal(old,69.)

    def test_actual_outlet_stays_open_and_unchanged(self):
        x=np.linspace(-65,-33,100);z=np.zeros_like(x);old=76.+(x+33)*.1
        new,weight,core,opening,_=M.shore_fields(x,z,old,LAKE,OUTLET)
        np.testing.assert_allclose(new,old,atol=1e-12)
        np.testing.assert_array_equal(core,False)
        np.testing.assert_allclose(opening,1.)

    def test_flared_outlet_bank_is_restored_even_in_its_weak_transition(self):
        x=np.array([-30.]);z=np.array([12.5]);old=np.array([69.])
        new,weight,core,opening,distance=M.shore_fields(x,z,old,LAKE,OUTLET)
        self.assertGreater(opening[0],0.)
        self.assertLess(opening[0],.01)
        self.assertTrue(core[0],'Partial outlet bank cannot be reopened by the original-bed restoration pass')
        self.assertGreater(new[0],80.)

    def test_existing_higher_hills_are_not_cut_down_to_an_oval_platform(self):
        x,z=np.meshgrid(np.arange(-75,76,2.),np.arange(-75,76,2.))
        old=90.+x*.2
        new,*_=M.shore_fields(x,z,old,LAKE,OUTLET)
        np.testing.assert_array_equal(new[old>=81.5],old[old>=81.5])
        self.assertTrue((new>=old).all())

    def test_actual_floor_increase_is_detected_even_if_a_worse_old_burial_exists(self):
        points=np.array([[0,0],[1,0]],float);floor=np.array([2.,2.]);reference=np.array([5.,1.])
        world=SimpleNamespace(height_at=lambda x,z:np.array([5.,2.3]))
        report=M.floor_clearance(world,points,floor,reference)
        self.assertEqual(report['newlyBuriedSamples'],1)
        self.assertAlmostEqual(report['maximumAddedBurial'],.3)

    def test_wave_boundary_has_real_ground_before_the_domain_cutoff(self):
        class World:
            def height_at(self,x,z):
                return M.shore_fields(x,z,np.full(np.broadcast(x,z).shape,69.),LAKE,OUTLET)[0]
        report=M.shoreline_proof(World(),LAKE,OUTLET)
        self.assertTrue(all(q['uncontainedWaterEdgeSamples']==0 for q in report))
        self.assertGreater(report[0]['minimumClosedBankHeight'],80.)

    def test_actual_floor_caps_only_the_contributing_shared_terrain_vertices(self):
        world=SimpleNamespace(height=np.full((3,3),69.),x=np.array([0.,2.,4.]),z=np.array([0.,2.,4.]))
        target=np.full((3,3),81.5)
        fitted,count=M.fit_below_floors(world,(0,3,0,3),target,np.array([[.5,.5],[3.5,3.5]]),np.array([81.4,82.]))
        self.assertEqual(count,1)
        self.assertAlmostEqual(float(fitted[0,0]*.5+fitted[0,1]*.25+fitted[1,0]*.25),81.34)
        self.assertEqual(fitted[2,2],81.5)
        self.assertTrue((fitted>=world.height).all())


if __name__=='__main__':unittest.main()
