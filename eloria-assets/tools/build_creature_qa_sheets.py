#!/usr/bin/env python3
"""Regenerate the creature QA evidence: model renders beside their concept art.

Three sheets are produced, each with a machine-readable manifest alongside it:

``roster_concept_comparison``    every creature in ``creature_roster.py``.
``creature_concept_comparison``  the original native creatures, against the
                                 concept cells they were authored from.
``elemental_concept_comparison`` the amorphous elementals, which need the
                                 alpha-blended render path.

The pairings for the latter two live in the existing manifests, so the tool is
re-runnable: it reads them, re-renders, and writes them back.

    ELORIA_CONCEPT_DIR=/path/to/sheets \\
        python3 eloria-assets/tools/build_creature_qa_sheets.py
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from PIL import Image, ImageDraw, ImageFont

import concept_figures as CF
import creature_roster as RO
import render_creature_qa as R

REPO = HERE.parents[1]
QA = REPO / "eloria-assets/qa/creatures"
GLBS = REPO / "godot-client/assets/actors/native/creatures"
CONCEPTS = Path(os.environ.get("ELORIA_CONCEPT_DIR", "concept-art"))
TILE = 176
YAW, PITCH = 34.0, 14.0
FONT = ImageFont.load_default(size=11)


def sheet_image(stem: str) -> Image.Image:
    for name in (f"{stem}-image.png", f"{stem}.png", stem):
        candidate = CONCEPTS / name
        if candidate.exists():
            return Image.open(candidate)
    raise FileNotFoundError(f"no concept sheet for {stem} under {CONCEPTS}")


def boxes_for(stems) -> dict:
    """Figure bounding boxes per sheet, from the segmenting indexer.

    Only needed when working from whole sheets; the cut-figure delivery already
    carries the artist's bounds, and the segmenter cannot run without the
    sheets themselves.
    """
    if CF._root() is not None:
        return {}
    proc = subprocess.run([sys.executable, str(HERE / "concept_sheet_index.py"),
                           "--json"] + sorted(stems),
                          capture_output=True, text=True)
    return json.loads(proc.stdout)


def cut_figure(stem: str, row: int, col: int):
    """The artist's own cut figure for a cell, when that delivery is present."""
    root = CF._root()
    if root is None:
        return None
    directory = root / CF.SHEET_DIRS.get(stem, "")
    if not directory.is_dir():
        return None
    found = sorted(directory.glob(f"*__{row * 4 + col + 1:02d}__*.png"))
    if not found:
        return None
    image = Image.open(found[0])
    if image.mode == "RGBA":
        bounds = image.getchannel("A").point(
            lambda v: 255 if v > 12 else 0).getbbox()
        if bounds:
            image = image.crop(bounds)
    return image


