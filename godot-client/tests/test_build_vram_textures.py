#!/usr/bin/env python3
"""The package-time sidecar tool (tools/build_vram_textures.py) and the rule
that the client never compresses a texture itself.

    python3 godot-client/tests/test_build_vram_textures.py -v

The recipe, schema and committed-fixture cases are pure Python. The encode
cases run the tool for real against a copy of tests/fixtures/vram, which needs
the Godot 4.7.2 editor binary (ELORIA_GODOT, the checkout's copy, or `godot`
on PATH) plus numpy and Pillow; without them they skip and say why.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CLIENT = TESTS.parent
TOOL = CLIENT / "tools" / "build_vram_textures.py"
FIXTURE = TESTS / "fixtures" / "vram"
SIDECARS = FIXTURE / "shared-assets" / "vram"
sys.path.insert(0, str(CLIENT / "tools"))

import build_vram_textures as tool  # noqa: E402


def _godot() -> Path | None:
    try:
        return tool.find_godot(None)
    except tool.BuildError:
        return None


def _imaging() -> str:
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as error:
        return str(error)
    return ""


GODOT = _godot()
SKIP_ENCODE = ("no Godot 4.7.2 editor binary (set ELORIA_GODOT)" if GODOT is None
               else (f"numpy/Pillow missing: {_imaging()}" if _imaging() else ""))
FIXTURE_SHAS = set(json.loads((FIXTURE / "world.json").read_text(encoding="utf-8"))["externalResources"].values())


def _two_pools(maps: Path) -> tuple[Path, Path]:
    """A maps tree with two packages, each beside its own copy of the fixture's images: a_first is the fixture,
    b_second (sorted after it) samples the same images in the stale-roles package's materials. Returns the two
    image directories, resolved."""
    first, second = maps / "a_first", maps / "b_second"
    shutil.copytree(FIXTURE, first, ignore=shutil.ignore_patterns("vram", "*.py", "stale_roles.*"))
    shutil.copytree(FIXTURE / "shared-assets", second / "shared-assets", ignore=shutil.ignore_patterns("vram"))
    shutil.copyfile(FIXTURE / "stale_roles.glb", second / "world.glb")
    manifest = json.loads((FIXTURE / "stale_roles.json").read_text(encoding="utf-8"))
    manifest["asset"]["glb"] = "world.glb"
    (second / "world.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return (first / "shared-assets").resolve(), (second / "shared-assets").resolve()


def _run_tool(maps: Path, cache: Path, *extra: str) -> tuple[int, dict, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if GODOT is not None:
        env["ELORIA_GODOT"] = str(GODOT)
    result = subprocess.run([sys.executable, str(TOOL), "--maps", str(maps), "--cache", str(cache),
                             "--procs", "2", *extra], capture_output=True, text=True, env=env, timeout=900)
    text = result.stdout
    start = text.find("\n{")
    summary = json.loads(text[start:]) if result.returncode == 0 and start >= 0 else {}
    return result.returncode, summary, text + result.stderr


class GodotLocator(unittest.TestCase):
    def test_worktree_can_find_primary_non_console_editor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worktree = root / "worktrees" / "texture-preparation"
            client = worktree / "godot-client"
            client.mkdir(parents=True)
            primary = root / "rabbitlands-client" / "godot-client"
            primary.mkdir(parents=True)
            editor = primary / tool.GODOT_EXE.replace("_console", "")
            editor.touch()
            with mock.patch.object(tool, "CLIENT", client), mock.patch.object(tool, "REPO", worktree), \
                    mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(tool.shutil, "which", return_value=None):
                self.assertEqual(tool.find_godot(None), editor)


class ScopedInventory(unittest.TestCase):
    @staticmethod
    def _glb(path: Path, image: Path, role="base"):
        uri = os.path.relpath(image, path.parent).replace(os.sep, "/")
        slot = {"base": "baseColorTexture", "normal": "normalTexture"}[role]
        material = {"pbrMetallicRoughness": {slot: {"index": 0}}} if role == "base" else {slot: {"index": 0}}
        document = {"images": [{"uri": uri}], "textures": [{"source": 0}], "materials": [material]}
        payload = json.dumps(document).encode()
        payload += b" " * (-len(payload) % 4)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(struct.pack("<4sIII4s", b"glTF", 2, len(payload) + 20, len(payload), b"JSON") + payload)
        return uri

    def _tree(self, root: Path):
        maps = root / "maps"
        images = maps / "_shared" / "images"
        images.mkdir(parents=True)
        first, second, unrelated = [images / f"{i}.png" for i in range(3)]
        for number, image in enumerate((first, second, unrelated)):
            image.write_bytes(bytes([number]))
        territory = maps / "territory"
        leaf = territory / "chunks" / "00_00" / "world.json"
        glb = leaf.with_suffix(".glb")
        uri = self._glb(glb, first)
        prototype = maps / "_shared" / "meshes" / "prop.glb"
        prototype_uri = self._glb(prototype, second, "normal")
        (prototype.parent / "index.json").write_text(json.dumps({"prototypes": {"prop": {"images": {
            prototype_uri: hashlib.sha256(second.read_bytes()).hexdigest()}}}}))
        leaf.write_text(json.dumps({"asset": {"glb": "world.glb"},
                                   "externalResources": {uri: hashlib.sha256(first.read_bytes()).hexdigest()},
                                   "externalMeshes": {os.path.relpath(prototype, glb.parent):
                                                       hashlib.sha256(prototype.read_bytes()).hexdigest()}}))
        manifest = territory / "world.json"
        manifest.write_text(json.dumps({"asset": {"glb": "review.glb"},
                                       "streamingChunks": {"chunks": [{"manifest": "chunks/00_00/world.json"}]}}))
        (territory / "review.glb").write_bytes(b"preview must never be read")
        self._glb(maps / "_shared" / "meshes" / "unused.glb", unrelated)
        unrelated_glb = maps / "unrelated" / "world.glb"
        unrelated_uri = self._glb(unrelated_glb, unrelated)
        unrelated_glb.with_suffix(".json").write_text(json.dumps({
            "asset": {"glb": "world.glb"},
            "externalResources": {unrelated_uri: hashlib.sha256(unrelated.read_bytes()).hexdigest()}}))
        return maps, manifest, leaf, first, second

    def test_declared_leaves_and_only_reachable_prototypes(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps, manifest, _, first, second = self._tree(Path(temporary))
            found = tool.inventory([maps], manifests=[manifest])
            by_path = {record["path"]: record for record in found.values()}
            self.assertEqual(set(by_path), {first.resolve(), second.resolve()})
            self.assertEqual(by_path[second.resolve()]["roles"], {("normal", "OPAQUE")})

    def test_dependencies_cannot_escape_maps_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps, manifest, leaf, _, _ = self._tree(Path(temporary))
            data = json.loads(leaf.read_text())
            data["externalMeshes"] = {"../../../../../outside.glb": "digest"}
            leaf.write_text(json.dumps(data))
            with self.assertRaisesRegex(tool.BuildError, "outside every --maps root"):
                tool.inventory([maps], manifests=[manifest])

    def test_stale_prototype_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps, manifest, _, _, _ = self._tree(Path(temporary))
            prototype = maps / "_shared" / "meshes" / "prop.glb"
            prototype.write_bytes(prototype.read_bytes() + b" changed")
            with self.assertRaisesRegex(tool.BuildError, "does not hash to its declared SHA256"):
                tool.inventory([maps], manifests=[manifest])

    def test_stale_prototype_image_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps, manifest, _, _, _ = self._tree(Path(temporary))
            path = maps / "_shared" / "meshes" / "index.json"
            data = json.loads(path.read_text())
            images = data["prototypes"]["prop"]["images"]
            images[next(iter(images))] = "0" * 64
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(tool.BuildError, "does not hash to its declared SHA256"):
                tool.inventory([maps], manifests=[manifest])

    def test_changed_prototype_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps, manifest, _, _, image = self._tree(Path(temporary))
            image.write_bytes(b"changed source image")
            with self.assertRaisesRegex(tool.BuildError, "does not hash to its declared SHA256"):
                tool.inventory([maps], manifests=[manifest])

    def test_changed_manifest_image_fails_before_any_encode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maps, manifest, _, image, _ = self._tree(root)
            image.write_bytes(b"changed source image")
            with mock.patch.object(tool, "godot_version", return_value="4.7.2.test"), \
                    mock.patch.object(tool, "ensure_ignored"), mock.patch.object(tool, "run_encoders") as encoder:
                with self.assertRaisesRegex(tool.BuildError, "does not hash to its manifest sha"):
                    tool.build([maps], root / "stage", root / "cache", root / "unused-godot", 1,
                               manifests=[manifest])
                encoder.assert_not_called()

    def test_nested_stage_link_cannot_redirect_output_into_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maps, stage = root / "maps", root / "stage"
            images = maps / "images"
            images.mkdir(parents=True)
            stage.mkdir()
            try:
                (stage / "images").symlink_to(images, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaisesRegex(tool.BuildError, "resolved sidecar output escapes"):
                tool.sidecar_target([maps], images, stage)

    def test_scoped_build_cannot_replace_a_source_pool_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            maps = Path(temporary) / "maps"
            for output in (None, maps, maps / "nested-stage"):
                with self.subTest(output=output), mock.patch.object(tool, "godot_version") as version:
                    with self.assertRaisesRegex(tool.BuildError, "separate|outside the source"):
                        tool.build([maps], output, Path(temporary) / "cache", Path("unused"), 1,
                                   manifests=[maps / "world.json"])
                    version.assert_not_called()

    def test_current_landfall_group_resolves_all_seventeen_territories(self):
        manifests = tool.scope_group_manifests(["landfall_continent"])
        self.assertEqual(len(manifests), 17)
        self.assertTrue(all("continent-v2" in path.parts and path.is_file() for path in manifests))
        self.assertEqual(tool.scope_group_manifests([]), [])
        with self.assertRaisesRegex(tool.BuildError, "unknown or empty"):
            tool.scope_group_manifests(["not_a_group"])


BASE_IMAGE = FIXTURE / "shared-assets" / "90c51de41c0f4fffd8a6c225f67472eb77d262a183e2fcae827383d3e10d32f4.jpg"
NORMAL_IMAGE = FIXTURE / "shared-assets" / "5168b5c2d5238b41c0b8b9626b2987775d00fe27f953b84aa9bb8bc7f11349ab.png"


def _scenery_glb(path: Path, images: list[tuple[bytes, str]], materials: list[dict]) -> None:
    """A world-object GLB that embeds `images` ((bytes, mimeType)) in its BIN chunk; no geometry (the tool reads the
    materials and the images only)."""
    binary, views, image_list, textures = bytearray(), [], [], []
    for payload, mime in images:
        binary += b"\0" * (-len(binary) % 4)
        image_list.append({"bufferView": len(views), "mimeType": mime})
        textures.append({"source": len(textures)})
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)})
        binary += payload
    binary += b"\0" * (-len(binary) % 4)
    document = {"asset": {"version": "2.0"}, "materials": materials, "textures": textures, "images": image_list,
                "bufferViews": views, "buffers": [{"byteLength": len(binary)}]}
    payload = json.dumps(document).encode()
    payload += b" " * (-len(payload) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 28 + len(payload) + len(binary))
                     + struct.pack("<I", len(payload)) + b"JSON" + payload
                     + struct.pack("<I", len(binary)) + b"BIN\0" + bytes(binary))


def _scenery_tree(root: Path) -> tuple[Path, Path, Path, Path]:
    """<root>/client/assets/world/props/{crate,barrel}.glb (the fixture's base colour and normal map embedded; the
    barrel samples the same base colour bytes) and a config naming them. Returns (client, config, crate, barrel)."""
    client = root / "client"
    props = client / "assets" / "world" / "props"
    base, normal = BASE_IMAGE.read_bytes(), NORMAL_IMAGE.read_bytes()
    _scenery_glb(props / "crate.glb", [(base, "image/jpeg"), (normal, "image/png")],
                 [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}, "normalTexture": {"index": 1}}])
    _scenery_glb(props / "barrel.glb", [(base, "image/jpeg")],
                 [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}])
    config = client / "data" / "scenery.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"assets": {"crate": "res://assets/world/props/crate.glb",
                                             "barrel": "res://assets/world/props/barrel.glb"}}), encoding="utf-8")
    return client, config, props / "crate.glb", props / "barrel.glb"


class Scenery(unittest.TestCase):
    """--scenery-config: the embedded images of world-object GLBs, keyed by the GLB's own directory."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-scenery-test-")).resolve()
        self.client, self.config, self.crate, self.barrel = _scenery_tree(self.scratch)
        self.patches = [mock.patch.object(tool, "CLIENT", self.client),
                        mock.patch.object(tool, "SCENERY_ROOT", self.client / "assets" / "world")]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        shutil.rmtree(self.scratch, ignore_errors=True)

    def _config(self, assets: dict) -> Path:
        path = self.scratch / "bad.json"
        path.write_text(json.dumps({"assets": assets}), encoding="utf-8")
        return path

    def test_config_names_glbs_below_assets_world(self):
        self.assertEqual(tool.scenery_glbs([self.config, self.config]), [self.crate.resolve(), self.barrel.resolve()])
        for value in ("res://src/props/crate.glb", "res://assets/world/../../data/scenery.json",
                      "res://assets/world/props/missing.glb", "assets/world/props/crate.glb",
                      "res://assets/world/props/crate.png"):
            with self.subTest(value=value), self.assertRaises(tool.BuildError):
                tool.scenery_glbs([self._config({"x": value})])
        with self.assertRaises(tool.BuildError):
            tool.scenery_glbs([self._config({})])

    def test_inventory_keys_embedded_images_by_the_glb_directory(self):
        maps = self.scratch / "maps"
        maps.mkdir()
        extract = self.scratch / "cache" / tool.EMBEDDED_DIR
        found = tool.inventory([maps], scenery=tool.scenery_glbs([self.config]), extract_dir=extract)
        base_sha = hashlib.sha256(BASE_IMAGE.read_bytes()).hexdigest()
        normal_sha = hashlib.sha256(NORMAL_IMAGE.read_bytes()).hexdigest()
        props = self.crate.parent.resolve()
        self.assertEqual(set(found), {(props, base_sha), (props, normal_sha)})
        self.assertEqual(found[(props, base_sha)]["roles"], {("base", "OPAQUE")})
        self.assertEqual(found[(props, base_sha)]["maps"], {"scenery:crate.glb", "scenery:barrel.glb"})
        self.assertEqual(found[(props, normal_sha)]["roles"], {("normal", "OPAQUE")})
        for (_, sha), record in found.items():
            self.assertEqual(record["path"].parent, extract)
            self.assertEqual(hashlib.sha256(record["path"].read_bytes()).hexdigest(), sha)
        self.assertEqual(found[(props, base_sha)]["path"].suffix, ".jpg")
        self.assertEqual(found[(props, normal_sha)]["path"].suffix, ".png")

    def test_targets_beside_the_glbs_or_mirrored_below_the_out_root(self):
        props = self.crate.parent
        self.assertEqual(tool.scenery_target(props, None), props / "vram")
        out = self.scratch / "stage" / "world"
        self.assertEqual(tool.scenery_target(props, out), out.resolve() / "props" / "vram")
        with self.assertRaises(tool.BuildError):
            tool.scenery_target(self.scratch / "elsewhere", out)

    def test_a_scoped_run_never_writes_a_partial_scenery_index_in_place(self):
        maps = self.scratch / "maps"
        maps.mkdir()
        for scenery_out in (None, self.client / "assets" / "world" / "stage"):
            with self.subTest(scenery_out=scenery_out), self.assertRaises(tool.BuildError) as raised:
                tool.build([maps], self.scratch / "stage", self.scratch / "cache", Path("no-godot"), 1,
                           manifests=[maps / "world.json"], scenery_configs=[self.config],
                           scenery_out_root=scenery_out)
            self.assertIn("--scenery-out-root", str(raised.exception))


