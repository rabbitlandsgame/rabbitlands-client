"""The Verdant Stair interiors.

Four authored insides reached from named landmarks on the 576 m region map. The
room, passage and lamp helpers come from the shared toolkit's `interiors`
module, so a doorway, a stair tread and a vault rib are the same construction
here as in Amberwood's and Amethyst's; only the four compositions below are this
region's.

They are deliberately four different kinds of place, because a region whose
interiors are all the same room with different props has no interiors:

    temple_sanctum    cut jade and gilt, lit, in use   - what the terraces are for
    cenote_deeps      water-cut rock, no straight line - what is under them
    banyan_hollow     bark, timber, thatch, rope       - people living in a tree
    stair_quarry      rubble, timber, iron, spoil      - where the stone came from

None of the four has a concept package. Verdant Stair has an aerial and a
ten-panel board and no interior brief at all, so these are authored from the
region's own surface landmarks and that board - the same footing Amethyst's
three unbriefed sections stand on. Every place name here is the author's.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import junglecraft as JC
from amberwood import mesh as M
from amberwood import props as P
from amberwood import stonework as S
from amberwood import treecraft as TC
from amberwood.interiors import (EYE, Interior, chamber, hanging_lamps, passage,
                                 root_ribs, timber_framing, trusses, WALL_T)

# -- the region's palette, indoors ----------------------------------------
# Every one of these is already in the shared material table because the
# surface map references it. An interior that introduces its own stone would
# read as a different region the moment a player stepped through the door.
JADE = "verdant_jade"
CARVED_JADE = "verdant_carved_jade"
STONE = "verdant_terrace_stone"
MOSSY = "verdant_mossy_stone"
WET = "verdant_wet_limestone"
CLIFF = "verdant_limestone_cliff"
SAND = "verdant_lagoon_sand"
FERN = "verdant_fern_glade"
JUNGLE = "verdant_jungle_floor"
TRAIL = "verdant_jungle_trail"
ROPE = "verdant_rope"
FROND = "verdant_frond"
VINE = "verdant_vine"
GILT = "gilt_brass"
IRON = "dark_iron"
AMBER = "amber_resin"
AMBER_GLASS = "amber_glass"
TIMBER = "timber_warm"
TIMBER_DARK = "timber_dark"
TIMBER_GREY = "timber_grey"
CARVED = "carved_wood"
THATCH = "thatch_reed"
BARK = "bark_pale"
BARK_DARK = "bark_dark"
RUBBLE = "rubble_stone"
ASHLAR = "ashlar"
EARTH = "packed_earth"
CLOTH = "woven_cloth"
WATER = "water_cenote"
DEEP = "water_deep"
FOLIAGE = "foliage_green"


# --------------------------------------------------------------------------
# pieces these four need that no kit carries
# --------------------------------------------------------------------------
def jade_colonnade(x0, z, x1, y, height=4.4, spacing=3.2, radius=0.34,
                   material=JADE, entablature=CARVED_JADE) -> S.MeshGroup:
    """A run of columns under a carved lintel, along X at a fixed Z."""
    out = S.MeshGroup()
    length = abs(x1 - x0)
    count = max(2, int(length / spacing) + 1)
    for index in range(count):
        x = min(x0, x1) + length * index / (count - 1)
        out.add(S.column(height, radius, 10, material).translate(x, y, z))
    out.add(M.box((length + radius * 4.0, 0.52, radius * 3.0),
                  center=((x0 + x1) * 0.5, y + height + 0.26, z),
                  uv_scale=0.55, material=entablature))
    return out


def relief_screen(x0, z, x1, y, height=3.0, material=CARVED_JADE,
                  frame=MOSSY) -> S.MeshGroup:
    """A wall of set relief panels: the region's meander, indoors."""
    out = S.MeshGroup()
    length = abs(x1 - x0)
    panels = max(1, int(length / 2.6))
    for index in range(panels):
        x = min(x0, x1) + length * (index + 0.5) / panels
        out.add(JC.relief_panel(2.1, height * 0.62, 0.28, seed=index)
                .translate(x, y + height * 0.52, z))
    out.add(M.box((length, 0.34, 0.62), center=((x0 + x1) * 0.5, y + height, z),
                  uv_scale=0.6, material=frame))
    out.add(M.box((length, 0.30, 0.62), center=((x0 + x1) * 0.5, y + 0.15, z),
                  uv_scale=0.6, material=frame))
    return out


def root_curtain(x, y, z, count=7, drop=6.0, spread=4.0, seed=0,
                 material=BARK) -> S.MeshGroup:
    """Aerial roots that have found their way down through a cave roof.

    Distinct from `banyan_roots`, which stands a tree up on props: these hang
    free from a ceiling and thicken where they reach the floor, which is what a
    root that has come through rock actually does.
    """
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    for index in range(count):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        reach = float(rng.uniform(0.3, 1.0)) * spread
        top = np.array([x + math.cos(angle) * reach * 0.35, y,
                        z + math.sin(angle) * reach * 0.35])
        foot = np.array([x + math.cos(angle) * reach, y - drop * float(rng.uniform(0.7, 1.0)),
                         z + math.sin(angle) * reach])
        path, radii = [], []
        for k in range(7):
            t = k / 6.0
            point = top + (foot - top) * t
            point[0] += float(rng.normal(0.0, 0.16))
            point[2] += float(rng.normal(0.0, 0.16))
            path.append(point)
            radii.append(0.17 - 0.08 * math.sin(math.pi * t) + 0.16 * t ** 3)
        out.add(M.tube(np.array(path), radii, segments=6, uv_scale=1.0,
                       material=material))
    return out


def block_stack(x, y, z, rows=3, per_row=3, block=(1.8, 0.9, 1.2), seed=0,
                material=STONE) -> S.MeshGroup:
    """Cut ashlar stacked as it comes off the face, courses offset."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    for row in range(rows):
        offset = (row % 2) * block[0] * 0.4
        for index in range(per_row - row // 2):
            out.add(M.box(block, uv_scale=0.5, material=material)
                    .jitter(0.01, seed=seed + row * 7 + index)
                    .translate(x + offset + index * (block[0] + 0.12),
                               y + block[1] * (row + 0.5),
                               z + float(rng.uniform(-0.16, 0.16))))
    return out


def quarry_face(x0, z, x1, y, height, seed=0, material=CLIFF,
                cut=STONE) -> S.MeshGroup:
    """A working face: rough rock above, part-cut blocks still keyed into it."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    length = abs(x1 - x0)
    out.add(M.box((length, height, 1.4), center=((x0 + x1) * 0.5, y + height * 0.5, z),
                  uv_scale=0.3, material=material))
    # the channels a wedge-and-feather crew cut round a block before splitting it
    for index in range(max(2, int(length / 2.4))):
        x = min(x0, x1) + length * (index + 0.5) / max(2, int(length / 2.4))
        h = float(rng.uniform(0.8, 1.6))
        out.add(M.box((1.7, h, 0.9),
                      center=(x, y + float(rng.uniform(0.5, height * 0.55)), z - 0.85),
                      uv_scale=0.6, material=cut)
                .jitter(0.012, seed=seed + index))
    return out


