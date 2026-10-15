"""Original tileable PBR texture synthesis for the Four Gates region.

All maps are generated procedurally from noise and pattern primitives written for
this project; nothing is sampled, traced or derived from third-party artwork.
Each material produces a base colour, a tangent-space normal map and a packed ORM
map (R = ambient occlusion, G = roughness, B = metallic), all seamlessly tileable.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image


# ------------------------------------------------------------------ noise base
def _smooth(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def value_noise(size: int, period: int, rng: np.random.Generator) -> np.ndarray:
    """Tileable value noise; `period` cells across the texture."""
    period = max(1, int(period))
    grid = rng.random((period, period))
    coords = np.arange(size) * period / size
    i0 = np.floor(coords).astype(int) % period
    i1 = (i0 + 1) % period
    frac = _smooth(coords - np.floor(coords))
    gx0 = grid[np.ix_(i0, i0)]
    gx1 = grid[np.ix_(i1, i0)]
    gy0 = grid[np.ix_(i0, i1)]
    gy1 = grid[np.ix_(i1, i1)]
    fx = frac[:, None]
    fy = frac[None, :]
    top = gx0 * (1 - fx) + gx1 * fx
    bottom = gy0 * (1 - fx) + gy1 * fx
    return top * (1 - fy) + bottom * fy


def fbm(size: int, base_period: int, octaves: int, rng: np.random.Generator,
        gain: float = 0.5, lacunarity: int = 2) -> np.ndarray:
    total = np.zeros((size, size))
    amplitude = 1.0
    norm = 0.0
    period = base_period
    for _ in range(octaves):
        total += value_noise(size, period, rng) * amplitude
        norm += amplitude
        amplitude *= gain
        period *= lacunarity
        if period > size:
            break
    return total / max(norm, 1e-6)


def ridged(size: int, base_period: int, octaves: int, rng: np.random.Generator) -> np.ndarray:
    n = fbm(size, base_period, octaves, rng)
    return 1.0 - np.abs(n * 2.0 - 1.0)


def worley(size: int, cells: int, rng: np.random.Generator
           ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tileable Worley noise; returns (nearest, second nearest, cell id).

    The gap between the two distances is what marks a cell *edge*: it falls to
    zero along the seam between neighbouring cells and rises towards each seed.
    The nearest distance alone dips at the seed instead, so thresholding it
    draws a disc in the middle of every cell rather than a joint around its rim.
    """
    points = (rng.random((cells, cells, 2)) + np.stack(
        np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij"), axis=-1)) / cells
    coords = np.stack(np.meshgrid(np.linspace(0, 1, size, endpoint=False),
                                  np.linspace(0, 1, size, endpoint=False),
                                  indexing="ij"), axis=-1)
    best = np.full((size, size), 10.0)
    runner_up = np.full((size, size), 10.0)
    ident = np.zeros((size, size), dtype=np.int32)
    flat = points.reshape(-1, 2)
    for index, point in enumerate(flat):
        delta = np.abs(coords - point)
        delta = np.minimum(delta, 1.0 - delta)
        dist = np.hypot(delta[..., 0], delta[..., 1])
        mask = dist < best
        runner_up = np.where(mask, best, np.minimum(runner_up, dist))
        best = np.where(mask, dist, best)
        ident = np.where(mask, index, ident)
    return best, runner_up, ident


def cell_hash(ident: np.ndarray) -> np.ndarray:
    """Scatter Worley cell ids over [0, 1) so neighbours are uncorrelated.

    `worley` numbers its cells in raster order, so shading a stone by its id --
    even behind a modulo, which is a no-op whenever there are fewer cells than
    the divisor -- ramps the tile smoothly from one edge to the other. Tiled
    across a road that reads as bands marching from dark to light, not as
    stonework.
    """
    h = ident.astype(np.uint64) & np.uint64(0xFFFFFFFF)
    h = (h * np.uint64(2654435761)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(15)
    h = (h * np.uint64(2246822519)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(13)
    return ((h & np.uint64(1023)).astype(np.float64) / 1023.0)


def brick_mask(size: int, rows: int, cols: int, mortar: float = 0.035,
               offset: float = 0.5, jitter: float = 0.0,
               rng: Optional[np.random.Generator] = None):
    """Returns (mortar_mask, brick_id, u_in_brick, v_in_brick)."""
    y = np.linspace(0, rows, size, endpoint=False)
    x = np.linspace(0, cols, size, endpoint=False)
    row = np.floor(y).astype(int)
    shift = (row % 2) * offset
    xx = x[None, :] + shift[:, None]
    col = np.floor(xx).astype(int)
    fx = xx - np.floor(xx)
    fy = (y - np.floor(y))[:, None] * np.ones((1, size))
    ident = (row[:, None] * 977 + col * 131) % 9973
    mortar_x = np.minimum(fx, 1 - fx)
    mortar_y = np.minimum(fy, 1 - fy)
    thickness = mortar
    if jitter and rng is not None:
        thickness = mortar * (1.0 + jitter * (rng.random(ident.shape) - 0.5))
    mask = np.minimum(mortar_x, mortar_y * (cols / rows)) > thickness
    return mask.astype(np.float64), ident, fx, fy


def height_to_normal(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    nx = -dx
    ny = dy
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / length, ny / length, nz / length], axis=-1)


def cavity_ao(height: np.ndarray, radius: int = 3, strength: float = 1.0) -> np.ndarray:
    blurred = height.copy()
    for _ in range(radius):
        blurred = (blurred
                   + np.roll(blurred, 1, 0) + np.roll(blurred, -1, 0)
                   + np.roll(blurred, 1, 1) + np.roll(blurred, -1, 1)) / 5.0
    ao = 1.0 + (height - blurred) * 6.0 * strength
    return np.clip(ao, 0.25, 1.0)


def to_image(array: np.ndarray, srgb: bool = True) -> Image.Image:
    a = np.clip(array, 0.0, 1.0)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8))


def normal_image(normal: np.ndarray) -> Image.Image:
    return to_image(normal * 0.5 + 0.5)


def orm_image(ao: np.ndarray, roughness: np.ndarray, metallic: np.ndarray) -> Image.Image:
    return to_image(np.stack([ao, roughness, metallic], axis=-1))


def tint(base: np.ndarray, colour, variation: np.ndarray, amount: float = 0.16):
    colour = np.asarray(colour, dtype=np.float64)
    shade = (0.5 + (variation - 0.5) * 2.0 * amount)[..., None]
    return np.clip(colour[None, None, :] * (base[..., None] * 0.55 + 0.45) * shade * 2.0,
                   0.0, 1.0)


# ------------------------------------------------------------------- materials
class MaterialSet:
    """A named PBR material: base colour, normal and packed ORM."""

    def __init__(self, name, base, normal, orm, emissive=None,
                 metallic=0.0, roughness=1.0, base_factor=(1, 1, 1, 1),
                 emissive_factor=(0, 0, 0), double_sided=False,
                 alpha_mode="OPAQUE", normal_scale=1.0, uv_scale=2.0):
        self.name = name
        self.base = base
        self.normal = normal
        self.orm = orm
        self.emissive = emissive
        self.metallic = metallic
        self.roughness = roughness
        self.base_factor = base_factor
        self.emissive_factor = emissive_factor
        self.double_sided = double_sided
        self.alpha_mode = alpha_mode
        self.normal_scale = normal_scale
        self.uv_scale = uv_scale


def _pack(name, colour, height, roughness, metallic=0.0, ao_strength=1.0,
          normal_strength=2.0, emissive=None, **kwargs) -> MaterialSet:
    ao = cavity_ao(height, strength=ao_strength)
    normal = height_to_normal(height, normal_strength)
    metal = np.broadcast_to(np.asarray(metallic, dtype=np.float64), height.shape)
    rough = np.broadcast_to(np.asarray(roughness, dtype=np.float64), height.shape)
    roughness = np.clip(rough, 0.03, 1.0)
    return MaterialSet(name, to_image(colour), normal_image(normal),
                       orm_image(ao, roughness, metal),
                       emissive=None if emissive is None else to_image(emissive),
                       **kwargs)


# ---------------------------------------------------------------- the library
def build_materials(size: int = 512, hero: int = 1024, seed: int = 20260827
                    ) -> Dict[str, MaterialSet]:
    rng = np.random.default_rng(seed)
    materials: Dict[str, MaterialSet] = {}
    S, H = size, hero

    # -- pale limestone ashlar: the dominant curtain-wall and gatehouse stone --
    mask, ident, fx, fy = brick_mask(H, 16, 8, mortar=0.028, offset=0.5)
    block_variation = (ident % 97) / 96.0
    grain = fbm(H, 12, 5, rng)
    speckle = fbm(H, 96, 3, rng)
    height = mask * (0.62 + block_variation * 0.16 + grain * 0.2) + (1 - mask) * 0.12
    height += (speckle - 0.5) * 0.05
    weather = np.clip(fbm(H, 5, 4, rng) * 1.25 - 0.15, 0, 1)
    colour = tint(height, (0.702, 0.659, 0.565), block_variation * 0.35 + grain * 0.65, 0.12)
    colour *= (0.88 + 0.12 * weather)[..., None]
    colour = np.clip(colour * (0.94 + 0.10 * mask)[..., None], 0, 1)
    rough = 0.72 + 0.20 * (1 - mask) + 0.10 * grain
    materials["stone_ashlar"] = _pack("stone_ashlar", colour, height, rough,
                                      normal_strength=2.6, uv_scale=4.0)

    # -- dark rubble granite: cliffs, foundations, retaining walls --
    # Cracks follow the seams between blocks and each block takes its own tone,
    # for the same reasons the street flagstones do: cutting from the nearest
    # distance hollowed the middle of every block, and `% 71` over 81 cells
    # wrapped once, shading the tile as a ramp with a step in it.
    near, far, cell = worley(S, 9, rng)
    cracks = np.clip(1.0 - (far - near) * 70.0, 0, 1)
    rock = fbm(S, 6, 6, rng)
    height = np.clip(0.5 + rock * 0.55 - cracks * 0.45, 0, 1)
    cell_variation = 0.5 + (cell_hash(cell) - 0.5) * 0.55
    colour = tint(height, (0.455, 0.436, 0.412), cell_variation * 0.6 + rock * 0.4, 0.30)
    moss = np.clip(fbm(S, 4, 4, rng) * 1.6 - 0.75, 0, 1) * 0.5
    colour[..., 0] *= (1 - moss * 0.45)
    colour[..., 1] *= (1 - moss * 0.10)
    colour[..., 2] *= (1 - moss * 0.55)
    materials["stone_rubble"] = _pack("stone_rubble", np.clip(colour, 0, 1), height,
                                      0.86 + 0.10 * rock, normal_strength=2.0, uv_scale=4.5)

    # -- smooth dressed trim stone for cornices, arches and mouldings --
    grain = fbm(S, 10, 5, rng)
    vein = np.clip(ridged(S, 4, 4, rng) * 1.3 - 0.55, 0, 1)
    height = 0.55 + grain * 0.28 + vein * 0.10
    colour = tint(height, (0.741, 0.706, 0.620), grain, 0.12)
    colour = np.clip(colour - vein[..., None] * 0.06, 0, 1)
    materials["stone_trim"] = _pack("stone_trim", colour, height, 0.55 + 0.18 * grain,
                                    normal_strength=1.1, uv_scale=3.0)

    # -- marble for statuary --
    grain = fbm(S, 8, 5, rng)
    vein = np.clip(ridged(S, 3, 5, rng) * 1.45 - 0.62, 0, 1)
    height = 0.6 + grain * 0.15
    colour = np.clip(tint(height, (0.839, 0.827, 0.796), grain, 0.08)
                     - vein[..., None] * np.array([0.10, 0.11, 0.13]), 0, 1)
    materials["stone_marble"] = _pack("stone_marble", colour, height,
                                      0.34 + 0.10 * grain, normal_strength=0.7, uv_scale=2.5)

    # -- plaza paving: concentric ring-and-inlay stonework --
    yy, xx = np.mgrid[0:H, 0:H].astype(np.float64) / H
    cx, cy = xx - 0.5, yy - 0.5
    radius = np.hypot(cx, cy)
    angle = np.arctan2(cy, cx)
    rings = np.sin(radius * math.pi * 26.0)
    spokes = np.sin(angle * 32.0)
    joint = np.clip(1.0 - np.abs(rings) * 7.0, 0, 1)
    joint = np.maximum(joint, np.clip(1.0 - np.abs(spokes) * 7.0, 0, 1) * (radius > 0.07))
    grain = fbm(H, 14, 5, rng)
    tiles = ((np.floor(radius * 13.0) * 31.0
              + np.floor((angle + math.pi) / (math.pi / 16.0)) * 17.0) % 89) / 88.0
    height = 0.66 + grain * 0.14 + tiles * 0.08 - joint * 0.50
    colour = tint(height, (0.639, 0.596, 0.510), tiles * 0.7 + grain * 0.3, 0.20)
    # sapphire inlay bands and a gilded compass rose at the centre
    inlay = np.clip(1.0 - np.abs(np.sin(radius * math.pi * 6.5)) * 5.0, 0, 1)
    inlay *= (radius > 0.08)
    colour = np.clip(colour * (1 - inlay[..., None] * 0.92)
                     + inlay[..., None] * np.array([0.086, 0.243, 0.396]), 0, 1)
    rose_r = 0.055 + 0.075 * np.abs(np.cos(angle * 2.0)) ** 0.5
    rose = np.clip((rose_r - radius) * 60.0, 0, 1)
    ring_mark = np.clip(1.0 - np.abs(radius - 0.168) * 90.0, 0, 1)
    gold = np.clip(rose + ring_mark, 0, 1)
    colour = np.clip(colour * (1 - gold[..., None])
                     + gold[..., None] * np.array([0.639, 0.510, 0.239]), 0, 1)
    joint = np.maximum(joint, gold * 0.0)
    wear = np.clip(fbm(H, 6, 4, rng) * 1.4 - 0.35, 0, 1)
    colour *= (0.88 + 0.12 * wear)[..., None]
    materials["paving_plaza"] = _pack("paving_plaza", colour, height,
                                      0.60 + 0.22 * (1 - joint), normal_strength=2.0,
                                      uv_scale=48.0)

    # -- street flagstones --
    # The mortar runs along the seams between cells, and each stone takes a tone
    # of its own from a hash of its id. Cutting the joint from the nearest
    # distance instead sank a pit into every stone, and shading from the raw id
    # ramped the whole tile dark to light, which tiled into bands down the road.
    near, far, cell = worley(S, 7, rng)
    joint = np.clip(1.0 - (far - near) * 80.0, 0, 1)
    grain = fbm(S, 16, 4, rng)
    cell_variation = 0.5 + (cell_hash(cell) - 0.5) * 0.55
    height = 0.68 + grain * 0.16 - joint * 0.45
    colour = tint(height, (0.596, 0.557, 0.467), cell_variation * 0.75 + grain * 0.25, 0.20)
    wear = np.clip(fbm(S, 11, 4, rng) * 1.35 - 0.3, 0, 1)
    colour *= (0.90 + 0.10 * wear)[..., None]
    materials["paving_road"] = _pack("paving_road", np.clip(colour, 0, 1), height,
                                     0.72 + 0.20 * (1 - joint), normal_strength=1.0,
                                     uv_scale=6.5)

    # -- oxidised copper roofing: the signature teal roofscape --
    seam = np.abs(np.sin(np.linspace(0, math.pi * 16, H))[None, :])
    seam = np.tile(seam, (H, 1))
    standing = np.clip(1.0 - seam * 3.2, 0, 1)
    batten = np.clip(np.sin(np.linspace(0, math.pi * 64, H))[:, None] * 0.5 + 0.5, 0, 1)
    patina = fbm(H, 14, 5, rng)
    streak = fbm(H, 6, 4, rng)
    height = 0.5 + standing * 0.32 + batten * 0.05 + patina * 0.12
    verdigris = np.array([0.208, 0.494, 0.463])
    copper = np.array([0.436, 0.352, 0.246])
    blend = np.clip(patina * 1.1 + 0.40, 0, 1)[..., None]
    colour = verdigris[None, None, :] * blend + copper[None, None, :] * (1 - blend)
    colour *= (0.80 + 0.34 * (height))[..., None]
    colour *= (0.90 + 0.13 * streak)[..., None]
    materials["roof_verdigris"] = _pack("roof_verdigris", np.clip(colour, 0, 1), height,
                                        0.44 + 0.34 * patina, metallic=0.25,
                                        normal_strength=2.2, uv_scale=3.0)

    # -- blue-grey slate tiles for residential roofs --
    # `brick_mask` ids are `(row * 977 + col * 131) % 9973`; taking those modulo
    # 61 as well leaves a lattice, and the slates it shades correlate along
    # diagonals into chevrons a roof wide. Hashing the id scatters them.
    mask, ident, fx, fy = brick_mask(S, 26, 13, mortar=0.05, offset=0.5)
    slate = 0.5 + (cell_hash(ident) - 0.5) * 0.55
    grain = fbm(S, 18, 4, rng)
    height = mask * (0.6 + slate * 0.22 + grain * 0.14) + (1 - mask) * 0.16
    colour = tint(height, (0.268, 0.336, 0.372), slate * 0.8 + grain * 0.2, 0.30)
    materials["roof_slate"] = _pack("roof_slate", colour, height,
                                    0.60 + 0.22 * grain, normal_strength=2.6, uv_scale=2.4)

    # -- terracotta pantile for agricultural buildings --
    wave = np.sin(np.linspace(0, math.pi * 26, S))[None, :] * 0.5 + 0.5
    wave = np.tile(wave, (S, 1))
    rows = np.floor(np.linspace(0, 18, S))[:, None] * np.ones((1, S))
    lap = np.clip(1.0 - np.abs(np.linspace(0, 18, S) % 1.0 - 0.5) * 2.6, 0, 1)[:, None]
    grain = fbm(S, 14, 4, rng)
    height = 0.42 + wave * 0.34 + lap * 0.14 + grain * 0.12
    variation = ((rows * 13) % 47) / 46.0
    colour = tint(height, (0.556, 0.316, 0.216), variation * 0.6 + grain * 0.4, 0.24)
    materials["roof_tile"] = _pack("roof_tile", colour, height, 0.72 + 0.16 * grain,
                                   normal_strength=2.2, uv_scale=2.2)

    # -- gold / brass ornament --
    grain = fbm(S, 20, 5, rng)
    swirl = ridged(S, 6, 4, rng)
    height = 0.55 + grain * 0.2 + swirl * 0.14
    colour = tint(height, (0.842, 0.664, 0.302), grain * 0.5 + swirl * 0.5, 0.16)
    materials["metal_gold"] = _pack("metal_gold", np.clip(colour * 1.05, 0, 1), height,
                                    0.22 + 0.24 * grain, metallic=1.0,
                                    normal_strength=1.2, uv_scale=1.6)

    # -- dark wrought iron --
    grain = fbm(S, 22, 5, rng)
    pit = np.clip(worley(S, 24, rng)[0] * 12.0, 0, 1)
    height = 0.5 + grain * 0.28 - (1 - pit) * 0.18
    colour = tint(height, (0.150, 0.152, 0.164), grain, 0.30)
    materials["metal_iron"] = _pack("metal_iron", colour, height,
                                    0.44 + 0.28 * grain, metallic=0.92,
                                    normal_strength=1.6, uv_scale=1.2)

    # -- weathered dark timber --
    lines = np.linspace(0, 1, S)[None, :] * np.ones((S, 1))
    warp = fbm(S, 5, 4, rng)
    rings = np.sin((lines * 34.0 + warp * 6.0) * math.pi)
    grain = fbm(S, 26, 4, rng)
    plank = np.floor(np.linspace(0, 8, S))[:, None] * np.ones((1, S))
    gap = np.clip(1.0 - np.abs(np.linspace(0, 8, S) % 1.0 - 0.5) * 12.0, 0, 1)[:, None]
    height = 0.6 + rings * 0.10 + grain * 0.16 - gap * 0.4
    variation = ((plank * 29) % 43) / 42.0
    colour = tint(height, (0.322, 0.232, 0.164), variation * 0.5 + grain * 0.5, 0.28)
    materials["timber_dark"] = _pack("timber_dark", colour, height,
                                     0.74 + 0.18 * grain, normal_strength=2.0, uv_scale=2.0)

    # -- warm lime render for upper storeys --
    grain = fbm(S, 9, 6, rng)
    stipple = fbm(S, 60, 3, rng)
    stain = np.clip(fbm(S, 4, 4, rng) * 1.5 - 0.55, 0, 1)
    height = 0.6 + grain * 0.2 + stipple * 0.1
    colour = tint(height, (0.706, 0.655, 0.557), grain * 0.7 + stipple * 0.3, 0.14)
    colour *= (0.88 + 0.12 * (1 - stain))[..., None]
    materials["plaster_warm"] = _pack("plaster_warm", colour, height,
                                      0.80 + 0.14 * stipple, normal_strength=1.2, uv_scale=3.0)

    # -- deep blue banner cloth with a woven gold chevron --
    weave = (np.sin(np.linspace(0, math.pi * 220, S))[None, :] +
             np.sin(np.linspace(0, math.pi * 220, S))[:, None]) * 0.25 + 0.5
    fold = fbm(S, 4, 3, rng)
    u = np.linspace(0, 1, S)[None, :] * np.ones((S, 1))
    v = np.linspace(0, 1, S)[:, None] * np.ones((1, S))
    du, dv = u - 0.5, v - 0.5
    radius_uv = np.hypot(du, dv)
    theta = np.arctan2(dv, du)
    # eight-pointed compass star: the civic mark of the Four Gates
    long_points = np.abs(np.cos(theta * 2.0)) ** 4.0
    short_points = np.abs(np.sin(theta * 2.0)) ** 4.0
    star_radius = 0.028 + 0.270 * long_points + 0.185 * short_points
    emblem = np.clip((star_radius - radius_uv) * 42.0, 0, 1)
    ring = np.clip(1.0 - np.abs(radius_uv - 0.355) * 60.0, 0, 1)
    inner_ring = np.clip(1.0 - np.abs(radius_uv - 0.315) * 110.0, 0, 1)
    gold_mask = np.clip(emblem + ring + inner_ring, 0, 1)
    height = 0.55 + weave * 0.14 + fold * 0.2 + gold_mask * 0.08
    base_blue = np.array([0.055, 0.180, 0.271])
    gold = np.array([0.836, 0.672, 0.316])
    colour = base_blue[None, None, :] * (0.75 + 0.5 * (weave * 0.4 + fold * 0.6))[..., None]
    colour = colour * (1 - gold_mask[..., None]) + gold[None, None, :] * gold_mask[..., None]
    materials["cloth_banner"] = _pack("cloth_banner", np.clip(colour, 0, 1), height,
                                      0.86 - 0.2 * gold_mask, metallic=gold_mask * 0.6,
                                      normal_strength=1.0, uv_scale=1.0,
                                      double_sided=True)

    # -- teal and cream market awning canvas --
    stripe = (np.floor(np.linspace(0, 8, S)) % 2)[None, :] * np.ones((S, 1))
    weave = (np.sin(np.linspace(0, math.pi * 200, S))[:, None] * 0.5 + 0.5)
    sag = fbm(S, 5, 3, rng)
    height = 0.55 + weave * 0.12 + sag * 0.2
    teal = np.array([0.176, 0.436, 0.452])
    cream = np.array([0.900, 0.868, 0.784])
    colour = teal[None, None, :] * stripe[..., None] + cream[None, None, :] * (1 - stripe[..., None])
    colour *= (0.80 + 0.32 * (weave * 0.5 + sag * 0.5))[..., None]
    materials["canvas_awning"] = _pack("canvas_awning", np.clip(colour, 0, 1), height,
                                       0.90, normal_strength=1.0, uv_scale=1.5,
                                       double_sided=True)

    # -- sapphire beacon crystal (emissive) --
    # The bright veins follow the seams between facets. Cut from the nearest
    # distance they lit a disc in the middle of each one instead, which is the
    # same misreading the paving and the rubble carried.
    facet, second, cell = worley(S, 6, rng)
    edges = np.clip(1.0 - (second - facet) * 70.0, 0, 1)
    inner = fbm(S, 8, 5, rng)
    height = 0.5 + (1 - facet) * 0.4 + inner * 0.12
    core = np.array([0.129, 0.522, 0.980])
    bright = np.array([0.678, 0.898, 1.0])
    blend = np.clip(edges + inner * 0.6, 0, 1)[..., None]
    colour = core[None, None, :] * (1 - blend) + bright[None, None, :] * blend
    emissive = np.clip(colour * (0.78 + 0.85 * np.clip(inner * 1.5, 0, 1))[..., None], 0, 1)
    materials["crystal_blue"] = _pack("crystal_blue", np.clip(colour, 0, 1), height,
                                      0.16 + 0.2 * inner, metallic=0.0,
                                      emissive=emissive, emissive_factor=(1.0, 1.0, 1.0),
                                      normal_strength=1.4, uv_scale=1.2)

    # -- warm lamp glass (emissive) --
    # A hanging lantern is the only light in most interiors, so its globe has to
    # read as lit from any angle. Lit by the point light alone it renders as a
    # black ball: the light sits inside the shade, so every outward-facing
    # surface is turned away from it.
    speck = fbm(S, 26, 4, rng)
    swirl = fbm(S, 7, 5, rng)
    height = 0.55 + swirl * 0.2 + speck * 0.08
    warm_core = np.array([1.0, 0.812, 0.478])
    warm_hot = np.array([1.0, 0.949, 0.831])
    blend = np.clip(swirl * 0.85 + speck * 0.3, 0, 1)[..., None]
    colour = warm_core[None, None, :] * (1 - blend) + warm_hot[None, None, :] * blend
    emissive = np.clip(colour * (0.82 + 0.5 * np.clip(swirl * 1.4, 0, 1))[..., None], 0, 1)
    materials["lamp_glow"] = _pack("lamp_glow", np.clip(colour, 0, 1), height,
                                   0.34 + 0.18 * speck, metallic=0.0,
                                   emissive=emissive, emissive_factor=(1.0, 1.0, 1.0),
                                   normal_strength=0.8, uv_scale=1.0)

    # -- glazing --
    grain = fbm(S, 30, 3, rng)
    pane_mask, ident, fx, fy = brick_mask(S, 5, 4, mortar=0.06, offset=0.0)
    height = pane_mask * 0.6 + (1 - pane_mask) * 0.9
    colour = np.stack([np.full((S, S), 0.108), np.full((S, S), 0.152),
                       np.full((S, S), 0.196)], axis=-1)
    colour = colour * (0.7 + 0.6 * grain)[..., None]
    colour = np.clip(colour + (1 - pane_mask)[..., None] * np.array([0.16, 0.15, 0.13]), 0, 1)
    materials["glass_window"] = _pack("glass_window", colour, height,
                                      0.14 + 0.5 * (1 - pane_mask), metallic=0.10,
                                      normal_strength=1.6, uv_scale=2.0)

    # -- meadow grass --
    blades = fbm(S, 70, 4, rng)
    clumps = fbm(S, 8, 5, rng)
    dry = np.clip(fbm(S, 4, 4, rng) * 1.5 - 0.5, 0, 1)
    height = 0.45 + blades * 0.35 + clumps * 0.2
    green = np.array([0.192, 0.271, 0.145])
    olive = np.array([0.333, 0.333, 0.184])
    colour = green[None, None, :] * (1 - dry[..., None]) + olive[None, None, :] * dry[..., None]
    colour *= (0.60 + 0.70 * (blades * 0.50 + clumps * 0.50))[..., None]
    materials["terrain_grass"] = _pack("terrain_grass", np.clip(colour, 0, 1), height,
                                       0.94, normal_strength=0.9, uv_scale=8.0)

    # -- exposed cliff rock (terrain): isotropic, no directional banding --
    coarse = fbm(S, 4, 7, rng)
    detail = fbm(S, 13, 5, rng)
    near, far, cell_id = worley(S, 8, rng)
    crack = np.clip(1.0 - (far - near) * 55.0, 0, 1)
    height = 0.40 + coarse * 0.34 + detail * 0.26 - crack * 0.30
    facet = (cell_id % 37) / 36.0
    colour = tint(height, (0.400, 0.376, 0.345), coarse * 0.45 + detail * 0.30
                  + facet * 0.25, 0.20)
    materials["terrain_rock"] = _pack("terrain_rock", colour, height,
                                      0.90 + 0.08 * detail, normal_strength=1.1,
                                      uv_scale=17.0)

    # -- warm ochre soil / trackway --
    grit = fbm(S, 40, 4, rng)
    clods = fbm(S, 7, 5, rng)
    height = 0.5 + grit * 0.28 + clods * 0.22
    colour = tint(height, (0.451, 0.357, 0.251), grit * 0.5 + clods * 0.5, 0.22)
    materials["terrain_soil"] = _pack("terrain_soil", colour, height, 0.95,
                                      normal_strength=1.8, uv_scale=5.0)

    # -- pale shore sand --
    grit = fbm(S, 80, 3, rng)
    ripple = np.sin(np.linspace(0, math.pi * 24, S))[:, None] * np.ones((1, S))
    height = 0.5 + grit * 0.2 + ripple * 0.08
    colour = tint(height, (0.706, 0.651, 0.541), grit, 0.12)
    materials["terrain_sand"] = _pack("terrain_sand", colour, height, 0.92,
                                      normal_strength=1.2, uv_scale=5.0)

    # -- ploughed crop rows --
    rows = np.sin(np.linspace(0, math.pi * 44, S))[None, :] * np.ones((S, 1))
    crop = fbm(S, 40, 4, rng)
    clods = fbm(S, 9, 4, rng)
    height = 0.5 + rows * 0.22 + crop * 0.22 + clods * 0.14
    wheat = np.array([0.706, 0.610, 0.306])
    soil = np.array([0.428, 0.336, 0.238])
    blend = np.clip(rows * 0.5 + 0.5, 0, 1)[..., None]
    colour = wheat[None, None, :] * blend + soil[None, None, :] * (1 - blend)
    colour *= (0.72 + 0.5 * crop)[..., None]
    materials["terrain_crop"] = _pack("terrain_crop", np.clip(colour, 0, 1), height,
                                      0.92, normal_strength=1.6, uv_scale=6.0)

    # -- turquoise water --
    ripple = (np.sin(np.linspace(0, math.pi * 14, S))[:, None]
              + np.cos(np.linspace(0, math.pi * 11, S))[None, :]) * 0.25 + 0.5
    swell = fbm(S, 6, 5, rng)
    height = 0.5 + ripple * 0.24 + swell * 0.26
    colour = tint(height, (0.043, 0.322, 0.400), swell, 0.16)
    materials["water_turquoise"] = _pack("water_turquoise", np.clip(colour, 0, 1), height,
                                         0.16 + 0.12 * swell, metallic=0.02,
                                         normal_strength=1.1, uv_scale=14.0)

    # -- white water: falls and foam --
    churn = fbm(S, 10, 6, rng)
    streaks = ridged(S, 4, 5, rng)
    height = 0.4 + churn * 0.35 + streaks * 0.3
    colour = np.clip(tint(height, (0.792, 0.855, 0.878), churn, 0.12), 0, 1)
    materials["water_foam"] = _pack("water_foam", colour, height, 0.30 + 0.3 * churn,
                                    normal_strength=1.6, uv_scale=6.0)

    # -- broadleaf canopy --
    leaf = fbm(S, 46, 5, rng)
    clump = fbm(S, 7, 5, rng)
    height = 0.4 + leaf * 0.4 + clump * 0.3
    dark = np.array([0.176, 0.302, 0.148])
    light = np.array([0.418, 0.556, 0.238])
    blend = np.clip(leaf * 0.6 + clump * 0.6, 0, 1)[..., None]
    colour = dark[None, None, :] * (1 - blend) + light[None, None, :] * blend
    materials["foliage_broadleaf"] = _pack("foliage_broadleaf", np.clip(colour, 0, 1),
                                           height, 0.93, normal_strength=2.0, uv_scale=2.5)

    # -- alpine evergreen --
    needle = fbm(S, 60, 5, rng)
    clump = fbm(S, 8, 5, rng)
    height = 0.4 + needle * 0.38 + clump * 0.3
    dark = np.array([0.086, 0.186, 0.136])
    light = np.array([0.212, 0.338, 0.216])
    blend = np.clip(needle * 0.7 + clump * 0.5, 0, 1)[..., None]
    colour = dark[None, None, :] * (1 - blend) + light[None, None, :] * blend
    materials["foliage_pine"] = _pack("foliage_pine", np.clip(colour, 0, 1), height,
                                      0.95, normal_strength=2.0, uv_scale=2.0)

    # -- flowering planter bed --
    petals, _, cell = worley(S, 20, rng)
    bloom = np.clip(1.0 - petals * 14.0, 0, 1)
    leaf = fbm(S, 40, 4, rng)
    height = 0.45 + leaf * 0.3 + bloom * 0.3
    green = np.array([0.216, 0.352, 0.176])
    hue = (cell % 3)
    flower = np.where(hue[..., None] == 0, np.array([0.760, 0.372, 0.512]),
                      np.where(hue[..., None] == 1, np.array([0.836, 0.716, 0.328]),
                               np.array([0.528, 0.416, 0.756])))
    colour = green[None, None, :] * (1 - bloom[..., None]) + flower * bloom[..., None]
    colour *= (0.72 + 0.44 * leaf)[..., None]
    materials["foliage_flowers"] = _pack("foliage_flowers", np.clip(colour, 0, 1), height,
                                         0.90, normal_strength=1.6, uv_scale=1.6)

    # -- snow for the alpine skyline --
    drift = fbm(S, 8, 5, rng)
    sparkle = fbm(S, 90, 3, rng)
    height = 0.55 + drift * 0.3 + sparkle * 0.1
    colour = np.clip(tint(height, (0.859, 0.878, 0.910), drift, 0.06), 0, 1)
    materials["terrain_snow"] = _pack("terrain_snow", colour, height, 0.52 + 0.2 * drift,
                                      normal_strength=1.2, uv_scale=10.0)

    # -- thatch / hay --
    straw = ridged(S, 30, 4, rng)
    bundle = fbm(S, 10, 4, rng)
    height = 0.45 + straw * 0.36 + bundle * 0.24
    colour = tint(height, (0.664, 0.548, 0.294), straw * 0.6 + bundle * 0.4, 0.24)
    materials["thatch_straw"] = _pack("thatch_straw", colour, height, 0.95,
                                      normal_strength=2.2, uv_scale=2.0)

    # -- ceremonial avenue paving: gold and teal inlay strips along the road --
    near, far, cell = worley(H, 9, rng)
    joint = np.clip(1.0 - (far - near) * 90.0, 0, 1)
    grain = fbm(H, 16, 4, rng)
    cell_variation = 0.5 + (cell_hash(cell) - 0.5) * 0.55
    across = np.linspace(0.0, 1.0, H, endpoint=False)[None, :] * np.ones((H, 1))
    height = 0.68 + grain * 0.14 - joint * 0.42
    colour = tint(height, (0.612, 0.573, 0.482),
                  cell_variation * 0.7 + grain * 0.3, 0.18)
    def band(centre, width_uv):
        return np.clip(1.0 - np.abs(across - centre) / width_uv, 0, 1)
    teal_mask = np.clip(band(0.16, 0.022) + band(0.84, 0.022), 0, 1)
    gold_mask2 = np.clip(band(0.22, 0.010) + band(0.78, 0.010)
                         + band(0.50, 0.014), 0, 1)
    lozenge = np.clip(1.0 - (np.abs(across - 0.5) * 6.0
                             + np.abs(((np.linspace(0, 6, H)[:, None]
                                        * np.ones((1, H))) % 1.0) - 0.5) * 2.6), 0, 1)
    gold_mask2 = np.clip(gold_mask2 + lozenge * 0.55, 0, 1)
    colour = np.clip(colour * (1 - teal_mask[..., None])
                     + teal_mask[..., None] * np.array([0.106, 0.322, 0.361]), 0, 1)
    colour = np.clip(colour * (1 - gold_mask2[..., None])
                     + gold_mask2[..., None] * np.array([0.545, 0.447, 0.239]), 0, 1)
    height = height + gold_mask2 * 0.05 + teal_mask * 0.03
    materials["paving_ceremonial"] = _pack(
        "paving_ceremonial", colour, height,
        np.clip(0.70 + 0.18 * (1 - joint) - gold_mask2 * 0.16, 0.20, 1.0),
        metallic=gold_mask2 * 0.12, normal_strength=1.0, uv_scale=30.0)

    return materials
