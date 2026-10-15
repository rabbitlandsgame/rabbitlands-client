#!/usr/bin/env python3
"""Take the generated armour set into the client and the server, in one pass.

Added 2026-09-01 for Eloria Client.

``conform_equipment`` turns one generated mesh into one wearable GLB.  This is
the other half: which sixty meshes, what each of them is, where its geometry
lands, and the two halves of the definition that make it a thing a player can
own.  A wearable is not one record but four, joined only by the item's name --

  the mesh          godot-client/assets/actors/native/equipment/<slug>.glb
  the client entry  godot-client/data/actors/equipment.json, models["part:id"]
  the server item   dev-server/config/eloria/items.txt, an [item] block
  the server visual dev-server/eloria/items.py, EQUIPMENT_VISUAL_OVERRIDES

What this tool does NOT decide is what a piece is worth.  It seeds a stat the
first time it defines a piece and preserves it on every run after, so a
balance pass done in the spreadsheet survives a rename or a new sheet.

-- and a set added to one side and not the other is either armour that draws
nothing or geometry nobody can wear.  All four are written here so they cannot
drift apart.

  python import_generated_equipment.py                 build and write
  python import_generated_equipment.py --dry-run       say what would change
  python import_generated_equipment.py --sheet arcane_ethereal

Idempotent.  The server blocks are fenced by markers and rewritten whole; the
client entries are merged into the registry by key, so the authored models
around them are left alone rather than regenerated.

Since the race programme's P7 cleanup (2026-10) the mesh an installed piece
ships is its Human fit, ``variants/human_male|human_female/<slug>.glb``
(refit_human_bodies.py, install_human_equipment.py,
share_human_equipment_textures.py), and its base ``scene`` names the
human_male file.  The old-male ``equipment/<slug>.glb`` this tool builds was
deleted for those pieces, so it is no longer rebuilt in place: that would only
leave an untracked file nothing names.  New pieces still build there.  To
rebuild installed pieces for an audit, build them into a scratch folder:

  python import_generated_equipment.py --meshes-only --build-dir <scratch>

and point audit_torso_remap.py / audit_limb_head_remap.py ``--directory``
(or render_generated_armour_sets.py ``--equipment``) at it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import conform_equipment as ce
import equipment_authoring as ea

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
PROJECT = HERE.parent.parent.parent
SERVER = PROJECT / "dev-server"
GENERATED = PROJECT / "generate_models" / "meshy-armor-individual-glb"

EQUIPMENT = CLIENT / "assets/actors/native/equipment"
REGISTRY = CLIENT / "data/actors/equipment.json"

OPEN_ITEMS = "# --- generated armour set (tools/import_generated_equipment.py) ---"
CLOSE_ITEMS = "# --- end generated armour set ---"
OPEN_PY = "    # --- generated armour set (eloria-assets/tools/import_generated_equipment.py) ---"
CLOSE_PY = "    # --- end generated armour set ---"

#: Where the catalogue starts.  1274 is the first id after the shipped items,
#: and the icon contract in tests/test_item_icon_contract.py stops at 1272, so
#: nothing here is inside a range that test pins.
FIRST_ITEM_ID = 1274

#: Where a sheet appended *after* that block is numbered from.  The thirty-two
#: sheets above fill 1274-1529 and images 118-373 exactly, and the weapon set
#: opens on the next id of both -- so a thirty-third sheet carrying on the
#: count would hand out ids the weapons already own, silently, in a table
#: nothing cross-checks.  The generated sets between them leave no room either:
#: their image ids are packed solid to 575.  So later sheets are numbered from
#: above all four, the weapons ending at 1629/473 and the painted potion shelf
#: at 1751/575.
#:
#: Pushing the other three sets up by eight instead was the obvious-looking
#: alternative and is not one: an item id is what a character's inventory
#: stores, so moving one rewrites what players already own.
LATER_ITEM_ID = 1752
LATER_IMAGE_ID = 576

#: What a piece is worth ON THE RUN THAT FIRST DEFINES IT is decided by three
#: things: its finish (the material family -- emu and the armour base), its
#: slot (a cuirass stops more than a boot), and its sheet's tier (militia kit
#: up to legendary regalia).  The numbers stay on the Eternal Lands scale the
#: old flat ladder used -- single digits per piece, a worn set in the twenties
#: -- the tiers spread the sheets across that scale instead of stacking them
#: all on one rung.
#:
#: After that first run this is a seed and not an authority: the stat belongs
#: to whoever balances it, through dev-server/tools/import_equipment_csv.py,
#: and `served_stats` carries what the catalogue holds across a rewrite.  So
#: editing a tier here moves a sheet that has never been served and nothing
#: else; `--reseed` is how a changed tier reaches pieces already served, and
#: it discards that balancing by design.
FINISH_EMU = {"cloth": 4, "leather": 8, "mail": 14, "plate": 18}

#: (armour low, armour high, defense) for a TORSO piece of the finish at
#: tier 1; SLOT_SHARE scales the other slots down from it.
FINISH_BASE = {
    "cloth": (0, 2, 0),
    "leather": (2, 6, -1),
    "mail": (3, 9, -2),
    "plate": (5, 12, -3),
}

#: How much of the torso's protection each part carries (part id -> share).
SLOT_SHARE = {5: 1.0, 4: 0.65, 3: 0.55, 6: 0.45}

#: Sheet tiers.  1 is field kit anyone drills in, 5 is regalia with a name.
#: Rarer gear is better gear: the tier widens the armour range, and from
#: tier 4 the piece is balanced enough to shed a point of defense penalty.
TIER_COMMON, TIER_STURDY, TIER_FINE, TIER_SUPERIOR, TIER_LEGENDARY = 1, 2, 3, 4, 5

#: Sheet themes that carry stats beyond armour.  Arcane work channels the
#: wearer (ether and magic protection); legendary pieces are simply better
#: made and harder to kill in.
THEME_EXTRAS = {
    "arcane": lambda tier: (
        [("magic_protection", max(0, tier - 2)),
         ("max_ether", 4 * max(0, tier - 2))] if tier >= 3 else []),
    "legendary": lambda tier: (
        [("max_health", 4 * max(0, tier - 2))] if tier >= 3 else []),
}


def finish_stats(finish: str, part: int, tier: int, theme: str):
    """(emu, armour low/high, defense, extras) on the Eternal Lands scale."""
    base_low, base_high, base_defense = FINISH_BASE[finish]
    share = SLOT_SHARE[part]
    low = int(round(base_low * share)) + max(0, tier - 2)
    high = int(round(base_high * share)) + 2 * (tier - 1)
    defense = int(round(base_defense * share))
    if tier >= TIER_SUPERIOR and defense < 0:
        defense += 1
    extras = list(THEME_EXTRAS.get(theme, lambda _: [])(tier))
    if theme == "legendary":
        low, high = low + 1, high + 2
    return FINISH_EMU[finish], (low, high), defense, extras

#: Where the set's inventory icons start.  Each piece gets its own icon --
#: rendered from its mesh by generate_models/equipment_icons and packed into
#: the runtime atlases by tools/build_item_icon_atlases.py, which assigns ids
#: in this same roster order.  118 is the first cell after the shipped painted
#: range: the blank tail of items5.png takes seven, items6-8.png the rest, so
#: the painted prefix stays contiguous and imageCount moves 118 -> 178.
FIRST_IMAGE_ID = 118

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]

#: What each piece is called, keyed by the slug of its sheet and given in the
#: sheet's own column order.  A sheet's eight designs are eight different
#: garments, not eight grades of one, so each is named for what it is drawn as
#: rather than numbered off its sheet: an item's name is what a player has to
#: recognise it by in a trade window or a drop list, and eight rows reading
#: "Militia Helmet I" through "VIII" say nothing about which one is the kettle
#: hat.  Where four sheets were drawn as one wardrobe -- the amberwood, arcane
#: and legendary sets each cover head, torso, legs and feet -- column N is the
#: same design in four slots and the names say so, so a matched outfit is
#: nameable ("Phoenix" head to foot).
#:
#: A sheet with no row here falls back to the numerals.  Renaming a piece is
#: not free: the name is what joins an item's four records, so re-run this tool
#: afterwards (--skip-build is enough) to move the registry entry, the server
#: item and the visual override together, and grep the server's tests for any
#: name they pin.
NAMES = {
    # --- Amberwood woodland: eight forest designs, one outfit per column ---
    "amberwood_woodland_cuirass": [
        "Bark Jerkin", "Mossbound Coat", "Rootwrap Tunic", "Leafscale Cuirass",
        "Heartwood Cuirass", "Furtrim Coat", "Amberglass Cuirass",
        "Ivory Vine Cuirass"],
    "amberwood_woodland_legguards": [
        "Bark Legguards", "Mossbound Legguards", "Rootwrap Legguards",
        "Leafscale Legguards", "Heartwood Legguards", "Furtrim Legguards",
        "Amberglass Legguards", "Ivory Vine Legguards"],
    "amberwood_forest_helm": [
        "Bark Hood", "Mossbound Cap", "Rootwrap Circlet", "Leafscale Hood",
        "Heartwood Helm", "Antler Hood", "Amberglass Helm", "Ivory Vine Helm"],
    "amberwood_woodland_boots": [
        "Bark Boots", "Mossbound Boots", "Rootwrap Boots", "Leafscale Boots",
        "Heartwood Boots", "Furtrim Boots", "Amberglass Boots",
        "Ivory Vine Boots"],

    # --- Arcane: the same eight castings across four slots ---
    "eloria_arcane_armor": [
        "Warded Tabard", "Glowline Coat", "Palesteel Cuirass",
        "Starglass Cuirass", "Twilight Cuirass", "Seawrap Robe",
        "Acolyte Tunic", "Crystalward Plate"],
    "arcane_leg_armor": [
        "Warded Legguards", "Glowline Legguards", "Palesteel Legguards",
        "Starglass Legguards", "Twilight Legguards", "Seawrap Legguards",
        "Acolyte Legguards", "Crystalward Legguards"],
    "arcane_ethereal_circlet": [
        "Warded Turban", "Glowline Hood", "Palesteel Circlet",
        "Starglass Circlet", "Twilight Helm", "Seawrap Veil", "Acolyte Hood",
        "Crystalward Helm"],
    "arcane_fantasy_boots": [
        "Warded Boots", "Glowline Boots", "Palesteel Boots", "Starglass Boots",
        "Twilight Boots", "Seawrap Boots", "Acolyte Boots",
        "Crystalward Boots"],

    # --- Legendary: eight named regalia, head to foot ---
    "legendary_hero_cuirass": [
        "Phoenix Cuirass", "Glacier Cuirass", "Nightstorm Cuirass",
        "Dragonbone Cuirass", "Sunburst Cuirass", "Amethyst Cuirass",
        "Knotwork Cuirass", "Lion Cuirass"],
    "legendary_leg_armor": [
        "Phoenix Legguards", "Glacier Legguards", "Nightstorm Legguards",
        "Dragonbone Legguards", "Sunburst Legguards", "Amethyst Legguards",
        "Knotwork Legguards", "Lion Legguards"],
    "legendary_eloria_helm": [
        "Phoenix Helm", "Glacier Helm", "Nightstorm Helm", "Dragonbone Helm",
        "Sunburst Helm", "Amethyst Helm", "Knotwork Helm", "Lion Helm"],
    "legendary_eloria_boots": [
        "Phoenix Boots", "Glacier Boots", "Nightstorm Boots",
        "Dragonbone Boots", "Sunburst Boots", "Amethyst Boots",
        "Knotwork Boots", "Lion Boots"],
    # Trimmed off the legendary leg armour, so they keep its column order.
    "legendary_sabatons": [
        "Phoenix Sabatons", "Glacier Sabatons", "Nightstorm Sabatons",
        "Dragonbone Sabatons", "Sunburst Sabatons", "Amethyst Sabatons",
        "Knotwork Sabatons", "Lion Sabatons"],

    # --- Knightly: refined plate and mail ---
    "knightly_torso_armor": [
        "Fluted Breastplate", "Polished Cuirass", "Gilded Vine Cuirass",
        "Scalework Cuirass", "Rosette Cuirass", "Tasset Cuirass",
        "Mantled Cuirass", "Blackened Cuirass"],
    "ceremonial_knight_greaves": [
        "Herald Cuisses", "Fleur Cuisses", "Crimson Cuisses", "Ivory Cuisses",
        "Lion Cuisses", "Silver Cuisses", "Rosette Cuisses",
        "Blackened Cuisses"],
    "knightly_headgear": [
        "Gilt Bascinet", "Visored Bascinet", "Great Helm", "Knight Sallet",
        "Winged Helm", "Crowned Helm", "Crested Helm", "Masked Helm"],
    "knightly_greaves": [
        "Fluted Sabatons", "Palmette Greaves", "Tracery Greaves",
        "Cathedral Greaves", "Cross Greaves", "Star Greaves",
        "Crimson Greaves", "Blackened Sabatons"],

    # --- Militia: the drilled kit, cheapest first ---
    "militia_torso_armor": [
        "Arming Gambeson", "Studded Jack", "Splinted Vest",
        "Mail Shirt", "Riveted Lamellar", "Plain Breastplate",
        "Brass Breastplate", "Crimson Guard Cuirass"],
    "militia_leg_armor": [
        "Arming Chausses", "Leather Kneecops", "Splinted Chausses",
        "Mail Leggings", "Riveted Tassets", "Steel Kneecops",
        "Brass Chausses", "Crimson Guard Chausses"],
    "militia_helmet": [
        "Padded Coif", "Leather Helm", "Kettle Hat", "Spangenhelm",
        "Mail Coif", "Cheekguard Helm", "Brass Helm", "Crimson Helm"],
    "militia_greaves": [
        "Shinplate Boots", "Banded Warboots", "Steel Greaves", "Toecap Boots",
        "Brass Greaves", "Splinted Greaves", "Crimson Warboots",
        "Furtop Warboots"],

    # --- Ranger and adventurer leathers ---
    "leather_ranger_torso": [
        "Bonehook Jerkin", "Scout Vest", "Sashed Jerkin", "Brassbuckle Coat",
        "Mossfringe Jerkin", "Ropecoil Jerkin", "Riveted Jerkin",
        "Trapper Coat"],
    "rugged_ranger_legwear": [
        "Pouchbelt Breeches", "Fangbelt Breeches", "Strapwrap Breeches",
        "Sidelace Breeches", "Bonecharm Breeches", "Ringcoil Breeches",
        "Studded Chaps", "Furwrap Breeches"],
    "adventurer_headwear": [
        "Fang Hood", "Feathered Cap", "Buckled Hood", "Plumed Hat",
        "Charm Hood", "Studded Cap", "Banded Cap", "Fur Hood"],
    "leather_adventurer_boots": [
        "Charmcord Boots", "Furcuff Boots", "Buckled Boots", "Beaded Boots",
        "Redlace Boots", "Runewrap Boots", "Guard Boots", "Strapped Boots"],

    # --- Frontier homespun ---
    "eloria_frontier_shirt": [
        "Homespun Shirt", "Redtrim Tunic", "Patched Workshirt", "Whipstitch Shirt",
        "Sashwrap Shirt", "Laced Field Tunic", "Tattered Blue Shirt",
        "Woollen Tunic"],
    "humble_frontier_pants": [
        "Patched Trousers", "Work Trousers", "Ragged Trousers",
        "Redtrim Trousers", "Sashed Breeches", "Kneepad Trousers",
        "Faded Trousers", "Woollen Breeches"],
    "frontier_hat": [
        "Wool Cap", "Drover Hat", "Patched Sunhat", "Earflap Cap",
        "Linen Kerchief", "Felt Hat", "Field Hood", "Fur Cap"],
    "frontier_boots": [
        "Ankle Boots", "Slouch Boots", "Laced Fieldboots", "Corded Moccasins",
        "Riding Boots", "Fleece Boots", "Canvas Boots", "Cuffed Boots"],

    # --- Sunmane steppe ---
    "sunmane_steppe_shirt": [
        "Tasselled Tunic", "Fringed Kaftan", "Rider Vest", "Bone Clasp Coat",
        "Sundisc Cuirass", "Red Sash Wrap", "Riding Jacket", "Boneplate Coat"],
    "sunmane_steppe_legwear": [
        "Rider Breeches", "Wrapskirt Trousers", "Steppe Chaps",
        "Bonepeg Trousers", "Bronze Tassets", "Sashcord Trousers",
        "Corded Trousers", "Sunplate Tassets"],
    "sunmane_steppe_headgear": [
        "Riding Hat", "Steppe Headcloth", "Rider Helm", "Steppe Turban",
        "Sundisc Helm", "Sun Headband", "Scarf Hood", "Redplume Helm"],
    "sunmane_steppe_boots": [
        "Tasselled Boots", "Steppe Wrap Boots", "Bronze Boots",
        "Bonepeg Boots", "Sunplate Boots", "Sashed Boots", "Corded Boots",
        "Ivory Riding Boots"],
}


def piece_name(slug: str, index: int, label: str) -> str:
    """What one design is called, or the numbered fallback if it has no name."""
    names = NAMES.get(slug, ())
    if index < len(names):
        return names[index]
    return "%s %s" % (label, ROMAN[index])

#: One row per concept sheet: the stem it generated under, what the pieces are,
#: where their visual ids begin, the finish, and the sheet's tier and theme.
#: The ranges start above every id the registry already uses (helmet 108,
#: legs 170, body 183, boots 191) and stay inside a byte, which is all
#: ACTOR_WEAR_ITEM gives a visual.
SHEETS = [
    ("Amberwood_Woodland_Armor_Concept_Sheet", "Amberwood Woodland Cuirass",
     "amberwood_woodland_cuirass", "cuirass", 5, 184, "leather", 2, ""),
    ("Amberwood_Woodland_Legwear_Concept_Sheet", "Amberwood Woodland Legguards",
     "amberwood_woodland_legguards", "legs", 4, 171, "leather", 2, ""),
    ("Arcane_Fantasy_Boots_Concept_Sheet", "Arcane Fantasy Boots",
     "arcane_fantasy_boots", "boots", 6, 192, "leather", 4, "arcane"),
    ("Arcane_ethereal_headgear_design_sheet", "Arcane Ethereal Circlet",
     "arcane_ethereal_circlet", "circlet", 3, 109, "cloth", 4, "arcane"),
    ("Eight_amberwood_forest_headgear_designs", "Amberwood Forest Helm",
     "amberwood_forest_helm", "helm", 3, 117, "mail", 2, ""),
    ("Eight_amberwood_woodland_boot_designs", "Amberwood Woodland Boots",
     "amberwood_woodland_boots", "boots", 6, 200, "leather", 2, ""),
    ("Eight_arcane_leg_armor_designs", "Arcane Leg Armor",
     "arcane_leg_armor", "legs", 4, 179, "plate", 4, "arcane"),
    ("Eight_ceremonial_knight_leg_armor_designs", "Ceremonial Knight Greaves",
     "ceremonial_knight_greaves", "legs", 4, 187, "plate", 4, ""),
    # The rest of the concept art, appended rather than inserted: `roster`
    # hands out item ids in this order, so a row added anywhere but the end
    # would renumber every piece below it and break the names the server
    # already ships.  Ceremonial above is the one sheet that was cut mid-way by
    # a --limit, and it simply grows from four pieces to eight -- the four it
    # has keep their names and visuals because the sources sort before the new
    # ones, and NAMES is read by the same column index.
    #
    # Visual ranges continue above what each part already uses (helmet 124,
    # legs 190, body 191, boots 207) and stay inside a byte, which is all
    # ACTOR_WEAR_ITEM carries.  Boots is now the full part -- the two greaves
    # sets that moved into it (below) take it to 255 -- so a further boot sheet
    # needs an existing range compacted first.  Legs ends at 250 with 203-218
    # freed where the greaves used to sit.
    ("Eight_Legendary_Helms_of_Eloria", "Legendary Eloria Helm",
     "legendary_eloria_helm", "helm", 3, 125, "plate", 5, "legendary"),
    ("Eight_grounded_militia_helmet_designs", "Militia Helmet",
     "militia_helmet", "helm", 3, 133, "mail", 1, ""),
    ("Refined_knightly_headgear_concept_sheet", "Knightly Headgear",
     "knightly_headgear", "helm", 3, 141, "mail", 3, ""),
    ("Eight_frontier_hats_concept_sheet", "Frontier Hat",
     "frontier_hat", "hood", 3, 149, "cloth", 1, ""),
    ("Eight_leather_adventurer_headwear_designs", "Adventurer Headwear",
     "adventurer_headwear", "hood", 3, 157, "leather", 2, ""),
    ("Sunmane_Steppe_Headgear_Collection", "Sunmane Steppe Headgear",
     "sunmane_steppe_headgear", "hood", 3, 165, "leather", 2, ""),

    ("Eight_legendary_hero_armor_designs", "Legendary Hero Cuirass",
     "legendary_hero_cuirass", "cuirass", 5, 192, "plate", 5, "legendary"),
    ("Eight_refined_knightly_torso_armor_designs", "Knightly Torso Armor",
     "knightly_torso_armor", "cuirass", 5, 200, "mail", 3, ""),
    ("Militia_torso_armor_concept_sheet", "Militia Torso Armor",
     "militia_torso_armor", "cuirass", 5, 208, "mail", 1, ""),
    ("Eloria_Arcane_Armor_Design_Sheet", "Eloria Arcane Armor",
     "eloria_arcane_armor", "cuirass", 5, 216, "plate", 4, "arcane"),
    ("Eight_leather_ranger_torso_designs", "Leather Ranger Torso",
     "leather_ranger_torso", "cuirass", 5, 224, "leather", 2, ""),
    ("Eight_Eloria_frontier_shirt_designs", "Eloria Frontier Shirt",
     "eloria_frontier_shirt", "shirt", 5, 232, "cloth", 1, ""),
    ("Sunmane_Steppe_Shirts_and_Armor", "Sunmane Steppe Shirt",
     "sunmane_steppe_shirt", "shirt", 5, 240, "cloth", 1, ""),

    ("Eight_legendary_fantasy_leg_armor_designs", "Legendary Leg Armor",
     "legendary_leg_armor", "legs", 4, 195, "plate", 5, "legendary"),
    # Both "greaves" sets are foot armour, not leg armour: the medieval militia
    # sheet is a pair of buckled boots and the refined knightly sheet is plate
    # greaves with sabatons over the foot (their leg counterparts are Militia
    # Leg Armor and Ceremonial Knight Greaves, which stay part 4).  Filed as
    # legs they stretched a boot up the whole thigh and sorted under Legs in
    # storage; boots/part 6 fits the foot region and lands them under Feet.
    # Visuals move into the free foot range above the six boot sheets (which
    # end at 239) rather than colliding inside part 4's occupied 200-215.
    ("Eight_Refined_Knightly_Greave_Designs", "Knightly Greaves",
     "knightly_greaves", "boots", 6, 240, "mail", 3, ""),
    ("Eight_medieval_militia_greaves", "Militia Greaves",
     "militia_greaves", "boots", 6, 248, "mail", 1, ""),
    ("Eloria_Militia_Leg_Armor_Variants", "Militia Leg Armor",
     "militia_leg_armor", "legs", 4, 219, "mail", 1, ""),
    ("Eight_rugged_ranger_legwear_designs", "Rugged Ranger Legwear",
     "rugged_ranger_legwear", "legs", 4, 227, "leather", 2, ""),
    ("Sunmane_Steppe_Legwear_Concept_Sheet", "Sunmane Steppe Legwear",
     "sunmane_steppe_legwear", "legs", 4, 235, "leather", 2, ""),
    ("Eight_Humble_Frontier_Pants_Designs", "Humble Frontier Pants",
     "humble_frontier_pants", "pants", 4, 243, "cloth", 1, ""),

    ("Legendary_Eloria_Fantasy_Boots_Concept_Sheet", "Legendary Eloria Boots",
     "legendary_eloria_boots", "boots", 6, 208, "plate", 5, "legendary"),
    ("Eight_Sunmane_Steppe_Boot_Designs", "Sunmane Steppe Boots",
     "sunmane_steppe_boots", "boots", 6, 216, "leather", 2, ""),
    ("Eight_frontier_boot_designs", "Frontier Boots",
     "frontier_boots", "boots", 6, 224, "leather", 1, ""),
    ("Eight_leather_adventurer_boot_designs", "Leather Adventurer Boots",
     "leather_adventurer_boots", "boots", 6, 232, "leather", 2, ""),
]

#: Sheets added after the block above was closed.  Same row shape, numbered
#: from ``LATER_ITEM_ID``/``LATER_IMAGE_ID`` -- see the note on those for why
#: they cannot simply carry on the count.
LATER_SHEETS = [
    # The feet the legendary leg armour was generated wearing, split off by
    # `trim_generated_boots.py` rather than thrown away: they are the only
    # armoured boots in the set drawn to match one specific pair of legs.  They
    # take the parent sheet's plate finish, tier and theme because they were
    # drawn as part of it.
    #
    # Part 6 has no high ground left -- 192-255 is the six boot sheets plus the
    # two greaves sets that moved into it -- so this takes the gap the server
    # leaves between its authored culture boots, which end at 106, and its next
    # block at 128.  Checked the way part 4's block was, because the client
    # registry alone is not enough: walking `equipment_visual` over the whole
    # item table emits nothing under 192, no `6:` key in the registry is under
    # 192, and the two paths that answer for a byte nobody equipped -- the
    # `visuals.get(6, look["boots"])` appearance fallback and the derived feet
    # visuals -- reach 14.  107-114 is clear on all four, and leaves 115-127.
    ("Eight_legendary_fantasy_sabatons", "Legendary Sabatons",
     "legendary_sabatons", "boots", 6, 107, "plate", 5, "legendary"),
]


#: Sheets whose meshes were deliberately cut short of the region they belong to,
#: and the span they should be seated against instead.  `conform_equipment`
#: sizes a piece to the region's own span, which is right for a design drawn
#: over the whole of it; a leg piece that `trim_generated_boots` hemmed at the
#: boot's rim covers the waist down to 0.320 and no further, and seated against
#: the region it would simply be stretched back over the ankle it was cut away
#: from, putting its knee where the calf goes and undoing the trim.
SHEET_SPAN = {
    "legendary_leg_armor": (0.320, ce.SPAN["legs"][1]),
}


class Piece:
    __slots__ = ("source", "slug", "name", "kind", "part", "visual", "finish",
                 "item_id", "image_id", "tier", "theme")

    def __init__(self, source, slug, name, kind, part, visual, finish,
                 item_id, image_id, tier, theme):
        self.source, self.slug, self.name = source, slug, name
        self.kind, self.part, self.visual = kind, part, visual
        self.finish, self.item_id, self.image_id = finish, item_id, image_id
        self.tier, self.theme = tier, theme


def roster() -> list[Piece]:
    """Every generated piece, in a fixed order so ids never move."""
    pieces: list[Piece] = []
    for rows, first_item, first_image in (
            (SHEETS, FIRST_ITEM_ID, FIRST_IMAGE_ID),
            (LATER_SHEETS, LATER_ITEM_ID, LATER_IMAGE_ID)):
        pieces.extend(_block(rows, first_item, first_image))
    return pieces


def _block(rows, first_item: int, first_image: int) -> list[Piece]:
    """One run of sheets, numbered from its own pair of bases."""
    pieces: list[Piece] = []
    item_id = first_item
    for stem, label, slug, kind, part, first_visual, finish, tier, theme in rows:
        sources = sorted(GENERATED.glob(stem + "__*.glb"))
        # Only sources that have been through the preprocessing pass (which
        # leaves the raw meshy export beside them as ``.glb.orig``): a raw
        # drop-in would otherwise be swept into the roster the moment it
        # lands, defining items whose icons and compressed textures do not
        # exist yet.
        ready = [s for s in sources
                 if s.with_name(s.name + ".orig").exists()]
        for skipped in (s for s in sources if s not in ready):
            print("  %s has no .orig sibling (unprocessed) -- skipped"
                  % skipped.name)
        for index, source in enumerate(ready):
            if index >= len(ROMAN):
                print("  more than %d in %s, skipping %s"
                      % (len(ROMAN), stem, source.name))
                continue
            pieces.append(Piece(
                source, "%s_%02d" % (slug, index + 1),
                piece_name(slug, index, label), kind, part,
                first_visual + index, finish, item_id,
                first_image + (item_id - first_item), tier, theme))
            item_id += 1
    return pieces


#: The lines of an [item] block this tool decides. Everything else in a block
#: -- emu, armor, defense, any other stat -- is a number somebody balances,
#: and is carried across a rewrite rather than recomputed. See `served_stats`.
AUTHORED_KEYS = ("name", "item_id", "image_id", "flags", "category",
                 "description", "equip_type")


def served_stats(items_text: str) -> dict[int, list[str]]:
    """The stat lines each item_id already has in the catalogue.

    `finish_stats` decides what a piece is worth the FIRST time it is defined.
    After that the number belongs to whoever balances it -- through
    dev-server/tools/import_equipment_csv.py, which writes these same lines --
    so a rewrite re-emits what it finds instead of computing over the top of
    it. Without this, running the tool for any other reason (a rename, a new
    sheet) silently reverts every balance pass, and the diff looks exactly
    like the rewrite doing its job.

    The consequence, and it is the whole cost of this: editing a tier in
    SHEETS no longer moves a piece that is already served. `--reseed` is the
    way back, and it says what it is discarding.
    """
    stats: dict[int, list[str]] = {}
    for chunk in items_text.split("[item]")[1:]:
        block = chunk.split("[/item]", 1)[0]
        fields, kept = {}, []
        for line in block.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key = key.strip()
            fields[key] = value.strip()
            if key not in AUTHORED_KEYS:
                kept.append(line.strip())
        if "item_id" in fields:
            stats[int(fields["item_id"])] = kept
    return stats


def item_block(piece: Piece, served: dict[int, list[str]] | None = None) -> str:
    slot = {3: "head", 4: "legs", 5: "body", 6: "feet"}[piece.part]
    kept = (served or {}).get(piece.item_id)
    if kept is None:
        # The first time this piece is defined, and only then: seed it from
        # its finish, slot and tier. Every later run keeps what it finds.
        emu, (low, high), defense, extras = finish_stats(
            piece.finish, piece.part, piece.tier, piece.theme)
        kept = ["emu: %d" % emu, "armor: %d/%d" % (low, high)]
        if defense:
            kept.append("defense: %d" % defense)
        kept.extend("%s: %d" % (key, value) for key, value in extras if value)
    # emu sits above the authored middle of a block and the stats below it,
    # which is the order every existing entry is written in.
    weight = [line for line in kept if line.startswith("emu:")]
    lines = ["", "[item]",
             "name: %s" % piece.name,
             "item_id: %d" % piece.item_id,
             "image_id: %d" % piece.image_id]
    lines.extend(weight)
    lines.extend(["flags: 2", "category: Armor",
                  "description: Generated from the %s concept sheet."
                  % piece.source.stem.split("__")[0].replace("_", " ").strip(),
                  "equip_type: %s" % slot])
    lines.extend(line for line in kept if not line.startswith("emu:"))
    lines.append("[/item]")
    return "\n".join(lines)


def fence(text: str, opener: str, closer: str, body: str) -> str:
    """Replace a marked block, or add one at the end if there is none yet."""
    block = "%s\n%s\n%s" % (opener, body, closer)
    pattern = re.compile("%s.*?%s" % (re.escape(opener), re.escape(closer)),
                         re.S)
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    return text.rstrip("\n") + "\n\n" + block + "\n"


def shipped_as_human_fit(registry: dict, piece) -> bool:
    """True when the piece's base scene is its canonical_human_male fit.

    That is every installed generated piece since the P7 cleanup (2026-10):
    its old-male equipment/<slug>.glb is deleted and nothing names it.
    """
    model = registry.get("models", {}).get(
        "%d:%d" % (piece.part, piece.visual), {})
    human = model.get("variants", {}).get("canonical_human_male", {})
    return bool(human) and model.get("scene") == human.get("scene")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="build the generated armour set and define it on both sides")
    ap.add_argument("--race", default="luminous_male")
    ap.add_argument("--sheet", default=None,
                    help="only pieces whose slug starts with this")
    ap.add_argument("--server", type=Path, default=SERVER,
                    help="dev-server checkout to write the item definitions "
                         "into (a worktree, say); default the sibling one")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reseed", action="store_true",
                    help="recompute every stat from finish, slot and tier "
                         "instead of keeping what the catalogue has. This "
                         "discards balancing done through "
                         "import_equipment_csv.py, so it is never what a "
                         "rename or a new sheet wants")
    ap.add_argument("--skip-build", action="store_true",
                    help="rewrite the definitions without rebuilding meshes")
    ap.add_argument("--meshes-only", action="store_true",
                    help="rebuild meshes and leave every definition alone: "
                         "the item stats belong to whoever balances them, and "
                         "a refit has no business restating them")
    ap.add_argument("--build-dir", type=Path, default=None,
                    help="with --meshes-only: build into this scratch folder "
                         "instead of the client's equipment/, including the "
                         "installed pieces whose shipped base is their Human "
                         "fit (which are otherwise not rebuilt)")
    args = ap.parse_args()
    if args.build_dir is not None:
        if not args.meshes_only:
            ap.error("--build-dir builds scratch meshes; it needs --meshes-only")
        if args.build_dir.resolve().is_relative_to(CLIENT.resolve()):
            ap.error("--build-dir is a scratch folder, not inside the client")
    items_path = args.server / "config/eloria/items.txt"
    items_py_path = args.server / "eloria/items.py"

    if not GENERATED.is_dir():
        print("no generated meshes at %s" % GENERATED)
        return 2
    pieces = [p for p in roster()
              if not args.sheet or p.slug.startswith(args.sheet)]
    if not pieces:
        print("nothing matched")
        return 2

    by_part: dict[int, int] = {}
    for piece in pieces:
        by_part[piece.part] = by_part.get(piece.part, 0) + 1
    print("%d piece(s): %s" % (len(pieces), ", ".join(
        "part %d x%d" % (part, count) for part, count in sorted(by_part.items()))))
    if args.dry_run:
        for piece in pieces:
            print("  %-34s %-9s part %d visual %-4d item %d icon %d"
                  % (piece.slug, piece.kind, piece.part, piece.visual,
                     piece.item_id, piece.image_id))
        print("\nnothing written (--dry-run)")
        return 0

    race_path = ce.RACES / ("%s.glb" % args.race)
    rig = ea.load_rig(race_path, ce.BODY_MESH)
    built, failed = 0, 0
    build_dir = args.build_dir or EQUIPMENT
    shipped = json.loads(REGISTRY.read_text(encoding="utf-8"))
    refused = [] if args.build_dir else [
        piece.slug for piece in pieces if shipped_as_human_fit(shipped, piece)]
    if not args.skip_build:
        build_dir.mkdir(parents=True, exist_ok=True)
        for piece in pieces:
            if piece.slug in refused:
                continue
            target = build_dir / ("%s.glb" % piece.slug)
            try:
                span = next((value for slug, value in SHEET_SPAN.items()
                             if piece.slug.startswith(slug)), None)
                info = ce.build(piece.source, target, rig, piece.kind,
                                piece.name, span=span)
            except Exception as exc:                    # noqa: BLE001
                print("  FAILED %-32s %s" % (piece.slug, exc))
                failed += 1
                continue
            built += 1
            posed = []
            for step in info.get("repose", []):
                if step.get("applied"):
                    posed.append("%s %+.0f" % (step["limb"].split("_")[0][0]
                                               + step["limb"][-1],
                                               step.get("poseDeg", 0.0)))
            print("  %-34s %-7s %5d verts  %.2f MB  %s"
                  % (piece.slug, info.get("attach", "skinned"),
                     info["vertices"], info["bytes"] / 1e6,
                     "pose " + " ".join(posed) if posed else ""))

    if refused and not args.skip_build:
        print("\n%d piece(s) not rebuilt: each ships its Human fit "
              "(base scene variants/human_male/<slug>.glb), and the old-male "
              "equipment/<slug>.glb built here was retired in P7 (2026-10).\n"
              "  refit them: refit_human_bodies.py, then "
              "install_human_equipment.py and share_human_equipment_textures.py\n"
              "  or inspect: --meshes-only --build-dir <scratch>" % len(refused))
    if args.meshes_only:
        print("\nmeshes only: %d built, %d failed -- registry, items and "
              "visuals left untouched" % (built, failed))
        if failed:
            return 1
        return 2 if refused and not built else 0

    # Definitions always cover the WHOLE roster: --sheet narrows which
    # meshes rebuild, but the fences are rewritten whole, and writing them
    # from the filtered list silently drops every other piece's item.
    everyone = roster()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for piece in everyone:
        entry = {"scene": "res://assets/actors/native/equipment/%s.glb"
                          % piece.slug,
                 "name": piece.name}
        if piece.kind in ea.GARMENT_KINDS:
            entry["attach"] = "skinned"
            entry["skinRegion"] = ea.garment_region(piece.kind)
            entry["kind"] = piece.kind
            entry["authoredFor"] = args.race
        else:
            entry["attach"] = "socket"
            if piece.part == 3:
                entry["hides"] = list(ea.PARTS[3]["hides"])
        # Merge, never replace: the fitted variants (install_human_equipment,
        # refit_race_headwear), the race feature/shoulder policy, sockets and
        # profiles belong to later tools.  Since the race programme's P7
        # cleanup (2026-10) an installed piece's base IS its canonical_human_male
        # fit and the old-male equipment/<slug>.glb is gone, so such a base
        # keeps its scene/authoredFor/fitProfile/socket; a rebuilt
        # equipment/<slug>.glb only becomes the base of a new piece.
        key = "%d:%d" % (piece.part, piece.visual)
        old = registry["models"].get(key, {})
        merged = dict(old)
        merged.update(entry)
        if shipped_as_human_fit(registry, piece):
            for field in ("scene", "authoredFor", "fitProfile", "socket"):
                if field in old:
                    merged[field] = old[field]
        registry["models"][key] = merged
    # A piece that changes part or visual -- a slot correction, say -- leaves
    # its old "part:visual" key behind still pointing at its mesh, which now
    # holds the rebuilt geometry: a stale key hands a boot to the leg slot, and
    # the leg-seam fixtures read it as legwear and fail.  Drop any key that
    # names one of our own slugs but is not that slug's current key; authored
    # models under other slugs are never one of our slugs, so they are untouched.
    current_keys = {"%d:%d" % (piece.part, piece.visual) for piece in everyone}
    our_slugs = {piece.slug for piece in everyone}
    for key in [key for key, entry in registry["models"].items()
                if Path(str(entry.get("scene", ""))).stem in our_slugs
                and key not in current_keys]:
        del registry["models"][key]
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n",
                        encoding="utf-8")

    items = items_path.read_text(encoding="utf-8")
    served = {} if args.reseed else served_stats(items)
    if args.reseed:
        print("--reseed: %d piece(s) go back to their computed stats, "
              "discarding any balancing done in the catalogue" % len(everyone))
    body = "\n".join(item_block(piece, served)
                    for piece in everyone).lstrip("\n")
    items_path.write_text(fence(items, OPEN_ITEMS, CLOSE_ITEMS, body),
                          encoding="utf-8")

    source = items_py_path.read_text(encoding="utf-8")
    rows = "\n".join('    "%s": (%d, %d),'
                     % (piece.name.casefold(), piece.part, piece.visual)
                     for piece in everyone)
    if OPEN_PY in source:
        source = fence(source, OPEN_PY, CLOSE_PY, rows)
    else:
        # Into the override table itself, immediately before it closes.
        marker = '    "spauldered breastplate": (5, 183),\n}'
        if marker not in source:
            print("could not find the end of EQUIPMENT_VISUAL_OVERRIDES")
            return 2
        source = source.replace(
            marker,
            '    "spauldered breastplate": (5, 183),\n%s\n%s\n%s\n}'
            % (OPEN_PY, rows, CLOSE_PY), 1)
    items_py_path.write_text(source, encoding="utf-8")

    print("\n%d built, %d failed" % (built, failed))
    print("  meshes   %s" % build_dir)
    print("  registry %s" % REGISTRY)
    print("  items    %s" % items_path)
    print("  visuals  %s" % items_py_path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
