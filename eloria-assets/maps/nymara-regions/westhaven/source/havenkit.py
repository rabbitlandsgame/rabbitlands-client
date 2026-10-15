"""Westhaven's material recipes and the region's material pin.

WHY THIS IS NOT IN `_toolkit/`
------------------------------
The production guide says a region needing new material recipes should add them
to the shared toolkit rather than fork it. It is right, and this module is
written so that promoting it is a move and not a rewrite: every recipe is a
plain `TextureSet` factory with the same signature as everything in
`textures.py`, and every spec is a plain `MaterialSpec`.

It lives here for the same reason Crownwater's `crownkit.py` does, and the
reason has not gone away: `materials.SPECS` is a module-level tuple that four
unfinished regions are all queued to append to, and three independent appends to
one tuple is the silent-corruption case that file's own comment warns about.
Westhaven adds its materials by *extending the table at build time* -
`register()` appends to `materials.SPECS` in memory before either registrar
reads it - so nothing under `_toolkit/` is modified and there is no merge
conflict to resolve. Promotion later is a copy-paste of `SPECS_EXTRA` into
`materials.SPECS` and of the factories into `textures.py`.

Every name here is `westhaven_`-prefixed, so it cannot collide with any other
region's additions even after promotion.

WHAT THE CONCEPT NEEDS THAT THE SHARED TABLE HAS NOT GOT
--------------------------------------------------------
Amberwood is a forest region and Crownwater a marble city on still water.
Westhaven is a *working port*: its surfaces are wet, salted and worn by traffic,
and the shared table has no wet stone, no tide line and no sea-bleached timber.
The six recipes below are the ones without which the painting cannot be
reproduced at all.

- `westhaven_sett` - the granite setts of the quays and ramp streets. The
  shared `cobble_paving` is a mossy woodland courtyard: rounded, organic,
  leaf-littered. A port's quay is square-cut kerbstone laid in courses, worn
  smooth in the cart tracks and dark with water in the joints.
- `westhaven_quay_plank` - the timber decking of the piers and the slipway,
  tarred and salt-bleached. `timber_grey` is a dry building plank.
- `westhaven_tide_shingle` - shingle at the water line, wet and weed-streaked.
  `shore_shingle` is a dry beach and reads bone-pale against this water.
- `westhaven_salt_turf` - the coarse coastal grass of the headland and upland.
  `meadow_grass` is inland pasture and is far too lush and too green.
- `westhaven_sea_rock` - the cliffs, the mole's outer face and the two
  lighthouse rocks. Closest to the shared `cliff_rock`, but that recipe is a
  warm inland sandstone; this is cold grey storm-washed stone. Deliberately
  *isotropic*: it covers terrain as well as walls, and a version with the tide
  zones baked in as horizontal bands tiled into hard stripes every few metres
  across the lighthouse rocks. The tide is told by `westhaven_surf` geometry.
- `westhaven_surf` - broken white water, alpha-cut. Three of the ten panels are
  substantially made of it and the region had none.
- `westhaven_harbour_water` - a retint of the shared water surface. The
  painting's harbour is a deep green-blue, not Amberwood's grey sea nor
  Crownwater's turquoise lagoon. A colour decision, not a new surface, so it
  reuses the shared texture rather than paying for a second 512px water set.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import materials as MAT
from amberwood import noise as N
from amberwood import textures as T

# The texture helpers are module-private by convention but are the documented
# way these recipes are written; every recipe in textures.py uses them.
_u8 = T._u8
_mix = T._mix
_colorize = T._colorize
_upsample = T._upsample

SETT = "westhaven_sett"
PLANK = "westhaven_quay_plank"
SHINGLE = "westhaven_tide_shingle"
TURF = "westhaven_salt_turf"
DRY_TURF = "westhaven_dry_pasture"
TRACK = "westhaven_track"
SEA_ROCK = "westhaven_sea_rock"
HARBOUR = "westhaven_harbour_water"
HARBOUR_TEX = "westhaven_harbour_tex"
SAILCLOTH = "westhaven_sailcloth"
BRASS = "westhaven_brass"
SURF = "westhaven_surf"
PANTILE = "westhaven_pantile"


# ------------------------------------------------------------- textures
def granite_sett(size: int = 512, seed: int = 401) -> T.TextureSet:
    """Square-cut granite setts laid in courses, worn in the cart tracks.

    Built from a *rectangular* cell grid rather than Worley, because setts are
    laid, not grown: the courses have to run straight and the joints have to be
    consistent width, which is exactly what Worley cannot give you. The wear is
    a pair of broad bands running with the courses - the ruts a century of
    handcarts leave - and the joints hold water, so they darken rather than
    lighten like a dry courtyard's.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    courses, along = 16, 8
    row = gy * courses
    # every other course offset by half a stone, the way setts are actually laid
    stagger = (np.floor(row).astype(int) % 2) * 0.5
    col = gx * along + stagger
    jitter = (N.tileable_value_noise(gx * 8.0, gy * 16.0, 8, 16, seed) - 0.5) * 0.10
    fx = np.abs((col + jitter) % 1.0 - 0.5) * 2.0
    fy = np.abs(row % 1.0 - 0.5) * 2.0
    joint = np.clip(np.maximum(fx, fy) * 1.0, 0.0, 1.0)
    joint = np.clip((joint - 0.80) * 5.6, 0.0, 1.0)

    rng = np.random.default_rng(seed + 7)
    stone_tone = rng.uniform(0.0, 1.0, size=(courses + 1, along + 1))
    ci = np.clip(row.astype(int), 0, courses)
    cj = np.clip(col.astype(int), 0, along)
    tone = stone_tone[ci, cj]
    grit = N.tileable_fbm(size, 34, 4, seed=seed + 3)

    height = np.clip(0.62 - joint * 0.60 + grit * 0.16 + tone * 0.07, 0.0, 1.0)
    color = _colorize(np.clip(tone * 0.62 + grit * 0.38, 0, 1),
                      (0.0, (0.104, 0.106, 0.110)), (0.4, (0.150, 0.152, 0.156)),
                      (0.75, (0.196, 0.196, 0.198)), (1.0, (0.244, 0.242, 0.240)))
    # wet joints: darker, not mossier. A working quay is scrubbed by boots.
    color = _mix(color, np.array([0.052, 0.056, 0.060]), joint * 0.82)
    # the cart ruts, running with the courses
    rut = np.exp(-((gx - 0.34) * 7.0) ** 2) + np.exp(-((gx - 0.71) * 7.0) ** 2)
    rut = np.clip(rut, 0.0, 1.0)
    color = _mix(color, np.array([0.176, 0.174, 0.170]), rut * 0.32)
    salt = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 13) * 1.9 - 1.05, 0.0, 1.0)
    color = _mix(color, np.array([0.262, 0.258, 0.250]), salt * 0.22)

    occlusion = np.clip(0.36 + (1.0 - joint) * 0.60, 0.0, 1.0)
    # polished where the carts run, coarse elsewhere
    roughness = np.clip(0.88 - rut * 0.26 - tone * 0.05, 0.0, 1.0)
    return T.TextureSet(SETT, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 3.2))


