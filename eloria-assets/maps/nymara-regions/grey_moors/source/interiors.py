"""The four Grey Moor barrow insides, and the combined map they share.

Modelled from the ten-panel interior board at
`interiors/grey_moor_barrows/references/00-concept-detail-board.png`:

    1 barrow entry      6 spike trap
    2 burial gallery    7 root crypt
    3 carved arch       8 flooded ossuary
    4 ritual altar      9 royal tomb
    5 sarcophagus hall 10 peat, stone and bone materials

Four sections, one per surface door, deliberately disjoint so the region does
not have four versions of the same room:

  **The Great Barrow** — the royal one. Dressed megalithic granite, spiral-carved
  jambs, a hall of sarcophagi, and a tomb chamber with a shaft open to the moor
  sky. Panels 1, 3, 5 and 9. Everything here was built to be seen.

  **The Root Crypt** — the counterweight. No dressed stone worth the name: a
  chamber the moor has taken back, with the roots of the Hanged Oak through its
  ceiling and its walls, and earth on the floor. Panel 7.

  **The Bone Gallery** — long, dry, and mean. A corbelled burial gallery lined
  with bone niches, a ritual altar at its head, and a stake-trap corridor that
  is the only part of these barrows built to keep people out rather than in.
  Panels 2, 4 and 6.

  **The Fen Crypt** — drowned. Peat water standing over a sunken ossuary, bones
  in it, and a dry shelf above that is the only footing. Panel 8.

Grounding matters more here than outside, because a player is inside the
geometry: every floor and every step goes through `MeshGroup.add_walk`, and
nothing else does. The water in the Fen Crypt is not a walk surface, and the
shelf around it is.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import moorcraft as MC
from amberwood import stonework as S
from amberwood.interiors import (EYE, Interior, chamber, hanging_lamps,
                                 passage, root_ribs)
from amberwood.noise import Rng

# The palette. Deliberately narrow, and shared with the surface region so a
# barrow reads as the inside of the mound the player just walked over.
GRANITE = "grey_moor_granite"
CARVED = "grey_carved_stone"
DRYSTONE = "grey_drystone"
TIMBER = "grey_bog_timber"
BARK = "grey_dead_bark"
BONE = "grey_bone"
EARTH = "packed_earth"
PEAT = "grey_peat_bog"
WATER = "grey_bog_water"
FLAME = "grey_votive_flame"
IRON = "dark_iron"
ROCK = "cliff_rock"
RUBBLE = "rubble_stone"


def _candles(interior: Interior, points, seed: int = 0) -> None:
    """Votive candles, and a lamp record so the client can light from them.

    The barrows are lit by candlelight in every panel of the board, and the
    package ships no KHR_lights_punctual, so the flame is emissive geometry and
    the manifest carries the positions separately.
    """
    for index, (x, y, z) in enumerate(points):
        piece = MC.candle_cluster(3 + index % 3, 0.55, seed=seed + index * 17)
        piece.translate(x, y, z)
        interior.group.add(piece)
        interior.lamps.append([round(x, 2), round(y + 0.4, 2), round(z, 2)])


def _sarcophagus(length: float = 2.4, width: float = 1.05, seed: int = 0,
                 lid_ajar: bool = False) -> S.MeshGroup:
    """A stone tomb chest. Panels 5 and 9 are full of them."""
    rng = Rng(seed)
    parts = []
    body = M.box((length, 0.86, width), uv_scale=0.7, material=GRANITE)
    body.translate(0.0, 0.43, 0.0)
    parts.append(body)
    plinth = M.box((length + 0.30, 0.18, width + 0.30), uv_scale=0.7,
                   material=GRANITE)
    plinth.translate(0.0, 0.09, 0.0)
    parts.append(plinth)
    lid = M.box((length + 0.14, 0.22, width + 0.14), uv_scale=0.6, material=CARVED)
    if lid_ajar:
        lid.transform(M.rotation_y(0.09))
        lid.translate(length * 0.16, 0.97, width * 0.22)
    else:
        lid.translate(0.0, 0.97, 0.0)
    parts.append(lid)
    return S.group(MC._weather(M.merge(parts, GRANITE), 0.008, seed + 3))


def _bone_niche(width: float = 1.1, height: float = 0.8, depth: float = 0.7,
                seed: int = 0) -> S.MeshGroup:
    """A loculus with bones stacked in it. The gallery walls of panel 2."""
    rng = Rng(seed)
    out = S.MeshGroup()
    # the recess is a dark box; the bones sit in its mouth
    recess = M.box((width, height, depth), uv_scale=1.0, material="charred_timber")
    recess.translate(0.0, height * 0.5, -depth * 0.35)
    out.add(recess)
    for index in range(4 + int(rng.uniform() * 4)):
        long_bone = M.cylinder(0.055, 0.048, width * (0.62 + rng.uniform() * 0.26),
                               6, uv_scale=1.6, material=BONE)
        long_bone.transform(M.rotation_z(math.pi * 0.5))
        long_bone.transform(M.rotation_y((rng.uniform() - 0.5) * 0.25))
        long_bone.translate((rng.uniform() - 0.5) * 0.10,
                            0.09 + index * 0.115,
                            -depth * 0.18 + (rng.uniform() - 0.5) * 0.12)
        out.add(long_bone)
    if rng.uniform() < 0.6:
        skull = M.icosphere(0.115, 1, material=BONE)
        skull.translate(width * 0.26, 0.11 + 0.115 * 4.4, -depth * 0.2)
        out.add(skull)
    return out


def _standing_pair(span: float, height: float, seed: int = 0) -> S.MeshGroup:
    """Two menhirs brought inside and stood either side of something."""
    out = S.MeshGroup()
    for index, side in enumerate((-1.0, 1.0)):
        stone = MC.menhir(height, seed + index * 13)
        stone.translate(side * span * 0.5, 0.0, 0.0)
        out.add(stone)
    return out


def _spiral_jambs(width: float, height: float, seed: int = 0) -> S.MeshGroup:
    """The carved arch of panel 3: two spiral-cut uprights under a lintel."""
    out = S.MeshGroup()
    thickness = 0.72
    for side in (-1.0, 1.0):
        jamb = M.box((thickness, height, 0.95), uv_scale=0.6, material=CARVED)
        jamb.translate(side * (width * 0.5 + thickness * 0.5), height * 0.5, 0.0)
        out.add(jamb)
    lintel = M.box((width + thickness * 2.6, height * 0.26, 1.05), uv_scale=0.55,
                   material=CARVED)
    lintel.translate(0.0, height + height * 0.13, 0.0)
    out.add(lintel)
    return out


# --------------------------------------------------------------------------
# 1. The Great Barrow
# --------------------------------------------------------------------------

def great_barrow(seed: int = 20260902) -> Interior:
    """The royal barrow: entry, carved arch, sarcophagus hall, tomb chamber."""
    it = Interior("great_barrow", "The Great Barrow", "tomb",
                  "grey-great-barrow", [114.0, 6.4, -273.0], "great-barrow-mouth")
    rng = Rng(seed)

    # -- the entry, just inside the lintel of panel 1
    it.space("entry", 0.0, 0.0, 9.0, 7.0, 0.0, 3.2,
             floor_mat=GRANITE, wall_mat=DRYSTONE, ceil_mat=GRANITE,
             doors=(("north", 4.5, 2.0, 2.6),), seed=seed)
    it.spawn_space = "entry"

    # -- the dromos: a long corbelled passage running north
    it.group.add(passage(4.5, 7.0, 4.5, 24.0, 3.2, 0.0, -1.4, 3.0,
                         floor_mat=GRANITE, wall_mat=DRYSTONE, ceil_mat=GRANITE,
                         steps=7, seed=seed + 1))
    it.passages["dromos"] = {"a": (4.5, 7.0), "b": (4.5, 24.0), "y0": 0.0,
                             "y1": -1.4, "width": 3.2, "height": 3.0}

    # -- the carved arch (panel 3), standing in the passage mouth
    arch = _spiral_jambs(2.6, 3.0, seed + 5)
    arch.translate(4.5, -1.4, 24.2)
    it.group.add(arch)

    # -- the hall of sarcophagi (panel 5)
    it.space("hall", -3.0, 25.0, 12.0, 44.0, -1.4, 5.2,
             floor_mat=GRANITE, wall_mat=CARVED, ceil_mat=GRANITE,
             doors=(("south", 4.5, 2.6, 3.0), ("north", 4.5, 2.4, 3.0)),
             ceiling="vault", vault_rise=2.4, seed=seed + 2)
    for index in range(8):
        row, column = divmod(index, 2)
        box = _sarcophagus(2.4, 1.05, seed + 40 + index,
                           lid_ajar=index in (3, 6))
        box.translate(-0.4 + column * 9.6, -1.4, 28.0 + row * 4.2)
        it.group.add(box)
    # the colonnade the panel puts down both sides
    for index in range(8):
        side = -1.0 if index % 2 == 0 else 1.0
        column = M.box((0.9, 5.2, 0.9), uv_scale=0.6, material=GRANITE)
        column.translate(4.5 + side * 6.4, -1.4 + 2.6, 27.0 + (index // 2) * 4.6)
        it.group.add(column)

    # -- the royal tomb (panel 9): raised sarcophagus under a shaft
    it.space("tomb", -1.0, 45.0, 10.0, 58.0, -1.4, 7.0,
             floor_mat=GRANITE, wall_mat=CARVED, ceil_mat=GRANITE,
             doors=(("south", 4.5, 2.4, 3.0),), seed=seed + 3)
    dais = M.box((6.0, 0.90, 5.0), uv_scale=0.5, material=CARVED)
    dais.translate(4.5, -0.95, 51.5)
    it.group.add_walk(dais)
    steps = M.stairs(6.0, 0.30, 0.5, 3, uv_scale=0.6, material=GRANITE)
    steps.transform(M.rotation_y(math.pi))
    steps.translate(4.5, -1.4, 47.6)
    it.group.add_walk(steps)
    royal = _sarcophagus(2.9, 1.3, seed + 71)
    royal.translate(4.5, -0.50, 51.5)
    it.group.add(royal)
    it.group.add(_standing_pair(6.6, 3.6, seed + 73).translate(4.5, -0.50, 54.4))
    # the shaft: this tomb is open to the moor above, which is where the light
    # in panel 9 comes from. Declared, so the client can keep a hole in the lid.
    it.open_to_sky.append("tomb")

    _candles(it, [(2.2, 0.0, 3.0), (6.8, 0.0, 3.0),
                  (3.0, -1.4, 26.5), (6.0, -1.4, 26.5),
                  (-1.6, -1.4, 33.0), (10.6, -1.4, 33.0),
                  (-1.6, -1.4, 41.0), (10.6, -1.4, 41.0),
                  (1.4, -1.4, 47.5), (7.6, -1.4, 47.5),
                  (2.0, -0.05, 51.0), (7.0, -0.05, 51.0)], seed + 90)

    it.landmark("grey-barrow-arch", "The Carved Arch", "hall", y_offset=1.6)
    it.landmark("grey-barrow-sarcophagi", "The Hall of Sarcophagi", "hall",
                y_offset=1.2)
    it.landmark("grey-barrow-royal", "The Royal Tomb", "tomb", y_offset=1.4)
    it.interactives.append({
        "id": "grey-royal-sarcophagus", "name": "Royal Sarcophagus",
        "type": "container", "position": [4.5, -0.05, 51.5],
        "authority": "server"})

    it.subjects = [
        ("entry", "barrow entry, from inside the lintel", "entry"),
        ("arch", "the spiral-carved arch", "hall"),
        ("sarcophagi", "the hall of sarcophagi", "hall"),
        ("royal", "the royal tomb under its shaft", "tomb"),
    ]
    it.notes = [
        "The only section built to be looked at: dressed granite, spiral "
        "carving, a colonnade and a raised dais.",
        "The tomb chamber is declared open_to_sky. A combined insides map has "
        "one environment, so the shaft will not currently show sky.",
    ]
    return it


# --------------------------------------------------------------------------
# 2. The Root Crypt
# --------------------------------------------------------------------------

def root_crypt(seed: int = 20260903) -> Interior:
    """Panel 7: a crypt the moor has taken back, roots through the roof."""
    it = Interior("root_crypt", "The Root Crypt", "crypt",
                  "grey-crypt-west", [-90.0, 4.2, -252.0], "west-crypt-stair")

    # -- the stair down from the surface door
    it.space("stairhead", 0.0, 0.0, 6.0, 5.5, 0.0, 3.0,
             floor_mat=DRYSTONE, wall_mat=DRYSTONE, ceil_mat=RUBBLE,
             doors=(("north", 3.0, 1.8, 2.5),), seed=seed)
    it.spawn_space = "stairhead"
    it.group.add(passage(3.0, 5.5, 3.0, 15.0, 2.6, 0.0, -3.4, 2.8,
                         floor_mat=DRYSTONE, wall_mat=EARTH, ceil_mat=EARTH,
                         steps=10, seed=seed + 1))
    it.passages["descent"] = {"a": (3.0, 5.5), "b": (3.0, 15.0), "y0": 0.0,
                              "y1": -3.4, "width": 2.6, "height": 2.8}

    # -- the rootfall: the chamber of the panel
    it.space("rootfall", -6.0, 16.0, 12.0, 32.0, -3.4, 6.4,
             floor_mat=EARTH, wall_mat=RUBBLE, ceil_mat=EARTH,
             doors=(("south", 3.0, 2.4, 2.8), ("east", 24.0, 2.2, 2.6)),
             seed=seed + 2)
    # the toolkit already grows root ribs; this is what they are for
    it.group.add(root_ribs(-5.0, 17.0, 11.0, 31.0, -3.4, -3.4, 15.0, 6.2,
                           material=BARK, seed=seed + 11))
    # a fallen kerb and spill of rubble where the roots pushed the wall in
    rng = Rng(seed + 21)
    for index in range(14):
        block = M.box((0.7 + rng.uniform() * 0.4, 0.32, 0.5 + rng.uniform() * 0.3),
                      uv_scale=1.1, material=DRYSTONE)
        block.transform(M.rotation_y(rng.uniform() * math.tau))
        block.transform(M.rotation_z((rng.uniform() - 0.5) * 0.5))
        block.translate(-4.0 + rng.uniform() * 14.0, -3.2,
                        17.5 + rng.uniform() * 13.0)
        it.group.add(block)
    # two sarcophagi, both broken open by the roots
    for index, (x, z) in enumerate(((-2.0, 22.0), (8.0, 27.0))):
        box = _sarcophagus(2.4, 1.05, seed + 60 + index, lid_ajar=True)
        box.translate(x, -3.4, z)
        it.group.add(box)

    # -- a lower gallery, half filled with earth
    it.group.add(passage(12.0, 24.0, 22.0, 24.0, 2.4, -3.4, -4.2, 2.5,
                         floor_mat=EARTH, wall_mat=EARTH, ceil_mat=EARTH,
                         steps=3, seed=seed + 3))
    it.passages["undergallery"] = {"a": (12.0, 24.0), "b": (22.0, 24.0),
                                   "y0": -3.4, "y1": -4.2, "width": 2.4,
                                   "height": 2.5}
    it.space("underchamber", 22.0, 19.0, 32.0, 29.0, -4.2, 4.0,
             floor_mat=EARTH, wall_mat=RUBBLE, ceil_mat=EARTH,
             doors=(("west", 24.0, 2.2, 2.5),), seed=seed + 4)
    it.group.add(root_ribs(23.0, 20.0, 31.0, 28.0, -4.2, -4.2, 8.0, 3.8,
                           material=BARK, seed=seed + 31))

    _candles(it, [(1.2, 0.0, 2.4), (4.8, 0.0, 2.4),
                  (-4.4, -3.4, 19.0), (10.4, -3.4, 19.0),
                  (-4.4, -3.4, 29.0), (10.4, -3.4, 29.0),
                  (24.0, -4.2, 21.0), (30.0, -4.2, 27.0)], seed + 90)

    it.landmark("grey-root-crypt", "The Root Crypt", "rootfall", y_offset=1.6)
    it.landmark("grey-root-underchamber", "The Under Chamber", "underchamber",
                y_offset=1.2)
    it.harvestables.append({
        "id": "grey-crypt-heartroot", "resource": "heartroot",
        "position": [3.0, -3.3, 24.0], "authority": "server"})

    it.subjects = [
        ("rootfall", "roots through the crypt roof", "rootfall"),
        ("underchamber", "the under chamber", "underchamber"),
    ]
    it.notes = [
        "The counterweight to the Great Barrow: no dressed stone, earth floors, "
        "and the roots of the moor's dead trees through the roof.",
        "Root geometry comes from the toolkit's own `root_ribs`, which is what "
        "it was written for.",
    ]
    return it


# --------------------------------------------------------------------------
# 3. The Bone Gallery
# --------------------------------------------------------------------------

def bone_gallery(seed: int = 20260904) -> Interior:
    """Panels 2, 4 and 6: a corbelled gallery of bone niches, altar, stake trap."""
    it = Interior("bone_gallery", "The Bone Gallery", "ossuary",
                  "grey-crypt-east", [288.0, 5.1, -198.0], "east-crypt-stair")

    it.space("stairhead", 0.0, 0.0, 6.0, 5.0, 0.0, 3.0,
             floor_mat=DRYSTONE, wall_mat=DRYSTONE, ceil_mat=GRANITE,
             doors=(("north", 3.0, 1.8, 2.5),), seed=seed)
    it.spawn_space = "stairhead"

    # -- the burial gallery of panel 2: long, narrow, candles down both sides
    it.group.add(passage(3.0, 5.0, 3.0, 12.0, 2.6, 0.0, -2.0, 2.9,
                         floor_mat=GRANITE, wall_mat=DRYSTONE, ceil_mat=GRANITE,
                         steps=6, seed=seed + 1))
    it.passages["descent"] = {"a": (3.0, 5.0), "b": (3.0, 12.0), "y0": 0.0,
                              "y1": -2.0, "width": 2.6, "height": 2.9}
    it.space("gallery", -1.0, 13.0, 7.0, 46.0, -2.0, 4.2,
             floor_mat=GRANITE, wall_mat=DRYSTONE, ceil_mat=GRANITE,
             doors=(("south", 3.0, 2.4, 2.8), ("north", 3.0, 2.2, 2.6)),
             ceiling="vault", vault_rise=1.6, seed=seed + 2)
    # niches down both walls, which is what makes it a gallery and not a corridor
    for index in range(16):
        side = -1.0 if index % 2 == 0 else 1.0
        z = 15.0 + (index // 2) * 3.9
        for tier in range(2):
            niche = _bone_niche(1.1, 0.8, 0.7, seed + 200 + index * 3 + tier)
            niche.transform(M.rotation_y(math.pi * 0.5 * side))
            niche.translate(3.0 + side * 3.85, -2.0 + 0.35 + tier * 1.25, z)
            it.group.add(niche)

    # -- the ritual altar of panel 4, at the head of the gallery
    it.space("altar", -4.0, 47.0, 10.0, 58.0, -2.0, 5.0,
             floor_mat=GRANITE, wall_mat=CARVED, ceil_mat=GRANITE,
             doors=(("south", 3.0, 2.2, 2.6), ("east", 58.0, 2.0, 2.4)),
             seed=seed + 3)
    slab = MC.altar_slab(seed + 61, span=3.0)
    slab.translate(3.0, -2.0, 53.0)
    it.group.add(slab)
    it.group.add(_standing_pair(5.6, 3.4, seed + 63).translate(3.0, -2.0, 53.0))
    # offerings on the slab: bowls and bone, as the panel has them
    rng = Rng(seed + 71)
    for index in range(7):
        bowl = M.lathe([[0.0, 0.0], [0.16, 0.02], [0.19, 0.13], [0.13, 0.15]],
                       10, uv_scale=1.4, material=IRON)
        bowl.translate(3.0 + (rng.uniform() - 0.5) * 2.2, -1.32,
                       53.0 + (rng.uniform() - 0.5) * 1.5)
        it.group.add(bowl)

    # -- the stake trap of panel 6: the one corridor built to keep people out
    it.group.add(passage(10.0, 52.5, 24.0, 52.5, 2.6, -2.0, -2.0, 2.7,
                         floor_mat=PEAT, wall_mat=RUBBLE, ceil_mat=RUBBLE,
                         seed=seed + 4))
    it.passages["trap"] = {"a": (10.0, 52.5), "b": (24.0, 52.5), "y0": -2.0,
                           "y1": -2.0, "width": 2.6, "height": 2.7}
    rng = Rng(seed + 81)
    for index in range(34):
        stake = M.cylinder(0.075, 0.012, 0.9 + rng.uniform() * 0.7, 5,
                           uv_scale=1.6, material=TIMBER)
        lean = (rng.uniform() - 0.5) * 0.7
        stake.transform(M.rotation_z(lean))
        stake.transform(M.rotation_x((rng.uniform() - 0.5) * 0.5))
        stake.translate(11.0 + rng.uniform() * 12.0, -2.0,
                        52.5 + (rng.uniform() - 0.5) * 2.0)
        it.group.add(stake)
    it.space("trapcell", 24.0, 48.5, 32.0, 56.5, -2.0, 3.6,
             floor_mat=PEAT, wall_mat=RUBBLE, ceil_mat=RUBBLE,
             doors=(("west", 52.5, 2.2, 2.5),), seed=seed + 5)
    # The cell the corridor delivers into: more stakes, and what is left of
    # whoever came down it before. An empty room at the end of a trap corridor
    # is not a trap, it is a corridor.
    rng = Rng(seed + 91)
    for index in range(26):
        stake = M.cylinder(0.08, 0.014, 1.0 + rng.uniform() * 0.9, 5,
                           uv_scale=1.6, material=TIMBER)
        stake.transform(M.rotation_z((rng.uniform() - 0.5) * 0.6))
        stake.transform(M.rotation_x((rng.uniform() - 0.5) * 0.6))
        stake.translate(25.0 + rng.uniform() * 6.0, -2.0,
                        49.5 + rng.uniform() * 6.0)
        it.group.add(stake)
    for index in range(16):
        bone = M.cylinder(0.05, 0.042, 0.32 + rng.uniform() * 0.36, 5,
                          uv_scale=1.8, material=BONE)
        bone.transform(M.rotation_z(math.pi * 0.5))
        bone.transform(M.rotation_y(rng.uniform() * math.tau))
        bone.translate(25.0 + rng.uniform() * 6.0, -1.92,
                       49.5 + rng.uniform() * 6.0)
        it.group.add(bone)
    for index in range(3):
        skull = M.icosphere(0.115, 1, material=BONE)
        skull.translate(26.0 + rng.uniform() * 4.5, -1.88,
                        50.5 + rng.uniform() * 4.5)
        it.group.add(skull)

    _candles(it, [(1.2, 0.0, 2.2), (4.8, 0.0, 2.2),
                  (0.2, -2.0, 18.0), (5.8, -2.0, 18.0),
                  (0.2, -2.0, 27.0), (5.8, -2.0, 27.0),
                  (0.2, -2.0, 36.0), (5.8, -2.0, 36.0),
                  (0.6, -2.0, 50.0), (5.4, -2.0, 50.0),
                  (3.0, -1.30, 55.4), (26.5, -2.0, 50.5)], seed + 90)

    it.landmark("grey-bone-gallery", "The Bone Gallery", "gallery", y_offset=1.4)
    it.landmark("grey-bone-altar", "The Ritual Altar", "altar", y_offset=1.2)
    it.landmark("grey-bone-trap", "The Stake Passage", "trapcell", y_offset=1.2)
    it.interactives.append({
        "id": "grey-gallery-altar", "name": "Ritual Altar", "type": "altar",
        "position": [3.0, -1.30, 53.0], "authority": "server"})

    it.subjects = [
        ("gallery", "the burial gallery", "gallery"),
        ("altar", "the ritual altar", "altar"),
        ("trap", "the stake passage", "trapcell"),
    ]
    it.notes = [
        "Dry, long and mean. The niches are what make it a gallery rather than "
        "a corridor with candles in it.",
        "The stake corridor is the only part of these barrows built to keep "
        "people out. It is walkable: the stakes are geometry, not collision, "
        "and the trap is the server's to run.",
    ]
    return it


# --------------------------------------------------------------------------
# 4. The Fen Crypt
# --------------------------------------------------------------------------

def fen_crypt(seed: int = 20260905) -> Interior:
    """Panel 8: a drowned ossuary, standing peat water over the bones."""
    it = Interior("fen_crypt", "The Fen Crypt", "flooded",
                  "grey-crypt-south", [102.0, 3.3, -18.0], "south-crypt-stair")

    it.space("stairhead", 0.0, 0.0, 6.0, 5.0, 0.0, 3.0,
             floor_mat=DRYSTONE, wall_mat=DRYSTONE, ceil_mat=RUBBLE,
             doors=(("north", 3.0, 1.8, 2.5),), seed=seed)
    it.spawn_space = "stairhead"
    it.group.add(passage(3.0, 5.0, 3.0, 16.0, 2.6, 0.0, -3.0, 2.8,
                         floor_mat=DRYSTONE, wall_mat=RUBBLE, ceil_mat=RUBBLE,
                         steps=9, seed=seed + 1))
    it.passages["descent"] = {"a": (3.0, 5.0), "b": (3.0, 16.0), "y0": 0.0,
                              "y1": -3.0, "width": 2.6, "height": 2.8}

    # -- the ossuary. Its floor is BELOW the water; the walkable part is the
    #    shelf around it, so a player walks the edge and looks into the pool.
    # `interiors.chamber` always makes its floor a walk surface, so a floor
    # 1.6 m under the water would have been drowned and walkable at once. The
    # water is shin-deep instead: the shelf is a step up out of it, the drowned
    # floor is waded, and both statements are true of the same geometry.
    water_level = -3.0
    floor_level = -3.6
    it.space("ossuary", -8.0, 17.0, 16.0, 40.0, floor_level, 7.2,
             floor_mat=PEAT, wall_mat=ROCK, ceil_mat=ROCK,
             doors=(("south", 3.0, 2.4, 2.8),), ceiling="vault",
             vault_rise=2.6, seed=seed + 2)

    # the dry shelf: a walkable ledge running round three sides at water height
    for x0, z0, x1, z1 in ((-8.0, 17.0, -3.4, 40.0),
                           (11.4, 17.0, 16.0, 40.0),
                           (-3.4, 35.6, 11.4, 40.0)):
        shelf = M.box((x1 - x0, 0.5, z1 - z0),
                      center=((x0 + x1) * 0.5, water_level - 0.25,
                              (z0 + z1) * 0.5),
                      uv_scale=0.4, material=DRYSTONE)
        it.group.add_walk(shelf)
    # steps down from the passage onto the shelf
    landing = M.box((3.4, 0.5, 2.2), center=(3.0, water_level - 0.25, 18.2),
                    uv_scale=0.4, material=DRYSTONE)
    it.group.add_walk(landing)
    causeway = M.box((3.0, 0.5, 18.0), center=(3.0, water_level - 0.25, 27.5),
                     uv_scale=0.4, material=DRYSTONE)
    it.group.add_walk(causeway)

    # the water itself, sitting between shelf and causeway. NOT a walk surface.
    for x0, x1 in ((-3.4, 1.5), (4.5, 11.4)):
        skin = M.box((x1 - x0, 0.10, 18.4),
                     center=((x0 + x1) * 0.5, water_level, 26.6),
                     uv_scale=0.35, material=WATER)
        it.group.add(skin)

    # pillars standing in the water, as the panel has them
    for index in range(6):
        side = -1.0 if index % 2 == 0 else 1.0
        pillar = M.box((1.0, 5.6, 1.0), uv_scale=0.6, material=ROCK)
        pillar.translate(3.0 + side * 5.4, floor_level + 2.8,
                         20.0 + (index // 2) * 6.4)
        it.group.add(pillar)

    # bones on the drowned floor and heaped against the shelf
    rng = Rng(seed + 41)
    for index in range(40):
        bone = M.cylinder(0.05, 0.042, 0.35 + rng.uniform() * 0.4, 5,
                          uv_scale=1.8, material=BONE)
        bone.transform(M.rotation_z(math.pi * 0.5))
        bone.transform(M.rotation_y(rng.uniform() * math.tau))
        bone.translate(3.0 + (rng.uniform() - 0.5) * 13.0, floor_level + 0.08,
                       19.0 + rng.uniform() * 19.0)
        it.group.add(bone)
    for index in range(9):
        skull = M.icosphere(0.115, 1, material=BONE)
        skull.translate(3.0 + (rng.uniform() - 0.5) * 12.0, floor_level + 0.12,
                        19.0 + rng.uniform() * 19.0)
        it.group.add(skull)

    # a sunken sarcophagus, lid off, half in the water
    box = _sarcophagus(2.6, 1.15, seed + 63, lid_ajar=True)
    box.translate(3.0, floor_level, 33.0)
    it.group.add(box)

    _candles(it, [(1.2, 0.0, 2.2), (4.8, 0.0, 2.2),
                  (-5.6, water_level, 20.0), (13.6, water_level, 20.0),
                  (-5.6, water_level, 30.0), (13.6, water_level, 30.0),
                  (0.0, water_level, 37.6), (6.0, water_level, 37.6)], seed + 90)

    it.landmark("grey-fen-ossuary", "The Flooded Ossuary", "ossuary", y_offset=1.2)
    it.harvestables.append({
        "id": "grey-fen-bonemeal", "resource": "bone-meal",
        "position": [3.0, water_level + 0.1, 36.0], "authority": "server"})

    it.subjects = [
        ("ossuary", "the flooded ossuary", "ossuary"),
    ]
    it.notes = [
        "Shin-deep standing water over the ossuary floor, with a drystone "
        "shelf and a causeway a step up out of it. The floor is waded rather "
        "than blocked, because the toolkit's chamber floor is always a walk "
        "surface and a drowned-but-walkable floor would have been a lie.",
        "Bog water here is the region's own opaque `grey_bog_water`, not a "
        "transparent lake: peat stain kills the light that enters it.",
    ]
    return it


ALL = {
    "great_barrow": great_barrow,
    "root_crypt": root_crypt,
    "bone_gallery": bone_gallery,
    "fen_crypt": fen_crypt,
}


# --------------------------------------------------------------------------
# The combined insides map
# --------------------------------------------------------------------------
# Eternal Lands puts every inside belonging to a region on one map, separated by
# unwalkable void, and sends the player to a different arrival point on that map
# depending on which door was used. Doing the same here means one GLB, one
# manifest and one collision grid instead of four, one server map key instead of
# four, and one load rather than a load per doorway.
#
# The blackspace falls out of the construction rather than being drawn: the
# collision grid is built only where a Walk_ surface exists, so the gutters
# between the four are already blocked, and nothing is rendered there either.
#
# Offsets are chosen from each section's measured footprint so no two come
# within about forty metres. That gap is what keeps one section's candles and
# cameras out of the next.
LAYOUT = {
    "great_barrow": (0.0, 0.0),      # 15 x 58
    "root_crypt": (95.0, 0.0),       # 38 x 32
    "bone_gallery": (0.0, 105.0),    # 36 x 58
    "fen_crypt": (95.0, 105.0),      # 24 x 40
}

# Shift the whole assembly clear of the origin so the map sits in positive
# coordinates with a margin on every side, the way a server map is indexed.
LAYOUT_ORIGIN = (40.0, 36.0)


def combine(seed: int = 20260902) -> Interior:
    """Assemble the four barrows onto one map with blackspace between them."""
    combined = Interior("grey_moors_insides", "Grey Moor Barrows", "insides",
                        "grey-great-barrow", [114.0, 6.4, -273.0],
                        "great-barrow-mouth")
    combined.arrivals = []
    combined.sections = []

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]

        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        def move(position, dx=dx, dz=dz):
            return [round(float(position[0]) + dx, 2), round(float(position[1]), 2),
                    round(float(position[2]) + dz, 2)]

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
                target.append(item)
        combined.lamps.extend(move(p) for p in part.lamps)
        combined.open_to_sky.extend(f"{key}.{s}" for s in part.open_to_sky)
        for entry in part.subjects:
            ident, subject, space = entry[0], entry[1], entry[2]
            rest = tuple(entry[3:])
            moved = tuple(move(v) for v in rest) if rest else ()
            combined.subjects.append(
                (f"{key}-{ident}", f"{part.name}: {subject}", f"{key}.{space}") + moved)

        # the arrival: where a player using this section's surface door lands
        spawn_space = combined.spaces[f"{key}.{part.spawn_space}"]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": f"{key}.{part.spawn_space}", "position": arrival,
            "returnsTo": part.anchor_landmark})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "spaces": [f"{key}.{s}" for s in part.spaces],
            "notes": part.notes})

    combined.spawn_space = "great_barrow.entry"

    # One map, one environment: candlelight in stone, and nothing else.
    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.10, 0.10, 0.09], "energy": 0.30},
        "fog": {"enabled": True, "colour": [0.04, 0.04, 0.04],
                "begin": 12.0, "end": 46.0},
        "audio": [
            {"id": "drip", "space": "great_barrow.hall", "loop": True},
            {"id": "low-chant", "space": "great_barrow.tomb", "loop": True},
            {"id": "root-creak", "space": "root_crypt.rootfall", "loop": True},
            {"id": "bone-settle", "space": "bone_gallery.gallery", "loop": True},
            {"id": "water-lap", "space": "fen_crypt.ossuary", "loop": True},
        ],
    }
    combined.notes = [
        "Four barrows on one map with blackspace between them, in the Eternal "
        "Lands convention: one GLB, one manifest, one collision grid, one "
        "server map key, and an arrival point per surface door.",
        "The blackspace is not drawn. The collision grid is built only where a "
        "Walk_ surface exists, so the gutters between sections are blocked by "
        "construction rather than by a mask that could drift out of step.",
        "Sections are spaced so no two come within about forty metres, which is "
        "what keeps one section's candles and cameras out of the next.",
    ]
    return combined


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def fifth_chamber(seed: int = 20260905) -> Interior:
    """The chamber the barrow count is one short by: a wolf den under a broken tower."""
    return SR.cave("grey_fifth_chamber", "The Fifth Chamber", "grey-tower-3",
                   [378.0, 5.6, -189.0], "fifth-chamber-mouth",
                   palette={"floor": EARTH, "rock": ROCK, "water": WATER, "bone": BONE},
                   seed=seed, den="Moorland Dire Wolf", pool=True)


def peat_croft(seed: int = 20260906) -> Interior:
    """A croft somebody still keeps, between the cuttings."""
    return SR.cottage("grey_peat_croft", "The Peat Cutter's Croft", "grey-croft-1",
                      [120.0, 4.7, 78.0], "peat-croft-door",
                      palette={"floor": TIMBER, "wall": DRYSTONE, "roof": "grey_turf_roof",
                               "timber": TIMBER, "stone": GRANITE, "cloth": "woven_cloth",
                               "iron": IRON},
                      seed=seed, trade="hearth")


def warm_stone(seed: int = 20260907) -> Interior:
    """The shrine whose stone is warm to the hand, and the niches under it."""
    return SR.shrine("grey_warm_stone", "The Warm Stone", "grey-shrine-0",
                     [114.0, 4.8, -222.0], "warm-stone-door",
                     palette={"floor": GRANITE, "wall": DRYSTONE, "ceil": GRANITE,
                              "accent": CARVED, "earth": EARTH, "metal": IRON},
                     seed=seed, style="stone", crypt=True)


ALL.update({"fifth_chamber": fifth_chamber, "peat_croft": peat_croft,
            "warm_stone": warm_stone})
LAYOUT.update({"fifth_chamber": (161.0, 6.0), "warm_stone": (161.0, 90.0),
               "peat_croft": (161.0, 140.0)})
