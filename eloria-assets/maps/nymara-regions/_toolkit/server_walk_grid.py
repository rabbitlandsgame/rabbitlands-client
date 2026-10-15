#!/usr/bin/env python3
"""Write a served map's walk grid in the repository's own EWCG format.

Every map package already ships its walkability as `collision.bin`, an EWCG
grid. What the server needs on top of that is the same field resampled onto
its own tile grid, because a map composed of several interiors on one server
map knows its own layout and nothing downstream can reconstruct it.

That resampled grid used to be written as an Eternal Lands ELM under
`source-elm/`, which meant the client repository shipped Eternal Lands binary
map files purely so the server could read a height field out of them. This
writes the identical field as EWCG instead:

    magic    b"EWCG"
    version  1        - cell size is whatever the reader is told, and for
                        these grids it is one cell per server tile
    width    uint32
    height   uint32
    cells    width * height bytes, one per server tile

A cell byte is the Eloria elevation code: zero means blocked, and any other
value is `code * 0.2 - 2.2` metres. That is the same encoding the ELM height
field carried, so a grid written here holds byte for byte what the ELM held
and the server reads the same numbers it always did.

On the server side these are declared in `tools/collision_sources.py` as

    Source("ewcg", f"nymara-regions/server-collision/<map>.bin",
           GridTransform(cell_tiles=1.0, shift=0.0))

which resamples one authored cell onto one server tile - the identity - and
so returns exactly the array `read_elm_heights` used to return.
"""

from __future__ import annotations

from pathlib import Path
import struct

import numpy as np

MAGIC = b"EWCG"
VERSION = 1
HEADER = struct.Struct("<4sHHII")

# The elevation encoding a cell byte carries, in metres.
METRES_PER_UNIT = 0.2
HEIGHT_ORIGIN = -2.2


def write_walk_grid(path: Path, cells: np.ndarray) -> int:
    """Write `cells` (height, width) of elevation codes. Returns bytes written."""
    if cells.ndim != 2:
        raise ValueError(f"walk grid must be 2D, got {cells.shape}")
    grid = np.ascontiguousarray(cells, dtype=np.uint8)
    height, width = grid.shape
    payload = HEADER.pack(MAGIC, VERSION, 0, width, height) + grid.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return len(payload)


def read_walk_grid(path: Path) -> np.ndarray:
    """Read a grid written by `write_walk_grid`."""
    raw = path.read_bytes()
    magic, version, _, width, height = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError(f"not an EWCG walk grid: {path}")
    if version != VERSION:
        raise ValueError(f"unsupported EWCG version {version}: {path}")
    end = HEADER.size + width * height
    if end > len(raw):
        raise ValueError(f"walk grid lies outside EWCG payload: {path}")
    return np.frombuffer(raw[HEADER.size:end],
                         dtype=np.uint8).reshape(height, width)


def describe(cells: np.ndarray) -> str:
    """One line of walkable/blocked proportions, for a build log."""
    walkable = float((cells > 0).mean())
    return (f"{cells.shape[1]}x{cells.shape[0]} tiles, "
            f"{walkable * 100:.1f}% walkable, "
            f"{(1.0 - walkable) * 100:.1f}% blocked")
