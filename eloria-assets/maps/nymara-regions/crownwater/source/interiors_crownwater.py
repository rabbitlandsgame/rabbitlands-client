"""Crownwater's interiors, built from the same kit as the city above them.

Four spaces reached from named landmarks on the 576 m map:

    The Drowned Crown        under The Crown Basilica    dungeon
    The Tide Campanile       inside the bell tower       tower
    The Tide Cistern         under the garden islet      utility
    The Harbour Customs Hall on the arrival islet        settlement

They share the region's material table, its `MeshGroup` walk-surface contract
and its modelling primitives, so a doorway, a stair tread and a column are the
same construction indoors as out.

WHY THESE FOUR
--------------
Crownwater is a city on water, so its insides are about water: what lies under
it, what holds it back, and what floats on it. Each interior takes a different
answer, so that no two feel like the same room with different textures:

* **The Drowned Crown** is the water winning. An older palace the basilica was
  built on top of, now half-flooded - the region's only concept-complete
  interior, and the only one whose subjects were given rather than invented.
* **The Tide Campanile** is the one dry, bright, vertical space in the set. A
  hollow tower with a switchback stair, a ringing floor and an open belfry.
  Deliberately the opposite of the Drowned Crown in every axis.
* **The Tide Cistern** is water held still and put to use: a forest of columns
  standing in a hand's depth of fresh water, lit by oculi from the garden
  overhead. Symmetric and repetitive where the Drowned Crown is broken.
* **The Harbour Customs Hall** is the only one with a job. Timber and plaster
  over stone, crates and ledgers and a water gate where a boat comes in under
  the building. Mundane on purpose - three monuments in a row is a museum.

WHY THIS IS NOT IN `_toolkit/`
------------------------------
Amberwood's interiors live in `_toolkit/amberwood/interiors.py`, which makes the
shared toolkit carry one region's content. Crownwater keeps its own where its
region plan is, for the same reason `region.py` and `populate.py` live here: the
toolkit's shell parts (`chamber`, `passage`, `_barrel_vault`) are genuinely
shared and are imported unchanged; the rooms are not.

TWO RULES THAT ARE LOAD-BEARING
-------------------------------
Inherited from the toolkit's own hard-won notes, and both re-learned here:

* A walkable surface must be registered with `add_walk`. A floor added with
  `add` is scenery the player falls through.
* A descending passage's ceiling must follow its floor, or the passage stands
  proud of the room it opens into and leaks to the void.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood.interiors import Interior, chamber, hanging_lamps, passage

import crownarch as CA
import crownkit as CK

# -- materials -------------------------------------------------------------
MARBLE = CK.MARBLE
MOSAIC = CK.MOSAIC
GILT = CK.GILT
VERDIGRIS = CK.VERDIGRIS
SAND = CK.SAND
STONE = "ashlar"
RUBBLE = "rubble_stone"
PLASTER = "lime_plaster"
PAVING = "cobble_paving"
TIMBER = "timber_warm"
TIMBER_DARK = "timber_dark"
CARVED = "carved_wood"
IRON = "dark_iron"
WATER = "water_deep"
CANVAS = "canvas_awning"

INTERIOR_MATERIALS = frozenset({
    MARBLE, MOSAIC, GILT, VERDIGRIS, SAND,
    STONE, RUBBLE, PLASTER, PAVING, TIMBER, TIMBER_DARK, CARVED, IRON, WATER,
    CANVAS, "foliage_green",
})


# -- shared helpers --------------------------------------------------------
def _sheet(x0, z0, x1, z1, y, material=WATER):
    """A still water surface. Not a walk surface: you wade, you do not stand."""
    return M.box((abs(x1 - x0), 0.06, abs(z1 - z0)),
                 center=((x0 + x1) * 0.5, y, (z0 + z1) * 0.5),
                 uv_scale=0.25, material=material)


def _column_grid(x0, z0, x1, z1, spacing, height, floor_y, *, radius=0.42,
                 material=MARBLE, jitter=0.0, seed=0):
    """A regular forest of columns, returned as one merged mesh.

    Merged rather than added one at a time because a cistern is a hundred of
    them and each `add` is a separate part in the export.
    """
    rng = np.random.default_rng(seed)
    parts = []
    x = x0
    while x <= x1 + 1e-6:
        z = z0
        while z <= z1 + 1e-6:
            dx = float(rng.uniform(-jitter, jitter)) if jitter else 0.0
            dz = float(rng.uniform(-jitter, jitter)) if jitter else 0.0
            parts.append(S.column(height, radius=radius, material=material)
                         .translate(x + dx, floor_y, z + dz))
            z += spacing
        x += spacing
    return M.merge(parts, material)


def _stair_flight(x, z, axis, length, y0, y1, width, steps, material=MARBLE):
    """A straight flight of treads, walkable, climbing along one axis.

    Returned as a MeshGroup whose treads are all `add_walk`, so a tower stair is
    a walk surface without the whole tower becoming one.
    """
    out = S.MeshGroup()
    rise = (y1 - y0) / steps
    run = length / steps
    for i in range(steps):
        y = y0 + rise * (i + 1)
        offset = run * (i + 0.5)
        if axis == "x":
            out.add_walk(M.box((run, 0.30, width), center=(x + offset, y - 0.15, z),
                               uv_scale=0.5, material=material))
        else:
            out.add_walk(M.box((width, 0.30, run), center=(x, y - 0.15, z + offset),
                               uv_scale=0.5, material=material))
    return out


def _landing(x0, z0, x1, z1, y, material=MARBLE):
    out = S.MeshGroup()
    out.add_walk(M.box((abs(x1 - x0), 0.30, abs(z1 - z0)),
                       center=((x0 + x1) * 0.5, y - 0.15, (z0 + z1) * 0.5),
                       uv_scale=0.5, material=material))
    return out


def _link(it, ident, a, b, width, y0, y1, height, steps, *,
          floor_mat=MARBLE, wall_mat=MARBLE, ceil_mat=MARBLE, seed=0):
    """Add a passage and record it, the way the toolkit's examples do."""
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


