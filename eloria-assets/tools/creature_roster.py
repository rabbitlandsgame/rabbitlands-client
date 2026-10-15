#!/usr/bin/env python3
"""The Nymara creature roster, keyed to the supplied concept-art sheets.

Each entry records the creature slug, display name, skeleton family, body
plan, palette, scale and the concept-art cell it was authored from, so any
model can be traced back to the artwork that defines it.

Palettes are *sampled from the artwork* by
``eloria-assets/tools/extract_concept_palettes.py`` rather than guessed by
hand, which is why they are exact triples rather than round numbers.

``sheet`` is the concept image stem; ``cell`` is (row, column) in that
sheet's 4x3 grid.  Several sheets are alternate renders of the same roster
(``47a41963``/``4dc46727`` and ``93197c59``/``1e840e1e``), and the three
Amberwood sheets share many subjects, so ``ALIAS_CELLS`` maps every duplicate
cell onto the model that already covers it.
"""
from __future__ import annotations

# slug, display name, family, plan, base rgb, accent rgb, scale, sheet, row, col
ROSTER = (
    # ---- Amethyst Barrens: crystal-grown fauna -------------------------
    ("amethyst_scorpion", "Amethyst Scorpion", "arachnid", "scorpion",
     (93, 82, 205), (52, 48, 152), 1.05, "47a41963", 0, 0),
    ("geode_scarab", "Geode Scarab", "insect", "beetle",
     (58, 71, 205), (40, 69, 143), .80, "47a41963", 0, 1),
    ("prism_drake", "Prism Drake", "quadruped", "sprawler",
     (69, 83, 151), (171, 181, 224), 1.22, "47a41963", 0, 2),
    ("shardling_swarm", "Shardling Swarm", "amorphous", "shards",
     (65, 81, 205), (43, 56, 154), .92, "47a41963", 0, 3),
    ("barrens_wisp", "Barrens Wisp", "amorphous", "wisp",
     (37, 61, 159), (135, 169, 224), .78, "47a41963", 1, 0),
    ("amethyst_golem", "Amethyst Golem", "biped", "golem",
     (78, 73, 114), (178, 175, 224), 1.55, "47a41963", 1, 1),
    ("crystalwing", "Crystalwing", "quadruped", "drake",
     (61, 66, 159), (170, 179, 224), 1.18, "47a41963", 1, 2),
    ("geode_tortoise", "Geode Tortoise", "quadruped", "chelonian",
     (106, 93, 194), (175, 180, 224), 1.10, "47a41963", 1, 3),
    ("facet_hound", "Facet Hound", "quadruped", "canid",
     (72, 75, 135), (155, 174, 224), 1.14, "47a41963", 2, 0),
    ("prism_moth", "Prism Moth", "insect", "moth",
     (61, 80, 205), (48, 58, 146), .88, "47a41963", 2, 1),
    ("lattice_spider", "Lattice Spider", "arachnid", "spider",
     (66, 67, 171), (181, 179, 224), 1.00, "47a41963", 2, 2),
    ("orrery_sentinel", "Orrery Sentinel", "biped", "construct",
     (91, 94, 139), (73, 107, 224), 1.42, "47a41963", 2, 3),

    # ---- Elemental lords: regional boss tier ---------------------------
    # Cell 0,0 of the elemental-lords sheet is the *drowned lich king*, and
    # this entry had been keyed to it: the name said forest monarch while the
    # art -- and therefore the sampled palette -- was a teal-and-gold drowned
    # king.  The lich now has its own entry at the end of the roster and keeps
    # that cell and that palette.  This one keeps its actor type and becomes
    # what its name says, authored rather than measured: no cell in the
    # supplied art shows a verdant crown king, so ``authored`` marks it as
    # having no concept figure to be compared against.  Its palette is a
    # choice, not a measurement -- deep forest green under old gold.
    ("verdant_crown_king", "Verdant Crown King", "biped", "monarch",
     (54, 92, 58), (198, 166, 84), 1.72, "authored", 0, 0),
    ("tidegold_wyrm", "Tidegold Wyrm", "serpent", "wyrm",
     (67, 98, 104), (73, 191, 224), 1.85, "f1bb1663", 0, 1),
    ("rimebound_archmage", "Rimebound Archmage", "biped", "mage",
     (78, 105, 132), (148, 199, 224), 1.62, "f1bb1663", 0, 2),
    ("glacier_brute", "Glacier Brute", "biped", "brute",
     (80, 121, 155), (175, 200, 213), 1.80, "f1bb1663", 0, 3),
    ("orrery_colossus", "Orrery Colossus", "biped", "construct",
     (103, 79, 74), (198, 194, 196), 1.78, "f1bb1663", 1, 0),
    ("amethyst_sibyl", "Amethyst Sibyl", "biped", "mage",
     (83, 77, 136), (130, 131, 224), 1.58, "f1bb1663", 1, 1),
    ("crimson_duelist", "Crimson Duelist", "biped", "duelist",
     (105, 59, 69), (209, 198, 182), 1.60, "f1bb1663", 1, 2),
    ("emberwood_matron", "Emberwood Matron", "biped", "treant",
     (99, 73, 26), (224, 215, 145), 1.75, "f1bb1663", 1, 3),
    ("barrow_sovereign", "Barrow Sovereign", "biped", "knight",
     (57, 60, 61), (173, 213, 202), 1.70, "f1bb1663", 2, 0),
    ("gilded_devourer", "Gilded Devourer", "amorphous", "tentacles",
     (100, 79, 79), (224, 190, 135), 1.66, "f1bb1663", 2, 1),
    ("tidecaller_sorceress", "Tidecaller Sorceress", "biped", "mage",
     (79, 106, 101), (135, 220, 224), 1.58, "f1bb1663", 2, 2),
    ("mirefather_leviathan", "Mirefather Leviathan", "amorphous", "tentacles",
     (81, 96, 63), (208, 221, 158), 1.92, "f1bb1663", 2, 3),

    # ---- Sunmane Steppe ------------------------------------------------
    ("goldmane_aurochs", "Goldmane Aurochs", "quadruped", "bovine",
     (167, 103, 37), (224, 206, 158), 1.42, "93197c59", 0, 1),
    ("dunburrow_mole", "Dunburrow Mole", "quadruped", "mustelid",
     (133, 84, 46), (224, 167, 113), .78, "93197c59", 0, 3),
    ("plumed_crane", "Plumed Crane", "avian", "wader",
     (178, 126, 70), (224, 115, 15), 1.16, "93197c59", 1, 0),
    ("sunmane_minotaur", "Sunmane Minotaur", "biped", "brute",
     (151, 87, 21), (224, 191, 133), 1.68, "93197c59", 1, 1),
    ("stormmane_lion", "Stormmane Lion", "quadruped", "felid",
     (205, 126, 28), (122, 81, 49), 1.30, "93197c59", 1, 2),
    ("grasswing_mantis", "Grasswing Mantis", "insect", "mantis",
     (184, 147, 31), (224, 194, 38), 1.05, "93197c59", 2, 0),
    ("dust_hyena", "Dust Hyena", "quadruped", "canid",
     (162, 95, 39), (224, 147, 63), 1.08, "93197c59", 2, 1),
    ("steppe_jackrabbit", "Steppe Jackrabbit", "quadruped", "lagomorph",
     (204, 133, 58), (224, 201, 160), .70, "93197c59", 2, 2),
    ("sunmane_gryphon", "Sunmane Gryphon", "quadruped", "gryphon",
     (144, 116, 84), (224, 200, 157), 1.34, "93197c59", 2, 3),

    # ---- Crownwater ----------------------------------------------------
    ("crownwater_turtle", "Crownwater Turtle", "quadruped", "chelonian",
     (121, 115, 78), (224, 204, 154), 1.16, "bc78bfcc", 0, 0),
    ("tidefin_naga", "Tidefin Naga", "biped", "warrior",
     (117, 143, 129), (224, 159, 74), 1.44, "bc78bfcc", 0, 1),
    ("lanternwyrm", "Lanternwyrm", "serpent", "sea_serpent",
     (55, 124, 141), (224, 167, 32), 1.55, "bc78bfcc", 0, 2),
    ("crownwater_wyvern", "Crownwater Wyvern", "quadruped", "drake",
     (59, 147, 157), (224, 173, 106), 1.40, "bc78bfcc", 0, 3),
    ("cascade_golem", "Cascade Golem", "biped", "golem",
     (91, 108, 71), (204, 207, 177), 1.62, "bc78bfcc", 1, 0),
    ("tidecoil_serpent", "Tidecoil Serpent", "serpent", "sea_serpent",
     (53, 136, 205), (51, 69, 132), 1.48, "bc78bfcc", 1, 1),
    ("palecrest_crab", "Palecrest Crab", "arachnid", "crab",
     (144, 145, 111), (208, 205, 175), 1.02, "bc78bfcc", 1, 2),
    ("riverbank_ibis", "Riverbank Ibis", "avian", "wader",
     (119, 121, 106), (219, 203, 166), 1.10, "bc78bfcc", 1, 3),
    ("algae_alligator", "Algae Alligator", "quadruped", "sprawler",
     (74, 109, 70), (224, 193, 50), 1.50, "bc78bfcc", 2, 0),
    ("springfly_sprite", "Springfly Sprite", "amorphous", "sprite",
     (62, 147, 205), (49, 106, 145), .74, "bc78bfcc", 2, 1),
    ("gilded_water_lion", "Gilded Water Lion", "quadruped", "felid",
     (89, 132, 116), (12, 156, 224), 1.36, "bc78bfcc", 2, 2),
    ("medusa_tidepriest", "Medusa Tidepriest", "amorphous", "tentacles",
     (61, 104, 97), (17, 171, 224), 1.40, "bc78bfcc", 2, 3),

    # ---- Westhaven -----------------------------------------------------
    ("courier_otter", "Courier Otter", "quadruped", "mustelid",
     (110, 85, 71), (220, 199, 169), .82, "4cf4bb0e", 0, 0),
    ("message_swallow", "Message Swallow", "avian", "songbird",
     (95, 85, 88), (224, 199, 166), .52, "4cf4bb0e", 0, 1),
    ("harborshell_crab", "Harborshell Crab", "arachnid", "crab",
     (106, 94, 64), (224, 206, 151), 1.00, "4cf4bb0e", 0, 2),
    ("brassband_pike", "Brassband Pike", "fish", "pike",
     (115, 121, 82), (224, 200, 141), 1.18, "4cf4bb0e", 0, 3),
    ("reedhat_fisher", "Reedhat Fisher", "biped", "warrior",
     (102, 76, 58), (224, 192, 154), 1.42, "4cf4bb0e", 1, 0),
    ("ratcatcher_tough", "Ratcatcher Tough", "biped", "warrior",
     (93, 71, 56), (209, 203, 175), 1.40, "4cf4bb0e", 1, 1),
    ("verdigris_beetle", "Verdigris Beetle", "insect", "beetle",
     (113, 93, 47), (205, 221, 163), .86, "4cf4bb0e", 1, 2),
    ("lanternwake_sprite", "Lanternwake Sprite", "amorphous", "sprite",
     (70, 186, 166), (117, 96, 39), .92, "4cf4bb0e", 1, 3),
    ("millstone_golem", "Millstone Golem", "biped", "golem",
     (122, 107, 73), (224, 201, 156), 1.66, "4cf4bb0e", 2, 0),
    ("drowned_dockhand", "Drowned Dockhand", "biped", "revenant",
     (82, 89, 82), (60, 211, 224), 1.44, "4cf4bb0e", 2, 1),
    ("sluice_elemental", "Sluice Elemental", "amorphous", "vortex",
     (42, 165, 194), (84, 205, 224), 1.24, "4cf4bb0e", 2, 2),
    ("waterwheel_golem", "Waterwheel Golem", "biped", "construct",
     (107, 112, 80), (61, 201, 224), 1.70, "4cf4bb0e", 2, 3),

    # ---- Drowned Crown coast -------------------------------------------
    ("harbor_gull", "Harbor Gull", "avian", "seabird",
     (155, 148, 162), (196, 196, 196), .70, "5b11c39c", 0, 0),
    ("rockshell_crab", "Rockshell Crab", "arachnid", "crab",
     (138, 73, 39), (224, 182, 136), .94, "5b11c39c", 0, 1),
    ("harbor_seal", "Harbor Seal", "quadruped", "pinniped",
     (119, 122, 124), (199, 197, 192), 1.16, "5b11c39c", 0, 2),
    ("kelpback_turtle", "Kelpback Turtle", "quadruped", "chelonian",
     (103, 102, 86), (224, 202, 156), 1.24, "5b11c39c", 0, 3),
    ("bluewater_marlin", "Bluewater Marlin", "fish", "billfish",
     (90, 105, 118), (224, 179, 61), 1.44, "5b11c39c", 1, 0),
    ("saltmarsh_crocodile", "Saltmarsh Crocodile", "quadruped", "sprawler",
     (107, 95, 72), (214, 201, 173), 1.52, "5b11c39c", 1, 1),
    ("bilge_rat", "Bilge Rat", "quadruped", "mustelid",
     (113, 83, 70), (224, 172, 151), .80, "5b11c39c", 1, 2),
    ("spinefin_eel", "Spinefin Eel", "serpent", "eel",
     (74, 88, 103), (224, 136, 70), 1.30, "5b11c39c", 1, 3),
    ("barnacle_troll", "Barnacle Troll", "biped", "brute",
     (86, 89, 72), (200, 202, 186), 1.72, "5b11c39c", 2, 0),
    ("drowned_captain", "Drowned Captain", "biped", "revenant",
     (76, 73, 69), (209, 199, 180), 1.50, "5b11c39c", 2, 1),
    ("glowmantle_ray", "Glowmantle Ray", "fish", "ray",
     (68, 121, 142), (9, 194, 224), 1.36, "5b11c39c", 2, 2),
    ("deepplate_coelacanth", "Deepplate Coelacanth", "fish", "armored",
     (59, 99, 125), (12, 178, 224), 1.30, "5b11c39c", 2, 3),

    # ---- Grey Moors ----------------------------------------------------
    ("moor_pony", "Moor Pony", "quadruped", "equine",
     (91, 74, 58), (215, 195, 178), 1.10, "2dd667c5", 0, 0),
    ("moorhorn_ram", "Moorhorn Ram", "quadruped", "cervid",
     (67, 59, 48), (224, 198, 145), 1.16, "2dd667c5", 0, 1),
    ("moor_heron", "Moor Heron", "avian", "wader",
     (92, 83, 79), (203, 197, 189), 1.12, "2dd667c5", 0, 2),
    ("cairnback_tortoise", "Cairnback Tortoise", "quadruped", "chelonian",
     (94, 80, 44), (221, 203, 164), 1.14, "2dd667c5", 0, 3),
    ("moorfell_wolf", "Moorfell Wolf", "quadruped", "canid",
     (71, 59, 44), (224, 183, 128), 1.20, "2dd667c5", 1, 0),
    ("reedmask_stalker", "Reedmask Stalker", "biped", "warrior",
     (89, 72, 40), (224, 179, 121), 1.46, "2dd667c5", 1, 1),
    ("moorlight_wisp", "Moorlight Wisp", "amorphous", "wisp",
     (113, 174, 178), (91, 134, 148), .84, "2dd667c5", 1, 2),
    ("barrow_knight", "Barrow Knight", "biped", "knight",
     (76, 98, 75), (129, 224, 205), 1.52, "2dd667c5", 1, 3),
    ("cairn_golem", "Cairn Golem", "biped", "golem",
     (84, 83, 51), (193, 205, 190), 1.60, "2dd667c5", 2, 0),
    ("lantern_wraith", "Lantern Wraith", "biped", "revenant",
     (64, 88, 75), (120, 224, 215), 1.48, "2dd667c5", 2, 1),
    ("spectral_moor_stag", "Spectral Moor Stag", "quadruped", "cervid",
     (83, 154, 150), (118, 224, 215), 1.30, "2dd667c5", 2, 2),
    ("barrow_king", "Barrow King", "biped", "monarch",
     (76, 93, 86), (152, 224, 208), 1.66, "2dd667c5", 2, 3),

    # ---- Mirrorhold ----------------------------------------------------
    ("tidelance_construct", "Tidelance Construct", "amorphous", "vortex",
     (97, 124, 79), (79, 217, 224), 1.16, "53a67c51", 0, 0),
    ("reefplate_golem", "Reefplate Golem", "quadruped", "ursine",
     (131, 129, 104), (224, 197, 166), 1.48, "53a67c51", 0, 1),
    ("mirrorhold_wheelwarden", "Mirrorhold Wheelwarden", "biped", "construct",
     (98, 101, 68), (147, 218, 223), 1.68, "53a67c51", 0, 2),
    ("verdigris_warden", "Verdigris Warden", "biped", "construct",
     (74, 115, 94), (190, 217, 181), 1.56, "53a67c51", 0, 3),
    ("palewater_wyrm", "Palewater Wyrm", "serpent", "sea_serpent",
     (72, 187, 205), (36, 96, 120), 1.52, "53a67c51", 1, 0),
    ("mirrorwing_swarm", "Mirrorwing Swarm", "amorphous", "shards",
     (89, 175, 201), (78, 124, 144), 1.02, "53a67c51", 1, 1),
    ("shattered_sentinel", "Shattered Sentinel", "biped", "golem",
     (95, 106, 81), (78, 192, 224), 1.50, "53a67c51", 1, 2),
    ("mirrorhold_oracle", "Mirrorhold Oracle", "biped", "mage",
     (58, 139, 165), (55, 185, 224), 1.52, "53a67c51", 1, 3),
    ("tideguard_vanguard", "Tideguard Vanguard", "biped", "knight",
     (69, 108, 101), (46, 185, 224), 1.54, "53a67c51", 2, 0),
    ("mirrorhold_siren", "Mirrorhold Siren", "serpent", "naga",
     (102, 130, 127), (213, 204, 172), 1.44, "53a67c51", 2, 1),
    ("shardbound_archivist", "Shardbound Archivist", "amorphous", "shards",
     (77, 157, 171), (85, 211, 224), 1.30, "53a67c51", 2, 2),
    ("mirrorhold_loremaster", "Mirrorhold Loremaster", "biped", "mage",
     (79, 130, 125), (59, 192, 224), 1.64, "53a67c51", 2, 3),

    # ---- Manymouth Delta -----------------------------------------------
    ("mudflat_crab", "Mudflat Crab", "arachnid", "crab",
     (103, 74, 39), (215, 204, 169), .96, "4bbc1f8e", 0, 0),
    ("delta_heron", "Delta Heron", "avian", "wader",
     (105, 85, 55), (216, 200, 173), 1.12, "4bbc1f8e", 0, 1),
    ("voltfin_eel", "Voltfin Eel", "serpent", "eel",
     (59, 80, 72), (121, 220, 224), 1.26, "4bbc1f8e", 1, 1),
    ("reed_stalker", "Reed Stalker", "quadruped", "sprawler",
     (89, 73, 38), (224, 197, 139), 1.10, "4bbc1f8e", 1, 2),
    ("mangrove_turtle", "Mangrove Turtle", "quadruped", "chelonian",
     (93, 86, 39), (224, 197, 151), 1.30, "4bbc1f8e", 1, 3),
    ("bog_warden", "Bog Warden", "biped", "construct",
     (78, 86, 56), (210, 210, 167), 1.62, "4bbc1f8e", 2, 0),
    ("frogspear_warrior", "Frogspear Warrior", "biped", "warrior",
     (85, 72, 49), (224, 202, 149), 1.34, "4bbc1f8e", 2, 1),
    ("reed_drake", "Reed Drake", "quadruped", "sprawler",
     (89, 76, 40), (224, 195, 148), 1.24, "4bbc1f8e", 2, 2),
    ("manymouth_hydra", "Manymouth Hydra", "serpent", "hydra",
     (83, 88, 54), (224, 169, 83), 1.72, "4bbc1f8e", 2, 3),

    # ---- Verdant Stair -------------------------------------------------
    ("emerald_basilisk", "Emerald Basilisk", "quadruped", "sprawler",
     (85, 113, 52), (224, 120, 13), .96, "66616a1d", 0, 0),
    ("leaf_mantis", "Leaf Mantis", "insect", "mantis",
     (127, 125, 21), (161, 224, 78), 1.02, "66616a1d", 0, 1),
    ("dartback_treefrog", "Dartback Tree Frog", "quadruped", "anuran",
     (81, 148, 51), (224, 73, 8), .62, "66616a1d", 0, 2),
    ("plumefire_hummingbird", "Plumefire Hummingbird", "avian", "songbird",
     (205, 101, 76), (224, 137, 63), .48, "66616a1d", 0, 3),
    ("vinecoil_snake", "Vinecoil Snake", "serpent", "snake",
     (82, 94, 37), (224, 126, 10), 1.16, "66616a1d", 1, 0),
    ("canopy_lynx", "Canopy Lynx", "quadruped", "felid",
     (119, 93, 50), (224, 173, 88), 1.08, "66616a1d", 1, 1),
    ("mossback_anteater", "Mossback Anteater", "quadruped", "ursine",
     (112, 88, 38), (224, 174, 91), 1.26, "66616a1d", 1, 2),
    ("bloomtail_axolotl", "Bloomtail Axolotl", "fish", "axolotl",
     (21, 103, 179), (8, 185, 224), .92, "66616a1d", 1, 3),
    ("canopy_gorilla", "Canopy Gorilla", "biped", "primate",
     (94, 64, 38), (224, 156, 78), 1.52, "66616a1d", 2, 0),
    ("vine_treant", "Vine Treant", "biped", "treant",
     (93, 86, 29), (224, 190, 68), 1.66, "66616a1d", 2, 1),
    # Cell 11 of the Verdant Stair sheet is a river *naga* -- a woman with a
    # water-serpent tail -- not a formless elemental.  Built on the amorphous
    # vortex plan it came out as a cloud of acid-green shards with two floating
    # orbs, which is not any part of what the art shows.  The accent came back
    # yellow-green from a figure whose highlights are pale cyan.
    ("verdant_naiad", "Verdant Naiad", "serpent", "naga",
     (50, 172, 178), (176, 232, 236), 1.28, "66616a1d", 2, 2),
    ("verdant_stair_dragon", "Verdant Stair Dragon", "quadruped", "drake",
     (66, 139, 83), (221, 224, 67), 1.62, "66616a1d", 2, 3),

    # ---- Whitehorn Range -----------------------------------------------
    ("rime_harpy", "Rime Harpy", "avian", "harpy",
     (87, 144, 205), (24, 110, 224), 1.28, "15c7630b", 1, 0),
    ("glacier_golem", "Glacier Golem", "biped", "golem",
     (81, 133, 177), (42, 76, 134), 1.62, "15c7630b", 1, 1),
    ("whitehorn_yak", "Whitehorn Yak", "quadruped", "bovine",
     (148, 152, 165), (68, 76, 108), 1.40, "15c7630b", 1, 3),
    ("rimeshell_crab", "Rimeshell Crab", "arachnid", "crab",
     (8, 107, 205), (8, 63, 185), 1.06, "15c7630b", 2, 0),
    ("hoarfrost_serpent", "Hoarfrost Serpent", "serpent", "snake",
     (45, 133, 205), (12, 102, 224), 1.34, "15c7630b", 2, 1),
    ("glacier_eagle", "Glacier Eagle", "avian", "raptor",
     (59, 148, 205), (38, 72, 142), 1.14, "15c7630b", 2, 2),
    ("frostplate_knight", "Frostplate Knight", "biped", "knight",
     (74, 118, 160), (55, 160, 224), 1.58, "15c7630b", 2, 3),

    # ---- Amberwood -----------------------------------------------------
    ("emberwing_moth", "Emberwing Moth", "insect", "moth",
     (205, 89, 18), (224, 151, 34), .92, "a5ba7c19", 0, 3),
    ("amberwood_owl", "Amberwood Owl", "avian", "owl",
     (120, 71, 31), (224, 167, 101), .96, "a5ba7c19", 1, 0),
    ("bramble_wolf", "Bramble Wolf", "quadruped", "canid",
     (108, 68, 44), (224, 153, 98), 1.18, "a5ba7c19", 1, 1),
    ("moss_troll", "Moss Troll", "biped", "brute",
     (120, 83, 24), (224, 173, 100), 1.64, "a5ba7c19", 1, 2),
    ("amberwood_treant", "Amberwood Treant", "biped", "treant",
     (120, 74, 23), (224, 168, 93), 1.72, "a5ba7c19", 1, 3),
    ("ivy_hound", "Ivy Hound", "quadruped", "canid",
     (109, 87, 60), (216, 195, 178), 1.10, "a5ba7c19", 2, 0),
    ("thorn_revenant", "Thorn Revenant", "biped", "revenant",
     (72, 67, 69), (156, 210, 222), 1.46, "a5ba7c19", 2, 1),
    ("spectral_highwayman", "Spectral Highwayman", "biped", "revenant",
     (78, 92, 104), (136, 195, 224), 1.50, "a5ba7c19", 2, 2),
    ("lantern_stag", "Lantern Stag", "quadruped", "cervid",
     (98, 57, 38), (224, 132, 41), 1.40, "a5ba7c19", 2, 3),
    ("moss_badger", "Moss Badger", "quadruped", "mustelid",
     (115, 90, 47), (223, 194, 171), .92, "c09f0eed", 1, 0),
    ("bramble_stag", "Bramble Stag", "quadruped", "cervid",
     (117, 66, 33), (224, 174, 119), 1.32, "c09f0eed", 1, 1),
    ("leafling_sprite", "Leafling Sprite", "biped", "treant",
     (122, 80, 13), (224, 175, 52), .72, "c09f0eed", 1, 2),
    ("ember_wisp", "Ember Wisp", "amorphous", "wisp",
     (205, 103, 13), (224, 208, 119), .86, "c09f0eed", 2, 0),
    ("ivy_stone_golem", "Ivy Stone Golem", "biped", "golem",
     (90, 90, 51), (224, 191, 131), 1.64, "c09f0eed", 2, 2),
    ("amberwood_dryad", "Amberwood Dryad", "biped", "mage",
     (103, 62, 46), (224, 170, 122), 1.56, "c09f0eed", 2, 3),
    ("moss_bear", "Moss Bear", "quadruped", "ursine",
     (109, 86, 41), (224, 176, 59), 1.36, "4250fde7", 0, 3),
    ("amberwood_scarecrow", "Amberwood Scarecrow", "biped", "revenant",
     (142, 80, 30), (213, 198, 177), 1.42, "4250fde7", 1, 3),
    ("amberwood_ghost_knight", "Amberwood Ghost Knight", "biped", "knight",
     (98, 104, 79), (188, 207, 193), 1.52, "4250fde7", 2, 1),

    # Appended last on purpose.  Actor types are assigned by roster position,
    # so inserting anywhere earlier renumbers every creature after it and
    # changes what an existing actor id means -- placed one line higher, this
    # entry moved the Amberwood Ghost Knight from 566 to 567.  Last, it takes
    # 567 and nothing else moves.  Keyed to the cell the artwork actually
    # occupies, with the palette already sampled from that figure.
    ("drowned_lich_king", "Drowned Lich King", "biped", "monarch",
     (51, 86, 86), (156, 222, 209), 1.76, "f1bb1663", 0, 0),
)

