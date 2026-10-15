"""Ssarathi Ruins' material recipes.

WHY THIS IS NOT IN `_toolkit/`
------------------------------
Same reason Crownwater's `crownkit.py` is not, and written the same way so that
promoting it is a move rather than a rewrite: the recipes are plain `TextureSet`
factories with the same signature as everything in `textures.py`, and the specs
are plain `MaterialSpec` tuples. `register()` appends to `materials.SPECS` in
memory before either registrar reads it, so nothing in `_toolkit/` is modified
and there is no shared-file merge to resolve. Promotion later is a copy-paste of
`SPECS_EXTRA` into `materials.SPECS` and the factories into `textures.py`.

Every name is `ssarathi_`-prefixed, so it cannot collide with another region's
additions even after promotion.

WHAT THE CONCEPT NEEDS THAT THE EXISTING FIFTY-SEVEN HAVE NOT GOT
------------------------------------------------------------------
Ssarathi's entire colour signature is jade-green stone with gold inlay, standing
in shallow turquoise water under jungle. The shared kit has verdigris copper
(`amethyst_verdigris`) and a brassy gilt (`gilt_brass`), but no jade masonry, no
drowned silt, no lily pads, no palm frond, and no scale tiling - and panel 10 is
a close-up of scale tiling, gilt scrollwork and a shell boss, so it is a
material panel before it is anything else. These twelve are the ones without
which the painting cannot be reproduced at all.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from amberwood import materials as MAT
from amberwood import noise as N
from amberwood import textures as T

# The texture helpers are module-private by convention but are the documented
# way these recipes are written; every recipe in textures.py uses them.
_u8 = T._u8
_mix = T._mix
_colorize = T._colorize
_upsample = T._upsample

JADE_PAVING = "ssarathi_jade_paving"
SILT = "ssarathi_silt"
JUNGLE_FLOOR = "ssarathi_jungle_floor"
MOSS_STONE = "ssarathi_moss_stone"
JADE_ASHLAR = "ssarathi_jade_ashlar"
JADE_SCALE = "ssarathi_jade_scale"
GILT = "ssarathi_gilt"
SERPENT_STONE = "ssarathi_serpent_stone"
BASIN_WATER = "ssarathi_basin_water"
LILY = "ssarathi_lily"
PALM = "ssarathi_palm"
VINE = "ssarathi_vine"

# from the shared kit
STONE = "ashlar"
ROCK = "cliff_rock"
RUBBLE = "rubble_stone"
IRON = "dark_iron"
TIMBER = "timber_grey"
TIMBER_WARM = "timber_warm"
CANVAS = "canvas_awning"
FOLIAGE = "foliage_green"
BARK = "bark_dark"
BARK_PALE = "bark_pale"
UNDERGROWTH = "undergrowth"
WATER_FALL = "water_stream"


# ----------------------------------------------------------------- helpers
def _brick_grid(size: int, courses: int, seed: int, jitter: float = 0.16):
    """Running-bond block mask: returns (mortar, block_id_noise, height)."""
    rows = courses
    v = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(v, v)
    row = np.floor(gy * rows)
    offset = (row % 2.0) * 0.5
    col = np.floor(gx * rows + offset)
    fx = (gx * rows + offset) % 1.0
    fy = (gy * rows) % 1.0
    joint = 0.055
    mortar = ((fx < joint) | (fx > 1.0 - joint) |
              (fy < joint) | (fy > 1.0 - joint)).astype(np.float64)
    ident = N.tileable_value_noise(col * 1.7, row * 2.3, rows, rows, seed=seed)
    grain = N.tileable_fbm(size, 24, 4, seed=seed + 3)
    height = (1.0 - mortar) * (0.55 + ident * jitter) + grain * 0.14
    return mortar, ident, height


# ---------------------------------------------------------------- textures
def jade_paving(size: int = 512, seed: int = 601) -> T.TextureSet:
    """The city's laid stone: jade flags with a gilt inlay line in the joints.

    The gilt is what stops this reading as green concrete. In the aerial the
    causeways are not flat colour - they carry a fine warm line-work that
    catches the light, and at 1.7 m it is the only thing that says the stone was
    laid by someone rather than poured.
    """
    mortar, ident, height = _brick_grid(size, 9, seed, jitter=0.20)
    stain = N.tileable_fbm(size, 6, 5, seed=seed + 11)
    # Three passes at these values: the first was a literal read of the
    # painting's dark jade and rendered near-black; the correction overshot and
    # the whole city came out pale mint; these keep the lifted mid-tone but put
    # the green-teal bias back, which is what actually makes it read as jade
    # rather than as limestone.
    colour = _colorize(np.clip(ident * 0.7 + stain * 0.4, 0.0, 1.0),
                       (0.0, (0.086, 0.148, 0.126)),
                       (0.45, (0.132, 0.212, 0.170)),
                       (0.75, (0.178, 0.258, 0.196)),
                       (1.0, (0.226, 0.300, 0.226)))
    # gilt inlay: the joint line, broken where the gold has gone
    survives = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 19) * 1.9 - 0.62, 0.0, 1.0)
    gilt = mortar * survives
    colour = _mix(colour, np.array([0.612, 0.470, 0.176]), gilt * 0.86)
    # mortar that has lost its gold is dark
    colour = _mix(colour, np.array([0.086, 0.104, 0.090]), mortar * (1.0 - survives) * 0.8)

    moss = np.clip(N.tileable_fbm(size, 4, 5, seed=seed + 23) * 2.1 - 1.18, 0.0, 1.0)
    colour = _mix(colour, np.array([0.078, 0.132, 0.052]), moss * 0.72)

    height = height + gilt * 0.10 - mortar * 0.22
    occlusion = np.clip(0.58 + height * 0.42 - mortar * 0.20, 0.0, 1.0)
    roughness = np.clip(0.62 + mortar * 0.20 + moss * 0.16 - gilt * 0.34, 0.05, 1.0)
    return T.TextureSet(JADE_PAVING, _u8(colour),
                        T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.4))


def silt(size: int = 512, seed: int = 607) -> T.TextureSet:
    """The drowned floor: green-brown algal silt over sunken grit.

    Seen through a metre of clear water for most of the region, so it is
    deliberately low-contrast and warm-shadowed; a high-contrast floor read as
    gravel through the water plane and made the basin look ankle-deep.
    """
    base = N.tileable_fbm(size, 7, 5, seed=seed)
    fine = N.tileable_fbm(size, 26, 4, seed=seed + 5)
    # Values are high for a silt: this is read through a 0.62-alpha water plane
    # and one to two metres of it. The first pass was correct as mud and came
    # out near-black in the basin, which made ankle-deep water look like a void.
    colour = _colorize(np.clip(base * 0.75 + fine * 0.3, 0.0, 1.0),
                       (0.0, (0.128, 0.156, 0.108)),
                       (0.5, (0.196, 0.216, 0.140)),
                       (1.0, (0.268, 0.276, 0.186)))
    algae = np.clip(N.tileable_fbm(size, 4, 5, seed=seed + 13) * 2.0 - 0.92, 0.0, 1.0)
    colour = _mix(colour, np.array([0.132, 0.226, 0.132]), algae * 0.78)
    grit = np.clip(_upsample(N.tileable_worley(min(size, 256), 40, seed=seed + 7),
                             size) * 2.0 - 1.32, 0.0, 1.0)
    colour = _mix(colour, np.array([0.288, 0.284, 0.246]), grit * 0.42)
    height = base * 0.30 + grit * 0.30 + fine * 0.14
    occlusion = np.clip(0.50 + height * 0.36, 0.0, 1.0)
    roughness = np.full((size, size), 0.88) - algae * 0.10
    return T.TextureSet(SILT, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 1.9))


def jungle_floor(size: int = 512, seed: int = 613) -> T.TextureSet:
    """Wet leaf litter, root ribbons and dark loam."""
    rng = np.random.default_rng(seed)
    loam = N.tileable_fbm(size, 8, 5, seed=seed)
    colour = _colorize(loam, (0.0, (0.022, 0.026, 0.014)),
                       (0.5, (0.046, 0.052, 0.026)),
                       (1.0, (0.078, 0.084, 0.042)))
    height = loam * 0.30

    leaves_rgb = Image.new("RGB", (size, size), (0, 0, 0))
    leaves_a = Image.new("L", (size, size), 0)
    cd, ad = ImageDraw.Draw(leaves_rgb), ImageDraw.Draw(leaves_a)
    palette = [(38, 62, 22), (52, 78, 28), (30, 48, 18), (66, 88, 34),
               (74, 66, 28), (44, 40, 20)]
    for _ in range(760):
        cx, cy = rng.uniform(0, size, 2)
        length = rng.uniform(size * 0.028, size * 0.070)
        angle = rng.uniform(0, math.pi * 2)
        base = palette[int(rng.integers(0, len(palette)))]
        shade = rng.uniform(0.65, 1.20)
        fill = tuple(int(min(255, c * shade)) for c in base)
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                if abs(cx + dx - size / 2) > size or abs(cy + dy - size / 2) > size:
                    continue
                lobes = int(rng.integers(3, 6))
                T._leaf_polygon(cd, cx + dx, cy + dy, length, angle, fill, lobes=lobes)
                T._leaf_polygon(ad, cx + dx, cy + dy, length, angle, 255, lobes=lobes)
    leaf = np.asarray(leaves_rgb).astype(np.float64) / 255.0
    mask = np.asarray(leaves_a).astype(np.float64) / 255.0
    colour = _mix(colour, leaf, mask * 0.90)
    height = height + mask * 0.32

    # root ribbons: a ridged field thresholded into long sinuous strands
    roots = N.tileable_fbm(size, 3, 5, seed=seed + 29)
    strands = np.clip(1.0 - np.abs(roots - 0.5) * 7.0, 0.0, 1.0)
    colour = _mix(colour, np.array([0.098, 0.078, 0.052]), strands * 0.72)
    height = height + strands * 0.42

    moss = np.clip(N.tileable_fbm(size, 5, 5, seed=seed + 31) * 2.0 - 1.02, 0.0, 1.0)
    colour = _mix(colour, np.array([0.062, 0.126, 0.044]), moss * (1.0 - mask) * 0.80)
    occlusion = np.clip(0.40 + height * 0.48, 0.0, 1.0)
    roughness = np.full((size, size), 0.95) - moss * 0.06
    return T.TextureSet(JUNGLE_FLOOR, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.8))


def moss_stone(size: int = 512, seed: int = 617) -> T.TextureSet:
    """Ruined paving gone back to moss: the drowned quarter and the pool floors."""
    mortar, ident, height = _brick_grid(size, 7, seed, jitter=0.24)
    colour = _colorize(np.clip(ident, 0.0, 1.0),
                       (0.0, (0.094, 0.114, 0.096)),
                       (0.5, (0.140, 0.160, 0.132)),
                       (1.0, (0.186, 0.202, 0.166)))
    colour = _mix(colour, np.array([0.106, 0.122, 0.100]), mortar * 0.72)
    # heavy moss, thickest in the joints
    moss = np.clip(N.tileable_fbm(size, 5, 5, seed=seed + 17) * 1.9 - 0.72, 0.0, 1.0)
    moss = np.clip(moss + mortar * 0.42, 0.0, 1.0)
    colour = _mix(colour, np.array([0.070, 0.140, 0.058]), moss * 0.88)
    cracks = np.clip(1.0 - np.abs(N.tileable_fbm(size, 6, 5, seed=seed + 23) - 0.5) * 12.0,
                     0.0, 1.0)
    colour = _mix(colour, np.array([0.030, 0.038, 0.028]), cracks * 0.70)
    height = height - mortar * 0.26 - cracks * 0.30 + moss * 0.18
    occlusion = np.clip(0.48 + height * 0.40 - cracks * 0.22, 0.0, 1.0)
    roughness = np.clip(0.82 + moss * 0.12, 0.0, 1.0)
    return T.TextureSet(MOSS_STONE, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.6))


def jade_ashlar(size: int = 512, seed: int = 619) -> T.TextureSet:
    """The city's wall stone: coursed jade blocks, weathered to verdigris."""
    mortar, ident, height = _brick_grid(size, 6, seed, jitter=0.18)
    colour = _colorize(np.clip(ident * 0.8 + 0.1, 0.0, 1.0),
                       (0.0, (0.118, 0.176, 0.148)),
                       (0.5, (0.174, 0.238, 0.190)),
                       (1.0, (0.232, 0.288, 0.222)))
    colour = _mix(colour, np.array([0.092, 0.116, 0.102]), mortar * 0.72)
    # verdigris bloom, running downward from the joints
    bloom = np.clip(N.tileable_fbm(size, 5, 5, seed=seed + 13) * 2.0 - 0.86, 0.0, 1.0)
    colour = _mix(colour, np.array([0.148, 0.360, 0.292]), bloom * 0.72)
    lichen = np.clip(N.tileable_fbm(size, 12, 4, seed=seed + 19) * 2.2 - 1.34, 0.0, 1.0)
    colour = _mix(colour, np.array([0.180, 0.192, 0.126]), lichen * 0.44)
    height = height - mortar * 0.24
    occlusion = np.clip(0.60 + height * 0.36 - mortar * 0.18, 0.0, 1.0)
    roughness = np.clip(0.70 + mortar * 0.14 - bloom * 0.10, 0.0, 1.0)
    return T.TextureSet(JADE_ASHLAR, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.5))


