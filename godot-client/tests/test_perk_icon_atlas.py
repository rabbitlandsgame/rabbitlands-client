#!/usr/bin/env python3
"""Contract checks for the perk emblem atlas.

These are not the framed tiles the subject atlas holds, so the checks are the
other way around: a tile is opaque to its edges and an emblem must NOT be.
An emblem is meant to sit on whatever panel draws the row, so a cell that is
opaque edge to edge means the backing was never keyed out, and a cell whose
ink touches the boundary means it was cropped from the wrong bounds and the
padding that keeps the column even has been eaten.
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
ATLAS = CLIENT / "assets" / "ui" / "eloria_perk_icons.png"
LOOKUP = CLIENT / "src" / "ui" / "perk_icons.gd"
CELL_SIZE = 32
COLUMNS = 8


def declared_indices() -> dict[str, int]:
    source = LOOKUP.read_text(encoding="utf-8")
    block = source[source.index("const INDICES := {"):]
    block = block[:block.index("}")]
    return {name: int(index) for name, index in
            re.findall(r'"([a-z ]+)"\s*:\s*(\d+)', block)}


class PerkIconAtlasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.image = np.asarray(Image.open(ATLAS).convert("RGBA"))
        self.indices = declared_indices()

    def cell(self, index: int) -> np.ndarray:
        row, column = divmod(index, COLUMNS)
        return self.image[row * CELL_SIZE:(row + 1) * CELL_SIZE,
                          column * CELL_SIZE:(column + 1) * CELL_SIZE]

    def test_the_atlas_keeps_the_runtime_dimensions(self) -> None:
        self.assertEqual((256, 256, 4), self.image.shape)

    def test_every_perk_has_a_drawn_emblem(self) -> None:
        for name, index in sorted(self.indices.items(), key=lambda p: p[1]):
            with self.subTest(perk=name, index=index):
                covered = (self.cell(index)[:, :, 3] > 8).mean()
                self.assertGreater(covered, .05, "%s is blank" % name)
                self.assertLess(covered, .85,
                                "%s fills its cell; the backing was not "
                                "keyed out" % name)

    def test_an_emblem_keeps_clear_of_its_own_edges(self) -> None:
        """Cropped from the wrong bounds, a symbol runs to the cell boundary
        and the column stops lining up.

        What is checked is solid ink on the boundary, not any ink at all. The
        source cells are about two hundred pixels wide, so a symbol drawn to
        within a few pixels of its cell leaves a faint halo on the edge once
        it is reduced to thirty-two - that is the resampling, not a bad crop.
        Ink that is more than half opaque out there is a symbol that has
        genuinely run off.
        """
        for name, index in sorted(self.indices.items(), key=lambda p: p[1]):
            with self.subTest(perk=name, index=index):
                alpha = self.cell(index)[:, :, 3]
                for side, strip in (("top", alpha[0]), ("bottom", alpha[-1]),
                                    ("left", alpha[:, 0]),
                                    ("right", alpha[:, -1])):
                    self.assertEqual(0, int((strip > 128).sum()),
                                     "%s runs off its %s edge" % (name, side))

    def test_the_cells_nothing_is_drawn_for_are_empty(self) -> None:
        used = set(self.indices.values())
        for index in range(COLUMNS * COLUMNS):
            if index not in used:
                with self.subTest(index=index):
                    self.assertEqual(0, self.cell(index)[:, :, 3].max())

    def test_the_table_is_a_dense_run_from_zero(self) -> None:
        self.assertEqual(sorted(self.indices.values()),
                         list(range(len(self.indices))))

    def test_every_perk_the_server_documents_has_an_emblem(self) -> None:
        """The encyclopedia's perk pages are generated from the server's own
        perk table, so they are the closest thing this repo has to the list
        the catalogue packet will carry. A perk added there and not here shows
        up as a row with a hole where its emblem should be."""
        document = json.loads(
            (CLIENT / "data" / "reference" / "encyclopedia.json")
            .read_text(encoding="utf-8"))
        perks = [category for category in document["categories"]
                 if category["id"] == "perks"][0]
        for entry in perks["entries"]:
            title = str(entry["title"])
            if not entry["id"].startswith("perk-") or title[0].islower():
                continue  # "How perks work" is a page, not a perk.
            with self.subTest(perk=title):
                self.assertIn(title.lower(), self.indices)


if __name__ == "__main__":
    unittest.main()
