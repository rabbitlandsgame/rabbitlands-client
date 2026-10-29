"""Single-pass field semantics, bounds, and complete stored trial contracts."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
SPEC = importlib.util.spec_from_file_location("road_terrain_blend_trial",TOOLS/"road_terrain_blend_trial.py")
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)


def triangles():
    first = np.array([[[0,0,0],[2,0,0],[0,0,2]]],float)
    return np.concatenate([first,first])


def test_coverage_is_maximum_not_alpha_union_and_ties_choose_last_uv():
    faces = triangles()
    uv = faces[...,[0,2]];uv[1] += 100
    grid = dict(width=4,height=4,origin_xz=[0,0],pixels_per_metre=2)
    result = TRIAL.dominant_raster(faces,uv,np.full((2,3),.5),grid)
    assert result["alpha"][0,0] == .5
    assert np.array_equal(result["uv"][0,0],[100.25,100.25])
    assert result["selected_triangle"][0,0] == 1
    assert result["ambiguous_uv"][0,0]


def test_higher_coverage_wins_even_when_lower_coverage_is_later():
    faces = triangles();uv=faces[...,[0,2]];uv[1] += 100
    result = TRIAL.dominant_raster(faces,uv,np.array([[.9]*3,[.7]*3]),
                                   dict(width=4,height=4,origin_xz=[0,0],pixels_per_metre=2))
    assert result["alpha"][0,0] == .9
    assert np.array_equal(result["uv"][0,0],[.25,.25])
    assert result["selected_triangle"][0,0] == 0


def test_odd_ppm_adjacent_frames_use_identical_world_sample_addresses():
    faces=np.array([[[0,0,0],[4,0,0],[0,0,2]],[[4,0,0],[4,0,2],[0,0,2]]],float)
    uv=faces[...,[0,2]]*3+100
    a=TRIAL.dominant_raster(faces,uv,np.ones((2,3)),dict(width=9,height=6,origin_xz=[0,0],pixels_per_metre=3))
    b=TRIAL.dominant_raster(faces,uv,np.ones((2,3)),dict(width=9,height=6,origin_xz=[1,0],pixels_per_metre=3))
    assert np.array_equal(a["uv"][:,3:],b["uv"][:,:6])
    assert np.array_equal(a["alpha"][:,3:],b["alpha"][:,:6])


def test_arbitrary_ppm_mip_plan_and_runtime_cap_are_explicit():
    plan=TRIAL.field_plan(triangles(),3)
    assert plan["fits_runtime_cap"]
    assert plan["mip_levels"][-1] == dict(width=1,height=1)
    assert plan["planned_rg32f_mip_bytes"] == 8*sum(m["width"]*m["height"] for m in plan["mip_levels"])
    large=TRIAL.field_plan(np.array([[[0,0,0],[1000,0,0],[0,0,1000]]]),8)
    assert not large["fits_runtime_cap"]
    with pytest.raises(ValueError,match="positive integer"):
        TRIAL.field_plan(triangles(),0)


@pytest.fixture
def source_fixture(tmp_path,monkeypatch):
    root=tmp_path/"repo"
    for number,chunk in enumerate(["00_00","00_01"]):
        directory=root/f"eloria-assets/maps/continent-v2/test/client/chunks/{chunk}"
        directory.mkdir(parents=True)
        vertices=np.array([[0,0,0],[2,0,0],[0,0,2],[2,0,0],[2,0,2],[0,0,2]],dtype="<f4")
        vertices[:,0] += number*2
        road=vertices.copy();road[:,1] += .055
        arrays=[vertices,road,vertices[:,[0,2]],np.ones((6,4),dtype="<f4")]
        body=bytearray();views=[];accessors=[]
        for array,kind in zip(arrays,["VEC3","VEC3","VEC2","VEC4"]):
            views.append(dict(buffer=0,byteOffset=len(body),byteLength=array.nbytes));body.extend(array.tobytes())
            accessors.append(dict(bufferView=len(views)-1,componentType=5126,count=6,type=kind))
        document=dict(asset={"version":"2.0"},scene=0,scenes=[{"nodes":[0,1,2]}],
                      nodes=[{"name":f"Terrain_test_{chunk}","mesh":0},
                             {"name":f"Walk_test_foo_test_{chunk}","mesh":1},
                             {"name":f"AuthoredGround_testBase_test_{chunk}","mesh":0,"translation":[0,.006,0]}],
                      meshes=[{"primitives":[{"attributes":{"POSITION":0},"material":0}]},
                              {"primitives":[{"attributes":{"POSITION":1,"TEXCOORD_0":2,"COLOR_0":3},"material":0}]}],
                      accessors=accessors,bufferViews=views,buffers=[{"byteLength":len(body)}],
                      materials=[{"name":"exact dirt","pbrMetallicRoughness":{"roughnessFactor":1}}],
                      textures=[],images=[],samplers=[])
        (directory/"world.glb").write_bytes(TRIAL.T.SM.write_glb(document,body))
        (directory/"world.json").write_text(json.dumps({"asset":{"id":"test","glb":"world.glb"},
                                                       "externalResources":{},"externalMeshes":{}}))
    monkeypatch.setattr(TRIAL.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0))
    return root


def test_complete_single_field_trial_verifies_storage_colliders_and_seams(source_fixture):
    root=source_fixture;out=root/"eloria-assets/maps/continent-v2/test/client/.local/direct-trial"
    report=TRIAL.bake(root,root,out,"test",["00_00","00_01"],["foo"],ppms=(3,))
    validation=report["variants"]["3"]["validation"]
    assert validation["ok"] and validation["exact_collision_primitives"] == 2
    assert len(validation["seam_checks"]) == 1
    assert validation["seam_checks"][0]["covered_pixel_samples"] > 0
    assert validation["seam_checks"][0]["mismatched_fragments"] == 0
    for chunk in ["00_00","00_01"]:
        metadata=json.loads((out/f"3ppm/chunks/{chunk}/trial.json").read_text())
        assert len(metadata["layers"]) == 1
        assert metadata["ground_node_names"] == [f"AuthoredGround_testBase_test_{chunk}"]
    actual_files=set(out.joinpath("3ppm").rglob("*"))|set(out.joinpath("common").rglob("*"))
    assert report["variants"]["3"]["bytes"] == sum(p.stat().st_size for p in actual_files if p.is_file())


def test_rejects_inequivalent_road_materials_without_writing_output(source_fixture):
    root=source_fixture;p=root/"eloria-assets/maps/continent-v2/test/client/chunks/00_01/world.glb"
    document,body=TRIAL.T.SM.read_glb(p)
    document["materials"][0]["pbrMetallicRoughness"]["roughnessFactor"] = .2
    p.write_bytes(TRIAL.T.SM.write_glb(document,body))
    out=root/"eloria-assets/maps/continent-v2/test/client/.local/rejected"
    with pytest.raises(ValueError,match="equivalent"):
        TRIAL.bake(root,root,out,"test",["00_00","00_01"],["foo"],ppms=(2,))
    assert not out.exists()
