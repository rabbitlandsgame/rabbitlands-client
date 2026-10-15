"""Manymouth Delta's material recipes and its stilt/boardwalk kit.

WHY THIS IS NOT IN `_toolkit/`
------------------------------
The production guide says a region needing new recipes should add them to the
shared toolkit rather than fork it, and it is right. This module is written so
that promoting it is a move rather than a rewrite: every recipe is a plain
`TextureSet` factory with the same signature as everything in `textures.py`,
and every spec is a plain `MaterialSpec`. `register()` appends to
`materials.SPECS` in memory before either registrar reads it, so nothing in
`_toolkit/` is edited and there is no merge conflict with the other region
sessions appending to the same tuple. Crownwater established this pattern for
exactly the same reason; Manymouth follows it.

Every name is `manymouth_`-prefixed, so it cannot collide even after promotion.

WHAT THE CONCEPT NEEDS THAT THE SHARED KIT HAS NOT GOT
------------------------------------------------------
Amberwood is a temperate forest, Crownwater a masonry city, Mirrorhold an
alpine one. Manymouth is a tropical brackish delta: everything a player touches
is either wet timber, woven plant fibre, silt, or water. The shared table has
fifty-seven materials and not one of them is any of those. `timber_grey` is
seasoned building timber, not the constantly-wetted decking of every panel;
`shore_shingle` is a cold pebble beach, not a silt bar; `water_lake` is
glacier-fed and opaque, and the delta's whole colour signature is clear jade
you can see the bottom through.

The eight recipes here are the ones without which the paintings cannot be
reproduced at all. Mangrove bark is deliberately *not* one of them: `bark_dark`
is close enough at any distance the player sees it, and a ninth 512px set is
bytes for nothing.
"""
from __future__ import annotations

import math

import numpy as np

from PIL import Image, ImageDraw, ImageFilter

from amberwood import architecture as A
from amberwood import materials as MAT
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as P
from amberwood import stonework as SW
from amberwood import textures as T
from amberwood import trees as TR
from amberwood.noise import Rng
from amberwood.stonework import MeshGroup, group

# The texture helpers are module-private by convention but are the documented
# way these recipes are written; every recipe in textures.py uses them.
_u8 = T._u8
_mix = T._mix
_colorize = T._colorize
_upsample = T._upsample

TEAK = "manymouth_teak"
BAMBOO = "manymouth_bamboo"
SILT = "manymouth_silt"
PADDY = "manymouth_paddy"
JUNGLE = "manymouth_jungle_floor"
SANDBAR = "manymouth_sandbar"
DELTA_WATER_TEX = "manymouth_delta_water"
GLYPH = "manymouth_glyph_stone"
FROND = "manymouth_frond"

# Water is two materials over one texture: the bright shallow channel water the
# region is mostly made of, and a darker deep pass for the dredged channels and
# the open sea in the north-west. Retinting one texture is cheaper than a second
# 512px set and is a colour decision, not a new surface.
DELTA_WATER = "manymouth_delta_shallow"
DELTA_DEEP = "manymouth_delta_deep"

# Borrowed from the shared kit rather than reinvented.
BARK = "bark_dark"
THATCH = "thatch_reed"
CARVED = "carved_wood"
BRONZE = "amethyst_verdigris"


