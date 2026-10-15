"""Amberwood building kit.

A modular timber-and-stone vocabulary: rubble plinths, framed walls with real
posts and braces, steep shingled roofs with eaves and ridge caps, porches,
balconies, chimneys, carved brackets, shutters and doors. Every part is a
closed solid with thickness - there are no single-sided planes standing in for
walls or roofs, and every decorative element is seated on the thing it belongs
to.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .noise import Rng

TIMBER = "timber_warm"
TIMBER_GREY = "timber_grey"
TIMBER_DARK = "timber_dark"
CARVED = "carved_wood"
SHINGLE = "shingles"
STONE = "ashlar"
RUBBLE = "rubble_stone"
IRON = "dark_iron"
CLOTH = "woven_cloth"
THATCH = "thatch_reed"
AMBER = "amber_resin"
GLASS = "amber_glass"


# --------------------------------------------------------------------------
# primitives with construction detail
# --------------------------------------------------------------------------

def beam(start, end, width: float, depth: float | None = None,
         material: str = TIMBER, uv_scale: float = 0.8) -> M.Mesh:
    """A squared timber running between two points, with real cross-section."""
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length < 1e-6:
        return M.Mesh(material=material)
    depth = width if depth is None else depth
    body = M.box((width, length, depth), center=(0.0, length * 0.5, 0.0),
                 uv_scale=uv_scale, material=material)
    body.transform(M.basis_from_direction(direction))
    body.translate(*start)
    return body


def post(x: float, z: float, base_y: float, height: float, width: float = 0.22,
         material: str = TIMBER, taper: float = 1.0) -> M.Mesh:
    if abs(taper - 1.0) < 1e-6:
        return M.box((width, height, width), center=(x, base_y + height * 0.5, z),
                     uv_scale=0.9, material=material)
    body = M.cylinder(width * 0.62, width * 0.62 * taper, height, 6, uv_scale=0.9,
                      material=material)
    return body.translate(x, base_y, z)


def plank_floor(half_x: float, half_z: float, y: float, thickness: float = 0.14,
                planks: int = 8, material: str = TIMBER, gap: float = 0.02,
                seed: int = 0) -> M.Mesh:
    """Individually laid boards - the deck has visible joints, not one slab."""
    rng = Rng(seed)
    parts = []
    width = (half_x * 2.0) / planks
    for i in range(planks):
        x = -half_x + width * (i + 0.5)
        wobble = float(rng.uniform(-0.012, 0.012))
        parts.append(M.box((width - gap, thickness, half_z * 2.0),
                           center=(x, y - thickness * 0.5 + wobble, 0.0),
                           uv_scale=1.4, material=material))
    return M.merge(parts, material)


def framed_wall(width: float, height: float, thickness: float = 0.24,
                material_frame: str = TIMBER_DARK, material_fill: str = TIMBER,
                studs: int = 4, braces: bool = True, seed: int = 0,
                preserve_materials: bool = False) -> M.Mesh:
    """Timber-framed panel: sill, head, studs, diagonal braces and infill."""
    parts = []
    frame = 0.16
    parts.append(M.box((width, frame, thickness), center=(0.0, frame * 0.5, 0.0),
                       uv_scale=1.0, material=material_frame))
    parts.append(M.box((width, frame, thickness),
                       center=(0.0, height - frame * 0.5, 0.0),
                       uv_scale=1.0, material=material_frame))
    for sign in (-1.0, 1.0):
        parts.append(M.box((frame, height, thickness),
                           center=(sign * (width * 0.5 - frame * 0.5), height * 0.5, 0.0),
                           uv_scale=1.0, material=material_frame))
    inner = width - frame * 2.0
    for i in range(1, studs):
        x = -inner * 0.5 + inner * i / studs
        parts.append(M.box((frame * 0.8, height - frame * 2.0, thickness * 0.92),
                           center=(x, height * 0.5, 0.0), uv_scale=1.0,
                           material=material_frame))
    if braces:
        for sign in (-1.0, 1.0):
            a = (sign * (width * 0.5 - frame), frame, 0.0)
            b = (sign * (width * 0.5 - frame - inner * 0.34), height - frame, 0.0)
            parts.append(beam(a, b, frame * 0.8, thickness * 0.9, material_frame, 1.0))
    # infill sits proud of nothing - it is recessed inside the frame
    parts.append(M.box((width - frame * 2.0, height - frame * 2.0, thickness * 0.62),
                       center=(0.0, height * 0.5, 0.0), uv_scale=1.1,
                       material=material_fill))
    if preserve_materials:
        from .stonework import group
        return group(*parts)
    return M.merge(parts, material_frame)


def door(width: float = 1.05, height: float = 2.05, thickness: float = 0.12,
         material: str = CARVED, iron: str = IRON) -> M.Mesh:
    parts = [M.box((width, height, thickness), center=(0.0, height * 0.5, 0.0),
                   uv_scale=1.3, material=material)]
    for y in (height * 0.24, height * 0.76):
        parts.append(M.box((width * 0.94, 0.09, thickness * 1.5),
                           center=(0.0, y, 0.0), uv_scale=2.0, material=iron))
    parts.append(M.box((0.09, 0.09, thickness * 1.9),
                       center=(width * 0.32, height * 0.48, 0.0), uv_scale=2.5,
                       material=iron))
    # frame
    for sign in (-1.0, 1.0):
        parts.append(M.box((0.12, height + 0.14, thickness * 1.8),
                           center=(sign * (width * 0.5 + 0.06), (height + 0.14) * 0.5, 0.0),
                           uv_scale=1.4, material=TIMBER_DARK))
    parts.append(M.box((width + 0.24, 0.14, thickness * 1.8),
                       center=(0.0, height + 0.07, 0.0), uv_scale=1.4, material=TIMBER_DARK))
    return M.merge(parts, material)


def window(width: float = 0.9, height: float = 1.15, thickness: float = 0.16,
           panes: int = 2, material: str = TIMBER_DARK, glass: str = GLASS) -> M.Mesh:
    parts = []
    parts.append(M.box((width, height, thickness * 0.5),
                       center=(0.0, height * 0.5, 0.0), uv_scale=1.6, material=glass))
    frame = 0.09
    for sign in (-1.0, 1.0):
        parts.append(M.box((frame, height + frame, thickness),
                           center=(sign * width * 0.5, height * 0.5, 0.0),
                           uv_scale=1.6, material=material))
        parts.append(M.box((width + frame, frame, thickness),
                           center=(0.0, height * 0.5 + sign * height * 0.5, 0.0),
                           uv_scale=1.6, material=material))
    for i in range(1, panes):
        parts.append(M.box((frame * 0.65, height, thickness * 0.9),
                           center=(-width * 0.5 + width * i / panes, height * 0.5, 0.0),
                           uv_scale=1.6, material=material))
    parts.append(M.box((frame * 0.65, width, thickness * 0.9),
                       center=(0.0, height * 0.52, 0.0), uv_scale=1.6, material=material)
                 .rotate_z(math.pi * 0.5))
    # sill with a drip edge
    parts.append(M.box((width + 0.30, 0.10, thickness * 2.6),
                       center=(0.0, -0.03, thickness * 0.5), uv_scale=1.4, material=STONE))
    return M.merge(parts, material)


def shutter(width: float = 0.45, height: float = 1.15, material: str = TIMBER_GREY,
            angle: float = 0.55) -> M.Mesh:
    body = M.box((width, height, 0.05), center=(width * 0.5, height * 0.5, 0.0),
                 uv_scale=1.8, material=material)
    slats = [body]
    for i in range(5):
        slats.append(M.box((width * 0.9, 0.05, 0.07),
                           center=(width * 0.5, height * (0.12 + 0.19 * i), 0.02),
                           uv_scale=2.2, material=material))
    panel = M.merge(slats, material)
    panel.rotate_y(angle)
    return panel


def bracket(size: float = 0.55, material: str = CARVED) -> M.Mesh:
    """Carved knee brace under an eave or balcony - seated against both faces."""
    parts = [
        M.box((0.13, size, 0.16), center=(0.0, size * 0.5, 0.0), uv_scale=2.0,
              material=material),
        M.box((0.13, 0.16, size), center=(0.0, size - 0.08, size * 0.5), uv_scale=2.0,
              material=material),
        beam((0.0, 0.10, 0.0), (0.0, size * 0.86, size * 0.86), 0.11, 0.11, material, 2.0),
    ]
    scroll = M.lathe([[0.0, 0.0], [0.10, 0.03], [0.13, 0.10], [0.08, 0.17], [0.0, 0.20]],
                     8, uv_scale=2.0, material=material)
    scroll.rotate_z(math.pi * 0.5).translate(0.0, size * 0.42, size * 0.42)
    parts.append(scroll)
    return M.merge(parts, material)


def railing(length: float, height: float = 0.98, posts: int = None,
            material: str = TIMBER_DARK, style: str = "turned",
            carved: str = CARVED) -> M.Mesh:
    """Balustrade running along +X, with a real handrail and bottom rail."""
    posts = posts if posts is not None else max(3, int(length / 0.46))
    parts = [
        M.box((length, 0.11, 0.16), center=(0.0, height, 0.0), uv_scale=1.6,
              material=carved),
        M.box((length, 0.08, 0.12), center=(0.0, 0.18, 0.0), uv_scale=1.6,
              material=material),
    ]
    for i in range(posts):
        x = -length * 0.5 + length * (i + 0.5) / posts
        if style == "turned":
            baluster = M.lathe(
                [[0.055, 0.0], [0.07, 0.06], [0.045, 0.18], [0.075, 0.34],
                 [0.05, 0.52], [0.062, 0.70], [0.05, height - 0.05]],
                7, uv_scale=1.8, material=material)
            parts.append(baluster.translate(x, 0.14, 0.0))
        else:
            parts.append(M.box((0.07, height - 0.20, 0.07),
                               center=(x, 0.14 + (height - 0.20) * 0.5, 0.0),
                               uv_scale=1.8, material=material))
    return M.merge(parts, material)


def roof(width: float, depth: float, pitch_height: float, overhang: float = 0.55,
         thickness: float = 0.20, material: str = SHINGLE,
         rafters: str = TIMBER_DARK, ridge: bool = True, hip: bool = False,
         clean_join: bool = False) -> M.Mesh:
    """Steep pitched roof with rafter tails, fascia and a ridge cap."""
    hw = width * 0.5 + overhang
    hd = depth * 0.5 + overhang
    if clean_join:
        from .civiccraft import pitched_canopy
        parts=list(pitched_canopy(hd*2,hw*2,0,pitch_height,material,rafters,thickness).rotate_y(math.pi/2).parts)
        for sign in (-1,1):
            pts=[(-hw,-thickness,sign*hd),(hw,-thickness,sign*hd),(0,pitch_height-thickness,sign*hd)]
            if sign<0:pts.reverse()
            parts.append(M._make(pts,[(0,0,sign)]*3,[(0,0),(1,0),(.5,1)],[0,1,2],material))
    else:
        parts = [M.gable_roof(width, depth, pitch_height, overhang, thickness,
                              uv_scale=2.3, material=material)]
    # exposed rafter tails under the eaves
    count = max(4, int(depth / 0.85))
    for i in range(count):
        z = -hd + (i + 0.5) * (hd * 2.0) / count
        for sign in (-1.0, 1.0):
            parts.append(M.box((0.62, 0.13, 0.11),
                               center=(sign * (hw - 0.28), pitch_height * (1.0 - (hw - 0.28) / hw) - 0.14, z),
                               uv_scale=2.0, material=rafters))
    # fascia board closes the eave edge
    for sign in (-1.0, 1.0):
        parts.append(M.box((0.10, 0.26, hd * 2.0),
                           center=(sign * hw, -0.06, 0.0), uv_scale=1.6, material=rafters))
    if ridge:
        parts.append(M.box((0.30, 0.18, hd * 2.0 + 0.2),
                           center=(0.0, pitch_height + 0.04, 0.0), uv_scale=1.6,
                           material=material))
    if clean_join:
        from .stonework import group
        return group(*parts)
    return M.merge(parts, material)


def chimney(width: float = 0.85, height: float = 3.4, material: str = RUBBLE,
            cap: str = STONE) -> M.Mesh:
    parts = [M.box((width, height, width), center=(0.0, height * 0.5, 0.0),
                   uv_scale=1.1, material=material)]
    parts.append(M.box((width * 1.34, 0.20, width * 1.34),
                       center=(0.0, height + 0.10, 0.0), uv_scale=1.2, material=cap))
    parts.append(M.box((width * 1.12, 0.24, width * 1.12),
                       center=(0.0, height + 0.32, 0.0), uv_scale=1.2, material=cap))
    # flue opening so the top is not a blank block
    parts.append(M.box((width * 0.34, 0.12, width * 0.34),
                       center=(0.0, height + 0.46, 0.0), uv_scale=1.6, material=IRON))
    return M.merge(parts, material)


def plinth(half_x: float, half_z: float, height: float, material: str = RUBBLE,
           batter: float = 0.10) -> M.Mesh:
    """Battered rubble base course that sets the building on the slope."""
    lower = np.array([[-half_x - batter, -half_z - batter], [half_x + batter, -half_z - batter],
                      [half_x + batter, half_z + batter], [-half_x - batter, half_z + batter]])
    upper = np.array([[-half_x, -half_z], [half_x, -half_z], [half_x, half_z],
                      [-half_x, half_z]])
    sections = [np.column_stack([lower[:, 0], np.full(4, -0.6), lower[:, 1]]),
                np.column_stack([upper[:, 0], np.full(4, height), upper[:, 1]])]
    body = M.loft(sections, closed_rings=True, uv_scale=0.5, material=material)
    cap = M.box((half_x * 2.0, 0.16, half_z * 2.0), center=(0.0, height, 0.0),
                uv_scale=0.9, material=STONE)
    return M.merge([body, cap], material)


def steps(width: float, height: float, run: float = 0.32, rise: float = 0.17,
          material: str = STONE) -> M.Mesh:
    count = max(1, int(round(height / rise)))
    return M.stairs(width, height / count, run, count, uv_scale=1.0, material=material)


# --------------------------------------------------------------------------
# whole buildings
# --------------------------------------------------------------------------

def forest_lodge(seed: int = 0, width: float = 7.2, depth: float = 9.4,
                 storeys: int = 2, porch: bool = True, balcony: bool = True,
                 workshop: bool = True, preserve_materials: bool = False) -> M.Mesh:
    """Player-scale timber lodge: porch, balcony, chimney, workshop lean-to.

    Matches the close-up reference panel of the two-storey forest house with a
    covered porch, hanging banners, an outdoor fire and a work bench.
    """
    rng = Rng(seed)
    parts = []
    hw, hd = width * 0.5, depth * 0.5
    base_height = 0.55 + float(rng.uniform(0.0, 0.35))
    parts.append(plinth(hw, hd, base_height, RUBBLE))

    storey_height = 2.55
    for level in range(storeys):
        y = base_height + level * storey_height
        fill = TIMBER if level == 0 else TIMBER_GREY
        for sign in (-1.0, 1.0):
            wall = framed_wall(width, storey_height, 0.26, TIMBER_DARK, fill,
                               studs=4, seed=seed + level, preserve_materials=preserve_materials)
            wall.translate(0.0, y, sign * hd)
            parts.append(wall)
            side = framed_wall(depth, storey_height, 0.26, TIMBER_DARK, fill,
                               studs=5, seed=seed + level + 3, preserve_materials=preserve_materials)
            side.rotate_y(math.pi * 0.5).translate(sign * hw, y, 0.0)
            parts.append(side)
        # floor plate between storeys, visibly thicker than the wall
        parts.append(M.box((width + 0.26, 0.22, depth + 0.26),
                           center=(0.0, y + storey_height, 0.0), uv_scale=1.0,
                           material=TIMBER_DARK))

    top = base_height + storeys * storey_height
    pitch = width * 0.78
    parts.append(roof(width + 0.5, depth + 0.5, pitch, 0.62, 0.22, clean_join=preserve_materials)
                 .translate(0.0, top + 0.22, 0.0))
    # gable infill under the roof so the interior is never open to the sky
    for sign in (-1.0, 1.0):
        gable = M.extrude([[-hw, 0.0], [hw, 0.0], [0.0, pitch]], 0.24, cap=True,
                          uv_scale=1.0, material=TIMBER_GREY)
        gable.rotate_x(-math.pi * 0.5).translate(0.0, top + 0.22, sign * (hd + 0.12))
        parts.append(gable)

    parts.append(chimney(0.9, storeys * storey_height * 0.6 + 2.2)
                 .translate(hw - 0.7, top - 1.2, -hd + 1.6))

    door_z = hd + (0.30 if preserve_materials else 0.06)
    parts.append(door().translate(-width * 0.16, base_height, door_z))
    for level in range(storeys):
        y = base_height + level * storey_height + 0.85
        for i, x in enumerate((-width * 0.30, width * 0.10, width * 0.32)):
            if level == 0 and i == 0:
                continue
            parts.append(window().translate(x, y, door_z))
            parts.append(shutter().translate(x + 0.48, y, door_z + 0.06))
            parts.append(shutter(angle=-0.55).translate(x - 0.48, y, door_z + 0.06))
        for x in (-depth * 0.22, depth * 0.18):
            w = window()
            w.rotate_y(math.pi * 0.5).translate(hw + (0.30 if preserve_materials else 0.06), y, x)
            parts.append(w)

    if porch:
        porch_depth = 2.3
        deck_y = base_height
        parts.append(plank_floor(hw, porch_depth * 0.5, deck_y + 0.10, 0.14, 9, TIMBER,
                                 seed=seed + 11)
                     .translate(0.0, 0.0, hd + porch_depth * 0.5))
        for x in (-hw + 0.35, 0.0, hw - 0.35):
            parts.append(post(x, hd + porch_depth - 0.35, deck_y, 2.45, 0.20, TIMBER_DARK))
            b = bracket(0.55)
            b.rotate_y(math.pi).translate(x, deck_y + 1.90, hd + porch_depth - 0.45)
            parts.append(b)
        parts.append(roof(width + 0.7, porch_depth + 0.5, 1.55, 0.35, 0.16, clean_join=preserve_materials)
                     .translate(0.0, deck_y + 2.45, hd + porch_depth * 0.5))
        rail = railing(width - 1.0)
        parts.append(rail.translate(0.0, deck_y + 0.10, hd + porch_depth - 0.12))
        parts.append(steps(1.8, base_height + 0.10, 0.32, 0.17, TIMBER_DARK)
                     .translate(width * 0.22, 0.0, hd + porch_depth))

    if balcony and storeys > 1:
        y = base_height + storey_height + 0.22
        parts.append(plank_floor(hw * 0.8, 0.75, y + 0.14, 0.12, 7, TIMBER, seed=seed + 21)
                     .translate(0.0, 0.0, hd + 0.75))
        parts.append(railing(width * 0.8 * 2.0 * 0.5 + 0.4, 0.92)
                     .translate(0.0, y + 0.14, hd + 1.42))
        for x in (-hw * 0.7, hw * 0.7):
            b = bracket(0.62)
            b.rotate_y(math.pi).translate(x, y - 0.55, hd + 0.35)
            parts.append(b)
        for x in (-hw * 0.5, hw * 0.5):
            banner = M.box((0.62, 1.35, 0.03), center=(x, y - 0.75, hd + 1.44),
                           uv_scale=1.2, material=CLOTH)
            parts.append(banner)

    if workshop:
        lean_width = 3.0
        lean_depth = 2.6
        cx = -hw - lean_width * 0.5
        parts.append(plank_floor(lean_width * 0.5, lean_depth * 0.5, base_height + 0.08,
                                 0.12, 6, TIMBER_GREY, seed=seed + 31)
                     .translate(cx, 0.0, -hd + lean_depth * 0.5 + 1.0))
        for dz in (-1.0, 1.0):
            parts.append(post(cx - lean_width * 0.42, -hd + lean_depth * 0.5 + 1.0
                              + dz * lean_depth * 0.42, base_height, 2.15, 0.18, TIMBER_DARK))
        shed = M.box((lean_width + 0.5, 0.18, lean_depth + 0.6),
                     center=(cx, base_height + 2.30, -hd + lean_depth * 0.5 + 1.0),
                     uv_scale=1.1, material=SHINGLE)
        shed.rotate_z(0.30)
        parts.append(shed)
    if preserve_materials:
        from .stonework import group
        return group(*parts)
    return M.merge(parts, TIMBER)


def manor(seed: int = 0, width: float = 15.0, depth: float = 11.0,
          storeys: int = 3, preserve_materials: bool = False) -> M.Mesh:
    """Multi-storey timber-and-stone civic hall / manor.

    The close-up reference shows a tall stone-and-timber house with tracery
    windows, steep gables, corner turrets, a terraced approach and water
    running down the terrace - all of which are built here as real solids.
    """
    rng = Rng(seed)
    parts = []
    hw, hd = width * 0.5, depth * 0.5
    base = 1.25
    parts.append(plinth(hw + 0.6, hd + 0.6, base, RUBBLE, 0.22))

    storey_height = 3.05
    for level in range(storeys):
        y = base + level * storey_height
        material = STONE if level == 0 else (STONE if level == 1 else TIMBER_GREY)
        for sign in (-1.0, 1.0):
            parts.append(M.box((width, storey_height, 0.42),
                               center=(0.0, y + storey_height * 0.5, sign * hd),
                               uv_scale=0.75, material=material))
            parts.append(M.box((0.42, storey_height, depth),
                               center=(sign * hw, y + storey_height * 0.5, 0.0),
                               uv_scale=0.75, material=material))
        # string course marking each floor
        parts.append(M.box((width + 0.55, 0.22, depth + 0.55),
                           center=(0.0, y + storey_height, 0.0), uv_scale=0.9,
                           material=STONE))
        # tall traceried windows
        for i in range(5):
            x = -width * 0.36 + width * 0.72 * i / 4
            for sign in (-1.0, 1.0):
                w = window(1.05, 2.05, 0.20, panes=3)
                if preserve_materials:
                    # Rotate in local space before translating to the back wall.
                    # The old order put both rows on the front face.
                    if sign<0:w.rotate_y(math.pi)
                    w.translate(x,y+.55,sign*(hd+.40))
                else:
                    w.translate(x, y + 0.55, sign * (hd + 0.20))
                    if sign < 0:
                        w.rotate_y(math.pi)
                        w.translate(0, 0, 0)
                parts.append(w)
                arch_head = M.arch(1.15, 0.62, 0.20, 0.30, 10, uv_scale=1.2,
                                   material=STONE)
                arch_head.translate(x, y + 2.60, sign * (hd + 0.22))
                parts.append(arch_head)
        for i in range(3):
            z = -depth * 0.30 + depth * 0.60 * i / 2
            for sign in (-1.0, 1.0):
                w = window(0.95, 1.85, 0.20, panes=2)
                w.rotate_y(sign * math.pi * 0.5 if preserve_materials else math.pi * 0.5).translate(sign * (hw + (0.40 if preserve_materials else 0.20)), y + 0.55, z)
                parts.append(w)

    top = base + storeys * storey_height
    # main roof plus cross gable
    parts.append(roof(width + 0.6, depth + 0.6, 7.4, 0.75, 0.26, clean_join=preserve_materials)
                 .translate(0.0, top + 0.25, 0.0))
    cross = roof(depth * 0.72, width * 0.42, 5.0, 0.55, 0.22, clean_join=preserve_materials)
    cross.rotate_y(math.pi * 0.5).translate(0.0, top + 0.25, hd - width * 0.10)
    parts.append(cross)
    for sign in (-1.0, 1.0):
        gable = M.extrude([[-(hw + 0.3), 0.0], [hw + 0.3, 0.0], [0.0, 7.4]], 0.30,
                          cap=True, uv_scale=0.8, material=STONE)
        gable.rotate_x(-math.pi * 0.5).translate(0.0, top + 0.25, sign * (hd + 0.44))
        parts.append(gable)

    # dormers
    for i, x in enumerate((-width * 0.28, 0.0, width * 0.28)):
        dormer_height = 1.55
        parts.append(M.box((1.5, dormer_height, 1.5),
                           center=(x, top + 0.9, hd - 1.1), uv_scale=1.0,
                           material=TIMBER_GREY))
        parts.append(roof(1.9, 1.9, 1.55, 0.22, 0.14, clean_join=preserve_materials)
                     .translate(x, top + 0.9 + dormer_height * 0.5, hd - 1.1))
        parts.append(window(0.8, 1.0, 0.16).translate(x, top + 0.35, hd - 0.34))

    # corner turrets with conical caps
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            cx, cz = sx * (hw + 0.15), sz * (hd + 0.15)
            turret_height = top + 1.4
            parts.append(M.cylinder(0.92, 0.86, turret_height, 10, uv_scale=0.8,
                                    material=STONE).translate(cx, base - 0.4, cz))
            cone = M.cylinder(1.10, 0.02, 3.8, 10, cap_bottom=False, uv_scale=2.0,
                              material=SHINGLE)
            parts.append(cone.translate(cx, turret_height + base - 0.4, cz))
            for level in range(1, storeys):
                w = window(0.55, 1.15, 0.14, panes=1)
                w.rotate_y(math.pi * 0.25 * (1 if sx > 0 else 3))
                w.translate(cx + sx * 0.58, base + level * storey_height + 0.7, cz + sz * 0.58)
                parts.append(w)

    # entrance: arched doorway, hood and approach stair
    parts.append(M.arch(2.4, 1.5, 0.45, 0.9, 14, uv_scale=0.9, material=STONE)
                 .translate(0.0, base + 2.35, hd + 0.30))
    parts.append(M.box((2.4, 2.35, 0.9), center=(0.0, base + 1.18, hd + 0.30),
                       uv_scale=0.9, material=STONE))
    parts.append(door(1.6, 2.3, 0.16).translate(0.0, base, hd + 0.78))
    parts.append(steps(3.4, base, 0.36, 0.18, STONE).translate(0.0, 0.0, hd + 0.78))
    for sign in (-1.0, 1.0):
        parts.append(railing(base * 2.2, 0.85, style="square", material=STONE, carved=STONE)
                     .rotate_y(math.pi * 0.5)
                     .translate(sign * 1.9, 0.05, hd + 1.7))
    if preserve_materials:
        from .stonework import group
        return group(*parts)
    return M.merge(parts, STONE)


def watchtower(height: float = 13.0, seed: int = 0, radius: float = 1.9) -> M.Mesh:
    """Narrow timber-and-stone lookout with a shingled cap and open gallery."""
    rng = Rng(seed)
    parts = [M.cylinder(radius * 1.28, radius, height * 0.55, 10, uv_scale=0.7,
                        material=RUBBLE)]
    parts.append(M.cylinder(radius, radius * 0.92, height * 0.45, 10, uv_scale=0.8,
                            material=TIMBER_GREY).translate(0.0, height * 0.55, 0.0))
    for i in range(4):
        angle = math.pi * 0.5 * i
        parts.append(post(math.cos(angle) * radius * 0.95, math.sin(angle) * radius * 0.95,
                          height * 0.55, height * 0.45, 0.20, TIMBER_DARK))
    # gallery deck with brackets and railing
    deck_y = height * 0.92
    parts.append(M.cylinder(radius * 1.7, radius * 1.7, 0.18, 12, uv_scale=0.9,
                            material=TIMBER).translate(0.0, deck_y, 0.0))
    for i in range(8):
        angle = math.pi * 2.0 * i / 8
        b = bracket(0.6)
        b.rotate_y(-angle + math.pi * 0.5)
        b.translate(math.cos(angle) * radius * 0.95, deck_y - 0.62,
                    math.sin(angle) * radius * 0.95)
        parts.append(b)
    for i in range(8):
        angle = math.pi * 2.0 * i / 8
        segment = railing(radius * 1.35, 0.92)
        segment.rotate_y(-angle)
        segment.translate(math.cos(angle + math.pi / 8) * radius * 1.55, deck_y + 0.18,
                          math.sin(angle + math.pi / 8) * radius * 1.55)
        parts.append(segment)
    cap = M.cylinder(radius * 1.85, 0.05, 3.6, 12, cap_bottom=False, uv_scale=2.0,
                     material=SHINGLE)
    parts.append(cap.translate(0.0, deck_y + 1.35, 0.0))
    for i in range(6):
        angle = math.pi * 2.0 * i / 6
        parts.append(post(math.cos(angle) * radius * 1.5, math.sin(angle) * radius * 1.5,
                          deck_y + 0.18, 1.2, 0.14, TIMBER_DARK))
    parts.append(M.cylinder(0.10, 0.10, 1.6, 6, uv_scale=1.4, material=IRON)
                 .translate(0.0, deck_y + 3.7, 0.0))
    # arrow slits and a door
    parts.append(door(1.0, 1.95, 0.12).translate(0.0, 0.0, radius * 1.24))
    for i in range(3):
        y = height * 0.18 + i * height * 0.13
        angle = 0.9 + i * 2.1
        slit = M.box((0.18, 0.85, 0.5),
                     center=(math.cos(angle) * radius * 1.1, y, math.sin(angle) * radius * 1.1),
                     uv_scale=1.6, material=IRON)
        parts.append(slit)
    return M.merge(parts, RUBBLE)
