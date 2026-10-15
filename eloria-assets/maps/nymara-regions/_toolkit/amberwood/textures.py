"""Procedural PBR texture authoring for Amberwood.

Every map is generated here from noise and drawn geometry - nothing is traced,
sampled or converted from any existing game's art. Each material returns a
base-colour map, an ORM map (R = ambient occlusion, G = roughness,
B = metallic, the standard glTF packing) and a tangent-space normal map.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import noise as N


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _u8(array: np.ndarray) -> np.ndarray:
    return np.clip(array * 255.0 + 0.5, 0, 255).astype(np.uint8)


def to_png(array: np.ndarray, mode: str = "RGB") -> bytes:
    image = Image.fromarray(array, mode)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def normal_from_height(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    """Tangent-space normal map (OpenGL +Y up) from a tiling height field."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.stack([nx / length, ny / length, nz / length], axis=-1)
    return _u8(out * 0.5 + 0.5)


def pack_orm(occlusion: np.ndarray, roughness: np.ndarray,
             metallic: np.ndarray | float = 0.0) -> np.ndarray:
    if np.isscalar(metallic):
        metallic = np.full_like(occlusion, float(metallic))
    return _u8(np.stack([np.clip(occlusion, 0, 1), np.clip(roughness, 0, 1),
                         np.clip(metallic, 0, 1)], axis=-1))


def _mix(a, b, t):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    t = np.asarray(t)[..., None] if np.asarray(t).ndim == 2 else t
    return a * (1.0 - t) + b * t


def _colorize(mask: np.ndarray, *stops) -> np.ndarray:
    """stops = (position, (r,g,b)) pairs; mask in [0,1] -> RGB float image."""
    positions = np.array([s[0] for s in stops])
    colors = np.array([s[1] for s in stops], dtype=np.float64)
    out = np.zeros(mask.shape + (3,))
    for channel in range(3):
        out[..., channel] = np.interp(mask, positions, colors[:, channel])
    return out


def _upsample(array: np.ndarray, size: int) -> np.ndarray:
    if array.shape[0] == size:
        return array
    image = Image.fromarray((np.clip(array, 0, 1) * 65535).astype(np.uint16))
    image = image.resize((size, size), Image.BICUBIC)
    return np.asarray(image).astype(np.float64) / 65535.0


@dataclass
class TextureSet:
    name: str
    base_color: np.ndarray
    orm: np.ndarray
    normal: np.ndarray
    alpha: np.ndarray | None = None

    def reduced(self, base_size: int = 256, orm_size: int = 128) -> "TextureSet":
        """A half-resolution copy for the reduced package."""
        def resize(array, size, mode):
            if array is None or array.shape[0] <= size:
                return array
            return np.asarray(Image.fromarray(array, mode).resize(
                (size, size), Image.BOX))
        alpha = self.alpha
        if alpha is not None and alpha.shape[0] > base_size:
            alpha = np.asarray(Image.fromarray(alpha, "L").resize(
                (base_size, base_size), Image.BOX))
        return TextureSet(self.name,
                          resize(self.base_color, base_size, "RGB"),
                          resize(self.orm, orm_size, "RGB"),
                          None, alpha)

    def compact(self, orm_size: int = 256, drop_normal: bool = False,
                normal_size: int | None = None) -> "TextureSet":
        """Trim the maps that do not need full resolution.

        Ambient occlusion and roughness carry low-frequency information, so a
        quarter-resolution ORM is indistinguishable in play and a quarter of the
        bytes. Alpha-cut foliage gains nothing from a normal map.
        """
        if self.orm.shape[0] > orm_size:
            self.orm = np.asarray(Image.fromarray(self.orm, "RGB").resize(
                (orm_size, orm_size), Image.BOX))
        if drop_normal:
            self.normal = None
        elif normal_size and self.normal is not None and self.normal.shape[0] > normal_size:
            self.normal = np.asarray(Image.fromarray(self.normal, "RGB").resize(
                (normal_size, normal_size), Image.BILINEAR))
        return self

    def images(self) -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        if self.alpha is None:
            out[f"{self.name}_basecolor"] = to_png(self.base_color, "RGB")
        else:
            rgba = np.dstack([self.base_color, self.alpha])
            out[f"{self.name}_basecolor"] = to_png(rgba, "RGBA")
        out[f"{self.name}_orm"] = to_png(self.orm, "RGB")
        if self.normal is not None:
            out[f"{self.name}_normal"] = to_png(self.normal, "RGB")
        return out

    def memory_bytes(self, bytes_per_texel: int = 4) -> int:
        total = self.base_color.shape[0] ** 2 + self.orm.shape[0] ** 2
        if self.normal is not None:
            total += self.normal.shape[0] ** 2
        return total * bytes_per_texel


# --------------------------------------------------------------------------
# material recipes
# --------------------------------------------------------------------------

def bark(size: int = 512, seed: int = 11, hue: str = "oak") -> TextureSet:
    """Deep vertical fissures with lichen and moss on the shaded side."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # long vertical ridges that wander, split by horizontal plate breaks
    # anisotropic fbm: features stretched ~8x vertically, still irregular
    stretched = np.zeros((size, size))
    amplitude, frequency, norm = 1.0, 2, 0.0
    for octave in range(4):
        stretched += amplitude * N.tileable_value_noise(
            gx * frequency * 9.0, gy * frequency, frequency * 9, frequency,
            seed + octave * 977)
        norm += amplitude
        amplitude *= 0.42
        frequency *= 2
    stretched /= norm
    # ridged transform turns the field into fissures with sharp bottoms
    fissure = 1.0 - np.abs(stretched * 2.0 - 1.0)
    plates = _upsample(N.tileable_worley(min(size, 256), 10, seed=seed + 4), size)
    fine = N.tileable_fbm(size, 26, 4, seed=seed + 8)
    height = fissure * 0.66 + plates * 0.14 + fine * 0.12
    height += N.tileable_fbm(size, 6, 3, seed=seed + 12) * 0.10
    height = np.clip((height - 0.18) * 1.35, 0.0, 1.0)
    ridge = np.clip(height * 1.15, 0.0, 1.0)

    if hue == "oak":
        stops = ((0.0, (0.052, 0.040, 0.031)), (0.30, (0.128, 0.100, 0.074)),
                 (0.62, (0.268, 0.216, 0.160)), (0.85, (0.392, 0.330, 0.252)),
                 (1.0, (0.505, 0.442, 0.352)))
    elif hue == "pale":
        stops = ((0.0, (0.086, 0.080, 0.072)), (0.30, (0.196, 0.184, 0.164)),
                 (0.62, (0.352, 0.336, 0.302)), (0.85, (0.492, 0.474, 0.432)),
                 (1.0, (0.612, 0.596, 0.552)))
    else:  # dark, wet, old-growth
        stops = ((0.0, (0.032, 0.026, 0.022)), (0.30, (0.082, 0.068, 0.056)),
                 (0.62, (0.170, 0.144, 0.114)), (0.85, (0.258, 0.224, 0.178)),
                 (1.0, (0.340, 0.302, 0.246)))
    color = _colorize(ridge, *stops)

    # moss sits in the fissures on one side of the trunk, not everywhere
    side = np.clip((0.62 - gx) * 2.4, 0.0, 1.0)
    moss = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 21) * 2.2 - 1.05, 0.0, 1.0)
    moss *= np.clip(1.0 - ridge * 0.9, 0.0, 1.0) * (0.35 + 0.65 * side)
    color = _mix(color, np.array([0.118, 0.176, 0.086]), moss * 0.85)

    # lichen as flat irregular patches, not speckle
    cells = _upsample(N.tileable_worley(min(size, 256), 12, seed=seed + 31), size)
    patch = np.clip((0.30 - cells) * 4.5, 0.0, 1.0)
    patch *= np.clip(N.tileable_fbm(size, 16, 4, seed=seed + 33) * 2.0 - 0.85, 0.0, 1.0)
    color = _mix(color, np.array([0.468, 0.492, 0.428]), np.clip(patch, 0.0, 1.0) * 0.7)

    occlusion = np.clip(0.24 + height * 0.92, 0.0, 1.0)
    roughness = np.clip(0.88 + (1.0 - ridge) * 0.10 - moss * 0.06, 0.0, 1.0)
    return TextureSet(f"bark_{hue}", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 5.0))


def _leaf_polygon(draw: ImageDraw.ImageDraw, cx: float, cy: float, length: float,
                  angle: float, fill, lobes: int = 5) -> None:
    """A lobed, oak-like leaf silhouette - not a billboard rectangle."""
    points = []
    steps = 34
    for i in range(steps + 1):
        t = i / steps
        # half-outline, mirrored below
        lobe = 0.5 + 0.5 * math.cos(t * math.pi * 2.0 * lobes)
        width = math.sin(math.pi * min(max(t, 0.02), 0.98)) ** 0.75
        r = length * (0.16 + 0.30 * width * (0.55 + 0.45 * lobe))
        x = -length * 0.5 + t * length
        points.append((x, -r))
    for i in range(steps, -1, -1):
        t = i / steps
        lobe = 0.5 + 0.5 * math.cos(t * math.pi * 2.0 * lobes)
        width = math.sin(math.pi * min(max(t, 0.02), 0.98)) ** 0.75
        r = length * (0.16 + 0.30 * width * (0.55 + 0.45 * lobe))
        x = -length * 0.5 + t * length
        points.append((x, r))
    c, s = math.cos(angle), math.sin(angle)
    draw.polygon([(cx + px * c - py * s, cy + px * s + py * c) for px, py in points], fill=fill)


def foliage_atlas(size: int = 512, seed: int = 47, palette: str = "amber") -> TextureSet:
    """Alpha-masked leaf-spray atlas: 2x2 cells, each an irregular open spray.

    Sprays are deliberately not round and not solid - they have gaps, a denser
    base near the twig and loose single leaves at the outside, so a canopy built
    from them reads as leaves rather than as a row of spheres.
    """
    rng = np.random.default_rng(seed)
    color_image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha_image = Image.new("L", (size, size), 0)
    depth_image = Image.new("L", (size, size), 0)
    color_draw = ImageDraw.Draw(color_image)
    alpha_draw = ImageDraw.Draw(alpha_image)
    depth_draw = ImageDraw.Draw(depth_image)

    palettes = {
        "amber": [(188, 104, 26), (152, 76, 20), (214, 138, 40), (120, 56, 16),
                  (230, 168, 66), (92, 42, 14), (172, 116, 34)],
        "gold": [(204, 144, 36), (172, 114, 28), (226, 176, 66), (140, 88, 22),
                 (238, 200, 104), (112, 68, 18), (188, 152, 54)],
        "rust": [(132, 44, 20), (104, 32, 16), (158, 62, 26), (78, 24, 14),
                 (176, 88, 34), (62, 20, 12), (140, 72, 28)],
        "green": [(58, 82, 30), (44, 66, 24), (76, 100, 38), (32, 50, 20),
                  (92, 116, 48), (24, 38, 16), (68, 88, 34)],
        "dead": [(92, 80, 62), (74, 64, 50), (108, 96, 76), (60, 52, 42),
                 (124, 110, 90), (50, 44, 36), (100, 88, 70)],
    }
    colors = palettes.get(palette, palettes["amber"])

    half = size // 2
    for cell_y in range(2):
        for cell_x in range(2):
            ox, oy = cell_x * half, cell_y * half
            # spray axis: leaves march out from the twig at the cell's base edge
            axis = rng.uniform(-0.55, 0.55)
            stem_x = ox + half * (0.5 + axis * 0.25)
            stem_y = oy + half * 0.94
            spine = []
            steps = 7
            for i in range(steps):
                t = (i + 1) / steps
                spine.append((stem_x + axis * half * 0.42 * t + rng.normal(0, half * 0.03),
                              stem_y - half * 0.86 * t))
            # twig
            twig_width = max(1, size // 300)
            color_draw.line([(stem_x, stem_y)] + spine, fill=(58, 44, 30), width=twig_width)
            alpha_draw.line([(stem_x, stem_y)] + spine, fill=255, width=twig_width)

            for i, (px, py) in enumerate(spine):
                t = (i + 1) / steps
                # fewer, larger leaves toward the tip; a gap or two on purpose
                count = int(round(30 * (1.25 - 0.6 * t)))
                for _ in range(count):
                    if rng.uniform() < 0.14:
                        continue
                    spread = half * (0.10 + 0.30 * (1.0 - t) + 0.16 * t)
                    lx = px + rng.normal(0.0, spread)
                    ly = py + rng.normal(0.0, spread * 0.72)
                    length = rng.uniform(half * 0.075, half * 0.155) * (1.15 - 0.30 * t)
                    angle = math.atan2(ly - stem_y, lx - stem_x) + rng.normal(0.0, 0.7)
                    base = colors[int(rng.integers(0, len(colors)))]
                    # depth shading: leaves further from the spine sit in front
                    reach = min(1.0, math.hypot(lx - px, ly - py) / max(spread, 1e-3))
                    shade = 0.52 + 0.50 * reach
                    fill = tuple(int(min(255, c * shade)) for c in base)
                    lobes = int(rng.integers(3, 6))
                    _leaf_polygon(color_draw, lx, ly, length, angle, fill, lobes=lobes)
                    _leaf_polygon(alpha_draw, lx, ly, length, angle, 255, lobes=lobes)
                    _leaf_polygon(depth_draw, lx, ly, length, angle,
                                  int(90 + 160 * reach), lobes=lobes)
            # a few loose outliers so the silhouette is never a clean oval
            for _ in range(22):
                lx = ox + rng.uniform(half * 0.06, half * 0.94)
                ly = oy + rng.uniform(half * 0.06, half * 0.86)
                length = rng.uniform(half * 0.06, half * 0.12)
                angle = rng.uniform(0, math.pi * 2)
                base = colors[int(rng.integers(0, len(colors)))]
                fill = tuple(int(min(255, c * rng.uniform(0.7, 1.15))) for c in base)
                lobes = int(rng.integers(3, 6))
                _leaf_polygon(color_draw, lx, ly, length, angle, fill, lobes=lobes)
                _leaf_polygon(alpha_draw, lx, ly, length, angle, 255, lobes=lobes)
                _leaf_polygon(depth_draw, lx, ly, length, angle, 210, lobes=lobes)

    color = np.asarray(color_image).astype(np.float64) / 255.0
    alpha = np.asarray(alpha_image).astype(np.float64) / 255.0
    depth = np.asarray(depth_image.filter(ImageFilter.GaussianBlur(1.4))).astype(np.float64) / 255.0
    variation = N.tileable_fbm(size, 7, 4, seed=seed + 9)
    color = color * (0.66 + 0.46 * variation)[..., None]
    alpha_mask = (alpha > 0.5).astype(np.float64)
    occlusion = np.clip(0.38 + depth * 0.70, 0.0, 1.0)
    roughness = np.full((size, size), 0.80) - depth * 0.08
    return TextureSet(f"foliage_{palette}", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(depth * 0.5, 2.0), _u8(alpha_mask))


def timber(size: int = 512, seed: int = 23, tone: str = "warm") -> TextureSet:
    """Sawn structural timber: cathedral grain, knots, saw marks, weathering."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # cathedral figure: concentric rings distorted along the board
    wander = (N.tileable_value_noise(gx * 2.0, gy * 4.0, 2, 4, seed + 31) - 0.5) * 0.35
    ring_coordinate = (gx + wander) * 7.0 + N.tileable_fbm(size, 3, 3, seed=seed + 2) * 1.6
    rings = 0.5 + 0.5 * np.cos(ring_coordinate * math.pi * 2.0 * 2.0)
    rings = rings ** 1.4
    fibre = N.tileable_value_noise(gx * 8.0, gy * 240.0, 8, 240, seed + 5)
    saw = 0.5 + 0.5 * np.sin(gy * math.pi * 2.0 * 46.0 + fibre * 3.0)
    height = rings * 0.08 + fibre * 0.48 + saw * 0.16 + N.tileable_fbm(size, 10, 4, seed=seed + 6) * 0.26

    rng = np.random.default_rng(seed + 77)
    knots = np.zeros((size, size))
    knot_rings = np.zeros((size, size))
    for _ in range(4):
        kx, ky = rng.uniform(0, 1, 2)
        radius = rng.uniform(0.035, 0.075)
        dx = np.minimum(np.abs(gx - kx), 1.0 - np.abs(gx - kx))
        dy = np.minimum(np.abs(gy - ky), 1.0 - np.abs(gy - ky))
        d = np.sqrt((dx * 1.7) ** 2 + (dy * 0.85) ** 2)
        core = np.clip(1.0 - d / radius, 0.0, 1.0)
        knots = np.maximum(knots, core)
        knot_rings = np.maximum(knot_rings,
                                np.clip(1.0 - d / (radius * 3.0), 0.0, 1.0)
                                * (0.5 + 0.5 * np.cos(d / radius * math.pi * 5.0)))
    height = height * (1.0 - knots * 0.7) + knot_rings * 0.12

    tones = {
        "warm": ((0.150, 0.094, 0.054), (0.352, 0.238, 0.140), (0.560, 0.428, 0.284)),
        "grey": ((0.118, 0.110, 0.100), (0.268, 0.252, 0.232), (0.448, 0.432, 0.406)),
        "dark": ((0.078, 0.052, 0.034), (0.186, 0.128, 0.080), (0.330, 0.248, 0.168)),
    }
    low, mid, high = tones.get(tone, tones["warm"])
    figure = np.clip(0.26 + rings * 0.08 + fibre * 0.26 + knot_rings * 0.06
                     + N.tileable_fbm(size, 5, 4, seed=seed + 51) * 0.30
                     + N.tileable_value_noise(gx * 4.0, gy * 300.0, 4, 300, seed + 63) * 0.16,
                     0, 1)
    color = _colorize(figure, (0.0, low), (0.5, mid), (1.0, high))
    color = _mix(color, np.array([0.042, 0.026, 0.016]), knots * 0.88)

    weather = np.clip(N.tileable_fbm(size, 3, 4, seed=seed + 13) * 1.6 - 0.6, 0.0, 1.0)
    color = _mix(color, np.array([0.268, 0.250, 0.226]), weather * 0.34)
    moss = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 41) * 2.0 - 1.15, 0.0, 1.0)
    color = _mix(color, np.array([0.138, 0.184, 0.094]), moss * 0.6)

    occlusion = np.clip(0.48 + height * 0.58 - knots * 0.35, 0.0, 1.0)
    roughness = np.clip(0.70 + weather * 0.20 + knots * 0.08, 0.0, 1.0)
    return TextureSet(f"timber_{tone}", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.8))