# ------------------------------------------------------------- textures
def teak_decking(size: int = 512, seed: int = 401) -> T.TextureSet:
    """Weathered hardwood plank decking - every boardwalk in the board.

    The distinguishing feature against `timber_grey` is not colour, it is that
    these planks are permanently damp: the seams hold water, so they read darker
    and glossier than the plank faces, and the faces themselves silver off
    unevenly where the sun reaches them. Driving roughness from the seam mask as
    well as the grain is what makes a deck look wet at 1.7 m instead of looking
    like a fence laid flat.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)

    planks = 9.0
    row = np.floor(gy * planks)
    # each plank gets its own tone and its own slight length offset
    jitter = N.tileable_value_noise(row * 0.37, row * 0.11, 9, 9, seed) - 0.5
    seam_y = np.clip(1.0 - np.abs(((gy * planks) % 1.0) - 0.5) * 2.0, 0.0, 1.0)
    seam_y = np.clip((seam_y - 0.86) * 7.0, 0.0, 1.0)
    # butt joints along the run, staggered per plank
    butt = np.clip(1.0 - np.abs(((gx * 3.0 + jitter * 2.0) % 1.0) - 0.5) * 2.0,
                   0.0, 1.0)
    butt = np.clip((butt - 0.94) * 16.0, 0.0, 1.0)
    seam = np.clip(seam_y + butt, 0.0, 1.0)

    grain = N.tileable_fbm(size, 96, 3, seed=seed + 3)
    long_grain = N.tileable_value_noise(gx * 140.0, gy * 9.0, 140, 9, seed + 5)
    figure = np.clip(grain * 0.45 + long_grain * 0.55, 0.0, 1.0)

    # sun-silvering: broad, low frequency, unrelated to the plank layout
    silver = N.tileable_fbm(size, 5, 4, seed=seed + 11)

    colour = _colorize(np.clip(figure * 0.72 + jitter * 0.6 + 0.14, 0.0, 1.0),
                       (0.00, (0.196, 0.148, 0.106)),
                       (0.38, (0.318, 0.246, 0.170)),
                       (0.72, (0.436, 0.360, 0.268)),
                       (1.00, (0.548, 0.482, 0.386)))
    colour = _mix(colour, np.array([0.588, 0.578, 0.532]),
                  np.clip((silver - 0.42) * 1.5, 0.0, 1.0) * 0.46)
    # the wet seam
    colour = _mix(colour, np.array([0.086, 0.072, 0.056]), seam * 0.82)

    height = figure * 0.22 - seam * 0.75
    occlusion = np.clip(0.92 - seam * 0.55, 0.0, 1.0)
    roughness = np.clip(0.62 + figure * 0.26 - seam * 0.44, 0.05, 1.0)
    return T.TextureSet(TEAK, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 2.1))


def woven_bamboo(size: int = 512, seed: int = 409) -> T.TextureSet:
    """Split-bamboo matting, the subject of the board's material study.

    A plain over-under weave, built as two phase-shifted crowns so the warp and
    weft alternate which one is on top. The give-away detail in the painting is
    that the strips are not uniform: each one has its own tone and its own
    gloss, because they are split cane, not milled.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    strips = 16.0

    fx = (gx * strips) % 1.0
    fy = (gy * strips) % 1.0
    ix = np.floor(gx * strips)
    iy = np.floor(gy * strips)

    # over-under: warp is on top where (ix + iy) is even
    warp_over = ((ix + iy) % 2.0) < 1.0

    # each strip crowns in cross-section, so the lit ridge runs down its middle
    crown_x = np.sin(fx * math.pi)
    crown_y = np.sin(fy * math.pi)
    height = np.where(warp_over, crown_x * 0.9, crown_y * 0.9)

    # per-strip tone, keyed on the strip index so it is constant along a strip
    tone_x = N.tileable_value_noise(ix * 0.5, np.zeros_like(ix), 16, 1, seed)
    tone_y = N.tileable_value_noise(np.zeros_like(iy), iy * 0.5, 1, 16, seed + 3)
    tone = np.where(warp_over, tone_x, tone_y)

    # cane fibre runs along the strip, so the two directions get different fields
    fibre = np.where(warp_over,
                     N.tileable_value_noise(gx * 180.0, gy * 16.0, 180, 16, seed + 9),
                     N.tileable_value_noise(gx * 16.0, gy * 180.0, 16, 180, seed + 11))

    colour = _colorize(np.clip(tone * 0.66 + fibre * 0.34, 0.0, 1.0),
                       (0.00, (0.352, 0.276, 0.164)),
                       (0.35, (0.552, 0.446, 0.256)),
                       (0.70, (0.712, 0.604, 0.372)),
                       (1.00, (0.826, 0.734, 0.496)))
    # the shadow in the gap where the under-strip passes beneath
    gap = np.clip(1.0 - np.abs(np.where(warp_over, crown_x, crown_y)) * 2.6,
                  0.0, 1.0)
    colour = _mix(colour, np.array([0.148, 0.112, 0.070]), gap * 0.55)

    occlusion = np.clip(0.94 - gap * 0.42, 0.0, 1.0)
    # split cane keeps a waxy skin on the outer face
    roughness = np.clip(0.48 + fibre * 0.30 + gap * 0.20, 0.0, 1.0)
    return T.TextureSet(BAMBOO, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height * 0.5 + 0.5, 2.6))


