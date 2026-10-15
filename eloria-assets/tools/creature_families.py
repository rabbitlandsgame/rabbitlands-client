#!/usr/bin/env python3
"""Skeleton families beyond the quadruped rig.

The first production pass covered quadrupeds only.  The wider Nymara roster
needs body plans the quadruped rig cannot express at all - upright humanoids,
birds, serpents, spiders, insects, fish and formless elementals - so each gets
its own rest skeleton, geometry builder and gait.

Every family keeps the same runtime contract as the quadrupeds:

* bones named ``root``, ``body``, ``neck`` and ``head`` exist, because
  godot-client/data/actors/models.json binds attachment points to them,
* exactly one root, weights normalised across at most four influences,
* the seven clip names in data/animations/creature.json are authored,
* the bind pose stands on y = 0 and locomotion never translates the root
  horizontally.
"""
from __future__ import annotations

import math

import numpy as np

from creature_anatomy import (AnatomyMesh, MAT_ACCENT, MAT_BODY, MAT_CORE,
                              MAT_DARK, MAT_FEATURE, MAT_GROWTH, _bezier,
                              _sheet, _euler, qaxis, branch_system,
                              facet_shell, feather_row, foliage_cluster,
                              debris_field, global_positions, metal_band,
                              orbit_plates, plated_shell, root_flare,
                              swirl_ribbon, woven_trunk)

# ---------------------------------------------------------------------------
# Biped
# ---------------------------------------------------------------------------
# A waist bone lets the torso bend rather than pivot at the hips; cloak bones
# carry capes and robes; prop bones anchor whatever the creature is holding, so
# a staff or greatsword tracks the hand instead of floating beside it.
BIPED_BONES = (
    ("root", -1), ("body", 0), ("spine", 1), ("chest", 2), ("neck", 3),
    ("head", 4), ("jaw", 5),
    ("shoulder_l", 3), ("upper_arm_l", 7), ("forearm_l", 8), ("hand_l", 9),
    ("shoulder_r", 3), ("upper_arm_r", 11), ("forearm_r", 12), ("hand_r", 13),
    ("thigh_l", 1), ("shin_l", 15), ("foot_l", 16),
    ("thigh_r", 1), ("shin_r", 18), ("foot_r", 19),
    ("tail_1", 1), ("tail_2", 21),
    ("cloak_1", 3), ("cloak_2", 23),
    ("prop_r", 14), ("prop_l", 10),
)
BIPED_INDEX = {name: i for i, (name, _) in enumerate(BIPED_BONES)}


def _biped(**over) -> dict:
    base = dict(
        hip_h=.52, waist_h=.66, chest_h=.80, shoulder_h=.86, head_h=1.02,
        shoulder_w=.21, hip_w=.13, chest=(.20, .17), waist=(.145, .135),
        skull=(.17, .20, .19), muzzle=.0, brow=.030, cheek=.0,
        arm_len=.46, arm_r=.055, leg_len=.50, leg_r=.070, foot_len=.20,
        neck_r=.055, hunch=.0, robe=False, armor=None, bark=False,
        crest=None, mane=.0, horns=None, tail=.0, knuckle=False,
        digit=4, eye_r=.019, shoulder_pad=.0, weapon=None, ragged=.0,
        cloak=.0, hood=False, beard=.0, tabard=False, belt=True,
        shield=None, gaunt=.0, surface="fur",
        # Woody construction.  ``wood`` builds the torso out of separate
        # twisting strands instead of one closed tube and turns the limbs into
        # branches; ``crown`` grows a forking rack off the skull; ``heart`` is
        # the lit hollow the concept art puts in every treant's chest.
        wood=.0, crown=.0, heart=.0, canopy=.0, arm_splay=.0, orb=.0,
        # Plated construction, the stone-and-metal counterpart of ``wood``.
        # ``plated`` clads the body in discrete overlapping slabs, ``bands``
        # rings the joints in metal, and ``heart_style`` picks what surrounds
        # the lit core: bark staves on a treant, a socket ring on a golem.
        plated=.0, bands=.0, runes=.0, heart_style="bark",
        # How the plates are cut, and how many slabs stack on each shoulder.
        # The concept art does not give these creatures one armour: a cairn
        # golem is stacked river boulders, a frost golem angular scale, a
        # temple guardian big flat slabs, an amethyst golem erupting crystal.
        plate_shape="boulder", pauldron=0,
        # Arcane constructs are not built like the others: the art hangs their
        # armour off a lit core with nothing touching.  ``halo`` is that ring
        # of detached plates, ``blades`` the crystal wings that flank it, and
        # ``debris`` the pieces of a body that has come apart.
        halo=.0, blades=.0, debris=.0,
        # ``gate`` builds an arch into the chest with water falling through it,
        # ``shrine`` sets a little building on one shoulder, and ``claws`` hangs
        # a cluster of grasping talons below an armature.
        gate=.0, shrine=.0, claws=.0,
        # How far down the legs a robe reaches, and how wide it opens.  Taken
        # to the floor at full flare it is a bell with a head on it, and the
        # art's kings both show their shins.
        robe_len=1.0, robe_flare=1.0,
        # ``face`` decides what is under the brow: "flesh" is the default,
        # "skull" is the pale bone the art gives every revenant and barrow
        # knight, "ember" the lit sockets of a spirit.  ``hem`` shapes the
        # bottom of a garment, which is most of what tells a robe from a
        # cylinder at the distance a player sees it.
        face="flesh", hem="straight",
    )
    base.update(over)
    return base


BIPED_PLANS = {
    "warrior": _biped(weapon="spear", belt=True),
    "knight": _biped(shoulder_w=.245, chest=(.225, .19), armor="plate",
                     shoulder_pad=.095, weapon="sword", leg_r=.082, arm_r=.064,
                     crest="helm", cloak=.30, shield="kite", surface="metal"),
    "monarch": _biped(shoulder_w=.235, robe=True, armor="plate", shoulder_pad=.105,
                      crest="crown", weapon="staff", chest=(.215, .185),
                      cloak=.44, beard=.07, surface="cloth"),
    "mage": _biped(shoulder_w=.185, robe=True, weapon="staff", arm_r=.049,
                   chest=(.175, .155), hood=True, cloak=.30, surface="cloth"),
    "revenant": _biped(shoulder_w=.185, robe=True, ragged=.20, arm_r=.045,
                       chest=(.165, .14), skull=(.16, .19, .18), hood=True,
                       cloak=.26, surface="cloth"),
    # The art draws a golem as a cairn: a stack of separate boulders with a
    # small head sunk between enormous shoulders.  The proportions follow that
    # -- wider across the shoulders, shorter in the neck, heavier in the
    # forearm -- and the plating does the rest.
    "golem": _biped(hip_h=.50, waist_h=.64, chest_h=.80, shoulder_h=.88, head_h=1.08,
                    shoulder_w=.355, hip_w=.185, chest=(.300, .258),
                    waist=(.240, .210), arm_len=.55, arm_r=.118, leg_len=.48,
                    leg_r=.128, skull=(.180, .170, .180), shoulder_pad=.150,
                    hunch=.05, foot_len=.28, belt=False, surface="stone",
                    gaunt=.02, neck_r=.052,
                    plated=1.0, bands=.55, runes=.30, heart=.62,
                    heart_style="socket", face="ember", arm_splay=.075,
                    plate_shape="boulder", pauldron=4),
    "construct": _biped(hip_h=.52, waist_h=.66, head_h=1.08, shoulder_w=.320,
                        chest=(.265, .235), hip_w=.170,
                        arm_r=.098, leg_r=.112, armor="plate", shoulder_pad=.135,
                        skull=(.175, .170, .180), foot_len=.26, weapon="staff",
                        belt=False, surface="metal", neck_r=.050,
                        plated=.85, bands=1.0, runes=.35, heart=.68,
                        heart_style="socket", face="ember", arm_splay=.070,
                        plate_shape="slab", pauldron=4),
    "brute": _biped(hip_h=.50, waist_h=.64, chest_h=.80, shoulder_h=.88, head_h=1.01,
                    shoulder_w=.305, hip_w=.175, chest=(.275, .235),
                    waist=(.225, .205), arm_len=.61, arm_r=.094, leg_len=.46,
                    leg_r=.110, hunch=.07, skull=(.19, .19, .21), muzzle=.09,
                    shoulder_pad=.06, foot_len=.25, belt=False, surface="hide"),
    # An ape's head sits *clear* of its shoulders in the art, and it wears a
    # heavy ruff.  At .94 head height against .82 shoulders the skull was only
    # a tenth of a unit proud, and the shoulder mass swallowed it whole: the
    # jungle gorilla came out as a brown barrel with no face at all.
    "primate": _biped(hip_h=.44, waist_h=.58, chest_h=.74, shoulder_h=.82, head_h=1.06,
                      shoulder_w=.295, hip_w=.15, chest=(.265, .235),
                      waist=(.215, .195), arm_len=.69, arm_r=.090, leg_len=.40,
                      leg_r=.100, hunch=.12, knuckle=True, skull=(.20, .19, .22),
                      muzzle=.14, mane=.15, foot_len=.24, belt=False,
                      neck_r=.070, brow=.055),
    "treant": _biped(hip_h=.54, waist_h=.70, chest_h=.82, shoulder_h=.90, head_h=1.02,
                     shoulder_w=.265, hip_w=.175, chest=(.235, .215),
                     waist=(.195, .185), arm_len=.44, arm_r=.108, leg_len=.50,
                     leg_r=.112, bark=True, crest=None, skull=(.18, .20, .19),
                     foot_len=.28, belt=False, surface="bark",
                     wood=1.0, crown=1.0, heart=.85, canopy=.9, arm_splay=.22),
    "duelist": _biped(shoulder_w=.195, chest=(.175, .155), waist=(.132, .125),
                      arm_r=.049, leg_r=.063, weapon="rapier", crest="hat",
                      cloak=.36, surface="cloth"),
}

# Per-creature identity: the concept art gives these humanoids distinct
# silhouettes, so each one overrides the shared plan where it matters.
BIPED_DETAIL = {
    # Authored, not measured: no cell in the supplied art shows this creature.
    # A forest monarch -- a rack of living branches for a crown, bark over the
    # shoulders, a long mantle, and a seed of green light at the breast.
    "verdant_crown_king": dict(weapon="scepter", crest=None, cloak=.56,
                               beard=.11, shoulder_pad=.13, tabard=True,
                               crown=1.15, canopy=.75, heart=.58,
                               heart_style="socket", bark=True, pauldron=3,
                               hem="ragged", surface="bark",
                               robe_len=.72, robe_flare=.74, head_h=1.10,
                               skull=(.195, .225, .215), eye_r=.024),
    # The drowned king the artwork actually shows.
    "drowned_lich_king": dict(weapon="staff", crest="crown", cloak=.58,
                              beard=.0, shoulder_pad=.15, tabard=True,
                              armor="plate", pauldron=4, hem="ragged",
                              face="skull", heart=.52, heart_style="socket",
                              surface="metal", orb=.34, ragged=.16,
                              robe_len=.70, robe_flare=.72, head_h=1.12,
                              skull=(.195, .225, .215), eye_r=.024),
    "rimebound_archmage": dict(hem="ragged", face="ember", weapon="staff", hood=True, cloak=.40, beard=.10,
                               crest=None),
    "glacier_brute": dict(shoulder_pad=.11, horns="crag", surface="ice",
                          gaunt=.03, hunch=.09),
    "orrery_colossus": dict(crest=None, weapon=None, shoulder_pad=.16,
                            surface="metal", gaunt=.03, halo=1.55, robe=True,
                            hem="ragged", heart=1.35, plate_shape="slab",
                            pauldron=3, arm_splay=.10, claws=.62),
    "amethyst_sibyl": dict(hem="ragged", weapon=None, crest="shards", cloak=.42, hood=False),
    "crimson_duelist": dict(weapon="rapier", crest="hat", cloak=.44),
    "emberwood_matron": dict(face="ember", crest=None, weapon="lantern_staff", cloak=.40,
                             bark=True, wood=.85, crown=1.15, heart=.70,
                             canopy=1.15),
    "barrow_sovereign": dict(face="skull", weapon="greatsword", crest="helm", cloak=.50,
                             shoulder_pad=.12, armor="plate", tabard=True),
    "tidecaller_sorceress": dict(hem="ragged", weapon="staff", crest="coral", cloak=.46),
    "amethyst_golem": dict(crest="shards", surface="crystal", shoulder_pad=.14,
                          plate_shape="shard", pauldron=3),
    "orrery_sentinel": dict(crest="rings", weapon=None, surface="metal",
                           blades=.46, heart=.80, plate_shape="slab",
                           pauldron=3),
    "sunmane_minotaur": dict(horns="bull", weapon="axe", muzzle=.13, mane=.07,
                             shoulder_pad=.07, belt=True),
    "tidefin_naga": dict(weapon="trident", crest="fin", surface="scale"),
    "cascade_golem": dict(surface="stone", shoulder_pad=.12, crest="falls",
                         plate_shape="scale", pauldron=5, bands=.9),
    "reedhat_fisher": dict(crest="strawhat", weapon="sickle", cloak=.24),
    "ratcatcher_tough": dict(weapon="hook", hunch=.10, cloak=.20, crest="cowl"),
    "millstone_golem": dict(surface="stone", crest="yoke", shoulder_pad=.13,
                           plate_shape="drum", pauldron=3, bands=1.35),
    "drowned_dockhand": dict(hem="ragged", face="skull", ragged=.22, hood=False, weapon=None, hunch=.09),
    "waterwheel_golem": dict(surface="stone", crest="wheel", shoulder_pad=.12,
                             plate_shape="slab", pauldron=4, gate=.62),
    "barnacle_troll": dict(surface="barnacle", hunch=.10, horns="crag",
                           shoulder_pad=.08),
    "drowned_captain": dict(face="skull", weapon="cutlass", crest="tricorn", cloak=.38,
                            ragged=.14),
    "reedmask_stalker": dict(face="skull", weapon="spear", crest="mask", cloak=.34, ragged=.18),
    "barrow_knight": dict(face="skull", weapon="sword", shield="kite", crest="helm", cloak=.34),
    "cairn_golem": dict(surface="stone", crest="cairn", shoulder_pad=.13,
                        plate_shape="boulder", pauldron=4),
    "lantern_wraith": dict(hem="ragged", face="ember", weapon="lantern_staff", hood=True, cloak=.44, ragged=.24),
    "barrow_king": dict(face="skull", weapon="greatsword", crest="crown", cloak=.48, beard=.08,
                        tabard=True),
    "mirrorhold_wheelwarden": dict(surface="stone", crest="wheel", weapon=None,
                              hunch=.30, knuckle=True, arm_len=.72,
                              plate_shape="boulder", pauldron=4),
    "verdigris_warden": dict(weapon="staff", crest="helm", surface="metal",
                            plate_shape="slab", pauldron=4, chest=(.235, .205),
                            shoulder_w=.290, arm_r=.086, leg_r=.098),
    "shattered_sentinel": dict(surface="stone", crest=None, shoulder_pad=.10,
                              debris=1.0, plate_shape="slab", pauldron=3),
    "mirrorhold_oracle": dict(hem="ragged", weapon="staff", hood=True, cloak=.42, crest="coral"),
    "tideguard_vanguard": dict(weapon="spear", shield="round", crest="helm",
                               cloak=.30, tabard=True),
    "shardbound_archivist": dict(weapon="book", crest="shards", cloak=.40),
    "mirrorhold_loremaster": dict(weapon="book", crest="crown", cloak=.46,
                                  beard=.09),
    "bog_warden": dict(weapon="halberd", crest="helm", surface="stone",
                       plate_shape="slab", pauldron=4, shrine=.30),
    "frogspear_warrior": dict(weapon="spear", muzzle=.11, crest="fin",
                              surface="scale"),
    "canopy_gorilla": dict(mane=.08, muzzle=.12),
    "vine_treant": dict(face="ember", crest=None, bark=True, surface="bark",
                        wood=1.0, crown=.85, heart=.70, canopy=1.25),
    "moss_troll": dict(hunch=.10, horns="crag", surface="moss", muzzle=.10),
    "amberwood_treant": dict(face="ember", crest=None, bark=True, surface="bark",
                             wood=1.0, crown=1.10, heart=1.0, canopy=1.0),
    "thorn_revenant": dict(hem="ragged", face="skull", ragged=.26, crest="thorns", cloak=.34, weapon=None),
    "spectral_highwayman": dict(hem="ragged", face="skull", weapon="rapier", crest="tricorn", cloak=.46,
                                ragged=.16),
    "leafling_sprite": dict(face="ember", crest=None, bark=True, surface="bark",
                            wood=.75, crown=.55, heart=.60, canopy=.75),
    "ivy_stone_golem": dict(surface="stone", crest="cairn", shoulder_pad=.12,
                            plate_shape="boulder", pauldron=4),
    "amberwood_dryad": dict(hem="ragged", crest=None, cloak=.44, weapon=None,
                            wood=.45, crown=1.45, heart=.55, canopy=1.0),
    "amberwood_scarecrow": dict(hem="ragged", face="skull", crest="strawhat", weapon="hook", ragged=.28,
                                cloak=.22, surface="cloth"),
    "amberwood_ghost_knight": dict(face="skull", weapon="greatsword", crest="helm", cloak=.42,
                                   ragged=.12),
    "glacier_golem": dict(plate_shape="scale", pauldron=4),
    "frostplate_knight": dict(weapon="greatsword", crest="helm", cloak=.38,
                              shoulder_pad=.11, surface="ice"),
    "amberwood_owl": dict(),
}

BIPED_GAITS = {"primate": "knuckle", "golem": "heavy", "construct": "heavy",
               "brute": "heavy", "treant": "heavy"}


# Which plan keys each measured proportion moves.  Heights stretch together so
# the figure stays coherent; girths and widths follow the mass measurements.
BIPED_PROPORTION_RULES = {
    "hip_h": "tall", "waist_h": "tall", "chest_h": "tall",
    "shoulder_h": "tall", "head_h": "tall",
    "shoulder_w": "shoulder", "shoulder_pad": "shoulder", "hip_w": "hip",
    "chest": "shoulder", "waist": "girth",
    "arm_len": "limb", "leg_len": "limb",
    "arm_r": "girth", "leg_r": "girth", "neck_r": "girth",
    "skull": "head", "foot_len": "limb",
}


def biped_config(plan_key: str, variant: str | None = None) -> dict:
    import creature_anatomy as anatomy
    plan = dict(BIPED_PLANS[plan_key])
    if variant:
        plan.update(BIPED_DETAIL.get(variant, {}))
        # Hand-authored detail wins on the features it names; the concept
        # measurements then set how tall, broad and heavy the figure reads.
        plan = anatomy.scale_plan(plan, anatomy.proportions(variant),
                                  BIPED_PROPORTION_RULES)
    return plan


def biped_skeleton(plan_key: str, scale: float, variant: str | None = None):
    p = biped_config(plan_key, variant)
    s = scale
    hip = np.array((0., p["hip_h"] * s, 0.))
    waist = np.array((0., p["waist_h"] * s, -p["hunch"] * s * .2))
    chest = np.array((0., p["chest_h"] * s, -p["hunch"] * s * .5))
    neck = np.array((0., p["shoulder_h"] * s, -p["hunch"] * s * .8))
    head = np.array((0., p["head_h"] * s, -p["hunch"] * s))
    jaw = head + np.array((0., -p["skull"][1] * s * .38, -p["skull"][2] * s * .30))
    g = {"root": np.zeros(3), "body": hip, "spine": waist, "chest": chest,
         "neck": neck, "head": head, "jaw": jaw}
    for side, sign in (("l", -1.), ("r", 1.)):
        sw = p["shoulder_w"] * s * sign
        g[f"shoulder_{side}"] = neck + np.array((sw * .45, -.02 * s, 0.))
        g[f"upper_arm_{side}"] = neck + np.array((sw, -.03 * s, 0.))
        # ``arm_splay`` swings the arm out from the ribs.  A treant whose arms
        # hang plumb merges into its own trunk and loses the limbs entirely,
        # which is not what any of the concept art shows.
        splay = p["arm_splay"] * s
        elbow = g[f"upper_arm_{side}"] + np.array((sign * (.04 * s + splay),
                                                   -p["arm_len"] * s * .52, .01 * s))
        g[f"forearm_{side}"] = elbow
        g[f"hand_{side}"] = elbow + np.array((sign * (.03 * s + splay * .85),
                                              -p["arm_len"] * s * .48, .02 * s))
        g[f"prop_{side}"] = g[f"hand_{side}"] + np.array((sign * .02 * s,
                                                          -p["arm_r"] * s * 1.6, 0.))
        hx = p["hip_w"] * s * sign
        g[f"thigh_{side}"] = hip + np.array((hx, -.04 * s, 0.))
        g[f"shin_{side}"] = np.array((hx, p["hip_h"] * s - p["leg_len"] * s * .52,
                                      .02 * s))
        g[f"foot_{side}"] = np.array((hx, p["foot_len"] * s * .26, 0.))
    g["tail_1"] = hip + np.array((0., .02 * s, .10 * s))
    g["tail_2"] = g["tail_1"] + np.array((0., -.10 * s, .16 * s))
    g["cloak_1"] = chest + np.array((0., .02 * s, p["chest"][1] * s * .9))
    g["cloak_2"] = g["cloak_1"] + np.array((0., -p["cloak"] * s if p["cloak"] else -.10 * s,
                                            .06 * s))
    bones = []
    for name, parent in BIPED_BONES:
        base = np.zeros(3) if parent < 0 else g[BIPED_BONES[parent][0]]
        bones.append((name, parent, tuple(float(v) for v in (g[name] - base))))
    return bones


def _weapon(mesh, kind, grip, forward, up, side, s, bones, scale_hint=1.0):
    """Build the held prop at ``grip``, aligned to the hand's forward axis."""
    f = forward / max(np.linalg.norm(forward), 1e-9)
    u = up / max(np.linalg.norm(up), 1e-9)
    r = np.cross(f, u)
    L = s * scale_hint * 1.35

    def line(a, b, ra, rb, mat, sides=8):
        mesh.tube([a, (a + b) * .5, b], [(ra, ra), ((ra + rb) * .5,) * 2, (rb, rb)],
                  bones, mat, sides=sides)

    if kind in ("staff", "scepter", "lantern_staff"):
        butt = grip - u * .42 * L
        tip = grip + u * .72 * L
        line(butt, tip, .020 * L, .017 * L, MAT_FEATURE, 8)
        if kind == "staff":
            # A ring finial holding a lit stone, which is what the wardens and
            # the tide-callers carry; a plain ball on a pole reads as a mop.
            hub = tip + u * .11 * L
            ring = []
            for k in range(15):
                a = 2 * math.pi * k / 14
                ring.append(hub + r * (math.cos(a) * .105 * L)
                            + u * (math.sin(a) * .105 * L))
            mesh.tube(ring, [(.017 * L, .013 * L)] * 15, bones, MAT_ACCENT,
                      sides=5, cap_start=False, cap_end=False)
            mesh.ellipsoid(tuple(hub), (.070 * L, .070 * L, .048 * L), bones,
                           MAT_CORE, rings=6, sides=9)
            for k in range(4):
                a = 2 * math.pi * k / 4 + .4
                prong = hub + r * (math.cos(a) * .105 * L) + u * (math.sin(a) * .105 * L)
                mesh.spike(prong, prong + (prong - hub) * .55, .016 * L, bones,
                           MAT_ACCENT, 5)
        elif kind == "scepter":
            for k in range(4):
                a = 2 * math.pi * k / 4
                node = tip + (r * math.cos(a) + f * math.sin(a)) * .055 * L
                mesh.spike(tip, node + u * .07 * L, .018 * L, bones, MAT_ACCENT, 6)
        else:  # lantern on a hook
            hook = tip + f * .10 * L
            line(tip, hook, .012 * L, .010 * L, MAT_FEATURE, 6)
            mesh.ellipsoid(tuple(hook - u * .09 * L), (.055 * L, .075 * L, .055 * L),
                           bones, MAT_ACCENT, rings=7, sides=8)
    elif kind in ("sword", "greatsword", "cutlass", "rapier"):
        length = {"sword": .58, "greatsword": .86, "cutlass": .46, "rapier": .62}[kind]
        width = {"sword": .030, "greatsword": .042, "cutlass": .034, "rapier": .014}[kind]
        hilt = grip - u * .10 * L
        tip = grip + u * length * L
        mesh.tube([hilt, grip, (grip + tip) * .5, tip],
                  [(width * L * .8, width * L * .5), (width * L, width * L * .34),
                   (width * L * .92, width * L * .30), (width * L * .2, width * L * .12)],
                  bones, MAT_FEATURE, sides=6)
        guard = grip + u * .02 * L
        mesh.tube([guard - r * .085 * L, guard + r * .085 * L],
                  [(.016 * L, .016 * L), (.016 * L, .016 * L)], bones, MAT_DARK, 6)
        mesh.tube([hilt - u * .10 * L, grip],
                  [(.022 * L, .022 * L), (.024 * L, .024 * L)], bones, MAT_DARK, 6)
    elif kind in ("spear", "trident", "halberd"):
        butt = grip - u * .46 * L
        tip = grip + u * .70 * L
        line(butt, tip, .017 * L, .015 * L, MAT_FEATURE, 7)
        if kind == "spear":
            mesh.spike(tip, tip + u * .18 * L, .030 * L, bones, MAT_DARK, 7)
        elif kind == "trident":
            for offset in (-.055, 0., .055):
                base = tip + r * offset * L
                mesh.spike(base, base + u * (.17 if offset else .21) * L,
                           .019 * L, bones, MAT_DARK, 6)
            mesh.tube([tip - r * .06 * L, tip + r * .06 * L],
                      [(.014 * L,) * 2, (.014 * L,) * 2], bones, MAT_DARK, 6)
        else:  # halberd
            # A crescent axe head with a back spike and a long spear point.
            # A dark triangle a tenth of a scale unit across read as a small
            # black flag tied to a pole, and this is the largest thing the
            # temple guardian carries.
            mesh.spike(tip, tip + u * .34 * L, .028 * L, bones, MAT_FEATURE, 7)
            edge, back = [], []
            for k in range(9):
                t = k / 8.0
                # Taller than it is wide, with the cutting edge bowed out and
                # swept to a point top and bottom.  Bowed a third of a scale
                # unit across a short span it came out a paddle.
                bow = math.sin(math.pi * (.06 + .88 * t))
                edge.append(tip + u * L * (.30 - .74 * t)
                            + r * L * (.055 + .195 * bow))
                back.append(tip + u * L * (.26 - .66 * t) + r * L * .030)
            _sheet(mesh, edge, back, .015 * L, bones, MAT_ACCENT)
            # A bright bevel down the cutting edge.
            mesh.tube(edge, [(.011 * L, .007 * L)] * len(edge), bones,
                      MAT_FEATURE, sides=4, cap_start=False, cap_end=False)
            # The rear hook, opposite the blade.
            hook = tip - r * L * .085 + u * L * .04
            mesh.tube([hook, hook - r * L * .16 - u * L * .10,
                       hook - r * L * .19 - u * L * .22],
                      [(.030 * L, .016 * L), (.024 * L, .012 * L),
                       (.006 * L, .004 * L)], bones, MAT_FEATURE, sides=5)
            # A collar where the head meets the haft.
            mesh.tube([tip - u * .10 * L, tip - u * .02 * L],
                      [(.034 * L, .034 * L), (.030 * L, .030 * L)],
                      bones, MAT_DARK, sides=8)
    elif kind == "axe":
        butt = grip - u * .22 * L
        tip = grip + u * .50 * L
        line(butt, tip, .020 * L, .018 * L, MAT_FEATURE, 7)
        head = tip - u * .05 * L
        mesh.ellipsoid(tuple(head + r * .09 * L), (.13 * L, .16 * L, .045 * L),
                       bones, MAT_DARK, rings=6, sides=8)
    elif kind in ("sickle", "hook"):
        butt = grip - u * .16 * L
        tip = grip + u * .28 * L
        line(butt, tip, .018 * L, .015 * L, MAT_FEATURE, 6)
        curve = [tip, tip + f * .10 * L + u * .06 * L, tip + f * .17 * L - u * .03 * L]
        mesh.tube(curve, [(.016 * L,) * 2, (.012 * L,) * 2, (.005 * L,) * 2],
                  bones, MAT_DARK, sides=6)
    elif kind == "book":
        mesh.ellipsoid(tuple(grip + f * .05 * L),
                       (.16 * L, .05 * L, .13 * L), bones, MAT_ACCENT,
                       rings=5, sides=8)