def jade_scale(size: int = 512, seed: int = 631) -> T.TextureSet:
    """Panel 10's subject: overlapping jade scale tiling.

    Roofs, serpent bodies and the temple's upper courses. Drawn as real
    overlapping discs rather than a noise field, because the panel is a close-up
    and a procedural stand-in reads as fabric at that distance.
    """
    rows = 14
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    step = size / rows
    radius = step * 0.72
    for row in range(-1, rows + 2):
        offset = (row % 2) * step * 0.5
        for col in range(-1, rows + 2):
            cx = col * step + offset
            cy = row * step * 0.62
            draw.ellipse([cx - radius, cy - radius * 0.86,
                          cx + radius, cy + radius * 1.30], fill=200)
            draw.ellipse([cx - radius * 0.66, cy - radius * 0.52,
                          cx + radius * 0.66, cy + radius * 0.96], fill=255)
    scale = np.asarray(image).astype(np.float64) / 255.0
    edge = np.clip(1.0 - np.abs(scale - 0.78) * 9.0, 0.0, 1.0)

    grain = N.tileable_fbm(size, 20, 4, seed=seed)
    tone = N.tileable_fbm(size, 6, 4, seed=seed + 7)
    # Values are lifted well above a literal reading of the painting's dark
    # jade. At the first pass's values the scale tiling rendered as near-black
    # in every capture and a serpent column read as a gold slab floating over
    # nothing, because the only thing on it bright enough to see was its gilt
    # abacus. Jade is a translucent stone that catches light; it is not a
    # shadow.
    colour = _colorize(np.clip(scale * 0.7 + tone * 0.42, 0.0, 1.0),
                       (0.0, (0.072, 0.132, 0.112)),
                       (0.45, (0.142, 0.230, 0.174)),
                       (0.8, (0.206, 0.300, 0.212)),
                       (1.0, (0.272, 0.352, 0.248)))
    colour = _mix(colour, np.array([0.088, 0.126, 0.110]), edge * 0.66)
    # a gilt rim on a minority of scales, as the painting has
    gold = np.clip(N.tileable_fbm(size, 8, 3, seed=seed + 11) * 2.4 - 1.42, 0.0, 1.0)
    colour = _mix(colour, np.array([0.596, 0.462, 0.184]), edge * gold * 0.92)
    colour = _mix(colour, colour * 0.86, grain * 0.30)

    height = scale * 0.62 - edge * 0.34 + grain * 0.10
    occlusion = np.clip(0.56 + scale * 0.34 - edge * 0.30, 0.0, 1.0)
    roughness = np.clip(0.54 + grain * 0.16 - gold * edge * 0.30, 0.05, 1.0)
    return T.TextureSet(JADE_SCALE, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 3.0))


