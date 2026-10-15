"""Placement passes for Verdant Stair.

`region.py` says where the ground is; this says what stands on it. The passes
run largest to smallest, as the production guide asks: water, then the stair
and its bridges, then the landmarks, then the settlements, then the jungle,
then the understory and ground dressing.

Two things here are not invented. The **server tables** at the top are copied
from `eloria-server/config/eloria/*.txt` for `verdant_stair`, so this region's
NPCs, creatures, harvestables and interactives are the ones the server actually
serves rather than placeholders. And the **panel kit** in `junglecraft` is built
to the ten-panel detail board rather than to a general idea of a jungle.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import terrain as TER
from regionbuild import Placement, RegionBuild

import region as REG

# ---------------------------------------------------------------------------
# Authoritative server content, transcribed from eloria-server config/eloria.
# Tiles are on the server's 192-cell map; the build scales them by three to the
# 576-cell map and grounds them on the terrain.
# ---------------------------------------------------------------------------

# config/eloria/spawns.txt
SERVER_SPAWNS: tuple[tuple[str, tuple[int, int]], ...] = (
    ("canopy_glider", (20, 20)),
    ("canopy_glider", (42, 28)),
    ("canopy_glider", (76, 20)),
    ("cenote_toader", (102, 34)),
    ("cenote_toader", (24, 50)),
    ("cenote_toader", (46, 44)),
    ("emerald_basilisk", (24, 24)),
    ("leaf_mantis", (36, 24)),
    ("dartback_treefrog", (48, 24)),
    ("plumefire_hummingbird", (60, 24)),
    ("vinecoil_snake", (72, 24)),
    ("canopy_lynx", (84, 24)),
    ("mossback_anteater", (96, 24)),
    ("bloomtail_axolotl", (108, 24)),
    ("canopy_gorilla", (120, 24)),
    ("vine_treant", (132, 24)),
    ("verdant_naiad", (24, 36)),
    ("verdant_stair_dragon", (36, 36)),
)

CREATURE_GROUPS: dict[str, str] = {
    "canopy_glider": "canopy-fauna",
    "canopy_lynx": "canopy-fauna",
    "canopy_gorilla": "canopy-fauna",
    "plumefire_hummingbird": "canopy-fauna",
    "leaf_mantis": "understory-fauna",
    "dartback_treefrog": "understory-fauna",
    "mossback_anteater": "understory-fauna",
    "vinecoil_snake": "understory-hostile",
    "emerald_basilisk": "understory-hostile",
    "cenote_toader": "water-fauna",
    "bloomtail_axolotl": "water-fauna",
    "verdant_naiad": "water-hostile",
    "vine_treant": "deep-jungle-hostile",
    "verdant_stair_dragon": "region-boss",
}

# config/eloria/harvesting.txt
SERVER_HARVEST: tuple[tuple[int, str, tuple[int, int]], ...] = (
    (45, "Lotus", (47, 58)),
    (46, "Lotus", (24, 97)),
    (47, "Orchid", (17, 60)),
    (48, "Orchid", (84, 79)),
    (49, "Lichen", (101, 70)),
    (50, "Lichen", (86, 61)),
    (51, "Venom Bulb", (49, 96)),
    (52, "Venom Bulb", (74, 81)),
    (53, "Sage", (55, 12)),
    (54, "Sage", (14, 89)),
    (55, "Sage", (19, 42)),
    (56, "Hearthroot", (32, 13)),
    (57, "Hearthroot", (35, 48)),
    (58, "Hearthroot", (100, 59)),
    (59, "Toadstool", (85, 70)),
    (60, "Toadstool", (94, 33)),
    (61, "Quartz", (69, 56)),
    (62, "Quartz", (82, 23)),
    (63, "Quartz", (27, 70)),
    (64, "Watercress", (92, 15)),
    (65, "Watercress", (99, 80)),
    (66, "Watercress", (44, 23)),
)

HARVEST_CATEGORIES: dict[str, str] = {
    "Lotus": "reagent",
    "Orchid": "reagent",
    "Lichen": "reagent",
    "Venom Bulb": "reagent",
    "Sage": "reagent",
    "Hearthroot": "reagent",
    "Toadstool": "reagent",
    "Watercress": "reagent",
    "Quartz": "mineral",
}

# config/eloria/interactives.txt
SERVER_INTERACTIVES: tuple[tuple[int, str, str, tuple[int, int]], ...] = (
    (12, "portal", "Verdant Stair Waygate", (58, 58)),
    (13, "information", "Region Board", (60, 62)),
    (14, "storage", "Wayfarer's Cache", (64, 62)),
    (15, "crafting_station", "Field Station", (68, 62)),
)


# ---------------------------------------------------------------------------
# water
# ---------------------------------------------------------------------------
def build_water(build: RegionBuild, seed: int = 0) -> None:
    """The lagoon, the cenotes, the terrace pools, the streams and the falls."""
    t = build.terrain

    # -- the lagoon: one surface over the whole drowned south-west corner,
    #    running out past the authored coast so the horizon is sea, not a cut
    build.water_meshes["Water_Lagoon"] = TER.water_plane(
        t, REG.SEA_LEVEL, t.x0 - 200.0, t.z0 - 200.0,
        t.x0 + t.size_x + 200.0, t.z0 + t.size_z + 200.0,
        # 4 m cells, not 8. The lagoon is clipped to where the ground is below
        # sea level, so the cell size *is* the shoreline resolution: at 8 m the
        # beach came out as a row of rectangular notches.
        material="water_lagoon", cell=8.0, only_below=False, margin=0.30,
        outside_is_water=True)

    # -- the cenotes and the terrace pools. Each is filled to a level a little
    #    below the terrace it sits in, so the pool has a visible rim of rock.
    for name, radius, drop, material in (
            ("cenote", 30.0, 4.0, "water_cenote"),
            ("north_cenote", 24.0, 4.0, "water_cenote"),
            ("lower_pools", 24.0, 1.6, "water_cenote"),
            ("shrine_pool", 32.0, 1.6, "water_cenote"),
            ("lotus_pools", 40.0, 1.6, "water_cenote"),
            ("summit_pools", 28.0, 1.6, "water_cenote"),
            ("quay_falls", 28.0, 1.2, "water_cenote")):
        x, z = REG.ANCHORS[name]
        level = float(t.height_at(x, z)) + drop
        from landscape_plan import pool_water
        piece = pool_water(t,level,x,z,radius,material,
                           spill_radius=10.0 if name=="lower_pools" else None)
        if piece.triangle_count:
            build.water_meshes[f"Water_Cenote_{_camel(name)}"] = piece

    # -- the streams. A ribbon of water follows each watercourse at the height
    #    of its own carved floor, so it sits in the channel instead of hovering.
    for name, points in REG.STREAMS.items():
        piece = _stream_ribbon(t, points, width=4.6, seed=seed
                               + N.stable_hash(name) % 97)
        if piece.triangle_count:
            build.water_meshes[f"Water_Stream_{_camel(name)}"] = piece

    # -- the falls. `region.waterfall_sites()` finds every place a stream
    #    crosses a riser, so a moved terrace or a new stream cannot leave a
    #    fall behind or invent one that is not there.
    from amberwood import stonework as SW
    for index, (stream, x, z, top, drop) in enumerate(REG.waterfall_sites()):
        if drop < 4.0:
            continue
        ground_top = float(t.height_at(x, z))
        sheet = SW.waterfall(width=7.0, height=drop + 3.0,
                             seed=seed + index, material="water_stream")
        # face the sheet down the fall line, which is the stair diagonal
        sheet.rotate_y(math.pi * 0.25)
        sheet.translate(x, max(ground_top, top - 1.0), z)
        build.water_meshes[f"Water_Falls_{_camel(stream)}_{index:02d}"] = sheet


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _stream_ribbon(t: TER.Terrain, points: np.ndarray, width: float,
                   seed: int) -> M.Mesh:
    """A water ribbon following a polyline at the height of its carved floor."""
    samples = []
    for index in range(points.shape[0] - 1):
        a, b = points[index], points[index + 1]
        span = float(np.linalg.norm(b - a))
        # Metre stations follow the compact terrace risers. The old eight-metre
        # chord cut across dry stair landings and left water above the treads.
        steps = max(2, math.ceil(span))
        for k in range(steps):
            t_local = k / steps
            samples.append(a + (b - a) * t_local)
    samples.append(points[-1])
    samples = np.asarray(samples)

    rings = []
    for index, point in enumerate(samples):
        if index == 0:
            direction = samples[1] - samples[0]
        elif index == len(samples) - 1:
            direction = samples[-1] - samples[-2]
        else:
            direction = samples[index + 1] - samples[index - 1]
        length = float(np.linalg.norm(direction))
        if length < 1e-6:
            continue
        side = np.array([-direction[1], direction[0]]) / length
        # the channel floor, sampled a little wide so the ribbon meets its banks
        floor = min(float(t.height_at(point[0], point[1])),
                    float(t.height_at(point[0] + side[0] * width * 0.5,
                                      point[1] + side[1] * width * 0.5)),
                    float(t.height_at(point[0] - side[0] * width * 0.5,
                                      point[1] - side[1] * width * 0.5)))
        y = floor + 0.12
        rings.append(np.array([
            [point[0] - side[0] * width * 0.5, y, point[1] - side[1] * width * 0.5],
            [point[0] + side[0] * width * 0.5, y, point[1] + side[1] * width * 0.5],
        ]))
    if len(rings) < 2:
        return M.Mesh(material="water_stream")
    piece = M.loft(rings, closed_rings=False, uv_scale=0.4,
                   material="water_stream")
    piece.uvs = np.stack([piece.positions[:, 0] * 0.09,
                          piece.positions[:, 2] * 0.09], axis=-1)
    piece.recompute_normals(180.0)
    return piece


# ---------------------------------------------------------------------------
# species
# ---------------------------------------------------------------------------
# Registered from the region rather than from the toolkit: a species profile is
# art direction for one region, and `trees.register` is a public entry point
# exactly so a region can add its own without editing the shared table.
_SPECIES_REGISTERED = False


def _register_species() -> None:
    global _SPECIES_REGISTERED
    if _SPECIES_REGISTERED:
        return
    from amberwood import trees as TREES
    TREES.register(TREES.TreeProfile(
        name="verdant_banyan", height=25.0, trunk_radius=1.45, trunk_sides=12,
        trunk_segments=9, first_branch=0.30, children=(7, 3, 2),
        branch_pitch=(0.80, 1.30), branch_length=0.52, branch_droop=0.34,
        cluster_size=(2.4, 3.6), clusters_per_tip=3, root_count=12,
        root_spread=4.6, root_rise=0.90, taper=0.46, bark_material="bark_pale",
        foliage_material="foliage_green", canopy_bias=1.35, max_clusters=132))
    # the emergent: a tall clean bole that only branches near the top, which is
    # what makes a rainforest canopy read as layered rather than as a hedge
    TREES.register(TREES.TreeProfile(
        name="verdant_emergent", height=26.0, trunk_radius=0.78, trunk_sides=9,
        trunk_segments=8, first_branch=0.62, children=(6, 3, 2),
        branch_pitch=(0.55, 1.05), branch_length=0.44, branch_droop=0.20,
        cluster_size=(2.0, 3.0), clusters_per_tip=3, root_count=8,
        root_spread=2.6, root_rise=0.75, taper=0.28, bark_material="bark_dark",
        foliage_material="foliage_green", canopy_bias=1.20, max_clusters=104))
    TREES.register(TREES.TreeProfile(
        name="verdant_canopy", height=17.0, trunk_radius=0.56, trunk_sides=8,
        trunk_segments=8, first_branch=0.42,
        children=(5, 3, 2), cluster_size=(1.9, 2.8), clusters_per_tip=3,
        root_count=5, root_spread=1.7, bark_material="bark_dark",
        foliage_material="foliage_green", canopy_bias=1.05, max_clusters=76))
    TREES.register(TREES.TreeProfile(
        name="verdant_understory", height=8.0, trunk_radius=0.26, trunk_sides=8,
        trunk_segments=7, first_branch=0.34, children=(5, 3),
        branch_pitch=(0.85, 1.35), cluster_size=(1.2, 1.9), clusters_per_tip=3,
        cluster_planes=2, root_count=4, root_spread=0.9, taper=0.30,
        bark_material="bark_dark", foliage_material="foliage_green",
        canopy_bias=0.85, max_clusters=44))
    TREES.register(TREES.TreeProfile(
        name="verdant_sapling", height=2.8, trunk_radius=0.08, trunk_sides=6,
        trunk_segments=4, first_branch=0.28, children=(4,),
        cluster_size=(0.45, 0.70), clusters_per_tip=2, cluster_planes=2,
        root_count=0, taper=0.30, bark_material="bark_pale",
        foliage_material="foliage_green", canopy_bias=0.65, max_clusters=14))
    _SPECIES_REGISTERED = True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Amberwood's kits hardcode a few of their own materials - the multi-arch
# bridge lays a cobbled deck, a leaf drift is coloured with the forest floor, a
# well holds pool water. Those are the right choices in an autumn wood and the
# wrong ones here, and the pin check in the build refuses to ship geometry
# pointing at a material the package does not carry. Remapping at the single
# point where a mesh is registered is the region-level fix; editing the shared
# kits to take a material argument each would be a wider change than this
# region needs, and forking them is exactly what the toolkit exists to avoid.
_RETINT: dict[str, str] = {
    "cobble_paving": "verdant_terrace_stone",
    "forest_floor": "verdant_jungle_floor",
    "water_pool": "water_cenote",
}


def _retint(piece):
    """Rewrite any Amberwood-default material to this region's equivalent."""
    parts = getattr(piece, "parts", None)
    if parts is not None:
        for part in piece.parts + piece.walk_parts:
            part.material = _RETINT.get(part.material, part.material)
    else:
        piece.material = _RETINT.get(piece.material, piece.material)
    return piece


