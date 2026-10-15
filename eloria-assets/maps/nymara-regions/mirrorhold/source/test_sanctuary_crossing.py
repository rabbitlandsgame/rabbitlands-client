"""Actual emitted deck, water and footing regression for the Sanctuary bridge."""
from pathlib import Path
import sys,unittest
import numpy as np

PACKAGE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PACKAGE.parent/'_toolkit')]
import glb_reader as G
from verify_runtime import VerticalRayIndex
import sanctuary_crossing as C


class SanctuaryCrossing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc,cls.body=G.load(PACKAGE/'world.glb')
        def triangles(prefix):return G.triangles(cls.doc,cls.body,G.named(cls.doc,prefix))
        cls.new_tri=triangles(C.DECK)
        if not len(cls.new_tri):raise AssertionError('The geographic road needs its real lake bridge')
        cls.new=VerticalRayIndex(cls.new_tri)
        cls.native=VerticalRayIndex(triangles('Walk_StreamCauseway_mirrorhold-four-gates'))
        cls.water=VerticalRayIndex(triangles('Water_'))
        cls.ground=VerticalRayIndex(triangles('Terrain_'))
        cls.piers=triangles('Structure_SanctuaryBridge_Piers')

    def test_former_lakebed_actor_tiles_have_four_metres_of_clearance(self):
        for x in np.arange(147.5,154.,1.):
            for z in np.arange(50.5,56.,1.):
                with self.subTest(x=x,z=z):
                    deck=self.new.top_hit(x,z)
                    self.assertIsNotNone(deck)
                    water=self.water.top_hit(x,z)
                    self.assertIsNotNone(water)
                    self.assertGreater(deck-water,3.9)

    def test_every_actual_walking_face_points_up_for_collision_raster(self):
        normal=np.cross(self.new_tri[:,1]-self.new_tri[:,0],self.new_tri[:,2]-self.new_tri[:,0])
        self.assertTrue(np.all(normal[np.linalg.norm(normal,axis=1)>1e-7,1]>0.))

    def test_native_causeway_has_no_copied_bridge_top(self):
        # Sample strictly inside the preserved original deck, avoiding shared
        # triangulation edges; the new bridge may only occupy its outer rim.
        for x in np.arange(121.1,128.,.2):
            for z in np.arange(57.6,60.,.2):
                with self.subTest(x=x,z=z):
                    self.assertIsNone(self.new.top_hit(x,z))
                    self.assertAlmostEqual(self.native.top_hit(x,z),4.,delta=.001)

    def test_visible_piers_reach_the_actual_bed_and_slab(self):
        self.assertTrue(len(self.piers))
        normal=np.cross(self.piers[:,1]-self.piers[:,0],self.piers[:,2]-self.piers[:,0])
        bottom=VerticalRayIndex(self.piers[normal[:,1]<-1e-7])
        top=VerticalRayIndex(self.piers[normal[:,1]>1e-7])
        for along in (8.,18.,28.,38.,48.,53.):
            i=min(int(np.searchsorted(C.DISTANCE,along,side='right')-1),len(C.CENTRES)-2)
            t=(along-C.DISTANCE[i])/(C.DISTANCE[i+1]-C.DISTANCE[i])
            q=C.CENTRES[i]*(1.-t)+C.CENTRES[i+1]*t
            with self.subTest(along=along):
                footing=bottom.top_hit(*q);cap=top.top_hit(*q)
                self.assertIsNotNone(footing);self.assertIsNotNone(cap)
                self.assertLessEqual(footing,self.ground.top_hit(*q))
                self.assertGreaterEqual(cap,3.29)


if __name__=='__main__':unittest.main()
