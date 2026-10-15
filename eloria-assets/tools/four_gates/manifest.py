"""world.json authoring for the Four Gates package (schema 1)."""

from __future__ import annotations

import math
from typing import Dict, List

import numpy as np

import interior_index as INDEX
import layout
import terrain as T

TAU = math.pi * 2.0


def _p(x, y, z):
    return [round(float(x), 2), round(float(y), 2), round(float(z), 2)]


def _polygon(pid: str, points, y: float, tags):
    return {"id": pid, "tags": list(tags),
            "vertices": [[round(float(x), 2), round(float(y), 2), round(float(z), 2)]
                         for x, z in points]}


def navigation_polygons() -> List[dict]:
    """Conservative convex walkable cover for the plateau, avenues and crossings."""
    polygons: List[dict] = []
    y = T.PLATEAU_Y + 0.08

    # the plateau is covered by an inscribed ring of convex wedges
    wedges = 16
    inner, outer = 0.0, layout.RING_ROADS[-1] + 12.0
    for i in range(wedges):
        a0 = TAU * i / wedges
        a1 = TAU * (i + 1) / wedges
        pts = [(math.cos(a0) * inner, math.sin(a0) * inner),
               (math.cos(a0) * outer, math.sin(a0) * outer),
               (math.cos(a1) * outer, math.sin(a1) * outer),
               (math.cos(a1) * inner, math.sin(a1) * inner)]
        polygons.append(_polygon(f"plateau-{i:02d}", pts, y,
                                 ["district", "walkable"]))

    # the four ceremonial avenues continue out to each gate
    for name, angle in (("north", -math.pi / 2), ("south", math.pi / 2),
                        ("east", 0.0), ("west", math.pi)):
        r0, r1 = layout.RING_ROADS[-1], T.PLATEAU_EDGE + 6.0
        half = layout.AVENUE_HALF
        c, s = math.cos(angle), math.sin(angle)
        pts = [(c * r0 - s * half, s * r0 + c * half),
               (c * r1 - s * half, s * r1 + c * half),
               (c * r1 + s * half, s * r1 - c * half),
               (c * r0 + s * half, s * r0 - c * half)]
        polygons.append(_polygon(f"gate-approach-{name}", pts, y, ["avenue", "gate"]))

        # the bridge deck across the water ring
        b0, b1 = T.BRIDGE_NEAR - 8.0, T.BRIDGE_FAR + 8.0
        bh = 13.0
        pts = [(c * b0 - s * bh, s * b0 + c * bh),
               (c * b1 - s * bh, s * b1 + c * bh),
               (c * b1 + s * bh, s * b1 - c * bh),
               (c * b0 + s * bh, s * b0 - c * bh)]
        polygons.append(_polygon(f"bridge-{name}", pts, T.CAUSEWAY_Y + 0.1,
                                 ["bridge", "crossing"]))

        # the far approach on the outer rim, up to the map portal
        if name != "north":
            f0, f1 = T.BRIDGE_FAR, T.RIM_APPROACH_END
            pts = [(c * f0 - s * bh, s * f0 + c * bh),
                   (c * f1 - s * bh, s * f1 + c * bh),
                   (c * f1 + s * bh, s * f1 - c * bh),
                   (c * f0 + s * bh, s * f0 - c * bh)]
            polygons.append(_polygon(f"rim-approach-{name}", pts, T.CAUSEWAY_Y + 0.1,
                                     ["approach", "portal"]))

    # the sanctuary shelf
    shelf_pts = []
    for i in range(8):
        a = TAU * i / 8
        shelf_pts.append((math.cos(a) * 46.0, -T.SANCTUARY_SHELF_R + math.sin(a) * 46.0))
    polygons.append(_polygon("sanctuary-shelf", shelf_pts, T.SANCTUARY_Y + 0.12,
                             ["ceremonial", "portal"]))
    return polygons


## Every Eloria minimap is drawn at this scale. One pixel, one metre.
MINIMAP_PIXELS_PER_METRE = 1.0


