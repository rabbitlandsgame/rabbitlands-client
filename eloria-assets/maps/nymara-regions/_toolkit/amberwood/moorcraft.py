"""Grey Moors kit: barrows, standing stones, boardwalks, crofts and peat works.

Everything here is modelled from the ten-panel concept detail board. The region
is a drowned burial moor, so the kit is deliberately narrow: granite that has
stood a long time, drystone that is falling down, timber that is permanently
wet, and two kinds of light - votive amber in the barrow mouths and the cold
blue of marsh lights out on the bog.

Two conventions matter for the runtime contract:

* A barrow mound is *terrain*, not a mesh. `region.build_terrain` raises the
  mound as a dome and paints it `terrain.BARROW_TURF`; this module supplies
  only the portal stonework and the kerb standing in it. Modelling the mound as
  geometry would put a dome over ground the grounding ray still hits, and a
  character would walk through the hill.
* Anything a character may stand on goes through `MeshGroup.add_walk`, so it
  exports under the navigation prefix. On this region that is exactly the
  boardwalk decks and the causeway bridge decks - nothing else.
"""
from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from . import trees as TREES
from .noise import Rng
from .stonework import MeshGroup, group

GRANITE = "grey_moor_granite"
CARVED = "grey_carved_stone"
BOG_TIMBER = "grey_bog_timber"
DRYSTONE = "grey_drystone"
TURF_ROOF = "grey_turf_roof"
DEAD_BARK = "grey_dead_bark"
BARROW_TURF = "grey_barrow_turf"
SCRUB = "grey_moor_scrub"
WISP = "grey_wisp"
FLAME = "grey_votive_flame"
BOG_WATER = "grey_bog_water"
IRON = "dark_iron"
ROPE = "timber_grey"

# The doorways in panels 2 and 5 are black holes with light in them. There is
# no interior behind them in the region package - the insides are their own
# maps - so the opening is a dark recessed slab rather than a hole in the mesh.
VOID = "charred_timber"


TREES.register(TREES.TreeProfile(
    name="moor_oak_snag", height=12.5, trunk_radius=1.05, trunk_sides=11,
    trunk_segments=9, lean=0.16, wander=0.34, taper=0.40, first_branch=0.30,
    children=(7, 4, 3), branch_pitch=(0.92, 1.48), branch_length=0.54,
    branch_droop=0.30, root_count=9, root_spread=3.4, root_rise=0.82,
    bark_material=DEAD_BARK, foliage=False, broken_top=False))

TREES.register(TREES.TreeProfile(
    name="moor_thorn_snag", height=5.4, trunk_radius=0.36, trunk_sides=7,
    trunk_segments=6, lean=0.34, wander=0.46, taper=0.30, first_branch=0.24,
    children=(6, 3), branch_pitch=(1.00, 1.52), branch_length=0.44,
    branch_droop=0.34, root_count=4, root_spread=1.5, root_rise=0.44,
    bark_material=DEAD_BARK, foliage=False, broken_top=True))


def _weather(mesh: M.Mesh, amount: float, seed: int) -> M.Mesh:
    """Knock the machine-perfect edges off a stone solid."""
    mesh.jitter(amount, seed=seed)
    mesh.recompute_normals(58.0)
    return mesh


# --------------------------------------------------------------------------
# standing stones
# --------------------------------------------------------------------------

def menhir(height: float = 2.6, seed: int = 0, material: str = GRANITE) -> M.Mesh:
    """One standing stone, after panel 3.

    Built as a lofted slab rather than a box: the stones in the painting are
    split slabs, wider than they are thick, tapering and leaning, with a broken
    irregular crown. A box with jitter reads as a crate.
    """
    rng = Rng(seed)
    width = height * (0.30 + rng.uniform() * 0.20)
    thickness = width * (0.38 + rng.uniform() * 0.24)
    sections = []
    levels = 5
    for index in range(levels):
        t = index / (levels - 1)
        # taper toward the crown, and wander the section off the vertical
        half_w = width * 0.5 * (1.0 - t * (0.24 + rng.uniform() * 0.22))
        half_t = thickness * 0.5 * (1.0 - t * (0.30 + rng.uniform() * 0.20))
        drift_x = (rng.uniform() - 0.5) * width * 0.24 * t
        drift_z = (rng.uniform() - 0.5) * thickness * 0.34 * t
        y = height * t
        ring = []
        for corner_x, corner_z in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            ring.append([drift_x + corner_x * half_w * (0.86 + rng.uniform() * 0.28),
                         y,
                         drift_z + corner_z * half_t * (0.82 + rng.uniform() * 0.36)])
        sections.append(np.array(ring, dtype=np.float64))
    stone = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.55,
                   material=material)
    # a lean, which is most of what makes a stone circle look old
    stone.transform(M.rotation_z((rng.uniform() - 0.5) * 0.20))
    stone.transform(M.rotation_x((rng.uniform() - 0.5) * 0.16))
    stone.transform(M.rotation_y(rng.uniform() * math.tau))
    return _weather(stone, height * 0.014, seed + 7)


