#!/usr/bin/env python3
"""Write a procedural descent's frame package: the map its floors are drawn on at runtime.

The owner asked for truly procedural dungeons on 2026-11-13 ("add support for truly procedural dungeons and
implement"). A procedural descent (a server plan with a `procedural` frame, rabbitlands-server `eloria/descent.py`;
contract in the server handbook's Descent-Runs.md) generates fresh floors for every run. Nothing about them can be
baked: the server sends each floor's layout (descent message 188, `kind: "layout"`) and the client builds it
(godot-client/src/world/descent_floor_builder.gd, styled by data/world/descent-themes.json). What stays fixed is the
frame those floors stand on, which this writes from the server's plan:

  ../<map>/client/world.json   asset, coordinate transform (the frame's `cells` tiles a side), the cave environment,
                               the cutaway convention, `descentFrame`, and one section per floor at the place the
                               server packs it (descent.procedural_origins), so fog, sections and map pictures line up
  ../<map>/client/world.glb    an empty scene (the floors are built under it at runtime)

It draws nothing and bakes nothing; the frame has no collision file (the server walks each run's own floors) and no
pictures (the client draws each floor's). godot-client/data/maps/registry.json carries the same transform, and
data/maps/map-backgrounds.json a `runtime` row for the map (tools/map_background_package.py).

    python -B eloria-assets/maps/continent-v2/_continent_v2/build_descent_frame.py --server ../rabbitlands-server
    python -B .../build_descent_frame.py --server <checkout> --check     # the package is the plan's (exit 1 if not)

--server is a rabbitlands-server checkout holding the descent generator; it is imported read-only (no bytecode).
Until 2026-11-13 The Serpent Deep was a baked pool (build_descent_pool.py, removed then; see git history).
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PLANS = {'serpent_deep': 'config/eloria/descents/serpent_deep.json'}   # in the server checkout
PARENT_REGION = {'serpent_deep': 'suncoil'}
ENVIRONMENT = {"profile": "cave-interior", "backgroundColor": "#000000",
               "ambient": {"color": "#acb3bf", "energy": 0.55, "skyContribution": 0},
               "sun": {"energy": 0.25, "color": "#ffe4c0", "shadows": False}, "fog": {"enabled": False},
               "tonemap": {"mode": "filmic", "exposure": 1.1}}
CUTAWAY = {"hideNodes": [], "walls": [], "facingThreshold": 0.6, "props": {"facingThreshold": 0.5, "radiusMetres": 12},
           "reason": "The shared interior camera-facing wall cutaway convention; each floor's walls are added at runtime"}
HEIGHTS = (-4.0, 8.5)   # the deepest chasm and the tallest face, metres


def _git(server, *args):
    return subprocess.run(['git', '-C', str(server), *args], capture_output=True, text=True, check=True).stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_of(server: Path, dungeon: str):
    server = server.resolve()
    if str(server) not in sys.path:
        sys.path.insert(0, str(server))
    from eloria import descent
    plan = descent.load_plan(server / PLANS[dungeon])
    if descent.layout_mode(plan) != 'procedural':
        raise SystemExit(f'{PLANS[dungeon]} is not a procedural descent')
    return descent, plan


def empty_glb(name: str) -> bytes:
    """A glTF 2.0 binary holding one empty node: the frame's scene root."""
    document = json.dumps({"asset": {"version": "2.0", "generator": "Rabbit Lands descent frame"},
                           "scene": 0, "scenes": [{"name": name, "nodes": [0]}], "nodes": [{"name": name}]},
                          separators=(',', ':')).encode('utf-8')
    document += b' ' * (-len(document) % 4)
    return (struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(document))
            + struct.pack('<II', len(document), 0x4E4F534A) + document)