def _headgear(mesh, kind, head_g, skull, head_i, s, p, neck_i=None):
    """Helms, crowns, hoods, hats, masks, horns and crests."""
    # Anything that hangs past the shoulders has to be able to weight to the
    # neck as well, or it swings with the head alone.
    neck_i = head_i if neck_i is None else neck_i
    if kind == "crown":
        base = head_g + np.array((0., skull[1] * .60, 0.))
        ring = [base + np.array((math.cos(2 * math.pi * k / 12) * skull[0] * .72,
                                 0., math.sin(2 * math.pi * k / 12) * skull[2] * .72))
                for k in range(13)]
        mesh.tube(ring, [(skull[0] * .10, skull[0] * .12)] * 13, [head_i],
                  MAT_FEATURE, sides=5, cap_start=False, cap_end=False)
        # Tall, uneven spikes swept slightly outward: at .12 of a scale unit
        # they were studs on a hatband, and the art makes the crown the tallest
        # thing on the figure.
        for k in range(9):
            a = 2 * math.pi * k / 9
            out = np.array((math.cos(a), 0., math.sin(a)))
            point = base + out * np.array((skull[0] * .74, 0., skull[2] * .74))
            reach = .30 * s * (1.0 if k % 2 else .66)
            mesh.tube([point, point + out * reach * .16
                       + np.array((0., reach * .55, 0.)),
                       point + out * reach * .30 + np.array((0., reach, 0.))],
                      [(.030 * s, .030 * s), (.018 * s, .018 * s),
                       (.004 * s, .004 * s)], [head_i], MAT_FEATURE, sides=5)
    elif kind == "helm":
        mesh.ellipsoid(tuple(head_g + np.array((0., skull[1] * .09, skull[2] * .03))),
                       (skull[0] * 1.16, skull[1] * 1.14, skull[2] * 1.14),
                       [head_i], MAT_FEATURE, rings=10, sides=14)
        visor = head_g + np.array((0., -skull[1] * .04, -skull[2] * .44))
        mesh.ellipsoid(tuple(visor), (skull[0] * .80, skull[1] * .30, skull[2] * .34),
                       [head_i], MAT_DARK, rings=5, sides=10)
        crest = head_g + np.array((0., skull[1] * .62, 0.))
        mesh.tube([crest + np.array((0., 0., -skull[2] * .40)),
                   crest + np.array((0., skull[1] * .16, 0.)),
                   crest + np.array((0., 0., skull[2] * .46))],
                  [(.009 * s, skull[1] * .11), (.011 * s, skull[1] * .19),
                   (.009 * s, skull[1] * .10)], [head_i], MAT_ACCENT, sides=5)
    elif kind == "hat":
        brim = head_g + np.array((0., skull[1] * .56, 0.))
        mesh.tube([brim - np.array((0., .012 * s, 0.)), brim + np.array((0., .012 * s, 0.))],
                  [(skull[0] * 1.62, skull[2] * 1.52), (skull[0] * 1.48, skull[2] * 1.38)],
                  [head_i], MAT_ACCENT, sides=14)
        mesh.ellipsoid(tuple(brim + np.array((0., .085 * s, 0.))),
                       (skull[0] * 1.25, .18 * s, skull[2] * 1.20),
                       [head_i], MAT_ACCENT, rings=7, sides=12)
        plume = brim + np.array((skull[0] * .8, .10 * s, 0.))
        mesh.tube([plume, plume + np.array((.12 * s, .16 * s, -.04 * s))],
                  [(.022 * s, .022 * s), (.006 * s, .006 * s)], [head_i],
                  MAT_FEATURE, sides=5)
    elif kind == "tricorn":
        brim = head_g + np.array((0., skull[1] * .58, 0.))
        for k in range(3):
            a = 2 * math.pi * k / 3
            corner = brim + np.array((math.cos(a) * skull[0] * 1.45, .02 * s,
                                      math.sin(a) * skull[2] * 1.45))
            mesh.ellipsoid(tuple((brim + corner) * .5),
                           (skull[0] * 1.10, .032 * s, skull[2] * 1.10),
                           [head_i], MAT_ACCENT, rings=4, sides=8)
        mesh.ellipsoid(tuple(brim + np.array((0., .07 * s, 0.))),
                       (skull[0] * 1.15, .13 * s, skull[2] * 1.10),
                       [head_i], MAT_ACCENT, rings=6, sides=10)
    elif kind == "strawhat":
        apex = head_g + np.array((0., skull[1] * 1.35, 0.))
        rim = head_g + np.array((0., skull[1] * .42, 0.))
        mesh.tube([rim, (rim + apex) * .5, apex],
                  [(skull[0] * 1.95, skull[2] * 1.95), (skull[0] * 1.15, skull[2] * 1.15),
                   (skull[0] * .12, skull[2] * .12)],
                  [head_i], MAT_ACCENT, sides=14, cap_start=False)
    elif kind == "hood" or kind == "cowl":
        # An open cowl.  A closed ellipsoid over the head sealed the face away
        # entirely, so every mage and revenant in the library was a smooth egg
        # on a pair of shoulders; the art always leaves the face showing in
        # shadow under a peak.  Built as a ring of panels with the front left
        # out, plus a peak and a mantle over the shoulders.
        centre = head_g + np.array((0., skull[1] * .12, skull[2] * .20))
        opening = 1.42                      # half-angle of the missing front
        panels = 15
        crown, mantle = [], []
        for k in range(panels):
            angle = math.pi + (2 * math.pi - 2 * opening) * (k / (panels - 1) - .5)
            out = np.array((math.sin(angle), 0., -math.cos(angle)))
            # The rim rises to a peak at the back and dips at the open front,
            # which is what makes a cowl read as cloth over a head rather than
            # as a collar standing on its own.
            reach = .55 + .45 * abs(math.cos((angle - math.pi) * .5))
            crown.append(centre + np.array((0., skull[1] * (.18 + .40 * reach), 0.))
                         + out * np.array((skull[0] * .62, 0., skull[2] * .66)))
            mantle.append(centre + np.array((0., -skull[1] * 1.02, 0.))
                          + out * np.array((skull[0] * .98, 0., skull[2] * 1.04)))
        _sheet(mesh, crown, mantle, skull[0] * .10, [head_i], MAT_ACCENT)
        # The peak that overhangs the face and puts it in shadow.
        peak = centre + np.array((0., skull[1] * .74, -skull[2] * .92))
        mesh.tube([peak + np.array((-skull[0] * .95, -skull[1] * .30, 0.)),
                   peak + np.array((0., 0., -skull[2] * .52)),
                   peak + np.array((skull[0] * .95, -skull[1] * .30, 0.))],
                  [(skull[0] * .12, skull[1] * .12),
                   (skull[0] * .20, skull[1] * .20),
                   (skull[0] * .12, skull[1] * .12)],
                  [head_i], MAT_ACCENT, sides=6)
    elif kind == "mask":
        mesh.ellipsoid(tuple(head_g + np.array((0., 0., -skull[2] * .66))),
                       (skull[0] * 1.45, skull[1] * 1.55, skull[2] * .55),
                       [head_i], MAT_FEATURE, rings=7, sides=12)
    elif kind == "antlers":
        for side in (-1., 1.):
            root = head_g + np.array((side * skull[0] * .5, skull[1] * .52, 0.))
            beam = [root, root + np.array((side * .11 * s, .19 * s, .10 * s)),
                    root + np.array((side * .21 * s, .34 * s, .24 * s))]
            mesh.tube(beam, [(.028 * s, .028 * s), (.020 * s, .020 * s),
                             (.008 * s, .008 * s)], [head_i], MAT_FEATURE, sides=7)
            for k, along in enumerate((.35, .70)):
                base = _bezier(beam, along)
                mesh.tube([base, base + np.array((side * .12 * s, .16 * s, -.05 * s))],
                          [(.017 * s, .017 * s), (.005 * s, .005 * s)],
                          [head_i], MAT_FEATURE, sides=6)
    elif kind == "branches":
        for side in (-1., 1.):
            root = head_g + np.array((side * skull[0] * .42, skull[1] * .48, 0.))
            for k, spread in enumerate((.14, .21, .27)):
                tip = root + np.array((side * spread * s, (.17 + .04 * k) * s,
                                       (-.06 + .06 * k) * s))
                mid = root * .45 + tip * .55 + np.array((0., .02 * s, 0.))
                mesh.tube([root, mid, tip],
                          [(.050 * s, .050 * s), (.031 * s, .031 * s), (.009 * s, .009 * s)],
                          [head_i], MAT_FEATURE, sides=7)
                fork = mid + np.array((side * .07 * s, .09 * s, .03 * s))
                mesh.tube([mid, fork], [(.022 * s, .022 * s), (.006 * s, .006 * s)],
                          [head_i], MAT_FEATURE, sides=5)
    elif kind == "thorns":
        for k in range(9):
            a = 2 * math.pi * k / 9
            base = head_g + np.array((math.cos(a) * skull[0] * .85, skull[1] * .30,
                                      math.sin(a) * skull[2] * .85))
            mesh.spike(base, base + np.array((math.cos(a) * .07 * s, .09 * s,
                                              math.sin(a) * .07 * s)),
                       .012 * s, [head_i], MAT_FEATURE, sides=5)
    elif kind == "shards":
        for k in range(8):
            a = 2 * math.pi * k / 8
            base = head_g + np.array((math.cos(a) * skull[0] * .70, skull[1] * .55,
                                      math.sin(a) * skull[2] * .70))
            mesh.ellipsoid(tuple(base + np.array((0., .06 * s, 0.))),
                           (.030 * s, .10 * s, .030 * s), [head_i], MAT_FEATURE,
                           rings=4, sides=5)
    elif kind == "rings":
        # An armillary cage, not three wire hoops.  The art builds these out of
        # broad banded rings of unequal size, each tilted off the others, with
        # a lit sphere caught at the centre and crystals set into the bands;
        # at .016 of a scale unit they drew as bent coat hangers.
        centre = head_g + np.array((0., skull[1] * .10, 0.))
        for index, (radius, tilt, width) in enumerate(
                ((2.35, 0.0, .052), (1.95, .62, .040), (2.15, -1.05, .034))):
            ring = []
            for k in range(21):
                a = 2 * math.pi * k / 20
                x = math.cos(a) * skull[0] * radius
                y = math.sin(a) * skull[1] * radius * math.cos(tilt)
                z = math.sin(a) * skull[2] * radius * math.sin(tilt)
                ring.append(centre + np.array((x, y, z)))
            mesh.tube(ring, [(width * s, width * s * .42)] * 21, [head_i],
                      MAT_FEATURE, sides=6, cap_start=False, cap_end=False)
            # Crystals set into the band, which is what carries the colour.
            for k in range(4):
                a = 2 * math.pi * k / 4 + index * .5
                x = math.cos(a) * skull[0] * radius
                y = math.sin(a) * skull[1] * radius * math.cos(tilt)
                z = math.sin(a) * skull[2] * radius * math.sin(tilt)
                mesh.ellipsoid(tuple(centre + np.array((x, y, z))),
                               (.075 * s, .105 * s, .075 * s), [head_i],
                               MAT_CORE, rings=5, sides=6)
        # The lit sphere the whole armature is built around.
        mesh.ellipsoid(tuple(centre), (skull[0] * 1.05,) * 3, [head_i],
                       MAT_CORE, rings=8, sides=12)
        mesh.ellipsoid(tuple(centre), (skull[0] * 1.35,) * 3, [head_i],
                       MAT_ACCENT, rings=6, sides=10)
    elif kind in ("coral", "fin"):
        for k in range(5):
            t = (k - 2) / 2.0
            base = head_g + np.array((t * skull[0] * .55, skull[1] * .55,
                                      skull[2] * .18))
            mesh.spike(base, base + np.array((t * .05 * s,
                                              (.13 - abs(t) * .04) * s, .05 * s)),
                       .018 * s, [head_i], MAT_ACCENT, sides=5)
    elif kind == "cairn":
        # A brow of stacked slabs sitting *on* the skull, not a stack of
        # balanced discs above it: the art's cairn golem wears its stones as a
        # heavy shelf over the eyes, and floating them clear of the head read
        # as a snowman's hat.
        for k in range(3):
            shelf = head_g + np.array((.018 * s * (1 if k % 2 else -1),
                                       skull[1] * (.36 + .30 * k),
                                       -skull[2] * (.10 - .07 * k)))
            mesh.ellipsoid(tuple(shelf),
                           (skull[0] * (2.05 - .34 * k), skull[1] * .46,
                            skull[2] * (1.85 - .30 * k)),
                           [head_i], MAT_BODY, rings=5, sides=9)
    elif kind == "yoke":
        # A timber frame across the shoulders with a millstone slung off each
        # end.  The bar on its own was a stick balanced on the golem's head:
        # the stones are the reason the yoke is there and the heaviest thing in
        # the silhouette.
        bar = head_g + np.array((0., skull[1] * .34, skull[2] * .55))
        span = skull[0] * 3.4
        mesh.tube([bar - np.array((span, 0., 0.)), bar + np.array((span, 0., 0.))],
                  [(.036 * s, .030 * s), (.036 * s, .030 * s)],
                  [head_i], MAT_ACCENT, sides=6)
        for sign in (-1., 1.):
            post = bar + np.array((sign * span * .58, 0., 0.))
            # Upright posts, so the frame reads as built rather than balanced.
            mesh.tube([post + np.array((0., -skull[1] * .95, 0.)),
                       post + np.array((0., skull[1] * .42, 0.))],
                      [(.026 * s, .024 * s), (.026 * s, .024 * s)],
                      [head_i], MAT_ACCENT, sides=5)
            # The rope and the stone on the end of it.
            hang = post + np.array((sign * span * .30, 0., 0.))
            stone = hang + np.array((0., -skull[1] * 2.5, 0.))
            mesh.tube([bar + np.array((sign * span * .88, 0., 0.)), stone],
                      [(.012 * s, .012 * s), (.010 * s, .010 * s)],
                      [head_i], MAT_DARK, sides=4)
            mesh.tube([stone - np.array((0., skull[1] * .30, 0.)),
                       stone + np.array((0., skull[1] * .30, 0.))],
                      [(skull[0] * 1.15, skull[0] * 1.15),
                       (skull[0] * 1.15, skull[0] * 1.15)],
                      [head_i], MAT_BODY, sides=12)
            mesh.ellipsoid(tuple(stone), (skull[0] * .34, skull[1] * .74,
                                          skull[0] * .34),
                           [head_i], MAT_DARK, rings=5, sides=8)
    elif kind == "wheel":
        # A waterwheel: two rims, an axle, spokes and paddles between them.
        # One thin hoop beside the head read as a hula hoop, and the wheel is
        # the largest thing in both of these figures.
        # Mounted behind the shoulder, on the axis the art puts it: a wheel
        # standing beside the head reads as a hoop being carried rather than as
        # machinery the creature is built around.
        hub = head_g + np.array((skull[0] * 1.5, -skull[1] * 1.35, skull[2] * 2.6))
        radius = .52 * s
        axis = np.array((1., 0., 0.))
        for offset in (-.09 * s, .09 * s):
            ring = []
            for k in range(19):
                a = 2 * math.pi * k / 18
                ring.append(hub + axis * offset
                            + np.array((0., math.sin(a) * radius,
                                        math.cos(a) * radius)))
            mesh.tube(ring, [(.030 * s, .030 * s)] * 19, [head_i], MAT_FEATURE,
                      sides=5, cap_start=False, cap_end=False)
        mesh.tube([hub - axis * .13 * s, hub + axis * .13 * s],
                  [(.040 * s, .040 * s), (.040 * s, .040 * s)], [head_i],
                  MAT_ACCENT, sides=8)
        for k in range(8):
            a = 2 * math.pi * k / 8
            rim = np.array((0., math.sin(a) * radius, math.cos(a) * radius))
            mesh.tube([hub, hub + rim],
                      [(.026 * s, .026 * s), (.018 * s, .018 * s)],
                      [head_i], MAT_ACCENT, sides=4)
            # The paddle boards, which are what catch the light on a wheel.
            _sheet(mesh,
                   [hub + rim * .62 - axis * .10 * s, hub + rim - axis * .10 * s],
                   [hub + rim * .62 + axis * .10 * s, hub + rim + axis * .10 * s],
                   .012 * s, [head_i], MAT_FEATURE)
    elif kind == "falls":
        # Water is the brightest thing on these figures and it *falls*: a
        # collar of stubby spikes round the head was neither.  Streams run from
        # the crown down past the shoulders, widening as they go, and they are
        # lit, because in the art they are the light source.
        for k in range(4):
            a = 2 * math.pi * k / 4 + .55
            base = head_g + np.array((math.cos(a) * skull[0] * 1.15,
                                      -skull[1] * .55,
                                      math.sin(a) * skull[2] * 1.15))
            drop = .52 * s
            mid = base + np.array((math.cos(a) * .10 * s, -drop * .45,
                                   math.sin(a) * .10 * s))
            end = base + np.array((math.cos(a) * .14 * s, -drop,
                                   math.sin(a) * .14 * s))
            mesh.tube([base, mid, end],
                      [(.014 * s, .014 * s), (.020 * s, .020 * s),
                       (.011 * s, .011 * s)],
                      [head_i, neck_i], MAT_CORE, sides=5)
            # The splash where it lands.
            mesh.ellipsoid(tuple(end + np.array((0., -.02 * s, 0.))),
                           (.075 * s, .028 * s, .075 * s), [head_i, neck_i],
                           MAT_CORE, rings=4, sides=7)


