"""Placement passes: forest, settlement, landmarks, props, water.

Placement is authored rather than uniform: density is driven by zone maps taken
from the aerial composition, roads and courtyards clear themselves, species and
detail level vary with zone and with distance from where the player walks, and
every instance is grounded on the sampled terrain height.
"""
from __future__ import annotations

import math

import numpy as np

from . import architecture as ARCH
from . import mesh as M
from . import noise as N
from . import props as PROPS
from . import stonework as STONE
from . import terrain as TER
from . import treecraft as TREECRAFT
from . import trees as TREES
from .noise import Rng
from .region import (ANCHORS, LOCAL as REGION_LOCAL, PLAY_MAX_X, PLAY_MAX_Z,
                     PLAY_MIN_X, PLAY_MIN_Z, RAVINE, RAVINE_NORTH, ROUTES, SCALE,
                     SEA_LEVEL, STREAMS, Placement, RegionBuild, region_noise,
                     shoreline_x)

# Placement offsets below are written in the original 192 m design space and
# multiplied by S, so the enlarged region keeps the composition of the concept
# instead of scattering the same objects across four times the ground.
S = SCALE
# Clearings, courtyards and the ground a building occupies are sized by the
# building, not by the region, so they use the local scale.
L = REGION_LOCAL

# ---------------------------------------------------------------- zones
FOREST_CORE = "forest_core"
FOREST_EDGE = "forest_edge"
COAST = "coast"
UPLAND = "upland"
TRANSITION = "transition"
BARREN = "barren"
SETTLED = "settled"

SPECIES_BY_ZONE: dict[str, tuple[tuple[str, float], ...]] = {
    FOREST_CORE: (("amber_oak", 0.34), ("gold_oak", 0.24), ("rust_maple", 0.18),
                  ("pale_birch", 0.10), ("dark_holly", 0.07),
                  ("understory_hazel", 0.05), ("dead_snag", 0.02)),
    FOREST_EDGE: (("amber_oak", 0.24), ("rust_maple", 0.22), ("pale_birch", 0.20),
                  ("dark_holly", 0.14), ("understory_hazel", 0.12),
                  ("dead_snag", 0.05), ("gold_oak", 0.03)),
    COAST: (("pale_birch", 0.30), ("dark_pine", 0.26), ("dark_holly", 0.20),
            ("rust_maple", 0.12), ("understory_hazel", 0.08), ("dead_snag", 0.04)),
    UPLAND: (("dark_pine", 0.34), ("gold_oak", 0.24), ("amber_oak", 0.18),
             ("pale_birch", 0.12), ("dead_snag", 0.08), ("dark_holly", 0.04)),
    TRANSITION: (("dead_snag", 0.30), ("burnt_snag", 0.24), ("dark_pine", 0.18),
                 ("rust_maple", 0.14), ("understory_hazel", 0.08),
                 ("dark_holly", 0.06)),
    BARREN: (("burnt_snag", 0.72), ("dead_snag", 0.28)),
    SETTLED: (("amber_oak", 0.30), ("gold_oak", 0.22), ("rust_maple", 0.20),
              ("pale_birch", 0.16), ("understory_hazel", 0.12)),
}

FOLIAGE_BY_ZONE = {
    FOREST_CORE: ("foliage_amber", "foliage_gold", "foliage_rust"),
    FOREST_EDGE: ("foliage_amber", "foliage_rust", "foliage_gold"),
    COAST: ("foliage_rust", "foliage_green", "foliage_gold"),
    UPLAND: ("foliage_gold", "foliage_green", "foliage_amber"),
    TRANSITION: ("foliage_dead", "foliage_rust", "foliage_green"),
    BARREN: ("foliage_dead",),
    SETTLED: ("foliage_amber", "foliage_gold", "foliage_rust"),
}


def zone_at(x: float, z: float, t: TER.Terrain) -> str:
    height = float(t.height_at(x, z))
    shore = float(shoreline_x(np.array([z]))[0])
    if x > 116.0 * S:
        return BARREN
    if x > 96.0 * S:
        return TRANSITION
    if x < shore + 16.0 * S:
        return COAST
    if height > 46.0 or z < -104.0 * S:
        return UPLAND
    settled = min(math.hypot(x - ANCHORS[k][0], z - ANCHORS[k][1])
                  for k in ("settlement", "settlement_market", "settlement_north",
                            "harbour_village", "hill_hamlet", "timber_yard",
                            "cove_huts", "lake_lodge", "north_hamlet",
                            "east_hamlet", "orchard"))
    if settled < 26.0 * S:
        return SETTLED
    edge = min(math.hypot(x - ANCHORS[k][0], z - ANCHORS[k][1])
               for k in ("garden_terrace", "south_gate", "arch_forecourt",
                         "great_arch", "east_lodge", "charcoal_camp", "quarry",
                         "old_battle", "burnt_mill"))
    if edge < 22.0 * S:
        return FOREST_EDGE
    return FOREST_CORE


# ---------------------------------------------------------------- density
def _route_distance_map(t: TER.Terrain, routes) -> np.ndarray:
    best = np.full(t.height.shape, 1e9)
    for points in routes:
        d, _ = TER._polyline_distance(t.gx, t.gz, np.asarray(points))
        best = np.minimum(best, d)
    return best