# Concept cells already represented by an existing or listed model.
ALIAS_CELLS = {
    # Alternate renders of the Amethyst Barrens sheet.
    **{("4dc46727", r, c): slug for (slug, _n, _f, _p, _b, _a, _s, sheet, r, c)
       in ROSTER if sheet == "47a41963"},
    # Alternate renders of the Sunmane Steppe sheet.
    **{("1e840e1e", r, c): slug for (slug, _n, _f, _p, _b, _a, _s, sheet, r, c)
       in ROSTER if sheet == "93197c59"},
    # Cells covered by creatures built in the previous pass.
    ("93197c59", 0, 0): "sunmane_steppe_horse",
    ("93197c59", 0, 2): "emberfox",
    ("93197c59", 1, 3): "desert_tortoise",
    ("1e840e1e", 0, 0): "sunmane_steppe_horse",
    ("1e840e1e", 0, 2): "emberfox",
    ("1e840e1e", 1, 3): "desert_tortoise",
    ("15c7630b", 0, 0): "mountain_goat",
    ("15c7630b", 0, 1): "snow_hare",
    ("15c7630b", 0, 2): "frost_maw",
    ("15c7630b", 0, 3): "ice_bear",
    ("15c7630b", 1, 2): "frost_tiger",
    ("4bbc1f8e", 0, 2): "miretoad",
    ("4bbc1f8e", 0, 3): "giant_komodo",
    ("4bbc1f8e", 1, 0): "giant_crocodile",
    ("a5ba7c19", 0, 0): "elk",
    ("a5ba7c19", 0, 1): "mossback_boar",
    ("a5ba7c19", 0, 2): "red_fox",
    # Amberwood sheets repeat one another's subjects.
    ("c09f0eed", 0, 0): "elk",
    ("c09f0eed", 0, 1): "mossback_boar",
    ("c09f0eed", 0, 2): "red_fox",
    ("c09f0eed", 0, 3): "amberwood_owl",
    ("c09f0eed", 1, 3): "bramble_wolf",
    ("c09f0eed", 2, 1): "amberwood_ghost_knight",
    ("4250fde7", 0, 0): "elk",
    ("4250fde7", 0, 1): "mossback_boar",
    ("4250fde7", 0, 2): "red_fox",
    ("4250fde7", 1, 0): "amberwood_owl",
    ("4250fde7", 1, 1): "bramble_wolf",
    ("4250fde7", 1, 2): "moss_troll",
    ("4250fde7", 2, 0): "amberwood_treant",
    ("4250fde7", 2, 2): "ivy_hound",
    ("4250fde7", 2, 3): "emberwing_moth",
    # Westhaven otter and coastal fauna already have a first-pass model.
    ("4cf4bb0e", 0, 0): "courier_otter",
}

