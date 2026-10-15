#!/usr/bin/env python3
"""Take the generated weapon and shield set into the client and the server.

Added 2026-09-02 for Eloria Client.

The sibling of ``import_generated_equipment`` for the things you hold rather
than wear.  Same four records, joined by the item's name --

  the mesh          godot-client/assets/actors/native/equipment/<slug>.glb
  the client entry  godot-client/data/actors/equipment.json, models["part:id"]
  the server item   dev-server/config/eloria/items.txt, an [item] block
  the server visual dev-server/eloria/items.py, EQUIPMENT_VISUAL_OVERRIDES

-- and the same rule that a set added to one side and not the other is either
a weapon that draws nothing or geometry nobody can hold.

Two things differ from the armour.  A prop is never skinned: parts 0 and 1
hang off ``hand_r`` and ``hand_l``, so these are plain static meshes and the
socket's own rotation lays them into the grip.  And a prop is not sized from
the body -- a sword is as long as a sword whoever swings it -- so each class
carries its own length, taken off the authored props in
``conform_equipment.PROP_KIND``.

``flip`` and ``roll`` are per item and are the two things that cannot be
derived.  Nothing in a mesh says which end is the tip: a guard is the widest
part of a sword and sits low, an axe head is the widest part of an axe and sits
high.  Nothing says which way a curved head hooks either.  Both are set by
looking at a render, the way lowpoly_rigged/models.json sets a donor's facing.

  python import_generated_weapons.py             build and write
  python import_generated_weapons.py --dry-run
  python import_generated_weapons.py --only sword
  python import_generated_weapons.py --only sword --skip-build --regrip

Each held weapon's grips are solved against every playable body and the
class kits (``held_grips``), which takes the best part of an hour for the set,
so they are cached by a digest of what they are solved from (``GRIP_CACHE``)
and a run with ``--only`` keeps the grips the other pieces already have.
``--regrip`` solves every piece afresh.

Idempotent, like its sibling: the server blocks are marker-fenced and rewritten
whole, the client entries merged into the registry by key.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

import conform_equipment as ce
import equipment_authoring as ea
import import_generated_equipment as armour

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
PROJECT = HERE.parent.parent.parent
GENERATED = PROJECT / "generate_models" / "meshy-weapons-glb"


def _server_beside(client: Path) -> Path:
    """The server checkout that belongs with this client checkout.

    Both halves of a wearable have to be written together, and this tool is
    meant to be run from a worktree -- so defaulting to ``dev-server`` writes
    a worktree's definitions into the main repository, which is exactly the
    mistake this exists to stop.  A worktree at ``wt-<name>`` pairs with
    ``wt-<name>-server`` beside it; anything else falls back to the main
    checkout.  ``--server`` overrides either way.
    """
    paired = client.parent.parent / (client.parent.name + "-server")
    return paired if paired.is_dir() else PROJECT / "dev-server"


SERVER = _server_beside(CLIENT)

EQUIPMENT = CLIENT / "assets/actors/native/equipment"
REGISTRY = CLIENT / "data/actors/equipment.json"

OPEN_ITEMS = "# --- generated weapon set (tools/import_generated_weapons.py) ---"
CLOSE_ITEMS = "# --- end generated weapon set ---"
OPEN_PY = "    # --- generated weapon set (eloria-assets/tools/import_generated_weapons.py) ---"
CLOSE_PY = "    # --- end generated weapon set ---"

#: After the armour set, which ends at 1529.
FIRST_ITEM_ID = 1530

#: After the armour set's icons, which end at 373.
FIRST_IMAGE_ID = 374

#: Where each part's visuals start.  Every legacy weapon and shield model was
#: taken out of the registry when the generated armour became the only
#: equipment, but the ids are left alone above what the legacy set reached
#: (weapon 113, shield 105) so restoring those models could not collide.
FIRST_VISUAL = {0: 114, 1: 106}

#: Part 1 is not "the shield" but "the left hand", and since Two Handed
#: Wielding opened the second hand it holds a weapon as readily as a shield.
#: A one-handed weapon therefore has a second visual, in a bank of its own
#: above the shields, drawing the same mesh from ``hand_l``.  It is the
#: weapon's own visual moved into that bank rather than a number allocated
#: beside it, so the two can never drift apart and a weapon added later gets
#: its off-hand id for free.  The top of the bank is 160 + 79 = 239, inside
#: the single byte the enhanced-actor packet carries a part in.
FIRST_OFFHAND_VISUAL = 160


def offhand_visual(visual: int) -> int:
    """The part-1 visual that draws part-0 ``visual`` in the left hand."""
    return FIRST_OFFHAND_VISUAL + visual - FIRST_VISUAL[0]

#: emu, damage low/high, accuracy, defense for the weapon classes; emu, armour
#: low/high, defense, accuracy for the shields.  The scale is Eternal Lands'
#: (damage in the single digits to the twenties, modifiers a few points either
#: way), and the classes divide it the way EL's families do: one-handed
#: weapons pay for their free shield hand with modest damage, two-handed
#: weapons hit hardest in their own specialty and pay for it somewhere else --
#: a greatsword swings past your own guard (defense), a maul is slow to line
#: up (accuracy), a polearm keeps its point between you and the enemy
#: (defense bonus) but is clumsy up close (accuracy).
WEAPON_STATS = {
    "dagger": (3, (2, 6), 3, 0),
    "sword": (8, (4, 11), 2, 1),
    "axe": (9, (5, 13), 0, 0),
    "mace": (8, (4, 12), 1, 0),
    "wand": (2, (2, 5), 2, 0),
    "thrown": (2, (3, 8), 2, 0),
    "fist": (4, (3, 8), 2, 1),
    "whip": (6, (4, 10), 1, 0),
    # Two-handed: the specialty is strong and the trade-off is explicit.
    "greatsword": (16, (10, 22), -1, -2),
    "greataxe": (15, (12, 24), -2, -3),
    "maul": (17, (11, 25), -3, -3),
    "spear": (11, (7, 16), 1, 1),
    "polearm": (14, (9, 20), -1, 2),
    "staff": (7, (4, 10), 0, 3),
    "bow": (6, (6, 16), 2, -2),
    "crossbow": (10, (9, 20), 1, -2),
}

#: Extra swing weight behind a true two-handed blow: crits land harder.  Reach
#: classes (spear, polearm, staff) and aimed classes (bow, crossbow) already
#: take their benefit as defense or accuracy instead.
TWO_HANDED_CRIT = {"greatsword": 3, "greataxe": 4, "maul": 5}

SHIELD_STATS = {
    "shield": (10, (2, 7), 2, 0),
    "greatshield": (16, (4, 11), 3, -1),
}

#: Which classes loose ammunition rather than swing.  The item declares the
#: class it fires so eloria's own catalogue arms the ranging tables without an
#: entry in the shared Eternal Lands ones (eloria/ranging.py).
AMMUNITION_OF = {"bow": "arrow", "crossbow": "bolt"}


def missile_speed(kind: str, tier: int) -> int:
    """EL firing-speed values: reload is (40 - speed)/10 seconds.

    The trade follows the Eternal Lands bow ladder: the harder a launcher
    hits (tier), the slower it cycles, and a crossbow always cycles slower
    than a bow of its rank.
    """
    if kind == "bow":
        return 30 - 2 * tier
    if kind == "crossbow":
        return 24 - tier
    return 0

#: Design tiers.  2 is honest regional work and the default; 1 is militia and
#: frontier kit; 3 is knightly or otherwise refined; 4 is arcane or exotic
#: mechanism; 5 is the named relics.  Rarer is better: the tier widens the
#: damage range, and from tier 4 the piece picks up a point of accuracy.
DEFAULT_TIER = 2
TIERS = {
    "001_militia_arming_sword": 1,
    "003_frontier_cutlass": 1,
    "011_woodsmans_hatchet": 1,
    "021_militia_short_spear": 1,
    "022_throwing_javelin": 1,
    "041_militia_pike": 1,
    "046_iron_sledgehammer": 1,
    "049_studded_frontier_club": 1,
    "050_fighting_quarterstaff": 1,
    "061_wooden_round_shield": 1,
    "040_frontier_voulge": 1,
    "075_frontier_barricade_shield": 1,
    "002_knightly_cavalry_sword": 3,
    "010_swept_hilt_rapier": 3,
    "013_knightly_battle_axe": 3,
    "018_chain_morningstar": 3,
    "024_knightly_boar_spear": 3,
    "025_hooked_dueling_spear": 3,
    "031_knightly_greatsword": 3,
    "032_highland_claymore": 3,
    "033_flamberge_zweihander": 3,
    "034_executioners_sword": 3,
    "036_classic_halberd": 3,
    "038_knightly_poleaxe": 3,
    "047_lucerne_hammer": 3,
    "048_knightly_great_maul": 3,
    "053_siege_great_crossbow": 3,
    "059_knightly_relic_banner_spear": 4,
    "062_steel_rimmed_heater_shield": 3,
    "063_norman_kite_shield": 3,
    "065_rectangular_tower_shield": 3,
    "066_crossbowmans_pavise": 3,
    "068_legionary_scutum": 3,
    "070_long_dueling_shield": 3,
    "071_knightly_lion_shield": 3,
    "020_arcane_crystal_cudgel": 4,
    "029_arcane_focus_wand": 4,
    "030_crescent_spellblade_sickle": 4,
    "035_arcane_flame_greatblade": 4,
    "054_clockwork_repeating_arbalest": 4,
    "055_alchemical_hand_cannon": 4,
    "056_arcane_double_staff": 4,
    "057_amberwood_branch_bowblade": 4,
    "058_sunmane_twin_crescent_glaive": 4,
    "060_storm_tuning_fork_spear": 4,
    "069_mechanical_lantern_shield": 4,
    "074_arcane_crystal_shield": 4,
    "076_polished_mirror_shield": 4,
    "077_dragon_scale_shield": 4,
    "078_ice_crystal_shield": 4,
    "079_molten_forge_shield": 4,
    "080_thorned_root_shield": 4,
    "081_segmented_whip_sword": 4,
    "084_lantern_flail": 4,
    "086_double_ended_twinblade": 4,
    "087_circular_ringblade": 4,
    "090_folding_crescent_bow": 4,
    "091_rune_battle_gauntlet": 4,
    "092_alchemist_cannon": 4,
    "093_crystal_prism_staff": 4,
    "094_clockwork_saw_lance": 4,
    "088_polarity_war_hammer": 5,
    "089_gravity_anchor_weapon": 5,
    "095_living_vine_bow": 5,
    "096_phoenix_feather_spear": 5,
    "097_void_glass_greatblade": 5,
    "098_radiant_sun_disc_chakram": 5,
    "099_echo_bell_hammer": 5,
    "100_stormglass_shield_spear": 5,
}

#: Elemental and warding character read off the design itself, stated per stem
#: so a piece's flavour is a decision rather than a substring accident.
THEME_STATS = {
    "020_arcane_crystal_cudgel": (("magic_damage", 2),),
    "029_arcane_focus_wand": (("magic_damage", 2), ("max_ether", 4)),
    "030_crescent_spellblade_sickle": (("magic_damage", 2),),
    "035_arcane_flame_greatblade": (("heat_damage", 3),),
    "056_arcane_double_staff": (("magic_damage", 2), ("max_ether", 6)),
    "060_storm_tuning_fork_spear": (("magic_damage", 2),),
    "074_arcane_crystal_shield": (("magic_protection", 3),),
    "076_polished_mirror_shield": (("magic_protection", 2),),
    "077_dragon_scale_shield": (("heat_protection", 3),),
    "078_ice_crystal_shield": (("cold_protection", 3),),
    "079_molten_forge_shield": (("heat_protection", 3),),
    "080_thorned_root_shield": (("critical_to_damage", 1),),
    "088_polarity_war_hammer": (("magic_damage", 3),),
    "089_gravity_anchor_weapon": (("critical_to_damage", 2),),
    "093_crystal_prism_staff": (("magic_damage", 3), ("max_ether", 8)),
    "095_living_vine_bow": (("perception_bonus", 2),),
    "096_phoenix_feather_spear": (("heat_damage", 3),),
    "097_void_glass_greatblade": (("magic_damage", 4),),
    "098_radiant_sun_disc_chakram": (("heat_damage", 2),),
    "099_echo_bell_hammer": (("magic_damage", 2), ("critical_to_hit", 2)),
    "100_stormglass_shield_spear": (("magic_damage", 2), ("magic_protection", 2)),
}

#: Which classes are held in one hand.  ``both_hands`` is a weapon slot on the
#: server (WEAPON_WEAR_EQUIP_TYPES) even though the legacy catalogue also hangs
#: gloves off it, so a two-hander is honest to declare there.
ONE_HANDED = {"dagger", "sword", "axe", "mace", "wand", "thrown", "fist",
              "whip"}

#: stem -> (label, kind).  The stems are the concept art's own file names, so
#: this table is the one place a piece's class is decided.  Order here is the
#: order ids are handed out in, and it follows the art's numbering.
DESIGNS = [
    ("001_militia_arming_sword", "Militia Arming Sword", "sword"),
    ("002_knightly_cavalry_sword", "Knightly Cavalry Sword", "sword"),
    ("003_frontier_cutlass", "Frontier Cutlass", "sword"),
    ("004_amberwood_leafblade", "Amberwood Leafblade", "sword"),
    ("005_sunmane_steppe_saber", "Sunmane Steppe Saber", "sword"),
    ("006_rondel_dagger", "Rondel Dagger", "dagger"),
    ("007_ring_guard_parrying_dagger", "Ring Guard Parrying Dagger", "dagger"),
    ("008_gladius", "Gladius", "sword"),
    ("009_heavy_falchion", "Heavy Falchion", "sword"),
    ("010_swept_hilt_rapier", "Swept Hilt Rapier", "sword"),
    ("011_woodsmans_hatchet", "Woodsman's Hatchet", "axe"),
    ("012_bearded_raider_axe", "Bearded Raider Axe", "axe"),
    ("013_knightly_battle_axe", "Knightly Battle Axe", "axe"),
    ("014_sunmane_crescent_axe", "Sunmane Crescent Axe", "axe"),
    ("015_amberwood_tomahawk", "Amberwood Tomahawk", "axe"),
    ("016_flanged_mace", "Flanged Mace", "mace"),
    ("017_war_hammer", "War Hammer", "mace"),
    ("018_chain_morningstar", "Chain Morningstar", "mace"),
    ("019_blacksmith_maul", "Blacksmith Maul", "maul"),
    ("020_arcane_crystal_cudgel", "Arcane Crystal Cudgel", "mace"),
    ("021_militia_short_spear", "Militia Short Spear", "spear"),
    ("022_throwing_javelin", "Throwing Javelin", "spear"),
    ("023_mariners_trident", "Mariner's Trident", "spear"),
    ("024_knightly_boar_spear", "Knightly Boar Spear", "spear"),
    ("025_hooked_dueling_spear", "Hooked Dueling Spear", "spear"),
    ("026_frontier_hand_crossbow", "Frontier Hand Crossbow", "crossbow"),
    ("027_throwing_knife_fan", "Throwing Knife Fan", "thrown"),
    ("028_engraved_war_chakram", "Engraved War Chakram", "thrown"),
    ("029_arcane_focus_wand", "Arcane Focus Wand", "wand"),
    ("030_crescent_spellblade_sickle", "Crescent Spellblade Sickle", "sword"),
    ("031_knightly_greatsword", "Knightly Greatsword", "greatsword"),
    ("032_highland_claymore", "Highland Claymore", "greatsword"),
    ("033_flamberge_zweihander", "Flamberge Zweihander", "greatsword"),
    ("034_executioners_sword", "Executioner's Sword", "greatsword"),
    ("035_arcane_flame_greatblade", "Arcane Flame Greatblade", "greatsword"),
    ("036_classic_halberd", "Classic Halberd", "polearm"),
    ("037_single_edged_glaive", "Single Edged Glaive", "polearm"),
    ("038_knightly_poleaxe", "Knightly Poleaxe", "polearm"),
    ("039_steppe_bardiche", "Steppe Bardiche", "polearm"),
    ("040_frontier_voulge", "Frontier Voulge", "polearm"),
    ("041_militia_pike", "Militia Pike", "polearm"),
    ("042_forged_war_scythe", "Forged War Scythe", "polearm"),
    ("043_three_pronged_ranseur", "Three Pronged Ranseur", "polearm"),
    ("044_winged_partisan", "Winged Partisan", "polearm"),
    ("045_heavy_boar_spear", "Heavy Boar Spear", "spear"),
    ("046_iron_sledgehammer", "Iron Sledgehammer", "maul"),
    ("047_lucerne_hammer", "Lucerne Hammer", "polearm"),
    ("048_knightly_great_maul", "Knightly Great Maul", "maul"),
    ("049_studded_frontier_club", "Studded Frontier Club", "mace"),
    ("050_fighting_quarterstaff", "Fighting Quarterstaff", "staff"),
    # Not "Amberwood Longbow": the authored prop of that name is already in the
    # catalogue, and the item's name is the only thing joining a definition to
    # its geometry, so two of them resolve to one another's models.
    ("051_amberwood_longbow", "Amberwood Yew Longbow", "bow"),
    ("052_sunmane_recurve_bow", "Sunmane Recurve Bow", "bow"),
    ("053_siege_great_crossbow", "Siege Great Crossbow", "crossbow"),
    ("054_clockwork_repeating_arbalest", "Clockwork Repeating Arbalest",
     "crossbow"),
    ("055_alchemical_hand_cannon", "Alchemical Hand Cannon", "crossbow"),
    ("056_arcane_double_staff", "Arcane Double Staff", "staff"),
    ("057_amberwood_branch_bowblade", "Amberwood Branch Bowblade", "bow"),
    ("058_sunmane_twin_crescent_glaive", "Sunmane Twin Crescent Glaive",
     "polearm"),
    ("059_knightly_relic_banner_spear", "Knightly Relic Banner Spear",
     "polearm"),
    ("060_storm_tuning_fork_spear", "Storm Tuning Fork Spear", "spear"),

    ("061_wooden_round_shield", "Wooden Round Shield", "shield"),
    ("062_steel_rimmed_heater_shield", "Steel Rimmed Heater Shield", "shield"),
    ("063_norman_kite_shield", "Norman Kite Shield", "greatshield"),
    ("064_parrying_buckler", "Parrying Buckler", "shield"),
    ("065_rectangular_tower_shield", "Rectangular Tower Shield",
     "greatshield"),
    ("066_crossbowmans_pavise", "Crossbowman's Pavise", "greatshield"),
    ("067_reinforced_highland_targe", "Reinforced Highland Targe", "shield"),
    ("068_legionary_scutum", "Legionary Scutum", "greatshield"),
    ("069_mechanical_lantern_shield", "Mechanical Lantern Shield", "shield"),
    ("070_long_dueling_shield", "Long Dueling Shield", "greatshield"),
    ("071_knightly_lion_shield", "Knightly Lion Shield", "shield"),
    ("072_sunmane_hide_bronze_shield", "Sunmane Hide Bronze Shield", "shield"),
    ("073_amberwood_living_bark_shield", "Amberwood Living Bark Shield",
     "shield"),
    ("074_arcane_crystal_shield", "Arcane Crystal Shield", "shield"),
    ("075_frontier_barricade_shield", "Frontier Barricade Shield",
     "greatshield"),
    ("076_polished_mirror_shield", "Polished Mirror Shield", "shield"),
    ("077_dragon_scale_shield", "Dragon Scale Shield", "shield"),
    ("078_ice_crystal_shield", "Ice Crystal Shield", "shield"),
    ("079_molten_forge_shield", "Molten Forge Shield", "shield"),
    ("080_thorned_root_shield", "Thorned Root Shield", "shield"),

    ("081_segmented_whip_sword", "Segmented Whip Sword", "whip"),
    ("082_chain_sickle", "Chain Sickle", "whip"),
    ("083_bladed_war_fans", "Bladed War Fans", "fist"),
    ("084_lantern_flail", "Lantern Flail", "mace"),
    ("085_serpent_coil_whip", "Serpent Coil Whip", "whip"),
    ("086_double_ended_twinblade", "Double Ended Twinblade", "staff"),
    ("087_circular_ringblade", "Circular Ringblade", "thrown"),
    ("088_polarity_war_hammer", "Polarity War Hammer", "maul"),
    ("089_gravity_anchor_weapon", "Gravity Anchor", "maul"),
    ("090_folding_crescent_bow", "Folding Crescent Bow", "bow"),
    ("091_rune_battle_gauntlet", "Rune Battle Gauntlet", "fist"),
    ("092_alchemist_cannon", "Alchemist Cannon", "crossbow"),
    ("093_crystal_prism_staff", "Crystal Prism Staff", "staff"),
    ("094_clockwork_saw_lance", "Clockwork Saw Lance", "polearm"),
    ("095_living_vine_bow", "Living Vine Bow", "bow"),
    ("096_phoenix_feather_spear", "Phoenix Feather Spear", "spear"),
    ("097_void_glass_greatblade", "Void Glass Greatblade", "greatsword"),
    ("098_radiant_sun_disc_chakram", "Radiant Sun Disc Chakram", "thrown"),
    ("099_echo_bell_hammer", "Echo Bell Hammer", "maul"),
    ("100_stormglass_shield_spear", "Stormglass Shield Spear", "spear"),
]

#: Pieces that arrive the opposite way round to the rest of their class, which
#: turns the class default off for them as readily as on.  The art is drawn per
#: piece and not to a rule, so a class default is only ever a majority: the
#: greatswords come out blade down like every other blade, except this one.
#: Each line is settled by looking at a render.
FLIP_EXCEPTIONS = {
    # Arrives crescent up, where the blades arrive point down: turning it with
    # its class buried the grip and stood the crescent on the floor, so the
    # fist closed on the flat of the blade with the haft out behind it.
    "030_crescent_spellblade_sickle",
    # The chained anchor arrives head down, with its wrapped handle at +Y.
    "089_gravity_anchor_weapon",
    "097_void_glass_greatblade",
}

#: Pieces that sit in the hand the right way up but face the wrong way about
#: their own haft.  End-for-end cannot reach this: a crescent is drawn hooking
#: one way, and which way that is decides whether the edge falls above the fist
#: or below it.  Settled by looking at a render, like the flip.
ROLL_EXCEPTIONS = {
    # Rides edge up otherwise, where a sickle is carried hooking down.
    "030_crescent_spellblade_sickle",
}

#: Grip centres in source-mesh coordinates for props whose handles cannot be
#: found from the class's length fraction and cross-section bounds.
GRIP_POINTS = {
    # The wrapped bar sits beside a returning chain; centring both would put
    # the socket in the gap instead of inside the handle.
    "089_gravity_anchor_weapon": (0.095, 0.34, 0.0),
}

#: How a prop is laid into the hand, as a socket this set overrides the shared
#: part socket with.  The runtime already allows that -- it is how a two-handed
#: haft rides differently from a one-handed hilt on the same bone -- so the
#: authored props keep the part socket they were built against.
#:
#: Modified 2026-10-06 for Eloria Client.  A weapon used to be held one way in
#: every clip: stood up in the idle hand by ``upright_grip_basis`` and leaned a
#: right angle forward.  That one way had to serve two hands that are nothing
#: alike -- the fist the combat idle and every swing close round the hilt, and
#: the open hand of the standing idle hanging by the thigh -- and it served
#: neither.  It was solved before the library idle changed (2026-09-07), so in
#: the idle the client stands in every blade pointed forward like a lance, 32
#: degrees out to the right; and no single rotation can be right for both,
#: because the blade that hangs down the leg at ease is the blade that the
#: wind-up of Combat_Slash_A buries 0.4 m in the floor.  So a held weapon now
#: carries two grips, both solved here from the piece itself:
#:
#:   socket       the fighting grip, the one the fist was animated around --
#:                ``fighting_grip``
#:   idleSocket   how it is held at ease, which WeaponCarryPose blends to while
#:                the actor idles or turns on the spot (which is also what the
#:                creation screen plays) -- ``idle_grip``
#:
#: and walking and running keep pointing it ahead through WeaponCarryPose, as
#: they did before.  "idleSocket" rather than "restSocket": everything else in
#: the registry and the runtime that says rest means the bone rest the socket is
#: resolved through.

#: The clip both grips are fitted to.  It can only be the one the client
#: idles in (data/animations/luminous.json maps "idle" and "turn" to it), and
#: it is sampled across its whole loop, because the hand drifts a few degrees
#: over it and a planted butt drifts with it.  Every playable body shares one
#: skeleton and plays this clip unchanged, scaled whole by its model scale, so
#: a grip solved on one body is the same grip on every other.
IDLE_CLIP = "Idle_Subtle"
IDLE_SAMPLES = 12

#: Where the fist closes, as the character-space offset the class arming
#: sword's grip was reviewed at (cdd44dea5), in the legacy units the props are
#: fitted in: five centimetres into the palm from the hand bone and seven along
#: it towards the knuckles, in the tunnel the curled fingers make.  Every
#: weapon is held there -- the mesh is authored with its grip on the origin --
#: so the arming sword, the wand and a halberd all close the same fist.
FIST_OFFSET = (-0.0757, -0.05, 0.0)

#: How far up its length from the mesh origin the fist closes, for the few
#: pieces whose handle is not on the origin ``seat_prop`` gave them.  Settled
#: by looking, like the flips.
FIGHTING_HOLDS = {
    # The source origin sits below the wrapped handle.  The Warden's reviewed
    # grip (cdd44dea5) held the staff 0.099 up its length from it.
    "050_fighting_quarterstaff": .10,
}

#: The props' measurement profile.  The registry marks every held weapon
#: ``"fitProfile": "legacy"``, which sizes it by the rig's head height over
#: this profile's, and the grips are solved in the units that gives.
FIT_PROFILE = "legacy"

#: How a class is held at ease, while the open hand of the standing idle
#: hangs by the thigh with the palm towards it.
#:
#:   hang     down along the leg, the flat towards it, the tip a little
#:            forward and clear of the floor through the whole idle loop
#:   lean     longer than the hand is high, so it is let down at a slant and
#:            its tip or head rests just off the floor ahead and to the side
#:   plant    stood upright on its butt beside the foot and held where the
#:            haft meets the hand, which is wherever that leaves the butt a
#:            centimetre off the floor
#:   upright  held up out of the fist and not planted
#:   bow      stood on end beside the leg and held at its grip, as it is
#:            drawn, the upper limb leant a little ahead
#:
#: The idle socket says which (``"style"``): WeaponCarryPose keeps the floor
#: end of a planted or leant piece where it was set down.
#:
#: Modified 2026-10-06 for Eloria Client: bows hung like a blade.  A bow is
#: held at its middle, so hanging its lower limb ahead laid the upper one as
#: far back -- forty degrees, through the cape and behind the arm.
REST_STYLE = {
    "dagger": "hang", "sword": "hang", "axe": "hang", "mace": "hang",
    "wand": "hang", "thrown": "hang", "fist": "hang", "crossbow": "hang",
    "bow": "bow",
    "greatsword": "lean", "greataxe": "lean", "maul": "lean", "whip": "lean",
    "spear": "plant", "polearm": "plant", "staff": "plant",
}

#: Pieces held at ease unlike their class.  Settled by looking at a render.
REST_STYLE_EXCEPTIONS = {
    # The ball is modelled hanging on its chain down the length of the handle,
    # so turned head down the chain would stand up out of the fist.  Carried
    # handle up, the chain hangs as it is drawn.
    "018_chain_morningstar": "upright",
}

#: How far the tip of each style may come to the floor, through the whole
#: idle loop, on the body the grips are solved on.  A body drawn smaller (the
#: model scales go down to .975) shrinks the margin with everything else.
FLOOR_CLEARANCE = {"hang": .05, "lean": .02, "plant": .01, "upright": .05,
                   "bow": .05}

#: How near the rest of the piece may come to the body, its clothes or the
#: armour worn over them (``HELD_CLEARANCE_GEAR``), away from the hand that
#: holds it.
BODY_CLEARANCE = .02

#: The surfaces of a body a held piece has to clear: the skin and the clothes
#: every body is drawn in when nothing is worn over them.
HELD_CLEARANCE_SURFACES = ("body", "wardrobe_shirt", "wardrobe_pants", "wardrobe_boots")

#: And the armour worn over them, as registry keys, each worn the way the
#: client fits it to every body (``_Worn``, ``_bodies_frames``).  Modified
#: 2026-10-06 for Eloria Client: the clearance used to stop at the bare body
#: and its default clothes, trusting ``BODY_CLEARANCE`` to leave room for
#: armour, and it did not -- measured in the client, the planted spears and
#: polearms ran 3-5 cm up inside the Studded Jack's sleeve in every idle frame
#: on every race, a greatsword's hilt end went into its hem, the bowblade's
#: upper limb and the chain morningstar's handle up its sleeve, and the
#: Warden's quarterstaff into the Furtrim Coat.  So the torso, legs and boots
#: of each creation class kit are cleared as surfaces of their own: every
#: player starts in one of them, and between them they are the bulkiest a body
#: is drawn in at the shin, the hem, the sleeve and the shoulder.
#:
#: And their capes.  Modified 2026-10-06 for Eloria Client: the Vanguard and
#: the Warden each start in one, and the set stopped at the boots, so nothing
#: kept a piece out of the cape -- the bows rested with the upper limb back
#: through it, and a hand crossbow, a shield spear, the chain weapons and a
#: chakram sat 3.5-5 cm inside it.  Both kits wear the one generic cape, so
#: one fit of it clears both (``_Worn.signature``).  A cape is a sheet drawn
#: from both sides, which ``_Worn.sheet`` handles.
HELD_CLEARANCE_GEAR = (
    "4:220", "5:209", "6:249", "2:105",  # Vanguard: Leather Kneecops, Studded Jack, Banded Warboots, cape
    "4:230", "5:225", "6:226",           # Ranger: Sidelace Breeches, Scout Vest, Laced Fieldboots
    "4:185", "5:222", "6:198",           # Arcanist: Acolyte Legguards, Tunic, Boots
    "4:176", "5:189", "6:205", "2:100",  # Warden: Furtrim Legguards, Coat, Boots, cape
)

#: How finely worn armour is sampled for that.  Its shells are a few thousand
#: vertices spread over a whole boot or jacket, too far apart for a nearest-
#: vertex distance to see a haft pass between them, so each triangle is halved
#: until no edge is longer than this, leaving no point of a shell more than a
#: centimetre and a bit from a sample (``_surface_samples``).
WORN_SPACING = .02

#: Worn armour is cleared by which side of its shell a point is on, which the
#: shell's own normals say (``_Frame.clearance``): a point this far behind the
#: nearest sample of it, within ``WORN_REACH`` of it, is inside the piece --
#: a centimetre, about what the sampled shell resolves (``WORN_SPACING``).
#: Unsigned, as the body is cleared, a pommel or a butt sunk a few centimetres
#: into a jacket hem or a boot is still only a centimetre or two from the
#: nearest point of the shell -- or of the body beneath it -- and passes for
#: clear: the planted butts measured 3-5 cm inside the Banded Warboots in the
#: client while the unsigned check here had them clear of everything.  And it
#: is only being inside that counts against a piece, not coming near: the
#: margins that keep a blade off the skin would keep it a hand's width off a
#: coat that flares at the hip where the hand already rests, and nothing held
#: in that hand can do that.
WORN_INSIDE = .01
WORN_REACH = .04
WORN_AGREE = 4

#: Except round the wrist of the hand that holds the piece.  A cuff closes
#: there -- the Furtrim Coat's fur, the Acolyte Tunic's bell, which hangs a
#: hand's width up the forearm -- and a pommel or a haft run up against the
#: wrist is inside it whichever way the piece leans: measured, every slant of
#: the arming sword left its pommel 1-4 cm inside one cuff or the other, and
#: every lean of a planted spear its haft 1-3 cm inside the bell, 13-18 cm
#: from the fist.  Up the sleeve beyond this, towards the elbow -- where the
#: spears ran up the Studded Jack's -- still counts.
CUFF_REACH = .14

#: The part of a piece the holding hand itself covers, and so is not counted
#: against the body: a grip's length either side of the fist.
HELD_LENGTH = .10

#: How near the handle end behind a grip -- a pommel, a short haft's butt --
#: may come: only out of the body.  See ``_margins``.
POMMEL_CLEARANCE = .005

#: Which ways a hanging piece may lean, in degrees round from straight ahead
#: towards the holding hand's side, tried in turn.
HANG_AZIMUTHS = (0., 15., 30., 45., 60., 75., 90.)

#: And a leaning one, which rests its tip on the floor ahead of the foot and
#: a little out to the side, taking the first of these that clears: laid
#: straight ahead it reads as the lance again, only lowered, and seen from the
#: front it is end on and all but disappears.  Swung farther out, the handle
#: end above the fist swings in against the hip.
LEAN_AZIMUTHS = (30., 20., 10., 0., 45., 60.)

#: A hanging piece leans at least this far forward of straight down.  A dead
#: vertical blade reads as dropped rather than held.
MIN_HANG_TILT = 8.0

#: How far a planted haft may lean, in degrees: out to the holding hand's side
#: and ahead (negative: in, and back), tried least first.
PLANT_OUT = (-4., -2., 0., 2., 4., 6., 8., 10., 12.)
PLANT_AHEAD = (-4., -2., 0., 2., 4., 6., 8., 10., 12., 14., 16.)

#: When no slant clears everything, how much worse than the best of them one
#: may be and still be preferred for being the more natural: a centimetre,
#: about what the sampled armour can resolve (``WORN_SPACING``).  Taking the
#: best outright let a few millimetres of that noise -- a pommel touching a
#: coat at the hip whichever way the blade hangs -- swing a sword forty degrees.
FALLBACK_TOLERANCE = .01

#: Classes whose head hangs to one side of the haft, so that which side leads
#: the swing is a property of the mesh: the larger half of the head goes to the
#: knuckles in the fighting grip, where the swing strikes.  A blade is left
#: alone -- the curve of a saber or a sickle already runs the way the hand
#: closes on it (``ROLL_EXCEPTIONS`` settles the odd ones in the mesh).
HEADED = {"axe", "greataxe", "polearm"}

#: Pieces fought with a half turn about their own length from the way the
#: rules above put them in the fist.  Both are drawn as crescents held at the
#: middle, and the turn decides which way the crescents hook: the way the
#: rules hold them, the folding bow drove its lower limb 0.14 m into the floor
#: in Combat_Slash_B, and the twin glaive both its blades -- 0.10 m in the
#: Combat_Slash_A wind-up, 0.02 m in B.  Turned, measured in the client at 121
#: samples a swing, neither reaches the floor (bow +0.13/+0.18 m, glaive
#: +0.02/+0.08 m) and the bow touches the body in one combat-idle frame rather
#: than eight.  Settled by measuring and looking, like the flips.
FIGHTING_TURNED = {
    "090_folding_crescent_bow",
    "058_sunmane_twin_crescent_glaive",
}

#: How a bow stands at ease: its upper limb leant ahead by the first of these
#: tilts, in degrees off upright, that keeps it clear, swung out towards the
#: holding hand's side by the first of the azimuths that lets one.
BOW_TILTS = (6., 10., 14., 18., 22., 26., 30.)
BOW_AZIMUTHS = (0., 20., 40.)

#: The off hand.  Modified 2026-10-06 for Eloria Client.  Its piece used to be
#: solved like the right hand's and came out unlike it: the idle rests the
#: left hand on the thigh, about four centimetres nearer the leg than the
#: right, so the search swung every left-hand piece away from the leg --
#: a rondel dagger 43 degrees out beside its twin's 10 -- and a dual-wield
#: pair looked lopsided at rest.  Now a left-hand piece rests as the mirror
#: image of the same piece in the right hand, and the arm makes the room
#: instead: WeaponCarryPose holds it out from the body at ease by the first of
#: these spreads, in degrees, that clears the leg, the armour over it and the
#: cape, which the idle socket carries as ``"armSpread"`` -- or, where none
#: does, the least of those that come nearest.  Four degrees puts the left fist
#: where the right one hangs; the rest is the hip of the kit legguards, whose
#: fur and hems stand out over the left thigh a centimetre or two farther than
#: over the right.  Ten degrees takes the fist about eleven centimetres out.
OFFHAND_SPREADS = (0., 2., 4., 6., 8., 10.)

#: And the off hand's fist, which the combat idle raises beside the left
#: shoulder.  The fighting grip laid every left-hand blade back over it, 3-4 cm
#: into the Studded Jack's upper arm and collar on every body, where the old
#: single socket had cleared it.  So the left-hand fighting grip is turned
#: within the fist -- in the hand's own frame, about its X (towards the
#: knuckles) and its Y (towards the back of the hand), in degrees -- by the
#: least of these turns that clears ``FIGHTING_CLIP`` on every body and in
#: every class kit -- and of the turns that size that clear it, the one that
#: touches the body in fewest frames of the swings, which no grip keeps wholly
#: clear: the slashes carry the left hand across the chest.  Only that size:
#: let a larger turn win on a frame or two of a swing and sister pieces came
#: out held thirty degrees apart.
FIGHTING_CLIP = "Fighting_Idle"
FIGHTING_SAMPLES = 12
#: The clips Combat_Slash_A and B are cut from
#: (godot-client/src/actors/combat_animation_library.gd).
SWING_CLIPS = ("Sword_Regular_A", "Sword_Regular_A_Rec",
               "Sword_Regular_B", "Sword_Regular_B_Rec")
SWING_SAMPLES = 8
OFFHAND_TURNS = tuple(sorted(
    ((x, y) for x in (-30., -20., -10., 0., 10., 20., 30.)
     for y in (-30., -20., -10., 0., 10., 20., 30.)),
    key=lambda turn: (math.hypot(*turn), abs(turn[0]), -turn[1], turn[0])))
OFFHAND_TURN_WINDOW = 0.
#: A frame of a swing counts as touching when a counted point of the piece
#: comes this near the body, or goes into armour.
SWING_TOUCH = .005


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The smallest rotation that turns direction ``a`` onto ``b``."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    axis = np.cross(a, b)
    cosine = float(a @ b)
    if np.linalg.norm(axis) < 1e-9:
        if cosine > 0:
            return np.eye(3)
        other = np.array([1., 0., 0.]) if abs(a[0]) < .9 else np.array([0., 1., 0.])
        axis = np.cross(a, other)
        axis /= np.linalg.norm(axis)
        return 2. * np.outer(axis, axis) - np.eye(3)
    skew = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]],
                     [-axis[1], axis[0], 0.]])
    return np.eye(3) + skew + skew @ skew / (1. + cosine)


def _clip_length(document: dict, binary: bytes, clip: str) -> float:
    animation = next(a for a in document.get("animations", [])
                     if a.get("name") == clip)
    return max(float(ea.accessor_array(document, binary,
                                       animation["samplers"][c["sampler"]]["input"]).max())
               for c in animation["channels"])


def _posed_globals(document: dict, pose: dict) -> list[np.ndarray]:
    """Every node's global matrix with ``pose`` (one sampled clip frame)
    applied by name, the way the client retargets the shared library."""
    nodes = document["nodes"]
    local: list[np.ndarray] = []
    for node in nodes:
        base = ea._node_matrix(node)
        channel = pose.get(node.get("name", ""))
        if channel is not None:
            matrix = np.eye(4)
            if "scale" in channel:
                matrix = matrix @ np.diag([*channel["scale"], 1.0])
            if "rotation" in channel:
                rotation = np.eye(4)
                rotation[:3, :3] = Rotation.from_quat(channel["rotation"]).as_matrix()
                matrix = rotation @ matrix
            translation = np.eye(4)
            translation[:3, 3] = channel.get("translation", base[:3, 3])
            base = translation @ matrix
        local.append(base)
    parent: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index
    resolved: dict[int, np.ndarray] = {}

    def resolve(index: int) -> np.ndarray:
        if index not in resolved:
            matrix = local[index]
            if index in parent:
                matrix = resolve(parent[index]) @ matrix
            resolved[index] = matrix
        return resolved[index]

    return [resolve(index) for index in range(len(nodes))]


class _Frame:
    """One sampled pose: the hands, the body posed with it, the armour worn
    over the body (``worn``: one surface per fit of each piece -- its sample
    points, their outward normals and the holding side each follows), and
    every bone's global transform by name (``named``)."""

    def __init__(self, hands: dict, body: np.ndarray, owner: np.ndarray,
                 named: dict | None = None, worn=()):
        self.hands, self.body, self.owner, self.named = hands, body, owner, named
        self.worn = [(points, normals, holder, points.min(axis=0) - WORN_REACH,
                      points.max(axis=0) + WORN_REACH) for points, normals, holder in worn]
        self._tree = None
        self._worn_trees: dict[int, object] = {}

    @property
    def tree(self):
        # Built on first use: a body's own frames are mostly only merged into
        # the frames of every body together, and never queried themselves.
        if self._tree is None:
            from scipy.spatial import cKDTree
            self._tree = cKDTree(self.body)
        return self._tree

    def worn_tree(self, index: int):
        if index not in self._worn_trees:
            from scipy.spatial import cKDTree
            self._worn_trees[index] = cKDTree(self.worn[index][0])
        return self._worn_trees[index]

    def clearance(self, points: np.ndarray, side: str,
                  margins: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Per point: the slack it has beyond its margin from the body
        (``distances``); how far inside worn armour it is (negative, or 0 when
        it is not); and how near it comes to anything."""
        distance = self.distances(points, side)
        slack = distance - margins
        armour = np.zeros(len(points))
        cuffed = np.linalg.norm(points - self.hands[side][:3, 3], axis=1) < CUFF_REACH
        # Each fit of each piece on its own: the same jacket on two builds is
        # two surfaces a few centimetres apart, and a point inside the one is
        # as often nearer the other.
        for index, (surface, normals, owner, low, high) in enumerate(self.worn):
            near = np.flatnonzero(np.all((points >= low) & (points <= high), axis=1))
            if not len(near):
                continue
            apart, nearest = self.worn_tree(index).query(points[near], k=WORN_AGREE)
            signed = np.einsum("ijk,ijk->ij", points[near, None, :] - surface[nearest], normals[nearest])
            # Inside only where every one of the nearest samples says so: a
            # sheet modelled with a lining has normals facing in as well as out,
            # and a cuff or a hem brings the two within reach of each other.
            inside = ((signed[:, 0] < -WORN_INSIDE) & (apart[:, 0] < WORN_REACH)
                      & np.all(signed < 0., axis=1) & (owner[nearest[:, 0]] != side)
                      & ~cuffed[near])
            armour[near] = np.where(inside, np.minimum(armour[near], signed[:, 0]), armour[near])
            distance[near] = np.minimum(distance[near], np.where(
                owner[nearest[:, 0]] == side, 9., np.where(inside, signed[:, 0], apart[:, 0])))
        return slack, armour, distance

    def distances(self, points: np.ndarray, side: str) -> np.ndarray:
        """How near each of ``points`` comes to the body or its clothes.

        Unsigned, on purpose.  The native shirt and trousers are shells with
        faces on both sides, so the normals round a shoulder point every way and
        no vertex can say which side of the skin a point is on.  A piece cannot
        reach the inside of a limb without first crossing its surface, though,
        and its vertices -- and the samples worn armour is cut into
        (``WORN_SPACING``) -- are close enough together that a crossing leaves
        one within a centimetre or so of it, which ``BODY_CLEARANCE`` covers.
        A point whose nearest vertex is the holding hand or forearm counts as
        clear: those close round the grip.  Worn armour is cleared apart from
        this, and signed (``clearance``).
        """
        if not len(points):
            return np.zeros(0)
        distance, nearest = self.tree.query(points)
        return np.where(self.owner[nearest] == side, 9., distance)


@lru_cache(maxsize=1)
def _registry() -> dict:
    """The client registry as it stands, for how worn gear is fitted."""
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _client_path(resource: str) -> Path:
    return CLIENT / resource.removeprefix("res://")


def _worn_model(registry: dict, key: str, slug: str) -> dict:
    """``ReplicatedActor3D._fit_variant``: the registry entry for ``key`` as
    the body ``slug`` wears it -- the copy built on its fit group's rig where
    there is one, the reference piece where there is not."""
    model = registry["models"][key]
    groups = registry.get("fitGroups", {}).get(slug, "")
    for group in groups if isinstance(groups, list) else [groups] if groups else []:
        variant = model.get("variants", {}).get(group)
        if variant:
            resolved = {k: v for k, v in model.items() if k != "variants"}
            resolved.update(variant)
            return resolved
    return model


def _worn_ratios(registry: dict, slug: str, author: str, profile: str,
                 table_key: str) -> dict:
    """``ReplicatedActor3D._girth_ratios`` (``table_key`` "bodyGirth") and
    ``_ground_drops`` ("footAnchor"): per bone, how this body differs from the
    one a garment was authored on, or nothing where they are the same."""
    refitted = profile == "canonical" and slug in registry.get("refittedBodies", [])
    templates = registry.get("bodyTemplates", {})
    shares = (profile == "canonical" and not refitted and bool(templates.get(author))
              and templates.get(author) == templates.get(slug))
    if not author or (author == slug and not refitted) or shares:
        return {}
    table = registry.get("fitProfiles", {}).get(profile, registry).get(table_key, {})
    authored_key = "authoredBodyGirth" if table_key == "bodyGirth" else "authoredFootAnchor"
    authored = registry.get(authored_key, table) if profile == "canonical" else table
    return {"author": authored.get(author, {}), "wearer": table.get(slug, {})}


def _bone_fit(name: str, author_rest: dict, rest: dict, children: dict, fit: float,
              girth: float, ground) -> np.ndarray:
    """``ReplicatedActor3D._bone_fit``: the transform a garment's bind is
    carried onto this body's bone by -- stretched along the bone to its span
    here, let out around it to its girth (only ever widened), and a boot's
    foot bones moved onto this body's foot.  4x4, applied after the bind."""
    def tip(authored: bool):
        found = [author_rest[c][:3, 3] if authored else rest[c][:3, 3]
                 for c in children.get(name, ()) if c in author_rest]
        return np.mean(found, axis=0) if found else None

    bone_rest = author_rest.get(name, np.eye(4))
    author_tip, target_tip = tip(True), tip(False)
    ratio, axis, measured = 1., np.array([0., 1., 0.]), False
    if author_tip is not None and target_tip is not None:
        local = (np.linalg.inv(bone_rest) @ np.r_[author_tip, 1.])[:3]
        author_span = float(np.linalg.norm(local))
        target_span = float(np.linalg.norm(target_tip - rest[name][:3, 3]))
        if author_span > .0005 and target_span > .0005:
            ratio = min(max(target_span / author_span, .4), 2.5)
            axis, measured = local / author_span, True
    matrix = np.eye(4)
    if ground is not None:
        wide = min(max(max(ratio, girth), 1.), 2.)
        landed = np.asarray(ground[0], float) * fit * wide
        matrix[:3, :3] = np.eye(3) * fit * wide
        matrix[:3, 3] = np.linalg.inv(rest[name][:3, :3]) @ (np.asarray(ground[1], float) - landed)
        return matrix
    across = min(max(max(ratio, girth), 1.), 2.)
    along = min(max(ratio, .4), 2.5) if measured else across
    if abs(across - 1.) < .02 and abs(along - 1.) < .02:
        matrix[:3, :3] = np.eye(3) * fit
        return matrix
    matrix[:3, :3] = fit * (np.eye(3) * across + (along - across) * np.outer(axis, axis))
    return matrix


class _Worn:
    """One worn piece rebound to one body as the client binds it
    (``ReplicatedActor3D._rebound_skin``), with its surface sampled
    ``WORN_SPACING`` apart: ``samples`` is a sparse matrix from its posed
    vertices to those points, ``owner`` the holding side each follows.

    ``sheet`` marks a cape.  Armour is a shell round the body, and which side
    of it a point is on is what its own normals say; a cape is a single sheet
    drawn from both faces, with half its normals turned in, so no four of
    them ever agreed a point was behind it and the bows passed through it
    unseen.  A sheet's normals are turned away from the body before it is
    cleared (``_bodies_frames``), and then a point between it and the back is
    under the cape, as a point under a jacket is inside it.

    Nor does a cape hang where its bind pose puts it.  The client's cloth
    (``cape_cloth.gd``) pushes the points its chains carry out of the torso
    and the legs and behind the plane of the back, and settled at rest it
    hangs about five centimetres farther back than it is bound -- the sides
    of the sheet at the hip 11-17 cm behind the hand rather than 4-13
    (measured in the client on a stoneborn in the Vanguard kit).  Left where
    it is bound, the sheet put every hilt held at the hip under it.  ``cloth``
    is each sample's share of the chains, which ``_bodies_frames`` moves back
    by ``CAPE_HANG`` and holds behind the plane: within 2 cm of the client's
    sheet at the median and 4 cm at the 90th percentile, against 2.4 and 5.6
    as bound."""

    def __init__(self, path: Path, model: dict, slug: str, registry: dict,
                 rest: dict, children: dict, head_y: float):
        self.sheet = model.get("skinRegion") == "cape"
        document, binary = ea.read_gltf(path)
        nodes = document["nodes"]
        profile = str(model.get("fitProfile", ""))
        author = str(model.get("authoredFor", ""))
        canonical = registry.get("fitProfiles", {}).get(profile, registry).get("canonicalHeadRestY", 0.)
        fit = head_y / float(canonical) if canonical else 1.
        girth = _worn_ratios(registry, slug, author, profile, "bodyGirth")
        ground = (_worn_ratios(registry, slug, author, profile, "footAnchor")
                  if model.get("skinRegion") == "boots" else {})
        positions, normals, joints, weights, rows = [], [], [], [], []
        binds, names = None, None
        for node in nodes:
            if "mesh" not in node or "skin" not in node:
                continue
            mesh = document["meshes"][node["mesh"]]
            # The authored shell only: a generated backing is the body cover
            # envelope drawn inside it.
            if str(mesh.get("name", node.get("name", ""))).startswith("Generated"):
                continue
            skin = document["skins"][node["skin"]]
            names = [nodes[j].get("name", "") for j in skin["joints"]]
            binds = (ea.accessor_array(document, binary, skin["inverseBindMatrices"])
                     .astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1))
            for primitive in mesh["primitives"]:
                attributes = primitive["attributes"]
                base = sum(len(p) for p in positions)
                positions.append(ea.accessor_array(document, binary, attributes["POSITION"]).astype(np.float64))
                normals.append(ea.accessor_array(document, binary, attributes["NORMAL"]).astype(np.float64)
                               if "NORMAL" in attributes else np.zeros_like(positions[-1]))
                joints.append(ea.accessor_array(document, binary, attributes["JOINTS_0"]).astype(np.int64))
                raw = ea.accessor_array(document, binary, attributes["WEIGHTS_0"])
                part = raw.astype(np.float64)
                if document["accessors"][attributes["WEIGHTS_0"]].get("normalized"):
                    part /= np.iinfo(raw.dtype).max
                weights.append(part)
                rows.append(ea.accessor_array(document, binary, primitive["indices"])
                            .astype(np.int64).reshape(-1, 3) + base)
        self.empty = not positions
        if self.empty:
            return
        self.positions = np.vstack(positions)
        self.normals = np.vstack(normals)
        self.joints = np.vstack(joints)
        weights = np.vstack(weights)
        self.weights = weights / np.maximum(weights.sum(axis=1, keepdims=True), 1e-9)
        self.names = names
        # A garment whose rig this body does not carry is refused, as the
        # client refuses it.
        if any(name not in rest for name in names):
            self.empty = True
            return
        author_rest = {name: np.linalg.inv(bind) for name, bind in zip(names, binds)}
        drops = {bone: (ground["author"][bone], ground["wearer"][bone])
                 for bone in ground.get("author", {})
                 if bone in ground.get("wearer", {}) and any(ground["author"][bone])
                 and any(ground["wearer"][bone])}
        ratios = {}
        for bone, value in girth.get("author", {}).items():
            to = float(girth.get("wearer", {}).get(bone, 0.))
            if float(value) > .0005 and to > .0005:
                ratios[bone] = min(max(to / float(value), 1.), 2.)
        self.binds = np.array([_bone_fit(name, author_rest, rest, children, fit,
                                         ratios.get(name, 1.), drops.get(name)) @ bind
                               for name, bind in zip(names, binds)])
        # The surface, cut into triangles no edge of which is longer than
        # WORN_SPACING, and sampled at their corners.
        self.samples = _surface_samples(self.positions, np.vstack(rows), WORN_SPACING)
        dominant = np.asarray(names)[self.joints[np.arange(len(self.joints)),
                                                 np.argmax(self.weights, axis=1)]]
        follows = dominant[np.asarray(self.samples.argmax(axis=1)).ravel()]
        if self.sheet:
            chained = np.array([name.startswith("cape_") for name in names])
            self.cloth = np.asarray(self.samples @ (
                self.weights * chained[self.joints]).sum(axis=1)).ravel()
        # Only a glove closes round the grip.  A sleeve does not, unlike the
        # bare forearm (``_clip_frames``): it stands off the arm, and a haft
        # or a hilt run up beside the forearm of the hand that holds it passes
        # inside it -- the planted spears and the Warden's staff went up the
        # Studded Jack's sleeve to the elbow, the bowblade's upper limb too.
        holding = ("hand", "index", "middle", "ring", "pinky", "thumb")
        self.owner = np.array([b[-1] if b[-2:] in ("_l", "_r") and b.split("_")[0] in holding
                               else "" for b in follows])
        # Two bodies on one skeleton wearing the piece fitted the same way
        # draw it identically, and it need only be cleared once.
        import hashlib
        digest = hashlib.sha1(str(path).encode())
        digest.update(np.round(self.binds, 6).tobytes())
        digest.update(np.round(np.array([rest[name] for name in names]), 5).tobytes())
        self.signature = digest.hexdigest()

    def posed(self, globals_by_name: dict) -> tuple[np.ndarray, np.ndarray]:
        """The sampled surface in one pose, and its outward normals."""
        skinning = np.array([globals_by_name[name] for name in self.names]) @ self.binds
        homogeneous = np.c_[self.positions, np.ones(len(self.positions))]
        vertices = np.zeros((len(self.positions), 3))
        normals = np.zeros((len(self.positions), 3))
        for k in range(self.joints.shape[1]):
            matrices = skinning[self.joints[:, k]]
            vertices += self.weights[:, k, None] * np.einsum(
                "nij,nj->ni", matrices, homogeneous)[:, :3]
            # Normals by the inverse transpose: the girth fit widens a garment
            # round a bone without lengthening it along the bone.
            normals += self.weights[:, k, None] * np.einsum(
                "nji,nj->ni", np.linalg.inv(matrices[:, :3, :3]), self.normals)
        normals = self.samples @ normals
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        return self.samples @ vertices, normals