def fallen_stone(length: float = 2.4, seed: int = 0) -> M.Mesh:
    """A menhir that has gone over: same slab, lying down and half sunk."""
    stone = menhir(length, seed)
    stone.transform(M.rotation_z(math.pi * 0.5 + (Rng(seed + 3).uniform() - 0.5) * 0.3))
    # sink it into the peat rather than leaving it resting on the surface
    stone.translate(0.0, -length * 0.10, 0.0)
    return stone


def altar_slab(seed: int = 0, span: float = 2.3) -> MeshGroup:
    """The low stone table at the centre of panel 3's ring.

    Three squat uprights carrying a single capstone. Deliberately not a dolmen
    at player height: the painting's slab is knee-high and read over, not
    walked under.
    """
    rng = Rng(seed)
    parts = []
    for index in range(3):
        angle = index * math.tau / 3.0 + rng.uniform() * 0.4
        support = M.box((span * 0.26, 0.52, span * 0.24), uv_scale=0.7,
                        material=GRANITE)
        support.transform(M.rotation_y(angle))
        support.translate(math.cos(angle) * span * 0.30, 0.26,
                          math.sin(angle) * span * 0.30)
        parts.append(support)
    cap = M.box((span, 0.26, span * 0.74), uv_scale=0.5, material=GRANITE)
    cap.transform(M.rotation_z(0.035))
    cap.translate(0.0, 0.64, 0.0)
    parts.append(cap)
    return group(_weather(M.merge(parts, GRANITE), 0.016, seed))


def stone_ring(radius: float = 6.0, count: int = 9, seed: int = 0,
               altar: bool = True, height: float = 2.6) -> MeshGroup:
    """A ring of menhirs, optionally around a slab. Panel 3's set piece."""
    rng = Rng(seed)
    out = MeshGroup()
    for index in range(count):
        angle = index * math.tau / count + (rng.uniform() - 0.5) * 0.16
        # one stone in six has gone over, which is what stops the ring reading
        # as a fence
        stone_height = height * (0.72 + rng.uniform() * 0.62)
        if rng.uniform() < 0.17:
            piece = fallen_stone(stone_height, seed + index * 13)
        else:
            piece = menhir(stone_height, seed + index * 13)
        drift = radius * (0.94 + rng.uniform() * 0.12)
        piece.translate(math.cos(angle) * drift, 0.0, math.sin(angle) * drift)
        out.add(piece)
    if altar:
        out.add(altar_slab(seed + 101, span=max(1.6, radius * 0.38)))
    return out


def stone_avenue(length: float = 24.0, spacing: float = 3.4, width: float = 3.0,
                 seed: int = 0) -> MeshGroup:
    """Two files of stones flanking a route - the avenues on the aerial."""
    rng = Rng(seed)
    out = MeshGroup()
    count = max(2, int(length / spacing))
    for index in range(count):
        z = -length * 0.5 + index * spacing
        for side in (-1.0, 1.0):
            if rng.uniform() < 0.12:
                continue            # gaps, so the file is not a picket fence
            stone = menhir(1.9 + rng.uniform() * 1.5, seed + index * 31 + int(side))
            stone.translate(side * width * 0.5 * (0.9 + rng.uniform() * 0.2), 0.0, z)
            out.add(stone)
    return out


def cairn(height: float = 1.5, seed: int = 0, lit: bool = True) -> MeshGroup:
    """A stacked waymarker cairn, with a votive candle on it (panel 1).

    Stones are stacked as flattened boxes on a shrinking radius, each rotated
    off its neighbour, which is what makes a pile read as built rather than as
    a cone.
    """
    rng = Rng(seed)
    parts = []
    courses = max(3, int(height / 0.24))
    for index in range(courses):
        t = index / max(courses - 1, 1)
        radius = (0.62 + rng.uniform() * 0.10) * (1.0 - t * 0.74)
        stones = max(2, int(7 * (1.0 - t * 0.62)))
        for stone_index in range(stones):
            angle = stone_index * math.tau / stones + t * 2.1 + rng.uniform() * 0.5
            block = M.box((radius * 0.86, 0.20 + rng.uniform() * 0.09,
                           radius * 0.62), uv_scale=1.4, material=GRANITE)
            block.transform(M.rotation_y(angle + rng.uniform() * 0.4))
            block.translate(math.cos(angle) * radius * 0.52,
                            0.11 + index * (height / courses),
                            math.sin(angle) * radius * 0.52)
            parts.append(block)
    out = group(_weather(M.merge(parts, GRANITE), 0.010, seed))
    if lit:
        out.add(votive_candle(seed + 5).translate(0.0, height + 0.02, 0.0))
    return out


