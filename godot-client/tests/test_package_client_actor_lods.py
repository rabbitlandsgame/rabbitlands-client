"""Packaging contract for actor files: each ships once, where the exported game reads it.

glTF actors are read loose (GlbSceneCache and the animation importer open
globalized paths, which an export resolves beside the executable, never in
the pack); the face masks are load()ed through ResourceLoader and the
equipment glTFs' URI textures are asked of ResourceLoader first, so both are
imported into the PCK; actor images nothing names ship nowhere.
"""
import importlib.util
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "package_client.py"
SPEC = importlib.util.spec_from_file_location("package_client_actor_lods", SOURCE)
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)

NATIVE = "godot-client/assets/actors/native"
RACE = f"{NATIVE}/races/hero.glb"
LIBRARY = f"{NATIVE}/shared/library.glb"
CLOTH = f"{NATIVE}/equipment/cloth.glb"
CLOTH_VARIANT = f"{NATIVE}/equipment/variants/hero/cloth.glb"
CLOTH_TEXTURE = f"{NATIVE}/equipment/textures/cloth.jpg"
CLOTH_EXTRACTED = f"{NATIVE}/equipment/cloth_0.png"
MASK = f"{NATIVE}/face_masks/hero.png"
MASK_MANIFEST = f"{NATIVE}/face_masks/manifest.json"
CREATURE = f"{NATIVE}/creatures/fox.glb"
CREATURE_EXTRACTED = f"{NATIVE}/creatures/fox_Fur Base Color.png"
RACE_SOURCE = f"{NATIVE}/race_textures/hero/body_basecolor.png"
NECK = f"{NATIVE}/neck_textures/hero.png"
NECK_MANIFEST = f"{NATIVE}/neck_textures/manifest.json"
DROPPED = {CLOTH_EXTRACTED, CREATURE_EXTRACTED, RACE_SOURCE, NECK}


def _glb(images: list[str]) -> bytes:
    """A GLB holding only a JSON chunk that names these images by URI."""
    document = json.dumps({"asset": {"version": "2.0"},
                           "images": [{"uri": uri} for uri in images]}).encode("utf-8")
    document += b" " * (-len(document) % 4)
    return (b"glTF" + struct.pack("<II", 2, 20 + len(document))
            + struct.pack("<II", len(document), 0x4E4F534A) + document)


def _write_tree(build: Path, *, extra: tuple[str, ...] = (), models_extra: dict | None = None,
                sources: dict[str, str] | None = None) -> list[str]:
    """A build tree whose catalogs name one race, its library, one garment (whose GLBs
    name a texture by URI), a creature and a mask; plus an image of each dropped kind."""
    files = [RACE, LIBRARY, CLOTH, CLOTH_VARIANT, CLOTH_TEXTURE, CLOTH_EXTRACTED, MASK,
             MASK_MANIFEST, CREATURE, CREATURE_EXTRACTED, RACE_SOURCE, NECK, NECK_MANIFEST, *extra]
    for relative in files:
        (build / relative).parent.mkdir(parents=True, exist_ok=True)
        (build / relative).write_bytes(b"x")
    (build / CLOTH).write_bytes(_glb(["textures/cloth.jpg"]))
    (build / CLOTH_VARIANT).write_bytes(_glb(["../../textures/cloth.jpg"]))
    models = {"models": {
        "hero": {"scene": "res://" + RACE.removeprefix("godot-client/"),
                 "animationLibrary": "res://" + LIBRARY.removeprefix("godot-client/"),
                 "faceAppearance": {"mask": "res://" + MASK.removeprefix("godot-client/")}},
        "fox": {"scene": "res://" + CREATURE.removeprefix("godot-client/")}}}
    if models_extra:
        models["models"]["hero"].update(models_extra)
    equipment = {"models": {"4:1": {"scene": "res://" + CLOTH.removeprefix("godot-client/"),
                                    "variants": {"hero": {"scene": "res://" + CLOTH_VARIANT.removeprefix(
                                        "godot-client/")}}}}}
    for name, document in (("models.json", models), ("equipment.json", equipment)):
        path = build / "godot-client/data/actors" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document), encoding="utf-8")
    for relative, text in (sources or {}).items():
        (build / relative).parent.mkdir(parents=True, exist_ok=True)
        (build / relative).write_text(text, encoding="utf-8")
    return files + list(package.ACTOR_CATALOGS) + list(sources or {})