def _surface_samples(positions: np.ndarray, triangles: np.ndarray, spacing: float):
    """Points over a triangle mesh no farther apart than ``spacing``, as a
    sparse matrix from its vertices to them: each triangle halved across its
    longest edge until no edge is longer, and every corner that leaves taken
    once.  A grid laid on each triangle instead put thousands of points on the
    long slivers these shells are full of."""
    from scipy.sparse import csr_matrix
    owner = np.arange(len(triangles))
    weights = np.tile(np.eye(3), (len(triangles), 1, 1))     # corner x vertex of the owner
    kept_weights, kept_owner = [], []
    while len(owner):
        corners = np.einsum("tcw,twd->tcd", weights, positions[triangles[owner]])
        edges = np.linalg.norm(corners - np.roll(corners, -1, axis=1), axis=2)  # c -> c + 1
        longest = np.argmax(edges, axis=1)
        done = edges[np.arange(len(owner)), longest] <= spacing
        kept_weights.append(weights[done])
        kept_owner.append(owner[done])
        weights, owner, longest = weights[~done], owner[~done], longest[~done]
        rows = np.arange(len(owner))
        a = weights[rows, longest]
        b = weights[rows, (longest + 1) % 3]
        c = weights[rows, (longest + 2) % 3]
        middle = (a + b) / 2
        weights = np.concatenate([np.stack([a, middle, c], axis=1),
                                  np.stack([middle, b, c], axis=1)])
        owner = np.concatenate([owner, owner])
    weights = np.concatenate(kept_weights).reshape(-1, 3)
    vertices = triangles[np.repeat(np.concatenate(kept_owner), 3)]
    where = np.einsum("nw,nwd->nd", weights, positions[vertices])
    _, first = np.unique(np.round(where, 6), axis=0, return_index=True)
    weights, vertices = weights[first], vertices[first]
    rows = np.repeat(np.arange(len(first)), 3)
    return csr_matrix((weights.ravel(), (rows, vertices.ravel())),
                      shape=(len(first), len(positions)))


