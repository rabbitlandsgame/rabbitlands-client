#!/usr/bin/env python3
"""Rebuild every region's walk grid from its own build script.

`build_collision` is where a region decides what a player may stand on, and it
needs the composed surface - terrain with its bridges, decks and stairs on it -
which only the full region build has. That build imports the offline preview
rasteriser, a C library that is not built on every machine and has nothing to
do with collision, so it is stubbed here; anything that actually reaches into
it raises rather than returning something wrong.

    python eloria-assets/maps/nymara-regions/_toolkit/rebuild_collision.py [--region X]

Writes `collision.bin` and updates the `collision` block of `world.json` for
each region, leaving the GLB alone: this changes what the server refuses to
walk through, not what the client draws.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
import subprocess
import sys
import time
import types
from pathlib import Path

REGIONS = Path(__file__).resolve().parent.parent
BUILDS = {
    "amberwood": "build_amberwood.py",
    "amethyst_barrens": "build_amethyst.py",
    "crownwater": "build_crownwater.py",
    "grey_moors": "build_grey_moors.py",
    "manymouth_delta": "build_manymouth_delta.py",
    "mirrorhold": "build_mirrorhold.py",
    "ssarathi_ruins": "build_ssarathi.py",
    "verdant_stair": "build_verdant_stair.py",
    "westhaven": "build_westhaven.py",
    "whitehorn_range": "build_whitehorn.py",
}


class MissingRasteriser(types.ModuleType):
    """Stands in for the preview rasteriser, which collision never needs."""

    def __getattr__(self, name):
        raise RuntimeError(
            f"the offline preview rasteriser is not built here ({name}); "
            "collision does not need it, so whatever asked for it does")


def load_build(region: str):
    for package in ("amberwood",):
        sys.modules.setdefault(f"{package}.render", MissingRasteriser(f"{package}.render"))
    sys.modules.setdefault("render", MissingRasteriser("render"))
    source = REGIONS / region / "source"
    for path in (REGIONS / "_toolkit", source):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    name = BUILDS[region]
    spec = importlib.util.spec_from_file_location(f"_build_{region}", source / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rebuild(region: str) -> dict:
    module = load_build(region)
    started = time.time()
    build = module.build_region()
    payload, width, height, stats = module.build_collision(build)
    package = REGIONS / region
    (package / "collision.bin").write_bytes(payload)

    manifest_path = package / "world.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collision = manifest.setdefault("collision", {})
    collision["binary"] = "collision.bin"
    collision["format"] = "EWCG-v2"
    collision["width"] = width
    collision["height"] = height
    collision["cellMetres"] = stats["cellMetres"]
    collision["heightEncoding"] = stats["heightEncoding"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    stats["seconds"] = round(time.time() - started, 1)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", action="append", default=None)
    parser.add_argument("--one", default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.one:
        # Each region is built in its own process. They all keep a `region.py`
        # and a `populate.py` beside their build script, so importing a second
        # region into a process that has already imported one hands it the
        # first one's modules under the same names.
        print(json.dumps(rebuild(args.one)))
        return 0
    regions = args.region or list(BUILDS)
    print(f"{'region':20s} {'walkable':>9s} {'steep cut':>10s} {'relief':>9s} {'step':>8s} {'s':>5s}")
    failed = []
    for region in regions:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--one", region],
            capture_output=True, text=True)
        line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        if result.returncode != 0 or not line.startswith("{"):
            failed.append(region)
            detail = (result.stderr.strip().splitlines() or ["no output"])[-1]
            print(f"{region:20s} FAILED  {detail[:60]}")
            continue
        stats = json.loads(line)
        cells = stats["width"] * stats["height"]
        print(f"{region:20s} {stats['walkableFraction'] * 100:8.1f}% "
              f"{stats['steepCells'] / cells * 100:9.1f}% "
              f"{stats['reliefMetres']:8.1f}m "
              f"{stats['heightEncoding']['step']:7.3f}m {stats['seconds']:5.1f}")
    if failed:
        print(f"[fail] {len(failed)} regions did not rebuild: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