def _track(monkeypatch, files: list[str]) -> None:
    monkeypatch.setattr(package, "tracked", lambda _tree, *specs: [
        f for f in files if any(f == s or f.startswith(s.rstrip("/") + "/") for s in specs)])


def _import(build: Path, relative: str, name: str, *, product: bool = True,
            params: str = "") -> str:
    """An imported texture: its .import remap and (optionally) the product it names."""
    project = build / "godot-client"
    imported = project / ".godot/imported" / name
    imported.parent.mkdir(parents=True, exist_ok=True)
    if product:
        imported.write_bytes(b"GST2 imported texture")
    (build / (relative + ".import")).write_text(
        "[remap]\n\nimporter=\"texture\"\ntype=\"CompressedTexture2D\"\n"
        f'path="res://.godot/imported/{name}"\n\n[deps]\n\n'
        f'dest_files=["res://.godot/imported/{name}"]\n\n[params]\n\n{params}', encoding="utf-8")
    return f".godot/imported/{name}"


def _import_mask(build: Path, *, product: bool = True) -> str:
    return _import(build, MASK, "hero.png-test.ctex", product=product)


VRAM_PARAMS = "".join(f"{k}={v}\n" for k, v in package.URI_TEXTURE_IMPORT_PARAMS)


def _import_cloth_texture(build: Path, *, params: str = VRAM_PARAMS) -> str:
    return _import(build, CLOTH_TEXTURE, "cloth.jpg-test.s3tc.ctex", params=params)


def _skip(build: Path, relative: str) -> None:
    (build / (relative + ".import")).write_text(package.SKIP_IMPORT, encoding="utf-8")


def _skip_equipment(build: Path) -> None:
    for relative in (CLOTH, CLOTH_VARIANT, CLOTH_EXTRACTED):
        _skip(build, relative)


@pytest.mark.parametrize("line", [
    "WARNING: Ignoring torso cover profile orun-male-rear-neck-v1: surface fingerprint "
    "drifted (adadf7459870edb2824a2010e68656f7272c382d76621c216594cba95dedf07b)",
    "WARNING: glb cache: pack failed for assets/actors/native/races/hero.glb (Unconfigured)",
    "WARNING: Native hairstyle failed to load: res://assets/actors/native/hair/a.glb",
    "WARNING: Fitted hairstyle has an incompatible skeleton: res://assets/actors/native/hair/a.glb",
])
def test_the_smoke_launch_fails_on_an_actor_part_that_fell_back(tmp_path, monkeypatch, line):
    """A fallback is a warning, not a load error, and the packaged Orun male's
    dropped neck surface passed the smoke launch that way."""
    monkeypatch.setattr(package, "run_godot",
                        lambda *_args, **_kwargs: "Godot Engine v4.7.2\n" + line + "\n")
    with pytest.raises(package.PackageError, match="reported errors at startup"):
        package._launch(tmp_path / "app", tmp_path, {"binary": "RabbitLands.exe"})


def test_the_smoke_launch_passes_a_clean_start(tmp_path, monkeypatch):
    clean = "Godot Engine v4.7.2\nWARNING: 231 ObjectDB instances were leaked at exit\n"
    monkeypatch.setattr(package, "run_godot", lambda *_args, **_kwargs: clean)
    assert package._launch(tmp_path / "app", tmp_path, {"binary": "RabbitLands.exe"}) == clean


def test_export_presets_never_filter_out_the_actor_tree():
    # A blanket assets/actors exclusion would drop the face masks and the
    # equipment textures again; actor files are kept out of the import instead.
    actor_exclusions = [
        line for line in package.EXPORT_PRESETS.splitlines()
        if line.startswith("exclude_filter=") and "assets/actors" in line
    ]
    assert not actor_exclusions
    assert package.EXPORT_PRESETS.count('export_filter="all_resources"') == 2


def test_each_actor_file_ships_in_the_pck_loose_or_nowhere(tmp_path, monkeypatch):
    build = tmp_path / "build"
    _track(monkeypatch, _write_tree(build))

    shipping = package.actor_shipping(build)

    assert shipping["uri_textures"] == {CLOTH_TEXTURE}
    assert shipping["pck"] == {MASK, MASK_MANIFEST, CLOTH_TEXTURE}
    assert shipping["loose"] == {RACE, LIBRARY, CLOTH, CLOTH_VARIANT, CREATURE, NECK_MANIFEST}
    assert shipping["dropped"] == DROPPED
    assert shipping["pck_folders"] == {f"{NATIVE}/face_masks", f"{NATIVE}/equipment"}
    assert shipping["loose_folders"] == {f"{NATIVE}/{folder}" for folder in (
        "races", "shared", "creatures", "race_textures", "neck_textures")}


