"""Packaging contract for the textures the world's 3D scenes sample.

The editor imports a texture VRAM-compressed with mipmaps (and a normal map
red-green compressed) only after it draws a material using it; a headless
--import draws nothing. A package built in a fresh worktree therefore shipped
184 world textures lossless without mipmaps that a worktree an editor session
had touched shipped compressed. The packager now finds those textures
(scene_textures) and writes their import settings before the import.
"""
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "package_client.py"
SPEC = importlib.util.spec_from_file_location("package_client_scene_textures", SOURCE)
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)

WORLD = "godot-client/assets/world"
PILOT = "godot-client/src/dev/map_authoring_pilot"
PRESETS = f"{PILOT}/style/textures"
CHUNK = f"{WORLD}/continent/chunk.glb"
ALBEDO = f"{WORLD}/continent/_textures/albedo.png"
NORMAL = f"{WORLD}/continent/_textures/normal.png"
HARVESTABLE = f"{WORLD}/harvestables/amber_resin.glb"
EXTRACTED = f"{WORLD}/harvestables/amber_resin_amber_resin Base Color.png"
REGION = "godot-client/world_authoring/regions/vale/vale.tscn"
PROTOTYPE = "godot-client/world_authoring/regions/vale/assets/prototypes/rock.glb"
PROTOTYPE_TEXTURE = "godot-client/world_authoring/regions/vale/assets/textures/rock.jpg"
GROUND = f"{PRESETS}/ground-basecolor.png"
GROUND_NORMAL = f"{PRESETS}/ground-normal.png"
GROUND_ORM = f"{PRESETS}/ground-orm.png"
MASK = f"{WORLD}/biome_blend/masks/00_00-base.png"


def _glb(document: dict) -> bytes:
    """A GLB holding only its JSON chunk."""
    raw = json.dumps({"asset": {"version": "2.0"}, **document}).encode("utf-8")
    raw += b" " * (-len(raw) % 4)
    return (b"glTF" + struct.pack("<II", 2, 20 + len(raw))
            + struct.pack("<II", len(raw), 0x4E4F534A) + raw)


