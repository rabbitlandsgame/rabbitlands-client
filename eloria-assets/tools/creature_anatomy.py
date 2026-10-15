#!/usr/bin/env python3
"""Production creature anatomy for the native Nymara GLB pipeline.

The first-pass generator assembled every creature from three stacked
ellipsoids and four straight cylinders, which read as a blockout rather than a
game asset.  This module replaces that with a body-plan driven anatomy builder:

* a swept, elliptical torso with real chest / waist / haunch shaping,
* a shaped skull with muzzle, jaw, ears, eyes and nose,
* tapered limbs bent through credible knee / hock / ankle pivots,
* tapering tails, horns, shells, spines and wing membranes,
* smooth multi-bone skin weights instead of rigid one-bone binding.

Geometry is authored in bind pose with +Y up and the creature facing -Z.
"""
from __future__ import annotations

import json as _json
import math
import zlib
from pathlib import Path as _Path

import numpy as np

# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------
# Topology is shared by every creature so a single res://data/animations/
# creature.json action map stays valid; rest positions are plan-specific.
# "body", "neck" and "head" are load-bearing: models.json binds runtime
# attachment points to those exact bone names.
BONE_TOPOLOGY = (
    ("root", -1), ("body", 0), ("chest", 1), ("neck", 2), ("head", 3), ("jaw", 4),
    ("tail_1", 1), ("tail_2", 6), ("tail_3", 7), ("tail_4", 8),
    ("front_leg_l", 2), ("front_shin_l", 10), ("front_paw_l", 11),
    ("front_leg_r", 2), ("front_shin_r", 13), ("front_paw_r", 14),
    ("rear_leg_l", 1), ("rear_shin_l", 16), ("rear_paw_l", 17),
    ("rear_leg_r", 1), ("rear_shin_r", 19), ("rear_paw_r", 20),
    ("wing_l", 2), ("wing_r", 2),
)
BONE_INDEX = {name: index for index, (name, _) in enumerate(BONE_TOPOLOGY)}

MAT_BODY, MAT_ACCENT, MAT_DARK, MAT_FEATURE, MAT_GROWTH = 0, 1, 2, 3, 4
# A sixth slot for whatever is lit from inside: the heart-hollow burning in a
# treant, the glow trapped in a geode carapace, the core a wisp swirls around.
# The concept art draws these as the brightest thing on the creature, and a
# whole-body emissive cannot express them because the shell around them has to
# stay dark for the core to read as a core.
MAT_CORE = 5


def _plan(**overrides) -> dict:
    """A canid baseline; every plan is expressed as a delta from it."""
    base = dict(
        # torso ------------------------------------------------------------
        hip_h=.78, shoulder_h=.82, rump_z=.52, chest_z=-.42,
        rump=(.32, .34), waist=(.27, .30), chest=(.34, .38), throat=(.26, .28),
        belly_drop=.02, back_arch=.03,
        # neck / head ------------------------------------------------------
        neck_len=.30, neck_rise=.16, neck_r=(.17, .18), head_drop=.0,
        skull=(.20, .21, .25), muzzle_len=.27, muzzle_r=(.115, .055),
        muzzle_drop=.045, jaw_len=.20, brow=.035,
        ear="pointed", ear_h=.22, ear_w=.12, ear_spread=.115, ear_tilt=.14,
        eye_r=.030, eye_fwd=.10, eye_spread=.085, eye_rise=.055,
        # limbs ------------------------------------------------------------
        stance="digitigrade", front_x=.20, rear_x=.22, front_z=-.30, rear_z=.34,
        upper_r=.095, lower_r=.065, ankle_r=.050,
        knee_fwd=.09, hock_back=.13, foot_len=.19, foot_r=.070, toes=4,
        # tail -------------------------------------------------------------
        tail_len=.74, tail_r=.105, tail_taper=.16, tail_droop=.34, tail_lift=.06,
        tail_bush=1.0, tails=1,
        # extras -----------------------------------------------------------
        horn=None, shell=False, spines=None, wings=False, plates=None,
        dorsal=None, humped=False, mane_ruff=False,
        # Plated construction, as on the bipedal golems: the stone beasts in
        # the art are clad in overlapping slabs, not smooth hide in a stone
        # colour.  ``core`` sets a lit gem in the shoulder.
        plated=.0, plate_shape="boulder", runes=.0, core=.0,
    )
    base.update(overrides)
    return base


BODY_PLANS = {
    "canid": _plan(),
    "felid": _plan(
        rump=(.30, .32), waist=(.26, .28), chest=(.32, .35), back_arch=.05,
        skull=(.21, .19, .22), muzzle_len=.19, muzzle_r=(.115, .070), muzzle_drop=.03,
        ear="rounded_point", ear_h=.17, ear_w=.13, ear_spread=.10,
        upper_r=.100, lower_r=.068, foot_len=.17, foot_r=.078,
        tail_len=.82, tail_r=.085, tail_droop=.18, tail_lift=.16,
    ),
    "ursine": _plan(
        hip_h=.80, shoulder_h=.88, rump_z=.56, chest_z=-.46,
        rump=(.44, .44), waist=(.40, .40), chest=(.48, .50), throat=(.34, .34),
        humped=True, back_arch=.02,
        neck_len=.24, neck_rise=.10, neck_r=(.26, .26),
        skull=(.27, .25, .27), muzzle_len=.24, muzzle_r=(.155, .105), muzzle_drop=.05,
        ear="round", ear_h=.13, ear_w=.14, ear_spread=.15, ear_tilt=.05,
        eye_spread=.10, eye_fwd=.07,
        stance="plantigrade", front_x=.26, rear_x=.27, upper_r=.135, lower_r=.105,
        ankle_r=.085, foot_len=.24, foot_r=.105, toes=5,
        tail_len=.20, tail_r=.075, tail_taper=.30, tail_droop=.55,
    ),
    "suid": _plan(   # boar / rhino: heavy shoulders, low head, short neck
        hip_h=.72, shoulder_h=.80, rump_z=.50, chest_z=-.44,
        rump=(.38, .38), waist=(.38, .38), chest=(.46, .46), throat=(.32, .30),
        humped=True,
        neck_len=.18, neck_rise=.02, neck_r=(.28, .26), head_drop=-.10,
        skull=(.24, .22, .26), muzzle_len=.30, muzzle_r=(.150, .120), muzzle_drop=.02,
        ear="round", ear_h=.14, ear_w=.11, ear_spread=.13,
        stance="unguligrade", front_x=.21, rear_x=.22, upper_r=.120, lower_r=.078,
        ankle_r=.058, foot_len=.14, foot_r=.082, toes=2,
        tail_len=.30, tail_r=.045, tail_taper=.40, tail_droop=.62,
    ),
    "cervid": _plan(  # elk / ram: long legs, deep chest, high head carriage
        hip_h=.94, shoulder_h=.98, rump_z=.50, chest_z=-.44,
        rump=(.32, .38), waist=(.28, .34), chest=(.34, .44), throat=(.24, .26),
        neck_len=.42, neck_rise=.34, neck_r=(.19, .21),
        skull=(.19, .20, .28), muzzle_len=.30, muzzle_r=(.110, .080), muzzle_drop=.06,
        ear="leaf", ear_h=.24, ear_w=.12, ear_spread=.13, ear_tilt=.55,
        stance="unguligrade", front_x=.19, rear_x=.21, front_z=-.32, rear_z=.36,
        upper_r=.098, lower_r=.058, ankle_r=.042, foot_len=.13, foot_r=.060, toes=2,
        tail_len=.24, tail_r=.055, tail_taper=.34, tail_droop=.50,
    ),
    "sprawler": _plan(  # lizard / crocodile: long low body, splayed limbs
        hip_h=.34, shoulder_h=.34, rump_z=.62, chest_z=-.52,
        rump=(.32, .26), waist=(.30, .24), chest=(.34, .27), throat=(.22, .18),
        belly_drop=.0, back_arch=.0,
        neck_len=.20, neck_rise=.02, neck_r=(.19, .16), head_drop=-.02,
        skull=(.20, .15, .24), muzzle_len=.38, muzzle_r=(.135, .085), muzzle_drop=.0,
        jaw_len=.34, brow=.045,
        ear=None, eye_r=.028, eye_fwd=.05, eye_spread=.085, eye_rise=.062,
        stance="sprawled", front_x=.30, rear_x=.32, front_z=-.34, rear_z=.38,
        upper_r=.080, lower_r=.058, ankle_r=.044, foot_len=.17, foot_r=.055, toes=5,
        tail_len=1.30, tail_r=.150, tail_taper=.10, tail_droop=.04, tail_lift=.0,
        dorsal=(.055, 7),
    ),
    "mustelid": _plan(  # otter / rat: long tubular body, short limbs
        hip_h=.40, shoulder_h=.40, rump_z=.50, chest_z=-.42,
        rump=(.24, .24), waist=(.22, .22), chest=(.25, .25), throat=(.18, .18),
        neck_len=.18, neck_rise=.10, neck_r=(.16, .16),
        skull=(.17, .16, .19), muzzle_len=.20, muzzle_r=(.090, .045), muzzle_drop=.03,
        ear="round", ear_h=.11, ear_w=.11, ear_spread=.095,
        stance="plantigrade", front_x=.17, rear_x=.18, upper_r=.070, lower_r=.052,
        ankle_r=.042, foot_len=.15, foot_r=.055, toes=5,
        tail_len=.86, tail_r=.090, tail_taper=.16, tail_droop=.20,
    ),
    "lagomorph": _plan(  # hare: crouched, huge ears, powerful haunches
        hip_h=.46, shoulder_h=.34, rump_z=.30, chest_z=-.24,
        rump=(.31, .36), waist=(.25, .27), chest=(.24, .25), throat=(.17, .17),
        back_arch=.13,
        neck_len=.13, neck_rise=.30, neck_r=(.15, .15), head_drop=.04,
        skull=(.17, .17, .20), muzzle_len=.13, muzzle_r=(.092, .055), muzzle_drop=.02,
        ear="long", ear_h=.46, ear_w=.12, ear_spread=.075, ear_tilt=.10,
        eye_r=.034, eye_spread=.090, eye_fwd=.04,
        stance="lagomorph", front_x=.13, rear_x=.17, front_z=-.24, rear_z=.24,
        upper_r=.075, lower_r=.055, ankle_r=.045, foot_len=.26, foot_r=.055, toes=4,
        tail_len=.11, tail_r=.070, tail_taper=.45, tail_droop=.30,
    ),
    "anuran": _plan(  # toad: squat, wide, no neck, folded legs
        hip_h=.36, shoulder_h=.33, rump_z=.40, chest_z=-.34,
        rump=(.46, .26), waist=(.48, .27), chest=(.44, .25), throat=(.34, .22),
        belly_drop=.03,
        neck_len=.06, neck_rise=.03, neck_r=(.30, .22), head_drop=.0,
        skull=(.34, .20, .26), muzzle_len=.16, muzzle_r=(.230, .130), muzzle_drop=.0,
        jaw_len=.24, brow=.06,
        ear=None, eye_r=.062, eye_fwd=.06, eye_spread=.135, eye_rise=.090,
        stance="anuran", front_x=.22, rear_x=.28, front_z=-.24, rear_z=.26,
        upper_r=.070, lower_r=.058, ankle_r=.046, foot_len=.24, foot_r=.048, toes=4,
        tail_len=0., tail_r=.0, tails=0,
    ),
    "chelonian": _plan(  # tortoise: domed shell, columnar legs
        hip_h=.30, shoulder_h=.30, rump_z=.44, chest_z=-.40,
        rump=(.34, .24), waist=(.36, .24), chest=(.34, .24), throat=(.20, .18),
        neck_len=.26, neck_rise=.14, neck_r=(.14, .14),
        skull=(.16, .14, .19), muzzle_len=.14, muzzle_r=(.100, .062), muzzle_drop=.02,
        ear=None, eye_r=.026, eye_spread=.075, eye_fwd=.05,
        stance="columnar", front_x=.26, rear_x=.27, front_z=-.28, rear_z=.30,
        upper_r=.088, lower_r=.078, ankle_r=.070, foot_len=.13, foot_r=.085, toes=4,
        tail_len=.16, tail_r=.055, tail_taper=.40, tail_droop=.40,
        shell=True,
    ),
    "bovine": _plan(  # aurochs, yak: deep chest, heavy shoulders, low head
        hip_h=.86, shoulder_h=.94, rump_z=.54, chest_z=-.46,
        rump=(.38, .40), waist=(.36, .38), chest=(.44, .46), throat=(.30, .30),
        humped=True,
        neck_len=.26, neck_rise=.06, neck_r=(.26, .26), head_drop=-.08,
        skull=(.22, .21, .27), muzzle_len=.26, muzzle_r=(.145, .120), muzzle_drop=.03,
        ear="round", ear_h=.15, ear_w=.13, ear_spread=.17,
        stance="unguligrade", front_x=.22, rear_x=.23, upper_r=.115, lower_r=.072,
        ankle_r=.052, foot_len=.15, foot_r=.078, toes=2,
        tail_len=.62, tail_r=.052, tail_taper=.22, tail_droop=.66, tail_bush=1.5,
        horn="bovine",
    ),
    "equine": _plan(  # pony, horse: long legs, arched neck, mane
        hip_h=.92, shoulder_h=.98, rump_z=.52, chest_z=-.46,
        rump=(.30, .38), waist=(.28, .36), chest=(.32, .44), throat=(.22, .26),
        neck_len=.44, neck_rise=.30, neck_r=(.19, .24),
        skull=(.17, .19, .30), muzzle_len=.32, muzzle_r=(.105, .085), muzzle_drop=.07,
        ear="pointed", ear_h=.17, ear_w=.10, ear_spread=.09,
        stance="unguligrade", front_x=.18, rear_x=.20, front_z=-.32, rear_z=.36,
        upper_r=.098, lower_r=.055, ankle_r=.040, foot_len=.14, foot_r=.062, toes=2,
        tail_len=.70, tail_r=.070, tail_taper=.42, tail_droop=.58, tail_bush=1.7,
    ),
    "pinniped": _plan(  # seal: torpedo body, flippers, no real legs
        hip_h=.26, shoulder_h=.30, rump_z=.62, chest_z=-.44,
        rump=(.20, .20), waist=(.28, .27), chest=(.30, .29), throat=(.22, .21),
        neck_len=.14, neck_rise=.10, neck_r=(.19, .19),
        skull=(.19, .18, .22), muzzle_len=.16, muzzle_r=(.105, .070), muzzle_drop=.03,
        ear=None, eye_r=.036, eye_spread=.080, eye_fwd=.07,
        stance="sprawled", front_x=.20, rear_x=.14, front_z=-.26, rear_z=.46,
        upper_r=.070, lower_r=.058, ankle_r=.050, foot_len=.26, foot_r=.050, toes=4,
        tail_len=.20, tail_r=.090, tail_taper=.30, tail_droop=.10,
    ),
    "gryphon": _plan(  # eagle fore, feline hind, feathered wings
        hip_h=.80, shoulder_h=.86, rump_z=.50, chest_z=-.44,
        rump=(.32, .34), waist=(.28, .30), chest=(.36, .38), throat=(.24, .26),
        neck_len=.32, neck_rise=.24, neck_r=(.19, .20),
        skull=(.19, .19, .22), muzzle_len=.24, muzzle_r=(.110, .045), muzzle_drop=.10,
        ear=None, eye_r=.032, eye_spread=.088, eye_fwd=.09, brow=.040,
        stance="digitigrade", front_x=.20, rear_x=.22, upper_r=.095, lower_r=.066,
        ankle_r=.050, foot_len=.19, foot_r=.072, toes=4,
        tail_len=.74, tail_r=.090, tail_taper=.20, tail_droop=.30, tail_bush=1.3,
        wings=True, mane_ruff=True,
    ),
    "drake": _plan(  # winged reptile
        hip_h=.62, shoulder_h=.66, rump_z=.52, chest_z=-.44,
        rump=(.30, .30), waist=(.28, .28), chest=(.36, .36), throat=(.22, .22),
        neck_len=.34, neck_rise=.26, neck_r=(.18, .18),
        skull=(.20, .18, .25), muzzle_len=.30, muzzle_r=(.120, .065), muzzle_drop=.02,
        jaw_len=.26, brow=.05, ear=None,
        eye_r=.030, eye_fwd=.07, eye_spread=.085, eye_rise=.060,
        stance="sprawled", front_x=.24, rear_x=.26, front_z=-.30, rear_z=.34,
        upper_r=.082, lower_r=.058, ankle_r=.046, foot_len=.17, foot_r=.055, toes=4,
        tail_len=1.10, tail_r=.120, tail_taper=.10, tail_droop=.10,
        dorsal=(.070, 8), wings=True,
    ),
}

ARCHETYPE_PLANS = {
    "fox": "canid", "two_tail_fox": "canid", "wolf": "canid",
    "cat": "felid", "saber_cat": "felid",
    "bear": "ursine", "porcupine": "ursine",
    "boar": "suid", "rhino": "suid",
    "elk": "cervid", "ram": "cervid",
    "lizard": "sprawler", "crocodile": "sprawler",
    "otter": "mustelid", "rat": "mustelid",
    "hare": "lagomorph", "toad": "anuran",
    "tortoise": "chelonian", "drake": "drake",
}


def plan_for(archetype: str) -> dict:
    """Accept either a concrete archetype ("fox") or a body-plan key ("canid")."""
    if archetype in BODY_PLANS:
        return BODY_PLANS[archetype]
    return BODY_PLANS[ARCHETYPE_PLANS.get(archetype, "canid")]