# ==================================================== 1. The Drowned Crown
def drowned_crown(seed: int = 20260901) -> Interior:
    """The older palace beneath The Crown Basilica, half taken by the lagoon.

    The only Crownwater interior whose programme was given rather than invented:
    `interiors/drowned_crown/concept.json` lists flooded vestibule, water
    galleries, submerged arch, shell altar, statue court, water channel,
    collapsed dome, air pocket and objective hall. Every one is a space here.

    The through-line is that the water is not an obstacle laid over a dungeon -
    it is the reason the place is a dungeon. Floors step down as you go in, the
    water line stays flat, and so the wading gets deeper until the collapsed
    dome lets the light and the air back in.
    """
    it = Interior("drowned_crown", "The Drowned Crown", "dungeon",
                  "crownwater-cathedral", [114.0, 18.09, -132.0],
                  "basilica-undercroft")
    rng = np.random.default_rng(seed)
    g = it.group

    # The lagoon's level, held constant through the whole plan. Rooms sink
    # below it; the water does not rise to meet them.
    flood = -6.05

    it.space("stairhead", -6, -6, 6, 6, 0.0, 5.0, floor_mat=MOSAIC,
             wall_mat=MARBLE, ceil_mat=MARBLE, ceiling="vault", vault_rise=2.0,
             doors=[("north", 0.0, 4.4, 3.0)])
    it.space("flooded_vestibule", -10, 18, 10, 36, -6.5, 6.0, floor_mat=SAND,
             wall_mat=MARBLE, ceil_mat=MARBLE, ceiling="vault", vault_rise=2.8,
             doors=[("south", 0.0, 4.4, 3.0), ("east", 27.0, 4.2, 3.0)])
    it.space("water_gallery", 24, 16, 46, 40, -7.2, 7.0, floor_mat=SAND,
             wall_mat=MARBLE, ceil_mat=MARBLE,
             doors=[("west", 27.0, 4.2, 3.0), ("north", 35.0, 4.6, 3.4)])
    it.space("statue_court", 22, 54, 50, 78, -7.2, 8.5, floor_mat=SAND,
             wall_mat=MARBLE, ceil_mat=MARBLE, ceiling="vault", vault_rise=3.4,
             doors=[("south", 35.0, 4.6, 3.4), ("west", 66.0, 4.0, 3.0),
                    ("north", 36.0, 4.8, 3.4)])
    it.space("shell_altar", -12, 56, 6, 76, -8.0, 6.5, floor_mat=SAND,
             wall_mat=RUBBLE, ceil_mat=MARBLE,
             doors=[("east", 66.0, 4.0, 3.0), ("west", 66.0, 4.6, 3.2)])
    it.space("collapsed_dome", -40, 54, -18, 78, -8.0, 13.0, floor_mat=RUBBLE,
             wall_mat=RUBBLE, ceil_mat=MARBLE, ceiling="open",
             doors=[("east", 66.0, 4.6, 3.2), ("south", -29.0, 4.0, 3.0)])
    it.space("air_pocket", -35, 30, -23, 44, -5.2, 4.4, floor_mat=MARBLE,
             wall_mat=MARBLE, ceil_mat=MARBLE, ceiling="vault", vault_rise=1.6,
             doors=[("north", -29.0, 4.0, 3.0)])
    it.space("crown_hall", 20, 92, 52, 118, -7.8, 10.0, floor_mat=MOSAIC,
             wall_mat=MARBLE, ceil_mat=MARBLE, ceiling="vault", vault_rise=4.2,
             doors=[("south", 36.0, 4.8, 3.4)])

    for ident, a, b, width, y0, y1, height, steps, mats in (
            ("descent", (0, 6), (0, 18), 4.4, 0.0, -6.5, 4.4, 20, (MOSAIC, MARBLE)),
            ("gallery_run", (10, 27), (24, 27), 4.2, -6.5, -7.2, 4.2, 3, (SAND, MARBLE)),
            ("submerged_arch", (35, 40), (35, 54), 4.6, -7.2, -7.2, 4.6, 0, (SAND, MARBLE)),
            ("altar_run", (22, 66), (6, 66), 4.0, -7.2, -8.0, 4.0, 4, (SAND, MARBLE)),
            ("dome_run", (-12, 66), (-18, 66), 4.6, -8.0, -8.0, 4.4, 0, (RUBBLE, RUBBLE)),
            ("air_stair", (-29, 54), (-29, 44), 4.0, -8.0, -5.2, 4.0, 12, (MARBLE, MARBLE)),
            ("hall_run", (36, 78), (36, 92), 4.8, -7.2, -7.8, 5.0, 3, (MOSAIC, MARBLE))):
        _link(it, ident, a, b, width, y0, y1, height, steps,
              floor_mat=mats[0], wall_mat=mats[1], ceil_mat=mats[1],
              seed=seed + len(ident))

    # -- stairhead: the basilica's own undercroft, still dry and still dressed
    cx, cz = it.centre("stairhead")
    g.add(CA.finial(1.1).translate(cx, 3.4, cz))
    for dx in (-4.2, 4.2):
        g.add(S.column(4.6, radius=0.34, material=MARBLE).translate(dx, 0.0, -3.6))
    g.add(P.barrel(seed=seed + 1).translate(-3.8, 0.0, 3.6))

    # -- flooded vestibule: the water line arrives, ankle deep over old mosaic
    cx, cz = it.centre("flooded_vestibule")
    g.add(_sheet(-10, 18, 10, 36, flood))
    g.add(CA.compass_inlay(5.4).translate(cx, -6.45, cz)
          if hasattr(CA, "compass_inlay") else
          M.lathe([[0.0, 0.0], [5.4, 0.0]], 32, uv_scale=0.3, material=MOSAIC)
          .translate(cx, -6.45, cz))
    for dz in (-6.0, 6.0):
        for dx in (-6.4, 6.4):
            g.add(S.column(6.0, radius=0.40, material=MARBLE)
                  .translate(cx + dx, -6.5, cz + dz))

    # -- water gallery: a colonnade standing in its own reflection
    cx, cz = it.centre("water_gallery")
    g.add(_sheet(24, 16, 46, 40, flood))
    g.add(_column_grid(28.0, 20.0, 42.0, 36.0, 4.6, 7.0, -7.2,
                       radius=0.44, material=MARBLE, seed=seed + 5))
    for i in range(4):
        g.add(P.crate(seed=seed + 10 + i).translate(
            float(rng.uniform(26, 44)), flood - 0.1, float(rng.uniform(18, 38))))

    # -- submerged arch: the passage the concept names, half under water
    g.add(M.arch(span=4.6, rise=2.2, thickness=0.7, depth=1.4, material=MARBLE)
          .transformed(M.rotation_y(math.pi * 0.5) @ M.translation(0.0, 0.0, 0.0))
          .translate(35.0, -7.2, 47.0))
    g.add(_sheet(32.5, 40, 37.5, 54, flood))

    # -- statue court: the drowned court of an older dynasty
    cx, cz = it.centre("statue_court")
    g.add(_sheet(22, 54, 50, 78, flood))
    for i in range(8):
        angle = 2.0 * math.pi * i / 8
        sx = cx + math.cos(angle) * 9.5
        sz = cz + math.sin(angle) * 8.5
        g.add(S.statue(height=3.0, seed=seed + 20 + i, plinth_height=1.5)
              .translate(sx, -7.2, sz))
    g.add(S.fountain(radius=2.8, seed=seed + 31).translate(cx, -7.2, cz))

    # -- shell altar: limestone gone to shell and brass, per the concept
    cx, cz = it.centre("shell_altar")
    g.add(_sheet(-12, 56, 6, 76, flood))
    g.add(M.lathe([[3.2, 0.0], [3.0, 0.5], [2.2, 0.9], [2.4, 1.15], [1.4, 1.35]],
                  24, uv_scale=0.6, material=RUBBLE).translate(cx, -8.0, cz))
    g.add(M.lathe([[1.5, 0.0], [1.2, 0.35], [0.5, 0.6], [0.0, 0.75]], 20,
                  uv_scale=0.9, material=GILT).translate(cx, -6.65, cz))
    for i in range(14):
        angle = 2.0 * math.pi * i / 14
        g.add(P.boulder(radius=float(rng.uniform(0.22, 0.5)),
                        seed=seed + 40 + i, material=RUBBLE)
              .translate(cx + math.cos(angle) * 5.4, -8.0,
                         cz + math.sin(angle) * 6.0))

    # -- collapsed dome: the roof is gone, and with it the dark
    cx, cz = it.centre("collapsed_dome")
    g.add(_sheet(-40, 54, -18, 78, flood))
    for i in range(9):
        g.add(P.boulder(radius=float(rng.uniform(0.7, 1.9)), seed=seed + 60 + i,
                        material=RUBBLE)
              .translate(cx + float(rng.uniform(-8, 8)), -8.0,
                         cz + float(rng.uniform(-9, 9))))
    # the dome's own ribs, fallen in and leaning on the rubble
    for i in range(5):
        angle = math.pi * (0.15 + 0.18 * i)
        g.add(M.box((0.7, 0.5, 9.0),
                    center=(cx + math.cos(angle) * 6.0, -6.6,
                            cz + math.sin(angle) * 5.0),
                    uv_scale=0.5, material=MARBLE)
              .transformed(M.rotation_y(angle)))
    g.add(_column_grid(cx - 8.0, cz - 8.0, cx + 8.0, cz + 8.0, 8.0, 5.0, -8.0,
                       radius=0.5, material=RUBBLE, seed=seed + 71))

    # -- air pocket: above the water line, and the only dry floor down here
    cx, cz = it.centre("air_pocket")
    g.add(P.brazier(seed=seed + 80).translate(cx - 3.0, -5.2, cz))
    g.add(P.bedroll(seed=seed + 81).translate(cx + 2.4, -5.2, cz + 2.0)
          if hasattr(P, "bedroll") else
          M.box((1.9, 0.25, 0.8), center=(cx + 2.4, -5.05, cz + 2.0),
                uv_scale=1.0, material=CANVAS))
    for i in range(3):
        g.add(P.crate(seed=seed + 85 + i).translate(cx + 3.6, -5.2, cz - 2.0 + i * 1.1))

    # -- crown hall: the objective, and the throne the lagoon took
    cx, cz = it.centre("crown_hall")
    g.add(_sheet(20, 92, 52, 118, flood))
    g.add(_column_grid(25.0, 97.0, 47.0, 113.0, 5.5, 10.0, -7.8,
                       radius=0.52, material=MARBLE, seed=seed + 90))
    dais = M.box((9.0, 1.2, 7.0), center=(cx, -7.2, cz + 7.5), uv_scale=0.4,
                 material=MARBLE)
    g.add(dais)
    g.add_walk(M.box((9.0, 0.25, 7.0), center=(cx, -6.5, cz + 7.5), uv_scale=0.4,
                     material=MOSAIC))
    g.add(M.box((2.4, 2.8, 1.6), center=(cx, -5.4, cz + 8.6), uv_scale=0.6,
                material=MARBLE))
    g.add(CA.finial(2.2).translate(cx, -4.0, cz + 8.6))
    for dx in (-3.6, 3.6):
        g.add(CA.dome(1.5, 1.6, segments=16, material=VERDIGRIS)
              .translate(cx + dx, -5.0, cz + 8.6))

    lamps, placed = hanging_lamps(
        [(0.0, 3.6, 0.0), (0.0, -3.0, 27.0), (35.0, -3.6, 28.0),
         (36.0, -3.6, 66.0), (-3.0, -4.4, 66.0), (-29.0, -1.8, 37.0),
         (36.0, -4.0, 105.0)], seed=seed + 99)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "stairhead"
    it.landmark("drowned-crown-throne", "The Drowned Throne", "crown_hall", 1.6)
    it.landmark("drowned-crown-altar", "The Shell Altar", "shell_altar", 1.4)
    it.landmark("drowned-crown-oculus", "The Fallen Dome", "collapsed_dome", 2.0)
    it.interactives.append({
        "id": "drowned-crown-shell-altar", "name": "Shell Altar", "type": "altar",
        "position": [round(it.centre("shell_altar")[0], 2), -6.6,
                     round(it.centre("shell_altar")[1], 2)], "authority": "server"})
    it.interactives.append({
        "id": "drowned-crown-sluice", "name": "Palace Sluice", "type": "mechanism",
        "position": [35.0, -6.4, 47.0], "authority": "server"})
    it.subjects = [
        ("flooded vestibule", "flooded_vestibule", "ankle-deep over old mosaic"),
        ("water galleries", "water_gallery", "colonnade standing in its reflection"),
        ("submerged arch", "submerged_arch", "the crossing, half under water"),
        ("shell altar", "shell_altar", "limestone gone to shell and brass"),
        ("statue court", "statue_court", "eight drowned figures round a fountain"),
        ("water channel", "gallery_run", "the run the water follows down"),
        ("collapsed dome", "collapsed_dome", "roof gone, and with it the dark"),
        ("air pocket", "air_pocket", "the only dry floor below the water line"),
        ("objective hall", "crown_hall", "the throne the lagoon took"),
        ("limestone shell brass", "shell_altar", "the material study"),
    ]
    it.notes.append("Water level is held at y = -6.05 throughout; rooms step "
                    "down beneath it rather than the water rising to meet them.")
    it.environment = {
        "sky": {"type": "gradient", "zenith": [0.06, 0.14, 0.20],
                "horizon": [0.12, 0.24, 0.28]},
        "sun": {"enabled": True, "direction": [-0.12, -0.94, 0.32],
                "color": [0.72, 0.86, 0.92], "energy": 0.95},
        "ambient": {"color": [0.28, 0.42, 0.48], "energy": 0.92,
                    "skyContribution": 0.35},
        "fog": {"enabled": True, "color": [0.16, 0.28, 0.32], "density": 0.012},
    }
    return it


