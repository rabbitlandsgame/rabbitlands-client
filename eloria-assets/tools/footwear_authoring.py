#!/usr/bin/env python3
"""Sixty-four boots, authored from concept art, built on the measured body.

Footwear used to be one lofted shell dressed as twenty catalogue entries.  This
builds each design as its own mesh: a base shell measured off the real foot, and
a stack of layers - plates, straps, cuffs, wraps, reliefs, ornaments - that carry
the silhouette of the sheet it came from.

Three things here are load-bearing and none of them is decoration.

**Skin scope.**  A boot is refitted per wearer by scaling each bone about *its
own origin*, and ``calf``'s origin is the knee.  A sole vertex that inherits the
body's own heel weighting - which is 31 per cent ``calf`` - is dragged 62 mm
under the floor on an Orun.  The foot shell and its sole are therefore scoped to
the foot chain and the shaft keeps the calf, so each part of the boot is
refitted against the part of the leg it sits on.

**Ground pre-compensation.**  The runtime now scales the foot chain by the
wearer's own ankle-to-sole distance (see ``soleDrop`` in the registry), which is
what lets one sole stand on sixteen different floors.  That scale can *shrink* a
boot - the female rigs are twenty per cent shorter from ankle to sole - so the
shell is measured against each cast body's foot divided by the shrink it will
receive.  Sized to the reference foot alone it would close inside a smaller one.

**Closure.**  Every element is a closed solid.  Open sheets have no inside, so
the enclosure test cannot use them and the winding test cannot check them; a
strap that is a closed band costs a few triangles and is measurable.  Winding is
settled at the end by ``face_outward``, which flips any closed component that
encloses negative volume - the failure that once made a closed boot render as an
open-toed sandal with the foot inside it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from equipment_authoring import (
    MATERIAL_BASE, MATERIAL_DETAIL, MATERIAL_TRIM, Rig, Surface, limb_rings,
    smooth_profile)

# ---------------------------------------------------------------------------
# Skin scopes
# ---------------------------------------------------------------------------

#: Bones each scope is solved against.  ``boot_foot`` deliberately excludes the
#: calf: see the module docstring.
SKIN_SCOPES = {
    "boot_foot": ["foot_l", "foot_r", "ball_l", "ball_r"],
    "boot_shaft": ["calf_l", "calf_r", "foot_l", "foot_r"],
}
FOOT = "boot_foot"
SHAFT = "boot_shaft"

#: The shared boot/trouser datum, on the reference rig.  Expressed as a fraction
#: along ``calf`` from the knee because world Y does not transfer: the Ssarathi
#: ankle stands at Y 0.235 where the Luminous one stands at 0.087, so the same
#: seam sits about 145 mm higher up the world on a digitigrade leg.
#: These are fractions to the ring *centre*.  The datum names the cuff's top
#: *edge*, and the two differ by about 13 mm because a shaft ring is built
#: perpendicular to the calf, which is tilted: the ring centred on Y 0.320 has
#: its highest vertex at Y 0.334.  The edge is what the shipped boots measure
#: and what the trouser has to clear, so the edge is what these hold; the
#: fractions below are the centres that produce it, and ``measure_cuff`` checks
#: the result rather than trusting the arithmetic.
CUFF_DATUM_T = 0.518          # cuff top edge at world Y 0.320 on luminous_male
CUFF_FLOOR_T = 0.693          # edge Y 0.240 - the lowest an outer boot may end
ANKLE_TOP_T = 0.995           # edge Y 0.102 - the highest an inner boot may end
#: Where a shaft finishes, below the ankle and inside the foot shell.
SHAFT_ROOT_T = 1.075

#: How far the shell closes *below* the foot inside it, in metres.
#:
#: It used to stand 1.5 mm proud of the sole, on the reasoning that a boot under
#: the floor is worse than one above it.  Both are wrong: standing proud leaves
#: the bottom 1.5 mm of the foot outside the boot, which is most of the skin
#: that was showing through - eighty-eight of orun_female's hundred and
#: fifty-four exposed vertices were the underside of her foot, poking out below
#: a shell that had closed above it.  A boot's sole is under the foot in life
#: too; the acceptance limit allows 8 mm and this uses under two.
SOLE_BELOW_FOOT = .0025
SOLE_THICKNESS = .013
#: The most another body's foot may widen a section, against this body's own.
CAST_HEADROOM = 1.45
SHELL_CORNER = 2.6


def _squircle(phi: float, corner: float = SHELL_CORNER) -> tuple[float, float]:
    """Unit rounded-rectangle offsets for one angle around a shell ring.

    Higher ``corner`` is squarer.  The sole plate uses a much squarer section
    than the shell above it, because a sole is flat underneath: rounded off at
    the bottom outer corner it stepped back from the ground exactly where a
    flatter arch than the reference's stands on it, which is where the last of
    the skin was showing on every female rig.
    """
    power = 2. / corner
    across, along = math.cos(phi), math.sin(phi)
    return (math.copysign(abs(across) ** power, across),
            math.copysign(abs(along) ** power, along))


def _slab_ring(centre_x: float, middle: float, centre_z: float,
               half: float, reach: float, sides: int,
               fillet: float = .12) -> np.ndarray:
    """A rounded-rectangle cross-section for the sole plate.

    Not a squircle.  A squircle's outer edge sits well above its own lowest
    point - at the widest part of the section it has already risen four tenths
    of the way up - so a plate built that way stops three millimetres short of
    the ground exactly where it is widest, which is where a flat arch stands on
    it.  A sole is a slab: flat underneath, flat on top, and rounded only at the
    corners.
    """
    ring = np.empty((sides, 3))
    for index in range(sides):
        share = index / sides
        # Walk the perimeter of a unit rectangle rather than sweep an angle.
        corner = math.cos(2 * math.pi * share)
        rise = math.sin(2 * math.pi * share)
        scale = 1.0 / max(abs(corner), abs(rise))
        across, along = corner * scale, rise * scale
        # Ease the four corners so the loft has no knife edge to shade - but
        # lightly.  At a quarter it takes enough off the bottom outer corner to
        # put the Ssarathi's toes outside their own sole again, which is the
        # fault this whole shape exists to fix.
        soft = 1.0 - fillet * max(0.0, abs(across) + abs(along) - 1.0)
        ring[index] = (centre_x + across * half * soft,
                       middle + along * reach * soft, centre_z)
    return ring


# ---------------------------------------------------------------------------
# The foot, measured
# ---------------------------------------------------------------------------

@dataclass
class FootAnatomy:
    """Everything a boot needs to know about one foot, measured off the body."""

    side: str
    ankle: np.ndarray
    ball: np.ndarray
    toe_tip: np.ndarray
    instep: np.ndarray        # unit axis, ankle -> ball
    forward: np.ndarray       # unit axis, ball -> toe
    under_arch: np.ndarray    # down, square to the instep
    under_toe: np.ndarray     # down, square to the forward axis
    lateral: np.ndarray
    #: The ankle-to-toe direction flattened into the ground plane.  "What is
    #: underneath this point" is a plan-view question and has to be asked along
    #: a horizontal axis: the ankle-to-toe axis tilts steeply downwards, so the
    #: heel *flesh* - which lies down and back of the ankle - projects onto it
    #: at almost the same station as the ankle itself, 90 mm away from where the
    #: heel *ring* projects.  Asked along the tilted axis the heel station finds
    #: only ankle flesh, seats itself on that, and the back of the boot ends up
    #: hanging at ankle height with no heel under it at all.
    plan: np.ndarray
    arch: float
    toe_span: float
    heel_reach: float
    toe_reach: float
    ground: float
    flesh: np.ndarray


def _frame(start: np.ndarray, end: np.ndarray):
    axis = end - start
    length = float(np.linalg.norm(axis))
    axis = axis / max(length, 1e-9)
    down = np.array([0., -1., 0.])
    down = down - axis * float(down @ axis)
    if float(down @ down) < 1e-6:
        down = np.array([0., 0., -1.])
    return axis, length, down / max(np.linalg.norm(down), 1e-9)


def _foot_flesh(positions: np.ndarray, ankle: np.ndarray,
                toe_tip: np.ndarray) -> np.ndarray:
    """Body vertices belonging to one foot, scoped geometrically.

    Measured off the body rather than off the skin weights: the heel is largely
    bound to the calf, so a bone-scoped region misses exactly the part of the
    foot the back of the boot has to contain.
    """
    span = toe_tip - ankle
    length = float(np.linalg.norm(span)) or 1.0
    axis = span / length
    offsets = positions - ankle
    along = np.clip(offsets @ axis, 0.0, length)
    aside = np.linalg.norm(offsets - np.outer(along, axis), axis=1)
    same_side = np.sign(positions[:, 0]) == np.sign(ankle[0] or 1.0)
    # Cut at the ankle.  The scope above is a cylinder about the ankle-to-toe
    # axis, and a cylinder that reaches the foot also reaches the bottom of the
    # shin standing above it, which then decides how tall the shell has to be:
    # measured with the shin in, the foot shell grows a hand's breadth up the
    # leg.  The joint is the right cut for either build - it is the ankle on a
    # plantigrade leg and the hock on a digitigrade one, and in both cases
    # everything below it is foot and everything above it is not.
    below_joint = positions[:, 1] < ankle[1] + .025
    # A generous cylinder, because the cut above is what keeps the shin out.
    # At 85 mm the back of the heel fell outside it - the axis tilts steeply
    # down toward the toe, so the point of the heel stands nearly a hundred
    # millimetres off it - and flesh that is never measured is flesh the shell
    # is never sized to hold. Those nine vertices per foot were the last of the
    # skin showing through.
    return same_side & below_joint & (aside < .130)


def measure_foot(rig: Rig, side: str) -> FootAnatomy:
    ankle = rig.origin(f"foot_{side}")
    ball = rig.origin(f"ball_{side}")
    toe_tip = rig.segment(f"ball_{side}")[1]
    instep, arch, under_arch = _frame(ankle, ball)
    forward, toe_span, under_toe = _frame(ball, toe_tip)

    picked = _foot_flesh(rig.positions, ankle, toe_tip)
    flesh = rig.positions[picked]
    span = toe_tip - ankle
    length = float(np.linalg.norm(span)) or 1.0
    axis = span / length
    along = np.clip((rig.positions - ankle) @ axis, 0.0, length)

    # How far the heel actually reaches behind the ankle, measured rather than
    # assumed: a plantigrade heel runs back nearly four tenths of the arch and a
    # digitigrade one barely two.
    heel_reach = arch * .38
    rear = rig.positions[picked & (along < length * .45)]
    if len(rear) > 16:
        behind = -((rear - ankle) @ instep)
        heel_reach = float(np.clip(np.quantile(behind, .995),
                                   arch * .16, arch * .60))
    # And the same in front: toe length varies far more between races than any
    # multiple of the last joint's span predicts.
    toe_reach = toe_span * 1.18
    front = rig.positions[picked & (along > length * .5)]
    if len(front) > 16:
        ahead = (front - ball) @ forward
        toe_reach = float(np.clip(np.quantile(ahead, .995) + .020,
                                  toe_span * .8, toe_span * 2.4))
    plan = np.array([span[0], 0., span[2]])
    plan_length = float(np.linalg.norm(plan))
    plan = plan / plan_length if plan_length > 1e-6 else np.array([0., 0., 1.])
    return FootAnatomy(
        side=side, ankle=ankle, ball=ball, toe_tip=toe_tip, instep=instep,
        forward=forward, under_arch=under_arch, under_toe=under_toe,
        lateral=np.array([1., 0., 0.]), plan=plan, arch=arch, toe_span=toe_span,
        heel_reach=heel_reach, toe_reach=toe_reach,
        ground=float(flesh[:, 1].min()) if len(flesh) else 0.0, flesh=flesh)


#: How many angles a cross-section is measured at.  The ring is built at this
#: many sides too, so every vertex sits on a measurement rather than on an
#: interpolation between two of them.
SECTION_SIDES = 20


@dataclass
class Station:
    """One cross-section of the foot shell, measured off the flesh it wraps.

    ``radius`` is the distance from ``centre`` to the shell at each of
    ``SECTION_SIDES`` angles around the section, starting on the ``lateral``
    axis and turning toward ``down``.  A foot is not an ellipse: it is flat
    underneath and widest at the bottom, and a rounded section sized to its
    bounding box cuts the corners off - which is where the last of the skin was
    showing through, four to fifteen millimetres outside the shell along the
    bottom edge of the foot.
    """

    centre: np.ndarray
    down: np.ndarray
    radius: np.ndarray
    #: Half-extent across the foot of everything this section had to contain,
    #: taken before the floor trim.  The trim pulls the section's lower corners
    #: in to keep it out of the ground, and on a broader foot than the authored
    #: one that is exactly the reach the sole needed: the slab underneath is
    #: built to this instead, so what the shell gives up the sole picks up.
    plan: float = 0.0

    @property
    def width(self) -> float:
        """Half-extent across the foot."""
        sides = len(self.radius)
        return float(max(self.radius[0], self.radius[sides // 2]))

    @property
    def height(self) -> float:
        """Half-extent along ``down``."""
        sides = len(self.radius)
        return float(max(self.radius[sides // 4], self.radius[3 * sides // 4]))

    def under(self) -> float:
        """World height of the lowest point of this section."""
        return float(min(self.point(index)[1] for index in range(len(self.radius))))

    def point(self, index: int, grow: float = 0.0) -> np.ndarray:
        phi = 2 * math.pi * index / len(self.radius)
        lateral = np.array([1., 0., 0.])
        return (self.centre + (lateral * math.cos(phi) + self.down * math.sin(phi))
                * (self.radius[index] + grow))


def foot_stations(rig, foot: FootAnatomy, *, stations: int = 9,
                  girth: float = 1.0, ground_shrink: float = 1.0,
                  clearance: float = .008,
                  cast: "list[np.ndarray] | None" = None) -> list[Station]:
    """Cross-sections that wrap the foot this rig actually has.

    Rewritten 2026-08-29 for Eloria Client.  The spine used to be constructed
    from the bones - a heel point placed back along the ankle-to-ball axis, then
    seated onto whatever flesh lay under it.  Back along that axis is *up*: the
    ball sits below and in front of the ankle, so the constructed heel landed
    12 cm in the air behind the ankle bone, and the flesh search then found the
    ankle rather than the heel and seated it there.  The result was a boot with
    no heel under it at all, its sole touching the ground only from the arch
    forward.

    Each station is now measured straight off the foot: walk the flesh along
    whichever axis the foot actually runs, take the slab at each step, and size
    the ring to that slab's own extent.  That describes a plantigrade foot and a
    digitigrade one equally well, because it never assumes which way either of
    them points.

    ``cast`` is every other foot in the fit group, already carried back into
    this rig's authored space through the refit that wearer will receive.  A
    shell solved against the authored foot alone fits the authored foot alone:
    an Orun's is twelve per cent wider and a Stoneborn's sixteen, and the
    runtime's widening is one number for a whole bone rather than a shape.
    Solving against all of them at once is what makes one authored mesh
    genuinely contain fourteen different feet.

    ``ground_shrink`` survives as a knob but is 1.0 in practice: the runtime
    seats footwear on the ground by moving it rather than by resizing it, so a
    shell no longer has to be built oversize against a shrink it will never
    receive.  Measured across the cast the foot itself barely varies - every
    female foot is within four per cent of its male counterpart's width - so
    clearance alone covers the difference.
    """
    axis = foot.toe_tip - foot.ankle
    length = float(np.linalg.norm(axis)) or 1.0
    axis = axis / length
    flesh = foot.flesh
    if len(flesh) < 24:
        raise ValueError(f"foot_{foot.side}: too little flesh to measure")

    along = (flesh - foot.ankle) @ axis
    back, front = float(along.min()), float(along.max())
    # A little past the last of the flesh at each end, so the shell closes
    # around the heel and the toes rather than cutting through them.
    back -= foot.arch * .07
    front += foot.arch * .10
    window = (front - back) / (stations - 1) * .85

    seats = np.linspace(back, front, stations)
    raw = []
    for index, seat in enumerate(seats):
        share = index / (stations - 1)
        # `down` follows the segment this station belongs to: square to the
        # metatarsal behind the ball and square to the toes in front of it.
        ball_at = float((foot.ball - foot.ankle) @ axis)
        down = (foot.under_arch if seat <= ball_at else foot.under_toe)
        anchor = foot.ankle + axis * seat
        near = flesh[np.abs(along - seat) < window]
        if len(near) < 3:
            raw.append(None)
            continue
        raw.append((anchor, down, near))

    # Ends with no flesh to measure carry the nearest measured station forward,
    # tapered, rather than dropping to a constant: a tip built to a small
    # constant leaves the undersides of the toes below the sole meant to cap
    # them, which is the fault this replaces.
    measured = [index for index, value in enumerate(raw) if value is not None]
    if not measured:
        raise ValueError(f"foot_{foot.side}: no station could be measured")
    ball_at = float((foot.ball - foot.ankle) @ axis)
    for index, value in enumerate(raw):
        if value is not None:
            continue
        nearest = min(measured, key=lambda other: abs(other - index))
        anchor, down, near = raw[nearest]
        # Carry the nearest measured slab forward, drawn in toward its own
        # centre, rather than dropping to a constant: a tip built to a small
        # constant leaves the undersides of the toes below the sole meant to
        # cap them, which is the fault this replaces.
        fade = .82 ** abs(index - nearest)
        middle = near.mean(axis=0)
        moved = foot.ankle + axis * seats[index]
        raw[index] = (moved,
                      foot.under_arch if seats[index] <= ball_at else foot.under_toe,
                      middle + (near - middle) * fade + (moved - anchor))

    floor_plane = foot.ground - SOLE_BELOW_FOOT
    lateral = foot.lateral
    centres, downs = [], []
    for anchor, down, near in raw:
        offset = near - anchor
        span_l, span_d = offset @ lateral, offset @ down
        centres.append(anchor + lateral * (span_l.min() + span_l.max()) * .5
                       + down * (span_d.min() + span_d.max()) * .5)
        downs.append(down)

    # Solved against the flesh rather than padded against a guess.
    #
    # Sizing a section to the bounding box of the slab beside it leaves the
    # corners out, because a foot is not an ellipse.  Sizing it to the slab's
    # own reach at each angle is closer but still misses, three ways at once:
    # the ring is a polygon and its edges cut inside the radii at its corners,
    # the loft between two rings is a chord and cuts inside both, and smoothing
    # the profile files the sharp lobe off a heel.  Each is a couple of
    # millimetres and together they were leaving twenty vertices of foot outside
    # a shell that had measured all of them.
    #
    # So every vertex of the foot is placed against the two rings that will
    # bracket it, and both are opened far enough at the two angles that will
    # bracket it to contain it.  A convex polygon whose vertices all stand at
    # least ``r / cos(pi / sides)`` from the centre contains every point at
    # radius ``r``, so the chord is paid for rather than hoped about.
    chord = 1.0 / math.cos(math.pi / SECTION_SIDES)
    radii = [np.full(SECTION_SIDES, .006) for _ in centres]
    own_radii = [np.full(SECTION_SIDES, .006) for _ in centres]
    plan_of = np.zeros(len(centres))
    seat_of = np.array([float((centre - foot.ankle) @ axis) for centre in centres])
    solving = flesh if not cast else np.concatenate([flesh, *cast])
    own = np.zeros(len(solving), dtype=bool)
    own[:len(flesh)] = True
    for point_index, point in enumerate(solving):
        here = float((point - foot.ankle) @ axis)
        upper = int(np.searchsorted(seat_of, here))
        for index in {max(upper - 1, 0), min(upper, len(centres) - 1)}:
            offset = point - centres[index]
            across = float(offset @ lateral)
            deep = float(offset @ downs[index])
            reach = float(np.hypot(across, deep))
            if reach < 1e-6:
                continue
            angle = math.atan2(deep, across) % (2 * math.pi)
            share = angle / (2 * math.pi) * SECTION_SIDES
            downwards = max(0.0, -float(downs[index][1]) * math.sin(angle)) ** 2
            pad = clearance * (1.0 - downwards) + SOLE_BELOW_FOOT * downwards
            want = reach * chord + pad
            # The plate is sized to *this* foot only.  The shell above it grows
            # to hold every foot in the group, because it has to; the sole does
            # not, and sizing it that way put an Orun's outsized lateral offset
            # into the plate under a Luminous boot - a flange standing 30 mm
            # proud of the foot all round, which reads as a snowshoe.
            if own[point_index]:
                plan_of[index] = max(plan_of[index],
                                     abs(across) * chord + clearance)
            for corner in (int(math.floor(share)), int(math.ceil(share))):
                slot = corner % SECTION_SIDES
                radii[index][slot] = max(radii[index][slot], want)
                if own[point_index]:
                    own_radii[index][slot] = max(own_radii[index][slot], want)

    # How far another body's foot may push this shell out.
    #
    # Left unbounded the solver sizes the shell to the most awkward foot in the
    # group and the boot stops being a boot: the Orun ankle sits 26 mm inboard
    # of the reference's, so their foot reaches 105 mm to the outside of the
    # joint where the reference's reaches 72, and a shell grown to hold both
    # stands 30 mm proud of the leg it is drawn on. The anchor datum carries
    # most of that difference at runtime; this bounds what is left, and the
    # handful of vertices still outside are worth less than the silhouette.
    own_radius = [np.array(r, dtype=np.float64) for r in own_radii]
    result = []
    for centre, down, radius, mine in zip(centres, downs, radii, own_radius):
        # Only where this body actually measured something.  An angle the
        # authored foot never reaches has no own-radius to bound against, and
        # bounding it against the floor value collapsed the shell to nothing
        # there - which took the Ssarathi's own boot off their own toes.
        radius = np.asarray(radius, dtype=np.float64)
        measured_here = mine > .0061
        radius = np.where(measured_here,
                          np.minimum(radius, mine * CAST_HEADROOM), radius)
        radius = radius / ground_shrink * girth
        # Smoothed, but only ever outward: filing a heel's lobe down is exactly
        # what this whole pass exists to stop.
        radius = np.maximum(radius, np.asarray(
            smooth_profile(list(radius), .006), dtype=np.float64))
        # Trimmed at the floor per angle, not raised as a whole.  Raising a
        # section to keep it off the floor lifts it off the foot as well, which
        # left the Ssarathi's toes outside their own authored shell.  What
        # actually carries a section under the ground is lateral reach times a
        # tilted `down`: an angle that points out and slightly downward turns a
        # wide measurement into a deep one.  Trimming only the offending angles
        # cannot expose anything real, because no flesh lies below the floor to
        # begin with.
        for index in range(SECTION_SIDES):
            phi = 2 * math.pi * index / SECTION_SIDES
            fall = float(down[1]) * math.sin(phi)
            if fall >= -1e-6:
                continue
            allowed = (floor_plane - float(centre[1])) / fall
            if allowed < radius[index]:
                radius[index] = max(allowed, .004)
        result.append(Station(centre=centre, down=down, radius=radius,
                              plan=float(plan_of[len(result)])))
    return result


def station_ring(station: Station, foot: FootAnatomy, sides: int = SECTION_SIDES,
                 grow: float = 0.0) -> np.ndarray:
    """The measured cross-section, traversed so the loft faces outwards."""
    return np.array([station.point(index, grow)
                     for index in range(len(station.radius))])


def resample(stations: list[Station], foot: FootAnatomy, rows: int,
             sides: int = 20, grow: float = 0.0) -> list[np.ndarray]:
    """Interpolate the station spine into a denser ring stack."""
    if rows <= len(stations):
        return [station_ring(s, foot, sides, grow) for s in stations]
    keys = np.linspace(0., 1., len(stations))
    want = np.linspace(0., 1., rows)
    centres = np.array([s.centre for s in stations])
    downs = np.array([s.down for s in stations])
    radii = np.array([s.radius for s in stations])
    rings = []
    for travel in want:
        centre = np.array([np.interp(travel, keys, centres[:, a]) for a in range(3)])
        down = np.array([np.interp(travel, keys, downs[:, a]) for a in range(3)])
        down = down / max(float(np.linalg.norm(down)), 1e-9)
        radius = np.array([np.interp(travel, keys, radii[:, a])
                           for a in range(radii.shape[1])])
        rings.append(station_ring(Station(centre, down, radius), foot, sides, grow))
    return rings


# ---------------------------------------------------------------------------
# Closed-solid primitives
#
# Every element a design is made of is a closed solid.  An open sheet has no
# inside, so the enclosure test cannot use it and the winding test cannot check
# it; a strap that is a closed band costs a few dozen triangles and is
# measurable.  Winding is settled once at the end by ``Surface.face_outward``.
# ---------------------------------------------------------------------------

def _ring_sample(ring: np.ndarray, at: float) -> np.ndarray:
    """A point on a closed ring at a fractional index, wrapping round."""
    sides = len(ring)
    low = math.floor(at)
    share = at - low
    return ring[int(low) % sides] * (1.0 - share) + ring[int(low + 1) % sides] * share


def ring_frame(path: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A closed ring's centre and its own plane normal, by Newell's method."""
    centre = path.mean(axis=0)
    normal = np.zeros(3)
    for index in range(len(path)):
        current, following = path[index], path[(index + 1) % len(path)]
        normal += np.cross(current - centre, following - centre)
    length = float(np.linalg.norm(normal))
    return centre, (normal / length if length > 1e-12 else np.array([0., 1., 0.]))


