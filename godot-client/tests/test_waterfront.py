"""Player rays cross timber seams, bends and landing ports without falling."""
import math
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2] /
                      "eloria-assets/maps/nymara-regions/_toolkit"))
from amberwood import waterfront as WF
from verify_runtime import VerticalRayIndex

def triangles(group):
    return np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in group.walk_parts])

def test_joined_boards_ground_at_seams_and_do_not_duplicate_the_top():
    panel=WF.deck_panel(3,4,y=2)
    tri=panel.positions[panel.indices.reshape(-1,3)]
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert np.isclose(normal[normal[:,1]>0,1].sum()/2,48)
    ray=VerticalRayIndex(tri,cell=1)
    for z in np.linspace(-3.999,3.999,401):
        assert ray.top_hit(.173,float(z))==pytest.approx(2)

def test_sloping_bend_has_continuous_floor_and_grounded_endpoints():
    stations=[(0,1,0),(12,2,0),(22,3,6)]
    tri=triangles(WF.piled_route(stations,width=4,rails=False))
    ray=VerticalRayIndex(tri,cell=1)
    for a,b in zip(np.array(stations),np.array(stations)[1:]):
        for u in np.linspace(.001,.999,91):
            p=a+(b-a)*u
            assert ray.top_hit(float(p[0]),float(p[2]))==pytest.approx(p[1],abs=.04)
    assert ray.top_hit(5,3) is None

def test_landing_chord_and_route_share_an_edge_without_overlapping():
    r=5.;width=4.;cut=math.sqrt(r*r-width*width/4)
    port=[np.array([cut,2,-2]),np.array([cut,2,2])]
    landing=WF.junction((0,2,0),[port],r)
    route=WF.piled_route([(cut,2,0),(20,4,0)],width,ends=(port,None),rails=False)
    a,b=triangles(landing),triangles(route)
    assert a[:,:,0].max()<=cut+1e-6
    assert b[:,:,0].min()>=cut-1e-6
    ray=VerticalRayIndex(np.concatenate([a,b]),cell=1)
    for x in np.linspace(cut-.2,cut+.2,41):
        expected=2+max(x-cut,0)*2/(20-cut)
        assert ray.top_hit(float(x),.731)==pytest.approx(expected,abs=.00001)

def test_bad_route_does_not_silently_emit_overlapping_bends():
    with pytest.raises(ValueError):
        WF.piled_route([(0,0,0),(10,0,0),(0,0,.01)])
