#!/usr/bin/env python3
"""Re-encode a region's walk grid heights from the ground it actually draws.

A region's `collision.bin` carries one height byte per half-metre cell, and the
region builders fit that byte's step to the map's whole relief over 63 levels.
On a map with real topography that step is enormous: Mirrorhold's is 3.94 m,
Whitehorn's 2.60, Verdant Stair's 2.07, Amberwood's 1.75. The server allows a
walker two stages between tiles, which is 1.6 m at the coarsest stage it has -
so on those maps *one code of difference is already an unclimbable cliff*, and
an ordinary hillside became a staircase of them. Amberwood came apart into 84
pieces, Mirrorhold into 301, and the crossings out of both stood on ground the
map's own arrival could not walk to.

Nothing about the format required it. The cell byte holds 255 levels and
Sunmane Steppe already uses them at 0.2 m a code, which is why the steppe is
one piece. This rewrites the other regions the same way: the walkable mask is
left exactly as the build decided it, and only the heights are replaced, taken
from the `Terrain_*` and `Walk_*` geometry the client draws and re-encoded over
the full range at the finest step the map's relief allows.

    python _toolkit/refine_walk_heights.py <region> [<region> ...]
    python _toolkit/refine_walk_heights.py --all
    python _toolkit/refine_walk_heights.py --all --check     # report, write nothing

Run it after a region build and before `open_walk_surfaces.py`. What it did is
recorded under `collision.refinedHeights`, and running it twice changes nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import glb_reader as GLB   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GROUND = "Terrain"
WALK = "Walk_"
## The cell byte holds 255 levels above "blocked". Using 63 of them was
## inherited from the Eternal Lands height byte, which nothing in this pipeline
## has written since the ELM formats were removed.
LEVELS = 255
## No finer than the step the server itself keeps, which is what every height
## is re-quantised onto on the way in. Finer would be thrown away.
FINEST_STEP = 0.2


def refine(package: Path, write: bool) -> dict | None:
    grid, manifest = GLB.read_grid(package)
    collision = manifest["collision"]
    encoding = collision.get("heightEncoding")
    if not encoding or not (package / "world.glb").is_file():
        print(f"[heights] {package.name}: no world.glb or no height encoding; skipped")
        return None
    cell = float(collision["cellMetres"])
    origin = GLB.grid_origin(manifest)
    document, body = GLB.load(package / "world.glb")
    shape = grid.shape
    ground_nodes = GLB.named(document, GROUND)
    if not ground_nodes:
        print(f"[heights] {package.name}: no {GROUND}* nodes; skipped")
        return None
    # A package that declares no walk surfaces builds what a player stands on
    # out of ordinary meshes, and this pass would only see the ground *under*
    # them: Sunmane Steppe's bridges are plain geometry, and reading its
    # heights off the terrain dropped every deck into the gully it spans. Its
    # encoding is already the finest there is, so there was nothing to gain.
    if not GLB.named(document, WALK):
        print(f"[heights] {package.name}: no {WALK}* nodes, so its decks are not "
              f"in the geometry this reads; skipped")
        return None
    drawn, top = GLB.rasterise(GLB.triangles(document, body, ground_nodes),
                               shape[1], shape[0], origin[0], origin[1], cell)
    walked, walk_top = GLB.rasterise(GLB.triangles(document, body, GLB.named(document, WALK)),
                                     shape[1], shape[0], origin[0], origin[1], cell)
    # A deck stands over the ground it crosses and is what a walker is on.
    covered = drawn | walked
    height = np.where(walked & (~drawn | (walk_top > top)), walk_top, top)

    walkable = grid != 0
    old_step, old_origin = float(encoding["step"]), float(encoding["origin"])
    old = old_origin + grid.astype(np.float64) * old_step
    # Cells the geometry does not answer for - blackspace, ground under a mesh
    # that is not terrain - keep the height the build gave them.
    metres = np.where(walkable & covered, height, old)
    if not walkable.any():
        print(f"[heights] {package.name}: nothing walkable; skipped")
        return None
    low = float(metres[walkable].min())
    relief = float(metres[walkable].max()) - low
    step = max(FINEST_STEP, relief / (LEVELS - 1))
    new_origin = low - step
    codes = np.clip(np.round((metres - new_origin) / step), 1, LEVELS)
    codes = np.where(walkable, codes, 0).astype(np.uint8)

    changed = int((codes != grid).sum())
    coarse = int((np.abs(np.diff(old, axis=0)) > 1.6).sum() + (np.abs(np.diff(old, axis=1)) > 1.6).sum())
    fine = int((np.abs(np.diff(metres, axis=0)) > 1.6).sum() + (np.abs(np.diff(metres, axis=1)) > 1.6).sum())
    record = {"levels": LEVELS, "step": round(step, 6), "origin": round(new_origin, 4),
              "previousStep": round(old_step, 6), "cellsRestated": changed,
              "cellsFromGeometry": int((walkable & covered).sum()),
              "cellsKept": int((walkable & ~covered).sum())}
    print(f"[heights] {package.name}: step {old_step:.4f} -> {step:.4f} m over {LEVELS} levels; "
          f"{record['cellsFromGeometry']} cells from the geometry, {record['cellsKept']} kept; "
          f"neighbour steps over 1.6 m: {coarse} -> {fine}")
    if not write:
        return record
    collision["heightEncoding"] = dict(encoding, origin=record["origin"], step=record["step"],
                                       range=[1, LEVELS])
    collision["refinedHeights"] = record
    manifest["collision"] = collision
    GLB.write_grid(package, manifest, codes)
    GLB.write_manifest(package / "world.json", manifest)
    return record


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    write = "--check" not in sys.argv
    if "--all" in sys.argv:
        packages = sorted(p.parent for p in ROOT.glob("*/world.json")
                          if (p.parent / "world.glb").is_file() and (p.parent / "collision.bin").is_file())
    elif args:
        packages = [ROOT / name for name in args]
    else:
        print(__doc__)
        return 2
    for package in packages:
        refine(package, write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
