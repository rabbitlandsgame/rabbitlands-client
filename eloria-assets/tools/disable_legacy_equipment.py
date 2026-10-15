#!/usr/bin/env python3
"""Leave the generated armour set as the only equipment in the game.

Added 2026-09-02 for Eloria Client.

Everything that is not one of the sixty generated pieces is switched off: the
authored armour, and also every weapon, shield, cape, neck piece and ring, and
the gear NPCs and creatures wear.  That is the whole catalogue bar the new set,
and it does mean the game has no weapons in it -- which is the point of the
exercise, not an oversight.

Four levers, one per place a wearable is defined:

  client registry   godot-client/data/actors/equipment.json -- drop every
                    `models` entry that is not the new set, so nothing else
                    resolves to geometry.
  client NPC looks  godot-client/data/actors/models.json -- clear the
                    `equipmentVisuals` each npcLook carries.  Removing the
                    models alone is not enough: a look that still names a
                    visual falls through to `_attach_fallback_equipment`, which
                    draws a placeholder blob on the bone rather than nothing.
  server items      dev-server/config/eloria/items.txt -- take `equip_type`
                    off every other equippable item.  The item survives, so
                    inventories, shops and drops that name it still resolve;
                    it simply cannot be worn.  This is also what stops
                    creatures rolling it, since `creature_equipment_eligible`
                    rejects anything without an equip type.
  server visuals    dev-server/eloria/items.py -- `equipment_visual` looks its
                    override table up by name before it looks at the item, so
                    an unequippable sword would still resolve to a visual.  A
                    guard at the top closes that, which is cheaper and far less
                    invasive than deleting four hundred override rows.

Creature gear is switched off at the settings rather than in the roll, by
taking the two chances to zero.

  python disable_legacy_equipment.py             disable
  python disable_legacy_equipment.py --restore   put it all back
  python disable_legacy_equipment.py --dry-run

`--restore` is `git checkout` of the four files, so uncommitted work in any of
them is lost.  It says so before doing it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import import_generated_equipment as ig

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
SERVER = HERE.parent.parent.parent / "dev-server"

REGISTRY = CLIENT / "data/actors/equipment.json"
MODELS = CLIENT / "data/actors/models.json"
ITEMS = SERVER / "config/eloria/items.txt"
ITEMS_PY = SERVER / "eloria/items.py"
SETTINGS = SERVER / "eloria/settings.py"

GUARD_OPEN = "    # --- generated-set-only guard (disable_legacy_equipment.py) ---"
GUARD_CLOSE = "    # --- end generated-set-only guard ---"
GUARD_BODY = """    # Every other wearable has had its equip_type taken away, and an item
    # that cannot be worn has no visual.  The lookup below is by name and runs
    # before anything reads the item, so without this a sword that nobody can
    # equip would still resolve to a weapon model.
    if not item.equip_type:
        return None"""


def kept_visuals() -> set[str]:
    return {"%d:%d" % (p.part, p.visual) for p in ig.roster()}


def kept_item_ids() -> set[int]:
    return {p.item_id for p in ig.roster()}


def disable_registry(dry: bool) -> str:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    keep = kept_visuals()
    before = len(data["models"])
    data["models"] = {k: v for k, v in data["models"].items() if k in keep}
    if not dry:
        REGISTRY.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "registry: %d models -> %d" % (before, len(data["models"]))


def disable_npc_looks(dry: bool) -> str:
    data = json.loads(MODELS.read_text(encoding="utf-8"))
    looks = data.get("npcLooks", {})
    cleared = 0
    for look in looks.values():
        if look.get("equipmentVisuals"):
            look["equipmentVisuals"] = {}
            cleared += 1
    if not dry:
        # Written back at the indent the file was authored with.  It is
        # currently tab-indented in the working tree by something that only
        # reflowed whitespace, so writing JSON puts it back and keeps this
        # change legible as a diff.
        MODELS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "npcLooks: cleared equipment on %d of %d" % (cleared, len(looks))


def disable_items(dry: bool) -> str:
    text = ITEMS.read_text(encoding="utf-8")
    keep = kept_item_ids()
    stripped = 0

    def scrub(match: re.Match) -> str:
        nonlocal stripped
        block = match.group(0)
        found = re.search(r"^item_id: (\d+)$", block, re.M)
        if not found or int(found.group(1)) in keep:
            return block
        if not re.search(r"^equip_type: ", block, re.M):
            return block
        stripped += 1
        return re.sub(r"^equip_type: .*\n", "", block, flags=re.M)

    out = re.sub(r"\[item\].*?\[/item\]", scrub, text, flags=re.S)
    if not dry:
        ITEMS.write_text(out, encoding="utf-8")
    return "items.txt: equip_type removed from %d item(s)" % stripped


def guard_visuals(dry: bool) -> str:
    source = ITEMS_PY.read_text(encoding="utf-8")
    if GUARD_OPEN in source:
        return "items.py: guard already present"
    anchor = ('    """Map catalog equipment to the stock enhanced-actor part '
              'and model IDs."""\n')
    if anchor not in source:
        raise SystemExit("could not find equipment_visual to guard")
    block = "%s\n%s\n%s\n" % (GUARD_OPEN, GUARD_BODY, GUARD_CLOSE)
    if not dry:
        ITEMS_PY.write_text(source.replace(anchor, anchor + block, 1),
                            encoding="utf-8")
    return "items.py: guarded equipment_visual against unequippable items"


def disable_creature_gear(dry: bool) -> str:
    source = SETTINGS.read_text(encoding="utf-8")
    out, changed = source, []
    for field in ("creature_equipment_base_chance",
                  "creature_equipment_max_chance"):
        pattern = re.compile(r"(%s: int = )(\d+)" % field)
        found = pattern.search(out)
        if found and found.group(2) != "0":
            changed.append("%s %s->0" % (field, found.group(2)))
            out = pattern.sub(r"\g<1>0", out, count=1)
    if changed and not dry:
        SETTINGS.write_text(out, encoding="utf-8")
    return "settings.py: " + (", ".join(changed) if changed
                              else "creature gear already off")


def restore() -> int:
    print("This is `git checkout` of five files.  Uncommitted work in any of\n"
          "them is lost:")
    for path in (REGISTRY, MODELS, ITEMS, ITEMS_PY, SETTINGS):
        print("   %s" % path)
    for repo, paths in ((CLIENT.parent, (REGISTRY, MODELS)),
                        (SERVER, (ITEMS, ITEMS_PY, SETTINGS))):
        rel = [str(p.relative_to(repo)) for p in paths]
        subprocess.run(["git", "-C", str(repo), "checkout", "--"] + rel,
                       check=True)
    print("restored")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="disable every wearable except the generated armour set")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.restore:
        return restore()

    print("keeping %d generated pieces; disabling everything else"
          % len(kept_visuals()))
    for line in (disable_registry(args.dry_run),
                 disable_npc_looks(args.dry_run),
                 disable_items(args.dry_run),
                 guard_visuals(args.dry_run),
                 disable_creature_gear(args.dry_run)):
        print("  " + line)
    if args.dry_run:
        print("\nnothing written (--dry-run)")
    else:
        print("\nRestart the server (the catalogue is read once at boot) and\n"
              "the client.  `--restore` puts it all back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