@lru_cache(maxsize=None)
def _worn(race: str, key: str) -> "_Worn | None":
    """Worn piece ``key`` rebound to the body ``race``."""
    registry = _registry()
    slug = Path(race).stem
    model = _worn_model(registry, key, slug)
    path = _client_path(str(model.get("scene", "")))
    if model.get("attach") != "skinned" or not path.exists():
        return None
    rig, children = _race_rig(race)
    worn = _Worn(path, model, slug, registry, rig.rest, children, float(rig.origin("Head")[1]))
    return None if worn.empty else worn


@lru_cache(maxsize=32)
def _race_rig(race: str):
    """A body's rig, and each of its bones' children by name."""
    rig = ea.load_rig(Path(race), ce.BODY_MESH)
    children: dict[str, list[str]] = {}
    for bone, parent in rig.parent.items():
        if parent is not None:
            children.setdefault(parent, []).append(bone)
    return rig, children


@lru_cache(maxsize=32)
def _clip_frames(race: str, library: str, clip: str, count: int) -> tuple[_Frame, ...]:
    """``clip`` sampled ``count`` times across its loop on ``race``: each
    hand's global transform and the skinned body surface, in character space
    (the skeleton's space, which the client's floor is the y = 0 plane of)."""
    document, binary = ea.read_gltf(Path(race))
    library_document, library_binary = ea.read_gltf(Path(library))
    nodes = document["nodes"]
    skin = document["skins"][0]
    joints = skin["joints"]
    inverse_binds = (ea.accessor_array(document, binary, skin["inverseBindMatrices"])
                     .astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1))
    # The skin and its native shirt, trousers and boots.  Eyes, brows and
    # scalp are left out: a held weapon is nowhere near them.  Some bodies
    # draw every surface from one shared vertex set and tell them apart only by
    # their faces (see ea.load_rig); others give each its own.  Each attribute
    # set is read once, and only the vertices these surfaces draw are kept.
    sets: dict[tuple, list] = {}
    for node in nodes:
        mesh = document["meshes"][node["mesh"]] if "mesh" in node and "skin" in node else None
        if mesh is None or mesh.get("name") not in HELD_CLEARANCE_SURFACES:
            continue
        for primitive in mesh["primitives"]:
            key = tuple(sorted(primitive["attributes"].items()))
            sets.setdefault(key, [primitive["attributes"], []])[1].append(
                ea.accessor_array(document, binary, primitive["indices"]).ravel())
    positions, bones, weights = [], [], []
    for attributes, faces in sets.values():
        used = np.unique(np.concatenate(faces))
        positions.append(ea.accessor_array(document, binary, attributes["POSITION"])
                         .astype(np.float64)[used])
        bones.append(ea.accessor_array(document, binary, attributes["JOINTS_0"])
                     .astype(np.int64)[used])
        raw_weights = ea.accessor_array(document, binary, attributes["WEIGHTS_0"])
        part = raw_weights.astype(np.float64)[used]
        if document["accessors"][attributes["WEIGHTS_0"]].get("normalized"):
            part /= np.iinfo(raw_weights.dtype).max
        weights.append(part)
    positions, bones, weights = np.vstack(positions), np.vstack(bones), np.vstack(weights)
    weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-9)
    names = [nodes[joint].get("name", "") for joint in joints]
    holding = {side: {i for i, name in enumerate(names)
                      if name.endswith("_" + side) and name.split("_")[0] in
                      ("lowerarm", "hand", "index", "middle", "ring", "pinky", "thumb")}
               for side in "lr"}
    dominant = bones[np.arange(len(bones)), np.argmax(weights, axis=1)]
    owner = np.array(["l" if b in holding["l"] else "r" if b in holding["r"] else ""
                      for b in dominant])
    by_name = {node.get("name", ""): index for index, node in enumerate(nodes)}
    length = _clip_length(library_document, library_binary, clip)
    frames = []
    for step in range(count):
        pose = ea._sample_clip_rotations(library_document, library_binary, clip,
                                         length * step / count)
        globals_ = _posed_globals(document, pose)
        skinning = np.array([globals_[joint] for joint in joints]) @ inverse_binds
        homogeneous = np.c_[positions, np.ones(len(positions))]
        posed = np.zeros((len(positions), 3))
        for k in range(bones.shape[1]):
            matrices = skinning[bones[:, k]]
            posed += weights[:, k, None] * np.einsum("nij,nj->ni", matrices, homogeneous)[:, :3]
        hands = {side: globals_[by_name["hand_" + side]] for side in "lr"}
        frames.append(_Frame(hands, posed, owner,
                             {name: globals_[joint] for name, joint in zip(names, joints)}))
    return tuple(frames)