def gilt_leaf(size: int = 256, seed: int = 641) -> T.TextureSet:
    """Warm gold leaf over a dark bole, for sun discs and scrollwork.

    Warmer and dirtier than the shared `gilt_brass`, which reads as polished
    instrument metal. Ssarathi's gold is old, thin and worn through in patches.
    """
    grain = N.tileable_fbm(size, 22, 4, seed=seed)
    sweep = N.tileable_fbm(size, 5, 4, seed=seed + 3)
    colour = _colorize(np.clip(grain * 0.5 + sweep * 0.62, 0.0, 1.0),
                       (0.0, (0.300, 0.212, 0.070)),
                       (0.45, (0.560, 0.420, 0.150)),
                       (0.78, (0.660, 0.520, 0.208)),
                       (1.0, (0.740, 0.616, 0.312)))
    worn = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 9) * 2.2 - 1.42, 0.0, 1.0)
    colour = _mix(colour, np.array([0.128, 0.116, 0.086]), worn * 0.84)
    tarnish = np.clip(N.tileable_fbm(size, 13, 3, seed=seed + 15) * 2.0 - 1.16, 0.0, 1.0)
    colour = _mix(colour, np.array([0.204, 0.286, 0.226]), tarnish * 0.42)
    height = grain * 0.26 - worn * 0.20
    occlusion = np.clip(0.74 + height * 0.24, 0.0, 1.0)
    roughness = np.clip(0.26 + worn * 0.50 + tarnish * 0.24, 0.03, 1.0)
    return T.TextureSet(GILT, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 1.6))


