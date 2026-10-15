#!/usr/bin/env python3
"""Write the server-side walk grid for an exterior region.

The region is authored at one metre per server tile, and the runtime GLB and
this grid are built from the same terrain, so the two cannot disagree about
where the ground is or whether you can stand on it.

Cell bytes carry the elevation encoding the rest of the project uses:

    elevation_metres = cell * COLLISION_HEIGHT_STEP + COLLISION_HEIGHT_ORIGIN

and zero means blocked.

This used to write an Eternal Lands ELM under `source-elm/`. It writes the same
field as EWCG under `server-collision/` now; see `server_walk_grid.py`.

The exteriors are not read from here by the server, which prefers each region's
own half-metre `collision.bin` and resamples that itself. This stays because it
is how a region states its walk grid on the server's own tile spacing, which is
what a regression check and a hand inspection both want to look at.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import regionpaths
from server_walk_grid import describe, write_walk_grid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    package = regionpaths.package_root(args.package)
    out = (Path(args.out) if args.out else
           regionpaths.REGIONS / "server-collision" / f"{package.name}.bin")

    build_module = regionpaths.load_region_build(package)
    origin = build_module.COLLISION_HEIGHT_ORIGIN
    step_metres = build_module.COLLISION_HEIGHT_STEP

    build = build_module.build_region()
    payload, width, height, _stats = build_module.build_collision(build)
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)

    # The collision grid is half-metre; the server's movement grid is one cell
    # per tile, which is the spacing this writes.
    cells = regionpaths.load_region_plan(package).SERVER_CELLS
    stride = max(1, width // cells)
    heights = grid[::stride, ::stride][:cells, :cells]
    if heights.shape != (cells, cells):
        padded = np.zeros((cells, cells), dtype=np.uint8)
        padded[:heights.shape[0], :heights.shape[1]] = heights
        heights = padded

    size = write_walk_grid(out, heights)
    print(f"[walk] {out} {size} bytes, {describe(heights)}")
    print(f"[walk] elevation = cell * {step_metres} {origin:+.1f} m, "
          f"zero means blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