#: How far behind the spine the cloth keeps a cape's chains
#: (``cape_cloth.gd`` BACK_OFFSET), the spine bone it measures from, and how
#: much farther back than it is bound the settled cloth hangs (``_Worn``).
CAPE_BACK_OFFSET = -.02
CAPE_ANCHOR = "spine_03"
CAPE_HANG = .05


def _hung(points: np.ndarray, cloth: np.ndarray, named: dict, rest: dict) -> np.ndarray:
    """A cape's samples with the share its chains carry hung back and held
    behind the plane of the back, the way the cloth hangs them: the plane
    through the anchor bone, facing the way the chest does -- the bone's own
    axis that faces forward at rest, carried by its pose."""
    anchor = named[CAPE_ANCHOR]
    at_rest = rest[CAPE_ANCHOR][:3, :3]
    forward = anchor[:3, :3] @ np.linalg.solve(at_rest, np.array([0., 0., 1.]))
    forward /= np.linalg.norm(forward)
    points = points - (CAPE_HANG * cloth)[:, None] * forward
    ahead = (points - anchor[:3, 3]) @ forward - CAPE_BACK_OFFSET
    return points - np.maximum(ahead, 0.)[:, None] * cloth[:, None] * forward


def _outward(points: np.ndarray, normals: np.ndarray, named: dict) -> np.ndarray:
    """``normals`` turned to face away from the body: from the line up its
    middle, pelvis to neck, which a cape hangs behind and wraps over."""
    low, high = named["pelvis"][:3, 3], named["neck_01"][:3, 3]
    spine = high - low
    along = np.clip((points - low) @ spine / float(spine @ spine), 0., 1.)
    away = points - (low + along[:, None] * spine)
    return np.where((np.einsum("ij,ij->i", normals, away) < 0.)[:, None], -normals, normals)