def test_tracked_import_settings_do_not_require_loose_runtime_copies(tmp_path, monkeypatch):
    build = tmp_path / "build"
    app = tmp_path / "app"
    sidecars = (CREATURE + ".import", CLOTH_TEXTURE + ".import", CREATURE + ".report.json")
    _track(monkeypatch, _write_tree(build, extra=sidecars))
    _import_mask(build)
    _import_cloth_texture(build)
    _write_pck(app / "RabbitLands.pck", GOOD_PCK)

    package.stage_loose_client_files(build, app)
    package.check_actor_pack(build, app)

    assert (app / CREATURE.removeprefix("godot-client/")).is_file()
    assert all(not (app / relative.removeprefix("godot-client/")).exists()
               for relative in sidecars)


def test_uri_textures_outside_the_imported_folders_stay_loose(tmp_path, monkeypatch):
    # The shared Superhero glTFs name their images by URI too; only the
    # equipment textures were the owner's call.
    hair = f"{NATIVE}/shared/hair.png"
    build = tmp_path / "build"
    files = _write_tree(build, extra=(hair,))
    (build / LIBRARY).write_bytes(_glb(["hair.png"]))
    _track(monkeypatch, files)

    shipping = package.actor_shipping(build)

    assert hair in shipping["loose"] and hair not in shipping["pck"]
    assert f"{NATIVE}/shared" in shipping["loose_folders"]


def test_a_catalog_or_source_name_keeps_an_image_out_of_the_drop(tmp_path, monkeypatch):
    # models.json naming a neck texture (faceAppearance.neckTexture) makes it a
    # load()ed resource; so does a client literal naming a race texture.
    build = tmp_path / "build"
    source = "godot-client/src/actors/skin.gd"
    _track(monkeypatch, _write_tree(
        build, models_extra={"neckTexture": "res://" + NECK.removeprefix("godot-client/")},
        sources={source: 'const BODY := "res://' + RACE_SOURCE.removeprefix("godot-client/") + '"\n'}))

    shipping = package.actor_shipping(build)

    assert {NECK, RACE_SOURCE} <= shipping["pck"]
    assert shipping["dropped"] == {CLOTH_EXTRACTED, CREATURE_EXTRACTED}
    assert {f"{NATIVE}/neck_textures", f"{NATIVE}/race_textures"} <= shipping["pck_folders"]


@pytest.mark.parametrize("line,kept", [
    ('var path := "res://assets/actors/native/race_textures/" + slug + "/body_basecolor.png"', True),
    ('var path := "res://assets/actors/native/race_textures/%s/body_basecolor.png" % slug', True),
    ('var path := "res://assets/actors/native/race_textures/{0}/body_basecolor.png".format([slug])', True),
    ('var path := "res://assets/actors/native/".path_join(folder)', True),
    # A directory kept in a const and joined later, where the literal itself
    # is followed by nothing that says so.
    ('const ROOT := "res://assets/actors/native/race_textures"\nvar path := ROOT.path_join(slug)', True),
    ('const NATIVE := "res://assets/actors/native"\nvar path := NATIVE.path_join("race_textures")', True),
    ("var path := 'res://assets/actors/native/race_textures/' + slug", True),
    ('var path := "/".join(["res://assets/actors/native/race_textures", slug, "body.png"])', True),
    ('var path := "".join(["res://assets/actors/native/race_textures/hero/body_basecolor.png", ext])',
     True),
    ('if not path.begins_with("res://assets/actors/"):', False),
    ("if not path.begins_with('res://assets/actors/native/race_textures'):", False),
])
def test_a_runtime_built_actor_path_keeps_the_images_it_can_reach(tmp_path, monkeypatch, line, kept):
    build = tmp_path / "build"
    _track(monkeypatch, _write_tree(build, sources={"godot-client/src/actors/skin.gd": line + "\n"}))

    shipping = package.actor_shipping(build)

    assert (RACE_SOURCE in shipping["loose"]) is kept
    assert (RACE_SOURCE in shipping["dropped"]) is not kept


