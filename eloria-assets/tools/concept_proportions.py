#!/usr/bin/env python3
"""Measure each concept figure's proportions so models inherit its silhouette.

Colour alone does not stop two creatures that share a body plan from being the
same model twice.  A wolf and a hyena are both ``canid``; in the art the hyena
is taller at the shoulder than the hip, thicker through the neck and shorter
in the leg, and none of that survives a shared plan.

Rather than hand-tune 139 silhouettes, this measures the segmented concept
figure and writes a small set of dimensionless ratios per creature:

``aspect``   figure height / width -- lanky versus squat.
``rake``     mean width of the upper third / the lower third -- top-heavy
             (hunched, broad-shouldered) versus bottom-heavy (skirted, squat).
``bulk``     filled fraction of the figure's bounding box -- solid versus
             spindly.
``taper``    width at 15% height / width at 85% height, along the figure.

Each is normalised against the median of every creature that shares the same
body plan, so the numbers say *how this creature differs from its plan-mates*
and can be applied as multipliers without re-tuning the plans themselves.

    ELORIA_CONCEPT_DIR=/path/to/sheets \\
        python3 eloria-assets/tools/concept_proportions.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from scipy import ndimage

import creature_roster as RO

U = Path(os.environ.get("ELORIA_CONCEPT_DIR", "concept-art"))
os.environ["ELORIA_CONCEPT_DIR"] = str(U)
HERE = Path(__file__).resolve().parent


def _boxes():
    sheets = sorted({e[7] for e in RO.ROSTER} & set(RO.CONCEPT_SHEETS))
    proc = subprocess.run([sys.executable, str(HERE / "concept_sheet_index.py"),
                           "--json"] + sheets, capture_output=True, text=True)
    return json.loads(proc.stdout)


def silhouette(boxes, stem, row, col):
    """A boolean figure mask for one concept cell."""
    im = Image.open(U / f"{stem}-image.png")
    arr = np.asarray(im.crop(tuple(boxes[stem][row * 4 + col])).convert("RGBA"),
                     dtype=float)
    rgb, alpha = arr[..., :3], arr[..., 3]
    if alpha.min() < 250:
        mask = alpha > 60
    else:
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        mask = np.linalg.norm(rgb - np.median(border, axis=0), axis=-1) > 40
    mask = ndimage.binary_opening(mask, np.ones((3, 3)))
    mask = ndimage.binary_closing(mask, np.ones((5, 5)))
    labels, count = ndimage.label(mask)
    if count > 1:
        sizes = ndimage.sum(mask, labels, range(1, count + 1))
        mask = labels == (int(np.argmax(sizes)) + 1)
    return mask


def measure(mask) -> dict | None:
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if len(rows) < 12 or len(cols) < 12:
        return None
    mask = mask[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    height, width = mask.shape
    per_row = mask.sum(axis=1).astype(float)
    third = max(height // 3, 1)
    upper = per_row[:third].mean()
    lower = per_row[-third:].mean()

    def band(frac):
        i = min(max(int(height * frac), 0), height - 1)
        lo = max(i - max(height // 40, 1), 0)
        hi = min(i + max(height // 40, 1) + 1, height)
        return max(per_row[lo:hi].mean(), 1.0)

    return {
        "aspect": height / max(width, 1),
        "rake": upper / max(lower, 1.0),
        "bulk": float(mask.sum()) / float(height * width),
        "taper": band(.15) / band(.85),
    }


KEYS = ("aspect", "rake", "bulk", "taper")


def main() -> None:
    boxes = _boxes()
    raw: dict[str, dict] = {}
    for slug, _, family, plan, *_rest, stem, row, col in RO.ROSTER:
        try:
            m = measure(silhouette(boxes, stem, row, col))
        except Exception:
            m = None
        if m:
            raw[slug] = m | {"plan": f"{family}:{plan}"}
    # Normalise against plan-mates: the useful signal is how a creature differs
    # from the others built on the same plan, not its absolute pixel size.
    groups: dict[str, list[str]] = {}
    for slug, m in raw.items():
        groups.setdefault(m["plan"], []).append(slug)
    out: dict[str, dict] = {}
    for plan, slugs in groups.items():
        for key in KEYS:
            values = np.array([raw[s][key] for s in slugs], dtype=float)
            median = float(np.median(values)) or 1.0
            for slug, value in zip(slugs, values):
                # Clamp: the art is stylised and a single odd crop should nudge
                # a model, never deform it.
                ratio = float(np.clip(value / median, .70, 1.42))
                out.setdefault(slug, {})[key] = round(ratio, 4)
    Path(os.environ.get("ELORIA_PROPORTIONS_OUT",
                        HERE / "concept_proportions.json")).write_text(
        json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    print(f"measured {len(out)} concept figures across {len(groups)} body plans")


if __name__ == "__main__":
    main()