@lru_cache(maxsize=8)
def _bodies_frames(races: tuple[str, ...], library: str, clip: str,
                   count: int, worn: tuple[str, ...] = ()) -> tuple[_Frame, ...]:
    """``_clip_frames`` over several bodies at once, as one surface to clear.

    Every playable body is built on the one skeleton and plays the clip
    unchanged -- only the model scale draws it larger or smaller, and that
    scales the held piece with it -- so the hands are the same in every one
    and only the flesh round them differs.  A grip solved against the slender
    body alone put a crossbow into a stoneborn's thigh.

    Each body also wears every piece of ``worn`` armour, fitted to it the way
    the client fits it, and the surface takes one copy of each distinct fit:
    the races that share a sex share their girths, so the sixteen bodies wear
    any one piece only four different ways."""
    each = [_clip_frames(race, library, clip, count) for race in races]
    fits: dict[str, tuple[int, _Worn]] = {}
    for index, race in enumerate(races):
        for key in worn:
            piece = _worn(race, key)
            if piece is not None:
                fits.setdefault(piece.signature, (index, piece))
    merged = []
    for frames in zip(*each):
        worn = []
        for index, piece in fits.values():
            points, normals = piece.posed(frames[index].named)
            if piece.sheet:
                points = _hung(points, piece.cloth, frames[index].named,
                               _race_rig(races[index])[0].rest)
                normals = _outward(points, normals, frames[index].named)
            worn.append((points, normals, piece.owner))
        merged.append(_Frame(frames[0].hands, np.vstack([f.body for f in frames]),
                             np.concatenate([f.owner for f in frames]), worn=worn,
                             named=frames[0].named))
    return tuple(merged)


def _prop_points(path: Path, count: int | None = 500) -> np.ndarray:
    """The seated mesh's vertices, thinned evenly, always keeping both ends
    (all of them for ``count`` None)."""
    document, binary = ea.read_gltf(path)
    points = np.concatenate([
        ea.accessor_array(document, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
        for mesh in document["meshes"] for primitive in mesh["primitives"]])
    if count is not None and len(points) > count:
        keep = np.unique(np.r_[np.linspace(0, len(points) - 1, count).astype(int),
                               np.argmin(points[:, 1]), np.argmax(points[:, 1])])
        points = points[keep]
    return points


#: How far either side of its axis a haft reaches, and so where a head starts.
HAFT_RADIUS = .04


def _head_side(path: Path) -> float:
    """Which way along X the head of a hafted piece hangs off its haft.

    The surface area of the top half of the piece that lies clear of the haft,
    each patch weighted by how far out it reaches: an axe's blade, a halberd's
    broad blade against the spike opposite it, a scythe's long blade.  Not the
    extent -- a bardiche's thin back hook reaches farther than its crescent --
    and not the vertex mean, which is mostly the haft and follows wherever the
    modeller spent vertices.
    """
    document, binary = ea.read_gltf(path)
    moment = 0.
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            points = ea.accessor_array(document, binary,
                                       primitive["attributes"]["POSITION"]).astype(np.float64)
            corners = points[ea.accessor_array(document, binary, primitive["indices"])
                             .astype(np.int64).reshape(-1, 3)]
            area = .5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0],
                                                corners[:, 2] - corners[:, 0]), axis=1)
            centre = corners.mean(axis=1)
            head = (centre[:, 1] > .5 * points[:, 1].max()) & (np.abs(centre[:, 0]) > HAFT_RADIUS)
            moment += float((area[head] * np.sign(centre[head, 0])
                             * (np.abs(centre[head, 0]) - HAFT_RADIUS)).sum())
    return moment


class Grip:
    """A hand-local placement: ``basis`` (columns are the prop's axes in the
    hand bone's frame) and ``origin`` (where the prop's own origin sits in that
    frame, in metres on the body it was solved on)."""

    def __init__(self, basis: np.ndarray, origin: np.ndarray, **report):
        self.basis, self.origin, self.report = basis, np.asarray(origin, float), report

    def socket(self, rig, side: str, fit: float) -> dict:
        """As the registry stores it: character space at the bone's rest, in
        the units the piece is fitted in -- the inverse of what
        ``ReplicatedActor3D._attach_socketed_equipment`` does with it."""
        rest = rig.basis("hand_" + side)
        socket = {"bone": "hand_" + side,
                  "offset": [round(float(v), 5) + 0. for v in rest @ self.origin / fit],
                  "rotationDegrees": _grip_degrees(rest @ self.basis)}
        # An idle grip also says how the piece rests, and how far out its
        # arm is held to give it room (OFFHAND_SPREADS).
        if "style" in self.report:
            socket["style"] = self.report["style"]
        if self.report.get("spread"):
            socket["armSpread"] = round(float(self.report["spread"]), 3)
        return socket


def _grip_degrees(basis: np.ndarray) -> list[float]:
    """``_euler_degrees``, settled at gimbal lock.  The fighting grip turns the
    piece a right angle about X, where YXZ angles stop being unique and the
    decomposition splits one turn between Y and Z at random (-175.06 and
    -4.94 for what is 0 and 180); there Y is taken as zero and Z solved
    alone, which is the same rotation written the way a person would."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)    # scipy's gimbal-lock note
        x, y, z = _euler_degrees(basis)
    if abs(abs(x) - 90.) < 1e-3:
        x = math.copysign(90., x)
        z = math.degrees(math.atan2(float(basis[2, 0]) * math.copysign(1., x),
                                    float(basis[0, 0])))
        y = 0.
    # Angles a hair off a whole degree are a whole degree written with the
    # float noise of the solve: -179.99998 for 180, 5e-05 for 0.
    whole = [float(round(v)) if abs(v - round(v)) < 1e-3 else v for v in (x, y, z)]
    return [180. if abs(v + 180.) < 1e-9 else round(float(v), 5) + 0. for v in whole]


def _mirror(basis: np.ndarray, origin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A right-hand placement moved to the left hand.  The two hand bones are
    mirror images with their X axes turned opposite ways through the hand --
    out of the back of the right, out of the palm of the left -- so a point
    mirrors by negating its X.  The piece itself cannot be mirrored (that would
    turn every asymmetric hilt inside out), so its own Z is turned over to keep
    it a rotation, which leaves its X -- the side a head hangs and an edge
    faces -- mirrored with the hand."""
    flip = np.diag([-1., 1., 1.])
    return flip @ basis @ np.diag([1., 1., -1.]), flip @ origin


