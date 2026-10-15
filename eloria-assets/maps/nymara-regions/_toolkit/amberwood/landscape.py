"""Opt-in landscape operators. Distances are metres, never map-scale multiples."""
from __future__ import annotations
import numpy as np
from . import noise as N, terrain as TER


def smoothstep(lo, hi, value):
    u = np.clip((value - lo) / (hi - lo), 0, 1)
    return u * u * (3 - 2 * u)


def distance_field(t, lines):
    distance = np.full_like(t.height, 1e6)
    for line in lines:
        d, _ = TER._polyline_distance(t.gx, t.gz, np.asarray(line, dtype=float))
        distance = np.minimum(distance, d)
    return distance


def grove_density(t, roads, streams, seed, *, open_ground=None):
    """Sheltered stands, moist margins and gaps, without a saturated noise floor.

    Region authors provide roads/water and their own open-ground field; no biome
    colours, species or settlement locations are baked into this reusable rule.
    """
    road = distance_field(t, roads)
    water = distance_field(t, streams)
    gz, gx = np.gradient(t.height, t.cell)
    slope = np.hypot(gx, gz)
    stands = N.warped_fbm(t.gx / 52, t.gz / 52, warp=.7, octaves=2, seed=seed)
    pockets = N.value_noise(t.gx / 21, t.gz / 21, seed + 7)
    density = .10 + .75 * smoothstep(.27, .72, stands) + .14 * pockets
    density *= 1 - .65 * smoothstep(.45, 1.05, slope)
    density *= smoothstep(5.0, 12.0, road)
    density *= smoothstep(3.0, 7.0, water)
    density *= (t.height > 1.2) & ~t.tree_block
    density *= ~np.isin(t.surface, [TER.PAVING, TER.PATH, TER.SHORE, TER.ROCK])
    if open_ground is not None:
        density *= 1 - np.clip(open_ground, 0, 1)
    moisture = (1 - smoothstep(8, 30, water)) * (1 - smoothstep(.4, .9, slope))
    return np.clip(density, 0, .95), road, moisture


def worn_path(t, points, width, seed, surface=TER.PATH):
    """Paint an irregular worn margin in the existing terrain, with no overlay.

    Does not alter elevation: survey the traversable bed first. Busy roads can
    be wide; a footpath can be narrow without thinning its collision corridor.
    """
    d, along = TER._polyline_distance(t.gx, t.gz, np.asarray(points, dtype=float))
    variation = N.value_noise(t.gx / 11, t.gz / 11, seed) - .5
    edge = width / 2 + variation * 1.6 + .35 * np.sin(along * 19)
    mask = (d < edge) & ~np.isin(t.surface, [TER.PAVING, TER.SHORE])
    t.surface[mask] = surface
    t._write_strength(np.abs(d - edge) / t.cell, mask)


def feather_level(t, signed_distance, height, shoulder):
    """A level built core whose earth banks meet the unmodified hillside."""
    blend = 1 - smoothstep(0, shoulder, signed_distance)
    t.height = t.height * (1 - blend) + height * blend
