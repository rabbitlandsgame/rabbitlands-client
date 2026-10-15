#!/usr/bin/env python3
"""Put a built creature next to the concept figure it is supposed to be.

This is the working tool for the fidelity pass: it renders the GLB from the
views that actually show disagreement (profile and three-quarter front) and
pastes them beside the artist's own cut figure at matched height, so silhouette
and proportion can be compared directly rather than described.

    ELORIA_CONCEPT_FIGURES=/path/to/cut/figures \
        python3 eloria-assets/tools/concept_compare.py amberwood_treant vine_treant

Writes one PNG per row of creatures under eloria-assets/qa/creatures/compare/
unless --output names a file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw, ImageFont

import concept_figures as CF
import render_creature_qa as R

REPO = HERE.parents[1]
GLBS = REPO / "godot-client/assets/actors/native/creatures"
OUT = REPO / "eloria-assets/qa/creatures/compare"
BG = (26, 29, 33)


def _fit(image: Image.Image, size: int, background=BG) -> Image.Image:
    """Letterbox onto a square tile, keeping the figure's own aspect."""
    pad = Image.new("RGB", (size, size), background)
    ratio = min(size / image.width, size / image.height)
    thumb = image.resize((max(1, int(image.width * ratio)),
                          max(1, int(image.height * ratio))), Image.LANCZOS)
    pad.paste(thumb, ((size - thumb.width) // 2, (size - thumb.height) // 2),
              thumb if thumb.mode == "RGBA" else None)
    return pad


def _trim(image: Image.Image) -> Image.Image:
    """Crop a cut figure to its own ink so it fills the tile like the render."""
    if image.mode != "RGBA":
        return image
    box = image.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox()
    return image.crop(box) if box else image


def row(slug: str, size: int, views) -> Image.Image:
    figure = CF.figure_path(slug)
    glb = GLBS / f"{slug}.glb"
    tiles, labels = [], []
    if figure is not None:
        tiles.append(_fit(_trim(Image.open(figure)), size))
        labels.append(f"art: {CF.subject_of(figure)}")
    if glb.exists():
        model = R.sheet(glb, size, list(views), None, None)
        tiles.append(model)
        labels.append("  |  ".join(views))
    if not tiles:
        raise SystemExit(f"{slug}: neither concept figure nor GLB found")
    width = sum(t.width for t in tiles)
    board = Image.new("RGB", (width, size + 34), BG)
    draw = ImageDraw.Draw(board)
    font = ImageFont.load_default(size=13)
    x = 0
    for tile, label in zip(tiles, labels):
        board.paste(tile, (x, 24))
        draw.text((x + 6, size + 26), label, fill=(150, 160, 170), font=font)
        x += tile.width
    draw.text((6, 5), slug.replace("_", " ").title(),
              fill=(238, 243, 247), font=ImageFont.load_default(size=15))
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="+")
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--views", default="profile,3q_front")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    views = [v.strip() for v in args.views.split(",") if v.strip() in R.VIEWS]
    rows = [row(slug, args.size, views) for slug in args.slugs]
    width = max(r.width for r in rows)
    board = Image.new("RGB", (width, sum(r.height for r in rows)), BG)
    y = 0
    for r_ in rows:
        board.paste(r_, (0, y))
        y += r_.height
    out = args.output or (OUT / f"{args.slugs[0]}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    print(f"wrote {out} ({board.width}x{board.height})")


if __name__ == "__main__":
    main()
