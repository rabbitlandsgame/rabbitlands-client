"""Export the public creature guide and current portraits to the wiki checkout.

Only the player-facing bestiary payload and rendered portrait files are copied.
Internal balance notes, server source files and authoring receipts stay private.
"""
from __future__ import annotations

import argparse
from datetime import date
import html
from pathlib import Path
import re
import shutil

from build_creature_bestiary import ROOT, DEFAULT_SERVER, OUTPUT, load_catalog, render_portrait

RAW = "https://raw.githubusercontent.com/wiki/rabbitlandsgame/rabbitlands-client/"


def export(wiki: Path, snapshot_date: str) -> None:
    rows, models = load_catalog(DEFAULT_SERVER)
    stamp = snapshot_date.replace("-", "")
    media = wiki / "media" / f"creature-stats-{stamp}"
    media.mkdir(parents=True, exist_ok=True)
    portraits = {}
    for model in models:
        _, source = render_portrait(model)
        assert re.fullmatch(r"[A-Za-z0-9_-]+", model["key"]), model["key"]
        target = media / (model["key"] + ".webp")
        shutil.copyfile(source, target)
        portraits[model["index"]] = RAW + target.relative_to(wiki).as_posix()
    offline = f"media/rabbitlands-creature-guide-{stamp}.html"
    shutil.copyfile(OUTPUT, wiki / offline)
    regular = [r for r in rows if not r["boss"]]
    bosses = [r for r in rows if r["boss"]]
    lines = [
        "# Creature Stats and Difficulty Guide", "",
        f"> **Development snapshot:** {snapshot_date}. These are the current authored stats; availability depends on your testing round and build.", "",
        f"Compare all **{len(rows)} creature definitions**: **{len(regular)} regular species** and **{len(bosses)} named bosses**, using {len(models)} current creature models.", "",
        "**Quick anchors:** Crown Stag **30/30 A/D**, Moss Boar **40/40 A/D**, and passive Golden Bison **80/80 A/D**. Ordinary family variants sit nearby; magical variants can be stronger.", "",
        f"The player cap is **200 Attack and 200 Defense**. This snapshot includes **{sum(r['endgame'] for r in regular)} regular species at 200+ in both skills** and **{sum(r['aboveCap'] for r in bosses)} named bosses above 200 in both skills**.", "",
        "## Using this guide", "",
        "- A/D average is the arithmetic mean of Attack and Defense. Each table runs from lower to higher average A/D.",
        "- These are native species stats. Equipment, encounter rules and gauntlet difficulty can change the actual fight; the average is not a simulated player difficulty rating.",
        "- Passive field creatures do not initiate combat. Aggressive creatures use their aggression limits; an aggressive label does not mean every player will be attacked.",
        "- Special encounters include named bosses, creatures without ordinary field placements and tame livestock. A catalogue entry does not guarantee a normal wild spawn.",
        "- Use your browser's Find command to locate a creature. Portraits are individually framed and do not compare physical size.", "",
        f"**[Download the interactive offline guide]({RAW + offline})** — save the linked HTML file and open it in your browser for search, sorting, habitats, full attributes, drop tables and the aggression checker. It works without an internet connection.", "",
        "[Passive field creatures](#passive-field-creatures) · [Aggressive field creatures](#aggressive-field-creatures) · [Special encounters](#special-encounters) · [Model galleries](Bestiary)", "",
    ]

    def number(value):
        return f"{value:,g}" if isinstance(value, float) else f"{value:,}"

    def bounds(pair):
        return number(pair[0]) if pair[0] == pair[1] else f"{number(pair[0])}–{number(pair[1])}"

    for group, heading in [("passive", "Passive field creatures"),
                           ("aggressive", "Aggressive field creatures"),
                           ("special", "Special encounters")]:
        selected = sorted((r for r in rows if r["group"] == group),
                          key=lambda r: (r["average"], r["name"].casefold()))
        lines += [f"## {heading}", "", f"**{len(selected)} entries.**", "",
                  "| Portrait | Creature | A/D avg | Attack | Defense | Health | Damage | Armor |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in selected:
            name = html.escape(r["name"])
            label = " · Named boss" if r["boss"] else ""
            if group == "special" and not r["boss"]:
                label = " · " + ("Tame livestock" if r["availability"] == "Livestock"
                                  else "Aggressive" if r["aggressive"] else "Passive")
            lines.append(f'| <img src="{portraits[r["portrait"]]}" alt="{name}" width="48" height="48"> '
                         f'| {name}{label} | {number(r["average"])} | {r["attack"]} | {r["defense"]} '
                         f'| {number(r["health"])} | {bounds(r["damage"])} | {bounds(r["armor"])} |')
        lines += [""]
    lines += ["## Related guides", "",
              "[Creature model galleries](Bestiary) · [Combat](Combat) · [Progression](Character-Progression) · [Gauntlet difficulty](Gauntlets-and-Instances) · [Summoning](Summoning)", "",
              "This page and its offline companion are generated from the same Rabbit Lands creature, map, spawn, recipe and drop definitions. Stats are a dated development reference; use the build supplied for your testing round.", "",
              "---", "", "[Wiki home](Home) · [Project identity](Project-Identity)", ""]
    (wiki / "Creature-Stats.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Exported {len(rows)} entries, {len(models)} portraits and the standalone HTML guide.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki", type=Path, default=ROOT.parent / "rabbitlands-client.wiki")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    export(args.wiki.resolve(), args.date)


if __name__ == "__main__":
    main()
