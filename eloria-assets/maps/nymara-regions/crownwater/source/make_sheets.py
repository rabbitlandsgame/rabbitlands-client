#!/usr/bin/env python3
"""Build Crownwater's concept-to-client comparison sheets.

WHY THIS IS NOT `_toolkit/make_comparison.py`
---------------------------------------------
The shared tool assumes `references/00-concept-detail-board.png` is a readable
ten-panel board and crops it into fifths. Crownwater's board is truncated - the
file is exactly 786,445 bytes and its zlib stream fails partway, so only the top
90 of 793 pixel rows decode. That is 11% of the image and not even the whole of
panel 1. Running the shared tool against it does not fail; it silently crops
garbage and presents it as concept art, which is worse than not building the
sheet at all.

So this builds the same sheets with one difference: where a concept panel cannot
be decoded, the concept half says so, in writing, with the panel's description
taken from `views.py`. Every claim on these sheets is one the files support.

The build halves are **real Godot client frames** captured by
`_toolkit/godot_capture.gd --environment=manifest`, not offline previews.
That is stated on every sheet, because it is the one thing about these captures
a reader would otherwise have to take on trust.
"""
from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFile, ImageFont

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(PACKAGE.parent / "_toolkit"))
sys.path.insert(0, str(HERE))

import views as VIEWTABLE  # noqa: E402

CAPTURES = PACKAGE / "references" / "godot-captures"
BOARD = PACKAGE / "references" / "00-concept-detail-board.png"
AERIAL = PACKAGE / "references" / "01-concept-aerial-overview.png"
OUT = PACKAGE / "references" / "comparisons"

INK = (232, 226, 214)
DIM = (150, 146, 138)
BG = (16, 17, 20)
WARN = (226, 176, 96)


