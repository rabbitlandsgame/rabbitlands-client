#!/usr/bin/env python3
"""Build the Crownwater runtime map package.

Outputs, next to this source tree:

    ../world.glb        self-contained glTF 2.0 (geometry, materials, textures)
    ../world.json       GLB world manifest, schema version 1
    ../collision.bin    half-metre walkability grid (EWCG v1)
    ../minimap.webp     minimap rendered from the final geometry
    ../world.glb.validator.json
    ../performance-summary.md

Deterministic: the same seed reproduces the same bytes.
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
from amberwood import noise as N
from amberwood import render as RENDER

from amberwood import terrain as TER
from amberwood import routecraft as RC

import crownkit as CK
import populate as POP
import coastal_plan as COAST
import coastal_population as COAST_POP
import streaming_borders as SB
import region as REG
import transitions as MARCH
import secretdoors as SD
import secrets_design as SEC
import loresites as LORE

register_materials = CK.register

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
SEED = 20260827
# Class islands smaller than this are given to whatever surrounds them. Six
# two-metre cells is 24 m2 - smaller than any surface a player is meant to read
# as its own thing, and larger than every crumb the thresholded noise and the
# boundary dither leave behind.
DESPECKLE_MIN_CELLS = 6

ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# Crownwater is the lake's ferry hub: every quay is a boat, and the four outer
# quays between them serve seven routes. A quay that serves two routes carries
# a second portal tile a few metres along the dock, so the boat to Mirrorhold
# and the boat to the Barrens leave from the same north quay without sharing a
# tile. region-connections.json names the second tiles with a suffix.
CROSSINGS = [
    MARCH.Crossing("east-quay", "four_gates", REG.ANCHORS["outer_east"],
                   (REG.PLAY_MAX_X + 20.0, REG.ANCHORS["outer_east"][1]),
                   radius=28.0, name="The Causeway Quay", station_position=(203, -35)),
    MARCH.Crossing("north-quay", "mirrorhold", REG.ANCHORS["outer_north"],
                   (REG.ANCHORS["outer_north"][0], REG.PLAY_MIN_Z - 20.0),
                   radius=28.0, ferry=True, name="The North Quay", station_position=(142, -237)),
    MARCH.Crossing("west-quay", "westhaven", REG.ANCHORS["outer_west"],
                   (REG.PLAY_MIN_X - 20.0, REG.ANCHORS["outer_west"][1]),
                   radius=28.0, ferry=True, name="The West Quay", station_position=(-86, -150)),
    MARCH.Crossing("south-quay", "manymouth_delta", REG.ANCHORS["outer_south"],
                   (REG.ANCHORS["outer_south"][0], REG.PLAY_MAX_Z + 20.0),
                   radius=28.0, ferry=True, name="The South Quay", station_position=(16, 91)),
]

# The places the region's people argue about (see loresites.py).
SITES = [
    LORE.Site("court-grating", "The Open Grating", "drowned_grating", (86.0, -122.0),
              thread="D", clearing=9.0,
              note="The grating over the drowned court, found thrown back on its hinge. "
                   "The diver's rope and weights are still on the kerb."),
]
# (quay portal id, second portal id, destination, name)
SECOND_BERTHS = (
    ("north-quay", "north-quay-east", "amethyst_barrens", "Barrens Packet"),
    ("west-quay", "west-quay-south", "grey_moors", "Moor Jetty Packet"),
    ("south-quay", "south-quay-east", "ssarathi_ruins", "Temple Boat"),
)
MARCH_MATERIALS: dict = dict(getattr(REG, "SURFACE_MATERIALS", {}))
CK.MATERIALS = CK.MATERIALS | SB.materials_for("crownwater") | MARCH.materials_for("crownwater", CROSSINGS) | SD.materials(SEC) | LORE.materials([s.piece for s in SITES])


# --------------------------------------------------------------------------
def build_region(seed: int = SEED, lod: str | None = None) -> REG.RegionBuild:
    """Build the region. `lod="far"` produces the reduced second package:
    far-tier vegetation only and no ground clutter, for low-end machines and for
    distant streaming."""
    t0 = time.time()
    terrain = REG.build_terrain(seed)
    REG.apply_built_ground(terrain, seed)
    build = REG.RegionBuild(terrain=terrain)
    # Ferry decks are explicitly surveyed; no generic station plateau.

    LORE.prepare(terrain, SITES, sea_level=getattr(REG, "SEA_LEVEL", 0.0))

    POP.build_water(build, lod=lod)
    POP.populate_causeways(build, seed)
    POP.populate_crown_isle(build, seed)
    POP.populate_pavilions(build, seed)
    POP.populate_harbour(build, seed)
    POP.populate_sunken_court(build, seed)
    COAST_POP.populate(build, seed)
    POP.populate_vegetation(build, seed, lod=lod)
    if lod is None:
        POP.populate_props(build, seed)
    POP.populate_metadata(build, seed)

    # The marches: the neighbours' country coming in along the roads out.
    # Open-water approaches retain the local lagoon palette.

    march = MARCH.dress(build, "crownwater", [], seed, sea_level=REG.SEA_LEVEL)
    LORE.dress(build, terrain, SITES, seed)
    SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
    build.landmarks.extend(march.landmarks)
    build.notes.extend(march.notes)

    RC.clear_walk_corridors(build, [[[x,0,z] for x,z in points]
                             for points in REG.CIVIC_PATHS.values()],
                            {"tree":4.5,"foliage":3.0})
    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.28, blend_edges=True, material_suffix=MAT.GROUND_SUFFIX,
        materials=MARCH_MATERIALS)
    # No landmass backdrop. Amberwood needs one because its mountain walls have
    # to stand in front of something; Crownwater's horizon is open water, and the
    # lagoon plane is already cut far outside the authored terrain to supply it.
    build.resolve_names()
    _add_spawns_and_portals(build)
    _add_population_markers(build, seed)
    SB.apply(build, "crownwater")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    connector_finish.apply(build, 'crownwater')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_color'))
    import terrain_paint
    terrain_paint.apply(build, 'crownwater')
    for item in build.interactives:
        if item.get("id") in COAST.SECRET_STANDING_TILES:
            item["serverTile"]=COAST.SECRET_STANDING_TILES[item["id"]]
    print(f"[region] built in {time.time() - t0:.1f}s")
    return build


def _add_spawns_and_portals(build: REG.RegionBuild) -> None:
    t = build.terrain
    # The default spawn is the harbour islet, not the cathedral plaza. Arriving
    # on the far side of the water is the whole framing of detail-board panel 1:
    # you see the crowned island across the lagoon before you can reach it.
    for spawn_id, (x, z), facing in (
            ("default", REG.SPAWN, math.radians(45.0)),
            ("crown-plaza", REG.SPAWN_PLAZA, math.pi),
            ("garden-isle", REG.SPAWN_GARDEN, 0.0)):
        y = float(t.height_at(x, z))
        build.spawns.append({
            "id": spawn_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})

    # Edge portals to the neighbouring Nymara regions. Destination map ids follow
    # the client registry; the server remains authoritative for the transition.
    # Crownwater's are quays rather than roads - every land route out of an
    # archipelago is a boat.
    for portal_id,name,destination in (
        ("north-quay","Mirrorhold Packet","mirrorhold"),
        ("north-quay-east","Barrens Packet","amethyst_barrens"),
        ("west-quay","Westhaven Packet","westhaven"),
        ("west-quay-south","Moor Jetty Packet","grey_moors"),
        ("south-quay","Delta Packet","manymouth_delta"),
        ("south-quay-east","Temple Boat","ssarathi_ruins"),
        ("east-quay","Four Gates Causeway","four_gates")):
        if portal_id=="east-quay": x,y,z=271.5,4.0,-10.5
        else:
            (x,z),_,y=COAST.FERRIES[portal_id]
        build.portals.append({"id":portal_id,"name":name,"type":"map-transition",
            "position":[x,y,z],"serverTile":[math.floor(x+120),math.floor(120-z)],
            "destinationMap":destination,"radius":2.0,"authority":"server",
            "travelMode":"causeway" if portal_id=="east-quay" else "ferry"})

    # Interior entrances. Each sits on the landmark it belongs to, so the door a
    # player walks into is the building they were looking at; the interior
    # package carries the matching return portal.
    for portal_id, name, landmark_id, destination, spawn in (
            # All four lead to the SAME map. Crownwater's insides share one
            # map with blackspace between them, as Eternal Lands lays out a
            # region's interiors and as amethyst_barrens_insides already does
            # here, so the destination is one elm and the section is chosen by
            # the spawn id.
            ("basilica-undercroft", "The Drowned Crown", "crownwater-cathedral",
             "drowned_crown", "basilica-undercroft"),
            ("campanile-door", "The Tide Campanile", "crownwater-campanile",
             "drowned_crown", "campanile-door"),
            ("cistern-stair", "The Tide Cistern",
             "crownwater-pavilion-pavilion_west",
             "drowned_crown", "cistern-stair"),
            ("customs-door", "The Harbour Customs Hall",
             "crownwater-customs-hall",
             "drowned_crown", "customs-door"),
             ("eleventh-bell-door", "The Eleventh Bell",
             "crownwater-pavilion-pavilion_northeast", "drowned_crown", "eleventh-bell-door"),
            ("case-room-door", "The Case Room",
             "crownwater-pavilion-pavilion_east", "drowned_crown", "case-room-door"),
            ("grating-mouth", "The Grating",
             "crownwater-pavilion-pavilion_south", "drowned_crown", "grating-mouth"),
):
        anchor = next((l for l in build.landmarks if l.get("id") == landmark_id),
                      None)
        if anchor is None:
            continue
        x, y, z = anchor["position"]
        if portal_id in REG.DOORS:
            x,z = REG.DOORS[portal_id]
            y = float(t.height_at(x,z))
            if portal_id == "customs-door":
                y = float(t.height_at(7,8)) + (x-7)/5 * (float(t.height_at(23,8))+1.4-float(t.height_at(7,8)))
        build.portals.append({
            "id": portal_id, "name": name, "type": "interior-entrance",
            "position": [round(float(x), 2), round(float(y) + 0.1, 2),
                         round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "landmark": landmark_id,
            "destinationMap": destination, "destinationSpawn": spawn,
            "radius": 2.5, "authority": "server"})


def _add_population_markers(build: REG.RegionBuild, seed: int) -> None:
    """Editor/visual markers only - the server owns actual spawning."""
    t = build.terrain
    rng = N.Rng(seed + 777)

    npc_plan = [
        ("crownwater-harbourmaster", "Harbour Master", "harbour_quay", 5.0),
        ("crownwater-ferryman", "Lagoon Ferryman", "harbour_isle", 6.0),
        ("crownwater-market-trader", "Quayside Trader", "harbour_market", 5.0),
        ("crownwater-cathedral-warden", "Warden of the Crown", "cathedral", 8.0),
        ("crownwater-plaza-herald", "Plaza Herald", "crown_plaza", 7.0),
        ("crownwater-garden-keeper", "Garden Keeper", "garden_fountain", 5.0),
        ("crownwater-bell-ringer", "Campanile Bell-Ringer", "crown_campanile", 4.0),
        ("crownwater-quay-steward", "Crown Quay Steward", "crown_quay_south", 5.0),
        ("crownwater-lamplighter", "Lamplighter", "harbour_lamp_walk", 6.0),
        ("crownwater-watchman", "Outer Watchman", "watch_tower", 4.0),
        ("crownwater-lightkeeper", "Lightkeeper", "lighthouse", 4.0),
        ("crownwater-diver", "Court Diver", "pavilion_west", 6.0),
    ]
    for npc_id, label, anchor, radius in npc_plan:
        centre = REG.ANCHORS[anchor]
        angle = float(rng.uniform(0, math.pi * 2))
        x = centre[0] + math.cos(angle) * radius
        z = centre[1] + math.sin(angle) * radius
        y = float(t.height_at(x, z))
        build.npc_markers.append({
            "id": npc_id, "name": label, "type": "npc",
            "position": [round(x, 2), round(y, 2), round(z, 2)],
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
        generator="Eloria Crownwater builder (original procedural assets)")
    # Fail loudly and early if a kit piece introduces a material the pin does
    # not cover. Without this the first sign of trouble is a KeyError from deep
    # inside the GLB writer, naming a merged sub-mesh rather than the piece that
    # actually pulled the material in.
    used = set()
    for item in list(build.meshes.values()):
        for piece in (getattr(item, "all_parts", None) or [item]):
            used.add(piece.material)
    for table in (build.terrain_meshes, build.water_meshes):
        for piece in table.values():
            used.add(piece.material)
    unpinned = sorted({MAT.base_material(name) for name in used}
                      - CK.MATERIALS)
    if unpinned:
        raise SystemExit(
            "materials used but not in crownkit.MATERIALS: "
            + ", ".join(unpinned))
    # The other direction is not an error but it is not free either: every
    # pinned material embeds its textures whether or not a mesh references it.
    # Amberwood's pin carries six such and pays 2.79 MB for them.
    # Read through the ground copies here too: a material the terrain
    # now draws with an alpha-tested copy is still referenced, and
    # calling it dead weight would invite trimming a pin the copy
    # depends on.
    unused = sorted(CK.MATERIALS
                    - {MAT.base_material(name) for name in used})
    if unused:
        print("[materials] WARNING pinned but unreferenced, costing bytes: "
              + ", ".join(unused))

    # Pinned by name to the materials Crownwater actually uses. Without `only=`
    # the package embeds the whole shared library - about ten megabytes of forest
    # and burnt-country textures this region never references - and, worse, its
    # contents would change whenever another region appends to the shared table.
    MAT.register_gltf_materials(builder, sets, only=CK.MATERIALS)
    MAT.register_ground_materials(
        builder, sets,
        {piece.material
         for piece in build.terrain_meshes.values()})

    # Tangents are intentionally omitted: Godot's glTF importer generates them
    # for normal-mapped materials, and shipping them would add sixteen bytes a
    # vertex to a package that is already dominated by vertex data.
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

    root = GLTF.Node("Crownwater")
    root_index = builder.add_node(root)
    groups = {}
    for group_name in ("Terrain", "Water", "Forest", "Structures", "Props",
                       "Boundary"):
        groups[group_name] = builder.add_node(GLTF.Node(f"Group_{group_name}"),
                                              root_index)

    # -- terrain and water ------------------------------------------------
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

    # -- placements --------------------------------------------------------
    kind_group = {
        "tree": "Forest", "foliage": "Forest", "undergrowth": "Forest",
        "leafdrift": "Forest", "mushrooms": "Forest", "fallenlog": "Forest",
        "stump": "Forest", "rock": "Forest",
        "building": "Structures", "landmark": "Structures",
        "interactive": "Structures", "prop": "Props",
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
COLLISION_HEIGHT_LEVELS = 255
# Metres of rise per metre travelled that a walker will not climb. Eternal
# Lands allows two 0.2 m stages across a half-metre tile, which is this.
MAX_WALK_GRADIENT = 1.0


def build_collision(build: REG.RegionBuild) -> tuple[bytes, int, int, dict]:
    """Half-metre walkability grid over the server footprint (EWCG version 1)."""
    t = build.terrain
    width = int(round((REG.PLAY_MAX_X - REG.PLAY_MIN_X + REG.METRES_PER_TILE)
                      / COLLISION_CELL))
    height = int(round((REG.PLAY_MAX_Z - REG.PLAY_MIN_Z + REG.METRES_PER_TILE)
                       / COLLISION_CELL))
    width -= width % 6
    height -= height % 6

    # Rows are indexed by server tile Y, which runs north to south, so row 0 is
    # the +Z (southern) edge. Writing the grid the other way round silently
    # mirrors every walkability decision about the map.
    xs = REG.PLAY_MIN_X + (np.arange(width) + 0.5) * COLLISION_CELL
    zs = REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE \
        - (np.arange(height) + 0.5) * COLLISION_CELL
    gx, gz = np.meshgrid(xs, zs)
    ground = t.height_at(gx, gz)

    gradient_z, gradient_x = np.gradient(t.height, t.cell)
    slope_grid = np.hypot(gradient_x, gradient_z)
    cx = np.clip(((gx - t.x0) / t.cell).astype(int), 0, t.cols - 1)
    cz = np.clip(((gz - t.z0) / t.cell).astype(int), 0, t.rows - 1)
    slope = slope_grid[cz, cx]

    walkable = (ground > REG.SEA_LEVEL + 0.35) & (slope < 1.05)
    # solid structures block their footprint
    blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if placement.node.startswith(SB.VIEW_PREFIX):continue
        if not placement.collides:
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        if (placement.kind == "building"
                or placement.node.startswith("Landmark_Retaining_")
                or placement.node == "Landmark_cistern-yard"
                or placement.node in ("Landmark_Cathedral","Landmark_CustomsHouse")):
            dx=gx-placement.position[0];dz=gz-placement.position[2]
            co,si=math.cos(placement.rotation_y),math.sin(placement.rotation_y)
            lx=(dx*co-dz*si)/placement.scale;lz=(dx*si+dz*co)/placement.scale
            blockers |= ((lx>low[0]-.2)&(lx<high[0]+.2)&
                         (lz>low[2]-.2)&(lz<high[2]+.2))
            continue
        # trees block only their trunk, not the spread of their canopy
        footprint = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2]))) \
            * placement.scale
        factor = 0.16 if placement.kind in ("tree", "foliage") else 0.62
        radius = min(max(footprint * factor, 0.40), 11.0)
        px, _, pz = placement.position
        blockers |= (np.hypot(gx - px, gz - pz) < radius)
    walkable &= ~blockers

    surface = ground.copy()
    decks = np.zeros_like(walkable)
    # An overhead walk surface owns its footprint: the client grounds an actor
    # on the highest walk surface below the ray, so a two-level column cannot be
    # expressed on a flat server grid. Bridges, decks and platforms therefore
    # take the cell, and the ground under them is not separately walkable.
    # Rasterise the walking triangles, including station heights and bends.
    # A bounds disc on a long bridge can open lakebed metres away from it.
    import glb_reader as GLB
    triangles = []
    elevated = 0
    for name,mesh in build.terrain_meshes.items():
        if name.startswith("Walk_") and not name.startswith(SB.VIEW_PREFIX):
            triangles.append(mesh.positions[mesh.indices.reshape(-1,3)])
            elevated += 1
    for placement in build.placements:
        if placement.node.startswith(SB.VIEW_PREFIX):continue
        item = build.meshes[placement.mesh]
        parts = list(getattr(item, "walk_parts", []))
        if placement.walk_surface and not parts:
            parts = [item] if isinstance(item, M.Mesh) else list(item.parts)
        if not parts:
            continue
        matrix = (M.translation(*placement.position) @ M.rotation_y(placement.rotation_y)
                  @ M.scaling(placement.scale))
        for part in parts:
            mesh = part.transformed(matrix)
            triangles.append(mesh.positions[mesh.indices.reshape(-1, 3)])
        elevated += 1
    if triangles:
        decks, deck_y = GLB.rasterise(np.concatenate(triangles), width, height,
                                     REG.PLAY_MIN_X, REG.SERVER_ORIGIN[1], COLLISION_CELL)
        # A bank can rise above the end of a bridge. The client's grounding
        # ray chooses the highest surface; a buried deck must not create a
        # false cliff in the raw steepness mask before refinement runs.
        surface = np.where(decks, np.maximum(deck_y, surface), surface)
        decks &= deck_y >= ground - 0.03
        walkable |= decks

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
        "rowOrder": "server-tile-y (row 0 is the +Z southern edge)",
        "columnOrder": "server-tile-x (column 0 is the -X western edge)",
    }
    return payload, width, height, stats


# --------------------------------------------------------------------------
## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def render_minimap(build: REG.RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down orthographic-ish capture of the finished geometry."""
    import preview
    from copy import copy
    overview=copy(build)
    overview.placements=[p for p in build.placements if not p.node.startswith(SB.VIEW_PREFIX)]
    overview.terrain_meshes={k:v for k,v in build.terrain_meshes.items() if not k.startswith(SB.VIEW_PREFIX)}
    overview.water_meshes={k:v for k,v in build.water_meshes.items() if not k.startswith(SB.VIEW_PREFIX)}
    scene = preview.scene_from_build(overview, sets)
    centre_x = (REG.PLAY_MIN_X + REG.PLAY_MAX_X) * 0.5
    centre_z = (REG.PLAY_MIN_Z + REG.PLAY_MAX_Z) * 0.5
    extent = max(REG.PLAY_MAX_X - REG.PLAY_MIN_X, REG.PLAY_MAX_Z - REG.PLAY_MIN_Z)
    if size <= 0:
        size = int(round(extent * MINIMAP_PIXELS_PER_METRE))
    altitude = 900.0
    fov = 2.0 * math.degrees(math.atan((extent * 0.5) / altitude))
    lighting = RENDER.Lighting(sun_direction=(-0.30, 0.90, 0.32),
                               fog_density=0.0, ambient_strength=0.72,
                               shadow_strength=0.35, sun_color=(1.10, 0.96, 0.74))
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
    min_x, min_z = REG.PLAY_MIN_X, REG.PLAY_MIN_Z
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
def write_camera_views(build: REG.RegionBuild, path: Path) -> dict:
    """Emit the Godot capture harness's view table from `source/views.py`.

    The offline renderer and the in-client harness must frame the same shots or
    the comparison sheets compare two different things. `views.py` is the single
    source of truth; this converts its design-space, ground-relative entries
    into the absolute world positions Godot wants, using the terrain that was
    actually built.
    """
    import views as VIEWTABLE

    t = build.terrain

    # Solid world-space boxes the camera must not end up inside or underneath.
    # Blind design-space framings put seven of the first twenty-three cameras
    # under a causeway deck or inside a quay wall: the causeways radiate from
    # the centre along the same diagonals a hand-picked viewpoint tends to fall
    # on. Checking is cheaper and more reliable than guessing.
    boxes = []
    for placement in build.placements:
        if placement.kind not in ("landmark", "building"):
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        angle = float(placement.rotation_y or 0.0)
        cosine, sine = math.cos(angle), math.sin(angle)
        corners = []
        for lx in (low[0], high[0]):
            for lz in (low[2], high[2]):
                corners.append((cosine * lx + sine * lz, -sine * lx + cosine * lz))
        xs = [c[0] * placement.scale + placement.position[0] for c in corners]
        zs = [c[1] * placement.scale + placement.position[2] for c in corners]
        boxes.append((min(xs), max(xs), min(zs), max(zs),
                      placement.position[1] + float(low[1]) * placement.scale,
                      placement.position[1] + float(high[1]) * placement.scale))

    # Walk-deck boxes, for cameras that stand on a causeway rather than on ground.
    decks = []
    for placement in build.placements:
        item = build.meshes[placement.mesh]
        bounds = getattr(item, "walk_bounds", lambda: None)()
        if bounds is None:
            continue
        low, high = bounds
        angle = float(placement.rotation_y or 0.0)
        cosine, sine = math.cos(angle), math.sin(angle)
        corners = []
        for lx in (low[0], high[0]):
            for lz in (low[2], high[2]):
                corners.append((cosine * lx + sine * lz, -sine * lx + cosine * lz))
        xs = [c[0] * placement.scale + placement.position[0] for c in corners]
        zs = [c[1] * placement.scale + placement.position[2] for c in corners]
        decks.append((min(xs), max(xs), min(zs), max(zs),
                      placement.position[1] + float(low[1]) * placement.scale,
                      placement.position[1] + float(high[1]) * placement.scale))

    def clear_eye(x, y, z):
        """Lift a camera that sits inside, or directly under, solid geometry."""
        for x0, x1, z0, z1, y0, y1 in boxes:
            if not (x0 - 1.2 <= x <= x1 + 1.2 and z0 - 1.2 <= z <= z1 + 1.2):
                continue
            if y <= y1 + 1.6:
                y = y1 + 2.4
        return y

    import glb_reader as GLB
    from verify_runtime import VerticalRayIndex
    doc,body = GLB.load(path.parent / "world.glb")
    deck_index = VerticalRayIndex(GLB.triangles(doc,body,GLB.named(doc,"Walk_")),cell=4)
    entries = []
    for (name, panel, eye_xz, eye_h, target_xz, target_h, fov, _size,
         _radius, mode) in VIEWTABLE.VIEWS:
        fixed = mode.endswith("!")
        mode = mode.rstrip("!")
        ex, ez = eye_xz[0] * REG.SCALE, eye_xz[1] * REG.SCALE
        tx, tz = target_xz[0] * REG.SCALE, target_xz[1] * REG.SCALE
        ey = float(t.height_at(ex, ez)) + eye_h
        ty = float(t.height_at(tx, tz)) + target_h
        # a camera below the waterline sees nothing but the water plane's
        # underside; lift any eye that the terrain put under the lagoon
        if mode == "deck":
            # Stand on a causeway deck the way the client grounds an actor:
            # snap to the highest walk surface under the eye, then add eye
            # height. A ground-relative height cannot express this - the ground
            # under a causeway is sometimes the lagoon floor at -6.6 and
            # sometimes an island shelf at -1.3, and the same declared height
            # therefore lands 1.7 m above the deck in one place and 7 m above it
            # in another. Two attempts at panel 4 failed exactly that way.
            deck = deck_index.top_hit(ex,ez)
            target_deck = deck_index.top_hit(tx,tz)
            if deck is None:
                raise ValueError(f"{name}: no walking surface under deck camera")
            ey = deck + eye_h
            ty = (deck if target_deck is None else target_deck) + target_h
        elif mode != "submerged":
            ey = max(ey, REG.SEA_LEVEL + 0.6)
            if not fixed:
                ey = clear_eye(ex, ey, ez)
        entries.append({
            "id": name,
            "panel": panel if isinstance(panel, int) else None,
            "position": [round(ex, 2), round(ey, 2), round(ez, 2)],
            "target": [round(tx, 2), round(ty, 2), round(tz, 2)],
            "fov": float(fov),
            "golden": mode == "golden",
            "note": (VIEWTABLE.PANELS[panel][1]
                     if isinstance(panel, int) else name.replace("-", " ")),
        })
    payload = {"schemaVersion": "1.0.0", "views": entries}
    path.write_text(json.dumps(payload, indent=2) + chr(10), encoding="utf-8")
    return payload