@pytest.mark.parametrize("source,kept", [
    ("godot-client/addons/kit/skin.gd", True),
    ("godot-client/world_authoring/kit/skin.tscn", True),
    ("godot-client/assets/ui/skin.tres", True),
    ("godot-client/native/native_crowd/src/skin.cpp", True),
    # Never in a package: the export leaves docs, tests and tools out.
    ("godot-client/tests/test_skin.gd", False),
    ("godot-client/tools/skin.gd", False),
])
def test_a_built_path_anywhere_a_package_runs_keeps_its_images(tmp_path, monkeypatch, source, kept):
    build = tmp_path / "build"
    line = 'var path := "res://assets/actors/native/race_textures/" + slug\n'
    _track(monkeypatch, _write_tree(build, sources={source: line}))

    shipping = package.actor_shipping(build)

    assert (RACE_SOURCE in shipping["loose"]) is kept
    assert (RACE_SOURCE in shipping["dropped"]) is not kept


def test_a_single_quoted_file_literal_is_a_resource_the_game_loads(tmp_path, monkeypatch):
    build = tmp_path / "build"
    line = "const BODY := 'res://" + RACE_SOURCE.removeprefix("godot-client/") + "'\n"
    _track(monkeypatch, _write_tree(build, sources={"godot-client/world_authoring/kit/skin.gd": line}))

    shipping = package.actor_shipping(build)

    assert RACE_SOURCE in shipping["pck"]
    assert f"{NATIVE}/race_textures" in shipping["pck_folders"]


MAP_MANIFEST = "eloria-assets/maps/isle/world.json"


@pytest.mark.parametrize("relative,content,image", [
    ("godot-client/data/world/objects.json",
     {"icon": "res://" + RACE_SOURCE.removeprefix("godot-client/")}, RACE_SOURCE),
    ("godot-client/data/actors/native_asset_catalog.json",
     {"x": {"texture": "race_textures/hero/body_basecolor.png"}}, RACE_SOURCE),
    ("godot-client/data/ui/icons.json", {"body_basecolor.png": 1}, RACE_SOURCE),
    ("godot-client/data/actors/necks.json", {"root": "res://assets/actors/native/neck_textures"}, NECK),
    ("godot-client/data/actors/necks.json",
     {"pattern": "res://assets/actors/native/neck_textures/%s.png"}, NECK),
    ("godot-client/world_authoring/kit/props.json",
     {"skin": "C:\\Eloria\\app\\assets\\actors\\native\\creatures\\fox_Fur Base Color.png"},
     CREATURE_EXTRACTED),
    (MAP_MANIFEST, {"actors": ["res://assets/actors/native/neck_textures/hero.png"]}, NECK),
    ("godot-client/data/world/creatures.json", {"skin": "creatures/fox_Fur%20Base%20Color.png"},
     CREATURE_EXTRACTED),
    ("godot-client/data/i18n/strings.csv", "key,en\nicon,cloth_0.png\n", CLOTH_EXTRACTED),
    ("godot-client/addons/kit/kit.gd", "var name := 'fox_Fur Base Color.png'\n", CREATURE_EXTRACTED),
])
def test_other_shipped_text_naming_an_image_keeps_it_loose(tmp_path, monkeypatch, relative, content, image):
    # The drop is decided from the catalogs, source literals and glTF URIs;
    # any other text a package carries that names the image keeps it, loose,
    # as every actor image shipped before the drop.
    build = tmp_path / "build"
    text = content if isinstance(content, str) else json.dumps(content)
    sources = {relative: text}
    if relative != MAP_MANIFEST:
        sources[MAP_MANIFEST] = "{}"
    _track(monkeypatch, _write_tree(build, sources=sources))

    shipping = package.actor_shipping(build)

    assert image in shipping["loose"] and image not in shipping["dropped"]
    assert any(where.startswith(relative + ": ") for where in shipping["kept"][image])
    assert shipping["dropped"] == DROPPED - {image}


@pytest.mark.parametrize("relative,content", [
    # Text no package carries names nothing a package reads.
    ("godot-client/tests/fixtures/necks.json", {"root": "res://assets/actors/native/neck_textures"}),
    ("godot-client/docs/necks.json", {"root": "res://assets/actors/native/neck_textures"}),
    ("eloria-assets/qa/fit-baseline.json", {"root": "godot-client/assets/actors/native/neck_textures"}),
    ("eloria-assets/maps/isle/qa/report.json", {"root": "godot-client/assets/actors/native/neck_textures"}),
    # A face mask's path, and a model key, are not the neck texture of that name.
    ("godot-client/data/actors/keys.json", {"hero": "res://" + MASK.removeprefix("godot-client/")}),
])
def test_text_that_ships_nowhere_or_names_a_namesake_keeps_nothing(tmp_path, monkeypatch, relative, content):
    build = tmp_path / "build"
    _track(monkeypatch, _write_tree(build, sources={relative: json.dumps(content), MAP_MANIFEST: "{}"}))

    shipping = package.actor_shipping(build)

    assert shipping["dropped"] == DROPPED
    assert shipping["kept"] == {}