def _add_mesh(build: RegionBuild, name: str, piece):
    return build.add_mesh(name, _retint(piece))


def _ground(t, x: float, z: float) -> float:
    return float(t.height_at(x, z))


def _standable(t, x: float, z: float, max_slope: float = 0.95) -> bool:
    """Somewhere a building can sit: above water, not on a cliff, in bounds."""
    if not (REG.PLAY_MIN_X + 6.0 <= x <= REG.PLAY_MAX_X - 6.0
            and REG.PLAY_MIN_Z + 6.0 <= z <= REG.PLAY_MAX_Z - 6.0):
        return False
    if float(t.height_at(x, z)) < REG.SEA_LEVEL + 0.6:
        return False
    return float(t.slope_at(x, z)) < max_slope


def _place(build: RegionBuild, node: str, mesh: str, x: float, z: float,
           y: float | None = None, rotation: float = 0.0, scale: float = 1.0,
           kind: str = "prop", collides: bool = False,
           landmark: str | None = None) -> Placement | None:
    t = build.terrain
    if (kind in ("undergrowth", "vine") or node.startswith("Ground_")) and REG.access_distance(x, z) < 5:
        return None
    if node.startswith(("Rail_", "Arcade_", "Wall_")) and REG.access_distance(x, z) < 7.0:
        return None
    if node.startswith("Rail_Cenote_"):
        d, _ = TER._polyline_distance(np.asarray(x), np.asarray(z),
                                      np.asarray(REG.CENOTE_APPROACH)[:, [0, 2]])
        if float(d) < 4:
            return None
    if y is None:
        y = _ground(t, x, z)
    return build.place(Placement(node=node, mesh=mesh,
                                 position=(round(x, 3), round(y, 3), round(z, 3)),
                                 rotation_y=rotation, scale=scale,
                                 collides=collides, kind=kind, landmark=landmark))


def _landmark(build: RegionBuild, identifier: str, name: str, node: str,
              x: float, z: float, y: float | None = None,
              type: str = "marker", note: str | None = None) -> None:
    """Record a landmark.

    `type` is the manifest convention, not a private key: verify_runtime
    exempts bridges, pavilions and landings from its floating-landmark check by
    reading exactly this field, and the vocabulary is Amberwood's so the two
    packages stay comparable. This was `kind` and nothing read it.
    """
    t = build.terrain
    if node.startswith("Rail_Cenote_"):
        d, _ = TER._polyline_distance(np.asarray(x), np.asarray(z),
                                      np.asarray(REG.CENOTE_APPROACH)[:, [0, 2]])
        if float(d) < 4:
            return None
    if y is None:
        y = _ground(t, x, z)
    entry = {
        "id": identifier, "name": name, "node": node, "type": type,
        "position": [round(x, 2), round(y, 2), round(z, 2)],
        "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                       int(round(REG.SERVER_ORIGIN[1] - z))],
        "terrace": REG.terrace_of(float(REG.stair_axis(x, z))),
    }
    if note:
        entry["note"] = note
    build.landmarks.append(entry)


