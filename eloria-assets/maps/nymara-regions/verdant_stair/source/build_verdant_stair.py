#!/usr/bin/env python3
"""Build the Verdant Stair runtime map package.

Outputs, next to this source tree:

    ../world.glb        self-contained glTF 2.0 (geometry, materials, textures)
    ../world.json       GLB world manifest, schema version 1
    ../collision.bin    half-metre walkability grid (EWCG v1)
    ../minimap.webp     minimap rendered from the final geometry
    ../world.glb.validator.json
    ../performance-summary.md

Deterministic: the same seed reproduces the same bytes.

    python3 build_verdant_stair.py --stage terrain   # terrain and water only
    python3 build_verdant_stair.py                   # the whole package
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np

# The authoring toolkit is shared by every region and lives two levels up, in
# `maps/nymara-regions/_toolkit/`. It must be on the path before the toolkit
# modules below are imported.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_gltf
from regionbuild import Placement, RegionBuild

from amberwood import gltf as GLTF
from amberwood import materials as MAT
from amberwood import mesh as M
from amberwood import routecraft as RC
from amberwood import render as RENDER
from amberwood import terrain as TER

import populate as POP
import region as REG
import landscape_plan as PLAN
import streaming_borders as SB
import transitions as MARCH
import secretdoors as SD
import secrets_design as SEC
import loresites as LORE

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
SEED = 20260829
# Class islands smaller than this are given to whatever surrounds them. Six
# two-metre cells is 24 m2 - smaller than any surface a player is meant to read
# as its own thing, and larger than every crumb the thresholded noise and the
# boundary dither leave behind.
DESPECKLE_MIN_CELLS = 6

# The materials Verdant Stair embeds, pinned. The shared table grows as other
# regions add recipes to it, and without this every one of those would be
# embedded here too - about fifteen megabytes of images nothing references, and
# a different world.glb for a change that has nothing to do with this region.
# Verified against the built GLB by `export_glb`, which warns on any pinned
# material no mesh actually points at.
# The two ways out of the stair, as region-connections.json declares them:
# the west quay gate along the coast to the Ssarathi temple causeways, and
# the east pass up over the ridge onto the Sunmane Steppe. Temple stelae line
# the west road; steppe grass and wind-banners come down the east pass.
CROSSINGS = [
    MARCH.Crossing("west-quay-gate", "ssarathi_ruins", REG.ANCHORS["westgate"],
                   (REG.PLAY_MIN_X - 20.0, REG.ANCHORS["westgate"][1]),
                   radius=40.0, name="The Temple Road March"),
    MARCH.Crossing("east-pass-gate", "sunmane_steppe", REG.ANCHORS["east_pass"],
                   (REG.PLAY_MAX_X + 20.0, REG.ANCHORS["east_pass"][1]),
                   radius=46.0, name="The Steppe Pass"),
]

# The places the region's people argue about (see loresites.py).
SITES = [
    LORE.Site("moved-anchor", "The Moved Anchor", "moved_anchor", PLAN.ground_point((133.0, -50.0)),
              thread="J", clearing=11.0,
              note="The stair's anchor stone on log rollers with the ropes still on it, and the "
                   "socket it was levered out of a few metres upslope."),
]
MARCH_MATERIALS: dict = dict(REG.SURFACE_MATERIALS)

MATERIALS = frozenset({
    # ground
    'verdant_jungle_floor', 'verdant_jungle_trail', 'verdant_terrace_stone',
    'verdant_mossy_stone', 'verdant_wet_limestone', 'verdant_limestone_cliff',
    'verdant_lagoon_sand', 'verdant_fern_glade',
    # water
    'water_lagoon', 'water_cenote', 'water_stream',
    # architecture
    'verdant_jade', 'verdant_carved_jade', 'rubble_stone', 'ashlar',
    'gilt_brass', 'dark_iron',
    # timber, rope and thatch
    'timber_warm', 'timber_grey', 'timber_dark', 'carved_wood', 'thatch_reed',
    'verdant_rope',
    # the one warm note in a green region: lantern glass and brazier embers,
    # which the reused lamp posts and hanging lanterns carry
    'amber_resin',
    # vegetation
    'bark_pale', 'bark_dark', 'foliage_green', 'verdant_frond', 'verdant_vine',
    'undergrowth',
}) | MARCH.materials_for("verdant_stair", CROSSINGS) | SD.materials(SEC) | LORE.materials([s.piece for s in SITES]) | SB.materials_for("verdant_stair")

ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# The region's four insides live on one map with blackspace between them, so
# every door targets the same map key and differs only in which arrival it asks
# for. See `source/interiors.py` and `interiors/verdant_stair_insides/`.
INTERIOR_MAP = "verdant_stair_insides"
INTERIOR_DOORS = (
    # portal id, name, landmark it belongs to, anchor, arrival on the insides map
    ("temple-sanctum-door", "The Green Sanctum", "great-temple", "great_temple",
     "temple-sanctum-door"),
    ("cenote-deeps-stair", "The Cenote Deeps", "cenote", "cenote",
     "cenote-deeps-stair"),
    ("banyan-hollow-arch", "The Banyan Hollow", "canopy-village",
     "canopy_village", "banyan-hollow-arch"),
    ("stair-quarry-adit", "The Stair Quarry", "quarry", "quarry",
     "stair-quarry-adit"),
    ("physick-still-door", "Tessara's Still Room", "herbalist", "herbalist",
     "physick-still-door"),
    ("anchor-hollow-mouth", "The Anchor Hollow", "fern-camp", "fern_camp",
     "anchor-hollow-mouth"),
    ("nine-lost-door", "The Shrine of the Nine Lost", "south-quay", "south_quay",
     "nine-lost-door"),
)


# --------------------------------------------------------------------------
def build_region(seed: int = SEED, lod: str | None = None,
                 stage: str = "full") -> RegionBuild:
    """Build the region.

    `lod="far"` produces the reduced second package: every plant at its far
    tier and no ground clutter. `stage="terrain"` stops after terrain and
    water, which is the gate the production guide asks for - grounding has to
    be proved on the heightfield before any detail work is done on top of it.
    """
    t0 = time.time()
    terrain = REG.build_terrain(seed)
    REG.apply_built_ground(terrain, seed)
    build = RegionBuild(terrain=terrain)

    if stage != "terrain":
        MARCH.prepare(terrain, CROSSINGS)
        LORE.prepare(terrain, SITES, sea_level=getattr(REG, "SEA_LEVEL", 0.0), keep=(TER.SHORE, TER.WET_ROCK))
        REG.prepare_access(terrain)
        POP.populate_stair(build, seed)
        POP.populate_landmarks(build, seed)
        POP.populate_crossings(build, seed)
        POP.populate_settlements(build, seed)
        POP.populate_terrace_architecture(build, seed)
        POP.populate_jungle(build, seed, lod=lod)
        if lod is None:
            POP.populate_understory(build, seed)
            POP.populate_ground_detail(build, seed)
    POP.build_water(build, seed)
    if stage != "terrain":
        # The marches: the neighbours' country coming in along the roads out.
        MARCH.paint(terrain, CROSSINGS, MARCH_MATERIALS, seed, sea_level=REG.SEA_LEVEL,
                    keep=(TER.SHORE, TER.WET_ROCK))
        march = MARCH.dress(build, "verdant_stair", CROSSINGS, seed, sea_level=REG.SEA_LEVEL)
        LORE.dress(build, terrain, SITES, seed)
        SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
        build.landmarks.extend(march.landmarks)
        build.notes.extend(march.notes)
        PLAN.inhabited_details(build, seed)

    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.26, materials=MARCH_MATERIALS, blend_edges=True,
        material_suffix=MAT.GROUND_SUFFIX)
    build.terrain_meshes["Backdrop_Distant"] = TER.backdrop(
        terrain, reach=240.0, cell=11.0, seed=seed + 909,
        material="verdant_limestone_cliff", sea_level=REG.SEA_LEVEL,
        open_side="west", clip_interior=True)

    # `heightfield` gives the terrain a top-down planar UV, which is right for
    # ground and badly wrong for a cliff: a near-vertical face gets almost no
    # UV variation over tens of metres of height, so the bedded limestone
    # smears into a smooth pale ramp. This region is *made* of cliff faces -
    # seven risers and four gorges - so the rock classes get world-space
    # triplanar UVs instead, which hold a constant texel density whichever way
    # a face points. The flat classes keep the planar projection: it tiles
    # better on ground the player walks on.
    # Every class, not just the rock: the steepest faces in the region are the
    # *paved* route corridors cut through the risers, and they smeared just as
    # badly. Triplanar is free on flat ground - where the surface normal points
    # up it selects the same XZ plane the planar projection uses, at the same
    # 0.26 tiles per metre - so this changes nothing a player walks on and
    # fixes everything they climb past.
    for name, piece in build.terrain_meshes.items():
        if piece.triangle_count:
            piece.project_uv_triplanar(0.09 if name.startswith("Backdrop")
                                       else 0.26)
    build.resolve_names()
    bridge_ids = {row[0] for row in REG.CROSSINGS}
    RC.clear_walk_corridors(build,
        [crossing["endpoints"] for crossing in build.crossings if crossing["id"] in bridge_ids],
        {"tree": 18, "fern": 10, "undergrowth": 5, "vine": 9, "rock": 4})
    _add_spawns_and_portals(build)
    _add_population_markers(build, seed)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_outer'))
    import outer_aprons
    outer_snapshot = outer_aprons.capture(build, 'verdant_stair')
    SB.apply(build, "verdant_stair")
    outer_aprons.apply(build, 'verdant_stair', outer_snapshot)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    connector_finish.apply(build, 'verdant_stair')
    import north_burn
    north_burn.apply(build)
    import north_approach
    north_approach.apply(build)
    import verdant_paint
    verdant_paint.apply(build)
    print(f"[region] built in {time.time() - t0:.1f}s "
          f"({len(build.placements)} placements)")
    return build


def _server_tile(x: float, z: float) -> list[int]:
    return [int(round(x + REG.SERVER_ORIGIN[0])),
            int(round(REG.SERVER_ORIGIN[1] - z))]


def _walk_surface_at(build: RegionBuild, x: float, z: float) -> float:
    """The highest Walk_ surface under (x, z), else the terrain.

    A brute-force point-in-triangle test over the walk geometry. It is only ever
    called for the dozen or so spawns and portals in the manifest, so the cost
    does not matter and the exactness does: this is the number the client's
    grounding ray will produce, and the manifest claiming anything else is what
    `region_client_check.gd` reports as a spawn error.
    """
    best = float(build.terrain.height_at(x, z))
    point = np.array([x, z])
    for placement in build.placements:
        if placement.node.startswith("StreamView_"): continue
        item = build.meshes[placement.mesh]
        walk_parts = getattr(item, "walk_parts", None)
        if not walk_parts:
            continue
        low, high = item.bounds()
        scale = placement.scale
        px, py, pz = placement.position
        reach = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2]))) * scale
        if abs(x - px) > reach + 1.0 or abs(z - pz) > reach + 1.0:
            continue
        cos_y, sin_y = math.cos(placement.rotation_y), math.sin(placement.rotation_y)
        for piece in walk_parts:
            if piece.triangle_count == 0:
                continue
            vertices = piece.positions * scale
            # the placement's own rotation about Y, then its translation
            rx = vertices[:, 0] * cos_y + vertices[:, 2] * sin_y + px
            rz = -vertices[:, 0] * sin_y + vertices[:, 2] * cos_y + pz
            ry = vertices[:, 1] + py
            tri = np.stack([rx, ry, rz], axis=-1)[piece.indices].reshape(-1, 3, 3)
            ax, az = tri[:, 0, 0], tri[:, 0, 2]
            bx, bz = tri[:, 1, 0], tri[:, 1, 2]
            cx, cz = tri[:, 2, 0], tri[:, 2, 2]
            denominator = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            good = np.abs(denominator) > 1e-12
            if not good.any():
                continue
            w0 = np.where(good, ((bz - cz) * (point[0] - cx)
                                 + (cx - bx) * (point[1] - cz)) / np.where(good, denominator, 1.0), -1.0)
            w1 = np.where(good, ((cz - az) * (point[0] - cx)
                                 + (ax - cx) * (point[1] - cz)) / np.where(good, denominator, 1.0), -1.0)
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w0 + w1 <= 1.0 + 1e-6)
            if not inside.any():
                continue
            w2 = 1.0 - w0 - w1
            ys = w0 * tri[:, 0, 1] + w1 * tri[:, 1, 1] + w2 * tri[:, 2, 1]
            best = max(best, float(ys[inside].max()))
    return best


def _add_spawns_and_portals(build: RegionBuild) -> None:
    t = build.terrain
    for spawn_id, (x, z), facing in (
            ("default", REG.SPAWN, math.pi * 0.25),
            ("west-quay", REG.SPAWN_QUAY, math.pi * 0.75),
            ("temple-court", REG.SPAWN_TEMPLE, math.pi * 1.25)):
        # Not the terrain height: a spawn standing on a landmark's own deck
        # grounds on that deck in the client, and the manifest has to say the
        # number the client's ray will produce. The waygate is exactly this -
        # the default spawn stands on its platform, 0.54 m above the ground.
        y = _walk_surface_at(build, float(x), float(z))
        build.spawns.append({
            "id": spawn_id,
            "position": [round(float(x), 2), round(y + 0.05, 2), round(float(z), 2)],
            "serverTile": _server_tile(x, z),
            "rotationDegrees": round(math.degrees(facing), 1),
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})

    # CONTINENT.md: the coastal Temple Road enters from Ssarathi, and
    # the quarry shelf leaves through Steppe Pass to Sunmane.
    for portal_id, name, anchor, destination in (
            ("west-quay-gate", "Temple Road to the Ssarathi Ruins", "westgate",
             "ssarathi_ruins"),
            ("east-pass-gate", "Steppe Pass to the Sunmane", "east_pass",
             "sunmane_steppe")):
        x, z = REG.ANCHORS[anchor]
        y = float(t.height_at(x, z))
        build.portals.append({
            "id": portal_id, "name": name, "type": "map-transition",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "destinationMap": destination, "radius": 3.5,
            "authority": "server"})

    # Seven visible entrances share the insides map, with paired returns.
    for portal_id, name, landmark_id, anchor, spawn_id in INTERIOR_DOORS:
        x, z = REG.DOOR_POSITIONS.get(portal_id, REG.ANCHORS[anchor])
        y = _walk_surface_at(build, x, z)
        build.portals.append({
            "id": portal_id, "name": name, "type": "interior-entrance",
            "position": [round(x, 2), round(y + 0.1, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "landmark": landmark_id,
            "destinationMap": INTERIOR_MAP, "destinationSpawn": spawn_id,
            "radius": 2.5, "authority": "server"})
        build.spawns.append({
            "id": spawn_id,
            "name": f"Return from {name}",
            "position": [round(x, 2), round(y + 0.05, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "rotationDegrees": 45.0,
            "surface": TER.SURFACE_NAMES[int(t.surface_at(x, z))],
            "grounded": True})


def _add_population_markers(build: RegionBuild, seed: int) -> None:
    """Editor/visual markers only - the server owns actual spawning.

    Unlike Amberwood, this region's roster is not invented: every NPC, creature
    and harvestable below is taken from the server's own `config/eloria/*.txt`
    for `verdant_stair`, at the tile the server records, scaled from the 192-cell
    map to 576 by three. Where a recorded tile lands on water or on a cliff the
    marker is nudged to the nearest walkable cell and the move is recorded in
    `build.notes`.
    """
    t = build.terrain
    rng = REG.N.Rng(seed + 777)

    def ground(x: float, z: float, label: str) -> tuple[float, float, float]:
        """Nearest reasonable standing point to a recorded server tile."""
        best = (x, z, float(t.height_at(x, z)))
        if best[2] > REG.SEA_LEVEL + 0.5 and float(t.slope_at(x, z)) < 1.05:
            return best
        for radius in (6.0, 12.0, 20.0, 30.0, 44.0):
            for k in range(16):
                angle = math.pi * 2.0 * k / 16
                px = x + math.cos(angle) * radius
                pz = z + math.sin(angle) * radius
                if not (REG.PLAY_MIN_X <= px <= REG.PLAY_MAX_X
                        and REG.PLAY_MIN_Z <= pz <= REG.PLAY_MAX_Z):
                    continue
                py = float(t.height_at(px, pz))
                if py > REG.SEA_LEVEL + 0.5 and float(t.slope_at(px, pz)) < 1.05:
                    build.notes.append(
                        f"{label}: server tile {_server_tile(x, z)} is not "
                        f"standable on the built terrain; marker moved "
                        f"{radius:.0f} m to {_server_tile(px, pz)}")
                    return (px, pz, py)
        return best

    # -- NPCs, from config/eloria/npcs.txt --------------------------------
    for npc_id, label, role, tile in (
            ("tessara", "Tessara", "dialogue", (52, 60)),
            ("orru-moss", "Orru Moss", "shop", (64, 60))):
        x, z = PLAN.ground_point((tile[0] * 3.0 - 174, 174 - tile[1] * 3.0))
        x, z, y = ground(x, z, f"npc {npc_id}")
        build.npc_markers.append({
            "id": npc_id, "name": label, "type": "npc", "role": role,
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "source": "server config/eloria/npcs.txt",
            "authority": "server"})

    # -- creature groups, from config/eloria/spawns.txt -------------------
    creature_tiles: dict[str, list[tuple[int, int]]] = {}
    for species, tile in POP.SERVER_SPAWNS:
        creature_tiles.setdefault(species, []).append(tile)
    for species, tiles in creature_tiles.items():
        points = []
        for tx, tz in tiles:
            x, z = PLAN.ground_point((tx * 3.0 - 174, 174 - tz * 3.0))
            x, z, y = ground(x, z, f"creature {species}")
            points.append([round(x, 2), round(y, 2), round(z, 2)])
        centre = np.asarray(points, dtype=np.float64).mean(axis=0)
        spread = max(float(np.linalg.norm(
            np.asarray(points)[:, [0, 2]] - centre[[0, 2]], axis=1).max()), 8.0)
        build.npc_markers.append({
            "id": species, "type": "creature-group",
            "group": POP.CREATURE_GROUPS.get(species, "jungle-fauna"),
            "centre": [round(float(centre[0]), 2), round(float(centre[1]), 2),
                       round(float(centre[2]), 2)],
            "radius": round(spread, 1), "positions": points,
            "source": "server config/eloria/spawns.txt",
            "authority": "server"})

    # -- harvestables, from config/eloria/harvesting.txt -------------------
    for index, (node_id, resource, tile) in enumerate(POP.SERVER_HARVEST, start=1):
        x, z = PLAN.ground_point((tile[0] * 3.0 - 174, 174 - tile[1] * 3.0))
        x, z, y = ground(x, z, f"harvestable {resource}")
        build.harvestables.append({
            "id": f"{resource.lower().replace(' ', '-')}-{index:02d}",
            "resource": resource,
            "category": POP.HARVEST_CATEGORIES.get(resource, "reagent"),
            "serverNode": node_id,
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "source": "server config/eloria/harvesting.txt",
            "authority": "server"})

    # -- interactives, from config/eloria/interactives.txt ------------------
    for node_id, kind, label, tile in POP.SERVER_INTERACTIVES:
        x, z = PLAN.ground_point((tile[0] * 3.0 - 174, 174 - tile[1] * 3.0))
        x, z, y = ground(x, z, f"interactive {kind}")
        build.interactives.append({
            "id": f"{kind}-{node_id}", "type": kind, "name": label,
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "serverTile": _server_tile(x, z),
            "radius": 2.0,
            "source": "server config/eloria/interactives.txt",
            "authority": "server"})
    del rng


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


def ensure_walk_faces_up(name: str, piece: M.Mesh) -> M.Mesh:
    """Flip a walk surface whose triangles all face downward.

    Godot builds the navigation layer as concave collision, which is one-sided
    for raycasts: a ray from y = 400 passes straight through a floor wound the
    wrong way and the actor grounds on whatever is underneath. Nothing else in
    the pipeline notices. `validate_gltf` is happy - the mesh is well formed -
    and `verify_runtime` casts against the same one-sided geometry, so it agrees
    with the client that the surface is not there.

    The waygate found this: `mesh.cylinder` with a radius that tapers *inward*
    winds its cap the other way, so the region's arrival platform had no
    upward-facing triangle on it at all and the default spawn grounded 0.54 m
    low on the terrain below. A box floor has downward triangles too - its
    underside - which is why the test is "no upward triangles", not "any
    downward ones".
    """
    if piece.triangle_count == 0:
        return piece
    tri = piece.positions[piece.indices].reshape(-1, 3, 3)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    good = lengths > 1e-9
    if not good.any():
        return piece
    up = normals[good, 1] / lengths[good]
    if (up > 0.35).any():
        return piece
    piece.flip_winding()
    piece.recompute_normals(60.0)
    print(f"[walk] {name}: no upward-facing triangle; winding flipped")
    return piece


def export_glb(build: RegionBuild, sets, path: Path,
               warn_unreferenced: bool = True) -> tuple[GLTF.GltfBuilder, dict]:
    builder = GLTF.GltfBuilder(
        generator="Eloria Verdant Stair builder (original procedural assets)")
    active_materials = MATERIALS | getattr(build, "vista_materials", set())
    MAT.register_gltf_materials(builder, sets, only=active_materials)
    MAT.register_ground_materials(
        builder, sets,
        {piece.material
         for piece in build.terrain_meshes.values()})

    # An over-broad pin is completely silent: the package simply carries
    # textures nothing references. Say so, or it happens again.
    used_materials = set()
    for bucket in (build.terrain_meshes, build.water_meshes):
        for piece in bucket.values():
            for part in (getattr(piece, "parts", None) or [piece]):
                if part.triangle_count:
                    used_materials.add(part.material)
    for item in build.meshes.values():
        parts = (getattr(item, "parts", []) + getattr(item, "walk_parts", [])
                 or [item])
        for part in parts:
            if part.triangle_count:
                used_materials.add(part.material)
    missing = sorted({MAT.base_material(name) for name in used_materials}
                     - set(active_materials))
    if missing:
        raise SystemExit(
            "[materials] these are referenced by geometry but not pinned, so "
            "the GLB would point at materials it does not carry: "
            + ", ".join(missing))
    # Read through the ground copies here too: a material the terrain
    # now draws with an alpha-tested copy is still referenced, and
    # calling it dead weight would invite trimming a pin the copy
    # depends on.
    unreferenced = sorted(set(active_materials)
                          - {MAT.base_material(name)
                             for name in used_materials})
    if warn_unreferenced and unreferenced:
        print(f"[materials] WARNING: {len(unreferenced)} pinned but unreferenced "
              f"in {path.name}: " + ", ".join(unreferenced))

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
            builder.add_mesh(name, prepare(ensure_walk_faces_up(name, piece)),
                             with_tangents=False)
            walk_names.append(name)
        exported[key] = (solid_names, walk_names)

    root = GLTF.Node("VerdantStair")
    root_index = builder.add_node(root)
    groups = {}
    for group_name in ("Terrain", "Water", "Jungle", "Structures", "Props",
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
        "tree": "Jungle", "foliage": "Jungle", "undergrowth": "Jungle",
        "vine": "Jungle", "fern": "Jungle", "fallenlog": "Jungle",
        "stump": "Jungle", "rock": "Jungle", "leafdrift": "Jungle",
        "building": "Structures", "landmark": "Structures",
        "bridge": "Structures", "stair": "Structures",
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


def build_collision(build: RegionBuild) -> tuple[bytes, int, int, dict]:
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
    blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if not placement.collides:
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        # plants block only their stem, not the spread of their canopy
        footprint = float(max(abs(low[0]), abs(high[0]), abs(low[2]),
                              abs(high[2]))) * placement.scale
        factor = 0.16 if placement.kind in ("tree", "foliage", "fern") else 0.62
        radius = min(max(footprint * factor, 0.40), 11.0)
        px, _, pz = placement.position
        blockers |= (np.hypot(gx - px, gz - pz) < radius)
    walkable &= ~blockers

    surface = ground.copy()
    decks = np.zeros_like(walkable)
    # An overhead walk surface owns its footprint: the client grounds an actor
    # on the highest walk surface below the ray, so a two-level column cannot be
    # expressed on a flat server grid. Bridges, decks and stairs therefore take
    # the cell, and the ground under them is not separately walkable.
    #
    # Rasterised triangle by triangle against the cell centre, not stamped as a
    # disc over the placement's bounding radius. A disc is right for a bridge
    # deck and wrong for anything with a hole in it: the cenote's spiral stair
    # winds around an open eighteen-metre shaft, and the disc laid a floor
    # straight across it - cells the server would let a player walk onto and the
    # client would drop them through. It is also wrong in the small for every
    # stair, because a disc is flat and a stair is not: the height came from the
    # top of the walk bounds, so the whole flight read as its own landing.
    elevated = 0
    z_top = REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE
    for placement in build.placements:
        if placement.node.startswith("StreamView_"): continue
        item = build.meshes[placement.mesh]
        walk_parts = getattr(item, "walk_parts", None)
        if not walk_parts:
            continue
        cos_y = math.cos(placement.rotation_y)
        sin_y = math.sin(placement.rotation_y)
        px, py, pz = placement.position
        touched = False
        for piece in walk_parts:
            if piece.triangle_count == 0:
                continue
            vertices = piece.positions * placement.scale
            wx = vertices[:, 0] * cos_y + vertices[:, 2] * sin_y + px
            wz = -vertices[:, 0] * sin_y + vertices[:, 2] * cos_y + pz
            wy = vertices[:, 1] + py
            tri = np.stack([wx, wy, wz], axis=-1)[piece.indices].reshape(-1, 3, 3)
            normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            lengths = np.linalg.norm(normals, axis=1)
            keep = lengths > 1e-9
            tri, normals, lengths = tri[keep], normals[keep], lengths[keep]
            if len(tri) == 0:
                continue
            # A riser is not a floor. Tested on the absolute normal because the
            # source geometry may be wound either way - `ensure_walk_faces_up`
            # corrects that at export, and a floor is a floor either side up.
            tri = tri[np.abs(normals[:, 1] / lengths) > 0.55]
            if len(tri) == 0:
                continue
            cx0 = np.clip(np.floor((tri[:, :, 0].min(axis=1) - REG.PLAY_MIN_X)
                                   / COLLISION_CELL), 0, width - 1).astype(int)
            cx1 = np.clip(np.floor((tri[:, :, 0].max(axis=1) - REG.PLAY_MIN_X)
                                   / COLLISION_CELL), 0, width - 1).astype(int)
            cz0 = np.clip(np.floor((z_top - tri[:, :, 2].max(axis=1))
                                   / COLLISION_CELL), 0, height - 1).astype(int)
            cz1 = np.clip(np.floor((z_top - tri[:, :, 2].min(axis=1))
                                   / COLLISION_CELL), 0, height - 1).astype(int)
            for i in range(len(tri)):
                rows = np.arange(cz0[i], cz1[i] + 1)
                columns = np.arange(cx0[i], cx1[i] + 1)
                if rows.size == 0 or columns.size == 0:
                    continue
                cell_x = REG.PLAY_MIN_X + (columns + 0.5) * COLLISION_CELL
                cell_z = z_top - (rows + 0.5) * COLLISION_CELL
                mx, mz = np.meshgrid(cell_x, cell_z)
                a, b, c = tri[i, 0], tri[i, 1], tri[i, 2]
                d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                if abs(d) < 1e-12:
                    continue
                w0 = ((b[2] - c[2]) * (mx - c[0])
                      + (c[0] - b[0]) * (mz - c[2])) / d
                w1 = ((c[2] - a[2]) * (mx - c[0])
                      + (a[0] - c[0]) * (mz - c[2])) / d
                w2 = 1.0 - w0 - w1
                # A small negative tolerance closes the seam between two
                # triangles sharing an edge, which would otherwise leave a line
                # of cells no triangle owns down the middle of every deck.
                inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
                if not inside.any():
                    continue
                heights = w0 * a[1] + w1 * b[1] + w2 * c[1]
                block_rows = rows[:, None].repeat(columns.size, axis=1)[inside]
                block_columns = columns[None, :].repeat(rows.size, axis=0)[inside]
                current = surface[block_rows, block_columns]
                taller = heights[inside] > current
                surface[block_rows[taller], block_columns[taller]] = \
                    heights[inside][taller]
                walkable[block_rows, block_columns] = True
                decks[block_rows, block_columns] = True
                touched = True
        if touched:
            elevated += 1

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
    # The un-quantised surface, kept for `snap_to_walkable`: a doorway attached
    # to a landmark stands on that landmark's own deck, and the manifest Y has
    # to be the surface the client's grounding ray will actually hit.
    build.collision_surface = surface
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


def _walk_surface_at(build: RegionBuild, x: float, z: float) -> float:
    """The highest Walk_ surface under (x, z), else the terrain.

    A brute-force point-in-triangle test over the walk geometry. It is only ever
    called for the dozen or so spawns and portals in the manifest, so the cost
    does not matter and the exactness does: this is the number the client's
    grounding ray will produce, and the manifest claiming anything else is what
    `region_client_check.gd` reports as a spawn error.
    """
    best = float(build.terrain.height_at(x, z))
    point = np.array([x, z])
    for placement in build.placements:
        if placement.node.startswith("StreamView_"): continue
        item = build.meshes[placement.mesh]
        walk_parts = getattr(item, "walk_parts", None)
        if not walk_parts:
            continue
        low, high = item.bounds()
        scale = placement.scale
        px, py, pz = placement.position
        reach = float(max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2]))) * scale
        if abs(x - px) > reach + 1.0 or abs(z - pz) > reach + 1.0:
            continue
        cos_y, sin_y = math.cos(placement.rotation_y), math.sin(placement.rotation_y)
        for piece in walk_parts:
            if piece.triangle_count == 0:
                continue
            vertices = piece.positions * scale
            # the placement's own rotation about Y, then its translation
            rx = vertices[:, 0] * cos_y + vertices[:, 2] * sin_y + px
            rz = -vertices[:, 0] * sin_y + vertices[:, 2] * cos_y + pz
            ry = vertices[:, 1] + py
            tri = np.stack([rx, ry, rz], axis=-1)[piece.indices].reshape(-1, 3, 3)
            ax, az = tri[:, 0, 0], tri[:, 0, 2]
            bx, bz = tri[:, 1, 0], tri[:, 1, 2]
            cx, cz = tri[:, 2, 0], tri[:, 2, 2]
            denominator = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            good = np.abs(denominator) > 1e-12
            if not good.any():
                continue
            w0 = np.where(good, ((bz - cz) * (point[0] - cx)
                                 + (cx - bx) * (point[1] - cz)) / np.where(good, denominator, 1.0), -1.0)
            w1 = np.where(good, ((cz - az) * (point[0] - cx)
                                 + (ax - cx) * (point[1] - cz)) / np.where(good, denominator, 1.0), -1.0)
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w0 + w1 <= 1.0 + 1e-6)
            if not inside.any():
                continue
            w2 = 1.0 - w0 - w1
            ys = w0 * tri[:, 0, 1] + w1 * tri[:, 1, 1] + w2 * tri[:, 2, 1]
            best = max(best, float(ys[inside].max()))
    return best


def snap_to_walkable(build: RegionBuild, payload: bytes, width: int,
                     height: int) -> list[str]:
    """Move any spawn or portal that landed on a blocked collision cell.

    A landmark that collides blocks its own footprint, and an interior doorway
    is attached to the landmark it belongs to - so a door placed at a landmark's
    anchor lands on a blocked cell more often than not. Amethyst Barrens found
    two of its four that way. Checking here rather than trusting the placement
    means the failure is a printed line at build time instead of a player
    standing in a wall.
    """
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)
    surface = getattr(build, "collision_surface", None)
    moved: list[str] = []

    def cell_of(x: float, z: float) -> tuple[int, int]:
        column = int(round((x - REG.PLAY_MIN_X) / COLLISION_CELL - 0.5))
        row = int(round((REG.SERVER_ORIGIN[1] * REG.METRES_PER_TILE - z)
                        / COLLISION_CELL - 0.5))
        return column, row

    def walkable(x: float, z: float) -> bool:
        column, row = cell_of(x, z)
        if not (0 <= column < width and 0 <= row < height):
            return False
        return bool(grid[row, column])

    def lift(entry) -> None:
        """Set the entry's Y to the walk surface the client will ground on.

        Not read out of the collision grid. `build_collision` stamps an
        elevated walk surface as a filled disc over its own footprint, which is
        right for a bridge deck and wrong for a ring: the cenote stair spirals
        around an open shaft, so the grid claims a floor across the middle of a
        hole and a door read eighteen metres high off it. This casts the same
        downward ray `Main._place_actor_on_surface` casts, against the same
        Walk_ geometry, over the handful of points that need it.
        """
        x, _, z = entry["position"]
        clearance = 0.1 if "destinationMap" in entry else 0.05
        entry["position"][1] = round(_walk_surface_at(build, x, z) + clearance, 2)

    surveyed = {s["portal"] for s in getattr(build, "streaming_borders", [])}
    for entry in list(build.spawns) + list(build.portals):
        if entry["id"] in surveyed: continue  # exposed shared decks are opened after raw collision
        x, _, z = entry["position"]
        if walkable(x, z):
            # An interior doorway is attached to the landmark it belongs to, and
            # that landmark usually has a walkable plinth or deck of its own. The
            # terrain height under it is therefore not where a character stands:
            # the temple door read 0.61 m low against the client's own grounding
            # ray until this took the height from the walk surface instead.
            lift(entry)
            continue
        best = None
        for radius in np.arange(1.0, 26.0, 1.0):
            for k in range(24):
                angle = math.pi * 2.0 * k / 24
                px = x + math.cos(angle) * float(radius)
                pz = z + math.sin(angle) * float(radius)
                if walkable(px, pz):
                    best = (px, pz, float(radius))
                    break
            if best:
                break
        if best is None:
            moved.append(f"{entry['id']}: on a blocked cell and no walkable cell "
                         f"within 25 m; left where it is")
            continue
        px, pz, distance = best
        entry["position"] = [round(px, 2),
                             round(float(build.terrain.height_at(px, pz))
                                   + (0.1 if "destinationMap" in entry else 0.05), 2),
                             round(pz, 2)]
        entry["serverTile"] = _server_tile(px, pz)
        lift(entry)
        moved.append(f"{entry['id']}: landed on a blocked collision cell; "
                     f"moved {distance:.1f} m to {entry['serverTile']}")
    return moved


# --------------------------------------------------------------------------
## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def render_minimap(build: RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down capture of the finished geometry, rendered not drawn."""
    import preview
    from copy import copy
    local = copy(build)
    local.placements = [p for p in build.placements if not p.node.startswith("StreamView_")]
    local.terrain_meshes = {k:v for k,v in build.terrain_meshes.items() if not k.startswith("StreamView_")}
    local.water_meshes = {k:v for k,v in build.water_meshes.items() if not k.startswith("StreamView_")}
    scene = preview.scene_from_build(local, sets)
    centre_x = (REG.PLAY_MIN_X + REG.PLAY_MAX_X) * 0.5
    centre_z = (REG.PLAY_MIN_Z + REG.PLAY_MAX_Z) * 0.5
    extent = max(REG.PLAY_MAX_X - REG.PLAY_MIN_X, REG.PLAY_MAX_Z - REG.PLAY_MIN_Z)
    if size <= 0:
        size = int(round(extent * MINIMAP_PIXELS_PER_METRE))
    altitude = 900.0
    fov = 2.0 * math.degrees(math.atan((extent * 0.5) / altitude))
    lighting = RENDER.Lighting(sun_direction=(-0.34, 0.88, 0.33),
                               fog_density=0.0, ambient_strength=0.74,
                               shadow_strength=0.38, sun_color=(1.08, 1.02, 0.86))
    image = scene.render(eye=(centre_x, altitude, centre_z + 0.01),
                         target=(centre_x, 40.0, centre_z),
                         width=size, height=size, fov=fov, lighting=lighting,
                         shadows=True, shadow_size=2048,
                         shadow_center=(centre_x, 60.0, centre_z),
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
def grounded_content_layout(package: Path) -> dict:
    """Keep authored resident posts and read their height at the actor centre."""
    import verify_runtime
    document, binary = verify_runtime.load_glb(package / 'world.glb')
    triangles, _ = verify_runtime.collect_triangles(
        document, binary, lambda name: name.startswith(('Terrain_', 'Walk_')))
    ground = verify_runtime.VerticalRayIndex(triangles)
    layout = copy.deepcopy(REG.CONTENT_LAYOUT)
    ox, oy = REG.SERVER_ORIGIN
    for name, position in layout['npcs'].items():
        tx, ty = round(position[0] + ox), round(oy - position[2])
        height = ground.top_hit(tx - ox + .5, oy - ty - .5)
        if height is None:
            raise ValueError(f'{name}: final resident post lacks a standing surface')
        position[1] = float(height)
    return layout


def write_manifest(build: RegionBuild, stats: dict, collision_stats: dict,
                   minimap: dict, path: Path) -> dict:
    t = build.terrain
    lows, highs = [], []
    for piece in list(build.terrain_meshes.values()) + list(build.water_meshes.values()):
        if piece.triangle_count:
            low, high = piece.bounds()
            lows.append(low)
            highs.append(high)
    for placement in build.placements:
        if placement.node.startswith("StreamView_"): continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        offset = np.asarray(placement.position)
        lows.append(low * placement.scale + offset)
        highs.append(high * placement.scale + offset)
    bounds_min = np.vstack(lows).min(axis=0)
    bounds_max = np.vstack(highs).max(axis=0)

    collision_nodes = sorted({p.node for p in build.placements if p.collides})
    clamp_at = COLLISION_HEIGHT_ORIGIN + 63 * COLLISION_HEIGHT_STEP

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": "verdant_stair",
            "name": "Verdant Stair",
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
        "navigation": {
            "crossings": build.crossings,
            "surfaceNodePrefixes": ["Terrain_", "Walk_"],
            "walkableAreas": ["jungle-floor", "trails", "terrace-paving",
                              "mossy-terraces", "strand", "fern-glade",
                              "stairs", "bridges", "walkways", "platforms",
                              "quays"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every "
                "authored walkable surface is named Walk_<...>. The client "
                "turns both into the navigation collision layer the grounding "
                "ray tests against.",
                "Structural geometry - terrace retaining walls, temple mass, "
                "arcade piers, tree trunks - is deliberately not a walk "
                "surface, so the grounding ray never snaps an actor onto a "
                "roof or the top of a wall.",
                "The stair is terraced, so cliff risers are steep by design "
                "and appear as GROUNDING_DISCONTINUITY warnings wherever a "
                "terrace meets the one below it.",
            ],
        },
        "landmarks": build.landmarks,
        "interactives": build.interactives,
        "npcMarkers": build.npc_markers,
        "harvestables": build.harvestables,
        "portals": build.portals,
        "contentLayout": grounded_content_layout(path.parent),
        "streamingBorders": getattr(build, "streaming_borders", []),
        "roads": [{"id": name,
                   "waypoints": [[round(float(p[0]), 1),
                                  round(float(t.height_at(p[0], p[1])), 2),
                                  round(float(p[1]), 1)] for p in points]}
                  for name, points in REG.ROUTES.items()] + REG.access_waypoints(t),
        "water": {
            "seaLevel": REG.SEA_LEVEL,
            "serverCells": REG.SERVER_CELLS,
            "bodies": [{"id": name, "node": name,
                        "type": ("sea" if "Lagoon" in name
                                 else "waterfall" if "Falls" in name
                                 else "cenote" if "Cenote" in name
                                 else "stream" if "Stream" in name else "pool")}
                       for name in build.water_meshes],
            "streams": [{"id": name,
                         "waypoints": [[round(float(p[0]), 1),
                                        round(float(t.height_at(p[0], p[1])), 2),
                                        round(float(p[1]), 1)] for p in points]}
                        for name, points in REG.STREAMS.items()],
            "gorges": [{"id": name,
                        "waypoints": [[round(float(p[0]), 1),
                                       round(float(t.height_at(p[0], p[1])), 2),
                                       round(float(p[1]), 1)] for p in points]}
                       for name, points in REG.RAVINES.items()],
        },
        "terraces": [{"id": label, "height": height,
                      "stairRange": [start, end]}
                     for start, end, height, label in REG.TERRACES],
        "environment": {
            "sky": {"type": "gradient", "zenith": [0.30, 0.52, 0.66],
                    "horizon": [0.72, 0.78, 0.72]},
            # Engine vectors follow light travel; preview vectors point toward the sun.
            "sun": {"direction": [0.38, -0.62, -0.68],
                    "color": [1.16, 1.08, 0.86], "energy": 1.20},
            "ambient": {"skyColor": [0.34, 0.48, 0.46],
                        "groundColor": [0.06, 0.10, 0.05], "energy": 0.55},
            "saturation": 1.22,
            # Read by the Godot capture rig and available to the client. The
            # region's ground and canopy albedos are deliberately dark - wet
            # limestone under closed canopy - and at the default 1.05 the
            # frames come back as silhouettes.
            "exposure": 2.0,
            "fog": {"enabled": True, "color": [0.62, 0.72, 0.68],
                    "density": 0.0016, "heightFalloff": 0.0022},
            "goldenHour": {"sun": {"direction": [0.80, -0.24, -0.55],
                                   "color": [1.48, 1.06, 0.66]},
                           "fog": {"color": [0.74, 0.66, 0.52], "density": 0.0030}},
            "presentation": {
                "mist": {"enabled": True,
                         "zones": ["cenote", "riser-falls", "lagoon"]},
                "waterSpray": {"enabled": True,
                               "nodes": sorted(n for n in build.water_meshes
                                               if "Falls" in n)},
                "fallingLeaves": {"enabled": True, "density": 0.35,
                                  "zones": ["jungle-core"]},
                "ambientAudio": [
                    {"id": "jungle-day", "zone": "jungle-core"},
                    {"id": "falls", "zone": "riser-falls"},
                    {"id": "surf", "zone": "lagoon"},
                    {"id": "settlement", "zone": "lower-terrace"}],
            },
            "zones": [
                {"id": "lagoon",
                 "centre": [float(REG.ANCHORS["lagoon"][0]), 0.0,
                            float(REG.ANCHORS["lagoon"][1])], "radius": 150.0},
                {"id": "lower-terrace",
                 "centre": [0.0, 24.0, 0.0], "radius": 90.0},
                {"id": "cenote",
                 "centre": [float(REG.ANCHORS["cenote"][0]), 30.0,
                            float(REG.ANCHORS["cenote"][1])], "radius": 70.0},
                {"id": "jungle-core",
                 "centre": [120.0, 60.0, -160.0], "radius": 260.0},
                {"id": "riser-falls",
                 "centre": [180.0, 80.0, -180.0], "radius": 300.0},
                {"id": "temple",
                 "centre": [float(REG.ANCHORS["great_temple"][0]), 100.0,
                            float(REG.ANCHORS["great_temple"][1])], "radius": 110.0},
            ],
        },
        "minimap": minimap,
        "lodGroups": [
            {"id": "jungle", "strategy": "authored-detail-tiers",
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
            {"id": "server-content",
             "file": "eloria-server config/eloria/{npcs,spawns,harvesting,"
                     "interactives,maps}.txt",
             "role": "authoritative-population"},
            {"id": "generator", "file": "source/build_verdant_stair.py",
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
        "buildNotes": build.notes,
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PACKAGE))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--stage", choices=("terrain", "full"), default="full")
    parser.add_argument("--skip-minimap", action="store_true")
    parser.add_argument("--skip-lod2", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import preview
    sets = preview.texture_sets()
    needed = {MAT.BY_NAME[m].texture for m in MATERIALS}
    if needed - sets.keys():
        sets.update({k:v for k,v in MAT.build_texture_sets().items() if k not in sets})

    build = build_region(args.seed, stage=args.stage)

    t0 = time.time()
    builder, stats = export_glb(build, sets, out / "world.glb",
                                warn_unreferenced=args.stage == "full")
    print(f"[glb] {stats['glbBytes'] / 1e6:.2f} MB, {stats['nodes']} nodes, "
          f"{stats['uniqueTriangles']} unique tris, "
          f"{stats['instancedTriangles']} instanced tris "
          f"({time.time() - t0:.1f}s)")

    payload, width, height, collision_stats = build_collision(build)
    (out / "collision.bin").write_bytes(payload)
    print(f"[collision] {width}x{height} cells, "
          f"{collision_stats['walkableFraction'] * 100:.1f}% walkable, "
          f"{collision_stats['elevatedDecks']} elevated decks")

    for line in snap_to_walkable(build, payload, width, height):
        print(f"[walkable] {line}")
        build.notes.append(line)

    minimap = {"file": "minimap.webp"}
    if not args.skip_minimap:
        t0 = time.time()
        minimap = render_minimap(build, sets, out / "minimap.webp")
        print(f"[minimap] rendered in {time.time() - t0:.1f}s")

    texture_bytes = sum(sum(len(v) for v in sets[name].images().values())
                        for name in sorted({MAT.BY_NAME[m].texture
                                            for m in MATERIALS}))
    stats["embeddedTextureBytes"] = texture_bytes
    stats["placements"] = len(build.placements)
    stats["collision"] = collision_stats
    stats["notes"] = build.notes
    playable = (REG.PLAY_MAX_X - REG.PLAY_MIN_X) * (REG.PLAY_MAX_Z - REG.PLAY_MIN_Z)
    stats["trianglesPerSquareMetre"] = round(
        stats["instancedTriangles"] / playable, 2)

    manifest = write_manifest(build, stats, collision_stats, minimap,
                              out / "world.json")
    print(f"[manifest] {len(manifest['landmarks'])} landmarks, "
          f"{len(manifest['interactives'])} interactives, "
          f"{len(manifest['harvestables'])} harvestables, "
          f"{len(manifest['npcMarkers'])} npc/creature markers, "
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

    if args.stage == "full" and not args.skip_lod2:
        t0 = time.time()
        lod_sets = {name: texture_set.reduced()
                    for name, texture_set in sets.items()}
        lod_build = build_region(args.seed, lod="far")
        _, lod_stats = export_glb(lod_build, lod_sets, out / "world-lod2.glb",
                                  warn_unreferenced=False)
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

    (out / "performance-summary.md").write_text(
        "# Verdant Stair performance summary\n\n```json\n"
        + json.dumps(stats, indent=2) + "\n```\n", encoding="utf-8")
    return 0 if counts["numErrors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