def carved_wood(size: int = 512, seed: int = 29) -> TextureSet:
    """Timber with a carved interlace band - used on brackets, posts and doors."""
    base = timber(size, seed, "dark")
    height = np.asarray(Image.fromarray(base.normal).convert("L")).astype(np.float64) / 255.0
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for row in range(4):
        y = (row + 0.5) * size / 4.0
        for i in range(16):
            x = (i + 0.5) * size / 16.0
            r = size / 34.0
            draw.arc([x - r, y - r, x + r, y + r], 0, 360, fill=255, width=max(2, size // 170))
            draw.arc([x - r * 1.7, y - r * 0.6, x + r * 1.7, y + r * 0.6], 200, 340,
                     fill=200, width=max(2, size // 220))
    carve = np.asarray(image.filter(ImageFilter.GaussianBlur(1.1))).astype(np.float64) / 255.0
    height = np.clip(height - carve * 0.55, 0.0, 1.0)
    color = np.asarray(base.base_color).astype(np.float64) / 255.0
    color = _mix(color, color * 0.45, carve * 0.8)
    occlusion = np.clip(0.6 - carve * 0.45, 0.0, 1.0)
    roughness = np.clip(0.7 + carve * 0.12, 0.0, 1.0)
    return TextureSet("carved_wood", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.2))


def shingles(size: int = 512, seed: int = 37, rows: int = 12) -> TextureSet:
    """Overlapping split-wood shingles with moss in the courses."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = gy * rows
    row_index = np.floor(row)
    row_fraction = row - row_index
    offset = (row_index % 2) * 0.5
    columns = rows * 2
    col = (gx * columns + offset)
    col_index = np.floor(col)
    col_fraction = col - col_index

    rng = np.random.default_rng(seed)
    variation = rng.uniform(0.0, 1.0, size=(rows + 1, columns + 1))
    per_shingle = variation[row_index.astype(int) % (rows + 1),
                            col_index.astype(int) % (columns + 1)]

    # each shingle steps down toward its butt edge; gaps darken
    height = 0.35 + 0.5 * row_fraction + per_shingle * 0.14
    gap_x = np.minimum(col_fraction, 1.0 - col_fraction)
    gap_y = row_fraction
    height -= np.clip(1.0 - gap_x * 26.0, 0.0, 1.0) * 0.45
    height -= np.clip(1.0 - gap_y * 20.0, 0.0, 1.0) * 0.40
    grain = N.tileable_value_noise(gx * 4.0, gy * 90.0, 4, 90, seed + 3)
    height += grain * 0.10
    height = np.clip(height, 0.0, 1.0)

    tone_field = per_shingle ** 1.3
    color = _colorize(np.clip(tone_field * 0.72 + height * 0.28, 0, 1),
                      (0.0, (0.082, 0.068, 0.058)), (0.3, (0.158, 0.134, 0.112)),
                      (0.6, (0.252, 0.222, 0.184)), (0.85, (0.330, 0.300, 0.256)),
                      (1.0, (0.412, 0.382, 0.334)))
    moss = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 17) * 1.9 - 0.85, 0.0, 1.0)
    moss *= np.clip(1.0 - row_fraction * 0.7, 0.0, 1.0)
    color = _mix(color, np.array([0.130, 0.182, 0.092]), moss * 0.72)
    lichen = np.clip(N.tileable_fbm(size, 11, 3, seed=seed + 29) * 2.1 - 1.25, 0.0, 1.0)
    color = _mix(color, np.array([0.455, 0.470, 0.410]), lichen * 0.5)

    occlusion = np.clip(0.40 + height * 0.68, 0.0, 1.0)
    roughness = np.clip(0.80 + moss * 0.12 - per_shingle * 0.06, 0.0, 1.0)
    return TextureSet("shingles", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.2))


def ashlar(size: int = 512, seed: int = 53, courses: int = 7, weathered: bool = True) -> TextureSet:
    """Dressed stone blocks with recessed mortar, chipping, moss and water stain."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = gy * courses
    row_index = np.floor(row)
    row_fraction = row - row_index
    blocks = courses * 2
    offset = (row_index % 2) * 0.5
    col = gx * blocks + offset
    col_index = np.floor(col)
    col_fraction = col - col_index

    rng = np.random.default_rng(seed)
    per_block = rng.uniform(0.0, 1.0, size=(courses + 1, blocks + 1))
    block_value = per_block[row_index.astype(int) % (courses + 1),
                            col_index.astype(int) % (blocks + 1)]

    mortar_x = np.clip(np.minimum(col_fraction, 1.0 - col_fraction) * 26.0, 0.0, 1.0)
    mortar_y = np.clip(np.minimum(row_fraction, 1.0 - row_fraction) * 22.0, 0.0, 1.0)
    mortar = np.minimum(mortar_x, mortar_y)

    grit = N.tileable_fbm(size, 10, 5, seed=seed + 2)
    chips = np.clip(_upsample(N.tileable_worley(min(size, 256), 30, seed=seed + 8), size) * 1.6 - 0.9,
                    0.0, 1.0)
    height = mortar * (0.62 + block_value * 0.22) + grit * 0.14 - chips * 0.18
    height = np.clip(height, 0.0, 1.0)

    warm = rng.uniform(0.0, 1.0, size=(courses + 1, blocks + 1))[
        row_index.astype(int) % (courses + 1), col_index.astype(int) % (blocks + 1)]
    color = _colorize(np.clip(block_value * 0.62 + grit * 0.38, 0, 1),
                      (0.0, (0.196, 0.190, 0.176)), (0.35, (0.276, 0.268, 0.250)),
                      (0.7, (0.356, 0.346, 0.322)), (1.0, (0.442, 0.430, 0.400)))
    color = _mix(color, np.array([0.362, 0.318, 0.252]), (warm ** 2.2) * 0.45)
    color = _mix(color, np.array([0.196, 0.190, 0.176]), 1.0 - mortar)
    if weathered:
        moss = np.clip(N.tileable_fbm(size, 4, 5, seed=seed + 19) * 2.0 - 0.95, 0.0, 1.0)
        moss *= np.clip(1.0 - mortar * 0.35, 0.0, 1.0)
        color = _mix(color, np.array([0.128, 0.176, 0.094]), moss * 0.80)
        stain = np.clip(N.tileable_value_noise(gx * 5.0, gy * 1.4, 5, 1, seed + 23) * 1.8 - 0.85,
                        0.0, 1.0)
        color = _mix(color, np.array([0.212, 0.196, 0.168]), stain * 0.45)
        lichen = _upsample(N.tileable_worley(min(size, 256), 11, seed=seed + 37), size)
        lichen = np.clip((0.22 - lichen) * 4.0, 0.0, 1.0)
        lichen *= np.clip(N.tileable_fbm(size, 14, 3, seed=seed + 43) * 1.8 - 0.7, 0.0, 1.0)
        color = _mix(color, np.array([0.470, 0.482, 0.418]), lichen * 0.45)

    occlusion = np.clip(0.32 + mortar * 0.62 + height * 0.2, 0.0, 1.0)
    roughness = np.clip(0.84 + (1.0 - mortar) * 0.10, 0.0, 1.0)
    return TextureSet("ashlar", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.8))


def rubble_stone(size: int = 512, seed: int = 61) -> TextureSet:
    """Irregular field-stone walling and retaining walls."""
    cells = _upsample(N.tileable_worley(min(size, 256), 13, seed=seed), size)
    edges = _upsample(N.tileable_worley(min(size, 256), 13, seed=seed, order=1), size) - cells
    joint = np.clip(edges * 7.0, 0.0, 1.0)
    grit = N.tileable_fbm(size, 22, 4, seed=seed + 3)
    height = joint * 0.75 + grit * 0.25
    color = _colorize(np.clip(cells * 0.7 + grit * 0.3, 0, 1),
                      (0.0, (0.222, 0.210, 0.192)), (0.45, (0.318, 0.302, 0.276)),
                      (1.0, (0.428, 0.410, 0.378)))
    color = _mix(color, np.array([0.170, 0.162, 0.150]), 1.0 - joint)
    moss = np.clip(N.tileable_fbm(size, 5, 5, seed=seed + 11) * 2.1 - 0.95, 0.0, 1.0)
    color = _mix(color, np.array([0.120, 0.168, 0.088]), moss * 0.85)
    occlusion = np.clip(0.30 + joint * 0.68, 0.0, 1.0)
    roughness = np.clip(0.88 - joint * 0.05, 0.0, 1.0)
    return TextureSet("rubble_stone", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 5.5))


def cliff_rock(size: int = 512, seed: int = 67) -> TextureSet:
    """Bedded coastal rock: hard strata, angular fracture, salt bleaching."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    tilt = (N.tileable_value_noise(gx * 2.0, gy * 2.0, 2, 2, seed + 41) - 0.5) * 0.5
    bedding = gy * 11.0 + tilt * 3.0 + N.tileable_fbm(size, 4, 4, seed=seed) * 1.1
    band = np.floor(bedding)
    within = bedding - band
    rng = np.random.default_rng(seed + 3)
    band_value = rng.uniform(0.0, 1.0, size=64)[band.astype(int) % 64]
    # hard ledge at each bedding plane, softer face between
    ledge = np.clip(1.0 - within * 5.0, 0.0, 1.0) ** 0.6
    face = 0.35 + 0.5 * band_value + within * 0.18

    # angular jointing perpendicular to the bedding
    joint_near = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed + 5), size)
    joint_far = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed + 5, order=1), size)
    joint = np.clip((joint_far - joint_near) * 44.0, 0.0, 1.0)
    detail = N.tileable_fbm(size, 26, 5, seed=seed + 9)
    height = np.clip(0.32 + face * 0.30 - ledge * 0.62 - (1.0 - joint) * 0.14
                     + detail * 0.22, 0.0, 1.0)

    color = _colorize(np.clip(face * 0.6 + detail * 0.4, 0, 1),
                      (0.0, (0.046, 0.043, 0.041)), (0.35, (0.088, 0.083, 0.078)),
                      (0.7, (0.142, 0.134, 0.126)), (1.0, (0.208, 0.198, 0.186)))
    color = _mix(color, np.array([0.094, 0.090, 0.088]), (1.0 - joint) * 0.30)
    color = _mix(color, np.array([0.072, 0.068, 0.064]), ledge * 0.82)
    salt = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 13) * 1.8 - 0.9, 0.0, 1.0)
    color = _mix(color, np.array([0.268, 0.264, 0.252]), salt * 0.26)
    weed = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 27) * 2.3 - 1.45, 0.0, 1.0)
    color = _mix(color, np.array([0.100, 0.122, 0.072]), weed * 0.65)
    occlusion = np.clip(0.26 + height * 0.74 + joint * 0.12, 0.0, 1.0)
    roughness = np.clip(0.90 - salt * 0.08, 0.0, 1.0)
    return TextureSet("cliff_rock", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 6.0))


def forest_floor(size: int = 512, seed: int = 71, leaf_count: int = 900,
                 leaf_strength: float = 0.92) -> TextureSet:
    """Leaf litter over dark loam, with twigs, moss patches and exposed roots."""
    rng = np.random.default_rng(seed)
    loam = N.tileable_fbm(size, 8, 5, seed=seed)
    # Litter over loam, not loam with litter on it. The old ramp bottomed at
    # 0.030 - near black - so every gap between leaves read as mud and the
    # whole floor went dark under canopy shadow.
    color = _colorize(loam, (0.0, (0.140, 0.108, 0.070)), (0.5, (0.212, 0.166, 0.108)),
                      (1.0, (0.296, 0.238, 0.156)))
    height = loam * 0.3

    # scattered fallen leaves drawn as real silhouettes
    leaf_color = Image.new("RGB", (size, size), (0, 0, 0))
    leaf_alpha = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(leaf_color)
    ad = ImageDraw.Draw(leaf_alpha)
    palette = [(158, 96, 36), (186, 124, 48), (134, 74, 30), (204, 152, 64),
               (116, 60, 26), (172, 130, 56), (100, 66, 32)]
    for _ in range(leaf_count):
        cx, cy = rng.uniform(0, size, 2)
        length = rng.uniform(size * 0.020, size * 0.052)
        angle = rng.uniform(0, math.pi * 2)
        base = palette[int(rng.integers(0, len(palette)))]
        shade = rng.uniform(0.62, 1.12)
        fill = tuple(int(min(255, c * shade)) for c in base)
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                if abs(cx + dx - size / 2) > size or abs(cy + dy - size / 2) > size:
                    continue
                _leaf_polygon(cd, cx + dx, cy + dy, length, angle, fill,
                              lobes=int(rng.integers(3, 6)))
                _leaf_polygon(ad, cx + dx, cy + dy, length, angle, 255,
                              lobes=int(rng.integers(3, 6)))
    leaves = np.asarray(leaf_color).astype(np.float64) / 255.0
    mask = np.asarray(leaf_alpha).astype(np.float64) / 255.0
    color = _mix(color, leaves, mask * leaf_strength)
    height = height + mask * 0.35

    # Moss fills the gaps between leaves, so its colour sets how dark the floor
    # reads overall - at 0.108 it was the darkest thing in the texture and it
    # covered most of what the litter did not.
    moss = np.clip(N.tileable_fbm(size, 5, 5, seed=seed + 17) * 2.0 - 1.05, 0.0, 1.0)
    color = _mix(color, np.array([0.194, 0.246, 0.126]), moss * (1.0 - mask) * 0.70)
    # A forest floor is shadowed by its canopy, which the renderer already does.
    # Baking a 0.44 floor into the texture as well darkened it twice.
    occlusion = np.clip(0.62 + height * 0.36 - moss * 0.08, 0.0, 1.0)
    roughness = np.full((size, size), 0.93) - moss * 0.05
    return TextureSet("forest_floor", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.6))


def leaf_path(size: int = 512, seed: int = 79, leaf_count: int = 900) -> TextureSet:
    """Packed earth track showing through a thin leaf cover, with pebbles."""
    base = forest_floor(size, seed + 3, leaf_count=leaf_count)
    earth = N.tileable_fbm(size, 10, 5, seed=seed)
    packed = _colorize(earth, (0.0, (0.156, 0.128, 0.096)), (0.5, (0.232, 0.196, 0.152)),
                       (1.0, (0.308, 0.268, 0.212)))
    cover = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 11) * 1.6 - 0.45, 0.0, 1.0)
    color = _mix(packed, np.asarray(base.base_color).astype(np.float64) / 255.0, cover * 0.72)
    pebbles = np.clip(_upsample(N.tileable_worley(min(size, 256), 34, seed=seed + 5), size) * 2.0 - 1.25,
                      0.0, 1.0)
    color = _mix(color, np.array([0.222, 0.214, 0.200]), pebbles * 0.7)
    height = earth * 0.35 + cover * 0.25 + pebbles * 0.4
    occlusion = np.clip(0.68 + height * 0.30, 0.0, 1.0)
    roughness = np.full((size, size), 0.94)
    return TextureSet("leaf_path", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.2))


def cobble_paving(size: int = 512, seed: int = 83) -> TextureSet:
    """Old paved courtyard: worn setts, wide joints, leaf drift and moss."""
    cells = _upsample(N.tileable_worley(min(size, 256), 18, seed=seed), size)
    second = _upsample(N.tileable_worley(min(size, 256), 18, seed=seed, order=1), size)
    joint = np.clip((second - cells) * 9.0, 0.0, 1.0)
    grit = N.tileable_fbm(size, 26, 4, seed=seed + 3)
    height = joint * 0.7 + grit * 0.2 + (1.0 - cells) * 0.1
    color = _colorize(np.clip(cells * 0.6 + grit * 0.4, 0, 1),
                      (0.0, (0.156, 0.150, 0.141)), (0.5, (0.230, 0.222, 0.210)),
                      (1.0, (0.312, 0.304, 0.290)))
    color = _mix(color, np.array([0.128, 0.122, 0.112]), 1.0 - joint)
    moss = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 9) * 2.0 - 1.0, 0.0, 1.0)
    moss = np.maximum(moss, (1.0 - joint) * 0.35)
    color = _mix(color, np.array([0.118, 0.164, 0.086]), moss * 0.7)
    litter = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 21) * 1.9 - 1.1, 0.0, 1.0)
    color = _mix(color, np.array([0.352, 0.234, 0.104]), litter * 0.55)
    occlusion = np.clip(0.34 + joint * 0.62, 0.0, 1.0)
    roughness = np.clip(0.86 - cells * 0.06, 0.0, 1.0)
    return TextureSet("cobble_paving", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.0))


def water_surface(size: int = 512, seed: int = 89, tone: str = "sea") -> TextureSet:
    """Animated-looking still water: ripple normals plus depth tint."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    ripple = (N.tileable_value_noise(gx * 12.0, gy * 12.0, 12, 12, seed)
              + 0.5 * N.tileable_value_noise(gx * 27.0, gy * 27.0, 27, 27, seed + 3)
              + 0.25 * N.tileable_value_noise(gx * 53.0, gy * 53.0, 53, 53, seed + 7))
    ripple /= 1.75
    if tone == "sea":
        stops = ((0.0, (0.006, 0.052, 0.086)), (0.55, (0.014, 0.116, 0.168)),
                 (1.0, (0.038, 0.208, 0.256)))
    elif tone == "pool":
        stops = ((0.0, (0.030, 0.128, 0.132)), (0.55, (0.062, 0.212, 0.204)),
                 (1.0, (0.132, 0.300, 0.276)))
    elif tone == "lake":
        # Mirrorhold's glacier-fed water: rock flour makes it opaque turquoise
        stops = ((0.0, (0.026, 0.156, 0.190)), (0.55, (0.068, 0.324, 0.356)),
                 (1.0, (0.180, 0.520, 0.532)))
    elif tone == "lagoon":
        # Verdant Stair's sheltered sea: shallow over pale coral sand, so it is
        # far brighter and greener than the open water of any other region
        stops = ((0.0, (0.032, 0.244, 0.276)), (0.55, (0.086, 0.446, 0.436)),
                 (1.0, (0.232, 0.652, 0.596)))
    elif tone == "cenote":
        # the sink pools: dissolved limestone makes them the brightest green in
        # the region, and they are what the eye goes to from every terrace
        stops = ((0.0, (0.040, 0.268, 0.216)), (0.55, (0.108, 0.500, 0.380)),
                 (1.0, (0.286, 0.716, 0.548)))
    else:  # fast stream
        stops = ((0.0, (0.078, 0.176, 0.190)), (0.55, (0.148, 0.276, 0.286)),
                 (1.0, (0.320, 0.420, 0.418)))
    color = _colorize(ripple, *stops)
    foam = np.clip(N.tileable_fbm(size, 14, 4, seed=seed + 11) * 2.0 - 1.25, 0.0, 1.0)
    color = _mix(color, np.array([0.780, 0.830, 0.840]), foam * (0.55 if tone != "sea" else 0.35))
    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.08 + foam * 0.45, 0.0, 1.0)
    return TextureSet(f"water_{tone}", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(ripple, 1.6))


def amber_resin(size: int = 256, seed: int = 97) -> TextureSet:
    """Amber: warm translucent body with internal inclusions and polish."""
    swirl = N.tileable_fbm(size, 4, 5, seed=seed)
    grain = N.tileable_fbm(size, 16, 4, seed=seed + 5)
    body = np.clip(swirl * 0.75 + grain * 0.25, 0, 1)
    color = _colorize(body, (0.0, (0.412, 0.150, 0.020)), (0.45, (0.740, 0.352, 0.040)),
                      (0.8, (0.930, 0.560, 0.104)), (1.0, (0.990, 0.760, 0.286)))
    inclusion = np.clip(_upsample(N.tileable_worley(min(size, 256), 20, seed=seed + 9), size) * 2.0 - 1.4,
                        0.0, 1.0)
    color = _mix(color, np.array([0.230, 0.096, 0.020]), inclusion * 0.6)
    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.10 + grain * 0.14, 0.0, 1.0)
    return TextureSet("amber_resin", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(body * 0.4, 1.4))


def dark_iron(size: int = 256, seed: int = 101) -> TextureSet:
    """Hand-forged ironwork: hammer facets, pitting, warm rust in the hollows."""
    hammer = _upsample(N.tileable_worley(min(size, 256), 16, seed=seed), size)
    pit = np.clip(N.tileable_fbm(size, 22, 4, seed=seed + 3) * 1.8 - 1.0, 0.0, 1.0)
    height = hammer * 0.6 + (1.0 - pit) * 0.2 + N.tileable_fbm(size, 40, 3, seed=seed + 7) * 0.2
    color = _colorize(np.clip(hammer, 0, 1), (0.0, (0.048, 0.046, 0.048)),
                      (0.6, (0.092, 0.088, 0.090)), (1.0, (0.148, 0.144, 0.148)))
    rust = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 13) * 1.9 - 1.05, 0.0, 1.0)
    color = _mix(color, np.array([0.286, 0.132, 0.056]), rust * 0.72)
    occlusion = np.clip(0.42 + height * 0.56, 0.0, 1.0)
    roughness = np.clip(0.46 + rust * 0.38 + pit * 0.1, 0.0, 1.0)
    metallic = np.clip(0.92 - rust * 0.75, 0.0, 1.0)
    return TextureSet("dark_iron", _u8(color), pack_orm(occlusion, roughness, metallic),
                      normal_from_height(height, 3.2))


