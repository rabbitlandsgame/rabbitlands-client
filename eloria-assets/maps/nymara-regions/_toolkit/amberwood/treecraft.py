"""Tree-integrated architecture: platforms, walkways, hollow-tree halls, dwellings.

Every join is authored: platforms are cut around the trunk they sit on, collars
and brackets bridge the gap between bark and deck, stairs land on something, and
the hollow-tree interiors are modelled as real chambers rather than a hole in a
texture.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from . import trees as TREES
from .architecture import (AMBER, CARVED, CLOTH, IRON, RUBBLE, SHINGLE, STONE,
                           TIMBER, TIMBER_DARK, TIMBER_GREY, beam, bracket, door,
                           plank_floor, post, railing, roof, window)
from .stonework import MeshGroup, group, lamp_post
from .noise import Rng


def _annulus_deck(inner: float, outer: float, y: float, thickness: float,
                  segments: int = 16, material: str = TIMBER,
                  planks: int = 14) -> M.Mesh:
    """A deck with a hole cut for the trunk, laid as radial boards."""
    parts = []
    for i in range(planks):
        a0 = math.pi * 2.0 * i / planks
        a1 = math.pi * 2.0 * (i + 1) / planks
        gap = 0.012
        ring = []
        for radius in (inner, outer):
            for angle in (a0 + gap, a1 - gap):
                ring.append((math.cos(angle) * radius, math.sin(angle) * radius))
        polygon = [ring[0], ring[1], ring[3], ring[2]]
        board = M.extrude(np.array(polygon), thickness, cap=True, uv_scale=1.2,
                          material=material)
        parts.append(board.translate(0.0, y - thickness, 0.0))
    return M.merge(parts, material)


def trunk_collar(radius: float, y: float, height: float = 0.45,
                 material: str = TIMBER_DARK) -> M.Mesh:
    """The trim ring that closes the gap where a deck meets a trunk."""
    return M.cylinder(radius * 1.06, radius * 1.02, height, 14, cap_bottom=False,
                      cap_top=False, uv_scale=1.4, material=material).translate(0, y, 0)


def canopy_platform(trunk_radius: float = 0.85, deck_radius: float = 4.2,
                    y: float = 9.0, seed: int = 0, rails: bool = True,
                    awning: bool = False) -> MeshGroup:
    """A working deck built around a trunk, braced back into the tree."""
    rng = Rng(seed)
    timber_parts = []
    inner = trunk_radius * 1.04
    deck = _annulus_deck(inner, deck_radius, y, 0.16, material=TIMBER)
    # radial joists under the boards
    for i in range(10):
        angle = math.pi * 2.0 * i / 10
        joist = M.box((deck_radius - inner, 0.20, 0.14),
                      center=((deck_radius + inner) * 0.5, y - 0.26, 0.0),
                      uv_scale=1.2, material=TIMBER_DARK)
        timber_parts.append(joist.rotate_y(angle))
    # diagonal braces from the trunk out to the deck rim
    for i in range(8):
        angle = math.pi * 2.0 * i / 8 + 0.2
        base = np.array([math.cos(angle) * inner, y - 2.1, math.sin(angle) * inner])
        tip = np.array([math.cos(angle) * (deck_radius - 0.25), y - 0.30,
                        math.sin(angle) * (deck_radius - 0.25)])
        timber_parts.append(beam(base, tip, 0.16, 0.16, TIMBER_DARK, 1.0))
    timber_parts.append(trunk_collar(trunk_radius, y - 0.18, 0.5))
    if rails:
        segments = 12
        for i in range(segments):
            angle = math.pi * 2.0 * i / segments
            chord = 2.0 * deck_radius * math.sin(math.pi / segments)
            piece = railing(chord * 1.02, 0.95)
            piece.rotate_y(-angle - math.pi / segments)
            piece.translate(math.cos(angle + math.pi / segments) * deck_radius * 0.97,
                            y, math.sin(angle + math.pi / segments) * deck_radius * 0.97)
            timber_parts.append(piece)
    extras: list[M.Mesh] = []
    if awning:
        for i in range(4):
            angle = math.pi * 0.5 * i + 0.4
            extras.append(post(math.cos(angle) * deck_radius * 0.72, y,
                               math.sin(angle) * deck_radius * 0.72, 2.2, 0.16,
                               TIMBER_DARK).translate(0, 0, 0))
        canvas = M.cylinder(deck_radius * 0.92, deck_radius * 0.30, 1.1, 12,
                            cap_bottom=False, uv_scale=1.6, material=CLOTH)
        extras.append(canvas.translate(0.0, y + 2.2, 0.0))
    result = group(M.merge(timber_parts, TIMBER), *extras)
    result.add_walk(deck)
    return result


def suspension_walkway(start, end, sag: float = 1.1, width: float = 1.5,
                       seed: int = 0, rope_material: str = TIMBER_DARK) -> MeshGroup:
    """A rope-and-plank bridge that hangs between two anchor points."""
    rng = Rng(seed)
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    span = end - start
    length = float(np.linalg.norm(span[[0, 2]]))
    steps = max(8, int(length / 0.55))
    axis = span / max(np.linalg.norm(span), 1e-9)
    side = np.cross(axis, np.array([0.0, 1.0, 0.0]))
    side /= max(np.linalg.norm(side), 1e-9)

    parts = []
    deck_planks = []
    deck_points = []
    for i in range(steps + 1):
        t = i / steps
        point = start + span * t
        point[1] -= sag * math.sin(math.pi * t)
        deck_points.append(point)
    for i in range(steps):
        a = deck_points[i]
        b = deck_points[i + 1]
        centre = (a + b) * 0.5
        direction = b - a
        plank = M.box((float(np.linalg.norm(direction)) * 0.94, 0.07, width),
                      uv_scale=1.6, material=TIMBER)
        yaw = math.atan2(direction[2], direction[0])
        pitch = math.asin(np.clip(direction[1] / max(np.linalg.norm(direction), 1e-9),
                                  -1.0, 1.0))
        plank.rotate_z(pitch).rotate_y(-yaw)
        deck_planks.append(plank.translate(*centre))
    # hand ropes and hangers
    for sign in (-1.0, 1.0):
        rope = np.array([p + side * sign * (width * 0.5) + np.array([0.0, 1.02, 0.0])
                         - np.array([0.0, sag * 0.25 * math.sin(math.pi * (i / steps)), 0.0])
                         for i, p in enumerate(deck_points)])
        parts.append(M.tube(rope, np.full(rope.shape[0], 0.045), segments=5,
                            uv_scale=1.2, material=rope_material))
        deck_rope = np.array([p + side * sign * (width * 0.5) for p in deck_points])
        parts.append(M.tube(deck_rope, np.full(deck_rope.shape[0], 0.04), segments=5,
                            uv_scale=1.2, material=rope_material))
        for i in range(0, steps + 1, 2):
            top = rope[i]
            bottom = deck_rope[i]
            parts.append(M.tube(np.array([bottom, top]), [0.022, 0.022], segments=4,
                                uv_scale=1.2, material=rope_material))
    result = group(M.merge(parts, TIMBER))
    result.add_walk(M.merge(deck_planks, TIMBER))
    return result


def tree_dwelling(trunk_radius: float = 1.0, y: float = 8.0, seed: int = 0,
                  width: float = 4.4, depth: float = 4.0) -> MeshGroup:
    """A small house built onto a trunk: deck, walls, steep roof, chimney flue."""
    rng = Rng(seed)
    parts = []
    hw, hd = width * 0.5, depth * 0.5
    offset = trunk_radius + hw * 0.72
    parts.append(plank_floor(hw, hd, y + 0.14, 0.16, 8, TIMBER, seed=seed)
                 .translate(offset, 0.0, 0.0))
    # brackets carrying the deck back onto the trunk
    for dz in (-hd * 0.7, 0.0, hd * 0.7):
        base = np.array([trunk_radius * 0.92, y - 2.0, dz])
        tip = np.array([offset + hw * 0.6, y - 0.18, dz])
        parts.append(beam(base, tip, 0.18, 0.18, TIMBER_DARK, 1.0))
    wall_height = 2.35
    from .architecture import framed_wall
    for sign in (-1.0, 1.0):
        wall = framed_wall(width, wall_height, 0.22, TIMBER_DARK, TIMBER_GREY,
                           studs=3, seed=seed + 1)
        parts.append(wall.translate(offset, y + 0.14, sign * hd))
        side = framed_wall(depth, wall_height, 0.22, TIMBER_DARK, TIMBER_GREY,
                           studs=3, seed=seed + 2)
        side.rotate_y(math.pi * 0.5)
        parts.append(side.translate(offset + sign * hw, y + 0.14, 0.0))
    parts.append(roof(width + 0.5, depth + 0.5, width * 0.75, 0.45, 0.16)
                 .translate(offset, y + 0.14 + wall_height, 0.0))
    parts.append(window(0.75, 0.95, 0.14).translate(offset, y + 1.05, hd + 0.10))
    parts.append(door(0.9, 1.85, 0.10).translate(offset - hw + 0.05, y + 0.14, 0.0)
                 .rotate_y(0.0))
    flue = M.cylinder(0.16, 0.14, 2.4, 6, uv_scale=1.4, material=IRON)
    parts.append(flue.translate(offset + hw * 0.55, y + 0.14 + wall_height, -hd * 0.5))
    lamp = lamp_post(1.4).translate(offset - hw - 0.25, y + 0.20, hd - 0.4)
    return group(M.merge(parts, TIMBER), lamp)


def spiral_stair(radius: float, height: float, seed: int = 0,
                 material: str = TIMBER_DARK, turns: float = 1.6) -> M.Mesh:
    """Stair winding around a trunk, with treads, a newel and an outer rail."""
    parts = [M.cylinder(0.18, 0.16, height, 7, uv_scale=1.2, material=material)]
    count = max(6, int(height / 0.22))
    for i in range(count):
        t = i / count
        angle = turns * math.pi * 2.0 * t
        y = height * t
        tread = M.box((radius, 0.10, 0.42), center=(radius * 0.5, y, 0.0),
                      uv_scale=1.6, material=TIMBER)
        parts.append(tread.rotate_y(angle))
        if i % 3 == 0:
            baluster = M.box((0.07, 0.95, 0.07),
                             center=(radius * 0.92, y + 0.48, 0.0), uv_scale=1.6,
                             material=material)
            parts.append(baluster.rotate_y(angle))
    # continuous handrail
    rail_points = []
    for i in range(count + 1):
        t = i / count
        angle = turns * math.pi * 2.0 * t
        rail_points.append([math.cos(angle) * radius * 0.92, height * t + 0.95,
                            math.sin(angle) * radius * 0.92])
    parts.append(M.tube(np.array(rail_points), np.full(count + 1, 0.055), segments=5,
                        uv_scale=1.2, material=material))
    return M.merge(parts, material)


def hollow_tree_hall(seed: int = 0, outer_radius: float = 4.6, height: float = 24.0,
                     opening_width: float = 3.0, opening_height: float = 5.2,
                     interior: bool = True) -> MeshGroup:
    """A colossal hollow tree with an arched entrance, a lit interior and stairs.

    Built to the close-up reference: a buttressed trunk whose root arch forms a
    doorway, a stone stair rising into the hollow, lantern light inside, and a
    real chamber wall so the interior is not an empty shell.
    """
    rng = Rng(seed)
    bark_parts: list[M.Mesh] = []
    slices = 34
    rings = 12
    sections = []
    for r in range(rings):
        t = r / (rings - 1)
        radius = outer_radius * (1.0 - 0.52 * t ** 0.8)
        y = height * t
        ring = []
        for k in range(slices):
            angle = math.pi * 2.0 * k / slices
            lobe = 1.0 + 0.16 * math.cos(angle * 5.0 + t * 2.0) \
                + 0.09 * math.cos(angle * 9.0 - t * 3.0)
            flare = 1.0 + 0.55 * math.exp(-t * 9.0)
            rr = radius * lobe * flare
            ring.append([math.cos(angle) * rr, y, math.sin(angle) * rr])
        sections.append(np.array(ring))
    trunk = M.loft(sections, closed_rings=True, uv_scale=0.35, material="bark_dark")
    bark_parts.append(trunk)

    # buttress roots
    for i in range(11):
        angle = math.pi * 2.0 * i / 11 + float(rng.uniform(-0.12, 0.12))
        direction = np.array([math.cos(angle), 0.0, math.sin(angle)])
        # keep the doorway clear
        if abs(((angle + math.pi) % (math.pi * 2.0)) - math.pi) < 0.45:
            continue
        spread = outer_radius * float(rng.uniform(1.1, 2.0))
        points, radii = [], []
        for s in range(6):
            t = s / 5
            points.append(direction * (outer_radius * 0.8 + spread * t ** 0.8)
                          + np.array([0.0, 2.6 * (1.0 - t) ** 2.0 - 0.2 * t, 0.0]))
            radii.append(outer_radius * (0.30 * (1.0 - t) ** 0.75 + 0.04))
        bark_parts.append(M.tube(np.array(points), radii, segments=7, cap_end=True,
                                 uv_scale=0.5, material="bark_dark"))

    # the arched opening: a recessed chamber cut into the front of the trunk
    inner_parts: list[M.Mesh] = []
    if interior:
        depth = outer_radius * 1.5
        chamber = []
        chamber_rings = 8
        for r in range(chamber_rings):
            t = r / (chamber_rings - 1)
            ry = opening_height * (0.55 + 0.75 * t)
            rx = opening_width * (0.55 + 0.35 * math.sin(t * math.pi))
            ring = []
            for k in range(18):
                angle = math.pi * 2.0 * k / 18
                ring.append([math.cos(angle) * rx,
                             opening_height * 0.55 + math.sin(angle) * ry * 0.5,
                             -depth * t])
            chamber.append(np.array(ring))
        shell = M.loft(chamber, closed_rings=True, uv_scale=0.5, material="bark_dark")
        shell.flip_winding()
        shell.recompute_normals(80.0)
        inner_parts.append(shell)
        # stone stair climbing into the hollow
        from .architecture import steps as _steps
        stair = _steps(opening_width * 0.85, 1.35, 0.38, 0.17, STONE)
        stair.rotate_y(math.pi)
        inner_parts.append(stair.translate(0.0, 0.0, outer_radius * 0.55))
        floor = M.box((opening_width * 1.5, 0.25, depth),
                      center=(0.0, 1.30, -depth * 0.45), uv_scale=1.0,
                      material="cobble_paving")
        inner_parts.append(floor)

    # entrance arch of exposed root wood
    arch_parts = []
    for sign in (-1.0, 1.0):
        points = []
        radii = []
        for s in range(9):
            t = s / 8
            angle = math.pi * (0.5 - 0.5 * t) * sign + math.pi * 0.5 * (0 if sign > 0 else 2)
            px = sign * opening_width * 0.78 * math.cos(t * math.pi * 0.5)
            py = opening_height * math.sin(t * math.pi * 0.5) * 1.06
            points.append([px, py, outer_radius * 0.86 + 0.18 * math.sin(t * 3.0)])
            radii.append(0.42 * (1.0 - 0.35 * t) + 0.12)
        arch_parts.append(M.tube(np.array(points), radii, segments=8, cap_start=True,
                                 uv_scale=0.6, material="bark_dark"))
    bark_parts.extend(arch_parts)

    # lanterns inside the hollow
    lights = []
    for i in range(3):
        lights.append(lamp_post(1.5 + i * 0.25)
                      .translate(-1.1 + i * 1.1, 1.45, -1.4 - i * 1.6))
    glow = M.icosphere(0.55, 1, material=AMBER)
    glow.translate(0.0, 3.2, -outer_radius * 0.9)

    bark = M.merge(bark_parts, "bark_dark")
    bark.recompute_normals(72.0)
    result = group(bark, glow, *lights)
    for piece in inner_parts:
        result.add(piece)

    # a canopy for the colossus
    wood, foliage = TREES.build_tree("great_oak", seed=seed + 41, detail="high")
    wood.scale(1.35)
    foliage.scale(1.35)
    wood.translate(0.0, height * 0.86, 0.0)
    foliage.translate(0.0, height * 0.86, 0.0)
    result.add(wood)
    result.add(foliage)
    return result


def root_stair(width: float = 2.2, height: float = 3.2, seed: int = 0) -> MeshGroup:
    """Steps cut between exposed roots - the transition from path to platform."""
    rng = Rng(seed)
    from .architecture import steps as _steps
    parts = [_steps(width, height, 0.40, 0.19, STONE)]
    roots = []
    count = max(2, int(round(height / 1.4)))
    for sign in (-1.0, 1.0):
        for i in range(count):
            y = height * (i + 0.4) / count
            path = np.array([
                [sign * (width * 0.5 + 0.1), y - 0.3, height / 0.19 * 0.40 * (i / count) - 0.4],
                [sign * (width * 0.5 + 0.55), y + 0.25, height / 0.19 * 0.40 * (i / count) + 0.5],
                [sign * (width * 0.5 + 0.35), y - 0.1, height / 0.19 * 0.40 * (i / count) + 1.5],
            ])
            roots.append(M.tube(path, [0.24, 0.30, 0.16], segments=6, cap_end=True,
                                uv_scale=0.7, material="bark_dark"))
    root_mesh = M.merge(roots, "bark_dark")
    root_mesh.recompute_normals(70.0)
    return group(M.merge(parts, STONE), root_mesh)
