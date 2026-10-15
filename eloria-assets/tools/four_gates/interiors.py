"""Modular interior kit for the Four Gates capital.

One room shell plus a furniture library, so twenty-four interiors cost one build
rather than twenty-four. Everything is authored in local space with the floor at
y = 0 and the room centred on the origin.

Openings are built, not cut: there is no CSG in this pipeline, so a wall with a
door in it is assembled from the piers either side, the panel under the sill and
the lintel above. That keeps every wall a closed solid with correct winding.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

import kits
import meshlib as M
from kits import Palette
from meshlib import Geo

TAU = math.pi * 2.0

# (centre along the wall, width, sill height, opening height)
Opening = Tuple[float, float, float, float]


# ------------------------------------------------------------------ structure
def wall_with_openings(length: float, height: float, thickness: float,
                       material: int, openings: Sequence[Opening] = (),
                       uv_scale: float = 3.0, reveal_material: Optional[int] = None,
                       reveal_depth: float = 0.18) -> Geo:
    """A wall running along X, centred on the origin, facing +/-Z.

    Assembled from solid panels around each opening so the result stays a
    watertight solid rather than a plane with a hole painted on it.
    """
    parts: List[Geo] = []
    spans = sorted(((o[0] - o[1] * 0.5, o[0] + o[1] * 0.5, o[2], o[3])
                    for o in openings), key=lambda s: s[0])
    cursor = -length * 0.5
    for left, right, sill, opening_height in spans:
        left = max(left, -length * 0.5)
        right = min(right, length * 0.5)
        if left > cursor:
            pier = M.box(left - cursor, height, thickness, material, uv_scale,
                         origin="corner")
            pier.translate((cursor + left) * 0.5, 0.0, 0.0)
            parts.append(pier)
        if sill > 0.01:
            under = M.box(right - left, sill, thickness, material, uv_scale,
                          origin="corner")
            under.translate((left + right) * 0.5, 0.0, 0.0)
            parts.append(under)
        head = sill + opening_height
        if head < height - 0.01:
            lintel = M.box(right - left, height - head, thickness, material,
                           uv_scale, origin="corner")
            lintel.translate((left + right) * 0.5, head, 0.0)
            parts.append(lintel)
        if reveal_material is not None:
            for side in (-1, 1):
                jamb = M.box(reveal_depth, opening_height, thickness * 1.02,
                             reveal_material, 1.2, origin="corner")
                jamb.translate(left + reveal_depth * 0.5 if side < 0
                               else right - reveal_depth * 0.5, sill, 0.0)
                parts.append(jamb)
            soffit = M.box(right - left, reveal_depth, thickness * 1.02,
                           reveal_material, 1.2, origin="corner")
            soffit.translate((left + right) * 0.5, head - reveal_depth, 0.0)
            parts.append(soffit)
        cursor = right
    if cursor < length * 0.5:
        pier = M.box(length * 0.5 - cursor, height, thickness, material, uv_scale,
                     origin="corner")
        pier.translate((cursor + length * 0.5) * 0.5, 0.0, 0.0)
        parts.append(pier)
    return Geo.concat(parts)


def room_shell_parts(width: float, depth: float, height: float, p: Palette,
                     floor_material: Optional[int] = None,
                     wall_material: Optional[int] = None,
                     ceiling_material: Optional[int] = None,
                     thickness: float = 0.55,
                     north: Sequence[Opening] = (), south: Sequence[Opening] = (),
                     east: Sequence[Opening] = (), west: Sequence[Opening] = (),
                     skirting: bool = True, cornice: bool = True,
                     beams: int = 0, include_floor: bool = True) -> Dict[str, Geo]:
    """The shell split into separately named parts. -Z is north, as in the world.

    The parts are emitted as their own nodes so the client can cut away the
    ceiling and whichever wall stands between the camera and the room: an
    isometric rig framed for open ground otherwise renders the roof and the
    near wall and the player never sees the interior at all. Skirting and
    cornice travel with their wall; ceiling beams travel with the ceiling.
    """
    floor_material = p.paving_road if floor_material is None else floor_material
    wall_material = p.plaster_warm if wall_material is None else wall_material
    ceiling_material = p.timber_dark if ceiling_material is None else ceiling_material
    parts: Dict[str, Geo] = {}

    if include_floor:
        parts["floor"] = room_floor(width, depth, floor_material)

    ceiling = M.box(width + thickness * 2, 0.4, depth + thickness * 2,
                    ceiling_material, 1.8, origin="corner")
    ceiling.translate(0.0, height, 0.0)
    parts["ceiling"] = ceiling
    # The beams are a separate part because they stay visible when the ceiling
    # slab is cut away: they read as the roof overhead, they give the hanging
    # lanterns something to hang from, and edge-on they hide almost nothing.
    beam_parts: List[Geo] = []
    for i in range(beams):
        beam = M.box(width + thickness, 0.42, 0.36, p.timber_dark, 1.6,
                     origin="corner")
        beam.translate(0.0, height - 0.42,
                       -depth * 0.5 + depth * (i + 0.5) / max(beams, 1))
        beam_parts.append(beam)
    if beam_parts:
        parts["beams"] = Geo.concat(beam_parts)

    # (label, openings, run, offset, yaw, skirting/cornice band footprint)
    walls = (
        ("north", north, width, -depth * 0.5 - thickness * 0.5, 0.0,
         (0.0, -depth * 0.5 + 0.12, width, 0.24),
         (0.0, -depth * 0.5 + 0.14, width, 0.28)),
        ("south", south, width, depth * 0.5 + thickness * 0.5, 0.0,
         (0.0, depth * 0.5 - 0.12, width, 0.24),
         (0.0, depth * 0.5 - 0.14, width, 0.28)),
        ("west", west, depth, -width * 0.5 - thickness * 0.5, math.pi / 2,
         (-width * 0.5 + 0.12, 0.0, 0.24, depth),
         (-width * 0.5 + 0.14, 0.0, 0.28, depth)),
        ("east", east, depth, width * 0.5 + thickness * 0.5, math.pi / 2,
         (width * 0.5 - 0.12, 0.0, 0.24, depth),
         (width * 0.5 - 0.14, 0.0, 0.28, depth)),
    )
    for label, openings, run, offset, yaw, skirt_box, cornice_box in walls:
        pieces: List[Geo] = []
        wall = wall_with_openings(run + thickness * 2, height, thickness,
                                  wall_material, openings, uv_scale=1.7,
                                  reveal_material=p.stone_trim)
        wall.rotate_y(yaw)
        if label in ("north", "south"):
            wall.translate(0.0, 0.0, offset)
        else:
            wall.translate(offset, 0.0, 0.0)
        pieces.append(wall)
        if skirting:
            sx, sz, w, d = skirt_box
            band = M.box(w, 0.34, d, p.stone_trim, 1.2, origin="corner")
            band.translate(sx, 0.0, sz)
            pieces.append(band)
        if cornice:
            sx, sz, w, d = cornice_box
            band = M.box(w, 0.3, d, p.stone_trim, 1.2, origin="corner")
            band.translate(sx, height - 0.3, sz)
            pieces.append(band)
        parts["wall_" + label] = Geo.concat(pieces)
    return parts


def room_shell(width: float, depth: float, height: float, p: Palette,
               **kwargs) -> Geo:
    """The whole shell as one mesh -- see `room_shell_parts` for the split form."""
    parts = room_shell_parts(width, depth, height, p, **kwargs)
    return Geo.concat([parts[key] for key in sorted(parts)])


def room_floor(width: float, depth: float, material: int) -> Geo:
    floor = M.box(width, 0.4, depth, material, 1.9, origin="corner")
    floor.translate(0.0, -0.4, 0.0)
    return floor


def door_leaf(width: float, height: float, p: Palette, open_angle: float = 0.0) -> Geo:
    leaf = M.box(width, height, 0.10, p.timber_dark, 1.2, origin="corner")
    parts = [leaf]
    for i in range(3):
        rail = M.box(width * 0.82, 0.14, 0.06, p.stone_trim, 0.8, origin="corner")
        rail.translate(0.0, height * (0.22 + 0.28 * i), 0.07)
        parts.append(rail)
    handle = M.cylinder(0.07, 0.16, 8, p.metal_gold, 0.5)
    handle.rotate_x(math.pi / 2).translate(width * 0.34, height * 0.46, 0.14)
    parts.append(handle)
    geo = Geo.concat(parts)
    if abs(open_angle) > 1e-6:
        geo.translate(-width * 0.5, 0.0, 0.0).rotate_y(open_angle)
        geo.translate(width * 0.5, 0.0, 0.0)
    return geo


def vault_bay(span: float, depth: float, spring: float, p: Palette,
              material: Optional[int] = None, segments: int = 10) -> Geo:
    """Barrel-vaulted ceiling bay -- undercrofts, cellars, the Library stacks."""
    material = p.stone_ashlar if material is None else material
    # the arch spans the room's width and extrudes along its depth; rotating it
    # put the barrel across the room and the ribs flat against the end wall
    vault = M.arch_ring(span * 0.5, span * 0.5 + 0.5, depth, 0.0, math.pi,
                        segments, material, 3.0)
    vault.translate(0.0, spring, 0.0)
    ribs = []
    for z in (-depth * 0.5 + 0.2, depth * 0.5 - 0.2):
        rib = M.arch_ring(span * 0.5 + 0.45, span * 0.5 + 0.78, 0.36, 0.0,
                          math.pi, segments, p.stone_trim, 2.0)
        rib.translate(0.0, spring, z)
        ribs.append(rib)
    return Geo.concat([vault] + ribs)


def stair_flight(width: float, rise: float, run: float, p: Palette,
                 steps: int = 0, rail: bool = True) -> Geo:
    steps = steps or max(4, int(round(rise / 0.19)))
    flight = M.stairs(width, rise, run, steps, p.stone_trim, 1.4)
    parts = [flight]
    if rail:
        for side in (-1, 1):
            post_count = 4
            for i in range(post_count):
                t = (i + 0.5) / post_count
                post = M.box(0.1, 0.95, 0.1, p.metal_gold, 0.6, origin="corner")
                post.translate(side * (width * 0.5 - 0.12),
                               rise * t + 0.05, -run * 0.5 + run * t)
                parts.append(post)
    return Geo.concat(parts)


def gallery(width: float, depth: float, height: float, p: Palette,
            posts: int = 4) -> Geo:
    """Mezzanine deck with balustrade and supporting posts."""
    deck = M.box(width, 0.36, depth, p.timber_dark, 2.0, origin="corner")
    deck.translate(0.0, height, 0.0)
    parts = [deck]
    for i in range(posts):
        x = -width * 0.5 + width * (i + 0.5) / posts
        post = M.revolve([(0.16, 0.0), (0.13, 0.4), (0.12, height - 0.4),
                          (0.17, height)], 8, p.timber_dark, 1.0)
        post.translate(x, 0.0, depth * 0.5 - 0.25)
        parts.append(post)
    rail = M.box(width, 0.14, 0.16, p.metal_gold, 0.8, origin="corner")
    rail.translate(0.0, height + 1.06, depth * 0.5 - 0.1)
    parts.append(rail)
    for i in range(int(width / 0.42)):
        x = -width * 0.5 + 0.42 * (i + 0.5)
        baluster = M.cylinder(0.045, 0.7, 6, p.metal_gold, 0.5)
        baluster.translate(x, height + 0.36, depth * 0.5 - 0.1)
        parts.append(baluster)
    return Geo.concat(parts)


# ------------------------------------------------------------------ furniture
def counter(length: float, p: Palette, height: float = 1.06,
            depth: float = 0.72) -> Geo:
    body = M.box(length, height - 0.08, depth, p.timber_dark, 1.4, origin="corner")
    top = M.box(length + 0.14, 0.09, depth + 0.14, p.stone_trim, 1.2,
                origin="corner")
    top.translate(0.0, height - 0.08, 0.0)
    kick = M.box(length - 0.2, 0.12, depth * 0.7, p.stone_trim, 1.0,
                 origin="corner")
    parts = [body, top, kick]
    for i in range(max(2, int(length / 1.2))):
        x = -length * 0.5 + length * (i + 0.5) / max(2, int(length / 1.2))
        panel = M.box(length / max(2, int(length / 1.2)) * 0.7, height * 0.6, 0.05,
                      p.stone_trim, 0.8, origin="corner")
        panel.translate(x, 0.2, depth * 0.5 + 0.02)
        parts.append(panel)
    return Geo.concat(parts)


def shelf_unit(width: float, height: float, p: Palette, shelves: int = 4,
               depth: float = 0.42, stocked: bool = True, seed: int = 0) -> Geo:
    rng = np.random.default_rng(seed)
    parts = []
    for side in (-1, 1):
        upright = M.box(0.09, height, depth, p.timber_dark, 1.0, origin="corner")
        upright.translate(side * (width * 0.5 - 0.045), 0.0, 0.0)
        parts.append(upright)
    back = M.box(width, height, 0.05, p.timber_dark, 1.2, origin="corner")
    back.translate(0.0, 0.0, -depth * 0.5 + 0.025)
    parts.append(back)
    for i in range(shelves + 1):
        y = height * i / shelves
        board = M.box(width - 0.1, 0.06, depth, p.timber_dark, 1.0, origin="corner")
        board.translate(0.0, y, 0.0)
        parts.append(board)
        if stocked and i < shelves:
            count = max(2, int(width / 0.34))
            for k in range(count):
                if rng.random() < 0.22:
                    continue
                x = -width * 0.5 + width * (k + 0.5) / count
                w = float(rng.uniform(0.14, 0.26))
                h = float(rng.uniform(0.2, 0.42))
                item = M.box(w, h, depth * 0.62,
                             p.stone_trim if k % 3 else p.timber_dark, 0.5,
                             origin="corner")
                item.translate(x, y + 0.06, 0.0)
                parts.append(item)
    return Geo.concat(parts)


def bookcase(width: float, height: float, p: Palette, shelves: int = 6,
             seed: int = 0) -> Geo:
    """Denser than a shelf unit and stocked with spines rather than boxes."""
    rng = np.random.default_rng(seed)
    parts = []
    carcass = M.box(width, height, 0.36, p.timber_dark, 1.2, origin="corner")
    carcass.translate(0.0, 0.0, -0.02)
    parts.append(carcass)
    for i in range(shelves):
        y = 0.12 + (height - 0.3) * i / shelves
        board = M.box(width - 0.08, 0.05, 0.34, p.timber_dark, 1.0, origin="corner")
        board.translate(0.0, y, 0.04)
        parts.append(board)
        x = -width * 0.5 + 0.08
        while x < width * 0.5 - 0.12:
            w = float(rng.uniform(0.035, 0.075))
            h = float(rng.uniform(0.20, 0.30))
            lean = float(rng.uniform(-0.08, 0.08)) if rng.random() < 0.18 else 0.0
            spine = M.box(w, h, 0.26, p.cloth_banner if rng.random() < 0.35
                          else p.timber_dark, 0.4, origin="corner")
            if lean:
                spine.rotate_z(lean)
            spine.translate(x + w * 0.5, y + 0.05, 0.06)
            parts.append(spine)
            x += w + 0.006
    return Geo.concat(parts)


def work_table(length: float, width: float, p: Palette, height: float = 0.78) -> Geo:
    top = M.box(length, 0.08, width, p.timber_dark, 1.2, origin="corner")
    top.translate(0.0, height - 0.08, 0.0)
    parts = [top]
    for sx in (-1, 1):
        for sz in (-1, 1):
            leg = M.box(0.1, height - 0.08, 0.1, p.timber_dark, 0.8,
                        origin="corner")
            leg.translate(sx * (length * 0.5 - 0.12), 0.0,
                          sz * (width * 0.5 - 0.12))
            parts.append(leg)
    brace = M.box(length - 0.3, 0.07, 0.07, p.timber_dark, 0.8, origin="corner")
    brace.translate(0.0, height * 0.32, 0.0)
    parts.append(brace)
    return Geo.concat(parts)


def stool(p: Palette, height: float = 0.52) -> Geo:
    seat = M.cylinder(0.19, 0.07, 10, p.timber_dark, 0.5)
    seat.translate(0.0, height - 0.07, 0.0)
    parts = [seat]
    for i in range(3):
        a = TAU * i / 3
        leg = M.cylinder(0.035, height - 0.07, 6, p.timber_dark, 0.5)
        leg.rotate_x(0.13).rotate_y(a)
        leg.translate(math.cos(a) * 0.12, 0.0, math.sin(a) * 0.12)
        parts.append(leg)
    return Geo.concat(parts)


def hanging_lantern(p: Palette, drop: float = 0.9, size: float = 0.3) -> Geo:
    """A lamp on a chain. The globe is emissive glass, not metal.

    The point light that goes with a lantern sits inside its shade, so every
    outward face of a metal globe is turned away from it and the lamp renders
    as a black ball against the room. The glass carries the glow instead, and
    the metal is reduced to the cap and the ring that hold it.
    """
    chain = M.cylinder(0.022, drop, 5, p.metal_iron, 0.4)
    chain.translate(0.0, -drop, 0.0)
    globe = M.revolve([(0.0, 0.0), (size, size * 0.32), (size * 0.86, size * 1.1),
                       (size * 0.3, size * 1.35), (0.0, size * 1.45)],
                      8, p.lamp_glow, 0.6)
    globe.translate(0.0, -drop - size * 1.45, 0.0)
    cap = M.revolve([(0.0, 0.0), (size * 0.34, 0.0), (size * 0.3, size * 0.16),
                     (0.0, size * 0.2)], 8, p.metal_gold, 0.4)
    cap.translate(0.0, -drop - size * 0.06, 0.0)
    ring = M.torus_arc(size * 0.9, size * 0.045, 0.0, math.tau, 12, 6,
                       p.metal_gold, 0.4)
    ring.translate(0.0, -drop - size * 0.35, 0.0)
    return Geo.concat([chain, globe, cap, ring])


def wall_sconce(p: Palette) -> Geo:
    bracket = M.box(0.12, 0.4, 0.26, p.metal_iron, 0.5, origin="corner")
    arm = M.cylinder(0.05, 0.3, 6, p.metal_gold, 0.4)
    arm.rotate_x(math.pi / 2).translate(0.0, 0.34, 0.16)
    bowl = M.revolve([(0.0, 0.0), (0.15, 0.1), (0.12, 0.24), (0.0, 0.3)],
                     8, p.metal_gold, 0.4)
    bowl.translate(0.0, 0.34, 0.3)
    # emissive glass, for the same reason the hanging lantern uses it
    gem = M.revolve([(0.0, 0.0), (0.1, 0.1), (0.0, 0.3)], 6, p.lamp_glow, 0.4)
    gem.translate(0.0, 0.42, 0.3)
    return Geo.concat([bracket, arm, bowl, gem])


def hearth(width: float, p: Palette, height: float = 1.9) -> Geo:
    surround = wall_with_openings(width, height, 0.5, p.stone_ashlar,
                                  [(0.0, width * 0.52, 0.0, height * 0.62)],
                                  reveal_material=p.stone_trim)
    mantel = M.box(width + 0.3, 0.22, 0.72, p.stone_trim, 1.2, origin="corner")
    mantel.translate(0.0, height * 0.64, 0.1)
    back = M.box(width * 0.56, height * 0.62, 0.18, p.metal_iron, 1.0,
                 origin="corner")
    back.translate(0.0, 0.0, -0.24)
    log = M.cylinder(0.12, width * 0.34, 6, p.timber_dark, 0.5)
    log.rotate_z(math.pi / 2).translate(width * 0.17, 0.14, 0.0)
    ember = M.icosphere(0.2, 1, p.crystal_blue, 0.5)
    ember.scale(1.6, 0.5, 1.0).translate(0.0, 0.1, 0.0)
    return Geo.concat([surround, mantel, back, log, ember])


def rug(width: float, depth: float, p: Palette, material: Optional[int] = None) -> Geo:
    material = p.cloth_banner if material is None else material
    mat = M.box(width, 0.03, depth, material, 1.0, origin="corner")
    border = M.box(width + 0.16, 0.02, depth + 0.16, p.metal_gold, 1.0,
                   origin="corner")
    return Geo.concat([border, mat])


def crate_stack(p: Palette, seed: int = 0, count: int = 4) -> Geo:
    rng = np.random.default_rng(seed)
    parts = []
    y = 0.0
    for i in range(count):
        size = float(rng.uniform(0.5, 0.78))
        box = kits.crate(p, size)
        box.rotate_y(float(rng.uniform(-0.3, 0.3)))
        box.translate(float(rng.uniform(-0.12, 0.12)), y,
                      float(rng.uniform(-0.12, 0.12)))
        parts.append(box)
        y += size * 0.85
    return Geo.concat(parts)


def sign_board(text_slots: int, p: Palette, width: float = 1.5) -> Geo:
    """A hanging trade sign: the shop's identity, read from the street."""
    arm = M.box(0.7, 0.09, 0.09, p.metal_iron, 0.5, origin="corner")
    arm.translate(0.35, 0.0, 0.0)
    board = M.box(width, 0.72, 0.07, p.timber_dark, 0.8, origin="corner")
    board.translate(0.64, -0.78, 0.0)
    frame = M.box(width + 0.1, 0.08, 0.09, p.metal_gold, 0.6, origin="corner")
    frame.translate(0.64, -0.12, 0.0)
    parts = [arm, board, frame]
    for i in range(text_slots):
        mark = M.cylinder(0.12, 0.04, 8, p.metal_gold, 0.4)
        mark.rotate_x(math.pi / 2)
        mark.translate(0.64 - width * 0.3 + width * 0.6 * i / max(text_slots - 1, 1),
                       -0.42, 0.05)
        parts.append(mark)
    return Geo.concat(parts)