def band(surface: Surface, path: np.ndarray, half_width: float,
         half_thickness: float, material: int, *, lift: float = 0.0,
         squash: float = 1.0) -> None:
    """A closed ring of material wrapped around a closed path.

    ``half_width`` runs along the path's own axis - the height of a strap on the
    leg - and ``half_thickness`` stands off it radially.
    """
    centre, normal = ring_frame(path)
    profiles = []
    for index in range(len(path) + 1):
        point = path[index % len(path)]
        radial = point - centre
        radial = radial - normal * float(radial @ normal)
        length = float(np.linalg.norm(radial))
        radial = radial / length if length > 1e-9 else np.array([1., 0., 0.])
        seat = point + radial * lift
        profiles.append(np.array([
            seat - radial * half_thickness - normal * half_width * squash,
            seat + radial * half_thickness - normal * half_width * squash,
            seat + radial * half_thickness + normal * half_width * squash,
            seat - radial * half_thickness + normal * half_width * squash]))
    surface.loft(profiles, material, closed=True)


def patch(surface: Surface, grid: list[np.ndarray], normals: list[np.ndarray],
          thickness: float, material: int, floor: float | None = None) -> None:
    """A closed slab standing off a patch of surface.

    Emitted as six pieces - two faces and four walls - whose border vertices
    coincide exactly, so the whole thing welds into one closed shell.  The
    pieces disagree about winding as they are laid down and ``face_outward``
    settles it afterwards.
    """
    rows = len(grid)
    if rows < 2 or len(grid[0]) < 2:
        return
    inner = [np.asarray(row, dtype=np.float64) for row in grid]
    outer = [row + np.asarray(offset, dtype=np.float64) * thickness
             for row, offset in zip(inner, normals)]
    if floor is not None:
        # A plate on the foot wraps a ring, and a ring has an underside.  Left
        # unclamped the ends of a sabaton or a toe cap follow it round and stand
        # seven millimetres through the floor before any refit has run.
        for row in inner + outer:
            np.maximum(row[:, 1], floor, out=row[:, 1])
    surface.loft(outer, material, closed=False)
    surface.loft(inner, material, closed=False)
    surface.loft([inner[0], outer[0]], material, closed=False)
    surface.loft([inner[-1], outer[-1]], material, closed=False)
    left = [np.array([row[0] for row in inner]), np.array([row[0] for row in outer])]
    right = [np.array([row[-1] for row in inner]), np.array([row[-1] for row in outer])]
    surface.loft(left, material, closed=False)
    surface.loft(right, material, closed=False)


