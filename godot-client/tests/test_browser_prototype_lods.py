"""Producer selection boundaries; no Godot run or authored assets are changed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "tools/build_browser_prototype_lods.py"
SPEC = importlib.util.spec_from_file_location("build_browser_prototype_lods", PATH)
PRODUCER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCER)


class PrototypeLodSelectionTests(unittest.TestCase):
    def setUp(self):
        ignored = PATH.parents[2] / ".local/browser-prototype"
        ignored.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ignored)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "eloria-assets/maps/_shared/meshes/tree.glb"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"private selection fixture")
        self.relative = self.source.relative_to(self.root).as_posix()
        self.out = self.root / ".local/lods"
        self.patch = patch.object(PRODUCER, "REPO", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_selection_is_deduplicated_and_keeps_logical_source_path(self):
        job = PRODUCER.prepare_job([self.relative, self.relative], self.out)
        self.assertEqual(job, {"sources": [{"path": self.relative,
                                          "absolute": self.source.as_posix()}],
                               "out": self.out.as_posix()})
        self.assertFalse(self.out.exists(), "selection validation has no write side effects")

    def test_output_cannot_escape_ignored_directory(self):
        for out in [self.root, self.root / "eloria-assets/derived", self.root / ".local/../public"]:
            with self.subTest(out=out), self.assertRaises(ValueError):
                PRODUCER.prepare_job([self.relative], out)

    def test_empty_missing_non_glb_and_non_map_sources_are_rejected(self):
        outside = self.root / "eloria-assets/actors/actor.glb"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(b"actor")
        other = self.source.with_suffix(".json")
        other.write_bytes(b"{}")
        for selection in [[], ["eloria-assets/maps/missing.glb"],
                          [other.relative_to(self.root).as_posix()],
                          [outside.relative_to(self.root).as_posix()],
                          ["../outside.glb"]]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                PRODUCER.prepare_job(selection, self.out)


if __name__ == "__main__":
    unittest.main()
