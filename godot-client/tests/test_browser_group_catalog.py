import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from browser_asset_catalog import factor_groups, creation_models
import build_web_prototype as web


class BrowserGroupCatalogTests(unittest.TestCase):
    def test_only_current_playable_models_are_required_before_character_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            client = Path(temporary)
            policy = client / "src/actors/player_creation_policy.gd"
            policy.parent.mkdir(parents=True)
            policy.write_text('const ACTOR_TYPES: Array[int] = [0, 1]\n')
            registry = {"creationOptions":[{"actorType":0,"model":"human_female"},
                {"actorType":1,"model":"human_male"}, {"actorType":3,"model":"npc_male"}]}
            self.assertEqual(creation_models(client, registry), {"human_female","human_male"})

    def test_shared_files_have_one_owner_and_dependency_pins_can_retain_them(self):
        a, b, shared, startup = map(Path, ("a", "b", "shared", "startup"))
        source = {"startup":{startup}, "map:a":{a, shared, startup}, "model:b":{b, shared}}
        groups, dependencies = factor_groups(source)
        all_files = [path for paths in groups.values() for path in paths]
        self.assertEqual(set(all_files), {a,b,shared,startup})
        self.assertEqual(len(all_files), 4)
        shared_id = next(name for name in groups if name.startswith("shared:"))
        self.assertIn(shared_id, dependencies["map:a"])
        self.assertIn(shared_id, dependencies["model:b"])
        self.assertIn("startup", dependencies["map:a"])

    def test_archives_are_stable_and_large_files_reassemble_exactly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); target = root / "godot-client/assets/large.bin"
            target.parent.mkdir(parents=True); assets = root / "assets"; assets.mkdir()
            original = bytes(range(256)) * 24577
            target.write_bytes(original)
            before = web.REPO
            try:
                web.REPO = root
                first = web.raw_archives([target], assets)[0]
                os.utime(target, (1000000000,1000000000))
                second = web.raw_archives([target], assets)[0]
            finally: web.REPO = before
            self.assertEqual(first, second)
            with zipfile.ZipFile(assets / first["file"]) as archive:
                self.assertGreater(len(archive.namelist()), 1)
                decoded = b"".join(archive.read(name) for name in archive.namelist())
                self.assertTrue(all(archive.getinfo(name).file_size <= 2*1024*1024 for name in archive.namelist()))
            self.assertEqual(hashlib.sha256(decoded).digest(), hashlib.sha256(original).digest())


if __name__ == "__main__": unittest.main()
