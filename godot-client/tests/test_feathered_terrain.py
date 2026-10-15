"""Soft soil coverage must retain a real, gap-free opaque ground surface."""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions/_toolkit'))
from amberwood import terrain as T,materials as MAT
from verify_runtime import VerticalRayIndex

def test_soft_path_retains_ground_and_has_both_feather_and_solid_interior():
    t=T.Terrain(-20,-20,40,40,1)
    t.height[:]=2+.05*t.gx
    t.surface[:]=T.TURF
    t.surface[abs(t.gx)<5]=T.PATH
    meshes=t.build_feathered_meshes(T.TURF,feather_metres=1.25)
    base=meshes['Terrain_Base']
    assert base.colors is None
    assert base.material==T.SURFACE_MATERIALS[T.TURF]
    ray=VerticalRayIndex(base.positions[base.indices.reshape(-1,3)])
    for x in np.linspace(-19.9,19.9,81):
        assert ray.top_hit(x,0)==pytest.approx(2+.05*x)
    path=next(m for n,m in meshes.items() if n!='Terrain_Base')
    assert path.material.endswith(MAT.SOFT_GROUND_SUFFIX)
    assert ((path.colors[:,3]>.05)&(path.colors[:,3]<.95)).any()
    assert path.colors[:,3].max()>.99
    assert MAT.base_material(path.material)==T.SURFACE_MATERIALS[T.PATH]
    assert np.allclose(path.positions[:,1],2+.05*path.positions[:,0]+.008)

def test_soft_material_edges_do_not_wrap_across_the_region():
    t=T.Terrain(0,0,30,30,1);t.surface[:]=T.TURF;t.surface[t.gx<3]=T.PATH
    mesh=next(m for n,m in t.build_feathered_meshes(T.TURF).items() if n!='Terrain_Base')
    assert mesh.positions[:,0].max()<15