def delta_silt(size: int = 512, seed: int = 419) -> T.TextureSet:
    """Wet tidal mud: the bank of every channel and the floor of the study panel.

    Silt is not "brown noise". What makes it read is the drying pattern - broad
    polygonal cracks where a bar has been out of the water long enough, over a
    wet sheen everywhere else - plus the fine mica glint the concept's
    foreground has. The cracks come from a Worley cell border, which is what mud
    actually does.
    """
    cells = _upsample(N.tileable_worley(min(size, 256), 9, seed=seed), size)
    # Worley returns distance-to-feature; the crack is the cell *border*, so it
    # is the high end of that field, not the low.
    crack = np.clip((cells - 0.52) * 4.2, 0.0, 1.0)

    dryness = N.tileable_fbm(size, 4, 4, seed=seed + 3)
    crack = crack * np.clip((dryness - 0.34) * 2.4, 0.0, 1.0)

    grit = N.tileable_fbm(size, 64, 4, seed=seed + 7)
    sheen = N.tileable_fbm(size, 7, 3, seed=seed + 11)

    colour = _colorize(np.clip(grit * 0.42 + dryness * 0.58, 0.0, 1.0),
                       (0.00, (0.096, 0.086, 0.068)),
                       (0.34, (0.174, 0.150, 0.110)),
                       (0.68, (0.268, 0.230, 0.168)),
                       (1.00, (0.372, 0.332, 0.250)))
    # the dried crust between cracks lifts and pales
    colour = _mix(colour, np.array([0.436, 0.398, 0.312]),
                  np.clip(dryness - 0.5, 0.0, 1.0) * 0.7)
    colour = _mix(colour, np.array([0.052, 0.046, 0.036]), crack * 0.75)

    height = grit * 0.20 + dryness * 0.14 - crack * 0.62
    occlusion = np.clip(0.88 - crack * 0.5, 0.0, 1.0)
    # wet where it is not cracked; that contrast is the whole read
    roughness = np.clip(0.34 + crack * 0.5 + dryness * 0.28
                        - np.clip(sheen - 0.5, 0.0, 1.0) * 0.24, 0.05, 1.0)
    return T.TextureSet(SILT, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.9))