def biped_geometry(plan_key: str, scale: float, bones,
                   variant: str | None = None) -> AnatomyMesh:
    p = biped_config(plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = BIPED_INDEX
    mesh = AnatomyMesh(g)
    body_i, spine_i, chest_i = B["body"], B["spine"], B["chest"]
    neck_i, head_i, jaw_i = B["neck"], B["head"], B["jaw"]
    torso_bones = [body_i, spine_i, chest_i, neck_i]
    chest_r = tuple(v * s for v in p["chest"])
    waist_r = tuple(v * s for v in p["waist"])
    hip_r = (p["hip_w"] * s * 1.5, p["hip_w"] * s * 1.2)

    # ---- torso: hips, waist, ribcage, shoulders -------------------------
    spine_pts, radii = [], []
    for t, (rx, ry) in ((0.0, (hip_r[0] * .94, hip_r[1] * .94)),
                        (0.30, (waist_r[0] * 1.04, waist_r[1] * 1.04)),
                        (0.52, (waist_r[0], waist_r[1])),
                        (0.78, (chest_r[0] * .98, chest_r[1] * .98)),
                        (0.92, (chest_r[0], chest_r[1])),
                        (1.0, (chest_r[0] * .72, chest_r[1] * .78))):
        if t <= .52:
            point = g[body_i] * (1 - t / .52) + g[spine_i] * (t / .52)
        else:
            k = (t - .52) / .48
            point = g[spine_i] * (1 - k) + g[neck_i] * k
        spine_pts.append(point)
        radii.append((rx, ry))
    if p["wood"]:
        # A treant's bole is braided, and the gaps between the strands are what
        # separate it from a barrel with bark painted on.  A narrow inner tube
        # keeps the hollow from reading straight through to the far side.
        woven_trunk(mesh, spine_pts, radii, torso_bones, MAT_BODY,
                    seed=variant or plan_key,
                    strands=int(11 + 5 * p["wood"]), twist=1.55 * p["wood"],
                    inset=.10, bulge=1.06, thickness=.44,
                    material_inner=MAT_DARK, inner_scale=.66)
    else:
        mesh.tube(spine_pts, radii, torso_bones, MAT_BODY, sides=20, uv_scale=1.8,
                  lower_material=MAT_ACCENT, lower_threshold=-.74)
    if p["plated"]:
        # Slabs over the whole trunk.  The smooth tube stays underneath as the
        # body the plates are bolted to, so the gaps between them read as
        # shadowed joints rather than as holes.
        # MAT_BODY, not MAT_FEATURE: the plates *are* the golem, and routed
        # through the keratin material they read as bones strapped to a body
        # rather than as the body itself.  The shadow in the joints is what
        # separates them, and that is geometry, not colour.
        plated_shell(mesh, spine_pts, radii, torso_bones, MAT_BODY,
                     seed=f"{variant or plan_key}:torso",
                     rows=3, around=4,
                     relief=.52 * p["plated"], gap=.06, dome=.70,
                     rune_material=MAT_CORE if p["runes"] else None,
                     rune_chance=p["runes"] * .55, span=(.26, .86), shape=p["plate_shape"])
    mesh.upright = True
    mesh.torso = (list(spine_pts) + [g[head_i]],
                  list(radii) + [(p["skull"][0] * s * .5, p["skull"][1] * s * .5)],
                  list(torso_bones) + [head_i])
    if not p["wood"]:
        pelvis = .88 if p["plated"] else 1.0
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., -hip_r[1] * .20 * pelvis, 0.))),
                       (hip_r[0] * 1.52 * pelvis, hip_r[1] * 1.62 * pelvis,
                        hip_r[0] * 1.35 * pelvis),
                       [body_i, B["thigh_l"], B["thigh_r"]], MAT_BODY,
                       rings=9, sides=14)
    else:
        # The bole divides into two leg-boles.  A closed pelvis would seal the
        # weave shut, so the join is a short stranded saddle instead.
        for sign in (-1., 1.):
            hip_top = g[body_i] + np.array((0., hip_r[1] * .32, 0.))
            hip_low = g[B["thigh_l" if sign < 0 else "thigh_r"]]
            woven_trunk(mesh, [hip_top, (hip_top + hip_low) * .5, hip_low],
                        [(hip_r[0] * .78, hip_r[1] * .78),
                         (hip_r[0] * .70, hip_r[1] * .70),
                         (hip_r[0] * .60, hip_r[1] * .60)],
                        [body_i, B["thigh_l"], B["thigh_r"]], MAT_BODY,
                        seed=f"{variant or plan_key}:hip:{sign:+.0f}", strands=6,
                        twist=.55, inset=.12, bulge=1.04, thickness=.48)
    if p["heart"]:
        # The lit hollow.  A ring of bark shades it so the glow sits *inside*
        # the trunk rather than floating on the front of it.
        # The heart has to sit at the *front face* of the bole.  Buried at the
        # spine it was occluded by its own trunk from every angle a player sees,
        # which is the one thing the concept art will not tolerate: the glow is
        # the creature's whole identity.
        heart = p["heart"] * s
        socket = p["heart_style"] == "socket"
        core = (spine_pts[2] * (.30 if socket else .38)
                + spine_pts[3] * (.70 if socket else .62)
                + np.array((0., 0., -chest_r[1] * (.96 if socket else .80))))
        gem = (heart * .26, heart * .26, heart * .17) if socket else \
              (heart * .20, heart * .25, heart * .15)
        mesh.ellipsoid(tuple(core), gem, [chest_i, spine_i], MAT_CORE,
                       rings=8, sides=13)
        if p["heart_style"] == "socket":
            # A golem's core is a gem set into the breastplate: a metal collar
            # around it and a rune ring outside that, which is how the art
            # makes the chest the focus of the whole figure.
            # These are ring *radii*, and the gem beside them is sized as a
            # full extent: at .34 and .52 of the heart the collar came out four
            # times the width of the core it was meant to frame and read as a
            # tyre hung round the golem's middle.
            for radius, width, material in ((.175, .034, MAT_FEATURE),
                                            (.245, .022, MAT_ACCENT)):
                ring = []
                for k in range(19):
                    angle = 2 * math.pi * k / 18
                    ring.append(core + np.array((math.cos(angle) * heart * radius,
                                                 math.sin(angle) * heart * radius,
                                                 chest_r[1] * .10)))
                mesh.tube(ring, [(heart * width, heart * width)] * 19,
                          [chest_i, spine_i], material, sides=5,
                          cap_start=False, cap_end=False)
            for k in range(8):
                angle = 2 * math.pi * k / 8 + .2
                stud = core + np.array((math.cos(angle) * heart * .245,
                                        math.sin(angle) * heart * .245,
                                        chest_r[1] * .04))
                mesh.ellipsoid(tuple(stud), (heart * .040,) * 3,
                               [chest_i, spine_i], MAT_CORE, rings=4, sides=6)
        else:
            # A ring of bark staves around it, so the light reads as coming out
            # of a split in the wood rather than sitting on top of it.
            for k in range(11):
                angle = 2 * math.pi * k / 11
                rim = core + np.array((math.cos(angle) * heart * .19,
                                       math.sin(angle) * heart * .24,
                                       chest_r[1] * .12))
                out = core + np.array((math.cos(angle) * heart * .34,
                                       math.sin(angle) * heart * .42,
                                       chest_r[1] * .30))
                mesh.tube([rim, out],
                          [(heart * .055, heart * .055), (heart * .034, heart * .034)],
                          [chest_i, spine_i], MAT_BODY, sides=5)
    if p["gate"]:
        # The fountain guardian is built round a stone arch with water pouring
        # out of it; the chest was closed and the water was nowhere.
        gate = p["gate"] * s
        face = spine_pts[3] + np.array((0., 0., -chest_r[1] * .74))
        for sign in (-1., 1.):
            jamb = face + np.array((sign * gate * .34, 0., 0.))
            mesh.tube([jamb + np.array((0., -gate * .62, 0.)),
                       jamb + np.array((0., gate * .46, 0.))],
                      [(gate * .11, gate * .10), (gate * .10, gate * .09)],
                      [chest_i, spine_i], MAT_FEATURE, sides=6)
        arch = []
        for k in range(9):
            a = math.pi * k / 8
            arch.append(face + np.array((math.cos(a) * gate * .34,
                                         gate * .46 + math.sin(a) * gate * .30,
                                         0.)))
        mesh.tube(arch, [(gate * .10, gate * .09)] * 9, [chest_i, spine_i],
                  MAT_FEATURE, sides=6, cap_start=False, cap_end=False)
        # The dark of the opening, then the fall.
        mesh.ellipsoid(tuple(face + np.array((0., gate * .02, chest_r[1] * .10))),
                       (gate * .58, gate * .96, gate * .22),
                       [chest_i, spine_i], MAT_DARK, rings=7, sides=11)
        for k in range(5):
            offset = (k - 2) * gate * .12
            top = face + np.array((offset, gate * .30, -gate * .06))
            foot = np.array((face[0] + offset * 1.25, hip_r[1] * .10,
                             face[2] - gate * .30))
            mesh.tube([top, (top + foot) * .5 + np.array((0., 0., -gate * .10)),
                       foot],
                      [(gate * .085, gate * .060), (gate * .105, gate * .075),
                       (gate * .070, gate * .050)],
                      [chest_i, spine_i, body_i], MAT_CORE, sides=5)
        mesh.ellipsoid((face[0], hip_r[1] * .06, face[2] - gate * .30),
                       (gate * .92, gate * .16, gate * .62),
                       [body_i], MAT_CORE, rings=5, sides=12)
    if p["shrine"]:
        # A little temple riding one shoulder, as the art gives the sunken
        # temple guardian: a plinth, four columns and a pediment.
        shrine = p["shrine"] * s
        seat = g[B["upper_arm_l"]] + np.array((-shrine * .10, shrine * .78,
                                               -shrine * .10))
        bones = [B["shoulder_l"], B["upper_arm_l"], chest_i]
        mesh.tube([seat - np.array((0., shrine * .10, 0.)),
                   seat + np.array((0., shrine * .04, 0.))],
                  [(shrine * .60, shrine * .48), (shrine * .54, shrine * .43)],
                  bones, MAT_FEATURE, sides=4)
        for cx in (-.34, -.11, .11, .34):
            for cz in (-.28, .28):
                foot = seat + np.array((cx * shrine, shrine * .06, cz * shrine))
                mesh.tube([foot, foot + np.array((0., shrine * .62, 0.))],
                          [(shrine * .075, shrine * .075),
                           (shrine * .065, shrine * .065)],
                          bones, MAT_FEATURE, sides=6)
        lintel = seat + np.array((0., shrine * .70, 0.))
        mesh.tube([lintel, lintel + np.array((0., shrine * .10, 0.))],
                  [(shrine * .58, shrine * .46), (shrine * .50, shrine * .40)],
                  bones, MAT_FEATURE, sides=4)
        mesh.tube([lintel + np.array((0., shrine * .12, 0.)),
                   lintel + np.array((0., shrine * .42, 0.))],
                  [(shrine * .48, shrine * .38), (shrine * .06, shrine * .05)],
                  bones, MAT_FEATURE, sides=4)
    if p["claws"]:
        # Grasping talon clusters hanging below the armature.  The colossus in
        # the art reaches with these; hidden behind the halo it had no hands.
        claw = p["claws"] * s
        for sign in (-1., 1.):
            wrist = (spine_pts[2] + np.array((sign * chest_r[0] * 1.55,
                                              -chest_r[1] * .30,
                                              -chest_r[1] * .35)))
            bones = [chest_i, spine_i, B[f"upper_arm_{'l' if sign < 0 else 'r'}"]]
            mesh.ellipsoid(tuple(wrist), (claw * .30, claw * .26, claw * .30),
                           bones, MAT_FEATURE, rings=6, sides=9)
            for k in range(4):
                a = 2 * math.pi * k / 4 + .5
                out = np.array((math.cos(a) * .55 + sign * .35, -1.0,
                                math.sin(a) * .55))
                out = out / float(np.linalg.norm(out))
                knuckle = wrist + out * claw * .34
                tip = wrist + out * claw * .92 + np.array((0., -claw * .18, 0.))
                mesh.tube([wrist, knuckle, tip],
                          [(claw * .13, claw * .13), (claw * .10, claw * .10),
                           (claw * .025, claw * .025)],
                          bones, MAT_FEATURE, sides=5)
    if p["halo"]:
        # Armour hanging off the core rather than bolted to a body.  Two rings
        # at different radii and tilts, so the arc reads as depth rather than
        # as a flat wheel drawn round the chest.
        hub = (spine_pts[2] * .34 + spine_pts[3] * .66
               + np.array((0., 0., -chest_r[1] * .30)))
        halo = p["halo"] * s
        for index, (radius, count, arc, tilt, material) in enumerate(
                ((.60, 10, .48, .10, MAT_FEATURE),
                 (.90, 13, .38, -.14, MAT_BODY))):
            orbit_plates(mesh, hub, halo * radius, [chest_i, spine_i, body_i],
                         material, seed=f"{variant or plan_key}:halo:{index}",
                         count=count, arc=arc, width=.155, thickness=.052,
                         axis=(0., 0., 1.), tilt=tilt, sides=5)
        # Concentric rune rings on the plane of the core.
        for radius, width in ((.34, .030), (.46, .020)):
            ring = []
            for k in range(25):
                angle = 2 * math.pi * k / 24
                ring.append(hub + np.array((math.cos(angle) * halo * radius,
                                            math.sin(angle) * halo * radius,
                                            -chest_r[1] * .10)))
            mesh.tube(ring, [(halo * width, halo * width)] * 25,
                      [chest_i, spine_i], MAT_ACCENT, sides=5,
                      cap_start=False, cap_end=False)
    if p["blades"]:
        # The crystal wings the automaton is flanked by, edge-on to the front.
        blade = p["blades"] * s
        # ``skull`` is not resolved until the head is built further down, so
        # take the measurement straight off the plan here.
        cranium = tuple(v * s for v in p["skull"])
        for sign in (-1., 1.):
            root = g[head_i] + np.array((sign * cranium[0] * 2.9,
                                         cranium[1] * .10, 0.))
            tip = root + np.array((sign * blade * .06, blade * .50, 0.))
            heel = root + np.array((-sign * blade * .04, -blade * .44, 0.))
            mesh.tube([heel, root, tip],
                      [(blade * .03, blade * .014),
                       (blade * .15, blade * .052),
                       (blade * .03, blade * .014)],
                      [head_i, neck_i], MAT_CORE, sides=5)
    if p["debris"]:
        # A body that has come apart and not finished falling.
        debris_field(mesh, spine_pts[3], np.array(
            (chest_r[0] * 2.6, chest_r[1] * 2.2, chest_r[1] * 2.2)),
            [chest_i, spine_i, body_i], MAT_BODY,
            seed=f"{variant or plan_key}:debris",
            count=int(6 + 8 * p["debris"]), size=chest_r[0] * .46 * p["debris"])
    if p["belt"]:
        belt = g[spine_i] + np.array((0., -waist_r[1] * .30, 0.))
        mesh.tube([belt - np.array((0., .018 * s, 0.)), belt + np.array((0., .018 * s, 0.))],
                  [(waist_r[0] * 1.16, waist_r[1] * 1.16),
                   (waist_r[0] * 1.14, waist_r[1] * 1.14)],
                  [spine_i, body_i], MAT_DARK, sides=14, cap_start=False, cap_end=False)
    if p["tabard"]:
        top = spine_pts[3]
        hemp = np.array((0., p["hip_h"] * s * .30, -chest_r[1] * .55))
        _sheet(mesh, [top + np.array((-chest_r[0] * .52, 0., -chest_r[1] * .88)),
                      hemp + np.array((-chest_r[0] * .46, 0., 0.))],
               [top + np.array((chest_r[0] * .52, 0., -chest_r[1] * .88)),
                hemp + np.array((chest_r[0] * .46, 0., 0.))],
               .010 * s, [chest_i, spine_i, body_i], MAT_ACCENT)

    # ---- shoulder girdle -------------------------------------------------
    girdle_l, girdle_r = g[B["upper_arm_l"]], g[B["upper_arm_r"]]
    gr = p["arm_r"] * s * 1.55
    yoke = [girdle_l + np.array((0., .01 * s, 0.)),
            (girdle_l + spine_pts[-1]) * .5, spine_pts[-1],
            (girdle_r + spine_pts[-1]) * .5,
            girdle_r + np.array((0., .01 * s, 0.))]
    yoke_r = [(gr * .78, gr * .78), (chest_r[0] * .58, chest_r[1] * .62),
              (chest_r[0] * .86, chest_r[1] * .90),
              (chest_r[0] * .58, chest_r[1] * .62), (gr * .78, gr * .78)]
    yoke_bones = [chest_i, B["shoulder_l"], B["shoulder_r"], neck_i]
    if p["wood"]:
        woven_trunk(mesh, yoke, yoke_r, yoke_bones, MAT_BODY,
                    seed=f"{variant or plan_key}:yoke", strands=6, twist=.85,
                    inset=.18, bulge=1.08, thickness=.66)
    else:
        mesh.tube(yoke, yoke_r, yoke_bones, MAT_BODY, sides=12)

    # ---- neck and head ---------------------------------------------------
    neck_r = p["neck_r"] * s
    mesh.tube([spine_pts[-1], (spine_pts[-1] + g[head_i]) * .5, g[head_i]],
              [(neck_r * 1.40, neck_r * 1.40), (neck_r * 1.06, neck_r * 1.06),
               (neck_r * .96, neck_r * .96)],
              [chest_i, neck_i, head_i], MAT_BODY, sides=12,
              cap_start=False, cap_end=False)
    skull = tuple(v * s for v in p["skull"])
    mesh.ellipsoid(tuple(g[head_i]), skull, [head_i, neck_i], MAT_BODY,
                   rings=12, sides=16)
    mesh.ellipsoid(tuple(g[head_i] + np.array((0., skull[1] * .16, skull[2] * .20))),
                   (skull[0] * .94, skull[1] * .92, skull[2] * .90),
                   [head_i], MAT_BODY, rings=9, sides=14)
    brow = g[head_i] + np.array((0., skull[1] * .26, -skull[2] * .40))
    mesh.ellipsoid(tuple(brow), (skull[0] * .98, p["brow"] * s * 2.0, skull[2] * .34),
                   [head_i], MAT_BODY, rings=6, sides=12)
    # Cheek and chin give the face a read at gameplay distance.
    mesh.ellipsoid(tuple(g[head_i] + np.array((0., -skull[1] * .22, -skull[2] * .40))),
                   (skull[0] * .80, skull[1] * .46, skull[2] * .52),
                   [head_i, jaw_i], MAT_BODY, rings=6, sides=12)
    if p["muzzle"]:
        tip = g[head_i] + np.array((0., -skull[1] * .18,
                                    -skull[2] * .52 - p["muzzle"] * s))
        mesh.tube([g[head_i] + np.array((0., -skull[1] * .10, -skull[2] * .24)), tip],
                  [(skull[0] * .46, skull[1] * .40), (skull[0] * .30, skull[1] * .26)],
                  [head_i, jaw_i], MAT_BODY, sides=10, cap_start=False)
    mesh.tube([g[jaw_i], g[jaw_i] + np.array((0., -.01 * s, -skull[2] * .52))],
              [(skull[0] * .62, skull[1] * .26), (skull[0] * .44, skull[1] * .20)],
              [jaw_i, head_i], MAT_BODY, sides=10, cap_start=False)
    eye = p["eye_r"] * s
    # What makes a face read at gameplay distance is not detail, it is shadow:
    # a brow that overhangs, sockets that are holes rather than dots, a nose
    # that catches light on one side and a jaw with an edge.  Without those a
    # head is a ball, which is what every humanoid in this library was.
    pale = p["face"] in ("skull", "ember")
    face_mat = MAT_FEATURE if pale else MAT_BODY
    if pale:
        # A bone mask over the front of the skull: the art gives every barrow
        # knight, revenant and drowned thing a face lighter than its armour.
        mesh.ellipsoid(tuple(g[head_i] + np.array((0., skull[1] * .02,
                                                   -skull[2] * .30))),
                       (skull[0] * .92, skull[1] * .96, skull[2] * .82),
                       [head_i], face_mat, rings=9, sides=13)
    for side in (-1., 1.):
        socket = g[head_i] + np.array((side * skull[0] * .42, skull[1] * .10,
                                       -skull[2] * .46))
        # The socket is sunk and oversized; the old dot sat on the surface.
        mesh.ellipsoid(tuple(socket + np.array((0., 0., skull[2] * .06))),
                       (eye * 3.2, eye * 2.9, eye * 2.2),
                       [head_i], MAT_DARK, rings=6, sides=10)
        if p["face"] == "ember":
            mesh.ellipsoid(tuple(socket + np.array((0., 0., -eye * .30))),
                           (eye * 1.5, eye * 1.4, eye * 1.0),
                           [head_i], MAT_CORE, rings=6, sides=9)
        else:
            mesh.ellipsoid(tuple(socket + np.array((0., 0., -eye * .45))),
                           (eye * 1.25, eye * 1.15, eye * .85),
                           [head_i], MAT_FEATURE, rings=5, sides=9)
        if p["wood"]:
            # A treant's brow is a bark ridge over the socket, which is what
            # gives the lit eye something to be sunk into.
            brow_ridge = socket + np.array((0., eye * 2.0, -eye * .30))
            mesh.tube([brow_ridge + np.array((-eye * 2.0, -eye * .5, 0.)),
                       brow_ridge, brow_ridge + np.array((eye * 2.0, -eye * .9, 0.))],
                      [(eye * .40, eye * .40), (eye * .70, eye * .70),
                       (eye * .40, eye * .40)], [head_i], MAT_BODY, sides=5)
        # Cheekbone: the plane that separates a face from the side of a head.
        mesh.ellipsoid(tuple(g[head_i] + np.array((side * skull[0] * .58,
                                                   -skull[1] * .10,
                                                   -skull[2] * .30))),
                       (skull[0] * .34, skull[1] * .26, skull[2] * .40),
                       [head_i], face_mat, rings=5, sides=9)
    # Nose bridge and brow spine, running down out of the brow ridge.
    bridge_top = g[head_i] + np.array((0., skull[1] * .28, -skull[2] * .52))
    bridge_low = g[head_i] + np.array((0., -skull[1] * .10, -skull[2] * .70))
    mesh.tube([bridge_top, (bridge_top + bridge_low) * .5, bridge_low],
              [(skull[0] * .17, skull[1] * .14), (skull[0] * .15, skull[1] * .13),
               (skull[0] * .20, skull[1] * .12)],
              [head_i], face_mat, sides=7)
    # Mouth: a dark line, deeper on a skull.
    mouth = g[head_i] + np.array((0., -skull[1] * .40, -skull[2] * .58))
    mesh.tube([mouth + np.array((-skull[0] * .34, 0., 0.)),
               mouth + np.array((0., -skull[1] * .04, -skull[2] * .04)),
               mouth + np.array((skull[0] * .34, 0., 0.))],
              [(skull[0] * .05, skull[1] * .05),
               (skull[0] * .09, skull[1] * .08 * (1.8 if pale else 1.0)),
               (skull[0] * .05, skull[1] * .05)],
              [head_i, jaw_i], MAT_DARK, sides=6)
    if p["wood"]:
        # A gash of a mouth, and bark strands running down over the skull so
        # the head belongs to the same grown thing as the trunk.
        jawline = g[head_i] + np.array((0., -skull[1] * .44, -skull[2] * .52))
        mesh.tube([jawline + np.array((-skull[0] * .46, 0., 0.)),
                   jawline + np.array((0., -skull[1] * .10, -skull[2] * .06)),
                   jawline + np.array((skull[0] * .46, 0., 0.))],
                  [(skull[0] * .05, skull[1] * .05),
                   (skull[0] * .10, skull[1] * .09),
                   (skull[0] * .05, skull[1] * .05)],
                  [head_i, jaw_i], MAT_DARK, sides=5)
        for k in range(7):
            angle = 2 * math.pi * k / 7 + .22
            top = g[head_i] + np.array((math.cos(angle) * skull[0] * .70,
                                        skull[1] * .72,
                                        math.sin(angle) * skull[2] * .70))
            low = g[head_i] + np.array((math.cos(angle) * skull[0] * .96,
                                        -skull[1] * .62,
                                        math.sin(angle) * skull[2] * .96))
            mesh.tube([top, (top + low) * .5, low],
                      [(skull[0] * .07, skull[0] * .07),
                       (skull[0] * .11, skull[0] * .11),
                       (skull[0] * .06, skull[0] * .06)],
                      [head_i, neck_i], MAT_BODY, sides=5)
    if p["beard"]:
        mesh.ellipsoid(tuple(g[jaw_i] + np.array((0., -p["beard"] * s * .5,
                                                  -skull[2] * .30))),
                       (skull[0] * .82, p["beard"] * s * 2.0, skull[2] * .70),
                       [jaw_i, head_i], MAT_ACCENT, rings=7, sides=12)

    # ---- arms -------------------------------------------------------------
    # Anything that grows on a standing figure grows on its shoulders and arms
    # too; a trunk-only growth spine leaves a moss troll with a mossy back and
    # bare limbs, which is the opposite of what the art shows.
    mesh.growth_extra = []
    for side, sign in (("l", -1.), ("r", 1.)):
        sh, el = g[B[f"upper_arm_{side}"]], g[B[f"forearm_{side}"]]
        hd = g[B[f"hand_{side}"]]
        arm_bones = [chest_i, B[f"shoulder_{side}"], B[f"upper_arm_{side}"],
                     B[f"forearm_{side}"], B[f"hand_{side}"]]
        r = p["arm_r"] * s
        mesh.growth_extra.append((
            [sh, sh * .5 + el * .5, el, el * .45 + hd * .55],
            [(r * 2.0, r * 2.0), (r * 1.15, r * 1.15), (r * 1.0, r * 1.0),
             (r * .86, r * .86)], arm_bones))
        inboard = sh + np.array((-sign * r * 1.1, .03 * s, 0.))
        arm_line = [inboard, sh, sh * .55 + el * .45, el, el * .45 + hd * .55, hd]
        arm_radii = [(r * 1.34, r * 1.34), (r * 1.24, r * 1.24), (r * 1.02, r * 1.02),
                     (r * .90, r * .90), (r * .82, r * .82), (r * .78, r * .78)]
        if p["wood"]:
            # Thicker, and stranded like the trunk, so the arm belongs to the
            # same grown mass instead of being a pipe screwed into it.
            heavy = [(rx * 1.46, ry * 1.46) for rx, ry in arm_radii]
            woven_trunk(mesh, arm_line, heavy, arm_bones, MAT_BODY,
                        seed=f"{variant or plan_key}:arm:{side}", strands=7,
                        twist=1.10, inset=.10, bulge=1.05, thickness=1.30,
                        material_inner=MAT_BODY, inner_scale=.76)
        else:
            mesh.tube(arm_line, arm_radii, arm_bones, MAT_BODY, sides=10,
                      cap_start=False, cap_end=False)
        if p["plated"]:
            plated_shell(mesh, arm_line, arm_radii, arm_bones, MAT_BODY,
                         seed=f"{variant or plan_key}:arm:{side}",
                         rows=2, around=3,
                         relief=.54 * p["plated"], gap=.07, dome=.70,
                         rune_material=MAT_CORE if p["runes"] else None,
                         rune_chance=p["runes"] * .45, span=(.16, .94), shape=p["plate_shape"])
        if p["bands"]:
            # Metal at the wrist and the top of the arm, which is where every
            # one of these figures is banded in the art.
            band = p["bands"]
            metal_band(mesh, (el + hd) * .5, hd - el, r * 1.02, arm_bones,
                       MAT_ACCENT, thickness=.16 * band, flare=1.34)
            metal_band(mesh, sh * .70 + el * .30, el - sh, r * 1.28, arm_bones,
                       MAT_ACCENT, thickness=.13 * band, flare=1.28)
        ball = 2.9 * (1.30 if p["wood"] else 1.0)
        mesh.ellipsoid(tuple(sh + np.array((0., .02 * s, 0.))),
                       (r * ball, r * ball * .93, r * ball * .93),
                       [B[f"shoulder_{side}"], B[f"upper_arm_{side}"], chest_i],
                       MAT_BODY, rings=8, sides=12)
        palm = hd + np.array((0., -r * 1.1, 0.))
        if p["knuckle"]:
            palm[1] = max(palm[1], r * 1.25)
        mesh.ellipsoid(tuple(palm), (r * 1.9, r * 2.2, r * 1.5),
                       [B[f"hand_{side}"], B[f"forearm_{side}"]], MAT_BODY,
                       rings=7, sides=10)
        if p["wood"]:
            # A treant has twigs, not fingers: the hand keeps forking until it
            # runs out, which is most of what reads as "tree" in silhouette.
            twigs = branch_system(
                mesh, palm + np.array((0., -r * .8, 0.)),
                np.array((sign * .48, -.78, -.34)), r * 1.9, r * .34,
                [B[f"hand_{side}"], B[f"forearm_{side}"]], MAT_BODY,
                seed=f"{variant or plan_key}:twig:{side}", depth=2, splits=3,
                spread=.74, gnarl=.34, up_bias=-.30, segments=2, sides=5)
            if p["canopy"]:
                for index, (tip, tip_r, _) in enumerate(twigs[::2]):
                    foliage_cluster(mesh, tip, r * 1.3 * p["canopy"],
                                    [B[f"hand_{side}"], B[f"forearm_{side}"]],
                                    MAT_GROWTH,
                                    seed=f"{variant or plan_key}:hand:{side}:{index}",
                                    count=4)
        else:
            # Fingers read as a hand rather than a mitten.
            knuckles = min(int(p["digit"]), 4)
            for k in range(knuckles):
                offset = (k - 1.5) * r * .58
                base = palm + np.array((offset, -r * 1.1, -r * .2))
                mesh.tube([palm + np.array((offset, -r * .5, -r * .1)), base],
                          [(r * .30, r * .30), (r * .22, r * .22)],
                          [B[f"hand_{side}"]], MAT_BODY, sides=5)
                if p["plated"]:
                    # A stone fist is a bunch of blocks, and these hands are
                    # the second thing the eye goes to after the chest.
                    mesh.ellipsoid(tuple(palm + np.array((offset, -r * .62,
                                                          -r * .34))),
                                   (r * .52, r * .50, r * .60),
                                   [B[f"hand_{side}"]], MAT_BODY,
                                   rings=4, sides=5)
        if p["pauldron"]:
            # A stack of overlapping slabs, each wider than the one above it.
            # Every armoured figure in this group is drawn with one, and it is
            # most of what makes the shoulders read as heavy; a single squashed
            # ellipsoid is a shoulder pad on a sports jersey.
            pad = max(p["shoulder_pad"], p["arm_r"] * 1.15) * s
            stack = max(2, int(p["pauldron"]) - 1)
            for k in range(stack):
                t = k / max(stack - 1, 1)
                # Each slab sits lower and further out than the one above, so
                # the stack sheds down the arm.  Spread flat and wide they read
                # as a sun hat brim rather than as shoulder armour.
                seat = sh + np.array((sign * pad * (.20 + .52 * t),
                                      pad * (.46 - 1.02 * t),
                                      -pad * .06 + pad * .16 * t))
                spread = 1.0 - .15 * k
                mesh.ellipsoid(tuple(seat),
                               (pad * 1.62 * spread, pad * 1.10 * spread,
                                pad * 1.70 * spread),
                               [B[f"shoulder_{side}"], B[f"upper_arm_{side}"],
                                chest_i], MAT_BODY, rings=6, sides=10,
                               squash=.82)
        elif p["shoulder_pad"]:
            pad = p["shoulder_pad"] * s
            mesh.ellipsoid(tuple(sh + np.array((sign * pad * .18, pad * .34, 0.))),
                           (pad * 2.0, pad * 1.5, pad * 2.1),
                           [B[f"shoulder_{side}"], chest_i], MAT_FEATURE,
                           rings=8, sides=12, squash=.72)
        if p["gaunt"]:
            mesh.ellipsoid(tuple((el + hd) * .5),
                           (r * 1.7, p["gaunt"] * s * 4.0, r * 1.7),
                           [B[f"forearm_{side}"]], MAT_FEATURE, rings=6, sides=10)

    # ---- legs and feet ----------------------------------------------------
    for side in ("l", "r"):
        hip = g[B[f"thigh_{side}"]]
        knee = g[B[f"shin_{side}"]]
        foot = g[B[f"foot_{side}"]]
        leg_bones = [body_i, B[f"thigh_{side}"], B[f"shin_{side}"], B[f"foot_{side}"]]
        lr = p["leg_r"] * s
        foot_len = p["foot_len"] * s
        if not p["robe"]:
            mesh.tube([hip + np.array((0., .05 * s, 0.)), hip * .5 + knee * .5, knee,
                       knee * .45 + foot * .55,
                       np.array((foot[0], foot_len * .30, foot[2]))],
                      [(lr * 1.35, lr * 1.35), (lr * 1.10, lr * 1.10),
                       (lr * .92, lr * .92), (lr * .80, lr * .80), (lr * .74, lr * .74)],
                      leg_bones, MAT_BODY, sides=10, cap_start=False, cap_end=False)
        if p["plated"]:
            leg_line = [hip + np.array((0., .05 * s, 0.)), hip * .5 + knee * .5,
                        knee, knee * .45 + foot * .55,
                        np.array((foot[0], foot_len * .30, foot[2]))]
            leg_radii = [(lr * 1.35, lr * 1.35), (lr * 1.10, lr * 1.10),
                         (lr * .92, lr * .92), (lr * .80, lr * .80),
                         (lr * .74, lr * .74)]
            plated_shell(mesh, leg_line, leg_radii, leg_bones, MAT_BODY,
                         seed=f"{variant or plan_key}:leg:{side}",
                         rows=2, around=3,
                         relief=.52 * p["plated"], gap=.07, dome=.70,
                         rune_material=MAT_CORE if p["runes"] else None,
                         rune_chance=p["runes"] * .38, span=(.12, .90), shape=p["plate_shape"])
            if p["bands"]:
                metal_band(mesh, knee * .35 + foot * .65, foot - knee,
                           lr * .80, leg_bones, MAT_ACCENT,
                           thickness=.16 * p["bands"], flare=1.30)
        heel = np.array((foot[0], foot_len * .26, foot[2] + foot_len * .24))
        toe = np.array((foot[0], foot_len * .20, foot[2] - foot_len * .72))
        mesh.tube([heel, (heel + toe) * .5, toe],
                  [(lr * .92, foot_len * .26), (lr * 1.02, foot_len * .22),
                   (lr * .80, foot_len * .16)],
                  [B[f"foot_{side}"], B[f"shin_{side}"]], MAT_BODY, sides=10)
        if p["wood"]:
            # Roots splay where a foot would have toes, and the shin is a
            # bundle of strands rather than one turned column.
            root_flare(mesh, np.array((foot[0], foot_len * .40, foot[2])),
                       lr * 2.4, [B[f"foot_{side}"], B[f"shin_{side}"]],
                       MAT_BODY, seed=f"{variant or plan_key}:root:{side}",
                       count=7, reach=1.15)
            shin = [hip + np.array((0., .05 * s, 0.)), hip * .5 + knee * .5, knee,
                    np.array((foot[0], foot_len * .40, foot[2]))]
            woven_trunk(mesh, shin,
                        [(lr * 1.72, lr * 1.72), (lr * 1.44, lr * 1.44),
                         (lr * 1.28, lr * 1.28), (lr * 1.18, lr * 1.18)],
                        leg_bones, MAT_BODY,
                        seed=f"{variant or plan_key}:leg:{side}",
                        strands=7, twist=.85, inset=.10, bulge=1.05,
                        thickness=1.05, material_inner=MAT_BODY, inner_scale=.74)

    # ---- garments ---------------------------------------------------------
    if p["robe"]:
        # A robe in the art flares from the waist, breaks into vertical folds
        # and ends in a shaped hem.  Swept as one straight tube with a disc on
        # the bottom it read as a lampshade, which is what every mage, monarch
        # and revenant in the library was standing in.
        drop = p["hip_h"] * s * (1.0 - p["robe_len"]) * .78
        hem = np.array((0., p["foot_len"] * s * .16 + drop, 0.))
        waist = g[body_i] + np.array((0., hip_r[1] * .55, 0.))
        flare = (1.62 if p["hem"] != "straight" else 1.46) * p["robe_flare"]
        skirt = [waist, waist * .62 + hem * .38, waist * .28 + hem * .72, hem]
        mesh.tube(skirt,
                  [(hip_r[0] * .98, hip_r[1] * .98),
                   (hip_r[0] * 1.12, hip_r[1] * 1.10),
                   (hip_r[0] * 1.38, hip_r[1] * 1.34),
                   (hip_r[0] * flare, hip_r[1] * flare)],
                  [body_i, spine_i], MAT_ACCENT, sides=18,
                  cap_start=False, cap_end=False)
        mesh.ellipsoid((0., hem[1] + hip_r[1] * .10, 0.),
                       (hip_r[0] * flare * 1.98, hip_r[1] * .40,
                        hip_r[1] * flare * 1.94),
                       [body_i], MAT_ACCENT, rings=6, sides=16)
        # Folds, and a hem that dips between them.
        folds = 11
        for k in range(folds):
            angle = 2 * math.pi * k / folds
            out = np.array((math.cos(angle), 0., math.sin(angle)))
            top = waist + out * hip_r[0] * .96
            mid = (waist * .40 + hem * .60) + out * hip_r[0] * 1.30
            low = hem + out * hip_r[0] * flare * 1.04
            drop = 0.0 if p["hem"] == "straight" else hip_r[1] * (
                .34 if k % 2 else .10)
            mesh.tube([top, mid, low - np.array((0., drop, 0.))],
                      [(hip_r[0] * .085, hip_r[0] * .085),
                       (hip_r[0] * .105, hip_r[0] * .105),
                       (hip_r[0] * .070, hip_r[0] * .070)],
                      [body_i, spine_i], MAT_ACCENT, sides=5)
            if p["canopy"]:
                # A dryad's gown is layered leaves, not cloth; the art gives
                # her no fabric at all.
                for along, size in ((.34, .78), (.68, 1.0), (1.0, .86)):
                    seat = mid * (1 - along) + low * along
                    foliage_cluster(mesh, seat - np.array((0., drop * along, 0.)),
                                    hip_r[0] * .30 * p["canopy"] * size,
                                    [body_i, spine_i], MAT_GROWTH,
                                    seed=f"{variant or plan_key}:gown:{k}:{along}",
                                    count=3, flatten=.48)
        for side in ("l", "r"):
            sh, el = g[B[f"upper_arm_{side}"]], g[B[f"forearm_{side}"]]
            r = p["arm_r"] * s
            mesh.tube([sh + np.array((0., r * .6, 0.)), (sh + el) * .5],
                      [(r * 2.0, r * 2.0), (r * 1.5, r * 1.5)],
                      [B[f"shoulder_{side}"], B[f"upper_arm_{side}"], chest_i],
                      MAT_ACCENT, sides=10, cap_start=False, cap_end=False)
    if p["cloak"]:
        top = spine_pts[-1] + np.array((0., -.02 * s, chest_r[1] * 1.22))
        drop = p["cloak"] * s * 1.5
        cloak_bones = [chest_i, B["cloak_1"], B["cloak_2"], spine_i]
        # Two panels hanging off the shoulders, narrowing as they fall, rather
        # than one wide plate across the whole back.
        for sign in (-1., 1.):
            outer = [top + np.array((sign * chest_r[0] * .96, .04 * s, -chest_r[1] * .30)),
                     top + np.array((sign * chest_r[0] * .90, -drop * .50, chest_r[1] * .30)),
                     top + np.array((sign * chest_r[0] * .62, -drop, chest_r[1] * .55))]
            inner = [top + np.array((sign * chest_r[0] * .10, .02 * s, -chest_r[1] * .20)),
                     top + np.array((sign * chest_r[0] * .12, -drop * .50, chest_r[1] * .22)),
                     top + np.array((sign * chest_r[0] * .10, -drop, chest_r[1] * .42))]
            _sheet(mesh, [_bezier(outer, t) for t in np.linspace(0, 1, 7)],
                   [_bezier(inner, t) for t in np.linspace(0, 1, 7)],
                   .010 * s, cloak_bones, MAT_ACCENT)
    if p["ragged"]:
        for k in range(11):
            angle = 2 * math.pi * k / 11
            rx = math.cos(angle) * hip_r[0] * 1.5
            rz = math.sin(angle) * hip_r[1] * 1.5
            top = np.array((rx * .7, p["hip_h"] * s * .95, rz * .7))
            mesh.tube([top, np.array((rx, p["ragged"] * s * .5, rz))],
                      [(.030 * s, .014 * s), (.014 * s, .007 * s)],
                      [body_i, spine_i], MAT_ACCENT, sides=5)
    if p["mane"]:
        seat = spine_pts[-1] + np.array((0., .03 * s, .02 * s))
        mesh.ellipsoid(tuple(seat),
                       (chest_r[0] * 2.0, p["mane"] * s * 2.4, chest_r[1] * 1.9),
                       [chest_i, neck_i], MAT_ACCENT, rings=8, sides=14)
        # A second, deeper lobe behind the first rather than a fringe of
        # hanging locks: on an upright chest those radiate off the shoulders
        # as dark spikes instead of hanging, which is what they do on a neck.
        mane = p["mane"] * s
        mesh.ellipsoid(tuple(seat + np.array((0., -mane * .55, mane * .30))),
                       (chest_r[0] * 2.25, mane * 1.9, chest_r[1] * 2.05),
                       [chest_i, neck_i], MAT_ACCENT, rings=8, sides=14)
    if p["bark"] and not p["wood"]:
        for k in range(7):
            t = .12 + .74 * k / 6
            index = min(int(t * (len(spine_pts) - 1)), len(spine_pts) - 2)
            point = spine_pts[index]
            angle = 2 * math.pi * k / 7
            r = chest_r[0] * 1.02
            base = point + np.array((math.cos(angle) * r, 0., math.sin(angle) * r))
            mesh.tube([base, base + np.array((math.cos(angle) * .05 * s, .11 * s,
                                              math.sin(angle) * .05 * s))],
                      [(.032 * s, .024 * s), (.016 * s, .012 * s)],
                      torso_bones, MAT_FEATURE, sides=6)
    if p["horns"]:
        for side in (-1., 1.):
            root = g[head_i] + np.array((side * skull[0] * .60, skull[1] * .30, 0.))
            if p["horns"] == "bull":
                mesh.tube([root, root + np.array((side * .17 * s, .05 * s, -.03 * s)),
                           root + np.array((side * .22 * s, .18 * s, -.12 * s))],
                          [(.048 * s, .046 * s), (.032 * s, .030 * s),
                           (.008 * s, .008 * s)], [head_i], MAT_FEATURE, sides=9)
            else:  # crag: jagged mineral spurs
                for k in range(3):
                    base = root + np.array((side * .02 * s * k, .03 * s * k, .04 * s * k))
                    mesh.spike(base, base + np.array((side * .09 * s, .13 * s,
                                                      -.03 * s)),
                               .026 * s, [head_i], MAT_FEATURE, sides=5)
    if p["crown"]:
        # A real rack.  The art's crown is *wide and low* -- it spreads to about
        # twice the shoulder span while rising barely half a head -- so the
        # limbs lean hard outward and are only gently lifted.  They are bark,
        # not keratin: routing them through MAT_FEATURE painted every treant a
        # set of bone-white antlers.
        crown = p["crown"]
        crown_bones = [head_i, neck_i]
        for side in (-1., 1.):
            for index, (out, back, lift) in enumerate(
                    ((1.00, .34, .62), (1.00, -.30, .48), (.62, -.70, .55),
                     (.54, .62, .70))):
                base = g[head_i] + np.array((side * skull[0] * .46,
                                             skull[1] * .52,
                                             back * skull[2] * .55))
                tips = branch_system(
                    mesh, base, np.array((side * out, lift, back)),
                    .27 * s * crown, .040 * s * crown, crown_bones, MAT_BODY,
                    seed=f"{variant or plan_key}:crown:{side:+.0f}:{index}",
                    depth=2, splits=3, spread=.72,
                    gnarl=.34, taper=.52, shorten=.72, up_bias=.06,
                    segments=3, sides=6)
                if p["canopy"]:
                    # Leaf mass is the most expensive thing on a treant, and it
                    # buys nothing past the point where the clusters overlap.
                    # A sapling sprite carried a full hero canopy -- thirty-four
                    # thousand triangles on a creature two-thirds of a metre
                    # tall -- so the crown thins with the creature.
                    stride = 1 if crown >= .9 else 2
                    for k, (tip, tip_r, _) in enumerate(tips[::stride]):
                        foliage_cluster(
                            mesh, tip,
                            .085 * s * p["canopy"] * (1.0 + .55 * (stride - 1)),
                            crown_bones,
                            MAT_GROWTH,
                            seed=f"{variant or plan_key}:crownleaf:{side:+.0f}:{index}:{k}",
                            count=4)
    _headgear(mesh, p["crest"], g[head_i], skull, head_i, s, p, neck_i)
    if p["hood"]:
        _headgear(mesh, "hood", g[head_i], skull, head_i, s, p, neck_i)

    # ---- held equipment ---------------------------------------------------
    if p["weapon"]:
        grip = g[B["prop_r"]]
        forward = np.array((0., 0., -1.))
        up = np.array((0., 1., 0.))
        _weapon(mesh, p["weapon"], grip, forward, up, 1.0, s,
                [B["prop_r"], B["hand_r"], B["forearm_r"]])
    if p["orb"]:
        # A sphere of cold light cupped in the off hand, which is half of what
        # the drowned king is doing in the art.
        orb = p["orb"] * s
        centre = g[B["hand_l"]] + np.array((0., -orb * .55, -orb * .30))
        bones = [B["prop_l"], B["hand_l"], B["forearm_l"]]
        mesh.ellipsoid(tuple(centre), (orb * .82,) * 3, bones, MAT_CORE,
                       rings=9, sides=13)
        for k in range(6):
            angle = 2 * math.pi * k / 6
            arc = []
            for j in range(9):
                t = j / 8.0
                arc.append(centre + np.array((
                    math.cos(angle) * math.sin(math.pi * t) * orb * .62,
                    math.cos(math.pi * t) * orb * .62,
                    math.sin(angle) * math.sin(math.pi * t) * orb * .62)))
            mesh.tube(arc, [(orb * .045, orb * .045)] * 9, bones, MAT_ACCENT,
                      sides=4, cap_start=False, cap_end=False)
    if p["shield"]:
        centre = g[B["hand_l"]] + np.array((0., -p["arm_r"] * s * 1.2,
                                            -p["arm_r"] * s * 2.2))
        bones = [B["prop_l"], B["hand_l"], B["forearm_l"]]
        if p["shield"] == "kite":
            mesh.ellipsoid(tuple(centre + np.array((0., .06 * s, 0.))),
                           (.26 * s, .40 * s, .05 * s), bones, MAT_FEATURE,
                           rings=8, sides=12)
        else:
            mesh.ellipsoid(tuple(centre), (.30 * s, .30 * s, .05 * s), bones,
                           MAT_FEATURE, rings=8, sides=14)
        mesh.ellipsoid(tuple(centre + np.array((0., .04 * s, -.035 * s))),
                       (.07 * s, .07 * s, .04 * s), bones, MAT_DARK, rings=5, sides=8)
    return mesh


