"""Timber joins add real floor without covering the retained floor twice."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manymouth_access import subtract
from bridge_export import _area_xz,triangulate_floor


class FishingFloorTests(unittest.TestCase):
    def test_existing_floor_hole_conserves_exact_visible_area(self):
        outer=np.array([[0,1.75,0],[0,1.75,6],[6,1.75,6],[6,1.75,0]],float)
        existing=np.array([[2,2],[4,2],[4,4],[2,4]],float)
        pieces=subtract([outer],existing)
        self.assertAlmostEqual(sum(-_area_xz(p) for p in pieces),32.)
        triangles=np.concatenate([triangulate_floor(p) for p in pieces])
        normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        self.assertTrue((normal[:,1]>0).all())
        np.testing.assert_array_equal(triangles[:,:,1],1.75)
        center=triangles[:,:,[0,2]].mean(axis=1)
        self.assertFalse(np.any(np.all((center>2)&(center<4),axis=1)))

    def test_intersecting_links_do_not_emit_coplanar_duplicate_area(self):
        first=np.array([[0,1.75,0],[0,1.75,2],[6,1.75,2],[6,1.75,0]],float)
        second=np.array([[2,1.75,-2],[2,1.75,4],[4,1.75,4],[4,1.75,-2]],float)
        pieces=subtract([second],first[::-1][:,[0,2]])
        self.assertAlmostEqual(-_area_xz(first)+sum(-_area_xz(p) for p in pieces),20.)
        # Subtraction is a no-op outside the retained occupied footprint.
        far=first.copy();far[:,0]+=30
        np.testing.assert_array_equal(subtract([far],first[::-1][:,[0,2]])[0],far)


if __name__=='__main__':unittest.main()
