"""Saved road faces must follow the terrain between vertices as well as at them."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from terrain_export import conform_road_faces, encoded_road_faces
from world_layout import triangle_sample


def world(heights,x0=0.,z0=0.):
    grid=np.asarray(heights,float)
    return SimpleNamespace(x0=x0,z0=z0,height=grid,
        height_at=lambda x,z:triangle_sample(grid,x,z,x0,z0))


def attributes(faces):
    x,z=faces[:,:,0],faces[:,:,2]
    return np.stack((2*x-z,3*z+x),axis=2),np.stack((x+z,x-z,x*0+.7,.1*x+.2*z),axis=2)


def signed_area(faces):
    a,b=faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]
    return (a[:,0]*b[:,2]-a[:,2]*b[:,0])*.5


class RoadConformanceTests(unittest.TestCase):
    def test_observed_float32_slivers_keep_nonzero_footprint_and_all_attributes(self):
        # Captured from Amberwood's saved road to Grey Moors after terrain cuts.
        reversed_face=np.array([[491.7680177688604,41.32873489864652,552.2319822311397],
            [491.0674877166748,41.40855268344756,552.9325113296509],
            [491.30099805196124,41.381946791400885,552.6990019480387]])
        collapsed=np.array([[498.,43.021644287109375,546.],
            [497.93092155456543,42.99129198680537,546.0690779685974],
            [497.930921792984,42.99129200112218,546.069078207016]])
        faces=np.array([reversed_face,collapsed,reversed_face[::-1]])
        uv=np.arange(18,dtype=float).reshape(3,3,2)
        rgba=np.arange(36,dtype=float).reshape(3,3,4)/36.
        saved=[v.copy() for v in (faces,uv,rgba)]
        out,out_uv,out_rgba,report=encoded_road_faces(faces,uv,rgba)
        self.assertEqual(report,{'inputFaces':3,'collapsedFaces':1,'reorientedFaces':2,'outputFaces':2})
        for value,original in zip((out,out_uv,out_rgba),(faces,uv,rgba)):
            np.testing.assert_array_equal(value,original[[0,2]][:,[0,2,1]])
        encoded=out.astype('f4').astype(float)
        self.assertTrue((signed_area(encoded)*signed_area(faces[[0,2]])>0).all())
        # Reordering does not move any represented vertex or erase nonzero area.
        np.testing.assert_array_equal(abs(signed_area(encoded)),abs(signed_area(faces[[0,2]].astype('f4').astype(float))))
        for value,copy in zip((faces,uv,rgba),saved):np.testing.assert_array_equal(value,copy)

    def test_sharp_valley_bend_preserves_footprint_attributes_and_winding(self):
        w=world([[10,10,10],[10,0,10],[10,10,10]])
        original=np.array([[[.2,10,.2],[3.8,10,.3],[.3,10,3.8]],
                           [[3.8,10,.3],[3.7,10,3.7],[.3,10,3.8]]])
        uv,colors=attributes(original); saved=[v.copy() for v in (original,uv,colors,w.height)]
        faces,out_uv,out_colors=conform_road_faces(w,original,uv,colors)
        self.assertGreater(len(faces),len(original))
        self.assertTrue((signed_area(faces)>0).all())
        before=unary_union([Polygon(f[:,[0,2]]) for f in original])
        after=unary_union([Polygon(f[:,[0,2]]) for f in faces])
        self.assertLess(before.symmetric_difference(after).area,1e-12)
        self.assertAlmostEqual(sum(abs(signed_area(faces))),before.area,places=11)
        expected_uv,expected_colors=attributes(faces)
        np.testing.assert_allclose(out_uv,expected_uv,atol=1e-13)
        np.testing.assert_allclose(out_colors,expected_colors,atol=1e-13)
        # Any barycentric interior point of each new face lies on one affine
        # terrain plane. The old ribbon floats over the valley by many metres.
        for weights in ([1/3]*3,[.1,.2,.7],[.6,.3,.1]):
            points=np.einsum('i,tij->tj',weights,faces)
            np.testing.assert_allclose(points[:,1]-w.height_at(points[:,0],points[:,2]),.055,atol=1e-12)
        self.assertGreater(10-w.height_at(2.,2.),9.)
        for value,copy in zip((original,uv,colors,w.height),saved):np.testing.assert_array_equal(value,copy)

    def test_reversed_and_overlapping_faces_keep_separate_attribute_layers(self):
        w=world([[0,4,0],[3,0,3],[0,4,0]],-2.,-2.)
        face=np.array([[-1.8,5,-1.8],[1.7,5,-1.7],[-1.7,5,1.7]])
        original=np.array([face,face[::-1]])
        uv,colors=attributes(original);colors[1,:,3]=.9
        out,_,rgba=conform_road_faces(w,original,uv,colors)
        positive=signed_area(out)>0;negative=signed_area(out)<0
        self.assertTrue(positive.any() and negative.any())
        self.assertAlmostEqual(sum(abs(signed_area(out))),sum(abs(signed_area(original))),places=11)
        np.testing.assert_allclose(rgba[negative,:,3],.9)

    def test_grid_edges_zero_area_and_outside_domain(self):
        w=world([[0,1,2],[1,2,3],[2,3,4]])
        original=np.array([[[0,5,0],[4,5,0],[0,5,4]],[[0,5,0],[2,5,2],[4,5,4]]],float)
        uv,colors=attributes(original)
        out,_,_=conform_road_faces(w,original,uv,colors)
        self.assertAlmostEqual(sum(abs(signed_area(out))),8.,places=12)
        with self.assertRaisesRegex(ValueError,'outside'):
            wrong=original.copy();wrong[0,0,0]=-.001
            conform_road_faces(w,wrong,uv,colors)
        with self.assertRaisesRegex(ValueError,'finite'):
            wrong=original.copy();wrong[0,0,1]=float('nan')
            conform_road_faces(w,wrong,uv,colors)

    def test_single_terrain_triangle_preserves_original_xz_and_attributes(self):
        w=world([[0,2],[3,4]])
        original=np.array([[[.1,99,.1],[.8,99,.1],[.1,99,.8]]])
        uv,colors=attributes(original)
        out,actual_uv,actual_colors=conform_road_faces(w,original,uv,colors)
        np.testing.assert_array_equal(out[:,:,[0,2]],original[:,:,[0,2]])
        np.testing.assert_array_equal(actual_uv,uv);np.testing.assert_array_equal(actual_colors,colors)


if __name__=='__main__':unittest.main()