def waymarker(height: float = 2.7, seed: int = 0) -> MeshGroup:
    """A tall lit pole. These are the small bright points all over the aerial.

    A leaning timber post with an iron cage lamp - the moor's only road
    furniture, and the thing that makes the routes legible from the air.
    """
    rng = Rng(seed)
    post = M.cylinder(0.17, 0.12, height, 7, uv_scale=1.2, material=BOG_TIMBER)
    post.transform(M.rotation_z((rng.uniform() - 0.5) * 0.13))
    cage = M.lathe([[0.0, 0.0], [0.30, 0.09], [0.33, 0.46], [0.24, 0.64], [0.0, 0.70]],
                   7, uv_scale=1.3, material=IRON)
    cage.translate(0.0, height - 0.08, 0.0)
    flame = M.icosphere(0.21, 1, material=FLAME)
    flame.translate(0.0, height + 0.24, 0.0)
    base = []
    for index in range(5):
        angle = index * math.tau / 5.0 + rng.uniform()
        stone = M.box((0.30, 0.16, 0.24), uv_scale=1.5, material=GRANITE)
        stone.transform(M.rotation_y(angle))
        stone.translate(math.cos(angle) * 0.30, 0.08, math.sin(angle) * 0.30)
        base.append(stone)
    return group(M.merge([post], BOG_TIMBER), cage,
                 _weather(M.merge(base, GRANITE), 0.008, seed + 3), flame)


def votive_candle(seed: int = 0) -> MeshGroup:
    """One stub candle with a flame. The warm points in panels 1, 2, 3 and 5."""
    rng = Rng(seed)
    stub = M.cylinder(0.055, 0.048, 0.13 + rng.uniform() * 0.07, 6, uv_scale=2.0,
                      material="lime_plaster")
    flame = M.icosphere(0.062, 1, material=FLAME)
    flame.translate(0.0, 0.22, 0.0)
    return group(stub, flame)


def candle_cluster(count: int = 5, radius: float = 0.55, seed: int = 0) -> MeshGroup:
    """Several candles set out together, as at the barrow mouths."""
    rng = Rng(seed)
    out = MeshGroup()
    for index in range(count):
        angle = index * math.tau / max(count, 1) + rng.uniform() * 0.7
        distance = radius * (0.30 + rng.uniform() * 0.85)
        piece = votive_candle(seed + index * 17)
        piece.translate(math.cos(angle) * distance, 0.0, math.sin(angle) * distance)
        out.add(piece)
    return out


def wisp(seed: int = 0) -> MeshGroup:
    """A marsh light: the blue-white figures in panel 7.

    Two nested spheres - a small bright core inside a larger dim shell - which
    at distance reads as a glow rather than as a ball.
    """
    rng = Rng(seed)
    # One small sphere, not a core inside a halo. The material is opaque, so a
    # larger outer shell hid the core entirely and the wisp read as a balloon.
    # At player distance the emissive tone does the work, not the silhouette.
    height = 0.95 + rng.uniform() * 0.6
    core = M.icosphere(0.11, 1, material=WISP)
    core.translate(0.0, height, 0.0)
    trail = M.icosphere(0.055, 1, material=WISP)
    trail.translate((rng.uniform() - 0.5) * 0.24, height - 0.28,
                    (rng.uniform() - 0.5) * 0.24)
    return group(core, trail)


# --------------------------------------------------------------------------
# barrows and crypts
# --------------------------------------------------------------------------

def _lintelled_doorway(width: float, height: float, depth: float, seed: int,
                       jamb_material: str = CARVED) -> tuple[list, np.ndarray]:
    """Two uprights and a lintel, with a dark recess behind. Panels 2 and 5."""
    rng = Rng(seed)
    parts = []
    jamb_thickness = width * 0.34
    for side in (-1.0, 1.0):
        jamb = M.box((jamb_thickness, height, depth * 0.9), uv_scale=0.8,
                     material=jamb_material)
        jamb.transform(M.rotation_z(side * (rng.uniform() - 0.5) * 0.05))
        jamb.translate(side * (width * 0.5 + jamb_thickness * 0.5), height * 0.5, 0.0)
        parts.append(jamb)
    lintel = M.box((width + jamb_thickness * 2.4, height * 0.22, depth * 1.05),
                   uv_scale=0.7, material=jamb_material)
    lintel.translate(0.0, height + height * 0.11, 0.0)
    parts.append(lintel)
    # the recess: a dark slab set back between the jambs, plus a sill
    recess = M.box((width, height, 0.12), uv_scale=1.0, material=VOID)
    recess.translate(0.0, height * 0.5, -depth * 0.42)
    parts.append(recess)
    sill = M.box((width + jamb_thickness, 0.14, depth * 0.8), uv_scale=1.0,
                 material=GRANITE)
    sill.translate(0.0, 0.07, 0.0)
    parts.append(sill)
    return parts, np.array([0.0, height * 0.42, -depth * 0.30])