def quay_plank(size: int = 512, seed: int = 409) -> T.TextureSet:
    """Tarred and salt-bleached decking for the piers and the slipway."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    boards = 11
    row = gy * boards
    gap = np.abs(row % 1.0 - 0.5) * 2.0
    gap = np.clip((gap - 0.86) * 7.4, 0.0, 1.0)

    rng = np.random.default_rng(seed + 11)
    board_tone = rng.uniform(0.0, 1.0, size=boards + 1)[np.clip(row.astype(int), 0, boards)]
    # grain runs along the board, so it is stretched hard in x
    grain = (N.tileable_value_noise(gx * 3.0, gy * 42.0, 3, 42, seed + 5) * 0.62
             + N.tileable_value_noise(gx * 7.0, gy * 96.0, 7, 96, seed + 9) * 0.38)
    knots = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed + 17), size)
    knot = np.clip(1.0 - knots * 9.0, 0.0, 1.0)

    height = np.clip(0.60 - gap * 0.58 + grain * 0.20 - knot * 0.16, 0.0, 1.0)
    color = _colorize(np.clip(grain * 0.55 + board_tone * 0.45, 0, 1),
                      (0.0, (0.148, 0.128, 0.104)), (0.45, (0.226, 0.202, 0.168)),
                      (0.8, (0.304, 0.278, 0.238)), (1.0, (0.372, 0.346, 0.302)))
    # tar in the seams and along the caulking
    color = _mix(color, np.array([0.052, 0.048, 0.044]), gap * 0.88)
    color = _mix(color, np.array([0.048, 0.040, 0.034]), knot * 0.70)
    # sun and salt bleach the exposed faces to a pale grey
    bleach = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 23) * 1.7 - 0.72, 0.0, 1.0)
    color = _mix(color, np.array([0.238, 0.234, 0.222]), bleach * 0.52)

    occlusion = np.clip(0.40 + (1.0 - gap) * 0.56, 0.0, 1.0)
    roughness = np.clip(0.94 - bleach * 0.06, 0.0, 1.0)
    return T.TextureSet(PLANK, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 3.6))


def tide_shingle(size: int = 512, seed: int = 419) -> T.TextureSet:
    """Wet shingle at the water line: dark, weed-streaked, shell-flecked."""
    near = _upsample(N.tileable_worley(min(size, 256), 26, seed=seed), size)
    far = _upsample(N.tileable_worley(min(size, 256), 26, seed=seed, order=1), size)
    dome = np.clip(1.0 - near / np.maximum(far, 1e-6), 0.0, 1.0) ** 0.62
    fine_near = _upsample(N.tileable_worley(min(size, 256), 54, seed=seed + 13), size)
    fine_far = _upsample(N.tileable_worley(min(size, 256), 54, seed=seed + 13, order=1), size)
    fine = np.clip(1.0 - fine_near / np.maximum(fine_far, 1e-6), 0.0, 1.0) ** 0.72
    grit = N.tileable_fbm(size, 44, 4, seed=seed + 3)
    height = np.clip(dome * 0.64 + fine * 0.26 + grit * 0.12, 0.0, 1.0)

    rng = np.random.default_rng(seed + 29)
    tone = rng.uniform(0.0, 1.0, size=(26, 26))
    index = np.clip(np.arange(size) * 26 // size, 0, 25)
    pebble = tone[np.ix_(index, index)]
    # wet stone is much darker and much more saturated than the same stone dry
    color = _colorize(np.clip(pebble * 0.62 + grit * 0.38, 0, 1),
                      (0.0, (0.040, 0.042, 0.044)), (0.4, (0.072, 0.074, 0.076)),
                      (0.75, (0.116, 0.114, 0.112)), (1.0, (0.168, 0.162, 0.152)))
    weed = np.clip(N.tileable_fbm(size, 8, 4, seed=seed + 31) * 2.1 - 1.18, 0.0, 1.0)
    color = _mix(color, np.array([0.062, 0.086, 0.048]), weed * 0.74)
    wrack = np.clip(N.tileable_fbm(size, 4, 3, seed=seed + 37) * 2.4 - 1.55, 0.0, 1.0)
    color = _mix(color, np.array([0.096, 0.078, 0.040]), wrack * 0.62)
    shell = np.clip(fine * 1.6 - 1.12, 0.0, 1.0)
    color = _mix(color, np.array([0.316, 0.302, 0.276]), shell * 0.55)

    occlusion = np.clip(0.28 + dome * 0.66, 0.0, 1.0)
    # wet: low roughness, and lower still in the hollows where water stands
    roughness = np.clip(0.52 + dome * 0.26 - weed * 0.10, 0.0, 1.0)
    return T.TextureSet(SHINGLE, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 3.4))


def salt_turf(size: int = 512, seed: int = 431) -> T.TextureSet:
    """Coarse wind-cropped coastal grass with thrift, bare patches and rock."""
    blades = (N.tileable_value_noise(np.linspace(0, 46, size)[None, :].repeat(size, 0),
                                     np.linspace(0, 46, size)[:, None].repeat(size, 1),
                                     46, 46, seed) * 0.6
              + N.tileable_fbm(size, 96, 3, seed=seed + 5) * 0.4)
    clump = N.tileable_fbm(size, 9, 4, seed=seed + 11)
    height = np.clip(blades * 0.62 + clump * 0.38, 0.0, 1.0)

    # a cooler, greyer, more olive green than inland pasture
    color = _colorize(np.clip(clump * 0.58 + blades * 0.42, 0, 1),
                      (0.0, (0.062, 0.082, 0.048)), (0.35, (0.098, 0.124, 0.066)),
                      (0.7, (0.146, 0.170, 0.092)), (1.0, (0.198, 0.212, 0.126)))
    # wind-burnt tips and dead thatch, which is most of what a headland looks like
    burn = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 17) * 1.9 - 0.86, 0.0, 1.0)
    color = _mix(color, np.array([0.192, 0.176, 0.104]), burn * 0.56)
    # bare ground and stone showing through where the turf is thin
    bare = np.clip(N.tileable_fbm(size, 11, 4, seed=seed + 23) * 2.2 - 1.46, 0.0, 1.0)
    color = _mix(color, np.array([0.130, 0.120, 0.104]), bare * 0.78)
    thrift = np.clip(N.tileable_fbm(size, 22, 3, seed=seed + 41) * 2.6 - 1.92, 0.0, 1.0)
    color = _mix(color, np.array([0.226, 0.128, 0.152]), thrift * 0.50)

    occlusion = np.clip(0.44 + clump * 0.50, 0.0, 1.0)
    roughness = np.clip(0.96 - bare * 0.06, 0.0, 1.0)
    return T.TextureSet(TURF, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.2))


def track(size: int = 512, seed: int = 491) -> T.TextureSet:
    """A country cart track: packed earth, stones, wheel ruts, weedy centre.

    The upland roads used to be surfaced in `westhaven_quay_plank`, because the
    terrain class the road operator marks is PATH and PATH was pointed at the
    pier decking. A cart track over open grazing came out planked like a ship's
    deck, which is visible from the road and absurd from the air. PATH is now
    this, and the shipyard slipway - the one place decking on the ground was
    right - is authored as PAVING instead.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    grit = N.tileable_fbm(size, 38, 4, seed=seed)
    clod = N.tileable_fbm(size, 11, 4, seed=seed + 7)
    stone_near = _upsample(N.tileable_worley(min(size, 256), 30, seed=seed + 13), size)
    stone_far = _upsample(N.tileable_worley(min(size, 256), 30, seed=seed + 13,
                                            order=1), size)
    stones = np.clip(1.0 - stone_near / np.maximum(stone_far, 1e-6), 0.0, 1.0) ** 0.7
    embedded = np.clip(stones * 1.5 - 0.85, 0.0, 1.0)

    # two wheel ruts with a weedy crown between them, running along the track
    rut = (np.exp(-((gx - 0.31) * 9.0) ** 2) + np.exp(-((gx - 0.69) * 9.0) ** 2))
    rut = np.clip(rut, 0.0, 1.0)
    crown = np.exp(-((gx - 0.5) * 11.0) ** 2)

    height = np.clip(0.52 + clod * 0.22 + embedded * 0.24 + grit * 0.10
                     - rut * 0.30, 0.0, 1.0)
    color = _colorize(np.clip(clod * 0.6 + grit * 0.4, 0, 1),
                      (0.0, (0.126, 0.104, 0.076)), (0.4, (0.186, 0.156, 0.114)),
                      (0.75, (0.246, 0.212, 0.158)), (1.0, (0.300, 0.264, 0.200)))
    color = _mix(color, np.array([0.150, 0.124, 0.090]), rut * 0.44)
    color = _mix(color, np.array([0.212, 0.196, 0.176]), embedded * 0.62)
    weed = np.clip(N.tileable_fbm(size, 16, 3, seed=seed + 23) * 1.9 - 0.86, 0.0, 1.0)
    color = _mix(color, np.array([0.116, 0.140, 0.070]), crown * weed * 0.66)

    occlusion = np.clip(0.44 + (1.0 - rut) * 0.40, 0.0, 1.0)
    roughness = np.full((size, size), 0.98)
    return T.TextureSet(TRACK, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.6))


