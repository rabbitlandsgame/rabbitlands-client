"""Raw scenery exports once, with independent imported-resource overrides."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_client as package
import runner_retirement


class WorldImports(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.model = "godot-client/assets/world/props/bookcase.glb"
        self.image = self.model[:-4] + "_wood.png"
        self.pixels = b"\x89PNG exact encoded source bytes"
        document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(self.pixels)}],
                    "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(self.pixels)}],
                    "images": [{"name": "wood", "bufferView": 0, "mimeType": "image/png"}]}
        raw = json.dumps(document).encode()
        raw += b" " * (-len(raw) % 4)
        binary = self.pixels + bytes(-len(self.pixels) % 4)
        self.write(self.model, b"glTF" + struct.pack("<II", 2, 28 + len(raw) + len(binary))
                   + struct.pack("<II", len(raw), 0x4E4F534A) + raw
                   + struct.pack("<II", len(binary), 0x004E4942) + binary)
        self.write(self.image, self.pixels)
        self.write("godot-client/src/actors/glb_scene_cache.gd", 'if not resource_path.begins_with("res://assets/actors/"):\n\treturn null\n')
        self.original = (self.root / self.model).read_bytes()
        self.patch = mock.patch.object(package, "tracked", self.tracked)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def tracked(self, root, *specs):
        return [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
                and any(path.relative_to(root).as_posix() == spec or path.relative_to(root).as_posix().startswith(spec.rstrip("/") + "/")
                        for spec in specs)]

    def write(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents.encode() if isinstance(contents, str) else contents)

    def test_raw_scene_and_exact_unused_derivative_are_not_imported(self):
        result = package.write_world_import_settings(self.root)
        self.assertEqual(result["raw_models"], {self.model})
        self.assertEqual(result["dropped_images"], {self.image})
        for path in (self.model, self.image):
            self.assertEqual(package._import_settings(self.root / (path + ".import"))[0], "skip")
        self.assertEqual((self.root / self.model).read_bytes(), self.original)
        self.assertEqual((self.root / self.image).read_bytes(), self.pixels)
        self.assertNotIn(self.image, package.scene_textures(self.root))

    def test_runner_reuses_complete_world_proof_after_actual_verified_map_retirement(self):
        relative = "eloria-assets/maps/continent-v2/_continent_v2/content/boat-network.json"
        self.write(relative, '{"note":"no world resource override"}\n')
        raw = (self.root / relative).read_bytes()
        expected = {relative: hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()}
        # A Git index continues to name retired tracked inputs. The ordinary
        # fixture's filesystem inventory must retain those names as Git does.
        files = self.tracked(self.root, "godot-client", "eloria-assets/maps")
        def committed(_root, *specs):
            return [path for path in files if any(path == spec or path.startswith(spec.rstrip("/") + "/") for spec in specs)]
        storage = SimpleNamespace(world_import_plans={})
        with tempfile.TemporaryDirectory() as outside:
            stage = Path(outside) / "stage"
            stage.mkdir()
            receipt = Path(outside) / "map-source-retirement.json"
            with mock.patch.object(package, "tracked", side_effect=committed), mock.patch.object(package, "STORAGE", storage):
                proof = package.world_import_shipping(self.root)
                retired = runner_retirement.retire_unstaged_maps(self.root, stage, expected, {}, lambda *_: None, receipt)
                self.assertEqual(set(retired["files"]), {relative})
                self.assertFalse((self.root / relative).exists())
                self.assertEqual(package.world_import_shipping(self.root), proof)
                # Exercise the failing production consumer, not just its cache.
                with mock.patch.object(package, "actor_shipping", return_value={"loose": set(), "dropped": set()}), \
                        mock.patch.object(package, "pck_paths", return_value=set()):
                    package.stage_loose_client_files(self.root, stage / "app")
                    package.check_world_import_pack(self.root, stage / "app")
                self.assertEqual((stage / "app/assets/world/props/bookcase.glb").read_bytes(), self.original)
                self.assertFalse((stage / "app/assets/world/props/bookcase_wood.png").exists())

    def test_runner_first_missing_reference_input_fails_without_caching_partial_proof(self):
        relative = "eloria-assets/maps/continent-v2/_continent_v2/content/boat-network.json"
        storage = SimpleNamespace(world_import_plans={})
        original = self.tracked
        with mock.patch.object(package, "tracked", side_effect=lambda root, *specs:
                original(root, *specs) + ([relative] if "eloria-assets/maps" in specs else [])), \
                mock.patch.object(package, "STORAGE", storage):
            with self.assertRaises(FileNotFoundError):
                package.world_import_shipping(self.root)
        self.assertEqual(storage.world_import_plans, {})

    def test_runner_generation_reset_invalidates_prior_world_proof(self):
        storage = SimpleNamespace(world_import_plans={})
        with mock.patch.object(package, "STORAGE", storage):
            first = package.world_import_shipping(self.root)
            first["dropped_images"].clear()
            self.assertEqual(package.world_import_shipping(self.root)["dropped_images"], {self.image})
            self.write("godot-client/src/new.tscn", '[gd_scene]\n[ext_resource type="PackedScene" '
                       'path="res://assets/world/props/bookcase.glb" id="1"]\n')
            self.write(".git", "gitdir: fixture\n")
            with self.assertRaisesRegex(package.PackageError, "fresh disposable build worktree"):
                package.prepare_build_tree(self.root, "a" * 40)
            self.assertEqual(storage.world_import_plans, {})
            self.assertEqual(package.world_import_shipping(self.root)["imported_models"], {self.model})

    def test_matching_name_with_custom_pixels_is_preserved(self):
        self.write(self.image, b"custom painted override")
        result = package.write_world_import_settings(self.root)
        self.assertNotIn(self.image, result["dropped_images"])
        self.assertFalse((self.root / (self.image + ".import")).exists())
        self.assertIn(self.image, package.scene_textures(self.root))

    def test_explicit_material_or_script_image_reference_overrides_dropping(self):
        self.write("godot-client/src/material.tres", '[gd_resource type="StandardMaterial3D"]\n'
                   '[ext_resource type="Texture2D" path="res://assets/world/props/bookcase_wood.png" id="1"]\n'
                   '[resource]\nalbedo_texture=ExtResource("1")\n')
        result = package.write_world_import_settings(self.root)
        self.assertNotIn(self.image, result["dropped_images"])
        self.assertIn(self.image, package.scene_textures(self.root))

    def test_explicit_imported_scene_reference_wins_and_clears_a_previous_skip(self):
        package.write_world_import_settings(self.root)
        self.write("godot-client/src/sample.tscn", '[gd_scene]\n'
                   '[ext_resource type="PackedScene" path="res://assets/world/props/bookcase.glb" id="1"]\n')
        result = package.write_world_import_settings(self.root)
        self.assertEqual(result["imported_models"], {self.model})
        self.assertNotIn(self.image, result["dropped_images"])
        self.assertFalse((self.root / (self.model + ".import")).exists())
        self.assertIn(self.image, package.scene_textures(self.root))

    def test_explicit_gdscript_load_keeps_the_scene_import(self):
        self.write("godot-client/src/sample.gd", 'const SCENE=preload("res://assets/world/props/bookcase.glb")\n')
        self.assertEqual(package.world_import_shipping(self.root)["imported_models"], {self.model})

    def test_another_raw_glTF_image_uri_preserves_the_texture(self):
        raw = json.dumps({"asset": {"version": "2.0"}, "images": [{"uri": "../../world/props/bookcase_wood.png"}]}).encode()
        raw += b" " * (-len(raw) % 4)
        self.write("godot-client/assets/actors/native/creature.glb", b"glTF" + struct.pack("<II", 2, 20 + len(raw))
                   + struct.pack("<II", len(raw), 0x4E4F534A) + raw)
        self.assertNotIn(self.image, package.world_import_shipping(self.root)["dropped_images"])

    def test_unrecognized_or_older_world_reader_keeps_its_imports(self):
        self.write("godot-client/src/actors/glb_scene_cache.gd", 'return ResourceLoader.load(path)\n')
        self.assertEqual(package.world_import_shipping(self.root)["imported_models"], {self.model})

    def test_dynamic_world_directory_prefix_keeps_possible_resource_dependencies(self):
        self.write("godot-client/src/custom.gd", 'const ROOT="res://assets/world/props/"\n'
                   'func resource(id): return ResourceLoader.load(ROOT + id)\n')
        result = package.world_import_shipping(self.root)
        self.assertEqual(result["imported_models"], {self.model})
        self.assertNotIn(self.image, result["dropped_images"])

    def test_loose_stage_keeps_raw_model_and_omits_only_verified_unused_image(self):
        app = self.root / "app"
        with mock.patch.object(package, "actor_shipping", return_value={"loose": set(), "dropped": set()}), \
                mock.patch.object(package, "pck_paths", return_value=set()):
            package.stage_loose_client_files(self.root, app)
        self.assertEqual((app / self.model.removeprefix("godot-client/")).read_bytes(), self.original)
        self.assertFalse((app / self.image.removeprefix("godot-client/")).exists())
        with mock.patch.object(package, "pck_paths", return_value=set()):
            package.check_world_import_pack(self.root, app)
        with mock.patch.object(package, "pck_paths", return_value={self.model.removeprefix("godot-client/") + ".import"}):
            with self.assertRaisesRegex(package.PackageError, "unused editor resource"):
                package.check_world_import_pack(self.root, app)
        (app / self.model.removeprefix("godot-client/")).write_bytes(b"modified raw model")
        with mock.patch.object(package, "pck_paths", return_value=set()):
            with self.assertRaisesRegex(package.PackageError, "raw source is missing or changed"):
                package.check_world_import_pack(self.root, app)

    def externalize_fixture(self, *, eligible=True):
        sha = hashlib.sha256(self.pixels).hexdigest()
        pool = "eloria-assets/world/_shared/images/" + sha + ".png"
        uri = "../../../../" + pool
        self.write(pool, self.pixels)
        document = {"asset": {"version": "2.0"}, "images": [{"name": "wood", "uri": uri, "extras": {
            "rl_texture_policy_directory": ".", "rl_texture_sidecar_eligible": eligible}}], "extras": {
            "rabbitlands_scenery_images": {"schema": "rabbitlands-scenery-images-v1", "mipPolicy": "full",
                "resources": {uri: sha}, "imagePolicies": {uri: ["."]}}}}
        raw = json.dumps(document).encode()
        raw += b" " * (-len(raw) % 4)
        self.write(self.model, b"glTF" + struct.pack("<II", 2, 20 + len(raw))
                   + struct.pack("<II", len(raw), 0x4E4F534A) + raw)
        return pool, sha

    def stage_externalized_fixture(self, *, eligible=True):
        pool, sha = self.externalize_fixture(eligible=eligible)
        stage = self.root / "stage"
        package.stage_eloria_assets(self.root, stage)
        with mock.patch.object(package, "actor_shipping", return_value={"loose": set(), "dropped": set()}), \
                mock.patch.object(package, "pck_paths", return_value=set()):
            package.stage_loose_client_files(self.root, stage / "app")
        return stage, pool, sha

    def test_new_world_pool_is_in_the_verified_loose_shipping_closure(self):
        stage, pool, _ = self.stage_externalized_fixture()
        self.assertEqual((stage / pool).read_bytes(), self.pixels)
        package.check_loose_scenery_images(self.root, stage)
        (stage / pool).write_bytes(b"changed staged pixels")
        with self.assertRaisesRegex(package.PackageError, "staged scenery images"):
            package.check_loose_scenery_images(self.root, stage)

    def test_untracked_or_modified_external_pixels_fail_closed(self):
        pool, _ = self.externalize_fixture()
        with mock.patch.object(package, "tracked", side_effect=lambda root, *paths: [
                path for path in self.tracked(root, *paths) if path != pool]):
            with self.assertRaisesRegex(package.PackageError, "not in the commit"):
                package.scenery_image_resources(self.root)
        (self.root / pool).write_bytes(b"changed source pixels")
        with self.assertRaisesRegex(package.PackageError, "missing/changed"):
            package.scenery_image_resources(self.root)

    def test_converted_scenery_retains_original_directory_sidecar_coverage(self):
        stage, _, sha = self.stage_externalized_fixture()
        self.write("stage/app/data/world/town-scenery.json", json.dumps({"assets": {
            "bookcase": "res://assets/world/props/bookcase.glb"}}))
        with self.assertRaisesRegex(package.PackageError, "no original-directory sidecar/exclusion"):
            package.check_scenery_vram_textures(stage / "app")
        self.write("stage/app/assets/world/props/vram/index.json", json.dumps({"images": {}, "excluded": {sha: "quality_gate"}}))
        package.check_scenery_vram_textures(stage / "app")

    def test_legacy_uri_image_does_not_gain_a_sidecar_requirement(self):
        stage, _, _ = self.stage_externalized_fixture(eligible=False)
        self.write("stage/app/data/world/town-scenery.json", json.dumps({"assets": {
            "bookcase": "res://assets/world/props/bookcase.glb"}}))
        package.check_scenery_vram_textures(stage / "app")


if __name__ == "__main__":
    unittest.main()
