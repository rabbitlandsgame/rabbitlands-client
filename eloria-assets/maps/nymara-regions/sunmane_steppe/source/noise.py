"""Tileable procedural noise primitives used by the Sunmane texture kit.

Every generator here is periodic, so the resulting maps tile seamlessly in both
axes and can be repeated across large terrain and architecture without visible
joins.
"""
from __future__ import annotations

import zlib

import numpy as np


def stable_seed(text: str, modulus: int = 10_000) -> int:
    """A seed derived from a name that is the same in every interpreter.

    `hash()` on a str is salted per process, so seeding from one gives a
    different seed on every run and the package stops being reproducible - two
    builds of identical code produce different files. The production guide
    names this exact trap. CRC32 is stable across runs, platforms and Python
    versions.
    """
    return zlib.crc32(text.encode("utf-8")) % modulus


def _fade(t: np.ndarray) -> np.ndarray:
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def value_noise(size: int, period: int, rng: np.random.Generator) -> np.ndarray:
    """Periodic value noise on a `size` grid with `period` lattice cells across."""
    lattice = rng.random((period, period))
    coordinates = np.arange(size) * period / size
    cell = np.floor(coordinates).astype(int)
    frac = _fade(coordinates - cell)
    low, high = cell % period, (cell + 1) % period
    # Rows index Y, columns index X.
    fx = frac[None, :]
    fy = frac[:, None]
    top = lattice[np.ix_(low, low)] * (1.0 - fx) + lattice[np.ix_(low, high)] * fx
    bottom = lattice[np.ix_(high, low)] * (1.0 - fx) + lattice[np.ix_(high, high)] * fx
    return top * (1.0 - fy) + bottom * fy


def fbm(size: int, base_period: int, octaves: int, rng: np.random.Generator,
        gain: float = 0.5, lacunarity: int = 2) -> np.ndarray:
    """Fractal sum of periodic value noise, normalised to 0..1."""
    total = np.zeros((size, size))
    amplitude, weight, period = 1.0, 0.0, base_period
    for _ in range(octaves):
        if period > size:
            break
        total += value_noise(size, period, rng) * amplitude
        weight += amplitude
        amplitude *= gain
        period *= lacunarity
    total /= max(weight, 1e-6)
    return normalise(total)


def normalise(field: np.ndarray) -> np.ndarray:
    low, high = float(field.min()), float(field.max())
    if high - low < 1e-9:
        return np.zeros_like(field)
    return (field - low) / (high - low)


def worley(size: int, cells: int, rng: np.random.Generator,
           order: int = 0) -> np.ndarray:
    """Periodic Worley/cellular noise returning the nth-nearest feature distance.

    Only the 3x3 neighbourhood of each sample's own cell is searched, which is
    exact for one feature point per cell and keeps a 1024 grid well under a
    second.
    """
    feature = (rng.random((cells, cells, 2)) + np.stack(np.meshgrid(
        np.arange(cells), np.arange(cells), indexing="ij"), axis=-1)) / cells
    axis = (np.arange(size) + 0.5) / size
    gy, gx = np.meshgrid(axis, axis, indexing="ij")
    own_y = np.minimum((gy * cells).astype(int), cells - 1)
    own_x = np.minimum((gx * cells).astype(int), cells - 1)
    distances = np.empty((9, size, size))
    slot = 0
    for offset_y in (-1, 0, 1):
        for offset_x in (-1, 0, 1):
            neighbour = feature[(own_y + offset_y) % cells, (own_x + offset_x) % cells]
            delta_y = np.abs(neighbour[..., 0] - gy)
            delta_x = np.abs(neighbour[..., 1] - gx)
            delta_y = np.minimum(delta_y, 1.0 - delta_y)
            delta_x = np.minimum(delta_x, 1.0 - delta_x)
            distances[slot] = np.sqrt(delta_y ** 2 + delta_x ** 2)
            slot += 1
    ordered = np.partition(distances, order, axis=0)[order]
    return normalise(ordered)


def directional_grain(size: int, rng: np.random.Generator, *, stretch: int = 14,
                      period: int = 32, octaves: int = 4) -> np.ndarray:
    """Wood-style grain: noise stretched along +U, so planks read lengthwise."""
    field = fbm(size, period, octaves, rng)
    kernel = np.hanning(stretch * 2 + 1)
    kernel /= kernel.sum()
    padded = np.concatenate([field[:, -stretch:], field, field[:, :stretch]], axis=1)
    smoothed = np.apply_along_axis(
        lambda row: np.convolve(row, kernel, mode="valid"), 1, padded)
    return normalise(smoothed)


def height_to_normal(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    """Tangent-space normal map (OpenGL +Y up) from a tileable height field."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    normal = np.stack([-dx * strength, -dy * strength, np.ones_like(height)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5