def dry_pasture(size: int = 512, seed: int = 487) -> T.TextureSet:
    """Sun-bleached grazing: dry gold and ochre, bare earth, thistle.

    The painting's upland is a patchwork of three or four tones - ochre, olive,
    dry gold, and the darker green of the tree belts. The build had one salt-turf
    recipe with noise over the whole of it, which reads uniform from any
    distance. This is the dry half of that patchwork; `assign_upland_ground`
    lays the two against each other on a long-wavelength field so the boundary
    is field-sized rather than noise-sized.
    """
    blades = (N.tileable_value_noise(
        np.linspace(0, 52, size)[None, :].repeat(size, 0),
        np.linspace(0, 52, size)[:, None].repeat(size, 1), 52, 52, seed) * 0.58
        + N.tileable_fbm(size, 104, 3, seed=seed + 5) * 0.42)
    clump = N.tileable_fbm(size, 8, 4, seed=seed + 11)
    height = np.clip(blades * 0.58 + clump * 0.42, 0.0, 1.0)

    color = _colorize(np.clip(clump * 0.56 + blades * 0.44, 0, 1),
                      (0.0, (0.146, 0.122, 0.062)), (0.35, (0.216, 0.184, 0.090)),
                      (0.7, (0.292, 0.252, 0.124)), (1.0, (0.356, 0.318, 0.166)))
    # bare earth showing through where the grazing is hardest
    bare = np.clip(N.tileable_fbm(size, 10, 4, seed=seed + 23) * 2.2 - 1.30, 0.0, 1.0)
    color = _mix(color, np.array([0.176, 0.140, 0.100]), bare * 0.72)
    # a little surviving green in the hollows
    green = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 31) * 1.9 - 1.02, 0.0, 1.0)
    color = _mix(color, np.array([0.126, 0.152, 0.080]), green * 0.52)
    thistle = np.clip(N.tileable_fbm(size, 26, 3, seed=seed + 41) * 2.6 - 2.02,
                      0.0, 1.0)
    color = _mix(color, np.array([0.204, 0.196, 0.150]), thistle * 0.50)

    occlusion = np.clip(0.46 + clump * 0.48, 0.0, 1.0)
    roughness = np.clip(0.97 - bare * 0.05, 0.0, 1.0)
    return T.TextureSet(DRY_TURF, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 2.0))


