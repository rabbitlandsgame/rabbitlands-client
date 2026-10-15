"""Hero landmark assemblies: central plaza, causeway bridges, sanctuary."""

from __future__ import annotations

import math
from typing import List

import numpy as np

import kits
import meshlib as M
from kits import Palette
from meshlib import Geo

TAU = math.pi * 2.0


# The plaza paving is one apron ring at the plateau datum and one raised
# terrace inside PLAZA_TERRACE_FRACTION of the radius, joined by a riser.  The
# builder places the plaza props on these same numbers, so keep them here.
PLAZA_TERRACE_FRACTION = 0.78
PLAZA_TERRACE_RISE = 0.42
PLAZA_TRIM_FRACTIONS = (0.44, 0.48)


def plaza_disc(p: Palette, radius: float = 70.0) -> Geo:
    """Radial paving mandala with a stepped terrace, as in the plaza reference.

    The paving UVs are authored so the concentric-and-spoke pattern maps exactly
    once across the plaza, centred on the monument, instead of tiling.

    Every paving face is a distinct annulus and the riser is capless, so no two
    surfaces of the mandala are ever coplanar.  Building the steps as capped
    full-radius cylinders stacked over overlapping inner discs put up to four
    identical surfaces at the same height and z-fought across the whole plaza.
    """
    terrace_r = radius * PLAZA_TERRACE_FRACTION
    trim_in, trim_out = (radius * f for f in PLAZA_TRIM_FRACTIONS)
    rings = ((1.5, trim_in, p.paving_plaza),
             (trim_in, trim_out, p.stone_trim),
             (trim_out, terrace_r, p.paving_plaza))
    parts = [M.polar_surface(np.linspace(terrace_r, radius, 6), 128,
                             lambda X, Z: np.full_like(X, 0.0),
                             material=p.paving_plaza, uv_scale=1.0),
             M.cylinder(terrace_r, PLAZA_TERRACE_RISE, 128, p.stone_trim, 3.0,
                        cap_top=False, cap_bottom=False)]
    for r_in, r_out, material in rings:
        steps = max(2, int((r_out - r_in) / 3.0) + 2)
        parts.append(M.polar_surface(
            np.linspace(r_in, r_out, steps), 128,
            lambda X, Z: np.full_like(X, PLAZA_TERRACE_RISE),
            material=material, uv_scale=1.0))
    plaza = Geo.concat(parts)
    # map the mandala once across the disc
    span = radius * 2.02
    plaza.t = np.stack([plaza.v[:, 0] / span + 0.5,
                        plaza.v[:, 2] / span + 0.5], axis=1).astype(np.float32)
    return plaza