def biped_animation(plan_key: str, scale: float, bones,
                    variant: str | None = None) -> dict:
    """The seven runtime clips for an upright body plan."""
    p = biped_config(plan_key, variant)
    gait = BIPED_GAITS.get(plan_key, "walk")
    B = BIPED_INDEX
    clips: dict[str, dict] = {}
    heavy = gait in ("heavy", "knuckle")

    def bake(times, tracks):
        out = {}
        for (node, path), values in tracks.items():
            out[(node, path)] = (path, list(times), list(values))
        return out

    # ---- idle: breathing, weight shift, arms hanging with life ----------
    n = 16
    times = [2.6 * i / n for i in range(n + 1)]
    wave = [math.sin(2 * math.pi * i / n) for i in range(n + 1)]
    slow = [math.sin(math.pi * i / n) for i in range(n + 1)]
    idle = {(B["root"], "translation"): [[0., .008 * scale * w, 0.] for w in wave],
            (B["body"], "rotation"): [_euler(roll=.020 * sl) for sl in slow],
            (B["chest"], "rotation"): [_euler(pitch=.024 * w, roll=-.014 * sl)
                                       for w, sl in zip(wave, slow)],
            (B["spine"], "rotation"): [_euler(pitch=.018 * w, roll=-.012 * sl)
                                       for w, sl in zip(wave, slow)],
            (B["neck"], "rotation"): [_euler(pitch=-.026 * w) for w in wave],
            (B["head"], "rotation"): [_euler(pitch=.020 * w, yaw=.060 * sl)
                                      for w, sl in zip(wave, slow)],
            (B["cloak_1"], "rotation"): [_euler(pitch=.030 * w, roll=.018 * sl)
                                         for w, sl in zip(wave, slow)],
            (B["cloak_2"], "rotation"): [_euler(pitch=.045 * w) for w in wave]}
    for side, sign in (("l", -1.), ("r", 1.)):
        idle[(B[f"upper_arm_{side}"], "rotation")] = [
            _euler(pitch=.05 * w, roll=sign * (.06 + .03 * sl))
            for w, sl in zip(wave, slow)]
        idle[(B[f"forearm_{side}"], "rotation")] = [_euler(pitch=-.10 - .05 * w)
                                                    for w in wave]
    clips["Idle_A"] = bake(times, idle)

    # ---- locomotion ----------------------------------------------------
    def locomotion(duration, samples, swing, lift, bob, arm):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]

        def put(node, path, value):
            tracks.setdefault((node, path), []).append(value)

        for i in range(samples + 1):
            u = i / samples
            cycle = 2 * math.pi * u
            put(B["root"], "translation",
                [0., bob * scale * abs(math.sin(cycle)) * (1.0 if not heavy else .8), 0.])
            put(B["body"], "rotation", _euler(roll=.05 * math.sin(cycle),
                                              yaw=.09 * math.sin(cycle)))
            put(B["spine"], "rotation", _euler(pitch=(.06 if heavy else .02),
                                               yaw=-.07 * math.sin(cycle),
                                               roll=-.03 * math.sin(cycle)))
            put(B["chest"], "rotation", _euler(pitch=(.10 if heavy else .04),
                                               yaw=-.14 * math.sin(cycle)))
            put(B["cloak_1"], "rotation",
                _euler(pitch=-.10 - .07 * math.sin(cycle + 1.0)))
            put(B["cloak_2"], "rotation",
                _euler(pitch=-.14 - .10 * math.sin(cycle + 1.6)))
            put(B["neck"], "rotation", _euler(pitch=-.06 * math.sin(2 * cycle)))
            put(B["head"], "rotation", _euler(pitch=.05 * math.sin(2 * cycle),
                                              yaw=.05 * math.sin(cycle)))
            for side, phase, sign in (("l", 0.0, -1.), ("r", .5, 1.)):
                leg = math.sin(cycle - 2 * math.pi * phase)
                knee = max(0., math.sin(cycle - 2 * math.pi * phase + math.pi * .40))
                put(B[f"thigh_{side}"], "rotation", _euler(pitch=swing * leg))
                put(B[f"shin_{side}"], "rotation", _euler(pitch=-lift * knee))
                put(B[f"foot_{side}"], "rotation",
                    _euler(pitch=-swing * leg * .35 + lift * knee * .55))
                # Arms swing opposite the leg on the same side.
                if p["knuckle"]:
                    put(B[f"upper_arm_{side}"], "rotation",
                        _euler(pitch=arm * -leg * .8 + .30, roll=sign * .10))
                    put(B[f"forearm_{side}"], "rotation", _euler(pitch=-.22))
                else:
                    put(B[f"upper_arm_{side}"], "rotation",
                        _euler(pitch=arm * -leg, roll=sign * .07))
                    put(B[f"forearm_{side}"], "rotation",
                        _euler(pitch=-.18 - .22 * max(0., -leg)))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    if heavy:
        clips["Walk"] = locomotion(1.15, 16, .30, .38, .022, .22)
        clips["Jog"] = locomotion(.74, 14, .46, .58, .040, .34)
    else:
        clips["Walk"] = locomotion(1.0, 16, .40, .52, .026, .34)
        clips["Jog"] = locomotion(.62, 14, .60, .74, .048, .52)

    # ---- combat idle: guard stance --------------------------------------
    n = 14
    times = [1.5 * i / n for i in range(n + 1)]
    wave = [math.sin(2 * math.pi * i / n) for i in range(n + 1)]
    fight = {(B["root"], "translation"): [[0., .006 * scale * w, 0.] for w in wave],
             (B["body"], "rotation"): [_euler(yaw=.20, roll=.03 * w) for w in wave],
             (B["chest"], "rotation"): [_euler(pitch=.10, yaw=-.14) for _ in wave],
             (B["neck"], "rotation"): [_euler(pitch=-.10) for _ in wave],
             (B["head"], "rotation"): [_euler(pitch=.06, yaw=.16) for _ in wave],
             (B["thigh_l"], "rotation"): [_euler(pitch=.20) for _ in wave],
             (B["shin_l"], "rotation"): [_euler(pitch=-.30) for _ in wave],
             (B["thigh_r"], "rotation"): [_euler(pitch=-.16) for _ in wave],
             (B["shin_r"], "rotation"): [_euler(pitch=-.22) for _ in wave],
             (B["upper_arm_l"], "rotation"): [_euler(pitch=-.50 + .05 * w, roll=-.30)
                                              for w in wave],
             (B["forearm_l"], "rotation"): [_euler(pitch=-.95 - .06 * w) for w in wave],
             (B["upper_arm_r"], "rotation"): [_euler(pitch=-.34 + .05 * w, roll=.24)
                                              for w in wave],
             (B["forearm_r"], "rotation"): [_euler(pitch=-.80 - .06 * w) for w in wave]}
    clips["Fighting_Idle"] = bake(times, fight)

    # ---- attack: wind up, strike at ~55%, recover ------------------------
    stamp = [0., .16, .30, .44, .58, .74, .92]
    swing = {
        (B["root"], "translation"): [[0., 0., 0.], [0., -.014 * scale, 0.],
                                     [0., .010 * scale, 0.], [0., .014 * scale, 0.],
                                     [0., .004 * scale, 0.], [0., -.006 * scale, 0.],
                                     [0., 0., 0.]],
        (B["body"], "rotation"): [_euler(), _euler(yaw=.30), _euler(yaw=.10),
                                  _euler(yaw=-.34), _euler(yaw=-.24),
                                  _euler(yaw=-.06), _euler()],
        (B["spine"], "rotation"): [_euler(), _euler(yaw=.22, pitch=-.05),
                                   _euler(yaw=.04), _euler(yaw=-.28, pitch=.10),
                                   _euler(yaw=-.18, pitch=.05), _euler(yaw=-.04),
                                   _euler()],
        (B["cloak_1"], "rotation"): [_euler(), _euler(pitch=-.24, yaw=.20),
                                     _euler(pitch=-.10), _euler(pitch=.26, yaw=-.24),
                                     _euler(pitch=.16), _euler(pitch=.04), _euler()],
        (B["cloak_2"], "rotation"): [_euler(), _euler(pitch=-.32), _euler(pitch=-.14),
                                     _euler(pitch=.34), _euler(pitch=.20),
                                     _euler(pitch=.06), _euler()],
        (B["chest"], "rotation"): [_euler(), _euler(yaw=.34, pitch=-.08),
                                   _euler(yaw=.06), _euler(yaw=-.42, pitch=.14),
                                   _euler(yaw=-.28, pitch=.08), _euler(yaw=-.06),
                                   _euler()],
        (B["neck"], "rotation"): [_euler(), _euler(yaw=-.14), _euler(yaw=-.04),
                                  _euler(yaw=.16, pitch=.10), _euler(yaw=.10),
                                  _euler(), _euler()],
        (B["head"], "rotation"): [_euler(), _euler(yaw=-.18), _euler(),
                                  _euler(yaw=.14, pitch=.08), _euler(yaw=.08),
                                  _euler(), _euler()],
        (B["upper_arm_r"], "rotation"): [_euler(pitch=-.10),
                                         _euler(pitch=-1.30, roll=.40),
                                         _euler(pitch=-.90, roll=.24),
                                         _euler(pitch=.55, roll=-.16),
                                         _euler(pitch=.30, roll=-.08),
                                         _euler(pitch=-.05), _euler(pitch=-.10)],
        (B["forearm_r"], "rotation"): [_euler(pitch=-.30), _euler(pitch=-1.05),
                                       _euler(pitch=-.70), _euler(pitch=-.12),
                                       _euler(pitch=-.24), _euler(pitch=-.30),
                                       _euler(pitch=-.30)],
        (B["upper_arm_l"], "rotation"): [_euler(pitch=-.10),
                                         _euler(pitch=.24, roll=-.20),
                                         _euler(pitch=.10, roll=-.12),
                                         _euler(pitch=-.55, roll=-.30),
                                         _euler(pitch=-.34, roll=-.20),
                                         _euler(pitch=-.10), _euler(pitch=-.10)],
        (B["forearm_l"], "rotation"): [_euler(pitch=-.30), _euler(pitch=-.44),
                                       _euler(pitch=-.40), _euler(pitch=-.86),
                                       _euler(pitch=-.60), _euler(pitch=-.34),
                                       _euler(pitch=-.30)],
        (B["thigh_l"], "rotation"): [_euler(), _euler(pitch=.16), _euler(pitch=.10),
                                     _euler(pitch=-.20), _euler(pitch=-.12),
                                     _euler(), _euler()],
        (B["thigh_r"], "rotation"): [_euler(), _euler(pitch=-.14), _euler(pitch=-.06),
                                     _euler(pitch=.24), _euler(pitch=.14),
                                     _euler(), _euler()],
        (B["shin_l"], "rotation"): [_euler(), _euler(pitch=-.20), _euler(pitch=-.14),
                                    _euler(pitch=-.10), _euler(pitch=-.08),
                                    _euler(), _euler()],
        (B["shin_r"], "rotation"): [_euler(), _euler(pitch=-.10), _euler(pitch=-.08),
                                    _euler(pitch=-.30), _euler(pitch=-.20),
                                    _euler(), _euler()],
    }
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in swing.items()}

    # ---- hit reaction ----------------------------------------------------
    hit_t = [0., .09, .20, .34, .50]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in {
        (B["root"], "translation"): [[0., 0., 0.], [0., -.018 * scale, 0.],
                                     [0., -.010 * scale, 0.], [0., -.004 * scale, 0.],
                                     [0., 0., 0.]],
        (B["body"], "rotation"): [_euler(), _euler(pitch=.22, roll=.12),
                                  _euler(pitch=.14, roll=.07), _euler(pitch=-.04),
                                  _euler()],
        (B["chest"], "rotation"): [_euler(), _euler(pitch=.30, yaw=.18),
                                   _euler(pitch=.18, yaw=.10), _euler(pitch=-.06),
                                   _euler()],
        (B["neck"], "rotation"): [_euler(), _euler(pitch=.34), _euler(pitch=.20),
                                  _euler(pitch=-.06), _euler()],
        (B["head"], "rotation"): [_euler(), _euler(pitch=.30, yaw=.20),
                                  _euler(pitch=.18), _euler(pitch=-.04), _euler()],
        (B["upper_arm_l"], "rotation"): [_euler(), _euler(pitch=-.40, roll=-.30),
                                         _euler(pitch=-.24), _euler(pitch=-.06),
                                         _euler()],
        (B["upper_arm_r"], "rotation"): [_euler(), _euler(pitch=-.34, roll=.28),
                                         _euler(pitch=-.20), _euler(pitch=-.05),
                                         _euler()],
    }.items()}

    # ---- death: legs give way, body folds and settles --------------------
    death_t = [0., .26, .52, .82, 1.10, 1.40]
    drop = -max(p["hip_h"] - p["hip_w"] * 1.4, .08) * scale
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in {
        (B["root"], "translation"): [[0., 0., 0.], [0., drop * .22, 0.],
                                     [0., drop * .56, 0.], [0., drop * .88, 0.],
                                     [0., drop, 0.], [0., drop, 0.]],
        (B["body"], "rotation"): [_euler(), _euler(pitch=.26),
                                  _euler(pitch=.62, roll=.30),
                                  _euler(pitch=1.05, roll=.66),
                                  _euler(pitch=1.30, roll=.86),
                                  _euler(pitch=1.34, roll=.90)],
        (B["spine"], "rotation"): [_euler(), _euler(pitch=.20), _euler(pitch=.44),
                                   _euler(pitch=.62), _euler(pitch=.74),
                                   _euler(pitch=.76)],
        (B["cloak_1"], "rotation"): [_euler(), _euler(pitch=-.20), _euler(pitch=-.44),
                                     _euler(pitch=-.66), _euler(pitch=-.78),
                                     _euler(pitch=-.80)],
        (B["chest"], "rotation"): [_euler(), _euler(pitch=-.16), _euler(pitch=-.10),
                                   _euler(pitch=.12), _euler(pitch=.22),
                                   _euler(pitch=.24)],
        (B["neck"], "rotation"): [_euler(), _euler(pitch=-.20), _euler(pitch=.14),
                                  _euler(pitch=.42), _euler(pitch=.54),
                                  _euler(pitch=.55)],
        (B["head"], "rotation"): [_euler(), _euler(pitch=-.12), _euler(pitch=.20),
                                  _euler(pitch=.40), _euler(pitch=.48),
                                  _euler(pitch=.50)],
        (B["thigh_l"], "rotation"): [_euler(), _euler(pitch=.34), _euler(pitch=.80),
                                     _euler(pitch=1.10), _euler(pitch=1.24),
                                     _euler(pitch=1.26)],
        (B["thigh_r"], "rotation"): [_euler(), _euler(pitch=.28), _euler(pitch=.72),
                                     _euler(pitch=1.02), _euler(pitch=1.16),
                                     _euler(pitch=1.18)],
        (B["shin_l"], "rotation"): [_euler(), _euler(pitch=-.40), _euler(pitch=-.90),
                                    _euler(pitch=-1.20), _euler(pitch=-1.34),
                                    _euler(pitch=-1.36)],
        (B["shin_r"], "rotation"): [_euler(), _euler(pitch=-.34), _euler(pitch=-.82),
                                    _euler(pitch=-1.12), _euler(pitch=-1.26),
                                    _euler(pitch=-1.28)],
        (B["upper_arm_l"], "rotation"): [_euler(), _euler(pitch=-.36, roll=-.34),
                                         _euler(pitch=-.20, roll=-.50),
                                         _euler(pitch=.10, roll=-.62),
                                         _euler(pitch=.26, roll=-.68),
                                         _euler(pitch=.28, roll=-.70)],
        (B["upper_arm_r"], "rotation"): [_euler(), _euler(pitch=-.30, roll=.30),
                                         _euler(pitch=-.14, roll=.46),
                                         _euler(pitch=.16, roll=.58),
                                         _euler(pitch=.30, roll=.64),
                                         _euler(pitch=.32, roll=.66)],
        (B["forearm_l"], "rotation"): [_euler(pitch=-.30), _euler(pitch=-.50),
                                       _euler(pitch=-.70), _euler(pitch=-.86),
                                       _euler(pitch=-.94), _euler(pitch=-.95)],
        (B["forearm_r"], "rotation"): [_euler(pitch=-.30), _euler(pitch=-.46),
                                       _euler(pitch=-.66), _euler(pitch=-.82),
                                       _euler(pitch=-.90), _euler(pitch=-.91)],
    }.items()}
    return clips


# ---------------------------------------------------------------------------
# Family dispatch
# ---------------------------------------------------------------------------
def _quadruped_skeleton(plan_key, scale, variant=None):
    import creature_anatomy as anatomy
    return anatomy.skeleton_for(plan_key, scale, variant)


def _quadruped_geometry(plan_key, scale, bones, variant=None):
    import creature_anatomy as anatomy
    return anatomy.creature_geometry(plan_key, scale, bones, variant)


def _quadruped_animation(plan_key, scale, bones, variant=None):
    import creature_anatomy as anatomy
    return anatomy.animation_set(plan_key, scale, bones, variant)


FAMILIES = {
    "quadruped": (_quadruped_skeleton, _quadruped_geometry, _quadruped_animation),
    "biped": (biped_skeleton, biped_geometry, biped_animation),
}


def material_hints(family: str, plan: str, variant: str | None = None) -> dict:
    """Per-creature material intent: translucency, glow and back-face need.

    Energy, water and slime only read correctly if light passes through them,
    and a wisp with no emissive is just a grey cone.
    """
    if family != "amorphous":
        return {}
    config = amorphous_config(plan, variant)
    alpha = float(config["translucent"])
    return {"alpha": alpha,
            "alpha_mode": "BLEND" if alpha < .995 else None,
            "glow": float(config["glow"]),
            "double_sided": alpha < .995,
            "surface": config["surface"]}


def build_parts(family: str, plan: str, scale: float, variant: str | None = None):
    """Return (bones, mesh, clips) for one creature.

    ``variant`` is the creature slug, letting a family specialise a shared body
    plan per creature - which is how the humanoids get distinct silhouettes.
    """
    skeleton_fn, geometry_fn, animation_fn = FAMILIES[family]
    bones = skeleton_fn(plan, scale, variant)
    mesh = geometry_fn(plan, scale, bones, variant)
    clips = animation_fn(plan, scale, bones, variant)
    return bones, mesh, clips


# ---------------------------------------------------------------------------
# Shared helpers for the non-quadruped families
# ---------------------------------------------------------------------------
def _chain_bones(prefix: str, count: int, parent: int):
    """A serial bone chain, e.g. spine_1..spine_n or a limb segment run."""
    out = []
    for i in range(count):
        out.append((f"{prefix}_{i + 1}", parent if i == 0 else -2))
    return out


def _assemble(spec):
    """Turn (name, parent-name) pairs into the (name, parent-index) table."""
    index = {name: i for i, (name, _) in enumerate(spec)}
    return tuple((name, -1 if parent is None else index[parent])
                 for name, parent in spec), index


def _bones_from(globals_map, table):
    bones = []
    for name, parent in table:
        base = np.zeros(3) if parent < 0 else globals_map[table[parent][0]]
        bones.append((name, parent, tuple(float(v) for v in (globals_map[name] - base))))
    return bones


def _loop_clip(times, tracks):
    return {(node, path): (path, list(times), list(values))
            for (node, path), values in tracks.items()}


# ---------------------------------------------------------------------------
# Avian
# ---------------------------------------------------------------------------
AVIAN_TABLE, AVIAN_INDEX = _assemble([
    ("root", None), ("body", "root"), ("chest", "body"),
    ("neck", "chest"), ("neck_2", "neck"), ("head", "neck_2"), ("jaw", "head"),
    ("tail_1", "body"), ("tail_2", "tail_1"),
    ("wing_l", "chest"), ("wing_fore_l", "wing_l"), ("wing_hand_l", "wing_fore_l"),
    ("wing_r", "chest"), ("wing_fore_r", "wing_r"), ("wing_hand_r", "wing_fore_r"),
    ("thigh_l", "body"), ("shin_l", "thigh_l"), ("foot_l", "shin_l"),
    ("thigh_r", "body"), ("shin_r", "thigh_r"), ("foot_r", "shin_r"),
])

# The smaller families share one rule set: the measurements say how tall, how
# broad and how heavy a figure reads, and the plan keys that carry those are
# named the same way across avian, serpent, arachnid, insect and fish.
MINOR_PROPORTION_RULES = {
    "body_h": "tall", "neck_len": "tall", "leg": "limb", "stand": "tall",
    "body": "girth", "girth": "girth", "cephalo": "shoulder",
    "abdomen": "hip", "thorax": "shoulder", "length": "limb",
    "skull": "head", "head": "head", "beak": "head", "jaw": "head",
    "wing": "shoulder", "tail": "limb", "leg_r": "girth", "neck_r": "girth",
    "fin": "limb", "dorsal": "shoulder", "bill": "head", "antenna": "head",
    "rise": "tall",
}


# Per-creature identity for the smaller families.  They previously had none at
# all -- every beetle was the same beetle at a different size -- so anything
# the art gives one insect, bird, fish or spider and not its neighbour had
# nowhere to live.
MINOR_DETAIL = {
    # Amethyst Barrens: grown out of the rock, and lit from inside it.
    "geode_scarab": dict(carapace="crystal", carapace_relief=.22, dome=1.35),
    "prism_moth": dict(carapace="crystal", wing=1.34, wing_facets=True,
                       carapace_relief=.18),
    "lattice_spider": dict(carapace="crystal", carapace_relief=.20),
    "amethyst_scorpion": dict(carapace="crystal", carapace_relief=.24),
    "crystal_cave_spider": dict(carapace="crystal"),
    # Mirrorhold's swarm is the same trick in glass.
    "verdigris_beetle": dict(carapace="plate", dome=1.55,
                             thorax=(.26, .20, .20), abdomen=(.30, .23, .26),
                             head=(.10, .085, .095), wing=.44),
    # A hummingbird has almost no legs, a bill as long as its head and body
    # together, and a tail it fans.  On the shared songbird plan it came out
    # long-legged and short-billed, which is a finch.
    "plumefire_hummingbird": dict(leg=.045, leg_r=.008, beak=.30, beak_r=.012,
                                  wing=.46, tail=.34, crest=.05, upright=.50,
                                  body=(.075, .085, .145)),
    # The great owl and the heron want their necks and bills back after the
    # body tilt; the harpy stands nearly upright.
    "amberwood_owl": dict(crest=.11),
}


def minor_config(plans: dict, plan_key: str, variant: str | None = None) -> dict:
    """A plan for one of the smaller families, nudged by concept measurements."""
    import creature_anatomy as anatomy
    plan = dict(plans[plan_key])
    plan.setdefault("carapace", None)
    plan.setdefault("carapace_relief", .16)
    plan.setdefault("dome", 1.0)
    plan.setdefault("wing_facets", False)
    plan.setdefault("wing_lift", .0)
    plan.setdefault("eyestalks", False)
    plan.setdefault("shell", False)
    plan.setdefault("claw_size", 1.0)
    if variant:
        plan.update(MINOR_DETAIL.get(variant, {}))
        plan = anatomy.scale_plan(plan, anatomy.proportions(variant),
                                  MINOR_PROPORTION_RULES)
    return plan


AVIAN_PLANS = {
    "wader": dict(body_h=.60, body=(.13, .15, .30), neck_len=.42, neck_r=.036,
                  skull=(.075, .085, .12), beak=.30, beak_r=.030, leg=.52,
                  leg_r=.020, wing=.52, tail=.20, crest=.10, upright=.85, webbed=False),
    "seabird": dict(body_h=.30, body=(.14, .15, .30), neck_len=.14, neck_r=.048,
                    skull=(.075, .080, .11), beak=.14, beak_r=.032, leg=.16,
                    leg_r=.022, wing=.46, tail=.18, crest=.0, upright=.35, webbed=True),
    "songbird": dict(body_h=.26, body=(.10, .11, .20), neck_len=.07, neck_r=.036,
                     skull=(.058, .062, .080), beak=.09, beak_r=.018, leg=.12,
                     leg_r=.013, wing=.38, tail=.20, crest=.0, upright=.40, webbed=False),
    "raptor": dict(body_h=.44, body=(.16, .18, .34), neck_len=.14, neck_r=.058,
                   skull=(.090, .095, .12), beak=.14, beak_r=.038, leg=.26,
                   leg_r=.028, wing=.62, tail=.26, crest=.05, upright=.55, webbed=False),
    # A perched owl's folded wing reaches about the length of its body; at .50
    # against a body .28 long the wing chain ran half again past the tail and
    # the bird disappeared inside its own plumage.
    "owl": dict(body_h=.40, body=(.19, .20, .28), neck_len=.06, neck_r=.070,
                skull=(.115, .110, .12), beak=.07, beak_r=.026, leg=.20,
                leg_r=.026, wing=.33, tail=.18, crest=.06, upright=.60, webbed=False),
    "harpy": dict(body_h=.62, body=(.15, .22, .20), neck_len=.16, neck_r=.052,
                  skull=(.090, .105, .10), beak=.08, beak_r=.022, leg=.42,
                  leg_r=.030, wing=.66, tail=.22, crest=.10, upright=.95, webbed=False),
}


def avian_skeleton(plan_key: str, scale: float, variant=None):
    p = minor_config(AVIAN_PLANS, plan_key, variant)
    s = scale
    body_y = p["body_h"] * s
    tilt = p["upright"]
    body = np.array((0., body_y, 0.))
    # ``upright`` has to tilt the *body*, not just lift the neck out of it.
    # Applied to the neck alone, an owl and a heron kept a duck's horizontal
    # teardrop with a tall neck stuck on the front of it; the art stands both
    # of them up on their tails.
    chest = body + np.array((0., p["body"][2] * s * .62 * tilt,
                             -p["body"][2] * s * .34 * (1. - tilt * .55)))
    neck = chest + np.array((0., p["neck_len"] * s * .35 * tilt,
                             -p["neck_len"] * s * .28 * (1 - tilt * .5)))
    neck2 = neck + np.array((0., p["neck_len"] * s * .40 * tilt,
                             -p["neck_len"] * s * .32 * (1 - tilt * .5)))
    head = neck2 + np.array((0., p["neck_len"] * s * .30 * tilt,
                             -p["neck_len"] * s * .34 - p["skull"][2] * s * .4))
    g = {"root": np.zeros(3), "body": body, "chest": chest, "neck": neck,
         "neck_2": neck2, "head": head,
         "jaw": head + np.array((0., -p["skull"][1] * s * .34, -p["skull"][2] * s * .5))}
    g["tail_1"] = body + np.array((0., .01 * s - p["body"][2] * s * .40 * tilt,
                                   p["body"][2] * s * .52 * (1. - tilt * .45)))
    g["tail_2"] = g["tail_1"] + np.array((0., -.02 * s, p["tail"] * s * .7))
    for side, sign in (("l", -1.), ("r", 1.)):
        shoulder = chest + np.array((sign * p["body"][0] * s * .78, .04 * s, 0.))
        g[f"wing_{side}"] = shoulder
        # A perched bird folds: the elbow swings back, the hand tucks in along
        # the flank.  Flight spreads the same chain outward.
        g[f"wing_fore_{side}"] = shoulder + np.array((sign * p["wing"] * s * .17,
                                                      .02 * s, p["wing"] * s * .30))
        g[f"wing_hand_{side}"] = shoulder + np.array((sign * p["wing"] * s * .09,
                                                      -.04 * s, p["wing"] * s * .66))
        hip = body + np.array((sign * p["body"][0] * s * .55, -p["body"][1] * s * .3, 0.))
        g[f"thigh_{side}"] = hip
        g[f"shin_{side}"] = np.array((hip[0], p["leg"] * s * .45, hip[2] + .02 * s))
        g[f"foot_{side}"] = np.array((hip[0], p["leg_r"] * s * 1.4, hip[2] - .01 * s))
    return _bones_from(g, AVIAN_TABLE)


