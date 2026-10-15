"""Mirrorhold's built kit.

Region-specific compositions built from the shared toolkit's primitives. The
pieces here are Mirrorhold's own - a gilded dome, an armillary mount, a
colonnaded ring on the lake - so they live with the region rather than in the
shared kits, which three other regions are editing at the same time.

Walk-surface discipline, per the runtime contract: only decks a character may
stand on go through `MeshGroup.add_walk`. Structural geometry never does, or
the client's downward grounding ray snaps actors onto roofs and arch crowns.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as ARCH
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as PROPS
from amberwood import stonework as STONE

# Mirrorhold's palette, named once so a change of stone is one edit.
ASHLAR = "pale_ashlar"
MARBLE = "veined_marble"
RUBBLE = "rubble_stone"
BRASS = "gilt_brass"
CRYSTAL = "blue_crystal"
MIRROR = "mirror_glass"
SLATE = "slate_roof"
IRON = "dark_iron"
TIMBER = "timber_grey"
TIMBER_WARM = "timber_warm"
CLOTH = "woven_cloth"
ROCK = "cliff_rock"


def _g(*meshes) -> STONE.MeshGroup:
    out = STONE.MeshGroup()
    for piece in meshes:
        out.add(piece)
    return out


# ------------------------------------------------------------------ pieces
def gilded_dome(radius: float = 3.0, height: float = 3.6, ribs: int = 8,
                material: str = BRASS) -> M.Mesh:
    """An onion dome on a drum, the silhouette that repeats across the citadel."""
    profile = [
        [radius, 0.0], [radius * 1.06, height * 0.22], [radius * 0.98, height * 0.44],
        [radius * 0.76, height * 0.66], [radius * 0.44, height * 0.84],
        [radius * 0.18, height * 0.95], [0.0, height],
    ]
    shell = M.lathe(profile, 20, uv_scale=1.1, material=material)
    parts = [shell]
    for index in range(ribs):
        angle = math.pi * 2.0 * index / ribs
        rib = M.box((0.09, height * 0.98, 0.09),
                    center=(radius * 0.62, height * 0.5, 0.0), material=material)
        parts.append(rib.rotate_y(angle))
    return M.merge(parts, material)


def finial(height: float = 1.4, material: str = BRASS) -> M.Mesh:
    return M.lathe([[0.0, 0.0], [0.18, height * 0.16], [0.10, height * 0.52],
                    [0.20, height * 0.66], [0.0, height]], 10,
                   uv_scale=1.4, material=material)


def crystal_panel(width: float = 0.9, height: float = 2.2,
                  depth: float = 0.16) -> STONE.MeshGroup:
    """A lens set in a gilt frame: the region's signature wall detail."""
    frame = M.box((width + 0.22, height + 0.22, depth), material=BRASS)
    glass = M.box((width, height, depth * 1.25), material=CRYSTAL)
    return _g(frame, glass)


def rose_window(radius: float = 2.6, spokes: int = 12) -> STONE.MeshGroup:
    """The blue rose window of the gallery: gilt tracery over crystal.

    Built flat about the Y axis and stood up once at the end - rotating the
    lathe and the spoke bars separately puts them in different planes.
    """
    glass = M.lathe([[radius, 0.0], [radius, 0.18], [0.0, 0.18]], 24,
                    uv_scale=1.0, material=CRYSTAL)
    brass = [M.lathe([[radius + 0.34, 0.0], [radius + 0.34, 0.30],
                      [radius + 0.02, 0.30], [radius + 0.02, 0.0]], 24,
                     uv_scale=1.0, material=BRASS),
             M.lathe([[radius * 0.36, 0.0], [radius * 0.36, 0.26],
                      [radius * 0.30, 0.26], [radius * 0.30, 0.0]], 18,
                     uv_scale=1.0, material=BRASS)]
    for index in range(spokes):
        angle = math.pi * index / spokes
        bar = M.box((radius * 2.0, 0.22, 0.10), center=(0.0, 0.14, 0.0),
                    material=BRASS)
        brass.append(bar.rotate_y(angle))
    out = STONE.MeshGroup()
    # The lathe grows along +Y and standing it up sends that into -Z, i.e.
    # into the wall behind. Push the glass back out so it reads through the
    # tracery instead of disappearing into the masonry.
    out.add(glass.rotate_x(math.pi * 0.5).translate(0.0, 0.0, 0.20))
    out.add(M.merge(brass, BRASS).rotate_x(math.pi * 0.5)
            .translate(0.0, 0.0, 0.20))
    return out