class NoRuntimeCompression(unittest.TestCase):
    """The shipped export template has no BC encoder: Image.compress returns
    ERR_UNAVAILABLE there, so a runtime call would pass every editor-binary
    test and do nothing in the game. Compression belongs to the package tool."""

    @staticmethod
    def _offenders(relative: str, source: str) -> list[str]:
        pattern = re.compile(r"\.compress\(|compress_from_channels\(")
        offenders = []
        producer, typed_bytes = False, False
        for number, line in enumerate(source.splitlines(), 1):
            code = line.split("#", 1)[0]
            if code.startswith(("func ", "static func ")):
                producer = code.startswith("static func write_packed(")
                typed_bytes = False
            if producer and code.strip() == "var raw := var_to_bytes(ordered)":
                typed_bytes = True
            # var_to_bytes infers PackedByteArray, so this exact maintenance
            # statement compresses serialized CPU vectors with ZSTD. It is
            # unrelated to the Image BC encoder unavailable in export builds.
            allowed = (relative == "src/world/map_collision_cache.gd" and producer and typed_bytes
                       and code.strip() == "bytes.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))")
            if pattern.search(code) and not allowed:
                offenders.append(f"{relative}:{number}")
        return offenders

    def test_client_scripts_never_compress(self):
        offenders = []
        for path in sorted((CLIENT / "src").rglob("*.gd")):
            offenders.extend(self._offenders(path.relative_to(CLIENT).as_posix(),
                                            path.read_text(encoding="utf-8", errors="replace")))
        self.assertEqual(offenders, [], "client code calls an Image compressor at runtime")

    def test_only_the_typed_maintenance_byte_compressor_is_allowed(self):
        relative = "src/world/map_collision_cache.gd"
        prefix = "static func write_packed():\n\tvar raw := var_to_bytes(ordered)\n"
        allowed = "\tbytes.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))\n"
        self.assertEqual(self._offenders(relative, prefix + allowed), [])
        forbidden = ["\timage.compress(Image.COMPRESS_BPTC)\n",
                     "\timage.compress_from_channels(Image.COMPRESS_S3TC)\n",
                     "\traw.compress(Image.COMPRESS_BPTC)\n"]
        for call in forbidden:
            with self.subTest(call=call):
                self.assertTrue(self._offenders(relative, prefix + allowed + call))
        self.assertTrue(self._offenders("src/world/another_file.gd", prefix + allowed))
        self.assertTrue(self._offenders(relative, "static func write_packed():\n" + allowed))
        self.assertTrue(self._offenders(relative, prefix + "static func another_function():\n" + allowed))