def test_a_glTF_outside_the_actor_tree_naming_an_image_keeps_it(tmp_path, monkeypatch):
    build = tmp_path / "build"
    rock = "godot-client/assets/world/rock.glb"
    files = _write_tree(build, extra=(rock,))
    (build / rock).write_bytes(_glb(["../actors/native/creatures/fox_Fur%20Base%20Color.png"]))
    _track(monkeypatch, files)

    shipping = package.actor_shipping(build)

    assert CREATURE_EXTRACTED in shipping["loose"]
    assert shipping["kept"][CREATURE_EXTRACTED] == {f"{rock}: ../actors/native/creatures/fox_Fur Base Color.png"}


def test_a_kept_image_is_staged_loose_and_passes_the_pack_check(tmp_path, monkeypatch):
    build = tmp_path / "build"
    app = tmp_path / "app"
    _track(monkeypatch, _write_tree(build, sources={
        "godot-client/data/world/objects.json": json.dumps({"icon": "body_basecolor.png"})}))
    _import_mask(build)
    _import_cloth_texture(build)

    _write_pck(app / "RabbitLands.pck", GOOD_PCK)
    package.stage_loose_client_files(build, app)
    package.check_actor_pack(build, app)

    assert (app / RACE_SOURCE.removeprefix("godot-client/")).is_file()
    assert not (app / NECK.removeprefix("godot-client/")).exists()


def test_a_gltf_in_a_folder_the_pck_draws_on_stops_the_package(tmp_path, monkeypatch):
    # Its .bin buffers would be packed by the include filter, not shipped beside it.
    build = tmp_path / "build"
    _track(monkeypatch, _write_tree(build, extra=(f"{NATIVE}/face_masks/bust.gltf",)))
    with pytest.raises(package.PackageError, match="split the folder"):
        package.actor_shipping(build)


def test_a_loaded_resource_missing_from_the_commit_stops_the_package(tmp_path, monkeypatch):
    build = tmp_path / "build"
    files = _write_tree(build)
    _track(monkeypatch, [f for f in files if f != MASK])
    with pytest.raises(package.PackageError, match="catalogs load are not in the commit"):
        package.actor_shipping(build)


def test_prepare_build_tree_sets_the_import_barriers_and_settings(tmp_path, monkeypatch):
    build = tmp_path / "client-src"
    (build / ".git").mkdir(parents=True)
    _track(monkeypatch, _write_tree(build))
    stale_root = build / "godot-client/assets/actors/.gdignore"
    stale_mask = build / NATIVE / "face_masks/.gdignore"
    stale_equipment = build / NATIVE / "equipment/.gdignore"
    for stale in (stale_root, stale_mask, stale_equipment):
        stale.write_text("", encoding="utf-8")
    # An older build imported the garment as a scene and left the mask skipped.
    (build / (CLOTH + ".import")).write_text('[remap]\n\nimporter="scene"\n', encoding="utf-8")
    _skip(build, MASK)
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "")

    project = package.prepare_build_tree(build, "a" * 40)

    assert project == build / "godot-client"
    assert not stale_root.exists() and not stale_mask.exists() and not stale_equipment.exists()
    for folder in ("races", "shared", "creatures", "race_textures", "neck_textures"):
        assert (build / NATIVE / folder / ".gdignore").is_file()
    assert "assets/actors" not in (project / "export_presets.cfg").read_text()
    importer, params = package._import_settings(build / (CLOTH_TEXTURE + ".import"))
    assert importer == "texture"
    assert params["compress/mode"] == "2" and params["mipmaps/generate"] == "true"
    assert params["detect_3d/compress_to"] == "0"
    for relative in (CLOTH, CLOTH_VARIANT, CLOTH_EXTRACTED):
        assert package._import_settings(build / (relative + ".import"))[0] == "skip"
    assert not (build / (MASK + ".import")).exists()
    assert not (build / (MASK_MANIFEST + ".import")).exists()