def barrow_portal(width: float = 1.5, height: float = 2.1, seed: int = 0,
                  revetment: float = 5.2, preserve_materials: bool = False) -> MeshGroup:
    """The entrance of panel 2: a stone doorway in a drystone revetted mound.

    The mound itself is terrain (see the module docstring). This is the face
    that is cut into it - a curved drystone retaining arc, the lintelled
    doorway, kerb stones flanking it, and candles on the threshold.
    """
    rng = Rng(seed)
    parts = []
    # The revetment: the drystone face holding the mound back around the mouth.
    # Written as courses along a shallow arc, with block length tied to the
    # course spacing. Deriving both the block count and the arc span from the
    # course index instead made every course a different width, which stacked
    # into a staircase rather than a wall.
    courses = 6
    course_height = 0.30
    block_length = 0.62
    arc_radius = revetment * 0.5
    # how far round the arc reaches, in metres of arc, each side of the door
    arc_reach = revetment * 0.72
    per_side = max(2, int(arc_reach / block_length))
    for course in range(courses):
        y = course_height * (0.5 + course)
        # the face steps back a little as it rises, as a revetment does
        radius = arc_radius + course * 0.055
        # the wall gets shorter toward its ends, so it dies into the mound
        for side in (-1.0, 1.0):
            for index in range(per_side):
                distance = (width * 0.5 + 0.55) + index * block_length
                if course > courses - 1 - index * 0.9:
                    continue        # the ends are lower than the middle
                angle = side * distance / radius
                if abs(angle) > 1.45:
                    continue
                if rng.uniform() < 0.06:
                    continue        # stones out of the face
                block = M.box((block_length * 0.94, course_height * 0.92,
                               0.48 + rng.uniform() * 0.10),
                              uv_scale=1.0, material=DRYSTONE)
                block.transform(M.rotation_y(-angle))
                block.translate(math.sin(angle) * radius, y,
                                math.cos(angle) * radius - arc_radius)
                parts.append(block)
    door_parts, glow_at = _lintelled_doorway(width, height, 0.9, seed + 11)
    parts.extend(door_parts)
    # kerb stones: the ring of upright slabs around a barrow's foot
    if preserve_materials:
        out=group(*[_weather(M.merge([p for p in parts if p.material==material],material),
                             0.012,seed)
                    for material in dict.fromkeys(p.material for p in parts)])
    else:
        out = group(_weather(M.merge(parts, DRYSTONE), 0.012, seed))
    for index in range(6):
        angle = math.pi * (-0.46 + 0.92 * index / 5.0)
        kerb = menhir(0.62 + rng.uniform() * 0.36, seed + 200 + index)
        kerb.translate(math.sin(angle) * revetment * 0.72, 0.0,
                       math.cos(angle) * revetment * 0.72 - revetment * 0.30)
        out.add(kerb)
    glow = M.icosphere(0.30, 1, material=FLAME)
    glow.translate(*glow_at)
    out.add(glow)
    out.add(candle_cluster(4, 0.75, seed + 41).translate(0.0, 0.14, 0.62))
    return out


def crypt_entrance(seed: int = 0, width: float = 1.6, height: float = 2.4,
                   preserve_materials: bool = False) -> MeshGroup:
    """Panel 5: a runed doorway with steps going down and warm light behind.

    The jambs carry the carved stone recipe, and there is a real flight of
    steps in front. The steps are NOT a walk surface - the descent leads to an
    interior map, and marking them walkable would let the grounding ray drop a
    character into the stair well.
    """
    rng = Rng(seed)
    parts = []
    door_parts, glow_at = _lintelled_doorway(width, height, 1.15, seed + 3)
    parts.extend(door_parts)
    # a dressed surround standing proud of the doorway
    for side in (-1.0, 1.0):
        pier = M.box((0.42, height * 1.10, 1.30), uv_scale=0.7, material=CARVED)
        pier.translate(side * (width * 0.5 + 0.92), height * 0.55, 0.10)
        parts.append(pier)
    cap = M.box((width + 2.9, 0.34, 1.5), uv_scale=0.6, material=GRANITE)
    cap.translate(0.0, height * 1.12, 0.10)
    parts.append(cap)
    # the descending flight, cut in front of the threshold
    steps = M.stairs(width * 1.25, 0.19, 0.36, 4, uv_scale=0.9, material=GRANITE)
    steps.transform(M.rotation_y(math.pi))
    steps.translate(0.0, -0.76, 0.86)
    parts.append(steps)
    for side in (-1.0, 1.0):
        cheek = M.box((0.26, 0.9, 1.5), uv_scale=0.9, material=DRYSTONE)
        cheek.translate(side * (width * 0.62 + 0.13), -0.34, 0.86)
        parts.append(cheek)
    if preserve_materials:
        out=group(*[_weather(M.merge([p for p in parts if p.material==material],material),
                             0.008,seed)
                    for material in dict.fromkeys(p.material for p in parts)])
    else:
        out = group(_weather(M.merge(parts, CARVED), 0.008, seed))
    glow = M.icosphere(0.36, 1, material=FLAME)
    glow.translate(*glow_at)
    out.add(glow)
    out.add(candle_cluster(6, 0.95, seed + 61).translate(0.0, 0.02, 1.35))
    return out


# --------------------------------------------------------------------------
# boardwalks and causeways
# --------------------------------------------------------------------------