# =================================================== 2. The Tide Campanile
def tide_campanile(seed: int = 20260902) -> Interior:
    """Inside Crownwater's bell tower: a hollow shaft with a switchback stair.

    Built as ONE tall space rather than stacked rooms. A tower modelled as
    chambers on top of each other gives every floor a ceiling slab and the next
    floor's slab immediately above it, and the stair then has to pierce both;
    one shaft with landings and flights added as walk geometry inside it is both
    cheaper and closer to what a campanile actually is.

    The counterweight to the Drowned Crown: dry, bright, and climbing.
    """
    it = Interior("crownwater_tide_campanile", "The Tide Campanile", "tower",
                  "crownwater-campanile", [162.0, 17.59, -150.0],
                  "campanile-door")
    g = it.group
    half = 5.0
    top = 26.0

    it.space("shaft", -half, -half, half, half, 0.0, top, floor_mat=MOSAIC,
             wall_mat=MARBLE, ceil_mat=MARBLE,
             doors=[("south", 0.0, 3.0, 3.0)])

    # Switchback stair: eight flights of 3.25 m rise around the shaft wall,
    # with a landing at each turn. Treads and landings are the walk surface;
    # the shaft itself is not.
    width = 1.9
    inner = half - width - 0.15
    rise = top / 8.0
    flights = [
        ("x", -inner, -inner, +1), ("z", +inner, -inner, +1),
        ("x", +inner, +inner, -1), ("z", -inner, +inner, -1),
    ]
    y = 0.0
    for turn in range(8):
        axis, a, b, direction = flights[turn % 4]
        length = inner * 2.0
        if axis == "x":
            x0 = a if direction > 0 else a - length
            g.add(_stair_flight(x0, b, "x", length, y, y + rise, width, 13))
            g.add(_landing(x0 + (length if direction > 0 else 0) - width * 0.5,
                           b - width * 0.5,
                           x0 + (length if direction > 0 else 0) + width * 0.5,
                           b + width * 0.5, y + rise))
        else:
            z0 = b if direction > 0 else b - length
            g.add(_stair_flight(a, z0, "z", length, y, y + rise, width, 13))
            g.add(_landing(a - width * 0.5,
                           z0 + (length if direction > 0 else 0) - width * 0.5,
                           a + width * 0.5,
                           z0 + (length if direction > 0 else 0) + width * 0.5,
                           y + rise))
        y += rise

    # Ringing floor, three quarters up. ANNULAR, not a full slab, and that is a
    # hard requirement rather than a flourish: the client places an actor on the
    # FIRST surface a ray from y = 400 hits, so a deck spanning the whole
    # footprint means every placement in this tower lands on whatever is
    # highest. With a full slab here and a full belfry above it, the arrival
    # spawn grounded 26 m up on the belfry rather than on the ground floor.
    # Leaving a well down the middle - which is where a campanile hangs its bell
    # anyway - keeps the centre column of tiles grounding on the floor you
    # actually arrive on.
    ring_y = rise * 6.0
    well = 1.7
    for sx, sz, w, d in ((0.0, half - well * 0.5, half * 2 - 0.4, half - well),
                         (0.0, -(half - well * 0.5), half * 2 - 0.4, half - well),
                         (half - well * 0.5, 0.0, half - well, well * 2),
                         (-(half - well * 0.5), 0.0, half - well, well * 2)):
        g.add_walk(M.box((w, 0.3, d), center=(sx, ring_y - 0.15, sz),
                         uv_scale=0.5, material=TIMBER))
    g.add(M.cylinder(0.06, 0.06, ring_y - 1.4, 6, uv_scale=1.0, material=CANVAS)
          .translate(1.6, 1.2, 0.0))

    # the bell itself, hung from the belfry frame at the top
    g.add(M.lathe([[0.0, 2.6], [1.1, 2.2], [1.5, 1.0], [1.7, 0.25],
                   [1.75, 0.0], [1.5, 0.0]], 22, uv_scale=0.7,
                  material=VERDIGRIS).translate(0.0, top - 4.4, 0.0))
    g.add(M.box((0.34, 0.34, half * 2 - 0.6), center=(0.0, top - 1.5, 0.0),
                uv_scale=0.6, material=TIMBER_DARK))
    g.add(M.box((half * 2 - 0.6, 0.34, 0.34), center=(0.0, top - 1.5, 0.0),
                uv_scale=0.6, material=TIMBER_DARK))

    # Belfry gallery: annular for the same reason, and the bell hangs through it.
    for sx, sz, w, d in ((0.0, half - well * 0.5, half * 2 - 0.4, half - well),
                         (0.0, -(half - well * 0.5), half * 2 - 0.4, half - well),
                         (half - well * 0.5, 0.0, half - well, well * 2),
                         (-(half - well * 0.5), 0.0, half - well, well * 2)):
        g.add_walk(M.box((w, 0.3, d), center=(sx, top - 0.15, sz),
                         uv_scale=0.5, material=MOSAIC))
    for i in range(4):
        angle = math.pi * 0.5 * i
        g.add(S.balustrade(half * 2 - 0.6, height=1.05, material=MARBLE)
              .transformed(M.rotation_y(angle)
                           @ M.translation(0.0, top, half - 0.4)))

    lamps, placed = hanging_lamps(
        [(0.0, rise * 2 + 2.2, 0.0), (0.0, rise * 5 + 2.2, 0.0),
         (0.0, ring_y + 2.4, 0.0)], seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "shaft"
    it.landmark("campanile-bell", "The Tide Bell", "shaft", top - 4.0)
    it.interactives.append({
        "id": "campanile-bell-rope", "name": "Bell Rope", "type": "mechanism",
        "position": [1.6, 1.4, 0.0], "authority": "server"})
    it.subjects = [
        ("switchback stair", "shaft", "eight flights round a hollow shaft"),
        ("ringing floor", "shaft", "timber deck where the rope comes down"),
        ("belfry gallery", "shaft", "open arcade under the verdigris cap"),
    ]
    it.notes.append(
        "Modelled as one 26 m shaft with flights and landings added as walk "
        "geometry, not as stacked chambers.")
    it.notes.append(
        "The ringing floor and belfry gallery are annular. The client places an "
        "actor on the first surface a downward ray meets, so a full-footprint "
        "deck would ground every placement in the tower on the topmost floor. "
        "A player can still WALK the stair normally - only placement is "
        "single-layer - but no spawn or portal may sit beneath a deck.")
    it.environment = {
        "sky": {"type": "gradient", "zenith": [0.16, 0.42, 0.72],
                "horizon": [0.72, 0.87, 0.92]},
        "sun": {"enabled": True, "direction": [-0.30, -0.84, 0.45],
                "color": [1.12, 1.05, 0.95], "energy": 0.95},
        "ambient": {"color": [0.60, 0.72, 0.80], "energy": 0.62,
                    "skyContribution": 0.55},
        "fog": {"enabled": False},
    }
    return it


# ===================================================== 3. The Tide Cistern
def tide_cistern(seed: int = 20260903) -> Interior:
    """The city's fresh-water reservoir under the garden islet.

    A hundred columns standing in a hand's depth of still water, lit by oculi
    from the garden plaza overhead. Where the Drowned Crown is water that got
    in, this is water that was put here on purpose and is still doing its job.
    """
    it = Interior("crownwater_tide_cistern", "The Tide Cistern", "utility",
                  "crownwater-pavilion-pavilion_west", [-48.0, 5.21, -114.0],
                  "cistern-stair")
    rng = np.random.default_rng(seed)
    g = it.group
    water = -3.35

    it.space("wellhouse", -5, -5, 5, 5, 0.0, 4.4, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=STONE, ceiling="vault", vault_rise=1.6,
             doors=[("north", 0.0, 3.2, 2.8)])
    it.space("basin", -26, 16, 26, 62, -4.0, 7.5, floor_mat=SAND,
             wall_mat=STONE, ceil_mat=STONE, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 3.6, 3.0), ("east", 39.0, 3.4, 2.8)])
    it.space("sluice_room", 30, 30, 44, 48, -4.0, 5.4, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=STONE,
             doors=[("west", 39.0, 3.4, 2.8)])

    _link(it, "cistern_stair", (0, 5), (0, 16), 3.6, 0.0, -4.0, 3.6, 16,
          floor_mat=PAVING, wall_mat=STONE, ceil_mat=STONE, seed=seed + 1)
    _link(it, "sluice_run", (26, 39), (30, 39), 3.4, -4.0, -4.0, 3.4, 0,
          floor_mat=PAVING, wall_mat=STONE, ceil_mat=STONE, seed=seed + 2)

    # -- the basin: the forest of columns, and the water they stand in
    g.add(_column_grid(-22.0, 20.0, 22.0, 58.0, 4.4, 7.5, -4.0,
                       radius=0.46, material=STONE, seed=seed + 10))
    g.add(_sheet(-26, 16, 26, 62, water))

    # A raised walkway through the middle, so the room is crossable on foot
    # rather than only wadeable. Registered walk; the water is not.
    g.add_walk(M.box((3.4, 0.35, 46.0), center=(0.0, water + 0.15, 39.0),
                     uv_scale=0.5, material=PAVING))
    for z in np.arange(20.0, 59.0, 6.0):
        g.add(S.balustrade(6.0, height=0.9, material=STONE)
              .transformed(M.rotation_y(math.pi * 0.5)
                           @ M.translation(0.0, water + 0.3, float(z))))

    # Oculi: the garden's own light wells, dropping shafts onto the water.
    # Modelled as openings framed in brass; the light itself is the client's.
    for ox, oz in ((-11.0, 27.0), (11.0, 39.0), (-11.0, 51.0)):
        g.add(M.lathe([[2.2, 0.0], [2.2, 0.5], [1.9, 0.5], [1.9, 0.0]], 20,
                      uv_scale=0.6, material=GILT).translate(ox, 3.2, oz))
        # [x, y, z], matching what hanging_lamps records. Written [x, z, y] the
        # oculi lit a point 27 m above the basin instead of 3 m above it.
        it.lamps.append([ox, 3.0, oz])

    # -- sluice room: the brass gear that lets the basin down to the lagoon
    cx, cz = it.centre("sluice_room")
    g.add(M.lathe([[1.6, 0.0], [1.6, 0.22], [0.3, 0.22], [0.3, 0.0]], 24,
                  uv_scale=0.7, material=GILT).translate(cx, -1.4, cz))
    for i in range(8):
        angle = 2.0 * math.pi * i / 8
        g.add(M.box((0.22, 0.5, 1.5),
                    center=(cx + math.cos(angle) * 1.1, -1.4,
                            cz + math.sin(angle) * 1.1),
                    uv_scale=0.8, material=IRON)
              .transformed(M.rotation_y(angle)))
    g.add(M.cylinder(0.14, 0.14, 3.0, 8, uv_scale=0.8, material=IRON)
          .translate(cx, -4.0, cz))
    g.add(M.box((4.4, 0.4, 0.6), center=(cx, -3.8, cz - 4.2), uv_scale=0.6,
                material=STONE))
    for i in range(3):
        g.add(P.crate(seed=seed + 30 + i).translate(
            cx - 4.5 + i * 1.2, -4.0, cz + 5.0))

    lamps, placed = hanging_lamps(
        [(0.0, -1.4, 22.0), (0.0, -1.4, 39.0), (0.0, -1.4, 56.0),
         (cx, -1.6, cz)], seed=seed + 40)
    g.add(lamps)
    it.lamps = it.lamps + placed

    it.spawn_space = "wellhouse"
    it.landmark("cistern-sluice", "The Sluice Gear", "sluice_room", 1.2)
    it.landmark("cistern-basin", "The Tide Basin", "basin", 1.8)
    it.interactives.append({
        "id": "cistern-sluice-wheel", "name": "Sluice Wheel", "type": "mechanism",
        "position": [round(cx, 2), -1.4, round(cz, 2)], "authority": "server"})
    it.harvestables.append({
        "id": "cistern-freshwater", "resource": "freshwater",
        "position": [0.0, round(water, 2), 39.0], "authority": "server"})
    it.subjects = [
        ("column basin", "basin", "a hundred columns in still fresh water"),
        ("oculi", "basin", "light wells down from the garden plaza"),
        ("raised walk", "basin", "the dry way across"),
        ("sluice room", "sluice_room", "brass gear letting the basin down"),
    ]
    it.environment = {
        "sky": {"type": "gradient", "zenith": [0.08, 0.16, 0.20],
                "horizon": [0.18, 0.30, 0.32]},
        "sun": {"enabled": True, "direction": [-0.05, -0.98, 0.16],
                "color": [1.05, 1.02, 0.92], "energy": 1.05},
        "ambient": {"color": [0.34, 0.44, 0.48], "energy": 0.88,
                    "skyContribution": 0.30},
        "fog": {"enabled": True, "color": [0.20, 0.30, 0.33], "density": 0.010},
    }
    return it