def avian_geometry(plan_key: str, scale: float, bones, variant=None) -> AnatomyMesh:
    p = minor_config(AVIAN_PLANS, plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = AVIAN_INDEX
    mesh = AnatomyMesh(g)
    body_i, chest_i, neck_i = B["body"], B["chest"], B["neck"]
    head_i, jaw_i = B["head"], B["jaw"]
    bw, bh, bl = (v * s for v in p["body"])

    # Teardrop body: full at the breast, tapering to the tail.
    tail_root = g[B["tail_1"]]
    breast = g[chest_i]
    spine = [tail_root, tail_root * .35 + breast * .65, breast]
    body_pts = [spine[0] + np.array((0., 0., bl * .10)), spine[1], spine[2]]
    body_radii = [(bw * .40, bh * .40), (bw, bh), (bw * .80, bh * .86)]
    mesh.tube(body_pts, body_radii, [body_i, chest_i, neck_i], MAT_BODY,
              sides=16, uv_scale=1.4, lower_material=MAT_ACCENT,
              lower_threshold=-.30)
    mesh.torso = (body_pts, body_radii, [body_i, chest_i, neck_i])

    neck_pts = [g[chest_i], g[neck_i], g[B["neck_2"]], g[head_i]]
    nr = p["neck_r"] * s
    mesh.tube(neck_pts, [(nr * 1.5, nr * 1.5), (nr * 1.1, nr * 1.1),
                         (nr, nr), (nr * .95, nr * .95)],
              [chest_i, neck_i, B["neck_2"], head_i], MAT_BODY, sides=10,
              cap_start=False, cap_end=False)
    skull = tuple(v * s for v in p["skull"])
    mesh.ellipsoid(tuple(g[head_i]), skull, [head_i, B["neck_2"]], MAT_BODY,
                   rings=9, sides=14)
    # Beak: upper and lower mandible so it reads as a bird from any angle.
    beak_root = g[head_i] + np.array((0., skull[1] * .04, -skull[2] * .42))
    beak_tip = beak_root + np.array((0., -p["beak"] * s * .18, -p["beak"] * s))
    br = p["beak_r"] * s
    mesh.tube([beak_root, (beak_root + beak_tip) * .5, beak_tip],
              [(br * 1.5, br * 1.3), (br * .9, br * .8), (br * .18, br * .16)],
              [head_i], MAT_FEATURE, sides=9, cap_start=False)
    mesh.tube([beak_root + np.array((0., -br * .8, 0.)),
               beak_tip + np.array((0., br * .1, br * 1.2))],
              [(br * 1.15, br * .70), (br * .20, br * .16)],
              [jaw_i, head_i], MAT_FEATURE, sides=8, cap_start=False)
    for side in (-1., 1.):
        mesh.ellipsoid(tuple(g[head_i] + np.array((side * skull[0] * .60,
                                                   skull[1] * .18, -skull[2] * .18))),
                       (skull[0] * .34,) * 3, [head_i], MAT_DARK, rings=6, sides=10)
    if p["crest"]:
        crest = g[head_i] + np.array((0., skull[1] * .74, skull[2] * .12))
        for k in range(4):
            tip = crest + np.array(((k - 1.5) * skull[0] * .30,
                                    p["crest"] * s * (1 - abs(k - 1.5) * .18),
                                    skull[2] * .30))
            mesh.tube([crest, tip], [(skull[0] * .16, skull[0] * .10),
                                     (skull[0] * .05, skull[0] * .04)],
                      [head_i], MAT_ACCENT, sides=6)

    # Wings as membranes over a three-segment spar.
    for side, sign in (("l", -1.), ("r", 1.)):
        sh = g[B[f"wing_{side}"]]
        fo = g[B[f"wing_fore_{side}"]]
        hand = g[B[f"wing_hand_{side}"]]
        wb = [chest_i, B[f"wing_{side}"], B[f"wing_fore_{side}"], B[f"wing_hand_{side}"]]
        wr = p["wing"] * s * .045
        mesh.tube([sh, fo, hand], [(wr * 1.5, wr * 1.5), (wr * 1.1, wr * 1.1),
                                   (wr * .7, wr * .7)], wb, MAT_BODY, sides=8,
                  cap_start=False)
        tip = hand + np.array((sign * p["wing"] * s * .04, -.05 * s,
                               p["wing"] * s * .30))
        lead = [sh + np.array((sign * bw * .10, .02 * s, -bl * .10)), fo, hand, tip]
        trail = [sh + np.array((sign * bw * .30, -bh * .55, bl * .18)),
                 fo + np.array((sign * bw * .22, -bh * .50, bl * .10)),
                 hand + np.array((sign * bw * .16, -bh * .40, .0)),
                 tip]
        edge_a = [_bezier(lead, t) for t in np.linspace(0, 1, 8)]
        edge_b = [_bezier(trail, t) for t in np.linspace(0, 1, 8)]
        _sheet(mesh, edge_a, edge_b, .012 * s, wb, MAT_ACCENT)
        # Flight feathers over the membrane.  Without them a wing is a
        # coloured triangle with no edge and no serration in its outline.
        feather_row(mesh, edge_a, edge_b, wb, MAT_ACCENT,
                    seed=f"{variant or plan_key}:wing:{side}", count=10,
                    overhang=.26, width=.30, splay=.12, tip_material=MAT_DARK)

    # Tail fan.
    t1, t2 = g[B["tail_1"]], g[B["tail_2"]]
    fan_a = [t1 + np.array((-bw * .5, 0., 0.)), t2 + np.array((-bw * .8, 0., 0.))]
    fan_b = [t1 + np.array((bw * .5, 0., 0.)), t2 + np.array((bw * .8, 0., 0.))]
    tail_bones = [body_i, B["tail_1"], B["tail_2"]]
    _sheet(mesh, fan_a, fan_b, .012 * s, tail_bones, MAT_ACCENT)
    # Tail feathers, spread across the fan rather than a single flat plate.
    root_line = [t1 + np.array((-bw * .46, 0., 0.)), t1 + np.array((bw * .46, 0., 0.))]
    tip_line = [t2 + np.array((-bw * .92, 0., bl * .22)),
                t2 + np.array((bw * .92, 0., bl * .22))]
    feather_row(mesh, root_line, tip_line, tail_bones, MAT_ACCENT,
                seed=f"{variant or plan_key}:tail", count=7, overhang=.14,
                width=.40, splay=.0, tip_material=MAT_DARK)

    # Legs and feet.
    for side, sign in (("l", -1.), ("r", 1.)):
        hip = g[B[f"thigh_{side}"]]
        knee = g[B[f"shin_{side}"]]
        foot = g[B[f"foot_{side}"]]
        lb = [body_i, B[f"thigh_{side}"], B[f"shin_{side}"], B[f"foot_{side}"]]
        lr = p["leg_r"] * s
        mesh.ellipsoid(tuple(hip + np.array((0., bh * .18, 0.))),
                       (lr * 3.4, bh * .78, bl * .34), lb, MAT_BODY,
                       rings=7, sides=10)
        mesh.tube([hip + np.array((0., bh * .3, 0.)),
                   hip * .4 + knee * .6, knee,
                   np.array((foot[0], lr * 1.3, foot[2]))],
                  [(lr * 2.8, lr * 2.8), (lr * 1.7, lr * 1.7),
                   (lr * 1.20, lr * 1.20), (lr, lr)],
                  lb, MAT_BODY, sides=8, cap_start=False, cap_end=False)
        if p["webbed"]:
            web_a = [np.array((foot[0] - lr * 1.6, lr * .5, foot[2] + lr * 1.2)),
                     np.array((foot[0] - lr * 1.8, lr * .4, foot[2] - lr * 3.4))]
            web_b = [np.array((foot[0] + lr * 1.6, lr * .5, foot[2] + lr * 1.2)),
                     np.array((foot[0] + lr * 1.8, lr * .4, foot[2] - lr * 3.4))]
            _sheet(mesh, web_a, web_b, lr * .5, [B[f"foot_{side}"]], MAT_FEATURE)
        else:
            for k in range(3):
                toe = np.array((foot[0] + (k - 1) * lr * 1.3, lr * .55,
                                foot[2] - lr * 3.0))
                mesh.tube([np.array((foot[0], lr * .8, foot[2])), toe],
                          [(lr * .8, lr * .7), (lr * .30, lr * .26)],
                          [B[f"foot_{side}"]], MAT_FEATURE, sides=6)
            back = np.array((foot[0], lr * .55, foot[2] + lr * 1.9))
            mesh.tube([np.array((foot[0], lr * .8, foot[2])), back],
                      [(lr * .7, lr * .6), (lr * .26, lr * .22)],
                      [B[f"foot_{side}"]], MAT_FEATURE, sides=6)
    return mesh


def avian_animation(plan_key: str, scale: float, bones, variant=None) -> dict:
    p = minor_config(AVIAN_PLANS, plan_key, variant)
    B = AVIAN_INDEX
    clips: dict[str, dict] = {}
    wing_bones = [(B["wing_l"], -1.), (B["wing_r"], 1.)]

    n = 16
    times = [2.4 * i / n for i in range(n + 1)]
    wave = [math.sin(2 * math.pi * i / n) for i in range(n + 1)]
    slow = [math.sin(math.pi * i / n) for i in range(n + 1)]
    idle = {(B["root"], "translation"): [[0., .006 * scale * w, 0.] for w in wave],
            (B["body"], "rotation"): [_euler(pitch=.020 * w) for w in wave],
            (B["neck"], "rotation"): [_euler(pitch=-.05 * w, yaw=.09 * sl)
                                      for w, sl in zip(wave, slow)],
            (B["neck_2"], "rotation"): [_euler(pitch=.04 * w) for w in wave],
            (B["head"], "rotation"): [_euler(yaw=-.16 * sl, pitch=.05 * w)
                                      for w, sl in zip(wave, slow)],
            (B["tail_1"], "rotation"): [_euler(pitch=.05 * w) for w in wave]}
    for bone, sign in wing_bones:
        idle[(bone, "rotation")] = [_euler(roll=sign * .03 * w, pitch=.02 * w)
                                    for w in wave]
    clips["Idle_A"] = _loop_clip(times, idle)

    def gait(duration, samples, swing, flap):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            c = 2 * math.pi * u
            tracks.setdefault((B["root"], "translation"), []).append(
                [0., .020 * scale * abs(math.sin(c)), 0.])
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(roll=.07 * math.sin(c), pitch=.03 * math.sin(2 * c)))
            tracks.setdefault((B["neck"], "rotation"), []).append(
                _euler(pitch=-.10 * math.sin(2 * c)))
            tracks.setdefault((B["head"], "rotation"), []).append(
                _euler(pitch=.12 * math.sin(2 * c + 1.0)))
            tracks.setdefault((B["tail_1"], "rotation"), []).append(
                _euler(pitch=.06 * math.sin(2 * c)))
            for side, phase in (("l", 0.0), ("r", .5)):
                leg = math.sin(c - 2 * math.pi * phase)
                knee = max(0., math.sin(c - 2 * math.pi * phase + math.pi * .4))
                tracks.setdefault((B[f"thigh_{side}"], "rotation"), []).append(
                    _euler(pitch=swing * leg))
                tracks.setdefault((B[f"shin_{side}"], "rotation"), []).append(
                    _euler(pitch=-swing * 1.5 * knee))
                tracks.setdefault((B[f"foot_{side}"], "rotation"), []).append(
                    _euler(pitch=swing * knee * .8))
            for bone, sign in wing_bones:
                tracks.setdefault((bone, "rotation"), []).append(
                    _euler(roll=sign * flap * abs(math.sin(c)), pitch=.04 * math.sin(c)))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Walk"] = gait(1.0, 16, .42, .12)
    clips["Jog"] = gait(.58, 14, .62, .85)

    n = 12
    times = [1.4 * i / n for i in range(n + 1)]
    wave = [math.sin(2 * math.pi * i / n) for i in range(n + 1)]
    fight = {(B["body"], "rotation"): [_euler(pitch=.16) for _ in wave],
             (B["neck"], "rotation"): [_euler(pitch=-.22 + .06 * w) for w in wave],
             (B["head"], "rotation"): [_euler(pitch=.14, yaw=.12 * w) for w in wave],
             (B["jaw"], "rotation"): [_euler(pitch=.10 + .05 * abs(w)) for w in wave]}
    for bone, sign in wing_bones:
        fight[(bone, "rotation")] = [_euler(roll=sign * (.70 + .12 * w)) for w in wave]
    clips["Fighting_Idle"] = _loop_clip(times, fight)

    stamp = [0., .16, .30, .44, .58, .78]
    attack = {(B["root"], "translation"): [[0., 0., 0.], [0., .04 * scale, 0.],
                                          [0., .07 * scale, 0.], [0., .02 * scale, 0.],
                                          [0., .01 * scale, 0.], [0., 0., 0.]],
              (B["body"], "rotation"): [_euler(), _euler(pitch=-.20), _euler(pitch=.26),
                                        _euler(pitch=.34), _euler(pitch=.10), _euler()],
              (B["neck"], "rotation"): [_euler(), _euler(pitch=.26), _euler(pitch=-.34),
                                        _euler(pitch=-.46), _euler(pitch=-.12), _euler()],
              (B["head"], "rotation"): [_euler(), _euler(pitch=.20), _euler(pitch=-.26),
                                        _euler(pitch=-.32), _euler(pitch=-.06), _euler()],
              (B["jaw"], "rotation"): [_euler(), _euler(pitch=.30), _euler(pitch=.52),
                                       _euler(pitch=.10), _euler(pitch=.04), _euler()]}
    for bone, sign in wing_bones:
        attack[(bone, "rotation")] = [_euler(), _euler(roll=sign * .90),
                                      _euler(roll=sign * .30), _euler(roll=sign * .12),
                                      _euler(roll=sign * .26), _euler()]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in attack.items()}

    hit_t = [0., .09, .20, .34, .48]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in {
        (B["body"], "rotation"): [_euler(), _euler(pitch=.26, roll=.16),
                                  _euler(pitch=.16, roll=.08), _euler(pitch=-.04), _euler()],
        (B["neck"], "rotation"): [_euler(), _euler(pitch=.34), _euler(pitch=.20),
                                  _euler(pitch=-.05), _euler()],
        (B["head"], "rotation"): [_euler(), _euler(pitch=.30, yaw=.18),
                                  _euler(pitch=.16), _euler(), _euler()],
        (B["wing_l"], "rotation"): [_euler(), _euler(roll=-.60), _euler(roll=-.30),
                                    _euler(roll=-.10), _euler()],
        (B["wing_r"], "rotation"): [_euler(), _euler(roll=.60), _euler(roll=.30),
                                    _euler(roll=.10), _euler()],
    }.items()}

    death_t = [0., .26, .52, .82, 1.10, 1.36]
    drop = -max(p["leg"] * .55, .06) * scale
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in {
        (B["root"], "translation"): [[0., 0., 0.], [0., drop * .30, 0.],
                                     [0., drop * .66, 0.], [0., drop * .92, 0.],
                                     [0., drop, 0.], [0., drop, 0.]],
        (B["body"], "rotation"): [_euler(), _euler(roll=.24, pitch=.14),
                                  _euler(roll=.72, pitch=.20), _euler(roll=1.16, pitch=.16),
                                  _euler(roll=1.42, pitch=.12), _euler(roll=1.46, pitch=.10)],
        (B["neck"], "rotation"): [_euler(), _euler(pitch=-.20), _euler(pitch=.24),
                                  _euler(pitch=.48), _euler(pitch=.60), _euler(pitch=.62)],
        (B["head"], "rotation"): [_euler(), _euler(pitch=-.10), _euler(pitch=.20),
                                  _euler(pitch=.40), _euler(pitch=.50), _euler(pitch=.52)],
        (B["wing_l"], "rotation"): [_euler(), _euler(roll=-.40), _euler(roll=-.70),
                                    _euler(roll=-.86), _euler(roll=-.94), _euler(roll=-.95)],
        (B["wing_r"], "rotation"): [_euler(), _euler(roll=.40), _euler(roll=.70),
                                    _euler(roll=.86), _euler(roll=.94), _euler(roll=.95)],
        (B["thigh_l"], "rotation"): [_euler(), _euler(pitch=.40), _euler(pitch=.86),
                                     _euler(pitch=1.10), _euler(pitch=1.20), _euler(pitch=1.22)],
        (B["thigh_r"], "rotation"): [_euler(), _euler(pitch=.36), _euler(pitch=.80),
                                     _euler(pitch=1.04), _euler(pitch=1.14), _euler(pitch=1.16)],
    }.items()}
    return clips


FAMILIES["avian"] = (avian_skeleton, avian_geometry, avian_animation)


# ---------------------------------------------------------------------------
# Serpent
# ---------------------------------------------------------------------------
SERPENT_SEGMENTS = 9
SERPENT_TABLE, SERPENT_INDEX = _assemble(
    [("root", None), ("body", "root")]
    + [(f"coil_{i + 1}", "body" if i == 0 else f"coil_{i}")
       for i in range(SERPENT_SEGMENTS)]
    + [("neck", "body"), ("head", "neck"), ("jaw", "head"),
       ("neck_b", "body"), ("head_b", "neck_b"),
       ("neck_c", "body"), ("head_c", "neck_c"),
       ("arm_l", "body"), ("forearm_l", "arm_l"),
       ("arm_r", "body"), ("forearm_r", "arm_r")])

# ``rear`` is how high the front of the body is carried.  Every serpent in the
# concept art is coiled and reared -- the body loops up off the ground and the
# head is held above it -- and laid out flat they were ten identical hoses.
# ``spine`` is the row of dorsal spines or fins running the length of the back,
# which is the other thing the art gives all of them and the models had none of.
SERPENT_PLANS = {
    "snake": dict(length=1.90, girth=.145, rise=.34, head=(.14, .11, .22),
                  jaw=.13, fins=False, frill=.20, heads=1, arms=False,
                  crest=.08, limbs=False, ride=.10, rear=.46, spine=.055,
                  coil=1.9),
    "sea_serpent": dict(length=2.40, girth=.180, rise=.46, head=(.16, .14, .26),
                        jaw=.17, fins=True, frill=.10, heads=1, arms=False,
                        crest=.10, limbs=False, ride=.16, rear=.62, spine=.085,
                        coil=2.1),
    "eel": dict(length=1.80, girth=.128, rise=.16, head=(.12, .10, .21),
                jaw=.15, fins=True, frill=.0, heads=1, arms=False,
                crest=.0, limbs=False, ride=.09, rear=.20, spine=.055,
                coil=1.5),
    "wyrm": dict(length=2.70, girth=.215, rise=.58, head=(.19, .17, .31),
                 jaw=.21, fins=False, frill=.14, heads=1, arms=True,
                 crest=.14, limbs=True, ride=.22, rear=.82, spine=.130,
                 coil=2.3),
    "hydra": dict(length=1.90, girth=.195, rise=.50, head=(.14, .12, .23),
                  jaw=.15, fins=False, frill=.08, heads=5, arms=False,
                  crest=.07, limbs=True, ride=.20, rear=.64, spine=.075,
                  coil=1.7),
    "naga": dict(length=1.70, girth=.155, rise=.94, head=(.11, .13, .13),
                 jaw=.08, fins=True, frill=.16, heads=1, arms=True,
                 crest=.0, limbs=False, ride=.22, rear=.52, spine=.045,
                 coil=1.9),
}


def serpent_skeleton(plan_key: str, scale: float, variant=None):
    p = minor_config(SERPENT_PLANS, plan_key, variant)
    s = scale
    girth = p["girth"] * s
    rear = p["rear"] * s
    body = np.array((0., girth * 1.05 + rear, 0.))
    g = {"root": np.zeros(3), "body": body}
    # Coils run backwards and *down*: the front of the animal is carried high
    # and the body settles to the floor over its length, looping wider as it
    # goes.  Held at a constant height in a shallow horizontal wiggle -- which
    # is what this was -- a serpent is a length of hose lying in the road, and
    # no amount of head detail rescues it.
    # A spiral, not a wave.  The radius is set from the body's own length so
    # roughly one turn uses it up: a serpent in the art occupies a compact
    # coil about as wide as it is tall, and stretched down a straight line the
    # same animal is a hosepipe two and a half metres long with a head on one
    # end.
    turns = max(.55, p["coil"] * .52)
    wrap = p["length"] * s / (2 * math.pi * turns)
    for i in range(SERPENT_SEGMENTS):
        t = (i + 1) / SERPENT_SEGMENTS
        # The descent has to carry the tail all the way to the floor.  Settling
        # only as far as ``rear`` left the whole animal hovering a tenth of a
        # unit up, because the spine stops at body height while the tube around
        # it has already tapered away to nothing.
        settle = (rear + girth * .85) * (1.0 - (1.0 - t) ** 1.9)
        undulate = math.sin(t * math.pi * 2.3) * girth * .85 * (1.0 - t)
        angle = t * turns * 2 * math.pi
        open_out = wrap * (.62 + .52 * t)
        g[f"coil_{i + 1}"] = np.array((
            math.sin(angle) * open_out,
            max(girth * .24, girth * 1.05 + rear - settle + undulate),
            (1.0 - math.cos(angle)) * open_out))
    rise = p["rise"] * s
    for suffix, lateral in (("", 0.), ("_b", -.22), ("_c", .22)):
        if suffix and p["heads"] < (2 if suffix == "_b" else 3):
            g[f"neck{suffix}"] = body + np.array((0., rise * .45, -girth * 2.0))
            g[f"head{suffix}"] = body + np.array((0., rise * .70, -girth * 3.2))
            continue
        neck = body + np.array((lateral * s * 1.5, rise * .60,
                                -girth * 1.5 - abs(lateral) * s * .7))
        head = neck + np.array((lateral * s * 1.3, rise * .50,
                                -p["head"][2] * s * 1.25))
        g[f"neck{suffix}"] = neck
        g[f"head{suffix}"] = head
    g["jaw"] = g["head"] + np.array((0., -p["head"][1] * s * .40,
                                     -p["head"][2] * s * .45))
    for side, sign in (("l", -1.), ("r", 1.)):
        shoulder = body + np.array((sign * girth * 1.5, rise * .30, -girth * 1.2))
        g[f"arm_{side}"] = shoulder
        g[f"forearm_{side}"] = shoulder + np.array((sign * .22 * s, -.18 * s, .02 * s))
    return _bones_from(g, SERPENT_TABLE)


def serpent_geometry(plan_key: str, scale: float, bones, variant=None) -> AnatomyMesh:
    p = minor_config(SERPENT_PLANS, plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = SERPENT_INDEX
    mesh = AnatomyMesh(g)
    body_i = B["body"]
    girth = p["girth"] * s
    coil_bones = [body_i] + [B[f"coil_{i + 1}"] for i in range(SERPENT_SEGMENTS)]

    points = [g[body_i]] + [g[B[f"coil_{i + 1}"]] for i in range(SERPENT_SEGMENTS)]
    tip = points[-1] + (points[-1] - points[-2]) * .7
    points.append(tip)
    widths = []
    for i, _ in enumerate(points):
        t = i / (len(points) - 1)
        swell = math.sin(min(t * 1.15 + .12, 1.) * math.pi) * .35 + .78
        r = girth * swell * (1.0 - .78 * t ** 2.1)
        widths.append((r, r * .92))
    mesh.tube(points, widths, coil_bones, MAT_BODY, sides=14, uv_scale=3.0,
              lower_material=MAT_ACCENT, lower_threshold=-.40)
    mesh.torso = (list(points), list(widths), list(coil_bones))
    if p["spine"]:
        # The ridge of spines or fins the art runs the whole length of the
        # back.  It is most of what separates a sea serpent from a worm, and
        # it is what makes the coils read as coils from the side.
        blade = p["spine"] * s
        count = SERPENT_SEGMENTS * 3
        for k in range(count):
            t = (k + .5) / count
            place = t * (len(points) - 1)
            low = min(int(place), len(points) - 2)
            frac = place - low
            here = points[low] * (1 - frac) + points[low + 1] * frac
            wide = widths[low][0] * (1 - frac) + widths[low + 1][0] * frac
            ahead = points[min(low + 1, len(points) - 1)] - points[low]
            norm = float(np.linalg.norm(ahead))
            ahead = ahead / norm if norm > 1e-9 else np.array((0., 0., 1.))
            up = np.array((0., 1., 0.)) - ahead * float(ahead[1])
            if float(np.linalg.norm(up)) < .2:
                up = np.array((0., 1., 0.))
            up = up / max(float(np.linalg.norm(up)), 1e-9)
            # Tallest a third of the way back, tapering to nothing at the tail.
            height = blade * math.sin(math.pi * min(1.0, t * 1.25 + .10)) * \
                (1.0 - .55 * t)
            base = here + up * wide * .92
            mesh.tube([base - ahead * wide * .55, base + up * height,
                       base + ahead * wide * .55],
                      [(wide * .10, wide * .10), (wide * .16, wide * .06),
                       (wide * .10, wide * .10)],
                      coil_bones, MAT_ACCENT, sides=4)

    heads = [("", B["neck"], B["head"])]
    if p["heads"] >= 2:
        heads.append(("_b", B["neck_b"], B["head_b"]))
    if p["heads"] >= 3:
        heads.append(("_c", B["neck_c"], B["head_c"]))
    hw, hh, hl = (v * s for v in p["head"])
    for suffix, neck_i, head_i in heads:
        neck_pts = [g[body_i] + np.array((0., girth * .2, -girth * .6)),
                    g[neck_i], g[head_i]]
        mesh.tube(neck_pts, [(girth * .95, girth * .90), (girth * .72, girth * .70),
                             (hw * .90, hh * .90)],
                  [body_i, neck_i, head_i], MAT_BODY, sides=12,
                  cap_start=False, cap_end=False)
        # The head has to be plainly bigger than the body behind it.  At 2.6
        # of a head unit against a body of the same diameter there was no
        # break in the silhouette at all: the neck simply stopped.
        skull_shape = ((hw * 2.3, hh * 2.4, hl * 2.4) if plan_key == "naga"
                       else (hw * 3.3, hh * 3.1, hl * 2.6))
        mesh.ellipsoid(tuple(g[head_i]), skull_shape,
                       [head_i, neck_i], MAT_BODY, rings=10, sides=15)
        # The bony brow ridge over the eyes, which is what gives a serpent a
        # face rather than a nose cone.
        # In the creature's own hide, and low: through the keratin material at
        # nearly three head-widths across it capped every serpent with a
        # bone-white shell that read as a hat.
        if plan_key != "naga":
            mesh.ellipsoid(tuple(g[head_i] + np.array((0., hh * .95, -hl * .45))),
                           (hw * 2.15, hh * .62, hl * 1.15),
                           [head_i], MAT_BODY, rings=6, sides=12)
        snout = g[head_i] + np.array((0., -hh * .18, -hl * 1.15))
        jaw_bone = B["jaw"] if suffix == "" else head_i
        if plan_key != "naga":
            # A naga's head is a person's; drawing the serpent snout and jaw on
            # top of the face gave it two heads in one.
            mesh.tube([g[head_i] + np.array((0., -hh * .10, -hl * .5)), snout],
                      [(hw * 1.5, hh * 1.3), (hw * .85, hh * .65)],
                      [head_i, jaw_bone], MAT_BODY, sides=10, cap_start=False)
            mesh.tube([g[head_i] + np.array((0., -hh * .75, -hl * .45)),
                       snout + np.array((0., hh * .16, hl * .18))],
                      [(hw * 1.15, hh * .55), (hw * .70, hh * .38)],
                      [jaw_bone, head_i], MAT_BODY, sides=9, cap_start=False)
            for side in (-1., 1.):
                mesh.ellipsoid(tuple(g[head_i] + np.array((side * hw * 1.15,
                                                           hh * .55, -hl * .45))),
                               (hw * .48,) * 3, [head_i], MAT_DARK,
                               rings=6, sides=10)
        if p["frill"]:
            # A crown of fins sweeping back off the skull.  Every serpent in
            # the art wears one -- ice on the frost serpent, leaf on the tree
            # serpent, horn on the wyrm -- and it is the single feature that
            # tells one of these apart from another at a glance.  Two flat
            # sheets on the neck did not read as anything.
            f = p["frill"] * s
            back = g[head_i] - g[neck_i]
            norm = float(np.linalg.norm(back))
            back = back / norm if norm > 1e-9 else np.array((0., 0., -1.))
            for k in range(7):
                a = math.pi * (k / 6.0) - math.pi * .5
                out = np.array((math.sin(a), math.cos(a) * .85, 0.))
                root = g[head_i] + out * hw * 1.5 - back * hl * .35
                # Longest over the crown, shortest at the jawline.
                reach = f * (.55 + .95 * math.cos(a) ** 2)
                tip = root + out * reach * .75 - back * reach * 1.05
                mid = (root + tip) * .5 + out * reach * .12
                mesh.tube([root, mid, tip],
                          [(hw * .30, hw * .12), (hw * .22, hw * .09),
                           (hw * .05, hw * .03)],
                          [head_i, neck_i], MAT_ACCENT, sides=4)
        if p["crest"]:
            c = p["crest"] * s
            for k in range(4):
                t = .15 + .55 * k / 3
                base = g[neck_i] * (1 - t) + g[head_i] * t + np.array((0., girth * .5, 0.))
                mesh.spike(base, base + np.array((0., c * (1 - .15 * k), girth * .3)),
                           .022 * s, [neck_i, head_i], MAT_FEATURE, sides=6)
            # A pair of horns swept back off the brow, as the art draws on
            # every one of these that carries a crest.
            for side in (-1., 1.):
                root = g[head_i] + np.array((side * hw * 1.25, hh * 1.35,
                                             hl * .30))
                mesh.tube([root, root + np.array((side * c * .45, c * .70,
                                                  c * .55)),
                           root + np.array((side * c * .60, c * .95, c * 1.35))],
                          [(hw * .34, hw * .34), (hw * .21, hw * .21),
                           (hw * .05, hw * .05)],
                          [head_i, neck_i], MAT_FEATURE, sides=6)
    if p["fins"]:
        for k in range(5):
            t = .10 + .62 * k / 4
            index = min(int(t * (len(points) - 1)), len(points) - 2)
            base = points[index] + np.array((0., widths[index][1] * .9, 0.))
            mesh.spike(base, base + np.array((0., girth * 1.15, girth * .25)),
                       widths[index][0] * .30, coil_bones, MAT_ACCENT, sides=6)
    if p["limbs"]:
        for side, sign in (("l", -1.), ("r", 1.)):
            sh = g[B[f"arm_{side}"]]
            fo = g[B[f"forearm_{side}"]]
            hand = fo + np.array((sign * .06 * s, -.14 * s, -.05 * s))
            mesh.tube([sh, fo, hand],
                      [(girth * .55, girth * .55), (girth * .40, girth * .40),
                       (girth * .26, girth * .26)],
                      [body_i, B[f"arm_{side}"], B[f"forearm_{side}"]], MAT_BODY,
                      sides=9, cap_start=False)
            for k in range(3):
                claw = hand + np.array((sign * (k - 1) * .03 * s, -.03 * s, -.05 * s))
                mesh.spike(hand, claw, girth * .10,
                           [B[f"forearm_{side}"]], MAT_DARK, sides=5)
    if p["arms"] and plan_key == "naga":
        # A naga is half a person, and the person half had nothing in it: the
        # neck tube ran straight into a ball, so the art's coral priestess came
        # out as a snowman on a coil.  Build the torso the art draws -- ribcage
        # over a waist, a shoulder girdle, arms with elbows and hands, and a
        # face -- on the bones the rig already carries.
        neck_i, head_i = B["neck"], B["head"]
        hw, hh, hl = (v * s for v in p["head"])
        waist = g[body_i] + np.array((0., girth * 1.05, -girth * .35))
        chest = (waist + g[neck_i]) * .5 + np.array((0., 0., -girth * .12))
        mesh.tube([waist, chest, g[neck_i]],
                  [(girth * .96, girth * .82), (girth * 1.06, girth * .86),
                   (girth * .62, girth * .56)],
                  [body_i, neck_i], MAT_BODY, sides=14, cap_start=False,
                  cap_end=False)
        # Hips flaring into the coil, so the join is not a seam.
        mesh.ellipsoid(tuple(waist + np.array((0., -girth * .35, 0.))),
                       (girth * 1.30, girth * 1.15, girth * 1.30),
                       [body_i], MAT_BODY, rings=8, sides=14)
        girdle = []
        for side, sign in (("l", -1.), ("r", 1.)):
            girdle.append(g[B[f"arm_{side}"]])
        mesh.tube([girdle[0], chest + np.array((0., girth * .40, 0.)), girdle[1]],
                  [(girth * .42, girth * .42), (girth * .95, girth * .78),
                   (girth * .42, girth * .42)],
                  [body_i, B["arm_l"], B["arm_r"], neck_i], MAT_BODY, sides=11)
        for side, sign in (("l", -1.), ("r", 1.)):
            sh = g[B[f"arm_{side}"]]
            fo = g[B[f"forearm_{side}"]]
            hand = fo + np.array((sign * .04 * s, -.20 * s, -.02 * s))
            arm_bones = [body_i, B[f"arm_{side}"], B[f"forearm_{side}"]]
            mesh.tube([sh, (sh + fo) * .5, fo, (fo + hand) * .5, hand],
                      [(girth * .46, girth * .46), (girth * .38, girth * .38),
                       (girth * .33, girth * .33), (girth * .29, girth * .29),
                       (girth * .26, girth * .26)],
                      arm_bones, MAT_BODY, sides=9, cap_start=False,
                      cap_end=False)
            mesh.ellipsoid(tuple(sh), (girth * .70,) * 3, arm_bones, MAT_BODY,
                           rings=7, sides=10)
            palm = hand + np.array((0., -girth * .26, 0.))
            mesh.ellipsoid(tuple(palm), (girth * .30, girth * .36, girth * .22),
                           arm_bones, MAT_BODY, rings=6, sides=8)
            for k in range(3):
                tipp = palm + np.array((sign * girth * .04 + (k - 1) * girth * .16,
                                        -girth * .34, -girth * .06))
                mesh.tube([palm + np.array(((k - 1) * girth * .14,
                                            -girth * .16, 0.)), tipp],
                          [(girth * .085, girth * .085),
                           (girth * .055, girth * .055)],
                          arm_bones, MAT_BODY, sides=4)
        # A face, built the way the bipeds build theirs: brow, sockets, nose,
        # cheek and mouth, because shadow is what makes a face read at all.
        eye = hw * .17
        for sign in (-1., 1.):
            socket = g[head_i] + np.array((sign * hw * 1.05, hh * .30,
                                           -hl * 1.15))
            mesh.ellipsoid(tuple(socket), (eye * 2.4, eye * 2.1, eye * 1.5),
                           [head_i], MAT_DARK, rings=6, sides=9)
            mesh.ellipsoid(tuple(socket + np.array((0., 0., -eye * .55))),
                           (eye * 1.15, eye * 1.05, eye * .80),
                           [head_i], MAT_CORE, rings=5, sides=8)
            mesh.ellipsoid(tuple(g[head_i] + np.array((sign * hw * 1.45,
                                                       -hh * .28, -hl * .85))),
                           (hw * .48, hh * .40, hl * .70),
                           [head_i], MAT_BODY, rings=5, sides=9)
        brow = g[head_i] + np.array((0., hh * .92, -hl * 1.20))
        mesh.tube([brow + np.array((-hw * 1.30, -hh * .16, 0.)), brow,
                   brow + np.array((hw * 1.30, -hh * .16, 0.))],
                  [(hw * .22, hh * .18), (hw * .34, hh * .26),
                   (hw * .22, hh * .18)], [head_i], MAT_BODY, sides=6)
        mouth = g[head_i] + np.array((0., -hh * .82, -hl * 1.30))
        mesh.tube([mouth + np.array((-hw * .60, 0., 0.)), mouth,
                   mouth + np.array((hw * .60, 0., 0.))],
                  [(hw * .09, hh * .07), (hw * .15, hh * .11),
                   (hw * .09, hh * .07)], [head_i], MAT_DARK, sides=5)
    return mesh


def serpent_animation(plan_key: str, scale: float, bones, variant=None) -> dict:
    p = minor_config(SERPENT_PLANS, plan_key, variant)
    B = SERPENT_INDEX
    coils = [B[f"coil_{i + 1}"] for i in range(SERPENT_SEGMENTS)]
    heads = [(B["neck"], B["head"])]
    if p["heads"] >= 2:
        heads.append((B["neck_b"], B["head_b"]))
    if p["heads"] >= 3:
        heads.append((B["neck_c"], B["head_c"]))
    clips: dict[str, dict] = {}

    def wave_clip(duration, samples, amp, speed, head_amp):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            for k, bone in enumerate(coils):
                phase = 2 * math.pi * (u * speed - k * .16)
                tracks.setdefault((bone, "rotation"), []).append(
                    _euler(yaw=amp * math.sin(phase),
                           roll=amp * .25 * math.cos(phase)))
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(yaw=amp * .5 * math.sin(2 * math.pi * u * speed)))
            for neck_i, head_i in heads:
                tracks.setdefault((neck_i, "rotation"), []).append(
                    _euler(yaw=head_amp * math.sin(2 * math.pi * u * speed + 1.1),
                           pitch=head_amp * .4 * math.sin(4 * math.pi * u * speed)))
                tracks.setdefault((head_i, "rotation"), []).append(
                    _euler(yaw=-head_amp * .7 * math.sin(2 * math.pi * u * speed + 1.4)))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Idle_A"] = wave_clip(2.6, 16, .10, 1.0, .07)
    clips["Walk"] = wave_clip(1.2, 16, .26, 1.0, .10)
    clips["Jog"] = wave_clip(.72, 14, .36, 1.0, .14)
    clips["Fighting_Idle"] = wave_clip(1.5, 14, .16, 1.0, .20)

    stamp = [0., .16, .30, .44, .58, .80]
    attack = {}
    for neck_i, head_i in heads:
        attack[(neck_i, "rotation")] = [_euler(), _euler(pitch=.42), _euler(pitch=-.48),
                                        _euler(pitch=-.62), _euler(pitch=-.18), _euler()]
        attack[(head_i, "rotation")] = [_euler(), _euler(pitch=.26), _euler(pitch=-.30),
                                        _euler(pitch=-.16), _euler(pitch=.06), _euler()]
    attack[(B["jaw"], "rotation")] = [_euler(), _euler(pitch=.24), _euler(pitch=.70),
                                      _euler(pitch=.72), _euler(pitch=.06), _euler()]
    attack[(B["body"], "rotation")] = [_euler(), _euler(pitch=.14), _euler(pitch=-.16),
                                       _euler(pitch=-.20), _euler(pitch=-.06), _euler()]
    for k, bone in enumerate(coils):
        attack[(bone, "rotation")] = [_euler(), _euler(yaw=.16 - .03 * k),
                                      _euler(yaw=-.12), _euler(yaw=-.18),
                                      _euler(yaw=-.06), _euler()]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in attack.items()}

    hit_t = [0., .09, .20, .34, .48]
    hit = {(B["body"], "rotation"): [_euler(), _euler(roll=.24, pitch=.16),
                                     _euler(roll=.14, pitch=.10), _euler(roll=-.03),
                                     _euler()]}
    for neck_i, head_i in heads:
        hit[(neck_i, "rotation")] = [_euler(), _euler(pitch=.40, yaw=.22),
                                     _euler(pitch=.24), _euler(pitch=-.05), _euler()]
    for k, bone in enumerate(coils[:5]):
        hit[(bone, "rotation")] = [_euler(), _euler(yaw=.20 - .03 * k),
                                   _euler(yaw=.12), _euler(yaw=.03), _euler()]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in hit.items()}

    death_t = [0., .28, .56, .86, 1.14, 1.44]
    drop = -p["girth"] * scale * .55
    death = {(B["root"], "translation"): [[0., 0., 0.], [0., drop * .3, 0.],
                                          [0., drop * .7, 0.], [0., drop * .95, 0.],
                                          [0., drop, 0.], [0., drop, 0.]],
             (B["body"], "rotation"): [_euler(), _euler(roll=.30), _euler(roll=.72),
                                       _euler(roll=1.04), _euler(roll=1.20),
                                       _euler(roll=1.22)]}
    for neck_i, head_i in heads:
        death[(neck_i, "rotation")] = [_euler(), _euler(pitch=-.24), _euler(pitch=.30),
                                       _euler(pitch=.62), _euler(pitch=.78),
                                       _euler(pitch=.80)]
        death[(head_i, "rotation")] = [_euler(), _euler(pitch=-.10), _euler(pitch=.24),
                                       _euler(pitch=.44), _euler(pitch=.54),
                                       _euler(pitch=.56)]
    for k, bone in enumerate(coils):
        sway = .34 - .03 * k
        death[(bone, "rotation")] = [_euler(), _euler(yaw=sway * .4),
                                     _euler(yaw=sway * .8), _euler(yaw=sway),
                                     _euler(yaw=sway * 1.05), _euler(yaw=sway * 1.06)]
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in death.items()}
    return clips