def serpent_stone(size: int = 512, seed: int = 643) -> T.TextureSet:
    """Warm pale limestone for the carved work: faces, volutes, stelae.

    The concept's carving is noticeably lighter and warmer than its walls; the
    figures read against the jade rather than merging into it.
    """
    grain = N.tileable_fbm(size, 14, 5, seed=seed)
    bed = N.tileable_fbm(size, 4, 4, seed=seed + 5)
    colour = _colorize(np.clip(grain * 0.55 + bed * 0.55, 0.0, 1.0),
                       (0.0, (0.286, 0.264, 0.206)),
                       (0.5, (0.404, 0.374, 0.292)),
                       (1.0, (0.512, 0.478, 0.382)))
    stain = np.clip(N.tileable_fbm(size, 7, 5, seed=seed + 11) * 1.9 - 0.94, 0.0, 1.0)
    colour = _mix(colour, np.array([0.152, 0.176, 0.108]), stain * 0.60)
    pits = np.clip(_upsample(N.tileable_worley(min(size, 256), 30, seed=seed + 17),
                             size) * 2.2 - 1.52, 0.0, 1.0)
    colour = _mix(colour, np.array([0.198, 0.184, 0.150]), pits * 0.52)
    height = grain * 0.34 - pits * 0.34
    occlusion = np.clip(0.66 + height * 0.32, 0.0, 1.0)
    roughness = np.clip(0.76 + pits * 0.14, 0.0, 1.0)
    return T.TextureSet(SERPENT_STONE, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.2))


