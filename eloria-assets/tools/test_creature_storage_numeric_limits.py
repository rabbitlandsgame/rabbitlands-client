import numpy as np
import pytest
from test_completed_creature_motion import numeric_limits


def test_default_witness_limits_are_unchanged():
    assert numeric_limits({},np.array([[0,0,0],[1,1,1]])) == (1e-8,1e-8)


def test_flat_creature_budget_is_in_coordinate_ulps_and_finite_normal_angle():
    height=.328125
    w={'sha256':'a'*64,'reference_sha256':'b'*64,'height':height,
       'surface_numeric_tolerance_over_height':4*float(np.spacing(np.float32(1.0)))/height,
       'normal_numeric_tolerance':2*np.sin(np.deg2rad(.0001)/2),
       'representation_numeric_budget':{'source_position_ulps':4,'source_normal_angle_degrees':.0001}}
    numeric_limits(w,np.array([[0,0,0],[1,height,1]]))
    w['surface_numeric_tolerance_over_height']*=2
    with pytest.raises(AssertionError):numeric_limits(w,np.array([[0,0,0],[1,height,1]]))


def test_new_budget_cannot_authorize_approximate_deformation():
    w={'sha256':'a'*64,'reference_sha256':'b'*64,'height':1.,
       'surface_numeric_tolerance_over_height':.001,
       'representation_numeric_budget':{'source_position_ulps':64,'source_normal_angle_degrees':1.0}}
    with pytest.raises(AssertionError):numeric_limits(w,np.array([[0,0,0],[1,1,1]]))