# --------------------------------------------------------------------------
def write_manifest(build: REG.RegionBuild, stats: dict, collision_stats: dict,
                   minimap: dict, path: Path) -> dict:
    t = build.terrain
    lows = []
    highs = []
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

    surface_prefixes = ["Terrain_", "Walk_"]
    collision_nodes = sorted({p.node for p in build.placements if p.collides})

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": "crownwater",
            "name": "Crownwater",
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [round(float(v), 2) for v in bounds_min],
                       "max": [round(float(v), 2) for v in bounds_max]},
            "playableBounds": {
                "min": [REG.PLAY_MIN_X, round(float(t.height.min()), 2), REG.PLAY_MIN_Z],
                "max": [REG.PLAY_MAX_X, round(float(t.height.max()), 2), REG.PLAY_MAX_Z]},
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": REG.SERVER_CELLS,
        },
        "coordinateTransform": {
            "metresPerTile": REG.METRES_PER_TILE,
            "serverOrigin": list(REG.SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": round(float(t.height_at(*REG.SPAWN)), 2),
            "invertServerY": True,
        },
        "spawnPoints": build.spawns,
        "streamingBorders": build.streaming_borders,
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
        },
        "contentLayout": REG.CONTENT_LAYOUT,
        "navigation": {
            "crossings": [{"id":c["id"],"endpoints":RC.crossing_endpoints(c["endpoints"])}
                          for c in build.crossings],
            "surfaceNodePrefixes": surface_prefixes,
            "walkableAreas": ["paving", "shore", "meadow", "causeways", "quays",
                              "stairs", "pavilion-decks"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every built "
                "walkable surface is named Walk_<...>. The client turns both "
                "into the navigation collision layer the grounding ray tests.",
                "Causeway decks and quays are walk surfaces, so a downward "
                "grounding ray under one resolves onto the deck above; the "
                "lagoon beneath them is water and is not walkable.",
                "The lagoon floor is terrain and carries the Terrain_ prefix "
                "everywhere, including below sea level. That is deliberate: the "
                "client casts its grounding ray at every server tile, not only "
                "walkable ones, so a region that is mostly water still needs a "
                "continuous surface underneath it. Those tiles ground "
                "successfully and are marked unwalkable in collision.bin.",
            ],
        },
        "landmarks": build.landmarks,
        "interactives": build.interactives,
        "npcMarkers": build.npc_markers,
        "harvestables": build.harvestables,
        "portals": build.portals,
        # Crownwater has no roads in the Amberwood sense. Its routes are stone
        # causeways over open water, so their waypoint heights come from the
        # deck, not from the lagoon floor the span crosses.
        "roads": [{"id": name, "type": "causeway",
                   "waypoints": [[round(float(p[0]), 1),
                                  round(REG.causeway_deck_level(t, name), 2),
                                  round(float(p[1]), 1)] for p in points]}
                  for name, points in REG.CAUSEWAYS.items()] + [
                      {"id":name,"type":"promenade","waypoints":[[x,round(float(t.height_at(x,z)),2),z] for x,z in points]}
                      for name,points in REG.CIVIC_PATHS.items()],
        "water": {
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": REG.SERVER_CELLS,
            "bodies": [{"id": name, "node": name,
                        "type": "lagoon" if "Lagoon" in name else "pool"}
                       for name in build.water_meshes],
            # One body of water, no watercourses: an archipelago has no streams.
            "streams": [],
            "channels": [{"id": "moat", "type": "navigable",
                          "note": "the ring of deep water around the crown isle"},
                         {"id": "approach-southwest", "type": "navigable"},
                         {"id": "approach-southeast", "type": "navigable"}],
        },
        "environment": {
            # Tuned to the concept: a high bright sky, a strong near-vertical
            # sun that drives the turquoise out of shallow water, and very
            # little fog - the painting's distances stay clear and saturated.
            "sky": {"type": "gradient", "zenith": [0.16, 0.42, 0.72],
                    "horizon": [0.72, 0.87, 0.92], "curve": 0.14,
                    "groundHorizon": [0.42, 0.62, 0.66],
                    "groundBottom": [0.16, 0.30, 0.38],
                    "sunAngleMax": 14.0, "energy": 1.16},
            # `direction` is the direction the light TRAVELS, not the direction
            # of the sun in the sky: the binder does
            # `sun.look_at_from_position(ZERO, direction)`, and a
            # DirectionalLight3D emits along its local -Z. A +Y component
            # therefore lights the world from underneath. The first in-client
            # capture of this region came back lit from below and reading as
            # night; Amberwood's manifest still declares +Y and has never been
            # rendered through this path.
            "sun": {"direction": [-0.30, -0.84, 0.45],
                    "color": [1.12, 1.05, 0.95], "energy": 1.08,
                    "indirectEnergy": 1.15, "angularDiameterDegrees": 1.2},
            "ambient": {"color": [0.52, 0.68, 0.78], "energy": 0.52,
                        "skyContribution": 0.75},
            "saturation": 1.34,
            "fog": {"enabled": True, "color": [0.62, 0.80, 0.86],
                    "density": 0.00035, "heightFalloff": 0.0022},
            "variants": {
                "golden-hour": {
                    "sun": {"direction": [-0.80, -0.26, 0.54],
                            "color": [1.52, 1.02, 0.62], "energy": 1.25},
                    "fog": {"enabled": True, "color": [0.78, 0.66, 0.52],
                            "density": 0.0016},
                },
            },
            "water": {
                "shallowColor": [0.24, 0.74, 0.74],
                "deepColor": [0.04, 0.24, 0.44],
                "causticsEnabled": True,
                "note": ("Shallow/deep tint and caustics are presentation "
                         "settings for whoever writes the water shader; the "
                         "GLB ships a flat lit plane."),
            },
            "presentation": {
                "gulls": {"enabled": True, "density": 0.5,
                          "zones": ["open-lagoon", "harbour"]},
                "mist": {"enabled": False},
                "spray": {"enabled": True, "zones": ["reef"]},
                "bannerWind": {"enabled": True, "strength": 0.45},
                "ambientAudio": [
                    {"id": "lagoon-lap", "zone": "open-lagoon"},
                    {"id": "harbour", "zone": "harbour"},
                    {"id": "crowd-plaza", "zone": "crown-isle"},
                    {"id": "gulls", "zone": "reef"}],
            },
            "zones": [
                {"id": "crown-isle", "centre": [114.0, 12.0, -114.0], "radius": 108.0},
                {"id": "harbour", "centre": [0.0, 8.0, 0.0], "radius": 64.0},
                {"id": "open-lagoon", "centre": [114.0, 0.0, -114.0], "radius": 280.0},
                {"id": "reef", "centre": [114.0, 0.0, -114.0], "radius": 400.0},
            ],
        },
        "minimap": minimap,
        "lodGroups": [
            {"id": "vegetation", "strategy": "authored-detail-tiers",
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
            {"id": "generator", "file": "source/build_crownwater.py",
             "role": "reproducible-build", "seed": SEED},
        ],
        "provenance": {
            "assets": "original to Eloria/Nymara; generated by source/amberwood/*",
            "thirdParty": "none",
            "textures": "procedural (numpy + Pillow), no sampled or traced source",
            "geometry": "procedural (numpy), no imported models",
            "license": "same as the Eloria client repository",
        },
        "productionStatus": "production-geometry-materials-population",
        "knownLimitations": [],
    }
    import contentposts
    contentposts.apply_runtime(manifest,path.parent)
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
    sets = CK.register(preview.texture_sets())

    build = build_region(args.seed)

    t0 = time.time()
    builder, stats = export_glb(build, sets, out / "world.glb")
    print(f"[glb] {stats['glbBytes'] / 1e6:.2f} MB, {stats['nodes']} nodes, "
          f"{stats['uniqueTriangles']} unique tris, "
          f"{stats['instancedTriangles']} instanced tris "
          f"({time.time() - t0:.1f}s)")

    payload, width, height, collision_stats = build_collision(build)
    (out / "collision.bin").write_bytes(payload)
    print(f"[collision] {width}x{height} cells, "
          f"{collision_stats['walkableFraction'] * 100:.1f}% walkable")

    minimap = {"file": "minimap.webp"}
    if not args.skip_minimap:
        t0 = time.time()
        minimap = render_minimap(build, sets, out / "minimap.webp")
        print(f"[minimap] rendered in {time.time() - t0:.1f}s")

    texture_bytes = sum(sum(len(v) for v in ts.images().values()) for ts in sets.values())
    stats["embeddedTextureBytes"] = texture_bytes
    stats["textureMemoryBytesUncompressed"] = sum(
        ts.base_color.shape[0] * ts.base_color.shape[1] * 4 * 3 for ts in sets.values())
    stats["placements"] = len(build.placements)
    stats["collision"] = collision_stats
    stats["notes"] = build.notes

    views = write_camera_views(build, out / "camera-views.json")
    print(f"[views] {len(views['views'])} camera framings written")

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
        # the reduced package also drops texture resolution, which is where
        # most of a self-contained GLB's bytes actually are
        lod_sets = {name: texture_set.reduced()
                    for name, texture_set in sets.items()}
        lod_sets = CK.register(lod_sets)
        lod_build = build_region(args.seed, lod="far")
        _, lod_stats = export_glb(lod_build, lod_sets, out / "world-lod2.glb")
        stats["lod2"] = {
            "glbBytes": lod_stats["glbBytes"],
            "nodes": lod_stats["nodes"],
            "uniqueTriangles": lod_stats["uniqueTriangles"],
            "instancedTriangles": lod_stats["instancedTriangles"],
            "sizeReductionPercent": round(
                100.0 * (1.0 - lod_stats["glbBytes"] / stats["glbBytes"]), 1),
            "triangleReductionPercent": round(
                100.0 * (1.0 - lod_stats["instancedTriangles"]
                         / stats["instancedTriangles"]), 1),
        }
        report_lod = validate_gltf.validate(str(out / "world-lod2.glb")).to_dict()
        (out / "world-lod2.glb.validator.json").write_text(
            json.dumps(report_lod, indent=2) + "\n")
        print(f"[lod2] {lod_stats['glbBytes'] / 1e6:.2f} MB, "
              f"{lod_stats['instancedTriangles']} instanced tris, "
              f"{stats['lod2']['triangleReductionPercent']}% fewer "
              f"({time.time() - t0:.1f}s)")
        manifest["lodGroups"].append({
            "id": "package-lod2", "glb": "world-lod2.glb",
            "strategy": "reduced-package",
            "notes": "Far-tier vegetation only, no ground clutter."})
        (out / "world.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Raw measurements go to performance.json, NOT to performance-summary.md.
    # Amberwood's build writes its JSON dump straight into the .md the guide
    # asks for as documentation, so every build clobbers the doc and the package
    # cannot be reproducible and documented at the same time. Here the
    # machine-written numbers and the human-written summary are two files, and
    # the summary quotes the numbers.
    (out / "performance.json").write_text(
        json.dumps(stats, indent=2) + chr(10), encoding="utf-8")
    return 0 if counts["numErrors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
