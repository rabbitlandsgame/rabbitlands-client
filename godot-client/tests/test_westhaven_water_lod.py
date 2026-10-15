"""The native sea must retain exact coverage in the streamed far package."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REGIONS=ROOT/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'westhaven/source'),str(REGIONS/'_toolkit')]
import populate as P
from amberwood import terrain as T


def test_far_sea_keeps_main_shoreline_geometry_and_uvs():
    t=T.Terrain(-12.,-12.,24.,24.,cell=1.)
    t.height=np.where((t.gx<2.)|(abs(t.gz-1.)<1.),-2.,3.)
    near=SimpleNamespace(terrain=t,water_meshes={})
    far=SimpleNamespace(terrain=t,water_meshes={})
    P.build_water(near,lod=None);P.build_water(far,lod='far')
    a,b=near.water_meshes['Water_Sea'],far.water_meshes['Water_Sea']
    assert a.triangle_count>0
    np.testing.assert_array_equal(a.positions,b.positions)
    np.testing.assert_array_equal(a.indices,b.indices)
    np.testing.assert_array_equal(a.uvs,b.uvs)