def boardwalk(length: float = 8.0, width: float = 1.8, deck_height: float = 0.55,
              seed: int = 0, handrail: bool = True) -> MeshGroup:
    """Panel 4: a plank deck on driven posts, with a rope handrail.

    Built along Z and CENTRED on the origin. That matters: the collision pass
    claims a deck's footprint from the placement position using the mesh's
    half-extents, so a deck modelled from one end makes the claim symmetric
    about that end and marks a span's length of open bog behind it walkable at
    deck height. The deck goes through `add_walk`; everything else is
    structure.
    """
    rng = Rng(seed)
    structure = []
    walk = []

    # bearers running the length, on driven posts
    posts = max(2, int(length / 2.1) + 1)
    for index in range(posts):
        z = -length * 0.5 + length * index / max(posts - 1, 1)
        for side in (-1.0, 1.0):
            post = M.cylinder(0.10, 0.085, deck_height + 0.85, 6, uv_scale=1.4,
                              material=BOG_TIMBER)
            post.transform(M.rotation_z((rng.uniform() - 0.5) * 0.10))
            post.translate(side * width * 0.42, -0.80, z)
            structure.append(post)
    for side in (-1.0, 1.0):
        bearer = M.box((0.10, 0.14, length), uv_scale=1.2, material=BOG_TIMBER)
        bearer.translate(side * width * 0.42, deck_height - 0.10, 0.0)
        structure.append(bearer)

    # the deck: individual planks, each with its own gap and tilt, so the walk
    # surface is one mesh but reads as boards
    plank_count = max(2, int(length / 0.34))
    # `M.box` takes FULL extents. Passing `width * 0.5` built a deck half as
    # wide as its own posts, and a plank depth of 40% of the pitch left 60% of
    # the deck as open gaps - which the grounding ray falls straight through,
    # dropping a character off the boardwalk into the bog. The planks are laid
    # nearly touching, with only enough of a seam to read as boards.
    for index in range(plank_count):
        z = -length * 0.5 + (index + 0.5) * length / plank_count
        plank = M.box((width, 0.055, length / plank_count * 0.94),
                      uv_scale=1.0, material=BOG_TIMBER)
        plank.transform(M.rotation_z((rng.uniform() - 0.5) * 0.035))
        plank.translate((rng.uniform() - 0.5) * 0.05, deck_height, z)
        walk.append(plank)

    out = MeshGroup()
    if handrail:
        for side in (-1.0, 1.0):
            for index in range(posts):
                z = -length * 0.5 + length * index / max(posts - 1, 1)
                stanchion = M.cylinder(0.065, 0.055, 0.92, 5, uv_scale=1.6,
                                       material=BOG_TIMBER)
                stanchion.transform(M.rotation_z((rng.uniform() - 0.5) * 0.14))
                stanchion.translate(side * width * 0.42, deck_height, z)
                structure.append(stanchion)
            # the rope, drooping between stanchions
            path = []
            for index in range(posts * 3):
                t = index / max(posts * 3 - 1, 1)
                z = -length * 0.5 + t * length
                sag = math.sin(t * math.pi * posts) * 0.06
                path.append([side * width * 0.42, deck_height + 0.84 - abs(sag), z])
            rope = M.tube(np.array(path), [0.028] * len(path), segments=5,
                          material=ROPE)
            structure.append(rope)
    out.add(_weather(M.merge(structure, BOG_TIMBER), 0.004, seed))
    out.add_walk(M.merge(walk, BOG_TIMBER))
    return out


def causeway_bridge(length: float = 6.0, width: float = 2.6, deck_height: float = 0.9,
                    seed: int = 0) -> MeshGroup:
    """A short stone-piered crossing where a causeway meets open water.

    Heavier than a boardwalk and built of the same flags as the track. Deck is
    walkable; the piers are not.
    """
    rng = Rng(seed)
    structure = []
    # `M.box` takes full extents, so the span and the width go in whole.
    pier_depth = 0.72
    for side in (-1.0, 1.0):
        pier = M.box((width * 1.06, deck_height + 1.1, pier_depth), uv_scale=0.8,
                     material=DRYSTONE)
        pier.translate(0.0, deck_height - (deck_height + 1.1) * 0.5,
                       side * (length * 0.5 - pier_depth * 0.5))
        structure.append(pier)
    deck = M.box((width, 0.22, length), uv_scale=0.7, material="grey_causeway")
    deck.translate(0.0, deck_height, 0.0)
    for side in (-1.0, 1.0):
        kerb = M.box((0.20, 0.26, length), uv_scale=1.0, material=GRANITE)
        kerb.translate(side * (width * 0.5 - 0.10), deck_height + 0.22, 0.0)
        structure.append(kerb)
    out = MeshGroup()
    out.add(_weather(M.merge(structure, DRYSTONE), 0.008, seed))
    out.add_walk(deck)
    return out


# --------------------------------------------------------------------------
# the living moor: crofts, fences, peat works
# --------------------------------------------------------------------------

