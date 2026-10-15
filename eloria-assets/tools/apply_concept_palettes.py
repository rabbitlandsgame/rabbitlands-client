#!/usr/bin/env python3
"""Bake sampled concept-art palettes into the roster and the legacy table.

``extract_concept_palettes.py`` writes JSON; this rewrites the two source
tables in place so a palette pass is reproducible rather than hand-applied.

    ELORIA_PALETTE_OUT=palettes.json \
    ELORIA_PALETTE_OUT_LEGACY=palettes_legacy.json \
        python3 eloria-assets/tools/apply_concept_palettes.py
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RGB = r"\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)"


def fmt(c):
    return "({}, {}, {})".format(*(int(v) for v in c))


def bake(path: str, palettes: dict, pattern) -> int:
    text = (HERE / path).read_text()
    changed = 0
    for slug, (base, accent) in palettes.items():
        rx = re.compile(pattern(slug), re.S)
        match = rx.search(text)
        if not match:
            continue
        text = (text[:match.start(1)] + fmt(base) + ", " + fmt(accent)
                + text[match.end(2):])
        changed += 1
    (HERE / path).write_text(text)
    return changed


def main() -> None:
    roster = json.loads(Path(os.environ.get(
        "ELORIA_PALETTE_OUT", HERE / "palettes.json")).read_text())
    legacy = json.loads(Path(os.environ.get(
        "ELORIA_PALETTE_OUT_LEGACY", HERE / "palettes_legacy.json")).read_text())
    n = bake("creature_roster.py", roster,
             lambda s: rf'\("{re.escape(s)}",.*?({RGB}),\s*({RGB}),\s*[\d.]')
    m = bake("build_native_nymara_glbs.py", legacy,
             lambda s: rf'"{re.escape(s)}",\s*"[^"]*",\s*"[^"]*",\s*({RGB}),\s*({RGB}),')
    print(f"baked {n} roster palettes and {m} legacy palettes")


if __name__ == "__main__":
    main()
