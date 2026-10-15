"""Placement passes for Amethyst Barrens.

Terrain was proved first: the grounding contract holds on bare ground before any
of this goes in, as the region production guide requires.

The landmark inventory follows the region's own QA brief and the names already
in the placeholder `world.json`, which - unlike Amberwood's - are region-correct
and are treated as canon here: one Glasswarden Observatory, seven crystal
bridges, four geode caves, eight levitating-shard fields, six storm ruins, ten
resonant crystal clusters and six field stations.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import architecture as ARCH
from amberwood import crystalcraft as CC
from amberwood import mesh as M
from amberwood import noise as N
from amberwood import props as PROPS
from amberwood import stonework as SW
from amberwood import terrain as TER

import region as REG
from region import Placement

L = REG.LOCAL

STONE = "amethyst_pale_stone"
ROOF = "amethyst_verdigris"
BRASS = "amethyst_brass"
CLOTH = "amethyst_banner"
CRYSTAL = "amethyst_crystal"
ROCK = "amethyst_storm_rock"


# --------------------------------------------------------------------------
def _ground(t: TER.Terrain, x: float, z: float, sink: float = 0.0):
    return float(x), float(t.height_at(x, z)) - sink, float(z)


def _face(origin, target) -> float:
    return math.atan2(target[0] - origin[0], target[1] - origin[1])


def _remap(piece, mapping: dict[str, str]):
    """Retint a kit piece into this region's palette.

    The shared kits are written against Amberwood's material names. Rather than
    fork them, the pieces are built and their material names rewritten, which
    is why every kit call here is followed by one of these.
    """
    parts = getattr(piece, "parts", None)
    for part in (parts if parts else [piece]):
        part.material = mapping.get(part.material, part.material)
    return piece


# The shared kits are written against Amberwood's material names (see the
# constants in architecture.py, stonework.py and props.py). Every one of them is
# mapped here, so a kit piece cannot arrive carrying a material this package
# does not embed - which is a KeyError at export, not a silent fallback.
KIT_TO_REGION = {
    "ashlar": STONE, "cobble_paving": STONE, "lime_plaster": STONE,
    "sooted_plaster": STONE, "carved_wood": STONE,
    "rubble_stone": ROCK, "cliff_rock": ROCK, "charred_timber": ROCK,
    "timber_warm": STONE, "timber_grey": STONE, "timber_dark": ROCK,
    "shingles": ROOF, "dark_iron": BRASS,
    "woven_cloth": CLOTH, "canvas_awning": CLOTH, "thatch_reed": CLOTH,
    "amber_resin": CRYSTAL, "amber_glass": CRYSTAL,
    "forest_floor": "amethyst_barrens_dust", "leaf_path": "amethyst_barrens_dust",
    "meadow_grass": "amethyst_barrens_dust", "scorched_ground": ROCK,
    "shore_shingle": "shore_shingle",
}


# --------------------------------------------------------------------------
from amberwood.observatorycraft import observatory, armillary


def crystal_bridge(length: float = 26.0, deck_height: float = 7.5,
                   seed: int = 0) -> SW.MeshGroup:
    """Panel 3: a masonry arch bridge whose deck is resonant roadway.

    Built on `stonework.high_bridge`, whose elevation is a solid wall following
    the arch intrados rather than floating rings, then retinted and given lamp
    spires at both ends.
    """
    rng = N.Rng(seed)
    bridge = SW.high_bridge(length=length, deck_height=deck_height, width=5.0,
                            arches=3, seed=seed, pier_foot=-2.0)
    _remap(bridge, KIT_TO_REGION)
    # the deck reads as the roadway, not as masonry
    for part in bridge.walk_parts:
        part.material = "amethyst_resonant_road"

    for sign in (-1.0, 1.0):
        for side in (-1.0, 1.0):
            shaft = M.cylinder(0.42, 0.30, 4.2, 10, uv_scale=0.7, material=STONE)
            bridge.add(shaft.translate(side * 2.2, deck_height,
                                       sign * (length * 0.5 - 1.2)))
            cap = M.cylinder(0.44, 0.02, 1.5, 10, uv_scale=0.7, material=ROOF)
            bridge.add(cap.translate(side * 2.2, deck_height + 4.2,
                                     sign * (length * 0.5 - 1.2)))
            lamp = M.icosphere(0.26, subdivisions=1, material=CRYSTAL)
            bridge.add(lamp.translate(side * 2.2, deck_height + 5.9,
                                      sign * (length * 0.5 - 1.2)))
    return bridge


def storm_ruin(seed: int = 0, span: float = 16.0) -> SW.MeshGroup:
    """Panel 6: a broken colonnade with a standard still flying."""
    rng = N.Rng(seed)
    out = SW.MeshGroup()
    columns = int(rng.integers(5, 9))
    for index in range(columns):
        x = -span * 0.5 + span * index / max(columns - 1, 1)
        height = float(rng.uniform(3.2, 7.4))
        col = SW.column(height, radius=0.52, flutes=12, material=STONE,
                        base=True, capital=bool(rng.integers(0, 2)))
        col.rotate_z(float(rng.normal(0.0, 0.035)))
        out.add(col.translate(x, 0.0, float(rng.normal(0.0, 0.5))))
        # a surviving lintel between some pairs
        if index and rng.integers(0, 3) == 0:
            beam = M.box((span / max(columns - 1, 1), 0.62, 1.05),
                         uv_scale=0.7, material=STONE)
            out.add(beam.translate(x - span / max(columns - 1, 1) * 0.5,
                                   min(height, 5.6), 0.0))

    # a fallen wall stub and scattered drums
    for index in range(int(rng.integers(2, 5))):
        frag = SW.ruin_fragment(seed=seed + 20 + index, scale=1.2)
        _remap(frag, KIT_TO_REGION)
        out.add(frag.translate(float(rng.uniform(-span * 0.6, span * 0.6)), 0.0,
                               float(rng.uniform(-4.5, 4.5))))

    # the banner pole
    pole = M.cylinder(0.16, 0.13, 7.0, 8, uv_scale=0.7, material=BRASS)
    out.add(pole.translate(-span * 0.5 - 1.4, 0.0, 1.6))
    flag = M.box((0.08, 3.4, 2.2), uv_scale=0.8, material=CLOTH)
    out.add(flag.translate(-span * 0.5 - 1.3, 3.0, 2.8))

    # crystal has come up through the ruin floor
    out.add(CC.vein_scatter(radius=span * 0.45, count=int(rng.integers(6, 11)),
                            seed=seed + 41, height=1.3))
    return out


def field_station(seed: int = 0) -> SW.MeshGroup:
    """Panel 8: the Glasswarden field station - canopy, bench, instruments."""
    rng = N.Rng(seed)
    out = SW.MeshGroup()

    # canopy: four posts and a purple awning
    half = 2.9
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            post = M.cylinder(0.13, 0.11, 3.1, 8, uv_scale=0.7, material=BRASS)
            out.add(post.translate(sx * half, 0.0, sz * half))
    from amberwood import civiccraft as CIV
    out.add(CIV.pitched_canopy(7.1,7.1,3.1,4.25,CLOTH,STONE))

    bench = PROPS.workbench(length=2.6, seed=seed + 3)
    _remap(bench, KIT_TO_REGION)
    out.add(bench.translate(0.0, 0.0, -1.3))

    # glowing specimen orbs on the bench and on stands
    for index in range(4):
        orb = M.icosphere(float(rng.uniform(0.16, 0.28)), subdivisions=1,
                          material=CRYSTAL)
        out.add(orb.translate(float(rng.uniform(-1.1, 1.1)), 1.06,
                              -1.3 + float(rng.uniform(-0.3, 0.3))))
    for index in range(2):
        stand = M.cylinder(0.10, 0.08, 1.15, 8, uv_scale=0.7, material=BRASS)
        x = float(rng.uniform(-2.2, 2.2))
        z = float(rng.uniform(0.6, 2.2))
        out.add(stand.translate(x, 0.0, z))
        out.add(M.icosphere(0.24, subdivisions=1, material=CRYSTAL)
                .translate(x, 1.38, z))

    # a small armillary on a tripod, the station's instrument
    out.add(armillary(radius=0.85, seed=seed + 9).translate(1.9, 1.5, -0.4))
    for index in range(3):
        angle = 2.0 * math.pi * index / 3.0
        leg = M.cylinder(0.06, 0.05, 1.5, 6, uv_scale=0.7, material=BRASS)
        leg.rotate_x(0.18 * math.cos(angle))
        leg.rotate_z(0.18 * math.sin(angle))
        out.add(leg.translate(1.9 + math.cos(angle) * 0.22, 0.0,
                              -0.4 + math.sin(angle) * 0.22))

    for index in range(int(rng.integers(2, 5))):
        crate = PROPS.crate(size=float(rng.uniform(0.5, 0.8)), seed=seed + 30 + index)
        _remap(crate, KIT_TO_REGION)
        out.add(crate.translate(float(rng.uniform(-3.2, 3.2)), 0.0,
                                float(rng.uniform(-3.2, 3.2))))

    brazier = PROPS.brazier(seed=seed + 5)
    _remap(brazier, KIT_TO_REGION)
    out.add(brazier.translate(-2.6, 0.0, 2.2))
    return out


def resonant_cluster(seed: int = 0, radius: float = 7.0) -> SW.MeshGroup:
    """Panel 7: a worked crystal digging - crane, scale pan, steps, spoil."""
    rng = N.Rng(seed)
    out = SW.MeshGroup()

    out.add(CC.cluster(count=int(rng.integers(6, 11)), radius=radius * 0.55,
                       height=float(rng.uniform(4.0, 7.0)), seed=seed + 1))

    # timber crane with a hanging brass scale pan
    mast_h = 7.4
    mast = M.cylinder(0.28, 0.22, mast_h, 8, uv_scale=0.7, material=STONE)
    out.add(mast.translate(radius * 0.8, 0.0, radius * 0.2))
    jib = M.cylinder(0.20, 0.16, radius * 1.15, 8, uv_scale=0.7, material=STONE)
    jib.rotate_z(math.pi * 0.5)
    out.add(jib.translate(radius * 0.8 - radius * 0.5, mast_h - 0.4, radius * 0.2))
    stay = M.cylinder(0.07, 0.06, mast_h * 0.9, 6, uv_scale=0.7, material=BRASS)
    stay.rotate_z(-0.55)
    out.add(stay.translate(radius * 0.95, mast_h * 0.5, radius * 0.2))
    # the pan and its chains
    pan_x = radius * 0.8 - radius * 1.0
    for index in range(3):
        angle = 2.0 * math.pi * index / 3.0
        chain = M.cylinder(0.03, 0.03, 1.6, 5, uv_scale=0.7, material=BRASS)
        out.add(chain.translate(pan_x + math.cos(angle) * 0.5,
                                mast_h - 2.1, radius * 0.2 + math.sin(angle) * 0.5))
    pan = M.cylinder(0.95, 0.80, 0.22, 14, uv_scale=0.7, material=BRASS)
    out.add(pan.translate(pan_x, mast_h - 2.4, radius * 0.2))

    # steps cut down into the digging
    steps = M.stairs(2.4, 1.6 / 6.0, 0.34, 6, uv_scale=0.6, material=STONE)
    steps.rotate_y(float(rng.uniform(0.0, math.pi * 2.0)))
    out.add_walk(steps.translate(-radius * 0.7, 0.0, -radius * 0.5))

    for index in range(int(rng.integers(3, 7))):
        crate = PROPS.crate(size=float(rng.uniform(0.5, 0.75)), seed=seed + 60 + index)
        _remap(crate, KIT_TO_REGION)
        out.add(crate.translate(float(rng.uniform(-radius, radius)), 0.0,
                                float(rng.uniform(-radius, radius))))
    out.add(CC.vein_scatter(radius=radius, count=int(rng.integers(8, 14)),
                            seed=seed + 77, height=1.0))
    return out


def watchtower(seed: int = 0) -> SW.MeshGroup:
    """Panel 1: the slender Glasswarden road towers with lit crystal lanterns."""
    out = SW.MeshGroup()
    tower = ARCH.watchtower(height=15.0, seed=seed, radius=2.0)
    _remap(tower, KIT_TO_REGION)
    out.add(tower)
    cap = M.cylinder(2.15, 0.05, 4.2, 12, uv_scale=0.7, material=ROOF)
    out.add(cap.translate(0.0, 15.0, 0.0))
    out.add(M.icosphere(0.52, subdivisions=1, material=CRYSTAL)
            .translate(0.0, 17.6, 0.0))
    for index in range(3):
        angle = 2.0 * math.pi * index / 3.0
        out.add(M.icosphere(0.26, subdivisions=1, material=CRYSTAL)
                .translate(math.cos(angle) * 2.1, 9.4, math.sin(angle) * 2.1))
    return out


# --------------------------------------------------------------------------
def populate_landmarks(build: REG.RegionBuild, seed: int, lod: str | None = None) -> None:
    t = build.terrain
    A = REG.ANCHORS

    def landmark(entry_id, name, node, kind, position):
        build.landmarks.append({
            "id": entry_id, "name": name, "node": node, "type": kind,
            "position": [round(float(position[0]), 2), round(float(position[1]), 2),
                         round(float(position[2]), 2)]})

    # -- the Glasswarden Observatory ---------------------------------------
    build.add_mesh("Observatory", observatory(seed=seed + 1))
    x, y, z = _ground(t, *A["observatory"], sink=0.4)
    # NOT walk_surface=True. The group already marks its own deck with add_walk;
    # setting it on the placement renames the CONTAINER to Walk_, which makes
    # every solid child inherit the prefix - dome, brass and all - and the
    # grounding ray then puts actors on the roof and on the armillary sphere.
    build.place(Placement("Landmark_GlasswardenObservatory", "Observatory",
                          (x, y, z), 0.0,
                          1.0, collides=True, kind="landmark",
                          landmark="glasswarden-observatory",extras={"solidRadius":6.5}))
    t.mark_blocked_disc(A["observatory"], 6.5)
    # the marker sits on the podium deck, which is where a player stands
    landmark("glasswarden-observatory", "The Glasswarden Observatory",
             "Landmark_GlasswardenObservatory", "civic", (x, y + 2.95, z))

    import layout as PLAN
    PLAN.dress_crossings(build,seed)

    # -- four geode caves ---------------------------------------------------
    for index, key in enumerate(("geode_north", "geode_east", "geode_south",
                                 "geode_massif")):
        mesh_key = f"GeodeMouth_{index}"
        build.add_mesh(mesh_key, CC.geode_mouth(radius=5.4, depth=8.0,
                                                seed=seed + 300 + index))
        x, y, z = _ground(t, *A[key], sink=0.6)
        # face the mouth downhill, so it reads as cut into rising ground
        gx, gz = np.gradient(t.height, t.cell)
        rotation = float(index) * 1.31
        build.place(Placement(f"Landmark_GeodeCave_{index}", mesh_key, (x, y, z),
                              rotation, 1.0, collides=True, kind="landmark",
                              landmark=f"amethyst-geode-cave-{index}"))
        t.mark_blocked_disc(A[key], 9.0 * L)
        landmark(f"amethyst-geode-cave-{index}", "Amethyst Geode Cave",
                 f"Landmark_GeodeCave_{index}", "cave", (x, y, z))

    # -- eight levitating shard fields --------------------------------------
    for index, key in enumerate(("shards_massif", "shards_basin", "shards_east",
                                 "shards_south", "shards_west", "shards_north",
                                 "shards_gate", "shards_coast")):
        mesh_key = f"FloatingShards_{index}"
        build.add_mesh(mesh_key, CC.floating_field(
            count=9 if lod is None else 5, radius=8.0,
            base_height=7.0, hero_height=7.5, seed=seed + 400 + index))
        x, y, z = _ground(t, *A[key])
        build.place(Placement(f"Landmark_LevitatingShards_{index}", mesh_key,
                              (x, y, z), float(index) * 0.77, 1.0,
                              collides=False, kind="shards",
                              landmark=f"amethyst-levitating-shards-{index}"))
        landmark(f"amethyst-levitating-shards-{index}", "Amethyst Levitating Shards",
                 f"Landmark_LevitatingShards_{index}", "phenomenon", (x, y, z))

    # -- six storm ruins ----------------------------------------------------
    for index, key in enumerate(("ruin_colonnade", "ruin_east_arch", "ruin_basin",
                                 "ruin_south", "ruin_west", "ruin_north")):
        mesh_key = f"StormRuin_{index}"
        build.add_mesh(mesh_key, storm_ruin(seed=seed + 500 + index,
                                            span=float(12.0 + 3.0 * (index % 3))))
        x, y, z = _ground(t, *A[key], sink=0.2)
        build.place(Placement(f"Landmark_StormRuin_{index}", mesh_key, (x, y, z),
                              float(index) * 0.91, 1.0, collides=True,
                              kind="landmark",
                              landmark=f"amethyst-storm-ruin-{index}"))
        t.mark_blocked_disc(A[key], 10.0 * L)
        landmark(f"amethyst-storm-ruin-{index}", "Amethyst Storm Ruin",
                 f"Landmark_StormRuin_{index}", "ruin", (x, y, z))

    # -- ten resonant crystal clusters --------------------------------------
    cluster_keys = ("cluster_court", "cluster_north", "cluster_east",
                    "cluster_south", "cluster_west", "cluster_far_east",
                    "cluster_mid", "cluster_massif", "cluster_road",
                    "cluster_deep")
    for index, key in enumerate(cluster_keys):
        mesh_key = f"ResonantCluster_{index}"
        build.add_mesh(mesh_key, resonant_cluster(seed=seed + 600 + index,
                                                  radius=float(6.0 + index % 4)))
        x, y, z = _ground(t, *A[key], sink=0.3)
        build.place(Placement(f"Landmark_ResonantCluster_{index}", mesh_key,
                              (x, y, z), float(index) * 0.63, 1.0, collides=True,
                              kind="landmark",
                              landmark=f"resonant-crystal-cluster-{index}"))
        landmark(f"resonant-crystal-cluster-{index}", "Resonant Crystal Cluster",
                 f"Landmark_ResonantCluster_{index}", "diggings", (x, y, z))

    # -- road towers and the stone ring -------------------------------------
    for index, key in enumerate(("watchtower_west", "watchtower_east",
                                 "watchtower_south")):
        mesh_key = f"Watchtower_{index}"
        build.add_mesh(mesh_key, watchtower(seed=seed + 700 + index))
        x, y, z = _ground(t, *A[key], sink=0.3)
        build.place(Placement(f"Landmark_Watchtower_{index}", mesh_key, (x, y, z),
                              float(index) * 1.7, 1.0, collides=True,
                              kind="landmark", landmark=f"glasswarden-tower-{index}"))
        t.mark_blocked_disc(A[key], 6.0 * L)
        landmark(f"glasswarden-tower-{index}", "Glasswarden Watchtower",
                 f"Landmark_Watchtower_{index}", "tower", (x, y, z))

    ring = SW.MeshGroup()
    rng = N.Rng(seed + 800)
    for index in range(11):
        angle = 2.0 * math.pi * index / 11.0
        stone = M.box((1.1, float(rng.uniform(2.6, 4.2)), 0.75), uv_scale=0.7,
                      material=ROCK)
        stone.rotate_y(angle + float(rng.normal(0.0, 0.08)))
        stone.rotate_z(float(rng.normal(0.0, 0.04)))
        ring.add(stone.translate(math.cos(angle) * 8.5,
                                 float(rng.uniform(1.2, 2.0)),
                                 math.sin(angle) * 8.5))
    build.add_mesh("StoneRing", ring)
    x, y, z = _ground(t, *A["stone_ring"])
    build.place(Placement("Landmark_StoneRing", "StoneRing", (x, y, z), 0.0, 1.0,
                          collides=True, kind="landmark", landmark="resonance-ring"))
    landmark("resonance-ring", "The Resonance Ring", "Landmark_StoneRing",
             "monument", (x, y, z))


def populate_stations(build: REG.RegionBuild, seed: int, lod: str | None = None) -> None:
    """Six Glasswarden field stations, each on its graded roadside pad."""
    t = build.terrain
    A = REG.ANCHORS
    keys = ("station_gate", "station_river", "station_east", "station_south",
            "station_massif", "station_coast")
    for index, key in enumerate(keys):
        mesh_key = f"FieldStation_{index}"
        build.add_mesh(mesh_key, field_station(seed=seed + 900 + index))
        x, y, z = _ground(t, *A[key])
        build.place(Placement(f"Landmark_FieldStation_{index}", mesh_key, (x, y, z),
                              float(index) * 1.05, 1.0, collides=True,
                              kind="building",
                              landmark=f"glasswarden-field-station-{index}"))
        t.mark_blocked_disc(A[key], 5.0 * L)
        build.landmarks.append({
            "id": f"glasswarden-field-station-{index}",
            "name": "Glasswarden Field Station",
            "node": f"Landmark_FieldStation_{index}", "type": "camp",
            "position": [round(x, 2), round(y, 2), round(z, 2)]})
        build.interactives.append({
            "id": f"assay-bench-{index}", "name": "Assay Bench",
            "node": f"Landmark_FieldStation_{index}", "kind": "crafting",
            "position": [round(x, 2), round(y + 1.0, 2), round(z, 2)],
            "authority": "server"})


def populate_crystal(build: REG.RegionBuild, seed: int, lod: str | None = None) -> None:
    """The massif's spires, and crystal breaking out across the barrens."""
    t = build.terrain
    A = REG.ANCHORS
    rng = N.Rng(seed + 1100)

    # -- the great massif: the pale shards that dominate the aerial ---------
    massif_x, massif_z = A["crystal_massif"]
    hero_count = 7 if lod is None else 4
    for index in range(hero_count):
        angle = 2.0 * math.pi * index / hero_count + 0.3
        distance = float(rng.uniform(0.0, 26.0)) if index else 0.0
        x = massif_x + math.cos(angle) * distance
        z = massif_z + math.sin(angle) * distance
        height = float(rng.uniform(34.0, 58.0)) if index == 0 else \
            float(rng.uniform(16.0, 40.0))
        mesh_key = f"MassifSpire_{index}"
        build.add_mesh(mesh_key, CC.spire(height=height,
                                          radius=height * 0.115,
                                          seed=seed + 1200 + index))
        y = float(t.height_at(x, z)) - 1.0
        build.place(Placement(f"Crystal_MassifSpire_{index}", mesh_key,
                              (float(x), y, float(z)), float(index) * 0.9, 1.0,
                              collides=True, kind="crystal"))
        t.mark_blocked_disc((x, z), height * 0.18)
    build.landmarks.append({
        "id": "the-amethyst-massif", "name": "The Amethyst Massif",
        "node": "Crystal_MassifSpire_0", "type": "natural",
        "position": [round(float(massif_x), 2),
                     round(float(t.height_at(massif_x, massif_z)), 2),
                     round(float(massif_z), 2)]})

    # -- secondary spires on the surrounding uplands -----------------------
    for index, key in enumerate(("massif_foot", "massif_east", "cliff_overlook")):
        x, z = A[key]
        for step in range(3 if lod is None else 1):
            height = float(rng.uniform(10.0, 22.0))
            mesh_key = f"UplandSpire_{index}_{step}"
            build.add_mesh(mesh_key, CC.spire(height=height, radius=height * 0.13,
                                              seed=seed + 1300 + index * 7 + step))
            px = x + float(rng.uniform(-22.0, 22.0))
            pz = z + float(rng.uniform(-22.0, 22.0))
            build.place(Placement(f"Crystal_UplandSpire_{index}_{step}", mesh_key,
                                  (px, float(t.height_at(px, pz)) - 0.8, pz),
                                  float(step) * 1.4, 1.0, collides=True,
                                  kind="crystal"))

    # -- outcrops through the crystal fields --------------------------------
    surface = t.surface
    cells = np.argwhere(surface == TER.CRYSTAL_FIELD)
    if not len(cells):
        return
    target = 260 if lod is None else 60
    picks = rng.integers(0, len(cells), size=min(target, len(cells)))
    variants = 8
    for variant in range(variants):
        build.add_mesh(f"CrystalOutcrop_{variant}",
                       CC.outcrop(seed=seed + 1400 + variant,
                                  radius=float(rng.uniform(1.8, 3.4)),
                                  height=float(rng.uniform(2.6, 5.2))))
    placed = 0
    for order, index in enumerate(picks):
        cz, cx = cells[int(index)]
        x = float(t.x0 + cx * t.cell)
        z = float(t.z0 + cz * t.cell)
        if not (REG.PLAY_MIN_X <= x <= REG.PLAY_MAX_X
                and REG.PLAY_MIN_Z <= z <= REG.PLAY_MAX_Z):
            continue
        if t.blocked_at(x, z):
            continue
        build.place(Placement(f"Crystal_Outcrop_{placed}",
                              f"CrystalOutcrop_{order % variants}",
                              (x, float(t.height_at(x, z)) - 0.35, z),
                              float(order) * 0.41,
                              float(np.clip(rng.uniform(0.7, 1.5), 0.7, 1.5)),
                              collides=True, kind="crystal"))
        placed += 1
    build.notes.append(f"crystal outcrops placed: {placed}")


