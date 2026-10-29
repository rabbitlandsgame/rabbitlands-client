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
    assert plan["planned_rgba32f_jacobian_nomip_bytes"] == plan["grid"]["width"]*plan["grid"]["height"]*16
    large=TRIAL.field_plan(np.array([[[0,0,0],[1000,0,0],[0,0,1000]]]),8)
    assert not large["fits_runtime_cap"]
    with pytest.raises(ValueError,match="positive integer"):
        TRIAL.field_plan(triangles(),0)


def test_source_affine_jacobian_reconstructs_uv_on_skewed_sloping_triangle():
    positions=np.array([[[11,30,-4],[13,35,-3],[10,33,1]]],float)
    xz=positions[...,[0,2]]
    uv=np.stack([2*xz[...,0]-3*xz[...,1]+7,.5*xz[...,0]+4*xz[...,1]-2],axis=-1)
    jacobian=TRIAL.affine_uv_jacobians(positions,uv)[0]
    assert np.array_equal(jacobian,[2,-3,.5,4])
    centre=positions[0].mean(axis=0)[[0,2]]
    centre_uv=uv[0].mean(axis=0)
    point=np.array([11.4,-1.3])
    reconstructed=centre_uv+jacobian.reshape(2,2)@(point-centre)
    assert np.allclose(reconstructed,[2*point[0]-3*point[1]+7,.5*point[0]+4*point[1]-2])


def test_uv_discontinuity_keeps_authored_footprint_in_jacobian_field(tmp_path):
    positions=np.array([[[0,0,0],[1,0,0],[0,0,1]],[[1,0,0],[1,0,1],[0,0,1]],
                        [[1,0,0],[2,0,0],[1,0,1]],[[2,0,0],[2,0,1],[1,0,1]]],float)
    uv=positions[...,[0,2]].copy();uv[2:]+=1000
    grid=dict(width=4,height=2,origin_xz=[0,0],pixels_per_metre=2)
    sheet=TRIAL.dominant_raster(positions,uv,np.ones((4,3)),grid)
    table=TRIAL.affine_uv_jacobians(positions,uv)
    metadata=TRIAL.store_jacobian(tmp_path,"jump",sheet,table)
    decoded=TRIAL.read_jacobian(tmp_path,metadata)
    assert np.array_equal(decoded,np.broadcast_to([1,0,0,1],decoded.shape))
    # Implicit differences across the field would invent a ~2001 texel/metre
    # footprint here. The authored selected triangles still have unit scale.
    assert sheet["uv"][0,2,0]-sheet["uv"][0,1,0] > 1000
    assert metadata["mipmaps"] is False
    assert metadata["uncompressed_bytes"] == 4*2*16
    assert metadata["codec_roundtrip_byte_identical"]


def test_degenerate_faces_have_finite_unused_jacobian_and_corruption_is_rejected(tmp_path):
    positions=np.array([[[0,0,0],[1,0,0],[2,0,0]]],float)
    assert np.array_equal(TRIAL.affine_uv_jacobians(positions,np.zeros((1,3,2))),np.zeros((1,4)))
    sheet=dict(selected_triangle=np.zeros((1,1),np.int32),valid=np.ones((1,1),bool))
    metadata=TRIAL.store_jacobian(tmp_path,"finite",sheet,np.array([[1,0,0,1.]]))
    (tmp_path/metadata["file"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError,match="stored hash"):
        TRIAL.read_jacobian(tmp_path,metadata)


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
    assert validation["stored_jacobians_verified"] == 2
    assert validation["jacobian_seam_checks"][0]["mismatched_pixels"] == 0
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