def test_untracked_files_in_a_pck_folder_are_skipped_too(tmp_path, monkeypatch):
    # The build worktree keeps ignored files: an earlier import's extracted
    # equipment/*_0.jpg images reached the PCK of the first package built this way.
    build = tmp_path / "client-src"
    (build / ".git").mkdir(parents=True)
    _track(monkeypatch, _write_tree(build))
    leftover = build / NATIVE / "equipment/cloth_1.jpg"
    leftover.write_bytes(b"x")
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "")
    _import_mask(build)
    _import_cloth_texture(build)

    package.prepare_build_tree(build, "a" * 40)

    assert package._import_settings(build / NATIVE / "equipment/cloth_1.jpg.import")[0] == "skip"
    package.check_actor_imports(build / "godot-client")
    (build / NATIVE / "equipment/cloth_1.jpg.import").unlink()
    with pytest.raises(package.PackageError, match="cloth_1.jpg: imported, but it ships loose or nowhere"):
        package.check_actor_imports(build / "godot-client")


def test_an_untracked_json_in_a_pck_folder_stops_the_package(tmp_path, monkeypatch):
    # The include filter packs *.json whatever its import says.
    build = tmp_path / "client-src"
    (build / ".git").mkdir(parents=True)
    _track(monkeypatch, _write_tree(build))
    (build / NATIVE / "equipment/notes.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "")
    with pytest.raises(package.PackageError, match="notes.json is not a PCK file"):
        package.prepare_build_tree(build, "a" * 40)


def test_import_settings_that_are_already_right_are_left_alone(tmp_path, monkeypatch):
    # Godot rewrites a .import with its products; rewriting it again would
    # import the texture again on every build.
    build = tmp_path / "client-src"
    (build / ".git").mkdir(parents=True)
    _track(monkeypatch, _write_tree(build))
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "")
    _import_cloth_texture(build)
    _skip_equipment(build)
    before = {r: (build / (r + ".import")).read_text(encoding="utf-8")
              for r in (CLOTH_TEXTURE, CLOTH, CLOTH_VARIANT, CLOTH_EXTRACTED)}

    counts = package.write_actor_import_settings(build, package.actor_shipping(build))

    assert counts == {"texture": 0, "skip": 0, "default": 0, "kept": 4}
    assert {r: (build / (r + ".import")).read_text(encoding="utf-8") for r in before} == before

    _import_cloth_texture(build, params=VRAM_PARAMS.replace("compress/mode=2", "compress/mode=0"))
    counts = package.write_actor_import_settings(build, package.actor_shipping(build))
    assert counts["texture"] == 1
    assert package._import_settings(build / (CLOTH_TEXTURE + ".import"))[1]["compress/mode"] == "2"


def test_actor_import_check_accepts_the_imported_masks_and_textures(tmp_path, monkeypatch):
    build = tmp_path / "client-src"
    _track(monkeypatch, _write_tree(build))
    _import_mask(build)
    _import_cloth_texture(build)
    _skip_equipment(build)
    package.check_actor_imports(build / "godot-client")


@pytest.mark.parametrize("product,barrier", [(False, False), (True, True)])
def test_actor_import_check_rejects_a_mask_the_pck_would_lack(tmp_path, monkeypatch,
                                                              product, barrier):
    build = tmp_path / "client-src"
    _track(monkeypatch, _write_tree(build))
    _import_mask(build, product=product)
    _import_cloth_texture(build)
    _skip_equipment(build)
    if barrier:
        (build / NATIVE / "face_masks/.gdignore").write_text("", encoding="utf-8")
    with pytest.raises(package.PackageError, match="PCK actor imports are incomplete"):
        package.check_actor_imports(build / "godot-client")


@pytest.mark.parametrize("change,message", [
    ("compress/mode=2", "compress/mode=0"),
    ("mipmaps/generate=true", "mipmaps/generate=false"),
])
def test_actor_import_check_rejects_a_uri_texture_without_vram_or_mips(tmp_path, monkeypatch,
                                                                       change, message):
    build = tmp_path / "client-src"
    _track(monkeypatch, _write_tree(build))
    _import_mask(build)
    _import_cloth_texture(build, params=VRAM_PARAMS.replace(change, message))
    _skip_equipment(build)
    with pytest.raises(package.PackageError, match=message):
        package.check_actor_imports(build / "godot-client")


def test_actor_import_check_rejects_a_glTF_imported_beside_the_textures(tmp_path, monkeypatch):
    build = tmp_path / "client-src"
    _track(monkeypatch, _write_tree(build))
    _import_mask(build)
    _import_cloth_texture(build)
    _skip_equipment(build)
    (build / (CLOTH + ".import")).write_text('[remap]\n\nimporter="scene"\n', encoding="utf-8")
    with pytest.raises(package.PackageError, match="cloth.glb: imported, but it ships loose"):
        package.check_actor_imports(build / "godot-client")


