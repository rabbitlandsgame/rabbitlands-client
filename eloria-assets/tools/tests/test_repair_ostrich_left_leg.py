"""Input/version guards for the bounded authoring recipe.

The real frozen-pair replay is also recorded in the versioned repair receipt.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import repair_ostrich_left_leg as tool


class RecipeGuards(unittest.TestCase):
    def test_wrong_reference_rejected_before_loading_or_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(tool, "digest", return_value="stale"), patch.object(tool, "NativeShapeAsset") as loader:
                with self.assertRaisesRegex(ValueError, "exact frozen"):
                    tool.repair(root / "source", root / "baseline", root / "new.glb", root / "report.json")
                loader.assert_not_called()
                self.assertEqual(list(root.iterdir()), [])

    def test_report_cannot_overwrite_input_or_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, baseline = root / "source", root / "baseline"
            def digest(path):
                return tool.REFERENCE_SHA if path == source else tool.BASELINE_SHA
            with patch.object(tool, "digest", side_effect=digest), patch.object(tool, "NativeShapeAsset") as loader:
                for report in (source, baseline, root / "new.glb"):
                    with self.assertRaisesRegex(ValueError, "separate new files"):
                        tool.repair(source, baseline, root / "new.glb", report)
                loader.assert_not_called()

    def test_existing_version_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, baseline, output = root / "source", root / "baseline", root / "existing.glb"
            output.write_bytes(b"retained evidence")
            with patch.object(tool, "digest", side_effect=[tool.REFERENCE_SHA, tool.BASELINE_SHA]):
                with self.assertRaisesRegex(ValueError, "separate new files"):
                    tool.repair(source, baseline, output, root / "report.json")
            self.assertEqual(output.read_bytes(), b"retained evidence")


if __name__ == "__main__":
    unittest.main()
