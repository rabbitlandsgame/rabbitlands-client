"""Mirrorhold's interiors.

Three places the region needs an inside for, built on the shared interiors
toolkit (`amberwood.interiors`: `chamber`, `passage`, the `Interior` container)
and Mirrorhold's own kit in `landmarks.py`.

They are chosen to answer questions the exterior raises rather than to add
generic dungeon:

* **The Lens Vault**, under the orrery, is where the mirrors and lenses are
  made. It explains the instrument on the summit.
* **The Mirror Cistern**, under the fountain plaza, is the waterworks that
  holds the terrace basins still and drops the rock flour out of the meltwater.
  It explains both the reflecting pools and why the lake is turquoise.
* **The Stair Cellars**, cut back into the rock behind the cliff town, are the
  lived-in counterweight to the two monumental ones.

Materials come from Mirrorhold's pinned set; interiors register only what they
actually use, so nothing here enlarges the region package.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood.interiors import Interior, chamber, passage

import landmarks as L

# Mirrorhold's palette, named once.
ASHLAR = "pale_ashlar"
MARBLE = "veined_marble"
ROCK = "cliff_rock"
RUBBLE = "rubble_stone"
PAVING = "cobble_paving"
BRASS = "gilt_brass"
IRON = "dark_iron"
CRYSTAL = "blue_crystal"
MIRROR = "mirror_glass"
ICE = "glacier_ice"
TIMBER = "timber_grey"
TIMBER_WARM = "timber_warm"
CARVED = "carved_wood"
CLOTH = "woven_cloth"
SLATE = "slate_roof"
AMBER = "amber_resin"
W_POOL = "water_pool"
W_STREAM = "water_stream"

EYE = 1.7


def _link(it: Interior, ident, a, b, width, y0, y1, height, steps,
          floor_mat, wall_mat, ceil_mat, seed=0) -> None:
    """Add a passage and register it as a space, so cameras and collision see it."""
    it.group.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                         floor_mat=floor_mat, wall_mat=wall_mat,
                         ceil_mat=ceil_mat, steps=steps, seed=seed))
    it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                        "z0": min(a[1], b[1]) - width * 0.5,
                        "x1": max(a[0], b[0]) + width * 0.5,
                        "z1": max(a[1], b[1]) + width * 0.5,
                        "floor": min(y0, y1), "height": height}
    it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                          "width": width, "height": height}


def _still_water(x0, z0, x1, z1, y, material=W_POOL) -> M.Mesh:
    """A flat water surface. Never a walk surface: you do not stand on it."""
    return M.quad([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)],
                  uv_scale=0.25, material=material)


def _hung_lamps(points, seed: int = 0):
    """Crystal vessels on brass hooks.

    `interiors.hanging_lamps` hangs amber ones, which is Amberwood's light.
    Mirrorhold's readable light is the blue lens, so this is the same fitting
    with the region's own vessel in it. Returns (group, placed) to match.
    """
    out = S.MeshGroup()
    placed = []
    for i, (x, y, z) in enumerate(points):
        out.add(M.box((0.06, 0.5, 0.06), center=(x, y - 0.25, z), material=BRASS))
        out.add(M.lathe([[0.0, 0.0], [0.26, 0.1], [0.30, 0.34], [0.20, 0.46],
                         [0.0, 0.5]], 10, uv_scale=1.0, material=BRASS)
                .translate(x, y - 0.98, z))
        out.add(M.icosphere(0.19, subdivisions=1, material=CRYSTAL)
                .translate(x, y - 0.72, z))
        placed.append([round(x, 2), round(y - 0.72, 2), round(z, 2)])
    return out, placed


def _brass_rail(length: float, height: float = 1.0) -> M.Mesh:
    parts = [M.box((length, 0.08, 0.08), center=(0.0, height, 0.0), material=BRASS)]
    for i in range(max(2, int(length / 2.0)) + 1):
        x = -length * 0.5 + length * i / max(2, int(length / 2.0))
        parts.append(M.box((0.07, height, 0.07), center=(x, height * 0.5, 0.0),
                           material=BRASS))
    return M.merge(parts, BRASS)


# ------------------------------------------------------------ 1. Lens Vault

def lens_vault(seed: int = 20260901) -> Interior:
    """Under the orrery: where Mirrorhold grinds its mirrors.

    The plan is a working sequence, not a dungeon loop - you come down the
    stair onto the sighting floor, and the rooms off it are the stages of
    making a mirror: grind, anneal, then test it against the still pool in the
    well. The region is named for reflective water, so the instrument of record
    here is a liquid mirror rather than a lens.
    """
    it = Interior("mirrorhold_lens_vault", "The Lens Vault", "workshop",
                  "orrery", [162.0, 124.0, -267.0], "lens-vault-stair")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("stairhead", -4, -23, 4, -15, 6.0, 4.0, floor_mat=MARBLE,
             wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("north", 0.0, 3.2, 2.8)])
    it.space("sighting_floor", -12, -12, 12, 12, 0.0, 8.0, floor_mat=MARBLE,
             wall_mat=ASHLAR, ceil_mat=ASHLAR, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 3.2, 2.8), ("east", 0.0, 3.0, 2.8),
                    ("north", -2.0, 3.0, 2.8), ("west", 0.0, 3.0, 2.8)])
    it.space("grinding_room", 18, -10, 34, 8, -0.8, 5.2, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("west", 0.0, 3.0, 2.8), ("north", 26.0, 2.8, 2.6)])
    it.space("annealing_ice", 18, 14, 32, 28, -0.8, 4.4, floor_mat=RUBBLE,
             wall_mat=ICE, ceil_mat=ICE,
             doors=[("south", 26.0, 2.8, 2.6)])
    it.space("mirror_well", -34, -9, -18, 9, -7.2, 11.0, floor_mat=ROCK,
             wall_mat=ROCK, ceil_mat=ASHLAR,
             doors=[("east", 0.0, 3.0, 2.8)])
    it.space("chart_aisle", -9, 18, 9, 32, 0.0, 4.8, floor_mat=MARBLE,
             wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("south", -2.0, 3.0, 2.8)])

    _link(it, "descent", (0, -15), (0, -12), 3.2, 6.0, 0.0, 3.6, 12,
          MARBLE, ASHLAR, ASHLAR, seed + 1)
    _link(it, "grind_aisle", (12, 0), (18, 0), 3.0, 0.0, -0.8, 3.4, 3,
          PAVING, ASHLAR, ASHLAR, seed + 2)
    _link(it, "well_stair", (-12, 0), (-18, 0), 3.0, 0.0, -7.2, 3.6, 14,
          ROCK, ROCK, ASHLAR, seed + 3)
    _link(it, "chart_link", (-2, 12), (-2, 18), 3.0, 0.0, 0.0, 3.4, 0,
          MARBLE, ASHLAR, ASHLAR, seed + 4)

    # -- the sighting floor: a brass meridian inlaid across it, and an oculus
    # looking up at the underside of the sphere on the terrace above.
    g.add(M.box((0.18, 0.06, 23.0), center=(0.0, 0.03, 0.0), material=BRASS))
    for i in range(9):
        z = -10.0 + i * 2.5
        g.add(M.box((0.9, 0.05, 0.09), center=(0.0, 0.03, z), material=BRASS))
    # graduated arc, the degrees of altitude
    for i in range(19):
        angle = math.pi * (i / 18.0)
        r = 9.4
        g.add(M.box((0.5, 0.05, 0.08),
                    center=(math.cos(angle) * r, 0.03, math.sin(angle) * r),
                    material=BRASS).rotate_y(-angle))
    # the oculus ring, open to the drum above
    g.add(M.lathe([[3.0, 10.6], [3.5, 10.6], [3.5, 11.2], [3.0, 11.2]], 28,
                  uv_scale=0.8, material=BRASS))
    it.open_to_sky.append("sighting_floor")
    # eight columns carrying the vault
    for i in range(8):
        angle = math.pi * 2.0 * i / 8 + math.pi / 8
        g.add(S.column(7.4, 0.42, 12, MARBLE)
              .translate(math.cos(angle) * 9.6, 0.0, math.sin(angle) * 9.6))
    # the working instrument: a small sighting frame on the meridian
    g.add(L.armillary(1.5, seed=seed + 11).translate(0.0, 2.4, 4.0))
    g.add(M.cylinder(0.55, 0.42, 1.9, segments=12, uv_scale=0.8,
                     material=ASHLAR).translate(0.0, 0.0, 4.0))

    # -- grinding room: laps, blanks, and a water drive off the cistern main
    cx, cz = it.centre("grinding_room")
    for i in range(3):
        bx = 21.0 + i * 5.0
        g.add(M.box((3.0, 0.95, 2.0), center=(bx, -0.32, -5.0), uv_scale=0.6,
                    material=ASHLAR))
        # the lap: a shallow brass disc that the blank is worked against
        g.add(M.lathe([[1.2, 0.0], [1.2, 0.12], [0.0, 0.12]], 20, uv_scale=0.9,
                      material=BRASS).translate(bx, 0.16, -5.0))
        g.add(M.cylinder(0.16, 0.14, 1.1, segments=8, uv_scale=1.0,
                         material=IRON).translate(bx, 0.28, -5.0))
    # blank racks against the north wall
    for i in range(6):
        rx = 20.0 + i * 2.3
        g.add(M.box((1.9, 0.12, 1.4), center=(rx, 0.9, 5.6), uv_scale=0.6,
                    material=TIMBER))
        g.add(M.box((0.14, 1.0, 0.14), center=(rx - 0.85, 0.4, 5.6), material=TIMBER))
        g.add(M.box((0.14, 1.0, 0.14), center=(rx + 0.85, 0.4, 5.6), material=TIMBER))
        if i % 2 == 0:
            g.add(M.lathe([[0.7, 0.0], [0.7, 0.1], [0.0, 0.1]], 16, uv_scale=0.9,
                          material=CRYSTAL).translate(rx, 1.02, 5.6))
    # the drive shaft along the ceiling, and the channel that turns it
    g.add(M.tube(np.array([[19.0, 3.9, -5.0], [33.0, 3.9, -5.0]]), [0.12, 0.12],
                 segments=8, cap_start=True, cap_end=True, material=IRON))
    g.add(S.water_channel(15.0, 1.1, 0.4, seed + 12)
          .translate(26.0, -0.8, 7.0).rotate_y(0.0))

    # -- annealing room: ice-lined, blanks cooling slowly in sand beds
    ax, az = it.centre("annealing_ice")
    for i in range(4):
        sx = 20.5 + (i % 2) * 7.0
        sz = 17.5 + (i // 2) * 6.5
        g.add(M.box((5.0, 0.55, 4.0), center=(sx, -0.52, sz), uv_scale=0.5,
                    material=RUBBLE))
        g.add(M.box((4.4, 0.16, 3.4), center=(sx, -0.18, sz), uv_scale=0.5,
                    material=PAVING))
        if i != 3:
            g.add(M.lathe([[0.85, 0.0], [0.85, 0.11], [0.0, 0.11]], 18,
                          uv_scale=0.9, material=MIRROR).translate(sx, -0.08, sz))
    # rime on the walls, as blocky frost
    for _ in range(22):
        x = float(rng.uniform(19.0, 31.0))
        z = float(rng.uniform(15.0, 27.0))
        y = float(rng.uniform(0.4, 3.2))
        g.add(M.box((float(rng.uniform(0.3, 0.9)), float(rng.uniform(0.1, 0.4)),
                     0.16), center=(x, y, 13.9), material=ICE))

    # -- the mirror well: a still dark pool used as a horizontal mirror
    wx, wz = it.centre("mirror_well")
    g.add(_still_water(-31.0, -6.0, -21.0, 6.0, -6.4, MIRROR))
    # the coping you stand on to look into it
    for side in (-1, 1):
        g.add(M.box((10.4, 0.4, 0.7), center=(-26.0, -7.0, side * 6.4),
                    uv_scale=0.5, material=ASHLAR))
    g.add(_brass_rail(10.0).translate(-26.0, -6.8, 6.4))
    # the plumb line and its frame, hung over the centre
    g.add(M.tube(np.array([[-31.5, 3.4, 0.0], [-20.5, 3.4, 0.0]]), [0.14, 0.14],
                 segments=8, cap_start=True, cap_end=True, material=IRON))
    g.add(M.tube(np.array([[-26.0, 3.4, 0.0], [-26.0, -5.9, 0.0]]), [0.03, 0.03],
                 segments=6, cap_start=True, cap_end=True, material=BRASS))
    g.add(M.icosphere(0.22, subdivisions=1, material=BRASS)
          .translate(-26.0, -6.0, 0.0))
    # a crystal lamp on each wall, the only light down here
    for z in (-4.0, 0.0, 4.0):
        g.add(L.crystal_lamp(2.2).translate(-33.0, -7.2, z))

    # -- chart aisle: presses of charts, an instrument bench, a rose light
    for i in range(5):
        px = -7.5 + i * 3.6
        g.add(M.box((2.6, 2.4, 1.1), center=(px, 1.2, 30.0), uv_scale=0.5,
                    material=TIMBER))
        for shelf in range(3):
            g.add(M.box((2.4, 0.08, 1.0), center=(px, 0.5 + shelf * 0.75, 30.0),
                        uv_scale=0.5, material=TIMBER_WARM))
    g.add(M.box((5.0, 0.9, 1.4), center=(0.0, 0.45, 21.0), uv_scale=0.6,
                material=TIMBER))
    g.add(P.workbench(3.0, seed + 13).translate(0.0, 0.9, 21.0))
    g.add(L.rose_window(1.6, 10).translate(0.0, 3.0, 32.4))

    it.lamps = [[0.0, 5.0, 0.0], [26.0, 3.4, -5.0], [25.0, 2.8, 21.0],
                [-26.0, -3.0, 0.0], [0.0, 3.2, 25.0], [0.0, 8.4, -19.0]]
    lamp_group, _ = _hung_lamps([(0.0, 5.0, 0.0), (26.0, 3.4, -5.0),
                                 (0.0, 3.2, 25.0)], seed + 14)
    g.add(lamp_group)

    it.spawn_space = "stairhead"
    it.subjects = [
        ("concept-01", "stair down from the orrery drum", "stairhead"),
        ("concept-02", "the sighting floor and its meridian", "sighting_floor"),
        ("concept-03", "oculus to the sphere above", "sighting_floor"),
        ("concept-04", "grinding laps and blank racks", "grinding_room"),
        ("concept-05", "the drive shaft and its channel", "grinding_room"),
        ("concept-06", "ice-lined annealing beds", "annealing_ice"),
        ("concept-07", "descent to the mirror well", "well_stair"),
        ("concept-08", "the still pool as a horizontal mirror", "mirror_well"),
        ("concept-09", "chart presses and instrument bench", "chart_aisle"),
        ("concept-10", "marble brass crystal ice materials", "sighting_floor"),
    ]
    it.landmark("the-meridian", "The Meridian Line", "sighting_floor", 0.4)
    it.landmark("the-mirror-well", "The Mirror Well", "mirror_well", 1.2)
    it.landmark("annealing-beds", "The Annealing Beds", "annealing_ice", 0.8)
    it.interactives = [
        {"id": "meridian-sight", "label": "Meridian Sight", "space": "sighting_floor"},
        {"id": "grinding-lap", "label": "Grinding Lap", "space": "grinding_room"},
        {"id": "well-plumb", "label": "Well Plumb Line", "space": "mirror_well"},
        {"id": "chart-press", "label": "Chart Press", "space": "chart_aisle"},
    ]
    it.npc_markers = [
        {"id": "lens-master", "label": "Lens Master", "space": "grinding_room"},
        {"id": "well-reader", "label": "Well Reader", "space": "mirror_well"},
    ]
    it.harvestables = [
        {"id": "lens-quartz-blank", "label": "Quartz Blank", "space": "grinding_room"},
        {"id": "annealing-rime", "label": "Annealing Rime", "space": "annealing_ice"},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.13, 0.16, 0.21], "energy": 0.34},
        "fog": {"enabled": True, "colour": [0.08, 0.10, 0.13],
                "begin": 14.0, "end": 52.0},
        "audio": [{"id": "lap-grind", "space": "grinding_room", "loop": True},
                  {"id": "drip", "space": "mirror_well", "loop": True}],
    }
    it.notes = [
        "One route in, from the orrery drum. The well is the deepest point at "
        "-7.2 m and the only dead end; everything else is a loop through the "
        "sighting floor.",
        "The pool in the mirror well is not a walk surface. Its coping is.",
        "The oculus is the only opening: the space list marks sighting_floor as "
        "open to sky so the loader does not light it as a sealed room.",
    ]
    return it


# --------------------------------------------------------- 2. Mirror Cistern

def mirror_cistern(seed: int = 20260902) -> Interior:
    """Under the fountain plaza: the waterworks behind the terrace basins.

    Glacier meltwater arrives loaded with rock flour, which is what makes the
    lake turquoise and what would make a reflecting basin useless. This is
    where it is dropped: a settling basin, filter racks, then a stilling floor
    wide and shallow enough to go glass-flat. The region's mirrors are made
    here as much as in the Lens Vault.
    """
    it = Interior("mirrorhold_cistern", "The Mirror Cistern", "works",
                  "plaza", [132.0, 58.0, -90.0], "cistern-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("sluice_hall", -11, -16, 11, 2, 0.0, 6.4, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=ASHLAR, ceiling="vault", vault_rise=2.4,
             doors=[("south", 0.0, 3.4, 2.9), ("east", -6.0, 3.0, 2.8),
                    ("west", -6.0, 3.0, 2.8), ("north", 0.0, 3.2, 2.8)])
    it.space("settling_basin", 17, -14, 37, 6, -3.0, 7.2, floor_mat=RUBBLE,
             wall_mat=ASHLAR, ceil_mat=ASHLAR, ceiling="vault", vault_rise=2.6,
             doors=[("west", -6.0, 3.0, 2.8)])
    it.space("stilling_floor", -38, -14, -17, 12, -1.6, 5.6, floor_mat=MARBLE,
             wall_mat=ASHLAR, ceil_mat=ASHLAR, ceiling="vault", vault_rise=2.2,
             doors=[("east", -6.0, 3.0, 2.8)])
    it.space("filter_racks", -9, 8, 9, 22, 0.0, 4.6, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("south", 0.0, 3.2, 2.8), ("east", 15.0, 2.8, 2.6)])
    it.space("pump_gallery", 15, 10, 31, 26, 0.0, 5.4, floor_mat=PAVING,
             wall_mat=ASHLAR, ceil_mat=ASHLAR,
             doors=[("west", 15.0, 2.8, 2.6)])

    _link(it, "basin_aisle", (11, -6), (17, -6), 3.0, 0.0, -3.0, 3.4, 6,
          PAVING, ASHLAR, ASHLAR, seed + 1)
    _link(it, "stilling_aisle", (-11, -6), (-17, -6), 3.0, 0.0, -1.6, 3.4, 4,
          PAVING, ASHLAR, ASHLAR, seed + 2)
    _link(it, "filter_link", (0, 2), (0, 8), 3.2, 0.0, 0.0, 3.4, 0,
          PAVING, ASHLAR, ASHLAR, seed + 3)
    _link(it, "pump_link", (9, 15), (15, 15), 2.8, 0.0, 0.0, 3.2, 0,
          PAVING, ASHLAR, ASHLAR, seed + 4)

    # -- sluice hall: the gates, and water coming in loud
    for i, x in enumerate((-6.0, 0.0, 6.0)):
        g.add(M.box((3.4, 0.6, 1.0), center=(x, 0.3, -14.4), uv_scale=0.5,
                    material=ASHLAR))
        # the gate itself, an iron plate on a screw
        g.add(M.box((2.8, 2.4, 0.22), center=(x, 1.5, -14.4), material=IRON))
        g.add(M.cylinder(0.1, 0.08, 2.2, segments=8, uv_scale=1.0,
                         material=BRASS).translate(x, 2.6, -14.4))
        g.add(M.lathe([[0.0, 0.0], [0.5, 0.08], [0.5, 0.16], [0.0, 0.24]], 10,
                      uv_scale=1.0, material=BRASS).translate(x, 4.8, -14.4))
        g.add(_still_water(x - 1.4, -14.2, x + 1.4, -9.0, 0.22, W_STREAM))
    # the channels running the water off toward the settling basin
    g.add(S.water_channel(16.0, 1.6, 0.5, seed + 11).translate(0.0, 0.0, -6.0)
          .rotate_y(math.pi * 0.5))
    g.add(_brass_rail(18.0).translate(0.0, 0.0, -3.4))

    # -- settling basin: still, milky, and deliberately ugly water
    g.add(_still_water(19.0, -12.0, 35.0, 4.0, -1.2, W_POOL))
    # the baffles that slow it, staggered so the flow has to turn
    for i in range(5):
        bx = 21.0 + i * 3.2
        offset = 3.0 if i % 2 else -3.0
        g.add(M.box((0.6, 3.0, 11.0), center=(bx, -1.5, -4.0 + offset),
                    uv_scale=0.5, material=ASHLAR))
    # the walk round the rim
    for side, z in (("s", -13.0), ("n", 5.0)):
        g.add(M.box((20.0, 0.4, 1.6), center=(27.0, -3.0, z), uv_scale=0.5,
                    material=PAVING))
    # a spoil barrow and the shovelled rock flour
    g.add(P.cart(seed + 12, 2.2, 1.2).translate(33.0, -3.0, -12.0))
    for _ in range(14):
        x = float(rng.uniform(30.0, 36.0))
        z = float(rng.uniform(-13.0, -9.0))
        g.add(M.icosphere(float(rng.uniform(0.2, 0.5)), subdivisions=1,
                          material=RUBBLE).translate(x, -2.9, z))

    # -- stilling floor: the mirror. Shallow, wide, and perfectly flat.
    g.add(_still_water(-36.0, -12.0, -19.0, 10.0, -1.1, MIRROR))
    # a walkway crossing it, on low piers, so it can be looked at from within
    g.add(M.box((17.0, 0.34, 2.2), center=(-27.5, -0.9, -1.0), uv_scale=0.5,
                material=MARBLE))
    for i in range(6):
        px = -35.0 + i * 3.2
        g.add(M.box((0.5, 0.9, 0.5), center=(px, -1.5, -1.0), material=ASHLAR))
    g.add(_brass_rail(16.0).translate(-27.5, -0.72, 0.1))
    g.add(_brass_rail(16.0).translate(-27.5, -0.72, -2.1))
    # columns standing in the water, which is the whole point of the room
    for i in range(6):
        cx = -34.0 + (i % 3) * 6.5
        cz = -8.0 + (i // 3) * 12.0
        g.add(S.column(4.4, 0.38, 12, MARBLE).translate(cx, -1.6, cz))
    for z in (-9.0, 7.0):
        g.add(L.crystal_lamp(2.4).translate(-37.0, -1.6, z))

    # -- filter racks: gravel and charcoal beds in timber frames
    for i in range(4):
        fz = 10.5 + i * 3.0
        g.add(M.box((14.0, 0.9, 2.2), center=(0.0, 0.45, fz), uv_scale=0.5,
                    material=ASHLAR))
        g.add(M.box((13.0, 0.3, 1.6), center=(0.0, 1.05, fz), uv_scale=0.6,
                    material=RUBBLE if i % 2 else PAVING))
        for dx in (-6.6, 6.6):
            g.add(M.box((0.3, 1.4, 2.4), center=(dx, 0.7, fz), material=TIMBER))
    g.add(P.barrel(0.4, 1.0, seed + 13).translate(7.0, 0.0, 20.0))
    g.add(P.crate(0.7, seed + 14, TIMBER).translate(-7.0, 0.0, 20.0))

    # -- pump gallery: brass machinery, a wheel, and the rising main
    px, pz = it.centre("pump_gallery")
    g.add(M.lathe([[2.6, 0.0], [2.6, 0.35], [2.2, 0.35], [2.2, 0.0]], 24,
                  uv_scale=0.8, material=BRASS).translate(px, 1.8, pz)
          .rotate_x(math.pi * 0.5))
    for i in range(8):
        angle = math.pi * 2.0 * i / 8
        g.add(M.box((0.14, 2.4, 0.14), center=(px, 1.8, pz), material=BRASS)
              .rotate_x(math.pi * 0.5).rotate_z(angle))
    g.add(M.cylinder(0.5, 0.5, 3.0, segments=12, uv_scale=0.8,
                     material=IRON).translate(px + 4.0, 0.0, pz))
    g.add(M.tube(np.array([[px + 4.0, 3.0, pz], [px + 4.0, 5.2, pz],
                           [px - 4.0, 5.2, pz]]), [0.26, 0.26, 0.26],
                 segments=8, cap_start=True, cap_end=True, material=BRASS))
    g.add(P.workbench(2.4, seed + 15).translate(px - 4.5, 0.0, pz + 5.0))

    it.lamps = [[0.0, 4.2, -8.0], [27.0, 2.6, -4.0], [-27.5, 2.4, -1.0],
                [0.0, 3.2, 15.0], [23.0, 3.6, 18.0]]
    lamp_group, _ = _hung_lamps([(0.0, 4.2, -8.0), (0.0, 3.2, 15.0),
                                 (23.0, 3.6, 18.0)], seed + 16)
    g.add(lamp_group)

    it.spawn_space = "sluice_hall"
    it.subjects = [
        ("concept-01", "sluice gates and the incoming main", "sluice_hall"),
        ("concept-02", "the vaulted sluice hall", "sluice_hall"),
        ("concept-03", "descent to the settling basin", "basin_aisle"),
        ("concept-04", "baffles dropping the rock flour", "settling_basin"),
        ("concept-05", "spoil barrow and shovelled flour", "settling_basin"),
        ("concept-06", "gravel and charcoal filter beds", "filter_racks"),
        ("concept-07", "the pump gallery and rising main", "pump_gallery"),
        ("concept-08", "the stilling floor walkway", "stilling_floor"),
        ("concept-09", "columns standing in the mirror", "stilling_floor"),
        ("concept-10", "ashlar marble brass water materials", "stilling_floor"),
    ]
    it.landmark("the-stilling-floor", "The Stilling Floor", "stilling_floor", 1.0)
    it.landmark("the-settling-basin", "The Settling Basin", "settling_basin", 1.0)
    it.landmark("the-sluice-gates", "The Sluice Gates", "sluice_hall", 1.4)
    it.interactives = [
        {"id": "sluice-wheel", "label": "Sluice Wheel", "space": "sluice_hall"},
        {"id": "filter-rack", "label": "Filter Rack", "space": "filter_racks"},
        {"id": "pump-drive", "label": "Pump Drive", "space": "pump_gallery"},
        {"id": "stilling-gauge", "label": "Stilling Gauge", "space": "stilling_floor"},
    ]
    it.npc_markers = [
        {"id": "cistern-reeve", "label": "Cistern Reeve", "space": "sluice_hall"},
        {"id": "flour-shoveller", "label": "Flour Shoveller", "space": "settling_basin"},
    ]
    it.harvestables = [
        {"id": "rock-flour", "label": "Glacier Rock Flour", "space": "settling_basin"},
        {"id": "filter-charcoal", "label": "Filter Charcoal", "space": "filter_racks"},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.14, 0.18, 0.22], "energy": 0.38},
        "fog": {"enabled": True, "colour": [0.09, 0.12, 0.14],
                "begin": 16.0, "end": 60.0},
        "audio": [{"id": "sluice-roar", "space": "sluice_hall", "loop": True},
                  {"id": "still-water", "space": "stilling_floor", "loop": True}],
    }
    it.notes = [
        "Water levels descend west to east through the works: sluice hall at "
        "0.0, stilling floor at -1.6, settling basin at -3.0. The two water "
        "surfaces are meshes, not walk surfaces.",
        "The stilling floor's walkway is the only way across it and is a walk "
        "surface; the water either side is not.",
    ]
    return it


# ---------------------------------------------------------- 3. Stair Cellars

def stair_cellars(seed: int = 20260903) -> Interior:
    """Behind the cliff town: cellars cut back into the rock.

    The lived-in one. Where the two monumental interiors are dressed stone and
    brass, this is rubble, ice cut from the glacier and stored in sawdust, and
    a stair down to a water gate the town would rather the citadel did not
    inventory.
    """
    it = Interior("mirrorhold_stair_cellars", "The Stair Cellars", "cellar",
                  "cliff-town", [-24.0, 17.0, -54.0], "stair-cellars-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("cellar_head", -6, -11, 6, -1, 0.0, 3.8, floor_mat=PAVING,
             wall_mat=RUBBLE, ceil_mat=ROCK,
             doors=[("south", 0.0, 2.8, 2.6), ("north", 0.0, 2.8, 2.6)])
    it.space("common_cellar", -10, 4, 10, 20, -1.4, 4.0, floor_mat=PAVING,
             wall_mat=RUBBLE, ceil_mat=ROCK, ceiling="vault", vault_rise=1.6,
             doors=[("south", 0.0, 2.8, 2.6), ("east", 12.0, 2.6, 2.5),
                    ("west", 12.0, 2.6, 2.5), ("north", -3.0, 2.6, 2.5)])
    it.space("cold_larder", 16, 6, 28, 18, -1.4, 3.4, floor_mat=RUBBLE,
             wall_mat=ICE, ceil_mat=ROCK,
             doors=[("west", 12.0, 2.6, 2.5)])
    it.space("rock_shrine", -26, 6, -14, 18, -1.0, 4.4, floor_mat=PAVING,
             wall_mat=ROCK, ceil_mat=ROCK,
             doors=[("east", 12.0, 2.6, 2.5)])
    it.space("water_gate", -9, 30, 3, 44, -8.4, 4.6, floor_mat=ROCK,
             wall_mat=ROCK, ceil_mat=ROCK,
             doors=[("south", -3.0, 2.6, 2.5)])

    _link(it, "head_stair", (0, -1), (0, 4), 2.8, 0.0, -1.4, 3.0, 5,
          PAVING, RUBBLE, ROCK, seed + 1)
    _link(it, "larder_aisle", (10, 12), (16, 12), 2.6, -1.4, -1.4, 3.0, 0,
          PAVING, RUBBLE, ROCK, seed + 2)
    _link(it, "shrine_aisle", (-10, 12), (-14, 12), 2.6, -1.4, -1.0, 3.0, 0,
          PAVING, ROCK, ROCK, seed + 3)
    _link(it, "smugglers_stair", (-3, 20), (-3, 30), 2.6, -1.4, -8.4, 3.2, 20,
          ROCK, ROCK, ROCK, seed + 4)

    # -- cellar head: a trap door above, brooms, a lantern hook
    g.add(M.box((2.4, 0.14, 2.4), center=(0.0, 3.72, -6.0), uv_scale=0.6,
                material=TIMBER))
    g.add(M.box((0.16, 0.1, 2.2), center=(-1.0, 3.62, -6.0), material=IRON))
    g.add(P.crate(0.6, seed + 11, TIMBER).translate(-4.2, 0.0, -3.0))
    g.add(P.barrel(0.34, 0.84, seed + 12).translate(4.0, 0.0, -3.4))

    # -- common cellar: barrels, a long table, the town's stores
    for i in range(9):
        bx = -8.0 + (i % 3) * 1.3
        bz = 6.0 + (i // 3) * 1.4
        g.add(P.barrel(0.36, 0.9, seed + 20 + i).translate(bx, -1.4, bz))
    g.add(M.box((5.6, 0.14, 1.5), center=(0.0, -0.62, 12.0), uv_scale=0.6,
                material=TIMBER_WARM))
    for dx in (-2.4, 2.4):
        for dz in (-0.55, 0.55):
            g.add(M.box((0.16, 0.7, 0.16), center=(dx, -1.05, 12.0 + dz),
                        material=TIMBER))
    for i in range(4):
        g.add(P.crate(0.62, seed + 30 + i, TIMBER)
              .translate(float(rng.uniform(4.0, 8.0)), -1.4,
                         float(rng.uniform(14.0, 18.0))))
    g.add(P.brazier(seed + 13).translate(0.0, -1.4, 17.0))

    # -- cold larder: glacier ice in sawdust, hung stores
    for i in range(6):
        ix = 18.0 + (i % 3) * 3.2
        iz = 8.5 + (i // 3) * 5.0
        g.add(M.box((2.6, 1.1, 2.6), center=(ix, -0.85, iz), uv_scale=0.5,
                    material=ICE))
        g.add(M.box((3.0, 0.25, 3.0), center=(ix, -1.28, iz), uv_scale=0.5,
                    material=TIMBER))
    g.add(M.tube(np.array([[17.0, 1.6, 15.5], [27.0, 1.6, 15.5]]), [0.08, 0.08],
                 segments=6, cap_start=True, cap_end=True, material=IRON))
    for i in range(5):
        hx = 18.0 + i * 2.0
        g.add(M.box((0.05, 0.7, 0.05), center=(hx, 1.2, 15.5), material=IRON))
        g.add(M.box((0.5, 0.5, 0.34), center=(hx, 0.7, 15.5), uv_scale=0.8,
                    material=CLOTH))

    # -- rock shrine: a niche cut in the rock with a crystal panel
    sx, sz = it.centre("rock_shrine")
    g.add(M.box((3.4, 2.8, 0.8), center=(sx - 4.6, 0.4, sz), uv_scale=0.5,
                material=RUBBLE))
    panel = L.crystal_panel(1.1, 2.0, 0.2)
    for part in panel.parts:
        g.add(part.translate(sx - 4.2, 0.6, sz))
    g.add(M.box((2.0, 0.5, 1.0), center=(sx - 3.0, -0.75, sz), uv_scale=0.6,
                material=MARBLE))
    for dz in (-1.2, 1.2):
        g.add(P.brazier(seed + 14).translate(sx - 3.0, -1.0, sz + dz))
    # offerings: small mirrors leaned against the plinth
    for i in range(5):
        g.add(M.box((0.28, 0.36, 0.05),
                    center=(sx - 3.0 + (i - 2) * 0.4, -0.42, sz + 0.6),
                    material=MIRROR).rotate_x(-0.2))

    # -- water gate: the stair reaches lake level and a barred opening
    gx, gz = it.centre("water_gate")
    g.add(_still_water(-8.0, 36.0, 2.0, 43.0, -8.0, "water_lake"))
    g.add(M.box((11.0, 0.4, 1.4), center=(-3.0, -8.4, 32.0), uv_scale=0.5,
                material=ROCK))
    for i in range(7):
        bx = -7.5 + i * 1.5
        g.add(M.box((0.14, 3.2, 0.14), center=(bx, -6.8, 43.6), material=IRON))
    g.add(M.box((11.0, 0.3, 0.3), center=(-3.0, -5.2, 43.6), material=IRON))
    g.add(P.rowing_boat(3.6, 1.2, seed + 15).translate(-3.0, -7.9, 39.0))
    g.add(L.crystal_lamp(2.0).translate(-8.2, -8.4, 33.0))

    it.lamps = [[0.0, 2.6, -6.0], [0.0, 2.0, 12.0], [22.0, 1.6, 12.0],
                [-20.0, 2.2, 12.0], [-3.0, -6.0, 34.0]]
    lamp_group, _ = _hung_lamps([(0.0, 2.0, 12.0), (22.0, 1.6, 12.0)], seed + 16)
    g.add(lamp_group)

    it.spawn_space = "cellar_head"
    it.subjects = [
        ("concept-01", "cellar head under the trap door", "cellar_head"),
        ("concept-02", "stair into the common cellar", "head_stair"),
        ("concept-03", "the town's stores and long table", "common_cellar"),
        ("concept-04", "glacier ice bedded in sawdust", "cold_larder"),
        ("concept-05", "hung stores on the iron rail", "cold_larder"),
        ("concept-06", "the niche shrine cut in rock", "rock_shrine"),
        ("concept-07", "mirror offerings at the plinth", "rock_shrine"),
        ("concept-08", "the long stair down to the water", "smugglers_stair"),
        ("concept-09", "the barred water gate and its boat", "water_gate"),
        ("concept-10", "rubble ice timber iron materials", "common_cellar"),
    ]
    it.landmark("the-water-gate", "The Water Gate", "water_gate", 1.2)
    it.landmark("the-rock-shrine", "The Rock Shrine", "rock_shrine", 1.2)
    it.landmark("cold-larder", "The Cold Larder", "cold_larder", 1.0)
    it.interactives = [
        {"id": "cellar-hatch", "label": "Cellar Hatch", "space": "cellar_head"},
        {"id": "store-table", "label": "Store Table", "space": "common_cellar"},
        {"id": "shrine-niche", "label": "Shrine Niche", "space": "rock_shrine"},
        {"id": "water-gate-bars", "label": "Water Gate Bars", "space": "water_gate"},
    ]
    it.npc_markers = [
        {"id": "cellar-keeper", "label": "Cellar Keeper", "space": "common_cellar"},
        {"id": "ice-cutter", "label": "Ice Cutter", "space": "cold_larder"},
    ]
    it.harvestables = [
        {"id": "stored-glacier-ice", "label": "Stored Glacier Ice", "space": "cold_larder"},
        {"id": "cellar-moss", "label": "Cellar Moss", "space": "water_gate"},
    ]
    it.environment = {
        "sky": "none",
        "ambient": {"colour": [0.12, 0.12, 0.14], "energy": 0.30},
        "fog": {"enabled": True, "colour": [0.07, 0.07, 0.09],
                "begin": 10.0, "end": 40.0},
        "audio": [{"id": "lap", "space": "water_gate", "loop": True},
                  {"id": "settle", "space": "common_cellar", "loop": True}],
    }
    it.notes = [
        "A branch, not a loop: the common cellar is the hub and the larder, "
        "shrine and water stair are dead ends off it.",
        "The water gate is at -8.4 m, roughly lake level relative to the cliff "
        "town's terrace. Its water is a mesh, not a walk surface.",
    ]
    return it


ALL = {
    "lens_vault": lens_vault,
    "cistern": mirror_cistern,
    "stair_cellars": stair_cellars,
}


# ------------------------------------------------- one map, three interiors

# Eternal Lands puts many insides on a single map, separated by dead space you
# cannot reach. That is the model here: one package, one collision grid, three
# self-contained blocks of rooms, and nothing between them. The gaps are not
# corridors - there is no geometry there at all, so the grid reads 0 and the
# black is genuinely black.
BLOCK_GAP = 34.0
MARGIN = 12.0
TILE_METRES = 6.0   # one ELM tile at the interior collision scale


def _offset_interior(source: Interior, dx: float, dz: float, prefix: str,
                     target: Interior) -> dict:
    """Copy one authored interior into `target`, shifted, with keys prefixed."""
    for part in source.group.parts:
        target.group.add(part.translate(dx, 0.0, dz))
    for part in source.group.walk_parts:
        target.group.add_walk(part.translate(dx, 0.0, dz))
    # Lids travel too. This walks the buckets rather than adding the group, so
    # a bucket left out here is silently dropped from the combined map.
    for part in source.group.overhead_parts:
        target.group.add_overhead(part.translate(dx, 0.0, dz))

    def key(name: str) -> str:
        return f"{prefix}_{name}"

    for name, s in source.spaces.items():
        target.spaces[key(name)] = {
            "x0": s["x0"] + dx, "x1": s["x1"] + dx,
            "z0": s["z0"] + dz, "z1": s["z1"] + dz,
            "floor": s["floor"], "height": s["height"],
        }
    for name, p in source.passages.items():
        target.passages[key(name)] = {
            "a": (p["a"][0] + dx, p["a"][1] + dz),
            "b": (p["b"][0] + dx, p["b"][1] + dz),
            "y0": p["y0"], "y1": p["y1"],
            "width": p["width"], "height": p["height"],
        }
    for name in source.open_to_sky:
        target.open_to_sky.append(key(name))

    def shift(entry: dict) -> dict:
        out = dict(entry)
        if "position" in out and len(out["position"]) == 3:
            x, y, z = out["position"]
            out["position"] = [round(x + dx, 2), round(y, 2), round(z + dz, 2)]
        if "space" in out and out["space"] in source.spaces:
            out["space"] = key(out["space"])
        return out

    for entry in source.landmarks:
        target.landmarks.append(shift(entry))
    for bucket, dest in ((source.interactives, target.interactives),
                         (source.harvestables, target.harvestables),
                         (source.npc_markers, target.npc_markers)):
        for entry in bucket:
            dest.append(shift(entry))
    for lamp in source.lamps:
        target.lamps.append([round(lamp[0] + dx, 2), round(lamp[1], 2),
                             round(lamp[2] + dz, 2)])
    for ident, label, space in source.subjects:
        target.subjects.append((f"{prefix}-{ident}", label, key(space)))

    spawn_space = source.spawn_space or source.subjects[0][2]
    s = target.spaces[key(spawn_space)]
    return {
        "id": prefix.replace("_", "-"),
        "name": source.name,
        "space": key(spawn_space),
        "portal": source.destination_spawn,
        "anchor_landmark": source.anchor_landmark,
        "position": [round((s["x0"] + s["x1"]) * 0.5, 2),
                     round(s["floor"] + 0.05, 2),
                     round((s["z0"] + s["z1"]) * 0.5, 2)],
    }


def mirrorhold_interiors(seed: int = 20260904) -> Interior:
    """All three of Mirrorhold's interiors on one square map.

    Laid out on a grid rather than in a row. Two constraints force this: the
    server's ELM validator requires width == height, so a long strip could
    never be served; and a map is a whole number of ELM tiles, six metres each
    at this scale. So the blocks are placed in a 2x2 arrangement with dead
    ground between and around them, and the map is squared up to the next tile
    boundary. The fourth quarter is left empty, which is where a later interior
    goes without moving anything already authored.
    """
    parts = [("lens_vault", lens_vault(seed)),
             ("cistern", mirror_cistern(seed + 1)),
             ("cellars", stair_cellars(seed + 2))]

    combined = Interior("mirrorhold_interiors", "Mirrorhold Interiors",
                        "multi", "citadel", [162.0, 124.0, -267.0],
                        "lens-vault-stair")
    combined.blocks = []

    sizes = []
    for _, source in parts:
        lo, hi = source.group.bounds()
        sizes.append((lo, hi, float(hi[0] - lo[0]), float(hi[2] - lo[2])))

    col_w = [max(sizes[0][2], sizes[2][2]), sizes[1][2]]
    row_d = [max(sizes[0][3], sizes[1][3]), sizes[2][3]]
    span_x = MARGIN * 2 + col_w[0] + BLOCK_GAP + col_w[1]
    span_z = MARGIN * 2 + row_d[0] + BLOCK_GAP + row_d[1]

    # Square, and a whole number of six-metre ELM tiles.
    side = max(span_x, span_z)
    tiles = int(math.ceil(side / TILE_METRES))
    side = tiles * TILE_METRES

    # cell origins for the 2x2 arrangement: A top-left, B top-right,
    # C bottom-left, fourth quarter reserved.
    cell_origin = [
        (MARGIN, MARGIN),
        (MARGIN + col_w[0] + BLOCK_GAP, MARGIN),
        (MARGIN, MARGIN + row_d[0] + BLOCK_GAP),
    ]

    for (prefix, source), (lo, hi, _w, _d), (ox, oz) in zip(parts, sizes,
                                                            cell_origin):
        dx = ox - float(lo[0])
        dz = oz - float(lo[2])
        combined.blocks.append(_offset_interior(source, dx, dz, prefix, combined))

    combined.map_metres = side
    combined.map_tiles = tiles
    combined.spawn_space = combined.blocks[0]["space"]
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.13, 0.16, 0.21], "energy": 0.34},
        "fog": {"enabled": True, "colour": [0.08, 0.10, 0.13],
                "begin": 14.0, "end": 52.0},
        "audio": [entry for _, s in parts
                  for entry in s.environment.get("audio", [])],
    }
    combined.notes = [
        "Three interiors on one map, in the Eternal Lands manner: separate "
        f"blocks on a {side:.0f} m square ({tiles} ELM tiles) with "
        f"{BLOCK_GAP:.0f} m of dead ground between them and nothing joining "
        "them in-map.",
        "Square because the server's ELM validator requires width == height, "
        "and a whole number of tiles because a map is measured in them. A row "
        "of blocks would have been neither.",
        "The gaps carry no geometry, so the collision grid reads 0 there: the "
        "space between blocks is unreachable rather than merely unlit.",
        "Each block keeps the coordinates it was authored in; only its origin "
        "moves. Space keys are prefixed with the block name.",
        "The fourth quarter is deliberately empty, so a later interior can be "
        "added without moving any block already placed.",
    ]
    for _, source in parts:
        combined.notes.extend(source.notes)
    return combined


ALL = {"interiors": mirrorhold_interiors}
