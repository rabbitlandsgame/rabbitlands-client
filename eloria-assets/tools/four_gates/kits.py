"""Original modular asset kits for the Four Gates region.

Every kit is authored in local space with its origin at the base centre and +Y
up, so it can be instanced anywhere on the plateau.  Shapes are derived from the
supplied Four Gates concept board: battered limestone masonry, twin-drum
gatehouses with gold crowns, verdigris turret roofs, deep-blue gate-star banners,
sapphire beacon crystals and arcaded civic halls.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

import meshlib as M
from meshlib import Geo

TAU = math.pi * 2.0


class Palette:
    """Resolves material names to glTF material indices for the kits."""

    def __init__(self, mapping: Dict[str, int]):
        self._m = mapping

    def __getattr__(self, name):
        try:
            return self._m[name]
        except KeyError as exc:  # pragma: no cover - authoring guard
            raise AttributeError(f"unknown material {name!r}") from exc


# ----------------------------------------------------------------- ornament
def moulding(width: float, depth: float, height: float, p: Palette,
             material: Optional[int] = None, steps: int = 3) -> Geo:
    """Stepped cornice band."""
    material = p.stone_trim if material is None else material
    parts = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        w = width * (1.0 + 0.075 * t)
        d = depth * (1.0 + 0.075 * t)
        slab = M.box(w, height / steps, d, material, 1.5, origin="corner")
        slab.translate(0.0, height * i / steps, 0.0)
        parts.append(slab)
    return Geo.concat(parts)


def finial(height: float, radius: float, p: Palette, crystal: bool = True) -> Geo:
    parts = [M.revolve([(radius * 0.9, 0.0), (radius * 1.15, height * 0.16),
                        (radius * 0.55, height * 0.32), (radius * 0.72, height * 0.5),
                        (radius * 0.30, height * 0.72), (0.0, height * 0.78)],
                       10, p.metal_gold, 0.8)]
    if crystal:
        gem = M.revolve([(0.0, 0.0), (radius * 0.52, height * 0.22),
                         (radius * 0.30, height * 0.62), (0.0, height * 0.9)],
                        8, p.crystal_blue, 0.8)
        gem.translate(0.0, height * 0.70, 0.0)
        parts.append(gem)
    return Geo.concat(parts)


def banner(width: float, length: float, p: Palette, pole: bool = True,
           pole_height: Optional[float] = None) -> Geo:
    """Hanging blue gate-star banner with a light catenary sag."""
    segments = 7
    verts, faces = [], []
    for i in range(segments + 1):
        t = i / segments
        y = -length * t
        bulge = math.sin(t * math.pi) * width * 0.05
        for side in (-1, 1):
            verts.append((side * width * 0.5, y, bulge))
    for i in range(segments):
        a, b = i * 2, i * 2 + 1
        c, d = (i + 1) * 2, (i + 1) * 2 + 1
        faces += [(a, b, d), (a, d, c)]
    cloth = M.make(verts, faces, p.cloth_banner, 1.0)
    cloth.t = np.stack([(cloth.v[:, 0] / width) + 0.5,
                        (-cloth.v[:, 1] / length)], axis=1).astype(np.float32)
    parts = [cloth]
    rail = M.cylinder(width * 0.045, width * 1.06, 6, p.metal_gold, 0.5)
    rail.rotate_z(math.pi / 2).translate(width * 0.53, 0.02, 0.0)
    parts.append(rail)
    if pole:
        h = pole_height if pole_height is not None else length * 0.22
        mast = M.cylinder(width * 0.05, h, 6, p.metal_gold, 0.6)
        parts.append(mast)
    return Geo.concat(parts)


def crystal_lamp(height: float, p: Palette, scale: float = 1.0) -> Geo:
    post = M.revolve([(0.16, 0.0), (0.22, 0.12), (0.11, 0.30),
                      (0.13, height * 0.82), (0.20, height * 0.88)],
                     8, p.metal_iron, 0.8)
    arm = M.revolve([(0.0, 0.0), (0.30, 0.10), (0.34, 0.30), (0.16, 0.48), (0.0, 0.54)],
                    8, p.metal_gold, 0.6)
    arm.translate(0.0, height * 0.86, 0.0)
    gem = M.revolve([(0.0, 0.0), (0.19, 0.16), (0.13, 0.40), (0.0, 0.56)],
                    8, p.crystal_blue, 0.5)
    gem.translate(0.0, height * 0.92, 0.0)
    return Geo.concat([post, arm, gem]).scale(scale, scale, scale)


def hooded_statue(height: float, p: Palette) -> Geo:
    """Robed sentinel figure -- the gate guardians of the ceremonial avenue."""
    plinth = M.box(1.5, 0.9, 1.5, p.stone_trim, 1.2, origin="corner")
    body = M.revolve([(0.62, 0.0), (0.66, height * 0.10), (0.50, height * 0.46),
                      (0.42, height * 0.66), (0.34, height * 0.76), (0.30, height * 0.80),
                      (0.26, height * 0.86), (0.0, height * 0.90)],
                     10, p.stone_marble, 1.4)
    body.translate(0.0, 0.9, 0.0)
    hood = M.revolve([(0.0, 0.0), (0.30, 0.10), (0.34, 0.26), (0.24, 0.40), (0.0, 0.46)],
                     10, p.stone_marble, 1.0)
    hood.translate(0.0, 0.9 + height * 0.74, 0.0)
    shoulder = M.revolve([(0.0, 0.0), (0.50, 0.06), (0.44, 0.22), (0.30, 0.30)],
                         10, p.stone_marble, 1.0)
    shoulder.translate(0.0, 0.9 + height * 0.60, 0.0)
    staff = M.cylinder(0.07, height * 0.86, 6, p.stone_trim, 0.8)
    staff.translate(0.52, 0.9, 0.18)
    return Geo.concat([plinth, body, shoulder, hood, staff])


def winged_crest(span: float, p: Palette) -> Geo:
    """Gilded winged figure crowning the gate keystones."""
    torso = M.revolve([(0.28, 0.0), (0.34, 0.5), (0.22, 1.3), (0.18, 1.7), (0.0, 1.95)],
                      8, p.metal_gold, 0.8)
    head = M.icosphere(0.24, 1, p.metal_gold, 0.6)
    head.translate(0.0, 1.86, 0.0)
    parts = [torso, head]
    for side in (-1, 1):
        wing_profile = [(0.0, 0.0), (span * 0.30, 0.32), (span * 0.46, 0.20),
                        (span * 0.50, -0.30), (span * 0.28, -0.42), (0.0, -0.22)]
        wing = M.prism(wing_profile, 0.14, p.metal_gold, 1.0)
        wing.rotate_x(-math.pi / 2)
        wing.scale(side, 1.0, 1.0)
        wing.translate(side * 0.22, 1.28, 0.0)
        parts.append(wing)
    return Geo.concat(parts)


# ------------------------------------------------------------------- masonry
def wall_segment(length: float, height: float, thickness: float, p: Palette,
                 crenellations: bool = True, arcade: bool = True) -> Geo:
    """Battered curtain-wall bay with an inner arcade and a crenellated walk."""
    parts = []
    body = M.tapered_box(thickness * 1.22, length, thickness, length,
                         height, p.stone_ashlar, 4.0)
    parts.append(body)
    plinth = M.tapered_box(thickness * 1.45, length * 1.005, thickness * 1.24,
                           length * 1.005, 2.2, p.stone_rubble, 3.0)
    parts.append(plinth)
    # Band and parapet run a little past the bay so their end caps clear the
    # body's. Cut to the bay length exactly, all three sat in one plane at each
    # joint and fought over the strip where they overlap.
    cap_length = length + 0.24
    band = M.box(thickness * 1.16, 0.85, cap_length, p.stone_trim, 2.0, origin="corner")
    band.translate(0.0, height - 1.5, 0.0)
    parts.append(band)
    walk = M.box(thickness * 1.10, 0.5, cap_length, p.paving_road, 2.0, origin="corner")
    walk.translate(0.0, height - 0.65, 0.0)
    parts.append(walk)
    if crenellations:
        merlon_count = max(2, int(length / 5.4))
        step = length / merlon_count
        for i in range(merlon_count):
            z = -length * 0.5 + step * (i + 0.5)
            for side in (-1, 1):
                merlon = M.box(thickness * 0.40, 2.3, step * 0.62, p.stone_ashlar,
                               1.8, origin="corner")
                merlon.translate(side * thickness * 0.36, height - 0.2, z)
                parts.append(merlon)
                cap = M.box(thickness * 0.48, 0.32, step * 0.70, p.stone_trim,
                            1.5, origin="corner")
                cap.translate(side * thickness * 0.36, height + 2.1, z)
                parts.append(cap)
    if arcade:
        bay_count = max(1, int(length / 6.0))
        step = length / bay_count
        for i in range(bay_count):
            z = -length * 0.5 + step * (i + 0.5)
            for side in (-1, 1):
                arch = M.arch_ring(step * 0.26, step * 0.36, 0.35, 0.0, math.pi, 8,
                                   p.stone_trim, 2.0)
                arch.rotate_y(math.pi / 2 * side)
                arch.translate(side * (thickness * 0.61), height * 0.44, z)
                parts.append(arch)
                recess = M.box(0.30, height * 0.44, step * 0.52, p.stone_rubble, 2.0,
                               origin="corner")
                recess.translate(side * (thickness * 0.55), 0.0, z)
                parts.append(recess)
    return Geo.concat(parts)


def wall_tower(radius: float, height: float, p: Palette, roofed: bool = True) -> Geo:
    parts = []
    base = M.cylinder(radius * 1.22, 3.0, 12, p.stone_rubble, 3.0)
    drum = M.cylinder(radius, height, 12, p.stone_ashlar, 4.0, top_radius=radius * 0.94)
    parts += [base, drum]
    corbel = M.cylinder(radius * 1.16, 1.1, 12, p.stone_trim, 2.0)
    corbel.translate(0.0, height - 1.4, 0.0)
    parts.append(corbel)
    merlons = 10
    for i in range(merlons):
        a = TAU * i / merlons
        merlon = M.box(1.0, 1.7, 1.5, p.stone_ashlar, 1.6, origin="corner")
        merlon.rotate_y(-a)
        merlon.translate(math.cos(a) * radius * 1.02, height - 0.3, math.sin(a) * radius * 1.02)
        parts.append(merlon)
    if roofed:
        roof = M.cone(radius * 1.20, radius * 1.5, 12, p.roof_verdigris, 2.2)
        roof.translate(0.0, height + 1.5, 0.0)
        parts.append(roof)
        parts.append(finial(2.4, 0.5, p).translate(0.0, height + 1.5 + radius * 1.5, 0.0))
    return Geo.concat(parts)


def portcullis(p: Palette, opening: float = 12.0, height: float = 16.0) -> Geo:
    """Iron gate grille -- a separate node so it can be animated."""
    grid = []
    bars_x = max(4, int(opening / 1.15))
    for i in range(bars_x + 1):
        x = -opening * 0.5 + opening * i / bars_x
        bar = M.box(0.18, height, 0.18, p.metal_iron, 0.8, origin="corner")
        bar.translate(x, 0.0, 0.0)
        grid.append(bar)
    for j in range(4):
        y = height * (j + 0.5) / 4.0
        rail = M.box(opening + 0.3, 0.18, 0.18, p.metal_iron, 0.8, origin="corner")
        rail.translate(0.0, y, 0.0)
        grid.append(rail)
    for i in range(bars_x + 1):
        x = -opening * 0.5 + opening * i / bars_x
        spike = M.cone(0.13, 0.5, 5, p.metal_iron, 0.4)
        spike.rotate_x(math.pi)
        spike.translate(x, 0.0, 0.0)
        grid.append(spike)
    return Geo.concat(grid)


def gatehouse(p: Palette, width: float = 44.0, depth: float = 20.0,
              height: float = 30.0, opening: float = 12.0,
              tower_radius: float = 7.0, banners: bool = True,
              crest: bool = True, variant: int = 0) -> Geo:
    """Twin-drum monumental gate: the signature Four Gates landmark.

    Local axes: the passage runs along +/-Z, the towers sit on +/-X.
    """
    parts: List[Geo] = []
    half = width * 0.5
    pier = half - tower_radius * 1.4

    # solid flanking piers with a barrel-vaulted passage between them
    for side in (-1, 1):
        block = M.tapered_box(half - opening * 0.5, depth * 1.02,
                              (half - opening * 0.5) * 0.90, depth * 0.96,
                              height * 0.78, p.stone_ashlar, 4.0)
        block.translate(side * (opening * 0.5 + (half - opening * 0.5) * 0.5), 0.0, 0.0)
        parts.append(block)
        base = M.tapered_box(half - opening * 0.5 + 2.0, depth * 1.10,
                             half - opening * 0.5 + 0.6, depth * 1.04,
                             4.0, p.stone_rubble, 3.0)
        base.translate(side * (opening * 0.5 + (half - opening * 0.5) * 0.5), 0.0, 0.0)
        parts.append(base)

    # arch over the passage, front and back rings plus the barrel intrados
    arch_span = opening * 0.5
    springing = height * 0.36
    for z in (-depth * 0.5, depth * 0.5):
        ring = M.arch_ring(arch_span, arch_span + 1.8, 1.6, 0.0, math.pi, 12,
                           p.stone_trim, 2.5)
        ring.translate(0.0, springing, z)
        parts.append(ring)
    barrel = M.arch_ring(arch_span, arch_span + 0.9, depth * 0.98, 0.0, math.pi, 12,
                         p.stone_ashlar, 3.0)
    barrel.translate(0.0, springing, 0.0)
    parts.append(barrel)
    for side in (-1, 1):
        jamb = M.box(1.8, springing, depth * 0.98, p.stone_trim, 2.0, origin="corner")
        jamb.translate(side * (arch_span + 0.9), 0.0, 0.0)
        parts.append(jamb)
    # spandrel wall above the arch closes the front elevation
    for z in (-depth * 0.5 - 0.3, depth * 0.5 - 0.3):
        spandrel = M.box(opening + 3.6, height * 0.78 - (springing + arch_span + 1.8),
                         0.6, p.stone_ashlar, 3.0, origin="corner")
        spandrel.translate(0.0, springing + arch_span + 1.8, z)
        parts.append(spandrel)

    # winch drums either side of the passage mouth
    for side in (-1, 1):
        drum_axle = M.cylinder(0.7, 1.4, 10, p.metal_gold, 0.8)
        drum_axle.rotate_z(math.pi / 2)
        drum_axle.translate(side * (arch_span + 0.6), springing + arch_span + 1.2,
                            -depth * 0.30)
        parts.append(drum_axle)

    # entablature, cornice and attic
    parts.append(moulding(width * 0.92, depth * 1.06, 1.9, p, steps=4).translate(
        0.0, height * 0.78, 0.0))
    attic = M.tapered_box(width * 0.84, depth * 0.92, width * 0.80, depth * 0.88,
                          height * 0.16, p.stone_ashlar, 3.5)
    attic.translate(0.0, height * 0.78 + 1.9, 0.0)
    parts.append(attic)
    parts.append(moulding(width * 0.86, depth * 0.94, 1.1, p).translate(
        0.0, height * 0.78 + 1.9 + height * 0.16, 0.0))

    top = height * 0.78 + 3.0 + height * 0.16
    # attic merlons
    for i in range(9):
        x = -width * 0.36 + width * 0.72 * i / 8.0
        for z in (-depth * 0.42, depth * 0.42):
            merlon = M.box(width * 0.055, 1.5, 1.1, p.stone_ashlar, 1.4, origin="corner")
            merlon.translate(x, top, z)
            parts.append(merlon)

    # flanking drum towers with verdigris cones
    tower_height = height * 1.16
    for side in (-1, 1):
        x = side * (half + tower_radius * 0.30)
        drum = M.cylinder(tower_radius, tower_height, 14, p.stone_ashlar, 4.0,
                          top_radius=tower_radius * 0.93)
        drum.translate(x, 0.0, 0.0)
        plinth = M.cylinder(tower_radius * 1.20, 4.5, 14, p.stone_rubble, 3.0)
        plinth.translate(x, 0.0, 0.0)
        corbel = M.cylinder(tower_radius * 1.16, 1.3, 14, p.stone_trim, 2.0)
        corbel.translate(x, tower_height - 1.6, 0.0)
        crown = M.cylinder(tower_radius * 1.10, 2.6, 14, p.metal_gold, 2.0,
                           top_radius=tower_radius * 1.02)
        crown.translate(x, tower_height - 0.3, 0.0)
        roof = M.cone(tower_radius * 1.06, tower_radius * 1.9, 14, p.roof_verdigris, 2.4)
        roof.translate(x, tower_height + 2.3, 0.0)
        parts += [plinth, drum, corbel, crown, roof]
        parts.append(finial(3.0, 0.62, p).translate(
            x, tower_height + 2.3 + tower_radius * 1.9, 0.0))
        # arrow slits
        for j in range(3):
            slit = M.box(0.5, 2.4, 0.9, p.metal_iron, 0.8, origin="corner")
            slit.translate(x + side * tower_radius * 0.93, tower_height * 0.42 + j * 5.0,
                           -0.45)
            parts.append(slit)

    # small turrets on the attic corners
    for sx in (-1, 1):
        for sz in (-1, 1):
            tx = sx * width * 0.33
            tz = sz * depth * 0.30
            turret = M.cylinder(2.0, 6.0, 10, p.stone_ashlar, 3.0)
            turret.translate(tx, top, tz)
            cap = M.cone(2.3, 3.4, 10, p.roof_verdigris, 2.0)
            cap.translate(tx, top + 6.0, tz)
            parts += [turret, cap]

    if crest:
        parts.append(winged_crest(4.6, p).scale(1.5, 1.5, 1.5).translate(
            0.0, top + 1.6, 0.0))
        pedestal = M.box(3.4, 1.6, 3.0, p.stone_trim, 1.5, origin="corner")
        pedestal.translate(0.0, top, 0.0)
        parts.append(pedestal)

    if banners:
        for side in (-1, 1):
            for z in (-depth * 0.52, depth * 0.52):
                flag = banner(3.4, 21.0, p, pole=False)
                flag.translate(side * (opening * 0.5 + 6.2), height * 0.86, z)
                parts.append(flag)
            # a second pair hangs from the flanking drums
            for z in (-depth * 0.30, depth * 0.30):
                drum_flag = banner(2.6, 16.0, p, pole=False)
                drum_flag.translate(side * (half + tower_radius * 0.30
                                            + tower_radius * 0.96),
                                    height * 0.96, z)
                parts.append(drum_flag)

    # gate-star roundel over the arch: a moulded ring carrying a sapphire boss
    for z in (-depth * 0.52, depth * 0.52):
        sign = 1.0 if z > 0 else -1.0
        ring = M.torus_arc(2.9, 0.42, 0.0, TAU, 20, 6, p.metal_gold, 1.0)
        ring.rotate_x(math.pi / 2)
        ring.translate(0.0, springing + arch_span + 4.4, z + sign * 0.30)
        parts.append(ring)
        plate = M.revolve([(0.0, 0.0), (2.55, 0.0), (2.55, 0.34), (0.0, 0.34)],
                          20, p.stone_trim, 1.6)
        plate.rotate_x(-math.pi / 2 * sign)
        plate.translate(0.0, springing + arch_span + 4.4, z + sign * 0.16)
        parts.append(plate)
        for k in range(4):
            petal = M.revolve([(0.0, 0.0), (0.52, 0.30), (0.30, 0.9), (0.0, 1.15)],
                              8, p.metal_gold, 0.6)
            petal.rotate_x(-math.pi / 2 * sign)
            angle_k = TAU * k / 4
            petal.translate(math.cos(angle_k) * 1.15,
                            springing + arch_span + 4.4 + math.sin(angle_k) * 1.15,
                            z + sign * 0.42)
            parts.append(petal)
        gem = M.revolve([(0.0, 0.0), (0.72, 0.26), (0.44, 0.62), (0.0, 0.86)],
                        8, p.crystal_blue, 0.7)
        gem.rotate_x(-math.pi / 2 * sign)
        gem.translate(0.0, springing + arch_span + 4.4, z + sign * 0.46)
        parts.append(gem)

    if variant == 1:      # inner gates carry a lighter, taller attic
        lantern = M.cylinder(3.0, 5.0, 10, p.stone_trim, 2.0)
        lantern.translate(0.0, top + 1.4, 0.0)
        cap = M.cone(3.4, 4.2, 10, p.roof_verdigris, 2.0)
        cap.translate(0.0, top + 6.4, 0.0)
        parts += [lantern, cap]
    return Geo.concat(parts)


# ------------------------------------------------------------------ buildings
def townhouse(p: Palette, width: float, depth: float, storeys: int = 3,
              variant: int = 0, roof_material: Optional[int] = None) -> Geo:
    """Concept-derived civic townhouse: ashlar ground floor, rendered upper
    storeys, verdigris or slate pitched roof, balcony and chimney."""
    storey_height = 3.6
    body_height = storey_height * storeys
    roof_material = p.roof_verdigris if roof_material is None else roof_material
    # The cornice is the last course of the elevation, not a band laid over it:
    # the wall it caps stops at its soffit. Running the wall to the cornice's own
    # top instead left two up-facing surfaces in the same plane on every house in
    # the city, and they fought.
    cornice_height = 0.5
    parts = []
    plinth = M.box(width + 0.5, 0.7, depth + 0.5, p.stone_rubble, 2.0, origin="corner")
    parts.append(plinth)
    ground_height = storey_height if storeys > 1 else storey_height - cornice_height
    ground = M.box(width, ground_height, depth, p.stone_ashlar, 3.0, origin="corner")
    ground.translate(0.0, 0.7, 0.0)
    parts.append(ground)
    if storeys > 1:
        upper = M.box(width * 0.99, body_height - storey_height - cornice_height,
                      depth * 0.99, p.plaster_warm, 3.0, origin="corner")
        upper.translate(0.0, 0.7 + storey_height, 0.0)
        parts.append(upper)
        band = M.box(width + 0.35, 0.35, depth + 0.35, p.stone_trim, 1.5, origin="corner")
        band.translate(0.0, 0.7 + storey_height - 0.18, 0.0)
        parts.append(band)
    cornice = M.box(width + 0.6, cornice_height, depth + 0.6, p.stone_trim, 1.5,
                    origin="corner")
    cornice.translate(0.0, 0.7 + body_height - cornice_height, 0.0)
    parts.append(cornice)

    # windows: recessed reveals, never floating decals
    for storey in range(storeys):
        y = 0.7 + storey * storey_height + 1.1
        count = max(1, int(width / 2.6))
        for i in range(count):
            x = -width * 0.5 + width * (i + 0.5) / count
            for sz, zpos in ((1, depth * 0.5), (-1, -depth * 0.5)):
                reveal = M.box(1.35, 1.9, 0.5, p.stone_trim, 1.2, origin="corner")
                reveal.translate(x, y, zpos - sz * 0.12)
                pane = M.box(1.05, 1.6, 0.22, p.glass_window, 1.0, origin="corner")
                pane.translate(x, y + 0.15, zpos - sz * 0.30)
                parts += [reveal, pane]
    # door
    door = M.box(1.6, 2.5, 0.45, p.timber_dark, 1.0, origin="corner")
    door.translate(0.0, 0.7, depth * 0.5 - 0.1)
    lintel = M.arch_ring(0.9, 1.35, 0.5, 0.0, math.pi, 8, p.stone_trim, 1.2)
    lintel.translate(0.0, 3.2, depth * 0.5 - 0.05)
    parts += [door, lintel]

    if variant % 3 == 0 and storeys > 2:
        balcony = M.box(width * 0.62, 0.3, 1.5, p.stone_trim, 1.2, origin="corner")
        balcony.translate(0.0, 0.7 + storey_height * 2 - 0.2, depth * 0.5 + 0.55)
        parts.append(balcony)
        for i in range(6):
            x = -width * 0.28 + width * 0.56 * i / 5.0
            baluster = M.cylinder(0.075, 1.0, 6, p.metal_gold, 0.6)
            baluster.translate(x, 0.7 + storey_height * 2 + 0.1, depth * 0.5 + 1.2)
            parts.append(baluster)
        rail = M.box(width * 0.62, 0.14, 0.2, p.metal_gold, 0.8, origin="corner")
        rail.translate(0.0, 0.7 + storey_height * 2 + 1.1, depth * 0.5 + 1.2)
        parts.append(rail)

    roof_h = 2.2 + (width + depth) * 0.09
    top = 0.7 + body_height
    if variant % 4 == 3:
        roof = M.hip_roof(width, depth, roof_h, 0.45, 0.55, roof_material, 2.4)
    else:
        roof = M.gable_roof(width, depth, roof_h, 0.55, roof_material, 2.4,
                            ridge_along_x=width >= depth)
    roof.translate(0.0, top, 0.0)
    parts.append(roof)
    ridge = M.box(width * 0.4 if width >= depth else 0.5, 0.3,
                  0.5 if width >= depth else depth * 0.4, p.metal_gold, 1.0,
                  origin="corner")
    ridge.translate(0.0, top + roof_h - 0.1, 0.0)
    parts.append(ridge)

    chimney = M.box(1.0, roof_h + 1.9, 1.0, p.stone_ashlar, 1.5, origin="corner")
    chimney.translate(width * 0.28, top - 0.4, -depth * 0.22)
    cap = M.box(1.35, 0.3, 1.35, p.stone_trim, 1.0, origin="corner")
    cap.translate(width * 0.28, top + roof_h + 1.5, -depth * 0.22)
    parts += [chimney, cap]
    if variant % 5 == 1:
        parts.append(finial(1.8, 0.32, p, crystal=True).translate(
            0.0, top + roof_h, depth * 0.30))
    return Geo.concat(parts)


def civic_hall(p: Palette, width: float = 26.0, depth: float = 18.0,
               variant: int = 0) -> Geo:
    """Arcaded civic hall with a verdigris dome, as seen around the plaza."""
    parts = []
    podium = M.box(width + 3.0, 1.6, depth + 3.0, p.stone_rubble, 2.5, origin="corner")
    parts.append(podium)
    steps = M.stairs(width * 0.5, 1.6, 3.0, 4, p.stone_trim, 1.5)
    steps.translate(0.0, 0.0, depth * 0.5 + 3.0)
    parts.append(steps)
    body = M.box(width, 12.0, depth, p.stone_ashlar, 4.0, origin="corner")
    body.translate(0.0, 1.6, 0.0)
    parts.append(body)
    # colonnade across the entrance front
    columns = max(4, int(width / 4.0))
    for i in range(columns):
        x = -width * 0.5 + width * (i + 0.5) / columns
        shaft = M.revolve([(0.62, 0.0), (0.55, 0.8), (0.50, 8.4), (0.62, 9.0),
                           (0.72, 9.4), (0.70, 10.0)], 10, p.stone_trim, 2.0)
        shaft.translate(x, 1.6, depth * 0.5 + 1.2)
        parts.append(shaft)
    architrave = M.box(width + 2.4, 1.5, 3.0, p.stone_trim, 2.0, origin="corner")
    architrave.translate(0.0, 11.6, depth * 0.5 + 1.2)
    parts.append(architrave)
    for i in range(columns - 1):
        x = -width * 0.5 + width * (i + 1.0) / columns
        arch = M.arch_ring(width / columns * 0.34, width / columns * 0.46, 2.6,
                           0.0, math.pi, 8, p.stone_trim, 2.0)
        arch.translate(x, 9.4, depth * 0.5 + 1.2)
        parts.append(arch)
    parts.append(moulding(width + 1.6, depth + 1.6, 1.6, p).translate(0.0, 13.6, 0.0))
    # pediment
    ped = M.gable_roof(width + 2.4, 3.2, 3.0, 0.2, p.stone_trim, 2.0, ridge_along_x=True)
    ped.translate(0.0, 13.1, depth * 0.5 + 1.2)
    parts.append(ped)

    drum_r = min(width, depth) * 0.30
    drum = M.cylinder(drum_r, 5.0, 16, p.stone_ashlar, 3.0)
    drum.translate(0.0, 15.2, -depth * 0.06)
    parts.append(drum)
    for i in range(10):
        a = TAU * i / 10
        window = M.box(0.7, 2.4, 0.6, p.glass_window, 1.0, origin="corner")
        window.rotate_y(-a)
        window.translate(math.cos(a) * drum_r * 0.98, 16.2, math.sin(a) * drum_r * 0.98 - depth * 0.06)
        parts.append(window)
    dome_profile = [(drum_r * 1.06, 0.0)]
    for i in range(1, 9):
        t = i / 8.0
        dome_profile.append((drum_r * 1.06 * math.cos(t * math.pi / 2),
                             drum_r * 1.15 * math.sin(t * math.pi / 2)))
    dome = M.revolve(dome_profile, 16, p.roof_verdigris, 2.6)
    dome.translate(0.0, 20.2, -depth * 0.06)
    parts.append(dome)
    lantern = M.cylinder(drum_r * 0.30, 2.4, 10, p.stone_trim, 1.5)
    lantern.translate(0.0, 20.2 + drum_r * 1.10, -depth * 0.06)
    parts.append(lantern)
    parts.append(finial(3.2, 0.6, p).translate(0.0, 22.4 + drum_r * 1.10, -depth * 0.06))
    if variant % 2 == 1:
        for side in (-1, 1):
            wing = M.box(6.0, 8.0, depth * 0.7, p.stone_ashlar, 3.0, origin="corner")
            wing.translate(side * (width * 0.5 + 3.0), 1.6, 0.0)
            wing_roof = M.gable_roof(6.6, depth * 0.7 + 0.6, 2.4, 0.4,
                                     p.roof_verdigris, 2.2, ridge_along_x=False)
            wing_roof.translate(side * (width * 0.5 + 3.0), 9.6, 0.0)
            parts += [wing, wing_roof]
    return Geo.concat(parts)


def market_hall(p: Palette, width: float = 20.0, depth: float = 13.0) -> Geo:
    parts = []
    base = M.box(width + 1.2, 0.6, depth + 1.2, p.stone_rubble, 2.0, origin="corner")
    body = M.box(width, 6.5, depth, p.stone_ashlar, 3.0, origin="corner")
    body.translate(0.0, 0.6, 0.0)
    parts += [base, body]
    bays = max(3, int(width / 3.4))
    for i in range(bays):
        x = -width * 0.5 + width * (i + 0.5) / bays
        arch = M.arch_ring(width / bays * 0.30, width / bays * 0.42, 1.0, 0.0,
                           math.pi, 8, p.stone_trim, 1.6)
        arch.translate(x, 3.4, depth * 0.5 + 0.05)
        void = M.box(width / bays * 0.6, 3.4, 0.6, p.timber_dark, 1.2, origin="corner")
        void.translate(x, 0.6, depth * 0.5 - 0.05)
        parts += [arch, void]
    parts.append(moulding(width + 1.0, depth + 1.0, 1.0, p).translate(0.0, 7.1, 0.0))
    roof = M.hip_roof(width, depth, 3.4, 0.35, 0.6, p.roof_verdigris, 2.4)
    roof.translate(0.0, 8.1, 0.0)
    parts.append(roof)
    for side in (-1, 1):
        awn = awning(width * 0.9, 3.2, p)
        awn.translate(0.0, 4.2, side * (depth * 0.5 + 1.4))
        if side < 0:
            awn.rotate_y(math.pi).translate(0.0, 0.0, 0.0)
        parts.append(awn)
    return Geo.concat(parts)


def farmhouse(p: Palette, width: float = 11.0, depth: float = 8.0, variant: int = 0) -> Geo:
    parts = []
    base = M.box(width + 0.4, 0.5, depth + 0.4, p.stone_rubble, 2.0, origin="corner")
    body = M.box(width, 4.4, depth, p.plaster_warm, 3.0, origin="corner")
    body.translate(0.0, 0.5, 0.0)
    parts += [base, body]
    for i in range(3):
        x = -width * 0.3 + width * 0.3 * i
        win = M.box(0.9, 1.1, 0.35, p.timber_dark, 1.0, origin="corner")
        win.translate(x, 2.1, depth * 0.5 - 0.08)
        parts.append(win)
    door = M.box(1.2, 2.1, 0.35, p.timber_dark, 1.0, origin="corner")
    door.translate(-width * 0.32, 0.5, depth * 0.5 - 0.08)
    parts.append(door)
    roof_mat = p.roof_tile if variant % 2 == 0 else p.thatch_straw
    roof = M.gable_roof(width, depth, 3.0, 0.6, roof_mat, 2.0, ridge_along_x=True)
    roof.translate(0.0, 4.9, 0.0)
    parts.append(roof)
    chimney = M.box(0.9, 3.2, 0.9, p.stone_rubble, 1.2, origin="corner")
    chimney.translate(width * 0.30, 4.5, -depth * 0.20)
    parts.append(chimney)
    if variant % 3 == 1:
        shed = M.box(4.5, 2.8, 3.4, p.timber_dark, 2.0, origin="corner")
        shed.translate(width * 0.5 + 2.4, 0.5, -depth * 0.2)
        shed_roof = M.gable_roof(4.8, 3.7, 1.3, 0.3, p.thatch_straw, 1.8, ridge_along_x=True)
        shed_roof.translate(width * 0.5 + 2.4, 3.3, -depth * 0.2)
        parts += [shed, shed_roof]
    return Geo.concat(parts)


def granary(p: Palette, radius: float = 3.6, height: float = 7.0) -> Geo:
    body = M.cylinder(radius, height, 12, p.plaster_warm, 3.0, top_radius=radius * 0.94)
    base = M.cylinder(radius * 1.14, 0.7, 12, p.stone_rubble, 2.0)
    band = M.cylinder(radius * 1.02, 0.4, 12, p.timber_dark, 1.2)
    band.translate(0.0, height * 0.55, 0.0)
    roof = M.cone(radius * 1.20, radius * 1.05, 12, p.thatch_straw, 2.0)
    roof.translate(0.0, height, 0.0)
    door = M.box(1.3, 2.2, 0.5, p.timber_dark, 1.0, origin="corner")
    door.translate(0.0, 0.0, radius * 0.92)
    return Geo.concat([base, body, band, roof, door])


def warehouse(p: Palette, width: float = 16.0, depth: float = 10.0) -> Geo:
    parts = []
    base = M.box(width + 0.6, 0.6, depth + 0.6, p.stone_rubble, 2.0, origin="corner")
    body = M.box(width, 6.0, depth, p.stone_ashlar, 3.0, origin="corner")
    body.translate(0.0, 0.6, 0.0)
    parts += [base, body]
    for i in range(3):
        x = -width * 0.32 + width * 0.32 * i
        gate = M.box(2.6, 3.6, 0.4, p.timber_dark, 1.4, origin="corner")
        gate.translate(x, 0.6, depth * 0.5 - 0.06)
        parts.append(gate)
    roof = M.gable_roof(width, depth, 2.8, 0.6, p.roof_slate, 2.2, ridge_along_x=True)
    roof.translate(0.0, 6.6, 0.0)
    parts.append(roof)
    hoist = M.box(0.4, 0.4, 2.6, p.timber_dark, 1.0, origin="corner")
    hoist.translate(0.0, 6.9, depth * 0.5 + 1.0)
    parts.append(hoist)
    return Geo.concat(parts)


# ---------------------------------------------------------------------- props
def awning(width: float, reach: float, p: Palette, drop: float = 1.0) -> Geo:
    verts = [(-width * 0.5, 0.0, 0.0), (width * 0.5, 0.0, 0.0),
             (width * 0.5, -drop, reach), (-width * 0.5, -drop, reach)]
    faces = [(0, 1, 2), (0, 2, 3)]
    canvas = M.make(verts, faces, p.canvas_awning, 1.0)
    canvas.t = np.stack([(canvas.v[:, 0] / width) + 0.5, canvas.v[:, 2] / reach],
                        axis=1).astype(np.float32)
    parts = [canvas]
    for side in (-1, 1):
        strut = M.cylinder(0.05, math.hypot(reach, drop), 5, p.timber_dark, 0.6)
        strut.rotate_x(math.atan2(reach, -drop) + math.pi)
        strut.translate(side * width * 0.5, 0.0, 0.0)
        parts.append(strut)
        post = M.cylinder(0.07, 2.2, 6, p.timber_dark, 0.8)
        post.translate(side * width * 0.5, -drop - 2.2, reach)
        parts.append(post)
    valance = M.box(width, 0.42, 0.06, p.canvas_awning, 0.8, origin="corner")
    valance.translate(0.0, -drop - 0.42, reach)
    parts.append(valance)
    return Geo.concat(parts)


def market_stall(p: Palette, variant: int = 0) -> Geo:
    parts = []
    deck = M.box(3.4, 0.9, 1.9, p.timber_dark, 1.2, origin="corner")
    parts.append(deck)
    for sx in (-1, 1):
        for sz in (-1, 1):
            post = M.cylinder(0.08, 2.6, 6, p.timber_dark, 0.8)
            post.translate(sx * 1.6, 0.9, sz * 0.9)
            parts.append(post)
    canopy_verts = [(-1.9, 0.0, -1.15), (1.9, 0.0, -1.15), (1.9, 0.0, 1.15), (-1.9, 0.0, 1.15),
                    (-1.9, 0.55, 0.0), (1.9, 0.55, 0.0)]
    canopy_faces = [(0, 1, 5), (0, 5, 4), (2, 3, 4), (2, 4, 5)]
    canopy = M.make(canopy_verts, canopy_faces, p.canvas_awning, 1.2)
    canopy.translate(0.0, 3.5, 0.0)
    parts.append(canopy)
    goods = []
    rng = np.random.default_rng(1000 + variant)
    for i in range(5):
        w = float(rng.uniform(0.28, 0.5))
        crate = M.box(w, w * 0.8, w, p.timber_dark if i % 2 else p.thatch_straw, 0.6,
                      origin="corner")
        crate.translate(float(rng.uniform(-1.3, 1.3)), 0.9, float(rng.uniform(-0.6, 0.6)))
        goods.append(crate)
    parts += goods
    return Geo.concat(parts)


def crate(p: Palette, size: float = 0.8) -> Geo:
    body = M.box(size, size * 0.85, size * 0.9, p.timber_dark, 0.5, origin="corner")
    band = M.box(size * 1.04, 0.08, size * 0.94, p.metal_iron, 0.4, origin="corner")
    band.translate(0.0, size * 0.4, 0.0)
    return Geo.concat([body, band])


def barrel(p: Palette, radius: float = 0.42, height: float = 1.1) -> Geo:
    body = M.revolve([(radius * 0.82, 0.0), (radius, height * 0.3),
                      (radius, height * 0.7), (radius * 0.82, height)],
                     10, p.timber_dark, 0.6)
    hoops = []
    for t in (0.18, 0.5, 0.82):
        hoop = M.cylinder(radius * 1.03, 0.07, 10, p.metal_iron, 0.4)
        hoop.translate(0.0, height * t, 0.0)
        hoops.append(hoop)
    lid = M.cylinder(radius * 0.84, 0.06, 10, p.timber_dark, 0.4)
    lid.translate(0.0, height, 0.0)
    return Geo.concat([body, lid] + hoops)


def handcart(p: Palette) -> Geo:
    parts = []
    bed = M.box(2.4, 0.35, 1.3, p.timber_dark, 1.0, origin="corner")
    bed.translate(0.0, 0.75, 0.0)
    parts.append(bed)
    for sz in (-1, 1):
        side = M.box(2.4, 0.5, 0.12, p.timber_dark, 0.8, origin="corner")
        side.translate(0.0, 1.10, sz * 0.62)
        parts.append(side)
    for sx in (-1, 1):
        wheel = M.cylinder(0.55, 0.14, 12, p.timber_dark, 0.6)
        wheel.rotate_z(math.pi / 2)
        wheel.translate(sx * 0.72, 0.58, 0.0)
        hub = M.cylinder(0.16, 0.2, 8, p.metal_iron, 0.4)
        hub.rotate_z(math.pi / 2)
        hub.translate(sx * 0.78, 0.58, 0.0)
        parts += [wheel, hub]
    for sz in (-1, 1):
        shaft = M.box(1.5, 0.1, 0.1, p.timber_dark, 0.6, origin="corner")
        shaft.translate(1.85, 0.85, sz * 0.45)
        parts.append(shaft)
    return Geo.concat(parts)


def bench(p: Palette, length: float = 2.4) -> Geo:
    seat = M.box(length, 0.16, 0.55, p.timber_dark, 0.8, origin="corner")
    seat.translate(0.0, 0.46, 0.0)
    back = M.box(length, 0.55, 0.12, p.timber_dark, 0.8, origin="corner")
    back.translate(0.0, 0.62, -0.24)
    parts = [seat, back]
    for sx in (-1, 1):
        leg = M.box(0.14, 0.46, 0.5, p.stone_trim, 0.6, origin="corner")
        leg.translate(sx * (length * 0.5 - 0.2), 0.0, 0.0)
        parts.append(leg)
    return Geo.concat(parts)


def planter(p: Palette, radius: float = 1.5) -> Geo:
    bowl = M.revolve([(radius * 0.78, 0.0), (radius, 0.32), (radius * 0.96, 0.78),
                      (radius * 0.86, 0.82)], 12, p.stone_trim, 1.2)
    soil = M.cylinder(radius * 0.86, 0.1, 12, p.terrain_soil, 0.8)
    soil.translate(0.0, 0.72, 0.0)
    bloom = M.icosphere(radius * 0.78, 1, p.foliage_flowers, 1.0)
    bloom.scale(1.0, 0.52, 1.0).translate(0.0, 0.92, 0.0)
    return Geo.concat([bowl, soil, bloom])


def well(p: Palette) -> Geo:
    ring = M.revolve([(1.0, 0.0), (1.15, 0.15), (1.15, 1.0), (1.0, 1.1),
                      (0.82, 1.05), (0.82, 0.1)], 12, p.stone_rubble, 1.2)
    parts = [ring]
    for sx in (-1, 1):
        post = M.box(0.18, 2.4, 0.18, p.timber_dark, 0.8, origin="corner")
        post.translate(sx * 1.0, 1.05, 0.0)
        parts.append(post)
    beam = M.box(2.4, 0.18, 0.18, p.timber_dark, 0.8, origin="corner")
    beam.translate(0.0, 3.35, 0.0)
    roof = M.gable_roof(2.9, 1.9, 0.7, 0.2, p.roof_tile, 1.2, ridge_along_x=True)
    roof.translate(0.0, 3.45, 0.0)
    bucket = M.cylinder(0.24, 0.32, 8, p.timber_dark, 0.4)
    bucket.translate(0.0, 2.2, 0.0)
    return Geo.concat(parts + [beam, roof, bucket])


def fountain(p: Palette, radius: float = 4.5) -> Geo:
    basin = M.revolve([(radius, 0.0), (radius, 1.0), (radius * 0.92, 1.05),
                       (radius * 0.92, 0.25), (radius * 0.2, 0.2), (0.0, 0.2)],
                      20, p.stone_trim, 1.6)
    water = M.cylinder(radius * 0.90, 0.02, 20, p.water_turquoise, 3.0)
    water.translate(0.0, 0.72, 0.0)
    stem = M.revolve([(0.9, 0.2), (0.65, 1.2), (0.42, 2.4), (0.72, 2.7), (0.30, 3.0)],
                     12, p.stone_trim, 1.2)
    bowl = M.revolve([(0.0, 0.0), (1.5, 0.35), (1.4, 0.55), (0.3, 0.4)],
                     14, p.stone_trim, 1.2)
    bowl.translate(0.0, 3.0, 0.0)
    jet = M.revolve([(0.0, 0.0), (0.34, 0.5), (0.16, 1.4), (0.0, 1.7)],
                    10, p.crystal_blue, 0.8)
    jet.translate(0.0, 3.5, 0.0)
    return Geo.concat([basin, water, stem, bowl, jet])


def bollard(p: Palette) -> Geo:
    return M.revolve([(0.22, 0.0), (0.26, 0.15), (0.2, 0.9), (0.24, 1.0), (0.0, 1.12)],
                     8, p.stone_trim, 0.8)


def signboard(p: Palette) -> Geo:
    post = M.cylinder(0.09, 2.8, 6, p.timber_dark, 0.8)
    arm = M.box(1.0, 0.1, 0.1, p.metal_iron, 0.5, origin="corner")
    arm.translate(0.45, 2.6, 0.0)
    board = M.box(1.1, 0.75, 0.08, p.timber_dark, 0.6, origin="corner")
    board.translate(0.85, 1.7, 0.0)
    mark = M.cylinder(0.26, 0.05, 10, p.metal_gold, 0.5)
    mark.rotate_x(math.pi / 2)
    mark.translate(0.85, 2.05, -0.07)
    return Geo.concat([post, arm, board, mark])


def hitching_rail(p: Palette, length: float = 4.0) -> Geo:
    parts = []
    for sx in (-1, 1):
        post = M.box(0.16, 1.3, 0.16, p.timber_dark, 0.6, origin="corner")
        post.translate(sx * length * 0.5, 0.0, 0.0)
        parts.append(post)
    rail = M.box(length + 0.3, 0.14, 0.14, p.timber_dark, 0.8, origin="corner")
    rail.translate(0.0, 1.05, 0.0)
    parts.append(rail)
    return Geo.concat(parts)


def fence_run(p: Palette, length: float = 6.0, posts: int = 4) -> Geo:
    parts = []
    for i in range(posts):
        x = -length * 0.5 + length * i / max(posts - 1, 1)
        post = M.box(0.14, 1.15, 0.14, p.timber_dark, 0.6, origin="corner")
        post.translate(x, 0.0, 0.0)
        parts.append(post)
    for y in (0.45, 0.92):
        rail = M.box(length, 0.09, 0.08, p.timber_dark, 0.8, origin="corner")
        rail.translate(0.0, y, 0.0)
        parts.append(rail)
    return Geo.concat(parts)


def hay_stack(p: Palette) -> Geo:
    base = M.cylinder(1.5, 1.3, 10, p.thatch_straw, 1.2, top_radius=1.35)
    top = M.cone(1.5, 1.4, 10, p.thatch_straw, 1.2)
    top.translate(0.0, 1.3, 0.0)
    return Geo.concat([base, top])


def dock_platform(p: Palette, width: float = 9.0, depth: float = 6.0,
                  height: float = 3.0) -> Geo:
    parts = []
    deck = M.box(width, 0.45, depth, p.timber_dark, 1.5, origin="corner")
    deck.translate(0.0, height, 0.0)
    parts.append(deck)
    for sx in (-1, 1):
        for sz in (-1, 1):
            pile = M.cylinder(0.28, height + 0.6, 8, p.timber_dark, 1.0)
            pile.translate(sx * (width * 0.5 - 0.6), -0.6, sz * (depth * 0.5 - 0.6))
            parts.append(pile)
    for i in range(4):
        bollard_post = M.cylinder(0.18, 0.8, 8, p.timber_dark, 0.6)
        bollard_post.translate(-width * 0.4 + width * 0.26 * i, height + 0.45, depth * 0.4)
        parts.append(bollard_post)
    return Geo.concat(parts)


def harbour_crane(p: Palette, height: float = 7.5) -> Geo:
    post = M.cylinder(0.45, height, 8, p.timber_dark, 1.2)
    base = M.box(2.4, 0.5, 2.4, p.stone_rubble, 1.2, origin="corner")
    boom = M.box(6.5, 0.3, 0.3, p.timber_dark, 1.0, origin="corner")
    boom.rotate_z(-0.32).translate(2.6, height - 0.4, 0.0)
    stay = M.box(4.0, 0.16, 0.16, p.metal_iron, 0.8, origin="corner")
    stay.rotate_z(0.55).translate(1.4, height - 1.9, 0.0)
    hook = M.cylinder(0.06, 2.2, 5, p.metal_iron, 0.5)
    hook.translate(5.3, height - 2.9, 0.0)
    return Geo.concat([base, post, boom, stay, hook])


# ----------------------------------------------------------------- vegetation
def broadleaf_tree(p: Palette, height: float = 9.0, seed: int = 0) -> Geo:
    rng = np.random.default_rng(seed)
    trunk = M.revolve([(0.42, 0.0), (0.33, height * 0.20), (0.26, height * 0.42),
                       (0.20, height * 0.55)], 7, p.timber_dark, 1.2)
    parts = [trunk]
    lobes = 4
    for i in range(lobes):
        a = TAU * i / lobes + float(rng.uniform(0, 1.0))
        radius = height * float(rng.uniform(0.22, 0.30))
        blob = M.icosphere(radius, 1, p.foliage_broadleaf, 1.6)
        blob.scale(1.0, 0.82, 1.0)
        blob.translate(math.cos(a) * height * 0.13, height * float(rng.uniform(0.58, 0.76)),
                       math.sin(a) * height * 0.13)
        parts.append(blob)
    crown = M.icosphere(height * 0.27, 1, p.foliage_broadleaf, 1.6)
    crown.scale(1.0, 0.9, 1.0).translate(0.0, height * 0.80, 0.0)
    parts.append(crown)
    for i in range(3):
        a = TAU * i / 3 + 0.4
        branch = M.cylinder(0.10, height * 0.28, 5, p.timber_dark, 0.8)
        branch.rotate_z(0.55).rotate_y(a)
        branch.translate(0.0, height * 0.44, 0.0)
        parts.append(branch)
    return Geo.concat(parts)


def cypress_tree(p: Palette, height: float = 12.0, seed: int = 0) -> Geo:
    """Columnar evergreen, as flanks the causeways and river banks."""
    rng = np.random.default_rng(seed)
    trunk = M.revolve([(0.26, 0.0), (0.18, height * 0.5), (0.10, height * 0.9)],
                      6, p.timber_dark, 1.0)
    parts = [trunk]
    profile = []
    rows = 9
    for i in range(rows):
        t = i / (rows - 1)
        # narrow spindle: wide near the base, tapering to a point
        radius = height * 0.105 * math.sin(math.pi * (0.12 + 0.85 * t)) ** 0.7
        radius *= float(rng.uniform(0.94, 1.06))
        profile.append((max(radius, 0.02), height * (0.10 + 0.90 * t)))
    profile.append((0.0, height * 1.02))
    parts.append(M.revolve(profile, 8, p.foliage_pine, 1.4, smooth=False))
    return Geo.concat(parts)


def crystal_standard(p: Palette, height: float = 7.0) -> Geo:
    """Gilded post carrying a tall sapphire shard -- the signature street light."""
    plinth = M.revolve([(0.62, 0.0), (0.66, 0.30), (0.48, 0.52), (0.44, 0.66)],
                       10, p.stone_trim, 1.2)
    shaft = M.revolve([(0.30, 0.0), (0.24, height * 0.30),
                       (0.20, height * 0.62), (0.30, height * 0.70),
                       (0.24, height * 0.76)], 10, p.metal_gold, 1.0)
    shaft.translate(0.0, 0.66, 0.0)
    collar = M.revolve([(0.0, 0.0), (0.52, 0.22), (0.40, 0.46), (0.22, 0.56)],
                       10, p.metal_gold, 0.8)
    collar.translate(0.0, 0.66 + height * 0.74, 0.0)
    shard = M.revolve([(0.0, 0.0), (0.34, height * 0.10), (0.26, height * 0.30),
                       (0.0, height * 0.46)], 6, p.crystal_blue, 0.8)
    shard.translate(0.0, 0.66 + height * 0.80, 0.0)
    return Geo.concat([plinth, shaft, collar, shard])


def pine_tree(p: Palette, height: float = 13.0, seed: int = 0) -> Geo:
    rng = np.random.default_rng(seed)
    trunk = M.revolve([(0.34, 0.0), (0.24, height * 0.4), (0.14, height * 0.9)],
                      6, p.timber_dark, 1.2)
    parts = [trunk]
    tiers = 4
    for i in range(tiers):
        t = i / tiers
        radius = height * (0.26 - 0.16 * t) * float(rng.uniform(0.9, 1.12))
        cone = M.cone(radius, height * 0.30, 8, p.foliage_pine, 1.6)
        cone.translate(0.0, height * (0.24 + 0.19 * i), 0.0)
        parts.append(cone)
    return Geo.concat(parts)


def hedge(p: Palette, length: float = 4.0, width: float = 1.1, height: float = 1.3) -> Geo:
    body = M.box(length, height, width, p.foliage_broadleaf, 1.2, origin="corner")
    cap = M.box(length * 0.94, 0.2, width * 0.86, p.foliage_broadleaf, 1.0, origin="corner")
    cap.translate(0.0, height, 0.0)
    return Geo.concat([body, cap])


def shrub(p: Palette, radius: float = 0.9) -> Geo:
    body = M.icosphere(radius, 1, p.foliage_broadleaf, 1.0)
    body.scale(1.0, 0.72, 1.0).translate(0.0, radius * 0.6, 0.0)
    return body


def boulder(p: Palette, radius: float = 1.6, seed: int = 0) -> Geo:
    rng = np.random.default_rng(seed)
    rock = M.icosphere(radius, 1, p.terrain_rock, 2.0, smooth=False)
    rock.v = (rock.v * (1.0 + rng.normal(0.0, 0.16, rock.v.shape))).astype(np.float32)
    rock.v[:, 1] = np.maximum(rock.v[:, 1], -radius * 0.15)
    rock.recompute_normals(False)
    rock.translate(0.0, radius * 0.55, 0.0)
    return rock
