"""Placement passes for Grey Moors.

Terrain was proved first: the grounding contract holds on bare ground before any
of this goes in, as the region production guide requires.

The inventory follows the region's QA brief, whose counts agree with what the
aerial actually shows: six barrows, eight standing-stone groups, eight
boardwalks, four crypt entrances, six abandoned cottages, ten dead trees and
five ritual shrines. To that the painting adds what the brief omits - six broken
towers on the skyline, four peat workings, and the waymarkers and cairns that
make the track web legible.

Unlike the other regions there is almost no material remapping here: the moor
kit in `_toolkit/amberwood/moorcraft.py` is written against this region's own
palette, so a kit piece arrives carrying a material this package already
embeds. The two shared kits that are still used - `props` for small scatter and
`terrain` for water - are the only things that need mapping.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import moorcraft as MC
from amberwood import noise as N
from amberwood import terrain as TER

import region as REG
import layout as LAY
from region import Placement

L = REG.LOCAL

GRANITE = "grey_moor_granite"
DRYSTONE = "grey_drystone"
TIMBER = "grey_bog_timber"


# --------------------------------------------------------------------------
def _ground(t: TER.Terrain, x: float, z: float, sink: float = 0.0):
    return float(x), float(t.height_at(x, z)) - sink, float(z)


def _face(origin, target) -> float:
    return math.atan2(target[0] - origin[0], target[1] - origin[1])


def _landmark(build, entry_id, name, node, kind, position):
    build.landmarks.append({
        "id": entry_id, "name": name, "node": node, "type": kind,
        "position": [round(float(position[0]), 2), round(float(position[1]), 2),
                     round(float(position[2]), 2)]})


def _detail(lod: str | None) -> str:
    return "low" if lod == "far" else "high"


def _downhill(t: TER.Terrain, x: float, z: float, step: float = 6.0) -> float:
    """The compass bearing of the steepest descent at a point.

    Barrow portals and crypt doors face out of the mound they are cut into,
    which is downhill. Facing them at a fixed angle put half of them looking
    into their own hillside.
    """
    here = float(t.height_at(x, z))
    best_angle, best_drop = 0.0, 0.0
    for index in range(12):
        angle = index * math.tau / 12.0
        drop = here - float(t.height_at(x + math.sin(angle) * step,
                                        z + math.cos(angle) * step))
        if drop > best_drop:
            best_drop, best_angle = drop, angle
    return best_angle


# --------------------------------------------------------------------------
def populate_landmarks(build: REG.RegionBuild, seed: int,
                       lod: str | None = None) -> None:
    t = build.terrain
    A = REG.ANCHORS
    detail = _detail(lod)

    # -- the Great Barrow --------------------------------------------------
    # Its mound is terrain (raised in `region.build_terrain`), so what goes in
    # here is the portal cut into the mound's downhill face, the stone court
    # on the crown, and the votive lights.
    gx, gz = A["great_barrow"]
    facing = 0.0
    # stand the portal part-way down the flank, not at the crown
    px = gx + math.sin(facing) * 15.0 * L
    pz = gz + 32.0
    build.add_mesh("GreatBarrowPortal",
                   MC.barrow_portal(2.0, 2.6, seed=seed + 1, revetment=7.5, preserve_materials=True))
    x, y, z = _ground(t, px, pz, sink=0.25)
    build.place(Placement("Landmark_GreatBarrow", "GreatBarrowPortal",
                          (x, y, z), facing, 1.0, collides=True,
                          kind="landmark", landmark="grey-great-barrow"))
    t.mark_blocked_disc((px, pz), 1.8)
    _landmark(build, "grey-great-barrow", "The Great Barrow",
              "Landmark_GreatBarrow", "monument", (x, y + 1.2, z))

    # the stone court crowning it, which is what the aerial's crowned hill is
    build.add_mesh("GreatBarrowRing", MC.stone_ring(radius=9.0 * L, count=13,
                                                    seed=seed + 3, altar=True,
                                                    height=4.6))
    cx, cy, cz = _ground(t, *A["ring_court"], sink=0.30)
    build.place(Placement("Landmark_GreatBarrowCourt", "GreatBarrowRing",
                          (cx, cy, cz), 0.0, 1.0, collides=False,
                          kind="stone", landmark="grey-barrow-court"))
    _landmark(build, "grey-barrow-court", "The Court of Standing Stones",
              "Landmark_GreatBarrowCourt", "monument", (cx, cy + 1.7, cz))

    # -- five lesser barrows, six with the Great Barrow --------------------
    for index, key in enumerate(("barrow_north", "barrow_east", "barrow_west",
                                 "barrow_south", "barrow_far_east")):
        bx, bz = A[key]
        facing = _downhill(t, bx, bz, step=9.0)
        radius = next(r for n, r, _h in REG.BARROW_MOUNDS if n == key)
        px = bx + math.sin(facing) * radius * L * 0.62
        pz = bz + math.cos(facing) * radius * L * 0.62
        mesh_key = f"BarrowPortal_{index}"
        build.add_mesh(mesh_key, MC.barrow_portal(1.5, 2.1, seed=seed + 11 + index,
                                                  revetment=5.2, preserve_materials=True))
        x, y, z = _ground(t, px, pz, sink=0.20)
        build.place(Placement(f"Landmark_Barrow_{index}", mesh_key, (x, y, z),
                              facing, 1.0, collides=True, kind="landmark",
                              landmark=f"grey-barrow-{index}"))
        t.mark_blocked_disc((px, pz), 3.6 * L)
        _landmark(build, f"grey-barrow-{index}", "Grey Moor Barrow",
                  f"Landmark_Barrow_{index}", "monument", (x, y + 1.0, z))

    # -- four crypt entrances (panel 5) ------------------------------------
    for index, key in enumerate(("crypt_great", "crypt_west", "crypt_east",
                                 "crypt_south")):
        kx, kz = A[key]
        facing = _downhill(t, kx, kz, step=8.0)
        mesh_key = f"CryptEntrance_{index}"
        build.add_mesh(mesh_key, MC.crypt_entrance(seed=seed + 31 + index, preserve_materials=True))
        x, y, z = _ground(t, kx, kz, sink=0.15)
        build.place(Placement(f"Landmark_Crypt_{index}", mesh_key, (x, y, z),
                              facing, 1.0, collides=True, kind="landmark",
                              landmark=f"grey-crypt-{index}"))
        t.mark_blocked_disc((kx, kz), 3.2 * L)
        _landmark(build, f"grey-crypt-{index}", "Grey Moor Crypt Entrance",
                  f"Landmark_Crypt_{index}", "entrance", (x, y + 1.3, z))

    # The interior portals in `build_grey_moors._add_spawns_and_portals` look
    # these up by id, so the three that carry doors keep stable names.
    for source_id, alias in (("grey-crypt-1", "grey-crypt-west"),
                             ("grey-crypt-2", "grey-crypt-east"),
                             ("grey-crypt-3", "grey-crypt-south")):
        for entry in build.landmarks:
            if entry["id"] == source_id:
                entry["id"] = alias

    # -- eight standing-stone groups (panel 3) -----------------------------
    ring_keys = ("ring_centre", "ring_north", "ring_east", "ring_west",
                 "ring_south", "ring_coast", "ring_far_east")
    for index, key in enumerate(ring_keys):
        mesh_key = f"StoneRing_{index}"
        count = 7 + (index % 4)
        build.add_mesh(mesh_key, MC.stone_ring(radius=(5.0 + index % 3) * L,
                                               count=count, seed=seed + 51 + index,
                                               altar=index % 3 == 0, height=3.6))
        x, y, z = _ground(t, *A[key], sink=0.25)
        build.place(Placement(f"Landmark_StoneRing_{index}", mesh_key, (x, y, z),
                              (index * 0.7) % math.tau, 1.0, collides=False,
                              kind="stone", landmark=f"grey-stone-ring-{index}"))
        _landmark(build, f"grey-stone-ring-{index}", "Grey Moor Standing Stones",
                  f"Landmark_StoneRing_{index}", "monument", (x, y + 1.4, z))

    # -- five ritual shrines (the altar slabs) ------------------------------
    for index, key in enumerate(("shrine_great", "shrine_bog", "shrine_east",
                                 "shrine_coast", "shrine_north")):
        mesh_key = f"Shrine_{index}"
        shrine = MC.altar_slab(seed=seed + 71 + index, span=2.6 * L)
        shrine.add(MC.candle_cluster(6, 1.5 * L, seed=seed + 81 + index))
        shrine.add(MC.menhir(2.4, seed + 91 + index).translate(-2.2 * L, 0.0, 0.0))
        shrine.add(MC.menhir(2.2, seed + 92 + index).translate(2.2 * L, 0.0, 0.0))
        build.add_mesh(mesh_key, shrine)
        x, y, z = _ground(t, *A[key], sink=0.10)
        build.place(Placement(f"Landmark_Shrine_{index}", mesh_key, (x, y, z),
                              (index * 1.1) % math.tau, 1.0, collides=True,
                              kind="landmark", landmark=f"grey-shrine-{index}"))
        t.mark_blocked_disc(A[key], 2.0 * L)
        _landmark(build, f"grey-shrine-{index}", "Grey Moor Ritual Shrine",
                  f"Landmark_Shrine_{index}", "shrine", (x, y + 0.9, z))

    # -- six broken towers on the skyline ----------------------------------
    for index, key in enumerate(("tower_nw", "tower_west", "tower_south_west",
                                 "tower_east", "tower_north_east", "tower_south")):
        mesh_key = f"TowerRuin_{index}"
        build.add_mesh(mesh_key, MC.tower_ruin(seed=seed + 101 + index,
                                               height=8.0 + (index % 3) * 1.6,
                                               radius=2.2 + (index % 2) * 0.4))
        x, y, z = _ground(t, *A[key], sink=0.35)
        build.place(Placement(f"Landmark_Tower_{index}", mesh_key, (x, y, z),
                              (index * 0.9) % math.tau, 1.0, collides=True,
                              kind="landmark", landmark=f"grey-tower-{index}"))
        t.mark_blocked_disc(A[key], 3.0 * L)
        _landmark(build, f"grey-tower-{index}", "Grey Moor Broken Tower",
                  f"Landmark_Tower_{index}", "ruin", (x, y + 1.6, z))

    # -- six abandoned crofts (panel 6) ------------------------------------
    for index, key in enumerate(("croft_coast", "croft_south", "croft_west",
                                 "croft_east", "croft_north", "croft_mid")):
        mesh_key = f"CroftRuin_{index}"
        build.add_mesh(mesh_key, MC.cottage_ruin(seed=seed + 131 + index,
                                                 length=7.0 + (index % 3) * 0.9,
                                                 width=4.6, wall_height=2.0))
        x, y, z = _ground(t, *A[key], sink=0.18)
        rotation = (index * 1.4) % math.tau
        build.place(Placement(f"Landmark_Croft_{index}", mesh_key, (x, y, z),
                              rotation, 1.0, collides=True, kind="building",
                              landmark=f"grey-croft-{index}"))
        t.mark_blocked_disc(A[key], 4.6 * L)
        _landmark(build, f"grey-croft-{index}", "Grey Moor Abandoned Cottage",
                  f"Landmark_Croft_{index}", "ruin", (x, y + 1.4, z))
        # its enclosure, a couple of runs of leaning fence
        for run in range(2):
            fence_key = f"CroftFence_{index}_{run}"
            build.add_mesh(fence_key, MC.peat_fence(6.0 * L, seed=seed + 141 + index * 3 + run))
            angle = rotation + math.pi * (0.5 + run)
            fx = A[key][0] + math.sin(angle) * 6.0 * L
            fz = A[key][1] + math.cos(angle) * 6.0 * L
            build.place(Placement(f"Prop_CroftFence_{index}_{run}", fence_key,
                                  _ground(t, fx, fz, sink=0.10), angle, 1.0,
                                  collides=False, kind="prop"))

    # -- four peat workings (panel 8) --------------------------------------
    for index, key in enumerate(("peat_west", "peat_centre", "peat_north",
                                 "peat_east")):
        mesh_key = f"PeatCutting_{index}"
        build.add_mesh(mesh_key, MC.peat_cutting(seed=seed + 161 + index,
                                                 span=7.0 * L))
        x, y, z = _ground(t, *A[key], sink=0.05)
        build.place(Placement(f"Landmark_PeatCutting_{index}", mesh_key,
                              (x, y, z), (index * 1.6) % math.tau, 1.0,
                              collides=True, kind="landmark",
                              landmark=f"grey-peat-working-{index}"))
        t.mark_blocked_disc(A[key], 5.0 * L)
        _landmark(build, f"grey-peat-working-{index}", "Grey Moor Peat Cutting",
                  f"Landmark_PeatCutting_{index}", "worksite", (x, y + 1.0, z))

    # -- ten dead trees (panel 7); the Hanged Oak is the one that carries it
    build.add_mesh("HangedOak", MC.dead_tree(seed=seed + 181, detail=detail,
                                             profile="moor_oak_snag"))
    x, y, z = _ground(t, *A["hanged_oak"], sink=0.30)
    build.place(Placement("Landmark_HangedOak", "HangedOak", (x, y, z), 0.4,
                          1.25, collides=True, kind="tree",
                          landmark="grey-hanged-oak"))
    t.mark_blocked_disc(A["hanged_oak"], 3.0 * L)
    _landmark(build, "grey-hanged-oak", "The Hanged Oak", "Landmark_HangedOak",
              "landmark-tree", (x, y + 1.8, z))
    # its attendant wisps, the figures under the tree in the panel
    for index in range(4):
        wisp_key = f"OakWisp_{index}"
        build.add_mesh(wisp_key, MC.wisp(seed=seed + 191 + index))
        angle = index * math.tau / 4.0 + 0.4
        wx = A["hanged_oak"][0] + math.sin(angle) * (5.0 + index) * L
        wz = A["hanged_oak"][1] + math.cos(angle) * (5.0 + index) * L
        build.place(Placement(f"Prop_OakWisp_{index}", wisp_key,
                              _ground(t, wx, wz), 0.0, 1.0, collides=False,
                              kind="prop"))

    # the other nine, scattered where the moor is wettest
    rng = np.random.default_rng(seed ^ 0x7EED)
    placed = 0
    attempts = 0
    tree_sites: list[tuple[float, float]] = []
    while placed < 9 and attempts < 400:
        attempts += 1
        tx = float(rng.uniform(REG.PLAY_MIN_X + 40, REG.PLAY_MAX_X - 40))
        tz = float(rng.uniform(REG.PLAY_MIN_Z + 40, REG.PLAY_MAX_Z - 40))
        surface = int(t.surface_at(tx, tz))
        if surface not in (TER.PEAT_BOG, TER.HEATHER_MOOR):
            continue
        if float(t.height_at(tx, tz)) < REG.SEA_LEVEL + 1.0:
            continue
        if any(math.hypot(tx - ox, tz - oz) < 70.0 for ox, oz in tree_sites):
            continue
        tree_sites.append((tx, tz))
        profile = "moor_oak_snag" if placed % 3 == 0 else "moor_thorn_snag"
        mesh_key = f"DeadTree_{placed}"
        build.add_mesh(mesh_key, MC.dead_tree(seed=seed + 211 + placed,
                                              detail=detail, profile=profile))
        build.place(Placement(f"Landmark_DeadTree_{placed}", mesh_key,
                              _ground(t, tx, tz, sink=0.25),
                              float(rng.uniform(0.0, math.tau)),
                              0.85 + float(rng.uniform(0.0, 0.3)),
                              collides=True, kind="tree",
                              landmark=f"grey-dead-tree-{placed}"))
        t.mark_blocked_disc((tx, tz), 1.8 * L)
        _landmark(build, f"grey-dead-tree-{placed}", "Grey Moor Dead Tree",
                  f"Landmark_DeadTree_{placed}", "landmark-tree",
                  (tx, float(t.height_at(tx, tz)) + 1.5, tz))
        placed += 1


# --------------------------------------------------------------------------
def populate_routes(build: REG.RegionBuild, seed: int,
                    lod: str | None = None) -> None:
    """Boardwalks, bridges, waymarkers, cairns and the stone avenue."""
    t = build.terrain
    A = REG.ANCHORS

    LAY.dress_crossings(build,seed)

    # -- the stone avenue up to the Great Barrow ---------------------------
    court = A["great_barrow_court"]
    shrine = A["shrine_great"]
    avenue_length = float(np.hypot(court[0] - shrine[0], court[1] - shrine[1]))
    build.add_mesh("StoneAvenue", MC.stone_avenue(length=avenue_length,
                                                  spacing=5.0 * L,
                                                  width=6.0 * L, seed=seed + 361))
    mid = ((court[0] + shrine[0]) * 0.5, (court[1] + shrine[1]) * 0.5)
    build.place(Placement("Landmark_StoneAvenue", "StoneAvenue",
                          _ground(t, *mid, sink=0.25),
                          math.atan2(court[0] - shrine[0], court[1] - shrine[1]),
                          1.0, collides=False, kind="stone",
                          landmark="grey-stone-avenue"))
    _landmark(build, "grey-stone-avenue", "The Barrow Avenue",
              "Landmark_StoneAvenue", "monument",
              (mid[0], float(t.height_at(*mid)) + 1.5, mid[1]))

    # -- waymarkers and cairns along the tracks ----------------------------
    # These are the small bright points scattered all over the aerial, and they
    # are what makes the route web read from the air and navigable on foot.
    rng = np.random.default_rng(seed ^ 0x3A17)
    marker_index = 0
    cairn_index = 0
    for name, points in REG.ROUTES.items():
        pts = np.asarray(points, dtype=np.float64)
        # walk the polyline at a fixed interval in metres
        spacing = 46.0
        carried = 0.0
        for segment in range(len(pts) - 1):
            ax, az = pts[segment]
            bx, bz = pts[segment + 1]
            seg_length = float(np.hypot(bx - ax, bz - az))
            if seg_length < 1e-6:
                continue
            distance = spacing - carried
            while distance < seg_length:
                u = distance / seg_length
                mx = ax + (bx - ax) * u
                mz = az + (bz - az) * u
                # offset to the shoulder so the marker never stands in the track
                offset = 2.4 * L * (1.0 if marker_index % 2 == 0 else -1.0)
                nx = -(bz - az) / seg_length * offset
                nz = (bx - ax) / seg_length * offset
                px, pz = mx + nx, mz + nz
                if float(t.height_at(px, pz)) > REG.SEA_LEVEL + 0.6:
                    if marker_index % 3 == 2:
                        key = f"Cairn_{cairn_index}"
                        build.add_mesh(key, MC.cairn(1.3 + (cairn_index % 3) * 0.25,
                                                     seed=seed + 401 + cairn_index,
                                                     lit=cairn_index % 2 == 0))
                        build.place(Placement(f"Prop_Cairn_{cairn_index}", key,
                                              _ground(t, px, pz, sink=0.08),
                                              float(rng.uniform(0, math.tau)),
                                              1.0, collides=False, kind="prop"))
                        cairn_index += 1
                    else:
                        key = f"Waymarker_{marker_index}"
                        build.add_mesh(key, MC.waymarker(2.7, seed=seed + 431 + marker_index))
                        build.place(Placement(f"Prop_Waymarker_{marker_index}", key,
                                              _ground(t, px, pz, sink=0.10),
                                              float(rng.uniform(0, math.tau)),
                                              1.0, collides=False, kind="prop"))
                    marker_index += 1
                distance += spacing
            carried = (carried + seg_length) % spacing


# --------------------------------------------------------------------------
def populate_bog(build: REG.RegionBuild, seed: int,
                 lod: str | None = None) -> None:
    """Standing water in the hollows, and the wisps over it."""
    t = build.terrain
    rng = np.random.default_rng(seed ^ 0x8B06)

    for index, ((cx, cz), radius, depth) in enumerate(REG.BOG_BASINS):
        wx, wz = cx * REG.SCALE, cz * REG.SCALE
        level = t._moor_pool_levels[index]
        if level < REG.SEA_LEVEL + 0.4:
            continue
        # the pool fills the lower part of the hollow, not the whole of it
        pool_radius = radius * REG.SCALE * 0.62
        key = f"BogPool_{index}"
        build.add_mesh(key, MC.bog_pool_skin(radius=pool_radius,
                                             seed=seed + 501 + index,
                                             segments=18))
        build.place(Placement(f"Water_BogPool_{index}", key, (wx, level, wz),
                              0.0, 1.0, collides=False, kind="prop"))
        # The deep middle of a pool is not walkable. The margin still is: the
        # concept's bog is ground you wade, with only the deep parts bridged.
        t.mark_blocked_disc((wx, wz), pool_radius * 0.86)

        # a wisp or two over the bigger pools
        if radius >= 12.0:
            for w in range(2):
                wisp_key = f"BogWisp_{index}_{w}"
                build.add_mesh(wisp_key, MC.wisp(seed=seed + 521 + index * 3 + w))
                angle = float(rng.uniform(0, math.tau))
                distance = pool_radius * float(rng.uniform(0.3, 0.9))
                build.place(Placement(f"Prop_BogWisp_{index}_{w}", wisp_key,
                                      (wx + math.sin(angle) * distance,
                                       level + 0.35,
                                       wz + math.cos(angle) * distance),
                                      0.0, 1.0, collides=False, kind="prop"))


# --------------------------------------------------------------------------
def populate_ground_detail(build: REG.RegionBuild, seed: int) -> None:
    """Heather, sedge and loose stone over the open moor.

    Sites are chosen by surface class, which is why `assign_surfaces` runs
    before the placement passes and not after.
    """
    t = build.terrain
    rng = np.random.default_rng(seed ^ 0x11FE)

    # -- ground scrub -------------------------------------------------------
    # One mesh per variant, instanced many times: the exporter batches repeats
    # of the same mesh, so twelve variants at a few hundred instances each is
    # far cheaper than a unique clump per site.
    # Each variant is a PATCH of cards rather than a single clump: at two or
    # three cards apiece the moor was bare between the scatter points and the
    # region came out at 1.1 triangles per square metre, a third of what the
    # sparsest finished region uses. Bigger patches raise cover without
    # multiplying the node count.
    variants = 14
    for index in range(variants):
        build.add_mesh(f"Scrub_{index}",
                       MC.scrub_clump(seed=seed + 601 + index,
                                      radius=1.5 + (index % 4) * 0.28,
                                      cards=10 + index % 5,
                                      height=0.38 + (index % 5) * 0.075))

    step = 5.0
    xs = np.arange(REG.PLAY_MIN_X + 6.0, REG.PLAY_MAX_X - 6.0, step)
    zs = np.arange(REG.PLAY_MIN_Z + 6.0, REG.PLAY_MAX_Z - 6.0, step)
    scatter = 0
    for zi, z in enumerate(zs):
        for xi, x in enumerate(xs):
            jx = x + float(rng.uniform(-step * 0.45, step * 0.45))
            jz = z + float(rng.uniform(-step * 0.45, step * 0.45))
            surface = int(t.surface_at(jx, jz))
            if surface == TER.HEATHER_MOOR:
                chance = 0.80
            elif surface == TER.PEAT_BOG:
                chance = 0.46
            elif surface == TER.BARROW_TURF:
                chance = 0.24
            else:
                continue
            if rng.random() > chance:
                continue
            height = float(t.height_at(jx, jz))
            if height < REG.SEA_LEVEL + 0.5:
                continue
            if bool(t.blocked_at(jx, jz)):
                continue
            index = int(rng.integers(0, variants))
            build.place(Placement(f"Scatter_Scrub_{scatter}", f"Scrub_{index}",
                                  (jx, height - 0.05, jz),
                                  float(rng.uniform(0, math.tau)),
                                  0.80 + float(rng.uniform(0.0, 0.40)),
                                  collides=False, kind="scatter"))
            scatter += 1

    # -- loose stone: erratics and outcrop on the open moor -----------------
    for index in range(8):
        build.add_mesh(f"Erratic_{index}", MC.menhir(0.6 + (index % 4) * 0.30,
                                                     seed=seed + 701 + index))
    stones = 0
    for _ in range(1400):
        sx = float(rng.uniform(REG.PLAY_MIN_X + 10, REG.PLAY_MAX_X - 10))
        sz = float(rng.uniform(REG.PLAY_MIN_Z + 10, REG.PLAY_MAX_Z - 10))
        surface = int(t.surface_at(sx, sz))
        if surface not in (TER.HEATHER_MOOR, TER.ROCK, TER.BARROW_TURF):
            continue
        height = float(t.height_at(sx, sz))
        if height < REG.SEA_LEVEL + 0.6 or bool(t.blocked_at(sx, sz)):
            continue
        index = int(rng.integers(0, 8))
        build.place(Placement(f"Scatter_Erratic_{stones}", f"Erratic_{index}",
                              (sx, height - 0.18, sz),
                              float(rng.uniform(0, math.tau)),
                              0.8 + float(rng.uniform(0.0, 0.9)),
                              collides=False, kind="scatter"))
        stones += 1

    # -- scattered standing stones ----------------------------------------
    # The aerial is COVERED in menhirs: they are not confined to the rings,
    # they stand singly and in twos and threes right across the moor, and they
    # are most of what gives the painting its density from the air. Eight rings
    # and a scatter of boulders did not read as the same place.
    for index in range(10):
        build.add_mesh(f"Menhir_{index}",
                       MC.menhir(2.6 + (index % 5) * 0.46, seed=seed + 801 + index))
    menhirs = 0
    for _ in range(2600):
        mx = float(rng.uniform(REG.PLAY_MIN_X + 12, REG.PLAY_MAX_X - 12))
        mz = float(rng.uniform(REG.PLAY_MIN_Z + 12, REG.PLAY_MAX_Z - 12))
        surface = int(t.surface_at(mx, mz))
        if surface not in (TER.HEATHER_MOOR, TER.BARROW_TURF):
            continue
        height = float(t.height_at(mx, mz))
        if height < REG.SEA_LEVEL + 1.0 or bool(t.blocked_at(mx, mz)):
            continue
        if float(t.slope_at(mx, mz)) > 0.55:
            continue
        index = int(rng.integers(0, 10))
        build.place(Placement(f"Scatter_Menhir_{menhirs}", f"Menhir_{index}",
                              (mx, height - 0.22, mz),
                              float(rng.uniform(0, math.tau)),
                              0.85 + float(rng.uniform(0.0, 0.55)),
                              collides=False, kind="stone"))
        menhirs += 1
        if menhirs >= 360:
            break

    build.notes.append(f"ground detail: {scatter} scrub clumps, {stones} erratics, "
                       f"{menhirs} scattered standing stones")


# --------------------------------------------------------------------------
def build_water(build: REG.RegionBuild) -> None:
    """The corner sea. Bog pools carry their own skins in `populate_bog`."""
    t = build.terrain
    sea = TER.water_plane(t, REG.SEA_LEVEL,
                          REG.TERRAIN_X0, REG.TERRAIN_Z0,
                          REG.TERRAIN_X0 + REG.TERRAIN_SIZE_X,
                          REG.TERRAIN_Z0 + REG.TERRAIN_SIZE_Z,
                          material="water_sea")
    if sea is not None and sea.triangle_count:
        build.water_meshes["Water_Sea"] = sea
