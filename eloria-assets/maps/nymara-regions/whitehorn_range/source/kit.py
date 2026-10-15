"""Whitehorn-specific kit pieces.

The shared toolkit already carries the generic masonry, timber and prop kits,
and this module reuses them wherever it can - `stonework.statue`,
`stonework.column`, `stonework.ancient_arch`, `architecture.steps`,
`props.brazier`, `props.hanging_lantern`. What lives here is only what an
alpine glacier region needs and no other region had: cairns, a rope-and-plank
suspension bridge, a timbered mine portal, an ice-cave mouth and a frozen
cascade.

The suspension bridge has been promoted to amberwood.mountaincraft;
rope_bridge below supplies Whitehorn's palette. The older region-specific
cairn, shrine, cave and cascade assemblies remain here. New reusable route
equipment belongs in the shared toolkit.

Walk surfaces include the bridge deck, temple stairs and the actual mine and
cave approach floors. Gantries, lintels and icicles remain structural, so they
cannot catch the client's downward grounding ray.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import stonework as SW

# Materials, all drawn from the pinned set in build_whitehorn.MATERIALS.
STONE = "pale_ashlar"
ROCK = "cliff_rock"
RUBBLE = "rubble_stone"
MARBLE = "veined_marble"
ICE = "glacier_ice"
SNOW = "snow_pack"
CRYSTAL = "blue_crystal"
BRASS = "gilt_brass"
IRON = "dark_iron"
TIMBER = "timber_grey"
TIMBER_DARK = "timber_dark"
CARVED = "carved_wood"
ROPE = "woven_cloth"
SLATE = "slate_roof"
AMBER = "amber_resin"


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed & 0x7FFFFFFF)


# --------------------------------------------------------------------------
# cairns and waystones - the region's signature roadside marker
# --------------------------------------------------------------------------
def cairn(height: float = 1.6, seed: int = 0, material: str = ROCK) -> M.Mesh:
    """A stack of flattened stones, wider at the base and leaning slightly.

    Panels 1, 5 and 9 of the detail board put these along every road and in
    dense clusters on the ridges. They are the cheapest piece in the region
    and the most repeated, so this is one flattened mesh, not a MeshGroup.
    """
    rng = _rng(seed)
    pieces = []
    courses = max(3, int(height / 0.22))
    y = 0.0
    for index in range(courses):
        t = index / float(courses - 1)
        radius = (0.42 * (1.0 - t) + 0.11 * t) * (1.0 + 0.16 * rng.standard_normal())
        radius = max(radius, 0.07)
        thickness = float(np.clip(0.10 + 0.09 * rng.random(), 0.07, 0.22))
        stone = M.cylinder(radius, radius * (0.86 + 0.12 * rng.random()),
                           thickness, segments=7, uv_scale=1.6, material=material)
        # each course sits a little off-axis, which is what makes a stack of
        # cylinders read as a cairn rather than as a column
        stone.transform(M.rotation_y(rng.random() * math.tau))
        stone.transform(M.translation(0.045 * rng.standard_normal(), y,
                                      0.045 * rng.standard_normal()))
        pieces.append(stone)
        y += thickness * (0.90 + 0.10 * rng.random())
    capstone = M.icosphere(0.13, subdivisions=1, material=material)
    capstone.transform(M.scaling(1.25, 0.62, 1.05))
    capstone.transform(M.translation(0.0, y + 0.04, 0.0))
    pieces.append(capstone)
    return M.merge(pieces, material=material)


def waystone(height: float = 2.3, seed: int = 0) -> SW.MeshGroup:
    """A dressed standing stone with a carved band and an inset crystal.

    Panels 5 and 8 show these at the cairn fields and along the base of the
    frozen falls, glowing faintly blue.
    """
    rng = _rng(seed)
    group = SW.MeshGroup()
    taper = 0.62 + 0.10 * rng.random()
    shaft = M.cylinder(0.34, 0.34 * taper, height, segments=6, uv_scale=1.3,
                       material=STONE)
    shaft.transform(M.rotation_y(rng.random() * math.tau))
    group.add(shaft)
    group.add(M.box((0.92, 0.16, 0.92), center=(0.0, 0.08, 0.0),
                    uv_scale=1.0, material=RUBBLE))
    band = M.cylinder(0.37, 0.37, 0.14, segments=6, uv_scale=1.6, material=BRASS)
    band.transform(M.translation(0.0, height * 0.62, 0.0))
    group.add(band)
    gem = M.icosphere(0.10, subdivisions=1, material=CRYSTAL)
    gem.transform(M.translation(0.0, height * 0.78, 0.30 * taper))
    group.add(gem)
    return group


# --------------------------------------------------------------------------
# the rope bridges - the one piece that carries a walk surface
# --------------------------------------------------------------------------
def rope_bridge(length=22.0, width=1.9, sag=1.5, seed=0, deck_y=0.0, rise=0.0):
    """Whitehorn palette for the shared continuous suspension bridge."""
    from amberwood.mountaincraft import suspension_bridge
    return suspension_bridge(length,width,sag,seed,deck_y,rise,
            stone=RUBBLE,timber=TIMBER,posts=TIMBER_DARK,rope=ROPE,iron=IRON)


# --------------------------------------------------------------------------
# the mine - panel 7
# --------------------------------------------------------------------------
def mine_portal(seed: int = 0, width: float = 3.6, height: float = 3.9,
                rail_length: float = 9.0) -> SW.MeshGroup:
    """Timber-framed adit mouth cut into a rock face, with rails running out.

    Built facing -Z so it can be rotated to face the road like every other
    landmark in the region.
    """
    rng = _rng(seed)
    group = SW.MeshGroup()
    half_w = width * 0.5

    # the dressed stone surround the timbers are set into
    group.add(M.box((width + 2.4, height + 1.3, 1.5),
                    center=(0.0, (height + 1.3) * 0.5, 0.55),
                    uv_scale=1.1, material=RUBBLE))
    # the dark of the tunnel: a recessed box, not a hole, so the silhouette
    # reads from outside without needing an interior
    # A deep recess, not a shallow panel: at 2.6 m deep and lit from outside
    # the face still caught the sun and read as a tan board across the
    # opening. Six metres back puts it in its own shadow.
    # `timber_dark` is a warm brown, not a dark: lit from outside it read as
    # a tan board across the opening rather than as a hole. `dark_iron` is the
    # darkest material in the pinned set and is what makes the adit read.
    group.add(M.box((width, height, 6.0), center=(0.0, height * 0.5, 1.6),
                    uv_scale=1.0, material=IRON))

    # heavy timber frame - two posts and a lintel, braced
    for side in (-1.0, 1.0):
        post = M.box((0.34, height, 0.42),
                     center=(side * (half_w + 0.17), height * 0.5, -0.1),
                     uv_scale=1.3, material=TIMBER_DARK)
        group.add(post)
        brace = M.box((0.24, 0.24, 1.1),
                      center=(side * (half_w - 0.1), height * 0.86, 0.32),
                      uv_scale=1.2, material=TIMBER)
        brace.transform(M.translation(0.0, 0.0, 0.0))
        group.add(brace)
    lintel = M.box((width + 1.0, 0.42, 0.62),
                   center=(0.0, height + 0.21, -0.1),
                   uv_scale=1.2, material=TIMBER_DARK)
    group.add(lintel)
    group.add(M.box((width + 1.4, 0.22, 0.48),
                    center=(0.0, height + 0.55, -0.05),
                    uv_scale=1.1, material=TIMBER))

    # rails running out of the adit
    for side in (-1.0, 1.0):
        rail = M.box((0.09, 0.09, rail_length),
                     center=(side * 0.62, 0.09, -1.0 - rail_length * 0.5),
                     uv_scale=2.2, material=IRON)
        group.add(rail)
    sleepers = []
    count = max(4, int(rail_length / 1.15))
    for i in range(count):
        z = -1.4 - (i + 0.5) * (rail_length / count)
        sleepers.append(M.box((1.9, 0.10, 0.24), center=(0.0, 0.04, z),
                              uv_scale=1.4, material=TIMBER))
    group.add(M.merge(sleepers, material=TIMBER))

    # The sleepers sit in a real bed of compacted spoil. Its exposed walking
    # surface reaches the front of the recess; the dark tunnel itself remains
    # solid. This narrow authored bed survives the landmark's broad blocker.
    group.add_walk(M.box((3.2, 0.18, 9.0), center=(0.0, 0.02, -5.9),
                         uv_scale=1.1, material=RUBBLE))

    # spoil heaps either side of the mouth
    for side in (-1.0, 1.0):
        heap = M.icosphere(1.5, subdivisions=1, material=RUBBLE)
        heap.transform(M.scaling(1.5, 0.42, 1.2))
        heap.transform(M.translation(side * (half_w + 2.3), 0.1,
                                     -2.2 - rng.random()))
        group.add(heap)
    return group


# --------------------------------------------------------------------------
# ice - panels 6 and 8
# --------------------------------------------------------------------------
def _icicle_fringe(span: float, count: int, seed: int, drop: float = 1.5,
                   y: float = 0.0, material: str = ICE) -> M.Mesh:
    rng = _rng(seed)
    spikes = []
    for i in range(count):
        x = -span * 0.5 + span * ((i + 0.5) / count)
        length = drop * (0.35 + 0.75 * rng.random())
        radius = 0.05 + 0.10 * rng.random()
        spike = M.cylinder(radius, 0.012, length, segments=5, uv_scale=1.5,
                           material=material)
        spike.transform(M.rotation_x(math.pi))
        spike.transform(M.translation(x + 0.08 * rng.standard_normal(), y,
                                      0.16 * rng.standard_normal()))
        spikes.append(spike)
    return M.merge(spikes, material=material)


def ice_cave_mouth(seed: int = 0, span: float = 7.5,
                   height: float = 5.2, approach_drop: float = 0.0) -> SW.MeshGroup:
    """A cavern opening in blue ice, fringed with icicles. Panel 6.

    Faces -Z. The first version was a single icosphere with a throat pushed
    into it, which rendered as a plain pale ball: the opening was swallowed by
    the mass and nothing read as a cave at all. This builds the mouth as a
    dark arched void framed by ice, which is what makes an opening legible
    from outside without an interior behind it.
    """
    rng = _rng(seed)
    group = SW.MeshGroup()
    half = span * 0.5

    # The ice mass, as two flanking shoulders and a lintel rather than one
    # ball, so there is an actual hole between them.
    for side in (-1.0, 1.0):
        shoulder = M.icosphere(span * 0.46, subdivisions=2, material=ICE)
        shoulder.transform(M.scaling(0.85, 1.25, 1.05))
        shoulder.transform(M.translation(side * (half + span * 0.20),
                                         height * 0.42, 1.4))
        group.add(shoulder)
    brow = M.icosphere(span * 0.55, subdivisions=2, material=ICE)
    brow.transform(M.scaling(1.35, 0.55, 1.0))
    brow.transform(M.translation(0.0, height * 0.95, 1.5))
    group.add(brow)

    # the void: a dark recess the shoulders frame, set back from the lip
    group.add(M.box((span * 0.78, height * 0.86, 5.0),
                    center=(0.0, height * 0.43, 3.1),
                    uv_scale=1.0, material=IRON))
    # a floor of trodden ice running out of it
    floor = M.box((span * 0.80, 0.25, 6.0), center=(0.0, 0.12, 1.4),
                  uv_scale=1.4, material=ICE)
    group.add_walk(floor)
    # Nine low cut-ice treads lead from the natural shelf to the trodden lip.
    # The larger western cave's shelf descends in front of its mouth; the
    # smaller watch cave only needs a shallow continuation of its ice apron.
    approach = M.stairs(span * 0.68, (0.245 + approach_drop) / 9.0,
                        0.60, 9, uv_scale=1.4, material=ICE)
    approach.transform(M.translation(0.0, -approach_drop, -7.0))
    group.add_walk(approach)

    # broken ice around the lip, and the icicle fringe over the opening
    shards = []
    for i in range(16):
        angle = math.pi * (i / 15.0)
        radius = half * (1.02 + 0.16 * rng.random())
        shard = M.icosphere(0.30 + 0.34 * rng.random(), subdivisions=1,
                            material=ICE)
        shard.transform(M.scaling(0.7, 1.6, 0.7))
        shard.transform(M.translation(math.cos(angle) * radius,
                                      height * 0.30
                                      + math.sin(angle) * height * 0.62,
                                      0.35))
        shards.append(shard)
    group.add(M.merge(shards, material=ICE))
    group.add(_icicle_fringe(span * 0.80, 18, seed + 5, drop=2.0,
                             y=height * 0.86, material=ICE))

    # lanterns at the mouth, as panel 6 has them
    for side in (-1.0, 1.0):
        post = M.cylinder(0.07, 0.06, 1.1, segments=6, uv_scale=1.2,
                          material=IRON)
        post.transform(M.translation(side * (half * 0.72), 0.0, -1.2))
        group.add(post)
        glow = M.icosphere(0.16, subdivisions=1, material=AMBER)
        glow.transform(M.translation(side * (half * 0.72), 1.22, -1.2))
        group.add(glow)
    return group


def frozen_cascade(width: float = 9.0, height: float = 16.0,
                   seed: int = 0, include_pool: bool = True) -> SW.MeshGroup:
    """A waterfall caught mid-fall, on the cliff it falls down. Panels 3 and 8.

    Two things the first version got wrong. It was built as a handful of fat
    lathed lobes, which read as flat cardboard slabs rather than ice; and it
    carried no rock, so it stood free on open snow instead of pouring down a
    face. An icefall is only legible against the cliff it hangs on, so the
    cliff is part of the piece.

    Built facing -Z. Structural throughout - never a walk surface.
    """
    rng = _rng(seed)
    group = SW.MeshGroup()

    # The cliff the ice hangs on. Sized to the fall and no larger: at
    # width*1.9 by height*2.2 this was a 44 m wall that filled the whole
    # frame and hid the ice it was supposed to back. Its top sits just above
    # the lip, and it runs 6 m below grade so it never floats.
    cliff_h = height * 1.06
    group.add(M.box((width * 1.25, cliff_h + 6.0, 2.6),
                    center=(0.0, cliff_h * 0.5 - 6.0, 2.3),
                    uv_scale=1.2, material=ROCK))

    # many thin columns, overlapping, at varied depth and height
    columns, caps = [], []
    count = max(10, int(width * 2.2))
    for i in range(count):
        x = -width * 0.5 + width * (i / float(count - 1))
        radius = width / count * (0.85 + 0.9 * rng.random())
        drop = height * (0.55 + 0.45 * rng.random())
        z = 0.35 + rng.random() * 0.7
        rings = 9
        profile = []
        for r in range(rings):
            t = r / (rings - 1.0)
            # bulge near the top, taper to a point: the shape meltwater makes
            bulge = 1.0 + 0.35 * (1.0 - abs(t - 0.22) / 0.6 if t < 0.82 else 0.0)
            profile.append([max(radius * bulge * (1.0 - 0.72 * t ** 1.7), 0.02),
                            -drop * t])
        column = M.lathe(profile, segments=9, uv_scale=1.4, material=ICE)
        column.transform(M.rotation_y(rng.random() * math.tau))
        column.transform(M.translation(x + 0.12 * rng.standard_normal(),
                                       height, z))
        columns.append(column)
        # a snow cap where the flow goes over the lip
        cap = M.icosphere(radius * 1.25, subdivisions=1, material=SNOW)
        cap.transform(M.scaling(1.2, 0.5, 1.0))
        cap.transform(M.translation(x, height + 0.15, z + 0.2))
        caps.append(cap)
    group.add(M.merge(columns, material=ICE))
    group.add(M.merge(caps, material=SNOW))

    # the frozen pool the fall lands in, and broken ice around it
    pool = M.cylinder(width * 0.62, width * 0.70, 0.5, segments=14,
                      uv_scale=1.6, material=ICE)
    pool.transform(M.translation(0.0, 0.0, -0.6))
    if include_pool:
        group.add(pool)
    rubble = []
    for _ in range(8):
        block = M.icosphere(0.35 + 0.5 * rng.random(), subdivisions=1,
                            material=ICE)
        block.transform(M.translation((rng.random() - 0.5) * width * 1.3,
                                      0.25, -1.4 - rng.random() * 1.6))
        rubble.append(block)
    group.add(M.merge(rubble, material=ICE))
    group.add(_icicle_fringe(width, count * 2, seed + 11, drop=2.6,
                             y=height * 0.30, material=ICE))
    return group


# --------------------------------------------------------------------------
# the shrines and the temple - panels 2 and 4
# --------------------------------------------------------------------------
def shrine_alcove(seed: int = 0, width: float = 5.4,
                  height: float = 5.0) -> SW.MeshGroup:
    """A statue standing in an arched recess, with steps and two braziers.

    Panel 4. Faces -Z.
    """
    group = SW.MeshGroup()
    half = width * 0.5

    group.add(M.box((width + 1.6, 0.55, 3.4), center=(0.0, 0.27, 0.9),
                    uv_scale=1.1, material=STONE))
    # the back mass the alcove is cut into
    group.add(M.box((width + 1.6, height + 1.2, 1.7),
                    center=(0.0, (height + 1.2) * 0.5, 2.1),
                    uv_scale=1.1, material=STONE))
    # the recess itself
    group.add(M.box((width - 1.0, height - 0.9, 1.3),
                    center=(0.0, (height - 0.9) * 0.5 + 0.55, 1.55),
                    uv_scale=1.0, material=MARBLE))
    # the arch ring over it - built in XY and extruded along Z, which is the
    # orientation mesh.arch is designed for, so it is used as-is here
    ring = M.arch(width - 1.0, (width - 1.0) * 0.5, 0.5, 1.4, segments=14,
                  uv_scale=1.1, material=STONE)
    ring.transform(M.translation(0.0, height - 0.9 + 0.55, 1.55))
    group.add(ring)

    figure = SW.statue(height=height * 0.52, seed=seed, plinth_height=0.85)
    figure.transform(M.translation(0.0, 0.55, 1.7))
    group.add(figure)

    for side in (-1.0, 1.0):
        group.add(M.box((0.5, 0.5, 0.5),
                        center=(side * (half + 0.35), 0.8, 0.55),
                        uv_scale=1.0, material=STONE))
    return group


def glacier_temple(seed: int = 0, width: float = 20.0,
                   height: float = 15.0) -> SW.MeshGroup:
    """The region's primary landmark. Panel 2.

    A marble facade set into the mountain: a tall pointed opening glowing
    blue, flanking robed figures on plinths, braziers, and a broad stair up
    to an inlaid forecourt. Faces -Z, so the approach reads as the panel does.

    The stair treads are registered as a walk surface; the facade, columns and
    roof are not, so the grounding ray cannot put an actor on the pediment.
    """
    group = SW.MeshGroup()
    half = width * 0.5

    # -- podium and the stair up to it ------------------------------------
    podium_h = 2.1
    group.add(M.box((width + 5.0, podium_h, 13.0),
                    center=(0.0, podium_h * 0.5, 3.0),
                    uv_scale=1.2, material=STONE))
    stair = M.stairs(width * 0.52, podium_h / 12.0, 0.36, 12, uv_scale=1.1,
                     material=MARBLE)
    # mesh.stairs climbs toward +Z from y=0, so the foot has to be placed
    # outside the podium by the full run or it climbs into its own mass
    run_length = 12 * 0.36
    stair.transform(M.translation(0.0, 0.0, -3.6 - run_length))
    group.add_walk(stair)

    # the forecourt deck, walkable, with the circular inlay of the panel
    # The old deck started 0.4 m beyond the top tread. Extend the real marble
    # lip to overlap it, rather than opening the unsupported folded grid row.
    group.add_walk(M.box((width + 4.4, 0.12, 13.0),
                         center=(0.0, podium_h + 0.06, 2.7),
                         uv_scale=1.4, material=MARBLE))
    inlay = M.cylinder(4.4, 4.4, 0.05, segments=32, uv_scale=2.2,
                       material=BRASS)
    # Inset the metal into the marble: its top sits 3 cm above the walking
    # plane. The former 8 cm air gap made the entire forecourt a low obstacle.
    inlay.transform(M.translation(0.0, podium_h + 0.10, 1.2))
    group.add(inlay)

    # -- the facade --------------------------------------------------------
    facade_y = podium_h
    group.add(M.box((width, height, 2.4),
                    center=(0.0, facade_y + height * 0.5, 8.2),
                    uv_scale=1.2, material=MARBLE))
    # The mountain the facade is cut into, so it is not a free-standing slab.
    # It runs 30 m below grade: the shelf falls away behind the temple, and a
    # mass sized only to the facade leaves the whole building visibly floating
    # from the valley below.
    group.add(M.box((width + 7.0, height + 34.0, 9.0),
                    center=(0.0, facade_y + height * 0.5 - 13.0, 13.0),
                    uv_scale=1.1, material=ROCK))

    # the doorway: a tall opening with a glowing crystal plane behind it
    door_w, door_h = 4.6, 8.4
    # The facade's front face is at local z = 7.0. The crystal has to stand
    # proud of it, not flush with it: at 7.4 it sat 0.1 m *behind* the face and
    # the glowing portal - the whole point of panel 2 - was invisible.
    group.add(M.box((door_w, door_h, 1.1),
                    center=(0.0, facade_y + door_h * 0.5, 6.65),
                    uv_scale=1.0, material=CRYSTAL))
    ring = M.arch(door_w + 1.2, (door_w + 1.2) * 0.55, 0.62, 2.6, segments=16,
                  uv_scale=1.1, material=STONE)
    ring.transform(M.translation(0.0, facade_y + door_h, 6.6))
    group.add(ring)

    # -- flanking figures, columns and braziers ---------------------------
    for side in (-1.0, 1.0):
        figure = SW.statue(height=4.6, seed=seed + int(side) + 3,
                           plinth_height=1.6)
        figure.transform(M.translation(side * (half - 3.0), facade_y + 0.12, 6.0))
        group.add(figure)

        col = SW.column(height=height * 0.72, radius=0.62, flutes=12,
                        material=MARBLE)
        col.transform(M.translation(side * (half - 0.9), facade_y + 0.12, 7.0))
        group.add(col)

        for offset in (0.0, 5.2):
            bowl = M.lathe([[0.0, 0.0], [0.46, 0.12], [0.52, 0.40], [0.47, 0.48]],
                           12, uv_scale=1.4, material=BRASS)
            bowl.transform(M.translation(side * (half - 1.4),
                                         facade_y + 1.05, 2.4 + offset))
            group.add(bowl)
            stem = M.cylinder(0.16, 0.13, 1.05, segments=8, uv_scale=1.3,
                              material=IRON)
            stem.transform(M.translation(side * (half - 1.4), facade_y + 0.12,
                                         2.4 + offset))
            group.add(stem)
            flame = M.icosphere(0.30, subdivisions=1, material=CRYSTAL)
            flame.transform(M.translation(side * (half - 1.4),
                                          facade_y + 1.62, 2.4 + offset))
            group.add(flame)

    # -- the crowning mass, snow-capped -----------------------------------
    group.add(M.box((width + 2.0, 1.1, 3.2),
                    center=(0.0, facade_y + height + 0.55, 8.0),
                    uv_scale=1.2, material=STONE))
    cap = M.box((width + 2.4, 0.42, 3.4),
                center=(0.0, facade_y + height + 1.30, 8.0),
                uv_scale=1.2, material=SNOW)
    group.add(cap)
    group.add(_icicle_fringe(width, 18, seed + 7, drop=1.3,
                             y=facade_y + height + 1.05))
    return group


def gate_arch(seed: int = 0, span: float = 6.0,
              height: float = 8.0) -> SW.MeshGroup:
    """The southern gate the approach road passes through. Panel 1.

    Two piers, a lintel and a pair of cairn-topped side walls. Deliberately
    lighter than the temple: this is the threshold, not the destination.
    """
    group = SW.MeshGroup()
    half = span * 0.5
    for side in (-1.0, 1.0):
        pier = M.box((1.5, height, 1.9),
                     center=(side * (half + 0.75), height * 0.5, 0.0),
                     uv_scale=1.2, material=STONE)
        group.add(pier)
        cap = M.box((1.9, 0.34, 2.3),
                    center=(side * (half + 0.75), height + 0.17, 0.0),
                    uv_scale=1.1, material=RUBBLE)
        group.add(cap)
        marker = cairn(0.9, seed=seed + int(side) + 11)
        marker.transform(M.translation(side * (half + 0.75), height + 0.34, 0.0))
        group.add(marker)
        wall = M.box((3.4, 1.5, 0.9),
                     center=(side * (half + 3.2), 0.75, 0.0),
                     uv_scale=1.3, material=RUBBLE)
        group.add(wall)
    lintel = M.box((span + 3.2, 1.0, 2.1),
                   center=(0.0, height + 0.5, 0.0), uv_scale=1.2,
                   material=STONE)
    group.add(lintel)
    plaque = M.box((1.5, 0.7, 0.16), center=(0.0, height + 0.5, -1.1),
                   uv_scale=1.0, material=BRASS)
    group.add(plaque)
    return group


def pine(height: float = 7.0, seed: int = 0) -> SW.MeshGroup:
    """A snow-laden conifer, cheap enough to place in the hundreds.

    The toolkit's `trees` module grows broadleaf skeletons with a species
    profile system; a conifer at this density is better served by a few
    stacked cones, which is what the aerial shows on the lower slopes.

    Returned as a MeshGroup, not a merged Mesh: `mesh.merge` collapses every
    part onto the first part's material, which would make the whole tree bark
    coloured. Each material is kept as its own part instead.
    """
    rng = _rng(seed)
    group = SW.MeshGroup()
    group.add(M.cylinder(0.16, 0.07, height * 0.9, segments=5, uv_scale=1.6,
                         material="bark_dark"))
    tiers = max(3, int(height / 1.8))
    foliage, snow = [], []
    for i in range(tiers):
        t = i / float(tiers)
        y = height * (0.22 + 0.68 * t)
        radius = (height * 0.30) * (1.0 - 0.72 * t) * (0.9 + 0.2 * rng.random())
        tier = M.cylinder(radius, 0.02, height * 0.30, segments=7,
                          uv_scale=1.2, material="foliage_green")
        tier.transform(M.rotation_y(rng.random() * math.tau))
        tier.transform(M.translation(0.0, y, 0.0))
        foliage.append(tier)
        # snow sitting on the tier
        cap = M.cylinder(radius * 0.82, 0.02, height * 0.10, segments=7,
                         uv_scale=1.2, material=SNOW)
        cap.transform(M.translation(0.0, y + height * 0.20, 0.0))
        snow.append(cap)
    group.add(M.merge(foliage, material="foliage_green"))
    group.add(M.merge(snow, material=SNOW))
    return group
