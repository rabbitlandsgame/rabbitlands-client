#!/usr/bin/env python3
"""Geometry for the sixty-four leg garments.

The silhouette is authored as a recipe and fitted procedurally: every design
names a kind and a handful of features, and the shapes below loft those onto
whichever rig is being built.  Sixty-four hand-modelled meshes would have to be
re-modelled for the saurian rig as well, and nothing in this project is authored
in a DCC tool, so the generator stays and grows a vocabulary instead.

Three structural shells carry the garment and every acceptance criterion that
matters is about them: a hip shell closed over the seat, and two leg tubes that
start *inside* it.  Everything else - tassets, kneecops, straps, panels, fur -
is decoration lofted over the top, and decoration is allowed to be an open band
because the winding test measures the mesh's total enclosed volume rather than
each piece's.

Three seams decide whether a leg garment works, and each has its own answer
here:

**Waist.**  The shirt spans Y 1.022-1.550 and is drawn outside the hip shell,
so a waistband at the old 1.055 was *underneath the shirt and invisible*; what
players read as the belt was a second belt the torso garment drew at 1.107, 30
mm above the top of the trousers.  Our user's ruling is that the legs get the
belt, so the torso piece drops its own and the waistband here is built to be
unambiguously the outer layer through the shared band: shell .020 proud of the
body against the shirt's .011, a waistband at .028 and a belt at .038.

**Seat.**  The hip shell reaches the crotch line and the leg tubes start above
it, so the two always overlap.  The band across the backside that the shell
used to leave bare is closed by construction rather than by tuning.

**Boot cuff.**  A ``pants`` hem lands at world Y .142 on the reference rig and
a ``legs`` hem at .178, both quoted to the footwear brief in world Y and as a
fraction of the thigh+calf chain, because the two pipelines parameterise
differently and bare fractions do not cross between them.
"""
from __future__ import annotations

import math

import numpy as np

from equipment_authoring import (Garment, HIP_BONES, LEG_MEASURE_L,
                                 LEG_MEASURE_R, MATERIAL_BASE, MATERIAL_DETAIL,
                                 MATERIAL_TRIM, Rig, Surface, limb_rings,
                                 torso_rings)

# --------------------------------------------------------------------------
# The seam datum, shared with the footwear brief.  Measured on luminous_male.
# --------------------------------------------------------------------------

#: Fraction along the thigh+calf chain each kind's hem sits at.  These are the
#: numbers the boot is cut against; moving one moves the seam and must be
#: agreed with the footwear brief rather than changed here alone.
HEM = {"pants": .93, "legs": .89, "kilt": .93}

#: Where the hip shell stops, in world Y on the reference rig - a height, not a
#: chain fraction, because it is lofted from the torso silhouette rather than
#: along a limb.  The inherited values were .902 and .914, which put the bottom
#: edge above the widest part of a female upper thigh: the two leg tubes below
#: are circles about each thigh axis and do not meet the outer hip flare, so
#: every female rig showed a crescent of skin there.  Dropped far enough that
#: the shell and the tubes overlap through the whole flare.
HIP_LOW = {"pants": .745, "legs": .753, "kilt": .745}

#: Top of the hip shell.  Raised from 1.075 so the waistband clears the shirt
#: hem at 1.022 with room to read as a separate garment.
WAIST_TOP = 1.088
#: The waistband proper - a doubled band of cloth or a plate girdle.
WAIST_LOW = 1.030
#: Height of the belt, and how far each layer stands off the body.  The shirt
#: is lofted at .011, so these three are deliberately outside it in order.
BELT_Y = 1.048
SHELL_STANDOFF = .032
WAIST_STANDOFF = .034
BELT_STANDOFF = .038
#: The shell reaches below the crotch so that it, and not the two leg tubes,
#: closes the inseam - tubes are circles about each thigh axis and never meet
#: across the middle.  Left at full thickness that low it would also stand about
#: 11 mm proud of the tubes at the outer thigh and read as a skirt, so the lower
#: rings are drawn back in.  Everything below the crotch is inside the tubes and
#: invisible; only the inseam itself shows, which is what it is for.
SEAT_TUCK = -.013


def _sides(feature_count: int) -> int:
    """Ring density.  Busy designs get more sides so detail does not alias."""
    return 26 if feature_count < 3 else 30


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------

