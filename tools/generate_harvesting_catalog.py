#!/usr/bin/env python3
"""Compile the served resource definitions for the encyclopedia.

Harvesting has no research-book gate in the server's start/harvest loop.
Keep that explicit instead of inferring manufacturing knowledge from an item.
The legacy `required_level` field is a recommendation used by harvest_interval,
not an unlock level. The configured `seconds` field is not used by that loop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="compare without writing")
    args = parser.parse_args()
    server = args.server_root.resolve()
    sys.path.insert(0, str(server))
    from eloria.harvesting import load_harvesting
    from eloria.items import ITEMS, configure_items

    profile = server / "config/eloria"
    harvesting = profile / "harvesting.txt"
    overlay = profile / "continent-v2/harvesting.txt"
    items = profile / "items.txt"
    configure_items(items)
    resources, _nodes = load_harvesting(harvesting, overlay=True)
    entries = []
    for name, resource in sorted(resources.items()):
        item = ITEMS[name]
        entries.append({
            "name": name,
            "imageId": item.image_id,
            "level": resource.required_level,
            "experience": resource.experience,
            "tool": resource.tool or "",
            "knowledge": "",
        })
    document = {
        "schemaVersion": 1,
        "sources": {
            "profile": "eloria",
            "harvestingSha256": digest(harvesting),
            "overlayHarvestingSha256": digest(overlay) if overlay.is_file() else "",
            "itemsSha256": digest(items),
        },
        "resources": entries,
    }
    if args.check:
        matches = json.loads(args.output.read_text(encoding="utf-8")) == document
        print(f"{'PASS' if matches else 'FAIL'} harvesting catalogue: {len(entries)} resources")
        return 0 if matches else 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(entries)} resources to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
