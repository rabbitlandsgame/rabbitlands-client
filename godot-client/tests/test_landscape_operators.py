"""Landscape shaping must preserve the route and leave other biomes opt-in."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions/_toolkit'))
from amberwood import terrain as T, landscape as L


def test_soft_bench_has_level_core_and_continuous_earth_banks():
    t=T.Terrain(-30,-30,60,60,1)
    t.height[:]=0
    t.rect_terrace((0,0),4,5,2,shoulder=12)
    assert t.height_at(0,0)==2
    assert t.height_at(25,0)==0
    assert np.max(np.abs(np.diff(t.height,axis=1)))<.26


def test_worn_track_keeps_surveyed_elevation_and_readable_centre():
    t=T.Terrain(-30,-30,60,60,1)
    t.height=t.gx*.07+t.gz*.02
    before=t.height.copy()
    L.worn_path(t,[(-25,0),(0,4),(25,0)],5,123)
    assert np.array_equal(t.height,before)
    for x in range(-23,24):
        z=4*(1-abs(x)/25)
        assert t.surface[int(round(z-t.z0)),int(x-t.x0)]==T.PATH


def test_habitat_keeps_meadow_and_road_open_without_uniform_forest():
    t=T.Terrain(-80,-80,160,160,2)
    t.height[:]=10
    meadow=np.zeros_like(t.height);meadow[t.gx>35]=1
    d,road,_=L.grove_density(t,[[(-80,0),(80,0)]],[[(-70,-80),(-70,80)]],19,open_ground=meadow)
    assert not np.any(d[road<5])
    assert not np.any(d[t.gx>35])
    assert np.ptp(d[(road>15)&(t.gx<30)])>.25
    again=L.grove_density(t,[[(-80,0),(80,0)]],[[(-70,-80),(-70,80)]],19,open_ground=meadow)[0]
    assert np.array_equal(d,again)


def test_compact_axis_preserves_village_scale_and_round_trips_outside_bounds():
    from compact_landscape import Axis
    axis=Axis(-174,402,-116,268,(-20,85))
    probes=np.linspace(-250,470,3000)
    assert np.all(np.diff(axis(probes))>0)
    assert np.allclose(axis.inverse(axis(probes)),probes)
    assert axis(85)-axis(-20)==105
    assert axis(402)-axis(-174)==384


def test_compact_keeps_building_scale_and_bridge_survey_coincident():
    from compact_landscape import Axis,CompactLandscape
    from regionbuild import RegionBuild,Placement
    from amberwood import mesh as M
    axis=Axis(-100,100,-60,60,(-20,20))
    plan=CompactLandscape(axis,axis,(100,100),(60,60))
    t=T.Terrain(-100,-100,200,200,2);t.height=t.gx*.1
    b=RegionBuild(t)
    b.meshes={'house':M.box((6,5,8)), 'bridge':M.box((20,.3,4))}
    b.placements=[Placement('house','house',(50,5,50),kind='building'),
                  Placement('Walk_bridge','bridge',(50,5,0),walk_surface=True)]
    b.crossings=[{'endpoints':[[40,5,0],[60,5,0]]}]
    original=b.meshes['house'].positions.copy()
    plan.apply(b)
    assert np.array_equal(b.meshes['house'].positions,original)
    deck=b.meshes[b.placements[1].mesh]
    pivot=b.placements[1].position[0]
    assert np.isclose(deck.positions[:,0].min()+pivot,b.crossings[0]['endpoints'][0][0])
    assert np.isclose(deck.positions[:,0].max()+pivot,b.crossings[0]['endpoints'][1][0])


def test_border_clip_keeps_exact_edge_without_overlapping_triangles():
    from border_vistas import clip_window
    from amberwood import mesh as M
    plane=M.quad([[-2,0,-2],[-2,0,2],[2,0,2],[2,0,-2]])
    seam=clip_window(plane,np.array([0,0]),np.array([1,0]),np.array([0,1]))
    triangles=plane.positions[plane.indices].reshape(-1,3,3)
    assert triangles[:,:,0].max()==0
    assert set(seam)=={-2,0,2}
    area=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1).sum()/2
    assert np.isclose(area,8)