def plaza_monument(p: Palette, height: float = 54.0) -> Geo:
    """Slender crystal-crowned civic spire at the centre of the city."""
    parts = []
    base = M.revolve([(9.5, 0.0), (9.5, 1.4), (8.6, 2.0), (8.6, 3.4),
                      (7.4, 4.0), (7.4, 4.6)], 24, p.stone_trim, 2.4)
    parts.append(base)
    for i in range(8):
        a = TAU * i / 8
        buttress = M.tapered_box(2.6, 3.4, 1.4, 2.0, 9.0, p.stone_trim, 2.0)
        buttress.rotate_y(-a)
        buttress.translate(math.cos(a) * 7.0, 4.6, math.sin(a) * 7.0)
        parts.append(buttress)
    shaft = M.revolve([(4.6, 0.0), (4.2, height * 0.24), (3.4, height * 0.50),
                       (2.9, height * 0.70), (3.4, height * 0.74),
                       (2.6, height * 0.78)], 16, p.stone_ashlar, 3.2)
    shaft.translate(0.0, 4.6, 0.0)
    parts.append(shaft)
    for i in range(4):
        a = TAU * i / 4 + math.pi / 4
        rib = M.box(0.55, height * 0.62, 0.55, p.metal_gold, 1.2, origin="corner")
        rib.rotate_y(-a)
        rib.translate(math.cos(a) * 3.9, 6.0, math.sin(a) * 3.9)
        parts.append(rib)
    gallery = M.revolve([(2.6, 0.0), (5.2, 0.5), (5.2, 2.2), (4.4, 2.6), (2.4, 2.4)],
                        16, p.stone_trim, 1.8)
    gallery.translate(0.0, 4.6 + height * 0.78, 0.0)
    parts.append(gallery)
    lantern = M.cylinder(2.5, 6.0, 12, p.stone_trim, 2.0)
    lantern.translate(0.0, 4.6 + height * 0.78 + 2.6, 0.0)
    parts.append(lantern)
    for i in range(6):
        a = TAU * i / 6
        window = M.box(0.9, 3.6, 0.5, p.crystal_blue, 1.0, origin="corner")
        window.rotate_y(-a)
        window.translate(math.cos(a) * 2.45, 4.6 + height * 0.78 + 3.6,
                         math.sin(a) * 2.45)
        parts.append(window)
    cap = M.cone(3.0, 5.0, 12, p.roof_verdigris, 2.0)
    cap.translate(0.0, 4.6 + height * 0.78 + 8.6, 0.0)
    parts.append(cap)
    return Geo.concat(parts)


def plaza_crystal(p: Palette, size: float = 5.4) -> Geo:
    """The pulsing sapphire that crowns the monument (its own node)."""
    gem = M.revolve([(0.0, 0.0), (size * 0.42, size * 0.36), (size * 0.30, size * 1.05),
                     (0.0, size * 1.5)], 8, p.crystal_blue, 1.0)
    collar = M.revolve([(size * 0.5, 0.0), (size * 0.62, 0.24), (size * 0.34, 0.5)],
                       8, p.metal_gold, 0.8)
    return Geo.concat([collar, gem])