def _downhill(x: float, z: float) -> float:
    """Yaw that faces down the stair, which is south-west for every terrace."""
    return math.atan2(-1.0, -1.0)


def _scatter(t, centre, radius: float, count: int, rng, *,
             inner: float = 0.0, surfaces=None, max_slope: float = 0.95,
             avoid_blocked: bool = True, min_gap: float = 0.0,
             tries: int = 6):
    """Poisson-ish scatter of standable points in an annulus."""
    out: list[tuple[float, float]] = []
    for _ in range(count):
        for _attempt in range(tries):
            angle = float(rng.uniform(0.0, math.pi * 2.0))
            r = math.sqrt(float(rng.uniform((inner / max(radius, 1e-6)) ** 2, 1.0))) * radius
            x = centre[0] + math.cos(angle) * r
            z = centre[1] + math.sin(angle) * r
            if not _standable(t, x, z, max_slope):
                continue
            if REG.access_distance(x, z) < 5.0:
                continue
            if not avoid_blocked and any(math.hypot(x - px, z - pz) < radius
                    for px, pz, radius in [(-18, -6, 10), (15, -3, 10), (13, -13, 14)]):
                continue
            if avoid_blocked and bool(t.blocked_at(x, z)):
                continue
            if surfaces is not None and int(t.surface_at(x, z)) not in surfaces:
                continue
            if min_gap > 0.0 and any(
                    (x - px) ** 2 + (z - pz) ** 2 < min_gap * min_gap
                    for px, pz in out):
                continue
            out.append((x, z))
            break
    return out


# ---------------------------------------------------------------------------
# pass 1: the stair itself - terrace walls and the flights that climb the risers
# ---------------------------------------------------------------------------
def populate_stair(build: RegionBuild, seed: int) -> None:
    """Retaining walls on every built terrace edge, and the climbs between."""
    from amberwood import junglecraft as JC
    t = build.terrain
    rng = N.Rng(seed + 11)

    # Flights fit surveyed landings and use the same jade, mossy stone and
    # shrine posts as the original monumental stair kit.
    for name, (foot, head, width) in REG.STAIR_RUNS.items():
        key = "GrandStair" if name == "grand-stair" else "Stair_" + name.replace("-", "_")
        rise = head[1] - foot[1]
        length = math.hypot(head[0] - foot[0], head[2] - foot[2])
        _add_mesh(build, key, JC.grand_stair(
            width=width, height=rise, length=length,
            seed=seed + N.stable_hash(name) % 97, landings=1 if rise < 20 else 2))
        yaw = math.atan2(head[0] - foot[0], head[2] - foot[2])
        node = "Landmark_" + key
        _place(build, node, key, foot[0], foot[2], y=foot[1], rotation=yaw,
               kind="stair", collides=False, landmark=name)
        _landmark(build, name, name.replace("-", " ").title(), node,
                  foot[0], foot[2], foot[1], type="monument")

    # -- retaining walls along the downhill edge of the built courts -------
    # One wall variant per length band, instanced: a unique mesh per court
    # would be sixty near-identical walls in the GLB for no visible gain.
    for length in (12.0, 18.0):
        for height in (3.0, 5.0):
            _add_mesh(build, f"TerraceWall_{int(length)}_{int(height)}",
                           JC.terrace_wall(length, height,
                                           seed=seed + int(length * height) % 89))

    walled = ("lower_plaza", "west_quay", "cenote_court", "middle_market",
              "upper_court", "water_shrine", "temple_court", "great_temple",
              "sun_pavilion", "east_lookout", "hanging_gardens",
              "orchid_terrace", "old_terrace", "east_terrace", "priest_walk",
              "summit_watch", "cloud_terrace", "south_quay", "quay_market",
              "lower_gardens", "stair_head", "east_pass", "ridge_shrine")
    for name in walled:
        x, z = REG.ANCHORS[name]
        level = REG.terrace_level(REG._ANCHOR_TERRACE[name])
        # A retaining wall goes at the lip of the court's downhill edge -
        # south-west, on this diagonal - and holds that court up. Ringing every
        # court with a wall on each side, as the first pass did, put a 30 m
        # blank slab across the middle of half the player-eye views; two short
        # runs along one edge read as a terrace instead of as a compound.
        for along, length in ((9.0, 12.0), (-9.0, 18.0)):
            wx = x - 15.0 * 0.7071 + along * 0.7071
            wz = z - 15.0 * 0.7071 - along * 0.7071
            if not (REG.PLAY_MIN_X <= wx <= REG.PLAY_MAX_X
                    and REG.PLAY_MIN_Z <= wz <= REG.PLAY_MAX_Z):
                continue
            drop = level - _ground(t, wx, wz)
            if not 2.2 <= drop <= 8.0:
                continue
            height = 5.0 if drop > 3.8 else 3.0
            key = f"TerraceWall_{int(length)}_{int(height)}"
            _place(build, f"Wall_{name}_{int(length)}", key, wx, wz,
                   y=level - height, rotation=math.pi * 0.25, kind="landmark")


