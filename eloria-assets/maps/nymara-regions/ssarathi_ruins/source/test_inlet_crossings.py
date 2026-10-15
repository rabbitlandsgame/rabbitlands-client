"""Emitted regression: the public approach never follows the tidal inlet bed."""
from pathlib import Path
import sys,unittest
import numpy as np
PACKAGE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PACKAGE.parent/'_toolkit')]
import glb_reader as G
from verify_runtime import VerticalRayIndex
import inlet_crossings as C


class InletCrossings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc,cls.body=G.load(PACKAGE/'world.glb')
        cls.water=VerticalRayIndex(G.triangles(cls.doc,cls.body,G.named(cls.doc,'Water_')))
        cls.ground=VerticalRayIndex(G.triangles(cls.doc,cls.body,G.named(cls.doc,'Terrain_')))

    def triangles(self,prefix):
        return G.triangles(self.doc,self.body,G.named(self.doc,prefix))

    def test_two_former_submerged_centres_have_clear_water_below_a_slab(self):
        for name,centre in [('EastInlet',[226.,-74.5]),('NorthInlet',[137.5,-224.])]:
            floor=VerticalRayIndex(self.triangles('Walk_StreamCauseway_Ssarathi'+name))
            for lateral in range(-3,4):
                q=np.array(centre)+([lateral,0.] if name=='EastInlet' else [0.,lateral])
                with self.subTest(name=name,lane=lateral):
                    top=floor.top_hit(*q);water=self.water.top_hit(*q)
                    self.assertIsNotNone(top);self.assertIsNotNone(water)
                    self.assertGreater(top-water,3.9)
            slab=self.triangles('Structure_Ssarathi'+name+'_Ashlar')
            normal=np.cross(slab[:,1]-slab[:,0],slab[:,2]-slab[:,0])
            bottom=VerticalRayIndex(slab[normal[:,1]<-1e-7]).top_hit(*centre)
            self.assertIsNotNone(bottom)
            self.assertAlmostEqual(floor.top_hit(*centre)-bottom,.8,delta=.001)

    def test_all_piers_contact_the_actual_inlet_bed(self):
        count=0
        for spec in C.CROSSINGS.values():
            c,d,_,_,_=C.geometry(spec)
            triangles=self.triangles('Structure_Ssarathi'+spec['name']+'_Piers')
            normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
            bottom=VerticalRayIndex(triangles[normals[:,1]<-1e-7])
            top=VerticalRayIndex(triangles[normals[:,1]>1e-7])
            for along in spec['piers']:
                if along>=d[-1]:continue
                i=min(int(np.searchsorted(d,along,side='right')-1),len(c)-2)
                t=(along-d[i])/(d[i+1]-d[i]);q=c[i]*(1.-t)+c[i+1]*t
                with self.subTest(name=spec['name'],along=along):
                    low=bottom.top_hit(*q);high=top.top_hit(*q)
                    self.assertIsNotNone(low);self.assertIsNotNone(high)
                    self.assertLessEqual(low,self.ground.top_hit(*q)+.001)
                    self.assertGreaterEqual(high,3.29)
                count+=1
        self.assertEqual(count,10)

    def test_new_walking_faces_are_upward_for_the_real_collision_raster(self):
        for spec in C.CROSSINGS.values():
            tri=self.triangles('Walk_StreamCauseway_Ssarathi'+spec['name'])
            self.assertGreater(len(tri),0)
            normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            self.assertTrue(np.all(normal[np.linalg.norm(normal,axis=1)>1e-7,1]>0.))


if __name__=='__main__':unittest.main()