def _minimap_block(bounds: dict) -> dict:
    """The packaged cartography, at the scale every map now shares.

    The square is the mesh's own bounds, because that is what the renderer
    frames. Deriving it from `WORLD_EDGE` instead declared a 1584 m square for
    an image that covers 1620 m, so the stated scale was 2% out from the day it
    was written. The old key spellings are kept beside the new ones for one
    release; at this scale `metresPerPixel` and `pixelsPerMetre` are the same
    number anyway.
    """
    low, high = bounds["min"], bounds["max"]
    extent = max(float(high[0]) - float(low[0]), float(high[2]) - float(low[2]))
    pixels = int(round(extent * MINIMAP_PIXELS_PER_METRE))
    min_x = (float(low[0]) + float(high[0])) * 0.5 - extent * 0.5
    min_z = (float(low[2]) + float(high[2])) * 0.5 - extent * 0.5
    return {
        "image": "minimap.webp",
        "imageSize": [pixels, pixels],
        "pixelsPerMetre": MINIMAP_PIXELS_PER_METRE,
        "worldMin": [round(min_x, 4), round(min_z, 4)],
        "worldMax": [round(min_x + extent, 4), round(min_z + extent, 4)],
        "northAxis": "-Z",
        "orientation": "north-up",
        "projection": "orthographic-top-down",
        "renderedFrom": "world.glb",
        "runtime": "live-subviewport",
        "generator": "godot-client/tests/integration/rendered_four_gates_minimap.gd",
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
        "file": "minimap.webp",
        "pixels": pixels,
        "size": [pixels, pixels],
        "metresPerPixel": round(1.0 / MINIMAP_PIXELS_PER_METRE, 6),
        "centre": [round(min_x + extent * 0.5, 4),
                   round(min_z + extent * 0.5, 4)],
        "northUp": True,
    }