def sea_rock(size: int = 512, seed: int = 443) -> T.TextureSet:
    """Cold grey storm-washed stone: jointed, weathered, isotropic.

    NO TIDE BANDING. The first version baked the three tide zones - pale dry
    stone, a dark weed-and-barnacle band, black wet rock - straight into the
    texture as horizontal bands of `gy`, on the reasoning that panel 8's sea
    wall reads as exactly those three zones. That is true of a *vertical* face.
    This material also covers the two lighthouse rocks and the headland, which
    are terrain: on a near-horizontal surface at terrain UV scale the bands tile
    into hard stripes every three and a half metres and the whole rock mass
    reads as corrugated iron.

    The tide story is now told by geometry instead - `populate_surf` rings every
    shoreline with foam weighted by exposure - which is both correct at every
    orientation and much closer to what the panels actually show. What is left
    here is rock: angular jointing, fracture, lichen and weed as blotches rather
    than as bands.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)

    # Angular jointing in two directions, so the fracture reads as blocky stone
    # rather than as bedded sandstone.
    joint_near = _upsample(N.tileable_worley(min(size, 256), 6, seed=seed + 5), size)
    joint_far = _upsample(N.tileable_worley(min(size, 256), 6, seed=seed + 5,
                                            order=1), size)
    joint = np.clip((joint_far - joint_near) * 30.0, 0.0, 1.0)
    fine_near = _upsample(N.tileable_worley(min(size, 256), 15, seed=seed + 17), size)
    fine_far = _upsample(N.tileable_worley(min(size, 256), 15, seed=seed + 17,
                                           order=1), size)
    fine = np.clip((fine_far - fine_near) * 26.0, 0.0, 1.0)

    block = N.tileable_fbm(size, 4, 4, seed=seed + 23)
    detail = N.tileable_fbm(size, 30, 5, seed=seed + 9)
    grit = N.tileable_fbm(size, 64, 3, seed=seed + 29)

    height = np.clip(0.42 + block * 0.26 + detail * 0.22 + grit * 0.10
                     - (1.0 - joint) * 0.28 - (1.0 - fine) * 0.12, 0.0, 1.0)

    tone = np.clip(block * 0.58 + detail * 0.42, 0.0, 1.0)
    color = _colorize(tone,
                      (0.0, (0.052, 0.056, 0.060)), (0.35, (0.086, 0.092, 0.098)),
                      (0.7, (0.140, 0.146, 0.152)), (1.0, (0.198, 0.202, 0.206)))
    color = _mix(color, np.array([0.066, 0.070, 0.076]), (1.0 - joint) * 0.34)
    color = _mix(color, np.array([0.078, 0.082, 0.088]), (1.0 - fine) * 0.18)

    # lichen and weed as blotches, isotropic, so they tile in any orientation
    lichen = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 13) * 1.9 - 0.94, 0.0, 1.0)
    color = _mix(color, np.array([0.244, 0.248, 0.232]), lichen * 0.42)
    weed = np.clip(N.tileable_fbm(size, 12, 4, seed=seed + 27) * 2.1 - 1.28, 0.0, 1.0)
    color = _mix(color, np.array([0.062, 0.078, 0.044]), weed * 0.60)
    rust = np.clip(N.tileable_fbm(size, 9, 3, seed=seed + 37) * 2.2 - 1.52, 0.0, 1.0)
    color = _mix(color, np.array([0.128, 0.098, 0.066]), rust * 0.36)

    occlusion = np.clip(0.32 + joint * 0.34 + fine * 0.28, 0.0, 1.0)
    roughness = np.clip(0.90 - lichen * 0.06 + weed * 0.04, 0.0, 1.0)
    return T.TextureSet(SEA_ROCK, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 3.6))


def sailcloth(size: int = 512, seed: int = 463) -> T.TextureSet:
    """Heavy flax canvas: bolt seams, reef bands, weathering.

    The shared `canvas_awning` is a bright striped market awning - which is
    exactly right for the fish market of panel 7 and exactly wrong for a sail.
    Rigging every ship in the harbour with it turned the waterfront into a row
    of fairground tents.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # the weave: a fine cross-hatch, coarse enough to read close up
    weave = (np.sin(gx * size * 0.55) * 0.5 + 0.5) * 0.5         + (np.sin(gy * size * 0.55) * 0.5 + 0.5) * 0.5
    grime = N.tileable_fbm(size, 7, 4, seed=seed)
    # bolt seams: the cloth is sewn from strips about a fifth of the sail wide
    seam = np.abs((gx * 5.0) % 1.0 - 0.5) * 2.0
    seam = np.clip((seam - 0.90) * 12.0, 0.0, 1.0)
    # reef bands across it, where the sail is shortened in heavy weather
    band = np.abs((gy * 3.0) % 1.0 - 0.5) * 2.0
    band = np.clip((band - 0.93) * 15.0, 0.0, 1.0)

    height = np.clip(0.5 + weave * 0.12 + seam * 0.30 + band * 0.26, 0.0, 1.0)
    color = _colorize(np.clip(grime * 0.7 + weave * 0.3, 0, 1),
                      (0.0, (0.300, 0.276, 0.234)), (0.5, (0.412, 0.386, 0.334)),
                      (1.0, (0.520, 0.494, 0.436)))
    color = _mix(color, np.array([0.238, 0.216, 0.180]), seam * 0.55)
    color = _mix(color, np.array([0.262, 0.238, 0.196]), band * 0.50)
    stain = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 9) * 2.0 - 1.20, 0.0, 1.0)
    color = _mix(color, np.array([0.196, 0.178, 0.146]), stain * 0.42)

    occlusion = np.clip(0.62 + (1.0 - seam) * 0.32, 0.0, 1.0)
    roughness = np.full((size, size), 0.94)
    return T.TextureSet(SAILCLOTH, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 1.6))