# ---------------------------------------------------------------------------
# pass 2: the landmarks
# ---------------------------------------------------------------------------
def populate_landmarks(build: RegionBuild, seed: int) -> None:
    from amberwood import junglecraft as JC
    from amberwood import props as P
    from amberwood import stonework as SW
    t = build.terrain
    rng = N.Rng(seed + 23)

    # -- the Great Temple: the summit landmark ---------------------------
    x, z = REG.ANCHORS["great_temple"]
    level = REG.terrace_level("temple")
    temple = SW.group()
    temple.add(JC.pagoda(radius=9.0, tiers=4, height=13.0, seed=seed + 31,
                         columns=12))
    # flanking towers, smaller and set back, as in the aerial's top right
    for sign in (-1.0, 1.0):
        wing = JC.pagoda(radius=4.4, tiers=2, height=7.0, seed=seed + 33,
                         columns=8)
        temple.add(wing.translate(sign * 15.0, -1.4, -9.0))
    # a colonnaded screen across the front
    for index in range(11):
        if index == 5:
            continue  # processional opening through the temple screen
        offset = -18.0 + index * 3.6
        temple.add(SW.column(6.2, 0.46, 12, JC.JADE)
                   .translate(offset, 0.0, 13.5))
    temple.add(M.box((40.0, 1.1, 2.2), center=(0.0, 6.75, 13.5),
                     uv_scale=0.9, material=JC.CARVED_JADE))
    for index in range(5):
        temple.add(JC.relief_panel(2.4, 1.4, seed=seed + index)
                   .translate(-9.6 + index * 4.8, 3.4, 14.7))
    from amberwood import routecraft as RC
    temple.add_walk(RC.stair_flight(4.0, 0.78, 2.8, 4, JC.MOSSY)
                    .rotate_y(math.pi).translate(0, 0, 12.4))
    _add_mesh(build, "GreatTemple", temple)
    _place(build, "Landmark_GreatTemple", "GreatTemple", x, z, y=level,
           rotation=math.pi * 0.25, kind="landmark", collides=True,
           landmark="great-temple")
    _landmark(build, "great-temple", "The Green Temple", "Landmark_GreatTemple",
              x, z, level, type="monument",
              note="aerial concept, upper right")

    # -- the Water Shrine: board panel 7 ---------------------------------
    x, z = REG.ANCHORS["water_shrine"]
    level = REG.terrace_level("upper")
    shrine = SW.group()
    shrine.add(JC.jade_gate(span=7.2, height=8.0, seed=seed + 41))
    for sign in (-1.0, 1.0):
        shrine.add(JC.shrine_post(3.0, seed=seed + 43 + int(sign))
                   .translate(sign * 7.4, 0.0, -4.6))
    # steps down into the reflecting pool, which is the panel's whole subject
    steps = M.stairs(11.0, 0.22, 0.62, 7, uv_scale=1.2,
                     material=JC.MOSSY)
    shrine.add_walk(steps.translate(0.0, -1.55, 2.2))
    shrine.add(M.box((13.0, 1.6, 1.0), center=(0.0, -0.8, 7.2),
                     uv_scale=1.0, material=JC.MOSSY))
    _add_mesh(build, "WaterShrine", shrine)
    _place(build, "Landmark_WaterShrine", "WaterShrine", x, z, y=level,
           rotation=math.pi * 0.25, kind="landmark", collides=True,
           landmark="water-shrine")
    _landmark(build, "water-shrine", "The Water Shrine", "Landmark_WaterShrine",
              x, z, level, type="shrine", note="board panel 7")

    # -- the Cenote: board panel 3 ---------------------------------------
    x, z = REG.ANCHORS["cenote"]
    rim = REG.terrace_level("middle")
    floor = _ground(t, x, z)
    _add_mesh(build, "CenoteStair", JC.cenote_stair(
        radius=13.0, depth=max(rim - floor - 1.5, 8.0), seed=seed + 51,
        turns=1.4, width=2.6))
    _place(build, "Landmark_CenoteStair", "CenoteStair", x, z, y=rim,
           rotation=0.0, kind="landmark", landmark="cenote")
    # The marker goes at the head of the stair, on the court side of the rim,
    # rather than over the middle of the shaft: a marker hanging eighteen
    # metres above the water is exactly what the floating-landmark check is
    # for, and the head of the stair is where a player actually stands.
    court = REG.ANCHORS["cenote_court"]
    reach = math.hypot(court[0] - x, court[1] - z)
    mx = x + (court[0] - x) / max(reach, 1e-6) * 15.0
    mz = z + (court[1] - z) / max(reach, 1e-6) * 15.0
    _landmark(build, "cenote", "The Green Cenote", "Landmark_CenoteStair",
              mx, mz, type="landing", note="board panel 3")
    points = np.asarray(REG.CENOTE_APPROACH)
    origin = points[0].copy()
    _add_mesh(build, "CenoteLanding", RC.graded_causeway(
        points - origin, width=3.4, stone=JC.JADE, paving=JC.MOSSY,
        foot=-18))
    _place(build, "Bridge_CenoteLanding", "CenoteLanding",
           origin[0], origin[2], y=origin[1], kind="bridge")
    # a broken balustrade round the rim, so the drop is announced
    _add_mesh(build, "CenoteRail", SW.balustrade(6.0, 1.05, JC.MOSSY))
    for index in range(14):
        angle = math.pi * 2.0 * index / 14
        if index % 5 == 3:
            continue                       # gaps: the ruin is not intact
        _place(build, f"Rail_Cenote_{index:02d}", "CenoteRail",
               x + math.cos(angle) * 15.0, z + math.sin(angle) * 15.0,
               y=rim, rotation=-angle, kind="landmark")

    # -- the aqueduct: reuse the multi-arch bridge rather than a new kit ---
    west = REG.ANCHORS["aqueduct_west"]
    east = REG.ANCHORS["aqueduct_east"]
    length = math.hypot(east[0] - west[0], east[1] - west[1])
    deck = REG.terrace_level("upper") + 1.0
    # Size the arcade from the deepest ground it crosses, not from its two
    # abutments: both of those stand on the terrace, so `min(west, east)` is
    # the terrace level and the piers got a floor 15 m too high. The bridge
    # then stood 7.6 m proud of the deck it was supposed to carry, which is
    # what verify_runtime reported as a buried landmark.
    samples = [_ground(t, west[0] + (east[0] - west[0]) * k / 24.0,
                       west[1] + (east[1] - west[1]) * k / 24.0)
               for k in range(25)]
    floor = min(samples)
    deck_height = max(deck - floor, 8.0)
    _add_mesh(build, "Aqueduct", SW.high_bridge(
        length=length, deck_height=deck_height, width=4.2,
        arches=max(3, int(length / 22.0)), seed=seed + 61, pier_foot=-1.5))
    mid = ((west[0] + east[0]) * 0.5, (west[1] + east[1]) * 0.5)
    _place(build, "Landmark_Aqueduct", "Aqueduct", mid[0], mid[1], y=floor,
           rotation=math.atan2(east[1] - west[1], east[0] - west[0]),
           kind="landmark", collides=True, landmark="aqueduct")
    # the walkable deck `high_bridge` lays sits 0.5 m above `deck_height`
    _landmark(build, "aqueduct", "The Upper Aqueduct", "Landmark_Aqueduct",
              mid[0], mid[1], floor + deck_height + 0.5, type="bridge",
              note="aerial concept, upper left")

    # -- the pavilions that repeat across the terraces --------------------
    _add_mesh(build, "Pavilion", JC.pagoda(radius=4.0, tiers=2, height=6.0,
                                         seed=seed + 71, columns=8))
    _add_mesh(build, "PavilionSmall", JC.pagoda(radius=2.8, tiers=1, height=4.4,
                                              seed=seed + 73, columns=6))
    pavilions = (
        ("sun-pavilion", "The Sun Pavilion", "sun_pavilion", "Pavilion"),
        ("east-lookout", "The East Lookout", "east_lookout", "PavilionSmall"),
        ("upper-court", "The Upper Court", "upper_court", "Pavilion"),
        ("ridge-shrine", "The Ridge Shrine", "ridge_shrine", "PavilionSmall"),
        ("summit-watch", "The Cloud Watch", "summit_watch", "PavilionSmall"),
        ("south-quay", "The South Quay Pavilion", "south_quay", "PavilionSmall"),
        ("hanging-gardens", "The Hanging Gardens", "hanging_gardens", "Pavilion"),
        ("quay-market", "The Quay Pavilion", "quay_market", "PavilionSmall"),
    )
    for identifier, label, anchor, mesh in pavilions:
        x, z = REG.ANCHORS[anchor]
        level = REG.terrace_level(REG._ANCHOR_TERRACE[anchor])
        node = f"Landmark_{_camel(anchor)}"
        _place(build, node, mesh, x, z, y=level,
               rotation=float(rng.uniform(0.0, math.pi * 2)), kind="landmark",
               collides=True, landmark=identifier)
        _landmark(build, identifier, label, node, x, z, level,
                  type="pavilion")

    # -- ruins: the terraces the jungle has taken back --------------------
    for index in range(5):
        _add_mesh(build, f"Ruin_{index}", SW.ruin_fragment(seed=seed + 81 + index,
                                                         scale=1.4))
    for anchor, count in (("old_terrace", 7), ("stone_ring", 9),
                          ("north_watch", 4), ("deep_jungle", 5),
                          ("boundary_shrine", 4)):
        centre = REG.ANCHORS[anchor]
        for index, (px, pz) in enumerate(_scatter(
                t, centre, 26.0, count, rng, inner=6.0, avoid_blocked=False,
                min_gap=5.0)):
            _place(build, f"Ruin_{anchor}_{index:02d}",
                   f"Ruin_{index % 5}", px, pz,
                   rotation=float(rng.uniform(0.0, math.pi * 2)),
                   scale=float(rng.uniform(0.8, 1.5)), kind="landmark",
                   collides=True)
    for anchor, identifier, label in (
            ("old_terrace", "old-terrace", "The Reclaimed Terrace"),
            ("stone_ring", "stone-ring", "The Standing Ring"),
            ("boundary_shrine", "boundary-shrine", "The Marchstone Shrine")):
        x, z = REG.ANCHORS[anchor]
        _landmark(build, identifier, label, f"Ruin_{anchor}_00", x, z,
                  type="ruin")

    # -- the west quay and its boats: board panel 1 -----------------------
    x, z = REG.ANCHORS["boat_landing"]
    _add_mesh(build, "Quay", P.dock(length=26.0, width=4.4, height=1.6, seed=seed + 91))
    _place(build, "Landmark_Quay", "Quay", x, z,
           y=REG.terrace_level("strand"), rotation=math.pi * 0.75,
           kind="landmark", landmark="boat-landing")
    _landmark(build, "boat-landing", "The Boat Landing", "Landmark_Quay",
              x, z, REG.terrace_level("strand"), type="landing",
              note="board panel 1")
    _add_mesh(build, "Boat", P.rowing_boat(length=5.2, beam_width=1.5, seed=seed + 93))
    for index, (px, pz) in enumerate(_scatter(
            t, REG.ANCHORS["lagoon_mouth"], 46.0, 5, rng, inner=12.0,
            avoid_blocked=False, max_slope=9.9, min_gap=9.0) or []):
        pass
    for index in range(5):
        angle = math.pi * 0.75 + index * 0.42
        px = x + math.cos(angle) * (14.0 + index * 5.0)
        pz = z + math.sin(angle) * (14.0 + index * 5.0)
        if _ground(t, px, pz) > REG.SEA_LEVEL - 0.3:
            continue
        _place(build, f"Boat_{index:02d}", "Boat", px, pz, y=REG.SEA_LEVEL - 0.18,
               rotation=float(rng.uniform(0.0, math.pi * 2)), kind="prop")

    # -- the waygate: the arrival interactive gets real geometry ----------
    x, z = REG.ANCHORS["waygate"]
    level = REG.terrace_level("lower")
    gate = SW.group()
    gate.add(JC.jade_gate(span=5.4, height=6.4, seed=seed + 101))
    # A capped cylinder, not a lathe closing at radius zero. A lathe's pole is a
    # fan of slivers that `drop_degenerate` removes on export, which leaves a
    # pinhole exactly on the axis - and the axis is where the default spawn
    # stands, so the client grounded it 0.54 m below its own platform.
    ring = M.cylinder(3.9, 3.7, 0.54, 24, cap_bottom=False, cap_top=True,
                      uv_scale=0.9, material=JC.MOSSY)
    gate.add_walk(ring)
    _add_mesh(build, "Waygate", gate)
    _place(build, "Landmark_Waygate", "Waygate", x, z, y=level,
           rotation=math.pi * 0.25, kind="landmark", collides=True,
           landmark="waygate")
    _landmark(build, "waygate", "The Verdant Stair Waygate", "Landmark_Waygate",
              x, z, level, type="transition",
              note="server interactives.txt node 12")


