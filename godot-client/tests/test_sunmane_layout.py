"""Geometry and server-coordinate checks for the surveyed steppe."""
import json
import sys
from pathlib import Path
import numpy as np
import pytest
TK=Path(__file__).resolve().parents[2]/"eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0,str(TK))
from amberwood import watercraft
from verify_runtime import VerticalRayIndex
import glb_reader as G

def test_pool_shore_is_clipped_inside_cells_with_unique_upward_faces():
    sample=lambda x,z:(x*x+z*z)/16
    mesh=watercraft.pools(sample,[(0,0,8,1.08)],cell=.6)
    tri=mesh.positions[mesh.indices.reshape(-1,3)]
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert np.all(normals[:,1]>0)
    area=normals[:,1].sum()/2
    assert area==pytest.approx(np.pi*16,rel=.02)
    assert np.max(sample(mesh.positions[:,0],mesh.positions[:,2]))<=1.001
    ray=VerticalRayIndex(tri,cell=1)
    assert ray.top_hit(0,0)==pytest.approx(1.08)
    assert ray.top_hit(5,0) is None

def test_sunmane_three_bridge_decks_match_their_bank_surveys():
    package=TK.parent/"sunmane_steppe"
    doc,body=G.load(package/"world.glb")
    walk=VerticalRayIndex(G.triangles(doc,body,G.named(doc,"Walk_Bridge_")),cell=1)
    data=json.loads((package/"world.json").read_bytes())
    assert data["asset"]["serverCells"]==192
    crossings=data["navigation"]["crossings"]
    assert len(crossings)==3
    for crossing in crossings:
        a,b=np.asarray(crossing["endpoints"],float)
        for fraction in np.linspace(0,1,25):
            x,y,z=a+(b-a)*fraction
            assert walk.top_hit(float(x),float(z))==pytest.approx(float(y),abs=.02),crossing["id"]

def test_sunmane_source_markers_stand_on_their_server_tiles():
    package=TK.parent/"sunmane_steppe"
    data=json.loads((package/"world.json").read_bytes())
    posts=json.loads((package/"source/server-content.json").read_bytes())
    for section in ("npcs","resources"):
        entries={e["id"]:e for e in data["runtimePopulation"][section]}
        for key,tile in posts["runtimePopulation."+section].items():
            entry=entries[key];point=entry.get("position",entry.get("center"))
            assert entry["serverTile"]==tile
            assert point[0]==pytest.approx(tile[0]-58)
            assert point[2]==pytest.approx(58-tile[1])
