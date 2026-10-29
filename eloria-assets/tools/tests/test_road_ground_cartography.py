"""Road-field cartography closure, sampler, height and native depth contracts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "eloria-assets/tools"
MAPTOOLS = ROOT / "eloria-assets/maps/continent-v2/_continent_v2"
sys.path[:0] = [str(TOOLS), str(MAPTOOLS), str(ROOT / "godot-client/tools")]
import road_ground_cartography as C
import render_region_cartography as RC
import render_minimap as RM
import publish_client as PC
import atlas_soft_ground as A


def sha(value):
    return hashlib.sha256(value).hexdigest()


def test_legacy_digest_stays_byte_identical(tmp_path):
    directory = tmp_path / "chunks/00_00"
    directory.mkdir(parents=True)
    (directory / "scene.glb").write_bytes(b"original geometry")
    (directory / "world.json").write_text(json.dumps({"asset": {"glb": "scene.glb"}}))
    rows = [{"id": "00_00", "manifest": "chunks/00_00/world.json"}]
    expected = sha(f"00_00 {sha(b'original geometry')}\n".encode())
    assert PC.chunks_digest(tmp_path, rows) == expected


def field_fixture(tmp_path):
    directory = tmp_path / "eloria-assets/maps/r/client/chunks/00_00"
    directory.mkdir(parents=True)
    resources = {}
    for name in ["ids.bin", "coeff.bin", "tile.png"]:
        (directory / name).write_bytes(name.encode())
        resources[name] = sha(name.encode())
    document = {"schema": "rabbitlands-road-terrain-blend-v1", "resources": resources,
                "field": {"coverage_mips": [], "triangle_ids": {"file": "ids.bin", "sha256": resources["ids.bin"]},
                          "affine_coefficients": {"file": "coeff.bin", "sha256": resources["coeff.bin"]}},
                "styles": [{"material_document": {"images": [{"uri": "tile.png"}]},
                            "externalResources": {"tile.png": resources["tile.png"]}}]}
    return directory, document


def test_digest_covers_fields_images_and_metadata_without_manifest_cycle(tmp_path):
    directory, document = field_fixture(tmp_path)
    (directory / "scene.glb").write_bytes(b"unchanged")
    def save():
        raw = json.dumps(document).encode()
        (directory / "roads.json").write_bytes(raw)
        config = {"metadata": "roads.json", "sha256": sha(raw)}
        (directory / "world.json").write_text(json.dumps({"asset": {"glb": "scene.glb"}, "roadGround": config}))
        return config
    config = save()
    assert len(C.dependencies(tmp_path, directory / "world.json", config)) == 4
    rows = [{"id": "00_00", "manifest": "chunks/00_00/world.json"}]
    first = PC.chunks_digest(directory.parents[1], rows)
    # Styling/environment-only manifest changes do not create a hash cycle.
    world = json.loads((directory / "world.json").read_text())
    world["environment"] = {"hour": 8}
    (directory / "world.json").write_text(json.dumps(world))
    assert PC.chunks_digest(directory.parents[1], rows) == first
    (directory / "ids.bin").write_bytes(b"new IDs")
    document["resources"]["ids.bin"] = sha(b"new IDs")
    document["field"]["triangle_ids"]["sha256"] = sha(b"new IDs")
    save()
    assert PC.chunks_digest(directory.parents[1], rows) != first
    (directory / "tile.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="resource changed"):
        PC.chunks_digest(directory.parents[1], rows)


def test_missing_top_resource_cannot_hide_a_material_dependency(tmp_path):
    directory, document = field_fixture(tmp_path)
    document["resources"].pop("tile.png")
    raw = json.dumps(document).encode()
    (directory / "roads.json").write_bytes(raw)
    with pytest.raises(ValueError, match="Undeclared/conflicting"):
        C.dependencies(tmp_path, directory / "world.json", {"metadata": "roads.json", "sha256": sha(raw)})


def test_highest_patch_height_ignores_triangle_vertex_order():
    base = np.array([[0, 0, 0], [2, 1, 0], [0, 0, 2]], float)
    patch = base[[2, 0, 1]].copy()
    patch[:, 1] += .012
    ground = [("Base", base, None, np.arange(3)), ("Patch", patch, None, np.arange(3))]
    chosen = C.highest_ground_triangles(ground, "Base", {"Base", "Patch"})
    np.testing.assert_allclose(chosen[0, :, 1], base[:, 1] + .012)


def test_atlas_keeps_pixel_alpha_and_source_factor_separate():
    class Pool:
        def __init__(self):
            self.images = {"tile": np.full((512, 512, 4), [128, 100, 50, 255], np.uint8)}
        def key(self, *args):
            return "tile"
    doc = {"materials": [{"pbrMetallicRoughness": {"baseColorFactor": [.3, .6, .2, 1.],
            "roughnessFactor": 1., "metallicFactor": 0., "baseColorTexture": {"index": 0}}}],
           "textures": [{"source": 0}], "images": [{"uri": "unused"}]}
    metadata = {"field": {"grid": {"pixels_per_metre": 4}},
                "styles": [{"id": 0, "material_document": doc, "externalResources": {}}]}
    atlas, factor = C.bake_atlas(RC, Pool(), metadata, np.ones((2, 2), np.int32),
                                 np.array([[0, 0, 0, 0, 0, 0, 0, 0]], np.float32),
                                 np.array([[255, 0], [255, 0]], np.uint8), Path("roads.json"), "r")
    assert factor == (.3, .6, .2, 1.)
    np.testing.assert_array_equal(atlas[100, 0], [128, 100, 50, 255])
    assert atlas[100, -1, 3] == 0


def test_reader_version_changes_only_for_intersecting_converted_sources(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    (package / "a.json").write_text(json.dumps({"roadGround": {"metadata": "roads.json"}}))
    source = {"package": package, "offset": [0, 0],
              "chunks": [{"manifest": "a.json", "bounds": {"min": [10, 0, 10], "max": [20, 0, 20]}}]}
    monkeypatch.setattr(RM, "sources", lambda *args: [source])
    assert RM.reader_version_for(tmp_path, "r", ([0, 0], [5, 5])) == 2
    assert RM.reader_version_for(tmp_path, "r", ([0, 0], [15, 15])) == 3


def test_mask_clamp_preserves_alpha_mode_bits_and_guards_hooks():
    source = (RC.TOOLKIT / "native/raster.c").read_text()
    shader = (ROOT / "godot-client/src/world/soft_ground.gdshader").read_text()
    specialized = A.specialize(source, shader)
    assert "(mat->alpha_mode & 3) == 1" in specialized
    material = RC.R.RenderMaterial("field", alpha_mode="MASK")
    material.atlas_wrap = (RC.CLAMP_TO_EDGE, RC.CLAMP_TO_EDGE)
    assert RC.clamp_flags(material) == 12
    with pytest.raises(ValueError, match="exactly once"):
        A.specialize(source.replace(A.MASK_HOOK, "changed"), shader)


def test_native_mask_clamp_and_bridge_prop_occlusion(tmp_path):
    scene = RC.R.Scene()
    colors = []
    floor = scene.add_material(RC.R.RenderMaterial("floor", (.02, .5, .02, 1), double_sided=True))
    scene.add_texture("road", np.full((512, 512, 4), [180, 100, 20, 255], np.uint8))
    road = RC.R.RenderMaterial("road", albedo="road", alpha_mode="MASK", double_sided=True)
    road.atlas_wrap = (RC.CLAMP_TO_EDGE, RC.CLAMP_TO_EDGE)
    road_id = scene.add_material(road)
    bridge = scene.add_material(RC.R.RenderMaterial("bridge", (.02, .02, .7, 1), double_sided=True))
    prop = scene.add_material(RC.R.RenderMaterial("prop", (.7, .02, .02, 1), double_sided=True))
    # Half the mask is transparent, and UVs deliberately exceed its extent:
    # clamping must keep that half transparent instead of repeating the road.
    scene._texture_images[0][:, 256:, 3] = 0
    def quad(bounds, y, material, uv_scale=1):
        x0, z0, x1, z1 = bounds
        p = np.array([[x0,y,z0],[x1,y,z0],[x0,y,z1],[x1,y,z1]], np.float32)
        scene.positions.append(p); scene.normals.append(np.tile([0,1,0], (4,1)).astype(np.float32))
        scene.uvs.append(np.array([[0,0],[uv_scale,0],[0,1],[uv_scale,1]], np.float32))
        scene.indices.append(np.array([0,2,1,1,2,3], np.int32) + scene._offset)
        scene.tri_material.append(np.full(2, material, np.int32)); scene._offset += 4
        colors.append(np.ones((4,4), np.float32))
    quad([0,0,4,4], 0, floor)
    quad([0,0,4,4], .01, road_id, 2)
    quad([.2,.2,.8,.8], 1, bridge)
    quad([.2,3.2,.8,3.8], 2, prop)
    rgb, _, _, _ = RC.raster(scene, np.concatenate(colors), np.array([0,0]), np.array([4,4]),
                             (64,64), supersample=1, minify=False, native_cache=tmp_path / "native")
    pixels = np.asarray(rgb)
    assert pixels[32, 8, 0] > pixels[32, 8, 1]        # road
    assert pixels[32, 56, 1] > pixels[32, 56, 0]      # clamped transparent road -> floor
    assert pixels[8, 8, 2] > pixels[8, 8, 0]         # bridge above road
    assert pixels[56, 8, 0] > pixels[56, 8, 1]       # prop above road


def test_native_legacy_repeat_mask_pixels_remain_identical(tmp_path, monkeypatch):
    old_source = subprocess.check_output(["git", "show", "HEAD:eloria-assets/tools/atlas_soft_ground.py"], cwd=ROOT)
    old_path = tmp_path / "old_adapter.py"
    old_path.write_bytes(old_source)
    spec = importlib.util.spec_from_file_location("legacy_atlas_adapter", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    scene = RC.R.Scene()
    floor = scene.add_material(RC.R.RenderMaterial("floor", (.1, .4, .1, 1), double_sided=True))
    image = np.full((512,512,4), [140,80,20,255], np.uint8)
    image[:,256:,3] = 0
    scene.add_texture("cutout", image)
    mask = scene.add_material(RC.R.RenderMaterial("mask", albedo="cutout", alpha_mode="MASK", double_sided=True))
    colors = []
    for height, material in [(0, floor), (.1, mask)]:
        scene.positions.append(np.array([[0,height,0],[4,height,0],[0,height,4],[4,height,4]],np.float32))
        scene.normals.append(np.tile([0,1,0],(4,1)).astype(np.float32))
        scene.uvs.append(np.array([[0,0],[2,0],[0,2],[2,2]],np.float32))
        scene.indices.append(np.array([0,2,1,1,2,3],np.int32)+scene._offset)
        scene.tri_material.append(np.full(2,material,np.int32));scene._offset+=4
        colors.append(np.ones((4,4),np.float32))
    args=(scene,np.concatenate(colors),np.array([0,0]),np.array([4,4]),(64,64))
    current=RC.raster(*args,supersample=1,minify=False,native_cache=tmp_path/'new')[0]
    monkeypatch.setattr(RC.atlas_soft_ground,"load",old.load)
    previous=RC.raster(*args,supersample=1,minify=False,native_cache=tmp_path/'old')[0]
    np.testing.assert_array_equal(np.asarray(current),np.asarray(previous))
