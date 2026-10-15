#!/usr/bin/env python3
"""The sixty-four leg garments as registry entries.

Joins `legwear_roster` to `legwear_palettes` and hands the build a table in the
same shape as the culture pieces it sits beside: slug, label, part, visual id,
kind, base colour, accent colour, and the feature list the geometry is lofted
from.

**Visual id allocation: part 4, ids 107-170.**

Part 4's byte is shared three ways, and all three have to be checked.  Reading
only the client registry is not enough - it was the first answer here and it was
wrong, because most of what already owns a part-4 id has no client mesh at all:

- **0-8 are the appearance fallback.**  `ADD_ACTOR` packs
  `visuals.get(4, look["pants"])`, so with nothing equipped the byte *is* the
  character's appearance pants index.  Character creation offers 0-8 and NPCs
  take `(seed // 17) % 6`, and the client resolves the byte by looking up
  `"4:<id>"` in the model registry - which finds the nine colour tints of
  `generic_pants` at exactly `4:0`-`4:8`.  The overlap is deliberate: those nine
  ids *are* the nine appearance trousers.  Taking one would put a garment on
  every unequipped character in the game.
- **9-15 are the rest of the generic tier**: leather, fur and the four cuisses.
- **16-46 are already claimed on the server**, and this is the half that is
  invisible from the client.  `EQUIPMENT_VISUAL_OVERRIDES` in `eloria/items.py`
  assigns 17-46 to the robe skirts, baggy pants, peasant skirts and wedding
  skirts, and the `kind == "legs"` branch of `equipment_visual` emits 16, 33, 34
  and 40 for the dragon cuisses.  None of them has a mesh in `equipment.json`,
  so every one of those ids looks free in the client registry and is not.
- **100-106 are the seven authored culture pieces.**

That leaves 47-99 - only fifty-three, too few - and 107-255.  So the block is
107-170, and 47-99 and 171-255 stay free.

"""
from __future__ import annotations

from legwear_palettes import load
from legwear_roster import ROSTER

#: First visual id of the block.  See the note above before moving it.
FIRST_VISUAL = 107

#: How each sheet's designs are finished, which drives metallic, roughness and
#: whether the trim glows.  A design's own palette carries its colour; the
#: finish carries how the surface behaves in light.
SHEET_FINISH = {
    "legendary": "plate", "arcane": "crystal", "amberwood": "leather",
    "sunmane": "leather", "ceremonial": "plate", "militia": "mail",
    "ranger": "leather", "frontier": "cloth",
}

#: Designs whose material is not their sheet's default.
FINISH_OVERRIDE = {
    "rimeguard_cuisses": "crystal", "ossuary_cuisses": "shell",
    "mosswarden_legs": "crystal", "umbral_drapes": "cloth",
    "astral_robe_legs": "cloth", "starfall_drapes": "cloth",
    "tidesilk_wrap": "cloth", "oracle_drapes": "cloth",
    "runebound_breeches": "leather", "barkplate_legs": "wood",
    "heartwood_cuisses": "wood", "antlerward_legs": "wood",
    "amberglass_legs": "crystal", "leafmail_legs": "mail",
    "sunmane_sarong": "cloth", "caravan_wrap": "cloth",
    "sundisc_tassets": "plate", "sunplate_cuisses": "plate",
    "quilted_chausses": "cloth", "mail_chausses": "mail",
    "padded_leathers": "leather", "levy_breeches": "leather",
    "brass_cuisses": "plate", "sergeant_cuisses": "plate",
    "splinted_cuisses": "plate", "brigandine_legs": "leather",
    "crimson_guard_legs": "plate", "standard_bearer_legs": "plate",
    "longcoat_leathers": "leather",
}


def _entries():
    palettes = load()
    for index, (slug, label, sheet, _tile, kind, features) in enumerate(ROSTER):
        colours = palettes[slug]
        finish = FINISH_OVERRIDE.get(slug, SHEET_FINISH[sheet])
        yield (slug, label, 4, FIRST_VISUAL + index, kind,
               tuple(colours["base"]), tuple(colours["trim"]), features, finish)


#: (slug, label, part, visual, kind, base, accent, features, finish)
LEGWEAR_EQUIPMENT = tuple(_entries())

#: The finish each slug is built with, in the shape `EQUIPMENT_FINISH` uses.
LEGWEAR_FINISH = {row[0]: row[8] for row in LEGWEAR_EQUIPMENT}


if __name__ == "__main__":
    print(f"{len(LEGWEAR_EQUIPMENT)} pieces, "
          f"visuals 4:{LEGWEAR_EQUIPMENT[0][3]}-4:{LEGWEAR_EQUIPMENT[-1][3]}")
    # Everything the server can already emit for part 4.  Derived by walking
    # `equipment_visual` over the whole item table plus the appearance range;
    # kept here as a literal so this file can be checked without the server
    # checkout beside it.
    taken = set(range(0, 47)) | set(range(100, 107))
    mine = {row[3] for row in LEGWEAR_EQUIPMENT}
    assert not (mine & taken), sorted(mine & taken)
    assert len(mine) == 64 and max(mine) < 256
    for row in LEGWEAR_EQUIPMENT:
        print(f"  4:{row[3]:<3d} {row[0]:22s} {row[4]:5s} {row[8]:8s} "
              f"#{row[5][0]:02x}{row[5][1]:02x}{row[5][2]:02x} "
              f"#{row[6][0]:02x}{row[6][1]:02x}{row[6][2]:02x}  {' '.join(row[7])}")