def basin_water(size: int = 512, seed: int = 647) -> T.TextureSet:
    """Turquoise standing water: broad slow ripple, almost no chop.

    The basin is enclosed and shallow, so it has none of a sea's directionality.
    """
    a = N.tileable_fbm(size, 4, 4, seed=seed)
    b = N.tileable_fbm(size, 11, 3, seed=seed + 5)
    ripple = np.sin((a * 5.4 + b * 2.1) * 2.0 * math.pi) * 0.5 + 0.5
    colour = _colorize(np.clip(ripple * 0.5 + a * 0.55, 0.0, 1.0),
                       (0.0, (0.075, 0.155, 0.128)),
                       (0.5, (0.092, 0.183, 0.145)),
                       (1.0, (0.115, 0.220, 0.173)))
    height = ripple * 0.045 + b * 0.02
    occlusion = np.full((size, size), 0.94)
    roughness = np.full((size, size), 0.40)
    return T.TextureSet(BASIN_WATER, _u8(colour), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 1.1))


def _disc_atlas(size: int, cells: int, rng, draw_one) -> tuple[Image.Image, Image.Image]:
    rgb = Image.new("RGB", (size, size), (0, 0, 0))
    alpha = Image.new("L", (size, size), 0)
    cd, ad = ImageDraw.Draw(rgb), ImageDraw.Draw(alpha)
    step = size / cells
    for row in range(cells):
        for col in range(cells):
            draw_one(cd, ad, rng, col * step, row * step, step)
    return rgb, alpha


