"""Deterministic city layout for Four Gates.

Derived from the canonical aerial: a circular walled island with four cardinal
gates, three concentric ring roads, four ceremonial avenues plus four diagonal
streets, and concentric districts wrapping a central plaza.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

TAU = math.pi * 2.0

PLAZA_RADIUS = 70.0
RING_ROADS = (160.0, 252.0, 336.0)
BANDS = {
    "civic": (110.0, 152.0),
    "residential": (172.0, 238.0),
    "outer": (264.0, 322.0),
}
CARDINALS = (0.0, math.pi * 0.5, math.pi, math.pi * 1.5)   # +X, +Z, -X, -Z
DIAGONALS = tuple(math.pi * 0.25 + math.pi * 0.5 * i for i in range(4))
AVENUE_HALF = 15.0      # ceremonial avenue half width
STREET_HALF = 8.0       # diagonal street half width
RING_HALF = 7.5


def angle_gap(a: float, b: float) -> float:
    d = abs((a - b + math.pi) % TAU - math.pi)
    return d


def clear_of_roads(radius: float, angle: float, margin: float = 6.0) -> bool:
    """True when a footprint centre is far enough from every carriageway."""
    for card in CARDINALS:
        if angle_gap(angle, card) * radius < AVENUE_HALF + margin:
            return False
    for diag in DIAGONALS:
        if angle_gap(angle, diag) * radius < STREET_HALF + margin:
            return False
    for ring in RING_ROADS:
        if abs(radius - ring) < RING_HALF + margin:
            return False
    return True


def quadrant(angle: float) -> str:
    """Districts follow the recorded gameplay regions."""
    a = angle % TAU
    if a < math.pi * 0.25 or a >= math.pi * 1.75:
        return "residential"          # east
    if a < math.pi * 0.75:
        return "agricultural"         # south
    if a < math.pi * 1.25:
        return "civic"                # west
    return "service"                  # north


@dataclass
class Placement:
    name: str
    kind: str
    x: float
    z: float
    yaw: float
    radius: float
    angle: float
    variant: int
    width: float
    depth: float


def _footprint_free(placements: Sequence[Placement], x: float, z: float,
                    clearance: float) -> bool:
    for other in placements:
        span = clearance + max(other.width, other.depth) * 0.5
        if (x - other.x) ** 2 + (z - other.z) ** 2 < span * span:
            return False
    return True


def generate_buildings(seed: int = 4041) -> List[Placement]:
    """Lay out the district architecture ring by ring."""
    rng = np.random.default_rng(seed)
    placements: List[Placement] = []

    plans = [
        # band            rows   angular step   kinds by district
        ("civic", 3, 12.0),
        ("residential", 5, 7.5),
        ("outer", 4, 8.5),
    ]
    for band, rows, step_deg in plans:
        r0, r1 = BANDS[band]
        for row in range(rows):
            radius = r0 + (r1 - r0) * (row + 0.5) / rows
            count = max(8, int(round(TAU * radius / (radius * math.radians(step_deg)))))
            count = int(round(360.0 / step_deg))
            for i in range(count):
                angle = TAU * i / count + (row % 2) * (TAU / count) * 0.5
                angle += float(rng.uniform(-0.012, 0.012))
                rr = radius + float(rng.uniform(-6.0, 6.0))
                if not clear_of_roads(rr, angle):
                    continue
                district = quadrant(angle)
                kind, width, depth = _pick_kind(band, district, rng)
                x = math.cos(angle) * rr
                z = math.sin(angle) * rr
                if not _footprint_free(placements, x, z, max(width, depth) * 0.5 + 1.2):
                    continue
                # buildings address the ring road: front faces outward
                yaw = -angle + math.pi * 0.5
                placements.append(Placement(
                    name=f"{kind}_{band}_{row}_{i:02d}", kind=kind, x=x, z=z,
                    yaw=yaw, radius=rr, angle=angle,
                    variant=int(rng.integers(0, 8)), width=width, depth=depth))
    return placements


def _pick_kind(band: str, district: str, rng) -> Tuple[str, float, float]:
    roll = float(rng.random())
    if band == "civic":
        if district == "civic":
            return ("civic_hall", 26.0, 18.0) if roll < 0.55 else ("townhouse_large", 12.0, 14.0)
        if district == "residential":
            return ("townhouse_large", 12.0, 14.0)
        if district == "agricultural":
            return ("market_hall", 20.0, 13.0) if roll < 0.4 else ("townhouse_large", 12.0, 14.0)
        return ("civic_hall", 26.0, 18.0) if roll < 0.3 else ("townhouse_large", 12.0, 14.0)
    if band == "residential":
        if district == "civic":
            return ("market_hall", 20.0, 13.0) if roll < 0.3 else ("townhouse", 9.5, 11.0)
        if district == "agricultural":
            return ("townhouse", 9.5, 11.0) if roll < 0.6 else ("warehouse", 16.0, 10.0)
        return ("townhouse", 9.5, 11.0)
    # outer band
    if district == "agricultural":
        if roll < 0.45:
            return ("farmhouse", 11.0, 8.0)
        if roll < 0.7:
            return ("granary", 7.2, 7.2)
        return ("townhouse_small", 8.0, 9.0)
    if district == "service":
        return ("warehouse", 16.0, 10.0) if roll < 0.5 else ("townhouse_small", 8.0, 9.0)
    return ("townhouse_small", 8.0, 9.0)


def ring_road_points(radius: float, segments: int = 128) -> List[Tuple[float, float]]:
    return [(math.cos(TAU * i / segments) * radius, math.sin(TAU * i / segments) * radius)
            for i in range(segments + 1)]


def avenue_lamp_positions() -> List[Tuple[float, float, float]]:
    """Lamp posts down each ceremonial avenue and around each ring road."""
    out = []
    for card in CARDINALS:
        for radius in np.arange(PLAZA_RADIUS + 14.0, 344.0, 26.0):
            for side in (-1, 1):
                offset = AVENUE_HALF + 3.2
                x = math.cos(card) * radius - math.sin(card) * offset * side
                z = math.sin(card) * radius + math.cos(card) * offset * side
                out.append((x, z, card))
    for ring in RING_ROADS:
        count = int(TAU * ring / 34.0)
        for i in range(count):
            a = TAU * i / count + 0.05
            out.append((math.cos(a) * (ring + RING_HALF + 2.6),
                        math.sin(a) * (ring + RING_HALF + 2.6), a))
    return out


def tree_positions(seed: int = 991) -> List[Tuple[float, float, float, str]]:
    """Street trees, garden groves and the outer evergreen belt."""
    rng = np.random.default_rng(seed)
    out = []
    # formal avenue planting
    for card in CARDINALS:
        for radius in np.arange(PLAZA_RADIUS + 26.0, 330.0, 34.0):
            for side in (-1, 1):
                offset = AVENUE_HALF + 8.5
                x = math.cos(card) * radius - math.sin(card) * offset * side
                z = math.sin(card) * radius + math.cos(card) * offset * side
                out.append((x, z, float(rng.uniform(8.0, 11.0)), "broadleaf"))
    # garden groves in the gaps between blocks
    for _ in range(240):
        radius = float(rng.uniform(PLAZA_RADIUS + 8.0, 330.0))
        angle = float(rng.uniform(0.0, TAU))
        if not clear_of_roads(radius, angle, margin=2.0):
            continue
        out.append((math.cos(angle) * radius, math.sin(angle) * radius,
                    float(rng.uniform(6.5, 10.5)), "broadleaf"))
    # evergreen belt on the outer rim and the northern massif
    for _ in range(620):
        radius = float(rng.uniform(600.0, 790.0))
        angle = float(rng.uniform(0.0, TAU))
        if min(angle_gap(angle, c) for c in CARDINALS) * radius < 40.0:
            continue
        out.append((math.cos(angle) * radius, math.sin(angle) * radius,
                    float(rng.uniform(11.0, 18.0)), "pine"))
    for _ in range(160):
        radius = float(rng.uniform(376.0, 424.0))
        angle = float(rng.uniform(0.0, TAU))
        if min(angle_gap(angle, c) for c in CARDINALS) * radius < 46.0:
            continue
        out.append((math.cos(angle) * radius, math.sin(angle) * radius,
                    float(rng.uniform(7.0, 12.0)), "pine"))
    return out


def farm_plots(seed: int = 77) -> List[Tuple[float, float, float, float, float]]:
    """Cropped field strips in the southern agricultural quarter."""
    rng = np.random.default_rng(seed)
    plots = []
    # A plot is a flat crop plane laid on flat ground, so two of them that
    # overlap are coplanar and fight. The first size runs radially and the
    # second along the ring, so each is a fraction of that plot's own cell in
    # the ring-and-row grid and a headland is left between neighbours.
    ring_step = 18.0
    for i in range(26):
        angle = math.pi * 0.30 + (math.pi * 0.40) * (i % 13) / 12.0
        radius = 272.0 + ring_step * (i // 13)
        if not clear_of_roads(radius, angle, margin=10.0):
            continue
        arc = radius * (math.pi * 0.40) / 12.0
        plots.append((math.cos(angle) * radius, math.sin(angle) * radius,
                      float(rng.uniform(0.62, 0.82)) * ring_step,
                      float(rng.uniform(0.66, 0.86)) * arc,
                      -angle))
    # outer-rim smallholdings beyond the south causeway
    for i in range(14):
        angle = math.pi * 0.5 + float(rng.uniform(-0.55, 0.55))
        radius = float(rng.uniform(640.0, 720.0))
        plots.append((math.cos(angle) * radius, math.sin(angle) * radius,
                      float(rng.uniform(26.0, 44.0)), float(rng.uniform(18.0, 28.0)),
                      -angle))
    return plots
