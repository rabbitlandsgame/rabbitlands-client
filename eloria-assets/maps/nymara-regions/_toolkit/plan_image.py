#!/usr/bin/env python3
"""Render a package's collision grid as a plan.

A top-down 3D shot of an interior photographs its ceilings, which is why the
plan overview of a lidded map comes back black. The collision grid is what a
plan actually wants to show: which cells are walkable, at what height, and -
for a multi-block map - how much dead ground lies between the blocks.

Walkable cells are shaded by their encoded height, low to high; blocked cells
are left as the background, so the void reads as void.

    python3 plan_image.py --package <dir> [--out <png>]
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

BACKGROUND = (12, 13, 17)
LOW = np.array([44, 58, 82], dtype=float)      # deepest walkable
HIGH = np.array([206, 220, 240], dtype=float)  # highest walkable


def render(package: Path, out: Path, scale: int = 2) -> dict:
    manifest = json.loads((package / "world.json").read_text())
    collision = manifest["collision"]
    width = int(collision["width"])
    height = int(collision["height"])
    raw = (package / str(collision.get("binary", "collision.bin"))).read_bytes()
    magic, _version, _reserved, w, h = struct.unpack_from("<4sHHII", raw, 0)
    if magic != b"EWCG" or (w, h) != (width, height):
        raise SystemExit(f"collision header does not match the manifest: {package}")
    grid = np.frombuffer(raw, dtype=np.uint8, offset=16,
                         count=width * height).reshape(height, width)

    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = BACKGROUND
    walkable = grid > 0
    if walkable.any():
        codes = grid[walkable].astype(float)
        lo, hi = codes.min(), codes.max()
        span = max(hi - lo, 1.0)
        t = ((codes - lo) / span)[:, None]
        image[walkable] = (LOW + (HIGH - LOW) * t).astype(np.uint8)

    picture = Image.fromarray(image, "RGB")
    if scale > 1:
        picture = picture.resize((width * scale, height * scale), Image.NEAREST)
    out.parent.mkdir(parents=True, exist_ok=True)
    picture.save(out)

    return {
        "file": out.name,
        "cells": [width, height],
        "cellMetres": float(collision.get("cellMetres", 0.5)),
        "walkableCells": int(walkable.sum()),
        "walkableFraction": round(float(walkable.mean()), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()
    package = Path(args.package).resolve()
    out = Path(args.out) if args.out else package / "references" / "plan.png"
    stats = render(package, out, args.scale)
    print(f"[plan] {stats['cells'][0]}x{stats['cells'][1]} cells, "
          f"{stats['walkableCells']} walkable "
          f"({stats['walkableFraction'] * 100:.1f}%) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
