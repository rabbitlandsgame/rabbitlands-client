"""The opt-in woodland kit keeps its palette and authored walking surfaces."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"eloria-assets/maps/nymara-regions/_toolkit"))
from amberwood import architecture as A, woodlandcraft as W, stonework as S
from verify_runtime import VerticalRayIndex

def test_lodge_keeps_its_existing_roof_stone_and_timber_palette():
    model=A.forest_lodge(seed=19,preserve_materials=True)
    materials={p.material for p in model.parts}
    assert {"shingles","rubble_stone","timber_dark","timber_warm"} <= materials
    assert A.forest_lodge(seed=19).material == "timber_warm"

def test_monument_stair_meets_its_open_podium():
    model=S.monumental_gate(seed=3,stair_width=14,stair_height=4.4,continuous_walk=True)
    tri=np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in model.walk_parts])
    ray=VerticalRayIndex(tri,cell=1)
    assert ray.top_hit(0,0)==pytest.approx(4.4)
    ys=[ray.top_hit(0,float(z)) for z in np.linspace(12.69,3.51,100)]
    assert all(y is not None for y in ys)
    assert np.all(np.diff(ys)>=-.001)
    assert ys[-1]==pytest.approx(4.4)

def test_surveyed_water_has_a_continuous_upward_skin_through_a_bend():
    model=W.water_ribbon([(0,12,0),(0,10,12),(8,8,20)],width=3)
    tri=model.positions[model.indices.reshape(-1,3)]
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert np.all(normals[:,1]>0)
    ray=VerticalRayIndex(tri,cell=1)
    for x,z,y in [(0,1,12-2/12),(0,11,12-22/12),(4,16,9)]:
        assert ray.top_hit(x,z)==pytest.approx(y,abs=.01)

def test_amberwood_declared_crossings_match_the_rendered_decks():
    import json
    import glb_reader as G
    package=Path(__file__).resolve().parents[2]/"eloria-assets/maps/nymara-regions/amberwood"
    document,blob=G.load(package/"world.glb")
    # Use only built walking geometry: nearby terrain must not conceal a
    # bridge translated half a span away from its declared bank survey.
    triangles=G.triangles(document,blob,G.named(document,"Walk_"))
    ray=VerticalRayIndex(triangles,cell=2)
    manifest=json.loads((package/"world.json").read_bytes())
    crossings=manifest["navigation"]["crossings"]
    assert len(crossings)>=7
    for crossing in crossings:
        a,b=np.asarray(crossing["endpoints"],dtype=float)
        for f in np.linspace(0,1,17):
            x,y,z=a+(b-a)*f
            assert ray.top_hit(float(x),float(z))==pytest.approx(float(y),abs=.025),crossing["id"]


def test_clean_roof_keeps_the_lodges_longitudinal_ridge():
    roof = A.roof(8, 12, 5, overhang=0, ridge=False, clean_join=True)
    triangles = np.concatenate([part.positions[part.indices.reshape(-1, 3)]
                                for part in roof.parts])
    index = VerticalRayIndex(triangles, cell=2)
    assert index.top_hit(2, 0) == pytest.approx(2.5)
    assert index.top_hit(2, 3) == pytest.approx(2.5)


def test_amberwood_mill_paddles_reach_water_without_hitting_the_bed():
    import glb_reader as G
    package = Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/amberwood"
    document, body = G.load(package / "world.glb")
    wheel = G.triangles(document, body, G.named(document, "Landmark_Building_Lodge_14"))
    water = VerticalRayIndex(G.triangles(document, body, G.named(document, "Water_Streams")), cell=4)
    ground = VerticalRayIndex(G.triangles(document, body, G.named(document, "Terrain_")), cell=4)
    low = float(wheel[:,:,1].min())
    assert ground.top_hit(-29.35, -118) < low < water.top_hit(-29.35, -118)
