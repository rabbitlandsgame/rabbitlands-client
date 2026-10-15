"""The Manymouth Delta interiors.

Four authored insides reached from named doors on the 576 m region map. The
room, passage and lamp helpers come from the shared toolkit's `interiors`
module, and the delta's own pieces - piles, plank decking, dugouts, stelae, the
ring arch - come from this region's `stiltkit`, so an inside is built out of the
same vocabulary as the map it opens off. Only the four compositions below are
this region's own.

WHY THESE FOUR
--------------
A region whose interiors are all the same room with different props has no
interiors. These are four different kinds of place, and each answers a question
the exterior raises but cannot answer:

    flooded_labyrinth   drowned, dark, ancient   - what the great arch IS
    smugglers_warren    timber, lamplit, working - what is under the town
    tide_hall           dry, inhabited, warm     - who lives here
    temple_sanctum      monumental, austere, lit - what they believe

The strongest of the four is the labyrinth's gate chamber. The ring-arch that
stands out of the whirlpool on the region map is the *top* of a gate whose lower
half is down here: you row past it for hours on the surface and then walk in
under it. That reversal is the reason the region's centrepiece is worth having
an interior at all.

ON THE CONCEPT ART
------------------
The interior concept package's detail board is truncated to 786,446 bytes and
only the top tenth of each panel decodes - enough to read a palette of wet dark
stone, hanging root, lamplit timber and green water, and nothing else. Its
`concept.json` names ten subjects, and the QA brief describes an authored
delta-smuggler layout of boardwalk crossings over flood channels between
smuggler shelves and cargo caches. Those two, plus the region board's intact
panel 8 - the drowned chamber with the glowing ring - are what these are built
from. The rest is authored. Anything a re-supplied board contradicts should be
changed to match it.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood.interiors import (EYE, Interior, chamber, hanging_lamps,
                                 passage, root_ribs, WALL_T)

import deltakit as DK
import stiltkit as SK

# -- the region's palette, indoors ----------------------------------------
GLYPH = DK.GLYPH
TEAK = DK.TEAK
BAMBOO = DK.BAMBOO
SILT = DK.SILT
SANDBAR = DK.SANDBAR
JUNGLE = DK.JUNGLE
WATER = DK.DELTA_WATER
DEEP = DK.DELTA_DEEP
BRONZE = DK.BRONZE
BARK = DK.BARK
CARVED = DK.CARVED
THATCH = DK.THATCH
CLOTH = "canvas_awning"
BANNER = "woven_cloth"
IRON = "dark_iron"
RUBBLE = "rubble_stone"
# Bulk stone for floors, walls and vaults. NOT the glyph stone: `manymouth_glyph_stone`
# carries an inlaid band of teal strokes, which is exactly right on an arch or a
# stele and completely wrong tiled ten times across a 28 m floor - the first
# render of these rooms came back with cyan dashes over every surface. The glyph
# stone is now reserved for the things that are actually cut with glyphs.
ROCK = "cliff_rock"
LEAF = "foliage_green"
TIMBER_DARK = "timber_dark"


# --------------------------------------------------------------------------
# shared fittings
# --------------------------------------------------------------------------
def flood(x0, z0, x1, z1, y, material=WATER) -> M.Mesh:
    """Standing water inside a room.

    Deliberately not a walk surface and deliberately not sealed to the walls:
    the floor beneath it is the walk surface, so a player wades. Water you
    cannot walk on in a room with no floor under it is a room you fall through.
    """
    return M.box((abs(x1 - x0), 0.06, abs(z1 - z0)),
                 center=((x0 + x1) * 0.5, y, (z0 + z1) * 0.5),
                 uv_scale=0.22, material=material)


def pile_forest(x0, z0, x1, z1, top, drop, seed=0, spacing=3.2) -> M.Mesh:
    """The underside of the town: rank on rank of driven piles.

    The single most important thing in the warren. What makes the space read as
    *under* something rather than as a cellar is that its ceiling is a deck and
    its columns are the same piles you walk past on the surface.
    """
    rng = np.random.default_rng(seed)
    points = []
    x = x0
    while x <= x1:
        z = z0
        while z <= z1:
            points.append((x + float(rng.uniform(-0.7, 0.7)),
                           z + float(rng.uniform(-0.7, 0.7))))
            z += spacing
        x += spacing
    return SK.pile_field(points, top, drop, 0.17, seed)


def deck_ceiling(x0, z0, x1, z1, y, seed=0) -> M.Mesh:
    """Plank decking seen from below - the warren's ceiling is the town's floor."""
    return A.plank_floor(abs(x1 - x0) * 0.5, abs(z1 - z0) * 0.5, y,
                         thickness=0.16, planks=max(6, int(abs(z1 - z0) / 0.8)),
                         material=TEAK, gap=0.03, seed=seed).translate(
        (x0 + x1) * 0.5, 0.0, (z0 + z1) * 0.5)


def crate_stack(count, seed=0, spread=2.2) -> S.MeshGroup:
    """Cargo, stacked the way cargo actually stacks: badly."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    for index in range(count):
        size = float(rng.uniform(0.52, 0.78))
        crate = P.crate(size, seed + index, material=BAMBOO)
        crate.rotate_y(float(rng.uniform(-0.4, 0.4)))
        out.add(crate.translate(float(rng.uniform(-spread, spread)),
                                size * 0.5 * int(rng.integers(0, 3)),
                                float(rng.uniform(-spread, spread))))
    return out


def rope_hank(radius=0.34, seed=0) -> M.Mesh:
    """A coil of rope on a peg. The board's tenth subject is rope and reed."""
    rng = np.random.default_rng(seed)
    rings = []
    for index in range(3):
        r = radius * (1.0 - index * 0.14)
        ring = M.lathe([[r - 0.05, 0.0], [r + 0.05, 0.03], [r + 0.05, 0.08],
                        [r - 0.05, 0.11], [r - 0.07, 0.055]],
                       segments=16, uv_scale=2.2, material=BAMBOO)
        rings.append(ring.translate(0.0, index * 0.06, 0.0))
    out = M.merge(rings, BAMBOO)
    return out.rotate_x(math.pi * 0.5).rotate_y(float(rng.uniform(0, 3.0)))


def tide_post(height=3.2, seed=0) -> S.MeshGroup:
    """A carved post cut with every flood the village remembers.

    Invented for this region, and the one piece of furniture in these interiors
    that could not belong anywhere else: a delta village's history is a list of
    how high the water came.
    """
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    out.add(M.cylinder(0.24, 0.20, height, 10, uv_scale=1.1, material=CARVED))
    for index in range(11):
        y = 0.5 + index * (height - 0.9) / 11.0
        band = M.box((0.54, 0.045, 0.10),
                     center=(0.0, y, 0.20 + float(rng.uniform(0.0, 0.02))),
                     uv_scale=1.0, material=BRONZE)
        out.add(band)
    cap = M.lathe([[0.0, 0.0], [0.26, 0.06], [0.19, 0.22], [0.0, 0.40]],
                  segments=10, uv_scale=1.0, material=BRONZE)
    out.add(cap.translate(0.0, height, 0.0))
    return out


