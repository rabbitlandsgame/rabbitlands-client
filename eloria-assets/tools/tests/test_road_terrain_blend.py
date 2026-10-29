"""Production road classification, compact affine fields, and retained geometry."""
import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import road_terrain_blend as P


def catalog():
    return dict(roads={"road-a":{}},bridges={"pier-a":{}},assets={"Authored_deck":{}})


def test_saved_typed_controls_classify_roads_bridges_and_asset_descendants():
    assert P.classify_walk("Walk_r_road-a_r_01_01","r","01_01",catalog()) == ("road","road-a")
    assert P.classify_walk("Walk_AuthoredBridge_r__pier-a_r","r","01_01",catalog()) == ("bridge","pier-a")
    assert P.classify_walk("Walk_deck","r","01_01",catalog(),"Authored_deck/Walk_deck") == ("retained_asset_walk","Authored_deck")
    with pytest.raises(ValueError,match="unverified"):
        P.classify_walk("Walk_r_unknown_r_01_01","r","01_01",catalog())
    with pytest.raises(ValueError,match="unclassified"):
        P.classify_walk("Walk_bridge_in_name_only","r","01_01",catalog())


def test_authoring_catalog_requires_typed_source_scripts(tmp_path):
    folder=tmp_path/"godot-client/world_authoring/regions/r";folder.mkdir(parents=True)
    (folder/"r.tscn").write_text('''[gd_scene format=3]
[ext_resource type="Script" path="res://src/dev/map_authoring_region/path_control.gd" id="path"]
[ext_resource type="Script" path="res://src/dev/map_authoring_region/bridge_control.gd" id="bridge"]
[node name="Road" type="Path3D" parent="Roads"]
script = ExtResource("path")
path_id = "road-a"
[node name="River" type="Path3D" parent="Rivers"]
script = ExtResource("path")
path_id = "river-a"
kind = "river"
[node name="Pier" type="Node3D" parent="Bridges"]
script = ExtResource("bridge")
bridge_id = "pier-a"
''')
    result=P.authoring_catalog(tmp_path,"r")
    assert list(result["roads"]) == ["road-a"]
    assert list(result["bridges"]) == ["pier-a"]


def test_geometric_guard_rejects_an_elevated_path_even_with_road_metadata():
    corners=np.array([[[.2,.055,.2],[1.7,.055,.2],[.2,.055,1.7]]])
    roads=[dict(triangles=corners)]
    result=P.terrain_clearance(roads,np.array([0,0]),np.zeros((2,2)))
    assert result["maximum_lift_error_metres"] == 0
    corners[:,:,1]+=2
    with pytest.raises(ValueError,match="not verified"):
        P.terrain_clearance(roads,np.array([0,0]),np.zeros((2,2)))


def test_boundary_road_can_use_actual_neighbor_terrain_without_extrapolating():
    corners=np.array([[[2.2,.055,.2],[2.7,.055,.2],[2.2,.055,.7]]])
    own=np.zeros((2,2));neighbor=np.zeros((2,2))
    result=P.terrain_clearance([dict(triangles=corners)],np.array([0,0]),own,
                               neighbors=[("neighbor",np.array([2,0]),neighbor,np.array([0,0]))])
    assert result["own_terrain_corner_samples"] == 0
    assert result["neighboring_terrain_corner_samples"] == {"neighbor":3}
    assert result["missing_corner_samples"] == 0


def test_footstep_class_uses_runtime_keyword_order_and_default(tmp_path):
    folder=tmp_path/"godot-client/src/audio";folder.mkdir(parents=True)
    (folder/"footstep_surface.gd").write_text('const SURFACES := {"stone": ["stone"], "sand": ["sand"]}')
    assert P.footstep_class(tmp_path,"sandstone") == "stone"
    assert P.footstep_class(tmp_path,"authored-r29") == "dirt"


@pytest.mark.parametrize("maximum,fmt",[(65535,"RG8"),(65536,"RGB8"),(16777215,"RGB8")])
def test_id_storage_is_exact_across_channel_boundaries(maximum,fmt):
    values=np.array([[1,255,256,maximum]],np.uint32)
    packed,format_name=P.pack_ids(values)
    assert format_name == fmt
    assert np.array_equal(P.unpack_ids(packed),values)