def _hip_shell(surface: Surface, rig: Rig, kind: str) -> None:
    """The seat, as a closed volume, from the crotch line to above the shirt hem.

    Capped at *both* ends, which is the whole point.  The inherited shell was
    capped at the top only, so it was an open tube - and an open tube is not a
    closed component, encloses nothing, and answers for no part of the body at
    all.  Coverage over the seat rested entirely on the two leg tubes, which are
    circles about each thigh axis and never meet across the middle.  That is the
    bare band across the backside, and no amount of moving the bottom edge fixes
    it while the shell is open.

    The bottom cap is a disc across the crotch, inside the body and invisible.
    It leaves the shell and the two tubes as three overlapping closed volumes in
    one primitive - which is exactly the case whole-primitive ray parity gets
    wrong, and exactly the case the connected-component split in ``garment_fit``
    exists to measure.
    """
    hips = torso_rings(rig, HIP_LOW[kind], WAIST_TOP, rows=11, sides=26,
                       thickness=SHELL_STANDOFF, flare_low=SEAT_TUCK,
                       floor=.058, bones=HIP_BONES)
    surface.loft(hips, MATERIAL_BASE, cap_start=True, cap_end=True)


def _waistband(surface: Surface, rig: Rig) -> None:
    """A doubled band over the shirt hem, and the belt over that.

    This is the whole answer to "the separation between the shirt and pants is
    still not clear".  Neither piece is subtle about which is outermost.
    """
    band = torso_rings(rig, WAIST_LOW, WAIST_TOP, rows=4, sides=28,
                       thickness=WAIST_STANDOFF, floor=.060, bones=HIP_BONES)
    surface.loft(band, MATERIAL_BASE)
    belt = torso_rings(rig, BELT_Y - .026, BELT_Y + .026, rows=3, sides=28,
                       thickness=BELT_STANDOFF, floor=.060, bones=HIP_BONES)
    surface.loft(belt, MATERIAL_TRIM)


#: How far the cuff is stretched fore-and-aft, and over what fraction of the
#: tube, measured from the hem.  An ankle is not round: the heel stands well
#: behind the calf axis and the instep in front of it, and a circle drawn about
#: that axis misses both.
#:
#: Both terms are needed and neither alone is enough, which was not the guess.
#: Growing the ring uniformly has to balloon the whole cuff to reach the heel,
#: and past about 1.10 the ring stops being convex and parity through it stops
#: meaning anything - a flare of 1.34 measured worse than no flare at all.
#: Sliding the ring backwards reaches the heel and gives up the instep; the
#: reasonable-sounding conclusion from that was to stop sliding and stretch
#: fore-and-aft instead, and measured against the fourteen plantigrade rigs it
#: was worse than the slide it replaced - 222 exposed against 172.  Swept as a
#: pair, a small stretch on top of a slightly larger slide beats either.
HEEL_STRETCH = 1.15
HEEL_BIAS = .034
HEEL_BLEND = .24
#: How many of the bottom rings are levelled off into a flat hem.
LEVEL_ROWS = 3



def _leg_tube(rig: Rig, side: str, kind: str, *, thickness: float,
              sides: int, start: float = .018,
              taper_end: float = 1.0) -> list[np.ndarray]:
    # `LEG_MEASURE_*` is thigh, calf and pelvis - it does not name the foot.
    # The hem sits below the ankle joint, so the bottom rings are measured
    # against the foot as well; without it every ray cast that way found no bone
    # it was allowed to measure and fell back to the floor radius.
    measure = (LEG_MEASURE_L if side == "l" else LEG_MEASURE_R) + [f"foot_{side}"]
    rings = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=18,
                       sides=sides, thickness=thickness, start=start,
                       end=HEM[kind], floor=.040, bones=measure,
                       taper_end=taper_end)
    rows = len(rings)
    for index, ring in enumerate(rings):
        depth = (index / (rows - 1) - (1.0 - HEEL_BLEND)) / HEEL_BLEND
        if depth <= 0.0:
            continue
        grow = 1.0 + (HEEL_STRETCH - 1.0) * depth ** 1.5
        centre = ring[:, 2].mean()
        ring[:, 2] = centre + (ring[:, 2] - centre) * grow
        ring[:, 2] -= HEEL_BIAS * depth ** 1.5
    # A hem is cut level, and on this rig it has to be.  The rings are built
    # perpendicular to the bone and then grown and slid, which leaves the last
    # one spanning 12 mm of height; the cap fanned across it is a tilted disc,
    # and a body vertex inside that band sits below the cap on one side of the
    # leg and above it on the other.  Levelling the last rings makes the cap
    # planar, which is both what a trouser hem looks like and the only way the
    # boundary is unambiguous enough to be measured.
    for index in range(rows - LEVEL_ROWS, rows):
        ring = rings[index]
        blend = (index - (rows - LEVEL_ROWS - 1)) / LEVEL_ROWS
        ring[:, 1] += (ring[:, 1].mean() - ring[:, 1]) * min(blend, 1.0)
    return rings