# ---------------------------------------------------------------------------
# Per-archetype feature tuning applied on top of the shared plan
# ---------------------------------------------------------------------------
ARCHETYPE_TWEAKS = {
    "wolf": dict(muzzle_len=.30, skull=(.21, .21, .26), tail_droop=.42, tail_bush=1.25,
                 ear_h=.20, upper_r=.100),
    "fox": dict(muzzle_len=.29, muzzle_r=(.100, .042), ear_h=.26, ear_w=.13,
                tail_bush=1.85, tail_len=.78, tail_droop=.40, upper_r=.080,
                lower_r=.055, skull=(.185, .185, .23)),
    "two_tail_fox": dict(muzzle_len=.29, muzzle_r=(.100, .042), ear_h=.26, ear_w=.13,
                         tail_bush=1.85, tail_len=.78, tail_droop=.40, tails=2,
                         upper_r=.080, lower_r=.055, skull=(.185, .185, .23)),
    "cat": dict(tail_bush=1.0),
    "saber_cat": dict(tail_bush=1.0, horn="fangs", skull=(.23, .21, .24),
                      muzzle_len=.21, upper_r=.112, lower_r=.076),
    "bear": dict(),
    "porcupine": dict(spines=(.30, 26), rump=(.42, .46), chest=(.40, .42),
                      muzzle_len=.22, ear_h=.10),
    "boar": dict(horn="tusks"),
    "rhino": dict(horn="nasal", plates=True, rump=(.42, .40), chest=(.50, .48)),
    "elk": dict(horn="antlers"),
    "ram": dict(horn="curl"),
    "lizard": dict(),
    "crocodile": dict(muzzle_len=.46, muzzle_r=(.150, .100), jaw_len=.42,
                      tail_len=1.45, dorsal=(.065, 9), rump=(.34, .28)),
    "otter": dict(tail_bush=1.0, tail_r=.100, tail_taper=.20),
    "rat": dict(tail_bush=.0, tail_r=.070, tail_taper=.34, tail_len=.92,
                ear="round", ear_h=.15, ear_w=.15, muzzle_len=.22),
    "hare": dict(), "toad": dict(), "tortoise": dict(), "drake": dict(),
}


# ---------------------------------------------------------------------------
# Concept-derived proportions
# ---------------------------------------------------------------------------
# Two creatures built on one body plan are the same model in two palettes, and
# that is exactly what the roster looked like: every canid was the same wolf.
# ``concept_proportions.py`` measures each concept figure and writes ratios --
# how lanky, how top-heavy, how solid, how tapered it is relative to the other
# creatures on its plan -- and those ratios drive the multipliers below, so the
# silhouettes diverge from the artwork rather than from invention.
_PROPORTION_PATH = _Path(__file__).with_name("concept_proportions.json")
try:
    CONCEPT_PROPORTIONS = _json.loads(_PROPORTION_PATH.read_text())
except (OSError, ValueError):     # measuring is optional; plans still build
    CONCEPT_PROPORTIONS = {}

NEUTRAL_PROPORTIONS = {"tall": 1.0, "girth": 1.0, "shoulder": 1.0, "hip": 1.0,
                       "limb": 1.0, "head": 1.0, "taper": 1.0}


def proportions(variant: str | None) -> dict:
    """Silhouette multipliers for one creature, from its concept measurements.

    The measured ratios are deliberately damped: the art is stylised and drawn
    at whatever angle suited the sheet, so they are meant to *nudge* a plan --
    a hyena higher at the shoulder than the hip -- not to rebuild it.
    """
    m = CONCEPT_PROPORTIONS.get(variant or "")
    if not m:
        return dict(NEUTRAL_PROPORTIONS)
    aspect, rake = float(m["aspect"]), float(m["rake"])
    bulk, taper = float(m["bulk"]), float(m["taper"])
    return {
        # Lanky figures grow taller and thin out; squat ones do the reverse.
        "tall": 1.0 + (aspect - 1.0) * .40,
        "girth": (1.0 - (aspect - 1.0) * .24) * (1.0 + (bulk - 1.0) * .32),
        # Top-heavy figures carry it in the shoulders, not the hips.
        "shoulder": 1.0 + (rake - 1.0) * .34,
        "hip": 1.0 - (rake - 1.0) * .18,
        "limb": 1.0 + (aspect - 1.0) * .30 - (bulk - 1.0) * .12,
        "head": 1.0 + (rake - 1.0) * .16 - (aspect - 1.0) * .12,
        "taper": 1.0 + (taper - 1.0) * .26,
    }