def frame(server: Path, dungeon: str) -> tuple[dict, bytes]:
    descent, plan = plan_of(server, dungeon)
    settings = descent.procedural_settings(plan)
    cells = settings.cells
    tiles = descent.CELL_TILES
    sections, spawns = [], []
    for depth, ((ox, oy), floor) in enumerate(zip(descent.procedural_origins(plan), plan.floors), start=1):
        width, height = floor.size[0] * tiles, floor.size[1] * tiles
        section = descent.procedural_section(plan, depth)
        name = f"{plan.name}: {'the boss floor' if floor.style == 'boss' else f'floor {depth}'}"
        sections.append({"id": section, "name": name,
                         "bounds": {"min": [ox, cells - (oy + height)], "max": [ox + width, cells - oy]}})
        cx, cy = ox + width // 2, oy + height // 2
        spawns.append({"id": section, "name": name, "section": section, "default": depth == 1,
                       "position": [cx + 0.5, 0.05, cells - cy - 0.5], "serverTile": [cx, cy], "rotationDegrees": 180})
    glb = empty_glb(f"{dungeon}_frame")
    manifest = {
        "schemaVersion": "1.1.0", "assetVersion": "2.0.0",
        "asset": {"id": settings.map_id, "name": plan.name, "glb": "world.glb", "units": "meters",
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"},
                  "origin": [0, 0, 0], "bounds": {"min": [0, HEIGHTS[0], 0], "max": [cells, HEIGHTS[1], cells]},
                  "interiorClass": "insides", "parentRegion": PARENT_REGION[dungeon], "serverCells": cells},
        "coordinateTransform": {"metresPerTile": 1.0, "serverOrigin": [0, cells], "serverCells": [cells, cells],
                                "origin": [0, 0, 0], "walkingHeight": 0.0, "invertServerY": True,
                                "serverStorageVersion": 1, "serverTileMin": [0, 0]},
        "serverCells": [cells, cells],
        "descentFrame": {
            "_about": "A procedural descent's frame: every floor is built at runtime from the server's layout "
                      "(descent_layout_v1) by src/world/descent_floor_builder.gd; nothing is drawn here.",
            "dungeon": plan.id, "cellTiles": tiles, "themes": "res://data/world/descent-themes.json"},
        "spawnPoints": spawns,
        "navigation": {"surfaceNodePrefixes": ["Walk_"], "authority": "server", "defaultSpawn": sections[0]["id"]},
        "collision": {"authority": "server", "nodeNames": [],
                      "_about": "The server walks each run's own floors; the client's walk surfaces are the built "
                                "floors' Walk_ meshes."},
        "environment": ENVIRONMENT,
        "lighting": {"markers": []},
        "cutaway": CUTAWAY,
        "sectioned": True,
        "sections": sections,
        "provenance": {"builder": f"_continent_v2/{Path(__file__).name}",
                       "plan": PLANS[dungeon], "planSha256": sha((server / PLANS[dungeon]).read_bytes()),
                       "server": _git(server, 'rev-parse', '--short', 'HEAD'),
                       "owner": "2026-11-13: add support for truly procedural dungeons and implement"},
    }
    return manifest, glb


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def _comparable(manifest: dict) -> dict:
    data = json.loads(json.dumps(manifest))
    data.get('provenance', {}).pop('server', None)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--server', type=Path, required=True, help='a rabbitlands-server checkout (read only)')
    parser.add_argument('--dungeon', default='serpent_deep', choices=sorted(PLANS))
    parser.add_argument('--check', action='store_true', help='compare the package with the plan; write nothing')
    args = parser.parse_args(argv)
    manifest, glb = frame(args.server, args.dungeon)
    out = HERE.parent / manifest['asset']['id'] / 'client'
    if args.check:
        try:
            on_file = json.loads((out / 'world.json').read_text(encoding='utf-8'))
            same = _comparable(on_file) == _comparable(manifest) and (out / 'world.glb').read_bytes() == glb
        except (OSError, ValueError):
            same = False
        print(json.dumps({'package': out.relative_to(HERE.parents[3]).as_posix(), 'current': same}))
        return 0 if same else 1
    out.mkdir(parents=True, exist_ok=True)
    (out / 'world.glb').write_bytes(glb)
    (out / 'world.json').write_bytes(manifest_bytes(manifest))
    print(json.dumps({'package': out.relative_to(HERE.parents[3]).as_posix(),
                      'sections': [s['id'] for s in manifest['sections']],
                      'cells': manifest['asset']['serverCells']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
