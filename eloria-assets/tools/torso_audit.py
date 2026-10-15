#!/usr/bin/env python3
"""Measure every torso design on every race that wears it, in every pose.

Added 2026-08-29 for Eloria Client.  This is the exhaustive run behind the
summary in ``godot-client/tests/test_torso_coverage.py``, which samples one
design of each construction because the full sweep is minutes rather than
seconds.  Run it when the construction changes, and keep its report as the
evidence for what the set actually measures.

Reports the shoulder separately from the body total throughout.  A torso garment
claims eight hundred-odd vertices and the reported defect was a handful of them
at the deltoid; averaged into a whole-body figure it disappears, which is how it
survived being "fixed" more than once.

    python torso_audit.py --client ../../godot-client --report audit.md
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
import time
from pathlib import Path

import garment_coverage as gf

#: What else the wearer has on when the waist seam is judged.  Every design is
#: measured both ways: a hem that is only long enough because something else is
#: over it is not a hem.
TROUSERS = ("4:0",)


def part_five(registry: dict) -> list[str]:
    """One key per distinct mesh.

    The generic tier is a material ladder over a shared scene - twelve shirt
    ids are one shirt in twelve tints - so measuring every id would measure the
    same geometry twelve times and say nothing new.  The lowest id of each scene
    stands for the rest.
    """
    seen: dict[str, str] = {}
    for key, model in registry["models"].items():
        if not key.startswith("5:") or model.get("attach") != "skinned":
            continue
        scene = str(model["scene"])
        if scene not in seen:
            seen[scene] = key
    return sorted(seen.values(), key=lambda key: int(key.split(":")[1]))


def one(client: Path, key: str, races, clips, dressed: bool) -> dict:
    """Every race and clip for one garment, reduced to its worst readings."""
    registry = json.loads((client / "data/actors/equipment.json").read_text())
    root = client / "assets/actors/native/races"
    library = client / "assets/actors/native/shared/Universal_Animation_Library.glb"
    worst_body = worst_shoulder = None
    checked = shoulder_checked = shells = closed = 0
    for race in races:
        scene, author = gf.resolve(registry, key, race)
        garment = client / scene.removeprefix("res://")
        also = gf.layers(client, registry, TROUSERS if dressed else (), race)
        for clip, moment in clips:
            result = gf.measure(garment, root / f"{race}.glb", registry,
                                author_rig=author, clip=clip,
                                library=library, time=moment, also=also)
            checked = max(checked, result.checked)
            shoulder_checked = max(shoulder_checked, result.shoulder_checked)
            shells, closed = result.shells, result.closed_shells
            if worst_body is None or result.exposed > worst_body.exposed:
                worst_body = result
            if (worst_shoulder is None
                    or result.shoulder_exposed > worst_shoulder.shoulder_exposed):
                worst_shoulder = result
    return {
        "name": registry["models"][key].get("name", key),
        "checked": checked, "shoulderChecked": shoulder_checked,
        "exposed": worst_body.exposed, "at": f"{worst_body.rig}/{worst_body.clip}",
        "shoulderExposed": worst_shoulder.shoulder_exposed,
        "shoulderAt": f"{worst_shoulder.rig}/{worst_shoulder.clip}",
        "shells": shells, "closedShells": closed,
    }


def audit(client: Path, keys, races, clips, dressed: bool, workers: int = 0) -> dict:
    """Every garment, in parallel.

    One garment against sixteen races in seven clips is about a minute; eighty
    of them twice over is a working day serially and twenty minutes spread
    across the cores that are sitting there anyway.  Each worker is handed one
    garment and reads its own copy of the registry, so nothing is shared and
    there is nothing to synchronise.
    """
    if workers == 1:
        return {key: one(client, key, races, clips, dressed) for key in keys}
    out: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers or None) as pool:
        pending = {pool.submit(one, client, key, races, clips, dressed): key
                   for key in keys}
        for future in as_completed(pending):
            key = pending[future]
            out[key] = future.result()
            row = out[key]
            print(f"  {key:<8} {row['exposed']:>3}/{row['checked']:<5} skin   "
                  f"{row['shoulderExposed']:>3}/{row['shoulderChecked']:<5} shoulder  "
                  f"{row['at']}", flush=True)
    return {key: out[key] for key in keys if key in out}


def markdown(dressed: dict, bare: dict) -> str:
    lines = ["| visual | design | skin | shoulder | worst | shells |",
             "|---|---|---|---|---|---|"]
    for key, row in dressed.items():
        loose = bare.get(key, row)
        worst = max(row["exposed"], loose["exposed"])
        shoulder = max(row["shoulderExposed"], loose["shoulderExposed"])
        lines.append(
            f"| `{key}` | {row['name']} | {worst}/{row['checked']} | "
            f"{shoulder}/{row['shoulderChecked']} | "
            f"{row['at'] if worst else '-'} | "
            f"{row['closedShells']}/{row['shells']} |")
    body = sum(max(row['exposed'], bare.get(key, row)['exposed'])
               for key, row in dressed.items())
    shoulder = sum(max(row['shoulderExposed'], bare.get(key, row)['shoulderExposed'])
                   for key, row in dressed.items())
    claimed = sum(row["checked"] for row in dressed.values())
    claimed_shoulder = sum(row["shoulderChecked"] for row in dressed.values())
    lines += ["",
              f"**Totals, worst pose per design, worse of dressed and bare-legged:** "
              f"{body}/{claimed} body vertices, "
              f"**{shoulder}/{claimed_shoulder} at the shoulder**."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--only", help="comma-separated visual keys")
    parser.add_argument("--bind-only", action="store_true")
    parser.add_argument("--workers", type=int, default=0,
                        help="0 for one per core, 1 to run in this process")
    arguments = parser.parse_args()

    registry = json.loads(
        (arguments.client / "data/actors/equipment.json").read_text())
    keys = (arguments.only.split(",") if arguments.only
            else part_five(registry))
    races = sorted(path.stem for path in
                   (arguments.client / "assets/actors/native/races").glob("*.glb"))
    clips = (("bind", 0.0),) if arguments.bind_only else gf.POSE_CLIPS

    started = time.time()
    print(f"auditing {len(keys)} torso entries over {len(races)} races "
          f"and {len(clips)} clips, with trousers")
    dressed = audit(arguments.client, keys, races, clips, True,
                    arguments.workers)
    print("and again on bare legs")
    bare = audit(arguments.client, keys, races, clips, False,
                 arguments.workers)
    print(f"done in {time.time() - started:.0f}s")

    report = markdown(dressed, bare)
    print("\n" + report)
    if arguments.report:
        arguments.report.write_text(report, encoding="utf-8")
    if arguments.json:
        arguments.json.write_text(json.dumps(
            {"dressed": dressed, "bareLegs": bare}, indent=1), encoding="utf-8")
    worst = max(max(row["exposed"] for row in dressed.values()),
                max(row["exposed"] for row in bare.values()))
    raise SystemExit(0 if worst <= 4 else 1)


if __name__ == "__main__":
    sys.exit(main())