def placeholder_tile(caption: str) -> Image.Image:
    """Stands in for a creature the supplied art has no figure for."""
    pad = Image.new("RGB", (TILE, TILE), (34, 30, 30))
    draw = ImageDraw.Draw(pad)
    draw.rectangle((6, 6, TILE - 7, TILE - 7), outline=(96, 78, 62))
    for y, line in enumerate(("no concept figure", "", caption)):
        draw.text((14, TILE // 2 - 16 + y * 14), line, fill=(168, 146, 120),
                  font=FONT)
    return pad


def concept_tile(stem: str, row: int, col: int, box=None) -> Image.Image:
    if stem not in RO.CONCEPT_SHEETS:
        return placeholder_tile("authored, not measured")
    # Prefer the cut figures: they are the artist's own bounds rather than a
    # segmentation guess, and they are what the fidelity pass was worked
    # against.  Segmenting a whole sheet stays as the fallback.
    crop = cut_figure(stem, row, col)
    if crop is None:
        im = sheet_image(stem)
        if box:
            crop = im.crop(tuple(box))
        else:                   # fall back to the nominal 4x3 grid
            cw, ch = im.width // 4, im.height // 3
            crop = im.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch))
    pad = Image.new("RGB", (TILE, TILE), (40, 44, 50))
    ratio = min(TILE / crop.width, TILE / crop.height)
    thumb = crop.resize((max(1, int(crop.width * ratio)),
                         max(1, int(crop.height * ratio))), Image.LANCZOS)
    pad.paste(thumb, ((TILE - thumb.width) // 2, (TILE - thumb.height) // 2),
              thumb if thumb.mode == "RGBA" else None)
    return pad


def compose(rows, cols=4):
    """rows: [(concept tile, glb path, caption)] -> a paired comparison sheet."""
    pair_w, pair_h = TILE * 2, TILE + 20
    tall = math.ceil(len(rows) / cols)
    canvas = Image.new("RGB", (pair_w * cols, pair_h * tall), (17, 20, 23))
    draw = ImageDraw.Draw(canvas)
    for i, (tile, glb, caption) in enumerate(rows):
        doc, binv = R.read_glb(glb)
        batches = R.gather(doc, binv)
        shot = R.render(batches, TILE, YAW, PITCH, R.model_bounds(batches))
        x, y = (i % cols) * pair_w, (i // cols) * pair_h
        canvas.paste(tile, (x, y))
        canvas.paste(shot, (x + TILE, y))
        draw.rectangle((x, y, x + pair_w - 1, y + TILE - 1), outline=(58, 66, 74))
        draw.text((x + 4, y + TILE + 4), caption, fill=(202, 212, 220), font=FONT)
    return canvas


def build_roster() -> None:
    entries = sorted(RO.ROSTER, key=lambda e: (RO.SHEET_LOCALES[e[7]], e[7], e[8], e[9]))
    boxes = boxes_for({e[7] for e in RO.ROSTER} & set(RO.CONCEPT_SHEETS))
    rows, manifest = [], []
    for slug, name, family, plan, _b, _a, _s, stem, row, col in entries:
        cell = boxes.get(stem, [])
        box = cell[row * 4 + col] if row * 4 + col < len(cell) else None
        glb = GLBS / f"{slug}.glb"
        rows.append((concept_tile(stem, row, col, box), glb,
                     f"{RO.SHEET_LOCALES[stem]}  {slug}"))
        manifest.append({"creature": slug, "name": name,
                         "locale": RO.SHEET_LOCALES[stem], "family": family,
                         "plan": plan,
                         "concept": {"sheet": stem, "cell": [row, col], "box": box},
                         "glb": str(glb.relative_to(REPO))})
    compose(rows).save(QA / "roster_concept_comparison.png", optimize=True)
    (QA / "roster_concept_comparison.json").write_text(json.dumps({
        "note": "Bind-pose renders of the checked-in GLBs beside the concept "
                "figure each creature was authored from. Concept crops are the "
                "artist's own cut figures where that delivery is available, "
                "resolved by concept_figures.py; otherwise the true figure "
                "bounds found by concept_sheet_index.py, never a uniform grid, "
                "so wings, antlers and tails are not clipped.",
        "renderer": "eloria-assets/tools/render_creature_qa.py",
        "index": "eloria-assets/tools/concept_figures.py",
        "view": {"yaw": YAW, "pitch": PITCH},
        "creatures": manifest}, indent=1) + "\n")
    print(f"roster sheet: {len(rows)} creatures")


def rebuild_manifest(name: str, key: str, sheet_of, cell_of, caption_of) -> None:
    path = QA / f"{name}.json"
    data = json.loads(path.read_text())
    records = data[key]
    stems = {sheet_of(r).removesuffix("-image.png") for r in records}
    boxes = boxes_for(stems)
    rows = []
    for record in records:
        stem = sheet_of(record).removesuffix("-image.png")
        row, col = cell_of(record)
        cell = boxes.get(stem, [])
        box = cell[row * 4 + col] if row * 4 + col < len(cell) else None
        rows.append((concept_tile(stem, row, col, box),
                     REPO / record["glb"], caption_of(record)))
    compose(rows).save(QA / f"{name}.png", optimize=True)
    path.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{name}: {len(rows)} creatures")


def main() -> None:
    QA.mkdir(parents=True, exist_ok=True)
    build_roster()
    rebuild_manifest("creature_concept_comparison", "pairs",
                     lambda r: r["conceptSheet"], lambda r: r["conceptCell"],
                     lambda r: f"{r['creature']}  <- {r['conceptSubject']}")
    rebuild_manifest("elemental_concept_comparison", "creatures",
                     lambda r: r["concept"]["sheet"], lambda r: r["concept"]["cell"],
                     lambda r: f"{r['creature']}  ({r['form']})")


if __name__ == "__main__":
    main()