def bridge_span(p: Palette, length: float, deck_y: float, water_y: float,
                width: float = 30.0, arches: int = 4) -> Geo:
    """Arched causeway bridge with piers, parapets, lamps and banner pylons.

    Local space: the span runs along +/-Z, centred on the origin, deck top at
    y = 0.  Callers place and rotate it.
    """
    parts: List[Geo] = []
    # the walkable deck itself is authored as a separate node by the caller so
    # it can carry the navigation surface; here we build only what sits below it
    soffit = M.box(width, 1.4, length, p.stone_ashlar, 3.0, origin="corner")
    soffit.translate(0.0, -3.0, 0.0)
    parts.append(soffit)
    for side in (-1, 1):
        # moulded edge beam, held clear of the deck node's own slab
        beam = M.box(2.4, 1.1, length, p.stone_trim, 2.0, origin="corner")
        beam.translate(side * (width * 0.5 + 0.6), -1.15, 0.0)
        parts.append(beam)

    pier_span = length / arches
    depth_to_water = deck_y - water_y
    for i in range(arches + 1):
        z = -length * 0.5 + pier_span * i
        if i in (0, arches):
            pier_w = width * 0.98
        else:
            pier_w = width * 0.62
        pier = M.tapered_box(pier_w, pier_span * 0.30, pier_w * 0.88,
                             pier_span * 0.24, depth_to_water + 6.0,
                             p.stone_rubble, 4.0)
        pier.translate(0.0, -(depth_to_water + 6.0) - 3.0, z)
        parts.append(pier)
        if 0 < i < arches:
            # cutwater noses upstream and downstream
            for side in (-1, 1):
                nose = M.cone(pier_span * 0.16, depth_to_water * 0.75, 6,
                              p.stone_rubble, 3.0)
                nose.rotate_x(math.pi)
                # Springs from inside the soffit, not off the pier top: an
                # inverted cone's base cap faces up, and at the pier's own top
                # the cap and the pier crown were one plane over half the cap.
                nose.translate(0.0, -2.6, z + side * pier_span * 0.16)
                parts.append(nose)
    # segmental arches spring low enough that their crowns stay under the deck
    soffit_bottom = -4.4
    for i in range(arches):
        z = -length * 0.5 + pier_span * (i + 0.5)
        radius = min(pier_span * 0.34, (depth_to_water - 8.0) * 0.5)
        radius = max(radius, 4.0)
        springing = soffit_bottom - (radius + 2.4)
        arch = M.arch_ring(radius, radius + 2.4, width * 0.86, 0.0, math.pi, 14,
                           p.stone_ashlar, 3.2)
        arch.rotate_y(math.pi / 2)
        arch.translate(0.0, springing, z)
        parts.append(arch)
        # Spandrel walls fill between the arch back and the deck soffit. They
        # stop just short of meeting over the pier: sized to overlap, the two
        # that share a pier had their tops in one plane and fought there.
        for side in (-1, 1):
            spandrel = M.box(width * 0.86, abs(springing) - abs(soffit_bottom),
                             pier_span * 0.5 - radius * 1.02, p.stone_ashlar, 3.2,
                             origin="corner")
            spandrel.translate(0.0, springing,
                               z + side * (radius + (pier_span * 0.5 - radius) * 0.5))
            parts.append(spandrel)

    for side in (-1, 1):
        parapet = M.box(1.5, 1.5, length, p.stone_trim, 2.5, origin="corner")
        parapet.translate(side * (width * 0.5 - 0.75), 0.0, 0.0)
        parts.append(parapet)
        count = int(length / 3.0)
        for i in range(count):
            z = -length * 0.5 + length * (i + 0.5) / count
            baluster = M.box(0.5, 1.1, 0.9, p.stone_trim, 1.0, origin="corner")
            baluster.translate(side * (width * 0.5 - 0.75), 1.5, z)
            parts.append(baluster)
        rail = M.box(1.2, 0.28, length, p.stone_trim, 1.5, origin="corner")
        rail.translate(side * (width * 0.5 - 0.75), 2.6, 0.0)
        parts.append(rail)

    # banner pylons at the quarter points, as on the causeway reference
    for i in range(1, arches):
        z = -length * 0.5 + pier_span * i
        for side in (-1, 1):
            pylon = M.tapered_box(3.6, 3.6, 3.0, 3.0, 11.0, p.stone_ashlar, 2.4)
            pylon.translate(side * (width * 0.5 - 0.75), 2.9, z)
            parts.append(pylon)
            parts.append(kits.moulding(4.2, 4.2, 1.0, p).translate(
                side * (width * 0.5 - 0.75), 13.9, z))
            flag = kits.banner(2.6, 7.4, p, pole=False)
            flag.translate(side * (width * 0.5 - 0.75 - side * 1.9), 13.2, z)
            parts.append(flag)
            parts.append(kits.finial(2.2, 0.5, p).translate(
                side * (width * 0.5 - 0.75), 14.9, z))
    # deck lamps
    count = max(2, int(length / 26.0))
    for i in range(count):
        z = -length * 0.5 + length * (i + 0.5) / count
        for side in (-1, 1):
            parts.append(kits.crystal_lamp(5.4, p).translate(
                side * (width * 0.5 - 2.6), 0.0, z))
    return Geo.concat(parts)


