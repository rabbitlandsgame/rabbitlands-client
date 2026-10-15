"""Exact single or multipart isle ownership; compatibility rings never replace the union."""
from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union


def rings(value):
    """Normalize a geography record, one ring, or ordered multiple rings without changing corners."""
    if isinstance(value, dict):
        value = value.get("ownershipPolygons") or [value.get("ownershipPolygon")]
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) == 0:
        raise ValueError("ownership needs at least one polygon")
    first = value[0]
    if len(first) == 2 and all(np.isscalar(v) for v in first):
        value = [value]
    result = []
    for ring in value:
        points = np.asarray(ring, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
            raise ValueError("ownership component needs at least three finite X/Z points")
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError("ownership component must be simple and have positive area")
        result.append(points.tolist())
    shape = unary_union([Polygon(r) for r in result])
    if abs(shape.area - sum(Polygon(r).area for r in result)) > 1e-7:
        raise ValueError("ownership components overlap")
    return result


def geometry(value):
    return unary_union([Polygon(r) for r in rings(value)])


def points(value):
    return np.concatenate([np.asarray(r, float) for r in rings(value)])


def contains(x, z, value, *, boundary=False):
    """Vectorized crossing-number rule; optional explicit boundary inclusion for assignment ties."""
    x, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float))
    result = np.zeros(x.shape, bool)
    for ring in rings(value):
        p = np.asarray(ring, float)
        inside = np.zeros(x.shape, bool)
        edge = np.zeros(x.shape, bool)
        for (x1, z1), (x2, z2) in zip(p, np.roll(p, -1, axis=0)):
            inside ^= ((z1 > z) != (z2 > z)) & (x < (x2-x1)*(z-z1)/(z2-z1 if z2 != z1 else 1e-12)+x1)
            if boundary:
                cross = (x-x1)*(z2-z1)-(z-z1)*(x2-x1)
                edge |= (np.abs(cross) < 1e-8) & (x >= min(x1,x2)-1e-9) & (x <= max(x1,x2)+1e-9) & (z >= min(z1,z2)-1e-9) & (z <= max(z1,z2)+1e-9)
        result |= inside | edge
    return result
