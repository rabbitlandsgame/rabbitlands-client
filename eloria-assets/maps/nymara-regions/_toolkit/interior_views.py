#!/usr/bin/env python3
"""Generate a camera set for an interior from its own manifest.

A region's cameras are authored by hand against the concept board. An
interior's rooms are already described in its manifest - every space carries
its extent, floor and height - so the camera set can be derived instead of
maintained twice and drifting from the geometry.

One eye-level shot per space, standing back inside the room and looking across
it at the far wall, plus a raised establishing shot of the whole plan.

    python3 interior_views.py --package <interior dir> [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EYE = 1.7


def views_for(manifest: dict) -> list[dict]:
    spaces: dict[str, dict] = manifest.get("spaces", {})
    if not spaces:
        raise SystemExit("manifest records no spaces")

    out: list[dict] = []
    lo_x = min(s["x0"] for s in spaces.values())
    hi_x = max(s["x1"] for s in spaces.values())
    lo_z = min(s["z0"] for s in spaces.values())
    hi_z = max(s["z1"] for s in spaces.values())
    hi_y = max(s["floor"] + s["height"] for s in spaces.values())
    cx, cz = (lo_x + hi_x) * 0.5, (lo_z + hi_z) * 0.5
    span = max(hi_x - lo_x, hi_z - lo_z)

    # Establishing shot: high and back, looking down the long axis. Interiors
    # have lids, so this sits above them and is only readable with the ceiling
    # culled - it is here for the plan, not for beauty.
    out.append({
        "id": "00-plan-overview",
        "file": "00-plan-overview.png",
        "space": None,
        "eye": [round(cx, 2), round(hi_y + span * 0.75, 2), round(hi_z + span * 0.55, 2)],
        "target": [round(cx, 2), 0.0, round(cz, 2)],
        "fieldOfViewDegrees": 52,
        "lighting": "day",
    })

    for index, (key, s) in enumerate(sorted(spaces.items()), start=1):
        width = s["x1"] - s["x0"]
        depth = s["z1"] - s["z0"]
        floor = s["floor"]
        # Shoot the diagonal rather than the axis. A room's furniture and its
        # columns sit on the centre line, so an axial shot from the mid-wall
        # tends to put a column through the middle of the frame; the diagonal
        # both misses them and shows two walls instead of one.
        inset_w = max(0.9, width * 0.15)
        inset_d = max(0.9, depth * 0.15)
        flip = index % 2 == 0
        if flip:
            eye = [s["x0"] + inset_w, floor + EYE, s["z0"] + inset_d]
            target = [s["x1"] - inset_w * 0.6, floor + EYE * 0.8,
                      s["z1"] - inset_d * 0.6]
        else:
            eye = [s["x1"] - inset_w, floor + EYE, s["z0"] + inset_d]
            target = [s["x0"] + inset_w * 0.6, floor + EYE * 0.8,
                      s["z1"] - inset_d * 0.6]
        out.append({
            "id": f"{index:02d}-{key.replace('_', '-')}",
            "file": f"{index:02d}-{key.replace('_', '-')}.png",
            "space": key,
            "eye": [round(v, 2) for v in eye],
            "target": [round(v, 2) for v in target],
            "fieldOfViewDegrees": 62 if max(width, depth) < 14 else 55,
            "lighting": "day",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    package = Path(args.package).resolve()
    manifest = json.loads((package / "world.json").read_text())
    views = views_for(manifest)
    out = Path(args.out) if args.out else package / "references" / "captures"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(views, indent=2) + chr(10))
    print(f"[views] {len(views)} cameras -> {out / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