def woven_cloth(size: int = 256, seed: int = 103, hue=(0.204, 0.286, 0.268)) -> TextureSet:
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    weave = (0.5 + 0.5 * np.sin(gx * math.pi * 2.0 * 64.0)) * (0.5 + 0.5 * np.sin(gy * math.pi * 2.0 * 64.0))
    slub = N.tileable_fbm(size, 12, 4, seed=seed)
    height = weave * 0.6 + slub * 0.4
    base = np.array(hue, dtype=np.float64)
    color = base[None, None, :] * (0.72 + 0.5 * height)[..., None]
    wear = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 9) * 1.7 - 0.85, 0.0, 1.0)
    color = _mix(color, base * 1.6, wear * 0.4)
    occlusion = np.clip(0.55 + height * 0.42, 0.0, 1.0)
    roughness = np.full((size, size), 0.92)
    return TextureSet("woven_cloth", _u8(np.clip(color, 0, 1)), pack_orm(occlusion, roughness),
                      normal_from_height(height, 1.6))


def thatch_reed(size: int = 512, seed: int = 107) -> TextureSet:
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    stalks = N.tileable_value_noise(gx * 150.0, gy * 6.0, 150, 6, seed)
    rows = 0.5 + 0.5 * np.sin(gy * math.pi * 2.0 * 8.0)
    height = stalks * 0.6 + rows * 0.25 + N.tileable_fbm(size, 12, 3, seed=seed + 5) * 0.15
    color = _colorize(np.clip(height, 0, 1), (0.0, (0.156, 0.126, 0.076)),
                      (0.5, (0.310, 0.256, 0.150)), (1.0, (0.452, 0.386, 0.238)))
    occlusion = np.clip(0.40 + height * 0.58, 0.0, 1.0)
    roughness = np.full((size, size), 0.95)
    return TextureSet("thatch_reed", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.0))


def scorched_ground(size: int = 512, seed: int = 109) -> TextureSet:
    """Eastern transition: burnt, ash-covered, cracked barren soil."""
    cracks = _upsample(N.tileable_worley(min(size, 256), 11, seed=seed, order=1), size)
    cracks -= _upsample(N.tileable_worley(min(size, 256), 11, seed=seed), size)
    crack_mask = np.clip(1.0 - cracks * 9.0, 0.0, 1.0)
    ash = N.tileable_fbm(size, 9, 5, seed=seed + 3)
    height = (1.0 - crack_mask) * 0.55 + ash * 0.45
    color = _colorize(np.clip(ash, 0, 1), (0.0, (0.042, 0.038, 0.036)),
                      (0.45, (0.062, 0.054, 0.047)), (0.8, (0.100, 0.086, 0.072)),
                      (1.0, (0.142, 0.122, 0.100)))
    color = _mix(color, np.array([0.022, 0.019, 0.018]), crack_mask * 0.85)
    ember = np.clip(N.tileable_fbm(size, 15, 3, seed=seed + 19) * 2.4 - 1.75, 0.0, 1.0)
    color = _mix(color, np.array([0.268, 0.108, 0.036]), ember * 0.5)
    occlusion = np.clip(0.34 + (1.0 - crack_mask) * 0.6, 0.0, 1.0)
    roughness = np.full((size, size), 0.96)
    return TextureSet("scorched_ground", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.6))


def shore_shingle(size: int = 512, seed: int = 113) -> TextureSet:
    """Wet pebble beach at the tide line - rounded stones with real relief."""
    near = _upsample(N.tileable_worley(min(size, 256), 22, seed=seed), size)
    far = _upsample(N.tileable_worley(min(size, 256), 22, seed=seed, order=1), size)
    # dome each cell so pebbles read as rounded solids rather than flat noise
    dome = np.clip(1.0 - near / np.maximum(far, 1e-6), 0.0, 1.0) ** 0.6
    small_near = _upsample(N.tileable_worley(min(size, 256), 48, seed=seed + 17), size)
    small_far = _upsample(N.tileable_worley(min(size, 256), 48, seed=seed + 17, order=1), size)
    small = np.clip(1.0 - small_near / np.maximum(small_far, 1e-6), 0.0, 1.0) ** 0.7
    grit = N.tileable_fbm(size, 40, 4, seed=seed + 5)
    height = np.clip(dome * 0.68 + small * 0.24 + grit * 0.12, 0.0, 1.0)

    rng = np.random.default_rng(seed + 61)
    cell_tone = rng.uniform(0.0, 1.0, size=(22, 22))
    cy = np.clip((np.arange(size) * 22 // size), 0, 21)
    tone = cell_tone[np.ix_(cy, cy)]
    color = _colorize(np.clip(tone * 0.55 + dome * 0.45, 0, 1),
                      (0.0, (0.056, 0.052, 0.049)), (0.35, (0.102, 0.096, 0.090)),
                      (0.7, (0.164, 0.155, 0.144)), (1.0, (0.234, 0.224, 0.208)))
    color = _mix(color, np.array([0.060, 0.056, 0.054]), (1.0 - dome) * 0.7)
    wet = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 11) * 1.7 - 0.55, 0.0, 1.0)
    color = color * (1.0 - wet * 0.48)[..., None]
    weed = np.clip(N.tileable_fbm(size, 10, 4, seed=seed + 23) * 2.3 - 1.5, 0.0, 1.0)
    color = _mix(color, np.array([0.100, 0.110, 0.066]), weed * 0.72)
    occlusion = np.clip(0.28 + height * 0.72, 0.0, 1.0)
    roughness = np.clip(0.88 - wet * 0.58, 0.0, 1.0)
    return TextureSet("shore_shingle", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 5.2))


def undergrowth_atlas(size: int = 512, seed: int = 127) -> TextureSet:
    """Alpha atlas of ferns, grass tufts, bracken and small flowering plants."""
    rng = np.random.default_rng(seed)
    color_image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha_image = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(color_image)
    ad = ImageDraw.Draw(alpha_image)
    half = size // 2

    def blade(x0, y0, height_px, width_px, lean, color):
        points = []
        steps = 10
        for i in range(steps + 1):
            t = i / steps
            w = width_px * (1.0 - t) ** 0.8
            x = x0 + lean * t * t * height_px
            y = y0 - t * height_px
            points.append((x - w, y))
        for i in range(steps, -1, -1):
            t = i / steps
            w = width_px * (1.0 - t) ** 0.8
            x = x0 + lean * t * t * height_px
            y = y0 - t * height_px
            points.append((x + w, y))
        cd.polygon(points, fill=color)
        ad.polygon(points, fill=255)

    def frond(x0, y0, length_px, angle, color):
        for side in (-1, 1):
            for i in range(1, 13):
                t = i / 13.0
                bx = x0 + math.cos(angle) * length_px * t
                by = y0 + math.sin(angle) * length_px * t
                leaflet = length_px * 0.22 * (1.0 - t * 0.7)
                nx = math.cos(angle + side * 1.15) * leaflet
                ny = math.sin(angle + side * 1.15) * leaflet
                cd.polygon([(bx, by), (bx + nx, by + ny),
                            (bx + nx * 0.5 + math.cos(angle) * leaflet * 0.5,
                             by + ny * 0.5 + math.sin(angle) * leaflet * 0.5)], fill=color)
                ad.polygon([(bx, by), (bx + nx, by + ny),
                            (bx + nx * 0.5 + math.cos(angle) * leaflet * 0.5,
                             by + ny * 0.5 + math.sin(angle) * leaflet * 0.5)], fill=255)

    greens = [(56, 78, 34), (44, 64, 28), (72, 96, 42), (88, 108, 48), (38, 56, 26)]
    ambers = [(132, 96, 38), (150, 112, 46), (112, 78, 32)]
    # cell 0,0 grass tuft; 1,0 fern; 0,1 bracken; 1,1 mixed with flowers
    for _ in range(90):
        c = greens[int(rng.integers(0, len(greens)))]
        blade(rng.uniform(6, half - 6), half - 4, rng.uniform(half * 0.35, half * 0.85),
              rng.uniform(2.0, 4.4), rng.uniform(-0.35, 0.35), c)
    for _ in range(26):
        c = greens[int(rng.integers(0, len(greens)))]
        frond(rng.uniform(half + 12, size - 12), rng.uniform(half * 0.75, half - 6),
              rng.uniform(half * 0.30, half * 0.48), rng.uniform(-2.5, -0.6), c)
    for _ in range(40):
        c = ambers[int(rng.integers(0, len(ambers)))]
        frond(rng.uniform(10, half - 10), rng.uniform(size - half * 0.3, size - 8),
              rng.uniform(half * 0.28, half * 0.44), rng.uniform(-2.6, -0.5), c)
    for _ in range(70):
        c = greens[int(rng.integers(0, len(greens)))]
        blade(rng.uniform(half + 6, size - 6), size - 4, rng.uniform(half * 0.25, half * 0.6),
              rng.uniform(1.8, 3.6), rng.uniform(-0.4, 0.4), c)
    for _ in range(26):
        x = rng.uniform(half + 10, size - 10)
        y = rng.uniform(size - half * 0.7, size - 12)
        r = rng.uniform(2.2, 4.0)
        c = (226, 206, 150) if rng.uniform() < 0.6 else (206, 138, 72)
        cd.ellipse([x - r, y - r, x + r, y + r], fill=c)
        ad.ellipse([x - r, y - r, x + r, y + r], fill=255)

    color = np.asarray(color_image).astype(np.float64) / 255.0
    alpha = np.asarray(alpha_image).astype(np.float64) / 255.0
    variation = N.tileable_fbm(size, 6, 4, seed=seed + 3)
    color = color * (0.82 + 0.36 * variation)[..., None]
    occlusion = np.clip(0.55 + alpha * 0.35, 0.0, 1.0)
    roughness = np.full((size, size), 0.84)
    return TextureSet("undergrowth", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(alpha * 0.3, 1.2), _u8((alpha > 0.5).astype(np.float64)))


def meadow_grass(size: int = 512, seed: int = 131) -> TextureSet:
    """Open clearing grass with autumn seed heads and worn patches."""
    rng = np.random.default_rng(seed)
    base = N.tileable_fbm(size, 9, 5, seed=seed)
    color = _colorize(base, (0.0, (0.082, 0.098, 0.048)), (0.45, (0.146, 0.162, 0.076)),
                      (0.8, (0.216, 0.218, 0.104)), (1.0, (0.288, 0.272, 0.140)))
    dry = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 7) * 1.8 - 0.75, 0.0, 1.0)
    color = _mix(color, np.array([0.288, 0.248, 0.128]), dry * 0.65)
    # fine blade texture
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    blades = N.tileable_value_noise(gx * 210.0, gy * 26.0, 210, 26, seed + 3)
    color = color * (0.80 + 0.40 * blades)[..., None]
    litter = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 21) * 2.1 - 1.35, 0.0, 1.0)
    color = _mix(color, np.array([0.348, 0.226, 0.098]), litter * 0.5)
    height = base * 0.4 + blades * 0.4 + litter * 0.2
    occlusion = np.clip(0.52 + height * 0.44, 0.0, 1.0)
    roughness = np.full((size, size), 0.94)
    return TextureSet("meadow_grass", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness), normal_from_height(height, 1.8))


def steppe_ground(name: str, size: int = 512) -> TextureSet:
    """Dry grass and travel dust with the shared ground recipes' modest relief.

    Recolour their seeded structure rather than tinting green grass at runtime.
    The original meadow and earth recipes keep their existing output bytes.
    """
    if name == 'steppe_sward':
        source = meadow_grass(size, seed=733)
        stops = ((0., (.20, .18, .105)), (.5, (.39, .34, .18)),
                 (1., (.56, .48, .28)))
    elif name == 'steppe_dust':
        source = packed_earth(size, seed=739)
        stops = ((0., (.23, .20, .15)), (.5, (.43, .37, .265)),
                 (1., (.62, .54, .40)))
    else:
        raise ValueError(name)
    luminance = source.base_color.astype(float).mean(axis=2) / 255
    lo, hi = np.percentile(luminance, [2, 98])
    field = np.clip((luminance - lo) / max(hi - lo, .001), 0, 1)
    return TextureSet(name, _u8(_colorize(field, *stops)), source.orm, source.normal)


def amber_glass(size: int = 256, seed: int = 137) -> TextureSet:
    """Hand-blown amber glazing: uneven, streaked, slightly bubbled."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    streak = N.tileable_value_noise(gx * 6.0, gy * 44.0, 6, 44, seed)
    bubble = np.clip(_upsample(N.tileable_worley(min(size, 256), 26, seed=seed + 5), size)
                     * 2.2 - 1.5, 0.0, 1.0)
    body = np.clip(streak * 0.7 + N.tileable_fbm(size, 5, 4, seed=seed + 9) * 0.3, 0, 1)
    color = _colorize(body, (0.0, (0.330, 0.222, 0.096)), (0.5, (0.560, 0.404, 0.168)),
                      (1.0, (0.780, 0.612, 0.290)))
    color = _mix(color, np.array([0.900, 0.780, 0.500]), bubble * 0.6)
    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.16 + body * 0.16, 0.0, 1.0)
    return TextureSet("amber_glass", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(body * 0.3 + bubble * 0.4, 1.2))


def lime_plaster(size: int = 512, seed: int = 211) -> TextureSet:
    """Lime plaster over lath: the pale infill between exposed timbers.

    Interiors built only from timber read as one uniform orange note, which is
    exactly what the region brief warns against. A cool pale infill gives the
    framing something to be read against.
    """
    coarse = N.tileable_fbm(size, 5, 5, seed=seed)
    fine = N.tileable_fbm(size, 34, 4, seed=seed + 1)
    colour = _colorize(coarse, (0.0, (0.690, 0.658, 0.596)), (0.55, (0.772, 0.744, 0.680)),
                       (1.0, (0.842, 0.815, 0.748)))
    colour = colour * (0.94 + 0.12 * fine)[..., None]
    # Hairline crazing, and damp rising from the foot of the panel.
    # Fine, irregular crazing. A low-frequency sine through smooth noise draws
    # closed loops that read as contour lines rather than cracked lime, so the
    # field is driven at high frequency and the contrast kept shallow.
    craze = N.tileable_fbm(size, 22, 5, seed=seed + 2)
    crack = np.clip(1.0 - np.abs(np.sin(craze * 62.0)) * 3.4, 0.0, 1.0) ** 1.5
    crack *= np.clip(N.tileable_fbm(size, 4, 3, seed=seed + 6) * 1.6 - 0.25, 0.0, 1.0)
    colour = _mix(colour, np.array((0.545, 0.516, 0.462)), crack * 0.42)
    v = np.linspace(0.0, 1.0, size)[:, None] * np.ones((1, size))
    damp = np.clip(v * 1.5 - 0.55, 0.0, 1.0) * N.tileable_fbm(size, 3, 4, seed=seed + 3)
    colour = _mix(colour, np.array((0.588, 0.556, 0.478)), damp * 0.4)
    height = np.clip(coarse * 0.5 + fine * 0.32 - crack * 0.3, 0.0, 1.0)
    occlusion = np.clip(0.70 + 0.30 * (1.0 - crack), 0.0, 1.0)
    roughness = np.clip(0.88 - 0.08 * fine, 0.0, 1.0)
    return TextureSet("lime_plaster", _u8(np.clip(colour, 0.0, 1.0)),
                      pack_orm(occlusion, roughness), normal_from_height(height, 1.5))


def sooted_plaster(size: int = 512, seed: int = 233) -> TextureSet:
    """The same lime plaster, smoke-blackened and washed by rain.

    The Cinder Chapel is the Amber Hall after a fire, so it must be built from
    the same wall - not from a different, paler stone that reads as merely old.
    """
    base = lime_plaster(size, seed=seed)
    colour = np.asarray(base.base_color, dtype=np.float64) / 255.0
    smoke = N.tileable_fbm(size, 4, 5, seed=seed + 5)
    soot = np.clip(smoke * 1.5 + 0.30, 0.0, 1.0)
    # Smoke stains heaviest at the top of a panel, where it rose and pooled, but
    # a burned building is blackened all over - a stain only at the head reads as
    # damp, not as fire.
    v = np.linspace(1.0, 0.0, size)[:, None] * np.ones((1, size))
    soot = np.clip(soot * (0.72 + 0.42 * v), 0.0, 1.0)
    colour = _mix(colour, np.array((0.062, 0.055, 0.052)), soot * 0.93)
    streak = np.clip(N.tileable_fbm(size, 30, 3, seed=seed + 7) - 0.52, 0.0, 1.0) * 2.6
    colour = _mix(colour, np.array((0.105, 0.096, 0.090)), np.clip(streak, 0, 1) * 0.6)
    # A few patches where the render fell away to bare, scorched lath.
    bare = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 11) * 1.7 - 0.95, 0.0, 1.0)
    colour = _mix(colour, np.array((0.196, 0.145, 0.101)), bare * 0.7)
    occlusion = np.clip(0.42 + 0.4 * (1.0 - soot), 0.0, 1.0)
    roughness = np.clip(0.93 + 0.05 * soot, 0.0, 1.0)
    return TextureSet("sooted_plaster", _u8(np.clip(colour, 0.0, 1.0)),
                      pack_orm(occlusion, roughness), base.normal)


def charred_timber(size: int = 512, seed: int = 241) -> TextureSet:
    """Structural timber that came through a fire: alligatored char over grain."""
    base = timber(size, seed=seed, tone="dark")
    colour = np.asarray(base.base_color, dtype=np.float64) / 255.0
    cells = N.tileable_fbm(size, 24, 5, seed=seed + 1)
    crack = np.clip(1.0 - np.abs(np.sin(cells * 30.0)) * 2.6, 0.0, 1.0) ** 1.3
    colour = _mix(colour, np.array((0.086, 0.074, 0.070)), 0.86)
    colour = _mix(colour, np.array((0.035, 0.031, 0.031)), crack * 0.75)
    ember = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 2) * 1.8 - 1.24, 0.0, 1.0)
    colour = _mix(colour, np.array((0.352, 0.145, 0.047)), ember * 0.5)
    height = np.clip(0.55 - crack * 0.5 + cells * 0.25, 0.0, 1.0)
    occlusion = np.clip(0.34 + 0.5 * (1.0 - crack), 0.0, 1.0)
    return TextureSet("charred_timber", _u8(np.clip(colour, 0.0, 1.0)),
                      pack_orm(occlusion, np.full((size, size), 0.95)),
                      normal_from_height(height, 3.4))


def packed_earth(size: int = 512, seed: int = 223) -> TextureSet:
    """Cut earth with grit, pebbles and root threads - the wall of a dug space."""
    soil = N.tileable_fbm(size, 6, 6, seed=seed)
    grit = N.tileable_fbm(size, 48, 4, seed=seed + 1)
    colour = _colorize(soil, (0.0, (0.166, 0.128, 0.094)), (0.6, (0.254, 0.196, 0.140)),
                       (1.0, (0.336, 0.264, 0.190)))
    colour = colour * (0.74 + 0.58 * grit)[..., None]
    threads = np.clip((N.tileable_fbm(size, 7, 3, seed=seed + 2) - 0.60) * 3.2, 0.0, 1.0)
    colour = _mix(colour, np.array((0.290, 0.219, 0.141)), threads * 0.55)
    pebble = _upsample(N.tileable_worley(min(size, 256), 22, seed=seed + 3), size)
    stones = np.clip(1.0 - pebble * 5.5, 0.0, 1.0)
    colour = _mix(colour, np.array((0.430, 0.408, 0.372)), stones * 0.72)
    height = np.clip(soil * 0.42 + grit * 0.34 + stones * 0.5, 0.0, 1.0)
    occlusion = np.clip(0.50 + 0.50 * soil, 0.0, 1.0)
    roughness = np.clip(0.95 - 0.05 * grit, 0.0, 1.0)
    return TextureSet("packed_earth", _u8(np.clip(colour, 0.0, 1.0)),
                      pack_orm(occlusion, roughness), normal_from_height(height, 2.1))


def canvas_awning(size: int = 256, seed: int = 139) -> TextureSet:
    """Striped market canvas, faded and patched."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    stripes = (np.floor(gx * 8.0) % 2)
    weave = (0.5 + 0.5 * np.sin(gx * math.pi * 2.0 * 90.0)) \
        * (0.5 + 0.5 * np.sin(gy * math.pi * 2.0 * 90.0))
    dirt = N.tileable_fbm(size, 6, 4, seed=seed)
    warm = np.array([0.482, 0.318, 0.152])
    pale = np.array([0.606, 0.548, 0.428])
    color = warm[None, None, :] * stripes[..., None] + pale[None, None, :] * (1 - stripes)[..., None]
    color = color * (0.78 + 0.34 * weave)[..., None]
    color = _mix(color, np.array([0.318, 0.276, 0.220]), np.clip(dirt * 1.4 - 0.6, 0, 1) * 0.5)
    occlusion = np.clip(0.62 + weave * 0.3, 0.0, 1.0)
    roughness = np.full((size, size), 0.90)
    return TextureSet("canvas_awning", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness), normal_from_height(weave * 0.4, 1.2))