def build_density(t: TER.Terrain, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (tree density in [0,1], distance-to-road map)."""
    if hasattr(t, "density_provider"):
        return t.density_provider(t, seed)
    road_distance = _route_distance_map(t, list(ROUTES.values()))
    stream_distance = _route_distance_map(
        t, list(STREAMS.values()) + [RAVINE, RAVINE_NORTH])

    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)

    density = np.ones_like(t.height)
    density *= np.clip((road_distance - 3.4 * S) / (3.6 * S), 0.0, 1.0)  # roads stay open
    density *= np.clip((stream_distance - 2.0 * S) / (2.8 * S), 0.0, 1.0)  # banks stay open
    density *= np.clip(1.0 - (slope - 1.05) / 0.8, 0.0, 1.0)           # no trees on cliffs
    density *= (t.height > SEA_LEVEL + 1.2)                            # not in the sea
    density *= ~t.tree_block                                           # authored clearings
    density *= ~np.isin(t.surface, [TER.PAVING])
    # the concept's density falls away toward the burnt east
    density *= np.clip(1.0 - (t.gx - 106.0 * S) / (24.0 * S), 0.12, 1.0)
    # natural clumping and glades
    clump = region_noise(t, seed + 5, 0.030 / S)
    density *= np.clip(1.00 + 0.90 * clump, 0.0, 1.80)
    glade = region_noise(t, seed + 9, 0.075 / S)
    # a higher floor here is what turns scattered stands into continuous
    # forest: fewer places where the density field collapses to nothing
    density *= np.clip((glade + 0.20) * 4.0, 0.0, 1.0)
    return np.clip(density, 0.0, 1.0), road_distance


def scatter_points(t: TER.Terrain, density: np.ndarray, spacing: float, seed: int,
                   jitter: float = 0.62) -> np.ndarray:
    """Jittered-grid scatter weighted by a density field."""
    rng = Rng(seed)
    xs = np.arange(t.x0 + spacing * 0.5, t.x0 + t.size_x, spacing)
    zs = np.arange(t.z0 + spacing * 0.5, t.z0 + t.size_z, spacing)
    gx, gz = np.meshgrid(xs, zs)
    gx = gx.reshape(-1) + rng.uniform(-spacing * jitter, spacing * jitter, gx.size)
    gz = gz.reshape(-1) + rng.uniform(-spacing * jitter, spacing * jitter, gz.size)
    inside = ((gx > t.x0 + 2.0) & (gx < t.x0 + t.size_x - 2.0)
              & (gz > t.z0 + 2.0) & (gz < t.z0 + t.size_z - 2.0))
    gx, gz = gx[inside], gz[inside]
    cx = np.clip(((gx - t.x0) / t.cell).astype(int), 0, t.cols - 1)
    cz = np.clip(((gz - t.z0) / t.cell).astype(int), 0, t.rows - 1)
    weight = density[cz, cx]
    keep = rng.uniform(0.0, 1.0, gx.size) < weight
    return np.stack([gx[keep], gz[keep]], axis=-1)


def _pick(rng: Rng, table) -> str:
    values = [name for name, _ in table]
    weights = np.array([w for _, w in table], dtype=np.float64)
    weights = weights / weights.sum()
    return str(rng.choice(values, p=weights))


# ---------------------------------------------------------------- forest
TREE_VARIANTS = 3

# The canopy palette is a property of the variant, not of the instance, so a
# recoloured canopy costs nothing extra in the runtime package: one mesh, one
# material, many nodes.
VARIANT_PALETTE = ("foliage_amber", "foliage_gold", "foliage_rust")

ZONE_VARIANT_WEIGHTS = {
    FOREST_CORE: (0.40, 0.34, 0.26),
    FOREST_EDGE: (0.32, 0.28, 0.40),
    COAST: (0.22, 0.26, 0.52),
    UPLAND: (0.26, 0.44, 0.30),
    TRANSITION: (0.14, 0.20, 0.66),
    BARREN: (0.10, 0.10, 0.80),
    SETTLED: (0.38, 0.34, 0.28),
}


def tree_mesh_key(species: str, variant: int, detail: str, part: str) -> str:
    return f"Tree_{species}_v{variant}_{detail}_{part}"


# How high up each species carries its lowest leaves, as a fraction of the
# tree's own height. The lowest branches droop and their tips carry clusters,
# so without this the canopy settles to about 1.4 m on a mature oak - head
# height - and a stand reads as hedge rather than woodland. Understorey species
# keep their low foliage, because being low is what they are for.
CANOPY_FLOOR = {
    "amber_oak": 0.42,
    "gold_oak": 0.42,
    "rust_maple": 0.44,
    "pale_birch": 0.52,
    "great_oak": 0.34,
    "dark_holly": 0.0,
    "understory_hazel": 0.0,
    "sapling": 0.0,
    "dead_snag": 0.0,
    "burnt_snag": 0.0,
    "dark_pine": 0.0,
}


def ensure_tree_meshes(build: RegionBuild, species: str, variant: int,
                       detail: str) -> tuple[str, str | None]:
    """Build (and cache) the wood and canopy meshes for one tree variant."""
    wood_key = tree_mesh_key(species, variant, detail, "wood")
    canopy_key = tree_mesh_key(species, variant, detail, "canopy")
    if wood_key not in build.meshes:
        profile = TREES.PROFILES[species]
        previous = profile.foliage_material
        profile.foliage_material = VARIANT_PALETTE[variant % len(VARIANT_PALETTE)]
        seed = 1000 + variant * 97 + N.stable_hash(species) % 500
        wood, leaves = TREES.build_tree(
            species, seed=seed, detail=detail,
            canopy_floor=CANOPY_FLOOR.get(species, 0.0))
        profile.foliage_material = previous
        build.add_mesh(wood_key, wood)
        if leaves.triangle_count:
            build.add_mesh(canopy_key, leaves)
    return wood_key, (canopy_key if canopy_key in build.meshes else None)


def populate_forest(build: RegionBuild, seed: int = 20260827,
                    spacing: float = 6.2, lod: str | None = None) -> None:
    t = build.terrain
    density, road_distance = build_density(t, seed)
    points = scatter_points(t, density, spacing, seed + 3)
    rng = Rng(seed + 11)
    counter = 0
    for x, z in points:
        if not (PLAY_MIN_X - 12 < x < PLAY_MAX_X + 12
                and PLAY_MIN_Z - 12 < z < PLAY_MAX_Z + 12):
            continue
        zone = zone_at(float(x), float(z), t)
        species = _pick(rng, SPECIES_BY_ZONE[zone])
        weights = np.asarray(ZONE_VARIANT_WEIGHTS[zone], dtype=np.float64)
        variant = int(rng.choice(np.arange(TREE_VARIANTS), p=weights / weights.sum()))
        cx = int(np.clip((x - t.x0) / t.cell, 0, t.cols - 1))
        cz = int(np.clip((z - t.z0) / t.cell, 0, t.rows - 1))
        near_road = float(road_distance[cz, cx])
        if lod == "far":
            detail = "low"
        elif near_road < 6.0 * S:
            detail = "high" if (near_road < 3.5 * S and rng.chance(0.10)) else "mid"
        elif near_road < 12.0 * S:
            detail = "mid" if rng.chance(0.10) else "low"
        else:
            detail = "low"
        wood_key, canopy_key = ensure_tree_meshes(build, species, variant, detail)
        y = float(t.height_at(x, z)) - 0.18
        rotation = float(rng.uniform(0.0, math.pi * 2.0))
        scale = float(rng.uniform(0.82, 1.24))
        if hasattr(t, "density_provider"):
            # Young edge trees leave breathing room; mature crowns are in the
            # stands. The same scale applies to trunk and canopy.
            scale *= .72 if near_road < 13 else .9
        if zone in (TRANSITION, BARREN):
            scale *= 0.85
        counter += 1
        name = f"Tree_{counter:04d}_{species}"
        build.place(Placement(name + "_Wood", wood_key, (float(x), y, float(z)),
                              rotation, scale,
                              collides=(scale > 1.02 and detail != "low"), kind="tree"))
        if canopy_key:
            build.place(Placement(name + "_Canopy", canopy_key, (float(x), y, float(z)),
                                  rotation, scale, kind="foliage"))
    build.notes.append(f"forest instances: {counter}")


def populate_undergrowth(build: RegionBuild, seed: int = 20260827) -> None:
    t = build.terrain
    density, road_distance = build_density(t, seed + 31)
    # undergrowth likes the same ground as trees but also fringes the roads
    fringe = np.clip((road_distance - 2.4 * S) / (3.0 * S), 0.0, 1.0) * \
        np.clip(1.0 - (road_distance - 3.0 * S) / (9.0 * S), 0.0, 1.0)
    field = np.clip(density * 0.8 + fringe * 0.9, 0.0, 1.0)
    if hasattr(t, "woodland_moisture"):
        field *= .25 + .7*t.woodland_moisture
        field *= 1-t.woodland_open
        field *= ~t.tree_block
    field *= (t.height > SEA_LEVEL + 0.8)
    field *= np.clip(1.0 - (t.gx - 92.0 * S) / (26.0 * S), 0.03, 1.0)
    points = scatter_points(t, field, 7.0, seed + 41)
    rng = Rng(seed + 43)
    for i in range(6):
        key = f"Undergrowth_{i}"
        if key not in build.meshes:
            build.add_mesh(key, PROPS.undergrowth_patch(
                radius=float(0.7 + 0.25 * i), count=4 + (i % 3), seed=seed + 700 + i,
                height=float(0.6 + 0.12 * (i % 4))))
    count = 0
    for x, z in points:
        if not (PLAY_MIN_X - 8 < x < PLAY_MAX_X + 8
                and PLAY_MIN_Z - 8 < z < PLAY_MAX_Z + 8):
            continue
        count += 1
        key = f"Undergrowth_{int(rng.integers(0, 6))}"
        build.place(Placement(f"Undergrowth_{count:04d}", key,
                              (float(x), float(t.height_at(x, z)) - 0.06, float(z)),
                              float(rng.uniform(0, math.pi * 2)),
                              float(rng.uniform(0.8, 1.5)), kind="undergrowth"))
    build.notes.append(f"undergrowth instances: {count}")


def populate_ground_detail(build: RegionBuild, seed: int = 20260827) -> None:
    """Fallen logs, stumps, boulders, mushrooms and leaf drifts."""
    t = build.terrain
    density, road_distance = build_density(t, seed + 51)
    rng = Rng(seed + 53)

    for i in range(4):
        build.add_mesh(f"FallenLog_{i}", TREES.fallen_log(
            length=float(5.5 + i * 1.4), radius=float(0.42 + 0.08 * i), seed=seed + 60 + i))
        build.add_mesh(f"Stump_{i}", TREES.stump(radius=float(0.55 + 0.12 * i),
                                                 height=float(0.7 + 0.15 * i),
                                                 seed=seed + 70 + i))
        build.add_mesh(f"Boulder_{i}", PROPS.boulder(radius=float(0.8 + 0.45 * i),
                                                     seed=seed + 80 + i))
        build.add_mesh(f"RockCluster_{i}", PROPS.rock_cluster(
            radius=float(1.6 + 0.6 * i), count=4 + i, seed=seed + 90 + i))
        build.add_mesh(f"LeafDrift_{i}", PROPS.leaf_drift(radius=float(1.2 + 0.5 * i),
                                                          seed=seed + 100 + i))
        build.add_mesh(f"Mushrooms_{i}", PROPS.mushroom_cluster(
            seed=seed + 110 + i, count=4 + i,
            material="amber_resin" if i % 2 else "foliage_dead"))

    def scatter(field, spacing, keys, kind, scale_range=(0.85, 1.3), sink=0.05,
                collide=False, limit=None):
        points = scatter_points(t, field, spacing, seed + N.stable_hash(kind) % 500)
        placed = 0
        for x, z in points:
            if limit is not None and placed >= limit:
                break
            if not (PLAY_MIN_X - 6 < x < PLAY_MAX_X + 6
                    and PLAY_MIN_Z - 6 < z < PLAY_MAX_Z + 6):
                continue
            placed += 1
            key = str(rng.choice(list(keys)))
            build.place(Placement(f"{kind}_{placed:04d}", key,
                                  (float(x), float(t.height_at(x, z)) - sink, float(z)),
                                  float(rng.uniform(0, math.pi * 2)),
                                  float(rng.uniform(*scale_range)),
                                  collides=collide, kind=kind.lower()))
        build.notes.append(f"{kind} instances: {placed}")

    forest_field = np.clip(density * 1.1, 0.0, 1.0)
    scatter(forest_field * 0.26, 13.0, [f"FallenLog_{i}" for i in range(4)],
            "FallenLog", (0.85, 1.25), 0.22, collide=True)
    scatter(forest_field * 0.30, 12.0, [f"Stump_{i}" for i in range(4)],
            "Stump", (0.8, 1.3), 0.16)
    scatter(forest_field * 0.55, 10.0, [f"LeafDrift_{i}" for i in range(4)],
            "LeafDrift", (0.9, 1.6), 0.10)
    scatter(forest_field * 0.34, 12.0, [f"Mushrooms_{i}" for i in range(4)],
            "Mushrooms", (0.8, 1.4), 0.02)

    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope = np.hypot(gradient_x, gradient_z)
    rocky = np.clip((slope - 0.55) / 0.7, 0.0, 1.0) * (t.height > SEA_LEVEL - 1.0)
    rocky = np.maximum(rocky, np.clip((SEA_LEVEL + 2.2 - t.height) / 3.0, 0.0, 1.0)
                       * (t.height > SEA_LEVEL - 3.0))
    scatter(np.clip(rocky * 0.55, 0.0, 1.0), 10.0,
            [f"Boulder_{i}" for i in range(4)] + [f"RockCluster_{i}" for i in range(4)],
            "Rock", (0.8, 1.7), 0.30, collide=True)


# ---------------------------------------------------------------- water
def build_water(build: RegionBuild) -> None:
    t = build.terrain
    # the open sea runs out past the authored coast so the west edge of the
    # world is water to the horizon rather than a cut-off slab
    # the open sea runs west to the horizon; east of the coastal strip the
    # land closes the world, so the surface is clipped there
    sea = TER.water_plane(t, SEA_LEVEL, t.x0 - 320.0, t.z0 - 260.0,
                          t.x0 + 96.0, t.z0 + t.size_z + 260.0,
                          material="water_sea", cell=6.0, margin=0.15,
                          outside_is_water=True)
    build.water_meshes["Water_Sea"] = sea

    # streams and pools follow the carved channels
    stream_parts = []
    for name, points in STREAMS.items():
        pts = np.asarray(points)
        for i in range(pts.shape[0] - 1):
            a, b = pts[i], pts[i + 1]
            steps = max(2, int(np.linalg.norm(b - a) / 3.0))
            for s in range(steps):
                t0 = s / steps
                t1 = (s + 1) / steps
                p0 = a + (b - a) * t0
                p1 = a + (b - a) * t1
                y0 = float(t.height_at(p0[0], p0[1])) + 0.42
                y1 = float(t.height_at(p1[0], p1[1])) + 0.42
                direction = p1 - p0
                length = float(np.linalg.norm(direction))
                if length < 0.2:
                    continue
                width = 3.6 if name != "garden_rill" else 2.6
                quad = M.Mesh(
                    np.array([[-width * 0.5, y0, 0.0], [width * 0.5, y0, 0.0],
                              [width * 0.5, y1, length], [-width * 0.5, y1, length]]),
                    np.tile([0.0, 1.0, 0.0], (4, 1)),
                    np.array([[0.0, 0.0], [width * 0.16, 0.0],
                              [width * 0.16, length * 0.16], [0.0, length * 0.16]]),
                    None, np.array([0, 1, 2, 0, 2, 3], np.int64), "water_stream")
                yaw = math.atan2(direction[0], direction[1])
                quad.rotate_y(yaw)
                quad.translate(float(p0[0]), 0.0, float(p0[1]))
                stream_parts.append(quad)
    if stream_parts:
        build.water_meshes["Water_Streams"] = M.merge(stream_parts, "water_stream")

    pools = []
    for name, radius in (("mill_pool", 12.0), ("forest_lake", 18.0)):
        centre = ANCHORS[name]
        level = float(t.height_at(*centre)) + 0.30
        disc = M.lathe([[0.0, 0.0], [radius, 0.0]], 18, uv_scale=0.4,
                       material="water_pool")
        disc.uvs = np.stack([disc.positions[:, 0] * 0.12, disc.positions[:, 2] * 0.12],
                            axis=-1)
        pools.append(disc.translate(centre[0], level, centre[1]))
    build.water_meshes["Water_Pools"] = M.merge(pools, "water_pool")

    falls = []
    for i, (x, z, width, height) in enumerate((
            (-17.5 * S, -22.0 * S, 5.5 * S, 10.0),
            (-19.5 * S, -40.0 * S, 3.6 * S, 7.5),
            (-16.0 * S, -6.0 * S, 4.2 * S, 8.0),
            (40.5 * S, -66.0 * S, 3.4 * S, 8.5),
            (52.5 * S, -100.0 * S, 3.2 * S, 8.0),
            (-30.0 * S, -60.0 * S, 4.4 * S, 7.0),
            (52.0 * S, 12.0 * S, 3.0 * S, 5.0))):
        top = float(t.height_at(x, z))
        sheet = STONE.waterfall(width, height, seed=200 + i)
        sheet.translate(x, top + 0.35, z)
        falls.append(sheet)
    build.water_meshes["Water_Falls"] = M.merge(falls, "water_stream")


# ---------------------------------------------------------------- settlement
def _ground(t: TER.Terrain, x: float, z: float, sink: float = 0.0) -> tuple[float, float, float]:
    return float(x), float(t.height_at(x, z)) - sink, float(z)


def _face(from_xz, to_xz) -> float:
    """Yaw that turns a +Z-facing model toward a target point."""
    return math.atan2(to_xz[0] - from_xz[0], to_xz[1] - from_xz[1])


def _register_group(build: RegionBuild, key: str, item) -> str:
    """Store a MeshGroup (multi-material landmark) under one mesh key."""
    if key not in build.meshes:
        build.meshes[key] = item
    return key


def populate_settlement(build: RegionBuild, seed: int = 20260827) -> None:
    """Amberwood town: the moot hall, the amber hall, lodges, market and mill."""
    t = build.terrain
    rng = Rng(seed + 101)

    # -- civic core ------------------------------------------------------
    build.add_mesh("Manor_MootHall", ARCH.manor(seed=seed + 1, width=15.0, depth=11.0,
                                                storeys=3, preserve_materials=True))
    x, y, z = _ground(t, *ANCHORS["moot_hall"], sink=0.35)
    build.place(Placement("Landmark_MootHall", "Manor_MootHall", (x, y, z),
                          _face(ANCHORS["moot_hall"], ANCHORS["settlement_market"]),
                          1.0, collides=True, kind="building", landmark="moot-hall"))
    t.mark_blocked_disc(ANCHORS["moot_hall"], 17.0 * L)
    build.landmarks.append({"id": "moot-hall", "name": "The Moot Hall",
                            "node": "Landmark_MootHall", "type": "civic",
                            "position": [round(x, 2), round(y, 2), round(z, 2)]})

    build.add_mesh("Manor_AmberHall", ARCH.manor(seed=seed + 2, width=12.5, depth=9.5,
                                                 storeys=2, preserve_materials=True))
    x, y, z = _ground(t, *ANCHORS["amber_hall"], sink=0.3)
    build.place(Placement("Landmark_AmberHall", "Manor_AmberHall", (x, y, z),
                          _face(ANCHORS["amber_hall"], ANCHORS["settlement_market"]),
                          1.0, collides=True, kind="building", landmark="amber-hall"))
    t.mark_blocked_disc(ANCHORS["amber_hall"], 14.0 * L)
    build.landmarks.append({"id": "amber-hall", "name": "The Amber Hall",
                            "node": "Landmark_AmberHall", "type": "guild",
                            "position": [round(x, 2), round(y, 2), round(z, 2)]})

    # -- lodges around the settlement ------------------------------------
    for i in range(4):
        build.add_mesh(f"Lodge_{i}", ARCH.forest_lodge(
            seed=seed + 300 + i, width=float(6.2 + 0.5 * (i % 3)),
            depth=float(8.0 + 0.7 * (i % 4)), storeys=2 if i % 3 else 1,
            porch=True, balcony=(i % 2 == 0), workshop=(i % 3 == 0), preserve_materials=True))

    def near(anchor: str, dx: float = 0.0, dz: float = 0.0) -> tuple[float, float]:
        base = ANCHORS[anchor]
        return (base[0] + dx * L, base[1] + dz * L)

    lodge_sites = [
        near("settlement", -13.0, 4.0), near("settlement", 12.0, 7.0),
        near("settlement", -6.0, -13.0), near("settlement", 14.0, -10.0),
        near("settlement_market", -12.0, -6.0), near("settlement_market", 11.0, 6.0),
        near("settlement_north", -9.0, 5.0), near("settlement_north", 8.0, -6.0),
        near("harbour_village", 5.0, -5.0), near("harbour_village", -4.0, 6.0),
        near("hill_hamlet", -7.0, 4.0), near("hill_hamlet", 6.0, -5.0),
        near("timber_yard", -9.0, -5.0), near("east_lodge"),
        near("mill_pool", 8.0, -4.0), near("canopy_camp", 6.0, 4.0),
        # settlements added with the enlargement
        near("cove_huts", -5.0, 3.0), near("cove_huts", 5.0, -3.0),
        near("cove_huts", 0.0, 6.0),
        near("lake_lodge", 0.0, 0.0), near("lake_lodge", -6.0, 4.0),
        near("north_hamlet", -6.0, 4.0), near("north_hamlet", 6.0, -4.0),
        near("north_hamlet", 0.0, -7.0),
        near("east_hamlet", -6.0, 4.0), near("east_hamlet", 6.0, -4.0),
        near("east_hamlet", 0.0, 6.0),
        near("orchard", -7.0, 3.0), near("quarry", 6.0, 4.0),
        near("burnt_mill", 0.0, 0.0), near("amber_diggings", 5.0, 3.0),
    ]
    for index, site in enumerate(lodge_sites):
        key = f"Lodge_{index % 4}"
        x, y, z = _ground(t, site[0], site[1], sink=0.25)
        toward = ANCHORS["settlement_market"] if index < 8 else ANCHORS["timber_yard"]
        if index >= 16:
            toward = (site[0] + math.cos(index * 1.7) * 10.0,
                      site[1] + math.sin(index * 1.7) * 10.0)
        rotation = _face(site, toward) + float(rng.uniform(-0.35, 0.35))
        name = f"Building_Lodge_{index:02d}"
        build.place(Placement(name, key, (x, y, z), rotation, 1.0, collides=True,
                              kind="building"))
        t.mark_blocked_disc(site, 11.0 * L)
    build.landmarks.append({
        "id": "amberwood-town", "name": "Amberwood",
        "node": "Landmark_MootHall", "type": "settlement",
        "position": [float(ANCHORS["settlement"][0]),
                     round(float(t.height_at(*ANCHORS["settlement"])), 2),
                     float(ANCHORS["settlement"][1])]})

    # -- market and working props ----------------------------------------
    build.add_mesh("MarketStall_A", PROPS.market_stall(seed=seed + 11, goods="amber_resin"))
    build.add_mesh("MarketStall_B", PROPS.market_stall(seed=seed + 12, goods="foliage_rust"))
    build.add_mesh("Workbench", PROPS.workbench(seed=seed + 13))
    build.add_mesh("AmberWorkstation", PROPS.amber_workstation(seed=seed + 14))
    build.add_mesh("Cart", PROPS.cart(seed=seed + 15))
    build.add_mesh("Barrel", PROPS.barrel(seed=seed + 16))
    build.add_mesh("Crate", PROPS.crate(seed=seed + 17))
    build.add_mesh("BasketAmber", PROPS.basket(seed=seed + 18, contents="amber_resin"))
    build.add_mesh("Sack", PROPS.sack(seed=seed + 19))
    build.add_mesh("Firewood", PROPS.firewood(seed=seed + 20))
    build.add_mesh("LogPile", PROPS.log_pile(seed=seed + 21))
    build.add_mesh("Well", PROPS.well(seed=seed + 22))
    build.add_mesh("Brazier", PROPS.brazier(seed=seed + 23))
    build.add_mesh("Signpost", PROPS.signpost(seed=seed + 24))
    build.add_mesh("FenceSplit", PROPS.fence(4.0, seed=seed + 25, style="split"))
    build.add_mesh("FencePicket", PROPS.fence(3.2, seed=seed + 26, style="picket"))
    build.add_mesh("LampPost", STONE.lamp_post(2.6))
    build.add_mesh("HangingLantern", PROPS.hanging_lantern(seed=seed + 27))
    build.add_mesh("FishingGear", PROPS.fishing_gear(seed=seed + 28))
    build.add_mesh("RowingBoat", PROPS.rowing_boat(seed=seed + 29))
    build.add_mesh("AmberLump", PROPS.amber_lump(seed=seed + 30))
    build.add_mesh("Banner", PROPS.banner(seed=seed + 31))

    market = ANCHORS["settlement_market"]
    for i in range(10):
        angle = math.pi * 2.0 * i / 10 + 0.4
        radius = 6.6 * L
        px = market[0] + math.cos(angle) * radius
        pz = market[1] + math.sin(angle) * radius
        key = "MarketStall_A" if i % 2 else "MarketStall_B"
        x, y, z = _ground(t, px, pz, sink=0.08)
        build.place(Placement(f"Prop_MarketStall_{i}", key, (x, y, z),
                              _face((px, pz), market), 1.0, collides=True, kind="prop"))
    x, y, z = _ground(t, market[0], market[1] + 1.2, sink=0.05)
    build.place(Placement("Interact_Well_Market", "Well", (x, y, z), 0.0, 1.0,
                          collides=True, kind="interactive"))
    build.interactives.append({"id": "market-well", "node": "Interact_Well_Market",
                               "type": "well", "position": [round(x, 2), round(y, 2),
                                                            round(z, 2)]})

    # amber working, the region's craft identity
    amber_sites = [near("amber_hall", -7.5, 5.0), near("settlement_market", 8.0, -6.5),
                   near("canopy_camp", -5.0, -4.0), near("amber_diggings", -4.0, -3.0),
                   near("north_hamlet", 4.0, 5.0)]
    for i, site in enumerate(amber_sites):
        x, y, z = _ground(t, site[0], site[1], sink=0.05)
        node = f"Interact_AmberBench_{i}"
        build.place(Placement(node, "AmberWorkstation", (x, y, z),
                              float(rng.uniform(0, math.pi * 2)), 1.0, collides=True,
                              kind="interactive"))
        build.interactives.append({"id": f"amber-bench-{i}", "node": node,
                                   "type": "craft-station", "craft": "amber-working",
                                   "position": [round(x, 2), round(y, 2), round(z, 2)]})

    clutter = [
        ("Barrel", 52, 0.0), ("Crate", 44, 0.0), ("BasketAmber", 32, 0.0),
        ("Sack", 28, 0.0), ("Firewood", 24, 0.0), ("Cart", 15, 0.0),
        ("Workbench", 18, 0.0), ("LogPile", 16, 0.0), ("Brazier", 15, 0.0),
        ("FenceSplit", 26, 0.0), ("Signpost", 10, 0.0), ("Well", 6, 0.0),
    ]
    hubs = [ANCHORS[k] for k in ("settlement", "settlement_market", "settlement_north",
                                 "harbour_village", "timber_yard", "hill_hamlet",
                                 "canopy_camp", "east_lodge", "charcoal_camp",
                                 "amber_hall", "moot_hall", "mill_pool",
                                 "cove_huts", "lake_lodge", "north_hamlet",
                                 "east_hamlet", "orchard", "quarry", "burnt_mill",
                                 "amber_diggings", "old_battle")]
    index = 0
    for key, count, sink in clutter:
        for _ in range(count):
            hub = hubs[int(rng.integers(0, len(hubs)))]
            angle = float(rng.uniform(0, math.pi * 2))
            radius = float(rng.uniform(3.5, 13.0)) * L
            px = hub[0] + math.cos(angle) * radius
            pz = hub[1] + math.sin(angle) * radius
            if t.height_at(px, pz) < SEA_LEVEL + 0.6:
                continue
            index += 1
            x, y, z = _ground(t, px, pz, sink)
            build.place(Placement(f"Prop_{key}_{index:03d}", key, (x, y, z),
                                  float(rng.uniform(0, math.pi * 2)),
                                  float(rng.uniform(0.9, 1.15)),
                                  collides=(key in ("Cart", "LogPile", "Workbench")),
                                  kind="prop"))

    # street lighting along the settlement roads and the monument axis
    lamp_routes = ("settlement_road", "arrival_road", "monument_axis", "south_road",
                   "north_ridge_road", "east_hamlet_road", "orchard_road",
                   "cove_road", "lake_road")
    lamp_index = 0
    for route_name in lamp_routes:
        points = ROUTES[route_name]
        lengths = np.concatenate([[0.0], np.cumsum(
            np.linalg.norm(np.diff(points, axis=0), axis=1))])
        total = float(lengths[-1])
        step = 16.0 * S
        distance = step * 0.5
        while distance < total:
            index_segment = int(np.searchsorted(lengths, distance, side="right") - 1)
            index_segment = min(max(index_segment, 0), points.shape[0] - 2)
            span = max(lengths[index_segment + 1] - lengths[index_segment], 1e-6)
            local = (distance - lengths[index_segment]) / span
            p = points[index_segment] + (points[index_segment + 1]
                                         - points[index_segment]) * local
            direction = points[index_segment + 1] - points[index_segment]
            side = np.array([-direction[1], direction[0]])
            side = side / max(np.linalg.norm(side), 1e-6)
            offset = 3.4 * L * (1.0 if lamp_index % 2 else -1.0)
            px, pz = p[0] + side[0] * offset, p[1] + side[1] * offset
            if t.height_at(px, pz) > SEA_LEVEL + 0.8:
                lamp_index += 1
                x, y, z = _ground(t, px, pz, 0.05)
                build.place(Placement(f"Prop_LampPost_{lamp_index:03d}", "LampPost",
                                      (x, y, z), float(rng.uniform(0, math.pi * 2)),
                                      1.0, kind="prop"))
            distance += step
    build.notes.append(f"settlement props: {index}, lamps: {lamp_index}")


# ---------------------------------------------------------------- landmarks
def populate_landmarks(build: RegionBuild, seed: int = 20260827) -> None:
    """The checklist landmarks, each grounded and connected to the road network."""
    t = build.terrain
    rng = Rng(seed + 201)

    def add_landmark(landmark_id: str, name: str, node: str, kind: str,
                     position: tuple[float, float, float], extra: dict | None = None):
        entry = {"id": landmark_id, "name": name, "node": node, "type": kind,
                 "position": [round(position[0], 2), round(position[1], 2),
                              round(position[2], 2)]}
        if extra:
            entry.update(extra)
        build.landmarks.append(entry)

    # -- the monumental arch on the central axis --------------------------
    build.add_mesh("Monument_GreatArch", STONE.monumental_gate(
        seed=seed + 5, span=7.6, height=16.0, stair_width=14.0, stair_height=4.4, continuous_walk=True))
    x, y, z = _ground(t, *ANCHORS["great_arch"], sink=0.15)
    build.place(Placement("Landmark_GreatArch", "Monument_GreatArch", (x, y, z),
                          math.pi, 1.0, collides=True,
                          kind="landmark", landmark="great-arch"))
    add_landmark("great-arch", "The Amber Gate", "Landmark_GreatArch", "monument",
                 (x, y, z), {"approach": [58.0, round(float(t.height_at(58, -20)), 2), -20.0]})
    t.mark_blocked_disc(ANCHORS["great_arch"], 20.0 * L)
    t.mark_blocked_disc(ANCHORS["arch_forecourt"], 14.0 * L)

    # flanking colonnade fragments and steps, so the podium is not a bare slab
    build.add_mesh("Stone_Column", STONE.column(4.6, 0.52, 12))
    build.add_mesh("Stone_RuinFragment_A", STONE.ruin_fragment(seed + 31, 1.0))
    build.add_mesh("Stone_RuinFragment_B", STONE.ruin_fragment(seed + 32, 1.4))
    build.add_mesh("Stone_RuinFragment_C", STONE.ruin_fragment(seed + 33, 0.8))
    for i in range(8):
        side = -1.0 if i % 2 else 1.0
        px = ANCHORS["great_arch"][0] + side * 11.0 * L
        pz = ANCHORS["great_arch"][1] + (6.0 - (i // 2) * 5.0) * L
        x, y, z = _ground(t, px, pz, sink=0.1)
        build.place(Placement(f"Landmark_ArchColumn_{i}", "Stone_Column", (x, y + 4.4, z),
                              0.0, float(rng.uniform(0.92, 1.08)), collides=True,
                              kind="landmark"))

    # -- the high stone bridge over the ravine ----------------------------
    build.add_mesh("Bridge_High", STONE.high_bridge(length=26.0, deck_height=9.0,
                                                    width=5.0, arches=3, seed=seed + 7,
                                                    pier_foot=-3.0))
    site = ANCHORS["high_bridge"]
    deck_y = float(t.height_at(site[0] - 15.0 * S, site[1] + 9.0 * S))
    x, z = site
    ravine_direction = math.atan2(RAVINE[-1][0] - RAVINE[0][0],
                                  RAVINE[-1][1] - RAVINE[0][1])
    build.place(Placement("Landmark_HighBridge", "Bridge_High",
                          (x, deck_y - 8.4, z), ravine_direction + math.pi * 0.5, 1.0,
                          collides=True, kind="landmark", landmark="high-bridge"))
    add_landmark("high-bridge", "The Long Span", "Landmark_HighBridge", "bridge",
                 (x, deck_y, z))

    # -- the old town bridge over the beck --------------------------------
    build.add_mesh("Bridge_Old", STONE.high_bridge(length=14.0, deck_height=4.2,
                                                   width=4.2, arches=2, seed=seed + 8,
                                                   pier_foot=-1.6))
    site = ANCHORS["old_bridge"]
    deck_y = float(t.height_at(site[0] + 8.0 * S, site[1] - 2.0 * S))
    build.place(Placement("Landmark_OldBridge", "Bridge_Old",
                          (site[0], deck_y - 3.9, site[1]), 0.35, 1.0,
                          collides=True, kind="landmark", landmark="old-bridge"))
    add_landmark("old-bridge", "Millrace Bridge", "Landmark_OldBridge", "bridge",
                 (site[0], deck_y, site[1]))

    # -- root-overgrown forest arches -------------------------------------
    build.add_mesh("Stone_AncientArch_A", STONE.ancient_arch(5.0, 6.6, 1.7, seed + 11))
    build.add_mesh("Stone_AncientArch_B", STONE.ancient_arch(4.2, 5.6, 1.4, seed + 12))
    arch_sites = [((-16.0 * S, -34.0 * S), "west-forest-arch", "The Weeping Arch"),
                  ((38.0 * S, -92.0 * S), "north-forest-arch", "The Kneeling Arch"),
                  ((46.0 * S, -20.0 * S), "axis-arch", "The Broken Arch"),
                  ((-16.0 * S, -62.0 * S), "hollow-way-arch", "The Root Arch"),
                  ((-34.0 * S, -100.0 * S), "grove-arch", "The Sleeping Arch"),
                  ((84.0 * S, -74.0 * S), "ridge-arch", "The Watcher's Arch"),
                  ((104.0 * S, -34.0 * S), "ash-arch", "The Cinder Arch")]
    for i, (site, landmark_id, label) in enumerate(arch_sites):
        key = "Stone_AncientArch_A" if i % 2 == 0 else "Stone_AncientArch_B"
        x, y, z = _ground(t, site[0], site[1], sink=0.25)
        node = f"Landmark_AncientArch_{i}"
        build.place(Placement(node, key, (x, y, z),
                              float(rng.uniform(0, math.pi)), 1.0, collides=True,
                              kind="landmark", landmark=landmark_id))
        add_landmark(landmark_id, label, node, "ruin", (x, y, z))
        t.mark_blocked_disc(site, 10.0 * L)

    # -- the ancient forest gate on the road ------------------------------
    build.add_mesh("Gate_Forest", STONE.forest_gate(5.8, 6.4, seed + 13))
    for i, key in enumerate(("forest_gate_west", "forest_gate_east")):
        site = ANCHORS[key]
        x, y, z = _ground(t, site[0], site[1], sink=0.2)
        node = f"Landmark_ForestGate_{i}"
        toward = ANCHORS["settlement"] if i == 0 else ANCHORS["ash_flats"]
        build.place(Placement(node, "Gate_Forest", (x, y, z),
                              _face(site, toward) + math.pi * 0.5, 1.0, collides=True,
                              kind="landmark", landmark=f"forest-gate-{i}"))
        add_landmark(f"forest-gate-{i}",
                     "The West Forest Gate" if i == 0 else "The Ash Gate",
                     node, "gate", (x, y, z))

    # -- the colossal hollow tree -----------------------------------------
    build.add_mesh("Landmark_HollowTree", TREECRAFT.hollow_tree_hall(
        seed=seed + 17, outer_radius=5.0, height=26.0, opening_width=3.2,
        opening_height=5.4))
    site = ANCHORS["hollow_tree"]
    x, y, z = _ground(t, site[0], site[1], sink=0.2)
    build.place(Placement("Landmark_HollowTreeHall", "Landmark_HollowTree", (x, y, z),
                          _face(site, ANCHORS["settlement"]), 1.0, collides=True,
                          kind="landmark", landmark="hollow-tree"))
    add_landmark("hollow-tree", "The Hollow Warden", "Landmark_HollowTreeHall",
                 "tree-hall", (x, y, z))
    t.mark_blocked_disc(site, 13.0 * L)

    # -- the monumental canopy tree and its canopy works -------------------
    hero_wood, hero_leaves = TREES.build_tree(
        "great_oak", seed=seed + 19, detail="high",
        canopy_floor=CANOPY_FLOOR["great_oak"])
    hero_wood.scale(1.45)
    hero_leaves.scale(1.45)
    build.add_mesh("Tree_Great_Wood", hero_wood)
    build.add_mesh("Tree_Great_Canopy", hero_leaves)
    site = ANCHORS["great_tree"]
    x, y, z = _ground(t, site[0], site[1], sink=0.25)
    build.place(Placement("Landmark_GreatTree_Wood", "Tree_Great_Wood", (x, y, z),
                          0.4, 1.0, collides=True, kind="landmark",
                          landmark="great-tree"))
    build.place(Placement("Landmark_GreatTree_Canopy", "Tree_Great_Canopy", (x, y, z),
                          0.4, 1.0, kind="foliage"))
    add_landmark("great-tree", "The Amberwood Mother", "Landmark_GreatTree_Wood",
                 "monumental-tree", (x, y, z))
    t.mark_blocked_disc(site, 15.0 * L)

    # supporting old-growth giants so the hero is not alone
    for i, site in enumerate(((14.0 * S, -92.0 * S), (36.0 * S, -80.0 * S),
                              (4.0 * S, -86.0 * S), (30.0 * S, -100.0 * S),
                              (-2.0 * S, -72.0 * S), (-20.0 * S, -110.0 * S),
                              (-26.0 * S, -104.0 * S), (-14.0 * S, -116.0 * S))):
        site = getattr(t, "giant_site_overrides", {}).get(i, site)
        wood, leaves = TREES.build_tree("great_oak", seed=seed + 400 + i,
                                        canopy_floor=CANOPY_FLOOR["great_oak"],
                                        detail="high" if i < 2 else "mid")
        build.add_mesh(f"Tree_Giant_{i}_Wood", wood)
        build.add_mesh(f"Tree_Giant_{i}_Canopy", leaves)
        x, y, z = _ground(t, site[0], site[1], sink=0.2)
        scale = float(rng.uniform(0.92, 1.18))
        rotation = float(rng.uniform(0, math.pi * 2))
        build.place(Placement(f"Landmark_Giant_{i}_Wood", f"Tree_Giant_{i}_Wood",
                              (x, y, z), rotation, scale, collides=True, kind="tree"))
        build.place(Placement(f"Landmark_Giant_{i}_Canopy", f"Tree_Giant_{i}_Canopy",
                              (x, y, z), rotation, scale, kind="foliage"))
        t.mark_blocked_disc(site, 11.0 * L)

    # -- canopy platforms and the suspension walkway -----------------------
    platform_sites = [((22.0 * S, -70.0 * S), 11.5), ((26.0 * S, -88.0 * S), 15.5),
                      ((14.0 * S, -92.0 * S), 12.0), ((36.0 * S, -80.0 * S), 11.0),
                      ((-20.0 * S, -110.0 * S), 12.5), ((-26.0 * S, -104.0 * S), 11.0)]
    build.add_mesh("Canopy_Platform_A", TREECRAFT.canopy_platform(
        trunk_radius=0.95, deck_radius=4.4, y=0.0, seed=seed + 21, awning=True))
    build.add_mesh("Canopy_Platform_B", TREECRAFT.canopy_platform(
        trunk_radius=1.15, deck_radius=5.2, y=0.0, seed=seed + 22))
    build.add_mesh("Canopy_Dwelling", TREECRAFT.tree_dwelling(
        trunk_radius=1.0, y=0.0, seed=seed + 23))
    build.add_mesh("Canopy_SpiralStair", TREECRAFT.spiral_stair(2.0, 11.0, seed + 24))
    walkway_nodes = []
    for i, (site, height) in enumerate(platform_sites):
        ground_y = float(t.height_at(site[0], site[1]))
        deck_y = ground_y + height
        key = "Canopy_Platform_A" if i % 2 else "Canopy_Platform_B"
        node = f"Landmark_CanopyPlatform_{i}"
        build.place(Placement(node, key, (site[0], deck_y, site[1]),
                              float(rng.uniform(0, math.pi)), 1.0,
                              collides=True, kind="landmark"))
        walkway_nodes.append((site[0], deck_y, site[1]))
        build.place(Placement(f"Prop_SpiralStair_{i}", "Canopy_SpiralStair",
                              (site[0] + 1.6, ground_y, site[1] + 0.4),
                              float(rng.uniform(0, math.pi)), height / 11.0,
                              walk_surface=True, kind="prop"))
        if i == 0:
            build.place(Placement("Landmark_CanopyDwelling", "Canopy_Dwelling",
                                  (site[0], deck_y + 0.2, site[1]), 1.1, 1.0,
                                  collides=True, kind="landmark",
                                  landmark="canopy-camp"))
            add_landmark("canopy-camp", "The Resin Walk", node, "canopy-works",
                         (site[0], deck_y, site[1]))
    for i in range(len(walkway_nodes) - 1):
        a = walkway_nodes[i]
        b = walkway_nodes[i + 1]
        key = f"Walkway_{i}"
        build.add_mesh(key, TREECRAFT.suspension_walkway(
            (0.0, 0.0, 0.0),
            (b[0] - a[0], b[1] - a[1], b[2] - a[2]),
            sag=1.4, width=1.6, seed=seed + 500 + i))
        build.place(Placement(f"Landmark_CanopyWalkway_{i}", key, a, 0.0, 1.0,
                              kind="landmark"))

    # amber working up in the canopy, as in the close-up reference
    x, y, z = walkway_nodes[0]
    build.place(Placement("Interact_AmberBench_Canopy", "AmberWorkstation"
                          if "AmberWorkstation" in build.meshes else "Workbench",
                          (x + 2.2, y + 0.16, z - 1.4), 0.8, 1.0, kind="interactive"))
    build.interactives.append({"id": "amber-bench-canopy",
                               "node": "Interact_AmberBench_Canopy",
                               "type": "craft-station", "craft": "amber-working",
                               "position": [round(x + 2.2, 2), round(y + 0.16, 2),
                                            round(z - 1.4, 2)]})

    # -- the formal garden terrace ----------------------------------------
    build.add_mesh("Garden_Fountain", STONE.fountain(3.4, seed + 25))
    build.add_mesh("Garden_Statue", STONE.statue(3.0, seed + 26))
    build.add_mesh("Garden_Balustrade", STONE.balustrade(9.0, 1.05))
    build.add_mesh("Garden_Steps", ARCH.steps(6.0, 1.6, 0.38, 0.18))
    build.add_mesh("Garden_Channel", STONE.water_channel(16.0, 1.6, 0.6, seed + 27))
    site = ANCHORS["garden_terrace"]
    gy = float(t.height_at(*site))
    t.mark_blocked_disc(site, 16.0 * L)
    build.place(Placement("Landmark_GardenFountain", "Garden_Fountain",
                          (site[0], gy, site[1]), 0.0, 1.0, collides=True,
                          kind="landmark", landmark="garden-terrace"))
    add_landmark("garden-terrace", "The Sunken Garden", "Landmark_GardenFountain",
                 "garden", (site[0], gy, site[1]))
    for i in range(4):
        angle = math.pi * 0.5 * i + math.pi * 0.25
        px = site[0] + math.cos(angle) * 8.5 * L
        pz = site[1] + math.sin(angle) * 7.0 * L
        build.place(Placement(f"Landmark_GardenStatue_{i}", "Garden_Statue",
                              (px, gy, pz), _face((px, pz), site), 1.0,
                              collides=True, kind="landmark"))
    for sign in (-1.0, 1.0):
        build.place(Placement(f"Prop_GardenBalustrade_{int(sign)}", "Garden_Balustrade",
                              (site[0] + sign * 11.0 * L, gy, site[1]),
                              math.pi * 0.5, 1.0, collides=True, kind="prop"))
    build.place(Placement("Walk_GardenSteps", "Garden_Steps",
                          (site[0], gy - 1.6, site[1] + 10.2 * L), 0.0, 1.0,
                          walk_surface=True, kind="prop"))
    build.place(Placement("Prop_GardenChannel", "Garden_Channel",
                          (site[0] - 0.5, gy, site[1] - 6.0 * L), math.pi * 0.5, 1.0,
                          kind="prop"))
    build.add_mesh("Garden_Rotunda", STONE.rotunda(3.1, 4.2, 8, seed + 28))
    build.place(Placement("Landmark_GardenRotunda", "Garden_Rotunda",
                          (site[0] + 0.5, gy, site[1] - 9.5 * L), 0.2, 1.0,
                          collides=True, kind="landmark", landmark="garden-rotunda"))
    add_landmark("garden-rotunda", "The Amber Rotunda", "Landmark_GardenRotunda",
                 "pavilion", (site[0] + 0.5, gy, site[1] - 9.5))
    # a fall of water down the terrace face, as in the garden reference
    build.add_mesh("Garden_Fall", STONE.waterfall(3.4, 2.4, seed + 29))
    build.place(Placement("Water_GardenFall", "Garden_Fall",
                          (site[0] - 6.5 * L, gy + 0.2, site[1] + 10.0 * L), 0.0, 1.0,
                          kind="prop"))

    # -- harbour, dock and boats -------------------------------------------
    build.add_mesh("Dock_Main", PROPS.dock(14.0, 3.4, 1.4, seed + 29, posts=6))
    build.add_mesh("Dock_Small", PROPS.dock(8.0, 2.6, 1.2, seed + 30, posts=4))
    harbour = ANCHORS["harbour"]
    build.place(Placement("Landmark_Harbour_Dock", "Dock_Main",
                          (harbour[0], SEA_LEVEL, harbour[1]), 0.15, 1.0,
                          collides=True, kind="landmark", landmark="harbour"))
    add_landmark("harbour", "Resinlanding", "Landmark_Harbour_Dock", "harbour",
                 (harbour[0], SEA_LEVEL + 1.4, harbour[1]))
    build.place(Placement("Prop_Dock_Small", "Dock_Small",
                          (harbour[0] + 6.0 * L, SEA_LEVEL, harbour[1] + 11.0 * L),
                          math.pi * 0.5, 1.0, collides=True, kind="prop"))
    for i, offset in enumerate(((-4.5, 3.0), (-5.5, -3.5), (3.0, 11.0), (6.0, -9.0),
                                (-9.0, 8.0))):
        build.place(Placement(f"Prop_RowingBoat_{i}", "RowingBoat",
                              (harbour[0] + offset[0] * L, SEA_LEVEL - 0.18,
                               harbour[1] + offset[1] * L),
                              float(rng.uniform(0, math.pi * 2)), 1.0, kind="prop"))
    for i, offset in enumerate(((6.0, 6.0), (7.5, -4.0), (9.0, 2.0))):
        px, pz = harbour[0] + offset[0] * L, harbour[1] + offset[1] * L
        x, y, z = _ground(t, px, pz, 0.05)
        build.place(Placement(f"Prop_FishingGear_{i}", "FishingGear", (x, y, z),
                              float(rng.uniform(0, math.pi * 2)), 1.0, kind="prop"))

    # -- watchtowers and outposts ------------------------------------------
    build.add_mesh("Tower_Watch", ARCH.watchtower(14.0, seed + 31, 2.0))
    for i, key in enumerate(("east_watchtower", "north_watchtower", "south_gate",
                             "north_gate", "south_watch", "ash_tower",
                             "hill_shrine", "west_cove")):
        site = ANCHORS[key]
        x, y, z = _ground(t, site[0], site[1], sink=0.3)
        node = f"Landmark_Watchtower_{i}"
        t.mark_blocked_disc(site, 10.0 * L)
        build.place(Placement(node, "Tower_Watch", (x, y, z),
                              float(rng.uniform(0, math.pi * 2)), 1.0,
                              collides=True, kind="landmark", landmark=f"lookout-{i}"))
        add_landmark(f"lookout-{i}", ("The East Watch", "The North Watch",
                                      "South Gate Tower", "North Gate Tower",
                                      "The South Watch", "The Cinder Tower",
                                      "Shrine Hill Tower", "Cove Watch")[i],
                     node, "lookout", (x, y, z))
        t.mark_blocked_disc(site, 6.0)

    # -- the wayshrine on the arrival road ---------------------------------
    build.add_mesh("Shrine_Way", STONE.group(
        STONE.ruin_fragment(seed + 41, 1.2),
        STONE.column(2.4, 0.34, 10).translate(-1.4, 0.0, 0.0),
        STONE.column(2.4, 0.34, 10).translate(1.4, 0.0, 0.0),
        STONE.statue(2.0, seed + 42).translate(0.0, 0.35, -0.6),
        PROPS.brazier(seed + 43).translate(0.0, 0.0, 1.7)))
    site = ANCHORS["wayshrine"]
    x, y, z = _ground(t, site[0], site[1], sink=0.1)
    build.place(Placement("Landmark_Wayshrine", "Shrine_Way", (x, y, z),
                          _face(site, ANCHORS["great_arch"]), 1.0, collides=True,
                          kind="landmark", landmark="wayshrine"))
    add_landmark("wayshrine", "The Amber Wayshrine", "Landmark_Wayshrine", "shrine",
                 (x, y, z))

    # -- forestry and charcoal ---------------------------------------------
    build.add_mesh("LogPile_Large", PROPS.log_pile(4.6, rows=4, per_row=6, seed=seed + 45,
                                                   radius=0.26))
    yard = ANCHORS["timber_yard"]
    for i in range(6):
        angle = math.pi * 2.0 * i / 6 + 0.3
        px = yard[0] + math.cos(angle) * 6.5 * L
        pz = yard[1] + math.sin(angle) * 5.0 * L
        x, y, z = _ground(t, px, pz, 0.05)
        build.place(Placement(f"Prop_TimberStack_{i}", "LogPile_Large", (x, y, z),
                              float(rng.uniform(0, math.pi)), 1.0, collides=True,
                              kind="prop"))
    x, y, z = _ground(t, yard[0], yard[1], 0.0)
    add_landmark("timber-yard", "The Long Yard", "Prop_TimberStack_0", "industry",
                 (x, y, z))
    build.interactives.append({"id": "timber-yard", "node": "Prop_TimberStack_0",
                               "type": "harvest-station", "resource": "timber",
                               "position": [round(x, 2), round(y, 2), round(z, 2)]})

    camp = ANCHORS["charcoal_camp"]
    build.add_mesh("Kiln_Charcoal", STONE.group(
        M.lathe([[2.2, 0.0], [2.3, 0.5], [1.6, 1.7], [0.7, 2.4], [0.0, 2.55]], 14,
                uv_scale=0.9, material=ARCH.RUBBLE),
        M.cylinder(0.36, 0.30, 0.7, 7, uv_scale=1.2, material=ARCH.IRON)
        .translate(0.0, 2.4, 0.0)))
    for i in range(3):
        angle = math.pi * 2.0 * i / 3
        px = camp[0] + math.cos(angle) * 4.6 * L
        pz = camp[1] + math.sin(angle) * 4.0 * L
        x, y, z = _ground(t, px, pz, 0.1)
        build.place(Placement(f"Landmark_CharcoalKiln_{i}", "Kiln_Charcoal", (x, y, z),
                              0.0, float(rng.uniform(0.9, 1.15)), collides=True,
                              kind="landmark"))
    x, y, z = _ground(t, camp[0], camp[1], 0.0)
    add_landmark("charcoal-camp", "The Burner's Camp", "Landmark_CharcoalKiln_0",
                 "industry", (x, y, z))

    # -- retaining walls where the built ground meets the slope -------------
    build.add_mesh("Wall_Retaining", STONE.retaining_wall(11.0, 2.4, seed + 47))
    def offset(anchor, dx, dz):
        base = ANCHORS[anchor]
        return (base[0] + dx * L, base[1] + dz * L)

    wall_sites = [(offset("settlement_market", 0.0, 11.5), 0.0),
                  (offset("moot_hall", -10.0, 0.0), math.pi * 0.5),
                  (offset("garden_terrace", 0.0, -10.5), 0.0),
                  (offset("great_arch", -14.5, 0.0), math.pi * 0.5),
                  (offset("great_arch", 14.5, 0.0), math.pi * 0.5),
                  (offset("hill_hamlet", 0.0, 9.5), 0.0),
                  (offset("harbour_village", 0.0, 8.5), 0.0),
                  (offset("north_hamlet", 0.0, 8.0), 0.0),
                  (offset("east_hamlet", 0.0, 8.0), 0.0),
                  (offset("orchard", 0.0, 9.0), 0.0),
                  (offset("quarry", -9.0, 0.0), math.pi * 0.5),
                  (offset("cove_huts", 0.0, 7.0), 0.0),
                  (offset("lake_lodge", 0.0, 7.0), 0.0),
                  (offset("amber_diggings", 0.0, 7.0), 0.0)]
    for i, (site, rotation) in enumerate(wall_sites):
        x, y, z = _ground(t, site[0], site[1], sink=0.9)
        build.place(Placement(f"Prop_RetainingWall_{i}", "Wall_Retaining", (x, y, z),
                              rotation, 1.0, collides=True, kind="prop"))

    # -- fallen ruins scattered through the forest --------------------------
    ruin_field, _ = build_density(t, seed + 61)
    ruin_points = scatter_points(t, np.clip(ruin_field * 0.30, 0.0, 1.0), 18.0, seed + 63)
    count = 0
    for x, z in ruin_points:
        if not (PLAY_MIN_X < x < PLAY_MAX_X and PLAY_MIN_Z < z < PLAY_MAX_Z):
            continue
        count += 1
        key = ("Stone_RuinFragment_A", "Stone_RuinFragment_B",
               "Stone_RuinFragment_C")[count % 3]
        gx, gy, gz = _ground(t, float(x), float(z), 0.25)
        build.place(Placement(f"Prop_Ruin_{count:03d}", key, (gx, gy, gz),
                              float(rng.uniform(0, math.pi * 2)),
                              float(rng.uniform(0.8, 1.4)), collides=True, kind="prop"))
    build.notes.append(f"ruin fragments: {count}")

    # -- burnt east: dead stands, abandoned camps ---------------------------
    build.add_mesh("Prop_BurntStack", PROPS.log_pile(3.0, rows=2, per_row=4,
                                                     seed=seed + 71, radius=0.20))
    for i, site in enumerate(((116.0 * S, -60.0 * S), (104.0 * S, -30.0 * S),
                              (110.0 * S, 4.0 * S), (100.0 * S, -84.0 * S),
                              (122.0 * S, -44.0 * S), (115.0 * S, -40.0 * S),
                              (94.0 * S, 30.0 * S), (122.0 * S, 12.0 * S))):
        x, y, z = _ground(t, site[0], site[1], 0.05)
        build.place(Placement(f"Prop_BurntCamp_{i}", "Prop_BurntStack", (x, y, z),
                              float(rng.uniform(0, math.pi)), 1.0, collides=True,
                              kind="prop"))
        build.place(Placement(f"Prop_BurntBrazier_{i}", "Brazier",
                              _ground(t, x + 3.0 * L, z + 1.5 * L, 0.0),
                              0.0, 1.2, kind="prop"))
    add_landmark("ash-flats", "The Ashen Reach", "Prop_BurntCamp_1", "transition",
                 _ground(t, *ANCHORS["ash_flats"], 0.0))


# ---------------------------------------------------------------- outlands
def populate_outlands(build: RegionBuild, seed: int = 20260827) -> None:
    """Content for the places the enlargement opened up.

    A bigger region is only better if the new ground has reasons to walk across
    it. These are smaller than the central set on purpose - camps, works,
    landings, standing stones and ruins - so the settlement keeps its weight.
    """
    t = build.terrain
    rng = Rng(seed + 401)

    def ground(x, z, sink=0.0):
        return float(x), float(t.height_at(x, z)) - sink, float(z)

    def add(landmark_id, name, node, kind, position):
        build.landmarks.append({
            "id": landmark_id, "name": name, "node": node, "type": kind,
            "position": [round(position[0], 2), round(position[1], 2),
                         round(position[2], 2)]})

    def scatter_around(anchor, key, count, radius, kind="prop", sink=0.0,
                       collide=False, scale_range=(0.9, 1.2), prefix=None):
        centre = ANCHORS[anchor]
        placed = 0
        for i in range(count):
            angle = float(rng.uniform(0, math.pi * 2))
            r = float(rng.uniform(radius * 0.25, radius)) * L
            x = centre[0] + math.cos(angle) * r
            z = centre[1] + math.sin(angle) * r
            if t.height_at(x, z) < SEA_LEVEL + 0.4:
                continue
            placed += 1
            gx, gy, gz = ground(x, z, sink)
            build.place(Placement(
                f"{prefix or key}_{anchor}_{placed:02d}", key, (gx, gy, gz),
                float(rng.uniform(0, math.pi * 2)),
                float(rng.uniform(*scale_range)), collides=collide, kind=kind))
        return placed

    # natural dressing this pass needs before the ground-detail pass runs
    for i in range(4):
        build.add_mesh(f"Stump_{i}", TREES.stump(radius=float(0.55 + 0.12 * i),
                                                 height=float(0.7 + 0.15 * i),
                                                 seed=seed + 70 + i))
        build.add_mesh(f"Boulder_{i}", PROPS.boulder(radius=float(0.8 + 0.45 * i),
                                                     seed=seed + 80 + i))
        build.add_mesh(f"RockCluster_{i}", PROPS.rock_cluster(
            radius=float(1.6 + 0.6 * i), count=4 + i, seed=seed + 90 + i))

    # -- new authored pieces ----------------------------------------------
    build.add_mesh("Stone_Standing", STONE.group(
        M.box((1.1, 3.4, 0.8), center=(0.0, 1.7, 0.0), uv_scale=0.9,
              material=ARCH.RUBBLE)))
    build.meshes["Stone_Standing"].parts[0].jitter(0.045, seed=seed + 3)
    build.meshes["Stone_Standing"].parts[0].recompute_normals(56.0)

    build.add_mesh("Prop_Skep", STONE.group(
        M.lathe([[0.0, 0.52], [0.20, 0.46], [0.30, 0.30], [0.32, 0.10], [0.30, 0.0]],
                10, uv_scale=1.8, material=ARCH.THATCH),
        M.box((0.9, 0.10, 0.9), center=(0.0, 0.05, 0.0), uv_scale=1.4,
              material=ARCH.TIMBER_GREY)))

    build.add_mesh("Prop_Tent", STONE.group(
        M.gable_roof(2.6, 3.2, 1.7, 0.15, 0.05, uv_scale=1.6,
                     material="canvas_awning").translate(0.0, 0.35, 0.0),
        M.cylinder(0.06, 0.05, 2.1, 5, uv_scale=1.4, material=ARCH.TIMBER_DARK)
        .translate(0.0, 0.0, 1.5),
        M.cylinder(0.06, 0.05, 2.1, 5, uv_scale=1.4, material=ARCH.TIMBER_DARK)
        .translate(0.0, 0.0, -1.5)))

    quarry_face = []
    for i in range(7):
        quarry_face.append(M.box((3.4, 1.5, 2.2),
                                 center=(0.0, 0.75 + i * 1.5, -i * 1.1),
                                 uv_scale=0.8, material="cliff_rock"))
    for i in range(5):
        quarry_face.append(M.box((float(rng.uniform(0.8, 1.6)),
                                  float(rng.uniform(0.5, 0.9)),
                                  float(rng.uniform(0.7, 1.4))),
                                 center=(float(rng.uniform(-4.0, 4.0)), 0.35,
                                         float(rng.uniform(2.0, 6.0))),
                                 uv_scale=0.9, material="ashlar"))
    face = M.merge(quarry_face, "cliff_rock")
    face.jitter(0.05, seed=seed + 7)
    face.recompute_normals(58.0)
    build.add_mesh("Quarry_Face", face)

    build.add_mesh("Ruin_Chapel", STONE.group(
        STONE.ancient_arch(3.6, 5.2, 1.3, seed + 11, roots=False),
        STONE.retaining_wall(9.0, 2.6, seed + 12).translate(0.0, 0.0, -4.0),
        STONE.column(3.4, 0.36, 10).translate(-3.4, 0.0, -2.0),
        STONE.column(2.2, 0.36, 10).translate(3.4, 0.0, -2.0),
        STONE.ruin_fragment(seed + 13, 1.2).translate(2.0, 0.0, 2.4)))

    # -- the places ---------------------------------------------------------
    # standing stones on the coast road
    ring = ANCHORS["stone_ring"]
    for i in range(9):
        angle = math.pi * 2.0 * i / 9
        x = ring[0] + math.cos(angle) * 6.0 * L
        z = ring[1] + math.sin(angle) * 6.0 * L
        gx, gy, gz = ground(x, z, 0.4)
        build.place(Placement(f"Landmark_StandingStone_{i}", "Stone_Standing",
                              (gx, gy, gz), float(rng.uniform(0, math.pi)),
                              float(rng.uniform(0.85, 1.25)), collides=True,
                              kind="landmark"))
    add("stone-ring", "The Nine Watchers", "Landmark_StandingStone_0", "ruin",
        ground(*ring, 0.0))

    # a sea arch off the headland
    # standing in the shallows off the headland, footed on the seabed rather
    # than floating at the waterline
    sea = ANCHORS["sea_arch"]
    seabed = float(t.height_at(sea[0], sea[1]))
    build.place(Placement("Landmark_SeaArch", "Stone_AncientArch_A",
                          (sea[0], seabed, sea[1]), 0.7, 2.4,
                          collides=True, kind="landmark"))
    add("sea-arch", "The Drowned Arch", "Landmark_SeaArch", "sea-stack",
        (sea[0], seabed, sea[1]))
    scatter_around("sea_arch", "RockCluster_2", 7, 9.0, kind="rock", sink=0.4,
                   collide=True, scale_range=(1.2, 2.6))

    # kelp landing: a small dock and its gear
    # the landing runs out from the shore, so its piles reach the seabed
    landing = ANCHORS["kelp_landing"]
    dock_x = landing[0] - 3.0 * L
    build.place(Placement("Landmark_KelpLanding", "Dock_Small",
                          (dock_x, SEA_LEVEL, landing[1]),
                          0.0, 1.0, collides=True, kind="landmark"))
    add("kelp-landing", "Kelp Landing", "Landmark_KelpLanding", "landing",
        (dock_x, SEA_LEVEL + 1.2, landing[1]))
    scatter_around("kelp_landing", "FishingGear", 3, 5.0, collide=True)
    scatter_around("kelp_landing", "Barrel", 8, 6.0)
    build.place(Placement("Prop_KelpBoat", "RowingBoat",
                          (dock_x - 4.0 * L, SEA_LEVEL - 0.18, landing[1] + 2.0),
                          0.6, 1.0, kind="prop"))

    # orchard and bee garden
    orchard_rows = ANCHORS["south_orchard"]
    count = 0
    for row in range(5):
        for column in range(7):
            x = orchard_rows[0] + (column - 3) * 3.2 * L
            z = orchard_rows[1] + (row - 2) * 3.4 * L
            if t.height_at(x, z) < SEA_LEVEL + 1.0:
                continue
            count += 1
            wood_key, canopy_key = ensure_tree_meshes(build, "rust_maple",
                                                      count % TREE_VARIANTS, "mid")
            gx, gy, gz = ground(x, z, 0.18)
            rotation = float(rng.uniform(0, math.pi * 2))
            scale = float(rng.uniform(0.62, 0.78))
            build.place(Placement(f"Orchard_{count:02d}_Wood", wood_key,
                                  (gx, gy, gz), rotation, scale, kind="tree"))
            if canopy_key:
                build.place(Placement(f"Orchard_{count:02d}_Canopy", canopy_key,
                                      (gx, gy, gz), rotation, scale, kind="foliage"))
    add("south-orchard", "The Long Orchard", "Orchard_01_Wood", "agriculture",
        ground(*orchard_rows, 0.0))
    scatter_around("beekeeper", "Prop_Skep", 9, 5.0, collide=False)
    scatter_around("beekeeper", "FenceSplit", 5, 6.5)
    add("beekeeper", "The Skep Rows", "Prop_Skep_beekeeper_01", "agriculture",
        ground(*ANCHORS["beekeeper"], 0.0))

    # the long meadow: open ground with a well and stock fencing
    meadow = ANCHORS["long_meadow"]
    gx, gy, gz = ground(meadow[0], meadow[1], 0.05)
    build.place(Placement("Interact_Well_Meadow", "Well", (gx, gy, gz), 0.0, 1.0,
                          collides=True, kind="interactive"))
    build.interactives.append({"id": "meadow-well", "node": "Interact_Well_Meadow",
                               "type": "well",
                               "position": [round(gx, 2), round(gy, 2), round(gz, 2)]})
    add("long-meadow", "The Long Meadow", "Interact_Well_Meadow", "clearing",
        (gx, gy, gz))
    scatter_around("long_meadow", "FenceSplit", 14, 11.0)

    # the coppice: worked woodland
    scatter_around("coppice", "LogPile_Large", 7, 7.0, collide=True)
    scatter_around("coppice", "Stump_1", 12, 9.0, kind="stump", sink=0.15)
    scatter_around("coppice", "Cart", 2, 5.0, collide=True)
    add("coppice", "The Coppice", "LogPile_Large_coppice_01", "industry",
        ground(*ANCHORS["coppice"], 0.0))

    # ridge camp and boundary marker
    scatter_around("ridge_camp", "Prop_Tent", 5, 5.0, collide=True)
    scatter_around("ridge_camp", "Brazier", 3, 4.0)
    add("ridge-camp", "The Ridge Camp", "Prop_Tent_ridge_camp_01", "camp",
        ground(*ANCHORS["ridge_camp"], 0.0))
    boundary = ANCHORS["boundary_stone"]
    gx, gy, gz = ground(boundary[0], boundary[1], 0.35)
    build.place(Placement("Landmark_BoundaryStone", "Stone_Standing", (gx, gy, gz),
                          0.3, 1.35, collides=True, kind="landmark"))
    build.place(Placement("Prop_BoundarySign", "Signpost",
                          (gx + 2.0, gy + 0.35, gz + 1.4), 0.9, 1.0, kind="prop"))
    add("boundary-stone", "The Marchstone", "Landmark_BoundaryStone", "marker",
        (gx, gy, gz))

    # the ruined chapel and the cinder field
    chapel = ANCHORS["ash_chapel"]
    gx, gy, gz = ground(chapel[0], chapel[1], 0.2)
    build.place(Placement("Landmark_AshChapel", "Ruin_Chapel", (gx, gy, gz),
                          _face(chapel, ANCHORS["ash_flats"]), 1.0, collides=True,
                          kind="landmark"))
    add("ash-chapel", "The Cinder Chapel", "Landmark_AshChapel", "ruin", (gx, gy, gz))
    scatter_around("ash_chapel", "Stone_RuinFragment_B", 8, 8.0, collide=True,
                   sink=0.25)
    scatter_around("cinder_field", "Stone_RuinFragment_C", 14, 11.0, collide=True,
                   sink=0.25)
    scatter_around("cinder_field", "Prop_BurntStack", 6, 9.0, collide=True)
    add("cinder-field", "The Cinder Field", "Stone_RuinFragment_C_cinder_field_01",
        "battlefield", ground(*ANCHORS["cinder_field"], 0.0))
    scatter_around("smoke_vents", "Brazier", 9, 8.0, scale_range=(1.2, 2.0))
    scatter_around("smoke_vents", "Boulder_3", 8, 9.0, kind="rock", sink=0.4,
                   collide=True, scale_range=(1.0, 2.0))
    add("smoke-vents", "The Smoking Ground", "Brazier_smoke_vents_01", "transition",
        ground(*ANCHORS["smoke_vents"], 0.0))

    # the east quarry
    quarry = ANCHORS["east_quarry"]
    gx, gy, gz = ground(quarry[0], quarry[1], 0.4)
    build.place(Placement("Landmark_EastQuarry", "Quarry_Face", (gx, gy, gz),
                          _face(quarry, ANCHORS["far_watch"]), 1.6, collides=True,
                          kind="landmark"))
    add("east-quarry", "The Long Cut", "Landmark_EastQuarry", "industry",
        (gx, gy, gz))
    scatter_around("east_quarry", "Cart", 3, 8.0, collide=True)
    scatter_around("east_quarry", "Crate", 9, 9.0)
    build.interactives.append({
        "id": "east-quarry", "node": "Landmark_EastQuarry",
        "type": "harvest-station", "resource": "stone",
        "position": [round(gx, 2), round(gy, 2), round(gz, 2)]})

    # far lookouts and the western lodge
    for key, label in (("far_watch", "The Far Watch"), ("west_lodge", None)):
        site = ANCHORS[key]
        gx, gy, gz = ground(site[0], site[1], 0.3)
        if label:
            build.place(Placement(f"Landmark_Tower_{key}", "Tower_Watch",
                                  (gx, gy, gz), float(rng.uniform(0, math.pi * 2)),
                                  1.0, collides=True, kind="landmark"))
            add(key.replace("_", "-"), label, f"Landmark_Tower_{key}", "lookout",
                (gx, gy, gz))

    # deep groves of old growth, west and east
    giant_index = 0
    for anchor, spread in (("far_grove", 11.0), ("east_grove", 9.0),
                           ("deep_grove", 10.0)):
        centre = ANCHORS[anchor]
        for i in range(4):
            angle = math.pi * 2.0 * i / 4 + float(rng.uniform(-0.4, 0.4))
            x = centre[0] + math.cos(angle) * spread * L * float(rng.uniform(0.4, 1.0))
            z = centre[1] + math.sin(angle) * spread * L * float(rng.uniform(0.4, 1.0))
            wood_key, canopy_key = ensure_tree_meshes(build, "great_oak",
                                                      giant_index % TREE_VARIANTS,
                                                      "mid")
            giant_index += 1
            gx, gy, gz = ground(x, z, 0.25)
            rotation = float(rng.uniform(0, math.pi * 2))
            scale = float(rng.uniform(1.05, 1.35))
            build.place(Placement(f"Grove_{giant_index:02d}_Wood", wood_key,
                                  (gx, gy, gz), rotation, scale, collides=True,
                                  kind="tree"))
            if canopy_key:
                build.place(Placement(f"Grove_{giant_index:02d}_Canopy", canopy_key,
                                      (gx, gy, gz), rotation, scale, kind="foliage"))
            t.mark_blocked_disc((x, z), 6.0 * L)
        add(anchor.replace("_", "-"),
            {"far_grove": "The Far Grove", "east_grove": "The East Grove",
             "deep_grove": "The Deep Grove"}[anchor],
            f"Grove_{giant_index:02d}_Wood", "old-growth",
            ground(*centre, 0.0))

    # upper falls: a shrine beside the water
    falls = ANCHORS["upper_falls"]
    gx, gy, gz = ground(falls[0] + 4.0 * L, falls[1], 0.1)
    build.place(Placement("Landmark_UpperFallsShrine", "Shrine_Way", (gx, gy, gz),
                          _face((gx, gz), falls), 1.0, collides=True, kind="landmark"))
    add("upper-falls", "The Upper Falls", "Landmark_UpperFallsShrine", "shrine",
        (gx, gy, gz))
    build.notes.append(f"outland places: {len(build.landmarks)} landmarks total")
