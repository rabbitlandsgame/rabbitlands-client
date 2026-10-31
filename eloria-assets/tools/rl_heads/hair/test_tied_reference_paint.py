"""Tied paint authoring preserves defaults and requires an authored chart."""
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import build_tied_reference as tied

class PaintedBacking(unittest.TestCase):
    def setUp(self):
        self.P=np.array([[-2.,0.,0.],[-1.,0.,0.],[-2.,1.,0.],[1.,0.,0.],[2.,0.,0.],[1.,1.,0.],[-1.75,.25,-.01],[1.25,.25,-.01]])
        self.N=np.tile([0.,0.,1.],(8,1));self.T=np.array([[0,1,2],[3,4,5]])
        self.UV=np.array([[.1,.1],[.2,.1],[.1,.2],[.8,.1],[.9,.1],[.8,.2],[.5,.8],[.5,.8]])
        self.C=np.ones((8,4));self.ranges={'exterior':[0,6],'backing':[6,8]}
    def run_builder(self,enabled):
        data=(self.P,self.N,self.UV,self.T,self.C,self.ranges,{})
        with patch.object(tied.shared,'all_parts',return_value=data):
            return tied.parts_builder(None,None,None,{'painted_backing':enabled},0)
    def test_opt_in_cannot_silently_use_an_unavailable_chart(self):
        data=(self.P,self.N,self.UV,self.T,self.C,self.ranges,{})
        with patch.object(tied.shared,'all_parts',return_value=data):
            with self.assertRaises(FileNotFoundError):
                tied.parts_builder(Path(__file__).parent/'missing-chart-fixture',None,None,{'painted_backing':True},0)
    def test_unopted_style_keeps_existing_uvs(self):
        result=self.run_builder(False)
        np.testing.assert_array_equal(result[2],self.UV)
        self.assertNotIn('backing_paint',result[-1])

if __name__=='__main__':unittest.main()