# Stems that are real concept sheets.  ``authored`` is the sentinel for a
# creature with no figure in the supplied art; tools that iterate the sheets to
# sample or segment them must skip it.
CONCEPT_SHEETS = frozenset((
    "47a41963", "4dc46727", "f1bb1663", "93197c59", "1e840e1e", "bc78bfcc",
    "4cf4bb0e", "5b11c39c", "2dd667c5", "53a67c51", "4bbc1f8e", "66616a1d",
    "15c7630b", "a5ba7c19", "c09f0eed", "4250fde7",
))

SHEET_LOCALES = {
    "authored": "elemental_lords",
    "47a41963": "amethyst_barrens", "4dc46727": "amethyst_barrens",
    "f1bb1663": "elemental_lords",
    "93197c59": "sunmane_steppe", "1e840e1e": "sunmane_steppe",
    "bc78bfcc": "crownwater", "4cf4bb0e": "westhaven",
    "5b11c39c": "drowned_crown", "2dd667c5": "grey_moors",
    "53a67c51": "mirrorhold", "4bbc1f8e": "manymouth_delta",
    "66616a1d": "verdant_stair", "15c7630b": "whitehorn_range",
    "a5ba7c19": "amberwood", "c09f0eed": "amberwood", "4250fde7": "amberwood",
}