def build(stats: dict, bounds: dict, landmark_records: List[dict],
          collision_nodes: List[str], coordinate_transform: dict,
          asset_id: str, asset_name: str, asset_version: str,
          schema_version: str) -> dict:
    plaza_r = layout.PLAZA_RADIUS
    y = T.PLATEAU_Y

    landmarks = list(landmark_records) + [
        {"id": "central-plaza", "name": "Central Plaza", "node": "Plaza_Disc",
         "type": "plaza", "position": _p(0, y, 0),
         "bounds": {"min": _p(-plaza_r, y - 2, -plaza_r),
                    "max": _p(plaza_r, y + 66, plaza_r)}},
        {"id": "civic-monument", "name": "Monument of the Four Gates",
         "node": "Plaza_Monument", "type": "monument", "position": _p(0, y, 0)},
        {"id": "northern-sanctuary", "name": "Northern Sanctuary",
         "node": "Northern_Sanctuary", "type": "sanctuary",
         "position": _p(0, T.SANCTUARY_Y, -T.SANCTUARY_SHELF_R)},
        {"id": "sanctuary-beacon", "name": "Sanctuary Beacon",
         "node": "Sanctuary_Beacon", "type": "beacon",
         "position": _p(0, T.SANCTUARY_Y + 39.6, -T.SANCTUARY_SHELF_R - 14.0)},
    ]

    gates = []
    for gate_id, node, angle in (("north", "Gate_North", -math.pi / 2),
                                 ("south", "Gate_South_Inner", math.pi / 2),
                                 ("east", "Gate_East", 0.0),
                                 ("west", "Gate_West", math.pi)):
        c, s = math.cos(angle), math.sin(angle)
        gates.append({
            "id": gate_id, "node": node,
            "portcullisNode": f"{node}_Portcullis",
            "traversalWidth": 12.0, "traversalHeight": 16.6,
            "traversable": True, "locked": False, "states": ["open", "closed"],
            "animation": f"{node}_Portcullis_OpenClose",
            "exteriorApproach": _p(c * (T.WALL_RADIUS + 34), y, s * (T.WALL_RADIUS + 34)),
            "interiorApproach": _p(c * (T.WALL_RADIUS - 34), y, s * (T.WALL_RADIUS - 34)),
            "connectedBridgeId": gate_id,
            "interactionId": f"interact-{gate_id}",
        })
    gates.append({
        "id": "south-outer", "node": "Gate_South_Outer",
        "portcullisNode": "Gate_South_Outer_Portcullis",
        "traversalWidth": 12.0, "traversalHeight": 16.6,
        "traversable": True, "locked": False, "states": ["open", "closed"],
        "animation": "Gate_South_Outer_Portcullis_OpenClose",
        "exteriorApproach": _p(0, T.CAUSEWAY_Y, 640.0),
        "interiorApproach": _p(0, T.CAUSEWAY_Y, 552.0),
        "connectedBridgeId": "south",
        "interactionId": "interact-south-outer",
    })

    bridges = []
    for name, angle in (("north", -math.pi / 2), ("south", math.pi / 2),
                        ("east", 0.0), ("west", math.pi)):
        centre = (T.BRIDGE_NEAR + T.BRIDGE_FAR) * 0.5
        bridges.append({
            "id": name, "node": f"Bridge_{name.capitalize()}",
            "deckNode": f"Deck_Bridge_{name.capitalize()}",
            "walkable": True, "spanMetres": round(T.BRIDGE_FAR - T.BRIDGE_NEAR, 1),
            "deckHeight": T.CAUSEWAY_Y,
            "position": _p(math.cos(angle) * centre, T.CAUSEWAY_Y,
                           math.sin(angle) * centre),
            "connects": ["city", f"{name}-rim"],
        })

    portals = []
    for name, angle, target in (("south", math.pi / 2, "nymara.south"),
                                ("east", 0.0, "nymara.east"),
                                ("west", math.pi, "nymara.west"),
                                ("north", -math.pi / 2, "nymara.sanctuary")):
        r = T.RIM_APPROACH_END if name != "north" else T.SANCTUARY_SHELF_R - 22.0
        py = T.CAUSEWAY_Y if name != "north" else T.SANCTUARY_Y
        portals.append({
            "id": name,
            "position": _p(math.cos(angle) * r, py, math.sin(angle) * r),
            "radius": 9.0, "targetHook": target,
        })

    for entry in INDEX.INTERIORS:
        portals.append({
            "id": f"interior-{entry['id']}",
            "position": entry["door"],
            "radius": 2.4,
            "targetMap": f"{entry['id']}",
            "targetSpawn": "entrance",
            "doorNode": f"Door_{entry['id']}",
            "label": entry["name"],
            "quarter": entry["quarter"],
            "trade": entry["trade"],
        })

    harvestables = [
        {"id": "resonant-crystal-east", "resource": "resonant_crystal",
         "position": _p(238, y, 120), "radius": 2.5, "respawnSeconds": 90},
        {"id": "stormglass-west", "resource": "stormglass_shard",
         "position": _p(-242, y, 116), "radius": 2.5, "respawnSeconds": 90},
        {"id": "mirror-reed-south", "resource": "mirror_reed",
         "position": _p(-82, y, 258), "radius": 2.5, "respawnSeconds": 90},
        {"id": "sunmane-seed-north", "resource": "sunmane_seed",
         "position": _p(92, y, -252), "radius": 2.5, "respawnSeconds": 90},
    ]

    npc_markers = [
        {"id": "toran-civic-official", "actorType": 307, "role": "official",
         "position": _p(-28, y, 42), "rotationDegrees": 200},
        {"id": "nima-vey-merchant", "actorType": 309, "role": "merchant",
         "position": _p(-142, y, -92), "rotationDegrees": 45},
        {"id": "south-gate-guard", "actorType": 301, "role": "guard",
         "position": _p(18, y, 325), "rotationDegrees": 180},
        {"id": "north-gate-guard", "actorType": 308, "role": "guard",
         "position": _p(-18, y, -325), "rotationDegrees": 0},
        {"id": "east-gate-guard", "actorType": 301, "role": "guard",
         "position": _p(325, y, 18), "rotationDegrees": 270},
        {"id": "west-gate-guard", "actorType": 308, "role": "guard",
         "position": _p(-325, y, -18), "rotationDegrees": 90},
        {"id": "civic-scholar", "actorType": 304, "role": "scholar",
         "position": _p(-112, y, 70), "rotationDegrees": 110},
        {"id": "ferry-lantern-bearer", "actorType": 303, "role": "ferryman",
         "position": _p(15, T.CAUSEWAY_Y, 448), "rotationDegrees": 180},
        {"id": "sanctuary-lake-priest", "actorType": 305, "role": "lake_priest",
         "position": _p(0, T.SANCTUARY_Y, -T.SANCTUARY_SHELF_R + 16), "rotationDegrees": 0},
    ]

    creature_spawns = [
        {"id": "garden-mirrorfin-otters", "creature": "mirrorfin_otter",
         "position": _p(225, y, -185), "radius": 22, "maxAlive": 4},
        {"id": "shore-gate-turtles", "creature": "gate_turtle",
         "position": _p(-270, T.WATER_Y + 2.0, 185), "radius": 24, "maxAlive": 3},
        {"id": "outer-reedhorn-stags", "creature": "reedhorn_stag",
         "position": _p(248, T.CAUSEWAY_Y, 640), "radius": 30, "maxAlive": 2},
        {"id": "cliff-lakeglass-drakes", "creature": "lakeglass_drake",
         "position": _p(-300, 6.0, -300), "radius": 34, "maxAlive": 2},
    ]

    regions = [
        {"id": "central-plaza", "position": _p(0, y, 0), "radius": 86,
         "tags": ["safe", "civic"]},
        {"id": "civic-quarter", "position": _p(-190, y, -30), "radius": 140,
         "tags": ["safe", "market"]},
        {"id": "residential-quarter", "position": _p(200, y, 20), "radius": 145,
         "tags": ["safe", "residential"]},
        {"id": "agricultural-quarter", "position": _p(0, y, 250), "radius": 130,
         "tags": ["safe", "harvest"]},
        {"id": "service-quarter", "position": _p(0, y, -250), "radius": 130,
         "tags": ["safe", "service"]},
        {"id": "sanctuary-approach",
         "position": _p(0, T.SANCTUARY_Y, -T.SANCTUARY_SHELF_R), "radius": 120,
         "tags": ["ceremonial", "portal"]},
    ]

    effects = [
        {"id": "water-ring", "type": "water-pbr", "node": "Water_Ring_Surface",
         "uvScroll": [0.018, -0.032], "color": [0.086, 0.556, 0.612, 0.78]},
        {"id": "falls", "type": "waterfall-sheet", "nodePrefix": "Waterfall_",
         "uvScroll": [0.0, -0.34], "customShaderRecommended": True},
        {"id": "blue-energy", "type": "emissive-pulse",
         "nodeSuffix": ["Crystal", "Beacon_Flame", "Portal"],
         "pulseHz": 0.75, "color": [0.106, 0.404, 0.930, 1.0]},
    ] + [
        {"id": f"waterfall-mist-{i:02d}", "type": "mist-emitter",
         "node": f"FX_Waterfall_Mist_{i:02d}",
         "dimensions": [40, 36, 28], "color": [0.72, 0.9, 1.0],
         "intensity": 0.65, "fallback": "locator-only"}
        for i in range(T.WATERFALL_COUNT)
    ]

    return {
        "schemaVersion": schema_version,
        "assetVersion": asset_version,
        "asset": {
            "id": asset_id,
            "name": asset_name,
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0.0, 0.0, 0.0],
            "bounds": bounds,
            # The server's 720-cell city grid ends at the four causeways;
            # the ocean and mountain backdrop extend far beyond it.
            "mapBounds": {"min": [-360.0, bounds["min"][1], -360.0],
                          "max": [360.0, bounds["max"][1], 360.0]},
            "cityRingDiameterMetres": round(T.WALL_RADIUS * 2.0, 1),
            "plateauWalkHeight": T.PLATEAU_Y,
            "waterLevel": T.WATER_Y,
        },
        "coordinateTransform": coordinate_transform,
        "camera": {"distance": 26.0, "minDistance": 8.0, "maxDistance": 90.0,
                   "pitchDegrees": -60.0, "zoomStep": 2.5},
        "landmarks": landmarks,
        "interiors": [
            {"id": e["id"], "name": e["name"], "quarter": e["quarter"],
             "trade": e["trade"], "door": e["door"],
             "doorNode": f"Door_{e['id']}", "map": f"{e['id']}",
             "description": e["blurb"]}
            for e in INDEX.INTERIORS
        ],
        "districts": [
            {"id": "civic", "name": "Civic Quarter", "node": "District_Civic"},
            {"id": "residential", "name": "Residential Quarter",
             "node": "District_Residential"},
            {"id": "agricultural", "name": "Agricultural Quarter",
             "node": "District_Agricultural"},
            {"id": "service", "name": "Service Quarter", "node": "District_Service"},
        ],
        "gates": gates,
        "bridges": bridges,
        "spawnPoints": [
            {"id": "player-plaza", "node": "Spawn_Player_Plaza",
             "position": _p(0, y, 55), "facing": [0, 0, -1], "default": True},
            {"id": "player-south-gate", "node": "Spawn_Player_South_Gate",
             "position": _p(0, y, 310), "facing": [0, 0, -1]},
        ],
        "pointsOfInterest": [
            {"id": "sanctuary", "node": "POI_Sanctuary",
             "position": _p(0, T.SANCTUARY_Y, -T.SANCTUARY_SHELF_R + 8)},
            {"id": "plaza", "node": "POI_Central_Plaza", "position": _p(0, y, 0)},
        ],
        "paths": [
            {"id": "south-ceremonial-axis", "widthMetres": 30.0,
             "connects": ["south-outer", "south", "central-plaza"],
             "waypoints": [_p(0, T.CAUSEWAY_Y, 640), _p(0, T.CAUSEWAY_Y, 470),
                           _p(0, y, 352), _p(0, y, 160), _p(0, y, 0)]},
            {"id": "north-sanctuary-axis", "widthMetres": 30.0,
             "connects": ["central-plaza", "north", "northern-sanctuary"],
             "waypoints": [_p(0, y, 0), _p(0, y, -352), _p(0, T.CAUSEWAY_Y, -520),
                           _p(0, T.SANCTUARY_Y, -T.SANCTUARY_SHELF_R + 40)]},
        ],
        "interactives": [
            {"id": g["interactionId"], "type": "gate-portcullis",
             "node": g["portcullisNode"], "initialState": "open",
             "animation": g["animation"]}
            for g in gates
        ],
        "portals": portals,
        "harvestables": harvestables,
        "npcMarkers": npc_markers,
        "creatureSpawns": creature_spawns,
        "regions": regions,
        "effects": effects,
        "environment": {
            "sky": {"type": "gradient", "horizon": [0.678, 0.784, 0.859],
                    "zenith": [0.239, 0.451, 0.729],
                    "groundHorizon": [0.573, 0.596, 0.573],
                    "groundBottom": [0.400, 0.400, 0.373],
                    "sunAngleMaxDegrees": 14.0},
            "sun": {"direction": [-0.40, -0.72, 0.34],
                    "color": [1.0, 0.937, 0.812], "energy": 1.10,
                    "angularDiameterDegrees": 0.6, "shadows": True},
            "ambient": {"color": [0.647, 0.667, 0.686], "energy": 0.46,
                        "skyContribution": 0.60},
            "fog": {"enabled": True, "color": [0.639, 0.741, 0.831],
                    "startMetres": 620.0, "endMetres": 2100.0,
                    "density": 0.00011, "skyAffect": 0.04,
                    "aerialPerspective": 0.12},
            "tonemap": {"mode": "filmic", "exposure": 0.94, "whitePoint": 9.0},
            "water": {"level": T.WATER_Y, "shallowColor": [0.176, 0.706, 0.729],
                      "deepColor": [0.043, 0.294, 0.408], "uvScroll": [0.018, -0.032]},
            "ambientAudio": [
                {"id": "city-ambience", "region": "central-plaza",
                 "loop": "civic_crowd", "gain": 0.5},
                {"id": "falls-ambience", "nodePrefix": "Waterfall_",
                 "loop": "waterfall", "gain": 0.7, "radius": 120},
            ],
        },
        "minimap": _minimap_block(bounds),
        "collision": {
            "nodeNames": collision_nodes,
            "nodesAreProxies": True,
            "note": ("Low-poly proxies inset inside their parent geometry. They "
                     "carry no surface the player should see, so the client hides "
                     "them and keeps only the shape built from them: inset by a "
                     "few millimetres they are coplanar with the wall they stand "
                     "for at any distance the depth buffer can still resolve."),
        },
        "navigation": {
            "nodeNames": ["Navigation"],
            "walkableAreas": ["plateau", "avenues", "ring-roads", "bridges",
                              "plaza", "sanctuary-shelf"],
            "surfaceNodePrefixes": ["Terrain_", "Road_", "Plaza_Disc", "Deck_",
                                    "Stair_"],
            "navmesh": {
                "format": "inline-convex-polygons-v1",
                "coordinateSystem": "asset",
                "agentRadius": 0.6, "agentHeight": 2.0, "maxSlopeDegrees": 35,
                "polygons": navigation_polygons(),
            },
            "exclusions": [
                {"id": "central-monument", "shape": "cylinder",
                 "centre": _p(0, T.PLATEAU_Y, 0), "radius": 11.0},
                {"id": "outside-wall", "shape": "outside-circle",
                 "centre": _p(0, T.PLATEAU_Y, 0), "radius": T.PLATEAU_EDGE},
            ],
        },
        "performance": stats,
        "sources": [
            {"id": "canonical-aerial", "file": "references/00-canonical-aerial.png",
             "role": "authoritative-layout"},
            {"id": "reference-board", "file": "references/",
             "role": "architecture-materials-props"},
        ],
        "assumptions": [
            "Canonical city defensive ring diameter is 704 m (wall centre radius 352 m).",
            "City plateau walking elevation is Y=31; water surface is Y=-2.",
            "The aerial governs layout; the perspective panels govern silhouette, "
            "material and ornament language.",
            "The existing development server coordinate binding is preserved "
            "unchanged so no server profile edit is required to load this map.",
        ],
        "knownLimitations": [
            "Water, foam and mist read as static glTF geometry when the client's "
            "effect shaders are disabled.",
            "Navigation polygons are conservative convex cover; final per-alley "
            "blockers should be rebaked from the collision proxies if the server "
            "adopts client-side pathing.",
        ],
    }
