#!/usr/bin/env python3
"""Write the server-side walk grid for a region's composed insides map.

Several interiors share one server map with blackspace between them, so the
server needs one collision grid for the lot, and only the package that composed
them knows that layout. This reads the package's own `collision.bin` - the
half-metre grid the client already agrees with - and resamples it to the
server's one-metre tile grid, so the two cannot drift apart.

Cell bytes follow the elevation encoding the rest of the project uses:

    elevation_metres = cell * 0.2 - 2.2

and zero means blocked, which is what the blackspace between sections is.

This used to write an Eternal Lands ELM under `source-elm/`. It writes the
same field as EWCG under `server-collision/` now; see `server_walk_grid.py`.

Each region called this with its own copy of the script, and the copies drifted:
Westhaven's takes the maximum over each block, and the other seven sample one
cell of it. That is not a cosmetic difference - a stride sample steps over any
wall thinner than the stride, and it once put three of Westhaven's four arrival
tiles on blocked cells - so it is a flag here rather than a silent default, and
every region keeps the behaviour it shipped with until its map is requalified.

The third mode, `footprint`, is the one the gauntlets use and the one a
requalified map should move to. The client draws a server tile centred on an
integer metre, so the ground under a tile is the block of cells *round* that
point, not the block that starts there; `footprint` folds that block the way
the server folds a region's own grid - blocked if any cell under it is, and
standing at the highest - so a creature's tile stops short of the wall beside
it instead of reaching half a metre into it. With `heights="server"` the cell
bytes are also re-expressed in the server's own 0.2 m step: a package fits its
height codes to its own relief (a gauntlet's are 0.1 m), and the server reads
a composed grid's bytes as 0.2 m steps, so passing them through doubled every
riser and shut every stair.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server_walk_grid import describe, write_walk_grid

TILE_SIZE = 6


def resample(grid: np.ndarray, step: int, downsample: str) -> np.ndarray:
    """Fold a half-metre grid onto one-metre cells."""
    if downsample == "max":
        rows = (grid.shape[0] // step) * step
        cols = (grid.shape[1] // step) * step
        return grid[:rows, :cols].reshape(
            rows // step, step, cols // step, step).max(axis=(1, 3))
    if downsample == "stride":
        return grid[::step, ::step]
    if downsample == "footprint":
        # Tile t is centred on cell step*t, so its ground is the block ending
        # there: pad by half a block so that block starts on a block boundary.
        half = step // 2
        padded = np.zeros((grid.shape[0] + half, grid.shape[1] + half), dtype=grid.dtype)
        padded[half:, half:] = grid
        rows = padded.shape[0] // step
        cols = padded.shape[1] // step
        block = padded[:rows * step, :cols * step].reshape(rows, step, cols, step)
        clear = (block != 0).all(axis=(1, 3))
        return np.where(clear, block.max(axis=(1, 3)), 0).astype(np.uint8)
    raise ValueError(f"unknown downsample mode: {downsample}")


SERVER_STEP = 0.2


def server_units(coarse: np.ndarray, encoding: dict | None) -> np.ndarray:
    """Re-express a package's height codes in the server's 0.2 m steps, on the
    package's own lowest walkable cell. Half-up rounding, not banker's: a 0.4 m
    riser is then always two codes, whichever side of a code boundary it starts
    on, and two codes is exactly the climb the server allows."""
    if not encoding or "step" not in encoding or "origin" not in encoding:
        return coarse
    walk = coarse != 0
    if not walk.any():
        return coarse
    metres = float(encoding["origin"]) + coarse.astype(np.float64) * float(encoding["step"])
    # (+1e-6: 1.9 / 0.2 is 9.4999... in floating point, and a riser that rounds down
    # on one tread and up on the next reads as three codes, not two)
    codes = np.floor((metres - metres[walk].min()) / SERVER_STEP + 0.5 + 1e-6) + 1
    return np.where(walk, np.clip(codes, 1, 63), 0).astype(np.uint8)


def export(package: Path, out: Path, tiles: int, downsample: str,
           heights: str = "package") -> np.ndarray:
    """Write the package's walk grid on the server's tile grid. `heights` is
    "package" to pass the cell bytes through as the package encoded them, or
    "server" to re-express them in the server's 0.2 m steps."""
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    collision = manifest["collision"]
    payload = (package / collision["binary"]).read_bytes()
    _, _, _, width, height = struct.unpack("<4sHHII", payload[:16])
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)

    step = int(round(1.0 / collision["cellMetres"]))
    coarse = resample(grid, step, downsample)
    if heights == "server":
        coarse = server_units(coarse, collision.get("heightEncoding"))
    elif heights != "package":
        raise ValueError(f"unknown heights mode: {heights}")

    cells = tiles * TILE_SIZE
    if coarse.shape[0] > cells or coarse.shape[1] > cells:
        raise SystemExit(
            f"insides map is {coarse.shape[1]}x{coarse.shape[0]} cells, which "
            f"does not fit {cells}x{cells}; raise --tiles")
    padded = np.zeros((cells, cells), dtype=np.uint8)
    padded[:coarse.shape[0], :coarse.shape[1]] = coarse

    size = write_walk_grid(out, padded)
    print(f"[walk] {out} {size} bytes, {tiles}x{tiles} tiles")
    print(f"[walk] {describe(padded)} (the blackspace between sections, "
          f"and the rock around each)")
    return padded


def report_arrivals(package: Path, cells: np.ndarray) -> None:
    """The server arrival tile for each door, derived rather than counted.

    The manifest's `serverOrigin` is what the client uses, so the server table
    has to agree with it or a player arrives somewhere else entirely.
    """
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    origin = manifest["coordinateTransform"]["serverOrigin"]
    extent = cells.shape[0]
    print("[walk] server arrival tiles (for eloria-server ARRIVAL_TILES):")
    for spawn in manifest["spawnPoints"]:
        x, _, z = spawn["position"]
        # coordinate_adapter.gd: godot_x = server_x - serverOrigin.x and
        # godot_z = -(server_y - serverOrigin.y), so inverting gives
        # server_x = godot_x + serverOrigin.x. Subtracting it instead put every
        # arrival ten tiles east of where the client puts it, which read as
        # three of the four landing on blackspace.
        tile = (int(round(x + origin[0])), int(round(origin[1] - z)))
        cell = (cells[tile[1], tile[0]]
                if 0 <= tile[1] < extent and 0 <= tile[0] < extent else 0)
        print(f"       {spawn['id']:<24} {tile}  "
              f"{'walkable' if cell else 'BLOCKED'}")


def cli(*, description: str, package: str, out: str, tiles: int,
        downsample: str, arrivals: bool = False) -> int:
    """Run one region's export. Paths are relative to `nymara-regions/`."""
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--package", default=str(root / "interiors" / package))
    ap.add_argument("--out", default=str(root / "server-collision" / f"{out}.bin"))
    ap.add_argument("--tiles", type=int, default=tiles)
    ap.add_argument("--downsample", choices=("max", "stride", "footprint"), default=downsample,
                    help="how a half-metre block becomes one server tile")
    ap.add_argument("--heights", choices=("package", "server"), default="package",
                    help="pass the package's height codes through, or re-express them in 0.2 m steps")
    args = ap.parse_args()

    cells = export(Path(args.package), Path(args.out), args.tiles,
                   args.downsample, heights=args.heights)
    if arrivals:
        report_arrivals(Path(args.package), cells)
    return 0