def lily_atlas(size: int = 512, seed: int = 653) -> T.TextureSet:
    """A 3x3 atlas of lily pads and two flowers, alpha-cut.

    The lily cover is the single most identifying feature of the aerial after
    the temple: without it the water reads as an empty lake.
    """
    rng = np.random.default_rng(seed)

    def one(cd, ad, rng, x, y, step):
        cx, cy = x + step * 0.5, y + step * 0.5
        radius = step * rng.uniform(0.30, 0.42)
        notch = rng.uniform(0, math.pi * 2)
        tone = rng.uniform(0.7, 1.25)
        base = (int(46 * tone), int(88 * tone), int(38 * tone))
        cd.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=base)
        ad.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=255)
        # the pad's split
        wedge = [(cx, cy),
                 (cx + radius * 1.1 * math.cos(notch - 0.22),
                  cy + radius * 1.1 * math.sin(notch - 0.22)),
                 (cx + radius * 1.1 * math.cos(notch + 0.22),
                  cy + radius * 1.1 * math.sin(notch + 0.22))]
        cd.polygon(wedge, fill=(0, 0, 0))
        ad.polygon(wedge, fill=0)
        # rim and veins
        cd.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                   outline=(int(70 * tone), int(112 * tone), int(48 * tone)),
                   width=max(1, int(step * 0.02)))
        for k in range(9):
            angle = notch + 0.5 + k * (2.0 * math.pi - 1.0) / 9.0
            cd.line([cx, cy, cx + radius * 0.92 * math.cos(angle),
                     cy + radius * 0.92 * math.sin(angle)],
                    fill=(int(64 * tone), int(104 * tone), int(44 * tone)),
                    width=max(1, int(step * 0.012)))

    rgb, alpha = _disc_atlas(size, 3, rng, one)
    colour = np.asarray(rgb).astype(np.float64) / 255.0
    mask = np.asarray(alpha)
    # two of the nine cells carry a flower instead
    flower = Image.fromarray(np.zeros((size, size, 3), np.uint8))
    fd = ImageDraw.Draw(flower)
    fa = Image.fromarray(np.zeros((size, size), np.uint8))
    fad = ImageDraw.Draw(fa)
    step = size / 3
    for cell in ((2, 0), (0, 2)):
        cx, cy = (cell[0] + 0.5) * step, (cell[1] + 0.5) * step
        for petal in range(12):
            angle = petal * math.pi / 6.0
            length = step * (0.34 if petal % 2 == 0 else 0.26)
            tip = (cx + length * math.cos(angle), cy + length * math.sin(angle))
            side = (cx + length * 0.34 * math.cos(angle + 1.2),
                    cy + length * 0.34 * math.sin(angle + 1.2))
            other = (cx + length * 0.34 * math.cos(angle - 1.2),
                     cy + length * 0.34 * math.sin(angle - 1.2))
            fd.polygon([tip, side, (cx, cy), other], fill=(238, 226, 236))
            fad.polygon([tip, side, (cx, cy), other], fill=255)
        fd.ellipse([cx - step * 0.07, cy - step * 0.07,
                    cx + step * 0.07, cy + step * 0.07], fill=(226, 190, 84))
        fad.ellipse([cx - step * 0.07, cy - step * 0.07,
                     cx + step * 0.07, cy + step * 0.07], fill=255)
    fmask = np.asarray(fa).astype(np.float64) / 255.0
    colour = _mix(colour, np.asarray(flower).astype(np.float64) / 255.0, fmask)
    mask = np.maximum(mask, np.asarray(fa))

    height = (mask.astype(np.float64) / 255.0) * 0.5
    occlusion = np.full((size, size), 0.88)
    roughness = np.full((size, size), 0.62)
    return T.TextureSet(LILY, _u8(colour), T.pack_orm(occlusion, roughness),
                        None, mask)