def sanctuary(p: Palette, landscape_terrace: bool = True) -> Geo:
    """Cliff-shelf temple with a glowing portal, beacon and flanking spires."""
    parts: List[Geo] = []
    # battered retaining wall carrying the shelf out of the hillside, so the
    # terrace never reads as a floating disc
    skirt = M.cylinder(50.0, 34.0, 40, p.stone_rubble, 5.0, top_radius=53.0,
                       cap_top=False, cap_bottom=False)
    skirt.translate(0.0, -36.0, 0.0)
    parts.append(skirt)
    for i in range(20):
        a = TAU * i / 20
        buttress = M.tapered_box(5.0, 7.0, 3.0, 4.0, 30.0, p.stone_rubble, 4.0)
        buttress.rotate_y(-a)
        buttress.translate(math.cos(a) * 51.0, -32.0, math.sin(a) * 51.0)
        parts.append(buttress)
    terrace = M.cylinder(53.0, 2.4, 40, p.paving_plaza, 6.0)
    terrace.translate(0.0, -2.4, 0.0)
    parts.append(terrace)
    rim = M.revolve([(53.0, 0.0), (54.8, 0.7), (54.8, 2.0), (53.0, 2.3)],
                    40, p.stone_trim, 2.0)
    rim.translate(0.0, -2.4, 0.0)
    parts.append(rim)
    for i in range(28):
        a = TAU * i / 28
        if abs(((a + math.pi * 0.5) % TAU) - math.pi) < 0.30:
            continue        # leave the stair mouth open
        post = M.box(1.5, 1.5, 1.5, p.stone_trim, 1.0, origin="corner")
        post.translate(math.cos(a) * 53.7, -0.1, math.sin(a) * 53.7)
        parts.append(post)

    if not landscape_terrace:
        # A terrain-authored shelf supplies the approach in compact regions.
        # Keep the temple, podium and stair dimensions; omit the old 106m disc.
        parts = []
    podium = M.box(56.0, 5.0, 34.0, p.stone_ashlar, 4.0, origin="corner")
    podium.translate(0.0, 0.0, -14.0)
    parts.append(podium)
    if landscape_terrace:
        steps = M.stairs(34.0, 5.0, 9.0, 6, p.stone_trim, 2.0)
        steps.rotate_y(math.pi)
        steps.translate(0.0, 0.0, 5.5)
        parts.append(steps)

    body = M.box(44.0, 22.0, 28.0, p.stone_ashlar, 4.0, origin="corner")
    body.translate(0.0, 5.0, -14.0)
    parts.append(body)
    parts.append(kits.moulding(48.0, 32.0, 2.6, p).translate(0.0, 27.0, -14.0))

    # colonnaded front
    for i in range(8):
        x = -21.0 + 42.0 * i / 7.0
        column = M.revolve([(1.35, 0.0), (1.2, 1.2), (1.05, 18.0), (1.3, 19.0),
                            (1.5, 19.8), (1.45, 20.6)], 12, p.stone_trim, 2.4)
        column.translate(x, 5.0, 1.6)
        parts.append(column)
    architrave = M.box(46.0, 3.0, 5.4, p.stone_trim, 2.4, origin="corner")
    architrave.translate(0.0, 25.6, 1.6)
    parts.append(architrave)
    pediment = M.gable_roof(47.0, 6.0, 6.0, 0.4, p.stone_trim, 2.4, ridge_along_x=True)
    pediment.translate(0.0, 28.6, 1.6)
    parts.append(pediment)

    # the great portal: a recessed arch filled with blue energy
    portal_arch = M.arch_ring(7.5, 10.5, 4.0, 0.0, math.pi, 16, p.stone_trim, 2.4)
    portal_arch.translate(0.0, 15.0, -0.4)
    parts.append(portal_arch)
    for side in (-1, 1):
        jamb = M.box(3.0, 15.0, 4.0, p.stone_trim, 2.0, origin="corner")
        jamb.translate(side * 9.0, 5.0, -0.4)
        parts.append(jamb)
    surround = M.box(26.0, 2.0, 3.0, p.metal_gold, 1.6, origin="corner")
    surround.translate(0.0, 26.0, -0.4)
    parts.append(surround)

    roof = M.gable_roof(46.0, 30.0, 9.0, 1.0, p.roof_verdigris, 3.0, ridge_along_x=True)
    roof.translate(0.0, 29.6, -14.0)
    parts.append(roof)
    for i in range(5):
        x = -18.0 + 36.0 * i / 4.0
        parts.append(kits.finial(3.4, 0.7, p).translate(x, 38.6, -14.0))

    # flanking spires
    for side in (-1, 1):
        base = M.cylinder(6.0, 4.0, 12, p.stone_rubble, 3.0)
        base.translate(side * 34.0, 0.0, -8.0)
        drum = M.cylinder(5.0, 30.0, 12, p.stone_ashlar, 4.0, top_radius=4.4)
        drum.translate(side * 34.0, 4.0, -8.0)
        cap = M.cone(5.4, 12.0, 12, p.roof_verdigris, 2.6)
        cap.translate(side * 34.0, 34.0, -8.0)
        parts += [base, drum, cap]
        parts.append(kits.finial(4.0, 0.8, p).translate(side * 34.0, 46.0, -8.0))
        for j in range(3):
            window = M.box(1.1, 3.6, 0.7, p.crystal_blue, 1.0, origin="corner")
            window.translate(side * 34.0, 12.0 + j * 7.0, -8.0 + 4.6)
            parts.append(window)

    # guardian statues at the stair head
    for side in (-1, 1):
        parts.append(kits.hooded_statue(7.5, p).translate(side * 22.0, 5.0, 7.0))
    return Geo.concat(parts)