def _font(size: int):
    for candidate in ("C:/Windows/Fonts/segoeui.ttf",
                      "C:/Windows/Fonts/arial.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def board_decoded_rows() -> int:
    """How many pixel rows of the detail board actually decode.

    Reported rather than assumed, so the sheets state a measured fact.
    """
    if not BOARD.is_file():
        return 0
    data = BOARD.read_bytes()
    index, idat = 8, b""
    while index < len(data) - 8:
        length = struct.unpack(">I", data[index:index + 4])[0]
        kind = data[index + 4:index + 8]
        if kind == b"IDAT":
            idat += data[index + 8:index + 8 + length]
        index += 12 + length
    try:
        zlib.decompress(idat)
        return -1                     # -1 means "fully decoded"
    except zlib.error:
        pass
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        import numpy as np
        array = np.asarray(Image.open(BOARD).convert("RGB"))
        rows = [y for y in range(array.shape[0]) if array[y].std() > 3.0]
        return (max(rows) + 1) if rows else 0
    except Exception:  # noqa: BLE001
        return 0


def _caption(image: Image.Image, text: str, sub: str = "",
             colour=INK) -> Image.Image:
    head = 30 if not sub else 50
    out = Image.new("RGB", (image.width, image.height + head), BG)
    out.paste(image, (0, head))
    draw = ImageDraw.Draw(out)
    draw.text((10, 6), text, fill=colour, font=_font(16))
    if sub:
        draw.text((10, 28), sub, fill=DIM, font=_font(13))
    return out


def _unavailable(size, number: int, description: str) -> Image.Image:
    """The concept half of a panel whose source pixels cannot be decoded."""
    tile = Image.new("RGB", size, (30, 26, 22))
    draw = ImageDraw.Draw(tile)
    draw.rectangle([6, 6, size[0] - 7, size[1] - 7], outline=(72, 62, 48))
    draw.text((22, 26), "concept panel %d unavailable" % number,
              fill=WARN, font=_font(19))
    draw.text((22, 56), "source PNG is truncated - see comparison-report.md",
              fill=DIM, font=_font(14))
    words, line, lines = description.split(), "", []
    for word in words:
        trial = (line + " " + word).strip()
        if len(trial) > 34:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    draw.text((22, 100), "described as:", fill=DIM, font=_font(13))
    for i, entry in enumerate(lines[:8]):
        draw.text((22, 122 + i * 22), entry, fill=INK, font=_font(15))
    return tile


def _load_capture(name: str, size):
    for suffix in (".png", ".webp"):
        path = CAPTURES / f"{name}{suffix}"
        if path.is_file():
            return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    tile = Image.new("RGB", size, (26, 26, 30))
    draw = ImageDraw.Draw(tile)
    draw.text((20, 20), f"capture missing: {name}", fill=WARN, font=_font(16))
    return tile


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    decoded = board_decoded_rows()
    board_ok = decoded == -1

    # ---- aerial: a genuine side-by-side --------------------------------
    cell = (760, 560)
    concept = Image.open(AERIAL).convert("RGB").resize(cell, Image.LANCZOS)
    build = _load_capture("00-aerial-overview", cell)
    sheet = Image.new("RGB", (cell[0] * 2 + 14, cell[1] + 50), BG)
    sheet.paste(_caption(concept, "Concept: crownwater_region_concept.png",
                         "composition authority, intact"), (0, 0))
    sheet.paste(_caption(build, "Build: real Godot 4.7.2 client frame",
                         "rendered_crownwater.gd, gl_compatibility"),
                (cell[0] + 14, 0))
    sheet.save(OUT / "aerial-comparison.webp", "WEBP", quality=88, method=5)

    # ---- the ten panels ------------------------------------------------
    cell = (560, 400)
    rows = []
    for number in range(1, 11):
        name, description = VIEWTABLE.PANELS[number]
        build = _load_capture(name, cell)
        if board_ok:
            board = Image.open(BOARD).convert("RGB")
            panel_w, panel_h = board.width // 5, board.height // 2
            column, row = (number - 1) % 5, 0 if number <= 5 else 1
            concept = board.crop((column * panel_w, row * panel_h,
                                  (column + 1) * panel_w,
                                  (row + 1) * panel_h)).resize(cell, Image.LANCZOS)
            concept = _caption(concept, f"Concept panel {number}", description)
        else:
            concept = _caption(_unavailable(cell, number, description),
                               f"Concept panel {number}: NOT AVAILABLE",
                               description, colour=WARN)
        build = _caption(build, f"Build: {name}",
                         "real Godot client frame")
        pair = Image.new("RGB", (cell[0] * 2 + 14, concept.height), BG)
        pair.paste(concept, (0, 0))
        pair.paste(build, (cell[0] + 14, 0))
        rows.append(pair)

    header_h = 64
    sheet = Image.new("RGB", (rows[0].width,
                              header_h + sum(r.height + 10 for r in rows)), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), "Crownwater - detail board panels versus build",
              fill=INK, font=_font(22))
    if board_ok:
        note = "Concept panels cropped from the supplied ten-panel board."
    else:
        note = ("Concept panels UNAVAILABLE: 00-concept-detail-board.png is "
                "truncated (%d of 793 rows decode). Build halves are real "
                "client frames." % max(decoded, 0))
    draw.text((12, 38), note, fill=WARN if not board_ok else DIM, font=_font(14))
    y = header_h
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + 10
    sheet.save(OUT / "panel-comparison.webp", "WEBP", quality=86, method=5)

    # ---- contact sheet of every client capture -------------------------
    names = [entry[0] for entry in VIEWTABLE.VIEWS]
    thumb = (400, 262)
    columns = 4
    rows_count = (len(names) + columns - 1) // columns
    contact = Image.new("RGB",
                        (columns * (thumb[0] + 8) + 8,
                         56 + rows_count * (thumb[1] + 34)), BG)
    draw = ImageDraw.Draw(contact)
    draw.text((12, 12), "Crownwater - all %d client captures" % len(names),
              fill=INK, font=_font(22))
    for index, name in enumerate(names):
        cx = 8 + (index % columns) * (thumb[0] + 8)
        cy = 56 + (index // columns) * (thumb[1] + 34)
        contact.paste(_load_capture(name, thumb), (cx, cy))
        draw.text((cx + 4, cy + thumb[1] + 6), name, fill=DIM, font=_font(13))
    contact.save(OUT / "capture-contact-sheet.webp", "WEBP", quality=84,
                 method=5)

    print(f"[sheets] board decoded rows: "
          f"{'all' if board_ok else max(decoded, 0)} of 793")
    print(f"[sheets] wrote {OUT / 'aerial-comparison.webp'}")
    print(f"[sheets] wrote {OUT / 'panel-comparison.webp'}")
    print(f"[sheets] wrote {OUT / 'capture-contact-sheet.webp'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