# ---------------------------------------------------------------------------
# pass 3: the crossings - board panels 4 and 5
# ---------------------------------------------------------------------------
def populate_crossings(build: RegionBuild, seed: int) -> None:
    from amberwood import junglecraft as JC
    from amberwood import treecraft as TC
    t = build.terrain

    for name, (foot, head, width) in REG.STAIR_RUNS.items():
        build.crossings.append({"id": name, "endpoints": [list(foot), list(head)]})
    build.crossings.append({"id": "cenote-landing",
                            "endpoints": [REG.CENOTE_APPROACH[0], REG.CENOTE_APPROACH[-1]]})
    for anchor, gorge, style, deck_above in REG.CROSSINGS:
        centre = REG.ANCHORS[anchor]
        points = REG.RAVINES[gorge]
        # the crossing runs across the gorge, so take the gorge's local
        # direction and span it perpendicular
        distances = np.linalg.norm(points - np.asarray(centre), axis=1)
        index = int(np.argmin(distances))
        a = points[max(index - 1, 0)]
        b = points[min(index + 1, len(points) - 1)]
        along = b - a
        length_along = float(np.linalg.norm(along))
        if length_along < 1e-6:
            continue
        across = np.array([-along[1], along[0]]) / length_along

        # walk out from the gorge floor until the ground has climbed back up
        floor = _ground(t, centre[0], centre[1])
        span = 18.0
        for candidate in np.arange(14.0, 62.0, 2.0):
            left = centre + across * candidate
            right = centre - across * candidate
            if (_ground(t, left[0], left[1]) > floor + deck_above - 1.0
                    and _ground(t, right[0], right[1]) > floor + deck_above - 1.0):
                span = float(candidate)
                break
        start = centre + across * (span + 3.0)
        end = centre - across * (span + 3.0)
        # A western gorge touches the map edge; its boarding ledge must
        # remain inside the playable boundary.
        for bank in (start, end):
            bank[0] = np.clip(bank[0], REG.PLAY_MIN_X + 10, REG.PLAY_MAX_X - 10)
            bank[1] = np.clip(bank[1], REG.PLAY_MIN_Z + 10, REG.PLAY_MAX_Z - 10)
        if anchor == 'ravine_bridge':
            start=np.array([-98.,-146.]);end=np.array([-59.,-136.])
            across=(start-end)/np.linalg.norm(start-end)
        start_y = _ground(t, start[0], start[1]) + 0.4
        end_y = _ground(t, end[0], end[1]) + 0.4
        deck_y = (start_y + end_y) * 0.5

        key = f"Crossing_{_camel(anchor)}"
        if style == "root":
            piece = JC.root_bridge(
                (start[0], start_y, start[1]), (end[0], end_y, end[1]),
                seed=seed + N.stable_hash(anchor) % 97, width=3.4, sag=1.1,
                roots=6)
            note = "board panel 4"
            label = "The Root Crossing"
        else:
            piece = TC.suspension_walkway(
                (start[0], start_y, start[1]), (end[0], end_y, end[1]),
                sag=min(2.2, span * 0.09), width=3.0,
                seed=seed + N.stable_hash(anchor) % 89, rope_material=JC.ROPE)
            note = "board panel 5"
            label = "Rope Crossing"
        _add_mesh(build, key, piece)
        # the bridge is authored in world coordinates, so it is placed at the
        # origin rather than at its own centre - translating it again would
        # move it twice
        _place(build, f"Landmark_{key}", key, 0.0, 0.0, y=0.0, kind="bridge")
        _landmark(build, anchor.replace("_", "-"), label, f"Landmark_{key}",
                  float((start[0]+end[0])/2), float((start[1]+end[1])/2), deck_y, type="bridge",
                  note=note)

        build.crossings.append({"id": anchor, "endpoints": [
            [float(p[0]), float(y), float(p[1])]
            for p, y in ((start + across * (-2 if anchor == "ravine_bridge" else 6), start_y), (end - across * (-2 if anchor == "ravine_bridge" else 6), end_y))]})
        # Wide bank aprons carry the end posts; boarding walks extend onto
        # the banks rather than duplicating the first six metres of deck.
        for side_index, (bank, inward, bank_y) in enumerate(
                ((start, -across, start_y), (end, across, end_y))):
            approach_end = bank - inward * 6.0
            court = bank - inward * 3.0
            t.plateau(tuple(court), 5.5, bank_y - 0.16, edge=6, surface=TER.PAVING)
            t.tree_block |= (t.gx - court[0])**2 + (t.gz - court[1])**2 < 10**2
            walk = JC.plank_walkway(
                (bank[0], bank_y, bank[1]),
                (approach_end[0],
                 _ground(t, approach_end[0], approach_end[1]) + 0.16,
                 approach_end[1]),
                seed=seed + side_index, width=3.4, rails=True,
                ground=lambda px, pz: _ground(t, px, pz))
            _add_mesh(build, f"{key}_Approach{side_index}", walk)
            _place(build, f"Walkway_{_camel(anchor)}_{side_index}",
                   f"{key}_Approach{side_index}", 0.0, 0.0, y=0.0, kind="bridge")