FAMILIES["serpent"] = (serpent_skeleton, serpent_geometry, serpent_animation)


# ---------------------------------------------------------------------------
# Arachnid (spiders, scorpions, crabs)
# ---------------------------------------------------------------------------
ARACHNID_TABLE, ARACHNID_INDEX = _assemble(
    [("root", None), ("body", "root"), ("chest", "body"),
     ("neck", "chest"), ("head", "neck"), ("jaw", "head"),
     ("abdomen_1", "body"), ("abdomen_2", "abdomen_1"), ("abdomen_3", "abdomen_2")]
    + [(f"leg_{side}{i}{seg}", f"leg_{side}{i}a" if seg == "b"
        else (f"leg_{side}{i}b" if seg == "c" else "chest"))
       for side in ("l", "r") for i in range(1, 5) for seg in ("a", "b", "c")]
    + [("claw_l", "chest"), ("claw_r", "chest")])

ARACHNID_PLANS = {
    "spider": dict(cephalo=(.24, .16, .26), abdomen=(.30, .26, .34), stand=.30,
                   leg=.46, leg_r=.026, sting=False, claws=False, shell=False,
                   eyes=8, abdomen_back=.34, fang=.06),
    "scorpion": dict(cephalo=(.26, .14, .34), abdomen=(.24, .18, .34), stand=.22,
                     leg=.34, leg_r=.028, sting=True, claws=True, shell=True,
                     eyes=2, abdomen_back=.30, fang=.04),
    # A crab's carapace is half again as wide as it is long and it carries no
    # projecting head at all: the spider proportions and the spider head were
    # why every crab in the library read as a pale spider.
    "crab": dict(cephalo=(.62, .17, .40), abdomen=(.20, .09, .16), stand=.20,
                 leg=.38, leg_r=.030, sting=False, claws=True, shell=True,
                 eyes=2, abdomen_back=.14, fang=.0, eyestalks=True,
                 carapace="dome", claw_size=1.15),
}


def arachnid_skeleton(plan_key: str, scale: float, variant=None):
    p = minor_config(ARACHNID_PLANS, plan_key, variant)
    s = scale
    stand = p["stand"] * s
    body = np.array((0., stand, 0.))
    chest = body + np.array((0., .01 * s, -p["cephalo"][2] * s * .5))
    g = {"root": np.zeros(3), "body": body, "chest": chest,
         "neck": chest + np.array((0., .02 * s, -p["cephalo"][2] * s * .35)),
         "head": chest + np.array((0., .01 * s, -p["cephalo"][2] * s * .75))}
    g["jaw"] = g["head"] + np.array((0., -p["cephalo"][1] * s * .30,
                                     -p["cephalo"][2] * s * .22))
    # A crab's abdomen is folded flat under the carapace; trailing it behind
    # gave every crab a lobster's tail.
    back = p["abdomen_back"] * s * (-.35 if p.get("carapace") == "dome" else 1.0)
    for i in range(3):
        t = (i + 1) / 3
        lift = stand + (.10 * s if p["sting"] else 0.) * t ** 2
        g[f"abdomen_{i + 1}"] = body + np.array((0., lift - stand + .02 * s * t,
                                                 back * t + p["abdomen"][2] * s * .3))
    for side, sign in (("l", -1.), ("r", 1.)):
        for i in range(1, 5):
            spread = (-.34 + .30 * (i - 1))
            base = chest + np.array((sign * p["cephalo"][0] * s * .55,
                                     .0, spread * s * .34))
            knee = base + np.array((sign * p["leg"] * s * .46,
                                    p["leg"] * s * .30, spread * s * .22))
            foot = base + np.array((sign * p["leg"] * s * .86, -stand,
                                    spread * s * .40))
            g[f"leg_{side}{i}a"] = base
            g[f"leg_{side}{i}b"] = knee
            g[f"leg_{side}{i}c"] = foot
        # Held folded in front of the shell.  Out at .8 of a widened carapace
        # and .7 of its length forward, a crab's claws sat on long arms and the
        # animal read as a lobster.
        reach = .52 if p.get("carapace") == "dome" else .8
        g[f"claw_{side}"] = chest + np.array((sign * p["cephalo"][0] * s * reach,
                                              -.02 * s,
                                              -p["cephalo"][2] * s * reach * .78))
    return _bones_from(g, ARACHNID_TABLE)


def arachnid_geometry(plan_key: str, scale: float, bones, variant=None) -> AnatomyMesh:
    p = minor_config(ARACHNID_PLANS, plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = ARACHNID_INDEX
    mesh = AnatomyMesh(g)
    body_i, chest_i, head_i = B["body"], B["chest"], B["head"]
    ce = tuple(v * s for v in p["cephalo"])
    ab = tuple(v * s for v in p["abdomen"])

    mesh.ellipsoid(tuple(g[chest_i]), ce, [chest_i, body_i, head_i],
                   MAT_BODY, rings=10, sides=16, squash=.86 if p["shell"] else None)
    mesh.torso = ([g[chest_i], g[body_i]],
                  [(ce[0] * .5, ce[1] * .5), (ab[0] * .5, ab[1] * .5)],
                  [chest_i, body_i])
    if p["carapace"] == "dome":
        # One broad shell over the whole animal, with a lip around it: what
        # separates a crab's silhouette from a spider's is that the body is a
        # single plate and the legs come out from under its edge.
        mesh.ellipsoid(tuple(g[chest_i] + np.array((0., ce[1] * .30, 0.))),
                       (ce[0] * 1.34, ce[1] * 1.70, ce[2] * 1.46),
                       [chest_i, body_i], MAT_FEATURE, rings=10, sides=20,
                       squash=.80)
        rim = []
        for k in range(21):
            angle = 2 * math.pi * k / 20
            rim.append(g[chest_i] + np.array((math.cos(angle) * ce[0] * .58,
                                              ce[1] * .12,
                                              math.sin(angle) * ce[2] * .56)))
        mesh.tube(rim, [(ce[1] * .13, ce[1] * .10)] * 21, [chest_i, body_i],
                  MAT_FEATURE, sides=5, cap_start=False, cap_end=False)
    elif p["shell"]:
        mesh.ellipsoid(tuple(g[chest_i] + np.array((0., ce[1] * .22, 0.))),
                       (ce[0] * 1.10, ce[1] * .90, ce[2] * 1.05),
                       [chest_i, body_i], MAT_FEATURE, rings=9, sides=16)
    seg_bones = [body_i, B["abdomen_1"], B["abdomen_2"], B["abdomen_3"]]
    pts = [g[body_i]] + [g[B[f"abdomen_{i + 1}"]] for i in range(3)]
    if p["sting"]:
        widths = [(ab[0] * .5, ab[1] * .5), (ab[0] * .42, ab[1] * .42),
                  (ab[0] * .30, ab[1] * .30), (ab[0] * .20, ab[1] * .20)]
        mesh.tube(pts, widths, seg_bones, MAT_BODY, sides=12, uv_scale=1.6)
        barb = pts[-1] + np.array((0., .10 * s, .06 * s))
        mesh.spike(pts[-1], barb, ab[0] * .18, [B["abdomen_3"]], MAT_DARK, sides=8)
    else:
        mesh.ellipsoid(tuple((pts[1] + pts[3]) * .5),
                       (ab[0], ab[1], ab[2]), seg_bones, MAT_BODY,
                       rings=10, sides=16)
    if p["eyestalks"]:
        # Short stalks standing off the front of the shell, which is the one
        # feature that reads as "crab" from any angle at all.
        for side in (-1., 1.):
            base = g[chest_i] + np.array((side * ce[0] * .17, ce[1] * .34,
                                          -ce[2] * .46))
            top = base + np.array((side * .012 * s, ce[1] * .62, -ce[2] * .10))
            mesh.tube([base, top], [(ce[1] * .085, ce[1] * .085),
                                    (ce[1] * .065, ce[1] * .065)],
                      [chest_i, head_i], MAT_BODY, sides=6)
            mesh.ellipsoid(tuple(top + np.array((0., ce[1] * .06, 0.))),
                           (ce[1] * .13,) * 3, [chest_i, head_i], MAT_DARK,
                           rings=5, sides=8)
    else:
        for k in range(p["eyes"]):
            row = k // 4
            col = (k % 4) - 1.5
            mesh.ellipsoid(tuple(g[head_i] + np.array((col * ce[0] * .16,
                                                       ce[1] * (.22 - .16 * row),
                                                       -ce[2] * .30))),
                           (ce[0] * .09,) * 3, [head_i], MAT_DARK,
                           rings=5, sides=8)
    if p["fang"]:
        for side in (-1., 1.):
            base = g[head_i] + np.array((side * ce[0] * .20, -ce[1] * .28, -ce[2] * .28))
            mesh.spike(base, base + np.array((side * .01 * s, -p["fang"] * s, -.02 * s)),
                       ce[0] * .10, [B["jaw"], head_i], MAT_DARK, sides=6)
    for side, sign in (("l", -1.), ("r", 1.)):
        for i in range(1, 5):
            a = g[B[f"leg_{side}{i}a"]]
            b = g[B[f"leg_{side}{i}b"]]
            c = g[B[f"leg_{side}{i}c"]]
            lb = [chest_i, B[f"leg_{side}{i}a"], B[f"leg_{side}{i}b"],
                  B[f"leg_{side}{i}c"]]
            r = p["leg_r"] * s
            mesh.tube([a, (a + b) * .5, b, (b + c) * .5,
                       np.array((c[0], max(c[1], r * .9), c[2]))],
                      [(r * 1.5, r * 1.5), (r * 1.2, r * 1.2), (r, r),
                       (r * .8, r * .8), (r * .5, r * .5)],
                      lb, MAT_BODY, sides=7, cap_start=False)
        if p["claws"]:
            root = g[B[f"claw_{side}"]]
            inside = g[chest_i] + np.array((sign * ce[0] * .28, 0., -ce[2] * .18))
            elbow = root + np.array((sign * .03 * s, -.01 * s,
                                     -.10 * s * (.55 if p["carapace"] == "dome"
                                                 else 1.0)))
            r = p["leg_r"] * s
            mesh.tube([inside, (inside + root) * .5, root, elbow],
                      [(r * 2.4, r * 2.4), (r * 2.1, r * 2.1),
                       (r * 1.8, r * 1.8), (r * 1.5, r * 1.5)],
                      [chest_i, B[f"claw_{side}"]], MAT_BODY, sides=8,
                      cap_start=False, cap_end=False)
            claw = p["claw_size"]
            pincer = elbow + np.array((sign * .03 * s, 0., -.075 * s * claw))
            # The palm of the pincer, then the two fingers, one fixed and one
            # opposed.  At the old scale a crab's claws were smaller than its
            # walking legs, which is backwards.
            mesh.ellipsoid(tuple(pincer),
                           (.11 * s * claw, .07 * s * claw, .18 * s * claw),
                           [B[f"claw_{side}"]], MAT_FEATURE, rings=7, sides=10)
            for jaw in (-1., 1.):
                tipbase = pincer + np.array((0., jaw * .028 * s * claw,
                                             -.08 * s * claw))
                mesh.tube([tipbase,
                           tipbase + np.array((sign * .006 * s, jaw * .010 * s * claw,
                                               -.07 * s * claw)),
                           tipbase + np.array((sign * .010 * s, jaw * .004 * s * claw,
                                               -.13 * s * claw))],
                          [(.030 * s * claw, .030 * s * claw),
                           (.021 * s * claw, .021 * s * claw),
                           (.005 * s * claw, .005 * s * claw)],
                          [B[f"claw_{side}"]], MAT_FEATURE, sides=6)
    return mesh


def arachnid_animation(plan_key: str, scale: float, bones, variant=None) -> dict:
    p = minor_config(ARACHNID_PLANS, plan_key, variant)
    B = ARACHNID_INDEX
    legs = [(B[f"leg_{side}{i}a"], B[f"leg_{side}{i}b"], B[f"leg_{side}{i}c"],
             (i + (0 if side == "l" else 2)) % 4 / 4.0)
            for side in ("l", "r") for i in range(1, 5)]
    clips: dict[str, dict] = {}

    def scuttle(duration, samples, swing, lift, bob):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            tracks.setdefault((B["root"], "translation"), []).append(
                [0., bob * scale * abs(math.sin(4 * math.pi * u)), 0.])
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(roll=.03 * math.sin(2 * math.pi * u)))
            for a, b, c, phase in legs:
                cyc = 2 * math.pi * (u - phase)
                tracks.setdefault((a, "rotation"), []).append(
                    _euler(yaw=swing * math.sin(cyc)))
                tracks.setdefault((b, "rotation"), []).append(
                    _euler(pitch=-lift * max(0., math.sin(cyc + math.pi * .35))))
                tracks.setdefault((c, "rotation"), []).append(
                    _euler(pitch=lift * .5 * max(0., math.sin(cyc + math.pi * .35))))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Idle_A"] = scuttle(2.4, 12, .04, .05, .003)
    clips["Walk"] = scuttle(.90, 16, .22, .34, .014)
    clips["Jog"] = scuttle(.56, 14, .32, .46, .024)
    clips["Fighting_Idle"] = scuttle(1.4, 12, .10, .16, .010)

    stamp = [0., .14, .28, .42, .56, .76]
    attack = {(B["root"], "translation"): [[0., 0., 0.], [0., -.02 * scale, 0.],
                                          [0., .05 * scale, 0.], [0., .06 * scale, 0.],
                                          [0., .01 * scale, 0.], [0., 0., 0.]],
              (B["chest"], "rotation"): [_euler(), _euler(pitch=.18), _euler(pitch=-.24),
                                         _euler(pitch=-.30), _euler(pitch=-.08), _euler()],
              (B["head"], "rotation"): [_euler(), _euler(pitch=.12), _euler(pitch=-.20),
                                        _euler(pitch=-.10), _euler(), _euler()],
              (B["jaw"], "rotation"): [_euler(), _euler(pitch=.20), _euler(pitch=.56),
                                       _euler(pitch=.10), _euler(), _euler()]}
    if p["sting"]:
        for k, bone in enumerate(("abdomen_1", "abdomen_2", "abdomen_3")):
            attack[(B[bone], "rotation")] = [
                _euler(pitch=-.10 * k), _euler(pitch=-.40 - .12 * k),
                _euler(pitch=-.70 - .16 * k), _euler(pitch=.26),
                _euler(pitch=-.10), _euler(pitch=-.10 * k)]
    if p["claws"]:
        for side, sign in (("l", -1.), ("r", 1.)):
            attack[(B[f"claw_{side}"], "rotation")] = [
                _euler(), _euler(yaw=sign * .34), _euler(yaw=-sign * .30),
                _euler(yaw=-sign * .44), _euler(yaw=-sign * .12), _euler()]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in attack.items()}

    hit_t = [0., .09, .20, .34, .48]
    hit = {(B["body"], "rotation"): [_euler(), _euler(pitch=.20, roll=.16),
                                     _euler(pitch=.12, roll=.08), _euler(pitch=-.03),
                                     _euler()],
           (B["chest"], "rotation"): [_euler(), _euler(pitch=.24), _euler(pitch=.14),
                                      _euler(pitch=-.04), _euler()]}
    for a, b, c, _ in legs[:4]:
        hit[(a, "rotation")] = [_euler(), _euler(yaw=.20), _euler(yaw=.12),
                                _euler(yaw=.03), _euler()]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in hit.items()}

    death_t = [0., .26, .52, .82, 1.10, 1.36]
    drop = -p["stand"] * scale * .82
    death = {(B["root"], "translation"): [[0., 0., 0.], [0., drop * .3, 0.],
                                          [0., drop * .7, 0.], [0., drop * .94, 0.],
                                          [0., drop, 0.], [0., drop, 0.]],
             (B["body"], "rotation"): [_euler(), _euler(roll=.20), _euler(roll=.50),
                                       _euler(roll=.72), _euler(roll=.84),
                                       _euler(roll=.86)]}
    # Legs curl inward under the body, the way a dead arachnid actually ends up.
    for a, b, c, _ in legs:
        death[(a, "rotation")] = [_euler(), _euler(yaw=.16), _euler(yaw=.34),
                                  _euler(yaw=.48), _euler(yaw=.56), _euler(yaw=.57)]
        death[(b, "rotation")] = [_euler(), _euler(pitch=-.40), _euler(pitch=-.90),
                                  _euler(pitch=-1.24), _euler(pitch=-1.42),
                                  _euler(pitch=-1.44)]
        death[(c, "rotation")] = [_euler(), _euler(pitch=-.30), _euler(pitch=-.70),
                                  _euler(pitch=-.96), _euler(pitch=-1.10),
                                  _euler(pitch=-1.12)]
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in death.items()}
    return clips


FAMILIES["arachnid"] = (arachnid_skeleton, arachnid_geometry, arachnid_animation)


# ---------------------------------------------------------------------------
# Insect (beetles, moths, mantids)
# ---------------------------------------------------------------------------
INSECT_TABLE, INSECT_INDEX = _assemble(
    [("root", None), ("body", "root"), ("chest", "body"),
     ("neck", "chest"), ("head", "neck"), ("jaw", "head"),
     ("abdomen_1", "body"), ("abdomen_2", "abdomen_1"),
     ("wing_l", "chest"), ("wing_r", "chest"),
     ("hind_wing_l", "body"), ("hind_wing_r", "body")]
    + [(f"leg_{side}{i}{seg}", f"leg_{side}{i}a" if seg == "b" else "chest")
       for side in ("l", "r") for i in range(1, 4) for seg in ("a", "b")]
    + [("antenna_l", "head"), ("antenna_r", "head")])

INSECT_PLANS = {
    "beetle": dict(thorax=(.30, .23, .24), abdomen=(.34, .26, .32), stand=.14,
                   leg=.24, leg_r=.022, wings="shell", wing=.34, antenna=.12,
                   raptorial=False, head=(.12, .10, .11), horn=.10),
    "moth": dict(thorax=(.20, .19, .24), abdomen=(.16, .15, .32), stand=.16,
                 leg=.22, leg_r=.016, wings="broad", wing=.78, antenna=.22,
                 raptorial=False, head=(.12, .12, .12), horn=.0, wing_lift=.62),
    "mantis": dict(thorax=(.14, .14, .34), abdomen=(.16, .15, .34), stand=.34,
                   leg=.36, leg_r=.017, wings="folded", wing=.34, antenna=.24,
                   raptorial=True, head=(.13, .10, .11), horn=.0),
}


def insect_skeleton(plan_key: str, scale: float, variant=None):
    p = minor_config(INSECT_PLANS, plan_key, variant)
    s = scale
    stand = p["stand"] * s
    body = np.array((0., stand, 0.))
    chest = body + np.array((0., .01 * s, -p["thorax"][2] * s * .38))
    head = chest + np.array((0., .02 * s, -p["thorax"][2] * s * .40
                             - p["head"][2] * s * .55))
    g = {"root": np.zeros(3), "body": body, "chest": chest,
         "neck": (chest + head) * .5, "head": head,
         "jaw": head + np.array((0., -p["head"][1] * s * .5, -p["head"][2] * s * .4))}
    for i in range(2):
        g[f"abdomen_{i + 1}"] = body + np.array((0., -.01 * s * (i + 1),
                                                 p["abdomen"][2] * s * (.28 + .30 * i)))
    for side, sign in (("l", -1.), ("r", 1.)):
        g[f"wing_{side}"] = chest + np.array((sign * p["thorax"][0] * s * .5,
                                              p["thorax"][1] * s * .5, .02 * s))
        g[f"hind_wing_{side}"] = body + np.array((sign * p["thorax"][0] * s * .4,
                                                  p["thorax"][1] * s * .3,
                                                  p["abdomen"][2] * s * .25))
        g[f"antenna_{side}"] = head + np.array((sign * p["head"][0] * s * .4,
                                                p["head"][1] * s * .5,
                                                -p["head"][2] * s * .4))
        for i in range(1, 4):
            spread = -.30 + .30 * (i - 1)
            base = chest + np.array((sign * p["thorax"][0] * s * .6, 0., spread * s * .30))
            foot = base + np.array((sign * p["leg"] * s * .70, -stand, spread * s * .34))
            g[f"leg_{side}{i}a"] = base
            g[f"leg_{side}{i}b"] = foot
    return _bones_from(g, INSECT_TABLE)


def insect_geometry(plan_key: str, scale: float, bones, variant=None) -> AnatomyMesh:
    p = minor_config(INSECT_PLANS, plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = INSECT_INDEX
    mesh = AnatomyMesh(g)
    body_i, chest_i, head_i = B["body"], B["chest"], B["head"]
    th = tuple(v * s for v in p["thorax"])
    ab = tuple(v * s for v in p["abdomen"])
    hd = tuple(v * s for v in p["head"])

    if p["carapace"] == "crystal":
        facet_shell(mesh, g[chest_i], th, [chest_i, body_i, head_i], MAT_BODY,
                    seed=f"{variant or plan_key}:thorax", subdivisions=1,
                    relief=p["carapace_relief"] * .8, gap=.05,
                    core_material=MAT_CORE, core_scale=.95)
    else:
        mesh.ellipsoid(tuple(g[chest_i]), th, [chest_i, body_i, head_i], MAT_BODY,
                       rings=9, sides=14)
    mesh.torso = ([g[chest_i], g[body_i]],
                  [(th[0] * .5, th[1] * .5), (ab[0] * .5, ab[1] * .5)],
                  [chest_i, body_i])
    seg = [body_i, B["abdomen_1"], B["abdomen_2"]]
    pts = [g[body_i], g[B["abdomen_1"]], g[B["abdomen_2"]]]
    pts.append(pts[-1] + (pts[-1] - pts[-2]) * .6)
    mesh.tube(pts, [(ab[0] * .5, ab[1] * .5), (ab[0] * .55, ab[1] * .55),
                    (ab[0] * .40, ab[1] * .40), (ab[0] * .12, ab[1] * .12)],
              seg, MAT_BODY, sides=12, uv_scale=1.4)
    mesh.ellipsoid(tuple(g[head_i]), (hd[0] * 2, hd[1] * 2, hd[2] * 2),
                   [head_i, chest_i], MAT_BODY, rings=8, sides=12)
    for side in (-1., 1.):
        mesh.ellipsoid(tuple(g[head_i] + np.array((side * hd[0] * .85, hd[1] * .30,
                                                   -hd[2] * .30))),
                       (hd[0] * .95, hd[1] * .85, hd[2] * .85),
                       [head_i], MAT_DARK, rings=7, sides=10)
        ant = g[B[f"antenna_{'l' if side < 0 else 'r'}"]]
        tip = ant + np.array((side * p["antenna"] * s * .45, p["antenna"] * s * .55,
                              -p["antenna"] * s * .55))
        mesh.tube([ant, (ant + tip) * .5, tip],
                  [(.012 * s, .012 * s), (.008 * s, .008 * s), (.004 * s, .004 * s)],
                  [B[f"antenna_{'l' if side < 0 else 'r'}"], head_i], MAT_FEATURE,
                  sides=5)
    if p["horn"]:
        base = g[head_i] + np.array((0., hd[1] * .8, -hd[2] * .5))
        mesh.tube([base, base + np.array((0., p["horn"] * s * .6, -p["horn"] * s * .5)),
                   base + np.array((0., p["horn"] * s, -p["horn"] * s * .9))],
                  [(.024 * s, .024 * s), (.014 * s, .014 * s), (.005 * s, .005 * s)],
                  [head_i], MAT_FEATURE, sides=7)
    for side, sign in (("l", -1.), ("r", 1.)):
        for i in range(1, 4):
            a = g[B[f"leg_{side}{i}a"]]
            b = g[B[f"leg_{side}{i}b"]]
            lb = [chest_i, B[f"leg_{side}{i}a"], B[f"leg_{side}{i}b"]]
            r = p["leg_r"] * s
            knee = (a + b) * .5 + np.array((sign * .04 * s, p["leg"] * s * .30, 0.))
            if p["raptorial"] and i == 1:
                knee = a + np.array((sign * .10 * s, p["leg"] * s * .42, -.10 * s))
                b = a + np.array((sign * .12 * s, p["leg"] * s * .05, -p["leg"] * s * .60))
                r *= 1.9
            mesh.tube([a, knee, b, np.array((b[0], max(b[1], r * .8), b[2]))],
                      [(r * 1.5, r * 1.5), (r * 1.1, r * 1.1), (r * .8, r * .8),
                       (r * .5, r * .5)],
                      lb, MAT_BODY, sides=6, cap_start=False)
        wing_i = B[f"wing_{side}"]
        wr = g[wing_i]
        span = p["wing"] * s
        if p["wings"] == "broad":
            # Fore and hind wing pairs, angled back and cambered, rather than
            # one flat plate per side.
            # A moth at rest in the art holds its wings up and open, so they
            # are the biggest thing about it from the front.  Laid almost flat
            # -- .22 of a scale unit of rise across a whole span of reach --
            # they vanished to a line in profile and read as two slabs in
            # three-quarter.  ``wing_lift`` opens them.
            lift = p["wing_lift"] * span
            tip = wr + np.array((sign * span * .74, .22 * s + lift * .92, -span * .30))
            rear = wr + np.array((sign * span * .54, .02 * s + lift * .62, span * .56))
            edge_a = [wr,
                      wr + np.array((sign * span * .30, .12 * s + lift * .34, -span * .44)),
                      wr + np.array((sign * span * .64, .12 * s + lift * .74, -span * .48)),
                      tip]
            edge_b = [wr + np.array((0., -.01 * s, span * .12)),
                      wr + np.array((sign * span * .30, lift * .26, span * .44)),
                      wr + np.array((sign * span * .54, -.01 * s + lift * .52, span * .58)),
                      rear]
            fore_a = [_bezier(edge_a, t) for t in np.linspace(0, 1, 7)]
            fore_b = [_bezier(edge_b, t) for t in np.linspace(0, 1, 7)]
            # Camber: a moth wing is a curved membrane.  Flat sheets caught the
            # light as one solid slab of colour from every angle.
            for k in range(1, len(fore_a) - 1):
                lift = math.sin(math.pi * k / (len(fore_a) - 1)) * .07 * s
                fore_a[k] = fore_a[k] + np.array((0., lift, 0.))
                fore_b[k] = fore_b[k] + np.array((0., lift * .6, 0.))
            _sheet(mesh, fore_a, fore_b, .008 * s, [wing_i, chest_i], MAT_ACCENT)
            if p["wing_facets"]:
                # A crystal moth's wing is leaded glass: bright veins dividing
                # it into panes.  Drawn in MAT_DARK it was a plain coloured
                # triangle with three grey lines on it.
                for k in range(1, len(fore_a) - 1):
                    clear = np.array((0., .0045 * s, 0.))
                    mesh.tube([fore_a[0] * .70 + fore_b[0] * .30 + clear,
                               (fore_a[k] * .62 + fore_b[k] * .38) + clear,
                               fore_a[k] * .12 + fore_b[k] * .88 + clear],
                              [(.014 * s, .010 * s), (.009 * s, .007 * s),
                               (.005 * s, .005 * s)],
                              [wing_i, chest_i], MAT_CORE, sides=4)
                # Cross-ribs close the panes so the glow reads as a lattice
                # rather than as a fan of separate spokes.
                for k in (2, 4):
                    up = np.array((0., .0045 * s, 0.))
                    rib = [fore_a[k] + up, (fore_a[k] + fore_b[k]) * .5 + up,
                           fore_b[k] + up]
                    mesh.tube(rib, [(.006 * s, .005 * s), (.008 * s, .006 * s),
                                    (.006 * s, .005 * s)],
                              [wing_i, chest_i], MAT_CORE, sides=4)
            else:
                # Veins and an eyespot: the two things that make a wing read as
                # a wing rather than a coloured triangle at gameplay distance.
                for k in (1, 3, 5):
                    mesh.tube([fore_a[0] * .82 + fore_b[0] * .18,
                               (fore_a[k] + fore_b[k]) * .5,
                               fore_a[k] * .30 + fore_b[k] * .70],
                              [(.011 * s, .008 * s), (.007 * s, .006 * s),
                               (.004 * s, .004 * s)],
                              [wing_i, chest_i], MAT_DARK, sides=4)
                eye = (fore_a[4] + fore_b[4]) * .5 + np.array((0., .012 * s, 0.))
                mesh.ellipsoid(tuple(eye), (span * .13, .010 * s, span * .13),
                               [wing_i, chest_i], MAT_DARK, rings=4, sides=10)
                mesh.ellipsoid(tuple(eye + np.array((0., .010 * s, 0.))),
                               (span * .075, .008 * s, span * .075),
                               [wing_i, chest_i], MAT_FEATURE, rings=4, sides=8)
            hind = B[f"hind_wing_{side}"]
            hg = g[hind]
            edge_c = [hg,
                      hg + np.array((sign * span * .36, lift * .34, span * .18)),
                      hg + np.array((sign * span * .48, lift * .58 - .02 * s,
                                     span * .48))]
            edge_d = [hg + np.array((0., -.01 * s, span * .16)),
                      hg + np.array((sign * span * .23, lift * .24 - .02 * s,
                                     span * .40)),
                      hg + np.array((sign * span * .30, lift * .40 - .03 * s,
                                     span * .62))]
            _sheet(mesh, edge_c, edge_d, .007 * s, [hind, body_i], MAT_ACCENT)
        else:
            # Beetle elytra and folded mantis wings lie along the abdomen.
            length = span * (1.15 if p["wings"] == "shell" else 1.0)
            dome = p["dome"]
            seat = wr + np.array((sign * th[0] * .18, -.01 * s, length * .42))
            size = (th[0] * .95 * dome, th[1] * .80 * dome * 1.25, length * .95)
            bones = [wing_i, chest_i, body_i]
            if p["carapace"] == "crystal":
                # The art's beetle is a mosaic of hard plates with the light
                # trapped under them; routing the elytra through MAT_FEATURE
                # painted it bone-white, which is the one colour a crystal
                # carapace is never.
                facet_shell(mesh, seat, size, bones, MAT_BODY,
                            seed=f"{variant or plan_key}:elytra:{sign:+.0f}",
                            subdivisions=2, relief=p["carapace_relief"],
                            gap=.055, core_material=MAT_CORE, core_scale=.94)
            elif p["carapace"]:
                # A bronze diving beetle's shell is bronze.  Through the
                # keratin material it came out as a white ribbed loaf sitting
                # on the abdomen, which is not a colour any beetle is.
                mesh.ellipsoid(tuple(seat), size, bones, MAT_BODY,
                               rings=9, sides=14)
                mesh.ellipsoid(tuple(seat + np.array((0., size[1] * .10, 0.))),
                               (size[0] * .84, size[1] * .86, size[2] * .90),
                               bones, MAT_ACCENT, rings=7, sides=12)
            else:
                mesh.ellipsoid(tuple(seat), size, bones,
                               MAT_FEATURE if p["wings"] == "shell" else MAT_ACCENT,
                               rings=8, sides=12)
    return mesh


def insect_animation(plan_key: str, scale: float, bones, variant=None) -> dict:
    p = minor_config(INSECT_PLANS, plan_key, variant)
    B = INSECT_INDEX
    legs = [(B[f"leg_{side}{i}a"], B[f"leg_{side}{i}b"],
             ((i - 1) + (0 if side == "l" else 1)) % 2 / 2.0)
            for side in ("l", "r") for i in range(1, 4)]
    wings = [(B["wing_l"], -1.), (B["wing_r"], 1.)]
    clips: dict[str, dict] = {}

    def gait(duration, samples, swing, lift, flutter):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            tracks.setdefault((B["root"], "translation"), []).append(
                [0., .006 * scale * abs(math.sin(4 * math.pi * u)), 0.])
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(roll=.04 * math.sin(2 * math.pi * u)))
            tracks.setdefault((B["head"], "rotation"), []).append(
                _euler(yaw=.10 * math.sin(2 * math.pi * u)))
            for a, b, phase in legs:
                c = 2 * math.pi * (u - phase)
                tracks.setdefault((a, "rotation"), []).append(
                    _euler(yaw=swing * math.sin(c)))
                tracks.setdefault((b, "rotation"), []).append(
                    _euler(pitch=-lift * max(0., math.sin(c + math.pi * .3))))
            for bone, sign in wings:
                tracks.setdefault((bone, "rotation"), []).append(
                    _euler(roll=sign * flutter * abs(math.sin(8 * math.pi * u))))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Idle_A"] = gait(2.2, 12, .05, .06, .04)
    clips["Walk"] = gait(.86, 16, .24, .34, .06)
    clips["Jog"] = gait(.52, 14, .34, .46, .55)
    clips["Fighting_Idle"] = gait(1.3, 12, .10, .14, .12)

    stamp = [0., .14, .28, .42, .58, .78]
    attack = {(B["chest"], "rotation"): [_euler(), _euler(pitch=.16), _euler(pitch=-.22),
                                         _euler(pitch=-.28), _euler(pitch=-.08), _euler()],
              (B["head"], "rotation"): [_euler(), _euler(pitch=.14), _euler(pitch=-.18),
                                        _euler(pitch=-.08), _euler(), _euler()],
              (B["jaw"], "rotation"): [_euler(), _euler(pitch=.24), _euler(pitch=.54),
                                       _euler(pitch=.08), _euler(), _euler()]}
    if p["raptorial"]:
        for side, sign in (("l", -1.), ("r", 1.)):
            attack[(B[f"leg_{side}1a"], "rotation")] = [
                _euler(), _euler(pitch=-.60), _euler(pitch=.55), _euler(pitch=.70),
                _euler(pitch=.10), _euler()]
            attack[(B[f"leg_{side}1b"], "rotation")] = [
                _euler(), _euler(pitch=-.80), _euler(pitch=.30), _euler(pitch=.44),
                _euler(pitch=.05), _euler()]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in attack.items()}

    hit_t = [0., .09, .20, .34, .48]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in {
        (B["body"], "rotation"): [_euler(), _euler(pitch=.20, roll=.18),
                                  _euler(pitch=.12, roll=.09), _euler(pitch=-.03),
                                  _euler()],
        (B["chest"], "rotation"): [_euler(), _euler(pitch=.24), _euler(pitch=.14),
                                   _euler(pitch=-.04), _euler()],
        (B["wing_l"], "rotation"): [_euler(), _euler(roll=-.40), _euler(roll=-.20),
                                    _euler(roll=-.06), _euler()],
        (B["wing_r"], "rotation"): [_euler(), _euler(roll=.40), _euler(roll=.20),
                                    _euler(roll=.06), _euler()],
    }.items()}

    death_t = [0., .24, .50, .80, 1.08, 1.34]
    drop = -p["stand"] * scale * .78
    death = {(B["root"], "translation"): [[0., 0., 0.], [0., drop * .3, 0.],
                                          [0., drop * .7, 0.], [0., drop * .94, 0.],
                                          [0., drop, 0.], [0., drop, 0.]],
             (B["body"], "rotation"): [_euler(), _euler(roll=.40), _euler(roll=1.10),
                                       _euler(roll=1.90), _euler(roll=2.40),
                                       _euler(roll=2.48)]}
    for a, b, _ in legs:
        death[(a, "rotation")] = [_euler(), _euler(yaw=.20), _euler(yaw=.42),
                                  _euler(yaw=.58), _euler(yaw=.66), _euler(yaw=.67)]
        death[(b, "rotation")] = [_euler(), _euler(pitch=-.50), _euler(pitch=-1.05),
                                  _euler(pitch=-1.40), _euler(pitch=-1.56),
                                  _euler(pitch=-1.58)]
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in death.items()}
    return clips


