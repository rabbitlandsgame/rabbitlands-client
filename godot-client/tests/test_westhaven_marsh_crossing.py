"""Geometry-only regressions for the Coast Road's authored wet crossing."""
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REGIONS=ROOT/'eloria-assets/maps/nymara-regions'
sys.path.insert(0,str(REGIONS/'_toolkit'))
sys.path.insert(0,str(REGIONS/'_northern'))
spec=importlib.util.spec_from_file_location('west_marsh_crossing',REGIONS/'westhaven/source/marsh_crossing.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
from verify_runtime import VerticalRayIndex
import glb_reader as GLB


def test_continuous_raised_ribbon_has_seven_clear_lanes_through_bends():
    mesh=C.ribbon(-C.HALF_WIDTH,C.HALF_WIDTH,C.HEIGHT,'cobble_paving')
    shared=SimpleNamespace(terrain_meshes={},water_meshes={})
    C.SB._causeway_meshes(shared,dict(id='westhaven-manymouth',anchor=[312.5,4.,64.5],outward=[1,0],deckWidth=7.,uvSign=1))
    existing=shared.terrain_meshes['Walk_StreamCauseway_westhaven-manymouth']
    ray=VerticalRayIndex(np.concatenate([mesh.positions[mesh.indices.reshape(-1,3)],existing.positions[existing.indices.reshape(-1,3)]]))
    for a,b in zip(C.CENTRES,C.CENTRES[1:]):
        d=b-a;d/=np.linalg.norm(d);side=np.array([-d[1],d[0]])
        for t in np.linspace(.01,.99,40):
            for lane in range(-3,4):
                q=a*(1-t)+b*t+side*lane
                height=ray.top_hit(*q)
                assert height is not None,(q,lane,t,a,b)
                assert abs(height-4.)<1e-8,(q,lane)
    assert np.all(mesh.normals[:,1]>.999)


def test_mouth_matches_existing_causeway_plane_and_width():
    assert np.array_equal(C.CENTRES[0],[244.,24.])
    assert np.array_equal(C.CENTRES[-1],[270.5,64.5])
    assert np.array_equal(C.edge_points(-4.25)[-1],[270.5,60.25])
    assert np.array_equal(C.edge_points(4.25)[-1],[270.5,68.75])
    # A visible0.8m masonry edge supports the walking skin above the water.
    slab=C.sides(-4.25,4.25,3.2,4.,'pale_ashlar')
    assert np.isclose(slab.positions[:,1].min(),3.2)
    assert np.isclose(slab.positions[:,1].max(),4.)


def test_native_lamp_junction_height_is_matched_without_moving_its_deck():
    native=C.M.quad([[250,3.7,40],[254,3.74,40],[254,3.78,44],[250,3.74,44]])
    original=native.positions.copy()
    placement=SimpleNamespace(node='Landmark_Route_lamp_causeway',mesh='lamp',
                              rotation_y=0.,scale=1.,position=np.zeros(3))
    build=SimpleNamespace(placements=[placement],meshes={'lamp':SimpleNamespace(walk_parts=[native])})
    _,height=C.lamp_join(build)
    assert np.isclose(height([252,42]),3.74)
    assert np.isclose(height([258,42]),4.)
    points=np.linspace(253.,259.,121)
    levels=np.array([height([x,42]) for x in points])
    assert np.max(np.abs(np.diff(levels)/np.diff(points)))<.15
    assert np.array_equal(native.positions,original)


def test_exact_native_cut_removes_duplicate_skin_and_keeps_its_surrounding_deck():
    deck=C.M.quad([[0,4,0],[4,4,0],[4,4,4],[0,4,4]])
    old=C.M.quad([[1,3.8,1],[3,3.8,1],[3,3.8,3],[1,3.8,3]])
    result=C.subtract_lamp_walk(deck,old.positions[old.indices.reshape(-1,3)])
    triangles=result.positions[result.indices.reshape(-1,3)]
    area=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1).sum()*.5
    assert np.isclose(area,12.)
    ray=VerticalRayIndex(triangles)
    assert ray.top_hit(2,2) is None
    assert np.isclose(ray.top_hit(.5,2),4.)


def test_clipped_top_normalization_restores_production_raster_without_moving_geometry():
    mesh=C.M.quad([[0,4,0],[2,4,0],[2,4,2],[0,4,2]],material='cobble_paving')
    faces=mesh.indices.reshape(-1,3);tri=mesh.positions[faces]
    down=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<0
    faces[down]=faces[down][:,[0,2,1]]
    faces[0]=faces[0,[0,2,1]]
    positions=mesh.positions.copy();uvs=mesh.uvs.copy()
    before,_=GLB.rasterise(mesh.positions[faces],8,8,0,2,.25)
    C.upward_top(mesh)
    after,height=GLB.rasterise(mesh.positions[mesh.indices.reshape(-1,3)],8,8,0,2,.25)
    assert before.sum()<64 and after.all() and np.all(height==4.)
    np.testing.assert_array_equal(mesh.positions,positions)
    np.testing.assert_array_equal(mesh.uvs,uvs)
