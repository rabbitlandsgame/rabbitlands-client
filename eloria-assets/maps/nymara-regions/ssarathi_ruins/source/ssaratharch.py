"""Ssarathi Ruins' architectural kit.

The serpent city's own pieces. Everything the shared toolkit already has -
columns, balustrades, lamp posts, ruin fragments, waterfalls, retaining walls -
is used from `stonework.py` rather than rebuilt here; what follows is only what
the concept needs and the shared kit has not got.

Two conventions the whole kit follows, both of them runtime contracts:

* Anything a player can stand on goes through `MeshGroup.add_walk`, so it is
  exported under the `Walk_` navigation prefix and the client's downward ray
  can find it. Structural geometry never does. Mark a whole temple as a walk
  surface and the ray snaps actors onto its roof.
* Everything is built with its base at y = 0 and its origin at the centre of
  its footprint, so a placement is `(x, ground_height, z)` and nothing has to
  know the terrain.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import stonework as SW
from amberwood import trees as TR

import ssarathikit as SK

JADE = SK.JADE_ASHLAR
SCALE_TILE = SK.JADE_SCALE
GILT = SK.GILT
CARVED = SK.SERPENT_STONE
PAVING = SK.JADE_PAVING
STONE = SK.STONE
ROCK = SK.ROCK
RUBBLE = SK.RUBBLE
TIMBER = SK.TIMBER
CANVAS = SK.CANVAS
VINE = SK.VINE
LILY = SK.LILY
PALM = SK.PALM
FOLIAGE = SK.FOLIAGE
WATER = SK.WATER_FALL


def _facet(mesh):
    """Harden the edges of a low-segment lathe or cylinder.

    `mesh.lathe` and `mesh.cylinder` smooth-shade around the axis, which is
    right for a round column and wrong for the square-sectioned prisms this kit
    builds with `segments=4`. Smooth-shaded, a four-sided prism gets normals
    pointing at its corners, so every flat face shades as if it were curving
    away from the light - and the whole temple rendered near-black beside
    paving made of the same stone. Re-splitting at 30 degrees makes the four
    faces flat, which is what they are.
    """
    mesh.recompute_normals(30.0)
    mesh.sanitise_normals()
    return mesh


def _rng(seed: int) -> TR.Rng:
    """Seeded RNG, guarded against a negative seed.

    Kit pieces derive per-instance seeds arithmetically (`seed + int(sign)`),
    which goes negative at seed 0 and numpy's `default_rng` rejects that. The
    mask keeps every derived seed deterministic - it is not `hash()`, which is
    salted per interpreter run and would make the build irreproducible.
    """
    return TR.Rng(int(seed) & 0x7FFFFFFF)


# --------------------------------------------------------------- ornament
def sun_disc(radius: float = 1.8, seed: int = 0,
             material: str = GILT) -> M.Mesh:
    """The region's signature motif: a rayed sun face on a disc.

    Panels 3, 7 and 10 all carry one. Built as a lathe for the boss plus real
    ray geometry, because a flat disc with a texture on it reads as a coin at
    any distance where the motif matters.
    """
    parts = [
        M.lathe([(0.0, 0.0), (radius * 0.94, 0.0), (radius * 0.98, 0.10),
                 (radius * 0.86, 0.20), (radius * 0.52, 0.30),
                 (radius * 0.30, 0.38), (0.0, 0.44)],
                segments=28, material=material),
    ]
    rays = 16
    for i in range(rays):
        angle = 2.0 * math.pi * i / rays
        length = radius * (0.42 if i % 2 else 0.62)
        blade = M.extrude([(-radius * 0.07, 0.0), (radius * 0.07, 0.0),
                           (0.0, length)], radius * 0.16, material=material)
        blade.rotate_y(-angle)
        blade.transform(M.rotation_x(-math.pi / 2.0))
        blade.translate(math.cos(angle) * radius * 0.88, 0.0,
                        math.sin(angle) * radius * 0.88)
        parts.append(blade)
    # the face: brow, eyes and mouth as shallow relief
    for offset, size in ((-0.30, 0.16), (0.30, 0.16)):
        eye = M.icosphere(radius * size, 1, material=CARVED)
        eye.scale(1.0, 0.5, 1.0)
        eye.translate(radius * offset, 0.44, radius * 0.10)
        parts.append(eye)
    mouth = M.box((radius * 0.52, radius * 0.10, radius * 0.16),
                  center=(0.0, 0.46, -radius * 0.34), material=CARVED)
    parts.append(mouth)
    out = M.merge(parts, material)
    out.recompute_normals(52.0)
    out.sanitise_normals()
    return out


def shell_boss(radius: float = 0.9, material: str = CARVED) -> M.Mesh:
    """The scallop of panel 10, used as a keystone and a wall boss."""
    ribs = 11
    profile = []
    for i in range(9):
        s = i / 8.0
        profile.append((radius * math.sin(s * math.pi * 0.5),
                        radius * 0.44 * (1.0 - math.cos(s * math.pi * 0.5))))
    shell = M.lathe(profile, segments=ribs * 2, arc=math.pi, material=material)
    # flute the shell by pushing alternate meridians in
    positions = shell.positions
    angle = np.arctan2(positions[:, 2], positions[:, 0])
    flute = 1.0 + 0.10 * np.cos(angle * ribs)
    positions[:, 0] *= flute
    positions[:, 2] *= flute
    shell.recompute_normals(48.0)
    shell.sanitise_normals()
    return shell


def stone_face(size: float = 1.4, seed: int = 0,
               material: str = CARVED) -> M.Mesh:
    """A carved guardian face, sunk into a wall or standing on a plinth."""
    rng = _rng(seed)
    parts = [M.box((size * 1.3, size * 1.6, size * 0.55),
                   center=(0.0, size * 0.8, 0.0), material=material)]
    # brow
    parts.append(M.box((size * 1.15, size * 0.22, size * 0.30),
                       center=(0.0, size * 1.12, size * 0.22), material=material))
    for sign in (-1.0, 1.0):
        socket = M.icosphere(size * 0.20, 1, material=material)
        socket.scale(1.0, 0.72, 0.6)
        socket.translate(sign * size * 0.31, size * 0.96, size * 0.24)
        parts.append(socket)
    # nose and jaw
    parts.append(M.box((size * 0.26, size * 0.46, size * 0.34),
                       center=(0.0, size * 0.74, size * 0.26), material=material))
    parts.append(M.box((size * 0.72, size * 0.16, size * 0.26),
                       center=(0.0, size * 0.46, size * 0.24), material=material))
    # a gilt headdress band, the one warm note
    parts.append(M.box((size * 1.38, size * 0.16, size * 0.60),
                       center=(0.0, size * 1.40, 0.0), material=GILT))
    # Cheek scrolls, a chin and a gilt collar. Panel 10 is a macro shot, and
    # without these the face is a box with three small boxes on one side -
    # which is precisely how it rendered at five metres.
    for sign in (-1.0, 1.0):
        scroll = M.lathe([(0.0, 0.0), (size * 0.20, 0.0), (size * 0.24, size * 0.10),
                          (size * 0.12, size * 0.18), (0.0, size * 0.20)],
                         segments=12, material=material)
        scroll.transform(M.rotation_x(-math.pi / 2.0))
        scroll.translate(sign * size * 0.52, size * 0.80, size * 0.26)
        parts.append(scroll)
        fang = M.cylinder(size * 0.05, 0.0, size * 0.16, segments=5,
                          material=GILT)
        fang.transform(M.rotation_x(math.pi))
        fang.translate(sign * size * 0.16, size * 0.46, size * 0.32)
        parts.append(fang)
    parts.append(M.box((size * 0.92, size * 0.14, size * 0.44),
                       center=(0.0, size * 0.30, size * 0.20), material=GILT))
    parts.append(M.box((size * 0.44, size * 0.26, size * 0.30),
                       center=(0.0, size * 0.20, size * 0.24), material=material))
    out = M.merge(parts, material)
    out.transform(M.rotation_y(float(rng.uniform(-0.05, 0.05))))
    out.recompute_normals(46.0)
    out.sanitise_normals()
    return out


# ---------------------------------------------------------------- columns
def serpent_column(height: float = 5.4, seed: int = 0) -> SW.MeshGroup:
    """A column whose shaft is a coiled serpent - the aerial's S-forms.

    Swept as a tube along a helix rather than a straight cylinder with a
    texture, because the silhouette is the whole point: these read as serpents
    from across the water, which a fluted column never would.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    base_radius = height * 0.13
    out.add(M.cylinder(base_radius * 1.35, base_radius * 1.20, height * 0.09,
                       segments=12, material=JADE)
            .translate(0.0, 0.0, 0.0))

    # Two and a bit turns, not three: at three the coil pitch was tighter than
    # the body was thick and the column read as a drill bit rather than as a
    # snake. A serpent column reads by having few, fat coils and a head.
    turns = 2.15 + float(rng.uniform(-0.25, 0.35))
    steps = 60
    path, radii = [], []
    for i in range(steps + 1):
        s = i / steps
        angle = s * turns * 2.0 * math.pi
        coil = base_radius * (0.80 - 0.34 * s)
        path.append((math.cos(angle) * coil,
                     height * 0.09 + s * height * 0.70,
                     math.sin(angle) * coil))
        # thick at the bottom, tapering, with a belly through the middle
        radii.append(base_radius * (0.56 - 0.26 * s + 0.09 * math.sin(s * math.pi)))
    body = M.tube(np.asarray(path), radii, segments=9, cap_start=True,
                  material=SCALE_TILE)
    out.add(body)

    # the head, reared over the capital
    # The head, reared over the capital and aimed outward along the coil's
    # last tangent, so a pair of columns face down the street rather than at
    # nothing in particular.
    tangent = (path[-1][0] - path[-2][0], path[-1][2] - path[-2][2])
    facing = math.atan2(-tangent[1], tangent[0])
    head = M.icosphere(base_radius * 0.52, 2, material=SCALE_TILE)
    head.scale(1.55, 0.80, 1.0)
    brow = M.box((base_radius * 0.62, base_radius * 0.18, base_radius * 0.70),
                 center=(base_radius * 0.10, base_radius * 0.26, 0.0),
                 material=SCALE_TILE)
    jaw = M.box((base_radius * 0.78, base_radius * 0.16, base_radius * 0.46),
                center=(base_radius * 0.26, -base_radius * 0.20, 0.0),
                material=GILT)
    skull = SW.group(head, brow, jaw)
    skull.rotate_y(facing)
    skull.translate(path[-1][0], path[-1][1] + base_radius * 0.34, path[-1][2])
    out.add(skull)
    for sign in (-1.0, 1.0):
        fang = M.cylinder(base_radius * 0.07, 0.0, base_radius * 0.30,
                          segments=5, material=GILT)
        fang.transform(M.rotation_x(math.pi))
        fang.rotate_y(facing)
        fang.translate(path[-1][0] + math.cos(facing) * base_radius * 0.62
                       + math.sin(facing) * sign * base_radius * 0.16,
                       path[-1][1] + base_radius * 0.12,
                       path[-1][2] - math.sin(facing) * base_radius * 0.62
                       + math.cos(facing) * sign * base_radius * 0.16)
        out.add(fang)

    # the abacus the serpent carries
    # The abacus. The gilt is a thin band around the edge of a jade block, not
    # a plate on top of it: as a full-width plate it was the brightest thing in
    # every capture and the column read as a gold slab floating in the air.
    out.add(M.box((base_radius * 2.0, height * 0.075, base_radius * 2.0),
                  center=(0.0, height * 0.88, 0.0), material=JADE))
    for sign in (-1.0, 1.0):
        out.add(M.box((base_radius * 2.06, height * 0.018, base_radius * 0.16),
                      center=(0.0, height * 0.925, sign * base_radius * 0.98),
                      material=GILT))
        out.add(M.box((base_radius * 0.16, height * 0.018, base_radius * 2.06),
                      center=(sign * base_radius * 0.98, height * 0.925, 0.0),
                      material=GILT))
    return out


