#!/usr/bin/env python3
"""Build the Manymouth Delta runtime map package.

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

import deltakit as DK
import stiltkit as SK  # noqa: F401  (registers the delta tree species)
import populate as POP
import layout as LAY
import glb_reader as GLB
import region as REG
import transitions as MARCH
import secretdoors as SD
import secrets_design as SEC
import loresites as LORE
import streaming_borders as SB
import compact_plan as COMPACT

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

# The four landings, as region-connections.json declares them: the north
# landing where the Crownwater packet comes down the main channel, the east
# landing under the temple causeway, the west landing where the moor's drain
# track comes down, and the south landing at the far bar where the coast road
# from Westhaven arrives.
CROSSINGS = [
    MARCH.Crossing("north-landing", "crownwater", REG.ANCHORS["north_fishing"],
                   (REG.ANCHORS["north_fishing"][0], REG.PLAY_MIN_Z - 20.0),
                   radius=30.0, ferry=True, name="The Channel Landing"),
    MARCH.Crossing("east-landing", "ssarathi_ruins", REG.ANCHORS["east_watch"],
                   (REG.PLAY_MAX_X + 20.0, REG.ANCHORS["east_watch"][1]),
                   radius=36.0, name="The Temple March"),
    MARCH.Crossing("west-landing", "grey_moors", REG.ANCHORS["sea_landing"],
                   (REG.PLAY_MIN_X - 20.0, REG.ANCHORS["sea_landing"][1]),
                   radius=36.0, name="The Drain March"),
    MARCH.Crossing("south-landing", "westhaven", REG.ANCHORS["far_bar"],
                   (REG.ANCHORS["far_bar"][0] + 30.0, REG.ANCHORS["far_bar"][1] + 30.0),
                   radius=32.0, name="The Coast Road March"),
]

# The places the region's people argue about (see loresites.py).
SITES = [
    LORE.Site("stelae-court", "The Stelae Court", "stelae_field", (330.0, -108.0),
              thread="G", clearing=13.0,
              note="The water lineage in the order the channels were claimed: two ranks with a "
                   "reading path between them, and the tenth stone left blank."),
]
MARCH_MATERIALS: dict = dict(getattr(REG, "SURFACE_MATERIALS", {}))
DK.MATERIALS = DK.MATERIALS | MARCH.materials_for("manymouth_delta", CROSSINGS) | SD.materials(SEC) | LORE.materials([s.piece for s in SITES]) | SB.materials_for("manymouth_delta")


def register_materials(sets):
    """Extend the shared texture table with this region's recipes.

    The toolkit's capture and comparison scripts call this if it exists, so an
    offline preview uses the same material table the GLB ships. Without it every
    `manymouth_*` material resolves to index 0 in the preview renderer and the
    captures show bark where the water should be.
    """
    return DK.register(sets)


# --------------------------------------------------------------------------
def walk_triangles(build):
    if hasattr(build, "_walk_triangles"):
        return build._walk_triangles
    out=[]
    # Shared causeway decks and invisible trigger skins are actual walking
    # geometry in terrain_meshes, not placements. Preserve them in raw collision.
    for name,part in build.terrain_meshes.items():
        if name.startswith("Walk_") and not name.startswith(SB.VIEW_PREFIX):
            out.append(part.positions[part.indices].reshape(-1,3,3))
    for p in build.placements:
        if p.node.startswith(SB.VIEW_PREFIX):continue
        item=build.meshes[p.mesh]
        parts=getattr(item,"walk_parts",[]) or ([item] if p.walk_surface else [])
        c,s=math.cos(p.rotation_y or 0),math.sin(p.rotation_y or 0)
        rotation=np.array([[c,0,s],[0,1,0],[-s,0,c]])
        for part in parts:
            world=part.positions@rotation.T*p.scale+np.asarray(p.position)
            out.append(world[part.indices].reshape(-1,3,3))
    build._walk_triangles=np.concatenate(out) if out else np.zeros((0,3,3))
    return build._walk_triangles

def walk_surface_at(build, x, z):
    tri=walk_triangles(build)
    mask=(tri[:,:,0].min(1)<=x)&(tri[:,:,0].max(1)>=x)&(tri[:,:,2].min(1)<=z)&(tri[:,:,2].max(1)>=z)
    covered,top=GLB.rasterise(tri[mask],1,1,x-.0005,z+.0005,.001)
    return max(float(build.terrain.height_at(x,z)),float(top[0,0]))


def apply_streaming(build):
    """Finalize both main/LOD geometry once, after native posts are authored."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_outer'))
    import outer_aprons
    outer_snapshot = outer_aprons.capture(build, 'manymouth_delta')
    SB.apply(build, "manymouth_delta")
    outer_aprons.apply(build, 'manymouth_delta', outer_snapshot)
    COMPACT.connector_requests(build)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    connector_finish.apply(build, 'manymouth_delta')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_color'))
    import terrain_paint
    terrain_paint.apply(build, 'manymouth_delta')
    # Native spawn authoring may have sampled decks before shared grading
    # moved placements or added the causeways. Collision must sample final ones.
    if hasattr(build, "_walk_triangles"):
        del build._walk_triangles


