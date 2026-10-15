#!/usr/bin/env python3
"""Rebuild named torso designs and their fit variants, without a full run.

Added 2026-08-29 for Eloria Client.  A whole-library rebuild is ten minutes and
rewrites two hundred files to change one garment, which then has to be pruned
back out of the diff.  When only a design's numbers have moved - and the registry
has not, because its slug and visual id are unchanged - this rebuilds exactly the
pieces named and leaves everything else alone.

    python rebuild_torso_pieces.py --client ../../godot-client \\
        --slug orun_rider_jerkin --slug levy_mail_hauberk
"""
from __future__ import annotations

import argparse
from pathlib import Path

import equipment_authoring as authoring
import torso_designs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--slug", action="append", default=[],
                        help="repeatable; omit to rebuild every design")
    arguments = parser.parse_args()

    # The design table owns finish and construction; register them the way the
    # full builder does so a piece built here is identical to one built there.
    authoring.EQUIPMENT_FINISH.update(
        {slug: finish for slug, _l, _k, finish, _b, _a, _s in torso_designs.DESIGNS})
    authoring.GARMENT_STYLES.update(
        {slug: style for slug, _l, _k, _f, _b, _a, style in torso_designs.DESIGNS})

    races = arguments.client / "assets/actors/native/races"
    equipment = arguments.client / "assets/actors/native/equipment"
    rigs: dict[str, authoring.Rig] = {}

    def rig(name: str) -> authoring.Rig:
        if name not in rigs:
            rigs[name] = authoring.load_rig(races / f"{name}.glb")
        return rigs[name]

    wanted = set(arguments.slug)
    built = 0
    for slug, label, kind, _finish, base, accent, _style in torso_designs.DESIGNS:
        if wanted and slug not in wanted:
            continue
        info = authoring.build_equipment_piece(
            equipment / f"{slug}.glb", rig("luminous_male"), slug, label, kind,
            base, accent)
        print(f"{slug:<32} {info['triangles']:>5} tris")
        built += 1
        for group, spec in authoring.FIT_GROUPS.items():
            if kind not in spec["kinds"]:
                continue
            variant = authoring.variant_slug(slug, group)
            info = authoring.build_equipment_piece(
                equipment / f"{variant}.glb", rig(spec["rig"]), variant, label,
                kind, base, accent)
            print(f"  {variant:<30} {info['triangles']:>5} tris")
            built += 1
    missing = wanted - {slug for slug, *_ in torso_designs.DESIGNS}
    if missing:
        raise SystemExit(f"no such design: {sorted(missing)}")
    print(f"rebuilt {built} files")


if __name__ == "__main__":
    main()
