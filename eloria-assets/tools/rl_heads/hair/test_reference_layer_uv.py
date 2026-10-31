"""Recipient UV seams cannot change geometry, normals or authoring colours."""
import unittest
import numpy as np
from reference_layer_uv import split_corner_uv

class RecipientSeams(unittest.TestCase):
    def test_separate_uv_charts_copy_all_corner_attributes_exactly(self):
        P=np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]])
        T=np.array([[0,1,2],[0,2,3]]);N=np.tile([0.,0.,1.],(4,1));C=np.arange(16).reshape(4,4)
        chart=np.array([[[0.,0.],[.4,0.],[.4,.4]],[[.6,.6],[1.,1.],[.6,1.]]])
        points,tri,uv,attrs,report=split_corner_uv(P,T,chart,{'N':N,'COL':C})
        self.assertEqual(len(points),6)
        np.testing.assert_array_equal(points[tri],P[T]);np.testing.assert_array_equal(attrs['N'][tri],N[T]);np.testing.assert_array_equal(attrs['COL'][tri],C[T])
        self.assertEqual(report['triangle_positions_before_sha256'],report['triangle_positions_after_sha256'])
    def test_shared_chart_needs_no_new_geometry_vertices(self):
        P=np.array([[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]])
        T=np.array([[0,1,2],[0,2,3]]);UV=np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.]])
        points,tri,uv,attrs,report=split_corner_uv(P,T,UV[T],{})
        self.assertEqual(len(points),4);np.testing.assert_array_equal(P[T],points[tri]);np.testing.assert_array_equal(uv,UV)

if __name__=='__main__':unittest.main()
