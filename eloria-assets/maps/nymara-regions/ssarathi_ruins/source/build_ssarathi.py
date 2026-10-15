#!/usr/bin/env python3
"""Build the Ssarathi Ruins runtime map package.

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

import ssaratharch as A  # noqa: F401  (kit pieces reach the build via populate)
import ssarathikit as SK
import populate as POP
import region as REG
import layout as PLAN
from amberwood import routecraft as RC
import transitions as MARCH
import secretdoors as SD
import secrets_design as SEC
import streaming_borders as SB
import contentposts

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
SEED = 20260829
# Class islands smaller than this are given to whatever surrounds them. Six
# two-metre cells is 24 m2 - smaller than any surface a player is meant to read
# as its own thing, and larger than every crumb the thresholded noise and the
# boundary dither leave behind.
DESPECKLE_MIN_CELLS = 6

ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# The four ways out of the valley, as region-connections.json declares them:
# the north stair up to the south causeway of Four Gates, the east causeway
# to the Verdant Stair, the west causeway out onto the delta's bars, and the
# south water gate where the Crown court's boat calls.
CROSSINGS = [
    MARCH.Crossing('north-stair','four_gates',(154.5,-264.5),(154.5,-304.5),
                   radius=40,name='The Causeway March',station_position=(186,-191)),
    MARCH.Crossing('east-causeway','verdant_stair',(264.5,-88.5),(304.5,-88.5),
                   radius=40,name='The Stair March',station_position=(192,-68)),
    MARCH.Crossing('west-causeway','manymouth_delta',(-112.5,-108.5),(-152.5,-108.5),
                   radius=40,name='The Delta March',station_position=(-78,-96)),
    MARCH.Crossing('south-gate','crownwater',PLAN.FERRY,(8,28),radius=30,
                   ferry=True,name='The Water Gate',station_position=PLAN.FERRY_STATION),
]
MARCH_MATERIALS: dict = dict(getattr(REG, "SURFACE_MATERIALS", {}))
SK.MATERIALS = SK.MATERIALS | MARCH.materials_for("ssarathi_ruins", CROSSINGS) | SD.materials(SEC) | SB.materials_for("ssarathi_ruins") | {"water_lake", "timber_dark", "glass", "dark_iron"}


# --------------------------------------------------------------------------
def register_materials(sets: dict) -> dict:
    """Toolkit hook: add this region's materials to a shared texture set.

    `capture_views.py` and any other toolkit consumer call this so an offline
    capture renders in the region's own materials rather than in fallback grey.
    Idempotent, like `ssarathikit.register` itself.
    """
    return SK.register(sets)


def build_region(seed: int = SEED, lod: str | None = None) -> REG.RegionBuild:
    """Build the region. `lod="far"` produces the reduced second package:
    far-tier vegetation only and no ground clutter, for low-end machines and for
    distant streaming."""
    t0 = time.time()
    terrain = REG.build_terrain(seed)
    REG.apply_built_ground(terrain, seed)
    build = REG.RegionBuild(terrain=terrain)
    MARCH.prepare(terrain, CROSSINGS)
    PLAN.prepare(terrain)

    POP.build_water(build, lod=lod)
    POP.populate_bridges(build, seed)
    POP.populate_causeways(build, seed)
    POP.populate_temple(build, seed)
    POP.populate_courts(build, seed)
    POP.populate_landmarks(build, seed)
    POP.populate_quarters(build, seed)
    POP.populate_ruin_blocks(build, seed)
    POP.populate_vegetation(build, seed, lod=lod)
    if lod is None:
        POP.populate_props(build, seed)
    POP.populate_interior_doors(build, seed)
    POP.populate_metadata(build, seed)
    PLAN.dress(build,seed)

    # The marches: the neighbours' country coming in along the roads out.
    MARCH.paint(terrain, CROSSINGS, MARCH_MATERIALS, seed, sea_level=REG.SEA_LEVEL, keep=(REG.SILT, REG.JADE_PAVING, REG.MOSS_STONE))
    march = MARCH.dress(build, "ssarathi_ruins", CROSSINGS, seed, sea_level=REG.SEA_LEVEL)
    PLAN.seat_marches(build,march)
    SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
    PLAN.seat_secrets(build)
    build.landmarks.extend(march.landmarks)
    build.notes.extend(march.notes)

    PLAN.clear_routes(build)
    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.12, blend_edges=True, material_suffix=MAT.GROUND_SUFFIX,
        materials=MARCH_MATERIALS)
    # No backdrop. Amberwood needs one because its mountain walls have to stand
    # in front of something. Ssarathi is a closed basin: its own jungle-clad
    # valley walls rise above every sightline out of the bowl, so there is
    # nothing for a backdrop to fill and one would only ever be seen clipping
    # through the rim from the temple summit.
    build.resolve_names()
    _collect_landmarks(build)
    _add_spawns_and_portals(build)
    _add_population_markers(build, seed)
    if lod == 'far':
        coarse=TER.Terrain(terrain.x0,terrain.z0,terrain.size_x,terrain.size_z,cell=2.0)
        coarse.height=terrain.height_at(coarse.gx,coarse.gz)
        coarse.surface=terrain.surface_at(coarse.gx,coarse.gz)
        build.terrain_meshes=coarse.build_meshes(uv_scale=.12,blend_edges=True,
            material_suffix=MAT.GROUND_SUFFIX,materials=MARCH_MATERIALS)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_outer'))
    import outer_aprons
    outer_snapshot = outer_aprons.capture(build, 'ssarathi_ruins')
    SB.apply(build,'ssarathi_ruins')
    from geographic_approach import clear_west_channel
    clear_west_channel(build)
    PLAN.clear_causeway_canopies(build)
    outer_aprons.apply(build, 'ssarathi_ruins', outer_snapshot)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    import west_ruin_bypass
    west_ruin_bypass.apply(build)
    import inlet_crossings
    inlet_crossings.apply(build)
    connector_finish.apply(build, 'ssarathi_ruins')
    import west_bank_finish
    west_bank_finish.apply(build)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_color'))
    import terrain_paint
    terrain_paint.apply(build, 'ssarathi_ruins')
    print(f"[region] built in {time.time() - t0:.1f}s")
    return build


# Display names and types for every placement that declares a landmark id.
# Every one of these names is invented - no authoritative written Ssarathi
# region description exists in the repository. See modeling-assumptions.md.
LANDMARK_INFO: dict[str, tuple[str, str]] = {
    "great-temple": ("Temple of the Coiled Sun", "monument"),
    "channel-bridge": ("The Coil Bridge", "bridge"),
    "cistern-shaft": ("The Cistern Shaft", "entrance"),
    "hatchery-descent": ("The Hatchery Descent", "entrance"),
    "undercroft-mouth": ("The Undercroft Mouth", "entrance"),
    "sun-vault": ("The Sun Vault", "gate"),
    "sun-stela": ("The Sun Stela", "monument"),
    "root-arch": ("The Strangled Arch", "ruin"),
    "south-water-gate": ("South Water Gate", "gate"),
    "serpent-gate": ("The Serpent Pair", "monument"),
    "lily_court": ("The Lily Court", "court"),
    "ritual_plaza": ("The Ritual Plaza", "court"),
    "west-shrine": ("West Marchstone Shrine", "shrine"),
    "east-shrine": ("East Marchstone Shrine", "shrine"),
    "south-shrine": ("South Marchstone Shrine", "shrine"),
    "north-falls": ("The Greater Fall", "waterfall"),
    "east-falls": ("The Lesser Fall", "waterfall"),
}


def _collect_landmarks(build: REG.RegionBuild) -> None:
    """Build the manifest's landmark list from the placements themselves.

    Derived rather than hand-listed beside each `_add`, so a landmark cannot be
    recorded in the manifest at a position the mesh is not actually at - which
    is exactly the class of defect this region's *placeholder* package shipped,
    where a third of the landmarks named other regions entirely.

    Runs after `resolve_names`, so a node renamed to `Walk_...` is recorded
    under the name the GLB actually uses.
    """
    t = build.terrain
    for placement in build.placements:
        if not placement.landmark:
            continue
        if any(mark['id']==placement.landmark for mark in build.landmarks):
            continue
        x, y, z = placement.position
        name, kind = LANDMARK_INFO.get(
            placement.landmark,
            (placement.landmark.replace("-", " ").replace("_", " ").title(),
             "structure"))
        build.landmarks.append({
            "id": placement.landmark,
            "name": name,
            "node": placement.node,
            "type": kind,
            "position": [round(float(x), 2), round(float(y), 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "note": "placeholder name - see modeling-assumptions.md"})
    build.landmarks.sort(key=lambda entry: entry["id"])


def _add_spawns_and_portals(build: REG.RegionBuild) -> None:
    t = build.terrain
    # The default spawn is the harbour islet, not the cathedral plaza. Arriving
    # on the far side of the water is the whole framing of detail-board panel 1:
    # you arrive on a quay with the temple visible up the axis, which is the
    # framing of detail-board panel 1.
    for spawn_id, (x, z), facing in (
            ("default", REG.SPAWN, math.radians(-52.0)),
            ("great-causeway", REG.SPAWN_CAUSEWAY, math.pi),
            ("temple-terrace", REG.SPAWN_TEMPLE, math.pi)):
        y = float(t.height_at(x, z))
        build.spawns.append({
            "id": spawn_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})

    # Edge portals to the neighbouring Nymara regions. Destination map ids
    # follow the client registry; the server remains authoritative for the
    # transition. Ssarathi's are the four outlying platforms at the ends of the
    # street network, where a causeway runs out toward the valley wall.
    for portal_id, name, anchor, destination in (
            ("north-stair", "Stair to the Four Gates Causeway", "north_terrace",
             "four_gates"),
            ("east-causeway", "Causeway to the Verdant Stair", "east_shrine",
             "verdant_stair"),
            ("west-causeway", "Causeway to the Manymouth Delta", "west_shrine",
             "manymouth_delta"),
            ("south-gate", "Water Gate: the Crownwater boat", "south_shrine",
             "crownwater")):
        x,y,z = PLAN.PORTALS[portal_id]
        build.portals.append({
            "id": portal_id, "name": name, "type": "map-transition",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "destinationMap": destination, "radius": 3.5,
            "authority": "server"})


def _add_population_markers(build: REG.RegionBuild, seed: int) -> None:
    """Editor/visual markers only - the server owns actual spawning."""
    t = build.terrain
    rng = N.Rng(seed + 777)

    npc_plan = [
        ("ssarathi-gate-warden", "Warden of the Water Gate", "south_gate", 7.0),
        ("ssarathi-causeway-guide", "Causeway Guide", "causeway_mid", 6.0),
        ("ssarathi-vault-keeper", "Keeper of the Sun Vault", "vault_door", 5.0),
        ("ssarathi-temple-hierophant", "Temple Hierophant", "temple_terrace", 7.0),
        ("ssarathi-stela-reader", "Stela Reader", "sun_stela", 5.0),
        ("ssarathi-market-trader", "Basin Trader", "market", 8.0),
        ("ssarathi-dock-poler", "Punt Poler", "east_dock", 5.0),
        ("ssarathi-west-poler", "West Landing Poler", "west_dock", 5.0),
        ("ssarathi-lily-tender", "Lily Court Tender", "lily_court", 7.0),
        ("ssarathi-pool-adept", "Ritual Pool Adept", "ritual_plaza", 8.0),
        ("ssarathi-drowned-scavenger", "Drowned Quarter Scavenger",
         "drowned_quarter", 12.0),
        ("ssarathi-arch-hermit", "Hermit of the Root Arch", "root_arch", 6.0),
        ("ssarathi-arrival-steward", "Arrival Quay Steward", "arrival_quay", 5.0),
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
        generator="Eloria Ssarathi Ruins builder (original procedural assets)")
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
                      - SK.MATERIALS)
    if unpinned:
        raise SystemExit(
            "materials used but not in ssarathikit.MATERIALS: "
            + ", ".join(unpinned))
    # The other direction is not an error but it is not free either: every
    # pinned material embeds its textures whether or not a mesh references it.
    # Amberwood's pin carries six such and pays 2.79 MB for them.
    # Read through the ground copies here too: a material the terrain
    # now draws with an alpha-tested copy is still referenced, and
    # calling it dead weight would invite trimming a pin the copy
    # depends on.
    unused = sorted(SK.MATERIALS
                    - {MAT.base_material(name) for name in used})
    if unused:
        print("[materials] WARNING pinned but unreferenced, costing bytes: "
              + ", ".join(unused))

    # Pinned by name to the materials Ssarathi Ruins actually uses. Without `only=`
    # the package embeds the whole shared library - about ten megabytes of forest
    # and burnt-country textures this region never references - and, worse, its
    # contents would change whenever another region appends to the shared table.
    MAT.register_gltf_materials(builder, sets, only=SK.MATERIALS)
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

    root = GLTF.Node("Ssarathi Ruins")
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

    # A flooded region's walkability threshold is the waterline, not a shore
    # margin: Ssarathi's causeways stand 1.8 m out of the water and its fringe
    # ground is barely above it, so anything above the surface is walkable and
    # anything below it is not.
    walkable = (ground > REG.WATER_LEVEL + 0.20) & (slope < 1.05)
    # solid structures block their footprint
    blockers = np.zeros_like(walkable)
    explicit_blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if placement.node.startswith(SB.VIEW_PREFIX):continue
        if not placement.collides:
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        # trees block only their trunk, not the spread of their canopy
        footprint = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2]))) \
            * placement.scale
        factor = 0.16 if placement.kind in ("tree", "foliage") else 0.62
        extra=placement.extras or {}
        radius=float(extra.get("solidRadius",min(max(footprint*factor,0.40),11.0)))
        px,_,pz=placement.position
        if "solidRects" in extra:
            c,s=math.cos(placement.rotation_y),math.sin(placement.rotation_y)
            lx=(c*(gx-px)-s*(gz-pz))/placement.scale
            lz=(s*(gx-px)+c*(gz-pz))/placement.scale
            mask=np.zeros_like(walkable)
            for x0,z0,x1,z1 in extra["solidRects"]:
                mask |= (lx>=x0)&(lx<=x1)&(lz>=z0)&(lz<=z1)
        else:
            mask=np.hypot(gx-px,gz-pz)<radius
        blockers |= mask
        if "solidRadius" in extra or "solidRects" in extra:explicit_blockers |= mask
    walkable &= ~blockers

    surface=ground.copy();decks=np.zeros_like(walkable)
    import glb_reader as GLB
    triangles=[];elevated=0
    for name,item in build.terrain_meshes.items():
        if name.startswith('Walk_') and item.triangle_count:
            triangles.append(item.positions[item.indices.reshape(-1,3)]);elevated+=1
    for placement in build.placements:
        if placement.node.startswith(SB.VIEW_PREFIX):continue
        item=build.meshes[placement.mesh]
        parts=list(getattr(item,'walk_parts',[]))
        if placement.walk_surface and not parts:parts=[item] if isinstance(item,M.Mesh) else list(item.parts)
        if not parts:continue
        matrix=M.translation(*placement.position)@M.rotation_y(placement.rotation_y)@M.scaling(placement.scale)
        for part in parts:
            mesh=part.transformed(matrix)
            triangles.append(mesh.positions[mesh.indices.reshape(-1,3)])
        elevated+=1
    if triangles:
        covered,deck_y=GLB.rasterise(np.concatenate(triangles),width,height,
            REG.PLAY_MIN_X,REG.SERVER_ORIGIN[1],COLLISION_CELL)
        surface=np.where(covered,np.maximum(surface,deck_y),surface)
        # Only exposed walking decks own terrain cells. Buried skins cannot
        # exempt a steep bank from the server's true surface slope mask.
        decks=covered&(deck_y>=ground-.03)&(deck_y>REG.WATER_LEVEL+.20)
        walkable|=decks

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
    walkable &= ~explicit_blockers

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
        # The world coordinate of cell (0, 0)'s outer corner: the -X edge and
        # the +Z edge, because rows run north to south. region_client_check.gd
        # needs this to judge grounding on walkable cells rather than on every
        # tile of the bounding square, which is the rule interiors need and
        # regions are merely stricter under.
        "originMetres": [float(REG.PLAY_MIN_X),
                         float(REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE)],
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
INSIDES_MAP = "ssarathi_royal_archive"

# door id -> (display name, landmark it hangs on, the anchor to place it at)
INTERIOR_DOORS = (
    ("archive-vault-door", "The Sun Vault", "sun-vault", "vault_door"),
    ("hatchery-descent", "The Hatchery Descent", "hatchery-descent",
     "ritual_plaza"),
    ("cistern-shaft", "The Cistern Shaft", "cistern-shaft", "drowned_quarter"),
    ("undercroft-mouth", "The Undercroft Mouth", "undercroft-mouth",
     "root_arch"),
    ("tenth-mouth-door", "The Tenth Mouth Shrine", "lily-court", "lily_court"),
    ("water-gate-undercut-mouth", "The Water Gate Undercut", "south-water-gate",
     "south_gate"),
    ("lineage-house-door", "The Lineage Reader's House", "serpent-gate", "serpent_gate"),
)


def _nearest_walkable(payload: bytes, width: int, height: int,
                      x: float, z: float) -> tuple[float, float, float]:
    """Move a point onto the nearest cell `collision.bin` calls walkable.

    A landmark that collides blocks its own footprint, and a doorway is attached
    to a landmark - so a door placed at a landmark's centre lands on a blocked
    cell and the player arrives inside a wall. Amethyst Barrens found two of its
    four doors in exactly that state; this checks all four rather than trusting
    them, and reports how far each moved.
    """
    grid = np.frombuffer(payload[16:], dtype=np.uint8).reshape(height, width)
    col = int(round((x - REG.PLAY_MIN_X) / COLLISION_CELL - 0.5))
    row = int(round((REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE - z)
                    / COLLISION_CELL - 0.5))
    col = min(max(col, 0), width - 1)
    row = min(max(row, 0), height - 1)
    if grid[row, col]:
        return x, z, 0.0
    for radius in range(1, 121):
        r0, r1 = max(row - radius, 0), min(row + radius + 1, height)
        c0, c1 = max(col - radius, 0), min(col + radius + 1, width)
        window = grid[r0:r1, c0:c1]
        hits = np.argwhere(window > 0)
        if hits.size == 0:
            continue
        rows_, cols_ = hits[:, 0] + r0, hits[:, 1] + c0
        distances = (rows_ - row) ** 2 + (cols_ - col) ** 2
        best = int(np.argmin(distances))
        nx = REG.PLAY_MIN_X + (cols_[best] + 0.5) * COLLISION_CELL
        nz = REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE \
            - (rows_[best] + 0.5) * COLLISION_CELL
        return float(nx), float(nz), float(math.hypot(nx - x, nz - z))
    return x, z, -1.0


def _add_interior_doors(build: REG.RegionBuild, payload: bytes,
                        width: int, height: int, collision_stats: dict) -> None:
    """The four ways into `ssarathi_insides`, and the four returns.

    Every door is an `interior-entrance` portal on this map pointing at the one
    insides map and choosing its section by spawn id, plus a matching spawn of
    the same name here so the return portal on the insides map has somewhere to
    land. Both directions resolve.
    """
    t = build.terrain
    for door_id, name, landmark_id, anchor in INTERIOR_DOORS:
        x, z = REG.ANCHORS[anchor]
        if anchor == "ritual_plaza":
            # the descent is on the court's north rim, not at its centre
            z = z - REG.COURTS["ritual_plaza"]["radius"] * 0.80
        elif anchor == "root_arch":
            x, z = x - 14.0, z + 12.0
        x,z=PLAN.DOORS[door_id]
        x,z,moved=_nearest_walkable(payload,width,height,x,z)
        grid=np.frombuffer(payload[16:],dtype=np.uint8).reshape(height,width)
        col=int(np.clip(round((x-REG.PLAY_MIN_X)/COLLISION_CELL-.5),0,width-1))
        row=int(np.clip(round((REG.SERVER_ORIGIN[1]-z)/COLLISION_CELL-.5),0,height-1))
        encoded=int(grid[row,col]);encoding=collision_stats['heightEncoding']
        y=encoding['origin']+encoded*encoding['step']
        if moved > 0.05:
            print(f"[door] {door_id} moved {moved:.1f} m onto walkable ground")
        elif moved < 0.0:
            print(f"[door] {door_id} FOUND NO WALKABLE CELL")
        tile = [int(round(x + REG.SERVER_ORIGIN[0])),
                int(round(REG.SERVER_ORIGIN[1] - z))]
        build.portals.append({
            "id": door_id, "name": name, "type": "interior-entrance",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": tile,
            "landmark": landmark_id,
            "destinationMap": INSIDES_MAP,
            "destinationSpawn": door_id,
            "radius": 2.5, "authority": "server"})
        build.spawns.append({
            "id": door_id,
            "position": [round(x, 2), round(y + 0.05, 2), round(z, 2)],
            "serverTile": tile,
            "rotationDegrees": 180.0,
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})


# --------------------------------------------------------------------------
## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def render_minimap(build: REG.RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down orthographic-ish capture of the finished geometry."""
    import preview
    scene = preview.scene_from_build(build, sets)
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

    # Use emitted walk triangles, so a sloping jetty and an open shaft
    # cannot be mistaken for the top of their enclosing bounding box.
    import glb_reader as GLB
    from verify_runtime import VerticalRayIndex
    document,body=GLB.load(path.parent/"world.glb")
    deck_index=VerticalRayIndex(GLB.triangles(document,body,GLB.named(document,"Walk_")),cell=4)

    def clear_eye(x, y, z):
        """Lift a camera that sits inside, or directly under, solid geometry."""
        for x0, x1, z0, z1, y0, y1 in boxes:
            if not (x0 - 1.2 <= x <= x1 + 1.2 and z0 - 1.2 <= z <= z1 + 1.2):
                continue
            if y <= y1 + 1.6:
                y = y1 + 2.4
        return y

    entries = []
    for (name, panel, eye_xz, eye_h, target_xz, target_h, fov, _size,
         _radius, mode) in VIEWTABLE.VIEWS:
        ex, ez = eye_xz[0] * REG.SCALE, eye_xz[1] * REG.SCALE
        tx, tz = target_xz[0] * REG.SCALE, target_xz[1] * REG.SCALE
        ey = float(t.height_at(ex, ez)) + eye_h
        ty = float(t.height_at(tx, tz)) + target_h
        # a camera below the waterline sees nothing but the water plane's
        # underside; lift any eye that the terrain put under the basin
        if mode.rstrip("!")=="deck":
            deck=deck_index.top_hit(ex,ez)
            if deck is None:raise ValueError(f"No walk surface for camera {name}: {ex},{ez}")
            target_deck=deck_index.top_hit(tx,tz)
            ey=deck+eye_h
            ty=(target_deck if target_deck is not None else deck)+target_h
        elif mode!="submerged":
            ey=max(ey,REG.WATER_LEVEL+0.6)
            if name not in VIEWTABLE.FIXED_VIEWS:ey=clear_eye(ex,ey,ez)
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
        if placement.node.startswith(SB.VIEW_PREFIX):continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        offset = np.asarray(placement.position)
        lows.append(low * placement.scale + offset)
        highs.append(high * placement.scale + offset)
    bounds_min = np.vstack(lows).min(axis=0)
    bounds_max = np.vstack(highs).max(axis=0)

    surface_prefixes = ["Terrain_", "Walk_"]
    collision_nodes = sorted({p.node for p in build.placements if p.collides and not p.node.startswith(SB.VIEW_PREFIX)})

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": "ssarathi_ruins",
            "name": "Ssarathi Ruins",
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
            "seaLevel": REG.WATER_LEVEL,
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
        "collision": {
            "nodeNames": collision_nodes,
            "stampedLandmarks":PLAN.solid_records(build),
            "binary": "collision.bin",
            # Both of these describe the file `build_collision` just wrote,
            # so both are taken from it rather than from the constants above,
            # which stopped being true when the grid moved to v2 and to an
            # encoding sized from the region's own relief.
            "format": "EWCG-v%d" % COLLISION_FORMAT_VERSION,
            "cellMetres": COLLISION_CELL,
            "originMetres": collision_stats["originMetres"],
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
        "navigation": {
            "crossings":build.crossings,
            "surfaceNodePrefixes": surface_prefixes,
            "walkableAreas": ["jade-paving", "moss-stone", "jungle-floor",
                              "causeways", "bridge-decks", "docks", "stairs",
                              "temple-tiers"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every built "
                "walkable surface is named Walk_<...>. The client turns both "
                "into the navigation collision layer the grounding ray tests.",
                "Ssarathi's causeways are stone embankments, so they are "
                "terrain, not decks. The only Walk_ geometry in the region is "
                "the channel bridges, the timber docks, the temple stair and "
                "summit, the vault threshold, the stela plinth and the shrine "
                "steps. Those own their server cell: the water beneath a "
                "bridge is not separately walkable.",
                "The basin floor is terrain and carries the Terrain_ prefix "
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
        "contentLayout":PLAN.CONTENT_LAYOUT,
        "streamingBorders":getattr(build,"streaming_borders",[]),
        "portals": build.portals,
        # Ssarathi's routes are stone embankments carrying paved surface,
        # not graded earth roads, so they are typed as causeways. Waypoint
        # heights are sampled from the built terrain rather than assumed,
        # because a route dips to the channel floor where a bridge crosses it
        # and the bridge deck is what a traveller is actually on there.
        "roads": [{"id": name, "type": "causeway",
                   "waypoints": [[round(float(p[0]), 1),
                                  round(max(float(t.height_at(p[0], p[1])),
                                            REG.DECK), 2),
                                  round(float(p[1]), 1)] for p in points]}
                  for name, points in REG.street_routes().items()] + [
                     {"id": name, "type": "causeway", "width": width,
                      "waypoints": [[float(x),float(y),float(z)] for (x,z),y in zip(points,heights)]}
                     for name,(points,heights,width) in PLAN.ROADS.items()],
        "water": {
            "seaLevel": REG.WATER_LEVEL,
            "serverCells": REG.SERVER_CELLS,
            "bodies": [{"id": name, "node": name,
                        "type": "basin" if "Basin" in name else "pool"}
                       for name in build.water_meshes],
            # One body of standing water. The three carved watercourses are
            # part of that same surface, not separate bodies - they are deeper
            # cuts in the same basin - so they are declared as channels.
            "streams": [],
            "channels": [{"id": name, "type": "navigable",
                          "floor": REG.CHANNEL_FLOOR,
                          "note": "carved watercourse, bridged where a street crosses"}
                         for name in REG.CHANNELS],
            "bridges": [{"id": span["name"], "street": span["street"],
                         "channel": span["channel"],
                         "deck": round(span["deck"], 2),
                         "centre": [round(span["centre"][0], 1), 0.0,
                                    round(span["centre"][1], 1)]}
                        for span in REG.bridge_spans()],
        },
        "environment": {
            # Tuned to the concept: a hot high sun through humid air over a
            # green basin. Unlike Crownwater's clear lagoon light this carries
            # real fog - the painting's distances go milky and green-blue, and
            # the far side of the basin is visibly hazier than the near.
            "sky": {"type": "gradient", "zenith": [0.24, 0.48, 0.70],
                    "horizon": [0.80, 0.86, 0.80], "curve": 0.20,
                    "groundHorizon": [0.40, 0.50, 0.38],
                    "groundBottom": [0.14, 0.20, 0.14],
                    "sunAngleMax": 18.0, "energy": 0.80},
            # `direction` is the direction the light TRAVELS, not the direction
            # of the sun in the sky: the binder does
            # `sun.look_at_from_position(ZERO, direction)`, and a
            # DirectionalLight3D emits along its local -Z. A +Y component
            # therefore lights the world from underneath. Amberwood's manifest
            # still declares +Y and has never been rendered through this path.
            # Tuned against real client frames, not guessed. At energy 1.12
            # with the sun almost straight down the region rendered dim and
            # blue-grey in Godot while the offline preview looked bright: a
            # near-vertical key gives vertical faces nothing, and the flat
            # default tonemap below was crushing what was left. This is
            # oblique enough to model the masonry and strong enough to carry
            # the basin.
            "sun": {"direction": [-0.38, -0.76, 0.52],
                    "color": [1.20, 1.13, 0.95], "energy": 2.35,
                    "indirectEnergy": 1.35, "angularDiameterDegrees": 1.1},
            # Strong indirect and a green-lifted ambient: a jungle basin's
            # shadows are filled by light bounced off leaves and off the water,
            # and a neutral ambient made the ruins read as grey stone.
            # skyContribution 0.45, not 0.70: the binder blends the declared
            # colour against the sky, and at 0.70 the blue sky drowned the
            # green bounce this region's shadows need.
            "ambient": {"color": [0.54, 0.66, 0.56], "energy": 0.42,
                        "skyContribution": 0.35},
            "saturation": 1.30,
            "fog": {"enabled": True, "color": [0.66, 0.78, 0.70],
                    "density": 0.00011, "heightFalloff": 0.0040,
                    "skyAffect": 0.04, "aerialPerspective": 0.10},
            # Declared explicitly. Without a tonemap block the binder leaves
            # Godot's linear default at exposure 1.0, which is what made the
            # first in-client captures read as an overcast evening. Amberwood,
            # Mirrorhold, Whitehorn, Amethyst and Crownwater all omit it too
            # and none of them has been checked through this path.
            "tonemap": {"mode": "filmic", "exposure": 1.05, "white": 6.0},
            "variants": {
                "golden-hour": {
                    "sun": {"direction": [-0.78, -0.30, 0.55],
                            "color": [1.50, 1.08, 0.68], "energy": 1.70},
                    "ambient": {"color": [0.62, 0.56, 0.46], "energy": 0.90,
                                "skyContribution": 0.40},
                    "fog": {"enabled": True, "color": [0.80, 0.70, 0.52],
                            "density": 0.0018, "aerialPerspective": 0.45},
                    "tonemap": {"mode": "filmic", "exposure": 1.28,
                                "white": 6.0},
                },
            },
            "water": {
                "shallowColor": [0.30, 0.72, 0.66],
                "deepColor": [0.06, 0.26, 0.30],
                "causticsEnabled": True,
                "note": ("Shallow/deep tint and caustics are presentation "
                         "settings for whoever writes the water shader; the "
                         "GLB ships a flat lit plane. Ssarathi's water is "
                         "shallow over most of its area, so the shallow tint "
                         "is what will actually be seen."),
            },
            "presentation": {
                "insects": {"enabled": True, "density": 0.7,
                            "zones": ["basin", "jungle-rim"]},
                "mist": {"enabled": True, "density": 0.35,
                         "zones": ["north-falls", "basin"]},
                "spray": {"enabled": True, "zones": ["north-falls", "east-falls"]},
                "birds": {"enabled": True, "density": 0.4, "zones": ["jungle-rim"]},
                "bannerWind": {"enabled": True, "strength": 0.30},
                "ambientAudio": [
                    {"id": "water-lap", "zone": "basin"},
                    {"id": "jungle-canopy", "zone": "jungle-rim"},
                    {"id": "falls", "zone": "north-falls"},
                    {"id": "market", "zone": "market"}],
                "note": ("Declared, not implemented: no particle systems ship "
                         "in the GLB."),
            },
            "zones": [
                {"id": "temple", "centre": [round(REG.ANCHORS["temple"][0], 1), 16.0,
                                            round(REG.ANCHORS["temple"][1], 1)],
                 "radius": 90.0},
                {"id": "basin", "centre": [90.0, 0.0, -90.0], "radius": 300.0},
                {"id": "jungle-rim", "centre": [90.0, 12.0, -90.0], "radius": 420.0},
                {"id": "market", "centre": [round(REG.ANCHORS["market"][0], 1), 2.0,
                                            round(REG.ANCHORS["market"][1], 1)],
                 "radius": 46.0},
                {"id": "north-falls",
                 "centre": [round(REG.ANCHORS["north_falls"][0], 1), 4.0,
                            round(REG.ANCHORS["north_falls"][1], 1)],
                 "radius": 70.0},
                {"id": "east-falls",
                 "centre": [round(REG.ANCHORS["east_falls"][0], 1), 4.0,
                            round(REG.ANCHORS["east_falls"][1], 1)],
                 "radius": 55.0},
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
             "role": "authoritative-player-scale",
             "note": ("The full ten-panel board. The truncated 786,444-byte "
                      "copy every region package shipped was replaced with the "
                      "intact 1983x793 board supplied for this build.")},
            {"id": "generator", "file": "source/build_ssarathi.py",
             "role": "reproducible-build", "seed": SEED},
        ],
        "provenance": {
            "assets": "original to Eloria/Nymara; generated by _toolkit/ and this region source",
            "thirdParty": "none",
            "textures": "procedural (numpy + Pillow), no sampled or traced source",
            "geometry": "procedural (numpy), no imported models",
            "license": "same as the Eloria client repository",
        },
        "productionStatus": "production-geometry-materials-population",
        "knownLimitations": [],
    }
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
    sets = SK.register(preview.texture_sets())

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

    _add_interior_doors(build, payload, width, height, collision_stats)

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
        lod_sets = SK.register(lod_sets)
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