# --------------------------------------------------------------------------
# Mirrorhold: alpine stone, ice and the blue crystal the region is named for
# --------------------------------------------------------------------------

def alpine_ground(name: str, size: int = 512, seed: int = 743) -> TextureSet:
    """Quiet alpine masses; directional strata belong to the landform, not a tile."""
    broad=N.tileable_fbm(size,3,3,seed=seed)
    grain=N.tileable_fbm(size,24,2,seed=seed+3)
    field=.75*broad+.25*grain
    colours={
        'alpine_snowfield':((.70,.76,.82),(.86,.89,.92)),
        'alpine_blue_ice':((.30,.46,.55),(.53,.66,.73)),
        'alpine_bedrock':((.29,.32,.35),(.43,.46,.49)),
    }
    lo,hi=colours[name]
    colour=np.asarray(lo)+(np.asarray(hi)-lo)*field[...,None]
    roughness=np.full((size,size),.72 if name=='alpine_blue_ice' else .96)
    return TextureSet(name,_u8(colour),pack_orm(np.full_like(field,.94),roughness),
                      normal_from_height(field,.22))


def snow_pack(size: int = 512, seed: int = 401) -> TextureSet:
    """Wind-packed snow: sastrugi ripples, a crust that catches light, blue shade."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # sastrugi run with the prevailing wind, so the ripple is strongly anisotropic
    drift = (N.tileable_value_noise(gx * 3.0, gy * 14.0, 3, 14, seed)
             + 0.45 * N.tileable_value_noise(gx * 7.0, gy * 29.0, 7, 29, seed + 3))
    drift /= 1.45
    grain = N.tileable_fbm(size, 22, 4, seed=seed + 7)
    height = np.clip(drift * 0.78 + grain * 0.22, 0.0, 1.0)

    # snow is almost white; what reads is the shadow colour, which is blue
    color = _colorize(height, (0.0, (0.560, 0.610, 0.700)),
                      (0.45, (0.760, 0.800, 0.860)),
                      (0.78, (0.880, 0.906, 0.940)),
                      (1.0, (0.950, 0.962, 0.975)))
    sparkle = np.clip(_upsample(N.tileable_worley(min(size, 256), 46, seed=seed + 11), size)
                      * 2.4 - 1.7, 0.0, 1.0)
    color = _mix(color, np.array([1.0, 1.0, 1.0]), sparkle * 0.55)
    occlusion = np.clip(0.44 + height * 0.56, 0.0, 1.0)
    roughness = np.clip(0.74 - sparkle * 0.34 - height * 0.10, 0.05, 1.0)
    return TextureSet("snow_pack", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.6))


def glacier_ice(size: int = 512, seed: int = 409) -> TextureSet:
    """Glacier ice: compressed blue banding, crevasse fracture, meltwater polish."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    warp = (N.tileable_fbm(size, 3, 4, seed=seed + 5) - 0.5) * 1.6
    banding = gy * 9.0 + warp * 2.4
    band = banding - np.floor(banding)
    # dense old ice reads as a deep blue band between paler bubble-rich layers
    depth = np.clip(np.sin(band * math.pi) ** 1.6, 0.0, 1.0)
    bubbles = N.tileable_fbm(size, 18, 4, seed=seed + 9)

    fracture_near = _upsample(N.tileable_worley(min(size, 256), 6, seed=seed + 13), size)
    fracture_far = _upsample(N.tileable_worley(min(size, 256), 6, seed=seed + 13, order=1), size)
    # a few hairline crevasses, not a cell net: bias hard toward 1 and keep
    # only the deepest seams
    fracture = np.clip((fracture_far - fracture_near) * 90.0, 0.0, 1.0)
    seam = np.clip(1.0 - fracture, 0.0, 1.0) ** 2.2

    height = np.clip(0.46 + depth * 0.12 + bubbles * 0.16 - seam * 0.30, 0.0, 1.0)
    color = _colorize(np.clip(depth * 0.55 + bubbles * 0.45, 0, 1),
                      (0.0, (0.788, 0.856, 0.884)), (0.45, (0.618, 0.744, 0.804)),
                      (0.78, (0.442, 0.616, 0.712)), (1.0, (0.310, 0.512, 0.628)))
    color = _mix(color, np.array([0.868, 0.918, 0.940]), seam * 0.30)
    rime = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 19) * 2.1 - 1.25, 0.0, 1.0)
    color = _mix(color, np.array([0.930, 0.950, 0.965]), rime * 0.50)
    occlusion = np.clip(0.34 + height * 0.66, 0.0, 1.0)
    roughness = np.clip(0.34 + rime * 0.40 - depth * 0.08, 0.05, 1.0)
    return TextureSet("glacier_ice", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.4))


def blue_crystal(size: int = 256, seed: int = 419) -> TextureSet:
    """The lens glass: a cool internally-lit blue with facet planes."""
    swirl = N.tileable_fbm(size, 3, 5, seed=seed)
    facet_near = _upsample(N.tileable_worley(min(size, 192), 5, seed=seed + 3), size)
    facet_far = _upsample(N.tileable_worley(min(size, 192), 5, seed=seed + 3, order=1), size)
    facet = np.clip((facet_far - facet_near) * 5.0, 0.0, 1.0) ** 0.55
    body = np.clip(swirl * 0.6 + facet * 0.4, 0, 1)
    color = _colorize(body, (0.0, (0.020, 0.098, 0.190)), (0.45, (0.055, 0.230, 0.400)),
                      (0.8, (0.130, 0.420, 0.640)), (1.0, (0.300, 0.640, 0.850)))
    height = np.clip(facet * 0.7 + swirl * 0.3, 0.0, 1.0)
    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.10 + (1.0 - facet) * 0.16, 0.03, 1.0)
    return TextureSet("blue_crystal", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.0))


def veined_marble(size: int = 512, seed: int = 421) -> TextureSet:
    """Pale blue-grey marble with darker veining: Mirrorhold's civic paving."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    warp = (N.tileable_fbm(size, 4, 5, seed=seed + 3) - 0.5) * 3.2
    # veins are a thin ridge in a warped coordinate, which is what marble does
    field = np.sin((gx * 5.0 + gy * 2.2 + warp) * math.pi)
    vein = np.clip(1.0 - np.abs(field) * 6.0, 0.0, 1.0) ** 1.4
    vein_fine = np.clip(1.0 - np.abs(np.sin((gx * 13.0 - gy * 6.0 + warp * 1.7)
                                            * math.pi)) * 12.0, 0.0, 1.0)
    grain = N.tileable_fbm(size, 20, 4, seed=seed + 11)
    body = np.clip(0.62 + grain * 0.28, 0, 1)
    color = _colorize(body, (0.0, (0.398, 0.426, 0.462)), (0.5, (0.536, 0.566, 0.602)),
                      (1.0, (0.664, 0.690, 0.722)))
    color = _mix(color, np.array([0.244, 0.286, 0.348]), vein * 0.62)
    color = _mix(color, np.array([0.352, 0.400, 0.462]), vein_fine * 0.30)
    height = np.clip(0.55 + grain * 0.20 - vein * 0.16, 0.0, 1.0)
    occlusion = np.clip(0.62 + height * 0.38 - vein * 0.14, 0.0, 1.0)
    roughness = np.clip(0.34 + grain * 0.16 + vein * 0.10, 0.05, 1.0)
    return TextureSet("veined_marble", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 1.5))


def pale_ashlar(size: int = 512, seed: int = 431, courses: int = 6) -> TextureSet:
    """Mirrorhold's masonry: cold grey granite ashlar, snow-bleached, lichened."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = gy * courses
    row_index = np.floor(row)
    row_fraction = row - row_index
    blocks = courses * 2
    offset = (row_index % 2) * 0.5
    col = gx * blocks + offset
    col_index = np.floor(col)
    col_fraction = col - col_index

    rng = np.random.default_rng(seed)
    per_block = rng.uniform(0.0, 1.0, size=(courses + 1, blocks + 1))
    block_value = per_block[row_index.astype(int) % (courses + 1),
                            col_index.astype(int) % (blocks + 1)]

    mortar_x = np.clip(np.minimum(col_fraction, 1.0 - col_fraction) * 30.0, 0.0, 1.0)
    mortar_y = np.clip(np.minimum(row_fraction, 1.0 - row_fraction) * 26.0, 0.0, 1.0)
    mortar = np.minimum(mortar_x, mortar_y)

    grit = N.tileable_fbm(size, 12, 5, seed=seed + 2)
    chips = np.clip(_upsample(N.tileable_worley(min(size, 256), 26, seed=seed + 8), size)
                    * 1.7 - 1.0, 0.0, 1.0)
    height = np.clip(mortar * (0.66 + block_value * 0.20) + grit * 0.13 - chips * 0.20,
                     0.0, 1.0)

    tone = np.clip(0.40 + block_value * 0.42 + grit * 0.18, 0, 1)
    color = _colorize(tone, (0.0, (0.168, 0.180, 0.198)), (0.45, (0.278, 0.294, 0.316)),
                      (0.78, (0.386, 0.404, 0.428)), (1.0, (0.492, 0.510, 0.534)))
    color = _mix(color, np.array([0.148, 0.156, 0.172]), (1.0 - mortar) * 0.55)
    # pale lichen in the sheltered courses, and snow caught on upward ledges
    lichen = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 17) * 2.2 - 1.35, 0.0, 1.0)
    color = _mix(color, np.array([0.404, 0.452, 0.376]), lichen * 0.34)
    snow = np.clip(N.tileable_fbm(size, 6, 3, seed=seed + 23) * 2.0 - 1.30, 0.0, 1.0)
    snow = snow * np.clip(1.0 - row_fraction * 3.0, 0.0, 1.0)
    color = _mix(color, np.array([0.780, 0.812, 0.848]), snow * 0.34)
    occlusion = np.clip(0.30 + height * 0.70, 0.0, 1.0)
    roughness = np.clip(0.88 - snow * 0.10 + lichen * 0.06, 0.05, 1.0)
    return TextureSet("pale_ashlar", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 5.0))


def gilt_brass(size: int = 256, seed: int = 433) -> TextureSet:
    """Gilded brass for the domes and the armillary: warm metal, wind-polished."""
    grain = N.tileable_fbm(size, 20, 4, seed=seed)
    # broad soft lustre bands, the way a beaten dome catches light - low
    # frequency, or it reads as corrugated iron
    sweep = N.tileable_fbm(size, 3, 3, seed=seed + 5)
    body = np.clip(sweep * 0.74 + grain * 0.26, 0, 1)
    color = _colorize(body, (0.0, (0.220, 0.148, 0.052)), (0.45, (0.492, 0.352, 0.116)),
                      (0.8, (0.716, 0.556, 0.212)), (1.0, (0.868, 0.734, 0.372)))
    # verdigris collects where meltwater sits
    patina = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 13) * 2.4 - 1.85, 0.0, 1.0)
    color = _mix(color, np.array([0.246, 0.408, 0.352]), patina * 0.26)
    height = np.clip(0.5 + grain * 0.18 - patina * 0.14, 0.0, 1.0)
    occlusion = np.clip(0.66 + height * 0.34, 0.0, 1.0)
    roughness = np.clip(0.18 + patina * 0.56 + grain * 0.08, 0.04, 1.0)
    return TextureSet("gilt_brass", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 0.9))


def slate_roof(size: int = 512, seed: int = 439, rows: int = 16) -> TextureSet:
    """Blue-grey slate courses for the cliff-town roofs."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = gy * rows
    row_index = np.floor(row)
    row_fraction = row - row_index
    per_row_offset = (row_index % 2) * 0.5
    col = gx * (rows // 2) + per_row_offset
    col_index = np.floor(col)
    col_fraction = col - col_index

    rng = np.random.default_rng(seed)
    tile_value = rng.uniform(0.0, 1.0, size=(rows + 1, rows))[
        row_index.astype(int) % (rows + 1), col_index.astype(int) % rows]

    lip = np.clip((1.0 - row_fraction) * 7.0, 0.0, 1.0)
    gap = np.clip(np.minimum(col_fraction, 1.0 - col_fraction) * 34.0, 0.0, 1.0)
    grain = N.tileable_fbm(size, 24, 4, seed=seed + 3)
    height = np.clip(0.30 + lip * 0.44 + tile_value * 0.10 + grain * 0.12
                     - (1.0 - gap) * 0.34, 0.0, 1.0)
    color = _colorize(np.clip(tile_value * 0.6 + grain * 0.4, 0, 1),
                      (0.0, (0.062, 0.072, 0.090)), (0.5, (0.116, 0.130, 0.156)),
                      (1.0, (0.186, 0.202, 0.230)))
    color = _mix(color, np.array([0.040, 0.046, 0.058]), (1.0 - gap) * 0.60)
    wet = np.clip(N.tileable_fbm(size, 5, 3, seed=seed + 21) * 1.9 - 1.05, 0.0, 1.0)
    occlusion = np.clip(0.34 + height * 0.66, 0.0, 1.0)
    roughness = np.clip(0.82 - wet * 0.36, 0.05, 1.0)
    return TextureSet("slate_roof", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.2))


def alpine_turf(size: int = 512, seed: int = 443) -> TextureSet:
    """Thin high-altitude turf over scree: the ground between the terraces."""
    loam = N.tileable_fbm(size, 9, 5, seed=seed)
    turf = N.tileable_fbm(size, 26, 4, seed=seed + 5)
    scree = np.clip(_upsample(N.tileable_worley(min(size, 256), 22, seed=seed + 9), size)
                    * 1.8 - 0.95, 0.0, 1.0)
    body = np.clip(loam * 0.55 + turf * 0.45, 0, 1)
    color = _colorize(body, (0.0, (0.078, 0.096, 0.062)), (0.4, (0.132, 0.158, 0.092)),
                      (0.72, (0.186, 0.212, 0.124)), (1.0, (0.244, 0.262, 0.164)))
    # bare stone comes through wherever the turf thins
    color = _mix(color, np.array([0.238, 0.238, 0.232]), scree * 0.66)
    frost = np.clip(N.tileable_fbm(size, 6, 3, seed=seed + 27) * 2.1 - 1.45, 0.0, 1.0)
    color = _mix(color, np.array([0.760, 0.790, 0.820]), frost * 0.34)
    height = np.clip(0.40 + turf * 0.34 + scree * 0.22, 0.0, 1.0)
    occlusion = np.clip(0.40 + height * 0.60, 0.0, 1.0)
    roughness = np.clip(0.94 - frost * 0.10, 0.05, 1.0)
    return TextureSet("alpine_turf", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.8))
# Amethyst Barrens kit
#
# A storm-scoured crystal basin: ochre dust and gravel over dark scoured rock,
# shot through with violet amethyst that grows out of the ground and glows.
# The built work is pale warm limestone with verdigris copper roofs and brass
# instruments, after the Glasswarden observatory in panel 2.
#
# Appended, never inserted, and every name carries the `amethyst_` prefix so
# the four regions in flight cannot collide on a material name.
# --------------------------------------------------------------------------

_AMETHYST_DEEP = (0.180, 0.086, 0.286)
_AMETHYST_MID = (0.392, 0.184, 0.588)
_AMETHYST_BRIGHT = (0.612, 0.352, 0.824)
_AMETHYST_PALE = (0.808, 0.678, 0.941)


def amethyst_barrens_dust(size: int = 512, seed: int = 501) -> TextureSet:
    """The basin floor: ochre dust, gravel, and chips of shed crystal."""
    grain = N.tileable_fbm(size, 26, 5, seed=seed)
    drift = N.tileable_fbm(size, 5, 4, seed=seed + 3)
    gravel = _upsample(N.tileable_worley(min(size, 256), 34, seed=seed + 7), size)
    height = grain * 0.4 + gravel * 0.45 + drift * 0.15
    color = _colorize(np.clip(drift * 0.7 + grain * 0.3, 0, 1),
                      (0.0, (0.286, 0.226, 0.132)),
                      (0.40, (0.470, 0.382, 0.204)),
                      (0.72, (0.612, 0.508, 0.286)),
                      (1.0, (0.714, 0.618, 0.392)))
    # stones sitting proud of the dust read cooler and greyer
    stone = np.clip(gravel * 1.7 - 0.85, 0.0, 1.0)
    color = _mix(color, np.array([0.352, 0.330, 0.318]), stone * 0.55)
    # scattered crystal chips, sparse enough to read as litter not as a field
    chip = np.clip(_upsample(N.tileable_worley(min(size, 256), 15, seed=seed + 11), size)
                   * 2.4 - 1.75, 0.0, 1.0)
    color = _mix(color, np.array(_AMETHYST_MID), chip * 0.78)
    occlusion = np.clip(0.46 + height * 0.52, 0.0, 1.0)
    roughness = np.clip(0.94 - chip * 0.55 - stone * 0.06, 0.0, 1.0)
    return TextureSet("amethyst_barrens_dust", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.4))


def amethyst_crystal_field(size: int = 512, seed: int = 509) -> TextureSet:
    """Ground given over to crystal: shards packed close, dust in the gaps."""
    # Few, large cells: the shards in panel 4 are hand-sized and bigger, so a
    # high cell count reads as violet noise rather than as broken crystal.
    # Worley distance is 0 at a cell's seed point and rises toward its boundary,
    # so the shard BODY is the low ground and the gap between shards is the high
    # ground. Reading it the other way puts the dust in the middle of each shard.
    dist = _upsample(N.tileable_worley(min(size, 256), 9, seed=seed), size)
    edge = _upsample(N.tileable_worley(min(size, 256), 9, seed=seed, order=1), size)
    facet = _upsample(N.tileable_worley(min(size, 256), 20, seed=seed + 5), size)
    dust = N.tileable_fbm(size, 18, 4, seed=seed + 9)
    shard = 1.0 - dist
    body = np.clip(shard * 0.66 + (1.0 - facet) * 0.34, 0, 1)
    height = body * 0.78 + dust * 0.22
    color = _colorize(body, (0.0, _AMETHYST_DEEP), (0.42, _AMETHYST_MID),
                      (0.78, _AMETHYST_BRIGHT), (1.0, _AMETHYST_PALE))
    # a bright crease along the shared boundary of two shards
    rim = np.clip(1.0 - (edge - dist) * 6.0, 0.0, 1.0)
    color = _mix(color, np.array(_AMETHYST_PALE), rim * 0.42)
    # ochre dust lies in the gaps, and there is a lot of it
    gap = np.clip(dist * 2.2 - 0.55, 0.0, 1.0)
    color = _mix(color, np.array([0.470, 0.386, 0.222]), gap * 0.85)
    # Knock the whole patch back toward the barrens it sits in. At full
    # saturation the crystal fields read as flat pink decals laid over the
    # ochre rather than as ground with crystal growing through it.
    color = _mix(color, np.array([0.404, 0.336, 0.212]), 0.34)
    occlusion = np.clip(0.34 + body * 0.64, 0.0, 1.0)
    roughness = np.clip(0.20 + gap * 0.72 + dust * 0.10, 0.0, 1.0)
    return TextureSet("amethyst_crystal_field", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.4))


def amethyst_resonant_road(size: int = 512, seed: int = 521) -> TextureSet:
    """The resonant roadway: pale flags with lit crystal running the joints.

    Panel 3's bridge deck and the roads on the aerial are the same surface —
    laid stone whose seams have been filled with growing amethyst.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # staggered flagstones
    row = np.floor(gy * 6.0)
    offset = (row % 2) * 0.5
    fx = (gx * 6.0 + offset) % 1.0
    fy = (gy * 6.0) % 1.0
    joint = np.minimum(np.minimum(fx, 1.0 - fx), np.minimum(fy, 1.0 - fy))
    seam = np.clip(1.0 - joint * 14.0, 0.0, 1.0)
    wear = N.tileable_fbm(size, 14, 4, seed=seed)
    # Darker than the observatory's ashlar: this is roadway laid on the barrens,
    # and it has to let the vein read as the bright thing in the surface.
    stone = _colorize(np.clip(wear, 0, 1), (0.0, (0.196, 0.186, 0.184)),
                      (0.5, (0.310, 0.296, 0.288)), (1.0, (0.412, 0.396, 0.380)))
    # the vein itself, brightest at the centre of the joint
    vein = seam ** 1.6
    color = _mix(stone, np.array(_AMETHYST_MID), vein * 0.95)
    color = _mix(color, np.array(_AMETHYST_BRIGHT), np.clip(vein - 0.45, 0, 1) * 1.6)
    color = _mix(color, np.array(_AMETHYST_PALE), np.clip(vein - 0.80, 0, 1) * 3.4)
    height = (1.0 - seam) * 0.7 + wear * 0.3
    occlusion = np.clip(0.50 + (1.0 - seam) * 0.46, 0.0, 1.0)
    roughness = np.clip(0.82 - vein * 0.62, 0.0, 1.0)
    return TextureSet("amethyst_resonant_road", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.0))


