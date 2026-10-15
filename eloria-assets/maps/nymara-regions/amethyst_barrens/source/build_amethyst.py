#!/usr/bin/env python3
"""Build the Amethyst Barrens runtime map package.

Outputs, next to this source tree:

    ../world.glb        self-contained glTF 2.0 (geometry, materials, textures)
    ../world.json       GLB world manifest, schema version 1
    ../collision.bin    half-metre walkability grid (EWCG v1)
    ../minimap.webp     minimap rendered from the final geometry
    ../world.glb.validator.json
    ../performance-summary.md

Deterministic: the same seed reproduces the same bytes.

Unlike `build_amberwood.py` this passes `only=` to `register_gltf_materials`,
so the package embeds only the textures this region actually uses. With four
regions appending their kits to the shared material table, a build that embeds
all of them grows by roughly ten megabytes of PNG per kit for no visible gain.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# The authoring toolkit is shared by every region and lives one level up, in
# `maps/nymara-regions/_toolkit/`. It must be on the path before the toolkit
# modules below are imported.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_gltf

from amberwood import gltf as GLTF
from amberwood import materials as MAT
from amberwood import mesh as M
from amberwood import terrain as TER

import populate as POP
import region as REG
import layout as PLAN
from amberwood import routecraft as RC
import copy
import transitions as MARCH
import secretdoors as SD
import secrets_design as SEC
import loresites as LORE
import landscape_plan as LANDSCAPE
import streaming_borders as SB

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
SEED = 20260828
# Class islands smaller than this are given to whatever surrounds them. Six
# two-metre cells is 24 m2 - smaller than any surface a player is meant to read
# as its own thing, and larger than every crumb the thresholded noise and the
# boundary dither leave behind.
DESPECKLE_MIN_CELLS = 6

ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# The four crossings, as region-connections.json declares them: the Whitehorn
# pass in the north, the Mirrorhold road along the lake's north shore to the
# west, the Sunmane track south, and the east landing where the Crownwater
# packet calls. Whitehorn's snow blows down the pass, the citadel's turf runs
# in along the west road, steppe grass climbs the south track.
CROSSINGS = [
    MARCH.Crossing("north-pass", "whitehorn_range", REG.ANCHORS["shards_north"],
                   (REG.ANCHORS["shards_north"][0], REG.PLAY_MIN_Z - 20.0),
                   radius=50.0, name="The Whitehorn March"),
    MARCH.Crossing("west-road", "mirrorhold", REG.ANCHORS["mirror_gate"],
                   (REG.PLAY_MIN_X - 20.0, REG.ANCHORS["mirror_gate"][1]),
                   radius=46.0, name="The Mirror Road March"),
    MARCH.Crossing("south-road", "sunmane_steppe", REG.ANCHORS["road_end_south"],
                   (REG.ANCHORS["road_end_south"][0], REG.PLAY_MAX_Z + 20.0),
                   radius=48.0, name="The Steppe March"),
    MARCH.Crossing("east-shore", "crownwater", REG.ANCHORS["road_end_east"],
                   (400.0,160.0), station_position=(319.0,64.0),
                   radius=32.0, ferry=True, name="The East Landing"),
]

# The places the region's people argue about (see loresites.py).
SITES = [
    LORE.Site("eleven-measures", "The Eleven Measures", "measure_stones", (218.0, -192.0),
              thread="C", clearing=13.0,
              note="Eleven calibration stones in an arc, each with a brass collar and a shard "
                   "cut to one length. A Glasswarden tunes against all eleven in a walk."),
]
MARCH_MATERIALS: dict = dict(getattr(REG, "SURFACE_MATERIALS", {}))
MARCH_MATERIALS[TER.RESONANT_ROAD] = "alpine_gravel"

# The materials this region embeds. Named explicitly rather than derived, so a
# kit added by another region cannot silently enlarge this package.
MATERIALS: frozenset[str] = frozenset({
    "amethyst_barrens_dust", "amethyst_crystal_field", "amethyst_resonant_road",
    "amethyst_storm_rock", "amethyst_crystal", "amethyst_pale_stone",
    "amethyst_verdigris", "amethyst_brass", "amethyst_banner",
    "shore_shingle", "cobble_paving", "water_sea", "water_stream", "timber_grey", "thatch_reed", "alpine_gravel",
}) | MARCH.materials_for("amethyst_barrens", CROSSINGS) | SD.materials(SEC) | LORE.materials([s.piece for s in SITES]) | (SB.materials_for("amethyst_barrens") if hasattr(SB,"materials_for") else set())


# --------------------------------------------------------------------------
def build_region(seed: int = SEED, lod: str | None = None) -> REG.RegionBuild:
    """Build the region. `lod="far"` produces the reduced second package."""
    t0 = time.time()
    terrain = REG.build_terrain(seed)
    REG.close_world(terrain)
    for course in REG.STREAMS.values():
        RC.incise_channel(terrain,course,width=7.0,shoulder=7.0,floor=-0.6)
    terrain._water_bed=copy.copy(terrain)
    terrain._water_bed.height=terrain.height.copy()
    REG.apply_built_ground(terrain, seed)
    build = REG.RegionBuild(terrain=terrain)

    # Surfaces are painted before the placement passes, not after: the crystal
    # and ground-dressing passes choose their sites by surface class, and if the
    # classes are still unpainted they scatter nothing at all.
    REG.assign_surfaces(terrain, seed)
    MARCH.prepare(terrain, CROSSINGS)
    LORE.prepare(terrain, SITES, sea_level=getattr(REG, "SEA_LEVEL", 0.0))

    PLAN.prepare(terrain)
    LANDSCAPE.prepare(terrain, seed)
    POP.populate_landmarks(build, seed, lod=lod)
    PLAN.dress(build,seed)
    POP.populate_stations(build, seed, lod=lod)
    POP.populate_crystal(build, seed, lod=lod)
    if lod is None:
        POP.populate_ground_detail(build, seed)

    POP.build_water(build)
    LANDSCAPE.dress(build, seed, lod)

    # The marches: the neighbours' country coming in along the roads out.
    MARCH.paint(terrain, CROSSINGS, MARCH_MATERIALS, seed, sea_level=REG.SEA_LEVEL)
    march = MARCH.dress(build, "amethyst_barrens", CROSSINGS, seed, sea_level=REG.SEA_LEVEL)
    LORE.dress(build, terrain, SITES, seed)
    SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
    build.landmarks.extend(march.landmarks)
    build.notes.extend(march.notes)

    RC.clear_walk_corridors(build,[[[x,0,z] for x,z in p] for p in REG.ROUTES.values()],
                            {"crystal":4.8,"shards":4.5,"rock":4.2,"scrub":3.8,"prop":2.5})
    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.28, blend_edges=True, material_suffix=MAT.GROUND_SUFFIX,
        materials=MARCH_MATERIALS)
    # The backdrop is the distant mountain ring. It comes out of the toolkit in
    # Amberwood's cliff rock, so it is retinted into this region's storm rock -
    # otherwise the horizon is grey while everything in front of it is violet.
    backdrop = TER.backdrop(terrain, reach=240.0, cell=11.0, seed=seed + 909, open_side="east", clip_interior=True)
    backdrop.material = "amethyst_storm_rock"
    build.terrain_meshes["Backdrop_Distant"] = backdrop
    build.resolve_names()
    _add_spawns_and_portals(build)
    _add_population_markers(build, seed)
    LANDSCAPE.compact(build)
    print(f"[region] built in {time.time() - t0:.1f}s")
    return build


def _add_spawns_and_portals(build: REG.RegionBuild) -> None:
    t = build.terrain
    for spawn_id, key, facing in (
            ("default", "arrival", 0.0),
            ("observatory", "observatory_court", math.pi),
            ("massif-camp", "station_massif", math.pi * 0.5)):
        x, z = REG.ANCHORS[key]
        y = float(t.height_at(x, z))
        build.spawns.append({
            "id": spawn_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})

    # Edge portals to neighbouring Nymara regions. Destination map ids follow the
    # client registry; the server remains authoritative for the transition.
    for portal_id, name, key, destination in (
            ("west-road", "Mirror Road to Mirrorhold", "mirror_gate",
             "mirrorhold"),
            ("north-pass", "Whitehorn Pass", "shards_north",
             "whitehorn_range"),
            ("east-shore", "Crownwater Landing", "road_end_east",
             "crownwater"),
            ("south-road", "Sunmane Track", "road_end_south",
             "sunmane_steppe")):
        x, z = REG.ANCHORS[key]
        y = float(t.height_at(x, z))
        build.portals.append({
            "id": portal_id, "name": name, "type": "map-transition",
            "position": [round(float(x), 2), round(y + 0.1, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "destinationMap": destination, "radius": 3.5,
            "authority": "server"})

    # Interior entrances. All four Amethyst insides live on one map with
    # blackspace between them, in the Eternal Lands convention, so every door
    # targets the same `destinationMap` and differs only in which arrival point
    # it asks for. Each door also gets a spawn of the same name on this map, so
    # the return portal on the insides map has somewhere to put the player back.
    for portal_id, name, landmark_id in (
            ("resonant-vault-stair", "The Resonant Vault", "glasswarden-observatory"),
            ("geode-hollow-mouth", "The Geode Hollow", "amethyst-geode-cave-1"),
            ("shardworks-headframe", "The Shardworks", "resonant-crystal-cluster-0"),
            ("storm-barrow-stair", "The Storm Barrow", "amethyst-storm-ruin-0"),
            ("sour-cut-mouth", "The Sour Cut", "amethyst-geode-cave-3"),
            ("measure-house-door", "The Measure House", "amethyst-storm-ruin-2"),
            ("counting-house-door", "The Shard Counter's House", "resonant-crystal-cluster-2"),
):
        anchor = next((l for l in build.landmarks if l.get("id") == landmark_id), None)
        if anchor is None:
            continue
        x, y, z = anchor["position"]
        x,z=PLAN.DOORS[portal_id]
        y=float(t.height_at(x,z))
        if portal_id=="resonant-vault-stair":
            y=float(t.height_at(*REG.ANCHORS["observatory"]))+2.5
        position = [round(float(x), 2), round(float(y) + 0.1, 2), round(float(z), 2)]
        tile = [int(round(x + REG.SERVER_ORIGIN[0])),
                int(round(REG.SERVER_ORIGIN[1] - z))]
        build.portals.append({
            "id": portal_id, "name": name, "type": "interior-entrance",
            "position": position, "serverTile": tile, "landmark": landmark_id,
            "destinationMap": "resonant_vault",
            "destinationSpawn": portal_id, "radius": 2.5,
            "authority": "server"})
        build.spawns.append({
            "id": portal_id,
            "position": [position[0], round(y + 0.05, 2), position[2]],
            "serverTile": tile,
            "rotationDegrees": 0.0,
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True,
            "note": "return point from the Amethyst Barrens insides map"})


def _add_population_markers(build: REG.RegionBuild, seed: int) -> None:
    """Editor/visual markers only - the server owns actual spawning."""
    rng = np.random.default_rng(seed ^ 0x5EED)
    t = build.terrain

    def marker(collection, entry):
        collection.append(entry)

    npc_sites = [
        ("glasswarden-astronomer", "Glasswarden Astronomer", "observatory_court"),
        ("glasswarden-warden", "Glasswarden of the Gate", "observatory_gate"),
        ("resonance-surveyor", "Resonance Surveyor", "cluster_court"),
        ("crystal-factor", "Crystal Factor", "station_river"),
        ("caravan-assayer", "Caravan Assayer", "station_east"),
        ("shard-cutter", "Shard Cutter", "cluster_north"),
        ("storm-watcher", "Storm Watcher", "cliff_overlook"),
        ("road-warden", "Road Warden", "station_south"),
        ("coast-factor", "Coast Factor", "station_coast"),
        ("massif-guide", "Massif Guide", "station_massif"),
    ]
    for npc_id, name, key in npc_sites:
        x, z = REG.ANCHORS[key]
        marker(build.npc_markers, {
            "id": npc_id, "name": name,
            "position": [round(float(x), 2),
                         round(float(t.height_at(x, z)) + 0.05, 2),
                         round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "role": "editor-marker", "authority": "server"})

    creature_zones = [
        ("storm-drake", "Storm Drake", "crystal_massif", 60.0),
        ("shard-stalker", "Shard Stalker", "shards_basin", 48.0),
        ("resonant-elemental", "Resonant Elemental", "cluster_deep", 40.0),
        ("barrens-jackal", "Barrens Jackal", "ruin_south", 56.0),
        ("geode-crawler", "Geode Crawler", "geode_east", 36.0),
    ]
    for creature_id, name, key, radius in creature_zones:
        x, z = REG.ANCHORS[key]
        marker(build.npc_markers, {
            "id": creature_id, "name": name, "kind": "creature-zone",
            "position": [round(float(x), 2),
                         round(float(t.height_at(x, z)) + 0.05, 2),
                         round(float(z), 2)],
            "radius": radius, "role": "editor-marker", "authority": "server"})

    # harvestables: crystal is the region's resource, scattered over the fields
    surface = build.terrain.surface
    crystal_cells = np.argwhere(surface == TER.CRYSTAL_FIELD)
    if crystal_cells.size:
        picks = rng.choice(len(crystal_cells), size=min(64, len(crystal_cells)),
                           replace=False)
        for index, cell in enumerate(crystal_cells[picks]):
            cz, cx = int(cell[0]), int(cell[1])
            x = float(t.x0 + cx * t.cell)
            z = float(t.z0 + cz * t.cell)
            if not (REG.PLAY_MIN_X <= x <= REG.PLAY_MAX_X
                    and REG.PLAY_MIN_Z <= z <= REG.PLAY_MAX_Z):
                continue
            build.harvestables.append({
                "id": f"amethyst-seam-{index:03d}", "resource": "amethyst-shard",
                "position": [round(x, 2), round(float(t.height_at(x, z)), 2),
                             round(z, 2)],
                "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                               int(round(REG.SERVER_ORIGIN[1] - z))],
                "authority": "server"})


# --------------------------------------------------------------------------
def _split_group(key: str, item) -> tuple[dict[str, M.Mesh], dict[str, M.Mesh]]:
    """Split a landmark into per-material meshes, keeping walkable decks apart."""
    if not hasattr(item, "parts"):
        return {key: item}, {}
    solid = {f"{key}__{material}": piece
             for material, piece in item.by_material(False).items()}
    walk = {f"{key}__walk__{material}": piece
            for material, piece in item.by_material(True).items()}
    return solid, walk


def export_glb(build: REG.RegionBuild, sets, path: Path) -> tuple[GLTF.GltfBuilder, dict]:
    builder = GLTF.GltfBuilder(
        generator="Eloria Amethyst Barrens builder (original procedural assets)")
    MAT.register_gltf_materials(builder, sets, only=set(MATERIALS))
    MAT.register_ground_materials(
        builder, sets,
        {piece.material
         for piece in build.terrain_meshes.values()})

    # Tangents are intentionally omitted: Godot's glTF importer generates them
    # for normal-mapped materials, and shipping them would add sixteen bytes a
    # vertex to a package already dominated by vertex data.
    def prepare(piece: M.Mesh) -> M.Mesh:
        piece.sanitise_normals()
        piece.drop_degenerate()
        piece.weld(1e-4)
        return piece

    exported: dict[str, tuple[list[str], list[str]]] = {}
    for key, item in build.meshes.items():
        solid, walk = _split_group(key, item)
        solid_names, walk_names = [], []
        for name, piece in solid.items():
            if piece.triangle_count == 0:
                continue
            builder.add_mesh(name, prepare(piece), with_tangents=False)
            solid_names.append(name)
        for name, piece in walk.items():
            if piece.triangle_count == 0:
                continue
            builder.add_mesh(name, prepare(piece), with_tangents=False)
            walk_names.append(name)
        exported[key] = (solid_names, walk_names)

    root = GLTF.Node("AmethystBarrens")
    root_index = builder.add_node(root)
    groups = {}
    for group_name in ("Terrain", "Water", "Crystal", "Structures", "Props",
                       "Boundary"):
        groups[group_name] = builder.add_node(GLTF.Node(f"Group_{group_name}"),
                                              root_index)

    for name, piece in build.terrain_meshes.items():
        if piece.triangle_count == 0:
            continue
        builder.add_mesh(name, prepare(piece), with_tangents=False)
        parent = groups["Boundary"] if name.startswith("Backdrop") else groups["Terrain"]
        builder.add_node(GLTF.Node(name, mesh=name), parent)
    for name, piece in build.water_meshes.items():
        if piece.triangle_count == 0:
            continue
        builder.add_mesh(name, prepare(piece), with_tangents=False)
        builder.add_node(GLTF.Node(name, mesh=name), groups["Water"])

    kind_group = {
        "crystal": "Crystal", "shards": "Crystal", "rock": "Crystal",
        "building": "Structures", "landmark": "Structures",
        "interactive": "Structures", "prop": "Props", "scatter": "Props",
    }
    used_names: set[str] = set()

    def unique(name: str) -> str:
        if name not in used_names:
            used_names.add(name)
            return name
        suffix = 2
        while f"{name}_{suffix}" in used_names:
            suffix += 1
        used_names.add(f"{name}_{suffix}")
        return f"{name}_{suffix}"

    for placement in build.placements:
        solid_names, walk_names = exported.get(placement.mesh, ([], []))
        if not solid_names and not walk_names:
            continue
        parent = groups[kind_group.get(placement.kind, "Props")]
        node_name = unique(placement.node)
        placement.node = node_name
        scale = (placement.scale, placement.scale, placement.scale)
        if len(solid_names) == 1 and not walk_names:
            builder.add_node(GLTF.Node(node_name, mesh=solid_names[0],
                                       translation=placement.position,
                                       rotation_y=placement.rotation_y,
                                       scale=scale), parent)
            continue
        container = builder.add_node(
            GLTF.Node(node_name, translation=placement.position,
                      rotation_y=placement.rotation_y, scale=scale), parent)
        for piece_name in solid_names:
            material = piece_name.split("__")[-1]
            builder.add_node(GLTF.Node(unique(f"{node_name}__{material}"),
                                       mesh=piece_name), container)
        for piece_name in walk_names:
            material = piece_name.split("__")[-1]
            # the navigation prefix has to be on the node the client sees
            builder.add_node(GLTF.Node(unique(f"Walk_{node_name}__{material}"),
                                       mesh=piece_name), container)

    size = builder.write_glb(str(path))
    stats = builder.statistics()
    stats["glbBytes"] = size
    stats["instancedTriangles"] = builder.instanced_triangles()
    return builder, stats


# --------------------------------------------------------------------------
COLLISION_CELL = 0.5
# EWCG version the grid is written at, and what the manifest advertises.
COLLISION_FORMAT_VERSION = 2
COLLISION_HEIGHT_STEP = 0.2
COLLISION_HEIGHT_ORIGIN = -2.2
# Levels an ELM height byte holds: the server masks it with 0x3F, so 1..63.
COLLISION_HEIGHT_LEVELS = 63
# Metres of rise per metre travelled that a walker will not climb. Eternal
# Lands allows two 0.2 m stages across a half-metre tile, which is this.
MAX_WALK_GRADIENT = 1.0


def build_collision(build: REG.RegionBuild) -> tuple[bytes, int, int, dict]:
    """Half-metre walkability grid over the server footprint (EWCG version 1)."""
    t = build.terrain
    width = int(round((LANDSCAPE.PLAY_MAX_X - LANDSCAPE.PLAY_MIN_X + REG.METRES_PER_TILE)
                      / COLLISION_CELL))
    height = int(round((LANDSCAPE.PLAY_MAX_Z - LANDSCAPE.PLAY_MIN_Z + REG.METRES_PER_TILE)
                       / COLLISION_CELL))
    width -= width % 6
    height -= height % 6

    # Rows are indexed by server tile Y, which runs north to south, so row 0 is
    # the +Z (southern) edge. Writing the grid the other way round silently
    # mirrors every walkability decision about the map.
    xs = LANDSCAPE.PLAY_MIN_X + (np.arange(width) + 0.5) * COLLISION_CELL
    zs = LANDSCAPE.SERVER_ORIGIN[1] * REG.METRES_PER_TILE \
        - (np.arange(height) + 0.5) * COLLISION_CELL
    gx, gz = np.meshgrid(xs, zs)
    ground = t.height_at(gx, gz)

    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope_grid = np.hypot(gradient_x, gradient_z)
    cx = np.clip(((gx - t.x0) / t.cell).astype(int), 0, t.cols - 1)
    cz = np.clip(((gz - t.z0) / t.cell).astype(int), 0, t.rows - 1)
    slope = slope_grid[cz, cx]

    walkable = (ground > REG.SEA_LEVEL + 0.35) & (slope < 1.05)
    blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if placement.node.startswith('StreamView_'):
            continue
        if not placement.collides:
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        footprint = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2]))) \
            * placement.scale
        factor = 0.30 if placement.kind in ("crystal", "shards") else 0.62
        radius = float((placement.extras or {}).get("solidRadius",
                      min(max(footprint * factor, 0.40), 11.0)))
        px, _, pz = placement.position
        blockers |= (np.hypot(gx - px, gz - pz) < radius)
    walkable &= ~blockers

    surface = ground.copy()
    decks = np.zeros_like(walkable)
    # An overhead walk surface owns its footprint: the client grounds an actor on
    # the highest walk surface below the ray, so a two-level column cannot be
    # expressed on a flat server grid. Bridge decks therefore take the cell, and
    # the ground under them is not separately walkable.
    elevated = 0
    for placement in build.placements:
        if placement.node.startswith('StreamView_'):
            continue
        item = build.meshes[placement.mesh]
        walk_bounds = getattr(item, "walk_bounds", lambda: None)()
        if walk_bounds is None and not placement.walk_surface:
            continue
        if walk_bounds is None:
            low, high = item.bounds()
        else:
            low, high = walk_bounds
        px, py, pz = placement.position
        half_x = float(max(abs(low[0]), abs(high[0]))) * placement.scale
        half_z = float(max(abs(low[2]), abs(high[2]))) * placement.scale
        deck_y = py + float(high[1]) * placement.scale
        # A rotated rectangle, not a circle on the smaller half-extent. A bridge
        # deck is long and narrow, so a circle covers only the middle span and
        # the rest of the deck keeps the gully floor's encoded height - which is
        # exactly what COLLISION_SURFACE_MISMATCH catches.
        cos_r = math.cos(placement.rotation_y)
        sin_r = math.sin(placement.rotation_y)
        dx = gx - px
        dz = gz - pz
        # inverse of mesh.rotation_y: local = R(-theta) . world
        local_x = dx * cos_r - dz * sin_r
        local_z = dx * sin_r + dz * cos_r
        # The deck is claimed to its full extent plus half a cell: trimming it
        # back leaves the last metre of each bridge end encoding the gully floor
        # while the ray overhead still finds the deck.
        footprint = ((np.abs(local_x) <= max(half_x * 0.96, 0.4))
                     & (np.abs(local_z) <= max(half_z * 0.96, 0.4)))
        if not footprint.any():
            continue
        if deck_y > ground.max() + 200.0:
            continue
        elevated += 1
        decks |= footprint
        surface = np.where(footprint, deck_y, surface)
        walkable = np.where(footprint, True, walkable)

    walkable &= ~blockers

    # Steepness has to be part of walkability, not of the height byte. That
    # byte holds 63 steps, and a region with 253 m of relief cannot be encoded
    # finely enough for a two-stage climb limit to mean anything - which is how
    # a mountainside ended up walkable. Measured here on the *composed* surface
    # at the walk grid's own resolution, so a bridge reads as the bridge rather
    # than the gorge under it, unlike the bare-terrain `slope` above.
    rise_z, rise_x = np.gradient(surface, COLLISION_CELL)
    too_steep = np.hypot(rise_x, rise_z) > MAX_WALK_GRADIENT
    # A deck is flat but its rim is a cliff. The package put it there to be
    # walked on, so it keeps its footprint and its own edges do the stopping.
    steep_ground = too_steep & ~decks
    walkable &= ~steep_ground

    # The map's own relief, at the finest step that fits the byte. Clipping to
    # 63 at 0.2 m held 12.4 m and flattened everything above it into one value.
    floor = float(surface[walkable].min()) if walkable.any() else 0.0
    relief = (float(surface[walkable].max()) - floor) if walkable.any() else 0.0
    height_step = max(COLLISION_HEIGHT_STEP,
                      relief / (COLLISION_HEIGHT_LEVELS - 1))
    quantised = np.clip(np.round((surface - floor) / height_step) + 1,
                        1, COLLISION_HEIGHT_LEVELS).astype(np.uint8)
    grid = np.where(walkable, quantised, 0).astype(np.uint8)
    saturated = int(((grid == 63) & walkable).sum())

    payload = struct.pack("<4sHHII", b"EWCG", COLLISION_FORMAT_VERSION, 0,
                          width, height) + grid.tobytes()
    stats = {
        "width": width, "height": height, "cellMetres": COLLISION_CELL,
        "walkableCells": int(walkable.sum()),
        "blockedCells": int((~walkable).sum()),
        "walkableFraction": round(float(walkable.mean()), 4),
        "elevatedDecks": elevated,
        "steepCells": int(steep_ground.sum()),
        "reliefMetres": round(relief, 2),
        "heightEncoding": {"origin": round(floor - height_step, 4),
                           "step": round(height_step, 6),
                           "range": [1, COLLISION_HEIGHT_LEVELS],
                           "zeroMeansBlocked": True},
        "saturatedCells": saturated,
        "saturatedFraction": round(saturated / max(int(walkable.sum()), 1), 4),
        "rowOrder": "server-tile-y (row 0 is the +Z southern edge)",
        "columnOrder": "server-tile-x (column 0 is the -X western edge)",
    }
    return payload, width, height, stats



def snap_to_walkable(build: REG.RegionBuild, payload: bytes, width: int,
                     height: int) -> list[str]:
    """Move any spawn or portal that landed on a blocked cell onto the nearest
    walkable one.

    An interior door sits on the landmark it belongs to, and a landmark that
    collides blocks its own footprint - so the doorway tile can end up inside
    the disc the door is attached to, and the server will not let a player stand
    in it. Rather than special-case the radius per landmark, every spawn and
    portal is checked against the finished collision grid and nudged out.
    """
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)
    walk = grid > 0
    moved: list[str] = []

    def cell_of(x: float, z: float) -> tuple[int, int]:
        cx = int((x - LANDSCAPE.PLAY_MIN_X) / COLLISION_CELL)
        cz = int((LANDSCAPE.SERVER_ORIGIN[1] * REG.METRES_PER_TILE - z) / COLLISION_CELL)
        return cx, cz

    def world_of(cx: int, cz: int) -> tuple[float, float]:
        x = LANDSCAPE.PLAY_MIN_X + (cx + 0.5) * COLLISION_CELL
        z = LANDSCAPE.SERVER_ORIGIN[1] * REG.METRES_PER_TILE - (cz + 0.5) * COLLISION_CELL
        return x, z

    for entry in list(build.spawns) + list(build.portals):
        x, y, z = entry["position"]
        cx, cz = cell_of(x, z)
        if not (0 <= cx < width and 0 <= cz < height):
            continue
        if walk[cz, cx]:
            continue
        best = None
        for radius in range(1, 60):
            lo_z, hi_z = max(cz - radius, 0), min(cz + radius + 1, height)
            lo_x, hi_x = max(cx - radius, 0), min(cx + radius + 1, width)
            window = walk[lo_z:hi_z, lo_x:hi_x]
            if not window.any():
                continue
            zs, xs = np.nonzero(window)
            zs, xs = zs + lo_z, xs + lo_x
            best_index = int(np.argmin((xs - cx) ** 2 + (zs - cz) ** 2))
            best = (int(xs[best_index]), int(zs[best_index]))
            break
        if best is None:
            continue
        nx, nz = world_of(*best)
        entry["position"] = [round(nx, 2), round(float(build.terrain.height_at(nx, nz)) + 0.1, 2),
                             round(nz, 2)]
        entry["serverTile"] = [int(round(nx + LANDSCAPE.SERVER_ORIGIN[0])),
                               int(round(LANDSCAPE.SERVER_ORIGIN[1] - nz))]
        distance = math.hypot(nx - x, nz - z)
        moved.append(f"{entry['id']} moved {distance:.1f} m onto walkable ground")
    return moved


# --------------------------------------------------------------------------
## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def render_minimap(build: REG.RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down capture of the finished geometry."""
    import preview
    from amberwood import render as RENDER
    scene = preview.scene_from_build(build, sets)
    centre_x = (LANDSCAPE.PLAY_MIN_X + LANDSCAPE.PLAY_MAX_X) * 0.5
    centre_z = (LANDSCAPE.PLAY_MIN_Z + LANDSCAPE.PLAY_MAX_Z) * 0.5
    extent = max(LANDSCAPE.PLAY_MAX_X - LANDSCAPE.PLAY_MIN_X, LANDSCAPE.PLAY_MAX_Z - LANDSCAPE.PLAY_MIN_Z)
    if size <= 0:
        size = int(round(extent * MINIMAP_PIXELS_PER_METRE))
    altitude = 900.0
    fov = 2.0 * math.degrees(math.atan((extent * 0.5) / altitude))
    # a cold storm key, matching the region's environment block
    lighting = RENDER.Lighting(sun_direction=(-0.28, 0.92, 0.28),
                               fog_density=0.0, ambient_strength=0.70,
                               shadow_strength=0.40, sun_color=(0.98, 0.92, 1.04))
    image = scene.render(eye=(centre_x, altitude, centre_z + 0.01),
                         target=(centre_x, 0.0, centre_z),
                         width=size, height=size, fov=fov, lighting=lighting,
                         shadows=True, shadow_size=2048,
                         shadow_center=(centre_x, 20.0, centre_z),
                         shadow_radius=extent * 0.62, near=200.0, far=1400.0)
    image.save(path, "WEBP", quality=88, method=5)
    # Every Eloria minimap is drawn at one pixel to the metre, so the image's
    # pixel size is the map's own size in metres and no two maps' cartography
    # is drawn at different densities. The old key spellings are written
    # alongside the new ones for one release; at this scale `metresPerPixel`
    # and `pixelsPerMetre` are the same number anyway.
    min_x, min_z = LANDSCAPE.PLAY_MIN_X, LANDSCAPE.PLAY_MIN_Z
    return {
        "image": path.name,
        "imageSize": [size, size],
        "pixelsPerMetre": MINIMAP_PIXELS_PER_METRE,
        "worldMin": [min_x, min_z],
        "worldMax": [min_x + extent, min_z + extent],
        "northAxis": "-Z",
        "orientation": "north-up",
        "projection": "orthographic-top-down",
        "renderedFrom": "final geometry (offline rasteriser)",
        "transform": {
            "pixelX": {"scale": MINIMAP_PIXELS_PER_METRE,
                       "offset": round(-min_x * MINIMAP_PIXELS_PER_METRE, 4)},
            "pixelY": {"scale": MINIMAP_PIXELS_PER_METRE,
                       "offset": round(-min_z * MINIMAP_PIXELS_PER_METRE, 4)},
            "formula": "pixel_x = world_x * scale + offset;"
                       " pixel_y = world_z * scale + offset",
        },
        "note": ("Every Eloria minimap is drawn at one pixel to the metre, so"
                 " the image's pixel size is the map's size in metres."),
        "file": path.name,
        "pixels": size,
        "size": [size, size],
        "metresPerPixel": round(1.0 / MINIMAP_PIXELS_PER_METRE, 6),
        "centre": [min_x + extent * 0.5, min_z + extent * 0.5],
        "northUp": True,
    }


