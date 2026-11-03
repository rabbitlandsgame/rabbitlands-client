#!/usr/bin/env python3
"""The package-time sidecar tool (tools/build_vram_textures.py) and the rule
that the client never compresses a texture itself.

    python3 godot-client/tests/test_build_vram_textures.py -v

The recipe, schema and committed-fixture cases are pure Python. The encode
cases run the tool for real against a copy of tests/fixtures/vram, which needs
the Godot 4.7.2 editor binary (ELORIA_GODOT, the checkout's copy, or `godot`
on PATH) plus numpy and Pillow; without them they skip and say why.

The actor mode (--actor-dir) is planned against a copy of
tests/fixtures/actor_vram (a client-shaped actor tree, see its
make_fixture.py); ActorPlanning is pure Python, ActorBuild encodes it.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
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


# Encoder (Godot) and quality-check processes per tool run; VRAM_TEST_PROCS=1 keeps a run to one Godot process on a
# machine that limits headless Godot instances.
TEST_PROCS = max(1, int(os.environ.get("VRAM_TEST_PROCS", "2")))
MEASURE_PROCS = 2


def _run_tool(maps: Path, cache: Path, *extra: str) -> tuple[int, dict, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if GODOT is not None:
        env["ELORIA_GODOT"] = str(GODOT)
    result = subprocess.run([sys.executable, str(TOOL), "--maps", str(maps), "--cache", str(cache),
                             "--procs", str(TEST_PROCS), "--measure-procs", str(MEASURE_PROCS), *extra],
                            capture_output=True, text=True, env=env, timeout=900)
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

    # (file, producer function, its typed-bytes statement, its compress statement). var_to_bytes infers
    # PackedByteArray, so each exact statement compresses serialized data with ZSTD (map collision vectors, the
    # actor geometry sidecars of actor_geometry_format.gd). It is unrelated to the Image BC encoder unavailable in
    # export builds, and allowed only there.
    BYTE_COMPRESSORS = (
        ("src/world/map_collision_cache.gd", "static func write_packed(", "var raw := var_to_bytes(ordered)",
         "bytes.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))"),
        ("src/actors/actor_geometry_format.gd", "static func encode(", "var raw := var_to_bytes(sidecar)",
         "out.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))"),
    )

    @classmethod
    def _offenders(cls, relative: str, source: str) -> list[str]:
        pattern = re.compile(r"\.compress\(|compress_from_channels\(")
        offenders = []
        producer, typed_bytes = None, False
        for number, line in enumerate(source.splitlines(), 1):
            code = line.split("#", 1)[0]
            if code.startswith(("func ", "static func ")):
                producer = next((entry for entry in cls.BYTE_COMPRESSORS
                                 if entry[0] == relative and code.startswith(entry[1])), None)
                typed_bytes = False
            if producer and code.strip() == producer[2]:
                typed_bytes = True
            allowed = producer is not None and typed_bytes and code.strip() == producer[3]
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
        # The actor geometry sidecar encoder: its own statement, in its own function and file only.
        geometry = "src/actors/actor_geometry_format.gd"
        encoder = ("static func encode(sidecar: Dictionary) -> PackedByteArray:\n\tvar raw := var_to_bytes(sidecar)\n"
                   "\tout.append_array(raw.compress(FileAccess.COMPRESSION_ZSTD))\n")
        self.assertEqual(self._offenders(geometry, encoder), [])
        self.assertTrue(self._offenders(relative, encoder), "not in another file")
        self.assertTrue(self._offenders(geometry, encoder.replace("static func encode(", "static func other(")))
        self.assertTrue(self._offenders(geometry, encoder.replace("COMPRESSION_ZSTD", "COMPRESS_BPTC")))
        self.assertTrue(self._offenders(geometry, prefix + allowed), "nor the collision cache's statement")


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
            summary = tool.build([maps], None, cache, GODOT, TEST_PROCS, prune=False, scenery_configs=[config],
                                 scenery_out_root=stage, measure_procs=MEASURE_PROCS)
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


# --- actor mode (--actor-dir) ---------------------------------------------------------------------------------------

ACTOR_FIXTURE = TESTS / "fixtures" / "actor_vram"
ACTOR_RECORD = json.loads((ACTOR_FIXTURE / "fixture.json").read_text(encoding="utf-8"))
ACTOR_SHA = {key: entry["sha256"] for key, entry in ACTOR_RECORD["images"].items()}
# The five directories a package names (actor-textures plan, 3.2).
ACTOR_DIRS = ["creatures", "races", "hair", "mounts", "equipment"]
# What planning decides per GLB directory (relative to assets/actors/native): image key -> recipe, or "!" + reason.
ACTOR_PLAN = {
    "creatures": {"wolf_base": "base", "wolf_normal": "normal", "wolf_orm": "orm"},
    "creatures/basic_expansion": {"wolf_base": "base", "fox_cutout": "base_alpha"},
    "races": {"race_atlas": "base", "race_eyes": "base", "race_normal": "normal"},
    "hair": {"hair_base": "base"},
    "hair/fitted": {"hair_base": "base"},
    "mounts": {"mount_normal": "normal", "mount_odd": "base", "mount_conflict": "!role_conflict: base+normal",
               "mount_unused": "!no_material_role"},
    "equipment": {"sword_base": "base"},
}
# ... and what the index then holds: the encoder refuses the 62 px base, and the mount's normal map is over the map
# floors (p99 3.2 deg at mip 0) but within the plan's proposed actor floors (ACTOR_NORMAL_FLOORS).
ACTOR_INDEX = {directory: dict(plan) for directory, plan in ACTOR_PLAN.items()}
ACTOR_INDEX["mounts"]["mount_odd"] = "!size_not_multiple_of_4"
ACTOR_INDEX["mounts"]["mount_normal"] = "!quality"
# The actor-only normal floors the plan proposes (actor-textures open question 2), as a package would pass them.
ACTOR_NORMAL_FLOORS = {"normal_mean_deg": 1.5, "normal_p99_deg": 8.0, "normal_mean_deg_mips": 2.0,
                       "normal_p99_deg_mips": 10.0}
ACTOR_ROLES = {"base": ["base"], "base_alpha": ["base_cutout"], "normal": ["normal"], "orm": ["occlusion", "orm"]}
# The GLBs planned: none below rl_heads/, not the retired one.
ACTOR_GLBS = ["creatures/basic_expansion/fox.glb", "creatures/wolf.glb", "equipment/sword.glb",
              "hair/fitted/short_fitted.glb", "hair/short.glb", "mounts/rat.glb", "races/human_female.glb",
              "races/human_male.glb"]


def _actor_tree(root: Path) -> Path:
    """A scratch copy of the actor fixture (a client-shaped tree); returns its root."""
    shutil.copytree(ACTOR_FIXTURE, root, ignore=shutil.ignore_patterns("*.py", "vram"))
    return root


def _actor_patches(root: Path) -> list:
    return [mock.patch.object(tool, "ACTORS_ROOT", root / "assets" / "actors"),
            mock.patch.object(tool, "RETIRED_INDEX", root / "data" / "assets" / "retired_procedural_models.json")]


def _git(*args: str) -> None:
    subprocess.run(["git", "-c", "core.autocrlf=false", *args], check=True, capture_output=True)


class ActorPlanning(unittest.TestCase):
    """--actor-dir without encoding: which GLBs, which images, which directories, which outputs."""

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-plan-")).resolve()
        self.root = _actor_tree(self.scratch / "client")
        self.native = self.root / "assets" / "actors" / "native"
        self.patches = _actor_patches(self.root)
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        shutil.rmtree(self.scratch, ignore_errors=True)

    def _relative(self, paths) -> list[str]:
        return [path.relative_to(self.native).as_posix() for path in paths]

    def test_glbs_are_recursive_sorted_and_never_rl_heads_or_retired(self):
        self.assertEqual(self._relative(tool.actor_glbs(ACTOR_DIRS)), ACTOR_GLBS)
        self.assertEqual(self._relative(tool.actor_glbs(["creatures", "creatures/basic_expansion"])),
                         ["creatures/basic_expansion/fox.glb", "creatures/wolf.glb"], "each GLB once")
        self.assertEqual(self._relative(tool.actor_glbs(["hair/fitted"])), ["hair/fitted/short_fitted.glb"])
        # The retirement index is what keeps the retired creature out.
        tool.RETIRED_INDEX.unlink()
        self.assertIn("creatures/retired_beast.glb", self._relative(tool.actor_glbs(["creatures"])))

    def test_actor_dir_names_a_directory_below_native(self):
        for name in ("", ".", "/", "..", "../native/creatures", "creatures/../..", "rl_heads", "rl_heads/hair",
                     "missing", "creatures/wolf.glb", str(self.native / "creatures"), "C:/creatures"):
            with self.subTest(name=name), self.assertRaises(tool.BuildError):
                tool.actor_glbs([name])
        with self.assertRaisesRegex(tool.BuildError, "never planned"):
            tool.actor_glbs(["rl_heads"])

    def test_a_worktree_plans_only_its_tracked_glbs(self):
        # The package's build tree is the commit: an untracked GLB in a checkout is not shipped, so it is not planned.
        _git("init", "-q", str(self.root))
        _git("-C", str(self.root), "add", "assets/actors/native/creatures/wolf.glb")
        self.assertEqual(self._relative(tool.actor_glbs(["creatures"])), ["creatures/wolf.glb"])
        _git("-C", str(self.root), "add", "assets/actors/native/creatures/retired_beast.glb")
        self.assertEqual(self._relative(tool.actor_glbs(["creatures"])), ["creatures/wolf.glb"],
                         "tracked but retired")

    def test_retirement_index_must_be_readable(self):
        tool.RETIRED_INDEX.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(tool.BuildError, "retirement index"):
            tool.actor_glbs(["creatures"])
        tool.RETIRED_INDEX.write_text(json.dumps({"runtimePaths": "creatures/wolf.glb"}), encoding="utf-8")
        with self.assertRaisesRegex(tool.BuildError, "retirement index"):
            tool.actor_glbs(["creatures"])

    def _inventory(self, dirs=None):
        extract = self.scratch / "cache" / tool.EMBEDDED_DIR
        return tool.inventory([], actors=tool.actor_glbs(dirs or ACTOR_DIRS), extract_dir=extract), extract

    def test_images_are_keyed_by_their_glb_directory(self):
        found, extract = self._inventory()
        expected = {((self.native / directory).resolve(), ACTOR_SHA[key])
                    for directory, plan in ACTOR_PLAN.items() for key in plan}
        self.assertEqual(set(found), expected)
        for (_, sha), record in found.items():
            self.assertEqual(record["path"].parent, extract)
            self.assertEqual(hashlib.sha256(record["path"].read_bytes()).hexdigest(), sha)
        races = self.native.resolve() / "races"
        self.assertEqual(found[(races, ACTOR_SHA["race_atlas"])]["maps"],
                         {"actor:human_male.glb", "actor:human_female.glb"}, "one record for the shared atlas")
        fox = (self.native / "creatures" / "basic_expansion").resolve()
        self.assertEqual(found[(fox, ACTOR_SHA["fox_cutout"])]["roles"], {("base", "MASK")})
        self.assertEqual(found[(fox, ACTOR_SHA["fox_cutout"])]["cutoffs"], {0.45})
        self.assertEqual(found[(fox, ACTOR_SHA["wolf_base"])]["roles"], {("base", "OPAQUE")},
                         "the fox directory's roles come from the fox only")
        never = {ACTOR_SHA["rl_base"], ACTOR_SHA["retired_base"], *ACTOR_RECORD["uriImages"].values()}
        self.assertFalse(never & {sha for _, sha in found}, "rl_heads, retired and URI images are never planned")
        self.assertFalse(list(self.native.rglob("vram")), "planning writes nothing into the actor tree")

    def test_recipes_and_exclusions_per_directory(self):
        found, _ = self._inventory()
        planned: dict[str, dict] = {}
        for (directory, sha), record in found.items():
            policy = tool.delivery_policy(record, directory)
            key = next(k for k, v in ACTOR_SHA.items() if v == sha)
            relative = directory.relative_to(self.native.resolve()).as_posix()
            planned.setdefault(relative, {})[key] = policy["recipe"] or "!" + policy["reason"]
            if policy["recipe"]:
                self.assertEqual(policy["roles"], ACTOR_ROLES[policy["recipe"]], (relative, key))
        self.assertEqual(planned, ACTOR_PLAN)

    def test_an_rlcz_creature_is_planned_from_its_decoded_bytes(self):
        try:
            import creature_compression
            creature_compression._zstd()
        except Exception as error:  # noqa: BLE001 - the optional codec dependency
            self.skipTest(f"creature_compression unavailable: {error}")
        before, _ = self._inventory(["creatures"])
        wolf = self.native / "creatures" / "wolf.glb"
        wolf.write_bytes(creature_compression.encode(wolf.read_bytes()))
        self.assertEqual(wolf.read_bytes()[:4], b"RLCZ")
        after, _ = self._inventory(["creatures"])
        self.assertEqual({key: (r["roles"], r["cutoffs"], r["maps"]) for key, r in after.items()},
                         {key: (r["roles"], r["cutoffs"], r["maps"]) for key, r in before.items()})
        wolf.write_bytes(wolf.read_bytes()[:-1])
        with self.assertRaisesRegex(tool.BuildError, "cannot read actor GLB"):
            self._inventory(["creatures"])

    def test_targets_mirror_below_the_actor_root(self):
        fox = self.native / "creatures" / "basic_expansion"
        self.assertEqual(tool.actor_target(fox, None), fox / "vram")
        out = self.scratch / "stage" / "app" / "assets" / "actors"
        self.assertEqual(tool.actor_target(fox, out), out.resolve() / "native" / "creatures" / "basic_expansion" / "vram")
        with self.assertRaisesRegex(tool.BuildError, "outside"):
            tool.actor_target(self.scratch / "elsewhere", out)
        (out / "native").mkdir(parents=True)
        link = out / "native" / "creatures"
        try:
            link.symlink_to(self.native / "creatures", target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            try:  # Windows without the symlink privilege: a directory junction redirects the same way
                import _winapi
                _winapi.CreateJunction(str(self.native / "creatures"), str(link))
            except (ImportError, OSError):
                self.skipTest(f"directory symlinks and junctions unavailable: {error}")
        with self.assertRaisesRegex(tool.BuildError, "resolved sidecar output escapes"):
            tool.actor_target(fox, out)

    def test_an_actor_run_is_its_own_invocation(self):
        # So its --floors (an owner choice for actor normals) and its cache pruning never reach a map's sidecars.
        maps, cache, stage = self.scratch / "maps", self.scratch / "cache", self.scratch / "stage"
        maps.mkdir()
        conflicting = [dict(maps_roots=[maps]), dict(manifests=[maps / "world.json"]), dict(out_root=stage),
                       dict(scenery_configs=[maps / "scenery.json"]), dict(scenery_out_root=stage),
                       dict(skip=["_shared/images"]), dict(unskip=["landfall_town"])]
        for options in conflicting:
            arguments = dict(maps_roots=[], out_root=None, cache=cache, godot=Path("unused"), procs=1,
                             actor_dirs=["creatures"])
            arguments.update(options)
            with self.subTest(options=list(options)), mock.patch.object(tool, "godot_version") as version:
                with self.assertRaisesRegex(tool.BuildError, "run of its own"):
                    tool.build(**arguments)
                version.assert_not_called()
        for options, message in ((dict(actor_out_root=stage), "needs --actor-dir"),
                                 (dict(actor_dirs=["creatures"], link_output=True), "requires --actor-out-root"),
                                 (dict(actor_dirs=["creatures"], actor_out_root=self.native / "stage"), "outside"),
                                 (dict(actor_dirs=["creatures"], actor_out_root=cache / "out"), "outside")):
            with self.subTest(options=list(options)), mock.patch.object(tool, "godot_version") as version:
                with self.assertRaisesRegex(tool.BuildError, message):
                    tool.build([], None, cache, Path("unused"), 1, **options)
                version.assert_not_called()

    def test_sidecar_folders_in_a_worktree_must_be_ignored(self):
        _git("init", "-q", str(self.root))
        _git("-C", str(self.root), "add", "assets")
        target = tool.actor_target(self.native / "creatures", None)
        with self.assertRaisesRegex(tool.BuildError, "not ignored"):
            tool.ensure_output_ignored(target)
        cache = self.scratch / "cache"
        with mock.patch.object(tool, "godot_version") as version, mock.patch.object(tool, "run_encoders") as encoder:
            with self.assertRaisesRegex(tool.BuildError, "not ignored"):
                tool.build([], None, cache, Path("unused"), 1, actor_dirs=["creatures"])
            version.assert_not_called()
            encoder.assert_not_called()
        self.assertFalse(target.exists(), "refused before anything is written")
        (self.root / ".gitignore").write_text("vram/\n", encoding="utf-8")
        tool.ensure_output_ignored(target)
        tool.ensure_output_ignored(tool.actor_target(self.native / "creatures", self.scratch / "outside"))

    def test_command_line_actor_run_scans_no_map_tree(self):
        cache, stage = self.scratch / "cache", self.scratch / "stage"
        argv = ["build_vram_textures.py", "--actor-dir", "creatures", "--actor-dir", "races", "--cache", str(cache),
                "--actor-out-root", str(stage), "--measure-procs", "3", "--procs", "1"]
        with mock.patch.object(tool, "find_godot", return_value=Path("godot")), \
                mock.patch.object(tool, "build", return_value={"ok": 1}) as build, \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(), 0)
        arguments, keywords = build.call_args
        self.assertEqual(arguments[0], [], "no default --maps for an actor run")
        self.assertEqual((keywords["actor_dirs"], keywords["actor_out_root"], keywords["measure_procs"]),
                         (["creatures", "races"], stage.resolve(), 3))
        printed = io.StringIO()
        with mock.patch.object(tool, "find_godot", return_value=Path("godot")), \
                mock.patch.object(sys, "argv", argv + ["--maps", str(self.scratch)]), \
                contextlib.redirect_stdout(printed):
            self.assertEqual(tool.main(), 1)
        self.assertIn("run of its own", printed.getvalue())


@unittest.skipIf(SKIP_ENCODE, SKIP_ENCODE or "")
class ActorBuild(unittest.TestCase):
    """Encodes the actor fixture for real (one encoder process)."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(tempfile.mkdtemp(prefix="vram-actor-build-")).resolve()
        cls.root = _actor_tree(cls.scratch / "client")
        cls.native = cls.root / "assets" / "actors" / "native"
        cls.patches = _actor_patches(cls.root)
        for patch in cls.patches:
            patch.start()
        cls.cache = cls.scratch / "cache"
        cls.out = cls.scratch / "stage" / "app" / "assets" / "actors"
        with contextlib.redirect_stdout(io.StringIO()):
            cls.summary = tool.build([], None, cls.cache, GODOT, 1, actor_dirs=ACTOR_DIRS, actor_out_root=cls.out,
                                     measure_procs=MEASURE_PROCS)

    @classmethod
    def tearDownClass(cls):
        for patch in cls.patches:
            patch.stop()
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def _build(self, **options) -> dict:
        arguments = dict(actor_dirs=ACTOR_DIRS, measure_procs=MEASURE_PROCS)
        arguments.update(options)
        with contextlib.redirect_stdout(io.StringIO()):
            return tool.build([], None, arguments.pop("cache", self.cache), GODOT, 1, **arguments)

    def _indexes(self, out: Path) -> dict[str, dict]:
        native = out / "native"
        return {path.parent.parent.relative_to(native).as_posix(): json.loads(path.read_text(encoding="utf-8"))
                for path in native.rglob("vram/index.json")}

    @staticmethod
    def _by_key(index: dict) -> dict:
        names = {sha: key for key, sha in ACTOR_SHA.items()}
        table = {names[sha]: entry["recipe"] for sha, entry in index["images"].items()}
        table.update({names[sha]: "!" + ("quality" if reason.startswith("quality:") else reason)
                      for sha, reason in index["excluded"].items()})
        return table

    def test_each_actor_directory_gets_its_own_index(self):
        indexes = self._indexes(self.out)
        self.assertEqual({directory: self._by_key(index) for directory, index in indexes.items()}, ACTOR_INDEX)
        for directory, index in indexes.items():
            vram = self.out / "native" / directory / "vram"
            self.assertEqual((index["schema"], index["recipeVersion"]), (tool.SCHEMA, tool.RECIPE_VERSION))
            self.assertEqual(sorted(path.name for path in vram.glob("*.evt")),
                             sorted(entry["file"] for entry in index["images"].values()), directory)
            self.assertTrue((vram / "report.json").is_file(), directory)
            for sha, entry in index["images"].items():
                data = (vram / entry["file"]).read_bytes()
                self.assertEqual((hashlib.sha256(data).hexdigest(), len(data)), (entry["sha256"], entry["fileBytes"]))
                self.assertEqual(entry["format"], tool.FORMAT_OF[entry["recipe"]])
                self.assertEqual(entry["roles"], ACTOR_ROLES[entry["recipe"]], (directory, entry["file"]))
                self.assertEqual((entry["width"], entry["mipmaps"]), (64, 6), "64 px carries its whole chain")
        self.assertFalse(list(self.native.rglob("vram")), "--actor-out-root leaves the actor tree alone")
        self.assertFalse((self.out / "native" / "rl_heads").exists())

    def test_summary_counts_the_actor_images(self):
        indexes = self._indexes(self.out).values()
        images = [entry for index in indexes for entry in index["images"].values()]
        self.assertEqual(self.summary["actorGlbs"], len(ACTOR_GLBS))
        self.assertEqual(self.summary["actorImages"], sum(len(plan) for plan in ACTOR_PLAN.values()))
        self.assertEqual(self.summary["actorAccepted"], len(images))
        self.assertEqual(self.summary["actorExcluded"],
                         {"size_not_multiple_of_4": 1, "role_conflict": 1, "no_material_role": 1, "quality": 1})
        self.assertEqual(self.summary["actorGpuBytes"], sum(entry["gpuBytes"] for entry in images))
        self.assertEqual(self.summary["actorFileBytes"], sum(entry["fileBytes"] for entry in images))
        # One encode per (image, recipe): wolf_base and hair_base are encoded once for their two directories.
        distinct = {(sha, recipe) for plan in ACTOR_PLAN.values() for sha, recipe in
                    ((ACTOR_SHA[key], value) for key, value in plan.items()) if not recipe.startswith("!")}
        self.assertEqual(self.summary["encoded"], len(distinct))
        self.assertTrue(list((self.cache / tool.ACTOR_CACHE_DIR).glob("*.evt")), "encodes live in _actors/")
        self.assertFalse(list(self.cache.glob("*.evt")), "and never at the cache root (the maps' entries)")

    def test_a_rerun_encodes_nothing_and_writes_the_same_indexes(self):
        out = self.scratch / "rerun"
        again = self._build(actor_out_root=out, prune=False)
        self.assertEqual((again["encoded"], again["cached"]), (0, self.summary["encoded"]))
        for directory in ACTOR_INDEX:
            relative = Path("native", directory, "vram", "index.json")
            self.assertEqual((out / relative).read_bytes(), (self.out / relative).read_bytes(), directory)

    def test_actor_floors_and_pruning_never_touch_a_map_run(self):
        tree = self.scratch / "floors"
        maps = tree / "maps"
        shutil.copytree(FIXTURE, maps, ignore=shutil.ignore_patterns("vram", "*.py"))
        cache = tree / "cache"
        shutil.copytree(self.cache / tool.ACTOR_CACHE_DIR, cache / tool.ACTOR_CACHE_DIR)
        with contextlib.redirect_stdout(io.StringIO()):
            first = tool.build([maps], None, cache, GODOT, 1, measure_procs=MEASURE_PROCS)
        map_entries = sorted(path.name for path in cache.glob("*.json"))
        self.assertTrue(map_entries and first["encoded"] > 0)
        actors = self._build(cache=cache, actor_out_root=tree / "actors", floors={"normal_mean_deg": 0.0})
        self.assertEqual(actors["encoded"], 0)
        indexes = self._indexes(tree / "actors")
        refused = {key for index in indexes.values() for key, value in self._by_key(index).items()
                   if value == "!quality"}
        self.assertEqual(refused, {"wolf_normal", "race_normal", "mount_normal"}, "the floors apply to the actors")
        self.assertEqual(sorted(path.name for path in cache.glob("*.json")), map_entries,
                         "the actor run's pruning leaves the maps' encodes alone")
        with contextlib.redirect_stdout(io.StringIO()):
            again = tool.build([maps], None, cache, GODOT, 1, measure_procs=MEASURE_PROCS)
        self.assertEqual(again["encoded"], 0)
        index = json.loads((maps / "shared-assets" / "vram" / "index.json").read_text(encoding="utf-8"))
        self.assertIn("normal", {entry["recipe"] for entry in index["images"].values()},
                      "the map run keeps its own floors")
        self.assertEqual(len(list((cache / tool.ACTOR_CACHE_DIR).glob("*.json"))), self.summary["encoded"],
                         "and the map run's pruning leaves the actors' encodes alone")

    def test_the_plans_actor_normal_floors_accept_the_mount_normal(self):
        out = self.scratch / "relaxed"
        summary = self._build(actor_out_root=out, prune=False, floors=ACTOR_NORMAL_FLOORS)
        self.assertEqual(summary["encoded"], 0, "verdicts are taken again from the recorded numbers")
        expected = {directory: dict(plan) for directory, plan in ACTOR_INDEX.items()}
        expected["mounts"]["mount_normal"] = "normal"
        self.assertEqual({d: self._by_key(index) for d, index in self._indexes(out).items()}, expected)
        self.assertNotIn("quality", summary["actorExcluded"])

    def test_link_output_links_from_the_actor_cache_and_the_budget_counts_the_whole_cache(self):
        out = self.scratch / "linked"
        self._build(actor_out_root=out, link_output=True, prune=False, cache_budget_bytes=1 << 30)
        linked = 0
        store = self.cache / tool.ACTOR_CACHE_DIR
        for index_path in out.rglob("index.json"):
            for sha, entry in json.loads(index_path.read_text(encoding="utf-8"))["images"].items():
                self.assertTrue(any(os.path.samefile(index_path.parent / entry["file"], cached)
                                    for cached in store.glob(f"{sha}.*.evt")), entry["file"])
                linked += 1
        self.assertEqual(linked, self.summary["actorAccepted"])
        cache = self.scratch / "budget"
        shutil.copytree(store, cache / tool.ACTOR_CACHE_DIR)
        (cache / "map-encodes.evt").write_bytes(bytes(2 * 1024 * 1024))
        used = sum(path.stat().st_size for path in cache.rglob("*") if path.is_file())
        with self.assertRaisesRegex(tool.BuildError, "disk budget"):
            self._build(cache=cache, actor_out_root=self.scratch / "linked-budget", link_output=True, prune=False,
                        cache_budget_bytes=used + 4 * 1024 * 1024)

    def test_without_an_out_root_the_sidecars_go_beside_the_glbs(self):
        tree = _actor_tree(self.scratch / "in-place")
        native = tree / "assets" / "actors" / "native"
        with mock.patch.object(tool, "ACTORS_ROOT", tree / "assets" / "actors"):
            summary = self._build(actor_dirs=["hair"], prune=False)
        self.assertEqual(summary["encoded"], 0)
        for directory in ("hair", "hair/fitted"):
            index = json.loads((native / directory / "vram" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(self._by_key(index), ACTOR_INDEX[directory])

    def test_command_line(self):
        out = self.scratch / "cli"
        argv = ["build_vram_textures.py", "--actor-dir", "mounts", "--actor-dir", "equipment", "--cache",
                str(self.cache), "--actor-out-root", str(out), "--godot", str(GODOT), "--procs", "1",
                "--measure-procs", str(MEASURE_PROCS), "--no-prune"]
        printed = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(printed):
            self.assertEqual(tool.main(), 0)
        text = printed.getvalue()
        summary = json.loads(text[text.find("\n{") + 1:])
        self.assertEqual((summary["encoded"], summary["actorGlbs"], summary["actorAccepted"]), (0, 2, 1))
        self.assertEqual(set(self._indexes(out)), {"mounts", "equipment"})


if __name__ == "__main__":
    unittest.main()