def amethyst_storm_rock(size: int = 512, seed: int = 523) -> TextureSet:
    """Dark basalt scoured by the storms, cracked and veined with violet."""
    strata = N.tileable_fbm(size, 7, 5, seed=seed)
    # The difference between the first and second Worley orders is small only
    # along a cell boundary, which is what draws a connected crack network
    # instead of the isolated specks a single order gives.
    near = _upsample(N.tileable_worley(min(size, 256), 12, seed=seed + 3), size)
    second = _upsample(N.tileable_worley(min(size, 256), 12, seed=seed + 3, order=1), size)
    fracture = np.clip((second - near) * 3.2, 0.0, 1.0)
    grain = N.tileable_fbm(size, 30, 4, seed=seed + 7)
    height = strata * 0.5 + fracture * 0.36 + grain * 0.14
    # Lifted off black: at value 0.10 the rock read as a hole in the map and the
    # violet in its cracks disappeared with it.
    color = _colorize(np.clip(strata * 0.75 + grain * 0.25, 0, 1),
                      (0.0, (0.116, 0.106, 0.120)),
                      (0.45, (0.180, 0.168, 0.186)),
                      (0.80, (0.256, 0.240, 0.258)),
                      (1.0, (0.330, 0.314, 0.328)))
    # Crystal has got into some of the cracks, not all of them: an unmasked
    # network covers the rock like leading in a window and stops reading as rock.
    crack = np.clip(1.0 - fracture * 0.95, 0.0, 1.0)
    seam_mask = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 13) * 2.0 - 0.62, 0.0, 1.0)
    lit = crack * seam_mask
    color = _mix(color, np.array(_AMETHYST_MID), lit * 0.78)
    color = _mix(color, np.array(_AMETHYST_BRIGHT), np.clip(lit - 0.55, 0, 1) * 1.5)
    occlusion = np.clip(0.36 + height * 0.60, 0.0, 1.0)
    roughness = np.clip(0.88 - lit * 0.50, 0.0, 1.0)
    return TextureSet("amethyst_storm_rock", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.0))


def amethyst_crystal(size: int = 256, seed: int = 541) -> TextureSet:
    """The crystal itself: banded violet body, polished facets, lit from within."""
    band = N.tileable_fbm(size, 4, 5, seed=seed)
    facet = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed + 5), size)
    facet_edge = _upsample(N.tileable_worley(min(size, 256), 7, seed=seed + 5, order=1), size)
    body = np.clip(band * 0.42 + facet * 0.58, 0, 1)
    color = _colorize(body, (0.0, _AMETHYST_DEEP), (0.38, _AMETHYST_MID),
                      (0.74, _AMETHYST_BRIGHT), (1.0, _AMETHYST_PALE))
    # crisp facet boundaries: a crystal is planes meeting at edges, not clouds
    crease = np.clip(1.0 - (facet_edge - facet) * 7.0, 0.0, 1.0)
    color = _mix(color, np.array(_AMETHYST_DEEP), crease * 0.42)
    # milky inclusions near the base of a shard
    milk = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 11) * 1.7 - 0.95, 0.0, 1.0)
    color = _mix(color, np.array([0.878, 0.824, 0.941]), milk * 0.45)
    occlusion = np.full((size, size), 1.0)
    roughness = np.clip(0.06 + band * 0.14, 0.0, 1.0)
    return TextureSet("amethyst_crystal", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(body * 0.5, 1.8))


def amethyst_pale_stone(size: int = 512, seed: int = 547, courses: int = 9) -> TextureSet:
    """Warm pale limestone ashlar, the Glasswarden building stone."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = np.floor(gy * courses)
    offset = (row % 2) * 0.5
    fx = (gx * (courses + 1) + offset) % 1.0
    fy = (gy * courses) % 1.0
    joint = np.minimum(np.minimum(fx, 1.0 - fx), np.minimum(fy, 1.0 - fy))
    seam = np.clip(1.0 - joint * 18.0, 0.0, 1.0)
    grain = N.tileable_fbm(size, 22, 5, seed=seed)
    blotch = N.tileable_fbm(size, 6, 4, seed=seed + 3)
    color = _colorize(np.clip(blotch * 0.6 + grain * 0.4, 0, 1),
                      (0.0, (0.560, 0.520, 0.446)),
                      (0.45, (0.706, 0.664, 0.578)),
                      (0.80, (0.812, 0.774, 0.686)),
                      (1.0, (0.878, 0.846, 0.766)))
    # storm staining runs down from the joints
    stain = np.clip(N.tileable_fbm(size, 10, 4, seed=seed + 9) * 1.5 - 0.75, 0, 1)
    color = _mix(color, np.array([0.412, 0.386, 0.368]), stain * 0.38)
    color = _mix(color, np.array([0.352, 0.322, 0.286]), seam * 0.72)
    height = (1.0 - seam) * 0.72 + grain * 0.28
    occlusion = np.clip(0.44 + (1.0 - seam) * 0.54, 0.0, 1.0)
    roughness = np.clip(0.74 + grain * 0.16, 0.0, 1.0)
    return TextureSet("amethyst_pale_stone", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.6))


def amethyst_verdigris(size: int = 256, seed: int = 557) -> TextureSet:
    """Oxidised copper roofing: the teal domes and spire caps of the concept."""
    seam = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, _gy = np.meshgrid(seam, seam)
    standing = np.clip(1.0 - np.abs(((gx * 10.0) % 1.0) - 0.5) * 5.0, 0.0, 1.0)
    patina = N.tileable_fbm(size, 8, 5, seed=seed)
    grime = N.tileable_fbm(size, 20, 4, seed=seed + 5)
    color = _colorize(np.clip(patina, 0, 1), (0.0, (0.086, 0.216, 0.212)),
                      (0.42, (0.157, 0.392, 0.365)),
                      (0.76, (0.259, 0.541, 0.494)),
                      (1.0, (0.400, 0.678, 0.612)))
    # copper showing through where rain keeps the metal clean
    bare = np.clip(grime * 1.9 - 1.35, 0.0, 1.0)
    color = _mix(color, np.array([0.478, 0.294, 0.157]), bare * 0.6)
    height = standing * 0.6 + patina * 0.4
    occlusion = np.clip(0.52 + height * 0.44, 0.0, 1.0)
    roughness = np.clip(0.62 + patina * 0.26 - bare * 0.3, 0.0, 1.0)
    metallic = np.clip(0.25 + bare * 0.7, 0.0, 1.0)
    return TextureSet("amethyst_verdigris", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness, metallic),
                      normal_from_height(height, 2.2))


def amethyst_brass(size: int = 256, seed: int = 563) -> TextureSet:
    """Instrument brass: the orrery ring, the scales, the field-station fittings."""
    turn = _upsample(N.tileable_worley(min(size, 256), 20, seed=seed), size)
    grain = N.tileable_fbm(size, 34, 4, seed=seed + 3)
    tarnish = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 7) * 1.8 - 0.9, 0.0, 1.0)
    height = turn * 0.5 + grain * 0.5
    color = _colorize(np.clip(turn * 0.6 + grain * 0.4, 0, 1),
                      (0.0, (0.376, 0.276, 0.106)),
                      (0.5, (0.635, 0.486, 0.196)),
                      (0.85, (0.792, 0.639, 0.290)),
                      (1.0, (0.878, 0.749, 0.404)))
    color = _mix(color, np.array([0.216, 0.196, 0.129]), tarnish * 0.55)
    occlusion = np.clip(0.58 + height * 0.40, 0.0, 1.0)
    roughness = np.clip(0.24 + tarnish * 0.44 + grain * 0.08, 0.0, 1.0)
    metallic = np.clip(0.96 - tarnish * 0.28, 0.0, 1.0)
    return TextureSet("amethyst_brass", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness, metallic),
                      normal_from_height(height, 1.8))


def amethyst_banner(size: int = 256, seed: int = 569) -> TextureSet:
    """Glasswarden purple: banners, tent canopies, the storm-ruin standards."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    weave = (0.5 + 0.5 * np.sin(gx * math.pi * 2.0 * 80.0)) \
        * (0.5 + 0.5 * np.sin(gy * math.pi * 2.0 * 80.0))
    fade = N.tileable_fbm(size, 5, 4, seed=seed)
    wear = np.clip(N.tileable_fbm(size, 16, 4, seed=seed + 5) * 1.7 - 0.95, 0.0, 1.0)
    deep = np.array([0.204, 0.098, 0.267])
    lit = np.array([0.365, 0.196, 0.447])
    color = _mix(deep[None, None, :] * np.ones((size, size, 1)), lit, fade * 0.7)
    color = color * (0.76 + 0.36 * weave)[..., None]
    color = _mix(color, np.array([0.478, 0.412, 0.372]), wear * 0.42)
    occlusion = np.clip(0.60 + weave * 0.32, 0.0, 1.0)
    roughness = np.full((size, size), 0.88)
    return TextureSet("amethyst_banner", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(weave * 0.4, 1.2))


def amethyst_vault_floor(size: int = 512, seed: int = 577) -> TextureSet:
    """The Resonant Vault's floor: dark polished slate inlaid with brass.

    Every panel of the vault's concept board is shot across this surface, so it
    carries the room. Large slabs rather than small flags, a mirror polish that
    picks up the crystal light, and a brass line running the joints - the
    Glasswardens laid a circuit into their own floor.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    slabs = 4.0
    fx = (gx * slabs) % 1.0
    fy = (gy * slabs) % 1.0
    joint = np.minimum(np.minimum(fx, 1.0 - fx), np.minimum(fy, 1.0 - fy))
    seam = np.clip(1.0 - joint * 26.0, 0.0, 1.0)

    grain = N.tileable_fbm(size, 9, 5, seed=seed)
    swirl = N.tileable_fbm(size, 3, 4, seed=seed + 3)
    color = _colorize(np.clip(swirl * 0.6 + grain * 0.4, 0, 1),
                      (0.0, (0.062, 0.066, 0.082)),
                      (0.45, (0.106, 0.112, 0.136)),
                      (0.80, (0.152, 0.160, 0.190)),
                      (1.0, (0.204, 0.212, 0.244)))
    # the brass inlay sits in the joint, bright and narrow
    inlay = np.clip(seam * 1.35 - 0.18, 0.0, 1.0)
    color = _mix(color, np.array([0.612, 0.470, 0.196]), inlay * 0.92)
    color = _mix(color, np.array([0.816, 0.678, 0.353]),
                 np.clip(inlay - 0.55, 0, 1) * 1.8)
    # a violet cast where the crystal light pools in the polish
    bloom = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 7) * 1.7 - 0.85, 0.0, 1.0)
    color = _mix(color, np.array([0.243, 0.145, 0.353]), bloom * 0.30)

    height = (1.0 - seam) * 0.5 + grain * 0.5
    occlusion = np.clip(0.58 + (1.0 - seam) * 0.40, 0.0, 1.0)
    # polished stone, but the brass is duller than the slate around it
    roughness = np.clip(0.20 + grain * 0.10 + inlay * 0.30, 0.0, 1.0)
    metallic = np.clip(inlay * 0.85, 0.0, 1.0)
    return TextureSet("amethyst_vault_floor", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness, metallic),
                      normal_from_height(height, 1.6))
# --------------------------------------------------------------------------
# Whitehorn: the silver its monks mined, and the granite they cut it from
# --------------------------------------------------------------------------

def whitehorn_silver(size: int = 256, seed: int = 601) -> TextureSet:
    """Worked silver for the temple's reliquary, bell and altar fittings.

    The interior concept names "ice granite silver" as its material study and
    the shared table had no white metal - only dark iron and warm brass, both
    of which read as the wrong century for a mountain reliquary.

    Deliberately not fully metallic. With metallic at 1.0 and no reflection
    probe, a metal has nothing to reflect and renders black in both the offline
    rasteriser and Godot; the Amethyst build hit this on verdigris and brass.
    At 0.45 the diffuse term still carries the surface.
    """
    grain = N.tileable_fbm(size, 26, 4, seed=seed)
    # hammered facets, broader than the grain so it reads as beaten sheet
    beat = N.tileable_worley(min(size, 128), 9, seed=seed + 7)
    beat = _upsample(beat, size)
    body = np.clip(0.62 + grain * 0.22 - beat * 0.18, 0.0, 1.0)
    color = _colorize(body, (0.0, (0.316, 0.330, 0.350)),
                      (0.45, (0.548, 0.566, 0.586)),
                      (0.8, (0.736, 0.752, 0.768)),
                      (1.0, (0.868, 0.878, 0.888)))
    # tarnish gathers in the hollows of the beating and along engraved lines
    tarnish = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 11) * 2.2 - 1.5,
                      0.0, 1.0)
    color = _mix(color, np.array([0.212, 0.208, 0.236]), tarnish * 0.45)
    height = np.clip(0.5 + grain * 0.16 - beat * 0.22, 0.0, 1.0)
    occlusion = np.clip(0.62 + height * 0.38, 0.0, 1.0)
    roughness = np.clip(0.22 + tarnish * 0.5 + beat * 0.16, 0.06, 1.0)
    return TextureSet("whitehorn_silver", _u8(color),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 0.8))




# --------------------------------------------------------------------------
# Verdant Stair
#
# A terraced limestone jungle: pale bedded rock, cut-stone terraces going to
# moss, jade-green carved architecture, and a canopy of broad wet leaves. The
# palette is deliberately narrow - three greens, one stone, one jade - because
# the region reads by silhouette and level, not by material variety.
# --------------------------------------------------------------------------

def _pinna_polygon(draw: "ImageDraw.ImageDraw", cx: float, cy: float, length: float,
                   angle: float, fill, width_ratio: float = 0.17) -> None:
    """One leaflet of a pinnate frond: a long blade, not a lobed leaf.

    `_leaf_polygon` draws a wide oak-like lobe, which at frond scale stacks
    into something closer to a pine cone than a fern. A pinna is narrow, has a
    straight edge on the rachis side and tapers to a point.
    """
    points = []
    steps = 12
    for i in range(steps + 1):
        t = i / steps
        r = length * width_ratio * math.sin(math.pi * min(max(t, 0.02), 0.99)) ** 0.62
        points.append((-length * 0.5 + t * length, -r))
    for i in range(steps, -1, -1):
        t = i / steps
        r = length * width_ratio * 0.55 * math.sin(math.pi * min(max(t, 0.02), 0.99)) ** 0.9
        points.append((-length * 0.5 + t * length, r))
    c, s = math.cos(angle), math.sin(angle)
    draw.polygon([(cx + px * c - py * s, cy + px * s + py * c) for px, py in points],
                 fill=fill)


def verdant_jungle_floor(size: int = 512, seed: int = 601) -> TextureSet:
    """Wet humus under broad fallen leaves, with moss and surface roots."""
    rng = np.random.default_rng(seed)
    humus = N.tileable_fbm(size, 7, 5, seed=seed)
    color = _colorize(humus, (0.0, (0.020, 0.023, 0.014)), (0.5, (0.042, 0.048, 0.026)),
                      (1.0, (0.074, 0.080, 0.044)))
    height = humus * 0.28

    leaf_color = Image.new("RGB", (size, size), (0, 0, 0))
    leaf_alpha = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(leaf_color)
    ad = ImageDraw.Draw(leaf_alpha)
    # broadleaf litter: fewer, larger and greener than a temperate forest floor
    palette = [(38, 48, 20), (28, 38, 16), (50, 58, 24), (62, 54, 22),
               (44, 34, 17), (24, 34, 17), (56, 64, 27)]
    for _ in range(260):
        cx, cy = rng.uniform(0, size, 2)
        length = rng.uniform(size * 0.028, size * 0.150)
        angle = rng.uniform(0, math.pi * 2)
        base = palette[int(rng.integers(0, len(palette)))]
        shade = rng.uniform(0.42, 1.10)
        fill = tuple(int(min(255, c * shade)) for c in base)
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                if abs(cx + dx - size / 2) > size or abs(cy + dy - size / 2) > size:
                    continue
                _leaf_polygon(cd, cx + dx, cy + dy, length, angle, fill, lobes=2)
                _leaf_polygon(ad, cx + dx, cy + dy, length, angle, 255, lobes=2)
    leaves = np.asarray(leaf_color).astype(np.float64) / 255.0
    mask = np.asarray(leaf_alpha).astype(np.float64) / 255.0
    color = _mix(color, leaves, mask * 0.90)
    height = height + mask * 0.30

    # surface roots: long, low, wandering ridges
    root = np.clip(np.abs(N.tileable_fbm(size, 3, 4, seed=seed + 19) - 0.5) * 6.0, 0.0, 1.0)
    root = np.clip(1.0 - root, 0.0, 1.0) ** 3.0
    color = _mix(color, np.array([0.086, 0.070, 0.048]), root * 0.70)
    height = height + root * 0.34

    moss = np.clip(N.tileable_fbm(size, 6, 5, seed=seed + 23) * 2.1 - 0.98, 0.0, 1.0)
    color = _mix(color, np.array([0.062, 0.128, 0.048]), moss * (1.0 - mask * 0.5) * 0.80)
    occlusion = np.clip(0.36 + height * 0.56 - moss * 0.08, 0.0, 1.0)
    roughness = np.full((size, size), 0.94) - moss * 0.06
    return TextureSet("verdant_jungle_floor", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 2.8))


def verdant_jungle_trail(size: int = 512, seed: int = 607) -> TextureSet:
    """A trodden earth track through the understory: wet clay, pebbles, litter."""
    earth = N.tileable_fbm(size, 9, 5, seed=seed)
    packed = _colorize(earth, (0.0, (0.148, 0.116, 0.082)), (0.5, (0.236, 0.190, 0.136)),
                       (1.0, (0.330, 0.272, 0.198)))
    # the trail is never clean: leaf drift creeps in from both shoulders, but
    # the trodden centre has to stay visibly lighter than the floor beside it
    drift = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 11) * 1.9 - 1.02, 0.0, 1.0)
    litter = _colorize(N.tileable_fbm(size, 12, 4, seed=seed + 13),
                       (0.0, (0.056, 0.070, 0.030)), (1.0, (0.118, 0.128, 0.056)))
    color = _mix(packed, litter, drift * 0.62)
    pebbles = np.clip(_upsample(N.tileable_worley(min(size, 256), 30, seed=seed + 5),
                                size) * 2.0 - 1.30, 0.0, 1.0)
    color = _mix(color, np.array([0.318, 0.310, 0.286]), pebbles * 0.74)
    puddle = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 17) * 2.2 - 1.52, 0.0, 1.0)
    color = _mix(color, np.array([0.086, 0.098, 0.086]), puddle * 0.66)
    height = earth * 0.30 + drift * 0.20 + pebbles * 0.42 - puddle * 0.24
    occlusion = np.clip(0.50 + height * 0.44, 0.0, 1.0)
    roughness = np.clip(0.95 - puddle * 0.55, 0.0, 1.0)
    return TextureSet("verdant_jungle_trail", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 2.2))


def _limestone_flags(size: int, seed: int, courses: int = 6):
    """Shared body for the cut-stone terrace surfaces: coursed pale flagstones."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    rng = np.random.default_rng(seed)
    row = np.floor(gy * courses)
    # every course is offset, and no two flags are the same length
    offset = rng.uniform(0.0, 1.0, size=courses)[row.astype(int) % courses]
    span = 1.6 + rng.uniform(0.0, 1.2, size=courses)[row.astype(int) % courses]
    fx = (gx + offset) * courses * span
    column = np.floor(fx)
    joint_y = np.minimum(gy * courses - row, 1.0 - (gy * courses - row))
    joint_x = np.minimum(fx - column, 1.0 - (fx - column))
    joint = np.clip(np.minimum(joint_y * 13.0, joint_x * 11.0), 0.0, 1.0)
    flag = rng.uniform(0.0, 1.0, size=4096)[
        (row.astype(np.int64) * 977 + column.astype(np.int64) * 131) % 4096]
    wear = N.tileable_fbm(size, 20, 4, seed=seed + 3)
    height = joint * 0.72 + wear * 0.16 + flag * 0.06
    return gx, gy, joint, flag, wear, height


