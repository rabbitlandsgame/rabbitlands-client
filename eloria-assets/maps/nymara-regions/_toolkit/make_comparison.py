#!/usr/bin/env python3
"""Build the concept-to-client comparison sheets and report."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFile

# Every region package except Amberwood and Sunmane ships a detail board
# truncated to 786,446 bytes, of which only the top row of five panels decodes.
# Allow the partial decode so the sheet can still be built, and mark the panels
# that are not really there rather than presenting grey as a comparison.
ImageFile.LOAD_TRUNCATED_IMAGES = True

import regionpaths

HERE = Path(__file__).resolve().parent
PACKAGE = regionpaths.package_root()
# Prefer real client frames when the package has them: a sheet captioned "the
# build" should show what the engine draws, not the authoring preview.
_GODOT = PACKAGE / "references" / "godot-captures"
_OFFLINE = PACKAGE / "references" / "captures"
def _has_frames(directory: Path) -> bool:
    # Both extensions: compress_captures.py converts these to WebP, and
    # globbing only for PNG silently falls back to the offline set the moment
    # the package is compressed.
    return directory.is_dir() and any(
        path for suffix in ("*.png", "*.webp") for path in directory.glob(suffix))


CAPTURES = _GODOT if _has_frames(_GODOT) else _OFFLINE
# Name the region on the sheet itself: these get looked at detached from the
# directory they came out of, and "build" alone does not say whose.
REGION = PACKAGE.name
BUILD_LABEL = (f"{REGION} build, real Godot frame" if CAPTURES is _GODOT
               else f"{REGION} build, offline preview renderer")
BOARD = PACKAGE / "references" / "00-concept-detail-board.png"
AERIAL = PACKAGE / "references" / "01-concept-aerial-overview.png"
OUT = PACKAGE / "references" / "comparisons"
PANELS = regionpaths.load_region_views(PACKAGE).PANELS



def _label(image: Image.Image, text: str, height: int = 26) -> Image.Image:
    out = Image.new("RGB", (image.width, image.height + height), (16, 16, 18))
    out.paste(image, (0, height))
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    draw.text((8, 5), text, fill=(226, 214, 190), font=font)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    board = Image.open(BOARD).convert("RGB")
    panel_w = board.width // 5
    panel_h = board.height // 2

    cell = (560, 380)

    def _decoded_rows(image: Image.Image) -> int:
        """How many rows of a panel the truncated board actually supplied.

        Beyond the truncation the decoder emits uniform rows, so the last row
        with any variation is where the real image stops.
        """
        grey = image.convert("L")
        width, height = grey.size
        last = 0
        for y in range(height):
            row = grey.crop((0, y, width, y + 1)).getextrema()
            if row[1] - row[0] > 6:
                last = y + 1
        return last

    rows = []
    for number in range(1, 11):
        column = (number - 1) % 5
        row = 0 if number <= 5 else 1
        concept = board.crop((column * panel_w, row * panel_h,
                              (column + 1) * panel_w, (row + 1) * panel_h))
        concept = concept.resize(cell, Image.LANCZOS)
        name, caption = PANELS[number]
        capture_path = CAPTURES / f"{name}.png"
        if not capture_path.exists():
            capture_path = CAPTURES / f"{name}.webp"
        if capture_path.exists():
            capture = Image.open(capture_path).convert("RGB")
            capture = capture.resize(cell, Image.LANCZOS)
        else:
            capture = Image.new("RGB", cell, (40, 30, 24))
        raw = board.crop((column * panel_w, row * panel_h,
                          (column + 1) * panel_w, (row + 1) * panel_h))
        decoded = _decoded_rows(raw)
        fraction = decoded / max(raw.height, 1)
        if fraction < 0.02:
            note = "concept UNAVAILABLE - board truncated"
            concept = Image.new("RGB", cell, (34, 34, 38))
            ImageDraw.Draw(concept).text(
                (14, cell[1] // 2 - 6),
                "this panel is not in the repository", fill=(190, 150, 90))
        elif fraction < 0.9:
            # show only what decoded, scaled to fit, rather than a strip of
            # picture over a field of black that reads as empty concept art
            note = f"concept {fraction * 100:.0f}% decoded - board truncated"
            strip = raw.crop((0, 0, raw.width, decoded))
            scaled_h = max(1, min(cell[1], int(cell[0] * strip.height / strip.width)))
            strip = strip.resize((cell[0], scaled_h), Image.LANCZOS)
            concept = Image.new("RGB", cell, (34, 34, 38))
            concept.paste(strip, (0, (cell[1] - scaled_h) // 2))
        else:
            note = "concept"
        pair = Image.new("RGB", (cell[0] * 2 + 12, cell[1]), (16, 16, 18))
        pair.paste(concept, (0, 0))
        pair.paste(capture, (cell[0] + 12, 0))
        rows.append(_label(pair, f"Panel {number} - {caption}   "
                                 f"[left: {note} | right: {BUILD_LABEL}]"))

    sheet_height = sum(r.height + 8 for r in rows)
    sheet = Image.new("RGB", (rows[0].width, sheet_height), (10, 10, 12))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 8
    sheet.save(OUT / "panel-comparison.png")
    sheet.convert("RGB").save(OUT / "panel-comparison.webp", "WEBP", quality=88, method=5)
    (OUT / "panel-comparison.png").unlink()

    # aerial pair
    aerial_concept = Image.open(AERIAL).convert("RGB")
    aerial_name = CAPTURES / "00-aerial-overview.png"
    if not aerial_name.exists():
        aerial_name = CAPTURES / "00-aerial-overview.webp"
    aerial_capture = Image.open(aerial_name).convert("RGB")
    width = 900
    a = aerial_concept.resize((width, int(width * aerial_concept.height
                                          / aerial_concept.width)), Image.LANCZOS)
    b = aerial_capture.resize((width, int(width * aerial_capture.height
                                          / aerial_capture.width)), Image.LANCZOS)
    pair = Image.new("RGB", (width, a.height + b.height + 12), (10, 10, 12))
    pair.paste(a, (0, 0))
    pair.paste(b, (0, a.height + 12))
    _label(pair, f"Aerial overview  [top: concept | bottom: {BUILD_LABEL}]").save(
        OUT / "aerial-comparison.png")
    Image.open(OUT / "aerial-comparison.png").convert("RGB").save(
        OUT / "aerial-comparison.webp", "WEBP", quality=88, method=5)
    (OUT / "aerial-comparison.png").unlink()

    # contact sheet of everything else
    # The index describes the *cameras*, and both capture sets are shot from
    # the same ones - `godot_capture.gd` reads this very file to place them -
    # so a Godot set with no index of its own falls back to the offline one
    # rather than failing with a FileNotFoundError.
    index_path = CAPTURES / "index.json"
    if not index_path.is_file():
        index_path = _OFFLINE / "index.json"
    index = json.loads(index_path.read_text())
    extras = [entry for entry in index if entry["panel"] is None]
    cols = 3
    thumb = (420, 280)
    sheet2 = Image.new("RGB", (cols * thumb[0], ((len(extras) + cols - 1) // cols)
                               * (thumb[1] + 24)), (10, 10, 12))
    for i, entry in enumerate(extras):
        path = CAPTURES / entry["file"]
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB")
        image.thumbnail(thumb)
        tile = _label(image, f"{REGION}  {entry['id']}", 22)
        sheet2.paste(tile, ((i % cols) * thumb[0], (i // cols) * (thumb[1] + 24)))
    sheet2.convert("RGB").save(OUT / "landmark-contact-sheet.webp", "WEBP",
                               quality=86, method=5)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