def sample_field():
    triangles=np.array([[[0,0,0],[2,0,0],[0,0,2]],[[0,0,0],[2,0,0],[0,0,2]]],float)
    flow=np.stack((triangles[0][:,[0,2]],triangles[0][:,[0,2]]+20))
    alpha=np.full((2,3),.5)
    grid=dict(origin_xz=[-.5,-.5],width=12,height=12,pixels_per_metre=4,gutter_pixels=2)
    sheet=P.B.dominant_raster(triangles,flow,alpha,grid)
    return sheet,grid,triangles,flow,P.B.affine_uv_jacobians(triangles,flow),np.array([0,1])


def test_compact_maps_reconstruct_covered_and_halo_uv_and_selected_style():
    sheet,grid,triangles,flow,j,styles=sample_field()
    ids,rows,result=P.compact_field(sheet,grid,triangles,flow,j,styles)
    assert result["maximum_covered_uv_abs_error"] == 0
    assert result["maximum_halo_uv_abs_error"] == 0
    assert result["source_jacobian_float32_byte_identical"]
    assert np.all(rows[ids-1,6] == 1) # The last authored material wins ties.
    assert np.all(ids>0)


def test_rasterized_overlap_winner_is_independent_of_window_batch_size():
    rng=np.random.default_rng(42)
    triangles=np.array([[[0,0,0],[2,0,0],[0,0,2]],[[0,0,0],[2,0,0],[0,0,2]]],float)
    triangles[1,:,0]+=.03
    uv=rng.uniform(-100,100,(2,3,2));alpha=np.ones((2,3))
    big=P.dominant_raster(triangles,uv,alpha,dict(width=8,height=8,origin_xz=[0,0],pixels_per_metre=4))
    for row,col in np.argwhere(big["valid"]):
        tiny=P.dominant_raster(triangles,uv,alpha,dict(width=1,height=1,origin_xz=[col/4,row/4],pixels_per_metre=4))
        for key in ("uv","alpha","selected_triangle"):
            assert np.array_equal(big[key][row,col],tiny[key][0,0])


def test_stored_compact_fields_verify_hashes_all_mips_and_corruption(tmp_path):
    values=sample_field()
    field=P.store_field(tmp_path,*values)
    ids,rows=P.read_field(tmp_path,field)
    assert ids.shape == values[0]["valid"].shape
    assert field["coverage_mips"][-1]["width"] == field["coverage_mips"][-1]["height"] == 1
    assert field["affine_coefficients"]["record_count"] == len(rows)
    path=tmp_path/field["triangle_ids"]["file"]
    path.write_bytes(path.read_bytes()+b"bad")
    with pytest.raises(ValueError,match="stored field SHA"):
        P.read_field(tmp_path,field)


def test_pruning_removes_road_nodes_and_retains_bridge_geometry_and_transform(tmp_path):
    positions=np.array([[0,0,0],[2,0,0],[0,0,2]],dtype="<f4")
    doc=dict(asset={"version":"2.0"},buffers=[{"byteLength":positions.nbytes}],
             bufferViews=[{"buffer":0,"byteOffset":0,"byteLength":positions.nbytes}],
             accessors=[{"bufferView":0,"componentType":5126,"count":3,"type":"VEC3"}],
             meshes=[{"primitives":[{"attributes":{"POSITION":0}}]},{"primitives":[{"attributes":{"POSITION":0}}]}],
             nodes=[{"name":"Road_WorldPlacement","children":[1]},{"name":"Road","mesh":0},
                    {"name":"Bridge","mesh":1,"translation":[0,4,0]}],scenes=[{"nodes":[0,2]}],scene=0)
    path=tmp_path/"source.glb";path.write_bytes(P.T.SM.write_glb(doc,positions.tobytes()))
    frames,paths,parents=P.T.node_frames(doc)
    source=dict(document=doc,body=positions.tobytes(),directory=tmp_path,path=path,frames=frames,paths=paths,parents=parents)
    destination=tmp_path/"base.glb"
    result=P.prune_roads(source,[dict(node_index=1,road_node_name="Road")],destination)
    assert [n["name"] for n in result["nodes"]] == ["Bridge"]
    final,body=P.T.SM.read_glb(destination)
    assert final["nodes"][0]["translation"] == [0,4,0]
    a=final["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
    assert P.T.accessor(final,body,a,False).tobytes() == positions.tobytes()