# How much each creature's albedo has to be lifted for it to sit at the same
# value, relative to the rest of the library, that it sits at in the artwork.
# The sampled hues are accurate -- the median hue error against the concept
# figures is about two degrees -- but the values were compressed: rendered and
# measured, a whitehorn yak and a coastal gull, which the art paints nearly
# white, came out within a few points of a black iron death knight.  Range is
# what tells one silhouette from another in a lineup, so it is restored here.
# Measured by ``concept_value_gains.py --table``; gains only ever lift, since
# the creatures the art paints dark were already right.
VALUE_GAIN = {
    "amethyst_scorpion": 1.41,          # art  83.4, model  56.0
    "geode_scarab": 1.51,               # art  94.2, model  65.8
    "shardling_swarm": 1.42,            # art  89.5, model  60.3
    "geode_tortoise": 1.39,             # art  86.5, model  58.4
    "prism_moth": 1.55,                 # art  90.0, model  54.1
    "tidegold_wyrm": 1.18,              # art  74.9, model  49.7
    "rimebound_archmage": 1.55,         # art  89.0, model  56.5
    "glacier_brute": 1.20,              # art  97.8, model  66.5
    "amethyst_sibyl": 1.11,             # art  68.1, model  46.2
    "tidecaller_sorceress": 1.47,       # art  81.7, model  54.3
    "goldmane_aurochs": 1.55,           # art  97.1, model  56.2
    "plumed_crane": 1.55,               # art 105.1, model  54.8
    "sunmane_minotaur": 1.09,           # art  79.4, model  53.7
    "stormmane_lion": 1.55,             # art 101.0, model  54.0
    "grasswing_mantis": 1.55,           # art 111.8, model  67.4
    "dust_hyena": 1.55,                 # art  87.2, model  52.1
    "steppe_jackrabbit": 1.55,          # art 115.5, model  66.4
    "sunmane_gryphon": 1.55,            # art  98.1, model  56.9
    "crownwater_turtle": 1.55,          # art  92.7, model  56.9
    "tidefin_naga": 1.55,               # art 109.9, model  58.0
    "lanternwyrm": 1.48,                # art  85.2, model  58.5
    "crownwater_wyvern": 1.55,          # art 105.6, model  57.3
    "cascade_golem": 1.05,              # art  84.3, model  57.3
    "tidecoil_serpent": 1.55,           # art 104.5, model  62.4
    "palecrest_crab": 1.55,             # art 118.9, model  67.2
    "riverbank_ibis": 1.55,             # art 105.9, model  55.7
    "algae_alligator": 1.55,            # art  82.5, model  51.5
    "springfly_sprite": 1.55,           # art 128.9, model  75.4
    "gilded_water_lion": 1.55,          # art  99.0, model  54.6
    "courier_otter": 1.35,              # art  77.1, model  50.8
    "message_swallow": 1.47,            # art  79.9, model  53.3
    "brassband_pike": 1.55,             # art  92.2, model  51.7
    "verdigris_beetle": 1.15,           # art  84.0, model  55.5
    "drowned_dockhand": 1.19,           # art  70.4, model  47.7
    "sluice_elemental": 1.43,           # art 112.1, model  75.3
    "waterwheel_golem": 1.30,           # art  93.3, model  63.3
    "harbor_gull": 1.55,                # art 128.5, model  64.3
    "harbor_seal": 1.55,                # art  98.1, model  58.3
    "kelpback_turtle": 1.55,            # art  84.6, model  55.2
    "bluewater_marlin": 1.55,           # art  87.1, model  51.1
    "saltmarsh_crocodile": 1.41,        # art  78.3, model  51.2
    "spinefin_eel": 1.10,               # art  73.7, model  48.8
    "glowmantle_ray": 1.55,             # art  92.2, model  58.9
    "deepplate_coelacanth": 1.35,       # art  74.2, model  48.8
    "moor_heron": 1.41,                 # art  77.9, model  51.5
    "moorlight_wisp": 1.55,             # art 144.0, model  79.7
    "spectral_moor_stag": 1.55,         # art 101.8, model  62.4
    "tidelance_construct": 1.55,        # art  96.4, model  63.2
    "reefplate_golem": 1.55,            # art 106.0, model  71.3
    "verdigris_warden": 1.21,           # art  84.4, model  56.6
    "palewater_wyrm": 1.55,             # art 121.1, model  68.4
    "mirrorwing_swarm": 1.55,           # art 144.3, model  62.7
    "shattered_sentinel": 1.09,         # art  85.8, model  58.2
    "mirrorhold_oracle": 1.55,          # art  96.6, model  58.9
    "tideguard_vanguard": 1.38,         # art  82.1, model  54.7
    "mirrorhold_siren": 1.55,           # art  99.5, model  59.6
    "mirrorhold_loremaster": 1.55,      # art  97.0, model  63.9
    "delta_heron": 1.07,                # art  74.5, model  50.2
    "emerald_basilisk": 1.55,           # art  84.7, model  50.8
    "leaf_mantis": 1.55,                # art  96.1, model  61.5
    "dartback_treefrog": 1.55,          # art  96.7, model  55.2
    "plumefire_hummingbird": 1.55,      # art 102.0, model  53.9
    "vinecoil_snake": 1.19,             # art  74.7, model  48.9
    "canopy_lynx": 1.55,                # art  80.5, model  52.5
    "mossback_anteater": 1.19,          # art  74.5, model  50.2
    "bloomtail_axolotl": 1.55,          # art  82.6, model  51.3
    "verdant_naiad": 1.54,              # art 124.5, model  54.9
    "verdant_stair_dragon": 1.55,       # art  99.1, model  55.2
    "rime_harpy": 1.55,                 # art 123.9, model  58.8
    "glacier_golem": 1.39,              # art 107.4, model  73.0
    "whitehorn_yak": 1.55,              # art 128.1, model  61.8
    "rimeshell_crab": 1.55,             # art  93.5, model  59.4
    "hoarfrost_serpent": 1.55,          # art 133.2, model  61.8
    "glacier_eagle": 1.55,              # art 114.0, model  59.8
    "frostplate_knight": 1.42,          # art  93.7, model  63.1
    "emberwing_moth": 1.55,             # art  88.9, model  58.3
    "ivy_hound": 1.19,                  # art  74.8, model  50.1
    "spectral_highwayman": 1.19,        # art  72.0, model  48.9
    "moss_bear": 1.23,                  # art  74.9, model  50.6
    "amberwood_ghost_knight": 1.38,     # art  88.7, model  59.5
}