def armillary(radius: float = 4.2, seed: int = 0) -> STONE.MeshGroup:
    """The mirror-sphere in its brass rings: Mirrorhold's crowning landmark.

    Three inclined rings around a dark polished sphere, on a short plinth. The
    aerial concept puts this on the highest terrace, visible from the lake.
    """
    parts = []
    for index, tilt in enumerate((0.0, math.pi * 0.34, -math.pi * 0.30)):
        ring_radius = radius * (1.0 - index * 0.055)
        ring = M.lathe([[ring_radius, -0.16], [ring_radius + 0.20, -0.16],
                        [ring_radius + 0.20, 0.16], [ring_radius, 0.16]], 40,
                       uv_scale=1.2, material=BRASS)
        ring = ring.rotate_x(math.pi * 0.5).rotate_z(tilt)
        if index == 2:
            ring = ring.rotate_y(math.pi * 0.42)
        parts.append(ring)
    # the meridian band the rings hang from
    band = M.lathe([[radius + 0.42, -0.22], [radius + 0.66, -0.22],
                    [radius + 0.66, 0.22], [radius + 0.42, 0.22]], 44,
                   uv_scale=1.2, material=BRASS)
    parts.append(band)
    sphere = M.icosphere(radius * 0.56, subdivisions=3, material=MIRROR)
    mount = M.lathe([[radius * 0.34, -radius - 1.6], [radius * 0.40, -radius - 1.2],
                     [radius * 0.22, -radius * 0.72], [0.16, -radius * 0.60]], 16,
                    uv_scale=1.0, material=BRASS)
    return _g(M.merge(parts, BRASS), sphere, mount)


def lens_tower(height: float = 15.0, radius: float = 2.0,
               seed: int = 0) -> STONE.MeshGroup:
    """A slender observation tower with a crystal lens under a gilded cap."""
    shaft = M.cylinder(radius, radius * 0.88, height, segments=14,
                       uv_scale=0.9, material=ASHLAR)
    base = M.lathe([[radius + 0.85, 0.0], [radius + 0.85, 0.5],
                    [radius + 0.40, 0.62], [radius + 0.40, 0.9], [0.0, 0.9]], 16,
                   uv_scale=0.8, material=ASHLAR)
    gallery = M.lathe([[radius + 0.62, height], [radius + 0.62, height + 0.34],
                       [radius + 0.20, height + 0.40], [radius + 0.20, height]], 16,
                      uv_scale=0.9, material=ASHLAR)
    lens = M.icosphere(radius * 0.72, subdivisions=2,
                       material=CRYSTAL).translate(0.0, height + 1.30, 0.0)
    cap = gilded_dome(radius * 0.96, radius * 1.5).translate(0.0, height + 1.9, 0.0)
    parts = [shaft, base, gallery]
    for index in range(4):
        angle = math.pi * 0.5 * index
        panel = crystal_panel(0.42, 1.5, 0.14)
        for sub in panel.parts:
            parts.append(sub.translate(0.0, height * 0.52, radius * 0.94)
                         .rotate_y(angle))
    return _g(M.merge([p for p in parts if p.material == ASHLAR], ASHLAR),
              *[p for p in parts if p.material != ASHLAR],
              lens, cap, finial(1.2).translate(0.0, height + 1.9 + radius * 1.5, 0.0))


