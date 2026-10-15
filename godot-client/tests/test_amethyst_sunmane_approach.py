"""Amethyst's regional finishing pass joins new paving to real ground."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import sys
import numpy as np
import pytest

REGIONS = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions'
sys.path[:0] = [str(REGIONS / '_toolkit'), str(REGIONS / '_northern')]
from amberwood import mesh as M
from regionbuild import RegionBuild
from verify_runtime import VerticalRayIndex
import road_profiles

spec = importlib.util.spec_from_file_location('amethyst_sunmane_finish', REGIONS / 'amethyst_barrens/source/sunmane_approach.py')
finish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finish)


@pytest.fixture
def corrected(monkeypatch):
    monkeypatch.setattr(road_profiles, '_edge_distance', lambda build, region, xz: np.abs(122.5 - xz[:, 1]))
    terrain = SimpleNamespace(gx=np.array([[40.5]]), gz=np.array([[90.]]), height=np.array([[19.]]))
    b = RegionBuild(terrain)
    b.geography_roads = [{'id': 'amethyst-sunmane', 'stations': [[54.5,19,71.5],[40.5,18,122.5]]},
                         {'id': 'whitehorn-amethyst', 'stations': [[-114.,24.15,-228.5],[-109.,24.15,-228.5]]}]
    b.streaming_borders = [{'id':'amethyst-sunmane','anchor':[40.5,18,122.5],'outward':[0,1],'sceneNodes':[]}]
    b.terrain_meshes['Terrain_Barrens'] = M.quad([[22,19,55],[66,19,55],[66,19,124],[22,19,124]])
    b.terrain_meshes['Terrain_Merge'] = M.quad([[-124,24.1,-242],[-100,24.1,-242],[-100,24.1,-218],[-124,24.1,-218]])
    road = M.quad([[36.25,18.03,65],[58.75,18.03,65],[58.75,18.03,122.5],[36.25,18.03,122.5]])
    b.terrain_meshes['Walk_ContinentRoad_amethyst-sunmane'] = road
    white = M.quad([[-115,24.183,-231],[-108,24.183,-231],[-108,24.183,-226],[-115,24.183,-226]])
    b.terrain_meshes['Walk_ContinentRoad_whitehorn-amethyst'] = white
    native = M.quad([[25,5,50],[30,5,50],[30,5,55],[25,5,55]])
    b.terrain_meshes['Walk_NativeEntry'] = native
    boundary = road.positions[road.positions[:,2] >= 119.5].copy()
    before = native.positions.copy()
    finish.apply(b)
    return b, boundary, before


def test_continuous_bend_is_seated_and_common_contour_native_entry_retained(corrected):
    b, boundary, before = corrected
    road = b.terrain_meshes['Walk_ContinentRoad_amethyst-sunmane']
    ray = VerticalRayIndex(road.positions[road.indices.reshape(-1,3)])
    base = b.terrain_meshes['Terrain_Barrens']
    ground = VerticalRayIndex(base.positions[base.indices.reshape(-1,3)])
    for x,z in [(42.334791,75),(43.5,109.44973),(40.5,90),(45,77)]:
        assert ray.top_hit(x,z) is not None
        assert ray.top_hit(x,z)-ground.top_hit(x,z) == pytest.approx(.03,abs=.06)
    for p in boundary:
        assert np.any(np.all(road.positions == p,axis=1))
    np.testing.assert_array_equal(b.terrain_meshes['Walk_NativeEntry'].positions,before)


def test_white_deck_edge_matches_shared_mirror_level(corrected):
    b,_,_ = corrected
    m = b.terrain_meshes['Walk_ContinentRoad_whitehorn-amethyst']
    ray = VerticalRayIndex(m.positions[m.indices.reshape(-1,3)])
    assert ray.top_hit(-111.49,-228.5) == pytest.approx(24.08,abs=1e-7)
    assert b.geography_roads[1]['stations'][0][1] == pytest.approx(ray.top_hit(-114.,-228.5)-.03,abs=1e-7)
    assert abs(b.geography_roads[1]['stations'][0][1]-24.05) < .001
