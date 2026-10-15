#!/usr/bin/env python3
"""Build the Godot-native Nymara actor library from clean glTF 2.0 sources.

This pipeline deliberately does not consume the legacy Cal3D humanoid or creature
generators.  Playable races retain the proven Quaternius 65-joint skin, topology,
weights, and animation bone names.  Creature meshes, rigs, and clips are authored
here from scratch.

Modified 2026-08-28 for Eloria Client: equipment is no longer a set of primitive
blobs bolted to a bone with an identity transform.  ``equipment_authoring``
lofts wearables around the measured body silhouette and skins them to the shared
rig, and authors props against a character-space socket solved from the rig
itself, so items attach at body scale and follow every animation clip.
"""
from __future__ import annotations

import argparse
import colorsys
import copy
from functools import lru_cache
import io
import json
import math
from pathlib import Path
import struct
import numpy as np

import creature_anatomy as anatomy
import creature_families as families
import creature_roster as roster
import creature_surfaces as surfaces
from PIL import Image

import equipment_authoring


COMPONENT_DTYPES = {5121: "<u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
COMPONENT_TYPES = {np.dtype("uint8"): 5121, np.dtype("int16"): 5122,
                   np.dtype("uint16"): 5123, np.dtype("uint32"): 5125,
                   np.dtype("float32"): 5126}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

RACES = {
    "luminous": {"label": "Human", "color": (196, 139, 103),
                  "accent": (48, 151, 164),
                  "feature": "none", "preserve_body": True,
                  "wardrobe": ((42, 126, 142), (42, 55, 72), (78, 55, 39),
                                (221, 190, 101))},
    "votary": {"label": "Whitehorn", "color": (161, 145, 108),
                "feature_color": (205, 216, 213), "accent": (226, 231, 228),
                "feature": "horns",
                "wardrobe": ((113, 145, 164), (76, 94, 108), (79, 91, 99),
                              (218, 232, 235))},
    "glasswarden": {"label": "Glassborn", "color": (168, 121, 91),
                     "feature_color": (38, 29, 62), "accent": (45, 128, 164),
                     "feature": "crystal",
                     "body_pattern": "none",
                     # The one human culture on the slim base body.  They are
                     # written as scholars and field engineers and were
                     # already the lightest entry in ANATOMY; the physique is
                     # now in the mesh rather than in a girth multiplier.
                     "base": "slim",
                     "wardrobe": ((54, 48, 84), (42, 44, 62), (83, 57, 39),
                                   (187, 145, 63))},
    "orun": {"label": "Orun", "color": (184, 139, 105),
             "accent": (219, 166, 72), "feature": "none",
             "wardrobe": ((146, 76, 39), (85, 64, 48), (82, 54, 35),
                           (49, 142, 145))},
    "greyhaven": {"label": "Greyhaven", "color": (153, 111, 89),
                   "accent": (154, 174, 171), "feature": "none",
                   "wardrobe": ((225, 220, 202), (41, 59, 75), (65, 49, 39),
                                 (171, 137, 70))},
    "ssarathi": {"label": "Lizardfolk", "color": (91, 153, 126),
                  "feature_color": (32, 91, 68), "accent": (157, 122, 50),
                  "feature": "scaled",
                  "wardrobe": ((43, 112, 86), (34, 76, 62), (71, 63, 42),
                                (189, 153, 67))},
    "stoneborn": {"label": "Stoneborn", "color": (118, 105, 91),
                   "feature_color": (61, 59, 56), "accent": (50, 122, 133),
                   "feature": "stone",
                   "wardrobe": ((91, 86, 80), (65, 67, 68), (62, 55, 48),
                                 (84, 189, 199))},
    "mycelari": {"label": "Mushroomfolk", "color": (116, 137, 91),
                  "feature_color": (82, 56, 35), "accent": (154, 92, 48),
                  "feature": "fungal",
                  "wardrobe": ((88, 112, 70), (62, 75, 53), (71, 54, 39),
                                (207, 143, 89))},
}

# --- race anatomy ---------------------------------------------------------
#
# Every playable race shares the one 65-joint Quaternius rig so the universal
# animation library keeps working, but sharing a rig does not have to mean
# sharing a body.  The previous pass scaled the source mesh with three hard
# width bands keyed off absolute height (hips below 48%, shoulders to 78%,
# head above).  That produced a visible pinch at the waist and the neck, it
# stretched arms lengthwise instead of thickening them -- the bands multiply
# X, and an A-posed arm is almost entirely X -- and it left all eight races
# the same human silhouette with a small prop glued on.
#
# This pass retargets the rest pose instead.  Segment lengths and rest
# rotations move the joints, and the mesh follows through linear blend
# skinning with T = B . G . A^-1, where A is the source bind pose, B the
# retargeted bind pose, and G a girth scale expressed perpendicular to the
# bone.  Deformation is therefore smooth by construction (it is blended by
# the same skin weights the renderer uses), anatomically meaningful (a bone
# gets longer or thicker rather than a slab of world space getting wider),
# and it costs no extra vertices.
#
# Two invariants keep the shared animation library usable:
#
#   * hip-to-ground distance is preserved.  The clips write pelvis
#     translation directly, so a longer leg cannot raise the hips -- it would
#     push the feet through the floor.  After retargeting, the leg chain is
#     rescaled by a single solved factor that restores the original ground
#     contact height.  Races still differ in how the leg is *divided*, which
#     is what makes a digitigrade stance possible at all.
#   * overall stature rides on the model registry's import scale rather than
#     on the rig, so a taller race is uniformly taller instead of having its
#     hips detached from its feet.
#
# The rest of the runtime contract is untouched: 65 joints, the same joint
# names and order, one skin, and rest transforms that stay rigid so the
# clips' rotation tracks still mean what they meant before.

CHAIN_CHILD = {"root": "pelvis", "pelvis": "spine_01",
               "hand_l": "middle_01_l", "hand_r": "middle_01_r"}
GROUND_JOINTS = ("ball_leaf_l", "ball_leaf_r")
LEG_GROUPS = ("thigh", "calf", "foot", "ball")


# ---------------------------------------------------------------------------
# Cape bones
#
# A cape skinned to the spine cannot avoid a leg: measured against the shared
# clips the body passes 254 mm behind the cape in a walk and 858 mm in a run.
# Weighting the hem to the thighs does not fix it either -- one cape spanning
# both legs follows their average, which is precisely where neither leg is, so
# it helps some poses and hurts others.
#
# The cape therefore needs bones of its own that a solver can move.  They hang
# off spine_03 and are carried by every race, so a cape stays an ordinary
# skinned garment and keeps the per-race rebind and girth fit; the runtime
# simulates them when a cape is worn and leaves them at rest otherwise.
#
# Three chains rather than one: a single column cannot twist, and the left and
# right halves of a cape have to part around a leg independently.  The shared
# animation library names no cape bone, so no clip touches them -- which is
# what makes them safe to add and available to own.
CAPE_CHAINS = ("l", "c", "r")
CAPE_LINKS = 4
# Where each chain leaves spine_03, in that joint's own bind frame.
CAPE_ROOTS = {"l": (-.150, .150, -.105), "c": (0., .162, -.098),
              "r": (.150, .150, -.105)}
# Every link below the first drops by this much and drifts a little further
# back, so the rest pose matches the hang of the authored cape.
CAPE_LINK_DROP = (0., -.293, -.012)


def cape_bone_names() -> list[str]:
    return [f"cape_{chain}_{index + 1:02d}"
            for chain in CAPE_CHAINS for index in range(CAPE_LINKS)]


def append_cape_bones(nodes: list[dict], joint_nodes: list[int],
                      source_bind: np.ndarray, parents: dict[int, int | None],
                      names: list[str]):
    """Hang the cape chains off spine_03, extending the rig in place.

    Returns the extended (joint_nodes, source_bind, parents, names).  The new
    joints carry spine_03's rotation basis and differ only in translation, so
    the retarget treats them exactly as it treats every other bone.
    """
    if "spine_03" not in names:
        return joint_nodes, source_bind, parents, names
    anchor = names.index("spine_03")
    basis = source_bind[anchor][:3, :3]
    binds = [source_bind[slot] for slot in range(len(source_bind))]
    joint_nodes = list(joint_nodes)
    names = list(names)
    parents = dict(parents)
    for chain in CAPE_CHAINS:
        parent_slot = anchor
        offset = np.asarray(CAPE_ROOTS[chain], dtype=float)
        for index in range(CAPE_LINKS):
            matrix = np.eye(4, dtype=np.float64)
            matrix[:3, :3] = basis
            matrix[:3, 3] = binds[parent_slot][:3, 3] + basis @ offset
            node = {"name": f"cape_{chain}_{index + 1:02d}"}
            nodes.append(node)
            nodes[joint_nodes[parent_slot]].setdefault("children", []).append(
                len(nodes) - 1)
            joint_nodes.append(len(nodes) - 1)
            binds.append(matrix)
            parents[len(binds) - 1] = parent_slot
            names.append(node["name"])
            parent_slot = len(binds) - 1
            offset = np.asarray(CAPE_LINK_DROP, dtype=float)
    return joint_nodes, np.stack(binds), parents, names


def joint_group(name: str) -> str:
    """Coarse anatomical group for a rig joint, used to key the race specs."""
    if name == "root":
        return "root"
    if name == "pelvis":
        return "pelvis"
    if name == "Head":
        return "head"
    if name.startswith("cape_"):
        return "cape"
    for prefix in ("spine", "neck", "clavicle", "upperarm", "lowerarm",
                   "hand", "thigh", "calf", "foot", "ball"):
        if name.startswith(prefix):
            return prefix
    return "finger"


# stature   uniform import scale for the whole actor (registry, not the rig)
# segment   multiplies the bone that *leaves* this group, i.e. the local
#           offsets of its children -- "thigh": 1.1 lengthens the femur
# girth     thickness perpendicular to the bone
# swell     uniform scale about the joint, for the skull and hands
# stance    rotation of the joint's offset from its parent, in world bind
#           axes (degrees), authored for the right side and mirrored to the
#           left -- this is anatomy the animation clips cannot overwrite
ANATOMY = {
    # Reference proportions.  The Luminous are the baseline every other race
    # is described against, so their body is left exactly as authored.
    "luminous": {},
    # Whitehorn highlanders: tall, long-limbed and lean, with the heavy neck
    # and loaded calves of people who walk mountains carrying horns.
    "votary": {
        "stature": 1.045,
        "segment": {"calf": 1.05, "thigh": 1.03, "neck": 1.10, "spine": 1.02},
        "girth": {"upperarm": .94, "lowerarm": .93, "spine": .97,
                  "neck": 1.16, "calf": 1.12, "thigh": 1.03},
    },
    # Glasswarden field engineers and scholars: shorter, lighter through the
    # shoulders and arms, with the head carried slightly forward.
    "glasswarden": {
        "stature": .975,
        "segment": {"clavicle": .95, "thigh": .99},
        # No girth block: BASE_BODIES["slim"] carries this culture's build,
        # and a uniform per-bone thinning stacked on top of an already
        # narrower body took the arms from light to spindly.
        "stance": {"neck_01": (7., 0., 0.), "Head": (-4., 0., 0.)},
    },
    # Orun riders: deep chest, heavy thighs, and the bowed, externally
    # rotated legs of a culture that grows up in the saddle.
    "orun": {
        "stature": 1.01,
        "segment": {"spine": .97, "thigh": 1.02, "clavicle": 1.04},
        "girth": {"spine": 1.09, "thigh": 1.14, "calf": 1.04,
                  "upperarm": 1.06, "lowerarm": 1.02},
        # Knees carried outward and ankles tucked back under: a rider's legs.
        "stance": {"calf_r": (0., 0., -7.), "foot_r": (0., 0., 10.)},
    },
    # Greyhaven coast: stocky and heavy-boned, broad through the shoulders
    # and forearms, shorter in the leg than the arm.
    "greyhaven": {
        "stature": .99,
        "segment": {"clavicle": 1.10, "thigh": .96, "calf": .96,
                    "lowerarm": 1.04, "neck": .94},
        "girth": {"spine": 1.12, "upperarm": 1.10, "lowerarm": 1.14,
                  "hand": 1.08, "thigh": 1.08, "calf": 1.08, "neck": 1.10},
        "stance": {"upperarm_r": (0., 0., -5.)},
    },
    # Ssarathi are reptilian, not humans in scale paint.  The leg is
    # digitigrade: the femur swings forward, the shin back, and the body
    # stands on a long metatarsal with the heel clear of the ground.  Total
    # hip height is unchanged, so the shared walk cycle still plants.  The
    # neck is longer and carried forward, counterweighted by the tail.
    "ssarathi": {
        "stature": 1.02,
        # The shin is shorter than the first pass gave it.  Length here and
        # fold at the knee trade against each other -- both lift the ankle --
        # but a long shin folded hard needs a heavily shortened chain to plant
        # at rest, and that chain cannot reach the floor once a clip extends
        # the leg.  This pair puts the ankle 0.235 m up, slightly more
        # clearance than the original, and plants in every clip.
        "segment": {"thigh": .86, "calf": 1.06, "foot": 1.55, "ball": 1.30,
                    "neck": 1.32, "spine": .97, "lowerarm": 1.10,
                    "hand": 1.12, "finger": 1.15},
        "girth": {"spine": .93, "upperarm": .88, "lowerarm": .86,
                  "thigh": 1.02, "calf": .88, "foot": .82, "neck": .90},
        "swell": {"hand": .96},
        # The ankle stands 0.23 m clear of the ground on a long metatarsal
        # with the ball and toe planted: femur forward, shin back, a steep
        # metatarsal, flat toes.
        #
        # These angles are solved against the animation library rather than
        # against the bind pose alone.  `solve_leg_scale` re-solves the chain
        # for whatever stance it is given, so every stance in this family
        # already lands the toe correctly in the A-pose -- which is exactly
        # why the bind pose could not show that the first one was wrong.  A
        # deeper knee fold needs a shorter chain to plant at rest, and a
        # shorter chain cannot reach the floor once a run cycle extends the
        # leg: the previous -29 degrees left the Ssarathi hanging 0.035 m in
        # the air for the whole of Run_Anime while every other race planted.
        # Sampled across Idle, Walk, Run, Crouch, Run_Female and
        # Walk_Backwards, this stance plants in all six and never comes
        # closer than 0.018 m to the floor from above.
        "stance": {"calf_r": (-20., 0., 0.), "foot_r": (-6., 0., 0.),
                   "ball_r": (50., 0., 0.), "ball_leaf_r": (5., 0., 0.),
                   "neck_01": (18., 0., 0.), "Head": (-14., 0., 0.)},
    },
    # Stoneborn carry mineral mass.  Everything is thicker, and the neck is
    # short and sunk between raised shoulders; the stance is wide because the
    # thighs cannot pass each other.
    "stoneborn": {
        "stature": 1.06,
        "segment": {"neck": .72, "clavicle": 1.14, "spine": 1.02,
                    "thigh": .95, "calf": .93, "upperarm": 1.02},
        "girth": {"spine": 1.24, "neck": 1.45, "clavicle": 1.30,
                  "upperarm": 1.30, "lowerarm": 1.26, "hand": 1.18,
                  "thigh": 1.26, "calf": 1.24, "foot": 1.14},
        "swell": {"head": 1.06},
        "stance": {"calf_r": (0., 0., -8.), "foot_r": (0., 0., 5.),
                   "upperarm_r": (0., 0., -12.), "neck_01": (5., 0., 0.),
                   "Head": (-4., 0., 0.)},
    },
    # Mycelari grow rather than build muscle: a long thin stipe of a body,
    # narrow shoulders, light limbs, and a small skull under a heavy cap.
    "mycelari": {
        "stature": .995,
        "segment": {"thigh": 1.08, "calf": 1.10, "spine": .95,
                    "clavicle": .90, "neck": 1.14, "lowerarm": 1.05},
        "girth": {"spine": .86, "upperarm": .76, "lowerarm": .74,
                  "hand": .88, "thigh": .82, "calf": .78, "neck": .84,
                  "clavicle": .86},
        "swell": {"head": .93},
        "stance": {"neck_01": (5., 0., 0.), "Head": (-5., 0., 0.)},
    },
}

# Every race shipped the same greyscaled human eye, so a round mammalian
# pupil sat inside a reptile muzzle and under a mushroom cap.  `pupil` picks
# the shape painted into the iris, `iris` its colour, and `brow` tints the
# eyebrow mesh, which is human hair geometry and reads wrong on a face that is
# scaled, mineral or fungal.
#
# `headwear` lists which of the two optional creation pieces are generated at
# all.  They are cut from the scalp of the shared body, so on a race with its
# own head anatomy they intersect it: a Mycelari cap has nowhere to put a hat,
# and a skullcap clips Votary horns and the Ssarathi crest.  The Glasswarden
# lens rig sits exactly on the band line.
RACE_FACE = {
    "luminous": {},
    "votary": {"headwear": ("band",)},
    "glasswarden": {"headwear": ("cap",)},
    "orun": {},
    "greyhaven": {},
    "ssarathi": {"pupil": "slit", "iris": (206, 152, 44),
                 "brow": (34, 84, 62), "headwear": ()},
    "stoneborn": {"pupil": "facet", "iris": (96, 198, 210),
                  "brow": (86, 80, 74), "headwear": ()},
    "mycelari": {"pupil": "none", "iris": (74, 52, 34),
                 "brow": (96, 72, 46), "headwear": ()},
}
DEFAULT_IRIS = (104, 78, 52)

PLAYER_ACTOR_TYPES = {
    0: "luminous_female", 1: "luminous_male",
    2: "votary_female", 3: "votary_male", 4: "glasswarden_female", 5: "glasswarden_male",
    37: "orun_female", 38: "orun_male", 39: "greyhaven_female", 40: "greyhaven_male",
    41: "ssarathi_female", 42: "ssarathi_male", 79: "stoneborn_female", 80: "stoneborn_male",
    81: "mycelari_female", 82: "mycelari_male",
}

CREATURES = (
    # Tuple IDs retain the authored sequence; add the four existing upstream
    # creature slots when registering against eloria-server.  Palettes for the
    # creatures that appear in the concept art are sampled from it by
    # eloria-assets/tools/extract_concept_palettes.py; the rest, which were
    # invented for this roster, keep their authored colours.
    (200, "emberfox", "Emberfox", "fox", (205, 123, 10), (143, 84, 25), .82),
    (201, "mossback_boar", "Mossback Boar", "boar", (111, 63, 29), (224, 154, 91), 1.18),
    (202, "ridgehorn", "Ridgehorn", "ram", (132, 112, 77), (214, 174, 91), 1.05),
    (203, "miretoad", "Miretoad", "toad", (137, 82, 18), (224, 185, 109), 1.15),
    (204, "ash_crawler", "Ash Crawler", "lizard", (67, 62, 66), (172, 63, 54), 1.30),
    (205, "frost_maw", "Frost Maw", "wolf", (105, 153, 205), (38, 89, 196), 1.18),
    (206, "bog_lurker", "Bog Lurker", "toad", (48, 83, 65), (111, 151, 83), 1.42),
    (207, "sunscale_drake", "Sunscale Drake", "drake", (184, 117, 42), (57, 145, 141), 1.35),
    (208, "red_fox", "Red Fox", "fox", (185, 75, 19), (224, 165, 116), .74),
    (209, "snow_hare", "Snow Hare", "hare", (148, 152, 165), (55, 79, 151), .62),
    (210, "mountain_goat", "Mountain Goat", "ram", (134, 150, 181), (73, 74, 109), .92),
    (211, "black_bear", "Black Bear", "bear", (43, 39, 38), (100, 88, 68), 1.28),
    (212, "elk", "Elk", "elk", (150, 70, 26), (224, 164, 110), 1.08),
    (213, "wild_boar", "Wild Boar", "boar", (88, 73, 59), (151, 116, 72), 1.04),
    (214, "dire_wolf", "Dire Wolf", "wolf", (70, 80, 89), (132, 155, 166), 1.13),
    (215, "frost_tiger", "Frost Tiger", "cat", (94, 148, 205), (32, 74, 158), 1.14),
    (216, "giant_crocodile", "Giant Crocodile", "crocodile", (97, 88, 47), (224, 202, 159), 1.55),
    (217, "fire_salamander", "Fire Salamander", "lizard", (184, 69, 33), (245, 153, 48), 1.02),
    # ART OVERRIDDEN: creatures/thunder_ram.glb is no longer what this line
    # builds. It carries hand-animated Meshy art accepted in review, at a
    # scale of 1.129 and a facing correction of 180 in models.json. This
    # line still describes the procedural ram, so a run with --only all or
    # --only creatures WILL write the old blocky body back over it.
    (218, "thunder_ram", "Thunder Ram", "ram", (102, 99, 94), (91, 160, 188), 1.24),
    (219, "giant_rat", "Giant Rat", "rat", (105, 85, 70), (179, 138, 92), .84),
    (220, "raccoon", "Raccoon", "fox", (93, 94, 90), (45, 48, 54), .72),
    (221, "river_otter", "River Otter", "otter", (94, 70, 47), (51, 111, 120), .75),
    (222, "porcupine", "Porcupine", "porcupine", (107, 82, 55), (48, 44, 38), .82),
    (223, "moose", "Moose", "elk", (91, 70, 48), (171, 133, 77), 1.28),
    (224, "lynx", "Lynx", "cat", (157, 126, 88), (71, 65, 61), .82),
    (225, "desert_tortoise", "Desert Tortoise", "tortoise", (172, 112, 48), (224, 182, 110), 1.06),
    (226, "saber_tooth_cat", "Saber-Tooth Cat", "saber_cat", (176, 137, 82), (235, 220, 173), 1.20),
    (227, "armored_rhino", "Armored Rhino", "rhino", (104, 105, 99), (62, 118, 128), 1.48),
    (228, "giant_komodo", "Giant Komodo", "lizard", (96, 82, 50), (224, 193, 112), 1.42),
    (229, "ice_bear", "Ice Bear", "bear", (122, 155, 188), (56, 97, 171), 1.48),
    (230, "lava_hound", "Lava Hound", "wolf", (154, 55, 30), (246, 119, 38), 1.17),
    (231, "two_tailed_fox", "Two-Tailed Fox", "two_tail_fox", (183, 100, 44), (63, 151, 164), .90),
)
CREATURE_ACTOR_TYPE_OFFSET = 4

# Scenery livestock authored by eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py.  They
# are not built here, but this script owns models.json and the asset catalog, so
# it has to re-register them or a plain rebuild silently unregisters the herds.
# The wider concept-art roster occupies one contiguous block after every range
# already in models.json (which ends at 427).  Server-side actor-type allocation
# belongs to eloria-server; these ids are reserved here for it to adopt.
ROSTER_ACTOR_TYPE_BASE = 428
HOVERING_FAMILIES = {"amorphous"}


def roster_actor_type(index: int) -> int:
    return ROSTER_ACTOR_TYPE_BASE + index


# The Sunmane camps' horses: (slug, label, archetype, scale, tacked, server
# actor type). eloria-server's creatures.txt allocates the actor types and
# stands them as tame livestock; they are no longer ambient scenery.
AMBIENT_CREATURES = (
    ("sunmane_steppe_horse", "Sunmane Steppe Horse", "equine", 1.25, False, 785),
    ("sunmane_dun_mare", "Sunmane Dun Mare", "equine", 1.2, False, 786),
    ("sunmane_grey_pony", "Sunmane Grey Pony", "equine", 1.1, True, 787),
)
AMBIENT_NOTE = ("The Sunmane camps' livestock: stood in pens and at hitching posts as tame creature "
                "spawns (eloria-server spawns.txt `tame` rows, eloria/livestock.py) that nobody can attack. Each carries "
                "the server actor type eloria-server's creatures.txt gives it; they replaced the client-only ambient herds.")
AMBIENT_SOURCE_NOTE = ("Authored to equine proportions on the shared creature rig "
                       "by eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py.")

import torso_designs
from legwear_pieces import LEGWEAR_EQUIPMENT

EQUIPMENT = (
    # part 0: weapons
    ("amberwood_longbow", "Amberwood Longbow", 0, 100, "bow", (74, 111, 61), (210, 145, 57)),
    ("ranger_leafblade", "Ranger Leafblade", 0, 101, "sword", (88, 116, 68), (196, 191, 139)),
    ("glasswarden_staff", "Glasswarden Resonance Staff", 0, 102, "staff", (78, 62, 121), (96, 205, 218)),
    ("glasswarden_pick", "Glasswarden Crystal Pick", 0, 103, "pick", (77, 64, 111), (130, 194, 223)),
    ("greyhaven_cutlass", "Greyhaven Cutlass", 0, 104, "sword", (49, 74, 91), (193, 198, 190)),
    ("greyhaven_harpoon", "Greyhaven Harpoon", 0, 105, "spear", (61, 79, 88), (176, 194, 188)),
    ("orun_sun_spear", "Orun Sun Spear", 0, 106, "spear", (151, 77, 34), (221, 169, 70)),
    ("ssarathi_glaive", "Ssarathi River Glaive", 0, 107, "glaive", (42, 105, 83), (188, 153, 67)),
    ("luminous_mace", "Luminous Compact Mace", 0, 108, "mace", (40, 117, 132), (214, 190, 105)),
    ("votary_ice_sword", "Votary Ice Sword", 0, 109, "sword", (112, 151, 173), (220, 240, 244)),
    ("stoneborn_hammer", "Stoneborn Memory Hammer", 0, 110, "hammer", (101, 92, 84), (84, 189, 199)),
    ("mycelari_staff", "Mycelari Spore Staff", 0, 111, "staff", (93, 113, 64), (210, 145, 91)),
    ("four_gates_guard_spear_native", "Four Gates Guardian Spear", 0, 112, "spear", (41, 116, 127), (224, 193, 103)),
    ("maritime_crossbow", "Greyhaven Maritime Crossbow", 0, 113, "crossbow", (66, 72, 76), (176, 132, 72)),
    # part 1: shields
    ("amberwood_roundshield", "Amberwood Roundshield", 1, 100, "roundshield", (83, 96, 58), (192, 124, 47)),
    ("glasswarden_shield", "Glasswarden Crystal Shield", 1, 101, "kite", (80, 63, 123), (85, 204, 216)),
    ("greyhaven_anchor_shield", "Greyhaven Anchor Shield", 1, 102, "roundshield", (46, 72, 91), (173, 187, 183)),
    ("orun_sun_shield", "Orun Sun Shield", 1, 103, "roundshield", (151, 76, 34), (219, 163, 62)),
    ("ssarathi_shell_shield", "Ssarathi Shell Shield", 1, 104, "shell", (43, 111, 89), (187, 151, 67)),
    ("four_gates_guard_shield_native", "Four Gates Guardian Shield", 1, 105, "kite", (39, 112, 124), (219, 190, 101)),
    # part 2: capes - none here since 2026-10; 2:100-105 are tints of the
    # shared sculpted cape (equipment_authoring.GENERIC_EQUIPMENT, generic_cape).
    # part 3: helmets
    ("amberwood_ranger_hood", "Amberwood Ranger Hood", 3, 100, "hood", (55, 87, 50), (143, 104, 50)),
    ("glasswarden_helm", "Glasswarden Crystal Helm", 3, 101, "helm", (75, 58, 116), (92, 202, 217)),
    ("greyhaven_helm", "Greyhaven League Helm", 3, 102, "helm", (56, 68, 76), (174, 184, 181)),
    ("orun_sunmane_helm", "Orun Sunmane Helm", 3, 103, "helm", (146, 72, 32), (218, 160, 61)),
    ("ssarathi_crest_helm", "Ssarathi Crest Helm", 3, 104, "crest", (39, 103, 82), (186, 151, 66)),
    ("luminous_circlet", "Luminous Compact Circlet", 3, 105, "circlet", (42, 124, 136), (224, 199, 111)),
    ("votary_fur_hood", "Votary Fur Hood", 3, 106, "hood", (113, 145, 164), (223, 230, 226)),
    ("stoneborn_crown", "Stoneborn Crystal Crown", 3, 107, "crest", (99, 92, 86), (92, 190, 201)),
    ("mycelari_cap", "Mycelari Spore Cap", 3, 108, "mushroom", (98, 116, 67), (208, 141, 87)),
    # part 4: legs
    ("amberwood_ranger_legs", "Amberwood Ranger Leggings", 4, 100, "legs", (64, 82, 48), (128, 83, 42)),
    ("glasswarden_greaves", "Glasswarden Crystal Greaves", 4, 101, "legs", (71, 55, 108), (89, 185, 207)),
    ("greyhaven_trousers", "Greyhaven League Trousers", 4, 102, "legs", (44, 59, 70), (121, 143, 145)),
    ("orun_rider_legs", "Orun Rider Leggings", 4, 103, "legs", (121, 64, 33), (193, 132, 57)),
    ("ssarathi_scale_legs", "Ssarathi Scale Leggings", 4, 104, "legs", (37, 93, 75), (143, 137, 67)),
    ("votary_winter_legs", "Votary Winter Leggings", 4, 105, "legs", (96, 125, 143), (211, 222, 219)),
    ("luminous_casual_pants", "Luminous Casual Pants", 4, 106, "pants", (47, 65, 83), (52, 126, 139)),
    # part 5: bodies
    ("amberwood_ranger_cuirass", "Amberwood Ranger Cuirass", 5, 100, "cuirass", (64, 91, 52), (170, 103, 43)),
    ("glasswarden_cuirass", "Glasswarden Crystal Cuirass", 5, 101, "cuirass", (76, 58, 116), (90, 195, 211)),
    ("greyhaven_coat", "Greyhaven League Coat", 5, 102, "coat", (46, 66, 80), (146, 166, 165)),
    ("orun_sun_cuirass", "Orun Sun Cuirass", 5, 103, "cuirass", (146, 72, 32), (219, 163, 64)),
    ("ssarathi_scale_cuirass", "Ssarathi Scale Cuirass", 5, 104, "cuirass", (38, 101, 81), (183, 148, 66)),
    ("luminous_turquoise_robe", "Luminous Turquoise Robe", 5, 105, "robe", (39, 118, 132), (222, 198, 110)),
    ("votary_fur_mantle", "Votary Fur Mantle", 5, 106, "coat", (104, 136, 156), (223, 231, 228)),
    ("stoneborn_plate", "Stoneborn Memory Plate", 5, 107, "cuirass", (101, 94, 86), (88, 184, 194)),
    ("mycelari_mantle", "Mycelari Spore Mantle", 5, 108, "robe", (91, 116, 66), (205, 142, 90)),
    ("four_gates_guard_cuirass", "Four Gates Guardian Cuirass", 5, 109, "cuirass", (40, 112, 125), (219, 190, 102)),
    ("luminous_short_sleeve_shirt", "Luminous Short-Sleeve Shirt", 5, 110, "shirt", (45, 125, 139), (222, 198, 110)),
    # part 6: boots
    ("amberwood_ranger_boots", "Amberwood Ranger Boots", 6, 100, "boots", (78, 55, 37), (137, 92, 46)),
    ("glasswarden_boots", "Glasswarden Crystal Boots", 6, 101, "boots", (70, 55, 104), (88, 181, 200)),
    ("greyhaven_boots", "Greyhaven League Boots", 6, 102, "boots", (47, 55, 61), (114, 126, 125)),
    ("orun_rider_boots", "Orun Rider Boots", 6, 103, "boots", (103, 58, 35), (179, 116, 53)),
    ("ssarathi_scale_boots", "Ssarathi Scale Boots", 6, 104, "boots", (39, 88, 72), (132, 126, 64)),
    ("votary_winter_boots", "Votary Winter Boots", 6, 105, "boots", (91, 112, 125), (205, 216, 213)),
    ("luminous_casual_boots", "Luminous Casual Boots", 6, 106, "boots", (64, 47, 39), (52, 126, 139)),
    # part 7: neck
    ("amberwood_amulet", "Amberwood Leaf Amulet", 7, 100, "amulet", (76, 104, 51), (211, 137, 50)),
    ("glasswarden_resonator", "Glasswarden Resonator", 7, 101, "amulet", (75, 58, 112), (89, 198, 215)),
    ("greyhaven_compass", "Greyhaven Compass", 7, 102, "amulet", (50, 73, 88), (192, 168, 91)),
    ("orun_sun_amulet", "Orun Sun Amulet", 7, 103, "amulet", (146, 73, 34), (220, 166, 66)),
    ("ssarathi_shell_amulet", "Ssarathi Shell Amulet", 7, 104, "amulet", (41, 101, 82), (186, 151, 68)),
    ("luminous_orbit_amulet", "Luminous Orbit Amulet", 7, 105, "amulet", (42, 120, 133), (222, 198, 109)),
    # part 5 continues: the sixty-four concept designs, appended below rather
    # than written out here so a sheet cell, a visual id and a construction stay
    # in one place.  See eloria-assets/tools/torso_designs.py.
) + torso_designs.entries() + LEGWEAR_EQUIPMENT

# Each design's finish and construction, registered the way the pieces that
# predate them are.  The authoring tool reads both by slug, which is also how a
# fit variant picks up the construction of the piece it is a variant of.
equipment_authoring.EQUIPMENT_FINISH.update(
    {slug: finish for slug, _label, _kind, finish, _base, _accent, _style
     in torso_designs.DESIGNS})
equipment_authoring.GARMENT_STYLES.update(
    {slug: style for slug, _label, _kind, _finish, _base, _accent, style
     in torso_designs.DESIGNS})


def align4(value: int) -> int:
    return (value + 3) & ~3


def quat(axis: str, angle: float) -> list[float]:
    half = angle * .5
    values = {"x": [math.sin(half), 0., 0., math.cos(half)],
              "y": [0., math.sin(half), 0., math.cos(half)],
              "z": [0., 0., math.sin(half), math.cos(half)]}
    return values[axis]


class GLB:
    def __init__(self, *, generator: str = "Eloria native Nymara builder"):
        self.binary = bytearray()
        self.doc = {"asset": {"version": "2.0", "generator": generator},
                    "scene": 0, "scenes": [{"nodes": []}], "nodes": [],
                    "meshes": [], "materials": [], "bufferViews": [],
                    "accessors": [], "buffers": [{"byteLength": 0}]}

    def bytes_view(self, raw: bytes, *, target: int | None = None) -> int:
        while len(self.binary) & 3:
            self.binary.append(0)
        offset = len(self.binary)
        self.binary.extend(raw)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(raw)}
        if target is not None:
            view["target"] = target
        self.doc["bufferViews"].append(view)
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, values: np.ndarray, gltf_type: str, *, target: int | None = None,
                 normalized: bool = False, bounds: bool = False) -> int:
        values = np.ascontiguousarray(values)
        component = COMPONENT_TYPES[values.dtype]
        view = self.bytes_view(values.tobytes(), target=target)
        spec = {"bufferView": view, "componentType": component,
                "count": int(values.shape[0]), "type": gltf_type}
        if normalized:
            spec["normalized"] = True
        if bounds:
            matrix = values.reshape(len(values), -1)
            spec["min"] = [float(v) for v in matrix.min(axis=0)]
            spec["max"] = [float(v) for v in matrix.max(axis=0)]
        self.doc["accessors"].append(spec)
        return len(self.doc["accessors"]) - 1

    def texture(self, name: str, png: bytes) -> int:
        view = self.bytes_view(png)
        self.doc.setdefault("images", []).append(
            {"name": name, "bufferView": view, "mimeType": "image/png"})
        image = len(self.doc["images"]) - 1
        self.doc.setdefault("samplers", []).append(
            {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
        sampler = len(self.doc["samplers"]) - 1
        self.doc.setdefault("textures", []).append({"source": image, "sampler": sampler})
        return len(self.doc["textures"]) - 1

    def material(self, name: str, color: tuple[int, int, int], *, metallic: float = 0.,
                 roughness: float = .78, emissive: tuple[int, int, int] | None = None,
                 texture_png: bytes | None = None, normal_png: bytes | None = None,
                 metallic_roughness_png: bytes | None = None,
                 double_sided: bool = False, alpha: float = 1.0,
                 alpha_mode: str | None = None) -> int:
        factor = [c / 255. for c in color] + [float(alpha)]
        pbr = {"baseColorFactor": factor, "metallicFactor": metallic,
               "roughnessFactor": roughness}
        if texture_png is not None:
            pbr["baseColorTexture"] = {"index": self.texture(name + " Base Color", texture_png)}
        if metallic_roughness_png is not None:
            pbr["metallicRoughnessTexture"] = {
                "index": self.texture(name + " Roughness", metallic_roughness_png)}
        material = {"name": name, "pbrMetallicRoughness": pbr, "doubleSided": double_sided}
        if alpha_mode:
            material["alphaMode"] = alpha_mode
        if normal_png is not None:
            material["normalTexture"] = {"index": self.texture(name + " Normal", normal_png)}
        if emissive is not None:
            material["emissiveFactor"] = [c / 255. for c in emissive]
        self.doc["materials"].append(material)
        return len(self.doc["materials"]) - 1

    def primitive(self, positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray,
                  indices: np.ndarray, material: int, *, joints: np.ndarray | None = None,
                  weights: np.ndarray | None = None) -> dict:
        attributes = {
            "POSITION": self.accessor(positions.astype("float32"), "VEC3", target=34962, bounds=True),
            "NORMAL": self.accessor(normals.astype("float32"), "VEC3", target=34962),
            "TEXCOORD_0": self.accessor(uvs.astype("float32"), "VEC2", target=34962),
        }
        if joints is not None and weights is not None:
            attributes["JOINTS_0"] = self.accessor(joints.astype("uint16"), "VEC4", target=34962)
            attributes["WEIGHTS_0"] = self.accessor(weights.astype("float32"), "VEC4", target=34962)
        return {"attributes": attributes,
                "indices": self.accessor(indices.astype("uint32").reshape(-1), "SCALAR", target=34963),
                "material": material, "mode": 4}

    def mesh_node(self, name: str, primitives: list[dict], *, skin: int | None = None,
                  parent: int | None = None) -> int:
        self.doc["meshes"].append({"name": name, "primitives": primitives})
        node = {"name": name, "mesh": len(self.doc["meshes"]) - 1}
        if skin is not None:
            node["skin"] = skin
        self.doc["nodes"].append(node)
        index = len(self.doc["nodes"]) - 1
        if parent is None:
            self.doc["scenes"][0]["nodes"].append(index)
        else:
            self.doc["nodes"][parent].setdefault("children", []).append(index)
        return index

    def write(self, path: Path) -> None:
        self.doc["buffers"][0]["byteLength"] = len(self.binary)
        encoded = json.dumps(self.doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        encoded += b" " * (align4(len(encoded)) - len(encoded))
        binary = bytes(self.binary) + b"\0" * (align4(len(self.binary)) - len(self.binary))
        total = 12 + 8 + len(encoded) + 8 + len(binary)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"glTF" + struct.pack("<II", 2, total)
                         + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                         + struct.pack("<II", len(binary), 0x004E4942) + binary)


def read_accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]])
    width = TYPE_WIDTHS[spec["type"]]
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    values = np.ndarray(shape, dtype=dtype, buffer=binary, offset=start, strides=strides).copy()
    if spec.get("normalized"):
        if np.issubdtype(dtype, np.unsignedinteger):
            values = values.astype(np.float32) / np.iinfo(dtype).max
        else:
            values = np.maximum(values.astype(np.float32) / np.iinfo(dtype).max, -1.)
    return values


