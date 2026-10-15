"""Modular Sunmane Steppe asset kit.

Each builder returns a dict of `material key -> Geometry` in local space, with
the origin on the ground plane and +Y up. The world builder turns each kit
entry into one glTF mesh and then instances it with per-placement transforms,
so authored variation comes from parameters and orientation rather than from
duplicating geometry.

Shape language follows the concept board: layered scalloped white canvas over
dark weathered timber, red and ochre textile, hammered metal fittings, carved
bone ornament and pale eroded stone.
"""
from __future__ import annotations

import math

import numpy as np

from glb import Geometry
from shapes import (UV_SCALE, add_quad, beam, box, conical_canopy, frustum,
                    oriented_quad, oriented_triangle, polygon_points, prism,
                    revolve, ribbon, sheet, sphere, wall_run)

TAU = math.pi * 2.0

# Material keys used across the kit. The builder maps these onto glTF materials.
CANVAS_PALE = "canvas_pale"
CANVAS_RED = "canvas_red"
CANVAS_OCHRE = "canvas_ochre"
TIMBER_DARK = "timber_dark"
TIMBER_WARM = "timber_warm"
STONE_PALE = "stone_pale"
STONE_DARK = "stone_dark"
# Cave rock is its own pair: the surface map's "dark" stone is the red
# sandstone of the mesas, which underground reads as raw salmon.
CAVE_ROCK_PALE = "cave_rock_pale"
CAVE_ROCK_WARM = "cave_rock_warm"
THATCH = "thatch_gold"
LEATHER = "leather"
TEXTILE = "textile"
METAL = "metal"
GOLD = "metal_gold"
BONE = "bone"


class Parts(dict):
    """A `material key -> Geometry` bundle with a convenience accessor."""

    def geometry(self, key: str) -> Geometry:
        found = self.get(key)
        if found is None:
            found = Geometry()
            self[key] = found
        return found

    @property
    def triangles(self) -> int:
        return sum(geometry.triangle_count for geometry in self.values())


def _uv(name: str) -> float:
    return UV_SCALE[name.split("_")[0]] if name.split("_")[0] in UV_SCALE else 1.0


# --------------------------------------------------------------------- details
def finial(parts: Parts, center, height: float, scale: float = 1.0) -> None:
    """Gold roof finial: a turned spike over a flared collar and a ring."""
    x, z = center
    gold = parts.geometry(GOLD)
    revolve(gold, [(0.0, 0.0), (0.16 * scale, 0.06 * scale),
                   (0.22 * scale, 0.16 * scale), (0.13 * scale, 0.26 * scale),
                   (0.20 * scale, 0.34 * scale), (0.09 * scale, 0.52 * scale),
                   (0.05 * scale, 0.78 * scale), (0.0, 1.05 * scale)],
            (x, height, z), sides=12, uv_scale=UV_SCALE["metal"],
            close_bottom=True, close_top=False)


def guy_ropes(parts: Parts, center, radius: float, anchor: float, top: float,
              count: int = 8, rotation: float = 0.0) -> None:
    """Tensioned ropes from the eave to ground stakes, with the stakes modelled."""
    x, z = center
    rope = parts.geometry(LEATHER)
    timber = parts.geometry(TIMBER_DARK)
    for index in range(count):
        angle = rotation + TAU * index / count
        direction = (math.cos(angle), math.sin(angle))
        eave = (x + direction[0] * radius, top, z + direction[1] * radius)
        stake = (x + direction[0] * anchor, 0.0, z + direction[1] * anchor)
        beam(rope, eave, (stake[0], 0.34, stake[2]), 0.035,
             uv_scale=UV_SCALE["leather"])
        beam(timber, (stake[0], -0.15, stake[2]), (stake[0], 0.42, stake[2]), 0.09,
             uv_scale=UV_SCALE["timber"])


def pennant_line(parts: Parts, start, end, count: int = 7, drop: float = 0.9,
                 length: float = 1.5) -> None:
    """A slack line of hanging pennants between two points."""
    cloth = parts.geometry(TEXTILE)
    rope = parts.geometry(LEATHER)
    start = np.asarray(start, dtype="float64")
    end = np.asarray(end, dtype="float64")
    def line_point(t: float) -> np.ndarray:
        point = start + (end - start) * t
        point[1] -= drop * math.sin(math.pi * t)      # catenary sag
        return point
    steps = 12
    for index in range(steps):
        beam(rope, line_point(index / steps), line_point((index + 1) / steps), 0.03,
             uv_scale=UV_SCALE["leather"])
    for index in range(count):
        t = (index + 0.5) / count
        anchor = line_point(t)
        width = 0.34 + 0.10 * ((index % 3) - 1)
        tip = anchor + np.array([0.0, -length - 0.25 * (index % 2), 0.0])
        corners = [anchor + np.array([-width * 0.5, 0.0, 0.0]),
                   anchor + np.array([width * 0.5, 0.0, 0.0]),
                   tip + np.array([width * 0.30, 0.0, 0.0]),
                   tip + np.array([-width * 0.30, 0.0, 0.0])]
        sheet(cloth, corners, uv_rect=(0.0, index / count, 1.0, (index + 1) / count))


def banner(parts: Parts, top, width: float, height: float, *, facing: float = 0.0,
           material: str = TEXTILE) -> None:
    """A vertical hanging banner with a timber head bar."""
    cloth = parts.geometry(material)
    timber = parts.geometry(TIMBER_DARK)
    x, y, z = top
    direction = (math.cos(facing), math.sin(facing))
    half = width * 0.5
    left = (x - direction[0] * half, y, z - direction[1] * half)
    right = (x + direction[0] * half, y, z + direction[1] * half)
    beam(timber, (left[0] - direction[0] * 0.12, y, left[2] - direction[1] * 0.12),
         (right[0] + direction[0] * 0.12, y, right[2] + direction[1] * 0.12), 0.07,
         uv_scale=UV_SCALE["timber"])
    # A slight taper and a swallow-tail hem read as cloth rather than a card.
    corners = [left, right,
               (right[0], y - height, right[2]), (left[0], y - height, left[2])]
    sheet(cloth, corners, uv_rect=(0.0, 0.0, 1.0, 1.6))
    tail = [(left[0], y - height, left[2]), (right[0], y - height, right[2]),
            (x + direction[0] * half * 0.55, y - height - 0.55,
             z + direction[1] * half * 0.55),
            (x - direction[0] * half * 0.55, y - height - 0.55,
             z - direction[1] * half * 0.55)]
    sheet(cloth, tail, uv_rect=(0.0, 1.6, 1.0, 2.0))


