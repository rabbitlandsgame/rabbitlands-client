"""Crownwater's architectural kit.

The shape language read off the concept: pale marble walls, verdigris copper
domes, gold finials, round-headed arcades, and every island meeting the water
through a built stone edge rather than a beach.

Companion to `crownkit.py`, the compatibility entry point for the shared
`amberwood.crownmaterials` palette. This region's landmark compositions
use the toolkit's own primitives and reusable civic recipes.

Walk surfaces are registered deliberately and sparingly, via
`MeshGroup.add_walk`: pavilion podiums, the cathedral portico and its stair,
causeway decks and quay aprons. Nothing else. Marking a whole landmark walkable
would let the client's downward grounding ray snap an actor onto a dome.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import stonework as SW
from amberwood import routecraft as RC
from amberwood import architecture as ARCH

from crownkit import GILT, IRON, MARBLE, MOSAIC, STONE, VERDIGRIS


def dome(radius: float, rise: float, segments: int = 24,
         material: str = VERDIGRIS, rings: int = 12,
         pointed: float = 0.86) -> M.Mesh:
    """A copper dome as a surface of revolution.

    `pointed` shapes the profile between a hemisphere (1.0) and a raised, more
    ogee outline (lower values), which is what the concept's domes actually are:
    they carry more of their height above the springing than a true hemisphere.
    """
    profile = []
    for k in range(rings + 1):
        a = (k / rings) * (math.pi * 0.5)
        profile.append([radius * math.cos(a) ** pointed, rise * math.sin(a)])
    return M.lathe(profile, segments, uv_scale=0.5, material=material)


def dome_soffit(radius: float, y: float, segments: int = 24,
                material: str = MARBLE) -> M.Mesh:
    """A flat soffit closing a dome from below.

    A lathed dome is a single surface, so on an open pavilion you would look
    straight up through its backface into an empty shell. This closes it for the
    cost of one triangle fan, far cheaper than a second inner shell.
    """
    return M.lathe([[0.0, y], [radius, y]], segments, uv_scale=0.5,
                   material=material)


def finial(height: float = 1.8, radius: float = 0.26,
           material: str = GILT) -> M.Mesh:
    """The gilt spike-and-ball every dome and tower in the concept is topped by."""
    return M.lathe([
        [radius * 1.5, 0.0], [radius * 1.2, height * 0.10],
        [radius * 1.9, height * 0.22], [radius * 1.3, height * 0.34],
        [radius * 0.5, height * 0.44], [radius * 0.9, height * 0.56],
        [radius * 0.28, height * 0.74], [0.0, height],
    ], 12, uv_scale=0.9, material=material)


def colonnade_ring(radius: float, count: int, height: float,
                   column_radius: float = 0.34,
                   material: str = MARBLE) -> M.Mesh:
    """A ring of columns - the open drum of a pavilion, or a drum gallery."""
    parts = []
    for i in range(count):
        angle = 2.0 * math.pi * i / count
        shaft = SW.column(height, radius=column_radius, material=material)
        parts.append(shaft.transformed(M.translation(
            radius * math.cos(angle), 0.0, radius * math.sin(angle))))
    return M.merge(parts, material)


def domed_pavilion(radius: float = 5.2, seed: int = 0,
                   columns: int = 10) -> SW.MeshGroup:
    """The signature building of the pavilion islets.

    A stepped marble podium, an open colonnaded drum, a verdigris dome and a
    gilt finial: the silhouette repeated around the ring in the aerial concept
    and shown close up in panel 5.
    """
    out = SW.MeshGroup()
    podium_h = 0.55
    for step in range(3):
        r = radius * (1.34 - step * 0.10)
        top = podium_h * (step + 1) / 3.0
        piece = M.lathe([[r, top - podium_h / 3.0], [r, top], [0.0, top]], 24,
                        uv_scale=0.6, material=MARBLE)
        if step == 2:
            out.add_walk(piece)
        else:
            out.add(piece)

    drum_h = 3.4
    out.add(colonnade_ring(radius * 0.86, columns, drum_h, material=MARBLE)
            .transformed(M.translation(0.0, podium_h, 0.0)))
    entab_y = podium_h + drum_h + 0.66
    out.add(M.lathe([[radius * 0.74, entab_y], [radius * 1.02, entab_y],
                     [radius * 1.02, entab_y + 0.40],
                     [radius * 0.90, entab_y + 0.52]], 24,
                    uv_scale=0.6, material=MARBLE))
    base_y = entab_y + 0.52
    out.add(dome_soffit(radius * 0.90, base_y, material=MARBLE))
    out.add(dome(radius * 0.92, radius * 0.86, segments=24, material=VERDIGRIS)
            .translate(0.0, base_y, 0.0))
    out.add(finial(radius * 0.34).translate(0.0, base_y + radius * 0.86, 0.0))
    return out


def campanile(height: float = 22.0, width: float = 3.6,
              seed: int = 0) -> SW.MeshGroup:
    """A slender marble bell tower with an arcaded belfry and a verdigris cap.

    Panel 9 looks out over one of these; in the aerial they break the dome line
    and give the city its vertical accents.
    """
    out = SW.MeshGroup()
    shaft_h = height * 0.74
    out.add(M.box((width, shaft_h, width), center=(0.0, shaft_h * 0.5, 0.0),
                  uv_scale=0.5, material=MARBLE))
    for k in range(1, 4):
        y = shaft_h * k / 4.0
        out.add(M.box((width * 1.10, 0.22, width * 1.10), center=(0.0, y, 0.0),
                      uv_scale=0.6, material=MARBLE))
    belfry_h = height * 0.16
    out.add(M.box((width * 1.16, 0.28, width * 1.16),
                  center=(0.0, shaft_h + 0.14, 0.0), uv_scale=0.6,
                  material=MARBLE))
    for i in range(4):
        angle = math.pi * 0.5 * i
        pier = M.box((width * 0.24, belfry_h, width * 0.24),
                     center=(0.0, shaft_h + 0.28 + belfry_h * 0.5, 0.0),
                     uv_scale=0.6, material=MARBLE)
        out.add(pier.transformed(
            M.rotation_y(angle) @ M.translation(width * 0.44, 0.0, width * 0.44)))
    cap_y = shaft_h + 0.28 + belfry_h
    out.add(M.box((width * 1.20, 0.26, width * 1.20), center=(0.0, cap_y, 0.0),
                  uv_scale=0.6, material=MARBLE))
    out.add(dome(width * 0.78, width * 0.92, segments=18, material=VERDIGRIS)
            .translate(0.0, cap_y + 0.13, 0.0))
    out.add(finial(width * 0.5).translate(0.0, cap_y + 0.13 + width * 0.92, 0.0))
    return out


def cathedral(seed: int = 0, scale: float = 1.0) -> SW.MeshGroup:
    """The crowned island's great domed complex - the region's hero landmark.

    A cruciform marble mass with a colonnaded west front, a great verdigris dome
    on a windowed drum, four lesser domes over the corner bays, and a broad
    walkable stair up to the portico. This is the silhouette the whole aerial is
    composed around, and the subject of panel 1.
    """
    out = SW.MeshGroup()
    s = scale
    body_w, body_d, body_h = 26.0 * s, 34.0 * s, 12.0 * s

    out.add(M.box((body_w, body_h, body_d), center=(0.0, body_h * 0.5, 0.0),
                  uv_scale=0.34, material=MARBLE))
    out.add(M.box((body_w * 1.52, body_h * 0.82, body_d * 0.34),
                  center=(0.0, body_h * 0.41, -body_d * 0.06),
                  uv_scale=0.34, material=MARBLE))
    out.add(M.box((body_w * 1.06, 0.70 * s, body_d * 1.04),
                  center=(0.0, body_h, 0.0), uv_scale=0.4, material=MARBLE))

    drum_r, drum_h = 8.6 * s, 6.2 * s
    drum_y = body_h + 0.35 * s
    crossing_z = -body_d * 0.06
    out.add(M.lathe([[drum_r, 0.0], [drum_r, drum_h],
                     [drum_r * 1.06, drum_h], [drum_r * 1.06, drum_h + 0.5 * s]],
                    28, uv_scale=0.5, material=MARBLE)
            .translate(0.0, drum_y, crossing_z))
    out.add(colonnade_ring(drum_r * 1.02, 16, drum_h * 0.86,
                           column_radius=0.30 * s, material=MARBLE)
            .transformed(M.translation(0.0, drum_y, crossing_z)))
    dome_y = drum_y + drum_h + 0.5 * s
    out.add(dome(drum_r * 1.06, drum_r * 1.24, segments=32, material=VERDIGRIS)
            .translate(0.0, dome_y, crossing_z))
    out.add(finial(3.4 * s).translate(0.0, dome_y + drum_r * 1.24, crossing_z))

    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            cx = sx * body_w * 0.34
            cz = sz * body_d * 0.32
            little_r = 3.5 * s
            out.add(M.lathe([[little_r, 0.0], [little_r, 2.0 * s]], 18,
                            uv_scale=0.5, material=MARBLE)
                    .translate(cx, body_h + 0.35 * s, cz))
            out.add(dome(little_r, little_r * 1.05, segments=20,
                         material=VERDIGRIS)
                    .translate(cx, body_h + 2.35 * s, cz))
            out.add(finial(1.5 * s).translate(
                cx, body_h + 2.35 * s + little_r * 1.05, cz))

    # west front: portico, pediment, and the ceremonial stair down to the plaza
    portico_z = body_d * 0.5 + 3.2 * s
    out.add(M.merge([
        SW.column(7.6 * s, radius=0.62 * s, material=MARBLE).transformed(
            M.translation(x * 4.2 * s, 0.0, portico_z))
        for x in (-2.5,-1.5,-0.5,0.5,1.5,2.5)], MARBLE))
    out.add(M.box((body_w * 1.02, 1.10 * s, 7.0 * s),
                  center=(0.0, 8.2 * s, portico_z - 0.6 * s),
                  uv_scale=0.4, material=MARBLE))
    out.add(M.gable_roof(body_w * 1.02, 7.0 * s, 3.0 * s, overhang=0.3 * s,
                         material=MARBLE)
            .translate(0.0, 8.75 * s, portico_z - 0.6 * s))
    out.add_walk(M.box((body_w * 1.02, 0.40 * s, 7.4 * s),
                       center=(0.0, 0.20 * s, portico_z - 0.6 * s),
                       uv_scale=0.5, material=MOSAIC))
    out.add_walk(RC.stair_flight(body_w*1.02,0.4*s,3.6*s,4,material=MARBLE)
                 .rotate_y(math.pi).translate(0,0,portico_z+6.7*s))
    out.add(ARCH.door(3.0*s,5.0*s,material="timber_dark")
            .translate(0,0.4*s,body_d*0.5+0.08*s))
    return out


def causeway(length: float, deck_height: float, width: float = 5.0,
             arches: int = 3, seed: int = 0, rise: float = 0.0) -> SW.MeshGroup:
    """A stone causeway spanning open water between two islands.

    Built on the toolkit's `high_bridge`, which already solves the hard part: the
    elevation is a solid wall whose underside follows the arch intrados, so the
    openings are real voids in real masonry rather than floating arch rings.
    Crownwater adds the marble balustrade and the mosaic deck that make it read
    as a civic causeway rather than a country bridge.

    `rise` is how much higher the far end stands than the near one. The span is
    built level and then sheared, which lifts the deck, the parapets and the
    arch crowns along its length and leaves every pier standing upright - which
    is how a sloping viaduct is built and how one looks. A causeway with no
    rise is untouched, so the flat ones are the meshes they always were.

    The deck is the only registered walk surface, so the grounding ray lands on
    it and never on a parapet or an arch crown.
    """
    out = SW.MeshGroup()
    out.add(SW.high_bridge(length=length, deck_height=deck_height, width=width,
                           arches=arches, seed=seed, pier_foot=-3.0))
    for side in (-1.0, 1.0):
        out.add(SW.balustrade(length, height=1.02, material=MARBLE)
                .transformed(M.translation(0.0, deck_height,
                                           side * (width * 0.5 - 0.22))))
    out.add_walk(M.box((length, 0.22, width - 0.9),
                       center=(0.0, deck_height + 0.08, 0.0),
                       uv_scale=0.5, material=MOSAIC))
    if abs(rise) > 1e-6 and length > 1e-6:
        shear = np.eye(4)
        shear[1, 0] = rise / length      # y += (rise / length) * x
        out = out.transformed(shear)
    return out


def quay_edge(length: float, height: float = 1.5, seed: int = 0) -> SW.MeshGroup:
    """A built stone waterfront: face, coping and a walkable apron.

    Crownwater's islands meet the water through masonry, not sand. Panels 2, 6
    and 10 are all this edge at three different distances.
    """
    out = SW.MeshGroup()
    out.add(M.box((length, height-0.08, 1.6), center=(0.0, (height-0.08) * 0.5, 0.0),
                  uv_scale=0.6, material=STONE))
    out.add(M.box((length, 0.34, 2.1), center=(0.0, height + 0.09, 0.0),
                  uv_scale=0.6, material=MARBLE))
    out.add_walk(M.box((length-0.08, 0.18, 3.4),
                       center=(0.0, height + 0.22, -1.6),
                       uv_scale=0.5, material=MOSAIC))
    return out


def bollard(height: float = 0.72, radius: float = 0.17) -> M.Mesh:
    """The brass mooring bollard of panel 10 - in close-up, the whole subject."""
    return M.lathe([
        [radius * 1.30, 0.0], [radius * 1.30, height * 0.10],
        [radius * 1.00, height * 0.18], [radius * 1.00, height * 0.66],
        [radius * 1.34, height * 0.78], [radius * 1.24, height * 0.90],
        [radius * 0.72, height], [0.0, height * 1.02],
    ], 14, uv_scale=1.4, material=GILT)


def mooring_ring(radius: float = 0.22) -> M.Mesh:
    """An iron ring set into a quay face."""
    path = np.asarray([[math.cos(a) * radius, math.sin(a) * radius, 0.0]
                       for a in np.linspace(0.0, 2.0 * math.pi, 13)])
    return M.tube(path, [0.035] * 13, segments=6, material=IRON)


def banner_pole(height: float = 6.4, seed: int = 0) -> SW.MeshGroup:
    """A quayside standard with a hanging banner - panels 1 and 6."""
    out = SW.MeshGroup()
    out.add(M.cylinder(0.11, 0.08, height, 10, uv_scale=0.8, material=IRON))
    out.add(finial(0.9, radius=0.14).translate(0.0, height, 0.0))
    # canvas rather than woven_cloth: the wool is dark enough that a banner
    # reads as a black slab against a bright sky, and four of them stood across
    # the harbour panel like shutters
    out.add(M.box((0.06, height * 0.42, 1.5),
                  center=(0.0, height * 0.70, 0.78),
                  uv_scale=1.0, material="canvas_awning"))
    return out


def moored_boat(length: float = 6.4, seed: int = 0) -> SW.MeshGroup:
    """A small lagoon boat, for the quaysides of panels 2, 6 and 10."""
    out = SW.MeshGroup()
    beam = length * 0.28
    sections = []
    for k in range(9):
        t = k / 8.0
        taper = math.sin(math.pi * (0.12 + 0.76 * t))
        z = -length * 0.5 + length * t
        ring = []
        for a in np.linspace(0.0, math.pi, 7):
            ring.append([math.cos(a) * beam * 0.5 * taper,
                         0.42 - math.sin(a) * 0.42 * taper, z])
        sections.append(np.asarray(ring))
    hull = M.loft(sections, closed_rings=False, cap_ends=False,
                  material="timber_dark")
    out.add(hull)
    out.add(M.box((beam * 0.72, 0.10, length * 0.52),
                  center=(0.0, 0.40, 0.0), uv_scale=0.8, material="timber_warm"))
    out.add(M.cylinder(0.07, 0.05, length * 0.62, 8, uv_scale=0.8,
                       material="timber_warm").translate(0.0, 0.44, 0.0))
    return out


def customs_house(width: float = 17.0, depth: float = 22.0, seed: int = 0
                  ) -> SW.MeshGroup:
    """The harbour islet's bonded warehouse - the door to the customs hall.

    Deliberately the plainest building in the region: ashlar base, plastered
    upper wall, slate roof, one wide cargo door and a row of shuttered windows.
    Crownwater's marble is for its monuments; a warehouse is built to keep rain
    off crates.
    """
    out = SW.MeshGroup()
    base_h, wall_h = 1.4, 6.2
    out.add(M.box((width, base_h, depth), center=(0.0, base_h * 0.5, 0.0),
                  uv_scale=0.5, material=STONE))
    out.add(M.box((width - 0.6, wall_h, depth - 0.6),
                  center=(0.0, base_h + wall_h * 0.5, 0.0),
                  uv_scale=0.4, material="lime_plaster"))
    out.add(M.box((width + 0.5, 0.4, depth + 0.5),
                  center=(0.0, base_h + wall_h, 0.0), uv_scale=0.5,
                  material=MARBLE))
    out.add(M.gable_roof(width + 1.0, depth + 1.0, 3.6, overhang=0.5,
                         material=VERDIGRIS)
            .translate(0.0, base_h + wall_h + 0.4, 0.0))
    # cargo door on the quay face, and a loading beam over it
    out.add(M.box((4.4, 4.6, 0.5), center=(0.0, base_h + 2.3, depth * 0.5),
                  uv_scale=0.6, material="timber_dark"))
    out.add(M.box((0.35, 0.35, 2.2), center=(0.0, base_h + 5.6, depth * 0.5 + 0.9),
                  uv_scale=0.8, material="timber_dark"))
    for side in (-1.0, 1.0):
        for k in range(3):
            out.add(M.box((0.4, 1.5, 1.2),
                          center=(side * (width * 0.5 - 0.1), base_h + 3.4,
                                  -6.0 + k * 6.0),
                          uv_scale=0.8, material="timber_dark"))
    out.add(finial(1.6).translate(0.0, base_h + wall_h + 4.0, 0.0))
    return out