def paddy_water(size: int = 512, seed: int = 431) -> T.TextureSet:
    """A flooded rice terrace seen from above: young green over standing water.

    This is a *ground* material, not a water plane. The terraces in panel 7 are
    read as a surface a player walks beside, and what identifies them is the
    planting grid - rows of seedling clumps in standing water - not the water
    itself. The regular clump lattice is the entire tell; without it this is
    just green mud.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    rows = 22.0

    jx = (N.tileable_value_noise(gx * rows, gy * rows, int(rows), int(rows),
                                 seed) - 0.5) * 0.34
    jy = (N.tileable_value_noise(gx * rows, gy * rows, int(rows), int(rows),
                                 seed + 3) - 0.5) * 0.34
    cx = ((gx * rows + jx) % 1.0) - 0.5
    cy = ((gy * rows + jy) % 1.0) - 0.5
    clump = np.clip(1.0 - np.hypot(cx, cy) * 3.1, 0.0, 1.0)

    blade = N.tileable_fbm(size, 150, 2, seed=seed + 7)
    water = N.tileable_fbm(size, 11, 4, seed=seed + 11)

    # the water between the clumps: it mirrors sky, so it is pale and blue-ish
    water_colour = _colorize(water,
                             (0.0, (0.118, 0.176, 0.164)),
                             (0.5, (0.204, 0.286, 0.268)),
                             (1.0, (0.372, 0.446, 0.412)))
    green = _colorize(np.clip(blade * 0.6 + clump * 0.4, 0.0, 1.0),
                      (0.00, (0.150, 0.244, 0.088)),
                      (0.45, (0.256, 0.396, 0.126)),
                      (0.80, (0.396, 0.542, 0.186)),
                      (1.00, (0.532, 0.652, 0.268)))
    colour = _mix(water_colour, green, np.clip(clump * 1.35, 0.0, 1.0))

    height = clump * 0.6 + blade * 0.12
    occlusion = np.clip(0.72 + clump * 0.24, 0.0, 1.0)
    roughness = np.clip(0.22 + clump * 0.62, 0.0, 1.0)
    return T.TextureSet(PADDY, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.7))


def jungle_floor(size: int = 512, seed: int = 439) -> T.TextureSet:
    """Wet tropical leaf litter: big palm fronds, not a temperate leaf mould.

    `forest_floor` is fine-grained deciduous litter. A palm island's floor is
    coarse - whole frond segments, fibrous husk, and moss in the shade - so the
    frequency here is deliberately an order lower than the shared recipe's, and
    the green is the blue-green of permanent damp rather than Amberwood's gold.
    """
    frond = _upsample(N.tileable_worley(min(size, 256), 13, seed=seed), size)
    litter = N.tileable_fbm(size, 28, 4, seed=seed + 3)
    fine = N.tileable_fbm(size, 90, 3, seed=seed + 7)
    moss = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 11) * 1.7 - 0.62,
                   0.0, 1.0)

    colour = _colorize(np.clip(frond * 0.42 + litter * 0.40 + fine * 0.18,
                               0.0, 1.0),
                       (0.00, (0.086, 0.076, 0.048)),
                       (0.30, (0.164, 0.138, 0.076)),
                       (0.58, (0.256, 0.212, 0.116)),
                       (0.82, (0.344, 0.296, 0.164)),
                       (1.00, (0.446, 0.396, 0.230)))
    colour = _mix(colour, np.array([0.118, 0.208, 0.118]), moss * 0.62)

    height = frond * 0.44 + litter * 0.32 + fine * 0.14
    occlusion = np.clip(0.74 + frond * 0.20 - moss * 0.10, 0.0, 1.0)
    roughness = np.clip(0.78 + litter * 0.20 - moss * 0.26, 0.0, 1.0)
    return T.TextureSet(JUNGLE, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.6))


def delta_sandbar(size: int = 512, seed: int = 443) -> T.TextureSet:
    """The pale bars the channels braid around: shell sand over grey silt.

    Warmer and much paler than `shore_shingle`, which is a cold pebble beach.
    The ripple lattice is what says "this was under moving water an hour ago".
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    warp = (N.tileable_fbm(size, 5, 4, seed=seed) - 0.5) * 1.4
    ripple = np.sin((gy * 26.0 + warp * 4.0) * 2.0 * math.pi) * 0.5 + 0.5
    grain = N.tileable_fbm(size, 128, 3, seed=seed + 3)
    shell = np.clip(_upsample(N.tileable_worley(min(size, 256), 40, seed=seed + 7),
                              size) * 1.5 - 0.85, 0.0, 1.0)
    wet = N.tileable_fbm(size, 4, 4, seed=seed + 11)

    colour = _colorize(np.clip(grain * 0.5 + ripple * 0.34 + shell * 0.16,
                               0.0, 1.0),
                       (0.00, (0.404, 0.372, 0.310)),
                       (0.40, (0.578, 0.540, 0.452)),
                       (0.74, (0.712, 0.676, 0.582)),
                       (1.00, (0.828, 0.800, 0.716)))
    colour = _mix(colour, np.array([0.898, 0.886, 0.842]), shell * 0.6)
    # the damp end of the bar
    colour = _mix(colour, colour * 0.62, np.clip(wet - 0.54, 0.0, 1.0) * 1.6)

    height = ripple * 0.34 + grain * 0.22 + shell * 0.20
    occlusion = np.clip(0.90 - ripple * 0.10, 0.0, 1.0)
    roughness = np.clip(0.86 - np.clip(wet - 0.54, 0.0, 1.0) * 1.1, 0.10, 1.0)
    return T.TextureSet(SANDBAR, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.4))