def colonnade_ring(radius: float = 13.0, columns: int = 20,
                   column_height: float = 5.4, seed: int = 0) -> STONE.MeshGroup:
    """The ring on the lake: a colonnaded disc round a still inner basin.

    The deck is a walk surface and owns its server cells; the water inside is
    not walkable and the ring's foundation is not a separate level.
    """
    out = STONE.MeshGroup()
    # A battered foundation, not a stepped one: read through the water, the
    # steps break into dark wedges against the lake surface.
    out.add(M.lathe([[radius + 2.7, -2.4], [radius + 2.3, -1.2],
                     [radius + 1.9, -0.4], [radius + 1.7, 0.0],
                     [0.0, 0.0]], 44, uv_scale=0.7, material=ASHLAR))
    # the deck a player walks on
    from amberwood import routecraft as RC
    deck = RC.annular_walk(radius + 1.7, radius * 0.42, material=MARBLE)
    out.add_walk(deck)
    # inner basin rim and its water
    out.add(M.lathe([[radius * 0.42, 0.16], [radius * 0.42, 0.62],
                     [radius * 0.30, 0.62], [radius * 0.30, 0.16]], 32,
                    uv_scale=0.8, material=MARBLE))
    out.add(M.lathe([[radius * 0.30, 0.30], [0.0, 0.30]], 32,
                    uv_scale=1.0, material="water_pool"))
    for index in range(columns):
        if index % (columns // 4) == 0:
            continue  # a clear opening at each causeway
        angle = math.pi * 2.0 * index / columns
        shaft = STONE.column(column_height, 0.34, 12, MARBLE)
        out.add(shaft.translate(math.cos(angle) * radius, 0.16,
                                math.sin(angle) * radius))
    # entablature
    out.add(M.lathe([[radius + 0.70, column_height + 0.16],
                     [radius + 0.70, column_height + 0.78],
                     [radius - 0.70, column_height + 0.78],
                     [radius - 0.70, column_height + 0.16]], 40,
                    uv_scale=0.8, material=ASHLAR))
    # four gilded finial posts on the cardinal axes
    for index in range(4):
        angle = math.pi * 0.5 * index + math.pi * 0.25
        post = M.cylinder(0.30, 0.24, 2.4, segments=10, uv_scale=1.0,
                          material=BRASS)
        out.add(post.translate(math.cos(angle) * (radius + 1.1),
                               column_height + 0.78,
                               math.sin(angle) * (radius + 1.1)))
    return out


def causeway(length: float = 30.0, width: float = 4.6, deck_height: float = 1.2,
             seed: int = 0) -> STONE.MeshGroup:
    """A low masonry causeway across the lake to the ring.

    Built as solid wall slices whose underside follows the arch intrados rather
    than as rotated arch rings, which is the mistake `stonework.high_bridge`
    documents.
    """
    out = STONE.MeshGroup()
    piers = max(2, int(length / 7.0))
    span = length / piers
    for index in range(piers):
        x = -length * 0.5 + span * (index + 0.5)
        pier = M.box((span * 0.34, deck_height + 2.6, width + 0.5),
                     center=(x, -1.3 + deck_height * 0.5, 0.0), material=ASHLAR)
        out.add(pier)
    body = M.box((length, 0.9, width + 0.4),
                 center=(0.0, deck_height - 0.45, 0.0), material=ASHLAR)
    out.add(body)
    deck = M.box((length, 0.16, width),
                 center=(0.0, deck_height + 0.08, 0.0), material=MARBLE)
    out.add_walk(deck)
    for side in (-1.0, 1.0):
        rail = STONE.balustrade(length, 1.0, MARBLE)
        out.add(rail.translate(0.0, deck_height + 0.16, side * width * 0.5))
    return out


def aqueduct_run(length: float = 40.0, height: float = 9.0, span: float = 7.0,
                 seed: int = 0) -> STONE.MeshGroup:
    """An arcade carrying the meltwater channel along the eastern shoulder."""
    out = STONE.MeshGroup()
    bays = max(2, int(round(length / span)))
    actual = length / bays
    for index in range(bays + 1):
        x = -length * 0.5 + actual * index
        pier = M.box((actual * 0.26, height, 2.6), center=(x, height * 0.5, 0.0),
                     material=ASHLAR)
        out.add(pier)
    # spandrel wall with the arch openings cut as a solid elevation
    for index in range(bays):
        x = -length * 0.5 + actual * (index + 0.5)
        arch = M.arch(actual * 0.74, actual * 0.36, 0.55, 2.4, segments=12,
                      material=ASHLAR)
        out.add(arch.translate(x, height * 0.56, 0.0))
    top = M.box((length + 1.2, 1.1, 3.2), center=(0.0, height + 0.55, 0.0),
                material=ASHLAR)
    out.add(top)
    channel = STONE.water_channel(length, 1.5, 0.55, seed=seed)
    out.add(channel.translate(0.0, height + 1.1, 0.0))
    return out


def quay(length: float = 26.0, width: float = 8.0, height: float = 2.6,
         seed: int = 0) -> STONE.MeshGroup:
    """Harbour quay: a masonry wall with a walkable stone apron on top."""
    out = STONE.MeshGroup()
    out.add(M.box((length, height, width),
                  center=(0.0, height * 0.5, 0.0), material=ASHLAR))
    deck = M.box((length, 0.18, width),
                 center=(0.0, height + 0.09, 0.0), material="cobble_paving")
    out.add_walk(deck)
    for index in range(max(2, int(length / 6.0))):
        x = -length * 0.5 + 3.0 + index * 6.0
        bollard = M.cylinder(0.22, 0.18, 0.62, segments=8, uv_scale=1.0,
                             material=IRON)
        out.add(bollard.translate(x, height + 0.18, width * 0.5 - 0.7))
    return out


def cliff_house(seed: int = 0, width: float = 5.0, depth: float = 5.6,
                storeys: int = 3) -> STONE.MeshGroup:
    """A stacked stone house of the cliff town: slate roof, timber balcony."""
    rng = np.random.default_rng(seed)
    out = STONE.MeshGroup()
    storey = 2.7
    total = storey * storeys
    out.add(M.box((width, total, depth), center=(0.0, total * 0.5, 0.0),
                  material=ASHLAR))
    # timber upper floor jettied out over the street, as the panel shows
    jetty = M.box((width + 0.7, storey * 0.92, depth * 0.55),
                  center=(0.0, total - storey * 0.5, depth * 0.30),
                  material=TIMBER)
    out.add(jetty)
    roof = M.gable_roof(width + 0.9, depth + 0.9, 1.9, overhang=0.4,
                        material=SLATE)
    out.add(roof.translate(0.0, total, 0.0))
    # windows, some lit with the crystal the region uses for glass
    for level in range(storeys):
        for side in (-1, 1):
            if rng.random() < 0.35:
                continue
            panel = crystal_panel(0.5, 0.9, 0.12)
            for sub in panel.parts:
                out.add(sub.translate(side * width * 0.22,
                                      0.9 + level * storey, depth * 0.5 + 0.02))
    # Preserve the original decorative railing byte-for-byte, then give it a
    # thin, non-walkable timber sill that is seated into both rail and jetty.
    balcony = ARCH.railing(width * 0.8, 0.95, material=TIMBER)
    balcony.translate(0.0, total - storey, depth * 0.58)
    out.add(balcony)
    rail_low, rail_high = balcony.bounds()
    _, roof_high = roof.bounds()
    jetty_front = depth * 0.575
    sill_inner = jetty_front - 0.12
    sill_outer = min(rail_high[2] + 0.02, roof_high[2] - 0.01)
    sill_top = rail_low[1] + 0.02
    sill_thickness = 0.05
    out.add(M.box((rail_high[0] - rail_low[0], sill_thickness,
                   sill_outer - sill_inner),
                  center=((rail_low[0] + rail_high[0]) * 0.5,
                          sill_top - sill_thickness * 0.5,
                          (sill_inner + sill_outer) * 0.5),
                  material=TIMBER))
    return out


def gate_wall(length: float = 22.0, height: float = 9.0,
              seed: int = 0) -> STONE.MeshGroup:
    """A stretch of citadel wall: crystal panels, banners, a walkable wall-walk."""
    out = STONE.MeshGroup()
    out.add(M.box((length, height, 2.2), center=(0.0, height * 0.5, 0.0),
                  material=ASHLAR))
    # battlement and the walk behind it
    out.add(M.box((length, 0.9, 0.55),
                  center=(0.0, height + 0.45, -0.8), material=ASHLAR))
    walk = M.box((length, 0.16, 1.5), center=(0.0, height + 0.08, 0.25),
                 material="cobble_paving")
    out.add_walk(walk)
    bays = max(2, int(length / 5.0))
    for index in range(bays):
        x = -length * 0.5 + length * (index + 0.5) / bays
        panel = crystal_panel(0.85, 2.4, 0.18)
        for sub in panel.parts:
            out.add(sub.translate(x, height * 0.46, 1.16))
        if index % 2 == 0:
            flag = PROPS.banner(1.0, 3.0, seed=seed + index, material=CLOTH)
            out.add(flag.translate(x, height * 0.30, 1.30))
    return out


def reflecting_basin(half_x: float = 9.0, half_z: float = 5.0,
                     seed: int = 0) -> STONE.MeshGroup:
    """A still terrace pool - the feature the region takes its name from.

    The coping is walkable; the water is not.
    """
    out = STONE.MeshGroup()
    rim = 0.45
    out.add(M.box((half_x * 2 + rim * 2, 0.55, half_z * 2 + rim * 2),
                  center=(0.0, -0.05, 0.0), material=MARBLE))
    coping = M.box((half_x * 2 + rim * 2, 0.16, rim), material=MARBLE)
    for side in (-1.0, 1.0):
        out.add_walk(coping.copy().translate(0.0, 0.30,
                                             side * (half_z + rim * 0.5)))
    coping_z = M.box((rim, 0.16, half_z * 2 + rim * 2), material=MARBLE)
    for side in (-1.0, 1.0):
        out.add_walk(coping_z.copy().translate(side * (half_x + rim * 0.5),
                                               0.30, 0.0))
    out.add(M.box((half_x * 2, 0.06, half_z * 2), center=(0.0, 0.24, 0.0),
                  material="water_pool"))
    return out


def citadel_block(seed: int = 0, width: float = 26.0, depth: float = 18.0,
                  height: float = 13.0, domes: int = 2) -> STONE.MeshGroup:
    """A mass of the observatory citadel: ashlar block, gilded corner domes."""
    out = STONE.MeshGroup()
    out.add(M.box((width, height, depth), center=(0.0, height * 0.5, 0.0),
                  material=ASHLAR))
    # string course and parapet
    out.add(M.box((width + 0.8, 0.5, depth + 0.8),
                  center=(0.0, height * 0.62, 0.0), material=MARBLE))
    out.add(M.box((width + 0.5, 1.0, depth + 0.5),
                  center=(0.0, height + 0.5, 0.0), material=ASHLAR))
    roof = M.box((width - 1.2, 0.16, depth - 1.2),
                 center=(0.0, height + 0.08, 0.0), material="cobble_paving")
    out.add_walk(roof)
    # corner towers with domes
    for index in range(domes * 2):
        sx = -1.0 if index % 2 == 0 else 1.0
        sz = -1.0 if index < 2 else 1.0
        tower_h = height + 4.5
        tower = M.cylinder(2.1, 1.95, tower_h, segments=12, uv_scale=0.9,
                           material=ASHLAR)
        out.add(tower.translate(sx * (width * 0.5 - 1.6), 0.0,
                                sz * (depth * 0.5 - 1.6)))
        out.add(gilded_dome(2.3, 3.0).translate(
            sx * (width * 0.5 - 1.6), tower_h, sz * (depth * 0.5 - 1.6)))
        out.add(finial(1.1).translate(sx * (width * 0.5 - 1.6), tower_h + 3.0,
                                      sz * (depth * 0.5 - 1.6)))
    # a tall arched opening on the south face
    out.add(M.arch(5.0, 3.0, 0.7, 2.6, segments=14, material=MARBLE)
            .translate(0.0, 0.0, depth * 0.5))
    return out


def pavilion(radius: float = 4.0, height: float = 4.6, columns: int = 10,
             seed: int = 0, dome: bool = True) -> STONE.MeshGroup:
    """Open colonnaded pavilion under a gilded dome.

    The toolkit's `stonework.rotunda` is the same idea in Amberwood's timber
    and shingle; Mirrorhold's is marble and brass, and its floor is a walk
    surface so a player can stand under it.
    """
    out = STONE.MeshGroup()
    out.add(M.lathe([[radius + 1.05, 0.0], [radius + 1.05, 0.22],
                     [radius + 0.70, 0.24], [radius + 0.70, 0.46],
                     [radius + 0.38, 0.48], [radius + 0.38, 0.60],
                     [0.0, 0.60]], 20, uv_scale=0.8, material=ASHLAR))
    floor = M.lathe([[radius + 0.38, 0.60], [radius + 0.38, 0.72],
                     [0.0, 0.72]], 20, uv_scale=0.7, material=MARBLE)
    out.add_walk(floor)
    for index in range(columns):
        angle = math.pi * 2.0 * index / columns
        out.add(STONE.column(height, 0.30, 10, MARBLE)
                .translate(math.cos(angle) * radius, 0.72,
                           math.sin(angle) * radius))
    out.add(M.lathe([[radius + 0.55, height + 0.72], [radius + 0.55, height + 1.10],
                     [radius + 0.30, height + 1.16], [radius + 0.30, height + 1.34],
                     [0.0, height + 1.38]], 20, uv_scale=0.8, material=ASHLAR))
    if dome:
        out.add(gilded_dome(radius * 0.94, radius * 1.05)
                .translate(0.0, height + 1.34, 0.0))
        out.add(finial(1.0).translate(0.0, height + 1.34 + radius * 1.05, 0.0))
    return out


def crystal_lamp(height: float = 2.8) -> STONE.MeshGroup:
    """A lamp post lit by a blue lens rather than Amberwood's amber resin.

    These line the causeway in the detail board and are the region's light at
    dusk, so the glow material matters: `stonework.lamp_post` hardcodes amber.
    """
    out = STONE.MeshGroup()
    out.add(M.lathe([[0.34, 0.0], [0.34, 0.16], [0.20, 0.22], [0.13, 0.55],
                     [0.11, height * 0.86]], 10, uv_scale=1.0, material=IRON))
    # the lantern head: a gilt cage round a crystal
    out.add(M.lathe([[0.0, height + 0.52], [0.20, height + 0.36],
                     [0.24, height * 0.98], [0.16, height * 0.90],
                     [0.0, height * 0.90]], 10, uv_scale=1.2, material=BRASS))
    out.add(M.icosphere(0.20, subdivisions=1, material=CRYSTAL)
            .translate(0.0, height + 0.06, 0.0))
    return out