def palm_atlas(size: int = 512, seed: int = 659) -> T.TextureSet:
    """A 2x2 atlas of pinnate palm fronds, alpha-cut."""
    rng = np.random.default_rng(seed)
    rgb = Image.new("RGB", (size, size), (0, 0, 0))
    alpha = Image.new("L", (size, size), 0)
    cd, ad = ImageDraw.Draw(rgb), ImageDraw.Draw(alpha)
    step = size / 2
    for row in range(2):
        for col in range(2):
            ox, oy = col * step, row * step
            tone = rng.uniform(0.72, 1.20)
            rib = (int(58 * tone), int(74 * tone), int(30 * tone))
            leaflet = (int(40 * tone), int(92 * tone), int(34 * tone))
            # the rachis, curving from the cell's bottom-centre to its top
            spine = [(ox + step * 0.5, oy + step * 0.97)]
            bend = rng.uniform(-0.16, 0.16)
            for i in range(1, 33):
                s = i / 32.0
                spine.append((ox + step * (0.5 + bend * s * s),
                              oy + step * (0.97 - 0.92 * s)))
            # Discrete leaflets, swept forward toward the tip, with a real
            # gap between each. The first version drew a quad at every spine
            # node straight out from the rib; they overlapped into one solid
            # blade and the result was a serrated broadleaf, not a palm. A
            # frond reads as a frond entirely because of the slots.
            for i in range(2, len(spine) - 1, 2):
                s = i / (len(spine) - 1.0)
                px, py = spine[i]
                span = step * 0.44 * math.sin(math.pi * min(s * 1.10, 1.0)) ** 0.55
                if span < step * 0.05:
                    continue
                # the rib's own direction here, so leaflets follow the curve
                rx = spine[i + 1][0] - spine[i - 1][0]
                ry = spine[i + 1][1] - spine[i - 1][1]
                rlen = math.hypot(rx, ry) or 1.0
                rx, ry = rx / rlen, ry / rlen
                half = step * 0.011
                for sign in (-1, 1):
                    # perpendicular, then swept 38 degrees toward the tip
                    nx, ny = -ry * sign, rx * sign
                    sweep = math.radians(38.0)
                    dx = nx * math.cos(sweep) + rx * math.sin(sweep)
                    dy = ny * math.cos(sweep) + ry * math.sin(sweep)
                    tip = (px + dx * span, py + dy * span)
                    blade = [(px - rx * half, py - ry * half), tip,
                             (px + rx * half * 2.6, py + ry * half * 2.6)]
                    cd.polygon(blade, fill=leaflet)
                    ad.polygon(blade, fill=255)
            cd.line(spine, fill=rib, width=max(2, int(step * 0.018)))
            ad.line(spine, fill=255, width=max(2, int(step * 0.018)))
    colour = np.asarray(rgb).astype(np.float64) / 255.0
    veins = N.tileable_fbm(size, 30, 3, seed=seed + 5)
    colour = _mix(colour, colour * 0.80, veins * 0.36)
    mask = np.asarray(alpha)
    occlusion = np.full((size, size), 0.84)
    roughness = np.full((size, size), 0.86)
    return T.TextureSet(PALM, _u8(colour), T.pack_orm(occlusion, roughness),
                        None, mask)


def vine_atlas(size: int = 512, seed: int = 661) -> T.TextureSet:
    """Hanging creeper: strands of small leaves falling down a wall.

    Every masonry face in the concept carries this. It is what turns a jade box
    into a ruin.
    """
    rng = np.random.default_rng(seed)
    rgb = Image.new("RGB", (size, size), (0, 0, 0))
    alpha = Image.new("L", (size, size), 0)
    cd, ad = ImageDraw.Draw(rgb), ImageDraw.Draw(alpha)
    for _ in range(26):
        x = rng.uniform(0, size)
        length = rng.uniform(size * 0.45, size * 0.98)
        drift = rng.uniform(-size * 0.10, size * 0.10)
        tone = rng.uniform(0.66, 1.20)
        stem = (int(52 * tone), int(62 * tone), int(28 * tone))
        leaf = (int(44 * tone), int(96 * tone), int(36 * tone))
        points = []
        steps = 34
        for i in range(steps):
            s = i / (steps - 1.0)
            points.append((x + drift * s * s + math.sin(s * 7.0) * size * 0.012,
                           s * length))
        cd.line(points, fill=stem, width=max(1, int(size * 0.006)))
        ad.line(points, fill=255, width=max(1, int(size * 0.006)))
        for i in range(2, steps, 2):
            px, py = points[i]
            size_l = size * rng.uniform(0.016, 0.034)
            angle = rng.uniform(0, math.pi * 2)
            T._leaf_polygon(cd, px, py, size_l, angle, leaf, lobes=3)
            T._leaf_polygon(ad, px, py, size_l, angle, 255, lobes=3)
    colour = np.asarray(rgb).astype(np.float64) / 255.0
    mask = np.asarray(alpha)
    occlusion = np.full((size, size), 0.80)
    roughness = np.full((size, size), 0.90)
    return T.TextureSet(VINE, _u8(colour), T.pack_orm(occlusion, roughness),
                        None, mask)