# The colour of the brightest lit feature on each concept figure: the ember in
# a treant's chest, the light inside a geode carapace, the centre of a wisp.
# Measured by ``concept_growth_tints.py --core``.  Used for the MAT_CORE
# material, which is why a treant's heart is amber and a barrens wisp's is
# blue rather than both being a generic white glow.
# Where a figure carries two bright inks -- lit water and metal trim, say --
# ``concept_growth_tints.py --core`` picks the more saturated cluster, and on a
# couple of figures that is the trim rather than the light.  Both clusters are
# measured; these name the one that is actually the glow, and the value is the
# cluster mean, not a guess.  Applied over CORE_TINT below.
CORE_TINT_OVERRIDE = {
    "cascade_golem": (119, 190, 220),           # cyan falls, not the gold trim
    "mirrorhold_wheelwarden": (102, 180, 200),  # cyan wheelwater, not the brass
}


CORE_TINT = {
    "amethyst_scorpion": (123, 211, 248),
    "geode_scarab": (126, 241, 253),
    "prism_drake": (118, 195, 246),
    "shardling_swarm": (125, 208, 250),
    "barrens_wisp": (83, 106, 213),
    "amethyst_golem": (104, 175, 235),
    "crystalwing": (108, 187, 246),
    "geode_tortoise": (110, 225, 253),
    "facet_hound": (107, 179, 243),
    "prism_moth": (122, 210, 251),
    "lattice_spider": (117, 193, 247),
    "orrery_sentinel": (108, 208, 247),
    "verdant_crown_king": (72, 158, 165),
    "tidegold_wyrm": (86, 173, 195),
    "rimebound_archmage": (115, 186, 218),
    "glacier_brute": (131, 204, 229),
    "orrery_colossus": (118, 146, 226),
    "amethyst_sibyl": (115, 116, 201),
    "crimson_duelist": (151, 125, 75),
    "emberwood_matron": (170, 112, 52),
    "barrow_sovereign": (57, 127, 121),
    "gilded_devourer": (164, 129, 85),
    "tidecaller_sorceress": (90, 166, 176),
    "mirefather_leviathan": (63, 163, 170),
    "goldmane_aurochs": (245, 209, 139),
    "dunburrow_mole": (194, 140, 89),
    "plumed_crane": (245, 195, 97),
    "sunmane_minotaur": (229, 179, 74),
    "stormmane_lion": (245, 187, 74),
    "grasswing_mantis": (232, 213, 79),
    "dust_hyena": (232, 161, 82),
    "steppe_jackrabbit": (240, 202, 111),
    "sunmane_gryphon": (240, 194, 107),
    "crownwater_turtle": (226, 190, 104),
    "tidefin_naga": (241, 199, 106),
    "lanternwyrm": (235, 193, 60),
    "crownwater_wyvern": (108, 219, 232),
    "cascade_golem": (214, 188, 95),
    "tidecoil_serpent": (238, 203, 100),
    "palecrest_crab": (245, 221, 134),
    "riverbank_ibis": (249, 221, 130),
    "algae_alligator": (197, 172, 73),
    "springfly_sprite": (242, 211, 130),
    "gilded_water_lion": (111, 216, 241),
    "medusa_tidepriest": (65, 203, 230),
    "courier_otter": (204, 157, 101),
    "message_swallow": (200, 150, 90),
    "harborshell_crab": (194, 136, 76),
    "brassband_pike": (80, 180, 194),
    "reedhat_fisher": (190, 138, 81),
    "ratcatcher_tough": (58, 146, 154),
    "verdigris_beetle": (69, 185, 208),
    "lanternwake_sprite": (96, 202, 216),
    "millstone_golem": (80, 205, 216),
    "drowned_dockhand": (64, 166, 176),
    "sluice_elemental": (89, 208, 227),
    "waterwheel_golem": (106, 220, 234),
    "rockshell_crab": (205, 138, 79),
    "kelpback_turtle": (192, 147, 97),
    "bluewater_marlin": (194, 168, 76),
    "saltmarsh_crocodile": (169, 149, 86),
    "bilge_rat": (170, 122, 92),
    "spinefin_eel": (53, 179, 204),
    "barnacle_troll": (159, 142, 74),
    "drowned_captain": (148, 129, 76),
    "glowmantle_ray": (46, 208, 229),
    "deepplate_coelacanth": (61, 154, 182),
    "moor_pony": (158, 139, 79),
    "moorhorn_ram": (119, 106, 55),
    "moor_heron": (208, 178, 113),
    "cairnback_tortoise": (144, 128, 61),
    "moorfell_wolf": (116, 100, 49),
    "reedmask_stalker": (141, 121, 70),
    "moorlight_wisp": (118, 237, 226),
    "barrow_knight": (98, 184, 171),
    "cairn_golem": (87, 182, 189),
    "lantern_wraith": (89, 175, 178),
    "spectral_moor_stag": (114, 207, 199),
    "barrow_king": (93, 174, 168),
    "tidelance_construct": (93, 218, 228),
    "mirrorhold_wheelwarden": (197, 155, 98),
    "verdigris_warden": (86, 179, 204),
    "palewater_wyrm": (107, 208, 220),
    "mirrorwing_swarm": (129, 223, 232),
    "shattered_sentinel": (88, 196, 216),
    "mirrorhold_oracle": (87, 188, 211),
    "tideguard_vanguard": (70, 182, 207),
    "mirrorhold_siren": (99, 181, 195),
    "shardbound_archivist": (98, 219, 231),
    "mirrorhold_loremaster": (95, 208, 224),
    "mudflat_crab": (199, 139, 79),
    "delta_heron": (201, 166, 83),
    "voltfin_eel": (57, 171, 181),
    "reed_stalker": (172, 141, 70),
    "mangrove_turtle": (151, 145, 44),
    "bog_warden": (48, 184, 192),
    "frogspear_warrior": (175, 126, 79),
    "reed_drake": (158, 139, 69),
    "manymouth_hydra": (210, 139, 67),
    "emerald_basilisk": (176, 168, 53),
    "leaf_mantis": (186, 190, 49),
    "dartback_treefrog": (118, 205, 45),
    "plumefire_hummingbird": (245, 186, 63),
    "vinecoil_snake": (225, 131, 39),
    "canopy_lynx": (209, 171, 69),
    "mossback_anteater": (165, 151, 49),
    "bloomtail_axolotl": (28, 206, 235),
    "canopy_gorilla": (151, 136, 48),
    "vine_treant": (188, 127, 63),
    "verdant_naiad": (111, 220, 240),
    "verdant_stair_dragon": (201, 189, 59),
    "glacier_golem": (127, 239, 252),
    "rimeshell_crab": (101, 224, 247),
    "hoarfrost_serpent": (142, 236, 252),
    "glacier_eagle": (252, 232, 116),
    "frostplate_knight": (105, 209, 244),
    "emberwing_moth": (246, 176, 37),
    "amberwood_owl": (174, 138, 46),
    "bramble_wolf": (161, 114, 79),
    "moss_troll": (172, 139, 53),
    "amberwood_treant": (169, 136, 51),
    "ivy_hound": (157, 140, 72),
    "thorn_revenant": (72, 123, 140),
    "spectral_highwayman": (176, 136, 93),
    "lantern_stag": (159, 100, 56),
    "moss_badger": (213, 142, 69),
    "bramble_stag": (145, 125, 49),
    "leafling_sprite": (153, 134, 36),
    "ember_wisp": (248, 205, 83),
    "ivy_stone_golem": (178, 125, 74),
    "amberwood_dryad": (171, 115, 79),
    "moss_bear": (223, 184, 48),
    "amberwood_scarecrow": (227, 150, 59),
    "amberwood_ghost_knight": (230, 193, 89),
    "elk": (186, 119, 83),
    "emberfox": (241, 176, 128),
    "frost_maw": (141, 238, 252),
    "frost_tiger": (128, 228, 251),
    "giant_crocodile": (172, 154, 75),
    "giant_komodo": (178, 155, 78),
    "giant_tortoise": (228, 173, 101),
    "horse": (236, 168, 84),
    "miretoad": (213, 178, 89),
    "mossback_boar": (149, 130, 60),
    "red_fox": (240, 189, 96),
}


