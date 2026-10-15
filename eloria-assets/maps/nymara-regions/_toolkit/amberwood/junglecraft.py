"""Terraced-jungle kit: stairs, terraces, jade architecture and root bridges.

Written for Verdant Stair against its ten-panel detail board, but parameterised
on material throughout - the way `crystalcraft` is - so any region with cut
terraces, a sink pool or a rope-and-plank crossing can use these pieces rather
than copying them.

What is here and what is not: Amberwood's kits already carry rope suspension
bridges (`treecraft.suspension_walkway`), canopy platforms, multi-arch stone
bridges (`stonework.high_bridge`), falling water and colonnades, and this module
does not duplicate any of them. It adds the seven things the board shows that
none of them can build:

    grand_stair          the monumental balustraded flight, board panel 2
    cenote_stair         a helical stair descending a sink pool, panel 3
    root_bridge          banyan roots carrying a plank deck, panel 4
    stilt_hut            a thatched house on posts over a deck, panel 6
    plank_walkway        a railed timber walk on posts, panels 6 and 9
    jade_gate            the water-shrine gateway, panel 7
    pagoda               the tiered jade-and-gilt roof of the terrace pavilions
    relief_panel         the carved spiral-meander slab, panel 10
    terrace_wall         the mossy retaining wall every terrace edge needs

Every walkable surface is registered with `add_walk`, so the client's grounding
ray snaps to a tread or a deck and never to the top of a balustrade or a roof.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .architecture import (IRON, THATCH, TIMBER, TIMBER_DARK, TIMBER_GREY,
                           beam, plank_floor, post, railing, roof)
from .noise import Rng
from .stonework import MeshGroup, group

# Verdant Stair's own palette. Callers override these for another region.
STONE = "verdant_terrace_stone"
MOSSY = "verdant_mossy_stone"
WET = "verdant_wet_limestone"
CLIFF = "verdant_limestone_cliff"
JADE = "verdant_jade"
CARVED_JADE = "verdant_carved_jade"
ROPE = "verdant_rope"
GILT = "gilt_brass"
FROND = "verdant_frond"
VINE = "verdant_vine"


def _weather(piece: M.Mesh, amount: float, seed: int) -> M.Mesh:
    """Knock the machine-perfect edges off a stone solid."""
    piece.jitter(amount, seed=seed)
    piece.recompute_normals(58.0)
    return piece


# --------------------------------------------------------------------------
# terraces and stairs
# --------------------------------------------------------------------------
def terrace_wall(length: float, height: float, seed: int = 0,
                 material: str = MOSSY, batter: float = 0.10,
                 coping: bool = True, vines: float = 0.55) -> MeshGroup:
    """A terrace's retaining face: battered coursed stone, coping, weep holes.

    Runs along X with its face toward +Z, foot at y = 0. Battered - leaning
    back as it rises - because a dead-vertical retaining wall of this height
    reads as a modern concrete panel, and every terrace in the concept leans.
    """
    rng = Rng(seed)
    stone_parts: list[M.Mesh] = []
    courses = max(3, int(height / 0.85))
    course_height = height / courses
    for index in range(courses):
        y = index * course_height
        inset = batter * (y / max(height, 1e-6)) * height * 0.25
        depth = 1.05 - inset * 0.5
        # uv_scale here is texture tiles per metre. At 0.8 a 0.85 m course
        # shows two thirds of a tile vertically against nineteen repeats along
        # a 24 m wall, and the stone reads as vertical stripes. 0.25 puts one
        # tile - five drawn courses - across four metres, which lines the
        # drawn coursing up with the built one.
        block = M.box((length, course_height * 0.97, depth),
                      center=(0.0, y + course_height * 0.5, -inset),
                      uv_scale=0.25, material=material)
        stone_parts.append(block)
        # weep holes: a terrace this wet has to drain, and the dark slots are
        # most of what makes the face read as built rather than as extruded
        if index % 3 == 1:
            count = max(1, int(length / 6.0))
            for k in range(count):
                x = -length * 0.5 + length * (k + 0.5) / count
                x += float(rng.uniform(-0.6, 0.6))
                stone_parts.append(M.box(
                    (0.34, course_height * 0.42, 0.30),
                    center=(x, y + course_height * 0.5, -inset + depth * 0.5 - 0.02),
                    uv_scale=1.4, material=WET))
    if coping:
        stone_parts.append(M.box((length + 0.5, 0.30, 1.35),
                                 center=(0.0, height + 0.15, -batter * height * 0.12),
                                 uv_scale=0.45, material=STONE))
    result = group(_weather(M.merge(stone_parts, material), 0.012, seed))
    if vines > 0.0:
        result.add(vine_curtain(length, height * 0.80, seed=seed + 3,
                                density=vines)
                   .translate(0.0, height * 0.92, 0.62))
    return result


def grand_stair(width: float = 9.0, height: float = 22.0, seed: int = 0,
                landings: int = 2, material: str = STONE,
                balustrade_material: str = MOSSY,
                shrine_material: str = CARVED_JADE,
                length: float | None = None) -> MeshGroup:
    """The monumental flight of board panel 2.

    A broad stair climbing +Z from y = 0, broken by landings, with battered
    cheek walls, a balustrade of turned posts, and a carved shrine post at each
    landing. `mesh.stairs` climbs toward +Z from y = 0 and its run grows with
    the step count, so each flight's own run is computed and the next flight is
    placed past the end of the last - a flight placed at its landing's centre
    climbs back into the mass below it.
    """
    rng = Rng(seed)
    rise = 0.19
    run = 0.34
    flights = landings + 1
    per_flight = max(4, int(round(height / rise / flights)))
    landing_depth = width * 0.55
    if length is not None:
        rise = height / (per_flight * flights)
        run = (length - landings * landing_depth) / (per_flight * flights)
        if run < 0.28:
            raise ValueError("surveyed stair is too short for safe treads")

    stone_parts: list[M.Mesh] = []
    walk_parts: list[M.Mesh] = []
    z = 0.0
    y = 0.0
    for index in range(flights):
        steps = per_flight
        if length is None:
            flight = M.stairs(width, rise, run, steps, uv_scale=1.3, material=material)
        else:
            from . import routecraft as RC
            flight = RC.stair_flight(width, steps * rise, steps * run, steps, material)
        walk_parts.append(flight.copy().translate(0.0, y, z))
        flight_run = steps * run
        # cheek walls carrying the balustrade, one either side
        for sign in (-1.0, 1.0):
            cheek = M.box((0.52, 1.05, flight_run + 0.2),
                          center=(sign * (width * 0.5 + 0.26),
                                  0.0, z + flight_run * 0.5),
                          uv_scale=0.9, material=balustrade_material)
            # rake the cheek wall with the flight
            cheek.transform(np.array([
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, rise / run, y + steps * rise * 0.5 + 0.5
                 - (z + flight_run * 0.5) * rise / run],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0]]))
            stone_parts.append(cheek)
        y += steps * rise
        z += flight_run
        if index < flights - 1:
            deck = M.box((width, 0.34, landing_depth),
                         center=(0.0, y - 0.17, z + landing_depth * 0.5),
                         uv_scale=1.3, material=material)
            walk_parts.append(deck)
            # The landing needs a mass under it or the stair floats - a 22 m
            # flight at this pitch runs nearly forty metres out from the cliff
            # foot, so that mass is tall. Built as courses rather than as one
            # block: a fourteen-metre blank slab is what filled half the first
            # capture pass, and it is the single largest surface a player sees
            # standing at the foot of the stair.
            if length is None:
                support = max(y - 0.5, 0.4)
                courses = max(2, int(support / 0.95))
                course_height = support / courses
                for course in range(courses):
                    inset = 0.16 * (1.0 - course / courses)
                    stone_parts.append(M.box(
                        (width + 1.0 + inset * 2.0, course_height * 0.97,
                         landing_depth + 0.4 + inset * 2.0),
                        center=(0.0, course * course_height + course_height * 0.5,
                                z + landing_depth * 0.5),
                        uv_scale=0.30, material=balustrade_material))
            z += landing_depth

    result = group(_weather(M.merge(stone_parts, balustrade_material), 0.010, seed))

    # balustrade: turned posts and a continuous rail, both sides, raked
    y = 0.0
    z = 0.0
    posts: list[M.Mesh] = []
    for index in range(flights):
        steps = per_flight
        flight_run = steps * run
        count = max(3, int(flight_run / 1.6))
        for k in range(count + 1):
            t = k / count
            for sign in (-1.0, 1.0):
                shaft = M.lathe([[0.0, 0.0], [0.11, 0.06], [0.075, 0.32],
                                 [0.105, 0.52], [0.07, 0.80], [0.10, 0.92],
                                 [0.0, 1.02]], 8, uv_scale=1.4,
                                material=balustrade_material)
                posts.append(shaft.translate(
                    sign * (width * 0.5 + 0.26),
                    y + steps * rise * t + 1.05, z + flight_run * t))
        y += steps * rise
        z += flight_run
        if index < flights - 1:
            z += landing_depth
    result.add(M.merge(posts, balustrade_material))

    # shrine posts at the landings: the carved jade markers of the panel
    y = 0.0
    z = 0.0
    for index in range(flights - 1):
        steps = per_flight
        y += steps * rise
        z += steps * run
        for sign in (-1.0, 1.0):
            result.add(shrine_post(2.6, seed=seed + index * 7 + int(sign) + 1,
                                   material=shrine_material)
                       .translate(sign * (width * 0.5 + 1.15), y - 0.34,
                                  z + landing_depth * 0.5))
        z += landing_depth

    result.add_walk(M.merge(walk_parts, material))
    return result


def shrine_post(height: float = 2.6, seed: int = 0,
                material: str = CARVED_JADE, cap: str = GILT) -> MeshGroup:
    """A carved marker post: stepped plinth, relief shaft, gilt finial."""
    rng = Rng(seed)
    parts = [
        M.box((0.78, 0.22, 0.78), center=(0.0, 0.11, 0.0), uv_scale=1.0,
              material=material),
        M.box((0.62, 0.18, 0.62), center=(0.0, 0.31, 0.0), uv_scale=1.0,
              material=material),
        M.box((0.46, height - 0.72, 0.46),
              center=(0.0, 0.40 + (height - 0.72) * 0.5, 0.0),
              uv_scale=1.6, material=material),
        M.box((0.58, 0.16, 0.58), center=(0.0, height - 0.24, 0.0),
              uv_scale=1.0, material=material),
    ]
    finial = M.lathe([[0.0, 0.0], [0.17, 0.09], [0.12, 0.26], [0.19, 0.36],
                      [0.0, 0.62]], 8, uv_scale=1.6, material=cap)
    return group(M.merge(parts, material),
                 finial.translate(0.0, height - 0.16, 0.0))


def cenote_stair(radius: float = 11.0, depth: float = 16.0, seed: int = 0,
                 turns: float = 1.35, width: float = 2.4,
                 material: str = MOSSY, wet_material: str = WET) -> MeshGroup:
    """The helical stair descending a sink pool, board panel 3.

    Cut into the wall of the shaft rather than free-standing: each tread is
    carried on the solid ring behind it, so from the rim you see a stone ramp
    wound round the inside of a cylinder, which is what the panel shows. The
    lowest quarter turn uses the wet material - it is below the splash line.
    """
    rng = Rng(seed)
    steps = max(24, int(depth / 0.24))
    treads: list[M.Mesh] = []
    body: list[M.Mesh] = []
    for index in range(steps):
        t = index / steps
        angle = turns * math.pi * 2.0 * t
        y = -depth * t
        wet = t > 0.76
        tread = M.box((width, 0.22, 2.0 * math.pi * radius / steps * 1.4),
                      center=(radius - width * 0.5, y, 0.0), uv_scale=1.3,
                      material=wet_material if wet else material)
        treads.append(tread.rotate_y(angle))
        # the mass the tread is cut from: a wedge of the shaft wall
        backing = M.box((1.5, 1.05, 2.0 * math.pi * radius / steps * 1.5),
                        center=(radius + 0.6, y - 0.55, 0.0), uv_scale=0.8,
                        material=wet_material if wet else material)
        body.append(backing.rotate_y(angle))
        # outer parapet, broken here and there the way a ruin's is
        if index % 2 == 0 and float(rng.uniform()) > 0.18:
            wall = M.box((0.34, 0.86, 2.0 * math.pi * radius / steps * 1.4),
                         center=(radius - width - 0.05, y + 0.54, 0.0),
                         uv_scale=1.2, material=material)
            body.append(wall.rotate_y(angle))

    # the shaft wall itself, so the stair is inside something
    rings = []
    for k in range(9):
        t = k / 8.0
        r = radius + 1.9 + 0.55 * math.sin(t * math.pi)
        ring = []
        for j in range(24):
            angle = math.pi * 2.0 * j / 24
            ring.append([math.cos(angle) * r, -depth * t - 0.4,
                         math.sin(angle) * r])
        rings.append(np.array(ring))
    shaft = M.loft(rings, closed_rings=True, uv_scale=0.7, material=CLIFF)
    shaft.flip_winding()          # seen from the inside
    shaft.recompute_normals(70.0)

    result = group(_weather(M.merge(body, material), 0.014, seed), shaft)
    result.add_walk(M.merge(treads, material))
    return result


# --------------------------------------------------------------------------
# crossings
# --------------------------------------------------------------------------
def root_bridge(start, end, seed: int = 0, width: float = 2.2,
                sag: float = 0.9, roots: int = 5,
                root_material: str = "bark_pale",
                deck_material: str = TIMBER) -> MeshGroup:
    """Banyan roots grown across a gorge carrying a plank deck, board panel 4.

    The roots are the structure and the deck is laid on top of them, so the
    roots dip below the walking line and rise past it at the abutments - a deck
    sitting on a flat bundle of tubes reads as a pipe rack.
    """
    rng = Rng(seed)
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    span = end - start
    length = float(np.linalg.norm(span[[0, 2]]))
    if length < 1e-6:
        return group()
    axis = span / max(float(np.linalg.norm(span)), 1e-9)
    side = np.cross(axis, np.array([0.0, 1.0, 0.0]))
    side /= max(float(np.linalg.norm(side)), 1e-9)

    steps = max(10, int(length / 0.8))
    centre_line = []
    for index in range(steps + 1):
        t = index / steps
        point = start + span * t
        point[1] -= sag * math.sin(math.pi * t)
        centre_line.append(point)

    root_parts: list[M.Mesh] = []
    for k in range(roots):
        offset = (k / max(roots - 1, 1) - 0.5) * width * 1.15
        wobble_seed = seed + k * 13
        path = []
        radii = []
        for index, point in enumerate(centre_line):
            t = index / steps
            wobble = float(Rng(wobble_seed + index).normal(0.0, 0.10))
            # roots braid: they cross the centre line rather than running parallel
            braid = math.sin(t * math.pi * 3.0 + k * 1.7) * width * 0.16
            lateral = side * (offset + braid + wobble)
            drop = 0.35 * math.sin(math.pi * t) + wobble * 0.4
            path.append(point + lateral - np.array([0.0, drop, 0.0]))
            taper = 0.30 + 0.34 * (1.0 - math.sin(math.pi * t) * 0.75)
            radii.append(taper)
        root_parts.append(M.tube(np.array(path), radii, segments=6,
                                 uv_scale=1.0, material=root_material))
        # a hanging aerial root every so often, which is the banyan tell
        for index in range(3, steps - 2, max(3, steps // 5)):
            anchor = np.array(path[index])
            drop = float(Rng(wobble_seed + index * 3).uniform(1.4, 4.2))
            root_parts.append(M.tube(
                np.array([anchor, anchor - np.array([0.0, drop, 0.0])]),
                [0.10, 0.055], segments=4, uv_scale=1.2,
                material=root_material))

    deck_parts: list[M.Mesh] = []
    for index in range(steps):
        a = np.array(centre_line[index])
        b = np.array(centre_line[index + 1])
        centre = (a + b) * 0.5
        direction = b - a
        plank = M.box((float(np.linalg.norm(direction)) * 0.95, 0.09, width),
                      uv_scale=1.6, material=deck_material)
        yaw = math.atan2(direction[2], direction[0])
        pitch = math.asin(float(np.clip(
            direction[1] / max(float(np.linalg.norm(direction)), 1e-9), -1.0, 1.0)))
        plank.rotate_z(pitch).rotate_y(-yaw)
        deck_parts.append(plank.translate(*centre))

    # a rope handline on each side, slung from the roots
    rope_parts: list[M.Mesh] = []
    for sign in (-1.0, 1.0):
        line = np.array([p + side * sign * (width * 0.5 + 0.10)
                         + np.array([0.0, 1.00 - 0.22 * math.sin(
                             math.pi * (i / steps)), 0.0])
                         for i, p in enumerate(centre_line)])
        rope_parts.append(M.tube(line, np.full(line.shape[0], 0.045), segments=5,
                                 uv_scale=1.2, material=ROPE))
        for index in range(0, steps + 1, 3):
            top = line[index]
            bottom = centre_line[index] + side * sign * (width * 0.5 + 0.10)
            rope_parts.append(M.tube(np.array([bottom, top]), [0.022, 0.022],
                                     segments=4, uv_scale=1.2, material=ROPE))

    result = group(M.merge(root_parts, root_material),
                   M.merge(rope_parts, ROPE))
    result.add_walk(M.merge(deck_parts, deck_material))
    return result


def plank_walkway(start, end, seed: int = 0, width: float = 1.8,
                  height: float = 0.0, posts_every: float = 3.2,
                  rails: bool = True, ground=None,
                  material: str = TIMBER) -> MeshGroup:
    """A railed timber walk carried on posts, board panels 6 and 9.

    Unlike `treecraft.suspension_walkway` this does not hang: it is a level
    deck on legs, which is what a terrace edge and a canopy village use. Pass
    `ground(x, z)` and every post is cut to the real ground under it instead of
    to a guessed length.
    """
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    span = end - start
    length = float(np.linalg.norm(span[[0, 2]]))
    if length < 1e-6:
        return group()
    axis = span / max(float(np.linalg.norm(span)), 1e-9)
    side = np.cross(axis, np.array([0.0, 1.0, 0.0]))
    side /= max(float(np.linalg.norm(side)), 1e-9)
    yaw = math.atan2(span[2], span[0])

    deck_parts: list[M.Mesh] = []
    frame_parts: list[M.Mesh] = []
    steps = max(4, int(length / 0.9))
    for index in range(steps):
        t0 = index / steps
        t1 = (index + 1) / steps
        a = start + span * t0
        b = start + span * t1
        centre = (a + b) * 0.5
        plank = M.box((float(np.linalg.norm(b - a)) * 0.94, 0.10, width),
                      uv_scale=1.6, material=material)
        plank.rotate_y(-yaw)
        deck_parts.append(plank.translate(centre[0], centre[1] + height,
                                          centre[2]))

    count = max(2, int(length / posts_every))
    for index in range(count + 1):
        t = index / count
        point = start + span * t
        deck_y = point[1] + height
        for sign in (-1.0, 1.0):
            foot = point + side * sign * (width * 0.5 - 0.16)
            base = float(ground(foot[0], foot[2])) if ground else foot[1] - 3.0
            leg = max(deck_y - base, 0.35)
            frame_parts.append(M.box((0.22, leg, 0.22),
                                     center=(foot[0], base + leg * 0.5, foot[2]),
                                     uv_scale=1.2, material=TIMBER_DARK))
            if leg > 2.0:
                # a diagonal brace, or a tall bent reads as a stilt walker
                frame_parts.append(beam(
                    np.array([foot[0], base + leg * 0.25, foot[2]]),
                    np.array([point[0], deck_y - 0.14, point[2]]),
                    0.14, 0.14, TIMBER_DARK, 1.0))
        frame_parts.append(M.box((width + 0.3, 0.16, 0.20),
                                 center=(point[0], deck_y - 0.13, point[2]),
                                 uv_scale=1.2, material=TIMBER_DARK)
                           .rotate_y(0.0))

    result = group(M.merge(frame_parts, TIMBER_DARK))
    if rails:
        rail_parts: list[M.Mesh] = []
        for sign in (-1.0, 1.0):
            line = np.array([start + span * (i / steps)
                             + side * sign * (width * 0.5)
                             + np.array([0.0, height + 0.98, 0.0])
                             for i in range(steps + 1)])
            rail_parts.append(M.tube(line, np.full(line.shape[0], 0.055),
                                     segments=5, uv_scale=1.2,
                                     material=TIMBER_GREY))
            for index in range(0, steps + 1, 2):
                top = line[index]
                bottom = top - np.array([0.0, 0.98, 0.0])
                rail_parts.append(M.tube(np.array([bottom, top]), [0.05, 0.045],
                                         segments=4, uv_scale=1.2,
                                         material=TIMBER_GREY))
        result.add(M.merge(rail_parts, TIMBER_GREY))
    result.add_walk(M.merge(deck_parts, material))
    return result


# --------------------------------------------------------------------------
# buildings
# --------------------------------------------------------------------------
def stilt_hut(seed: int = 0, width: float = 4.6, depth: float = 4.0,
              stilt: float = 2.4, ground=None,
              material: str = TIMBER, thatch: str = THATCH) -> MeshGroup:
    """A thatched house on posts over its own deck, board panel 6.

    The deck is wider than the house so there is a verandah to stand on, and
    the roof is a steep hip with a deep overhang - a jungle roof sheds water
    away from the walls, and the overhang is most of the silhouette.
    """
    rng = Rng(seed)
    half_x, half_z = width * 0.5, depth * 0.5
    deck_x, deck_z = half_x + 0.9, half_z + 0.7
    parts: list[M.Mesh] = []
    walk: list[M.Mesh] = []

    deck = plank_floor(deck_x, deck_z, stilt, 0.14, 9, material, seed=seed)
    walk.append(deck)
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            foot_x = sx * (deck_x - 0.35)
            foot_z = sz * (deck_z - 0.35)
            base = float(ground(foot_x, foot_z)) if ground else -0.4
            leg = max(stilt - base, 0.5)
            parts.append(M.box((0.26, leg, 0.26),
                               center=(foot_x, base + leg * 0.5, foot_z),
                               uv_scale=1.2, material=TIMBER_DARK))
    # a mid post on the long sides so a 5 m deck is not on four legs
    for sx in (-1.0, 1.0):
        base = float(ground(sx * (deck_x - 0.35), 0.0)) if ground else -0.4
        leg = max(stilt - base, 0.5)
        parts.append(M.box((0.22, leg, 0.22),
                           center=(sx * (deck_x - 0.35), base + leg * 0.5, 0.0),
                           uv_scale=1.2, material=TIMBER_DARK))

    from .architecture import door, framed_wall, window
    wall_height = 2.25
    for sign in (-1.0, 1.0):
        wall = framed_wall(width, wall_height, 0.20, TIMBER_DARK, TIMBER_GREY,
                           studs=3, seed=seed + 1)
        parts.append(wall.translate(0.0, stilt + 0.14, sign * half_z))
        side = framed_wall(depth, wall_height, 0.20, TIMBER_DARK, TIMBER_GREY,
                           studs=3, seed=seed + 2)
        side.rotate_y(math.pi * 0.5)
        parts.append(side.translate(sign * half_x, stilt + 0.14, 0.0))
    parts.append(window(0.80, 0.95, 0.13).translate(0.0, stilt + 1.15,
                                                    half_z + 0.09))
    parts.append(door(0.92, 1.90, 0.10).translate(0.0, stilt + 0.14,
                                                  -half_z - 0.06))

    # thatch: a steep hip on a ring of rafters, overhanging the verandah
    eave = stilt + 0.14 + wall_height
    apex = eave + max(width, depth) * 0.52
    rings = [
        np.array([[sx * (half_x + 1.05), eave - 0.12, sz * (half_z + 0.95)]
                  for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
        np.array([[sx * (half_x * 0.62), eave + (apex - eave) * 0.55,
                   sz * (half_z * 0.62)]
                  for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
        np.array([[sx * 0.16, apex, sz * 0.16]
                  for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
    ]
    hip = M.loft(rings, closed_rings=True, uv_scale=1.1, material=thatch)
    parts.append(hip)
    ridge = M.box((0.42, 0.30, 0.42), center=(0.0, apex + 0.10, 0.0),
                  uv_scale=1.4, material=thatch)
    parts.append(ridge)
    for sign in (-1.0, 1.0):
        parts.append(beam(np.array([sign * (half_x + 1.0), eave - 0.10, 0.0]),
                          np.array([sign * half_x * 0.3, apex - 0.4, 0.0]),
                          0.12, 0.12, TIMBER_DARK, 1.0))

    result = group(M.merge(parts, material))
    result.add_walk(M.merge(walk, material))
    return result


def pagoda(radius: float = 4.2, tiers: int = 3, height: float = 7.0,
           seed: int = 0, columns: int = 8, material: str = JADE,
           roof_material: str = JADE, trim: str = GILT,
           base_material: str = STONE) -> MeshGroup:
    """A tiered jade pavilion: the roof shape that repeats across the concept.

    Every terrace in the aerial carries one of these. Tiered rather than domed,
    because a dome reads as classical and the painting's roofs are stacked
    flares with upturned eaves.
    """
    parts: list[M.Mesh] = []
    trim_parts: list[M.Mesh] = []
    walk: list[M.Mesh] = []

    # stepped base
    base = M.lathe([[radius + 1.30, 0.0], [radius + 1.30, 0.26],
                    [radius + 0.95, 0.28], [radius + 0.95, 0.52],
                    [radius + 0.62, 0.54], [radius + 0.62, 0.70],
                    [0.0, 0.72]], 20, uv_scale=0.8, material=base_material)
    parts.append(base)
    walk.append(M.cylinder(radius + 0.60, radius + 0.60, 0.12, 20,
                           uv_scale=1.2, material=base_material)
                .translate(0.0, 0.66, 0.0))

    shaft = height / tiers
    for index in range(columns):
        angle = math.pi * 2.0 * index / columns
        pillar = M.lathe([[0.30, 0.0], [0.32, 0.10], [0.26, shaft * 0.92],
                          [0.34, shaft], [0.30, shaft + 0.16]], 10,
                         uv_scale=0.9, material=material)
        parts.append(pillar.translate(math.cos(angle) * radius, 0.72,
                                      math.sin(angle) * radius))

    eave_y = 0.72 + shaft
    for tier in range(tiers):
        spread = radius * (1.42 - 0.30 * tier / max(tiers - 1, 1))
        inner = radius * (0.86 - 0.26 * tier / max(tiers - 1, 1))
        lift = 0.95 - 0.12 * tier
        # the flare: a ring that rises as it goes out, so the eave turns up
        rings = [
            np.array([[math.cos(math.pi * 2.0 * k / 24) * spread,
                       eave_y + 0.34,
                       math.sin(math.pi * 2.0 * k / 24) * spread]
                      for k in range(24)]),
            np.array([[math.cos(math.pi * 2.0 * k / 24) * spread * 0.90,
                       eave_y - 0.10,
                       math.sin(math.pi * 2.0 * k / 24) * spread * 0.90]
                      for k in range(24)]),
            np.array([[math.cos(math.pi * 2.0 * k / 24) * inner,
                       eave_y + lift,
                       math.sin(math.pi * 2.0 * k / 24) * inner]
                      for k in range(24)]),
        ]
        parts.append(M.loft(rings, closed_rings=True, uv_scale=1.4,
                            material=roof_material))
        # gilt eave band and corner spurs
        trim_parts.append(M.lathe(
            [[spread, eave_y + 0.30], [spread + 0.16, eave_y + 0.36],
             [spread, eave_y + 0.44]], 24, uv_scale=1.6, material=trim))
        for k in range(4):
            angle = math.pi * 0.5 * k + math.pi * 0.25
            spur = M.tube(np.array([
                [math.cos(angle) * spread, eave_y + 0.34, math.sin(angle) * spread],
                [math.cos(angle) * (spread + 0.55), eave_y + 0.62,
                 math.sin(angle) * (spread + 0.55)],
                [math.cos(angle) * (spread + 0.72), eave_y + 1.05,
                 math.sin(angle) * (spread + 0.72)]]),
                [0.10, 0.075, 0.045], segments=5, uv_scale=1.4, material=trim)
            trim_parts.append(spur)
        eave_y += lift + 0.55
        if tier < tiers - 1:
            drum = M.cylinder(inner * 0.92, inner * 0.88, 0.66, 16,
                              uv_scale=1.2, material=material)
            parts.append(drum.translate(0.0, eave_y - 0.66, 0.0))

    finial = M.lathe([[0.0, 0.0], [0.26, 0.14], [0.15, 0.42], [0.24, 0.58],
                      [0.10, 0.92], [0.0, 1.30]], 10, uv_scale=1.6, material=trim)
    trim_parts.append(finial.translate(0.0, eave_y - 0.2, 0.0))

    result = group(_weather(M.merge(parts, material), 0.006, seed),
                   M.merge(trim_parts, trim))
    result.add_walk(M.merge(walk, base_material))
    return result


def jade_gate(span: float = 6.4, height: float = 7.2, seed: int = 0,
              material: str = JADE, carved: str = CARVED_JADE,
              trim: str = GILT) -> MeshGroup:
    """The water-shrine gateway of board panel 7.

    Two carved piers on stepped plinths carrying a double lintel with upturned
    ends, a relief tablet between them, and a guardian figure at each foot.
    Built as solids: the panel's gate is heavy stonework, not a frame.
    """
    rng = Rng(seed)
    parts: list[M.Mesh] = []
    carved_parts: list[M.Mesh] = []
    trim_parts: list[M.Mesh] = []
    half = span * 0.5

    for sign in (-1.0, 1.0):
        x = sign * half
        parts.append(M.box((1.35, 0.34, 1.35), center=(x, 0.17, 0.0),
                           uv_scale=0.9, material=material))
        parts.append(M.box((1.10, 0.26, 1.10), center=(x, 0.47, 0.0),
                           uv_scale=0.9, material=material))
        pier = M.box((0.86, height - 0.60, 0.86),
                     center=(x, 0.60 + (height - 0.60) * 0.5, 0.0),
                     uv_scale=1.1, material=carved)
        carved_parts.append(pier)
        # the guardian: a seated figure on its own low plinth, as in the panel
        carved_parts.append(_guardian(seed=seed + int(sign) + 3, material=carved)
                            .translate(x + sign * 1.55, 0.0, 0.55))

    # lintels: a deep lower beam and a lighter upper one with upturned ends
    for index, (y, thickness, over) in enumerate(
            ((height - 0.10, 0.52, 1.30), (height + 0.72, 0.34, 1.85))):
        beam_mesh = M.box((span + over * 2.0, thickness, 0.74),
                          center=(0.0, y, 0.0), uv_scale=1.0, material=carved)
        carved_parts.append(beam_mesh)
        for sign in (-1.0, 1.0):
            tip = M.tube(np.array([
                [sign * (half + over), y + thickness * 0.2, 0.0],
                [sign * (half + over + 0.52), y + thickness * 0.55, 0.0],
                [sign * (half + over + 0.70), y + thickness * 1.15, 0.0]]),
                [0.20, 0.14, 0.08], segments=6, uv_scale=1.4, material=trim)
            trim_parts.append(tip)
        if index == 0:
            tablet = M.box((span * 0.62, 1.05, 0.30),
                           center=(0.0, y + 0.68, 0.0), uv_scale=1.4,
                           material=carved)
            carved_parts.append(tablet)

    # struts between pier and lintel, which is what stops it reading as a table
    for sign in (-1.0, 1.0):
        trim_parts.append(M.tube(np.array([
            [sign * (half - 0.35), height - 1.55, 0.0],
            [sign * (half + 0.55), height - 0.42, 0.0]]),
            [0.12, 0.09], segments=5, uv_scale=1.2, material=trim))

    result = group(_weather(M.merge(parts, material), 0.008, seed),
                   _weather(M.merge(carved_parts, carved), 0.006, seed + 1),
                   M.merge(trim_parts, trim))
    return result


def _guardian(seed: int = 0, height: float = 1.75,
              material: str = CARVED_JADE) -> M.Mesh:
    """A seated guardian figure - blocked out, not sculpted."""
    rng = Rng(seed)
    parts = [
        M.box((1.05, 0.34, 1.05), center=(0.0, 0.17, 0.0), uv_scale=1.0,
              material=material),
        # folded legs
        M.box((0.86, 0.32, 0.62), center=(0.0, 0.50, 0.10), uv_scale=1.2,
              material=material),
        # torso, leaning very slightly back
        M.box((0.66, height * 0.46, 0.50),
              center=(0.0, 0.66 + height * 0.23, -0.04), uv_scale=1.2,
              material=material),
        # shoulders and head
        M.box((0.82, 0.22, 0.46), center=(0.0, 0.66 + height * 0.47, -0.04),
              uv_scale=1.2, material=material),
        M.box((0.34, 0.40, 0.34), center=(0.0, 0.66 + height * 0.60, -0.04),
              uv_scale=1.4, material=material),
    ]
    for sign in (-1.0, 1.0):
        parts.append(M.box((0.20, height * 0.40, 0.20),
                           center=(sign * 0.40, 0.68 + height * 0.22, 0.06),
                           uv_scale=1.3, material=material))
    piece = M.merge(parts, material)
    piece.jitter(0.012, seed=seed)
    piece.recompute_normals(52.0)
    return piece


def relief_panel(width: float = 2.0, height: float = 1.2, depth: float = 0.26,
                 seed: int = 0, material: str = CARVED_JADE) -> M.Mesh:
    """The carved spiral-meander slab of board panel 10.

    The meander itself is in the material's normal and colour maps; this is the
    slab it is cut into, with a chamfered border so it reads as a set panel and
    not as a decal on a wall.
    """
    parts = [
        M.box((width, height, depth * 0.62), center=(0.0, 0.0, 0.0),
              uv_scale=1.0, material=material),
        M.box((width + 0.16, height + 0.16, depth * 0.38),
              center=(0.0, 0.0, -depth * 0.30), uv_scale=0.9, material=material),
    ]
    piece = M.merge(parts, material)
    piece.jitter(0.006, seed=seed)
    piece.recompute_normals(58.0)
    return piece


# --------------------------------------------------------------------------
# vegetation that is architecture-adjacent
# --------------------------------------------------------------------------
def vine_curtain(width: float, drop: float, seed: int = 0, density: float = 0.6,
                 material: str = VINE) -> M.Mesh:
    """A hanging curtain of lianas: alpha-cut cards, crossed so it has depth.

    Cards are crossed rather than laid in one plane because a single plane of
    alpha vanishes edge-on, which is exactly the angle a player walking a
    terrace sees a cliff face from.
    """
    rng = Rng(seed)
    count = max(2, int(width * density))
    parts = []
    for index in range(count):
        x = -width * 0.5 + width * (index + 0.5) / count
        x += float(rng.uniform(-width / count * 0.4, width / count * 0.4))
        length = drop * float(rng.uniform(0.45, 1.0))
        card_width = float(rng.uniform(0.9, 1.9))
        for angle in (0.0, math.pi * 0.5):
            card = M.quad([(-card_width * 0.5, 0.0, 0.0),
                           (card_width * 0.5, 0.0, 0.0),
                           (card_width * 0.5, -length, 0.0),
                           (-card_width * 0.5, -length, 0.0)],
                          uv_scale=1.0, material=material)
            card.rotate_y(angle + float(rng.uniform(-0.3, 0.3)))
            parts.append(card.translate(x, 0.0, float(rng.uniform(-0.35, 0.35))))
    piece = M.merge(parts, material)
    piece.sanitise_normals()
    return piece


def frond_cluster(radius: float = 1.6, count: int = 6, seed: int = 0,
                  rise: float = 1.9, material: str = FROND) -> M.Mesh:
    """A rosette of frond cards: tree-fern crown, palm head or ground clump.

    Cards spring from a common point and tilt outward, so the silhouette is a
    shuttlecock rather than a disc. The centre vertex is offset from the
    cluster centre on purpose - a card whose centre coincides with the origin
    produces a zero-length normal, which glTF forbids and Godot shades black.
    """
    rng = Rng(seed)
    parts = []
    for index in range(count):
        angle = math.pi * 2.0 * index / count + float(rng.uniform(-0.25, 0.25))
        tilt = float(rng.uniform(0.55, 1.15))
        length = radius * float(rng.uniform(0.80, 1.25))
        card_width = length * float(rng.uniform(0.34, 0.52))
        card = M.quad([(-card_width * 0.5, 0.02, 0.0),
                       (card_width * 0.5, 0.02, 0.0),
                       (card_width * 0.5, 0.02, length),
                       (-card_width * 0.5, 0.02, length)],
                      uv_scale=1.0, material=material)
        card.rotate_x(-tilt)
        card.rotate_y(angle)
        parts.append(card.translate(0.0, rise * float(rng.uniform(0.85, 1.0)), 0.0))
        # a second card rolled about the frond axis gives the crown thickness
        twin = card.copy()
        twin.rotate_y(0.22)
        parts.append(twin)
    piece = M.merge(parts, material)
    piece.sanitise_normals()
    return piece


def tree_fern(height: float = 4.6, seed: int = 0, crown: float = 2.4,
              trunk_material: str = "bark_dark",
              frond_material: str = FROND) -> MeshGroup:
    """A tree fern: a fibrous trunk with old frond bases and a single crown."""
    rng = Rng(seed)
    path = []
    radii = []
    steps = 7
    lean = float(rng.uniform(-0.10, 0.10))
    for index in range(steps + 1):
        t = index / steps
        path.append([lean * height * t * t, height * t,
                     float(rng.normal(0.0, 0.06))])
        radii.append(0.26 - 0.10 * t)
    trunk = M.tube(np.array(path), radii, segments=8, uv_scale=1.1,
                   material=trunk_material)
    # the ring of shed frond bases that makes a fern trunk read as a fern trunk
    stubs = []
    for index in range(9):
        t = 0.25 + 0.70 * index / 9.0
        angle = index * 2.4
        y = height * t
        stub = M.box((0.14, 0.10, 0.34),
                     center=(0.24, y, 0.0), uv_scale=1.4, material=trunk_material)
        stubs.append(stub.rotate_y(angle))
    top = np.array(path[-1])
    crown_mesh = frond_cluster(crown, count=7, seed=seed + 5, rise=0.0,
                               material=frond_material)
    crown_mesh.translate(top[0], top[1], top[2])
    return group(M.merge([trunk] + stubs, trunk_material), crown_mesh)


def banyan_roots(radius: float = 3.2, count: int = 9, height: float = 5.5,
                 seed: int = 0, material: str = "bark_pale") -> M.Mesh:
    """The curtain of aerial roots under a banyan crown, board panels 4 and 6.

    Roots drop from the crown, meet the ground and thicken into props. They are
    what tells a banyan from any other big tree at silhouette distance.
    """
    rng = Rng(seed)
    parts = []
    for index in range(count):
        angle = math.pi * 2.0 * index / count + float(rng.uniform(-0.3, 0.3))
        reach = radius * float(rng.uniform(0.45, 1.15))
        top = np.array([math.cos(angle) * reach * 0.55, height,
                        math.sin(angle) * reach * 0.55])
        foot = np.array([math.cos(angle) * reach, 0.0, math.sin(angle) * reach])
        path = []
        radii = []
        steps = 6
        for k in range(steps + 1):
            t = k / steps
            point = top + (foot - top) * t
            point[0] += float(rng.normal(0.0, 0.14))
            point[2] += float(rng.normal(0.0, 0.14))
            path.append(point)
            # thick at the crown, thin in the middle, flared where it lands
            radii.append(0.20 - 0.11 * math.sin(math.pi * t) + 0.20 * t ** 3)
        parts.append(M.tube(np.array(path), radii, segments=6, uv_scale=1.0,
                            material=material))
    piece = M.merge(parts, material)
    piece.recompute_normals(66.0)
    return piece


def terrace_house(seed: int = 0, width: float = 6.4, depth: float = 5.2,
                  storeys: int = 2, material: str = STONE,
                  upper: str = TIMBER, roof_material: str = JADE,
                  trim: str = GILT, entrance_steps: bool = False) -> MeshGroup:
    """A town house for a terrace city: stone below, timber above, tiered roof.

    Amberwood's `forest_lodge` and `manor` are steep-shingled temperate timber
    buildings, and a street of them in a jade jungle reads as the wrong region
    entirely. This is the same idea in this region's vocabulary: a coursed
    stone ground floor that matches the terrace it stands on, a lighter timber
    upper storey set back behind a verandah, and the flared tiered roof that
    repeats across the whole concept.
    """
    rng = Rng(seed)
    from .architecture import door, framed_wall, window

    half_x, half_z = width * 0.5, depth * 0.5
    parts: list[M.Mesh] = []
    trim_parts: list[M.Mesh] = []
    walk: list[M.Mesh] = []

    # plinth and ground-floor mass, built as a solid with a doorway recess
    plinth = M.box((width + 0.9, 0.45, depth + 0.9), center=(0.0, 0.22, 0.0),
                   uv_scale=0.5, material=MOSSY)
    parts.append(plinth)
    walk.append(M.box((width + 0.9, 0.10, depth + 0.9),
                      center=(0.0, 0.45, 0.0), uv_scale=0.9, material=MOSSY))
    if entrance_steps:
        from . import routecraft as RC
        walk.append(RC.stair_flight(2.2, 0.50, 1.8, 3, MOSSY)
                    .translate(0, 0, -half_z - 0.45 - 1.8))
    ground_height = 2.6
    for sign in (-1.0, 1.0):
        parts.append(M.box((width, ground_height, 0.36),
                           center=(0.0, 0.45 + ground_height * 0.5,
                                   sign * half_z),
                           uv_scale=0.45, material=material))
        parts.append(M.box((0.36, ground_height, depth),
                           center=(sign * half_x, 0.45 + ground_height * 0.5,
                                   0.0),
                           uv_scale=0.45, material=material))
    parts.append(door(1.00, 2.05, 0.12).translate(0.0, 0.45, -half_z - 0.10))
    for sign in (-1.0, 1.0):
        parts.append(window(0.85, 1.00, 0.14)
                     .translate(sign * width * 0.28, 1.35, half_z + 0.10))
    # a carved jade band at the head of the ground floor
    trim_parts.append(M.box((width + 0.5, 0.26, depth + 0.5),
                            center=(0.0, 0.45 + ground_height + 0.13, 0.0),
                            uv_scale=0.7, material=CARVED_JADE))

    eave = 0.45 + ground_height + 0.26
    if storeys > 1:
        upper_height = 2.15
        inset = 0.45
        for sign in (-1.0, 1.0):
            wall = framed_wall(width - inset * 2.0, upper_height, 0.20,
                               TIMBER_DARK, upper, studs=3, seed=seed + 1)
            parts.append(wall.translate(0.0, eave, sign * (half_z - inset)))
            side = framed_wall(depth - inset * 2.0, upper_height, 0.20,
                               TIMBER_DARK, upper, studs=3, seed=seed + 2)
            side.rotate_y(math.pi * 0.5)
            parts.append(side.translate(sign * (half_x - inset), eave, 0.0))
        # the verandah the upper storey is set back behind
        walk.append(M.box((width + 0.2, 0.12, depth + 0.2),
                          center=(0.0, eave + 0.06, 0.0), uv_scale=1.2,
                          material=upper))
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                # post() is (x, z, base_y, height): passing eave as the third
                # argument put the verandah posts underground
                parts.append(post(sx * (half_x - 0.10), sz * (half_z - 0.10),
                                  eave, upper_height + 0.30, 0.16,
                                  TIMBER_DARK))
        eave += upper_height + 0.30

    # the tiered flared roof: two rings, the eave turning up at the corners
    for tier in range(2):
        spread_x = (half_x + 1.15) * (1.0 - 0.28 * tier)
        spread_z = (half_z + 1.15) * (1.0 - 0.28 * tier)
        lift = 1.05 - 0.20 * tier
        rings = [
            np.array([[sx * spread_x, eave + 0.30, sz * spread_z]
                      for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
            np.array([[sx * spread_x * 0.94, eave - 0.14, sz * spread_z * 0.94]
                      for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
            np.array([[sx * spread_x * 0.42, eave + lift, sz * spread_z * 0.42]
                      for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]),
        ]
        parts.append(M.loft(rings, closed_rings=True, uv_scale=1.2,
                            material=roof_material))
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                trim_parts.append(M.tube(np.array([
                    [sx * spread_x, eave + 0.30, sz * spread_z],
                    [sx * (spread_x + 0.40), eave + 0.58, sz * (spread_z + 0.40)],
                    [sx * (spread_x + 0.52), eave + 0.92, sz * (spread_z + 0.52)]]),
                    [0.085, 0.06, 0.038], segments=5, uv_scale=1.4,
                    material=trim))
        eave += lift + 0.42

    result = group(_weather(M.merge(parts, material), 0.006, seed),
                   M.merge(trim_parts, trim))
    result.add_walk(M.merge(walk, MOSSY))
    return result


def stair_profile(width, height, length, landings=2):
    """Local (distance, height) stations, including the flat rest landings."""
    flights = landings + 1
    landing_depth = width * 0.55
    flight_run = (length - landings * landing_depth) / flights
    if min(width, height, flight_run) <= 0:
        raise ValueError("stair needs positive flights and landing room")
    stations = [(0.0, 0.0)]
    distance = 0.0
    for index in range(flights):
        distance += flight_run
        y = height * (index + 1) / flights
        stations.append((distance, y))
        if index < landings:
            distance += landing_depth
            stations.append((distance, y))
    return np.asarray(stations)
