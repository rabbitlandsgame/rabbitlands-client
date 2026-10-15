"""The Whitehorn Glacier Temple interior.

Built with the shared interior kit in `_toolkit/amberwood/interiors.py` -
`chamber`, `passage`, `hanging_lamps` and the `Interior` container - plus this
region's own exterior kit, so a rope bridge underground is the same piece of
carpentry as the two that cross the gorge outside.

Kept here rather than in the toolkit's `interiors.py`: that module holds
Amberwood's four because it is where they grew, but an interior is region
content, and adding a fifth there would put Whitehorn's rooms in every other
region's import path.

## The idea

The concept package names ten subjects - snow entry, monastery nave, prayer
columns, ice arch, glacier altar, mining gallery, chasm bridge, votive chamber,
upper sanctuary, and an ice/granite/silver material study. What connects them,
and what this build is about, is that **the glacier is eating the monastery**.

The monks cut a temple into the mountain and then followed a silver vein north,
straight into the ice. The building nearest the door is intact and level. The
further in you go the more the ice has taken: the colonnade's outer wall is
cracked and bulging, the arch at the north end is half-swallowed, and beyond it
the masonry stops entirely and the rooms are cut in blue ice. Deepest of all,
the older colonnade the glacier has carried away from its foundations stands
tilted in the altar chamber, still in rows, twenty metres from where it was
built. The mine beyond is reached by crossing a crevasse the ice opened through
the workings.

That gives every room a reason to look the way it does, and a direction of
travel: order behind you, ice ahead.

## Plan

                                 mining      chasm       glacier
                                 gallery <-- bridge  <-- altar
                                                            ^
                                                        ice arch
                                                            ^
    votive <-- nave --> colonnade --> stair --> upper sanctuary
                 ^
             snow entry  (spawn)
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import interiors as I
from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S

import kit

# -- materials -------------------------------------------------------------
ICE = "glacier_ice"
SNOW = "snow_pack"
MARBLE = "veined_marble"
ASHLAR = "pale_ashlar"
ROCK = "cliff_rock"
RUBBLE = "rubble_stone"
CRYSTAL = "blue_crystal"
SILVER = "whitehorn_silver"
BRASS = "gilt_brass"
IRON = "dark_iron"
TIMBER = "timber_grey"
TIMBER_DARK = "timber_dark"
CLOTH = "woven_cloth"
PAVING = "cobble_paving"
AMBER = "amber_resin"

# Where the temple attaches on the region map: the Glacier Temple landmark,
# whose forecourt deck sits at y = 70.45.
ANCHOR = [102.0, 70.45, -309.0]


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed & 0x7FFFFFFF)


def _tilted_column(height: float, lean: float, seed: int) -> M.Mesh:
    """A prayer column the ice has pushed off plumb."""
    column = S.column(height=height, radius=0.46, flutes=12, material=ASHLAR)
    column.transform(M.rotation_x(lean))
    column.transform(M.rotation_y((seed % 17) * 0.37))
    return column


def glacier_temple(seed: int = 20260901) -> I.Interior:
    it = I.Interior("whitehorn_glacier_temple", "The Glacier Temple", "temple",
                    "whitehorn-glacier-temple", ANCHOR,
                    "whitehorn-glacier-temple-door")
    rng = _rng(seed)
    g = it.group

    # ---------------------------------------------------------------- rooms
    it.space("snow_entry", -7, -12, 7, 0, 0.0, 5.0,
             floor_mat=SNOW, wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("north", 0.0, 4.8, 3.2)])
    it.space("nave", -15, 6, 15, 44, 0.0, 10.0,
             floor_mat=MARBLE, wall_mat=ASHLAR, ceil_mat=ASHLAR,
             ceiling="vault", vault_rise=3.4,
             doors=[("south", 0.0, 4.8, 3.2), ("east", 22.0, 4.8, 3.6),
                    ("west", 20.0, 3.4, 3.2), ("north", 0.0, 4.6, 3.6)])
    it.space("colonnade", 17, 8, 31, 34, 0.0, 6.5,
             floor_mat=PAVING, wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("west", 22.0, 4.8, 3.6), ("north", 24.0, 4.8, 3.4)])
    it.space("votive", -31, 12, -17, 28, -0.8, 4.6,
             floor_mat=RUBBLE, wall_mat=RUBBLE, ceil_mat=ASHLAR,
             doors=[("east", 20.0, 3.4, 3.2)])
    it.space("upper_sanctuary", 15, 56, 39, 78, 7.0, 8.5,
             floor_mat=MARBLE, wall_mat=ASHLAR, ceil_mat=ASHLAR,
             ceiling="vault", vault_rise=2.6,
             doors=[("south", 24.0, 4.8, 3.4)])
    it.space("ice_arch", -9, 50, 9, 62, -1.5, 7.5,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", 0.0, 4.6, 3.6), ("north", 0.0, 5.0, 3.8)])
    it.space("glacier_altar", -19, 66, 11, 94, -3.0, 13.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", 0.0, 5.4, 3.8)])

    # ------------------------------------------------------------- passages
    # Passage widths are chosen against the collision quantisation, not for
    # looks. The grid is half-metre and the server samples tile centres a metre
    # apart, so a corridor of half-width h centred on an integer marks the cell
    # at h-0.25 walkable while the ray at the next whole tile finds nothing.
    # Any half-width in (1.75, 2.00) produces that: the server lets a player
    # stand where the client cannot ground them. 3.6 and 4.0 are exactly the
    # bad cases; 3.4 (h=1.7) and 4.4 (h=2.2) are not.
    links = [
        ("threshold", (0, 0), (0, 6), 4.4, 0.0, 0.0, 3.6, 0, MARBLE, ASHLAR),
        ("east_arcade", (15, 22), (17, 22), 4.4, 0.0, 0.0, 4.6, 0, PAVING, ASHLAR),
        ("votive_door", (-15, 20), (-17, 20), 3.4, 0.0, -0.8, 3.6, 3, RUBBLE, RUBBLE),
        ("sanctuary_stair", (24, 34), (24, 56), 4.4, 0.0, 7.0, 4.2, 24, MARBLE, ASHLAR),
        ("north_walk", (0, 44), (0, 50), 4.6, 0.0, -1.5, 4.8, 5, MARBLE, ASHLAR),
        ("ice_descent", (0, 62), (0, 66), 5.0, -1.5, -3.0, 5.6, 5, ICE, ICE),
    ]
    for ident, a, b, width, y0, y1, height, steps, floor_mat, wall_mat in links:
        g.add(I.passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                        floor_mat=floor_mat, wall_mat=wall_mat,
                        ceil_mat=wall_mat, steps=steps,
                        seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    _snow_entry(g, rng)
    _nave(g, it, rng, seed)
    _colonnade(g, rng, seed)
    _votive(g, rng, seed)
    _sanctuary(g, rng, seed)
    _ice_arch(g, rng, seed)
    _glacier_altar(g, it, rng, seed)

    _metadata(it, seed)
    return it


# ------------------------------------------------------------ 1. snow entry
def _snow_entry(g, rng) -> None:
    """The narthex just inside the blue portal. Panel 1: snow entry.

    Snow blows in past the door and never quite melts, so the threshold is
    drifted and the first two metres of marble are under it.
    """
    # the inner face of the portal, still glowing
    g.add(M.box((4.6, 3.4, 0.5), center=(0.0, 1.7, -12.2), uv_scale=1.0,
                material=CRYSTAL))
    g.add(M.box((5.8, 0.5, 0.7), center=(0.0, 3.6, -12.2), uv_scale=1.0,
                material=SILVER))

    # drifts banked against the threshold and the corners
    for i in range(6):
        x = -6.0 + i * 2.4
        depth = 0.35 + 0.28 * abs(math.sin(i * 1.7))
        g.add(M.extrude([(x, -12.0), (x + 2.4, -12.0), (x + 2.4, -8.6), (x, -8.6)],
                        depth, material=SNOW))
    for corner in (-6.2, 6.2):
        drift = M.icosphere(1.5, subdivisions=1, material=SNOW)
        drift.transform(M.scaling(1.5, 0.35, 1.2))
        drift.transform(M.translation(corner, 0.05, -10.0))
        g.add(drift)

    # benches for pilgrims to unstrap crampons, and a boot scraper
    for side in (-1.0, 1.0):
        g.add(M.box((0.9, 0.42, 4.2), center=(side * 5.6, 0.21, -4.0),
                    uv_scale=0.6, material=ASHLAR))
        g.add(M.box((0.9, 0.16, 4.2), center=(side * 5.6, 0.50, -4.0),
                    uv_scale=0.6, material=TIMBER))
    g.add(M.box((0.7, 0.1, 0.14), center=(2.4, 0.06, -9.0), material=IRON))

    # two braziers, as the exterior facade has
    for side in (-1.0, 1.0):
        stem = M.cylinder(0.16, 0.13, 1.0, segments=8, uv_scale=1.2,
                          material=IRON)
        stem.transform(M.translation(side * 3.2, 0.0, -7.0))
        g.add(stem)
        bowl = M.lathe([[0.0, 0.0], [0.44, 0.12], [0.5, 0.38], [0.45, 0.44]], 12,
                       uv_scale=1.4, material=BRASS)
        bowl.transform(M.translation(side * 3.2, 1.0, -7.0))
        g.add(bowl)
        flame = M.icosphere(0.17, subdivisions=1, material="amber_resin")
        flame.transform(M.translation(side * 3.2, 1.5, -7.0))
        g.add(flame)


# ------------------------------------------------------------------ 2. nave
def _nave(g, it, rng, seed) -> None:
    """The monastery hall. Panel 2: monastery nave.

    A meltwater channel runs the length of the floor to a grated cistern at the
    north end - the temple's water supply, and the reason the nave is the only
    room with a drain.
    """
    # the channel: a cut in the marble with a silver lip
    g.add(M.box((0.9, 0.3, 36.0), center=(0.0, -0.15, 25.0), uv_scale=0.8,
                material=ICE))
    for side in (-1.0, 1.0):
        g.add(M.box((0.16, 0.12, 36.0), center=(side * 0.52, 0.06, 25.0),
                    uv_scale=0.8, material=SILVER))
    # the grate over the cistern
    for i in range(9):
        g.add(M.box((1.3, 0.08, 0.09),
                    center=(0.0, 0.06, 40.0 + i * 0.36), material=IRON))

    # two rows of columns carrying the vault
    for i in range(7):
        z = 10.0 + i * 5.2
        for side in (-1.0, 1.0):
            column = S.column(height=7.2, radius=0.52, flutes=14,
                              material=ASHLAR)
            column.transform(M.translation(side * 10.5, 0.0, z))
            g.add(column)
            # a silver ring at the springing, catching the lamplight
            ring = M.cylinder(0.58, 0.58, 0.14, segments=14, uv_scale=1.4,
                              material=SILVER)
            ring.transform(M.translation(side * 10.5, 6.6, z))
            g.add(ring)

    # banners between the columns
    for i in range(5):
        z = 12.0 + i * 6.4
        for side in (-1.0, 1.0):
            g.add(M.box((0.1, 3.2, 1.6), center=(side * 13.6, 5.0, z),
                        uv_scale=0.7, material=CLOTH))

    # the gong at the north end, on a silver frame
    for side in (-1.0, 1.0):
        g.add(M.box((0.22, 3.0, 0.22), center=(side * 1.8, 1.5, 42.4),
                    uv_scale=0.8, material=SILVER))
    g.add(M.box((4.2, 0.2, 0.2), center=(0.0, 3.0, 42.4), uv_scale=0.8,
                material=SILVER))
    gong = M.cylinder(1.15, 1.15, 0.12, segments=20, uv_scale=1.2,
                      material=BRASS)
    gong.transform(M.rotation_x(math.pi * 0.5))
    gong.transform(M.translation(0.0, 1.7, 42.4))
    g.add(gong)

    # reading desks down the aisles
    for i in range(4):
        z = 14.0 + i * 7.0
        for side in (-1.0, 1.0):
            g.add(P.workbench(length=1.8, seed=seed + i, tools=False)
                  .transformed(M.translation(side * 6.4, 0.0, z)))


# ------------------------------------------------------------- 3. colonnade
def _colonnade(g, rng, seed) -> None:
    """The prayer colonnade. Panel 3: prayer columns.

    The first room that shows the ice. Its outer (east) wall is the one nearest
    the glacier's flank, and the northern third of it is cracked and bulging,
    with ice pushing through the joints.
    """
    for i in range(8):
        z = 10.5 + i * 3.1
        for x in (20.5, 27.5):
            column = S.column(height=5.0, radius=0.4, flutes=12,
                              material=ASHLAR)
            column.transform(M.translation(x, 0.0, z))
            g.add(column)
        # a votive lamp stand between each pair
        stand = M.cylinder(0.13, 0.10, 1.15, segments=8, uv_scale=1.2,
                           material=SILVER)
        stand.transform(M.translation(24.0, 0.0, z))
        g.add(stand)
        cup = M.lathe([[0.0, 0.0], [0.20, 0.06], [0.24, 0.2], [0.20, 0.24]], 10,
                      uv_scale=1.4, material=SILVER)
        cup.transform(M.translation(24.0, 1.15, z))
        g.add(cup)
        flame = M.icosphere(0.08, subdivisions=1, material="amber_resin")
        flame.transform(M.translation(24.0, 1.34, z))
        g.add(flame)

    # the east wall failing: ice through the joints, and a bulge in the courses
    for i in range(7):
        z = 22.0 + i * 1.7
        lobe = M.icosphere(0.5 + 0.45 * rng.random(), subdivisions=1,
                           material=ICE)
        lobe.transform(M.scaling(0.55, 1.0, 1.0))
        lobe.transform(M.translation(30.7, 0.6 + 3.4 * rng.random(), z))
        g.add(lobe)
    bulge = M.icosphere(3.0, subdivisions=2, material=ASHLAR)
    bulge.transform(M.scaling(0.35, 1.1, 1.6))
    bulge.transform(M.translation(30.4, 2.6, 29.0))
    g.add(bulge)
    # fallen blocks below it
    for _ in range(9):
        block = M.box((0.7 + 0.4 * rng.random(), 0.4, 0.6 + 0.4 * rng.random()),
                      center=(28.4 + rng.random() * 1.8, 0.2,
                              24.0 + rng.random() * 8.0),
                      uv_scale=0.8, material=ASHLAR)
        block.transform(M.rotation_y(rng.random() * math.tau))
        g.add(block)


# ---------------------------------------------------------------- 4. votive
def _votive(g, rng, seed) -> None:
    """The votive chamber. Panel 8: votive chamber.

    A low rubble-vaulted room of niches. Every niche holds a lamp and a token
    left by someone who came up the pass and wanted to be remembered for it.
    """
    for row in range(3):
        y = -0.8 + 0.6 + row * 1.2
        for i in range(9):
            x = -29.5 + i * 1.5
            # A niche is a hole in a wall. Built in ICE it rendered as a
            # grid of pale panes - a tiled bathroom, not an ossuary.
            g.add(M.box((1.1, 0.9, 0.5), center=(x, y + 0.45, 27.4),
                        uv_scale=0.7, material=IRON))
            if (i + row) % 2 == 0:
                cup = M.cylinder(0.09, 0.08, 0.12, segments=7, uv_scale=1.4,
                                 material=SILVER)
                cup.transform(M.translation(x, y + 0.1, 27.2))
                g.add(cup)
                flame = M.icosphere(0.07, subdivisions=1,
                                    material="amber_resin")
                flame.transform(M.translation(x, y + 0.26, 27.2))
                g.add(flame)
    # a cairn of remembrance in the middle, the same piece as the roadside ones
    g.add(kit.cairn(1.4, seed=seed + 3, material=RUBBLE)
          .transformed(M.translation(-24.0, -0.8, 20.0)))
    for i in range(4):
        g.add(kit.cairn(0.7 + 0.4 * rng.random(), seed=seed + 20 + i,
                        material=RUBBLE)
              .transformed(M.translation(-28.0 + i * 2.6, -0.8, 15.0)))
    # candle shelf along the south wall
    g.add(M.box((12.0, 0.14, 0.6), center=(-24.0, 0.2, 12.6), uv_scale=0.7,
                material=ASHLAR))


# ------------------------------------------------------------- 5. sanctuary
def _sanctuary(g, rng, seed) -> None:
    """The upper sanctuary. Panel 9: upper sanctuary, and panel 10: materials.

    The one room the ice has not reached, and the only one with daylight: a
    tall ice-filled window in the north wall, where the monks cut through to
    the mountain face. Ice, granite and silver together, which is the material
    study the concept asks for.
    """
    # the window: a slab of glacier ice in a silver frame, lighting the room
    g.add(M.box((6.0, 5.0, 0.6), center=(27.0, 11.0, 77.6), uv_scale=1.0,
                material=ICE))
    g.add(M.box((6.8, 0.35, 0.8), center=(27.0, 13.7, 77.5), uv_scale=1.0,
                material=SILVER))
    for side in (-1.0, 1.0):
        g.add(M.box((0.35, 5.4, 0.8), center=(27.0 + side * 3.2, 11.0, 77.5),
                    uv_scale=1.0, material=SILVER))
    ring = M.arch(6.0, 3.0, 0.5, 1.0, segments=14, uv_scale=1.0,
                  material=ASHLAR)
    ring.transform(M.translation(27.0, 13.5, 77.4))
    g.add(ring)

    # the reliquary: a granite plinth, a silver casket, a crystal
    g.add(M.box((3.2, 1.0, 2.0), center=(27.0, 7.5, 72.0), uv_scale=0.7,
                material=ROCK))
    g.add(M.box((2.0, 0.9, 1.2), center=(27.0, 8.45, 72.0), uv_scale=1.0,
                material=SILVER))
    lid = M.lathe([[0.0, 0.0], [0.7, 0.12], [0.55, 0.34], [0.0, 0.4]], 12,
                  uv_scale=1.2, material=SILVER)
    lid.transform(M.translation(27.0, 8.9, 72.0))
    g.add(lid)
    gem = M.icosphere(0.3, subdivisions=2, material=CRYSTAL)
    gem.transform(M.translation(27.0, 9.5, 72.0))
    g.add(gem)

    # the silver bell, hung from a granite frame
    for side in (-1.0, 1.0):
        g.add(M.box((0.4, 4.0, 0.4), center=(20.5 + side * 0.0,
                                             9.0, 62.0 + side * 2.6),
                    uv_scale=0.8, material=ROCK))
    g.add(M.box((0.4, 0.4, 5.6), center=(20.5, 11.2, 62.0), uv_scale=0.8,
                material=ROCK))
    bell = M.lathe([[0.0, 0.0], [0.9, 0.15], [1.0, 0.9], [0.85, 1.5],
                    [0.3, 1.9], [0.0, 2.0]], 16, uv_scale=1.0, material=SILVER)
    bell.transform(M.rotation_x(math.pi))
    bell.transform(M.translation(20.5, 11.0, 62.0))
    g.add(bell)

    # benches facing the reliquary, and a marble floor inlay
    for i in range(4):
        z = 63.0 + i * 2.2
        g.add(M.box((7.0, 0.42, 0.6), center=(27.0, 7.21, z), uv_scale=0.6,
                    material=MARBLE))
    inlay = M.cylinder(3.0, 3.0, 0.05, segments=28, uv_scale=2.0,
                       material=SILVER)
    inlay.transform(M.translation(27.0, 7.03, 69.0))
    g.add(inlay)

    # the material study proper: three sample blocks on a bench, ice, granite,
    # silver, which is what the tenth panel asks for
    for i, material in enumerate((ICE, ROCK, SILVER)):
        g.add(M.box((0.8, 0.8, 0.8), center=(33.0, 7.9, 66.0 + i * 1.4),
                    uv_scale=1.0, material=material))
    g.add(M.box((1.4, 0.5, 5.4), center=(33.0, 7.25, 67.4), uv_scale=0.7,
                material=ASHLAR))


# -------------------------------------------------------------- 6. ice arch
def _ice_arch(g, rng, seed) -> None:
    """Where the building stops. Panel 4: ice arch.

    The monks' last built arch, standing in a room that is no longer theirs:
    the ice has come through the north wall and closed over the top of it.
    """
    ring = M.arch(5.0, 2.5, 0.62, 2.2, segments=16, uv_scale=1.0,
                  material=ASHLAR)
    ring.transform(M.translation(0.0, 1.5, 55.0))
    g.add(ring)
    for side in (-1.0, 1.0):
        g.add(M.box((0.9, 4.0, 2.2), center=(side * 2.95, 0.5, 55.0),
                    uv_scale=0.8, material=ASHLAR))

    # the ice closing over it
    lobe = M.icosphere(4.6, subdivisions=2, material=ICE)
    lobe.transform(M.scaling(1.5, 0.7, 0.9))
    lobe.transform(M.translation(0.0, 5.6, 56.4))
    g.add(lobe)
    for side in (-1.0, 1.0):
        shoulder = M.icosphere(2.6, subdivisions=2, material=ICE)
        shoulder.transform(M.scaling(0.8, 1.3, 1.0))
        shoulder.transform(M.translation(side * 6.2, 1.6, 57.0))
        g.add(shoulder)

    # icicles hanging from the ceiling of the transition
    spikes = []
    for _ in range(40):
        x = rng.uniform(-8.0, 8.0)
        z = rng.uniform(51.0, 61.0)
        length = 0.4 + 1.5 * rng.random()
        spike = M.cylinder(0.05 + 0.06 * rng.random(), 0.01, length,
                           segments=5, uv_scale=1.4, material=ICE)
        spike.transform(M.rotation_x(math.pi))
        spike.transform(M.translation(x, 5.9, z))
        spikes.append(spike)
    g.add(M.merge(spikes, material=ICE))

    # the last pair of columns, already off plumb
    for side, lean in ((-1.0, 0.07), (1.0, -0.05)):
        column = _tilted_column(4.6, lean, seed + int(side) + 5)
        column.transform(M.translation(side * 7.0, -1.5, 52.0))
        g.add(column)


# --------------------------------------------------------- 7. glacier altar
def _glacier_altar(g, it, rng, seed) -> None:
    """The chamber inside the ice. Panel 5: glacier altar.

    The altar is cut from the ice itself with a marble mensa set into it. Around
    it stand the columns of an older colonnade the glacier has carried out of
    its own foundations - still in two rows, still evenly spaced, and every one
    of them leaning the same way, because they are all riding the same ice.
    """
    # the altar
    g.add(M.box((5.0, 1.5, 3.0), center=(-4.0, -2.25, 84.0), uv_scale=0.8,
                material=ICE))
    g.add(M.box((4.2, 0.35, 2.4), center=(-4.0, -1.32, 84.0), uv_scale=0.9,
                material=MARBLE))
    g.add(M.box((1.4, 0.3, 0.9), center=(-4.0, -1.0, 84.0), uv_scale=1.0,
                material=SILVER))
    crystal = M.icosphere(0.85, subdivisions=2, material=CRYSTAL)
    crystal.transform(M.scaling(0.7, 1.5, 0.7))
    crystal.transform(M.translation(-4.0, 0.2, 84.0))
    g.add(crystal)

    # the carried colonnade: two rows, all leaning downhill together
    for i in range(6):
        z = 70.0 + i * 3.6
        for side in (-1.0, 1.0):
            lean = 0.13 + 0.03 * rng.random()
            column = _tilted_column(5.4, lean, seed + i * 3 + int(side))
            column.transform(M.translation(side * 8.0 - 4.0, -3.0, z))
            g.add(column)
    # one that has gone over completely
    fallen = S.column(height=5.4, radius=0.46, flutes=12, material=ASHLAR)
    fallen.transform(M.rotation_x(math.pi * 0.46))
    fallen.transform(M.translation(2.0, -2.6, 78.0))
    g.add(fallen)

    # ice columns of the chamber itself, floor to ceiling
    for _ in range(9):
        x = rng.uniform(-17.0, 9.0)
        z = rng.uniform(68.0, 92.0)
        if abs(x + 4.0) < 5.0 and abs(z - 84.0) < 5.0:
            continue
        radius = 0.5 + 0.7 * rng.random()
        pillar = M.cylinder(radius, radius * 0.8, 10.0, segments=9,
                            uv_scale=1.3, material=ICE)
        pillar.transform(M.translation(x, -3.0, z))
        g.add(pillar)

    # a ceiling of icicles, dense over the altar
    spikes = []
    for _ in range(120):
        x = rng.uniform(-18.0, 10.0)
        z = rng.uniform(67.0, 93.0)
        length = 0.5 + 2.6 * rng.random()
        spike = M.cylinder(0.06 + 0.1 * rng.random(), 0.01, length,
                           segments=5, uv_scale=1.4, material=ICE)
        spike.transform(M.rotation_x(math.pi))
        spike.transform(M.translation(x, 9.6, z))
        spikes.append(spike)
    g.add(M.merge(spikes, material=ICE))

    # waystones brought down from the road, set around the altar
    for i, (x, z) in enumerate(((-10.0, 80.0), (2.0, 80.0), (-10.0, 88.0),
                                (2.0, 88.0))):
        g.add(kit.waystone(2.1, seed=seed + 40 + i)
              .transformed(M.translation(x, -3.0, z)))




# --------------------------------------------------------- temple metadata
def _metadata(it: I.Interior, seed: int) -> None:
    g = it.group
    lamp_points = [
        (0.0, 3.0, -6.0), (0.0, 3.2, 4.0),
        (-10.5, 6.4, 14.0), (10.5, 6.4, 14.0), (-10.5, 6.4, 30.0),
        (10.5, 6.4, 30.0), (0.0, 7.4, 22.0), (0.0, 7.4, 40.0),
        (24.0, 4.6, 14.0), (24.0, 4.6, 26.0), (24.0, 4.6, 32.0),
        (-24.0, 2.6, 16.0), (-24.0, 2.6, 24.0),
        (24.0, 11.4, 62.0), (27.0, 11.4, 70.0), (33.0, 11.4, 74.0),
        (0.0, 4.0, 54.0), (0.0, 4.0, 60.0),
        (-4.0, 5.0, 76.0), (-4.0, 5.0, 88.0), (-14.0, 5.0, 82.0),
        (6.0, 5.0, 82.0),
    ]
    lamps, placed = I.hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "snow_entry"
    it.subjects = [
        ("concept-01", "snow entry", "snow_entry"),
        ("concept-02", "monastery nave", "nave"),
        ("concept-03", "prayer columns", "colonnade"),
        ("concept-04", "ice arch", "ice_arch"),
        ("concept-05", "glacier altar", "glacier_altar"),
        ("concept-08", "votive chamber", "votive"),
        ("concept-09", "upper sanctuary", "upper_sanctuary"),
        ("concept-10", "ice granite silver materials", "upper_sanctuary"),
    ]
    it.landmark("temple-narthex", "The Snow Threshold", "snow_entry", 1.6)
    it.landmark("temple-nave", "The Nave", "nave", 1.6)
    it.landmark("temple-colonnade", "The Prayer Colonnade", "colonnade", 1.6)
    it.landmark("temple-votive", "The Votive Chamber", "votive")
    it.landmark("temple-ice-arch", "The Last Arch", "ice_arch", 1.6)
    it.landmark("temple-altar", "The Glacier Altar", "glacier_altar", 1.6)
    it.landmark("temple-sanctuary", "The Upper Sanctuary", "upper_sanctuary", 1.6)

    it.interactives = [
        {"id": "temple-gong", "kind": "use", "position": [0.0, 1.7, 42.4]},
        {"id": "temple-reliquary", "kind": "lore", "position": [27.0, 9.0, 72.0]},
        {"id": "temple-altar-crystal", "kind": "lore",
         "position": [-4.0, 0.2, 84.0]},
        {"id": "temple-bell", "kind": "use", "position": [20.5, 10.0, 62.0]},
        {"id": "temple-votive-shelf", "kind": "use",
         "position": [-24.0, 0.2, 12.6]},
    ]
    it.harvestables = [
        {"id": "glacier-ice-%02d" % i, "resource": "ice",
         "position": [round(-14.0 + i * 5.0, 2), -3.0, round(70.0 + i * 4.0, 2)]}
        for i in range(4)
    ]
    it.npc_markers = [
        {"id": "temple-abbot", "name": "The Abbot", "role": "civilian",
         "position": [27.0, 7.0, 68.0]},
        {"id": "temple-cantor", "name": "Cantor", "role": "civilian",
         "position": [0.0, 0.0, 38.0]},
        {"id": "temple-warden", "name": "Ice Warden", "role": "guard",
         "position": [0.0, -1.5, 56.0]},
    ]
    it.environment = {
        "audio": [{"id": "wind", "space": "snow_entry", "loop": True},
                  {"id": "chant", "space": "nave", "loop": True},
                  {"id": "ice-groan", "space": "glacier_altar", "loop": True},
                  {"id": "drip", "space": "ice_arch", "loop": True}],
    }
    it.notes = [
        "The glacier is taking the monastery. The colonnade's east wall is "
        "cracked and bulging with ice through the joints; the last built arch "
        "is half-swallowed; and the columns in the altar chamber are an older "
        "colonnade the ice has carried off its foundations, still in rows and "
        "all leaning the same way.",
    ]


# ==========================================================================
# 2. The Whitehorn Mine
# ==========================================================================
def whitehorn_mine(seed: int = 20260902) -> I.Interior:
    """Behind the timbered adit on the region's eastern massif.

    The workings the monastery's silver came out of, and the reason the temple
    is where it is. The ice reached these too: a crevasse opened straight
    across the main gallery, and rather than abandon the far side the miners
    bridged it with the same carpentry the region uses on its gorge.
    """
    it = I.Interior("whitehorn_mine", "The Whitehorn Mine", "dungeon",
                    "whitehorn-mine", [288.0, 52.0, -138.0],
                    "whitehorn-mine-adit")
    rng = _rng(seed)
    g = it.group

    it.space("adit_head", -18, -6, -4, 8, 0.0, 4.2,
             floor_mat=RUBBLE, wall_mat=ROCK, ceil_mat=TIMBER_DARK,
             doors=[("east", 1.0, 3.8, 3.0)])
    it.space("main_gallery", 0, -8, 26, 16, -1.2, 5.0,
             floor_mat=RUBBLE, wall_mat=ROCK, ceil_mat=TIMBER_DARK,
             doors=[("west", 1.0, 3.8, 3.0), ("north", 13.0, 4.8, 3.4),
                    ("east", 4.0, 3.8, 3.0)])
    it.space("crevasse_hall", 0, 20, 26, 36, -1.2, 9.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", 13.0, 4.8, 3.4)])
    it.space("pump_room", 30, -4, 42, 12, -2.4, 4.4,
             floor_mat=RUBBLE, wall_mat=ROCK, ceil_mat=TIMBER_DARK,
             doors=[("west", 4.0, 3.8, 3.0)])

    links = [
        ("adit", (-4, 1), (0, 1), 3.4, 0.0, -1.2, 3.6, 4, RUBBLE, ROCK),
        ("gallery_north", (13, 16), (13, 20), 4.4, -1.2, -1.2, 4.6, 0, RUBBLE, ROCK),
        ("pump_stair", (26, 4), (30, 4), 3.4, -1.2, -2.4, 3.6, 4, RUBBLE, ROCK),
    ]
    _link(it, links, seed)

    # -- the adit head: the inside face of the surface portal, and the tally
    g.add(M.box((4.0, 3.2, 0.5), center=(-17.4, 1.6, 1.0), uv_scale=1.0,
                material=IRON))
    for side in (-1.0, 1.0):
        g.add(A.post(-16.0, 1.0 + side * 2.0, 0.0, 3.6, width=0.3,
                     material=TIMBER_DARK))
    g.add(A.beam((-16.0, 3.5, -1.2), (-16.0, 3.5, 3.2), 0.32,
                 material=TIMBER_DARK))
    g.add(P.workbench(length=1.8, seed=seed + 1, tools=True)
          .transformed(M.translation(-12.0, 0.0, 6.0)))
    for i in range(3):
        g.add(P.crate(size=0.6, seed=seed + 2 + i, material=TIMBER)
              .transformed(M.translation(-14.0 + i * 1.2, 0.0, -4.0)))

    # -- the main gallery: timber sets, rails, the vein in the north face
    for i in range(9):
        z = -6.0 + i * 2.6
        for side in (-1.0, 1.0):
            g.add(A.post(13.0 + side * 5.0, z, -1.2, 3.8, width=0.3,
                         material=TIMBER_DARK))
        g.add(A.beam((7.6, 2.6, z), (18.4, 2.6, z), 0.32, material=TIMBER_DARK))
        g.add(M.box((11.2, 0.18, 0.3), center=(13.0, 2.9, z), uv_scale=0.8,
                    material=TIMBER))
    for side in (-1.0, 1.0):
        g.add(M.box((0.09, 0.09, 22.0),
                    center=(13.0 + side * 0.62, -1.1, 3.0),
                    uv_scale=2.2, material=IRON))
    sleepers = [M.box((1.0, 0.1, 0.24), center=(13.0, -1.15, -7.0 + i * 1.25),
                      uv_scale=1.4, material=TIMBER) for i in range(18)]
    g.add(M.merge(sleepers, material=TIMBER))
    g.add(P.cart(seed=seed + 5, length=2.0, width=1.1)
          .transformed(M.translation(13.0, -1.2, 8.0)))
    for i in range(12):
        vein = M.box((1.4 + rng.random(), 0.26 + 0.28 * rng.random(), 0.25),
                     center=(2.0 + i * 2.0, 0.2 + 1.6 * rng.random(), 15.4),
                     uv_scale=1.2, material=SILVER)
        vein.transform(M.rotation_y(rng.uniform(-0.2, 0.2)))
        g.add(vein)
    for _ in range(12):
        heap = M.icosphere(0.4 + 0.5 * rng.random(), subdivisions=1,
                           material=RUBBLE)
        heap.transform(M.scaling(1.4, 0.5, 1.2))
        heap.transform(M.translation(rng.uniform(2.0, 24.0), -1.1,
                                     rng.uniform(-6.0, 14.0)))
        g.add(heap)

    # -- the crevasse: the ice cut the workings in half
    g.add(M.box((7.0, 14.0, 14.0), center=(13.0, -8.2, 28.0), uv_scale=1.0,
                material=IRON))
    for side in (-1.0, 1.0):
        g.add(M.box((1.2, 12.0, 14.0),
                    center=(13.0 + side * 4.1, -7.2, 28.0),
                    uv_scale=1.0, material=ICE))
    span = kit.rope_bridge(length=12.0, width=1.8, sag=0.5, seed=seed + 9,
                           deck_y=0.0)
    span.transform(M.rotation_y(math.pi * 0.5))
    span.transform(M.translation(13.0, -1.1, 28.0))
    # MeshGroup.add keeps the group's walk parts separate, so only the deck is
    # standable; add_walk here would put the ropes on the navigation layer.
    g.add(span)
    for _ in range(9):
        block = M.icosphere(0.3 + 0.5 * rng.random(), subdivisions=1,
                            material=ICE)
        block.transform(M.translation(rng.uniform(2.0, 24.0), -1.0,
                                      rng.uniform(21.0, 35.0)))
        g.add(block)
    g.add(P.well(radius=0.8, seed=seed + 11)
          .transformed(M.translation(5.0, -1.2, 23.0)))

    # -- the pump room: the workings flooded, so they built an engine
    drum = M.cylinder(1.5, 1.5, 2.4, segments=14, uv_scale=1.2,
                      material=TIMBER_DARK)
    drum.transform(M.rotation_z(math.pi * 0.5))
    drum.transform(M.translation(36.0, -1.0, 4.0))
    g.add(drum)
    for side in (-1.0, 1.0):
        g.add(A.post(36.0, 4.0 + side * 2.2, -2.4, 3.0, width=0.34,
                     material=TIMBER_DARK))
    g.add(M.box((0.3, 0.3, 6.0), center=(33.0, -0.4, 4.0), uv_scale=1.0,
                material=IRON))
    for i in range(4):
        g.add(M.box((0.24, 1.6, 0.24), center=(34.0 + i * 1.6, -1.6, 9.0),
                    uv_scale=1.0, material=IRON))
    g.add(M.box((10.0, 0.3, 2.0), center=(36.0, -2.3, 10.4), uv_scale=1.0,
                material=ICE))

    _mine_metadata(it, seed)
    return it


def _mine_metadata(it: I.Interior, seed: int) -> None:
    lamp_points = [(-12.0, 2.6, 1.0), (-8.0, 2.6, 6.0),
                   (13.0, 2.2, -4.0), (13.0, 2.2, 4.0), (13.0, 2.2, 12.0),
                   (7.0, 2.2, 24.0), (19.0, 2.2, 32.0), (13.0, 3.4, 28.0),
                   (34.0, 1.4, 2.0), (40.0, 1.4, 9.0)]
    lamps, placed = I.hanging_lamps(lamp_points, seed=seed)
    it.group.add(lamps)
    it.lamps = placed
    it.spawn_space = "adit_head"
    it.subjects = [
        ("concept-06", "mining gallery", "main_gallery"),
        ("concept-07", "chasm bridge", "crevasse_hall"),
        ("mine-01", "adit head", "adit_head"),
        ("mine-02", "pump engine", "pump_room"),
    ]
    it.landmark("mine-adit", "The Adit Head", "adit_head", 1.6)
    it.landmark("mine-gallery", "The Silver Gallery", "main_gallery", 1.6)
    it.landmark("mine-crevasse", "The Crevasse Crossing", "crevasse_hall", 1.6)
    it.landmark("mine-pump", "The Pump Engine", "pump_room", 1.6)
    it.interactives = [
        {"id": "mine-ore-cart", "kind": "container", "position": [13.0, -0.7, 8.0]},
        {"id": "mine-tally", "kind": "lore", "position": [-12.0, 0.9, 6.0]},
        {"id": "mine-winch", "kind": "use", "position": [36.0, -0.4, 4.0]},
    ]
    it.harvestables = [
        {"id": "silver-ore-%02d" % i, "resource": "ore",
         "position": [round(2.0 + i * 2.0, 2), 0.2, 15.0]} for i in range(6)
    ]
    it.npc_markers = [
        {"id": "mine-foreman", "name": "Mine Foreman", "role": "civilian",
         "position": [-10.0, 0.0, 2.0]},
        {"id": "mine-pickman", "name": "Pickman", "role": "civilian",
         "position": [8.0, -1.2, 12.0]},
    ]
    it.environment = {"audio": [{"id": "pick", "space": "main_gallery", "loop": True},
                                {"id": "ice-groan", "space": "crevasse_hall",
                                 "loop": True}]}
    it.notes = ["The crevasse span is kit.rope_bridge, the same piece the "
                "exterior uses on the gorge: the miners who bridged one "
                "bridged the other."]


# ==========================================================================
# 3. The Ice Cave
# ==========================================================================
def ice_cave(seed: int = 20260903) -> I.Interior:
    """Behind the lantern-lit mouth in the region's west.

    Not built by anyone. Meltwater cut it and refroze, so every surface is ice
    and the only worked things in it are the lamps someone hung to make it
    passable and the plank walk over the pool.
    """
    it = I.Interior("whitehorn_ice_cave", "The Whitehorn Ice Cave", "cave",
                    "whitehorn-ice-cave", [-114.0, 30.0, -42.0],
                    "whitehorn-ice-cave-mouth")
    rng = _rng(seed)
    g = it.group

    it.space("cave_mouth", -12, -8, 2, 4, 0.0, 5.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("north", -5.0, 4.8, 3.4)])
    it.space("blue_chamber", -18, 8, 12, 30, -1.6, 11.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", -5.0, 4.8, 3.4), ("east", 15.0, 3.8, 3.0),
                    ("north", 0.0, 4.8, 3.4)])
    it.space("meltwater_pool", 16, 6, 32, 24, -2.4, 6.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("west", 15.0, 3.8, 3.0)])
    it.space("crystal_vault", -10, 34, 10, 46, -3.2, 8.0,
             floor_mat=ICE, wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", 0.0, 4.8, 3.4)])

    links = [
        ("throat", (-5, 4), (-5, 8), 4.4, 0.0, -1.6, 4.6, 4, ICE, ICE),
        ("pool_walk", (12, 15), (16, 15), 3.4, -1.6, -2.4, 3.6, 3, TIMBER, ICE),
        ("vault_descent", (0, 30), (0, 34), 4.4, -1.6, -3.2, 4.6, 5, ICE, ICE),
    ]
    _link(it, links, seed)

    # -- the mouth: daylight behind you, lanterns on the ground
    g.add(M.box((5.0, 3.6, 0.5), center=(-5.0, 1.8, -7.8), uv_scale=1.0,
                material=SNOW))
    for side in (-1.0, 1.0):
        post = M.cylinder(0.07, 0.06, 1.1, segments=6, uv_scale=1.2,
                          material=IRON)
        post.transform(M.translation(-5.0 + side * 2.4, 0.0, -5.0))
        g.add(post)
        glow = M.icosphere(0.14, subdivisions=1, material=AMBER)
        glow.transform(M.translation(-5.0 + side * 2.4, 1.22, -5.0))
        g.add(glow)

    # -- the blue chamber: ice pillars, a fallen ceiling slab, icicles
    for _ in range(11):
        x = rng.uniform(-16.0, 10.0)
        z = rng.uniform(10.0, 28.0)
        radius = 0.45 + 0.8 * rng.random()
        pillar = M.cylinder(radius, radius * 0.75, 9.0, segments=9,
                            uv_scale=1.3, material=ICE)
        pillar.transform(M.translation(x, -1.6, z))
        g.add(pillar)
    slab = M.icosphere(3.2, subdivisions=2, material=ICE)
    slab.transform(M.scaling(1.6, 0.4, 1.2))
    slab.transform(M.rotation_z(0.22))
    slab.transform(M.translation(6.0, -0.9, 24.0))
    g.add(slab)
    g.add(_icicles(rng, 90, (-17.0, 11.0), (9.0, 29.0), 8.2, 2.4))

    # -- the pool: meltwater that has not refrozen, and a plank walk over it
    g.add(M.box((14.0, 0.4, 16.0), center=(24.0, -2.5, 15.0), uv_scale=1.2,
                material="water_pool"))
    planks = []
    for i in range(11):
        planks.append(M.box((1.1, 0.12, 2.0), center=(18.0 + i * 1.2, -1.9, 15.0),
                            uv_scale=0.8, material=TIMBER))
    g.add_walk(M.merge(planks, material=TIMBER))
    for side in (-1.0, 1.0):
        rope = M.tube(np.array([[17.5, -1.0, 15.0 + side * 1.3],
                                [30.5, -1.0, 15.0 + side * 1.3]]),
                      [0.04, 0.04], segments=5, uv_scale=2.0, material=CLOTH)
        g.add(rope)
        for i in range(4):
            g.add(M.cylinder(0.09, 0.08, 1.1, segments=6, uv_scale=1.2,
                             material=TIMBER_DARK)
                  .transformed(M.translation(18.5 + i * 3.6, -1.9,
                                             15.0 + side * 1.3)))

    # -- the crystal vault: what the cave is worth walking to
    for i in range(7):
        angle = i * math.tau / 7.0
        shard = M.icosphere(0.5 + 0.5 * rng.random(), subdivisions=2,
                            material=CRYSTAL)
        shard.transform(M.scaling(0.55, 2.2, 0.55))
        shard.transform(M.rotation_z(0.16 * math.cos(angle)))
        shard.transform(M.translation(math.cos(angle) * 5.5, -3.2,
                                      40.0 + math.sin(angle) * 4.0))
        g.add(shard)
    core = M.icosphere(1.5, subdivisions=2, material=CRYSTAL)
    core.transform(M.scaling(0.8, 1.8, 0.8))
    core.transform(M.translation(0.0, -3.0, 40.0))
    g.add(core)
    g.add(_icicles(rng, 60, (-9.0, 35.0), (9.0, 45.0), 4.4, 2.0))

    _cave_metadata(it, seed)
    return it


def _cave_metadata(it: I.Interior, seed: int) -> None:
    lamp_points = [(-5.0, 3.0, -2.0), (-5.0, 3.4, 6.0),
                   (-12.0, 5.0, 14.0), (6.0, 5.0, 14.0), (-4.0, 5.0, 26.0),
                   (20.0, 2.6, 12.0), (28.0, 2.6, 20.0),
                   (0.0, 3.6, 38.0), (0.0, 3.6, 44.0)]
    lamps, placed = I.hanging_lamps(lamp_points, seed=seed)
    it.group.add(lamps)
    it.lamps = placed
    it.spawn_space = "cave_mouth"
    it.subjects = [
        ("cave-01", "cave mouth", "cave_mouth"),
        ("cave-02", "blue chamber", "blue_chamber"),
        ("cave-03", "meltwater pool", "meltwater_pool"),
        ("cave-04", "crystal vault", "crystal_vault"),
    ]
    it.landmark("cave-mouth", "The Cave Mouth", "cave_mouth", 1.6)
    it.landmark("cave-blue", "The Blue Chamber", "blue_chamber", 1.6)
    it.landmark("cave-pool", "The Meltwater Pool", "meltwater_pool", 1.6)
    it.landmark("cave-vault", "The Crystal Vault", "crystal_vault", 1.6)
    it.interactives = [
        {"id": "cave-crystal-core", "kind": "lore", "position": [0.0, -1.2, 40.0]},
    ]
    it.harvestables = [
        {"id": "cave-ice-%02d" % i, "resource": "ice",
         "position": [round(-14.0 + i * 5.0, 2), -1.6, round(12.0 + i * 3.0, 2)]}
        for i in range(5)
    ] + [
        {"id": "cave-crystal-%02d" % i, "resource": "crystal",
         "position": [round(math.cos(i * 1.2) * 5.5, 2), -3.2,
                      round(40.0 + math.sin(i * 1.2) * 4.0, 2)]}
        for i in range(4)
    ]
    it.npc_markers = [
        {"id": "cave-watch", "name": "Cave Watch", "role": "guard",
         "position": [-5.0, 0.0, 0.0]},
    ]
    it.environment = {"audio": [{"id": "drip", "space": "blue_chamber", "loop": True},
                                {"id": "water", "space": "meltwater_pool",
                                 "loop": True}]}
    it.notes = ["Nobody built this. The only worked things in it are the hung "
                "lamps and the plank walk over the pool."]


# ==========================================================================
# 4. The Frost Barrow
# ==========================================================================
def frost_barrow(seed: int = 20260904) -> I.Interior:
    """Under the cairn ridge in the region's west.

    Older than the monastery and not of it. The cairns on the ridge above are
    the roof of this: a creep passage into a gallery of stone cists, and one
    chamber at the end that the monks walled up rather than empty.
    """
    it = I.Interior("whitehorn_frost_barrow", "The Frost Barrow", "barrow",
                    "whitehorn-cairn-field-cairn_ridge",
                    [-87.0, 62.0, -204.0], "whitehorn-barrow-door")
    rng = _rng(seed)
    g = it.group

    it.space("barrow_entry", -10, -8, 2, 2, 0.0, 3.2,
             floor_mat=RUBBLE, wall_mat=RUBBLE, ceil_mat=ROCK,
             doors=[("north", -4.0, 3.8, 2.6)])
    it.space("cist_gallery", -16, 6, 8, 22, -1.2, 3.6,
             floor_mat=RUBBLE, wall_mat=RUBBLE, ceil_mat=ROCK,
             doors=[("south", -4.0, 3.8, 2.6), ("east", 15.0, 3.8, 2.6)])
    it.space("barrow_chamber", 12, 8, 26, 26, -2.0, 5.0,
             floor_mat=RUBBLE, wall_mat=ROCK, ceil_mat=ROCK,
             doors=[("west", 15.0, 3.8, 2.6)])

    links = [
        ("creep", (-4, 2), (-4, 6), 3.4, 0.0, -1.2, 2.8, 3, RUBBLE, RUBBLE),
        ("inner_door", (8, 15), (12, 15), 3.4, -1.2, -2.0, 3.2, 3, RUBBLE, ROCK),
    ]
    _link(it, links, seed)

    # -- the entry: a cairn standing inside, the same piece as the ridge above
    g.add(kit.cairn(1.5, seed=seed + 1, material=RUBBLE)
          .transformed(M.translation(-8.0, 0.0, -5.0)))
    g.add(M.box((3.6, 0.4, 0.6), center=(-4.0, 2.6, 1.6), uv_scale=0.8,
                material=ROCK))

    # -- the cist gallery: stone boxes down both walls, lids on and off
    for i in range(6):
        z = 8.0 + i * 2.4
        for side in (-1.0, 1.0):
            x = -4.0 + side * 9.0
            g.add(M.box((2.4, 0.9, 1.4), center=(x, -0.75, z), uv_scale=0.7,
                        material=ROCK))
            if (i + int(side)) % 3 != 0:
                g.add(M.box((2.6, 0.16, 1.6), center=(x, -0.22, z),
                            uv_scale=0.7, material=ROCK))
            else:
                lid = M.box((2.6, 0.16, 1.6), center=(x + side * 1.6, -1.12, z),
                            uv_scale=0.7, material=ROCK)
                lid.transform(M.rotation_y(rng.uniform(-0.3, 0.3)))
                g.add(lid)
                cup = M.cylinder(0.1, 0.09, 0.13, segments=7, uv_scale=1.4,
                                 material=SILVER)
                cup.transform(M.translation(x, -0.3, z))
                g.add(cup)
    for i in range(4):
        g.add(kit.waystone(1.6 + 0.3 * rng.random(), seed=seed + 20 + i)
              .transformed(M.translation(-4.0, -1.2, 9.0 + i * 3.6)))

    # -- the sealed chamber: the monks walled it and left a shrine at the wall
    g.add(M.box((12.0, 4.0, 1.0), center=(19.0, 0.0, 24.6), uv_scale=0.8,
                material=ASHLAR))
    g.add(M.box((2.4, 0.4, 0.6), center=(19.0, -1.6, 23.6), uv_scale=0.8,
                material=ASHLAR))
    for side in (-1.0, 1.0):
        cup = M.lathe([[0.0, 0.0], [0.18, 0.05], [0.22, 0.18], [0.18, 0.22]], 10,
                      uv_scale=1.4, material=SILVER)
        cup.transform(M.translation(19.0 + side * 1.6, -1.4, 23.6))
        g.add(cup)
        flame = M.icosphere(0.08, subdivisions=1, material=AMBER)
        flame.transform(M.translation(19.0 + side * 1.6, -1.2, 23.6))
        g.add(flame)
    # a central cist, larger than the rest, its lid pushed aside
    g.add(M.box((3.4, 1.2, 2.2), center=(19.0, -1.4, 16.0), uv_scale=0.7,
                material=ROCK))
    pushed = M.box((3.6, 0.18, 2.4), center=(19.0, -0.7, 18.6), uv_scale=0.7,
                   material=ROCK)
    pushed.transform(M.rotation_y(0.18))
    g.add(pushed)
    for i in range(5):
        g.add(kit.cairn(0.6 + 0.5 * rng.random(), seed=seed + 40 + i,
                        material=RUBBLE)
              .transformed(M.translation(14.0 + i * 2.4, -2.0, 11.0)))

    _barrow_metadata(it, seed)
    return it


def _barrow_metadata(it: I.Interior, seed: int) -> None:
    lamp_points = [(-4.0, 2.2, -3.0), (-4.0, 2.2, 10.0), (-4.0, 2.2, 18.0),
                   (19.0, 2.6, 13.0), (19.0, 2.6, 21.0)]
    lamps, placed = I.hanging_lamps(lamp_points, seed=seed)
    it.group.add(lamps)
    it.lamps = placed
    it.spawn_space = "barrow_entry"
    it.subjects = [
        ("barrow-01", "barrow entry", "barrow_entry"),
        ("barrow-02", "cist gallery", "cist_gallery"),
        ("barrow-03", "the sealed chamber", "barrow_chamber"),
    ]
    it.landmark("barrow-entry", "The Barrow Creep", "barrow_entry", 1.4)
    it.landmark("barrow-gallery", "The Cist Gallery", "cist_gallery", 1.4)
    it.landmark("barrow-chamber", "The Sealed Chamber", "barrow_chamber", 1.4)
    it.interactives = [
        {"id": "barrow-wall", "kind": "lore", "position": [19.0, -1.4, 23.6]},
        {"id": "barrow-great-cist", "kind": "container",
         "position": [19.0, -0.8, 16.0]},
    ]
    it.harvestables = []
    it.npc_markers = []
    it.environment = {"audio": [{"id": "wind", "space": "barrow_entry",
                                 "loop": True}]}
    it.notes = ["Older than the monastery and not of it. The monks walled the "
                "end chamber rather than empty it, and left a shrine at the "
                "wall."]


# --------------------------------------------------------------- helpers
def _link(it: I.Interior, links, seed: int) -> None:
    """Cut the passages for a section and record them for the camera set."""
    for ident, a, b, width, y0, y1, height, steps, floor_mat, wall_mat in links:
        it.group.add(I.passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                               floor_mat=floor_mat, wall_mat=wall_mat,
                               ceil_mat=wall_mat, steps=steps,
                               seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}


def _icicles(rng, count, lo, hi, ceiling, drop):
    spikes = []
    for _ in range(count):
        x = rng.uniform(lo[0], hi[0])
        z = rng.uniform(lo[1], hi[1])
        length = 0.4 + drop * rng.random()
        spike = M.cylinder(0.05 + 0.08 * rng.random(), 0.01, length,
                           segments=5, uv_scale=1.4, material=ICE)
        spike.transform(M.rotation_x(math.pi))
        spike.transform(M.translation(x, ceiling, z))
        spikes.append(spike)
    return M.merge(spikes, material=ICE)


ALL = {
    "glacier_temple": glacier_temple,
    "whitehorn_mine": whitehorn_mine,
    "ice_cave": ice_cave,
    "frost_barrow": frost_barrow,
}


# ==========================================================================
# The combined insides map
# ==========================================================================
# Eternal Lands puts every inside belonging to a region on one map, separated by
# unwalkable void, and sends the player to a different arrival point depending
# on which door was used. Doing the same here means one GLB, one manifest, one
# collision grid and one server map key instead of four of each, and one load
# rather than a load per doorway.
#
# The blackspace is not drawn. The collision grid is built only where a Walk_
# surface exists, so the gutters between the four sections are already blocked,
# and nothing is rendered in them either - a player walking off the edge of a
# section finds no floor and no geometry, which is exactly what EL's void is.
#
# The offsets keep about thirty metres of nothing between any two sections.
# That gap is not decoration: it is what stops a lamp in the mine lighting the
# barrow, and what keeps a camera in one section from seeing into another.
LAYOUT = {
    "glacier_temple": (0.0, 0.0),
    "whitehorn_mine": (95.0, 0.0),
    "ice_cave": (95.0, 95.0),
    "frost_barrow": (0.0, 130.0),
}

# Shift the assembly clear of the origin so the whole map sits in positive
# coordinates with a margin, the way a server map is indexed. Chosen so the
# result fits inside the 192 m an interior ELM allows without a server change.
LAYOUT_ORIGIN = (40.0, 20.0)

MIN_GUTTER = 20.0


def combine(seed: int = 20260901) -> I.Interior:
    """Assemble the four Whitehorn insides onto one map with void between."""
    combined = I.Interior("whitehorn_insides", "Whitehorn Range Insides",
                          "insides", "whitehorn-glacier-temple",
                          [102.0, 70.45, -309.0],
                          "whitehorn-glacier-temple-door")
    combined.arrivals = []
    combined.sections = []
    footprints = {}

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]
        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        lo, hi = part.group.walk_bounds()
        footprints[key] = (float(lo[0]), float(lo[2]), float(hi[0]), float(hi[2]))

        def move(position, dx=dx, dz=dz):
            return [round(float(position[0]) + dx, 2),
                    round(float(position[1]), 2),
                    round(float(position[2]) + dz, 2)]

        for space_key, space in part.spaces.items():
            combined.spaces["%s.%s" % (key, space_key)] = {
                "x0": space["x0"] + dx, "x1": space["x1"] + dx,
                "z0": space["z0"] + dz, "z1": space["z1"] + dz,
                "floor": space["floor"], "height": space["height"]}
        for run_key, run in part.passages.items():
            combined.passages["%s.%s" % (key, run_key)] = {
                "a": (run["a"][0] + dx, run["a"][1] + dz),
                "b": (run["b"][0] + dx, run["b"][1] + dz),
                "y0": run["y0"], "y1": run["y1"],
                "width": run["width"], "height": run["height"]}

        for entry in part.landmarks:
            item = dict(entry)
            item["position"] = move(entry["position"])
            if "space" in entry:
                item["space"] = "%s.%s" % (key, entry["space"])
            item["section"] = key
            combined.landmarks.append(item)
        for source, target in ((part.interactives, combined.interactives),
                               (part.harvestables, combined.harvestables),
                               (part.npc_markers, combined.npc_markers)):
            for entry in source:
                item = dict(entry)
                item["position"] = move(entry["position"])
                item["section"] = key
                target.append(item)
        combined.lamps.extend(move(p) for p in part.lamps)
        combined.open_to_sky.extend("%s.%s" % (key, s) for s in part.open_to_sky)
        for ident, subject, space in part.subjects:
            combined.subjects.append(
                ("%s-%s" % (key, ident), "%s: %s" % (part.name, subject),
                 "%s.%s" % (key, space)))

        spawn_space = combined.spaces["%s.%s" % (key, part.spawn_space)]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": "%s.%s" % (key, part.spawn_space), "position": arrival})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "surfaceLandmark": part.anchor_landmark,
            "surfacePosition": part.anchor_position,
            "spaces": ["%s.%s" % (key, s) for s in part.spaces],
            "notes": part.notes})

    _assert_gutters(footprints)

    combined.spawn_space = "glacier_temple.snow_entry"
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.30, 0.36, 0.46], "energy": 0.46},
        "fog": {"enabled": True, "colour": [0.42, 0.50, 0.60],
                "begin": 24.0, "end": 90.0},
        "audio": [entry for key, build_fn in ALL.items()
                  for entry in _section_audio(key, build_fn, seed)],
    }
    combined.notes = [
        "Four insides on one map with unwalkable void between them, in the "
        "Eternal Lands manner: one GLB, one collision grid and one server map "
        "key, entered at a different arrival depending on which surface door "
        "was used.",
        "The void is not drawn. The collision grid is built only where a Walk_ "
        "surface exists, so the gutters are blocked already, and nothing is "
        "rendered in them - walking off a section's edge finds no floor and no "
        "geometry.",
        "Section offsets keep at least %.0f m of nothing between any two, "
        "checked at build time." % MIN_GUTTER,
    ]
    return combined


def _section_audio(key, build_fn, seed):
    part = build_fn(seed)
    for entry in part.environment.get("audio", []):
        item = dict(entry)
        item["space"] = "%s.%s" % (key, entry["space"])
        item["section"] = key
        yield item


def _assert_gutters(footprints) -> None:
    """Fail the build if two sections come within MIN_GUTTER of each other.

    The void between sections is the whole point of the layout, and it is set
    by hand-chosen offsets. Without this check a later edit that grows one
    section by fifteen metres would silently join it to its neighbour, and the
    first sign would be a player walking out of the mine into the barrow.
    """
    keys = list(footprints)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ax0, az0, ax1, az1 = footprints[a]
            bx0, bz0, bx1, bz1 = footprints[b]
            gap_x = max(bx0 - ax1, ax0 - bx1)
            gap_z = max(bz0 - az1, az0 - bz1)
            if max(gap_x, gap_z) < MIN_GUTTER:
                raise SystemExit(
                    "sections %r and %r are only %.1f m apart; the layout needs "
                    "at least %.0f m of void between every pair"
                    % (a, b, max(gap_x, gap_z), MIN_GUTTER))


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR
from amberwood.interiors import Interior


def snowline_cell(seed: int = 20260905) -> Interior:
    """The cell the snowline is measured from, cut behind the east shrine."""
    return SR.shrine("whitehorn_snowline_cell", "The Snowline Cell", "whitehorn-shrine-02",
                     [354.0, 58.1, -192.0], "snowline-cell-door",
                     palette={"floor": PAVING, "wall": ASHLAR, "ceil": MARBLE,
                              "accent": SILVER, "earth": "packed_earth", "metal": BRASS},
                     seed=seed, style="stone")


def cascade_cave(seed: int = 20260906) -> Interior:
    """A cave behind the west watch, where the meltwater comes through."""
    return SR.cave("whitehorn_cascade_cave", "The Cascade Cave",
                   "whitehorn-cairn-field-west_watch", [-132.0, 47.6, -132.0],
                   "west-watch-cave-mouth",
                   palette={"floor": "packed_earth", "rock": ROCK, "water": "water_deep",
                            "bone": "pale_ashlar"},
                   seed=seed, den="Glacier Crab", pool=True)


def gate_store(seed: int = 20260907) -> Interior:
    """The Ration Sister's store by the Whitehorn Gate."""
    return SR.cottage("whitehorn_gate_store", "The Ration Sister's Store", "whitehorn-south-gate",
                      [-12.0, 19.9, 84.0], "gate-store-door",
                      palette={"floor": TIMBER, "wall": ASHLAR, "roof": TIMBER_DARK,
                               "timber": TIMBER_DARK, "stone": RUBBLE, "cloth": CLOTH,
                               "iron": IRON},
                      seed=seed, trade="chandlery")


ALL.update({"snowline_cell": snowline_cell, "cascade_cave": cascade_cave,
            "gate_store": gate_store})
LAYOUT.update({"cascade_cave": (200.0, 6.0), "snowline_cell": (200.0, 100.0),
               "gate_store": (200.0, 170.0)})
