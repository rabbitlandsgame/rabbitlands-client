"""Westhaven's insides: four interiors on one map with blackspace between them.

    The Custom House      inside The Custom House        civic
    The Bonded Vaults     under the warehouse row        stores
    The Lamp Rock Light   inside The Lamp Rock Light     tower
    The Gullstone Undertow  under The Gullstone Watch    cave

They share the region's material table, its `MeshGroup` walk-surface contract
and its modelling primitives, so a doorway, a stair tread and a bracket are the
same construction indoors as out. Nothing here is scattered by a noise function:
every chamber is an authored extent and every prop is placed by hand.

FOUR KINDS OF PLACE, NOT ONE ROOM FOUR TIMES
--------------------------------------------
A region whose interiors are all the same room with different props has no
interiors. These are built from four deliberately disjoint material sets:

**The Custom House** - dressed ashlar, polished oak, brass and glass. Lit,
occupied, bureaucratic: the tide board, the ledger office, a weighing floor
tall enough for a beam scale, and the bonded strongroom behind an iron door.
The only warm, orderly place of the four.

**The Bonded Vaults** - the counterweight to it. Brick barrel vaults cut into
the terrace riser under the warehouse row, stacked with cargo, with a hoist
shaft up to the quay floor above and a flooded sump at the seaward end where
the tide gets in. No dressed stone, no brass, no daylight.

**The Lamp Rock Light** - stone, iron and glass, and almost nothing else. A
climb: oil store at the foot, two stair flights through the rock, the watch
room with its chart table, the lantern room with the burner and the lens, and
the gallery outside it, open to the sky.

**The Gullstone Undertow** - no dressed stone and no straight line. A cleft
down from the watch tower into a sea cave with a tidal pool open to the water,
a shingle beach inside it with a boat drawn up, a smugglers' ledge, and a
blowhole open to the sky that the sea breathes through.

TWO RULES THAT ARE LOAD-BEARING
-------------------------------
* A walkable surface must be registered with `add_walk`. The client turns
  `navigation.surfaceNodePrefixes` into the layer its grounding ray tests, so a
  floor added with `add` is scenery the player falls through.
* **No two spaces may overlap in plan.** The server grid is 2-D: a cell has one
  height, so an overhead deck owns its footprint and the ground beneath it is
  not separately walkable. That is why the lighthouse is *unfolded* - see
  `lamp_rock_light` below.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A, mesh as M, props as P, stonework as S
from amberwood.interiors import (EYE, WALL_T, Interior, chamber, passage,
                                 hanging_lamps)

import havenarch as HA
import havenkit as HK

# Rotate-then-move. `rotation @ translation` rotates an already-placed piece
# about the world origin and flings it; see `havenarch.at` for the whole story.
at = HA.at

# ------------------------------------------------------------------ palette
SETT = HK.SETT
SEA_ROCK = HK.SEA_ROCK
SHINGLE = HK.SHINGLE
PLANK = HK.PLANK
BRASS = HK.BRASS
STONE = "ashlar"
RUBBLE = "rubble_stone"
PLASTER = "lime_plaster"
EARTH = "packed_earth"
TIMBER = "timber_warm"
TIMBER_DARK = "timber_dark"
TIMBER_GREY = "timber_grey"
CARVED = "carved_wood"
IRON = "dark_iron"
GLASS = "amber_resin"
CLOTH = "woven_cloth"
CANVAS = "canvas_awning"
WATER = "water_deep"
# `props.fishing_gear` and `props.basket` weave their baskets in reed, so a
# harbour interior that carries either references it whether or not it thatches
# anything.
REED = "thatch_reed"

MATERIALS = frozenset({
    SETT, SEA_ROCK, SHINGLE, PLANK, BRASS,
    STONE, RUBBLE, PLASTER, EARTH,
    TIMBER, TIMBER_DARK, TIMBER_GREY, CARVED, IRON, GLASS, CLOTH, CANVAS,
    WATER, REED,
})
"""What the four sections reference, pinned so the package embeds nothing else."""


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _link(it: Interior, ident: str, a, b, width, y0, y1, height, steps,
          floor_mat, wall_mat, ceil_mat, seed: int) -> None:
    """Add a passage and register it as a space, so cameras and the manifest
    can see it. Every section uses this, so the bookkeeping lives in one place."""
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


def _shelf(x, y, z, length, depth=0.55, posts=True, material=TIMBER_DARK):
    """A wall shelf: a board on two brackets. Used in three of the four."""
    out = S.MeshGroup()
    out.add(M.box((length, 0.07, depth), center=(x, y, z), uv_scale=0.7,
                  material=material))
    if posts:
        for side in (-1, 1):
            out.add(M.box((0.09, 0.5, 0.09),
                          center=(x + side * (length * 0.5 - 0.25), y - 0.28, z),
                          uv_scale=0.9, material=material))
    return out


# ==========================================================================
# 1. The Custom House
# ==========================================================================
def custom_house(seed: int = 20260902) -> Interior:
    """The harbour's paperwork, in dressed stone and polished oak.

    Every cargo landed at Westhaven is weighed, taxed and entered here, and the
    interior is organised around that sequence: you come in at the tide board,
    the ledgers run east, the weighing floor is tall enough to swing a beam
    scale, and what cannot be released sits in the strongroom until the duty is
    paid.
    """
    it = Interior("westhaven_custom_house", "The Custom House", "civic",
                  "custom-house", [-72.0, 9.55, -7.0], "custom-house-hall")
    rng = _rng(seed)
    g = it.group

    it.space("hall", -8, -6, 8, 6, 0.0, 5.0, floor_mat=SETT, wall_mat=STONE,
             ceil_mat=PLASTER, doors=[("south", 0.0, 3.0, 3.2),
                                      ("north", 0.0, 3.6, 3.2),
                                      ("east", 2.0, 3.6, 3.0)])
    it.space("ledgers", -8, 14, 8, 34, 0.0, 4.4, floor_mat=TIMBER,
             wall_mat=PLASTER, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 3.6, 3.2), ("north", 0.0, 3.0, 3.0),
                    ("east", 26.0, 2.8, 2.8)])
    it.space("weighing", 20, -8, 40, 12, 0.0, 7.2, floor_mat=SETT,
             wall_mat=STONE, ceil_mat=TIMBER_DARK,
             doors=[("west", 2.0, 3.6, 3.0)])
    it.space("strongroom", 22, 20, 34, 32, 0.0, 3.4, floor_mat=SETT,
             wall_mat=STONE, ceil_mat=STONE,
             doors=[("west", 26.0, 2.8, 2.8)])
    it.space("loft", -8, 42, 8, 58, 5.4, 4.0, floor_mat=TIMBER,
             wall_mat=PLASTER, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 3.0, 3.0)])

    _link(it, "entry_run", (0, 6), (0, 14), 4.0, 0.0, 0.0, 4.0, 0,
          TIMBER, PLASTER, TIMBER_DARK, seed + 1)
    _link(it, "weigh_way", (8, 2), (20, 2), 3.6, 0.0, 0.0, 4.0, 0,
          SETT, STONE, TIMBER_DARK, seed + 2)
    _link(it, "vault_way", (8, 26), (22, 26), 2.8, 0.0, 0.0, 3.0, 0,
          SETT, STONE, STONE, seed + 3)
    _link(it, "loft_stair", (0, 34), (0, 42), 3.0, 0.0, 5.4, 3.4, 18,
          TIMBER, PLASTER, TIMBER_DARK, seed + 4)

    # -- hall: the tide board, the counter, the public bench -----------------
    g.add(M.box((5.0, 2.2, 0.18), center=(0.0, 2.6, 5.6), uv_scale=0.6,
                material=TIMBER_DARK))
    for row in range(7):                       # the tide table's ruled lines
        g.add(M.box((4.6, 0.04, 0.03), center=(0.0, 1.75 + row * 0.28, 5.48),
                    uv_scale=1.2, material=CARVED))
    g.add(M.box((7.0, 1.15, 0.9), center=(-2.0, 0.575, 1.2), uv_scale=0.5,
                material=CARVED))              # the counter
    g.add(M.box((7.4, 0.12, 1.2), center=(-2.0, 1.21, 1.2), uv_scale=0.6,
                material=TIMBER))
    for i in range(3):
        g.add(P.crate(size=0.6, seed=seed + 10 + i,
                      material=TIMBER_GREY).translate(
            5.2 - i * 0.9, 0.0, -3.4 + float(rng.uniform(-0.3, 0.3))))
    g.add(A.railing(6.0, height=0.95, material=CARVED).transformed(
        M.translation(-3.0, 0.0, -2.4)))
    it.lamps += [[0.0, 3.6, 0.0], [0.0, 3.6, 4.0]]

    # -- ledgers: desks down both sides, shelves of bound volumes ------------
    for i in range(5):
        z = 16.5 + i * 3.6
        for side in (-1, 1):
            g.add(P.workbench(length=2.2, seed=seed + 20 + i * 2 + (side > 0),
                              tools=False).transformed(
                at(side * 5.4, 0.0, z, yaw=math.pi * 0.5)))
            g.add(M.box((0.5, 0.5, 0.5), center=(side * 5.4, 0.25, z - 1.4),
                        uv_scale=0.8, material=CARVED))      # the clerk's stool
        g.add(_shelf(0.0, 2.5, z, 3.2))
        for k in range(6):
            g.add(M.box((0.12, 0.34, 0.26),
                        center=(-1.4 + k * 0.5, 2.71, z), uv_scale=1.1,
                        material=CARVED if k % 2 else TIMBER_DARK))
    it.lamps += [[0.0, 3.4, 18.0], [0.0, 3.4, 25.0], [0.0, 3.4, 32.0]]

    # -- weighing floor: the great beam scale, tall enough to swing ----------
    g.add(M.box((0.4, 6.4, 0.4), center=(30.0, 3.2, 2.0), uv_scale=0.6,
                material=TIMBER_DARK))
    g.add(M.box((7.2, 0.34, 0.34), center=(30.0, 6.3, 2.0), uv_scale=0.6,
                material=TIMBER_DARK))
    for side in (-1, 1):                        # the two pans on their chains
        x = 30.0 + side * 3.2
        g.add(M.tube(np.array([[x, 6.2, 2.0], [x, 2.4, 2.0]]),
                     [0.04, 0.04], segments=5, material=IRON))
        g.add(M.cylinder(1.15, 1.0, 0.16, segments=16, uv_scale=0.7,
                         material=BRASS).transformed(
            M.translation(x, 2.25, 2.0)))
    for i in range(9):                          # the weights, in a graded row
        r = 0.14 + i * 0.024
        g.add(M.cylinder(r, r * 0.86, r * 2.1, segments=10, uv_scale=1.0,
                         material=IRON).transformed(
            M.translation(24.0, 0.0, -5.4 + i * 0.62)))
    for i in range(10):                         # cargo waiting to be weighed
        g.add(P.barrel(seed=seed + 40 + i).translate(
            35.0 + float(rng.uniform(-2.4, 2.4)), 0.0,
            7.0 + float(rng.uniform(-3.2, 3.2))))
    for i in range(6):
        g.add(P.crate(size=0.78, seed=seed + 50 + i,
                      material=TIMBER_GREY).translate(
            23.5 + float(rng.uniform(-1.5, 1.5)), 0.0,
            9.0 + float(rng.uniform(-1.8, 1.8))))
    g.add(P.cart(seed=seed + 60).transformed(
        at(36.0, 0.0, -4.5, yaw=0.7)))
    it.lamps += [[30.0, 5.4, 2.0], [24.0, 4.6, 8.0], [36.0, 4.6, -4.0]]

    # -- strongroom: the iron door, the bonded stack -------------------------
    g.add(M.box((0.26, 2.9, 3.0), center=(22.1, 1.45, 26.0), uv_scale=0.5,
                material=IRON))
    for i in range(3):
        g.add(M.cylinder(0.13, 0.13, 0.10, segments=10, uv_scale=1.0,
                         material=BRASS).transformed(
            at(21.95, 1.0 + i * 0.5, 26.0, roll=math.pi * 0.5)))
    for i in range(14):
        g.add(P.crate(size=0.72, seed=seed + 70 + i,
                      material=TIMBER_GREY).translate(
            24.0 + (i % 4) * 1.05, (i // 4) * 0.74, 22.5 + (i // 4) * 0.4))
    for i in range(5):
        g.add(P.sack(seed=seed + 90 + i).translate(
            31.5, 0.0, 22.0 + i * 1.3))
    it.lamps += [[28.0, 2.6, 26.0]]

    # -- loft: the records, and a window onto the harbour --------------------
    for i in range(6):
        z = 44.0 + i * 2.3
        for side in (-1, 1):
            g.add(_shelf(side * 6.2, 6.6, z, 2.0, material=TIMBER_DARK))
            g.add(_shelf(side * 6.2, 7.5, z, 2.0, material=TIMBER_DARK))
            for k in range(4):
                g.add(M.box((0.11, 0.30, 0.24),
                            center=(side * 6.2 - 0.7 + k * 0.45, 6.79, z),
                            uv_scale=1.1, material=CARVED))
    g.add(A.window(width=1.6, height=1.5, material=TIMBER_DARK).transformed(
        M.translation(0.0, 6.6, 57.9)))
    g.add(P.workbench(length=2.4, seed=seed + 110).translate(0.0, 5.4, 55.0))
    it.lamps += [[0.0, 8.4, 48.0], [0.0, 8.4, 55.0]]

    it.spawn_space = "hall"
    it.subjects = [
        ("tide-board", "the tide board and the public counter", "hall"),
        ("ledger-office", "clerks' desks and the bound ledgers", "ledgers"),
        ("beam-scale", "the great beam scale on the weighing floor", "weighing"),
        ("bonded-stack", "cargo held against unpaid duty", "strongroom"),
        ("records-loft", "the records loft over the office", "loft"),
    ]
    it.landmark("westhaven-tide-board", "The Tide Board", "hall", 1.8)
    it.landmark("westhaven-beam-scale", "The King's Beam", "weighing", 3.0)
    it.interactives += [
        {"id": "westhaven-customs-counter", "name": "Customs Counter",
         "type": "workstation", "position": [-2.0, 1.3, 1.2]},
        {"id": "westhaven-duty-ledger", "name": "Duty Ledger", "type": "notice",
         "position": [0.0, 1.0, 20.0]},
        {"id": "westhaven-kings-beam", "name": "The King's Beam",
         "type": "workstation", "position": [30.0, 2.4, 2.0]},
        {"id": "westhaven-bond-chest", "name": "Bond Chest", "type": "container",
         "position": [31.5, 0.5, 26.0]},
    ]
    it.npc_markers += [
        {"id": "westhaven-collector", "name": "Collector of Customs",
         "type": "npc", "position": [-2.0, 0.0, 3.0]},
        {"id": "westhaven-ledger-clerk", "name": "Ledger Clerk", "type": "npc",
         "position": [4.4, 0.0, 23.7]},
        {"id": "westhaven-weighmaster", "name": "Weighmaster", "type": "npc",
         "position": [27.0, 0.0, 2.0]},
    ]
    it.notes = ["Dressed ashlar, polished oak, brass and glass. The one warm, "
                "orderly, occupied place of the four."]
    return it


# ==========================================================================
# 2. The Bonded Vaults
# ==========================================================================
def bonded_vaults(seed: int = 20260903) -> Interior:
    """Brick barrel vaults under the warehouse row, and the tide in the sump.

    The counterweight to the Custom House: the same cargo, three metres lower
    and without the paperwork. Cut into the terrace riser between the quay and
    the lower town, so the hoist shaft comes out on the warehouse floor above
    and the seaward end floods.
    """
    it = Interior("westhaven_bonded_vaults", "The Bonded Vaults", "stores",
                  "warehouse-row", [-42.0, 9.5, -15.0], "bonded-vaults-tunnel")
    rng = _rng(seed)
    g = it.group

    it.space("tunnel_head", -5, -6, 5, 4, 0.0, 3.8, floor_mat=SETT,
             wall_mat=RUBBLE, ceil_mat=RUBBLE,
             doors=[("south", 0.0, 3.0, 3.0), ("north", 0.0, 3.4, 3.0)])
    it.space("bay_a", -9, 14, 9, 30, -3.0, 5.0, floor_mat=EARTH,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=2.8,
             doors=[("south", 0.0, 3.4, 3.0), ("north", 0.0, 4.0, 3.2),
                    ("east", 24.0, 3.2, 2.8), ("west", 24.0, 2.6, 2.6)])
    it.space("bay_b", -9, 36, 9, 52, -3.0, 5.0, floor_mat=EARTH,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=2.8,
             doors=[("south", 0.0, 4.0, 3.2), ("north", 0.0, 3.6, 3.0)])
    it.space("hoist", 16, 18, 28, 30, -3.0, 11.5, floor_mat=EARTH,
             wall_mat=RUBBLE, ceil_mat=TIMBER_DARK,
             doors=[("west", 24.0, 3.2, 2.8)])
    it.space("tally", -24, 20, -14, 28, -3.0, 3.2, floor_mat=EARTH,
             wall_mat=RUBBLE, ceil_mat=RUBBLE,
             doors=[("east", 24.0, 2.6, 2.6)])
    it.space("sump", -9, 58, 9, 72, -5.4, 4.6, floor_mat=SHINGLE,
             wall_mat=RUBBLE, ceil_mat=RUBBLE, ceiling="vault", vault_rise=2.4,
             doors=[("south", 0.0, 3.6, 3.0)])

    _link(it, "descent", (0, 4), (0, 14), 4.2, 0.0, -3.0, 3.8, 12,
          SETT, RUBBLE, RUBBLE, seed + 1)
    _link(it, "bays", (0, 30), (0, 36), 4.0, -3.0, -3.0, 4.4, 0,
          EARTH, RUBBLE, RUBBLE, seed + 2)
    _link(it, "hoistway", (9, 24), (16, 24), 3.2, -3.0, -3.0, 4.0, 0,
          EARTH, RUBBLE, RUBBLE, seed + 3)
    _link(it, "tallyway", (-14, 24), (-9, 24), 2.6, -3.0, -3.0, 3.0, 0,
          EARTH, RUBBLE, RUBBLE, seed + 4)
    _link(it, "sumpway", (0, 52), (0, 58), 3.6, -3.0, -5.4, 4.0, 8,
          SHINGLE, RUBBLE, RUBBLE, seed + 5)

    # -- the bays: cargo stacked to the springing of the vault ---------------
    for bay, z0 in (("a", 15.5), ("b", 37.5)):
        for i in range(26):
            col, row, tier = i % 5, (i // 5) % 3, i // 15
            x = -7.4 + col * 3.1
            z = z0 + row * 4.4
            if abs(x) < 2.6:
                continue                     # keep the centre aisle clear
            g.add(P.barrel(seed=seed + 200 + i + (bay == "b") * 40).translate(
                x + float(rng.uniform(-0.25, 0.25)), tier * 0.88,
                z + float(rng.uniform(-0.4, 0.4))))
        for i in range(12):
            col, row = i % 4, i // 4
            x = -7.0 + col * 4.6
            if abs(x) < 2.4:
                continue
            g.add(P.crate(size=0.8, seed=seed + 260 + i,
                          material=TIMBER_GREY).translate(
                x, 0.0, z0 + 1.6 + row * 5.0))
    # the vault ribs, which is what makes a cellar read as brick and not as a box
    for z0, z1 in ((14, 30), (36, 52), (58, 72)):
        floor = -3.0 if z1 < 55 else -5.4
        for i in range(5):
            z = z0 + (i + 0.5) * (z1 - z0) / 5.0
            for k in range(9):
                a = math.pi * k / 8.0
                b = math.pi * (k + 1) / 8.0
                r = 8.6
                g.add(M.box((0.34, 0.30, 0.5),
                            center=(math.cos(a) * r * 0.98,
                                    floor + 5.0 + math.sin(a) * 2.6, z),
                            uv_scale=0.8, material=RUBBLE))
    it.lamps += [[0.0, 0.6, 18.0], [0.0, 0.6, 27.0], [0.0, 0.6, 40.0],
                 [0.0, 0.6, 49.0]]

    # -- the hoist shaft: a windlass over an open well up to the quay --------
    g.add(M.box((11.0, 0.5, 11.0), center=(22.0, 7.4, 24.0), uv_scale=0.4,
                material=TIMBER_DARK))
    g.add(M.box((3.4, 0.55, 3.4), center=(22.0, 7.4, 24.0), uv_scale=0.6,
                material=IRON))                      # the trap in the floor above
    for side in (-1, 1):
        g.add(M.box((0.34, 2.2, 0.34), center=(22.0 + side * 1.9, 6.1, 24.0),
                    uv_scale=0.7, material=TIMBER_DARK))
    g.add(M.cylinder(0.42, 0.42, 3.4, segments=12, uv_scale=0.6,
                     material=TIMBER).transformed(
        at(23.7, 7.0, 24.0, roll=math.pi * 0.5)))
    g.add(M.tube(np.array([[22.0, 6.95, 24.0], [22.0, -1.6, 24.0]]),
                 [0.05, 0.05], segments=5, material=IRON))
    g.add(M.box((1.5, 0.9, 1.5), center=(22.0, -2.1, 24.0), uv_scale=0.6,
                material=TIMBER_GREY))               # the pallet on the fall
    for i in range(6):
        g.add(P.sack(seed=seed + 300 + i).translate(
            19.0 + float(rng.uniform(-1.2, 1.2)), -3.0,
            21.0 + float(rng.uniform(-1.6, 1.6))))
    it.lamps += [[19.0, 0.0, 24.0]]

    # -- the tally alcove: the only paperwork down here ----------------------
    g.add(P.workbench(length=2.0, seed=seed + 320).translate(-19.0, -3.0, 26.4))
    g.add(_shelf(-19.0, -0.6, 27.6, 5.0, material=TIMBER_GREY))
    for k in range(7):
        g.add(M.box((0.11, 0.28, 0.22), center=(-21.2 + k * 0.72, -0.42, 27.6),
                    uv_scale=1.1, material=CARVED))
    g.add(P.brazier(seed=seed + 322).translate(-16.5, -3.0, 22.0))
    it.lamps += [[-19.0, -0.6, 24.0]]

    # -- the sump: standing water, wrack, a grating to the harbour -----------
    g.add(M.box((17.0, 0.06, 13.0), center=(0.0, -4.55, 65.0), uv_scale=0.25,
                material=WATER))
    g.add(M.box((5.0, 3.2, 0.3), center=(0.0, -3.6, 71.8), uv_scale=0.6,
                material=IRON))                      # the tide grating
    for i in range(9):
        g.add(M.box((0.16, 3.0, 0.16), center=(-2.0 + i * 0.5, -3.7, 71.7),
                     uv_scale=0.9, material=IRON))
    for i in range(7):
        g.add(P.boulder(radius=0.5 + float(rng.uniform(0, 0.4)),
                        seed=seed + 340 + i, material=SEA_ROCK).translate(
            float(rng.uniform(-7.0, 7.0)), -5.4, float(rng.uniform(59.0, 63.0))))
    for i in range(4):
        g.add(P.barrel(seed=seed + 350 + i).translate(
            float(rng.uniform(-6.0, 6.0)), -5.4, float(rng.uniform(59.0, 62.0))))
    g.add(P.fishing_gear(seed=seed + 360).translate(-6.0, -5.4, 60.0))
    it.lamps += [[0.0, -3.4, 60.0]]

    it.spawn_space = "tunnel_head"
    it.subjects = [
        ("cargo-tunnel", "the cargo tunnel down from the quay", "tunnel_head"),
        ("first-bay", "casks stacked to the springing of the vault", "bay_a"),
        ("hoist-shaft", "the windlass and the trap up to the warehouse floor",
         "hoist"),
        ("tally-alcove", "the tallyman's bench and brazier", "tally"),
        ("flooded-sump", "standing water and the tide grating", "sump"),
    ]
    it.landmark("westhaven-hoist", "The Bonded Hoist", "hoist", 2.0)
    it.landmark("westhaven-tide-grating", "The Tide Grating", "sump", 1.2)
    it.interactives += [
        {"id": "westhaven-tally-bench", "name": "Tallyman's Bench",
         "type": "workstation", "position": [-19.0, -2.2, 26.4]},
        {"id": "westhaven-bonded-cask", "name": "Bonded Cask",
         "type": "container", "position": [5.0, -3.0, 20.0]},
        {"id": "westhaven-windlass", "name": "Hoist Windlass",
         "type": "workstation", "position": [22.0, -3.0, 22.2]},
    ]
    it.harvestables += [
        {"id": f"westhaven-cellar-mussels-{i}", "name": "Cellar Mussels",
         "type": "shellfish",
         "position": [round(float(rng.uniform(-6.5, 6.5)), 2), -5.3,
                      round(float(rng.uniform(59.0, 70.0)), 2)]}
        for i in range(4)
    ]
    it.npc_markers += [
        {"id": "westhaven-tallyman", "name": "Tallyman", "type": "npc",
         "position": [-18.0, -3.0, 24.5]},
        {"id": "westhaven-cellarman", "name": "Cellarman", "type": "npc",
         "position": [0.0, -3.0, 33.0]},
    ]
    it.notes = ["Brick barrel vaults, cargo, damp and no daylight. The seaward "
                "end floods: the sump's water is at -4.55, half a metre over "
                "its floor."]
    return it


# ==========================================================================
# 3. The Lamp Rock Light
# ==========================================================================
def lamp_rock_light(seed: int = 20260904) -> Interior:
    """The inside of the great lighthouse: a climb from the oil store to the lens.

    UNFOLDED ON PURPOSE. A real tower stacks its rooms one above another, and
    the server's collision grid is 2-D - a cell carries one height, so an
    overhead deck owns its footprint and the floor beneath it is not separately
    walkable. Stacking these five spaces would make four of them unreachable.

    So the climb is laid out in plan as well as in section: the lower spaces are
    cut into the rock the tower stands on and the stair works north through that
    rock before rising into the tower head. The fiction holds - Lamp Rock is a
    stack of stone and the light is built on top of it - and every space is
    reachable. The cost is that the tower you see from outside is not
    geometrically the tower you climb inside, which is recorded in the package's
    known limitations.
    """
    it = Interior("westhaven_lamp_rock_light", "The Lamp Rock Light", "tower",
                  "great-lighthouse", [302.64, 46.0, 120.24], "lamp-rock-foot")
    rng = _rng(seed)
    g = it.group

    it.space("foot", -7, -6, 7, 6, 0.0, 4.6, floor_mat=SETT, wall_mat=STONE,
             ceil_mat=STONE, doors=[("south", 0.0, 3.0, 3.0),
                                    ("north", 0.0, 3.2, 3.0),
                                    ("east", -1.0, 3.0, 2.8)])
    it.space("oilstore", 12, -6, 24, 4, 0.0, 3.6, floor_mat=SETT,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK,
             doors=[("west", -1.0, 3.0, 2.8)])
    it.space("mid_landing", -6, 16, 6, 26, 5.8, 4.0, floor_mat=SETT,
             wall_mat=SEA_ROCK, ceil_mat=STONE,
             doors=[("south", 0.0, 3.2, 3.0), ("north", 0.0, 3.2, 3.0)])
    it.space("watchroom", -8, 34, 8, 48, 11.8, 4.4, floor_mat=TIMBER,
             wall_mat=STONE, ceil_mat=TIMBER_DARK,
             doors=[("south", 0.0, 3.2, 3.0), ("north", 0.0, 3.0, 2.8)])
    it.space("lantern", -7, 56, 7, 70, 18.4, 6.2, floor_mat=IRON,
             wall_mat=STONE, ceil_mat=IRON,
             doors=[("south", 0.0, 3.0, 2.8), ("north", 0.0, 3.2, 2.8)])
    it.space("gallery", -10, 72, 10, 80, 18.4, 3.2, floor_mat=STONE,
             wall_mat=STONE, ceil_mat=STONE, ceiling="open",
             doors=[("south", 0.0, 3.2, 2.8)])

    _link(it, "oilway", (7, -1), (12, -1), 3.0, 0.0, 0.0, 3.2, 0,
          SETT, SEA_ROCK, SEA_ROCK, seed + 1)
    _link(it, "lower_stair", (0, 6), (0, 16), 3.2, 0.0, 5.8, 3.6, 20,
          SETT, SEA_ROCK, SEA_ROCK, seed + 2)
    _link(it, "upper_stair", (0, 26), (0, 34), 3.2, 5.8, 11.8, 3.6, 20,
          SETT, SEA_ROCK, STONE, seed + 3)
    _link(it, "lantern_stair", (0, 48), (0, 56), 3.0, 11.8, 18.4, 3.4, 22,
          IRON, STONE, STONE, seed + 4)
    _link(it, "gallery_door", (0, 70), (0, 72), 3.0, 18.4, 18.4, 3.0, 0,
          STONE, STONE, STONE, seed + 5)

    # -- foot: the entry stage, a bench, the keeper's boots ------------------
    g.add(M.box((6.0, 0.5, 1.0), center=(-3.4, 0.25, -4.2), uv_scale=0.6,
                material=STONE))
    g.add(_shelf(-5.0, 1.9, 5.4, 3.4, material=TIMBER_DARK))
    for i in range(4):
        g.add(M.box((0.24, 0.34, 0.20), center=(-6.2 + i * 0.5, 2.11, 5.4),
                    uv_scale=1.1, material=TIMBER_GREY))
    g.add(P.fishing_gear(seed=seed + 400).translate(5.0, 0.0, 3.6))
    it.lamps += [[0.0, 3.4, 0.0]]

    # -- oil store: the year's oil, in casks on stillages --------------------
    for i in range(12):
        col, row = i % 4, i // 4
        g.add(P.barrel(radius=0.40, height=0.98,
                       seed=seed + 410 + i).translate(
            14.0 + col * 2.4, 0.35, -4.4 + row * 2.6))
    for row in range(3):
        g.add(M.box((9.6, 0.34, 0.5), center=(18.0, 0.17, -4.4 + row * 2.6),
                    uv_scale=0.6, material=TIMBER_DARK))
    g.add(M.box((1.1, 1.4, 1.1), center=(22.4, 0.7, 2.4), uv_scale=0.6,
                material=IRON))               # the measure and the filling can
    it.lamps += [[18.0, 2.6, -1.0]]

    # -- mid landing: a window slot and the rock showing through -------------
    g.add(A.window(width=0.7, height=1.6, material=IRON).transformed(
        at(-5.9, 7.4, 21.0, yaw=math.pi * 0.5)))
    for i in range(5):
        g.add(P.boulder(radius=0.6 + float(rng.uniform(0, 0.5)),
                        seed=seed + 430 + i, material=SEA_ROCK).translate(
            float(rng.uniform(3.0, 5.2)), 5.8, float(rng.uniform(17.0, 25.0))))
    it.lamps += [[0.0, 8.6, 21.0]]

    # -- watch room: chart table, the log, the glass, a stove ----------------
    g.add(P.workbench(length=2.8, seed=seed + 440).translate(0.0, 11.8, 40.0))
    g.add(M.box((2.4, 0.03, 1.6), center=(0.0, 12.72, 40.0), uv_scale=0.9,
                material=CLOTH))              # the chart
    for side in (-1, 1):
        g.add(A.window(width=1.3, height=1.5, material=IRON).transformed(
            M.rotation_y(math.pi * 0.5)
            @ M.translation(side * 7.9, 13.2, 41.0)))
    g.add(M.cylinder(0.5, 0.42, 1.5, segments=12, uv_scale=0.7,
                     material=IRON).transformed(M.translation(6.0, 11.8, 36.5)))
    g.add(M.tube(np.array([[6.0, 13.3, 36.5], [6.0, 16.4, 36.5]]),
                 [0.12, 0.10], segments=6, material=IRON))
    g.add(_shelf(-6.4, 13.6, 45.0, 2.6, material=TIMBER_DARK))
    for k in range(5):
        g.add(M.box((0.10, 0.30, 0.22), center=(-7.4 + k * 0.5, 13.79, 45.0),
                    uv_scale=1.1, material=CARVED))
    g.add(M.box((0.6, 0.6, 0.6), center=(-4.0, 12.1, 43.0), uv_scale=0.8,
                material=CARVED))
    it.lamps += [[0.0, 15.2, 40.0], [0.0, 15.2, 45.0]]

    # -- lantern room: the burner, the lens, the glazing ---------------------
    g.add(M.cylinder(1.5, 1.35, 1.1, segments=14, uv_scale=0.6,
                     material=BRASS).transformed(M.translation(0.0, 18.4, 63.0)))
    g.add(M.cylinder(0.7, 0.6, 1.2, segments=12, uv_scale=0.7,
                     material=BRASS).transformed(M.translation(0.0, 19.5, 63.0)))
    # the lens: stacked annular rings, which is what a Fresnel reads as
    for i in range(9):
        y = 19.4 + i * 0.34
        r = 2.05 * math.sin(math.pi * (0.18 + 0.64 * i / 8.0))
        g.add(M.lathe([(r, 0.0), (r + 0.20, 0.10), (r + 0.20, 0.24), (r, 0.34)],
                      segments=20, uv_scale=0.7, material=GLASS).transformed(
            M.translation(0.0, y, 63.0)))
    for i in range(12):                        # the lantern's glazing bars
        a = math.pi * 2.0 * i / 12.0
        g.add(M.box((0.13, 5.4, 0.13),
                    center=(math.cos(a) * 5.6, 21.1, 63.0 + math.sin(a) * 5.6),
                    uv_scale=0.8, material=IRON))
    g.add(M.lathe([(5.8, 0.0), (5.2, 0.9), (3.2, 1.9), (0.0, 2.4)],
                  segments=20, uv_scale=0.6, material=IRON).transformed(
        M.translation(0.0, 23.8, 63.0)))
    g.add(P.barrel(radius=0.34, height=0.8, seed=seed + 460).translate(
        4.4, 18.4, 58.5))
    it.lamps += [[0.0, 21.0, 63.0]]

    # -- gallery: outside the lantern, open to the sky -----------------------
    for i in range(16):
        a = math.pi * (0.06 + 0.88 * i / 15.0)
        g.add(M.box((0.11, 1.05, 0.11),
                    center=(math.cos(a) * 9.2, 18.9, 76.0 + math.sin(a) * 3.4),
                    uv_scale=0.9, material=IRON))
    g.add(M.box((19.4, 0.10, 0.10), center=(0.0, 19.45, 79.4), uv_scale=0.6,
                material=IRON))
    g.add(HA.bollard(height=0.6, seed=seed + 470).transformed(
        M.translation(-7.0, 18.4, 74.0)))
    it.lamps += [[0.0, 20.4, 76.0]]

    it.spawn_space = "foot"
    it.open_to_sky.append("gallery")
    it.subjects = [
        ("tower-foot", "the entry stage at the tower's foot", "foot"),
        ("oil-store", "the year's oil on its stillages", "oilstore"),
        ("stair-rock", "the stair worked through the rock", "mid_landing"),
        ("watch-room", "chart table, log and stove", "watchroom"),
        ("lantern-room", "the burner and the lens", "lantern"),
        ("gallery", "the gallery outside the lantern, open to the sky",
         "gallery"),
    ]
    it.landmark("westhaven-lens", "The Lamp Rock Lens", "lantern", 2.4)
    it.landmark("westhaven-watch-room", "The Keeper's Watch", "watchroom", 1.4)
    it.interactives += [
        {"id": "westhaven-lamp-burner", "name": "The Burner",
         "type": "workstation", "position": [0.0, 19.5, 63.0]},
        {"id": "westhaven-keepers-log", "name": "Keeper's Log", "type": "notice",
         "position": [0.0, 12.8, 40.0]},
        {"id": "westhaven-oil-stillage", "name": "Oil Stillage",
         "type": "container", "position": [18.0, 0.4, -1.0]},
    ]
    it.npc_markers += [
        {"id": "westhaven-lightkeeper-in", "name": "Lightkeeper", "type": "npc",
         "position": [0.0, 11.8, 43.0]},
    ]
    it.notes = ["Stone, iron and glass, and almost nothing else.",
                "Unfolded in plan rather than stacked, because the server "
                "collision grid is 2-D and a stacked tower makes every space "
                "but the top one unreachable."]
    return it


# ==========================================================================
# 4. The Gullstone Undertow
# ==========================================================================
def gullstone_cave(seed: int = 20260905) -> Interior:
    """A sea cave under the Gullstone watch: tidal, natural, no dressed stone.

    The counterweight to all three of the others. Nothing here is built except
    what smugglers dragged in: the rock is the wall, the floor is shingle and
    water, and the only straight lines are a boat's keel and a timber staging.
    """
    it = Interior("westhaven_gullstone_undertow", "The Gullstone Undertow",
                  "cave", "gullstone-watch", [-77.5, 17.05, 96.5],
                  "gullstone-cleft")
    rng = _rng(seed)
    g = it.group

    it.space("cleft", -6, -6, 6, 6, 0.0, 5.4, floor_mat=SEA_ROCK,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK, ceiling="vault",
             vault_rise=2.4, doors=[("south", 0.0, 3.0, 3.0),
                                    ("north", 0.0, 4.4, 3.4)])
    it.space("cavern", -26, 22, 26, 70, -8.4, 17.0, floor_mat=SHINGLE,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK, ceiling="vault",
             vault_rise=8.0, doors=[("south", 0.0, 4.4, 3.4),
                                    ("north", -20.0, 5.0, 3.6),
                                    ("east", 46.0, 4.0, 3.2),
                                    ("north", 0.0, 4.0, 3.2)])
    it.space("beach", -32, 74, -10, 92, -7.6, 9.0, floor_mat=SHINGLE,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK, ceiling="vault",
             vault_rise=4.2, doors=[("south", -20.0, 5.0, 3.6)])
    it.space("stash", 34, 40, 46, 52, -4.6, 4.2, floor_mat=EARTH,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK, ceiling="vault",
             vault_rise=2.0, doors=[("west", 46.0, 4.0, 3.2)])
    it.space("blowhole", -6, 76, 6, 88, -8.4, 19.0, floor_mat=SEA_ROCK,
             wall_mat=SEA_ROCK, ceil_mat=SEA_ROCK, ceiling="open",
             doors=[("south", 0.0, 4.0, 3.2)])

    _link(it, "descent", (0, 6), (0, 22), 4.4, 0.0, -8.4, 5.0, 22,
          SEA_ROCK, SEA_ROCK, SEA_ROCK, seed + 1)
    _link(it, "beachway", (-20, 70), (-20, 74), 5.0, -8.4, -7.6, 5.0, 3,
          SHINGLE, SEA_ROCK, SEA_ROCK, seed + 2)
    _link(it, "stashway", (26, 46), (34, 46), 4.0, -8.4, -4.6, 4.0, 10,
          SEA_ROCK, SEA_ROCK, SEA_ROCK, seed + 3)
    _link(it, "blowway", (0, 70), (0, 76), 4.0, -8.4, -8.4, 4.4, 0,
          SEA_ROCK, SEA_ROCK, SEA_ROCK, seed + 4)

    # -- the cavern: a tidal pool over half its floor, and rock everywhere ---
    g.add(M.box((30.0, 0.06, 30.0), center=(8.0, -7.3, 46.0), uv_scale=0.2,
                material=WATER))
    # Boulders on a radial falloff from the centre line a player walks, so the
    # rock is dense against the walls and thin where the route runs.
    for i in range(70):
        x = float(rng.uniform(-25.0, 25.0))
        z = float(rng.uniform(23.0, 69.0))
        edge = min(abs(x + 26.0), abs(26.0 - x)) / 26.0
        if float(rng.uniform(0, 1)) < edge * 0.85:
            continue
        r = 0.55 + float(rng.uniform(0.0, 1.5)) * (0.4 + edge)
        g.add(P.boulder(radius=r, seed=seed + 500 + i,
                        material=SEA_ROCK).translate(x, -8.4, z))
    # Stalactites down from the vault, thickest over the pool. `mesh.cylinder`
    # builds upward from y = 0 with `radius_bottom` first, so a downward taper
    # is just a narrow bottom and a wide top placed at ceiling minus drop - no
    # rotation, and therefore none of the flinging that a rotate-then-translate
    # composed the wrong way round produces.
    ceiling = -8.4 + 17.0
    for i in range(34):
        x = float(rng.uniform(-22.0, 24.0))
        z = float(rng.uniform(25.0, 67.0))
        drop = float(rng.uniform(1.2, 4.6))
        g.add(M.cylinder(0.05, 0.42, drop, segments=7, uv_scale=0.7,
                         material=SEA_ROCK).transformed(
            M.translation(x, ceiling - drop, z)))
    # More lamps than a smugglers' cave strictly wants, and with a longer reach
    # than the 9 m default. The first client capture of this section averaged 12
    # to 15 out of 255 - defensible for an unlit cave and useless as a place to
    # look at - and adding lamps at the default range moved it by 0.1, because
    # 9 m of throw in a chamber 52 m across lights almost nothing.
    #
    # A lamp may carry `range` and `energy` after its position; the manifest
    # writer honours them and `godot_capture.gd` binds them.
    it.lamps += [[-16.0, -5.4, 27.0, 26.0, 2.2], [-18.0, -5.4, 38.0, 26.0, 2.2],
                 [-17.0, -5.4, 50.0, 26.0, 2.2], [-14.0, -5.4, 62.0, 24.0, 2.0],
                 [2.0, -5.8, 33.0, 22.0, 1.8], [6.0, -5.8, 56.0, 22.0, 1.8]]

    # -- the beach: shingle, a boat drawn up, a fire ------------------------
    g.add(P.rowing_boat(length=4.6, seed=seed + 560).transformed(
        at(-22.0, -7.4, 82.0, yaw=0.5)))
    g.add(P.rowing_boat(length=4.0, seed=seed + 562).transformed(
        at(-15.0, -7.5, 87.0, yaw=2.3)))
    g.add(P.brazier(seed=seed + 564).translate(-26.0, -7.6, 78.0))
    for i in range(10):
        g.add(P.boulder(radius=0.4 + float(rng.uniform(0, 0.5)),
                        seed=seed + 570 + i, material=SEA_ROCK).translate(
            float(rng.uniform(-31.0, -11.0)), -7.6,
            float(rng.uniform(75.0, 91.0))))
    g.add(P.fishing_gear(seed=seed + 580).translate(-28.0, -7.6, 85.0))
    # a timber staging over the shingle, the one built thing in the cave
    g.add(M.box((7.0, 0.16, 3.0), center=(-20.0, -7.0, 76.5), uv_scale=0.5,
                material=PLANK))
    for side in (-1, 1):
        for k in range(3):
            g.add(M.cylinder(0.16, 0.14, 0.9, segments=6, uv_scale=0.8,
                             material=TIMBER_DARK).transformed(
                M.translation(-23.0 + k * 3.0, -7.9, 76.5 + side * 1.2)))
    it.lamps += [[-22.0, -5.6, 82.0, 18.0, 2.0], [-26.5, -6.2, 78.5, 16.0, 2.4],
                 [-16.0, -5.8, 86.0, 16.0, 1.8]]

    # -- the stash: what the boats brought in that the Custom House never saw
    for i in range(16):
        col, row, tier = i % 4, (i // 4) % 2, i // 8
        g.add(P.crate(size=0.68, seed=seed + 600 + i,
                      material=TIMBER_GREY).translate(
            36.0 + col * 1.4, -4.6 + tier * 0.72, 42.0 + row * 1.6))
    for i in range(6):
        g.add(P.barrel(seed=seed + 620 + i).translate(
            44.0, -4.6, 42.0 + i * 1.3))
    for i in range(4):
        g.add(P.sack(seed=seed + 630 + i).translate(
            37.0 + i * 0.9, -4.6, 49.5))
    g.add(M.box((3.0, 0.04, 2.2), center=(41.0, -3.4, 46.0), uv_scale=0.7,
                material=CANVAS))
    it.lamps += [[40.0, -3.0, 46.0, 14.0, 1.7], [37.0, -3.2, 42.0, 12.0, 1.5],
                 [44.0, -3.2, 49.0, 12.0, 1.5]]

    # -- the blowhole: a shaft the sea breathes through, open to the sky -----
    for i in range(20):
        a = math.pi * 2.0 * i / 20.0
        r = 5.4 + float(rng.uniform(-0.6, 0.6))
        g.add(P.boulder(radius=0.7 + float(rng.uniform(0, 0.6)),
                        seed=seed + 650 + i, material=SEA_ROCK).translate(
            math.cos(a) * r, -8.4 + float(rng.uniform(0.0, 9.0)),
            82.0 + math.sin(a) * r))
    g.add(M.box((9.0, 0.06, 9.0), center=(0.0, -7.9, 82.0), uv_scale=0.25,
                material=WATER))
    it.lamps += [[0.0, -5.0, 82.0, 20.0, 1.9], [-3.5, -6.4, 79.0, 15.0, 1.6],
                 [3.5, -6.4, 85.0, 15.0, 1.6]]

    it.spawn_space = "cleft"
    it.open_to_sky.append("blowhole")
    it.subjects = [
        ("cleft", "the cleft down from the watch tower", "cleft"),
        ("tidal-cavern", "the main cavern and its tidal pool", "cavern"),
        ("inner-beach", "shingle, a boat drawn up, a fire", "beach"),
        ("smugglers-ledge", "what the Custom House never saw", "stash"),
        ("blowhole", "the shaft the sea breathes through", "blowhole"),
    ]
    it.landmark("westhaven-undertow-pool", "The Undertow Pool", "cavern", 1.0)
    it.landmark("westhaven-blowhole", "The Gullstone Blowhole", "blowhole", 2.0)
    it.interactives += [
        {"id": "westhaven-smugglers-cache", "name": "Smugglers' Cache",
         "type": "container", "position": [40.0, -4.2, 44.0]},
        {"id": "westhaven-cave-fire", "name": "Beach Fire", "type": "fire",
         "position": [-26.0, -7.2, 78.0]},
    ]
    it.harvestables += [
        {"id": f"westhaven-cave-limpets-{i}", "name": "Cave Limpets",
         "type": "shellfish",
         "position": [round(float(rng.uniform(-20.0, 20.0)), 2), -8.3,
                      round(float(rng.uniform(26.0, 66.0)), 2)]}
        for i in range(5)
    ] + [
        {"id": f"westhaven-driftwood-cave-{i}", "name": "Driftwood",
         "type": "wood",
         "position": [round(float(rng.uniform(-30.0, -12.0)), 2), -7.5,
                      round(float(rng.uniform(76.0, 90.0)), 2)]}
        for i in range(3)
    ]
    it.npc_markers += [
        {"id": "westhaven-free-trader", "name": "Free Trader", "type": "npc",
         "position": [-20.0, -7.6, 80.0]},
    ]
    it.notes = ["No dressed stone and no straight line except a boat's keel "
                "and one timber staging.",
                "Boulders are placed on a radial falloff from the walked "
                "centre line, so the rock is dense at the walls and thin "
                "where the route runs."]
    return it


ALL = {
    "custom_house": custom_house,
    "bonded_vaults": bonded_vaults,
    "lamp_rock_light": lamp_rock_light,
    "gullstone_cave": gullstone_cave,
}


# ==========================================================================
# The combined insides map
# ==========================================================================
# Eternal Lands puts every inside belonging to a region on one map, separated
# by unwalkable void, and sends the player to a different arrival point on that
# map depending on which door was used. Doing the same here means one GLB, one
# manifest and one collision grid instead of four, one server map key instead
# of four, and one blackspace instead of four empty margins.
#
# The blackspace is not drawn and it is not masked. The collision grid is built
# only where a `Walk_` surface exists, so the gutters between sections are
# blocked by construction rather than by a mask that could drift out of step
# with the geometry.
# Laid out two by two rather than in a row. Four sections in a line span
# 350 m of x, which overflows the 384 m of a 64-tile server map once the
# margin a server map wants on every side is allowed for. Measured footprints,
# for the record:
#
#     custom_house      49 x 67      bonded_vaults    53 x 79
#     lamp_rock_light   52 x 89      gullstone_cave   79 x 99
#
# The offsets below leave 45 m between the closest pair and more everywhere
# else, which is what keeps one section's lamps and cameras out of the next.
LAYOUT = {
    "custom_house": (0.0, 0.0),
    "bonded_vaults": (110.0, 0.0),
    "gullstone_cave": (0.0, 140.0),
    "lamp_rock_light": (120.0, 140.0),
}

# Shift the whole assembly clear of the origin so the map sits in positive
# coordinates with a margin on every side, the way a server map is indexed.
# The assembly then spans x 7.5..201.3 and z 21.4..262.5, inside 64 tiles.
LAYOUT_ORIGIN = (40.0, 30.0)


def combine(seed: int = 20260902) -> Interior:
    """Assemble the four interiors onto one map with blackspace between them."""
    combined = Interior("westhaven_insides", "Westhaven Insides", "insides",
                        "custom-house", [-72.0, 9.55, -7.0],
                        "custom-house-hall")
    combined.arrivals = []
    combined.sections = []

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]

        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        def move(position, dx=dx, dz=dz):
            # Keeps any tail past the first three numbers. A lamp may carry its
            # own range and energy - see the note on `it.lamps` in
            # `gullstone_cave` - and dropping them here silently put every lamp
            # in the region back on the 9 m default.
            moved = [round(float(position[0]) + dx, 2), round(float(position[1]), 2),
                     round(float(position[2]) + dz, 2)]
            return moved + [float(v) for v in position[3:]]

        for space_key, space in part.spaces.items():
            combined.spaces[f"{key}.{space_key}"] = {
                "x0": space["x0"] + dx, "x1": space["x1"] + dx,
                "z0": space["z0"] + dz, "z1": space["z1"] + dz,
                "floor": space["floor"], "height": space["height"]}
        for run_key, run in part.passages.items():
            combined.passages[f"{key}.{run_key}"] = {
                "a": (run["a"][0] + dx, run["a"][1] + dz),
                "b": (run["b"][0] + dx, run["b"][1] + dz),
                "y0": run["y0"], "y1": run["y1"],
                "width": run["width"], "height": run["height"]}

        for entry in part.landmarks:
            item = dict(entry)
            item["position"] = move(entry["position"])
            item["space"] = f"{key}.{entry['space']}" if "space" in entry else None
            item["section"] = key
            combined.landmarks.append(item)
        for source, target in ((part.interactives, combined.interactives),
                               (part.harvestables, combined.harvestables),
                               (part.npc_markers, combined.npc_markers)):
            for entry in source:
                item = dict(entry)
                item["position"] = move(entry["position"])
                item["section"] = key
                item["authority"] = "server"
                target.append(item)
        combined.lamps.extend(move(p) for p in part.lamps)
        combined.open_to_sky.extend(f"{key}.{s}" for s in part.open_to_sky)
        for entry in part.subjects:
            ident, subject, space = entry[0], entry[1], entry[2]
            rest = tuple(entry[3:])
            moved = tuple(move(v) for v in rest) if rest else ()
            combined.subjects.append(
                (f"{key}-{ident}", f"{part.name}: {subject}", f"{key}.{space}")
                + moved)

        # the arrival: where a player using this section's surface door lands
        spawn_space = combined.spaces[f"{key}.{part.spawn_space}"]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": f"{key}.{part.spawn_space}", "position": arrival,
            "surfaceLandmark": part.anchor_landmark,
            "surfacePosition": part.anchor_position})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "surfaceLandmark": part.anchor_landmark,
            "spaces": [f"{key}.{s}" for s in part.spaces],
            "notes": part.notes})

    combined.spawn_space = "custom_house.hall"

    # One map, one environment. The four sections carry their own audio, and the
    # two spaces genuinely open to the region's sky stay declared so the client
    # can keep a hole in the roof where they are.
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.13, 0.15, 0.18], "energy": 0.42},
        "fog": {"enabled": True, "colour": [0.06, 0.07, 0.08],
                "begin": 14.0, "end": 48.0},
        "audio": [
            {"id": "quill-and-crowd", "space": "custom_house.ledgers",
             "loop": True},
            {"id": "scale-chain", "space": "custom_house.weighing", "loop": True},
            {"id": "cellar-drip", "space": "bonded_vaults.bay_a", "loop": True},
            {"id": "bilge-slap", "space": "bonded_vaults.sump", "loop": True},
            {"id": "wind-in-glazing", "space": "lamp_rock_light.lantern",
             "loop": True},
            {"id": "gulls-outside", "space": "lamp_rock_light.gallery",
             "loop": True},
            {"id": "surge", "space": "gullstone_cave.cavern", "loop": True},
            {"id": "blowhole-boom", "space": "gullstone_cave.blowhole",
             "loop": True},
        ],
    }
    combined.notes = [
        "Four interiors on one map with blackspace between them, in the Eternal "
        "Lands convention: one GLB, one manifest, one collision grid, one server "
        "map key, and an arrival point per surface door.",
        "The blackspace is not drawn. The collision grid is built only where a "
        "Walk_ surface exists, so the gutters between sections are blocked by "
        "construction rather than by a mask that could drift out of step.",
        "Sections are spaced so no two come within about forty metres, which is "
        "what keeps one section's lamps and cameras out of the next.",
        "No two spaces overlap in plan, in any section. The server collision "
        "grid is 2-D, so a cell carries one height; the Lamp Rock Light is "
        "unfolded rather than stacked for exactly that reason.",
    ]
    return combined


# ---- small rooms (shared kit) ----
# The shared cave / cottage / shrine kit brings three materials the four
# harbour sections never needed.
SR_MATERIALS = frozenset({"bark_dark", "cliff_rock", "pale_ashlar"})
MATERIALS = MATERIALS | SR_MATERIALS
from amberwood import smallrooms as SR


def gullscar_farmhouse(seed: int = 20260905) -> Interior:
    """The farmhouse at Gullscar: a hearth, a loft, and the season's stores."""
    return SR.cottage("westhaven_gullscar_farmhouse", "The Gullscar Farmhouse", "upland-farm",
                      [216.2, 38.2, -255.6], "gullscar-farmhouse-door",
                      palette={"floor": TIMBER, "wall": PLASTER, "roof": TIMBER_DARK,
                               "timber": TIMBER_DARK, "stone": RUBBLE, "cloth": CLOTH,
                               "iron": IRON},
                      seed=seed, trade="hearth")


