"""Westhaven's architectural kit: the pieces a working port is made of.

Same reasoning as `havenkit.py` for why this is here and not in `_toolkit/`:
every piece is a plain `MeshGroup` factory with the same shape as everything in
`stonework.py` and `architecture.py`, so promoting it is a move rather than a
rewrite, but four unfinished regions are queued to append to those modules and
this avoids the conflict.

The shared kit already covers a great deal - `stonework.column`, `balustrade`,
`retaining_wall`, `ancient_arch`, `high_bridge`, `lamp_post`, `rotunda`,
`architecture.roof`, `framed_wall`, `window`, `watchtower`, `manor`, and the
whole of `props` - and this module uses all of it. What it adds is the things a
harbour has that a forest and a lagoon city do not: a quay wall, a breakwater
mole, a timber pier on piles, a cargo crane, a ship, a ship on the stocks, and
a lighthouse.

WALK SURFACES
-------------
Every piece that a character can stand on registers that geometry through
`MeshGroup.add_walk`, and nothing else. The client turns node names matching
`navigation.surfaceNodePrefixes` into the layer its grounding ray tests, so a
whole landmark marked walkable snaps actors onto its roof. Quay aprons, pier
decks, the mole deck and the bastion platform are walk surfaces; walls, roofs,
hulls, jibs and rigging are not.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as P
from amberwood import stonework as SW

import havenkit as HK

STONE = "ashlar"
RUBBLE = "rubble_stone"
SEA_ROCK = HK.SEA_ROCK
SETT = HK.SETT
PLANK = HK.PLANK
TIMBER = "timber_warm"
TIMBER_GREY = "timber_grey"
TIMBER_DARK = "timber_dark"
CARVED = "carved_wood"
IRON = "dark_iron"
BRASS = HK.BRASS
ROOF = HK.PANTILE
SAIL = HK.SAILCLOTH
PLASTER = "lime_plaster"
CANVAS = "canvas_awning"
CLOTH = "woven_cloth"
GLASS = "amber_resin"


def at(x: float, y: float, z: float, yaw: float = 0.0,
       pitch: float = 0.0, roll: float = 0.0):
    """Place a piece: rotate it about its own origin, then move it.

    Matrix composition here is `A @ B` applied as A(B(v)), so
    `rotation @ translation` rotates the *already moved* piece about the world
    origin and flings it somewhere else on a circle. That is not "put it there
    facing that way", and it is the bug this helper exists to stop repeating:
    the crane's treadwheels ended up below the quay, the bastion's merlons
    bunched at double their intended angle, and the pier rails swapped their X
    and Z. Nothing in the shared toolkit ever writes that order.
    """
    matrix = M.translation(x, y, z)
    if yaw:
        matrix = matrix @ M.rotation_y(yaw)
    if pitch:
        matrix = matrix @ M.rotation_x(pitch)
    if roll:
        matrix = matrix @ M.rotation_z(roll)
    return matrix


def _jitter(seed: int, index: int, spread: float) -> float:
    """Deterministic small offset. `stable_hash`, never the builtin `hash`."""
    return (N.stable_hash(f"{seed}:{index}") % 1000 / 1000.0 - 0.5) * 2.0 * spread


# --------------------------------------------------------------- the water edge
def quay_wall(length: float, height: float = 4.0, thickness: float = 1.6,
              seed: int = 0, rings: bool = True) -> SW.MeshGroup:
    """A masonry harbour edge: battered face, projecting cope, mooring rings.

    Built along +X with its face on -Z and its top at y = 0, so a caller places
    it at the quay level and the wall hangs down into the water. That is the
    right way round for a quay: the deck level is the known quantity and the
    depth of water in front of it is not.

    The face is battered - it leans back about one in twelve - because a
    vertical slab reads as a retaining wall for a car park. The batter is what
    makes it look like it is holding the sea out.
    """
    out = SW.MeshGroup()
    batter = height / 12.0
    # the wall body, as a lofted quadrilateral prism so the face can lean
    half = length * 0.5
    sections = []
    for y, back in ((-height, batter), (0.0, 0.0)):
        sections.append(np.array([
            [-half, y, -thickness * 0.5 - back],
            [half, y, -thickness * 0.5 - back],
            [half, y, thickness * 0.5],
            [-half, y, thickness * 0.5],
        ]))
    body = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.34,
                  material=RUBBLE)
    out.add(body)

    # the cope: a projecting kerb course along the water edge, which is the
    # line that actually reads at distance
    cope = M.box((length, 0.34, thickness * 0.5 + 0.42),
                 center=(0.0, -0.17, -thickness * 0.25 - 0.21),
                 uv_scale=0.6, material=STONE)
    out.add(cope)

    if rings:
        count = max(int(length / 6.0), 1)
        for i in range(count):
            x = -half + (i + 0.5) * (length / count) + _jitter(seed, i, 0.25)
            # a mooring ring: a torus is overkill, a short thick tube reads
            # correctly at every distance this is ever seen from
            path = np.array([[x, -0.85, -thickness * 0.5 - 0.30],
                             [x, -1.15, -thickness * 0.5 - 0.52],
                             [x, -1.45, -thickness * 0.5 - 0.30]])
            out.add(M.tube(path, [0.055, 0.065, 0.055], segments=6,
                           material=IRON))
            out.add(M.box((0.20, 0.22, 0.16),
                          center=(x, -0.80, -thickness * 0.5 - 0.20),
                          material=IRON))
    return out


def bollard(height: float = 0.72, seed: int = 0) -> M.Mesh:
    """A cast bollard: swollen head, tapered shaft, splayed foot."""
    profile = [
        (0.00, 0.0), (0.26, 0.0), (0.26, 0.10), (0.20, 0.16),
        (0.185, height * 0.55), (0.215, height * 0.80),
        (0.20, height * 0.90), (0.13, height), (0.00, height),
    ]
    return M.lathe(profile, segments=12, uv_scale=1.1, material=IRON)


def mole_section(length: float, deck_y: float, floor_y: float,
                 deck_width: float = 7.0, seed: int = 0) -> SW.MeshGroup:
    """One run of the harbour breakwater.

    A mole is not a bridge and not a wall: it is a rubble mound with a masonry
    deck on top and an armoured slope facing the weather. Built along +X with
    the sea on -Z and the harbour on +Z, origin at the deck's centreline and
    y = 0 at the deck, so a caller places it by its deck level.

    The deck is the only walk surface. The armour slope is not: an actor
    grounded on it would stand on a 1-in-2 face over open water.
    """
    out = SW.MeshGroup()
    half = length * 0.5
    depth = max(deck_y - floor_y, 2.0)
    # The mound: wide at the bed, narrow at the deck, wider on the sea side
    # than the harbour side because that is the face taking the weather.
    sea_toe = deck_width * 0.5 + depth * 0.72
    harbour_toe = deck_width * 0.5 + depth * 0.42
    sections = [
        np.array([[-half, -depth, -sea_toe], [half, -depth, -sea_toe],
                  [half, -depth, harbour_toe], [-half, -depth, harbour_toe]]),
        np.array([[-half, -0.55, -deck_width * 0.5 - 0.9],
                  [half, -0.55, -deck_width * 0.5 - 0.9],
                  [half, -0.55, deck_width * 0.5 + 0.5],
                  [-half, -0.55, deck_width * 0.5 + 0.5]]),
    ]
    out.add(M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.22,
                   material=SEA_ROCK))

    # the deck slab, and a parapet on the weather side only
    deck = M.box((length, 0.55, deck_width),
                 center=(0.0, -0.275, 0.0), uv_scale=0.5, material=SETT)
    out.add_walk(deck)
    out.add(M.box((length, 1.15, 0.62),
                  center=(0.0, 0.575, -deck_width * 0.5 + 0.31),
                  uv_scale=0.55, material=STONE))
    # rough armour blocks tumbled along the sea toe, which is what stops the
    # slope reading as a smooth ramp
    count = max(int(length / 5.5), 1)
    for i in range(count):
        x = -half + (i + 0.5) * (length / count) + _jitter(seed, i, 1.1)
        z = -sea_toe * (0.62 + 0.24 * abs(_jitter(seed + 5, i, 1.0)))
        y = -depth * (0.30 + 0.34 * abs(_jitter(seed + 9, i, 1.0)))
        block = P.boulder(radius=1.05 + _jitter(seed + 13, i, 0.35),
                          seed=seed + i, material=SEA_ROCK)
        out.add(block.transformed(
            M.translation(x, y, z) @ M.rotation_y(_jitter(seed + 17, i, 3.1))))
    return out


def bastion(radius: float = 8.0, height: float = 7.0, deck_y: float = 0.0,
            seed: int = 0) -> SW.MeshGroup:
    """The mole's bastion - detail-board panel 8.

    A round battered drum with a parapet, a banner mast and a stair up from the
    mole deck. `deck_y` is where the mole deck meets it, so the stair has a
    known bottom; everything is built relative to y = 0 at that deck.
    """
    out = SW.MeshGroup()
    # battered drum, wider at the foot
    out.add(M.cylinder(radius * 1.16, radius, height, segments=24,
                       cap_bottom=False, cap_top=False, uv_scale=0.30,
                       material=RUBBLE).transformed(
        M.translation(0.0, deck_y - height * 0.55, 0.0)))
    platform_y = deck_y + height * 0.45
    out.add_walk(M.cylinder(radius, radius, 0.5, segments=24,
                            uv_scale=0.5, material=SETT).transformed(
        M.translation(0.0, platform_y - 0.5, 0.0)))
    # a crenellated parapet: merlons around three quarters of the drum, open
    # toward the mole so the stair arrives at something
    merlons = 18
    for i in range(merlons):
        angle = math.radians(-118.0 + 236.0 * i / (merlons - 1))
        x = math.cos(angle) * (radius - 0.42)
        z = math.sin(angle) * (radius - 0.42)
        out.add(M.box((0.9, 1.25, 0.62), center=(0.0, 0.0, 0.0),
                      uv_scale=0.7, material=STONE).transformed(
            at(x, platform_y + 0.62, z, yaw=-angle)))
    # the string course where the batter stops
    out.add(M.cylinder(radius + 0.34, radius + 0.34, 0.30, segments=24,
                       uv_scale=0.6, material=STONE).transformed(
        M.translation(0.0, platform_y - 0.62, 0.0)))

    # banner mast and banner - the panel's subject
    out.add(M.cylinder(0.14, 0.10, 7.2, segments=8, uv_scale=0.8,
                       material=TIMBER_DARK).transformed(
        M.translation(0.0, platform_y, 0.0)))
    out.add(P.banner(width=1.5, height=4.2, seed=seed,
                     material=CLOTH).transformed(
        M.translation(0.0, platform_y + 6.6, 0.10)))

    # stair down to the mole deck, on the harbour side
    run = 0.34
    steps = max(int(round(height * 0.45 / 0.17)), 2)
    stair = M.stairs(2.4, 0.17, run, steps, uv_scale=0.6, material=SETT)
    out.add_walk(stair.transformed(
        M.translation(0.0, deck_y, radius - steps * run + 0.4)))
    return out


def pier(length: float, width: float = 5.0, deck_y: float = 0.0,
         floor_y: float = -8.0, seed: int = 0) -> SW.MeshGroup:
    """A timber pier on driven piles, running along +Z from its root.

    The deck is a walk surface and, per the runtime contract, it owns its
    footprint on the server grid: the water beneath is not separately walkable.
    """
    out = SW.MeshGroup()
    bays = max(int(length / 4.2), 2)
    depth = deck_y - floor_y
    for i in range(bays + 1):
        z = i * (length / bays)
        for side in (-1, 1):
            x = side * (width * 0.5 - 0.45)
            lean = side * 0.22 * (depth / 8.0)
            path = np.array([[x + lean, floor_y - 0.6, z],
                             [x, deck_y - 0.35, z]])
            out.add(M.tube(path, [0.30, 0.24], segments=7, material=TIMBER_DARK))
        # cross bracing and the bearer the deck sits on
        out.add(M.box((width, 0.30, 0.28),
                      center=(0.0, deck_y - 0.50, z), uv_scale=0.7,
                      material=TIMBER_DARK))
    deck = M.box((width, 0.22, length),
                 center=(0.0, deck_y - 0.11, length * 0.5),
                 uv_scale=0.55, material=PLANK)
    out.add_walk(deck)
    # a low kerb rail down both sides, broken where a ship would come alongside
    for side in (-1, 1):
        for i in range(bays):
            z0 = i * (length / bays) + 0.4
            if i % 3 == 1:
                continue        # the gap a gangway lands in
            out.add(A.railing(length / bays - 0.8, height=0.92,
                              material=TIMBER_GREY).transformed(
                at(side * (width * 0.5 - 0.2), deck_y,
                   z0 + (length / bays - 0.8) * 0.5, yaw=math.pi * 0.5)))
    return out


# ------------------------------------------------------------------ working port
def harbour_crane(height: float = 9.0, reach: float = 6.5,
                  seed: int = 0) -> SW.MeshGroup:
    """The timber cargo crane of detail-board panel 5.

    A treadwheel crane: two heavy A-frame legs, a raked jib, a great spoked
    wheel on the axle, and a laden net hanging from the jib head. Built with
    the jib reaching toward -Z so a caller aims it at the water.
    """
    out = SW.MeshGroup()
    spread = 2.2
    # the A-frame, twice, fore and aft
    for z in (-1.1, 1.1):
        for side in (-1, 1):
            path = np.array([[side * spread, 0.0, z],
                             [side * 0.35, height, z]])
            out.add(M.tube(path, [0.30, 0.20], segments=6, material=TIMBER_DARK))
        out.add(M.box((spread * 2.0, 0.26, 0.24),
                      center=(0.0, height * 0.42, z), uv_scale=0.7,
                      material=TIMBER))
    # the head beam the jib pivots on
    out.add(M.box((1.5, 0.34, 3.0), center=(0.0, height - 0.1, 0.0),
                  uv_scale=0.7, material=TIMBER_DARK))
    # the raked jib
    jib = np.array([[0.0, height - 0.35, 0.6],
                    [0.0, height + 1.4, -reach * 0.55],
                    [0.0, height + 1.1, -reach]])
    out.add(M.tube(jib, [0.26, 0.22, 0.17], segments=6, material=TIMBER))
    # the treadwheel: rim, hub and spokes, on the axle between the frames
    axle_y = height * 0.42
    for z in (-0.55, 0.55):
        out.add(M.cylinder(1.9, 1.9, 0.14, segments=20, uv_scale=0.6,
                           material=TIMBER).transformed(
            at(0.0, axle_y, z, pitch=math.pi * 0.5)))
    for i in range(10):
        angle = math.pi * 2.0 * i / 10.0
        out.add(M.box((0.13, 3.6, 0.13), center=(0.0, 0.0, 0.0),
                      uv_scale=0.8, material=TIMBER).transformed(
            at(0.0, axle_y, 0.0, roll=angle)))
    out.add(M.cylinder(0.22, 0.22, 1.5, segments=10, uv_scale=0.7,
                       material=IRON).transformed(
        at(0.0, axle_y, -0.75, pitch=math.pi * 0.5)))

    # fall, hook and a laden cargo net under the jib head
    drop = height * 0.62
    out.add(M.tube(np.array([[0.0, height + 1.05, -reach],
                             [0.0, height + 1.05 - drop, -reach]]),
                   [0.05, 0.05], segments=5, material=IRON))
    net_y = height + 1.05 - drop
    for i in range(5):
        r = 0.85
        angle = math.pi * 2.0 * i / 5.0
        out.add(P.sack(radius=0.34, height=0.72, seed=seed + i).transformed(
            M.translation(math.cos(angle) * r * 0.5, net_y - 0.7,
                          -reach + math.sin(angle) * r * 0.5)))
    out.add(M.cylinder(1.05, 0.55, 1.05, segments=12, cap_top=False,
                       uv_scale=0.9, material=CLOTH).transformed(
        M.translation(0.0, net_y - 1.15, -reach)))
    return out


def gantry(width: float = 5.4, height: float = 6.2, seed: int = 0) -> SW.MeshGroup:
    """The shear-legs gantry of panel 4, for lifting into a hold."""
    out = SW.MeshGroup()
    for side in (-1, 1):
        out.add(M.tube(np.array([[side * width * 0.5, 0.0, 0.9],
                                 [side * 0.25, height, -0.5]]),
                       [0.26, 0.18], segments=6, material=TIMBER_DARK))
    out.add(M.tube(np.array([[0.0, height * 0.55, 0.2],
                             [0.0, height, -0.5]]),
                   [0.20, 0.16], segments=6, material=TIMBER))
    out.add(M.box((width * 1.02, 0.22, 0.22), center=(0.0, height * 0.55, 0.55),
                  uv_scale=0.7, material=TIMBER))
    out.add(M.tube(np.array([[0.0, height - 0.15, -0.5],
                             [0.0, height - 3.4, -0.5]]),
                   [0.045, 0.045], segments=5, material=IRON))
    out.add(P.crate(size=0.78, seed=seed, material=TIMBER_GREY).transformed(
        M.translation(0.0, height - 3.9, -0.5)))
    return out


def ship_hull(length: float = 22.0, beam: float = 6.0, seed: int = 0,
              masts: int = 2, rigged: bool = True) -> SW.MeshGroup:
    """A merchant hull, moored. Built along +X, waterline at y = 0.

    Lofted from a stack of sections rather than boxed, because the sheer line
    and the tumblehome are the whole silhouette; a boxy hull reads as a barge
    and the painting's harbour is full of proper ships.

    Never a walk surface. A moored ship is scenery: making its deck walkable
    would claim water cells on the server grid for a thing the server does not
    know exists.
    """
    out = SW.MeshGroup()
    stations = 13
    sections = []
    for i in range(stations):
        u = i / (stations - 1)
        # fine at the bow, full amidships, a little fuller aft than forward
        fullness = math.sin(math.pi * min(max(u, 0.02), 0.98)) ** 0.62
        half_b = beam * 0.5 * fullness
        # sheer: the deck line rises toward bow and stern
        sheer = 3.0 + 1.9 * (1.0 - math.sin(math.pi * u)) ** 1.4
        x = (u - 0.5) * length
        ring = []
        for j, (fz, fy) in enumerate(((0.00, -2.2), (0.62, -1.80), (0.94, -0.90),
                                      (1.00, 0.10), (0.92, sheer * 0.55),
                                      (0.80, sheer))):
            ring.append([x, fy, half_b * fz])
        for j in range(len(ring) - 1, -1, -1):
            fz = ring[j][2]
            if abs(fz) > 1e-6:
                ring.append([ring[j][0], ring[j][1], -fz])
        sections.append(np.array(ring))
    out.add(M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.20,
                   material=TIMBER_DARK))
    # wale, deck and rail
    out.add(M.box((length * 0.97, 0.30, beam * 0.90),
                  center=(0.0, 0.55, 0.0), uv_scale=0.4, material=TIMBER))
    out.add(M.box((length * 0.86, 0.16, beam * 0.72),
                  center=(0.0, 2.90, 0.0), uv_scale=0.4, material=PLANK))
    # sterncastle
    out.add(M.box((length * 0.20, 2.2, beam * 0.66),
                  center=(length * 0.34, 4.05, 0.0), uv_scale=0.45,
                  material=TIMBER))
    out.add(M.gable_roof(beam * 0.70, length * 0.21, 0.9, overhang=0.20,
                         material=ROOF).transformed(
        at(length * 0.34, 5.15, 0.0, yaw=math.pi * 0.5)))
    for i in range(masts):
        mx = length * (-0.24 + 0.42 * i / max(masts - 1, 1))
        mh = length * (0.92 - 0.10 * i)
        out.add(M.cylinder(0.30, 0.16, mh, segments=8, uv_scale=0.5,
                           material=TIMBER).transformed(
            M.translation(mx, 3.0, 0.0)))
        if not rigged:
            continue
        # Two yards a mast, each with its sail, plus shrouds, backstays and a
        # forestay. One yard and three shrouds read as a mast with a sheet on
        # it; the painting's ships carry courses and topsails and a web of
        # standing rigging, and this is the cheapest half of that difference.
        for tier, (height_fraction, spread, drop) in enumerate(
                ((0.66, 1.25, 0.44), (0.86, 0.86, 0.16))):
            yard_y = 3.0 + mh * height_fraction
            out.add(M.box((0.20, 0.20, beam * spread),
                          center=(mx, yard_y, 0.0), uv_scale=0.6,
                          material=TIMBER))
            foot = yard_y - mh * drop
            half_top = beam * spread * 0.48
            half_foot = beam * spread * 0.40
            out.add(M.quad([(mx - 0.05, yard_y, -half_top),
                            (mx - 0.05, yard_y, half_top),
                            (mx - 0.05, foot, half_foot),
                            (mx - 0.05, foot, -half_foot)],
                           uv_scale=0.35, material=SAIL))
        # shrouds: a fan each side from the masthead down to the channels
        for side in (-1, 1):
            for k in range(4):
                out.add(M.tube(np.array(
                    [[mx, 3.0 + mh * 0.72, 0.0],
                     [mx + (k - 1.5) * 1.15, 3.05, side * beam * 0.36]]),
                    [0.032, 0.032], segments=4, material=IRON))
        # a forestay forward and a backstay aft, which is what stops a mast
        # reading as a pole standing loose in a deck
        out.add(M.tube(np.array([[mx, 3.0 + mh * 0.92, 0.0],
                                 [mx - length * 0.20, 3.4, 0.0]]),
                       [0.030, 0.030], segments=4, material=IRON))
        out.add(M.tube(np.array([[mx, 3.0 + mh * 0.92, 0.0],
                                 [mx + length * 0.22, 3.4, 0.0]]),
                       [0.030, 0.030], segments=4, material=IRON))
    return out


def ship_on_stocks(length: float = 20.0, beam: float = 5.6,
                   seed: int = 0) -> SW.MeshGroup:
    """The hull under construction of detail-board panel 6.

    Keel, stem, sternpost and open frames, planked only up to the turn of the
    bilge, standing on a cradle of shores. The point of the panel is that you
    can see *through* it, so the frames are individual ribs and there is no
    skin above the garboards.
    """
    out = SW.MeshGroup()
    keel_y = 0.55
    out.add(M.box((length, 0.55, 0.62), center=(0.0, keel_y, 0.0),
                  uv_scale=0.4, material=TIMBER_DARK))
    # stem and sternpost, raked
    out.add(M.tube(np.array([[-length * 0.5, keel_y, 0.0],
                             [-length * 0.5 - 1.6, keel_y + 5.4, 0.0]]),
                   [0.34, 0.26], segments=6, material=TIMBER_DARK))
    out.add(M.tube(np.array([[length * 0.5, keel_y, 0.0],
                             [length * 0.5 + 0.9, keel_y + 4.6, 0.0]]),
                   [0.34, 0.26], segments=6, material=TIMBER_DARK))

    frames = 15
    for i in range(frames):
        u = (i + 0.5) / frames
        fullness = math.sin(math.pi * u) ** 0.60
        half_b = beam * 0.5 * fullness
        top = keel_y + 3.4 + 1.5 * (1.0 - math.sin(math.pi * u)) ** 1.3
        x = (u - 0.5) * length * 0.94
        for side in (-1, 1):
            path = np.array([
                [x, keel_y + 0.1, side * half_b * 0.10],
                [x, keel_y + 0.6, side * half_b * 0.72],
                [x, keel_y + 1.7, side * half_b * 1.00],
                [x, top, side * half_b * 0.88]])
            out.add(M.tube(path, [0.15, 0.15, 0.14, 0.12], segments=5,
                           material=TIMBER))
    # garboard planking: three strakes each side, low down only
    for side in (-1, 1):
        for k, (fz, fy) in enumerate(((0.30, 0.35), (0.66, 0.95), (0.95, 1.75))):
            sections = []
            for i in range(9):
                u = i / 8.0
                fullness = math.sin(math.pi * min(max(u, 0.03), 0.97)) ** 0.60
                x = (u - 0.5) * length * 0.94
                hb = beam * 0.5 * fullness
                sections.append(np.array([
                    [x, keel_y + fy, side * hb * fz],
                    [x, keel_y + fy + 0.42, side * hb * (fz + 0.16)]]))
            out.add(M.loft(sections, closed_rings=False, uv_scale=0.3,
                           material=TIMBER))
    # the cradle of shores holding it upright
    for i in range(6):
        x = (i / 5.0 - 0.5) * length * 0.8
        for side in (-1, 1):
            out.add(M.tube(np.array([[x, 0.0, side * (beam * 0.5 + 1.9)],
                                     [x, keel_y + 1.9, side * beam * 0.42]]),
                           [0.20, 0.16], segments=5, material=TIMBER_GREY))
    # keel blocks
    for i in range(7):
        x = (i / 6.0 - 0.5) * length * 0.88
        out.add(M.box((0.9, keel_y, 1.1), center=(x, keel_y * 0.5, 0.0),
                      uv_scale=0.6, material=TIMBER_GREY))
    return out


# ------------------------------------------------------------------- buildings
def warehouse(width: float = 8.0, depth: float = 11.0, storeys: int = 3,
              seed: int = 0, hoist: bool = True) -> SW.MeshGroup:
    """A tall narrow harbour warehouse: gable to the water, loading door,
    hoist beam under the ridge. The whole waterfront of the painting is these.

    Gable end faces -Z, which is the water, so a caller places it with its back
    to the town.
    """
    out = SW.MeshGroup()
    storey_h = 3.1
    height = storey_h * storeys
    out.add(M.box((width, height, depth), center=(0.0, height * 0.5, 0.0),
                  uv_scale=0.32, material=PLASTER))
    # a stone base course - everything on a quay gets splashed
    out.add(M.box((width + 0.18, 1.35, depth + 0.18),
                  center=(0.0, 0.67, 0.0), uv_scale=0.5, material=RUBBLE))
    out.add(M.gable_roof(width, depth, 2.9, overhang=0.42, material=ROOF)
            .transformed(M.translation(0.0, height, 0.0)))

    # openings: a tall loading door on the gable, windows either side
    out.add(A.door(width=1.5, height=2.6, material=TIMBER_DARK).transformed(
        M.translation(0.0, 0.0, -depth * 0.5 - 0.06)))
    for storey in range(1, storeys):
        y = storey * storey_h + 0.55
        out.add(A.door(width=1.35, height=1.85, material=TIMBER_DARK)
                .transformed(M.translation(0.0, y, -depth * 0.5 - 0.06)))
        for side in (-1, 1):
            out.add(A.window(width=0.78, height=1.0, material=TIMBER_GREY)
                    .transformed(M.translation(side * width * 0.30, y + 0.30,
                                               -depth * 0.5 - 0.06)))
    for storey in range(storeys):
        for i in range(max(int(depth / 3.0), 1)):
            z = -depth * 0.5 + (i + 0.7) * (depth / max(int(depth / 3.0), 1))
            for side in (-1, 1):
                out.add(A.window(width=0.72, height=1.0, material=TIMBER_GREY)
                        .transformed(at(side * (width * 0.5 + 0.06),
                                        storey * storey_h + 1.5, z,
                                        yaw=math.pi * 0.5)))
    if hoist:
        # the hoist beam projecting from the gable peak, with its block
        out.add(M.box((0.24, 0.24, 1.9),
                      center=(0.0, height + 1.85, -depth * 0.5 - 0.7),
                      uv_scale=0.7, material=TIMBER_DARK))
        out.add(M.tube(np.array([[0.0, height + 1.72, -depth * 0.5 - 1.45],
                                 [0.0, height - 1.2, -depth * 0.5 - 1.45]]),
                       [0.04, 0.04], segments=4, material=IRON))
    return out


def town_house(width: float = 6.0, depth: float = 7.5, storeys: int = 3,
               seed: int = 0, jetty: bool = True) -> SW.MeshGroup:
    """A city house: masonry ground floor, jettied timber storeys, tiled roof.

    Jettying - each storey oversailing the one below - is what gives the
    painting's streets their crowded top-heavy look, and it costs one extra box
    per storey.
    """
    out = SW.MeshGroup()
    storey_h = 2.85
    out.add(M.box((width, storey_h, depth),
                  center=(0.0, storey_h * 0.5, 0.0), uv_scale=0.36,
                  material=RUBBLE))
    for storey in range(1, storeys):
        over = 0.34 * storey if jetty else 0.0
        y = storey * storey_h
        w = width + over
        d = depth + over * 0.5
        out.add(M.box((w, storey_h, d), center=(0.0, y + storey_h * 0.5, 0.0),
                      uv_scale=0.36, material=PLASTER))
        # the exposed frame on the front face
        out.add(A.framed_wall(w, storey_h, thickness=0.14,
                              material_frame=TIMBER_DARK,
                              material_fill=PLASTER, seed=seed + storey).transformed(
            M.translation(0.0, y, -d * 0.5 - 0.07)))
        for i in range(max(int(w / 2.2), 1)):
            x = -w * 0.5 + (i + 0.5) * (w / max(int(w / 2.2), 1))
            out.add(A.window(width=0.82, height=1.1, material=TIMBER_GREY)
                    .transformed(M.translation(x, y + 0.85, -d * 0.5 - 0.30)))
    top = storeys * storey_h
    over = 0.34 * (storeys - 1) if jetty else 0.0
    out.add(M.gable_roof(width + over, depth + over * 0.5, 2.4, overhang=0.46,
                         material=ROOF).transformed(M.translation(0.0, top, 0.0)))
    out.add(A.door(width=1.0, height=2.05, material=TIMBER_DARK).transformed(
        M.translation(_jitter(seed, 1, width * 0.22), 0.0, -depth * 0.5 - 0.06)))
    if N.stable_hash(f"chimney{seed}") % 3:
        out.add(A.chimney(width=0.8, height=2.6, material=RUBBLE).transformed(
            M.translation(width * 0.28, top + 1.2, depth * 0.18)))
    return out


def arcade_range(bays: int = 7, span: float = 3.4, height: float = 4.6,
                 depth: float = 4.2, seed: int = 0,
                 upper: bool = True) -> SW.MeshGroup:
    """An arcaded terrace: the long colonnaded fronts of the painting's
    middle city, and the shelter the fish market of panel 7 stands under.

    Runs along +X, arches facing -Z. The walkway behind the arcade is a walk
    surface; the range above it is not.
    """
    out = SW.MeshGroup()
    length = bays * span
    half = length * 0.5
    # the back wall and the walkway floor
    out.add(M.box((length, height + (3.0 if upper else 0.0), 0.6),
                  center=(0.0, (height + (3.0 if upper else 0.0)) * 0.5,
                          depth * 0.5),
                  uv_scale=0.34, material=STONE))
    out.add_walk(M.box((length, 0.24, depth),
                       center=(0.0, 0.12, 0.0), uv_scale=0.5, material=SETT))
    for i in range(bays + 1):
        x = -half + i * span
        out.add(SW.column(height - 0.55, radius=0.34, flutes=10,
                          material=STONE).transformed(M.translation(x, 0.24, 0.0)))
    for i in range(bays):
        x = -half + (i + 0.5) * span
        out.add(M.arch(span - 0.68, (span - 0.68) * 0.5, 0.42, 0.72,
                       segments=10, uv_scale=0.5, material=STONE).transformed(
            M.translation(x, height - 0.31, 0.0)))
    # entablature over the arcade
    out.add(M.box((length + 0.4, 0.52, depth * 0.4),
                  center=(0.0, height + 0.26, depth * 0.1), uv_scale=0.5,
                  material=STONE))
    if upper:
        for i in range(bays):
            x = -half + (i + 0.5) * span
            out.add(A.window(width=1.05, height=1.5, material=TIMBER_GREY)
                    .transformed(M.translation(x, height + 1.1, depth * 0.2 - 0.32)))
        out.add(SW.balustrade(length, height=1.02, material=STONE).transformed(
            M.translation(0.0, height + 0.52, 0.0)))
        out.add(M.gable_roof(depth * 1.05, length, 1.9, overhang=0.4,
                             material=ROOF).transformed(
            at(0.0, height + 3.0, depth * 0.28, yaw=math.pi * 0.5)))
    return out


def gate_arch(span: float = 11.0, height: float = 17.0, depth: float = 5.0,
              seed: int = 0, towers: bool = True) -> SW.MeshGroup:
    """The harbour gate of detail-board panel 1: a single tall arch on piers
    with flanking towers, spanning the mouth of the west inlet.

    Built spanning the X axis with the opening facing Z, which is the way
    `mesh.arch` builds - the guide's trap about rotating an arch ninety degrees
    and looking at the barrel end is avoided by building the piece in the
    orientation the caller wants and letting the caller rotate the whole group.
    """
    out = SW.MeshGroup()
    pier_w = 3.4
    springing = height * 0.52
    for side in (-1, 1):
        x = side * (span * 0.5 + pier_w * 0.5)
        out.add(M.box((pier_w, springing, depth),
                      center=(x, springing * 0.5, 0.0), uv_scale=0.3,
                      material=RUBBLE))
        out.add(M.box((pier_w + 0.5, 0.42, depth + 0.5),
                      center=(x, springing + 0.21, 0.0), uv_scale=0.5,
                      material=STONE))
        # the cutwater, so the pier reads as standing in moving water
        out.add(M.extrude([(-0.9, 0.0), (0.9, 0.0), (0.0, 2.1)], springing * 0.7,
                          uv_scale=0.4, material=RUBBLE).transformed(
            at(x, 0.0, -depth * 0.5, yaw=math.pi)))
    out.add(M.arch(span, span * 0.5, 1.5, depth, segments=18, uv_scale=0.38,
                   material=STONE).transformed(
        M.translation(0.0, springing, -depth * 0.5)))
    # the spandrel wall and the roadway over it
    out.add(M.box((span + pier_w * 2.0, height - springing - span * 0.5 - 1.5,
                   depth),
                  center=(0.0, springing + span * 0.5 + 1.5
                          + (height - springing - span * 0.5 - 1.5) * 0.5, 0.0),
                  uv_scale=0.32, material=RUBBLE))
    # The roadway over the arch is a walk surface: the gate spans a channel,
    # and the quay route west has to cross on it. Per the runtime contract the
    # deck then owns its footprint on the server grid and the water beneath is
    # not separately walkable, which is correct here.
    out.add_walk(M.box((span + pier_w * 2.0 + 0.6, 0.5, depth + 0.6),
                       center=(0.0, height + 0.25, 0.0), uv_scale=0.5,
                       material=SETT))
    # Seat the turrets within the deck slab; their bottom caps must not
    # share the spandrel top plane, even where the overlap is concealed.
    if towers:
        for side in (-1, 1):
            x = side * (span * 0.5 + pier_w * 0.5)
            out.add(M.cylinder(2.4, 2.15, 7.5, segments=14, uv_scale=0.34,
                               material=STONE).transformed(
                M.translation(x, height + 0.2, 0.0)))
            out.add(M.cylinder(2.55, 2.55, 0.5, segments=14, uv_scale=0.6,
                               material=STONE).transformed(
                M.translation(x, height + 7.7, 0.0)))
            out.add(M.cylinder(2.3, 0.0, 3.6, segments=14, uv_scale=0.5,
                               material=ROOF).transformed(
                M.translation(x, height + 8.2, 0.0)))
    return out


def lighthouse(height: float = 26.0, base_radius: float = 4.4,
               seed: int = 0) -> SW.MeshGroup:
    """The great lighthouse of detail-board panel 2.

    A battered stone tower on a splayed base, a corbelled gallery, a glazed
    lantern and a domed cap. The gallery is a walk surface; the tower is not.
    """
    out = SW.MeshGroup()
    top_radius = base_radius * 0.52
    # splayed foot, then the tower proper as a lathe so the entasis is smooth
    profile = []
    steps = 14
    for i in range(steps + 1):
        u = i / steps
        # a slight concave batter - the classic lighthouse curve
        r = base_radius * (1.0 - u) ** 1.35 + top_radius * u
        profile.append((r, u * height))
    out.add(M.lathe([(0.0, 0.0), (base_radius * 1.28, 0.0),
                     (base_radius * 1.28, 1.1), (base_radius * 1.05, 1.6)]
                    + profile, segments=22, uv_scale=0.26, material=STONE))
    # string courses, which is what gives the tower its scale
    for band in (0.30, 0.55, 0.78):
        u = band
        r = base_radius * (1.0 - u) ** 1.35 + top_radius * u
        out.add(M.cylinder(r + 0.20, r + 0.20, 0.28, segments=22, uv_scale=0.6,
                           material=STONE).transformed(
            M.translation(0.0, u * height, 0.0)))
    # the gallery: a corbelled ring with a rail
    gallery_r = top_radius + 1.25
    out.add(M.cylinder(top_radius + 0.4, gallery_r, 0.75, segments=22,
                       uv_scale=0.5, material=STONE).transformed(
        M.translation(0.0, height - 0.75, 0.0)))
    out.add_walk(M.cylinder(gallery_r, gallery_r, 0.20, segments=22,
                            uv_scale=0.6, material=STONE).transformed(
        M.translation(0.0, height, 0.0)))
    # The gallery rail is a ring of stanchions with a hoop on top. Wrapping a
    # straight `railing` of length 2*pi*r round a circle is not something the
    # shared kit can do: translated to a point it renders as a single tangent
    # bar flying off the lantern, which is what the first panel-2 capture showed.
    for i in range(14):
        angle = math.pi * 2.0 * i / 14.0
        out.add(M.box((0.10, 1.05, 0.10),
                      center=(math.cos(angle) * gallery_r, height + 0.72,
                              math.sin(angle) * gallery_r),
                      uv_scale=0.8, material=IRON))
    out.add(M.cylinder(gallery_r, gallery_r, 0.10, segments=22, uv_scale=0.7,
                       material=IRON).transformed(
        M.translation(0.0, height + 1.20, 0.0)))
    # the lantern: glazed drum, then a lead dome and a finial
    out.add(M.cylinder(top_radius, top_radius, 3.2, segments=14,
                       cap_bottom=False, cap_top=False, uv_scale=0.5,
                       material=GLASS).transformed(
        M.translation(0.0, height + 0.2, 0.0)))
    for i in range(10):
        angle = math.pi * 2.0 * i / 10.0
        out.add(M.box((0.14, 3.2, 0.14),
                      center=(math.cos(angle) * top_radius, height + 1.8,
                              math.sin(angle) * top_radius),
                      uv_scale=0.8, material=IRON))
    out.add(M.lathe([(top_radius + 0.25, 0.0), (top_radius * 0.92, 0.9),
                     (top_radius * 0.60, 1.75), (top_radius * 0.22, 2.25),
                     (0.0, 2.45)], segments=18, uv_scale=0.5,
                    material=IRON).transformed(
        M.translation(0.0, height + 3.4, 0.0)))
    out.add(M.cylinder(0.10, 0.05, 1.6, segments=6, uv_scale=0.8,
                       material=IRON).transformed(
        M.translation(0.0, height + 5.85, 0.0)))
    # the keeper's house against the foot, on the landward side
    out.add(town_house(width=5.4, depth=6.2, storeys=1, seed=seed + 3,
                       jetty=False).transformed(
        M.translation(0.0, 0.0, base_radius * 1.35)))
    return out


def domed_hall(radius: float = 7.0, drum_height: float = 8.0,
               seed: int = 0) -> SW.MeshGroup:
    """The brass-domed civic hall of detail-board panel 9.

    A colonnaded drum carrying a ribbed dome and a lantern. The terrace around
    it is a walk surface - the panel is a view *from* that terrace.
    """
    out = SW.MeshGroup()
    out.add_walk(M.cylinder(radius * 1.75, radius * 1.75, 0.4, segments=26,
                            uv_scale=0.5, material=SETT).transformed(
        M.translation(0.0, -0.4, 0.0)))
    # a ring of balusters, for the same reason the lighthouse gallery is
    for i in range(30):
        angle = math.pi * 2.0 * i / 30.0
        out.add(M.cylinder(0.10, 0.09, 0.86, segments=6, uv_scale=0.9,
                           material=STONE).transformed(
            M.translation(math.cos(angle) * radius * 1.72, 0.0,
                          math.sin(angle) * radius * 1.72)))
    out.add(M.lathe([(radius * 1.62, 0.0), (radius * 1.82, 0.0),
                     (radius * 1.82, 0.16), (radius * 1.62, 0.16)],
                    segments=30, uv_scale=0.6, material=STONE).transformed(
        M.translation(0.0, 0.86, 0.0)))
    out.add(M.cylinder(radius, radius, drum_height, segments=24, uv_scale=0.3,
                       material=STONE))
    for i in range(16):
        angle = math.pi * 2.0 * i / 16.0
        out.add(SW.column(drum_height - 0.6, radius=0.30, flutes=10,
                          material=STONE).transformed(
            M.translation(math.cos(angle) * (radius + 0.62), 0.0,
                          math.sin(angle) * (radius + 0.62))))
        out.add(A.window(width=0.9, height=2.0, material=TIMBER_GREY)
                .transformed(at(math.cos(angle) * (radius + 0.02),
                                drum_height * 0.42,
                                math.sin(angle) * (radius + 0.02),
                                yaw=-angle)))
    out.add(M.cylinder(radius + 0.95, radius + 0.95, 0.55, segments=24,
                       uv_scale=0.55, material=STONE).transformed(
        M.translation(0.0, drum_height - 0.55, 0.0)))
    # the dome, ribbed. Brass, so it takes the iron material's metallic.
    dome_profile = []
    for i in range(13):
        u = i / 12.0
        dome_profile.append((radius * math.cos(u * math.pi * 0.5),
                             radius * 0.86 * math.sin(u * math.pi * 0.5)))
    out.add(M.lathe(dome_profile, segments=24, uv_scale=0.34,
                    material=BRASS).transformed(
        M.translation(0.0, drum_height, 0.0)))
    for i in range(12):
        angle = math.pi * 2.0 * i / 12.0
        rib = []
        for k in range(9):
            u = k / 8.0
            r = radius * math.cos(u * math.pi * 0.5)
            y = radius * 0.86 * math.sin(u * math.pi * 0.5)
            rib.append([math.cos(angle) * r, drum_height + y,
                        math.sin(angle) * r])
        out.add(M.tube(np.array(rib), [0.10] * 9, segments=4, material=BRASS))
    out.add(M.cylinder(1.15, 1.05, 2.1, segments=12, uv_scale=0.6,
                       material=STONE).transformed(
        M.translation(0.0, drum_height + radius * 0.83, 0.0)))
    out.add(M.lathe([(1.25, 0.0), (0.95, 0.7), (0.45, 1.25), (0.0, 1.5)],
                    segments=12, uv_scale=0.6, material=BRASS).transformed(
        M.translation(0.0, drum_height + radius * 0.83 + 2.1, 0.0)))
    return out


def campanile(height: float = 34.0, width: float = 5.2,
              seed: int = 0) -> SW.MeshGroup:
    """The dark bell tower that dominates the painting's upper city."""
    out = SW.MeshGroup()
    out.add(M.box((width * 1.20, 1.4, width * 1.20), center=(0.0, 0.7, 0.0),
                  uv_scale=0.4, material=STONE))
    out.add(M.box((width, height - 1.4, width),
                  center=(0.0, 1.4 + (height - 1.4) * 0.5, 0.0),
                  uv_scale=0.26, material=RUBBLE))
    # blind arcading up the faces, which is what stops it reading as a chimney
    for level in range(1, 5):
        y = 1.4 + (height - 8.0) * level / 5.0
        for side, rot in ((0, 0.0), (1, math.pi * 0.5), (2, math.pi),
                          (3, math.pi * 1.5)):
            for k in (-1, 1):
                out.add(M.arch(1.15, 0.58, 0.22, 0.30, segments=8, uv_scale=0.6,
                               material=STONE).transformed(
                    M.rotation_y(rot)
                    @ at(k * width * 0.24, y, -width * 0.5 - 0.02)))
    # the belfry: open arches on all four faces
    belfry_y = height - 6.6
    for rot in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
        out.add(M.arch(2.4, 1.2, 0.4, 0.5, segments=12, uv_scale=0.5,
                       material=STONE).transformed(
            M.rotation_y(rot)
            @ at(0.0, belfry_y + 2.0, -width * 0.5 - 0.05)))
    out.add(M.box((width + 0.9, 0.55, width + 0.9),
                  center=(0.0, height - 0.9, 0.0), uv_scale=0.5, material=STONE))
    # a pyramidal cap
    out.add(M.cylinder(width * 0.80, 0.0, 5.4, segments=4, uv_scale=0.5,
                       material=ROOF).transformed(
        at(0.0, height - 0.35, 0.0, yaw=math.pi * 0.25)))
    return out


