#!/usr/bin/env python3
"""Fit one torso prototype and measure it on every race, in every pose.

Added 2026-08-29 for Eloria Client.  Sixty-four designs times sixteen races is a
thousand variants if the variant list is guessed at, so it is measured instead:
a cloth prototype and a rigid one are built here, checked against the whole cast
under every clip a shoulder has to survive, and the races that the runtime refit
genuinely cannot reach are the ones that get an authored variant.  Everyone else
wears the reference piece.

Run it before authoring the set, and again whenever the construction changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import equipment_authoring as ea
import garment_coverage as gf


def build(rig: ea.Rig, path: Path, kind: str, style: ea.Style, label: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    return ea.build_equipment_piece(path, rig, path.stem, label, kind,
                                    (120, 110, 96), (170, 150, 120), style=style)


#: What else the wearer has on.  A torso hem is meant to finish inside these.
WORN_WITH = ("4:0",)


def check(client: Path, garment: Path, races: list[str], author_rig: str,
          clips, dressed: bool = True) -> list[gf.Coverage]:
    registry = json.loads((client / "data/actors/equipment.json").read_text())
    root = client / "assets/actors/native/races"
    library = client / "assets/actors/native/shared/Universal_Animation_Library.glb"
    results = []
    for race in races:
        also = gf.layers(client, registry, WORN_WITH if dressed else (), race)
        for clip, time in clips:
            results.append(gf.measure(garment, root / f"{race}.glb", registry,
                                      author_rig=author_rig, clip=clip,
                                      library=library, time=time, also=also))
    return results


def report(name: str, results: list[gf.Coverage]) -> dict:
    """Per-race worst case, so one bad pose is not averaged away by six good ones."""
    by_race: dict[str, gf.Coverage] = {}
    for result in results:
        worst = by_race.get(result.rig)
        if worst is None or (result.exposed, result.shoulder_exposed) > \
                (worst.exposed, worst.shoulder_exposed):
            by_race[result.rig] = result
    print(f"\n== {name}")
    print(f"{'race':<20} {'skin':>10} {'shoulder':>10}  worst pose   shells")
    for race in sorted(by_race):
        worst = by_race[race]
        print(f"{race:<20} {worst.exposed:>4}/{worst.checked:<5} "
              f"{worst.shoulder_exposed:>4}/{worst.shoulder_checked:<5} "
              f"{worst.clip:<12} {worst.closed_shells}/{worst.shells}")
    failing = sorted(race for race, worst in by_race.items() if worst.exposed)
    print(f"   races needing an authored variant: {failing or 'none'}")
    return {"failing": failing,
            "worst": {race: [worst.exposed, worst.shoulder_exposed, worst.clip]
                      for race, worst in by_race.items()}}


#: The two prototypes the variant list is decided from.  Cloth drapes and can be
#: let out; plate cannot, and the shoulder is exactly where the two diverge.
PROTOTYPES = {
    "cloth": ("shirt", ea.Style(sleeve_end=.34, sleeve_thickness=.013,
                                cap_outboard=.46, cap_swell=1.38)),
    "rigid": ("cuirass", ea.Style(thickness=.017, cap_outboard=.44,
                                  cap_swell=1.62, cap_trim=True,
                                  facing_end=.22,
                                  plate=(1.140, 1.420), yoke=True)),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--author-rig", default="luminous_male")
    parser.add_argument("--posed", action="store_true")
    parser.add_argument("--bare-legs", action="store_true",
                        help="check without trousers, which the waist seam has "
                             "to survive as well")
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()

    races = sorted(path.stem for path in
                   (arguments.client / "assets/actors/native/races").glob("*.glb"))
    rig = ea.load_rig(arguments.client
                      / f"assets/actors/native/races/{arguments.author_rig}.glb")
    clips = gf.POSE_CLIPS if arguments.posed else (("bind", 0.0),)

    summary = {}
    for name, (kind, style) in PROTOTYPES.items():
        path = arguments.out / f"prototype_{name}.glb"
        stats = build(rig, path, kind, style, f"Prototype {name.title()}")
        print(f"built {path.name}: {stats['vertices']} verts, "
              f"{stats['triangles']} tris", flush=True)
        summary[name] = report(name, check(arguments.client, path, races,
                                           arguments.author_rig, clips,
                                           not arguments.bare_legs))
    if arguments.json:
        arguments.json.write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.exit(main())
