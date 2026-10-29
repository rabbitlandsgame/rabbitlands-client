"""Cross-checkout promotion, resource rebasing, recovery, and repeatability."""
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import apply_road_terrain_blend as A
P=A.P


@pytest.fixture
def staged(tmp_path,monkeypatch):
    root=tmp_path/"source";destination=root/"eloria-assets/maps/continent-v2/r/client/chunks/01_01"
    destination.mkdir(parents=True);texture=root/"eloria-assets/maps/_shared/textures/tile.png"
    texture.parent.mkdir(parents=True);P.Image.new("RGB",(2,2),(120,80,30)).save(texture)
    positions=np.array([[0,0,0],[2,0,0],[0,0,2]],dtype="<f4")
    doc=dict(asset={"version":"2.0"},buffers=[{"byteLength":positions.nbytes}],
             bufferViews=[{"buffer":0,"byteOffset":0,"byteLength":positions.nbytes}],
             accessors=[{"bufferView":0,"componentType":5126,"count":3,"type":"VEC3"}],
             meshes=[{"primitives":[{"attributes":{"POSITION":0},"material":0}]}],
             materials=[{"name":"ground","pbrMetallicRoughness":{"baseColorTexture":{"index":0}}}],
             images=[{"uri":P.T.relative(texture,destination)}],textures=[{"source":0}],
             nodes=[{"name":"Walk_r_road-a_r_01_01","mesh":0},{"name":"Base","mesh":0}],scenes=[{"nodes":[0,1]}],scene=0)
    (destination/"world.glb").write_bytes(P.T.SM.write_glb(doc,positions.tobytes()))
    manifest=dict(asset={"glb":"world.glb"},externalResources={P.T.relative(texture,destination):P.T.sha(texture.read_bytes())},
                  externalMeshes={},custom={"preserve":"newer metadata"})
    P.T.write_json(destination/"world.json",manifest);source=P.load_chunk(destination)
    stage=root/"eloria-assets/maps/continent-v2/r/client/.local/stage"
    leaf=stage/"r/chunks/01_01";leaf.mkdir(parents=True)
    P.prune_roads(source,[dict(node_index=0,road_node_name="Walk_r_road-a_r_01_01")],leaf/"world.glb")
    tri=positions.reshape(1,3,3).astype(float);flow=tri[...,[0,2]]
    grid=dict(origin_xz=[0,0],width=8,height=8,pixels_per_metre=4,gutter_pixels=2)
    sheet=P.dominant_raster(tri,flow,np.ones((1,3)),grid)
    field=P.store_field(leaf,sheet,grid,tri,flow,P.B.affine_uv_jacobians(tri,flow),np.array([0]))
    uri=P.T.relative(texture,leaf);digest=P.T.sha(texture.read_bytes())
    material=dict(asset={"version":"2.0"},materials=[{"pbrMetallicRoughness":{"baseColorTexture":{"index":0}}}],
                  images=[{"uri":uri}],textures=[{"source":0}])
    metadata=dict(schema=P.SCHEMA,region="r",chunk="01_01",pixels_per_metre=4,
                  source_glb_sha256=P.T.sha(source["path"].read_bytes()),
                  removed_road_node_names=["Walk_r_road-a_r_01_01"],field=field,
                  styles=[dict(id=0,material_document=material,externalResources={uri:digest},footstep_class="dirt")])
    metadata["resources"]={name:P.T.sha((leaf/name).read_bytes()) for name in A.field_files(metadata)}
    metadata["resources"][uri]=digest;P.T.write_json(leaf/"roads.json",metadata)
    monkeypatch.setattr(A.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0))
    return root,stage,destination,texture


def test_dry_run_preserves_sources_and_rebases_all_resource_uris(staged):
    root,stage,destination,texture=staged;before=(destination/"world.glb").read_bytes()
    plan=A.build_plan(root,stage)
    assert (destination/"world.glb").read_bytes()==before
    metadata=json.loads(plan["writes"][destination/"roads.json"])
    image=metadata["styles"][0]["material_document"]["images"][0]["uri"]
    assert (destination/image).resolve()==texture
    assert image in metadata["resources"]
    manifest=json.loads(plan["writes"][destination/"world.json"])
    assert manifest["custom"]=={"preserve":"newer metadata"}
    assert manifest["roadGround"]["sha256"]==P.T.sha(plan["writes"][destination/"roads.json"])