#: How much the tube widens at the hem.  A leg is not a circle at the ankle -
#: the heel juts back past any circle drawn about the calf axis - so a tube that
#: fits the shin lets the heel through at the very bottom ring.  A real trouser
#: flares at the cuff for the same reason.  Swept from 1.00 to 1.34 against the
#: fourteen plantigrade rigs: coverage improves to about 1.10 and then gets
#: rapidly *worse*, because a ring grown about its own bone axis stops being
#: convex once it is grown far enough and the parity test through a self-folded
#: ring is no longer meaningful.  1.34 scored worse than no flare at all.
HEM_FLARE = 1.10


def _legs(surface: Surface, rig: Rig, kind: str, *, thickness: float,
          sides: int) -> None:
    for side in ("l", "r"):
        rings = _leg_tube(rig, side, kind, thickness=thickness, sides=sides,
                          taper_end=HEM_FLARE)
        surface.loft(rings, MATERIAL_BASE, cap_start=True, cap_end=True)


# --------------------------------------------------------------------------
# Feature helpers
# --------------------------------------------------------------------------

def _band(surface: Surface, rig: Rig, side: str, kind: str, *, low: float,
          high: float, thickness: float, material: int = MATERIAL_TRIM,
          rows: int = 3, sides: int = 22) -> None:
    """A ring around one leg, between two fractions of the chain."""
    measure = LEG_MEASURE_L if side == "l" else LEG_MEASURE_R
    rings = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=rows,
                       sides=sides, thickness=thickness, start=low, end=high,
                       floor=.040, bones=measure)
    surface.loft(rings, material)


def _plate(surface: Surface, rig: Rig, side: str, kind: str, *, low: float,
           high: float, thickness: float, material: int = MATERIAL_TRIM,
           arc: float = .55, rows: int = 4, sides: int = 22,
           face: float = 0.0) -> None:
    """A shell over part of the leg's circumference - a cop, a splint, a plate.

    ``arc`` is the fraction of the way round it wraps and ``face`` rotates it,
    0 being the front of the leg.  Open at both edges by design: a kneecop is a
    lid over the tube underneath, not a closed volume of its own.
    """
    measure = LEG_MEASURE_L if side == "l" else LEG_MEASURE_R
    rings = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=rows,
                       sides=sides, thickness=thickness, start=low, end=high,
                       floor=.040, bones=measure)
    keep = max(3, int(round(sides * arc)))
    start = int(round(sides * face)) - keep // 2
    sliced = [np.roll(ring, -start, axis=0)[:keep] for ring in rings]
    surface.loft(sliced, material, closed=False)


def _hanging(surface: Surface, rig: Rig, kind: str, *, low: float, high: float,
             thickness: float, material: int = MATERIAL_BASE, rows: int = 8,
             sides: int = 26, taper: float = 1.0, ragged: bool = False,
             seed: int = 0) -> None:
    """A panel hung from the waist: kilt, tabard, sarong, longcoat skirt.

    Lofted from the hip measurement rather than the leg, so it falls clear of
    both legs instead of following one of them, and left open at the bottom
    because a hem is an edge, not a lid.
    """
    rings = torso_rings(rig, low, high, rows=rows, sides=sides,
                        thickness=thickness, flare_low=.055 * taper,
                        floor=.062, bones=HIP_BONES + ["thigh_l", "thigh_r"])
    if ragged:
        rng = np.random.default_rng(seed)
        bite = rng.uniform(.0, .055, size=sides)
        drop = rings[0][:, 1].copy()
        rings[0][:, 1] = drop - bite
    surface.loft(rings, material, v_start=1.0, v_end=0.0)