def spur(surface: Surface, base: np.ndarray, direction: np.ndarray,
         length: float, radius: float, material: int, *, sides: int = 7,
         taper: float = .12) -> None:
    """A tapered closed spike, claw or stud."""
    axis = np.asarray(direction, dtype=np.float64)
    axis = axis / max(float(np.linalg.norm(axis)), 1e-9)
    points = [base - axis * radius * .4, base + axis * length * .5,
              base + axis * length]
    surface.tube(points, [radius, radius * .62, max(radius * taper, .0012)],
                 material, sides=sides, cap=True)


# ---------------------------------------------------------------------------
# Where a layer sits
# ---------------------------------------------------------------------------

@dataclass
class BootContext:
    """Everything a layer needs to place itself on one boot, one side."""

    rig: object
    side: str
    foot: FootAnatomy
    stations: list[Station]
    design: "BootDesign"
    surface: Surface

    def shaft_ring(self, travel: float, *, sides: int = 20,
                   thickness: float = .0) -> np.ndarray:
        """A measured ring around the calf, ``travel`` of the way from the knee."""
        rings = limb_rings(
            self.rig, [f"calf_{self.side}"], rows=1, sides=sides,
            thickness=self.design.shaft_thickness + thickness,
            start=travel, end=travel, floor=.044,
            bones=[f"calf_{self.side}", f"foot_{self.side}"])
        return rings[0]

    def foot_ring(self, travel: float, *, sides: int = 20,
                  grow: float = 0.0) -> np.ndarray:
        """A ring across the foot shell, 0 at the heel and 1 at the toe."""
        rings = resample(self.stations, self.foot, 24, sides, grow)
        index = int(round(np.clip(travel, 0., 1.) * (len(rings) - 1)))
        return rings[index]

    def arc(self, ring: np.ndarray, span: float = .55,
            facing: str = "front", count: int = 13) -> np.ndarray:
        """The front, back, outer or upper run of a ring, as a contiguous arc.

        ``top`` is what anything mounted on the foot wants.  A foot ring's
        cross-section stands upright, so its "front" is the instep only by
        accident of which way the toe points; asked for the front, a sabaton
        wrapped the *underside* and pushed nine millimetres of plate through the
        floor before any refit had run.
        """
        centre = ring.mean(axis=0)
        offsets = ring - centre
        if facing == "top":
            key = offsets[:, 1]
        elif facing == "front":
            key = offsets[:, 2]
        elif facing == "back":
            key = -offsets[:, 2]
        else:
            key = offsets[:, 0] * (1.0 if self.side == "l" else -1.0)
        order = int(np.argmax(key))
        # Always ``count`` points, whatever the span.
        #
        # Taking every ring vertex inside the span gave rows of different
        # lengths as soon as a plate tapered, and a loft needs equal rings: the
        # patch's faces and its side walls then disagreed about where its border
        # was and it shipped with thirty-two boundary edges - an open shell,
        # which the enclosure test cannot use and the winding test cannot check.
        # Sampling a fixed number of points along the span tapers the plate by
        # moving its edge rather than by dropping vertices off it.
        reach = span * len(ring) * .5
        return np.array([
            _ring_sample(ring, order + reach * (2.0 * step / (count - 1) - 1.0))
            for step in range(count)])

    def outward(self, points: np.ndarray, ring: np.ndarray,
                floor: float | None = None) -> list[np.ndarray]:
        """Unit normals standing off a ring, never pointing into the ground."""
        centre = ring.mean(axis=0)
        result = []
        for point in points:
            radial = point - centre
            radial[1] *= .25
            if floor is not None and float(point[1]) - .012 < floor:
                radial[1] = max(radial[1], 0.)
            length = float(np.linalg.norm(radial))
            result.append(radial / length if length > 1e-9
                          else np.array([0., 0., 1.]))
        return result


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Layer:
    """One element of a design, placed against the measured boot."""

    def emit(self, ctx: BootContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class Cuff(Layer):
    """The band that finishes the top of the shaft."""

    drop: float = .075
    flare: float = .010
    thickness: float = .011
    style: str = "band"
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        top = ctx.design.shaft_top
        bottom = min(top + self.drop, SHAFT_ROOT_T - .02)
        rows = 4 if self.style in {"band", "fold"} else 6
        rings = []
        for step in range(rows + 1):
            travel = top + (bottom - top) * (step / rows)
            grow = self.flare * (1.0 - step / rows) ** 1.4
            if self.style == "fold" and step <= 1:
                grow += self.flare * .8
            rings.append(ctx.shaft_ring(travel, thickness=self.thickness + grow))
        if self.style in {"scallop", "points"}:
            count = 9 if self.style == "points" else 7
            reach = .026 if self.style == "points" else .014
            for index in range(count):
                phi = 2 * math.pi * index / count
                seat = ctx.shaft_ring(top + .004, thickness=self.thickness)
                pick = seat[int(phi / (2 * math.pi) * len(seat)) % len(seat)]
                centre = seat.mean(axis=0)
                direction = pick - centre
                direction[1] = max(direction[1], 0.) + .35 * float(
                    np.linalg.norm(direction))
                spur(ctx.surface, pick, -direction if self.style == "scallop"
                     else np.array([direction[0], -abs(direction[1]) - .5,
                                    direction[2]]),
                     reach, .012, self.material, sides=6)
        elif self.style == "spike":
            for index in range(8):
                seat = ctx.shaft_ring(top + .010, thickness=self.thickness)
                pick = seat[int(index * len(seat) / 8) % len(seat)]
                centre = seat.mean(axis=0)
                spur(ctx.surface, pick, pick - centre, .030, .009,
                     self.material, sides=6)
        elif self.style == "fur":
            # Seated below the rim, not across it.  A ruff is swept along the
            # ring's own axis, so one centred on the opening stands about
            # sixteen millimetres above it - and a boot that reaches higher is a
            # boot answerable for more leg, which the shaft below it does not
            # cover.  It doubled the skin showing through on every furred design
            # in the set.
            for index, travel in enumerate((top + .024, top + .042, top + .060)):
                ruff = ctx.shaft_ring(travel, sides=14,
                                      thickness=self.thickness + .020 - index * .004)
                band(ctx.surface, ruff, .013, .013, self.material, squash=1.0)
        surface_rings = rings if self.style != "fur" else rings[:3]
        ctx.surface.loft(surface_rings, self.material, cap_start=True,
                         cap_end=True)


@dataclass(frozen=True)
class Strap(Layer):
    """A band round the shaft, with an optional buckle on the outside."""

    travel: float = .70
    width: float = .013
    thickness: float = .008
    buckle: bool = True
    material: int = MATERIAL_DETAIL

    def emit(self, ctx: BootContext) -> None:
        ring = ctx.shaft_ring(self.travel, thickness=.002)
        band(ctx.surface, ring, self.width, self.thickness, self.material)
        if not self.buckle:
            return
        outer = ctx.arc(ring, span=.06, facing="side")
        seat = outer[len(outer) // 2]
        centre = ring.mean(axis=0)
        radial = seat - centre
        radial[1] = 0.
        length = float(np.linalg.norm(radial))
        radial = radial / length if length > 1e-9 else np.array([1., 0., 0.])
        ctx.surface.box(tuple(seat + radial * .008),
                        (.020, .019, .020), MATERIAL_TRIM, bevel=.004)


@dataclass(frozen=True)
class Lames(Layer):
    """Overlapping plates down the front of the shaft, as on an armoured greave."""

    top: float = .58
    bottom: float = .95
    count: int = 4
    depth: float = .006
    span: float = .46
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        for index in range(self.count):
            head = self.top + (self.bottom - self.top) * index / self.count
            tail = self.top + (self.bottom - self.top) * (index + .70) / self.count
            grid, normals = [], []
            for travel in (head, (head + tail) * .5, tail):
                ring = ctx.shaft_ring(travel, sides=24, thickness=.003)
                arc = ctx.arc(ring, self.span)
                grid.append(arc)
                normals.append(ctx.outward(arc, ring))
            patch(ctx.surface, grid, normals, self.depth, self.material)


@dataclass(frozen=True)
class ShinPlate(Layer):
    """One raised panel running down the shaft."""

    top: float = .52
    bottom: float = 1.00
    span: float = .40
    depth: float = .013
    facing: str = "front"
    rows: int = 5
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        grid, normals = [], []
        for step in range(self.rows):
            travel = self.top + (self.bottom - self.top) * step / (self.rows - 1)
            taper = 1.0 - .35 * abs(step / (self.rows - 1) - .5)
            ring = ctx.shaft_ring(travel, sides=24, thickness=.003)
            arc = ctx.arc(ring, self.span * taper, self.facing)
            grid.append(arc)
            normals.append(ctx.outward(arc, ring))
        patch(ctx.surface, grid, normals, self.depth, self.material)


@dataclass(frozen=True)
class Sabaton(Layer):
    """Articulated plates across the instep, ending in a toe cap."""

    count: int = 4
    start: float = .30
    end: float = .92
    depth: float = .006
    span: float = .50
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        floor = ctx.foot.ground - SOLE_BELOW_FOOT
        for index in range(self.count):
            head = self.start + (self.end - self.start) * index / self.count
            tail = self.start + (self.end - self.start) * (index + .84) / self.count
            grid, normals = [], []
            for travel in (head, (head + tail) * .5, tail):
                ring = ctx.foot_ring(travel, sides=24, grow=.002)
                arc = ctx.arc(ring, self.span, facing="top")
                grid.append(arc)
                normals.append(ctx.outward(arc, ring, floor))
            patch(ctx.surface, grid, normals, self.depth, self.material, floor)


@dataclass(frozen=True)
class ToeCap(Layer):
    """A cap over the toe box: a rounded steel toe, a point, or a claw."""

    style: str = "round"
    reach: float = .22
    depth: float = .008
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        floor = ctx.foot.ground - SOLE_BELOW_FOOT
        start = 1.0 - self.reach
        grid, normals = [], []
        for step in range(4):
            travel = start + (1.0 - start) * step / 3
            ring = ctx.foot_ring(travel, sides=24, grow=.002)
            arc = ctx.arc(ring, .66, facing="top")
            grid.append(arc)
            normals.append(ctx.outward(arc, ring, floor))
        patch(ctx.surface, grid, normals, self.depth, self.material, floor)
        if self.style == "point":
            tip = ctx.stations[-1]
            spur(ctx.surface, tip.centre, ctx.foot.forward, .034, .016,
                 self.material, sides=8)
        elif self.style == "claw":
            ring = ctx.foot_ring(.97, sides=12)
            for index in (2, 6, 10):
                seat = ring[index % len(ring)]
                # Forward and level.  Angled down, a claw is the lowest thing on
                # the boot and puts eleven millimetres of it through the floor.
                direction = np.array([ctx.foot.forward[0], 0.,
                                      ctx.foot.forward[2]])
                seat = np.array([seat[0], max(float(seat[1]), floor + .010),
                                 seat[2]])
                spur(ctx.surface, seat, direction, .028, .008,
                     self.material, sides=6)


@dataclass(frozen=True)
class Sole(Layer):
    """The slab under the foot, and whatever tread or heel it carries."""

    style: str = "flat"
    thickness: float = SOLE_THICKNESS
    material: int = MATERIAL_DETAIL

    def emit(self, ctx: BootContext) -> None:
        floor = ctx.foot.ground - SOLE_BELOW_FOOT
        # A slab, not a stack of ellipses.
        #
        # Built as a lofted tube of per-station sections the sole followed the
        # shell's own curvature, which meant it pulled away from the ground
        # under the arch - and a flatter arch than the authored one then had
        # nothing under it.  That was the last of the skin showing through: a
        # dozen vertices under the midfoot of every female rig in the cast.  A
        # real sole is a slab: it spans the whole footprint, from the floor up
        # to whatever the shell above it is doing, and the arch is simply where
        # it stops touching the foot.
        # The plate does not pinch at the arch.
        #
        # Sized station by station the sole follows the foot's own waist, which
        # narrows sharply at the arch - and a flatter arch than the authored one
        # then stands on ground the plate has stepped back from.  That was the
        # last of the skin showing through: six vertices under each midfoot on
        # every female rig, whose arches touch the floor where the reference's
        # does not.  A real sole is cut to the widest part of the foot and
        # carries straight through, so this takes a running maximum along the
        # length rather than the local width.
        plan = [max(station.width, station.plan) for station in ctx.stations]
        # One width for the whole plate, drawn in only at the very toe.
        #
        # Sized station by station the plate vanishes at the arch: that station
        # sits over the waist of the foot, sometimes with too little flesh
        # beneath it to measure at all, and the section there is built to a
        # floor value.  The plate then simply is not present under the midfoot,
        # which is where a flatter arch than the reference's stands.  A shoe
        # sole is a constant-width plate that tapers at the toe and nowhere
        # else, so that is what this is.
        # Taken across the middle of the foot rather than at its very widest,
        # and padded by a welt rather than by the shell's own clearance: sized
        # to the maximum, the plate stood 30 mm proud of the foot all round and
        # read as a snowshoe.
        # A floor, not a cap.  The constant is what carries the plate through
        # the waist of the foot, where the section is narrow and a flat arch
        # still has to stand on something; where the foot is actually wider than
        # that - the ball on a plantigrade foot, the toes on a digitigrade one -
        # the plate follows it.  Taken as a cap and measured across the middle
        # stations it cut the Ssarathi's own toes out of their own sole.
        middle = plan[2:-2] if len(plan) > 5 else plan
        carried = max(middle) * .87 + .002
        spread = [max(carried, value * .96) for value in plan]
        spread[-1] = min(spread[-1], carried * .86)
        rings = []
        for station, half in zip(ctx.stations, spread):
            # Capped: under the arch the shell is high and an uncapped slab
            # follows it up, which turns the sole into a wedge.
            ceiling = min(station.under() + .014, floor + .026)
            half = half + .003
            middle = (floor + ceiling) * .5
            reach = max((ceiling - floor) * .5, .004)
            rings.append(_slab_ring(float(station.centre[0]), middle,
                                    float(station.centre[2]), half, reach,
                                    SECTION_SIDES))
        ctx.surface.loft(rings, self.material, cap_start=True, cap_end=True)
        # Everything below is tread, and tread stands on the floor rather than
        # under it.  A lug placed relative to the ring above it, or a welt hung
        # off the ring's underside, reaches wherever that ring happens to be -
        # which put twelve millimetres of boot through the ground the actor
        # stands on, on every race at once, before any refit had run.
        if self.style == "lug":
            for step in range(5):
                travel = .16 + .17 * step
                seat = ctx.foot_ring(travel, sides=10)
                low = float(seat[:, 1].min())
                if low - .010 < floor:
                    continue
                middle = seat.mean(axis=0)
                half = min(.010, (low - floor) * .5)
                ctx.surface.box((float(middle[0]), floor + half,
                                 float(middle[2])),
                                (.052, half * 2, .026), self.material,
                                bevel=min(.003, half * .5))
        elif self.style == "heel":
            heel = ctx.stations[0]
            low = heel.under()
            half = max(min(.022, (low - floor) * .5), .004)
            ctx.surface.box((float(heel.centre[0]), floor + half,
                             float(heel.centre[2])),
                            (.052, half * 2, .052), self.material,
                            bevel=min(.004, half * .5))
        elif self.style == "welt":
            # A welt is a rim around the edge of the sole, so it stands out
            # sideways from the shell rather than hanging below it.
            for travel in (.12, .40, .68, .92):
                seat = ctx.foot_ring(travel, sides=16)
                low = float(seat[:, 1].min())
                # Raised by its own half-thickness plus its stand-off, so the
                # rim's lowest point lands on the floor rather than under it.
                seat = seat + np.array([0., max(floor + .019 - low, 0.), 0.])
                band(ctx.surface, seat, .0055, .0075, self.material, lift=.004)


@dataclass(frozen=True)
class Wrap(Layer):
    """A cord or cloth strip spiralling round the shaft."""

    top: float = .55
    bottom: float = 1.00
    turns: float = 3.0
    radius: float = .0085
    material: int = MATERIAL_DETAIL

    def emit(self, ctx: BootContext) -> None:
        steps = max(24, int(self.turns * 14))
        points, radii = [], []
        for step in range(steps + 1):
            share = step / steps
            travel = self.top + (self.bottom - self.top) * share
            ring = ctx.shaft_ring(travel, sides=32, thickness=.004)
            index = int((share * self.turns) % 1.0 * len(ring))
            points.append(ring[index % len(ring)])
            radii.append(self.radius)
        ctx.surface.tube(points, radii, self.material, sides=7, cap=True)


@dataclass(frozen=True)
class Studs(Layer):
    """Rivets round a ring."""

    travel: float = .80
    count: int = 8
    radius: float = .0055
    onfoot: bool = False
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        ring = (ctx.foot_ring(self.travel, sides=24, grow=.002) if self.onfoot
                else ctx.shaft_ring(self.travel, sides=24, thickness=.004))
        centre = ring.mean(axis=0)
        for index in range(self.count):
            seat = ring[int(index * len(ring) / self.count) % len(ring)]
            radial = seat - centre
            length = float(np.linalg.norm(radial))
            radial = radial / length if length > 1e-9 else np.array([0., 0., 1.])
            ctx.surface.sphere(tuple(seat + radial * self.radius * .4),
                               (self.radius * 2, self.radius * 2, self.radius * 2),
                               self.material, rings=6, sides=8)


@dataclass(frozen=True)
class Spikes(Layer):
    """Points standing off a ring."""

    travel: float = .60
    count: int = 5
    length: float = .026
    radius: float = .008
    span: float = .5
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        ring = ctx.shaft_ring(self.travel, sides=24, thickness=.004)
        arc = ctx.arc(ring, self.span, facing="side")
        centre = ring.mean(axis=0)
        for index in range(self.count):
            seat = arc[int((index + .5) * len(arc) / self.count) % len(arc)]
            spur(ctx.surface, seat, seat - centre, self.length, self.radius,
                 self.material, sides=6)


@dataclass(frozen=True)
class Medallion(Layer):
    """A disc or boss on the outside of the shaft."""

    travel: float = .72
    radius: float = .022
    depth: float = .010
    facing: str = "side"
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        ring = ctx.shaft_ring(self.travel, sides=32, thickness=.003)
        arc = ctx.arc(ring, .10, self.facing)
        seat = arc[len(arc) // 2]
        centre = ring.mean(axis=0)
        radial = seat - centre
        radial[1] = 0.
        length = float(np.linalg.norm(radial))
        radial = radial / length if length > 1e-9 else np.array([1., 0., 0.])
        ctx.surface.tube([seat - radial * .004, seat + radial * self.depth],
                         [self.radius, self.radius * .74], self.material,
                         sides=14, cap=True)


@dataclass(frozen=True)
class Gem(Layer):
    """A faceted stone set into the shaft."""

    travel: float = .62
    size: float = .020
    facing: str = "front"
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        ring = ctx.shaft_ring(self.travel, sides=32, thickness=.004)
        arc = ctx.arc(ring, .08, self.facing)
        seat = arc[len(arc) // 2]
        centre = ring.mean(axis=0)
        radial = seat - centre
        length = float(np.linalg.norm(radial))
        radial = radial / length if length > 1e-9 else np.array([0., 0., 1.])
        ctx.surface.tube([seat - radial * .002, seat + radial * self.size * .45,
                          seat + radial * self.size],
                         [self.size * .30, self.size * .62, .0015],
                         self.material, sides=6, cap=True)


@dataclass(frozen=True)
class Tassels(Layer):
    """Cords hanging from a ring."""

    travel: float = .62
    count: int = 3
    length: float = .055
    radius: float = .006
    material: int = MATERIAL_DETAIL

    def emit(self, ctx: BootContext) -> None:
        ring = ctx.shaft_ring(self.travel, sides=24, thickness=.006)
        arc = ctx.arc(ring, .22, facing="side")
        for index in range(self.count):
            seat = arc[int((index + .5) * len(arc) / self.count) % len(arc)]
            drop = np.array([0., -1., .12])
            ctx.surface.tube(
                [seat, seat + drop * self.length * .55, seat + drop * self.length],
                [self.radius, self.radius * .8, self.radius * 1.3],
                self.material, sides=6, cap=True)


@dataclass(frozen=True)
class Relief(Layer):
    """Raised line-work on the shaft: branches, scrollwork, runes, flame."""

    top: float = .56
    bottom: float = .98
    motif: str = "scroll"
    radius: float = .0055
    strands: int = 3
    facing: str = "front"
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        for strand in range(self.strands):
            phase = strand / max(self.strands, 1)
            points, radii = [], []
            steps = 14
            for step in range(steps + 1):
                share = step / steps
                travel = self.top + (self.bottom - self.top) * share
                ring = ctx.shaft_ring(travel, sides=32, thickness=.004)
                arc = ctx.arc(ring, .52, self.facing)
                if self.motif == "branches":
                    wander = .5 + .42 * math.sin((share * 3.1 + phase * 6.3))
                elif self.motif == "runes":
                    wander = .5 + .30 * (1 if int(share * 6 + phase * 3) % 2 else -1)
                elif self.motif == "flame":
                    wander = .5 + .34 * math.sin(share * 5.0 + phase * 2.1) * (1 - share)
                else:  # scroll
                    wander = .5 + .38 * math.sin(share * 6.3 + phase * 2.1)
                points.append(arc[int(np.clip(wander, 0., .999) * len(arc))])
                taper = 1.0 - .45 * abs(share - .5) * 2
                radii.append(max(self.radius * taper, .0016))
            ctx.surface.tube(points, radii, self.material, sides=6, cap=True)


@dataclass(frozen=True)
class Scales(Layer):
    """Overlapping leaves or scales up the shaft."""

    top: float = .55
    bottom: float = .98
    rows: int = 4
    around: int = 6
    size: float = .020
    depth: float = .007
    material: int = MATERIAL_TRIM

    def emit(self, ctx: BootContext) -> None:
        for row in range(self.rows):
            travel = self.top + (self.bottom - self.top) * row / max(self.rows - 1, 1)
            ring = ctx.shaft_ring(travel, sides=self.around * 3, thickness=.003)
            centre = ring.mean(axis=0)
            for index in range(self.around):
                offset = (row % 2) * .5
                seat = ring[int((index + offset) * len(ring) / self.around) % len(ring)]
                radial = seat - centre
                length = float(np.linalg.norm(radial))
                radial = radial / length if length > 1e-9 else np.array([0., 0., 1.])
                ctx.surface.tube(
                    [seat - radial * .002, seat + radial * self.depth,
                     seat + radial * self.depth * .5 + np.array([0., -self.size, 0.])],
                    [self.size * .55, self.size * .48, .0018],
                    self.material, sides=6, cap=True)


# Which part of the boot each layer belongs to, and therefore which bones it is
# skinned against.  Anything on the foot is bound to the foot chain so the
# runtime's ground scale reaches it; anything on the shaft keeps the calf.
_FOOT_LAYERS = (Sabaton, ToeCap, Sole)


def layer_scope(layer: "Layer") -> str:
    if isinstance(layer, Studs) and layer.onfoot:
        return FOOT
    return FOOT if isinstance(layer, _FOOT_LAYERS) else SHAFT


# ---------------------------------------------------------------------------
# A design
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BootDesign:
    """One boot from one cell of one concept sheet."""

    slug: str
    label: str
    sheet: int
    cell: tuple
    finish: str
    base: tuple
    accent: tuple
    #: Where the shaft finishes, as a fraction along ``calf`` from the knee.
    #: World Y does not transfer between rigs; this does.
    shaft_top: float = CUFF_DATUM_T
    #: ``outer`` - the trouser tucks into this boot, which is the default and
    #: needs the shaft above ``CUFF_FLOOR_T``.  ``inner`` - an ankle boot the
    #: trouser falls over, which needs it below ``ANKLE_TOP_T``.
    layering: str = "outer"
    shaft_thickness: float = .026
    shaft_flare: float = 1.0
    foot_girth: float = 1.0
    sole: str = "flat"
    layers: tuple = ()

    def __post_init__(self) -> None:
        if self.layering == "outer" and self.shaft_top > CUFF_FLOOR_T:
            raise ValueError(
                f"{self.slug}: an outer boot's shaft top must sit at or above "
                f"t={CUFF_FLOOR_T} (world Y 0.240 on the reference rig); "
                f"this one is t={self.shaft_top}")
        if self.layering == "inner" and self.shaft_top < ANKLE_TOP_T:
            raise ValueError(
                f"{self.slug}: an inner boot's shaft top must sit at or below "
                f"t={ANKLE_TOP_T} (world Y 0.102); this one is t={self.shaft_top}")


def shaft_rings(ctx: BootContext, rows: int = 9) -> list:
    """The shaft, from its top down to inside the foot shell."""
    design = ctx.design
    rings = []
    for step in range(rows + 1):
        share = step / rows
        travel = design.shaft_top + (SHAFT_ROOT_T - design.shaft_top) * share
        # A shaft that is widest at the top reads as a riding boot; one that is
        # even reads as a greave.  Either way it may never be tighter than the
        # trouser it has to swallow.
        grow = (design.shaft_flare - 1.0) * (1.0 - share) * design.shaft_thickness
        # The rim is where a shaft is thinnest and the leg is widest: the calf
        # is still swelling toward the knee at the top of a tall boot, and a
        # shaft cut to the measured radius left a ring of skin showing in the
        # last centimetre under its own opening - on the female rigs, whose
        # calves are proportionally fuller there than the authored one's.  The
        # top third is let out, tapering, so the opening is the widest part of
        # the shaft rather than the narrowest.
        grow += .007 * max(0.0, 1.0 - share * 3.0) ** .7
        rings.append(ctx.shaft_ring(travel, sides=22, thickness=grow))
    # The opening is cut level, not square to the bone.
    #
    # A ring built perpendicular to the calf is tilted, so its rim spans about
    # twenty millimetres of height: the boot's highest point is one side of the
    # opening and the leg comes out of the other, which is where the last of the
    # skin was showing on every rig with a fuller calf than the reference's.  It
    # is also simply what a boot looks like - the cuffs on all eight sheets are
    # level - and it gives the trouser a horizontal seam to meet rather than an
    # ellipse.  The flattening is faded over the top few rows so the shaft does
    # not kink where it starts.
    level = float(max(point[1] for point in rings[0]))
    fade = min(4, len(rings) - 1)
    for row in range(fade):
        weight = (1.0 - row / fade) ** 1.5
        for index, point in enumerate(rings[row]):
            rings[row][index][1] = point[1] * (1.0 - weight) + level * weight
        level -= .004
    return rings


def build_boot(design: BootDesign, rig, *, ground_shrink: float = 1.0,
               cast: dict | None = None) -> Surface:
    """One design, built on one rig, both feet.

    ``cast`` maps a side to the other feet in the fit group, already carried
    back into this rig's space by ``group_feet``.
    """
    surface = Surface()
    for side in ("l", "r"):
        foot = measure_foot(rig, side)
        stations = foot_stations(rig, foot, girth=design.foot_girth,
                                 ground_shrink=ground_shrink,
                                 cast=(cast or {}).get(side))
        ctx = BootContext(rig=rig, side=side, foot=foot, stations=stations,
                          design=design, surface=surface)
        with surface.scoped(FOOT):
            surface.loft(resample(stations, foot, 17, SECTION_SIDES), MATERIAL_BASE,
                         cap_start=True, cap_end=True)
            Sole(style=design.sole).emit(ctx)
        with surface.scoped(SHAFT):
            surface.loft(shaft_rings(ctx), MATERIAL_BASE,
                         cap_start=True, cap_end=True)
        for layer in design.layers:
            with surface.scoped(layer_scope(layer)):
                layer.emit(ctx)
    # Settled once, at the end, rather than reasoned about in fifteen generators.
    surface.face_outward()
    return surface


def measure_cuff(design: "BootDesign", rig) -> dict:
    """Where a built boot's cuff actually finishes, both ways round.

    World Y is what the trouser brief pins the seam in and only means anything
    on the reference rig; the fraction along ``calf`` is what transfers to a
    digitigrade leg, where the same seam sits about 145 mm higher up the world.
    """
    surface = build_boot(design, rig)
    top = max(float(points[:, 1].max())
              for points, _n, _uv, indices in surface.arrays() if len(indices))
    knee = float(rig.origin("calf_l")[1])
    ankle = float(rig.origin("foot_l")[1])
    return {"slug": design.slug, "layering": design.layering,
            "cuffTopY": round(top, 4),
            "cuffTopT": round((knee - top) / max(knee - ankle, 1e-9), 4),
            "authoredT": design.shaft_top}


# ---------------------------------------------------------------------------
# The rest of the fit group, seen from the authoring rig
# ---------------------------------------------------------------------------

# ``group_feet`` used to pre-size the shell against every wearer in the group by
# carrying their feet back into this rig's space.  The anchor datum does that
# job properly now - it moves the boot onto each foot instead of making one boot
# big enough for all of them - so the pre-sizing is gone and what remains is in
# ``build_footwear.preimage``, which is only ever asked about vertices that are
# actually still outside.