FAMILIES["insect"] = (insect_skeleton, insect_geometry, insect_animation)


# ---------------------------------------------------------------------------
# Fish
# ---------------------------------------------------------------------------
FISH_TABLE, FISH_INDEX = _assemble(
    [("root", None), ("body", "root"), ("chest", "body"),
     ("neck", "chest"), ("head", "neck"), ("jaw", "head")]
    + [(f"spine_{i + 1}", "body" if i == 0 else f"spine_{i}") for i in range(5)]
    + [("fin_l", "chest"), ("fin_r", "chest"), ("dorsal", "body")])

FISH_PLANS = {
    "pike": dict(length=.92, girth=(.13, .17), head=(.11, .13, .22), bill=.0,
                 tail=.26, fin=.20, dorsal=.14, disc=False, gills=False, jaw=.16),
    "billfish": dict(length=1.10, girth=(.14, .22), head=(.12, .16, .24), bill=.34,
                     tail=.34, fin=.30, dorsal=.28, disc=False, gills=False, jaw=.10),
    "armored": dict(length=.86, girth=(.17, .21), head=(.14, .15, .20), bill=.0,
                    tail=.24, fin=.24, dorsal=.16, disc=False, gills=False, jaw=.14),
    # A manta is nearly all wing: the art draws a flat diamond half again as
    # wide as it is long, trailing a whip.  At .42 girth against .70 length it
    # was a torpedo with a slight bulge.
    "ray": dict(length=.62, girth=(.80, .07), head=(.16, .06, .15), bill=.0,
                tail=.34, fin=.96, dorsal=.0, disc=True, gills=False, jaw=.06),
    "axolotl": dict(length=.80, girth=(.12, .13), head=(.14, .11, .16), bill=.0,
                    tail=.28, fin=.16, dorsal=.12, disc=False, gills=True, jaw=.10),
}


def fish_skeleton(plan_key: str, scale: float, variant=None):
    p = minor_config(FISH_PLANS, plan_key, variant)
    s = scale
    # Ride high enough that the caudal fin clears the floor rather than sinking
    # through it; these creatures swim just above the ground.
    rest = max(p["girth"][1] * s * 1.15, p["tail"] * s * .86, .10 * s)
    body = np.array((0., rest, 0.))
    chest = body + np.array((0., .0, -p["length"] * s * .22))
    head = chest + np.array((0., .0, -p["length"] * s * .22 - p["head"][2] * s * .6))
    g = {"root": np.zeros(3), "body": body, "chest": chest,
         "neck": (chest + head) * .5, "head": head,
         "jaw": head + np.array((0., -p["head"][1] * s * .40, -p["head"][2] * s * .40))}
    for i in range(5):
        t = (i + 1) / 5
        g[f"spine_{i + 1}"] = body + np.array((0., .01 * s * t,
                                               p["length"] * s * .62 * t))
    for side, sign in (("l", -1.), ("r", 1.)):
        g[f"fin_{side}"] = chest + np.array((sign * p["girth"][0] * s * .8,
                                             -p["girth"][1] * s * .2, .02 * s))
    g["dorsal"] = body + np.array((0., p["girth"][1] * s * .9, -.02 * s))
    return _bones_from(g, FISH_TABLE)


def fish_geometry(plan_key: str, scale: float, bones, variant=None) -> AnatomyMesh:
    p = minor_config(FISH_PLANS, plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = FISH_INDEX
    mesh = AnatomyMesh(g)
    body_i, chest_i, head_i, jaw_i = B["body"], B["chest"], B["head"], B["jaw"]
    gw, gh = (v * s for v in p["girth"])
    hd = tuple(v * s for v in p["head"])
    spine_bones = [body_i] + [B[f"spine_{i + 1}"] for i in range(5)]

    pts = [g[head_i] + np.array((0., 0., -hd[2] * .25)),
           (g[head_i] + g[chest_i]) * .5, g[chest_i], g[body_i]] \
        + [g[B[f"spine_{i + 1}"]] for i in range(5)]
    tail_tip = pts[-1] + (pts[-1] - pts[-2]) * .8
    pts.append(tail_tip)
    widths = []
    for i, _ in enumerate(pts):
        t = i / (len(pts) - 1)
        # Narrow at the snout, deepest just behind the gills, tapering to the tail.
        swell = math.sin(min(t * 1.55 + .22, 1.) * math.pi) * .52 + .58
        widths.append((gw * swell * (1 - .66 * max(t - .30, 0.) ** 2),
                       gh * swell * (1 - .58 * max(t - .30, 0.) ** 2)))
    mesh.torso = (list(pts), list(widths), [head_i, chest_i] + spine_bones)
    mesh.tube(pts, widths, [head_i, chest_i] + spine_bones, MAT_BODY, sides=14,
              uv_scale=2.0,
              lower_material=MAT_ACCENT, lower_threshold=-.36)
    mesh.ellipsoid(tuple(g[head_i]), (hd[0] * 2, hd[1] * 2, hd[2] * 2),
                   [head_i, chest_i], MAT_BODY, rings=9, sides=14)
    if p["bill"]:
        tipp = g[head_i] + np.array((0., 0., -hd[2] - p["bill"] * s))
        mesh.tube([g[head_i] + np.array((0., 0., -hd[2] * .6)), tipp],
                  [(hd[0] * .55, hd[1] * .55), (hd[0] * .08, hd[1] * .08)],
                  [head_i], MAT_FEATURE, sides=8, cap_start=False)
    else:
        mesh.tube([g[head_i] + np.array((0., -hd[1] * .2, -hd[2] * .5)),
                   g[head_i] + np.array((0., -hd[1] * .4, -hd[2] * 1.35))],
                  [(hd[0] * 1.2, hd[1] * .9), (hd[0] * .7, hd[1] * .5)],
                  [head_i, jaw_i], MAT_BODY, sides=10, cap_start=False)
    for side in (-1., 1.):
        mesh.ellipsoid(tuple(g[head_i] + np.array((side * hd[0] * 1.05, hd[1] * .35,
                                                   -hd[2] * .30))),
                       (hd[0] * .40,) * 3, [head_i], MAT_DARK, rings=6, sides=10)
    if p["gills"]:
        # Three thin spikes a tenth of a unit long were whiskers.  An axolotl's
        # external gills are the biggest thing on its head: three stalks a side
        # carrying a fan of filaments, and they are the whole silhouette.
        for side in (-1., 1.):
            base = g[head_i] + np.array((side * hd[0] * .95, hd[1] * .45,
                                         hd[2] * .55))
            for k in range(3):
                lean = (k - 1) * .38
                stalk = base + np.array((side * .20 * s,
                                         (.20 - .11 * k) * s,
                                         (.10 + .10 * k) * s))
                mesh.tube([base, (base + stalk) * .5, stalk],
                          [(.026 * s, .026 * s), (.019 * s, .019 * s),
                           (.011 * s, .011 * s)],
                          [head_i, chest_i], MAT_ACCENT, sides=5)
                # Filaments fanning off the stalk.
                for f in range(5):
                    t = (f + .5) / 5.0
                    seat = base * (1 - t) + stalk * t
                    spray = np.array((side * (.055 + .045 * t) * s,
                                      (.075 - .050 * t + lean * .04) * s,
                                      (.030 + .060 * t) * s))
                    mesh.tube([seat, seat + spray * .55, seat + spray],
                              [(.013 * s, .013 * s), (.009 * s, .009 * s),
                               (.003 * s, .003 * s)],
                              [head_i, chest_i], MAT_ACCENT, sides=4)
    # Tail fin, pectorals and dorsal as thin membranes.
    tail = p["tail"] * s
    # A forked caudal fin with a concave trailing edge, not a flat paddle.
    # Two control points made one quad, and a rectangle on the back of a
    # torpedo is the single most model-looking thing about a fish.
    root = pts[-2]
    upper = [root,
             tail_tip + np.array((0., tail * .34, tail * .18)),
             tail_tip + np.array((0., tail * .96, tail * .62))]
    lower = [root,
             tail_tip + np.array((0., -tail * .34, tail * .18)),
             tail_tip + np.array((0., -tail * .96, tail * .62))]
    # The notch: the middle of the trailing edge cuts back toward the body.
    notch = [root,
             tail_tip + np.array((0., 0., tail * .04)),
             tail_tip + np.array((0., 0., tail * .16))]
    for lobe in (upper, lower):
        _sheet(mesh, [_bezier(lobe, t) for t in np.linspace(0, 1, 6)],
               [_bezier(notch, t) for t in np.linspace(0, 1, 6)],
               .010 * s, spine_bones, MAT_ACCENT)
    # A stiffening ray down the leading edge of each lobe.
    for lobe in (upper, lower):
        mesh.tube([_bezier(lobe, t) for t in np.linspace(0, 1, 5)],
                  [(tail * .048, tail * .030), (tail * .040, tail * .026),
                   (tail * .032, tail * .020), (tail * .024, tail * .015),
                   (tail * .012, tail * .008)],
                  spine_bones, MAT_ACCENT, sides=4)
    for side, sign in (("l", -1.), ("r", 1.)):
        base = g[B[f"fin_{side}"]]
        fin = p["fin"] * s
        if p["disc"]:
            # A ray is mostly wing: sweep a broad pectoral disc from snout to tail.
            nose = g[head_i] + np.array((0., 0., -hd[2] * .5))
            tail = g[B["spine_2"]]
            # A manta's wing is a swept diamond: the leading edge runs almost
            # straight out from the nose, the tip is carried well back, and the
            # trailing edge cuts in concave to the tail.  Bulging widest at the
            # middle and tapering both ways gives an oval, which is a skate.
            outer = [nose,
                     g[chest_i] + np.array((sign * fin * .82, .0, fin * .10)),
                     g[body_i] + np.array((sign * fin * 1.32, .0, fin * .52)),
                     tail + np.array((sign * fin * .58, .0, fin * .40))]
            inner = [nose, g[chest_i], g[body_i] + np.array((0., 0., fin * .06)),
                     tail]
            _sheet(mesh, [_bezier(outer, t) for t in np.linspace(0, 1, 11)],
                   [_bezier(inner, t) for t in np.linspace(0, 1, 11)],
                   gh * .55, [B[f"fin_{side}"], chest_i, body_i, head_i], MAT_BODY)
            # A thickened leading edge, and the cephalic lobe at the mouth --
            # the pair of horns that say "manta" before anything else does.
            mesh.tube([_bezier(outer, t) for t in np.linspace(0, .75, 5)],
                      [(gh * .52, gh * .40), (gh * .44, gh * .32),
                       (gh * .32, gh * .22), (gh * .20, gh * .13),
                       (gh * .10, gh * .07)],
                      [B[f"fin_{side}"], chest_i, head_i], MAT_BODY, sides=6)
            lobe = nose + np.array((sign * hd[0] * .70, 0., -hd[2] * .30))
            mesh.tube([lobe, lobe + np.array((sign * hd[0] * .30, -hd[1] * .20,
                                              -hd[2] * .95))],
                      [(hd[0] * .30, hd[1] * .55), (hd[0] * .14, hd[1] * .26)],
                      [head_i, chest_i], MAT_BODY, sides=6)
        else:
            # Swept back and down, and long enough to see: at .9 of the fin
            # measure across a body twice that long they were tabs.
            edge_a = [base,
                      base + np.array((sign * fin * .85, -fin * .30, fin * .34)),
                      base + np.array((sign * fin * 1.45, -fin * .62, fin * .92))]
            edge_b = [base + np.array((0., -fin * .05, fin * .38)),
                      base + np.array((sign * fin * .55, -fin * .34, fin * .78)),
                      base + np.array((sign * fin * .80, -fin * .52, fin * 1.18))]
            _sheet(mesh, [_bezier(edge_a, t) for t in np.linspace(0, 1, 6)],
                   [_bezier(edge_b, t) for t in np.linspace(0, 1, 6)],
                   .008 * s, [B[f"fin_{side}"], chest_i], MAT_ACCENT)
            mesh.tube([_bezier(edge_a, t) for t in np.linspace(0, 1, 4)],
                      [(fin * .045, fin * .028), (fin * .034, fin * .021),
                       (fin * .024, fin * .015), (fin * .010, fin * .007)],
                      [B[f"fin_{side}"], chest_i], MAT_ACCENT, sides=4)
    if p["dorsal"]:
        d = p["dorsal"] * s
        # A long swept dorsal running most of the back, with an anal fin under
        # the tail to match.  A short stub over the shoulders read as a shark
        # fin glued to a submarine.
        ridge = [g[chest_i] + np.array((0., gh * .92, 0.)),
                 g[body_i] + np.array((0., gh * .96, 0.)),
                 g[B["spine_2"]] + np.array((0., gh * .86, 0.)),
                 g[B["spine_4"]] + np.array((0., gh * .70, 0.))]
        crest = [point + np.array((0., d * math.sin(math.pi * (.20 + .62 * k / 3)),
                                   d * .34 * (k / 3.0)))
                 for k, point in enumerate(ridge)]
        _sheet(mesh, [_bezier(crest, t) for t in np.linspace(0, 1, 7)],
               [_bezier(ridge, t) for t in np.linspace(0, 1, 7)],
               .009 * s, spine_bones, MAT_ACCENT)
        belly = [g[body_i] + np.array((0., -gh * .92, 0.)),
                 g[B["spine_3"]] + np.array((0., -gh * .78, 0.))]
        under = [point + np.array((0., -d * .60, d * .30)) for point in belly]
        _sheet(mesh, [_bezier(under, t) for t in np.linspace(0, 1, 5)],
               [_bezier(belly, t) for t in np.linspace(0, 1, 5)],
               .009 * s, spine_bones, MAT_ACCENT)
        top_a = [g[body_i] + np.array((0., gh * .9, -gw * .4)),
                 g[B["spine_2"]] + np.array((0., gh * .8, 0.))]
        top_b = [g[body_i] + np.array((0., gh * .9 + d, -gw * .1)),
                 g[B["spine_2"]] + np.array((0., gh * .8 + d * .5, 0.))]
        _sheet(mesh, top_a, top_b, .008 * s, [B["dorsal"], body_i], MAT_ACCENT)
    return mesh


def fish_animation(plan_key: str, scale: float, bones, variant=None) -> dict:
    p = minor_config(FISH_PLANS, plan_key, variant)
    B = FISH_INDEX
    spine = [B[f"spine_{i + 1}"] for i in range(5)]
    clips: dict[str, dict] = {}

    def swim(duration, samples, amp, head_amp, roll):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            tracks.setdefault((B["root"], "translation"), []).append(
                [0., .010 * scale * math.sin(2 * math.pi * u), 0.])
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(yaw=amp * .4 * math.sin(2 * math.pi * u), roll=roll * math.sin(2 * math.pi * u)))
            for k, bone in enumerate(spine):
                phase = 2 * math.pi * (u - k * .13)
                tracks.setdefault((bone, "rotation"), []).append(
                    _euler(yaw=amp * (.5 + .16 * k) * math.sin(phase)))
            tracks.setdefault((B["head"], "rotation"), []).append(
                _euler(yaw=-head_amp * math.sin(2 * math.pi * u + .8)))
            for side, sign in (("l", -1.), ("r", 1.)):
                tracks.setdefault((B[f"fin_{side}"], "rotation"), []).append(
                    _euler(roll=sign * (.10 + .12 * math.sin(2 * math.pi * u))))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Idle_A"] = swim(2.4, 14, .07, .05, .02)
    clips["Walk"] = swim(1.1, 16, .17, .10, .05)
    clips["Jog"] = swim(.62, 14, .27, .16, .09)
    clips["Fighting_Idle"] = swim(1.4, 12, .12, .16, .06)

    stamp = [0., .14, .28, .42, .58, .78]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in {
        (B["body"], "rotation"): [_euler(), _euler(yaw=.30), _euler(yaw=-.26),
                                  _euler(yaw=-.34), _euler(yaw=-.10), _euler()],
        (B["head"], "rotation"): [_euler(), _euler(yaw=.22, pitch=.10),
                                  _euler(yaw=-.20, pitch=-.16), _euler(yaw=-.10),
                                  _euler(), _euler()],
        (B["jaw"], "rotation"): [_euler(), _euler(pitch=.24), _euler(pitch=.58),
                                 _euler(pitch=.10), _euler(), _euler()],
        (B["spine_1"], "rotation"): [_euler(), _euler(yaw=.24), _euler(yaw=-.20),
                                     _euler(yaw=-.28), _euler(yaw=-.08), _euler()],
        (B["spine_3"], "rotation"): [_euler(), _euler(yaw=.30), _euler(yaw=-.24),
                                     _euler(yaw=-.34), _euler(yaw=-.10), _euler()],
    }.items()}

    hit_t = [0., .09, .20, .34, .48]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in {
        (B["body"], "rotation"): [_euler(), _euler(roll=.30, yaw=.22),
                                  _euler(roll=.18, yaw=.12), _euler(roll=-.04), _euler()],
        (B["head"], "rotation"): [_euler(), _euler(yaw=.30), _euler(yaw=.16),
                                  _euler(yaw=-.04), _euler()],
        (B["spine_2"], "rotation"): [_euler(), _euler(yaw=.26), _euler(yaw=.14),
                                     _euler(yaw=.03), _euler()],
    }.items()}

    death_t = [0., .26, .52, .82, 1.10, 1.38]
    drop = -max(p["girth"][1] * .55, .04) * scale
    death = {(B["root"], "translation"): [[0., 0., 0.], [0., drop * .3, 0.],
                                          [0., drop * .7, 0.], [0., drop * .94, 0.],
                                          [0., drop, 0.], [0., drop, 0.]],
             # Fish roll belly-up as they die.
             (B["body"], "rotation"): [_euler(), _euler(roll=.60), _euler(roll=1.60),
                                       _euler(roll=2.50), _euler(roll=3.00),
                                       _euler(roll=3.08)],
             (B["head"], "rotation"): [_euler(), _euler(pitch=-.10), _euler(pitch=.10),
                                       _euler(pitch=.22), _euler(pitch=.28),
                                       _euler(pitch=.29)]}
    for k, bone in enumerate(spine):
        death[(bone, "rotation")] = [_euler(), _euler(yaw=.10 + .02 * k),
                                     _euler(yaw=.20 + .04 * k), _euler(yaw=.26 + .05 * k),
                                     _euler(yaw=.30 + .05 * k), _euler(yaw=.31 + .05 * k)]
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in death.items()}
    return clips


FAMILIES["fish"] = (fish_skeleton, fish_geometry, fish_animation)


# ---------------------------------------------------------------------------
# Amorphous (swarms, spectres, jellies, krakens, nymphs, oozes, vortices)
# ---------------------------------------------------------------------------
# These creatures have no skeleton in the concept art at all: they are clouds
# of shards, rising plumes of flame, bells trailing tentacles, or a torso
# dissolving into a swirl of water.  One shared "core plus legs" rig cannot
# express any of them, so the family carries eight distinct forms and a
# per-creature detail table, the same way the humanoids do.
# Raised from eight: the will-o-wisp and the water elemental are drawn with
# more streamers than that, and capping the count made them read sparse.
# Unused chains cost three bones and no geometry.
AMORPHOUS_TENDRILS = 10
AMORPHOUS_TABLE, AMORPHOUS_INDEX = _assemble(
    [("root", None), ("body", "root"), ("chest", "body"),
     ("neck", "chest"), ("head", "neck"), ("jaw", "head")]
    + [(f"tendril_{i + 1}{seg}",
        "body" if seg == "a" else f"tendril_{i + 1}{'a' if seg == 'b' else 'b'}")
       for i in range(AMORPHOUS_TENDRILS) for seg in ("a", "b", "c")]
    + [("orb_1", "chest"), ("orb_2", "chest"), ("orb_3", "chest"),
       ("wing_l", "chest"), ("wing_r", "chest"), ("prop_r", "chest")])


def _amorph(**over) -> dict:
    base = dict(
        form="spectre", core=.17, hover=.80, tendril=.52, tendril_r=.034,
        count=6, orbs=0, orb_r=.055, wings=False, face=True, head=.11,
        maw=False, prop=None, motes=0, mote_r=.05, translucent=.72,
        glow=.55, spread=1.0, rise=.0, drape=.0, surface="energy",
    )
    base.update(over)
    return base


AMORPHOUS_PLANS = {
    # A cloud of discrete pieces with no solid body at all.
    "shards": _amorph(form="swarm", core=.09, hover=.86, count=4, motes=17,
                      mote_r=.085, tendril=.20, face=False, glow=.70,
                      surface="crystal", translucent=.85),
    # A rising plume of flame or spirit-light trailing long streamers.
    "wisp": _amorph(form="spectre", core=.16, hover=.78, tendril=.66,
                    tendril_r=.019, count=7, orbs=3, rise=.30, glow=.85,
                    translucent=.62, surface="energy"),
    # Humanoid above, dissolving into a swirl below.
    "sprite": _amorph(form="nymph", core=.13, hover=.72, tendril=.46,
                      tendril_r=.026, count=4, wings=True, head=.105,
                      glow=.45, translucent=.78, surface="water"),
    # Curling arms sweeping out of a turning column.
    "vortex": _amorph(form="vortex", core=.19, hover=.62, tendril=.70,
                      tendril_r=.046, count=7, orbs=2, spread=1.25,
                      glow=.50, translucent=.66, surface="water"),
    # A heavy mass with a maw and radial tentacles.
    "tentacles": _amorph(form="kraken", core=.30, hover=.52, tendril=.80,
                         tendril_r=.062, count=8, maw=True, face=False,
                         glow=.30, translucent=1.0, surface="slick"),
}

AMORPHOUS_DETAIL = {
    "shardling_swarm": dict(form="swarm", motes=26, mote_r=.155, surface="crystal",
                            spread=.85, glow=.55, translucent=.90),
    "mirrorwing_swarm": dict(form="swarm", motes=28, mote_r=.115, wings=True,
                             surface="water", spread=.95, glow=.45,
                             translucent=.88),
    "shardbound_archivist": dict(form="nymph", motes=10, mote_r=.090, prop="book",
                                 surface="crystal", count=5, glow=.60,
                                 translucent=.82),
    "barrens_wisp": dict(form="spectre", orbs=2, glow=.95, rise=.34, drape=.28),
    # The art is a radial swirl of hair around a hooded face, near circular in
    # outline.  At drape .85 the whole head of hair streamed off one side and
    # the wisp read as a comet; halved, it fans all the way round again.
    "moorlight_wisp": dict(form="spectre", orbs=3, count=9, tendril=.88,
                           spread=1.35, glow=.80, drape=.42, rise=.26),
    "ember_wisp": dict(form="spectre", orbs=2, count=6, rise=.40, glow=1.0,
                       motes=7, mote_r=.045),
    "springfly_sprite": dict(form="nymph", wings=True, count=3, glow=.55),
    "verdant_naiad": dict(form="nymph", wings=False, count=5, core=.15,
                          tendril=.62, glow=.50),
    "lanternwake_sprite": dict(form="ooze", core=.30, hover=.28, count=3,
                               tendril=.22, motes=3, mote_r=.13, face=False,
                               translucent=.55, glow=.40),
    "sluice_elemental": dict(form="vortex", count=8, orbs=3, spread=1.3),
    "tidelance_construct": dict(form="lance", core=.14, hover=.62, count=3,
                                face=False, glow=.55, surface="metal",
                                translucent=1.0),
    "medusa_tidepriest": dict(form="jelly", core=.26, hover=.86, count=8,
                              tendril=.74, tendril_r=.030, prop="trident",
                              face=False, glow=.60, translucent=.74),
    "gilded_devourer": dict(form="kraken", count=8, orbs=3, glow=.45,
                            surface="metal", translucent=.92),
    "mirefather_leviathan": dict(form="kraken", core=.34, hover=.44, count=8,
                                 maw=True, surface="moss", translucent=1.0),
}


def amorphous_config(plan_key: str, variant: str | None = None) -> dict:
    plan = dict(AMORPHOUS_PLANS[plan_key])
    if variant:
        plan.update(AMORPHOUS_DETAIL.get(variant, {}))
    return plan


def amorphous_skeleton(plan_key: str, scale: float, variant: str | None = None):
    p = amorphous_config(plan_key, variant)
    s = scale
    form = p["form"]
    body = np.array((0., p["hover"] * s, 0.))
    chest = body + np.array((0., p["core"] * s * .55, 0.))
    head = chest + np.array((0., p["core"] * s * .78, -p["core"] * s * .22))
    g = {"root": np.zeros(3), "body": body, "chest": chest,
         "neck": (chest + head) * .5, "head": head,
         "jaw": head + np.array((0., -p["head"] * s * .5, -p["head"] * s * .4))}
    reach = p["tendril"] * s
    for i in range(AMORPHOUS_TENDRILS):
        active = i < p["count"]
        angle = 2 * math.pi * i / max(p["count"], 1) + (.4 if form == "vortex" else 0.)
        radial = np.array((math.cos(angle), 0., math.sin(angle)))
        swirl = np.array((-radial[2], 0., radial[0]))
        length = reach * (1.0 if active else .12)
        spread = p["spread"]
        if form in ("jelly", "kraken"):
            # Eight identical legs at eight even angles is a table, which is
            # what these were.  The art coils them: different lengths, some
            # lifted and curling back, none of them straight.  Deterministic
            # per index so the build stays reproducible.
            wobble = ((i * 2654435761) % 1000) / 1000.0
            reach = length * (.72 + .62 * wobble)
            lift = 1.0 if (i % 3 == 0) else -1.0
            start = body + radial * p["core"] * s * (.72 if form == "jelly" else .86)
            mid = (start + radial * reach * (.30 + .22 * wobble) * spread
                   + swirl * reach * .26 * lift
                   + np.array((0., -reach * (.44 - .30 * max(lift, 0.)), 0.)))
            tip = (start + radial * reach * (.52 + .30 * wobble) * spread
                   + swirl * reach * .58 * lift
                   + np.array((0., -reach * (.92 - .96 * max(lift, 0.)), 0.)))
        elif form == "spectre":
            # Flame licks upward; spirit-hair drapes outward and falls.  The
            # same chain does both, switched by the plan's drape weight.
            drape = p["drape"]
            # Flame curls back on itself as it rises; earlier these went
            # straight out and up, which read as a spider's legs rather than a
            # plume.  Hold them in close, wind them round, and let the rise do
            # most of the work.
            # Two behaviours share this chain.  Undraped it is flame: it goes
            # *up*, curling inward over the crown, because a plume whose licks
            # leave sideways is a starfish.  Draped it is spirit-hair, which
            # streams away behind the figure and only sags -- sending it
            # straight down turned a will-o-wisp into a standing spider.
            start = body + radial * p["core"] * s * .38
            lift = p["rise"] + .55
            # Drape leans the strand outward and lets it sag; it must not push
            # every strand the same way in world space, which swept the whole
            # head of hair off one side and made a comet of it.
            mid = (start + radial * length * (.26 + .58 * drape) * spread
                   + swirl * length * (.40 - .10 * drape)
                   + np.array((0., length * lift * (.62 - .74 * drape), 0.)))
            tip = (start + radial * length * (.06 + 1.10 * drape) * spread
                   + swirl * length * (.62 - .20 * drape)
                   + np.array((0., length * (lift * 1.24 - 1.55 * drape), 0.)))
        elif form == "vortex":
            start = body + radial * p["core"] * s * .55
            mid = (start + radial * length * .42 * spread + swirl * length * .30
                   + np.array((0., length * .18, 0.)))
            tip = (start + radial * length * .58 * spread + swirl * length * .72
                   + np.array((0., length * .40, 0.)))
        elif form == "nymph":
            # Water streams fall and trail behind, they do not splay outward
            # like limbs.
            start = body + radial * p["core"] * s * .28
            mid = (start + radial * length * .12 + swirl * length * .16
                   + np.array((0., -length * .52, length * .10)))
            tip = (start + radial * length * .10 + swirl * length * .34
                   + np.array((0., -length * .98, length * .30)))
        else:  # swarm, ooze, lance
            start = body + radial * p["core"] * s * .6
            mid = start + radial * length * .5 + np.array((0., -length * .18, 0.))
            tip = start + radial * length * .9 + np.array((0., -length * .34, 0.))
        g[f"tendril_{i + 1}a"] = start
        g[f"tendril_{i + 1}b"] = mid
        g[f"tendril_{i + 1}c"] = tip
    for k in range(3):
        angle = 2 * math.pi * k / 3 + .7
        g[f"orb_{k + 1}"] = chest + np.array((math.cos(angle) * p["core"] * s * 2.3,
                                              p["core"] * s * (.5 - .6 * k),
                                              math.sin(angle) * p["core"] * s * 2.3))
    for side, sign in (("l", -1.), ("r", 1.)):
        g[f"wing_{side}"] = chest + np.array((sign * p["core"] * s * .7,
                                              p["core"] * s * .5, p["core"] * s * .3))
    g["prop_r"] = chest + np.array((p["core"] * s * 1.5, -p["core"] * s * .4,
                                    -p["core"] * s * .3))
    return _bones_from(g, AMORPHOUS_TABLE)


