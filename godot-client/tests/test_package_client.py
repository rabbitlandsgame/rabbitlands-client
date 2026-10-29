#!/usr/bin/env python3
"""What the packager ships of a continent-v2 map the server serves (tools/package_client.py served_v2_packages,
stage_eloria_assets, check_served_packages; serve plan CV11).

    python3 godot-client/tests/test_package_client.py -v

A served isle's client package ships: its territory world.json, every chunk, and the shared images the chunks name.
What only the server reads does not: collision.bin and served-grid.escg.gz (the server vendors the grid from the
repository, never from an installed client), nor the territory folder around the package (the editor's stub, the
server content tables). A preview row still ships nothing, and a legacy package keeps everything it shipped before.
The cases stage a small fixture tree for real, with git's file list stood in for by the fixture's own files.

The RL head (the High Human head) ships as develop's native actors do: its head, hair and beard GLBs
(native/rl_heads) loose only, never imported; its maps (native/rl_head_textures, LOADED_IMAGE_FOLDERS) in the PCK
only, each imported VRAM-compressed with mipmaps by the settings committed beside it; its lab (prototypes/rl_heads)
and its tests and evidence scripts nowhere. RLHeadShipping holds a fixture tree to that, and CommittedRLHead the
real tree's committed import settings.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))

import package_client as packager  # noqa: E402

V2 = "eloria-assets/maps/continent-v2"
SHARED = V2 + "/_continent_v2/shared-assets/ground.png"
SHARED_SHA = "a" * 64


def write(root: Path, relative: str, data) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def chunk_manifest(collision=None) -> dict:
    return {"asset": {"glb": "world.glb", "units": "meters"},
            "collision": collision if collision is not None else {"nodeNames": []},
            "externalResources": {"../../../../_continent_v2/shared-assets/ground.png": SHARED_SHA}}


def build_fixture(root: Path) -> None:
    """A checkout with one served isle, one preview isle and one legacy package, and their registry rows."""
    isle = V2 + "/isle"
    write(root, isle + "/world.json", {"asset": {"glb": "world.glb"}, "server": {"origin": [1023, 993]}})
    write(root, isle + "/content/spawns.json", {"rows": []})
    write(root, isle + "/source/prepare_meshy_kit.py", b"# editor-side source\n")
    write(root, isle + "/client/world.json", {
        "asset": {"id": "isle", "glb": "world.glb", "units": "meters"},
        "collision": {"nodeNames": [], "binary": "collision.bin", "format": "EWCG-v2",
                      "servedGrid": {"binary": "served-grid.escg.gz", "format": "ESCG-v2", "sha256": "b" * 64}},
        "externalResources": {"../../_continent_v2/shared-assets/ground.png": SHARED_SHA},
        "streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local", "chunks": [
            {"id": "00_00", "manifest": "chunks/00_00/world.json"},
            {"id": "00_01", "manifest": "chunks/00_01/world.json"}]}})
    write(root, isle + "/client/publication.json", {"schema": 1})
    write(root, isle + "/client/collision.bin", b"EWCG" + bytes(64))
    write(root, isle + "/client/served-grid.escg.gz", b"\x1f\x8b" + bytes(32))
    for chunk in ("00_00", "00_01"):
        write(root, f"{isle}/client/chunks/{chunk}/world.json", chunk_manifest())
        write(root, f"{isle}/client/chunks/{chunk}/world.glb", b"glTF" + bytes(16))
    write(root, SHARED, b"\x89PNG" + bytes(16))
    write(root, V2 + "/_continent_v2/crossings.json", {"schema": 1})
    draft = V2 + "/draft"
    write(root, draft + "/client/world.json", {"asset": {"glb": "world.glb"}})
    write(root, draft + "/client/world.glb", b"glTF" + bytes(16))
    legacy = "eloria-assets/maps/legacy"
    write(root, legacy + "/world.json", {"asset": {"glb": "world.glb"},
                                          "collision": {"binary": "collision.bin", "nodeNames": []}})
    write(root, legacy + "/world.glb", b"glTF" + bytes(16))
    write(root, legacy + "/collision.bin", b"EWCG" + bytes(16))
    write(root, packager.REGISTRY_FILE, {"schemaVersion": 1, "maps": {
        "isle": {"manifest": f"res://../{isle}/client/world.json", "status": "continent-v2-served"},
        "draft": {"manifest": f"res://../{draft}/client/world.json", "status": "continent-v2-client-preview"},
        "legacy": {"manifest": f"res://../{legacy}/world.json", "status": "production-geometry-materials-population"}}})


class ServedIsle(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="package-client-tree-"))
        self.stage = Path(tempfile.mkdtemp(prefix="package-client-stage-"))
        build_fixture(self.root)
        self._tracked = packager.tracked
        self._log = packager.log
        root = self.root

        def tracked(tree, *pathspecs):
            files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
            return [p for p in files if any(p == s or p.startswith(s.rstrip("/") + "/") for s in pathspecs)]
        packager.tracked = tracked
        packager.log = lambda message: None

    def tearDown(self):
        packager.tracked = self._tracked
        packager.log = self._log
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.stage, ignore_errors=True)

    def stage_assets(self):
        """main()'s order: the preview rows leave the build tree's registry, then the stage is made."""
        previews = packager.drop_preview_maps(self.root)
        served = packager.read_served_v2_packages(self.root)
        warnings = packager.stage_eloria_assets(self.root, self.stage, previews, served)
        staged = sorted(p.relative_to(self.stage).as_posix() for p in self.stage.rglob("*") if p.is_file())
        return served, staged, warnings

    def test_the_served_rows_are_found_with_their_territory_folders(self):
        registry = json.loads((self.root / packager.REGISTRY_FILE).read_text(encoding="utf-8"))
        self.assertEqual(packager.served_v2_packages(registry), [(V2 + "/isle/client", V2 + "/isle")])
        self.assertEqual(packager.preview_map_folders(registry), [V2 + "/draft"])

    def test_the_served_grid_and_collision_bin_never_ship(self):
        served, staged, _ = self.stage_assets()
        for name in packager.SERVER_ONLY_FILES:
            self.assertNotIn(f"{V2}/isle/client/{name}", staged)
        packager.check_served_packages(self.stage, served)

    def test_the_isle_ships_its_package_chunks_and_shared_images(self):
        _, staged, _ = self.stage_assets()
        for relative in ("isle/client/world.json", "isle/client/chunks/00_00/world.json",
                         "isle/client/chunks/00_00/world.glb", "isle/client/chunks/00_01/world.glb"):
            self.assertIn(f"{V2}/{relative}", staged)
        self.assertIn(SHARED, staged)
        # the territory manifest streams chunks: its master world.glb is named but never existed, and is no refusal
        self.assertNotIn(f"{V2}/isle/client/world.glb", staged)

    def add_road_field(self):
        chunk = V2 + "/isle/client/chunks/00_00"
        field = chunk + "/triangle-ids.bin.zst"
        image = V2 + "/_continent_v2/shared-assets/road-only.png"
        write(self.root, field, b"compact field bytes")
        write(self.root, image, b"road style image bytes")
        metadata = chunk + "/roads.json"
        write(self.root, metadata, {"schema": "rabbitlands-road-terrain-blend-v1", "resources": {
            "triangle-ids.bin.zst": hashlib.sha256((self.root / field).read_bytes()).hexdigest(),
            "../../../../_continent_v2/shared-assets/road-only.png": hashlib.sha256((self.root / image).read_bytes()).hexdigest()}})
        path = self.root / chunk / "world.json"
        data = json.loads(path.read_text())
        data["roadGround"] = {"metadata": "roads.json", "sha256": hashlib.sha256((self.root / metadata).read_bytes()).hexdigest()}
        write(self.root, chunk + "/world.json", data)
        return field, image, metadata

    def test_road_fields_and_style_only_images_ship_with_verified_bytes(self):
        files = self.add_road_field()
        _, staged, _ = self.stage_assets()
        for relative in files:
            self.assertIn(relative, staged)
            self.assertEqual((self.root / relative).read_bytes(), (self.stage / relative).read_bytes())

    def test_road_field_absent_from_commit_is_refused(self):
        field, _, _ = self.add_road_field()
        original = packager.tracked
        packager.tracked = lambda root, *paths: [p for p in original(root, *paths) if p != field]
        with self.assertRaisesRegex(packager.PackageError, "roadGround.*not in the commit"):
            self.stage_assets()

    def test_mutated_road_input_is_refused(self):
        _, image, _ = self.add_road_field()
        (self.root / image).write_bytes(b"unpublished replacement")
        with self.assertRaisesRegex(packager.PackageError, "runtime resource changed"):
            self.stage_assets()

    def test_staged_road_field_bytes_are_checked_after_copy(self):
        field, _, _ = self.add_road_field()
        original = packager.copy_file
        def copy(source, destination):
            size = original(source, destination)
            if destination == self.stage / field:
                destination.write_bytes(b"corrupted staged bytes")
            return size
        packager.copy_file = copy
        try:
            with self.assertRaisesRegex(packager.PackageError, "staged .*runtime resource changed"):
                self.stage_assets()
        finally:
            packager.copy_file = original

    def test_the_territory_folder_around_the_package_stays_home(self):
        _, staged, _ = self.stage_assets()
        for relative in ("isle/world.json", "isle/content/spawns.json", "isle/source/prepare_meshy_kit.py",
                         "_continent_v2/crossings.json"):
            self.assertNotIn(f"{V2}/{relative}", staged)

    def test_a_preview_ships_nothing_and_a_legacy_package_keeps_its_collision(self):
        _, staged, _ = self.stage_assets()
        self.assertFalse([p for p in staged if p.startswith(V2 + "/draft/")])
        self.assertIn("eloria-assets/maps/legacy/collision.bin", staged)
        self.assertIn("eloria-assets/maps/legacy/world.glb", staged)

    def test_a_chunk_glb_missing_from_the_commit_is_refused(self):
        (self.root / V2 / "isle/client/chunks/00_01/world.glb").unlink()
        with self.assertRaisesRegex(packager.PackageError, "chunks/00_01/world.glb is not in the commit"):
            self.stage_assets()

    def test_the_check_refuses_a_staged_served_grid(self):
        served, _, _ = self.stage_assets()
        write(self.stage, V2 + "/isle/client/served-grid.escg.gz", b"\x1f\x8b")
        with self.assertRaisesRegex(packager.PackageError, "served-grid.escg.gz is read by the server only"):
            packager.check_served_packages(self.stage, served)

    def test_the_check_refuses_a_chunk_that_names_a_collision_binary(self):
        served, _, _ = self.stage_assets()
        write(self.stage, V2 + "/isle/client/chunks/00_01/world.json",
              chunk_manifest({"nodeNames": [], "binary": "collision.bin"}))
        with self.assertRaisesRegex(packager.PackageError, "chunks/00_01/world.json names a collision binary"):
            packager.check_served_packages(self.stage, served)

    def test_the_check_refuses_a_missing_chunk_and_a_stray_territory_file(self):
        served, _, _ = self.stage_assets()
        shutil.rmtree(self.stage / V2 / "isle/client/chunks/00_00")
        write(self.stage, V2 + "/isle/content/spawns.json", {"rows": []})
        with self.assertRaises(packager.PackageError) as caught:
            packager.check_served_packages(self.stage, served)
        self.assertIn("chunk 00_00 (chunks/00_00/world.json) is not staged", str(caught.exception))
        self.assertIn("isle/content/spawns.json lies outside the client package", str(caught.exception))


NATIVE = packager.ACTOR_ROOT
RL_GLBS = [f"{NATIVE}/rl_heads/rl_head_male.glb", f"{NATIVE}/rl_heads/rl_head_female.glb",
           f"{NATIVE}/rl_heads/hair/rowan_shag.glb", f"{NATIVE}/rl_heads/beards/goatee.glb"]
RL_MAPS = [f"{NATIVE}/rl_head_textures/head_male_albedo.png", f"{NATIVE}/rl_head_textures/head_male_brows.png",
           f"{NATIVE}/rl_head_textures/hair_clump.png"]
RL_MANIFEST = f"{NATIVE}/rl_head_textures/manifest.json"
RL_LAB = ["prototypes/rl_heads/rl_head_lab.gd", "prototypes/rl_heads/rl_head_lab.tscn",
          "prototypes/rl_heads/rl_head_stage.gd"]
RL_TOOLING = ["tests/test_rl_head.gd", "tests/integration/rl_head_renders.gd", "tests/rl_head_gain_probe.gd"]
RL_RUNTIME = ["src/actors/rl_head/rl_head_library.gd", "src/actors/rl_head/rl_skin.gdshader",
              "data/actors/rl_head_wire_defaults.json", "data/actors/rl_head_presets.json",
              "prototypes/creature_dissolve_preview.gd"]
RACE = f"{NATIVE}/races/luminous_male.glb"
MASK = f"{NATIVE}/face_masks/luminous_male.png"


def glb(images: list[str] | None = None) -> bytes:
    """A GLB holding only a JSON chunk (naming these images by URI)."""
    document = json.dumps({"asset": {"version": "2.0"},
                           **({"images": [{"uri": uri} for uri in images]} if images else {})}).encode("utf-8")
    document += b" " * (-len(document) % 4)
    return (b"glTF" + struct.pack("<II", 2, 20 + len(document))
            + struct.pack("<II", len(document), 0x4E4F534A) + document)


def write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4.7 (format 4) PCK directory listing empty files with these names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
    reserved = b"\0" * 64
    directory = struct.pack("<I", len(names))
    for name in names:
        raw = name.encode("utf-8")
        raw += b"\0" * (-len(raw) % 4)
        directory += struct.pack("<I", len(raw)) + raw + struct.pack("<QQ", 0, 0) + b"\0" * 16 + struct.pack("<I", 0)
    path.write_bytes(header + struct.pack("<QQ", 0, len(header) + 16 + len(reserved)) + reserved + directory)


def import_texture(root: Path, relative: str, product: str, params: dict) -> str:
    """An imported texture: its .import remap, as Godot writes it, and the product it names."""
    project = root / "godot-client"
    (project / ".godot/imported").mkdir(parents=True, exist_ok=True)
    (project / ".godot/imported" / product).write_bytes(b"GST2 imported texture")
    (root / (relative + ".import")).write_text(
        '[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n'
        f'path="res://.godot/imported/{product}"\n\n[deps]\n\n'
        f'dest_files=["res://.godot/imported/{product}"]\n\n[params]\n\n'
        + "".join(f"{k}={v}\n" for k, v in params.items()), encoding="utf-8")
    return f".godot/imported/{product}"


VRAM = dict(packager.URI_TEXTURE_IMPORT_PARAMS)


class RLHeadShipping(unittest.TestCase):
    """A tree with the RL head beside one race, its face mask and the RL lab and tooling."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="package-client-rl-"))
        self.app = Path(tempfile.mkdtemp(prefix="package-client-rl-app-"))
        root = self.root
        for relative in RL_GLBS + [RACE]:
            write(root, relative, glb())
        for relative in RL_MAPS + [MASK]:
            write(root, relative, b"\x89PNG" + bytes(16))
        write(root, RL_MANIFEST, {"male": {"albedo": "head_male_albedo.png"}})
        write(root, "godot-client/data/actors/models.json", {"models": {"luminous_male": {
            "scene": "res://" + RACE.removeprefix("godot-client/"),
            "faceAppearance": {"mask": "res://" + MASK.removeprefix("godot-client/")}}}})
        write(root, "godot-client/data/actors/equipment.json", {"models": {}})
        # RLHeadLibrary names both folders only as prefixes it joins at runtime.
        write(root, "godot-client/src/actors/rl_head/rl_head_library.gd",
              b'const ROOT := "res://assets/actors/native/rl_heads/"\n'
              b'const TEXTURE_DIR := "res://assets/actors/native/rl_head_textures/"\n')
        for relative in RL_LAB + RL_TOOLING:
            write(root, "godot-client/" + relative, b"extends SceneTree\n")
        self._tracked = packager.tracked
        self._log = packager.log

        def tracked(tree, *pathspecs):
            files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                           if p.is_file() and p.suffix != ".import" and ".godot" not in p.parts)
            return [p for p in files if any(p == s or p.startswith(s.rstrip("/") + "/") for s in pathspecs)]
        packager.tracked = tracked
        packager.log = lambda message: None

    def tearDown(self):
        packager.tracked = self._tracked
        packager.log = self._log
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.app, ignore_errors=True)

    def import_all(self, params: dict | None = None, product: str = "bptc") -> None:
        for relative in RL_MAPS:
            name = Path(relative).name
            import_texture(self.root, relative, f"{name}-rl.{product}.ctex", params or VRAM)
        import_texture(self.root, MASK, "luminous_male.png-mask.ctex", {})

    def pck(self) -> list[str]:
        names = ["project.binary", MASK.removeprefix("godot-client/") + ".import",
                 ".godot/imported/luminous_male.png-mask.ctex", RL_MANIFEST.removeprefix("godot-client/")]
        for relative in RL_MAPS:
            name = Path(relative).name
            names += [relative.removeprefix("godot-client/") + ".import", f".godot/imported/{name}-rl.bptc.ctex"]
        return names

    def test_the_glbs_ship_loose_and_the_maps_in_the_pck(self):
        shipping = packager.actor_shipping(self.root)
        self.assertEqual(shipping["folder_textures"], set(RL_MAPS))
        self.assertLessEqual(set(RL_MAPS) | {RL_MANIFEST}, shipping["pck"])
        self.assertLessEqual(set(RL_GLBS), shipping["loose"])
        self.assertFalse(set(RL_GLBS) & shipping["pck"])
        self.assertIn(f"{NATIVE}/rl_head_textures", shipping["pck_folders"])
        self.assertIn(f"{NATIVE}/rl_heads", shipping["loose_folders"])
        self.assertFalse({p for p in shipping["dropped"] if "/rl_head" in p})

    def test_the_build_tree_never_imports_the_glbs(self):
        (self.root / ".git").mkdir()
        self.import_all()
        git, packager.git = packager.git, lambda *_args, **_kwargs: ""
        try:
            project = packager.prepare_build_tree(self.root, "a" * 40)
        finally:
            packager.git = git
        self.assertTrue((self.root / NATIVE / "rl_heads/.gdignore").is_file())
        self.assertFalse((self.root / NATIVE / "rl_head_textures/.gdignore").exists())
        for relative in RL_MAPS:  # the committed settings are left as they are
            self.assertEqual(packager._import_settings(self.root / (relative + ".import"))[1]["compress/mode"], "2")
        packager.check_actor_imports(project)

    def test_the_import_check_wants_vram_mipmapped_maps(self):
        self.import_all()
        packager.check_actor_imports(self.root / "godot-client")
        for key, value in (("compress/mode", "0"), ("mipmaps/generate", "false")):
            with self.subTest(key=key):
                self.import_all({**VRAM, key: value})
                with self.assertRaisesRegex(packager.PackageError, rf"head_male_brows.png: .*{key}={value}"):
                    packager.check_actor_imports(self.root / "godot-client")
        self.import_all(product="etc2")
        with self.assertRaisesRegex(packager.PackageError, "no VRAM-compressed import product"):
            packager.check_actor_imports(self.root / "godot-client")
        self.import_all()
        (self.root / (RL_MAPS[0] + ".import")).unlink()
        with self.assertRaisesRegex(packager.PackageError, "head_male_albedo.png: missing .import remap"):
            packager.check_actor_imports(self.root / "godot-client")

    def test_the_pack_check_refuses_an_imported_glb(self):
        # An editor import of a loose-only actor would reach the PCK beside its loose copy.
        self.import_all()
        write_pck(self.app / "RabbitLands.pck", self.pck() + [
            RL_GLBS[0].removeprefix("godot-client/") + ".import"])
        packager.stage_loose_client_files(self.root, self.app)
        with self.assertRaisesRegex(packager.PackageError, "rl_head_male.glb.import: an actor file that ships loose"):
            packager.check_actor_pack(self.root, self.app)

    def test_each_rl_file_is_staged_once(self):
        self.import_all()
        write_pck(self.app / "RabbitLands.pck", self.pck())
        packager.stage_loose_client_files(self.root, self.app)
        packager.check_actor_pack(self.root, self.app)
        staged = sorted(p.relative_to(self.app).as_posix() for p in self.app.rglob("*")
                        if p.is_file() and "rl_head" in p.as_posix())
        self.assertEqual(staged, sorted(p.removeprefix("godot-client/") for p in RL_GLBS))
        write_pck(self.app / "RabbitLands.pck", [n for n in self.pck() if not n.endswith("brows.png-rl.bptc.ctex")])
        with self.assertRaisesRegex(packager.PackageError, "head_male_brows.png: its imported product is not in the PCK"):
            packager.check_actor_pack(self.root, self.app)

    def test_the_lab_and_the_rl_tooling_are_never_exported(self):
        filters = [line.split("=", 1)[1].strip('"').split(",")
                   for line in packager.EXPORT_PRESETS.splitlines() if line.startswith("exclude_filter=")]
        self.assertTrue(filters)
        for preset in filters:
            def excluded(path):
                return any(fnmatch.fnmatchcase(path.lower(), f.lower()) for f in preset)
            for path in RL_LAB + RL_TOOLING:
                self.assertTrue(excluded(path), path)
            for path in RL_RUNTIME:
                self.assertFalse(excluded(path), path)