def sanctuary_portal_energy(p: Palette) -> Geo:
    """Animated blue energy sheet inside the sanctuary arch."""
    verts = []
    faces = []
    segments = 12
    for i in range(segments + 1):
        t = i / segments
        a = math.pi * t
        x = math.cos(a) * 7.4
        y = math.sin(a) * 7.4
        verts.append((x, max(y, 0.0), 0.0))
        verts.append((x, 0.0, 0.0))
    for i in range(segments):
        a0, a1 = i * 2, i * 2 + 1
        b0, b1 = (i + 1) * 2, (i + 1) * 2 + 1
        faces += [(a0, b0, b1), (a0, b1, a1)]
    sheet = M.make(verts, faces, p.crystal_blue, 1.0, smooth=True)
    return sheet


def beacon(p: Palette, height: float = 26.0) -> Geo:
    parts = []
    base = M.revolve([(4.2, 0.0), (4.6, 1.2), (3.4, 2.4), (3.0, 3.0)],
                     12, p.stone_trim, 1.6)
    parts.append(base)
    for i in range(4):
        a = TAU * i / 4 + math.pi / 4
        pillar = M.box(1.0, height * 0.72, 1.0, p.stone_trim, 1.4, origin="corner")
        pillar.rotate_y(-a)
        pillar.translate(math.cos(a) * 2.4, 3.0, math.sin(a) * 2.4)
        parts.append(pillar)
    canopy = M.revolve([(4.0, 0.0), (4.4, 0.8), (2.4, 3.2), (0.0, 4.2)],
                       12, p.metal_gold, 1.4)
    canopy.translate(0.0, 3.0 + height * 0.72, 0.0)
    parts.append(canopy)
    return Geo.concat(parts)


def beacon_flame(p: Palette) -> Geo:
    gem = M.revolve([(0.0, 0.0), (2.2, 1.4), (1.5, 4.4), (0.0, 6.4)],
                    10, p.crystal_blue, 1.0)
    return gem