def fighting_grip(rig, side: str, fit: float, roll: bool, hold: float = 0.) -> Grip:
    """The fist the swings were animated around.  The fingers curl right
    round, so the tunnel they leave runs along the hand bone's Z, out of the
    thumb side: the piece's length goes that way, its edge (X) faces the
    knuckles (+Y), which is the way a closed hand strikes, and its flat faces
    the back of the hand.  ``roll`` turns it a half turn about its length, to
    lead with a head that hangs to the other side; ``hold`` is how far up its
    length from the mesh origin the fist closes (``FIGHTING_HOLDS``).  The
    grip remembers the fist itself as ``fist``: the idle grip is held there."""
    basis = np.column_stack(([0., 1., 0.], [0., 0., 1.], [1., 0., 0.]))
    if roll:
        basis = basis @ np.diag([-1., 1., -1.])
    fist = rig.basis("hand_r").T @ np.asarray(FIST_OFFSET) * fit
    if side == "l":
        basis, fist = _mirror(basis, fist)
    grip = Grip(basis, fist - basis @ np.array([0., hold, 0.]) * fit)
    grip.fist = fist
    return grip


def _direction(side: str, tilt: float, azimuth: float, up: bool = False) -> np.ndarray:
    """A character-space direction ``tilt`` degrees off straight down (or up),
    leaning towards ``azimuth``: 0 is the way the body faces (+Z), 90 is out
    to the holding hand's side (-X for the right)."""
    t, a = math.radians(tilt), math.radians(azimuth)
    out = np.array([-1. if side == "r" else 1., 0., 0.])
    ahead = math.sin(a) * out + math.cos(a) * np.array([0., 0., 1.])
    return math.cos(t) * np.array([0., 1. if up else -1., 0.]) + math.sin(t) * ahead


def _turned(fighting: Grip, frame: _Frame, side: str, direction: np.ndarray) -> np.ndarray:
    """The fighting grip turned the least way that points the piece along
    ``direction`` in ``frame``'s pose.  Keeping the turn smallest keeps the
    flat facing the way the fist held it -- across the hand, which hangs palm
    to thigh, so a blade lies flat to the leg -- and keeps the blend between
    the two grips a single swing rather than a twist."""
    hand = frame.hands[side][:3, :3]
    hand = hand / np.linalg.norm(hand, axis=0)
    wanted = hand.T @ direction
    return _rotation_between(fighting.basis[:, 1], wanted) @ fighting.basis


def _held_out(frames, side: str, degrees: float):
    """``frames`` with the ``side`` arm held ``degrees`` out from the body at
    the shoulder, the way WeaponCarryPose holds an off-hand weapon's arm at
    ease: turned about the line the arm hangs along crossed with the way out,
    which moves the hand and leaves the body where it is -- only the hand is
    measured from, and the forearm it moves is never counted."""
    if not degrees:
        return frames
    moved = []
    for frame in frames:
        shoulder = frame.named["upperarm_" + side][:3, 3]
        across = frame.named["upperarm_" + ("r" if side == "l" else "l")][:3, 3]
        out = shoulder - across
        out[1] = 0.
        axis = np.cross(frame.hands[side][:3, 3] - shoulder, out)
        turn = np.eye(4)
        turn[:3, :3] = Rotation.from_rotvec(
            axis / np.linalg.norm(axis) * math.radians(degrees)).as_matrix()
        turn[:3, 3] = shoulder - turn[:3, :3] @ shoulder
        held = copy.copy(frame)
        held.hands = dict(frame.hands)
        held.hands[side] = turn @ frame.hands[side]
        moved.append(held)
    return moved


def _turned_in_fist(grip: Grip, turn: tuple[float, float]) -> Grip:
    """``grip`` turned within the fist, about the fist itself, by ``turn``
    degrees about the hand's X and then its Y."""
    rotation = (Rotation.from_rotvec([math.radians(turn[0]), 0., 0.])
                * Rotation.from_rotvec([0., math.radians(turn[1]), 0.])).as_matrix()
    turned = Grip(rotation @ grip.basis, grip.fist - rotation @ (grip.fist - grip.origin),
                  turn=tuple(turn))
    turned.fist = grip.fist
    return turned


def _touching(frames, side: str, grip: Grip, points: np.ndarray, scale: float,
              margins: np.ndarray) -> int:
    """How many of ``frames`` the piece touches the body or goes into armour
    in, away from the hand that holds it."""
    touching = 0
    for frame in frames:
        _, _, _, body, armour = _measure((frame,), side, grip.basis, grip.origin,
                                         points, scale, margins)
        touching += body + BODY_CLEARANCE < SWING_TOUCH or armour < 0.
    return touching


def offhand_fighting_grip(races: tuple[str, ...], library: str, base: Grip,
                          points: np.ndarray, scale: float, hold: float) -> Grip:
    """The left-hand fighting grip: ``base`` -- the right hand's fist grip
    mirrored -- turned in the fist by the least of ``OFFHAND_TURNS`` that
    clears the combat idle (see ``OFFHAND_TURNS``)."""
    stance = _bodies_frames(races, library, FIGHTING_CLIP, FIGHTING_SAMPLES, HELD_CLEARANCE_GEAR)
    margins = _margins(points, scale, hold, "hang")
    clearing, tried, first = [], [], None
    for turn in OFFHAND_TURNS:
        size = math.hypot(*turn)
        if first is not None and size > first + OFFHAND_TURN_WINDOW:
            break
        grip = _turned_in_fist(base, turn)
        lowest, slack, nearest, body, armour = _measure(stance, "l", grip.basis, grip.origin,
                                                        points, scale, margins)
        tried.append((slack, grip))
        if slack >= 0:
            first = size if first is None else first
            clearing.append(grip)
    if not clearing:
        # Nothing clears: the turn that comes nearest, the least of those
        # within FALLBACK_TOLERANCE of it.
        best = max(slack for slack, _ in tried)
        grip = next(grip for slack, grip in tried if slack >= best - FALLBACK_TOLERANCE)
        grip.report.update(clear=False, swings=None)
        return grip
    swings = tuple(frame for clip in SWING_CLIPS
                   for frame in _bodies_frames(races, library, clip, SWING_SAMPLES, HELD_CLEARANCE_GEAR))
    scored = [(_touching(swings, "l", grip, points, scale, margins), index, grip)
              for index, grip in enumerate(clearing)]
    touching, _, grip = min(scored, key=lambda s: (s[0], s[1]))
    grip.report.update(clear=True, swings="%d/%d" % (touching, len(swings)))
    return grip


def _measure(frames, side, basis, origin, points, scale, margins,
             floor_only: bool = False) -> tuple[float, float, float, float, float]:
    """Over every frame, of a piece placed by (``basis``, ``origin``): its
    lowest point above the floor; its slack, the least by which any point
    clears the body beyond the margin it has to keep or is inside worn armour
    (negative when one comes too near or goes in; a NaN margin marks a point
    the hand covers, which is not counted); the nearest approach of any
    counted point; and the two parts of the slack, the body's and the
    armour's (0 when nothing goes in).  ``floor_only`` measures the lowest
    point alone, for the searches that only slide or tilt a piece onto the
    floor."""
    counted = ~np.isnan(margins)
    lowest, body, armour, nearest = 9., 9., 0., 9.
    for frame in frames:
        hand = frame.hands[side]
        placed = (hand[:3, :3] @ (basis * scale) @ points.T).T + hand[:3, :3] @ origin + hand[:3, 3]
        lowest = min(lowest, float(placed[:, 1].min()))
        if floor_only:
            continue
        clear, inside, distance = frame.clearance(placed[counted], side, margins[counted])
        if len(distance):
            body = min(body, float(clear.min()))
            armour = min(armour, float(inside.min()))
            nearest = min(nearest, float(distance.min()))
    return lowest, min(body, armour), nearest, body, armour


def _margins(points: np.ndarray, scale: float, hold_y: float, style: str) -> np.ndarray:
    """How near each point of a piece may come to the body.  The hand's own
    width either side of the hold is not counted.  The handle end behind a
    hilt held at its grip -- a pommel, a short haft's butt -- rides at the
    heel of the hand beside the forearm, which hangs against the hip, and need
    only stay out of it.  Everything else keeps ``BODY_CLEARANCE``."""
    along = (points[:, 1] - hold_y) * scale
    reach = np.linalg.norm(points * scale - np.array([0., hold_y * scale, 0.]), axis=1)
    margins = np.full(len(points), BODY_CLEARANCE)
    if style != "plant":
        margins[along < 0] = POMMEL_CLEARANCE
    margins[reach <= HELD_LENGTH] = np.nan
    return margins