def verdant_terrace_stone(size: int = 512, seed: int = 613) -> TextureSet:
    """Laid limestone flags: pale, sun-bleached on the faces, moss in the joints."""
    _, _, joint, flag, wear, height = _limestone_flags(size, seed)
    color = _colorize(np.clip(flag * 0.55 + wear * 0.45, 0, 1),
                      (0.0, (0.176, 0.172, 0.152)), (0.45, (0.240, 0.234, 0.208)),
                      (0.8, (0.300, 0.292, 0.262)), (1.0, (0.354, 0.346, 0.310)))
    color = _mix(color, np.array([0.176, 0.174, 0.152]), (1.0 - joint) * 0.72)
    moss = np.clip(N.tileable_fbm(size, 8, 4, seed=seed + 9) * 1.9 - 0.92, 0.0, 1.0)
    moss = np.maximum(moss * 0.7, (1.0 - joint) * 0.55)
    color = _mix(color, np.array([0.098, 0.150, 0.062]), moss * 0.62)
    damp = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 15) * 2.0 - 1.20, 0.0, 1.0)
    color = _mix(color, np.array([0.196, 0.204, 0.188]), damp * 0.42)
    occlusion = np.clip(0.32 + joint * 0.64, 0.0, 1.0)
    roughness = np.clip(0.90 - damp * 0.26, 0.0, 1.0)
    return TextureSet("verdant_terrace_stone", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 4.2))


def verdant_mossy_stone(size: int = 512, seed: int = 617) -> TextureSet:
    """The same flags where the jungle has won: moss over most of the face."""
    _, _, joint, flag, wear, height = _limestone_flags(size, seed, courses=5)
    color = _colorize(np.clip(flag * 0.55 + wear * 0.45, 0, 1),
                      (0.0, (0.196, 0.196, 0.172)), (0.5, (0.276, 0.272, 0.242)),
                      (1.0, (0.352, 0.346, 0.310)))
    color = _mix(color, np.array([0.128, 0.128, 0.112]), (1.0 - joint) * 0.80)
    moss = np.clip(N.tileable_fbm(size, 6, 5, seed=seed + 7) * 1.7 - 0.42, 0.0, 1.0)
    moss = np.maximum(moss, (1.0 - joint) * 0.85)
    body = _colorize(N.tileable_fbm(size, 14, 4, seed=seed + 11),
                     (0.0, (0.044, 0.088, 0.032)), (0.5, (0.078, 0.140, 0.052)),
                     (1.0, (0.124, 0.196, 0.076)))
    color = _mix(color, body, moss * 0.88)
    height = height + moss * 0.22
    occlusion = np.clip(0.28 + joint * 0.58 + (1.0 - moss) * 0.12, 0.0, 1.0)
    roughness = np.clip(0.94 - moss * 0.08, 0.0, 1.0)
    return TextureSet("verdant_mossy_stone", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 3.6))


def verdant_wet_limestone(size: int = 512, seed: int = 619) -> TextureSet:
    """Spray-wet rock behind a fall: dark runnels, algae film, mineral bloom."""
    flow = N.tileable_fbm(size, 5, 5, seed=seed)
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # vertical runnels: the water has been finding the same lines for a long
    # time, so they are many, fine and almost parallel - not a few fat tubes
    fine = N.tileable_value_noise(gx * 96.0, gy * 2.0, 96, 2, seed + 5)
    coarse = N.tileable_value_noise(gx * 34.0, gy * 2.0, 34, 2, seed + 7)
    runnel = np.clip(np.abs(fine - 0.5) * 7.0, 0.0, 1.0) * 0.62         + np.clip(np.abs(coarse - 0.5) * 5.0, 0.0, 1.0) * 0.38
    channel = np.clip(1.0 - runnel, 0.0, 1.0) ** 1.8
    height = np.clip(0.42 + flow * 0.26 - channel * 0.40, 0.0, 1.0)
    color = _colorize(np.clip(flow * 0.6 + (1.0 - channel) * 0.4, 0, 1),
                      (0.0, (0.048, 0.056, 0.052)), (0.5, (0.098, 0.110, 0.100)),
                      (1.0, (0.166, 0.178, 0.162)))
    color = _mix(color, np.array([0.022, 0.030, 0.028]), channel * 0.76)
    algae = np.clip(N.tileable_fbm(size, 9, 4, seed=seed + 13) * 1.8 - 0.62, 0.0, 1.0)
    color = _mix(color, np.array([0.042, 0.092, 0.050]), algae * 0.74)
    # the mineral crust is a highlight, not the body of the rock
    bloom = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 21) * 2.1 - 1.58, 0.0, 1.0)
    color = _mix(color, np.array([0.242, 0.250, 0.232]), bloom * 0.44)
    occlusion = np.clip(0.30 + height * 0.66, 0.0, 1.0)
    # wet rock is the least rough surface in the region, which is what sells it
    roughness = np.clip(0.44 + bloom * 0.34 - channel * 0.18, 0.0, 1.0)
    return TextureSet("verdant_wet_limestone", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 4.4))


def verdant_limestone_cliff(size: int = 512, seed: int = 631) -> TextureSet:
    """Bedded pale limestone: hard strata, solution pitting, vines in the cracks."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    tilt = (N.tileable_value_noise(gx * 3.0, gy * 3.0, 3, 3, seed + 41) - 0.5) * 0.22
    # two bedding rhythms plus a wandering term: equal courses read as masonry
    bedding = (gy * 11.0 + tilt * 2.0
               + N.tileable_fbm(size, 5, 4, seed=seed) * 2.6
               + N.tileable_value_noise(gx * 4.0, gy * 4.0, 4, 4, seed + 61) * 1.5)
    band = np.floor(bedding)
    within = bedding - band
    rng = np.random.default_rng(seed + 3)
    band_value = rng.uniform(0.0, 1.0, size=64)[band.astype(int) % 64]
    # a hard shadow line at every bedding plane: limestone breaks in courses,
    # and without a crisp riser the cliff reads as folded fabric
    ledge = np.clip(1.0 - within * 9.0, 0.0, 1.0) ** 0.45
    face = 0.40 + 0.48 * band_value + within * 0.22

    # karst solution pitting rather than the angular jointing of a hard coast
    pit_near = _upsample(N.tileable_worley(min(size, 256), 24, seed=seed + 5), size)
    pit = np.clip(pit_near * 2.8 - 1.05, 0.0, 1.0)
    detail = N.tileable_fbm(size, 44, 5, seed=seed + 9)
    grit = N.tileable_fbm(size, 96, 3, seed=seed + 15)
    # the bedding owns the relief; pitting and grit only roughen the faces
    height = np.clip(0.46 + face * 0.10 - ledge * 0.92 - pit * 0.10
                     + detail * 0.12 + grit * 0.07, 0.0, 1.0)

    color = _colorize(np.clip(face * 0.62 + detail * 0.38, 0, 1),
                      (0.0, (0.062, 0.066, 0.058)), (0.35, (0.108, 0.110, 0.096)),
                      (0.7, (0.158, 0.158, 0.138)), (1.0, (0.216, 0.212, 0.186)))
    color = _mix(color, np.array([0.054, 0.054, 0.048]), pit * 0.54)
    # the shadow under each course is the thing that says "rock in beds"
    color = _mix(color, np.array([0.058, 0.058, 0.052]), ledge * 0.88)
    # the cliff is never bare: moss on the wet ledges, vines down the cracks
    moss = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 27) * 2.0 - 0.96, 0.0, 1.0)
    color = _mix(color, np.array([0.050, 0.096, 0.036]), moss * 0.92)
    # vines hang straight down the face and are the region's signature on rock
    vine = np.clip(N.tileable_value_noise(gx * 23.0, gy * 2.0, 23, 2, seed + 33) * 2.6 - 1.62,
                   0.0, 1.0)
    color = _mix(color, np.array([0.044, 0.092, 0.034]), vine * 0.78)
    occlusion = np.clip(0.28 + height * 0.72, 0.0, 1.0)
    roughness = np.clip(0.92 - moss * 0.06, 0.0, 1.0)
    return TextureSet("verdant_limestone_cliff", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 3.2))


def verdant_lagoon_sand(size: int = 512, seed: int = 641) -> TextureSet:
    """Pale coral sand with shell grit and the damp line the tide leaves."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    grain = N.tileable_fbm(size, 40, 4, seed=seed)
    ripple = N.tileable_value_noise(gx * 9.0, gy * 34.0, 9, 34, seed + 3)
    color = _colorize(np.clip(grain * 0.5 + ripple * 0.5, 0, 1),
                      (0.0, (0.404, 0.376, 0.316)), (0.5, (0.520, 0.492, 0.424)),
                      (1.0, (0.638, 0.612, 0.542)))
    shell = np.clip(_upsample(N.tileable_worley(min(size, 256), 44, seed=seed + 7),
                              size) * 2.2 - 1.62, 0.0, 1.0)
    color = _mix(color, np.array([0.812, 0.792, 0.744]), shell * 0.80)
    damp = np.clip(N.tileable_fbm(size, 3, 4, seed=seed + 11) * 1.9 - 0.92, 0.0, 1.0)
    color = _mix(color, np.array([0.286, 0.276, 0.246]), damp * 0.58)
    weed = np.clip(N.tileable_fbm(size, 11, 4, seed=seed + 17) * 2.3 - 1.62, 0.0, 1.0)
    color = _mix(color, np.array([0.086, 0.116, 0.062]), weed * 0.68)
    height = ripple * 0.36 + grain * 0.18 + shell * 0.30
    occlusion = np.clip(0.58 + height * 0.36, 0.0, 1.0)
    roughness = np.clip(0.94 - damp * 0.22, 0.0, 1.0)
    return TextureSet("verdant_lagoon_sand", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 1.8))


def verdant_fern_glade(size: int = 512, seed: int = 643) -> TextureSet:
    """Ground seen through low ferns: overlapping fronds, deep shade beneath."""
    rng = np.random.default_rng(seed)
    soil = N.tileable_fbm(size, 8, 5, seed=seed)
    color = _colorize(soil, (0.0, (0.022, 0.030, 0.016)), (1.0, (0.052, 0.062, 0.030)))
    height = soil * 0.2

    frond_color = Image.new("RGB", (size, size), (0, 0, 0))
    frond_alpha = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(frond_color)
    ad = ImageDraw.Draw(frond_alpha)
    greens = [(52, 86, 30), (66, 104, 36), (40, 70, 26), (82, 118, 44),
              (34, 58, 22), (74, 96, 38)]
    for _ in range(220):
        cx, cy = rng.uniform(0, size, 2)
        angle = rng.uniform(0, math.pi * 2)
        length = rng.uniform(size * 0.09, size * 0.20)
        base = greens[int(rng.integers(0, len(greens)))]
        shade = rng.uniform(0.60, 1.20)
        fill = tuple(int(min(255, c * shade)) for c in base)
        pinnae = int(rng.integers(7, 13))
        for dx in (-size, 0, size):
            for dy in (-size, 0, size):
                px, py = cx + dx, cy + dy
                if abs(px - size / 2) > size or abs(py - size / 2) > size:
                    continue
                c, s = math.cos(angle), math.sin(angle)
                for k in range(pinnae):
                    t = (k + 1) / pinnae
                    taper = math.sin(math.pi * min(max(t, 0.05), 0.95)) ** 0.6
                    leaf_len = length * 0.30 * taper
                    if leaf_len < 1.5:
                        continue
                    for side in (-1, 1):
                        lx = px + (length * (t - 0.5)) * c
                        ly = py + (length * (t - 0.5)) * s
                        _leaf_polygon(cd, lx + side * leaf_len * 0.5 * -s,
                                      ly + side * leaf_len * 0.5 * c,
                                      leaf_len, angle + side * 1.35, fill, lobes=1)
                        _leaf_polygon(ad, lx + side * leaf_len * 0.5 * -s,
                                      ly + side * leaf_len * 0.5 * c,
                                      leaf_len, angle + side * 1.35, 255, lobes=1)
    fronds = np.asarray(frond_color).astype(np.float64) / 255.0
    mask = np.asarray(frond_alpha).astype(np.float64) / 255.0
    color = _mix(color, fronds, mask * 0.94)
    height = height + mask * 0.42
    occlusion = np.clip(0.30 + mask * 0.62, 0.0, 1.0)
    roughness = np.full((size, size), 0.90)
    return TextureSet("verdant_fern_glade", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 2.4))


def verdant_jade(size: int = 512, seed: int = 647) -> TextureSet:
    """The region's architectural stone: polished jade-green with cloudy veining.

    Not a metal and not verdigris. Verdigris is a crust on bronze and reads
    blue; this is a cut stone the builders quarried, so it keeps a stone's
    roughness and a stone's depth of colour.
    """
    swirl = N.tileable_fbm(size, 3, 5, seed=seed)
    cloud = N.tileable_fbm(size, 9, 5, seed=seed + 5)
    body = np.clip(swirl * 0.68 + cloud * 0.32, 0, 1)
    color = _colorize(body, (0.0, (0.028, 0.086, 0.070)), (0.35, (0.056, 0.150, 0.118)),
                      (0.7, (0.104, 0.226, 0.176)), (1.0, (0.176, 0.312, 0.240)))
    vein = np.clip(np.abs(N.tileable_fbm(size, 5, 4, seed=seed + 11) - 0.5) * 7.0, 0.0, 1.0)
    vein = np.clip(1.0 - vein, 0.0, 1.0) ** 2.6
    color = _mix(color, np.array([0.290, 0.400, 0.322]), vein * 0.70)
    dark = np.clip(N.tileable_fbm(size, 16, 4, seed=seed + 17) * 1.9 - 1.05, 0.0, 1.0)
    color = _mix(color, np.array([0.016, 0.046, 0.038]), dark * 0.55)
    height = body * 0.22 + vein * 0.10
    occlusion = np.clip(0.62 + height * 0.34, 0.0, 1.0)
    roughness = np.clip(0.46 - vein * 0.10 + dark * 0.16, 0.0, 1.0)
    return TextureSet("verdant_jade", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 1.6))