def test_packaging_stops_before_export_when_pck_actor_imports_are_absent(
        tmp_path, monkeypatch):
    project = tmp_path / "client-src/godot-client"
    project.mkdir(parents=True)
    # main() reads the build tree's map registry (drop_preview_maps,
    # read_served_v2_packages) before the import.
    (tmp_path / "client-src" / package.REGISTRY_FILE).parent.mkdir(parents=True)
    (tmp_path / "client-src" / package.REGISTRY_FILE).write_text('{"maps": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        str(SOURCE), "--no-fetch", "--no-zip", "--no-smoke",
        "--build-dir", str(tmp_path / "client-src"),
        "--out", str(tmp_path / "dist"),
    ])
    monkeypatch.setattr(package, "find_godot", lambda _explicit: tmp_path / "godot.exe")
    monkeypatch.setattr(package, "git", lambda *_args, **_kwargs: "a" * 40 + "\n")
    monkeypatch.setattr(package, "prepare_build_tree", lambda *_args: project)
    monkeypatch.setattr(package, "import_project", lambda *_args: None)
    monkeypatch.setattr(
        package, "check_actor_imports",
        lambda _project: (_ for _ in ()).throw(package.PackageError("PCK actor imports are incomplete")),
    )
    monkeypatch.setattr(
        package, "export_project",
        lambda *_args: pytest.fail("export must not run without the face-mask imports"),
    )

    assert package.main() == 1


def test_only_loose_actor_files_are_staged_beside_the_executable(tmp_path, monkeypatch):
    build = tmp_path / "build"
    app = tmp_path / "app"
    _track(monkeypatch, _write_tree(build))
    _write_pck(app / "RabbitLands.pck", GOOD_PCK)

    package.stage_loose_client_files(build, app)

    staged = sorted(p.relative_to(app).as_posix() for p in app.rglob("*")
                    if p.is_file() and p.name != "RabbitLands.pck")
    assert staged == [
        "assets/actors/native/creatures/fox.glb",
        "assets/actors/native/equipment/cloth.glb",
        "assets/actors/native/equipment/variants/hero/cloth.glb",
        "assets/actors/native/neck_textures/manifest.json",
        "assets/actors/native/races/hero.glb",
        "assets/actors/native/shared/library.glb",
        "data/actors/equipment.json",
        "data/actors/models.json",
    ]


