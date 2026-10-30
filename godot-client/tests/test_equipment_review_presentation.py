"""Coverage and identity checks for the preview-only gear presentation."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "godot-client"
REVIEW = CLIENT / "tools/equipment_review"
sys.path.insert(0, str(REVIEW))
from gear_presentation import decorate_items


class EquipmentReviewPresentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((REVIEW / "item_catalog.json").read_text(encoding="utf-8"))
        cls.equipment = json.loads((CLIENT / "data/actors/equipment.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((REVIEW / "icons/manifest.json").read_text(encoding="utf-8"))

    def test_every_registered_visual_has_authored_presentation(self):
        self.assertEqual(set(self.equipment["models"]), set(self.catalog["visuals"]))
        self.assertEqual(64, len(self.catalog["sets"]))
        names = [style["name"].casefold() for style in self.catalog["sets"].values()]
        self.assertEqual(len(names), len(set(names)))

    def test_names_and_descriptions_cover_items_and_registry_only_pieces(self):
        pieces = self.catalog["items"] + list(self.catalog["visuals"].values())
        forbidden = ("concept", "generated from", "test environment")
        regions = ("amberwood", "sunmane", "four gates", "greyhaven", "glasswarden", "ssarathi", "bellwatch")
        for piece in pieces:
            with self.subTest(piece=piece["name"]):
                self.assertTrue(piece["name"].strip())
                self.assertGreater(len(piece["description"]), 50)
                self.assertFalse(any(word in piece["description"].casefold() for word in forbidden))
                self.assertFalse(any(word in piece["name"].casefold() for word in regions))
                if piece.get("set_name"):
                    self.assertTrue(piece["name"].startswith(piece["set_name"] + " "))
                    self.assertIn(piece["set_name"] + " set", piece["description"])

    def test_slot_choices_have_unique_names(self):
        by_part = defaultdict(list)
        known_keys = {piece["key"] for piece in self.catalog["items"]}
        for piece in self.catalog["items"]:
            by_part[piece["part"]].append(piece["name"].casefold())
        for key, piece in self.catalog["visuals"].items():
            if key not in known_keys:
                by_part[int(key.split(":")[0])].append(piece["name"].casefold())
        for part, names in by_part.items():
            self.assertEqual(len(names), len(set(names)), f"duplicate names in slot {part}")

    def test_presentation_preserves_item_identity_and_stats(self):
        aliases = json.loads((CLIENT / "data/items/display_names.json").read_text())["names"]
        items = deepcopy(self.catalog["items"])
        for item in items:
            item["name"] = aliases.get(item["canonical_name"], item["canonical_name"])
        fields = ("id", "item_id", "image_id", "key", "part", "visual", "stats", "effects", "equip_type", "worn")
        before = [{field: deepcopy(item[field]) for field in fields} for item in items]
        equipment_before = deepcopy(self.equipment)
        decorate_items(items, self.equipment)
        self.assertEqual(before, [{field: item[field] for field in fields} for item in items])
        self.assertEqual(equipment_before, self.equipment)

    def test_icons_cover_every_model_with_real_transparency_and_padding(self):
        self.assertFalse(self.manifest["failures"])
        self.assertEqual(set(self.equipment["models"]), set(self.manifest["icons"]))
        for key, record in self.manifest["icons"].items():
            with self.subTest(key=key):
                path = REVIEW / "icons" / record["file"]
                self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                with Image.open(path) as image:
                    self.assertEqual((512, 512), image.size)
                    self.assertEqual("RGBA", image.mode)
                    alpha = image.getchannel("A")
                    self.assertEqual((0, 255), alpha.getextrema())
                    bounds = alpha.getbbox()
                    self.assertIsNotNone(bounds)
                    self.assertGreaterEqual(min(bounds[0], bounds[1], 512 - bounds[2], 512 - bounds[3]), 8)
                    for band in ((0, 0, 512, 1), (0, 511, 512, 512), (0, 0, 1, 512), (511, 0, 512, 512)):
                        self.assertEqual((0, 0), alpha.crop(band).getextrema())

    def test_every_piece_uses_the_matching_component_render(self):
        for piece in self.catalog["items"]:
            self.assertEqual("res://tools/equipment_review/icons/" + piece["key"].replace(":", "_") + ".png", piece["icon"])
        for key, piece in self.catalog["visuals"].items():
            self.assertEqual("res://tools/equipment_review/icons/" + key.replace(":", "_") + ".png", piece["icon"])


if __name__ == "__main__":
    unittest.main()
