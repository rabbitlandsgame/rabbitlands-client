#!/usr/bin/env python3
"""Build the Whitehorn Range runtime package.

Writes `world.glb`, `world.json`, `collision.bin`, `minimap.webp`, the glTF
validator report and the performance summary, one directory up.

Deterministic for a given seed: the same source reproduces the same bytes.

    python3 build_whitehorn.py
    python3 ../../_toolkit/verify_runtime.py --package ..
    python3 ../../_toolkit/validate_gltf.py ../world.glb
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(PACKAGE.parent / "_toolkit"))
sys.path.insert(0, str(HERE))

from amberwood import gltf as GLTF          # noqa: E402
from amberwood import materials as MAT      # noqa: E402
from amberwood import mesh as M             # noqa: E402
from amberwood import terrain as TER        # noqa: E402
from regionbuild import RegionBuild         # noqa: E402
import validate_gltf                        # noqa: E402

import region as REG                        # noqa: E402
import layout as LAYOUT
import landscape_plan as LANDSCAPE
import transitions as MARCH                 # noqa: E402
import secretdoors as SD                    # noqa: E402
import secrets_design as SEC                # noqa: E402
import loresites as LORE                    # noqa: E402

SEED = 20260828
# Class islands smaller than this are given to whatever surrounds them. Six
# two-metre cells is 24 m2 - smaller than any surface a player is meant to
# read as its own thing, and larger than every crumb the noise leaves.
DESPECKLE_MIN_CELLS = 6
ASSET_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

# The materials Whitehorn embeds, pinned by name. The shared table grows as
# other regions add recipes; without this pin every one of those would be
# embedded here too - megabytes of images nothing references, and a different
# world.glb for a change that has nothing to do with Whitehorn.
#
# Whitehorn reuses the shared alpine recipes rather than duplicating them.
# `snow_pack`, `glacier_ice`, `veined_marble`, `pale_ashlar`, `blue_crystal`,
# `gilt_brass`, `slate_roof` and `alpine_turf` were added to the toolkit by the
# Mirrorhold build; reusing them by name is the intended contract.
#
# This set is exactly the materials the build emits - verified against the
# meshes it actually produces, not guessed. An unused name would embed a
# texture nothing references; a missing one is a hard error at export.
#
# The ground's alpha-tested copies are not pinned separately: a copy
# carries the pinned material's own textures and differs only in alpha
# mode, so the pin is read through `MAT.base_material`.
# The three crossings, as region-connections.json declares them: the south
# march down to Mirrorhold, the west pass to the Amberwood, the east pass to
# the Barrens. Turf and stone come up the south road, autumn trees stand in
# the west pass, crystal dust blows through the east one.
CROSSINGS = [
    MARCH.Crossing("south-gate", "mirrorhold", REG.ANCHORS["south_march"],
                   (REG.ANCHORS["south_march"][0], REG.PLAY_MAX_Z + 20.0),
                   radius=78.0, name="The Mirrorhold March"),
    MARCH.Crossing("west-pass", "amberwood", REG.ANCHORS["west_pass"],
                   (REG.PLAY_MIN_X - 20.0, REG.ANCHORS["west_pass"][1]),
                   radius=90.0, name="The Amber Pass"),
    MARCH.Crossing("east-pass", "amethyst_barrens", REG.ANCHORS["east_pass"],
                   (REG.PLAY_MAX_X + 20.0, REG.ANCHORS["east_pass"][1]),
                   radius=78.0, name="The Barrens Pass"),
]

# The places the region's people argue about (see loresites.py).
SITES = [
    LORE.Site("snowline-stones", "The Snowline Stones", "snowline_stones", (198.0, -137.0),
              thread="K", clearing=12.0,
              note="Ten cut stones up the slope, each with a brass line where the snow stood the "
                   "year it was set. The last three stand above the snow now."),
]
MARCH_MATERIALS: dict = dict(REG.SURFACE_MATERIALS) | LANDSCAPE.GROUND

MATERIALS = frozenset({
    'snow_pack', 'glacier_ice', 'veined_marble', 'pale_ashlar',
    'blue_crystal', 'gilt_brass', 'alpine_turf',
    'cliff_rock', 'rubble_stone', 'packed_earth', 'ashlar',
    'timber_grey', 'timber_dark', 'dark_iron', 'woven_cloth',
    'bark_dark', 'foliage_green', 'amber_resin', 'carved_wood',
    'alpine_snowfield','alpine_blue_ice','alpine_gravel','alpine_bedrock',
    'woodland_track','woodland_sward','woodland_loam',
    'timber_warm',
}) | MARCH.materials_for("whitehorn_range", CROSSINGS) | SD.materials(SEC) | LORE.materials([s.piece for s in SITES])

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


# --------------------------------------------------------------------------
def build_region(seed: int = SEED, lod: str | None = None) -> RegionBuild:
    """Terrain, then population. Terrain must stand on its own first."""
    terrain = REG.build_terrain(seed)
    REG.apply_built_ground(terrain, seed)
    REG.assign_surfaces(terrain, seed)
    # Thresholded noise and a dithered boundary both leave crumbs - a few cells
    # of snow marooned in rock, a gap of turf in the middle of a road. A stray
    # square was easy to miss; cut inside the cell it reads as a deliberate
    # blob, so the crumbs are cleared before the ground is built.
    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)

    build = RegionBuild(terrain=terrain)
    MARCH.prepare(terrain, CROSSINGS)
    LORE.prepare(terrain, SITES, sea_level=getattr(REG, "SEA_LEVEL", 0.0), keep=(TER.ICE, TER.MARBLE))

    LAYOUT.prepare(terrain)
    LANDSCAPE.prepare(terrain,seed)
    import populate
    populate.populate(build, seed, lod=lod)
    from amberwood.routecraft import clear_walk_corridors
    clear_walk_corridors(build,
        [[[x,y,z] for (x,z),y in zip(points,heights)]
         for points,heights,width in LAYOUT.ROADS.values()],
        {"rock":4.2,"tree":4.6})
    LAYOUT.dress(build, seed+809)

    # The marches: the neighbours' country coming in along the roads out.
    MARCH.paint(terrain, CROSSINGS, MARCH_MATERIALS, seed, keep=(TER.ICE, TER.MARBLE))
    for surface, material in list(MARCH_MATERIALS.items()):
        MARCH_MATERIALS[surface] = LANDSCAPE.PALETTE.get(material, {'forest_floor':'woodland_loam'}.get(material,material))
    march = MARCH.dress(build, "whitehorn_range", CROSSINGS, seed)
    LORE.dress(build, terrain, SITES, seed)
    SD.dress(build, terrain, SEC, seed, sea_level=getattr(REG, "SEA_LEVEL", 0.0), server_origin=REG.SERVER_ORIGIN)
    build.landmarks.extend(march.landmarks)
    build.notes.extend(march.notes)
    LANDSCAPE.dress(build,seed)
    terrain.despeckle_surfaces(DESPECKLE_MIN_CELLS)
    build.terrain_meshes = terrain.build_meshes(
        uv_scale=0.30, materials=MARCH_MATERIALS,
        blend_edges=True, material_suffix=MAT.GROUND_SUFFIX)

    _add_spawns(build)
    _add_portals(build)
    LANDSCAPE.compact(build)
    return build


def _add_portals(build: RegionBuild) -> None:
    """The three ways out, and the four doors into the insides map."""
    t = build.terrain

    def tile(x: float, z: float) -> list[int]:
        return [int(round(x + REG.SERVER_ORIGIN[0])), int(round(REG.SERVER_ORIGIN[1] - z))]

    for crossing, name, destination in (
            (CROSSINGS[0], "March down to Mirrorhold", "mirrorhold"),
            (CROSSINGS[1], "Amber Pass", "amberwood"),
            (CROSSINGS[2], "Barrens Pass", "amethyst_barrens")):
        x, z = crossing.position
        build.portals.append({
            "id": crossing.id, "name": name, "type": "map-transition",
            "position": [round(float(x), 2), round(float(t.height_at(x, z)) + 0.1, 2),
                         round(float(z), 2)],
            "serverTile": tile(x, z), "destinationMap": destination, "radius": 3.5,
            "authority": "server"})

    # The insides: every door targets the one composed map and differs only in
    # where it arrives. The door stands on its landmark, so the entrance a
    # player walks into is the building they were looking at.
    for portal_id, name, landmark_id in (
            ("whitehorn-glacier-temple-door", "Glacier Temple", "whitehorn-glacier-temple"),
            ("whitehorn-mine-adit", "Whitehorn Mine", "whitehorn-mine"),
            ("whitehorn-ice-cave-mouth", "Whitehorn Ice Cave", "whitehorn-ice-cave"),
            ("whitehorn-barrow-door", "The Frost Barrow", "whitehorn-cairn-field-cairn_ridge"),
            ("snowline-cell-door", "The Snowline Cell", "whitehorn-shrine-02"),
            ("west-watch-cave-mouth", "The Cascade Cave", "whitehorn-cairn-field-west_watch"),
            ("gate-store-door", "The Ration Sister's Store", "whitehorn-south-gate"),
):
        anchor = next((l for l in build.landmarks if l.get("id") == landmark_id), None)
        if anchor is None:
            continue
        x, y, z = anchor["position"]
        if portal_id == "gate-store-door":
            x,y,z = -28.0,19.66,65.5
        elif portal_id == "west-watch-cave-mouth":
            x,y,z = -122.0,47.64,-136.0
        position = [round(float(x), 2), round(float(y) + 0.1, 2), round(float(z), 2)]
        build.portals.append({
            "id": portal_id, "name": name, "type": "interior-entrance",
            "position": position, "serverTile": tile(x, z), "landmark": landmark_id,
            "destinationMap": "whitehorn_glacier_temple", "destinationSpawn": portal_id,
            "radius": 2.5, "authority": "server"})
        build.spawns.append({
            "id": portal_id, "name": name,
            "position": [position[0], round(float(y), 2), position[2]],
            "rotationY": 0.0, "authority": "server",
            "note": "return point from the Whitehorn insides map"})


def _add_spawns(build: RegionBuild) -> None:
    t = build.terrain
    for ident, name, position in (
            ("whitehorn-arrival", "Whitehorn Arrival", REG.SPAWN),
            ("whitehorn-temple", "Glacier Temple Forecourt", REG.SPAWN_TEMPLE),
            ("whitehorn-mine", "Mine Yard", REG.SPAWN_MINE)):
        x, z = position
        build.spawns.append({
            "id": ident,
            "name": name,
            "position": [round(float(x), 2),
                         round(float(t.height_at(x, z)), 2),
                         round(float(z), 2)],
            "rotationY": 0.0,
            "authority": "server",
        })


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


def export_glb(build: RegionBuild, sets, path: Path) -> tuple[GLTF.GltfBuilder, dict]:
    builder = GLTF.GltfBuilder(
        generator="Eloria Whitehorn Range builder (original procedural assets)")
    MAT.register_gltf_materials(builder, sets, only=MATERIALS | getattr(build,'vista_materials',set()))
    MAT.register_ground_materials(
        builder, sets,
        {piece.material for piece in build.terrain_meshes.values()})

    # Tangents are intentionally omitted: Godot's glTF importer generates them
    # for normal-mapped materials, and shipping them costs sixteen bytes a
    # vertex in a package already dominated by vertex data.
    def prepare(piece: M.Mesh) -> M.Mesh:
        piece.sanitise_normals()
        piece.drop_degenerate()
        piece.weld(1e-4)
        return piece

    # Every mesh a placement references, registered once and instanced by node.
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

    root_index = builder.add_node(GLTF.Node("WhitehornRange"))
    # Group nodes are created on first use. Emitting the full set up front
    # leaves childless nodes in the GLB, which the validator reports as
    # NODE_EMPTY and which serve no purpose in the scene tree.
    _groups: dict[str, int] = {}

    def groups_get(name: str) -> int:
        if name not in _groups:
            _groups[name] = builder.add_node(
                GLTF.Node(f"Group_{name}"), root_index)
        return _groups[name]

    class _Groups:
        def __getitem__(self, name: str) -> int:
            return groups_get(name)

    groups = _Groups()

    for name, piece in build.terrain_meshes.items():
        if piece.triangle_count == 0:
            continue
        builder.add_mesh(name, prepare(piece), with_tangents=False)
        parent = groups["Boundary"] if name.startswith("Backdrop") \
            else groups["Terrain"]
        builder.add_node(GLTF.Node(name, mesh=name), parent)
    for name, piece in build.water_meshes.items():
        if piece.triangle_count == 0:
            continue
        builder.add_mesh(name, prepare(piece), with_tangents=False)
        builder.add_node(GLTF.Node(name, mesh=name), groups["Ice"])

    kind_group = {
        "tree": "Props", "foliage": "Props", "rock": "Props",
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
def build_collision(build: RegionBuild) -> tuple[bytes, int, int, dict]:
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

    # Whitehorn has no sea, so walkability is mostly a slope question. The
    # glacier surface is walkable; the gorge walls and the ranges that close
    # the world are not.
    walkable = slope < 1.05

    # The gorge floor is excluded deliberately. It sits 22 m below the valley
    # datum, which is past what the legacy six-bit height field can encode -
    # those cells quantised to the floor of the range and then disagreed with
    # the rendered surface. More importantly it is a chasm: the two rope
    # bridges exist precisely because it is not something a player walks
    # across, so marking its bed unwalkable states the design rather than
    # working around the encoding.
    walkable &= ground > (REG.VALLEY_FLOOR - 10.0)

    blockers = np.zeros_like(walkable)
    for placement in build.placements:
        if not placement.collides:
            continue
        if placement.node == 'Landmark_glacier_temple':
            # A circular landmark blocker used to surround the stair's foot
            # with an invisible moat. Block the actual podium/backing instead;
            # the authored deck and stair are rasterised below.
            dx,dz=gx-placement.position[0],gz-placement.position[2]
            blockers|=(abs(dx)<14)&(dz<3.5)&(dz>-20)
            continue
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        footprint = float(max(abs(low[0]), abs(high[0]),
                              abs(low[2]), abs(high[2]))) * placement.scale
        factor = 0.16 if placement.kind in ("tree", "foliage") else 0.62
        radius = min(max(footprint * factor, 0.40), 11.0)
        px, _, pz = placement.position
        blockers |= (np.hypot(gx - px, gz - pz) < radius)
    LANDSCAPE.block_walls(blockers,gx,gz)
    walkable &= ~blockers

    surface = ground.copy()
    decks = np.zeros_like(walkable)
    # An overhead walk surface owns its footprint: the client grounds an actor
    # on the first walk surface below the ray, so a two-level column cannot be
    # expressed on a flat server grid. The rope bridges therefore take their
    # cells, and the gorge floor beneath them is not separately walkable.
    import glb_reader as GLB_READ
    elevated = 0
    faces=[]
    for placement in build.placements:
        item=build.meshes[placement.mesh]
        parts=getattr(item,"walk_parts",[])
        if not parts and placement.walk_surface:parts=getattr(item,"all_parts",[item])
        if not parts:continue
        elevated+=1
        matrix=M.translation(*placement.position)@M.rotation_y(placement.rotation_y)@M.scaling(placement.scale)
        for part in parts:
            placed=part.transformed(matrix)
            faces.append(placed.positions[placed.indices.reshape(-1,3)])
    if faces:
        decks,deck_height=GLB_READ.rasterise(np.concatenate(faces),width,height,
            LANDSCAPE.PLAY_MIN_X,LANDSCAPE.PLAY_MAX_Z,COLLISION_CELL)
        surface=np.where(decks,np.maximum(ground,deck_height),surface)
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


def render_minimap(build: RegionBuild, sets, path: Path, size: int = 0) -> dict:
    """Top-down capture of the finished geometry, not a hand-drawn map."""
    import math

    import preview
    from amberwood import render as RENDER

    scene = preview.scene_from_build(build, sets)
    centre_x = (LANDSCAPE.PLAY_MIN_X + LANDSCAPE.PLAY_MAX_X) * 0.5
    centre_z = (LANDSCAPE.PLAY_MIN_Z + LANDSCAPE.PLAY_MAX_Z) * 0.5
    extent = max(LANDSCAPE.PLAY_MAX_X - LANDSCAPE.PLAY_MIN_X,
                 LANDSCAPE.PLAY_MAX_Z - LANDSCAPE.PLAY_MIN_Z)
    if size <= 0:
        size = int(round(extent * MINIMAP_PIXELS_PER_METRE))
    altitude = 1100.0
    fov = 2.0 * math.degrees(math.atan((extent * 0.5) / altitude))
    # Cold, near-shadowless light: a snow region under the warm preset reads
    # as sand, and heavy shadow on a white subject hides the relief rather
    # than describing it.
    lighting = RENDER.Lighting(sun_direction=(-0.28, 0.92, 0.28),
                               fog_density=0.0, ambient_strength=0.78,
                               shadow_strength=0.42,
                               sun_color=(1.02, 1.04, 1.10),
                               sky_color=(0.42, 0.50, 0.64),
                               saturation=0.94, exposure=1.0)
    image = scene.render(eye=(centre_x, altitude, centre_z + 0.01),
                         target=(centre_x, 0.0, centre_z),
                         width=size, height=size, fov=fov, lighting=lighting,
                         shadows=True, shadow_size=2048,
                         shadow_center=(centre_x, 40.0, centre_z),
                         shadow_radius=extent * 0.62, near=240.0, far=1700.0)
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
def _environment() -> dict:
    """The manifest's `environment` block, consumed by WorldEnvironmentBinder.

    THE SIGN OF `sun.direction` IS THE DIRECTION THE LIGHT TRAVELS, not the
    direction of the sun in the sky. `world_environment_binder.gd` aims the key
    light with `sun.look_at_from_position(Vector3.ZERO, facing, up)`, which
    points the node's -Z at `facing`, and a DirectionalLight3D emits along its
    local -Z. So a positive Y component lights the world from underneath.

    The offline preview renderer uses the opposite convention: its
    `Lighting.sun_direction` points *toward* the sun. The two must therefore be
    negations of each other, and copying one into the other - which is what
    Amberwood's manifest does, declaring [-0.46, 0.50, 0.73] - inverts the key
    light. It has never been caught because no offline preview can show it.

    Whitehorn's preview sun is (-0.38, 0.62, 0.68); this is its negation.
    """
    day_sun = (0.38, -0.62, -0.68)
    golden_sun = (0.80, -0.24, -0.52)
    return {
        "biome": "alpine-glacial",
        "snowLine": REG.SNOW_LINE,
        "sky": {
            "type": "gradient",
            "zenith": [0.24, 0.38, 0.62],
            "horizon": [0.72, 0.78, 0.86],
        },
        # Cool, bright and low-contrast: snow is a high-albedo subject lit
        # largely by sky bounce, and the warm preset the forest regions use
        # renders it as sand.
        "sun": {
            "direction": list(day_sun),
            "color": [1.06, 1.06, 1.10],
            "energy": 1.05,
            "shadows": True,
            "angularDiameterDegrees": 0.6,
        },
        "ambient": {
            "skyColor": [0.40, 0.48, 0.62],
            "groundColor": [0.30, 0.34, 0.40],
            "energy": 0.52,
        },
        "saturation": 0.92,
        "fog": {
            "enabled": True,
            "color": [0.62, 0.68, 0.76],
            "density": 0.00048,
            "heightFalloff": 0.0026,
            "skyAffect": 0.35,
        },
        "goldenHour": {
            "sun": {"direction": list(golden_sun),
                    "color": [1.44, 1.02, 0.66]},
            "fog": {"color": [0.68, 0.62, 0.62], "density": 0.0011},
        },
        "zones": [
            {"id": "glacier", "centre": [78.0, 40.0, -132.0], "radius": 150.0},
            {"id": "temple", "centre": [102.0, 70.0, -300.0], "radius": 90.0},
            {"id": "gorge", "centre": [90.0, 0.0, -84.0], "radius": 170.0},
            {"id": "approach", "centre": [0.0, 18.0, 42.0], "radius": 140.0},
            {"id": "mine", "centre": [282.0, 50.0, -132.0], "radius": 90.0},
        ],
        "notes": [
            "Whitehorn has no sea and no standing water; the watercourses are "
            "frozen or dry meltwater beds.",
            "sun.direction is the direction the light travels, so its Y is "
            "negative. See _environment() in source/build_whitehorn.py.",
        ],
    }


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
        item = build.meshes[placement.mesh]
        low, high = item.bounds()
        offset = np.asarray(placement.position)
        lows.append(low * placement.scale + offset)
        highs.append(high * placement.scale + offset)
    bounds_min = np.vstack(lows).min(axis=0)
    bounds_max = np.vstack(highs).max(axis=0)

    build.resolve_names()
    collision_nodes = sorted({p.node for p in build.placements if p.collides})

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": "whitehorn_range",
            "name": "Whitehorn Range",
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [round(float(v), 2) for v in bounds_min],
                       "max": [round(float(v), 2) for v in bounds_max]},
            "playableBounds": {
                "min": [LANDSCAPE.PLAY_MIN_X, round(float(t.height.min()), 2),
                        LANDSCAPE.PLAY_MIN_Z],
                "max": [LANDSCAPE.PLAY_MAX_X, round(float(t.height.max()), 2),
                        LANDSCAPE.PLAY_MAX_Z]},
            "seaLevel": None,
            "valleyFloor": REG.VALLEY_FLOOR,
            "serverCells": LANDSCAPE.SERVER_CELLS,
        },
        "coordinateTransform": {
            "metresPerTile": REG.METRES_PER_TILE,
            "serverOrigin": list(LANDSCAPE.SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": round(float(t.height_at(float(LANDSCAPE.PLAN.x(REG.SPAWN[0])),float(LANDSCAPE.PLAN.z(REG.SPAWN[1])))), 2),
            "invertServerY": True,
        },
        "spawnPoints": build.spawns,
        "collision": {
            "nodeNames": collision_nodes,
            "binary": "collision.bin",
            # Both of these describe the file `build_collision` just wrote, so
            # both are taken from it. They used to be written from the constants
            # above, which stopped being true when the grid moved to EWCG v2 and
            # to an encoding sized from the region's own relief: the manifest
            # then advertised a 0.2 m step for a file holding 2.6 m ones, and
            # the correction had to be made by hand after every build.
            "format": "EWCG-v%d" % COLLISION_FORMAT_VERSION,
            "cellMetres": COLLISION_CELL,
            "width": collision_stats["width"],
            "height": collision_stats["height"],
            "heightEncoding": dict(collision_stats["heightEncoding"], note=(
                "The grid is authoritative for walkability. The Godot loader "
                "takes elevation from the rendered walk surfaces, not from "
                "this file.")),
            "walkableCells": collision_stats["walkableCells"],
            "walkableFraction": collision_stats["walkableFraction"],
        },
        "navigation": {
            "crossings": build.crossings,
            "surfaceNodePrefixes": ["Terrain_", "Walk_"],
            "walkableAreas": ["snow", "ice", "rock", "trails", "paving",
                              "marble", "alpine-turf", "bridges", "stairs"],
            "agentRadius": 0.55,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 40,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": [
                "Every terrain sub-mesh is named Terrain_<class>; every "
                "authored walkable deck is named Walk_<name>. Structural "
                "geometry is deliberately not a walk surface, so the "
                "grounding ray never snaps an actor onto a roof, a gantry or "
                "the top of an arch.",
            ],
        },
        "landmarks": build.landmarks,
        "interactives": build.interactives,
        "npcMarkers": build.npc_markers,
        "harvestables": build.harvestables,
        "portals": build.portals,
        "roads": LANDSCAPE.roads(),
        "contentLayout": LANDSCAPE.content_layout(),
        "water": [],
        "environment": _environment(),
        "minimap": minimap,
        "lodGroups": [],
        "performance": stats,
        "sources": {
            "concept": "eloria-assets/concepts/nymara-regions/"
                       "whitehorn_range_region_concept.png",
            "detailBoard": "references/00-concept-detail-board.png",
            "build": "source/build_whitehorn.py",
        },
        "provenance": {
            "generator": "Eloria Whitehorn Range builder",
            "seed": SEED,
            "toolkit": "maps/nymara-regions/_toolkit",
            "deterministic": True,
            "assets": "All geometry and textures generated procedurally; no "
                      "third-party models or images.",
        },
        "productionStatus": "production-geometry-materials-population",
        "knownLimitations": build.notes,
    }
    manifest["landscapeRevision"]="inhabited-396-v1"
    manifest["borderVistas"]=build.border_vistas
    manifest["streamingBorders"]=build.streaming_borders
    manifest["environment"]["zones"]=LANDSCAPE.PLAN.metadata(manifest["environment"]["zones"])
    for zone in manifest["environment"]["zones"]:zone["radius"]*=.7
    if (HERE / "server-content.json").exists():
        import server_posts
        server_posts.apply(manifest, path.parent, json.loads((HERE / "server-content.json").read_text()))
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
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    import preview
    sets = preview.texture_sets()

    t0 = time.time()
    build = build_region(args.seed)
    print(f"[region] built in {time.time() - t0:.1f}s  "
          f"height {build.terrain.height.min():.1f} .. "
          f"{build.terrain.height.max():.1f} m")

    t0 = time.time()
    builder, stats = export_glb(build, sets, out / "world.glb")
    print(f"[glb] {stats['glbBytes'] / 1e6:.2f} MB, {stats['nodes']} nodes, "
          f"{stats['uniqueTriangles']} unique tris "
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

    texture_bytes = sum(sum(len(v) for v in ts.images().values())
                        for name, ts in sets.items() if name in MATERIALS)
    stats["embeddedTextureBytes"] = texture_bytes
    stats["placements"] = len(build.placements)
    stats["collision"] = collision_stats
    stats["trianglesPerSquareMetre"] = round(
        stats["instancedTriangles"] / float(LANDSCAPE.SERVER_CELLS ** 2), 2)

    manifest = write_manifest(build, stats, collision_stats, minimap,
                              out / "world.json")
    print(f"[manifest] {len(manifest['landmarks'])} landmarks, "
          f"{len(manifest['spawnPoints'])} spawns")

    report = validate_gltf.validate(str(out / "world.glb"))
    payload = report.to_dict()
    (out / "world.glb.validator.json").write_text(
        json.dumps(payload, indent=2) + "\n")
    counts = payload["issues"]
    print(f"[validate] errors={counts['numErrors']} "
          f"warnings={counts['numWarnings']} infos={counts['numInfos']}")
    for message in report.messages:
        if message["severity"] <= 1:
            print("   ", message["code"], message["message"], message["pointer"])

    (out / "performance-summary.md").write_text(
        "# Whitehorn Range performance summary\n\n```json\n"
        + json.dumps(stats, indent=2) + "\n```\n", encoding="utf-8")
    return 0 if counts["numErrors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