def pantile(size: int = 512, seed: int = 467) -> T.TextureSet:
    """Terracotta pantiles: the concept's single loudest colour note.

    The whole painting is warm orange roofs against pale walls above dark
    green-blue water, and the shared `shingles` recipe is a grey-brown wooden
    shake. Roofing the city in it lost the colour the region is recognised by.
    Barrel tiles in overlapping courses, fired unevenly so no two runs match,
    with lichen in the shaded laps.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    courses, per_course = 13, 17
    row = gy * courses
    # every other course offset half a tile, and the barrel profile across x
    stagger = (np.floor(row).astype(int) % 2) * 0.5
    col = (gx * per_course + stagger) % 1.0
    barrel = np.sin(col * math.pi) ** 0.7
    lap = np.clip(1.0 - (row % 1.0) * 4.5, 0.0, 1.0)

    rng = np.random.default_rng(seed + 5)
    tone = rng.uniform(0.0, 1.0, size=(courses + 1, per_course + 1))
    ci = np.clip(row.astype(int), 0, courses)
    cj = np.clip((gx * per_course + stagger).astype(int), 0, per_course)
    fired = tone[ci, cj]
    grit = N.tileable_fbm(size, 30, 4, seed=seed + 3)

    height = np.clip(0.34 + barrel * 0.46 + lap * 0.22 + grit * 0.10, 0.0, 1.0)
    color = _colorize(np.clip(fired * 0.66 + grit * 0.34, 0, 1),
                      (0.0, (0.176, 0.070, 0.036)), (0.32, (0.286, 0.112, 0.052)),
                      (0.62, (0.392, 0.166, 0.078)), (0.85, (0.470, 0.222, 0.112)),
                      (1.0, (0.536, 0.290, 0.164)))
    # the shaded lap under each course
    color = _mix(color, np.array([0.098, 0.044, 0.026]), lap * 0.72)
    color = _mix(color, np.array([0.120, 0.052, 0.030]), (1.0 - barrel) * 0.34)
    lichen = np.clip(N.tileable_fbm(size, 8, 4, seed=seed + 13) * 2.1 - 1.28,
                     0.0, 1.0)
    color = _mix(color, np.array([0.186, 0.196, 0.126]), lichen * 0.58)
    salt = np.clip(N.tileable_fbm(size, 5, 3, seed=seed + 19) * 1.8 - 1.10, 0.0, 1.0)
    color = _mix(color, np.array([0.402, 0.320, 0.256]), salt * 0.30)

    occlusion = np.clip(0.34 + barrel * 0.36 + (1.0 - lap) * 0.28, 0.0, 1.0)
    roughness = np.clip(0.90 - fired * 0.08, 0.0, 1.0)
    return T.TextureSet(PANTILE, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(height, 4.0))


def surf(size: int = 512, seed: int = 479) -> T.TextureSet:
    """Broken white water: foam with holes in it, alpha-cut.

    Three of the ten detail-board panels are substantially made of breaking
    water - the lighthouse rock, the sea wall's outer face, and the whole
    southern half of the aerial - and the region had none of it. A flat white
    band would read as paint; what foam actually looks like is a lace of
    thicker and thinner water with the sea showing through, so the alpha is a
    thresholded turbulence field and the colour is near-white where the alpha is
    thick and blue-grey where it thins.

    Alpha-cut rather than blended on purpose: hundreds of overlapping foam cards
    with a blend mode sort against each other and flicker, and the same recipe
    cut at a threshold reads correctly and costs nothing to sort.
    """
    turbulence = (N.tileable_fbm(size, 5, 5, seed=seed) * 0.55
                  + N.tileable_fbm(size, 13, 4, seed=seed + 3) * 0.30
                  + N.tileable_fbm(size, 31, 3, seed=seed + 7) * 0.15)
    # a radial falloff so a single card is a patch of foam, not a square of it
    u = np.linspace(-1.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    radial = np.clip(1.0 - np.hypot(gx, gy * 1.35), 0.0, 1.0) ** 0.75
    density = np.clip(turbulence * 1.55 - 0.34, 0.0, 1.0) * radial
    alpha_mask = (density > 0.20).astype(np.float64)

    # thick foam is white; thin foam takes the water's colour through it
    thickness = np.clip(density * 2.1, 0.0, 1.0)
    color = _colorize(thickness,
                      (0.0, (0.196, 0.286, 0.306)), (0.35, (0.402, 0.510, 0.526)),
                      (0.7, (0.716, 0.780, 0.788)), (1.0, (0.930, 0.952, 0.955)))
    streak = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 11) * 1.7 - 0.75, 0.0, 1.0)
    color = _mix(color, np.array([0.860, 0.892, 0.900]), streak * 0.45)

    occlusion = np.clip(0.72 + thickness * 0.26, 0.0, 1.0)
    roughness = np.clip(0.58 + thickness * 0.30, 0.0, 1.0)
    return T.TextureSet(SURF, _u8(color), T.pack_orm(occlusion, roughness),
                        T.normal_from_height(density * 0.6, 1.6), _u8(alpha_mask))


def harbour_water(size: int = 512, seed: int = 457) -> T.TextureSet:
    """The shared water surface, retinted to the painting's green-blue."""
    base = T.water_surface(size=size, seed=seed, tone="sea")
    tinted = base.base_color.astype(np.float64) / 255.0
    tint = np.array([0.62, 1.02, 1.06])
    tinted = np.clip(tinted * tint, 0.0, 1.0)
    return T.TextureSet(HARBOUR_TEX, _u8(tinted), base.orm, base.normal)


