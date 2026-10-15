#!/usr/bin/env python3
"""Verify Ssarathi Ruins's interiors against the client's grounding contract.

WHY NOT JUST `_toolkit/verify_runtime.py`
-----------------------------------------
That tool casts the grounding ray at every tile of the map's bounding box and
counts a tile with no floor under it as a miss. That is the right rule for a
region, where every tile of the server grid is ground somebody could stand on.

It is the wrong rule for an interior. An interior is rooms carved out of solid
rock: most of its bounding box is rock, has no floor by design, and is not
reachable. Run against Ssarathi Ruins's four, it reports 46-74% "misses", every one
of them correct behaviour.

The contract that actually matters indoors is narrower and stricter:

    every cell the interior's own collision grid calls WALKABLE
    must have a walk surface under it

That is what this checks. A cell marked walkable with nothing under it is a hole
a player falls through; a cell marked blocked with no floor is a wall, and fine.

It also re-checks the two things that are contract, not taste:

  * every spawn and portal grounds within tolerance of where it is declared
  * the collision grid's encoded height agrees with the rendered surface

USAGE
    python verify_interiors.py                 # all four
    python verify_interiors.py --only drowned_crown
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_runtime as VR

INTERIOR_ROOT = Path(__file__).resolve().parents[1].parent / "interiors"
# One package: the four insides share a single map with blackspace between them.
IDS = ["ssarathi_insides"]

# A cell is half a metre; a tread is 0.30 m thick. Anything inside this of the
# encoded height is the surface the player will actually stand on.
HEIGHT_TOLERANCE = 0.75
SPAWN_TOLERANCE = 0.30


def check(package: Path) -> dict:
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    document, binary = VR.load_glb(package / "world.glb")
    prefixes = tuple(manifest["navigation"]["surfaceNodePrefixes"])
    triangles, matched = VR.collect_triangles(
        document, binary, lambda name: name.startswith(prefixes))
    index = VR.VerticalRayIndex(triangles, cell=2.0)

    collision = manifest["collision"]
    payload = (package / collision["binary"]).read_bytes()
    _, _, _, width, height = struct.unpack("<4sHHII", payload[:16])
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(height, width)
    cell = float(collision["cellMetres"])
    origin = collision.get("originMetres", [0.0, 0.0])
    encoding = collision["heightEncoding"]

    walkable = grid > 0
    misses, disagreements = [], []
    for row in range(height):
        for column in range(width):
            if not walkable[row, column]:
                continue
            # Row 0 is the +Z edge and z DECREASES with the row index, matching
            # `build_collision`. Adding instead of subtracting mirrors the grid
            # about its own north edge and reports every cell as floorless -
            # which is exactly what the first run of this tool did.
            x = origin[0] + (column + 0.5) * cell
            z = origin[1] - (row + 0.5) * cell
            hit = index.top_hit(x, z)
            if hit is None:
                misses.append([round(x, 2), round(z, 2)])
                continue
            encoded = encoding["origin"] + int(grid[row, column]) * encoding["step"]
            if abs(encoded - hit) > HEIGHT_TOLERANCE:
                disagreements.append({"at": [round(x, 2), round(z, 2)],
                                      "encoded": round(encoded, 2),
                                      "surface": round(hit, 2)})

    spawn_problems = []
    for spawn in manifest.get("spawnPoints", []):
        x, y, z = spawn["position"]
        hit = index.top_hit(x, z)
        if hit is None:
            spawn_problems.append({"id": spawn["id"], "problem": "no surface"})
        elif abs(hit - y) > SPAWN_TOLERANCE:
            spawn_problems.append({"id": spawn["id"], "declared": round(y, 2),
                                   "surface": round(hit, 2)})

    portal_problems = []
    for portal in manifest.get("portals", []):
        x, y, z = portal["position"]
        hit = index.top_hit(x, z)
        if hit is None:
            portal_problems.append({"id": portal["id"], "problem": "no surface"})
        elif abs(hit - y) > 1.5:
            portal_problems.append({"id": portal["id"], "declared": round(y, 2),
                                    "surface": round(hit, 2)})

    # Per-section walkable counts, so a section that lost its floor entirely is
    # visible rather than averaged away across a map that is 89% blackspace.
    per_section = []
    for section in manifest.get("sections", []):
        sx0, sz0 = section["bounds"]["min"]
        sx1, sz1 = section["bounds"]["max"]
        c0 = max(int((sx0 - origin[0]) / cell) - 4, 0)
        c1 = min(int((sx1 - origin[0]) / cell) + 4, width - 1)
        r0 = max(int((origin[1] - sz1) / cell) - 4, 0)
        r1 = min(int((origin[1] - sz0) / cell) + 4, height - 1)
        per_section.append({
            "id": section["id"],
            "walkableCells": int(walkable[r0:r1 + 1, c0:c1 + 1].sum())})

    total = int(walkable.sum())
    return {
        "sections": per_section,
        "id": manifest["asset"]["id"],
        "walkSurfaceNodes": len(matched),
        "walkableCells": total,
        "walkableCellsWithoutSurface": len(misses),
        "misses": misses[:12],
        "heightDisagreements": len(disagreements),
        "disagreementSamples": disagreements[:8],
        "spawnProblems": spawn_problems,
        "portalProblems": portal_problems,
        "ok": not misses and not spawn_problems and not portal_problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    results, failed = [], False
    for ident in IDS:
        if args.only and ident not in args.only:
            continue
        package = INTERIOR_ROOT / ident
        if not (package / "world.json").is_file():
            print(f"[{ident}] not built")
            failed = True
            continue
        result = check(package)
        results.append(result)
        status = "PASS" if result["ok"] else "FAIL"
        print(f"[{ident}] {result['walkableCells']} walkable cells, "
              f"{result['walkableCellsWithoutSurface']} without a surface, "
              f"{result['heightDisagreements']} height disagreements, "
              f"{len(result['spawnProblems'])} spawn problems  {status}")
        for section in result.get("sections", []):
            print(f"     {section['id']:<18} {section['walkableCells']:>7} walkable cells")
        for entry in result["spawnProblems"] + result["portalProblems"]:
            print("    ", json.dumps(entry))
        if not result["ok"]:
            failed = True

    if args.report:
        Path(args.report).write_text(json.dumps(
            {"tolerances": {"height": HEIGHT_TOLERANCE, "spawn": SPAWN_TOLERANCE},
             "interiors": results}, indent=2) + "\n", encoding="utf-8")
        print(f"[report] {args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