# --------------------------------------------------------------------------
def write_manifest(build: REG.RegionBuild, stats: dict, collision_stats: dict,
                   minimap: dict, path: Path) -> dict:
    t = build.terrain
    lows, highs = [], []
    for piece in list(build.terrain_meshes.values()) + list(build.water_meshes.values()):
        if piece.triangle_count:
            low, high = piece.bounds()
            lows.append(low)
            highs.append(high)
    for placement in build.placements:
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        offset = np.asarray(placement.position)
        lows.append(low * placement.scale + offset)
        highs.append(high * placement.scale + offset)
    bounds_min = np.vstack(lows).min(axis=0)
    bounds_max = np.vstack(highs).max(axis=0)

    collision_nodes = sorted({p.node for p in build.placements if p.collides})

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": "amethyst_barrens",
            "name": "Amethyst Barrens",
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [round(float(v), 2) for v in bounds_min],
                       "max": [round(float(v), 2) for v in bounds_max]},
            "playableBounds": {
                "min": [LANDSCAPE.PLAY_MIN_X, round(float(t.height.min()), 2), LANDSCAPE.PLAY_MIN_Z],
                "max": [LANDSCAPE.PLAY_MAX_X, round(float(t.height.max()), 2), LANDSCAPE.PLAY_MAX_Z]},
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": LANDSCAPE.SERVER_CELLS,
        },
        "coordinateTransform": {
            "metresPerTile": REG.METRES_PER_TILE,
            "serverOrigin": list(LANDSCAPE.SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": round(float(build.spawns[0]["position"][1]), 2),
            "invertServerY": True,
        },
        "spawnPoints": build.spawns,
        "collision": {
            "nodeNames": collision_nodes,
            "binary": "collision.bin",
            # Both of these describe the file `build_collision` just wrote,
            # so both are taken from it rather than from the constants
            # above, which stopped being true when the grid moved to v2
            # and to an encoding sized from the region's own relief.
            "format": "EWCG-v%d" % COLLISION_FORMAT_VERSION,
            "cellMetres": COLLISION_CELL,
            "width": collision_stats["width"],
            "height": collision_stats["height"],
            "heightEncoding": dict(
                collision_stats["heightEncoding"],
                note="The grid is authoritative for walkability. The "
                     "Godot loader takes elevation from the rendered "
                     "walk surfaces, not from this file."),
            "walkableCells": collision_stats["walkableCells"],
            "walkableFraction": collision_stats["walkableFraction"],
            "saturatedCells": collision_stats["saturatedCells"],
        },
        "contentLayout": LANDSCAPE.content_layout(),
        "streamingBorders": getattr(build, "streaming_borders", []),
        "navigation": {
            "crossings": build.crossings,
            "surfaceNodePrefixes": ["Terrain_", "Walk_"],
            "walkableAreas": ["barrens", "resonant-roads", "paving", "shore",
                              "crystal-fields", "bridges", "stairs"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every built "
                "walkable surface is named Walk_<...>. The client turns both "
                "into the navigation collision layer the grounding ray tests.",
                "Crystal bridge decks are walk surfaces, so a downward grounding "
                "ray under one resolves onto the deck above; the gully or river "
                "beneath them is not separately walkable.",
            ],
        },
        "landmarks": build.landmarks,
        "interactives": build.interactives,
        "npcMarkers": build.npc_markers,
        "harvestables": build.harvestables,
        "portals": build.portals,
        "roads": LANDSCAPE.roads(),
        "water": {
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": LANDSCAPE.SERVER_CELLS,
            "bodies": [{"id": name, "node": name,
                        "type": ("sea" if "Sea" in name
                                 else "stream" if "River" in name else "pool")}
                       for name in build.water_meshes],
            "streams": [{"id": name,
                         "waypoints": [[round(float(p[0]), 1),
                                        round(float(t.height_at(p[0], p[1])), 2),
                                        round(float(p[1]), 1)] for p in points]}
                        for name, points in REG.STREAMS.items()],
        },
        "environment": {
            # A permanent storm over a violet basin: cold blue-grey sky, a low
            # bruised sun, and the crystal supplying most of the colour.
            "sky": {"type": "gradient", "zenith": [0.10, 0.09, 0.16],
                    "horizon": [0.34, 0.30, 0.38]},
            "sun": {"direction": [0.38, -0.42, -0.82],
                    "color": [0.96, 0.88, 1.02], "energy": 0.82},
            "ambient": {"skyColor": [0.20, 0.17, 0.30],
                        "groundColor": [0.10, 0.08, 0.06], "energy": 0.34},
            "saturation": 1.04,
            "fog": {"enabled": True, "color": [0.30, 0.27, 0.36],
                    "density": 0.0011, "heightFalloff": 0.0026},
            "goldenHour": {"sun": {"direction": [0.86, -0.16, -0.48],
                                   "color": [1.35, 0.86, 0.72]},
                           "fog": {"color": [0.52, 0.40, 0.44], "density": 0.0026}},
            "presentation": {
                "stormFlashes": {"enabled": True, "density": 0.7,
                                 "zones": ["massif", "barrens-core"]},
                "crystalGlow": {"enabled": True,
                                "zones": ["massif", "diggings", "roads"]},
                "duststorm": {"enabled": True, "zones": ["barrens-core", "south"]},
                "ambientAudio": [
                    {"id": "storm-distant", "zone": "barrens-core"},
                    {"id": "crystal-resonance", "zone": "massif"},
                    {"id": "surf", "zone": "coast"},
                    {"id": "camp", "zone": "observatory"}],
            },
            "zones": [
                {"id": "barrens-core", "centre": [90.0, 5.0, -30.0], "radius": 220.0},
                {"id": "massif", "centre": [168.0, 30.0, -330.0], "radius": 130.0},
                {"id": "observatory", "centre": [-78.0, 12.0, -204.0], "radius": 96.0},
                {"id": "coast", "centre": [330.0, 2.0, -330.0], "radius": 120.0},
                {"id": "south", "centre": [60.0, 4.0, 120.0], "radius": 140.0},
            ],
        },
        "minimap": minimap,
        "lodGroups": [
            {"id": "crystal", "strategy": "authored-detail-tiers",
             "levels": [{"id": "near", "suffix": "_high"},
                        {"id": "mid", "suffix": "_mid"},
                        {"id": "far", "suffix": "_low"}]}],
        "performance": stats,
        "sources": [
            {"id": "aerial-concept",
             "file": "references/01-concept-aerial-overview.png",
             "role": "authoritative-composition"},
            {"id": "detail-board",
             "file": "references/00-concept-detail-board.png",
             "role": "authoritative-player-scale"},
            {"id": "generator", "file": "source/build_amethyst.py",
             "role": "reproducible-build", "seed": SEED},
        ],
        "provenance": {
            "assets": "original to Eloria/Nymara; generated by _toolkit/amberwood/*",
            "thirdParty": "none",
            "textures": "procedural (numpy + Pillow), no sampled or traced source",
            "geometry": "procedural (numpy), no imported models",
            "license": "same as the Eloria client repository",
        },
        "productionStatus": "production-geometry-materials-population",
        "knownLimitations": [],
    }
    manifest["environment"]["zones"] = LANDSCAPE.PLAN.metadata(manifest["environment"]["zones"])
    manifest["water"]["streams"] = LANDSCAPE.PLAN.metadata(manifest["water"]["streams"])
    posts=HERE/"server-content.json"
    if posts.exists():
        from contentposts import apply
        apply(manifest, PACKAGE, json.loads(posts.read_text()))
    import contentposts
    contentposts.apply_runtime(manifest, HERE.parent)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PACKAGE))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--skip-minimap", action="store_true")
    parser.add_argument("--skip-lod2", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import preview
    sets = preview.texture_sets()

    build = build_region(args.seed)

    t0 = time.time()
    builder, stats = export_glb(build, sets, out / "world.glb")
    print(f"[glb] {stats['glbBytes'] / 1e6:.2f} MB, {stats['nodes']} nodes, "
          f"{stats['uniqueTriangles']} unique tris, "
          f"{stats['instancedTriangles']} instanced tris "
          f"({time.time() - t0:.1f}s)")

    payload, width, height, collision_stats = build_collision(build)
    (out / "collision.bin").write_bytes(payload)
    nudged = snap_to_walkable(build, payload, width, height)
    for line in nudged:
        print(f"[snap] {line}")
    build.notes.extend(nudged)
    print(f"[collision] {width}x{height} cells, "
          f"{collision_stats['walkableFraction'] * 100:.1f}% walkable, "
          f"{collision_stats['saturatedFraction'] * 100:.1f}% saturated")

    minimap = {"file": "minimap.webp"}
    if not args.skip_minimap:
        t0 = time.time()
        minimap = render_minimap(build, sets, out / "minimap.webp")
        print(f"[minimap] rendered in {time.time() - t0:.1f}s")

    used = {name: ts for name, ts in sets.items()
            if name in {MAT.BY_NAME[m].texture for m in MATERIALS if m in MAT.BY_NAME}}
    texture_bytes = sum(sum(len(v) for v in ts.images().values())
                        for ts in used.values())
    stats["embeddedTextureBytes"] = texture_bytes
    stats["textureMemoryBytesUncompressed"] = sum(
        ts.base_color.shape[0] * ts.base_color.shape[1] * 4 * 3 for ts in used.values())
    stats["placements"] = len(build.placements)
    stats["collision"] = collision_stats
    stats["notes"] = build.notes

    manifest = write_manifest(build, stats, collision_stats, minimap,
                              out / "world.json")
    print(f"[manifest] {len(manifest['landmarks'])} landmarks, "
          f"{len(manifest['interactives'])} interactives, "
          f"{len(manifest['harvestables'])} harvestables, "
          f"{len(manifest['portals'])} portals")

    report = validate_gltf.validate(str(out / "world.glb"))
    payload = report.to_dict()
    (out / "world.glb.validator.json").write_text(json.dumps(payload, indent=2) + "\n")
    counts = payload["issues"]
    print(f"[validate] errors={counts['numErrors']} warnings={counts['numWarnings']} "
          f"infos={counts['numInfos']}")
    for message in report.messages:
        if message["severity"] <= 1:
            print("   ", message["code"], message["message"], message["pointer"])

    if not args.skip_lod2:
        t0 = time.time()
        lod_sets = {name: texture_set.reduced() for name, texture_set in sets.items()}
        lod_build = build_region(args.seed, lod="far")
        _, lod_stats = export_glb(lod_build, lod_sets, out / "world-lod2.glb")
        stats["lod2"] = {
            "glbBytes": lod_stats["glbBytes"],
            "nodes": lod_stats["nodes"],
            "uniqueTriangles": lod_stats["uniqueTriangles"],
            "instancedTriangles": lod_stats["instancedTriangles"],
        }
        print(f"[lod2] {lod_stats['glbBytes'] / 1e6:.2f} MB, "
              f"{lod_stats['instancedTriangles']} instanced tris "
              f"({time.time() - t0:.1f}s)")
        lod_report = validate_gltf.validate(str(out / "world-lod2.glb"))
        (out / "world-lod2.glb.validator.json").write_text(
            json.dumps(lod_report.to_dict(), indent=2) + "\n")
        write_manifest(build, stats, collision_stats, minimap, out / "world.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