def ceremonial_stair(p: Palette, width: float, rise: float, run: float,
                     flights: int = 5) -> Geo:
    """Monumental stair in flights and landings, climbing toward -Z.

    Origin is the bottom of the first flight; the stair advances in -Z and the
    treads sit directly on the authored ramp so nothing floats or steps into
    the hillside.
    """
    parts = []
    flight_rise = rise / flights
    flight_run = run / flights
    tread_run = flight_run * 0.74
    landing_run = flight_run - tread_run
    y = 0.0
    z = 0.0
    for i in range(flights):
        steps = max(6, int(round(flight_rise / 0.36)))
        stair = M.stairs(width, flight_rise, tread_run, steps, p.paving_road, 2.0)
        # M.stairs builds toward +Z from its centre; mirror it onto -Z
        stair.rotate_y(math.pi)
        stair.translate(0.0, y, z - tread_run * 0.5)
        parts.append(stair)
        y += flight_rise
        z -= tread_run
        landing = M.box(width, 0.55, landing_run + 0.6, p.paving_road, 2.5,
                        origin="corner")
        landing.translate(0.0, y - 0.55, z - landing_run * 0.5)
        parts.append(landing)
        for side in (-1, 1):
            wall = M.box(1.8, flight_rise + 1.6, flight_run, p.stone_trim, 2.0,
                         origin="corner")
            wall.translate(side * (width * 0.5 + 0.9), y - flight_rise - 0.4,
                           z + tread_run * 0.5 - landing_run * 0.5)
            parts.append(wall)
            post = M.box(2.4, 2.6, 2.4, p.stone_trim, 1.2, origin="corner")
            post.translate(side * (width * 0.5 + 0.9), y + 1.2, z - landing_run * 0.5)
            parts.append(post)
            parts.append(kits.crystal_lamp(5.2, p).translate(
                side * (width * 0.5 + 0.9), y + 3.8, z - landing_run * 0.5))
        z -= landing_run
    return Geo.concat(parts)


def plaza_arcade(p: Palette, radius: float, sweep: float, bays: int = 7,
                 plinth_rise: float = 1.2) -> Geo:
    """Curved arcaded portico enclosing the plaza, as in the plaza reference."""
    parts = []
    depth = 9.0
    height = 11.0
    podium = M.ring_band(radius - depth * 0.5, radius + depth * 0.5, bays * 4,
                         lambda x, z: 0.0, p.stone_trim, 2.0,
                         start=-sweep * 0.5, sweep=sweep)
    # A plinth projects past the wall it carries. At the back wall's own radius
    # the two open cylinders were the same surface over the plinth's height.
    base = M.cylinder(radius + depth * 0.5 + 0.35, 1.2, bays * 4, p.stone_trim, 3.0,
                      start_angle=-sweep * 0.5, sweep=sweep, cap_top=False,
                      cap_bottom=False)
    parts += [podium, base]
    back = M.cylinder(radius + depth * 0.5, height, bays * 4, p.stone_ashlar, 4.0,
                      start_angle=-sweep * 0.5, sweep=sweep, cap_top=False,
                      cap_bottom=False)
    parts.append(back)
    for i in range(bays + 1):
        a = -sweep * 0.5 + sweep * i / bays
        column = M.revolve([(0.85, 0.0), (0.75, 0.9), (0.66, height - 1.6),
                            (0.82, height - 0.9), (0.95, height - 0.4),
                            (0.92, height)], 10, p.stone_trim, 2.0)
        column.translate(math.cos(a) * (radius - depth * 0.42), plinth_rise,
                         math.sin(a) * (radius - depth * 0.42))
        parts.append(column)
    entablature = M.cylinder(radius + depth * 0.55, 1.8, bays * 4, p.stone_trim, 2.2,
                             start_angle=-sweep * 0.5, sweep=sweep,
                             top_radius=radius + depth * 0.60,
                             cap_top=False, cap_bottom=False)
    entablature.translate(0.0, height + plinth_rise, 0.0)
    parts.append(entablature)
    roof = M.ring_band(radius - depth * 0.5, radius + depth * 0.62, bays * 4,
                       lambda x, z: 0.0, p.roof_verdigris, 2.6,
                       start=-sweep * 0.5, sweep=sweep)
    roof.translate(0.0, height + 3.0, 0.0)
    parts.append(roof)
    for i in range(bays):
        a = -sweep * 0.5 + sweep * (i + 0.5) / bays
        parts.append(kits.finial(2.4, 0.5, p).translate(
            math.cos(a) * (radius + depth * 0.2), height + 3.0,
            math.sin(a) * (radius + depth * 0.2)))
    return Geo.concat(parts)