# --------------------------------------------------------------------------
def build_region(seed: int = SEED, lod: str | None = None, *, prototype=False, legacy=False) -> REG.RegionBuild:
    """Build the region. `lod="far"` produces the reduced second package:
    far-tier vegetation only and no ground clutter, for low-end machines and for
    distant streaming."""
    t0 = time.time()
    COMPACT.restore_legacy_frame()
    terrain = REG.build_terrain(seed)
    REG.apply_built_ground(terrain, seed)
    build = REG.RegionBuild(terrain=terrain)
    MARCH.prepare(terrain, CROSSINGS)
    LORE.prepare(terrain, SITES, sea_level=getattr(REG, "SEA_LEVEL", 0.0), keep=(TER.DELTA_SILT, TER.DELTA_PADDY))

    # The walkway network resolves first and everything else reads its deck
    # levels out of the result. See the note at the top of populate.py.
    network = LAY.walkway_network(build, seed)
    POP.build_water(build, lod=lod)
    POP.populate_arch(build, seed, network)
    POP.populate_cave(build, seed, network)
    POP.populate_temple(build, seed, network)
    POP.populate_stilt_town(build, seed, network)
    POP.populate_villages(build, seed, network)
    POP.populate_deck_study(build, seed, network)
    POP.populate_paddies(build, seed, network)
    POP.populate_mangroves(build, seed, network, lod=lod)
    POP.populate_vegetation(build, seed, network, lod=lod)
    if lod is None:
        POP.populate_props(build, seed, network)
    LAY.finish(build, seed, network)
    POP.populate_metadata(build, seed, network)

    # The marches: the neighbours' country coming in along the roads out.
    MARCH.paint(terrain, CROSSINGS, MARCH_MATERIALS, seed, sea_level=REG.SEA_LEVEL, keep=(TER.DELTA_SILT, TER.DELTA_PADDY))
    march = MARCH.dress(build, "manymouth_delta", CROSSINGS, seed, sea_level=REG.SEA_LEVEL)
    LORE.dress(build, terrain, SITES, seed)
    SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
    build.landmarks.extend(march.landmarks)
    build.notes.extend(march.notes)

    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.28, blend_edges=True, material_suffix=MAT.GROUND_SUFFIX,
        materials=MARCH_MATERIALS)
    # No landmass backdrop. Amberwood needs one because its mountain walls have
    # to stand in front of something; the delta's horizon is open water on three
    # sides and its own jungle head on the fourth, and the water plane is
    # already cut far outside the authored terrain to supply the rest.
    build.resolve_names()
    build.network = network
    _add_spawns_and_portals(build, network)
    if not legacy:
        COMPACT.apply(build,MARCH_MATERIALS)
    if prototype:
        build.streaming_borders=[]
    else:
        apply_streaming(build)
    print(f"[region] built in {time.time() - t0:.1f}s")
    return build