def _studs(surface: Surface, rig: Rig, side: str, *, travel: float,
           count: int, radius: float, material: int = MATERIAL_DETAIL,
           kind: str = "legs") -> None:
    """Small bosses set around the leg: rivets, teeth, gems, bone, discs."""
    measure = LEG_MEASURE_L if side == "l" else LEG_MEASURE_R
    ring = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=1,
                      sides=max(count * 2, 8), thickness=.014, start=travel,
                      end=travel + .004, floor=.040, bones=measure)[0]
    step = max(1, len(ring) // count)
    for index in range(0, len(ring), step):
        surface.sphere(tuple(ring[index]), (radius, radius, radius),
                       material, rings=5, sides=6)


def _pouch(surface: Surface, rig: Rig, side: str, *, travel: float,
           size: tuple[float, float, float],
           material: int = MATERIAL_TRIM) -> None:
    measure = LEG_MEASURE_L if side == "l" else LEG_MEASURE_R
    ring = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=1, sides=16,
                      thickness=.020, start=travel, end=travel + .004,
                      floor=.040, bones=measure)[0]
    outer = int(len(ring) * (.25 if side == "l" else .75))
    surface.box(tuple(ring[outer]), size, material, bevel=.008)


def _strands(surface: Surface, rig: Rig, side: str, *, travel: float,
             count: int, length: float, thickness: float,
             material: int = MATERIAL_TRIM) -> None:
    """Fringe, tassels and hanging teeth: thin tapered strands."""
    measure = LEG_MEASURE_L if side == "l" else LEG_MEASURE_R
    ring = limb_rings(rig, [f"thigh_{side}", f"calf_{side}"], rows=1,
                      sides=max(count, 8), thickness=.012, start=travel,
                      end=travel + .004, floor=.040, bones=measure)[0]
    step = max(1, len(ring) // count)
    for index in range(0, len(ring), step):
        top = ring[index]
        surface.tube([top, top + np.array([0., -length, 0.])],
                     [thickness, thickness * .35], material, sides=5)


# --------------------------------------------------------------------------
# The feature vocabulary
# --------------------------------------------------------------------------

#: Every feature is a call against the helpers above.  Grouping them this way
#: rather than writing thirty-five separate builders keeps the vocabulary
#: honest: a splint and a bark plank are the same shell at different widths,
#: and pretending otherwise would be thirty-five chances to get the winding
#: wrong instead of five.
#:
#: Fractions are along the thigh+calf chain, 0 at the hip and 1 at the ankle,
#: so a feature stays where it belongs when the chain changes length.

#: (low, high, thickness, material, arc, face) - shells over part of the leg.
PLATES = {
    "tasset":  (.030, .250, .034, MATERIAL_TRIM,   .62, .00),
    "kneecop": (.440, .580, .030, MATERIAL_TRIM,   .50, .00),
    "greave":  (.640, .880, .026, MATERIAL_TRIM,   .58, .00),
    "splint":  (.120, .430, .028, MATERIAL_TRIM,   .40, .00),
    "bark":    (.080, .420, .036, MATERIAL_TRIM,   .70, .00),
    "leaf":    (.100, .560, .030, MATERIAL_TRIM,   .78, .00),
    "stone":   (.070, .440, .038, MATERIAL_TRIM,   .72, .00),
    "quilt":   (.060, .440, .024, MATERIAL_DETAIL, .84, .00),
    "scale":   (.180, .700, .022, MATERIAL_DETAIL, .86, .00),
    "mail":    (.060, .820, .018, MATERIAL_DETAIL, .92, .00),
    "patch":   (.380, .560, .020, MATERIAL_DETAIL, .38, .00),
    "flare":   (.800, .900, .046, MATERIAL_TRIM,   .96, .00),
    "fringe":  (.150, .330, .020, MATERIAL_DETAIL, .34, .25),
}

#: (low, high, thickness, material) - rings all the way round.
BANDS = {
    "strap":    (.230, .270, .026, MATERIAL_TRIM),
    "buckle":   (.500, .530, .028, MATERIAL_DETAIL),
    "lace":     (.660, .700, .022, MATERIAL_DETAIL),
    "cord":     (.880, .910, .022, MATERIAL_TRIM),
    "wrap":     (.720, .790, .030, MATERIAL_TRIM),
    "trim":     (.855, .885, .026, MATERIAL_TRIM),
    "stitch":   (.300, .320, .018, MATERIAL_DETAIL),
    "coil":     (.560, .620, .032, MATERIAL_TRIM),
    "cuffroll": (.870, .920, .038, MATERIAL_BASE),
    "fur":      (.820, .900, .052, MATERIAL_DETAIL),
    "sash":     (.040, .140, .044, MATERIAL_TRIM),
}

#: (travel, count, radius, material) - small bosses.
BOSSES = {
    "stud": (.320, 10, .012, MATERIAL_DETAIL),
    "gem":  (.240,  6, .020, MATERIAL_TRIM),
    "bone": (.190,  7, .017, MATERIAL_DETAIL),
    "disc": (.150,  4, .034, MATERIAL_TRIM),
    "tooth": (.210, 8, .014, MATERIAL_DETAIL),
    "vine": (.520, 12, .011, MATERIAL_TRIM),
    "bead": (.360,  9, .013, MATERIAL_TRIM),
}

#: (travel, count, length, thickness) - hanging strands.
STRANDS = {
    "tassel": (.180, 6, .105, .010),
}

#: (travel, size) - a bag on the outside of the thigh.
POUCHES = {
    "pouch": (.260, (.085, .105, .055)),
}

#: Panels hung from the waist.  (low, high, thickness, ragged)
PANELS = {
    "panel":  (.560, WAIST_TOP - .030, .030, False),
    "tatter": (.420, WAIST_TOP - .034, .026, True),
}


def _clamp(low: float, high: float, kind: str) -> tuple[float, float]:
    """Keep a feature above the hem it shares a garment with.

    The hem is a contract with the footwear brief, not a stylistic choice, and
    the fractions in the tables below are written once for all three kinds.
    `flare` runs to .90 of the chain, which is past a rigid `legs` hem at .89 -
    so `emberforge_cuisses` shipped a cuff plate hanging 13 mm below its own
    trouser, and the seam test caught it at Y .1651 against a datum of .178.
    Every feature is trimmed to the hem rather than each table being written
    out three times, because the next feature added would have the same trap.
    """
    limit = HEM[kind]
    return min(low, limit), min(high, limit)


def _apply(surface: Surface, rig: Rig, kind: str, feature: str, sides: int,
           seed: int) -> None:
    """Loft one named feature onto both legs, or once about the hips."""
    if feature in PANELS:
        low, high, thickness, ragged = PANELS[feature]
        _hanging(surface, rig, kind, low=low, high=high, thickness=thickness,
                 material=MATERIAL_BASE if feature == "panel" else MATERIAL_TRIM,
                 ragged=ragged, seed=seed, sides=sides)
        return
    for side in ("l", "r"):
        if feature in PLATES:
            low, high, thickness, material, arc, face = PLATES[feature]
            low, high = _clamp(low, high, kind)
            _plate(surface, rig, side, kind, low=low, high=high,
                   thickness=thickness, material=material, arc=arc,
                   face=face if side == "l" else 1.0 - face, sides=sides)
        elif feature in BANDS:
            low, high, thickness, material = BANDS[feature]
            low, high = _clamp(low, high, kind)
            _band(surface, rig, side, kind, low=low, high=high,
                  thickness=thickness, material=material, sides=sides)
        elif feature in BOSSES:
            travel, count, radius, material = BOSSES[feature]
            travel = _clamp(travel, travel, kind)[0]
            _studs(surface, rig, side, travel=travel, count=count,
                   radius=radius, material=material, kind=kind)
        elif feature in STRANDS:
            travel, count, length, thickness = STRANDS[feature]
            travel = _clamp(travel, travel, kind)[0]
            _strands(surface, rig, side, travel=travel, count=count,
                     length=length, thickness=thickness)
        elif feature in POUCHES:
            travel, size = POUCHES[feature]
            _pouch(surface, rig, side, travel=_clamp(travel, travel, kind)[0],
                   size=size)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

#: How far the structural leg tube stands off the body, by kind.  Rigid armour
#: is thicker because it is plate over padding, not cloth over skin.
LEG_THICKNESS = {"pants": .013, "legs": .017, "kilt": .012}


def legwear_geometry(kind: str, rig: Rig, features: tuple[str, ...] = (),
                     seed: int = 0) -> Garment:
    """One leg garment: structure first, then its features over the top."""
    if kind not in HEM:
        raise ValueError(f"not a leg garment kind: {kind}")
    surface = Surface()
    sides = _sides(len(features))
    _hip_shell(surface, rig, kind)
    _waistband(surface, rig)
    _legs(surface, rig, kind, thickness=LEG_THICKNESS[kind], sides=22)
    for index, feature in enumerate(features):
        _apply(surface, rig, kind, feature, sides, seed * 97 + index)
    return Garment(surface, "skirt" if kind == "kilt" else "legs")
