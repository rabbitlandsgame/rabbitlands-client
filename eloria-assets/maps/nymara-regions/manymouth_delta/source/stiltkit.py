"""Manymouth Delta's building kit: everything that stands in water.

Companion to `deltakit.py`, which holds the materials. Split because they are
two different kinds of thing and because the material module is the one that has
to be imported before the texture registrars run.

WHY THIS IS NOT IN `_toolkit/` (yet)
------------------------------------
Same reason as `deltakit`: three other region sessions are appending to the
shared kit modules right now, and a fourth concurrent edit to `architecture.py`
and `props.py` is how that table gets silently corrupted. Every piece here is
written to the shared kit's own conventions - a `MeshGroup` with `add_walk` for
anything a character stands on, local space with the origin at the piece's
footprint centre, `Rng(seed)` for all variation - so promoting the module later
is a move rather than a rewrite.

WHAT THE SHARED KIT ALREADY DOES, AND IS USED FOR
-------------------------------------------------
`props.rowing_boat`, `barrel`, `crate`, `basket`, `sack`, `fishing_gear`,
`market_stall`, `fence`, `signpost`, `hanging_lantern`, `undergrowth_patch`,
`boulder`, `rock_cluster`; `architecture.beam`, `post`, `plank_floor`,
`framed_wall`, `door`, `window`, `shutter`, `bracket`, `railing`, `roof`,
`steps`; `stonework.MeshGroup`, `ruin_fragment`, `column`, `retaining_wall`;
`treecraft.suspension_walkway`, `spiral_stair`; `trees.build_tree`.

WHAT IT DOES NOT, AND THIS MODULE ADDS
--------------------------------------
Amberwood's buildings stand on the ground. Every building in this region stands
on piles over moving water, which is not a variation on a lodge - the pile
field, the joist raft, the tidal splash zone and the ladder down to a moored
canoe are the whole vocabulary, and none of it exists in the shared kit.

The tree profiles are the other gap: the shared species are oak, maple, birch,
holly and pine. A delta needs palm, mangrove and banyan, and mangrove in
particular is a tree whose *roots* are the silhouette.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import props as P
from amberwood import waterfront as WF
from amberwood import stonework as SW
from amberwood import trees as TR
from amberwood.noise import Rng
from amberwood.stonework import MeshGroup, group

import deltakit as DK

TEAK = DK.TEAK
BAMBOO = DK.BAMBOO
THATCH = DK.THATCH
BARK = DK.BARK
CARVED = DK.CARVED
BRONZE = DK.BRONZE
GLYPH = DK.GLYPH
LEAF = "foliage_green"
# Palms and nipa get the pinnate frond atlas; the mangrove and the banyan
# are genuine broadleaves and keep the shared spray.
FROND = DK.FROND
BLOSSOM = "foliage_green"
ROPE = "timber_dark"
CLOTH = "canvas_awning"


# ==========================================================================
# tree species
# ==========================================================================
# Registered at import time, into the shared profile table. This is additive
# and idempotent, so it does not conflict with another region's species.

TR.register(TR.TreeProfile(
    # A coconut palm is a hinge, not a tree: one unbranched shaft with a crown
    # of fronds at the top. `first_branch` at 0.93 and a single child level is
    # what produces that, and `branch_droop` is what makes the fronds arch over
    # instead of standing up like a shuttlecock.
    name="delta_palm", height=15.5, trunk_radius=0.30, trunk_sides=8,
    trunk_segments=9, lean=0.26, wander=0.14, taper=0.62,
    first_branch=0.93, children=(9,), branch_pitch=(1.15, 1.42),
    branch_length=0.44, branch_radius=0.30, branch_droop=0.62,
    cluster_size=(2.3, 3.6), clusters_per_tip=3, cluster_planes=2,
    root_count=4, root_spread=0.9, root_rise=0.22,
    bark_material=BARK, foliage_material=FROND,
    canopy_bias=1.0, max_clusters=42))

TR.register(TR.TreeProfile(
    name="delta_palm_young", height=8.2, trunk_radius=0.19, trunk_sides=7,
    trunk_segments=6, lean=0.34, taper=0.66, first_branch=0.90,
    children=(7,), branch_pitch=(1.10, 1.44), branch_length=0.40,
    branch_droop=0.58, cluster_size=(1.5, 2.4), clusters_per_tip=2,
    cluster_planes=2, root_count=3, root_spread=0.6,
    bark_material=BARK, foliage_material=FROND, canopy_bias=0.9,
    max_clusters=18))

TR.register(TR.TreeProfile(
    # Mangrove: short, many low forks, and an enormous root spread. The root
    # parameters carry the whole silhouette of panels 1 and 5 - a mangrove seen
    # from a canoe is mostly stilt roots with a bit of leaf on top.
    name="mangrove", height=7.4, trunk_radius=0.34, trunk_sides=8,
    trunk_segments=6, lean=0.22, wander=0.42, taper=0.30,
    first_branch=0.16, children=(6, 3, 2), branch_pitch=(0.85, 1.35),
    branch_length=0.42, branch_droop=0.30, cluster_size=(1.0, 1.7),
    clusters_per_tip=3, root_count=13, root_spread=3.6, root_rise=1.35,
    bark_material=BARK, foliage_material=LEAF, canopy_bias=0.72,
    max_clusters=54))

TR.register(TR.TreeProfile(
    # The banyan of panel 5, whose aerial roots the landing is built inside.
    name="delta_banyan", height=21.0, trunk_radius=1.45, trunk_sides=12,
    trunk_segments=10, first_branch=0.24, children=(8, 4, 3),
    branch_length=0.52, branch_droop=0.44, cluster_size=(2.2, 3.4),
    clusters_per_tip=3, root_count=15, root_spread=5.4, root_rise=2.1,
    bark_material=BARK, foliage_material=LEAF, canopy_bias=1.25,
    max_clusters=180))

TR.register(TR.TreeProfile(
    # Nipa palm: the low fringing palm that lines every channel edge. Trunkless
    # in life; here a very short shaft so the fronds spray straight off the mud.
    name="nipa", height=3.4, trunk_radius=0.15, trunk_sides=6, trunk_segments=3,
    taper=0.5, first_branch=0.30, children=(8,), branch_pitch=(0.95, 1.40),
    branch_length=0.62, branch_droop=0.34, cluster_size=(1.2, 2.0),
    clusters_per_tip=2, cluster_planes=2, root_count=0,
    bark_material=BARK, foliage_material=FROND, canopy_bias=0.8,
    max_clusters=16))


# ==========================================================================
# the pile vocabulary
# ==========================================================================

def _pile(x: float, z: float, top_y: float, drop: float, radius: float = 0.15,
          seed: int = 0) -> M.Mesh:
    """One driven pile, from the deck down past the waterline into the bed.

    Piles are the single most repeated element in the region, so this is
    deliberately an 6-sided cylinder and nothing else: at 1.7 m eye height the
    silhouette is a dark vertical, and the difference between six sides and
    twelve is forty thousand triangles across the map.
    """
    rng = Rng(seed)
    lean = float(rng.uniform(-0.05, 0.05))
    shaft = M.cylinder(radius * float(rng.uniform(0.92, 1.14)), radius * 0.86,
                       drop, 6, cap_bottom=False, cap_top=False,
                       uv_scale=1.4, material=BARK)
    shaft.translate(0.0, -drop, 0.0)
    shaft.rotate_x(lean)
    return shaft.translate(x, top_y, z)


def pile_field(points, top_y: float, drop: float, radius: float = 0.15,
               seed: int = 0) -> M.Mesh:
    parts = [_pile(float(x), float(z), top_y, drop, radius, seed + i)
             for i, (x, z) in enumerate(points)]
    return M.merge(parts, BARK) if parts else M.Mesh(material=BARK)


def _deck_slab(half_x: float, half_z: float, y: float, seed: int,
               planks: int = 0) -> M.Mesh:
    """Plank decking. Thin, because you see its edge from every boat."""
    if planks <= 0:
        planks = max(3, int(half_z * 2.4))
    return WF.deck_panel(half_x, half_z, y, material=TEAK)


def stilt_deck(half_x: float, half_z: float, drop: float = 3.2, seed: int = 0,
               rails: str = "none", ladder: bool = False,
               pile_spacing: float = 2.6) -> MeshGroup:
    """A rectangular plank platform on a pile field, deck top at y = 0.

    Local origin is the centre of the deck at its walking surface, which is what
    the placement pass wants: it reads the water level and the bed depth, and
    then only has to say where the platform goes.

    `rails` is "none", "rear" (one long side, for a quay you moor against) or
    "all" - a market deck is railed on three sides and open to the water on the
    fourth, and a quay is open on the water side entirely.
    """
    rng = Rng(seed)
    out = MeshGroup()
    deck = _deck_slab(half_x, half_z, 0.0, seed)
    out.add_walk(deck)

    # joists under the boards, running across the short axis
    joists = []
    count = max(2, int(half_x * 2.0 / 1.6))
    for i in range(count + 1):
        x = -half_x + (2.0 * half_x) * i / max(count, 1)
        joists.append(M.box((0.13, 0.19, half_z * 2.0),
                            center=(x, -0.27, 0.0), uv_scale=1.1,
                            material=TEAK))
    joists.append(M.box((half_x * 2.0, 0.16, 0.15), center=(0.0, -0.36, half_z),
                        uv_scale=1.1, material=TEAK))
    joists.append(M.box((half_x * 2.0, 0.16, 0.15), center=(0.0, -0.36, -half_z),
                        uv_scale=1.1, material=TEAK))
    out.add(M.merge(joists, TEAK))

    # the pile field
    points = []
    nx = max(2, int(round(half_x * 2.0 / pile_spacing)) + 1)
    nz = max(2, int(round(half_z * 2.0 / pile_spacing)) + 1)
    for i in range(nx):
        for j in range(nz):
            edge = i in (0, nx - 1) or j in (0, nz - 1)
            if not edge and (i + j) % 2:
                continue          # interior piles thinned; the rim carries it
            points.append((-half_x + 2.0 * half_x * i / (nx - 1),
                           -half_z + 2.0 * half_z * j / (nz - 1)))
    out.add(pile_field(points, -0.36, drop + 0.36, 0.155, seed + 11))

    if rails != "none":
        sides = [(half_z, 0.0), (-half_z, math.pi)] if rails == "rear" else \
            [(half_z, 0.0), (-half_z, math.pi)]
        for offset, yaw in sides[:1] if rails == "rear" else sides:
            piece = A.railing(half_x * 2.0 * 0.96, 0.94,
                              posts=max(3, int(half_x * 1.5)),
                              material=TEAK, style="square", carved=BAMBOO)
            piece.rotate_y(yaw)
            out.add(piece.translate(0.0, 0.0, offset))
        if rails == "all":
            for offset, yaw in ((half_x, math.pi * 0.5),
                                (-half_x, -math.pi * 0.5)):
                piece = A.railing(half_z * 2.0 * 0.90, 0.94,
                                  posts=max(3, int(half_z * 1.5)),
                                  material=TEAK, style="square", carved=BAMBOO)
                piece.rotate_y(yaw)
                out.add(piece.translate(offset, 0.0, 0.0))

    if ladder:
        rungs = []
        side = half_z + 0.10
        for k in range(int(drop / 0.42) + 1):
            rungs.append(M.box((0.62, 0.055, 0.055),
                               center=(0.0, -0.30 - k * 0.42, side),
                               uv_scale=1.0, material=BAMBOO))
        for sx in (-0.30, 0.30):
            rungs.append(M.box((0.07, drop + 0.4, 0.07),
                               center=(sx, -(drop + 0.4) * 0.5, side),
                               uv_scale=1.0, material=BAMBOO))
        out.add(M.merge(rungs, BAMBOO))
    return out


def boardwalk(length: float, width: float = 2.2, drop: float = 3.0,
              seed: int = 0, rails: bool = True,
              drop_end: float | None = None) -> MeshGroup:
    """A plank walkway on piles, running along local +X, deck top at y = 0.

    This is the region's *road*. The concept has no streets; it has a network of
    these, and every junction, market and doorway hangs off one. Built centred
    on the origin so a placement only needs a midpoint and a heading.

    `drop` and `drop_end` are the distances from the deck down to the bed at
    each end, so a run that leaves a bar and crosses a channel gets longer piles
    where the water is deeper instead of a row of stumps hanging in mid-water.
    """
    rng = Rng(seed)
    if drop_end is None:
        drop_end = drop
    out = MeshGroup()
    half_x = length * 0.5
    half_z = width * 0.5

    planks = max(4, int(length / 0.75))
    deck = A.plank_floor(half_x, half_z, 0.0, thickness=0.10, planks=planks,
                         material=TEAK, gap=0.028, seed=seed)
    out.add_walk(deck)

    # stringers along the run and a bearer at each pile bent
    frame = [M.box((length, 0.17, 0.13), center=(0.0, -0.18, z), uv_scale=1.2,
                   material=TEAK) for z in (-half_z + 0.16, half_z - 0.16)]

    bents = max(2, int(round(length / 4.2)) + 1)
    piles = []
    for i in range(bents):
        t = i / max(bents - 1, 1)
        x = -half_x + length * t
        local_drop = drop + (drop_end - drop) * t
        frame.append(M.box((0.15, 0.15, width * 0.96),
                           center=(x, -0.33, 0.0), uv_scale=1.0, material=TEAK))
        for z in (-half_z + 0.20, half_z - 0.20):
            piles.append(_pile(x, z, -0.33, local_drop + 0.33, 0.145,
                               seed + i * 7 + int(z > 0)))
    out.add(M.merge(frame, TEAK))
    if piles:
        out.add(M.merge(piles, BARK))

    if rails:
        # A handrail on one side only, which is what the panels show: two people
        # pass on these, and a rail on both sides makes a 2.2 m walk read as a
        # corridor. Which side alternates so the network does not look extruded.
        side = half_z if rng.chance(0.5) else -half_z
        posts = max(2, int(length / 2.4))
        rail_parts = []
        for i in range(posts + 1):
            x = -half_x + length * i / max(posts, 1)
            rail_parts.append(A.post(x, 0.0, side - math.copysign(0.12, side),
                                     0.98, 0.10, BAMBOO))
        rail_parts.append(M.box((length, 0.07, 0.07),
                                center=(0.0, 0.94, side - math.copysign(0.12, side)),
                                uv_scale=1.0, material=BAMBOO))
        rail_parts.append(M.box((length, 0.06, 0.06),
                                center=(0.0, 0.54, side - math.copysign(0.12, side)),
                                uv_scale=1.0, material=BAMBOO))
        out.add(M.merge(rail_parts, BAMBOO))
    return out


def bamboo_causeway(length: float, width: float = 1.5, seed: int = 0,
                    drop: float = 1.1) -> MeshGroup:
    """The light bamboo walk of panel 7: bunds, paddies and lotus beds.

    Lighter than `boardwalk` in every dimension - split cane rather than sawn
    plank, a thin double handrail, and short legs, because it crosses ankle-deep
    standing water rather than a channel.
    """
    out = MeshGroup()
    half_x = length * 0.5
    half_z = width * 0.5
    deck = A.plank_floor(half_x, half_z, 0.0, thickness=0.07,
                         planks=max(3, int(length / 0.55)), material=BAMBOO,
                         gap=0.02, seed=seed)
    out.add_walk(deck)

    parts = []
    bents = max(2, int(round(length / 2.6)) + 1)
    for i in range(bents):
        x = -half_x + length * i / max(bents - 1, 1)
        for z in (-half_z + 0.12, half_z - 0.12):
            parts.append(M.cylinder(0.075, 0.065, drop + 0.2, 6,
                                    cap_bottom=False, cap_top=False,
                                    uv_scale=1.2, material=BAMBOO)
                         .translate(x, -(drop + 0.2), z))
        parts.append(A.post(x, 0.0, half_z - 0.10, 0.90, 0.075, BAMBOO))
        parts.append(A.post(x, 0.0, -half_z + 0.10, 0.90, 0.075, BAMBOO))
    for z in (half_z - 0.10, -half_z + 0.10):
        for y in (0.86, 0.48):
            parts.append(M.box((length, 0.055, 0.055), center=(0.0, y, z),
                               uv_scale=1.0, material=BAMBOO))
    out.add(M.merge(parts, BAMBOO))
    return out


# ==========================================================================
# buildings
# ==========================================================================

def _hip_thatch(width: float, depth: float, rise: float,
                overhang: float = 0.75) -> M.Mesh:
    """A hipped thatch roof: four slopes to a short ridge.

    `architecture.roof` builds a gable, which is the wrong roof for this region -
    every roof in the board is hipped, deeply overhung, and steep enough to shed
    monsoon rain. Built here as a loft between the eaves rectangle and the ridge
    so the hip lines are real geometry rather than a gable with ends stuck on.
    """
    hw = width * 0.5 + overhang
    hd = depth * 0.5 + overhang
    ridge = max(width * 0.22, 0.35)
    eaves = np.asarray([[-hw, 0.0, -hd], [hw, 0.0, -hd],
                        [hw, 0.0, hd], [-hw, 0.0, hd]])
    top = np.asarray([[-ridge, rise, -0.0], [ridge, rise, -0.0],
                      [ridge, rise, 0.0], [-ridge, rise, 0.0]])
    shell = M.loft([eaves, top], closed_rings=True, cap_ends=False,
                   uv_scale=0.55, material=THATCH)
    # close the ridge and the soffit so the roof is solid from underneath
    cap = M.quad([(-ridge, rise, -0.02), (ridge, rise, -0.02),
                  (ridge, rise, 0.02), (-ridge, rise, 0.02)],
                 uv_scale=0.5, material=THATCH)
    soffit = M.quad([(-hw, 0.0, hd), (hw, 0.0, hd),
                     (hw, 0.0, -hd), (-hw, 0.0, -hd)],
                    uv_scale=0.5, material=THATCH)
    return M.merge([shell, cap, soffit.translate(0,-.10,0)], THATCH)


def stilt_house(width: float = 4.6, depth: float = 4.0, drop: float = 3.4,
                seed: int = 0, veranda: bool = True,
                storeys: int = 1) -> MeshGroup:
    """A dwelling on piles: bamboo walls, hipped thatch, a veranda and a ladder.

    Origin at the veranda deck's walking level, centred on the house footprint.
    The veranda - not the interior - is the walk surface: the houses have no
    interiors in this package, and marking a whole hut walkable would let the
    grounding ray snap a character onto its roof.
    """
    rng = Rng(seed)
    out = MeshGroup()
    floor_y = 0.0
    wall_h = 2.35

    deck_half_x = width * 0.5 + (1.15 if veranda else 0.18)
    deck_half_z = depth * 0.5 + (0.30 if veranda else 0.18)
    platform = stilt_deck(deck_half_x, deck_half_z, drop, seed + 3,
                          rails="none", ladder=True, pile_spacing=2.4)
    # Keep the closed room out of the navigation bucket. The four veranda
    # strips and its inner floor partition the old rectangle without overlap.
    platform.walk_parts=[]
    inner_x,inner_z=width/2+.15,depth/2+.12
    platform.add(WF.deck_panel(inner_x,inner_z,material=TEAK))
    for sign in (-1,1):
        hx=(deck_half_x-inner_x)/2
        platform.add_walk(WF.deck_panel(hx,deck_half_z,material=TEAK)
                          .translate(sign*(inner_x+hx),0,0))
        hz=(deck_half_z-inner_z)/2
        platform.add_walk(WF.deck_panel(inner_x,hz,material=TEAK)
                          .translate(0,0,sign*(inner_z+hz)))
    out.add(platform)

    # walls: framed timber with woven bamboo infill
    solid = []
    for sign in (-1.0, 1.0):
        wall = A.framed_wall(width, wall_h, 0.16, material_frame=TEAK,
                             material_fill=BAMBOO, studs=3, braces=True,
                             seed=seed + int(sign) + 5)
        wall.translate(0.0, floor_y, sign * depth * 0.5)
        solid.append(wall)
    for sign in (-1.0, 1.0):
        wall = A.framed_wall(depth, wall_h, 0.16, material_frame=TEAK,
                             material_fill=BAMBOO, studs=3, braces=True,
                             seed=seed + int(sign) + 9)
        wall.rotate_y(math.pi * 0.5)
        wall.translate(sign * width * 0.5, floor_y, 0.0)
        solid.append(wall)

    door = A.door(0.95, 1.95, 0.10, material=CARVED)
    solid.append(door.translate(0.0, floor_y, depth * 0.5 + 0.02))
    for sx in (-width * 0.28, width * 0.28):
        shutter = A.shutter(0.52, 0.86, material=BAMBOO,
                            angle=float(rng.uniform(0.35, 0.85)))
        solid.append(shutter.translate(sx, floor_y + 1.20,
                                       -depth * 0.5 - 0.04))
    out.add(M.merge(solid, TEAK))

    # upper storey for the larger houses in the town core
    top_y = floor_y + wall_h
    if storeys > 1:
        upper = []
        band = A.plank_floor(width * 0.5 + 0.22, depth * 0.5 + 0.22, top_y,
                             thickness=0.14, planks=6, material=TEAK,
                             gap=0.02, seed=seed + 21)
        upper.append(band)
        for sign in (-1.0, 1.0):
            wall = A.framed_wall(width * 0.86, 1.85, 0.15, material_frame=TEAK,
                                 material_fill=BAMBOO, studs=2, braces=False,
                                 seed=seed + 31 + int(sign))
            wall.translate(0.0, top_y + 0.14, sign * depth * 0.42)
            upper.append(wall)
            side = A.framed_wall(depth * 0.84, 1.85, 0.15, material_frame=TEAK,
                                 material_fill=BAMBOO, studs=2, braces=False,
                                 seed=seed + 41 + int(sign))
            side.rotate_y(math.pi * 0.5)
            side.translate(sign * width * 0.43, top_y + 0.14, 0.0)
            upper.append(side)
        out.add(M.merge(upper, TEAK))
        top_y += 1.99
        roof_w, roof_d = width * 0.86, depth * 0.84
    else:
        roof_w, roof_d = width, depth

    out.add(_hip_thatch(roof_w, roof_d, max(roof_w, roof_d) * 0.46,
                        overhang=0.82).translate(0.0, top_y, 0.0))

    # eave brackets, which is where the carved detail lives in panel 2
    brackets = []
    for sx in (-roof_w * 0.42, roof_w * 0.42):
        for sz in (-roof_d * 0.44, roof_d * 0.44):
            piece = SW.MeshGroup() if False else A.bracket(0.48, CARVED)
            piece.rotate_y(math.atan2(sz, sx))
            brackets.append(piece.translate(sx, top_y - 0.42, sz))
    out.add(M.merge(brackets, CARVED))
    return out


def pagoda_hall(seed: int = 0, base: float = 7.2, tiers: int = 3) -> MeshGroup:
    """The tiered, gilded meeting hall of panel 2 - the town's one landmark.

    Each tier is a smaller hipped roof over an open gallery, so the silhouette
    steps in as it rises and you can see through it at every level, which is
    what the painting shows. The finial is the bronze the material study picks
    out, not gold leaf: the delta's metal is patinated, everywhere.
    """
    rng = Rng(seed)
    out = MeshGroup()
    drop = 3.6

    half = base * 0.5
    platform = stilt_deck(half + 1.3, half + 1.3, drop, seed + 2,
                          rails="none", ladder=False, pile_spacing=2.2)
    out.add(platform)

    y = 0.0
    width = base
    for tier in range(tiers):
        posts = []
        gallery_h = 2.6 - tier * 0.28
        step = width * 0.5
        for sx in (-step, 0.0, step):
            for sz in (-step, 0.0, step):
                if sx == 0.0 and sz == 0.0:
                    continue
                posts.append(A.post(sx, sz, y, gallery_h, 0.17, TEAK))
        out.add(M.merge(posts, TEAK))

        # the gallery balustrade, carved
        rails = []
        for sign, yaw in ((-1.0, math.pi),) if tier == 0 else ((1.0, 0.0), (-1.0, math.pi)):
            piece = A.railing(width * 0.98, 0.88, posts=7, material=CARVED,
                              carved=CARVED)
            piece.rotate_y(yaw)
            rails.append(piece.translate(0.0, y, sign * step))
        for sign, yaw in ((1.0, math.pi * 0.5), (-1.0, -math.pi * 0.5)):
            piece = A.railing(width * 0.98, 0.88, posts=7, material=CARVED,
                              carved=CARVED)
            piece.rotate_y(yaw)
            rails.append(piece.translate(sign * step, y, 0.0))
        out.add(M.merge(rails, CARVED))

        y += gallery_h
        out.add(_hip_thatch(width, width, width * 0.40, overhang=0.95)
                .translate(0.0, y, 0.0))
        # the ridge and hip caps are bronze in the painting, which is what
        # reads as "gilded" at distance
        cap = M.box((width * 0.30, 0.14, 0.22), center=(0.0, 0.0, 0.0),
                    uv_scale=1.0, material=BRONZE)
        out.add(cap.translate(0.0, y + width * 0.40, 0.0))

        if tier == 0:
            floor = A.plank_floor(width * 0.44, width * 0.44, y + 0.10,
                                  thickness=0.13, planks=7, material=TEAK,
                                  gap=0.02, seed=seed + 51)
            out.add(floor)
            y += 0.24
        width *= 0.74

    # the finial: a lathe-turned bronze spike, the tallest thing in the town
    finial = M.lathe([[0.0, 0.0], [0.34, 0.22], [0.20, 0.62], [0.30, 0.86],
                      [0.11, 1.35], [0.16, 1.62], [0.0, 2.45]],
                     segments=10, uv_scale=1.0, material=BRONZE)
    out.add(finial.translate(0.0, y + width * 0.52, 0.0))
    return out


def market_hall(seed: int = 0, span: float = 9.0, length: float = 14.0,
                arches: int = 4) -> MeshGroup:
    """The arched market of panel 4: bent-timber ribs under a taut canopy.

    The ribs are the subject. `mesh.arch` builds in XY and extrudes along Z,
    which is right here - the barrel runs along the walkway - so this does not
    hit the rotation trap the guide warns about for bridges.
    """
    out = MeshGroup()
    rng = Rng(seed)
    drop = 3.2
    deck = stilt_deck(length * 0.5 + 0.6, span * 0.5 + 0.6, drop, seed + 1,
                      rails="none", pile_spacing=2.8)
    out.add(deck)

    ribs = []
    rise = span * 0.46
    for i in range(arches):
        t = i / max(arches - 1, 1)
        x = -length * 0.5 + length * t
        rib = M.arch(span, rise, 0.22, 0.30, segments=16, uv_scale=0.9,
                     material=TEAK)
        rib.rotate_y(math.pi * 0.5)
        ribs.append(rib.translate(x, 0.0, 0.0))
    # purlins tying the ribs together
    for k in range(5):
        angle = math.pi * (k + 1) / 6.0
        px = math.cos(angle) * span * 0.5
        py = math.sin(angle) * rise
        ribs.append(M.box((length, 0.11, 0.11), center=(0.0, py, px),
                          uv_scale=1.0, material=TEAK))
    out.add(M.merge(ribs, TEAK))

    # the canopy itself: a translucent green sheet stretched over the ribs
    sections = []
    steps = 14
    for k in range(steps + 1):
        angle = math.pi * k / steps
        r_x = math.cos(angle) * (span * 0.5 + 0.14)
        r_y = math.sin(angle) * (rise + 0.14)
        sections.append(np.asarray([[-length * 0.5, r_y, r_x],
                                    [length * 0.5, r_y, r_x]]))
    canopy = M.loft(sections, closed_rings=False, cap_ends=False,
                    uv_scale=0.42, material=CLOTH)
    out.add(canopy)
    lining=canopy.copy().translate(0,-.045,0).flip_winding()
    lining.normals *= -1
    out.add(lining)
    return out


def stepped_temple(seed: int = 0, base: float = 26.0, tiers: int = 4,
                   tier_height: float = 3.4) -> MeshGroup:
    """The stepped temple on the aerial's east rim.

    A battered stone mass in four diminishing stages with a bronze-capped
    shrine on top, a stair up the west face, and the glyph banding the ruins
    share. The stair is the only walk surface: the terraces are 3.4 m risers and
    letting the grounding ray find them would put a character on a ledge they
    cannot reach.
    """
    rng = Rng(seed)
    out = MeshGroup()
    y = 0.0
    half = base * 0.5
    for tier in range(tiers):
        batter = half * 0.09
        block = M.loft([
            np.asarray([[-half, 0.0, -half], [half, 0.0, -half],
                        [half, 0.0, half], [-half, 0.0, half]]),
            np.asarray([[-half + batter, tier_height, -half + batter],
                        [half - batter, tier_height, -half + batter],
                        [half - batter, tier_height, half - batter],
                        [-half + batter, tier_height, half - batter]]),
        ], closed_rings=True, cap_ends=True, uv_scale=0.36, material=GLYPH)
        out.add(block.translate(0.0, y, 0.0))
        # a bronze string course at each setback: the aerial's green-gold banding
        band = M.box(((half - batter) * 2.0 + 0.3, 0.22,
                      (half - batter) * 2.0 + 0.3),
                     center=(0.0, y + tier_height - 0.11, 0.0),
                     uv_scale=0.8, material=BRONZE)
        out.add(band)
        y += tier_height
        half = (half - batter) * 0.80

    # the shrine on the summit
    shrine_half = max(half * 0.9, 1.6)
    posts = []
    for sx in (-shrine_half, shrine_half):
        for sz in (-shrine_half, shrine_half):
            posts.append(SW.column(2.6, 0.30, flutes=8, material=GLYPH,
                                   base=True, capital=True)
                         .translate(sx, y, sz))
    out.add(M.merge(posts, GLYPH))
    out.add(_hip_thatch(shrine_half * 2.2, shrine_half * 2.2, shrine_half * 1.1,
                        overhang=0.7).translate(0.0, y + 2.6, 0.0)
            .with_material(BRONZE))
    floor = A.plank_floor(shrine_half, shrine_half, y + 0.06, thickness=0.12,
                          planks=4, material=GLYPH, gap=0.01, seed=seed + 7)
    out.add_walk(floor)

    # the processional stair up the west face, in one flight per tier
    stair_y = 0.0
    stair_half = base * 0.5
    stairs = []
    for tier in range(tiers):
        steps = int(tier_height / 0.24)
        flight = M.stairs(4.6, 0.24, 0.34, steps, uv_scale=0.7, material=GLYPH)
        flight.rotate_y(math.pi * 0.5)
        flight.translate(-stair_half - steps * 0.34 * 0.5 + 0.4, stair_y, 0.0)
        stairs.append(flight)
        stair_y += tier_height
        stair_half = (stair_half - stair_half * 0.09) * 0.80
    out.add_walk(M.merge(stairs, GLYPH))
    return out


# ==========================================================================
# the ruins
# ==========================================================================

def ring_arch(seed: int = 0, radius: float = 9.5, thickness: float = 1.5,
              depth: float = 2.6) -> MeshGroup:
    """The great glyph ring standing out of the whirlpool.

    The aerial's centrepiece and the subject of panel 8: a broken torus of dark
    stone, banded with the teal inlay, its lower third lost in the water. Built
    as a swept ring rather than as `stonework.ancient_arch` because the concept's
    arch is a full circle with a bite out of it, not a doorway.
    """
    rng = Rng(seed)
    out = MeshGroup()

    # The ring, swept as a loft of square sections around an arc that stops
    # short of closing - the break at the top is what makes it read as a ruin.
    start = math.radians(-6.0)
    end = math.radians(186.0)
    sections = []
    steps = 44
    for k in range(steps + 1):
        angle = start + (end - start) * k / steps
        cx = math.cos(angle) * radius
        cy = math.sin(angle) * radius
        # the section thins and roughens toward the broken end
        erosion = 1.0 - 0.34 * max(0.0, (k / steps - 0.72) / 0.28)
        t = thickness * 0.5 * erosion
        d = depth * 0.5 * erosion
        nx, ny = math.cos(angle), math.sin(angle)
        sections.append(np.asarray([
            [cx - nx * t, cy - ny * t, -d],
            [cx + nx * t, cy + ny * t, -d],
            [cx + nx * t, cy + ny * t, d],
            [cx - nx * t, cy - ny * t, d]]))
    ring = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.5,
                  material=GLYPH)
    ring.jitter(0.06, seed=seed + 3)
    out.add(ring)

    # the two piers the ring springs from
    for sign in (-1.0, 1.0):
        pier = M.loft([
            np.asarray([[-2.4, -radius * 0.55, -2.2], [2.4, -radius * 0.55, -2.2],
                        [2.4, -radius * 0.55, 2.2], [-2.4, -radius * 0.55, 2.2]]),
            np.asarray([[-1.5, 0.6, -1.6], [1.5, 0.6, -1.6],
                        [1.5, 0.6, 1.6], [-1.5, 0.6, 1.6]]),
        ], closed_rings=True, cap_ends=True, uv_scale=0.4, material=GLYPH)
        out.add(pier.translate(sign * radius, 0.0, 0.0))

    # fallen voussoirs in the water below the break
    rubble = []
    for i in range(7):
        piece = SW.ruin_fragment(seed + 40 + i, scale=float(rng.uniform(0.6, 1.3)))
        piece.rotate_y(float(rng.uniform(0, math.pi * 2)))
        rubble.append(piece.translate(float(rng.uniform(-radius, radius)),
                                      float(rng.uniform(-radius * 0.7, -radius * 0.3)),
                                      float(rng.uniform(-radius * 0.8, radius * 0.8))))
    out.add(M.merge(rubble, GLYPH).with_material(GLYPH))
    return out


def stele(height: float = 3.6, seed: int = 0) -> M.Mesh:
    """A standing glyph stone. Panels 8 and 9 are full of them, half-drowned."""
    rng = Rng(seed)
    taper = float(rng.uniform(0.55, 0.78))
    shaft = M.loft([
        np.asarray([[-0.46, 0.0, -0.30], [0.46, 0.0, -0.30],
                    [0.46, 0.0, 0.30], [-0.46, 0.0, 0.30]]),
        np.asarray([[-0.46 * taper, height, -0.30 * taper],
                    [0.46 * taper, height, -0.30 * taper],
                    [0.46 * taper, height, 0.30 * taper],
                    [-0.46 * taper, height, 0.30 * taper]]),
    ], closed_rings=True, cap_ends=True, uv_scale=0.7, material=GLYPH)
    shaft.jitter(0.035, seed=seed + 5)
    shaft.rotate_x(float(rng.uniform(-0.10, 0.10)))
    shaft.rotate_z(float(rng.uniform(-0.12, 0.12)))
    shaft.recompute_normals(70.0)
    return shaft


def cave_portal(seed: int = 0, span: float = 6.5, height: float = 7.5) -> MeshGroup:
    """The mouth of the flooded labyrinth: a cut arch in the rock headland.

    The interior it leads to is the `manymouth_flooded_labyrinth` server map,
    not this package - panel 8 is that map's subject. What belongs here is the
    threshold, and enough of the cut face around it that the mouth reads as
    built rather than as a hole.
    """
    out = MeshGroup()
    face = M.box((span + 7.0, height + 3.0, 1.6), center=(0.0, (height + 3.0) * 0.5, 0.0),
                 uv_scale=0.42, material=GLYPH)
    face.jitter(0.09, seed=seed + 2)
    out.add(face)

    opening = M.arch(span, height * 0.52, 0.9, 2.4, segments=16, uv_scale=0.6,
                     material=GLYPH)
    out.add(opening.translate(0.0, height * 0.48, 0.6))

    jambs = []
    for sign in (-1.0, 1.0):
        jambs.append(SW.column(height * 0.48, 0.44, flutes=6, material=GLYPH,
                               base=True, capital=False)
                     .translate(sign * span * 0.5, 0.0, 0.6))
    out.add(M.merge(jambs, GLYPH))

    threshold = A.plank_floor(span * 0.5, 1.5, 0.10, thickness=0.2, planks=3,
                              material=GLYPH, gap=0.0, seed=seed + 9)
    out.add_walk(threshold.translate(0.0, 0.0, 1.8))
    return out


# ==========================================================================
# boats, gear and planting
# ==========================================================================

def dugout(length: float = 6.4, seed: int = 0, carved_prow: bool = True) -> M.Mesh:
    """The long dugout of panel 1, with a raised carved prow.

    `props.rowing_boat` is a clinker-built dinghy: wrong hull, wrong length,
    wrong culture. This is one hollowed log - a narrow lens in plan, almost no
    freeboard amidships, and a prow that rises and is where all the carving is.
    """
    rng = Rng(seed)
    beam_w = length * 0.135
    depth = length * 0.085
    sections = []
    steps = 11
    for k in range(steps + 1):
        t = k / steps
        # plan: a lens, fullest at 0.45 of the length
        w = beam_w * math.sin(math.pi * min(t * 1.08, 1.0)) ** 0.62
        w = max(w, 0.06)
        rise = 0.0
        if t > 0.86:
            rise = ((t - 0.86) / 0.14) ** 2 * depth * 2.1
        elif t < 0.10:
            rise = ((0.10 - t) / 0.10) ** 2 * depth * 0.9
        x = -length * 0.5 + length * t
        sections.append(np.asarray([
            [x, rise - depth, 0.0],
            [x, rise - depth * 0.35, w],
            [x, rise + depth * 0.30, w * 0.92],
            [x, rise + depth * 0.30, -w * 0.92],
            [x, rise - depth * 0.35, -w]]))
    hull = M.loft(sections, closed_rings=True, cap_ends=True, uv_scale=0.8,
                  material=CARVED if carved_prow else TEAK)
    hull.recompute_normals(75.0)
    parts = [hull]
    # thwarts
    for t in (0.32, 0.55, 0.78):
        x = -length * 0.5 + length * t
        parts.append(M.box((0.22, 0.06, beam_w * 1.5), center=(x, depth * 0.16, 0.0),
                           uv_scale=1.0, material=TEAK))
    return M.merge(parts, CARVED if carved_prow else TEAK)


def awning_boat(seed: int = 0, length: float = 6.0) -> MeshGroup:
    """A market boat: a dugout with a cane awning and produce under it (panel 6)."""
    rng = Rng(seed)
    out = MeshGroup()
    out.add(dugout(length, seed, carved_prow=False))
    posts = []
    for sx in (-length * 0.16, length * 0.16):
        for sz in (-length * 0.055, length * 0.055):
            posts.append(A.post(sx, sz, length * 0.085 * 0.3, 1.55, 0.06, BAMBOO))
    out.add(M.merge(posts, BAMBOO))
    awning = M.box((length * 0.44, 0.07, length * 0.20),
                   center=(0.0, length * 0.085 * 0.3 + 1.58, 0.0),
                   uv_scale=1.3, material=CLOTH)
    out.add(awning)
    goods = []
    for i in range(int(rng.integers(3, 6))):
        crate = P.crate(float(rng.uniform(0.32, 0.48)), seed + i * 3,
                        material=BAMBOO)
        crate.rotate_y(float(rng.uniform(0, math.pi)))
        goods.append(crate.translate(float(rng.uniform(-length * 0.2, length * 0.2)),
                                     length * 0.085 * 0.3,
                                     float(rng.uniform(-0.22, 0.22))))
    out.add(M.merge(goods, BAMBOO))
    return out


def net_rack(seed: int = 0, width: float = 3.2) -> MeshGroup:
    """Drying nets on a bamboo frame - the dressing of every quay in the board."""
    rng = Rng(seed)
    out = MeshGroup()
    frame = []
    for sx in (-width * 0.5, width * 0.5):
        frame.append(A.post(sx, 0.0, 0.0, 2.3, 0.09, BAMBOO))
    frame.append(M.box((width, 0.08, 0.08), center=(0.0, 2.26, 0.0),
                       uv_scale=1.0, material=BAMBOO))
    out.add(M.merge(frame, BAMBOO))
    # the net itself: a slack sheet, modelled as a catenary strip
    steps = 10
    sections = []
    for k in range(steps + 1):
        t = k / steps
        x = -width * 0.46 + width * 0.92 * t
        sag = 1.55 * (1.0 - 4.0 * (t - 0.5) ** 2)
        sections.append(np.asarray([[x, 2.20 - sag, -0.30],
                                    [x, 2.20 - sag, 0.30]]))
    net = M.loft(sections, closed_rings=False, cap_ends=False, uv_scale=1.6,
                 material=CLOTH)
    out.add(net)
    return out


def fish_trap(seed: int = 0) -> M.Mesh:
    """A conical woven basket trap, stacked on every quay in the board."""
    rng = Rng(seed)
    trap = M.lathe([[0.0, 0.0], [0.34, 0.06], [0.40, 0.42], [0.30, 0.82],
                    [0.13, 1.02], [0.09, 1.10], [0.0, 1.10]],
                   segments=9, uv_scale=1.2, material=BAMBOO)
    trap.rotate_z(float(rng.uniform(-0.25, 0.25)))
    return trap


def water_jar(seed: int = 0, height: float = 0.78) -> M.Mesh:
    """The big glazed storage jars standing on every deck (panels 5 and 6)."""
    rng = Rng(seed)
    r = height * 0.46
    jar = M.lathe([[0.0, 0.0], [r * 0.55, 0.0], [r * 0.86, height * 0.16],
                   [r, height * 0.44], [r * 0.82, height * 0.74],
                   [r * 0.50, height * 0.92], [r * 0.56, height],
                   [r * 0.44, height]],
                  segments=11, uv_scale=1.0, material=BRONZE)
    jar.rotate_y(float(rng.uniform(0, math.pi * 2)))
    return jar


def _card(width: float, height: float, material: str, cell: int = 0) -> M.Mesh:
    """One alpha-cut card out of the 2x2 foliage atlas."""
    cell_u = 0.5 * (cell % 2)
    cell_v = 0.5 * ((cell // 2) % 2)
    positions = [(-width, 0.0, 0.0), (width, 0.0, 0.0),
                 (width, height, 0.0), (-width, height, 0.0)]
    uvs = [[cell_u, cell_v + 0.5], [cell_u + 0.5, cell_v + 0.5],
           [cell_u + 0.5, cell_v], [cell_u, cell_v]]
    return M.Mesh(np.asarray(positions, dtype=np.float64),
                  np.tile([0.0, 0.0, 1.0], (4, 1)),
                  np.asarray(uvs, dtype=np.float64), None,
                  np.asarray([0, 1, 2, 0, 2, 3], np.int64), material)


def reed_patch(radius: float = 1.4, count: int = 7, seed: int = 0,
               height: float = 1.7) -> M.Mesh:
    """Tall channel-edge reeds and rice grass. Crossed cards, like undergrowth."""
    rng = Rng(seed)
    parts = []
    for i in range(count):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0.0, radius))
        scale = float(rng.uniform(0.7, 1.35))
        for plane in range(2):
            card = _card(0.52 * scale, height * scale, LEAF,
                         int(rng.integers(0, 4)))
            card.rotate_y(float(rng.uniform(0, math.pi)) + plane * math.pi * 0.5)
            parts.append(card.translate(math.cos(angle) * r, 0.0,
                                        math.sin(angle) * r))
    return M.merge(parts, LEAF)


def lotus_bed(radius: float = 2.6, count: int = 9, seed: int = 0) -> M.Mesh:
    """Floating lily pads with a few standing leaves - the subject of panel 7.

    Pads are flat discs rather than cards: they are seen from above from a
    walkway, and a vertical card read edge-on from the causeway above disappears.
    """
    rng = Rng(seed)
    parts = []
    for i in range(count):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0.0, radius))
        pad_r = float(rng.uniform(0.30, 0.62))
        pad = M.cylinder(pad_r, pad_r * 0.97, 0.035, 9, cap_bottom=False,
                         uv_scale=1.8, material=LEAF)
        pad.rotate_x(float(rng.uniform(-0.09, 0.09)))
        parts.append(pad.translate(math.cos(angle) * r, 0.0,
                                   math.sin(angle) * r))
        if rng.chance(0.34):
            # a standing leaf on its stalk
            stalk = M.cylinder(0.022, 0.020, float(rng.uniform(0.35, 0.65)), 5,
                               uv_scale=1.0, material=LEAF)
            cup = M.cylinder(pad_r * 0.72, pad_r * 0.42, 0.10, 9,
                             cap_bottom=False, uv_scale=1.6, material=LEAF)
            h = float(rng.uniform(0.35, 0.65))
            parts.append(stalk.translate(math.cos(angle) * r, 0.0,
                                         math.sin(angle) * r))
            parts.append(cup.translate(math.cos(angle) * r, h,
                                       math.sin(angle) * r))
    return M.merge(parts, LEAF)


def mangrove_thicket(radius: float = 3.2, seed: int = 0) -> M.Mesh:
    """A mat of prop roots without a tree on it.

    The mangrove *profile* grows a whole tree, which is right where one stands
    alone. Along a channel bank what you actually see is the root mat between
    the trunks, and instancing forty trees to get it costs twenty times the
    triangles this does.
    """
    rng = Rng(seed)
    parts = []
    for i in range(int(radius * 5)):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(radius * 0.15, radius))
        top = float(rng.uniform(0.8, 1.9))
        spread = float(rng.uniform(0.5, 1.2))
        path = np.asarray([
            [math.cos(angle) * r, -0.5, math.sin(angle) * r],
            [math.cos(angle) * (r - spread * 0.4), top * 0.55,
             math.sin(angle) * (r - spread * 0.4)],
            [math.cos(angle) * (r - spread), top,
             math.sin(angle) * (r - spread)]])
        parts.append(M.tube(path, [0.085, 0.06, 0.045], segments=5,
                            uv_scale=1.4, material=BARK))
    return M.merge(parts, BARK)


def deck_study(seed: int = 0) -> MeshGroup:
    """The board's material study, built as a vignette on a quay deck.

    Panel 10 is not a place, it is a still life: woven bamboo matting, a coil of
    rope, a verdigris bronze-headed staff and fallen blossom on wet planking.
    Every other panel has a subject somewhere in the region already; this one
    had none, because a material study is not a landmark and nothing in the
    population passes would ever have produced one. So it is authored as a
    single small group and placed once, on the town quay, where the macro
    camera can find it.
    """
    rng = Rng(seed)
    out = MeshGroup()

    # the mat: a thin slab, laid slightly askew
    mat = M.box((2.1, 0.035, 1.45), center=(0.0, 0.017, 0.0), uv_scale=1.6,
                material=BAMBOO)
    out.add(mat.rotate_y(0.16))

    # a coil of rope: three concentric flattened rings
    coils = []
    for i, radius in enumerate((0.40, 0.30, 0.21)):
        ring = M.lathe([[radius - 0.045, 0.0], [radius + 0.045, 0.022],
                        [radius + 0.045, 0.062], [radius - 0.045, 0.084],
                        [radius - 0.062, 0.045]], segments=18, uv_scale=2.4,
                       material=BAMBOO)
        coils.append(ring.translate(0.0, 0.035 + i * 0.055, 0.0))
    out.add(M.merge(coils, BAMBOO).translate(0.62, 0.0, -0.38))

    # the staff: a shaft with a cast bronze head, laid across the mat
    shaft = M.cylinder(0.036, 0.030, 1.55, 8, uv_scale=1.6, material=CARVED)
    shaft.rotate_z(math.pi * 0.5)
    head = M.lathe([[0.0, 0.0], [0.105, 0.03], [0.128, 0.10], [0.112, 0.19],
                    [0.070, 0.235], [0.052, 0.255], [0.0, 0.26]],
                   segments=12, uv_scale=1.2, material=BRONZE)
    head.rotate_z(math.pi * 0.5)
    collar = M.cylinder(0.048, 0.044, 0.10, 10, uv_scale=1.4, material=BRONZE)
    collar.rotate_z(math.pi * 0.5)
    staff = SW.group(shaft.translate(0.0, 0.09, 0.0),
                     head.translate(-0.80, 0.09, 0.0),
                     collar.translate(-0.72, 0.09, 0.0))
    staff.rotate_y(0.42)
    out.add(staff.translate(-0.25, 0.05, 0.10))

    # a scatter of fallen blossom
    petals = []
    for i in range(9):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(0.15, 1.0))
        petal = _card(0.10, 0.10, LEAF, int(rng.integers(0, 4)))
        petal.rotate_x(-math.pi * 0.5)
        petal.rotate_y(float(rng.uniform(0, math.pi * 2)))
        petals.append(petal.translate(math.cos(angle) * r, 0.045,
                                      math.sin(angle) * r))
    out.add(M.merge(petals, LEAF))

    # two water jars at the edge, which is what the panel has in its corner
    out.add(water_jar(seed + 3, 0.52).translate(0.95, 0.0, 0.44))
    out.add(fish_trap(seed + 5).scale(0.72).translate(-1.05, 0.0, -0.50))
    return out
