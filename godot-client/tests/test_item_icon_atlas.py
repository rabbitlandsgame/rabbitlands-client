#!/usr/bin/env python3
"""Grid and coverage checks for the inventory item icon atlases.

Added 2026-08-28 for Eloria Client.

``ItemAtlas`` slices every icon at ``(id % columns) * cell, (id / columns) *
cell``.  The shipped atlases were pasted below that grid, so icons from id 25
upwards rendered with a slice of their neighbour, and the sixteen Nymara
materials were flat placeholder polygons.  These tests pin the grid, the icon
coverage and the fallback so a future atlas edit cannot silently drift again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest

# Item IDs remain frozen, while the public painting manifest now owns the art.
# Routine atlas checks must not depend on ignored model-generation inputs.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                       / "eloria-assets" / "tools"))
FIRST_GENERATED_IMAGE_ID = 118


def generated_piece_count() -> int:
    manifest = json.loads((ROOT / "eloria-assets/source/item-icons/"
                           "painted-2026-10-18/manifest.json").read_text())
    return sum(record["imageId"] >= FIRST_GENERATED_IMAGE_ID
               for record in manifest["items"])

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"

# The unframed backing must remain opaque along every sampling-grid edge.
FRAME_BAND = 6
FIRST_NYMARA_IMAGE_ID = 85


def read_png(path: Path):
    from PIL import Image
    import numpy as np
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.int16)


class ItemIconAtlasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((CLIENT / "data/items/atlases.json").read_text())
        cls.cell = int(cls.config["cellSize"][0])
        cls.columns = int(cls.config["columns"])
        cls.per_atlas = int(cls.config["imagesPerAtlas"])
        cls.atlases = [read_png(CLIENT / path.removeprefix("res://"))
                       for path in cls.config["atlases"]]

    def cell_for(self, image_id: int):
        atlas, local = divmod(image_id, self.per_atlas)
        row, column = divmod(local, self.columns)
        return self.atlases[atlas][row * self.cell:(row + 1) * self.cell,
                                   column * self.cell:(column + 1) * self.cell]

    def test_item_art_has_no_decorative_corner_frame(self) -> None:
        import numpy as np
        background = np.array([5, 15, 18, 255])
        for image_id in range(self.config["imageCount"]):
            cell = self.cell_for(image_id)
            edges = np.concatenate((cell[:3].reshape(-1, 4),
                                    cell[-3:].reshape(-1, 4),
                                    cell[:, :3].reshape(-1, 4),
                                    cell[:, -3:].reshape(-1, 4)))
            with self.subTest(image_id=image_id):
                self.assertTrue(np.all(edges == background),
                                "icon decorations still reach the grid perimeter")

    def test_complete_painted_equipment_no_longer_uses_legacy_substitutes(self) -> None:
        manifest = json.loads((ROOT / "eloria-assets/source/item-icons/"
                               "painted-2026-10-18/manifest.json").read_text())
        records = {record["imageId"]: record for record in manifest["items"]}
        self.assertFalse(self.config["aliases"])
        equipment_ids = set(range(118, 474)) | set(range(506, 570)) | set(range(576, 584))
        self.assertEqual(428, len(equipment_ids))
        for image_id in sorted(equipment_ids):
            with self.subTest(image_id=image_id):
                self.assertEqual("equipment-concept-cutout",
                                 records[image_id]["sourceKind"])
        self.assertEqual("Knightly Boar Spear", records[397]["name"])
        self.assertEqual("Circular Ringblade", records[460]["name"])

    def test_atlas_declares_its_painted_range(self) -> None:
        # The public paintings cover the same contiguous IDs as the registry.
        self.assertEqual(FIRST_GENERATED_IMAGE_ID + generated_piece_count(),
                         self.config["imageCount"])
        self.assertEqual(117, self.config["fallbackImageId"])
        capacity = len(self.config["atlases"]) * self.per_atlas
        self.assertLessEqual(self.config["imageCount"], capacity)

    def test_every_declared_icon_is_painted(self) -> None:
        for image_id in range(self.config["imageCount"]):
            with self.subTest(image_id=image_id):
                cell = self.cell_for(image_id)
                opaque = (cell[:, :, 3] > 8).mean()
                self.assertGreater(opaque, .90,
                                   f"image {image_id} is not a painted cell")

    def test_icons_sit_on_the_sampling_grid(self) -> None:
        """A misaligned paste shows as a transparent or black band at one edge.

        Each icon's plate reaches its own cell border on every side, so any
        residual offset leaves a dead strip this catches.
        """
        band = FRAME_BAND
        for image_id in range(self.config["imageCount"]):
            cell = self.cell_for(image_id)
            alpha = cell[:, :, 3]
            edges = {
                "top": alpha[:band].mean(), "bottom": alpha[-band:].mean(),
                "left": alpha[:, :band].mean(), "right": alpha[:, -band:].mean()}
            for edge, value in edges.items():
                with self.subTest(image_id=image_id, edge=edge):
                    self.assertGreater(value, 200,
                                       f"image {image_id} has a dead {edge} edge")

    def test_nymara_materials_are_no_longer_flat_placeholders(self) -> None:
        """The placeholders were single-colour polygons on an empty cell."""
        import numpy as np
        for image_id in range(FIRST_NYMARA_IMAGE_ID, self.config["fallbackImageId"]):
            cell = self.cell_for(image_id)
            with self.subTest(image_id=image_id):
                colours = len(np.unique(cell.reshape(-1, 4), axis=0))
                self.assertGreater(colours, 600,
                                   f"image {image_id} is still flat art")

    def test_every_declared_atlas_ships(self) -> None:
        """The PNGs are the atlas source; nothing authors them elsewhere.

        They used to be checked against DDS twins under `eloria-assets/ui`,
        which existed only for the retired C client. With those gone the
        shipped PNG is the art, so what is left to hold is that every path
        `atlases.json` declares actually resolves to one.
        """
        for path in self.config["atlases"]:
            with self.subTest(atlas=path):
                self.assertTrue((CLIENT / path.removeprefix("res://")).is_file())

    def test_the_island_crops_take_the_icons_after_the_distillates(self) -> None:
        """Olive and Lemon are 594 and 595, the ids the server's items name.

        The crops are the one set whose items the client does not define:
        the server appends Olive and Lemon to items.txt with these image ids,
        so they are pinned here rather than only counted. Grapes and Cabbage
        (596, 597) followed for Landfall's farms, and Rosemary (598), whose
        old item borrowed Sage's cell 101 until it was released for Landfall.
        """
        import numpy as np
        import crop_icons
        import potion_icons
        crops = {crop.name: crop.image_id for crop in crop_icons.roster()}
        self.assertEqual(crops, {"Olive": 594, "Lemon": 595, "Grapes": 596,
                                 "Cabbage": 597, "Rosemary": 598})
        self.assertEqual(min(crops.values()),
                         max(p.image_id for p in potion_icons.roster()) + 1)
        # The potion shelf writes item ids into the server's fence; a
        # distillate appended after Magic Distillate would have been handed
        # 1860 and icon 594, the crops' own. It continues after them now,
        # and after Grapes and Cabbage's items (1892-1893), which follow the
        # spell tomes, and after the Watch Arming Sword the server gave 1894.
        potions = potion_icons.roster()
        self.assertEqual(sum(p.image_id < min(crops.values()) for p in potions),
                         potion_icons.SHELF_BEFORE_CROPS)
        self.assertEqual(potion_icons.AFTER_CROPS_IMAGE_ID, max(crops.values()) + 1)
        self.assertEqual(potion_icons.AFTER_CROPS_ITEM_ID, 1895)
        self.assertGreater(potion_icons.AFTER_CROPS_ITEM_ID,
                           max(crop_icons.SERVER_ITEM_IDS.values()))
        self.assertEqual(set(crop_icons.SERVER_ITEM_IDS), set(crops))
        self.assertFalse({p.item_id for p in potions} & set(crop_icons.SERVER_ITEM_IDS.values()))
        background = np.array([5, 15, 18, 255])
        for name, image_id in crops.items():
            with self.subTest(crop=name):
                self.assertLess(image_id, self.config["imageCount"])
                changed = (np.abs(self.cell_for(image_id) - background).max(axis=2) > 24).mean()
                self.assertGreater(changed, .12)

    def test_the_potion_shelf_refuses_ids_another_item_holds(self) -> None:
        """The shelf's ids are frozen by roster order, so the server can take
        one first (the Watch Arming Sword took 1894 before any bottle did).
        Rows inside the tool's own fence are its own and never collide."""
        import potion_icons
        potions = potion_icons.roster()
        first = potions[0]
        fenced = "\n".join([potion_icons.OPEN_ITEMS,
                            "item_id: %d" % first.item_id,
                            "image_id: %d" % first.image_id,
                            potion_icons.CLOSE_ITEMS])
        self.assertEqual(potion_icons.id_collisions(potions, fenced), [])
        foreign = "[item]\nname: Intruder\nitem_id: %d\nimage_id: %d\n[/item]\n" % (
            first.item_id, first.image_id)
        clashes = potion_icons.id_collisions(potions, foreign + fenced)
        self.assertIn("%s: item %d" % (first.name, first.item_id), clashes)
        self.assertIn("%s: icon %d" % (first.name, first.image_id), clashes)
        self.assertIn("next free outside the fence", clashes[-1])


if __name__ == "__main__":
    unittest.main()