def pool_colonnade(radius: float, count: int = 12, height: float = 11.0,
                   seed: int = 0, broken: float = 0.35) -> SW.MeshGroup:
    """The ring of columns around a pool court, panels 5 and 6.

    Column size is derived from the ring's radius, not fixed. At a fixed
    0.30 m shaft and 5.2 m height, a 43 m-radius court's far colonnade was
    0.6 m of stone at 85 m - about one and a half pixels - and both pool-court
    captures came back as an empty paved shelf with water beyond it. A court is
    sized by its colonnade and its colonnade has to be sized back.

    A third of the columns are broken off at varying heights, which is what
    makes a colonnade read as a ruin rather than as a rotunda.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    shaft_radius = max(0.55, radius * 0.028)
    base = shaft_radius * 3.0
    for i in range(count):
        angle = 2.0 * math.pi * i / count
        x, z = math.cos(angle) * radius, math.sin(angle) * radius
        broken_here = float(rng.uniform(0.0, 1.0)) < broken
        h = height * (float(rng.uniform(0.24, 0.62)) if broken_here
                      else float(rng.uniform(0.92, 1.08)))
        out.add(M.box((base, shaft_radius * 0.8, base),
                      center=(x, shaft_radius * 0.4, z), material=JADE))
        shaft = SW.column(h, radius=shaft_radius, flutes=12, material=JADE)
        shaft.translate(x, shaft_radius * 0.8, z)
        out.add(shaft)
        if not broken_here:
            out.add(M.box((base * 0.92, shaft_radius * 0.7, base * 0.92),
                          center=(x, shaft_radius * 0.8 + h, z), material=CARVED))
            out.add(M.box((base * 0.74, shaft_radius * 0.34, base * 0.74),
                          center=(x, shaft_radius * 1.2 + h, z), material=GILT))
            # a serpent finial on some, as the concept's paired columns carry
            if float(rng.uniform(0.0, 1.0)) < 0.34:
                head = M.icosphere(shaft_radius * 0.9, 1, material=SCALE_TILE)
                head.scale(1.5, 0.8, 1.0)
                head.rotate_y(-angle)
                head.translate(x, shaft_radius * 1.6 + h, z)
                out.add(head)
        else:
            rubble = SW.ruin_fragment(seed=seed + i, scale=shaft_radius * 1.6)
            rubble.translate(x + float(rng.uniform(-1.6, 1.6)), 0.0,
                             z + float(rng.uniform(-1.6, 1.6)))
            out.add(rubble)
    return out


def obelisk(height: float = 7.5, seed: int = 0) -> SW.MeshGroup:
    """A slender inscribed spire. The aerial is full of these."""
    rng = _rng(seed)
    out = SW.MeshGroup()
    base = height * 0.09
    out.add(M.box((base * 2.4, base * 0.5, base * 2.4),
                  center=(0.0, base * 0.25, 0.0), material=JADE))
    out.add(M.box((base * 1.9, base * 0.34, base * 1.9),
                  center=(0.0, base * 0.66, 0.0), material=JADE))
    shaft = _facet(M.cylinder(base * 0.78, base * 0.44, height * 0.80,
                              segments=4, material=JADE))
    shaft.rotate_y(math.pi / 4.0)
    shaft.translate(0.0, base * 0.83, 0.0)
    out.add(shaft)
    cap = _facet(M.cylinder(base * 0.44, 0.0, height * 0.11, segments=4,
                            material=GILT))
    cap.rotate_y(math.pi / 4.0)
    cap.translate(0.0, base * 0.83 + height * 0.80, 0.0)
    out.add(cap)
    # a band of gilt glyph work partway up
    band = _facet(M.cylinder(base * 0.66, base * 0.62, height * 0.05,
                             segments=4, material=GILT))
    band.rotate_y(math.pi / 4.0)
    band.translate(0.0, base * 0.83 + height * 0.34, 0.0)
    out.add(band)
    out.transform(M.rotation_y(float(rng.uniform(0.0, math.pi * 0.5))))
    return out


def sun_stela(height: float = 12.0, seed: int = 0) -> SW.MeshGroup:
    """Panel 7: a tall slab carrying a gold sun face, on a stepped plinth.

    The stela is walkable at its plinth, so a player can climb to the base of
    the disc; the slab itself is not.
    """
    out = SW.MeshGroup()
    width = height * 0.40
    # stepped plinth - three courses, each one a walk surface
    level = 0.0
    for i, (half, rise) in enumerate(((width * 1.50, 0.30),
                                      (width * 1.18, 0.30),
                                      (width * 0.92, 0.30))):
        step = M.box((half * 2.0, rise, half * 2.0),
                     center=(0.0, level + rise * 0.5, 0.0), material=PAVING)
        out.add_walk(step)
        level += rise
    # the slab: a rounded-top stele
    slab_h = height - level
    slab = M.extrude([(-width * 0.5, -width * 0.16), (width * 0.5, -width * 0.16),
                      (width * 0.5, width * 0.16), (-width * 0.5, width * 0.16)],
                     slab_h * 0.86, material=JADE)
    slab.translate(0.0, level, 0.0)
    out.add(slab)
    crown = M.lathe([(0.0, 0.0), (width * 0.5, 0.0), (width * 0.42, slab_h * 0.10),
                     (0.0, slab_h * 0.15)], segments=18, arc=math.pi,
                    material=JADE)
    crown.scale(1.0, 1.0, 0.32 * width / (width * 0.5))
    crown.translate(0.0, level + slab_h * 0.86, 0.0)
    out.add(crown)
    # The disc on the south face. Sized to nearly fill the slab's width: at
    # 0.44 it was a medallion on a blank stone and panel 7 is a picture of a
    # gold sun face, not of a stele that happens to have one.
    disc = sun_disc(width * 0.62, seed=seed)
    disc.transform(M.rotation_x(math.pi / 2.0))
    disc.translate(0.0, level + slab_h * 0.54, width * 0.17)
    out.add(disc)
    # a gilt border framing it, so the slab is not blank around the disc
    for sign in (-1.0, 1.0):
        out.add(M.box((width * 0.06, slab_h * 0.70, width * 0.10),
                      center=(sign * width * 0.44,
                              level + slab_h * 0.50, width * 0.16),
                      material=GILT))
    out.add(M.box((width * 0.94, slab_h * 0.05, width * 0.10),
                  center=(0.0, level + slab_h * 0.86, width * 0.16),
                  material=GILT))
    # serpent volutes down the slab's edges
    for sign in (-1.0, 1.0):
        path, radii = [], []
        for i in range(21):
            s = i / 20.0
            path.append((sign * (width * 0.5 + 0.10 + 0.16 * math.sin(s * 6.0)),
                         level + slab_h * 0.86 * s, 0.0))
            radii.append(0.16 - 0.06 * s)
        out.add(M.tube(np.asarray(path), radii, segments=7,
                       material=SCALE_TILE))
    return out


# ---------------------------------------------------------------- masonry
def causeway_balustrade(length: float, seed: int = 0,
                        height: float = 1.05) -> SW.MeshGroup:
    """Kerb, posts and rail down one side of a causeway, with gaps.

    Built along +X, centred, so a placement rotates it into the street's
    heading. Sections are missing at intervals - a complete rail on a ruined
    causeway reads as new-built.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    out.add(M.box((length, 0.34, 0.42), center=(0.0, 0.17, 0.0), material=JADE))
    spacing = 2.6
    count = max(int(length / spacing), 2)
    for i in range(count + 1):
        x = -length * 0.5 + i * (length / count)
        if float(rng.uniform(0.0, 1.0)) < 0.18:
            continue
        out.add(M.box((0.30, height, 0.34), center=(x, 0.34 + height * 0.5, 0.0),
                      material=JADE))
        if float(rng.uniform(0.0, 1.0)) < 0.30:
            out.add(M.box((0.22, 0.10, 0.26),
                          center=(x, 0.34 + height + 0.05, 0.0), material=GILT))
    # the rail, in runs that skip the missing posts
    run_start = None
    for i in range(count + 2):
        x = -length * 0.5 + i * (length / count)
        broken = float(rng.uniform(0.0, 1.0)) < 0.22 or i > count
        if not broken and run_start is None:
            run_start = x
        elif broken and run_start is not None:
            span = x - run_start
            if span > 0.5:
                out.add(M.box((span, 0.18, 0.24),
                              center=(run_start + span * 0.5,
                                      0.34 + height * 0.86, 0.0),
                              material=JADE))
            run_start = None
    return out