def test_apply_copies_every_original_before_any_mutation_and_is_idempotent(staged,monkeypatch):
    root,stage,destination,_=staged;plan=A.build_plan(root,stage);recovery=root/".local/recovery-test"
    originals={Path(path):Path(path).read_bytes() for path,digest in plan["before_sha256"].items() if digest is not None}
    actual_replace=A.os.replace
    def checked_replace(source,target):
        for path,data in originals.items():assert (recovery/path.relative_to(root)).read_bytes()==data
        actual_replace(source,target)
    monkeypatch.setattr(A.os,"replace",checked_replace)
    result=A.apply_plan(plan,recovery)
    assert result["applied"] and A.valid_existing_leaf(root,destination)
    assert json.loads((recovery/"receipt.json").read_text())["complete"]
    assert not A.build_plan(root,stage)["writes"]


def test_cross_checkout_stage_maps_images_by_verified_logical_asset_path(staged,tmp_path):
    source,stage,destination,texture=staged;root=tmp_path/"target"
    target=root/destination.relative_to(source);shutil.copytree(destination,target)
    target_texture=root/texture.relative_to(source);target_texture.parent.mkdir(parents=True);shutil.copyfile(texture,target_texture)
    plan=A.build_plan(root,stage);A.apply_plan(plan,root/".local/recovery")
    metadata=json.loads((target/"roads.json").read_text())
    assert A.valid_existing_leaf(root,target)
    assert all(str(source) not in value for value in metadata["resources"])
    for uri in metadata["resources"]:assert (target/uri).resolve().is_relative_to(root/"eloria-assets")


def test_cross_checkout_refuses_changed_shared_image(staged,tmp_path):
    source,stage,destination,texture=staged;root=tmp_path/"target"
    shutil.copytree(destination,root/destination.relative_to(source))
    target=root/texture.relative_to(source);target.parent.mkdir(parents=True);target.write_bytes(b"changed")
    with pytest.raises(ValueError,match="differs from staged source"):
        A.build_plan(root,stage)


def test_recovery_preflight_preserves_newer_destination_edits(staged):
    root,stage,destination,_=staged;plan=A.build_plan(root,stage)
    path=destination/"world.json";path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(ValueError,match="changed after plan"):
        A.apply_plan(plan,root/".local/recovery")
    assert not (root/".local/recovery").exists()


def test_only_obsolete_owned_leaf_resources_are_removed(staged):
    root,stage,destination,texture=staged
    old=destination/"previous-roads.json";owned=destination/"old-owned.bin";owned.write_bytes(b"old field")
    keep=destination/"unrelated.bin";keep.write_bytes(b"unrelated")
    P.T.write_json(old,dict(schema=P.SCHEMA,field=dict(triangle_ids={"file":"old-owned.bin"},affine_coefficients={"file":"old-owned.bin"},coverage_mips=[]),
                          resources={"old-owned.bin":P.T.sha(owned.read_bytes()),P.T.relative(texture,destination):P.T.sha(texture.read_bytes())}))
    manifest=json.loads((destination/"world.json").read_text());manifest["roadGround"]=dict(metadata=old.name)
    P.T.write_json(destination/"world.json",manifest)
    plan=A.build_plan(root,stage)
    assert set(plan["deletes"])=={old,owned}
    A.apply_plan(plan,root/".local/recovery")
    assert keep.exists() and texture.exists() and not old.exists() and not owned.exists()


def test_finish_hook_skips_already_valid_stripped_leaves(staged,monkeypatch):
    root,stage,destination,_=staged;A.apply_plan(A.build_plan(root,stage),root/".local/recovery")
    P.T.write_json(destination.parents[1]/"world.json",dict(streamingChunks={"chunks":[{"id":"01_01","manifest":"chunks/01_01/world.json"}]}))
    monkeypatch.setattr(P,"authoring_catalog",lambda *a:dict(roads={},bridges={},assets={}))
    monkeypatch.setattr(P,"bake_region",lambda *a,**kw:pytest.fail("already-stripped leaf must not be rebaked"))
    report=A.finish_region(root,"r")
    assert report["chunks"]==0 and report["skipped"]==["01_01"]