def exit_threshold(kind: str, seed: int = 0) -> S.MeshGroup:
    """Built geometry that says "this is the way out", at every arrival.

    An arrival used to be a bare point in a room. A player who walks in, turns
    around twice and wants to leave has nothing to look for, and on a combined
    insides map with four sections and no connecting corridors that is a real
    problem: there is no wrong door to find by accident, so if the right one is
    invisible there is nothing at all.

    Four kinds, one per section, because the way out of a drowned ruin is not
    the way out of a cellar.
    """
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    if kind == "root-arch":
        # a cut arch with roots through it: the labyrinth's threshold
        out.add(S.ancient_arch(span=3.4, height=4.2, depth=1.1, seed=seed,
                               roots=True, ruined=False))
        for sign in (-1, 1):
            out.add(SK.stele(2.2, seed + 3).translate(sign * 2.6, 0.0, 0.6))
    elif kind == "ladder":
        # the hatch you came down, with daylight implied by the lamp above it
        for k in range(9):
            out.add(M.box((0.78, 0.07, 0.07), center=(0.0, 0.35 + k * 0.42, 0.0),
                          uv_scale=1.0, material=BAMBOO))
        for sx in (-0.36, 0.36):
            out.add(M.box((0.09, 4.2, 0.09), center=(sx, 2.1, 0.0),
                          uv_scale=1.0, material=BAMBOO))
        out.add(M.box((2.2, 0.18, 2.2), center=(0.0, 4.3, 0.0), uv_scale=0.9,
                      material=TEAK))
    elif kind == "doorway":
        # a carved timber door frame with a lintel, the hall's own manner
        for sx in (-1.35, 1.35):
            out.add(M.box((0.30, 3.0, 0.34), center=(sx, 1.5, 0.0),
                          uv_scale=1.0, material=CARVED))
        out.add(M.box((3.2, 0.36, 0.34), center=(0.0, 3.15, 0.0), uv_scale=1.0,
                      material=CARVED))
        out.add(A.bracket(0.5, CARVED).translate(-1.35, 2.7, 0.0))
        out.add(A.bracket(0.5, CARVED).rotate_y(math.pi).translate(1.35, 2.7, 0.0))
    elif kind == "stair-head":
        # two columns and a bronze lintel: the sanctum does not do doors
        for sx in (-2.0, 2.0):
            out.add(S.column(height=4.0, radius=0.42, flutes=10, material=ROCK)
                    .translate(sx, 0.0, 0.0))
        out.add(M.box((4.9, 0.42, 0.62), center=(0.0, 4.2, 0.0), uv_scale=0.8,
                      material=BRONZE))
    elif kind == "drowned-stair":
        # a flight rising out of the water toward a shaft that is not modelled:
        # the way back up to the arch, going nowhere the player can see
        flight = M.stairs(4.0, 0.26, 0.34, 14, uv_scale=0.6, material=ROCK)
        out.add_walk(flight)
        for sx in (-2.4, 2.4):
            out.add(S.column(height=7.0, radius=0.44, flutes=8, material=GLYPH)
                    .translate(sx, 0.0, 2.2))
    return out


SKYLIGHT = {"colour": [0.62, 0.82, 0.86], "range": 34.0, "energy": 3.2}
GATELIGHT = {"colour": [0.34, 0.92, 0.82], "range": 30.0, "energy": 4.0}