def spawn_point(build, anchor, reach=52.0):
    """The authored, continuous landing at this destination."""
    x,_,z=LAY.standing(build,anchor)
    return x,walk_surface_at(build,x,z),z


def _add_spawns_and_portals(build: REG.RegionBuild, network: dict) -> None:
    t = build.terrain
    levels = network["levels"]
    # The default spawn is the town bar, not the arch: arriving with the ring
    # standing out of the water half a kilometre off is the framing of panel 9,
    # and it is the first thing the region should say.
    for spawn_id, anchor, facing in (
            ("default", "stilt_town", math.radians(38.0)),
            ("arch-stair", "arch_stair", math.radians(-140.0)),
            ("temple-quay", "temple_quay", math.radians(-104.0))):
        x, y, z = spawn_point(build, anchor)
        build.spawns.append({
            "id": spawn_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True,
            "note": ("grounded on the surveyed landing at the town and route junctions"),
        })

    # --- the four doors into the insides map ---------------------------
    # Every door targets the SAME destinationMap and differs only in
    # destinationSpawn, which is the whole point of putting a region's
    # interiors on one map: one load, four arrivals. Each door also gains a
    # region spawn of the same name so the insides map's return portal has
    # somewhere to land - without it a player leaving the Underdeck reappears
    # at the default spawn on the other side of the town.
    #
    # The return spawn is sited by `spawn_point`, not at the door itself: the
    # door is on a deck, and a spawn declared on a deck is a spawn the client's
    # ray may fall straight through between two planks.
    for door_id, name, anchor, facing in (
            ("labyrinth-mouth", "Mouth of the Flooded Labyrinth", "cave_mouth",
             math.radians(20.0)),
            ("underdeck-hatch", "The Underdeck Hatch", "town_quay",
             math.radians(34.0)),
            ("tide-hall-door", "The Tide Hall", "town_hall",
             math.radians(18.0)),
            ("temple-sanctum-door", "The Sanctum Stair", "green_temple",
             math.radians(-104.0)),
            # The fifth door, and the one worth having: the ring standing out
            # of the whirlpool is the top of the Submerged Gate, so going down
            # through it lands under it. Both ends of that transition are
            # geometry that already existed - this only admits that the arch on
            # the surface and the gate below are the same object.
            ("gate-descent", "The Manymouth Arch", "great_arch",
             math.radians(-140.0)),
             ("paddy-sump-mouth", "The Paddy Watch Sump", "paddy_tower",
             math.radians(90.0)),
            ("bund-shrine-door", "The Bund Shrine", "south_shrine",
             math.radians(0.0)),
            ("bund-warden-door", "The Bund Warden's House", "paddy_hamlet",
             math.radians(45.0)),
):
        x, y, z = spawn_point(build, anchor)
        build.spawns.append({
            "id": door_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True,
            "note": "return landing for the insides map's exit portal"})
        build.portals.append({
            "id": door_id, "name": name, "type": "map-transition",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "destinationMap": "manymouth_flooded_labyrinth",
            "destinationSpawn": door_id,
            "radius": 3.5, "authority": "server"})

    # Edge portals to the neighbouring Nymara regions. Destination map ids follow
    # the client registry; the server remains authoritative for the transition.
    # Every land route out of a delta is a boat, so these are landings rather
    # than roads.
    for portal_id, name, anchor, destination in (
            ("north-landing", "Crownwater Packet up the Channel", "north_fishing",
             "crownwater"),
            ("east-landing", "Temple Causeway to the Ssarathi Ruins", "east_watch",
             "ssarathi_ruins"),
            ("south-landing", "Coast Road to Westhaven", "far_bar",
             "westhaven"),
            ("west-landing", "Drain Track up to the Grey Moors", "sea_landing",
             "grey_moors")):
        x, z = network["points"][anchor]
        y = walk_surface_at(build, x, z)
        build.portals.append({
            "id": portal_id, "name": name, "type": "map-transition",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "destinationMap": destination, "radius": 3.5,
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
        generator="Eloria Manymouth Delta builder (original procedural assets)")
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
                      - DK.MATERIALS)
    if unpinned:
        raise SystemExit(
            "materials used but not in deltakit.MATERIALS: "
            + ", ".join(unpinned))
    # The other direction is not an error but it is not free either: every
    # pinned material embeds its textures whether or not a mesh references it.
    # Amberwood's pin carries six such and pays 2.79 MB for them.
    # Read through the ground copies here too: a material the terrain
    # now draws with an alpha-tested copy is still referenced, and
    # calling it dead weight would invite trimming a pin the copy
    # depends on.
    unused = sorted(DK.MATERIALS
                    - {MAT.base_material(name) for name in used})
    if unused:
        print("[materials] WARNING pinned but unreferenced, costing bytes: "
              + ", ".join(unused))

    # Pinned by name to the materials Crownwater actually uses. Without `only=`
    # the package embeds the whole shared library - about ten megabytes of forest
    # and burnt-country textures this region never references - and, worse, its
    # contents would change whenever another region appends to the shared table.
    MAT.register_gltf_materials(builder, sets, only=DK.MATERIALS)
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

    root = GLTF.Node("ManymouthDelta")
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
COLLISION_HEIGHT_LEVELS = 63
# Metres of rise per metre travelled that a walker will not climb. Eternal
# Lands allows two 0.2 m stages across a half-metre tile, which is this.
MAX_WALK_GRADIENT = 1.0


