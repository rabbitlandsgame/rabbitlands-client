"""Shared Crownwater material recipes and opt-in registration.

Promoted without changing the generated texels or existing material names.
The exterior keeps its crownkit import as a compatibility entry point.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import materials as MAT
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import stonework as SW
from amberwood import textures as T

# The texture helpers are module-private by convention but are the documented
# way these recipes are written; every recipe in textures.py uses them.
_u8 = T._u8
_mix = T._mix
_colorize = T._colorize
_upsample = T._upsample

MARBLE = "crownwater_marble"
VERDIGRIS = "crownwater_verdigris"
GILT = "crownwater_gilt"
MOSAIC = "crownwater_mosaic"
SAND = "crownwater_sand"
LAGOON_TEX = "crownwater_lagoon_water"

STONE = "ashlar"
IRON = "dark_iron"


# ------------------------------------------------------------- textures
def veined_marble(size: int = 512, seed: int = 307) -> T.TextureSet:
    """Pale marble with grey veining, for the city's walls and columns.

    The veins are a turbulence-displaced sine field, which is the cheap standard
    trick and reads correctly at both plaza scale and 1.7 m eye height: broad
    drifting bands with fine branching inside them.
    """
    turbulence = N.tileable_fbm(size, 5, 5, seed=seed) - 0.5
    fine = N.tileable_fbm(size, 17, 4, seed=seed + 3) - 0.5
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    field = np.sin((gx * 2.4 + gy * 1.1 + turbulence * 2.6 + fine * 0.55)
                   * 2.0 * math.pi)
    veins = np.clip(1.0 - np.abs(field) * 3.4, 0.0, 1.0)
    grain = N.tileable_fbm(size, 48, 3, seed=seed + 7)

    colour = _colorize(np.clip(grain * 0.6 + 0.4, 0.0, 1.0),
                       (0.0, (0.786, 0.780, 0.752)),
                       (0.6, (0.874, 0.868, 0.842)),
                       (1.0, (0.936, 0.932, 0.912)))
    colour = _mix(colour, np.array([0.404, 0.416, 0.432]), veins * 0.62)
    height = grain * 0.25 + veins * 0.10
    occlusion = np.clip(0.80 - veins * 0.16, 0.0, 1.0)
    roughness = np.clip(0.34 + grain * 0.16 + veins * 0.10, 0.0, 1.0)
    return T.TextureSet(MARBLE, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.5))


def verdigris_copper(size: int = 512, seed: int = 311) -> T.TextureSet:
    """Patinated copper roofing: the teal-green of every dome in the concept.

    Patina is not uniform. It sits thickest where water lies and runs thin on
    ridges and edges, so the recipe drives the green with a low-frequency mask
    and lets warm bare copper come through where that mask is weak - which is
    what stops a dome reading as a flat green ball.
    """
    patina = N.tileable_fbm(size, 6, 5, seed=seed)
    streak = N.tileable_fbm(size, 3, 4, seed=seed + 3)
    # vertical running, as rainwater actually weathers a dome
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    _, gy = np.meshgrid(u, u)
    runs = np.clip(N.tileable_fbm(size, 22, 3, seed=seed + 5) * 1.6 - 0.5, 0.0, 1.0)
    coverage = np.clip(patina * 0.72 + streak * 0.42 + gy * 0.14, 0.0, 1.0)
    coverage = np.clip((coverage - 0.24) * 1.9, 0.0, 1.0)

    copper = np.empty((size, size, 3))
    copper[..., 0] = 0.474
    copper[..., 1] = 0.256
    copper[..., 2] = 0.148
    green = _colorize(np.clip(patina * 0.8 + runs * 0.3, 0.0, 1.0),
                      (0.0, (0.176, 0.428, 0.396)),
                      (0.5, (0.264, 0.560, 0.502)),
                      (1.0, (0.372, 0.658, 0.580)))
    colour = _mix(copper, green, coverage)
    seam = np.clip(1.0 - np.abs(((gy * 14.0) % 1.0) - 0.5) * 12.0, 0.0, 1.0)
    colour = _mix(colour, colour * 0.72, seam * 0.5)

    height = patina * 0.35 + runs * 0.18 + seam * 0.30
    occlusion = np.clip(0.74 + patina * 0.18 - seam * 0.22, 0.0, 1.0)
    roughness = np.clip(0.30 + coverage * 0.52, 0.0, 1.0)
    metallic = np.clip(0.95 - coverage * 0.80, 0.0, 1.0)
    return T.TextureSet(VERDIGRIS, _u8(colour),
                        T.pack_orm(occlusion, roughness, metallic),
                        T.normal_from_height(height, 2.4))


def gilt_leaf(size: int = 256, seed: int = 313) -> T.TextureSet:
    """Gold leaf over a worked ground, for finials, ribs and gate ornament."""
    beat = _upsample(N.tileable_worley(min(size, 256), 22, seed=seed), size)
    fine = N.tileable_fbm(size, 34, 3, seed=seed + 3)
    height = beat * 0.62 + fine * 0.24
    colour = _colorize(np.clip(beat * 0.7 + fine * 0.3, 0.0, 1.0),
                       (0.0, (0.706, 0.512, 0.164)),
                       (0.55, (0.914, 0.734, 0.288)),
                       (1.0, (0.986, 0.892, 0.520)))
    tarnish = np.clip(N.tileable_fbm(size, 8, 4, seed=seed + 11) * 1.7 - 0.95,
                      0.0, 1.0)
    colour = _mix(colour, np.array([0.336, 0.288, 0.152]), tarnish * 0.55)
    occlusion = np.clip(0.58 + height * 0.40, 0.0, 1.0)
    roughness = np.clip(0.17 + tarnish * 0.42 + fine * 0.10, 0.0, 1.0)
    # Deliberately NOT fully metallic. The client renders through OpenGL 3.3
    # compatibility with no image-based lighting, so a metallic=1 surface has
    # nothing to reflect and renders near-black - every gilt finial and the
    # panel-10 bollard came back as dark blobs. Treating the gold as a bright
    # dielectric with a little metal in it is wrong physically and right on
    # screen, until there is an environment map to reflect.
    metallic = np.clip(0.34 - tarnish * 0.12, 0.0, 1.0)
    return T.TextureSet(GILT, _u8(colour),
                        T.pack_orm(occlusion, roughness, metallic),
                        T.normal_from_height(height, 1.8))


def mosaic_paving(size: int = 512, seed: int = 317, tile_px: int = 10) -> T.TextureSet:
    """Tesserae paving for the plazas: small cut stones in a banded palette.

    Built as an explicit grid rather than from worley noise. Worley gives a
    distance field, not cell identities, so every tile ends up the same colour as
    its neighbours and the result reads as blotchy stone - which is exactly what
    the first two attempts here looked like. A nearest-neighbour upsample of a
    per-cell random array gives each tessera its own hard-edged colour, and the
    grout is a real gap between them.

    Detail-board panel 3 is a compass-rose mosaic; this is its *field*. The rose
    itself is geometry, laid as an inlaid disc in the plaza.
    """
    # ceil, not floor: with tile_px=10 and size=512 a floored count gives
    # 510 px of tiles and the arrays no longer broadcast.
    cells = -(-size // tile_px)
    rng = np.random.default_rng(seed)

    # per-tessera colour draw, nearest-upsampled so edges stay hard
    pick = rng.random((cells, cells))
    shade = rng.random((cells, cells))
    pick = np.repeat(np.repeat(pick, tile_px, 0), tile_px, 1)[:size, :size]
    shade = np.repeat(np.repeat(shade, tile_px, 0), tile_px, 1)[:size, :size]

    # broad concentric banding, so the field has the concept's ring structure
    u = np.linspace(-1.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    ring = np.clip((np.hypot(gx, gy) * 1.9) % 1.0, 0.0, 1.0)
    mixed = np.clip(pick * 0.55 + ring * 0.45, 0.0, 1.0)

    # Tesserae are ~5 cm at the paving's UV scale, so from more than a few
    # metres away the field is not read tile by tile - it is averaged. A
    # half-cream half-teal checker averages to a noisy cyan and aliases badly
    # from the air, which is how the first in-client aerial came back. The
    # palette is therefore mostly warm stone, with teal as an accent that only
    # appears in the darkest part of the ring banding.
    colour = _colorize(mixed,
                       (0.00, (0.722, 0.704, 0.650)),
                       (0.42, (0.664, 0.646, 0.592)),
                       (0.70, (0.606, 0.590, 0.540)),
                       (0.88, (0.352, 0.520, 0.532)),
                       (1.00, (0.236, 0.412, 0.458)))
    colour = colour * (0.93 + shade * 0.13)[..., None]

    # grout: a hard gap on the tile lattice, slightly irregular
    ax = np.arange(size)
    lattice_x = (ax % tile_px < 1).astype(float)
    lattice_y = lattice_x.copy()
    grout = np.clip(lattice_x[None, :] + lattice_y[:, None], 0.0, 1.0)
    jitter = N.tileable_fbm(size, 70, 2, seed=seed + 5)
    grout = np.clip(grout * (0.72 + jitter * 0.5), 0.0, 1.0)
    colour = _mix(colour, np.array([0.322, 0.310, 0.290]), grout * 0.92)

    height = (1.0 - grout) * 0.55 + shade * 0.10
    occlusion = np.clip(0.92 - grout * 0.46, 0.0, 1.0)
    roughness = np.clip(0.40 + grout * 0.32 + shade * 0.10, 0.0, 1.0)
    return T.TextureSet(MOSAIC, _u8(np.clip(colour, 0.0, 1.0)),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 2.6))


def lagoon_sand(size: int = 512, seed: int = 331) -> T.TextureSet:
    """Pale carbonate sand for the lagoon floor.

    This is the single biggest lever on how the water reads. A turquoise lagoon
    is not turquoise water - it is a blue-green filter over a *bright pale
    floor*. Left on Amberwood's grey shore shingle, Crownwater's water came back
    slate blue in client capture no matter what tint the water material carried.
    """
    ripple_a = N.tileable_fbm(size, 9, 4, seed=seed)
    ripple_b = N.tileable_fbm(size, 26, 3, seed=seed + 3)
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    ripples = np.sin((gy * 5.0 + ripple_a * 1.8) * 2.0 * math.pi) * 0.5 + 0.5
    height = ripples * 0.42 + ripple_b * 0.30
    # Bright, but not white. At 0.94 luminance the shelves blew out under the
    # client's sun and the shallows read as snow rather than as turquoise; the
    # water tint has to have something to sit on, not something to be lost in.
    colour = _colorize(np.clip(ripples * 0.55 + ripple_b * 0.45, 0.0, 1.0),
                       (0.0, (0.412, 0.452, 0.402)),
                       (0.5, (0.512, 0.530, 0.462)),
                       (1.0, (0.596, 0.598, 0.520)))
    weed = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 7) * 1.8 - 1.02,
                   0.0, 1.0)
    colour = _mix(colour, np.array([0.352, 0.470, 0.336]), weed * 0.58)
    occlusion = np.clip(0.82 + height * 0.16, 0.0, 1.0)
    roughness = np.clip(0.72 + ripple_b * 0.18, 0.0, 1.0)
    return T.TextureSet(SAND, _u8(colour),
                        T.pack_orm(occlusion, roughness, np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.6))


def lagoon_water(size: int = 512, seed: int = 337) -> T.TextureSet:
    """Bright tropical lagoon water.

    Amberwood's `water_sea` is a cold north-Atlantic surface; multiplying it by
    a turquoise base-colour factor cannot brighten it, because a factor only
    ever scales down. glTF clamps baseColorFactor to [0,1], so the only way to
    reach the concept's turquoise is to author the texture at that colour.
    """
    swell = N.tileable_fbm(size, 4, 4, seed=seed)
    chop = N.tileable_fbm(size, 15, 4, seed=seed + 3)
    fine = N.tileable_fbm(size, 44, 3, seed=seed + 7)
    height = swell * 0.5 + chop * 0.34 + fine * 0.16

    colour = _colorize(np.clip(swell * 0.55 + chop * 0.45, 0.0, 1.0),
                       (0.00, (0.106, 0.412, 0.516)),
                       (0.40, (0.180, 0.606, 0.640)),
                       (0.72, (0.324, 0.774, 0.752)),
                       (1.00, (0.508, 0.876, 0.836)))
    # glitter on the crests, which is what sells a lit water plane with no
    # animated shader behind it
    crest = np.clip((fine - 0.62) * 3.4, 0.0, 1.0)
    colour = _mix(colour, np.array([0.86, 0.96, 0.94]), crest * 0.5)

    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.06 + chop * 0.16, 0.0, 1.0)
    return T.TextureSet(LAGOON_TEX, _u8(colour),
                        T.pack_orm(occlusion, roughness,
                                   np.zeros_like(roughness)),
                        T.normal_from_height(height, 1.1))


TEXTURE_FACTORIES = {
    MARBLE: veined_marble,
    VERDIGRIS: verdigris_copper,
    GILT: gilt_leaf,
    MOSAIC: mosaic_paving,
    SAND: lagoon_sand,
    LAGOON_TEX: lagoon_water,
}

LAGOON = "crownwater_lagoon"

SPECS_EXTRA = (
    # Reuses the shared water texture and only retints it: the concept's
    # turquoise is a colour decision, not a new surface, and a second 512px
    # water set would cost bytes for nothing.
    MAT.MaterialSpec(LAGOON, LAGOON_TEX, roughness=0.09,
                     base_color=(1.0, 1.0, 1.0, 0.70), alpha_mode="BLEND"),
    MAT.MaterialSpec(MARBLE, MARBLE, roughness=0.38),
    MAT.MaterialSpec(VERDIGRIS, VERDIGRIS, roughness=0.62, metallic=0.35),
    MAT.MaterialSpec(GILT, GILT, roughness=0.28, metallic=0.34),
    MAT.MaterialSpec(MOSAIC, MOSAIC, roughness=0.52),
    MAT.MaterialSpec(SAND, SAND, roughness=0.78),
)


def register(sets: dict) -> dict:
    """Extend the shared material table with Crownwater's four recipes.

    Idempotent, so calling it twice in one process (the main build and the LOD
    build both do) does not duplicate specs. Returns the texture-set table with
    Crownwater's sets added, ready for `register_gltf_materials`.
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
            sets[name] = factory().compact(orm_size=256)
    return sets


MATERIALS = frozenset({
    # Crownwater's own four
    MARBLE, VERDIGRIS, GILT, MOSAIC,
    # masonry and metal, from the shared kit
    "ashlar", "cliff_rock", "dark_iron", "cobble_paving",
    "lime_plaster",
    # timber, cloth and the lamp glass the toolkit's lamp_post uses
    "timber_warm", "timber_dark", "carved_wood",
    "canvas_awning", "amber_resin",
    # ground and planting
    "forest_floor", "meadow_grass", "foliage_green", SAND,
    "bark_pale",
    # water
    "water_pool", LAGOON,
})
"""The materials Crownwater actually uses.

Passed as `only=` to `register_gltf_materials`, which keeps the eleven forest
and burnt-country materials Crownwater has no use for out of the package
entirely - and, more importantly, makes this region immune to whatever any other
region appends to the shared table.
"""