def verdant_carved_jade(size: int = 512, seed: int = 653) -> TextureSet:
    """Jade cut with the region's spiral-meander band, as on the close-up panel."""
    base = verdant_jade(size, seed + 1)
    color = np.asarray(base.base_color).astype(np.float64) / 255.0

    relief = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(relief)
    cells = 4
    step = size // cells
    width = max(2, size // 96)
    for cy in range(cells):
        for cx in range(cells):
            ox, oy = cx * step, cy * step
            # a squared spiral: three turns inward, the meander of the reliefs
            margin = step * 0.16
            x0, y0 = ox + margin, oy + margin
            x1, y1 = ox + step - margin, oy + step - margin
            gap = (x1 - x0) / 7.0
            inset = 0.0
            points = []
            for _turn in range(3):
                points.extend([(x0 + inset, y1 - inset), (x0 + inset, y0 + inset),
                               (x1 - inset, y0 + inset), (x1 - inset, y1 - inset - gap),
                               (x0 + inset + gap, y1 - inset - gap)])
                inset += gap
            draw.line(points, fill=255, width=width, joint="curve")
    carved = np.asarray(relief.filter(ImageFilter.GaussianBlur(size / 340.0))) \
        .astype(np.float64) / 255.0
    # the groove is cut into the stone, so it is darker and lower, not raised
    color = _mix(color, np.array([0.014, 0.048, 0.038]), carved * 0.82)
    height = N.tileable_fbm(size, 9, 4, seed=seed + 3) * 0.12 + (1.0 - carved) * 0.42
    occlusion = np.clip(0.94 - carved * 0.52, 0.0, 1.0)
    roughness = np.clip(0.44 + carved * 0.24, 0.0, 1.0)
    return TextureSet("verdant_carved_jade", _u8(color),
                      pack_orm(occlusion, roughness), normal_from_height(height, 4.0))


def verdant_rope(size: int = 256, seed: int = 659) -> TextureSet:
    """Twisted hemp cable: three strands laid right-handed, weathered pale."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    strands = 3.0
    lay = np.sin((gx * strands + gy * 0.85) * math.pi * 2.0)
    body = 0.5 + 0.5 * lay
    fibre = N.tileable_value_noise(gx * 64.0, gy * 10.0, 64, 10, seed)
    height = np.clip(body * 0.78 + fibre * 0.22, 0.0, 1.0)
    color = _colorize(np.clip(body * 0.62 + fibre * 0.38, 0, 1),
                      (0.0, (0.128, 0.108, 0.074)), (0.5, (0.238, 0.204, 0.140)),
                      (1.0, (0.344, 0.306, 0.220)))
    fray = np.clip(N.tileable_fbm(size, 18, 4, seed=seed + 5) * 2.0 - 1.22, 0.0, 1.0)
    color = _mix(color, np.array([0.402, 0.370, 0.286]), fray * 0.62)
    damp = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 9) * 2.0 - 1.30, 0.0, 1.0)
    color = _mix(color, np.array([0.074, 0.086, 0.058]), damp * 0.60)
    occlusion = np.clip(0.34 + height * 0.62, 0.0, 1.0)
    roughness = np.full((size, size), 0.97)
    return TextureSet("verdant_rope", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.0))


def verdant_frond_atlas(size: int = 512, seed: int = 661) -> TextureSet:
    """Alpha-cut atlas of pinnate fronds: tree fern and palm, 2x2 cells.

    Distinct from `foliage_atlas`, which sprays small lobed leaves off a twig.
    A frond is one long rachis carrying paired pinnae, and that shape is most
    of what makes a jungle canopy read as a jungle rather than as a wood.
    """
    rng = np.random.default_rng(seed)
    color_image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha_image = Image.new("L", (size, size), 0)
    depth_image = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(color_image)
    ad = ImageDraw.Draw(alpha_image)
    dd = ImageDraw.Draw(depth_image)

    greens = [(46, 78, 28), (60, 96, 34), (36, 62, 24), (78, 112, 42),
              (28, 50, 20), (68, 88, 34), (92, 124, 48)]
    half = size // 2
    for cell_y in range(2):
        for cell_x in range(2):
            ox, oy = cell_x * half, cell_y * half
            # two or three fronds per cell, springing from the cell's base edge
            for _frond in range(int(rng.integers(1, 3))):
                base_x = ox + half * float(rng.uniform(0.30, 0.70))
                base_y = oy + half * 0.97
                lean = float(rng.uniform(-0.42, 0.42))
                length = half * float(rng.uniform(0.72, 0.94))
                arc = float(rng.uniform(0.10, 0.28))
                spine = []
                steps = 26
                for i in range(steps + 1):
                    t = i / steps
                    x = base_x + lean * half * 0.5 * t + arc * half * 0.30 * t * t
                    y = base_y - length * t
                    spine.append((x, y))
                rachis = max(1, size // 280)
                cd.line(spine, fill=(52, 62, 30), width=rachis)
                ad.line(spine, fill=255, width=rachis)
                for i in range(1, steps + 1):
                    t = i / steps
                    # pinnae are longest in the middle third, short at both ends
                    taper = math.sin(math.pi * min(max(t, 0.04), 0.99)) ** 0.55
                    pinna = half * 0.21 * taper * float(rng.uniform(0.88, 1.12))
                    if pinna < 2.0:
                        continue
                    px, py = spine[i]
                    qx, qy = spine[i - 1]
                    ang = math.atan2(py - qy, px - qx)
                    base = greens[int(rng.integers(0, len(greens)))]
                    shade = 0.58 + 0.52 * t
                    fill = tuple(int(min(255, c * shade)) for c in base)
                    for side in (-1, 1):
                        sweep = ang + side * (0.72 + 0.30 * (1.0 - t))
                        mx = px + math.cos(sweep) * pinna * 0.5
                        my = py + math.sin(sweep) * pinna * 0.5
                        _pinna_polygon(cd, mx, my, pinna, sweep, fill)
                        _pinna_polygon(ad, mx, my, pinna, sweep, 255)
                        _pinna_polygon(dd, mx, my, pinna, sweep, int(80 + 170 * t))

    color = np.asarray(color_image).astype(np.float64) / 255.0
    alpha = np.asarray(alpha_image).astype(np.float64) / 255.0
    depth = np.asarray(depth_image.filter(ImageFilter.GaussianBlur(1.5))) \
        .astype(np.float64) / 255.0
    variation = N.tileable_fbm(size, 6, 4, seed=seed + 9)
    color = color * (0.70 + 0.44 * variation)[..., None]
    occlusion = np.clip(0.40 + depth * 0.66, 0.0, 1.0)
    roughness = np.full((size, size), 0.84) - depth * 0.10
    return TextureSet("verdant_frond", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(depth * 0.5, 2.0),
                      _u8((alpha > 0.5).astype(np.float64)))


def verdant_vine_atlas(size: int = 512, seed: int = 673) -> TextureSet:
    """Alpha-cut atlas of hanging lianas: cords with paired leaves, 2x2 cells."""
    rng = np.random.default_rng(seed)
    color_image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha_image = Image.new("L", (size, size), 0)
    depth_image = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(color_image)
    ad = ImageDraw.Draw(alpha_image)
    dd = ImageDraw.Draw(depth_image)
    greens = [(48, 82, 30), (62, 100, 36), (34, 60, 24), (80, 114, 44), (30, 52, 22)]
    half = size // 2
    for cell_y in range(2):
        for cell_x in range(2):
            ox, oy = cell_x * half, cell_y * half
            for _strand in range(int(rng.integers(3, 6))):
                x = ox + half * float(rng.uniform(0.12, 0.88))
                drift = float(rng.uniform(-0.10, 0.10))
                path = []
                steps = 20
                drop = half * float(rng.uniform(0.55, 0.98))
                for i in range(steps + 1):
                    t = i / steps
                    path.append((x + drift * half * math.sin(t * 3.4) + t * drift * half,
                                 oy + half * 0.03 + drop * t))
                cd.line(path, fill=(56, 50, 32), width=max(1, size // 340))
                ad.line(path, fill=255, width=max(1, size // 340))
                for i in range(2, steps + 1, 2):
                    px, py = path[i]
                    leaf = half * 0.085 * float(rng.uniform(0.7, 1.25))
                    base = greens[int(rng.integers(0, len(greens)))]
                    fill = tuple(int(min(255, c * float(rng.uniform(0.7, 1.2))))
                                 for c in base)
                    for side in (-1, 1):
                        ang = side * 0.55 + math.pi * 0.5
                        mx = px + math.cos(ang) * leaf * 0.55
                        my = py + math.sin(ang) * leaf * 0.35
                        _pinna_polygon(cd, mx, my, leaf, ang, fill, 0.34)
                        _pinna_polygon(ad, mx, my, leaf, ang, 255, 0.34)
                        _pinna_polygon(dd, mx, my, leaf, ang, 190, 0.34)
    color = np.asarray(color_image).astype(np.float64) / 255.0
    alpha = np.asarray(alpha_image).astype(np.float64) / 255.0
    depth = np.asarray(depth_image.filter(ImageFilter.GaussianBlur(1.3))) \
        .astype(np.float64) / 255.0
    variation = N.tileable_fbm(size, 5, 4, seed=seed + 7)
    color = color * (0.68 + 0.46 * variation)[..., None]
    occlusion = np.clip(0.42 + depth * 0.62, 0.0, 1.0)
    roughness = np.full((size, size), 0.86)
    return TextureSet("verdant_vine", _u8(color), pack_orm(occlusion, roughness),
                      normal_from_height(depth * 0.4, 1.8),
                      _u8((alpha > 0.5).astype(np.float64)))


# --------------------------------------------------------------------------
# Grey Moors kit
#
# A drowned burial moor under permanent overcast: sodden black peat and olive
# moor-grass shot through with purple heather, grey lichen-blotched granite
# standing in it, and warm candle-light in the barrow mouths. The palette is
# deliberately narrow and desaturated - the concept has almost no saturated
# colour except the heather, the amber doorways and the blue-white wisps, and
# those only read as bright because everything around them is grey.
#
# Appended, never inserted, and every name carries the `grey_` prefix so the
# regions in flight cannot collide on a material name.
# --------------------------------------------------------------------------

_MOOR_PEAT = (0.086, 0.074, 0.062)
_MOOR_LOAM = (0.128, 0.122, 0.092)
# Warmed slightly against the concept, which is a brown-olive moor rather than
# a grey-green one; the aerial comparison read cold beside the painting.
_MOOR_GRASS = (0.196, 0.192, 0.124)
_MOOR_STRAW = (0.278, 0.258, 0.164)
_MOOR_HEATHER = (0.336, 0.226, 0.352)
_MOOR_HEATHER_PALE = (0.494, 0.372, 0.500)
_MOOR_GRANITE = (0.392, 0.396, 0.388)
_MOOR_LICHEN = (0.508, 0.520, 0.436)


def grey_heather_moor(size: int = 512, seed: int = 601) -> TextureSet:
    """The default ground of the region: tussock moor-grass over wet peat.

    Panels 1, 3 and 10 all show the same surface - olive and straw grass in
    clumps, dark sodden ground between them, and heather coming through in
    ragged purple patches rather than an even wash.
    """
    tussock = N.tileable_fbm(size, 24, 5, seed=seed)
    drift = N.tileable_fbm(size, 6, 4, seed=seed + 3)
    clump = _upsample(N.tileable_worley(min(size, 256), 18, seed=seed + 7), size)
    body = np.clip(tussock * 0.52 + drift * 0.30 + (1.0 - clump) * 0.18, 0, 1)
    color = _colorize(body, (0.0, _MOOR_PEAT), (0.34, _MOOR_LOAM),
                      (0.68, _MOOR_GRASS), (1.0, _MOOR_STRAW))
    # heather in patches, driven by a separate low-frequency field so it does
    # not simply follow the grass and turn the whole surface mauve
    heath = np.clip(N.tileable_fbm(size, 4, 4, seed=seed + 11) * 2.3 - 1.18, 0.0, 1.0)
    heath = heath * np.clip(tussock * 1.5 - 0.25, 0.0, 1.0)
    color = _mix(color, np.array(_MOOR_HEATHER), heath * 0.72)
    color = _mix(color, np.array(_MOOR_HEATHER_PALE), heath * heath * 0.34)
    # standing wet in the hollows: darker and much less rough
    wet = np.clip(0.62 - body, 0.0, 1.0) * np.clip(drift * 1.8 - 0.35, 0.0, 1.0)
    color = _mix(color, np.array([0.056, 0.056, 0.052]), wet * 0.72)
    height = np.clip(0.34 + tussock * 0.44 + (1.0 - clump) * 0.22, 0.0, 1.0)
    occlusion = np.clip(0.38 + height * 0.60, 0.0, 1.0)
    roughness = np.clip(0.98 - wet * 0.62, 0.05, 1.0)
    return TextureSet("grey_heather_moor", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.6))


def grey_peat_bog(size: int = 512, seed: int = 607) -> TextureSet:
    """Sodden cut peat and sphagnum: the black ground the boardwalks cross.

    Panel 8's peat banks are almost pure black-brown with a wet sheen, broken
    by pale sphagnum and the white heads of bog cotton.
    """
    fibre = N.tileable_fbm(size, 30, 5, seed=seed)
    slick = N.tileable_fbm(size, 7, 4, seed=seed + 5)
    body = np.clip(fibre * 0.46 + slick * 0.54, 0, 1)
    color = _colorize(body, (0.0, (0.062, 0.058, 0.050)),
                      (0.42, (0.108, 0.096, 0.074)),
                      (0.74, (0.164, 0.146, 0.106)),
                      (1.0, (0.224, 0.204, 0.146)))
    # sphagnum: pale sour green, in small close cushions
    moss = np.clip(_upsample(N.tileable_worley(min(size, 256), 26, seed=seed + 9), size)
                   * -1.9 + 1.05, 0.0, 1.0)
    moss = moss * np.clip(slick * 1.7 - 0.42, 0.0, 1.0)
    color = _mix(color, np.array([0.286, 0.320, 0.204]), moss * 0.88)
    # Bog cotton: few and large. A high Worley cell count with a hard
    # threshold gave a uniform star-field of single texels, which reads as
    # sensor noise rather than as flower heads.
    cotton = np.clip(_upsample(N.tileable_worley(min(size, 256), 5, seed=seed + 13), size)
                     * -6.0 + 0.72, 0.0, 1.0)
    cotton = cotton * np.clip(N.tileable_fbm(size, 4, 3, seed=seed + 21) * 1.9 - 0.72,
                              0.0, 1.0)
    color = _mix(color, np.array([0.828, 0.840, 0.808]), cotton * 0.86)
    # the sheen: peat holds water, so most of this surface is near-mirror
    sheen = np.clip(slick * 1.4 - 0.24, 0.0, 1.0)
    height = np.clip(0.42 + fibre * 0.34 + moss * 0.24, 0.0, 1.0)
    occlusion = np.clip(0.34 + height * 0.58, 0.0, 1.0)
    roughness = np.clip(0.88 - sheen * 0.30 + moss * 0.10, 0.46, 1.0)
    return TextureSet("grey_peat_bog", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.2))


def grey_causeway(size: int = 512, seed: int = 613) -> TextureSet:
    """The laid stone track of panel 1: irregular wet flags, moss in the joints.

    Not a Roman road - these are field stones set flat into the peat, so the
    courses are irregular and the joints are wide and green.
    """
    # irregular flags: a jittered Worley cellular pattern reads as set stones
    dist = _upsample(N.tileable_worley(min(size, 256), 11, seed=seed), size)
    edge = _upsample(N.tileable_worley(min(size, 256), 11, seed=seed, order=1), size)
    joint = np.clip(1.0 - (edge - dist) * 7.0, 0.0, 1.0)
    grain = N.tileable_fbm(size, 28, 4, seed=seed + 3)
    face = np.clip(0.52 + grain * 0.42 - dist * 0.34, 0, 1)
    # Darker than dressed masonry: these are field stones bedded in wet peat
    # under a permanently overcast sky, not a swept plaza.
    color = _colorize(face, (0.0, (0.090, 0.094, 0.093)), (0.45, (0.150, 0.156, 0.153)),
                      (0.78, (0.208, 0.214, 0.208)), (1.0, (0.270, 0.272, 0.262)))
    # Each flag takes its own tone. Modulating by the Worley distance itself
    # gives a smooth gradient inside every cell instead of one tone per stone,
    # so the variation is driven by a coarse field sampled at cell scale.
    patch = N.tileable_fbm(size, 12, 2, seed=seed + 31)
    color = _mix(color, np.array([0.148, 0.156, 0.142]),
                 np.clip(patch * 1.6 - 0.36, 0.0, 1.0) * 0.52)
    color = _mix(color, np.array([0.316, 0.312, 0.290]),
                 np.clip(patch * -1.6 + 0.72, 0.0, 1.0) * 0.30)
    # wet moss and peat pushed up between the stones
    color = _mix(color, np.array([0.146, 0.170, 0.106]), joint * 0.82)
    # standing water lying on the flags: the panel's track is mirror-wet
    pool = np.clip(N.tileable_fbm(size, 5, 3, seed=seed + 17) * 2.0 - 1.02, 0.0, 1.0)
    color = _mix(color, np.array([0.128, 0.136, 0.140]), pool * 0.44)
    height = np.clip(0.68 + grain * 0.20 - joint * 0.56, 0.0, 1.0)
    occlusion = np.clip(0.40 + height * 0.58, 0.0, 1.0)
    roughness = np.clip(0.82 - pool * 0.66 + joint * 0.12, 0.04, 1.0)
    return TextureSet("grey_causeway", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.0))


def grey_barrow_turf(size: int = 512, seed: int = 617) -> TextureSet:
    """Close-cropped turf over a barrow: greener than the moor, stone beneath.

    Panel 2's mound is grassed right over, but the kerb stones and the drystone
    of the chamber show through wherever the turf has slipped.
    """
    turf = N.tileable_fbm(size, 44, 5, seed=seed)
    sward = N.tileable_fbm(size, 9, 4, seed=seed + 5)
    body = np.clip(turf * 0.60 + sward * 0.40, 0, 1)
    # Kept close to the moor it sits in. Brighter greens read as mown lawn on a
    # burial mound once the client's own key light is on them, which is what
    # the first Godot capture of the Great Barrow showed.
    color = _colorize(body, (0.0, (0.076, 0.084, 0.056)), (0.40, (0.124, 0.138, 0.086)),
                      (0.74, (0.174, 0.188, 0.116)), (1.0, (0.230, 0.240, 0.154)))
    # stone showing through where the turf is thin
    # Worley ridges run along the cell boundaries, so a strong mix paints a
    # bright web of veins over the whole mound rather than a few bald patches.
    # Kept sparse, and to a stone tone darker than the turf so it reads as
    # something showing through rather than as cracking.
    stone = np.clip(_upsample(N.tileable_worley(min(size, 256), 10, seed=seed + 9), size)
                    * 2.6 - 1.86, 0.0, 1.0)
    color = _mix(color, np.array([0.268, 0.268, 0.258]), stone * 0.52)
    lichen = np.clip(N.tileable_fbm(size, 30, 3, seed=seed + 13) * 2.2 - 1.32, 0.0, 1.0)
    color = _mix(color, np.array(_MOOR_LICHEN), lichen * stone * 0.62)
    height = np.clip(0.44 + turf * 0.34 + stone * 0.22, 0.0, 1.0)
    occlusion = np.clip(0.42 + height * 0.56, 0.0, 1.0)
    roughness = np.clip(0.96 - stone * 0.12, 0.05, 1.0)
    return TextureSet("grey_barrow_turf", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.4))


def grey_moor_granite(size: int = 512, seed: int = 619) -> TextureSet:
    """The standing stones: coarse grey granite under grey and gold lichen.

    Panel 3 is the reference. The lichen is what makes these read as ancient
    rather than as freshly quarried, so it is generous and blotchy.
    """
    grain = N.tileable_fbm(size, 34, 5, seed=seed)
    body = N.tileable_fbm(size, 9, 4, seed=seed + 3)
    crystal = _upsample(N.tileable_worley(min(size, 256), 40, seed=seed + 7), size)
    face = np.clip(body * 0.54 + grain * 0.32 + (1.0 - crystal) * 0.14, 0, 1)
    color = _colorize(face, (0.0, (0.104, 0.106, 0.108)), (0.42, (0.190, 0.194, 0.192)),
                      (0.76, (0.286, 0.290, 0.284)), (1.0, (0.390, 0.390, 0.380)))
    # feldspar flecks
    color = _mix(color, np.array([0.640, 0.628, 0.598]),
                 np.clip(crystal * -2.6 + 0.62, 0.0, 1.0) * 0.42)
    # lichen: two colonies, grey-green and a rarer ochre
    # Lichen colonises in discrete patches with bare stone between them. Driving
    # it hard off a near-uniform Worley field covered the whole face in even
    # yellow-green spots, which reads as mould on cheese rather than as a
    # weathered menhir; the coarse fbm gate is what keeps colonies apart.
    lichen = np.clip(N.tileable_fbm(size, 7, 4, seed=seed + 11) * 2.6 - 1.42, 0.0, 1.0)
    fringe = np.clip(_upsample(N.tileable_worley(min(size, 256), 18, seed=seed + 17), size)
                     * -2.0 + 1.12, 0.0, 1.0)
    color = _mix(color, np.array([0.436, 0.452, 0.396]), lichen * fringe * 0.62)
    ochre = np.clip(N.tileable_fbm(size, 11, 3, seed=seed + 23) * 2.6 - 1.72, 0.0, 1.0)
    color = _mix(color, np.array([0.508, 0.436, 0.244]), ochre * fringe * 0.60)
    # rain streaks running down the stone
    streak = np.clip(N.tileable_fbm(size, 3, 3, seed=seed + 29) * 1.9 - 0.92, 0.0, 1.0)
    color = _mix(color, np.array([0.176, 0.180, 0.180]), streak * 0.30)
    height = np.clip(0.46 + grain * 0.30 + (1.0 - crystal) * 0.24, 0.0, 1.0)
    occlusion = np.clip(0.40 + height * 0.58, 0.0, 1.0)
    roughness = np.clip(0.92 - streak * 0.26 + lichen * 0.06, 0.05, 1.0)
    return TextureSet("grey_moor_granite", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.2))


def grey_carved_stone(size: int = 512, seed: int = 631) -> TextureSet:
    """The runed jambs of the crypt doorways in panels 2 and 5.

    Dressed stone, darker than the raw granite because it is cut and always
    wet, with a band of incised spiral and chevron work.
    """
    grain = N.tileable_fbm(size, 30, 4, seed=seed)
    body = N.tileable_fbm(size, 8, 4, seed=seed + 3)
    face = np.clip(body * 0.58 + grain * 0.42, 0, 1)
    color = _colorize(face, (0.0, (0.146, 0.140, 0.130)), (0.44, (0.226, 0.218, 0.202)),
                      (0.78, (0.312, 0.300, 0.278)), (1.0, (0.392, 0.376, 0.348)))
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # incised work: concentric spirals on a coarse lattice, plus chevron bands
    cell_x = (gx * 4.0) % 1.0 - 0.5
    cell_y = (gy * 4.0) % 1.0 - 0.5
    radius = np.hypot(cell_x, cell_y)
    angle = np.arctan2(cell_y, cell_x)
    spiral = np.cos(radius * 44.0 - angle * 3.0)
    carve = np.clip((spiral - 0.62) * 3.0, 0.0, 1.0) * np.clip(1.0 - radius * 2.6, 0.0, 1.0)
    chevron = np.clip(np.cos((np.abs((gy * 9.0) % 1.0 - 0.5) * 2.0 - gx * 6.0)
                             * np.pi * 2.0) - 0.72, 0.0, 1.0) * 3.4
    # Carving is banded on the real jambs, not applied over the whole face, so
    # both motifs are gated by a coarse field and the plain stone shows between.
    band = np.clip(np.cos(gy * np.pi * 4.0) * 1.4 + 0.35, 0.0, 1.0)
    carve = np.clip(carve * band + chevron * 0.5 * (1.0 - band), 0.0, 1.0)
    carve = carve * np.clip(N.tileable_fbm(size, 5, 3, seed=seed + 37) * 1.5 + 0.42,
                            0.0, 1.0)
    # cut lines hold shadow, water and lichen
    color = _mix(color, np.array([0.086, 0.086, 0.078]), carve * 0.80)
    lichen = np.clip(N.tileable_fbm(size, 12, 3, seed=seed + 13) * 2.3 - 1.42, 0.0, 1.0)
    color = _mix(color, np.array(_MOOR_LICHEN), lichen * 0.44)
    height = np.clip(0.72 + grain * 0.18 - carve * 0.66, 0.0, 1.0)
    occlusion = np.clip(0.32 + height * 0.64, 0.0, 1.0)
    roughness = np.clip(0.88 - lichen * 0.10, 0.05, 1.0)
    return TextureSet("grey_carved_stone", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.0))


def grey_bog_timber(size: int = 512, seed: int = 641) -> TextureSet:
    """The boardwalk of panel 4: bog oak planks, black-wet, silvered at the edge."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    plank = (gy * 7.0) % 1.0
    seam = np.clip(1.0 - np.minimum(plank, 1.0 - plank) * 26.0, 0.0, 1.0)
    index = np.floor(gy * 7.0)
    # each plank keeps its own tone and its own grain phase
    tone = np.clip(np.sin(index * 12.9898) * 0.5 + 0.5, 0, 1)
    grain = N.tileable_fbm(size, 46, 4, seed=seed) * 0.6 \
        + N.tileable_fbm(size, 12, 3, seed=seed + 5) * 0.4
    body = np.clip(grain * 0.62 + tone * 0.38, 0, 1)
    color = _colorize(body, (0.0, (0.062, 0.056, 0.050)), (0.40, (0.128, 0.112, 0.094)),
                      (0.74, (0.206, 0.188, 0.162)), (1.0, (0.302, 0.288, 0.262)))
    # silvered, weathered fibre standing up on the wearing surface
    silver = np.clip(N.tileable_fbm(size, 40, 3, seed=seed + 9) * 2.1 - 1.16, 0.0, 1.0)
    color = _mix(color, np.array([0.404, 0.400, 0.382]), silver * 0.50)
    # green slime in the seams and along the shaded edge of every plank
    slime = np.clip(N.tileable_fbm(size, 16, 3, seed=seed + 13) * 1.8 - 0.72, 0.0, 1.0)
    color = _mix(color, np.array([0.140, 0.176, 0.108]),
                 np.clip(seam + slime * 0.5, 0, 1) * 0.62)
    color = _mix(color, np.array([0.030, 0.028, 0.026]), seam * 0.72)
    wet = np.clip(N.tileable_fbm(size, 6, 3, seed=seed + 19) * 1.8 - 0.74, 0.0, 1.0)
    height = np.clip(0.70 + grain * 0.24 - seam * 0.64, 0.0, 1.0)
    occlusion = np.clip(0.34 + height * 0.62, 0.0, 1.0)
    roughness = np.clip(0.86 - wet * 0.58, 0.04, 1.0)
    return TextureSet("grey_bog_timber", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 3.4))