def scale_plan(plan: dict, mult: dict, rules: dict) -> dict:
    """Return ``plan`` with the keys named in ``rules`` scaled by ``mult``.

    Values may be scalars or tuples; tuples are scaled component-wise so a
    ``(width, depth)`` girth stays a girth.
    """
    out = dict(plan)
    for key, name in rules.items():
        factor = mult.get(name, 1.0)
        if factor == 1.0 or key not in out:
            continue
        value = out[key]
        if isinstance(value, tuple):
            out[key] = tuple(v * factor for v in value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value * factor
    return out


QUADRUPED_PROPORTION_RULES = {
    "hip_h": "tall", "shoulder_h": "tall",
    "rump": "hip", "waist": "girth", "chest": "shoulder", "throat": "girth",
    "neck_r": "girth", "neck_len": "tall",
    "upper_r": "girth", "lower_r": "girth", "ankle_r": "girth",
    "foot_r": "girth", "foot_len": "limb",
    "front_x": "shoulder", "rear_x": "hip",
    "skull": "head", "muzzle_len": "head",
    "tail_len": "limb", "tail_r": "girth",
}


# ``ARCHETYPE_TWEAKS`` is keyed by concrete archetype ("wolf", "fox").  The
# roster names body plans instead ("canid", "felid"), so none of it ever
# applied to a roster creature: every roster canid was the bare canid baseline
# in a different palette, and measured proportions were the only thing telling
# them apart.  This is where per-creature features from the art live -- the
# ruff on a dire wolf, the mane on a lion, the sloping back of a hyena.
QUADRUPED_DETAIL = {
    # Canids.  The art gives all of them a heavy shoulder ruff and a longer,
    # deeper muzzle than the baseline; the dire wolves are big-headed.
    "moorfell_wolf": dict(mane_ruff=1.15, muzzle_len=.32, ear_h=.26,
                          skull=(.23, .23, .28), tail_bush=1.35),
    "bramble_wolf": dict(mane_ruff=1.05, muzzle_len=.31, ear_h=.25,
                         skull=(.22, .22, .27), tail_bush=1.25),
    "facet_hound": dict(muzzle_len=.30, ear_h=.27, skull=(.22, .21, .27),
                        tail_bush=.85),
    "ivy_hound": dict(mane_ruff=.85, muzzle_len=.29, ear_h=.24),
    "dust_hyena": dict(shoulder_h=.90, hip_h=.70, mane_ruff=.95, ear="round",
                       ear_h=.20, ear_w=.17, skull=(.22, .22, .26),
                       muzzle_len=.26, tail_bush=1.15),
    # Felids.  A lion is mostly mane in the art, and it is the one thing that
    # separated the two lions from the two wolves.
    "stormmane_lion": dict(mane_ruff=1.95, tail_bush=1.5, skull=(.23, .21, .24),
                           muzzle_len=.21),
    "gilded_water_lion": dict(mane_ruff=1.70, tail_bush=1.4,
                              skull=(.23, .21, .24)),
    "canopy_lynx": dict(ear_h=.30, ear_w=.13, tail_bush=1.1, tail_len=.42),
    # Equines and bovines: a standing mane along the crest of the neck.
    "moor_pony": dict(mane_ruff=1.25, tail_bush=1.6, muzzle_len=.34,
                      skull=(.19, .21, .30)),
    "goldmane_aurochs": dict(mane_ruff=1.45, horn="curl"),
    "whitehorn_yak": dict(mane_ruff=1.60, horn="curl", tail_bush=1.3),
    "moorhorn_ram": dict(horn="curl", mane_ruff=1.05),
    # Cervids keep their antlers and gain the throat ruff the art shows.
    "spectral_moor_stag": dict(horn="antlers", mane_ruff=.90),
    "bramble_stag": dict(horn="antlers", mane_ruff=.85),
    "lantern_stag": dict(horn="antlers", mane_ruff=.85),
    "moss_bear": dict(mane_ruff=.80),
    "mossback_anteater": dict(muzzle_len=.52, muzzle_r=(.085, .060),
                              tail_bush=1.7),
    # Stone beasts: the art clads these in overlapping plate the same way it
    # clads the bipedal golems, and sets a lit gem over the shoulder.
    "reefplate_golem": dict(plated=1.0, plate_shape="scale", runes=.25,
                            core=.62, shell=True, mane_ruff=.0,
                            skull=(.24, .22, .24)),
    "cairnback_tortoise": dict(plated=.75, plate_shape="slab", runes=.20),
    "geode_tortoise": dict(plated=.85, plate_shape="shard", runes=.35,
                           core=.46),
    "crystalwing": dict(plated=.70, plate_shape="shard", runes=.30),
    "prism_drake": dict(plated=.65, plate_shape="shard", runes=.30),
    "facet_hound": dict(plated=.60, plate_shape="shard", runes=.25),
}


def resolved_plan(archetype: str, variant: str | None = None) -> dict:
    plan = dict(plan_for(archetype))
    plan.update(ARCHETYPE_TWEAKS.get(archetype, {}))
    if variant:
        plan.update(QUADRUPED_DETAIL.get(variant, {}))
        plan = scale_plan(plan, proportions(variant),
                          QUADRUPED_PROPORTION_RULES)
    # Stamped so feature code can seed deterministically off the creature
    # without every helper having to carry the slug through its arguments.
    plan["_variant"] = variant or archetype
    return plan


# ---------------------------------------------------------------------------
# Skeleton construction
# ---------------------------------------------------------------------------
def skeleton_for(archetype: str, scale: float, variant: str | None = None
                 ) -> list[tuple[str, int, tuple[float, float, float]]]:
    """Rest-pose bone table (name, parent, local translation) for a creature."""
    p = resolved_plan(archetype, variant)
    s = scale
    hip_h, sho_h = p["hip_h"] * s, p["shoulder_h"] * s
    rump_z, chest_z = p["rump_z"] * s, p["chest_z"] * s

    body_g = np.array((0., hip_h, rump_z * .38))
    chest_g = np.array((0., sho_h, chest_z * .62))
    neck_g = chest_g + np.array((0., p["neck_rise"] * .45 * s, (chest_z * .38) - .02 * s))
    head_g = neck_g + np.array((0., p["neck_rise"] * .55 * s + p["head_drop"] * s,
                                -p["neck_len"] * s))
    jaw_g = head_g + np.array((0., -p["skull"][1] * .45 * s, -p["skull"][2] * .35 * s))

    globals_: dict[str, np.ndarray] = {
        "root": np.zeros(3), "body": body_g, "chest": chest_g,
        "neck": neck_g, "head": head_g, "jaw": jaw_g,
    }

    # Tail chain marches back and down from the rump.
    tail_n = 4
    tail_len = p["tail_len"] * s
    for i in range(tail_n):
        t = (i + 1) / tail_n
        droop = p["tail_droop"] * tail_len * (t ** 1.6)
        lift = p["tail_lift"] * tail_len * math.sin(t * math.pi)
        globals_[f"tail_{i + 1}"] = body_g + np.array(
            ((0.), (rump_z - body_g[1] * 0) * 0 - droop + lift + (.05 * s if i == 0 else 0.),
             (rump_z - body_g[2]) + tail_len * t))

    # Limbs
    stance = p["stance"]
    for side, sign in (("l", -1.), ("r", 1.)):
        fx, rx = p["front_x"] * s * sign, p["rear_x"] * s * sign
        fz, rz = p["front_z"] * s, p["rear_z"] * s
        if stance == "sprawled":
            fx *= 1.05
            rx *= 1.05
        front_hip = np.array((fx, sho_h * .92, fz))
        rear_hip = np.array((rx, hip_h * .96, rz))
        if stance == "digitigrade":
            fk, fa = .52, .20
            rk, ra = .50, .20
        elif stance == "plantigrade":
            fk, fa = .50, .16
            rk, ra = .48, .16
        elif stance == "unguligrade":
            fk, fa = .55, .26
            rk, ra = .54, .26
        elif stance == "sprawled":
            fk, fa = .55, .22
            rk, ra = .55, .22
        elif stance == "columnar":
            fk, fa = .55, .22
            rk, ra = .55, .22
        elif stance == "lagomorph":
            fk, fa = .50, .20
            rk, ra = .46, .22
        else:  # anuran
            fk, fa = .50, .20
            rk, ra = .44, .20

        knee_out = .0
        if stance == "sprawled":
            knee_out = .22 * s * sign
        # Fore limb: elbow trails, wrist returns forward.  Hind limb: stifle
        # drives forward, hock kicks back - the classic quadruped zig-zag.
        front_knee = np.array((fx + knee_out, front_hip[1] * fk,
                               fz + p["knee_fwd"] * s * .55))
        front_ankle = np.array((fx + knee_out * 1.15, front_hip[1] * fa,
                                fz - p["knee_fwd"] * s * .35))
        rear_knee = np.array((rx + knee_out, rear_hip[1] * rk,
                              rz - p["hock_back"] * s * .75))
        rear_ankle = np.array((rx + knee_out * 1.15, rear_hip[1] * ra,
                               rz + p["hock_back"] * s * .55))
        globals_[f"front_leg_{side}"] = front_hip
        globals_[f"front_shin_{side}"] = front_knee
        globals_[f"front_paw_{side}"] = front_ankle
        globals_[f"rear_leg_{side}"] = rear_hip
        globals_[f"rear_shin_{side}"] = rear_knee
        globals_[f"rear_paw_{side}"] = rear_ankle

    globals_["wing_l"] = chest_g + np.array((-.14 * s, .06 * s, .02 * s))
    globals_["wing_r"] = chest_g + np.array((.14 * s, .06 * s, .02 * s))

    bones = []
    for name, parent in BONE_TOPOLOGY:
        position = globals_[name]
        base = np.zeros(3) if parent < 0 else globals_[BONE_TOPOLOGY[parent][0]]
        bones.append((name, parent, tuple(float(v) for v in (position - base))))
    return bones


def global_positions(bones) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for _, parent, translation in bones:
        base = np.zeros(3) if parent < 0 else result[parent]
        result.append(base + np.asarray(translation, dtype=float))
    return result


# ---------------------------------------------------------------------------
# Mesh authoring with smooth skin weights
# ---------------------------------------------------------------------------
MATERIAL_SLOTS = 6


class AnatomyMesh:
    """Primitive authoring helper that emits smooth, multi-bone skin weights."""

    def __init__(self, bone_globals: list[np.ndarray]):
        self.bones = np.asarray(bone_globals, dtype=float)
        self.groups = [([], [], [], [], [], []) for _ in range(MATERIAL_SLOTS)]
        # (spine points, per-point radii, bones) recorded by whichever family
        # built the body, so surface growth can be scattered over it later.
        self.torso = None

    # -- skinning ----------------------------------------------------------
    def _weights(self, positions: np.ndarray, candidates: list[int]):
        """Inverse-distance blend across a curated candidate bone set.

        Restricting candidates per body part keeps a rear paw from pulling on
        the jaw while still producing smooth shoulder / hip / neck transitions.
        """
        points = np.asarray(positions, dtype=float)
        joints = np.zeros((len(points), 4), dtype="uint16")
        weights = np.zeros((len(points), 4), dtype="float32")
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            weights[:, 0] = 1.0
            return joints, weights
        if len(candidates) == 1:
            joints[:, 0] = candidates[0]
            weights[:, 0] = 1.0
            return joints, weights
        centres = self.bones[candidates]
        delta = points[:, None, :] - centres[None, :, :]
        distance = np.linalg.norm(delta, axis=2)
        influence = 1.0 / np.power(distance + 1e-3, 3.0)
        order = np.argsort(-influence, axis=1)[:, :4]
        rows = np.arange(len(points))[:, None]
        picked = influence[rows, order]
        picked = picked / np.maximum(picked.sum(axis=1, keepdims=True), 1e-9)
        # Drop negligible influences so the runtime keeps meaningful weights.
        picked[picked < .02] = 0.0
        picked = picked / np.maximum(picked.sum(axis=1, keepdims=True), 1e-9)
        lookup = np.asarray(candidates)
        joints[:, :order.shape[1]] = lookup[order]
        weights[:, :order.shape[1]] = picked
        return joints, weights

    def _append_multi(self, positions, normals, uvs, faces_by_material, candidates):
        """Append one vertex set split across materials, compacting each subset."""
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        for material, faces in faces_by_material.items():
            if not faces:
                continue
            flat = np.asarray(faces, dtype=np.int64).reshape(-1)
            used, remapped = np.unique(flat, return_inverse=True)
            self._append(positions[used],
                         np.asarray(normals, dtype=float).reshape(-1, 3)[used],
                         np.asarray(uvs, dtype=float).reshape(-1, 2)[used],
                         remapped, material, candidates)

    def _append(self, positions, normals, uvs, indices, material, candidates):
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        normals = np.asarray(normals, dtype=float).reshape(-1, 3)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.maximum(lengths, 1e-9)
        uvs = np.asarray(uvs, dtype=float).reshape(-1, 2)
        joints, weights = self._weights(positions, candidates)
        p, n, t, f, j, w = self.groups[material]
        base = len(p)
        p.extend(map(tuple, positions))
        n.extend(map(tuple, normals))
        t.extend(map(tuple, uvs))
        f.extend(base + int(i) for i in np.asarray(indices).reshape(-1))
        j.extend(map(tuple, joints))
        w.extend(map(tuple, weights))

    # -- primitives --------------------------------------------------------
    @staticmethod
    def _frame(tangent: np.ndarray):
        tangent = tangent / max(np.linalg.norm(tangent), 1e-9)
        reference = np.array((0., 1., 0.))
        if abs(float(np.dot(tangent, reference))) > .88:
            reference = np.array((0., 0., -1.))
        right = np.cross(reference, tangent)
        right /= max(np.linalg.norm(right), 1e-9)
        up = np.cross(tangent, right)
        up /= max(np.linalg.norm(up), 1e-9)
        return right, up

    def tube(self, points, radii, candidates, material=MAT_BODY, sides=16,
             cap_start=True, cap_end=True, uv_scale=1.0,
             lower_material=None, lower_threshold=-.32):
        """Swept elliptical tube. ``radii`` is a per-row (width, height) pair."""
        centres = np.asarray(points, dtype=float)
        radii = [(float(a), float(b)) for a, b in radii]
        # Coincident control points give a zero-length tangent and therefore a
        # degenerate frame, so collapse them before sweeping.
        if len(centres) > 1:
            keep = [0]
            for i in range(1, len(centres)):
                if np.linalg.norm(centres[i] - centres[keep[-1]]) > 1e-5:
                    keep.append(i)
            if len(keep) < len(centres):
                centres = centres[keep]
                radii = [radii[i] for i in keep]
        if len(centres) < 2:
            return
        positions, normals, uvs, faces = [], [], [], []
        arc = [0.0]
        for i in range(1, len(centres)):
            arc.append(arc[-1] + float(np.linalg.norm(centres[i] - centres[i - 1])))
        total = max(arc[-1], 1e-6)
        for row, centre in enumerate(centres):
            if row == 0:
                tangent = centres[1] - centre
            elif row == len(centres) - 1:
                tangent = centre - centres[row - 1]
            else:
                tangent = centres[row + 1] - centres[row - 1]
            right, up = self._frame(tangent)
            rx, ry = radii[row]
            for side in range(sides):
                angle = 2 * math.pi * side / sides
                offset = right * (rx * math.cos(angle)) + up * (ry * math.sin(angle))
                normal = right * (math.cos(angle) / max(rx, 1e-5)) + up * (math.sin(angle) / max(ry, 1e-5))
                positions.append(centre + offset)
                normals.append(normal)
                uvs.append((side / sides, arc[row] / total * uv_scale))
        under: list[int] = []
        for row in range(len(centres) - 1):
            for side in range(sides):
                nxt = (side + 1) % sides
                a = row * sides + side
                b = row * sides + nxt
                c = (row + 1) * sides + side
                d = (row + 1) * sides + nxt
                quad = (a, c, b, b, c, d)
                mid = math.sin(2 * math.pi * (side + .5) / sides)
                # Ends stay on the primary material so caps never show a seam.
                belly = (lower_material is not None and mid < lower_threshold
                         and 0 < row < len(centres) - 2)
                (under if belly else faces).extend(quad)
        # Caps keep the shell closed so normals and silhouettes stay solid.
        for cap, row in ((cap_start, 0), (cap_end, len(centres) - 1)):
            if not cap:
                continue
            centre = centres[row]
            tangent = (centres[1] - centres[0]) if row == 0 else (centres[-1] - centres[-2])
            tangent = tangent / max(np.linalg.norm(tangent), 1e-9)
            outward = -tangent if row == 0 else tangent
            hub = len(positions)
            positions.append(centre + outward * (min(radii[row]) * .28))
            normals.append(outward)
            uvs.append((.5, arc[row] / total * uv_scale))
            ring = row * sides
            for side in range(sides):
                nxt = (side + 1) % sides
                if row == 0:
                    faces.extend((hub, ring + side, ring + nxt))
                else:
                    faces.extend((hub, ring + nxt, ring + side))
        if under:
            self._append_multi(positions, normals, uvs,
                               {material: faces, lower_material: under}, candidates)
        else:
            self._append(positions, normals, uvs, faces, material, candidates)

    def ellipsoid(self, centre, size, candidates, material=MAT_BODY,
                  rings=10, sides=18, squash=None):
        cx, cy, cz = centre
        sx, sy, sz = (v * .5 for v in size)
        positions, normals, uvs, faces = [], [], [], []
        for ring in range(rings + 1):
            theta = math.pi * ring / rings
            for side in range(sides + 1):
                phi = 2 * math.pi * side / sides
                nx = math.sin(theta) * math.cos(phi)
                ny = math.cos(theta)
                nz = math.sin(theta) * math.sin(phi)
                x, y, z = cx + sx * nx, cy + sy * ny, cz + sz * nz
                if squash is not None:
                    y = cy + (y - cy) * (1.0 if nz >= 0 else squash)
                positions.append((x, y, z))
                normals.append((nx / max(sx, 1e-5), ny / max(sy, 1e-5), nz / max(sz, 1e-5)))
                uvs.append((side / sides, ring / rings))
        for ring in range(rings):
            for side in range(sides):
                a = ring * (sides + 1) + side
                b = a + sides + 1
                faces.extend((a, b, a + 1, a + 1, b, b + 1))
        self._append(positions, normals, uvs, faces, material, candidates)

    def spike(self, start, end, radius, candidates, material=MAT_FEATURE, sides=10):
        """A tapered cone used for claws, horns, spines and tusks."""
        self.tube([np.asarray(start, dtype=float), np.asarray(end, dtype=float)],
                  [(radius, radius), (radius * .06, radius * .06)],
                  candidates, material, sides, cap_start=True, cap_end=True)

    def arrays(self):
        out = []
        for p, n, u, f, j, w in self.groups:
            out.append((np.asarray(p, dtype="float32").reshape(-1, 3),
                        np.asarray(n, dtype="float32").reshape(-1, 3),
                        np.asarray(u, dtype="float32").reshape(-1, 2),
                        np.asarray(f, dtype="uint32").reshape(-1),
                        np.asarray(j, dtype="uint16").reshape(-1, 4),
                        np.asarray(w, dtype="float32").reshape(-1, 4)))
        return out


def _sheet(mesh: AnatomyMesh, edge_a, edge_b, thickness, candidates,
           material=MAT_FEATURE):
    """Two-sided membrane between two edge curves (wings, fins, large ears)."""
    a = np.asarray(edge_a, dtype=float)
    b = np.asarray(edge_b, dtype=float)
    count = len(a)
    if count < 2 or len(b) != count:
        return
    mid = (a + b) * .5
    tangent = np.gradient(mid, axis=0)
    span = b - a
    normal = np.cross(tangent, span)
    lengths = np.linalg.norm(normal, axis=1, keepdims=True)
    # A collapsed span would yield a zero normal; fall back to the local frame.
    degenerate = (lengths[:, 0] < 1e-7)
    if degenerate.any():
        fallback = np.cross(tangent, np.array((0., 1., 0.)))
        fb_len = np.linalg.norm(fallback, axis=1, keepdims=True)
        fallback = np.where(fb_len > 1e-7, fallback / np.maximum(fb_len, 1e-9),
                            np.array((0., 0., 1.)))
        normal[degenerate] = fallback[degenerate]
        lengths = np.linalg.norm(normal, axis=1, keepdims=True)
    normal = normal / np.maximum(lengths, 1e-9)
    positions, normals, uvs, faces = [], [], [], []
    for sign in (1., -1.):
        base = len(positions)
        for i in range(count):
            positions.append(a[i] + normal[i] * thickness * sign * .5)
            normals.append(normal[i] * sign)
            uvs.append((0., i / (count - 1)))
            positions.append(b[i] + normal[i] * thickness * sign * .5)
            normals.append(normal[i] * sign)
            uvs.append((1., i / (count - 1)))
        for i in range(count - 1):
            p0 = base + i * 2
            if sign > 0:
                faces.extend((p0, p0 + 2, p0 + 1, p0 + 1, p0 + 2, p0 + 3))
            else:
                faces.extend((p0, p0 + 1, p0 + 2, p0 + 1, p0 + 3, p0 + 2))
    mesh._append(positions, normals, uvs, faces, material, candidates)


def creature_geometry(archetype: str, scale: float, bones=None,
                      variant: str | None = None) -> AnatomyMesh:
    """Author a full production creature body for ``archetype``."""
    p = resolved_plan(archetype, variant)
    s = scale
    bones = bones if bones is not None else skeleton_for(archetype, s, variant)
    g = global_positions(bones)
    B = BONE_INDEX
    mesh = AnatomyMesh(g)

    body_i, chest_i, neck_i, head_i, jaw_i = (B["body"], B["chest"], B["neck"],
                                              B["head"], B["jaw"])
    torso_bones = [body_i, chest_i, neck_i]

    # ---- torso ---------------------------------------------------------
    rump_z, chest_z = p["rump_z"] * s, p["chest_z"] * s
    hip_h, sho_h = p["hip_h"] * s, p["shoulder_h"] * s
    rump = tuple(v * s for v in p["rump"])
    waist = tuple(v * s for v in p["waist"])
    chest = tuple(v * s for v in p["chest"])
    throat = tuple(v * s for v in p["throat"])

    profile = [(0.00, (rump[0] * .62, rump[1] * .60)),
               (0.06, (rump[0] * .84, rump[1] * .86)),
               (0.16, (rump[0] * .97, rump[1] * .99)),
               (0.30, (rump[0], rump[1])),
               (0.52, (waist[0], waist[1])),
               (0.74, (chest[0] * .97, chest[1] * .97)),
               (0.88, (chest[0], chest[1])),
               (1.00, (throat[0], throat[1]))]
    spine, radii = [], []
    for t, (rx, ry) in profile:
        z = rump_z + (chest_z - rump_z) * t
        y = hip_h + (sho_h - hip_h) * t
        y += p["back_arch"] * s * math.sin(t * math.pi)
        if p["humped"]:
            y += .085 * s * math.exp(-((t - .74) ** 2) / .012)
        y -= p["belly_drop"] * s * math.sin(t * math.pi) * .5
        spine.append(np.array((0., y, z)))
        radii.append((rx, ry))
    mesh.tube(spine, radii, torso_bones, MAT_BODY, sides=20, uv_scale=2.0,
              lower_material=MAT_ACCENT, lower_threshold=-.42)
    # Growth runs from rump to skull, so moss and crystal reach the head rather
    # than stopping at the shoulders.
    skull_size = tuple(v * s for v in p["skull"])
    mesh.torso = (list(spine) + [g[neck_i], g[head_i]],
                  list(radii) + [(throat[0] * .9, throat[1] * .9),
                                 (skull_size[0] * .5, skull_size[1] * .5)],
                  list(torso_bones) + [head_i])

    family = archetype if archetype in BODY_PLANS else ARCHETYPE_PLANS.get(archetype, "canid")
    if family == "anuran":
        _anuran_head(mesh, p, s, g, B, spine, radii)
        _features(mesh, p, s, g, B, spine, radii, g[head_i],
                  tuple(v * s for v in p["skull"]),
                  g[head_i] + np.array((0., 0., -p["muzzle_len"] * s)), p["muzzle_r"][1] * s)
        _limbs_and_tail(mesh, p, s, g, B, spine, radii, archetype)
        return mesh

    # ---- neck ----------------------------------------------------------
    # Begin the neck behind the throat plane so it emerges through the chest.
    neck_start = spine[-1] * .72 + spine[-2] * .28
    head_g = g[head_i]
    neck_pts, neck_radii = [], []
    for i in range(6):
        t = i / 5
        point = neck_start * (1 - t) + head_g * t
        point = point + np.array((0., p["neck_rise"] * s * .16 * math.sin(t * math.pi), 0.))
        neck_pts.append(point)
        rx = throat[0] * .94 * (1 - t) + p["neck_r"][0] * s * t
        ry = throat[1] * .94 * (1 - t) + p["neck_r"][1] * s * t
        neck_radii.append((rx * (1 - .16 * t), ry * (1 - .10 * t)))
    mesh.tube(neck_pts, neck_radii, [chest_i, neck_i, head_i], MAT_BODY, sides=16,
              cap_start=False, cap_end=False)

    # ---- head ----------------------------------------------------------
    skull = tuple(v * s for v in p["skull"])
    mesh.ellipsoid(tuple(head_g), skull, [head_i, neck_i], MAT_BODY, rings=12, sides=20)

    muzzle_len = p["muzzle_len"] * s
    m0, m1 = (v * s for v in p["muzzle_r"])
    muzzle_root = head_g + np.array((0., -p["muzzle_drop"] * s * .4, -skull[2] * .30))
    muzzle_tip = muzzle_root + np.array((0., -p["muzzle_drop"] * s, -muzzle_len))
    muzzle_pts = [muzzle_root * (1 - t) + muzzle_tip * t for t in (0., .38, .72, 1.)]
    mesh.tube(muzzle_pts,
              [(m0, m0 * .95), (m0 * .84, m0 * .80), (m1 * 1.25, m1 * 1.15), (m1, m1 * .92)],
              [head_i, jaw_i], MAT_BODY, sides=14, cap_start=False)

    # Lower jaw is bound to the jaw bone so bites and roars actually open.
    jaw_len = p["jaw_len"] * s
    jaw_g = g[jaw_i]
    jaw_dir = np.array((0., -.05, -1.))
    jaw_dir /= np.linalg.norm(jaw_dir)
    jaw_pts = [jaw_g + jaw_dir * jaw_len * t for t in (0., .45, .85, 1.)]
    mesh.tube(jaw_pts,
              [(m0 * .82, m0 * .48), (m0 * .74, m0 * .42), (m1 * 1.15, m1 * .70), (m1 * .85, m1 * .55)],
              [jaw_i, head_i], MAT_BODY, sides=12, cap_start=False)

    # Brow ridge gives reptiles and heavy predators a readable scowl.
    if p["brow"]:
        for side in (-1., 1.):
            mesh.ellipsoid(tuple(head_g + np.array((side * p["eye_spread"] * s * 1.02,
                                                    p["eye_rise"] * s + p["brow"] * s * .55,
                                                    -p["eye_fwd"] * s * 1.05))),
                           (p["brow"] * s * 2.1, p["brow"] * s * 1.15, p["brow"] * s * 2.6),
                           [head_i], MAT_BODY, rings=6, sides=10)

    # Eyes and nose in the dark slot read at gameplay distance.
    eye_r = p["eye_r"] * s
    for side in (-1., 1.):
        mesh.ellipsoid(tuple(head_g + np.array((side * p["eye_spread"] * s,
                                                p["eye_rise"] * s,
                                                -p["eye_fwd"] * s))),
                       (eye_r * 2, eye_r * 2, eye_r * 2), [head_i], MAT_DARK,
                       rings=7, sides=12)
    mesh.ellipsoid(tuple(muzzle_tip + np.array((0., m1 * .30, -m1 * .30))),
                   (m1 * 1.30, m1 * .95, m1 * 1.05), [head_i], MAT_DARK, rings=7, sides=12)

    # ---- ears ----------------------------------------------------------
    ear = p["ear"]
    if ear:
        ear_h, ear_w = p["ear_h"] * s, p["ear_w"] * s
        base_y = head_g[1] + skull[1] * .34
        base_z = head_g[2] + skull[2] * .10
        for side in (-1., 1.):
            bx = side * p["ear_spread"] * s
            root = np.array((bx, base_y, base_z))
            tilt = np.array((side * p["ear_tilt"], 1., p["ear_tilt"] * .35))
            tilt /= np.linalg.norm(tilt)
            if ear in ("pointed", "rounded_point"):
                tip = root + tilt * ear_h
                mid = root + tilt * ear_h * .55
                mesh.tube([root, mid, tip],
                          [(ear_w * .55, ear_w * .30), (ear_w * .40, ear_w * .22),
                           (ear_w * .06, ear_w * .05)],
                          [head_i], MAT_BODY, sides=10)
                mesh.tube([root + np.array((0., ear_h * .10, -ear_w * .12)),
                           mid + np.array((0., 0., -ear_w * .10))],
                          [(ear_w * .34, ear_w * .16), (ear_w * .20, ear_w * .10)],
                          [head_i], MAT_ACCENT, sides=8)
            elif ear == "long":  # hare
                tip = root + tilt * ear_h
                edge_a = [root + tilt * ear_h * t + np.array((-ear_w * .42, 0., 0.))
                          for t in np.linspace(0, 1, 6)]
                edge_b = [root + tilt * ear_h * t + np.array((ear_w * .42, 0., 0.))
                          for t in np.linspace(0, 1, 6)]
                for i, t in enumerate(np.linspace(0, 1, 6)):
                    pinch = math.sin(min(t, .95) * math.pi) * .55 + .45
                    centre = (edge_a[i] + edge_b[i]) * .5
                    edge_a[i] = centre + (edge_a[i] - centre) * pinch
                    edge_b[i] = centre + (edge_b[i] - centre) * pinch
                _sheet(mesh, edge_a, edge_b, ear_w * .16, [head_i], MAT_BODY)
            elif ear == "leaf":  # cervid
                axis = np.array((side * .82, .50, .28))
                axis /= np.linalg.norm(axis)
                tip = root + axis * ear_h
                edge_a, edge_b = [], []
                for t in np.linspace(0, 1, 5):
                    centre = root + axis * ear_h * t
                    width = ear_w * max(math.sin(min(t * .86 + .12, 1.) * math.pi), .18) * .9
                    edge_a.append(centre + np.array((0., 0., -width)))
                    edge_b.append(centre + np.array((0., 0., width)))
                _sheet(mesh, edge_a, edge_b, ear_w * .20, [head_i], MAT_BODY)
            else:  # round
                mesh.ellipsoid(tuple(root + tilt * ear_h * .55),
                               (ear_w * 1.05, ear_h * 1.05, ear_w * .42),
                               [head_i], MAT_BODY, rings=8, sides=12)

    _limbs_and_tail(mesh, p, s, g, B, spine, radii, archetype)

    # ---- archetype features --------------------------------------------
    _features(mesh, p, s, g, B, spine, radii, head_g, skull, muzzle_tip, m1)
    return mesh


def _limbs_and_tail(mesh, p, s, g, B, spine, radii, archetype):
    """Legs, feet, claws and tail chains shared by every body plan."""
    body_i, chest_i = B["body"], B["chest"]
    rump = tuple(v * s for v in p["rump"])
    claw_colour = MAT_DARK
    for prefix, root_bone in (("front", chest_i), ("rear", body_i)):
        for side in ("l", "r"):
            hip = g[B[f"{prefix}_leg_{side}"]]
            knee = g[B[f"{prefix}_shin_{side}"]]
            ankle = g[B[f"{prefix}_paw_{side}"]]
            leg_b = B[f"{prefix}_leg_{side}"]
            shin_b = B[f"{prefix}_shin_{side}"]
            paw_b = B[f"{prefix}_paw_{side}"]
            candidates = [root_bone, leg_b, shin_b, paw_b]
            upper, lower, ankle_r = (p["upper_r"] * s, p["lower_r"] * s, p["ankle_r"] * s)
            foot_len = p["foot_len"] * s
            foot_r = p["foot_r"] * s
            shoulder = hip + (np.array((0., 1., 0.)) * upper * .55)
            # The limb continues below the ankle so hooves and paws stay joined
            # to the leg instead of floating under a high hock.
            foot_top = np.array((ankle[0], foot_r * 1.05, ankle[2] - foot_len * .10))
            points = [shoulder,
                      hip * .70 + knee * .30,
                      knee,
                      knee * .35 + ankle * .65,
                      ankle,
                      ankle * .40 + foot_top * .60,
                      foot_top]
            widths = [(upper * 1.45, upper * 1.55), (upper * 1.10, upper * 1.20),
                      (lower * 1.05, lower * 1.15), (ankle_r * 1.05, ankle_r * 1.10),
                      (ankle_r, ankle_r), (ankle_r * .94, ankle_r * .94),
                      (ankle_r * .88, ankle_r * .92)]
            mesh.tube(points, widths, candidates, MAT_BODY, sides=12, uv_scale=1.4,
                      cap_start=False, cap_end=False)
            heel = np.array((ankle[0], foot_r * .78, ankle[2] + foot_len * .22))
            toe = np.array((ankle[0], foot_r * .62, ankle[2] - foot_len * .78))
            mesh.tube([heel, (heel + toe) * .5, toe],
                      [(foot_r * .90, foot_r * .80), (foot_r * 1.02, foot_r * .74),
                       (foot_r * .80, foot_r * .52)],
                      [paw_b, shin_b], MAT_BODY, sides=12)
            toes = int(p["toes"])
            if toes >= 3:
                for k in range(min(toes, 4)):
                    offset = (k - (min(toes, 4) - 1) * .5) * foot_r * .52
                    start = toe + np.array((offset, -foot_r * .10, 0.))
                    mesh.spike(start, start + np.array((offset * .18, -foot_r * .16,
                                                        -foot_len * .30)),
                               foot_r * .18, [paw_b], claw_colour, sides=7)
            else:  # cloven hoof
                for offset in (-foot_r * .34, foot_r * .34):
                    mesh.ellipsoid(tuple(toe + np.array((offset, -foot_r * .10, -foot_len * .06))),
                                   (foot_r * .70, foot_r * 1.05, foot_len * .52),
                                   [paw_b], claw_colour, rings=7, sides=10)

    # ---- tail(s) -------------------------------------------------------
    if p["tails"] and p["tail_len"] > 0:
        chain = [g[B["tail_1"]], g[B["tail_2"]], g[B["tail_3"]], g[B["tail_4"]]]
        tail_bones = [body_i, B["tail_1"], B["tail_2"], B["tail_3"], B["tail_4"]]
        for tail_index in range(int(p["tails"])):
            lateral = 0. if p["tails"] == 1 else (tail_index - .5) * p["tail_r"] * s * 2.6
            points, widths = [], []
            root = spine[1] + np.array((lateral, -rump[1] * .10, 0.))
            points.append(root)
            widths.append((p["tail_r"] * s * .95, p["tail_r"] * s * .95))
            for i, node in enumerate(chain):
                t = (i + 1) / len(chain)
                bush = 1.0 + (p["tail_bush"] - 1.0) * math.sin(min(t * 1.08, 1.) * math.pi) ** .65
                taper = 1.0 - (1.0 - p["tail_taper"]) * (t ** 1.35)
                r = p["tail_r"] * s * taper * bush
                points.append(node + np.array((lateral, 0., 0.)))
                widths.append((r, r))
            tip = points[-1] + (points[-1] - points[-2]) * .55
            points.append(tip)
            widths.append((p["tail_r"] * s * p["tail_taper"] * .5,) * 2)
            material = MAT_BODY if tail_index == 0 else MAT_ACCENT
            mesh.tube(points, widths, tail_bones, material, sides=14, uv_scale=1.6)
            if p["tail_bush"] > 1.4:  # brush tip highlight
                mesh.tube(points[-3:], [(w[0] * .92, w[1] * .92) for w in widths[-3:]],
                          tail_bones, MAT_ACCENT, sides=12)


def _anuran_head(mesh, p, s, g, B, spine, radii) -> None:
    """Toads have no neck: a wide, flat skull continues straight off the body."""
    head_i, jaw_i, neck_i = B["head"], B["jaw"], B["neck"]
    head_g = g[head_i]
    skull = tuple(v * s for v in p["skull"])
    # Shoulder-to-skull blend keeps the silhouette continuous.
    bridge = [spine[-1], (spine[-1] + head_g) * .5, head_g]
    mesh.tube(bridge,
              [(radii[-1][0] * .98, radii[-1][1] * .98),
               (skull[0] * .46, skull[1] * .52),
               (skull[0] * .44, skull[1] * .48)],
              [neck_i, head_i, B["chest"]], MAT_BODY, sides=16,
              cap_start=False, cap_end=False)
    mesh.ellipsoid(tuple(head_g), (skull[0] * 1.06, skull[1] * 1.10, skull[2] * 1.15),
                   [head_i, neck_i], MAT_BODY, rings=12, sides=20)
    # Wide mouth line, hinged on the jaw bone.
    jaw_g = g[jaw_i]
    mesh.ellipsoid(tuple(jaw_g + np.array((0., skull[1] * .10, -skull[2] * .16))),
                   (skull[0] * .96, skull[1] * .46, skull[2] * 1.02),
                   [jaw_i, head_i], MAT_ACCENT, rings=9, sides=18)
    # Bulging dorsal eyes with dark pupils.
    for side in (-1., 1.):
        socket = head_g + np.array((side * p["eye_spread"] * s,
                                    skull[1] * .46, -skull[2] * .16))
        mesh.ellipsoid(tuple(socket), (p["eye_r"] * s * 2.5,) * 3,
                       [head_i], MAT_BODY, rings=8, sides=14)
        mesh.ellipsoid(tuple(socket + np.array((side * p["eye_r"] * s * .5,
                                                p["eye_r"] * s * .55,
                                                -p["eye_r"] * s * .9))),
                       (p["eye_r"] * s * 1.7,) * 3, [head_i], MAT_DARK, rings=7, sides=12)
    nostril = head_g + np.array((0., skull[1] * .18, -skull[2] * .58))
    for side in (-1., 1.):
        mesh.ellipsoid(tuple(nostril + np.array((side * skull[0] * .16, 0., 0.))),
                       (p["eye_r"] * s * .7,) * 3, [head_i], MAT_DARK, rings=5, sides=8)


def _features(mesh: AnatomyMesh, p: dict, s: float, g, B, spine, radii,
              head_g, skull, muzzle_tip, m1) -> None:
    """Horns, shells, quills, dorsal scutes, armour plates and wings."""
    head_i, body_i, chest_i = B["head"], B["body"], B["chest"]

    horn = p["horn"]
    if horn == "antlers":
        for side in (-1., 1.):
            root = head_g + np.array((side * skull[0] * .50, skull[1] * .46, skull[2] * .12))
            # Main beam sweeps back over the shoulders and lifts, the way a
            # real stag carries antlers, instead of spiking straight up.
            beam = [root,
                    root + np.array((side * .13 * s, .22 * s, .12 * s)),
                    root + np.array((side * .26 * s, .40 * s, .30 * s)),
                    root + np.array((side * .34 * s, .54 * s, .50 * s))]
            mesh.tube(beam, [(.062 * s, .058 * s), (.052 * s, .048 * s),
                             (.040 * s, .037 * s), (.024 * s, .022 * s)],
                      [head_i], MAT_FEATURE, sides=10)
            # Brow tine forward over the eye.
            mesh.tube([root + np.array((side * .04 * s, .05 * s, -.02 * s)),
                       root + np.array((side * .10 * s, .17 * s, -.20 * s)),
                       root + np.array((side * .13 * s, .26 * s, -.30 * s))],
                      [(.034 * s, .032 * s), (.022 * s, .021 * s), (.007 * s, .007 * s)],
                      [head_i], MAT_FEATURE, sides=8)
            # Upright tines fanning off the beam.
            for k, along in enumerate((.32, .58, .84)):
                base = _bezier(beam, along)
                spread = .16 + .07 * k
                tip = base + np.array((side * spread * s, (.30 - .05 * k) * s,
                                       (-.10 + .09 * k) * s))
                mesh.tube([base, (base + tip) * .5, tip],
                          [(.034 * s, .032 * s), (.022 * s, .021 * s), (.007 * s, .007 * s)],
                          [head_i], MAT_FEATURE, sides=8)
    elif horn == "bovine":
        for side in (-1., 1.):
            root = head_g + np.array((side * skull[0] * .68, skull[1] * .28, skull[2] * .10))
            mesh.tube([root,
                       root + np.array((side * .22 * s, .06 * s, -.02 * s)),
                       root + np.array((side * .30 * s, .18 * s, -.14 * s)),
                       root + np.array((side * .26 * s, .28 * s, -.24 * s))],
                      [(.070 * s, .066 * s), (.050 * s, .048 * s),
                       (.032 * s, .030 * s), (.009 * s, .009 * s)],
                      [head_i], MAT_FEATURE, sides=10)
    elif horn == "curl":
        for side in (-1., 1.):
            root = head_g + np.array((side * skull[0] * .58, skull[1] * .34, skull[2] * .10))
            points, widths = [], []
            for k in range(11):
                t = k / 10
                # A full turn and a half sweeping back, down and forward again.
                angle = t * math.pi * 2.15
                radius = .28 * s * (1.0 - .34 * t)
                points.append(root + np.array((side * (.06 + .16 * t) * s,
                                               radius * math.sin(angle + .5) * .80 - .12 * s,
                                               radius * (1 - math.cos(angle + .5)) * .95 - .05 * s)))
                thickness = .088 * s * (1.0 - .62 * t)
                widths.append((thickness, thickness))
            mesh.tube(points, widths, [head_i], MAT_FEATURE, sides=12)
    elif horn == "tusks":
        for side in (-1., 1.):
            root = muzzle_tip + np.array((side * m1 * .78, -m1 * .10, m1 * .90))
            mesh.tube([root,
                       root + np.array((side * .03 * s, .09 * s, -.09 * s)),
                       root + np.array((side * .07 * s, .20 * s, -.13 * s))],
                      [(.032 * s, .032 * s), (.024 * s, .024 * s), (.008 * s, .008 * s)],
                      [head_i], MAT_FEATURE, sides=8)
    elif horn == "fangs":
        for side in (-1., 1.):
            root = muzzle_tip + np.array((side * m1 * .70, -m1 * .15, m1 * 1.05))
            mesh.tube([root,
                       root + np.array((side * .01 * s, -.13 * s, .01 * s)),
                       root + np.array((side * .02 * s, -.30 * s, .04 * s))],
                      [(.034 * s, .030 * s), (.026 * s, .023 * s), (.006 * s, .006 * s)],
                      [head_i], MAT_FEATURE, sides=9)
    elif horn == "nasal":
        base = muzzle_tip + np.array((0., m1 * .70, m1 * 1.4))
        mesh.tube([base, base + np.array((0., .18 * s, -.05 * s)),
                   base + np.array((0., .30 * s, -.12 * s))],
                  [(.075 * s, .070 * s), (.048 * s, .045 * s), (.010 * s, .010 * s)],
                  [head_i], MAT_FEATURE, sides=10)
        brow = head_g + np.array((0., skull[1] * .52, skull[2] * .18))
        mesh.tube([brow, brow + np.array((0., .13 * s, .02 * s))],
                  [(.055 * s, .050 * s), (.012 * s, .012 * s)],
                  [head_i], MAT_FEATURE, sides=9)

    if p.get("plated"):
        plated = float(p["plated"])
        seed = str(p.get("_variant", ""))
        plated_shell(mesh, spine, radii, [body_i, chest_i, B["neck"]], MAT_BODY,
                     seed=seed + ":back", rows=int(2 + 2 * plated), around=5,
                     relief=.38 * plated, gap=.11, dome=.60,
                     shape=p.get("plate_shape", "boulder"),
                     rune_material=MAT_CORE if p.get("runes") else None,
                     rune_chance=float(p.get("runes") or 0.) * .5,
                     span=(.08, .92))
        for key in ("front_leg_l", "front_leg_r", "rear_leg_l", "rear_leg_r"):
            if key not in B:
                continue
            shin = key.replace("_leg_", "_shin_")
            paw = key.replace("_leg_", "_paw_")
            if shin not in B or paw not in B:
                continue
            chain = [g[B[key]], (g[B[key]] + g[B[shin]]) * .5, g[B[shin]],
                     g[B[paw]]]
            thick = p["upper_r"] * s
            widths = [(thick * 1.05, thick * 1.05), (thick * .92, thick * .92),
                      (thick * .80, thick * .80), (thick * .66, thick * .66)]
            plated_shell(mesh, chain, widths,
                         [body_i, B[key], B[shin], B[paw]], MAT_BODY,
                         seed=f"{seed}:{key}", rows=3, around=4,
                         relief=.38 * plated, gap=.13, dome=.60,
                         shape=p.get("plate_shape", "boulder"),
                         span=(.10, .90))
    if p.get("core"):
        # A gem set over the shoulder, where the art puts it on these beasts.
        gem = float(p["core"]) * s
        seat = spine[max(len(spine) - 3, 0)] + np.array((0., radii[-1][1] * .55, 0.))
        mesh.ellipsoid(tuple(seat), (gem * .30, gem * .26, gem * .30),
                       [chest_i, B["neck"]], MAT_CORE, rings=7, sides=11)
        for k in range(9):
            angle = 2 * math.pi * k / 9
            mesh.ellipsoid(tuple(seat + np.array((math.cos(angle) * gem * .24,
                                                  -gem * .04,
                                                  math.sin(angle) * gem * .24))),
                           (gem * .075,) * 3, [chest_i, B["neck"]],
                           MAT_FEATURE, rings=4, sides=6)
    ruff = float(p.get("mane_ruff") or 0.0)
    if ruff:
        # One smooth ellipsoid reads as a scarf.  A mane is a mass of hanging
        # locks, and its outline is what separates a lion from a big cat and a
        # dire wolf from a dog at any distance worth modelling for.
        collar = g[B["neck"]]
        span = p["neck_r"][0] * s
        mesh.ellipsoid(tuple(collar + np.array((0., 0., .04 * s))),
                       (span * 2.6 * ruff, p["neck_r"][1] * s * 2.5 * ruff,
                        span * 1.9 * ruff),
                       [B["neck"], chest_i], MAT_ACCENT, rings=9, sides=16)
        rng = np.random.default_rng(
            zlib.crc32(("mane:" + str(p.get("_variant", ""))).encode("utf-8"))
            % (2 ** 31))
        locks = int(11 + 7 * min(ruff, 2.0))
        for k in range(locks):
            angle = 2 * math.pi * k / locks + float(rng.uniform(-.12, .12))
            out = np.array((math.cos(angle), math.sin(angle) * .82, 0.))
            root = collar + np.array((out[0] * span * 1.5 * ruff,
                                       out[1] * span * 1.5 * ruff, .02 * s))
            # Locks lie along the mass and hang; radiating them straight out
            # made a sunburst collar rather than a head of fur.
            reach = span * ruff * float(rng.uniform(.62, 1.05))
            tip = root + np.array((out[0] * reach * .34,
                                   out[1] * reach * .22 - reach * .74,
                                   reach * float(rng.uniform(.10, .52))))
            mesh.tube([root, (root + tip) * .5, tip],
                      [(span * .26 * ruff, span * .26 * ruff),
                       (span * .20 * ruff, span * .20 * ruff),
                       (span * .08 * ruff, span * .08 * ruff)],
                      [B["neck"], chest_i], MAT_ACCENT, sides=5)

    if p["shell"]:
        top = max(pt[1] + r[1] for pt, r in zip(spine, radii))
        centre = (spine[2] + spine[4]) * .5
        span = abs(spine[0][2] - spine[-1][2])
        mesh.ellipsoid((0., centre[1] + .10 * s, centre[2]),
                       (max(r[0] for r in radii) * 2.15, (top - centre[1]) * 2.05, span * .90),
                       [body_i, chest_i], MAT_FEATURE, rings=12, sides=22)
        mesh.ellipsoid((0., centre[1] - .12 * s, centre[2]),
                       (max(r[0] for r in radii) * 1.85, .14 * s, span * .72),
                       [body_i, chest_i], MAT_ACCENT, rings=8, sides=18)

    if p["spines"]:
        length, count = p["spines"]
        for k in range(count):
            t = .10 + .78 * (k % (count // 2)) / max(count // 2 - 1, 1)
            lateral = (-1. if k < count // 2 else 1.) * .30
            index = min(int(t * (len(spine) - 1)), len(spine) - 2)
            point = spine[index]
            r = radii[index]
            base = np.array((lateral * r[0] * 1.3, point[1] + r[1] * .78, point[2]))
            direction = np.array((lateral * .55, 1., .18))
            direction /= np.linalg.norm(direction)
            mesh.spike(base, base + direction * length * s, .020 * s,
                       [body_i, chest_i], MAT_FEATURE, sides=6)

    if p["dorsal"]:
        height, count = p["dorsal"]
        for k in range(count):
            t = k / (count - 1)
            index = min(int(t * (len(spine) - 1)), len(spine) - 1)
            point = spine[index]
            r = radii[index]
            fade = math.sin(min(t + .10, 1.) * math.pi) * .85 + .25
            base = np.array((0., point[1] + r[1] * .86, point[2]))
            mesh.spike(base, base + np.array((0., height * s * fade, .02 * s)),
                       .030 * s * fade, [body_i, chest_i], MAT_FEATURE, sides=6)

    if p["plates"]:
        for t, width in ((.30, 1.16), (.74, 1.20)):
            index = min(int(t * (len(spine) - 1)), len(spine) - 1)
            point = spine[index]
            r = radii[index]
            mesh.ellipsoid((0., point[1] + r[1] * .18, point[2]),
                           (r[0] * 2 * width, r[1] * 1.55, r[1] * 1.25),
                           [body_i, chest_i], MAT_FEATURE, rings=8, sides=16)

    if p["wings"]:
        for side in (-1., 1.):
            shoulder = g[B[f"wing_{'l' if side < 0 else 'r'}"]]
            wing_bone = B[f"wing_{'l' if side < 0 else 'r'}"]
            elbow = shoulder + np.array((side * .40 * s, .26 * s, .10 * s))
            wrist = elbow + np.array((side * .46 * s, .10 * s, .04 * s))
            mesh.tube([shoulder, elbow, wrist],
                      [(.055 * s, .055 * s), (.040 * s, .040 * s), (.028 * s, .028 * s)],
                      [wing_bone, chest_i], MAT_BODY, sides=9)
            # Three digits carrying the membrane, folded slightly back.
            tips = [wrist + np.array((side * .30 * s, .04 * s, .40 * s)),
                    wrist + np.array((side * .46 * s, -.06 * s, .18 * s)),
                    wrist + np.array((side * .40 * s, -.18 * s, -.06 * s))]
            for tip in tips:
                mesh.tube([wrist, (wrist + tip) * .5, tip],
                          [(.024 * s, .024 * s), (.017 * s, .017 * s), (.008 * s, .008 * s)],
                          [wing_bone], MAT_BODY, sides=7)
            anchor = shoulder + np.array((side * .05 * s, -.16 * s, .30 * s))
            leading = [shoulder, elbow, wrist, tips[1]]
            trailing = [anchor, anchor + (elbow - shoulder) * .55 + np.array((0., -.04 * s, .22 * s)),
                        tips[0], tips[0]]
            samples = 8
            edge_a, edge_b = [], []
            for i in range(samples):
                t = i / (samples - 1)
                edge_a.append(_bezier(leading, t))
                edge_b.append(_bezier(trailing, t))
            _sheet(mesh, edge_a, edge_b, .016 * s, [wing_bone, chest_i], MAT_ACCENT)


def _bezier(points, t: float) -> np.ndarray:
    pts = [np.asarray(v, dtype=float) for v in points]
    while len(pts) > 1:
        pts = [pts[i] * (1 - t) + pts[i + 1] * t for i in range(len(pts) - 1)]
    return pts[0]


# ---------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------
# Clip names are the runtime contract from godot-client/data/animations/
# creature.json; they must not drift without updating that map.
REQUIRED_CLIPS = ("Idle_A", "Walk", "Jog", "Fighting_Idle",
                  "Sword_Attack", "Hit_Chest", "Death_A")
LOOPING_CLIPS = {"Idle_A", "Walk", "Jog", "Fighting_Idle"}

GAITS = {"canid": "walk", "felid": "walk", "ursine": "walk", "suid": "walk",
         "cervid": "walk", "mustelid": "walk", "drake": "sprawl",
         "sprawler": "sprawl", "chelonian": "sprawl",
         "lagomorph": "hop", "anuran": "hop"}


def qaxis(axis, angle: float) -> list[float]:
    v = np.asarray(axis, dtype=float)
    v = v / max(np.linalg.norm(v), 1e-9)
    half = angle * .5
    return [float(v[0] * math.sin(half)), float(v[1] * math.sin(half)),
            float(v[2] * math.sin(half)), float(math.cos(half))]


def qmul(a, b) -> list[float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def _euler(pitch=0., yaw=0., roll=0.) -> list[float]:
    q = qaxis((1., 0., 0.), pitch)
    if yaw:
        q = qmul(qaxis((0., 1., 0.), yaw), q)
    if roll:
        q = qmul(qaxis((0., 0., 1.), roll), q)
    return q


LEG_KEYS = ("front_l", "front_r", "rear_l", "rear_r")
WALK_PHASE = {"front_l": .00, "rear_r": .25, "front_r": .50, "rear_l": .75}
TROT_PHASE = {"front_l": .00, "rear_r": .00, "front_r": .50, "rear_l": .50}
HOP_PHASE = {"front_l": .00, "front_r": .00, "rear_l": .50, "rear_r": .50}


def _leg_bones(B, key):
    prefix, side = key.split("_")
    return (B[f"{prefix}_leg_{side}"], B[f"{prefix}_shin_{side}"], B[f"{prefix}_paw_{side}"])


def _locomotion(B, gait: str, phases: dict, swing: float, lift: float,
                bob: float, samples: int, duration: float, plan: dict):
    """Bake a full-body gait: hips, knees, feet, spine, neck, head and tail."""
    tracks: dict[int, dict[str, list]] = {}

    def key(node, path, time, value):
        entry = tracks.setdefault(node, {})
        times, values = entry.setdefault(path, ([], []))
        times.append(time)
        values.append(value)

    for step in range(samples + 1):
        u = step / samples
        time = u * duration
        for leg in LEG_KEYS:
            hip_b, shin_b, paw_b = _leg_bones(B, leg)
            phase = (u - phases[leg]) % 1.0
            cycle = 2 * math.pi * phase
            front = leg.startswith("front")
            if gait == "hop":
                # Both limb pairs fold and extend together.
                drive = math.sin(cycle)
                hip = swing * drive * (.75 if front else 1.15)
                flex = lift * (.55 + .45 * math.cos(cycle))
            else:
                hip = swing * math.sin(cycle)
                # Knee flexes through the swing half of the stride only.
                flex = lift * max(0., math.sin(cycle + math.pi * .35))
            shin = -flex if front else flex
            key(hip_b, "rotation", time, _euler(pitch=hip))
            key(shin_b, "rotation", time, _euler(pitch=shin))
            key(paw_b, "rotation", time, _euler(pitch=-hip * .35 - shin * .55))

        beats = 2.0 if gait != "hop" else 1.0
        key(B["root"], "translation", time,
            [0., bob * math.sin(2 * math.pi * beats * u + math.pi * .25), 0.])
        key(B["body"], "rotation", time,
            _euler(pitch=bob * 1.4 * math.sin(2 * math.pi * beats * u),
                   roll=bob * 2.2 * math.sin(2 * math.pi * u)))
        key(B["chest"], "rotation", time,
            _euler(pitch=-bob * 1.1 * math.sin(2 * math.pi * beats * u + .6),
                   roll=-bob * 1.6 * math.sin(2 * math.pi * u)))
        key(B["neck"], "rotation", time,
            _euler(pitch=bob * .9 * math.sin(2 * math.pi * beats * u + 1.1),
                   yaw=bob * 1.3 * math.sin(2 * math.pi * u + .4)))
        key(B["head"], "rotation", time,
            _euler(pitch=-bob * .7 * math.sin(2 * math.pi * beats * u + 1.5)))
        for index, bone in enumerate(("tail_1", "tail_2", "tail_3", "tail_4")):
            lag = .16 * index
            key(B[bone], "rotation", time,
                _euler(yaw=(.10 + .05 * index) * math.sin(2 * math.pi * (u - lag)),
                       pitch=(.05 + .02 * index) * math.sin(4 * math.pi * (u - lag))))
    return tracks


def _finalise(tracks) -> dict[int, tuple[str, list[float], list[list[float]]]]:
    out = {}
    for node, paths in tracks.items():
        for path, (times, values) in paths.items():
            out[(node, path)] = (path, times, values)
    return out


def animation_set(archetype: str, scale: float, bones,
                  variant: str | None = None) -> dict:
    """Return {clip_name: {(node, path): (path, times, values)}} for a creature."""
    plan = resolved_plan(archetype, variant)
    family = archetype if archetype in BODY_PLANS else ARCHETYPE_PLANS.get(archetype, "canid")
    gait = GAITS.get(family, "walk")
    B = BONE_INDEX
    clips: dict[str, dict] = {}

    # ---- Idle: breathing, weight shift, tail and ear life ---------------
    idle = {}

    def ikey(node, path, times, values):
        idle[(node, path)] = (path, times, values)

    samples = 16
    times = [2.4 * i / samples for i in range(samples + 1)]
    breath = [math.sin(2 * math.pi * i / samples) for i in range(samples + 1)]
    ikey(B["root"], "translation", times,
         [[0., .006 * scale * b, 0.] for b in breath])
    ikey(B["chest"], "rotation", times, [_euler(pitch=.022 * b) for b in breath])
    ikey(B["body"], "rotation", times, [_euler(roll=.016 * math.sin(math.pi * i / samples * 2 + .8))
                                        for i in range(samples + 1)])
    ikey(B["neck"], "rotation", times,
         [_euler(pitch=-.030 * b, yaw=.055 * math.sin(math.pi * i / samples))
          for i, b in enumerate(breath)])
    ikey(B["head"], "rotation", times,
         [_euler(pitch=.024 * b, yaw=-.070 * math.sin(math.pi * i / samples))
          for i, b in enumerate(breath)])
    for index, bone in enumerate(("tail_1", "tail_2", "tail_3", "tail_4")):
        ikey(B[bone], "rotation", times,
             [_euler(yaw=(.09 + .045 * index) * math.sin(2 * math.pi * (i / samples) - .22 * index))
              for i in range(samples + 1)])
    clips["Idle_A"] = idle

    # ---- Locomotion ------------------------------------------------------
    swing = {"walk": .40, "sprawl": .30, "hop": .46}[gait]
    lift = {"walk": .52, "sprawl": .34, "hop": .70}[gait]
    bob = {"walk": .020, "sprawl": .010, "hop": .045}[gait] * (1.0 if gait != "hop" else 1.0)
    phases = {"walk": WALK_PHASE, "sprawl": WALK_PHASE, "hop": HOP_PHASE}[gait]
    clips["Walk"] = _finalise(_locomotion(B, gait, phases, swing, lift, bob, 16, 1.0, plan))
    run_phases = {"walk": TROT_PHASE, "sprawl": TROT_PHASE, "hop": HOP_PHASE}[gait]
    clips["Jog"] = _finalise(_locomotion(B, gait, run_phases, swing * 1.55, lift * 1.45,
                                         bob * 1.9, 14, .62, plan))

    # ---- Combat idle: lowered, weaving, weight on the forehand ----------
    fight = {}
    samples = 14
    times = [1.4 * i / samples for i in range(samples + 1)]
    wave = [math.sin(2 * math.pi * i / samples) for i in range(samples + 1)]
    fight[(B["root"], "translation")] = ("translation", times,
                                         [[0., -.030 * scale + .008 * scale * w, 0.] for w in wave])
    fight[(B["body"], "rotation")] = ("rotation", times, [_euler(pitch=.055, roll=.035 * w) for w in wave])
    fight[(B["chest"], "rotation")] = ("rotation", times, [_euler(pitch=-.075, roll=-.045 * w) for w in wave])
    fight[(B["neck"], "rotation")] = ("rotation", times, [_euler(pitch=-.16, yaw=.13 * w) for w in wave])
    fight[(B["head"], "rotation")] = ("rotation", times, [_euler(pitch=.11, yaw=-.16 * w) for w in wave])
    fight[(B["jaw"], "rotation")] = ("rotation", times, [_euler(pitch=.10 + .05 * abs(w)) for w in wave])
    for index, bone in enumerate(("tail_1", "tail_2", "tail_3", "tail_4")):
        fight[(B[bone], "rotation")] = ("rotation", times,
                                        [_euler(yaw=(.16 + .07 * index) * math.sin(2 * math.pi * (i / samples) - .3 * index))
                                         for i in range(samples + 1)])
    for leg in LEG_KEYS:
        hip_b, shin_b, _ = _leg_bones(B, leg)
        crouch = .16 if leg.startswith("rear") else .10
        fight[(hip_b, "rotation")] = ("rotation", times, [_euler(pitch=crouch * (1 + .12 * w)) for w in wave])
        fight[(shin_b, "rotation")] = ("rotation", times,
                                       [_euler(pitch=(-.22 if leg.startswith("front") else .24) * (1 + .10 * w))
                                        for w in wave])
    clips["Fighting_Idle"] = fight

    # ---- Primary attack: coil, lunge, bite, recover ---------------------
    # Contact lands at ~55% so server-side impact timing stays readable.
    stamp = [0., .16, .30, .42, .55, .68, .86]
    attack = {
        (B["root"], "translation"): ("translation", stamp,
                                     [[0., 0., 0.], [0., -.035 * scale, 0.],
                                      [0., .020 * scale, 0.], [0., .030 * scale, 0.],
                                      [0., .010 * scale, 0.], [0., -.010 * scale, 0.],
                                      [0., 0., 0.]]),
        (B["body"], "rotation"): ("rotation", stamp,
                                  [_euler(), _euler(pitch=.24), _euler(pitch=-.17),
                                   _euler(pitch=-.27), _euler(pitch=-.13), _euler(pitch=.07), _euler()]),
        (B["chest"], "rotation"): ("rotation", stamp,
                                   [_euler(), _euler(pitch=.16), _euler(pitch=-.26),
                                    _euler(pitch=-.38), _euler(pitch=-.16), _euler(pitch=.09), _euler()]),
        (B["neck"], "rotation"): ("rotation", stamp,
                                  [_euler(), _euler(pitch=.22), _euler(pitch=-.30),
                                   _euler(pitch=-.44), _euler(pitch=-.16), _euler(pitch=.10), _euler()]),
        (B["head"], "rotation"): ("rotation", stamp,
                                  [_euler(), _euler(pitch=.16), _euler(pitch=-.22),
                                   _euler(pitch=-.30), _euler(pitch=.06), _euler(pitch=.08), _euler()]),
        (B["jaw"], "rotation"): ("rotation", stamp,
                                 [_euler(), _euler(pitch=.18), _euler(pitch=.62),
                                  _euler(pitch=.70), _euler(pitch=.02), _euler(pitch=.06), _euler()]),
    }
    for leg in LEG_KEYS:
        hip_b, shin_b, _ = _leg_bones(B, leg)
        rear = leg.startswith("rear")
        drive = [0., .30 if rear else .14, -.24 if rear else -.30,
                 -.34 if rear else -.40, -.12, .08, 0.]
        attack[(hip_b, "rotation")] = ("rotation", stamp, [_euler(pitch=v) for v in drive])
        attack[(shin_b, "rotation")] = ("rotation", stamp,
                                        [_euler(pitch=(.9 if rear else -.9) * abs(v) * .6) for v in drive])
    for index, bone in enumerate(("tail_1", "tail_2", "tail_3", "tail_4")):
        attack[(B[bone], "rotation")] = ("rotation", stamp,
                                         [_euler(pitch=-(.10 + .05 * index) * v)
                                          for v in (0., .8, -.6, -1.0, -.4, .3, 0.)])
    clips["Sword_Attack"] = attack

    # ---- Hit reaction ----------------------------------------------------
    hit_t = [0., .09, .20, .34, .48]
    clips["Hit_Chest"] = {
        (B["root"], "translation"): ("translation", hit_t,
                                     [[0., 0., 0.], [0., -.022 * scale, 0.],
                                      [0., -.012 * scale, 0.], [0., -.004 * scale, 0.], [0., 0., 0.]]),
        (B["body"], "rotation"): ("rotation", hit_t,
                                  [_euler(), _euler(pitch=-.20, roll=.16), _euler(pitch=-.12, roll=.10),
                                   _euler(pitch=.04, roll=-.03), _euler()]),
        (B["chest"], "rotation"): ("rotation", hit_t,
                                   [_euler(), _euler(pitch=.26, roll=-.14), _euler(pitch=.16, roll=-.08),
                                    _euler(pitch=-.05), _euler()]),
        (B["neck"], "rotation"): ("rotation", hit_t,
                                  [_euler(), _euler(pitch=.34, yaw=.20), _euler(pitch=.20, yaw=.12),
                                   _euler(pitch=-.06), _euler()]),
        (B["head"], "rotation"): ("rotation", hit_t,
                                  [_euler(), _euler(pitch=.30, yaw=.24), _euler(pitch=.18, yaw=.14),
                                   _euler(pitch=-.04), _euler()]),
        (B["jaw"], "rotation"): ("rotation", hit_t,
                                 [_euler(), _euler(pitch=.44), _euler(pitch=.30), _euler(pitch=.08), _euler()]),
    }

    # ---- Death: buckle, topple onto the flank, settle on the ground -----
    # Roll about the *body* bone rather than the root: rotating the root would
    # pivot the whole creature about the ground point and bury it.  The root
    # only drops by the distance from the hip to the flank so the carcass ends
    # resting on the surface instead of sinking through it.
    death_t = [0., .22, .46, .74, 1.02, 1.30]
    # Tall-bodied creatures topple fully onto the flank; already-low sprawlers,
    # toads and shelled creatures only slump, which is how they actually fall.
    roll = .62 if family in ("sprawler", "anuran", "chelonian", "mustelid") else 1.42
    drop = -max(plan["hip_h"] - plan["rump"][0], .02) * scale
    clips["Death_A"] = {
        (B["root"], "translation"): ("translation", death_t,
                                     [[0., 0., 0.], [0., drop * .18, 0.], [0., drop * .48, 0.],
                                      [0., drop * .86, 0.], [0., drop, 0.], [0., drop, 0.]]),
        (B["body"], "rotation"): ("rotation", death_t,
                                  [_euler(), _euler(pitch=.12, roll=.16),
                                   _euler(pitch=.16, roll=.58), _euler(pitch=.12, roll=1.10),
                                   _euler(pitch=.08, roll=roll), _euler(pitch=.07, roll=roll)]),
        (B["chest"], "rotation"): ("rotation", death_t,
                                   [_euler(), _euler(pitch=-.10), _euler(pitch=.10, roll=.10),
                                    _euler(pitch=.18, roll=.06), _euler(pitch=.20), _euler(pitch=.20)]),
        (B["neck"], "rotation"): ("rotation", death_t,
                                  [_euler(), _euler(pitch=-.18), _euler(pitch=.26), _euler(pitch=.46),
                                   _euler(pitch=.54), _euler(pitch=.55)]),
        (B["head"], "rotation"): ("rotation", death_t,
                                  [_euler(), _euler(pitch=-.10), _euler(pitch=.22), _euler(pitch=.40),
                                   _euler(pitch=.46), _euler(pitch=.47)]),
        (B["jaw"], "rotation"): ("rotation", death_t,
                                 [_euler(), _euler(pitch=.20), _euler(pitch=.34), _euler(pitch=.30),
                                  _euler(pitch=.26), _euler(pitch=.25)]),
    }
    for leg in LEG_KEYS:
        hip_b, shin_b, _ = _leg_bones(B, leg)
        rear = leg.startswith("rear")
        curl = [0., .20, .56, .80, .94, .96]
        clips["Death_A"][(hip_b, "rotation")] = ("rotation", death_t,
                                                 [_euler(pitch=v * (1.0 if rear else .82)) for v in curl])
        clips["Death_A"][(shin_b, "rotation")] = ("rotation", death_t,
                                                  [_euler(pitch=(1.15 if rear else -1.15) * v) for v in curl])
    for index, bone in enumerate(("tail_1", "tail_2", "tail_3", "tail_4")):
        clips["Death_A"][(B[bone], "rotation")] = ("rotation", death_t,
                                                   [_euler(yaw=(.12 + .06 * index) * v)
                                                    for v in (0., .5, .9, .6, .2, .15)])
    return clips


# ---------------------------------------------------------------------------
# Procedural surface textures
# ---------------------------------------------------------------------------
# Luminance-only maps multiply the material base colour, which keeps palettes
# authored in one place and keeps the embedded PNGs small.
SURFACE_KINDS = {
    "fox": "fur", "two_tail_fox": "fur", "wolf": "fur", "cat": "fur",
    "bear": "fur", "hare": "fur", "otter": "fur", "rat": "fur",
    "porcupine": "fur", "elk": "fur", "ram": "fleece", "boar": "bristle",
    "rhino": "hide", "lizard": "scale", "crocodile": "scale", "drake": "scale",
    "toad": "warty", "tortoise": "scute",
}
MARKINGS = {"cat": "stripes"}


def _value_noise(rng, size: int, cells: int) -> np.ndarray:
    """Smooth periodic value noise via bilinear upsampling of a coarse grid."""
    grid = rng.random((cells + 1, cells + 1))
    grid[-1, :] = grid[0, :]
    grid[:, -1] = grid[:, 0]
    ys = np.linspace(0, cells, size, endpoint=False)
    xs = np.linspace(0, cells, size, endpoint=False)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    sy = fy * fy * (3 - 2 * fy)
    sx = fx * fx * (3 - 2 * fx)
    g00 = grid[np.ix_(y0, x0)]
    g10 = grid[np.ix_(y0 + 1, x0)]
    g01 = grid[np.ix_(y0, x0 + 1)]
    g11 = grid[np.ix_(y0 + 1, x0 + 1)]
    return (g00 * (1 - sy) * (1 - sx) + g10 * sy * (1 - sx)
            + g01 * (1 - sy) * sx + g11 * sy * sx)


def surface_texture(archetype: str, size: int = 256, seed: int = 0) -> bytes:
    """Return a tiling luminance PNG describing the creature's surface."""
    from PIL import Image
    import io

    kind = SURFACE_KINDS.get(archetype, "fur")
    # zlib.crc32 rather than hash(): the built-in is salted per process, which
    # would make every rebuild produce different textures.
    rng = np.random.default_rng(
        zlib.crc32(f"{archetype}:{seed}".encode("utf-8")) % (2 ** 31))
    field = np.zeros((size, size))
    for octave, weight in ((4, .48), (8, .26), (16, .16), (32, .10)):
        field += _value_noise(rng, size, octave) * weight
    field = (field - field.min()) / max(float(np.ptp(field)), 1e-6)

    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    u = np.linspace(0, 1, size, endpoint=False)[None, :]

    if kind in ("fur", "bristle", "fleece"):
        strands = _value_noise(rng, size, 96 if kind == "bristle" else 64)
        streak = np.roll(strands, 0, axis=0)
        # Stretch the noise along V so it reads as lie-of-fur, not static.
        streak = (streak + np.roll(streak, 1, 0) + np.roll(streak, 2, 0)
                  + np.roll(streak, 3, 0)) * .25
        detail = .58 + .30 * field + .22 * streak
        if kind == "fleece":
            curl = .5 + .5 * np.sin(u * math.pi * 26 + field * 7.0)
            detail = .60 + .24 * field + .20 * curl
        if kind == "bristle":
            detail = .55 + .26 * field + .30 * (streak ** 1.6)
    elif kind == "scale":
        rows, cols = 26, 20
        yy = v * rows
        xx = u * cols + (np.floor(yy) % 2) * .5
        cell = np.sqrt(((xx % 1) - .5) ** 2 * 1.15 + ((yy % 1) - .5) ** 2)
        scale = np.clip(1.0 - cell * 2.05, 0, 1) ** .55
        detail = .52 + .34 * scale + .18 * field
    elif kind == "scute":
        rows, cols = 7, 9
        yy = v * rows
        xx = u * cols
        edge = np.minimum(np.minimum(xx % 1, 1 - xx % 1), np.minimum(yy % 1, 1 - yy % 1))
        plate = np.clip(edge * 6.5, 0, 1)
        detail = .42 + .46 * plate + .18 * field
    elif kind == "warty":
        bumps = _value_noise(rng, size, 30)
        warts = np.clip((bumps - .58) * 5.2, 0, 1) ** .7
        detail = .62 + .22 * field + .30 * warts
    else:  # hide
        cracks = _value_noise(rng, size, 22)
        seam = np.clip(1.0 - np.abs(cracks - .5) * 7.0, 0, 1)
        detail = .68 + .22 * field - .26 * seam

    if MARKINGS.get(archetype) == "stripes":
        bands = .5 + .5 * np.sin(v * math.pi * 13 + field * 9.5)
        detail = detail * (1.0 - .22 * np.clip((bands - .62) * 2.4, 0, 1))

    detail = np.clip(detail, .12, 1.0)
    image = Image.fromarray((detail * 255).astype(np.uint8), mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def keratin_texture(size: int = 128, seed: int = 3) -> bytes:
    """Ridged luminance map for horn, antler, hoof, quill and shell rims."""
    from PIL import Image
    import io

    rng = np.random.default_rng(seed)
    v = np.linspace(0, 1, size, endpoint=False)[:, None]
    grain = _value_noise(rng, size, 18)
    rings = .5 + .5 * np.sin(v * math.pi * 34 + grain * 3.2)
    detail = np.clip(.66 + .24 * rings + .18 * grain, .15, 1.0)
    detail = np.repeat(detail, size // detail.shape[1], axis=1)[:, :size] \
        if detail.shape[1] != size else detail
    image = Image.fromarray((detail * 255).astype(np.uint8), mode="L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Ground clamping
# ---------------------------------------------------------------------------
def _quat_to_matrix(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _clip_sample(clip, time):
    pose: dict[int, dict[str, list]] = {}
    for (node, _), (path, times, values) in clip.items():
        times = list(times)
        index = 0
        while index + 1 < len(times) and times[index + 1] <= time:
            index += 1
        nxt = min(index + 1, len(values) - 1)
        span = max(times[nxt] - times[index], 1e-9)
        frac = min(max((time - times[index]) / span, 0.), 1.) if nxt != index else 0.
        a = np.asarray(values[index], dtype=float)
        b = np.asarray(values[nxt], dtype=float)
        if path == "rotation":
            if float(np.dot(a, b)) < 0:
                b = -b
            value = a * (1 - frac) + b * frac
            value = value / max(np.linalg.norm(value), 1e-9)
        else:
            value = a * (1 - frac) + b * frac
        pose.setdefault(node, {})[path] = value.tolist()
    return pose


def _pose_lowest(bones, arrays, clip, time: float) -> float:
    return clip_lowest_point(bones, arrays, clip, samples=0, at=time)


def clip_lowest_point(bones, arrays, clip, samples: int = 14, at=None) -> float:
    """Lowest skinned vertex reached anywhere in ``clip`` (bind pose = y 0)."""
    children: dict[int, list[int]] = {i: [] for i in range(len(bones))}
    for index, (_, parent, _) in enumerate(bones):
        if parent >= 0:
            children[parent].append(index)
    rest = global_positions(bones)
    duration = max((max(times) for (_, times, _) in clip.values()), default=0.)
    positions = [a[0] for a in arrays if len(a[0])]
    joints = [a[4] for a in arrays if len(a[0])]
    weights = [a[5] for a in arrays if len(a[0])]
    if not positions:
        return 0.0
    lowest = float("inf")
    if at is not None:
        stamps = [at]
    else:
        # Sample the uniform grid *and* every keyframe time: a clip's lowest
        # pose is usually exactly on a key, which a coarse grid can step over.
        stamps = {duration * step / max(samples, 1) for step in range(samples + 1)}
        for _, times, _ in clip.values():
            stamps.update(float(t) for t in times)
        stamps = sorted(stamps)
    for time in stamps:
        pose = _clip_sample(clip, time)
        world = [np.eye(4) for _ in bones]

        def walk(index: int, parent: np.ndarray) -> None:
            local = np.eye(4)
            override = pose.get(index, {})
            rotation = override.get("rotation")
            if rotation is not None:
                local[:3, :3] = _quat_to_matrix(rotation)
            translation = override.get("translation", bones[index][2])
            local[:3, 3] = np.asarray(translation, dtype=float)
            current = parent @ local
            world[index] = current
            for child in children[index]:
                walk(child, current)

        walk(0, np.eye(4))
        matrices = np.stack([world[i] @ np.array([[1., 0, 0, -rest[i][0]],
                                                  [0, 1., 0, -rest[i][1]],
                                                  [0, 0, 1., -rest[i][2]],
                                                  [0, 0, 0, 1.]])
                             for i in range(len(bones))])
        for verts, jnt, wgt in zip(positions, joints, weights):
            homogeneous = np.concatenate([verts.astype(float),
                                          np.ones((len(verts), 1))], axis=1)
            skinned = np.zeros((len(verts), 3))
            for slot in range(jnt.shape[1]):
                weight = wgt[:, slot:slot + 1].astype(float)
                if not weight.any():
                    continue
                picked = matrices[np.clip(jnt[:, slot].astype(int), 0, len(matrices) - 1)]
                skinned += weight * np.einsum("nij,nj->ni", picked, homogeneous)[:, :3]
            lowest = min(lowest, float(skinned[:, 1].min()))
    return 0.0 if lowest == float("inf") else lowest


def settle_final_pose(clips: dict, bones, arrays, name: str = "Death_A",
                      margin: float = .004) -> dict:
    """Lower a one-shot clip's held final pose until the body rests on y = 0.

    Ground clamping only ever lifts, which can leave a corpse hovering.  This
    lowers the terminal hold by however far it floats, then verifies the rest
    of the clip still clears the floor.
    """
    clip = clips.get(name)
    root = BONE_INDEX["root"]
    key = (root, "translation")
    if not clip or key not in clip:
        return clips
    path, times, values = clip[key]
    duration = max((max(t) for (_, t, _) in clip.values()), default=0.)
    floating = _pose_lowest(bones, arrays, clip, duration)
    if floating <= margin:
        return clips
    held = [i for i, t in enumerate(times) if t >= duration - 1e-6] or [len(values) - 1]
    lowered = [list(v) for v in values]
    for index in held:
        lowered[index][1] -= floating
    clip[key] = (path, times, lowered)
    deficit = clip_lowest_point(bones, arrays, clip)
    if deficit < -margin:
        for index in held:
            lowered[index][1] += -deficit
        clip[key] = (path, times, lowered)
    return clips


def ground_clamp(clips: dict, bones, arrays, margin: float = .004) -> dict:
    """Lift each clip vertically so no pose drives the mesh through the floor.

    Without an IK solver a swinging limb inevitably dips below the ground, and
    a crouch lowers the whole body.  A per-clip vertical offset on the root is
    the cheapest honest fix: it never introduces horizontal travel, so in-place
    locomotion stays in place.
    """
    root = BONE_INDEX["root"]
    for name, clip in clips.items():
        # Iterate: lifting the root can expose a different lowest pose, because
        # rotation-driven parts do not move rigidly with the offset.
        for _ in range(4):
            lowest = clip_lowest_point(bones, arrays, clip)
            if lowest >= -margin:
                break
            lift = -lowest
            key = (root, "translation")
            if key in clip:
                path, times, values = clip[key]
                clip[key] = (path, times, [[v[0], v[1] + lift, v[2]] for v in values])
            else:
                duration = max((max(t) for (_, t, _) in clip.values()), default=1.)
                clip[key] = ("translation", [0., duration],
                             [[0., lift, 0.], [0., lift, 0.]])
    return clips


# ---------------------------------------------------------------------------
# Surface growth
# ---------------------------------------------------------------------------
# The concept art almost never shows a clean animal: creatures carry moss,
# crystal, barnacles, thorns, quills, plates, fungus, vines and leaves, and
# that growth is most of what breaks up their silhouette.  A smooth swept tube
# reads as a balloon animal no matter how good its proportions are, so every
# creature the art shows encrusted gets real geometry scattered over it.
# Mineral growth erupts along the surface normal in every direction; the rest
# settles on whatever faces the sky.
SPIKY_GROWTH = frozenset(("crystal", "rime", "spine", "coral"))

GROWTH_KINDS = ("moss", "crystal", "barnacle", "thorn", "plate", "fungus",
                "vine", "leaf", "spine", "coral", "rime", "ember")

# What each growth is made of.  ``mix`` blends the creature's accent toward the
# growth's own colour, so a mossy bear carries green moss and a crystal golem
# carries its own violet, rather than everything taking the hide's tint.
# Growth that is vegetation, and so takes its colour from the artwork rather
# than from the kind.  Mineral crusts keep the creature's own mineral tint.
PLANT_GROWTH = {"leaf", "vine", "moss", "thorn", "fungus"}

GROWTH_COLOUR = {
    "moss": ((86, 122, 52), .78), "vine": ((74, 112, 54), .74),
    "leaf": ((132, 158, 58), .62), "fungus": ((206, 176, 132), .58),
    "thorn": ((78, 58, 44), .70), "barnacle": ((206, 198, 178), .62),
    "coral": ((214, 142, 118), .58), "rime": ((214, 234, 246), .52),
    "crystal": ((168, 146, 236), .30), "ember": ((246, 156, 52), .46),
    "plate": ((150, 148, 140), .50), "spine": ((92, 78, 62), .58),
}


# ---------------------------------------------------------------------------
# Woody structure: forking limbs and trunks you can see through
# ---------------------------------------------------------------------------
# A tree is not a cylinder with leaves glued on.  What makes bark read as bark
# at gameplay distance is that the silhouette forks, tapers and has holes in
# it, and neither a swept tube nor a scattering of surface growth can produce a
# hole.  These are the missing primitives: one grows a limb that splits, one
# builds a trunk out of separate strands so daylight gets through the gaps.


def _rotate_toward(direction, axis, angle: float):
    """Rodrigues rotation of ``direction`` about a unit ``axis``."""
    d = np.asarray(direction, dtype=float)
    a = np.asarray(axis, dtype=float)
    a = a / max(float(np.linalg.norm(a)), 1e-9)
    c, sn = math.cos(angle), math.sin(angle)
    return d * c + np.cross(a, d) * sn + a * float(np.dot(a, d)) * (1 - c)


def _perp(direction):
    """Any unit vector perpendicular to ``direction``."""
    d = np.asarray(direction, dtype=float)
    reference = np.array((0., 1., 0.))
    if abs(float(np.dot(d / max(np.linalg.norm(d), 1e-9), reference))) > .90:
        reference = np.array((0., 0., 1.))
    out = np.cross(d, reference)
    return out / max(float(np.linalg.norm(out)), 1e-9)


def branch_system(mesh, root, direction, length: float, radius: float, bones,
                  material, seed: str, depth: int = 3, splits: int = 2,
                  spread: float = .62, gnarl: float = .30, taper: float = .58,
                  shorten: float = .70, up_bias: float = .28,
                  segments: int = 3, sides: int = 6, tips=None):
    """Grow a forking, tapering, gnarled limb and return where it ended.

    Returns ``(tip, radius, depth)`` triples so foliage, lanterns or crystal can
    be hung on the ends rather than scattered over the whole shape.  The branch
    kinks at every segment (``gnarl``) and each fork leans away from its parent
    (``spread``) while being pulled back toward the sky (``up_bias``), which is
    what stops a recursive limb from looking like a radio antenna.
    """
    if tips is None:
        tips = []
    if depth < 0 or length <= 1e-5 or radius <= 1e-6:
        return tips
    rng = np.random.default_rng(zlib.crc32(seed.encode("utf-8")) % (2 ** 31))
    root = np.asarray(root, dtype=float)
    direction = np.asarray(direction, dtype=float)
    direction = direction / max(float(np.linalg.norm(direction)), 1e-9)

    points, radii = [root], [(radius, radius)]
    here, heading = root, direction
    for step in range(segments):
        # Kink about a random perpendicular axis, then bend back toward up so
        # the limb reaches rather than wanders.
        axis = _rotate_toward(_perp(heading), heading,
                              float(rng.uniform(0, 2 * math.pi)))
        heading = _rotate_toward(heading, axis, float(rng.uniform(-gnarl, gnarl)))
        heading = heading + np.array((0., up_bias * .5, 0.))
        heading = heading / max(float(np.linalg.norm(heading)), 1e-9)
        here = here + heading * (length / segments)
        grade = radius * (taper ** ((step + 1) / segments))
        # Slight ovality reads as woody rather than machined.
        points.append(here)
        radii.append((grade, grade * float(rng.uniform(.86, 1.14))))
    mesh.tube(points, radii, bones, material, sides=sides)

    end_radius = radii[-1][0]
    if depth == 0:
        tips.append((here, end_radius, depth))
        return tips
    # Fork.  One child continues the parent's line so the limb keeps a leader;
    # the rest peel off around it.
    for index in range(splits):
        axis = _rotate_toward(_perp(heading), heading,
                              2 * math.pi * index / max(splits, 1)
                              + float(rng.uniform(-.4, .4)))
        lean = spread * (0.0 if index == 0 and splits > 2
                         else float(rng.uniform(.55, 1.25)))
        child = _rotate_toward(heading, axis, lean)
        child = child + np.array((0., up_bias, 0.))
        child = child / max(float(np.linalg.norm(child)), 1e-9)
        branch_system(mesh, here, child,
                      length * shorten * float(rng.uniform(.82, 1.12)),
                      end_radius * float(rng.uniform(.72, .94)), bones, material,
                      seed + ":" + str(index), depth - 1, splits, spread, gnarl,
                      taper, shorten, up_bias, segments, max(4, sides - 1), tips)
    return tips


def woven_trunk(mesh, spine, radii, bones, material, seed: str, strands: int = 7,
                twist: float = 1.15, inset: float = .30, bulge: float = 1.24,
                sides: int = 5, material_inner=None, thickness: float = 1.0,
                inner_scale: float = .78):
    """A trunk built from separate twisting strands instead of one closed tube.

    The gaps between strands are the point: they are what makes a treant read
    as grown rather than turned on a lathe, and they are the one thing surface
    detail cannot fake.  ``material_inner``, if given, lines the hollow so the
    inside of the trunk is not the same shade as the outside.
    """
    spine = [np.asarray(point, dtype=float) for point in spine]
    if len(spine) < 2 or strands < 3:
        return
    rng = np.random.default_rng(
        zlib.crc32(("trunk:" + seed).encode("utf-8")) % (2 ** 31))
    rows = len(spine)
    if material_inner is not None:
        # A darker core stops the gaps showing straight through to the far side
        # of the model, which reads as a hole rather than a hollow.
        mesh.tube(spine, [(rx * (1 - inset) * inner_scale,
                           ry * (1 - inset) * inner_scale)
                          for rx, ry in radii], bones, material_inner, sides=10)
    # Strands have to ring the spine in the plane *perpendicular to it*, not in
    # world XZ.  Offsetting in XZ is right by accident for a vertical trunk and
    # wrong for everything else: on a shoulder yoke, which runs left to right,
    # the offsets lie along the yoke itself and the weave opens into a trumpet.
    frames = []
    for row in range(rows):
        if row == 0:
            tangent = spine[1] - spine[0]
        elif row == rows - 1:
            tangent = spine[-1] - spine[-2]
        else:
            tangent = spine[row + 1] - spine[row - 1]
        if float(np.linalg.norm(tangent)) < 1e-9:
            tangent = np.array((0., 1., 0.))
        frames.append(AnatomyMesh._frame(tangent))

    for strand in range(strands):
        phase = 2 * math.pi * strand / strands
        wobble = float(rng.uniform(.82, 1.18))
        girth = float(rng.uniform(.78, 1.26))
        points, thick = [], []
        for row in range(rows):
            t = row / (rows - 1)
            rx, ry = radii[row]
            # Strands converge at the ends and bow out across the middle, so
            # the trunk swells at the waist the way a braided bole does.
            swell = 1.0 + (bulge - 1.0) * math.sin(math.pi * t) ** .8
            angle = phase + twist * t * wobble
            right, up = frames[row]
            offset = (right * (math.cos(angle) * rx * (1 - inset) * swell)
                      + up * (math.sin(angle) * ry * (1 - inset) * swell))
            points.append(spine[row] + offset)
            span = (rx + ry) * .5 * (1 - inset)
            thick.append((span * .40 * girth * thickness
                          * (0.62 + .55 * math.sin(math.pi * t)),) * 2)
        mesh.tube(points, thick, bones, material, sides=sides)


# What a plate is cut like.  The concept art does not give these creatures one
# armour: a cairn golem is stacked river boulders, a frost golem is angular
# scale, a temple guardian wears big flat slabs and an amethyst golem erupts
# crystal.  (cross-section sides, relief x, footprint x, crown x, tilt down)
PLATE_SHAPES = {
    "boulder": (6, 1.00, 1.00, .70, .00),
    "scale":   (5, 0.80, 1.20, .52, .34),
    "slab":    (4, 0.86, 1.30, .78, .12),
    "shard":   (5, 1.85, 0.74, .10, -.18),
    "drum":    (10, 0.34, 1.34, .90, .00),
}


def plated_shell(mesh, spine, radii, bones, material, seed: str, rows: int = 4,
                 around: int = 6, relief: float = .26, gap: float = .16,
                 dome: float = .55, sides: int = 7, rune_material=None,
                 rune_chance: float = .22, span=(0.0, 1.0), shape: str = "boulder"):
    """Clad a limb in overlapping slabs, the way a cairn or a suit of plate is.

    The golems and constructs are drawn as a *stack of discrete blocks* -- you
    can count the boulders in a cairn golem's forearm -- and that is the whole
    read.  A smooth swept limb in a stone colour is a sausage with a rock
    texture on it, and no amount of normal map fixes a silhouette.

    Each plate is a short oriented puck standing proud of the surface along its
    own outward normal, so it catches its own highlight and casts its own
    shadow line; rows are staggered like masonry so the joints do not line up
    into stripes.  ``rune_material`` marks a scattering of plates with a lit
    glyph, which is what the art carves into them.
    """
    spine = [np.asarray(point, dtype=float) for point in spine]
    if len(spine) < 2 or rows < 1 or around < 3:
        return
    rng = np.random.default_rng(
        zlib.crc32(("plate:" + seed).encode("utf-8")) % (2 ** 31))
    cut, relief_x, foot_x, crown_x, tilt = PLATE_SHAPES.get(
        shape, PLATE_SHAPES["boulder"])
    sides = cut
    relief = relief * relief_x
    dome = dome * crown_x

    def sample(t):
        position = t * (len(spine) - 1)
        low = min(int(position), len(spine) - 2)
        frac = position - low
        point = spine[low] * (1 - frac) + spine[low + 1] * frac
        rx = radii[low][0] * (1 - frac) + radii[low + 1][0] * frac
        ry = radii[low][1] * (1 - frac) + radii[low + 1][1] * frac
        tangent = spine[low + 1] - spine[low]
        if float(np.linalg.norm(tangent)) < 1e-9:
            tangent = np.array((0., 1., 0.))
        return point, (rx, ry), tangent

    for row in range(rows):
        t = span[0] + (span[1] - span[0]) * (row + .5) / rows
        point, (rx, ry), tangent = sample(t)
        right, up = AnatomyMesh._frame(tangent)
        # Brick bond: every other row is offset by half a plate.
        phase = math.pi / around * (row % 2)
        girth = (rx + ry) * .5
        # Plate half-width from the arc it has to cover, less the joint gap.
        half = (math.pi * girth / around) * (1.0 - gap) * foot_x
        depth = girth * relief
        for k in range(around):
            angle = phase + 2 * math.pi * k / around
            outward = right * math.cos(angle) + up * math.sin(angle)
            outward = outward / max(float(np.linalg.norm(outward)), 1e-9)
            seat = point + right * (math.cos(angle) * rx) + up * (math.sin(angle) * ry)
            lift = float(rng.uniform(.72, 1.28))
            wobble = float(rng.uniform(.86, 1.16))
            lean = -tangent / max(float(np.linalg.norm(tangent)), 1e-9) * (
                girth * tilt)
            inner = seat - outward * depth * .55
            crest = seat + outward * depth * .34 * lift + lean * .35
            outer = seat + outward * depth * lift + lean
            mesh.tube([inner, crest, outer],
                      [(half * .80 * wobble, half * .72 * wobble),
                       (half * wobble, half * .90 * wobble),
                       (half * dome * wobble, half * dome * .90 * wobble)],
                      bones, material, sides=sides)
            if rune_material is not None and rng.random() < rune_chance:
                # A glyph cut into the face of the plate, lit from inside it.
                mesh.tube([outer - outward * depth * .10,
                           outer + outward * depth * .16],
                          [(half * .30, half * .26), (half * .22, half * .19)],
                          bones, rune_material, sides=5)


def orbit_plates(mesh, centre, radius: float, bones, material, seed: str,
                 count: int = 8, arc: float = .62, width: float = .34,
                 thickness: float = .12, axis=(0., 0., 1.), tilt: float = .0,
                 sides: int = 5, jitter: float = .14):
    """Curved armour plates floating in a ring, detached from the body.

    The arcane constructs are not built like anything else in the library: the
    art gives them a lit core with its armour hanging *off* it in an arc,
    nothing touching.  Each plate here is a swept arc of a circle with a broad
    flat section, so it reads as a curved slab rather than as a bent pipe.
    """
    centre = np.asarray(centre, dtype=float)
    axis = np.asarray(axis, dtype=float)
    axis = axis / max(float(np.linalg.norm(axis)), 1e-9)
    right, up = AnatomyMesh._frame(axis)
    rng = np.random.default_rng(
        zlib.crc32(("orbit:" + seed).encode("utf-8")) % (2 ** 31))
    for index in range(count):
        base = 2 * math.pi * index / count
        reach = radius * (1.0 + float(rng.uniform(-jitter, jitter)))
        lift = float(rng.uniform(-jitter, jitter)) * radius * .5
        points, radii = [], []
        steps = 5
        for step in range(steps):
            t = step / (steps - 1)
            angle = base + arc * (t - .5)
            here = (centre + right * (math.cos(angle) * reach)
                    + up * (math.sin(angle) * reach)
                    + axis * (lift + tilt * math.sin(angle) * radius))
            # Broad in the plane of the ring, thin through it, tapering to
            # both ends so the plate has a point rather than a cut-off.
            taper = math.sin(math.pi * (.18 + .64 * t))
            points.append(here)
            radii.append((radius * width * taper,
                          radius * thickness * taper))
        mesh.tube(points, radii, bones, material, sides=sides)


def debris_field(mesh, centre, extent, bones, material, seed: str,
                 count: int = 9, size: float = .16, drift: float = 1.0):
    """Broken pieces hanging in the air around a shattered body."""
    centre = np.asarray(centre, dtype=float)
    extent = np.asarray(extent, dtype=float)
    rng = np.random.default_rng(
        zlib.crc32(("debris:" + seed).encode("utf-8")) % (2 ** 31))
    for index in range(count):
        offset = np.array([float(rng.uniform(-1., 1.)) for _ in range(3)])
        # Pieces drift outward and upward, as though still coming apart.
        offset[1] = abs(offset[1]) * .8 + .12
        here = centre + offset * extent * drift
        chunk = size * float(rng.uniform(.55, 1.35))
        axis = np.array([float(rng.uniform(-1., 1.)) for _ in range(3)])
        axis = axis / max(float(np.linalg.norm(axis)), 1e-9) * chunk
        # Blocky rather than bladed: these are pieces of a wall, and a thin
        # tapered spindle reads as a shard of glass instead.
        mesh.tube([here - axis, here + axis * .2, here + axis],
                  [(chunk * .50, chunk * .42), (chunk * .66, chunk * .58),
                   (chunk * .44, chunk * .36)],
                  bones, material, sides=4)


def metal_band(mesh, centre, direction, radius, bones, material,
               thickness: float = .10, flare: float = 1.18, sides: int = 12):
    """A banding ring around a limb, as the art puts at every wrist and ankle."""
    centre = np.asarray(centre, dtype=float)
    direction = np.asarray(direction, dtype=float)
    length = float(np.linalg.norm(direction))
    if length < 1e-9 or radius <= 0:
        return
    axis = direction / length
    half = axis * radius * thickness
    mesh.tube([centre - half, centre, centre + half],
              [(radius * flare * .94, radius * flare * .94),
               (radius * flare, radius * flare),
               (radius * flare * .94, radius * flare * .94)],
              bones, material, sides=sides, cap_start=False, cap_end=False)


def root_flare(mesh, base, radius: float, bones, material, seed: str,
               count: int = 5, reach: float = 1.5, drop: float = .0):
    """Buttress roots splaying off the foot of a trunk."""
    rng = np.random.default_rng(
        zlib.crc32(("roots:" + seed).encode("utf-8")) % (2 ** 31))
    base = np.asarray(base, dtype=float)
    for index in range(count):
        angle = 2 * math.pi * index / count + float(rng.uniform(-.28, .28))
        out = np.array((math.cos(angle), 0., math.sin(angle)))
        # Roots reach outward and only just down: dropping them a full radius
        # put the toes under the floor, and the builder then lifted the whole
        # creature to clear them, so every treant appeared to hover.
        fall = min(radius * .34, base[1] * .62)
        knee = base + out * radius * .85 + np.array((0., -fall * .70, 0.))
        toe = base + out * radius * reach + np.array((0., -fall - drop, 0.))
        mesh.tube([base + np.array((0., radius * .30, 0.)), knee, toe],
                  [(radius * .17, radius * .20), (radius * .11, radius * .12),
                   (radius * .035, radius * .035)], bones, material, sides=6)


def _geodesic(subdivisions: int = 2):
    """Unit icosphere as (vertices, triangles).  Even facets, no poles."""
    phi = (1.0 + math.sqrt(5.0)) * .5
    verts = []
    for a, b in ((1.0, phi), (-1.0, phi), (1.0, -phi), (-1.0, -phi)):
        verts += [(0.0, a, b), (b, 0.0, a), (a, b, 0.0)]
    verts = [np.asarray(v, dtype=float) / math.sqrt(1 + phi * phi) for v in verts]
    # Rebuild the icosahedron's faces from proximity: every vertex pair at the
    # shortest edge length is an edge, and every triangle of mutual edges is a
    # face.  Cheaper to derive than to spell out and impossible to mistype.
    edge = min(float(np.linalg.norm(a - b))
               for i, a in enumerate(verts) for b in verts[i + 1:])
    near = [[j for j, b in enumerate(verts)
             if j != i and abs(float(np.linalg.norm(a - b)) - edge) < 1e-6]
            for i, a in enumerate(verts)]
    faces = set()
    for i, neighbours in enumerate(near):
        for j in neighbours:
            for k in near[j]:
                if k in neighbours:
                    faces.add(tuple(sorted((i, j, k))))
    faces = sorted(faces)
    for _ in range(max(0, subdivisions)):
        midpoint, split = {}, []

        def middle(a, b):
            key = (min(a, b), max(a, b))
            if key not in midpoint:
                point = verts[a] + verts[b]
                verts.append(point / max(float(np.linalg.norm(point)), 1e-9))
                midpoint[key] = len(verts) - 1
            return midpoint[key]

        for a, b, c in faces:
            ab, bc, ca = middle(a, b), middle(b, c), middle(c, a)
            split += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = split
    return verts, faces


def feather_row(mesh, lead, trail, bones, material, seed: str, count: int = 9,
                overhang: float = .55, width: float = .30, tip_material=None,
                splay: float = .18, sides: int = 4):
    """Overlapping flight feathers laid along a wing's trailing edge.

    A wing drawn as one membrane between two curves is a coloured triangle: it
    has no edge to catch light and no serration in its outline, and at any
    distance it reads as a fin rather than as a wing.  Real flight feathers
    overlap in a row, each one a little longer than the last toward the tip,
    and their staggered ends are what the eye reads as feathering.

    ``lead`` and ``trail`` are the two edge curves already used for the
    membrane; the feathers hinge on the leading edge and reach ``overhang``
    past the trailing one.
    """
    lead = [np.asarray(point, dtype=float) for point in lead]
    trail = [np.asarray(point, dtype=float) for point in trail]
    if len(lead) < 2 or len(lead) != len(trail) or count < 1:
        return
    rng = np.random.default_rng(
        zlib.crc32(("feather:" + seed).encode("utf-8")) % (2 ** 31))
    for index in range(count):
        t = (index + .5) / count
        root = _bezier(lead, t)
        edge = _bezier(trail, t)
        chord = edge - root
        span = float(np.linalg.norm(chord))
        if span < 1e-6:
            continue
        # Primaries at the wing tip are the longest; coverts near the shoulder
        # are short.  The gradient is what gives the wing its swept outline.
        reach = 1.0 + overhang * (.35 + .95 * t) * float(rng.uniform(.88, 1.12))
        # Fan each quill slightly off the chord so they overlap rather than
        # stacking exactly on one another.
        drift = np.cross(chord, np.array((0., 1., 0.)))
        norm = float(np.linalg.norm(drift))
        if norm > 1e-9:
            drift = drift / norm * span * splay * (t - .5)
        else:
            drift = np.zeros(3)
        tip = root + chord * reach + drift
        quill = span * width * (.55 + .60 * (1.0 - abs(t - .55)))
        mesh.tube([root, root + chord * .45, tip],
                  [(quill * .34, quill * .12), (quill * .30, quill * .10),
                   (quill * .07, quill * .04)],
                  bones, material, sides=sides)
        if tip_material is not None and t > .35:
            mesh.tube([root + chord * reach * .74 + drift * .74, tip],
                      [(quill * .17, quill * .06), (quill * .06, quill * .03)],
                      bones, tip_material, sides=sides)


def facet_shell(mesh, centre, size, bones, material, seed: str,
                subdivisions: int = 2, relief: float = .10, gap: float = .16,
                core_material=None, core_scale: float = .90, squash=None):
    """A shell of flat crystal plates with light showing between them.

    The crystal fauna were smooth ellipsoids in a crystal colour, which reads
    as painted plastic; what the art actually draws is a mosaic of hard flat
    facets with the glow trapped inside leaking out of the seams.  Neither half
    of that survives a smooth-shaded sphere, so this emits every plate as its
    own flat-shaded triangle -- shrunk toward its centroid by ``gap`` so the
    seams are real openings -- over an optional lit inner shell.
    """
    centre = np.asarray(centre, dtype=float)
    half = np.asarray(size, dtype=float) * .5
    rng = np.random.default_rng(
        zlib.crc32(("facet:" + seed).encode("utf-8")) % (2 ** 31))
    verts, faces = _geodesic(subdivisions)

    if core_material is not None:
        mesh.ellipsoid(tuple(centre), tuple(np.asarray(size) * core_scale),
                       bones, core_material, rings=9, sides=14, squash=squash)

    positions, normals, uvs, indices = [], [], [], []
    for a, b, c in faces:
        plate = [verts[a], verts[b], verts[c]]
        # Each plate stands a little proud of the sphere, by its own amount,
        # so the shell has the irregular crystal relief the art shows.
        lift = 1.0 + relief * float(rng.uniform(.35, 1.0))
        corners = []
        centroid = (plate[0] + plate[1] + plate[2]) / 3.0
        for point in plate:
            pulled = centroid + (point - centroid) * (1.0 - gap)
            local = pulled * lift * half
            if squash is not None and local[2] < 0:
                local = np.array((local[0], local[1] * squash, local[2]))
            corners.append(centre + local)
        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
        length = float(np.linalg.norm(normal))
        if length < 1e-12:
            continue
        normal = normal / length
        if float(np.dot(normal, centroid)) < 0:
            corners = [corners[0], corners[2], corners[1]]
            normal = -normal
        base = len(positions)
        for point in corners:
            positions.append(point)
            normals.append(normal)
        uvs += [(.5 + centroid[0] * .5, .5 + centroid[1] * .5),
                (.5 + centroid[2] * .5, .5 + centroid[1] * .5),
                (.5 + centroid[0] * .5, .5 + centroid[2] * .5)]
        indices += [base, base + 1, base + 2]
    if indices:
        mesh._append(positions, normals, uvs, indices, material, bones)


def swirl_ribbon(mesh, points, width: float, bones, material, seed: str,
                 samples: int = 15, turns: float = 1.15, curl: float = .30,
                 flatten: float = .34, taper: float = .06, sides: int = 7,
                 phase: float = 0.0):
    """A long curling band that winds around the line it follows.

    Flame, spirit-hair and running water are drawn in the concept art as
    ribbons that coil: they wrap, cross in front of the body and taper away.
    Sweeping a fat three-point tube down the same path instead produces a
    straight wedge, and a ring of straight wedges reads as an upturned insect
    rather than as a wisp.  This resamples the path finely, winds it round its
    own axis, and sweeps a flattened section so the band has an edge.

    ``curl`` is the coil radius as a fraction of the path length; ``turns`` is
    how many times it goes round on the way out; ``flatten`` is the ribbon's
    thickness relative to its width.
    """
    points = [np.asarray(point, dtype=float) for point in points]
    if len(points) < 2 or width <= 0:
        return
    rng = np.random.default_rng(
        zlib.crc32(("ribbon:" + seed).encode("utf-8")) % (2 ** 31))
    span = float(np.linalg.norm(points[-1] - points[0]))
    lean = float(rng.uniform(.82, 1.18))

    centres, radii = [], []
    for index in range(samples):
        t = index / (samples - 1)
        here = _bezier(points, t)
        # Wind about the local direction of travel.
        ahead = _bezier(points, min(1.0, t + .04))
        behind = _bezier(points, max(0.0, t - .04))
        tangent = ahead - behind
        if float(np.linalg.norm(tangent)) < 1e-9:
            tangent = np.array((0., 1., 0.))
        right, up = AnatomyMesh._frame(tangent)
        angle = phase + 2 * math.pi * turns * t * lean
        # The coil opens up as the ribbon runs out, the way a flame's tip
        # loosens; holding it constant reads as a drill bit.
        swing = curl * span * (.35 + .85 * t)
        centres.append(here + right * (math.cos(angle) * swing)
                       + up * (math.sin(angle) * swing))
        # Wide at the root, drawn to nothing at the tip.
        grade = width * (1.0 - (1.0 - taper) * t ** 1.35)
        radii.append((grade, max(grade * flatten, width * .02)))
    mesh.tube(centres, radii, bones, material, sides=sides, cap_start=False)


def foliage_cluster(mesh, centre, size: float, bones, material, seed: str,
                    count: int = 5, flatten: float = .62):
    """A puff of leaf mass, built from overlapping lobes rather than one blob."""
    rng = np.random.default_rng(
        zlib.crc32(("leaf:" + seed).encode("utf-8")) % (2 ** 31))
    centre = np.asarray(centre, dtype=float)
    for _ in range(count):
        offset = np.array([float(rng.uniform(-.55, .55)) for _ in range(3)]) * size
        lobe = size * float(rng.uniform(.44, .80))
        # Four rings by seven sides was fifty-six triangles a lobe and hundreds
        # a cluster; at the size a leaf clump is drawn none of that is visible.
        mesh.ellipsoid(tuple(centre + offset), (lobe, lobe * flatten, lobe),
                       bones, material, rings=3, sides=6)


def growth_colour(kinds, accent, base, measured=None):
    """Blend the creature's accent toward the colour of what grows on it.

    ``measured`` is the tint sampled from that creature's own concept figure.
    Where it exists it replaces the per-kind guess, because the kind only says
    *what* is growing and the art says what colour it is -- the difference
    between a green Verdant Stair leaf and an amber Amberwood one.
    """
    if not kinds:
        return accent
    total = np.zeros(3, dtype=float)
    for kind, weight in kinds:
        tint, mix = GROWTH_COLOUR.get(kind, ((150, 150, 150), .5))
        if measured is not None and kind in PLANT_GROWTH:
            tint, mix = measured, min(.92, mix + .22)
        blended = np.asarray(accent, dtype=float) * (1 - mix) + np.asarray(tint, dtype=float) * mix
        total += blended * weight
    total /= max(sum(w for _, w in kinds), 1e-6)
    return tuple(int(round(min(255, max(0, v)))) for v in total)


# How far each growth is pulled off the surface normal: negative hangs with
# gravity, positive stands up toward the light.
_DRAPE = {"moss": -.52, "vine": -.68, "leaf": -.46, "coral": .30,
          "fungus": .58, "crystal": .30, "rime": .34, "spine": .18,
          "ember": .40}


def _growth_frame(rng, point, radius, up_bias: float, tangent=None):
    """A point on the shell, its outward normal, and how high up the flank it is.

    Growth sits *on* a surface, so it points along that surface's normal, and
    the surface here is a tube around the spine -- which means the normal lives
    in the plane perpendicular to the local spine direction.  Sampling in world
    space instead works by accident on a quadruped, whose spine is horizontal,
    and fails completely on a biped, whose spine is vertical: every tuft ends
    up pointing along the trunk axis and buried inside the torso, which is why
    a moss troll came out bald.  ``up_bias`` crowds the draw toward the ridge
    of that tube -- the back of a quadruped, the shoulders and spine of a
    standing figure -- with 0 spreading evenly all the way round.
    """
    axis = np.array((0., 1., 0.)) if tangent is None else np.asarray(tangent, float)
    norm = float(np.linalg.norm(axis))
    axis = np.array((0., 0., 1.)) if norm < 1e-6 else axis / norm
    # "Up" on the tube: world up, less whatever of it runs along the spine.
    up = np.array((0., 1., 0.)) - axis * float(axis[1])
    if float(np.linalg.norm(up)) < .25:
        # A vertical spine has no meaningful up; ride the back instead.
        up = np.array((0., 0., 1.)) - axis * float(axis[2])
    up /= max(float(np.linalg.norm(up)), 1e-6)
    side = np.cross(axis, up)
    side /= max(float(np.linalg.norm(side)), 1e-6)
    skew = float(rng.random()) ** (1.0 + 4.0 * max(min(up_bias, 1.0), 0.0))
    theta = skew * math.pi                      # 0 at the ridge, pi underneath
    direction = up * math.cos(theta) + side * math.sin(theta) * (
        1.0 if rng.random() < .5 else -1.0)
    direction /= max(float(np.linalg.norm(direction)), 1e-6)
    surface = point + np.array((direction[0] * radius[0],
                                direction[1] * radius[1],
                                direction[2] * radius[0]))
    # 1 at the ridge, 0 underneath: growth is thickest where it catches rain.
    return surface, direction, .5 + .5 * math.cos(theta)


def encrust(mesh, kind: str, count: int, spine, radii, bones, scale: float,
            seed: str = "", material_body=None, material_feature=None,
            span=(0.06, 0.94), up_bias: float = .78, size: float = 1.0):
    """Scatter growth of ``kind`` along a body's spine."""
    if count <= 0 or len(spine) < 2:
        return
    body_mat = MAT_GROWTH if material_body is None else material_body
    feature_mat = MAT_GROWTH if material_feature is None else material_feature
    rng = np.random.default_rng(zlib.crc32(f"{kind}:{seed}".encode("utf-8")) % (2 ** 31))
    s = scale
    for index in range(count):
        t = span[0] + (span[1] - span[0]) * (index + .5) / count
        t += float(rng.uniform(-.4, .4)) * (span[1] - span[0]) / count
        t = min(max(t, 0.0), 1.0)
        position = t * (len(spine) - 1)
        low = min(int(position), len(spine) - 2)
        frac = position - low
        point = spine[low] * (1 - frac) + spine[low + 1] * frac
        radius = (radii[low][0] * (1 - frac) + radii[low + 1][0] * frac,
                  radii[low][1] * (1 - frac) + radii[low + 1][1] * frac)
        tangent = spine[low + 1] - spine[low]
        base, direction, high = _growth_frame(rng, point, radius, up_bias, tangent)
        # Thick over the back, thinning to a fringe down the flank, and sized
        # against the body it is growing on rather than against the creature's
        # nominal scale.  Scale alone is near 1 for a songbird and a bear
        # alike, so an owl was wearing leaves a bear's size and disappeared
        # under them.
        girth = (radius[0] + radius[1]) * .5
        grow = (float(rng.uniform(.7, 1.35)) * size * (.62 + .52 * high)
                * max(girth * 2.9, s * .22))
        # What grows on a creature does not stand along the surface normal.
        # Moss and vine hang, fungus caps turn to face the sky, and only the
        # mineral growths -- crystal, rime, thorn, spine -- actually spike
        # outward.  Left un-drooped, a mossy flank sprays sideways like quills.
        pull = _DRAPE.get(kind)
        if pull is not None:
            direction = direction * (1.0 - abs(pull)) + np.array(
                (0., math.copysign(1.0, pull), 0.)) * abs(pull)
            direction /= max(float(np.linalg.norm(direction)), 1e-6)

        if kind == "moss":
            # A mat of overlapping clumps hugging the hide, with a few strands
            # hanging off its lower edge.  One pebble and two bristles read as
            # scattered flecks at any distance a player sees the model from.
            for k in range(3):
                spread = np.array([float(rng.uniform(-.075, .075)) for _ in range(3)])
                mesh.ellipsoid(tuple(base + direction * .010 * grow + spread * grow),
                               (.105 * grow * (1 - .18 * k), .042 * grow,
                                .105 * grow * (1 - .18 * k)),
                               bones, body_mat, rings=4, sides=7)
            for _ in range(3):
                tuft = base + direction * .02 * grow + np.array(
                    (float(rng.uniform(-.07, .07)), 0.,
                     float(rng.uniform(-.07, .07)))) * grow
                mesh.tube([tuft, tuft + direction * .05 * grow,
                           tuft + direction * .07 * grow
                           + np.array((0., -.055 * grow, 0.))],
                          [(.017 * grow, .017 * grow), (.011 * grow, .011 * grow),
                           (.003 * grow, .003 * grow)],
                          bones, body_mat, sides=4)
        elif kind in ("crystal", "rime"):
            for _ in range(3):
                jitter = np.array([float(rng.uniform(-.7, .7)) for _ in range(3)])
                axis = direction + jitter
                axis /= max(np.linalg.norm(axis), 1e-6)
                # Wide length spread: a cluster of equal shards reads as a comb.
                length = .11 * grow * float(rng.uniform(.42, 1.9))
                mesh.tube([base, base + axis * length * .45, base + axis * length],
                          [(.040 * grow, .034 * grow), (.030 * grow, .026 * grow),
                           (.005 * grow, .005 * grow)],
                          bones, feature_mat, sides=5)
        elif kind == "barnacle":
            mesh.tube([base, base + direction * .045 * grow],
                      [(.055 * grow, .055 * grow), (.030 * grow, .030 * grow)],
                      bones, feature_mat, sides=6)
            mesh.ellipsoid(tuple(base + direction * .05 * grow),
                           (.030 * grow, .012 * grow, .030 * grow),
                           bones, MAT_DARK, rings=3, sides=6)
        elif kind in ("thorn", "spine"):
            if kind == "spine":
                mesh.spike(base, base + direction * .24 * grow, .026 * grow,
                           bones, feature_mat, sides=5)
            else:
                # Bramble is a runner studded with short barbs, not a fan of
                # long quills: the quills were reading as a hedgehog from every
                # angle and swallowing the silhouette underneath.
                heading = direction.copy()
                steps = [base]
                for _ in range(3):
                    heading = heading + np.array(
                        [float(rng.uniform(-.55, .55)) for _ in range(3)])
                    heading[1] -= .22
                    heading /= max(np.linalg.norm(heading), 1e-6)
                    steps.append(steps[-1] + heading * .090 * grow)
                mesh.tube(steps, [(.016 * grow, .016 * grow), (.013 * grow, .013 * grow),
                                  (.010 * grow, .010 * grow), (.005 * grow, .005 * grow)],
                          bones, body_mat, sides=5)
                for point in steps[:3]:
                    jitter = np.array([float(rng.uniform(-1., 1.)) for _ in range(3)])
                    axis = direction * .5 + jitter
                    axis /= max(np.linalg.norm(axis), 1e-6)
                    mesh.spike(point, point + axis * .070 * grow, .015 * grow,
                               bones, feature_mat, sides=4)
        elif kind == "plate":
            mesh.ellipsoid(tuple(base + direction * .01 * grow),
                           (.20 * grow, .055 * grow, .15 * grow),
                           bones, feature_mat, rings=5, sides=8)
        elif kind == "fungus":
            stalk = base + direction * .055 * grow
            mesh.tube([base, stalk], [(.016 * grow, .016 * grow),
                                      (.013 * grow, .013 * grow)],
                      bones, body_mat, sides=5)
            mesh.ellipsoid(tuple(stalk + direction * .012 * grow),
                           (.098 * grow, .042 * grow, .098 * grow),
                           bones, feature_mat, rings=4, sides=8, squash=.5)
        elif kind in ("vine", "coral"):
            steps = [base]
            heading = direction.copy()
            for _ in range(4):
                heading = heading + np.array([float(rng.uniform(-.5, .5)) for _ in range(3)])
                heading /= max(np.linalg.norm(heading), 1e-6)
                steps.append(steps[-1] + heading * .095 * grow)
            mesh.tube(steps, [(.024 * grow, .024 * grow), (.019 * grow, .019 * grow),
                              (.015 * grow, .015 * grow), (.010 * grow, .010 * grow),
                              (.004 * grow, .004 * grow)],
                      bones, body_mat if kind == "vine" else feature_mat, sides=5)
        elif kind == "leaf":
            # A spray of three, each big enough to read: single stamps at the
            # old size vanished into the hide at any sane viewing distance.
            stem = base + direction * .05 * grow
            mesh.tube([base, stem], [(.011 * grow, .011 * grow),
                                     (.007 * grow, .007 * grow)],
                      bones, body_mat, sides=4)
            for k in range(3):
                jitter = np.array([float(rng.uniform(-.45, .45)) for _ in range(3)])
                heading = direction + jitter
                heading /= max(np.linalg.norm(heading), 1e-6)
                tip = stem + heading * .17 * grow
                side = np.cross(heading, np.array((0., 1., 0.)))
                if np.linalg.norm(side) < 1e-6:
                    side = np.array((1., 0., 0.))
                side /= np.linalg.norm(side)
                _sheet(mesh,
                       [stem, stem + heading * .08 * grow + side * .058 * grow, tip],
                       [stem, stem + heading * .08 * grow - side * .058 * grow, tip],
                       .006 * grow, bones, feature_mat)
        elif kind == "ember":
            mesh.ellipsoid(tuple(base + direction * .05 * grow),
                           (.030 * grow, .030 * grow, .030 * grow),
                           bones, feature_mat, rings=4, sides=6)
