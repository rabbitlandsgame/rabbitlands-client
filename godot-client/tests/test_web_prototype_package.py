"""Qualify the real Landfall dependency closure, including streamed road data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_web_prototype as web
from road_ground_dependencies import dependencies as road_dependencies


class LandfallPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = set(web.raw_files())
        registry = json.loads((web.CLIENT / "data/maps/registry.json").read_text())
        cls.manifest = (web.CLIENT / registry["maps"]["landfall"]["manifest"].removeprefix("res://")).resolve()

    def test_every_declared_landfall_chunk_and_road_field_is_available(self):
        self.assertEqual(web.MAPS, ("landfall",))
        root = json.loads(self.manifest.read_text())
        chunks = root["streamingChunks"]["chunks"]
        self.assertGreater(len(chunks), 1)
        roads = 0
        for row in chunks:
            manifest = (self.manifest.parent / row["manifest"]).resolve()
            self.assertIn(manifest, self.files)
            document = json.loads(manifest.read_text())
            self.assertIn((manifest.parent / document["asset"]["glb"]).resolve(), self.files)
            closure = road_dependencies(web.REPO, manifest, document.get("roadGround"))
            self.assertTrue(set(closure).issubset(self.files))
            roads += bool(closure)
        self.assertGreater(roads, 0)

    def test_archive_is_runtime_content_from_the_client_repository(self):
        for path in self.files:
            self.assertTrue(path.is_relative_to(web.REPO))
            self.assertNotIn(".local", path.relative_to(web.REPO).parts)
            self.assertNotIn(path.suffix, {".sqlite3", ".key", ".pem", ".py"})
        self.assertNotIn(web.REPO / "eloria-assets/maps/lantern-reach/world.json", self.files)

    def test_cape_export_registers_only_the_small_platform_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "site").mkdir()
            (root / "build.json").write_text('{"archives":[]}')
            module = root / "browser_cape.wasm"
            module.write_bytes(b"\0asm\1\0\0\0")
            editor = root / "browser_cape.dll"
            editor.write_bytes(b"editor fixture")
            notice = root / "godot-cpp-LICENSE.md"
            notice.write_text("MIT fixture")
            web.stage_browser_cape(root, module, editor)
            directory = root / "project/assets/platform/browser_cape"
            self.assertEqual((directory / module.name).read_bytes(), module.read_bytes())
            self.assertEqual((directory / editor.name).read_bytes(), editor.read_bytes())
            self.assertEqual((root / "site" / notice.name).read_text(), notice.read_text())
            descriptor = (directory / "browser_cape.gdextension").read_text()
            self.assertIn('web.wasm32="./browser_cape.wasm"', descriptor)
            self.assertIn('windows.x86_64="./browser_cape.dll"', descriptor)
            self.assertEqual(json.loads((root / "build.json").read_text())["browser_cape_sha256"],
                             web.describe(module)["sha256"])

    def test_raw_world_scenes_do_not_duplicate_the_runtime_but_explicit_users_win(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reader = root / "src/actors/glb_scene_cache.gd"
            reader.parent.mkdir(parents=True)
            reader.write_text('if not resource_path.begins_with("res://assets/actors/"):\n pass\n')
            models = root / "assets/world"
            models.mkdir(parents=True)
            for name in ("raw", "direct", "scene", "dynamic"):
                (models / (name + ".glb")).write_bytes(b"fixture")
            (root / "src/users.gd").write_text('''var a = load("res://assets/world/direct.glb")
const PATH = "res://assets/world/dynamic.glb"
var b = load(PATH)
''')
            (root / "scene.tscn").write_text('[ext_resource path="res://assets/world/scene.glb"]')
            self.assertEqual(web.raw_world_models(root), {models / "raw.glb"})
            # An unrecognized reader retains all ordinary editor imports.
            reader.write_text("changed reader")
            self.assertEqual(web.raw_world_models(root), set())

    def test_loose_scenery_images_keep_independent_resource_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reader = root / "src/actors/glb_scene_cache.gd"
            reader.parent.mkdir(parents=True)
            reader.write_text('if not resource_path.begins_with("res://assets/actors/"):\n pass\nconst ROOT="res://assets/world/"')
            folder = root / "assets/world/underground"
            folder.mkdir(parents=True)
            raw_model = folder / "raw.glb"
            raw_model.write_bytes(b"fixture")
            for name in ("loose.jpg", "used.jpg"):
                (folder / name).write_bytes(b"fixture")
            (root / "data").mkdir()
            (root / "data/images.json").write_text('{"icon":"res://assets/world/underground/used.jpg"}')
            self.assertEqual(web.raw_underground_images(root, {raw_model}), {folder / "loose.jpg"})
            self.assertEqual(web.raw_underground_images(root, set()), set())


if __name__ == "__main__":
    unittest.main()
