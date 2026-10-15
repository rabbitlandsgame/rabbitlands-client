"""Deterministic value/fBm noise on numpy grids.

Everything in the Amberwood build is seeded, so a rebuild reproduces the
committed runtime artefacts byte-for-byte.
"""
from __future__ import annotations

import zlib

import numpy as np


def _hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Integer lattice hash -> float in [0, 1)."""
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263
         + np.int64(seed) * 2147483647)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0x7FFFFFFF).astype(np.float64) / float(0x7FFFFFFF)


def stable_hash(text: str) -> int:
    """Process-independent string hash.

    `hash()` on str is salted per interpreter run (PEP 456), so seeds derived
    from it change on every build. Everything here is meant to be reproducible,
    so name-derived seeds use CRC-32 instead.
    """
    return zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF


def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def value_noise(x: np.ndarray, y: np.ndarray, seed: int = 0) -> np.ndarray:
    """Smooth value noise sampled at arbitrary float coordinates."""
    ix = np.floor(x)
    iy = np.floor(y)
    fx = _fade(x - ix)
    fy = _fade(y - iy)
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    n00 = _hash2(ix, iy, seed)
    n10 = _hash2(ix + 1, iy, seed)
    n01 = _hash2(ix, iy + 1, seed)
    n11 = _hash2(ix + 1, iy + 1, seed)
    a = n00 + (n10 - n00) * fx
    b = n01 + (n11 - n01) * fx
    return a + (b - a) * fy


def fbm(x: np.ndarray, y: np.ndarray, octaves: int = 5, lacunarity: float = 2.0,
        gain: float = 0.5, seed: int = 0) -> np.ndarray:
    """Fractal Brownian motion in [0, 1]."""
    total = np.zeros_like(np.asarray(x, dtype=np.float64))
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0
    for octave in range(octaves):
        total += amplitude * value_noise(x * frequency, y * frequency, seed + octave * 7919)
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity
    return total / max(norm, 1e-9)


def ridged(x: np.ndarray, y: np.ndarray, octaves: int = 5, seed: int = 0) -> np.ndarray:
    """Ridged multifractal in [0, 1] - used for cliff and rock silhouettes."""
    total = np.zeros_like(np.asarray(x, dtype=np.float64))
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0
    for octave in range(octaves):
        n = value_noise(x * frequency, y * frequency, seed + octave * 6271)
        n = 1.0 - np.abs(n * 2.0 - 1.0)
        total += amplitude * n * n
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / max(norm, 1e-9)


def warped_fbm(x: np.ndarray, y: np.ndarray, warp: float = 1.0, octaves: int = 5,
               seed: int = 0) -> np.ndarray:
    """Domain-warped fBm; breaks up the machine-made look of plain fBm."""
    wx = fbm(x + 11.3, y + 5.7, octaves=3, seed=seed + 101) * 2.0 - 1.0
    wy = fbm(x - 7.1, y + 19.4, octaves=3, seed=seed + 202) * 2.0 - 1.0
    return fbm(x + wx * warp, y + wy * warp, octaves=octaves, seed=seed)


class Rng:
    """Small deterministic PRNG wrapper so every placement pass is reproducible."""

    def __init__(self, seed: int) -> None:
        self._rng = np.random.default_rng(seed)

    def uniform(self, low: float = 0.0, high: float = 1.0, size=None):
        return self._rng.uniform(low, high, size)

    def integers(self, low: int, high: int, size=None):
        return self._rng.integers(low, high, size)

    def normal(self, loc: float = 0.0, scale: float = 1.0, size=None):
        return self._rng.normal(loc, scale, size)

    def choice(self, values, size=None, p=None, replace: bool = True):
        return self._rng.choice(values, size=size, p=p, replace=replace)

    def chance(self, probability: float) -> bool:
        return bool(self._rng.uniform() < probability)

    def shuffled(self, values):
        out = list(values)
        self._rng.shuffle(out)
        return out


def _hash2_periodic(ix, iy, period_x: int, period_y: int, seed: int) -> np.ndarray:
    return _hash2(np.mod(ix, period_x), np.mod(iy, period_y), seed)


def tileable_value_noise(x: np.ndarray, y: np.ndarray, period_x: int, period_y: int,
                         seed: int = 0) -> np.ndarray:
    ix = np.floor(x)
    iy = np.floor(y)
    fx = _fade(x - ix)
    fy = _fade(y - iy)
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    n00 = _hash2_periodic(ix, iy, period_x, period_y, seed)
    n10 = _hash2_periodic(ix + 1, iy, period_x, period_y, seed)
    n01 = _hash2_periodic(ix, iy + 1, period_x, period_y, seed)
    n11 = _hash2_periodic(ix + 1, iy + 1, period_x, period_y, seed)
    a = n00 + (n10 - n00) * fx
    b = n01 + (n11 - n01) * fx
    return a + (b - a) * fy


def tileable_fbm(size: int, base_frequency: int = 4, octaves: int = 5, gain: float = 0.5,
                 seed: int = 0) -> np.ndarray:
    """Seamless fBm on a size x size grid; wraps exactly at the edges."""
    u = np.linspace(0.0, 1.0, size, endpoint=False)
    gx, gy = np.meshgrid(u, u)
    total = np.zeros((size, size))
    amplitude = 1.0
    frequency = base_frequency
    norm = 0.0
    for octave in range(octaves):
        total += amplitude * tileable_value_noise(
            gx * frequency, gy * frequency, frequency, frequency, seed + octave * 3931)
        norm += amplitude
        amplitude *= gain
        frequency *= 2
    return total / max(norm, 1e-9)


def tileable_worley(size: int, cells: int = 8, seed: int = 0, order: int = 0) -> np.ndarray:
    """Seamless Worley/cellular noise in [0,1]; used for stone, bark and shingles.

    Vectorised: each pixel only consults its own cell and the eight neighbours,
    with the cell grid wrapped so the result tiles exactly.
    """
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(0.0, 1.0, size=(cells, cells, 2))
    u = (np.arange(size) + 0.5) / size
    gx, gy = np.meshgrid(u, u)
    cell_x = np.floor(gx * cells).astype(np.int64)
    cell_y = np.floor(gy * cells).astype(np.int64)
    best = np.full((size, size), 1e9)
    second = np.full((size, size), 1e9)
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            nx = cell_x + ox
            ny = cell_y + oy
            wx = np.mod(nx, cells)
            wy = np.mod(ny, cells)
            px = (nx + jitter[wy, wx, 0]) / cells
            py = (ny + jitter[wy, wx, 1]) / cells
            d = np.sqrt((gx - px) ** 2 + (gy - py) ** 2)
            second = np.minimum(second, np.maximum(best, d))
            best = np.minimum(best, d)
    result = second if order >= 1 else best
    return np.clip(result * cells, 0.0, 1.0)
