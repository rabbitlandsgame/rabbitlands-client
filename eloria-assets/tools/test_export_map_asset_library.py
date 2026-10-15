from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_map_asset_library as E


class MapAssetLibraryExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.output = cls.root / "assets/world/continent"
        cls.catalog = cls.root / "data/world/map_asset_extras.json"
        cls.result = E.export_library(E.DEFAULT_MANIFEST, cls.output, cls.catalog)
        cls.source = json.loads(E.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        cls.extras = json.loads(cls.catalog.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_declared_assets_and_prop_families_are_exported(self):
        expected_families = {
            "cracked_slab", "cellar_hatch", "loose_stone", "drain_grate",
            "shrine_slab", "ivy_arch", "cairn", "reed_hide", "ice_crack",
            "root_door", "tide_cave", "crystal_seam", "sand_sink",
            "hollow_tree", "well_shaft",
        }
        self.assertEqual(self.result["assetCount"], len(self.source["assets"]))
        self.assertEqual({row.get("family") for row in self.source["assets"] if row.get("family")},
                         expected_families)
        self.assertEqual([row["id"] for row in self.extras["entries"]],
                         [row["id"] for row in self.source["assets"]])
        self.assertLessEqual(self.result["outputBytes"], self.source["maxOutputBytes"])

    def test_outputs_are_centered_grounded_and_keep_reachable_resources(self):
        for source_spec, report in zip(self.source["assets"], self.result["assets"], strict=True):
            path = self.output / (source_spec["id"].removeprefix("continent:") + ".glb")
            document, body = E.S.GR.load(path)
            roots = document["scenes"][document.get("scene", 0)]["nodes"]
            low, high = E.OE.subtree_bounds_all(E.S, document, body, roots)
            self.assertAlmostEqual(float(low[1]), 0.0, places=4, msg=source_spec["id"])
            self.assertAlmostEqual(float((low[0] + high[0]) * 0.5), 0.0, places=4,
                                   msg=source_spec["id"])
            self.assertAlmostEqual(float((low[2] + high[2]) * 0.5), 0.0, places=4,
                                   msg=source_spec["id"])
            self.assertTrue(np.allclose(high - low, report["bounds"]["size"], atol=1e-4),
                            source_spec["id"])
            self.assertGreater(len(document.get("meshes", [])), 0, source_spec["id"])
            self.assertGreater(len(document.get("materials", [])), 0, source_spec["id"])
            for image in document.get("images", []):
                uri = image.get("uri", "")
                self.assertTrue(uri and not Path(uri).is_absolute(), source_spec["id"])
                texture = (path.parent / uri).resolve()
                texture.relative_to(self.output.resolve())
                self.assertTrue(texture.is_file(), texture)

    def test_source_roots_are_current_complete_placements(self):
        allowed = E._allowed_sources()
        for spec in self.source["assets"]:
            source = (E.MAPS / spec["source"]).resolve()
            self.assertIn(source, allowed)
            document, _ = E.S.GR.load(source)
            roots = E._select_roots(spec["id"], document, spec["roots"])
            self.assertEqual(len(roots), len(spec["roots"]))


if __name__ == "__main__":
    unittest.main()
