#!/usr/bin/env python3
"""Contract checks for the Godot-specific HUD action icon atlases."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "godot-client" / "assets" / "ui"
CELL_SIZE = 32
ICON_COUNT = 25


class HudIconAtlasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.active = np.asarray(
            Image.open(UI / "eloria_gamebuttons.png").convert("RGBA"))
        self.inactive = np.asarray(
            Image.open(UI / "eloria_gamebuttons_inactive.png").convert("RGBA"))

    def cell(self, image: np.ndarray, index: int) -> np.ndarray:
        row, column = divmod(index, 8)
        return image[row * CELL_SIZE:(row + 1) * CELL_SIZE,
                     column * CELL_SIZE:(column + 1) * CELL_SIZE]

    def test_atlases_keep_the_runtime_dimensions(self) -> None:
        self.assertEqual((256, 256, 4), self.active.shape)
        self.assertEqual(self.active.shape, self.inactive.shape)

    def test_every_runtime_icon_is_a_complete_independent_cell(self) -> None:
        for index in range(ICON_COUNT):
            with self.subTest(index=index):
                cell = self.cell(self.active, index)
                self.assertGreater((cell[:, :, 3] > 8).mean(), .98)
                self.assertGreater(len(np.unique(cell.reshape(-1, 4), axis=0)), 80)

    def test_unused_cells_are_transparent(self) -> None:
        for index in range(ICON_COUNT, 64):
            with self.subTest(index=index):
                self.assertEqual(0, self.cell(self.active, index)[:, :, 3].max())

    def test_inactive_atlas_preserves_shapes_without_reusing_active_colours(self) -> None:
        self.assertTrue(np.array_equal(self.active[:, :, 3], self.inactive[:, :, 3]))
        self.assertFalse(np.array_equal(self.active[:, :, :3], self.inactive[:, :, :3]))


if __name__ == "__main__":
    unittest.main()
