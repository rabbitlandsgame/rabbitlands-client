"""Contracts for the isolated producer: no engine or production asset writes."""
import importlib.util
from pathlib import Path
import sys
import json
from types import SimpleNamespace
import zstandard

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("road_texture_trial", TOOLS/"road_texture_trial.py")
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)


def test_collision_compaction_preserves_signed_zero_and_corner_order():
    positions = np.array([[0,0,0], [1,0,0], [0,0,1], [0,0,0], [-0.,0,0], [99,99,99]], dtype="<f4")
    indices = np.array([0,1,2,3,2,1,4,1,2], dtype="<u4")
    packed, remapped = TRIAL.compact_collision(positions, indices)
    assert len(packed) == 4
    assert remapped.dtype == np.dtype("<u2")
    assert packed[remapped].tobytes() == positions[indices].tobytes()


def test_node_frames_preserve_parent_rotation_and_scale():
    document = {"nodes":[{"name":"root","translation":[10,2,20],"scale":[2,3,4],"children":[1]},
                         {"name":"road","translation":[1,1,1]}]}
    frames, paths, parents = TRIAL.node_frames(document)
    assert np.array_equal(frames[1] @ [0,0,0,1], [12,5,24,1])
    assert paths[1] == "root/road" and parents[1] == 0


def test_raster_shared_edge_does_not_become_an_overlap_sheet():
    triangles = np.array([[[0,0,0],[2,0,0],[0,0,2]], [[2,0,0],[2,0,2],[0,0,2]]], float)
    uv = triangles[..., [0,2]] * 3 + 100
    grid = dict(width=4,height=4,origin_xz=[0,0],pixels_per_metre=2)
    sheets, conflicts = TRIAL.rasterize(triangles, uv, np.ones((2,3)), grid)
    assert len(sheets) == 1 and conflicts == 0
    assert sheets[0]["valid"].all()
    xx, zz = np.meshgrid((np.arange(4)+.5)/2, (np.arange(4)+.5)/2)
    assert np.allclose(sheets[0]["uv"], np.stack([xx,zz],axis=-1)*3+100)


def test_overlapping_different_uv_retains_ordered_separate_sheet():
    triangle = np.array([[[0,0,0],[2,0,0],[0,0,2]]], float)
    triangles = np.concatenate([triangle,triangle])
    uv = triangles[..., [0,2]]
    uv[1] += 30
    grid = dict(width=4,height=4,origin_xz=[0,0],pixels_per_metre=2)
    sheets, conflicts = TRIAL.rasterize(triangles, uv, np.full((2,3),.5), grid)
    assert len(sheets) == 2 and conflicts > 0
    valid = sheets[0]["valid"]
    assert np.allclose(sheets[1]["uv"][valid]-sheets[0]["uv"][valid], 30)


def test_gutter_samples_agree_across_adjacent_aligned_frames():
    triangles = np.array([[[0,0,0],[4,0,0],[0,0,2]], [[4,0,0],[4,0,2],[0,0,2]]],float)
    uv = triangles[..., [0,2]]*2
    left = dict(width=8,height=4,origin_xz=[-1,0],pixels_per_metre=2)
    right = dict(width=8,height=4,origin_xz=[1,0],pixels_per_metre=2)
    a = TRIAL.rasterize(triangles,uv,np.ones((2,3)),left)[0][0]
    b = TRIAL.rasterize(triangles,uv,np.ones((2,3)),right)[0][0]
    assert np.array_equal(a["valid"][:,4:],b["valid"][:,:4])
    assert np.array_equal(a["uv"][:,4:],b["uv"][:,:4])


def test_mips_keep_large_unwrapped_uv_at_alpha_edge():
    uv = np.zeros((4,4,2))
    uv[0,0] = [1048.25,-533.75]
    coverage = np.zeros((4,4));coverage[0,0] = 1
    levels = TRIAL.mip_chain(uv,coverage)
    assert [v[0].shape[:2] for v in levels] == [(4,4),(2,2),(1,1)]
    for mapped, _ in levels:
        assert np.array_equal(mapped, np.broadcast_to(uv[0,0],mapped.shape))
    assert levels[-1][1][0,0] == 1/16


def test_storage_inventory_counts_actual_mips_and_each_referenced_file_once(tmp_path):
    (tmp_path/"tile-a").write_bytes(b"same detail tile")
    (tmp_path/"tile-b").write_bytes(b"same detail tile")
    (tmp_path/"mip-0").write_bytes(b"base")
    (tmp_path/"mip-1").write_bytes(b"mip")
    result = TRIAL.inventory([*tmp_path.iterdir(),tmp_path/"tile-a",tmp_path/"mip-1"])
    assert result["unique_files"] == 4
    assert result["unique_contents"] == 3
    assert result["bytes"] == 2*len(b"same detail tile")+len(b"base")+len(b"mip")
    assert result["content_deduplicated_bytes"] == len(b"same detail tile")+len(b"base")+len(b"mip")


def test_sparse_sheet_crop_preserves_world_pixel_centres():
    sheet = dict(valid=np.zeros((20,30),bool), alpha=np.zeros((20,30)), uv=np.zeros((20,30,2)))
    sheet["valid"][8:10,12:15] = True
    frame = dict(width=30,height=20,origin_xz=[-10,30],pixels_per_metre=4,gutter_pixels=2)
    cropped, grid = TRIAL.crop_sheet(sheet,frame)
    assert grid["origin_xz"] == [-7.5,31.5]
    assert cropped["valid"].shape == (6,7)
    assert cropped["valid"][2:4,2:5].all()