TEXTURE_FACTORIES = {
    SETT: granite_sett,
    PLANK: quay_plank,
    SHINGLE: tide_shingle,
    TURF: salt_turf,
    DRY_TURF: dry_pasture,
    TRACK: track,
    SEA_ROCK: sea_rock,
    HARBOUR_TEX: harbour_water,
    SURF: surf,
    SAILCLOTH: sailcloth,
    PANTILE: pantile,
}

SPECS_EXTRA = (
    MAT.MaterialSpec(SETT, SETT, roughness=0.90),
    MAT.MaterialSpec(PLANK, PLANK, roughness=0.94),
    MAT.MaterialSpec(SHINGLE, SHINGLE, roughness=0.66),
    MAT.MaterialSpec(TURF, TURF, roughness=0.98),
    MAT.MaterialSpec(SEA_ROCK, SEA_ROCK, roughness=0.92),
    MAT.MaterialSpec(DRY_TURF, DRY_TURF, roughness=0.97),
    MAT.MaterialSpec(TRACK, TRACK, roughness=0.98),
    MAT.MaterialSpec(SAILCLOTH, SAILCLOTH, roughness=0.94, double_sided=True),
    MAT.MaterialSpec(PANTILE, PANTILE, roughness=0.88),
    MAT.MaterialSpec(SURF, SURF, roughness=0.62, alpha_mode="MASK",
                     alpha_cutoff=0.5, double_sided=True),
    # Brass is a tint, not a surface: it reuses the shared iron texture and
    # only recolours it, the same trick the harbour water uses. The dome of
    # panel 9 is the region's one warm metal and it was reading as cast iron.
    MAT.MaterialSpec(BRASS, "dark_iron", roughness=0.34, metallic=1.0,
                     base_color=(0.86, 0.62, 0.26, 1.0)),
    # The harbour is a deep green-blue and slightly more opaque than open sea:
    # it is dredged and busy, so it does not read clear to the bottom.
    MAT.MaterialSpec(HARBOUR, HARBOUR_TEX, roughness=0.11,
                     base_color=(1.0, 1.0, 1.0, 0.80), alpha_mode="BLEND"),
)