def cathedral(seed: int = 0, length: float = 34.0, width: float = 16.0,
              height: float = 15.0) -> SW.MeshGroup:
    """The citadel church: a long aisled nave, a crossing tower and an apse.

    Not a copy of the concept's building - the painting's citadel is read at
    120 m and its detail is not resolvable - but its massing: a long ridge
    running with the terrace, a taller crossing, and a rounded east end.
    """
    out = SW.MeshGroup()
    nave_w = width * 0.55
    out.add(M.box((nave_w, height, length), center=(0.0, height * 0.5, 0.0),
                  uv_scale=0.28, material=STONE))
    out.add(M.gable_roof(nave_w, length, 4.2, overhang=0.5, material=ROOF)
            .transformed(M.translation(0.0, height, 0.0)))
    # aisles, lower, either side
    for side in (-1, 1):
        out.add(M.box((width * 0.22, height * 0.58, length * 0.86),
                      center=(side * (nave_w * 0.5 + width * 0.11),
                              height * 0.29, 0.0),
                      uv_scale=0.3, material=STONE))
        out.add(M.gable_roof(width * 0.22, length * 0.86, 1.7, overhang=0.4,
                             material=ROOF).transformed(
            M.translation(side * (nave_w * 0.5 + width * 0.11),
                          height * 0.58, 0.0)))
        # buttresses
        for i in range(7):
            z = (i / 6.0 - 0.5) * length * 0.82
            out.add(M.box((1.5, height * 0.52, 0.8),
                          center=(side * (nave_w * 0.5 + width * 0.22 + 0.4),
                                  height * 0.26, z),
                          uv_scale=0.45, material=STONE))
        for i in range(6):
            z = (i / 5.0 - 0.5) * length * 0.7
            out.add(A.window(width=1.1, height=2.6, material=TIMBER_GREY)
                    .transformed(at(side * (nave_w * 0.5 + 0.03),
                                    height * 0.62, z, yaw=math.pi * 0.5)))
    # crossing tower
    out.add(M.box((nave_w * 1.25, height * 0.62, nave_w * 1.25),
                  center=(0.0, height + height * 0.31, -length * 0.10),
                  uv_scale=0.3, material=STONE))
    out.add(M.cylinder(nave_w * 0.92, 0.0, 8.0, segments=4, uv_scale=0.5,
                       material=ROOF).transformed(
        at(0.0, height * 1.62, -length * 0.10, yaw=math.pi * 0.25)))
    # the apse at the east end
    # `cylinder` has no arc parameter, so the apse is a half-drum lathed
    # through pi. `lathe` does take one, and revolving a straight profile is
    # exactly a cylinder.
    out.add(M.lathe([(nave_w * 0.5, 0.0), (nave_w * 0.5, height * 0.86)],
                    segments=9, arc=math.pi, uv_scale=0.3,
                    material=STONE).transformed(
        M.translation(0.0, 0.0, length * 0.5)))
    out.add(M.lathe([(nave_w * 0.52, 0.0), (nave_w * 0.36, 1.6),
                     (0.0, 3.0)], segments=9, uv_scale=0.5,
                    material=ROOF).transformed(
        M.translation(0.0, height * 0.86, length * 0.5)))
    # the west front: a great door under a wheel window, flanked by turrets
    out.add(M.arch(3.2, 1.6, 0.55, 1.0, segments=12, uv_scale=0.5,
                   material=STONE).transformed(
        M.translation(0.0, 3.4, -length * 0.5 - 0.5)))
    out.add(M.cylinder(2.3, 2.3, 0.5, segments=16, uv_scale=0.5,
                       material=GLASS).transformed(
        at(0.0, height * 0.66, -length * 0.5 - 0.2, pitch=math.pi * 0.5)))
    for side in (-1, 1):
        out.add(M.cylinder(1.5, 1.35, height * 1.16, segments=12, uv_scale=0.34,
                           material=STONE).transformed(
            M.translation(side * nave_w * 0.55, 0.0, -length * 0.5 - 0.2)))
        out.add(M.cylinder(1.5, 0.0, 3.4, segments=12, uv_scale=0.5,
                           material=ROOF).transformed(
            M.translation(side * nave_w * 0.55, height * 1.16,
                          -length * 0.5 - 0.2)))
    return out