def cottage_ruin(seed: int = 0, length: float = 7.0, width: float = 4.6,
                 wall_height: float = 2.0) -> MeshGroup:
    """Panel 6: an abandoned croft - drystone walls, roof mostly gone.

    The gable stands, one long wall has slumped, and what is left of the sod
    roof sits over the surviving end.
    """
    rng = Rng(seed)
    parts = []

    # Block size is tied to the spacing in both axes. Sizing the stones
    # independently of the grid they sit on left a 0.30 m stone every 0.62 m
    # on a 0.28 m course, so the walls read as rows of separate posts.
    course_height = 0.26
    block_length = 0.58
    thickness = 0.44

    def wall(x, z, along_x, span, height_scale, ruin_from=1.0):
        courses = max(2, int(round(wall_height * height_scale / course_height)))
        blocks = max(3, int(round(span / block_length)))
        for course in range(courses):
            y = course_height * (0.5 + course)
            for index in range(blocks):
                t = (index + 0.5) / blocks
                # the wall falls away toward one end
                standing = 1.0 - max(0.0, (t - ruin_from) / max(1.0 - ruin_from, 1e-6))
                if course / courses > standing:
                    continue
                if rng.uniform() < 0.05:
                    continue        # stones robbed out of the face
                offset = (t - 0.5) * span
                run = span / blocks * 0.96
                block = M.box((run if along_x else thickness, course_height * 0.94,
                               thickness if along_x else run),
                              uv_scale=1.2, material=DRYSTONE)
                bx = x + (offset if along_x else 0.0)
                bz = z + (0.0 if along_x else offset)
                block.transform(M.rotation_y((rng.uniform() - 0.5) * 0.06))
                block.translate(bx + (rng.uniform() - 0.5) * 0.03, y,
                                bz + (rng.uniform() - 0.5) * 0.03)
                parts.append(block)

    half_l, half_w = length * 0.5, width * 0.5
    wall(0.0, -half_w, True, length, 1.0, 0.72)      # back wall, slumping
    wall(0.0, half_w, True, length, 0.55, 0.40)      # front wall, mostly down
    wall(-half_l, 0.0, False, width, 1.35)           # standing gable end
    wall(half_l, 0.0, False, width, 0.75, 0.60)      # fallen gable end

    # the surviving gable triangle
    gable = M.extrude([[-half_w, 0.0], [half_w, 0.0], [0.0, 1.5]], 0.34,
                      uv_scale=0.9, material=DRYSTONE)
    gable.transform(M.rotation_y(math.pi * 0.5))
    gable.translate(-half_l, wall_height * 1.35, 0.0)
    parts.append(gable)

    out = group(_weather(M.merge(parts, DRYSTONE), 0.010, seed))

    # what is left of the sod roof, over the standing end only
    roof = M.gable_roof(width + 0.5, length * 0.38, 1.5, overhang=0.30,
                        uv_scale=0.7, material=TURF_ROOF)
    roof.transform(M.rotation_y(math.pi * 0.5))
    roof.translate(-half_l + length * 0.19, wall_height * 1.35, 0.0)
    out.add(roof)

    # a couple of fallen roof timbers in the open end
    for index in range(3):
        beam = M.box((0.08, 0.07, width * 0.42), uv_scale=1.4, material=BOG_TIMBER)
        beam.transform(M.rotation_x(0.5 + rng.uniform() * 0.5))
        beam.transform(M.rotation_y(rng.uniform() * 0.9))
        beam.translate(half_l * (0.1 + rng.uniform() * 0.6), 0.30,
                       (rng.uniform() - 0.5) * width * 0.7)
        out.add(beam)
    return out


def peat_fence(length: float = 6.0, seed: int = 0) -> M.Mesh:
    """Leaning posts and a sagging rail - the croft enclosure in panel 6."""
    rng = Rng(seed)
    parts = []
    posts = max(2, int(length / 1.4) + 1)
    tops = []
    for index in range(posts):
        z = -length * 0.5 + length * index / max(posts - 1, 1)
        height = 0.95 + rng.uniform() * 0.35
        post = M.box((0.055, height * 0.5, 0.045), uv_scale=1.8,
                     material=BOG_TIMBER)
        lean = (rng.uniform() - 0.5) * 0.34
        post.transform(M.rotation_x(lean))
        post.translate((rng.uniform() - 0.5) * 0.08, height * 0.5, z)
        parts.append(post)
        tops.append([0.0, height * 0.92, z])
    rail = M.tube(np.array(tops, dtype=np.float64), [0.032] * len(tops),
                  segments=5, material=BOG_TIMBER)
    parts.append(rail)
    return _weather(M.merge(parts, BOG_TIMBER), 0.004, seed)


