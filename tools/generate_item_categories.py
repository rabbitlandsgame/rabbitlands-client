"""Export public item names, storage categories and book subjects for shops."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "godot-client/data/items/categories.json")
    args = parser.parse_args()
    sys.path.insert(0, str(args.server_root.resolve()))
    from eloria.items import load_items
    from eloria.book_types import book_type

    source = args.server_root / "config/eloria/items.txt"
    items = load_items(source)
    document = {
        "schemaVersion": 1,
        "itemsSha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "categories": {name: item.category for name, item in sorted(items.items())},
        "bookTypes": {name: book_type(name) for name in sorted(items) if book_type(name)},
    }
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