# What colour that growth actually is in the artwork, measured by
# ``eloria-assets/tools/concept_growth_tints.py`` from the cut concept figures.
# Deriving it from the kind alone made every leaf green, which is right for the
# Verdant Stair and wrong for the Amberwood -- an autumn wood whose foliage
# measures amber -- and badly wrong for the thornwood dryad, whose canopy is
# crimson.  Only vegetation is listed: mineral crusts already take the
# creature's own palette.
GROWTH_TINT = {
    "algae_alligator": (153, 129, 50),              # 45% of the ink
    "amberwood_dryad": (127, 73, 50),               # 72% of the ink
    "amberwood_owl": (127, 79, 44),                 # 68% of the ink
    "amberwood_scarecrow": (143, 59, 12),           # 69% of the ink
    "amberwood_treant": (127, 92, 41),              # 50% of the ink
    # barrow_king: dominant hue (78, 147, 141) is not foliage
    # barrow_knight: dominant hue (81, 149, 137) is not foliage
    # bog_lurker: no figure
    "bog_warden": (129, 109, 71),                   # 54% of the ink
    "bramble_stag": (122, 71, 44),                  # 77% of the ink
    "bramble_wolf": (123, 82, 58),                  # 92% of the ink
    "cairn_golem": (113, 100, 50),                  # 75% of the ink
    "canopy_gorilla": (135, 82, 55),                # 60% of the ink
    "drowned_captain": (113, 77, 56),               # 39% of the ink
    "elk": (143, 71, 46),                           # 100% of the ink
    "emerald_basilisk": (112, 134, 40),             # 27% of the ink
    "frogspear_warrior": (132, 104, 60),            # 52% of the ink
    "giant_crocodile": (127, 103, 54),              # 59% of the ink
    "giant_komodo": (135, 114, 57),                 # 88% of the ink
    "ivy_hound": (112, 96, 52),                     # 73% of the ink
    "ivy_stone_golem": (123, 105, 61),              # 49% of the ink
    "kelpback_turtle": (132, 111, 64),              # 62% of the ink
    "leafling_sprite": (120, 92, 22),               # 58% of the ink
    "mangrove_turtle": (129, 107, 59),              # 45% of the ink
    "manymouth_hydra": (136, 113, 58),              # 36% of the ink
    "millstone_golem": (133, 110, 68),              # 73% of the ink
    "mirefather_leviathan": (126, 110, 52),         # 38% of the ink
    "miretoad": (150, 115, 46),                     # 56% of the ink
    "moorfell_wolf": (115, 95, 54),                 # 78% of the ink
    "moorhorn_ram": (117, 100, 57),                 # 78% of the ink
    "moss_badger": (128, 109, 45),                  # 64% of the ink
    "moss_bear": (159, 122, 35),                    # 77% of the ink
    "moss_troll": (127, 97, 36),                    # 68% of the ink
    "mossback_anteater": (134, 109, 44),            # 46% of the ink
    "mossback_boar": (126, 80, 59),                 # 74% of the ink
    "red_fox": (186, 121, 38),                      # 89% of the ink
    "reed_drake": (126, 103, 58),                   # 64% of the ink
    "reed_stalker": (134, 104, 49),                 # 89% of the ink
    "saltmarsh_crocodile": (125, 107, 61),          # 81% of the ink
    "sunmane_gryphon": (170, 122, 62),              # 76% of the ink
    # thorn_revenant: dominant hue (63, 107, 122) is not foliage
    # verdant_stair_dragon: dominant hue (29, 122, 95) is not foliage
    "vine_treant": (133, 104, 42),                  # 42% of the ink
    "waterwheel_golem": (143, 117, 67),             # 45% of the ink
}


