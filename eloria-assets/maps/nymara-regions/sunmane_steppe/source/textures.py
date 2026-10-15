"""Original tileable PBR texture kit for the Sunmane Steppe.

Six material families, each authored as base colour + tangent-space normal +
ORM (R = occlusion, G = roughness, B = metallic), matching the channel packing
already documented for the Four Gates package.  Every map is generated from
periodic noise so it repeats without seams at terrain scale.

Palette authority is the concept art: warm ochre soil, sun-bleached grass, pale
canvas, dark weathered timber, red textile, hammered metal, leather and bone.
The generators deliberately favour readable mid-frequency structure - boards,
weave, strata, tufts - over fine noise, because that is what survives mip
reduction and reads at player distance.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from noise import fbm, worley, directional_grain, height_to_normal, normalise


@dataclass
class MaterialMaps:
    name: str
    base_color: bytes
    normal: bytes
    orm: bytes
    size: int


def _encode(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.clip(array * 255.0 + 0.5, 0, 255).astype("uint8")).save(
        buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _halve(array: np.ndarray) -> np.ndarray:
    """Box-filter an image to half resolution."""
    size = array.shape[0]
    if size % 2:
        return array
    if array.ndim == 2:
        return array.reshape(size // 2, 2, size // 2, 2).mean(axis=(1, 3))
    return array.reshape(size // 2, 2, size // 2, 2, array.shape[2]).mean(axis=(1, 3))


def _encode_normal(normal: np.ndarray) -> bytes:
    """Encode a normal map at half resolution and renormalise after filtering."""
    halved = _halve(normal) * 2.0 - 1.0
    lengths = np.linalg.norm(halved, axis=-1, keepdims=True)
    lengths[lengths == 0.0] = 1.0
    return _encode(halved / lengths * 0.5 + 0.5)


def _pack_orm(occlusion, roughness, metallic) -> np.ndarray:
    """Pack ORM at half resolution.

    Occlusion, roughness and metallic are low-frequency signals, so a
    half-size map is visually indistinguishable while roughly quartering the
    encoded bytes.
    """
    stacked = np.stack([np.clip(occlusion, 0, 1), np.clip(roughness, 0, 1),
                        np.clip(metallic, 0, 1)], axis=-1)
    size = stacked.shape[0]
    if size % 2:
        return stacked
    half = stacked.reshape(size // 2, 2, size // 2, 2, 3).mean(axis=(1, 3))
    return half


def _tint(mask: np.ndarray, low, high) -> np.ndarray:
    low = np.asarray(low, dtype="float64") / 255.0
    high = np.asarray(high, dtype="float64") / 255.0
    return low + (high - low) * np.clip(mask, 0, 1)[..., None]


def _blend(base: np.ndarray, color, mask: np.ndarray) -> np.ndarray:
    """Alpha-composite a flat colour over an RGB field."""
    color = np.asarray(color, dtype="float64") / 255.0
    mask = np.clip(mask, 0, 1)[..., None]
    return base * (1.0 - mask) + color * mask


def _occlusion(height: np.ndarray, radius: int = 3) -> np.ndarray:
    blurred = height.copy()
    for _ in range(radius):
        blurred = (blurred
                   + np.roll(blurred, 1, 0) + np.roll(blurred, -1, 0)
                   + np.roll(blurred, 1, 1) + np.roll(blurred, -1, 1)) / 5.0
    return np.clip(0.70 + (height - blurred) * 3.0, 0.30, 1.0)


def _wave(size: int, cycles: float, phase: np.ndarray | float = 0.0) -> np.ndarray:
    """Periodic 0..1 triangle-ish wave along an axis, safe for tiling."""
    return 0.5 + 0.5 * np.cos(np.arange(size) * 2.0 * np.pi * cycles / size + phase)


def _stripes(size: int, cycles: int, sharpness: float, jitter: np.ndarray) -> np.ndarray:
    """Repeating sharp-edged bands along V, warped by a per-row jitter."""
    position = (np.arange(size) * cycles / size) + jitter
    within = position - np.floor(position)
    edge = np.minimum(within, 1.0 - within) * 2.0
    return np.clip(edge * sharpness, 0.0, 1.0)


# --------------------------------------------------------------------- canvas
def canvas(size: int, seed: int) -> MaterialMaps:
    """Sun-bleached heavy tent canvas: visible weave, panel seams and sag."""
    rng = np.random.default_rng(seed)
    threads = 44                                    # coarse, legible cloth
    warp = _wave(size, threads)[None, :] * np.ones((size, 1))
    weft = _wave(size, threads)[:, None] * np.ones((1, size))
    # Over-under interlacing rather than a flat grid.
    checker = ((np.floor(np.arange(size) * threads / size)[None, :]
                + np.floor(np.arange(size) * threads / size)[:, None]) % 2).astype(float)
    weave = warp * checker + weft * (1.0 - checker)
    weave = normalise(weave)

    slub = fbm(size, 30, 3, rng)                    # thread thickness variation
    sag = fbm(size, 3, 3, rng)                      # broad cloth folds
    # Stitched panel seams every third of the tile, running along U.
    seam = 1.0 - _stripes(size, 3, 26.0, fbm(size, 4, 2, rng)[:, 0] * 0.05)
    stitch = seam * (_wave(size, 150)[None, :] * np.ones((size, 1)))

    height = normalise(weave * 0.34 + slub * 0.12 + sag * 0.34
                       + seam * 0.14 + stitch * 0.06)
    soiling = np.clip(fbm(size, 4, 4, rng) * 1.9 - 0.72, 0.0, 1.0)
    bleach = fbm(size, 6, 3, rng)

    color = _tint(normalise(sag * 0.5 + bleach * 0.5), (206, 190, 156), (243, 234, 210))
    color = _blend(color, (150, 112, 68), soiling * 0.68)          # dust and use
    color = _blend(color, (176, 165, 141), (1.0 - weave) * 0.18)   # thread shadow
    color = _blend(color, (198, 186, 160), seam * 0.35)            # seam webbing
    normal = height_to_normal(height, strength=1.9)
    roughness = np.clip(0.82 + slub * 0.10 + soiling * 0.06, 0, 1)
    return MaterialMaps("canvas", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 2), roughness,
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- timber
def timber(size: int, seed: int) -> MaterialMaps:
    """Dark weathered structural timber: crisp boards in V, grain along U."""
    rng = np.random.default_rng(seed)
    boards = 5
    row = np.arange(size) * boards / size
    index = np.floor(row).astype(int)
    within = row - index
    # Hard shadow gap plus a chamfered arris on each board edge.
    gap = np.clip(np.minimum(within, 1.0 - within) * boards * 2.6, 0.0, 1.0)
    arris = np.clip(np.minimum(within, 1.0 - within) * boards * 0.9, 0.0, 1.0) ** 0.45
    gap_field = gap[:, None] * np.ones((1, size))
    arris_field = arris[:, None] * np.ones((1, size))

    grain = directional_grain(size, rng, stretch=30, period=110, octaves=3)
    grain = normalise(grain) ** 1.4
    coarse = directional_grain(size, rng, stretch=44, period=18, octaves=3)
    shifted_grain = np.empty_like(grain)
    shifted_coarse = np.empty_like(coarse)
    board_tone = np.zeros((size, 1))
    for board in range(boards):
        rows = index == board
        roll = int(rng.integers(0, size))
        shifted_grain[rows] = np.roll(grain[rows], roll, axis=1)
        shifted_coarse[rows] = np.roll(coarse[rows], roll, axis=1)
        board_tone[rows, 0] = rng.uniform(-0.14, 0.14)      # each board differs

    knot_field = worley(size, 5, rng)
    knots = np.clip(1.0 - knot_field * 7.0, 0.0, 1.0)
    checking = np.clip(directional_grain(size, rng, stretch=40, period=90, octaves=2)
                       * 2.2 - 1.35, 0.0, 1.0)

    height = normalise(arris_field * 0.46 + shifted_grain * 0.16
                       + shifted_coarse * 0.10 - checking * 0.16 - knots * 0.12)
    tone = np.clip(normalise(shifted_coarse * 0.55 + shifted_grain * 0.45)
                   + board_tone, 0.0, 1.0)
    color = _tint(tone, (38, 27, 19), (112, 84, 55))
    silvering = np.clip((arris_field - 0.55) * 2.2, 0.0, 1.0) * fbm(size, 7, 3, rng)
    color = _blend(color, (150, 140, 126), silvering * 0.5)   # sun-bleached edges
    color = _blend(color, (26, 17, 11), knots * 0.8)          # dark knots
    color = _blend(color, (18, 12, 8), (1.0 - gap_field) * 0.85)  # shadow between boards
    color = _blend(color, (24, 16, 11), checking * 0.45)      # splits
    normal = height_to_normal(height, strength=3.2)
    roughness = np.clip(0.74 + shifted_grain * 0.18 + checking * 0.06 - silvering * 0.06, 0, 1)
    occlusion = np.clip(_occlusion(height, 3) * (0.45 + 0.55 * gap_field), 0.2, 1.0)
    return MaterialMaps("timber", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(occlusion, roughness,
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- ground
def ground(size: int, seed: int) -> MaterialMaps:
    """Ochre steppe soil under sun-bleached grass, with sparse grit and cracks.

    Terrain classes tint this one detail map through material base-colour
    factors, which keeps texel density uniform and avoids splat seams.
    """
    rng = np.random.default_rng(seed)
    # Grass is the dominant read: fine blades clumped into tufts.
    blades = directional_grain(size, rng, stretch=2, period=170, octaves=2)
    clumps = fbm(size, 11, 4, rng)
    tufts = np.clip((blades * 0.55 + clumps * 0.45 - 0.42) * 3.4, 0.0, 1.0)
    # Second blade direction so the sward does not comb one way.
    cross = np.clip((directional_grain(size, rng, stretch=2, period=150, octaves=2).T
                     * 0.6 + clumps * 0.4 - 0.46) * 3.0, 0.0, 1.0)
    sward = np.clip(tufts * 0.78 + cross * 0.55, 0.0, 1.0)

    soil_patch = fbm(size, 5, 5, rng)                      # broad bare/covered areas
    bare = np.clip((0.56 - soil_patch) * 3.2, 0.0, 1.0)
    grit = 1.0 - worley(size, 52, rng)
    pebbles = np.clip((1.0 - worley(size, 13, rng) - 0.70) * 6.0, 0.0, 1.0) * bare
    crack = np.clip(1.0 - worley(size, 9, np.random.default_rng(seed + 3), order=1) * 9.0,
                    0.0, 1.0) * bare

    height = normalise(sward * 0.34 + soil_patch * 0.28 + grit * 0.08
                       + pebbles * 0.24 - crack * 0.22)
    # Warm ochre dirt showing through pale straw-coloured grass.
    color = _tint(normalise(soil_patch * 0.6 + grit * 0.4), (116, 88, 56), (166, 136, 86))
    grass_color = _tint(normalise(blades * 0.5 + clumps * 0.5), (144, 132, 74), (212, 198, 128))
    color = color * (1.0 - sward[..., None] * 0.88) + grass_color * sward[..., None] * 0.88
    color = _blend(color, (166, 150, 122), pebbles * 0.62)
    color = _blend(color, (92, 62, 34), crack * 0.5)
    color = _blend(color, (198, 172, 108), np.clip((soil_patch - 0.74) * 3.5, 0, 1) * 0.3)
    normal = height_to_normal(height, strength=2.0)
    roughness = np.clip(0.88 + grit * 0.08 - pebbles * 0.18, 0, 1)
    return MaterialMaps("ground", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness,
                                          np.zeros((size, size)))), size)


# ---------------------------------------------------------------------- stone
def stone(size: int, seed: int) -> MaterialMaps:
    """Pale eroded sandstone with clear bedding strata for mesas and cliffs."""
    rng = np.random.default_rng(seed)
    # Bedding planes of varying hardness, gently warped so they are not level.
    warp = fbm(size, 4, 3, rng)[:, 0] * 0.30
    rows = np.arange(size)
    bed_index = np.floor(rows * 7.0 / size + warp)
    within = (rows * 7.0 / size + warp) - bed_index
    hardness = np.zeros(size)
    for value in np.unique(bed_index):
        hardness[bed_index == value] = rng.uniform(0.25, 1.0)
    # Each bed steps proud or recedes; the parting line between beds is dark.
    parting = np.clip(np.minimum(within, 1.0 - within) * 9.0, 0.0, 1.0)
    bedding = (hardness * (0.35 + 0.65 * parting))[:, None] * np.ones((1, size))
    recess = np.clip(1.0 - parting, 0.0, 1.0)[:, None] * np.ones((1, size))
    soft_bed = np.clip(0.55 - hardness, 0.0, 1.0)[:, None] * np.ones((1, size))

    body = fbm(size, 3, 5, rng)
    chips = np.clip((1.0 - worley(size, 14, rng) - 0.55) * 3.6, 0.0, 1.0)
    pitting = np.clip((1.0 - worley(size, 36, rng) - 0.74) * 6.0, 0.0, 1.0)

    height = normalise(bedding * 0.52 + body * 0.24 - recess * 0.24
                       - soft_bed * 0.20 - chips * 0.08 - pitting * 0.06)
    color = _tint(normalise(bedding * 0.55 + body * 0.45), (126, 114, 96), (210, 200, 176))
    stain = np.clip(fbm(size, 3, 4, np.random.default_rng(seed + 6)) * 1.8 - 0.80, 0, 1)
    color = _blend(color, (174, 132, 84), stain * 0.42)          # iron staining
    color = _blend(color, (88, 74, 57), recess * 0.62)           # shadowed partings
    color = _blend(color, (152, 128, 98), soft_bed * 0.45)       # softer marl beds
    color = _blend(color, (231, 222, 200), chips * 0.45)         # fresh spalled faces
    color = _blend(color, (82, 72, 58), pitting * 0.5)
    normal = height_to_normal(height, strength=3.2)
    roughness = np.clip(0.74 + chips * 0.16 + pitting * 0.08 + soft_bed * 0.08, 0, 1)
    return MaterialMaps("stone", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 4), roughness,
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- thatch
def thatch(size: int, seed: int) -> MaterialMaps:
    """Bundled straw for hay stacks, wheat stooks and thatched shelter."""
    rng = np.random.default_rng(seed)
    strands = directional_grain(size, rng, stretch=1, period=200, octaves=2)
    strands = np.clip((strands - 0.40) * 3.0, 0.0, 1.0)
    # Irregular bundle spacing rather than a metronomic stripe.
    bundling = _stripes(size, 8, 2.4, fbm(size, 6, 3, rng)[:, 0] * 0.55)
    bundling = bundling[:, None] * np.ones((1, size))
    ends = np.clip(fbm(size, 26, 3, rng) * 1.6 - 0.6, 0.0, 1.0)   # cut straw ends
    shade = fbm(size, 8, 4, rng)

    height = normalise(strands * 0.34 + bundling * 0.36 + ends * 0.16 + shade * 0.14)
    color = _tint(normalise(strands * 0.5 + shade * 0.5), (150, 112, 48), (232, 202, 128))
    color = _blend(color, (96, 68, 30), (1.0 - bundling) * 0.55)   # shadowed bindings
    color = _blend(color, (243, 226, 176), ends * 0.35)            # bright cut ends
    normal = height_to_normal(height, strength=3.2)
    roughness = np.clip(0.88 + shade * 0.08, 0, 1)
    return MaterialMaps("thatch", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness,
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- crystal
def crystal(size: int, seed: int) -> MaterialMaps:
    """Amethyst: banded violet quartz with bright cleavage faces.

    The Amethyst Barrens is Sunmane's northern neighbour on the continent
    concept, so its crystal shows up in the badland spires and the cave the
    badlands hide. Kept cooler and less saturated than the Barrens' own hero
    material, because here it is an influence rather than the subject.
    """
    rng = np.random.default_rng(seed)
    facets = 1.0 - worley(size, 9, rng)
    banding = _stripes(size, 11, 3.2, fbm(size, 5, 3, rng)[:, 0] * 0.4)
    banding = banding[:, None] * np.ones((1, size))
    depth = fbm(size, 6, 5, rng)
    height = normalise(facets * 0.6 + banding * 0.24 + depth * 0.16)
    color = _tint(normalise(depth * 0.5 + banding * 0.5), (58, 38, 84), (168, 140, 208))
    color = _blend(color, (214, 198, 240), np.clip((height - 0.72) * 3.6, 0, 1) * 0.7)
    color = _blend(color, (40, 28, 62), np.clip((0.3 - height) * 3.0, 0, 1) * 0.55)
    normal = height_to_normal(height, strength=2.2)
    roughness = np.clip(0.32 - np.clip((height - 0.7) * 2.0, 0, 1) * 0.18
                        + fbm(size, 18, 3, rng) * 0.14, 0.06, 1)
    return MaterialMaps("crystal", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness,
                                          np.zeros((size, size)))), size)


# ------------------------------------------------------------------------ hide
def hide(size: int, seed: int) -> MaterialMaps:
    """Neutral pale animal hide: short coat hair over soft dappling.

    Deliberately close to mid-grey so a coat colour applied through
    baseColorFactor lands where it is aimed - a dark leather base would drag
    every horse to the same brown however it was tinted.
    """
    rng = np.random.default_rng(seed)
    coat = directional_grain(size, rng, stretch=3, period=190, octaves=2)
    dapple = fbm(size, 9, 4, rng)
    fine = 1.0 - worley(size, 40, rng)
    height = normalise(coat * 0.5 + dapple * 0.3 + fine * 0.2)
    color = _tint(normalise(coat * 0.45 + dapple * 0.55), (150, 142, 132),
                  (233, 227, 218))
    # Slightly darker along the spine line and paler at the flank.
    color = _blend(color, (176, 168, 158), np.clip((0.42 - dapple) * 2.4, 0, 1) * 0.45)
    normal = height_to_normal(height, strength=1.4)
    return MaterialMaps("hide", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 2),
                                          np.full((size, size), 0.68),
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- leather
def leather(size: int, seed: int) -> MaterialMaps:
    """Pebbled hide for tack, straps, packs and door curtains."""
    rng = np.random.default_rng(seed)
    pebble = 1.0 - worley(size, 26, rng)
    creases = np.clip(1.0 - worley(size, 6, rng, order=1) * 6.0, 0.0, 1.0)
    height = normalise(pebble * 0.5 + fbm(size, 10, 4, rng) * 0.5 - creases * 0.55)
    color = _tint(height, (52, 30, 17), (136, 90, 50))
    color = _blend(color, (30, 17, 9), creases * 0.7)
    color = _blend(color, (170, 126, 78), np.clip((height - 0.78) * 4.0, 0, 1) * 0.5)
    normal = height_to_normal(height, strength=2.4)
    roughness = np.clip(0.58 + pebble * 0.2 + creases * 0.1, 0, 1)
    return MaterialMaps("leather", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness,
                                          np.zeros((size, size)))), size)


# --------------------------------------------------------------------- textile
def textile(size: int, seed: int) -> MaterialMaps:
    """Woven Orun cloth: red and ochre banding with a diamond motif."""
    rng = np.random.default_rng(seed)
    threads = 46
    warp = _wave(size, threads)[None, :] * np.ones((size, 1))
    weft = _wave(size, threads)[:, None] * np.ones((1, size))
    checker = ((np.floor(np.arange(size) * threads / size)[None, :]
                + np.floor(np.arange(size) * threads / size)[:, None]) % 2).astype(float)
    weave = normalise(warp * checker + weft * (1.0 - checker))

    rows = np.arange(size)
    stripe = np.zeros(size)
    unit = size / 64.0
    for start_row, width, value in ((0, 18, 0.1), (18, 5, 0.9), (23, 9, 0.5),
                                    (32, 5, 0.9), (37, 16, 0.1), (53, 11, 0.7)):
        window = (rows >= start_row * unit) & (rows < (start_row + width) * unit)
        stripe[window] = value
    band = stripe[:, None] * np.ones((1, size))

    color = np.zeros((size, size, 3))
    color = _blend(color, (150, 48, 36), (band < 0.3).astype(float))
    color = _blend(color, (204, 156, 70), ((band >= 0.3) & (band < 0.6)).astype(float))
    color = _blend(color, (222, 210, 186), ((band >= 0.6) & (band < 0.8)).astype(float))
    color = _blend(color, (48, 38, 32), (band >= 0.8).astype(float))
    step = max(8, size // 12)
    motif = np.abs(((np.arange(size)[:, None] + np.arange(size)[None, :]) % step)
                   - step / 2) / (step / 2)
    motif = motif + np.abs(((np.arange(size)[:, None] - np.arange(size)[None, :]) % step)
                           - step / 2) / (step / 2)
    diamond = np.clip((0.75 - motif) * 4.0, 0.0, 1.0) * (band < 0.3)
    color = _blend(color, (226, 198, 152), diamond * 0.85)
    color *= (0.76 + 0.32 * weave[..., None])
    height = normalise(weave * 0.7 + diamond * 0.3)
    normal = height_to_normal(height, strength=1.8)
    return MaterialMaps("textile", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 2),
                                          np.full((size, size), 0.84),
                                          np.zeros((size, size)))), size)


# ----------------------------------------------------------------------- metal
def metal(size: int, seed: int) -> MaterialMaps:
    """Hammered bronze and iron fittings: dished facets with worn crests."""
    rng = np.random.default_rng(seed)
    facets = 1.0 - worley(size, 12, rng)
    height = normalise(facets * 0.86 + fbm(size, 26, 3, rng) * 0.14)
    wear = np.clip((height - 0.66) * 3.4, 0.0, 1.0)
    tarnish = np.clip(fbm(size, 7, 4, rng) * 1.5 - 0.55, 0.0, 1.0)
    color = _tint(height, (68, 58, 42), (168, 146, 94))
    color = _blend(color, (220, 198, 140), wear * 0.65)
    color = _blend(color, (54, 52, 44), tarnish * 0.45)
    normal = height_to_normal(height, strength=2.6)
    roughness = np.clip(0.50 - wear * 0.30 + tarnish * 0.22, 0.10, 1)
    metallic = np.clip(0.90 - tarnish * 0.25, 0, 1)
    return MaterialMaps("metal", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness, metallic)),
                        size)


# ------------------------------------------------------------------------ bone
def bone(size: int, seed: int) -> MaterialMaps:
    """Carved bone and antler for shrine ornament, tool handles and totems."""
    rng = np.random.default_rng(seed)
    body = fbm(size, 12, 5, rng)
    veins = np.abs(np.sin(np.arange(size) * np.pi * 6.0 / size
                          + fbm(size, 4, 3, rng)[:, 0] * 3.0))[:, None] * np.ones((1, size))
    incision = np.clip(1.0 - worley(size, 8, rng, order=1) * 8.0, 0.0, 1.0)
    height = normalise(body * 0.66 + veins * 0.34 - incision * 0.75)
    color = _tint(height, (174, 160, 130), (242, 236, 218))
    color = _blend(color, (128, 112, 86), incision * 0.7)
    color = _blend(color, (200, 178, 140),
                   np.clip(fbm(size, 5, 3, rng) * 1.4 - 0.6, 0, 1) * 0.3)
    normal = height_to_normal(height, strength=2.4)
    roughness = np.clip(0.40 + incision * 0.34, 0, 1)
    return MaterialMaps("bone", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 3), roughness,
                                          np.zeros((size, size)))), size)


def cavern(size: int, seed: int) -> MaterialMaps:
    """Damp cave limestone: mottled flowstone with drapery, no pitting.

    Deliberately unlike the surface `stone` family. The mesa map carries worley
    pitting and hard bedding partings, which on a chamber floor tens of metres
    across repeat into a spotted pattern. Cave rock instead reads as broad damp
    mottling with fine vertical drapery where water has run.
    """
    rng = np.random.default_rng(seed)
    broad = fbm(size, 3, 5, rng)                      # damp patches
    medium = fbm(size, 7, 4, rng)                     # calcite mottling
    drapery = directional_grain(size, rng, stretch=26)
    # Flowstone runs are vertical ribs, strongest where the drapery mask is.
    ribs = np.clip(drapery * 1.5 - 0.35, 0.0, 1.0) * np.clip(broad * 1.4 - 0.2, 0, 1)
    height = normalise(broad * 0.42 + medium * 0.30 + ribs * 0.28)
    color = _tint(normalise(broad * 0.55 + medium * 0.45), (96, 88, 80), (206, 196, 180))
    damp = np.clip(fbm(size, 4, 4, np.random.default_rng(seed + 5)) * 1.7 - 0.85, 0, 1)
    color = _blend(color, (74, 70, 66), damp * 0.55)          # wet, darker rock
    color = _blend(color, (226, 219, 203), ribs * 0.50)       # fresh calcite
    seep = np.clip(fbm(size, 9, 3, np.random.default_rng(seed + 9)) * 1.6 - 0.9, 0, 1)
    color = _blend(color, (132, 120, 96), seep * 0.35)        # mineral seep stain
    normal = height_to_normal(height, strength=2.4)
    # Wet flowstone is the only part that is at all shiny.
    roughness = np.clip(0.92 - ribs * 0.30 - damp * 0.10, 0.2, 1.0)
    return MaterialMaps("cavern", _encode(color), _encode_normal(normal),
                        _encode(_pack_orm(_occlusion(height, 5), roughness,
                                          np.zeros((size, size)))), size)


FAMILIES = {
    "cavern": (cavern, 512, 1212),
    "canvas": (canvas, 512, 1201),
    "timber": (timber, 512, 1202),
    "ground": (ground, 1024, 1203),
    "stone": (stone, 512, 1204),
    "thatch": (thatch, 512, 1205),
    "crystal": (crystal, 256, 1211),
    "hide": (hide, 256, 1210),
    "leather": (leather, 256, 1206),
    "textile": (textile, 256, 1207),
    "metal": (metal, 256, 1208),
    "bone": (bone, 256, 1209),
}


def build_kit(scale: float = 1.0, families=None) -> dict[str, MaterialMaps]:
    """Build the kit, optionally at a fraction of the authored resolution.

    Creature assets take a small kit: at the size an animal occupies on screen
    a full-resolution hide map is pure package weight.
    """
    selected = FAMILIES if families is None else {
        name: FAMILIES[name] for name in families}
    return {name: builder(max(64, int(size * scale)), seed)
            for name, (builder, size, seed) in selected.items()}