def haven_undercroft(seed: int = 20260906) -> Interior:
    """Under the Haven Church: the league's own register, and the dead it keeps."""
    return SR.shrine("westhaven_haven_undercroft", "The Haven Undercroft", "cathedral",
                     [59.3, 41.0, -136.1], "haven-undercroft-door",
                     palette={"floor": STONE, "wall": STONE, "ceil": STONE, "accent": CARVED,
                              "metal": IRON, "earth": EARTH},
                     seed=seed, style="lantern", crypt=True)


def salvage_hole(seed: int = 20260907) -> Interior:
    """The cave under the East Watch where salvage goes that the customs never see."""
    return SR.cave("westhaven_salvage_hole", "The Salvage Hole", "east-watch",
                   [319.9, 56.6, -156.2], "salvage-hole-mouth",
                   palette={"floor": EARTH, "rock": "cliff_rock", "water": WATER,
                            "bone": "pale_ashlar"},
                   seed=seed, den="Bronze Tide Crab", pool=True)


ALL.update({"gullscar_farmhouse": gullscar_farmhouse, "haven_undercroft": haven_undercroft,
            "salvage_hole": salvage_hole})
LAYOUT.update({"salvage_hole": (178.0, 6.0), "haven_undercroft": (178.0, 90.0),
               "gullscar_farmhouse": (178.0, 140.0)})