def _write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4.7 (format 4) PCK directory listing empty files with these names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
    reserved = b"\0" * 64
    directory_offset = len(header) + 8 + 8 + len(reserved)
    directory = struct.pack("<I", len(names))
    for name in names:
        raw = name.encode("utf-8")
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw
        directory += struct.pack("<QQ", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
    path.write_bytes(header + struct.pack("<QQ", 0, directory_offset) + reserved + directory)


def test_pck_directory_is_read_from_a_godot_47_pack(tmp_path):
    pck = tmp_path / "RabbitLands.pck"
    _write_pck(pck, ["assets/actors/native/face_masks/hero.png.import", "res://project.binary"])
    assert package.pck_paths(pck) == {
        "assets/actors/native/face_masks/hero.png.import", "project.binary"}


GOOD_PCK = ["assets/actors/native/face_masks/hero.png.import",
            ".godot/imported/hero.png-test.ctex",
            "assets/actors/native/face_masks/manifest.json",
            "assets/actors/native/equipment/textures/cloth.jpg.import",
            ".godot/imported/cloth.jpg-test.s3tc.ctex"]


@pytest.mark.parametrize("names,change,message", [
    (GOOD_PCK[2:], None, "hero.png: not in the PCK"),
    ([n for n in GOOD_PCK if not n.endswith("s3tc.ctex")], None,
     "cloth.jpg: its imported product is not in the PCK"),
    (GOOD_PCK + ["assets/actors/native/races/hero.glb.import"], None,
     "races/hero.glb.import: an actor file that ships loose or nowhere is in the PCK"),
    (GOOD_PCK + ["assets/actors/native/equipment/cloth_0.png.import"], None,
     "cloth_0.png.import: an actor file that ships loose or nowhere is in the PCK"),
    (GOOD_PCK, ("remove", "assets/actors/native/races/hero.glb"), "not staged loose"),
    (GOOD_PCK, ("add", "assets/actors/native/equipment/textures/cloth.jpg"), "also staged loose"),
    (GOOD_PCK, ("add", "assets/actors/native/race_textures/hero/body_basecolor.png"),
     "a dropped image was staged loose"),
])
def test_actor_pack_check_holds_each_file_to_one_place(tmp_path, monkeypatch,
                                                       names, change, message):
    build = tmp_path / "build"
    app = tmp_path / "app"
    _track(monkeypatch, _write_tree(build))
    _import_mask(build)
    _import_cloth_texture(build)
    _write_pck(app / "RabbitLands.pck", GOOD_PCK)
    package.stage_loose_client_files(build, app)
    package.check_actor_pack(build, app)

    _write_pck(app / "RabbitLands.pck", names)
    if change and change[0] == "remove":
        (app / change[1]).unlink()
    elif change:
        (app / change[1]).parent.mkdir(parents=True, exist_ok=True)
        (app / change[1]).write_bytes(b"x")
    with pytest.raises(package.PackageError, match=message):
        package.check_actor_pack(build, app)


def test_glTF_texture_check_takes_an_import_in_the_pck_or_a_loose_file(tmp_path):
    app = tmp_path / "app"
    for relative, images in (("assets/actors/native/equipment/cloth.glb", ["textures/cloth.jpg"]),
                             ("assets/actors/native/equipment/variants/hero/cloth.glb",
                              ["../../textures/cloth.jpg"]),
                             ("assets/actors/native/shared/library.glb", ["hair%20base.png"])):
        (app / relative).parent.mkdir(parents=True, exist_ok=True)
        (app / relative).write_bytes(_glb(images))
    (app / "assets/actors/native/shared/hair base.png").write_bytes(b"x")
    _write_pck(app / "RabbitLands.pck", ["assets/actors/native/equipment/textures/cloth.jpg.import"])

    package.check_glb_textures(app)

    _write_pck(app / "RabbitLands.pck", [])
    with pytest.raises(package.PackageError, match="2 glTF textures missing"):
        package.check_glb_textures(app)


# --- the real tree ---------------------------------------------------------------
# GLTFDocument reads a URI texture it got from ResourceLoader back with
# get_image(), a RenderingServer call that, from a worker thread, waits for the
# main thread. A package imports the equipment glTFs' URI textures, so no glTF
# that names one may be parsed on a worker the main thread joins: the animation
# libraries main.gd prewarms (NativeAnimationImporter joins that worker) and
# the visual scenes a map preloader builds (GlbSceneCache.prepare) must not.

def _repo_tracked(*specs: str) -> list[str]:
    try:
        return package.tracked(package.REPO, *specs)
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git cannot list this checkout: {error}")


def _imported_folder(target: str) -> bool:
    if not target.startswith(package.ACTOR_ROOT + "/"):
        return False
    return PurePosixPath(target).relative_to(package.ACTOR_ROOT).parts[0] in package.IMPORTED_URI_TEXTURE_FOLDERS


def test_prewarmed_animation_libraries_name_no_imported_texture():
    models = json.loads((package.CLIENT / "data/actors/models.json").read_text(encoding="utf-8"))
    libraries = sorted({str(model["animationLibrary"]) for model in models["models"].values()
                        if isinstance(model, dict) and model.get("animationLibrary")})
    assert libraries
    absent, imported = [], []
    for library in libraries:
        relative = "godot-client/" + library.removeprefix("res://")
        if not (package.REPO / relative).is_file():
            absent.append(relative)
            continue
        for uri in package.gltf_image_uris(package.REPO / relative):
            target = package._resolve(relative, uri)
            if _imported_folder(target):
                imported.append(f"{relative} -> {target}")
    if absent:
        pytest.skip(f"{len(absent)} animation libraries are not checked out, e.g. {absent[0]}")
    assert imported == []


def _values_named(value, key: str):
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key == key:
                yield child
            yield from _values_named(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _values_named(child, key)


def test_worker_preloaded_visual_scenes_name_no_actor_file():
    files = [p for p in _repo_tracked("eloria-assets", "godot-client")
             if p.lower().endswith(".json") and not p.startswith(package.UNSHIPPED_CLIENT_DIRS)]
    assert files
    actor = []
    for relative in files:
        path = package.REPO / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b'"visualScenes"' not in data:
            continue
        for scenes in _values_named(json.loads(data.decode("utf-8-sig")), "visualScenes"):
            for scene in scenes if isinstance(scenes, list) else [scenes]:
                if package.ACTOR_PATH_IN_TEXT.search(str(scene).replace("\\", "/")):
                    actor.append(f"{relative}: {scene}")
    assert actor == []
