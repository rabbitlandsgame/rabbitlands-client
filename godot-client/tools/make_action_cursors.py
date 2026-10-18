#!/usr/bin/env python3
"""Validate and export the reviewed Rabbit Lands action cursor set.

The 32x32 RGBA PNGs in assets/ui/cursors are the published artwork. This
helper preserves their antialiasing, material shading and per-glyph hotspots;
it does not regenerate the retired 16x16 monochrome character maps.

Run from godot-client/: python tools/make_action_cursors.py [--out DIR]
    [--preview out.png]
Original generation sources and earlier takes remain in the ignored local
asset-authoring workspace. See docs/cursor-art.md in the client checkout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw

SOURCE = Path(__file__).resolve().parents[1] / "assets" / "ui" / "cursors"
ORDER = ("eye", "talk", "attack", "enter", "pick", "harvest", "walk", "arrow",
         "trade", "use_witem", "use", "wand", "text", "grab")


def build(out_dir: Path) -> dict:
    manifest = json.loads((SOURCE / "cursors.json").read_text(encoding="utf-8"))
    entries = manifest["cursors"]
    if tuple(e["name"] for e in entries) != ORDER:
        raise ValueError("Cursor names/order must match MouseCursors ids")
    for entry in entries:
        name = entry["name"]
        if entry["file"] != f"cursor_{name}.png":
            raise ValueError(f"{name}: unexpected cursor filename")
        with Image.open(SOURCE / entry["file"]) as image:
            if image.mode != "RGBA" or image.size != (32, 32):
                raise ValueError(f"{name}: expected a 32x32 RGBA cursor")
            if image.getchannel("A").getextrema() != (0, 255):
                raise ValueError(f"{name}: expected transparent and opaque pixels")
        hotspot = entry["hotspot"]
        if len(hotspot) != 2 or any(type(v) is not int or not 0 <= v < 32 for v in hotspot):
            raise ValueError(f"{name}: hotspot must be inside the cursor")
    if out_dir.resolve() != SOURCE.resolve():
        out_dir.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            shutil.copy2(SOURCE / entry["file"], out_dir / entry["file"])
        shutil.copy2(SOURCE / "cursors.json", out_dir / "cursors.json")
    return manifest


def preview(manifest: dict, out_dir: Path, path: Path, zoom: int = 4) -> None:
    """Show the actual cursor and enlarged pixel detail on light/dark panels."""
    cell = 144
    sheet = Image.new("RGB", (7 * cell, 2 * 212), (25, 32, 39))
    draw = ImageDraw.Draw(sheet)
    for index, entry in enumerate(manifest["cursors"]):
        x, y = (index % 7) * cell, (index // 7) * 212
        with Image.open(out_dir / entry["file"]) as image:
            image = image.convert("RGBA")
            for dx, color in ((8, (16, 32, 25)), (56, (221, 213, 189))):
                draw.rectangle((x+dx, y+8, x+dx+35, y+43), fill=color)
                sheet.paste(image, (x+dx+2, y+10), image)
            large = image.resize((32 * zoom, 32 * zoom), Image.Resampling.NEAREST)
            sheet.paste(large, (x+8, y+52), large)
        draw.text((x+8, y+188), entry["name"], fill=(241, 230, 210))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=SOURCE)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    manifest = build(args.out)
    if args.preview:
        preview(manifest, args.out, args.preview)
    print(f"validated {len(manifest['cursors'])} reviewed cursors in {args.out}")


if __name__ == "__main__":
    main()
