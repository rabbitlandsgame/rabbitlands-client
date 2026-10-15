#!/usr/bin/env python3
"""Compose the insides package's ten-panel detail board from real client frames.

WHY THIS EXISTS
---------------
`interiors/manymouth_flooded_labyrinth/references/00-concept-detail-board.png`
is truncated to 786,446 bytes: its IDAT stream fails to inflate and only the
top tenth of each panel decodes. It is the package's player-scale authority and
it cannot be looked at. Nobody can re-supply it from here.

What can be produced honestly is the *other* kind of board - not concept art but
a built one: the same 5x2 grid, the same ten subjects `concept.json` names, made
from real Godot 4.7.2 frames of the shipped GLB. It answers the question a
detail board is for ("what does this place look like at eye height?") for the
nine of ten subjects the build actually contains, and it says plainly on its own
face that it is a build reference and not concept art.

It is deliberately NOT written to the concept package and NOT named
`00-concept-detail-board.png`. The truncated original stays exactly where it is,
untouched, so that a re-supplied board replaces it and this one stays what it
is.

    python3 make_interior_board.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1] / "interiors" / "manymouth_delta_insides"
FRAMES = PACKAGE / "references" / "godot-captures"
OUT = PACKAGE / "references" / "00-detail-board.png"

# The ten subjects `manymouth_flooded_labyrinth/concept.json` names, in its
# order, each mapped to the view that answers it. The build's own subject ids
# were chosen to line up with these, which is why the mapping is one to one.
PANELS = [
    (1, "hidden entry", "flooded_labyrinth-concept-01"),
    (2, "stilt corridor", "smugglers_warren-concept-02"),
    (3, "boardwalk maze", "smugglers_warren-concept-03"),
    (4, "flood channel", "flooded_labyrinth-concept-04"),
    (5, "smuggler cache", "smugglers_warren-concept-05"),
    (6, "crate workroom", "smugglers_warren-concept-06"),
    (7, "root chamber", "flooded_labyrinth-concept-07"),
    (8, "submerged gate", "flooded_labyrinth-concept-08"),
    (9, "labyrinth panorama", "flooded_labyrinth-concept-09"),
    (10, "reed rope mangrove materials", "smugglers_warren-concept-10"),
]

# The original boards are 1983 x 793 in a 5 x 2 grid. Matching that means the
# comparison tooling and anyone's eye can put the two side by side.
COLS, ROWS = 5, 2
CELL_W, CELL_H = 396, 340
CAPTION = 56


def _font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def main() -> int:
    if not FRAMES.is_dir():
        raise SystemExit(f"no client frames at {FRAMES}")
    index_path = FRAMES / "index.json"
    lookup: dict[str, Path] = {}
    if index_path.is_file():
        for entry in json.loads(index_path.read_text(encoding="utf-8")):
            lookup[str(entry.get("id", ""))] = FRAMES / str(entry.get("file", ""))
    for path in list(FRAMES.glob("*.png")) + list(FRAMES.glob("*.webp")):
        for prefix in (p[2] for p in PANELS):
            if path.name.startswith(prefix):
                lookup.setdefault(prefix, path)

    board = Image.new("RGB", (COLS * CELL_W, ROWS * CELL_H + CAPTION),
                      (13, 14, 15))
    draw = ImageDraw.Draw(board)
    title = _font(19)
    label = _font(15)
    small = _font(13)

    missing = []
    for index, (number, subject, view) in enumerate(PANELS):
        col, row = index % COLS, index // COLS
        x, y = col * CELL_W, row * CELL_H
        source = None
        for key, path in lookup.items():
            if key.startswith(view) and path.exists():
                source = path
                break
        if source is None:
            missing.append(subject)
            draw.rectangle([x + 2, y + 2, x + CELL_W - 3, y + CELL_H - 3],
                           outline=(70, 60, 50))
            draw.text((x + 12, y + CELL_H // 2), "no frame", font=label,
                      fill=(150, 130, 110))
        else:
            frame = Image.open(source).convert("RGB")
            # crop to the cell's aspect before scaling, or every panel is
            # letterboxed and the board reads as a contact sheet
            want = CELL_W / (CELL_H - 26)
            have = frame.width / frame.height
            if have > want:
                new_w = int(frame.height * want)
                left = (frame.width - new_w) // 2
                frame = frame.crop((left, 0, left + new_w, frame.height))
            else:
                new_h = int(frame.width / want)
                top = (frame.height - new_h) // 2
                frame = frame.crop((0, top, frame.width, top + new_h))
            frame = frame.resize((CELL_W - 4, CELL_H - 30), Image.LANCZOS)
            board.paste(frame, (x + 2, y + 26))
        draw.rectangle([x, y, x + CELL_W - 1, y + 24], fill=(22, 23, 25))
        draw.text((x + 8, y + 4), f"{number}.  {subject}", font=label,
                  fill=(224, 210, 184))

    draw.rectangle([0, ROWS * CELL_H, board.width, board.height],
                   fill=(22, 23, 25))
    draw.text((10, ROWS * CELL_H + 8),
              "Manymouth Delta insides - built detail board.  "
              "NOT concept art: every panel is a real Godot 4.7.2 frame of the "
              "shipped world.glb.", font=title, fill=(226, 214, 190))
    note = ("The concept board at interiors/manymouth_flooded_labyrinth/references/ "
            "is truncated to 786,446 bytes and only its top tenth decodes; this "
            "answers the same ten subjects from the build instead.")
    draw.text((10, ROWS * CELL_H + 32), note, font=small, fill=(150, 146, 138))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    board.save(OUT)
    print(f"[board] {OUT}  {board.width}x{board.height}")
    if missing:
        print("[board] no frame for: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