def peat_cutting(seed: int = 0, span: float = 7.0) -> MeshGroup:
    """Panel 8: stepped peat banks with a timber winch standing over them.

    The stepped bank is geometry laid into a terrace the terrain already cut,
    so the steps read at player scale without the heightfield having to
    resolve them.
    """
    rng = Rng(seed)
    parts = []
    # The bank stands PROUD of the surrounding moor and is cut into from one
    # side, which is what makes it read. Stepping it downward from y=0 buried
    # the whole thing in the ground and left only the winch visible.
    steps = 4
    step_rise = 0.38
    top = steps * step_rise
    for index in range(steps):
        # each step is a slab of the remaining bank, so the cut face is a stair
        remaining = span * 0.62 - index * span * 0.13
        bank = M.box((span, step_rise, remaining), uv_scale=0.8,
                     material="grey_peat_bog")
        bank.translate(0.0, step_rise * (0.5 + index),
                       -(span * 0.62 - remaining) * 0.5)
        parts.append(bank)
    # the flooded trench the peat was lifted out of, in front of the face
    water = M.box((span * 0.92, 0.06, span * 0.30), uv_scale=0.5,
                  material=BOG_WATER)
    water.translate(0.0, 0.05, span * 0.42)
    parts.append(water)

    # cut turves stood on end to dry, the small dark blocks in the panel
    stack = MeshGroup()
    for index in range(12):
        turf = M.box((0.34, 0.22, 0.13), uv_scale=1.8, material="grey_peat_bog")
        turf.transform(M.rotation_y(rng.uniform() * 0.4))
        turf.translate(span * 0.30 + (index % 4) * 0.20 - 0.30,
                       0.11 + (index // 4) * 0.22,
                       span * 0.50 + (rng.uniform() - 0.5) * 0.2)
        stack.add(turf)

    # the winch: an A-frame straddling the face with a windlass and a jib
    frame = []
    foot_z = span * 0.30
    for side in (-1.0, 1.0):
        leg = M.cylinder(0.13, 0.10, 3.4, 6, uv_scale=1.3, material=BOG_TIMBER)
        leg.transform(M.rotation_z(side * 0.24))
        leg.translate(side * 0.80, top, foot_z)
        frame.append(leg)
    # the cross-head, spanning between the leg tops
    head = M.cylinder(0.09, 0.09, 1.7, 6, uv_scale=1.3, material=BOG_TIMBER)
    head.transform(M.rotation_z(math.pi * 0.5))
    head.translate(0.0, top + 3.32, foot_z)
    frame.append(head)
    # the jib, reaching out over the cut face
    jib = M.cylinder(0.085, 0.070, 2.2, 6, uv_scale=1.3, material=BOG_TIMBER)
    jib.transform(M.rotation_x(math.pi * 0.5 - 0.30))
    jib.translate(0.0, top + 3.22, foot_z - 0.95)
    frame.append(jib)
    drum = M.cylinder(0.20, 0.20, 0.9, 8, uv_scale=1.4, material=BOG_TIMBER)
    drum.transform(M.rotation_z(math.pi * 0.5))
    drum.translate(0.0, top + 1.15, foot_z)
    frame.append(drum)
    rope_path = np.array([[0.0, top + 2.90, foot_z - 1.85],
                          [0.0, top + 2.00, foot_z - 1.88],
                          [0.0, top + 1.25, foot_z - 1.86]])
    frame.append(M.tube(rope_path, [0.022, 0.022, 0.022], segments=5, material=ROPE))

    out = MeshGroup()
    out.add(M.merge(parts, "grey_peat_bog"))
    out.add(stack)
    out.add(_weather(M.merge(frame, BOG_TIMBER), 0.004, seed + 3))
    return out


def tower_ruin(seed: int = 0, height: float = 9.0, radius: float = 2.3) -> MeshGroup:
    """A broken drystone tower - the skyline markers all over the aerial.

    The break is authored: the wall runs full height on one side and falls to a
    third of it on the other, because a tower snapped level reads as a chimney.
    """
    rng = Rng(seed)
    parts = []
    courses = max(6, int(height / 0.36))
    blocks_per_course = 15
    for course in range(courses):
        y = 0.18 + course * 0.36
        t = course / max(courses - 1, 1)
        for index in range(blocks_per_course):
            angle = index * math.tau / blocks_per_course + course * 0.13
            # the standing side faces -Z; the broken side falls away
            exposure = 0.5 + 0.5 * math.cos(angle)
            limit = 0.34 + 0.66 * exposure
            if t > limit:
                continue
            if rng.uniform() < 0.05:
                continue        # stones missing out of the face
            block = M.box((radius * 0.30, 0.17, radius * 0.20), uv_scale=1.1,
                          material=DRYSTONE)
            block.transform(M.rotation_y(-angle))
            block.translate(math.cos(angle) * radius, y, math.sin(angle) * radius)
            parts.append(block)
    # rubble at the foot, where the missing half went
    for index in range(14):
        angle = rng.uniform() * math.tau
        distance = radius * (1.05 + rng.uniform() * 1.5)
        stone = M.box((0.28 + rng.uniform() * 0.2, 0.16, 0.22 + rng.uniform() * 0.18),
                      uv_scale=1.3, material=DRYSTONE)
        stone.transform(M.rotation_y(rng.uniform() * math.tau))
        stone.transform(M.rotation_z((rng.uniform() - 0.5) * 0.5))
        stone.translate(math.cos(angle) * distance, 0.09, math.sin(angle) * distance)
        parts.append(stone)
    return group(_weather(M.merge(parts, DRYSTONE), 0.012, seed))


def dead_tree(seed: int = 0, detail: str = "high",
              profile: str = "moor_oak_snag") -> MeshGroup:
    """Panel 7's tree, grown through the toolkit's own skeleton generator."""
    wood, _ = TREES.build_tree(profile, seed=seed, detail=detail)
    return group(wood)


def scrub_clump(seed: int = 0, radius: float = 0.85, cards: int = 3,
                height: float = 0.72) -> M.Mesh:
    """Alpha-cut ground cover: heather, sedge, bog cotton and bracken.

    Cards are pitched off vertical and offset from the cluster centre. A card
    whose centre vertex coincides with the cluster centre yields a zero-length
    normal, which glTF forbids and Godot shades black, so the offsets are never
    allowed to collapse.
    """
    rng = Rng(seed)
    parts = []
    # Which quarter of the atlas this clump draws from, weighted rather than
    # uniform. The atlas is laid out heather / sedge / bog cotton / bracken,
    # and an even draw put white cotton heads on a quarter of every clump on
    # the moor, which read as blossom strewn everywhere. Cotton is a bog plant
    # and it is rare.
    draw = rng.uniform()
    if draw < 0.46:
        cell_u, cell_v = 0.0, 0.0          # heather
    elif draw < 0.76:
        cell_u, cell_v = 0.5, 0.0          # sedge and moor grass
    elif draw < 0.82:
        cell_u, cell_v = 0.0, 0.5          # bog cotton
    else:
        cell_u, cell_v = 0.5, 0.5          # bracken
    for index in range(cards):
        angle = index * math.pi / max(cards, 1) + rng.uniform() * 0.5
        width = radius * (0.85 + rng.uniform() * 0.5)
        card_height = height * (0.75 + rng.uniform() * 0.55)
        offset_x = (rng.uniform() - 0.5) * radius * 0.55
        offset_z = (rng.uniform() - 0.5) * radius * 0.55
        card = M.quad([(-width * 0.5, 0.0, 0.0), (width * 0.5, 0.0, 0.0),
                       (width * 0.5, card_height, 0.0), (-width * 0.5, card_height, 0.0)],
                      uv_scale=1.0, material=SCRUB)
        # map onto one quarter of the atlas
        card.uvs = card.uvs * 0.5 + np.array([cell_u, cell_v])
        card.transform(M.rotation_y(angle))
        card.transform(M.rotation_x((rng.uniform() - 0.5) * 0.16))
        card.translate(offset_x, 0.0, offset_z)
        parts.append(card)
        # Explicit back face rather than a double-sided material. Godot's
        # spatial shader inverts the normal on the back face of a
        # cull-disabled material, so an up-leaning normal becomes a
        # down-leaning one and every card facing away from the light shaded
        # black - which is what the first client captures of this region
        # showed. Two wound-opposite faces are both front faces, and both keep
        # the up-leaning normal that makes ground cover read.
        back = card.copy()
        back.indices = back.indices.reshape(-1, 3)[:, ::-1].reshape(-1)
        parts.append(back)
    clump = M.merge(parts, SCRUB)
    # Bend the card normals toward +Y. A card standing vertically has a
    # horizontal normal, so under an overhead key it receives almost no light,
    # and a double-sided material in Godot does not flip the normal for back
    # faces - the first client capture of this region came back with every
    # scrub clump shaded solid black. Leaning the normals up makes the cards
    # take the sky and the ground the way real ground cover does, and keeps
    # them consistent whichever side is being viewed.
    if clump.vertex_count:
        up = np.array([0.0, 1.0, 0.0])
        blended = clump.normals * 0.22 + up * 0.78
        lengths = np.linalg.norm(blended, axis=1, keepdims=True)
        clump.normals = blended / np.maximum(lengths, 1e-9)
    clump.sanitise_normals()
    return clump


def bog_pool_skin(radius: float = 3.0, seed: int = 0, segments: int = 14) -> M.Mesh:
    """A standing water disc for a pool the terrain has already hollowed.

    Deliberately not a `terrain.water_plane`: the bog pools are small, many,
    and each sits at its own level in its own hollow, so each carries its own
    skin rather than one region-wide sheet.
    """
    rng = Rng(seed)
    ring = []
    for index in range(segments):
        angle = index * math.tau / segments
        r = radius * (0.80 + rng.uniform() * 0.40)
        ring.append([math.cos(angle) * r, 0.0, math.sin(angle) * r])
    centre = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
    positions = np.vstack([centre, np.array(ring, dtype=np.float64)])
    indices = []
    for index in range(segments):
        indices.extend([0, 1 + index, 1 + (index + 1) % segments])
    normals = np.tile(np.array([0.0, 1.0, 0.0]), (positions.shape[0], 1))
    uvs = positions[:, [0, 2]] * 0.18
    mesh = M.Mesh(positions=positions, normals=normals, uvs=uvs,
                  indices=np.array(indices, dtype=np.int64), material=BOG_WATER)
    return mesh
