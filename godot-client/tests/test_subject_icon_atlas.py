#!/usr/bin/env python3
"""Contract checks for the shared subject icon atlas.

The sheet these were packed from is a generated contact sheet, which is only
approximately ruled: its rows sat on a tighter pitch than its columns, so
slicing it into even cells cut the top off the bottom row. `--detect` exists
because of that, and these checks are what would catch it happening again -
a tile packed from the wrong bounds shows up as a cell that is not opaque
edge to edge, or as one whose framed border is missing on a side.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
ATLAS = CLIENT / "assets" / "ui" / "eloria_subject_icons.png"
LOOKUP = CLIENT / "src" / "ui" / "subject_icons.gd"
CELL_SIZE = 32
COLUMNS = 8


def declared_indices() -> dict[str, int]:
    """The subject-to-cell table as the client actually declares it."""
    source = LOOKUP.read_text(encoding="utf-8")
    block = source[source.index("const INDICES := {"):]
    block = block[:block.index("}")]
    return {name: int(index) for name, index in
            re.findall(r'"([a-z_]+)"\s*:\s*(\d+)', block)}


class SubjectIconAtlasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.image = np.asarray(Image.open(ATLAS).convert("RGBA"))
        self.indices = declared_indices()

    def cell(self, index: int) -> np.ndarray:
        row, column = divmod(index, COLUMNS)
        return self.image[row * CELL_SIZE:(row + 1) * CELL_SIZE,
                          column * CELL_SIZE:(column + 1) * CELL_SIZE]

    def test_the_atlas_keeps_the_runtime_dimensions(self) -> None:
        self.assertEqual((256, 256, 4), self.image.shape)

    def test_every_declared_subject_has_a_complete_opaque_tile(self) -> None:
        for name, index in sorted(self.indices.items(), key=lambda p: p[1]):
            with self.subTest(subject=name, index=index):
                cell = self.cell(index)
                self.assertGreater((cell[:, :, 3] > 8).mean(), .98)
                self.assertGreater(
                    len(np.unique(cell.reshape(-1, 4), axis=0)), 80)

    def test_a_tile_is_framed_on_all_four_sides(self) -> None:
        """A tile cropped from the wrong bounds loses a side of its frame, and
        the lost side is the giveaway: the brass rail stops short of the edge
        it was cut on while the other three still reach it."""
        for name, index in sorted(self.indices.items(), key=lambda p: p[1]):
            with self.subTest(subject=name, index=index):
                cell = self.cell(index).astype(int)
                # The rail is the brightest thing near an edge; the backing
                # between tiles is nearly black.
                edges = {
                    "top": cell[:4, :, :3].max(),
                    "bottom": cell[-4:, :, :3].max(),
                    "left": cell[:, :4, :3].max(),
                    "right": cell[:, -4:, :3].max(),
                }
                for side, brightest in edges.items():
                    self.assertGreater(
                        brightest, 60,
                        "%s has no frame on its %s side" % (name, side))

    def test_the_cells_nothing_is_drawn_for_are_empty(self) -> None:
        used = set(self.indices.values())
        for index in range(COLUMNS * COLUMNS):
            if index in used:
                continue
            with self.subTest(index=index):
                self.assertEqual(0, self.cell(index)[:, :, 3].max())

    def test_the_table_is_a_dense_run_from_zero(self) -> None:
        """Cells are addressed by number, so a gap in the table is a hole in
        the sheet that nothing would ever notice."""
        self.assertEqual(sorted(self.indices.values()),
                         list(range(len(self.indices))))


class SubjectCoverageTest(unittest.TestCase):
    """Every shelf and tab the client draws has to resolve to a picture."""

    def setUp(self) -> None:
        self.indices = declared_indices()
        source = LOOKUP.read_text(encoding="utf-8")
        block = source[source.index("const ALIASES := {"):]
        self.aliases = dict(re.findall(
            r'"([a-z_]+)"\s*:\s*"([a-z_]+)"', block[:block.index("}")]))

    def resolves(self, subject: str) -> bool:
        key = subject.strip().lower()
        return self.aliases.get(key, key) in self.indices

    def test_every_encyclopedia_category_has_an_icon(self) -> None:
        document = json.loads(
            (CLIENT / "data" / "reference" / "encyclopedia.json")
            .read_text(encoding="utf-8"))
        for category in document["categories"]:
            with self.subTest(category=category["id"]):
                self.assertTrue(self.resolves(category["id"]))

    def test_every_mixing_skill_has_an_icon(self) -> None:
        recipes = json.loads(
            (CLIENT / "data" / "manufacturing" / "recipes.json")
            .read_text(encoding="utf-8"))["recipes"]
        for skill in sorted({recipe["skill"] for recipe in recipes}):
            with self.subTest(skill=skill):
                self.assertTrue(self.resolves(skill))

    def test_every_skill_the_statistics_table_lists_has_an_icon(self) -> None:
        """The table names a skill per row. A skill added to a group without a
        picture drawn for it leaves one row blank, which reads as a mistake
        rather than as a gap."""
        main = (CLIENT / "src" / "app" / "main.gd").read_text(encoding="utf-8")
        block = main[main.index("const SKILL_GROUPS: Array[Array] = ["):]
        block = block[:block.index(chr(10) + "]")]
        for skill in re.findall(r'"([a-z]+)"', block):
            if skill[0].isupper():
                continue
            with self.subTest(skill=skill):
                self.assertTrue(self.resolves(skill))

    def test_an_alias_points_at_a_subject_that_exists(self) -> None:
        for alias, target in self.aliases.items():
            with self.subTest(alias=alias):
                self.assertIn(target, self.indices)
                self.assertNotIn(alias, self.indices,
                                 "%s is both a subject and an alias" % alias)


if __name__ == "__main__":
    unittest.main()