def test_zstd_flow_preserves_every_rg32f_mip_byte(tmp_path):
    sheet = dict(valid=np.ones((4,4),bool), alpha=np.ones((4,4)),
                 uv=np.arange(32,dtype=float).reshape(4,4,2)+1000)
    result = TRIAL.store_fields(tmp_path,"flow",sheet)
    encoded = (tmp_path/result["uv_file"]).read_bytes()
    decoded = zstandard.ZstdDecompressor().decompress(encoded)
    expected = b"".join(uv.astype("<f4").tobytes() for uv,_ in TRIAL.mip_chain(sheet["uv"],sheet["alpha"]))
    assert decoded == expected
    assert TRIAL.sha(decoded) == result["uv_sha256"]
    assert TRIAL.sha(encoded) == result["uv_file_sha256"]
    assert result["uv_uncompressed_bytes"] == len(expected)
    assert sum(m["uv_bytes"] for m in result["mips"]) == len(expected)
    assert all(TRIAL.sha((tmp_path/m["coverage"]).read_bytes()) == m["coverage_sha256"] for m in result["mips"])


def test_material_document_remaps_only_indices_preserving_used_resources():
    document = dict(materials=[{"name":"road","pbrMetallicRoughness":{"baseColorTexture":{"index":2}}}],
                    textures=[{"source":0},{"source":1},{"source":2,"sampler":1}],
                    images=[{"uri":"unused0.png"},{"uri":"unused1.png"},{"uri":"exact.png"}],
                    samplers=[{"wrapS":33071},{"wrapS":10497,"minFilter":9987}])
    material = TRIAL.material_document({"document":document},{"material_index":0})
    assert material["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"] == 0
    assert material["images"] == [{"uri":"exact.png"}]
    assert material["samplers"] == [document["samplers"][1]]
    assert document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"] == 2


def test_pruned_base_contains_no_original_visual_road_or_its_vertices(tmp_path):
    positions = np.array([[0,0,0],[1,0,0],[0,0,1]],dtype="<f4")
    road = positions + [0,.055,0]
    body = positions.tobytes()+road.astype("<f4").tobytes()
    document = dict(asset={"version":"2.0"}, scenes=[{"nodes":[0,1]}], scene=0,
                    nodes=[{"name":"Terrain_test","mesh":0},{"name":"Walk_test","mesh":1}],
                    meshes=[{"primitives":[{"attributes":{"POSITION":0}}]},
                            {"primitives":[{"attributes":{"POSITION":1}}]}],
                    accessors=[{"bufferView":i,"componentType":5126,"count":3,"type":"VEC3"} for i in range(2)],
                    bufferViews=[{"buffer":0,"byteOffset":i*36,"byteLength":36} for i in range(2)],
                    buffers=[{"byteLength":72}], materials=[],textures=[],images=[],samplers=[])
    destination = tmp_path/"base.glb"
    TRIAL.prune_visual_roads({"document":document,"body":body,"directory":tmp_path},[{"node_index":1}],destination)
    actual, packed = TRIAL.SM.read_glb(destination)
    assert actual["nodes"][1] == {"name":"Walk_test"}
    assert len(actual["meshes"]) == 1
    assert packed == positions.tobytes()


def test_complete_trial_keeps_colliders_removes_roads_and_verifies_adjacent_halos(tmp_path,monkeypatch):
    root = tmp_path/"repo"
    for number,chunk in enumerate(["00_00","00_01"]):
        directory = root/f"eloria-assets/maps/continent-v2/test/client/chunks/{chunk}"
        directory.mkdir(parents=True)
        vertices = np.array([[0,0,0],[2,0,0],[0,0,2],[2,0,0],[2,0,2],[0,0,2]],dtype="<f4")
        vertices[:,0] += number*2
        road = vertices.copy();road[:,1] += .055
        arrays = [vertices,road,vertices[:,[0,2]],np.ones((6,4),dtype="<f4")]
        body = bytearray();views=[];accessors=[]
        for array,kind in zip(arrays,["VEC3","VEC3","VEC2","VEC4"]):
            views.append(dict(buffer=0,byteOffset=len(body),byteLength=array.nbytes));body.extend(array.tobytes())
            accessors.append(dict(bufferView=len(views)-1,componentType=5126,count=6,type=kind))
        document = dict(asset={"version":"2.0"},scene=0,scenes=[{"nodes":[0,1]}],
                        nodes=[{"name":f"Terrain_test_{chunk}","mesh":0},
                               {"name":f"Walk_test_foo_test_{chunk}","mesh":1}],
                        meshes=[{"primitives":[{"attributes":{"POSITION":0},"material":0}]},
                                {"primitives":[{"attributes":{"POSITION":1,"TEXCOORD_0":2,"COLOR_0":3},"material":0}]}],
                        accessors=accessors,bufferViews=views,buffers=[{"byteLength":len(body)}],
                        materials=[{"name":"exact dirt","pbrMetallicRoughness":{"roughnessFactor":1}}],
                        textures=[],images=[],samplers=[])
        (directory/"world.glb").write_bytes(TRIAL.SM.write_glb(document,body))
        (directory/"world.json").write_text(json.dumps({"asset":{"id":"test","glb":"world.glb"},
                                                        "externalResources":{},"externalMeshes":{}}))
    monkeypatch.setattr(TRIAL.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0))
    out = root/"eloria-assets/maps/continent-v2/test/client/.local/trial"
    report = TRIAL.bake(root,root,out,"test",["00_00","00_01"],["foo"],ppms=(2,))
    check = report["variants"]["2"]["validation"]
    assert check["ok"] and check["exact_collision_primitives"] == 2
    assert check["seam_checks"][0]["covered_pixel_samples"] > 0
    assert check["seam_checks"][0]["mismatched_fragments"] == 0
    assert report["variants"]["2"]["bytes"] > 0
