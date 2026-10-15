#!/usr/bin/env python3
"""Every boot against every race that wears it, as it will really be worn.

This is what decides the variant list.  A design is authored once on the
reference rig; the runtime refits it per wearer, and the only races that need a
copy authored on their own body are the ones the refit cannot reach.  Guessing
which those are produces either sixteen variants of everything or skin showing
on somebody, so the question is settled by running the refit offline and
counting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import garment_fit as ff
import footwear_refit as fr

CLIENT = Path(__file__).resolve().parents[2] / "godot-client"
RACES = CLIENT / "assets" / "actors" / "native" / "races"
REGISTRY = CLIENT / "data" / "actors" / "equipment.json"


#: Groups that claim ``boots``; a race in none of them wears the reference.
BOOT_GROUPS = ("feminine_foot", "broad_foot", "saurian")


def _boot_group(groups: dict, race: str) -> str:
    """Which footwear build a race wears.

    ``fitGroups`` lists every group a race belongs to, and most of them are
    claimed by other garment kinds.
    """
    listed = groups.get(race, [])
    if isinstance(listed, str):
        listed = [listed]
    return next((name for name in listed if name in BOOT_GROUPS), "")


def race_paths() -> list[Path]:
    return sorted(RACES.glob("*.glb"))


def worn_report(boot: Path, rig: Path, registry: dict,
                author_rig: str) -> ff.FitReport:
    """Fit of one boot on one body, after the runtime has refitted it."""
    shells: list[ff.Component] = []
    for points, triangles in fr.worn_geometry(boot, rig, registry, author_rig):
        shells.extend(ff.components(points, triangles))
    return ff.check(boot, rig, shells=shells)


def matrix(boots: dict[str, Path], authors: dict[str, str],
           rigs: list[Path] | None = None) -> list[ff.FitReport]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    groups = registry.get("fitGroups", {})
    rigs = rigs or race_paths()
    reports = []
    for name, boot in boots.items():
        author = authors[name]
        group = _boot_group(groups, author)
        for rig in rigs:
            # A race in a fit group wears that group's variant, not this one.
            if _boot_group(groups, rig.stem) != group:
                continue
            reports.append(worn_report(boot, rig, registry, author))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boot", type=Path, nargs="+")
    parser.add_argument("--author", default="luminous_male",
                        help="rig the boot was authored on")
    parser.add_argument("--all-races", action="store_true",
                        help="ignore fit groups and measure against all sixteen")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reports = []
    for boot in args.boot:
        for rig in race_paths():
            if not args.all_races:
                groups = registry.get("fitGroups", {})
                if _boot_group(groups, rig.stem) != _boot_group(
                        groups, args.author):
                    continue
            report = worn_report(boot, rig, registry, args.author)
            reports.append(report)
            print(report.line(), flush=True)
    failed = [report for report in reports if not report.ok]
    print(f"\n{len(reports) - len(failed)}/{len(reports)} pass")
    if args.json:
        args.json.write_text(json.dumps([r.as_dict() for r in reports], indent=2))


if __name__ == "__main__":
    main()
