#!/usr/bin/env python3
"""Validate the unregistered themed item-icon concept sheets."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
CONCEPTS = ROOT / "eloria-assets" / "concepts" / "item-icons"
MANIFEST = CONCEPTS / "manifest.json"


class ItemIconConceptSheetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text())

    def test_manifest_describes_twenty_unregistered_sheets(self) -> None:
        self.assertEqual(1, self.manifest["schema"])
        self.assertFalse(self.manifest["runtimeRegistered"])
        self.assertFalse(self.manifest["serverEntriesAdded"])
        self.assertEqual(20, len(self.manifest["sheets"]))
        self.assertEqual(500, sum(len(sheet["items"])
                                  for sheet in self.manifest["sheets"]))

    def test_sheet_names_layout_and_files_are_stable(self) -> None:
        layout = self.manifest["layout"]
        self.assertEqual([256, 256], layout["canvasSize"])
        self.assertEqual([50, 50], layout["cellSize"])
        self.assertEqual(5, layout["columns"])
        self.assertEqual(5, layout["rows"])
        self.assertEqual(25, layout["imagesPerSheet"])
        expected = [f"{index:02d}_" for index in range(1, 21)]
        files = [sheet["file"] for sheet in self.manifest["sheets"]]
        self.assertEqual(expected, [name[:3] for name in files])
        self.assertEqual(files, sorted(path.name for path in
                                      CONCEPTS.glob("*.png")))

    def test_every_cell_is_independently_painted(self) -> None:
        for sheet in self.manifest["sheets"]:
            image = Image.open(CONCEPTS / sheet["file"]).convert("RGBA")
            with self.subTest(sheet=sheet["file"]):
                self.assertEqual((256, 256), image.size)
            for index in range(25):
                row, column = divmod(index, 5)
                cell = image.crop((column * 50, row * 50,
                                   (column + 1) * 50, (row + 1) * 50))
                alpha = cell.getchannel("A")
                painted = sum(alpha.histogram()[9:]) / 2500
                colours = len(cell.getcolors(maxcolors=2501) or [])
                with self.subTest(sheet=sheet["file"], cell=index):
                    self.assertGreater(
                        painted, .90, "cell is not backed by its own plate")
                    self.assertGreater(
                        colours, 100, "cell lacks distinct icon detail")

    def test_unused_tail_padding_is_transparent(self) -> None:
        for sheet in self.manifest["sheets"]:
            image = Image.open(CONCEPTS / sheet["file"]).convert("RGBA")
            alpha = image.getchannel("A")
            right = alpha.crop((250, 0, 256, 256))
            bottom = alpha.crop((0, 250, 256, 256))
            with self.subTest(sheet=sheet["file"]):
                self.assertEqual(0, right.getextrema()[1])
                self.assertEqual(0, bottom.getextrema()[1])

    def test_concepts_are_not_in_the_runtime_atlas_registry(self) -> None:
        registry_path = CLIENT / "data" / "items" / "atlases.json"
        registry = registry_path.read_text()
        self.assertNotIn("concepts/item-icons", registry)
        for sheet in self.manifest["sheets"]:
            with self.subTest(sheet=sheet["file"]):
                self.assertNotIn(sheet["file"], registry)


if __name__ == "__main__":
    unittest.main()