def delta_water(size: int = 512, seed: int = 449) -> T.TextureSet:
    """Clear brackish jade, the region's entire colour signature.

    `water_lake` is Mirrorhold's glacier melt - opaque, rock-floured, blue.
    `water_sea` is cold and nearly black. glTF clamps `baseColorFactor` to
    [0,1], so a factor can only ever darken: the concept's luminous jade has to
    be authored into the texture or it cannot be reached at all. That is the
    same finding Crownwater recorded, and it holds here for a different hue.

    Delta water differs from Crownwater's lagoon in one way that matters: it
    carries suspended silt from upstream, so it is greener, and the surface is
    broken by current rather than by swell. The chop field is therefore
    stretched along one axis instead of isotropic.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # current-stretched chop: long in x, short in y
    current = N.tileable_value_noise(gx * 6.0, gy * 21.0, 6, 21, seed)
    swell = N.tileable_fbm(size, 4, 4, seed=seed + 3)
    fine = N.tileable_fbm(size, 52, 3, seed=seed + 7)
    height = swell * 0.42 + current * 0.40 + fine * 0.18

    colour = _colorize(np.clip(swell * 0.46 + current * 0.54, 0.0, 1.0),
                       (0.00, (0.062, 0.278, 0.276)),
                       (0.36, (0.128, 0.470, 0.428)),
                       (0.68, (0.242, 0.664, 0.578)),
                       (1.00, (0.436, 0.826, 0.732)))
    # silt bloom where the current turns: pale jade, not white foam
    bloom = np.clip((fine - 0.58) * 2.8, 0.0, 1.0)
    colour = _mix(colour, np.array([0.706, 0.876, 0.804]), bloom * 0.46)

    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.05 + current * 0.18, 0.0, 1.0)
    return T.TextureSet(DELTA_WATER_TEX, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.2))


def glyph_stone(size: int = 512, seed: int = 457) -> T.TextureSet:
    """The drowned ruins' stone: dark wet basalt with a teal glyph inlay.

    The arch, the stelae and the cave mouth all read the same way in the board -
    near-black stone, water-polished, cut with a band of glowing script. The
    glow is carried in the material's emissive channel rather than baked bright
    into base colour, so it still reads as an inlay in daylight and as a light
    source at dusk.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)

    block = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed), size)
    pit = np.clip(_upsample(N.tileable_worley(min(size, 256), 34, seed=seed + 3),
                            size) * 1.6 - 0.72, 0.0, 1.0)
    grain = N.tileable_fbm(size, 72, 4, seed=seed + 7)
    wet = N.tileable_fbm(size, 6, 3, seed=seed + 11)

    colour = _colorize(np.clip(block * 0.36 + grain * 0.44 + pit * 0.20,
                               0.0, 1.0),
                       (0.00, (0.070, 0.082, 0.086)),
                       (0.42, (0.128, 0.146, 0.152)),
                       (0.76, (0.196, 0.216, 0.222)),
                       (1.00, (0.272, 0.294, 0.300)))

    # the inlay: a banded lattice of short strokes, not a continuous line
    band = np.clip(1.0 - np.abs(((gy * 5.0) % 1.0) - 0.5) * 5.6, 0.0, 1.0)
    band = np.clip((band - 0.55) * 3.2, 0.0, 1.0)
    stroke = N.tileable_value_noise(gx * 44.0, gy * 5.0, 44, 5, seed + 13)
    glyph = band * np.clip((stroke - 0.46) * 3.4, 0.0, 1.0)

    teal = np.array([0.286, 0.912, 0.842])
    colour = _mix(colour, teal * 0.86, glyph * 0.94)

    height = block * 0.30 + grain * 0.16 + pit * 0.30 - glyph * 0.45
    occlusion = np.clip(0.80 - pit * 0.30 + glyph * 0.14, 0.0, 1.0)
    # water-polished: low roughness broadly, rough where it has spalled
    roughness = np.clip(0.30 + pit * 0.46 + grain * 0.14
                        - np.clip(wet - 0.48, 0.0, 1.0) * 0.5, 0.05, 1.0)
    return T.TextureSet(GLYPH, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 2.2))


