"""Mirrorhold placement passes.

Built in the order the production guide prescribes: water and massing first,
then landmarks, then architecture, then dressing. Each pass is independent so
the terrain can be verified for grounding before any of them run.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as ARCH
from amberwood import mesh as M
from amberwood import routecraft as RC
from amberwood import noise as N
from amberwood import props as PROPS
from amberwood import stonework as STONE
from amberwood import terrain as TER
from amberwood import trees as TREES
from amberwood.populate import scatter_points

import landmarks as L
import region as REG
import ring_links as RING_LINKS
from region import ANCHORS, LEVEL, SCALE, LOCAL

from regionbuild import Placement, RegionBuild

ASHLAR_MAT = L.ASHLAR
MARBLE_MAT = L.MARBLE
IRON_MAT = L.IRON
TIMBER_MAT = L.TIMBER
LAKE = REG.LAKE_LEVEL

# Spruce stop well below the snow: an alpine belt, not a forest.
TREE_LINE = 118.0


# --------------------------------------------------------------------- water
def build_water(build: RegionBuild) -> None:
    """The lake, the canals, and the still basins on the citadel terraces."""
    t = build.terrain

    # The lake is bounded by the authored basin, so unlike Amberwood's open sea
    # it is clipped to the terrain rather than run to a horizon.
    lake = TER.water_plane(t, REG.LAKE_LEVEL,
                           t.x0, t.z0, t.x0 + t.size_x, t.z0 + t.size_z,
                           material="water_lake", cell=5.0, margin=0.30)
    if lake.triangle_count:
        build.water_meshes["Water_Lake"] = lake

    # Canals and cascades follow the carved channels.
    parts: list[M.Mesh] = []
    for name, points in REG.WATERCOURSES.items():
        pts = np.asarray(points, dtype=np.float64)
        for index in range(pts.shape[0] - 1):
            a, b = pts[index], pts[index + 1]
            steps = max(2, int(np.linalg.norm(b - a) / 4.0))
            for step in range(steps):
                p0 = a + (b - a) * (step / steps)
                p1 = a + (b - a) * ((step + 1) / steps)
                y0 = float(t.height_at(p0[0], p0[1])) + 0.34
                y1 = float(t.height_at(p1[0], p1[1])) + 0.34
                direction = p1 - p0
                length = float(np.linalg.norm(direction))
                if length < 0.25:
                    continue
                quad = _ribbon(p0, p1, y0, y1, width=4.0 * LOCAL)
                parts.append(quad)
    if parts:
        build.water_meshes["Water_Canal"] = M.merge(parts, material="water_lake")


def _ribbon(p0, p1, y0: float, y1: float, width: float) -> M.Mesh:
    """A flat quad from p0 to p1, used for canal and cascade surfaces."""
    direction = np.asarray(p1, dtype=np.float64) - np.asarray(p0, dtype=np.float64)
    length = float(np.linalg.norm(direction))
    nx, nz = -direction[1] / length, direction[0] / length
    half = width * 0.5
    corners = [
        (p0[0] + nx * half, y0, p0[1] + nz * half),
        (p0[0] - nx * half, y0, p0[1] - nz * half),
        (p1[0] - nx * half, y1, p1[1] - nz * half),
        (p1[0] + nx * half, y1, p1[1] + nz * half),
    ]
    return M.quad(corners, uv_scale=0.25, material="water_lake")


# ------------------------------------------------------------------ helpers
def _ground(t: TER.Terrain, x: float, z: float, sink: float = 0.0):
    return float(x), float(t.height_at(x, z)) - sink, float(z)


def _face(from_xz, to_xz) -> float:
    """Yaw that turns a +Z-facing model toward a target point."""
    return math.atan2(to_xz[0] - from_xz[0], to_xz[1] - from_xz[1])


def _add_landmark(build: RegionBuild, landmark_id: str, name: str, node: str,
                  kind: str, position, extra: dict | None = None) -> None:
    entry = {"id": landmark_id, "name": name, "node": node, "type": kind,
             "position": [round(float(position[0]), 2), round(float(position[1]), 2),
                          round(float(position[2]), 2)]}
    if extra:
        entry.update(extra)
    build.landmarks.append(entry)


# -------------------------------------------------------------- the citadel
def populate_citadel(build: RegionBuild, seed: int = 20260828) -> None:
    """The summit: three courts, the gate, the gallery, towers and the orrery."""
    t = build.terrain
    rng = N.Rng(seed + 101)

    # -- the orrery, the region's crowning landmark ------------------------
    build.add_mesh("Mirrorhold_Armillary", L.armillary(4.6 * LOCAL, seed=seed + 3))
    x, z = ANCHORS["orrery"]
    y = LEVEL["orrery"] + 6.9 * LOCAL
    build.place(Placement("Landmark_Orrery", "Mirrorhold_Armillary", (x, y, z),
                          0.0, 1.0, collides=True, kind="landmark",
                          landmark="orrery"))
    _add_landmark(build, "orrery", "The Orrery", "Landmark_Orrery", "monument",
                  (x, y, z))
    # the drum it stands on
    build.add_mesh("Mirrorhold_OrreryDrum", L.pavilion(
        radius=6.0 * LOCAL, height=4.6, columns=16, seed=seed + 5, dome=False))
    build.place(Placement("Landmark_OrreryDrum", "Mirrorhold_OrreryDrum",
                          _ground(t, x, z), 0.0, 1.0, collides=True,
                          kind="landmark"))
    t.mark_blocked_disc((x, z), 18.0 * LOCAL)

    # -- the citadel courts ------------------------------------------------
    build.add_mesh("Mirrorhold_CitadelHigh", L.citadel_block(
        seed=seed + 11, width=30.0 * LOCAL, depth=17.0 * LOCAL, height=15.0))
    hx, hz = ANCHORS["citadel"][0], ANCHORS["citadel"][1] - 16.0 * LOCAL
    build.place(Placement("Landmark_CitadelHigh", "Mirrorhold_CitadelHigh",
                          (hx, LEVEL["citadel_high"], hz), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="citadel"))
    _add_landmark(build, "citadel", "The Observatory Citadel",
                  "Landmark_CitadelHigh", "structure",
                  (hx, LEVEL["citadel_high"] + 15.2, hz))

    build.add_mesh("Mirrorhold_CitadelCourt", L.citadel_block(
        seed=seed + 13, width=40.0 * LOCAL, depth=22.0 * LOCAL, height=11.0))
    cx, cz = ANCHORS["citadel"]
    build.place(Placement("Landmark_CitadelCourt", "Mirrorhold_CitadelCourt",
                          (cx, LEVEL["citadel_court"], cz + 10.0 * LOCAL), 0.0, 1.0,
                          collides=True, kind="landmark"))
    t.mark_blocked_disc((cx, cz), 34.0 * LOCAL)

    # reflecting basins on the courts - the region's namesake feature
    build.add_mesh("Mirrorhold_Basin_Large", L.reflecting_basin(11.0 * LOCAL,
                                                                5.5 * LOCAL))
    build.add_mesh("Mirrorhold_Basin_Small", L.reflecting_basin(6.0 * LOCAL,
                                                                4.0 * LOCAL))
    for index, (ax, az, level, mesh) in enumerate((
            (cx - 16.0 * LOCAL, cz + 18.0 * LOCAL, LEVEL["citadel_court"],
             "Mirrorhold_Basin_Small"),
            (cx + 16.0 * LOCAL, cz + 18.0 * LOCAL, LEVEL["citadel_court"],
             "Mirrorhold_Basin_Small"),
            (ANCHORS["citadel_gate"][0], ANCHORS["citadel_gate"][1] + 6.0 * LOCAL,
             LEVEL["citadel_gate"], "Mirrorhold_Basin_Large"))):
        build.place(Placement(f"Landmark_Basin_{index}", mesh, (ax, level, az),
                              0.0, 1.0, collides=True, 
                              kind="landmark"))
    _add_landmark(build, "mirror-basins", "The Mirror Basins",
                  "Landmark_Basin_2", "feature",
                  (ANCHORS["citadel_gate"][0], LEVEL["citadel_gate"],
                   ANCHORS["citadel_gate"][1] + 6.0 * LOCAL))

    # -- the gate wall -----------------------------------------------------
    build.add_mesh("Mirrorhold_GateWall", L.gate_wall(26.0 * LOCAL, 9.5,
                                                      seed=seed + 17))
    gx, gz = ANCHORS["citadel_gate"]
    build.place(Placement("Landmark_GateWall", "Mirrorhold_GateWall",
                          _ground(t, gx, gz + 9.0 * LOCAL), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="gate"))
    _add_landmark(build, "gate", "The Lens Gate", "Landmark_GateWall", "structure",
                  (gx, LEVEL["citadel_gate"] + 9.7, gz + 9.0 * LOCAL))
    # flanking wall runs
    for side in (-1.0, 1.0):
        build.place(Placement(f"Landmark_GateWing_{int(side)}",
                              "Mirrorhold_GateWall",
                              _ground(t, gx + side * 26.0 * LOCAL,
                                      gz + 9.0 * LOCAL),
                              0.0, 0.8, collides=True, 
                              kind="landmark"))

    # -- the rose gallery --------------------------------------------------
    build.add_mesh("Mirrorhold_RoseWindow", L.rose_window(3.2 * LOCAL, 14))
    build.add_mesh("Mirrorhold_Gallery", L.citadel_block(
        seed=seed + 19, width=18.0 * LOCAL, depth=10.0 * LOCAL, height=9.0,
        domes=1))
    rx, rz = ANCHORS["rose_gallery"]
    build.place(Placement("Landmark_Gallery", "Mirrorhold_Gallery",
                          (rx, LEVEL["citadel_court"], rz), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="rose-gallery"))
    build.place(Placement("Landmark_RoseWindow", "Mirrorhold_RoseWindow",
                          (rx, LEVEL["citadel_court"] + 6.0,
                           rz + 5.9 * LOCAL), 0.0, 1.0,
                          collides=False, kind="landmark"))
    _add_landmark(build, "rose-gallery", "The Rose Gallery", "Landmark_Gallery",
                  "structure", (rx, LEVEL["citadel_court"] + 9.2, rz))

    # -- the lens towers ---------------------------------------------------
    build.add_mesh("Mirrorhold_LensTower", L.lens_tower(17.0, 2.2 * LOCAL,
                                                        seed=seed + 23))
    for name in ("lens_tower_west", "lens_tower_east"):
        tx, tz = ANCHORS[name]
        build.place(Placement(f"Landmark_{name}", "Mirrorhold_LensTower",
                              (tx, LEVEL["citadel_court"] + 6.0, tz), 0.0, 1.0,
                              collides=True, kind="landmark",
                              landmark=name.replace("_", "-")))
        _add_landmark(build, name.replace("_", "-"),
                      "Lens Tower", f"Landmark_{name}", "structure",
                      (tx, LEVEL["citadel_court"] + 6.0, tz))
        t.mark_blocked_disc((tx, tz), 8.0 * LOCAL)


# ---------------------------------------------------------- the civic descent
def populate_city(build: RegionBuild, seed: int = 20260828) -> None:
    """Plaza, canals, aqueduct, overlook and the stepped cliff town."""
    t = build.terrain
    rng = N.Rng(seed + 211)

    # -- the fountain plaza ------------------------------------------------
    build.add_mesh("Mirrorhold_Fountain", STONE.fountain(4.2 * LOCAL, seed + 31))
    px, pz = ANCHORS["fountain_plaza"]
    build.place(Placement("Landmark_Fountain", "Mirrorhold_Fountain",
                          _ground(t, px, pz), 0.0, 1.0,
                          collides=True, kind="landmark", landmark="plaza"))
    _add_landmark(build, "plaza", "The Fountain Plaza", "Landmark_Fountain",
                  "feature", (px, LEVEL["fountain_plaza"], pz))
    build.add_mesh("Mirrorhold_Statue", STONE.statue(3.0, seed + 33, 1.1))
    build.add_mesh("Mirrorhold_Lamp", L.crystal_lamp(3.0))
    for index in range(8):
        angle = math.pi * 2.0 * index / 8
        lx = px + math.cos(angle) * 15.0 * LOCAL
        lz = pz + math.sin(angle) * 15.0 * LOCAL
        build.place(Placement(f"Prop_PlazaLamp_{index}", "Mirrorhold_Lamp",
                              _ground(t, lx, lz),
                              0.0, 1.0, collides=True, kind="prop"))
    for index in range(4):
        angle = math.pi * 0.5 * index + math.pi * 0.25
        sx = px + math.cos(angle) * 11.0 * LOCAL
        sz = pz + math.sin(angle) * 11.0 * LOCAL
        build.place(Placement(f"Landmark_PlazaStatue_{index}", "Mirrorhold_Statue",
                              _ground(t, sx, sz),
                              _face((sx, sz), (px, pz)), 1.0,
                              collides=True, kind="landmark"))
    t.mark_blocked_disc((px, pz), 20.0 * LOCAL)

    # -- the canal district ------------------------------------------------
    build.add_mesh("Mirrorhold_Channel", STONE.water_channel(14.0 * LOCAL, 1.6,
                                                             0.6, seed + 37))
    build.add_mesh("Mirrorhold_Waterfall", STONE.waterfall(6.0 * LOCAL, 9.0,
                                                           seed + 39))
    cx, cz = ANCHORS["canal_district"]
    for index in range(5):
        chx = cx + (index - 2) * 8.0 * LOCAL
        build.place(Placement(f"Landmark_Channel_{index}", "Mirrorhold_Channel",
                              _ground(t, chx, cz, sink=-0.2),
                              math.pi * 0.5, 1.0, collides=True, kind="landmark"))
    for index in range(3):
        wx = cx + (index - 1) * 12.0 * LOCAL
        wz = cz + 15.0 * LOCAL
        build.place(Placement(f"Landmark_Fall_{index}", "Mirrorhold_Waterfall",
                              _ground(t, wx, wz),
                              0.0, 1.0, collides=False, kind="landmark"))
    _add_landmark(build, "canal-district", "The Canal Terraces",
                  "Landmark_Channel_2", "district",
                  (cx, LEVEL["canal_district"], cz))

    # retaining walls holding the terraces up, which is what the concept shows
    build.add_mesh("Mirrorhold_Retaining", STONE.retaining_wall(22.0 * LOCAL, 6.0,
                                                                seed + 41))
    for index, (wx, wz, level, rot) in enumerate((
            (cx, cz + 17.0 * LOCAL, LEVEL["canal_district"], 0.0),
            (px, pz + 20.0 * LOCAL, LEVEL["fountain_plaza"], 0.0),
            (ANCHORS["east_stair"][0], ANCHORS["east_stair"][1] + 15.0 * LOCAL,
             LEVEL["mid_town"], 0.0),
            (ANCHORS["terrace_overlook"][0],
             ANCHORS["terrace_overlook"][1] + 13.0 * LOCAL,
             LEVEL["upper_terrace"] - 6.0, 0.0))):
        build.place(Placement(f"Landmark_Retaining_{index}", "Mirrorhold_Retaining",
                              _ground(t, wx, wz, sink=6.0), rot, 1.0,
                              collides=True, kind="landmark"))

    # -- the aqueduct ------------------------------------------------------
    build.add_mesh("Mirrorhold_Aqueduct", L.aqueduct_run(46.0 * LOCAL, 10.0,
                                                         8.0, seed + 43))
    ax, az = ANCHORS["aqueduct"]
    build.place(Placement("Landmark_Aqueduct", "Mirrorhold_Aqueduct",
                          _ground(t, ax, az, sink=1.0),
                          math.pi * 0.5, 1.0, collides=True, kind="landmark",
                          landmark="aqueduct"))
    _add_landmark(build, "aqueduct", "The Meltwater Aqueduct",
                  "Landmark_Aqueduct", "structure",
                  (ax, LEVEL["canal_district"] - 4.0, az))

    # -- the terrace overlook ---------------------------------------------
    ox, oz = ANCHORS["terrace_overlook"]
    build.add_mesh("Mirrorhold_Pavilion", L.pavilion(radius=4.4 * LOCAL,
                                                     height=4.6, columns=10,
                                                     seed=seed + 47))
    build.place(Placement("Landmark_Overlook", "Mirrorhold_Pavilion",
                          _ground(t, ox, oz), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="overlook"))
    _add_landmark(build, "overlook", "The North Overlook", "Landmark_Overlook",
                  "feature", (ox, LEVEL["upper_terrace"] - 6.0, oz))
    build.add_mesh("Mirrorhold_Balustrade", STONE.balustrade(18.0 * LOCAL, 1.05,
                                                             MARBLE_MAT))
    for index in range(3):
        bx = ox + (index - 1) * 18.0 * LOCAL
        build.place(Placement(f"Prop_OverlookRail_{index}", "Mirrorhold_Balustrade",
                              _ground(t, bx, oz - 11.0 * LOCAL), 0.0, 1.0,
                              collides=True, kind="prop"))

    # -- the stepped cliff town -------------------------------------------
    for variant in range(4):
        build.add_mesh(f"Mirrorhold_House_{variant}", L.cliff_house(
            seed=seed + 51 + variant,
            width=(4.4 + variant * 0.6) * LOCAL,
            depth=(5.0 + (variant % 2) * 0.8) * LOCAL,
            storeys=2 + variant % 3))
    tx, tz = ANCHORS["cliff_town"]
    count = 0
    for shelf in range(5):
        level = LEVEL["lower_town"] + shelf * 6.5
        sx = tx + shelf * 4.0 * LOCAL
        sz = tz - shelf * 7.0 * LOCAL
        for slot in range(5):
            hx = sx + (slot - 2) * 5.4 * LOCAL
            hz = sz + (0.6 if slot % 2 else -0.6) * LOCAL
            gx_, gy_, gz_ = _ground(t, hx, hz, sink=0.35)
            build.place(Placement(
                f"Building_CliffHouse_{count}",
                f"Mirrorhold_House_{(shelf + slot) % 4}",
                (gx_, gy_, gz_), float(rng.uniform(-0.10, 0.10)),
                float(rng.uniform(0.94, 1.06)), collides=True,
                kind="building"))
            count += 1
    _add_landmark(build, "cliff-town", "The Stair Town",
                  "Building_CliffHouse_0", "settlement",
                  (tx, LEVEL["lower_town"], tz))

    # Readable thresholds lead into the cellar map. The building's front is
    # two metres behind its trigger, leaving room for a group to gather.
    build.add_mesh("Mirrorhold_VaultEntry", RC.vault_entry())
    for name, (x, y, z) in REG.VAULT_ENTRIES.items():
        build.place(Placement("Building_VaultEntry_" + name, "Mirrorhold_VaultEntry",
                              (x, y, z), 0, 1, collides=True, kind="building"))
        t.mark_blocked_disc((x, z), 7)

    # -- the east stair ----------------------------------------------------
    ex, ez = ANCHORS["east_stair"]
    build.add_mesh("Mirrorhold_Stair", M.stairs(7.0 * LOCAL, 0.19, 0.34, 34,
                                                material=ASHLAR_MAT))
    build.place(Placement("Landmark_EastStair", "Mirrorhold_Stair",
                          _ground(t, ex, ez + 8.0 * LOCAL),
                          0.0, 1.0, collides=True, walk_surface=True,
                          kind="landmark", landmark="east-stair"))
    _add_landmark(build, "east-stair", "The East Stair", "Landmark_EastStair",
                  "structure", (ex, LEVEL["mid_town"], ez))


# ------------------------------------------------------------------ the lake
def populate_lake(build: RegionBuild, seed: int = 20260828) -> None:
    """The ring, its causeways, the harbour and the south watch."""
    t = build.terrain
    rng = N.Rng(seed + 311)

    # -- the ring ----------------------------------------------------------
    build.add_mesh("Mirrorhold_Ring", L.colonnade_ring(15.0 * LOCAL, 24, 5.8,
                                                       seed=seed + 61))
    rx, rz = ANCHORS["ring"]
    ring_level = LEVEL["quay"] - 1.0
    build.place(Placement("Landmark_Ring", "Mirrorhold_Ring",
                          (rx, ring_level, rz), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="ring"))
    _add_landmark(build, "ring", "The Drowned Crown", "Landmark_Ring",
                  "monument", (rx, ring_level, rz))
    t.mark_blocked_disc((rx, rz), 20.0 * LOCAL)

    # A continuous promenade meets both shores. Its deck stands 4 cm above
    # the ring's marble at the joins, so their overlapping lips cannot shimmer.
    for name, stations in REG.LAKE_LINKS.items():
        asset = "Mirrorhold_LakeLink_" + name
        points = np.asarray(stations, dtype=float)
        centre = (points.min(axis=0) + points.max(axis=0)) * 0.5
        centre[1] = 0
        build.add_mesh(asset, RING_LINKS.graded_ring_link(
            name, points, centre, ring_z=ANCHORS["ring"][1], width=6.5,
            foot=-12.0, stone=ASHLAR_MAT, paving=MARBLE_MAT,
            parapet=0.8))
        build.place(Placement("Landmark_LakeLink_" + name, asset, tuple(centre),
                              0, 1, collides=True, kind="landmark"))

    # -- the harbour -------------------------------------------------------
    hx, hz = ANCHORS["harbour"]
    build.add_mesh("Mirrorhold_Quay", L.quay(30.0 * LOCAL, 9.0, 3.4,
                                             seed=seed + 65))
    build.place(Placement("Landmark_Quay", "Mirrorhold_Quay",
                          (hx, LEVEL["quay"] - 3.4, hz), 0.0, 1.0,
                          collides=True, kind="landmark",
                          landmark="harbour"))
    _add_landmark(build, "harbour", "The North Quay", "Landmark_Quay",
                  "settlement", (hx, LEVEL["quay"], hz))

    build.add_mesh("Mirrorhold_Dock", PROPS.dock(14.0 * LOCAL, 3.4, 1.4))
    build.add_mesh("Mirrorhold_Boat", PROPS.rowing_boat(4.6, 1.5, seed + 67))
    for index in range(3):
        dx = hx + (index - 1) * 10.0 * LOCAL
        dz = hz + 8.0 * LOCAL
        build.place(Placement(f"Landmark_Dock_{index}", "Mirrorhold_Dock",
                              (dx, LAKE, dz), 0.0, 1.0,
                              collides=True, kind="landmark"))
        build.place(Placement(f"Prop_Boat_{index}", "Mirrorhold_Boat",
                              (dx + 5.0, LAKE + 0.1, dz + 6.0),
                              float(rng.uniform(-0.4, 0.4)), 1.0,
                              collides=True, kind="prop"))

    build.add_mesh("Mirrorhold_FishCrate", PROPS.crate(0.72, seed + 68))
    for index, x in enumerate((96.5, 215.5)):
        build.place(Placement(f"Prop_PierCrate_{index}", "Mirrorhold_FishCrate",
                              (x, 3.72, 57.7), 0.2, 1, collides=True, kind="prop"))
        build.place(Placement(f"Prop_PierSkiff_{index}", "Mirrorhold_Boat",
                              (x, LAKE + 0.1, 66), 0, 1, collides=True, kind="prop"))

    # -- the south watch ---------------------------------------------------
    sx, sz = ANCHORS["south_watch"]
    build.add_mesh("Mirrorhold_Watchtower", ARCH.watchtower(15.0, seed + 69,
                                                            2.1 * LOCAL))
    build.place(Placement("Landmark_SouthWatch", "Mirrorhold_Watchtower",
                          _ground(t, sx, sz), 0.0, 1.0,
                          collides=True, kind="landmark", landmark="south-watch"))
    _add_landmark(build, "south-watch", "The South Watch", "Landmark_SouthWatch",
                  "structure", (sx, LEVEL["shore_terrace"] + 3.0, sz))

    # -- the islets --------------------------------------------------------
    build.add_mesh("Mirrorhold_IsletRuin", STONE.ruin_fragment(seed + 71, 1.6))
    for name in ("east_islet", "west_islet"):
        ix, iz = ANCHORS[name]
        x, y, z = _ground(t, ix, iz, sink=0.2)
        build.place(Placement(f"Landmark_{name}", "Mirrorhold_IsletRuin",
                              (x, y, z), float(rng.uniform(0.0, 6.28)), 1.0,
                              collides=True, kind="landmark"))


# ---------------------------------------------------------------- outlands
# Design-space sites for the second ring of places. The aerial concept is built
# right across its middle band, not just at the citadel and the lake, so the
# space the enlargement opens is filled with more authored places rather than
# by spreading the same ones thinner.
SATELLITES = [
    # (id, label, design x, z, kind)
    ("west-bench", "The West Bench", -26.0, -40.0, "hamlet"),
    ("west-shrine", "The Wayside Shrine", -20.0, -2.0, "shrine"),
    ("gorge-head", "Gorge Head", -30.0, 12.0, "post"),
    ("lower-terrace", "The Lower Terrace", 6.0, 6.0, "hamlet"),
    ("mid-bench", "The Mid Bench", 14.0, -26.0, "hamlet"),
    ("cistern-yard", "The Cistern Yard", 34.0, -14.0, "yard"),
    ("lens-works", "The Lens Works", 66.0, -26.0, "yard"),
    ("east-bench", "The East Bench", 88.0, -8.0, "hamlet"),
    ("east-post", "The East Post", 108.0, -14.0, "post"),
    ("north-post", "The North Post", 34.0, -62.0, "post"),
    ("upper-shrine", "The Upper Shrine", 64.0, -58.0, "shrine"),
    ("quarry-shelf", "The Quarry Shelf", 96.0, -50.0, "yard"),
    ("lake-north", "North Shore Row", 30.0, -4.0, "hamlet"),
    ("lake-east", "East Shore Row", 92.0, 16.0, "hamlet"),
    ("south-shore", "South Shore Row", 24.0, 44.0, "hamlet"),
    ("west-shore", "West Shore Row", 4.0, 24.0, "hamlet"),
    ("far-south", "The Far Watch", 62.0, 52.0, "post"),
    ("far-west", "The West Watch", -34.0, -18.0, "post"),
]


def populate_outlands(build: RegionBuild, seed: int = 20260828) -> None:
    """The second ring of places: benches, shrines, yards and watch posts.

    Without these the middle band of the region is bare slope between the
    citadel and the lake, which the aerial concept is not.
    """
    t = build.terrain
    rng = N.Rng(seed + 611)

    for variant in range(4):
        if f"Mirrorhold_House_{variant}" not in build.meshes:
            build.add_mesh(f"Mirrorhold_House_{variant}", L.cliff_house(
                seed=seed + 51 + variant,
                width=(4.4 + variant * 0.6) * LOCAL,
                depth=(5.0 + (variant % 2) * 0.8) * LOCAL,
                storeys=2 + variant % 3))

    build.add_mesh("Mirrorhold_Shrine", L.pavilion(radius=2.6 * LOCAL, height=3.2,
                                                   columns=8, seed=seed + 91))
    build.add_mesh("Mirrorhold_Post", ARCH.watchtower(10.5, seed + 93, 1.7 * LOCAL))
    build.add_mesh("Mirrorhold_YardWall", STONE.retaining_wall(14.0 * LOCAL, 3.6,
                                                               seed + 95))
    build.add_mesh("Mirrorhold_Bollard", STONE.column(2.2, 0.28, 8, ASHLAR_MAT))

    for index, (site_id, label, dx, dz, kind) in enumerate(SATELLITES):
        x, z = dx * SCALE, dz * SCALE
        gx, gy, gz = _ground(t, x, z)
        if gy < REG.LAKE_LEVEL + 1.0:
            continue
        t.mark_blocked_disc((x, z), 11.0 * LOCAL)

        if kind == "hamlet":
            for slot in range(4):
                angle = math.pi * 2.0 * slot / 4 + float(rng.uniform(-0.3, 0.3))
                radius = float(rng.uniform(6.0, 11.0)) * LOCAL
                hx = x + math.cos(angle) * radius
                hz = z + math.sin(angle) * radius
                px, py, pz = _ground(t, hx, hz, sink=0.3)
                build.place(Placement(
                    f"Building_{site_id}_{slot}",
                    f"Mirrorhold_House_{(index + slot) % 4}",
                    (px, py, pz), _face((hx, hz), (x, z)),
                    float(rng.uniform(0.9, 1.1)), collides=True,
                    kind="building"))
        elif kind == "shrine":
            build.place(Placement(f"Landmark_{site_id}", "Mirrorhold_Shrine",
                                  (gx, gy, gz), 0.0, 1.0, collides=True,
                                  kind="landmark"))
        elif kind == "post":
            build.place(Placement(f"Landmark_{site_id}", "Mirrorhold_Post",
                                  (gx, gy, gz), 0.0, 1.0, collides=True,
                                  kind="landmark"))
        else:  # yard
            build.place(Placement(f"Landmark_{site_id}", "Mirrorhold_YardWall",
                                  (gx, gy - 3.6, gz),
                                  float(rng.uniform(0.0, 3.14)), 1.0,
                                  collides=True, kind="landmark"))
            for slot in range(3):
                bx = x + float(rng.uniform(-8.0, 8.0)) * LOCAL
                bz = z + float(rng.uniform(-8.0, 8.0)) * LOCAL
                build.place(Placement(f"Prop_{site_id}_bollard_{slot}",
                                      "Mirrorhold_Bollard",
                                      _ground(t, bx, bz), 0.0,
                                      float(rng.uniform(0.8, 1.2)),
                                      collides=True, kind="prop"))

        _add_landmark(build, site_id, label,
                      f"Building_{site_id}_0" if kind == "hamlet"
                      else f"Landmark_{site_id}",
                      "settlement" if kind == "hamlet" else "feature",
                      (gx, gy, gz))

    # Retaining walls along the switchbacks, which is how the concept holds its
    # roads onto the slope.
    build.add_mesh("Mirrorhold_RoadWall", STONE.retaining_wall(18.0 * LOCAL, 4.4,
                                                               seed + 97))
    wall = 0
    for name, points in REG.ROUTES.items():
        pts = np.asarray(points, dtype=np.float64)
        for index in range(pts.shape[0] - 1):
            a, b = pts[index], pts[index + 1]
            length = float(np.linalg.norm(b - a))
            if length < 30.0:
                continue
            for s in range(1, int(length / 46.0) + 1):
                p = a + (b - a) * (s * 46.0 / length)
                direction = (b - a) / max(length, 1e-6)
                # downhill side of the road
                for side in (-1.0, 1.0):
                    wx = p[0] - direction[1] * side * 7.5
                    wz = p[1] + direction[0] * side * 7.5
                    here = float(t.height_at(wx, wz))
                    road = float(t.height_at(p[0], p[1]))
                    if road - here < 2.6:
                        continue
                    yaw = math.atan2(direction[0], direction[1])
                    build.place(Placement(
                        f"Landmark_RoadWall_{wall}", "Mirrorhold_RoadWall",
                        (wx, here, wz), yaw, 1.0, collides=True,
                        kind="landmark"))
                    wall += 1
    build.notes.append(f"road retaining walls: {wall}")

    # Waterfalls off the terrace edges, which the concept has everywhere.
    build.add_mesh("Mirrorhold_CliffFall", STONE.waterfall(5.0 * LOCAL, 14.0,
                                                           seed + 99))
    falls = 0
    for site in ((10.0, -34.0), (-14.0, -24.0), (40.0, -18.0), (72.0, -34.0),
                 (86.0, -18.0), (58.0, -6.0), (20.0, -8.0), (100.0, -38.0)):
        fx, fz = site[0] * SCALE, site[1] * SCALE
        x_, y_, z_ = _ground(t, fx, fz)
        if y_ < REG.LAKE_LEVEL + 6.0:
            continue
        build.place(Placement(f"Landmark_CliffFall_{falls}", "Mirrorhold_CliffFall",
                              (x_, y_, z_), float(rng.uniform(0.0, 6.28)), 1.0,
                              collides=False, kind="landmark"))
        falls += 1
    build.notes.append(f"cliff waterfalls: {falls}")


# ------------------------------------------------------------- vegetation
def populate_vegetation(build: RegionBuild, seed: int = 20260828,
                        lod: str | None = None) -> None:
    """Conifer stands on the turf benches, thinning with altitude.

    Mirrorhold is a stone region: the trees are a sparse alpine spruce belt
    between the lake shore and the snow line, not a forest.
    """
    t = build.terrain
    tiers = ("low",) if lod == "far" else ("high", "mid", "low")
    for tier in tiers:
        for variant in range(2):
            wood, leaves = TREES.build_tree("dark_pine",
                                            seed=seed + 400 + variant * 17,
                                            detail=tier)
            build.add_mesh(f"Tree_Spruce_{tier}_{variant}_Wood", wood)
            if leaves.triangle_count:
                build.add_mesh(f"Tree_Spruce_{tier}_{variant}_Canopy", leaves)

    # Turf carries the stands, and spruce also take hold on the gentler scree,
    # which is what the concept shows: dark conifer across the whole middle
    # band, not a lawn with a tree line drawn on it.
    gy, gx = np.gradient(t.height, REG.TERRAIN_CELL)
    slope = np.hypot(gx, gy)
    density = (t.surface == TER.TURF).astype(np.float64)
    density += (t.surface == TER.ROCK) * np.clip(1.0 - slope / 0.55, 0.0, 1.0) * 0.85
    density = np.clip(density, 0.0, 1.0)
    density *= np.clip((TREE_LINE - t.height) / 26.0, 0.0, 1.0)
    density *= np.clip((t.height - REG.LAKE_LEVEL - 2.0) / 6.0, 0.0, 1.0)
    density[t.tree_block] = 0.0
    grain = REG.region_noise(t, seed + 401, frequency=0.010)
    density *= np.clip(grain * 2.1 - 0.42, 0.0, 1.0)

    density *= getattr(t, "mirror_groves", np.ones_like(density))
    points = scatter_points(t, density, spacing=7.2, seed=seed + 403)
    rng = N.Rng(seed + 405)
    count = 0
    for x, z in points:
        y = float(t.height_at(x, z))
        if y < REG.LAKE_LEVEL + 2.0 or y > TREE_LINE:
            continue
        distance = math.hypot(x, z)
        tier = "low" if lod == "far" else (
            "high" if distance < 90.0 else "mid" if distance < 220.0 else "low")
        variant = count % 2
        yaw = float(rng.uniform(0.0, 6.28))
        scale = float(rng.uniform(0.78, 1.26))
        build.place(Placement(
            f"Tree_Spruce_{count}_Wood", f"Tree_Spruce_{tier}_{variant}_Wood",
            (x, y - 0.15, z), yaw, scale, collides=(tier == "high"),
            kind="tree"))
        canopy = f"Tree_Spruce_{tier}_{variant}_Canopy"
        if canopy in build.meshes:
            build.place(Placement(
                f"Tree_Spruce_{count}_Canopy", canopy, (x, y - 0.15, z),
                yaw, scale, collides=False, kind="foliage"))
        count += 1
    build.notes.append(f"spruce instances: {count}")


# ---------------------------------------------------------------- dressing
def populate_dressing(build: RegionBuild, seed: int = 20260828) -> None:
    """Lamps along the roads, harbour clutter, braziers on the high terraces."""
    t = build.terrain
    rng = N.Rng(seed + 511)

    build.add_mesh("Mirrorhold_RoadLamp", L.crystal_lamp(2.8))
    build.add_mesh("Mirrorhold_Brazier", PROPS.brazier(seed + 73))
    build.add_mesh("Mirrorhold_Crate", PROPS.crate(0.68, seed + 75, TIMBER_MAT))
    build.add_mesh("Mirrorhold_Barrel", PROPS.barrel(0.35, 0.88, seed + 77))
    build.add_mesh("Mirrorhold_Signpost", PROPS.signpost(seed + 79, 2))
    build.add_mesh("Mirrorhold_Boulder", PROPS.boulder(1.5, seed + 81, "cliff_rock"))

    # lamps down the great road
    lamp = 0
    for name, points in REG.ROUTES.items():
        pts = np.asarray(points, dtype=np.float64)
        step = 26.0 if name == "great_road" else 40.0
        for index in range(pts.shape[0] - 1):
            a, b = pts[index], pts[index + 1]
            length = float(np.linalg.norm(b - a))
            for s in range(1, max(1, int(length / step))):
                p = a + (b - a) * (s * step / length)
                side = 4.2 if s % 2 else -4.2
                direction = (b - a) / max(length, 1e-6)
                lx = p[0] - direction[1] * side
                lz = p[1] + direction[0] * side
                x, y, z = _ground(t, lx, lz)
                build.place(Placement(f"Prop_RoadLamp_{lamp}",
                                      "Mirrorhold_RoadLamp", (x, y, z),
                                      0.0, 1.0, collides=True, kind="prop"))
                lamp += 1

    # harbour clutter
    hx, hz = ANCHORS["harbour"]
    for index in range(14):
        cx = hx + float(rng.uniform(-12.0, 12.0)) * LOCAL
        cz = hz + float(rng.uniform(-3.0, 3.0)) * LOCAL
        mesh = "Mirrorhold_Crate" if index % 2 else "Mirrorhold_Barrel"
        build.place(Placement(f"Prop_HarbourGoods_{index}", mesh,
                              _ground(t, cx, cz),
                              float(rng.uniform(0.0, 6.28)), 1.0,
                              collides=True, kind="prop"))

    # braziers on the high terraces, which the concept lights at dusk
    for index, name in enumerate(("citadel_gate", "fountain_plaza", "orrery",
                                  "terrace_overlook", "canal_district")):
        bx, bz = ANCHORS[name]
        level = {"citadel_gate": LEVEL["citadel_gate"],
                 "fountain_plaza": LEVEL["fountain_plaza"],
                 "orrery": LEVEL["orrery"],
                 "terrace_overlook": LEVEL["upper_terrace"] - 6.0,
                 "canal_district": LEVEL["canal_district"]}[name]
        for side in (-1.0, 1.0):
            build.place(Placement(
                f"Prop_Brazier_{index}_{int(side)}", "Mirrorhold_Brazier",
                _ground(t, bx + side * 8.0 * LOCAL, bz + 6.0 * LOCAL),
                0.0, 1.0, collides=True, kind="prop"))

    # signposts where the roads meet
    for index, name in enumerate(("spawn_road", "harbour", "east_stair")):
        sx, sz = ANCHORS[name]
        x, y, z = _ground(t, sx, sz)
        build.place(Placement(f"Prop_Signpost_{index}", "Mirrorhold_Signpost",
                              (x, y, z), float(rng.uniform(0.0, 6.28)), 1.0,
                              collides=True, kind="prop"))

    # boulders on the scree, so bare rock is not perfectly smooth
    density = (t.surface == TER.ROCK).astype(np.float64)
    density[t.tree_block] = 0.0
    grain = REG.region_noise(t, seed + 513, frequency=0.02)
    density *= np.clip(grain * 2.0 - 0.9, 0.0, 1.0)
    points = scatter_points(t, density, spacing=17.0, seed=seed + 515)
    for index, (x, z) in enumerate(points):
        y = float(t.height_at(x, z))
        build.place(Placement(f"Prop_Boulder_{index}", "Mirrorhold_Boulder",
                              (x, y - 0.35, z), float(rng.uniform(0.0, 6.28)),
                              float(rng.uniform(0.6, 1.7)),
                              collides=False, kind="rock"))


# ------------------------------------------------------------- interactives
def populate_interactives(build: RegionBuild, seed: int = 20260828) -> None:
    """Editor-visible interaction points. The server owns behaviour."""
    plan = [
        ("orrery-console", "Orrery Console", "orrery", LEVEL["orrery"]),
        ("gate-ward", "Gate Ward", "citadel_gate", LEVEL["citadel_gate"]),
        ("plaza-well", "Plaza Cistern", "fountain_plaza", LEVEL["fountain_plaza"]),
        ("harbour-crane", "Harbour Crane", "harbour", LEVEL["quay"]),
        ("ring-dial", "Ring Dial", "ring", LEVEL["quay"] - 1.0),
        ("canal-sluice", "Canal Sluice", "canal_district", LEVEL["canal_district"]),
        ("aqueduct-valve", "Aqueduct Valve", "aqueduct",
         LEVEL["canal_district"] - 4.0),
        ("town-forge", "Stair-town Forge", "cliff_town", LEVEL["lower_town"]),
    ]
    for entry_id, label, anchor, level in plan:
        x, z = ANCHORS[anchor]
        build.interactives.append({
            "id": entry_id, "label": label, "type": "interaction-point",
            "position": [round(float(x), 2), round(float(level) + 0.1, 2),
                         round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "authority": "server"})
