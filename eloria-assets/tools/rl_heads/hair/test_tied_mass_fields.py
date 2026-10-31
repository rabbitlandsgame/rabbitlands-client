"""Core mass controls must move independently while scalp roots stay pinned."""
import unittest
import numpy as np
import headref
from build_tied_reference import knot_field

class Head:
    C=np.zeros(3)
class Scalp:
    def point(self,lon,lat):
        normal=headref.lonlat_dir(np.atleast_1d(lon),np.atleast_1d(lat));return normal*.1,normal

GROOM={'length_positive':.35,'length_negative':.25,'volume_positive':.45,'volume_negative':.25,'root_fade_mm':[8,28]}

class TiedMassFields(unittest.TestCase):
    def test_two_knots_keep_independent_mass_axes(self):
        centers=[[70,55],[-70,55]];P=[];Q=[]
        for center in centers:
            axis=headref.lonlat_dir(*center);side=headref.unit(np.cross(axis,[0,1.,0]));P.append(axis*.145+side*.025);Q.append(axis*.1)
        P=np.array(P);Q=np.array(Q);spec={'groom':GROOM,'tied_mass':{'centers':centers,'angular_radius_degrees':25,'angular_feather_degrees':8,'attachment_mm':8,'root_ramp_mm':[3,10]}}
        length=knot_field(P,Q,Head(),Scalp(),spec,'length',True);volume=knot_field(P,Q,Head(),Scalp(),spec,'volume',True)
        self.assertTrue((np.linalg.norm(length,axis=1)>.005).all());self.assertTrue((np.linalg.norm(volume,axis=1)>.01).all())
        np.testing.assert_allclose((length*volume).sum(1),0,atol=1e-10)
        np.testing.assert_array_equal(knot_field(Q,Q,Head(),Scalp(),spec,'length',True),np.zeros_like(Q))
    def test_tail_length_and_width_are_orthogonal_and_attachment_pinned(self):
        spec={'groom':GROOM,'tied_mass':{'kind':'tail','center':[180,42],'attachment_mm':10,'direction':[0,-1,0],'root_ramp_mm':[0,35],'rear_sector':[80,115],'spine':[[0,0,-.025],[.15,-.015,-.075],[.5,-.015,-.12]]}}
        root,normal=Scalp().point(180,42);anchor=root+normal*.01;P=anchor+np.array([[.025,-.25,-.04]]);Q=root
        length=knot_field(P,Q,Head(),Scalp(),spec,'length',True);volume=knot_field(P,Q,Head(),Scalp(),spec,'volume',True)
        self.assertLess(length[0,1],-.05);self.assertGreater(np.linalg.norm(volume),.005)
        self.assertAlmostEqual(float((length*volume).sum()),0,places=12)
        np.testing.assert_array_equal(knot_field(Q,Q,Head(),Scalp(),spec,'volume',False),np.zeros_like(Q))

if __name__=='__main__':unittest.main()