class CommittedRLHead(unittest.TestCase):
    """The real tree: every RL head map carries committed import settings that ship it VRAM-compressed with mipmaps."""

    FOLDER = TESTS.parent / "assets/actors/native/rl_head_textures"
    # Independent masks packed into RGBA: BPTC (BC7, the size of DXT5 without its cross-channel bleed) and no
    # alpha-border fix, which rewrites the RGB masks wherever A < 20 within 4 px of an alpha edge.
    PACKED = re.compile(r"^(head_(male|female)_(features|features2|brows)|eye)\.png$")

    def test_every_map_is_imported_vram_compressed_with_mipmaps(self):
        maps = sorted(self.FOLDER.glob("*.png"))
        self.assertGreaterEqual(len(maps), 13)
        for png in maps:
            with self.subTest(map=png.name):
                importer, params = packager._import_settings(png.with_name(png.name + ".import"))
                self.assertEqual(importer, "texture")
                self.assertEqual(params["compress/mode"], "2")
                self.assertEqual(params["mipmaps/generate"], "true")
                self.assertEqual(params["detect_3d/compress_to"], "0")
                packed = bool(self.PACKED.match(png.name))
                self.assertEqual(params["compress/high_quality"], "true" if packed else "false")
                self.assertEqual(params["process/fix_alpha_border"], "false" if packed else "true")
                self.assertEqual(params["process/size_limit"], "1024" if "features2" in png.name else "0")
                text = png.with_name(png.name + ".import").read_text(encoding="utf-8")
                self.assertRegex(text, r'(?m)^uid="uid://[0-9a-z]+"$')
                self.assertRegex(text, r"(?m)^dest_files=\[\"res://\.godot/imported/[^\"]+\.(bptc|s3tc)\.ctex\"\]$")

    def test_the_glbs_sit_in_a_loose_folder_beside_no_map(self):
        glbs = sorted((TESTS.parent / "assets/actors/native/rl_heads").rglob("*.glb"))
        self.assertGreaterEqual(len(glbs), 8)
        self.assertFalse([p for p in (TESTS.parent / "assets/actors/native/rl_heads").rglob("*")
                          if p.is_file() and p.suffix.lower() in packager.IMAGE_SUFFIXES + packager.PLAIN_EXPORT_SUFFIXES])
        self.assertFalse((TESTS.parent / "assets/actors/rl_heads").exists())