# =============================================== 4. The Harbour Customs Hall
def customs_hall(seed: int = 20260904) -> Interior:
    """The bonded warehouse behind the arrival islet's quay.

    The only interior in the set with a job. Timber and plaster over stone,
    ledgers and crates and a strongroom, and a water gate at the back where a
    lighter comes in under the building to unload out of the weather.

    Deliberately the plainest of the four: three monuments in a row would make
    Crownwater a museum rather than a place people work.
    """
    it = Interior("crownwater_customs_hall", "The Harbour Customs Hall",
                  "settlement", "crownwater-customs-hall",
                  [40.0, 4.35, -14.0], "customs-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("ledger_hall", -12, -9, 12, 11, 0.0, 6.4, floor_mat=TIMBER,
             wall_mat=PLASTER, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 3.4, 2.8), ("north", 4.0, 3.2, 2.8),
                    ("east", 2.0, 3.0, 2.6)])
    it.space("bonded_store", -14, 20, 14, 46, -0.8, 7.2, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=TIMBER_DARK,
             doors=[("south", 4.0, 3.2, 2.8), ("east", 33.0, 2.8, 2.6)])
    it.space("strongroom", 20, 26, 32, 40, -0.8, 4.4, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=STONE, ceiling="vault", vault_rise=1.4,
             doors=[("west", 33.0, 2.8, 2.6)])
    it.space("water_gate", -16, 52, 16, 74, -2.6, 8.0, floor_mat=PAVING,
             wall_mat=STONE, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 5.0, 4.2)])

    _link(it, "store_run", (4, 11), (4, 20), 3.2, 0.0, -0.8, 3.6, 3,
          floor_mat=TIMBER, wall_mat=PLASTER, ceil_mat=TIMBER_DARK, seed=seed + 1)
    _link(it, "strong_run", (14, 33), (20, 33), 2.8, -0.8, -0.8, 3.0, 0,
          floor_mat=PAVING, wall_mat=STONE, ceil_mat=STONE, seed=seed + 2)
    _link(it, "gate_run", (0, 46), (0, 52), 5.0, -0.8, -2.6, 4.6, 5,
          floor_mat=PAVING, wall_mat=STONE, ceil_mat=STONE, seed=seed + 3)

    # -- ledger hall: counters, a mezzanine office, and the stair to it
    for i in range(3):
        z = -5.0 + i * 5.0
        g.add(M.box((7.0, 0.12, 1.1), center=(-5.0, 1.0, z), uv_scale=0.7,
                    material=TIMBER))
        for dx in (-8.0, -2.0):
            g.add(M.box((0.16, 1.0, 0.9), center=(dx, 0.5, z), uv_scale=0.8,
                        material=TIMBER_DARK))
    mezz_y = 3.2
    g.add_walk(M.box((10.0, 0.28, 8.0), center=(6.5, mezz_y - 0.14, 4.0),
                     uv_scale=0.6, material=TIMBER))
    g.add(_stair_flight(1.0, 8.4, "x", 6.0, 0.0, mezz_y, 1.4, 12,
                        material=TIMBER))
    g.add(S.balustrade(9.6, height=0.95, material=TIMBER_DARK)
          .translate(6.5, mezz_y, 0.1))
    g.add(M.box((2.2, 0.1, 1.2), center=(8.0, mezz_y + 0.75, 5.5),
                uv_scale=0.8, material=CARVED))
    for i in range(5):
        g.add(P.crate(seed=seed + 10 + i).translate(
            float(rng.uniform(-10, -4)), 0.0, float(rng.uniform(-7, 9))))

    # -- bonded store: cargo under seal, stacked to the trusses
    for i in range(22):
        x = float(rng.uniform(-12, 12))
        z = float(rng.uniform(22, 44))
        stack = int(rng.integers(1, 4))
        for k in range(stack):
            g.add(P.crate(seed=seed + 30 + i * 3 + k).translate(x, -0.8 + k * 0.95, z))
    for i in range(6):
        g.add(P.barrel(seed=seed + 90 + i).translate(
            float(rng.uniform(-13, 13)), -0.8, float(rng.uniform(21, 45))))
    for z in (24.0, 31.0, 38.0, 44.0):
        g.add(M.box((28.0, 0.4, 0.4), center=(0.0, 5.8, z), uv_scale=0.6,
                    material=TIMBER_DARK))

    # -- strongroom: brass, iron and a very short list of people with keys
    cx, cz = it.centre("strongroom")
    g.add(M.box((0.4, 2.6, 2.8), center=(20.3, 0.5, cz), uv_scale=0.6,
                material=IRON))
    for i in range(4):
        g.add(P.crate(seed=seed + 120 + i).translate(cx + 2.6, -0.8, cz - 3.0 + i * 1.6))
    g.add(M.lathe([[0.9, 0.0], [0.9, 0.6], [0.5, 0.85], [0.0, 0.95]], 18,
                  uv_scale=0.8, material=GILT).translate(cx - 2.6, -0.8, cz))

    # -- water gate: the lagoon comes in under the building
    cx, cz = it.centre("water_gate")
    g.add(_sheet(-11, 54, 11, 74, -1.9))
    for side in (-1, 1):
        g.add_walk(M.box((4.0, 0.3, 20.0), center=(side * 13.0, -1.75, 63.0),
                         uv_scale=0.5, material=PAVING))
        for k in range(4):
            g.add(CA.bollard().translate(side * 12.0, -1.6, 56.0 + k * 5.0))
    g.add(CA.moored_boat(7.2, seed=seed + 140).translate(0.0, -2.05, 62.0))
    g.add(M.arch(span=9.0, rise=3.4, thickness=0.9, depth=1.6, material=STONE)
          .transformed(M.rotation_y(math.pi * 0.5))
          .translate(0.0, -1.9, 74.0))

    lamps, placed = hanging_lamps(
        [(0.0, 4.6, 0.0), (6.5, 5.4, 4.0), (0.0, 4.8, 32.0),
         (0.0, 4.2, 63.0), (11.0, 3.2, 58.0)], seed=seed + 150)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "ledger_hall"
    it.landmark("customs-ledger", "The Ledger Hall", "ledger_hall", 1.4)
    it.landmark("customs-strongroom", "The Bonded Strongroom", "strongroom", 1.2)
    it.landmark("customs-water-gate", "The Water Gate", "water_gate", 1.6)
    it.interactives.append({
        "id": "customs-ledger-desk", "name": "Customs Ledger", "type": "desk",
        "position": [-5.0, 1.2, 0.0], "authority": "server"})
    it.interactives.append({
        "id": "customs-strongroom-door", "name": "Strongroom Door", "type": "door",
        "position": [20.3, 0.6, round(it.centre("strongroom")[1], 2)],
        "authority": "server"})
    it.npc_markers.append({
        "id": "customs-officer", "name": "Customs Officer", "type": "npc",
        "position": [-5.0, 0.0, 4.0], "authority": "server"})
    it.npc_markers.append({
        "id": "customs-lighterman", "name": "Lighterman", "type": "npc",
        "position": [10.0, -1.6, 60.0], "authority": "server"})
    it.subjects = [
        ("ledger hall", "ledger_hall", "counters and a mezzanine office"),
        ("bonded store", "bonded_store", "cargo under seal, stacked to the trusses"),
        ("strongroom", "strongroom", "iron door, brass, and a short list of keys"),
        ("water gate", "water_gate", "a lighter unloading inside the building"),
    ]
    it.environment = {
        "sky": {"type": "gradient", "zenith": [0.16, 0.42, 0.72],
                "horizon": [0.72, 0.87, 0.92]},
        "sun": {"enabled": True, "direction": [-0.30, -0.84, 0.45],
                "color": [1.10, 1.02, 0.90], "energy": 0.95},
        "ambient": {"color": [0.60, 0.62, 0.64], "energy": 0.95,
                    "skyContribution": 0.35},
        "fog": {"enabled": True, "color": [0.42, 0.46, 0.48], "density": 0.006},
    }
    return it


