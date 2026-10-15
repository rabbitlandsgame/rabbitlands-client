"""Spatial material batches for local lighting and culling in long interiors."""
from __future__ import annotations

from collections import defaultdict
import numpy as np

from . import mesh as M
from .stonework import MeshGroup


def sections(group, ident, cell_metres=12.0, axis=2):
    """Split triangle ownership into ordered bands, retaining navigation/lids.

    Godot Compatibility chooses a small set of point lights per mesh. One
    material batch spanning an entire dungeon therefore loses the lamps near
    most rooms. Local batches bound that choice without changing a triangle.
    """
    bands = defaultdict(MeshGroup)
    for bucket in ("parts", "walk_parts", "overhead_parts"):
        for piece in getattr(group, bucket):
            faces = piece.indices.reshape(-1, 3)
            if not len(faces):
                continue
            cells = np.floor(piece.positions[faces, axis].mean(axis=1) / cell_metres).astype(int)
            for cell in sorted(set(cells)):
                used, inverse = np.unique(faces[cells == cell], return_inverse=True)
                part = M.Mesh(positions=piece.positions[used].copy(),
                              normals=piece.normals[used].copy(),
                              uvs=piece.uvs[used].copy(), indices=inverse.reshape(-1),
                              colors=piece.colors[used].copy() if piece.colors is not None else None,
                              material=piece.material)
                getattr(bands[int(cell)], bucket).append(part)
    return [(f"{ident}_band_{cell:+04d}", bands[cell]) for cell in sorted(bands)]