def fish_stall(seed: int = 0) -> SW.MeshGroup:
    """A fish market stall - detail-board panel 7. Trestle, awning, catch."""
    out = SW.MeshGroup()
    out.add(P.market_stall(width=2.8, depth=1.9, seed=seed, goods=CLOTH))
    # The shared stall merges its canopy into the timber material, so the
    # striped awning that is the whole look of panel 7 does not survive. Add a
    # real one over the top: two sloping panels on the canvas material, which
    # is a market awning and is exactly what that recipe is for.
    for side in (-1, 1):
        out.add(M.quad([(-1.65, 2.15, side * 0.05),
                        (1.65, 2.15, side * 0.05),
                        (1.65, 1.72, side * 1.30),
                        (-1.65, 1.72, side * 1.30)],
                       uv_scale=0.9, material=CANVAS))
    # the slab of catch on the trestle: flattened ellipsoids, silver-blue
    for i in range(7):
        x = -1.05 + (i % 4) * 0.62 + _jitter(seed, i, 0.12)
        z = -0.28 + (i // 4) * 0.42
        fish = M.icosphere(radius=0.20, subdivisions=1, material=IRON)
        fish.transform(M.scaling(1.55, 0.42, 0.55))
        out.add(fish.transformed(
            at(x, 0.92, z, yaw=_jitter(seed + 3, i, 0.8))))
    out.add(P.basket(radius=0.34, height=0.44, seed=seed + 7).transformed(
        M.translation(1.15, 0.0, 0.55)))
    return out


def coiled_rope(radius: float = 0.62, turns: int = 5, thickness: float = 0.055,
                seed: int = 0) -> M.Mesh:
    """A rope flaked down in a flat coil - detail-board panel 10.

    A real coil is laid in a spiral that rises a little as it goes, so the
    inner turns sit slightly proud of the outer ones. Built as one swept tube
    along that spiral rather than as concentric rings, because rings leave
    visible end caps wherever two of them meet.
    """
    points = []
    radii = []
    steps = turns * 22
    for i in range(steps + 1):
        u = i / steps
        angle = u * turns * math.tau
        r = radius * (1.0 - u * 0.62)
        points.append([math.cos(angle) * r,
                       thickness + u * thickness * 1.7,
                       math.sin(angle) * r])
        radii.append(thickness)
    # the bitter end, laid off across the coil
    tail = points[-1]
    points.append([tail[0] * 0.4, thickness, tail[2] * 0.4 - radius * 0.9])
    radii.append(thickness * 0.9)
    return M.tube(np.array(points), radii, segments=6, material=CLOTH)


def chain_run(length: float = 2.2, links: int = 11, link_radius: float = 0.11,
              seed: int = 0) -> SW.MeshGroup:
    """A run of chain, alternate links turned ninety degrees.

    Each link is a torus lathed from a circular profile offset from the axis.
    Alternating the roll is the whole reason a chain reads as a chain and not
    as a row of washers.
    """
    out = SW.MeshGroup()
    profile = []
    for i in range(9):
        angle = math.tau * i / 8.0
        profile.append((link_radius + math.cos(angle) * link_radius * 0.34,
                        math.sin(angle) * link_radius * 0.34))
    spacing = length / max(links - 1, 1)
    for i in range(links):
        link = M.lathe(profile, segments=10, uv_scale=1.4, material=IRON)
        # lathe revolves about +Y, so a link lies in the XZ plane; stand it up
        # and roll every other one across the run
        out.add(link.transformed(
            at(-length * 0.5 + i * spacing,
               link_radius + _jitter(seed, i, 0.01),
               _jitter(seed + 3, i, 0.02),
               pitch=math.pi * 0.5,
               roll=0.0 if i % 2 else math.pi * 0.5)))
    return out


def street_arch(span: float = 5.2, height: float = 4.6, depth: float = 4.0,
                storeys: int = 2, seed: int = 0) -> SW.MeshGroup:
    """A street running through an arch with building over it - panel 3.

    The panel's defining feature is that the cobbled climb passes *under* a
    house, and the build had an open ramp between two rows instead. The arch
    springs from piers either side of the street and carries two jettied
    storeys across it.

    The roadway under the arch is a walk surface; the storeys above are not.
    """
    out = SW.MeshGroup()
    pier = 1.6
    for side in (-1, 1):
        x = side * (span * 0.5 + pier * 0.5)
        out.add(M.box((pier, height, depth), center=(x, height * 0.5, 0.0),
                      uv_scale=0.4, material=RUBBLE))
    out.add(M.arch(span, span * 0.5, 0.6, depth, segments=14, uv_scale=0.45,
                   material=STONE).transformed(
        M.translation(0.0, height, -depth * 0.5)))
    # the roadway through it
    out.add_walk(M.box((span + pier * 2.0, 0.20, depth),
                       center=(0.0, -0.10, 0.0), uv_scale=0.6, material=SETT))
    top = height + span * 0.5 + 0.6
    width = span + pier * 2.0
    for storey in range(storeys):
        over = 0.30 * (storey + 1)
        y = top + storey * 2.85
        w = width + over
        d = depth + over * 0.6
        out.add(M.box((w, 2.85, d), center=(0.0, y + 1.425, 0.0), uv_scale=0.36,
                      material=PLASTER))
        out.add(A.framed_wall(w, 2.85, thickness=0.14, material_frame=TIMBER_DARK,
                              material_fill=PLASTER, seed=seed + storey).transformed(
            M.translation(0.0, y, -d * 0.5 - 0.07)))
        for i in range(max(int(w / 2.1), 1)):
            wx = -w * 0.5 + (i + 0.5) * (w / max(int(w / 2.1), 1))
            out.add(A.window(width=0.80, height=1.05, material=TIMBER_GREY)
                    .transformed(M.translation(wx, y + 0.85, -d * 0.5 - 0.08)))
    out.add(M.gable_roof(width + 0.30 * storeys, depth + 0.18 * storeys, 2.2,
                         overhang=0.45, material=ROOF).transformed(
        M.translation(0.0, top + storeys * 2.85, 0.0)))
    return out


def jetty(length: float = 9.0, width: float = 2.2, deck_y: float = 0.0,
          floor_y: float = -6.0, seed: int = 0) -> SW.MeshGroup:
    """A small timber landing stage, for the many short jetties the aerial has
    along its waterfront that the two big piers do not account for."""
    out = SW.MeshGroup()
    bays = max(int(length / 3.0), 2)
    for i in range(bays + 1):
        z = i * (length / bays)
        for side in (-1, 1):
            x = side * (width * 0.5 - 0.25)
            out.add(M.tube(np.array([[x, floor_y - 0.4, z], [x, deck_y - 0.25, z]]),
                           [0.20, 0.16], segments=6, material=TIMBER_DARK))
        out.add(M.box((width, 0.22, 0.20), center=(0.0, deck_y - 0.36, z),
                      uv_scale=0.7, material=TIMBER_DARK))
    out.add_walk(M.box((width, 0.18, length),
                       center=(0.0, deck_y - 0.09, length * 0.5),
                       uv_scale=0.6, material=PLANK))
    return out


def cistern_head(seed: int = 0) -> SW.MeshGroup:
    """A street cistern head: the city's fresh water, and a street ornament."""
    out = SW.MeshGroup()
    out.add(M.lathe([(0.0, 0.0), (1.05, 0.0), (1.05, 0.75), (0.92, 0.90),
                     (0.86, 1.05), (0.0, 1.05)], segments=12, uv_scale=0.7,
                    material=STONE))
    out.add(M.cylinder(0.34, 0.30, 1.35, segments=8, uv_scale=0.7,
                       material=STONE).transformed(M.translation(0.0, 1.05, 0.0)))
    out.add(M.box((0.16, 0.16, 0.42), center=(0.0, 1.75, -0.30),
                  uv_scale=0.8, material=IRON))
    return out