def idle_grip(frames, side: str, style: str, fighting: Grip, points: np.ndarray,
              scale: float) -> Grip:
    """How a piece is held at ease, solved over the idle loop in ``frames``."""
    middle = frames[len(frames) // 2]
    floor = FLOOR_CLEARANCE[style]

    def place(direction, hold_y=0., floor_only=False):
        """basis, origin, then ``_measure``'s lowest, slack, nearest, body
        and armour."""
        basis = _turned(fighting, middle, side, direction)
        origin = fighting.fist - basis @ np.array([0., hold_y, 0.]) * scale
        return (basis, origin) + _measure(frames, side, basis, origin, points, scale,
                                          _margins(points, scale, hold_y, style), floor_only)

    def grip(basis, origin, lowest, slack, nearest, body, armour, lean, hold=0.):
        return Grip(basis, origin, style=style, lean=lean, hold=round(float(hold), 4),
                    floor=lowest, body=nearest, slack=round(float(slack), 4),
                    body_slack=round(float(body), 4), armour=round(float(armour), 4),
                    clear=bool(slack >= 0 and lowest >= floor - 1e-4))

    def natural(options, measured):
        """When nothing clears: the first of ``options`` -- listed most
        natural first -- among those that go least far into worn armour, and
        then nearest to clearing the body and the floor, each to within
        FALLBACK_TOLERANCE.  The armour first because it is what is seen
        cutting through; trading the body's margin for it the other way round
        stood every unclearable spear against the leg.  ``measured`` gives an
        option's (lowest, body, armour)."""
        def armour(option):
            return measured(option)[2]

        def rest(option):
            lowest, body, _ = measured(option)
            return min(lowest - floor, body)

        best = max(armour(option) for option in options)
        options = [option for option in options if armour(option) >= best - FALLBACK_TOLERANCE]
        best = max(rest(option) for option in options)
        return next(option for option in options if rest(option) >= best - FALLBACK_TOLERANCE)

    if style == "plant":
        # Stood on its butt and held wherever along the haft leaves the butt
        # just off the floor.  Sliding the hold along a near-upright haft moves
        # the butt by the slide times the haft's rise, so a correction or two
        # from the measured height lands it.  Upright
        # unless that runs it through the shoulder or the foot: then its top
        # is leant the least that clears them, out or forward first, since a
        # haft leant in or back crosses the arm that holds it.
        tried = []
        leans = sorted(((out, ahead) for out in PLANT_OUT for ahead in PLANT_AHEAD),
                       key=lambda lean: (abs(lean[0]) + abs(lean[1]), -lean[0], -lean[1]))
        for out, ahead in leans:
            direction = np.array([
                math.sin(math.radians(out)) * (-1. if side == "r" else 1.),
                1., math.sin(math.radians(ahead))])
            direction /= np.linalg.norm(direction)
            hold_y = 0.
            for _ in range(3):
                basis, origin, lowest = place(direction, hold_y, floor_only=True)[:3]
                rise = abs(float((middle.hands[side][:3, :3] @ basis[:, 1])[1]))
                hold_y += (lowest - floor) / scale / max(rise, .3)
            tried.append(grip(*place(direction, hold_y), lean=(out, ahead), hold=hold_y))
            if tried[-1].report["clear"]:
                return tried[-1]
        return natural(tried, lambda g: (g.report["floor"], g.report["body_slack"], g.report["armour"]))

    if style == "bow":
        tried = []
        for azimuth in BOW_AZIMUTHS:
            for tilt in BOW_TILTS:
                tried.append(((tilt, azimuth), place(_direction(side, tilt, azimuth, up=True))))
                placed = tried[-1][1]
                if placed[2] >= floor and placed[3] >= 0:
                    return grip(*placed, lean=(tilt, azimuth))
        lean, placed = natural(tried, lambda t: (t[1][2], t[1][5], t[1][6]))
        return grip(*placed, lean=lean)

    if style == "upright":
        tried = []
        for tilt in (0., 4., 8., 12., 16.):
            tried.append((tilt, place(_direction(side, tilt, 90., up=True))))
            if tried[-1][1][3] >= 0:
                break
        tilt, placed = natural(tried, lambda t: (t[1][2], t[1][5], t[1][6]))
        return grip(*placed, lean=(tilt, 90.))

    # hang: the most nearly vertical slant that clears the floor and the body,
    # ahead first and then swung out to the side when the leg is in the way.
    # lean: longer than the hand is high, so its slant is found exactly, by
    # halving, to rest the tip just off the floor, in the first direction of
    # LEAN_AZIMUTHS that keeps the rest of it off the body.
    candidates, fallback = [], []
    for azimuth in HANG_AZIMUTHS if style == "hang" else LEAN_AZIMUTHS:
        if style == "hang":
            for tilt in np.arange(MIN_HANG_TILT, 46., 2.):
                # The floor first, which is cheap: a slant that reaches it is
                # only measured against the body if nothing else will do.
                placed = place(_direction(side, tilt, azimuth), floor_only=True)
                if placed[2] >= floor:
                    placed = place(_direction(side, tilt, azimuth))
                fallback.append((tilt, azimuth, placed))
                if placed[2] >= floor and placed[3] >= 0:
                    candidates.append((tilt, azimuth, placed))
                    break
        else:
            low, high = 0., 85.
            for _ in range(14):
                tilt = (low + high) / 2
                lowest = place(_direction(side, tilt, azimuth), floor_only=True)[2]
                low, high = (tilt, high) if lowest < floor else (low, tilt)
            placed = place(_direction(side, high, azimuth))
            fallback.append((high, azimuth, placed))
            if placed[3] >= 0:
                candidates.append((high, azimuth, placed))
                break
    if candidates and style == "lean":
        tilt, azimuth, placed = candidates[0]
    elif candidates:
        tilt, azimuth, placed = min(candidates, key=lambda c: c[0] + .2 * c[1])
    else:
        # Nothing clears both: take the slant that comes nearest to it, and say
        # so in the report, rather than leave the piece without a grip -- the
        # most natural of those that come within FALLBACK_TOLERANCE of it.
        if style == "hang":
            fallback.sort(key=lambda c: c[0] + .2 * c[1])
            fallback = [(t, a, place(_direction(side, t, a)) if p[2] < floor else p)
                        for t, a, p in fallback]
        tilt, azimuth, placed = natural(fallback, lambda c: (c[2][2], c[2][5], c[2][6]))
    return grip(*placed, lean=(round(float(tilt), 2), azimuth))


def offhand_idle_grip(frames, right: Grip, fighting: Grip, points: np.ndarray,
                      scale: float) -> Grip:
    """The left-hand idle grip: the mirror image of ``right``, the same piece's
    idle grip in the right hand, with the arm held out by the first of
    ``OFFHAND_SPREADS`` that clears the floor, the leg and what is worn over
    it, and the cape -- or, when none does, the least spread of those that
    come nearest."""
    style = right.report["style"]
    floor = FLOOR_CLEARANCE[style]
    middle = frames[len(frames) // 2]
    hand = middle.hands["r"][:3, :3]
    direction = (hand / np.linalg.norm(hand, axis=0)) @ right.basis[:, 1]
    direction = direction * np.array([-1., 1., 1.])
    hold = float(right.report.get("hold", 0.))
    margins = _margins(points, scale, hold, style)
    tried = []
    for spread in OFFHAND_SPREADS:
        held = _held_out(frames, "l", spread)
        basis = _turned(fighting, held[len(held) // 2], "l", direction)
        origin = fighting.fist - basis @ np.array([0., hold, 0.]) * scale
        lowest, slack, nearest, body, armour = _measure(held, "l", basis, origin, points,
                                                        scale, margins)
        grip = Grip(basis, origin, style=style, lean=right.report["lean"], hold=round(hold, 4),
                    spread=spread, floor=lowest, body=nearest, slack=round(float(slack), 4),
                    body_slack=round(float(body), 4), armour=round(float(armour), 4),
                    clear=bool(slack >= 0 and lowest >= floor - 1e-4))
        if grip.report["clear"]:
            return grip
        tried.append(grip)
    # Of the spreads that go least far into armour, the least that keeps the
    # piece off the body and the floor: holding the arm farther out than that
    # buys nothing the armour does not take back.
    best = max(grip.report["armour"] for grip in tried)
    tried = [grip for grip in tried if grip.report["armour"] >= best - FALLBACK_TOLERANCE]
    for grip in tried:
        if grip.report["body_slack"] >= 0 and grip.report["floor"] >= floor - 1e-4:
            return grip
    best = max(min(grip.report["floor"] - floor, grip.report["body_slack"]) for grip in tried)
    return next(grip for grip in tried
                if min(grip.report["floor"] - floor, grip.report["body_slack"])
                >= best - FALLBACK_TOLERANCE)


def held_grips(rig, race: Path, library: Path, piece: "Piece", mesh: Path,
               fit: float, idle: bool = True,
               bodies: tuple[Path, ...] = ()) -> dict[str, tuple[Grip, Grip | None]]:
    """The fighting and idle grip of one weapon in each hand it can be held
    in: the right always, the left as well for a one-handed class.  ``idle``
    is false for a bow that hands its idle to the ranged presentation, whose
    registry prop is hidden whenever that bow is shown.  Every grip clears
    ``race``'s body and every one of ``bodies`` (``playable_bodies``).

    Modified 2026-10-06 for Eloria Client: the left hand is no longer solved
    as the right hand is.  Its idle grip mirrors the right's
    (``offhand_idle_grip``) and its fighting grip is turned off the shoulder
    the combat idle raises it beside (``offhand_fighting_grip``)."""
    points = _prop_points(mesh)
    roll = (piece.kind in HEADED and _head_side(mesh) < 0) != (piece.source.stem in FIGHTING_TURNED)
    style = rest_style(piece)
    races = tuple(dict.fromkeys(str(body) for body in (race, *bodies)))
    frames = _bodies_frames(races, str(library), IDLE_CLIP, IDLE_SAMPLES, HELD_CLEARANCE_GEAR)
    hold = FIGHTING_HOLDS.get(piece.source.stem, 0.)
    fighting = fighting_grip(rig, "r", fit, roll, hold)
    right = idle_grip(frames, "r", style, fighting, points, fit) if idle else None
    grips = {"r": (fighting, right)}
    if piece.kind in ONE_HANDED:
        left = offhand_fighting_grip(races, str(library), fighting_grip(rig, "l", fit, roll, hold),
                                     points, fit, hold)
        grips["l"] = (left, offhand_idle_grip(frames, right, left, points, fit)
                      if right is not None else None)
    return grips


def floor_point(idle_socket: dict, side: str, rig, race: Path, library: Path,
                mesh: Path, fit: float) -> list[float]:
    """The vertex of the piece its idle grip brings nearest the floor, half
    way through the idle on ``race``, in the piece's own space -- the units
    of its mesh, which is the space of the prop node the client hangs it by.
    WeaponCarryPose sets a planted or leant piece down on it, and keeps
    anything else's off the floor by it when an emote drops the hand.  The
    end of the piece's length is not always what touches: a maul rests on the
    rim of its head, a crescent hangs a tip a hand's width off its haft.

    Added 2026-10-06 for Eloria Client.  Read off the solved socket, so a
    grip kept from the registry or the cache gets one the same as a grip just
    solved."""
    rest = rig.basis("hand_" + side)
    x, y, z = idle_socket["rotationDegrees"]
    basis = rest.T @ Rotation.from_euler("YXZ", [y, x, z], degrees=True).as_matrix()
    origin = rest.T @ np.asarray(idle_socket["offset"], float) * fit
    frame = _held_out(_clip_frames(str(race), str(library), IDLE_CLIP, IDLE_SAMPLES)[IDLE_SAMPLES // 2:][:1],
                      side, float(idle_socket.get("armSpread", 0.)))[0]
    hand = frame.hands[side]
    vertices = _prop_points(mesh, None)
    placed = (hand[:3, :3] @ (basis * fit) @ vertices.T).T + hand[:3, :3] @ origin + hand[:3, 3]
    return [round(float(v), 4) + 0. for v in vertices[int(np.argmin(placed[:, 1]))]]


def rest_style(piece: "Piece") -> str:
    return REST_STYLE_EXCEPTIONS.get(piece.source.stem, REST_STYLE[piece.kind])


def playable_bodies(registry: dict) -> tuple[Path, ...]:
    """Every body a player can be, as the registry's body templates list them."""
    return tuple(ce.RACES / ("%s.glb" % slug) for slug in sorted(registry.get("bodyTemplates", {}))
                 if (ce.RACES / ("%s.glb" % slug)).exists())


def held_fit(rig, registry: dict) -> float:
    """The size the client draws a held prop at on ``rig``: its head height
    over the legacy profile's, as ``ReplicatedActor3D.rig_fit_scale`` does."""
    profile = registry.get("fitProfiles", {}).get(FIT_PROFILE, registry)
    return float(rig.origin("Head")[1]) / float(profile["canonicalHeadRestY"])


#: The shield is worn half again larger than it is authored, pushed clear of the
#: hip, and turned out from the body so its face is seen rather than its edge.
SHIELD_SCALE = 1.5
SHIELD_SPLAY = 25.0
SHIELD_PUSH = 0.10


def _euler_degrees(basis: np.ndarray) -> list[float]:
    """A basis as the XYZ degrees Godot's ``Basis.from_euler`` will rebuild.

    ``from_euler`` composes YXZ, so the angles come out in that order and are
    reordered here.  Checked against both shipped sockets, which round-trip to
    themselves exactly.
    """
    y, x, z = Rotation.from_matrix(basis).as_euler("YXZ", degrees=True)
    return [round(float(x), 5), round(float(y), 5), round(float(z), 5)]


def shield_socket(rig, race: Path, library: Path, base: dict) -> dict:
    """The shield's socket, solved against the idle hand: held in the left
    hand, its face turned out from the body and its top up.

    Modified 2026-10-06 for Eloria Client: this was the shield third of
    ``prop_sockets``, whose weapon two thirds are now ``held_grips``.
    """
    idle = ea._idle_hand_bases(str(race), str(library), IDLE_CLIP)
    # The shield's face is turned out from the body, which for the left hand is
    # the actor's own left, and its top stays up.
    splay = math.radians(SHIELD_SPLAY)
    face = np.array([math.sin(splay), 0., math.cos(splay)])
    up = np.array([0., 1., 0.])
    up = up - face * float(up @ face)
    up /= np.linalg.norm(up)
    desired = np.column_stack((np.cross(up, face), up, face))
    held = rig.basis("hand_l") @ np.linalg.inv(idle["l"]) @ desired
    offset = list(base[1]["offset"])
    offset[2] += SHIELD_PUSH
    return {"bone": "hand_l", "offset": offset,
            "rotationDegrees": _euler_degrees(held)}


class Piece:
    __slots__ = ("source", "slug", "name", "kind", "part", "visual", "item_id",
                 "image_id", "flip", "roll")

    def __init__(self, source, slug, name, kind, part, visual, item_id,
                 image_id, flip, roll):
        self.source, self.slug, self.name, self.kind = source, slug, name, kind
        self.part, self.visual = part, visual
        self.item_id, self.image_id, self.flip = item_id, image_id, flip
        self.roll = roll


def roster() -> list[Piece]:
    """Every generated prop, in a fixed order so ids never move."""
    pieces: list[Piece] = []
    nxt = dict(FIRST_VISUAL)
    for index, (stem, label, kind) in enumerate(DESIGNS):
        source = GENERATED / (stem + ".glb")
        # Only sources that have been through the texture pass, which leaves
        # the raw export beside them as `.glb.orig`.  Same guard the armour
        # importer uses: a raw drop-in would otherwise define an item whose
        # icon and compressed texture do not exist yet.
        if not source.exists() or not source.with_name(
                source.name + ".orig").exists():
            continue
        part = ce.PROP_KIND[kind]["part"]
        pieces.append(Piece(
            source, stem[4:], label, kind, part, nxt[part],
            FIRST_ITEM_ID + index, FIRST_IMAGE_ID + index,
            stem in FLIP_EXCEPTIONS, stem in ROLL_EXCEPTIONS))
        nxt[part] += 1
    return pieces


def design_tier(stem: str) -> int:
    return TIERS.get(stem, DEFAULT_TIER)


def item_block(piece: Piece, served: dict[int, list[str]] | None = None) -> str:
    """One [item] block. `served` is the catalogue's own stat lines, kept.

    The tables below decide what a weapon is worth the FIRST time it is
    defined and never again -- balancing lives in the catalogue, written
    through dev-server/tools/import_equipment_csv.py, and a rewrite of this
    fence carries it across. Without that, running this tool for any other
    reason silently reverts a balance pass, and the diff looks exactly like
    the rewrite doing its job. `--reseed` is the deliberate way back.
    """
    kept = (served or {}).get(piece.item_id)
    if kept is not None:
        weight = [line for line in kept if line.startswith("emu:")]
        category = "Armor" if piece.kind in SHIELD_STATS else "Weapons"
        slot = ("left_hand" if piece.kind in SHIELD_STATS
                else "right_hand" if piece.kind in ONE_HANDED else "both_hands")
        return "\n".join([
            "", "[item]",
            "name: %s" % piece.name,
            "item_id: %d" % piece.item_id,
            "image_id: %d" % piece.image_id,
            *weight,
            "flags: 2",
            "category: %s" % category,
            "description: Generated from the %s concept art." % piece.name.lower(),
            "equip_type: %s" % slot,
            *[line for line in kept if not line.startswith("emu:")],
            "[/item]"])
    stem = piece.source.stem
    tier = design_tier(stem)
    shield = piece.kind in SHIELD_STATS
    themed = list(THEME_STATS.get(stem, ()))
    if shield:
        emu, (low, high), defense, accuracy = SHIELD_STATS[piece.kind]
        low += max(0, tier - 2)
        high += 2 * (tier - 1)
        if tier >= 4:
            defense += 1
        rows = ["armor: %d/%d" % (low, high), "damage: 0/0",
                "accuracy: %d" % accuracy, "defense: %d" % defense]
        category, slot = "Armor", "left_hand"
    else:
        emu, (low, high), accuracy, defense = WEAPON_STATS[piece.kind]
        low += max(0, tier - 2)
        high += 2 * (tier - 1)
        if tier >= 4:
            accuracy += 1
        rows = ["armor: 0/0", "damage: %d/%d" % (low, high),
                "accuracy: %d" % accuracy, "defense: %d" % defense]
        crit = TWO_HANDED_CRIT.get(piece.kind, 0)
        if crit:
            themed.insert(0, ("critical_to_damage", crit))
        category = "Weapons"
        slot = "right_hand" if piece.kind in ONE_HANDED else "both_hands"
    rows.extend("%s: %d" % (key, value) for key, value in themed if value)
    if piece.kind in AMMUNITION_OF:
        rows.append("ranged_ammunition: %s" % AMMUNITION_OF[piece.kind])
        rows.append("missile_speed: %d" % missile_speed(piece.kind, tier))
    return "\n".join([
        "", "[item]",
        "name: %s" % piece.name,
        "item_id: %d" % piece.item_id,
        "image_id: %d" % piece.image_id,
        "emu: %d" % emu,
        "flags: 2",
        "category: %s" % category,
        "description: Generated from the %s concept art." % piece.name.lower(),
        "equip_type: %s" % slot,
        *rows,
        "[/item]"])


#: The keys of a held entry this tool decides, in the order it writes them.
#: Any other key -- a ranged presentation added by a later pass, say -- is kept
#: after them as it was, so re-running this does not undo that pass.
OWNED_KEYS = ("scene", "name", "attach", "socket", "idleSocket", "scale",
              "fitProfile")


def held_entry(previous: dict | None, *, scene: str, name: str,
               socket: dict | None = None, idle_socket: dict | None = None,
               scale: float | None = None) -> dict:
    """One registry entry for a held prop, merged over the one already there.

    A weapon names its two grips, a shield its one socket.  Both are drawn at
    the legacy fit their sockets were solved in, which the entry has to say:
    without it the client sizes the piece by the canonical profile instead,
    two per cent larger than the grip was fitted to.

    A bow the ranged presentation draws keeps the socket it has.  Modified
    2026-10-06 for Eloria Client: its prop is hidden whenever that bow is
    shown, and solving it a fist grip like any other weapon threw away the
    reviewed offset the Amberwood longbow was given (cdd44dea5).
    """
    owned = {"scene": scene, "name": name, "attach": "socket"}
    ranged = "rangedAnimationScene" in (previous or {})
    owned["socket"] = previous["socket"] if ranged and "socket" in previous else socket
    if idle_socket is not None and not ranged:
        owned["idleSocket"] = idle_socket
    if scale is not None:
        owned["scale"] = scale
    owned["fitProfile"] = FIT_PROFILE
    for key, value in (previous or {}).items():
        if key not in OWNED_KEYS:
            owned[key] = value
    return owned


def describe_grip(idle: "Grip | None", fighting: "Grip | None" = None) -> str:
    turned = ""
    if fighting is not None and "turn" in fighting.report:
        turned = "  fist turned %s, touching %s swing frames%s" % (
            tuple(round(float(v)) for v in fighting.report["turn"]),
            fighting.report.get("swings"),
            "" if fighting.report.get("clear") else " (nearest the combat idle comes to clear)")
    if idle is None:
        return "fighting grip only (the ranged presentation holds it at ease)" + turned
    report = idle.report
    return "%-7s lean %-14s floor %+.3f body %+.3f armour %+.3f hold %+.3f%s%s%s" % (
        report["style"], tuple(round(float(v), 1) for v in report["lean"]),
        report["floor"], report["body_slack"], report["armour"], report["hold"],
        "  arm out %.0f" % report["spread"] if report.get("spread") else "",
        "" if report["clear"] else "  (nearest it comes to clear)", turned)


#: Where solved grips are kept between runs, by a digest of everything that
#: decides them (``grip_digest``).  Modified 2026-10-06 for Eloria Client:
#: solving both grips of every piece against every playable body and the kit
#: armour takes the best part of an hour, and every run did it -- even
#: ``--only <piece> --skip-build``.  Kept out of the tree: it is only ever a
#: shortcut to an answer the solve would give again.
GRIP_CACHE = Path(tempfile.gettempdir()) / "eloria-generated-weapon-grips.json"


@lru_cache(maxsize=None)
def _file_digest(path: str) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def _scenes(value) -> list[str]:
    """Every "scene" a registry entry names, its fit variants' included."""
    if isinstance(value, dict):
        return [str(v) for k, v in value.items() if k == "scene"] + [
            scene for v in value.values() for scene in _scenes(v)]
    return [scene for v in value for scene in _scenes(v)] if isinstance(value, list) else []


def grip_digest(piece: "Piece", mesh: Path, race: Path, library: Path,
                bodies: tuple[Path, ...], idle: bool, registry: dict) -> str:
    """Everything a piece's grips are solved from: the solver (this file and
    the two it measures with), the piece and its mesh, the bodies and the
    clips, the armour cleared and how the registry fits it to each body, and
    whether the piece has an idle grip at all."""
    digest = hashlib.sha1()
    for module in (__file__, ce.__file__, ea.__file__):
        digest.update(_file_digest(str(Path(module).resolve())).encode())
    digest.update(("%s|%s|%s" % (piece.source.stem, piece.kind, idle)).encode())
    for path in (mesh, race, library, *bodies):
        digest.update(_file_digest(str(path)).encode())
    fits = {key: registry.get(key) for key in (
        "fitProfiles", "fitGroups", "bodyTemplates", "refittedBodies", "bodyGirth",
        "authoredBodyGirth", "footAnchor", "authoredFootAnchor", "canonicalHeadRestY")}
    fits["gear"] = {key: registry["models"].get(key) for key in HELD_CLEARANCE_GEAR}
    digest.update(json.dumps(fits, sort_keys=True).encode())
    for scene in _scenes(fits["gear"]):
        if _client_path(scene).exists():
            digest.update(_file_digest(str(_client_path(scene))).encode())
    return digest.hexdigest()


def solve_held(piece: "Piece", rig, race: Path, library: Path, registry: dict,
               bodies: tuple[Path, ...], idle: bool, cache: dict,
               regrip: bool = False) -> dict[str, tuple[dict, dict | None, str]]:
    """``piece``'s sockets as the registry stores them, per hand: the fighting
    grip, the idle grip (or None) and a line describing them -- from
    ``cache`` when the digest of what they are solved from is there."""
    mesh = EQUIPMENT / ("%s.glb" % piece.slug)
    digest = grip_digest(piece, mesh, race, library, bodies, idle, registry)
    if not regrip and digest in cache:
        return {side: tuple(value) for side, value in cache[digest].items()}
    fit = held_fit(rig, registry)
    grips = held_grips(rig, race, library, piece, mesh, fit, idle=idle, bodies=bodies)
    solved = {side: (fighting.socket(rig, side, fit),
                     rest.socket(rig, side, fit) if rest is not None else None,
                     describe_grip(rest, fighting))
              for side, (fighting, rest) in grips.items()}
    cache[digest] = solved
    return solved


def load_grip_cache() -> dict:
    try:
        return json.loads(GRIP_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_grip_cache(cache: dict) -> None:
    try:
        GRIP_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def define_held(registry: dict, everything: list["Piece"], solve: set[str], rig,
                race: Path, library: Path, cache: dict, regrip: bool = False,
                log=print) -> None:
    """Every generated prop's entry in ``registry``.  A shield takes the
    socket solved against the idle hand.  A weapon whose slug is in ``solve``
    takes its grips from ``solve_held``; any other keeps the grips it already
    has (a new one is solved anyway), so a run that rebuilds one piece does
    not re-solve eighty."""
    shield = shield_socket(rig, race, library,
                           {int(k): v for k, v in registry["sockets"].items()})
    bodies = playable_bodies(registry)
    log("\ngrips, solved against %s on %s and %d bodies:" % (IDLE_CLIP, race.stem, len(bodies)))
    for p in everything:
        scene = "res://assets/actors/native/equipment/%s.glb" % p.slug
        key = "%d:%d" % (p.part, p.visual)
        if p.part == 1:
            registry["models"][key] = held_entry(
                registry["models"].get(key), scene=scene, name=p.name,
                socket=shield, scale=SHIELD_SCALE)
            continue
        previous = registry["models"].get(key, {})
        idle = "rangedAnimationScene" not in previous
        # The same mesh again, in the left hand, for the weapons a player may
        # hold two of.  A two-handed weapon has no off-hand entry because
        # nothing can be worn beside it.
        keys = {"r": key, "l": "1:%d" % offhand_visual(p.visual)} if p.kind in ONE_HANDED else {"r": key}
        kept = {side: registry["models"].get(entry, {}) for side, entry in keys.items()}
        if p.slug in solve or not all("socket" in entry and ("idleSocket" in entry or not idle)
                                      for entry in kept.values()):
            solved = solve_held(p, rig, race, library, registry, bodies, idle, cache, regrip)
            save_grip_cache(cache)
        else:
            solved = {side: (entry["socket"], entry.get("idleSocket"), "kept")
                      for side, entry in kept.items()}
        for side, entry in keys.items():
            socket, idle_socket, description = solved[side]
            if idle_socket is not None:
                idle_socket = dict(idle_socket, floorPoint=floor_point(
                    idle_socket, side, rig, race, library, EQUIPMENT / ("%s.glb" % p.slug),
                    held_fit(rig, registry)))
            registry["models"][entry] = held_entry(
                registry["models"].get(entry), scene=scene,
                name=p.name if side == "r" else "%s (off hand)" % p.name,
                socket=socket, idle_socket=idle_socket)
            log("  %-32s %-10s %s" % (p.slug if side == "r" else "  (off hand)",
                                      p.kind if side == "r" else "", description))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="build the generated weapon set and define it on both sides")
    ap.add_argument("--race", default="luminous_male")
    ap.add_argument("--only", default=None,
                    help="only pieces whose slug or kind contains this")
    ap.add_argument("--server", type=Path, default=SERVER)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reseed", action="store_true",
                    help="recompute every stat from its class and tier "
                         "instead of keeping what the catalogue has. This "
                         "discards balancing done through "
                         "import_equipment_csv.py")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--regrip", action="store_true",
                    help="solve every weapon's grips afresh, ignoring the "
                         "grips the registry has and the cache of solved ones")
    args = ap.parse_args()

    # `--only` narrows what is *built*, never what is defined.  The server
    # blocks are one marker-fenced region rewritten whole, so writing them from
    # a filtered roster deletes every piece the filter excluded -- a one-piece
    # rebuild would take the other ninety-nine out of the catalogue with it.
    everything = roster()
    pieces = everything
    if args.only:
        pieces = [p for p in everything
                  if args.only in p.slug or args.only == p.kind]
    if not pieces:
        print("nothing to do (are the meshes generated and texture-shrunk?)")
        return 2

    import collections
    print("%d prop(s): %s" % (len(pieces), ", ".join(
        "%s x%d" % (k, n) for k, n in
        sorted(collections.Counter(p.kind for p in pieces).items()))))
    if args.dry_run:
        for p in pieces:
            print("  %-32s %-11s part %d visual %-4d item %d image %d"
                  % (p.slug, p.kind, p.part, p.visual, p.item_id, p.image_id))
        print("\nnothing written (--dry-run)")
        return 0

    # An item's name is the only thing joining its definition to its geometry,
    # so two items sharing one is not a cosmetic clash: the catalogue refuses to
    # load, and if it did not, the pair would resolve to each other's models.
    # Checked against the catalogue as it stands minus this set's own fence,
    # so re-running is not mistaken for a collision with itself.
    items_path = args.server / "config/eloria/items.txt"
    catalogue = items_path.read_text(encoding="utf-8")
    if OPEN_ITEMS in catalogue:
        head, _, rest = catalogue.partition(OPEN_ITEMS)
        catalogue = head + rest.partition(CLOSE_ITEMS)[2]
    taken = {line.partition(":")[2].strip().casefold()
             for line in catalogue.splitlines() if line.startswith("name:")}
    clash = sorted(p.name for p in everything if p.name.casefold() in taken)
    if clash:
        print("these names are already in the catalogue: %s"
              % ", ".join(clash), file=sys.stderr)
        return 2

    rig = ea.load_rig(ce.RACES / ("%s.glb" % args.race), ce.BODY_MESH)
    built = failed = 0
    if not args.skip_build:
        EQUIPMENT.mkdir(parents=True, exist_ok=True)
        for p in pieces:
            try:
                info = ce.build(p.source, EQUIPMENT / ("%s.glb" % p.slug), rig,
                                p.kind, p.name, flip=p.flip, roll=p.roll,
                                grip=GRIP_POINTS.get(p.source.stem))
            except Exception as exc:                      # noqa: BLE001
                print("  FAILED %-30s %s" % (p.slug, exc))
                failed += 1
                continue
            built += 1
            print("  %-32s %-11s %5d verts  %.2f MB"
                  % (p.slug, p.kind, info["vertices"], info["bytes"] / 1e6))

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    race = ce.RACES / ("%s.glb" % args.race)
    library = CLIENT / "assets/actors/native/shared/Universal_Animation_Library.glb"
    # The grips of the pieces built now are solved (or found in the cache);
    # with --regrip, every piece's are solved afresh.
    define_held(registry, everything,
                {p.slug for p in (everything if args.regrip else pieces)},
                rig, race, library, load_grip_cache(), regrip=args.regrip)
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n",
                        encoding="utf-8")

    items = args.server / "config/eloria/items.txt"
    served = {} if args.reseed else armour.served_stats(
        items.read_text(encoding="utf-8"))
    if args.reseed:
        print("--reseed: %d piece(s) go back to their computed stats, "
              "discarding any balancing done in the catalogue" % len(everything))
    body = "\n".join(item_block(p, served)
                    for p in everything).lstrip("\n")
    items.write_text(
        armour.fence(items.read_text(encoding="utf-8"), OPEN_ITEMS,
                     CLOSE_ITEMS, body), encoding="utf-8")

    items_py = args.server / "eloria/items.py"
    source = items_py.read_text(encoding="utf-8")
    rows = "\n".join('    "%s": (%d, %d),' % (p.name.casefold(), p.part,
                                              p.visual) for p in everything)
    if OPEN_PY in source:
        source = armour.fence(source, OPEN_PY, CLOSE_PY, rows)
    else:
        anchor = armour.CLOSE_PY + "\n"
        if anchor not in source:
            print("could not find the armour set's override block to sit after")
            return 2
        source = source.replace(
            anchor, anchor + "%s\n%s\n%s\n" % (OPEN_PY, rows, CLOSE_PY), 1)
    items_py.write_text(source, encoding="utf-8")

    print("\n%d built, %d failed" % (built, failed))
    for label, path in (("meshes", EQUIPMENT), ("registry", REGISTRY),
                        ("items", items), ("visuals", items_py)):
        print("  %-9s %s" % (label, path))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