def grey_drystone(size: int = 512, seed: int = 643, courses: int = 9) -> TextureSet:
    """The cottage walling of panel 6: uncoursed drystone, no mortar at all.

    The gaps are true voids rather than mortar joints, so they go almost black
    and the normal map has to push them a long way in.
    """
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    row = gy * courses
    index = np.floor(row)
    within = row % 1.0
    # every course is offset by its own pseudo-random amount
    shift = (np.sin(index * 78.233) * 0.5 + 0.5)
    span = 6.0 + np.floor(np.sin(index * 21.7) * 1.6 + 1.6)
    col = (gx * span + shift) % 1.0
    joint = np.clip(1.0 - np.minimum(within, 1.0 - within) * 13.0, 0.0, 1.0)
    joint = np.maximum(joint, np.clip(1.0 - np.minimum(col, 1.0 - col) * 15.0, 0.0, 1.0))
    grain = N.tileable_fbm(size, 32, 4, seed=seed)
    stone_tone = np.clip(np.sin(index * 45.1 + np.floor(gx * span + shift) * 9.7)
                         * 0.5 + 0.5, 0, 1)
    face = np.clip(grain * 0.52 + stone_tone * 0.48, 0, 1)
    color = _colorize(face, (0.0, (0.176, 0.176, 0.170)), (0.42, (0.276, 0.278, 0.268)),
                      (0.76, (0.376, 0.374, 0.358)), (1.0, (0.470, 0.462, 0.440)))
    lichen = np.clip(N.tileable_fbm(size, 10, 4, seed=seed + 11) * 2.2 - 1.20, 0.0, 1.0)
    color = _mix(color, np.array(_MOOR_LICHEN), lichen * 0.56)
    # the voids between stones
    color = _mix(color, np.array([0.028, 0.028, 0.026]), joint * 0.88)
    height = np.clip(0.76 + grain * 0.18 - joint * 0.74, 0.0, 1.0)
    occlusion = np.clip(0.26 + height * 0.70, 0.0, 1.0)
    roughness = np.clip(0.96 - lichen * 0.06, 0.05, 1.0)
    return TextureSet("grey_drystone", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 4.6))


def grey_turf_roof(size: int = 512, seed: int = 647) -> TextureSet:
    """Sod roofing over the cottages, half fallen in and grown over."""
    sod = N.tileable_fbm(size, 16, 5, seed=seed)
    grass = N.tileable_fbm(size, 52, 4, seed=seed + 5)
    body = np.clip(sod * 0.42 + grass * 0.58, 0, 1)
    color = _colorize(body, (0.0, (0.076, 0.078, 0.056)), (0.40, (0.146, 0.156, 0.096)),
                      (0.74, (0.216, 0.226, 0.132)), (1.0, (0.296, 0.294, 0.184)))
    # bare earth and rotted thatch showing where the roof has failed
    bare = np.clip(N.tileable_fbm(size, 5, 3, seed=seed + 9) * 2.2 - 1.24, 0.0, 1.0)
    color = _mix(color, np.array([0.152, 0.126, 0.092]), bare * 0.72)
    height = np.clip(0.44 + sod * 0.36 + grass * 0.20, 0.0, 1.0)
    occlusion = np.clip(0.36 + height * 0.60, 0.0, 1.0)
    return TextureSet("grey_turf_roof", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, np.full((size, size), 0.97)),
                      normal_from_height(height, 3.0))


def grey_dead_bark(size: int = 512, seed: int = 653) -> TextureSet:
    """The bare tree of panel 7: bark long gone, silvered and split heartwood."""
    fibre = N.tileable_fbm(size, 8, 5, seed=seed)
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # long vertical splits running the length of the trunk
    split = np.clip(np.abs(np.sin((gx * 9.0 + fibre * 1.8) * np.pi)) * -3.4 + 1.0,
                    0.0, 1.0)
    grain = N.tileable_fbm(size, 60, 3, seed=seed + 5)
    body = np.clip(fibre * 0.50 + grain * 0.50, 0, 1)
    color = _colorize(body, (0.0, (0.128, 0.120, 0.108)), (0.42, (0.226, 0.216, 0.196)),
                      (0.76, (0.352, 0.340, 0.316)), (1.0, (0.474, 0.462, 0.436)))
    color = _mix(color, np.array([0.048, 0.044, 0.040]), split * 0.82)
    moss = np.clip(N.tileable_fbm(size, 16, 3, seed=seed + 13) * 2.4 - 1.52, 0.0, 1.0)
    color = _mix(color, np.array([0.176, 0.204, 0.128]), moss * 0.54)
    height = np.clip(0.66 + grain * 0.26 - split * 0.60, 0.0, 1.0)
    occlusion = np.clip(0.32 + height * 0.64, 0.0, 1.0)
    return TextureSet("grey_dead_bark", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, np.clip(0.94 - moss * 0.08, 0.05, 1.0)),
                      normal_from_height(height, 3.8))


def grey_bog_water(size: int = 512, seed: int = 659) -> TextureSet:
    """Peat-stained standing water: near-black, barely moving, highly reflective.

    Distinct from the region's sea. Bog pools in the concept are flat black
    mirrors holding the sky, not blue water.
    """
    ripple = N.tileable_fbm(size, 12, 4, seed=seed) * 0.6 \
        + N.tileable_fbm(size, 30, 3, seed=seed + 5) * 0.4
    scum = np.clip(N.tileable_fbm(size, 6, 4, seed=seed + 9) * 2.1 - 1.28, 0.0, 1.0)
    color = _colorize(np.clip(ripple, 0, 1),
                      (0.0, (0.020, 0.024, 0.024)), (0.5, (0.040, 0.046, 0.044)),
                      (1.0, (0.070, 0.076, 0.070)))
    # peat scum and duckweed gathering at the edges
    color = _mix(color, np.array([0.124, 0.134, 0.092]), scum * 0.66)
    height = np.clip(0.5 + (ripple - 0.5) * 0.30, 0.0, 1.0)
    # Not a mirror: at roughness 0.10 the pools reflected the whole sky and
    # read as bright blue discs on a grey moor. Peat water holds the sky dimly.
    roughness = np.clip(0.34 + scum * 0.46, 0.03, 1.0)
    return TextureSet("grey_bog_water", _u8(np.clip(color, 0, 1)),
                      pack_orm(np.full((size, size), 0.98), roughness),
                      normal_from_height(height, 1.1))


def _bleed_into_alpha(color: np.ndarray, opaque: np.ndarray,
                      iterations: int = 10) -> np.ndarray:
    """Push colour outward into the transparent texels of an alpha atlas.

    An atlas drawn on a black background stores black RGB wherever alpha is
    zero. That is invisible when the texture is sampled point-for-point, and
    catastrophic once it is not: bilinear filtering and every mip level average
    the plant colour with the black void around it, so an alpha-cut card fades
    to black as it recedes. The first Godot capture of Grey Moors came back
    with every scrub clump shaded solid black for exactly this reason, while
    the offline preview - which does not mipmap - looked correct.

    Dilating the colour outward means those averages pick up plant colour
    instead of void. Alpha is untouched, so the cut-out shape is unchanged.

    `amberwood`'s own `foliage_atlas` and `undergrowth_atlas` are drawn the same
    way and would benefit from this too, but they are pinned by the packages
    already built against them, so this is applied only where it is new.
    """
    out = np.array(color, dtype=np.float64, copy=True)
    known = np.asarray(opaque, dtype=bool)
    for _ in range(iterations):
        if known.all():
            break
        total = np.zeros_like(out)
        count = np.zeros(known.shape, dtype=np.float64)
        for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
            neighbour = np.roll(known, shift, axis=axis)
            colours = np.roll(out, shift, axis=axis)
            total += np.where(neighbour[..., None], colours, 0.0)
            count += neighbour
        fill = (~known) & (count > 0)
        out = np.where(fill[..., None], total / np.maximum(count, 1.0)[..., None], out)
        known = known | fill
    return out


def grey_moor_scrub(size: int = 512, seed: int = 661) -> TextureSet:
    """Alpha-cut atlas of moor ground cover: heather, sedge, bog cotton, bracken.

    Four cells in a 2x2 grid, matched to the clumps in panels 3, 8 and 10.
    """
    image = Image.new("RGB", (size, size), (0, 0, 0))
    alpha = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    mask = ImageDraw.Draw(alpha)
    rng = np.random.default_rng(seed)
    half = size // 2

    def stalk(ox, oy, count, height_frac, spread, palette, head=None,
              head_radius=0.0):
        for _ in range(count):
            bx = ox + half * (0.5 + (rng.random() - 0.5) * spread)
            by = oy + half * 0.94
            length = half * height_frac * (0.6 + rng.random() * 0.7)
            lean = (rng.random() - 0.5) * half * 0.30
            tx, ty = bx + lean, by - length
            width = max(1, int(half * 0.0052 * (0.7 + rng.random())))
            tone = palette[int(rng.integers(0, len(palette)))]
            draw.line([(bx, by), (tx, ty)], fill=tone, width=width)
            mask.line([(bx, by), (tx, ty)], fill=255, width=width)
            if head is not None:
                r = half * head_radius * (0.7 + rng.random() * 0.6)
                box = [tx - r, ty - r, tx + r, ty + r]
                draw.ellipse(box, fill=head[int(rng.integers(0, len(head)))])
                mask.ellipse(box, fill=255)

    # heather: dense, woody, purple flower heads
    # Every palette here is darker than the ground it stands on. Lighter
    # cards read as pale litter scattered over the moor rather than as plants
    # growing out of it, which is what the first pass looked like.
    stalk(0, 0, 120, 0.40, 1.05,
          [(40, 45, 28), (54, 60, 36), (31, 35, 23)],
          head=[(78, 54, 82), (104, 78, 108), (63, 44, 67)], head_radius=0.022)
    # sedge and moor grass: tall, thin, dull straw
    stalk(half, 0, 130, 0.80, 1.05,
          [(57, 54, 35), (75, 70, 45), (42, 42, 27), (90, 82, 52)])
    # bog cotton: sparse, with off-white heads. Kept few - the heads are the
    # brightest thing in the region after the votive flames, and at scatter
    # density a generous count reads as straw bales strewn over the moor.
    stalk(0, half, 22, 0.62, 1.0,
          [(54, 60, 39), (69, 75, 46)],
          head=[(150, 152, 143), (124, 126, 119)], head_radius=0.026)
    # bracken and dead fern, rust brown, low and broad
    stalk(half, half, 95, 0.38, 1.05,
          [(75, 57, 34), (94, 72, 42), (57, 43, 27), (108, 82, 49)])

    color = np.asarray(image).astype(np.float64) / 255.0
    alpha_array = np.asarray(alpha).astype(np.uint8)
    body = np.clip(N.tileable_fbm(size, 20, 3, seed=seed + 3), 0, 1)
    color = _mix(color, color * 0.74, body[..., None] * 0.30)
    color = _bleed_into_alpha(color, alpha_array > 96, iterations=12)
    occlusion = np.clip(0.52 + body * 0.42, 0.0, 1.0)
    return TextureSet("grey_moor_scrub", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, np.full((size, size), 0.95)),
                      normal_from_height(np.full((size, size), 0.5), 1.0),
                      alpha_array)


def grey_bone(size: int = 512, seed: int = 683) -> TextureSet:
    """Old bone: the ossuary walls and the skulls in the barrows.

    Panel 8 stacks it and panel 10 puts a skull in close-up. Ivory going grey
    and green where it has lain in peat water, with the fine longitudinal
    cracking that tells old bone from new stone.
    """
    grain = N.tileable_fbm(size, 40, 4, seed=seed)
    body = N.tileable_fbm(size, 9, 4, seed=seed + 3)
    face = np.clip(body * 0.62 + grain * 0.38, 0, 1)
    color = _colorize(face, (0.0, (0.284, 0.268, 0.226)), (0.42, (0.436, 0.414, 0.348)),
                      (0.76, (0.596, 0.570, 0.482)), (1.0, (0.724, 0.700, 0.606)))
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    # fine cracks running the length of the bone
    crack = np.clip(np.abs(np.sin((gy * 22.0 + body * 3.4) * np.pi)) * -7.0 + 1.0,
                    0.0, 1.0)
    color = _mix(color, np.array([0.156, 0.146, 0.122]), crack * 0.66)
    # peat stain: bone that has lain in this ground comes out brown, not white
    stain = np.clip(N.tileable_fbm(size, 5, 4, seed=seed + 9) * 2.0 - 0.92, 0.0, 1.0)
    color = _mix(color, np.array([0.300, 0.246, 0.152]), stain * 0.60)
    algae = np.clip(N.tileable_fbm(size, 14, 3, seed=seed + 13) * 2.3 - 1.52, 0.0, 1.0)
    color = _mix(color, np.array([0.244, 0.268, 0.176]), algae * 0.48)
    height = np.clip(0.62 + grain * 0.26 - crack * 0.52, 0.0, 1.0)
    occlusion = np.clip(0.36 + height * 0.60, 0.0, 1.0)
    roughness = np.clip(0.86 - stain * 0.10, 0.05, 1.0)
    return TextureSet("grey_bone", _u8(np.clip(color, 0, 1)),
                      pack_orm(occlusion, roughness),
                      normal_from_height(height, 2.8))


def grey_wisp(size: int = 128, seed: int = 673) -> TextureSet:
    """The blue-white marsh lights of panel 7. Emissive, no surface detail."""
    body = np.clip(N.tileable_fbm(size, 6, 3, seed=seed) * 0.4 + 0.72, 0, 1)
    color = _colorize(body, (0.0, (0.352, 0.560, 0.700)), (0.6, (0.640, 0.812, 0.912)),
                      (1.0, (0.880, 0.948, 0.984)))
    return TextureSet("grey_wisp", _u8(np.clip(color, 0, 1)),
                      pack_orm(np.full((size, size), 1.0), np.full((size, size), 0.34)),
                      normal_from_height(np.full((size, size), 0.5), 1.0))


def grey_votive_flame(size: int = 128, seed: int = 677) -> TextureSet:
    """Candle and doorway light: the warm amber that reads against all this grey."""
    body = np.clip(N.tileable_fbm(size, 5, 3, seed=seed) * 0.36 + 0.74, 0, 1)
    color = _colorize(body, (0.0, (0.560, 0.284, 0.076)), (0.55, (0.856, 0.564, 0.184)),
                      (1.0, (0.980, 0.856, 0.560)))
    return TextureSet("grey_votive_flame", _u8(np.clip(color, 0, 1)),
                      pack_orm(np.full((size, size), 1.0), np.full((size, size), 0.42)),
                      normal_from_height(np.full((size, size), 0.5), 1.0))


def hatchery_eggshell(size: int = 256, seed: int = 719) -> TextureSet:
    """Soft ivory with sparse mineral freckles, without masonry seams."""
    body = N.tileable_fbm(size, 6, 4, seed=seed)
    freckles = np.clip((N.tileable_fbm(size, 31, 3, seed=seed + 7) - .64) * 10, 0, 1)
    color = _mix((.60, .63, .50), (.82, .82, .69), body)
    color = _mix(color, (.31, .34, .22), freckles * .30)
    height = body * .025 + freckles * .01
    roughness = .70 + freckles * .10
    return TextureSet("hatchery_eggshell", _u8(color),
                      pack_orm(np.full_like(body, .97), roughness),
                      normal_from_height(height, .8))


def lily_pad(size: int = 256, seed: int = 727) -> TextureSet:
    """An opaque waxy leaf with radial veins, mapped onto a round pad."""
    body = N.tileable_fbm(size, 7, 4, seed=seed)
    y, x = np.mgrid[0:size, 0:size] / (size - 1) * 2 - 1
    radius = np.sqrt(x * x + y * y)
    angle = np.arctan2(y, x)
    veins = np.exp(-(np.sin(angle * 9) * 23) ** 2) * np.clip(1 - radius * .7, 0, 1)
    color = _mix((.025, .065, .024), (.09, .20, .058), body)
    color = _mix(color, (.14, .25, .07), veins * .55)
    height = body * .035 + veins * .02
    return TextureSet("lily_pad", _u8(color),
                      pack_orm(np.full_like(body, .95), .50 + body * .10),
                      normal_from_height(height, .8))
