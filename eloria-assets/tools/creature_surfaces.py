#!/usr/bin/env python3
"""Procedural surface maps for the creature library.

The first pass shipped a single 256px luminance map per creature that only
modulated a flat base colour, so every fox, golem and serpent carried the same
grey grain.  This module authors a full-colour albedo and a matching tangent-
space normal map per surface kind, both derived from one height field, so the
relief in the normal map lines up with the pattern in the albedo.

Colour comes from the creature's own palette: ``base`` carries the body, and
``accent`` tints markings, plates, moss and rime, so the same generator gives a
red fox and an ice wolf genuinely different surfaces.
"""
from __future__ import annotations

import io
import math
import zlib

import numpy as np
from PIL import Image

# Surface kind per body plan / archetype.  Anything unlisted falls back to hide.
SURFACE_KINDS = {
    # quadrupeds
    "fox": "fur", "two_tail_fox": "fur", "wolf": "fur", "cat": "fur",
    "saber_cat": "fur", "bear": "fur", "hare": "fur", "otter": "pelt",
    "rat": "pelt", "porcupine": "quill", "elk": "fur", "ram": "fleece",
    "boar": "bristle", "rhino": "hide", "lizard": "scale", "crocodile": "scute",
    "drake": "scale", "toad": "warty", "tortoise": "shell",
    "canid": "fur", "felid": "fur", "ursine": "fur", "suid": "bristle",
    "cervid": "fur", "sprawler": "scale", "mustelid": "pelt",
    "lagomorph": "fur", "anuran": "warty", "chelonian": "shell",
    "bovine": "fur", "equine": "coat", "pinniped": "hide", "gryphon": "feather",
    # other families
    "wader": "feather", "seabird": "feather", "songbird": "feather",
    "raptor": "feather", "owl": "feather", "harpy": "feather",
    "snake": "scale", "sea_serpent": "scale", "eel": "slick", "wyrm": "scute",
    "hydra": "scute", "naga": "scale",
    "spider": "chitin", "scorpion": "chitin", "crab": "shell",
    "beetle": "chitin", "moth": "dust", "mantis": "chitin",
    "pike": "fishscale", "billfish": "fishscale", "armored": "fishscale",
    "ray": "slick", "axolotl": "slick",
    "wisp": "energy", "shards": "crystal", "sprite": "energy",
    "vortex": "water", "tentacles": "slick",
    # biped surface tags
    "metal": "metal", "stone": "stone", "cloth": "cloth", "bark": "bark",
    "ice": "ice", "crystal": "crystal", "moss": "moss", "barnacle": "barnacle",
    "hide": "hide", "fur": "fur", "scale": "scale",
}

# Markings layered on top of the base pattern for specific creatures.
MARKINGS = {
    "cat": "stripes", "frost_tiger": "rosette", "lynx": "rosette",
    "saber_cat": "dapple", "canopy_lynx": "rosette", "stormmane_lion": "dapple",
    "dust_hyena": "stripes", "harbor_seal": "speckle", "moss_badger": "blaze",
    "raccoon": "blaze", "emerald_basilisk": "band", "dartback_treefrog": "speckle",
    "glowmantle_ray": "speckle", "bloomtail_axolotl": "speckle",
}


def _noise(rng, size: int, cells: int) -> np.ndarray:
    """Smooth, tiling value noise via bilinear upsampling of a coarse grid."""
    grid = rng.random((cells + 1, cells + 1))
    grid[-1, :] = grid[0, :]
    grid[:, -1] = grid[:, 0]
    ys = np.linspace(0, cells, size, endpoint=False)
    xs = np.linspace(0, cells, size, endpoint=False)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    sy = fy * fy * (3 - 2 * fy)
    sx = fx * fx * (3 - 2 * fx)
    g00 = grid[np.ix_(y0, x0)]
    g10 = grid[np.ix_(y0 + 1, x0)]
    g01 = grid[np.ix_(y0, x0 + 1)]
    g11 = grid[np.ix_(y0 + 1, x0 + 1)]
    return (g00 * (1 - sy) * (1 - sx) + g10 * sy * (1 - sx)
            + g01 * (1 - sy) * sx + g11 * sy * sx)


