"""Placement passes for Manymouth Delta.

`region.py` says where the land and the water are. This says what stands on
them. The order below is the guide's "largest to smallest": water, then the
walkway network that is this region's road system, then the landmarks, then the
villages that hang off the network, then planting, then props.

THE ONE STRUCTURAL IDEA
-----------------------
Everything is hung off the **walkway network**. In a land region you place a
village on a hill and a road to it; here the walkway comes first and the village
is what is nailed to it, because that is how the concept's settlements are
actually built. So `walkway_network()` resolves every route, every deck level
and every landing *before* any building pass runs, and the building passes read
their deck heights out of it rather than deciding independently. Two passes
choosing their own deck level is how a hut ends up half a metre under the
walkway it opens onto.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as A
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as P
from amberwood import stonework as SW
from amberwood import terrain as TER
from amberwood import trees as TR
from amberwood.noise import Rng

import deltakit as DK
import region as REG
import stiltkit as SK
import layout as LAY

from region import Placement

# Clearance from the water to the underside of a deck. Low, because the
# concept's walkways are low: you step down into a canoe from them, you do not
# look down at one from a bridge.
DECK_CLEAR = 1.70
# Longest single boardwalk mesh. Longer routes are chained out of segments, so
# that one 180 m run is not one 180 m collision rectangle and one huge mesh.
SEGMENT = 34.0



# WHY NO PLACEMENT HERE SETS `walk_surface=True`
# ----------------------------------------------
# `RegionBuild.place()` renames a placement's node to `Walk_<node>` when
# `walk_surface` is set, and `export_glb` then names every *solid* child of that
# node `<node>__<material>` - which inherits the `Walk_` prefix. The client turns
# anything matching `navigation.surfaceNodePrefixes` into the layer its grounding
# ray tests, so the boardwalk handrails, the pile heads and the bamboo posts all
# became walk surfaces two metres above the deck, and every spawn on a walkway
# snapped to the top of a rail post.
#
# Every walkable piece in this region is a `MeshGroup` that already declares its
# deck through `add_walk`, which `export_glb` exports as `Walk_<node>__<material>`
# on its own. `build_collision` and `verify_runtime` both key off `walk_bounds`,
# not off the flag. So the flag is redundant here and actively harmful: the
# correct idiom for a MeshGroup is `add_walk` alone.


# ==========================================================================
# water
# ==========================================================================
def build_water(build, lod: str | None = None) -> None:
    t = build.terrain
    x0, z0 = t.x0, t.z0
    x1, z1 = t.x0 + t.size_x, t.z0 + t.size_z

    # The shallow pass covers the whole region and runs past the authored
    # terrain to the horizon, because the north-west edge of this map is open
    # sea and has to have something in it.
    build.water_meshes["Water_Delta"] = TER.water_plane(
        t, REG.SEA_LEVEL, x0 - 420.0, z0 - 420.0, x1 + 420.0, z1 + 420.0,
        material=DK.DELTA_WATER, cell=6.0, only_below=True, margin=0.12,
        outside_is_water=True)

    # The deep pass sits five centimetres *below* the shallow one rather than
    # above it. Two blended planes at the same height double-composite and the
    # channels come out milky; one under the other reads exactly as what it is,
    # a darker body of water seen through clear water.
    deep = TER.water_plane(
        t, REG.SEA_LEVEL - 0.05, x0, z0, x1, z1,
        material=DK.DELTA_DEEP, cell=6.0, only_below=True, margin=3.2,
        outside_is_water=False)
    if deep.triangle_count:
        build.water_meshes["Water_DeepChannels"] = deep


# ==========================================================================
# the walkway network
# ==========================================================================
# Which places are joined to which. This is the region's road map: read it as
# "you can walk from A to B without a boat". Chosen to match the aerial's
# chains - a dense knot around the town, long single strands out to the
# outlying bars, and nothing at all across the open north-west water.
ROUTES: tuple[tuple[str, str], ...] = (
    # the town knot (panels 2, 3, 4 and 6 all happen inside this)
    ("stilt_town", "town_hall"),
    ("stilt_town", "town_quay"),
    ("stilt_town", "market_hall"),
    ("market_hall", "floating_market"),
    ("town_quay", "arch_stair"),
    # the ruin approach
    ("arch_stair", "great_arch"),
    ("arch_stair", "overlook"),
    # east and south
    ("overlook", "cave_mouth"),
    ("cave_mouth", "east_hamlet"),
    ("east_hamlet", "east_watch"),
    ("overlook", "south_hamlet"),
    ("south_hamlet", "south_shrine"),
    ("south_hamlet", "far_bar"),
    # the banyan reach and the ruins beyond it
    ("stilt_town", "banyan_landing"),
    ("banyan_landing", "deep_grove"),
    ("deep_grove", "ruin_stelae"),
    ("ruin_stelae", "green_temple"),
    ("green_temple", "temple_quay"),
    # west and the paddy country
    ("floating_market", "west_hamlet"),
    ("west_hamlet", "boat_yard"),
    ("banyan_landing", "mangrove_reach"),
    ("mangrove_reach", "paddy_hamlet"),
    ("paddy_hamlet", "paddy_terraces"),
    ("paddy_terraces", "paddy_tower"),
    ("paddy_tower", "upper_paddy"),
    ("upper_paddy", "north_fishing"),
    ("paddy_hamlet", "sea_landing"),
)

# Routes walked on bamboo rather than plank: the light causeways of panel 7,
# which cross standing water in a paddy rather than a channel.
BAMBOO_ROUTES = {("paddy_terraces", "paddy_tower"), ("paddy_tower", "upper_paddy"),
                 ("paddy_hamlet", "paddy_terraces")}


# How far above its *lower* landing a walkway may climb before it stops being a
# walkway. Beyond this the route runs into rising ground and whatever stair is
# built there takes over.
DECK_MAX_CLIMB = 2.2


def _deck_level(t, a, b) -> float:
    """The level a walkway runs at between two anchors.

    Taken from the higher of the two landings so a deck never runs below the
    ground it meets, floored at a fixed clearance above the water so it always
    reads as bridging a channel, and - this is the part that matters here -
    **capped a short way above the lower landing**.

    Without that cap, any route touching the temple mount inherited the mount's
    height: the walkway from the stelae court to the temple ran dead level at
    14.8 m for a hundred metres, a plank deck four storeys above open water, and
    it took the collision grid and every landmark under it with it. A walkway
    crosses water; where the ground rises out of reach it stops, and the
    temple's own processional stair is what continues.
    """
    low = min(float(t.height_at(*a)), float(t.height_at(*b)))
    high = max(float(t.height_at(*a)), float(t.height_at(*b)))
    ceiling = max(low, REG.SEA_LEVEL) + DECK_MAX_CLIMB
    return max(min(high, ceiling), REG.SEA_LEVEL + DECK_CLEAR)


def _segments(a, b, seed: int):
    """Split a route into boardwalk-length segments with a slight meander.

    A straight 180 m plank run across a braided delta looks like a survey line.
    The lateral offset is a fixed fraction of the span, so a short hop stays
    straight and a long reach bends around the bars it passes.
    """
    ax, az = a
    bx, bz = b
    length = math.hypot(bx - ax, bz - az)
    count = max(1, int(round(length / SEGMENT)))
    nx, nz = -(bz - az) / max(length, 1e-6), (bx - ax) / max(length, 1e-6)
    points = []
    for i in range(count + 1):
        t = i / count
        bow = math.sin(math.pi * t) * length * 0.035
        sway = (N.stable_hash(f"{seed}:{i}") % 1000 / 1000.0 - 0.5) * 2.0
        offset = bow * sway
        points.append((ax + (bx - ax) * t + nx * offset,
                       az + (bz - az) * t + nz * offset))
    return points


def walkway_network(build, seed: int) -> dict:
    """Build every route, and return what the building passes need to know.

    Returns `{anchor_name: deck_level}` plus the list of resolved segments, so a
    village pass can put its huts at the height of the walkway they open onto
    instead of guessing.
    """
    t = build.terrain
    rng = Rng(seed)
    deck_levels: dict[str, float] = {}
    segments: list[dict] = []

    for route_index, (a_name, b_name) in enumerate(ROUTES):
        a = REG.ANCHORS[a_name]
        b = REG.ANCHORS[b_name]
        level = _deck_level(t, a, b)
        deck_levels[a_name] = max(deck_levels.get(a_name, -99.0), level)
        deck_levels[b_name] = max(deck_levels.get(b_name, -99.0), level)
        bamboo = (a_name, b_name) in BAMBOO_ROUTES or \
                 (b_name, a_name) in BAMBOO_ROUTES

        points = _segments(a, b, seed + route_index * 17)
        for i in range(len(points) - 1):
            p, q = points[i], points[i + 1]
            length = math.hypot(q[0] - p[0], q[1] - p[1])
            if length < 3.0:
                continue
            mid = ((p[0] + q[0]) * 0.5, (p[1] + q[1]) * 0.5)
            angle = math.atan2(q[1] - p[1], q[0] - p[0])
            bed_p = float(t.height_at(p[0], p[1]))
            bed_q = float(t.height_at(q[0], q[1]))
            drop_a = max(level - bed_p, 0.55)
            drop_b = max(level - bed_q, 0.55)

            key = f"walkway_{route_index:02d}_{i:02d}"
            if bamboo:
                piece = SK.bamboo_causeway(length, 1.6, seed + route_index * 31 + i,
                                           drop=min(max(drop_a, drop_b), 2.4))
            else:
                piece = SK.boardwalk(length, 2.3, drop_a,
                                     seed + route_index * 31 + i,
                                     rails=True, drop_end=drop_b)
            build.add_mesh(key, piece)
            build.place(Placement(
                node=key, mesh=key, position=(mid[0], level, mid[1]),
                rotation_y=-angle, walk_surface=False, kind="landmark"))
            segments.append({"a": p, "b": q, "level": level, "angle": angle,
                             "route": (a_name, b_name)})

        # A short flight where the walkway meets ground appreciably below it.
        for name, point in ((a_name, a), (b_name, b)):
            ground = float(t.height_at(*point))
            rise = level - ground
            if 0.32 < rise < 4.5 and ground > REG.SEA_LEVEL + 0.15:
                steps = max(2, int(round(rise / 0.22)))
                key = f"landing_{route_index:02d}_{name}"
                if key in build.meshes:
                    continue
                flight = M.stairs(2.2, rise / steps, 0.30, steps, uv_scale=0.8,
                                  material=DK.TEAK)
                group = SW.group()
                group.add_walk(flight)
                build.add_mesh(key, group)
                heading = math.atan2(point[1] - REG.ANCHORS[
                    b_name if name == a_name else a_name][1],
                    point[0] - REG.ANCHORS[
                        b_name if name == a_name else a_name][0])
                build.place(Placement(
                    node=key, mesh=key, position=(point[0], ground, point[1]),
                    rotation_y=-heading + math.pi * 0.5, walk_surface=False,
                    kind="landmark"))

    build.notes.append(
        f"walkway network: {len(ROUTES)} routes, {len(segments)} deck segments")
    return {"levels": deck_levels, "segments": segments}


# ==========================================================================
# landmarks
# ==========================================================================
def populate_arch(build, seed: int, network: dict) -> None:
    """The great ring-arch, its platform and the stelae around it."""
    t = build.terrain
    rng = Rng(seed + 5)
    centre = REG.ANCHORS["great_arch"]

    arch = SK.ring_arch(seed + 11, radius=11.5, thickness=1.8, depth=3.2)
    build.add_mesh("great_arch", arch)
    build.place(Placement(node="Landmark_GreatArch", mesh="great_arch",
                          position=(centre[0], 0.35, centre[1]),
                          rotation_y=math.radians(28.0), collides=True,
                          kind="landmark", landmark="great-arch"))

    # the drowned approach platform: walkable, just above the water
    deck = SK.stilt_deck(9.0, 7.0, 2.6, seed + 13, rails="none")
    build.add_mesh("arch_platform", deck)
    build.place(Placement(node="arch_platform", mesh="arch_platform",
                          position=(centre[0], REG.SEA_LEVEL + 0.55, centre[1]),
                          rotation_y=math.radians(28.0), walk_surface=False,
                          kind="landmark"))

    # stelae standing in the shallows around the pit, thickest to the east
    for i in range(14):
        angle = math.pi * 2.0 * i / 14 + 0.22
        radius = float(rng.uniform(20.0, 34.0)) * REG.LOCAL
        x = centre[0] + math.cos(angle) * radius
        z = centre[1] + math.sin(angle) * radius
        y = float(t.height_at(x, z))
        key = f"stele_{i % 5}"
        if key not in build.meshes:
            build.add_mesh(key, SK.stele(float(rng.uniform(2.6, 4.6)),
                                         seed + 60 + i))
        build.place(Placement(node=f"stele_{i:02d}", mesh=key,
                              position=(x, y, z),
                              rotation_y=float(rng.uniform(0, math.pi * 2)),
                              collides=True, kind="prop"))

    # the ruined stelae court on its own bar
    court = REG.ANCHORS["ruin_stelae"]
    for i in range(9):
        angle = math.pi * 2.0 * i / 9
        r = 9.0 * REG.LOCAL
        x, z = court[0] + math.cos(angle) * r, court[1] + math.sin(angle) * r
        build.place(Placement(node=f"court_stele_{i:02d}",
                              mesh=f"stele_{i % 5}",
                              position=(x, float(t.height_at(x, z)), z),
                              rotation_y=angle, collides=True, kind="prop"))
    fragments = []
    for i in range(6):
        fragments.append(SW.ruin_fragment(seed + 90 + i, scale=1.4)
                         .with_material(DK.GLYPH))
    build.add_mesh("ruin_rubble", M.merge(fragments, DK.GLYPH))
    build.place(Placement(node="Landmark_StelaeCourt", mesh="ruin_rubble",
                          position=(court[0], float(t.height_at(*court)),
                                    court[1]),
                          collides=True, kind="landmark",
                          landmark="stelae-court"))


def populate_cave(build, seed: int, network: dict) -> None:
    """The mouth of the flooded labyrinth in the rock headland."""
    t = build.terrain
    cave = REG.ANCHORS["cave_mouth"]
    mouth = (cave[0] - 6.0 * REG.LOCAL, cave[1] + 9.0 * REG.LOCAL)
    y = float(t.height_at(*mouth))
    portal = SK.cave_portal(seed + 3, span=6.5, height=7.5)
    build.add_mesh("cave_portal", portal)
    build.place(Placement(node="Landmark_LabyrinthMouth", mesh="cave_portal",
                          position=(mouth[0], y, mouth[1]),
                          rotation_y=math.radians(200.0), collides=True,
                          kind="landmark", landmark="labyrinth-mouth"))
    rng = Rng(seed + 7)
    rocks = []
    for i in range(7):
        rocks.append(P.boulder(float(rng.uniform(0.9, 2.4)), seed + 30 + i,
                               material=DK.GLYPH))
    build.add_mesh("headland_rocks", M.merge(rocks, DK.GLYPH))
    build.place(Placement(node="headland_rocks", mesh="headland_rocks",
                          position=(cave[0], float(t.height_at(*cave)) - 0.6,
                                    cave[1]),
                          collides=True, kind="rock"))


def populate_temple(build, seed: int, network: dict) -> None:
    """The stepped temple on the east rim."""
    t = build.terrain
    temple = REG.ANCHORS["green_temple"]
    y = float(t.height_at(*temple))
    piece = SK.stepped_temple(seed + 21, base=26.0, tiers=4, tier_height=3.4)
    build.add_mesh("green_temple", piece)
    build.place(Placement(node="Landmark_GreenTemple", mesh="green_temple",
                          position=(temple[0], y, temple[1]),
                          rotation_y=math.radians(45.0), collides=True,
                          kind="landmark", landmark="green-temple"))

    rng = Rng(seed + 23)
    for i in range(8):
        angle = math.radians(-104.0) + (i - 3.5) * 0.42
        r = 22.0 * REG.LOCAL
        x, z = temple[0] + math.cos(angle) * r, temple[1] + math.sin(angle) * r
        build.place(Placement(node=f"temple_stele_{i:02d}",
                              mesh=f"stele_{i % 5}",
                              position=(x, float(t.height_at(x, z)), z),
                              rotation_y=angle + math.pi, collides=True,
                              kind="prop"))


# ==========================================================================
# settlements
# ==========================================================================
def _house_variants(build, seed: int) -> list[str]:
    keys = []
    for i in range(6):
        key = f"stilt_house_{i}"
        if key not in build.meshes:
            build.add_mesh(key, SK.stilt_house(
                width=3.8 + (i % 3) * 0.9, depth=3.4 + (i % 2) * 0.8,
                drop=3.4, seed=seed + i * 13, veranda=True,
                storeys=2 if i >= 4 else 1))
        keys.append(key)
    return keys


def _place_hamlet(build, seed: int, anchor: str, level: float, count: int,
                  radius: float, houses: list[str], label: str) -> None:
    """Ring a walkway anchor with houses standing in the water around it."""
    t = build.terrain
    rng = Rng(seed)
    centre = REG.ANCHORS[anchor]
    placed = 0
    for i in range(count * 3):
        if placed >= count:
            break
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(radius * 0.45, radius))
        x, z = centre[0] + math.cos(angle) * r, centre[1] + math.sin(angle) * r
        bed = float(t.height_at(x, z))
        if bed > level - 0.30:
            continue          # too shallow: it would be a hut on dry mud
        if bed < level - 6.5:
            continue          # too deep to pile
        key = houses[int(rng.integers(0, len(houses)))]
        build.place(Placement(
            node=f"{label}_house_{placed:02d}", mesh=key,
            position=(x, level, z),
            rotation_y=float(rng.uniform(0, math.pi * 2)),
            collides=True, kind="building"))
        placed += 1
    build.notes.append(f"{label}: {placed} stilt houses")


def populate_stilt_town(build, seed: int, network: dict) -> None:
    """The main town - panels 2, 3 and 4, plus the floating market of panel 6."""
    t = build.terrain
    rng = Rng(seed + 41)
    levels = network["levels"]
    houses = _house_variants(build, seed)

    town_level = levels.get("stilt_town", REG.SEA_LEVEL + DECK_CLEAR)
    LAY.house_rows(build, seed + 101, network, "stilt_town", 14, "town")

    # panel 2: the tiered gilded hall
    hall = REG.ANCHORS["town_hall"]
    build.add_mesh("pagoda_hall", SK.pagoda_hall(seed + 51, base=7.6, tiers=3))
    build.place(Placement(node="Landmark_MootHall", mesh="pagoda_hall",
                          position=(hall[0], levels.get("town_hall", town_level),
                                    hall[1]),
                          rotation_y=math.radians(18.0), collides=True,
                          walk_surface=False, kind="landmark",
                          landmark="moot-hall"))

    # panel 4: the arched market hall
    market = REG.ANCHORS["market_hall"]
    build.add_mesh("market_hall", SK.market_hall(seed + 55, span=9.0,
                                                 length=15.0, arches=5))
    build.place(Placement(node="Landmark_MarketHall", mesh="market_hall",
                          position=(market[0],
                                    levels.get("market_hall", town_level),
                                    market[1]),
                          rotation_y=math.radians(20.0), collides=True,
                          walk_surface=False, kind="landmark",
                          landmark="market-hall"))

    # panel 3: the boardwalk junction quay, with its gear
    quay = REG.ANCHORS["town_quay"]
    quay_level = levels.get("town_quay", town_level)
    build.add_mesh("town_quay_deck",
                   SK.stilt_deck(7.5, 5.5, 3.2, seed + 57, rails="rear",
                                 ladder=True))
    build.place(Placement(node="town_quay_deck", mesh="town_quay_deck",
                          position=(quay[0], quay_level, quay[1]),
                          rotation_y=math.radians(34.0), walk_surface=False,
                          kind="landmark"))

    # panel 6: the floating market - a raft of moored awning boats
    fm = REG.ANCHORS["floating_market"]
    for i in range(5):
        key = f"awning_boat_{i}"
        if key not in build.meshes:
            build.add_mesh(key, SK.awning_boat(seed + 70 + i,
                                               length=5.4 + (i % 3) * 0.8))
    placed = 0
    for i in range(26):
        angle = float(rng.uniform(0, math.pi * 2))
        r = float(rng.uniform(3.0, 17.0)) * REG.LOCAL
        x, z = fm[0] + math.cos(angle) * r, fm[1] + math.sin(angle) * r
        if float(t.height_at(x, z)) > REG.SEA_LEVEL - 0.55:
            continue
        build.place(Placement(
            node=f"market_boat_{placed:02d}", mesh=f"awning_boat_{i % 5}",
            position=(x, REG.SEA_LEVEL - 0.16, z),
            rotation_y=float(rng.uniform(0, math.pi * 2)), kind="prop"))
        placed += 1
    build.notes.append(f"floating market: {placed} moored market boats")


def populate_deck_study(build, seed: int, network: dict) -> None:
    """Panel 10's material study, on the arch approach walkway.

    It has to sit somewhere a macro camera can actually stand: on a deck, at
    the deck's own level, with nothing built within a few metres. The town quay
    fails that on every count - it is the densest part of the region and a hut
    stands on the anchor - so the study goes on the last stretch of the
    arch approach instead, four metres short of the ruin platform. Reading it
    as an offering left at the arch is better than reading it as clutter on a
    quay, and it is the only deck in the region with room around it.
    """
    level = network["levels"].get("great_arch", REG.SEA_LEVEL + DECK_CLEAR)
    a = REG.ANCHORS["arch_stair"]
    b = REG.ANCHORS["great_arch"]
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    ux, uz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    x, z = b[0] - ux * 4.0, b[1] - uz * 4.0
    build.add_mesh("deck_study", SK.deck_study(seed + 59))
    build.place(Placement(
        node="Landmark_DeckStudy", mesh="deck_study",
        position=(x, level, z), rotation_y=-math.atan2(uz, ux),
        kind="landmark", landmark="deck-study"))
    build.notes.append(
        f"deck study placed at ({x:.1f}, {level:.2f}, {z:.1f})")


def populate_villages(build, seed: int, network: dict) -> None:
    """The outlying hamlets, and the two places that are not villages."""
    t = build.terrain
    levels = network["levels"]
    houses = _house_variants(build, seed)

    for index, (anchor, count, radius) in enumerate((
            ("paddy_hamlet", 8, 22.0), ("east_hamlet", 9, 24.0),
            ("south_hamlet", 9, 24.0), ("west_hamlet", 7, 21.0),
            ("north_fishing", 6, 19.0), ("boat_yard", 6, 20.0),
            ("far_bar", 6, 22.0), ("sea_landing", 5, 18.0),
            ("temple_quay", 6, 20.0), ("deep_grove", 5, 20.0))):
        level = levels.get(anchor, REG.SEA_LEVEL + DECK_CLEAR)
        LAY.house_rows(build, seed + 200 + index * 7, network, anchor, count, anchor)

    # the overlook of panel 9: a plain deck on the edge of a bar, looking north
    over = REG.ANCHORS["overlook"]
    build.add_mesh("overlook_deck",
                   SK.stilt_deck(5.5, 4.0, 3.0, seed + 61, rails="rear"))
    build.place(Placement(node="Landmark_Overlook", mesh="overlook_deck",
                          position=(over[0], levels.get("overlook", 2.2),
                                    over[1]),
                          rotation_y=math.radians(-58.0), walk_surface=False,
                          kind="landmark", landmark="delta-overlook"))

    # the paddy watchtower of panel 7
    tower = REG.ANCHORS["paddy_tower"]
    # Not `architecture.watchtower`: that is Amberwood's stone-and-shingle
    # tower and it would be the only masonry building in a region made of
    # bamboo. The paddy watch is a tall thin stilt house, which is what the
    # panel shows.
    build.add_mesh("paddy_tower",
                   SK.stilt_house(3.0, 3.0, 6.5, seed + 63, storeys=2))
    build.place(Placement(node="Landmark_PaddyTower", mesh="paddy_tower",
                          position=(tower[0], float(t.height_at(*tower)),
                                    tower[1]),
                          rotation_y=math.radians(126.0), collides=True,
                          kind="landmark", landmark="paddy-watchtower"))

    # the shrine on the southern bar
    shrine = REG.ANCHORS["south_shrine"]
    build.place(Placement(node="Landmark_SouthShrine", mesh="stele_0",
                          position=(shrine[0], float(t.height_at(*shrine)),
                                    shrine[1]),
                          scale=1.6, collides=True, kind="landmark",
                          landmark="south-shrine"))

    watch = REG.ANCHORS["east_watch"]
    build.add_mesh("east_watch", SK.stilt_house(3.2, 3.2, 5.5, seed + 67,
                                                storeys=2))
    build.place(Placement(node="Landmark_EastWatch", mesh="east_watch",
                          position=(watch[0], float(t.height_at(*watch)),
                                    watch[1]),
                          rotation_y=math.radians(-32.0), collides=True,
                          kind="landmark", landmark="east-watch"))


# ==========================================================================
# planting
# ==========================================================================
def populate_paddies(build, seed: int, network: dict) -> None:
    """Lotus beds and rice in the terraced water of panel 7."""
    t = build.terrain
    rng = Rng(seed + 71)
    for i in range(4):
        build.add_mesh(f"lotus_bed_{i}", SK.lotus_bed(2.8, 11, seed + 80 + i))
        build.add_mesh(f"reed_patch_{i}", SK.reed_patch(1.5, 8, seed + 90 + i,
                                                        height=1.75))
    lotus = reeds = 0
    paddy = t.surface == REG.MM_PADDY
    rows, cols = np.nonzero(paddy)
    if rows.size:
        pick = rng.integers(0, rows.size, size=min(520, rows.size))
        for k in pick:
            r, c = int(rows[k]), int(cols[k])
            x = t.x0 + c * t.cell + float(rng.uniform(-1.0, 1.0))
            z = t.z0 + r * t.cell + float(rng.uniform(-1.0, 1.0))
            y = float(t.height_at(x, z))
            if rng.chance(0.42):
                build.place(Placement(
                    node=f"lotus_{lotus:03d}", mesh=f"lotus_bed_{lotus % 4}",
                    position=(x, y + 0.05, z),
                    rotation_y=float(rng.uniform(0, math.pi * 2)),
                    kind="foliage"))
                lotus += 1
            else:
                build.place(Placement(
                    node=f"paddy_reed_{reeds:03d}",
                    mesh=f"reed_patch_{reeds % 4}", position=(x, y, z),
                    rotation_y=float(rng.uniform(0, math.pi * 2)),
                    scale=float(rng.uniform(0.75, 1.2)), kind="foliage"))
                reeds += 1
    build.notes.append(f"paddies: {lotus} lotus beds, {reeds} rice clumps")


def populate_mangroves(build, seed: int, network: dict,
                       lod: str | None = None) -> None:
    """The mangrove belts of panels 1 and 5, and the banyan landing."""
    t = build.terrain
    rng = Rng(seed + 73)

    for i in range(4):
        build.add_mesh(f"mangrove_mat_{i}",
                       SK.mangrove_thicket(3.4, seed + 100 + i))

    # the banyan of panel 5, with a deck built inside its roots
    banyan = REG.ANCHORS["banyan_landing"]
    bark, foliage = TR.build_tree("delta_banyan", seed + 111,
                                  "low" if lod == "far" else "high")
    tree = SW.group(bark, foliage)
    build.add_mesh("great_banyan", tree)
    by = float(t.height_at(*banyan))
    # Offset from the anchor, not on it. The anchor is where the walkway ends
    # and therefore where panel 5's camera has to stand; with the tree on the
    # anchor the camera is inside the trunk and the frame is bark.
    build.place(Placement(node="Landmark_GreatBanyan", mesh="great_banyan",
                          position=(banyan[0] - 11.0, by, banyan[1] - 8.0),
                          scale=1.35, collides=True, kind="tree",
                          landmark="great-banyan"))
    build.add_mesh("banyan_deck",
                   SK.stilt_deck(6.0, 4.5, 2.6, seed + 113, rails="rear",
                                 ladder=True))
    build.place(Placement(node="banyan_deck", mesh="banyan_deck",
                          position=(banyan[0] + 7.5, max(by + 0.4, 2.0),
                                    banyan[1] + 4.0),
                          rotation_y=math.radians(-38.0), walk_surface=False,
                          kind="landmark"))

    # mangrove belts: on the silt flats and along the wetted edge of every bar
    belt = ((t.surface == REG.MM_SILT)
            | ((t.height > REG.SEA_LEVEL - 1.35)
               & (t.height < REG.SEA_LEVEL + 0.55)))
    belt &= ~t.tree_block
    rows, cols = np.nonzero(belt)
    trees = mats = 0
    if rows.size:
        want = 520 if lod == "far" else 1500
        pick = rng.integers(0, rows.size, size=min(want, rows.size))
        for k in pick:
            r, c = int(rows[k]), int(cols[k])
            x = t.x0 + c * t.cell + float(rng.uniform(-1.4, 1.4))
            z = t.z0 + r * t.cell + float(rng.uniform(-1.4, 1.4))
            y = float(t.height_at(x, z))
            if rng.chance(0.36):
                tier = ("low" if lod == "far"
                        else ("mid" if rng.chance(0.28) else "low"))
                key = f"mangrove_{tier}_{trees % 4}"
                if key not in build.meshes:
                    bark, foliage = TR.build_tree("mangrove",
                                                  seed + 400 + trees % 4, tier)
                    build.add_mesh(key, SW.group(bark, foliage))
                build.place(Placement(
                    node=f"mangrove_{trees:04d}", mesh=key,
                    position=(x, y - 0.45, z),
                    rotation_y=float(rng.uniform(0, math.pi * 2)),
                    scale=float(rng.uniform(0.85, 1.35)),
                    collides=True, kind="tree"))
                trees += 1
            elif lod == "far":
                # root mats are ground dressing: the reduced package drops them
                # the same way it drops undergrowth
                continue
            else:
                build.place(Placement(
                    node=f"mangrove_mat_{mats:04d}",
                    mesh=f"mangrove_mat_{mats % 4}",
                    position=(x, y - 0.30, z),
                    rotation_y=float(rng.uniform(0, math.pi * 2)),
                    scale=float(rng.uniform(0.7, 1.25)), kind="foliage"))
                mats += 1
    build.notes.append(f"mangrove belt: {trees} trees, {mats} root mats")


def populate_vegetation(build, seed: int, network: dict,
                        lod: str | None = None) -> None:
    """Palms on the bars, and ground dressing under them.

    Density is per area, not per region. The bars carry a palm roughly every
    90 square metres, which is an open coastal stand rather than a forest - you
    can see through it to the water on either side, which is what every panel
    shows and what a closed canopy would destroy.
    """
    t = build.terrain
    rng = Rng(seed + 77)

    tiers = ("low",) if lod == "far" else ("high", "mid", "low")
    for tier in tiers:
        for i in range(4):
            for species in ("delta_palm", "delta_palm_young", "nipa"):
                key = f"{species}_{tier}_{i}"
                if key not in build.meshes:
                    bark, foliage = TR.build_tree(species, seed + 500 + i, tier)
                    build.add_mesh(key, SW.group(bark, foliage))

    land = (t.height > REG.SEA_LEVEL + 0.45) & ~t.tree_block
    land &= np.isin(t.surface, [TER.FOREST, TER.MEADOW, TER.PATH])
    rows, cols = np.nonzero(land)
    palms = ground = 0
    if rows.size:
        # one candidate per ~90 m2 of bar; `t.cell` is 2 m, so a cell is 4 m2
        want = int(rows.size * 4.0 / 62.0)
        pick = rng.integers(0, rows.size, size=min(want, rows.size))
        for k in pick:
            r, c = int(rows[k]), int(cols[k])
            x = t.x0 + c * t.cell + float(rng.uniform(-1.6, 1.6))
            z = t.z0 + r * t.cell + float(rng.uniform(-1.6, 1.6))
            y = float(t.height_at(x, z))
            if y < REG.SEA_LEVEL + 0.30:
                continue
            roll = float(rng.uniform())
            if lod == "far":
                tier = "low"
            elif roll < 0.10:
                tier = "high"
            elif roll < 0.40:
                tier = "mid"
            else:
                tier = "low"
            species = ("nipa" if rng.chance(0.22)
                       else ("delta_palm_young" if rng.chance(0.30)
                             else "delta_palm"))
            build.place(Placement(
                node=f"palm_{palms:04d}",
                mesh=f"{species}_{tier}_{palms % 4}", position=(x, y, z),
                rotation_y=float(rng.uniform(0, math.pi * 2)),
                scale=float(rng.uniform(0.82, 1.28)),
                collides=species != "nipa", kind="tree"))
            palms += 1

    if lod != "far":
        for i in range(4):
            build.add_mesh(f"undergrowth_{i}",
                           P.undergrowth_patch(1.3, 6, seed + 600 + i, 0.8))
            build.add_mesh(f"shore_reed_{i}",
                           SK.reed_patch(1.6, 7, seed + 610 + i, height=1.5))
        if rows.size:
            pick = rng.integers(0, rows.size, size=min(rows.size, 2200))
            for k in pick:
                r, c = int(rows[k]), int(cols[k])
                x = t.x0 + c * t.cell + float(rng.uniform(-1.8, 1.8))
                z = t.z0 + r * t.cell + float(rng.uniform(-1.8, 1.8))
                y = float(t.height_at(x, z))
                if y < REG.SEA_LEVEL + 0.20:
                    continue
                near_water = y < REG.SEA_LEVEL + 1.1
                key = (f"shore_reed_{ground % 4}" if near_water
                       else f"undergrowth_{ground % 4}")
                build.place(Placement(
                    node=f"ground_{ground:04d}", mesh=key, position=(x, y, z),
                    rotation_y=float(rng.uniform(0, math.pi * 2)),
                    scale=float(rng.uniform(0.7, 1.3)), kind="undergrowth"))
                ground += 1
    build.notes.append(f"planting: {palms} palms, {ground} ground patches")


# ==========================================================================
# props
# ==========================================================================
def populate_props(build, seed: int, network: dict) -> None:
    """Boats, gear and household clutter along the walkway network."""
    t = build.terrain
    rng = Rng(seed + 79)

    for i in range(4):
        build.add_mesh(f"dugout_{i}", SK.dugout(5.6 + i * 0.5, seed + 700 + i))
        build.add_mesh(f"net_rack_{i}", SK.net_rack(seed + 710 + i,
                                                    2.8 + i * 0.3))
        build.add_mesh(f"fish_trap_{i}", SK.fish_trap(seed + 720 + i))
        build.add_mesh(f"water_jar_{i}", SK.water_jar(seed + 730 + i,
                                                      0.66 + i * 0.09))
        build.add_mesh(f"crate_{i}", P.crate(0.58 + i * 0.06, seed + 740 + i,
                                             material=DK.BAMBOO))
        build.add_mesh(f"basket_{i}", P.basket(0.32, 0.44, seed + 750 + i))
    build.add_mesh("fishing_gear", P.fishing_gear(seed + 760))
    build.add_mesh("market_stall", P.market_stall(2.6, 1.8, seed + 770,
                                                  goods="foliage_green"))

    boats = clutter = 0
    for segment in network["segments"]:
        if not rng.chance(0.85):
            continue
        ax, az = segment["a"]
        bx, bz = segment["b"]
        tx = float(rng.uniform(0.2, 0.8))
        x = ax + (bx - ax) * tx
        z = az + (bz - az) * tx
        normal = segment["angle"] + math.pi * 0.5
        offset = float(rng.uniform(2.6, 4.4)) * (1.0 if rng.chance(0.5) else -1.0)
        bx2 = x + math.cos(normal) * offset
        bz2 = z + math.sin(normal) * offset
        if float(t.height_at(bx2, bz2)) < REG.SEA_LEVEL - 0.5:
            build.place(Placement(
                node=f"moored_boat_{boats:03d}", mesh=f"dugout_{boats % 4}",
                position=(bx2, REG.SEA_LEVEL - 0.14, bz2),
                rotation_y=segment["angle"] + float(rng.uniform(-0.3, 0.3)),
                kind="prop"))
            boats += 1
        # gear on the deck itself
        for _repeat in range(int(rng.integers(1, 4))):
            choice = int(rng.integers(0, 5))
            mesh = (f"net_rack_{clutter % 4}" if choice == 0 else
                    f"fish_trap_{clutter % 4}" if choice == 1 else
                    f"water_jar_{clutter % 4}" if choice == 2 else
                    f"crate_{clutter % 4}" if choice == 3 else
                    f"basket_{clutter % 4}")
            side = float(rng.uniform(0.55, 0.95)) * \
                (1.0 if rng.chance(0.5) else -1.0)
            build.place(Placement(
                node=f"deck_gear_{clutter:03d}", mesh=mesh,
                position=(x + math.cos(normal) * side, segment["level"],
                          z + math.sin(normal) * side),
                rotation_y=float(rng.uniform(0, math.pi * 2)), kind="prop"))
            clutter += 1

    # stalls along the market hall's deck
    market = REG.ANCHORS["market_hall"]
    level = network["levels"].get("market_hall", REG.SEA_LEVEL + DECK_CLEAR)
    for i in range(6):
        yaw=math.radians(20);along=(i%3-1)*4.8;side=-1 if i<3 else 1
        x=market[0]+math.cos(yaw)*along+math.sin(yaw)*side*3.55
        z=market[1]-math.sin(yaw)*along+math.cos(yaw)*side*3.55
        build.place(Placement(node=f"market_stall_{i:02d}",mesh="market_stall",
                   position=(x,level,z),rotation_y=yaw+(math.pi if side>0 else 0),kind="prop"))
    build.notes.append(f"props: {boats} moored boats, {clutter} deck gear")


# ==========================================================================
# metadata
# ==========================================================================
def surface_at(build, x: float, z: float) -> float:
    """Highest walk deck covering (x, z), else terrain. See build script."""
    best = float(build.terrain.height_at(x, z))
    for placement in build.placements:
        item = build.meshes[placement.mesh]
        walk_bounds = getattr(item, "walk_bounds", lambda: None)()
        if walk_bounds is None:
            if not placement.walk_surface:
                continue
            low, high = item.bounds()
        else:
            low, high = walk_bounds
        px, py, pz = placement.position
        angle = float(placement.rotation_y or 0.0)
        cosine, sine = math.cos(angle), math.sin(angle)
        lx = cosine * (x - px) - sine * (z - pz)
        lz = sine * (x - px) + cosine * (z - pz)
        if not (float(low[0]) * placement.scale <= lx <= float(high[0]) * placement.scale
                and float(low[2]) * placement.scale <= lz
                <= float(high[2]) * placement.scale):
            continue
        best = max(best, py + float(high[1]) * placement.scale)
    return best


def populate_metadata(build, seed: int, network: dict) -> None:
    """Landmarks, interactives and the server-authoritative population markers.

    Nothing here is baked into the static mesh. NPCs, creature groups and
    harvestables are positions carrying `"authority": "server"`; the server
    owns whether anything is actually there.
    """
    t = build.terrain
    rng = Rng(seed + 83)
    levels = network["levels"]

    named = {
        "great-arch": ("The Manymouth Arch",
                       "The drowned ring-gate standing over the central whirl."),
        "green-temple": ("The Green Temple",
                         "A stepped bronze-banded temple on the delta's east rim."),
        "moot-hall": ("The Tide Hall",
                      "The town's tiered meeting hall, its ridge capped in bronze."),
        "market-hall": ("The Long Market",
                        "A barrel-vaulted market hall over the main walkway."),
        "labyrinth-mouth": ("Mouth of the Flooded Labyrinth",
                            "The cut arch into the drowned ruins under the headland."),
        "stelae-court": ("The Stelae Court",
                         "A ring of glyph-cut stones on a silt bar."),
        "great-banyan": ("The Root Landing",
                         "A deck built inside the aerial roots of a great banyan."),
        "deck-study": ("The Ferry Post",
                       "Matting, rope, a bronze-headed staff and fallen blossom."),
        "delta-overlook": ("The Long Look",
                           "A plank deck on a bar edge, open to the whole fan."),
        "paddy-watchtower": ("The Paddy Watch",
                             "A stilted watch over the terraced water."),
        "east-watch": ("The East Watch", "A stilt watch on the eastern reach."),
        "south-shrine": ("The South Shrine", "A single stele on a southern bar."),
    }
    for placement in build.placements:
        if not placement.landmark:
            continue
        title, blurb = named.get(placement.landmark,
                                 (placement.landmark, ""))
        build.landmarks.append({
            "id": placement.landmark, "name": title, "description": blurb,
            "node": placement.node,
            "position": [round(float(v), 2) for v in placement.position],
            "serverTile": [int(round(placement.position[0] + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - placement.position[2]))],
        })

    # interactives: the things a player clicks
    for ident, name, anchor, kind in (
            ("arch-gate", "The Manymouth Arch", "great_arch", "portal-focus"),
            ("labyrinth-door", "Mouth of the Flooded Labyrinth", "cave_mouth",
             "interior-entrance"),
            ("moot-hall-door", "Tide Hall", "town_hall", "door"),
            ("market-scales", "Market Scales", "market_hall", "vendor"),
            ("ferry-post", "Ferry Post", "town_quay", "travel"),
            ("temple-altar", "Temple Altar", "green_temple", "shrine"),
            ("paddy-sluice", "Paddy Sluice", "paddy_terraces", "mechanism")):
        x, z = REG.ANCHORS[anchor]
        # Read off the real walk surfaces: an interactive placed at the
        # network's nominal deck level ends up under the veranda of whatever
        # building actually stands on that anchor.
        y = surface_at(build, x, z)
        build.interactives.append({
            "id": ident, "name": name, "type": kind,
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "authority": "server"})

    # NPC and creature markers
    for index, (anchor, role, count) in enumerate((
            ("stilt_town", "villager", 9), ("floating_market", "trader", 7),
            ("town_quay", "ferryman", 3), ("green_temple", "acolyte", 4),
            ("paddy_terraces", "farmer", 5), ("east_hamlet", "villager", 4),
            ("south_hamlet", "villager", 4), ("boat_yard", "shipwright", 3),
            ("west_hamlet", "villager", 3), ("north_fishing", "fisher", 4))):
        cx, cz = REG.ANCHORS[anchor]
        for i in range(count):
            angle = float(rng.uniform(0, math.pi * 2))
            r = float(rng.uniform(3.0, 16.0)) * REG.LOCAL
            x, z = cx + math.cos(angle) * r, cz + math.sin(angle) * r
            y = levels.get(anchor, float(t.height_at(x, z)))
            build.npc_markers.append({
                "id": f"{anchor}-{role}-{i}", "role": role,
                "position": [round(x, 2), round(y, 2), round(z, 2)],
                "authority": "server"})

    for index, (anchor, species, count) in enumerate((
            ("mangrove_reach", "delta-crocodile", 4),
            ("great_arch", "drowned-sentinel", 5),
            ("cave_mouth", "labyrinth-crawler", 5),
            ("sea_landing", "shore-raider", 4),
            ("deep_grove", "canopy-serpent", 4),
            ("ruin_stelae", "silt-wight", 4))):
        cx, cz = REG.ANCHORS[anchor]
        for i in range(count):
            angle = float(rng.uniform(0, math.pi * 2))
            r = float(rng.uniform(6.0, 24.0)) * REG.LOCAL
            x, z = cx + math.cos(angle) * r, cz + math.sin(angle) * r
            build.npc_markers.append({
                "id": f"{anchor}-{species}-{i}", "role": "creature",
                "species": species,
                "position": [round(x, 2), round(float(t.height_at(x, z)), 2),
                             round(z, 2)],
                "authority": "server"})

    # harvestables
    for index, (anchor, resource, count) in enumerate((
            ("paddy_terraces", "lotus-root", 8), ("upper_paddy", "rice", 8),
            ("mangrove_reach", "mangrove-bark", 7),
            ("banyan_landing", "banyan-resin", 5),
            ("floating_market", "river-fish", 6),
            ("far_bar", "shell-lime", 6), ("sea_landing", "salt-pan", 5),
            ("deep_grove", "palm-heart", 6))):
        cx, cz = REG.ANCHORS[anchor]
        for i in range(count):
            angle = float(rng.uniform(0, math.pi * 2))
            r = float(rng.uniform(4.0, 20.0)) * REG.LOCAL
            x, z = cx + math.cos(angle) * r, cz + math.sin(angle) * r
            build.harvestables.append({
                "id": f"{resource}-{index}-{i}", "resource": resource,
                "position": [round(x, 2), round(float(t.height_at(x, z)), 2),
                             round(z, 2)],
                "authority": "server"})
