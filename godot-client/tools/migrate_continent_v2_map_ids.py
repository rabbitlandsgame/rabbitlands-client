#!/usr/bin/env python3
"""Rename continent-v2 map ids (a successor map inherits a retired map's authored content).

    python godot-client/tools/migrate_continent_v2_map_ids.py --map spindle_hill=jadestair --map tollholm=coilmere --check
    python godot-client/tools/migrate_continent_v2_map_ids.py --map spindle_hill=jadestair --map tollholm=coilmere \
        --unserve ringholm --unserve saltsound

For each old=new pair:
  * moves godot-client/world_authoring/regions/<old> (scene renamed <new>.tscn), eloria-assets/maps/continent-v2/<old>
    (without its published client/ package) and godot-client/src/world/look/regions/<old>.json;
  * deletes the old viewer scene and the published package (both are regenerated: bootstrap and publish);
  * rewrites the old id as a whole word (case-sensitive; "tollholms" or "Tollholm" are other words) in the moved
    files and in the authored sources that name maps or markers (content tables, scenes, music program);
  * records every renamed marker id in _continent_v2/marker-renames-a3.json.
Historical inputs (partition-inputs*, ground-v2, the tollholms source, marker-renames.json) and generated outputs
(plan, catalog, crossings, publication, data/maps, server overlay) are left alone; the build regenerates them.
--unserve also removes a map's published client/ package and its registry row, so its frame may move.
--check lists every change and writes nothing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

CHECKOUT = Path(__file__).resolve().parents[2]
REGIONS = CHECKOUT / "godot-client/world_authoring/regions"
PACKAGES = CHECKOUT / "eloria-assets/maps/continent-v2"
LOOKS = CHECKOUT / "godot-client/src/world/look/regions"
VIEWER = CHECKOUT / "godot-client/world_authoring/continent-v2/viewer"
REGISTRY = CHECKOUT / "godot-client/data/maps/registry.json"
META = PACKAGES / "_continent_v2"
RENAMES = META / "marker-renames-a3.json"
# authored sources outside the moved folders that name maps or markers
SHARED = [META / "content/server-rows.json", META / "content/server-tables.json", META / "content/underground.json",
          META / "content/questlines.txt", CHECKOUT / "eloria-assets/source/audio/music-program.json"]


def word(old: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])")


def tracked(path: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--", str(path.relative_to(CHECKOUT))], cwd=CHECKOUT,
                         capture_output=True, check=True).stdout.decode("utf-8")
    return [CHECKOUT / p for p in out.split("\0") if p]


def is_text(path: Path) -> bool:
    return path.suffix in {".tscn", ".json", ".txt", ".md", ".gd", ".py", ".tres", ".cfg"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", action="append", required=True, help="old=new")
    parser.add_argument("--unserve", action="append", default=[], help="also unserve this (kept) map id")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    pairs = dict(item.split("=", 1) for item in args.map)
    for old, new in pairs.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", new) or (REGIONS / new).exists() or (PACKAGES / new).exists():
            raise SystemExit(f"refusing: {new} is not a fresh map id")
        if not (REGIONS / old).is_dir():
            raise SystemExit(f"refusing: no region folder for {old}")
    plan_moves, plan_deletes, edits, markers = [], [], {}, {}
    for old, new in pairs.items():
        for path in tracked(REGIONS / old):
            name = (new + ".tscn") if path.name == old + ".tscn" else path.name
            plan_moves.append((path, REGIONS / new / path.relative_to(REGIONS / old).parent / name))
        for path in tracked(PACKAGES / old):
            rel = path.relative_to(PACKAGES / old)
            if rel.parts[0] == "client":
                plan_deletes.append(path)
            else:
                plan_moves.append((path, PACKAGES / new / rel))
        if (LOOKS / f"{old}.json").exists():
            plan_moves.append((LOOKS / f"{old}.json", LOOKS / f"{new}.json"))
        if (VIEWER / f"{old}_view.tscn").exists():
            plan_deletes.append(VIEWER / f"{old}_view.tscn")
    for kept in args.unserve:
        plan_deletes += tracked(PACKAGES / kept / "client")
    # text rewrites: moved files, shared sources, and every region scene that names an old id
    targets = {dst: src for src, dst in plan_moves}
    candidates = [(dst, src) for dst, src in targets.items() if is_text(src)]
    candidates += [(p, p) for p in SHARED if p.exists()]
    catalog = json.loads((CHECKOUT / "godot-client/world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))
    candidates += [(REGIONS / e["id"] / f"{e['id']}.tscn",) * 2 for e in catalog["entries"] if e["id"] not in pairs]
    for dst, src in candidates:
        text = src.read_bytes().decode("utf-8")
        new_text = text
        for old, new in pairs.items():
            pattern = word(old)
            if dst.suffix == ".tscn":
                for match in re.finditer(r'\[node name="([^"]+)"', new_text):
                    if pattern.search(match.group(1)):
                        markers[match.group(1)] = pattern.sub(new, match.group(1))
            new_text = pattern.sub(new, new_text)
        if new_text != text:
            edits[dst] = new_text
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    dropped = [m for m in list(pairs) + args.unserve if m in registry["maps"]]
    summary = {"moves": len(plan_moves), "deletes": len(plan_deletes), "rewrittenFiles": sorted(
        str(p.relative_to(CHECKOUT)) for p in edits), "markerRenames": len(markers), "registryRowsDropped": dropped}
    if args.check:
        print(json.dumps(summary, indent=1))
        return 0
    for src, dst in plan_moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(src.relative_to(CHECKOUT)), str(dst.relative_to(CHECKOUT))], cwd=CHECKOUT,
                       check=True, capture_output=True)
    for path in plan_deletes:
        subprocess.run(["git", "rm", "-q", "--", str(path.relative_to(CHECKOUT))], cwd=CHECKOUT, check=True,
                       capture_output=True)
    for path, text in edits.items():
        path.write_bytes(text.encode("utf-8"))
    for old in pairs:
        for leftover in (REGIONS / old, PACKAGES / old):
            if leftover.exists() and not any(leftover.rglob("*")):
                shutil.rmtree(leftover)
    for m in dropped:
        del registry["maps"][m]
    REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    record = json.loads(RENAMES.read_text(encoding="utf-8")) if RENAMES.exists() else {
        "schema": "eloria-continent-v2-marker-renames-v1", "about": "Landfall A3 map-id migration (owner 2026-10-19): "
        "successor maps inherit the retired maps' authored content under fresh ids.", "maps": {}, "markers": {}}
    record["maps"].update(pairs)
    record["markers"].update(dict(sorted(markers.items())))
    RENAMES.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