def _fbm(rng, size: int, octaves=((4, .50), (8, .26), (16, .15), (32, .09))):
    field = np.zeros((size, size))
    for cells, weight in octaves:
        field += _noise(rng, size, cells) * weight
    return (field - field.min()) / max(float(np.ptp(field)), 1e-6)


def _cells(size: int, rows: int, cols: int, stagger=.5, round_=1.15):
    """Distance-to-cell-centre field: scales, scutes, plates, cobbles."""
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    u = np.linspace(0, 1, size, endpoint=False)[None, :]
    yy = v * rows
    xx = u * cols + (np.floor(yy) % 2) * stagger
    return np.sqrt(((xx % 1) - .5) ** 2 * round_ + ((yy % 1) - .5) ** 2)


def _height(kind: str, size: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """Return (height 0..1, pattern mask 0..1) for a surface kind."""
    fine = _fbm(rng, size)
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    u = np.linspace(0, 1, size, endpoint=False)[None, :]

    if kind in ("fur", "pelt", "coat", "fleece", "bristle", "quill"):
        strands = _noise(rng, size, {"fur": 74, "pelt": 96, "coat": 64,
                                     "fleece": 52, "bristle": 108,
                                     "quill": 40}[kind])
        lie = strands
        for shift in (1, 2, 3, 4):
            lie = lie + np.roll(strands, shift, 0)
        lie /= 5.0
        if kind == "fleece":
            curl = .5 + .5 * np.sin(u * math.pi * 30 + fine * 8.0)
            height = .30 * fine + .70 * curl
        elif kind == "quill":
            spikes = np.clip((lie - .48) * 6.0, 0, 1) ** .6
            height = .35 * fine + .65 * spikes
        else:
            height = .34 * fine + .66 * lie
        mask = np.clip((fine - .46) * 2.6, 0, 1)
    elif kind in ("scale", "fishscale", "scute", "shell"):
        rows, cols = {"scale": (30, 22), "fishscale": (36, 26),
                      "scute": (14, 11), "shell": (8, 10)}[kind]
        cell = _cells(size, rows, cols)
        dome = np.clip(1.0 - cell * (2.15 if kind != "shell" else 1.85), 0, 1) ** .55
        rim = np.clip(1.0 - abs(cell - .42) * 9.0, 0, 1)
        height = .70 * dome + .18 * rim + .12 * fine
        mask = np.clip((dome - .55) * 2.2, 0, 1)
    elif kind == "chitin":
        plate = _cells(size, 9, 7, stagger=.0, round_=1.0)
        seam = np.clip(1.0 - abs(plate - .46) * 7.0, 0, 1)
        height = np.clip(.78 - seam * .55 + .22 * fine, 0, 1)
        mask = np.clip((seam - .30) * 2.0, 0, 1)
    elif kind == "feather":
        rows = 26
        yy = v * rows
        quill = np.clip(1.0 - abs((yy % 1) - .5) * 3.4, 0, 1)
        barbs = .5 + .5 * np.sin(u * math.pi * 96 + (yy % 1) * 3.0)
        height = .46 * quill + .22 * barbs + .32 * fine
        mask = np.clip((quill - .55) * 2.4, 0, 1)
    elif kind == "warty":
        bumps = _noise(rng, size, 34)
        warts = np.clip((bumps - .56) * 5.6, 0, 1) ** .65
        height = .40 * fine + .60 * warts
        mask = warts
    elif kind in ("stone", "cairn"):
        cobble = _cells(size, 7, 6, stagger=.35, round_=1.0)
        block = np.clip(1.0 - cobble * 1.75, 0, 1) ** .8
        crack = np.clip(1.0 - abs(cobble - .48) * 8.0, 0, 1)
        height = np.clip(.62 * block + .34 * fine - .30 * crack, 0, 1)
        mask = np.clip((fine - .58) * 2.6, 0, 1)
    elif kind == "moss":
        clump = _noise(rng, size, 26)
        height = .45 * fine + .55 * np.clip((clump - .40) * 2.2, 0, 1)
        mask = np.clip((clump - .44) * 2.6, 0, 1)
    elif kind == "barnacle":
        studs = _noise(rng, size, 30)
        shells = np.clip((studs - .60) * 6.5, 0, 1) ** .5
        height = .42 * fine + .58 * shells
        mask = shells
    elif kind == "bark":
        ridge = .5 + .5 * np.sin(v * math.pi * 22 + _noise(rng, size, 10) * 9.0)
        groove = np.clip(ridge, 0, 1) ** 1.6
        height = .68 * groove + .32 * fine
        mask = np.clip((groove - .62) * 2.6, 0, 1)
    elif kind == "metal":
        panel = _cells(size, 6, 5, stagger=.0, round_=1.0)
        seam = np.clip(1.0 - abs(panel - .47) * 10.0, 0, 1)
        brushed = .5 + .5 * np.sin(u * math.pi * 150 + fine * 2.0)
        height = np.clip(.74 - seam * .5 + .12 * brushed + .14 * fine, 0, 1)
        mask = seam
    elif kind in ("crystal", "ice"):
        facet = _cells(size, 9, 8, stagger=.5, round_=.75)
        shard = np.clip(1.0 - facet * 2.0, 0, 1) ** .45
        height = .72 * shard + .28 * fine
        mask = np.clip((shard - .50) * 2.4, 0, 1)
    elif kind == "cloth":
        weave = (.5 + .5 * np.sin(u * math.pi * 190)) * (.5 + .5 * np.sin(v * math.pi * 190))
        fold = _noise(rng, size, 12)
        height = .30 * weave + .70 * fold
        mask = np.clip((fold - .55) * 2.4, 0, 1)
    elif kind in ("slick", "water", "energy", "dust"):
        flow = _noise(rng, size, 16)
        ripple = .5 + .5 * np.sin((u * 5.0 + v * 3.0) * math.pi * 2 + flow * 7.0)
        height = .58 * flow + .42 * ripple
        mask = np.clip((ripple - .52) * 2.2, 0, 1)
    else:  # hide
        wrinkle = _noise(rng, size, 20)
        seam = np.clip(1.0 - abs(wrinkle - .5) * 6.5, 0, 1)
        height = np.clip(.70 + .26 * fine - .32 * seam, 0, 1)
        mask = np.clip((fine - .60) * 2.4, 0, 1)
    return np.clip(height, 0, 1), np.clip(mask, 0, 1)


def _marking(name: str, size: int, rng, fine: np.ndarray) -> np.ndarray | None:
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    u = np.linspace(0, 1, size, endpoint=False)[None, :]
    if name == "stripes":
        band = .5 + .5 * np.sin(v * math.pi * 15 + fine * 7.0)
        return np.clip((band - .62) * 3.0, 0, 1)
    if name == "rosette":
        spots = _noise(rng, size, 20)
        core = np.clip((spots - .60) * 6.0, 0, 1)
        ring = np.clip(1.0 - abs(spots - .565) * 24.0, 0, 1)
        return np.clip(core * .55 + ring, 0, 1)
    if name == "dapple":
        spots = _noise(rng, size, 15)
        return np.clip((spots - .58) * 4.0, 0, 1) * .6
    if name == "speckle":
        spots = _noise(rng, size, 42)
        return np.clip((spots - .64) * 7.0, 0, 1)
    if name == "band":
        return np.clip((.5 + .5 * np.sin(u * math.pi * 9 + fine * 4.0) - .55) * 3.0, 0, 1)
    if name == "blaze":
        return np.clip((.5 + .5 * np.sin(u * math.pi * 2.0) - .52) * 4.0, 0, 1)
    return None


def _encode(array: np.ndarray, mode: str, colours: int | None = None,
            dither: bool = True) -> bytes:
    """Encode a map, optionally palettised.

    These surfaces are built from two palette colours and a height field, so
    their colour range is narrow and a 192-entry palette is visually lossless
    while roughly halving the embedded PNG.  Normal maps quantise without
    dither: dithering a normal map scatters the surface directions as noise.
    """
    image = Image.fromarray(array, mode=mode)
    if colours:
        image = image.quantize(
            colors=colours, method=Image.MEDIANCUT,
            dither=Image.FLOYDSTEINBERG if dither else Image.NONE)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _normal_map(height: np.ndarray, strength: float, size: int) -> bytes:
    """Tangent-space normal map from the same height field as the albedo."""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength * size / 256.0
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength * size / 256.0
    normal = np.stack([-dx, -dy, np.ones_like(height)], axis=-1)
    normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-9)
    return _encode(((normal * .5 + .5) * 255).astype(np.uint8), "RGB",
                   colours=128, dither=False)