def frond_atlas(size: int = 512, seed: int = 463) -> T.TextureSet:
    """Alpha-masked palm fronds: 2x2 cells, one arching pinnate leaf each.

    The single most important texture in the region, and the reason it is worth
    a ninth recipe. The shared `foliage_atlas` draws open sprays of small round
    leaves, which is a broadleaf tree; instanced on a palm profile it produces a
    dark blob on a stick, and the whole delta reads as temperate woodland with
    the colour turned up. A palm's silhouette is a *pinnate blade* - a long
    curved rachis with narrow leaflets combed off both sides, thinning to a
    point - and nothing else reads as a palm at any distance.

    Each cell holds one frond rising from the cell's base edge, which is the
    convention `trees.py` expects: the card's bottom edge is the twig.
    """
    rng = np.random.default_rng(seed)
    colour_image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha_image = Image.new("L", (size, size), 0)
    depth_image = Image.new("L", (size, size), 0)
    colour_draw = ImageDraw.Draw(colour_image)
    alpha_draw = ImageDraw.Draw(alpha_image)
    depth_draw = ImageDraw.Draw(depth_image)

    greens = [(62, 104, 38), (78, 126, 46), (96, 148, 56), (52, 88, 32),
              (116, 168, 66), (44, 76, 30), (86, 134, 50)]

    half = size // 2
    for cell_y in range(2):
        for cell_x in range(2):
            ox, oy = cell_x * half, cell_y * half
            # the rachis: an arc from the base edge, curving over as it rises
            lean = rng.uniform(-0.42, 0.42)
            tip_drop = rng.uniform(0.10, 0.30)
            steps = 26
            spine = []
            for i in range(steps + 1):
                t = i / steps
                x = ox + half * (0.5 + lean * t * t * 0.92)
                y = oy + half * (0.97 - 0.94 * t + tip_drop * t * t)
                spine.append((x, y, t))
            rachis_width = max(2, size // 190)
            colour_draw.line([(x, y) for x, y, _ in spine],
                             fill=(74, 84, 40), width=rachis_width)
            alpha_draw.line([(x, y) for x, y, _ in spine], fill=255,
                            width=rachis_width)
            depth_draw.line([(x, y) for x, y, _ in spine], fill=150,
                            width=rachis_width)

            # leaflets combed off both sides, longest at mid-blade
            for i in range(1, steps):
                x, y, t = spine[i]
                px, py, _ = spine[i - 1]
                nx, ny, _ = spine[i + 1]
                tangent = math.atan2(ny - py, nx - px)
                # a lens envelope along the blade: short at base and at tip
                envelope = math.sin(math.pi * min(1.0, t * 1.04)) ** 0.7
                length = half * (0.07 + 0.34 * envelope)
                if length < 2.0:
                    continue
                for side in (-1.0, 1.0):
                    if rng.uniform() < 0.06:
                        continue      # the odd missing leaflet
                    # leaflets sweep back toward the tip, not straight out
                    sweep = math.pi * 0.5 - 0.52 - 0.30 * t
                    angle = tangent + side * sweep + rng.normal(0.0, 0.06)
                    lx = x + math.cos(angle) * length
                    ly = y + math.sin(angle) * length
                    shade = 0.78 + 0.34 * (0.5 + 0.5 * side) * envelope
                    base = greens[int(rng.integers(0, len(greens)))]
                    fill = tuple(int(min(255, c * shade)) for c in base)
                    # thick enough to survive the far detail tier: at one
                    # pixel a leaflet aliases away entirely and the frond
                    # reads as a bare stick
                    width = max(2, int(size / 128 * (0.6 + 0.9 * envelope)))
                    colour_draw.line([(x, y), (lx, ly)], fill=fill, width=width)
                    alpha_draw.line([(x, y), (lx, ly)], fill=255, width=width)
                    depth_draw.line([(x, y), (lx, ly)],
                                    fill=int(90 + 150 * envelope), width=width)

    colour = np.asarray(colour_image).astype(np.float64) / 255.0
    alpha = np.asarray(alpha_image).astype(np.float64) / 255.0
    depth = np.asarray(depth_image.filter(ImageFilter.GaussianBlur(1.2))
                       ).astype(np.float64) / 255.0
    variation = N.tileable_fbm(size, 6, 4, seed=seed + 9)
    colour = colour * (0.70 + 0.44 * variation)[..., None]
    alpha_mask = (alpha > 0.5).astype(np.float64)
    occlusion = np.clip(0.42 + depth * 0.66, 0.0, 1.0)
    roughness = np.full((size, size), 0.86) - depth * 0.10
    return T.TextureSet(FROND, _u8(colour),
                        T.pack_orm(occlusion, roughness,
                                   np.zeros_like(roughness)),
                        T.normal_from_height(depth * 0.5, 1.8),
                        _u8(alpha_mask))


TEXTURE_FACTORIES = {
    TEAK: teak_decking,
    BAMBOO: woven_bamboo,
    SILT: delta_silt,
    PADDY: paddy_water,
    JUNGLE: jungle_floor,
    SANDBAR: delta_sandbar,
    DELTA_WATER_TEX: delta_water,
    GLYPH: glyph_stone,
    FROND: frond_atlas,
}

SPECS_EXTRA = (
    MAT.MaterialSpec(TEAK, TEAK, roughness=0.82),
    MAT.MaterialSpec(BAMBOO, BAMBOO, roughness=0.68),
    MAT.MaterialSpec(SILT, SILT, roughness=0.72),
    MAT.MaterialSpec(PADDY, PADDY, roughness=0.58),
    MAT.MaterialSpec(JUNGLE, JUNGLE, roughness=0.96),
    MAT.MaterialSpec(SANDBAR, SANDBAR, roughness=0.86),
    # NO EMISSIVE. glTF's `emissiveFactor` has no mask without an
    # `emissiveTexture`, and `materials.MaterialSpec` has no field for one, so
    # a factor applies uniformly across the whole surface. On a crystal that is
    # correct and it is why the Amethyst specs use it; on near-black ruin stone
    # it swamps the albedo completely, and the first real client frame of this
    # region came back with the great arch as a solid glowing teal ring - the
    # geometry perfect, the stone gone. The inlay is painted into the base
    # colour instead, which reads as an inlay in daylight and does not glow at
    # dusk. See modeling-assumptions.md.
    MAT.MaterialSpec(GLYPH, GLYPH, roughness=0.44),
    MAT.MaterialSpec(FROND, FROND, roughness=0.90,
                     alpha_mode="MASK", alpha_cutoff=0.42, double_sided=True),
    # Two passes over one water texture.
    # Alpha 0.44, not Crownwater's 0.70. This region's water is shallower and
    # the aerial's signature is that the bars read *through* it - a channel you
    # cannot see the bottom of is a channel that might as well be a wall. At
    # 0.62 the first captures came back as flat cyan with no bed visible at all.
    MAT.MaterialSpec(DELTA_WATER, DELTA_WATER_TEX, roughness=0.08,
                     base_color=(1.0, 1.0, 1.0, 0.44), alpha_mode="BLEND"),
    # Much darker than the shallow pass, and nearly opaque. The aerial's
    # strongest structural read is the tonal step between bar-edge shallows and
    # the dredged channels; at 0.82 alpha over a pale bed that step was almost
    # invisible in the first client frame.
    MAT.MaterialSpec(DELTA_DEEP, DELTA_WATER_TEX, roughness=0.10,
                     base_color=(0.20, 0.40, 0.44, 0.93), alpha_mode="BLEND"),
)


def register(sets: dict) -> dict:
    """Extend the shared material table with Manymouth's recipes.

    Idempotent, so calling it twice in one process (the main build and the LOD
    build both do) does not duplicate specs.
    """
    existing = {spec.name for spec in MAT.SPECS}
    additions = tuple(s for s in SPECS_EXTRA if s.name not in existing)
    if additions:
        MAT.SPECS = MAT.SPECS + additions
        MAT.BY_NAME.update({spec.name: spec for spec in additions})
    for name, factory in TEXTURE_FACTORIES.items():
        if name not in sets:
            # generated fresh each run rather than read from preview.py's cache,
            # whose key covers only the shared recipe sources and would not
            # notice an edit to this file
            if name == FROND:
                # alpha-cut foliage gains nothing from a normal map, and that
                # map is a third of the set's bytes
                sets[name] = factory().compact(orm_size=128, drop_normal=True)
            else:
                sets[name] = factory().compact(orm_size=256)
    return sets


# The exact set of materials this region references. Pinned by name so the GLB
# embeds only these: without `only=`, the package embeds the whole shared
# library - about ten megabytes of forest and burnt-country textures Manymouth
# never uses - and worse, its contents would change whenever another region
# appends to the shared table. `export_glb` fails loudly if a kit piece pulls in
# something not listed, and warns if something listed is never referenced.
MATERIALS = frozenset({
    # Manymouth's own
    TEAK, BAMBOO, SILT, PADDY, JUNGLE, SANDBAR, GLYPH, FROND,
    DELTA_WATER, DELTA_DEEP,
    # timber, fibre and metal from the shared kit
    "bark_dark", "carved_wood", "thatch_reed", "timber_dark", "timber_warm",
    "canvas_awning", "woven_cloth", "amethyst_verdigris",
    # planting
    "foliage_green", "undergrowth",
    # the terrain classes the surface rules can still produce
    "cliff_rock", "leaf_path",
})
