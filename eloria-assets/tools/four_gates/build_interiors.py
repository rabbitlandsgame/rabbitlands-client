#!/usr/bin/env python3
"""Build the Four Gates interior map packages.

Each interior is an ordinary Eloria world package -- `world.glb` plus
`world.json` under `eloria-assets/maps/<id>/` -- because `WorldLoader` has no
special case for interiors. They differ from the city only in scale, in the
material subset they embed, and in carrying manifest-declared point lights
instead of a sky.

Run:  python3 eloria-assets/tools/four_gates/build_interiors.py
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import interior_index as INDEX   # noqa: E402
import interiors as I     # noqa: E402
import kits               # noqa: E402
import meshlib as M       # noqa: E402
from assembly import (INTERIOR_RESOLUTION, INTERIOR_RESOLUTIONS,  # noqa: E402
                      MaterialLibrary, SceneBuilder)
from gltf_writer import GLB       # noqa: E402
from meshlib import Geo           # noqa: E402

TAU = math.pi * 2.0
SCHEMA_VERSION = "1.0.0"
ASSET_VERSION = "1.0.0"

## Every Eloria map answers the server at one metre per tile. These interiors
## were the last that did not: they used a quarter-metre tile so that indoor
## click-to-move landed precisely, which is a real thing given up here - a
## sixteen-metre room is sixteen tiles across now rather than sixty-four.
METRES_PER_TILE = 1.0
## Collision grids come in multiples of six, so tile grids do too, and each
## room's carries a few metres of margin outside its own walls.
TILE_STEP = 6
TILE_MARGIN = 6.0


def coordinate_transform(spec) -> dict:
    """One interior's grid, sized to the room it addresses.

    The quarter-metre tile implied a 256 m addressable band from a fixed
    origin of 512, which for a room sixteen metres across described mostly
    nothing. The grid is measured from the room instead, so the band is a few
    metres wider than the walls and the origin sits at their centre.
    """
    extent = max(spec.width, spec.depth) + 3.0
    tiles = int(math.ceil((extent + TILE_MARGIN) / TILE_STEP)) * TILE_STEP
    return {
        "metresPerTile": METRES_PER_TILE,
        "serverOrigin": [tiles / 2.0, tiles / 2.0],
        "origin": [0.0, 0.05, 0.0],
        "walkingHeight": 0.05,
        "invertServerY": True,
    }

# (room_shell_parts key, node name). The outward normals below drive the
# client-side cutaway, so the two lists have to stay in step.
SHELL_NODES = (
    ("ceiling", "Shell_Ceiling"),
    ("beams", "Shell_Beams"),
    ("wall_north", "Shell_Wall_North"),
    ("wall_south", "Shell_Wall_South"),
    ("wall_east", "Shell_Wall_East"),
    ("wall_west", "Shell_Wall_West"),
)
SHELL_OUTWARD = {
    "Shell_Wall_North": [0.0, 0.0, -1.0],
    "Shell_Wall_South": [0.0, 0.0, 1.0],
    "Shell_Wall_East": [1.0, 0.0, 0.0],
    "Shell_Wall_West": [-1.0, 0.0, 0.0],
}

BASE_MATERIALS = ["stone_ashlar", "stone_trim", "plaster_warm", "timber_dark",
                  "paving_road", "metal_gold", "metal_iron", "glass_window",
                  "cloth_banner", "crystal_blue", "lamp_glow"]


class Interior:
    """One interior: a room shell, a furniture layout and its metadata."""

    def __init__(self, ident: str, name: str, width: float, depth: float,
                 height: float, blurb: str, quarter: str,
                 door_world: Sequence[float], door_yaw: float,
                 materials: Optional[Sequence[str]] = None,
                 ambient: Sequence[float] = (0.32, 0.34, 0.36),
                 ambient_energy: float = 0.55,
                 background: Sequence[float] = (0.04, 0.05, 0.06)):
        self.id = ident
        self.name = name
        self.width = width
        self.depth = depth
        self.height = height
        self.blurb = blurb
        self.quarter = quarter
        self.door_world = list(door_world)   # where the door sits in Four Gates
        self.door_yaw = door_yaw
        self.materials = list(materials or BASE_MATERIALS)
        self.ambient = list(ambient)
        self.ambient_energy = ambient_energy
        self.background = list(background)
        self.lights: List[dict] = []
        self.markers: List[Tuple[str, Tuple[float, float, float]]] = []
        self.npcs: List[dict] = []

    def lamp(self, x: float, y: float, z: float, energy: float = 3.2,
             colour=(1.0, 0.86, 0.66), rng: float = 12.0) -> None:
        self.lights.append({"position": [round(x, 2), round(y, 2), round(z, 2)],
                            "color": list(colour), "energy": energy, "range": rng})


def build_interior(spec: Interior, layout: Callable, out_root: str,
                   cache_dir: Optional[str]) -> dict:
    glb = GLB(f"Eloria Four Gates interior builder -- {spec.id}")
    library = MaterialLibrary(glb, size=512, hero=1024, cache_dir=cache_dir,
                              subset=spec.materials,
                              resolutions=INTERIOR_RESOLUTIONS,
                              default_resolution=INTERIOR_RESOLUTION)
    scene = SceneBuilder(glb, library)
    p = library.palette

    groups: Dict[str, List[int]] = {}

    def add(group: str, node: int) -> int:
        groups.setdefault(group, []).append(node)
        return node

    # floor is its own node so it can carry the navigation surface while the
    # shell carries structural collision
    floor_mesh = scene.mesh("Floor_Mesh",
                            I.room_floor(spec.width, spec.depth, p.paving_road))
    add("Structure", scene.instance("Floor_Deck", floor_mesh))

    openings, extras = layout(spec, p, scene, add)

    # The shell goes in as separate nodes -- ceiling, and one node per wall --
    # so the client can cut away the roof and whichever wall stands between the
    # camera and the room. Built as one mesh it would simply hide the interior.
    parts = I.room_shell_parts(spec.width, spec.depth, spec.height, p,
                               include_floor=False, **openings)
    for key, node_name in SHELL_NODES:
        part = parts.get(key)
        if part is None:
            continue
        mesh = scene.mesh(node_name + "_Mesh", part)
        add("Structure", scene.instance(node_name, mesh))

    order = ["Structure", "Fittings", "Furniture", "Lighting", "Markers"]
    group_nodes = [glb.add_node(g, children=groups[g]) for g in order if groups.get(g)]
    root = glb.add_node("Interior_Root", children=group_nodes)
    glb.scene_roots = [root]

    out_dir = os.path.join(out_root, spec.id)
    os.makedirs(out_dir, exist_ok=True)
    stats = glb.save(os.path.join(out_dir, "world.glb"))
    stats["instances"] = scene.stats["instances"]
    stats["visibleTriangles"] = scene.stats["visibleTriangles"]
    stats["textureMemoryBytes"] = library.texture_memory_bytes()
    stats.pop("path", None)

    manifest = interior_manifest(spec, stats, extras)
    with open(os.path.join(out_dir, "world.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return stats


def interior_manifest(spec: Interior, stats: dict, extras: dict) -> dict:
    half_w, half_d = spec.width * 0.5, spec.depth * 0.5
    # Pull back far enough to hold the long axis of the room in frame.
    distance = min(17.0, max(9.0, max(spec.width, spec.depth) * 0.55 + 3.0))
    spawn = extras.get("spawn", [0.0, 0.0, spec.depth * 0.5 - 2.0])
    # Stand three metres inside the exit, so integer conversion cannot place a
    # new arrival on its automatic return trigger.
    spawn = [spawn[0], spawn[1], min(spawn[2], spec.depth * 0.5 - 3.9)]
    post = INDEX.ROOM_DOOR_POSTS.get(spec.id, {})
    spawn = post.get('arrival', spawn)
    exit_post = post.get('exit', [round(spawn[0], 2), 0., round(spec.depth * .5 - .9, 2)])
    return {
        "schemaVersion": SCHEMA_VERSION,
        "assetVersion": ASSET_VERSION,
        "asset": {
            "id": spec.id,
            "name": spec.name,
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0.0, 0.0, 0.0],
            "bounds": {"min": [-half_w - 1.5, -1.0, -half_d - 1.5],
                       "max": [half_w + 1.5, spec.height + 1.5, half_d + 1.5]},
            "interior": True,
            "parentMap": "four_gates",
            "quarter": spec.quarter,
            "description": spec.blurb,
        },
        "coordinateTransform": coordinate_transform(spec),
        "spawnPoints": [{"id": "entrance", "node": "Spawn_Entrance",
                         "position": [round(v, 2) for v in spawn],
                         "facing": [0, 0, -1], "default": True}],
        "portals": [{
            "id": "exit",
            "position": exit_post,
            "radius": 1.6,
            "targetMap": "four_gates",
            "targetPosition": [round(v, 2) for v in spec.door_world],
            "label": "Out to the street",
        }],
        "landmarks": extras.get("landmarks", []),
        "npcMarkers": spec.npcs,
        "interactives": extras.get("interactives", []),
        "collision": {
            "nodeNames": [name for _key, name in SHELL_NODES
                          if name in SHELL_OUTWARD] + extras.get("collision", []),
            "note": ("The four walls plus solid fittings; the floor is a walk "
                     "surface and the walls stay solid while cut away."),
        },
        "navigation": {
            "surfaceNodePrefixes": ["Floor_", "Deck_", "Stair_"],
            "walkableAreas": ["floor"],
            "navmesh": {
                "format": "inline-convex-polygons-v1",
                "coordinateSystem": "asset",
                "agentRadius": 0.4, "agentHeight": 1.9, "maxSlopeDegrees": 30,
                "polygons": [{
                    "id": "room", "tags": ["interior", "walkable"],
                    "vertices": [
                        [-half_w + 0.6, 0.02, -half_d + 0.6],
                        [half_w - 0.6, 0.02, -half_d + 0.6],
                        [half_w - 0.6, 0.02, half_d - 0.6],
                        [-half_w + 0.6, 0.02, half_d - 0.6]],
                }],
            },
        },
        "camera": {
            "distance": round(distance, 1),
            "minDistance": round(max(6.0, distance - 5.0), 1),
            "maxDistance": round(distance + 6.0, 1),
            "pitchDegrees": -48.0, "zoomStep": 1.2,
            "note": ("Framed for the whole room with the ceiling and near wall "
                     "cut away; closer and shallower than the city rig."),
        },
        "cutaway": {
            "hideNodes": ["Shell_Ceiling", "Shell_Beams"],
            "walls": [{"node": name, "outward": SHELL_OUTWARD[name]}
                      for _key, name in SHELL_NODES if name in SHELL_OUTWARD],
            "facingThreshold": 0.2,
            "note": ("Hide the roof, and any wall whose outward normal points "
                     "back towards the camera, so the room stays visible from "
                     "an isometric rig. Collision is unaffected."),
        },
        "environment": {
            "backgroundColor": spec.background,
            "ambient": {"color": spec.ambient, "energy": spec.ambient_energy,
                        "skyContribution": 0.0},
            "sun": {"enabled": False},
            "fog": {"enabled": False},
            "tonemap": {"mode": "filmic", "exposure": 1.0, "whitePoint": 8.0},
            "lights": spec.lights,
        },
        "performance": stats,
    }


# --------------------------------------------------------------------- layouts
def lantern_row(spec, p, scene, add):
    """Covered market hall: stalls down both sides, counting desk at the end."""
    w, d, h = spec.width, spec.depth, spec.height
    stall = scene.mesh("Stall_Mesh", lambda: kits.market_stall(p, 1))
    shelf = scene.mesh("Shelf_Mesh", lambda: I.shelf_unit(2.2, 2.6, p, seed=4))
    crates = scene.mesh("Crates_Mesh", lambda: I.crate_stack(p, seed=2))
    barrel = scene.mesh("Barrel_Mesh", lambda: kits.barrel(p))
    lantern = scene.mesh("Lantern_Mesh", lambda: I.hanging_lantern(p, 1.1, 0.34))
    desk = scene.mesh("Desk_Mesh", lambda: I.counter(4.4, p))
    post = scene.mesh("Post_Mesh", lambda: M.revolve(
        [(0.24, 0.0), (0.2, 0.5), (0.18, h - 0.7), (0.26, h - 0.35), (0.24, h)],
        8, p.timber_dark, 1.4))

    for i in range(6):
        z = -d * 0.5 + d * (i + 0.5) / 6
        for side in (-1, 1):
            add("Fittings", scene.instance(f"Hall_Post_{i}_{'L' if side < 0 else 'R'}",
                                           post, (side * (w * 0.5 - 2.6), 0.0, z)))
        add("Lighting", scene.instance(f"Hall_Lantern_{i}", lantern,
                                       (0.0, h - 0.25, z)))
        spec.lamp(0.0, h - 1.5, z, energy=3.4, rng=11.0)
    for i in range(5):
        z = -d * 0.5 + 2.4 + (d - 5.6) * i / 4
        for side in (-1, 1):
            add("Furniture", scene.instance(
                f"Hall_Stall_{i}_{'L' if side < 0 else 'R'}", stall,
                (side * (w * 0.5 - 4.6), 0.0, z), 0.0 if side > 0 else math.pi))
    for i in range(4):
        z = -d * 0.5 + 3.0 + (d - 7.0) * i / 3
        add("Furniture", scene.instance(f"Hall_Shelf_{i}", shelf,
                                        (-w * 0.5 + 1.1, 0.0, z), math.pi / 2))
        add("Furniture", scene.instance(f"Hall_Crates_{i}", crates,
                                        (w * 0.5 - 1.6, 0.0, z + 0.6)))
    for i in range(5):
        add("Furniture", scene.instance(f"Hall_Barrel_{i}", barrel,
                                        (w * 0.5 - 2.6, 0.0, -d * 0.5 + 2.0 + i * 2.1)))
    add("Furniture", scene.instance("Counting_Desk", desk, (0.0, 0.0, -d * 0.5 + 1.9)))
    spec.lamp(0.0, 2.4, -d * 0.5 + 2.6, energy=4.0, colour=(0.72, 0.86, 1.0), rng=9.0)
    spec.npcs.append({"id": "nima-vey-merchant", "actorType": 309, "role": "merchant",
                      "position": [0.0, 0.0, -d * 0.5 + 3.1], "rotationDegrees": 180})

    openings = {"south": [(0.0, 3.2, 0.0, 3.4)],
                "east": [(-3.0, 1.4, 2.2, 1.6), (3.0, 1.4, 2.2, 1.6)],
                "beams": 6}
    extras = {
        "spawn": [0.0, 0.0, d * 0.5 - 2.2],
        "collision": ["Counting_Desk"],
        "landmarks": [{"id": "counting-desk", "name": "Nima Vey's counting desk",
                       "node": "Counting_Desk", "type": "vendor",
                       "position": [0.0, 0.0, -d * 0.5 + 1.9]}],
    }
    return openings, extras


def stormglass_house(spec, p, scene, add):
    """Glazier and alchemist: lens benches, racks of blanks, a grinding wheel."""
    w, d, h = spec.width, spec.depth, spec.height
    bench = scene.mesh("Bench_Mesh", lambda: I.work_table(2.6, 1.1, p))
    shelf = scene.mesh("Shelf_Mesh", lambda: I.shelf_unit(2.0, 2.8, p, seed=11))
    stool = scene.mesh("Stool_Mesh", lambda: I.stool(p))
    sconce = scene.mesh("Sconce_Mesh", lambda: I.wall_sconce(p))
    counter = scene.mesh("Counter_Mesh", lambda: I.counter(3.2, p))
    wheel = scene.mesh("Wheel_Mesh", lambda: Geo.concat([
        M.cylinder(0.62, 0.14, 16, p.stone_trim, 0.8).rotate_z(math.pi / 2)
         .translate(0.0, 0.9, 0.0),
        M.box(1.4, 0.9, 0.7, p.timber_dark, 1.0, origin="corner"),
        M.cylinder(0.06, 0.9, 6, p.metal_iron, 0.4).rotate_z(math.pi / 2)
         .translate(0.0, 0.9, 0.0)]))
    lens = scene.mesh("Lens_Mesh", lambda: Geo.concat([
        M.revolve([(0.0, 0.0), (0.26, 0.05), (0.0, 0.1)], 12, p.glass_window, 0.4),
        M.cylinder(0.28, 0.04, 12, p.metal_gold, 0.4)]))

    for i in range(3):
        z = -d * 0.5 + 2.4 + i * 2.6
        add("Furniture", scene.instance(f"Lens_Bench_{i}", bench,
                                        (-w * 0.5 + 2.2, 0.0, z), math.pi / 2))
        add("Furniture", scene.instance(f"Bench_Stool_{i}", stool,
                                        (-w * 0.5 + 3.6, 0.0, z)))
        add("Furniture", scene.instance(f"Ground_Lens_{i}", lens,
                                        (-w * 0.5 + 2.2, 0.78, z + 0.4)))
    for i in range(3):
        add("Furniture", scene.instance(f"Blank_Shelf_{i}", shelf,
                                        (w * 0.5 - 1.2, 0.0, -d * 0.5 + 2.6 + i * 2.6),
                                        -math.pi / 2))
    add("Furniture", scene.instance("Grinding_Wheel", wheel, (2.0, 0.0, d * 0.5 - 3.2)))
    add("Furniture", scene.instance("Sale_Counter", counter, (0.0, 0.0, -d * 0.5 + 1.6)))
    for i, (x, z) in enumerate([(-w * 0.5 + 0.4, 0.0), (w * 0.5 - 0.4, 0.0),
                                (0.0, -d * 0.5 + 0.4)]):
        add("Lighting", scene.instance(f"Sconce_{i}", sconce, (x, 2.5, z),
                                       math.pi / 2 if i < 2 else 0.0))
        spec.lamp(x * 0.85, 2.6, z * 0.85, energy=3.0, colour=(0.68, 0.84, 1.0), rng=9.0)
    spec.lamp(0.0, h - 1.0, 0.0, energy=2.4, colour=(0.86, 0.9, 1.0), rng=12.0)

    openings = {"south": [(0.0, 1.7, 0.0, 2.6)],
                "west": [(0.0, 2.6, 1.3, 1.7)], "beams": 3}
    extras = {"spawn": [0.0, 0.0, d * 0.5 - 1.9],
              "collision": ["Sale_Counter", "Grinding_Wheel"],
              "interactives": [{"id": "grinding-wheel", "type": "workstation",
                                "node": "Grinding_Wheel", "skill": "crafting"}]}
    return openings, extras


def mirrorsmith_forge(spec, p, scene, add):
    """Smithy: hearth, anvil, quench trough fed from the ring, and a keystone."""
    w, d, h = spec.width, spec.depth, spec.height
    forge = scene.mesh("Hearth_Mesh", lambda: I.hearth(3.0, p, 2.3))
    anvil = scene.mesh("Anvil_Mesh", lambda: Geo.concat([
        M.box(0.7, 0.55, 0.7, p.timber_dark, 0.8, origin="corner"),
        M.tapered_box(1.3, 0.42, 0.9, 0.34, 0.34, p.metal_iron, 0.6)
         .translate(0.0, 0.55, 0.0),
        M.cone(0.17, 0.5, 8, p.metal_iron, 0.5).rotate_z(math.pi / 2)
         .translate(0.78, 0.72, 0.0)]))
    trough = scene.mesh("Trough_Mesh", lambda: Geo.concat([
        M.box(2.6, 0.7, 1.0, p.stone_trim, 1.0, origin="corner"),
        M.box(2.3, 0.06, 0.72, p.crystal_blue, 1.0, origin="corner")
         .translate(0.0, 0.62, 0.0)]))
    rack = scene.mesh("Rack_Mesh", lambda: Geo.concat([
        M.box(2.6, 0.16, 0.3, p.timber_dark, 0.8, origin="corner")
         .translate(0.0, 1.85, 0.0),
        M.box(2.6, 0.16, 0.3, p.timber_dark, 0.8, origin="corner")
         .translate(0.0, 0.9, 0.0)] + [
        M.box(0.14, 1.5, 0.14, p.metal_iron, 0.5, origin="corner")
         .translate(-1.0 + k * 0.5, 0.5, 0.0) for k in range(5)]))
    bench = scene.mesh("Bench_Mesh", lambda: I.work_table(2.4, 1.0, p))
    keystone = scene.mesh("Keystone_Mesh", lambda: Geo.concat([
        M.tapered_box(1.5, 1.0, 1.05, 1.0, 1.2, p.stone_ashlar, 1.4),
        M.box(0.9, 0.1, 1.02, p.stone_trim, 0.8, origin="corner")
         .translate(0.0, 1.2, 0.0)]))

    add("Furniture", scene.instance("Forge_Hearth", forge, (0.0, 0.0, -d * 0.5 + 0.3)))
    add("Furniture", scene.instance("Anvil", anvil, (-1.8, 0.0, -d * 0.5 + 3.4)))
    add("Furniture", scene.instance("Quench_Trough", trough, (2.6, 0.0, -d * 0.5 + 3.6),
                                    math.pi / 2))
    add("Furniture", scene.instance("Weapon_Rack", rack, (-w * 0.5 + 0.5, 0.0, 0.6),
                                    math.pi / 2))
    add("Furniture", scene.instance("Smith_Bench", bench, (w * 0.5 - 1.8, 0.0, 1.4),
                                    math.pi / 2))
    add("Furniture", scene.instance("The_Odd_Keystone", keystone,
                                    (w * 0.5 - 1.6, 0.0, d * 0.5 - 2.0), 0.4))
    shelf = scene.mesh("Stock_Shelf_Mesh",
                       lambda: I.shelf_unit(2.2, 2.6, p, seed=21))
    barrel = scene.mesh("Barrel_Mesh", lambda: kits.barrel(p))
    crates = scene.mesh("Crates_Mesh", lambda: I.crate_stack(p, seed=7))
    ingots = scene.mesh("Ingot_Mesh", lambda: Geo.concat([
        M.tapered_box(0.7, 0.3, 0.56, 0.24, 0.16, p.metal_iron, 0.4)
         .translate(0.0, 0.16 * k, 0.03 * k) for k in range(4)]))
    tongs = scene.mesh("Tool_Rack_Mesh", lambda: Geo.concat(
        [M.box(1.8, 0.12, 0.14, p.timber_dark, 0.8, origin="corner")
         .translate(0.0, 1.7, 0.0)] +
        [M.box(0.07, 0.62, 0.07, p.metal_iron, 0.4, origin="corner")
         .translate(-0.65 + k * 0.33, 1.05, 0.0) for k in range(5)]))
    for i in range(2):
        add("Furniture", scene.instance(f"Stock_Shelf_{i}", shelf,
                                        (-w * 0.5 + 1.2, 0.0, 3.0 + i * 2.8),
                                        math.pi / 2))
    for i in range(3):
        add("Furniture", scene.instance(f"Forge_Barrel_{i}", barrel,
                                        (w * 0.5 - 1.4, 0.0, -d * 0.5 + 1.6 + i * 1.0)))
    add("Furniture", scene.instance("Forge_Crates", crates, (-3.6, 0.0, d * 0.5 - 2.4)))
    add("Furniture", scene.instance("Iron_Stock", ingots, (-2.6, 0.0, -d * 0.5 + 5.2)))
    add("Fittings", scene.instance("Tool_Rack", tongs, (0.6, 0.0, -d * 0.5 + 0.5)))
    spec.lamp(0.0, 1.3, -d * 0.5 + 1.4, energy=6.0, colour=(1.0, 0.62, 0.34), rng=13.0)
    spec.lamp(0.0, h - 1.2, 1.0, energy=2.0, colour=(0.8, 0.86, 1.0), rng=13.0)
    spec.lamp(2.6, 1.0, -d * 0.5 + 3.6, energy=2.2, colour=(0.4, 0.78, 1.0), rng=7.0)

    openings = {"south": [(0.0, 2.4, 0.0, 3.0)],
                "east": [(1.5, 1.6, 1.6, 1.6)], "beams": 4}
    extras = {"spawn": [0.0, 0.0, d * 0.5 - 2.0],
              "collision": ["Forge_Hearth", "Anvil", "Quench_Trough", "Smith_Bench",
                            "The_Odd_Keystone"],
              "landmarks": [{"id": "odd-keystone",
                             "name": "The keystone that fits no arch",
                             "node": "The_Odd_Keystone", "type": "curiosity",
                             "position": [w * 0.5 - 1.6, 0.0, d * 0.5 - 2.0]}],
              "interactives": [{"id": "forge-anvil", "type": "workstation",
                                "node": "Anvil", "skill": "manufacturing"}]}
    return openings, extras


def reedworks(spec, p, scene, add):
    """Cordage and cloth from mirror reed: dye vats, looms, drying racks."""
    w, d, h = spec.width, spec.depth, spec.height
    vat = scene.mesh("Vat_Mesh", lambda: Geo.concat([
        M.revolve([(1.0, 0.0), (1.1, 0.2), (1.1, 1.0), (0.98, 1.06)],
                  14, p.stone_trim, 1.2),
        M.cylinder(0.96, 0.04, 14, p.cloth_banner, 1.0).translate(0.0, 0.94, 0.0)]))
    loom = scene.mesh("Loom_Mesh", lambda: Geo.concat([
        M.box(2.2, 2.2, 0.2, p.timber_dark, 1.0, origin="corner")
         .translate(0.0, 0.0, -0.5),
        M.box(2.2, 2.2, 0.2, p.timber_dark, 1.0, origin="corner")
         .translate(0.0, 0.0, 0.5),
        M.box(2.0, 1.5, 0.9, p.canvas_awning if "canvas_awning" in
              spec.materials else p.cloth_banner, 1.0, origin="corner")
         .translate(0.0, 0.4, 0.0),
        M.box(2.4, 0.16, 1.2, p.timber_dark, 0.8, origin="corner")
         .translate(0.0, 2.2, 0.0)]))
    bundle = scene.mesh("Reed_Mesh", lambda: Geo.concat([
        M.cylinder(0.3, 2.0, 8, p.thatch_straw if "thatch_straw" in spec.materials
                   else p.timber_dark, 1.0).rotate_z(0.18),
        M.cylinder(0.32, 0.1, 8, p.metal_iron, 0.4).translate(0.0, 1.2, 0.0)]))
    rack = scene.mesh("Dry_Rack_Mesh", lambda: Geo.concat(
        [M.box(0.12, 2.4, 0.12, p.timber_dark, 0.8, origin="corner")
         .translate(x, 0.0, 0.0) for x in (-1.6, 1.6)] +
        [M.box(3.4, 0.1, 0.1, p.timber_dark, 0.8, origin="corner")
         .translate(0.0, 2.3, 0.0)] +
        [M.box(0.9, 1.5, 0.05, p.cloth_banner, 1.0, origin="corner")
         .translate(-1.0 + k * 1.0, 0.75, 0.0) for k in range(3)]))
    bench = scene.mesh("Bench_Mesh", lambda: I.work_table(2.4, 1.0, p))

    for i in range(3):
        add("Furniture", scene.instance(f"Dye_Vat_{i}", vat,
                                        (-w * 0.5 + 2.2, 0.0, -d * 0.5 + 2.6 + i * 3.0)))
        spec.lamp(-w * 0.5 + 2.2, 1.4, -d * 0.5 + 2.6 + i * 3.0, energy=1.8,
                  colour=(0.42, 0.7, 0.9), rng=6.0)
    for i in range(2):
        add("Furniture", scene.instance(f"Loom_{i}", loom,
                                        (2.0, 0.0, -d * 0.5 + 3.0 + i * 3.4),
                                        math.pi / 2))
    for i in range(3):
        add("Furniture", scene.instance(f"Drying_Rack_{i}", rack,
                                        (w * 0.5 - 1.5, 0.0, d * 0.5 - 2.4 - i * 2.2),
                                        math.pi / 2))
    for i in range(5):
        add("Furniture", scene.instance(f"Reed_Bundle_{i}", bundle,
                                        (-w * 0.5 + 0.9, 0.0, d * 0.5 - 1.4 - i * 0.7),
                                        i * 0.7))
    add("Furniture", scene.instance("Cutting_Bench", bench, (0.0, 0.0, 0.5)))
    spec.lamp(0.0, h - 0.8, -1.0, energy=2.6, colour=(0.92, 0.92, 0.86), rng=14.0)
    spec.lamp(0.0, h - 0.8, 4.0, energy=2.2, colour=(0.92, 0.92, 0.86), rng=12.0)

    openings = {"south": [(0.0, 2.0, 0.0, 2.8)],
                "west": [(-2.0, 2.2, 1.4, 1.8), (2.4, 2.2, 1.4, 1.8)], "beams": 5}
    extras = {"spawn": [0.0, 0.0, d * 0.5 - 2.0],
              "collision": ["Cutting_Bench"],
              "interactives": [{"id": "reed-loom", "type": "workstation",
                                "node": "Loom_0", "skill": "tailoring"}]}
    return openings, extras


def ferrymans_rest(spec, p, scene, add):
    """Low tavern at the north dock: hearth, tables, bar, and the work board."""
    w, d, h = spec.width, spec.depth, spec.height
    fire = scene.mesh("Hearth_Mesh", lambda: I.hearth(2.6, p, 2.0))
    bar = scene.mesh("Bar_Mesh", lambda: I.counter(5.0, p, 1.1, 0.8))
    table = scene.mesh("Table_Mesh", lambda: I.work_table(1.7, 1.7, p, 0.74))
    stool = scene.mesh("Stool_Mesh", lambda: I.stool(p))
    barrel = scene.mesh("Barrel_Mesh", lambda: kits.barrel(p))
    lantern = scene.mesh("Lantern_Mesh", lambda: I.hanging_lantern(p, 0.7, 0.26))
    board = scene.mesh("Board_Mesh", lambda: Geo.concat([
        M.box(2.2, 1.5, 0.1, p.timber_dark, 1.0, origin="corner"),
        M.box(2.35, 0.12, 0.14, p.metal_gold, 0.6, origin="corner")
         .translate(0.0, 1.5, 0.0)] + [
        M.box(0.3, 0.4, 0.02, p.plaster_warm, 0.4, origin="corner")
         .translate(-0.7 + k * 0.45, 0.5 + (k % 3) * 0.28, 0.06) for k in range(5)]))
    rug = scene.mesh("Rug_Mesh", lambda: I.rug(3.4, 2.4, p))

    add("Furniture", scene.instance("Tavern_Hearth", fire, (-w * 0.5 + 0.3, 0.0, 0.0),
                                    math.pi / 2))
    add("Furniture", scene.instance("Tavern_Rug", rug, (-w * 0.5 + 3.0, 0.0, 0.0)))
    add("Furniture", scene.instance("Ferry_Bar", bar, (0.0, 0.0, -d * 0.5 + 1.5)))
    add("Fittings", scene.instance("Work_Board", board,
                                   (w * 0.5 - 0.42, 1.0, -1.4), -math.pi / 2))
    for i, (x, z) in enumerate([(-1.6, 1.4), (2.2, 1.0), (0.4, 3.2), (3.4, 3.4)]):
        add("Furniture", scene.instance(f"Tavern_Table_{i}", table, (x, 0.0, z),
                                        i * 0.4))
        for k in range(3):
            a = TAU * k / 3 + i
            add("Furniture", scene.instance(
                f"Tavern_Stool_{i}_{k}", stool,
                (x + math.cos(a) * 1.25, 0.0, z + math.sin(a) * 1.25)))
    for i in range(4):
        add("Furniture", scene.instance(f"Cellar_Barrel_{i}", barrel,
                                        (-w * 0.5 + 1.4 + i * 0.9, 0.0, -d * 0.5 + 1.2)))
    for i in range(4):
        z = -d * 0.5 + d * (i + 0.5) / 4
        add("Lighting", scene.instance(f"Tavern_Lantern_{i}", lantern,
                                       (0.0, h - 0.2, z)))
        spec.lamp(0.0, h - 1.1, z, energy=2.6, colour=(1.0, 0.82, 0.6), rng=8.0)
    spec.lamp(-w * 0.5 + 1.2, 1.1, 0.0, energy=4.4, colour=(1.0, 0.58, 0.3), rng=10.0)
    spec.npcs.append({"id": "ferry-lantern-bearer", "actorType": 303,
                      "role": "ferryman", "position": [0.0, 0.0, -d * 0.5 + 2.9],
                      "rotationDegrees": 180})

    openings = {"south": [(0.0, 1.8, 0.0, 2.4)],
                "north": [(-3.0, 1.2, 1.1, 1.2), (3.0, 1.2, 1.1, 1.2)], "beams": 5}
    extras = {"spawn": [0.0, 0.0, d * 0.5 - 1.8],
              "collision": ["Ferry_Bar", "Tavern_Hearth"],
              "landmarks": [{"id": "work-board", "name": "The ferry crews' board",
                             "node": "Work_Board", "type": "noticeboard",
                             "position": [w * 0.5 - 0.42, 1.0, -1.4]}]}
    return openings, extras


def deposit_of_four_keys(spec, p, scene, add):
    """Vaulted strongroom: four keyed doors, and a fifth under new plaster."""
    w, d, h = spec.width, spec.depth, spec.height
    vault_door = scene.mesh("Vault_Door_Mesh", lambda: Geo.concat([
        M.arch_ring(1.05, 1.5, 0.5, 0.0, math.pi, 12, p.stone_trim, 1.4)
         .translate(0.0, 1.5, 0.0),
        M.box(2.1, 1.5, 0.5, p.stone_trim, 1.2, origin="corner"),
        M.cylinder(0.95, 0.24, 20, p.metal_iron, 0.8).rotate_x(math.pi / 2)
         .translate(0.0, 1.5, 0.22),
        M.torus_arc(0.62, 0.09, 0.0, TAU, 20, 6, p.metal_gold, 0.6)
         .rotate_x(math.pi / 2).translate(0.0, 1.5, 0.34),
        M.revolve([(0.0, 0.0), (0.2, 0.12), (0.0, 0.34)], 8, p.crystal_blue, 0.4)
         .rotate_x(-math.pi / 2).translate(0.0, 1.5, 0.4)]))
    sealed = scene.mesh("Sealed_Bay_Mesh", lambda: Geo.concat([
        M.box(2.1, 3.0, 0.42, p.plaster_warm, 1.2, origin="corner"),
        M.box(2.3, 0.14, 0.5, p.stone_trim, 0.8, origin="corner")
         .translate(0.0, 3.0, 0.0)]))
    desk = scene.mesh("Clerk_Desk_Mesh", lambda: I.counter(3.0, p))
    chest = scene.mesh("Chest_Mesh", lambda: Geo.concat([
        M.box(1.1, 0.66, 0.68, p.timber_dark, 0.8, origin="corner"),
        M.box(1.14, 0.1, 0.72, p.metal_iron, 0.5, origin="corner")
         .translate(0.0, 0.66, 0.0),
        M.box(0.16, 0.78, 0.74, p.metal_gold, 0.5, origin="corner")]))
    vault = scene.mesh("Vault_Bay_Mesh", lambda: I.vault_bay(w - 1.0, d - 2.0,
                                                             h - 3.2, p))
    add("Fittings", scene.instance("Vault_Ceiling", vault, (0.0, 0.0, 0.0)))

    positions = [(-w * 0.5 + 0.35, -3.0, math.pi / 2, "West"),
                 (-w * 0.5 + 0.35, 1.4, math.pi / 2, "North"),
                 (w * 0.5 - 0.35, -3.0, -math.pi / 2, "East"),
                 (w * 0.5 - 0.35, 1.4, -math.pi / 2, "South")]
    for x, z, yaw, label in positions:
        add("Fittings", scene.instance(f"Vault_Door_{label}", vault_door,
                                       (x, 0.0, z), yaw))
        spec.lamp(x * 0.72, 1.7, z, energy=2.0, colour=(0.4, 0.72, 1.0), rng=6.0)
    add("Fittings", scene.instance("Sealed_Fifth_Bay", sealed,
                                   (0.0, 0.0, -d * 0.5 + 0.36)))
    add("Furniture", scene.instance("Clerk_Desk", desk, (0.0, 0.0, d * 0.5 - 2.6)))
    for i in range(3):
        add("Furniture", scene.instance(f"Strong_Chest_{i}", chest,
                                        (-2.2 + i * 2.2, 0.0, -1.0), i * 0.3))
    spec.lamp(0.0, h - 1.4, 0.0, energy=3.0, colour=(0.78, 0.84, 0.95), rng=14.0)
    spec.npcs.append({"id": "deposit-official", "actorType": 300, "role": "official",
                      "position": [0.0, 0.0, d * 0.5 - 3.4], "rotationDegrees": 0})

    openings = {"south": [(0.0, 2.0, 0.0, 2.8)]}
    extras = {"spawn": [0.0, 0.0, d * 0.5 - 1.9],
              "collision": ["Clerk_Desk", "Sealed_Fifth_Bay"],
              "landmarks": [{"id": "sealed-fifth-bay",
                             "name": "The plastered fifth bay",
                             "node": "Sealed_Fifth_Bay", "type": "curiosity",
                             "position": [0.0, 0.0, -d * 0.5 + 0.36]}],
              "interactives": [{"id": "storage", "type": "storage",
                                "node": "Clerk_Desk"}]}
    return openings, extras


# ---------------------------------------------------------------------- roster
def roster() -> List[Tuple[Interior, Callable]]:
    """Room specs, with every street-facing value taken from the shared index."""
    warm = (0.30, 0.29, 0.27)
    cool = (0.28, 0.31, 0.35)
    def street(ident: str) -> Tuple[List[float], float]:
        entry = INDEX.by_id(ident)
        return entry["arrival"], entry["yaw"]
    return [
        (Interior("four-gates-lantern-row", "Lantern Row", 26.0, 15.0, 6.6,
                  "Covered market hall; general goods and Nima Vey's counting desk.",
                  "agricultural", *street("four-gates-lantern-row"),
                  materials=BASE_MATERIALS + ["canvas_awning", "thatch_straw"],
                  ambient=warm, ambient_energy=0.93), lantern_row),
        (Interior("four-gates-stormglass-house", "The Stormglass House",
                  13.0, 10.5, 4.6,
                  "Glazier and alchemist; buys stormglass, sells lenses and reagents.",
                  "service", *street("four-gates-stormglass-house"),
                  ambient=cool, ambient_energy=1.02), stormglass_house),
        (Interior("four-gates-mirrorsmith-forge", "Mirrorsmith's Forge",
                  15.0, 12.0, 5.8,
                  "The smithy behind the civic equipment set; repair and reforge.",
                  "service", *street("four-gates-mirrorsmith-forge"),
                  ambient=(0.30, 0.26, 0.24), ambient_energy=0.78),
         mirrorsmith_forge),
        (Interior("four-gates-reedworks", "The Reedworks", 17.0, 12.0, 5.0,
                  "Cordage, canvas and cloth from mirror reed; dye vats and looms.",
                  "agricultural", *street("four-gates-reedworks"),
                  materials=BASE_MATERIALS + ["canvas_awning", "thatch_straw"],
                  ambient=(0.30, 0.32, 0.31), ambient_energy=1.11), reedworks),
        (Interior("four-gates-ferrymans-rest", "The Ferryman's Rest",
                  16.0, 12.0, 4.2,
                  "Inn, tavern and the Crownwater ferry office at the north dock.",
                  "service", *street("four-gates-ferrymans-rest"),
                  ambient=(0.30, 0.27, 0.24), ambient_energy=0.83), ferrymans_rest),
        (Interior("four-gates-deposit-four-keys", "The Deposit of Four Keys",
                  13.0, 13.0, 6.0,
                  "Storage and banking; four keyed vault doors and a plastered fifth.",
                  "civic", *street("four-gates-deposit-four-keys"),
                  ambient=(0.27, 0.29, 0.33), ambient_energy=0.93),
         deposit_of_four_keys),
    ]


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.abspath(os.path.join(here, "..", "..", "maps"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=default_out)
    parser.add_argument("--cache", default=os.environ.get("FOUR_GATES_TEXCACHE", ""))
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    summary = {}
    for spec, layout in roster():
        if args.only and args.only not in spec.id:
            continue
        stats = build_interior(spec, layout, args.out, args.cache or None)
        summary[spec.id] = stats
        print(f"{spec.id:34s} tris={stats['uniqueTriangles']:6d} "
              f"nodes={stats['nodes']:4d} "
              f"glb={stats['bytes'] / 1048576:5.2f} MB "
              f"tex={stats['textureMemoryBytes'] / 1048576:5.1f} MB")
    total_glb = sum(s["bytes"] for s in summary.values())
    print(f"\n{len(summary)} interiors, {total_glb / 1048576:.1f} MB total")


if __name__ == "__main__":
    main()