def arch_bridge(span: float, width: float, rise: float, seed: int = 0) -> SW.MeshGroup:
    """Panel 4's span: a segmental stone bridge over a channel.

    Built along +X with its deck top at y = 0, so a placement puts the deck at
    the causeway level and the arch hangs below it into the water.

    Deliberately **not** `mesh.arch`, which builds a ring in XY and extrudes
    along Z: rotating that 90 degrees for a bridge shows you the barrel end.
    This is a solid elevation whose underside follows the intrados, the same
    approach `stonework.high_bridge` takes, with the deck as a separate walk
    part.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    half = span * 0.5
    deck_thickness = 0.55
    slices = 26

    # two side elevations: a wall whose lower edge is the arch curve
    for sign in (-1.0, 1.0):
        z = sign * (width * 0.5 - 0.22)
        parts = []
        for i in range(slices):
            x0 = -half + span * i / slices
            x1 = -half + span * (i + 1) / slices
            xm = (x0 + x1) * 0.5
            # a segmental curve: full depth at the abutments, rising to the crown
            t = abs(xm) / half
            under = -deck_thickness - rise * (1.0 - t * t)
            floor = -rise - 2.6 - 1.4 * t          # the pier foot, into the water
            if under <= floor:
                continue
            parts.append(M.box((x1 - x0, under - floor, 0.44),
                               center=(xm, (under + floor) * 0.5, z),
                               material=JADE))
        out.add(M.merge(parts, JADE))

    # the deck: the only walkable part
    deck = M.box((span + 1.6, deck_thickness, width),
                 center=(0.0, -deck_thickness * 0.5, 0.0), material=PAVING)
    out.add_walk(deck)

    # abutment blocks at each end, so the deck meets the embankment
    for sign in (-1.0, 1.0):
        out.add(M.box((1.8, rise + 3.4, width + 0.5),
                      center=(sign * (half + 0.6),
                              -deck_thickness - (rise + 3.4) * 0.5, 0.0),
                      material=JADE))

    # balustrades
    for sign in (-1.0, 1.0):
        rail = causeway_balustrade(span * 0.94, seed=seed + int(sign) + 3,
                                   height=0.86)
        rail.translate(0.0, 0.0, sign * (width * 0.5 - 0.20))
        out.add(rail)

    # a keystone shell on each face, and a stone face on one
    for sign in (-1.0, 1.0):
        boss = shell_boss(width * 0.20)
        boss.transform(M.rotation_x(-math.pi / 2.0 * sign))
        boss.translate(0.0, -deck_thickness - rise * 0.30,
                       sign * (width * 0.5 + 0.02))
        out.add(boss)
    if float(rng.uniform(0.0, 1.0)) < 0.6:
        face = stone_face(width * 0.16, seed=seed)
        face.translate(-half * 0.62, -deck_thickness - rise * 0.75,
                       width * 0.5 + 0.10)
        out.add(face)
    return out


def water_gate(span: float = 9.0, height: float = 11.0,
               seed: int = 0) -> SW.MeshGroup:
    """The city's south gate: twin pylons, a lintel and a hanging sun disc.

    Straddles the causeway, so its opening is clear and nothing of it is a walk
    surface - the causeway terrain runs through underneath.
    """
    out = SW.MeshGroup()
    pylon_w = span * 0.34
    for sign in (-1.0, 1.0):
        x = sign * (span * 0.5 + pylon_w * 0.5)
        # a battered pylon, wider at the foot
        pylon = _facet(M.lathe(
            [(pylon_w * 0.78, 0.0), (pylon_w * 0.70, height * 0.30),
             (pylon_w * 0.60, height * 0.72), (pylon_w * 0.64, height * 0.80),
             (pylon_w * 0.58, height * 0.86)], segments=4, material=JADE))
        pylon.rotate_y(math.pi / 4.0)
        pylon.translate(x, 0.0, 0.0)
        out.add(pylon)
        out.add(M.box((pylon_w * 1.55, height * 0.06, pylon_w * 1.55),
                      center=(x, height * 0.88, 0.0), material=CARVED))
        # a serpent coiled up each pylon's outer face
        path, radii = [], []
        for i in range(25):
            s = i / 24.0
            path.append((x + sign * pylon_w * 0.62,
                         height * 0.88 * s,
                         math.sin(s * 5.0) * pylon_w * 0.36))
            radii.append(0.24 - 0.09 * s)
        out.add(M.tube(np.asarray(path), radii, segments=7, material=SCALE_TILE))
        face = stone_face(pylon_w * 0.30, seed=seed + int(sign))
        face.translate(x, height * 0.44, pylon_w * 0.70)
        out.add(face)

    # the lintel
    out.add(M.box((span + pylon_w * 2.6, height * 0.14, pylon_w * 1.2),
                  center=(0.0, height * 0.95, 0.0), material=JADE))
    out.add(M.box((span + pylon_w * 2.9, height * 0.05, pylon_w * 1.4),
                  center=(0.0, height * 1.04, 0.0), material=GILT))
    disc = sun_disc(span * 0.20, seed=seed)
    disc.transform(M.rotation_x(math.pi / 2.0))
    disc.translate(0.0, height * 0.80, pylon_w * 0.62)
    out.add(disc)
    return out


def vault_portal(width: float = 9.0, height: float = 8.5,
                 seed: int = 0) -> SW.MeshGroup:
    """Panel 3: a recessed portal closed by a great circular sun-disc door.

    The panel's subject is the *door*, so the disc is the largest single piece
    of geometry here and everything else frames it.
    """
    out = SW.MeshGroup()
    depth = width * 0.42
    # the surround: a stepped reveal, each order set back
    for i, (w, h, d) in enumerate((
            (width * 1.34, height * 1.10, depth * 0.10),
            (width * 1.16, height * 1.02, depth * 0.28),
            (width * 1.02, height * 0.96, depth * 0.46))):
        out.add(M.box((w, 0.42, d), center=(0.0, h, d * 0.5 - depth * 0.5),
                      material=JADE))
        for sign in (-1.0, 1.0):
            out.add(M.box((0.42, h, d),
                          center=(sign * w * 0.5, h * 0.5, d * 0.5 - depth * 0.5),
                          material=JADE if i else CARVED))
    # the back wall the disc sits against
    out.add(M.box((width * 1.02, height * 0.96, 0.5),
                  center=(0.0, height * 0.48, -depth * 0.5), material=JADE))
    # the door
    disc = sun_disc(width * 0.40, seed=seed + 5)
    disc.transform(M.rotation_x(math.pi / 2.0))
    disc.translate(0.0, height * 0.48, -depth * 0.5 + 0.30)
    out.add(disc)
    # a concentric gilt ring around it
    ring = M.lathe([(width * 0.44, 0.0), (width * 0.50, 0.0),
                    (width * 0.50, 0.22), (width * 0.44, 0.22)],
                   segments=32, material=GILT)
    ring.transform(M.rotation_x(math.pi / 2.0))
    ring.translate(0.0, height * 0.48, -depth * 0.5 + 0.24)
    out.add(ring)
    # flanking guardian faces
    for sign in (-1.0, 1.0):
        face = stone_face(width * 0.13, seed=seed + int(sign) * 7)
        face.translate(sign * width * 0.60, height * 0.30, depth * 0.20)
        out.add(face)
    # the threshold, walkable, so the player can stand in the portal
    out.add_walk(M.box((width * 1.02, 0.30, depth),
                       center=(0.0, 0.15, 0.0), material=PAVING))
    return out


def square_frustum(bottom: float, top: float, height: float,
                   material: str = JADE) -> M.Mesh:
    """A solid battered box: a square frustum with both ends capped.

    Not `mesh.lathe(..., segments=4)`. A lathe is a surface of revolution - it
    has no caps - so a "stage" built that way is a hollow four-sided shell you
    can see straight through, and the first ziggurat was four such shells with a
    staircase running up the middle of nothing. `mesh.loft` with `cap_ends`
    gives the solid that mass depends on.
    """
    sections = []
    for radius, y in ((bottom, 0.0), (top, height)):
        sections.append(np.array([(-radius, y, -radius), (radius, y, -radius),
                                  (radius, y, radius), (-radius, y, radius)],
                                 dtype=np.float64))
    solid = M.loft(sections, closed_rings=True, cap_ends=True, material=material)
    return _facet(solid)


def ziggurat_temple(base: float = 72.0, tiers: int = 5,
                    tier_height: float = 7.0, seed: int = 0,
                    include_roof: bool = True) -> SW.MeshGroup:
    """Panel 2: the great stepped temple, and the region's one real silhouette.

    The terrain carries three walkable tiers of precinct under this; the mesh is
    the built mass standing on them - five battered stages, a cornice on each, a
    stair up the south face, corner obelisks, serpent volutes flanking the
    stair, and the summit shrine with its sun finial.

    Only the stair treads and the summit floor are walk surfaces. Marking the
    stages walkable would let the client grounding ray put an actor on a cornice
    thirty metres up.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    half = base * 0.5
    level = 0.0
    widths = []
    for i in range(tiers):
        shrink = 1.0 - i * (0.62 / max(tiers, 1))
        w = half * shrink
        widths.append(w)

        out.add(square_frustum(w, w * 0.93, tier_height * 0.86, JADE)
                .translate(0.0, level, 0.0))
        # the cornice: a wider slab in scale tiling, which is the horizontal
        # banding the concept's temple reads by from across the basin
        out.add(M.box((w * 2.10, tier_height * 0.16, w * 2.10),
                      center=(0.0, level + tier_height * 0.92, 0.0),
                      material=SCALE_TILE))
        out.add(M.box((w * 2.14, tier_height * 0.04, w * 2.14),
                      center=(0.0, level + tier_height * 0.845, 0.0),
                      material=GILT))

        if i < tiers - 1:
            for sx in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    spire = obelisk(tier_height * 1.05,
                                    seed=seed + i * 4 + int(sx + sz * 2) + 8)
                    spire.translate(sx * w * 0.86,
                                    level + tier_height * 0.97, sz * w * 0.86)
                    out.add(spire)
            if float(rng.uniform(0.0, 1.0)) < 0.7:
                face = stone_face(min(2.2, w * 0.09), seed=seed + 20 + i)
                face.translate(w * 0.55, level + tier_height * 0.22, w + 0.2)
                out.add(face)
        level += tier_height

    # One continuous, supported ascent. The old independent flights overlap:
    # their10m run exceeds the4.5m tier inset, making higher treads cut across
    # the lower stair. This flight reaches the unchanged summit without jumps.
    run=48.0;steps=72;rise=(level+.32)/steps
    stair=M.stairs(9.0,rise,run/steps,steps,material=PAVING)
    stair.rotate_y(math.pi);stair.translate(0,0,64)
    out.add_walk(stair)
    # The last tread and summit overlap at exactly the same walking height.
    out.add_walk(M.box((9.0,.28,2.3),center=(0,level+.18,15.5),material=PAVING))
    for sign in (-1,1):
        for i in range(steps):
            out.add(M.box((.55,.6,run/steps),center=(sign*4.8,rise*(i+1)+.22,64-(i+.5)*run/steps),material=JADE))

    # the summit shrine
    top = widths[-1] * 0.86
    out.add_walk(M.box((top * 2.0, 0.32, top * 2.0),
                       center=(0.0, level + 0.16, 0.0), material=PAVING))
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            col = SW.column(top * 1.20, radius=top * 0.11, flutes=12,
                            material=JADE)
            col.translate(sx * top * 0.76, level + 0.32, sz * top * 0.76)
            out.add(col)
    if include_roof:
        out.add(ziggurat_summit_roof(base,tiers,tier_height,seed))

    # Vines falling down the stage faces. Each card is hung from a *named*
    # stage, so its x and z are taken from that stage's own width - hung from
    # the base width at every height, as the first version did, the upper cards
    # fell through open air beside a temple that had already tapered away from
    # them, which is exactly how they rendered.
    for i in range(16):
        stage = int(rng.uniform(0, len(widths)))
        w = widths[stage]
        top = stage * tier_height + tier_height * 0.86
        drop = float(rng.uniform(tier_height * 0.7, tier_height * 1.9))
        face = int(rng.uniform(0, 4))
        along = float(rng.uniform(-w * 0.82, w * 0.82))
        offset = w * 1.02
        x, z = ((along, -offset), (along, offset),
                (-offset, along), (offset, along))[face]
        card = M.quad([(-2.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                       (2.0, -drop, 0.0), (-2.0, -drop, 0.0)],
                      material=VINE)
        if face >= 2:
            card.rotate_y(math.pi / 2.0)
        card.translate(x, top, z)
        out.add(card)
    out.sanitise_normals()
    return out


def ziggurat_summit_roof(base=72.0,tiers=5,tier_height=7.0,seed=0):
    """Separate the unchanged summit lid so the gameplay camera can fade it."""
    out=SW.MeshGroup()
    top=base*.5*(1-(tiers-1)*(.62/max(tiers,1)))*.86
    level=tiers*tier_height
    roof_h=top*1.05;cap_y=level+.32+top*1.20
    out.add(M.box((top*2.16,roof_h*.16,top*2.16),
                  center=(0,cap_y+roof_h*.08,0),material=JADE))
    roof=square_frustum(top*1.20,.02,roof_h*.82,SCALE_TILE)
    roof.translate(0,cap_y+roof_h*.16,0);out.add(roof)
    finial=sun_disc(top*.52,seed=seed+11)
    finial.transform(M.rotation_x(math.pi/2))
    finial.translate(0,cap_y+roof_h*.62,top*.10);out.add(finial)
    out.sanitise_normals()
    return out


def ruin_arch_rooted(span: float = 13.0, height: float = 13.5,
                     seed: int = 0) -> SW.MeshGroup:
    """Panel 8: a broken overgrown arch with a strangler root system over it.

    Built in XY and left there, so the barrel runs along Z exactly as
    `mesh.arch` produces it. Rotating that ring 90 degrees for a bridge is the
    trap the production guide names - here the arch faces the camera, which is
    the one orientation it is right for.

    The first version kept only a third of the ring and lost both piers to a
    vertex filter, so it rendered as a smooth grey hook with no masonry in it.
    This keeps three quarters of the ring, gives both piers real coursed mass,
    and breaks the arch by *removing* a wedge near the crown rather than
    everything past a plane.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    half = span * 0.5
    thickness = span * 0.24
    depth = span * 0.42
    rise = height * 0.40

    # the two piers, one broken short, both coursed
    pier_heights = (height * 0.60, height * float(rng.uniform(0.34, 0.52)))
    for sign, pier_h in ((-1.0, pier_heights[0]), (1.0, pier_heights[1])):
        x = sign * (half + thickness * 0.5)
        courses = max(int(pier_h / 1.1), 3)
        for c in range(courses):
            y = c * (pier_h / courses)
            inset = 0.0 if c % 2 else thickness * 0.05
            out.add(M.box((thickness - inset, pier_h / courses * 0.96, depth - inset),
                          center=(x, y + pier_h / courses * 0.5, 0.0),
                          material=JADE))
        # a plinth and an impost band
        out.add(M.box((thickness * 1.30, 0.55, depth * 1.24),
                      center=(x, 0.27, 0.0), material=CARVED))
        out.add(M.box((thickness * 1.22, 0.42, depth * 1.16),
                      center=(x, pier_h + 0.21, 0.0), material=CARVED))

    # the arch ring, springing from the taller pier's impost
    ring = M.arch(span, rise, thickness, depth, segments=18, material=JADE)
    ring.translate(0.0, pier_heights[0] + 0.42, 0.0)
    # Break it: drop a wedge of the ring near the crown, on the side of the
    # short pier, so the arch is open at the top and still lands on both piers.
    positions = ring.positions
    angle = np.arctan2(np.maximum(positions[:, 1] - (pier_heights[0] + 0.42), 0.0),
                       positions[:, 0])
    gap_centre = float(rng.uniform(0.45, 0.95))       # radians from +X
    gap_width = float(rng.uniform(0.30, 0.52))
    keep = np.abs(angle - gap_centre) > gap_width
    faces = ring.indices.reshape(-1, 3)
    faces = faces[keep[faces].all(axis=1)]
    if faces.shape[0]:
        ring.indices = faces.reshape(-1)
        ring.recompute_normals(52.0)
        ring.sanitise_normals()
        out.add(ring)

    # the fallen voussoirs, below the gap
    for i in range(4):
        block = M.box((thickness * float(rng.uniform(0.5, 0.9)),
                       thickness * float(rng.uniform(0.4, 0.7)),
                       depth * float(rng.uniform(0.5, 0.9))),
                      material=JADE)
        block.rotate_y(float(rng.uniform(0.0, math.pi)))
        block.transform(M.rotation_z(float(rng.uniform(-0.6, 0.6))))
        block.translate(half * float(rng.uniform(0.1, 0.9)),
                        thickness * 0.3,
                        depth * float(rng.uniform(-0.9, 0.9)))
        out.add(block)
    for i in range(8):
        chunk = SW.ruin_fragment(seed=seed + 10 + i,
                                 scale=span * float(rng.uniform(0.05, 0.12)))
        chunk.translate(float(rng.uniform(-span, span)), 0.0,
                        float(rng.uniform(-span * 0.8, span * 0.8)))
        out.add(chunk)

    # The roots. The subject of the panel: a strangler over masonry, falling
    # from the crown and the haunches to the ground and spreading at the foot.
    for i in range(14):
        start_x = float(rng.uniform(-half * 1.15, half * 1.15))
        start_y = (pier_heights[0] + rise) * float(rng.uniform(0.55, 1.02))
        z = float(rng.uniform(-depth * 0.7, depth * 0.7))
        spread = float(rng.uniform(1.8, 5.4)) * (1.0 if i % 2 else -1.0)
        path, radii = [], []
        steps = 16
        for k in range(steps):
            t = k / (steps - 1.0)
            path.append((start_x + spread * t * t,
                         start_y * (1.0 - t) + 0.06,
                         z + math.sin(t * 3.4 + i) * 0.85))
            radii.append(float(rng.uniform(0.26, 0.50)) * (1.0 - 0.55 * t) + 0.07)
        out.add(M.tube(np.asarray(path), radii, segments=7, material=SK.BARK))
    # the trunk the roots come from, standing behind the arch
    trunk = jungle_tree(16.0, seed=seed + 3, tier="near",
                        species="ssarathi_strangler")
    trunk.translate(half * 0.45, pier_heights[0] * 0.10, -depth * 1.5)
    out.add(trunk)

    for i in range(4):
        out.add(vine_curtain(3.0, 4.5, seed=seed + 30 + i, sheets=2)
                .translate(float(rng.uniform(-half, half)),
                           pier_heights[0] * float(rng.uniform(0.6, 1.0)),
                           depth * 0.55))
    out.sanitise_normals()
    return out


def ruin_tower(half: float = 5.0, storeys: int = 4, seed: int = 0) -> SW.MeshGroup:
    """A tall square ruin tower, broken off at some height.

    The aerial's skyline is made of these. Without them the region is a field
    of one-storey blocks and the comparison against the concept reads flat at
    any distance - which is exactly what the first aerial sheet showed.

    Not a walk surface: the tower stands on a block whose platform is terrain
    and already carries the player.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    storey_h = float(rng.uniform(3.4, 4.6))
    level = 0.0
    width = half
    for i in range(storeys):
        top = width * float(rng.uniform(0.90, 0.96))
        out.add(square_frustum(width, top, storey_h, JADE)
                .translate(0.0, level, 0.0))
        # a string course between storeys
        out.add(M.box((width * 2.14, storey_h * 0.10, width * 2.14),
                      center=(0.0, level + storey_h * 0.95, 0.0),
                      material=SCALE_TILE))
        # openings: a recessed panel per face, which is what reads as a window
        for face in range(4):
            angle = face * math.pi / 2.0
            panel = M.box((width * 0.44, storey_h * 0.46, 0.32),
                          center=(0.0, level + storey_h * 0.46, width * 0.99),
                          material=CARVED)
            panel.rotate_y(angle)
            out.add(panel)
        level += storey_h
        width = top

    # The break. The top storey is cut down on one side, and its rubble is at
    # the foot - a tower with a clean flat top reads as unfinished, not ruined.
    broken = float(rng.uniform(0.35, 0.85))
    crest = square_frustum(width, width * 0.92, storey_h * broken, JADE)
    crest.translate(0.0, level, 0.0)
    out.add(crest)
    for k in range(4):
        out.add(M.box((float(rng.uniform(0.5, 1.1)), float(rng.uniform(0.3, 0.7)),
                       float(rng.uniform(0.5, 1.1))),
                      center=(float(rng.uniform(-width, width)),
                              level + storey_h * broken + 0.2,
                              float(rng.uniform(-width, width))),
                      material=JADE))
    if float(rng.uniform(0.0, 1.0)) < 0.45:
        finial = obelisk(storey_h * 1.1, seed=seed + 5)
        finial.translate(0.0, level + storey_h * broken, 0.0)
        out.add(finial)

    for k in range(int(rng.uniform(2, 5))):
        out.add(vine_curtain(2.6, storey_h * 1.4, seed=seed + 60 + k, sheets=2)
                .translate(float(rng.uniform(-half, half)),
                           float(rng.uniform(storey_h, level)),
                           half * float(rng.uniform(-1.0, 1.0))))
    out.add(rubble_heap(half * 0.9, seed=seed + 71))
    return out


# ------------------------------------------------------------------- soft
def lily_patch(radius: float = 4.0, count: int = 22, seed: int = 0,
               level: float = 0.0) -> M.Mesh:
    """A raft of lily pads, as horizontal cards on the water surface.

    Cards, not discs: the pad silhouette is in the alpha channel, so a quad per
    pad is two triangles for a shape that would otherwise cost twenty.
    """
    rng = _rng(seed)
    parts = []
    cells = 3
    for i in range(count):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        r = radius * math.sqrt(float(rng.uniform(0.0, 1.0)))
        x, z = math.cos(angle) * r, math.sin(angle) * r
        # A lily pad is about 40 cm across, so the card is ~0.25 m half-extent.
        # At 0.42-0.86 they rendered as three-metre discs and the lily court
        # looked like a pond full of dinner plates.
        size = float(rng.uniform(0.20, 0.36))
        cell_x = int(rng.uniform(0, cells))
        cell_z = int(rng.uniform(0, cells))
        card = M.quad([(-size, 0.0, -size), (size, 0.0, -size),
                       (size, 0.0, size), (-size, 0.0, size)],
                      material=LILY)
        # pick one atlas cell
        card.uvs = np.asarray([
            [(cell_x + 0.02) / cells, (cell_z + 0.02) / cells],
            [(cell_x + 0.98) / cells, (cell_z + 0.02) / cells],
            [(cell_x + 0.98) / cells, (cell_z + 0.98) / cells],
            [(cell_x + 0.02) / cells, (cell_z + 0.98) / cells]])
        card.rotate_y(float(rng.uniform(0.0, math.pi * 2.0)))
        card.translate(x, level + float(rng.uniform(0.01, 0.06)), z)
        parts.append(card)
    out = M.merge(parts, LILY)
    out.sanitise_normals()
    return out


def palm(height: float = 9.0, seed: int = 0, tier: str = "near") -> SW.MeshGroup:
    """A feather palm: a curved trunk and a crown of frond cards.

    Fronds are cards from the palm atlas rather than grown geometry - a palm's
    silhouette is entirely in its frond outline, and the atlas already has it.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    lean = float(rng.uniform(-0.14, 0.14))
    steps = 9 if tier == "near" else 5
    path, radii = [], []
    for i in range(steps):
        s = i / (steps - 1.0)
        path.append((lean * height * s * s, height * s,
                     lean * height * 0.4 * s * s))
        radii.append(height * (0.042 - 0.020 * s))
    out.add(M.tube(np.asarray(path), radii, segments=7 if tier == "near" else 5,
                   cap_start=True, material=SK.BARK_PALE))
    top = np.asarray(path[-1])
    fronds = 9 if tier == "near" else 5
    length = height * float(rng.uniform(0.34, 0.46))
    cells = 2
    for i in range(fronds):
        angle = 2.0 * math.pi * i / fronds + float(rng.uniform(-0.2, 0.2))
        droop = float(rng.uniform(0.30, 0.75))
        card = M.quad([(-length * 0.34, 0.0, 0.0), (length * 0.34, 0.0, 0.0),
                       (length * 0.34, 0.0, length), (-length * 0.34, 0.0, length)],
                      material=PALM)
        cx, cz = int(rng.uniform(0, cells)), int(rng.uniform(0, cells))
        card.uvs = np.asarray([
            [(cx + 0.02) / cells, (cz + 0.98) / cells],
            [(cx + 0.98) / cells, (cz + 0.98) / cells],
            [(cx + 0.98) / cells, (cz + 0.02) / cells],
            [(cx + 0.02) / cells, (cz + 0.02) / cells]])
        card.transform(M.rotation_x(droop))
        card.rotate_y(angle)
        card.translate(top[0], top[1] - 0.2, top[2])
        out.add(card)
    out.sanitise_normals()
    return out


# Two Ssarathi canopy species, registered into the shared profile table at
# import. `trees.register` is the toolkit's documented extension point, so this
# adds a species without touching `trees.py` - the same build-time extension the
# materials use.
KAPOK = TR.register(TR.TreeProfile(
    name="ssarathi_kapok", height=21.0, trunk_radius=0.92, trunk_sides=11,
    first_branch=0.52, lean=0.06, wander=0.16, taper=0.38,
    children=(6, 3, 2), branch_pitch=(0.80, 1.32), branch_length=0.52,
    branch_droop=0.10, cluster_size=(2.6, 4.2), clusters_per_tip=2,
    root_count=9, root_spread=3.2, root_rise=0.72,
    bark_material=SK.BARK_PALE, foliage_material=FOLIAGE, canopy_bias=1.25,
    max_clusters=96))

STRANGLER = TR.register(TR.TreeProfile(
    name="ssarathi_strangler", height=13.5, trunk_radius=0.54, trunk_sides=9,
    first_branch=0.34, lean=0.16, wander=0.34, taper=0.46,
    children=(7, 3, 2), branch_pitch=(0.50, 1.20), branch_length=0.46,
    branch_droop=0.34, cluster_size=(1.8, 3.0), clusters_per_tip=2,
    root_count=11, root_spread=2.6, root_rise=0.54,
    bark_material=SK.BARK, foliage_material=FOLIAGE, canopy_bias=0.95,
    max_clusters=72))


def jungle_tree(height: float = 15.0, seed: int = 0, tier: str = "near",
                species: str = "ssarathi_kapok") -> SW.MeshGroup:
    """A buttressed broadleaf, the basin's canopy species.

    Uses the shared tree grower rather than a private generator:
    `trees.build_tree` already does grown skeletons, three detail tiers and
    buttress roots, and a second one would be exactly the duplication the
    production guide warns about. `build_tree` returns (wood, foliage) as two
    meshes so they keep their own materials; the group carries both.
    """
    detail = {"near": "high", "mid": "mid", "far": "low"}[tier]
    profile = TR.PROFILES[species]
    wood, foliage = TR.build_tree(profile, seed=seed, detail=detail)
    out = SW.MeshGroup()
    out.add(wood)
    out.add(foliage)
    if abs(height - profile.height) > 0.05:
        out.scale(height / profile.height)
    out.sanitise_normals()
    return out


def vine_curtain(width: float = 3.0, drop: float = 4.0, seed: int = 0,
                 sheets: int = 3) -> M.Mesh:
    """Hanging creeper cards, for wall faces and arch soffits."""
    rng = _rng(seed)
    parts = []
    for i in range(sheets):
        w = width * float(rng.uniform(0.6, 1.0))
        d = drop * float(rng.uniform(0.6, 1.0))
        card = M.quad([(-w * 0.5, 0.0, 0.0), (w * 0.5, 0.0, 0.0),
                       (w * 0.5, -d, 0.0), (-w * 0.5, -d, 0.0)],
                      material=VINE)
        card.rotate_y(float(rng.uniform(-0.5, 0.5)))
        card.translate(float(rng.uniform(-width * 0.4, width * 0.4)), 0.0,
                       float(rng.uniform(-0.14, 0.14)))
        parts.append(card)
    out = M.merge(parts, VINE)
    out.sanitise_normals()
    return out


# ------------------------------------------------------------------ works
def timber_dock(length: float = 9.0, width: float = 3.6,
                seed: int = 0) -> SW.MeshGroup:
    """A jetty out over the water. The decking is the walk surface.

    Built along +X with the deck top at y = 0, so it places at the quay level
    and its piles run down into the water.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    out.add_walk(M.box((length, 0.22, width),
                       center=(0.0, -0.11, 0.0), material=TIMBER))
    # plank lines: a few raised boards so the deck is not one flat slab
    for i in range(5):
        z = -width * 0.5 + width * (i + 0.5) / 5.0
        out.add(M.box((length * 0.98, 0.06, width * 0.13),
                      center=(0.0, 0.03, z), material=TIMBER))
    piles = max(int(length / 2.4), 2)
    for i in range(piles + 1):
        x = -length * 0.5 + i * (length / piles)
        for sign in (-1.0, 1.0):
            depth = float(rng.uniform(2.2, 3.4))
            out.add(M.cylinder(0.17, 0.15, depth, segments=6, material=TIMBER)
                    .translate(x, -depth - 0.20, sign * (width * 0.5 - 0.24)))
        if i % 2 == 0:
            out.add(M.cylinder(0.13, 0.11, 1.05, segments=6, material=TIMBER)
                    .translate(x, 0.0, width * 0.5 - 0.24))
    return out


def market_stall(width: float = 3.4, seed: int = 0) -> SW.MeshGroup:
    """A canvas awning over a trestle - the aerial's warm orange notes."""
    rng = _rng(seed)
    out = SW.MeshGroup()
    depth = width * 0.72
    post_h = 2.35
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            out.add(M.cylinder(0.07, 0.06, post_h, segments=5, material=TIMBER)
                    .translate(sx * width * 0.5, 0.0, sz * depth * 0.5))
    from amberwood import civiccraft as CIV
    out.add(CIV.pitched_canopy(width*1.12,depth*1.16,post_h,
                              post_h+width*0.20,CANVAS,TIMBER))
    out.add(M.box((width * 0.94, 0.10, depth * 0.62),
                  center=(0.0, 0.86, 0.0), material=TIMBER))
    for sx in (-1.0, 1.0):
        out.add(M.box((0.10, 0.86, depth * 0.58),
                      center=(sx * width * 0.40, 0.43, 0.0), material=TIMBER))
    # goods on the trestle
    for i in range(int(rng.uniform(3, 6))):
        pot = M.lathe([(0.0, 0.0), (0.16, 0.04), (0.20, 0.16), (0.11, 0.28),
                       (0.14, 0.32), (0.0, 0.34)], segments=9, material=CARVED)
        pot.translate(float(rng.uniform(-width * 0.34, width * 0.34)), 0.91,
                      float(rng.uniform(-depth * 0.22, depth * 0.22)))
        out.add(pot)
    out.sanitise_normals()
    return out


def shrine(height: float = 3.6, seed: int = 0) -> SW.MeshGroup:
    """A roadside serpent shrine: a niche, a face and an offering step."""
    out = SW.MeshGroup()
    w = height * 0.52
    out.add_walk(M.box((w * 2.2, 0.24, w * 1.6),
                       center=(0.0, 0.12, w * 0.5), material=PAVING))
    out.add(M.box((w * 1.5, height * 0.74, w * 0.9),
                  center=(0.0, height * 0.37, 0.0), material=JADE))
    out.add(M.box((w * 1.75, height * 0.08, w * 1.1),
                  center=(0.0, height * 0.78, 0.0), material=CARVED))
    roof = _facet(M.lathe([(w * 1.15, 0.0), (w * 0.86, height * 0.10),
                           (0.0, height * 0.22)], segments=4,
                          material=SCALE_TILE))
    roof.rotate_y(math.pi / 4.0)
    roof.translate(0.0, height * 0.82, 0.0)
    out.add(roof)
    face = stone_face(w * 0.42, seed=seed)
    face.translate(0.0, height * 0.22, w * 0.46)
    out.add(face)
    out.add(vine_curtain(w * 1.2, height * 0.5, seed=seed + 3, sheets=2)
            .translate(0.0, height * 0.80, -w * 0.44))
    return out


def waterfall_sheet(width: float, height: float, seed: int = 0) -> SW.MeshGroup:
    """A falling sheet of water with spray at its foot.

    Uses the shared `stonework.waterfall` for the sheet and adds the plunge
    ring; the concept's falls all land in the basin rather than on rock.
    """
    # `stonework.waterfall` builds downward from y = 0, so this piece places at
    # the *lip* and the plunge ring sits at -height.
    out = SW.MeshGroup()
    out.add(SW.waterfall(width, height, seed=seed))
    for i in range(5):
        angle = 2.0 * math.pi * i / 5.0
        ring = M.lathe([(width * 0.30, 0.0), (width * 0.52, 0.10),
                        (width * 0.58, 0.0)], segments=14, material=WATER)
        ring.translate(math.cos(angle) * width * 0.12,
                       -height + 0.05 + i * 0.04,
                       math.sin(angle) * width * 0.12)
        out.add(ring)
    out.sanitise_normals()
    return out


def rubble_heap(radius: float = 2.4, seed: int = 0) -> M.Mesh:
    """A collapse pile, for the drowned quarter and the ruin fields."""
    rng = _rng(seed)
    parts = []
    for i in range(int(rng.uniform(5, 10))):
        chunk = SW.ruin_fragment(seed=seed + i, scale=float(rng.uniform(0.3, 0.9)))
        angle = float(rng.uniform(0, math.pi * 2))
        r = radius * float(rng.uniform(0.0, 1.0))
        chunk.translate(math.cos(angle) * r, float(rng.uniform(-0.1, 0.3)),
                        math.sin(angle) * r)
        parts.append(chunk)
    out = M.merge(parts, RUBBLE)
    out.sanitise_normals()
    return out


def ruin_building(half_x: float, half_z: float, seed: int = 0,
                  storeys: int = 1) -> SW.MeshGroup:
    """A ruined block of the drowned city: walls, columns and a broken roof.

    This is the piece the aerial is mostly *made of*. The basin between the
    causeways is not water with paving in it - it is a dense mass of collapsed
    jade masonry with trees coming through it, and without this the massing
    pass produces coloured rectangles.

    Nothing here is a walk surface. The block's platform is terrain and already
    carries the player; the walls standing on it are structure, and marking a
    half-collapsed roof walkable would let the grounding ray put an actor on
    top of it.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    height = (2.6 + float(rng.uniform(0.0, 2.4))) * storeys
    thickness = 0.55

    # Walls, each one independently broken down to some fraction of full
    # height. A block with four intact walls reads as a shed; the concept's
    # blocks are always missing at least one side.
    walls = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    standing = 0
    for i, (sx, sz) in enumerate(walls):
        survives = float(rng.uniform(0.0, 1.0))
        if survives < 0.22:
            continue                              # this side is gone entirely
        h = height * float(rng.uniform(0.35, 1.0))
        standing += 1
        if sx:
            out.add(M.box((thickness, h, half_z * 2.0),
                          center=(sx * (half_x - thickness * 0.5), h * 0.5, 0.0),
                          material=JADE))
        else:
            out.add(M.box((half_x * 2.0, h, thickness),
                          center=(0.0, h * 0.5, sz * (half_z - thickness * 0.5)),
                          material=JADE))
        # a ragged crest of loose blocks along the break
        for k in range(3):
            u = float(rng.uniform(-0.85, 0.85))
            out.add(M.box((float(rng.uniform(0.4, 0.9)),
                           float(rng.uniform(0.2, 0.5)),
                           float(rng.uniform(0.4, 0.9))),
                          center=(sx * (half_x - thickness) if sx else u * half_x,
                                  h + 0.15,
                                  sz * (half_z - thickness) if sz else u * half_z),
                          material=JADE))

    # Corner columns, which is what survives longest and what the aerial shows
    # standing out of every collapse.
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            if float(rng.uniform(0.0, 1.0)) < 0.30:
                continue
            ch = height * float(rng.uniform(0.55, 1.25))
            col = SW.column(ch, radius=0.30, flutes=9, material=JADE)
            col.translate(sx * (half_x - 0.9), 0.0, sz * (half_z - 0.9))
            out.add(col)
            if float(rng.uniform(0.0, 1.0)) < 0.45:
                out.add(M.box((0.80, 0.20, 0.80),
                              center=(sx * (half_x - 0.9), ch, sz * (half_z - 0.9)),
                              material=CARVED))

    # A partial scale-tiled roof, only where enough walls stand to carry one.
    if standing >= 3 and float(rng.uniform(0.0, 1.0)) < 0.55:
        span = float(rng.uniform(0.35, 0.80))
        roof = _facet(M.lathe(
            [(min(half_x, half_z) * 1.12, 0.0),
             (min(half_x, half_z) * 0.70, height * 0.22),
             (0.0, height * 0.40)], segments=4, material=SCALE_TILE))
        roof.rotate_y(math.pi / 4.0)
        roof.scale(half_x / min(half_x, half_z), 1.0, half_z / min(half_x, half_z))
        # cut the roof back to a fragment: keep the half that is still there
        keep = roof.positions[:, 0] < half_x * (span * 2.0 - 1.0)
        faces = roof.indices.reshape(-1, 3)
        faces = faces[keep[faces].all(axis=1)]
        if faces.shape[0]:
            roof.indices = faces.reshape(-1)
            roof.translate(0.0, height * 0.92, 0.0)
            out.add(roof)

    # A doorway lintel on one face, and a boss or a face on some blocks.
    if float(rng.uniform(0.0, 1.0)) < 0.5:
        out.add(M.box((1.9, 0.36, thickness * 1.4),
                      center=(0.0, height * 0.52, half_z - thickness * 0.5),
                      material=CARVED))
    if float(rng.uniform(0.0, 1.0)) < 0.28:
        boss = shell_boss(0.6)
        boss.transform(M.rotation_x(-math.pi / 2.0))
        boss.translate(0.0, height * 0.70, half_z + 0.05)
        out.add(boss)

    # Vines and rubble, which is what turns masonry into ruin.
    for k in range(int(rng.uniform(1, 4))):
        out.add(vine_curtain(2.4, height * 0.8, seed=seed + 40 + k, sheets=2)
                .translate(float(rng.uniform(-half_x, half_x)),
                           height * float(rng.uniform(0.5, 0.95)),
                           half_z * float(rng.uniform(-1.0, 1.0))))
    out.add(rubble_heap(min(half_x, half_z) * 0.7, seed=seed + 61)
            .translate(float(rng.uniform(-half_x * 0.5, half_x * 0.5)), 0.0,
                       float(rng.uniform(-half_z * 0.5, half_z * 0.5))))
    return out

# ------------------------------------------------------------------ doors
def well_head(radius: float = 3.4, height: float = 3.0,
              seed: int = 0) -> SW.MeshGroup:
    """A drum well-head over a shaft: the way down into the cistern.

    The rim is a walk surface and the mouth is left open, so the piece reads as
    somewhere you can stand and look down rather than as a solid plinth. The
    ring is annular for the reason every deck in this region is: placement is
    single-layer, and a solid lid would ground an actor on the lid.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    # the drum, as a ring of ashlar blocks
    blocks = 16
    for i in range(blocks):
        angle = 2.0 * math.pi * i / blocks
        block = M.box((radius * 0.44, height * float(rng.uniform(0.82, 1.0)),
                       radius * 0.34),
                      center=(radius, 0.0, 0.0), uv_scale=0.7, material=JADE)
        block.transform(M.rotation_y(-angle))
        out.add(block)
    # a walkable kerb around the mouth, annular
    steps = 20
    for i in range(steps):
        a0 = 2.0 * math.pi * i / steps
        plank = M.box((radius * 0.42, 0.30, radius * 0.52),
                      center=(radius * 1.26, height * 0.5 - 0.15, 0.0),
                      uv_scale=0.6, material=PAVING)
        plank.transform(M.rotation_y(-a0))
        out.add_walk(plank)
    # the head-frame and its bucket
    for sign in (-1.0, 1.0):
        out.add(M.cylinder(0.16, 0.13, height * 1.5,
                           segments=6, material=TIMBER)
                .translate(sign * radius * 0.9, height * 0.5, 0.0))
    out.add(M.cylinder(0.11, 0.11, radius * 1.9, segments=6, material=TIMBER)
            .transformed(M.rotation_z(math.pi * 0.5))
            .translate(0.0, height * 2.0, 0.0))
    out.add(shell_boss(radius * 0.22)
            .translate(0.0, height * 0.52, radius * 1.15))
    out.add(vine_curtain(radius * 0.8, height * 0.9, seed=seed + 3, sheets=2)
            .translate(0.0, height * 0.5, -radius * 1.1))
    return out


def stair_mouth(width: float = 5.2, drop: float = 3.2,
                seed: int = 0) -> SW.MeshGroup:
    """A stepped opening in a plaza floor: the way down to the hatchery.

    Built along +Z with its top at y = 0 so it places on the plaza surface. The
    treads descend into the ground and are walk surfaces; the cheek walls and
    the lintel are not.
    """
    out = SW.MeshGroup()
    steps = 8
    rise = drop / steps
    run = width * 0.22
    for i in range(steps):
        y = -rise * (i + 1)
        out.add_walk(M.box((width * 0.62, 0.30, run),
                           center=(0.0, y + 0.15, run * (i + 0.5)),
                           uv_scale=0.6, material=PAVING))
    for sign in (-1.0, 1.0):
        out.add(M.box((width * 0.20, drop * 1.1, run * steps * 1.05),
                      center=(sign * width * 0.41, -drop * 0.45,
                              run * steps * 0.5),
                      uv_scale=0.6, material=JADE))
        out.add(M.box((width * 0.22, 0.36, width * 0.30),
                      center=(sign * width * 0.41, 0.18, -width * 0.10),
                      uv_scale=0.7, material=CARVED))
    # the lintel and its sun disc, so the mouth reads as a doorway
    out.add(M.box((width * 1.02, 0.42, width * 0.34),
                  center=(0.0, 1.9, -width * 0.06), uv_scale=0.6,
                  material=JADE))
    disc = sun_disc(width * 0.16, seed=seed)
    disc.transform(M.rotation_x(math.pi / 2.0))
    disc.translate(0.0, 1.5, -width * 0.22)
    out.add(disc)
    for sign in (-1.0, 1.0):
        out.add(M.box((width * 0.12, 1.9, width * 0.28),
                      center=(sign * width * 0.45, 0.95, -width * 0.06),
                      uv_scale=0.7, material=JADE))
    return out


def broken_mouth(width: float = 4.6, drop: float = 2.8,
                 seed: int = 0) -> SW.MeshGroup:
    """A collapsed opening into the root undercroft.

    Not a built door: a hole where a vault came down, edged in rubble with roots
    across it. Its ramp is walkable so the way in is real.
    """
    rng = _rng(seed)
    out = SW.MeshGroup()
    steps = 7
    for i in range(steps):
        y = -drop * (i + 1) / steps
        out.add_walk(M.box((width * 0.58, 0.30, width * 0.26),
                           center=(float(rng.uniform(-0.3, 0.3)), y + 0.15,
                                   width * 0.26 * (i + 0.5)),
                           uv_scale=0.6, material=RUBBLE))
    for i in range(9):
        angle = math.pi * float(rng.uniform(0.05, 0.95))
        chunk = SW.ruin_fragment(seed=seed + i,
                                 scale=float(rng.uniform(0.4, 1.0)))
        chunk.translate(math.cos(angle) * width * 0.62,
                        float(rng.uniform(-0.2, 0.4)),
                        math.sin(angle) * width * 0.62 - width * 0.1)
        out.add(chunk)
    # roots across the opening
    for i in range(5):
        path, radii = [], []
        for k in range(12):
            t = k / 11.0
            path.append((-width * 0.6 + width * 1.2 * t,
                         0.9 - math.sin(t * math.pi) * 0.7,
                         float(rng.uniform(-0.4, 0.4)) + width * 0.25 * i * 0.2))
            radii.append(float(rng.uniform(0.14, 0.26)))
        out.add(M.tube(np.asarray(path), radii, segments=6, material=SK.BARK))
    out.add(vine_curtain(width * 0.9, 2.2, seed=seed + 11, sheets=3)
            .translate(0.0, 1.1, -width * 0.2))
    return out
