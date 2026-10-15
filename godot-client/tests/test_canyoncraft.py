"""The canyon's surveyed ramps and open mouths must carry real walk ground."""
import sys
from pathlib import Path
import numpy as np
import pytest

KIT = Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(KIT))
from amberwood import canyoncraft as C
from verify_runtime import VerticalRayIndex

@pytest.mark.parametrize("a,b,y0,y1", [
    ((-3,2),(8,16),0,3), ((7,-1),(-4,18),4,.6)])
def test_open_cut_ramp_grounds_across_its_surveyed_width(a,b,y0,y1):
    width=3.6
    ramp=C.cut_passage(a,b,width,y0,y1)
    triangles=np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in ramp.walk_parts])
    rays=VerticalRayIndex(triangles)
    aa,bb=np.array(a,float),np.array(b,float)
    along=(bb-aa)/np.linalg.norm(bb-aa)
    normal=np.array([along[1],-along[0]])
    for t in np.linspace(.001,.999,83):
        for side in (-1.7,0,1.7):
            x,z=aa+(bb-aa)*t+normal*side
            actual=rays.top_hit(x,z)
            assert actual is not None
            assert abs(actual-(y0+(y1-y0)*t))<1e-6
    x,z=(aa+bb)/2+normal*(width/2+.1)
    assert rays.top_hit(x,z) is None

def test_ramp_reaches_both_levels_in_the_collision_export():
    from secrets_build import build_collision
    ramp=C.cut_passage((0,0),(0,14),3.6,0,3)
    payload,stats=build_collision(ramp)
    grid=np.frombuffer(payload[16:],dtype=np.uint8).reshape(stats["height"],stats["width"])
    ox,oz=stats["originMetres"]
    x=int((0-ox)/.5)
    codes=[]
    for z in np.arange(.25,14,.5):
        code=int(grid[int((oz-z)/.5),x])
        assert code>0
        codes.append(code)
    heights=np.array(codes)*stats["heightEncoding"]["step"]+stats["heightEncoding"]["origin"]
    assert heights[0]<=.2 and heights[-1]>=2.8
    assert np.max(np.abs(np.diff(codes)))<=2