def _mote(mesh, centre, size, bones, material, kind, axis=None):
    if kind == "shard" and axis is not None:
        # A faceted splinter along an arbitrary axis, so a cloud of them does
        # not read as a field of identical upright eggs.
        half = np.asarray(axis, dtype=float) * size
        mesh.tube([centre - half, centre - half * .25, centre + half * .35,
                   centre + half],
                  [(size * .05, size * .05), (size * .34, size * .30),
                   (size * .26, size * .22), (size * .04, size * .04)],
                  bones, material, sides=5)
        return
    if kind == "wing":
        # A pair of wings tilted into the drift, so a swarm reads as insects in
        # flight rather than a field of flat plates all facing the same way.
        span = size * 1.15
        axis = np.asarray(axis if axis is not None else (0., 1., 0.), dtype=float)
        axis = axis / max(float(np.linalg.norm(axis)), 1e-6)
        ref = np.array((0., 1., 0.)) if abs(axis[1]) < .85 else np.array((1., 0., 0.))
        right = np.cross(ref, axis)
        right /= max(float(np.linalg.norm(right)), 1e-6)
        up = np.cross(axis, right)
        for sign in (-1., 1.):
            a = [centre, centre + right * sign * span * .55 + up * span * .40,
                 centre + right * sign * span * 1.05 + up * span * .30]
            b = [centre + axis * size * .18,
                 centre + right * sign * span * .50 + up * span * .05 + axis * size * .10,
                 centre + right * sign * span * .85 - up * span * .25]
            _sheet(mesh, [_bezier(a, t) for t in np.linspace(0, 1, 4)],
                   [_bezier(b, t) for t in np.linspace(0, 1, 4)],
                   size * .07, bones, material)
        mesh.ellipsoid(tuple(centre), (size * .16, size * .16, size * .52),
                       bones, material, rings=4, sides=5)
    else:
        mesh.ellipsoid(tuple(centre), (size * .60, size * 1.7, size * .60),
                       bones, material, rings=4, sides=5)


def amorphous_geometry(plan_key: str, scale: float, bones,
                       variant: str | None = None) -> AnatomyMesh:
    p = amorphous_config(plan_key, variant)
    s = scale
    g = global_positions(bones)
    B = AMORPHOUS_INDEX
    mesh = AnatomyMesh(g)
    body_i, chest_i, head_i = B["body"], B["chest"], B["head"]
    core = p["core"] * s
    form = p["form"]
    tendrils = [(B[f"tendril_{i + 1}a"], B[f"tendril_{i + 1}b"], B[f"tendril_{i + 1}c"])
                for i in range(p["count"])]

    def strand(a, b, c, radius, material, taper=.10, sides=8):
        tip = g[c] + (g[c] - g[b]) * .5
        mesh.tube([g[a], (g[a] + g[b]) * .5, g[b], (g[b] + g[c]) * .5, g[c], tip],
                  [(radius * 1.25, radius * 1.25), (radius * 1.02, radius * 1.02),
                   (radius * .84, radius * .84), (radius * .60, radius * .60),
                   (radius * .34, radius * .34), (radius * taper, radius * taper)],
                  [body_i, a, b, c], material, sides=sides, cap_start=False)

    # ---- core mass -------------------------------------------------------
    if form == "swarm":
        # No body: a knot of light with the shards doing all the work.
        mesh.ellipsoid(tuple(g[body_i]), (core * 1.5,) * 3, [body_i, chest_i],
                       MAT_ACCENT, rings=7, sides=10)
        mesh.ellipsoid(tuple(g[body_i]), (core * .90,) * 3, [body_i, chest_i],
                       MAT_CORE, rings=7, sides=10)
    elif form == "spectre":
        # A plume: narrow at the base, swelling into a hooded crown -- and
        # twisting on the way up.  A straight cone reads as a traffic bollard
        # whatever colour it is painted; flame in the art turns as it rises.
        rng = np.random.default_rng(zlib_crc((variant or plan_key) + ":plume"))
        # The plume is a body, not a spear.  Rooting it at the floor drew a
        # long hard-edged blade under every wisp -- the single most wrong thing
        # about them, since the art gives them no lower half at all: the mass
        # gathers, swirls and frays away.
        base = g[body_i] - np.array((0., core * 1.35, 0.))
        column = [base, base * .40 + g[body_i] * .60, g[body_i],
                  g[chest_i], g[head_i], g[head_i] + np.array((0., core * .55, 0.))]
        widths = [(core * .30, core * .30), (core * .74, core * .74),
                  (core * .98, core * .98), (core * 1.06, core * 1.08),
                  (core * .74, core * .78), (core * .22, core * .26)]
        turn = float(rng.uniform(.7, 1.3))
        for k in range(1, len(column) - 1):
            sway = math.sin(k * 1.15 * turn) * core * .38
            lean = math.cos(k * .92 * turn) * core * .30
            column[k] = column[k] + np.array((sway, 0., lean))
        mesh.tube(column, widths, [body_i, chest_i, head_i], MAT_BODY,
                  sides=16, uv_scale=1.6)
        mesh.ellipsoid(tuple(g[chest_i] + np.array((0., -core * .10, 0.))),
                       (core * .82, core * 1.02, core * .82),
                       [chest_i, body_i], MAT_CORE, rings=8, sides=12)
        # Tongues licking off the column: what makes a plume read as fire or
        # spirit rather than as a cone with antennae stuck in the top.
        for k in range(6):
            t = .28 + .62 * (k + float(rng.uniform(-.2, .2))) / 6.0
            index = min(int(t * (len(column) - 1)), len(column) - 2)
            frac = t * (len(column) - 1) - index
            anchor = column[index] * (1 - frac) + column[index + 1] * frac
            angle = 2 * math.pi * (k / 6.0 + float(rng.uniform(-.09, .09)))
            out = np.array((math.cos(angle), 0., math.sin(angle)))
            reach = core * float(rng.uniform(.75, 1.7))
            lick = [anchor,
                    anchor + out * reach * .42 + np.array((0., reach * .55, 0.)),
                    anchor + out * reach * .30 + np.array((0., reach * 1.25, 0.))]
            mesh.tube(lick, [(core * .30, core * .30), (core * .17, core * .17),
                             (core * .03, core * .03)],
                      [body_i, chest_i, head_i], MAT_ACCENT, sides=6,
                      cap_start=False)
    elif form == "jelly":
        # Bell: a flattened dome with a scalloped rim and a lit core.
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., core * .18, 0.))),
                       (core * 2.4, core * 1.9, core * 2.4), [body_i, chest_i],
                       MAT_BODY, rings=10, sides=18, squash=1.0)
        rim = []
        for k in range(19):
            a = 2 * math.pi * k / 18
            rim.append(g[body_i] + np.array((math.cos(a) * core * 1.20, -core * .28,
                                             math.sin(a) * core * 1.20)))
        mesh.tube(rim, [(core * .16, core * .12)] * 19, [body_i, chest_i],
                  MAT_FEATURE, sides=6, cap_start=False, cap_end=False)
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., core * .10, -core * .60))),
                       (core * .60,) * 3, [body_i], MAT_ACCENT, rings=7, sides=10)
    elif form == "kraken":
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., core * .10, 0.))),
                       (core * 2.3, core * 1.7, core * 2.2), [body_i, chest_i],
                       MAT_BODY, rings=11, sides=18)
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., core * .62, core * .10))),
                       (core * 1.5, core * 1.1, core * 1.5), [chest_i, body_i],
                       MAT_BODY, rings=8, sides=14)
        if p["maw"]:
            mouth = g[body_i] + np.array((0., -core * .10, -core * 1.05))
            mesh.ellipsoid(tuple(mouth), (core * 1.05, core * .70, core * .70),
                           [body_i, B["jaw"]], MAT_DARK, rings=7, sides=12)
            for k in range(9):
                a = math.pi * k / 8
                tooth = mouth + np.array((math.cos(a) * core * .50, core * .20,
                                          -math.sin(a) * core * .22))
                mesh.spike(tooth, tooth + np.array((0., -core * .30, -core * .10)),
                           core * .09, [B["jaw"], body_i], MAT_FEATURE, sides=5)
    elif form == "nymph":
        # Torso above, dissolving into a turning skirt of water below.
        # Waist, ribcage, shoulders, then a head: the figure has to read
        # before the water below it means anything.
        torso = [g[body_i] + np.array((0., -core * .10, 0.)),
                 g[body_i] + np.array((0., core * .34, 0.)),
                 g[chest_i] + np.array((0., core * .10, 0.)),
                 g[chest_i] + np.array((0., core * .52, 0.))]
        mesh.tube(torso, [(core * .46, core * .40), (core * .40, core * .34),
                          (core * .56, core * .46), (core * .30, core * .28)],
                  [body_i, chest_i, head_i], MAT_BODY, sides=14, cap_end=False)
        mesh.ellipsoid(tuple(g[head_i]), (core * .62, core * .70, core * .62),
                       [head_i, chest_i], MAT_BODY, rings=9, sides=12)
        # Hair or crest falling behind the head.
        mesh.tube([g[head_i] + np.array((0., core * .26, core * .16)),
                   g[head_i] + np.array((0., -core * .30, core * .52)),
                   g[head_i] + np.array((0., -core * .92, core * .62))],
                  [(core * .46, core * .34), (core * .38, core * .26),
                   (core * .14, core * .10)],
                  [head_i, chest_i], MAT_ACCENT, sides=10, cap_start=False)
        skirt = [g[body_i] + np.array((0., core * .10, 0.)),
                 g[body_i] + np.array((0., -core * .70, core * .10)),
                 g[body_i] + np.array((0., -core * 1.70, core * .30)),
                 g[body_i] + np.array((0., -core * 2.60, core * .58))]
        mesh.tube(skirt, [(core * .50, core * .46), (core * .78, core * .72),
                          (core * .96, core * .88), (core * .44, core * .42)],
                  [body_i] + [t[0] for t in tendrils[:2]], MAT_ACCENT,
                  sides=14, cap_start=False, cap_end=False)
        for side, sign in (("l", -1.), ("r", 1.)):
            shoulder = g[chest_i] + np.array((sign * core * .48, core * .34, 0.))
            hand = shoulder + np.array((sign * core * .78, -core * .74, -core * .30))
            mesh.tube([g[chest_i] + np.array((sign * core * .18, core * .34, 0.)),
                       shoulder, (shoulder + hand) * .5, hand],
                      [(core * .22, core * .22), (core * .18, core * .18),
                       (core * .13, core * .13), (core * .09, core * .09)],
                      [chest_i, B[f"wing_{side}"]], MAT_BODY, sides=8, cap_start=False)
    elif form == "ooze":
        # A settled translucent mound with things suspended inside it.  Swept
        # as a single tapering tube it came out a smooth cone -- a tent, with
        # nothing about it reading as liquid.  A slime sags: it domes over,
        # spreads where it meets the floor, and hangs runnels off the rim.
        rng = np.random.default_rng(zlib_crc((variant or plan_key) + ":ooze"))
        # Taller than wide, with the mass carried high: the art's slime bulges
        # over and narrows to the floor, rather than spreading like a puddle.
        mound = [np.array((0., core * .04, 0.)),
                 g[body_i] + np.array((0., core * .10, 0.)),
                 g[body_i] + np.array((0., core * .95, 0.)),
                 g[body_i] + np.array((0., core * 1.62, 0.))]
        mesh.tube(mound, [(core * 2.30, core * 2.10), (core * 2.05, core * 1.95),
                          (core * 1.90, core * 1.80), (core * .50, core * .50)],
                  [body_i, chest_i], MAT_BODY, sides=18, uv_scale=1.4)
        mesh.ellipsoid(tuple(g[body_i] + np.array((0., core * .95, 0.))),
                       (core * 2.05, core * 1.75, core * 2.05),
                       [body_i, chest_i], MAT_BODY, rings=10, sides=18)
        # The puddle it is standing in, and the drips coming off its shoulders.
        mesh.ellipsoid((0., core * .16, 0.),
                       (core * 3.15, core * .34, core * 3.15),
                       [body_i], MAT_BODY, rings=6, sides=20)
        for k in range(9):
            angle = 2 * math.pi * k / 9 + float(rng.uniform(-.18, .18))
            out = np.array((math.cos(angle), 0., math.sin(angle)))
            top = g[body_i] + out * core * 1.85 + np.array((0., core * 1.05, 0.))
            fall = core * float(rng.uniform(.80, 1.70))
            mesh.tube([top,
                       top + out * core * .16 - np.array((0., fall * .55, 0.)),
                       top + out * core * .20 - np.array((0., fall, 0.))],
                      [(core * .22, core * .22), (core * .15, core * .15),
                       (core * .07, core * .07)],
                      [body_i, chest_i], MAT_BODY, sides=6)
            # A bead about to drop, which is most of what makes a surface wet.
            mesh.ellipsoid(tuple(top + out * core * .26
                                 - np.array((0., fall * 1.14, 0.))),
                           (core * .155,) * 3, [body_i], MAT_BODY,
                           rings=5, sides=7)
        # Salvage suspended inside the slime: a lantern, a mill wheel, a plank.
        lantern = g[body_i] + np.array((-core * .70, core * .52, -core * .20))
        mesh.tube([lantern + np.array((0., core * .40, 0.)),
                   lantern + np.array((0., core * .26, 0.))],
                  [(core * .05, core * .05), (core * .05, core * .05)],
                  [body_i, chest_i], MAT_DARK, sides=5)
        mesh.ellipsoid(tuple(lantern), (core * .30, core * .44, core * .30),
                       [body_i, chest_i], MAT_FEATURE, rings=6, sides=6)
        wheel = g[body_i] + np.array((core * .74, core * .10, core * .12))
        ring = []
        for k in range(15):
            a = 2 * math.pi * k / 14
            ring.append(wheel + np.array((0., math.sin(a) * core * .56,
                                          math.cos(a) * core * .56)))
        mesh.tube(ring, [(core * .07, core * .07)] * 15, [body_i, chest_i],
                  MAT_DARK, sides=5, cap_start=False, cap_end=False)
        for k in range(4):
            a = math.pi * k / 4
            mesh.tube([wheel, wheel + np.array((0., math.sin(a) * core * .54,
                                                math.cos(a) * core * .54))],
                      [(core * .05,) * 2, (core * .04,) * 2],
                      [body_i, chest_i], MAT_DARK, sides=4)
        plank = g[body_i] + np.array((0., -core * .34, core * .55))
        mesh.tube([plank - np.array((core * .80, 0., 0.)),
                   plank + np.array((core * .80, 0., 0.))],
                  [(core * .10, core * .28), (core * .10, core * .28)],
                  [body_i, chest_i], MAT_DARK, sides=4)
    elif form == "lance":
        # A brass lance construct trailing a plume of water.
        axis = np.array((0., 0., -1.))
        head_pt = g[body_i] + axis * core * 2.6
        tail_pt = g[body_i] - axis * core * 2.2
        mesh.tube([tail_pt, g[body_i], head_pt],
                  [(core * .52, core * .52), (core * .62, core * .62),
                   (core * .28, core * .28)],
                  [body_i, chest_i], MAT_FEATURE, sides=12)
        for t in (-.5, 0., .5):
            ring = []
            centre = g[body_i] + axis * core * 2.6 * t
            for k in range(13):
                a = 2 * math.pi * k / 12
                ring.append(centre + np.array((math.cos(a) * core * .80,
                                               math.sin(a) * core * .80, 0.)))
            mesh.tube(ring, [(core * .10, core * .10)] * 13, [body_i, chest_i],
                      MAT_DARK, sides=5, cap_start=False, cap_end=False)
        plume = [tail_pt, tail_pt - axis * core * 1.2, tail_pt - axis * core * 2.4]
        mesh.tube(plume, [(core * .40, core * .40), (core * .85, core * .85),
                          (core * .30, core * .30)],
                  [body_i, chest_i], MAT_ACCENT, sides=12, cap_start=False)
    else:
        mesh.ellipsoid(tuple(g[body_i]), (core * 2, core * 2.2, core * 2),
                       [body_i, chest_i], MAT_BODY, rings=10, sides=14)
        if form == "vortex":
            mesh.ellipsoid(tuple(g[body_i]), (core * 1.05, core * 1.20, core * 1.05),
                           [body_i, chest_i], MAT_CORE, rings=8, sides=12)

    # ---- streamers, tentacles and arms ------------------------------------
    strand_material = MAT_ACCENT if form in ("spectre", "vortex", "nymph") else MAT_BODY
    for index, (a, b, c) in enumerate(tendrils):
        radius = p["tendril_r"] * s
        if form == "swarm":
            continue
        if form == "ooze":
            continue
        if form in ("spectre", "vortex", "nymph"):
            # Flame, spirit-hair and running water are ribbons that coil round
            # the body, not spokes radiating off it.  A three-point tube down
            # the same bone chain drew a straight wedge however thick it was
            # made, and a ring of wedges is an upturned insect.
            tip = g[c] + (g[c] - g[b]) * .45
            swirl_ribbon(mesh, [g[a], g[b], g[c], tip],
                         radius * (6.2 if form == "spectre"
                                   else 3.6 if form == "vortex" else 2.2),
                         [body_i, a, b, c], strand_material,
                         seed=f"{variant or plan_key}:ribbon:{index}",
                         turns=1.35 if form == "spectre" else .95,
                         curl=.20 if form == "spectre" else .15,
                         flatten=.22, taper=.04,
                         phase=2 * math.pi * index / max(p["count"], 1))
        elif form in ("kraken", "jelly"):
            tip_pt = g[c] + (g[c] - g[b]) * .45
            swirl_ribbon(mesh, [g[a], g[b], g[c], tip_pt], radius * 1.45,
                         [body_i, a, b, c], strand_material,
                         seed=f"{variant or plan_key}:arm:{index}",
                         turns=.55, curl=.10, flatten=.86, taper=.10, sides=8,
                         phase=2 * math.pi * index / max(p["count"], 1))
        else:
            strand(a, b, c, radius, strand_material,
                   taper=.06 if form == "vortex" else .14,
                   sides=9)
        if form == "kraken":
            for k in range(4):
                t = .35 + .20 * k
                spot = _bezier([g[a], g[b], g[c]], t)
                mesh.ellipsoid(tuple(spot + np.array((0., -radius * .9, 0.))),
                               (radius * .55,) * 3, [b, c], MAT_ACCENT,
                               rings=4, sides=6)

    # ---- floating motes: shards, wings, embers, suspended cargo -----------
    if p["motes"]:
        rng = np.random.default_rng(zlib_crc(variant or plan_key))
        kind = "wing" if (p["wings"] and form == "swarm") else "shard"
        for k in range(int(p["motes"])):
            if form == "swarm":
                # A vortex, not a lattice.  The regular helix this used to walk
                # spaced the motes so evenly that a swarm read as confetti on a
                # grid; the art turns them around a core, tighter at the middle
                # and ragged at the edge.  Jitter is drawn from the same seeded
                # generator, so the cloud stays reproducible.
                t = k / max(p["motes"] - 1, 1)
                turn = t * 3.4 + float(rng.uniform(-.22, .22))
                angle = 2 * math.pi * turn
                swell = abs(math.sin(t * math.pi * 1.15))
                radius = (core * (1.35 + 3.9 * swell) * p["spread"]
                          * float(rng.uniform(.62, 1.34)))
                height = ((t - .5) * p["tendril"] * s * 6.4
                          + float(rng.uniform(-.5, .5)) * core * 1.6)
                centre = g[body_i] + np.array((math.cos(angle) * radius, height,
                                               math.sin(angle) * radius * .7))
            elif form == "ooze":
                continue
            else:
                angle = 2 * math.pi * k / max(p["motes"], 1)
                centre = g[chest_i] + np.array((math.cos(angle) * core * 1.9,
                                                core * (1.1 - .28 * k),
                                                math.sin(angle) * core * 1.9))
            size = p["mote_r"] * s * (.75 + .5 * float(rng.random()))
            hub = tendrils[k % max(len(tendrils), 1)][0] if tendrils else body_i
            axis = rng.normal(size=3)
            axis = axis / max(float(np.linalg.norm(axis)), 1e-6)
            _mote(mesh, centre, size, [body_i, chest_i, hub],
                  MAT_FEATURE if form != "ooze" else MAT_DARK, kind, axis)

    # ---- floating orbs ----------------------------------------------------
    for k in range(int(p["orbs"])):
        orb = g[B[f"orb_{k + 1}"]]
        mesh.ellipsoid(tuple(orb), (p["orb_r"] * s * 2,) * 3,
                       [B[f"orb_{k + 1}"], chest_i], MAT_FEATURE, rings=7, sides=10)

    # ---- wings ------------------------------------------------------------
    if p["wings"] and form == "nymph":
        for side, sign in (("l", -1.), ("r", 1.)):
            root = g[B[f"wing_{side}"]]
            span = core * 3.1
            for pair, lift in ((0, 1.0), (1, .62)):
                tip = root + np.array((sign * span * (1.0 - .22 * pair),
                                       span * (.78 - .52 * pair),
                                       span * (-.10 + .42 * pair)))
                outer = [root, root + np.array((sign * span * .45, span * .58 * lift,
                                                span * .05)), tip]
                inner = [root + np.array((0., -core * .10, core * .16)),
                         root + np.array((sign * span * .30, span * .18 * lift,
                                          span * .28)),
                         tip + np.array((-sign * span * .22, -span * .16, span * .22))]
                _sheet(mesh, [_bezier(outer, t) for t in np.linspace(0, 1, 7)],
                       [_bezier(inner, t) for t in np.linspace(0, 1, 7)],
                       core * .05, [B[f"wing_{side}"], chest_i], MAT_ACCENT)

    # ---- face -------------------------------------------------------------
    if p["face"]:
        hd = p["head"] * s
        for side in (-1., 1.):
            mesh.ellipsoid(tuple(g[head_i] + np.array((side * hd * .52, hd * .16,
                                                       -hd * .80))),
                           (hd * .42,) * 3, [head_i], MAT_DARK, rings=6, sides=8)

    # ---- held prop --------------------------------------------------------
    if p["prop"] == "trident":
        grip = g[B["prop_r"]]
        butt = grip - np.array((0., core * 1.5, 0.))
        tip = grip + np.array((0., core * 2.0, 0.))
        mesh.tube([butt, grip, tip], [(core * .09,) * 2, (core * .10,) * 2,
                                      (core * .08,) * 2],
                  [B["prop_r"], chest_i], MAT_FEATURE, sides=7)
        for off in (-.20, 0., .20):
            base = tip + np.array((off * core * 2.0, 0., 0.))
            mesh.spike(base, base + np.array((0., core * (.62 if off else .80), 0.)),
                       core * .07, [B["prop_r"]], MAT_FEATURE, sides=5)
        mesh.tube([tip - np.array((core * .42, 0., 0.)), tip + np.array((core * .42, 0., 0.))],
                  [(core * .06,) * 2, (core * .06,) * 2], [B["prop_r"]],
                  MAT_FEATURE, sides=5)
    elif p["prop"] == "book":
        grip = g[B["prop_r"]]
        mesh.ellipsoid(tuple(grip), (core * .95, core * .28, core * .78),
                       [B["prop_r"], chest_i], MAT_FEATURE, rings=5, sides=8)
    return mesh


def zlib_crc(text: str) -> int:
    import zlib
    return zlib.crc32(text.encode("utf-8")) % (2 ** 31)


def amorphous_animation(plan_key: str, scale: float, bones,
                        variant: str | None = None) -> dict:
    p = amorphous_config(plan_key, variant)
    form = p["form"]
    B = AMORPHOUS_INDEX
    tendrils = [(B[f"tendril_{i + 1}a"], B[f"tendril_{i + 1}b"], B[f"tendril_{i + 1}c"],
                 i / max(p["count"], 1)) for i in range(p["count"])]
    orbs = [B[f"orb_{k + 1}"] for k in range(int(p["orbs"]))]
    clips: dict[str, dict] = {}
    # Swarms and vortices turn; jellies pulse; plumes stream upward.
    turning = form in ("swarm", "vortex")

    def drift(duration, samples, amp, bob, spin):
        tracks: dict[tuple[int, str], list] = {}
        stamps = [duration * i / samples for i in range(samples + 1)]
        for i in range(samples + 1):
            u = i / samples
            c = 2 * math.pi * u
            tracks.setdefault((B["root"], "translation"), []).append(
                [0., bob * scale * math.sin(c), 0.])
            yaw = (u * 2 * math.pi * spin) if turning else .07 * math.sin(c)
            tracks.setdefault((B["body"], "rotation"), []).append(
                _euler(yaw=yaw, roll=.05 * math.sin(c + .8)))
            tracks.setdefault((B["chest"], "rotation"), []).append(
                _euler(roll=-.06 * math.sin(c), pitch=.04 * math.sin(c + .4)))
            tracks.setdefault((B["head"], "rotation"), []).append(
                _euler(pitch=.07 * math.sin(c + 1.1), yaw=.10 * math.sin(c * .5)))
            for a, b, cc, phase in tendrils:
                ph = c - 2 * math.pi * phase
                # A travelling wave down each strand rather than a rigid swing.
                tracks.setdefault((a, "rotation"), []).append(
                    _euler(pitch=amp * math.sin(ph), roll=amp * .55 * math.cos(ph)))
                tracks.setdefault((b, "rotation"), []).append(
                    _euler(pitch=amp * 1.35 * math.sin(ph - .75),
                           roll=amp * .70 * math.cos(ph - .75)))
                tracks.setdefault((cc, "rotation"), []).append(
                    _euler(pitch=amp * 1.75 * math.sin(ph - 1.5),
                           roll=amp * .85 * math.cos(ph - 1.5)))
            for k, orb in enumerate(orbs):
                tracks.setdefault((orb, "rotation"), []).append(
                    _euler(yaw=c * (1.0 if k % 2 else -1.0) * .5,
                           pitch=.20 * math.sin(c + k)))
        return {k: (k[1], stamps, v) for k, v in tracks.items()}

    clips["Idle_A"] = drift(3.0, 18, .12, .020, .25)
    clips["Walk"] = drift(1.4, 16, .20, .034, .55)
    clips["Jog"] = drift(.85, 14, .28, .048, 1.0)
    clips["Fighting_Idle"] = drift(1.7, 14, .24, .028, .70)

    stamp = [0., .16, .30, .44, .58, .80]
    attack = {(B["root"], "translation"): [[0., 0., 0.], [0., .045 * scale, 0.],
                                          [0., -.030 * scale, 0.], [0., -.055 * scale, 0.],
                                          [0., -.012 * scale, 0.], [0., 0., 0.]],
              (B["body"], "rotation"): [_euler(), _euler(pitch=-.22), _euler(pitch=.26),
                                        _euler(pitch=.34), _euler(pitch=.10), _euler()],
              (B["chest"], "rotation"): [_euler(), _euler(pitch=-.16), _euler(pitch=.20),
                                         _euler(pitch=.26), _euler(pitch=.08), _euler()],
              (B["head"], "rotation"): [_euler(), _euler(pitch=-.24), _euler(pitch=.30),
                                        _euler(pitch=.18), _euler(), _euler()],
              (B["jaw"], "rotation"): [_euler(), _euler(pitch=.26), _euler(pitch=.68),
                                       _euler(pitch=.16), _euler(), _euler()]}
    for a, b, cc, phase in tendrils:
        # Coil back, then lash forward together.
        attack[(a, "rotation")] = [_euler(), _euler(pitch=-.58), _euler(pitch=.76),
                                   _euler(pitch=.94), _euler(pitch=.22), _euler()]
        attack[(b, "rotation")] = [_euler(), _euler(pitch=-.44), _euler(pitch=.68),
                                   _euler(pitch=.82), _euler(pitch=.18), _euler()]
        attack[(cc, "rotation")] = [_euler(), _euler(pitch=-.30), _euler(pitch=.54),
                                    _euler(pitch=.66), _euler(pitch=.14), _euler()]
    for k, orb in enumerate(orbs):
        attack[(orb, "rotation")] = [_euler(), _euler(yaw=-.6), _euler(yaw=.9),
                                     _euler(yaw=1.2), _euler(yaw=.4), _euler()]
    clips["Sword_Attack"] = {k: (k[1], stamp, v) for k, v in attack.items()}

    hit_t = [0., .09, .20, .34, .50]
    hit = {(B["root"], "translation"): [[0., 0., 0.], [0., -.034 * scale, 0.],
                                        [0., -.017 * scale, 0.], [0., -.006 * scale, 0.],
                                        [0., 0., 0.]],
           (B["body"], "rotation"): [_euler(), _euler(roll=.30, pitch=.18),
                                     _euler(roll=.16, pitch=.09), _euler(roll=-.03),
                                     _euler()],
           (B["head"], "rotation"): [_euler(), _euler(pitch=.32), _euler(pitch=.17),
                                     _euler(), _euler()]}
    for a, b, cc, _ in tendrils:
        hit[(a, "rotation")] = [_euler(), _euler(pitch=.50, roll=.24),
                                _euler(pitch=.27), _euler(pitch=.07), _euler()]
        hit[(b, "rotation")] = [_euler(), _euler(pitch=.40), _euler(pitch=.21),
                                _euler(pitch=.05), _euler()]
    clips["Hit_Chest"] = {k: (k[1], hit_t, v) for k, v in hit.items()}

    # Death: cohesion fails, the strands fall slack and the form sinks.
    death_t = [0., .28, .56, .88, 1.16, 1.46]
    drop = -p["hover"] * scale * .88
    death = {(B["root"], "translation"): [[0., 0., 0.], [0., drop * .16, 0.],
                                          [0., drop * .50, 0.], [0., drop * .84, 0.],
                                          [0., drop, 0.], [0., drop, 0.]],
             (B["body"], "rotation"): [_euler(), _euler(roll=.16, pitch=.18),
                                       _euler(roll=.36, pitch=.38),
                                       _euler(roll=.54, pitch=.54),
                                       _euler(roll=.62, pitch=.62),
                                       _euler(roll=.63, pitch=.63)],
             (B["head"], "rotation"): [_euler(), _euler(pitch=.20), _euler(pitch=.44),
                                       _euler(pitch=.62), _euler(pitch=.70),
                                       _euler(pitch=.71)]}
    for a, b, cc, _ in tendrils:
        death[(a, "rotation")] = [_euler(), _euler(pitch=.36), _euler(pitch=.78),
                                  _euler(pitch=1.06), _euler(pitch=1.20),
                                  _euler(pitch=1.22)]
        death[(b, "rotation")] = [_euler(), _euler(pitch=.32), _euler(pitch=.70),
                                  _euler(pitch=.96), _euler(pitch=1.08),
                                  _euler(pitch=1.10)]
        death[(cc, "rotation")] = [_euler(), _euler(pitch=.24), _euler(pitch=.54),
                                   _euler(pitch=.74), _euler(pitch=.84),
                                   _euler(pitch=.86)]
    for k, orb in enumerate(orbs):
        death[(orb, "rotation")] = [_euler(), _euler(pitch=.3), _euler(pitch=.7),
                                    _euler(pitch=1.0), _euler(pitch=1.2),
                                    _euler(pitch=1.22)]
    clips["Death_A"] = {k: (k[1], death_t, v) for k, v in death.items()}
    return clips


FAMILIES["amorphous"] = (amorphous_skeleton, amorphous_geometry, amorphous_animation)