def populate_ground_detail(build: REG.RegionBuild, seed: int) -> None:
    """Boulders and small crystal on the open barrens - the cheapest dressing."""
    t = build.terrain
    rng = N.Rng(seed + 1500)

    for variant in range(6):
        rock = PROPS.rock_cluster(radius=float(rng.uniform(1.4, 2.8)),
                                  count=int(rng.integers(3, 7)),
                                  seed=seed + 1600 + variant)
        _remap(rock, KIT_TO_REGION)
        build.add_mesh(f"BarrensRocks_{variant}", rock)
    for variant in range(5):
        build.add_mesh(f"VeinScatter_{variant}",
                       CC.vein_scatter(radius=float(rng.uniform(2.0, 4.0)),
                                       count=int(rng.integers(5, 10)),
                                       seed=seed + 1700 + variant,
                                       height=float(rng.uniform(0.5, 1.1))))

    barrens = np.argwhere(np.isin(t.surface, [TER.BARRENS, TER.STORM_ROCK]))
    if not len(barrens):
        return
    picks = rng.integers(0, len(barrens), size=min(420, len(barrens)))
    rocks = veins = 0
    for order, index in enumerate(picks):
        cz, cx = barrens[int(index)]
        x = float(t.x0 + cx * t.cell)
        z = float(t.z0 + cz * t.cell)
        if not (REG.PLAY_MIN_X <= x <= REG.PLAY_MAX_X
                and REG.PLAY_MIN_Z <= z <= REG.PLAY_MAX_Z):
            continue
        if t.blocked_at(x, z):
            continue
        y = float(t.height_at(x, z))
        if y < REG.SEA_LEVEL + 0.4:
            continue
        if order % 3 == 0:
            build.place(Placement(f"Prop_BarrensRocks_{rocks}",
                                  f"BarrensRocks_{order % 6}",
                                  (x, y - 0.3, z), float(order) * 0.37,
                                  float(rng.uniform(0.7, 1.4)),
                                  collides=False, kind="scatter"))
            rocks += 1
        else:
            build.place(Placement(f"Prop_VeinScatter_{veins}",
                                  f"VeinScatter_{order % 5}",
                                  (x, y - 0.1, z), float(order) * 0.53,
                                  float(rng.uniform(0.7, 1.3)),
                                  collides=False, kind="scatter"))
            veins += 1
    build.notes.append(f"ground dressing: {rocks} rock clusters, {veins} vein scatters")