def register(sets: dict) -> dict:
    """Extend the shared material table with Westhaven's six recipes.

    Idempotent, so calling it twice in one process (the main build and the LOD
    build both do) does not duplicate specs. Returns the texture-set table with
    Westhaven's sets added, ready for `register_gltf_materials`.
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
    # Westhaven's own six
    SETT, PLANK, SHINGLE, TURF, DRY_TURF, TRACK, SEA_ROCK, HARBOUR,
    SAILCLOTH, PANTILE, BRASS, SURF,
    # masonry, from the shared kit
    "ashlar", "rubble_stone", "lime_plaster",
    # timber, roofing and metal - a port is built out of these
    "timber_warm", "timber_grey", "timber_dark", "carved_wood",
    "thatch_reed", "dark_iron",
    # cloth: awnings over the fish market, sails, banners
    "canvas_awning", "woven_cloth",
    # planting and the lamp glass the toolkit's lamp_post uses
    "foliage_green", "bark_dark", "undergrowth", "amber_resin",
})
"""The materials Westhaven actually uses.

Passed as `only=` to `register_gltf_materials`, which keeps the forest,
burnt-country, crystal and marble materials this region has no use for out of
the package entirely - and, more importantly, makes the package immune to
whatever any other region appends to the shared table.

Pinned to what the region *references*, not to what it might plausibly want.
`shingles`, `cobble_paving`, `bark_pale` and `water_sea` were all in this set
and all superseded by a Westhaven recipe; the build's own unreferenced-material
warning is what caught them, and each was costing its textures in every
package.
"""