class CommittedRegistry(unittest.TestCase):
    def test_every_partition_section_is_served_with_a_package_and_none_is_preview(self):
        checkout = TESTS.parents[1]
        registry = json.loads((checkout / packager.REGISTRY_FILE).read_text(encoding="utf-8"))
        catalog = json.loads((TESTS.parent / "world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))
        def res_path(path):
            self.assertTrue(path.startswith("res://"))
            return (TESTS.parent / path.removeprefix("res://")).resolve()
        partition = json.loads(res_path(catalog["partitionSpecPath"]).read_text(encoding="utf-8"))
        ids = sorted(section.get("mapId", section["id"]) for section in partition["sections"])
        self.assertTrue(ids)
        self.assertEqual(sorted(entry["id"] for entry in catalog["entries"]), ids)
        self.assertEqual([package for package, _ in packager.served_v2_packages(registry)],
                         [f"{V2}/{map_id}/client" for map_id in ids])
        for entry in catalog["entries"]:
            row = registry["maps"][entry["id"]]
            self.assertEqual(row["status"], "continent-v2-served")
            self.assertEqual(row["manifest"], entry["publishedManifestPath"])
            package = res_path(entry["publishedManifestPath"])
            self.assertTrue(package.is_file(), f"missing served package: {package}")
            manifest = json.loads(package.read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset"]["id"], entry["id"])
            self.assertTrue(manifest.get("streamingChunks"), f"no served chunks: {entry['id']}")
        for retired in catalog.get("retiredMapIds", []):
            self.assertNotIn(retired, registry["maps"])
        self.assertEqual(packager.preview_map_folders(registry), [])


if __name__ == "__main__":
    unittest.main()