# --------------------------------------------------------------------------
def build_water(build: REG.RegionBuild) -> None:
    """The two sea corners and the resonant river."""
    t = build.terrain

    # One sea surface over the whole footprint, clipped to where the ground is
    # actually below sea level, so both the north-east bay and the south-east
    # inlet are covered by a single plane and the open water runs to the horizon.
    build.water_meshes["Water_Sea"] = TER.water_plane(
        t, REG.SEA_LEVEL,
        t.x0, t.z0, t.x0 + t.size_x, t.z0 + t.size_z,
        material="water_sea", cell=6.0, only_below=True, margin=0.30,
        outside_is_water=True)

    build.water_meshes["Water_RiverResonant"] = _river_ribbon(
        t, REG.STREAMS["resonant_river"], width=5.2 * REG.SCALE,
        material="water_stream")
    build.water_meshes["Water_RiverBeck"] = _river_ribbon(
        t, REG.STREAMS["mountain_beck"], width=3.4 * REG.SCALE,
        material="water_stream")


def _river_ribbon(t: TER.Terrain, points: np.ndarray, width: float,
                  material: str, drop: float = 0.35) -> M.Mesh:
    """A water strip that follows a carved channel down its own gradient.

    Sampled along the polyline rather than laid flat: the river falls several
    metres from the northern mountains to the sea, and one flat plane over it
    would either float at the top or vanish at the bottom.
    """
    mesh = M.Mesh(material=material)
    if len(points) < 2:
        return mesh

    segments = np.diff(points, axis=0)
    lengths = np.hypot(segments[:, 0], segments[:, 1])
    total = float(lengths.sum())
    if total <= 0.0:
        return mesh
    count = max(int(total / 6.0), 2)
    distances = np.linspace(0.0, total, count + 1)
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    xs = np.interp(distances, cumulative, points[:, 0])
    zs = np.interp(distances, cumulative, points[:, 1])

    bed = t._water_bed.height_at(xs,zs) if hasattr(t,"_water_bed") else t.height_at(xs,zs)
    # monotonic downstream: a river does not run uphill, and the eroded bed can
    # wobble by a few centimetres either way
    surface = np.minimum.accumulate(bed) + 0.45

    tangent_x = np.gradient(xs)
    tangent_z = np.gradient(zs)
    norm = np.hypot(tangent_x, tangent_z)
    norm[norm < 1e-6] = 1.0
    nx = -tangent_z / norm
    nz = tangent_x / norm

    half = width * 0.5
    left = np.stack([xs + nx * half, surface, zs + nz * half], axis=-1)
    right = np.stack([xs - nx * half, surface, zs - nz * half], axis=-1)

    positions = np.empty((len(xs) * 2, 3), dtype=np.float64)
    positions[0::2] = left
    positions[1::2] = right
    uvs = np.zeros((len(positions), 2), dtype=np.float64)
    uvs[:, 0] = positions[:, 0] * 0.09
    uvs[:, 1] = positions[:, 2] * 0.09
    normals = np.tile(np.array([0.0, 1.0, 0.0]), (len(positions), 1))

    indices = []
    for i in range(len(xs) - 1):
        a, b, c, d = i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 3
        indices.extend([a, c, b, b, c, d])

    mesh.positions = positions
    mesh.normals = normals
    mesh.uvs = uvs
    mesh.indices = np.asarray(indices, dtype=np.int64)
    return mesh