class Recipes(unittest.TestCase):
    def _recipe(self, roles, alpha=False):
        record = {"roles": set(roles), "path": FIXTURE / "world.json"}
        original = tool.alpha_used
        tool.alpha_used = lambda _path: alpha
        try:
            return tool.recipe_for(record)
        finally:
            tool.alpha_used = original

    def test_recipe_per_role(self):
        self.assertEqual(self._recipe({("base", "OPAQUE")}), ("base", ""))
        self.assertEqual(self._recipe({("emissive", "OPAQUE"), ("base", "OPAQUE")}), ("base", ""))
        self.assertEqual(self._recipe({("base", "MASK")}, alpha=True), ("base_alpha", ""))
        self.assertEqual(self._recipe({("base", "BLEND")}, alpha=True), ("base_alpha", ""))
        self.assertEqual(self._recipe({("base", "MASK")}, alpha=False), ("base", ""),
                         "a cutout whose alpha is all opaque needs no alpha channel")
        self.assertEqual(self._recipe({("base", "OPAQUE")}, alpha=True), ("base", ""),
                         "an opaque material never samples alpha")
        self.assertEqual(self._recipe({("orm", "OPAQUE"), ("occlusion", "OPAQUE")}), ("orm", ""))
        self.assertEqual(self._recipe({("normal", "MASK")}), ("normal", ""))

    def test_role_names_are_the_clients(self):
        # vram_textures.gd SLOT_ROLES / image_roles name them the same way.
        self.assertEqual(tool.role_names({("base", "OPAQUE"), ("emissive", "MASK")}), ["base", "emissive"])
        self.assertEqual(tool.role_names({("base", "MASK"), ("base", "BLEND")}), ["base_cutout"])
        self.assertEqual(tool.role_names({("base", "OPAQUE"), ("base", "MASK")}), ["base", "base_cutout"])
        self.assertEqual(tool.role_names({("orm", "OPAQUE"), ("occlusion", "MASK")}), ["occlusion", "orm"])

    def test_cutoffs_come_from_the_materials(self):
        document = {"textures": [{"source": 0}, {"source": 1}, {"source": 2}],
                    "materials": [
                        {"alphaMode": "MASK", "alphaCutoff": 0.45, "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
                        {"alphaMode": "MASK", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
                        {"alphaMode": "BLEND", "pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
                        {"pbrMetallicRoughness": {"baseColorTexture": {"index": 2}}},
                        {"alphaMode": "MASK", "alphaCutoff": 0.3, "normalTexture": {"index": 2}}]}
        self.assertEqual(tool.image_cutoffs(document), {0: {0.45, 0.5}, 1: {0.5}},
                         "each MASK material's cutoff (glTF default 0.5), 0.5 for BLEND, none for opaque or a normal map")

    def test_mip_floors(self):
        floors = tool.FLOORS
        self.assertEqual(tool.verdict("base", {"psnr": 40.0, "psnr_mips": [40.0, 35.0, 31.0, 30.5, 20.0]}, floors), "",
                         "mip 4 is reported, not gated")
        self.assertEqual(tool.verdict("base", {"psnr": 40.0, "psnr_mips": [40.0, 35.0, 29.9, 31.0]}, floors),
                         "quality: psnr 29.9 < 30.0 at mip 2")
        self.assertEqual(tool.verdict("base", {"psnr": 40.0, "psnr_mips": [40.0, 35.0, 20.0, 20.0], "size": [64, 64]},
                                      floors), "", "a 64 px image's 16 and 8 px mips are reported, not gated")
        self.assertEqual(tool.verdict("base", {"psnr": 40.0, "psnr_mips": [40.0, 29.0, 40.0], "size": [64, 64]},
                                      floors), "quality: psnr 29.0 < 30.0 at mip 1")
        flips = {"psnr": 45.0, "psnr_mips": [45.0] * 5, "alpha_flip_mip0": 0.0, "alpha_flip_mip2": 0.0,
                 "alpha_flip_max": [0.0, 0.001, 0.004, 0.009, 0.0166]}
        self.assertEqual(tool.verdict("base_alpha", flips, floors), "")
        flips["alpha_flip_max"][4] = 0.021
        self.assertEqual(tool.verdict("base_alpha", flips, floors), "quality: alpha flips 0.021 > 0.02 at mip 4")
        normal = {"mean_deg": 0.8, "p99_deg": 2.0, "mean_deg_mips": [0.8, 1.2, 1.6], "p99_deg_mips": [2.0, 3.0, 3.0]}
        self.assertEqual(tool.verdict("normal", normal, floors), "quality: normal error 1.6 / 3.0 deg at mip 2")
        orm = {"psnr_rgb": [40.0, 40.0, 40.0], "psnr_rgb_mips": [[40.0] * 3, [35.0, 27.5, 40.0], [40.0] * 3]}
        self.assertEqual(tool.verdict("orm", orm, floors), "quality: channel psnr 27.5 < 28.0 at mip 1")

    def test_conflicts_and_unused_are_excluded(self):
        self.assertEqual(self._recipe({("base", "OPAQUE"), ("normal", "OPAQUE")}),
                         (None, "role_conflict: base+normal"))
        self.assertEqual(self._recipe({("orm", "OPAQUE"), ("base", "OPAQUE")}),
                         (None, "role_conflict: base+orm"))
        self.assertEqual(self._recipe(set()), (None, "no_material_role"))

    def test_fixture_inventory_names_every_role(self):
        found = tool.inventory([FIXTURE])
        self.assertEqual({sha for _, sha in found}, FIXTURE_SHAS)
        self.assertEqual({directory for directory, _ in found}, {(FIXTURE / "shared-assets").resolve()})
        roles = {sha: {role for role, _ in record["roles"]} for (_, sha), record in found.items()}
        self.assertIn({"orm", "occlusion"}, roles.values())
        self.assertIn({"base", "normal"}, roles.values())
        self.assertIn(set(), roles.values())

    def test_each_copy_of_a_shared_image_keeps_its_own_roles(self):
        # Two pools holding the same bytes, as continent-v2's and nymara-regions' do: the pool whose maps sort
        # first must not take the other's images, and each copy's roles come from the maps that name it.
        with tempfile.TemporaryDirectory() as tmp:
            maps = Path(tmp) / "maps"
            first, second = _two_pools(maps)
            found = tool.inventory([maps])
            directories = {directory for directory, _ in found}
            self.assertEqual(directories, {first, second})
            for directory in directories:
                self.assertEqual({sha for d, sha in found if d == directory}, FIXTURE_SHAS, directory)
            alone = tool.inventory([maps / "b_second"])
            self.assertEqual({sha: (r["roles"], r["cutoffs"]) for (d, sha), r in found.items() if d == second},
                             {sha: (r["roles"], r["cutoffs"]) for (_, sha), r in alone.items()},
                             "a pool's records are the same with or without the other pool in the tree")
            fixture = {sha: r["roles"] for (_, sha), r in tool.inventory([FIXTURE]).items()}
            self.assertEqual({sha: r["roles"] for (d, sha), r in found.items() if d == first}, fixture)
            # The stale-roles materials: the opaque JPEG base is a MASK cutout there, the ORM map also colour.
            committed = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))["images"]
            by_recipe = {entry["recipe"]: sha for sha, entry in committed.items()}
            second_roles = {sha: tool.role_names(r["roles"]) for (d, sha), r in found.items() if d == second}
            first_roles = {sha: tool.role_names(r["roles"]) for (d, sha), r in found.items() if d == first}
            self.assertEqual((first_roles[by_recipe["base"]], second_roles[by_recipe["base"]]),
                             (["base"], ["base", "base_cutout"]))
            self.assertEqual((first_roles[by_recipe["orm"]], second_roles[by_recipe["orm"]]),
                             (["occlusion", "orm"], ["base", "occlusion", "orm"]))


class CommittedFixture(unittest.TestCase):
    """The sidecars committed beside the fixture are what the client tests load."""

    def setUp(self):
        self.index = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))

    def test_index_schema(self):
        self.assertEqual(self.index["schema"], tool.SCHEMA)
        self.assertEqual(self.index["recipeVersion"], tool.RECIPE_VERSION)
        self.assertEqual(set(self.index["images"]) | set(self.index["excluded"]), FIXTURE_SHAS)
        self.assertEqual({entry["recipe"] for entry in self.index["images"].values()},
                         {"base", "base_alpha", "orm", "normal"})
        for entry in self.index["images"].values():
            self.assertEqual(set(entry), {"file", "recipe", "format", "width", "height", "mipmaps",
                                          "gpuBytes", "rawBytes", "fileBytes", "sha256", "roles"})
            self.assertEqual(entry["format"], tool.FORMAT_OF[entry["recipe"]])
            self.assertEqual(entry["mipmaps"], 6, "64 px carries its whole chain")
        # The roles each encode was chosen for, as the fixture's materials use them.
        self.assertEqual({e["recipe"]: e["roles"] for e in self.index["images"].values()},
                         {"base": ["base"], "base_alpha": ["base_cutout"], "normal": ["normal"],
                          "orm": ["occlusion", "orm"]})

    def test_exclusions_have_reasons(self):
        reasons = sorted(self.index["excluded"].values())
        self.assertEqual(reasons, ["no_material_role", "role_conflict: base+normal", "size_not_multiple_of_4"])

    def test_sidecar_header_and_hash(self):
        for sha, entry in self.index["images"].items():
            data = (SIDECARS / entry["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], entry["file"])
            self.assertEqual(len(data), entry["fileBytes"])
            magic, raw, flags, reserved = tool.HEADER.unpack_from(data)
            self.assertEqual((magic, raw, flags, reserved), (b"EVT1", entry["rawBytes"], tool.FLAG_ZSTD, 0))
            self.assertEqual(data[16:20], b"\x28\xb5\x2f\xfd", "the body is one zstd frame")
            self.assertTrue(entry["file"].startswith(sha))


@unittest.skipIf(SKIP_ENCODE, SKIP_ENCODE or "")
class Build(unittest.TestCase):
    """Runs the tool against a scratch copy of the fixture."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="vram-build-test-"))
        cls.maps = cls.scratch / "maps"
        shutil.copytree(FIXTURE, cls.maps, ignore=shutil.ignore_patterns("vram", "*.py"))
        cls.cache = cls.scratch / "cache"
        cls.code, cls.summary, cls.output = _run_tool(cls.maps, cls.cache)
        cls.out = cls.maps / "shared-assets" / "vram"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def _index(self, directory: Path | None = None) -> dict:
        return json.loads(((directory or self.out) / "index.json").read_text(encoding="utf-8"))

    def test_build_matches_the_committed_index(self):
        self.assertEqual(self.code, 0, self.output[-2000:])
        built = self._index()
        committed = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(built["excluded"], committed["excluded"])
        fields = ("file", "recipe", "format", "width", "height", "mipmaps", "gpuBytes", "rawBytes", "roles")
        self.assertEqual({sha: {k: e[k] for k in fields} for sha, e in built["images"].items()},
                         {sha: {k: e[k] for k in fields} for sha, e in committed["images"].items()})
        self.assertEqual(sorted(p.name for p in self.out.glob("*.evt")),
                         sorted(e["file"] for e in built["images"].values()))

    def test_bc1_and_bc5_are_byte_deterministic(self):
        second = self.scratch / "second"
        shutil.copytree(self.maps, second, ignore=shutil.ignore_patterns("vram"))
        code, _, output = _run_tool(second, self.scratch / "cache-second")
        self.assertEqual(code, 0, output[-2000:])
        again = self._index(second / "shared-assets" / "vram")
        for sha, entry in self._index()["images"].items():
            if entry["format"] in ("bc1", "bc5"):
                self.assertEqual(again["images"][sha]["sha256"], entry["sha256"], entry["file"])

    def test_cache_reuse_and_prune(self):
        maps = self.scratch / "prune"
        shutil.copytree(self.maps, maps, ignore=shutil.ignore_patterns("vram"))
        cache = self.scratch / "cache-prune"
        code, first, output = _run_tool(maps, cache)
        self.assertEqual(code, 0, output[-2000:])
        code, again, output = _run_tool(maps, cache)
        self.assertEqual((code, again["encoded"], again["cached"]), (0, 0, first["encoded"]),
                         "a second run encodes nothing")
        # Drop the normal map from the package: its cache entry and its
        # sidecar go stale and are removed.
        manifest_path = maps / "world.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        normal = next(sha for sha, e in self._index()["images"].items() if e["recipe"] == "normal")
        manifest["externalResources"] = {u: s for u, s in manifest["externalResources"].items() if s != normal}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        code, pruned, output = _run_tool(maps, cache)
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual(pruned["pruned"], 1)
        self.assertFalse(any(cache.glob(normal + ".*")))
        directory = next(iter(pruned["directories"].values()))
        self.assertEqual(directory["staleRemoved"], 1)
        self.assertNotIn(normal, self._index(maps / "shared-assets" / "vram")["images"])

    def test_report_has_every_measured_mip(self):
        self.assertEqual(self.code, 0, self.output[-2000:])
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        by_recipe = {e["recipe"]: e for e in report.values()}
        self.assertEqual(len(by_recipe["base"]["psnr_mips"]), tool.MEASURED_MIPS["base"] + 1)
        self.assertEqual(len(by_recipe["normal"]["p99_deg_mips"]), tool.MEASURED_MIPS["normal"] + 1)
        self.assertEqual(len(by_recipe["orm"]["psnr_rgb_mips"]), tool.MEASURED_MIPS["orm"] + 1)
        cutout = by_recipe["base_alpha"]
        self.assertEqual(cutout["cutoffs"], [0.5], "the fixture's cutout material cuts at 0.5")
        self.assertEqual(len(cutout["alpha_flips"]["0.5"]), tool.MEASURED_MIPS["base_alpha"] + 1)
        self.assertTrue(all(e["qualityVersion"] == tool.QUALITY_VERSION for e in report.values()))

    @unittest.skipIf(tool._zstd() is None, "zstandard missing: stale measurements re-encode instead")
    def test_stale_measurements_are_taken_again_without_encoding(self):
        maps = self.scratch / "remeasure"
        shutil.copytree(self.maps, maps, ignore=shutil.ignore_patterns("vram"))
        cache = self.scratch / "cache-remeasure"
        shutil.copytree(self.cache, cache)
        metas = sorted(cache.glob("*.json"))
        stale = json.loads(metas[0].read_text(encoding="utf-8"))
        stale["quality"].pop("qualityVersion", None)
        metas[0].write_text(json.dumps(stale), encoding="utf-8")
        code, summary, output = _run_tool(maps, cache, "--no-prune")
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual((summary["encoded"], summary["remeasured"]), (0, 1), "measured again, not encoded")
        self.assertEqual(json.loads(metas[0].read_text(encoding="utf-8"))["quality"]["qualityVersion"],
                         tool.QUALITY_VERSION)

    def test_quality_floor_excludes(self):
        maps = self.scratch / "floors"
        shutil.copytree(self.maps, maps, ignore=shutil.ignore_patterns("vram"))
        # Same cache: the verdict is re-taken from the recorded numbers.
        code, _, output = _run_tool(maps, self.cache, "--no-prune", "--floors",
                                    json.dumps({"base_psnr": 99.0, "normal_mean_deg": 0.0}))
        self.assertEqual(code, 0, output[-2000:])
        out = maps / "shared-assets" / "vram"
        index = self._index(out)
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        failed = {sha for sha, e in report.items() if e["recipe"] in ("base", "base_alpha", "normal")}
        self.assertEqual(len(failed), 3)
        self.assertTrue(all(index["excluded"][sha].startswith("quality:") for sha in failed),
                        {sha: index["excluded"].get(sha) for sha in failed})
        self.assertEqual({e["recipe"] for e in index["images"].values()}, {"orm"})

    def test_orm_below_the_bc1_floor_gets_a_bc7_second_chance(self):
        maps = self.scratch / "orm"
        shutil.copytree(self.maps, maps, ignore=shutil.ignore_patterns("vram"))
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        orm = next(sha for sha, e in report.items() if e["recipe"] == "orm")
        bc1_floor = min(report[orm]["psnr_rgb"]) + 0.5  # just above what BC1 kept
        code, summary, output = _run_tool(maps, self.cache, "--no-prune", "--floors",
                                          json.dumps({"orm_psnr": bc1_floor}))
        self.assertEqual(code, 0, output[-2000:])
        index = self._index(maps / "shared-assets" / "vram")
        entry = index["images"].get(orm, {})
        self.assertEqual((entry.get("recipe"), entry.get("format")), ("orm_bc7", "bc7"),
                         index["excluded"].get(orm))
        code, _, output = _run_tool(maps, self.cache, "--no-prune", "--floors", json.dumps({"orm_psnr": 99.0}))
        self.assertEqual(code, 0, output[-2000:])
        reason = self._index(maps / "shared-assets" / "vram")["excluded"].get(orm, "")
        self.assertTrue(reason.startswith("quality: channel psnr"), reason)

    def test_each_pool_gets_its_own_index(self):
        # The whole-tree run package_client makes, over two pools that share images: each directory's index names
        # every image its own maps use, an in-place run deletes no sidecar of the other pool, and the second pool's
        # index is byte for byte the one a run without the first pool writes (MapSceneCache keys hash it).
        self.assertEqual(self.code, 0, self.output[-2000:])
        tree = self.scratch / "pools"
        first, second = _two_pools(tree / "maps")
        cache = tree / "cache"
        shutil.copytree(self.cache, cache)
        code, summary, output = _run_tool(tree / "maps", cache, "--no-prune")
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual(summary["encoded"], 0, "the second copy of an image reuses the first copy's encode")
        self.assertIn("distinct encodes", output)
        indexes = {d: self._index(d / "vram") for d in (first, second)}
        for directory, index in indexes.items():
            self.assertEqual(set(index["images"]) | set(index["excluded"]), FIXTURE_SHAS, directory)
            self.assertEqual(sorted(p.name for p in (directory / "vram").glob("*.evt")),
                             sorted(e["file"] for e in index["images"].values()))
        committed = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))
        fields = ("file", "recipe", "format", "width", "height", "mipmaps", "gpuBytes", "rawBytes", "roles")
        self.assertEqual({sha: {k: e[k] for k in fields} for sha, e in indexes[first]["images"].items()},
                         {sha: {k: e[k] for k in fields} for sha, e in committed["images"].items()})
        by_recipe = {entry["recipe"]: sha for sha, entry in committed["images"].items()}
        self.assertEqual(indexes[second]["excluded"].get(by_recipe["orm"]), "role_conflict: base+occlusion+orm")
        self.assertEqual(indexes[second]["images"][by_recipe["base"]]["roles"], ["base", "base_cutout"])
        # The same pool alone, from the same cache.
        alone = tree / "alone"
        shutil.copytree(tree / "maps" / "b_second", alone / "b_second", ignore=shutil.ignore_patterns("vram"))
        code, _, output = _run_tool(alone, cache, "--no-prune")
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual((second / "vram" / "index.json").read_bytes(),
                         (alone / "b_second" / "shared-assets" / "vram" / "index.json").read_bytes())

    def test_psnr_median_counts_each_encode_once(self):
        # Two pools holding the same images under the same materials are one set of encodes: the set-level median
        # gate and the reported basePsnrMedian are the single pool's, whatever else is in the tree.
        self.assertEqual(self.code, 0, self.output[-2000:])
        self.assertIn("basePsnrEncodes", self.summary)
        tree = self.scratch / "twins"
        for name in ("a_first", "b_twin"):
            shutil.copytree(FIXTURE, tree / "maps" / name, ignore=shutil.ignore_patterns("vram", "*.py"))
        cache = tree / "cache"
        shutil.copytree(self.cache, cache)
        code, summary, output = _run_tool(tree / "maps", cache, "--no-prune")
        self.assertEqual(code, 0, output[-2000:])
        self.assertEqual(summary["encoded"], 0)
        self.assertEqual(summary["basePsnrEncodes"], self.summary["basePsnrEncodes"])
        self.assertEqual(summary["basePsnrMedian"], self.summary["basePsnrMedian"])

    def test_scenery_sidecars_go_in_the_glb_directory_s_vram(self):
        # Embedded images of world-object GLBs, planned from the GLBs' materials and keyed by the bytes' sha: the
        # same encodes as the fixture pool's (same bytes, same recipes), so nothing is encoded again.
        self.assertEqual(self.code, 0, self.output[-2000:])
        tree = self.scratch / "scenery"
        client, config, crate, _ = _scenery_tree(tree)
        maps = tree / "maps"
        maps.mkdir()
        cache = tree / "cache"
        shutil.copytree(self.cache, cache)
        stage = tree / "stage"
        with mock.patch.object(tool, "CLIENT", client), \
                mock.patch.object(tool, "SCENERY_ROOT", client / "assets" / "world"):
            summary = tool.build([maps], None, cache, GODOT, 2, prune=False, scenery_configs=[config],
                                 scenery_out_root=stage)
        self.assertEqual(summary["encoded"], 0)
        index = json.loads((stage / "props" / "vram" / "index.json").read_text(encoding="utf-8"))
        committed = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))
        base_sha = hashlib.sha256(BASE_IMAGE.read_bytes()).hexdigest()
        normal_sha = hashlib.sha256(NORMAL_IMAGE.read_bytes()).hexdigest()
        self.assertEqual(index["excluded"], {})
        self.assertEqual({sha: (e["recipe"], e["format"], e["roles"]) for sha, e in index["images"].items()},
                         {base_sha: ("base", "bc7", ["base"]), normal_sha: ("normal", "bc5", ["normal"])})
        for sha, entry in index["images"].items():
            self.assertEqual(entry["width"], committed["images"][sha]["width"])
            self.assertEqual(hashlib.sha256((stage / "props" / "vram" / entry["file"]).read_bytes()).hexdigest(),
                             entry["sha256"])
        self.assertFalse((crate.parent / "vram").exists(), "--scenery-out-root leaves the GLB directory alone")

    def test_unskip_keeps_one_map_s_images_in_a_skipped_pool(self):
        # The package skips the shared image pool but still ships one map's sidecars there (--unskip-map).
        self.assertEqual(self.code, 0, self.output[-2000:])
        tree = self.scratch / "unskip"
        first, second = _two_pools(tree / "maps")
        cache = tree / "cache"
        shutil.copytree(self.cache, cache)
        code, summary, output = _run_tool(tree / "maps", cache, "--no-prune", "--skip-dir", "shared-assets",
                                          "--unskip-map", "a_first")
        self.assertEqual(code, 0, output[-2000:])
        kept = self._index(first / "vram")
        skipped = self._index(second / "vram")
        committed = json.loads((SIDECARS / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(kept["images"]), set(committed["images"]))
        self.assertEqual(set(skipped["images"]), set())
        self.assertEqual(set(skipped["excluded"].values()), {"excluded_by_caller"})

    def test_cache_inside_a_worktree_must_be_ignored(self):
        repo = self.scratch / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        code, _, output = _run_tool(self.maps, repo / "cache", "--no-prune")
        self.assertEqual(code, 1)
        self.assertIn("not ignored", output)


if __name__ == "__main__":
    unittest.main()