ALL = {
    "drowned_crown": drowned_crown,
    "tide_campanile": tide_campanile,
    "tide_cistern": tide_cistern,
    "customs_hall": customs_hall,
}


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def eleventh_bell(seed: int = 20260905) -> Interior:
    """The bell that rang once too often: a register-shrine under the northeast pavilion."""
    return SR.shrine("crownwater_eleventh_bell", "The Eleventh Bell",
                     "crownwater-pavilion-pavilion_northeast", [228.6, 4.2, -228.6],
                     "eleventh-bell-door",
                     palette={"floor": PAVING, "wall": STONE, "ceil": STONE, "accent": CARVED,
                              "metal": IRON},
                     seed=seed, style="lantern")


def case_room(seed: int = 20260906) -> Interior:
    """Where the unclaimed case waits, under the east pavilion."""
    return SR.cottage("crownwater_case_room", "The Case Room",
                      "crownwater-pavilion-pavilion_east", [276.0, 4.0, -114.0], "case-room-door",
                      palette={"floor": TIMBER, "wall": PLASTER, "roof": TIMBER_DARK,
                               "timber": TIMBER_DARK, "stone": RUBBLE, "cloth": CANVAS,
                               "iron": IRON},
                      seed=seed, trade="chandlery")


def the_grating(seed: int = 20260907) -> Interior:
    """The grating that was open: the cut under the south pavilion the fish come up."""
    return SR.cave("crownwater_grating", "The Grating", "crownwater-pavilion-pavilion_south",
                   [114.0, 4.7, 48.0], "grating-mouth",
                   palette={"floor": "packed_earth", "rock": RUBBLE, "water": WATER,
                            "bone": "pale_ashlar"},
                   seed=seed, den="Abyssal Armoured Fish", pool=True)


ALL.update({"eleventh_bell": eleventh_bell, "case_room": case_room, "the_grating": the_grating})