def _material_glb(images: list[dict], normal_image: int | None = None) -> bytes:
    """A GLB whose one material samples image 0 as base colour and normal_image as its normal map."""
    material = {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
    if normal_image is not None:
        material["normalTexture"] = {"index": normal_image}
    return _glb({"images": images, "textures": [{"source": i} for i in range(len(images))],
                 "materials": [material]})


def _track(monkeypatch, files: list[str]) -> None:
    monkeypatch.setattr(package, "tracked", lambda _tree, *specs: [
        f for f in files if any(f == s or f.startswith(s.rstrip("/") + "/") for s in specs)])


def _write(build: Path, files: dict[str, bytes | str]) -> list[str]:
    for relative, content in files.items():
        (build / relative).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            (build / relative).write_text(content, encoding="utf-8")
        else:
            (build / relative).write_bytes(content)
    return list(files)


def _world_tree(build: Path, monkeypatch, extra: dict | None = None) -> list[str]:
    """A continent chunk naming two textures by URI and a harvestable with an embedded image."""
    files = _write(build, {
        "godot-client/src/actors/glb_scene_cache.gd":
            'if not resource_path.begins_with("res://assets/actors/"):\n\treturn null\n',
        CHUNK: _material_glb([{"uri": "_textures/albedo.png"}, {"uri": "_textures/normal.png"}], 1),
        ALBEDO: b"x", NORMAL: b"x",
        HARVESTABLE: _material_glb([{"name": "amber_resin Base Color", "bufferView": 0,
                                     "mimeType": "image/png"}]),
        EXTRACTED: b"x",
        "godot-client/src/imported-world-fixture.tscn":
            '[gd_scene]\n[ext_resource type="PackedScene" path="res://assets/world/harvestables/amber_resin.glb" id="1"]\n',
        **(extra or {})})
    _track(monkeypatch, files)
    return files


def test_glTF_uri_and_extracted_images_are_scene_textures(tmp_path, monkeypatch):
    _world_tree(tmp_path, monkeypatch)
    assert package.scene_textures(tmp_path) == {ALBEDO: False, NORMAL: True, EXTRACTED: False}


def test_a_glTF_texture_outside_the_scene_roots_is_left_to_the_editor(tmp_path, monkeypatch):
    # world_authoring holds the map editor's region sources; the game never loads them.
    _world_tree(tmp_path, monkeypatch, {
        PROTOTYPE: _material_glb([{"uri": "../textures/rock.jpg"}]), PROTOTYPE_TEXTURE: b"x",
        "godot-client/tests/fixtures/world.glb": _material_glb([{"uri": "../../assets/world/x.png"}]),
        f"{WORLD}/x.png": b"x"})
    assert set(package.scene_textures(tmp_path)) == {ALBEDO, NORMAL, EXTRACTED}


@pytest.mark.parametrize("images,extracted", [
    # The image name, its extension dropped and made a valid file name.
    ([{"name": "bark.diffuse.png", "bufferView": 0}], "tree_bark.diffuse.png"),
    ([{"name": "bark: <wet>", "bufferView": 0}], "tree_bark_ _wet_.png"),
    ([{"name": "textures/leaf", "bufferView": 0}], "tree_leaf.png"),
    ([{"name": "leaf.jpg", "bufferView": 0, "mimeType": "image/jpeg"}], "tree_leaf.jpg"),
    # No name: the image index. A repeated name: "_<index>".
    ([{"bufferView": 0}], "tree_0.png"),
    ([{"uri": "leaf.png", "name": "leaf"}, {"name": "leaf", "bufferView": 0}], "tree_leaf_1.png"),
])
def test_an_embedded_image_counts_through_the_copy_the_editor_extracted(tmp_path, monkeypatch,
                                                                         images, extracted):
    glb = f"{WORLD}/interactives/tree.glb"
    files = _write(tmp_path, {glb: _glb({"images": images}),
                              f"{WORLD}/interactives/{extracted}": b"x",
                              f"{WORLD}/interactives/leaf.png": b"x",
                              "godot-client/src/imported-tree.tscn":
                                  '[gd_scene]\n[ext_resource type="PackedScene" path="res://assets/world/interactives/tree.glb" id="1"]\n'})
    _track(monkeypatch, files)
    found = package.scene_textures(tmp_path)
    assert f"{WORLD}/interactives/{extracted}" in found
    # An extracted copy the commit does not hold is not a scene texture.
    _track(monkeypatch, [f for f in files if not f.endswith(extracted)])
    assert f"{WORLD}/interactives/{extracted}" not in package.scene_textures(tmp_path)


REGION_SCENE = f"""[gd_scene format=3]

[ext_resource type="Texture2D" uid="uid://a" path="res://src/dev/map_authoring_pilot/style/textures/ground-basecolor.png" id="1_a"]
[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/ground-normal.png" id="2_n"]
[ext_resource path="res://src/dev/map_authoring_pilot/style/textures/ground-orm.png" type="Texture2D" id="3_o"]
[ext_resource type="Shader" path="res://src/dev/map_authoring_pilot/style/worn_path.gdshader" id="4_s"]
[ext_resource type="Texture2D" path="res://world_authoring/regions/vale/assets/textures/rock.jpg" id="5_r"]
[ext_resource type="Texture2D" path="res://assets/world/ui_only.png" id="6_u"]
[ext_resource type="Texture2D" path="res://assets/world/canvas_only.png" id="7_c"]

[sub_resource type="StandardMaterial3D" id="Mat_a"]
albedo_texture = ExtResource("1_a")
normal_enabled = true
normal_texture = ExtResource("2_n")

[sub_resource type="ShaderMaterial" id="Mat_s"]
shader = ExtResource("4_s")
shader_parameter/ground_albedo = ExtResource("1_a")
shader_parameter/ground_orm = ExtResource("3_o")
shader_parameter/unused = ExtResource("6_u")

[sub_resource type="StandardMaterial3D" id="Mat_r"]
albedo_texture = ExtResource("5_r")

[sub_resource type="Shader" id="Shader_c"]
code = "shader_type canvas_item;
uniform sampler2D tex : source_color;
"

[sub_resource type="ShaderMaterial" id="Mat_c"]
shader = SubResource("Shader_c")
shader_parameter/tex = ExtResource("7_c")

[node name="Vale" type="Node3D"]

[node name="Icon" type="TextureRect" parent="."]
texture = ExtResource("6_u")
"""

WORN_PATH = """shader_type spatial;
uniform sampler2D ground_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_normal : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D ground_orm : filter_linear_mipmap_anisotropic, repeat_enable;
"""


def test_3d_materials_in_scenes_and_resources_name_scene_textures(tmp_path, monkeypatch):
    files = _write(tmp_path, {
        f"{WORLD}/vale.tscn": REGION_SCENE, f"{PILOT}/style/worn_path.gdshader": WORN_PATH,
        GROUND: b"x", GROUND_NORMAL: b"x", GROUND_ORM: b"x", PROTOTYPE_TEXTURE: b"x",
        f"{WORLD}/ui_only.png": b"x", f"{WORLD}/canvas_only.png": b"x",
        f"{WORLD}/path_normal.png": b"x", f"{WORLD}/rock_orm.png": b"x",
        # A material resource file, and a spatial shader whose normal map is a parameter.
        f"{WORLD}/rock.tres": """[gd_resource type="ORMMaterial3D" format=3]

[ext_resource type="Texture2D" path="res://assets/world/rock_orm.png" id="1"]

[resource]
orm_texture = ExtResource("1")
""",
        f"{WORLD}/path.tres": """[gd_resource type="ShaderMaterial" load_steps=3 format=3]

[ext_resource type="Shader" path="res://src/dev/map_authoring_pilot/style/worn_path.gdshader" id="1"]
[ext_resource type="Texture2D" path="res://assets/world/path_normal.png" id="2"]

[resource]
shader = ExtResource("1")
shader_parameter/ground_normal = ExtResource("2")
"""})
    # Without the preset folder, so only what the scenes name counts.
    monkeypatch.setattr(package, "RUNTIME_SCENE_TEXTURE_FOLDERS", ())
    _track(monkeypatch, files)
    assert package.scene_textures(tmp_path) == {
        GROUND: False, GROUND_NORMAL: True, GROUND_ORM: False,
        f"{WORLD}/rock_orm.png": False, f"{WORLD}/path_normal.png": True}


def test_the_preset_library_folder_is_sampled_in_3d(tmp_path, monkeypatch):
    files = _write(tmp_path, {GROUND: b"x", GROUND_NORMAL: b"x", GROUND_ORM: b"x",
                              f"{PRESETS}/desert-basecolor.provenance.json": "{}",
                              f"{PILOT}/style/texture_packs/delta-silt/delta-silt-v001.png": b"x"})
    _track(monkeypatch, files)
    assert package.scene_textures(tmp_path) == {GROUND: False, GROUND_NORMAL: True, GROUND_ORM: False}


def test_the_map_editor_region_sources_are_not_read(tmp_path, monkeypatch):
    # world_authoring leaves the package (owner call 2026-10-05), so what its scenes and prototypes draw
    # decides nothing: only what the game samples does.
    files = _write(tmp_path, {
        REGION: REGION_SCENE, f"{PILOT}/style/worn_path.gdshader": WORN_PATH,
        PROTOTYPE: _material_glb([{"uri": "../../../../../src/dev/map_authoring_pilot/style/textures/ground-orm.png"}]),
        GROUND: b"x", GROUND_NORMAL: b"x", GROUND_ORM: b"x", PROTOTYPE_TEXTURE: b"x"})
    monkeypatch.setattr(package, "RUNTIME_SCENE_TEXTURE_FOLDERS", ())
    _track(monkeypatch, files)
    assert package.scene_textures(tmp_path) == {}
    # The same scene outside world_authoring counts.
    files += _write(tmp_path, {f"{PILOT}/vale.tscn": REGION_SCENE})
    _track(monkeypatch, files)
    assert package.scene_textures(tmp_path) == {GROUND: False, GROUND_NORMAL: True, GROUND_ORM: False}


PACKS = f"{PILOT}/style/texture_packs"
PRESET_SCRIPT = f"""const _TEXTURE_ROOT := "res://src/dev/map_authoring_pilot/style/textures/"
const _PRESETS := {{
	"Delta silt": {{"albedo_path": "res://src/dev/map_authoring_pilot/style/texture_packs/delta-silt/delta-silt-v001.png"}},
	"Reed thatch": {{'albedo_path': 'res://src/dev/map_authoring_pilot/style/texture_packs/reed-thatch/reed-thatch-v001.png'}},
}}
"""


def test_textures_the_presets_or_the_map_data_name_are_scene_textures(tmp_path, monkeypatch):
    # The biome-blend terrain loads the texture packs by the res:// path the map data records, which the
    # editor published from MapAuthoringTexturePresets' albedo_path entries; no shipped scene names them.
    silt, thatch, moss, scree, snow = (f"{PACKS}/{name}/{name}-v001.png" for name in (
        "delta-silt", "reed-thatch", "forest-floor-moss", "alpine-scree-lichen", "alpine-snow-crust"))
    picture = f"{WORLD}/cartography/four_gates.png"

    def res(path: str) -> str:
        return "res://" + path.removeprefix("godot-client/")

    files = _write(tmp_path, {
        package.RUNTIME_SCENE_TEXTURE_SOURCES[0]: PRESET_SCRIPT,
        f"{WORLD}/biome_blend/catalog.json": json.dumps({"chunks": [{"base": [{"albedoTexture": res(scree)}]}]}),
        "eloria-assets/maps/four-gates/chunks/02_07/world.json": json.dumps(
            {"biomeBlend": {"palette": [{"albedoTexture": res(moss)}]}, "minimap": res(picture)}),
        # Provenance names textures the game never loads; one outside the scene roots is not a scene texture.
        "eloria-assets/maps/four-gates/authoring/continent-authoring.json": json.dumps({"surfaces": [
            {"albedoTexture": res(snow)}, {"albedoTexture": "res://world_authoring/regions/vale/assets/textures/rock.jpg"}]}),
        silt: b"x", thatch: b"x", moss: b"x", scree: b"x", snow: b"x", picture: b"x", PROTOTYPE_TEXTURE: b"x"})
    monkeypatch.setattr(package, "RUNTIME_SCENE_TEXTURE_FOLDERS", ())
    _track(monkeypatch, files)
    # The map's 2D picture is named under another key, and is left alone.
    assert package.scene_textures(tmp_path) == {silt: False, thatch: False, moss: False, scree: False}
    # A script the commit does not track names nothing.
    _track(monkeypatch, [f for f in files if f != package.RUNTIME_SCENE_TEXTURE_SOURCES[0]])
    assert set(package.scene_textures(tmp_path)) == {moss, scree}


def test_a_texture_whose_import_the_commit_tracks_keeps_it(tmp_path, monkeypatch):
    # The biome masks' committed settings keep Godot from bleeding RGB under zero alpha.
    files = _world_tree(tmp_path, monkeypatch, {
        f"{WORLD}/terrain.glb": _material_glb([{"uri": "biome_blend/masks/00_00-base.png"}]),
        MASK: b"x", MASK + ".import": "[remap]\n"})
    _track(monkeypatch, files)
    assert MASK not in package.scene_textures(tmp_path)


def _params(sidecar: Path) -> dict[str, str]:
    return package._import_settings(sidecar)[1]


def test_prepare_build_tree_writes_the_scene_texture_settings(tmp_path, monkeypatch):
    build = tmp_path / "client-src"
    (build / ".git").mkdir(parents=True)
    _world_tree(build, monkeypatch)
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(package, "actor_shipping", lambda _tree: {
        "pck_folders": set(), "loose_folders": set(), "kept": {}})
    monkeypatch.setattr(package, "write_actor_import_settings", lambda *_args: {})

    package.prepare_build_tree(build, "a" * 40)

    for relative, normal_map in ((ALBEDO, "0"), (NORMAL, "1"), (EXTRACTED, "0")):
        importer, params = package._import_settings(build / (relative + ".import"))
        assert importer == "texture"
        assert params["compress/mode"] == "2" and params["mipmaps/generate"] == "true"
        assert params["detect_3d/compress_to"] == "0"
        assert params["compress/normal_map"] == normal_map


# What Godot leaves after importing a texture the editor saw drawn: products,
# uid, and the roughness detection 4.7.2 writes (a mode that changes no pixel).
EDITOR_IMPORT = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://da8msg64hip2d"
path.s3tc="res://.godot/imported/albedo.png-1.s3tc.ctex"
metadata={{
"imported_formats": ["s3tc_bptc"],
"vram_texture": true
}}

[deps]

source_file="res://assets/world/continent/_textures/albedo.png"
dest_files=["res://.godot/imported/albedo.png-1.s3tc.ctex"]

[params]

{params}"""


def test_settings_already_right_are_left_alone(tmp_path, monkeypatch):
    textures = {ALBEDO: False, NORMAL: True}
    for relative, normal_map in textures.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        params = "".join(f"{k}={v}\n" for k, v in package.scene_texture_import_params(normal_map))
        (tmp_path / (relative + ".import")).write_text(EDITOR_IMPORT.format(params=params), encoding="utf-8")
    before = {r: (tmp_path / (r + ".import")).read_text(encoding="utf-8") for r in textures}

    counts = package.write_scene_texture_import_settings(tmp_path, textures)

    assert counts == {"texture": 0, "normal_map": 0, "kept": 2}
    assert {r: (tmp_path / (r + ".import")).read_text(encoding="utf-8") for r in textures} == before


@pytest.mark.parametrize("key,value", [
    ("compress/mode", "0"), ("mipmaps/generate", "false"), ("detect_3d/compress_to", "1"),
    ("compress/normal_map", "1"),
    # An editor-touched tree: same pixels, but a fresh worktree would not have it.
    ("roughness/mode", "8"),
])
def test_other_settings_are_rewritten(tmp_path, monkeypatch, key, value):
    (tmp_path / ALBEDO).parent.mkdir(parents=True)
    params = "".join(f"{k}={value if k == key else v}\n" for k, v in package.URI_TEXTURE_IMPORT_PARAMS)
    (tmp_path / (ALBEDO + ".import")).write_text(EDITOR_IMPORT.format(params=params), encoding="utf-8")

    counts = package.write_scene_texture_import_settings(tmp_path, {ALBEDO: False})

    assert counts == {"texture": 1, "normal_map": 0, "kept": 0}
    assert _params(tmp_path / (ALBEDO + ".import")) == dict(package.URI_TEXTURE_IMPORT_PARAMS)
    # The texture keeps its uid, so the scenes that name it by uid still find it.
    assert package.IMPORT_UID.findall((tmp_path / (ALBEDO + ".import")).read_text(encoding="utf-8")) == [
        "uid://da8msg64hip2d"]


def test_a_rewritten_import_keeps_the_uid_it_had_and_gets_none_otherwise(tmp_path):
    # Without its uid line Godot 4.7.2 gave 107 rewritten textures of the long-lived build worktree new uids
    # (a fresh worktree derives the same uid as every checkout); the region scenes and imported glTF scenes
    # name them by the old one.
    old = tmp_path / (ALBEDO + ".import")
    old.parent.mkdir(parents=True)
    old.write_text(EDITOR_IMPORT.format(params="compress/mode=0\n"), encoding="utf-8")
    new = tmp_path / (NORMAL + ".import")

    counts = package.write_scene_texture_import_settings(tmp_path, {ALBEDO: False, NORMAL: True})

    assert counts == {"texture": 2, "normal_map": 1, "kept": 0}
    text = old.read_text(encoding="utf-8")
    assert package.IMPORT_UID.findall(text) == ["uid://da8msg64hip2d"]
    assert package._import_settings(old) == ("texture", dict(package.URI_TEXTURE_IMPORT_PARAMS))
    assert text.index('uid="uid://da8msg64hip2d"') < text.index("[params]")
    assert package.IMPORT_UID.findall(new.read_text(encoding="utf-8")) == []
    assert package._import_settings(new) == ("texture", dict(package.NORMAL_MAP_IMPORT_PARAMS))
    # A uid in another section is not the texture's.
    old.write_text('[remap]\n\nimporter="texture"\n\n[deps]\n\nuid="uid://notmine"\n\n[params]\n\n'
                   "compress/mode=0\n", encoding="utf-8")
    package.write_scene_texture_import_settings(tmp_path, {ALBEDO: False})
    assert package.IMPORT_UID.findall(old.read_text(encoding="utf-8")) == []


def _imported(build: Path, relative: str, product: str | None, normal_map: bool = False,
              **changes: str) -> None:
    """An imported scene texture: its .import with the scene settings (changed) and its product."""
    project = build / "godot-client"
    params = dict(package.scene_texture_import_params(normal_map), **{
        k.replace("__", "/"): v for k, v in changes.items()})
    dest = ""
    if product:
        (project / ".godot/imported" / product).parent.mkdir(parents=True, exist_ok=True)
        (project / ".godot/imported" / product).write_bytes(b"GST2 imported texture")
        dest = f'dest_files=["res://.godot/imported/{product}"]\n'
    (build / (relative + ".import")).write_text(
        '[remap]\n\nimporter="texture"\n\n[deps]\n\n' + dest + "\n[params]\n\n"
        + "".join(f"{k}={v}\n" for k, v in params.items()), encoding="utf-8")


def _import_world(build: Path) -> None:
    _imported(build, ALBEDO, "albedo.png-1.s3tc.ctex")
    _imported(build, NORMAL, "normal.png-1.s3tc.ctex", normal_map=True)
    _imported(build, EXTRACTED, "amber.png-1.s3tc.ctex")


def test_scene_texture_check_accepts_vram_imports(tmp_path, monkeypatch):
    _world_tree(tmp_path, monkeypatch)
    _import_world(tmp_path)
    package.check_scene_texture_imports(tmp_path / "godot-client")


@pytest.mark.parametrize("relative,product,normal_map,changes,message", [
    (ALBEDO, "albedo.png-1.ctex", False, {"compress__mode": "0", "mipmaps__generate": "false"},
     "albedo.png: imported as texture with compress/mode=0, mipmaps/generate=false"),
    # Settings written, but the product is still the lossless one of an earlier import.
    (ALBEDO, "albedo.png-1.ctex", False, {}, "albedo.png: no VRAM-compressed import product"),
    (NORMAL, "normal.png-1.s3tc.ctex", False, {}, "normal.png: imported as texture with compress/normal_map=0"),
    (EXTRACTED, None, False, {}, "Base Color.png: no VRAM-compressed import product"),
])
def test_scene_texture_check_rejects_a_texture_imported_for_2d(tmp_path, monkeypatch, relative, product,
                                                               normal_map, changes, message):
    _world_tree(tmp_path, monkeypatch)
    _import_world(tmp_path)
    _imported(tmp_path, relative, product, normal_map, **changes)
    with pytest.raises(package.PackageError, match=re.escape(message)):
        package.check_scene_texture_imports(tmp_path / "godot-client")


def test_scene_texture_check_rejects_a_missing_import(tmp_path, monkeypatch):
    _world_tree(tmp_path, monkeypatch)
    _import_world(tmp_path)
    (tmp_path / (EXTRACTED + ".import")).unlink()
    with pytest.raises(package.PackageError, match="Base Color.png: missing .import remap"):
        package.check_scene_texture_imports(tmp_path / "godot-client")


def _write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4.7 (format 4) PCK directory listing empty files with these names."""
    header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
    reserved = b"\0" * 64
    directory = struct.pack("<I", len(names))
    for name in names:
        raw = name.encode("utf-8")
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw
        directory += struct.pack("<QQ", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + struct.pack("<QQ", 0, len(header) + 16 + len(reserved)) + reserved + directory)


def test_scene_texture_pack_check_wants_each_remap_and_product(tmp_path, monkeypatch):
    build = tmp_path / "build"
    app = tmp_path / "app"
    _world_tree(build, monkeypatch)
    _import_world(build)
    names = [r.removeprefix("godot-client/") + ".import" for r in (ALBEDO, NORMAL, EXTRACTED)] + [
        ".godot/imported/albedo.png-1.s3tc.ctex", ".godot/imported/normal.png-1.s3tc.ctex",
        ".godot/imported/amber.png-1.s3tc.ctex"]
    _write_pck(app / "RabbitLands.pck", names)
    package.check_scene_texture_pack(build, app)

    _write_pck(app / "RabbitLands.pck", [n for n in names if not n.startswith(".godot/imported/normal")])
    with pytest.raises(package.PackageError, match="normal.png: its imported product is not in the PCK"):
        package.check_scene_texture_pack(build, app)
    _write_pck(app / "RabbitLands.pck", [n for n in names if "albedo.png.import" not in n])
    with pytest.raises(package.PackageError, match="albedo.png: not in the PCK"):
        package.check_scene_texture_pack(build, app)


# --- the real tree ---------------------------------------------------------------

def _repo_tracked(*specs: str) -> list[str]:
    try:
        return package.tracked(package.REPO, *specs)
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git cannot list this checkout: {error}")


def test_the_preset_library_builds_its_paths_in_a_declared_folder():
    # MapAuthoringTexturePresets loads _TEXTURE_ROOT + "<family>-<map>.png"; no
    # scene names most of those files, so the folder is declared instead.
    presets = package.CLIENT / "src/dev/map_authoring_pilot/style/texture_presets.gd"
    if not presets.is_file():
        pytest.skip("the map-authoring pilot is not checked out")
    root = re.search(r'const _TEXTURE_ROOT := "res://([^"]+)"', presets.read_text(encoding="utf-8"))
    assert root, "texture_presets.gd no longer declares _TEXTURE_ROOT"
    assert "godot-client/" + root.group(1).rstrip("/") in package.RUNTIME_SCENE_TEXTURE_FOLDERS


def test_every_texture_pack_the_game_samples_is_a_scene_texture():
    # No scene a package carries names six of the packs the biome-blend terrain samples; only the map
    # editor's region scenes did, and scene_textures no longer reads those. The presets and the map data
    # name them by res:// path, and so must keep them VRAM-compressed with mipmaps.
    sources = [package.REPO / package.RUNTIME_SCENE_TEXTURE_SOURCES[0],
               package.CLIENT / "assets/world/biome_blend/catalog.json"]
    absent = [s for s in sources if not s.is_file()]
    if absent:
        pytest.skip(f"{absent[0]} is not checked out")
    tracked = set(_repo_tracked("godot-client"))
    roots = tuple(root + "/" for root in package.SCENE_TEXTURE_ROOTS)
    named = {"godot-client/" + literal for source in sources
             for literal in package.RES_IMAGE_LITERAL.findall(source.read_text(encoding="utf-8"))}
    named = {p for p in named if p.startswith(roots) and p in tracked and p + ".import" not in tracked}
    packs = {p for p in named if "/style/texture_packs/" in p}
    assert len(packs) >= 10, sorted(packs)
    found = package.scene_textures(package.REPO)
    assert sorted(named - set(found)) == []
    assert not any(found[p] for p in packs)


def test_every_embedded_world_image_is_committed_beside_its_glTF():
    # An embedded image's extracted copy that is not committed appears only
    # during a build's import, after the packager wrote the settings: it would
    # ship with the import defaults, lossless and without mipmaps.
    roots = tuple(root + "/" for root in package.SCENE_TEXTURE_ROOTS)
    files = [f for f in _repo_tracked(*package.SCENE_TEXTURE_ROOTS) if f.startswith(roots)]
    stems = {f.rsplit(".", 1)[0] for f in files if f.lower().endswith(package.IMAGE_SUFFIXES)}
    raw_world = package.world_import_shipping(package.REPO)["raw_models"]
    gltfs = [f for f in files if f.lower().endswith(package.GLTF_SUFFIXES) and f not in raw_world]
    absent = [f for f in gltfs if not (package.REPO / f).is_file()]
    if absent:
        pytest.skip(f"{len(absent)} world glTFs are not checked out, e.g. {absent[0]}")
    missing = [f"{gltf} -> {gltf.rsplit('.', 1)[0]}_{name}"
               for gltf in gltfs
               for name in package._extracted_image_names(package.gltf_document(package.REPO / gltf))
               if name is not None and f"{gltf.rsplit('.', 1)[0]}_{name}" not in stems]
    assert missing == []