# ----------------------------------------------------------------- round tents
def round_tent(radius: float = 3.4, wall: float = 2.05, peak: float = 4.55,
               *, door_angle: float = 0.0, variant: int = 0) -> Parts:
    """An Orun round tent: canvas cone on a lattice wall with a timber door.

    Matches detail-board panel 2 - stepped entry, dark timber frame, gold
    finial, guy ropes and a banded skirt.
    """
    parts = Parts()
    canvas = parts.geometry(CANVAS_PALE)
    accent = parts.geometry(CANVAS_RED if variant % 2 == 0 else CANVAS_OCHRE)
    timber = parts.geometry(TIMBER_DARK)
    sides = 18

    # Wall: a slightly battered drum, thick enough to read as felt over lattice.
    frustum(canvas, (0, 0.18, 0), (0, wall, 0), radius * 1.01, radius,
            sides=sides, uv_scale=UV_SCALE["canvas"], cap_start=False, cap_end=False)
    # Skirt band in the clan colour.
    frustum(accent, (0, 0.0, 0), (0, 0.46, 0), radius * 1.03, radius * 1.015,
            sides=sides, uv_scale=UV_SCALE["textile"], cap_start=True, cap_end=False)
    # Roof: a broad lower canopy carrying a smaller crown tier over the smoke
    # ring, which is the two-step silhouette the concept board repeats.
    shoulder = wall + (peak - wall) * 0.52
    conical_canopy(canvas, (0, 0, 0), radius, wall, shoulder + 0.18, sides=sides,
                   uv_scale=UV_SCALE["canvas"], sag=0.18, scallop=0.16,
                   overhang=0.30, eave_drop=0.14)
    conical_canopy(canvas, (0, 0, 0), radius * 0.52, shoulder, peak,
                   sides=max(8, sides // 2), uv_scale=UV_SCALE["canvas"],
                   sag=0.12, scallop=0.14, overhang=0.26, eave_drop=0.14)
    # Smoke ring between the tiers.
    frustum(timber, (0, shoulder - 0.10, 0), (0, shoulder + 0.14, 0),
            radius * 0.50, radius * 0.47, sides=max(8, sides // 2),
            uv_scale=UV_SCALE["timber"], cap_start=False, cap_end=False)
    # Radial roof ribs, visible as raised battens on the lower canopy.
    for index in range(sides // 2):
        angle = TAU * index / (sides // 2) + 0.12
        outer = (math.cos(angle) * (radius + 0.28), wall - 0.10,
                 math.sin(angle) * (radius + 0.28))
        beam(timber, outer, (math.cos(angle) * radius * 0.50, shoulder - 0.02,
                             math.sin(angle) * radius * 0.50), 0.085,
             uv_scale=UV_SCALE["timber"])
    # Horizontal tension bands around the felt wall.
    for level in (0.62, 1.28, wall - 0.16):
        for index in range(sides):
            a0, a1 = TAU * index / sides, TAU * (index + 1) / sides
            beam(parts.geometry(LEATHER),
                 (math.cos(a0) * (radius + 0.03), level, math.sin(a0) * (radius + 0.03)),
                 (math.cos(a1) * (radius + 0.03), level, math.sin(a1) * (radius + 0.03)),
                 0.055, 0.035, uv_scale=UV_SCALE["leather"])
    # Compression ring and finial.
    revolve(timber, [(0.34, peak - 0.22), (0.42, peak - 0.10), (0.36, peak + 0.06)],
            (0, 0, 0), sides=12, uv_scale=UV_SCALE["timber"], close_bottom=True,
            close_top=True)
    finial(parts, (0.0, 0.0), peak + 0.02, 0.9)

    # Doorway: framed opening with a lintel, threshold step and hide curtain.
    direction = (math.cos(door_angle), math.sin(door_angle))
    side = (-direction[1], direction[0])
    door_half, door_height = 0.62, 1.72
    outer_r = radius * 1.02
    for sign in (-1, 1):
        post = (direction[0] * outer_r + side[0] * sign * door_half, 0.0,
                direction[1] * outer_r + side[1] * sign * door_half)
        beam(timber, post, (post[0], door_height + 0.16, post[2]), 0.15,
             uv_scale=UV_SCALE["timber"])
    lintel_left = (direction[0] * outer_r + side[0] * -door_half, door_height,
                   direction[1] * outer_r + side[1] * -door_half)
    lintel_right = (direction[0] * outer_r + side[0] * door_half, door_height,
                    direction[1] * outer_r + side[1] * door_half)
    beam(timber, (lintel_left[0], door_height + 0.10, lintel_left[2]),
         (lintel_right[0], door_height + 0.10, lintel_right[2]), 0.18, 0.22,
         uv_scale=UV_SCALE["timber"])
    # Carved head board over the lintel.
    box(parts.geometry(TIMBER_WARM),
        (direction[0] * outer_r, door_height + 0.34, direction[1] * outer_r),
        (door_half * 2.1, 0.30, 0.14), uv_scale=UV_SCALE["timber"],
        rotation_y=-door_angle)
    # Entry steps and a small porch canopy on two posts.
    for step, (rise, reach, width_scale) in enumerate(
            ((0.09, 0.42, 2.4), (0.26, 0.86, 2.0))):
        box(parts.geometry(STONE_PALE),
            (direction[0] * (outer_r + reach), rise,
             direction[1] * (outer_r + reach)),
            (door_half * width_scale, 0.18, 0.62), uv_scale=UV_SCALE["stone"],
            rotation_y=-door_angle)
    for sign in (-1, 1):
        post = (direction[0] * (outer_r + 1.05) + side[0] * sign * (door_half + 0.16),
                direction[1] * (outer_r + 1.05) + side[1] * sign * (door_half + 0.16))
        beam(timber, (post[0], 0.0, post[1]), (post[0], 2.05, post[1]), 0.10,
             uv_scale=UV_SCALE["timber"])
    porch = [
        (direction[0] * outer_r + side[0] * -(door_half + 0.3), 2.32,
         direction[1] * outer_r + side[1] * -(door_half + 0.3)),
        (direction[0] * outer_r + side[0] * (door_half + 0.3), 2.32,
         direction[1] * outer_r + side[1] * (door_half + 0.3)),
        (direction[0] * (outer_r + 1.15) + side[0] * (door_half + 0.24), 2.02,
         direction[1] * (outer_r + 1.15) + side[1] * (door_half + 0.24)),
        (direction[0] * (outer_r + 1.15) + side[0] * -(door_half + 0.24), 2.02,
         direction[1] * (outer_r + 1.15) + side[1] * -(door_half + 0.24))]
    add_quad(canvas, porch, [[0, 0], [1.1, 0], [1.1, 0.9], [0, 0.9]])
    add_quad(canvas, [(c[0], c[1] - 0.05, c[2]) for c in porch][::-1],
             [[0, 0], [1.1, 0], [1.1, 0.9], [0, 0.9]])
    banner(parts, (direction[0] * (outer_r + 0.4), 2.26,
                   direction[1] * (outer_r + 0.4)), 0.55, 1.15,
           facing=door_angle + math.pi / 2)
    # Hide door curtain, rolled slightly aside.
    curtain = parts.geometry(LEATHER)
    inner = 0.06
    sheet(curtain, [
        (lintel_left[0] + direction[0] * inner, door_height, lintel_left[2] + direction[1] * inner),
        (lintel_right[0] + direction[0] * inner, door_height, lintel_right[2] + direction[1] * inner),
        (lintel_right[0] + direction[0] * inner, 0.12, lintel_right[2] + direction[1] * inner),
        (lintel_left[0] + direction[0] * inner, 0.12, lintel_left[2] + direction[1] * inner)],
        uv_rect=(0.0, 0.0, 1.4, 2.0))

    guy_ropes(parts, (0.0, 0.0), radius + 0.30, radius + 1.75, wall - 0.12,
              count=8, rotation=door_angle + TAU / 16.0)
    return parts


def great_hall(radius: float = 11.5) -> Parts:
    """The monumental white-canopied central hall.

    Three stacked scalloped canopies over a timber drum on a stone podium, with
    a flanking stair, corner standards and hanging banners - the silhouette the
    aerial overview and panels 3 and 5 are built around.
    """
    parts = Parts()
    canvas = parts.geometry(CANVAS_PALE)
    red = parts.geometry(CANVAS_RED)
    timber = parts.geometry(TIMBER_DARK)
    stone = parts.geometry(STONE_PALE)
    sides = 24

    # Stepped stone podium.
    for step, (r, y0, y1) in enumerate((
            (radius + 2.6, 0.0, 0.42), (radius + 1.9, 0.42, 0.84),
            (radius + 1.3, 0.84, 1.26))):
        prism(stone, polygon_points((0, 0, 0), r, sides), y0, y1,
              uv_scale=UV_SCALE["stone"], cap_top=True)

    # Timber drum with engaged posts.
    prism(timber, polygon_points((0, 0, 0), radius, sides), 1.26, 5.4,
          uv_scale=UV_SCALE["timber"], cap_top=False, smooth_walls=False)
    for index in range(sides // 2):
        angle = TAU * index / (sides // 2)
        position = (math.cos(angle) * (radius + 0.22), 0.0,
                    math.sin(angle) * (radius + 0.22))
        beam(timber, (position[0], 1.26, position[2]),
             (position[0], 5.9, position[2]), 0.34, uv_scale=UV_SCALE["timber"])

    # Three stacked canopies, each scalloped and sagging between ribs.
    tiers = ((radius + 1.5, 5.4, 8.4, 24), (radius * 0.72, 8.1, 10.7, 20),
             (radius * 0.42, 10.4, 12.9, 16))
    for tier, (tier_radius, wall_top, peak, tier_sides) in enumerate(tiers):
        target = canvas if tier != 1 else red
        conical_canopy(target, (0, 0, 0), tier_radius, wall_top, peak,
                       sides=tier_sides, uv_scale=UV_SCALE["canvas"],
                       sag=0.30, scallop=0.16, overhang=1.15, eave_drop=0.42)
        # Drum between tiers so the stack has real thickness.
        if tier < len(tiers) - 1:
            next_radius = tiers[tier + 1][0]
            lower = (wall_top - 0.42 + (peak - wall_top + 0.42)
                     * (1 - next_radius * 1.02 / (tier_radius + 1.15)) - 0.08)
            frustum(timber, (0, lower, 0), (0, tiers[tier + 1][1], 0),
                    next_radius * 1.02, next_radius, sides=tier_sides,
                    uv_scale=UV_SCALE["timber"], cap_start=False, cap_end=False)
        for index in range(tier_sides // 2):
            angle = TAU * index / (tier_sides // 2) + 0.1
            outer = (math.cos(angle) * (tier_radius + 0.85), wall_top - 0.22,
                     math.sin(angle) * (tier_radius + 0.85))
            beam(timber, outer, (0.0, peak - 0.3, 0.0), 0.11,
                 uv_scale=UV_SCALE["timber"])
    finial(parts, (0.0, 0.0), 12.85, 2.4)

    # South entrance: a broad stair through the podium, with flanking standards.
    stair_width = 5.4
    for step in range(4):
        box(stone, (0.0, 0.16 + step * 0.32, radius + 2.6 + 1.5 - step * 0.5),
            (stair_width, 0.32, 1.0), uv_scale=UV_SCALE["stone"])
    for sign in (-1, 1):
        post = (sign * (stair_width * 0.5 + 0.6), 0.0, radius + 3.5)
        beam(timber, (post[0], 0.0, post[2]), (post[0], 6.4, post[2]), 0.30,
             uv_scale=UV_SCALE["timber"])
        finial(parts, (post[0], post[2]), 6.4, 0.8)
        banner(parts, (post[0], 5.7, post[2] - 0.2), 1.15, 3.2, facing=0.0)
    # Doorway recess so the drum is not a blank wall.
    box(parts.geometry(TIMBER_WARM), (0.0, 3.1, radius - 0.1),
        (3.6, 3.5, 0.5), uv_scale=UV_SCALE["timber"])
    for sign in (-1, 1):
        banner(parts, (sign * 2.6, 5.1, radius + 0.25), 0.9, 2.6, facing=0.0)
    return parts


# --------------------------------------------------------------- market canopy
def market_canopy(length: float = 7.0, width: float = 4.2, variant: int = 0) -> Parts:
    """A market awning with counter, crates and hanging goods (panel 3)."""
    parts = Parts()
    cloth = parts.geometry([CANVAS_PALE, CANVAS_RED, CANVAS_OCHRE][variant % 3])
    timber = parts.geometry(TIMBER_DARK)
    half_l, half_w = length * 0.5, width * 0.5
    post_height = 2.65
    ridge = 3.5

    for sx in (-1, 1):
        for sz in (-1, 1):
            base = (sx * half_l, 0.0, sz * half_w)
            beam(timber, base, (base[0], post_height, base[2]), 0.16,
                 uv_scale=UV_SCALE["timber"])
    # Ridge beam and rafters.
    beam(timber, (-half_l, ridge, 0.0), (half_l, ridge, 0.0), 0.14, 0.20,
         uv_scale=UV_SCALE["timber"])
    rafters = 5
    for index in range(rafters):
        t = index / (rafters - 1)
        x = -half_l + length * t
        for sz in (-1, 1):
            beam(timber, (x, ridge, 0.0), (x, post_height, sz * half_w), 0.09,
                 uv_scale=UV_SCALE["timber"])
    # Canvas: two sagging slopes with a scalloped valance.
    segments = 8
    for sz in (-1, 1):
        for index in range(segments):
            x0 = -half_l + length * index / segments
            x1 = -half_l + length * (index + 1) / segments
            sag0 = 0.16 * math.sin(math.pi * (index / segments))
            sag1 = 0.16 * math.sin(math.pi * ((index + 1) / segments))
            corners = [(x0, ridge - sag0, 0.0), (x1, ridge - sag1, 0.0),
                       (x1, post_height - sag1, sz * half_w),
                       (x0, post_height - sag0, sz * half_w)]
            if sz < 0:
                corners = corners[::-1]
            add_quad(cloth, corners,
                     [[c[0] / UV_SCALE["canvas"], c[2] / UV_SCALE["canvas"]]
                      for c in corners])
            # Underside, so the awning is cloth with thickness.
            under = [(c[0], c[1] - 0.05, c[2]) for c in corners][::-1]
            add_quad(cloth, under,
                     [[c[0] / UV_SCALE["canvas"], c[2] / UV_SCALE["canvas"]]
                      for c in under])
        # Scalloped valance hem.
        hem = parts.geometry(TEXTILE)
        for index in range(segments):
            x0 = -half_l + length * index / segments
            x1 = -half_l + length * (index + 1) / segments
            dip = 0.34 if index % 2 == 0 else 0.20
            sheet(hem, [(x0, post_height, sz * half_w), (x1, post_height, sz * half_w),
                        (x1, post_height - dip, sz * half_w),
                        (x0, post_height - dip, sz * half_w)],
                  uv_rect=(0.0, 0.0, 1.0, 0.5))

    # Counter, crates and sacks.
    box(timber, (0.0, 0.95, half_w - 0.5), (length - 1.0, 0.12, 0.8),
        uv_scale=UV_SCALE["timber"])
    for sx in (-1, 1):
        beam(timber, (sx * (half_l - 0.9), 0.0, half_w - 0.5),
             (sx * (half_l - 0.9), 0.95, half_w - 0.5), 0.12,
             uv_scale=UV_SCALE["timber"])
    crate = parts.geometry(TIMBER_WARM)
    for index, (cx, cz, size, spin) in enumerate((
            (-half_l + 1.0, -half_w + 0.9, 0.62, 0.3),
            (-half_l + 1.7, -half_w + 1.2, 0.48, -0.5),
            (half_l - 1.2, -half_w + 1.0, 0.55, 0.9))):
        box(crate, (cx, size * 0.5, cz), (size, size, size * 0.8),
            uv_scale=UV_SCALE["timber"], rotation_y=spin)
        if index == 0:
            box(crate, (cx, size * 1.5, cz), (size * 0.85, size * 0.9, size * 0.7),
                uv_scale=UV_SCALE["timber"], rotation_y=spin + 0.4)
    for index, (px, pz) in enumerate(((half_l - 1.9, -half_w + 1.4),
                                      (half_l - 2.5, -half_w + 0.9))):
        pot(parts, (px, pz), 0.34 + 0.06 * index)
    pennant_line(parts, (-half_l, ridge - 0.1, 0.0), (half_l, ridge - 0.1, 0.0),
                 count=5, drop=0.35, length=0.85)
    return parts


# ------------------------------------------------------------------ small props
def pot(parts: Parts, center, radius: float = 0.34, *, tall: bool = False) -> None:
    """A thrown storage jar."""
    x, z = center
    clay = parts.geometry(STONE_DARK)
    height = radius * (4.2 if tall else 2.7)
    revolve(clay, [(radius * 0.45, 0.0), (radius * 0.95, height * 0.22),
                   (radius, height * 0.45), (radius * 0.72, height * 0.78),
                   (radius * 0.46, height * 0.92), (radius * 0.55, height)],
            (x, 0.0, z), sides=12, uv_scale=UV_SCALE["stone"], close_bottom=True)


def barrel(parts: Parts, center, radius: float = 0.36, height: float = 0.86,
           rotation: float = 0.0) -> None:
    x, z = center
    timber = parts.geometry(TIMBER_WARM)
    hoop = parts.geometry(METAL)
    revolve(timber, [(radius * 0.86, 0.0), (radius, height * 0.3),
                     (radius, height * 0.7), (radius * 0.86, height)],
            (x, 0.0, z), sides=12, uv_scale=UV_SCALE["timber"],
            close_bottom=True, close_top=True)
    for level in (0.18, height - 0.18):
        revolve(hoop, [(radius * 0.99, level - 0.045), (radius * 1.03, level),
                       (radius * 0.99, level + 0.045)],
                (x, 0.0, z), sides=12, uv_scale=UV_SCALE["metal"])


def hay_bale(parts: Parts, center, radius: float = 0.62, width: float = 1.3,
             rotation: float = 0.0) -> None:
    x, z = center
    straw = parts.geometry(THATCH)
    axis = (math.cos(rotation), math.sin(rotation))
    start = (x - axis[0] * width * 0.5, radius, z - axis[1] * width * 0.5)
    end = (x + axis[0] * width * 0.5, radius, z + axis[1] * width * 0.5)
    frustum(straw, start, end, radius, radius, sides=12,
            uv_scale=UV_SCALE["thatch"])
    rope = parts.geometry(LEATHER)
    for offset in (-0.3, 0.3):
        centre = (x + axis[0] * width * offset, radius, z + axis[1] * width * offset)
        revolve(rope, [(radius * 1.02, -0.03), (radius * 1.05, 0.0),
                       (radius * 1.02, 0.03)], (centre[0], centre[1], centre[2]),
                sides=10, uv_scale=UV_SCALE["leather"])


def fire_pit(parts: Parts, center, radius: float = 0.85) -> None:
    x, z = center
    stone = parts.geometry(STONE_PALE)
    ember = parts.geometry(TIMBER_DARK)
    for index in range(9):
        angle = TAU * index / 9
        position = (x + math.cos(angle) * radius, 0.0, z + math.sin(angle) * radius)
        sphere(stone, (position[0], 0.11, position[2]), 0.20 + 0.05 * (index % 3),
               rings=5, sides=7, uv_scale=UV_SCALE["stone"], squash=0.7)
    for index in range(5):
        angle = TAU * index / 5 + 0.3
        beam(ember, (x + math.cos(angle) * radius * 0.55, 0.05,
                     z + math.sin(angle) * radius * 0.55),
             (x - math.cos(angle) * radius * 0.2, 0.42,
              z - math.sin(angle) * radius * 0.2), 0.075,
             uv_scale=UV_SCALE["timber"])
    # Tripod and cook pot.
    for index in range(3):
        angle = TAU * index / 3
        beam(ember, (x + math.cos(angle) * radius * 1.1, 0.0,
                     z + math.sin(angle) * radius * 1.1),
             (x, 1.55, z), 0.06, uv_scale=UV_SCALE["timber"])
    revolve(parts.geometry(METAL),
            [(0.0, 0.72), (0.26, 0.78), (0.30, 0.98), (0.24, 1.12), (0.26, 1.16)],
            (x, 0.0, z), sides=10, uv_scale=UV_SCALE["metal"], close_bottom=True)


def hitching_post(parts: Parts, center, length: float = 3.2,
                  rotation: float = 0.0) -> None:
    x, z = center
    timber = parts.geometry(TIMBER_DARK)
    axis = (math.cos(rotation), math.sin(rotation))
    for sign in (-1, 1):
        post = (x + axis[0] * length * 0.5 * sign, z + axis[1] * length * 0.5 * sign)
        beam(timber, (post[0], -0.2, post[1]), (post[0], 1.24, post[1]), 0.14,
             uv_scale=UV_SCALE["timber"])
    beam(timber, (x - axis[0] * length * 0.55, 1.08, z - axis[1] * length * 0.55),
         (x + axis[0] * length * 0.55, 1.08, z + axis[1] * length * 0.55), 0.11,
         uv_scale=UV_SCALE["timber"])
    tack = parts.geometry(LEATHER)
    for offset in (-0.25, 0.3):
        anchor = (x + axis[0] * length * offset, 1.05, z + axis[1] * length * offset)
        beam(tack, anchor, (anchor[0] + 0.06, 0.42, anchor[2] + 0.05), 0.035,
             uv_scale=UV_SCALE["leather"])


def cart(parts: Parts, rotation: float = 0.0, loaded: bool = True) -> Parts:
    """A two-wheeled steppe cart with spoked wheels and a load."""
    parts = parts if parts is not None else Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    metal_parts = parts.geometry(METAL)
    body_y = 0.86
    box(warm, (0.0, body_y, 0.0), (2.5, 0.16, 1.35), uv_scale=UV_SCALE["timber"])
    for sz in (-1, 1):
        box(warm, (0.0, body_y + 0.28, sz * 0.62), (2.5, 0.46, 0.11),
            uv_scale=UV_SCALE["timber"])
    for sx in (-1, 1):
        box(warm, (sx * 1.2, body_y + 0.28, 0.0), (0.11, 0.46, 1.35),
            uv_scale=UV_SCALE["timber"])
    # Wheels with spokes and iron tyres.
    for sz in (-1, 1):
        centre = (0.0, 0.62, sz * 0.82)
        frustum(timber, (centre[0], centre[1], centre[2] - 0.06),
                (centre[0], centre[1], centre[2] + 0.06), 0.16, 0.16, sides=10,
                uv_scale=UV_SCALE["timber"])
        for index in range(8):
            angle = TAU * index / 8
            rim = (centre[0] + math.cos(angle) * 0.56, centre[1] + math.sin(angle) * 0.56,
                   centre[2])
            beam(timber, centre, rim, 0.055, uv_scale=UV_SCALE["timber"])
        for index in range(16):
            a0 = TAU * index / 16
            a1 = TAU * (index + 1) / 16
            beam(metal_parts,
                 (centre[0] + math.cos(a0) * 0.60, centre[1] + math.sin(a0) * 0.60,
                  centre[2]),
                 (centre[0] + math.cos(a1) * 0.60, centre[1] + math.sin(a1) * 0.60,
                  centre[2]), 0.10, 0.13, uv_scale=UV_SCALE["metal"])
    # Shafts.
    for sz in (-1, 1):
        beam(timber, (1.2, body_y - 0.04, sz * 0.5), (2.9, 0.92, sz * 0.42), 0.09,
             uv_scale=UV_SCALE["timber"])
    if loaded:
        for index, (cx, cz, size) in enumerate(((-0.55, 0.0, 0.66), (0.35, -0.25, 0.54),
                                                (0.4, 0.3, 0.48))):
            box(warm, (cx, body_y + 0.08 + size * 0.5, cz), (size, size, size * 0.9),
                uv_scale=UV_SCALE["timber"], rotation_y=0.3 * index)
        sheet(parts.geometry(TEXTILE),
              [(-1.15, body_y + 0.95, -0.6), (0.9, body_y + 1.0, -0.6),
               (0.9, body_y + 0.92, 0.6), (-1.15, body_y + 0.88, 0.6)],
              uv_rect=(0.0, 0.0, 2.0, 1.2))
    return parts


# ------------------------------------------------------------------ structures
def gate_tower(height: float = 7.6, width: float = 2.6) -> Parts:
    """One ornamental gate tower: timber shaft, gallery, gold-tipped pagoda cap."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    canvas = parts.geometry(CANVAS_PALE)

    half = width * 0.5
    for sx in (-1, 1):
        for sz in (-1, 1):
            base = (sx * half, 0.0, sz * half)
            beam(timber, (base[0], -0.4, base[2]), (base[0], height, base[2]), 0.30,
                 uv_scale=UV_SCALE["timber"])
    # Cross bracing between the legs.
    for level in (1.6, 3.9):
        for sx, sz, ex, ez in ((-1, -1, 1, -1), (1, -1, 1, 1),
                               (1, 1, -1, 1), (-1, 1, -1, -1)):
            beam(timber, (sx * half, level, sz * half), (ex * half, level, ez * half),
                 0.14, uv_scale=UV_SCALE["timber"])
            beam(timber, (sx * half, level, sz * half),
                 (ex * half, level + 1.15, ez * half), 0.09,
                 uv_scale=UV_SCALE["timber"])
    # Boarded infill on the shaft, so the tower reads as a solid structure
    # rather than an open frame seen straight through.
    for face in range(4):
        angle = TAU * face / 4
        normal = (math.cos(angle), math.sin(angle))
        centre = (normal[0] * half, 0.0, normal[1] * half)
        box(warm, (centre[0], height * 0.5 - 0.4, centre[2]),
            (width if face % 2 else 0.20, height - 1.6, 0.20 if face % 2 else width),
            uv_scale=UV_SCALE["timber"])
    # Arrow slits break the boarding up.
    for face in (0, 2):
        angle = TAU * face / 4
        normal = (math.cos(angle), math.sin(angle))
        for level in (2.6, 4.6):
            box(timber, (normal[0] * (half + 0.02), level, normal[1] * (half + 0.02)),
                (0.22 if face % 2 else 0.30, 0.85, 0.30 if face % 2 else 0.22),
                uv_scale=UV_SCALE["timber"])
    # Enclosed gallery.
    box(warm, (0.0, height - 1.55, 0.0), (width + 0.9, 1.5, width + 0.9),
        uv_scale=UV_SCALE["timber"])
    box(warm, (0.0, height - 2.42, 0.0), (width + 1.5, 0.24, width + 1.5),
        uv_scale=UV_SCALE["timber"])
    # Two-tier pagoda cap in canvas over timber, gold finial.
    for tier, (radius, low, high, sides) in enumerate((
            (width * 1.15, height - 0.8, height + 1.15, 8),
            (width * 0.72, height + 0.85, height + 2.55, 8))):
        conical_canopy(canvas, (0, 0, 0), radius, low, high, sides=sides,
                       uv_scale=UV_SCALE["canvas"], sag=0.10, scallop=0.13,
                       overhang=0.55, eave_drop=0.28)
    finial(parts, (0.0, 0.0), height + 2.5, 1.3)
    for sx in (-1, 1):
        banner(parts, (sx * (half + 0.55), height - 2.6, 0.0), 0.8, 2.4,
               facing=math.pi / 2)
    return parts


def palisade_gate(opening: float = 5.2, wall_height: float = 4.4) -> Parts:
    """A gate bay: twin towers, lintel, hung banners and braced leaves (panel 5)."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    half = opening * 0.5

    tower = gate_tower(7.6, 2.6)
    for sign in (-1, 1):
        offset = np.array([sign * (half + 1.5), 0.0, 0.0])
        for key, geometry in tower.items():
            parts.geometry(key).extend(geometry, compose_translation(offset))
    # Lintel beam spanning the opening, with a carved head board.
    beam(timber, (-half - 1.2, wall_height + 0.5, 0.0),
         (half + 1.2, wall_height + 0.5, 0.0), 0.44, 0.60,
         uv_scale=UV_SCALE["timber"])
    box(warm, (0.0, wall_height + 1.12, 0.0), (opening + 1.4, 0.52, 0.34),
        uv_scale=UV_SCALE["timber"])
    for index in range(5):
        x = -half + opening * index / 4.0
        beam(warm, (x, wall_height + 0.82, 0.0), (x, wall_height + 1.42, 0.0), 0.13,
             uv_scale=UV_SCALE["timber"])
    # Gate leaves, standing open against the jambs.
    for sign in (-1, 1):
        hinge = sign * half
        leaf_angle = sign * 0.85
        for plank in range(5):
            t = (plank + 0.5) / 5
            depth = t * 2.1
            x = hinge + sign * math.cos(leaf_angle) * depth * 0.2
            z = -math.sin(abs(leaf_angle)) * depth
            beam(warm, (x, 0.05, z), (x, wall_height - 0.35, z), 0.22, 0.16,
                 uv_scale=UV_SCALE["timber"])
        for level in (1.1, wall_height - 0.9):
            beam(parts.geometry(METAL),
                 (hinge, level, -0.05), (hinge + sign * 0.42, level, -1.95), 0.14, 0.09,
                 uv_scale=UV_SCALE["metal"])
    pennant_line(parts, (-half - 1.0, wall_height + 0.3, 0.35),
                 (half + 1.0, wall_height + 0.3, 0.35), count=7, drop=0.55,
                 length=1.25)
    return parts


def compose_translation(offset) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, 3] = np.asarray(offset, dtype="float64")
    return matrix


def watchtower(height: float = 9.0) -> Parts:
    """A remote timber lookout on a splayed frame with a banner and a canopy."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    canvas = parts.geometry(CANVAS_OCHRE)
    spread, top_half = 2.3, 1.05
    legs = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            base = (sx * spread, -0.4, sz * spread)
            top = (sx * top_half, height, sz * top_half)
            beam(timber, base, top, 0.26, uv_scale=UV_SCALE["timber"])
            legs.append((base, top))
    for level in (0.35, 0.62, 0.86):
        y = height * level
        ring = []
        for base, top in legs:
            point = np.array(base) + (np.array(top) - np.array(base)) * level
            ring.append(point)
        for index in range(4):
            beam(timber, ring[index], ring[(index + 1) % 4], 0.12,
                 uv_scale=UV_SCALE["timber"])
        if level < 0.86:
            for index in range(4):
                following = (index + 1) % 4
                target = np.array(legs[following][0]) + (
                    np.array(legs[following][1]) - np.array(legs[following][0])) * (
                        level + 0.24)
                beam(timber, ring[index], target, 0.08, uv_scale=UV_SCALE["timber"])
    # Platform, rail and canopy.
    box(warm, (0.0, height + 0.1, 0.0), (3.3, 0.22, 3.3), uv_scale=UV_SCALE["timber"])
    for sx, sz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        box(warm, (sx * 1.55, height + 0.62, sz * 1.55),
            (0.16 if sx else 3.3, 0.85, 3.3 if sx else 0.16),
            uv_scale=UV_SCALE["timber"])
    for sx in (-1, 1):
        for sz in (-1, 1):
            beam(timber, (sx * 1.5, height + 0.2, sz * 1.5),
                 (sx * 1.5, height + 2.5, sz * 1.5), 0.13,
                 uv_scale=UV_SCALE["timber"])
    conical_canopy(canvas, (0, 0, 0), 2.5, height + 2.4, height + 3.6, sides=8,
                   uv_scale=UV_SCALE["canvas"], sag=0.08, scallop=0.14,
                   overhang=0.5, eave_drop=0.2)
    finial(parts, (0.0, 0.0), height + 3.55, 0.8)
    banner(parts, (1.7, height + 2.2, 1.7), 0.85, 2.6, facing=0.8)
    # Ladder up one face.
    for rung in range(int(height / 0.55)):
        y = 0.4 + rung * 0.55
        t = y / height
        x = spread + (top_half - spread) * t
        beam(warm, (x + 0.1, y, -0.42), (x + 0.1, y, 0.42), 0.055,
             uv_scale=UV_SCALE["timber"])
    return parts


def windmill(height: float = 8.4) -> Parts:
    """A timber tower mill with four sails, gallery and cap (panel 6)."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    canvas = parts.geometry(CANVAS_PALE)
    stone = parts.geometry(STONE_PALE)
    sides = 10

    prism(stone, polygon_points((0, 0, 0), 2.9, sides), -0.3, 0.85,
          uv_scale=UV_SCALE["stone"], cap_top=False)
    frustum(warm, (0, 0.85, 0), (0, height, 0), 2.7, 1.75, sides=sides,
            uv_scale=UV_SCALE["timber"], cap_start=False, cap_end=False)
    # Corner posts and hoops so the shell reads as boarded framing.
    for index in range(sides):
        angle = TAU * index / sides
        beam(timber, (math.cos(angle) * 2.74, 0.85, math.sin(angle) * 2.74),
             (math.cos(angle) * 1.79, height, math.sin(angle) * 1.79), 0.14,
             uv_scale=UV_SCALE["timber"])
    for level, radius in ((3.0, 2.42), (5.6, 2.08)):
        for index in range(sides):
            a0, a1 = TAU * index / sides, TAU * (index + 1) / sides
            beam(timber, (math.cos(a0) * radius, level, math.sin(a0) * radius),
                 (math.cos(a1) * radius, level, math.sin(a1) * radius), 0.11,
                 uv_scale=UV_SCALE["timber"])
    # Gallery.
    box(warm, (0.0, 4.35, 0.0), (6.4, 0.16, 6.4), uv_scale=UV_SCALE["timber"])
    for index in range(sides):
        angle = TAU * index / sides
        beam(timber, (math.cos(angle) * 3.0, 4.4, math.sin(angle) * 3.0),
             (math.cos(angle) * 3.0, 5.3, math.sin(angle) * 3.0), 0.10,
             uv_scale=UV_SCALE["timber"])
    # Cap and windshaft.
    conical_canopy(canvas, (0, 0, 0), 2.05, height - 0.1, height + 1.9, sides=10,
                   uv_scale=UV_SCALE["canvas"], sag=0.07, scallop=0.06,
                   overhang=0.35, eave_drop=0.16)
    hub = (0.0, height + 0.35, -2.3)
    frustum(timber, (0.0, height + 0.35, -1.2), hub, 0.26, 0.30, sides=8,
            uv_scale=UV_SCALE["timber"])
    # Four sails: lattice frames carrying furled canvas.
    for index in range(4):
        angle = TAU * index / 4 + 0.35
        direction = (math.cos(angle), math.sin(angle))
        tip = (hub[0] + direction[0] * 5.4, hub[1] + direction[1] * 5.4, hub[2] - 0.15)
        beam(timber, (hub[0], hub[1], hub[2] - 0.15), tip, 0.16, 0.12,
             uv_scale=UV_SCALE["timber"])
        across = (-direction[1], direction[0])
        for rung in range(1, 7):
            t = rung / 7.0
            centre = (hub[0] + direction[0] * 5.4 * t, hub[1] + direction[1] * 5.4 * t,
                      hub[2] - 0.15)
            beam(timber, (centre[0] - across[0] * 0.62, centre[1] - across[1] * 0.62,
                          centre[2]),
                 (centre[0] + across[0] * 0.62, centre[1] + across[1] * 0.62,
                  centre[2]), 0.055, uv_scale=UV_SCALE["timber"])
        near = (hub[0] + direction[0] * 1.1, hub[1] + direction[1] * 1.1, hub[2] - 0.2)
        far = (hub[0] + direction[0] * 5.1, hub[1] + direction[1] * 5.1, hub[2] - 0.2)
        sheet(canvas, [
            (near[0] - across[0] * 0.10, near[1] - across[1] * 0.10, near[2]),
            (far[0] - across[0] * 0.10, far[1] - across[1] * 0.10, far[2]),
            (far[0] + across[0] * 0.58, far[1] + across[1] * 0.58, far[2]),
            (near[0] + across[0] * 0.58, near[1] + across[1] * 0.58, near[2])],
            uv_rect=(0.0, 0.0, 3.0, 0.6))
    # Door and sack hoist.
    box(warm, (0.0, 1.9, 2.62), (1.35, 2.1, 0.2), uv_scale=UV_SCALE["timber"])
    beam(timber, (0.0, 6.2, 2.3), (0.0, 6.2, 3.6), 0.14, uv_scale=UV_SCALE["timber"])
    beam(parts.geometry(LEATHER), (0.0, 6.15, 3.5), (0.0, 3.4, 3.5), 0.04,
         uv_scale=UV_SCALE["leather"])
    return parts


def steppe_well() -> Parts:
    """Stone well ring with an A-frame, windlass and bucket (panel 7)."""
    parts = Parts()
    stone = parts.geometry(STONE_PALE)
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    radius = 1.15

    # Coursed ring with a shaped coping.
    revolve(stone, [(radius, 0.0), (radius + 0.07, 0.62), (radius + 0.13, 0.86),
                    (radius + 0.05, 0.96)], (0, 0, 0), sides=16,
            uv_scale=UV_SCALE["stone"], close_bottom=False)
    revolve(stone, [(radius - 0.26, 0.0), (radius - 0.26, 0.92)], (0, 0, 0), sides=16,
            uv_scale=UV_SCALE["stone"], close_bottom=True)
    for index in range(16):
        a0, a1 = TAU * index / 16, TAU * (index + 1) / 16
        add_quad(stone, [
            (math.cos(a1) * (radius + 0.05), 0.96, math.sin(a1) * (radius + 0.05)),
            (math.cos(a0) * (radius + 0.05), 0.96, math.sin(a0) * (radius + 0.05)),
            (math.cos(a0) * (radius - 0.26), 0.92, math.sin(a0) * (radius - 0.26)),
            (math.cos(a1) * (radius - 0.26), 0.92, math.sin(a1) * (radius - 0.26))],
            [[math.cos(a1) * radius / UV_SCALE["stone"], math.sin(a1) * radius / UV_SCALE["stone"]],
             [math.cos(a0) * radius / UV_SCALE["stone"], math.sin(a0) * radius / UV_SCALE["stone"]],
             [math.cos(a0) * radius / UV_SCALE["stone"], math.sin(a0) * radius / UV_SCALE["stone"]],
             [math.cos(a1) * radius / UV_SCALE["stone"], math.sin(a1) * radius / UV_SCALE["stone"]]])
    # A-frame with a windlass drum and crank.
    for sign in (-1, 1):
        for spread in (-1, 1):
            beam(timber, (sign * (radius + 0.5), 0.0, spread * 0.55),
                 (sign * 0.12, 2.55, 0.0), 0.15, uv_scale=UV_SCALE["timber"])
    beam(timber, (-0.95, 2.5, 0.0), (0.95, 2.5, 0.0), 0.13, uv_scale=UV_SCALE["timber"])
    frustum(warm, (-0.55, 2.16, 0.0), (0.55, 2.16, 0.0), 0.19, 0.19, sides=10,
            uv_scale=UV_SCALE["timber"])
    beam(warm, (0.62, 2.16, 0.0), (0.62, 2.16, 0.42), 0.07,
         uv_scale=UV_SCALE["timber"])
    beam(warm, (0.62, 2.16, 0.42), (0.62, 1.74, 0.42), 0.07,
         uv_scale=UV_SCALE["timber"])
    # Rope and bucket.
    beam(parts.geometry(LEATHER), (0.0, 2.10, 0.0), (0.0, 1.28, 0.0), 0.035,
         uv_scale=UV_SCALE["leather"])
    revolve(warm, [(0.0, 1.02), (0.24, 1.03), (0.27, 1.28), (0.25, 1.30)],
            (0, 0, 0), sides=10, uv_scale=UV_SCALE["timber"], close_bottom=True)
    revolve(parts.geometry(METAL), [(0.275, 1.20), (0.29, 1.235), (0.275, 1.27)],
            (0, 0, 0), sides=10, uv_scale=UV_SCALE["metal"])
    # Trough and jars.
    box(warm, (0.0, 0.34, radius + 1.35), (2.4, 0.44, 0.72),
        uv_scale=UV_SCALE["timber"])
    box(warm, (0.0, 0.60, radius + 1.35), (2.2, 0.10, 0.54),
        uv_scale=UV_SCALE["timber"])
    for index, offset in enumerate((-1.9, -1.45, 1.7)):
        pot(parts, (offset, -radius - 0.65), 0.30 + 0.05 * index,
            tall=index == 2)
    return parts


def banner_shrine(variant: int = 0) -> Parts:
    """Tall pennant frame over an ornamented shrine box on a stone base (panel 4)."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    stone = parts.geometry(STONE_PALE)
    bone_parts = parts.geometry(BONE)

    # Stone plinth of stacked slabs.
    for index, (size, y0, y1) in enumerate(((2.5, 0.0, 0.34), (2.05, 0.34, 0.66),
                                            (1.65, 0.66, 0.94))):
        prism(stone, polygon_points((0, 0, 0), size * 0.5, 6, rotation=0.3 * index),
              y0, y1, uv_scale=UV_SCALE["stone"], cap_top=True)
    # Shrine box with a scalloped canopy roof and carved bone panels.
    box(warm, (0.0, 1.44, 0.0), (1.15, 1.0, 1.0), uv_scale=UV_SCALE["timber"])
    for sign in (-1, 1):
        box(bone_parts, (sign * 0.60, 1.44, 0.0), (0.06, 0.78, 0.78),
            uv_scale=UV_SCALE["bone"])
    box(bone_parts, (0.0, 1.44, 0.52), (0.86, 0.74, 0.06), uv_scale=UV_SCALE["bone"])
    conical_canopy(parts.geometry(CANVAS_PALE), (0, 0, 0), 0.95, 1.96, 2.62, sides=8,
                   uv_scale=UV_SCALE["canvas"], sag=0.05, scallop=0.16,
                   overhang=0.28, eave_drop=0.12)
    finial(parts, (0.0, 0.0), 2.58, 0.7)

    # Two tall masts carrying the pennant line.
    height = 6.2 + 0.5 * (variant % 3)
    for sign in (-1, 1):
        base = (sign * 2.05, 0.0, 0.0)
        beam(timber, (base[0], -0.3, base[2]), (base[0], height, base[2]), 0.19,
             uv_scale=UV_SCALE["timber"])
        beam(timber, (base[0], 1.5, base[2]), (base[0] + sign * 1.0, 0.0, base[2]),
             0.11, uv_scale=UV_SCALE["timber"])
        finial(parts, (base[0], base[2]), height, 0.7)
        banner(parts, (base[0], height - 0.55, base[2]), 0.75, 2.5,
               facing=math.pi / 2)
    pennant_line(parts, (-2.05, height - 0.35, 0.0), (2.05, height - 0.35, 0.0),
                 count=9, drop=0.95, length=1.55)
    pennant_line(parts, (-2.05, height - 1.7, 0.32), (2.05, height - 1.7, 0.32),
                 count=7, drop=0.7, length=1.15)
    # Offering stones and a bone totem.
    for index, angle in enumerate((0.6, 2.4, 4.3)):
        position = (math.cos(angle) * 2.0, math.sin(angle) * 2.0)
        sphere(stone, (position[0], 0.22, position[1]), 0.30 + 0.06 * index,
               rings=6, sides=8, uv_scale=UV_SCALE["stone"], squash=0.72)
    beam(bone_parts, (1.4, 0.0, 1.4), (1.5, 1.5, 1.5), 0.10,
         uv_scale=UV_SCALE["bone"])
    return parts


def caravanserai(variant: int = 0) -> Parts:
    """A walled travellers' station guarding a travel axis (panel 5).

    A short palisade court with a gate bay, a long canvas-roofed hall, stables
    and a water trough - the structure that marks each road out of the region.
    """
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    canvas = parts.geometry(CANVAS_PALE)
    stone = parts.geometry(STONE_PALE)

    width, depth = 15.0, 11.0
    half_w, half_d = width * 0.5, depth * 0.5
    # Court wall, open at the road face.
    for path in ([(-half_w, half_d), (-half_w, -half_d), (half_w, -half_d),
                  (half_w, half_d)],):
        wall_run(timber, path, 3.1, 0.55, uv_scale=UV_SCALE["timber"])
    for path, gap in (([(-half_w, half_d), (-3.0, half_d)], None),
                      ([(3.0, half_d), (half_w, half_d)], None)):
        wall_run(timber, path, 3.1, 0.55, uv_scale=UV_SCALE["timber"])
    # Palisade stake tops so the wall does not read as a plain slab.
    perimeter = [(-half_w, half_d), (-half_w, -half_d), (half_w, -half_d),
                 (half_w, half_d)]
    for index in range(len(perimeter) - 1):
        start = np.array(perimeter[index], dtype="float64")
        end = np.array(perimeter[index + 1], dtype="float64")
        length = float(np.linalg.norm(end - start))
        count = max(2, int(length / 0.62))
        for step in range(count):
            point = start + (end - start) * ((step + 0.5) / count)
            frustum(timber, (point[0], 3.0, point[1]),
                    (point[0], 3.52 + 0.12 * (step % 3), point[1]), 0.26, 0.16,
                    sides=6, uv_scale=UV_SCALE["timber"])
    # Gate bay on the road face.
    gate = palisade_gate(5.4, 3.1)
    for key, geometry in gate.items():
        parts.geometry(key).extend(geometry, compose_translation((0.0, 0.0, half_d)))
    # Long hall along the back wall.
    hall_w, hall_d = width - 3.0, 4.6
    prism(warm, [(-hall_w * 0.5, -half_d + 0.6), (hall_w * 0.5, -half_d + 0.6),
                 (hall_w * 0.5, -half_d + 0.6 + hall_d),
                 (-hall_w * 0.5, -half_d + 0.6 + hall_d)], 0.0, 2.9,
          uv_scale=UV_SCALE["timber"], cap_top=False)
    ridge_z = -half_d + 0.6 + hall_d * 0.5
    beam(timber, (-hall_w * 0.5 - 0.4, 4.5, ridge_z), (hall_w * 0.5 + 0.4, 4.5, ridge_z),
         0.24, 0.30, uv_scale=UV_SCALE["timber"])
    segments = 9
    for sz in (-1, 1):
        for index in range(segments):
            x0 = -hall_w * 0.5 - 0.5 + (hall_w + 1.0) * index / segments
            x1 = -hall_w * 0.5 - 0.5 + (hall_w + 1.0) * (index + 1) / segments
            sag0 = 0.14 * math.sin(math.pi * index / segments)
            sag1 = 0.14 * math.sin(math.pi * (index + 1) / segments)
            eave_z = ridge_z + sz * (hall_d * 0.5 + 0.7)
            corners = [(x0, 4.5 - sag0, ridge_z), (x1, 4.5 - sag1, ridge_z),
                       (x1, 2.75 - sag1, eave_z), (x0, 2.75 - sag0, eave_z)]
            if sz > 0:
                corners = corners[::-1]
            add_quad(canvas, corners,
                     [[c[0] / UV_SCALE["canvas"], c[2] / UV_SCALE["canvas"]]
                      for c in corners])
            under = [(c[0], c[1] - 0.06, c[2]) for c in corners][::-1]
            add_quad(canvas, under,
                     [[c[0] / UV_SCALE["canvas"], c[2] / UV_SCALE["canvas"]]
                      for c in under])
    for index in range(5):
        x = -hall_w * 0.5 + hall_w * index / 4.0
        beam(timber, (x, 0.0, ridge_z - hall_d * 0.5 - 0.6),
             (x, 2.75, ridge_z - hall_d * 0.5 - 0.6), 0.18,
             uv_scale=UV_SCALE["timber"])
    box(warm, (0.0, 1.35, -half_d + 0.6 + hall_d + 0.05), (2.2, 2.4, 0.22),
        uv_scale=UV_SCALE["timber"])

    # Stable lean-to on one side, trough, and yard dressing.
    side = -1 if variant % 2 == 0 else 1
    for index in range(5):
        z = -1.6 + index * 1.5
        beam(timber, (side * (half_w - 0.6), 0.0, z),
             (side * (half_w - 0.6), 2.5, z), 0.15, uv_scale=UV_SCALE["timber"])
        beam(timber, (side * (half_w - 3.4), 0.0, z),
             (side * (half_w - 3.4), 2.05, z), 0.15, uv_scale=UV_SCALE["timber"])
        if index < 4:
            add_quad(canvas, [
                (side * (half_w - 0.6), 2.5, z), (side * (half_w - 0.6), 2.5, z + 1.5),
                (side * (half_w - 3.4), 2.05, z + 1.5), (side * (half_w - 3.4), 2.05, z)]
                if side < 0 else [
                (side * (half_w - 3.4), 2.05, z), (side * (half_w - 3.4), 2.05, z + 1.5),
                (side * (half_w - 0.6), 2.5, z + 1.5), (side * (half_w - 0.6), 2.5, z)],
                [[0, 0], [1.4, 0], [1.4, 1.4], [0, 1.4]])
    box(warm, (side * (half_w - 4.6), 0.33, 1.6), (0.75, 0.5, 3.0),
        uv_scale=UV_SCALE["timber"])
    hitching_post(parts, (-side * 3.4, 2.0), 3.6, rotation=math.pi / 2)
    fire_pit(parts, (-side * 4.6, -1.0), 0.8)
    for index, (bx, bz) in enumerate(((side * 2.4, 3.2), (side * 3.2, 3.6),
                                      (-side * 5.4, 2.4))):
        barrel(parts, (bx, bz), 0.36, 0.86)
    hay_bale(parts, (side * (half_w - 4.6), -2.6), 0.6, 1.3, rotation=0.4)
    for index in range(3):
        pot(parts, (-side * (2.0 + index * 0.55), -3.4), 0.28 + 0.05 * index)
    box(stone, (0.0, 0.06, half_d + 1.4), (6.0, 0.12, 2.4),
        uv_scale=UV_SCALE["stone"])
    return parts


def animal_pen(radius: float = 6.5, sides: int = 11, gate_index: int = 0) -> Parts:
    """A post-and-rail corral with a gate bay, trough and hay feeder."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    points = polygon_points((0, 0, 0), radius, sides)
    for index in range(sides):
        if index == gate_index:
            continue
        start = np.array(points[index])
        end = np.array(points[(index + 1) % sides])
        beam(timber, (start[0], -0.25, start[1]), (start[0], 1.42, start[1]), 0.16,
             uv_scale=UV_SCALE["timber"])
        for level in (0.55, 1.02, 1.34):
            beam(warm, (start[0], level, start[1]), (end[0], level, end[1]), 0.10,
                 0.07, uv_scale=UV_SCALE["timber"])
    # Gate bay: two heavier posts and a swung rail gate.
    start = np.array(points[gate_index])
    end = np.array(points[(gate_index + 1) % sides])
    for post in (start, end):
        beam(timber, (post[0], -0.3, post[1]), (post[0], 1.85, post[1]), 0.22,
             uv_scale=UV_SCALE["timber"])
    swing = start + (end - start) * 0.15
    outward = np.array([swing[0], swing[1]])
    outward = outward / max(np.linalg.norm(outward), 1e-6)
    for level in (0.55, 1.05):
        beam(warm, (start[0], level, start[1]),
             (start[0] + outward[0] * 2.6, level, start[1] + outward[1] * 2.6),
             0.09, uv_scale=UV_SCALE["timber"])
    # Trough and feeder inside.
    box(warm, (radius * 0.42, 0.32, -radius * 0.3), (2.6, 0.46, 0.8),
        uv_scale=UV_SCALE["timber"], rotation_y=0.5)
    for index in range(2):
        hay_bale(parts, (-radius * 0.35 + index * 1.4, radius * 0.4), 0.58, 1.25,
                 rotation=0.3 + index * 0.8)
    hitching_post(parts, (0.0, -radius * 0.55), 3.0, rotation=0.2)
    return parts


def burial_mound(radius: float = 5.2, height: float = 2.4,
                 with_entrance: bool = True) -> Parts:
    """A turfed barrow with a stone lintel entrance and a kerb of set stones."""
    parts = Parts()
    turf = parts.geometry("ground_mound")
    stone = parts.geometry(STONE_PALE)
    sides = 16
    rings = 5
    for ring in range(rings):
        t0, t1 = ring / rings, (ring + 1) / rings
        r0 = radius * math.cos(t0 * math.pi * 0.5)
        r1 = radius * math.cos(t1 * math.pi * 0.5)
        y0 = height * math.sin(t0 * math.pi * 0.5)
        y1 = height * math.sin(t1 * math.pi * 0.5)
        frustum(turf, (0, y0, 0), (0, y1, 0), r0, r1, sides=sides,
                uv_scale=UV_SCALE["ground"], cap_start=False,
                cap_end=ring == rings - 1)
    # Kerb stones around the toe.
    for index in range(sides):
        angle = TAU * index / sides
        position = (math.cos(angle) * (radius + 0.15), math.sin(angle) * (radius + 0.15))
        box(stone, (position[0], 0.24, position[1]),
            (0.7, 0.55 + 0.12 * (index % 3), 0.4), uv_scale=UV_SCALE["stone"],
            rotation_y=-angle)
    if with_entrance:
        # Passage mouth: two orthostats and a heavy lintel, recessed into the toe.
        for sign in (-1, 1):
            box(stone, (sign * 0.85, 0.9, radius - 0.35), (0.45, 1.8, 1.3),
                uv_scale=UV_SCALE["stone"])
        box(stone, (0.0, 1.95, radius - 0.35), (2.5, 0.5, 1.4),
            uv_scale=UV_SCALE["stone"])
        box(parts.geometry(TIMBER_DARK), (0.0, 0.85, radius - 0.9),
            (1.3, 1.7, 0.16), uv_scale=UV_SCALE["timber"])
        box(stone, (0.0, 0.07, radius + 0.7), (3.0, 0.15, 1.8),
            uv_scale=UV_SCALE["stone"])
    return parts


MENHIR = "stone_menhir"


def standing_stone(height: float = 4.6, width: float = 1.3, lean: float = 0.08,
                   seed: int = 0) -> Parts:
    """A single weathered menhir with an irregular taper."""
    parts = Parts()
    stone = parts.geometry(MENHIR)
    rng = np.random.default_rng(seed)
    levels = 5
    previous = None
    for index in range(levels + 1):
        t = index / levels
        radius = width * 0.5 * (1.0 - 0.42 * t) * (1.0 + 0.12 * float(rng.normal()))
        y = height * t
        offset = lean * height * t
        if previous is not None:
            frustum(stone, (previous[2], previous[1], 0.0), (offset, y, 0.0),
                    previous[0], max(radius, 0.12), sides=7,
                    uv_scale=UV_SCALE["stone"], cap_start=index == 1,
                    cap_end=index == levels)
        previous = (max(radius, 0.12), y, offset)
    # Set stones packing the base.
    packing = parts.geometry(STONE_PALE)
    for index in range(5):
        angle = TAU * index / 5 + float(rng.random())
        sphere(packing, (math.cos(angle) * width * 0.75, 0.14,
                         math.sin(angle) * width * 0.75), 0.28,
               rings=5, sides=7, uv_scale=UV_SCALE["stone"], squash=0.6)
    return parts


def dock(length: float = 14.0, width: float = 3.2) -> Parts:
    """A timber landing stage on driven piles, with bollards and a stacked catch."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    deck_y = 1.35
    piles = int(length / 2.4)
    for index in range(piles + 1):
        z = -length * 0.5 + length * index / piles
        for sx in (-1, 1):
            beam(timber, (sx * width * 0.45, -2.6, z),
                 (sx * width * 0.45, deck_y, z), 0.24,
                 uv_scale=UV_SCALE["timber"])
        beam(timber, (-width * 0.5, deck_y - 0.16, z), (width * 0.5, deck_y - 0.16, z),
             0.16, uv_scale=UV_SCALE["timber"])
    planks = int(width / 0.36)
    for index in range(planks):
        x = -width * 0.5 + width * (index + 0.5) / planks
        box(warm, (x, deck_y, 0.0), (width / planks - 0.03, 0.1, length),
            uv_scale=UV_SCALE["timber"])
    for index, z in enumerate((-length * 0.36, 0.0, length * 0.36)):
        for sx in (-1, 1):
            frustum(timber, (sx * (width * 0.5 + 0.16), deck_y, z),
                    (sx * (width * 0.5 + 0.16), deck_y + 0.62, z), 0.17, 0.14,
                    sides=8, uv_scale=UV_SCALE["timber"])
    for index, (bx, bz) in enumerate(((-0.6, -length * 0.3), (0.5, -length * 0.22))):
        barrel(parts, (bx, bz), 0.34, 0.8)
    for index in range(3):
        box(warm, (0.55 - 0.1 * index, deck_y + 0.32 + index * 0.42, length * 0.28),
            (0.8, 0.42, 0.66), uv_scale=UV_SCALE["timber"],
            rotation_y=0.2 * index)
    # Coiled rope and a drying net frame.
    for sign in (-1, 1):
        beam(timber, (sign * width * 0.42, deck_y, -length * 0.44),
             (sign * width * 0.42, deck_y + 2.3, -length * 0.44), 0.12,
             uv_scale=UV_SCALE["timber"])
    beam(timber, (-width * 0.42, deck_y + 2.25, -length * 0.44),
         (width * 0.42, deck_y + 2.25, -length * 0.44), 0.10,
         uv_scale=UV_SCALE["timber"])
    sheet(parts.geometry(LEATHER), [
        (-width * 0.38, deck_y + 2.2, -length * 0.44),
        (width * 0.38, deck_y + 2.2, -length * 0.44),
        (width * 0.38, deck_y + 0.7, -length * 0.44 + 0.25),
        (-width * 0.38, deck_y + 0.7, -length * 0.44 + 0.25)],
        uv_rect=(0.0, 0.0, 2.4, 1.8))
    return parts


def drying_rack(width: float = 3.0) -> Parts:
    """A frame of hanging hides and drying meat - lived-in working dressing."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    hide = parts.geometry(LEATHER)
    for sign in (-1, 1):
        beam(timber, (sign * width * 0.5, -0.2, 0.0), (sign * width * 0.5, 2.15, 0.0),
             0.13, uv_scale=UV_SCALE["timber"])
        beam(timber, (sign * width * 0.5, 2.1, 0.0),
             (sign * (width * 0.5 + 0.7), 0.0, 0.55), 0.08,
             uv_scale=UV_SCALE["timber"])
    beam(timber, (-width * 0.55, 2.05, 0.0), (width * 0.55, 2.05, 0.0), 0.10,
         uv_scale=UV_SCALE["timber"])
    for index in range(3):
        x = -width * 0.32 + index * width * 0.32
        drop = 1.15 + 0.2 * (index % 2)
        sheet(hide, [(x - 0.42, 2.02, 0.0), (x + 0.42, 2.02, 0.0),
                     (x + 0.33, 2.02 - drop, 0.06), (x - 0.33, 2.02 - drop, 0.06)],
              uv_rect=(0.0, 0.0, 1.0, 1.4))
    return parts


def tool_rack() -> Parts:
    """Leaning tools, a bone-handled fork and a rolled textile - panel 10 language."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    metal_parts = parts.geometry(METAL)
    bone_parts = parts.geometry(BONE)
    box(warm, (0.0, 0.42, 0.0), (1.9, 0.84, 0.6), uv_scale=UV_SCALE["timber"])
    for index, (lean_x, lean_z, kind) in enumerate((
            (-0.55, 0.35, "fork"), (0.0, 0.42, "spade"), (0.55, 0.3, "staff"))):
        top = (lean_x * 1.5, 2.05, lean_z * 1.8)
        beam(timber, (lean_x, 0.0, lean_z + 0.4), top, 0.055,
             uv_scale=UV_SCALE["timber"])
        if kind == "fork":
            for tine in (-0.09, 0.0, 0.09):
                beam(bone_parts, (top[0] + tine, top[1] - 0.05, top[2]),
                     (top[0] + tine * 1.6, top[1] + 0.42, top[2]), 0.03,
                     uv_scale=UV_SCALE["bone"])
        elif kind == "spade":
            box(metal_parts, (top[0], top[1] + 0.18, top[2]), (0.26, 0.34, 0.05),
                uv_scale=UV_SCALE["metal"])
        else:
            sphere(bone_parts, (top[0], top[1] + 0.1, top[2]), 0.09, rings=5, sides=7,
                   uv_scale=UV_SCALE["bone"])
    frustum(parts.geometry(TEXTILE), (-0.75, 0.95, 0.0), (0.75, 0.95, 0.0), 0.17, 0.17,
            sides=8, uv_scale=UV_SCALE["textile"])
    for index in range(2):
        pot(parts, (0.9 + index * 0.42, -0.5), 0.26)
    return parts


# ------------------------------------------------------------------ vegetation
FOLIAGE = "foliage"
GRASS = "grass_blades"
WHEAT = "wheat_crop"


def grass_tuft(parts: Parts, center, height: float = 0.5, blades: int = 5,
               seed: int = 0, material: str = GRASS) -> None:
    """A clump of tapered blades. Opaque geometry, so there is no alpha sorting."""
    rng = np.random.default_rng(seed)
    geometry = parts.geometry(material)
    x, z = center
    for index in range(blades):
        angle = TAU * (index + float(rng.random())) / blades
        lean = 0.22 + 0.34 * float(rng.random())
        blade_height = height * (0.65 + 0.7 * float(rng.random()))
        base_half = 0.035 + 0.02 * float(rng.random())
        root = np.array([x + math.cos(angle) * 0.05, 0.0, z + math.sin(angle) * 0.05])
        tip = root + np.array([math.cos(angle) * lean * blade_height, blade_height,
                               math.sin(angle) * lean * blade_height])
        across = np.array([-math.sin(angle), 0.0, math.cos(angle)])
        # One tapered quad per blade. A second segment doubles the region's
        # ground-cover cost for a curve nobody reads at gameplay distance.
        corners = [root - across * base_half, root + across * base_half,
                   tip + across * 0.005, tip - across * 0.005]
        uvs = [[0.0, 0.0], [base_half * 2 / UV_SCALE["thatch"], 0.0],
               [0.01, blade_height / UV_SCALE["thatch"]],
               [0.0, blade_height / UV_SCALE["thatch"]]]
        add_quad(geometry, corners, uvs)


def wheat_stand(parts: Parts, center, height: float = 1.05, *,
                stems: int = 7, seed: int = 0) -> None:
    """A stand of ripe cereal with drooping ears, for the crop blocks."""
    rng = np.random.default_rng(seed)
    geometry = parts.geometry(WHEAT)
    x, z = center
    for index in range(stems):
        angle = TAU * (index + float(rng.random())) / stems
        offset = 0.10 + 0.16 * float(rng.random())
        stem_height = height * (0.82 + 0.32 * float(rng.random()))
        root = np.array([x + math.cos(angle) * offset, 0.0, z + math.sin(angle) * offset])
        lean = 0.10 + 0.12 * float(rng.random())
        top = root + np.array([math.cos(angle) * lean * stem_height, stem_height,
                               math.sin(angle) * lean * stem_height])
        frustum(geometry, root, top, 0.018, 0.012, sides=4,
                uv_scale=UV_SCALE["thatch"], cap_start=False, cap_end=False)
        # Ear: a short fat spindle nodding away from the stem.
        ear_tip = top + np.array([math.cos(angle) * 0.10, 0.20,
                                  math.sin(angle) * 0.10])
        frustum(geometry, top, (top + ear_tip) * 0.5, 0.014, 0.055, sides=5,
                uv_scale=UV_SCALE["thatch"], cap_start=False, cap_end=False)
        frustum(geometry, (top + ear_tip) * 0.5, ear_tip, 0.055, 0.008, sides=5,
                uv_scale=UV_SCALE["thatch"], cap_start=False, cap_end=False)


def shrub(radius: float = 0.75, seed: int = 0) -> Parts:
    """A low woody steppe shrub built from overlapping clumps."""
    parts = Parts()
    rng = np.random.default_rng(seed)
    wood = parts.geometry(TIMBER_DARK)
    leaves = parts.geometry(FOLIAGE)
    for index in range(3):
        angle = TAU * index / 3 + float(rng.random())
        tip = (math.cos(angle) * radius * 0.5, radius * 0.75,
               math.sin(angle) * radius * 0.5)
        beam(wood, (0.0, -0.1, 0.0), tip, 0.055, uv_scale=UV_SCALE["timber"])
        sphere(leaves, (tip[0], tip[1] + radius * 0.25, tip[2]),
               radius * (0.52 + 0.18 * float(rng.random())), rings=4, sides=6,
               uv_scale=UV_SCALE["thatch"], squash=0.72)
    return parts


def steppe_tree(height: float = 6.2, seed: int = 0) -> Parts:
    """A wind-shaped coastal tree with a broad, flattened crown."""
    parts = Parts()
    rng = np.random.default_rng(seed)
    wood = parts.geometry(TIMBER_DARK)
    leaves = parts.geometry(FOLIAGE)
    trunk_top = height * 0.44
    lean = float(rng.normal()) * 0.16
    frustum(wood, (0.0, -0.25, 0.0), (lean * 0.5, trunk_top * 0.55, lean * 0.3),
            0.34, 0.25, sides=8, uv_scale=UV_SCALE["timber"], cap_start=True,
            cap_end=False)
    frustum(wood, (lean * 0.5, trunk_top * 0.55, lean * 0.3),
            (lean, trunk_top, lean * 0.6), 0.25, 0.17, sides=8,
            uv_scale=UV_SCALE["timber"], cap_start=False, cap_end=False)
    crown = []
    branches = 5
    for index in range(branches):
        angle = TAU * index / branches + float(rng.random()) * 0.5
        reach = height * (0.30 + 0.14 * float(rng.random()))
        tip = (lean + math.cos(angle) * reach, trunk_top + height * 0.20
               + float(rng.random()) * height * 0.10, lean * 0.6 + math.sin(angle) * reach)
        beam(wood, (lean, trunk_top, lean * 0.6), tip, 0.11,
             uv_scale=UV_SCALE["timber"])
        crown.append(tip)
    for index, tip in enumerate(crown):
        sphere(leaves, (tip[0] * 0.9, tip[1] + height * 0.06, tip[2] * 0.9),
               height * (0.20 + 0.05 * float(rng.random())), rings=6, sides=9,
               uv_scale=UV_SCALE["thatch"], squash=0.55)
    sphere(leaves, (lean, trunk_top + height * 0.26, lean * 0.6), height * 0.23,
           rings=6, sides=9, uv_scale=UV_SCALE["thatch"], squash=0.52)
    return parts


def shore_rock(radius: float = 1.6, seed: int = 0) -> Parts:
    """An irregular boulder for shorelines, scree and field margins."""
    parts = Parts()
    rng = np.random.default_rng(seed)
    stone = parts.geometry(STONE_PALE)
    for index in range(2):
        offset = (float(rng.normal()) * radius * 0.35, radius * 0.14 * index,
                  float(rng.normal()) * radius * 0.35)
        sphere(stone, offset, radius * (0.88 - 0.22 * index), rings=4, sides=7,
               uv_scale=UV_SCALE["stone"], squash=0.62 + 0.1 * float(rng.random()))
    return parts


def camp_pavilion(width: float = 5.4, depth: float = 4.4, variant: int = 0) -> Parts:
    """A square-plan awning tent used for storage and shade inside the enclosure.

    Distinct from the round clan tents, so the region description's count of
    twelve round tents stays exact while the precinct still reads as dense.
    """
    parts = Parts()
    canvas = parts.geometry(CANVAS_PALE if variant % 2 == 0 else CANVAS_OCHRE)
    accent = parts.geometry(CANVAS_RED)
    timber = parts.geometry(TIMBER_DARK)
    half_w, half_d = width * 0.5, depth * 0.5
    wall, peak = 2.15, 3.9

    for sx in (-1, 1):
        for sz in (-1, 1):
            base = (sx * half_w, 0.0, sz * half_d)
            beam(timber, (base[0], -0.2, base[2]), (base[0], wall + 0.1, base[2]),
                 0.17, uv_scale=UV_SCALE["timber"])
    # Walls, open on the leeward face.
    for sx, sz, along in ((0, -1, "x"), (-1, 0, "z"), (1, 0, "z")):
        if along == "x":
            corners = [(-half_w, 0.0, sz * half_d), (half_w, 0.0, sz * half_d),
                       (half_w, wall, sz * half_d), (-half_w, wall, sz * half_d)]
        else:
            corners = [(sx * half_w, 0.0, -half_d), (sx * half_w, 0.0, half_d),
                       (sx * half_w, wall, half_d), (sx * half_w, wall, -half_d)]
        sheet(canvas, corners, uv_rect=(0.0, 0.0, width / 2.4, wall / 2.4))
    # Hipped canvas roof with sag, plus a ridge and hip rafters.
    apex = (0.0, peak, 0.0)
    eaves = [(-half_w - 0.5, wall, -half_d - 0.5), (half_w + 0.5, wall, -half_d - 0.5),
             (half_w + 0.5, wall, half_d + 0.5), (-half_w - 0.5, wall, half_d + 0.5)]
    for index in range(4):
        a = np.array(eaves[index])
        b = np.array(eaves[(index + 1) % 4])
        mid = (a + b) * 0.5 + np.array([0.0, -0.14, 0.0])
        for lower, upper in ((a, mid), (mid, b)):
            geometry_corners = [tuple(lower), tuple(upper), apex]
            normal = np.cross(np.array(upper) - np.array(lower),
                              np.array(apex) - np.array(lower))
            length = np.linalg.norm(normal)
            if length < 1e-9:
                continue
            canvas.add(geometry_corners, np.tile(normal / length, (3, 1)),
                       [[lower[0] / 2.4, lower[2] / 2.4], [upper[0] / 2.4, upper[2] / 2.4],
                        [0.0, peak / 2.4]], [0, 1, 2])
        beam(timber, tuple(a), apex, 0.09, uv_scale=UV_SCALE["timber"])
        # Valance along each eave.
        sheet(accent, [tuple(a), tuple(b),
                       (b[0], b[1] - 0.34, b[2]), (a[0], a[1] - 0.34, a[2])],
              uv_rect=(0.0, 0.0, 1.6, 0.4))
    finial(parts, (0.0, 0.0), peak - 0.05, 0.75)
    for index, (bx, bz) in enumerate(((half_w - 0.8, half_d - 0.7),
                                      (half_w - 1.5, half_d - 0.6))):
        barrel(parts, (bx, bz), 0.34, 0.82)
    for index in range(2):
        pot(parts, (-half_w + 0.7 + index * 0.5, half_d - 0.8), 0.28)
    return parts


# ------------------------------------------------------ desert and highlands
CRYSTAL = "crystal_amethyst"


def badland_spire(height: float = 11.0, radius: float = 2.4, seed: int = 0,
                  crystal: bool = False) -> Parts:
    """A wind-carved badland spire, undercut and banded like the Barrens' rock.

    Modelled rather than sculpted into the heightfield: at the region's cell
    size a spire would be two cells wide, which folds the terrain surface over
    instead of making a spire.
    """
    parts = Parts()
    rock = parts.geometry(STONE_DARK if seed % 2 else STONE_PALE)
    rng = np.random.default_rng(seed + 700)
    levels = 7
    previous = None
    lean = float(rng.normal()) * 0.05
    for index in range(levels + 1):
        t = index / levels
        # Undercut waist, flared cap: the wind erodes the softer middle beds.
        profile = (1.0 - 0.55 * math.sin(t * math.pi * 0.92) ** 2) * (1.0 - 0.30 * t)
        ring = radius * profile * (1.0 + 0.10 * float(rng.normal()))
        y = height * t
        offset = lean * height * t + 0.18 * math.sin(t * 5.0)
        if previous is not None:
            frustum(rock, (previous[2], previous[1], previous[3]),
                    (offset, y, offset * 0.4), max(previous[0], 0.10),
                    max(ring, 0.10), sides=7, uv_scale=UV_SCALE["stone"],
                    cap_start=index == 1, cap_end=index == levels)
        previous = (ring, y, offset, offset * 0.4)
    # Talus of shed blocks around the foot.
    for index in range(6):
        angle = TAU * index / 6 + float(rng.random())
        reach = radius * (1.4 + 0.7 * float(rng.random()))
        sphere(rock, (math.cos(angle) * reach, 0.16,
                      math.sin(angle) * reach), 0.32 + 0.26 * float(rng.random()),
               rings=4, sides=7, uv_scale=UV_SCALE["stone"], squash=0.62)
    if crystal:
        gems = parts.geometry(CRYSTAL)
        for index in range(5):
            angle = TAU * index / 5 + float(rng.random())
            base = (math.cos(angle) * radius * 0.85, height * (0.18 + 0.5 * float(rng.random())),
                    math.sin(angle) * radius * 0.85)
            tip = (base[0] + math.cos(angle) * 1.1, base[1] + 0.9 + float(rng.random()),
                   base[2] + math.sin(angle) * 1.1)
            frustum(gems, base, tip, 0.20, 0.0, sides=6,
                    uv_scale=UV_SCALE["crystal"], cap_start=True, cap_end=False)
    return parts


def crystal_cluster(scale: float = 1.0, seed: int = 0) -> Parts:
    """A cluster of amethyst points pushing out of the badland ground."""
    parts = Parts()
    gems = parts.geometry(CRYSTAL)
    matrix = parts.geometry(STONE_DARK)
    rng = np.random.default_rng(seed + 810)
    sphere(matrix, (0.0, -0.10, 0.0), 0.62 * scale, rings=5, sides=8,
           uv_scale=UV_SCALE["stone"], squash=0.5)
    for index in range(6):
        angle = TAU * index / 6 + float(rng.random()) * 0.7
        lean = 0.24 + 0.34 * float(rng.random())
        length = scale * (0.85 + 0.9 * float(rng.random()))
        base = (math.cos(angle) * 0.26 * scale, 0.0, math.sin(angle) * 0.26 * scale)
        tip = (base[0] + math.cos(angle) * lean * length, length,
               base[2] + math.sin(angle) * lean * length)
        width = 0.11 * scale * (0.7 + 0.6 * float(rng.random()))
        shoulder = ((base[0] + tip[0]) * 0.5, tip[1] * 0.78, (base[2] + tip[2]) * 0.5)
        frustum(gems, base, shoulder, width, width * 0.92, sides=6,
                uv_scale=UV_SCALE["crystal"], cap_start=True, cap_end=False)
        frustum(gems, shoulder, tip, width * 0.92, 0.0, sides=6,
                uv_scale=UV_SCALE["crystal"], cap_start=False, cap_end=False)
    return parts


def dead_scrub(radius: float = 0.8, seed: int = 0) -> Parts:
    """A wind-killed desert bush: bare forked wood, no leaves."""
    parts = Parts()
    wood = parts.geometry(TIMBER_DARK)
    rng = np.random.default_rng(seed + 920)
    for index in range(5):
        angle = TAU * index / 5 + float(rng.random())
        lean = 0.5 + 0.5 * float(rng.random())
        tip = (math.cos(angle) * radius * lean, radius * (0.7 + 0.5 * float(rng.random())),
               math.sin(angle) * radius * lean)
        beam(wood, (0.0, -0.08, 0.0), tip, 0.045, uv_scale=UV_SCALE["timber"])
        for fork in range(2):
            spread = angle + (fork - 0.5) * 0.9
            beam(wood, tip, (tip[0] + math.cos(spread) * radius * 0.42,
                             tip[1] + radius * 0.30,
                             tip[2] + math.sin(spread) * radius * 0.42), 0.026,
                 uv_scale=UV_SCALE["timber"])
    return parts


def bleached_bones(seed: int = 0) -> Parts:
    """A weathered skull and ribs in the sand - the steppe's memento mori."""
    parts = Parts()
    bone_parts = parts.geometry(BONE)
    rng = np.random.default_rng(seed + 1010)
    skull = (0.0, 0.16, 0.0)
    sphere(bone_parts, skull, 0.26, rings=6, sides=9, uv_scale=UV_SCALE["bone"],
           squash=0.72)
    frustum(bone_parts, skull, (0.0, 0.12, -0.46), 0.17, 0.10, sides=7,
            uv_scale=UV_SCALE["bone"], cap_start=False, cap_end=True)
    for side in (-1, 1):
        horn = (side * 0.18, 0.30, -0.04)
        frustum(bone_parts, horn, (side * 0.52, 0.42, 0.10), 0.055, 0.018, sides=6,
                uv_scale=UV_SCALE["bone"], cap_start=True, cap_end=False)
    for index in range(5):
        offset = 0.42 + index * 0.20
        arc = 0.30 - index * 0.035
        for side in (-1, 1):
            beam(bone_parts, (side * 0.04, 0.08, offset),
                 (side * arc, 0.05 + 0.10 * float(rng.random()), offset + 0.10),
                 0.035, uv_scale=UV_SCALE["bone"])
    beam(bone_parts, (0.0, 0.10, 0.34), (0.0, 0.10, 1.42), 0.055,
         uv_scale=UV_SCALE["bone"])
    return parts


def desert_waystone(height: float = 3.2, seed: int = 0) -> Parts:
    """A stacked cairn with a carved marker slab and a pennant, for the sand roads."""
    parts = Parts()
    stone = parts.geometry(STONE_PALE)
    rng = np.random.default_rng(seed + 1120)
    courses = 6
    for index in range(courses):
        t = index / courses
        radius = 0.85 * (1.0 - 0.55 * t)
        y = height * 0.62 * t
        prism(stone, polygon_points((0, 0, 0), radius, 6,
                                    rotation=0.5 * index + float(rng.random()) * 0.3),
              y, y + height * 0.62 / courses, uv_scale=UV_SCALE["stone"],
              cap_top=index == courses - 1)
    box(parts.geometry(BONE), (0.0, height * 0.62 + 0.42, 0.0), (0.62, 0.84, 0.10),
        uv_scale=UV_SCALE["bone"])
    beam(parts.geometry(TIMBER_DARK), (0.0, height * 0.55, 0.14),
         (0.0, height + 0.5, 0.14), 0.08, uv_scale=UV_SCALE["timber"])
    banner(parts, (0.0, height + 0.42, 0.14), 0.5, 1.2, facing=math.pi / 2)
    return parts


def desert_water_station() -> Parts:
    """A sunken cistern under a canvas sun-shade, for the desert caravan road."""
    parts = Parts()
    stone = parts.geometry(STONE_PALE)
    timber = parts.geometry(TIMBER_DARK)
    canvas = parts.geometry(CANVAS_PALE)
    # Sunken stone kerb around the cistern mouth.
    revolve(stone, [(1.55, 0.0), (1.62, 0.34), (1.50, 0.48), (1.24, 0.44)],
            (0, 0, 0), sides=16, uv_scale=UV_SCALE["stone"], close_bottom=False)
    revolve(stone, [(1.24, -0.9), (1.24, 0.44)], (0, 0, 0), sides=16,
            uv_scale=UV_SCALE["stone"], close_bottom=True)
    # Four posts and a taut sun-shade over the water.
    half = 2.5
    for sx in (-1, 1):
        for sz in (-1, 1):
            beam(timber, (sx * half, -0.2, sz * half), (sx * half, 3.0, sz * half),
                 0.16, uv_scale=UV_SCALE["timber"])
    apex = (0.0, 3.75, 0.0)
    corners = [(-half, 2.95, -half), (half, 2.95, -half),
               (half, 2.95, half), (-half, 2.95, half)]
    for index in range(4):
        first = corners[index]
        second = corners[(index + 1) % 4]
        mid = ((first[0] + second[0]) * 0.5, 2.82, (first[2] + second[2]) * 0.5)
        for lower, upper in ((first, mid), (mid, second)):
            normal = np.cross(np.asarray(upper) - np.asarray(lower),
                              np.asarray(apex) - np.asarray(lower))
            length = float(np.linalg.norm(normal))
            if length < 1e-9:
                continue
            canvas.add([lower, upper, apex], np.tile(normal / length, (3, 1)),
                       [[lower[0] / 2.4, lower[2] / 2.4], [upper[0] / 2.4, upper[2] / 2.4],
                        [0.0, 1.5]], [0, 1, 2])
        beam(timber, first, apex, 0.075, uv_scale=UV_SCALE["timber"])
    finial(parts, (0.0, 0.0), 3.70, 0.7)
    box(parts.geometry(TIMBER_WARM), (2.9, 0.34, 0.0), (0.7, 0.48, 2.6),
        uv_scale=UV_SCALE["timber"])
    for index in range(3):
        pot(parts, (-2.6, -0.9 + index * 0.8), 0.30 + 0.04 * index)
    barrel(parts, (2.4, -1.9), 0.36, 0.86)
    hitching_post(parts, (0.0, -3.6), 3.4, rotation=0.0)
    return parts


def cave_mouth(width: float = 5.2, height: float = 4.4, depth: float = 6.5,
               *, framed: bool = True, crystal: bool = False,
               seed: int = 0) -> Parts:
    """A cave entrance cut into a rock face.

    Built as a real recess rather than a dark decal: an arched throat sunk into
    the hillside, a lintel and jambs where the Orun have timbered it, spoil and
    boulders at the lip. The throat closes at the back so the interior stays a
    separate map and a player can never see into an empty shell.
    """
    parts = Parts()
    rock = parts.geometry(STONE_DARK)
    face = parts.geometry(STONE_PALE)
    rng = np.random.default_rng(seed + 1300)
    sides = 11
    half = width * 0.5

    def arch(t: float) -> list:
        """Cross-section of the throat at depth fraction t, narrowing inward."""
        taper = 1.0 - 0.34 * t
        ring = []
        for index in range(sides):
            angle = math.pi * index / (sides - 1)
            ring.append((math.cos(angle) * half * taper,
                         math.sin(angle) * height * taper * (0.92 + 0.08 * (1.0 - t)),
                         -depth * t))
        return ring

    rings = 5
    previous = arch(0.0)
    for step in range(1, rings + 1):
        current = arch(step / rings)
        for index in range(sides - 1):
            quad = [previous[index], previous[index + 1],
                    current[index + 1], current[index]]
            # The throat is seen from inside, so its surface faces the axis.
            inward = np.array([-(quad[0][0] + quad[2][0]) * 0.5,
                               -(quad[0][1] + quad[2][1]) * 0.5 + height * 0.4, 0.0])
            oriented_quad(rock, quad,
                          [[q[0] / UV_SCALE["stone"], q[1] / UV_SCALE["stone"]]
                           for q in quad], inward)
            if step == 1:
                floor = [(previous[index][0], -0.1, previous[index][2]),
                         (previous[index + 1][0], -0.1, previous[index + 1][2]),
                         (current[index + 1][0], -0.1, current[index + 1][2]),
                         (current[index][0], -0.1, current[index][2])]
                oriented_quad(rock, floor,
                              [[q[0] / UV_SCALE["stone"], q[2] / UV_SCALE["stone"]]
                               for q in floor], (0.0, 1.0, 0.0))
        previous = current
    # Back wall: the throat is closed, the interior is its own map.
    back = previous
    centre = (0.0, height * 0.30, -depth)
    for index in range(sides - 1):
        oriented_triangle(rock, [centre, back[index + 1], back[index]],
                          [[0.5, 0.5], [1.0, 0.0], [0.0, 0.0]], (0.0, 0.0, 1.0))

    # Rock face around the opening, so the mouth sits in a cliff rather than
    # floating on the ground.
    outer = half + 2.6
    crest = height + 2.4
    face_ring = [(-outer, 0.0, 0.4), (-outer, crest * 0.72, 0.25),
                 (-half * 0.9, crest, 0.1), (half * 0.9, crest, 0.1),
                 (outer, crest * 0.72, 0.25), (outer, 0.0, 0.4)]
    mouth_ring = arch(0.0)
    for index in range(len(face_ring) - 1):
        a = face_ring[index]
        b = face_ring[index + 1]
        near = mouth_ring[min(len(mouth_ring) - 1,
                              int(index * (sides - 1) / (len(face_ring) - 1)))]
        far = mouth_ring[min(len(mouth_ring) - 1,
                             int((index + 1) * (sides - 1) / (len(face_ring) - 1)))]
        oriented_quad(face, [a, b, (far[0], far[1], far[2] + 0.15),
                             (near[0], near[1], near[2] + 0.15)],
                      [[a[0] / 3.0, a[1] / 3.0], [b[0] / 3.0, b[1] / 3.0],
                       [far[0] / 3.0, far[1] / 3.0], [near[0] / 3.0, near[1] / 3.0]],
                      (0.0, 0.0, 1.0))
    for index in range(7):
        angle = math.pi * (index + 0.5) / 7
        sphere(face, (math.cos(angle) * (outer * 0.82),
                      crest * 0.5 + math.sin(angle) * crest * 0.42,
                      0.55 + 0.2 * float(rng.random())),
               0.65 + 0.5 * float(rng.random()), rings=4, sides=7,
               uv_scale=UV_SCALE["stone"], squash=0.7)

    if framed:
        timber = parts.geometry(TIMBER_DARK)
        for sign in (-1, 1):
            post = (sign * (half + 0.32), 0.0, 0.55)
            beam(timber, post, (post[0], height * 0.86, post[2]), 0.28,
                 uv_scale=UV_SCALE["timber"])
            beam(timber, (post[0], height * 0.86, post[2]),
                 (sign * (half - 0.5), height * 0.86 - 0.9, 0.4), 0.16,
                 uv_scale=UV_SCALE["timber"])
        beam(timber, (-(half + 0.55), height * 0.9, 0.55),
             (half + 0.55, height * 0.9, 0.55), 0.34, 0.40,
             uv_scale=UV_SCALE["timber"])
        box(parts.geometry(BONE), (0.0, height * 0.9 + 0.46, 0.55),
            (1.5, 0.5, 0.14), uv_scale=UV_SCALE["bone"])
        banner(parts, (0.0, height * 0.86, 0.75), 0.9, 1.9, facing=0.0)
        for sign in (-1, 1):
            beam(timber, (sign * (half + 0.32), 1.35, 0.55),
                 (sign * (half + 1.55), 1.05, 1.5), 0.11,
                 uv_scale=UV_SCALE["timber"])
    if crystal:
        gems = parts.geometry(CRYSTAL)
        for index in range(7):
            angle = math.pi * (index + 0.5) / 7
            base = (math.cos(angle) * half * 0.85, math.sin(angle) * height * 0.8, -0.3)
            tip = (base[0] * 1.25, base[1] * 0.94, base[2] + 0.85)
            frustum(gems, base, tip, 0.14, 0.0, sides=6,
                    uv_scale=UV_SCALE["crystal"], cap_start=True, cap_end=False)

    # Spoil heap and fallen blocks at the lip.
    for index in range(7):
        angle = math.pi * (index + 0.5) / 7
        reach = half + 0.6 + 1.9 * float(rng.random())
        sphere(face, (math.cos(angle) * reach * 0.9, 0.18,
                      1.5 + 1.4 * float(rng.random())),
               0.30 + 0.30 * float(rng.random()), rings=4, sides=7,
               uv_scale=UV_SCALE["stone"], squash=0.6)
    return parts


def mountain_scree(radius: float = 3.0, seed: int = 0) -> Parts:
    """A scree fan of broken slabs for the mountain foot."""
    parts = Parts()
    stone = parts.geometry(STONE_DARK)
    rng = np.random.default_rng(seed + 1400)
    for index in range(9):
        angle = TAU * float(rng.random())
        reach = radius * math.sqrt(float(rng.random()))
        size = 0.34 + 0.55 * float(rng.random())
        box(stone, (math.cos(angle) * reach, size * 0.32, math.sin(angle) * reach),
            (size * 1.7, size * 0.55, size * 1.2), uv_scale=UV_SCALE["stone"],
            rotation_y=float(rng.random()) * TAU)
    return parts


def cave_formation(height: float = 2.4, radius: float = 0.5, seed: int = 0,
                   *, hanging: bool = False) -> Parts:
    """A stalagmite or, hanging, a stalactite.

    Built as a stack of narrowing rings with a wandering axis so no two read as
    the same casting, and with a flared foot where it meets the rock.
    """
    parts = Parts()
    rock = parts.geometry(CAVE_ROCK_PALE if seed % 2 else CAVE_ROCK_WARM)
    rng = np.random.default_rng(seed + 1700)
    levels = 6
    drift = np.array([float(rng.normal()) * 0.06, float(rng.normal()) * 0.06])
    previous = None
    for index in range(levels + 1):
        t = index / levels
        # Flared foot, slow taper, fine tip - the shape carbonate leaves.
        ring = radius * (1.0 - t) ** 1.45 * (1.0 + 0.16 * float(rng.normal()))
        ring = max(ring, 0.035)
        y = height * t * (-1.0 if hanging else 1.0)
        offset = drift * height * t
        if previous is not None:
            frustum(rock, (previous[1], previous[0], previous[2]),
                    (offset[0], y, offset[1]), max(previous[3], 0.035), ring,
                    sides=7, uv_scale=UV_SCALE["stone"],
                    cap_start=index == 1, cap_end=index == levels)
        previous = (y, offset[0], offset[1], ring)
    return parts


def cave_column(height: float = 3.6, radius: float = 0.62, seed: int = 0) -> Parts:
    """A grown-together column: a stalagmite and stalactite joined at a waist."""
    parts = Parts()
    rock = parts.geometry(CAVE_ROCK_PALE)
    rng = np.random.default_rng(seed + 1800)
    levels = 8
    previous = None
    for index in range(levels + 1):
        t = index / levels
        # Two flares meeting at a pinched waist halfway up.
        waist = abs(t - 0.5) * 2.0
        ring = radius * (0.34 + 0.66 * waist ** 1.6) * (1.0 + 0.12 * float(rng.normal()))
        y = height * t
        wobble = 0.05 * math.sin(t * 7.0 + float(rng.random()))
        if previous is not None:
            frustum(rock, (previous[1], previous[0], previous[2]),
                    (wobble, y, wobble * 0.6), max(previous[3], 0.06),
                    max(ring, 0.06), sides=8, uv_scale=UV_SCALE["stone"],
                    cap_start=index == 1, cap_end=index == levels)
        previous = (y, wobble, wobble * 0.6, ring)
    return parts


def pit_props(width: float = 2.6, height: float = 2.5, seed: int = 0) -> Parts:
    """A timber frame the Orun have set to hold a worked passage open."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    warm = parts.geometry(TIMBER_WARM)
    half = width * 0.5
    for side in (-1, 1):
        # Legs raked slightly outward at the foot, as a set frame is built.
        beam(timber, (side * (half + 0.14), 0.0, 0.0), (side * half, height, 0.0),
             0.22, uv_scale=UV_SCALE["timber"])
    beam(warm, (-half - 0.18, height, 0.0), (half + 0.18, height, 0.0), 0.24,
         uv_scale=UV_SCALE["timber"])
    for side in (-1, 1):
        beam(timber, (side * half, height - 0.55, 0.0),
             (side * (half - 0.55), height, 0.0), 0.13,
             uv_scale=UV_SCALE["timber"])
    # Lagging boards across the crown, laid unevenly as salvage timber is.
    rng = np.random.default_rng(seed + 1900)
    for index in range(4):
        offset = -0.42 + index * 0.28
        box(warm, (0.0, height + 0.19, offset),
            (width + 0.3, 0.09, 0.22 + 0.05 * float(rng.random())),
            uv_scale=UV_SCALE["timber"])
    return parts


def cave_brazier(height: float = 1.05) -> Parts:
    """A standing iron brazier: the light source the Orun carry underground."""
    parts = Parts()
    metal = parts.geometry(METAL)
    coals = parts.geometry(STONE_DARK)
    for index in range(3):
        angle = TAU * index / 3
        beam(metal, (math.cos(angle) * 0.34, 0.0, math.sin(angle) * 0.34),
             (math.cos(angle) * 0.12, height, math.sin(angle) * 0.12), 0.07,
             uv_scale=UV_SCALE["metal"])
    revolve(metal, ((0.0, height), (0.34, height + 0.06), (0.40, height + 0.30),
                    (0.36, height + 0.34), (0.30, height + 0.10), (0.0, height + 0.04)),
            (0.0, 0.0, 0.0), sides=14, uv_scale=UV_SCALE["metal"])
    sphere(coals, (0.0, height + 0.20, 0.0), 0.26, rings=4, sides=10,
           uv_scale=UV_SCALE["stone"], squash=0.45)
    return parts


def _menhir(parts: Parts, offset_x: float, height: float, width: float, lean: float,
            seed: int) -> None:
    """One weathered menhir with an irregular taper, standing at `offset_x`."""
    stone = parts.geometry(MENHIR)
    rng = np.random.default_rng(seed)
    levels = 5
    previous = None
    for index in range(levels + 1):
        t = index / levels
        radius = width * 0.5 * (1.0 - 0.42 * t) * (1.0 + 0.12 * float(rng.normal()))
        y = height * t
        offset = lean * height * t
        if previous is not None:
            frustum(stone, (offset_x + previous[2], previous[1], 0.0),
                    (offset_x + offset, y, 0.0),
                    previous[0], max(radius, 0.12), sides=7,
                    uv_scale=UV_SCALE["stone"], cap_start=index == 1,
                    cap_end=index == levels)
        previous = (max(radius, 0.12), y, offset)
    packing = parts.geometry(STONE_PALE)
    for index in range(5):
        angle = TAU * index / 5 + float(rng.random())
        sphere(packing, (offset_x + math.cos(angle) * width * 0.75, 0.14,
                         math.sin(angle) * width * 0.75), 0.28,
               rings=5, sides=7, uv_scale=UV_SCALE["stone"], squash=0.6)


def march_gate(seed: int = 0) -> Parts:
    """Two menhirs flanking a road where the steppe hands over to a neighbour.

    The gap between them is the crossing tile. The collision pass stamps
    triangles rather than footprints, so the stones are solid and the road
    between them stays open.
    """
    parts = Parts()
    _menhir(parts, -2.6, 4.2, 1.15, 0.05, seed + 3)
    _menhir(parts, 2.6, 3.7, 1.05, -0.04, seed + 8)
    stone = parts.geometry(STONE_PALE)
    for sign in (-1, 1):
        box(stone, (sign * 2.6, 0.12, 1.3), (1.4, 0.24, 0.5), uv_scale=UV_SCALE["stone"])
        box(stone, (sign * 2.6, 0.12, -1.3), (1.4, 0.24, 0.5), uv_scale=UV_SCALE["stone"])
    banner(parts, (-2.6, 4.35, 0.0), 0.55, 1.3, facing=math.pi / 2)
    return parts


def secret_hatch() -> Parts:
    """A timber hatch set flush in the ground, with an iron bar across it: the
    way down a secret the steppe keeps under a floor."""
    parts = Parts()
    timber = parts.geometry(TIMBER_DARK)
    box(timber, (0.0, 0.1, 0.0), (1.8, 0.2, 1.4), uv_scale=UV_SCALE["timber"], rotation_y=0.2)
    for offset in (-0.45, 0.45):
        box(timber, (0.0, 0.22, offset), (1.6, 0.06, 0.12), uv_scale=UV_SCALE["timber"], rotation_y=0.2)
    box(parts.geometry(METAL), (0.5, 0.26, 0.0), (0.3, 0.06, 0.6), uv_scale=UV_SCALE["metal"])
    return parts


def filled_well() -> Parts:
    """The fourth well, filled: a steppe well ring with the shaft packed with
    dark rubble to the coping and a cairn built badly on purpose over it. The
    well-digger says the water hummed (thread H, the sour ground)."""
    parts = Parts()
    stone = parts.geometry(STONE_PALE)
    dark = parts.geometry(STONE_DARK)
    radius = 1.15
    revolve(stone, [(radius, 0.0), (radius + 0.07, 0.62), (radius + 0.13, 0.86),
                    (radius + 0.05, 0.96)], (0, 0, 0), sides=16,
            uv_scale=UV_SCALE["stone"], close_bottom=False)
    revolve(stone, [(radius - 0.26, 0.0), (radius - 0.26, 0.92)], (0, 0, 0), sides=16,
            uv_scale=UV_SCALE["stone"], close_bottom=True)
    rng = np.random.default_rng(1140)
    for index in range(14):
        angle = float(rng.random()) * TAU
        reach = float(rng.random()) * 0.7
        sphere(dark, (math.cos(angle) * reach, 0.78 + float(rng.random()) * 0.35,
                      math.sin(angle) * reach), 0.22 + float(rng.random()) * 0.16,
               rings=5, sides=7, uv_scale=UV_SCALE["stone"], squash=0.7)
    courses = 5
    for index in range(courses):
        t = index / courses
        r = 0.72 * (1.0 - 0.5 * t)
        y = 0.95 + 1.6 * t
        prism(stone, polygon_points((0.28 * t, 0, 0.12 * t), r, 6, rotation=0.6 * index),
              y, y + 1.6 / courses, uv_scale=UV_SCALE["stone"], cap_top=index == courses - 1)
    for index in range(6):
        angle = TAU * index / 6 + 0.4
        sphere(stone, (math.cos(angle) * 2.6, 0.12, math.sin(angle) * 2.6), 0.26,
               rings=5, sides=7, uv_scale=UV_SCALE["stone"], squash=0.55)
    return parts
