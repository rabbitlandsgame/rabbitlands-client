"""Mirrorhold lake-link geometry with clear Drowned Crown entrances."""
from __future__ import annotations

import numpy as np

from amberwood import routecraft as RC


RING_JOIN_RADIUS = 20.8
COMPACT_Z_OUTER_SCALE = 170.0 / 362.0
_TRIM_DIRECTIONS = {"City": -1.0, "Sanctuary": 1.0}


def graded_ring_link(name, stations, centre, *, ring_z=60.0, width=6.5,
                     foot=-12.0, stone="rubble_stone",
                     paving="cobble_paving", parapet=0.8):
    """Build a baseline link, trimming only its inner parapet ribbons.

    The complete walking skin, slab and piers retain the authored stations.
    City and Sanctuary parapets begin at the emitted 20.8 m ring join so they
    cannot divide the annular promenade. The shared causeway implementation
    remains the authority for both the baseline geometry and trimmed ribbons.
    """
    points = np.asarray(stations, dtype=np.float64)
    centre = np.asarray(centre, dtype=np.float64)
    local = points - centre
    kwargs = dict(width=width, foot=foot, stone=stone,
                  paving=paving, parapet=parapet)
    group = RC.graded_causeway(local, **kwargs)
    direction = _TRIM_DIRECTIONS.get(name)
    if direction is None:
        return group

    target_z = float(ring_z + direction * RING_JOIN_RADIUS /
                     COMPACT_Z_OUTER_SCALE)
    first, second = points[0], points[1]
    denominator = float(second[2] - first[2])
    if abs(denominator) < 1e-12:
        raise ValueError(f"{name} inner run cannot reach the ring join")
    fraction = (target_z - float(first[2])) / denominator
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"{name} ring join is outside its first run")
    split = first + (second - first) * fraction
    # Keep the complete suffix so the original second-station mitre continues
    # to account for the following run (Sanctuary bends after that station).
    trimmed = RC.graded_causeway(
        np.vstack([split, points[1:]]) - centre, **kwargs)

    # A straight one-run causeway has three slab faces, six parapet faces,
    # then its piers. Assert that contract before replacing only the ribbons.
    parapets = trimmed.parts[3:9]
    if len(parapets) != 6 or any(part.triangle_count != 2 for part in parapets):
        raise RuntimeError("graded_causeway parapet layout changed")
    original = group.parts[3:9]
    if len(original) != 6 or any(part.triangle_count != 2 for part in original):
        raise RuntimeError("graded_causeway parapet layout changed")
    group.parts[3:9] = parapets
    return group
