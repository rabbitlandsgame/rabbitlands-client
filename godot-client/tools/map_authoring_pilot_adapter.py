#!/usr/bin/env python3
"""Validate a map-authoring pilot export with the real server pathfinder.

The editor writes the existing EWCG-v2 half-metre collision format.  This
small adapter folds it onto the server's one-metre tile grid, then imports the
server checkout named by ``--server-root`` and runs ``World.find_path``.
It deliberately does not know about the continent composition pipeline.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path
from types import SimpleNamespace


EWCG_HEADER = struct.Struct("<4sHHII")
SERVER_HEIGHT_STEP = 0.2
DEFAULT_CLIMB_UNITS = 2


def read_ewcg(path: Path) -> tuple[int, int, bytes]:
    raw = path.read_bytes()
    if len(raw) < EWCG_HEADER.size:
        raise ValueError(f"short EWCG header: {path}")
    magic, version, reserved, width, height = EWCG_HEADER.unpack_from(raw)
    if magic != b"EWCG" or version != 2 or reserved != 0:
        raise ValueError(f"expected EWCG-v2 collision: {path}")
    end = EWCG_HEADER.size + width * height
    if end != len(raw):
        raise ValueError(
            f"EWCG payload is {len(raw) - EWCG_HEADER.size} bytes; "
            f"expected {width * height}")
    return width, height, raw[EWCG_HEADER.size:end]


def fold_for_server(width: int, height: int, authored: bytes,
                    height_origin: float, height_step: float
                    ) -> tuple[int, int, bytes]:
    """Conservatively fold four half-metre samples into one server tile."""
    if width % 2 or height % 2:
        raise ValueError("half-metre EWCG dimensions must both be even")
    server_width, server_height = width // 2, height // 2
    folded: list[int | None] = []
    for y in range(server_height):
        for x in range(server_width):
            samples = (
                authored[(2 * y) * width + 2 * x],
                authored[(2 * y) * width + 2 * x + 1],
                authored[(2 * y + 1) * width + 2 * x],
                authored[(2 * y + 1) * width + 2 * x + 1],
            )
            folded.append(None if 0 in samples else max(samples))

    walkable_metres = [height_origin + value * height_step
                       for value in folded if value is not None]
    if not walkable_metres:
        raise ValueError("export has no walkable server tiles")
    floor = min(walkable_metres)
    server = bytearray()
    for value in folded:
        if value is None:
            server.append(0)
            continue
        metres = height_origin + value * height_step
        encoded = round((metres - floor) / SERVER_HEIGHT_STEP) + 1
        if not 1 <= encoded <= 63:
            raise ValueError(
                "exported relief cannot fit the server's six-bit height field")
        server.append(encoded)
    return server_width, server_height, bytes(server)


def _point(value: object, name: str) -> tuple[int, int]:
    if (not isinstance(value, list) or len(value) != 2
            or not all(isinstance(part, int) for part in value)):
        raise ValueError(f"validation.{name} must be [integer x, integer y]")
    return value[0], value[1]


def load_server_world(server_root: Path, width: int, height: int,
                      heights: bytes, climb_units: int):
    server_root = server_root.resolve()
    if not (server_root / "eloria" / "collision.py").is_file():
        raise ValueError(f"not an Eloria server checkout: {server_root}")
    sys.path.insert(0, str(server_root))
    try:
        import eloria.collision as collision_module
        import eloria.world as world_module
    finally:
        sys.path.pop(0)
    for module in (collision_module, world_module):
        try:
            Path(module.__file__).resolve().relative_to(server_root)
        except ValueError as exc:
            raise RuntimeError(
                f"loaded {module.__name__} from outside --server-root: "
                f"{module.__file__}") from exc

    world = world_module.World.__new__(world_module.World)
    world.collision_maps = {
        "map_authoring_pilot": collision_module.with_step_mask(
            collision_module.CollisionMap(width, height, heights), climb_units)
    }
    world._footprint_collision = {}
    world.settings = SimpleNamespace(max_walk_height_change=climb_units)
    return world


def validate_export(manifest_path: Path, server_root: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collision = manifest.get("collision")
    if not isinstance(collision, dict):
        raise ValueError("manifest collision object is required")
    if collision.get("gridAlignment") != "tile-centres-v1":
        raise ValueError("collision.gridAlignment must be tile-centres-v1")
    if float(collision.get("cellSize", 0.0)) != 0.5:
        raise ValueError("collision.cellSize must be 0.5 metres")
    encoding = collision.get("heightEncoding")
    if not isinstance(encoding, dict):
        raise ValueError("collision.heightEncoding is required")
    height_origin = float(encoding["origin"])
    height_step = float(encoding["step"])
    if not math.isfinite(height_origin):
        raise ValueError("collision.heightEncoding.origin must be finite")
    if not math.isfinite(height_step) or height_step <= 0.0:
        raise ValueError("collision.heightEncoding.step must be positive and finite")
    binary_name = collision.get("binary", "collision.bin")
    if not isinstance(binary_name, str) or Path(binary_name).is_absolute():
        raise ValueError("collision.binary must be a relative path")
    binary_path = (manifest_path.parent / binary_name).resolve()
    try:
        binary_path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("collision.binary escapes the export directory") from exc

    width, height, authored = read_ewcg(binary_path)
    server_width, server_height, heights = fold_for_server(
        width, height, authored, height_origin, height_step)
    transform = manifest.get("coordinateTransform", {})
    fixed_transform = {
        "metresPerTile": 1.0,
        "serverOrigin": [0, 0],
        "origin": [-server_width * 0.5, 0.0, server_height * 0.5],
        "invertServerY": True,
    }
    for name, expected in fixed_transform.items():
        if transform.get(name) != expected:
            raise ValueError(
                f"coordinateTransform.{name} must be {expected!r} for the pilot")
    declared = transform.get("serverCells")
    if declared not in ([server_width, server_height], server_width):
        raise ValueError(
            f"coordinateTransform.serverCells must describe "
            f"{server_width}x{server_height}")

    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("manifest validation probes are required")
    route_names = ("spawn", "roadWaypoint", "bridgeEntry", "bridgeDeck",
                   "bridgeExit", "entrance")
    route = [_point(validation.get(name), name) for name in route_names]
    if len(set(route)) != len(route):
        raise ValueError("validation route probes must identify distinct server tiles")
    blocked_names = ("waterProbe", "solidProbe", "besideBridgeProbe")
    blocked = {name: _point(validation.get(name), name) for name in blocked_names}
    if set(blocked.values()) & set(route):
        raise ValueError("blocked probes must not overlap the validation route")
    climb_units = int(validation.get("maxWalkHeightChange", DEFAULT_CLIMB_UNITS))
    if not 0 <= climb_units <= 63:
        raise ValueError("validation.maxWalkHeightChange must be 0..63")

    world = load_server_world(
        server_root, server_width, server_height, heights, climb_units)
    map_id = "map_authoring_pilot"
    for name, point in zip(route_names, route):
        if not world.is_walkable(map_id, *point):
            raise AssertionError(f"route probe {name} is blocked at {point}")
    segments: list[list[tuple[int, int]]] = []
    for (start_name, start), (end_name, end) in zip(
            zip(route_names, route), zip(route_names[1:], route[1:])):
        path = world.find_path(map_id, start, end, set())
        if not path or path[-1] != end:
            raise AssertionError(
                f"server found no route from {start_name} {start} "
                f"to {end_name} {end}")
        segments.append(path)
    for name, point in blocked.items():
        if world.is_walkable(map_id, *point):
            raise AssertionError(f"blocked probe {name} is walkable at {point}")

    return {
        "serverGrid": [server_width, server_height],
        "route": route,
        "segmentLengths": [len(segment) for segment in segments],
        "blocked": blocked,
        "pathfinder": f"{world.__class__.__module__}.{world.__class__.__name__}.find_path",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--server-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_export(args.manifest.resolve(), args.server_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
