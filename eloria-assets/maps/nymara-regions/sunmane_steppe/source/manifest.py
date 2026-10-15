"""Assemble the schema 1.x `world.json` companion manifest.

Field names follow `godot-client/schemas/world-manifest-1.schema.json` and the
conventions the Four Gates package established, so the same `WorldLoader`
consumes this package with no client change.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import terrain
import layout as DESIGN

# The client registry maps this region at one metre per tile with the server
# arrival datum (58, 58) at the Godot origin.
METRES_PER_TILE = 1.0
SERVER_ORIGIN = (58.0, 58.0)


def server_to_world(tile_x: float, tile_y: float) -> tuple[float, float]:
    """Mirror `CoordinateAdapter.server_to_godot` for authoring-time placement."""
    return ((tile_x - SERVER_ORIGIN[0]) * METRES_PER_TILE,
            -(tile_y - SERVER_ORIGIN[1]) * METRES_PER_TILE)


def world_to_server(world_x: float, world_z: float) -> tuple[int, int]:
    return (round(world_x / METRES_PER_TILE + SERVER_ORIGIN[0]),
            round(-world_z / METRES_PER_TILE + SERVER_ORIGIN[1]))


## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def build(builder, landform: terrain.Landform, statistics: dict) -> dict:
    half = terrain.HALF_EXTENT
    centre = terrain.CENTRE
    world_min = (centre[0] - half, centre[1] - half)
    world_max = (centre[0] + half, centre[1] + half)
    # Every Eloria minimap is drawn at one pixel to the metre, so the image is
    # the map's own size rather than a fixed square.
    minimap_pixels = int(round(half * 2.0 * MINIMAP_PIXELS_PER_METRE))
    lowest = float(landform.height.min())
    highest = float(landform.height.max())
    datum_height = landform.height_at(0.0, 0.0)

    spawn_points = []
    for identifier, tile, facing, note in (
            ("arrival-datum", (58, 58), [0, 0, -1],
             "ceremonial crossroads at the shared market"),
            ("west-caravanserai", (6, 58), [1, 0, 0], "arrival from Mirrorhold along the west road"),
            ("east-caravanserai", (110, 58), [-1, 0, 0], "eastern frontier; no exterior map link"),
            ("north-barrowfield", (58, 100), [0, 0, 1],
             "sealed Orun barrow approach")):
        world_x, world_z = server_to_world(*tile)
        spawn_points.append({
            "id": identifier,
            "node": "Terrain_Chunk_%02d_%02d" % _chunk_of(world_x, world_z),
            "serverTile": list(tile),
            "position": [round(world_x, 3), round(landform.height_at(world_x, world_z), 3),
                         round(world_z, 3)],
            "facing": facing,
            "groundedBy": "navigation-surface-raycast",
            "note": note})

    manifest = {
        "schemaVersion": "1.1.0",
        "assetVersion": "1.0.0",
        "asset": {
            "id": "sunmane_steppe",
            "name": "Sunmane Steppe",
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {
                "min": [world_min[0], round(lowest - 1.0, 2), world_min[1]],
                "max": [world_max[0], round(highest + 1.0, 2), world_max[1]]},
            "regionSpanMeters": half * 2.0,
            "serverCells": 192,
            "worldCentre": [centre[0], 0.0, centre[1]],
            "seaLevel": terrain.SEA_LEVEL,
        },
        "coordinateTransform": {
            "metresPerTile": METRES_PER_TILE,
            "serverOrigin": list(SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            # Fallback height only, used if a grounding raycast ever misses.
            # It is set to the arrival plateau so a miss can never drop an actor
            # below the landform.
            "walkingHeight": round(datum_height, 3),
            "invertServerY": True,
            # Server tiles are non-negative, so with the datum at (58, 58) the
            # addressable band is Godot X -58..133 and Z -133..58. The map is
            # wider than that on purpose: everything outside it is coastal
            # scenery and rim highland that a player can see but never stand
            # on, which is exactly what makes it a natural world boundary.
            "addressableWorldBounds": {"min": [-58.0, -133.0],
                                       "max": [133.0, 58.0]},
        },
        "spawnPoints": spawn_points + [{
            "id":"server-arrival", "serverTile":[79,37], "position":[21,9.6,21],
            "facing":[-1,0,0], "groundedBy":"navigation-surface-raycast",
            "note":"southern arrival forecourt; the gate leads to the market"}],
        "collision": collision_block(builder),
        "navigation": {
            "surfaceNodePrefixes": ["Terrain_", "Walk_"],
            "walkableAreas": [terrain.CLASS_NAMES[c] for c in
                              (terrain.CLASS_CLEARING, terrain.CLASS_STEPPE,
                               terrain.CLASS_ROAD, terrain.CLASS_DRY_GRASS,
                               terrain.CLASS_SAND)],
            "navmesh": {"format": "surface-prefix-v1", "agentRadius": 0.55,
                        "agentHeight": 1.9, "maxSlopeDegrees": 42, "polygons": []},
            "crossings":[{"id":name,"endpoints":[list(a),list(b)]}
                         for name,a,b,_ in DESIGN.BRIDGES],
            "note": ("Every terrain chunk carries the Terrain_ prefix, so the "
                     "navigation-surface layer covers the whole landform "
                     "including the shallow shelf. A grounding raycast can "
                     "therefore never miss and fall back to walkingHeight."),
        },
        "contentLayout": DESIGN.CONTENT,
        "roads": [{"id":name,"waypoints":[[x,round(landform.height_at(x,z),3),z] for x,z in points]}
                  for name,points in {**DESIGN.ROADS,**DESIGN.TRAILS}.items()],
        "landmarks": builder.landmarks,
        "interactives": builder.interactives,
        "terrain": {
            "cellMeters": terrain.CELL,
            "chunkGrid": [terrain.CHUNKS, terrain.CHUNKS],
            "classes": {terrain.CLASS_NAMES[k]: list(v)
                        for k, v in terrain.CLASS_TINT.items()},
            "lowestElevation": round(lowest, 2),
            "highestElevation": round(highest, 2),
            "worldEdgeBarrier": ("mountain range closing the north and east, "
                                 "raised ridge to the south, open sea to the west"),
        },
        "materials": {
            "strategy": "shared-tileable-pbr-families-with-world-scale-uvs",
            "channelPacking": {"orm": "R=occlusion,G=roughness,B=metallic"},
            "families": {name: {"uvScaleMeters": scale} for name, scale
                         in sorted(__import__("shapes").UV_SCALE.items())},
            "embedded": True,
        },
        "environment": {
            "profile": "warm-daylight",
            "sky": {
                "topColor": "#2a6ec4", "horizonColor": "#b7c8cf",
                "groundHorizonColor": "#b09a72", "groundBottomColor": "#6b5a3e",
                "curve": 0.15, "sunAngleMax": 11.0, "energy": 1.0},
            "ambient": {"color": "#c9c6b6", "skyContribution": 0.42, "energy": 0.52},
            "sun": {"rotationDegrees": [-48, 132, 0], "color": "#fff0d2",
                    "energy": 1.25, "indirectEnergy": 0.9, "shadows": True},
            "fog": {"enabled": True, "color": "#d6c8ab", "density": 0.0009,
                    "skyAffect": 0.16, "aerialPerspective": 0.06},
            "tonemap": {"mode": "filmic", "exposure": 0.92, "white": 2.6},
            "water": {"seaLevel": terrain.SEA_LEVEL,
                      "shallowColor": "#2f9aa6", "deepColor": "#0d5866",
                      "node": "Water_Sea", "waterholeNode": "Water_Waterholes"},
            "variants": {
                "golden-hour": {
                    "sky": {"topColor": "#2f6ba8", "horizonColor": "#e7bf88",
                            "groundHorizonColor": "#a4834f",
                            "groundBottomColor": "#5b4830",
                            "curve": 0.20, "sunAngleMax": 14.0, "energy": 1.0},
                    "ambient": {"color": "#e6c49a", "skyContribution": 0.40, "energy": 0.66},
                    "sun": {"rotationDegrees": [-13, 152, 0], "color": "#ffcf96",
                            "energy": 2.0, "indirectEnergy": 1.0, "shadows": True},
                    "fog": {"enabled": True, "color": "#e6bd8c", "density": 0.0019,
                            "skyAffect": 0.28, "aerialPerspective": 0.10},
                    "tonemap": {"mode": "filmic", "exposure": 1.12, "white": 2.2}}},
        },
        "lighting": {
            "markers": getattr(builder, "lights", []),
            "note": ("Warm landmark and transition light markers are emitted as "
                     "named empty nodes so a client lighting pass can bind them "
                     "without the package depending on a glTF light extension."),
        },
        "minimap": {
            "image": "minimap.webp",
            "fullMapImage": "full-map.webp",
            "previewImage": "minimap-preview.webp",
            "projection": "orthographic-top-down",
            "renderedFrom": "world.glb",
            "generator": ("godot-client/tests/integration/sunmane_minimap.gd, "
                          "rendered through the client's own WorldLoader"),
            "northAxis": "-Z",
            "imageSize": [minimap_pixels, minimap_pixels],
            "worldMin": [world_min[0], world_min[1]],
            "worldMax": [world_max[0], world_max[1]],
            "pixelsPerMetre": MINIMAP_PIXELS_PER_METRE,
            # Image +X is world +X and image +Y (downward) is world +Z, so north
            # (-Z) is at the top of the picture.
            "transform": {
                "pixelX": {"scale": MINIMAP_PIXELS_PER_METRE,
                           "offset": round(-world_min[0] * MINIMAP_PIXELS_PER_METRE, 4)},
                "pixelY": {"scale": MINIMAP_PIXELS_PER_METRE,
                           "offset": round(-world_min[1] * MINIMAP_PIXELS_PER_METRE, 4)},
                "formula": ("pixel_x = world_x * scale + offset; "
                            "pixel_y = world_z * scale + offset"),
            },
            "note": ("Every Eloria minimap is drawn at one pixel to the metre,"
                     " so the image's pixel size is the map's size in metres."),
            "file": "minimap.webp",
            "pixels": minimap_pixels,
            "size": [minimap_pixels, minimap_pixels],
            "metresPerPixel": round(1.0 / MINIMAP_PIXELS_PER_METRE, 6),
            "centre": [round((world_min[0] + world_max[0]) * 0.5, 4),
                       round((world_min[1] + world_max[1]) * 0.5, 4)],
            "northUp": True,
            "orientation": "north-up",
        },
        **getattr(builder, "population", {}),
        "provenance": {
            "generator": "eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py",
            "conceptArt": {
                "aerial": "references/01-aerial-overview.png",
                "detailBoard": "references/00-concept-detail-board.png"},
            "writtenDescription": [
                "eloria-assets/qa/regions/sunmane-steppe/README.md",
                "eloria-assets/NYMARA_ASSET_MANIFEST.md"],
            "sourceConnections": "../region-connections.json",
            "license": "Original Eloria project work, CC-BY-4.0",
            "thirdPartyAssets": "none",
        },
        "statistics": {key:value for key,value in statistics.items() if key!="buildSeconds"},
    }
    return manifest


def _chunk_of(world_x: float, world_z: float) -> tuple[int, int]:
    span = terrain.HALF_EXTENT * 2.0 / terrain.CHUNKS
    origin_x = terrain.CENTRE[0] - terrain.HALF_EXTENT
    origin_z = terrain.CENTRE[1] - terrain.HALF_EXTENT
    last = terrain.CHUNKS - 1
    return (min(last, max(0, int((world_x - origin_x) / span))),
            min(last, max(0, int((world_z - origin_z) / span))))


def collision_block(builder) -> dict:
    """What the package says about its own walk grid.

    Only the node names were published before, so anything wanting to read
    `collision.bin` had to infer the world-to-cell mapping from
    `coordinateTransform` and guess the row order. The client's own region
    check gives up and skips the grid when `originMetres` is missing, which is
    what it did here.
    """
    block = {"nodeNames": sorted(set(builder.collision_nodes)),
             "binary": "collision.bin", "format": "EWCG-v2"}
    grid = getattr(builder, "collision_stats", None)
    if grid:
        block.update({
            "cellMetres": grid["cellMetres"],
            "width": grid["cells"], "height": grid["cells"],
            "originMetres": grid["originMetres"],
            "heightEncoding": dict(grid["heightEncoding"], note=(
                "The grid is authoritative for walkability. The Godot loader "
                "takes elevation from the rendered walk surfaces, not from "
                "this file.")),
            "walkableCells": grid["walkableCells"],
            "walkableFraction": grid["walkableFraction"],
        })
    return block