def recolored_texture(path: Path, base: tuple[int, int, int], accent: tuple[int, int, int],
                      feature: str) -> bytes:
    image = Image.open(path).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
    source = np.asarray(image).astype(np.float32)
    luminance = (source[..., :3] * np.array([.2126, .7152, .0722])).sum(axis=2) / 255.
    shadow = np.array(base, dtype=np.float32) * .42
    highlight = np.array(base, dtype=np.float32) * .76 + np.array(accent, dtype=np.float32) * .24
    rgb = shadow[None, None, :] * (1. - luminance[..., None]) + highlight[None, None, :] * luminance[..., None]
    yy, xx = np.mgrid[0:512, 0:512]
    if feature == "scaled":
        mask = ((xx // 18 + yy // 14) % 4 == 0)[..., None]
        rgb = np.where(mask, rgb * .72 + np.array(accent) * .28, rgb)
    elif feature == "stone":
        cracks = (((xx * 7 + yy * 11) % 97) < 2)[..., None]
        rgb = np.where(cracks, np.array(accent) * .78, rgb)
    elif feature == "fungal":
        spores = (((xx * 13 + yy * 17) % 149) < 3)[..., None]
        rgb = np.where(spores, np.array(accent), rgb)
    elif feature == "crystal":
        facets = (((xx + 2 * yy) % 71) < 3)[..., None]
        rgb = np.where(facets, np.array(accent), rgb)
    out = np.dstack((np.clip(rgb, 0, 255).astype(np.uint8), source[..., 3].astype(np.uint8)))
    encoded = io.BytesIO()
    Image.fromarray(out, "RGBA").save(encoded, format="PNG", optimize=True)
    return encoded.getvalue()


@lru_cache(maxsize=64)
def resized_texture(path: Path, size: int = 512) -> bytes:
    image = Image.open(path).convert("RGBA")
    if max(image.size) > size:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG", optimize=True)
    return encoded.getvalue()


@lru_cache(maxsize=64)
def neutral_texture(path: Path, *, floor: float = .34, size: int = 512) -> bytes:
    """Retain authored texture detail while making it safe for runtime tinting."""
    image = Image.open(path).convert("RGBA")
    if max(image.size) > size:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    source = np.asarray(image).astype(np.float32)
    luminance = (source[..., :3] * np.array([.2126, .7152, .0722])).sum(axis=2) / 255.
    luminance = floor + (1. - floor) * luminance
    rgb = np.repeat((luminance * 255.)[..., None], 3, axis=2)
    out = np.dstack((np.clip(rgb, 0, 255).astype(np.uint8), source[..., 3].astype(np.uint8)))
    encoded = io.BytesIO()
    Image.fromarray(out, "RGBA").save(encoded, format="PNG", optimize=True)
    return encoded.getvalue()


def _detail_field(kind: str, size: int) -> np.ndarray:
    """Value field behind the wardrobe detail maps."""
    yy, xx = np.mgrid[0:size, 0:size]
    if kind == "cloth":
        # A real weave.  The first two terms used to be sin(n*pi) on an
        # integer grid, which is zero to within float error, so "cloth" was
        # silently just the one diagonal band the third term draws.
        value = (.86 + np.sin(xx * math.pi / 3.) * .035
                 + np.sin(yy * math.pi / 3.) * .028
                 + np.sin((xx + yy) * math.pi / 31.) * .020)
    elif kind == "leather":
        grain = (np.sin(xx * .173 + np.sin(yy * .071) * 2.1)
                 + np.sin(yy * .219 + np.sin(xx * .049) * 1.7)) * .035
        pores = (((xx * 17 + yy * 29) % 113) < 3) * -.08
        value = .82 + grain + pores
    else:
        # Braided trim.  A twelve-pixel diagonal lattice read as a printed
        # pattern at gameplay distance rather than as a woven cord.
        value = (.90 + np.sin((xx + yy) * math.pi / 3.) * .030
                 + np.sin((xx - yy) * math.pi / 9.) * .018)
    return value


@lru_cache(maxsize=16)
def surface_detail_texture(kind: str, size: int = 512) -> bytes:
    """Neutral cloth/leather detail that remains compatible with runtime tinting."""
    channel = np.clip(_detail_field(kind, size) * 255., 0, 255).astype(np.uint8)
    alpha = np.full((size, size), 255, dtype=np.uint8)
    encoded = io.BytesIO()
    Image.fromarray(np.dstack((channel, channel, channel, alpha)), "RGBA").save(
        encoded, format="PNG", optimize=True)
    return encoded.getvalue()


# Relief and roughness window for each wardrobe surface.  The garments had an
# albedo and nothing else, so cloth, leather and metal trim all answered a
# light identically -- and the trim, carrying a flat metallic factor with no
# roughness break at all, blew out into a solid highlight wherever it caught
# the key.  Equipment was given this treatment already; the player wardrobe
# was not.
WARDROBE_SURFACES = {
    "cloth": {"relief": .20, "rough": (.78, .97)},
    "leather": {"relief": .38, "rough": (.54, .86)},
    "trim": {"relief": .34, "rough": (.30, .66)},
}


@lru_cache(maxsize=16)
def surface_detail_maps(kind: str, size: int = 512) -> tuple[bytes, bytes]:
    """Normal and metallic-roughness companions to `surface_detail_texture`.

    The metallic channel is left at full so the material's own metallic factor
    still decides how metallic the trim is; only the roughness is textured.
    """
    spec = WARDROBE_SURFACES.get(kind, WARDROBE_SURFACES["cloth"])
    field = _detail_field(kind, size)
    span = float(field.max() - field.min())
    # Roughness wants the full contrast of the pattern...
    height = (field - field.min()) / span if span > 1e-6 else field * 0.

    # ...but the normal must not.  Stretching a weave that varies by three per
    # cent of a unit across the full 0..1 range and then differencing it turns
    # a shirt into chainmail, so the relief is taken from the field's real
    # amplitude instead of a normalised copy of it.
    relief = field - float(field.mean())
    strength = spec["relief"] * size / 64.
    gx = (np.roll(relief, -1, axis=1) - np.roll(relief, 1, axis=1)) * .5 * strength
    gy = (np.roll(relief, -1, axis=0) - np.roll(relief, 1, axis=0)) * .5 * strength
    normal = np.dstack((-gx, -gy, np.ones_like(height)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-9)
    encoded = np.clip((normal * .5 + .5) * 255., 0, 255).astype(np.uint8)
    normal_png = io.BytesIO()
    Image.fromarray(encoded, "RGB").save(normal_png, format="PNG", optimize=True)

    low, high = spec["rough"]
    green = np.clip((high - (high - low) * height) * 255., 0, 255).astype(np.uint8)
    blue = np.full((size, size), 255, dtype=np.uint8)
    red = np.zeros((size, size), dtype=np.uint8)
    mr_png = io.BytesIO()
    Image.fromarray(np.dstack((red, green, blue)), "RGB").save(
        mr_png, format="PNG", optimize=True)
    return normal_png.getvalue(), mr_png.getvalue()


@lru_cache(maxsize=32)
def race_eye_texture(path: Path, pupil: str, iris: tuple[int, int, int],
                     *, floor: float = .62, size: int = 512) -> bytes:
    """The source eye, repainted with a race-appropriate iris and pupil.

    Every race shipped the same greyscaled human eye, so a round mammalian
    pupil sat inside a reptile muzzle and under a mushroom cap.  The sclera,
    lids and lashes are kept from the authored texture -- they carry detail
    worth having -- and only the iris disc is re-authored.  The iris is
    located from the source rather than hard-coded, so this stays correct if
    the Quaternius texture is ever replaced.
    """
    image = Image.open(path).convert("RGBA")
    if max(image.size) > size:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    source = np.asarray(image).astype(np.float32)
    height, width = source.shape[:2]
    luminance = (source[..., :3] * np.array([.2126, .7152, .0722])).sum(axis=2) / 255.
    base = floor + (1. - floor) * luminance
    rgb = np.repeat((base * 255.)[..., None], 3, axis=2)

    # The pupil is the darkest thing in the texture; its centroid is the iris.
    dark = luminance <= np.quantile(luminance, .004)
    ys, xs = np.nonzero(dark)
    if len(xs):
        cx, cy = float(xs.mean()), float(ys.mean())
    else:
        cx, cy = width * .45, height * .48
    iris_radius = width * .098
    pupil_radius = width * .034

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    radius = np.hypot(dx, dy)
    inside = radius <= iris_radius
    # Radial fibre and a darker limbal ring, so the iris is not a flat disc.
    angle = np.arctan2(dy, dx)
    fibre = .78 + .22 * np.sin(angle * 26.)
    edge = np.clip(1. - (radius / max(iris_radius, 1e-6)) ** 6, 0., 1.)
    tint = np.asarray(iris, dtype=np.float32)[None, None, :]
    painted = tint * (fibre * edge * .85 + .30)[..., None]
    rgb = np.where(inside[..., None], painted, rgb)

    if pupil == "slit":
        # A vertical lens: full height of the iris, pinched to nothing at top
        # and bottom.  This is the single clearest reptilian cue on a face.
        half = np.sqrt(np.clip(1. - (dy / max(iris_radius, 1e-6)) ** 2, 0., 1.))
        slit = np.abs(dx) <= pupil_radius * .62 * half
        rgb = np.where((inside & slit)[..., None], np.float32(14.), rgb)
    elif pupil == "facet":
        # A cut mineral eye: bright planes and no organic pupil at all.
        wedge = np.floor(angle / (math.pi / 7.))
        band = np.floor(radius / max(iris_radius / 3., 1e-6))
        facet = ((wedge + band) % 2. == 0.)
        rgb = np.where((inside & facet)[..., None], np.clip(rgb * 1.55, 0, 255), rgb)
        rgb = np.where((inside & (radius <= pupil_radius * .7))[..., None],
                       np.float32(24.), rgb)
    elif pupil == "none":
        # Fungal eyes are matte and pupil-less; the whole disc goes dark.
        rgb = np.where(inside[..., None], tint * .34, rgb)
    else:
        rgb = np.where((inside & (radius <= pupil_radius))[..., None],
                       np.float32(16.), rgb)

    out = np.dstack((np.clip(rgb, 0, 255).astype(np.uint8),
                     source[..., 3].astype(np.uint8)))
    encoded = io.BytesIO()
    Image.fromarray(out, "RGBA").save(encoded, format="PNG", optimize=True)
    return encoded.getvalue()




# ---------------------------------------------------------------------------
# Race feature surfaces
#
# The integrated race features used to be the only materials on a player that
# carried no maps at all: a base colour factor beside a body with albedo,
# normal and metallic-roughness textures.  Under the client's real lighting a
# flat-shaded solid next to a textured surface reads as a plastic prop stuck
# to a person, which is exactly how scale, stone and fungus were landing.
#
# Each surface is authored once as a height field and everything else is
# derived from it, so the albedo cavities, the normal map and the roughness
# breakup all describe the same relief instead of drifting apart.  Patterns
# are integer-hashed or trigonometric rather than drawn from a random
# generator, and the result is quantised to 8 bits, so the textures are
# reproducible everywhere the build runs.

def _value_noise(size: int, cells: int, seed: int) -> np.ndarray:
    """Smooth deterministic value noise on a `cells` grid, tiling seamlessly."""
    grid = np.arange(cells, dtype=np.int64)
    gx, gy = np.meshgrid(grid, grid, indexing="xy")
    key = (gx * 374761393 + gy * 668265263 + seed * 362437) & 0xFFFFFFFF
    key = (key ^ (key >> 13)) * 1274126177 & 0xFFFFFFFF
    lattice = ((key ^ (key >> 16)) & 0xFFFF) / 65535.
    # Bilinear interpolation with a smoothstep fade, wrapping at the edges.
    position = np.linspace(0., cells, size, endpoint=False)
    low = np.floor(position).astype(np.int64) % cells
    high = (low + 1) % cells
    frac = position - np.floor(position)
    fade = frac * frac * (3. - 2. * frac)
    top = (lattice[np.ix_(low, low)] * (1. - fade)[None, :]
           + lattice[np.ix_(low, high)] * fade[None, :])
    bottom = (lattice[np.ix_(high, low)] * (1. - fade)[None, :]
              + lattice[np.ix_(high, high)] * fade[None, :])
    return top * (1. - fade)[:, None] + bottom * fade[:, None]


def _fractal_noise(size: int, octaves: tuple[int, ...], seed: int) -> np.ndarray:
    """Summed value noise, normalised to 0..1."""
    total = np.zeros((size, size))
    amplitude = 1.
    weight = 0.
    for index, cells in enumerate(octaves):
        total += _value_noise(size, cells, seed + index * 17) * amplitude
        weight += amplitude
        amplitude *= .5
    total /= max(weight, 1e-6)
    span = float(total.max() - total.min())
    return (total - total.min()) / span if span > 1e-6 else total


def _cell_field(size: int, cells: int, seed: int, jitter: float = .42):
    """Deterministic Worley cells: returns (edge distance, per-cell id value).

    Stone wants hard facet boundaries rather than smooth lumps, so the plating
    is cut from cell edges instead of being mottled with noise.
    """
    axis = np.linspace(0., cells, size, endpoint=False)
    px, py = np.meshgrid(axis, axis, indexing="xy")
    best = np.full((size, size), 1e9)
    second = np.full((size, size), 1e9)
    owner = np.zeros((size, size))
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            gx = (np.floor(px).astype(np.int64) + ox)
            gy = (np.floor(py).astype(np.int64) + oy)
            key = ((gx % cells) * 374761393 + (gy % cells) * 668265263
                   + seed * 362437) & 0xFFFFFFFF
            key = (key ^ (key >> 13)) * 1274126177 & 0xFFFFFFFF
            jx = ((key >> 4) & 0xFFFF) / 65535.
            jy = ((key >> 20) & 0xFFFF) / 65535.
            value = ((key ^ (key >> 9)) & 0xFFFF) / 65535.
            cx = gx + .5 + (jx - .5) * 2. * jitter
            cy = gy + .5 + (jy - .5) * 2. * jitter
            distance = np.hypot(px - cx, py - cy)
            closer = distance < best
            second = np.where(closer, best, np.minimum(second, distance))
            owner = np.where(closer, value, owner)
            best = np.where(closer, distance, best)
    return second - best, owner


# Height field relief, albedo contrast, normal strength, the roughness window
# each surface occupies, and metallic.  Metallic is only non-zero where the
# material really is metal, because a dielectric with a raised metallic factor
# goes black in a scene without a bright reflection probe.
FEATURE_SURFACES = {
    # Overlapping keeled scales.
    "scaled": {"relief": .55, "albedo": .34, "rough": (.42, .78), "metallic": .0},
    # Cut stone: hard facet edges, coarse grain, no gloss.
    "stone": {"relief": .85, "albedo": .40, "rough": (.68, .96), "metallic": .0},
    # Cap flesh: soft radial fibre with pores.
    "fungal": {"relief": .38, "albedo": .30, "rough": (.62, .90), "metallic": .0},
    # Gill lamellae: fine parallel blades.
    "gill": {"relief": .46, "albedo": .36, "rough": (.70, .94), "metallic": .0},
    # Horn and claw keratin: growth rings plus longitudinal striation.
    "keratin": {"relief": .42, "albedo": .28, "rough": (.30, .62), "metallic": .0},
    # Faceted mineral: sharp planes, glossy.
    "crystal": {"relief": .62, "albedo": .30, "rough": (.08, .34), "metallic": .0},
    # Brass instrument fittings on the Glasswarden lens rig.
    "brass": {"relief": .30, "albedo": .22, "rough": (.22, .48), "metallic": .90},
    # Ground lens glass.
    "glass": {"relief": .16, "albedo": .14, "rough": (.04, .18), "metallic": .0},
}


def _surface_height(kind: str, size: int) -> np.ndarray:
    """The one authored relief every other map for a surface is derived from."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    u = xx / size
    v = yy / size
    if kind == "scaled":
        # Offset rows of rounded, keeled scales.  Each row is shifted half a
        # scale so the pattern interlocks the way reptile skin does.
        rows, columns = 26., 20.
        row = v * rows
        shift = (np.floor(row) % 2.) * .5
        cell_u = (u * columns + shift) % 1. - .5
        cell_v = row % 1. - .5
        radius = np.sqrt((cell_u * 1.9) ** 2 + (cell_v * 2.15) ** 2)
        scale = np.clip(1. - radius, 0., 1.) ** .62
        keel = np.clip(1. - abs(cell_u) * 3.4, 0., 1.) ** 2 * .22
        height = scale * .82 + keel
        height += _fractal_noise(size, (32, 64), 11) * .12
    elif kind == "stone":
        edge, owner = _cell_field(size, 9, 3, jitter=.46)
        # Flat facets with a hard rim: the plate faces stay level and only the
        # seams between them cut in.
        facet = np.clip(edge * 3.1, 0., 1.)
        seam = np.clip(1. - edge * 5.5, 0., 1.) ** 1.6
        height = facet * (.52 + owner * .48) - seam * .55
        height += _fractal_noise(size, (16, 48, 96), 5) * .22
    elif kind == "fungal":
        # Radial fibre running out from the cap centre, with pores.
        cx, cy = u - .5, v - .5
        angle = np.arctan2(cy, cx)
        radius = np.hypot(cx, cy)
        fibre = np.sin(angle * 74.) * .5 + .5
        height = fibre * (.20 + .34 * np.clip(radius * 2.2, 0., 1.))
        height += _fractal_noise(size, (8, 24, 64), 23) * .58
        pores = _fractal_noise(size, (96,), 41)
        height -= np.clip((pores - .70) * 3.4, 0., 1.) * .34
    elif kind == "gill":
        blades = np.sin(u * math.pi * 96.) * .5 + .5
        height = blades ** .70 * .78 + _fractal_noise(size, (24, 64), 31) * .18
    elif kind == "keratin":
        rings = np.sin(v * math.pi * 34. + _fractal_noise(size, (8,), 7) * 2.2)
        stripes = np.sin(u * math.pi * 120.) * .5 + .5
        height = (rings * .5 + .5) * .46 + stripes * .16
        height += _fractal_noise(size, (16, 48), 13) * .30
    elif kind == "crystal":
        edge, owner = _cell_field(size, 6, 19, jitter=.30)
        facet = np.clip(edge * 2.6, 0., 1.)
        height = facet * (.40 + owner * .60)
        height -= np.clip(1. - edge * 7.0, 0., 1.) ** 2 * .42
    elif kind == "brass":
        turned = np.sin(v * math.pi * 150.) * .5 + .5
        height = turned * .30 + _fractal_noise(size, (12, 40), 3) * .40
    else:  # glass
        height = _fractal_noise(size, (6, 16), 29) * .55
    span = float(height.max() - height.min())
    return (height - height.min()) / span if span > 1e-6 else height * 0.


@lru_cache(maxsize=32)
def feature_surface_textures(kind: str, size: int = 256) -> tuple[bytes, bytes, bytes]:
    """Albedo, tangent-space normal and metallic-roughness for a race surface.

    The albedo stays near-neutral so the per-race base colour factor still
    tints it: these maps add cavity shading and grain, they do not decide hue.
    """
    spec = FEATURE_SURFACES.get(kind, FEATURE_SURFACES["stone"])
    height = _surface_height(kind, size)

    # Albedo: darken the cavities and lift the peaks *around* white, so the
    # map adds cavity shading without dimming the authored colour.  Centring
    # this on 208 quietly took 18 per cent off every race feature.
    shade = 1. + (height - .5) * 2. * spec["albedo"]
    channel = np.clip(shade * 246., 0, 255).astype(np.uint8)
    alpha = np.full((size, size), 255, dtype=np.uint8)
    albedo_png = io.BytesIO()
    Image.fromarray(np.dstack((channel, channel, channel, alpha)), "RGBA").save(
        albedo_png, format="PNG", optimize=True)

    # Normal: central-difference gradient of the same relief.  Rolling the
    # difference keeps the map tileable, which matters because feature UVs are
    # scaled to world size and therefore repeat.
    strength = spec["relief"] * size / 64.
    gx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * .5 * strength
    gy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * .5 * strength
    normal = np.dstack((-gx, -gy, np.ones_like(height)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-9)
    encoded = np.clip((normal * .5 + .5) * 255., 0, 255).astype(np.uint8)
    normal_png = io.BytesIO()
    # No alpha on the normal or metallic-roughness maps: nothing reads it, and
    # a fourth channel on the least compressible image in the file is pure
    # weight.
    Image.fromarray(encoded, "RGB").save(normal_png, format="PNG", optimize=True)

    # Metallic-roughness: glTF reads roughness from green and metallic from
    # blue.  Rough where the relief is broken, smoother on the raised faces.
    low, high = spec["rough"]
    roughness = np.clip(high - (high - low) * height, 0., 1.)
    green = np.clip(roughness * 255., 0, 255).astype(np.uint8)
    blue = np.full((size, size), int(round(spec["metallic"] * 255.)), dtype=np.uint8)
    red = np.zeros((size, size), dtype=np.uint8)
    mr_png = io.BytesIO()
    Image.fromarray(np.dstack((red, green, blue)), "RGB").save(
        mr_png, format="PNG", optimize=True)
    return albedo_png.getvalue(), normal_png.getvalue(), mr_png.getvalue()


# Which surface the primary and accent halves of each race feature are made
# of.  ShapeMesh material 0 is the primary form, material 1 the accent.
# One feature texture repeat covers this much of the model, in metres, so a
# claw and a mushroom cap carry the same physical scale size instead of each
# stretching one copy of the map over whatever primitive it lands on.
FEATURE_UV_TILE = .22

FEATURE_MATERIALS = {
    "horns": ("keratin", "keratin"),
    "crystal": ("brass", "glass"),
    "scaled": ("scaled", "keratin"),
    "stone": ("stone", "crystal"),
    "fungal": ("fungal", "gill"),
}


def source_texture(document: dict, directory: Path, material_index: int,
                   texture_key: str) -> bytes | None:
    material = document["materials"][material_index]
    if texture_key == "normalTexture":
        texture_spec = material.get("normalTexture")
    else:
        texture_spec = material.get("pbrMetallicRoughness", {}).get(texture_key)
    if texture_spec is None:
        return None
    texture = document["textures"][texture_spec["index"]]
    image = document["images"][texture["source"]]
    path = directory / image["uri"]
    if not path.is_file():
        path = directory.parent / image["uri"]
    return resized_texture(path)


def quaternion_matrix(rotation: list[float]) -> np.ndarray:
    x, y, z, w = rotation
    length = math.sqrt(x*x + y*y + z*z + w*w)
    if length < 1e-8:
        return np.eye(4, dtype=np.float64)
    x, y, z, w = x/length, y/length, z/length, w/length
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), 0],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), 0],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), 0],
        [0, 0, 0, 1],
    ], dtype=np.float64)


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    translation = np.eye(4, dtype=np.float64)
    translation[:3, 3] = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
    rotation = quaternion_matrix(node.get("rotation", [0, 0, 0, 1]))
    scale = np.eye(4, dtype=np.float64)
    scale[np.arange(3), np.arange(3)] = np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64)
    return translation @ rotation @ scale


def global_node_matrix(document: dict, node_index: int) -> np.ndarray:
    parents = {}
    for parent, node in enumerate(document["nodes"]):
        for child in node.get("children", []):
            parents[child] = parent
    chain = []
    current = node_index
    while current is not None:
        chain.append(current)
        current = parents.get(current)
    result = np.eye(4, dtype=np.float64)
    for index in reversed(chain):
        result = result @ node_matrix(document["nodes"][index])
    return result


def joint_parents(document: dict, skin: dict) -> dict[int, int | None]:
    """Parent slot for every joint, indexed by position in skin["joints"]."""
    slot_of = {node: slot for slot, node in enumerate(skin["joints"])}
    parents: dict[int, int | None] = {slot: None for slot in range(len(skin["joints"]))}
    for node_index, node in enumerate(document["nodes"]):
        if node_index not in slot_of:
            continue
        for child in node.get("children", []):
            if child in slot_of:
                parents[slot_of[child]] = slot_of[node_index]
    return parents


def hierarchy_order(parents: dict[int, int | None]) -> list[int]:
    """Joint slots ordered so a parent is always visited before its children."""
    children: dict[int | None, list[int]] = {}
    for slot, parent in parents.items():
        children.setdefault(parent, []).append(slot)
    order: list[int] = []
    queue = list(children.get(None, []))
    while queue:
        slot = queue.pop(0)
        order.append(slot)
        queue.extend(children.get(slot, []))
    return order


def axis_rotation(degrees: tuple[float, float, float]) -> np.ndarray:
    """Extrinsic X-then-Y-then-Z rotation in world bind axes."""
    result = np.eye(3, dtype=np.float64)
    for axis, value in enumerate(degrees):
        if not value:
            continue
        angle = math.radians(value)
        cos, sin = math.cos(angle), math.sin(angle)
        matrix = np.eye(3, dtype=np.float64)
        i, j = [(1, 2), (2, 0), (0, 1)][axis]
        matrix[i, i] = cos; matrix[i, j] = -sin
        matrix[j, i] = sin; matrix[j, j] = cos
        result = matrix @ result
    return result


def stance_rotation(spec: dict, name: str) -> np.ndarray | None:
    """Rotation applied to a joint's offset, mirrored from the right side."""
    stance = spec.get("stance", {})
    if name in stance:
        return axis_rotation(stance[name])
    if name.endswith("_l"):
        mirrored = stance.get(name[:-2] + "_r")
        if mirrored is not None:
            # Reflecting through the YZ plane flips rotation about Y and Z.
            return axis_rotation((mirrored[0], -mirrored[1], -mirrored[2]))
    return None


def retarget_bind(source_bind: np.ndarray, parents: dict[int, int | None],
                  names: list[str], spec: dict, leg_scale: float) -> np.ndarray:
    """Rebuild the global bind pose from race segment lengths and stance.

    Stance is expressed by rotating a joint's *offset from its parent*, never
    by rotating the joint's own frame.  That distinction is the whole reason a
    digitigrade Ssarathi is possible at all on a shared rig: glTF rotation
    tracks are absolute, so the animation library overwrites every rest
    rotation the moment a clip plays, and any anatomy stored there would snap
    back to the human A-pose.  Local translations are never animated below the
    pelvis, so anatomy stored in the offsets survives every clip -- the limb
    keeps its own segment directions inside whatever frame the clip puts the
    parent in.  Joint frames are therefore left exactly as the source authored
    them, which also means the clips' rotations still mean what they meant.
    """
    segment = spec.get("segment", {})
    result = np.zeros_like(source_bind)
    for slot in hierarchy_order(parents):
        parent = parents[slot]
        if parent is None:
            result[slot] = source_bind[slot].copy()
            continue
        group = joint_group(names[parent])
        scale = segment.get(group, 1.)
        if group in LEG_GROUPS:
            scale *= leg_scale
        offset = (source_bind[slot][:3, 3] - source_bind[parent][:3, 3]) * scale
        rotation = stance_rotation(spec, names[slot])
        if rotation is not None:
            offset = rotation @ offset
        result[slot] = np.eye(4, dtype=np.float64)
        result[slot][:3, :3] = source_bind[slot][:3, :3]
        result[slot][:3, 3] = result[parent][:3, 3] + offset
    return result


def solve_leg_scale(source_bind: np.ndarray, parents: dict[int, int | None],
                    names: list[str], spec: dict) -> float:
    """Leg-chain scale that restores the source hip-to-ground distance.

    Ground contact height is affine in the chain scale -- the offsets are
    scaled, the rotations are not -- so two probes solve it exactly.
    """
    ground = [names.index(joint) for joint in GROUND_JOINTS]
    target = source_bind[ground, 1, 3].min()
    probes = []
    for candidate in (1., 1.1):
        bind = retarget_bind(source_bind, parents, names, spec, candidate)
        probes.append((candidate, float(bind[ground, 1, 3].min())))
    (k0, y0), (k1, y1) = probes
    if abs(y1 - y0) < 1e-9:
        return 1.
    return k0 + (target - y0) * (k1 - k0) / (y1 - y0)


def bone_axis(slot: int, source_bind: np.ndarray, parents: dict[int, int | None],
              names: list[str], children: dict[int, list[int]]) -> np.ndarray:
    """Unit bone direction at a joint, in that joint's own bind frame."""
    options = children.get(slot, [])
    preferred = CHAIN_CHILD.get(names[slot])
    target = None
    for child in options:
        if preferred is None or names[child] == preferred:
            target = source_bind[child][:3, 3]
            break
    if target is None and options:
        target = source_bind[options[0]][:3, 3]
    if target is None:
        parent = parents[slot]
        if parent is None:
            return np.array([0., 1., 0.])
        direction = source_bind[slot][:3, 3] - source_bind[parent][:3, 3]
    else:
        direction = target - source_bind[slot][:3, 3]
    length = np.linalg.norm(direction)
    if length < 1e-7:
        return np.array([0., 1., 0.])
    return source_bind[slot][:3, :3].T @ (direction / length)


def shape_matrices(source_bind: np.ndarray, target_bind: np.ndarray,
                   parents: dict[int, int | None], names: list[str],
                   spec: dict) -> np.ndarray:
    """Per-joint skinning transform T = B . G . A^-1 for the race body."""
    girth = spec.get("girth", {})
    swell = spec.get("swell", {})
    children: dict[int, list[int]] = {}
    for slot, parent in parents.items():
        if parent is not None:
            children.setdefault(parent, []).append(slot)
    result = np.zeros_like(source_bind)
    identity = np.eye(3, dtype=np.float64)
    for slot in range(len(source_bind)):
        group = joint_group(names[slot])
        thickness = girth.get(group, 1.)
        uniform = swell.get(group, 1.)
        axis = bone_axis(slot, source_bind, parents, names, children)
        # Scale only across the bone, so a thicker arm stays the same length
        # whatever direction the bone happens to point in world space.
        local = uniform * (identity + (thickness - 1.) *
                           (identity - np.outer(axis, axis)))
        shape = np.eye(4, dtype=np.float64)
        shape[:3, :3] = local
        result[slot] = target_bind[slot] @ shape @ np.linalg.inv(source_bind[slot])
    return result


# ---------------------------------------------------------------------------
# Base bodies
#
# All sixteen rigs derived from the one Quaternius "Superhero" mesh, which is
# heroic-proportioned and heavy through the chest and shoulders, so the five
# human cultures were one physique in five colours.  ANATOMY's `girth` can
# only scale a whole bone uniformly, which cannot tell a rib cage from a
# pectoral or thin a forearm towards the wrist; turning it up further just
# made a shrunken heroic body.
#
# A base body is a real re-proportioning of the shared mesh instead.  It is a
# radial field: every vertex is scaled across the bone that drives it, by a
# factor that tapers along that bone and is further modulated by anatomical
# zones anchored to named joints, so it works on the male and female
# skeletons alike without a second set of coordinates.
#
# It runs on the source mesh in bind space, *before* the race retarget, and
# it never moves a vertex along its own bone.  Two consequences matter:
# garment cuts are still selected from the untouched source body, so no hem
# moves; and the rig -- hip height, ground contact, the solved leg chain -- is
# not involved at all, because this changes the mesh and not the skeleton.

BASE_BODIES = {
    # The Quaternius body exactly as authored.  An empty preset is the
    # identity: the reshape returns its input untouched, so every race that
    # uses it is byte-for-byte what it was before base bodies existed.
    "heroic": {},
    # Glasswarden field engineers and scholars: a light frame with a narrow
    # rib cage, little deltoid or pectoral mass, and limbs that taper rather
    # than hold their thickness to the wrist and ankle.
    "slim": {
        # Radial scale across each bone, at its root and at its tip.  `foot`,
        # `ball`, `head` and the fingers are deliberately absent: a lighter
        # person does not get smaller feet, and leaving the foot alone keeps
        # ground contact exactly where the leg solve put it.
        "taper": {
            "pelvis": (.94, .94),
            "spine": (.93, .88),
            "neck": (.94, .94),
            "clavicle": (.86, .82),
            "upperarm": (.83, .87),
            "lowerarm": (.87, .90),
            "hand": (.96, .96),
            "thigh": (.90, .92),
            "calf": (.91, .93),
        },
        # Anatomical masses, as ellipsoids anchored to a joint: (joint,
        # offset from it in metres, radii, scale).  These multiply the taper,
        # so they subtract mass from a specific place rather than from a whole
        # bone -- which is the difference between a slimmer body and a
        # smaller one.
        "zones": (
            ("spine_03", (0., .075, .055), (.185, .105, .115), .90),
            ("upperarm_l", (0., 0., 0.), (.105, .105, .115), .88),
            ("upperarm_r", (0., 0., 0.), (.105, .105, .115), .88),
            ("spine_01", (0., .015, 0.), (.185, .105, .150), .94),
            ("pelvis", (0., .020, 0.), (.200, .095, .155), .96),
        ),
    },
}


def bone_frames(source_bind: np.ndarray, parents: dict[int, int | None],
                names: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Global bind origin, unit direction and length for every joint."""
    children: dict[int, list[int]] = {}
    for slot, parent in parents.items():
        if parent is not None:
            children.setdefault(parent, []).append(slot)
    origins = source_bind[:, :3, 3].copy()
    axes = np.zeros((len(source_bind), 3), dtype=np.float64)
    lengths = np.full(len(source_bind), .1, dtype=np.float64)
    for slot in range(len(source_bind)):
        axis = source_bind[slot][:3, :3] @ bone_axis(
            slot, source_bind, parents, names, children)
        axes[slot] = axis / max(float(np.linalg.norm(axis)), 1e-9)
        preferred = CHAIN_CHILD.get(names[slot])
        target = None
        for child in children.get(slot, []):
            if preferred is None or names[child] == preferred:
                target = source_bind[child][:3, 3]
                break
        if target is None and children.get(slot):
            target = source_bind[children[slot][0]][:3, 3]
        if target is not None:
            lengths[slot] = max(float(np.linalg.norm(target - origins[slot])), 1e-3)
    return origins, axes, lengths


def base_body_shape(positions: np.ndarray, normals: np.ndarray,
                    joints: np.ndarray, weights: np.ndarray,
                    source_bind: np.ndarray, parents: dict[int, int | None],
                    names: list[str], preset: dict):
    """Re-proportion the source body radially, in its own bind space.

    Built as linear blend skinning over per-joint transforms of exactly the
    form `shape_matrices` uses -- scale across the bone, never along it -- so
    normals come from the inverse transpose and the authored smoothing seams
    survive.  An empty preset is the exact identity.
    """
    taper = preset.get("taper", {})
    zones = preset.get("zones", ())
    if not taper and not zones:
        return positions, normals
    origins, axes, lengths = bone_frames(source_bind, parents, names)
    root = np.array([taper.get(joint_group(name), (1., 1.))[0] for name in names])
    tip = np.array([taper.get(joint_group(name), (1., 1.))[1] for name in names])

    points = positions.astype(np.float64)
    weight = weights.astype(np.float64)
    total = weight.sum(axis=1, keepdims=True)
    weight = np.divide(weight, total, out=np.zeros_like(weight), where=total > 1e-8)
    slots = joints.astype(np.int64)

    by_name = {name: index for index, name in enumerate(names)}
    zone_scale = np.ones(len(points))
    for anchor, offset, radii, scale in zones:
        slot = by_name.get(anchor)
        if slot is None:
            continue
        centre = origins[slot] + np.asarray(offset, dtype=float)
        falloff = np.clip(1. - (((points - centre)
                                 / np.asarray(radii, dtype=float)) ** 2).sum(axis=1),
                          0., 1.)
        zone_scale = zone_scale * (1. + (scale - 1.) * falloff)

    identity = np.eye(3, dtype=np.float64)
    linear = np.zeros((len(points), 3, 3), dtype=np.float64)
    translation = np.zeros((len(points), 3), dtype=np.float64)
    for influence_index in range(slots.shape[1]):
        slot = slots[:, influence_index]
        share = weight[:, influence_index]
        if not share.any():
            continue
        origin = origins[slot]
        axis = axes[slot]
        delta = points - origin
        along = np.einsum("ni,ni->n", delta, axis)
        position = np.clip(along / lengths[slot], 0., 1.)
        scale = (root[slot] + (tip[slot] - root[slot]) * position) * zone_scale
        across = identity[None] - np.einsum("ni,nj->nij", axis, axis)
        matrix = identity[None] + (scale - 1.)[:, None, None] * across
        linear += share[:, None, None] * matrix
        translation += share[:, None] * (
            origin - np.einsum("nij,nj->ni", matrix, origin))

    moved = np.einsum("nij,nj->ni", linear, points) + translation
    cofactor = np.linalg.inv(linear).transpose(0, 2, 1)
    turned = np.einsum("nij,nj->ni", cofactor, normals.astype(np.float64))
    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-9)
    return moved.astype(np.float32), turned.astype(np.float32)


def apply_shape(positions: np.ndarray, normals: np.ndarray, joints: np.ndarray,
                weights: np.ndarray, transforms: np.ndarray):
    """Linear blend skinning of the source mesh into the retargeted rest pose."""
    weight = weights.astype(np.float64)
    total = weight.sum(axis=1, keepdims=True)
    weight = np.divide(weight, total, out=np.zeros_like(weight), where=total > 1e-8)
    blended = np.einsum("nk,nkij->nij", weight, transforms[joints.astype(np.int64)])
    unweighted = total[:, 0] <= 1e-8
    if unweighted.any():
        blended[unweighted] = np.eye(4, dtype=np.float64)
    linear = blended[:, :3, :3]
    moved = np.einsum("nij,nj->ni", linear, positions.astype(np.float64)) + blended[:, :3, 3]
    # Normals need the inverse transpose because girth scaling is not uniform.
    cofactor = np.linalg.inv(linear).transpose(0, 2, 1)
    turned = np.einsum("nij,nj->ni", cofactor, normals.astype(np.float64))
    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-9)
    return moved.astype(np.float32), turned.astype(np.float32)


def matrix_quaternion(matrix: np.ndarray) -> list[float]:
    """glTF (x, y, z, w) quaternion from a rotation matrix."""
    trace = matrix[0, 0] + matrix[1, 1] + matrix[2, 2]
    if trace > 0.:
        scale = math.sqrt(trace + 1.) * 2.
        w = .25 * scale
        x = (matrix[2, 1] - matrix[1, 2]) / scale
        y = (matrix[0, 2] - matrix[2, 0]) / scale
        z = (matrix[1, 0] - matrix[0, 1]) / scale
    else:
        axis = int(np.argmax((matrix[0, 0], matrix[1, 1], matrix[2, 2])))
        i, j, k = axis, (axis + 1) % 3, (axis + 2) % 3
        scale = math.sqrt(1. + matrix[i, i] - matrix[j, j] - matrix[k, k]) * 2.
        values = [0., 0., 0.]
        values[i] = .25 * scale
        values[j] = (matrix[j, i] + matrix[i, j]) / scale
        values[k] = (matrix[k, i] + matrix[i, k]) / scale
        x, y, z = values
        w = (matrix[k, j] - matrix[j, k]) / scale
    length = math.sqrt(x * x + y * y + z * z + w * w) or 1.
    return [float(x / length), float(y / length), float(z / length), float(w / length)]


def write_rest_pose(nodes: list[dict], skin_joints: list[int], target_bind: np.ndarray,
                    parents: dict[int, int | None]) -> np.ndarray:
    """Store the retargeted rest pose on the joint nodes; return inverse binds.

    The rest transforms stay rigid, so the animation library's rotation tracks
    keep their meaning and only the proportions they act on have changed.
    """
    for slot, node_index in enumerate(skin_joints):
        parent = parents[slot]
        if parent is None:
            continue
        local = np.linalg.inv(target_bind[parent]) @ target_bind[slot]
        node = nodes[node_index]
        node.pop("matrix", None)
        node.pop("scale", None)
        node["translation"] = [float(value) for value in local[:3, 3]]
        node["rotation"] = matrix_quaternion(local[:3, :3])
    inverse = np.linalg.inv(target_bind)
    return inverse.transpose(0, 2, 1).reshape(-1, 16).astype("float32")


def skinned_subset(positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray,
                   joints: np.ndarray, weights: np.ndarray, faces: np.ndarray,
                   face_mask: np.ndarray, offset: float):
    selected = faces[face_mask]
    if not len(selected):
        empty = np.empty((0, 3), dtype=np.float32)
        return (empty, empty.copy(), np.empty((0, 2), dtype=np.float32),
                np.empty(0, dtype=np.uint32), np.empty((0, 4), dtype=np.uint16),
                np.empty((0, 4), dtype=np.float32))
    unique, remapped = np.unique(selected.reshape(-1), return_inverse=True)
    garment_positions = positions[unique] + normals[unique] * offset
    return (garment_positions.astype(np.float32), normals[unique].astype(np.float32),
            uvs[unique].astype(np.float32), remapped.astype(np.uint32),
            joints[unique].astype(np.uint16), weights[unique].astype(np.float32))


def influence(weights: np.ndarray, joints: np.ndarray, selected_joints: set[int]) -> np.ndarray:
    return np.where(np.isin(joints, list(selected_joints)), weights, 0.).sum(axis=1)


def player_accessory(feature: str, joint_by_name: dict[str, int],
                     bind: dict[str, np.ndarray], color: tuple[int, int, int],
                     accent: tuple[int, int, int]):
    """Integrated race anatomy, authored against the reference bind pose.

    These are not props hung off a human.  Each form is placed from the rig's
    own joint positions and skinned to the joints it grows from, then pushed
    through the same retarget as the body, so it lands on the race's own
    skeleton rather than on the reference one it was measured against.
    """
    mesh = ShapeMesh()
    mesh.uv_tile = FEATURE_UV_TILE
    head = joint_by_name["Head"]
    pelvis = joint_by_name["pelvis"]
    spine = joint_by_name["spine_03"]
    lower_spine = joint_by_name["spine_01"]
    neck = joint_by_name["neck_01"]
    clavicles = {-1.: joint_by_name["clavicle_l"],
                  1.: joint_by_name["clavicle_r"]}
    upperarms = {-1.: joint_by_name["upperarm_l"],
                  1.: joint_by_name["upperarm_r"]}
    forearms = {-1.: joint_by_name["lowerarm_l"],
                 1.: joint_by_name["lowerarm_r"]}


    def deltoid_blend(clavicle: int, upperarm: int, root, axis, length):
        """Share a shoulder plate between the clavicle and the upper arm.

        A pauldron bound rigidly to the clavicle stays with the shoulder while
        the body surface under it is driven by the upper arm, so the further
        down the deltoid a plate sits, the further it slides off the arm as
        that arm swings.  Sampling real clips put the worst of them nearly
        half a metre clear of the body during a run.
        """
        root = np.asarray(root, dtype=float)
        axis = np.asarray(axis, dtype=float)

        def blend(position):
            along = float(np.dot(np.asarray(position, dtype=float) - root, axis))
            share = min(1., max(0., along / max(length, 1e-6) + .18))
            return [(clavicle, 1. - share), (upperarm, share)]

        return blend
    thighs = {-1.: joint_by_name["thigh_l"], 1.: joint_by_name["thigh_r"]}
    if feature == "horns":
        # Curved, ringed horns growing out of the temples.
        #
        # They used to start at |x| 0.070 with a 0.060 radius, which spans
        # 0.010..0.130 across a skull whose half width is 0.0906: the root ring
        # straddled the surface, and because `tapered_curve` has no end caps
        # the open mouth of the tube sat visible on the head.  The root is now
        # buried inside the skull and the form is swept with closed ends, so
        # what leaves the scalp is a solid horn rather than a pipe.
        #
        # (x, y, z, half width, half height).  The first station is inside the
        # skull; the second is the flare where the horn breaks the skin.
        HORN = ((.024, 1.674, -.004, .042, .040),
                (.058, 1.697, -.012, .062, .058),
                (.100, 1.722, -.034, .052, .049),
                (.140, 1.749, -.064, .046, .043),
                (.176, 1.783, -.109, .039, .036),
                (.196, 1.818, -.156, .030, .028),
                (.194, 1.846, -.194, .022, .021),
                (.182, 1.868, -.218, .015, .014),
                (.152, 1.880, -.231, .008, .008),
                (.122, 1.883, -.235, .004, .004))
        for side in (-1., 1.):
            mesh.swept([(side * x, y, z) for x, y, z, _w, _h in HORN],
                       [w for *_rest, w, _h in HORN],
                       [h for *_rest, _w, h in HORN],
                       head, 0, 16)
            # A low collar of raised scalp around the emergence, so the horn
            # reads as growing out of the head rather than pushed into it.
            mesh.swept([(side * .046, 1.690, -.008), (side * .066, 1.702, -.017)],
                       [.070, .058], [.066, .055], head, 0, 14,
                       cap_start=False, cap_end=False)
            # Growth rings, following the new path rather than the old one.
            for x, y, z, radius in ((.078, 1.708, -.021, .054),
                                    (.118, 1.734, -.046, .049),
                                    (.158, 1.764, -.084, .042),
                                    (.188, 1.800, -.132, .033),
                                    (.196, 1.832, -.175, .025)):
                mesh.sphere((side * x, y, z), (radius, .024, radius),
                            head, 1, 3, 10)
    elif feature == "crystal":
        # Glasswardens are human scholars and field engineers in the concept
        # sheets: a brass-and-glass lens rig, worn rather than hovering.
        #
        # The temple arms used to run at |x| 0.150-0.162 across a skull whose
        # half width is 0.0906, so they stood six centimetres clear of the head
        # and read as antennae; the lenses sat as far as 0.050 in front of a
        # face whose front is at z 0.0945.  Everything now follows the skull:
        # the brow bar ends at the temple, the arms lie along the side of the
        # head, and each one finishes with a hook behind the ear, whose widest
        # point the body mesh puts at (0.0906, 1.704, -0.028).
        mesh.swept([(-.090, 1.703, .052), (-.060, 1.712, .092),
                    (0., 1.716, .104), (.060, 1.712, .092),
                    (.090, 1.703, .052)],
                   [.011, .010, .009, .010, .011],
                   [.009, .009, .008, .009, .009], head, 0, 12)
        for side in (-1., 1.):
            x = side * .046
            # Lens barrel and ground glass, pulled back onto the face.
            mesh.swept([(x, 1.706, .088), (x, 1.706, .112)],
                       [.040, .042], [.038, .040], head, 0, 16,
                       cap_start=False, cap_end=False)
            mesh.sphere((x, 1.706, .114), (.068, .062, .016), head, 1, 6, 16)
            # Bridge between the two barrels.
            mesh.swept([(-.014, 1.706, .100), (.014, 1.706, .100)],
                       [.007, .007], [.006, .006], head, 0, 10)
            # Temple arm: off the frame, along the side of the head, and hooked
            # down behind the ear.
            mesh.swept([(side * .076, 1.706, .086), (side * .088, 1.703, .040),
                        (side * .091, 1.698, -.004), (side * .088, 1.688, -.030),
                        (side * .080, 1.674, -.041)],
                       [.008, .008, .008, .007, .006],
                       [.011, .011, .010, .009, .007], head, 0, 10)
    elif feature == "scaled":
        # Ssarathi anatomy.  The skull is one continuous form: a swept upper
        # muzzle and a separate lower jaw that meet at a mouth line, rather
        # than three overlapping ellipsoids whose intersections showed as
        # seams and whose silhouette read as a sock pulled over a human face.
        # Gold stays reserved for nostril, tooth and scute accents.
        mesh.swept([(0., 1.664, -.020), (0., 1.656, .052), (0., 1.644, .120),
                    (0., 1.632, .180), (0., 1.626, .228), (0., 1.624, .258)],
                   [.108, .104, .095, .080, .058, .022],
                   [.086, .079, .068, .056, .042, .018],
                   head, 0, 16)
        # Lower jaw: shallower and set back, so the mouth line is a real edge.
        mesh.swept([(0., 1.598, -.010), (0., 1.594, .060), (0., 1.590, .130),
                    (0., 1.590, .190), (0., 1.594, .232)],
                   [.094, .090, .081, .066, .042],
                   [.040, .038, .034, .028, .018],
                   head, 0, 14)
        # Brow ridges laid along the skull instead of standing off it as fins.
        for side in (-1., 1.):
            mesh.swept([(side * .028, 1.700, .086), (side * .068, 1.708, .068),
                        (side * .104, 1.702, .038), (side * .126, 1.688, .002)],
                       [.022, .024, .019, .010],
                       [.014, .016, .013, .007],
                       head, 0, 10)
            # Nostril, set into the top of the snout near the tip.
            mesh.cone((side * .030, 1.638, .238), (side * .030, 1.642, .250),
                      .008, head, 1, 8)
            # Cheek scutes: low, wide plates rather than beads.
            for y, z, length in ((1.688, .120, .030), (1.660, .158, .024)):
                mesh.swept([(side * .070, y, z), (side * .098, y - .006, z + .014)],
                           [length * .55, length * .34],
                           [length * .30, length * .20], head, 1, 8)
            # A short row of teeth along the jaw line reads the mouth at
            # gameplay distance, which a smooth seam never did.
            for step in range(3):
                z = .108 + step * .046
                mesh.claw((side * (.082 - step * .012), 1.606, z),
                          (side * .12, -1., .10), .020, .0075, head, 1,
                          curl=.10, sides=6, stations=3, flatten=.70)
        # Dorsal crest: one webbed, serrated ridge from the brow to mid-back.
        # It is authored as three chained segments only because each has to be
        # skinned to the joint it lies over; the stations are shared, so the
        # crest stays continuous across the joins.
        for joint, path, rises in (
                (head, ((0., 1.718, -.004), (0., 1.732, -.052),
                        (0., 1.728, -.104), (0., 1.712, -.148)),
                 (.030, .042, .040, .032)),
                (neck, ((0., 1.712, -.148), (0., 1.648, -.126),
                        (0., 1.578, -.112), (0., 1.516, -.104)),
                 (.032, .034, .030, .026)),
                (spine, ((0., 1.516, -.104), (0., 1.440, -.108),
                         (0., 1.372, -.116), (0., 1.312, -.126)),
                 (.026, .024, .021, .016))):
            mesh.ridge(path, rises, [.011, .010, .009, .008], joint, 0,
                       spikes=.22)
        # Tail: a laterally compressed chord off the sacrum, shared between
        # the pelvis and the lower spine so it tracks the hips through the
        # shared locomotion clips instead of swinging as one board.
        points, widths, heights = [], [], []
        for step in range(13):
            t = step / 12.
            points.append((0.,
                           .952 - .58 * t - .08 * math.sin(t * math.pi)
                           + .10 * max(0., t - .78),
                           -.100 - .86 * t))
            radius = .112 * (1. - t) ** 1.30 + .007
            # A real tail is taller than it is wide; a round tube read as rope.
            widths.append(radius * .80)
            heights.append(radius * 1.16)
        mesh.blend = lambda position: [
            (pelvis, 1.),
            (lower_spine, max(0., .42 * (1. + position[2] / .34)))]
        mesh.swept(points, widths, heights, pelvis, 0, 14, cap_start=False)
        # A scute ridge along the top of the tail reads the taper at a
        # distance and breaks the tube without adding separate blobs.
        ridge_points = [points[index] for index in range(1, 11)]
        mesh.ridge(ridge_points,
                   [.088 * (1. - index / 11.) ** 1.2 + .006 for index in range(1, 11)],
                   [.010 * (1. - index / 13.) + .004 for index in range(1, 11)],
                   pelvis, 1, spikes=.30)
        mesh.blend = None
        # Claws on every finger and both feet, placed and aimed from the rig.
        for side in ("l", "r"):
            for digit in ("index", "middle", "pinky", "ring", "thumb"):
                tip = bind.get(f"{digit}_04_leaf_{side}")
                knuckle = bind.get(f"{digit}_03_{side}")
                if tip is None or knuckle is None:
                    continue
                direction = tip - knuckle
                length = float(np.linalg.norm(direction))
                if length < 1e-5:
                    continue
                direction = direction / length
                mesh.claw(tuple(tip - direction * length * .34), direction,
                          length * 1.42, length * .30,
                          joint_by_name[f"{digit}_04_leaf_{side}"], 1,
                          curl=.40, sides=8, stations=5)
            toe = bind.get(f"ball_leaf_{side}")
            ball = bind.get(f"ball_{side}")
            if toe is None or ball is None:
                continue
            direction = toe - ball
            length = float(np.linalg.norm(direction))
            if length < 1e-5:
                continue
            direction = direction / length
            for offset in (-.032, .0, .032):
                root = toe + np.array([offset, 0., 0.]) - direction * length * .24
                mesh.claw(tuple(root), direction, length * 1.18, .020,
                          joint_by_name[f"ball_leaf_{side}"], 1,
                          curl=.30, sides=8, stations=5)
    elif feature == "stone":
        # Stoneborn plating is load-bearing anatomy, and it is all cut rather
        # than moulded.  The previous plating was spheres and tapered tubes,
        # which have no edge anywhere for a light to catch, so under the
        # client's lighting it read as inflated padding strapped to a person.
        # Everything here is a flat-shaded slab instead: hard rims, angled
        # faces, and plates that step and overlap like riven rock.
        def limb_frame(root, tip):
            """Bone axis plus two perpendiculars, for seating plates on limbs."""
            axis = np.asarray(tip, dtype=float) - np.asarray(root, dtype=float)
            length = float(np.linalg.norm(axis))
            if length < 1e-6:
                return None
            axis = axis / length
            reference = (np.array((0., 0., 1.)) if abs(axis[2]) < .85
                         else np.array((1., 0., 0.)))
            right = np.cross(axis, reference)
            right = right / max(np.linalg.norm(right), 1e-9)
            up = np.cross(right, axis)
            return axis, right, up / max(np.linalg.norm(up), 1e-9), length

        # Sternum: a stepped column of slabs down the chest, each one tilted a
        # little further off vertical so the stack catches light in bands.
        for y, z, width, height, thick, tilt, joint in (
                (1.404, .092, .300, .118, .044, .16, spine),
                (1.312, .104, .330, .116, .048, .06, spine),
                (1.222, .098, .296, .110, .044, -.06, lower_spine),
                (1.140, .082, .244, .100, .038, -.14, lower_spine)):
            mesh.plate((0., y, z), (0., tilt, 1.), (1., 0., 0.),
                       width, height, thick, joint, 0, taper=.80)
        # Collar slabs flanking the throat.
        for side in (-1., 1.):
            mesh.plate((side * .126, 1.472, .052), (side * .42, .58, .70),
                       (1., 0., .0), .150, .088, .038, spine, 0, taper=.74)

        for side in (-1., 1.):
            shoulder = bind.get("clavicle_r" if side > 0 else "clavicle_l")
            arm = bind.get("upperarm_r" if side > 0 else "upperarm_l")
            elbow = bind.get("lowerarm_r" if side > 0 else "lowerarm_l")
            hand = bind.get("hand_r" if side > 0 else "hand_l")
            if shoulder is None or arm is None or elbow is None:
                continue
            frame = limb_frame(arm, elbow)
            if frame is None:
                continue
            axis, right, up, arm_length = frame
            # Pauldron: three rows of three plates wrapping the deltoid, each
            # row smaller and set further down the arm.  Overlapping slabs are
            # what make plating read as plating instead of a sleeve.
            for row, (along, width, height, thick, lift) in enumerate((
                    (-.07, .132, .096, .036, .062),
                    (.13, .112, .080, .029, .057),
                    (.33, .090, .066, .024, .050))):
                centre_base = arm + axis * (arm_length * along)
                # Each row is rotated off the last so the three bands do not
                # line up into one rectangular sleeve around the arm.
                for angle in (-58., 0., 58.):
                    radians = math.radians(angle + row * 19. - 10.)
                    outward = right * math.cos(radians) + up * math.sin(radians)
                    centre = centre_base + outward * lift
                    mesh.blend = deltoid_blend(clavicles[side], upperarms[side],
                                               arm, axis, arm_length)
                    mesh.plate(tuple(centre), tuple(outward), tuple(axis),
                               width, height, thick, clavicles[side], 0,
                               taper=.74, shear=.004)
                    mesh.blend = None
            # Forearm bracer: four plates banded around the lower arm.
            if hand is not None:
                lower = limb_frame(elbow, hand)
                if lower is not None:
                    laxis, lright, lup, lower_length = lower
                    for along in (.28, .54):
                        centre_base = elbow + laxis * (lower_length * along)
                        for index in range(5):
                            radians = math.radians(index * 72. + 36.)
                            outward = lright * math.cos(radians) + lup * math.sin(radians)
                            mesh.plate(tuple(centre_base + outward * .046),
                                       tuple(outward), tuple(laxis),
                                       .086, .058, .020, forearms[side], 0,
                                       taper=.76)
                    # A crystal seam let into the gap between the bands.
                    mesh.swept([tuple(elbow + laxis * (lower_length * .38) + lup * .066),
                                tuple(elbow + laxis * (lower_length * .44) + lup * .068)],
                               [.010, .009], [.006, .005], forearms[side], 1, 6)
            thigh = bind.get("thigh_r" if side > 0 else "thigh_l")
            knee = bind.get("calf_r" if side > 0 else "calf_l")
            if thigh is not None and knee is not None:
                leg = limb_frame(thigh, knee)
                if leg is not None:
                    taxis, tright, tup, thigh_length = leg
                    for along, width, height in ((.22, .134, .104),
                                                 (.46, .120, .094)):
                        centre = thigh + taxis * (thigh_length * along)
                        for angle in (-38., 38.):
                            radians = math.radians(angle)
                            outward = tright * math.cos(radians) + tup * math.sin(radians)
                            mesh.plate(tuple(centre + outward * .064),
                                       tuple(outward), tuple(taxis),
                                       width, height, .030, thighs[side], 0,
                                       taper=.78)
            # Brow and jaw slabs, angular so the face reads as carved.  They
            # sit above the eye line: dropped to the brow itself they closed
            # over the eyes and the head read as a helmet with a vision slot.
            mesh.plate((side * .098, 1.694, .058), (side * .40, .40, .82),
                       (1., .12, 0.), .096, .050, .026, head, 0, taper=.70)
            mesh.plate((side * .086, 1.592, .092), (side * .36, -.42, .83),
                       (1., .18, 0.), .086, .058, .026, head, 0, taper=.68)
        # Brow band across the forehead, clear of the eye line.
        mesh.plate((0., 1.734, .074), (0., .58, .82), (1., 0., 0.),
                   .196, .046, .030, head, 0, taper=.72)
        # Crystal seams: thin lit veins let into the sternum and the nape.
        mesh.swept([(-.034, 1.404, .108), (.012, 1.348, .116),
                    (-.020, 1.292, .102), (.024, 1.238, .088)],
                   [.009, .008, .007, .005], [.007, .006, .005, .004],
                   spine, 1, 8)
        mesh.swept([(0., 1.566, -.070), (0., 1.514, -.086)],
                   [.011, .008], [.008, .006], neck, 1, 8)
        for side in (-1., 1.):
            mesh.swept([(side * .092, 1.430, .092), (side * .126, 1.372, .080)],
                       [.008, .006], [.006, .005], spine, 1, 6)
    elif feature == "fungal":
        # Mycelari carry a true parasol.  The cap used to be a surface of
        # revolution, which is precisely what makes a mushroom read as an
        # umbrella: a real cap is irregular in outline, uneven in thickness
        # and droops unevenly at the margin.  The outline, the rise and the
        # margin droop here all vary with angle, from a fixed trigonometric
        # profile so the shape is authored rather than random.
        around = 26

        def margin(angle):
            """Radial multiplier: a lobed, uneven cap edge."""
            return (1. + .112 * math.sin(3. * angle + .70)
                    + .064 * math.sin(5. * angle + 2.15)
                    + .038 * math.sin(8. * angle + 4.30))

        def droop(angle):
            """Vertical offset at the margin, so the rim is not a flat ring."""
            return (.020 * math.sin(2. * angle + 1.05)
                    + .012 * math.sin(7. * angle + .35))

        # (height, radius, how much of the margin variation applies here)
        top_profile = ((1.918, .034, .10), (1.904, .124, .34), (1.882, .206, .62),
                       (1.852, .268, .84), (1.820, .304, .96), (1.792, .318, 1.00))
        under_profile = ((1.792, .318, 1.00), (1.782, .276, .92), (1.790, .208, .70),
                         (1.802, .140, .44), (1.812, .076, .18))

        def cap_rings(profile):
            rings = []
            for height, radius, blend in profile:
                ring = []
                for index in range(around):
                    angle = 2. * math.pi * index / around
                    scale = 1. + (margin(angle) - 1.) * blend
                    ring.append((math.cos(angle) * radius * scale,
                                 height + droop(angle) * blend,
                                 math.sin(angle) * radius * scale))
                rings.append(ring)
            return rings

        mesh.lofted(cap_rings(top_profile), head, 0)
        # The underside carries the gill material, so the lamellae are read
        # from the map rather than cut into the silhouette as flat prisms.
        mesh.lofted(cap_rings(under_profile), head, 1, flip=True)
        # A dozen shallow lamellae inset from the rim give the underside real
        # parallax without serrating the cap outline the way the old eighteen
        # full-depth blades did.
        for index in range(12):
            angle = 2. * math.pi * index / 12. + .13
            cos, sin = math.cos(angle), math.sin(angle)
            scale = margin(angle)
            inner, outer = .120, .262 * scale
            mesh.plate((cos * (inner + outer) * .5, 1.791,
                        sin * (inner + outer) * .5),
                       (0., -1., 0.), (cos, 0., sin),
                       outer - inner, .012, .020, head, 1, taper=.55)
        # Stipe: the neck of the mushroom, thickening into the cap.
        mesh.swept([(0., 1.664, -.012), (0., 1.712, -.014), (0., 1.758, -.016),
                    (0., 1.804, -.014)],
                   [.070, .062, .056, .062], [.068, .060, .054, .060],
                   head, 0, 14, cap_start=False, cap_end=False)
        # Annulus: the torn collar where the veil broke off the stipe.
        annulus = []
        for height, radius, flare in ((1.804, .074, .0), (1.796, .122, 1.),
                                      (1.784, .112, 1.), (1.776, .076, .0)):
            ring = []
            for index in range(18):
                angle = 2. * math.pi * index / 18.
                scale = 1. + (.16 * math.sin(4. * angle + .8)
                              + .09 * math.sin(7. * angle)) * flare
                ring.append((math.cos(angle) * radius * scale, height,
                             math.sin(angle) * radius * scale))
            annulus.append(ring)
        mesh.lofted(annulus, head, 1)
        # Shoulder brackets: layered shelf fungi.  Plates rather than squashed
        # spheres, so each shelf has a real edge where it leaves the body.
        # Shelf fungi grow on the deltoid, not at the collar.  Measuring
        # `along` from the clavicle put every shelf beside the neck, where the
        # shirt covered them and they read as damage rather than anatomy.
        for side in (-1., 1.):
            arm = bind.get("upperarm_r" if side > 0 else "upperarm_l")
            elbow = bind.get("lowerarm_r" if side > 0 else "lowerarm_l")
            if arm is None or elbow is None:
                continue
            direction = elbow - arm
            length = float(np.linalg.norm(direction))
            if length < 1e-6:
                continue
            direction = direction / length
            for along, lift, width, depth, thick, out in (
                    (-.02, .050, .196, .150, .040, .054),
                    (.22, .026, .166, .126, .034, .050),
                    (.46, .004, .124, .096, .028, .044)):
                centre = (arm + direction * (length * along)
                          + np.array([0., lift, -.014]))
                centre = centre + np.array([side * out, 0., 0.])
                # The shelf leaves the arm nearly level and tips down at the
                # rim, which is how a bracket fungus actually sits.
                mesh.blend = deltoid_blend(clavicles[side], upperarms[side],
                                           arm, direction, length)
                mesh.plate(tuple(centre), (side * .34, 1., -.18),
                           (side * 1., -.22, .0), width, depth, thick,
                           clavicles[side], 0, taper=.62)
                mesh.plate(tuple(centre + np.array([0., -thick * .78, 0.])),
                           (side * .34, -1., .18), (side * 1., -.22, .0),
                           width * .86, depth * .86, thick * .5,
                           clavicles[side], 1, taper=.58)
                mesh.blend = None
        # Mycelial threads down the sternum.
        mesh.swept([(0., 1.430, .100), (-.030, 1.372, .104),
                    (.026, 1.312, .096), (-.014, 1.256, .084)],
                   [.009, .008, .007, .005], [.007, .006, .005, .004],
                   spine, 1, 8)
    return mesh.arrays()


def build_player(source_dir: Path, output: Path, race: str, gender: str) -> dict:
    config = RACES[race]
    source = source_dir / f"Superhero_{gender.title()}_FullBody.gltf"
    document = json.loads(source.read_text(encoding="utf-8"))
    binary = (source.parent / document["buffers"][0]["uri"]).read_bytes()
    glb = GLB()
    glb.doc["nodes"] = copy.deepcopy(document["nodes"])
    glb.doc["scenes"] = copy.deepcopy(document["scenes"])
    glb.doc["scene"] = document.get("scene", 0)
    for node in glb.doc["nodes"]:
        node.pop("mesh", None); node.pop("skin", None)
    skin = document["skins"][0]
    joint_by_name = {document["nodes"][node].get("name", ""): index
                     for index, node in enumerate(skin["joints"])}
    joint_names = [document["nodes"][node].get("name", "") for node in skin["joints"]]
    anatomy = ANATOMY.get(race, {})
    base_body = BASE_BODIES.get(config.get("base", "heroic"), {})
    source_bind = np.stack([global_node_matrix(document, node) for node in skin["joints"]])
    parents = joint_parents(document, skin)
    # The cape chains join the rig here, before anything measures, solves or
    # retargets it, so they are ordinary joints to every step that follows.
    joint_nodes, source_bind, parents, joint_names = append_cape_bones(
        glb.doc["nodes"], list(skin["joints"]), source_bind, parents, joint_names)
    joint_by_name = {name: slot for slot, name in enumerate(joint_names)}
    leg_scale = solve_leg_scale(source_bind, parents, joint_names, anatomy)
    target_bind = retarget_bind(source_bind, parents, joint_names, anatomy, leg_scale)
    transforms = shape_matrices(source_bind, target_bind, parents, joint_names, anatomy)
    inverse = write_rest_pose(glb.doc["nodes"], joint_nodes, target_bind, parents)
    inverse_accessor = glb.accessor(inverse, "MAT4")
    glb.doc["skins"] = [{"name": "Armature", "joints": joint_nodes,
                         "inverseBindMatrices": inverse_accessor,
                         "skeleton": joint_nodes[0]}]
    base_uri = document["images"][document["textures"][
        document["materials"][2]["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]["uri"]
    if config.get("preserve_body"):
        body_texture = resized_texture(source.parent / base_uri)
    else:
        body_texture = recolored_texture(
            source.parent / base_uri, config["color"], config["accent"],
            config.get("body_pattern", config["feature"]))
    hair_base = source_texture(document, source.parent, 0, "baseColorTexture")
    eye_base = source_texture(document, source.parent, 1, "baseColorTexture")
    face = RACE_FACE.get(race, {})

    def face_texture(material_index: int) -> Path:
        return source.parent / document["images"][document["textures"][
            document["materials"][material_index]["pbrMetallicRoughness"][
                "baseColorTexture"]["index"]]["source"]]["uri"]

    # Race features get the same class of material as the body: a relief
    # derived albedo, normal and metallic-roughness map instead of a bare
    # colour factor.  With a map supplied the metallic and roughness factors
    # go to 1.0 so the texture governs outright; glTF multiplies the two.
    feature_surface, accent_surface = FEATURE_MATERIALS.get(
        config["feature"], (None, None))
    feature_maps = (feature_surface_textures(feature_surface)
                    if feature_surface else (None, None, None))
    accent_maps = (feature_surface_textures(accent_surface)
                   if accent_surface else (None, None, None))
    materials = {
        "eyebrows": glb.material(
            config["label"] + " Eyebrows", face.get("brow", (255, 255, 255)),
            roughness=.82,
            texture_png=neutral_texture(face_texture(0)) if hair_base else None,
            normal_png=source_texture(document, source.parent, 0, "normalTexture"),
            double_sided=True),
        "eyes": glb.material(
            config["label"] + " Eyes", (255, 255, 255), roughness=.30,
            texture_png=race_eye_texture(
                face_texture(1), face.get("pupil", "round"),
                face.get("iris", DEFAULT_IRIS)) if eye_base else None,
            normal_png=source_texture(document, source.parent, 1, "normalTexture"),
            emissive=tuple(c // 16 for c in config["accent"]), double_sided=True),
        "body": glb.material(
            config["label"] + " Body", (255, 255, 255), roughness=.78,
            texture_png=body_texture,
            normal_png=source_texture(document, source.parent, 2, "normalTexture"),
            metallic_roughness_png=source_texture(
                document, source.parent, 2, "metallicRoughnessTexture"),
            double_sided=True),
        "feature": glb.material(
            config["label"] + " Integrated Feature",
            config.get("feature_color", config["color"]),
            metallic=1. if feature_surface else .04,
            roughness=1. if feature_surface else .72,
            texture_png=feature_maps[0], normal_png=feature_maps[1],
            metallic_roughness_png=feature_maps[2]),
        "accent": glb.material(
            config["label"] + " Integrated Accent", config["accent"],
            metallic=1. if accent_surface else .12,
            roughness=1. if accent_surface else .46,
            texture_png=accent_maps[0], normal_png=accent_maps[1],
            metallic_roughness_png=accent_maps[2],
            emissive=tuple(c // 28 for c in config["accent"])),
    }
    shirt, pants, boots, trim = config["wardrobe"]
    cloth_normal, cloth_mr = surface_detail_maps("cloth")
    leather_normal, leather_mr = surface_detail_maps("leather")
    trim_normal, trim_mr = surface_detail_maps("trim")
    materials.update({
        "shirt": glb.material(config["label"] + " Shirt", shirt, roughness=1.,
                              texture_png=surface_detail_texture("cloth"),
                              normal_png=cloth_normal,
                              metallic_roughness_png=cloth_mr),
        "shirt_trim": glb.material(config["label"] + " Shirt Trim", trim,
                                   metallic=.22, roughness=1.,
                                   texture_png=surface_detail_texture("trim"),
                                   normal_png=trim_normal,
                                   metallic_roughness_png=trim_mr),
        "pants": glb.material(config["label"] + " Pants", pants, roughness=1.,
                              texture_png=surface_detail_texture("cloth"),
                              normal_png=cloth_normal,
                              metallic_roughness_png=cloth_mr),
        "pants_trim": glb.material(config["label"] + " Pants Seam",
                                   tuple(round(c * .68) for c in pants),
                                   metallic=.12, roughness=1.,
                                   texture_png=surface_detail_texture("trim"),
                                   normal_png=trim_normal,
                                   metallic_roughness_png=trim_mr),
        "boots": glb.material(config["label"] + " Boots", boots, roughness=1.,
                              texture_png=surface_detail_texture("leather"),
                              normal_png=leather_normal,
                              metallic_roughness_png=leather_mr),
        "boots_trim": glb.material(config["label"] + " Boots Seam",
                                   tuple(round(c * .68) for c in boots),
                                   metallic=.18, roughness=1.,
                                   texture_png=surface_detail_texture("trim"),
                                   normal_png=trim_normal,
                                   metallic_roughness_png=trim_mr),
        "headwear": glb.material(config["label"] + " Headwear", shirt, roughness=1.,
                                 texture_png=surface_detail_texture("cloth"),
                                 normal_png=cloth_normal,
                                 metallic_roughness_png=cloth_mr),
        "headwear_trim": glb.material(config["label"] + " Headwear Trim", trim,
                                      metallic=.20, roughness=1.,
                                      texture_png=surface_detail_texture("trim"),
                                      normal_png=trim_normal,
                                      metallic_roughness_png=trim_mr),
    })
    vertices = triangles = 0
    body_arrays = None
    for mesh_index, node_index in enumerate((65, 66, 67)):
        source_primitive = document["meshes"][mesh_index]["primitives"][0]
        attrs = source_primitive["attributes"]
        source_positions = read_accessor(document, binary, attrs["POSITION"])
        source_normals = read_accessor(document, binary, attrs["NORMAL"])
        uvs = read_accessor(document, binary, attrs["TEXCOORD_0"]).astype("float32")
        joints = read_accessor(document, binary, attrs["JOINTS_0"]).astype("uint16")
        weights = read_accessor(document, binary, attrs["WEIGHTS_0"]).astype("float32")
        # The base body re-proportions the shared mesh before the race
        # retarget touches it.  `source_positions` is deliberately kept for
        # the garment masks below: cuts are chosen on the untouched source so
        # a hem cannot wander when a culture changes physique.
        base_positions, base_normals = base_body_shape(
            source_positions, source_normals, joints, weights,
            source_bind, parents, joint_names, base_body)
        positions, normals = apply_shape(base_positions, base_normals,
                                         joints, weights, transforms)
        indices = read_accessor(document, binary, source_primitive["indices"]).astype("uint32")
        material = (materials["eyebrows"], materials["eyes"], materials["body"])[mesh_index]
        primitive = glb.primitive(positions, normals, uvs, indices, material,
                                  joints=joints, weights=weights)
        canonical_name = ("Eyebrows", "Eyes", "Body")[mesh_index]
        glb.doc["meshes"].append({"name": canonical_name,
                                  "primitives": [primitive]})
        glb.doc["nodes"][node_index]["name"] = canonical_name
        glb.doc["nodes"][node_index]["mesh"] = len(glb.doc["meshes"]) - 1
        glb.doc["nodes"][node_index]["skin"] = 0
        vertices += len(positions)
        triangles += len(indices) // 3
        if mesh_index == 2:
            body_arrays = (positions, normals, uvs, joints, weights,
                           indices.reshape(-1, 3), source_positions)

    # Default clothing is copied from the original body surface, offset by only
    # millimetres and retaining the exact skin weights. It therefore follows all
    # 65 joints instead of moving as one rigid chest/pelvis attachment.
    positions, normals, uvs, joints, weights, faces, source_body = body_arrays
    # Garment cuts are selected on the *source* body.  The thresholds below are
    # absolute heights on the reference skeleton, so reading them off a
    # retargeted body would move every hem as soon as a race changed
    # proportions -- a digitigrade Ssarathi would get boots at mid-shin and a
    # Stoneborn would get a shirt at the collarbone.  Faces are shared between
    # the two, so the mask stays valid for the deformed geometry.
    centers = source_body[faces].mean(axis=1)
    y = centers[:, 1]
    x = np.abs(centers[:, 0])
    z = centers[:, 2]
    by_name = lambda *names: {joint_by_name[name] for name in names}
    shirt_score = influence(weights, joints, by_name(
        "pelvis", "spine_01", "spine_02", "spine_03", "clavicle_l", "clavicle_r",
        "upperarm_l", "upperarm_r"))
    pants_score = influence(weights, joints, by_name(
        "pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r"))
    boots_score = influence(weights, joints, by_name(
        "calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r",
        "ball_leaf_l", "ball_leaf_r"))
    head_score = influence(weights, joints, by_name("Head"))
    shirt_mask = ((shirt_score[faces].mean(axis=1) > .30) & (y > .900) & (y < 1.550))
    pants_mask = ((pants_score[faces].mean(axis=1) > .30) & (y > .245) & (y < 1.120))
    boots_mask = ((boots_score[faces].mean(axis=1) > .24) & (y < .320))
    def garment_edge(mask, values, depth, upper=True):
        """Faces within `depth` of a garment's own extent along `values`.

        Measuring the band from the cut itself rather than from an absolute
        coordinate means one number describes the hem on both skeletons; the
        male and female arms differ by 50 mm at the shoulder alone.
        """
        if not mask.any():
            return np.zeros_like(mask)
        if upper:
            return mask & (values > float(values[mask].max()) - depth)
        return mask & (values < float(values[mask].min()) + depth)

    # Trim used to take the whole outer deltoid plus a slab of upper chest,
    # which read as a rectangle stencilled onto the shirt rather than as
    # tailoring -- the loudest thing on a Stoneborn or a Mycelari once the
    # materials underneath started behaving.  It is now the three edges a
    # shirt actually has: a cuff at the sleeve, a collar at the neck, and a
    # placket down the centre front.
    sleeve_cuff = garment_edge(shirt_mask, x, .055)
    collar = garment_edge(shirt_mask, y, .028)
    # The placket stops above the waistband: a shirt front that carried on
    # under the belt read as a stripe painted down the whole figure.
    placket = shirt_mask & (x < .016) & (z > .030) & (y > 1.130)
    shirt_trim = sleeve_cuff | collar | placket
    pants_trim = pants_mask & (y > 1.015) & (y < 1.110)
    boots_trim = boots_mask & (y > .270) & (y < .325)
    head_band = ((head_score[faces].mean(axis=1) > .45) &
                 (y > 1.655) & (y < 1.710) & (z < .075))
    head_cap = ((head_score[faces].mean(axis=1) > .45) &
                (y > 1.690) & (z < .050))

    def add_skinned(name: str, mask: np.ndarray, offset: float, material: int) -> None:
        nonlocal vertices, triangles
        arrays = skinned_subset(positions, normals, uvs, joints, weights, faces, mask, offset)
        if not len(arrays[0]):
            return
        primitive = glb.primitive(*arrays[:4], material, joints=arrays[4], weights=arrays[5])
        glb.mesh_node(name, [primitive], skin=0, parent=68)
        vertices += len(arrays[0])
        triangles += len(arrays[3]) // 3

    add_skinned("Wardrobe_Shirt", shirt_mask, .008, materials["shirt"])
    add_skinned("Wardrobe_Shirt_Trim", shirt_trim, .012, materials["shirt_trim"])
    add_skinned("Wardrobe_Pants", pants_mask, .009, materials["pants"])
    add_skinned("Wardrobe_Pants_Seam", pants_trim, .013, materials["pants_trim"])
    add_skinned("Wardrobe_Boots", boots_mask, .013, materials["boots"])
    add_skinned("Wardrobe_Boots_Seam", boots_trim, .017, materials["boots_trim"])
    # Optional creation headwear, skipped on races whose own head anatomy
    # occupies the same scalp the piece is cut from.
    headwear = face.get("headwear", ("band", "cap"))
    if "band" in headwear:
        add_skinned("Wardrobe_Head_Band", head_band, .012, materials["headwear_trim"])
    if "cap" in headwear:
        add_skinned("Wardrobe_Head_Cap", head_cap, .014, materials["headwear"])

    bind_positions = {name: source_bind[slot][:3, 3]
                      for slot, name in enumerate(joint_names)}
    accessory = player_accessory(config["feature"], joint_by_name, bind_positions,
                                 config["color"], config["accent"])
    if len(accessory[0]):
        primitives = []
        # ShapeMesh emits one consolidated primitive and material selectors as its seventh array.
        for material_index, arrays in enumerate(accessory[6]):
            if len(arrays[0]) == 0:
                continue
            feature_material = (materials["feature"], materials["accent"])[material_index]
            # Race features are authored against the reference skeleton and
            # then pushed through the same retarget as the body, so horns sit
            # on the retargeted skull and a tail leaves the retargeted pelvis
            # instead of floating where the reference joint used to be.
            shaped, shaped_normals = apply_shape(arrays[0], arrays[1], arrays[4],
                                                 arrays[5], transforms)
            primitives.append(glb.primitive(shaped, shaped_normals, arrays[2],
                                            arrays[3], feature_material,
                                            joints=arrays[4], weights=arrays[5]))
            vertices += len(arrays[0])
            triangles += len(arrays[3]) // 3
        glb.mesh_node("Integrated_%s_Feature" % config["label"].replace(" ", "_"),
                      primitives, skin=0, parent=68)
    glb.write(output)
    return {"vertices": vertices, "triangles": triangles,
            "joints": len(joint_nodes), "feature": config["feature"],
            "wardrobe": "skinned", "anatomy": "retargeted",
            "capeBones": len(cape_bone_names()),
            "baseBody": config.get("base", "heroic"),
            "stature": round(anatomy.get("stature", 1.), 4),
            "legChainScale": round(float(leg_scale), 4),
            "hipHeight": round(float(target_bind[joint_by_name["pelvis"]][1, 3]), 5),
            "groundHeight": round(float(min(
                target_bind[joint_by_name[name]][1, 3] for name in GROUND_JOINTS)), 5)}


class ShapeMesh:
    """Small, consistently wound primitive authoring helper."""
    def __init__(self):
        self.groups = [([], [], [], [], [], []), ([], [], [], [], [], [])]
        # Optional position -> [(joint, weight), ...] callback.  A rigid single
        # joint is right for a horn or a claw, but a tail or a shoulder shelf
        # needs to be shared between joints or it swings as one board.
        self.blend = None
        # World size of one texture repeat, in metres.  Every primitive here
        # authors its own 0..1 UVs -- a sphere spans the map once however big
        # it is, a tube wraps it once around whatever its circumference -- so
        # without this a toe claw and a mushroom cap would show the same scale
        # pattern at a twentyfold difference in size.  Off by default because
        # the region-map landmark builder shares this class.
        self.uv_tile = None

    def _skin(self, position, joint: int):
        if self.blend is None:
            return [joint, 0, 0, 0], [1., 0., 0., 0.]
        pairs = sorted(self.blend(position), key=lambda pair: -pair[1])[:4]
        total = sum(weight for _, weight in pairs) or 1.
        joints = [int(bone) for bone, _ in pairs] + [0] * (4 - len(pairs))
        weights = [weight / total for _, weight in pairs] + [0.] * (4 - len(pairs))
        return joints, weights

    def _rescale_uvs(self, positions, uvs, indices):
        """Retile a primitive's UVs to `uv_tile` metres per repeat."""
        if self.uv_tile is None or len(indices) < 3:
            return uvs
        points = np.asarray(positions, dtype=float)
        coords = np.asarray(uvs, dtype=float)
        faces = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
        pa, pb, pc = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]
        world = np.linalg.norm(np.cross(pb - pa, pc - pa), axis=1).sum() * .5
        ta, tb, tc = coords[faces[:, 0]], coords[faces[:, 1]], coords[faces[:, 2]]
        edge, other = tb - ta, tc - ta
        texel = np.abs(edge[:, 0] * other[:, 1] - edge[:, 1] * other[:, 0]).sum() * .5
        if world <= 1e-12 or texel <= 1e-12:
            return uvs
        scale = math.sqrt(world / texel) / self.uv_tile
        return [(u * scale, v * scale) for u, v in uvs]

    def _append(self, positions, normals, uvs, indices, joint: int, material: int):
        p, n, t, f, j, w = self.groups[material]
        uvs = self._rescale_uvs(positions, uvs, indices)
        base = len(p); p.extend(positions); n.extend(normals); t.extend(uvs)
        f.extend(base + int(i) for i in indices)
        for position in positions:
            joints, weights = self._skin(position, joint)
            j.append(joints); w.append(weights)

    def sphere(self, center, size, joint=0, material=0, rings=10, sides=20):
        cx, cy, cz = center; sx, sy, sz = (v * .5 for v in size)
        positions=[]; normals=[]; uvs=[]; faces=[]
        for ring in range(rings + 1):
            theta = math.pi * ring / rings
            for side in range(sides + 1):
                phi = 2 * math.pi * side / sides
                nx, ny, nz = math.sin(theta)*math.cos(phi), math.cos(theta), math.sin(theta)*math.sin(phi)
                position=(cx+sx*nx, cy+sy*ny, cz+sz*nz)
                normal=np.array((nx/max(sx,1e-4),ny/max(sy,1e-4),nz/max(sz,1e-4)))
                normal/=np.linalg.norm(normal)
                positions.append(position); normals.append(tuple(normal)); uvs.append((side/sides, ring/rings))
        for ring in range(rings):
            for side in range(sides):
                a=ring*(sides+1)+side; b=a+sides+1
                faces.extend((a,b,a+1,a+1,b,b+1))
        self._append(positions,normals,uvs,faces,joint,material)

    def box(self, center, size, joint=0, material=0):
        cx,cy,cz=center; sx,sy,sz=(v*.5 for v in size)
        corners=[(cx+x*sx,cy+y*sy,cz+z*sz) for x,y,z in
                 ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        self.prism(corners, joint, material)

    def prism(self, corners, joint=0, material=0):
        """Six-sided solid through eight arbitrary corners.

        Hewn Stoneborn plating and Mycelari gills are flat forms that do not
        line up with the world axes, and an axis-aligned box cannot express
        either without visibly floating off the surface it belongs to.
        """
        corners=[np.asarray(corner,dtype=float) for corner in corners]
        quads=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
        p=[];n=[];u=[];f=[]
        for quad in quads:
            points=[corners[i] for i in quad]
            normal=np.cross(points[1]-points[0],points[2]-points[0])
            length=np.linalg.norm(normal)
            if length<1e-9: continue
            normal/=length
            base=len(p);p.extend(tuple(point) for point in points)
            n.extend([tuple(normal)]*4);u.extend(((0,0),(1,0),(1,1),(0,1)))
            f.extend((base,base+1,base+2,base,base+2,base+3))
        self._append(p,n,u,f,joint,material)

    def revolve(self, profile, joint=0, material=0, sides=20):
        """Surface of revolution about the Y axis through (height, radius) pairs."""
        points=[(0.,height,0.) for height,_ in profile]
        radii=[radius for _,radius in profile]
        self.tapered_curve(points,radii,joint,material,sides)

    def cylinder(self, start, end, radius, joint=0, material=0, sides=16):
        a=np.array(start,dtype=float); b=np.array(end,dtype=float); axis=b-a; length=np.linalg.norm(axis)
        if length < 1e-6: return
        axis/=length; ref=np.array((1.,0.,0.)) if abs(axis[0])<.85 else np.array((0.,0.,1.))
        right=np.cross(axis,ref);right/=np.linalg.norm(right);forward=np.cross(right,axis)
        p=[];n=[];u=[];f=[]
        for row,center in enumerate((a,b)):
            for side in range(sides):
                angle=2*math.pi*side/sides; normal=right*math.cos(angle)+forward*math.sin(angle)
                p.append(tuple(center+normal*radius));n.append(tuple(normal));u.append((side/sides,row))
        for side in range(sides):
            nxt=(side+1)%sides;a0=side;a1=nxt;b0=sides+side;b1=sides+nxt
            f.extend((a0,b0,a1,a1,b0,b1))
        self._append(p,n,u,f,joint,material)

    def tapered_curve(self, points, radii, joint=0, material=0, sides=16):
        """Author a continuous tapered tube through bind-pose control points."""
        centers = np.asarray(points, dtype=float)
        if len(centers) < 2 or len(centers) != len(radii):
            return
        p=[];n=[];u=[];f=[]
        previous_right = None
        for row, center in enumerate(centers):
            if row == 0:
                tangent = centers[1] - center
            elif row == len(centers) - 1:
                tangent = center - centers[row - 1]
            else:
                tangent = centers[row + 1] - centers[row - 1]
            tangent /= max(np.linalg.norm(tangent), 1e-6)
            if previous_right is None:
                ref = np.array((1., 0., 0.)) if abs(tangent[0]) < .82 else np.array((0., 0., 1.))
                right = np.cross(tangent, ref)
            else:
                right = previous_right - tangent * np.dot(previous_right, tangent)
            if np.linalg.norm(right) < 1e-5:
                right = np.cross(tangent, np.array((0., 1., 0.)))
            right /= max(np.linalg.norm(right), 1e-6)
            forward = np.cross(right, tangent)
            forward /= max(np.linalg.norm(forward), 1e-6)
            previous_right = right
            for side in range(sides):
                angle = 2 * math.pi * side / sides
                normal = right * math.cos(angle) + forward * math.sin(angle)
                p.append(tuple(center + normal * radii[row]))
                n.append(tuple(normal));u.append((side / sides, row / (len(centers) - 1)))
        for row in range(len(centers) - 1):
            for side in range(sides):
                nxt = (side + 1) % sides
                a = row * sides + side; b = row * sides + nxt
                c = (row + 1) * sides + side; d = (row + 1) * sides + nxt
                f.extend((a, c, b, b, c, d))
        self._append(p,n,u,f,joint,material)

    def cone(self, start, end, radius, joint=0, material=0, sides=14):
        a=np.array(start,dtype=float); b=np.array(end,dtype=float); axis=b-a; length=np.linalg.norm(axis)
        if length < 1e-6:return
        axis/=length; ref=np.array((1.,0.,0.)) if abs(axis[0])<.85 else np.array((0.,0.,1.))
        right=np.cross(axis,ref);right/=np.linalg.norm(right);forward=np.cross(right,axis)
        p=[tuple(b)];n=[tuple(axis)];u=[(.5,0)];f=[]
        for side in range(sides):
            angle=2*math.pi*side/sides; radial=right*math.cos(angle)+forward*math.sin(angle)
            normal=radial*length+axis*radius;normal/=np.linalg.norm(normal)
            p.append(tuple(a+radial*radius));n.append(tuple(normal));u.append((side/sides,1))
        for side in range(sides):f.extend((0,1+side,1+(side+1)%sides))
        self._append(p,n,u,f,joint,material)

    def curved_tail(self, start, end, joint=0, material=0):
        a=np.array(start,dtype=float); b=np.array(end,dtype=float); previous=a
        for step in range(1,7):
            t=step/6; current=a*(1-t)+b*t+np.array((0., .12*math.sin(t*math.pi), .12*math.sin(t*math.pi)))
            self.cylinder(previous,current,.09*(1-t*.72),joint,material,12);previous=current

    def _frames(self, centers):
        """Parallel-transported (right, up, tangent) frames along a path."""
        frames = []
        previous_right = None
        for row, center in enumerate(centers):
            if row == 0:
                tangent = centers[1] - center
            elif row == len(centers) - 1:
                tangent = center - centers[row - 1]
            else:
                tangent = centers[row + 1] - centers[row - 1]
            tangent = tangent / max(np.linalg.norm(tangent), 1e-6)
            if previous_right is None:
                ref = np.array((1., 0., 0.)) if abs(tangent[0]) < .82 else np.array((0., 0., 1.))
                right = np.cross(tangent, ref)
            else:
                right = previous_right - tangent * float(np.dot(previous_right, tangent))
            if np.linalg.norm(right) < 1e-5:
                right = np.cross(tangent, np.array((0., 1., 0.)))
            right = right / max(np.linalg.norm(right), 1e-6)
            up = np.cross(right, tangent)
            up = up / max(np.linalg.norm(up), 1e-6)
            previous_right = right
            frames.append((right, up, tangent))
        return frames

    def swept(self, points, widths, heights, joint=0, material=0, sides=14,
              cap_start=True, cap_end=True):
        """Sweep an elliptical section along a path, with closed ends.

        A muzzle, a claw and a horn are all one continuous tapering solid with
        a section that is not round -- a snout is wider than it is deep, a claw
        is flattened side to side.  Building them from overlapping spheres and
        circular cones is what left visible intersection seams and gave claws
        no cross-section to read at all.
        """
        centers = np.asarray(points, dtype=float)
        if len(centers) < 2 or len(widths) != len(centers) or len(heights) != len(centers):
            return
        frames = self._frames(centers)
        p = []; n = []; u = []; f = []
        for row, (center, (right, up, tangent)) in enumerate(zip(centers, frames)):
            half_w = max(float(widths[row]), 1e-5)
            half_h = max(float(heights[row]), 1e-5)
            for side in range(sides):
                angle = 2. * math.pi * side / sides
                cos, sin = math.cos(angle), math.sin(angle)
                offset = right * (cos * half_w) + up * (sin * half_h)
                # Ellipse normal: scale the radial direction by the inverse
                # semi-axes or a flattened claw lights as though it were round.
                normal = right * (cos / half_w) + up * (sin / half_h)
                normal = normal / max(np.linalg.norm(normal), 1e-9)
                p.append(tuple(center + offset))
                n.append(tuple(normal))
                u.append((side / sides, row / (len(centers) - 1)))
        for row in range(len(centers) - 1):
            for side in range(sides):
                nxt = (side + 1) % sides
                a = row * sides + side; b = row * sides + nxt
                c = (row + 1) * sides + side; d = (row + 1) * sides + nxt
                f.extend((a, c, b, b, c, d))
        for cap, row in ((cap_start, 0), (cap_end, len(centers) - 1)):
            if not cap:
                continue
            center = centers[row]
            _, _, tangent = frames[row]
            direction = -tangent if row == 0 else tangent
            hub = len(p)
            p.append(tuple(center)); n.append(tuple(direction)); u.append((.5, .5))
            ring = row * sides
            for side in range(sides):
                nxt = (side + 1) % sides
                if row == 0:
                    f.extend((hub, ring + nxt, ring + side))
                else:
                    f.extend((hub, ring + side, ring + nxt))
        self._append(p, n, u, f, joint, material)

    def ridge(self, points, rises, widths, joint=0, material=0, spikes=0.):
        """A continuous crest along a path: a webbed fin, not a row of cones.

        `rises` is how far the crest stands off the path at each station and
        `widths` its thickness.  A non-zero `spikes` pulls alternate stations
        proud of the membrane so the ridge serrates without breaking into
        separate pieces.
        """
        centers = np.asarray(points, dtype=float)
        if len(centers) < 2 or len(rises) != len(centers):
            return
        frames = self._frames(centers)
        p = []; n = []; u = []; f = []
        span = max(len(centers) - 1, 1)
        for row, (center, (right, up, _)) in enumerate(zip(centers, frames)):
            rise = float(rises[row])
            if spikes:
                rise *= 1. + spikes * (1. if row % 2 else -1.)
            half = max(float(widths[row]), 1e-5)
            crest = center + up * rise
            for side, offset in ((0, -half), (1, half)):
                p.append(tuple(center + right * offset))
                n.append(tuple(right * (1. if offset > 0 else -1.)))
                u.append((side * .18, row / span))
                p.append(tuple(crest + right * offset * .35))
                n.append(tuple(right * (1. if offset > 0 else -1.)))
                u.append((side * .18 + .82, row / span))
        # Four vertices per station: base-left, tip-left, base-right, tip-right.
        for row in range(len(centers) - 1):
            a = row * 4; b = (row + 1) * 4
            for left, right_index in ((0, 1), (2, 3)):
                f.extend((a + left, b + left, a + right_index,
                          a + right_index, b + left, b + right_index))
            # Cap the crest edge between the two faces.
            f.extend((a + 1, b + 1, a + 3, a + 3, b + 1, b + 3))
        self._append(p, n, u, f, joint, material)

    def claw(self, base, direction, length, width, joint=0, material=0,
             curl=.34, sides=10, stations=6, flatten=.62):
        """A curved, laterally flattened claw rather than a straight cone.

        The curl bends the claw towards the palm and the flattened section
        gives it an edge, so it reads as a claw from the side as well as
        head on.  A circular cone read as a blob from every angle.
        """
        base = np.asarray(base, dtype=float)
        direction = np.asarray(direction, dtype=float)
        direction = direction / max(np.linalg.norm(direction), 1e-9)
        # Bend in the plane spanned by the digit and world down.
        down = np.array((0., -1., 0.))
        bend = down - direction * float(np.dot(down, direction))
        if np.linalg.norm(bend) < 1e-6:
            bend = np.cross(direction, np.array((1., 0., 0.)))
        bend = bend / max(np.linalg.norm(bend), 1e-9)
        points = []; widths = []; heights = []
        for step in range(stations):
            t = step / (stations - 1)
            points.append(tuple(base + direction * (length * t)
                                + bend * (curl * length * t * t)))
            taper = (1. - t) ** .78
            widths.append(width * taper * flatten)
            heights.append(width * taper)
        self.swept(points, widths, heights, joint, material, sides,
                   cap_start=True, cap_end=False)

    def plate(self, center, outward, along, length, width, thickness,
              joint=0, material=0, taper=.86, shear=0.):
        """A hewn slab with hard edges, seated on the surface it armours.

        Stone plating built from spheres and tubes reads as padding, because a
        smooth surface of revolution has no edge anywhere for a light to catch.
        A plate is flat-shaded on six quads instead, so it takes a hard
        specular line along every cut and looks quarried rather than inflated.
        """
        center = np.asarray(center, dtype=float)
        outward = np.asarray(outward, dtype=float)
        outward = outward / max(np.linalg.norm(outward), 1e-9)
        along = np.asarray(along, dtype=float)
        along = along - outward * float(np.dot(along, outward))
        if np.linalg.norm(along) < 1e-6:
            along = np.cross(outward, np.array((0., 1., 0.)))
        along = along / max(np.linalg.norm(along), 1e-9)
        across = np.cross(outward, along)
        across = across / max(np.linalg.norm(across), 1e-9)
        inner = center - outward * (thickness * .5)
        outer = center + outward * (thickness * .5) + along * shear
        corners = []
        for base, scale in ((inner, 1.), (outer, taper)):
            half_l = along * (length * .5 * scale)
            half_w = across * (width * .5 * scale)
            corners.extend([tuple(base - half_l - half_w), tuple(base + half_l - half_w),
                            tuple(base + half_l + half_w), tuple(base - half_l + half_w)])
        self.prism(corners, joint, material)

    def banded_plates(self, start, end, outward, count, length, width, thickness,
                      joint=0, material=0, taper=.84, spread=1.):
        """A run of overlapping plates stepping along a limb."""
        start = np.asarray(start, dtype=float)
        end = np.asarray(end, dtype=float)
        along = end - start
        span = float(np.linalg.norm(along))
        if span < 1e-6 or count < 1:
            return
        along = along / span
        for step in range(count):
            t = (step + .5) / count
            centre = start + (end - start) * t
            shrink = 1. - (1. - spread) * t
            self.plate(centre, outward, along, length * shrink, width * shrink,
                       thickness, joint, material, taper)

    def lofted(self, rings, joint=0, material=0, closed=True, flip=False):
        """Surface through a grid of rings, with normals from the grid itself.

        A surface of revolution is the one thing a mushroom cap must not be:
        perfect rotational symmetry is what makes it read as an umbrella.  This
        takes an explicit ring-by-ring grid so the outline, the thickness and
        the droop of the margin can all vary with angle.
        """
        grid = np.asarray(rings, dtype=float)
        if grid.ndim != 3 or grid.shape[0] < 2 or grid.shape[1] < 3:
            return
        depth, around = grid.shape[0], grid.shape[1]
        forward = np.roll(grid, -1, axis=1) - np.roll(grid, 1, axis=1)
        down = np.empty_like(grid)
        down[1:-1] = grid[2:] - grid[:-2]
        down[0] = grid[1] - grid[0]
        down[-1] = grid[-1] - grid[-2]
        normals = np.cross(down, forward)
        if flip:
            normals = -normals
        lengths = np.maximum(np.linalg.norm(normals, axis=2, keepdims=True), 1e-9)
        normals = normals / lengths
        p = []; n = []; u = []; f = []
        for row in range(depth):
            for side in range(around):
                p.append(tuple(grid[row, side]))
                n.append(tuple(normals[row, side]))
                u.append((side / around, row / (depth - 1)))
        limit = around if closed else around - 1
        for row in range(depth - 1):
            for side in range(limit):
                nxt = (side + 1) % around
                a = row * around + side; b = row * around + nxt
                c = (row + 1) * around + side; d = (row + 1) * around + nxt
                if flip:
                    f.extend((a, b, c, b, d, c))
                else:
                    f.extend((a, c, b, b, c, d))
        self._append(p, n, u, f, joint, material)

    def arrays(self):
        consolidated=[]
        for p,n,u,f,j,w in self.groups:
            consolidated.append((np.asarray(p,dtype="float32").reshape(-1,3),
                                 np.asarray(n,dtype="float32").reshape(-1,3),
                                 np.asarray(u,dtype="float32").reshape(-1,2),
                                 np.asarray(f,dtype="uint32").reshape(-1),
                                 np.asarray(j,dtype="uint16").reshape(-1,4),
                                 np.asarray(w,dtype="float32").reshape(-1,4)))
        # Compatibility prefix retained for the player builder; the grouped arrays are item 6.
        nonempty=next((g for g in consolidated if len(g[0])),(np.empty((0,3)),)*6)
        return (*nonempty, consolidated)


# The legacy blockout bone table and sphere/box geometry were replaced by the
# body-plan driven anatomy builder in creature_anatomy.py.  Bone *names* are
# still part of the runtime contract: godot-client/data/actors/models.json
# binds attachment points to "head", "body" and "neck".
CREATURE_BONES = anatomy.BONE_TOPOLOGY


def global_bone_positions(bones):
    return anatomy.global_positions(bones)


def creature_geometry(archetype: str, scale: float, bones=None) -> "anatomy.AnatomyMesh":
    return anatomy.creature_geometry(archetype, scale, bones)


def add_animation(glb: GLB, name: str, channels: dict[int, tuple[str, list[float], list[list[float]]]]) -> None:
    animation={"name":name,"samplers":[],"channels":[]}
    for node,(path,times,values) in channels.items():
        input_acc=glb.accessor(np.asarray(times,dtype="float32"),"SCALAR",bounds=True)
        width="VEC4" if path=="rotation" else "VEC3"
        output_acc=glb.accessor(np.asarray(values,dtype="float32"),width)
        animation["samplers"].append({"input":input_acc,"output":output_acc,"interpolation":"LINEAR"})
        animation["channels"].append({"sampler":len(animation["samplers"])-1,
                                      "target":{"node":node,"path":path}})
    glb.doc.setdefault("animations",[]).append(animation)



def apply_growth(mesh, slug: str, scale: float) -> None:
    """Scatter the moss, crystal, barnacles or bramble the art shows.

    The art never scatters growth evenly.  A moss bear carries a mantle over
    its back and shoulders with the brown hide showing on flank and belly; a
    moss troll wears the same mantle plus a beard.  Scattering uniformly in
    every direction — which is what an even radial pass does — turns both into
    a featureless bush and throws away the silhouette the growth is there to
    decorate.  So the heavy pass rides the upper surface, and a much lighter
    pass drapes the flanks.
    """
    entries = roster.GROWTH.get(slug)
    if not entries or not getattr(mesh, "torso", None):
        return
    spine, radii, bones = mesh.torso
    # An upright body is narrower than a quadruped's barrel, so the same count
    # reads as denser; it needs a size gain to clear a robe, not a count gain.
    upright = getattr(mesh, "upright", False)
    density = 1.60 if upright else 1.40
    gain = 1.32 if upright else 1.22
    limbs = getattr(mesh, "growth_extra", None) or ()
    # A standing figure's growth stops at the collar; running it to the end of
    # the torso spine buries the face, which is the one part a player reads.
    crown = 0.86 if upright else 0.98
    for kind, count, size in entries:
        # Mineral growth erupts in every direction; soft growth settles on the
        # upper surfaces.  One bias for both gave golems a tidy one-sided fan.
        bias = .30 if kind in anatomy.SPIKY_GROWTH else .60
        # Mantle: heaviest over the back and shoulders, thinning as it wraps.
        anatomy.encrust(mesh, kind, max(int(count * density), 3), spine, radii,
                        bones, scale, seed=f"{slug}:{kind}", size=size * gain,
                        span=(0.10, crown), up_bias=bias)
        # Drape: a sparse fringe further round the barrel, so the mantle has an
        # edge rather than stopping dead at the waterline.
        anatomy.encrust(mesh, kind, max(int(count * density * .40), 1), spine,
                        radii, bones, scale, seed=f"{slug}:{kind}:flank",
                        size=size * gain * .70, span=(0.14, crown * .96),
                        up_bias=min(bias, .16))
        # Limbs: arms and shoulders on the upright families, so growth does not
        # stop at the shoulder seam.
        for i, (pts, widths, limb_bones) in enumerate(limbs):
            anatomy.encrust(mesh, kind, max(int(count * density * .38), 2), pts,
                            widths, limb_bones, scale,
                            seed=f"{slug}:{kind}:limb{i}", size=size * gain * .78,
                            span=(0.05, 0.85), up_bias=.45)


def add_baked_animation(glb: GLB, name: str,
                        channels: dict[tuple[int, str], tuple[str, list, list]]) -> None:
    """Write a baked clip that may drive several paths on the same node."""
    animation = {"name": name, "samplers": [], "channels": []}
    for (node, _), (path, times, values) in sorted(channels.items()):
        input_acc = glb.accessor(np.asarray(times, dtype="float32"), "SCALAR", bounds=True)
        width = "VEC4" if path == "rotation" else "VEC3"
        output_acc = glb.accessor(np.asarray(values, dtype="float32"), width)
        animation["samplers"].append({"input": input_acc, "output": output_acc,
                                      "interpolation": "LINEAR"})
        animation["channels"].append({"sampler": len(animation["samplers"]) - 1,
                                      "target": {"node": node, "path": path}})
    glb.doc.setdefault("animations", []).append(animation)


def build_roster_creature(path: Path, actor_type: int, slug: str, label: str,
                          family: str, plan: str, base: tuple[int, int, int],
                          accent: tuple[int, int, int], scale: float,
                          surface: str | None = None) -> dict:
    """Author one creature from any skeleton family, not just the quadrupeds."""
    glb = GLB()
    glb.doc["nodes"] = []
    bones, mesh, clips = families.build_parts(family, plan, scale, slug)
    apply_growth(mesh, slug, scale)
    globals_ = anatomy.global_positions(bones)
    children: dict[int, list[int]] = {index: [] for index in range(len(bones))}
    for index, (_, parent, _) in enumerate(bones):
        if parent >= 0:
            children[parent].append(index)
    for index, (name, parent, translation) in enumerate(bones):
        node = {"name": name, "translation": [float(v) for v in translation]}
        if children[index]:
            node["children"] = children[index]
        glb.doc["nodes"].append(node)
    glb.doc["scenes"][0]["nodes"] = [0]

    inverse = []
    for position in globals_:
        matrix = np.eye(4, dtype="float32")
        matrix[:3, 3] = -position
        inverse.append(matrix.T.reshape(-1))
    glb.doc["skins"] = [{"name": f"Nymara {family.title()} Rig",
                         "joints": list(range(len(bones))), "skeleton": 0,
                         "inverseBindMatrices": glb.accessor(
                             np.asarray(inverse, dtype="float32"), "MAT4")}]

    # Full-colour albedo plus a matching normal map, both derived from one
    # height field so the relief lines up with the pattern.  The albedo carries
    # the palette, so the base colour factor stays white and is not applied
    # twice; the underside shares the grain and tints with a factor.
    hints = families.material_hints(family, plan, slug)
    gain = roster.VALUE_GAIN.get(slug, 1.0)
    base, accent = _lift(base, gain), _lift(accent, gain)
    surface_kind = hints.get("surface") or surface or plan
    albedo_png, _ = surfaces.surface_maps(
        surface_kind, base, accent, seed=slug, size=256,
        marking=surfaces.MARKINGS.get(slug))
    _, normal_png = surfaces.surface_maps(
        surface_kind, base, accent, seed=slug, size=192)
    if hints.get("glow"):
        # Shards, motes, orbs and props on an elemental belong to its own
        # palette; bone-white keratin turned every crystal swarm grey.
        horn_albedo, horn_normal = surfaces.surface_maps(
            surface_kind, accent, base, seed=f"{slug}:feature", size=160)
    else:
        horn_albedo, horn_normal = surfaces.keratin_maps(accent, seed=slug, size=160)
    dark = tuple(max(14, int(c * .26)) for c in base)
    alpha = float(hints.get("alpha", 1.0))
    alpha_mode = hints.get("alpha_mode")
    glow = float(hints.get("glow", 0.0))
    two_sided = bool(hints.get("double_sided", False))
    body_glow = tuple(int(c * glow) for c in base) if glow else None
    accent_glow = tuple(int(c * min(1.0, glow * 1.35)) for c in accent) if glow else None
    mats = [glb.material(f"{label} Hide", (255, 255, 255), roughness=.86,
                         texture_png=albedo_png, normal_png=normal_png,
                         emissive=body_glow, alpha=alpha, alpha_mode=alpha_mode,
                         double_sided=two_sided)]
    hide_texture = len(glb.doc["textures"]) - 2
    hide_normal = len(glb.doc["textures"]) - 1
    underside = tuple(min(255, int(.46 * a + .54 * b) + 26) for a, b in zip(accent, base))
    mats.append(glb.material(f"{label} Underside", underside, roughness=.82,
                             emissive=accent_glow, alpha=alpha,
                             alpha_mode=alpha_mode, double_sided=two_sided))
    glb.doc["materials"][mats[1]]["pbrMetallicRoughness"]["baseColorTexture"] = {
        "index": hide_texture}
    glb.doc["materials"][mats[1]]["normalTexture"] = {"index": hide_normal}
    mats.append(glb.material(f"{label} Claw", dark, roughness=.44, metallic=.04))
    # Motes, shards, orbs and props stay opaque so they read through the body.
    mats.append(glb.material(f"{label} Keratin", (255, 255, 255), roughness=.56,
                             metallic=.03, texture_png=horn_albedo,
                             normal_png=horn_normal, emissive=accent_glow))
    # Growth carries its own colour and surface: moss is green, rime is pale
    # ice, crystal keeps the creature's own mineral tint.
    growth_kinds = [(kind, count) for kind, count, _ in roster.GROWTH.get(slug, [])]
    growth_rgb = anatomy.growth_colour(growth_kinds, accent, base,
                                       roster.GROWTH_TINT.get(slug))
    growth_surface = {"moss": "moss", "vine": "moss", "leaf": "moss",
                      "fungus": "hide", "thorn": "bark", "barnacle": "barnacle",
                      "coral": "barnacle", "rime": "ice", "crystal": "crystal",
                      "ember": "energy", "plate": "stone", "spine": "bark"}.get(
        growth_kinds[0][0] if growth_kinds else "moss", "moss")
    growth_albedo, growth_normal = surfaces.surface_maps(
        growth_surface, growth_rgb, accent, seed=f"{slug}:growth", size=160)
    mats.append(glb.material(f"{label} Growth", (255, 255, 255), roughness=.80,
                             texture_png=growth_albedo, normal_png=growth_normal,
                             emissive=accent_glow))
    # The lit interior: a treant's heart-hollow, the glow inside a geode shell,
    # the bright centre a wisp swirls around.  It has to be its own material
    # because the shell around it stays dark -- that contrast is the whole
    # effect, and a whole-body emissive destroys it.
    core_rgb = (hints.get("core") or roster.CORE_TINT_OVERRIDE.get(slug)
                or roster.CORE_TINT.get(slug))
    if core_rgb is None:
        core_rgb = tuple(min(255, int(c * .45 + 150)) for c in accent)
    core_rgb = _saturate(core_rgb)
    mats.append(glb.material(f"{label} Core", core_rgb, roughness=.30,
                             metallic=.0, emissive=core_rgb))

    groups = mesh.arrays()
    # Settle the bind pose: raise the rig and its geometry together so a rest
    # pose never starts below the floor.  Shifting the root translation moves
    # every global, and shifting the vertices by the same amount keeps the skin
    # binding identical.
    filled = [a for a in groups if len(a[0])]
    if filled:
        lowest = float(min(a[0][:, 1].min() for a in filled))
        if lowest < -0.002:
            lift = -lowest
            for arrays in groups:
                if len(arrays[0]):
                    arrays[0][:, 1] += lift
            name, parent, translation = bones[0]
            bones[0] = (name, parent, (translation[0], translation[1] + lift,
                                       translation[2]))
            globals_ = anatomy.global_positions(bones)
            inverse = []
            for position in globals_:
                matrix = np.eye(4, dtype="float32")
                matrix[:3, 3] = -position
                inverse.append(matrix.T.reshape(-1))
            glb.doc["skins"][0]["inverseBindMatrices"] = glb.accessor(
                np.asarray(inverse, dtype="float32"), "MAT4")
            glb.doc["nodes"][0]["translation"] = [float(v) for v in bones[0][2]]

    primitives = []
    vertices = triangles = 0
    for index, arrays in enumerate(groups):
        if not len(arrays[0]):
            continue
        primitives.append(glb.primitive(*arrays[:4], mats[index],
                                        joints=arrays[4], weights=arrays[5]))
        vertices += len(arrays[0])
        triangles += len(arrays[3]) // 3
    glb.mesh_node(label, primitives, skin=0, parent=0)

    clips = anatomy.ground_clamp(clips, bones, groups)
    clips = anatomy.settle_final_pose(clips, bones, groups, "Death_A")
    for clip in anatomy.REQUIRED_CLIPS:
        add_baked_animation(glb, clip, clips[clip])
    glb.write(path)
    return {"actor_type": actor_type, "id": slug, "name": label, "family": family,
            "archetype": plan, "vertices": vertices, "triangles": triangles,
            "joints": len(bones), "animations": len(anatomy.REQUIRED_CLIPS)}


def _lift(rgb, gain: float):
    """Raise a colour's value by ``gain``, by blending it toward white.

    Multiplying clips: a colour with a channel already near 255 cannot get any
    brighter that way, so the creatures that needed lifting most -- the pale
    ones -- barely moved.  Blending toward white hits the requested mean
    exactly, never clips, and desaturates as it lightens, which is what a
    nearly-white gull or yak looks like in the artwork anyway.
    """
    if gain <= 1.0:
        return tuple(int(round(c)) for c in rgb)
    mean = sum(rgb) / 3.0
    if mean >= 254.0:
        return tuple(int(round(c)) for c in rgb)
    blend = min(1.0, mean * (gain - 1.0) / (255.0 - mean))
    return tuple(int(round(c + (255.0 - c) * blend)) for c in rgb)


def _saturate(rgb, floor: float = .58):
    """Push a colour sampled off the artwork back up to emissive strength.

    A core measured from a painting is averaged with all the bloom around it,
    so it comes back pale; emitted at that saturation it reads as a grey lamp
    rather than as light.  Keep the measured hue, restore the punch.
    """
    red, green, blue = (max(0.0, min(1.0, c / 255.0)) for c in rgb)
    hue, saturation, _ = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < .12:
        # A near-neutral colour has no meaningful hue -- what little it has is
        # sampling noise -- and pushing it to emissive saturation amplifies
        # that noise into a confident wrong answer.  Lift the value instead.
        return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(hue, saturation, 1.0))
    saturation = max(saturation, floor)
    return tuple(int(round(c * 255))
                 for c in colorsys.hsv_to_rgb(hue, saturation, 1.0))


def build_creature(path: Path, actor_type: int, slug: str, label: str, archetype: str,
                   base: tuple[int, int, int], accent: tuple[int, int, int],
                   scale: float) -> dict:
    """Author one production creature GLB: rig, skin, materials and clips."""
    glb = GLB()
    glb.doc["nodes"] = []
    bones = anatomy.skeleton_for(archetype, scale)
    globals_ = anatomy.global_positions(bones)
    children: dict[int, list[int]] = {index: [] for index in range(len(bones))}
    for index, (_, parent, _) in enumerate(bones):
        if parent >= 0:
            children[parent].append(index)
    for index, (name, parent, translation) in enumerate(bones):
        node = {"name": name, "translation": [float(v) for v in translation]}
        if children[index]:
            node["children"] = children[index]
        glb.doc["nodes"].append(node)
    glb.doc["scenes"][0]["nodes"] = [0]

    inverse = []
    for position in globals_:
        matrix = np.eye(4, dtype="float32")
        matrix[:3, 3] = -position
        inverse.append(matrix.T.reshape(-1))
    inverse_acc = glb.accessor(np.asarray(inverse, dtype="float32"), "MAT4")
    glb.doc["skins"] = [{"name": "Nymara Creature Rig",
                         "joints": list(range(len(bones))),
                         "skeleton": 0, "inverseBindMatrices": inverse_acc}]

    # -- materials -------------------------------------------------------
    # Full-colour albedo plus a matching normal map, both derived from one
    # height field so the relief lines up with the pattern.  The albedo carries
    # the palette, so the base colour factor stays white and is not applied
    # twice; the underside shares the grain and tints with a factor.
    hints = families.material_hints("quadruped", archetype, slug)
    gain = roster.VALUE_GAIN.get(slug, 1.0)
    base, accent = _lift(base, gain), _lift(accent, gain)
    albedo_png, _ = surfaces.surface_maps(
        archetype, base, accent, seed=slug, size=256,
        marking=surfaces.MARKINGS.get(slug))
    _, normal_png = surfaces.surface_maps(
        archetype, base, accent, seed=slug, size=192)
    if hints.get("glow"):
        # Shards, motes, orbs and props on an elemental belong to its own
        # palette; bone-white keratin turned every crystal swarm grey.
        horn_albedo, horn_normal = surfaces.surface_maps(
            surface_kind, accent, base, seed=f"{slug}:feature", size=160)
    else:
        horn_albedo, horn_normal = surfaces.keratin_maps(accent, seed=slug, size=160)
    dark = tuple(max(14, int(c * .26)) for c in base)
    alpha = float(hints.get("alpha", 1.0))
    alpha_mode = hints.get("alpha_mode")
    glow = float(hints.get("glow", 0.0))
    two_sided = bool(hints.get("double_sided", False))
    body_glow = tuple(int(c * glow) for c in base) if glow else None
    accent_glow = tuple(int(c * min(1.0, glow * 1.35)) for c in accent) if glow else None
    mats = [glb.material(f"{label} Hide", (255, 255, 255), roughness=.86,
                         texture_png=albedo_png, normal_png=normal_png,
                         emissive=body_glow, alpha=alpha, alpha_mode=alpha_mode,
                         double_sided=two_sided)]
    hide_texture = len(glb.doc["textures"]) - 2
    hide_normal = len(glb.doc["textures"]) - 1
    underside = tuple(min(255, int(.46 * a + .54 * b) + 26) for a, b in zip(accent, base))
    mats.append(glb.material(f"{label} Underside", underside, roughness=.82,
                             emissive=accent_glow, alpha=alpha,
                             alpha_mode=alpha_mode, double_sided=two_sided))
    glb.doc["materials"][mats[1]]["pbrMetallicRoughness"]["baseColorTexture"] = {
        "index": hide_texture}
    glb.doc["materials"][mats[1]]["normalTexture"] = {"index": hide_normal}
    mats.append(glb.material(f"{label} Claw", dark, roughness=.44, metallic=.04))
    # Motes, shards, orbs and props stay opaque so they read through the body.
    mats.append(glb.material(f"{label} Keratin", (255, 255, 255), roughness=.56,
                             metallic=.03, texture_png=horn_albedo,
                             normal_png=horn_normal, emissive=accent_glow))
    # Growth carries its own colour and surface: moss is green, rime is pale
    # ice, crystal keeps the creature's own mineral tint.
    growth_kinds = [(kind, count) for kind, count, _ in roster.GROWTH.get(slug, [])]
    growth_rgb = anatomy.growth_colour(growth_kinds, accent, base,
                                       roster.GROWTH_TINT.get(slug))
    growth_surface = {"moss": "moss", "vine": "moss", "leaf": "moss",
                      "fungus": "hide", "thorn": "bark", "barnacle": "barnacle",
                      "coral": "barnacle", "rime": "ice", "crystal": "crystal",
                      "ember": "energy", "plate": "stone", "spine": "bark"}.get(
        growth_kinds[0][0] if growth_kinds else "moss", "moss")
    growth_albedo, growth_normal = surfaces.surface_maps(
        growth_surface, growth_rgb, accent, seed=f"{slug}:growth", size=160)
    mats.append(glb.material(f"{label} Growth", (255, 255, 255), roughness=.80,
                             texture_png=growth_albedo, normal_png=growth_normal,
                             emissive=accent_glow))
    # The lit interior: a treant's heart-hollow, the glow inside a geode shell,
    # the bright centre a wisp swirls around.  It has to be its own material
    # because the shell around it stays dark -- that contrast is the whole
    # effect, and a whole-body emissive destroys it.
    core_rgb = (hints.get("core") or roster.CORE_TINT_OVERRIDE.get(slug)
                or roster.CORE_TINT.get(slug))
    if core_rgb is None:
        core_rgb = tuple(min(255, int(c * .45 + 150)) for c in accent)
    core_rgb = _saturate(core_rgb)
    mats.append(glb.material(f"{label} Core", core_rgb, roughness=.30,
                             metallic=.0, emissive=core_rgb))

    geometry = anatomy.creature_geometry(archetype, scale, bones)
    apply_growth(geometry, slug, scale)
    groups = geometry.arrays()
    primitives = []
    vertices = triangles = 0
    for index, arrays in enumerate(groups):
        if not len(arrays[0]):
            continue
        primitives.append(glb.primitive(*arrays[:4], mats[index],
                                        joints=arrays[4], weights=arrays[5]))
        vertices += len(arrays[0])
        triangles += len(arrays[3]) // 3
    glb.mesh_node(label, primitives, skin=0, parent=0)

    clips = anatomy.ground_clamp(anatomy.animation_set(archetype, scale, bones),
                                 bones, groups)
    clips = anatomy.settle_final_pose(clips, bones, groups, "Death_A")
    for clip in anatomy.REQUIRED_CLIPS:
        add_baked_animation(glb, clip, clips[clip])

    glb.write(path)
    return {"actor_type": actor_type, "id": slug, "name": label, "archetype": archetype,
            "vertices": vertices, "triangles": triangles, "joints": len(bones),
            "animations": len(anatomy.REQUIRED_CLIPS)}


def build_equipment(path: Path, slug: str, label: str, kind: str,
                    base: tuple[int,int,int], accent: tuple[int,int,int],
                    rig: "equipment_authoring.Rig", *,
                    features: tuple[str, ...] = (),
                    finish: str | None = None) -> dict:
    """Author one equipment GLB through the body-conforming pipeline."""
    return equipment_authoring.build_equipment_piece(
        path, rig, slug, label, kind, base, accent, finish=finish,
        features=features)


HAIR_SOURCES = {
    "buzzed": {"female": "Hair_BuzzedFemale", "male": "Hair_Buzzed"},
    "parted": {"female": "Hair_SimpleParted", "male": "Hair_SimpleParted"},
    "long": {"female": "Hair_Long", "male": "Hair_Long"},
    "buns": {"female": "Hair_Buns", "male": "Hair_Buns"},
}


def build_hair(source_dir: Path, output: Path, style: str, gender: str) -> dict:
    source_name = HAIR_SOURCES[style][gender]
    source = source_dir / "hairstyles" / f"{source_name}.gltf"
    document = json.loads(source.read_text(encoding="utf-8"))
    binary = (source.parent / document["buffers"][0]["uri"]).read_bytes()
    mesh_node_index = next(i for i, node in enumerate(document["nodes"]) if "mesh" in node)
    mesh_index = document["nodes"][mesh_node_index]["mesh"]
    primitive_source = document["meshes"][mesh_index]["primitives"][0]
    attrs = primitive_source["attributes"]
    positions = read_accessor(document, binary, attrs["POSITION"]).astype(np.float64)
    normals = read_accessor(document, binary, attrs["NORMAL"]).astype(np.float64)
    uvs = read_accessor(document, binary, attrs["TEXCOORD_0"]).astype(np.float32)
    indices = read_accessor(document, binary, primitive_source["indices"]).astype(np.uint32)

    body_path = source_dir / f"Superhero_{gender.title()}_FullBody.gltf"
    body_document = json.loads(body_path.read_text(encoding="utf-8"))
    head_node = next(i for i, node in enumerate(body_document["nodes"])
                     if node.get("name") == "Head")
    to_head_local = np.linalg.inv(global_node_matrix(body_document, head_node))
    transform = to_head_local @ global_node_matrix(document, mesh_node_index)
    homogeneous = np.column_stack((positions, np.ones(len(positions))))
    positions = (transform @ homogeneous.T).T[:, :3].astype(np.float32)
    normal_matrix = np.linalg.inv(transform[:3, :3]).T
    normals = (normal_matrix @ normals.T).T
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-6)

    material_source = primitive_source.get("material", 0)
    base_spec = document["materials"][material_source]["pbrMetallicRoughness"]["baseColorTexture"]
    image_uri = document["images"][document["textures"][base_spec["index"]]["source"]]["uri"]
    image_path = source.parent / image_uri
    if not image_path.is_file():
        image_path = source_dir / image_uri
    glb = GLB(generator="Eloria native Quaternius hairstyle packer")
    material = glb.material(
        f"Native Hair {style.title()}", (255, 255, 255), roughness=.82,
        texture_png=neutral_texture(image_path, floor=.42),
        normal_png=source_texture(document, source.parent, material_source, "normalTexture"),
        double_sided=True)
    primitive = glb.primitive(positions, normals.astype(np.float32), uvs, indices, material)
    glb.mesh_node("NativeHair_%s_%s" % (style.title(), gender.title()), [primitive])
    glb.write(output)
    return {"style": style, "gender": gender, "source": source_name,
            "vertices": len(positions), "triangles": len(indices) // 3,
            "bounds": {"min": positions.min(axis=0).round(5).tolist(),
                       "max": positions.max(axis=0).round(5).tolist()}}


# Generic pieces that are sculpted rather than generated, and the asset extra
# that marks the sculpted file. The shared cape (2026-10) is a Meshy cape fitted
# in Blender and packed by build_shared_cape.py; the procedural sheet this
# module used to write would replace it, so an existing sculpted file is kept
# and only its numbers are recorded.
SCULPTED_GENERIC = {"generic_cape": "eloriaSharedCape"}


def sculpted_generic(path: Path, piece) -> dict | None:
    marker = SCULPTED_GENERIC.get(piece.slug)
    if marker is None or not path.exists():
        return None
    raw = path.read_bytes()
    json_length = struct.unpack_from("<II", raw, 12)[0]
    doc = json.loads(raw[20:20 + json_length])
    if marker not in doc.get("asset", {}).get("extras", {}):
        return None
    vertices = sum(doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
                   for mesh in doc.get("meshes", []) for primitive in mesh["primitives"])
    stats = glb_geometry_stats(path)
    return {"id": piece.slug, "name": piece.label, "kind": piece.kind,
            "finish": piece.finish, "attach": "skinned", "skinRegion": "cape",
            "vertices": vertices, "triangles": stats["triangles"],
            "joints": stats["joints"], "bytes": len(raw)}


def glb_geometry_stats(path: Path) -> dict:
    """Triangle, joint and clip counts read back out of a finished GLB."""
    raw = path.read_bytes()
    json_length = struct.unpack_from("<II", raw, 12)[0]
    doc = json.loads(raw[20:20 + json_length])
    triangles = 0
    for mesh in doc.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if "indices" in primitive:
                triangles += doc["accessors"][primitive["indices"]]["count"] // 3
    joints = len(doc["skins"][0]["joints"]) if doc.get("skins") else 0
    return {"triangles": triangles, "joints": joints,
            "animations": len(doc.get("animations", []))}


def validate_glb(path: Path) -> dict:
    raw=path.read_bytes()
    if raw[:4]!=b"glTF":raise ValueError(f"invalid GLB magic: {path}")
    version,total=struct.unpack_from("<II",raw,4)
    if version!=2 or total!=len(raw):raise ValueError(f"invalid GLB header: {path}")
    json_length,json_kind=struct.unpack_from("<II",raw,12)
    if json_kind!=0x4E4F534A:raise ValueError(f"missing JSON chunk: {path}")
    doc=json.loads(raw[20:20+json_length])
    for mesh in doc.get("meshes",[]):
        for primitive in mesh.get("primitives",[]):
            if "POSITION" not in primitive.get("attributes",{}):raise ValueError(f"mesh without POSITION: {path}")
    return {"nodes":len(doc.get("nodes",[])),"meshes":len(doc.get("meshes",[])),
            "skins":len(doc.get("skins",[])),"animations":len(doc.get("animations",[]))}


def humanoid_model(scene: str, culture: str, gender: str) -> dict:
    return {
        "scene": scene,
        "animationLibrary": "res://assets/actors/native/shared/Universal_Animation_Library.glb",
        "animationMap": "res://data/animations/luminous.json",
        "culture": culture,
        "gender": gender,
        "hairStyles": [
            f"res://assets/actors/native/hair/buzzed_{gender}.glb",
            f"res://assets/actors/native/hair/parted_{gender}.glb",
            f"res://assets/actors/native/hair/long_{gender}.glb",
            f"res://assets/actors/native/hair/buns_{gender}.glb",
        ],
        "boneAliases": {"head": "Head"},
        # Native source characters face +Z, matching the creation-preview
        # camera.  Keeping this at zero presents the face and culture features
        # by default; the legacy 180-degree correction showed their backs.
        # Stature is carried here rather than in the rig: the animation clips
        # write pelvis translation directly, so a taller skeleton would leave
        # the hips at the reference height with the feet hanging below it.
        # The race rigs are authored facing +Z, so the visual root takes a half
        # turn onto Godot's -Z forward.  Stated per model rather than left to
        # the runtime default: the creature rigs are authored the other way.
        "import": {"scale": round(ANATOMY.get(culture, {}).get("stature", 1.), 4),
                   "rotationDegreesX": 0,
                   "rotationDegreesY": 0, "rotationDegreesZ": 0,
                   "forwardAxisCorrectionDegreesY": 180},
        "attachments": {
            "right_hand": "hand_r", "left_hand": "hand_l", "head": "Head",
            "back": "spine_03", "body": "spine_02", "pelvis": "pelvis",
            "feet": ["foot_l", "foot_r"], "neck": "neck_01",
        },
    }


def culture_loadout(culture: str, role: str = "") -> dict[str, int]:
    # The culture body models already carry a fully skinned shirt, pants, boots,
    # trim, and optional headwear. Keep NPC defaults to held/shoulder props so
    # rigid pelvis/body/head attachments cannot cover that production wardrobe.
    base = {
        "luminous": {},
        "votary": {0: 109},
        "glasswarden": {0: 102, 1: 101, 2: 101},
        "orun": {0: 106, 1: 103, 2: 103},
        "greyhaven": {0: 104, 1: 102, 2: 102},
        "ssarathi": {0: 107, 1: 104, 2: 104},
    }[culture].copy()
    if culture == "luminous" and role == "guard":
        return {0: 112, 1: 105, 2: 105}
    if culture == "luminous" and role == "ferryman":
        return {0: 105, 2: 102}
    if role in {"merchant", "official", "scholar", "lake_priest", "elder", "councilor"}:
        base.pop(1, None)
    if role in {"merchant", "scholar", "researcher", "astronomer"}:
        base[0] = {"luminous": 108, "glasswarden": 102,
                   "greyhaven": 113}.get(culture, base.get(0, 108))
    return base


def build_model_registry() -> dict:
    models = {}
    actor_types = {}
    creation = []
    for actor_type, model_id in PLAYER_ACTOR_TYPES.items():
        race, gender = model_id.rsplit("_", 1)
        models[model_id] = humanoid_model(
            f"res://assets/actors/native/races/{model_id}.glb", race, gender)
        actor_types[str(actor_type)] = model_id
        creation.append({"actorType": actor_type, "model": model_id,
                         "label": f"{RACES[race]['label']} {gender.title()}"})
    for actor_type, slug, *_ in CREATURES:
        actor_type += CREATURE_ACTOR_TYPE_OFFSET
        models[slug] = {
            "scene": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationLibrary": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationMap": "res://data/animations/creature.json",
            # A seed, not a statement about the body: `carry_forward_registry`
            # keeps whatever the catalogue already says for scale and facing.
            # It holds for a rig ``creature_anatomy`` built, which puts the
            # muzzle and jaw down -Z already on Godot's forward axis, and not
            # for the auto-rigged family, which is authored the other way and
            # needs the half turn.  tools/creature_facing.py measures which.
            "import": {"scale": 1, "rotationDegreesX": 0,
                       "rotationDegreesY": 0, "rotationDegreesZ": 0,
                       "forwardAxisCorrectionDegreesY": 0},
            "attachments": {"head": "head", "body": "body", "neck": "neck"},
        }
        actor_types[str(actor_type)] = slug

    for index, entry in enumerate(roster.ROSTER):
        slug = entry[0]
        models[slug] = {
            "scene": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationLibrary": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationMap": "res://data/animations/creature.json",
            # A seed, not a statement about the body: `carry_forward_registry`
            # keeps whatever the catalogue already says for scale and facing.
            # It holds for a rig ``creature_anatomy`` built, which puts the
            # muzzle and jaw down -Z already on Godot's forward axis, and not
            # for the auto-rigged family, which is authored the other way and
            # needs the half turn.  tools/creature_facing.py measures which.
            "import": {"scale": 1, "rotationDegreesX": 0,
                       "rotationDegreesY": 0, "rotationDegreesZ": 0,
                       "forwardAxisCorrectionDegreesY": 0},
            "attachments": {"head": "head", "body": "body", "neck": "neck"},
        }
        actor_types[str(roster_actor_type(index))] = slug

    for slug, _label, _archetype, scale, _tacked, actor_type in AMBIENT_CREATURES:
        models[slug] = {
            "scene": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationLibrary": f"res://assets/actors/native/creatures/{slug}.glb",
            "animationMap": "res://data/animations/creature.json",
            # A seed, not a statement about the body: `carry_forward_registry`
            # keeps whatever the catalogue already says for scale and facing.
            # It holds for a rig ``creature_anatomy`` built, which puts the
            # muzzle and jaw down -Z already on Godot's forward axis, and not
            # for the auto-rigged family, which is authored the other way and
            # needs the half turn.  tools/creature_facing.py measures which.
            "import": {"scale": scale, "rotationDegreesX": 0,
                       "rotationDegreesY": 0, "rotationDegreesZ": 0,
                       "forwardAxisCorrectionDegreesY": 0},
            "attachments": {"head": "head", "body": "body", "neck": "neck"},
            "serverActorType": actor_type,
        }
        actor_types[str(actor_type)] = slug

    # Humanoid enemies share player rigs and gain equipment-defined silhouettes.
    enemy_models = {
        236: "luminous_male", 237: "luminous_male", 238: "stoneborn_male",
        239: "luminous_male", 240: "luminous_male", 241: "luminous_male",
        242: "glasswarden_male", 243: "stoneborn_male", 244: "stoneborn_male",
        245: "votary_male", 246: "luminous_female", 247: "greyhaven_male",
        248: "ssarathi_male", 249: "orun_male", 250: "ssarathi_female",
        251: "ssarathi_male", 252: "orun_male", 253: "orun_male",
        254: "orun_male", 255: "luminous_female", 256: "luminous_male",
        257: "orun_male", 258: "orun_male", 259: "ssarathi_male",
    }
    actor_types.update({str(key): value for key, value in enemy_models.items()})
    # Invasion-only server IDs intentionally reuse the production native
    # creature library. Keep these in the generator so rebuilding character
    # assets cannot silently regress them to magenta fallbacks.
    invasion_models = {
        400: "river_otter", 401: "elk", 402: "desert_tortoise",
        403: "sunscale_drake", 404: "snow_hare", 405: "thunder_ram",
        406: "ice_bear", 407: "frost_tiger", 408: "ash_crawler",
        409: "dire_wolf", 410: "armored_rhino", 411: "giant_komodo",
        412: "emberfox", 413: "ridgehorn", 414: "saber_tooth_cat",
        415: "fire_salamander", 416: "moose", 417: "mossback_boar",
        418: "frost_maw", 419: "porcupine", 420: "two_tailed_fox",
        421: "miretoad", 422: "giant_komodo", 423: "sunscale_drake",
        424: "bog_lurker", 425: "miretoad", 426: "giant_crocodile",
        427: "giant_crocodile",
    }

    npc_looks = {}
    cultures = {
        "luminous": ["official", "guard", "merchant", "ferryman", "scholar", "lake_priest", "civilian"],
        "votary": ["monk", "mountaineer", "miner", "glacier_guardian"],
        "glasswarden": ["engineer", "astronomer", "researcher", "guard"],
        "orun": ["rider", "scout", "elder", "camp_resident", "mounted_warden"],
        "greyhaven": ["sailor", "fisher", "shipwright", "merchant", "militia", "councilor"],
        "ssarathi": ["civilian", "priest", "archivist", "warrior", "sun_ceremonial"],
    }
    actor_type = 300
    for culture, roles in cultures.items():
        for gender in ("female", "male"):
            for role in roles:
                model = f"{culture}_{gender}"
                actor_types[str(actor_type)] = model
                npc_looks[str(actor_type)] = {
                    "model": model,
                    "equipmentVisuals": {str(k): v for k, v in culture_loadout(culture, role).items()},
                }
                actor_type += 1
    actor_types.update({str(key): value for key, value in invasion_models.items()})
    return {"schemaVersion": 2, "models": models, "actorTypes": actor_types,
            "creationOptions": creation, "npcLooks": npc_looks}


def _footwear_catalogue():
    """The sixty-four footwear designs, if the catalogue is importable.

    Kept soft so a tree without it still builds the rest of the library.
    """
    try:
        from footwear_catalogue import VISUALS
    except Exception as error:  # pragma: no cover - a partial checkout
        print("skip footwear catalogue", error)
        return {}
    return VISUALS


def build_equipment_registry(rig: "equipment_authoring.Rig",
                             idle_bases: dict | None, author_rig: str = "",
                             girths: dict | None = None,
                             foot_anchors: dict | None = None,
                             footwear=None) -> dict:
    """Equipment registry v3: character-space sockets and skinned garments."""
    return equipment_authoring.build_equipment_registry(
        rig, EQUIPMENT, idle_bases, author_rig=author_rig, girths=girths,
        foot_anchors=foot_anchors, footwear=footwear)


def carry_forward_ambient(manifest_path: Path, manifest: dict) -> None:
    """Preserve ambient scenery entries contributed by regional generators.

    The Sunmane horses are authored by eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py
    and merged into these two registries.  Rebuilding the actor library used to
    drop them silently, which left every herd on the steppe as a magenta
    fallback until someone noticed.  Carry them across instead of rewriting
    them away.

    The models.json half of this now lives in `carry_forward_registry`, which
    keeps every entry the generator did not author rather than only the
    scenery ones.
    """
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        ambient = previous.get("ambientCreatures")
        if ambient:
            manifest["ambientCreatures"] = ambient


#: The keys of a model entry this generator decides: where the scene and its
#: clips live, and how the body is put together.  Everything else an entry
#: holds is somebody else's measurement of the artwork and is carried across a
#: rebuild rather than recomputed -- see `carry_forward_registry`.
AUTHORED_MODEL_KEYS = ("scene", "animationLibrary", "animationMap",
                       "attachments", "culture", "gender", "hairStyles",
                       "boneAliases")

#: The same split inside an entry's ``import`` block.  The rotations are the
#: generator's and are flat zero for everything it builds; ``scale`` and
#: ``forwardAxisCorrectionDegreesY`` are measurements of an individual body
#: that the tables below cannot know.
AUTHORED_IMPORT_KEYS = ("rotationDegreesX", "rotationDegreesY",
                        "rotationDegreesZ")


def keep_catalogued(previous: dict, fresh: dict) -> dict:
    """One model entry: the generator's lines, and the catalogue's numbers."""
    if previous.get('bodyTemplate'):
        # The source-body installer owns these reviewed models, including the
        # fitted hairstyles and skin calibration. Generic seeds cannot replace
        # those assets with old hair caps on a subsequent registry rebuild.
        return copy.deepcopy(previous)
    merged = {**fresh,
              **{key: value for key, value in previous.items()
                 if key != "import" and key not in AUTHORED_MODEL_KEYS}}
    merged["import"] = {**fresh.get("import", {}),
                        **{key: value
                           for key, value in previous.get("import", {}).items()
                           if key not in AUTHORED_IMPORT_KEYS}}
    return merged


def carry_forward_registry(models_path: Path, models: dict,
                           reseed: bool = False) -> None:
    """Seed a model once, and keep what the catalogue holds after that.

    `build_model_registry` writes the whole of models.json from CREATURES,
    creature_roster.ROSTER and AMBIENT_CREATURES.  Those tables say which
    bodies exist and where their files are.  They do not say how big a body is
    or which way it faces, and they have never been the whole library -- so
    rebuilding the file from them alone reverted five landed changes at once,
    every one of them silently, because a wholesale rewrite of a generated
    file looks exactly like the generator doing its job:

      * the sizes.  Every creature GLB is exported normalised to 1.7 m, and
        `import.scale` is the whole of what draws a fox smaller than a boar.
        A rebuild put 69 of them back to 1 and the roster back to one height.
      * the facings.  The creature rigs are two families authored facing
        opposite ways.  163 are built muzzle-first down -Z and need no turn,
        which is all this generator knows how to say; the 57 that came from
        the auto-rigger need the half turn, and without it a wolf attacks a
        player with the back of its head.
      * the reviewed models.  55 creatures and their 73 actor types were
        brought into the catalogue as their rigs passed review, and the
        generator has never heard of one of them.  A rebuild deleted them.
      * the invasion mapping.  22 actor types were pointed at reviewed art in
        place of their stand-ins; the table here still names the stand-ins.
      * the NPC bodies and their wardrobes.  The Stoneborn and Mycelari looks
        at 362-377 are not in `cultures` below, and the 56 emptied
        `equipmentVisuals` were emptied on purpose -- a look still naming a
        visual whose model has gone draws a placeholder blob on the bone.

    So the rule is the one import_generated_equipment.py adopted for stats:
    this tool authors the lines it owns and treats the rest of the file as
    somebody's work.  A model, actor type or look the generator defines is
    seeded on the run that first defines it and preserved on every run after;
    one it has never heard of is carried across untouched.

    The cost, and it is the whole cost: editing a number this generator seeds
    no longer reaches a model already in the catalogue.  ANATOMY stature is
    the one that bites -- a race's `import.scale` is rounded from there -- and
    `--reseed` is the way back.  It says how many entries it is reverting,
    because a silent revert is the thing this exists to stop.

    A wrong seed on a genuinely new model is not silent either:
    test_every_rig_declares_the_correction_its_facing_needs measures every
    body in the file against the correction its entry declares.
    """
    if not models_path.is_file():
        return
    previous = json.loads(models_path.read_text(encoding="utf-8"))
    kept = carried = reverted = 0

    for section, merge in (("models", keep_catalogued),
                           ("actorTypes", lambda held, _fresh: held),
                           ("npcLooks", lambda held, _fresh: held)):
        fresh = models[section]
        # The catalogue's order first, then whatever this run adds to it.  A
        # carried entry appended to the end instead of left where it sits
        # reindents the file around it, and a diff nobody can read is how the
        # reverts above went unnoticed in the first place.
        merged = {}
        for key, held in previous.get(section, {}).items():
            if key not in fresh:
                # Not in any table here: reviewed art, regional scenery,
                # anything added to the catalogue by hand.  These tables are
                # not the library, so an entry the generator cannot account
                # for is not an entry to drop -- and `--reseed` does not drop
                # it either.  Retiring one means editing models.json.
                merged[key] = held
                carried += 1
                continue
            wanted = merge(held, fresh[key])
            if wanted == fresh[key]:
                merged[key] = fresh[key]
            elif reseed:
                merged[key] = fresh[key]
                reverted += 1
            else:
                merged[key] = wanted
                kept += 1
        merged.update({key: value for key, value in fresh.items()
                       if key not in merged})
        models[section] = merged

    if reseed:
        print(f"reseed: reverting {reverted} catalogued entries to generator "
              f"defaults; {carried} entries the generator does not define are "
              f"carried across regardless")
    else:
        print(f"registry: kept {kept} catalogued entries, "
              f"carried {carried} the generator does not define")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def catalogue_path(path: Path, repo_root: Path) -> str:
    """The path a manifest records, relative to whichever checkout owns it.

    Modified 2026-08-29 for Eloria Client.  These paths used to be taken with
    ``relative_to(repo_root)`` against the checkout the *builder* lives in, so
    pointing ``--output`` at a git worktree raised ValueError and the build died
    after writing its GLBs but before writing the registry.  Asset work happens
    in worktrees, so the root is now the tree the output actually sits in - the
    parent of the ``godot-client`` directory on the way down to the file - and
    the builder's own repo is only the fallback for an output somewhere else.
    """
    for parent in path.parents:
        if parent.name == "godot-client":
            return path.relative_to(parent.parent).as_posix()
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    assets_root=Path(__file__).resolve().parents[1]
    repo_root=assets_root.parent
    parser.add_argument("--source",type=Path,default=assets_root/"source/player_models/native")
    parser.add_argument("--output",type=Path,default=repo_root/"godot-client/assets/actors/native")
    parser.add_argument("--manifest",type=Path,default=repo_root/"godot-client/data/actors/native_asset_catalog.json")
    parser.add_argument("--models",type=Path,default=repo_root/"godot-client/data/actors/models.json")
    parser.add_argument("--equipment-registry",type=Path,
                        default=repo_root/"godot-client/data/actors/equipment.json")
    parser.add_argument("--animation-library",type=Path,
                        default=repo_root/"godot-client/assets/actors/native/shared/Universal_Animation_Library.glb",
                        help="clip source used to solve weapon grips in the idle pose")
    parser.add_argument("--only",choices=("all","equipment","creatures"),default="all",
                        help="rebuild a single section instead of the whole library")
    parser.add_argument("--reseed",action="store_true",
                        help="take this generator's defaults for scale, facing "
                             "and actor-type mapping over what models.json "
                             "already holds, and say how many entries that "
                             "reverts; the way back after editing a seed. "
                             "Models the generator does not define are carried "
                             "across either way")
    args=parser.parse_args()
    if args.only in ("equipment","creatures") and args.manifest.is_file():
        manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.only=="equipment":
            manifest["equipment"]={}
            manifest["genericEquipment"]={}
        else:
            manifest["creatures"]={}
    else:
        manifest={"schemaVersion":2,"source":"nymara-concept-art-named.zip",
                  "pipeline":"build_native_nymara_glbs.py","races":{},"hair":{},
                  "creatures":{},"equipment":{},"genericEquipment":{}}
    if args.only=="all":
        for gender in ("female", "male"):
            for style in HAIR_SOURCES:
                hair_id = f"{style}_{gender}"
                path = args.output / "hair" / f"{hair_id}.glb"
                manifest["hair"][hair_id] = build_hair(args.source, path, style, gender) | {
                    "path": catalogue_path(path, repo_root)}
                print("hair", hair_id, manifest["hair"][hair_id])
        for race in RACES:
            for gender in ("female","male"):
                model=f"{race}_{gender}";path=args.output/"races"/f"{model}.glb"
                manifest["races"][model]=build_player(args.source,path,race,gender)|{"path":catalogue_path(path, repo_root)}
                print("race",model,manifest["races"][model])
    if args.only in ("all","creatures"):
        for actor_type,slug,label,archetype,base,accent,scale in CREATURES:
            actor_type += CREATURE_ACTOR_TYPE_OFFSET
            path=args.output/"creatures"/f"{slug}.glb"
            manifest["creatures"][slug]=build_creature(path,actor_type,slug,label,archetype,base,accent,scale)|{"path":catalogue_path(path, repo_root)}
            print("creature",slug,manifest["creatures"][slug])
    if args.only in ("all","creatures"):
        for index, entry in enumerate(roster.ROSTER):
            slug, label, family, plan, base, accent, scale, sheet, row, column = entry
            path = args.output / "creatures" / f"{slug}.glb"
            record = build_roster_creature(path, roster_actor_type(index), slug, label,
                                           family, plan, base, accent, scale)
            record |= {"path": catalogue_path(path, repo_root),
                       "locale": roster.SHEET_LOCALES[sheet],
                       "concept": {"sheet": sheet, "cell": [row, column]}}
            if family in HOVERING_FAMILIES:
                record["hovers"] = True
            manifest["creatures"][slug] = record
            print("creature", slug, record["triangles"], "tris")
    if args.only=="creatures":
        previous=manifest.get("validation",{}).get("results",{})
        rebuilt={catalogue_path(path, repo_root):validate_glb(path)
                 for path in (args.output/"creatures").rglob("*.glb")}
        merged={**previous,**{k:v for k,v in rebuilt.items() if k in previous}}
        manifest["validation"]={"files":len(merged),"results":merged}
        write_json(args.manifest, manifest)
        print(f"rebuilt {len(manifest['creatures'])} creature GLBs")
        return
    # Equipment is authored against the rig as it exists on disk, so a full run
    # has to build the races first or the geometry is fitted to a stale rest
    # pose. Loading the rig here also keeps a clean tree bootstrappable.
    rig_source=args.output/"races/luminous_male.glb"
    reference_rig=rig_source.stem
    rig=equipment_authoring.load_rig(rig_source)
    # Modified 2026-08-28 for Eloria Client: garments are lofted tight around
    # this one reference body.  They used to be lofted around the widest
    # silhouette in the whole cast so that a single mesh would clear everybody,
    # which fitted the broadest race and hung off every other one.  Each race's
    # measurements are shipped in the registry instead and the runtime refits
    # the garment per wearer, so the authored piece can stay close to the body.
    girths={}
    foot_anchors={}
    race_rigs={}
    for race_path in sorted((args.output/"races").glob("*.glb")):
        try:
            race_rigs[race_path.stem]=equipment_authoring.load_rig(race_path)
        except Exception as error:  # a race still being authored must not stop a build
            print("skip race measurement",race_path.name,error)
            continue
        girths[race_path.stem]=equipment_authoring.body_girth(race_rigs[race_path.stem])
        foot_anchors[race_path.stem]=equipment_authoring.foot_anchor(race_rigs[race_path.stem])
    print(f"measured {len(girths)} race silhouettes")
    # Male and female bodies differ in shape, not only in size - a bust and a
    # hip flare are not a scaled chest - and a per-bone radius cannot express
    # that, so the two builds of the reference culture are both measured at
    # authoring time.  Everything else is a size difference and is handled per
    # wearer at runtime, which is what keeps the piece close to the body.
    shape_cast=[race_rigs[name] for name in ("luminous_female",)
                if name in race_rigs]
    if shape_cast:
        rig=equipment_authoring.RigSet(rig, shape_cast)
        print(f"garment shape cast: reference + {len(shape_cast)}")
    idle_bases=None
    if args.animation_library.is_file():
        idle_bases=equipment_authoring._idle_hand_bases(
            str(rig_source), str(args.animation_library))
    def fit_variants(slug,label,kind,base,accent,finish=None,features=()):
        """Author the extra copies a race whose build differs needs."""
        built=[]
        for group,spec in equipment_authoring.FIT_GROUPS.items():
            if kind not in spec["kinds"]:
                continue
            group_rig=race_rigs.get(spec["rig"])
            if group_rig is None:
                print("skip variant",slug,group,"- no rig",spec["rig"])
                continue
            vslug=equipment_authoring.variant_slug(slug,group)
            vpath=args.output/"equipment"/f"{vslug}.glb"
            info=equipment_authoring.build_equipment_piece(
                vpath,group_rig,vslug,label,kind,base,accent,finish=finish,
                features=features)
            built.append(info|{"group":group,"authoredFor":spec["rig"],
                               "path":catalogue_path(vpath, repo_root)})
        return built

    manifest["fitVariants"]={}
    # The legwear rows carry two fields the others do not - the feature list a
    # silhouette is lofted from, and an explicit finish - so a row is unpacked
    # by length rather than by shape.
    for row in EQUIPMENT:
        slug,label,part,visual,kind,base,accent=row[:7]
        features=row[7] if len(row)>7 else ()
        finish=row[8] if len(row)>8 else None
        path=args.output/"equipment"/f"{slug}.glb"
        manifest["equipment"][slug]=build_equipment(
            path,slug,label,kind,base,accent,rig,features=features,finish=finish)|{
            "part":part,"visual":visual,"path":catalogue_path(path, repo_root)}
        print("equipment",slug,manifest["equipment"][slug])
        for info in fit_variants(slug,label,kind,base,accent,finish,features):
            manifest["fitVariants"][info["id"]]=info
            print("variant",info["id"],info["triangles"],"tris")
    # The generic tier claims the legacy visual ids directly. One authored mesh
    # serves a whole material ladder; the ids differ by a runtime tint.
    manifest["genericEquipment"]={}
    for piece in equipment_authoring.GENERIC_EQUIPMENT:
        path=args.output/"equipment"/f"{piece.slug}.glb"
        info=sculpted_generic(path,piece)
        if info is not None:
            manifest["genericEquipment"][piece.slug]=info|{
                "part":piece.part,
                "visuals":[visual for visual,_n,_b,_a in piece.variants],
                "path":catalogue_path(path, repo_root)}
            print("generic (sculpted, kept)",piece.slug)
            continue
        info=equipment_authoring.build_equipment_piece(
            path,rig,piece.slug,piece.label,piece.kind,piece.base,piece.accent,
            finish=piece.finish)
        manifest["genericEquipment"][piece.slug]=info|{
            "part":piece.part,
            "visuals":[visual for visual,_n,_b,_a in piece.variants],
            "path":catalogue_path(path, repo_root)}
        print("generic",piece.slug,manifest["genericEquipment"][piece.slug])
        for variant in fit_variants(piece.slug,piece.label,piece.kind,
                                    piece.base,piece.accent,finish=piece.finish):
            manifest["fitVariants"][variant["id"]]=variant
            print("variant",variant["id"],variant["triangles"],"tris")
    manifest["ambientCreatures"] = {}
    for slug, label, archetype, _scale, tacked, actor_type in AMBIENT_CREATURES:
        path = args.output / "creatures" / f"{slug}.glb"
        record = {"id": slug, "name": label, "archetype": archetype,
                  "path": catalogue_path(path, repo_root),
                  "generator": "eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py",
                  "tacked": tacked, "region": "sunmane_steppe",
                  "note": AMBIENT_SOURCE_NOTE, "actor_type": actor_type}
        if path.exists():
            record |= glb_geometry_stats(path)
        manifest["ambientCreatures"][slug] = record
    manifest["ambientCreaturesNote"] = AMBIENT_NOTE
    # Catalogue paths are POSIX-form on every platform.  str() on a Windows
    # PurePath yields backslashes, which the Godot side does not resolve and
    # which made the catalogue completeness test fail on Windows builds only.
    validation={catalogue_path(path, repo_root):validate_glb(path) for path in args.output.rglob("*.glb")}
    if args.only=="equipment":
        # Only revalidate what this run rebuilt.  Ambient scenery GLBs are
        # authored by a different generator and are not part of this manifest's
        # validated set, so a partial rebuild must not adopt them.
        previous=manifest.get("validation",{}).get("results",{})
        validation={key:value for key,value in validation.items()
                    if key in previous or "/equipment/" in key}
        validation={**previous,**validation}
    manifest["validation"]={"files":len(validation),"results":validation}
    models = build_model_registry()
    carry_forward_ambient(args.manifest, manifest)
    write_json(args.manifest, manifest)
    if args.only=="all":
        carry_forward_registry(args.models, models, reseed=args.reseed)
        write_json(args.models, models)
    write_json(args.equipment_registry,
               build_equipment_registry(rig, idle_bases,
                                        author_rig=reference_rig, girths=girths,
                                        foot_anchors=foot_anchors,
                                        footwear=_footwear_catalogue()))
    print(f"validated {len(validation)} native GLBs")


if __name__=="__main__":main()
