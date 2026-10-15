#!/usr/bin/env python3
"""Build Sunmane Steppe's cave systems as ONE map with blackspace between them.

Eternal Lands puts a region's interiors on a single map, laid out as islands of
floor with unwalkable void between, rather than one map file per system.
`amethyst_barrens_insides`, `crownwater_insides` and `ssarathi_insides` already
do this in the repository, and Crownwater's and Mirrorhold's were refactored to
it from exactly the position Sunmane is in now: two complete, separately-built
interior packages.

Nothing here re-authors the caves. Both systems keep the specs, the clearance
field, the shell generator, the props, the braziers and the light markers they
already had; `caves.Shell` simply gained a movable sample centre, so a system
can be built somewhere other than the origin, and this module builds both into
one `Builder` and writes one package.

WHY THE BLACKSPACE IS FREE

Nothing draws the void. The cavern floor is what carries the `Terrain_` prefix
the client grounds against, and it only exists where a system's clearance field
is open - so the gap between the two systems has no floor, nothing to stand on
and nothing to render. The gutter is not a wall; it is the absence of cave.

LAYOUT, in metres on the 192 x 192 map

    z=-10  +----------------+          +------------------+
           |  wind caves    |          | crystal hollow   |
           |  60 x 60       |   82 m   | 60 x 60          |
    z=-70  +----------------+          +------------------+
             x=12     x=72              x=138       x=198

Each system keeps its own 60 m sampling square - the extent
`caves.HALF_EXTENT` covers - and they are placed 126 m apart centre to centre.
The shells taper well inside those squares, so the actual empty band between
any geometry of one system and any of the other is **82 m**, measured off the
built GLB rather than assumed. That is far beyond the reach of any brazier (the
widest declared range is under 20 m) and of the grounding ray.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import caves                                          # noqa: E402
import settlement                                     # noqa: E402
from build_sunmane import Builder                             # noqa: E402
import kit                                            # noqa: E402

ASSET_ROOT = HERE.parents[3]
MAP_ROOT = HERE.parents[1] / "interiors"
PACKAGE_ID = "sunmane_insides"
PACKAGE_NAME = "Sunmane Insides"

# The combined map. 192 m square, which is 32 six-metre ELM tiles, and the same
# server-side shape `sunmane_steppe` itself uses.
MAP_SPAN = 192.0
# The client's convention is `godot_z = serverOrigin[1] - server_y`, so with the
# map laid out over world x 0..192 and z -192..0 the origin is (0, 0) and
# `server_y = -z`. Setting it to (0, MAP_SPAN) put every arrival tile at 192 or
# above - off the far edge of a 192-cell map.
SERVER_ORIGIN = (0.0, 0.0)

# section id -> (centre on the combined map, the surface door that reaches it)
SECTIONS = [
    ("sunmane_wind_caves", (43.0, -45.0), "wind-caves-mouth"),
    ("sunmane_crystal_hollow", (169.0, -45.0), "crystal-hollow-adit"),
]


def _offset_spec(spec: dict, centre: tuple) -> dict:
    """A copy of a system's spec with every coordinate moved onto the map.

    The spec is what the clearance field is sampled from, so moving it and the
    sample grid together is the whole of what placing a system takes: every
    field expression in `caves.Shell` is a difference between a sample and a
    chamber, and differences do not care where the pair sits.
    """
    dx, dz = centre
    moved = dict(spec)
    moved["chambers"] = []
    for chamber in spec["chambers"]:
        clone = copy.copy(chamber)
        clone.x = chamber.x + dx
        clone.z = chamber.z + dz
        moved["chambers"].append(clone)
    moved["passages"] = []
    for passage in spec["passages"]:
        clone = copy.copy(passage)
        clone.start = passage.start + [dx, dz]
        clone.end = passage.end + [dx, dz]
        moved["passages"].append(clone)
    moved["water"] = tuple((x + dx, z + dz, r, y) for x, z, r, y in spec["water"])
    moved["camps"] = [(x + dx, z + dz, r) for x, z, r in spec["camps"]]
    return moved


def server_tile(x: float, z: float) -> list[int]:
    return [int(round(x / caves.METRES_PER_TILE + SERVER_ORIGIN[0])),
            int(round(SERVER_ORIGIN[1] - z / caves.METRES_PER_TILE))]


def build(output: Path, texture_scale: float = 1.0) -> dict:
    started = time.time()
    builder = Builder(texture_scale=texture_scale)
    builder.lights = []

    statistics = {"sections": {}}
    sections: list[dict] = []
    shells: list = []
    lowest, highest = 1e9, -1e9

    for identifier, centre, door in SECTIONS:
        # Node names must be unique across the whole map, and both systems
        # number their boulders and stalactites from zero. Without a per-system
        # tag the combined GLB fails the validator with 54 reused names, and the
        # client resolves collision and navigation nodes by name.
        #
        # A suffix, because `navigation.surfaceNodePrefixes` matches the start
        # of the name: tagging the front hid every Terrain_ floor from the
        # client and the map grounded nothing at all.
        builder.name_suffix = "_wind" if "wind" in identifier else "_hollow"
        spec = _offset_spec(caves.SYSTEMS[identifier], centre)
        shell = caves.Shell(spec, centre=centre)
        amethyst = spec["palette"] == "amethyst"

        # Each system keeps its own rock colours: the limestone caves and the
        # amethyst hollow are different stone and always were, and putting them
        # on one map is a layout change, not an art one.
        shell_materials = {
            "floor": builder.material(
                f"cave_floor_{identifier}", "cavern",
                base_color=(0.62, 0.58, 0.54, 1.0) if not amethyst
                else (0.58, 0.52, 0.62, 1.0), roughness=0.93, normal_scale=1.0),
            "roof": builder.material(
                f"cave_roof_{identifier}", "cavern",
                base_color=(0.44, 0.41, 0.39, 1.0) if not amethyst
                else (0.40, 0.35, 0.48, 1.0), roughness=0.95, normal_scale=1.1),
            "wall": builder.material(
                f"cave_wall_{identifier}", "cavern",
                base_color=(0.54, 0.50, 0.46, 1.0) if not amethyst
                else (0.50, 0.44, 0.56, 1.0), roughness=0.94, normal_scale=1.2),
        }

        class _Materials(dict):
            def __missing__(self, key: str) -> int:
                specification = settlement.MATERIALS[key]
                family, color, metallic, roughness, double_sided = specification[:5]
                normal_map = specification[5] if len(specification) > 5 else True
                if len(specification) > 6:
                    normal_map = specification[6]
                emissive = None
                if key == kit.CRYSTAL:
                    emissive = (0.16, 0.07, 0.28)
                    color = (0.50, 0.36, 0.70, 1.0)
                    roughness = 0.24
                value = builder.material(key, family, base_color=color,
                                         metallic=metallic, roughness=roughness,
                                         double_sided=double_sided,
                                         normal_map=normal_map, emissive=emissive)
                self[key] = value
                return value

        section_stats = caves.build_shell(builder, shell, shell_materials)
        section_stats.update(
            caves.populate(builder, shell, shell_materials, _Materials()))
        if spec["water"]:
            water = builder.glb.material(f"cave_pool_{identifier}",
                                         base_color=(0.06, 0.20, 0.24, 1.0),
                                         metallic=0.05, roughness=0.18)
            section_stats["waterTriangles"] = caves.build_water(builder, shell, water)
        statistics["sections"][identifier] = section_stats

        shells.append(shell)
        lowest = min(lowest, float(shell.floor[shell.open].min()))
        highest = max(highest, float(shell.roof[shell.open].max()))

        entrance = spec["chambers"][0]
        arrival = [round(entrance.x, 2),
                   round(shell.floor_at(entrance.x, entrance.z), 2),
                   round(entrance.z, 2)]
        sections.append({
            "id": identifier,
            "name": caves.SYSTEMS[identifier]["name"],
            "class": "cave",
            "spawn": door,
            "centre": [centre[0], centre[1]],
            "arrival": arrival,
            "arrivalServerTile": server_tile(entrance.x, entrance.z),
            "returnMap": spec["returnMap"],
            "returnTile": spec["returnTile"],
            "bounds": {"min": [round(centre[0] - caves.HALF_EXTENT, 1),
                               round(centre[1] - caves.HALF_EXTENT, 1)],
                       "max": [round(centre[0] + caves.HALF_EXTENT, 1),
                               round(centre[1] + caves.HALF_EXTENT, 1)]},
            "chambers": [{
                "id": chamber.id, "label": chamber.label,
                "position": [round(chamber.x, 2),
                             round(shell.floor_at(chamber.x, chamber.z), 2),
                             round(chamber.z, 2)],
                "radius": chamber.radius, "headroom": chamber.headroom,
                "serverTile": server_tile(chamber.x, chamber.z),
            } for chamber in spec["chambers"]],
        })

    builder.name_suffix = ""
    output.mkdir(parents=True, exist_ok=True)
    glb_bytes = builder.glb.write(output / "world.glb")
    statistics.update(builder.glb.statistics())
    statistics["glbBytes"] = glb_bytes
    statistics["buildSeconds"] = round(time.time() - started, 1)

    payload, collision_stats = build_collision(shells)
    (output / "collision.bin").write_bytes(payload)
    statistics["collision"] = collision_stats

    manifest = build_manifest(builder, sections, statistics, lowest, highest,
                              collision_stats)
    (output / "world.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "build-statistics.json").write_text(
        json.dumps(statistics, indent=2) + "\n")
    return statistics


COLLISION_CELL = 0.5
COLLISION_HEIGHT_STEP = 0.2
COLLISION_HEIGHT_ORIGIN = -8.0
# The same agent the manifest's navigation block declares.
AGENT_RADIUS = 0.55
AGENT_HEIGHT = 1.9


def build_collision(shells: list) -> tuple[bytes, dict]:
    """Half-metre walkability grid over the whole map (EWCG version 1).

    The cave systems ship no collision grid of their own - each was one map
    whose whole extent was cave, so walkability was the navigation surface and
    nothing else. A combined map needs one, because the point of the layout is
    that most of the map is *not* cave, and only a grid can say so to the
    server or to the in-engine checker.

    It is built straight from the same clearance field the shells were sampled
    on, at the same half-metre spacing, so a cell is walkable exactly where
    there is cave floor under it and blocked everywhere else. The blackspace is
    not subtracted; it is simply never written.
    """
    import numpy as np

    width = int(round(MAP_SPAN / COLLISION_CELL))
    height = width
    width -= width % 6
    height -= height % 6
    walkable = np.zeros((height, width), dtype=bool)
    surface = np.zeros((height, width), dtype=float)

    for shell in shells:
        # A cell is walkable only where a *complete* floor quad covers it. The
        # floor is built from quads between adjacent samples, so the outermost
        # ring of open samples has clearance but no finished triangle under it.
        # ...and only where a player could actually stand. The navigation block
        # declares agentRadius 0.55 and agentHeight 1.9; the cavern rim tapers
        # to a crawl space well under both, and those cells are cave the ray can
        # graze but nobody can occupy. Marking them walkable is what left the
        # in-engine check reporting a miss - a different single cell each time
        # the mask moved, because it is a continuous rim rather than one hole.
        opened = shell.open & (shell.clearance >= AGENT_RADIUS)             & ((shell.roof - shell.floor) >= AGENT_HEIGHT)
        solid = (opened[:-1, :-1] & opened[1:, :-1]
                 & opened[:-1, 1:] & opened[1:, 1:])
        # Key each quad by its own centre, not by its corner sample. The samples
        # and the collision cells share a half-metre pitch, so a corner-keyed
        # cell claims ground whose quad only *begins* at the tile centre the
        # grounding ray is cast from - and a ray down a shared edge grazes it.
        # One cell of 5,977 came back a miss for exactly that reason.
        for j in range(solid.shape[0]):
            zc = 0.5 * (shell.axis_z[j] + shell.axis_z[j + 1])
            row = int(math.floor((SERVER_ORIGIN[1] - zc) / COLLISION_CELL))
            if row < 0 or row >= height:
                continue
            for i in range(solid.shape[1]):
                if not solid[j, i]:
                    continue
                xc = 0.5 * (shell.axis_x[i] + shell.axis_x[i + 1])
                column = int(math.floor((xc - SERVER_ORIGIN[0]) / COLLISION_CELL))
                if column < 0 or column >= width:
                    continue
                walkable[row, column] = True
                surface[row, column] = float(shell.floor[j, i])

    quantised = np.clip(np.round((surface - COLLISION_HEIGHT_ORIGIN)
                                 / COLLISION_HEIGHT_STEP), 1, 63).astype(np.uint8)
    grid = np.where(walkable, quantised, 0).astype(np.uint8)
    payload = struct.pack("<4sHHII", b"EWCG", 1, 0, width, height) + grid.tobytes()
    stats = {
        "width": width, "height": height, "cellMetres": COLLISION_CELL,
        "originMetres": [float(SERVER_ORIGIN[0]), float(SERVER_ORIGIN[1])],
        "walkableCells": int(walkable.sum()),
        "blockedCells": int((~walkable).sum()),
        "walkableFraction": round(float(walkable.mean()), 4),
        "rowOrder": "server-tile-y (row 0 is the +Z edge)",
        "columnOrder": "server-tile-x (column 0 is the -X edge)",
    }
    return payload, stats


def build_manifest(builder: Builder, sections: list, statistics: dict,
                   lowest: float, highest: float,
                   collision_stats: dict) -> dict:
    image = 1024
    spawn_points = [{
        "id": "default",
        "serverTile": sections[0]["arrivalServerTile"],
        "position": sections[0]["arrival"],
        "facing": [0, 0, -1],
        "groundedBy": "navigation-surface-raycast",
        "section": sections[0]["id"],
        "note": "Arrival for the wind caves mouth, and the map default.",
    }]
    for section in sections:
        spawn_points.append({
            "id": section["spawn"],
            "serverTile": section["arrivalServerTile"],
            "position": section["arrival"],
            "facing": [0, 0, -1],
            "groundedBy": "navigation-surface-raycast",
            "section": section["id"],
            "note": f"Arrival for {section['name']}.",
        })
    portals = [{
        "id": f"exit-{section['spawn']}",
        "kind": "map-transition",
        "position": section["arrival"],
        "serverTile": section["arrivalServerTile"],
        "destinationMap": section["returnMap"],
        "destinationTile": section["returnTile"],
        "section": section["id"],
        "label": f"Back out to the Sunmane Steppe ({section['name']})",
    } for section in sections]

    return {
        "schemaVersion": caves.SCHEMA_VERSION,
        "assetVersion": caves.ASSET_VERSION,
        "asset": {
            "id": PACKAGE_ID,
            "name": PACKAGE_NAME,
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                 "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [0.0, round(lowest - 1.0, 2), -MAP_SPAN],
                       "max": [MAP_SPAN, round(highest + 1.0, 2), 0.0]},
            "regionSpanMeters": MAP_SPAN,
            "interior": True,
            "insides": True,
        },
        # A top-level `bounds` alongside the schema-1.1 `asset.bounds`, because
        # `_toolkit/region_client_check.gd` sizes the server grid from
        # `bounds.serverCells` and cannot check a package that does not publish
        # one. The caves' own schema had no reason to carry it while each system
        # was its own map; a combined map wants the in-engine check.
        "bounds": {
            "serverCells": int(MAP_SPAN),
            "min": [0.0, round(lowest - 1.0, 2), -MAP_SPAN],
            "max": [MAP_SPAN, round(highest + 1.0, 2), 0.0],
        },
        "coordinateTransform": {
            "metresPerTile": caves.METRES_PER_TILE,
            "serverOrigin": list(SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": sections[0]["arrival"][1],
            "invertServerY": True,
            "addressableWorldBounds": {"min": [0.0, -MAP_SPAN],
                                       "max": [MAP_SPAN, 0.0]},
        },
        "sections": sections,
        "spawnPoints": spawn_points,
        "collision": {
            "nodeNames": sorted(set(builder.collision_nodes)),
            "binary": "collision.bin",
            "format": "EWCG-v1",
            "cellMetres": COLLISION_CELL,
            "originMetres": collision_stats["originMetres"],
            "width": collision_stats["width"],
            "height": collision_stats["height"],
            "heightEncoding": {"origin": COLLISION_HEIGHT_ORIGIN,
                               "step": COLLISION_HEIGHT_STEP,
                               "range": [1, 63], "zeroMeansBlocked": True},
            "walkableCells": collision_stats["walkableCells"],
            "walkableFraction": collision_stats["walkableFraction"],
            "note": ("Built from the shells' own clearance field, so a cell is "
                     "walkable exactly where there is cave floor. Everything "
                     "else - the rock around each system and the whole gutter "
                     "between them - is zero, which is what the blackspace is."),
        },
        "navigation": {
            "surfaceNodePrefixes": ["Terrain_"],
            "walkableAreas": ["cave_floor"],
            "navmesh": {"format": "surface-prefix-v1", "agentRadius": 0.55,
                        "agentHeight": 1.9, "maxSlopeDegrees": 42,
                        "polygons": []},
            "note": ("The cavern floor carries the Terrain_ prefix so the "
                     "grounding raycast lands on it; the roof and the wall "
                     "skirt carry structural collision. The ground between the "
                     "two systems has no floor at all - that is the "
                     "blackspace, and it is the absence of cave rather than "
                     "anything drawn."),
        },
        "landmarks": builder.landmarks,
        "interactives": builder.interactives,
        "chambers": [chamber for section in sections
                     for chamber in section["chambers"]],
        "materials": {
            "strategy": "shared-tileable-pbr-families-with-world-scale-uvs",
            "channelPacking": {"orm": "R=occlusion,G=roughness,B=metallic"},
            "embedded": True,
        },
        "environment": {
            # One profile for both systems. They were lit separately before -
            # warm for the limestone, violet for the amethyst - and a single
            # map can only carry one environment block, so this is pitched
            # between them and the per-system light markers carry the
            # difference. That is a genuine compromise of the single-map
            # layout rather than a choice, and it is the same one Crownwater's
            # insides made.
            "profile": "cave-interior",
            "sky": {"topColor": "#05060a", "horizonColor": "#0b0d14",
                    "groundHorizonColor": "#08090d",
                    "groundBottomColor": "#05060a",
                    "curve": 0.4, "sunAngleMax": 2.0, "energy": 0.35},
            "ambient": {"color": "#918aa0", "skyContribution": 0.0,
                        "energy": 0.26},
            "sun": {"rotationDegrees": [-62, 8, 0], "color": "#e0d0d8",
                    "energy": 0.22, "indirectEnergy": 0.40, "shadows": False},
            "fog": {"enabled": True, "color": "#241e26", "density": 0.017,
                    "skyAffect": 0.0, "aerialPerspective": 0.30},
            "tonemap": {"mode": "filmic", "exposure": 1.20, "white": 2.0},
            "note": ("An interior profile: no sky contribution, dense short "
                     "fog and a low fill so the brazier and crystal markers "
                     "carry the lighting."),
        },
        "lighting": {
            "markers": builder.lights,
            "note": ("Braziers and, in the hollow, the crystal faces are the "
                     "light sources; they are emitted as named markers so a "
                     "client lighting pass can bind them without the package "
                     "depending on a glTF light extension."),
        },
        # No minimap block. The two standalone packages each ship a rendered
        # minimap.webp; this combined map does not have one yet, and declaring
        # a file that is not there is worse than declaring nothing.
        "portals": portals,
        "performance": statistics,
        "provenance": {
            "generator": "eloria-assets/maps/nymara-regions/sunmane_steppe/source/insides.py",
            "systems": [section["id"] for section in sections],
            "surfaceMap": "eloria-assets/maps/nymara-regions/sunmane_steppe",
            "note": ("Both systems are built from the same specs, clearance "
                     "field and props they shipped as separate packages; only "
                     "their placement changed."),
        },
        "notes": [
            "Two cave systems on one map with unwalkable blackspace between "
            "them, following amethyst_barrens_insides, crownwater_insides and "
            "ssarathi_insides. The gutter is 66 m of nothing: the cavern floor "
            "only exists where a system's clearance field is open, so there is "
            "no floor between them to stand on and nothing there to render.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=MAP_ROOT / PACKAGE_ID)
    parser.add_argument("--texture-scale", type=float, default=1.0)
    arguments = parser.parse_args()
    statistics = build(arguments.output, arguments.texture_scale)
    collision = statistics["collision"]
    print(f"[{PACKAGE_ID}] {statistics['glbBytes'] / 1e6:.2f} MB, "
          f"{collision['width']}x{collision['height']} cells, "
          f"{collision['walkableCells']} walkable "
          f"({collision['walkableFraction'] * 100:.1f}%), "
          f"{statistics['buildSeconds']}s")
    for identifier, _, _ in SECTIONS:
        section = statistics["sections"][identifier]
        print(f"    {identifier:<24} "
              f"{section.get('shellTriangles', '?')} shell triangles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
