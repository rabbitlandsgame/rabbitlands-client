#!/usr/bin/env python3
"""Block the ground a solid landmark stands on in a region's walk grid.

The region builders block a placed structure with a circle inscribed in its
bounds. That is right for a tree or a boulder and wrong for a hall: the
circle leaves the ends of a long building and the corners of a square one
walkable, so a player could walk into the customs hall's east end and an
NPC posted at a tower's door stood inside the tower. This reads the
package's own GLB, measures each landmark of a solid kind (`building`,
`tower`) by the bounds of the parts of it that stand on the ground - roofs
overhang and float above - and blocks that box, plus a margin, in the
package's `collision.bin`. What it stamped is recorded under
`collision.stampedLandmarks` in `world.json`, so running it twice changes
nothing, and a server sync that follows sees the box.

    python _toolkit/stamp_solid_landmarks.py <region> [<region> ...]
    python _toolkit/stamp_solid_landmarks.py --all

Run it after a region build and after `open_walk_surfaces.py`: the build
writes `collision.bin` from the circles again, and the opener would open a
hall's own floor. Then `tools/sync_authored_collision.py` on the server
side, which opens each door tile and cuts its approach, so a building's
door stays a door.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import glb_reader as GLB   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOLID = ("building", "tower")
MARGIN = 0.5            # metres round the walls that nobody should stand on either
GROUNDED = 1.2          # a part whose lowest point is within this of the lowest stands on the ground


def ground_boxes(document: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Node name -> world-space (low, high) of the parts of a landmark that
    stand on the ground, from the accessors' own bounds."""
    nodes = document["nodes"]
    matrices, _ = GLB.hierarchy(document)

    def subtree(index: int):
        yield index
        for child in nodes[index].get("children", ()):
            yield from subtree(child)

    out = {}
    for index, node in enumerate(nodes):
        if not node.get("name", "").startswith("Landmark_"):
            continue
        parts = []
        for descendant in subtree(index):
            mesh = nodes[descendant].get("mesh")
            if mesh is None:
                continue
            matrix = matrices[descendant]
            for primitive in document["meshes"][mesh]["primitives"]:
                accessor = document["accessors"][primitive["attributes"]["POSITION"]]
                low = np.array(accessor["min"], dtype=float)
                high = np.array(accessor["max"], dtype=float)
                corners = np.array([[x, y, z, 1.0] for x in (low[0], high[0])
                                    for y in (low[1], high[1]) for z in (low[2], high[2])])
                points = (matrix @ corners.T).T[:, :3]
                parts.append((points.min(axis=0), points.max(axis=0)))
        if not parts:
            continue
        floor = min(low[1] for low, _ in parts)
        grounded = [(low, high) for low, high in parts if low[1] <= floor + GROUNDED]
        out[node["name"]] = (np.min([low for low, _ in grounded], axis=0),
                             np.max([high for _, high in grounded], axis=0))
    return out


def stamp(region: Path) -> int:
    if not (region / "world.glb").is_file() or not (region / "world.json").is_file():
        print(f"[stamp] {region.name}: no world.glb or world.json; skipped")
        return 0
    grid, manifest = GLB.read_grid(region)
    grid = grid.copy()
    collision = manifest["collision"]
    if float(collision.get("cellMetres", 0.5)) != 0.5:
        print(f"[stamp] {region.name}: not a half-metre grid; skipped")
        return 0
    cell = float(collision["cellMetres"])
    origin = GLB.grid_origin(manifest)
    previous = {entry["id"]: entry for entry in collision.get("stampedLandmarks", ())}
    boxes = ground_boxes(GLB.load(region / "world.glb")[0])
    height, width = grid.shape
    stamped = []
    blocked = 0
    for landmark in manifest.get("landmarks", ()):
        kind = landmark.get("type", landmark.get("kind"))
        node = landmark.get("node", "")
        if kind not in SOLID or node not in boxes:
            continue
        low, high = boxes[node]
        # cell (cx, cz) is centred on (origin.x + (cx+.5)*cell, origin.z - (cz+.5)*cell)
        c0 = max(int(np.ceil((low[0] - MARGIN - origin[0]) / cell - 0.5)), 0)
        c1 = min(int(np.floor((high[0] + MARGIN - origin[0]) / cell - 0.5)), width - 1)
        r0 = max(int(np.ceil((origin[1] - high[2] - MARGIN) / cell - 0.5)), 0)
        r1 = min(int(np.floor((origin[1] - low[2] + MARGIN) / cell - 0.5)), height - 1)
        if c1 < c0 or r1 < r0:
            continue
        patch = grid[r0:r1 + 1, c0:c1 + 1]
        newly = int((patch != 0).sum())
        patch[:] = 0
        blocked += newly
        # a second run finds the box already blocked; keep what the first took
        newly = max(newly, int(previous.get(landmark["id"], {}).get("cellsBlocked", 0)))
        stamped.append({"id": landmark["id"], "node": node, "type": kind,
                        "box": [round(float(low[0]), 2), round(float(low[2]), 2),
                                round(float(high[0]), 2), round(float(high[2]), 2)],
                        "marginMetres": MARGIN, "cellsBlocked": newly})
        print(f"[stamp] {region.name}: {landmark['id']} ({kind}) x {low[0]:.1f}..{high[0]:.1f} "
              f"z {low[2]:.1f}..{high[2]:.1f}: {newly} cells were walkable")
    if not stamped:
        print(f"[stamp] {region.name}: no solid landmarks")
        return 0
    walkable = int((grid != 0).sum())
    collision["walkableCells"] = walkable
    collision["walkableFraction"] = round(walkable / grid.size, 4)
    collision["stampedLandmarks"] = stamped
    manifest["collision"] = collision
    GLB.write_grid(region, manifest, grid)
    GLB.write_manifest(region / "world.json", manifest)
    print(f"[stamp] {region.name}: {len(stamped)} landmarks, {blocked} cells blocked; "
          f"{walkable} walkable cells remain")
    return blocked


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv:
        regions = sorted(p.parent for p in ROOT.glob("*/world.json")
                         if (p.parent / "world.glb").is_file())
    elif args:
        regions = [ROOT / name for name in args]
    else:
        print(__doc__)
        return 2
    for region in regions:
        stamp(region)
    return 0


if __name__ == "__main__":
    sys.exit(main())