def build_collision(build: REG.RegionBuild) -> tuple[bytes, int, int, dict]:
    """Half-metre walkability grid over the server footprint (EWCG version 1)."""
    t = build.terrain
    width = height = int(round(REG.SERVER_CELLS*REG.METRES_PER_TILE/COLLISION_CELL))
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

    actual_terrain = (gx>=t.x0)&(gx<=t.xs[-1])&(gz>=t.z0)&(gz<=t.zs[-1])
    walkable = actual_terrain & (ground > REG.SEA_LEVEL + 0.35) & (slope < 1.05)
    # solid structures block their footprint
    blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if not placement.collides:
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
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
    decks,top=GLB.rasterise(walk_triangles(build),width,height,
                           REG.PLAY_MIN_X,REG.SERVER_ORIGIN[1],COLLISION_CELL)
    surface=np.where(decks,np.maximum(ground,top),ground)
    walkable |= decks
    elevated=sum(bool(getattr(build.meshes[p.mesh],"walk_parts",[])) for p in build.placements)
    # Closed houses remain solid, including where their verandas are Walk_.
    for p in build.placements:
        if p.kind!="building" or not p.collides:continue
        px,_,pz=p.position;c,sn=math.cos(p.rotation_y),math.sin(p.rotation_y)
        lx=c*(gx-px)-sn*(gz-pz);lz=sn*(gx-px)+c*(gz-pz)
        shut=(abs(lx)<2.45)&(abs(lz)<2.15)
        walkable &= ~shut
        decks &= ~shut

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
    # Water cells are not merely blocked: the bed under them is real geometry
    # at a known depth, so a swim or aquatic-form traversal mode can be added
    # without rebuilding the package. Counted and described here rather than
    # encoded, because EWCG v1 has no spare bit and inventing v2 for a flag no
    # client reads yet would be worse. The rule is derivable by any consumer:
    # a zero cell whose terrain sample is below sea level is water, not wall.
    swimmable = (~walkable) & (ground < REG.SEA_LEVEL)

    stats = {
        "width": width, "height": height, "cellMetres": COLLISION_CELL,
        "walkableCells": int(walkable.sum()),
        "swimmableCells": int(swimmable.sum()),
        "swimmableFraction": round(float(swimmable.mean()), 4),
        "meanWaterDepth": round(float((REG.SEA_LEVEL - ground)[swimmable].mean())
                                if swimmable.any() else 0.0, 2),
        "maxWaterDepth": round(float((REG.SEA_LEVEL - ground)[swimmable].max())
                               if swimmable.any() else 0.0, 2),
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


def minimap_metadata(build,path):
    low,high=(COMPACT.BOUNDS if hasattr(build,'compact_revision') else
        [[REG.PLAY_MIN_X,REG.PLAY_MIN_Z],[REG.PLAY_MAX_X,REG.PLAY_MAX_Z]])
    size=[round(high[i]-low[i]) for i in range(2)]
    return {'image':path.name,'imageSize':size,'pixelsPerMetre':1.,'worldMin':low,'worldMax':high,
        'northAxis':'-Z','orientation':'north-up','projection':'orthographic-top-down',
        'renderedFrom':'actual packaged geometry','transform':{
            'pixelX':{'scale':1.,'offset':-low[0]},'pixelY':{'scale':1.,'offset':-low[1]}},
        'file':path.name,'size':size,'metresPerPixel':1.,
        'centre':[(low[i]+high[i])/2 for i in range(2)],'northUp':True}


def render_minimap(build: REG.RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down orthographic-ish capture of the finished geometry."""
    import preview
    scene = preview.scene_from_build(build, sets)
    metadata=minimap_metadata(build,path)
    centre_x,centre_z=metadata['centre']
    width,height=metadata['imageSize']
    extent=max(width,height)
    altitude = 900.0
    fov = 2.0 * math.degrees(math.atan((height * 0.5) / altitude))
    lighting = RENDER.Lighting(sun_direction=(-0.30, 0.90, 0.32),
                               fog_density=0.0, ambient_strength=0.72,
                               shadow_strength=0.35, sun_color=(1.10, 0.96, 0.74))
    image = scene.render(eye=(centre_x, altitude, centre_z + 0.01),
                         target=(centre_x, 0.0, centre_z),
                         width=width, height=height, fov=fov, lighting=lighting,
                         shadows=True, shadow_size=2048,
                         shadow_center=(centre_x, 20.0, centre_z),
                         shadow_radius=extent * 0.62, near=200.0, far=1400.0)
    image.save(path, "WEBP", quality=88, method=5)
    return metadata


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

    entries = []
    for (name, panel, eye_xz, eye_h, target_xz, target_h, fov, _size,
         _radius, mode) in VIEWTABLE.VIEWS:
        ex, ez = eye_xz[0] * REG.SCALE, eye_xz[1] * REG.SCALE
        tx, tz = target_xz[0] * REG.SCALE, target_xz[1] * REG.SCALE
        if hasattr(build,'compact_revision'):
            ex,ez=float(COMPACT.PLAN.x(ex)),float(COMPACT.PLAN.z(ez))
            tx,tz=float(COMPACT.PLAN.x(tx)),float(COMPACT.PLAN.z(tz))
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
            ey=walk_surface_at(build,ex,ez)+eye_h
            ty=walk_surface_at(build,tx,tz)+target_h
        elif mode != "submerged":
            ey = max(ey, REG.SEA_LEVEL + 0.6)
            ey = clear_eye(ex, ey, ez)
        fixed=getattr(VIEWTABLE,"WORLD_VIEWS",{}).get(name)
        if fixed:
            (ex,ey,ez),(tx,ty,tz)=fixed
            if hasattr(build,'compact_revision'):
                ex,ey,ez=COMPACT.PLAN.point([ex,ey,ez]);tx,ty,tz=COMPACT.PLAN.point([tx,ty,tz])
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
                   minimap: dict, path: Path, network: dict) -> dict:
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
            "id": "manymouth_delta",
            "name": "Manymouth Delta",
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
            # See traversal-modes.md. Not a second binary and not a format
            # change: a derivable classification of the cells this grid already
            # marks unwalkable, so an aquatic traversal mode has the numbers it
            # needs without this package being rebuilt.
            "swimmable": {
                "rule": ("a cell whose grid value is 0 and whose terrain "
                         "height is below asset.seaLevel is water, not wall"),
                "cells": collision_stats["swimmableCells"],
                "fraction": collision_stats["swimmableFraction"],
                "meanDepthMetres": collision_stats["meanWaterDepth"],
                "maxDepthMetres": collision_stats["maxWaterDepth"],
            },
        },
        "navigation": {
            "crossings": [{"id":a+"--"+b,"endpoints":LAY.RC.crossing_endpoints(stations.tolist())}
                      for a,b,stations,_ in network["surveys"]],
            "surfaceNodePrefixes": surface_prefixes,
            "walkableAreas": ["bars", "sandbars", "walkways", "quays",
                              "landings", "stairs", "temple-stair",
                              "paddy-causeways"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every built "
                "walkable surface is named Walk_<...>. The client turns both "
                "into the navigation collision layer the grounding ray tests.",
                "Walkway decks, quays and landings are walk surfaces, so a "
                "downward grounding ray under one resolves onto the deck "
                "above; the channel beneath them is water and is not walkable. "
                "This region's walkway network IS its road network - there are "
                "no graded roads at all - so a large fraction of the reachable "
                "walkable area is elevated deck rather than ground.",
                "The delta floor is terrain and carries the Terrain_ prefix "
                "everywhere, including below sea level. That is deliberate: the "
                "client casts its grounding ray at every server tile, not only "
                "walkable ones, so a region that is two-thirds water still "
                "needs a continuous surface underneath it. Those tiles ground "
                "successfully and are marked unwalkable in collision.bin.",
                "Water tiles are recorded as swimmable rather than merely "
                "blocked (see collision.swimmable and traversal-modes.md): the "
                "bed height is real everywhere, so a future swim or aquatic "
                "traversal mode has a surface to work against without the "
                "package being rebuilt.",
            ],
        },
        "landmarks": build.landmarks,
        "interactives": build.interactives,
        "npcMarkers": build.npc_markers,
        "harvestables": build.harvestables,
        "portals": build.portals,
        # This region has no roads in the Amberwood sense at all. Its routes
        # are plank walkways on piles over open water, so a waypoint's height
        # comes from the deck, never from the channel floor it crosses.
        "contentLayout": getattr(build,'content_layout',LAY.CONTENT_LAYOUT),
        "roads": [{"id":a+"--"+b,"type":"walkway","surface":"plank",
                   "waypoints":np.round(stations,3).tolist()}
                  for a,b,stations,_ in network["surveys"]],
        "water": {
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": REG.SERVER_CELLS,
            "bodies": [{"id": name, "node": name,
                        "type": "deep-channel" if "Deep" in name else "delta"}
                       for name in build.water_meshes],
            "streams": [],
            # The named distributaries. `deep` ones are dredged to the channel
            # floor and are the routes a boat can actually take across the map.
            "channels": [
                {"id": name, "type": ("navigable" if name in REG.DEEP_ROUTES
                                      else "shallow-braid"),
                 "floor": (REG.CHANNEL_FLOOR if name in REG.DEEP_ROUTES
                           else round(REG.DELTA_FLOOR - 2.5, 2)),
                 "waypoints": [[round(float(p[0]), 1), REG.SEA_LEVEL,
                                round(float(p[1]), 1)]
                               for p in points]}
                for name, points in REG.DISTRIBUTARIES.items()],
            "depths": {
                "barFlat": REG.DELTA_FLOOR,
                "navigableChannel": REG.CHANNEL_FLOOR,
                "openSea": REG.SEA_FLOOR,
                "whirlpool": REG.WHIRL_FLOOR,
            },
        },
        "environment": {
            # Tuned to the concept: a high bright sky, a strong near-vertical
            # sun that drives the turquoise out of shallow water, and very
            # little fog - the painting's distances stay clear and saturated.
            "sky": {"type": "gradient", "zenith": [0.20, 0.46, 0.70],
                    "horizon": [0.86, 0.86, 0.78], "curve": 0.18,
                    "groundHorizon": [0.44, 0.58, 0.52],
                    "groundBottom": [0.14, 0.26, 0.24],
                    "sunAngleMax": 16.0, "energy": 1.14},
            # `direction` is the direction the light TRAVELS, not the direction
            # of the sun in the sky: the binder does
            # `sun.look_at_from_position(ZERO, direction)`, and a
            # DirectionalLight3D emits along its local -Z. A +Y component
            # therefore lights the world from underneath. The first in-client
            # capture of this region came back lit from below and reading as
            # night; Amberwood's manifest still declares +Y and has never been
            # rendered through this path.
            # The aerial is lit late and low from the west-north-west, which
            # is what puts the warm rim on every island and the long glitter
            # across the water. Kept as the default rather than as a variant.
            "sun": {"direction": [0.62, -0.58, 0.53],
                    "color": [1.22, 1.04, 0.82], "energy": 1.12,
                    "indirectEnergy": 1.15, "angularDiameterDegrees": 1.2},
            "ambient": {"color": [0.48, 0.66, 0.68], "energy": 0.56,
                        "skyContribution": 0.75},
            "saturation": 1.34,
            "fog": {"enabled": True, "color": [0.72, 0.80, 0.76],
                    "density": 0.00055, "heightFalloff": 0.0026},
            "variants": {
                "monsoon": {
                    "sun": {"direction": [0.30, -0.86, 0.42],
                            "color": [0.86, 0.90, 0.92], "energy": 0.62},
                    "fog": {"enabled": True, "color": [0.68, 0.74, 0.74],
                            "density": 0.0026},
                },
                "night": {
                    "sun": {"direction": [0.40, -0.72, 0.56],
                            "color": [0.34, 0.46, 0.68], "energy": 0.16},
                    "fog": {"enabled": True, "color": [0.10, 0.18, 0.24],
                            "density": 0.0018},
                },
            },
            "water": {
                "shallowColor": [0.30, 0.80, 0.71],
                "deepColor": [0.03, 0.20, 0.26],
                "causticsEnabled": True,
                "note": ("Shallow/deep tint and caustics are presentation "
                         "settings for whoever writes the water shader; the "
                         "GLB ships a flat lit plane."),
            },
            "presentation": {
                "gulls": {"enabled": True, "density": 0.62,
                          "zones": ["open-delta", "sea-reach"]},
                "mist": {"enabled": True, "density": 0.22,
                         "zones": ["mangrove-reach"]},
                "spray": {"enabled": False},
                "bannerWind": {"enabled": True, "strength": 0.38},
                "ambientAudio": [
                    {"id": "channel-lap", "zone": "open-delta"},
                    {"id": "town-quay", "zone": "stilt-town"},
                    {"id": "insects", "zone": "mangrove-reach"},
                    {"id": "arch-hum", "zone": "the-arch"},
                    {"id": "surf", "zone": "sea-reach"}],
            },
            "zones": [
                {"id": "stilt-town",
                 "centre": [round(REG.ANCHORS["stilt_town"][0], 1), 3.0,
                            round(REG.ANCHORS["stilt_town"][1], 1)],
                 "radius": 96.0},
                {"id": "the-arch",
                 "centre": [round(REG.ANCHORS["great_arch"][0], 1), 2.0,
                            round(REG.ANCHORS["great_arch"][1], 1)],
                 "radius": 78.0},
                {"id": "mangrove-reach",
                 "centre": [round(REG.ANCHORS["mangrove_reach"][0], 1), 1.0,
                            round(REG.ANCHORS["mangrove_reach"][1], 1)],
                 "radius": 120.0},
                {"id": "paddy-country",
                 "centre": [round(REG.ANCHORS["paddy_terraces"][0], 1), 2.0,
                            round(REG.ANCHORS["paddy_terraces"][1], 1)],
                 "radius": 130.0},
                {"id": "temple-rim",
                 "centre": [round(REG.ANCHORS["green_temple"][0], 1), 12.0,
                            round(REG.ANCHORS["green_temple"][1], 1)],
                 "radius": 110.0},
                {"id": "sea-reach",
                 "centre": [round(REG.ANCHORS["sea_landing"][0], 1), 0.0,
                            round(REG.ANCHORS["sea_landing"][1], 1)],
                 "radius": 200.0},
                {"id": "open-delta", "centre": [114.0, 0.0, -114.0],
                 "radius": 420.0},
            ],
            # Traversal modes this region is authored to support but the client
            # does not implement yet. Recorded here rather than in prose alone so
            # whoever builds them has the numbers. See traversal-modes.md.
            "traversal": {
                "walk": {"available": True},
                "swim": {
                    "available": False,
                    "reason": "no client swim state yet",
                    "surfaceLevel": REG.SEA_LEVEL,
                    "authoredFor": True,
                    "note": ("Every water tile has real bed geometry beneath "
                             "it and is flagged swimmable in collision.bin's "
                             "companion mask, so a swim mode needs no rebuild "
                             "of this package."),
                },
                "dive": {
                    "available": False,
                    "authoredFor": True,
                    "maxDepth": REG.WHIRL_FLOOR,
                    "note": ("The whirlpool under the arch, the dredged "
                             "channels and the sunken stelae are modelled below "
                             "the water line and are lit as if seen through "
                             "water."),
                },
            },
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
            {"id": "generator", "file": "source/build_manymouth_delta.py",
             "role": "reproducible-build", "seed": SEED},
        ],
        "provenance": {
            "assets": "original to Eloria/Nymara; generated by _toolkit/amberwood/* plus source/deltakit.py and source/stiltkit.py",
            "thirdParty": "none",
            "textures": "procedural (numpy + Pillow), no sampled or traced source",
            "geometry": "procedural (numpy), no imported models",
            "license": "same as the Eloria client repository",
        },
        "productionStatus": "production-geometry-materials-population",
        "knownLimitations": [],
    }
    if hasattr(build,'compact_revision'):
        manifest['compactLandscape']=build.compact_report
        manifest['asset']['mapBounds']={'min':[COMPACT.BOUNDS[0][0],float(t.height.min()),COMPACT.BOUNDS[0][1]],
            'max':[COMPACT.BOUNDS[1][0],float(t.height.max()),COMPACT.BOUNDS[1][1]]}
        for channel in manifest['water']['channels']:
            channel['waypoints']=[COMPACT.PLAN.point(point) for point in channel['waypoints']]
    import contentposts
    contentposts.apply_runtime(manifest,PACKAGE)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PACKAGE))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--skip-minimap", action="store_true")
    parser.add_argument("--skip-lod2", action="store_true")
    parser.add_argument("--prototype", action="store_true", help="Export compact native prototype without shared geography")
    parser.add_argument("--legacy-native", action="store_true", help="Read-only comparison source composition before compaction")
    args = parser.parse_args()
    out = Path(args.out)
    if args.prototype and out.resolve()==PACKAGE.resolve():
        parser.error('--prototype requires a separate --out directory')
    out.mkdir(parents=True, exist_ok=True)

    import preview
    sets = DK.register(preview.texture_sets())

    build = build_region(args.seed,prototype=args.prototype,legacy=args.legacy_native)

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

    minimap = minimap_metadata(build,out/'minimap.webp')
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
                              out / "world.json", build.network)
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
        lod_sets = DK.register(lod_sets)
        lod_build = build_region(args.seed, lod="far",prototype=args.prototype,legacy=args.legacy_native)
        # build_region has already produced and partitioned the far terrain.
        # Rebuilding it here would discard shared cells and causeway deck skins.
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