# What the concept art shows growing on each creature.  This is most of what
# breaks up a silhouette: a clean swept tube reads as a balloon animal however
# good its proportions are.  (kind, count, size) per entry.
GROWTH = {
    # Amethyst Barrens: crystal erupting through everything
    "amethyst_scorpion": [("crystal", 12, 1.15)],
    "geode_scarab": [("crystal", 9, 1.0)],
    "prism_drake": [("crystal", 13, 1.05)],
    "amethyst_golem": [("crystal", 16, 1.2)],
    "crystalwing": [("crystal", 10, 1.0)],
    "geode_tortoise": [("crystal", 14, 1.15)],
    "facet_hound": [("crystal", 11, .95)],
    "prism_moth": [("crystal", 7, .8)],
    "lattice_spider": [("crystal", 10, .9)],
    "orrery_sentinel": [("plate", 7, 1.0)],
    # Sunmane Steppe
    "goldmane_aurochs": [("plate", 5, .9)],
    "sunmane_gryphon": [("leaf", 8, .7)],
    # Crownwater and the coast: algae, coral, barnacles
    "crownwater_turtle": [("moss", 12, 1.0), ("coral", 5, .8)],
    "algae_alligator": [("moss", 16, 1.05), ("vine", 6, .9)],
    "cascade_golem": [("moss", 14, 1.1), ("coral", 6, .9)],
    "kelpback_turtle": [("moss", 14, 1.1), ("vine", 7, 1.0)],
    "saltmarsh_crocodile": [("moss", 11, .95)],
    "barnacle_troll": [("barnacle", 18, 1.05), ("moss", 8, .9)],
    "rockshell_crab": [("barnacle", 9, .85)],
    "harborshell_crab": [("barnacle", 8, .85), ("moss", 6, .8)],
    "reefplate_golem": [("coral", 12, 1.1), ("barnacle", 8, .9)],
    "mudflat_crab": [("barnacle", 7, .8)],
    "drowned_dockhand": [("moss", 10, .9), ("barnacle", 6, .8)],
    "drowned_captain": [("moss", 7, .8)],
    "millstone_golem": [("moss", 9, .9)],
    "waterwheel_golem": [("moss", 10, .95)],
    "mirrorhold_wheelwarden": [("coral", 8, .9)],
    "verdigris_warden": [("coral", 7, .85)],
    "tidefin_naga": [("coral", 6, .8)],
    # Grey Moors: heather, lichen, cairn stone
    "moorfell_wolf": [("moss", 9, .85)],
    "cairnback_tortoise": [("moss", 12, 1.0), ("plate", 5, .9)],
    "cairn_golem": [("moss", 13, 1.05)],
    "moorhorn_ram": [("moss", 7, .8)],
    "spectral_moor_stag": [("ember", 6, .8)],
    "lantern_wraith": [("ember", 5, .8)],
    "barrow_knight": [("moss", 7, .8)],
    "barrow_king": [("moss", 6, .8)],
    # Manymouth Delta and Verdant Stair: reeds, mangrove, canopy
    "mangrove_turtle": [("vine", 10, 1.1), ("moss", 10, 1.0)],
    "reed_stalker": [("vine", 9, 1.0)],
    "reed_drake": [("vine", 8, .95), ("moss", 7, .9)],
    "bog_warden": [("moss", 11, 1.0)],
    "manymouth_hydra": [("vine", 9, 1.0), ("moss", 9, 1.0)],
    "frogspear_warrior": [("moss", 6, .8)],
    "mossback_anteater": [("moss", 13, 1.05), ("leaf", 7, .8)],
    "vine_treant": [("vine", 10, .85), ("leaf", 4, .7)],
    "verdant_stair_dragon": [("leaf", 12, .9), ("vine", 7, .9)],
    "emerald_basilisk": [("leaf", 6, .7)],
    "canopy_gorilla": [("leaf", 7, .8)],
    # Whitehorn Range: rime and ice
    "rimeshell_crab": [("rime", 10, 1.0)],
    "hoarfrost_serpent": [("rime", 11, .95)],
    "glacier_golem": [("rime", 16, 1.2)],
    "glacier_brute": [("rime", 14, 1.15)],
    "frostplate_knight": [("rime", 9, .95)],
    "whitehorn_yak": [("rime", 7, .85)],
    "rime_harpy": [("rime", 7, .85)],
    # Amberwood: bramble, moss, fungus, leaves
    "moss_bear": [("moss", 15, 1.1), ("fungus", 5, .9), ("leaf", 7, .8)],
    "moss_badger": [("moss", 11, 1.0), ("fungus", 4, .85)],
    "moss_troll": [("moss", 15, 1.1), ("fungus", 6, .95)],
    "bramble_wolf": [("thorn", 14, 1.0), ("leaf", 6, .8)],
    "bramble_stag": [("thorn", 12, 1.0), ("leaf", 7, .85)],
    "ivy_hound": [("vine", 11, 1.0), ("leaf", 8, .85)],
    "ivy_stone_golem": [("vine", 13, 1.05), ("leaf", 9, .9)],
    "amberwood_treant": [("vine", 7, .8), ("leaf", 4, .7), ("fungus", 4, .85)],
    "leafling_sprite": [("leaf", 4, .7)],
    "amberwood_dryad": [("leaf", 6, .8), ("thorn", 6, .8)],
    "thorn_revenant": [("thorn", 13, 1.0)],
    "amberwood_scarecrow": [("thorn", 8, .9)],
    "lantern_stag": [("ember", 7, .85), ("leaf", 6, .8)],
    "amberwood_owl": [("leaf", 7, .8)],
    "emberwing_moth": [("ember", 5, .7)],
    # Elemental lords
    "emberwood_matron": [("leaf", 5, .8), ("ember", 5, .8)],
    "mirefather_leviathan": [("moss", 16, 1.15), ("vine", 8, 1.0)],
    "amethyst_sibyl": [("crystal", 9, .95)],
    "shattered_sentinel": [("crystal", 10, 1.0)],
    "shardbound_archivist": [("crystal", 8, .95)],
    "verdant_crown_king": [("leaf", 10, .90), ("vine", 7, .85)],
    "drowned_lich_king": [("moss", 7, .80), ("barnacle", 5, .75)],
    "tidecaller_sorceress": [("coral", 7, .85)],
    "mirrorhold_oracle": [("coral", 6, .8)],
    "mirrorhold_loremaster": [("coral", 6, .8)],
    "orrery_colossus": [("plate", 8, 1.0)],
    # Legacy roster creatures that the art shows encrusted
    "mossback_boar": [("moss", 13, 1.05), ("fungus", 4, .85)],
    "miretoad": [("fungus", 6, .95), ("moss", 8, .9)],
    "bog_lurker": [("moss", 10, .95)],
    "giant_crocodile": [("moss", 9, .9)],
    "giant_komodo": [("moss", 6, .8)],
    "ice_bear": [("rime", 10, 1.0)],
    "frost_maw": [("rime", 9, .95)],
    "frost_tiger": [("rime", 7, .85)],
    "mountain_goat": [("rime", 6, .8)],
    "snow_hare": [("rime", 4, .7)],
    "armored_rhino": [("plate", 6, 1.0)],
    "porcupine": [("spine", 10, 1.0)],
    "ash_crawler": [("crystal", 7, .85)],
    "sunscale_drake": [("plate", 6, .9)],
    "elk": [("leaf", 6, .8)],
    "red_fox": [],
}
