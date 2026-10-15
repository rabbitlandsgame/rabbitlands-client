"""Suspension bridge rays follow the sag without plank gaps or stacked tops."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2] /
    "eloria-assets/maps/nymara-regions/_toolkit"))
from amberwood.mountaincraft import suspension_bridge
from verify_runtime import VerticalRayIndex

@pytest.mark.parametrize("rise",[0.0,8.0,-8.0])
def test_bridge_has_one_complete_profiled_walking_skin(rise):
    span=suspension_bridge(length=46,width=1.9,sag=1.4,rise=rise)
    tri=np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in span.walk_parts])
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert np.all(normal[:,1]>0)
    assert normal[:,1].sum()/2 == pytest.approx(46*1.9,abs=0.001)
    ray=VerticalRayIndex(tri,cell=1)
    for x in np.linspace(-23,23,461):
        t=(x+23)/46
        expected=rise*(t-.5)-1.4*(1-(2*t-1)**2)
        for z in (-.90,0,.90):
            assert ray.top_hit(float(x),z)==pytest.approx(expected,abs=.004)
    assert ray.top_hit(0,1.05) is None
