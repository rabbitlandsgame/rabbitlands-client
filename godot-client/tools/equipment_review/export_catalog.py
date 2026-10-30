"""Refresh the previewer's public item facts from the authored server catalog.

Only item definitions are read. No server settings, player records or private
authoring records are exported. Run from any directory with --server PATH.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

CLIENT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).with_name("item_catalog.json")


def build_catalog(server: Path, client: Path = CLIENT) -> dict:
    sys.path.insert(0, str(server.resolve()))
    from eloria.items import load_items, equipment_visual, offhand_visual

    source = server / "config/eloria/items.txt"
    registry = json.loads((client / "data/actors/equipment.json").read_text(encoding="utf-8"))
    models = registry["models"]
    aliases = json.loads((client / "data/items/display_names.json").read_text(encoding="utf-8"))["names"]
    items = load_items(source)
    degraded = {item.degrades_to for item in items.values() if item.degrades_to}
    entries = []
    for item in sorted(items.values(), key=lambda item: item.item_id):
        visual = equipment_visual(item)
        if visual is None:
            continue
        visuals = [visual]
        offhand = offhand_visual(item)
        if offhand is not None and item.equip_type == "right_hand":
            visuals.append((1, offhand))
        for part, number in visuals:
            key = f"{part}:{number}"
            # The previewer only offers models registered in this client.
            if key not in models:
                continue
            stats = dict(item.stats)
            stats["weight_emu"] = item.emu
            if item.missile_speed:
                stats["missile_speed"] = item.missile_speed
            entries.append({
                "id": f"item:{item.item_id}:{part}", "item_id": item.item_id,
                "name": aliases.get(item.name, item.name), "canonical_name": item.name,
                "image_id": item.image_id, "key": key, "part": part, "visual": number,
                "description": item.description, "stats": stats,
                "effects": [asdict(effect) for effect in item.effects],
                "equip_type": item.equip_type, "worn": item.name in degraded,
                "degrades_to": aliases.get(item.degrades_to, item.degrades_to),
                "wear_chance": item.wear_chance, "obtainable": item.obtainable,
            })
    return {"schema": 1, "source": "Rabbit Lands authored item definitions",
            "items_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "items": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build_catalog(args.server), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != text:
            raise SystemExit("Preview item catalog needs refreshing")
        print("Preview item catalog is current")
    else:
        args.output.write_bytes(text.encode("utf-8"))
        print(f"Exported {len(json.loads(text)['items'])} item/slot choices to {args.output}")


if __name__ == "__main__":
    main()
