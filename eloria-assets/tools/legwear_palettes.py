#!/usr/bin/env python3
"""Colours for the sixty-four leg garments, read off the concept tiles.

The sheets are the only statement of what each design looks like, so the
palette is measured from them rather than invented.  Each tile gives four
colours - base, trim, accent and a dark for the shadowed underside - clustered
out of the figure's own pixels with the background and the drop shadow removed.

This is deliberately the same method the creature sheets use in
``extract_concept_palettes``: cluster, then lift the cluster toward albedo
without letting one channel saturate, because scaling one channel to 255 while
the others stay put is what turns brown leather into gold.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from legwear_roster import ROSTER

TILES = Path(__file__).resolve().parents[1] / "concepts" / "legwear"
CACHE = Path(__file__).resolve().parent / "legwear_palettes.json"


#: The sheets are laid out with a white gutter around a parchment field, so the
#: tile border is paper rather than ground.  Sampling the border gives white,
#: every parchment pixel then reads as "not background", and the palette comes
#: back the colour of the sheet.  The ground is sampled from a ring just inside
#: the gutter instead, where the parchment is and the figure is not.
_INSET = .10


def _ground(rgb: np.ndarray) -> np.ndarray:
    height, width, _ = rgb.shape
    top, left = int(height * _INSET), int(width * _INSET)
    ring = np.concatenate([
        rgb[top:top + 8, left:width - left].reshape(-1, 3),
        rgb[height - top - 8:height - top, left:width - left].reshape(-1, 3),
        rgb[top:height - top, left:left + 8].reshape(-1, 3),
        rgb[top:height - top, width - left - 8:width - left].reshape(-1, 3)])
    return np.median(ring, axis=0)


def _figure_pixels(path: Path) -> np.ndarray:
    """The garment's own pixels: paper, parchment and cast shadow removed."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float)
    ground = _ground(rgb)
    paper = np.array([250., 250., 250.])
    keep = ((np.linalg.norm(rgb - ground, axis=-1) > 52)
            & (np.linalg.norm(rgb - paper, axis=-1) > 52))
    # The cast shadow is the parchment dimmed, so it keeps the parchment's
    # channel ratios.  Anything that is a uniform scaling of the ground colour
    # is ground, however dark it has been rendered.
    scale = (rgb @ ground) / float(ground @ ground)
    residual = np.linalg.norm(rgb - scale[..., None] * ground, axis=-1)
    keep &= ~((residual < 26) & (scale > .55) & (scale < 1.15))
    pixels = rgb[keep]
    if len(pixels) < 400:
        return rgb.reshape(-1, 3)
    luma = pixels.mean(axis=1)
    return pixels[(luma > 16) & (luma < 250)]


def _kmeans(pixels: np.ndarray, k: int = 5, iters: int = 20,
            seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    if len(pixels) > 20000:
        pixels = pixels[rng.choice(len(pixels), 20000, replace=False)]
    centres = pixels[rng.choice(len(pixels), k, replace=False)].astype(float)
    labels = np.zeros(len(pixels), dtype=int)
    for _ in range(iters):
        distance = ((pixels[:, None, :] - centres[None]) ** 2).sum(-1)
        labels = distance.argmin(1)
        for index in range(k):
            chosen = pixels[labels == index]
            if len(chosen):
                centres[index] = chosen.mean(0)
    return centres, np.bincount(labels, minlength=k)


def _lift(colour: np.ndarray, target: float = 150.0, ceiling: float = 208.0,
          gain: float = 1.22, floor: float = 46.0) -> tuple[int, int, int]:
    """Toward albedo without inventing a hue: one factor for all three channels.

    Polished steel is the case that breaks a single target.  A white plate is
    lit brightly and shadowed warm, so its cluster comes back a mid warm grey;
    normalised to the same luma as dyed cloth it reads as brown leather, which
    is what the ceremonial sheet first produced.  A nearly unsaturated colour
    is therefore lifted to a brighter target and pulled the last of the way to
    neutral, because on these sheets desaturated means metal.
    """
    colour = np.asarray(colour, dtype=float)
    if _saturation(colour) < .14:
        grey = float(colour.mean())
        colour = grey + (colour - grey) * .45
        target, gain = max(target, 186.0), 1.55
    luma = max(float(colour.mean()), 1.0)
    goal = min(max(luma * gain, floor), target)
    scaled = colour * (goal / luma)
    if scaled.max() > ceiling:
        scaled *= ceiling / scaled.max()
    return tuple(int(round(v)) for v in np.clip(scaled, 8, 255))


def _saturation(colour) -> float:
    colour = np.asarray(colour, dtype=float)
    high = float(colour.max())
    return 0.0 if high <= 0 else (high - float(colour.min())) / high


def palette(tile: Path) -> dict:
    """base, trim, accent and dark for one design."""
    pixels = _figure_pixels(tile)
    centres, counts = _kmeans(pixels)
    order = np.argsort(-counts)
    ranked = [centres[i] for i in order]
    # The base is the garment's lit surface, not simply its commonest pixel.
    # On a plate design the shadowed side of the same metal is as large a
    # cluster as the lit side and darker, and taking the largest outright
    # returned the ceremonial sheet's white armour as brown.  Among the
    # clusters that are large enough to be structural, the brightest is the
    # one the eye reads as the garment's colour.
    floor_count = counts[order[0]] * .5
    structural = [centres[i] for i in order if counts[i] >= floor_count]
    base = max(structural, key=lambda c: float(c.mean()))
    # The trim is the most saturated cluster that is not the base; on a plate
    # design that is the gold, on a cloth one the dyed band.  Falling back to
    # the second largest keeps a monochrome design from picking up noise.
    rest = [c for c in ranked if not np.array_equal(c, base)]
    trim = max(rest, key=_saturation) if rest else base
    if _saturation(trim) < .12 and rest:
        trim = rest[0]
    accent = max((c for c in rest if not np.array_equal(c, trim)),
                 key=lambda c: float(c.mean()), default=trim)
    dark = min(ranked, key=lambda c: float(c.mean()))
    return {"base": _lift(base), "trim": _lift(trim, target=162.0),
            "accent": _lift(accent, target=176.0),
            "dark": _lift(dark, target=92.0, gain=1.05, floor=28.0)}


def build() -> dict:
    out = {}
    for slug, _name, sheet, index, _kind, _features in ROSTER:
        out[slug] = palette(TILES / f"{sheet}_{index}.png")
    return out


def load() -> dict:
    if CACHE.is_file():
        return json.loads(CACHE.read_text())
    data = build()
    CACHE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return data


if __name__ == "__main__":
    data = build()
    CACHE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    for slug in sorted(data):
        row = data[slug]
        cells = "  ".join(f"{k}#{r:02x}{g:02x}{b:02x}"
                          for k, (r, g, b) in row.items())
        print(f"{slug:22s} {cells}")
