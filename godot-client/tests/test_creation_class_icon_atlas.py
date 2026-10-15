#!/usr/bin/env python3
"""Raster and lookup contracts for character-creation class emblems.

The creation rail draws four large buttons from one compact sheet.  These
checks keep the source art inside its cell, keep the runtime lookup in lockstep
with the packing order, and guard the cache that prevents class/appearance
redraws from allocating new AtlasTextures.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
ATLAS = CLIENT / "assets" / "ui" / "eloria_creation_class_icons.png"
LOOKUP = CLIENT / "src" / "ui" / "creation_class_icons.gd"
CELL_SIZE = 128
COLUMNS = 4
EXPECTED = ["vanguard", "ranger", "arcanist", "warden"]


def declared_indices() -> dict[str, int]:
    source = LOOKUP.read_text(encoding="utf-8")
    block = source[source.index("const INDICES := {"):]
    block = block[:block.index("}")]
    return {name: int(index) for name, index in
            re.findall(r'"([a-z_]+)"\s*:\s*(\d+)', block)}


class CreationClassIconAtlasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.image = np.asarray(Image.open(ATLAS).convert("RGBA"))
        self.indices = declared_indices()

    def cell(self, index: int) -> np.ndarray:
        return self.image[:, index * CELL_SIZE:(index + 1) * CELL_SIZE]

    def test_the_atlas_keeps_the_runtime_dimensions(self) -> None:
        self.assertEqual((128, 512, 4), self.image.shape)

    def test_lookup_matches_the_packed_class_order(self) -> None:
        ordered = [name for name, _ in
                   sorted(self.indices.items(), key=lambda pair: pair[1])]
        self.assertEqual(EXPECTED, ordered)
        self.assertEqual(list(range(COLUMNS)), sorted(self.indices.values()))

    def test_every_class_has_a_distinct_transparent_emblem(self) -> None:
        cells = []
        for name, index in self.indices.items():
            with self.subTest(class_name=name):
                cell = self.cell(index)
                alpha = cell[:, :, 3]
                coverage = (alpha > 8).mean()
                self.assertGreater(coverage, .10, "%s is blank" % name)
                self.assertLess(coverage, .65,
                                "%s lost its transparent backing" % name)
                self.assertGreater(len(np.unique(
                    cell.reshape(-1, 4), axis=0)), 1000)
                cells.append(cell.tobytes())
        self.assertEqual(len(cells), len(set(cells)))

    def test_artwork_keeps_an_eight_pixel_inset(self) -> None:
        for name, index in self.indices.items():
            with self.subTest(class_name=name):
                alpha = self.cell(index)[:, :, 3]
                for side, strip in (
                        ("top", alpha[:8]), ("bottom", alpha[-8:]),
                        ("left", alpha[:, :8]), ("right", alpha[:, -8:])):
                    self.assertEqual(0, int(strip.max()),
                                     "%s touches its %s edge" % (name, side))

    def test_lookup_caches_subtextures_and_invalidates_on_override(self) -> None:
        source = LOOKUP.read_text(encoding="utf-8")
        self.assertIn("if _cache.has(key):", source)
        self.assertIn("return _cache[key]", source)
        self.assertIn("static func set_sheet_override(texture: Texture2D)",
                      source)
        override = source[source.index("static func set_sheet_override"):]
        self.assertIn("_sheet = texture", override)
        self.assertIn("_cache.clear()", override)


if __name__ == "__main__":
    unittest.main()