def glyph_stele_row(count, spacing, height, seed=0, drown=0.0) -> S.MeshGroup:
    """A line of the region's stelae, optionally standing in water."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    for index in range(count):
        piece = SK.stele(height * float(rng.uniform(0.72, 1.25)), seed + index)
        out.add(piece.translate(0.0, -drown * float(rng.uniform(0.0, 1.0)),
                                index * spacing))
    return out


# ==========================================================================
# 1. The Flooded Labyrinth
# ==========================================================================
def flooded_labyrinth(seed: int = 20260830) -> Interior:
    """Under the rock headland: what the great arch is the top of.

    A drowned processional running down and inward, in water that gets deeper as
    it goes, ending under the gate. The player enters dry, wades, and finishes
    chest-deep looking up at the underside of the thing they rowed past outside.
    """
    it = Interior("manymouth_flooded_labyrinth", "The Flooded Labyrinth",
                  "drowned-ruin", "labyrinth-mouth", [198.0, 9.32, -3.0],
                  "labyrinth-mouth")
    rng = np.random.default_rng(seed)
    g = it.group

    # The floors step down; the water line stays at 0, so depth accumulates.
    it.space("threshold", -6, -7, 6, 6, 0.0, 5.0, floor_mat=ROCK,
             wall_mat=GLYPH, ceil_mat=ROCK, ceiling="vault", vault_rise=2.0,
             doors=[("north", 0.0, 4.0, 3.2)], seed=seed)
    it.space("wading_hall", -13, 20, 13, 50, -1.1, 7.5, floor_mat=SILT,
             wall_mat=ROCK, ceil_mat=ROCK, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 4.0, 3.2), ("north", 0.0, 4.4, 3.4),
                    ("east", 34.0, 3.4, 2.8)], seed=seed + 1)
    it.space("root_chamber", 22, 26, 44, 46, -0.7, 8.5, floor_mat=SILT,
             wall_mat=RUBBLE, ceil_mat=BARK, ceiling="vault", vault_rise=3.6,
             doors=[("west", 34.0, 3.4, 2.8)], seed=seed + 2)
    it.space("stelae_walk", -10, 64, 10, 96, -1.9, 7.0, floor_mat=SILT,
             wall_mat=ROCK, ceil_mat=ROCK, ceiling="vault", vault_rise=2.6,
             doors=[("south", 0.0, 4.4, 3.4), ("north", 0.0, 5.0, 3.8)],
             seed=seed + 3)
    it.space("gate_chamber", -20, 110, 20, 150, -2.8, 15.0, floor_mat=ROCK,
             wall_mat=GLYPH, ceil_mat=ROCK, ceiling="vault", vault_rise=5.5,
             doors=[("south", 0.0, 5.0, 3.8)], seed=seed + 4)

    links = [
        ("descent", (0, 6), (0, 20), 4.0, 0.0, -1.1, 3.6, 7),
        ("rootway", (13, 36), (22, 36), 3.4, -1.1, -0.7, 3.2, 2),
        ("processional", (0, 50), (0, 64), 4.4, -1.1, -1.9, 3.6, 5),
        ("gateway", (0, 96), (0, 110), 5.0, -1.9, -2.8, 4.2, 5),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=ROCK, wall_mat=ROCK, ceil_mat=ROCK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- threshold: dry, cut, and obviously built -------------------------
    g.add(S.ancient_arch(span=4.2, height=4.8, depth=1.4, seed=seed,
                         roots=True, ruined=True).translate(0.0, 0.0, -5.6))
    g.add(exit_threshold("root-arch", seed + 5).translate(0.0, 0.0, -3.2))
    for sign in (-1, 1):
        g.add(S.column(height=4.4, radius=0.42, flutes=6, material=GLYPH)
              .translate(sign * 4.4, 0.0, -2.0))

    # -- wading hall: ankle-deep, piered, roots through the vault ---------
    g.add(flood(-13, 20, 13, 50, -0.15))
    for row in range(5):
        z = 24.0 + row * 6.4
        for sign in (-1, 1):
            g.add(S.column(height=6.2, radius=0.62, flutes=8, material=ROCK)
                  .translate(sign * 8.4, -1.1, z))
    g.add(root_ribs(-13, 20, 13, 50, -1.1, -1.1, 22.0, 7.5,
                    material=BARK, spacing=6.0, seed=seed + 11))
    for index in range(14):
        frag = S.ruin_fragment(seed=seed + 20 + index, scale=1.1)
        for part in (frag.parts if hasattr(frag, "parts") else [frag]):
            part.material = ROCK
        g.add(frag.translate(float(rng.uniform(-11, 11)), -1.1,
                             float(rng.uniform(21, 49))))

    # -- root chamber: the banyan has taken the room ----------------------
    rx, rz = it.centre("root_chamber")
    g.add(flood(22, 26, 44, 46, -0.35))
    bark, foliage = SK.TR.build_tree("delta_banyan", seed + 31, "mid")
    g.add(S.group(bark, foliage).scale(0.9).translate(rx, -0.7, rz))
    for index in range(9):
        angle = 2.0 * math.pi * index / 9.0
        g.add(SK.mangrove_thicket(3.0, seed + 40 + index)
              .translate(rx + math.cos(angle) * 7.0, -0.7,
                         rz + math.sin(angle) * 7.0))
    g.add(root_ribs(22, 26, 44, 46, -0.7, -0.7, 20.0, 8.5,
                    material=BARK, spacing=4.0, seed=seed + 12))

    # -- stelae walk: knee-deep, lined both sides -------------------------
    g.add(flood(-10, 64, 10, 96, -0.15))
    for sign in (-1, 1):
        row = glyph_stele_row(7, 4.4, 3.4, seed + 50 + (sign > 0), drown=0.8)
        g.add(row.translate(sign * 6.4, -1.9, 66.0))
    g.add(root_ribs(-10, 64, 10, 96, -1.9, -1.9, 17.0, 7.0,
                    material=BARK, spacing=7.5, seed=seed + 13))

    # -- gate chamber: the lower half of the ring, from beneath -----------
    gx, gz = it.centre("gate_chamber")
    g.add(flood(-20, 110, 20, 150, -0.15, material=DEEP))
    # the ring itself, inverted so its broken span rises out of the pool:
    # the exterior arch is the top of this, seen from a boat 40 m above.
    arch = SK.ring_arch(seed + 60, radius=10.5, thickness=1.7, depth=3.0)
    arch.rotate_y(math.pi)
    g.add(arch.translate(gx, -1.6, gz))
    # a sunken dais the ring springs from, walkable, a step above the pool
    g.add_walk(M.cylinder(9.0, 8.4, 0.55, 28, uv_scale=0.5, material=ROCK)
               .translate(gx, -2.8, gz))
    for index in range(12):
        angle = 2.0 * math.pi * index / 12.0
        g.add(S.column(height=9.5, radius=0.55, flutes=8, material=ROCK)
              .translate(gx + math.cos(angle) * 16.0, -2.8,
                         gz + math.sin(angle) * 17.0))
    for index in range(6):
        g.add(SK.stele(float(rng.uniform(3.0, 4.8)), seed + 70 + index)
              .translate(gx + float(rng.uniform(-13, 13)), -2.8,
                         gz + float(rng.uniform(-16, 16))))
    # The way up to the surface arch: a flight rising out of the pool on the
    # chamber's far side, which is where a player arriving through the whirlpool
    # comes down and where one leaving that way goes back. The shaft above it is
    # deliberately not modelled - it opens into forty metres of water.
    g.add(exit_threshold("drowned-stair", seed + 80)
          .translate(gx, -2.8, gz + 15.0))
    # offerings left at the gate, half in the water
    for index in range(10):
        angle = 2.0 * math.pi * index / 10.0 + 0.3
        g.add(SK.water_jar(seed + 120 + index, float(rng.uniform(0.45, 0.75)))
              .translate(gx + math.cos(angle) * 7.4, -2.25,
                         gz + math.sin(angle) * 7.4))

    lamp_points = [
        (0.0, 3.0, -4.0), (-3.4, 3.0, 0.0), (3.4, 3.0, 2.0),
        (0.0, 2.2, 12.0),
        (-9.0, 4.2, 23.0), (9.0, 4.2, 23.0), (-9.0, 4.2, 31.0),
        (9.0, 4.2, 31.0), (-9.0, 4.2, 39.0), (9.0, 4.2, 39.0),
        (-9.0, 4.2, 47.0), (9.0, 4.2, 47.0), (0.0, 4.6, 35.0),
        (26.0, 5.2, 30.0), (40.0, 5.2, 30.0), (26.0, 5.2, 42.0),
        (40.0, 5.2, 42.0), (33.0, 6.0, 36.0),
        (0.0, 2.4, 57.0),
        (-6.6, 3.6, 68.0), (6.6, 3.6, 68.0), (-6.6, 3.6, 78.0),
        (6.6, 3.6, 78.0), (-6.6, 3.6, 88.0), (6.6, 3.6, 88.0),
        (0.0, 3.0, 103.0),
        (-15.0, 6.0, 118.0), (15.0, 6.0, 118.0), (-15.0, 6.0, 130.0),
        (15.0, 6.0, 130.0), (-15.0, 6.0, 142.0), (15.0, 6.0, 142.0),
        (0.0, 9.0, 122.0), (0.0, 9.0, 142.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed
    # The ring is the light in the gate chamber. Forty metres square and fifteen
    # high is more room than a hanging lantern can reach across, and the point of
    # the room is that the gate glows.
    it.skylights = [
        {"position": [round(gx, 2), 0.5, round(gz, 2)], **GATELIGHT,
         "energy": 6.5, "range": 44.0},
        {"position": [round(gx, 2), -1.9, round(gz - 6.0, 2)], **GATELIGHT,
         "energy": 3.4},
        {"position": [round(gx - 9.0, 2), 4.0, round(gz, 2)], **GATELIGHT},
        {"position": [round(gx + 9.0, 2), 4.0, round(gz, 2)], **GATELIGHT},
        {"position": [round(gx, 2), 8.0, round(gz - 10.0, 2)], **GATELIGHT},
        {"position": [round(gx, 2), 8.0, round(gz + 10.0, 2)], **GATELIGHT},
    ]

    it.spawn_space = "threshold"
    # A SECOND arrival, and the best portal in the region: the ring that stands
    # out of the whirlpool on the surface is the top of this gate, so going down
    # through it has to land here. Both ends of that transition are geometry
    # that already existed; all this does is admit they are the same object.
    it.extra_arrivals = [("gate-descent", "The Submerged Gate", "gate_chamber",
                          (0.0, -2.75, 145.0), 180.0)]
    # 1.6, not 4.0: the anchor belongs on the dais the ring springs from,
    # not in the middle of the ring, or the runtime check reports it
    # floating three metres above the floor.
    it.landmark("submerged-gate", "The Submerged Gate", "gate_chamber", 1.6)
    it.landmark("root-chamber", "The Root Chamber", "root_chamber", 2.0)
    it.interactives.append({
        "id": "gate-focus", "name": "The Submerged Gate", "type": "portal-focus",
        "position": [round(gx, 2), -2.2, round(gz, 2)], "authority": "server"})
    for index in range(4):
        it.harvestables.append({
            "id": f"drowned-glyphstone-{index}", "resource": "glyph-shard",
            "position": [round(float(rng.uniform(-9, 9)), 2), -1.9,
                         round(float(rng.uniform(66, 94)), 2)],
            "authority": "server"})
    it.subjects = [
        ("concept-01", "the hidden entry, cut and root-hung", "threshold"),
        ("concept-04", "the flood channel through the wading hall", "wading_hall"),
        # Explicit cameras: the generic framing stands in a corner and looks at
        # the room centre, which here is the inside of a banyan trunk and, in
        # the gate chamber, a 40 m room whose subject is a ring you have to be
        # low and back to see whole.
        ("concept-07", "the root chamber", "root_chamber",
         (24.0, 0.4, 28.5), (33.0, 0.9, 36.0)),
        ("concept-09", "the drowned processional", "stelae_walk",
         (-6.5, 0.1, 66.5), (4.0, 0.4, 93.0)),
        ("concept-08", "the submerged gate from beneath", "gate_chamber",
         (-8.5, -1.4, 118.0), (0.0, 3.4, 130.0)),
    ]
    it.notes = [
        "The gate chamber holds the lower half of the same ring that stands out "
        "of the whirlpool on the region map. The exterior arch is its top.",
        "Floors step down while the water line stays at y = 0, so the player "
        "wades progressively deeper without a single depth being authored.",
    ]
    return it


# ==========================================================================
# 2. The Smugglers' Warren
# ==========================================================================
def smugglers_warren(seed: int = 20260831) -> Interior:
    """Under the town: the space between the decks and the water, floored over.

    Every ceiling in here is a deck somebody is walking on. Every column is a
    pile you moor a boat to on the surface. It is the same town from underneath,
    which is why it is worth building rather than being a generic cellar.
    """
    it = Interior("manymouth_smugglers_warren", "The Underdeck", "warren",
                  "ferry-post", [54.0, 2.74, -33.0], "underdeck-hatch")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("hatch", -4, -5, 4, 4, -1.6, 4.2, floor_mat=TEAK, wall_mat=BARK,
             ceil_mat=TEAK, doors=[("north", 0.0, 3.0, 2.6)], seed=seed)
    it.space("stilt_corridor", -4, 16, 4, 54, -1.6, 3.2, floor_mat=TEAK,
             wall_mat=BARK, ceil_mat=TEAK,
             doors=[("south", 0.0, 3.0, 2.6), ("north", 0.0, 3.4, 2.6)],
             seed=seed + 1)
    it.space("boardwalk_maze", -22, 66, 22, 104, -1.6, 6.4, floor_mat=SILT,
             wall_mat=BARK, ceil_mat=TEAK,
             doors=[("south", 0.0, 3.4, 2.6), ("east", 86.0, 3.2, 2.4),
                    ("north", 0.0, 3.4, 2.6)], seed=seed + 2)
    it.space("cache", 30, 76, 48, 96, -0.6, 3.0, floor_mat=SANDBAR,
             wall_mat=SILT, ceil_mat=TEAK,
             doors=[("west", 86.0, 3.2, 2.4)], seed=seed + 3)
    it.space("crate_workroom", -16, 118, 16, 148, -1.2, 4.6, floor_mat=TEAK,
             wall_mat=BAMBOO, ceil_mat=TEAK,
             doors=[("south", 0.0, 3.4, 2.6)], seed=seed + 4)

    links = [
        ("ladderway", (0, 4), (0, 16), 3.0, -1.6, -1.6, 3.0, 0),
        ("mazeway", (0, 54), (0, 66), 3.4, -1.6, -1.6, 3.0, 0),
        ("cacheway", (22, 86), (30, 86), 3.2, -1.6, -0.6, 2.8, 3),
        ("workway", (0, 104), (0, 118), 3.4, -1.6, -1.2, 3.0, 2),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=TEAK, wall_mat=BARK, ceil_mat=TEAK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- hatch: a ladder down from the ferry post -------------------------
    g.add(exit_threshold("ladder", seed + 7).translate(0.0, -1.6, 3.2))
    # a dugout tied up at the foot of the ladder: you came down to a boat, which
    # is the only way anything gets in or out of here
    g.add(SK.dugout(5.0, seed + 8).rotate_y(0.4).translate(2.6, -1.75, 0.0))
    g.add(rope_hank(0.3, seed + 9).translate(1.2, -1.5, 2.0))

    # -- stilt corridor: narrow, low, piles either hand -------------------
    g.add(pile_forest(-3.2, 16, 3.2, 54, -1.9, 2.6, seed=seed + 10, spacing=3.6))
    for index in range(11):
        z = 18.0 + index * 3.3
        g.add(M.box((7.4, 0.16, 0.16), center=(0.0, 1.4, z), uv_scale=1.0,
                    material=TEAK))

    # -- boardwalk maze: crossings at three heights over a flood channel --
    g.add(flood(-22, 66, 22, 104, -0.9))
    g.add(pile_forest(-20, 68, 20, 102, 4.4, 6.0, seed=seed + 11, spacing=4.4))
    g.add(deck_ceiling(-22, 66, 22, 104, 4.7, seed=seed + 12))
    # The crossings themselves. Three levels, deliberately not aligned: the
    # subject of the board's third panel is that you can see the runs above you.
    for index, (z, level, length, angle) in enumerate((
            (72.0, -0.2, 40.0, 0.0), (80.0, 1.3, 34.0, 0.42),
            (88.0, 0.4, 40.0, -0.30), (96.0, 2.1, 30.0, 0.22))):
        run = SK.boardwalk(length, 2.1, max(level + 1.4, 0.6),
                           seed + 20 + index, rails=True)
        run.rotate_y(angle)
        g.add(run.translate(0.0, level, z))
    for index in range(7):
        g.add(SK.dugout(5.2, seed + 30 + index)
              .rotate_y(float(rng.uniform(0, math.pi)))
              .translate(float(rng.uniform(-18, 18)), -1.05,
                         float(rng.uniform(68, 102))))
    # lines strung between the piles, with what is drying on them. The maze was
    # structurally right and visually empty above the water line.
    for index in range(14):
        z = 68.0 + index * 2.6
        y = 2.2 + float(rng.uniform(-0.5, 0.9))
        g.add(M.box((34.0, 0.05, 0.05), center=(0.0, y, z), uv_scale=1.0,
                    material=BAMBOO))
        for hang in range(int(rng.integers(1, 4))):
            hx = float(rng.uniform(-15, 15))
            g.add(P.banner(0.5, float(rng.uniform(0.7, 1.4)),
                           seed + 60 + index * 3 + hang, material=CLOTH)
                  .translate(hx, y - 1.4, z))
    for index in range(6):
        g.add(SK.net_rack(seed + 130 + index, 3.0)
              .translate(float(rng.uniform(-19, 19)), -1.6,
                         float(rng.uniform(68, 102))))

    # -- cache: shelves cut into a bar's flank ----------------------------
    cx, cz = it.centre("cache")
    for level in range(3):
        y = -0.6 + 0.05 + level * 0.85
        g.add(M.box((16.0, 0.12, 1.0), center=(cx, y, cz + 8.4), uv_scale=0.9,
                    material=TEAK))
        for index in range(5):
            g.add(crate_stack(2, seed + 40 + level * 5 + index, spread=0.6)
                  .translate(cx - 6.0 + index * 3.0, y + 0.06, cz + 8.4))
    for index in range(9):
        g.add(SK.water_jar(seed + 50 + index, float(np.random.default_rng(
            seed + index).uniform(0.5, 0.85)))
            .translate(cx + float(rng.uniform(-7, 7)), -0.6,
                       cz + float(rng.uniform(-7, 5))))
    for index in range(6):
        g.add(SK.fish_trap(seed + 60 + index)
              .translate(cx + float(rng.uniform(-7, 7)), -0.6,
                         cz + float(rng.uniform(-7, 6))))

    # -- crate workroom: benches, a hoist, netting ------------------------
    wx, wz = it.centre("crate_workroom")
    for sign in (-1, 1):
        g.add(P.workbench(seed=seed + 70 + (sign > 0))
              if hasattr(P, "workbench") else
              M.box((3.2, 0.9, 1.1), center=(0, 0.45, 0), uv_scale=0.8,
                    material=TEAK))
    for index in range(4):
        g.add(crate_stack(5, seed + 80 + index, spread=1.8)
              .translate(wx + float(rng.uniform(-12, 12)), -1.2,
                         wz + float(rng.uniform(-12, 12))))
    for index in range(5):
        g.add(SK.net_rack(seed + 90 + index, 2.8)
              .translate(wx + float(rng.uniform(-12, 12)), -1.2,
                         wz + float(rng.uniform(-12, 12))))
    # a hoist over the hatch in the floor where cargo comes up from a boat
    for sx in (-1.6, 1.6):
        g.add(M.cylinder(0.14, 0.12, 3.4, 8, uv_scale=0.9, material=TEAK)
              .translate(wx + sx, -1.2, wz + 6.0))
    g.add(M.box((3.8, 0.16, 0.16), center=(wx, 2.2, wz + 6.0), uv_scale=1.0,
                material=TEAK))
    g.add(rope_hank(0.4, seed + 100).translate(wx, 1.9, wz + 6.0))
    for index in range(8):
        g.add(rope_hank(float(rng.uniform(0.24, 0.4)), seed + 110 + index)
              .translate(wx + float(rng.uniform(-13, 13)), -1.1,
                         wz + float(rng.uniform(-13, 13))))
    g.add(deck_ceiling(-16, 118, 16, 148, 3.3, seed=seed + 120))

    lamp_points = [
        (0.0, 1.6, -2.0), (0.0, 1.6, 2.0),
        (0.0, 1.1, 20.0), (0.0, 1.1, 28.0), (0.0, 1.1, 36.0),
        (0.0, 1.1, 44.0), (0.0, 1.1, 52.0),
        # the maze: a lamp at each crossing end and one over each channel, or
        # the room is a black frame - which is exactly what the first render was
        (-17.0, 1.4, 70.0), (17.0, 1.4, 70.0), (-17.0, 3.0, 80.0),
        (17.0, 3.0, 80.0), (-17.0, 2.0, 90.0), (17.0, 2.0, 90.0),
        (-17.0, 3.8, 99.0), (17.0, 3.8, 99.0),
        (0.0, 1.2, 72.0), (0.0, 2.7, 80.0), (0.0, 1.8, 88.0), (0.0, 3.5, 96.0),
        (-9.0, 4.0, 84.0), (9.0, 4.0, 84.0),
        (26.0, 1.2, 86.0), (34.0, 1.6, 82.0), (42.0, 1.6, 90.0),
        (0.0, 1.4, 112.0),
        (-12.0, 2.4, 124.0), (12.0, 2.4, 124.0), (-12.0, 2.4, 136.0),
        (12.0, 2.4, 136.0), (0.0, 2.8, 130.0), (0.0, 2.8, 144.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "hatch"
    it.landmark("smuggler-cache", "The Cache", "cache", 1.4)
    it.landmark("crate-workroom", "The Workroom", "crate_workroom", 1.6)
    it.interactives.append({
        "id": "cargo-hoist", "name": "Cargo Hoist", "type": "mechanism",
        "position": [round(wx, 2), -1.1, round(wz + 6.0, 2)],
        "authority": "server"})
    for index, role in enumerate(("smuggler", "smuggler", "fence", "lookout")):
        it.npc_markers.append({
            "id": f"underdeck-{role}-{index}", "role": role,
            "position": [round(float(rng.uniform(-13, 13)), 2), -1.2,
                         round(float(rng.uniform(120, 146)), 2)],
            "authority": "server"})
    it.subjects = [
        ("concept-02", "the stilt corridor", "stilt_corridor"),
        # Low, at the water, looking along the channel so the crossings stack
        # overhead. The generic framing put the eye inside a plank deck and the
        # frame came back black.
        ("concept-03", "the boardwalk maze at three levels", "boardwalk_maze",
         (-17.0, 0.2, 68.5), (12.0, 1.6, 100.0)),
        ("concept-05", "the smuggler cache", "cache"),
        ("concept-06", "the crate workroom", "crate_workroom"),
        ("concept-10", "reed, rope and mangrove on the bench", "crate_workroom"),
    ]
    it.notes = [
        "Every ceiling here is plank decking: the warren's roof is the town's "
        "floor, and its columns are the piles you moor against on the surface.",
        "The maze crossings sit at four different levels and are deliberately "
        "not aligned, so a player under one can see the others overhead.",
    ]
    return it


# ==========================================================================
# 3. The Tide Hall
# ==========================================================================
def tide_hall(seed: int = 20260901) -> Interior:
    """Inside the town's tiered hall: the one dry, warm, inhabited room.

    Three of these four insides are dark. This one has to carry the fact that
    people live here, so it is the only one lit from its own windows, the only
    one with textiles in it, and the only one whose floor is swept.
    """
    it = Interior("manymouth_tide_hall", "The Tide Hall", "hall",
                  "moot-hall", [30.0, 1.7, -61.5], "tide-hall-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("porch", -5, -6, 5, 2, 0.0, 3.4, floor_mat=TEAK, wall_mat=BAMBOO,
             ceil_mat=TEAK, doors=[("north", 0.0, 3.2, 2.6)], seed=seed)
    it.space("hall", -14, 14, 14, 46, 0.0, 6.8, floor_mat=BAMBOO,
             wall_mat=CARVED, ceil_mat=TEAK,
             doors=[("south", 0.0, 3.2, 2.6), ("east", 40.0, 2.6, 2.4),
                    ("north", 0.0, 3.0, 2.6)], seed=seed + 1)
    it.space("strongroom", 22, 32, 34, 44, 0.0, 3.2, floor_mat=TEAK,
             wall_mat=TEAK, ceil_mat=TEAK,
             doors=[("west", 40.0, 2.6, 2.4)], seed=seed + 2)
    it.space("gallery", -11, 58, 11, 80, 4.2, 4.4, floor_mat=BAMBOO,
             wall_mat=CARVED, ceil_mat=THATCH,
             doors=[("south", 0.0, 3.0, 2.6)], seed=seed + 3)

    links = [
        ("entry", (0, 2), (0, 14), 3.2, 0.0, 0.0, 3.2, 0),
        ("vaultway", (14, 40), (22, 40), 2.6, 0.0, 0.0, 2.8, 0),
        ("stair", (0, 46), (0, 58), 3.0, 0.0, 4.2, 3.4, 16),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=TEAK, wall_mat=CARVED, ceil_mat=TEAK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    g.add(exit_threshold("doorway", seed + 6).translate(0.0, 0.0, 1.4))

    # -- hall: carved posts, matting, a hearth basin, the tide post -------
    hx, hz = it.centre("hall")
    for row in range(4):
        z = 20.0 + row * 7.0
        for sign in (-1, 1):
            post = M.cylinder(0.42, 0.36, 6.6, 12, uv_scale=1.0, material=CARVED)
            g.add(post.translate(sign * 9.0, 0.0, z))
            g.add(A.bracket(0.7, CARVED).rotate_y(0.0 if sign > 0 else math.pi)
                  .translate(sign * 9.0, 5.6, z))
    for row in range(3):
        g.add(M.box((19.0, 0.34, 0.34), center=(0.0, 6.5, 22.0 + row * 8.0),
                    uv_scale=1.0, material=TEAK))
    # woven matting laid over the plank floor, which is what BAMBOO reads as
    for index in range(9):
        g.add(M.box((4.4, 0.04, 3.0),
                    center=(hx + float(rng.uniform(-8, 8)), 0.06,
                            hz + float(rng.uniform(-13, 13))),
                    uv_scale=1.6, material=BAMBOO).rotate_y(
            float(rng.uniform(-0.2, 0.2))))
    # the hearth: a bronze basin on a stone bed, the only fire in the region
    g.add(M.cylinder(2.2, 2.0, 0.34, 20, uv_scale=0.6, material=RUBBLE)
          .translate(hx, 0.05, hz))
    g.add(M.lathe([[0.0, 0.0], [1.5, 0.10], [1.65, 0.55], [1.35, 0.78],
                   [1.45, 0.86]], segments=20, uv_scale=0.8, material=BRONZE)
          .translate(hx, 0.39, hz))
    g.add(P.brazier(seed=seed + 11).scale(1.2).translate(hx, 0.5, hz))
    g.add(tide_post(3.4, seed + 12).translate(hx - 6.5, 0.0, hz + 9.0))
    for sign in (-1, 1):
        for index in range(3):
            g.add(P.banner(0.8, 2.6, seed + 20 + index, material=BANNER)
                  .translate(sign * 12.6, 4.0, 20.0 + index * 8.0))
    for index in range(6):
        g.add(SK.water_jar(seed + 30 + index, 0.7)
              .translate(hx + float(rng.uniform(-11, 11)), 0.05,
                         hz + float(rng.uniform(-14, 14))))
    g.add(SK.deck_study(seed + 40).translate(hx + 7.0, 0.06, hz - 8.0))
    # The hall was a handsome empty room. These are the things that say people
    # sleep, eat and work in it: mats rolled against the walls, a loom, fish on
    # a line over the hearth, and bundles in the rafters.
    for index in range(8):
        sign = -1.0 if index % 2 == 0 else 1.0
        roll = M.cylinder(0.28, 0.26, 1.8, 9, uv_scale=1.2, material=BAMBOO)
        roll.rotate_z(math.pi * 0.5)
        g.add(roll.translate(sign * 12.2, 0.28, 18.0 + index * 3.2))
    loom = S.MeshGroup()
    for sx in (-0.9, 0.9):
        loom.add(M.box((0.14, 2.2, 0.14), center=(sx, 1.1, 0.0), uv_scale=1.0,
                       material=CARVED))
    loom.add(M.box((2.0, 0.14, 0.14), center=(0.0, 2.2, 0.0), uv_scale=1.0,
                   material=CARVED))
    for warp in range(9):
        loom.add(M.box((0.03, 1.7, 0.03),
                       center=(-0.8 + warp * 0.2, 1.25, 0.0), uv_scale=1.0,
                       material=BAMBOO))
    g.add(loom.translate(hx - 9.5, 0.05, hz - 4.0))
    for index in range(9):
        g.add(M.box((0.16, 0.42, 0.10),
                    center=(hx - 2.0 + index * 0.5, 2.5, hz + 2.4),
                    uv_scale=1.0, material=BRONZE))
    g.add(M.box((5.0, 0.05, 0.05), center=(hx, 2.75, hz + 2.4), uv_scale=1.0,
                material=BAMBOO))
    for index in range(10):
        bundle = M.cylinder(0.22, 0.18, 0.9, 8, uv_scale=1.2, material=BAMBOO)
        g.add(bundle.translate(hx + float(rng.uniform(-10, 10)), 5.6,
                               hz + float(rng.uniform(-12, 12))))

    # -- strongroom: the village's bronze ---------------------------------
    sx, sz = it.centre("strongroom")
    for index in range(4):
        g.add(P.crate(0.7, seed + 50 + index, material=TEAK)
              .translate(sx + float(rng.uniform(-4, 4)), 0.0,
                         sz + float(rng.uniform(-4, 4))))
    for index in range(6):
        g.add(SK.water_jar(seed + 60 + index, 0.62)
              .translate(sx + float(rng.uniform(-4.5, 4.5)), 0.0,
                         sz + float(rng.uniform(-4.5, 4.5))))
    g.add(M.box((5.0, 0.14, 1.0), center=(sx, 1.3, sz + 4.6), uv_scale=0.9,
                material=TEAK))

    # -- gallery: the upper tier, open to the hall below ------------------
    gx, gz = it.centre("gallery")
    for sign in (-1, 1):
        rail = A.railing(20.0, 0.94, posts=14, material=CARVED, carved=CARVED)
        g.add(rail.translate(0.0, 4.2, gz + sign * 10.0))
    for index in range(5):
        g.add(P.basket(0.34, 0.46, seed + 70 + index)
              .translate(gx + float(rng.uniform(-9, 9)), 4.2,
                         gz + float(rng.uniform(-9, 9))))
    for index in range(4):
        g.add(rope_hank(0.32, seed + 80 + index)
              .translate(gx + float(rng.uniform(-9, 9)), 4.25,
                         gz + float(rng.uniform(-9, 9))))

    lamp_points = [
        (0.0, 2.4, -3.0), (0.0, 2.4, 0.0), (0.0, 2.4, 8.0),
        (-10.0, 4.6, 18.0), (10.0, 4.6, 18.0), (-10.0, 4.6, 26.0),
        (10.0, 4.6, 26.0), (-10.0, 4.6, 34.0), (10.0, 4.6, 34.0),
        (-10.0, 4.6, 42.0), (10.0, 4.6, 42.0),
        (0.0, 5.4, 24.0), (0.0, 5.4, 38.0),
        (26.0, 2.2, 34.0), (30.0, 2.2, 42.0),
        (0.0, 2.6, 52.0),
        (-8.0, 7.2, 62.0), (8.0, 7.2, 62.0), (-8.0, 7.2, 72.0),
        (8.0, 7.2, 72.0), (0.0, 7.6, 68.0), (0.0, 7.6, 78.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "porch"
    it.landmark("tide-post", "The Tide Post", "hall", 1.8)
    it.landmark("hall-gallery", "The Gallery", "gallery", 1.6)
    it.interactives.append({
        "id": "tide-post-read", "name": "The Tide Post", "type": "lore",
        "position": [round(hx - 6.5, 2), 1.6, round(hz + 9.0, 2)],
        "authority": "server"})
    it.interactives.append({
        "id": "hall-hearth", "name": "The Hall Hearth", "type": "fire",
        "position": [round(hx, 2), 0.9, round(hz, 2)], "authority": "server"})
    for index, role in enumerate(("elder", "steward", "villager", "villager",
                                 "trader")):
        it.npc_markers.append({
            "id": f"tide-hall-{role}-{index}", "role": role,
            "position": [round(float(rng.uniform(-11, 11)), 2), 0.0,
                         round(float(rng.uniform(18, 44)), 2)],
            "authority": "server"})
    it.subjects = [
        ("hall-01", "the hall from the porch", "hall"),
        ("hall-02", "the hearth basin", "hall"),
        ("hall-03", "the tide post", "hall"),
        ("hall-04", "the strongroom", "strongroom"),
        ("hall-05", "the gallery over the hall", "gallery"),
    ]
    it.notes = [
        "The only dry, inhabited, warm interior of the four, and the only one "
        "with fire and textiles in it.",
        "The tide post is a carved post banded in bronze at every flood the "
        "village remembers - a delta village's history is how high the water "
        "came.",
    ]
    return it


# ==========================================================================
# 4. The Temple Sanctum
# ==========================================================================
def temple_sanctum(seed: int = 20260902) -> Interior:
    """Inside the stepped temple: monumental, austere, and half open to the sky.

    The counterweight to the warren. Nothing here is improvised, nothing is
    timber, and every dimension is larger than it needs to be.
    """
    it = Interior("manymouth_temple_sanctum", "The Sanctum", "sanctum",
                  "green-temple", [297.0, 14.82, -309.0], "temple-sanctum-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("shrine_head", -6, -7, 6, 5, 0.0, 5.2, floor_mat=ROCK,
             wall_mat=GLYPH, ceil_mat=ROCK,
             doors=[("north", 0.0, 3.6, 3.0)], seed=seed)
    it.space("ambulatory", -22, 20, 22, 62, -2.2, 7.0, floor_mat=ROCK,
             wall_mat=ROCK, ceil_mat=ROCK, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 3.6, 3.0), ("north", 0.0, 4.2, 3.4)],
             seed=seed + 1)
    # open to the sky: rain falls into it and stands in the pool
    it.space("oculus_court", -16, 76, 16, 108, -3.4, 18.0, floor_mat=ROCK,
             wall_mat=ROCK, ceil_mat=ROCK, ceiling="open",
             doors=[("south", 0.0, 4.2, 3.4), ("north", 0.0, 3.6, 3.0)],
             seed=seed + 2)
    it.space("crypt", -13, 122, 13, 150, -8.0, 5.4, floor_mat=ROCK,
             wall_mat=RUBBLE, ceil_mat=ROCK, ceiling="vault", vault_rise=2.4,
             doors=[("south", 0.0, 3.6, 3.0)], seed=seed + 3)

    links = [
        ("descent", (0, 5), (0, 20), 3.6, 0.0, -2.2, 3.6, 8),
        ("courtway", (0, 62), (0, 76), 4.2, -2.2, -3.4, 4.0, 5),
        ("cryptway", (0, 108), (0, 122), 3.6, -3.4, -8.0, 3.4, 16),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=ROCK, wall_mat=ROCK, ceil_mat=ROCK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    g.add(exit_threshold("stair-head", seed + 6).translate(0.0, 0.0, 3.0))

    # -- ambulatory: a ring of columns around a solid core ----------------
    ax, az = it.centre("ambulatory")
    for index in range(16):
        angle = 2.0 * math.pi * index / 16.0
        g.add(S.column(height=6.4, radius=0.62, flutes=10, material=ROCK)
              .translate(ax + math.cos(angle) * 14.0, -2.2,
                         az + math.sin(angle) * 15.0))
    # the core the ambulatory walks around: a solid mass, bronze-banded
    g.add(M.box((11.0, 7.0, 13.0), center=(ax, 1.3, az), uv_scale=0.4,
                material=ROCK))
    for level in range(3):
        g.add(M.box((11.4, 0.28, 13.4), center=(ax, -1.0 + level * 2.3, az),
                    uv_scale=0.7, material=BRONZE))
    # A niche in the core's south face with what the ambulatory walks around.
    # The core was a bronze-banded box and gave the player no reason to look at
    # it; a thing inside it is the reason the ring corridor exists.
    g.add(M.box((3.0, 3.4, 0.8), center=(ax, -0.5, az - 6.6), uv_scale=0.7,
                material=ROCK))
    g.add(S.statue(height=2.4, seed=seed + 12, plinth_height=0.8)
          .translate(ax, -2.2, az - 6.4))
    for sx in (-1.5, 1.5):
        g.add(M.cylinder(0.14, 0.12, 2.6, 8, uv_scale=0.9, material=BRONZE)
              .translate(ax + sx, -2.2, az - 6.0))
    # water channels cut into the ambulatory floor, running inward to the court
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0
        g.add(M.box((0.7, 0.14, 9.0),
                    center=(ax + math.cos(angle) * 9.0, -2.05,
                            az + math.sin(angle) * 9.0),
                    uv_scale=0.7, material=BRONZE).rotate_y(angle))

    # -- oculus court: rain, a reflecting pool, bronze rings --------------
    ox, oz = it.centre("oculus_court")
    g.add_walk(M.box((28.0, 0.4, 28.0), center=(ox, -3.6, oz), uv_scale=0.35,
                     material=ROCK))
    g.add(M.cylinder(7.4, 7.4, 0.5, 40, uv_scale=0.5, material=ROCK)
          .translate(ox, -3.4, oz))
    g.add(flood(ox - 6.8, oz - 6.8, ox + 6.8, oz + 6.8, -3.0))
    for radius, lift in ((9.2, 0.0), (11.4, 0.0)):
        ring = M.lathe([[radius - 0.16, 0.0], [radius + 0.16, 0.10],
                        [radius + 0.16, 0.30], [radius - 0.16, 0.40]],
                       segments=44, uv_scale=1.4, material=BRONZE)
        g.add(ring.translate(ox, -3.4 + lift, oz))
    for index in range(8):
        angle = 2.0 * math.pi * index / 8.0 + 0.4
        g.add(SK.stele(5.4, seed + 20 + index)
              .translate(ox + math.cos(angle) * 13.0, -3.4,
                         oz + math.sin(angle) * 13.5))
    # the walls rise 18 m to open sky, so they get a real order on them
    for index in range(12):
        angle = 2.0 * math.pi * index / 12.0
        g.add(S.column(height=15.0, radius=0.72, flutes=12, material=ROCK)
              .translate(ox + math.cos(angle) * 15.0, -3.4,
                         oz + math.sin(angle) * 15.5))
    # rain-fed planting: the only green in the sanctum, and it grows in the pool
    for index in range(10):
        g.add(SK.reed_patch(1.2, 5, seed + 40 + index, 1.4)
              .translate(ox + float(rng.uniform(-6, 6)), -3.4,
                         oz + float(rng.uniform(-6, 6))))
    g.add(SK.lotus_bed(3.0, 12, seed + 50).translate(ox, -3.0, oz))

    # -- crypt: the founders, under glyph-cut slabs -----------------------
    cx, cz = it.centre("crypt")
    for index in range(8):
        row, col = divmod(index, 2)
        g.add(M.box((3.4, 0.55, 2.0),
                    center=(cx + (col - 0.5) * 6.0, -7.7, cz - 9.0 + row * 6.0),
                    uv_scale=0.6, material=GLYPH))
        g.add(M.box((3.0, 0.10, 1.6),
                    center=(cx + (col - 0.5) * 6.0, -7.4, cz - 9.0 + row * 6.0),
                    uv_scale=0.8, material=BRONZE))
    for index in range(10):
        g.add(S.column(height=5.0, radius=0.44, flutes=8, material=ROCK)
              .translate(cx + float(rng.uniform(-11, 11)), -8.0,
                         cz + float(rng.uniform(-12, 12))))
    for index in range(5):
        frag = S.ruin_fragment(seed=seed + 60 + index, scale=0.9)
        for part in (frag.parts if hasattr(frag, "parts") else [frag]):
            part.material = RUBBLE
        g.add(frag.translate(cx + float(rng.uniform(-11, 11)), -8.0,
                             cz + float(rng.uniform(-12, 12))))

    lamp_points = [
        (0.0, 3.2, -4.0), (0.0, 3.2, 2.0),
        (0.0, 2.4, 12.0),
        (-16.0, 3.6, 24.0), (16.0, 3.6, 24.0), (-16.0, 3.6, 34.0),
        (16.0, 3.6, 34.0), (-16.0, 3.6, 44.0), (16.0, 3.6, 44.0),
        (-16.0, 3.6, 56.0), (16.0, 3.6, 56.0),
        (0.0, 3.6, 22.0), (0.0, 3.6, 58.0),
        (0.0, 2.6, 69.0),
        (-13.0, 4.4, 80.0), (13.0, 4.4, 80.0), (-13.0, 4.4, 92.0),
        (13.0, 4.4, 92.0), (-13.0, 4.4, 104.0), (13.0, 4.4, 104.0),
        (0.0, 2.8, 115.0),
        (-10.0, 3.2, 126.0), (10.0, 3.2, 126.0), (-10.0, 3.2, 136.0),
        (10.0, 3.2, 136.0), (-10.0, 3.2, 146.0), (10.0, 3.2, 146.0),
        (0.0, 3.4, 131.0), (0.0, 3.4, 143.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed
    # Daylight down the oculus. The court is declared open to the sky, but a
    # capture harness cannot know that from geometry, and neither can a client
    # that has not implemented it: the shaft is authored as light so the room is
    # lit whether or not anything ever opens a hole in its roof.
    it.skylights = [
        {"position": [round(ox, 2), 12.0, round(oz, 2)], **SKYLIGHT,
         "energy": 5.0, "range": 46.0},
        {"position": [round(ox - 7.0, 2), 6.0, round(oz, 2)], **SKYLIGHT},
        {"position": [round(ox + 7.0, 2), 6.0, round(oz, 2)], **SKYLIGHT},
        {"position": [round(ox, 2), 6.0, round(oz - 8.0, 2)], **SKYLIGHT},
        {"position": [round(ox, 2), 6.0, round(oz + 8.0, 2)], **SKYLIGHT},
    ]

    it.spawn_space = "shrine_head"
    it.landmark("oculus-pool", "The Rain Pool", "oculus_court", 2.0)
    it.landmark("temple-crypt", "The Founders' Crypt", "crypt", 1.6)
    it.interactives.append({
        "id": "sanctum-altar", "name": "The Rain Pool", "type": "shrine",
        "position": [round(ox, 2), -3.0, round(oz, 2)], "authority": "server"})
    for index in range(3):
        it.npc_markers.append({
            "id": f"sanctum-acolyte-{index}", "role": "acolyte",
            "position": [round(float(rng.uniform(-12, 12)), 2), -3.4,
                         round(float(rng.uniform(80, 104)), 2)],
            "authority": "server"})
    for index in range(3):
        it.harvestables.append({
            "id": f"sanctum-lotus-{index}", "resource": "lotus-root",
            "position": [round(ox + float(rng.uniform(-5, 5)), 2), -3.0,
                         round(oz + float(rng.uniform(-5, 5)), 2)],
            "authority": "server"})
    it.subjects = [
        ("sanctum-01", "the shrine head and the descent", "shrine_head"),
        ("sanctum-02", "the ambulatory around the core", "ambulatory"),
        ("sanctum-03", "the oculus court and its rain pool", "oculus_court"),
        ("sanctum-04", "the ring of stelae", "oculus_court"),
        ("sanctum-05", "the founders' crypt", "crypt"),
    ]
    it.notes = [
        "The oculus court is declared open to the sky, so the client keeps a "
        "hole in the roof and the region's weather falls into the pool.",
        "The only stone interior, and deliberately the only one with no timber "
        "in it at all - it is the counterweight to the warren.",
    ]
    return it


ALL = {
    "flooded_labyrinth": flooded_labyrinth,
    "smugglers_warren": smugglers_warren,
    "tide_hall": tide_hall,
    "temple_sanctum": temple_sanctum,
}


# --------------------------------------------------------------------------
# The combined insides map
# --------------------------------------------------------------------------
# Eternal Lands puts every inside belonging to a region on one map, separated by
# unwalkable void, and sends the player to a different arrival point depending on
# which door was used. Doing the same here means one GLB, one manifest and one
# collision grid instead of four, one server map key instead of four, and one
# load instead of four.
#
# The gutters are not drawn and not masked. The collision grid is built only
# where a Walk_ surface exists, so the void between sections is blocked by
# construction rather than by a mask that could drift out of step with the
# geometry. Sections are spaced so no two come within about forty metres, which
# keeps one section's lamps out of the next.
LAYOUT = {
    "flooded_labyrinth": (0.0, 0.0),
    "smugglers_warren": (110.0, 0.0),
    "tide_hall": (0.0, 200.0),
    "temple_sanctum": (105.0, 190.0),
}

# Shift the whole assembly clear of the origin so the map sits in positive
# coordinates with a margin on every side, the way a server map is indexed.
LAYOUT_ORIGIN = (60.0, 40.0)


def combine(seed: int = 20260830) -> Interior:
    """Assemble the four interiors onto one map with blackspace between them."""
    combined = Interior("manymouth_delta_insides", "Manymouth Delta Insides",
                        "insides", "labyrinth-mouth", [198.0, 9.32, -3.0],
                        "labyrinth-mouth")
    combined.arrivals = []
    combined.sections = []
    combined.skylights = []

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]

        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        def move(position, dx=dx, dz=dz):
            return [round(float(position[0]) + dx, 2),
                    round(float(position[1]), 2),
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
        for entry in getattr(part, "skylights", []):
            item = dict(entry)
            item["position"] = move(entry["position"])
            item["section"] = key
            combined.skylights.append(item)
        combined.open_to_sky.extend(f"{key}.{s}" for s in part.open_to_sky)
        for entry in part.subjects:
            ident, subject, space = entry[0], entry[1], entry[2]
            rest = tuple(entry[3:])
            moved = tuple(move(v) for v in rest) if rest else ()
            combined.subjects.append(
                (f"{key}-{ident}", f"{part.name}: {subject}",
                 f"{key}.{space}") + moved)

        spawn_space = combined.spaces[f"{key}.{part.spawn_space}"]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": f"{key}.{part.spawn_space}", "position": arrival,
            "facing": 0.0})
        # A section may offer more than one way in. The labyrinth does: its
        # threshold is the cave mouth in the headland, and its gate chamber is
        # the underside of the arch in the whirlpool.
        for spawn_id, label, space_key, at, facing in getattr(
                part, "extra_arrivals", []):
            combined.arrivals.append({
                "id": spawn_id, "name": label, "section": key,
                "space": f"{key}.{space_key}", "position": move(at),
                "facing": facing})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "spaces": [f"{key}.{s}" for s in part.spaces],
            "notes": part.notes})

    combined.spawn_space = "flooded_labyrinth.threshold"

    combined.environment = {
        "sky": "none",
        "ambient": {"colour": [0.11, 0.15, 0.16], "energy": 0.42},
        "fog": {"enabled": True, "colour": [0.05, 0.08, 0.08],
                "begin": 14.0, "end": 48.0},
        "audio": [
            {"id": "drip", "space": "flooded_labyrinth.wading_hall", "loop": True},
            {"id": "gate-hum", "space": "flooded_labyrinth.gate_chamber",
             "loop": True},
            {"id": "wading", "space": "flooded_labyrinth.stelae_walk",
             "loop": True},
            {"id": "hull-creak", "space": "smugglers_warren.stilt_corridor",
             "loop": True},
            {"id": "water-lap", "space": "smugglers_warren.boardwalk_maze",
             "loop": True},
            {"id": "hall-murmur", "space": "tide_hall.hall", "loop": True},
            {"id": "hearth-fire", "space": "tide_hall.hall", "loop": True},
            {"id": "rain-on-stone", "space": "temple_sanctum.oculus_court",
             "loop": True},
            {"id": "crypt-silence", "space": "temple_sanctum.crypt",
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
        "The Flooded Labyrinth's gate chamber holds the lower half of the same "
        "ring-arch that stands out of the whirlpool on the region map.",
    ]
    return combined


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def paddy_sump(seed: int = 20260905) -> Interior:
    """The sump under the Paddy Watch, where the crabs come up the drain."""
    return SR.cave("manymouth_paddy_sump", "The Paddy Watch Sump", "paddy-watchtower",
                   [-12.0, 1.8, -276.0], "paddy-sump-mouth",
                   palette={"floor": "packed_earth", "rock": ROCK, "water": "water_deep",
                            "bone": "pale_ashlar"},
                   seed=seed, den="Manymouth Crab", pool=True)


def bund_shrine(seed: int = 20260906) -> Interior:
    """The shrine the bund-cutting rite opens from."""
    return SR.shrine("manymouth_bund_shrine", "The Bund Shrine", "south-shrine",
                     [72.0, 1.1, 123.0], "bund-shrine-door",
                     palette={"floor": "verdant_terrace_stone", "wall": RUBBLE, "ceil": RUBBLE,
                              "accent": "verdant_carved_jade", "water": "water_deep",
                              "metal": IRON},
                     seed=seed, style="water")


def bund_warden(seed: int = 20260907) -> Interior:
    """Sentry Ossa-Kel's house at the paddy hamlet."""
    return SR.cottage("manymouth_bund_warden", "The Bund Warden's House", "paddy-hamlet",
                      [-40.0, 1.6, -300.0], "bund-warden-door",
                      palette={"floor": TIMBER_DARK, "wall": "timber_grey", "roof": "thatch_reed",
                               "timber": TIMBER_DARK, "stone": RUBBLE, "cloth": BANNER,
                               "iron": IRON},
                      seed=seed, trade="hearth")


ALL.update({"paddy_sump": paddy_sump, "bund_shrine": bund_shrine, "bund_warden": bund_warden})
LAYOUT.update({"paddy_sump": (192.0, 6.0), "bund_shrine": (192.0, 90.0),
               "bund_warden": (192.0, 140.0)})