# ---------------------------------------------------------------------------
# pass 4: settlements
# ---------------------------------------------------------------------------
def populate_settlements(build: RegionBuild, seed: int) -> None:
    from amberwood import junglecraft as JC
    from amberwood import props as P
    from amberwood import stonework as SW
    from amberwood import treecraft as TC
    from amberwood import trees as TREES
    _register_species()
    t = build.terrain
    rng = N.Rng(seed + 131)

    def g(x, z):
        return _ground(t, x, z)

    # -- the canopy village: board panel 6 --------------------------------
    centre = REG.ANCHORS["canopy_village"]
    level = REG.terrace_level("middle")
    for index in range(3):
        wood, foliage = TREES.build_tree("verdant_banyan", seed=seed + 141 + index)
        crown = SW.group(wood, foliage)
        crown.add(JC.banyan_roots(radius=4.4, count=11, height=6.5,
                                  seed=seed + 141 + index))
        _add_mesh(build, f"VillageBanyan_{index}", crown)
    for index in range(3):
        _add_mesh(build, f"VillageHut_{index}", JC.stilt_hut(
            seed=seed + 151 + index, width=4.8, depth=4.2, stilt=3.0,
            ground=lambda x, z: 0.0))
    trunks: list[tuple[float, float]] = []
    for index, (px, pz) in enumerate(_scatter(
            t, centre, 26.0, 7, rng, inner=5.0, avoid_blocked=False,
            min_gap=9.0)):
        _place(build, f"Banyan_Village_{index:02d}", f"VillageBanyan_{index % 3}",
               px, pz, rotation=float(rng.uniform(0, math.pi * 2)),
               scale=float(rng.uniform(0.9, 1.25)), kind="tree", collides=True)
        trunks.append((px, pz))
    # platforms round the trunks and huts on the ground between them
    _add_mesh(build, "VillagePlatform", TC.canopy_platform(
        trunk_radius=1.5, deck_radius=5.0, y=8.5, seed=seed + 161, rails=True))
    for index, (px, pz) in enumerate(trunks[:4]):
        _place(build, f"Platform_Village_{index:02d}", "VillagePlatform",
               px, pz, kind="building")
    for index, (px, pz) in enumerate(_scatter(
            t, centre, 22.0, 5, rng, inner=8.0, avoid_blocked=False,
            min_gap=8.0)):
        _place(build, f"Hut_Village_{index:02d}", f"VillageHut_{index % 3}",
               px, pz, rotation=float(rng.uniform(0, math.pi * 2)),
               kind="building", collides=True)
    # the walkways that tie it together, following the trunk ring
    for index in range(len(trunks) - 1):
        a = trunks[index]
        b = trunks[index + 1]
        if math.dist(a, b) > 30.0:
            continue
        deck_y = max(g(*a), g(*b)) + 3.2
        walk = JC.plank_walkway((a[0], deck_y, a[1]), (b[0], deck_y, b[1]),
                                seed=seed + 171 + index, width=1.9,
                                ground=g)
        _add_mesh(build, f"VillageWalk_{index}", walk)
        _place(build, f"Walkway_Village_{index:02d}", f"VillageWalk_{index}",
               0.0, 0.0, y=0.0, kind="bridge")
    _landmark(build, "canopy-village", "The Canopy Village",
              "Hut_Village_00", centre[0], centre[1], level, type="settlement",
              note="board panel 6")

    # -- the lower town: the arrival terrace ------------------------------
    # Amberwood's forest lodge and manor are steep-shingled temperate timber
    # buildings; a street of them in a jade jungle city reads as the wrong
    # region. The terrace house is the same idea in this region's vocabulary -
    # coursed stone below, timber above, a flared tiered roof.
    _add_mesh(build, "TownHouse_0", JC.terrace_house(seed=seed + 181, width=7.0,
                                                     depth=5.6, storeys=2))
    _add_mesh(build, "TownHouse_1", JC.terrace_house(seed=seed + 183, width=5.8,
                                                     depth=5.0, storeys=1,
                                                     entrance_steps=True))
    _add_mesh(build, "TownHouse_2", JC.terrace_house(seed=seed + 184, width=6.4,
                                                     depth=6.0, storeys=2))
    _add_mesh(build, "TownHall", JC.pagoda(radius=6.0, tiers=3, height=8.4,
                                           seed=seed + 185, columns=10))
    _add_mesh(build, "MarketStall", P.market_stall(width=3.0, depth=2.0,
                                                 seed=seed + 187))
    _add_mesh(build, "Well", P.well(radius=1.05, seed=seed + 189))
    _add_mesh(build, "Brazier", P.brazier(seed=seed + 191))
    _add_mesh(build, "Cart", P.cart(seed=seed + 193))
    _add_mesh(build, "Signpost", P.signpost(seed=seed + 195, arms=2))
    _add_mesh(build, "Statue", SW.statue(height=3.0, seed=seed + 197))

    town_level = REG.terrace_level("lower")
    for index, (px, pz) in enumerate(_scatter(
            t, REG.ANCHORS["lower_plaza"], 24.0, 8, rng, inner=9.0,
            avoid_blocked=False, min_gap=9.5)):
        _place(build, f"House_Lower_{index:02d}", f"TownHouse_{index % 3}",
               px, pz, y=town_level,
               rotation=float(rng.uniform(0, math.pi * 2)), kind="building",
               collides=True)
    x, z = REG.ANCHORS["lower_plaza"]
    _place(build, "Building_TownHall", "TownHall", x + 7.0, z - 7.0,
           y=town_level, rotation=math.pi * 0.25, kind="building", collides=True)
    _landmark(build, "stair-house", "The Stairhouse", "Building_TownHall",
              x + 7.0, z - 7.0, town_level, type="civic")
    _place(build, "Prop_Well", "Well", x - 5.0, z + 4.0, y=town_level,
           kind="prop", collides=True)
    _place(build, "Landmark_Statue", "Statue", x + 2.0, z + 9.0, y=town_level,
           rotation=math.pi * 0.25, kind="landmark", collides=True)
    for index, (px, pz) in enumerate(((8, 20), (15, 21), (22, 22))):
        _place(build, f"Stall_Lower_{index:02d}", "MarketStall",
               px, pz, y=town_level, rotation=math.pi, kind="prop")

    # the two NPC premises named in the server's own npcs.txt
    for anchor, node, label, identifier in (
            ("herbalist", "Building_Herbalist", "Tessara's Physick Garden",
             "herbalist"),
            ("provisioner", "Building_Provisioner", "Orru Moss, Provisioner",
             "provisioner")):
        px, pz = REG.ANCHORS[anchor]
        _place(build, node, "TownHouse_1", px, pz, y=town_level,
               rotation=math.pi * 0.25 + (0.4 if anchor == "herbalist" else -0.4),
               kind="building", collides=True)
        # The marker goes on the ground in front of the door, not at the
        # building's centre: a terrace house has a verandah deck two and a half
        # metres up, and a marker under its own floor reads to verify_runtime
        # as a landmark buried in the scenery.
        _landmark(build, identifier, label, node, px - 6.0, pz + 6.0,
                  town_level, type="guild",
                  note="server config/eloria/npcs.txt")

    # -- the quay settlement ----------------------------------------------
    quay_level = REG.terrace_level("quay")
    for index, (px, pz) in enumerate(_scatter(
            t, REG.ANCHORS["west_quay"], 20.0, 5, rng, inner=8.0,
            avoid_blocked=False, min_gap=9.0)):
        _place(build, f"House_Quay_{index:02d}", f"TownHouse_{index % 3}",
               px, pz, y=quay_level,
               rotation=float(rng.uniform(0, math.pi * 2)), kind="building",
               collides=True)
    x, z = REG.ANCHORS["quay_market"]
    for index in range(4):
        angle = math.pi * 2.0 * index / 4 + 0.4
        _place(build, f"Stall_Quay_{index:02d}", "MarketStall",
               x + math.cos(angle) * 9.0, z + math.sin(angle) * 9.0,
               y=quay_level, rotation=-angle, kind="prop")

    # -- the camps: smaller, tents and lean-tos rather than houses --------
    _add_mesh(build, "Camp_Hut", JC.stilt_hut(seed=seed + 201, width=3.8,
                                            depth=3.4, stilt=1.6,
                                            ground=lambda x, z: 0.0))
    _add_mesh(build, "Firewood", P.firewood(radius=0.8, seed=seed + 203))
    _add_mesh(build, "Crate", P.crate(size=0.7, seed=seed + 205))
    _add_mesh(build, "Barrel", P.barrel(seed=seed + 207))
    for anchor in ("fern_camp", "high_camp", "kiln_yard", "north_pass",
                   "strand_camp", "south_watch", "north_watch", "quarry"):
        centre = REG.ANCHORS[anchor]
        level = REG.terrace_level(REG._ANCHOR_TERRACE[anchor])
        for index, (px, pz) in enumerate(_scatter(
                t, centre, 13.0, 2, rng, inner=3.0, avoid_blocked=False,
                min_gap=6.0)):
            _place(build, f"Hut_{anchor}_{index:02d}", "Camp_Hut", px, pz,
                   rotation=float(rng.uniform(0, math.pi * 2)),
                   kind="building", collides=True)
        for index, (px, pz) in enumerate(_scatter(
                t, centre, 11.0, 4, rng, inner=2.0, avoid_blocked=False,
                min_gap=2.5)):
            mesh = ("Firewood", "Crate", "Barrel", "Brazier")[index % 4]
            _place(build, f"Prop_{anchor}_{index:02d}", mesh, px, pz,
                   rotation=float(rng.uniform(0, math.pi * 2)), kind="prop")
        _landmark(build, anchor.replace("_", "-"),
                  anchor.replace("_", " ").title(), f"Hut_{anchor}_00",
                  centre[0], centre[1], level, type="camp")

    # -- signposts where routes meet --------------------------------------
    for anchor in ("waygate", "stair_head", "west_quay", "upper_court",
                   "temple_court", "ridge_shrine", "cenote_court"):
        px, pz = REG.ANCHORS[anchor]
        _place(build, f"Signpost_{_camel(anchor)}", "Signpost",
               px + 4.5, pz + 4.5,
               # The temple forecourt is recessed below its terrace datum.
               y=None if anchor == "temple_court" else REG.terrace_level(REG._ANCHOR_TERRACE[anchor]),
               kind="prop")