NORMAL_STRENGTH = {
    "fur": 1.5, "pelt": 1.6, "coat": 1.2, "fleece": 1.7, "bristle": 1.9,
    "quill": 2.4, "scale": 2.2, "fishscale": 2.0, "scute": 2.6, "shell": 2.4,
    "chitin": 2.2, "feather": 1.6, "warty": 2.6, "stone": 2.4, "moss": 1.8,
    "barnacle": 2.8, "bark": 2.6, "metal": 1.6, "crystal": 2.6, "ice": 2.2,
    "cloth": 1.1, "slick": 0.8, "water": 0.9, "energy": 0.7, "dust": 1.0,
    "hide": 1.4,
}


def surface_maps(kind: str, base: tuple[int, int, int],
                 accent: tuple[int, int, int], seed: str = "",
                 size: int = 320, marking: str | None = None):
    """Return (albedo_png, normal_png) for one creature's surface."""
    kind = SURFACE_KINDS.get(kind, kind if kind in NORMAL_STRENGTH else "hide")
    rng = np.random.default_rng(zlib.crc32(f"{kind}:{seed}".encode("utf-8")) % (2 ** 31))
    height, mask = _height(kind, size, rng)
    fine = _fbm(rng, size, octaves=((6, .55), (12, .28), (24, .17)))

    base_rgb = np.asarray(base, dtype=float) / 255.0
    accent_rgb = np.asarray(accent, dtype=float) / 255.0
    # Shade with the height field, then tint the raised pattern toward the
    # accent so markings and plates carry hue, not just value.
    shade = (.62 + .48 * height)[..., None]
    # The accent marks the hide; it must not repaint it.  At the old weight a
    # brown bear under gold moss came out gold all over.
    tint = (mask * .30)[..., None]
    albedo = base_rgb * (1 - tint) + accent_rgb * tint
    albedo = albedo * shade
    # A little low-frequency hue drift keeps large flat areas from reading dead.
    drift = (fine - .5)[..., None] * .10
    albedo = albedo + drift * np.array([1.0, .55, -.35])
    if marking:
        pattern = _marking(marking, size, rng, fine)
        if pattern is not None:
            dark = base_rgb * .42
            albedo = albedo * (1 - pattern[..., None]) + dark * pattern[..., None]
            height = np.clip(height - pattern * .12, 0, 1)
    albedo = np.clip(albedo, 0.02, 1.0)
    albedo_png = _encode((albedo * 255).astype(np.uint8), "RGB", colours=192)
    normal_png = _normal_map(height, NORMAL_STRENGTH.get(kind, 1.4), size)
    return albedo_png, normal_png


def keratin_maps(accent: tuple[int, int, int], seed: str = "", size: int = 192):
    """Horn, antler, hoof, quill, shell rim and armour trim."""
    rng = np.random.default_rng(zlib.crc32(f"keratin:{seed}".encode("utf-8")) % (2 ** 31))
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    grain = _fbm(rng, size, octaves=((8, .55), (18, .30), (36, .15)))
    rings = .5 + .5 * np.sin(v * math.pi * 40 + grain * 3.4)
    height = np.clip(.60 + .28 * rings + .20 * grain, 0, 1)
    tone = np.asarray(accent, dtype=float) / 255.0
    bone = np.array([.92, .88, .78])
    colour = (tone * .45 + bone * .55) * (.66 + .44 * height)[..., None]
    albedo = _encode((np.clip(colour, 0, 1) * 255).astype(np.uint8), "RGB",
                     colours=128)
    return albedo, _normal_map(height, 1.5, size)
