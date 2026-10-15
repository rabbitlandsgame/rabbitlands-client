#!/usr/bin/env python3
"""Draw every map's minimap at one scale, and describe it one way.

Four families of map had grown four different answers to "how big is a metre
on the minimap": the ten Nymara regions at 1.336 px/m, Four Gates at 0.646,
the Sunmane steppe at 3.657 and the two Sunmane cave interiors at 8.533. They
also described it three different ways -- `pixelsPerMetre` against
`metresPerPixel`, `size` against `pixels` against `imageSize`, `image` against
`file` -- so no two of them could even be compared without a conversion.

Every minimap is now one pixel to the metre, which makes the image's pixel
dimensions the map's own size in metres and makes the two rival spellings of
the scale numerically identical: at 1.0 they are the same number, so the old
keys can stay alongside the new ones without saying anything different.

The scale is applied by resampling each packaged image, except Four Gates,
whose renderer now sizes its viewport from the geometry and was re-run: it is
the only map whose image had to grow, and an upscale would have invented
detail the map does not have.

Run: python3 eloria-assets/tools/unify_minimap_scale.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MAPS = ROOT / "eloria-assets" / "maps"

## One pixel, one metre, on every map in the world.
PIXELS_PER_METRE = 1.0
## What the packaged cartography is encoded as. Quality 92 sits within a few
## per cent of the sizes these files already had.
WEBP_QUALITY = 92

## Keys the old schemas used for the same facts. They are written alongside the
## canonical ones for one release so nothing reading them breaks; at a scale of
## 1.0 `metresPerPixel` and `pixelsPerMetre` carry the same number anyway.
LEGACY_ALIASES = ("file", "pixels", "size", "centre", "northUp", "metresPerPixel")


def detect_format(raw: str, data) -> tuple[int, tuple[str, str], str]:
    """How this file was written, so rewriting it changes only the minimap."""
    for indent in (1, 2, 3, 4):
        for sep in ((",", ": "), (", ", ": ")):
            for tail in ("\n", ""):
                if json.dumps(data, indent=indent, separators=sep,
                              ensure_ascii=False) + tail == raw:
                    return indent, sep, tail
    raise SystemExit("cannot reproduce %s byte for byte; refusing to rewrite it")


def square_bounds(manifest: dict, minimap: dict):
    """The square of world the minimap covers, as (min_x, min_z, extent).

    A map that already states its own bounds is believed. Four Gates does not:
    its renderer frames the mesh, so the square is the mesh's own bounds.
    """
    low, high = minimap.get("worldMin"), minimap.get("worldMax")
    if isinstance(low, list) and isinstance(high, list):
        extent = max(float(high[0]) - float(low[0]), float(high[-1]) - float(low[-1]))
        return float(low[0]), float(low[-1]), extent
    bounds = manifest.get("asset", {}).get("bounds", {})
    low, high = bounds.get("min"), bounds.get("max")
    if not (isinstance(low, list) and isinstance(high, list)):
        raise SystemExit("no bounds to size the minimap from")
    extent = max(float(high[0]) - float(low[0]), float(high[2]) - float(low[2]))
    centre_x = (float(low[0]) + float(high[0])) * 0.5
    centre_z = (float(low[2]) + float(high[2])) * 0.5
    return centre_x - extent * 0.5, centre_z - extent * 0.5, extent


def canonical_block(previous: dict, image_name: str, pixels: int,
                    min_x: float, min_z: float, extent: float) -> dict:
    """One shape for every map, with the old keys kept beside the new ones."""
    block = {
        "image": image_name,
        "imageSize": [pixels, pixels],
        "pixelsPerMetre": PIXELS_PER_METRE,
        "worldMin": [round(min_x, 4), round(min_z, 4)],
        "worldMax": [round(min_x + extent, 4), round(min_z + extent, 4)],
        "northAxis": previous.get("northAxis", "-Z"),
        "orientation": previous.get("orientation", "north-up"),
        "projection": previous.get("projection", "orthographic-top-down"),
        "renderedFrom": previous.get("renderedFrom", "world.glb"),
        "transform": {
            "pixelX": {"scale": PIXELS_PER_METRE,
                       "offset": round(-min_x * PIXELS_PER_METRE, 4)},
            "pixelY": {"scale": PIXELS_PER_METRE,
                       "offset": round(-min_z * PIXELS_PER_METRE, 4)},
            "formula": "pixel_x = world_x * scale + offset;"
                       " pixel_y = world_z * scale + offset",
        },
        "note": ("Every Eloria minimap is drawn at one pixel to the metre, so"
                 " the image's pixel size is the map's size in metres."),
    }
    for key in ("runtime", "generator", "fullMapImage", "previewImage"):
        if key in previous:
            block[key] = previous[key]
    # The old spellings, carried one more release.
    block["file"] = image_name
    block["pixels"] = pixels
    block["size"] = [pixels, pixels]
    block["metresPerPixel"] = round(1.0 / PIXELS_PER_METRE, 6)
    block["centre"] = [round(min_x + extent * 0.5, 4),
                       round(min_z + extent * 0.5, 4)]
    block["northUp"] = bool(previous.get("northUp", True))
    return block


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="write the manifests and resample the images")
    args = parser.parse_args()

    print("%-46s %-11s %-11s %-9s %s" % (
        "map", "was", "becomes", "extent_m", "px/m was -> now"))
    changed = 0
    for path in sorted(MAPS.glob("**/world.json")):
        raw = path.read_text(encoding="utf-8")
        manifest = json.loads(raw)
        minimap = manifest.get("minimap")
        if not isinstance(minimap, dict):
            continue
        name = str(path.parent.relative_to(MAPS))
        image_name = str(minimap.get("image") or minimap.get("file")
                         or "minimap.webp")
        image_path = path.parent / image_name
        if not image_path.exists():
            print("%-46s image missing: %s" % (name, image_name))
            continue

        min_x, min_z, extent = square_bounds(manifest, minimap)
        if abs(extent - round(extent)) > 1e-6:
            print("%-46s extent %.4f m is not whole; skipped" % (name, extent))
            continue
        pixels = int(round(extent * PIXELS_PER_METRE))

        with Image.open(image_path) as handle:
            was = handle.size
            source = handle.convert("RGB")
        old_ppm = was[0] / extent
        print("%-46s %-11s %-11s %-9s %.4f -> %.4f" % (
            name, "%dx%d" % was, "%dx%d" % (pixels, pixels), extent,
            old_ppm, PIXELS_PER_METRE))
        if not args.apply:
            continue

        if was != (pixels, pixels):
            source = source.resize((pixels, pixels), Image.LANCZOS)
        source.save(image_path, "WEBP", quality=WEBP_QUALITY, method=6)

        manifest["minimap"] = canonical_block(
            minimap, image_name, pixels, min_x, min_z, extent)
        indent, sep, tail = detect_format(raw, json.loads(raw))
        path.write_text(json.dumps(manifest, indent=indent, separators=sep,
                                   ensure_ascii=False) + tail, encoding="utf-8")
        changed += 1

    if args.apply:
        print("\nrewrote %d manifests at %.1f px/m" % (changed, PIXELS_PER_METRE))
    else:
        print("\ndry run; pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
