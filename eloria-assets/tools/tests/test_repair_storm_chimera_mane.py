"""Conservative whole-piece and version guards for the mane authoring recipe."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import repair_storm_chimera_mane as tool


class StrandGuards(unittest.TestCase):
    def test_one_protected_seam_excludes_whole_piece(self):
        ids, mass = np.array([0, 1, 2]), np.ones(4)
        self.assertFalse(tool.eligible_component(ids, {2}, mass))
        self.assertTrue(tool.eligible_component(ids, {3}, mass))

    def test_body_and_large_components_excluded(self):
        self.assertFalse(tool.eligible_component(np.arange(101), set(), np.ones(101)))
        self.assertFalse(tool.eligible_component(np.arange(4), set(), np.full(4, .79)))

    def test_stale_profile_rejected_before_loading(self):
        with patch.object(tool, "digest", side_effect=[tool.REFERENCE_SHA, tool.BASELINE_SHA, "stale"]):
            with patch.object(tool, "NativeShapeAsset") as loader:
                with self.assertRaisesRegex(ValueError, "exact frozen"):
                    tool.repair(Path("source"), Path("bake"), Path("profile"), Path("new"), Path("report"))
                loader.assert_not_called()

    def test_report_cannot_overwrite_frozen_profile(self):
        with patch.object(tool, "digest", side_effect=[tool.REFERENCE_SHA, tool.BASELINE_SHA, tool.PROFILE_SHA]):
            with patch.object(tool, "NativeShapeAsset") as loader:
                with self.assertRaisesRegex(ValueError, "separate new files"):
                    tool.repair(Path("source"), Path("bake"), Path("profile"), Path("new"), Path("profile"))
                loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
