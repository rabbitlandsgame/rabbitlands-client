"""Standalone cover IDs must not change or extend the painted atlas grid."""
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
from build_item_icon_atlases import planned_atlases


def test_book_custom_icons_leave_the_painted_atlases_unchanged():
    config = json.loads((ROOT / "godot-client/data/items/atlases.json").read_bytes())
    covers = {int(key): value for key, value in config["customIcons"].items()
              if "/books/" in value}
    assert len(covers) == 9
    assert min(covers) >= config["imageCount"]
    for path in covers.values():
        assert (ROOT / "godot-client" / path.removeprefix("res://")).is_file()
    planned = planned_atlases()
    assert len(planned) == len(config["atlases"])
    for path, image in planned:
        assert image.tobytes() == Image.open(path).convert("RGBA").tobytes()
