"""Environmental storytelling props: the lived-in economy of Amberwood.

Forestry, amber working, fishing, market trade and household life, plus the
small natural dressing (rocks, logs, fungi, leaf drifts) that keeps the forest
floor from reading as a flat texture.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .architecture import (AMBER, CARVED, CLOTH, GLASS, IRON, RUBBLE, SHINGLE,
                           STONE, THATCH, TIMBER, TIMBER_DARK, TIMBER_GREY,
                           beam, bracket, plank_floor, post, railing, roof)
from .stonework import MeshGroup, group
from .noise import Rng

CANVAS = "canvas_awning"


# --------------------------------------------------------------------------
# containers and gear
# --------------------------------------------------------------------------

def barrel(radius: float = 0.34, height: float = 0.86, seed: int = 0,
           material: str = TIMBER, hoops: str = IRON) -> MeshGroup:
    staves = M.lathe([[radius * 0.86, 0.0], [radius * 1.0, height * 0.22],
                      [radius * 1.04, height * 0.5], [radius * 1.0, height * 0.78],
                      [radius * 0.86, height]], 12, uv_scale=1.6, material=material)
    lid = M.lathe([[0.0, height], [radius * 0.88, height]], 12, uv_scale=1.6,
                  material=material)
    bands = []
    for t in (0.12, 0.42, 0.86):
        bands.append(M.cylinder(radius * 1.06, radius * 1.06, 0.06, 12,
                                cap_bottom=False, cap_top=False, uv_scale=2.2,
                                material=hoops).translate(0, height * t, 0))
    return group(M.merge([staves, lid], material), M.merge(bands, hoops))


def crate(size: float = 0.66, seed: int = 0, material: str = TIMBER_GREY) -> M.Mesh:
    rng = Rng(seed)
    h = size * 0.86
    parts = [M.box((size, h, size), center=(0, h * 0.5, 0), uv_scale=1.6,
                   material=material)]
    for sign in (-1.0, 1.0):
        for axis in range(2):
            for y in (h * 0.16, h * 0.84):
                dims = (size * 1.02, 0.06, 0.06) if axis == 0 else (0.06, 0.06, size * 1.02)
                offset = (0.0, y, sign * size * 0.5) if axis == 0 \
                    else (sign * size * 0.5, y, 0.0)
                parts.append(M.box(dims, center=offset, uv_scale=2.2,
                                   material=TIMBER_DARK))
    mesh = M.merge(parts, material)
    mesh.rotate_y(float(rng.uniform(0, math.pi * 2)))
    return mesh


def basket(radius: float = 0.30, height: float = 0.42, seed: int = 0,
           material: str = THATCH, contents: str | None = None) -> MeshGroup:
    body = M.lathe([[radius * 0.62, 0.0], [radius * 0.78, height * 0.25],
                    [radius, height * 0.75], [radius * 1.04, height]],
                   12, uv_scale=2.0, material=material)
    rim = M.cylinder(radius * 1.08, radius * 1.08, 0.05, 12, cap_bottom=False,
                     cap_top=False, uv_scale=2.4, material=material)
    parts = [body, rim.translate(0, height - 0.04, 0)]
    extras = []
    if contents:
        heap = M.icosphere(radius * 0.92, 1, material=contents)
        heap.scale(1.0, 0.45, 1.0)
        extras.append(heap.translate(0.0, height * 0.92, 0.0))
    return group(M.merge(parts, material), *extras)


def sack(radius: float = 0.26, height: float = 0.55, seed: int = 0) -> M.Mesh:
    body = M.lathe([[radius * 0.85, 0.0], [radius * 1.05, height * 0.35],
                    [radius * 0.92, height * 0.72], [radius * 0.42, height * 0.92],
                    [radius * 0.18, height]], 10, uv_scale=1.8, material=CLOTH)
    body.jitter(0.012, seed=seed)
    body.recompute_normals(70.0)
    return body


def log_pile(length: float = 3.2, rows: int = 3, per_row: int = 5, seed: int = 0,
             radius: float = 0.22, material: str = "bark_dark") -> M.Mesh:
    """Stacked timber - the forestry economy made visible."""
    rng = Rng(seed)
    parts = []
    for r in range(rows):
        count = max(1, per_row - r)
        for i in range(count):
            x = (i - (count - 1) * 0.5) * radius * 2.1
            y = radius + r * radius * 1.86
            log = M.cylinder(radius * float(rng.uniform(0.86, 1.12)),
                             radius * float(rng.uniform(0.86, 1.08)),
                             length * float(rng.uniform(0.92, 1.05)), 8,
                             uv_scale=0.9, material=material)
            log.rotate_z(math.pi * 0.5)
            log.translate(-length * 0.5, y, x + float(rng.normal(0, 0.02)))
            parts.append(log)
    # end posts holding the stack
    for sign in (-1.0, 1.0):
        for z in (-per_row * radius * 1.1, per_row * radius * 1.1):
            parts.append(post(sign * length * 0.52, z, 0.0, rows * radius * 2.0 + 0.4,
                              0.14, TIMBER_DARK))
    return M.merge(parts, material)


def firewood(radius: float = 0.72, seed: int = 0) -> M.Mesh:
    rng = Rng(seed)
    parts = []
    for i in range(22):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0, radius))
        piece = M.cylinder(0.055, 0.05, float(rng.uniform(0.3, 0.5)), 6,
                           uv_scale=1.4, material="bark_dark")
        piece.rotate_z(math.pi * 0.5).rotate_y(float(rng.uniform(0, math.pi)))
        parts.append(piece.translate(math.cos(angle) * r, 0.06 + (i % 4) * 0.11,
                                     math.sin(angle) * r))
    return M.merge(parts, "bark_dark")


def cart(seed: int = 0, length: float = 2.6, width: float = 1.35) -> MeshGroup:
    """Two-wheeled forest cart with a boarded bed, shafts and iron tyres."""
    rng = Rng(seed)
    wheel_radius = 0.62
    timber_parts = [
        plank_floor(length * 0.5, width * 0.5, wheel_radius + 0.42, 0.09, 7, TIMBER,
                    seed=seed),
    ]
    for sign in (-1.0, 1.0):
        timber_parts.append(M.box((length, 0.42, 0.10),
                                  center=(0.0, wheel_radius + 0.62, sign * width * 0.5),
                                  uv_scale=1.6, material=TIMBER_GREY))
        timber_parts.append(M.box((0.10, 0.42, width),
                                  center=(sign * length * 0.5, wheel_radius + 0.62, 0.0),
                                  uv_scale=1.6, material=TIMBER_GREY))
    axle = M.cylinder(0.07, 0.07, width + 0.5, 6, uv_scale=1.4, material=IRON)
    axle.rotate_x(math.pi * 0.5).translate(0.0, wheel_radius, (width + 0.5) * 0.5)
    for sign in (-1.0, 1.0):
        timber_parts.append(beam((sign * 0.18, wheel_radius + 0.40, -width * 0.42),
                                 (sign * 0.30, wheel_radius + 0.30, -width * 0.42 - 1.6),
                                 0.09, 0.09, TIMBER_DARK, 1.2))
    wheels = []
    for sign in (-1.0, 1.0):
        hub = M.cylinder(0.13, 0.13, 0.18, 8, uv_scale=1.4, material=TIMBER_DARK)
        rim = M.lathe([[wheel_radius - 0.10, 0.0], [wheel_radius, 0.03],
                       [wheel_radius, 0.13], [wheel_radius - 0.10, 0.16]], 16,
                      uv_scale=1.4, material=TIMBER_DARK)
        tyre = M.cylinder(wheel_radius + 0.04, wheel_radius + 0.04, 0.10, 16,
                          cap_bottom=False, cap_top=False, uv_scale=2.0, material=IRON)
        spokes = []
        for i in range(8):
            spoke = M.box((0.05, wheel_radius - 0.10, 0.06),
                          center=(0.0, (wheel_radius - 0.10) * 0.5 + 0.13, 0.08),
                          uv_scale=1.6, material=TIMBER_DARK)
            spokes.append(spoke.rotate_z(math.pi * 2.0 * i / 8))
        wheel = M.merge([hub, rim, tyre] + spokes, TIMBER_DARK)
        wheel.rotate_x(math.pi * 0.5)
        wheels.append(wheel.translate(0.0, wheel_radius, sign * (width * 0.5 + 0.16)))
    return group(M.merge(timber_parts, TIMBER), M.merge(wheels + [axle], TIMBER_DARK))


def workbench(length: float = 2.1, seed: int = 0, tools: bool = True) -> MeshGroup:
    rng = Rng(seed)
    height = 0.88
    parts = [plank_floor(length * 0.5, 0.38, height, 0.09, 5, TIMBER, seed=seed)]
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            parts.append(post(sx * (length * 0.5 - 0.14), sz * 0.30, 0.0, height,
                              0.10, TIMBER_DARK))
    parts.append(M.box((length - 0.3, 0.07, 0.12), center=(0.0, 0.32, 0.0),
                       uv_scale=1.8, material=TIMBER_DARK))
    extras = []
    if tools:
        vice = M.box((0.24, 0.20, 0.30), center=(-length * 0.36, height + 0.10, 0.20),
                     uv_scale=2.0, material=IRON)
        extras.append(vice)
        for i in range(3):
            chisel = M.cylinder(0.017, 0.014, 0.28, 5, uv_scale=1.8, material=IRON)
            chisel.rotate_z(math.pi * 0.5)
            extras.append(chisel.translate(length * 0.1 + i * 0.10, height + 0.06, -0.16))
        mallet = M.cylinder(0.07, 0.07, 0.16, 7, uv_scale=1.6, material=TIMBER_DARK)
        mallet.rotate_z(math.pi * 0.5)
        extras.append(mallet.translate(length * 0.28, height + 0.10, 0.10))
    return group(M.merge(parts, TIMBER), *extras)


def market_stall(width: float = 2.6, depth: float = 1.8, seed: int = 0,
                 goods: str = AMBER) -> MeshGroup:
    rng = Rng(seed)
    height = 2.15
    parts = [plank_floor(width * 0.5, depth * 0.5, 0.92, 0.09, 6, TIMBER, seed=seed)]
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            parts.append(post(sx * width * 0.46, sz * depth * 0.44, 0.0, height, 0.09,
                              TIMBER_DARK))
    canopy = M.gable_roof(width + 0.5, depth + 0.5, 0.55, 0.30, 0.05, uv_scale=1.4,
                          material=CANVAS)
    parts.append(canopy.translate(0.0, height, 0.0))
    extras = []
    for i in range(5):
        heap = M.icosphere(0.11 + 0.03 * (i % 3), 1, material=goods)
        heap.scale(1.0, 0.7, 1.0)
        extras.append(heap.translate(-width * 0.32 + i * width * 0.16, 1.00,
                                     float(rng.uniform(-0.3, 0.3))))
    extras.append(basket(0.24, 0.34, seed + 1).translate(width * 0.34, 0.94, 0.0))
    return group(M.merge(parts, TIMBER), *extras)


def amber_workstation(seed: int = 0) -> MeshGroup:
    """The amber-working scene from the close-up board: hanging vessels, scales, trays."""
    rng = Rng(seed)
    bench = workbench(2.3, seed, tools=False)
    parts = []
    extras = []
    frame_height = 2.5
    for sx in (-1.0, 1.0):
        parts.append(post(sx * 1.2, 0.0, 0.88, frame_height - 0.88, 0.10, TIMBER_DARK))
    parts.append(beam((-1.35, frame_height, 0.0), (1.35, frame_height, 0.0),
                      0.11, 0.11, TIMBER_DARK, 1.4))
    # suspended amber vessels of different sizes
    for i, x in enumerate((-0.85, -0.15, 0.55, 1.05)):
        drop = 0.35 + 0.22 * ((i * 7) % 3)
        parts.append(M.tube(np.array([[x, frame_height - 0.05, 0.0],
                                      [x, frame_height - drop, 0.0]]),
                            [0.012, 0.012], segments=4, uv_scale=1.2, material=IRON))
        size = 0.14 + 0.06 * (i % 3)
        vessel = M.lathe([[0.0, 0.0], [size * 0.9, size * 0.35], [size, size * 1.05],
                          [size * 0.55, size * 1.55], [size * 0.30, size * 1.75],
                          [0.0, size * 1.80]], 10, uv_scale=1.6, material=GLASS)
        extras.append(vessel.translate(x, frame_height - drop - size * 1.8, 0.0))
    # balance scales
    parts.append(M.tube(np.array([[0.0, frame_height - 0.05, 0.42],
                                  [0.0, frame_height - 0.62, 0.42]]), [0.012, 0.012],
                        segments=4, uv_scale=1.2, material=IRON))
    parts.append(beam((-0.42, frame_height - 0.62, 0.42), (0.42, frame_height - 0.66, 0.42),
                      0.03, 0.03, IRON, 1.6))
    for sx, dy in ((-1.0, 0.0), (1.0, -0.04)):
        pan = M.lathe([[0.0, 0.0], [0.16, 0.03], [0.18, 0.08]], 10, uv_scale=1.6,
                      material=IRON)
        extras.append(pan.translate(sx * 0.42, frame_height - 0.94 + dy, 0.42))
        for k in range(3):
            angle = math.pi * 2.0 * k / 3
            parts.append(M.tube(np.array([
                [sx * 0.42 + math.cos(angle) * 0.16, frame_height - 0.86 + dy, 0.42 + math.sin(angle) * 0.16],
                [sx * 0.42, frame_height - 0.64 + dy, 0.42]]), [0.006, 0.006],
                segments=4, uv_scale=1.2, material=IRON))
        heap = M.icosphere(0.09, 1, material=AMBER)
        heap.scale(1.0, 0.5, 1.0)
        extras.append(heap.translate(sx * 0.42, frame_height - 0.90 + dy, 0.42))
    tray = basket(0.30, 0.20, seed + 3, contents=AMBER)
    result = group(M.merge(parts, TIMBER_DARK), *extras)
    result.add(tray.translate(-0.8, 0.97, -0.1))
    for piece in bench.parts:
        result.add(piece)
    result.add(basket(0.28, 0.36, seed + 5, contents=AMBER).translate(1.5, 0.0, 0.35))
    return result


def fishing_gear(seed: int = 0) -> MeshGroup:
    rng = Rng(seed)
    parts = []
    extras = []
    # drying rack with nets
    for sx in (-1.0, 1.0):
        parts.append(post(sx * 1.4, 0.0, 0.0, 2.0, 0.10, TIMBER_DARK))
    parts.append(beam((-1.5, 2.0, 0.0), (1.5, 2.0, 0.0), 0.09, 0.09, TIMBER_DARK, 1.4))
    net = M.box((2.6, 1.25, 0.03), center=(0.0, 1.32, 0.0), uv_scale=2.6,
                material=CLOTH)
    extras.append(net)
    for i in range(3):
        trap = M.lathe([[0.0, 0.0], [0.22, 0.10], [0.24, 0.42], [0.10, 0.52], [0.0, 0.54]],
                       9, uv_scale=1.8, material=THATCH)
        trap.rotate_z(math.pi * 0.5)
        extras.append(trap.translate(-1.0 + i * 0.9, 0.22, 0.55))
    return group(M.merge(parts, TIMBER_DARK), *extras)


def rowing_boat(length: float = 4.2, beam_width: float = 1.4, seed: int = 0) -> M.Mesh:
    """Clinker-built boat hull with thwarts - moored at the landings."""
    sections = []
    rows = 11
    for i in range(rows):
        t = i / (rows - 1)
        taper = math.sin(math.pi * (0.12 + 0.76 * t))
        half_width = beam_width * 0.5 * taper
        depth = 0.55 * (0.55 + 0.55 * taper)
        ring = []
        points = 9
        for k in range(points):
            u = k / (points - 1)
            angle = math.pi * u
            ring.append([-length * 0.5 + length * t,
                         depth * (1.0 - math.sin(angle)) * 1.0,
                         -half_width + 2.0 * half_width * u])
        sections.append(np.array(ring))
    hull = M.loft(sections, closed_rings=False, uv_scale=0.9, material=TIMBER_GREY)
    parts = [hull]
    for t in (0.32, 0.55, 0.78):
        parts.append(M.box((0.22, 0.06, beam_width * 0.82),
                           center=(-length * 0.5 + length * t, 0.42, 0.0),
                           uv_scale=1.6, material=TIMBER))
    parts.append(M.box((length * 0.96, 0.08, 0.14), center=(0.0, 0.52, 0.0),
                       uv_scale=1.4, material=TIMBER_DARK))
    merged = M.merge(parts, TIMBER_GREY)
    merged.recompute_normals(75.0)
    return merged


def dock(length: float = 12.0, width: float = 3.2, height: float = 1.2,
         seed: int = 0, posts: int = 5) -> MeshGroup:
    rng = Rng(seed)
    deck = plank_floor(length * 0.5, width * 0.5, height, 0.14, 16, TIMBER_GREY,
                       seed=seed)
    parts = []
    for i in range(posts):
        x = -length * 0.5 + length * (i + 0.5) / posts
        for sz in (-1.0, 1.0):
            pile = M.cylinder(0.17, 0.15, height + 2.4, 7, uv_scale=0.9,
                              material="bark_dark")
            parts.append(pile.translate(x, -2.4, sz * (width * 0.5 - 0.22)))
        parts.append(M.box((0.18, 0.22, width), center=(x, height - 0.20, 0.0),
                           uv_scale=1.4, material=TIMBER_DARK))
    extras = []
    for i in range(3):
        bollard = M.cylinder(0.13, 0.11, 0.55, 7, uv_scale=1.4, material=TIMBER_DARK)
        extras.append(bollard.translate(-length * 0.35 + i * length * 0.35,
                                        height, width * 0.5 - 0.35))
    result = group(M.merge(parts, TIMBER_GREY), *extras)
    result.add_walk(deck)
    return result


def fence(length: float = 4.0, height: float = 1.15, seed: int = 0,
          style: str = "split") -> M.Mesh:
    rng = Rng(seed)
    parts = []
    posts = max(2, int(length / 1.5) + 1)
    for i in range(posts):
        x = -length * 0.5 + length * i / (posts - 1)
        parts.append(M.cylinder(0.09, 0.075, height * float(rng.uniform(0.94, 1.06)), 6,
                                uv_scale=1.2, material="bark_dark").translate(x, 0, 0))
    if style == "split":
        for y in (height * 0.36, height * 0.74):
            rail = M.cylinder(0.055, 0.05, length, 6, uv_scale=0.9, material=TIMBER_GREY)
            rail.rotate_z(math.pi * 0.5)
            parts.append(rail.translate(-length * 0.5, y, 0.0))
    else:
        pickets = int(length / 0.22)
        for i in range(pickets):
            x = -length * 0.5 + length * (i + 0.5) / pickets
            parts.append(M.box((0.08, height * 0.9, 0.04),
                               center=(x, height * 0.45, 0.0), uv_scale=1.8,
                               material=TIMBER_GREY))
        for y in (height * 0.28, height * 0.72):
            parts.append(M.box((length, 0.07, 0.06), center=(0.0, y, 0.0),
                               uv_scale=1.6, material=TIMBER_DARK))
    return M.merge(parts, TIMBER_GREY)


def signpost(seed: int = 0, arms: int = 2) -> MeshGroup:
    parts = [M.cylinder(0.09, 0.08, 2.35, 7, uv_scale=1.2, material=TIMBER_DARK)]
    boards = []
    for i in range(arms):
        y = 2.05 - i * 0.34
        board = M.box((0.95, 0.22, 0.05), center=(0.55, y, 0.0), uv_scale=2.0,
                      material=CARVED)
        boards.append(board.rotate_y(1.1 * i))
    return group(M.merge(parts, TIMBER_DARK), M.merge(boards, CARVED))


def well(radius: float = 0.95, seed: int = 0) -> MeshGroup:
    parts = [M.lathe([[radius, 0.0], [radius, 0.86], [radius - 0.22, 0.92],
                      [radius - 0.22, 0.0]], 16, uv_scale=1.0, material=RUBBLE)]
    for sx in (-1.0, 1.0):
        parts.append(post(sx * (radius - 0.1), 0.0, 0.86, 1.9, 0.13, TIMBER_DARK))
    parts.append(beam((-radius, 2.76, 0.0), (radius, 2.76, 0.0), 0.12, 0.12,
                      TIMBER_DARK, 1.4))
    canopy = M.gable_roof(radius * 2.6, radius * 2.0, 0.6, 0.24, 0.08, uv_scale=1.6,
                          material=SHINGLE)
    parts.append(canopy.translate(0.0, 2.82, 0.0))
    drum = M.cylinder(0.14, 0.14, radius * 1.3, 8, uv_scale=1.4, material=TIMBER)
    drum.rotate_z(math.pi * 0.5)
    parts.append(drum.translate(-radius * 0.65, 2.42, 0.0))
    bucket = M.lathe([[0.0, 0.0], [0.16, 0.02], [0.18, 0.26], [0.16, 0.28]], 9,
                     uv_scale=1.6, material=TIMBER)
    rope = M.tube(np.array([[0.0, 2.40, 0.0], [0.0, 1.55, 0.0]]), [0.012, 0.012],
                  segments=4, uv_scale=1.2, material=IRON)
    water = M.lathe([[0.0, 0.0], [radius - 0.24, 0.0]], 14, uv_scale=0.6,
                    material="water_pool")
    return group(M.merge(parts, RUBBLE), bucket.translate(0.0, 1.27, 0.0), rope,
                 water.translate(0.0, 0.45, 0.0))


def brazier(seed: int = 0) -> MeshGroup:
    bowl = M.lathe([[0.0, 0.0], [0.38, 0.10], [0.44, 0.34], [0.40, 0.40]], 12,
                   uv_scale=1.4, material=IRON)
    legs = []
    for i in range(3):
        angle = math.pi * 2.0 * i / 3
        legs.append(M.tube(np.array([[math.cos(angle) * 0.30, 0.0, math.sin(angle) * 0.30],
                                     [math.cos(angle) * 0.16, 0.55, math.sin(angle) * 0.16]]),
                           [0.045, 0.04], segments=5, uv_scale=1.4, material=IRON))
    embers = M.icosphere(0.30, 1, material=AMBER)
    embers.scale(1.0, 0.35, 1.0)
    return group(M.merge([bowl.translate(0.0, 0.55, 0.0)] + legs, IRON),
                 embers.translate(0.0, 0.72, 0.0))


def hanging_lantern(seed: int = 0, drop: float = 0.7) -> MeshGroup:
    chain = M.tube(np.array([[0.0, 0.0, 0.0], [0.0, -drop, 0.0]]), [0.012, 0.012],
                   segments=4, uv_scale=1.2, material=IRON)
    housing = M.lathe([[0.0, 0.0], [0.14, 0.05], [0.16, 0.26], [0.11, 0.38], [0.0, 0.42]],
                      6, uv_scale=1.4, material=IRON)
    glow = M.icosphere(0.115, 1, material=AMBER)
    return group(chain, housing.translate(0.0, -drop - 0.42, 0.0),
                 glow.translate(0.0, -drop - 0.20, 0.0))


def amber_lump(radius: float = 0.30, seed: int = 0) -> M.Mesh:
    lump = M.icosphere(radius, 1, material=AMBER)
    lump.jitter(radius * 0.22, seed=seed)
    lump.scale(1.0, 0.72, 1.15)
    lump.recompute_normals(65.0)
    return lump


# --------------------------------------------------------------------------
# natural dressing
# --------------------------------------------------------------------------

def boulder(radius: float = 1.1, seed: int = 0, material: str = "cliff_rock",
            subdivisions: int = 1) -> M.Mesh:
    rock = M.icosphere(radius, subdivisions, material=material)
    rock.jitter(radius * 0.26, seed=seed)
    rock.scale(1.0, float(0.55 + (seed % 7) * 0.06), 1.0)
    rock.project_uv_triplanar(0.55)
    rock.recompute_normals(62.0)
    return rock


def rock_cluster(radius: float = 2.0, count: int = 5, seed: int = 0,
                 material: str = "cliff_rock") -> M.Mesh:
    rng = Rng(seed)
    parts = []
    for i in range(count):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0, radius))
        size = float(rng.uniform(0.30, 0.95)) * radius * 0.55
        rock = boulder(size, seed + i * 13, material, subdivisions=1)
        rock.rotate_y(float(rng.uniform(0, math.pi * 2)))
        parts.append(rock.translate(math.cos(angle) * r, -size * 0.30,
                                    math.sin(angle) * r))
    return M.merge(parts, material)


def mushroom_cluster(seed: int = 0, count: int = 4, material: str = AMBER) -> M.Mesh:
    rng = Rng(seed)
    parts = []
    for i in range(count):
        scale = float(rng.uniform(0.06, 0.17))
        stem = M.cylinder(scale * 0.28, scale * 0.22, scale * 1.6, 5, uv_scale=2.0,
                          material="timber_grey")
        cap = M.lathe([[0.0, scale * 1.5], [scale * 0.9, scale * 1.15],
                       [scale * 0.95, scale * 0.95], [0.0, scale * 0.90]],
                      6, uv_scale=2.0, material=material)
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0.0, 0.45))
        piece = M.merge([stem, cap], material)
        parts.append(piece.translate(math.cos(angle) * r, 0.0, math.sin(angle) * r))
    return M.merge(parts, material)


def undergrowth_patch(radius: float = 1.0, count: int = 5, seed: int = 0,
                      height: float = 0.85) -> M.Mesh:
    """Crossed alpha cards of ferns and grass, randomised so patches never repeat."""
    rng = Rng(seed)
    parts = []
    for i in range(count):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0.0, radius))
        cx, cz = math.cos(angle) * r, math.sin(angle) * r
        scale = float(rng.uniform(0.7, 1.3))
        cell_u = 0.5 * int(rng.integers(0, 2))
        cell_v = 0.5 * int(rng.integers(0, 2))
        for plane in range(2):
            yaw = float(rng.uniform(0, math.pi)) + plane * math.pi * 0.5
            w = 0.85 * scale
            h = height * scale
            positions = [(-w, 0.0, 0.0), (w, 0.0, 0.0), (w, h, 0.0), (-w, h, 0.0)]
            uvs = [[cell_u, cell_v + 0.5], [cell_u + 0.5, cell_v + 0.5],
                   [cell_u + 0.5, cell_v], [cell_u, cell_v]]
            card = M.Mesh(np.asarray(positions), np.tile([0.0, 0.0, 1.0], (4, 1)),
                          np.asarray(uvs), None, np.asarray([0, 1, 2, 0, 2, 3], np.int64),
                          "undergrowth")
            card.rotate_y(yaw)
            parts.append(card.translate(cx, 0.0, cz))
    return M.merge(parts, "undergrowth")


def leaf_drift(radius: float = 1.6, seed: int = 0) -> M.Mesh:
    """A raised drift of fallen leaves banked against roots and walls.

    Kept at the coarsest subdivision on purpose: it is a low mound of ground
    seen from above, and there are hundreds of them.
    """
    rng = Rng(seed)
    drift = M.icosphere(radius, 1, material="forest_floor")
    drift.scale(1.0, 0.16, 0.7)
    drift.jitter(radius * 0.10, seed=seed)
    drift.project_uv_triplanar(0.9)
    drift.recompute_normals(120.0)
    drift.rotate_y(float(rng.uniform(0, math.pi * 2)))
    return drift


def banner(width: float = 0.7, height: float = 2.2, seed: int = 0,
           material: str = CLOTH) -> M.Mesh:
    """A hanging cloth with a curved lower edge and a little wind in it."""
    rows, cols = 7, 4
    positions, uvs, indices = [], [], []
    rng = Rng(seed)
    phase = float(rng.uniform(0, math.pi * 2))
    for r in range(rows + 1):
        for c in range(cols + 1):
            u = c / cols
            v = r / rows
            wave = math.sin(u * math.pi * 2.0 + phase) * 0.06 * v
            drop = 0.0 if v < 0.82 else -(v - 0.82) * height * 0.5 * abs(math.sin(u * math.pi * 3))
            positions.append([(u - 0.5) * width, -v * height + drop, wave])
            uvs.append([u, v * 2.2])
    for r in range(rows):
        for c in range(cols):
            a = r * (cols + 1) + c
            indices.extend([a, a + cols + 1, a + cols + 2, a, a + cols + 2, a + 1])
    cloth = M.Mesh(np.asarray(positions), np.zeros((len(positions), 3)),
                   np.asarray(uvs), None, np.asarray(indices, np.int64), material)
    cloth.recompute_normals(180.0)
    return cloth