# --------------------------------------------------------------- registrar
TEXTURE_FACTORIES = {
    JADE_PAVING: jade_paving,
    SILT: silt,
    JUNGLE_FLOOR: jungle_floor,
    MOSS_STONE: moss_stone,
    JADE_ASHLAR: jade_ashlar,
    JADE_SCALE: jade_scale,
    GILT: gilt_leaf,
    SERPENT_STONE: serpent_stone,
    BASIN_WATER: basin_water,
    LILY: lily_atlas,
    PALM: palm_atlas,
    VINE: vine_atlas,
}

SPECS_EXTRA = (
    MAT.MaterialSpec(JADE_PAVING, JADE_PAVING, roughness=0.68),
    MAT.MaterialSpec(SILT, SILT, roughness=0.90),
    MAT.MaterialSpec(JUNGLE_FLOOR, JUNGLE_FLOOR, roughness=0.96),
    MAT.MaterialSpec(MOSS_STONE, MOSS_STONE, roughness=0.86),
    MAT.MaterialSpec(JADE_ASHLAR, JADE_ASHLAR, roughness=0.74),
    MAT.MaterialSpec(JADE_SCALE, JADE_SCALE, roughness=0.56, metallic=0.10),
    # Metallic 0.42 with a bright base blew the gilt out to white beside the
    # jade in every capture; 0.30 keeps it reading as old gold leaf.
    MAT.MaterialSpec(GILT, GILT, roughness=0.36, metallic=0.30),
    MAT.MaterialSpec(SERPENT_STONE, SERPENT_STONE, roughness=0.80),
    # The basin water. Alpha 0.62 rather than Crownwater's 0.70: Ssarathi's
    # whole subject is drowned paving you can see through, so the surface has to
    # give more of the floor away than a lagoon's would.
    MAT.MaterialSpec(BASIN_WATER, BASIN_WATER, roughness=0.40,
                     base_color=(1.0, 1.0, 1.0, 0.83), alpha_mode="BLEND"),
    MAT.MaterialSpec(LILY, LILY, roughness=0.62,
                     alpha_mode="MASK", double_sided=True),
    MAT.MaterialSpec(PALM, PALM, roughness=0.88,
                     alpha_mode="MASK", double_sided=True),
    MAT.MaterialSpec(VINE, VINE, roughness=0.92,
                     alpha_mode="MASK", double_sided=True),
)


def register(sets: dict) -> dict:
    """Extend the shared material table with Ssarathi's twelve recipes.

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
            # Generated fresh each run rather than read from preview.py's cache,
            # whose key covers only the shared recipe sources and would not
            # notice an edit to this file. That exact staleness is what made the
            # Amberwood package drift from its own source; see its change-log.
            texture = factory()
            # Alpha-cut foliage gains nothing from a normal map, and ORM is
            # low-frequency everywhere.
            drop = texture.alpha is not None
            sets[name] = texture.compact(orm_size=256, drop_normal=drop)
    return sets


# Every material this region actually references. The build pins its exported
# material set to this, so an unused recipe from the shared table cannot bloat
# the package.
MATERIALS = frozenset({
    JADE_PAVING, SILT, JUNGLE_FLOOR, MOSS_STONE, JADE_ASHLAR, JADE_SCALE,
    GILT, SERPENT_STONE, BASIN_WATER, LILY, PALM, VINE,
    STONE, ROCK, RUBBLE, IRON, TIMBER, CANVAS,
    FOLIAGE, BARK, BARK_PALE, UNDERGROWTH, WATER_FALL,
    # the lamp-post glass the shared `stonework.lamp_post` uses
    "amber_resin",
})