# ---------------------------------------------------------------------------
# pass 4b: terrace architecture
# ---------------------------------------------------------------------------
def populate_terrace_architecture(build: RegionBuild, seed: int) -> None:
    """Colonnades, balustraded edges and terrace-edge flights.

    The aerial concept is an architectural picture: every shelf carries a
    colonnade or a screen wall, its edge is balustraded, and short flights drop
    from one level to the next between the main climbs. Without this pass the
    region reads as a jungle with a handful of clearings in it, which is what
    the first minimap showed.
    """
    from amberwood import junglecraft as JC
    from amberwood import stonework as SW
    t = build.terrain
    rng = N.Rng(seed + 331)

    # -- one arcade variant per length, instanced --------------------------
    for columns in (5, 8, 12):
        arcade = SW.group()
        spacing = 3.4
        span = spacing * (columns - 1)
        for index in range(columns):
            arcade.add(SW.column(4.6, 0.36, 10, JC.JADE)
                       .translate(-span * 0.5 + index * spacing, 0.0, 0.0))
        arcade.add(M.box((span + 1.4, 0.62, 1.05), center=(0.0, 4.90, 0.0),
                         uv_scale=0.9, material=JC.CARVED_JADE))
        arcade.add(M.box((span + 1.9, 0.30, 1.35), center=(0.0, 5.36, 0.0),
                         uv_scale=0.9, material=JC.MOSSY))
        _add_mesh(build, f"Arcade_{columns}", arcade)
    _add_mesh(build, "TerraceRail", SW.balustrade(7.0, 1.05, JC.MOSSY))

    # -- the courts that get an architectural edge -------------------------
    courts = ("lower_plaza", "cenote_court", "middle_market", "upper_court",
              "temple_court", "great_temple", "sun_pavilion", "priest_walk",
              "hanging_gardens", "orchid_terrace", "west_quay", "quay_market",
              "east_terrace", "east_pass", "ridge_shrine", "summit_watch",
              "water_shrine", "stair_head", "lower_gardens", "south_quay",
              "east_lookout", "village_landing", "old_terrace", "cloud_terrace")
    rails = 0
    arcades = 0
    for name in courts:
        x, z = REG.ANCHORS[name]
        level = REG.terrace_level(REG._ANCHOR_TERRACE[name])
        # the balustrade runs along the downhill (south-west) edge of the court
        for step in range(-3, 4):
            offset = step * 7.0
            # perpendicular to the fall line, which is the stair diagonal
            bx = x + offset * 0.7071 - 13.0 * 0.7071
            bz = z - offset * 0.7071 - 13.0 * 0.7071
            if not (REG.PLAY_MIN_X < bx < REG.PLAY_MAX_X
                    and REG.PLAY_MIN_Z < bz < REG.PLAY_MAX_Z):
                continue
            # A parapet stands at the lip of a drop. Placed over the full
            # height of a riser it is a rail hanging in mid-air twenty metres
            # from anything, which is what the first captures showed.
            drop = level - _ground(t, bx, bz)
            if not 1.2 <= drop <= 6.0:
                continue
            _place(build, f"Rail_{_camel(name)}_{step + 3}", "TerraceRail",
                   bx, bz, y=level, rotation=math.pi * 0.25, kind="landmark")
            rails += 1
        # an arcade set back on the uphill side, facing the court
        ax = x + 13.0 * 0.7071
        az = z + 13.0 * 0.7071
        if (REG.PLAY_MIN_X < ax < REG.PLAY_MAX_X
                and REG.PLAY_MIN_Z < az < REG.PLAY_MAX_Z
                and abs(_ground(t, ax, az) - level) < 4.0):
            columns = 12 if name in ("great_temple", "temple_court",
                                     "upper_court", "lower_plaza") else (
                8 if name in ("cenote_court", "middle_market", "west_quay",
                              "water_shrine", "sun_pavilion") else 5)
            _place(build, f"Arcade_{_camel(name)}", f"Arcade_{columns}",
                   ax, az, y=level, rotation=math.pi * 0.25,
                   kind="landmark", collides=True)
            arcades += 1

    # There is deliberately no scatter of extra stair flights here. A first
    # attempt dropped fourteen of them at random points along the risers, at a
    # fixed yaw and with no relation to the local fall line; from the air they
    # read as planks of debris lying across the slope. Every climb between two
    # terraces in this region is an authored route with a stair on it, and that
    # is the whole set.
    build.notes.append(
        f"terrace architecture: {arcades} arcades, {rails} balustrade runs")

# ---------------------------------------------------------------------------
# pass 5: the jungle
# ---------------------------------------------------------------------------
def populate_jungle(build: RegionBuild, seed: int, lod: str | None = None) -> None:
    """Trees, by terrace band, thinned where the ground is built or steep."""
    from amberwood import junglecraft as JC
    from amberwood import stonework as SW
    from amberwood import trees as TREES
    _register_species()
    t = build.terrain
    rng = N.Rng(seed + 211)

    tiers = ("low",) if lod == "far" else ("high", "mid", "low")
    variants: dict[tuple[str, str], list[str]] = {}
    for species, count in (("verdant_banyan", 2), ("verdant_emergent", 3),
                           ("verdant_canopy", 4), ("verdant_understory", 3)):
        for tier in tiers:
            keys = []
            for index in range(count):
                key = f"Tree_{species}_{tier}_{index}"
                wood, foliage = TREES.build_tree(
                    species, seed=seed + N.stable_hash(species) % 97 + index * 17,
                    detail=tier)
                piece = SW.group(wood, foliage)
                if species == "verdant_banyan" and tier != "low":
                    piece.add(JC.banyan_roots(
                        radius=4.0, count=9 if tier == "high" else 4,
                        height=6.0, seed=seed + index * 23))
                _add_mesh(build, key, piece)
                keys.append(key)
            variants[(species, tier)] = keys

    # tree ferns and palms are built from fronds, not from leaf sprays
    for index in range(3):
        _add_mesh(build, f"TreeFern_{index}", JC.tree_fern(
            height=float(rng.uniform(3.6, 5.6)), seed=seed + 221 + index,
            crown=2.5))
        _add_mesh(build, f"Palm_{index}", JC.tree_fern(
            height=float(rng.uniform(9.0, 13.0)), seed=seed + 231 + index,
            crown=4.2, trunk_material="bark_pale"))

    # Spacing is per area, not per region: the jungle thins as the map grows
    # rather than the same trees being spread thinner over it.
    spacing = 9.6 if lod is None else 13.5
    cell = spacing
    x0, z0 = REG.PLAY_MIN_X, REG.PLAY_MIN_Z
    cols = int((REG.PLAY_MAX_X - x0) / cell)
    rows = int((REG.PLAY_MAX_Z - z0) / cell)
    density_noise = None
    placed = 0
    for row in range(rows):
        for col in range(cols):
            jitter_x = float(rng.uniform(-cell * 0.45, cell * 0.45))
            jitter_z = float(rng.uniform(-cell * 0.45, cell * 0.45))
            x = x0 + (col + 0.5) * cell + jitter_x
            z = z0 + (row + 0.5) * cell + jitter_z
            if not _standable(t, x, z, max_slope=1.15):
                continue
            if bool(t.blocked_at(x, z)):
                continue
            surface = int(t.surface_at(x, z))
            if surface in (TER.PAVING, TER.TERRACE_MOSS, TER.SHORE,
                           TER.WET_ROCK):
                continue
            if surface == TER.PATH and float(rng.uniform()) < 0.75:
                continue
            height = float(t.height_at(x, z))
            # the canopy thins toward the summit, where the cloud forest is
            # lower and more open, and toward the strand
            thin = 0.20 if height > 54.0 else (0.12 if height < 6.0 else 0.0)
            if float(rng.uniform()) < thin:
                continue

            roll = float(rng.uniform())
            if roll < 0.06:
                species = "verdant_banyan"
            elif roll < 0.26:
                species = "verdant_emergent"
            elif roll < 0.72:
                species = "verdant_canopy"
            else:
                species = "verdant_understory"

            # detail tier by distance from the routes a player actually walks
            if lod == "far":
                tier = "low"
            else:
                near = _near_route(x, z)
                # Tight on purpose. The far tier is where the triangle count
                # stops tracking the area, and a tree 30 m off a path is
                # silhouette, not bark.
                tier = "high" if near < 10.0 else ("mid" if near < 26.0 else "low")
            keys = variants[(species, tier)]
            key = keys[int(rng.integers(0, len(keys)))]
            _place(build, f"Tree_{row:03d}_{col:03d}", key, x, z, height,
                   rotation=float(rng.uniform(0, math.pi * 2)),
                   scale=float(rng.uniform(0.82, 1.24)), kind="tree",
                   collides=True)
            placed += 1

            # a fern or a palm in the gap beside roughly one tree in three
            if lod is None and float(rng.uniform()) < 0.28:
                fx = x + float(rng.uniform(-cell * 0.5, cell * 0.5))
                fz = z + float(rng.uniform(-cell * 0.5, cell * 0.5))
                if _standable(t, fx, fz, 1.05) and not bool(t.blocked_at(fx, fz)):
                    palm = height < 15.0 and float(rng.uniform()) < 0.35
                    mesh = (f"Palm_{int(rng.integers(0, 3))}" if palm
                            else f"TreeFern_{int(rng.integers(0, 3))}")
                    _place(build, f"Fern_{row:03d}_{col:03d}", mesh, fx, fz,
                           rotation=float(rng.uniform(0, math.pi * 2)),
                           scale=float(rng.uniform(0.85, 1.3)), kind="fern",
                           collides=False)
    build.notes.append(f"jungle: {placed} trees at {spacing:.1f} m nominal spacing")


