"""Render matched generated outfits, both assembled and worn, using Blender.

All eight designs in each family are paired by their concept-sheet cell. The
legendary harness uses its matching derived sabatons; --alternate-boots adds
the eight separate legendary boot designs. No game assets are modified.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
from pathlib import Path
import subprocess
import sys

import import_generated_equipment as batch

FAMILIES = {
    "amberwood": (
        "amberwood_woodland_cuirass",
        "amberwood_woodland_legguards",
        "amberwood_woodland_boots",
        "amberwood_forest_helm",
    ),
    "arcane": (
        "eloria_arcane_armor",
        "arcane_leg_armor",
        "arcane_fantasy_boots",
        "arcane_ethereal_circlet",
    ),
    "legendary": (
        "legendary_hero_cuirass",
        "legendary_leg_armor",
        "legendary_sabatons",
        "legendary_eloria_helm",
    ),
    "knightly": (
        "knightly_torso_armor",
        "ceremonial_knight_greaves",
        "knightly_greaves",
        "knightly_headgear",
    ),
    "militia": (
        "militia_torso_armor",
        "militia_leg_armor",
        "militia_greaves",
        "militia_helmet",
    ),
    "ranger": (
        "leather_ranger_torso",
        "rugged_ranger_legwear",
        "leather_adventurer_boots",
        "adventurer_headwear",
    ),
    "frontier": (
        "eloria_frontier_shirt",
        "humble_frontier_pants",
        "frontier_boots",
        "frontier_hat",
    ),
    "sunmane": (
        "sunmane_steppe_shirt",
        "sunmane_steppe_legwear",
        "sunmane_steppe_boots",
        "sunmane_steppe_headgear",
    ),
}


def gallery(out, records, save_blend):
    cards = []
    for record in records:
        key, title = record["key"], record["title"]
        links = (
            (
                f'<p><a href="{key}.blend">Assembled Blender scene</a> · '
                f'<a href="{key}_worn.blend">Character Blender scene</a></p>'
            )
            if save_blend
            else ""
        )
        cards.append(
            f"""<article><h2>{escape(title)}</h2><div class="pair">
            <figure><a href="{key}.png"><img loading="lazy" src="{key}.png"></a><figcaption>Complete armour</figcaption></figure>
            <figure><a href="{key}_worn.png"><img loading="lazy" src="{key}_worn.png"></a><figcaption>On luminous male, true scale</figcaption></figure>
            </div>{links}<p class="parts">{escape(' · '.join(record['pieces']))}</p></article>"""
        )
    (out / "index.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>Eloria complete armour sets</title>
        <style>body{margin:32px auto;max-width:1600px;background:#1b2024;color:#eef0ed;font:16px system-ui}
        h1,p{margin:16px}h2{margin:16px 0 8px;font-size:22px}a{color:#dcc397}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(560px,1fr));gap:28px}
        article{padding:18px;background:#272d31;border-radius:10px}.pair{display:flex}figure{margin:0;width:50%}img{width:100%;display:block}
        figcaption{padding:10px;color:#bcc5c9}.parts{font-size:12px;color:#abb6bc;overflow-wrap:anywhere}</style>
        <h1>Eloria — complete generated armour sets</h1><p>Each outfit is shown assembled in Blender and worn by the character.
        The armour-only view is normalized for detail; the worn view retains true character scale. Faces and hands remain visible where the design is open.</p>
        <main>"""
        + "\n".join(cards)
        + "</main>",
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--equipment",
        type=Path,
        default=batch.EQUIPMENT / "variants" / "human_male",
        help="override leg/boot/head directory; torsos fall back to the shipped Human male fits",
    )
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        help="optional key such as legendary_01; repeatable",
    )
    ap.add_argument("--alternate-boots", action="store_true")
    ap.add_argument("--save-blend", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--pose", choices=["rest", "source", "bent"], default="source")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    roster = {p.slug: p for p in batch.roster()}
    families = dict(FAMILIES)
    if args.alternate_boots:
        torso, legs, _, head = families["legendary"]
        families["legendary_alt"] = (torso, legs, "legendary_eloria_boots", head)
    records = []
    for family, sheets in families.items():
        for index in range(1, 9):
            key = f"{family}_{index:02}"
            if args.set and key not in args.set:
                continue
            slugs = [f"{sheet}_{index:02}" for sheet in sheets]
            paths = [args.equipment / (slug + ".glb") for slug in slugs]
            # The shipped pieces are the Human male fits; the old-male base
            # scenes equipment/<slug>.glb were deleted in P7 (2026-10).
            paths = [p if p.exists() else batch.EQUIPMENT / "variants" / "human_male" / p.name for p in paths]
            if not all(p.exists() for p in paths):
                raise SystemExit("Missing outfit: " + key)
            records.append(
                dict(
                    key=key,
                    title=roster[slugs[0]].name
                    + " / "
                    + family.replace("_", " ").title(),
                    pieces=slugs,
                    paths=[str(p.resolve()) for p in paths],
                    yaw=args.yaw,
                    pose=args.pose,
                )
            )
    if args.set and set(args.set) - {r["key"] for r in records}:
        raise SystemExit("Unknown --set key")
    (args.out / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    gallery(args.out, records, args.save_blend)

    def render(record):
        key = record["key"]
        expected = [
            args.out / (key + suffix)
            for suffix in [".png", "_worn.png"]
            + ([".blend", "_worn.blend"] if args.save_blend else [])
        ]
        if args.resume and all(p.exists() for p in expected):
            return key + " already rendered"
        command = [
            sys.executable,
            str(Path(__file__).with_name("compare_conformed_piece.py")),
            *record["paths"],
            "--ensemble",
            "--out",
            str(args.out / (key + ".png")),
            "--width",
            str(args.width),
            "--worn",
            str(batch.CLIENT / "assets/actors/native/races/luminous_male.glb"),
            "--worn-pose",
            args.pose,
            "--yaw",
            str(args.yaw),
        ]
        if args.save_blend:
            command.append("--save-blend")
        result = subprocess.run(command, capture_output=True, text=True)
        (args.out / (key + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode or not all(p.exists() for p in expected):
            raise RuntimeError("Render failed: " + key + "; see its log")
        return key + " rendered"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for message in pool.map(render, records):
            print(message, flush=True)
    print(f'{len(records)} complete outfits: {args.out / "index.html"}', flush=True)


if __name__ == "__main__":
    main()