def water_sheet(x0, z0, x1, z1, y, material=WATER) -> M.Mesh:
    """A still water surface. Never a walk surface: it is a hole, not a floor."""
    return M.box((abs(x1 - x0), 0.06, abs(z1 - z0)),
                 center=((x0 + x1) * 0.5, y, (z0 + z1) * 0.5),
                 uv_scale=0.18, material=material)


def frond_bank(x, y, z, count=6, radius=3.0, seed=0) -> S.MeshGroup:
    """Ferns growing where light reaches - a shaft foot or a root hole."""
    rng = np.random.default_rng(seed)
    out = S.MeshGroup()
    for index in range(count):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        r = float(rng.uniform(0.2, 1.0)) * radius
        out.add(JC.frond_cluster(float(rng.uniform(0.9, 1.7)), 5,
                                 seed=seed + index, rise=0.0)
                .translate(x + math.cos(angle) * r, y, z + math.sin(angle) * r))
    return out


# --------------------------------------------------------------------------
# 1. The Green Sanctum - inside the temple on the summit terrace
# --------------------------------------------------------------------------
def temple_sanctum(seed: int = 20260901) -> Interior:
    """Cut jade and gilt, lit and in use: what the whole stair climbs toward.

    The only one of the four with a straight line in it. Everything is dressed,
    everything is level, and the axis runs the length of the plan - which is
    what makes the other three read as caves and workings rather than as rooms
    with different wallpaper.
    """
    it = Interior("verdant_temple_sanctum", "The Green Sanctum", "temple",
                  "great-temple", [204.0, 100.0, -198.0], "temple-sanctum-door")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("narthex", -11, -9, 11, 5, 0.0, 6.0, floor_mat=STONE, wall_mat=MOSSY,
             ceil_mat=MOSSY, ceiling="flat",
             doors=[("south", 0.0, 4.6, 3.4), ("north", 0.0, 4.4, 3.4)])
    it.space("processional", -13, 17, 13, 57, -1.6, 9.0, floor_mat=STONE,
             wall_mat=JADE, ceil_mat=CARVED_JADE, ceiling="vault", vault_rise=3.4,
             doors=[("south", 0.0, 4.4, 3.4), ("north", 0.0, 5.0, 4.0),
                    ("east", 46.0, 3.4, 3.0)])
    it.space("sanctum", -18, 69, 18, 105, -3.2, 14.0, floor_mat=MOSSY,
             wall_mat=JADE, ceil_mat=CARVED_JADE, ceiling="vault", vault_rise=6.0,
             doors=[("south", 0.0, 5.0, 4.0), ("west", 87.0, 3.2, 2.8)])
    it.space("basin", 25, 34, 47, 58, -2.6, 7.5, floor_mat=MOSSY, wall_mat=MOSSY,
             ceil_mat=JADE, ceiling="vault", vault_rise=2.6,
             doors=[("west", 46.0, 3.4, 3.0)])
    it.space("relics", -44, 78, -25, 100, -3.2, 6.5, floor_mat=STONE,
             wall_mat=MOSSY, ceil_mat=MOSSY, ceiling="flat",
             doors=[("east", 87.0, 3.2, 2.8)])

    links = [
        ("approach", (0, 5), (0, 17), 4.4, 0.0, -1.6, 4.2, 6),
        ("axis", (0, 57), (0, 69), 5.0, -1.6, -3.2, 5.0, 6),
        ("basinway", (13, 46), (25, 46), 3.4, -1.6, -2.6, 3.6, 4),
        ("relicway", (-25, 87), (-18, 87), 3.2, -3.2, -3.2, 3.4, 0),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=STONE, wall_mat=MOSSY, ceil_mat=MOSSY,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- narthex: the screen you pass through, and the shoe benches ---------
    g.add(relief_screen(-9.0, -8.4, 9.0, 0.0, 2.8))
    for sign in (-1.0, 1.0):
        g.add(M.box((6.0, 0.5, 1.0), center=(sign * 7.0, 0.25, -2.0),
                    uv_scale=0.6, material=MOSSY))
        g.add(JC.shrine_post(2.4, seed=seed + int(sign) + 2)
              .translate(sign * 8.4, 0.0, 3.0))

    # -- processional: two colonnades and a runnel down the middle ---------
    for z in (22.0, 30.0, 38.0, 46.0, 54.0):
        for sign in (-1.0, 1.0):
            g.add(S.column(6.4, 0.44, 12, JADE).translate(sign * 9.5, -1.6, z))
    for sign in (-1.0, 1.0):
        g.add(M.box((1.1, 0.66, 40.0), center=(sign * 9.5, 5.13, 37.0),
                    uv_scale=0.5, material=CARVED_JADE))
    # the water channel: the aqueduct's water is brought in along the axis
    g.add(S.water_channel(38.0, 1.6, 0.5, seed=seed + 5).rotate_y(math.pi * 0.5)
          .translate(0.0, -1.6, 37.0))
    for index in range(6):
        g.add(JC.relief_panel(2.0, 1.3, 0.26, seed=seed + 20 + index)
              .translate(-12.4, 1.4, 21.0 + index * 6.0))
        g.add(JC.relief_panel(2.0, 1.3, 0.26, seed=seed + 30 + index)
              .translate(12.4, 1.4, 21.0 + index * 6.0))
    # a guardian between every second pair of columns, and hangings above them
    for index, z in enumerate((24.0, 36.0, 48.0)):
        for sign in (-1.0, 1.0):
            g.add(JC._guardian(seed=seed + 33 + index * 2 + int(sign),
                               height=2.0, material=CARVED_JADE)
                  .translate(sign * 7.4, -1.6, z))
        g.add(P.banner(0.9, 3.2, seed=seed + 36 + index).translate(-11.6, 3.4, z))
        g.add(P.banner(0.9, 3.2, seed=seed + 39 + index).translate(11.6, 3.4, z))
    for index in range(4):
        g.add(P.brazier(seed=seed + 44 + index)
              .translate(-6.0 + (index % 2) * 12.0, -1.6, 26.0 + (index // 2) * 22.0))

    # -- sanctum: the seated figure the region is built around --------------
    sx, sz = it.centre("sanctum")
    g.add(M.lathe([[9.0, 0.0], [9.0, 0.5], [7.6, 0.55], [7.6, 1.0], [6.2, 1.05],
                   [0.0, 1.1]], 24, uv_scale=0.5, material=MOSSY)
          .translate(sx, -3.2, sz))
    g.add(JC._guardian(seed=seed + 41, height=6.4, material=CARVED_JADE)
          .scale(3.4, 3.4, 3.4).translate(sx, -2.1, sz + 2.0))
    g.add(jade_colonnade(sx - 14.0, sz - 14.0, sx + 14.0, -3.2, 7.0, 4.0, 0.42))
    g.add(jade_colonnade(sx - 14.0, sz + 14.0, sx + 14.0, -3.2, 7.0, 4.0, 0.42))
    for index in range(8):
        angle = math.pi * 2.0 * index / 8.0 + 0.3
        g.add(P.brazier(seed=seed + 50 + index)
              .translate(sx + math.cos(angle) * 11.0, -3.2,
                         sz + math.sin(angle) * 11.0))
    # a gilt ring set in the floor under the figure
    g.add(M.lathe([[4.4, 0.02], [4.7, 0.06], [4.4, 0.10]], 32, uv_scale=1.2,
                  material=GILT).translate(sx, -3.15, sz + 2.0))

    # -- basin: still water fed from the channel ----------------------------
    bx, bz = it.centre("basin")
    g.add(M.lathe([[8.4, 0.0], [8.4, 0.9], [7.2, 0.95], [7.2, 0.2], [0.0, 0.15]], 26,
                  uv_scale=0.5, material=MOSSY).translate(bx, -2.6, bz))
    g.add(water_sheet(bx - 7.0, bz - 7.0, bx + 7.0, bz + 7.0, -2.05))
    for index in range(4):
        angle = math.pi * 0.5 * index + 0.6
        g.add(JC.shrine_post(2.0, seed=seed + 60 + index)
              .translate(bx + math.cos(angle) * 8.8, -2.6,
                         bz + math.sin(angle) * 8.8))

    # -- relics: racks of panels and a working table -----------------------
    # The screens stand in two rows against the side walls with an aisle down
    # the middle. Ranked across the room they walled it off end to end and the
    # camera looking down it saw nothing but the back of the first screen.
    rx, rz = it.centre("relics")
    for index in range(4):
        z = rz - 7.0 + index * 4.6
        g.add(relief_screen(rx - 8.0, z, rx - 3.4, -3.2, 2.4))
        g.add(relief_screen(rx + 3.4, z, rx + 8.0, -3.2, 2.4))
    g.add(P.workbench(2.6, seed=seed + 70).translate(rx, -3.2, rz + 9.0))
    for index in range(4):
        g.add(P.crate(0.7, seed=seed + 80 + index)
              .translate(rx - 1.4 + index * 0.9, -3.2, rz + 7.0))
    for index in range(3):
        g.add(P.banner(0.8, 2.4, seed=seed + 88 + index)
              .translate(rx, 1.4, rz - 6.0 + index * 5.0))

    lamp_points = [
        (0.0, 3.6, -3.0), (0.0, 3.6, 3.0),
        (-8.0, 4.4, 22.0), (8.0, 4.4, 22.0), (-8.0, 4.4, 38.0), (8.0, 4.4, 38.0),
        (-8.0, 4.4, 54.0), (8.0, 4.4, 54.0),
        (sx - 11.0, 5.6, sz - 10.0), (sx + 11.0, 5.6, sz - 10.0),
        (sx - 11.0, 5.6, sz + 10.0), (sx + 11.0, 5.6, sz + 10.0),
        (bx, 2.4, bz),
        (rx, 1.6, rz - 6.0), (rx, 1.6, rz + 6.0),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "narthex"
    it.subjects = [
        ("concept-01", "the screen at the door", "narthex"),
        ("concept-02", "the processional colonnade", "processional"),
        ("concept-03", "the axis runnel", "processional"),
        ("concept-04", "the seated figure", "sanctum"),
        ("concept-05", "the sanctum colonnade", "sanctum"),
        ("concept-06", "the reflecting basin", "basin"),
        ("concept-07", "the relief aisle", "relics"),
    ]
    it.landmark("the-green-figure", "The Green Figure", "sanctum", 2.2)
    it.landmark("the-processional", "The Processional", "processional", 2.0)
    it.landmark("the-still-basin", "The Still Basin", "basin", 1.0)
    it.landmark("the-relief-aisle", "The Relief Aisle", "relics", 1.6)
    it.interactives = [
        {"id": "sanctum-offering", "type": "information",
         "name": "Offering table",
         "position": [round(sx, 2), -3.0, round(sz - 7.0, 2)], "radius": 2.0,
         "authority": "server"},
        {"id": "relic-bench", "type": "crafting_station", "name": "Relic bench",
         "position": [round(rx, 2), -3.0, round(rz + 9.0, 2)], "radius": 2.0,
         "authority": "server"},
    ]
    it.npc_markers = [
        {"id": "sanctum-keeper", "name": "Keeper of the Green Sanctum",
         "type": "npc", "role": "dialogue",
         "position": [round(sx - 4.0, 2), -3.2, round(sz - 6.0, 2)],
         "authority": "server"},
    ]
    it.environment = {"audio": [{"id": "temple-hush", "space": "sanctum", "loop": True}]}
    it.notes = [
        "The only section with a straight axis. Everything else in this map is "
        "cut by water or grown.",
        "The runnel down the processional is the aqueduct's water brought "
        "indoors; it feeds the basin off the east side.",
    ]
    return it


# --------------------------------------------------------------------------
# 2. The Cenote Deeps - under the sink pool on the middle terrace
# --------------------------------------------------------------------------
def cenote_deeps(seed: int = 20260902) -> Interior:
    """Water-cut limestone under the cenote: the counterweight to the Sanctum.

    No dressed stone and no straight line. The only built thing in it is the
    bottom of the spiral stair the surface package already carries, and the
    only light is what falls down the shaft.
    """
    it = Interior("verdant_cenote_deeps", "The Cenote Deeps", "cave",
                  "cenote", [-18.0, 46.0, -102.0], "cenote-deeps-stair")
    rng = np.random.default_rng(seed)
    g = it.group

    # The shaft foot is open to the sky: it is the bottom of the cenote, and the
    # surface package has a real hole above it.
    it.space("shaftfoot", -13, -13, 13, 13, 0.0, 18.0, floor_mat=WET,
             wall_mat=CLIFF, ceil_mat=CLIFF, ceiling="open",
             doors=[("north", 0.0, 5.4, 4.0)])
    it.space("gallery", -8, 26, 8, 62, -2.4, 7.0, floor_mat=WET, wall_mat=CLIFF,
             ceil_mat=CLIFF, ceiling="vault", vault_rise=3.0,
             doors=[("south", 0.0, 5.4, 4.0), ("north", 0.0, 5.0, 3.6)])
    it.space("drowned", -26, 74, 26, 118, -6.0, 13.0, floor_mat=WET,
             wall_mat=CLIFF, ceil_mat=CLIFF, ceiling="vault", vault_rise=6.0,
             doors=[("south", 0.0, 5.0, 3.6), ("east", 100.0, 4.4, 3.4)])
    it.space("roothall", 40, 84, 74, 116, -5.2, 16.0, floor_mat=JUNGLE,
             wall_mat=CLIFF, ceil_mat=CLIFF, ceiling="vault", vault_rise=6.5,
             doors=[("west", 100.0, 4.4, 3.4)])

    links = [
        ("throat", (0, 13), (0, 26), 5.4, 0.0, -2.4, 5.0, 8),
        ("gullet", (0, 62), (0, 74), 5.0, -2.4, -6.0, 4.6, 10),
        ("rootway", (26, 100), (40, 100), 4.4, -6.0, -5.2, 4.4, 3),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=WET, wall_mat=CLIFF, ceil_mat=CLIFF,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- shaft foot: the stair lands, light comes down, ferns grow ----------
    g.add(JC.cenote_stair(radius=11.0, depth=15.0, seed=seed + 3, turns=0.9,
                          width=2.4).translate(0.0, 15.0, 0.0))
    g.add(water_sheet(-9.0, -9.0, 9.0, 9.0, 0.25))
    g.add(frond_bank(0.0, 0.0, -9.0, 9, 5.0, seed=seed + 11))
    g.add(root_curtain(-6.0, 15.0, 4.0, 6, 12.0, 3.2, seed=seed + 12))
    g.add(root_curtain(7.0, 15.0, -3.0, 5, 11.0, 2.8, seed=seed + 13))
    for index in range(7):
        g.add(P.boulder(radius=float(rng.uniform(0.6, 1.5)), seed=seed + 20 + index,
                        material=CLIFF)
              .translate(float(rng.uniform(-10, 10)), 0.0, float(rng.uniform(-10, 10))))
    g.add(JC.vine_curtain(16.0, 9.0, seed=seed + 14, density=1.1)
          .translate(0.0, 15.5, -12.0))

    # -- gallery: a water-cut run with flowstone and a stream in the floor --
    for index in range(11):
        z = 27.0 + index * 3.2
        side = -1 if index % 2 else 1
        g.add(M.lathe([[0.0, 0.0], [0.55, 0.3], [0.32, 1.4], [0.5, 2.2],
                       [0.18, 3.4], [0.0, 3.8]], 8, uv_scale=0.8, material=WET)
              .translate(side * float(rng.uniform(4.6, 6.4)), -2.4, z))
        if index % 3 == 0:
            g.add(root_curtain(side * 3.0, 2.6, z, 3, 4.0, 1.6, seed=seed + 40 + index))
    g.add(water_sheet(-1.6, 26.0, 1.6, 62.0, -2.2))

    # -- drowned hall: a big chamber half under water ------------------------
    dx, dz = it.centre("drowned")
    g.add(water_sheet(dx - 22.0, dz - 18.0, dx + 22.0, dz + 6.0, -5.35))
    for index in range(13):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        r = float(rng.uniform(0.5, 1.0)) ** 0.5 * 22.0
        height = float(rng.uniform(2.4, 7.0))
        g.add(M.lathe([[0.0, 0.0], [0.9, 0.4], [0.5, height * 0.5],
                       [0.7, height * 0.75], [0.0, height]], 9, uv_scale=0.6,
                      material=WET)
              .translate(dx + math.cos(angle) * r, -6.0, dz + math.sin(angle) * r))
    # stalactites answering them from the roof
    for index in range(16):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        r = float(rng.uniform(0.3, 1.0)) * 23.0
        drop = float(rng.uniform(1.6, 5.0))
        g.add(M.lathe([[0.0, 0.0], [0.6, -0.4], [0.34, -drop * 0.6], [0.0, -drop]], 8,
                      uv_scale=0.6, material=WET)
              .translate(dx + math.cos(angle) * r, 7.0, dz + math.sin(angle) * r))
    for index in range(9):
        g.add(P.boulder(radius=float(rng.uniform(0.7, 2.0)), seed=seed + 60 + index,
                        material=CLIFF)
              .translate(dx + float(rng.uniform(-20, 20)), -6.0,
                         dz + float(rng.uniform(-14, 14))))

    # -- root hall: banyan roots have come down through the roof ------------
    rx, rz = it.centre("roothall")
    for index in range(5):
        angle = math.pi * 2.0 * index / 5.0 + 0.4
        g.add(root_curtain(rx + math.cos(angle) * 8.0, 9.0,
                           rz + math.sin(angle) * 8.0, 9, 14.0, 4.4,
                           seed=seed + 80 + index))
    g.add(JC.banyan_roots(radius=6.0, count=13, height=9.0, seed=seed + 91)
          .translate(rx, -5.2, rz))
    g.add(frond_bank(rx, -5.2, rz, 14, 12.0, seed=seed + 92))
    g.add(root_ribs(rx - 14, rz - 12, rx + 14, rz + 12, -5.2, -5.2, 3.0, 9.0,
                    material=BARK_DARK))
    for index in range(6):
        g.add(JC.tree_fern(height=float(rng.uniform(2.6, 4.2)), seed=seed + 100 + index,
                           crown=2.0)
              .translate(rx + float(rng.uniform(-11, 11)), -5.2,
                         rz + float(rng.uniform(-9, 9))))

    lamp_points = [
        (0.0, 4.0, 30.0), (0.0, 4.0, 42.0), (0.0, 4.0, 54.0),
        (dx - 14.0, 1.0, dz + 12.0), (dx + 14.0, 1.0, dz + 12.0),
        (dx, 1.0, dz + 16.0),
        (rx - 8.0, 2.0, rz), (rx + 8.0, 2.0, rz),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "shaftfoot"
    it.subjects = [
        ("concept-01", "the shaft foot, looking up", "shaftfoot"),
        ("concept-02", "the water-cut gallery", "gallery"),
        ("concept-03", "the gullet down", "gullet"),
        ("concept-04", "the drowned hall", "drowned"),
        # An explicit camera: the second view of a room swings the eye a third
        # of a turn, and in a chamber this size that put it inside a pillar.
        ("concept-05", "flowstone and pillars", "drowned",
         (-18.0, -4.3, 78.0), (10.0, -3.0, 104.0)),
        ("concept-06", "the root hall", "roothall"),
    ]
    it.landmark("the-shaft-foot", "The Shaft Foot", "shaftfoot", 1.6)
    it.landmark("the-drowned-hall", "The Drowned Hall", "drowned", 2.4)
    it.landmark("the-root-hall", "The Root Hall", "roothall", 3.0)
    it.harvestables = [
        {"id": f"cenote-watercress-{index:02d}", "resource": "Watercress",
         "category": "reagent",
         "position": [round(float(rng.uniform(-8, 8)), 2), 0.0,
                      round(float(rng.uniform(-8, 8)), 2)],
         "authority": "server"} for index in range(3)]
    it.environment = {"audio": [{"id": "drip", "space": "gallery", "loop": True},
                                {"id": "water-hollow", "space": "drowned",
                                 "loop": True}]}
    it.notes = [
        "The shaft foot is declared open to the sky: it is the bottom of the "
        "cenote the surface package cuts, and light down that shaft is the only "
        "daylight in this map.",
        "Nothing in this section is dressed. The only built object is the foot "
        "of the spiral stair, which is the same kit piece the surface uses.",
    ]
    return it


# --------------------------------------------------------------------------
# 3. The Banyan Hollow - inside the great tree at the canopy village
# --------------------------------------------------------------------------
def banyan_hollow(seed: int = 20260903) -> Interior:
    """Bark, timber, thatch and rope: people living inside a tree.

    The warm one. Every surface is either the tree or something lashed to it,
    and it is the only section with a floor above another floor.
    """
    it = Interior("verdant_banyan_hollow", "The Banyan Hollow", "tree-hall",
                  "canopy-village", [-66.0, 46.0, -126.0], "banyan-hollow-arch")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("rootarch", -8, -7, 8, 4, 0.0, 5.0, floor_mat=JUNGLE,
             wall_mat=BARK_DARK, ceil_mat=BARK_DARK, ceiling="vault",
             vault_rise=1.8, doors=[("south", 0.0, 4.4, 3.2), ("north", 0.0, 4.6, 3.4)])
    it.space("hollow", -17, 16, 17, 50, -0.6, 22.0, floor_mat=TIMBER,
             wall_mat=BARK, ceil_mat=BARK, ceiling="open",
             doors=[("south", 0.0, 4.6, 3.4), ("east", 40.0, 3.2, 2.8),
                    ("west", 26.0, 3.0, 2.6)])
    it.space("store", -36, 20, -20, 34, -0.6, 4.4, floor_mat=EARTH,
             wall_mat=BARK_DARK, ceil_mat=BARK_DARK, ceiling="flat",
             doors=[("east", 26.0, 3.0, 2.6)])
    it.space("loft", 25, 32, 45, 50, 9.4, 6.0, floor_mat=TIMBER,
             wall_mat=BARK, ceil_mat=THATCH, ceiling="flat",
             doors=[("west", 40.0, 3.2, 2.8)])

    links = [
        ("archway", (0, 4), (0, 16), 4.6, 0.0, -0.6, 4.4, 3),
        ("storeway", (-20, 26), (-17, 26), 3.0, -0.6, -0.6, 3.0, 0),
        ("loftstair", (17, 40), (25, 40), 3.2, -0.6, 9.4, 3.6, 24),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=TIMBER, wall_mat=BARK_DARK, ceil_mat=BARK_DARK,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- root arch: buttress roots either side of the way in ----------------
    for sign in (-1.0, 1.0):
        g.add(JC.banyan_roots(radius=5.0, count=7, height=5.0, seed=seed + 3 + int(sign))
              .translate(sign * 7.0, 0.0, -2.0))
    g.add(JC.vine_curtain(14.0, 4.0, seed=seed + 5, density=1.0)
          .translate(0.0, 4.6, -6.4))

    # -- the hollow: the inside of the trunk, and the stair up it -----------
    hx, hz = it.centre("hollow")
    g.add(TC.spiral_stair(radius=6.8, height=9.6, seed=seed + 7, material=TIMBER_DARK,
                          turns=1.15).translate(hx + 6.0, -0.6, hz - 4.0))
    # the trunk wall: ribs of bark standing in from the chamber wall so the
    # room reads as the inside of something grown, not as a round room
    for index in range(18):
        angle = math.pi * 2.0 * index / 18.0
        r = 15.0 + float(rng.uniform(-1.0, 1.0))
        rib = M.lathe([[0.0, 0.0], [1.1, 0.6], [0.7, 8.0], [1.0, 14.0], [0.4, 21.0],
                       [0.0, 22.0]], 7, uv_scale=0.7, material=BARK)
        g.add(rib.translate(hx + math.cos(angle) * r, -0.6, hz + math.sin(angle) * r))
    g.add(root_curtain(hx, 20.0, hz, 11, 15.0, 9.0, seed=seed + 9))
    g.add(P.well(0.95, seed=seed + 11).translate(hx - 7.0, -0.6, hz + 6.0))
    g.add(P.firewood(0.8, seed=seed + 12).translate(hx - 10.0, -0.6, hz - 8.0))
    for index in range(4):
        g.add(P.market_stall(2.4, 1.6, seed=seed + 20 + index)
              .translate(hx - 11.0 + index * 6.0, -0.6, hz + 12.0))
    for index in range(5):
        g.add(P.basket(0.32, 0.44, seed=seed + 30 + index)
              .translate(hx + float(rng.uniform(-12, 12)), -0.6,
                         hz + float(rng.uniform(-12, 12))))
    # rope walkways crossing the hollow above head height
    # Offset from the trunk's axis rather than crossing at it: two walkways
    # meeting over the centre put a deck directly above the hollow's own
    # landmark, which verify_runtime reads as a landmark buried in the scenery -
    # and it is a better crossing anyway.
    for level, y in ((0, 6.6), (1, 12.4)):
        a = (hx - 14.0, y, hz - 10.0 + level * 15.0)
        b = (hx + 14.0, y, hz - 4.0 + level * 15.0)
        g.add(TC.suspension_walkway(a, b, sag=0.7, width=1.5, seed=seed + 40 + level,
                                    rope_material=ROPE))

    # -- store: sacks, crates and a rack among the roots --------------------
    stx, stz = it.centre("store")
    g.add(P.log_pile(3.0, 3, 4, seed=seed + 50).translate(stx - 3.0, -0.6, stz))
    for index in range(6):
        g.add(P.sack(0.26, 0.55, seed=seed + 60 + index)
              .translate(stx + 2.0 + (index % 3) * 0.9, -0.6,
                         stz - 2.0 + (index // 3) * 1.1))
    g.add(P.workbench(2.1, seed=seed + 70).translate(stx + 4.0, -0.6, stz + 4.0))

    # -- loft: a plank floor with a thatched lid and a hearth ---------------
    lx, lz = it.centre("loft")
    g.add(timber_framing(lx - 9, lz - 8, lx + 9, lz + 8, 9.4, 5.4, spacing=3.0,
                         material=TIMBER_DARK))
    g.add(trusses(lx - 9, lz - 8, lx + 9, lz + 8, 14.6, count=4,
                  material=TIMBER_DARK, rise=1.0))
    g.add(P.brazier(seed=seed + 90).translate(lx, 9.4, lz))
    for index in range(3):
        g.add(P.crate(0.66, seed=seed + 95 + index)
              .translate(lx - 6.0 + index * 1.5, 9.4, lz - 6.0))
    g.add(P.banner(0.7, 2.0, seed=seed + 99).translate(lx + 7.0, 12.6, lz))

    lamp_points = [
        (0.0, 3.2, 0.0),
        (hx - 8.0, 4.4, hz - 8.0), (hx + 8.0, 4.4, hz - 8.0),
        (hx - 8.0, 4.4, hz + 10.0), (hx + 8.0, 4.4, hz + 10.0),
        (hx, 9.0, hz), (hx, 15.0, hz),
        (stx, 2.6, stz),
        (lx - 5.0, 13.0, lz), (lx + 5.0, 13.0, lz),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "rootarch"
    it.subjects = [
        ("concept-01", "the root arch", "rootarch"),
        ("concept-02", "the hollow from the floor", "hollow"),
        ("concept-03", "the stair up the trunk", "hollow"),
        ("concept-04", "rope walkways overhead", "hollow"),
        ("concept-05", "the store among the roots", "store"),
        ("concept-06", "the loft and its hearth", "loft"),
    ]
    it.landmark("the-hollow", "The Hollow", "hollow", 3.0)
    it.landmark("the-loft", "The Loft", "loft", 1.6)
    it.landmark("the-root-store", "The Root Store", "store", 1.2)
    it.interactives = [
        {"id": "hollow-storage", "type": "storage", "name": "Village cache",
         "position": [round(stx + 4.0, 2), -0.4, round(stz + 4.0, 2)], "radius": 2.0,
         "authority": "server"},
        {"id": "hollow-hearth", "type": "crafting_station", "name": "Hollow hearth",
         "position": [round(lx, 2), 9.6, round(lz, 2)], "radius": 2.0,
         "authority": "server"},
    ]
    it.npc_markers = [
        {"id": "hollow-elder", "name": "Hollow Elder", "type": "npc",
         "role": "dialogue",
         "position": [round(hx - 5.0, 2), -0.6, round(hz + 8.0, 2)],
         "authority": "server"},
    ]
    it.environment = {"audio": [{"id": "village-inside", "space": "hollow", "loop": True},
                                {"id": "creaking-timber", "space": "loft", "loop": True}]}
    it.notes = [
        "The hollow is declared open to the sky: the trunk is open at the top, "
        "which is where its daylight comes from and why the rope walkways read.",
        "The only section with a floor above another floor. The loft stair is a "
        "24-step run, so it is walkable rather than a ladder the client cannot "
        "ground an actor on.",
    ]
    return it


# --------------------------------------------------------------------------
# 4. The Stair Quarry - where the terrace stone was cut
# --------------------------------------------------------------------------
def stair_quarry(seed: int = 20260904) -> Interior:
    """Rubble, timber, iron and spoil: the workings under the summit.

    Every terrace on the surface is faced with cut limestone, and this is the
    hole it came out of. The only section where the stone is a product rather
    than a setting.
    """
    it = Interior("verdant_stair_quarry", "The Stair Quarry", "workings",
                  "quarry", [354.0, 124.0, -174.0], "stair-quarry-adit")
    rng = np.random.default_rng(seed)
    g = it.group

    it.space("adit", -7, -6, 7, 8, 0.0, 5.0, floor_mat=EARTH, wall_mat=CLIFF,
             ceil_mat=CLIFF, ceiling="vault", vault_rise=1.6,
             doors=[("south", 0.0, 4.2, 3.2), ("north", 0.0, 4.4, 3.2)])
    it.space("cutting", -21, 20, 21, 58, -2.0, 11.0, floor_mat=EARTH,
             wall_mat=CLIFF, ceil_mat=CLIFF, ceiling="flat",
             doors=[("south", 0.0, 4.4, 3.2), ("north", 0.0, 4.6, 3.4),
                    ("west", 46.0, 3.4, 3.0)])
    it.space("sorting", -50, 34, -27, 58, -2.0, 7.0, floor_mat=EARTH,
             wall_mat=RUBBLE, ceil_mat=CLIFF, ceiling="flat",
             doors=[("east", 46.0, 3.4, 3.0)])
    it.space("sump", -18, 72, 18, 104, -8.4, 10.0, floor_mat=WET, wall_mat=CLIFF,
             ceil_mat=CLIFF, ceiling="vault", vault_rise=4.0,
             doors=[("south", 0.0, 4.6, 3.4)])

    links = [
        ("driftway", (0, 8), (0, 20), 4.4, 0.0, -2.0, 4.2, 6),
        ("sortway", (-27, 46), (-21, 46), 3.4, -2.0, -2.0, 3.4, 0),
        ("winze", (0, 58), (0, 72), 4.6, -2.0, -8.4, 4.4, 16),
    ]
    for ident, a, b, width, y0, y1, height, steps in links:
        g.add(passage(a[0], a[1], b[0], b[1], width, y0, y1, height,
                      floor_mat=EARTH, wall_mat=CLIFF, ceil_mat=CLIFF,
                      steps=steps, seed=seed + len(ident)))
        it.spaces[ident] = {"x0": min(a[0], b[0]) - width * 0.5,
                            "z0": min(a[1], b[1]) - width * 0.5,
                            "x1": max(a[0], b[0]) + width * 0.5,
                            "z1": max(a[1], b[1]) + width * 0.5,
                            "floor": min(y0, y1), "height": height}
        it.passages[ident] = {"a": a, "b": b, "y0": y0, "y1": y1,
                              "width": width, "height": height}

    # -- adit: props, a rail sledge and the last daylight -------------------
    for index in range(4):
        z = -4.0 + index * 3.2
        for sign in (-1.0, 1.0):
            g.add(M.box((0.36, 4.6, 0.36), center=(sign * 5.6, 2.3, z),
                        uv_scale=1.0, material=TIMBER_DARK))
        g.add(M.box((11.6, 0.38, 0.34), center=(0.0, 4.7, z), uv_scale=0.8,
                    material=TIMBER_DARK))
    g.add(P.cart(seed=seed + 3).translate(2.4, 0.0, 5.0))
    g.add(JC.vine_curtain(11.0, 3.0, seed=seed + 4, density=0.9)
          .translate(0.0, 4.4, -5.6))

    # -- cutting floor: the working face with blocks still keyed in ---------
    cx, cz = it.centre("cutting")
    g.add(quarry_face(cx - 18.0, cz + 17.0, cx + 18.0, -2.0, 10.0, seed=seed + 10))
    for index, (bx, bz) in enumerate(((-14.0, -10.0), (-6.0, -13.0), (5.0, -11.0),
                                      (13.0, -6.0), (-11.0, 2.0), (10.0, 4.0))):
        g.add(block_stack(cx + bx, -2.0, cz + bz, rows=int(rng.integers(2, 4)),
                          per_row=int(rng.integers(2, 4)), seed=seed + 20 + index))
    for index in range(5):
        g.add(M.box((0.36, 9.0, 0.36),
                    center=(cx - 16.0 + index * 8.0, 2.5, cz + 12.0),
                    uv_scale=1.0, material=TIMBER_DARK))
    g.add(P.workbench(2.4, seed=seed + 30).translate(cx + 12.0, -2.0, cz - 14.0))
    for index in range(6):
        g.add(P.boulder(radius=float(rng.uniform(0.4, 1.0)), seed=seed + 40 + index,
                        material=RUBBLE)
              .translate(cx + float(rng.uniform(-17, 17)), -2.0,
                         cz + float(rng.uniform(-15, 15))))

    # -- sorting floor: the spoil heap, a scale, and finished stone ---------
    sx, sz = it.centre("sorting")
    g.add(P.log_pile(4.0, 3, 5, seed=seed + 50).translate(sx - 6.0, -2.0, sz - 6.0))
    for index in range(4):
        g.add(block_stack(sx - 7.0 + index * 4.4, -2.0, sz + 4.0, rows=2, per_row=3,
                          seed=seed + 60 + index))
    g.add(P.cart(seed=seed + 70).translate(sx + 6.0, -2.0, sz - 8.0))
    for index in range(7):
        g.add(P.boulder(radius=float(rng.uniform(0.3, 0.9)), seed=seed + 80 + index,
                        material=RUBBLE)
              .translate(sx + float(rng.uniform(-9, 9)), -2.0,
                         sz + float(rng.uniform(-10, 10))))
    g.add(P.barrel(seed=seed + 90).translate(sx + 8.0, -2.0, sz + 8.0))

    # -- sump: the flooded lower working ------------------------------------
    ux, uz = it.centre("sump")
    g.add(water_sheet(ux - 15.0, uz - 13.0, ux + 15.0, uz + 5.0, -7.9))
    for index in range(8):
        g.add(M.box((0.34, 7.0, 0.34),
                    center=(ux - 12.0 + (index % 4) * 8.0, -4.9,
                            uz - 10.0 + (index // 4) * 16.0),
                    uv_scale=1.0, material=TIMBER_DARK))
    for index in range(10):
        angle = float(rng.uniform(0.0, math.pi * 2.0))
        r = float(rng.uniform(0.3, 1.0)) * 15.0
        drop = float(rng.uniform(1.0, 3.2))
        g.add(M.lathe([[0.0, 0.0], [0.5, -0.3], [0.28, -drop * 0.6], [0.0, -drop]], 7,
                      uv_scale=0.6, material=WET)
              .translate(ux + math.cos(angle) * r, 1.2, uz + math.sin(angle) * r))
    g.add(P.cart(seed=seed + 100).translate(ux - 9.0, -8.4, uz + 8.0))
    g.add(block_stack(ux + 6.0, -8.4, uz + 6.0, rows=2, per_row=2, seed=seed + 110))

    lamp_points = [
        (0.0, 3.0, 2.0),
        (cx - 12.0, 4.0, cz - 12.0), (cx + 12.0, 4.0, cz - 12.0),
        (cx - 12.0, 4.0, cz + 8.0), (cx + 12.0, 4.0, cz + 8.0), (cx, 4.0, cz),
        (sx, 2.6, sz - 6.0), (sx, 2.6, sz + 6.0),
        (ux - 8.0, -4.4, uz), (ux + 8.0, -4.4, uz),
    ]
    lamps, placed = hanging_lamps(lamp_points, seed=seed)
    g.add(lamps)
    it.lamps = placed

    it.spawn_space = "adit"
    it.subjects = [
        ("concept-01", "the adit and its props", "adit"),
        ("concept-02", "the working face", "cutting"),
        ("concept-03", "blocks keyed into the face", "cutting"),
        ("concept-04", "the sorting floor", "sorting"),
        ("concept-05", "the winze down", "winze"),
        ("concept-06", "the flooded sump", "sump"),
    ]
    it.landmark("the-working-face", "The Working Face", "cutting", 2.4)
    it.landmark("the-sorting-floor", "The Sorting Floor", "sorting", 1.4)
    it.landmark("the-sump", "The Sump", "sump", 1.4)
    it.interactives = [
        {"id": "quarry-bench", "type": "crafting_station", "name": "Mason's bench",
         "position": [round(cx + 12.0, 2), -1.8, round(cz - 14.0, 2)], "radius": 2.0,
         "authority": "server"},
    ]
    it.harvestables = [
        {"id": f"pale-quartz-{index:02d}", "resource": "Quartz",
         "category": "mineral",
         "position": [round(cx + float(rng.uniform(-15, 15)), 2), -2.0,
                      round(cz + float(rng.uniform(-13, 13)), 2)],
         "authority": "server"} for index in range(4)]
    it.environment = {"audio": [{"id": "pick-work", "space": "cutting", "loop": True},
                                {"id": "drip", "space": "sump", "loop": True}]}
    it.notes = [
        "The face is a working one: blocks are still keyed into it with the "
        "wedge channels cut round them, rather than the room being a finished "
        "cavity.",
        "The sump is the only water in this section and it is not walkable; the "
        "shelf around it is.",
    ]
    return it


ALL = {
    "temple_sanctum": temple_sanctum,
    "cenote_deeps": cenote_deeps,
    "banyan_hollow": banyan_hollow,
    "stair_quarry": stair_quarry,
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
# Offsets come from each section's measured footprint so no two come within
# about forty metres. That gap is not decoration - it is what stops a lamp in
# the Quarry lighting the Sanctum, and what keeps a stray camera in one from
# seeing into another.
LAYOUT = {
    "temple_sanctum": (0.0, 0.0),
    "cenote_deeps": (150.0, 0.0),
    "banyan_hollow": (0.0, 175.0),
    "stair_quarry": (120.0, 175.0),
}

# Shift the whole assembly clear of the origin so the map sits in positive
# coordinates with a margin on every side, the way a server map is indexed.
LAYOUT_ORIGIN = (60.0, 34.0)


def combine(seed: int = 20260901) -> Interior:
    """Assemble the four interiors onto one map with blackspace between them."""
    combined = Interior("verdant_stair_insides", "Verdant Stair Insides",
                        "insides", "great-temple", [204.0, 100.0, -198.0],
                        "temple-sanctum-door")
    combined.arrivals = []
    combined.sections = []

    for key, build_fn in ALL.items():
        part = build_fn(seed)
        dx = LAYOUT[key][0] + LAYOUT_ORIGIN[0]
        dz = LAYOUT[key][1] + LAYOUT_ORIGIN[1]

        part.group.translate(dx, 0.0, dz)
        combined.group.add(part.group)

        def move(position):
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

        spawn_space = combined.spaces[f"{key}.{part.spawn_space}"]
        arrival = [round((spawn_space["x0"] + spawn_space["x1"]) * 0.5, 2),
                   round(spawn_space["floor"] + 0.05, 2),
                   round((spawn_space["z0"] + spawn_space["z1"]) * 0.5, 2)]
        combined.arrivals.append({
            "id": part.destination_spawn, "name": part.name, "section": key,
            "space": f"{key}.{part.spawn_space}", "position": arrival})
        combined.sections.append({
            "id": key, "name": part.name, "class": part.klass,
            "offset": [dx, 0.0, dz], "arrival": arrival,
            "spaces": [f"{key}.{s}" for s in part.spaces],
            "notes": part.notes})

    combined.spawn_space = "temple_sanctum.narthex"

    # One map, one environment. The four sections carry their own audio. Two
    # spaces stay declared open to the sky - the cenote shaft foot and the top
    # of the banyan trunk - because both are genuinely holes the surface package
    # cuts, even though a combined map is lit as sealed.
    combined.environment = {
        "sky": "none",
        # The capture rig lights a sealed package from this colour alone, at
        # four times the declared energy, plus a token key. A dark green-grey
        # ambient on jade, wet limestone and bark leaves every frame a shape in
        # the dark, and exposure cannot recover what was never lit.
        "ambient": {"colour": [0.32, 0.38, 0.34], "energy": 0.62},
        # Read by the Godot capture rig. A sealed map is lit by its own ambient
        # and a token key, and this region's indoor surfaces - jade, wet
        # limestone, bark - are all dark, so at the default exposure the frames
        # come back as shapes in the dark rather than as rooms.
        "exposure": 1.85,
        "fog": {"enabled": True, "colour": [0.06, 0.09, 0.08],
                "begin": 14.0, "end": 56.0},
        "audio": [
            {"id": "temple-hush", "space": "temple_sanctum.sanctum", "loop": True},
            {"id": "water-runnel", "space": "temple_sanctum.processional", "loop": True},
            {"id": "drip", "space": "cenote_deeps.gallery", "loop": True},
            {"id": "water-hollow", "space": "cenote_deeps.drowned", "loop": True},
            {"id": "village-inside", "space": "banyan_hollow.hollow", "loop": True},
            {"id": "creaking-timber", "space": "banyan_hollow.loft", "loop": True},
            {"id": "pick-work", "space": "stair_quarry.cutting", "loop": True},
            {"id": "drip", "space": "stair_quarry.sump", "loop": True},
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
        "None of the four has a concept package: Verdant Stair has an aerial and "
        "a ten-panel board and no interior brief, so all four are authored from "
        "the region's surface landmarks and that board. Every place name is the "
        "author's.",
    ]
    return combined


# ---- small rooms (shared kit) ----
from amberwood import smallrooms as SR


def physick_still(seed: int = 20260905) -> Interior:
    """Tessara's still room, behind the physick garden."""
    return SR.cottage("verdant_physick_still", "Tessara's Still Room", "herbalist",
                      [-24.0, 24.0, 0.0], "physick-still-door",
                      palette={"floor": TIMBER, "wall": STONE, "roof": THATCH,
                               "timber": TIMBER_DARK, "stone": STONE, "cloth": "woven_cloth",
                               "iron": IRON},
                      seed=seed, trade="still")


def anchor_hollow(seed: int = 20260906) -> Interior:
    """The hollow behind Fern Camp, where the stair's old anchor stone was moved to."""
    return SR.cave("verdant_anchor_hollow", "The Anchor Hollow", "fern-camp",
                   [-132.0, 46.0, -180.0], "anchor-hollow-mouth",
                   palette={"floor": JUNGLE, "rock": CLIFF, "water": "water_deep",
                            "bone": "pale_ashlar"},
                   seed=seed, den="Moonshadow Lynx", pool=True)


def nine_lost(seed: int = 20260907) -> Interior:
    """A water shrine for the nine the stair lost, under the south quay pavilion."""
    return SR.shrine("verdant_nine_lost", "The Shrine of the Nine Lost", "south-quay",
                     [204.0, 46.0, 120.0], "nine-lost-door",
                     palette={"floor": STONE, "wall": MOSSY, "ceil": STONE,
                              "accent": CARVED_JADE, "water": "water_deep", "metal": GILT},
                     seed=seed, style="water")


ALL.update({"physick_still": physick_still, "anchor_hollow": anchor_hollow,
            "nine_lost": nine_lost})
LAYOUT.update({"anchor_hollow": (258.0, 6.0), "nine_lost": (258.0, 90.0),
               "physick_still": (258.0, 140.0)})