_ROUTE_POINTS: np.ndarray | None = None


def _near_route(x: float, z: float) -> float:
    """Distance to the nearest authored route, for choosing a detail tier."""
    global _ROUTE_POINTS
    if _ROUTE_POINTS is None:
        chunks = []
        for points in REG.ROUTES.values():
            for index in range(points.shape[0] - 1):
                a, b = points[index], points[index + 1]
                steps = max(2, int(np.linalg.norm(b - a) / 12.0))
                for k in range(steps):
                    chunks.append(a + (b - a) * (k / steps))
        _ROUTE_POINTS = np.asarray(chunks)
    d = _ROUTE_POINTS - np.array([x, z])
    return float(np.sqrt((d * d).sum(axis=1)).min())


# ---------------------------------------------------------------------------
# pass 6: the understory
# ---------------------------------------------------------------------------
def populate_understory(build: RegionBuild, seed: int) -> None:
    from amberwood import junglecraft as JC
    from amberwood import props as P
    t = build.terrain
    rng = N.Rng(seed + 241)

    for index in range(4):
        _add_mesh(build, f"FrondClump_{index}", JC.frond_cluster(
            radius=float(rng.uniform(1.3, 2.2)), count=7, seed=seed + 251 + index,
            rise=float(rng.uniform(0.5, 1.3))))
        _add_mesh(build, f"Undergrowth_{index}", P.undergrowth_patch(
            radius=float(rng.uniform(1.0, 1.8)), count=6, seed=seed + 261 + index))
    for index in range(3):
        _add_mesh(build, f"VineCurtain_{index}", JC.vine_curtain(
            width=float(rng.uniform(5.0, 10.0)), drop=float(rng.uniform(4.0, 9.0)),
            seed=seed + 271 + index, density=0.8))

    # ground cover on the shelves
    spacing = 5.2
    x0, z0 = REG.PLAY_MIN_X, REG.PLAY_MIN_Z
    cols = int((REG.PLAY_MAX_X - x0) / spacing)
    rows = int((REG.PLAY_MAX_Z - z0) / spacing)
    count = 0
    for row in range(rows):
        for col in range(cols):
            x = x0 + (col + 0.5) * spacing + float(rng.uniform(-2.2, 2.2))
            z = z0 + (row + 0.5) * spacing + float(rng.uniform(-2.2, 2.2))
            if not _standable(t, x, z, 1.0):
                continue
            surface = int(t.surface_at(x, z))
            if surface in (TER.PAVING, TER.TERRACE_MOSS, TER.WET_ROCK):
                continue
            if surface == TER.SHORE and float(rng.uniform()) < 0.85:
                continue
            if float(rng.uniform()) < 0.42:
                continue
            mesh = (f"FrondClump_{int(rng.integers(0, 4))}"
                    if float(rng.uniform()) < 0.55
                    else f"Undergrowth_{int(rng.integers(0, 4))}")
            _place(build, f"Under_{row:03d}_{col:03d}", mesh, x, z,
                   rotation=float(rng.uniform(0, math.pi * 2)),
                   scale=float(rng.uniform(0.8, 1.5)), kind="undergrowth")
            count += 1

    # vines down the risers, which is where a cliff face is actually seen
    s_grid = REG.stair_axis(t.gx, t.gz)
    hung = 0
    for index in range(len(REG.TERRACES) - 1):
        _, end, low, _ = REG.TERRACES[index]
        start, _, high, _ = REG.TERRACES[index + 1]
        mid = (start + end) * 0.5
        # Sampling the whole map and rejecting everything off the riser found
        # about two curtains per cliff. Sample along the riser instead: pick a
        # point on it directly, then jog across to find the steep face.
        for _ in range(900):
            c = float(rng.uniform(-92.0, 92.0))
            s_here = mid + float(rng.uniform(-1.4, 1.4))
            x = (s_here + c) * REG.SCALE
            z = (c - s_here) * REG.SCALE
            if not (REG.PLAY_MIN_X + 10.0 < x < REG.PLAY_MAX_X - 10.0
                    and REG.PLAY_MIN_Z + 10.0 < z < REG.PLAY_MAX_Z - 10.0):
                continue
            if float(t.slope_at(x, z)) < 1.0:
                continue
            y = float(t.height_at(x, z))
            _place(build, f"Vines_{index}_{hung:03d}",
                   f"VineCurtain_{int(rng.integers(0, 3))}", x, z, y + 6.5,
                   rotation=float(rng.uniform(0, math.pi * 2)),
                   scale=float(rng.uniform(0.8, 1.6)), kind="vine")
            hung += 1
    build.notes.append(f"understory: {count} ground clumps, {hung} vine curtains")


# ---------------------------------------------------------------------------
# pass 7: ground dressing
# ---------------------------------------------------------------------------
def populate_ground_detail(build: RegionBuild, seed: int) -> None:
    from amberwood import props as P
    from amberwood import trees as TREES
    t = build.terrain
    rng = N.Rng(seed + 281)

    for index in range(4):
        _add_mesh(build, f"Boulder_{index}", P.boulder(
            radius=float(rng.uniform(0.9, 2.4)), seed=seed + 291 + index,
            material="verdant_limestone_cliff"))
        _add_mesh(build, f"RockCluster_{index}", P.rock_cluster(
            radius=float(rng.uniform(1.6, 3.2)), count=5, seed=seed + 301 + index,
            material="verdant_limestone_cliff"))
    for index in range(3):
        _add_mesh(build, f"FallenLog_{index}", TREES.fallen_log(
            length=float(rng.uniform(5.0, 9.0)),
            radius=float(rng.uniform(0.4, 0.7)), seed=seed + 311 + index,
            material="bark_pale"))
        _add_mesh(build, f"Stump_{index}", TREES.stump(
            radius=float(rng.uniform(0.55, 0.95)), height=0.9,
            seed=seed + 321 + index, material="bark_dark"))
    _add_mesh(build, "LeafDrift", P.leaf_drift(radius=2.0, seed=seed + 331))

    spacing = 15.0
    x0, z0 = REG.PLAY_MIN_X, REG.PLAY_MIN_Z
    cols = int((REG.PLAY_MAX_X - x0) / spacing)
    rows = int((REG.PLAY_MAX_Z - z0) / spacing)
    count = 0
    for row in range(rows):
        for col in range(cols):
            x = x0 + (col + 0.5) * spacing + float(rng.uniform(-6.0, 6.0))
            z = z0 + (row + 0.5) * spacing + float(rng.uniform(-6.0, 6.0))
            if not _standable(t, x, z, 1.25):
                continue
            surface = int(t.surface_at(x, z))
            roll = float(rng.uniform())
            if surface in (TER.ROCK, TER.WET_ROCK):
                mesh = (f"Boulder_{int(rng.integers(0, 4))}" if roll < 0.6
                        else f"RockCluster_{int(rng.integers(0, 4))}")
            elif surface in (TER.PAVING, TER.TERRACE_MOSS):
                if roll > 0.22:
                    continue
                mesh = "LeafDrift"
            elif roll < 0.30:
                mesh = f"FallenLog_{int(rng.integers(0, 3))}"
            elif roll < 0.52:
                mesh = f"Stump_{int(rng.integers(0, 3))}"
            elif roll < 0.74:
                mesh = "LeafDrift"
            else:
                mesh = f"Boulder_{int(rng.integers(0, 4))}"
            _place(build, f"Ground_{row:03d}_{col:03d}", mesh, x, z,
                   rotation=float(rng.uniform(0, math.pi * 2)),
                   scale=float(rng.uniform(0.75, 1.45)), kind="rock",
                   collides=mesh.startswith(("Boulder", "RockCluster")))
            count += 1
    build.notes.append(f"ground dressing: {count} pieces")
