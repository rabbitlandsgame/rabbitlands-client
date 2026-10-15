#!/usr/bin/env python3
"""Fit a generated equipment mesh onto the shared body rig and skin it.

Added 2026-09-01 for Eloria Client.

``equipment_authoring`` lofts garments from the measured body, so every torso
piece it makes is already a shell around the wearer and already skinned.  A
mesh that arrives from an image-to-3D generator is none of those things: it is
a static island, normalised into a unit cube, with no joints, no weights and no
relationship to the body it is supposed to be worn on.  The client will not
attach it -- ``attach: "skinned"`` needs ``JOINTS_0``/``WEIGHTS_0`` against the
77-joint rig -- and even as a rigid prop it would be roughly four times the
size of the actor.

This closes that gap, and the useful discovery is how little it takes.  A
generated armour piece is already garment-shaped -- the cuirass this was
written against arrives with a collar, a laced front, spiked pauldrons, a belt
and a tasset skirt, all in the right relation to each other.  It does not need
to be conformed to the body.  It needs to be put in the right place at the
right size and bound to the skeleton:

  seat    uniform scale and translate, matching the piece's height to the body
          region it covers.  Uniform because the proportions are the design,
          and the design is the reason to import the mesh at all.
  repose  carry each limb of the garment from the pose the concept was drawn
          in -- arms dropped, feet a stance apart -- onto the rig's rest pose.
          Found with the ray caster from the limb's own bone axis, never from
          percentiles of the garment's point cloud; see ``repose``.  Without
          this a sleeved piece is wearable but wrong everywhere that moves:
          its sleeves inherit chest weights from wherever they hang, and in
          the running client they neither follow the arm nor stay on the
          chest.
  skin    ``Rig.weights_for``, which hands each vertex the blend of the body
          surface nearest it.  That is what keeps cloth and skin bending as
          one; solving from bone distance instead lets a knee come through a
          trouser the moment it bends.

Two deforming fits are kept behind ``--fit`` for pieces that need rescuing, and
both are worse than leaving the mesh alone.  ``push`` moves every buried vertex
out to the measured skin, which is what a lofted open shell wants -- run on an
imported *solid* it drives the inner surface through the outer one and returns
a shredded coat with the pauldrons flung off sideways.  ``grow`` scales the
whole piece up until the body is inside it, which keeps the design intact but
has no reliable stopping rule: parity enclosure never passes, because a
generated garment is dozens of disjoint solids and no single closed component
holds a torso, and the radial fallback compares the body's shoulders against
the garment's collar at the top slice and oversizes everything.  Reach for
them only with a render open.

  python conform_equipment.py in.glb -o out.glb --kind cuirass
  python conform_equipment.py sourcedir -o outdir --kind boots --race luminous_male
  python conform_equipment.py in.glb -o out.glb --kind legs --report fit.json

The baked texture the generator produced is carried through as the base colour
map, rather than the palette-and-detail-map materials the authored pieces use:
the art is the reason to import the mesh at all.

Exits non-zero if a piece could not be fitted.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from pathlib import Path

import numpy as np

import equipment_authoring as ea
import garment_fit as gf

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
RACES = CLIENT / "assets/actors/native/races"

# All source-derived canonical body faces, including the closed scalp.
# Attribute accessors are gathered once by load_rig and face buffers unioned.
BODY_MESH = ea.BODY_SURFACES

#: How each region's silhouette is measured, mirroring what the lofted shells
#: do rather than inventing a second rule.
#:
#: The bones here are NOT the region's skinning bones.  ``GARMENT_SKIN["torso"]``
#: carries the upper arms, because a vertex at the shoulder of a cuirass should
#: be weighted to the arm that moves it -- but measuring the body against that
#: set reports the half-width out to the elbows, and a chest piece pushed out to
#: that is a barrel with the arms inside it.  ``torso_rings`` measures against
#: ``TORSO_BONES``, which stops at the clavicles, and so does this.
#:
#: ``vertical`` measures about the world upright through the body centre, the
#: axis ``torso_rings`` uses.  ``sides`` splits the mesh at x=0 and measures
#: each half against its own limb, because trousers are two tubes and a right
#: leg sized against the left one is sized against thin air.
MEASURE = {
    "torso": {"mode": "vertical", "bones": ea.TORSO_BONES},
    "skirt": {"mode": "vertical",
              "bones": ea.TORSO_BONES + ["thigh_l", "thigh_r"]},
    "legs": {"mode": "sides", "axis": ("thigh_%s", "calf_%s"),
             "bones": ("thigh_%s", "calf_%s")},
    "boots": {"mode": "sides", "axis": ("calf_%s", "ball_%s"),
              "bones": ("calf_%s", "foot_%s", "ball_%s")},
}

#: The (height, girth) factors the most recent seat() call applied, for the
#: torso's axis equalisation to read back.
LAST_SEAT_FACTORS = (1.0, 1.0)

#: How far outside the skin a fitted vertex is parked, in metres.  The authored
#: shells sit at 11 mm; matching that keeps an imported piece from reading as
#: baggier than the set it joins.
CLEARANCE = 0.011

#: How much wider than the body's own box a seated piece is allowed to sit, as
#: a fraction.  Six per cent is a garment worn over a body rather than sprayed
#: onto one, and it is what keeps the shell clear of the skin once a limb bends.
SLACK = 0.06

#: Over what height a joined garment's inward shift is ramped out, in metres,
#: measured down from the crotch.  Long enough that the seat is not sheared,
#: short enough that the leg is on its limb by the time the thigh is clear of
#: the hip shell.
SEAT_RAMP = 0.25

#: And how far out from the midline the same shift is faded in, in metres.
#: Wide enough that the inseam is not sheared, narrow enough that the tube
#: itself still travels: the thigh's inner wall sits about 40 mm off centre.
SEAT_MIDLINE = 0.04

#: Bounds on that draw-in.  A piece is never taken below three quarters -- past
#: that the design is being restyled rather than fitted, and a pauldron that was
#: drawn proud stops reading as one.  Letting out is capped nearer to 1: a piece
#: that has to grow much at all was misread, and a render will show it.
TIGHTEST, LOOSEST = 0.75, 1.15

#: Where each kind of garment sits on the reference body, as world Y at
#: ``fit_scale`` 1.  The torso pair is the module's own hem and collar; the limb
#: pairs are measured off the authored ranger set, which is the reference these
#: pieces are joining -- amberwood_ranger_legs spans 0.184..1.088 and
#: amberwood_ranger_boots -0.013..0.320.  A region with no entry falls back to
#: the extent of the body it is weighted against.
SPAN = {
    "torso": (ea.TORSO_HEM, ea.COLLAR_TOP),
    "legs": (0.184, 1.088),
    "boots": (-0.013, 0.320),
}


#: Headwear and the rest of the socket-attached kinds.  A socket piece is a
#: plain static mesh -- ``amberwood_ranger_hood.glb`` is one node with no skin,
#: exactly the shape a generated mesh already arrives in -- so nothing has to be
#: bound for these.  What they need is the other thing a generated mesh lacks:
#: to be the size of a head, and to be authored about the socket rather than
#: about the world, because the runtime hangs them off a bone and the mesh has
#: to be drawn where that bone will put it.
#: ``lift`` is a fraction of head height added above the median-centred
#: placement, to seat headgear high like a hat rather than centred like a
#: bucket.  Helms ride up a third of the head so the brow line clears the
#: eyes; circlets and bands ride higher still to sit at the hairline.
SOCKET_SHRINK = 0.8

SOCKET_KIND = {
    # The setbacks were measured against a head that had only ever grown
    # offline: with the phantom joint scale gone and headgear sized to the
    # real skull, the old 0.12 pushed every helm five centimetres past the
    # back of the head.  These land the median piece on the skull's own
    # centre, measured in the client.
    # ``covers`` says the piece is meant to enclose the skull: a helm or a
    # hat that leaves the crown in the air is wrong, where a circlet that
    # does is a circlet.
    "helm": {"part": 3, "bones": ["Head"], "clearance": .010, "lift": 0.12,
             "setback": 0.070, "covers": True},
    "hood": {"part": 3, "bones": ["Head"], "clearance": .014, "lift": 0.06,
             "setback": 0.070, "covers": True},
    "circlet": {"part": 3, "bones": ["Head"], "clearance": .008, "lift": 0.18,
                "setback": 0.060},
}


#: Weapons and shields.  Unlike headwear these are not sized to anything on the
#: body -- a sword is as long as a sword regardless of who holds it -- so each
#: class carries its own length in metres and how much of it hangs below the
#: grip.  Both numbers are read off the authored props rather than invented:
#: ranger_leafblade spans -0.143..+0.785 (0.93 long, 15 per cent below the
#: hand), glasswarden_staff -0.480..+1.139 (1.62, 30 per cent), and
#: amberwood_longbow -0.621..+0.621, which is a bow held at its middle.
#:
#: Shields are the same shape of record with ``below`` at a half, because a
#: shield is centred on the socket: amberwood_roundshield is 0.49 x 0.49 about
#: its own origin and glasswarden_shield 0.43 x 0.70.
PROP_KIND = {
    "dagger": {"flip": True, "part": 0, "length": 0.42, "below": .16},
    "sword": {"flip": True, "part": 0, "length": 0.93, "below": .15},
    "greatsword": {"flip": True, "part": 0, "length": 1.36, "below": .18},
    "axe": {"part": 0, "length": 0.86, "below": .18},
    "greataxe": {"part": 0, "length": 1.24, "below": .24},
    "mace": {"part": 0, "length": 0.78, "below": .18},
    "maul": {"part": 0, "length": 1.22, "below": .25},
    "spear": {"part": 0, "length": 1.79, "below": .29},
    "polearm": {"part": 0, "length": 2.02, "below": .30},
    "staff": {"part": 0, "length": 1.62, "below": .30},
    "bow": {"part": 0, "length": 1.24, "below": .50},
    "crossbow": {"part": 0, "length": 0.76, "below": .45},
    "thrown": {"part": 0, "length": 0.36, "below": .50},
    "wand": {"part": 0, "length": 0.44, "below": .22},
    "fist": {"part": 0, "length": 0.32, "below": .50},
    "whip": {"part": 0, "length": 1.18, "below": .20},
    "shield": {"part": 1, "length": 0.49, "below": .50},
    "greatshield": {"part": 1, "length": 0.70, "below": .50},
}


#: How much of a prop's length counts as "the part the hand closes on", as a
#: fraction either side of the grip.  Wide enough that a thin haft still lands
#: enough vertices to measure, narrow enough that a guard or an axe head does
#: not reach into it.
GRIP_BAND = .05

#: Widened until the band holds at least this many vertices, so a haft that is
#: an eight-sided tube of two rings is still measured rather than missed.
GRIP_BAND_MINIMUM = 24

#: And never past this, at which point the piece has no distinguishable grip
#: and the whole thing is the best answer available.
GRIP_BAND_LIMIT = .25


def _grip_centre(points: np.ndarray, axis: int, spec: dict) -> float:
    """Where the hand closes, across the prop, on one axis.

    The socket holds a prop by its grip, so it is the grip that has to sit on
    the socket -- not the middle of the piece.  For a sword the two are the
    same and this changes nothing, but a sickle, a saber or a scythe carries a
    curved head far out to one side, and centring the whole bounding box moves
    the haft out from under the hand by as much as the head hangs out: the
    reported symptom is a weapon riding beside the fist rather than in it.

    Measured as the middle of the band's extent rather than its centre of
    mass, which matters for a ring: a chakram's grip band is two arcs at
    opposite edges, whose average vertex lies on either one of them but whose
    extent is centred on the hole where the hand goes.
    """
    band = GRIP_BAND * spec["length"]
    while True:
        near = points[np.abs(points[:, 1]) <= band]
        if len(near) >= GRIP_BAND_MINIMUM or band >= GRIP_BAND_LIMIT * spec["length"]:
            break
        band *= 1.6
    if len(near) == 0:
        near = points
    return float(near[:, axis].max() + near[:, axis].min()) / 2.


def seat_prop(surface: "Imported", kind: str, flip: bool = False,
              roll: bool = False,
              grip: tuple[float, float, float] | None = None) -> None:
    """Stand a generated prop up along +Y and put its grip on the socket.

    A generated weapon arrives in whatever frame the drawing implied, boxed
    into a unit cube.  The authored props are all built the same way -- the
    long axis is Y, the grip is the origin, and the blade runs up from it --
    because the socket's own rotation is what lays the weapon into the hand.
    So the mesh is turned to that frame rather than measured against a body.

    The turn is a permutation of axes, not a fitted rotation: longest to Y,
    shortest to Z, middle to X.  A permutation can mirror, which would turn
    every asymmetric hilt inside out, so the handedness is put back when it
    does.

    ``flip`` turns the piece end for end, and the turn is baked into the mesh
    that is written rather than compensated for at the socket, so every prop
    that ships holds to one convention: business end at +Y, grip at the origin.

    ``roll`` turns it a half turn about that same long axis, which is the one
    thing end-for-end cannot fix: a curved head faces the way it was drawn, and
    the drawing settles which side of the haft the edge falls on.  It is a
    rotation rather than the mirror ``flip`` performs, so an asymmetric hilt
    keeps its handedness.  Baked into the mesh for the same reason as the flip
    -- the socket is shared by every prop in a hand, so nothing that is true of
    one piece belongs there.

    Across the other two axes a held prop is centred on its *grip* rather than
    on its bounding box, which for a sword is the same thing and for a curved
    head is not: see ``_grip_centre``.

    ``grip`` names an explicit point in source-mesh coordinates when a prop's
    handle cannot be inferred, such as a bar beside a returning chain. It
    follows the mesh's axis conversion and scale and becomes the origin.

    It is needed because the concept art does not hold to one.  Hafted weapons
    are drawn head up -- an axe, a spear, a maul, a halberd all arrive the
    right way round -- but a sword is drawn hanging point down, so it arrives
    pommel up and the hand closes on the blade.  Nothing in the mesh separates
    the two cases: a guard is the widest part of a sword and sits low, an axe
    head is the widest part of an axe and sits high.  So it is a property of
    the class, defaulted per kind here and overridable per item, and it is
    settled by looking at a render.
    """
    spec = PROP_KIND[kind]
    points = np.array(surface.positions, dtype=np.float64)
    normals = np.array(surface.normals, dtype=np.float64)
    if grip is not None:
        points -= np.asarray(grip, dtype=np.float64)

    extent = points.max(axis=0) - points.min(axis=0)
    order = np.argsort(extent)                   # shortest, middle, longest
    perm = [int(order[1]), int(order[2]), int(order[0])]
    points, normals = points[:, perm], normals[:, perm]
    if np.linalg.det(np.eye(3)[:, perm]) < 0:
        points[:, 0] *= -1.
        normals[:, 0] *= -1.
    # Exclusive: the caller's flag means "this piece differs from its class",
    # so it can turn a piece the class leaves alone and leave alone a piece the
    # class turns.  An OR could only ever add turns, and the void glass
    # greatblade needs the other direction -- it arrives blade up where the
    # rest of its class arrives blade down.
    if bool(flip) != bool(spec.get("flip", False)):
        points[:, 1] *= -1.
        normals[:, 1] *= -1.
    if roll:
        points[:, ::2] *= -1.
        normals[:, ::2] *= -1.

    span = float(points[:, 1].max() - points[:, 1].min())
    points *= spec["length"] / max(span, 1e-9)
    if grip is None:
        points[:, 1] -= points[:, 1].min() + spec["below"] * spec["length"]
        # Shields are strapped across their middle; weapons use the grip band.
        for axis in (0, 2):
            points[:, axis] -= (
                (points[:, axis].max() + points[:, axis].min()) / 2.
                if spec["part"] == 1 else _grip_centre(points, axis, spec))

    surface.positions = points
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    surface.normals = normals / np.where(lengths < 1e-9, 1., lengths)


class Imported:
    """A ``Surface``-shaped view of a mesh that came from a file.

    ``build_equipment_piece`` takes a caller-supplied surface -- the footwear
    catalogue already does that -- and only needs three things from it, so this
    supplies exactly those rather than pretending to be the full builder.
    """

    def __init__(self, positions, normals, uvs, indices):
        self.positions = np.asarray(positions, dtype=np.float64)
        self.normals = np.asarray(normals, dtype=np.float64)
        self.uvs = np.asarray(uvs, dtype=np.float64)
        self.indices = np.asarray(indices, dtype=np.uint32).reshape(-1)
        self.pins = [[], [], []]

    def scope_array(self, material: int, count: int) -> np.ndarray:
        # One scope for the whole piece: an imported mesh carries no record of
        # which part of it is a sole and which is a shaft.
        return np.asarray([""] * count, dtype=object)

    def arrays(self):
        empty = (np.zeros((0, 3), "float32"), np.zeros((0, 3), "float32"),
                 np.zeros((0, 2), "float32"), np.zeros(0, "uint32"))
        return [(self.positions, self.normals, self.uvs, self.indices),
                empty, empty]


def read_source(path: Path) -> tuple[Imported, bytes | None]:
    """Positions, normals, UVs and indices of a GLB, plus its base colour PNG."""
    document, binary = ea.read_glb(path)
    matrices = ea.global_matrices(document)
    positions, normals, uvs, indices = [], [], [], []
    base = 0
    for index, node in enumerate(document.get("nodes", [])):
        if "mesh" not in node:
            continue
        matrix = matrices[index]
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            attributes = primitive["attributes"]
            points = ea.accessor_array(document, binary, attributes["POSITION"])
            points = points @ matrix[:3, :3].T + matrix[:3, 3]
            if "NORMAL" in attributes:
                normal = ea.accessor_array(document, binary, attributes["NORMAL"])
                normal = normal @ np.linalg.inv(matrix[:3, :3]).T
            else:
                normal = np.tile([0., 1., 0.], (len(points), 1))
            if "TEXCOORD_0" in attributes:
                uv = ea.accessor_array(document, binary, attributes["TEXCOORD_0"])
            else:
                uv = np.zeros((len(points), 2))
            triangles = ea.accessor_array(
                document, binary, primitive["indices"]).reshape(-1)
            positions.append(np.asarray(points, dtype=np.float64))
            normals.append(np.asarray(normal, dtype=np.float64))
            uvs.append(np.asarray(uv, dtype=np.float64)[:, :2])
            indices.append(np.asarray(triangles, dtype=np.int64) + base)
            base += len(points)
    if not positions:
        raise ValueError(f"no mesh in {path.name}")

    png = None
    images = document.get("images", [])
    if images:
        if "bufferView" in images[0]:
            view = document["bufferViews"][images[0]["bufferView"]]
            start = view.get("byteOffset", 0)
            png = bytes(binary[start:start + view["byteLength"]])
        else:
            png = (path.parent / images[0]["uri"]).read_bytes()

    return Imported(np.vstack(positions), np.vstack(normals),
                    np.vstack(uvs), np.concatenate(indices)), png


def measure_bones(region: str, side: str = "l") -> list[str]:
    spec = MEASURE[region]
    if spec["mode"] == "vertical":
        return list(spec["bones"])
    return [name % side for name in spec["bones"]]


def region_points(rig: ea.Rig, region: str) -> np.ndarray:
    """The body this region is sized against -- both limbs, for a limb region."""
    spec = MEASURE[region]
    if spec["mode"] == "vertical":
        return rig._region(measure_bones(region))
    return np.vstack([rig._region(measure_bones(region, side))
                      for side in ("l", "r")])


def cast(origin: np.ndarray, direction: np.ndarray,
         verts: np.ndarray) -> tuple[float, int]:
    """Nearest forward hit along a ray, and how many times it crosses at all.

    ``garment_fit._crossings`` answers the parity question for many origins at
    once and throws the distances away; this is the other half of it -- one
    origin, and the distance to the first surface it meets.  Same
    Moller-Trumbore arrangement and the same epsilons, so the two agree about
    what counts as a hit.

    The crossing count comes back with it because it is the check that the ray
    started somewhere meaningful: an origin inside a closed shell crosses it an
    odd number of times, and a measurement taken from outside the garment would
    otherwise report the outer surface as though it were the lining.
    """
    corner = verts[:, 0]
    edge1 = verts[:, 1] - corner
    edge2 = verts[:, 2] - corner
    pvec = np.cross(direction, edge2)
    det = np.einsum("ij,ij->i", edge1, pvec)
    live = np.abs(det) > 1e-12
    if not live.any():
        return math.inf, 0
    corner, edge1, edge2 = corner[live], edge1[live], edge2[live]
    inv = 1.0 / det[live]
    tvec = origin - corner
    u = np.einsum("mj,mj->m", tvec, pvec[live]) * inv
    qvec = np.cross(tvec, edge1)
    v = (qvec @ direction) * inv
    distance = np.einsum("mj,mj->m", qvec, edge2) * inv
    hit = (u >= 0.) & (v >= 0.) & (u + v <= 1.) & (distance > 1e-7)
    if not hit.any():
        return math.inf, 0
    return float(distance[hit].min()), int(hit.sum())


def hug_profile(shell: np.ndarray, skin: np.ndarray, axis: np.ndarray,
                clearance: float = CLEARANCE, rows: int = 12,
                sectors: int = 12,
                verts: np.ndarray | None = None
                ) -> tuple[np.ndarray, np.ndarray]:
    """How much to take the piece in or let it out, height by height.

    One factor for the whole garment cannot serve a waist and an ankle at the
    same time: the trouser that is half again too wide at the cuff is barely
    clear of the thigh, and a single number either pinches the thigh or leaves
    the cuff flapping.  So each height band gets its own, measured where the
    band actually is, and a vertex takes the factor interpolated at its height.

    Within a band the rule is the same one a single factor used: in each
    angular sector the garment has surface in, its innermost surface has to
    clear the furthest skin.  Bands are smoothed along the height afterwards,
    because a profile that steps between neighbouring bands puts a crease
    around the leg.
    """
    low, high = float(skin[:, 1].min()), float(skin[:, 1].max())
    centres = low + (high - low) * (np.arange(rows) + .5) / rows
    factors = np.ones(rows)
    for row in range(rows):
        band_lo = low + (high - low) * row / rows
        band_hi = low + (high - low) * (row + 1) / rows
        in_skin = skin[(skin[:, 1] >= band_lo) & (skin[:, 1] < band_hi)]
        if len(in_skin) < 3:
            factors[row] = np.nan          # no skin here to be answerable for
            continue
        skin_a = np.arctan2(in_skin[:, 2] - axis[1], in_skin[:, 0] - axis[0])
        skin_r = np.linalg.norm(in_skin[:, [0, 2]] - axis, axis=1)
        height = float((band_lo + band_hi) / 2.)
        origin = np.array([axis[0], height, axis[1]])
        # Only the triangles this band could contain, so each ray is cast at a
        # few hundred rather than a few thousand.
        near = verts[(verts[:, :, 1].min(axis=1) <= band_hi + .02)
                     & (verts[:, :, 1].max(axis=1) >= band_lo - .02)]
        if not len(near):
            factors[row] = np.nan
            continue
        want = 1.0
        measured = 0
        for sector in range(sectors):
            angle = 2 * np.pi * (sector + .5) / sectors
            direction = np.array([math.cos(angle), 0., math.sin(angle)])
            inner, crossings = cast(origin, direction, near)
            # Even means the ray started outside this garment, so the surface
            # it met is the outside of it and says nothing about the lining.
            if not np.isfinite(inner) or crossings % 2 == 0:
                continue
            lo = angle - np.pi / sectors
            here = (np.mod(skin_a - lo, 2 * np.pi) < 2 * np.pi / sectors)
            if here.sum() < 2:
                continue
            outer = float(np.percentile(skin_r[here], 92.))
            want = max(want, (outer + clearance) / max(inner, 1e-6))
            measured += 1
        factors[row] = want if measured else np.nan
    if np.isnan(factors).all():
        return centres, np.ones(rows)
    # Carry the nearest measured band into the ones that had nothing in them,
    # so a cuff below the last skin keeps the profile of the leg above it.
    good = ~np.isnan(factors)
    factors = np.interp(centres, centres[good], factors[good])
    smoothed = factors.copy()
    for _ in range(2):
        smoothed = np.convolve(np.pad(smoothed, 1, mode="edge"),
                               [1 / 3., 1 / 3., 1 / 3.], mode="valid")
    return centres, np.clip(smoothed, TIGHTEST, LOOSEST)


def hug_factor(points: np.ndarray, rig: ea.Rig, region: str,
               clearance: float = CLEARANCE, rows: int = 10,
               sectors: int = 12) -> float:
    """Smallest horizontal scale that still keeps the skin inside the garment.

    Measured against the garment's *innermost* surface in each direction, not
    against its bounding box.  The box is set by whatever sticks out furthest --
    a knee pad, a strap, a pauldron -- and on this legwear it reads half again
    too wide while the trouser tube itself is barely clear of the thigh.  Taking
    the piece in by that ratio drags the tube inside the leg and the body walks
    out through the front of its own trousers.

    So each height band is cut into sectors, and in every sector that the
    garment actually has surface in, the nearest garment vertex has to stay
    outside the furthest skin vertex.  Sectors it has no surface in are its
    openings -- a boot's collar, a sleeve's cuff -- and nothing can be said
    about those from here.
    """
    groups = []
    if MEASURE[region]["mode"] == "vertical":
        groups.append((points, rig._region(measure_bones(region))))
    else:
        for side in ("l", "r"):
            own = points[:, 0] >= 0 if side == "l" else points[:, 0] < 0
            groups.append((points[own], rig._region(measure_bones(region, side))))

    needed = 0.0
    for shell, skin in groups:
        if len(shell) < 8 or len(skin) < 8:
            continue
        # About this group's own upright: for a pair, each leg answers to the
        # limb it is worn on rather than to the midline between them.
        axis = np.array([float(np.median(skin[:, 0])), float(np.median(skin[:, 2]))])
        low, high = float(skin[:, 1].min()), float(skin[:, 1].max())
        for row in range(rows):
            band_lo = low + (high - low) * row / rows
            band_hi = low + (high - low) * (row + 1) / rows
            in_skin = skin[(skin[:, 1] >= band_lo) & (skin[:, 1] < band_hi)]
            in_shell = shell[(shell[:, 1] >= band_lo) & (shell[:, 1] < band_hi)]
            if len(in_skin) < 3 or len(in_shell) < 3:
                continue
            skin_a = np.arctan2(in_skin[:, 2] - axis[1], in_skin[:, 0] - axis[0])
            shell_a = np.arctan2(in_shell[:, 2] - axis[1], in_shell[:, 0] - axis[0])
            skin_r = np.linalg.norm(in_skin[:, [0, 2]] - axis, axis=1)
            shell_r = np.linalg.norm(in_shell[:, [0, 2]] - axis, axis=1)
            for sector in range(sectors):
                lo = -np.pi + 2 * np.pi * sector / sectors
                hi = -np.pi + 2 * np.pi * (sector + 1) / sectors
                here_skin = (skin_a >= lo) & (skin_a < hi)
                here_shell = (shell_a >= lo) & (shell_a < hi)
                if here_skin.sum() < 2 or here_shell.sum() < 2:
                    continue
                inner = float(np.percentile(shell_r[here_shell], 12.))
                outer = float(np.percentile(skin_r[here_skin], 92.))
                if inner > 1e-6:
                    needed = max(needed, (outer + clearance) / inner)
    if needed <= 0.:
        return 1.0
    return float(np.clip(needed, TIGHTEST, LOOSEST))


def lateral_profile(skin: np.ndarray, pivot: np.ndarray,
                    verts: np.ndarray, rows: int = 12
                    ) -> tuple[np.ndarray, np.ndarray]:
    """How far each height of one limb's garment misses that limb by.

    The fault a girth scale cannot touch.  Seated on height alone, this legwear
    puts each trouser leg 80 mm outboard of the thigh inside it: cast a ray at
    mid-thigh and the outboard side has 190 mm of room while the inboard wall
    is at 47 mm, well inside the 80 mm leg.  Scaling the band cannot mend that
    -- widening to clear the inboard side doubles an outboard gap that was
    already too big.  The garment is not the wrong size, it is in the wrong
    place, and the answer is to move it.

    Measured band by band and applied by interpolation rather than as one rigid
    shift, so a joined garment does not tear: the offset dies away over the
    height where the two legs merge into a seat, because up there the garment
    is a single tube already centred on the body and the measurement says so.
    """
    low, high = float(skin[:, 1].min()), float(skin[:, 1].max())
    centres = low + (high - low) * (np.arange(rows) + .5) / rows
    offsets = np.full((rows, 2), np.nan)
    for row in range(rows):
        band_lo = low + (high - low) * row / rows
        band_hi = low + (high - low) * (row + 1) / rows
        in_skin = skin[(skin[:, 1] >= band_lo) & (skin[:, 1] < band_hi)]
        if len(in_skin) < 4:
            continue
        height = float((band_lo + band_hi) / 2.)
        origin = np.array([pivot[0], height, pivot[1]])
        near = verts[(verts[:, :, 1].min(axis=1) <= band_hi + .02)
                     & (verts[:, :, 1].max(axis=1) >= band_lo - .02)]
        if not len(near):
            continue
        # Where the wall is on each side, found by ray rather than inferred
        # from the spread of vertices.  That distinction is the whole point:
        # a percentile of vertex position is pulled outboard by every strap and
        # knee pad hanging off the design, so a centre computed that way sits
        # outboard of the real garment and the correction overshoots inboard --
        # which is a trouser pulled tight against the leg it should hang from.
        # A ray finds the body-facing surface and ignores the decoration.
        for index, axis in enumerate((0, 2)):
            reach = []
            for sign in (1., -1.):
                direction = np.zeros(3)
                direction[axis] = sign
                distance, crossings = cast(origin, direction, near)
                reach.append(distance if (np.isfinite(distance)
                                          and crossings % 2 == 1) else None)
            if reach[0] is None or reach[1] is None:
                continue
            # Centre the lining on the limb: half the difference between the
            # two walls is how far off it currently sits.
            offsets[row, index] = -(reach[0] - reach[1]) / 2.
    # Per column: a band can find its walls on one axis and not the other -- a
    # boot at ankle height is bounded left and right and open front to back --
    # and a mask taken from one axis carries the other's gaps through the
    # interpolation as NaN, which reaches the skin weights as a bad cast.
    for index in (0, 1):
        good = ~np.isnan(offsets[:, index])
        if not good.any():
            offsets[:, index] = 0.
            continue
        offsets[:, index] = np.interp(centres, centres[good],
                                      offsets[good, index])
    for _ in range(3):
        offsets = np.stack([np.convolve(np.pad(offsets[:, i], 1, mode="edge"),
                                        [1 / 3., 1 / 3., 1 / 3.], mode="valid")
                            for i in (0, 1)], axis=1)
    return centres, offsets


def group_masks(points: np.ndarray, region: str):
    """Which vertices answer to which body, as (mask, measuring bones) pairs."""
    if MEASURE[region]["mode"] == "vertical":
        return [(np.ones(len(points), dtype=bool), measure_bones(region))]
    return [(points[:, 0] >= 0, measure_bones(region, "l")),
            (points[:, 0] < 0, measure_bones(region, "r"))]


def halves_are_separate(points: np.ndarray, triangles: np.ndarray) -> bool:
    """True when nothing joins the left of the piece to the right.

    A pair of boots is two solids and each may be moved onto its own foot.
    Trousers are one, and moving half of them opens a hole.
    """
    if triangles is None or not len(triangles):
        return False
    spanning = 0
    for shell in gf.components(points, triangles):
        used = shell.points[np.unique(shell.triangles)]
        if not len(used):
            continue
        # A component with material on both sides of the midline is the thing
        # that joins them, so the piece is one garment and cannot be split.
        if used[:, 0].min() < -.02 and used[:, 0].max() > .02:
            spanning += 1
    return spanning == 0


def nearer_limb(points: np.ndarray, rig: ea.Rig, region: str) -> np.ndarray:
    """Which limb of a pair each vertex belongs to.  True is the left one.

    Splitting a two-tube garment at x = 0 is right for most of it and wrong
    exactly where it matters.  At the knee the tubes are at their closest, so
    the inner wall of one leg crosses the midline and is counted as part of the
    other; the seat then shifts a leg that is partly its neighbour, and the slim
    measures the width of one.  Both come out different for the two legs of a
    design whose own halves match, and a player sees one thigh thicker than the
    other.  Distance to the limb's own axis has no seam down the middle for
    geometry to fall through.
    """
    spec = MEASURE.get(region, {})
    if spec.get("mode") != "sides":
        return points[:, 0] >= 0
    reach = []
    for side in ("l", "r"):
        start = rig.origin(spec["axis"][0] % side)
        end = rig.origin(spec["axis"][1] % side)
        axis = end - start
        length = float(np.linalg.norm(axis))
        if length < 1e-6:
            return points[:, 0] >= 0
        axis = axis / length
        offset = points - start
        along = np.clip(offset @ axis, 0.0, length)[:, None]
        reach.append(np.linalg.norm(offset - along * axis, axis=1))
    return reach[0] <= reach[1]


def seat(points: np.ndarray, rig: ea.Rig, region: str,
         triangles: np.ndarray | None = None,
         taper: bool = False,
         span: tuple[float, float] | None = None,
         girth: float | None = None) -> np.ndarray:
    """Uniform scale and translate so the piece occupies the garment's span.

    Sized to where the garment goes, not to the whole region it is weighted
    against.  ``torso`` reaches the pelvis, but a cuirass hangs from the hem at
    ``TORSO_HEM`` -- seated against the region it would be stretched a third
    again too tall and worn as a dress.
    """
    body = region_points(rig, region)
    # A caller may name the span itself.  The region's own is right for a piece
    # drawn over the whole of it, and wrong for one that was deliberately cut
    # short: a trouser trimmed at the boot line covers the waist to the boot's
    # rim, and seated against the region it would be stretched back down over
    # the ankle it was cut away from, putting its knee where the calf goes.
    span = span if span is not None else SPAN.get(region)
    # Every garment is anchored to the span the authored set uses, because
    # where a piece ends is load-bearing on both axes.  On the limbs the legs
    # region runs down through the foot bones, and a trouser stretched to fill
    # it hems on the floor past the boot it tucks into.  On the torso the
    # region reaches the pelvis, and a cuirass stretched to fill it hangs 26 cm
    # below an authored one, over the hips and into the legs slot: nearly half
    # its vertices come out weighted to `pelvis` where an authored chest piece
    # is weighted to the spine, so it rides the hips instead of the chest.
    if span is not None:
        low, high = (value * rig.fit_scale for value in span)
    else:
        low, high = float(body[:, 1].min()), float(body[:, 1].max())

    extent = points.max(axis=0) - points.min(axis=0)
    # Height is the honest axis to scale on: a piece drawn front-on is as tall
    # as what it covers, while its depth is whatever the generator inferred
    # from the single view it was given.
    scale = (high - low) / max(float(extent[1]), 1e-9)

    # Girth is scaled separately from height, and only for the limb garments.
    # One uniform number cannot serve both: a trouser tall enough to reach the
    # floor is wide enough to hang off the leg, and one cut to hem at 0.184 for
    # the boot to swallow is 18 per cent narrower with it and disappears inside
    # the thigh.  Height answers to the authored span because the seam tests
    # measure where a hem lands; girth answers to the body region, which is
    # what put the trousers around the legs in the first place.  Vertical
    # against horizontal keeps the plan view of the design intact -- the piece
    # is made longer or shorter, never skewed.
    #
    # This factor is measured for the TRUNK, and the trunk is the only part of
    # a torso piece it is right for.  Seating a cuirass isotropically was tried
    # -- the arithmetic is seductive, since this design's span across its
    # hanging arms lands within a millimetre of the body's own -- and it fails
    # on the part that matters: the generated trunk is drawn slender, 60 per
    # cent of the body's width at the chest, and worn at its drawn proportions
    # the body stands outside its own breastplate.  At the region ratio the
    # trunk measures 0.89-0.97 of the body, which is what a garment should.
    # What the ratio is wrong for is the sleeves and pauldrons, which are not
    # fitted to a trunk; `_unsquash_limbs` gives it back to them once the
    # repose has said which vertices those are.
    if girth is None:
        girth = scale
        if span is not None:
            body_span = float(body[:, 1].max()) - float(body[:, 1].min())
            girth = body_span / max(float(extent[1]), 1e-9)
    global LAST_SEAT_FACTORS
    LAST_SEAT_FACTORS = (scale, girth)

    seated = (points - (points.max(axis=0) + points.min(axis=0)) / 2.)
    seated[:, 1] *= scale
    seated[:, 0] *= girth
    seated[:, 2] *= girth
    centre = (body.max(axis=0) + body.min(axis=0)) / 2.
    seated[:, 0] += centre[0]
    seated[:, 2] += centre[2]
    seated[:, 1] += (low + high) / 2.

    # Then sit each half of a pair on the limb it is worn on.  Sized on height
    # alone the trouser legs seat 80 mm outboard of the thighs and the boots 60
    # mm, because the generator draws a wider stance than the rig stands in, and
    # that splay is what the shins graze their way out through.
    #
    # Only when the halves are separate solids.  A rigid shift of one leg of a
    # joined garment tears it at the crotch, and the alternative -- taking the
    # whole piece in about the midline until the splay closes -- was measured
    # and is worse: the bounding box it would be scaled by is set by whatever
    # sticks out furthest, so on this legwear (knee pads, straps) it reads half
    # again too wide while the tube is barely clear of the thigh, and drawing it
    # in by that ratio pulls the trousers inside the leg.
    # Put each half of a pair over the limb it is worn on.  Rigid where the
    # halves are separate solids; ramped where they are one shell, which is
    # what most of the generated legwear is.
    #
    # Skipping a joined garment entirely -- which is what this did -- leaves it
    # standing exactly as far outboard as the note above measures, and a player
    # sees it at once: equipping the legs bows the character's stance out where
    # the bare body stood straight.  But the two legs of a trouser are only
    # joined ABOVE the crotch, so a shift that has died to nothing by the time
    # it reaches that line moves each leg onto its limb without opening the
    # seat.  The hips keep the width they were drawn with, which is right --
    # hips are wide -- and only the legs come in.
    if MEASURE[region]["mode"] == "sides":
        rigid = halves_are_separate(seated, triangles)
        crotch = float(rig.origin(measure_bones(region, "l")[0])[1])
        left = nearer_limb(seated, rig, region)
        for side in ("l", "r"):
            own = left if side == "l" else ~left
            if own.sum() < 8:
                continue
            limb = rig._region(measure_bones(region, side))
            # Measured from the part that is going to move: on a joined
            # garment the seat and its belt sit far outboard of the leg and
            # would drag the aim with them.
            block = own if rigid else own & (seated[:, 1] < crotch)
            if block.sum() < 8:
                continue
            half = seated[block]
            # Two ramps, and the lateral one is what keeps the garment whole.
            # Moving a side rigidly moves everything on it, so any triangle
            # that reaches across the middle -- an inseam, a crotch plate --
            # has its two ends dragged in opposite directions and is pulled
            # apart: measured over the set, a rigid shift healed four pieces
            # and tore thirteen.  Fading the shift out to nothing AT the
            # midline instead means the two sides agree where they meet, so
            # nothing is torn; the tube is drawn in from outside rather than
            # slid across.
            ramp = (np.ones(int(own.sum())) if rigid else
                    np.clip((crotch - seated[own, 1]) / SEAT_RAMP, 0., 1.)
                    * np.clip(np.abs(seated[own, 0]) / SEAT_MIDLINE, 0., 1.))
            for axis in (0, 2):
                shift = ((limb[:, axis].max() + limb[:, axis].min()) / 2.
                         - (half[:, axis].max() + half[:, axis].min()) / 2.)
                seated[own, axis] += shift * ramp

    # Per-height placement and girth.  Both off by default; see the note above
    # `lateral_profile` for why the measurement is not trustworthy yet.
    if taper:
        for own, bones in group_masks(seated, region):
            if own.sum() < 8:
                continue
            skin = rig._region(bones)
            pivot = np.array([float(np.median(skin[:, 0])),
                              float(np.median(skin[:, 2]))])
            heights, offsets = lateral_profile(skin, pivot,
                                               seated[triangles])
            block = seated[own]
            for index, axis in enumerate((0, 2)):
                block[:, axis] += np.interp(block[:, 1], heights,
                                            offsets[:, index])
            seated[own] = block

    # Girth, band by band -- off unless asked for.  The idea is right and is
    # what the runtime itself does through `bodyGirth`: one factor cannot serve
    # a waist and an ankle, so each height should get its own.  With the piece
    # centred the ray cast finds a real lining to measure against, but the two
    # sides of a band still disagree by more than one scale can express, so it
    # stays opt-in until it is measured against a fuller set of designs.
    if taper:
        for own, bones in group_masks(seated, region):
            if own.sum() < 8:
                continue
            skin = rig._region(bones)
            pivot = np.array([float(np.median(skin[:, 0])),
                              float(np.median(skin[:, 2]))])
            heights, factors = hug_profile(
                seated[own], skin, pivot, verts=seated[triangles])
            scale = np.interp(seated[own, 1], heights, factors)
            block = seated[own]
            for index, axis in enumerate((0, 2)):
                block[:, axis] = ((block[:, axis] - pivot[index]) * scale
                                  + pivot[index])
            seated[own] = block
    return seated


#: Which limbs a generated piece may arrive posed around, and how far.  A
#: concept sheet draws its figure at ease -- arms dropped toward an A-pose,
#: feet a stance apart -- and the generator models the garment exactly as
#: drawn, so a sleeved cuirass arrives with its sleeves 50-60 degrees below the
#: rig's T-pose arms and legwear arrives splayed wider than the rig stands.
#: Seating cannot fix that: it is a rotation, not a size or a place.  Worn
#: as-is, the sleeves inherit whatever body surface happens to be nearest their
#: hanging position -- chest and lats -- and the moment the idle clip drops the
#: arms, the sleeve neither follows the arm nor stays on the chest.  That is
#: the "pauldrons hovering beside the upper arms" defect: the authored pose
#: showing through, not the runtime retarget.
#:
#: Per region: (pivot bone per side, how many degrees of drop/splay to search).
#: Arms only ever drop from the T and legs only ever splay outward, because
#: that is the whole space of at-ease figures; searching the other way just
#: gives noise somewhere to land.
REPOSE = {
    # 88, not the A-pose's 60: some sheets drop the arms nearly straight down,
    # and a sweep that stops short reads a 84-degree sleeve as no sleeve.
    "torso": (("upperarm_l", 88), ("upperarm_r", 88)),
    "legs": (("thigh_l", 25), ("thigh_r", 25)),
}

#: How far from its joint a shell may reach and still be a cap rather than a
#: sleeve, in metres.  A pauldron covers the shoulder crest and stops; a sleeve
#: goes down the arm.  On the legendary hero cuirass the caps end 0.17 m out and
#: the sleeves reach 0.36 and 0.49, so the line is not finely balanced.
CAP_REACH = 0.22

#: Bones a torso garment may weight beyond the region's own set.  The region
#: stops at the upper arms because a lofted piece never reaches further, but a
#: generated jacket ships full sleeves; once those lie along the arm they need
#: the forearm to bend with, or the cuff rides through the body at the first
#: elbow bend.
REPOSE_SKIN = {
    "torso": ["lowerarm_l", "lowerarm_r"],
}

#: What counts as the limb being inside the garment: the fraction of radial
#: rays, cast outward from the posed bone axis, that meet garment surface
#: within ``REPOSE_REACH`` metres.  A sleeve is a tube and surrounds its axis,
#: so an enclosed sample answers 0.75-1.0; a hip fauld hanging beside the axis
#: answers a third or less.
REPOSE_ENCLOSED = 0.55
REPOSE_REACH = 0.15


def _limb_axis_enclosure(origin: np.ndarray, axis: np.ndarray,
                         verts: np.ndarray, sectors: int = 8) -> float:
    """How surrounded one point of a limb axis is by garment surface."""
    seed = (np.array([0., 0., 1.]) if abs(axis[2]) < 0.9
            else np.array([1., 0., 0.]))
    u = np.cross(axis, seed)
    u /= max(np.linalg.norm(u), 1e-9)
    v = np.cross(axis, u)
    hits = 0
    for sector in range(sectors):
        angle = 2.0 * math.pi * (sector + 0.5) / sectors
        direction = math.cos(angle) * u + math.sin(angle) * v
        distance, _ = cast(origin, direction, verts)
        if distance <= REPOSE_REACH:
            hits += 1
    return hits / float(sectors)


def _frontal_turn(points: np.ndarray, pivot: np.ndarray,
                  angle: np.ndarray | float) -> np.ndarray:
    """Rotate points about the world-Z line through ``pivot``, per point."""
    turned = points.copy()
    cos = np.cos(angle)
    sin = np.sin(angle)
    x = points[:, 0] - pivot[0]
    y = points[:, 1] - pivot[1]
    turned[:, 0] = pivot[0] + cos * x - sin * y
    turned[:, 1] = pivot[1] + sin * x + cos * y
    return turned


def _keep_to_own_side(points: np.ndarray, pivot: np.ndarray, angle: float,
                      turn: np.ndarray, step: float = math.radians(4.0),
                      margin: float = 0.004) -> float:
    """Back a limb's turn off until it stops swinging across the midline.

    The pose is chosen from how well the garment encloses the limb axis, which
    says nothing about where the far end of the limb ends up.  On an arm that
    is harmless -- the shoulders are far enough apart, and a sleeve that falls
    across the chest is a drape rather than a fault -- which is why only
    ``legs`` asks for this.  On a leg it is not: the hip sits 114 mm off centre
    and the hem a further 700 mm down, so every degree of turn walks the hem
    12 mm inward and at 12 degrees it arrives on the other side of the body,
    through the leg it is paired with.  The result is a sheet of triangles
    stretched across the gap between the knees -- a garment that is inside out
    about the midline, not merely mis-posed.

    So the angle is reduced in the steps the search itself used until the limb
    it turns stays on its own side.  A pose the search never considered is not
    substituted; this only ever gives back one of its own candidates, and it
    is a no-op for every piece whose chosen pose was already physical.
    """
    limb = turn > 0.5
    if not limb.any() or abs(pivot[0]) < 1e-9:
        return angle
    side = math.copysign(1.0, pivot[0])
    while abs(angle) > 1e-9:
        moved = _frontal_turn(points[limb], pivot, -angle)
        if (moved[:, 0] * side >= -margin).all():
            return angle
        angle -= math.copysign(min(step, abs(angle)), angle)
    return 0.0


def _limb_bones(rig: ea.Rig, root: str) -> set[str]:
    """The chain that rides a pivot: the bone and everything below it."""
    names = {root}
    grew = True
    while grew:
        grew = False
        for child, parent in rig.parent.items():
            if parent in names and child not in names:
                names.add(child)
                grew = True
    return names


def _weld(points: np.ndarray, triangles: np.ndarray
          ) -> tuple[np.ndarray, np.ndarray, int]:
    """Vertices welded by position, so the graph sees solids, not UV islands.

    A generated mesh splits vertices along every texture seam, which leaves
    each little patch its own island: an edge graph over the raw indices calls
    a single sleeve four hundred components.  Coincident positions are one
    point of the same solid, whatever the UVs did.
    """
    keys = np.round(points * 1e5).astype(np.int64)
    _, canon, inverse = np.unique(keys, axis=0, return_index=True,
                                  return_inverse=True)
    edges = np.sort(inverse[triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)],
                    axis=1)
    edges = np.unique(edges[edges[:, 0] != edges[:, 1]], axis=0)
    return inverse, edges, len(canon)


def _graph_smooth(values: np.ndarray, edges: np.ndarray,
                  rounds: int = 8) -> np.ndarray:
    """Average a per-vertex signal over the mesh graph."""
    degree = np.zeros(len(values))
    np.add.at(degree, edges[:, 0], 1.0)
    np.add.at(degree, edges[:, 1], 1.0)
    degree = np.maximum(degree, 1.0)
    smoothed = values.astype(np.float64).copy()
    for _ in range(rounds):
        pooled = np.zeros(len(values))
        np.add.at(pooled, edges[:, 0], smoothed[edges[:, 1]])
        np.add.at(pooled, edges[:, 1], smoothed[edges[:, 0]])
        smoothed = 0.5 * smoothed + 0.5 * pooled / degree
    return smoothed


def _components(edges: np.ndarray, count: int) -> np.ndarray:
    """Connected-component label per vertex, by union-find."""
    parent = np.arange(count)

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    for a, b in edges:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[ra] = rb
    return np.array([find(int(index)) for index in range(count)])


def _wraps_axis(points: np.ndarray, origin: np.ndarray, axis: np.ndarray,
                reach: float, radius_cap: float = 0.13,
                sectors: int = 12) -> bool:
    """Whether a component encircles a limb axis, the way a sleeve ring does.

    A ring worn on the limb has surface most of the way around the axis and
    close to it.  A belt the axis merely passes near, or a flank plate beside
    it, fails one of the two: the belt's surface rings the torso and sits too
    far from the arm, the plate covers half a turn at most.
    """
    relative = points - origin
    travel = relative @ axis
    across = relative - np.outer(travel, axis)
    radius = np.linalg.norm(across, axis=1)
    near = (travel >= -0.05) & (travel <= reach)
    if int(near.sum()) < 12:
        return False
    if float(np.median(radius[near])) > radius_cap:
        return False
    seed = (np.array([0., 0., 1.]) if abs(axis[2]) < 0.9
            else np.array([1., 0., 0.]))
    u = np.cross(axis, seed)
    u /= max(np.linalg.norm(u), 1e-9)
    v = np.cross(axis, u)
    angles = np.arctan2(across[near] @ v, across[near] @ u)
    bins = np.unique(((angles + math.pi) / (2 * math.pi) * sectors)
                     .astype(int).clip(0, sectors - 1))
    return len(bins) >= sectors // 2


def repose(points: np.ndarray, normals: np.ndarray, rig: ea.Rig, region: str,
           triangles: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Carry each limb of the garment from its authored pose onto the rig's.

    Nothing here trusts a percentile of the garment's own point cloud -- that
    is how every earlier fit went wrong, because decorative geometry pollutes
    any such measure.  The pose is found with the ray caster instead, from the
    limb's real bone axis: drop the axis through the candidate poses and keep
    the ones the garment's surface actually surrounds.  A sleeve is a tube, so
    the arm axis that threads it is enclosed by it; a hip fauld beside the
    sleeve never surrounds the axis at any pose, and a skirt surrounds the leg
    at *every* pose, which is why a pose only counts when it beats the rig's
    own rest pose -- a piece that already encloses the rest axis is already
    wearable and is left exactly as it arrived.

    Sorting the garment into limb and trunk is then not geometric guesswork
    either: the body itself is posed into the found stance, each garment
    vertex inherits the weights of the body surface nearest it -- the same
    rule the final skinning uses, in the one configuration where sleeve wraps
    arm and fauld hugs hip unambiguously -- and the limb share of that blend
    is how far each vertex turns back onto the rig.  The turn is confined to
    the frontal plane, which is where a sheet-drawn figure's pose lives.
    """
    reports: list[dict] = []
    out = points.copy()
    turned = normals.copy()
    for pivot_bone, most_degrees in REPOSE.get(region, ()):
        start = rig.origin(pivot_bone)
        seg_start, seg_end = rig.segment(pivot_bone)
        rig_dir = seg_end - seg_start
        rig_dir /= max(np.linalg.norm(rig_dir), 1e-9)
        side = 1.0 if start[0] >= 0 else -1.0
        drop_sign = -side if region == "torso" else side
        report = {"limb": pivot_bone, "applied": False}
        reports.append(report)
        verts = out[triangles]
        # Sample points sit along the garment-covered run of the limb: past
        # the elbow for a sleeve, down the shin for a trouser leg.  The near
        # and far halves are scored apart, and the far half only ever helps:
        # a cap sleeve encloses nothing past the elbow at any pose, and
        # averaging that silence in would veto a pose the near half found.
        near_spans, far_spans = ((np.linspace(0.14, 0.28, 3),
                                  np.linspace(0.36, 0.50, 3))
                                 if region == "torso"
                                 else (np.linspace(0.15, 0.38, 3),
                                       np.linspace(0.46, 0.65, 3)))
        samples: list[tuple[int, float, float]] = []
        for degrees in range(0, most_degrees + 1, 4):
            angle = math.radians(degrees) * drop_sign
            cos, sin = math.cos(angle), math.sin(angle)
            axis = np.array([cos * rig_dir[0] - sin * rig_dir[1],
                             sin * rig_dir[0] + cos * rig_dir[1],
                             rig_dir[2]])
            near, far = (float(np.mean([
                _limb_axis_enclosure(start + reach * axis, axis, verts)
                for reach in spans])) for spans in (near_spans, far_spans))
            samples.append((degrees, near, far))
        long_limb = max(far for _, _, far in samples) >= 0.5
        curve = [(degrees, (near + far) / 2.0 if long_limb else near)
                 for degrees, near, far in samples]
        best = max(value for _, value in curve)
        at_rest = curve[0][1]
        report["enclosure"] = {"rest": round(at_rest, 2),
                               "best": round(best, 2)}
        if best < REPOSE_ENCLOSED:
            report["reason"] = "nothing surrounds this limb at any pose"
            continue
        if at_rest >= best - 0.08:
            report["reason"] = "already encloses the rest axis"
            continue
        # The band's onset, not its middle: past the true angle the axis dives
        # out of the sleeve into the flank, where hem and fauld geometry keeps
        # the score saturated, so the top edge of the band is noise while its
        # first near-max angle is the sleeve itself.
        plateau = [degrees for degrees, value in curve if value >= best - 0.02]
        chosen = math.radians(float(plateau[0])) * drop_sign
        report["poseDeg"] = round(math.degrees(chosen), 1)

        limb = _limb_bones(rig, pivot_bone)
        limb_slots = np.isin(
            rig.joints, [rig.joint_names.index(name) for name in limb
                         if name in rig.joint_names])
        share = (rig.weights * limb_slots).sum(axis=1, keepdims=True)
        posed_body = (share * _frontal_turn(rig.positions, start, chosen)
                      + (1.0 - share) * rig.positions)
        posed_rig = dataclasses.replace(rig, positions=posed_body)
        candidates = (list(ea.GARMENT_SKIN[region])
                      + REPOSE_SKIN.get(region, []))
        inherited = posed_rig._weights_from_body(out, candidates)
        if inherited is None:
            report["reason"] = "posed body offered no weights to inherit"
            continue
        joints, weights = inherited
        member = np.isin(joints, [rig.joint_names.index(name) for name in limb
                                  if name in rig.joint_names])
        blend = (weights * member).sum(axis=1)
        # A generated piece is a stack of disjoint closed solids, and a solid
        # turns whole or not at all: blending the turn per vertex smears a
        # rigid sleeve, because its inner wall lies nearer the flank than the
        # arm and inherits a different answer than its outer wall.  Each
        # component votes with its mean inherited share; only a component that
        # genuinely spans limb and trunk -- a one-piece trouser, say -- falls
        # back to the smoothed per-vertex blend, where the shear belongs.
        canon, edges, welded = _weld(out, triangles)
        pooled = np.zeros(welded)
        counts = np.zeros(welded)
        np.add.at(pooled, canon, blend)
        np.add.at(counts, canon, 1.0)
        pooled /= np.maximum(counts, 1.0)
        pooled = _graph_smooth(pooled, edges)
        labels = _components(edges, welded)
        chosen_cos = math.cos(chosen)
        chosen_sin = math.sin(chosen)
        posed_axis = np.array([
            chosen_cos * rig_dir[0] - chosen_sin * rig_dir[1],
            chosen_sin * rig_dir[0] + chosen_cos * rig_dir[1], rig_dir[2]])
        reach = 0.55 if region == "torso" else 0.75
        turn = np.zeros(welded)
        for label in np.unique(labels):
            inside = labels == label
            # A sleeve belongs to ONE arm.  A component that straddles the
            # midline is the garment's trunk however well it scores: a
            # closed chest shell encloses the arm axis at the shoulder as
            # surely as a sleeve does, and one that voted its way into a
            # turn swung the whole cuirass off the body and up to head
            # height (knightly torso VIII).  Sidedness is not a vote.
            indexed_side = np.zeros(welded, dtype=bool)
            indexed_side[inside] = True
            side_points = out[indexed_side[canon]]
            if len(side_points):
                spans_midline = (float(side_points[:, 0].max()) > 0.08
                                 and float(side_points[:, 0].min()) < -0.08)
                wrong_side = (float(np.median(side_points[:, 0]))
                              * float(start[0])) < 0.0
                if spans_midline or wrong_side:
                    continue
            vote = float(pooled[inside].mean())
            if vote >= 0.7:
                turn[inside] = 1.0
            else:
                # The inherited weights under-report a sleeve ring whose
                # inner wall hugs the flank -- it can vote nearly all trunk
                # and still be worn on the arm.  Geometry settles it: a piece
                # worn *on* the limb encircles the posed axis, and a piece
                # that merely hangs beside it -- a belt the axis threads, a
                # fauld, half a chest plate -- does not.
                indexed = np.zeros(welded, dtype=bool)
                indexed[inside] = True
                verts_of = indexed[canon]
                if _wraps_axis(out[verts_of], start, posed_axis, reach):
                    turn[inside] = 1.0
        # What sits on top of the joint stays there.  A pauldron is drawn
        # draped over the shoulder crest, and it covers the crest wherever
        # the arm points; rotating it with the sleeve swings it down the
        # arm and bares the trapezius.  A component whose body lies above
        # the pivot is such a cap, and keeps its authored drape.
        caps = np.zeros(welded, dtype=bool)
        for label in np.unique(labels):
            indexed = np.zeros(welded, dtype=bool)
            indexed[labels == label] = True
            verts_of = indexed[canon]
            if not verts_of.any() or float(turn[canon][verts_of].mean()) < 0.99:
                continue
            centroid = out[verts_of].mean(axis=0)
            above = float(centroid[1] - start[1])
            outboard = abs(float(centroid[0])) - abs(float(start[0]))
            # How much limb the shell covers at all.  Radius from the joint,
            # because the repose turns ABOUT that joint, so this is the one
            # measure of a shell that the pose it arrived in cannot change.
            span_of = float(np.linalg.norm(out[verts_of] - start,
                                           axis=1).max())
            crest = float(out[verts_of][:, 1].max()) - float(start[1])
            # And it must DRAPE, not encircle: a long armoured sleeve's
            # upper section also sits above the joint in an A-pose, but it
            # wraps the authored arm axis where a pauldron shell does not
            # -- demoting it to cap left the legendary hero's upper
            # sleeves standing off the shoulders at the concept's angle.
            wraps = _wraps_axis(out[verts_of], start, posed_axis, reach)
            # A pauldron drapes OVER the crest and down the outside of it, so
            # its body hangs level with the joint or a little below -- the
            # legendary hero's sits 16 mm under it.  Asking for the centroid to
            # be above the joint therefore misses the very shells this rule
            # exists to hold, and they ride down the arm with the sleeve.  What
            # separates them is not height but reach: a cap covers the joint and
            # stops, a sleeve carries on down the limb.  Measured on this piece
            # the caps end 0.17 m from the joint and the sleeves run to 0.36 and
            # 0.49, so there is a wide gap to put the line in.
            capped = span_of < CAP_REACH and crest > 0.01
            if capped or (above > 0.01 and outboard < 0.10 and not wraps):
                turn[indexed] = 0.0
                caps[indexed] = True
        turn = turn[canon]
        if region == "legs":
            chosen = _keep_to_own_side(out, start, chosen, turn)
            report["poseDeg"] = round(math.degrees(chosen), 1)
        out = _frontal_turn(out, start, -chosen * turn)
        turned = _frontal_turn(turned, np.zeros(3), -chosen * turn)
        report["applied"] = True
        report["limbVertices"] = int((turn > 0.5).sum())
        report["components"] = int(len(np.unique(labels)))
        # The masks ride along so the finishing passes in build() -- seated
        # and stretched geometry -- can still tell sleeve from cap from
        # trunk without re-deriving the segmentation.
        report["sleeve"] = turn > 0.5
        report["cap"] = caps[canon]
        report["pivot"] = pivot_bone
    return out, turned, reports


def _push_axis(points: np.ndarray, indices: np.ndarray, rig: ea.Rig,
               axis_start: np.ndarray, axis_end: np.ndarray, bones: list[str],
               clearance: float, moved: np.ndarray) -> int:
    """Push one group of vertices out to the body measured about one axis."""
    axis = axis_end - axis_start
    length = float(np.linalg.norm(axis))
    if length < 1e-6 or not len(indices):
        return 0
    axis = axis / length
    reference = (np.array([0., 1., 0.]) if abs(axis[1]) < .8
                 else np.array([0., 0., 1.]))
    right = np.cross(axis, reference)
    right /= np.linalg.norm(right)
    forward = np.cross(right, axis)

    pushed = 0
    for index in indices:
        offset = points[index] - axis_start
        along = float(offset @ axis)
        radial = offset - along * axis
        distance = float(np.linalg.norm(radial))
        if distance < 1e-6:
            continue
        angle = math.atan2(float(radial @ forward), float(radial @ right))
        radius = rig.surface_radius(axis_start, axis_end, along / length, angle,
                                    bones=bones, slab=.05, default=.0)
        want = radius + clearance
        if radius > 0. and distance < want:
            moved[index] = points[index] + radial / distance * (want - distance)
            pushed += 1
    return pushed


#: The few millimetres a sleeve must stand off the liner, on top of the lift
#: the standoff already gives it.  Read at the call rather than
#: folded into a constant here, because that one is defined further down with
#: the rest of the liner and this file reads top to bottom.
SLEEVE_MARGIN = 0.005


def _let_out_axis(points: np.ndarray, indices: np.ndarray, rig: ea.Rig,
                  axis_start: np.ndarray, axis_end: np.ndarray,
                  bones: list[str], clearance: float, moved: np.ndarray,
                  rows: int = 8, sectors: int = 8,
                  most: float = 1.35) -> int:
    """Scale one group of vertices out about a limb axis, band by band.

    Outward only, and a band at a time rather than a vertex at a time.  A
    sleeve is a closed shell: pushing every vertex that sits inside the body
    out to the body's own radius drives the shell's INNER wall out to meet its
    outer one, and the sleeve renders as a scatter of loose slabs with its
    lining showing.  That is the same failure `_slim_to_body` describes in the
    other direction, and it has the same answer -- scale the whole band, so
    both walls travel together and the shell stays a shell.

    Each band asks, per angular sector, how far its nearest surface is from
    the axis against how far the body's surface is, and the band is scaled by
    the largest factor any sector needs.  Sectors the sleeve has no surface in
    are its openings and say nothing.
    """
    axis = axis_end - axis_start
    length = float(np.linalg.norm(axis))
    if length < 1e-6 or not len(indices):
        return 0
    axis = axis / length
    reference = (np.array([0., 1., 0.]) if abs(axis[1]) < .8
                 else np.array([0., 0., 1.]))
    right = np.cross(axis, reference)
    right /= np.linalg.norm(right)
    forward = np.cross(right, axis)

    offset = points[indices] - axis_start
    along = offset @ axis
    radial = offset - np.outer(along, axis)
    distance = np.linalg.norm(radial, axis=1)
    angle = np.arctan2(radial @ forward, radial @ right)
    fraction = np.clip(along / length, 0.0, 1.0)

    factors = np.ones(rows)
    for row in range(rows):
        lo, hi = row / rows, (row + 1) / rows
        band = (fraction >= lo) & (fraction < hi) & (distance > 1e-6)
        if int(band.sum()) < 4:
            factors[row] = np.nan
            continue
        middle = (lo + hi) / 2.0
        need = 1.0
        for sector in range(sectors):
            low = -np.pi + 2 * np.pi * sector / sectors
            high = -np.pi + 2 * np.pi * (sector + 1) / sectors
            here = band & (angle >= low) & (angle < high)
            if int(here.sum()) < 2:
                continue
            inner = float(np.percentile(distance[here], 12.0))
            radius = rig.surface_radius(axis_start, axis_end, middle,
                                        (low + high) / 2.0, bones=bones,
                                        slab=.05, default=.0)
            if radius > 0.0 and inner > 1e-6:
                need = max(need, (radius + clearance) / inner)
        factors[row] = float(np.clip(need, 1.0, most))

    good = ~np.isnan(factors)
    if not good.any():
        return 0
    centres = (np.arange(rows) + 0.5) / rows
    factors = np.interp(centres, centres[good], factors[good])
    for _ in range(2):
        factors = np.convolve(np.pad(factors, 1, mode="edge"),
                              [1 / 3.0, 1 / 3.0, 1 / 3.0], mode="valid")
    scale = np.interp(fraction, centres, factors)
    grew = scale > 1.0005
    if not grew.any():
        return 0
    moved[indices] = (axis_start + np.outer(along, axis)
                      + radial * scale[:, None])
    return int(grew.sum())


def _unsquash_limb(points: np.ndarray, indices: np.ndarray,
                   axis_start: np.ndarray, axis_end: np.ndarray,
                   factor: float) -> int:
    """Take the trunk's girth correction back off one sleeve.

    `seat` scales height and girth by different numbers, and the girth number
    is measured for the trunk: a generated cuirass is drawn slender and has to
    be let out to go round a body.  A sleeve was never the thing being fitted.
    It arrives drawn hanging, so its LENGTH runs down the height axis and its
    cross-section across the girth axes -- and letting the girth out by half
    again, with the height untouched, leaves a tube half again too fat for its
    length.  That is the squashed, flat-slabbed upper arm: not the repose, not
    the clearance passes, just the trunk's correction charged to the wrong
    part of the piece.

    So the sleeve's cross-section is scaled back about its own arm's axis,
    which is the one direction that leaves its length, its place on the limb
    and its drape alone.  Anything this takes inside the arm `_clear_sleeves`
    puts back, measured against the body rather than guessed.
    """
    if not len(indices) or not 0.05 < factor < 0.999:
        return 0
    axis = axis_end - axis_start
    length = float(np.linalg.norm(axis))
    if length < 1e-6:
        return 0
    axis = axis / length
    offset = points[indices] - axis_start
    along = offset @ axis
    radial = offset - np.outer(along, axis)
    points[indices] = (axis_start + np.outer(along, axis) + radial * factor)
    return int(len(indices))


def _clear_sleeves(points: np.ndarray, rig: ea.Rig, sleeve: np.ndarray,
                   clearance: float | None = None) -> tuple[np.ndarray, int]:
    """Let a sleeve out until it clears the liner over the arm it covers.

    Everything else the torso branch does draws the piece IN, and it exempts
    the sleeves on the reasoning that a sleeve is fitted to its limb already.
    Seated geometry is not.  ``seat`` sizes girth from the design's own
    proportions, so a figure drawn with slimmer arms than the rig has puts its
    sleeve *inside* the arm -- 25 mm inside it on the legendary hero cuirass,
    where the liner then stands 34 mm proud of the armour across the top of the
    shoulder and the piece reads as a black band between pauldron and elbow.
    The armour was there the whole time; it was underneath.

    So the sleeve is let out about its own arm's axis, the way the limb
    garments are cleared, and outward only: a sleeve already clear of the liner
    keeps exactly the shape the design gave it.  Band at a time, never vertex
    at a time -- see `_let_out_axis` for what the per-vertex version did to a
    closed sleeve once the seat stopped over-inflating one.
    """
    if clearance is None:
        clearance = SKIN_STANDOFF + SLEEVE_MARGIN
    moved = np.array(points, dtype=np.float64)
    pushed = 0
    for side in ("l", "r"):
        mine = points[:, 0] >= 0 if side == "l" else points[:, 0] < 0
        own = np.flatnonzero(sleeve & mine)
        pushed += _let_out_axis(points, own, rig,
                                rig.origin("upperarm_%s" % side),
                                rig.origin("hand_%s" % side),
                                ["upperarm_%s" % side, "lowerarm_%s" % side,
                                 "hand_%s" % side], clearance, moved)
    return moved, pushed


def grow_clear(points: np.ndarray, triangles: np.ndarray, rig: ea.Rig,
               region: str, clearance: float = CLEARANCE,
               limit: float = 1.35) -> tuple[np.ndarray, float]:
    """Scale the piece up about its own centre until the body fits inside it.

    The alternative -- moving each buried vertex out to the skin -- is what a
    lofted shell can afford and an imported mesh cannot.  A generated garment
    is a closed solid: it has an inner surface as well as an outer one, and
    pushing the inner surface out to the body drives it through the outer one.
    The cuirass that comes back is shredded, with the pauldrons flung out
    sideways as loose slabs.  Growing the whole piece keeps every relation in
    the design intact and only costs a garment that reads slightly loose.
    """
    spec = MEASURE[region]
    if spec["mode"] == "vertical":
        groups = [(np.arange(len(points)), measure_bones(region), None)]
    else:
        groups = []
        for side in ("l", "r"):
            own = np.flatnonzero(points[:, 0] >= 0 if side == "l"
                                 else points[:, 0] < 0)
            groups.append((own, measure_bones(region, side), side))

    body = np.vstack([rig._region(bones) for _i, bones, _s in groups])
    centre = (points.max(axis=0) + points.min(axis=0)) / 2.
    # Only the skin the piece covers: a cuirass is not answerable for an ankle,
    # and counting one would grow it forever.
    span = SPAN.get(region)
    if span is not None:
        low, high = (value * rig.fit_scale for value in span)
        body = body[(body[:, 1] >= low) & (body[:, 1] <= high)]
    if not len(body):
        return points, 1.0

    # Compared in horizontal slices about the piece's own upright.  Parity
    # enclosure would be the better question -- is the body *inside* the shell --
    # but a generated garment is dozens of disjoint solids (plates, laces,
    # buckles) and no single closed component contains a torso, so the test can
    # never pass and every piece saturates at the limit.
    axis = np.array([centre[0], centre[2]])
    needed = 1.0
    for step in range(14):
        height = float(body[:, 1].min()) + (
            float(body[:, 1].max()) - float(body[:, 1].min())) * (step + .5) / 14.
        band = (float(body[:, 1].max()) - float(body[:, 1].min())) / 28. + .01
        skin = body[np.abs(body[:, 1] - height) <= band]
        shell = points[np.abs(points[:, 1] - height) <= band]
        if len(skin) < 4 or len(shell) < 4:
            continue
        skin_r = float(np.percentile(
            np.linalg.norm(skin[:, [0, 2]] - axis, axis=1), 96.))
        shell_r = float(np.percentile(
            np.linalg.norm(shell[:, [0, 2]] - axis, axis=1), 96.))
        if shell_r > 1e-6:
            needed = max(needed, (skin_r + clearance) / shell_r)
    scale = float(min(needed, limit))
    return (points - centre) * scale + centre, scale


def clear_body(points: np.ndarray, rig: ea.Rig, region: str,
               clearance: float = CLEARANCE) -> tuple[np.ndarray, int]:
    """Push vertices that sit inside the skin out to the measured surface.

    Kept for open shells, where it is the right tool; ``grow_clear`` is the
    default because imported solids are not open shells.
    """
    spec = MEASURE[region]
    moved = np.array(points, dtype=np.float64)
    if spec["mode"] == "vertical":
        body = region_points(rig, region)
        # The upright through the body centre, spanning what the region covers:
        # the axis `torso_rings` measures its own shells about.
        centre = (body.max(axis=0) + body.min(axis=0)) / 2.
        start = np.array([centre[0], float(body[:, 1].min()), centre[2]])
        end = np.array([centre[0], float(body[:, 1].max()), centre[2]])
        pushed = _push_axis(points, np.arange(len(points)), rig, start, end,
                            measure_bones(region), clearance, moved)
        return moved, pushed

    pushed = 0
    for side in ("l", "r"):
        bones = measure_bones(region, side)
        start = rig.origin(spec["axis"][0] % side)
        end = rig.origin(spec["axis"][1] % side)
        # Split at the body midline: each half belongs to the limb on its side.
        own = np.flatnonzero(points[:, 0] >= 0 if side == "l"
                             else points[:, 0] < 0)
        pushed += _push_axis(points, own, rig, start, end, bones, clearance,
                             moved)
    return moved, pushed


def textured_material(glb: ea.EquipmentGLB, name: str, png: bytes | None,
                      colour=(190, 185, 178), double_sided: bool = False) -> int:
    """Base colour straight off the generated map, when there is one."""
    pbr = {"baseColorFactor": ea.srgb_to_linear(colour) + [1.],
           "metallicFactor": 0.0, "roughnessFactor": 0.72}
    if png is not None:
        pbr["baseColorFactor"] = [1., 1., 1., 1.]
        pbr["baseColorTexture"] = {"index": glb.texture(png)}
    glb.doc["materials"].append(
        {"name": name, "pbrMetallicRoughness": pbr,
         "doubleSided": double_sided})
    return len(glb.doc["materials"]) - 1


#: How far a hidden surface has to stand off the skin, in metres.
#:
#: This was the lift on a shirt liner -- an underlayer of the body's own
#: triangles that every torso piece used to ship, because the meshy race
#: bodies paint their wardrobe into the body texture and an open design of
#: straps and plates showed the painted shirt through every gap in it.  The
#: liner closed those gaps and cost the armour: drawn a few millimetres off
#: the skin in a near-black, it won the depth test wherever a plate was seated
#: nearer than that, and pieces read as a black tunic with ornament floating on
#: it.  It is no longer drawn, so what is left of it is the number: how far off
#: the body a surface has to sit before the two stop fighting for the same
#: pixels at a grazing angle.
SKIN_STANDOFF = 0.008


def socket_origin(rig: ea.Rig, part: int) -> np.ndarray:
    """Where the runtime will hang this part, in world space."""
    socket = ea.build_sockets(rig).get(part)
    origin = rig.origin(socket.bone if socket else "Head")
    offset = np.asarray(getattr(socket, "offset", (0., 0., 0.)),
                        dtype=np.float64)
    return origin + offset


#: How far a sleeve's own axis may be turned onto its bone's, in degrees.  A
#: fit that claims more than this has latched onto a fin rather than the tube.
SLEEVE_TILT = 40.0


def _sleeve_bone(shell: np.ndarray, rig: ea.Rig, side: str):
    """Which arm segment a sleeve component is worn on.

    By where its vertices ARE, not by where its centroid is.  A bracer running
    from just above the elbow to the wrist has its centroid nearer the upper
    arm's line than the forearm's -- the upper segment stops at the elbow, so
    the whole bracer is measured against that one point -- and both sleeve
    passes then straightened it against the wrong bone.  Every vertex votes for
    the segment it is nearest and the majority wins, which puts the legendary
    hero's vambrace on the forearm where 87 per cent of it lives.
    """
    scores = {}
    for name, (top, bottom) in (("upper", ("upperarm", "lowerarm")),
                                ("fore", ("lowerarm", "hand"))):
        try:
            a = rig.origin("%s_%s" % (top, side))
            b = rig.origin("%s_%s" % (bottom, side))
        except (KeyError, ValueError):
            continue
        span = b - a
        along = np.clip((shell - a) @ span / max(float(span @ span), 1e-12),
                        0.0, 1.0)
        scores[name] = (np.linalg.norm(shell - (a + np.outer(along, span)),
                                       axis=1), a, b)
    if len(scores) < 2:
        return None
    nearer = scores["upper"][0] < scores["fore"][0]
    name = "upper" if float(nearer.mean()) >= 0.5 else "fore"
    return (name, scores[name][1], scores[name][2])


def _tube_axis(shell: np.ndarray, seed: np.ndarray, bands: int = 5):
    """The line a sleeve's rings are strung on, and its middle.

    Fitted through the median of each band rather than by taking the whole
    cloud's principal axis: a sleeve carries fins, lames and a flared cuff, and
    a principal axis follows whichever of those is longest.  A ring's median
    centre does not care how far its fin sticks out.
    """
    centre = np.median(shell, axis=0)
    along = (shell - centre) @ seed
    low, high = float(along.min()), float(along.max())
    if high - low < 1e-6:
        return seed, centre
    rings = []
    for band in range(bands):
        lo = low + (high - low) * band / bands
        hi = low + (high - low) * (band + 1) / bands
        here = (along >= lo) & (along <= hi)
        if int(here.sum()) >= 4:
            rings.append(np.median(shell[here], axis=0))
    if len(rings) < 3:
        return seed, centre
    rings = np.asarray(rings)
    middle = rings.mean(axis=0)
    axis = np.linalg.svd(rings - middle, full_matrices=False)[2][0]
    if float(axis @ seed) < 0.0:
        axis = -axis
    return axis, middle


def _true_sleeve_axes(points: np.ndarray, triangles: np.ndarray,
                      rig: ea.Rig, steps: list[dict]) -> int:
    """Turn each sleeve so its own axis lies along the bone it is worn on.

    `_align_arm_sleeves` rotates a sleeve group about the joint until its
    CENTROID sits on the bone line.  That fixes a sleeve hanging off at the
    concept's elbow angle and does nothing at all for one already centred but
    lying across the bone.  The legendary hero's vambrace is the second kind:
    centred within 9 mm and tilted 29 degrees, so its rings drift from 16 mm
    off the forearm at the elbow to 45 mm at the wrist and it reads as a bell
    flaring off the arm.  `_clear_sleeves` then makes it worse -- the tilt puts
    the near wall inside the arm, and a band scaled up to free that wall takes
    the far wall out with it.

    So each wrapping component is turned about its own middle until its tube
    axis matches the bone's.  Rigid, so nothing can invert; the translation
    that remains is `_centre_sleeves`' job.
    """
    inverse, edges, count = _weld(points, triangles)
    labels = _components(edges, count)[inverse]
    turned = 0
    for step in steps:
        if not step.get("applied") or "sleeve" not in step:
            continue
        side = step["limb"].rsplit("_", 1)[-1]
        sleeve = np.asarray(step["sleeve"], dtype=bool)
        for label in np.unique(labels[sleeve]):
            members = labels == label
            if int((members & sleeve).sum()) * 2 < int(members.sum()):
                continue
            shell = points[members]
            found = _sleeve_bone(shell, rig, side)
            if found is None:
                continue
            _name, pivot, tip = found
            bone = tip - pivot
            bone = bone / max(np.linalg.norm(bone), 1e-9)
            axis, middle = _tube_axis(shell, bone)
            half = float(np.percentile(np.abs((shell - middle) @ bone), 95.0))
            if not _wraps_axis(shell - (middle - bone * half), np.zeros(3),
                               bone, 2.0 * half + 0.05):
                continue
            cross = np.cross(axis, bone)
            norm = float(np.linalg.norm(cross))
            angle = math.degrees(math.acos(
                float(np.clip(np.dot(axis, bone), -1.0, 1.0))))
            if norm < 1e-6 or angle < 4.0 or angle > SLEEVE_TILT:
                continue
            cross = cross / norm
            cos = math.cos(math.radians(angle))
            sin = math.sin(math.radians(angle))
            skew = np.array([[0, -cross[2], cross[1]],
                             [cross[2], 0, -cross[0]],
                             [-cross[1], cross[0], 0]])
            turn = np.eye(3) + sin * skew + (1 - cos) * (skew @ skew)
            points[members] = (points[members] - middle) @ turn.T + middle
            turned += 1
    return turned


def _align_arm_sleeves(points: np.ndarray, triangles: np.ndarray,
                       rig: ea.Rig, steps: list[dict]) -> int:
    """Rigidly turn each arm-sleeve group onto its own bone line.

    The repose corrects the shoulder angle the concept drew, but a sheet
    that poses its knight akimbo bends the FOREARM of the sleeve too --
    and a bracer bound rigidly to a straight forearm bone then juts
    across the chest at the concept's elbow angle.  Per side, the sleeve
    components are grouped by their nearest bone segment, and each group
    takes the one rotation about its pivot (shoulder for the upper group,
    elbow for the forearm group) that carries its centroid direction onto
    the bone; ring centring afterwards handles the residual translation.
    Small angles are left alone so already-straight sheets pass through
    byte-stable.  Returns how many groups turned.
    """
    inverse, edges, count = _weld(points, triangles)
    labels = _components(edges, count)[inverse]
    turned = 0
    for step in steps:
        if not step.get("applied") or "sleeve" not in step:
            continue
        side = step["limb"].rsplit("_", 1)[-1]
        try:
            shoulder = rig.origin("upperarm_" + side)
            elbow = rig.origin("lowerarm_" + side)
            wrist = rig.origin("hand_" + side)
        except (KeyError, ValueError):
            continue
        sleeve = np.asarray(step["sleeve"], dtype=bool)
        groups = {"upper": [], "fore": []}
        for label in np.unique(labels[sleeve]):
            members = labels == label
            if int((members & sleeve).sum()) * 2 < int(members.sum()):
                continue
            centre = np.median(points[members], axis=0)
            found = _sleeve_bone(points[members], rig, side)
            if found is None:
                continue
            which, pivot, tip = found
            # Only ring-like components are worn ON the arm and belong in
            # the alignment: a shoulder mantle or drape classified as
            # sleeve must keep its authored hang -- rotated onto the bone
            # it crumples around the arm like a wrung rag (the legendary
            # hero's half-cape found this).
            axis = tip - pivot
            axis = axis / max(np.linalg.norm(axis), 1e-9)
            travel = (points[members] - centre) @ axis
            half = float(np.percentile(np.abs(travel), 95.0))
            if not _wraps_axis(points[members] - (centre - axis * half),
                               np.zeros(3), axis, 2.0 * half + 0.05):
                continue
            groups[which].append(members)
        for name, pivot, tip in (("upper", shoulder, elbow),
                                 ("fore", elbow, wrist)):
            if not groups[name]:
                continue
            members = np.zeros(len(points), dtype=bool)
            for m in groups[name]:
                members |= m
            centroid = points[members].mean(axis=0)
            d0 = centroid - pivot
            d1 = tip - pivot
            n0, n1 = np.linalg.norm(d0), np.linalg.norm(d1)
            if n0 < 1e-6 or n1 < 1e-6:
                continue
            d0, d1 = d0 / n0, d1 / n1
            axis = np.cross(d0, d1)
            norm = float(np.linalg.norm(axis))
            angle = float(np.degrees(np.arccos(np.clip(np.dot(d0, d1),
                                                       -1.0, 1.0))))
            if norm < 1e-6 or angle < 4.0:
                continue
            axis /= norm
            c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
            K = np.array([[0, -axis[2], axis[1]],
                          [axis[2], 0, -axis[0]],
                          [-axis[1], axis[0], 0]])
            R = np.eye(3) + s * K + (1 - c) * (K @ K)
            points[members] = (points[members] - pivot) @ R.T + pivot
            turned += 1
    return turned


def _segment_gap(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    span = b - a
    t = float(np.clip(np.dot(point - a, span)
                      / max(np.dot(span, span), 1e-12), 0.0, 1.0))
    return float(np.linalg.norm(point - (a + t * span)))


def _centre_sleeves(points: np.ndarray, triangles: np.ndarray, rig: ea.Rig,
                    steps: list[dict]) -> int:
    """Rigidly re-centre each wrapping sleeve ring on its own limb axis.

    The repose turns a sleeve down about the shoulder by the angle the sweep
    detected, and every residual error in that angle -- or forward lean the
    concept drew that a frontal turn cannot see -- lands as a translation
    that grows with distance from the pivot.  A bracer half a metre out rides
    visibly off the forearm while still swinging with it.  The fix is the
    measurement the sweep already trusts: a component that encircles the limb
    axis is worn on it, so slide it (perpendicular to the axis only -- the
    wrist clamp owns the length) until its ring centre sits on the bone.
    The median centre shrugs off a decorative fin; plates that do not wrap
    stay where the design drew them.  Returns how many rings moved.
    """
    inverse, edges, count = _weld(points, triangles)
    labels = _components(edges, count)[inverse]
    moved = 0
    for step in steps:
        if not step.get("applied") or "sleeve" not in step:
            continue
        side = step["limb"].rsplit("_", 1)[-1]
        segments = []
        for top, bottom in (("upperarm", "lowerarm"), ("lowerarm", "hand")):
            try:
                a = rig.origin("%s_%s" % (top, side))
                b = rig.origin("%s_%s" % (bottom, side))
            except (KeyError, ValueError):
                continue
            segments.append((a, b))
        if not segments:
            continue
        sleeve = np.asarray(step["sleeve"], dtype=bool)
        for label in np.unique(labels[sleeve]):
            members = labels == label
            if int((members & sleeve).sum()) * 2 < int(members.sum()):
                continue
            centre = np.median(points[members], axis=0)
            found = _sleeve_bone(points[members], rig, side)
            if found is None:
                continue
            _name, a, b = found
            span = b - a
            t = float(np.clip(np.dot(centre - a, span)
                              / max(np.dot(span, span), 1e-12), 0.0, 1.0))
            on = a + t * span
            axis = span / max(np.linalg.norm(span), 1e-9)
            # Ring-ness is judged about the component's OWN centre, not the
            # limb line: the very displacement being corrected can put the
            # limb axis outside the ring, where the sector test sees a gap
            # and vetoes exactly the components that need the fix.
            travel = (points[members] - centre) @ axis
            half = float(np.percentile(np.abs(travel), 95.0))
            if not _wraps_axis(points[members] - (centre - axis * half),
                               np.zeros(3), axis, 2.0 * half + 0.05):
                continue
            delta = on - centre
            delta -= axis * float(np.dot(delta, axis))
            if float(np.linalg.norm(delta)) < 0.004:
                continue
            points[members] += delta
            moved += 1
    return moved


def seat_socket(points: np.ndarray, rig: ea.Rig, kind: str) -> np.ndarray:
    """Size a socket piece to what it is worn on and centre it on the socket.

    Authored about the socket, not about the world: the runtime attaches the
    scene to a bone and applies the socket's own offset, so a mesh drawn at the
    head's world height would be lifted by that height again and worn as a
    hat above the hat.  The reference pieces confirm the convention --
    ``amberwood_ranger_hood`` is centred within 9 mm of its own origin.
    """
    spec = SOCKET_KIND[kind]
    head = rig._region(spec["bones"])
    # Measured as it stands: the head's size lives in its vertices now
    # (adjust_race_proportions.py grows them), so the region this reads
    # IS the runtime head.  The joint carries no scale to compensate for
    # -- when it did, every helm was authored a third too large for a
    # head that had only ever grown offline.
    span = head.max(axis=0) - head.min(axis=0)
    # Size to the head's widest horizontal axis, from a robust span: a helm
    # is a shell around a skull, and matching height instead lets a tall crest
    # pull the whole piece down inside the face.  The span uses the 4th-96th
    # percentile so a single spike does not inflate the scale.
    lo = np.percentile(points, 4, axis=0)
    hi = np.percentile(points, 96, axis=0)
    extent = np.maximum(hi - lo, 1e-9)
    scale = max((span[axis] + 2 * spec["clearance"]) / float(extent[axis])
                for axis in (0, 2))
    # Reviewed in game: pieces sized strictly to the skull read a fifth
    # too big -- their flares and trim inflate the visual bulk past the
    # measured span -- so every socket piece takes a flat trim.
    scale *= SOCKET_SHRINK
    seated = (points - (points.max(axis=0) + points.min(axis=0)) / 2.) * scale
    # Centre on the head's own centre by the MEDIAN of the piece, not its
    # bounding box: circlets and helms carry danglers and spikes that skew a
    # bbox centre and drag the band down over the eyes.  The head sits inside
    # the shell, riding high, and a per-kind lift seats it like a hat on the
    # crown rather than a bucket over the face.
    head_mid = 0.5 * (float(head[:, 1].min()) + float(head[:, 1].max()))
    # Centre depth on the cranium alone: the full head region includes the
    # nose and jaw, whose verts drag a median forward and wear the piece out
    # over the brow.  A skull is round above its midline, so the upper half
    # is the shell the piece actually wraps.
    crown = head[head[:, 1] >= head_mid]
    # And a per-kind setback on top of the cranium median: even centred on
    # the skull the shells kept reading worn out over the brow in game, so
    # each kind slides back a touch further.
    centre = np.array([float(np.median(head[:, 0])), 0.0,
                       float(np.median(crown[:, 2]))
                       - float(spec.get("setback", 0.0))])
    lift = float(spec.get("lift", 0.0)) * (head[:, 1].max() - head[:, 1].min())
    centre[1] = head_mid - float(np.median(seated[:, 1])) + lift
    placed = seated + centre

    # Cover the skull.  Sizing a piece by the head's WIDTH says nothing
    # about how deep its shell is, so a shallow crown -- and the shrink
    # every socket piece takes -- can leave the head standing out of the
    # top of its own helmet.  The piece grows about its brim until its
    # crown clears the head, and only lifts if growing alone cannot do it:
    # a hat pulled up off the head reads worse than a slightly tall one.
    if spec.get("covers"):
        # The margin is measured, not chosen: the fitter works in the rest
        # pose while the wearer stands in the idle, whose levelled head
        # reads about two centimetres taller, so a helm that just covers
        # here leaves the crown out in the client.
        wanted = float(head[:, 1].max()) + 0.055
        base = float(placed[:, 1].min())
        top = float(placed[:, 1].max())
        height = top - base
        if top < wanted and height > 1e-4:
            # Upward only: growing a piece whole to cover the crown also
            # spreads a wide brim, and a hat's brim was never the problem.
            factor = float(np.clip((wanted - base) / height, 1.0, 1.45))
            placed[:, 1] = base + (placed[:, 1] - base) * factor
            short = wanted - float(placed[:, 1].max())
            if short > 0.0:
                placed[:, 1] += min(short, 0.045)
    return placed - socket_origin(rig, spec["part"])


def build_socket(source: Path, out: Path, rig: ea.Rig, kind: str,
                 label: str, flip: bool = False, roll: bool = False,
                 grip: tuple[float, float, float] | None = None) -> dict:
    """Size and place one socket piece, and write it unskinned."""
    surface, png = read_source(source)
    before = surface.positions.copy()
    if kind in PROP_KIND:
        # A weapon or shield is sized from its own class rather than from the
        # body: it hangs off a hand and owes nothing to the wearer's build.
        seat_prop(surface, kind, flip, roll, grip)
    else:
        surface.positions = seat_socket(surface.positions, rig, kind)
    # Socket pieces carry concept-sheet debris too, and the runtime-size
    # scale swings a buried splinter clear of the shell.
    _drop_orphan_shards(surface)

    glb = ea.EquipmentGLB(generator="Eloria conform_equipment")
    material = textured_material(glb, "%s Base" % label, png)
    positions, normals, uvs, indices = surface.arrays()[0]
    primitive = glb.primitive(positions, normals, uvs, indices, material)
    glb.mesh(label, [primitive])
    glb.write(out)

    span_before = before.max(axis=0) - before.min(axis=0)
    span_after = surface.positions.max(axis=0) - surface.positions.min(axis=0)
    return {"source": source.name, "out": out.name, "kind": kind,
            "region": "", "attach": "socket",
            "vertices": int(len(positions)),
            "triangles": int(len(indices) // 3), "joints": 0,
            "scale": round(float(span_after[1] / max(span_before[1], 1e-9)), 4),
            "spanBefore": [round(float(v), 3) for v in span_before],
            "spanAfter": [round(float(v), 3) for v in span_after],
            "fit": "socket", "grew": 1.0, "pushedOut": 0,
            "textured": png is not None, "bytes": out.stat().st_size}


def _slim_to_body(points: np.ndarray, rig: ea.Rig, region: str,
                  movable: np.ndarray, target_clear: float,
                  body_points: np.ndarray | None = None,
                  centre: np.ndarray | None = None,
                  grow: bool = False) -> np.ndarray:
    """Draw a garment's trunk in toward the body until it hugs.

    A pull, never a push, and per axis: the torso is an ellipse -- wide across
    the shoulders, shallow front to back -- so a single radial factor cut to
    the wide sides drives the shallow front and back panels straight through
    the body and leaves the chest bare padding.  Each height band therefore
    gets its own x factor and z factor, each landing that side of the shell at
    the body's own half-extent plus ``target_clear`` on that axis, clamped to
    [floor, 1] so the shell only comes in, never past the body, and a real
    relief is thinned rather than erased.  Measured against the body's closed
    surface, never the garment's multi-shell point cloud.
    A limb region -- two tubes -- is slimmed a tube at a time: the caller
    passes the movable subset for one leg and the body points and centre of
    that same leg, so each trouser leg hugs its own thigh rather than a
    midline between them.
    """
    if body_points is None:
        body_points = region_points(rig, region)
    if centre is None:
        centre = np.array([float(np.median(body_points[:, 0])),
                           float(np.median(body_points[:, 2]))])
    body = body_points
    low, high = float(body[:, 1].min()), float(body[:, 1].max())
    rows = 12
    # Growing is the same banded, per-axis move in the other direction --
    # and the only body-clearing move a closed generated solid can take:
    # scaling a whole band keeps inner and outer surfaces together, where a
    # per-vertex push (clear_body) turns the inside of the shell out.
    lo_clip, hi_clip = (1.0, 1.35) if grow else (0.55, 1.0)
    floor = lo_clip
    factors = np.ones((rows, 2))
    for row in range(rows):
        lo = low + (high - low) * row / rows
        hi = low + (high - low) * (row + 1) / rows
        skin = body[(body[:, 1] >= lo) & (body[:, 1] < hi)]
        mid = (points[:, 1] >= lo) & (points[:, 1] < hi) & movable
        if len(skin) < 6 or int(mid.sum()) < 6:
            factors[row] = np.nan
            continue
        shell = points[mid]
        for index, axis in enumerate((0, 2)):
            skin_h = float(np.percentile(np.abs(skin[:, axis] - centre[index]),
                                         92.0))
            shell_h = float(np.percentile(np.abs(shell[:, axis] - centre[index]),
                                          92.0))
            factors[row, index] = (float(np.clip(
                (skin_h + target_clear) / shell_h, lo_clip, hi_clip))
                if shell_h > 1e-4 else np.nan)
    centres = low + (high - low) * (np.arange(rows) + 0.5) / rows
    out = points.copy()
    for index in range(2):
        column = factors[:, index]
        good = ~np.isnan(column)
        if not good.any():
            continue
        column = np.interp(centres, centres[good], column[good])
        for _ in range(2):
            column = np.convolve(np.pad(column, 1, mode="edge"),
                                 [1 / 3.0, 1 / 3.0, 1 / 3.0], mode="valid")
        axis = (0, 2)[index]
        scale = np.interp(out[movable, 1], centres, column)
        out[movable, axis] = ((out[movable, axis] - centre[index]) * scale
                              + centre[index])
    return out


def _fit_trunk_profile(points: np.ndarray, triangles: np.ndarray, rig: ea.Rig,
                       movable: np.ndarray, clearance: float) -> dict:
    """Fit the trunk's lining by height, preserving solid walls and ornaments.

    A ray from the cavity meets the lining first even when it crosses an even
    number of walls.  Parity tests material enclosure, not whether a hollow
    garment surrounds a wearer; it cannot validate this measurement.  Nor can
    a percentile of the whole point cloud: sleeves, straps and lames enlarge
    the apparent width while the actual chest shell remains inside the body.

    Width answers to both inner side walls.  Depth lets the front and back
    out independently, so a shallow back cannot pull a clear front backwards.
    Each band receives one positive affine transform; its inner and outer
    walls travel together.  Short shells follow their centre rigidly instead
    of being sheared by a profile defined over a much taller trunk.  Missing
    bands interpolate only through the chest; the hem and collar retain
    their seating, and the repose's sleeves and caps are exempt throughout.
    """
    body = region_points(rig, "torso")
    heights = np.linspace(1.10, 1.44, 18) * rig.fit_scale
    factors = np.full(len(heights), np.nan)
    depth_factors = np.full(len(heights), np.nan)
    depth_shifts = np.full(len(heights), np.nan)
    faces = points[triangles[movable[triangles].all(axis=1)]]
    for row, height in enumerate(heights):
        skin = body[np.abs(body[:, 1] - height) < .025 * rig.fit_scale]
        if len(skin) < 6:
            continue
        centre_z = float((skin[:, 2].min() + skin[:, 2].max()) / 2)
        origin = np.array([0., height, centre_z])
        front, _ = cast(origin, np.array([0., 0., 1.]), faces)
        back, _ = cast(origin, np.array([0., 0., -1.]), faces)
        if np.isfinite(front + back) and min(front, back) > .04 * rig.fit_scale:
            # Let both faces out independently.  Recentring a band on its
            # backplate must never pay for that move by burying its front.
            want_front = max(float(np.percentile(skin[:, 2], 98)) + clearance,
                             centre_z + front) + .008 * rig.fit_scale
            want_back = min(float(np.percentile(skin[:, 2], 2)) - clearance,
                            centre_z - back)
            depth_factors[row] = np.clip(
                (want_front - want_back) / (front + back), 1., 2.)
            depth_shifts[row] = ((want_front + want_back) / 2
                                - (centre_z + (front - back) / 2)
                                * depth_factors[row])
        lining = []
        for sign in (-1., 1.):
            distance, _ = cast(origin, np.array([sign, 0., 0.]), faces)
            # A tab crossing the cavity is not a torso side wall.  Reject
            # that band instead of saturating the profile on the tab.
            if np.isfinite(distance) and distance > .06 * rig.fit_scale:
                lining.append(distance)
        if len(lining) != 2:
            continue
        want = float(np.percentile(np.abs(skin[:, 0]), 98)) + clearance
        factors[row] = np.clip(want / min(lining), .85, 1.8)
    good = np.isfinite(factors)
    if not good.any():
        return {"bands": 0}
    factors = np.interp(heights, heights[good], factors[good])
    for _ in range(2):
        factors = np.convolve(np.pad(factors, 1, mode="edge"),
                              [.25, .5, .25], mode="valid")
    for column, default in ((depth_factors, 1.), (depth_shifts, 0.)):
        valid = np.isfinite(column)
        column[:] = (np.interp(heights, heights[valid], column[valid])
                     if valid.any() else default)
        for _ in range(2):
            column[:] = np.convolve(np.pad(column, 1, mode="edge"),
                                    [.25, .5, .25], mode="valid")
    # The neck opening has its own size.  Do not extrapolate shoulder width
    # up into the collar, or the collar becomes a second pair of shoulders.
    heights = np.r_[ea.TORSO_HEM * rig.fit_scale, heights, 1.50 * rig.fit_scale]
    factors = np.r_[1., factors, 1.]
    depth_factors = np.r_[1., depth_factors, 1.]
    depth_shifts = np.r_[0., depth_shifts, 0.]
    canon, edges, count = _weld(points, triangles)
    labels = _components(edges, count)[canon]
    before = points.copy()
    short_shells = 0
    for label in np.unique(labels[movable]):
        member = labels == label
        if not movable[member].all():
            continue
        block = before[member]
        if np.ptp(block[:, 1]) <= WHOLE_SHELL * rig.fit_scale:
            short_shells += 1
            centre = block.mean(axis=0)
            factor = np.interp(centre[1], heights, factors)
            points[member, 0] += centre[0] * (factor - 1.)
            points[member, 2] += (
                centre[2] * (np.interp(centre[1], heights, depth_factors) - 1.)
                + np.interp(centre[1], heights, depth_shifts))
        else:
            points[member, 0] *= np.interp(block[:, 1], heights, factors)
            points[member, 2] = (
                block[:, 2] * np.interp(block[:, 1], heights, depth_factors)
                + np.interp(block[:, 1], heights, depth_shifts))
    return {"bands": int(good.sum()), "shortShells": short_shells,
            "heights": np.round(heights, 3).tolist(),
            "widthFactors": np.round(factors, 3).tolist(),
            "depthFactors": np.round(depth_factors, 3).tolist(),
            "depthShifts": np.round(depth_shifts, 3).tolist(),
            "maxMove": round(float(np.abs(points - before).max()), 4)}


def _raise_sunken_front(points: np.ndarray, rig: ea.Rig, region: str,
                        movable: np.ndarray, target_clear: float,
                        triangles: np.ndarray | None = None,
                        rows: int = 12, most: float = 0.04) -> int:
    """Slide each height band of the trunk forward until its front clears.

    `_slim_to_body` measures one half-extent per axis about a fixed centre, so
    on the depth axis it cannot tell a breastplate from a backplate: whichever
    reaches further sets the number, and a piece whose front is sunk while its
    back stands proud reads as correctly sized.  That is what the yoke of a
    generated cuirass does.  Seated, the phoenix cuirass sits 13-17 mm too far
    BACK across the shoulders -- its breastplate 9 mm inside the pecs while its
    backplate stands 17 mm off the shoulder blades -- and since the liner is
    lifted 8 mm off the skin, the underlayer wins the depth test across the
    whole upper chest.  The armour was there; the player saw a black yoke.

    Front only, and forward only.  Fitting both faces at once was tried and is
    wrong: several bands of a generated cuirass are shallower at the BACK than
    the body is, so a two-faced fit drags the whole band backwards to deepen a
    backplate and sinks a chest that was already clear.  The back has its own
    pass -- `_floor_backplate` runs next and clamps anything this leaves inside
    the liner -- so this one only ever answers the question it can measure.
    """
    body = region_points(rig, region)
    low, high = float(body[:, 1].min()), float(body[:, 1].max())
    shifts = np.zeros(rows)
    centres = low + (high - low) * (np.arange(rows) + 0.5) / rows
    moved = 0
    for row in range(rows):
        lo = low + (high - low) * row / rows
        hi = low + (high - low) * (row + 1) / rows
        skin = body[(body[:, 1] >= lo) & (body[:, 1] < hi)]
        here = (points[:, 1] >= lo) & (points[:, 1] < hi) & movable
        if len(skin) < 6 or int(here.sum()) < 6:
            continue
        want = float(np.percentile(skin[:, 2], 92.0)) + target_clear
        have = float(np.percentile(points[here][:, 2], 92.0))
        shifts[row] = float(np.clip(want - have, 0.0, most))
        if shifts[row] > 1e-4:
            moved += int(here.sum())
    if not (shifts > 1e-4).any():
        return 0
    # Ramped between bands: a step in depth from one band to the next would
    # tear the shell along a horizontal line.
    for _ in range(2):
        shifts = np.convolve(np.pad(shifts, 1, mode="edge"),
                             [1 / 3.0, 1 / 3.0, 1 / 3.0], mode="valid")
    move = np.zeros(len(points))
    move[movable] = np.interp(points[movable, 1], centres, shifts)
    # The ramp belongs to the trunk shell, which is tall enough to follow it.
    # A shell SHORTER than one band has no ramp to follow, and giving it one
    # shears it: these designs stud the plate with rivets a few millimetres
    # thick, and a 7 mm shell told to move 10 mm more at its top than at its
    # bottom turns inside out and renders as a hole.  Each of those travels on
    # one number, read at its own height.
    if triangles is not None and len(triangles):
        canon, edges, welded = _weld(points, triangles)
        labels = _components(edges, welded)[canon]
        for label in np.unique(labels[movable]):
            member = labels == label
            here = points[member, 1]
            if float(here.max() - here.min()) > WHOLE_SHELL:
                continue
            move[member] = np.interp(float(here.mean()), centres, shifts)
    points[:, 2] += np.where(movable, move, 0.0)
    return moved


def _settle_floaters(points: np.ndarray, triangles: np.ndarray, rig: ea.Rig,
                     region: str, limit: float = 0.05,
                     rest: float = 0.025,
                     body: np.ndarray | None = None) -> int:
    """Bring ornaments that hover back onto the wearer.

    A concept sheet draws its mantles and sashes against the body it was
    drawn on; seated onto a different body, a small welded ornament can
    end up hanging in the air beside the wearer with nothing touching it
    -- the sunmane shirts stood a fur mantle nine centimetres clear.  Any
    small component whose closest approach exceeds ``limit`` slides
    straight toward the body until it rests ``rest`` from it, which keeps
    its shape and its place in the design while taking the float out.
    Large components are the garment itself and are never moved.

    The body it settles onto has to be the body the garment can actually rest
    on.  A torso region measures against ``TORSO_BONES``, which stop at the
    clavicles, so a bracer worn correctly out on the forearm has nothing within
    reach of it and reads as hanging in mid-air: it was being dragged 22 cm in
    onto the chest, which is what collapsed the bicep and forearm plates of the
    legendary hero cuirass into one lump on the upper arm.  Callers that dress
    a limb pass the wider body their garment is skinned to.
    """
    if body is None:
        body = region_points(rig, region)
    inverse, edges, count = _weld(points, triangles)
    labels = _components(edges, count)[inverse]
    settled = 0
    for label in np.unique(labels):
        members = labels == label
        size = int(members.sum())
        if size < 8 or size > 220:
            continue
        block = points[members]
        gaps = np.linalg.norm(
            body[None, :, :] - block[:, None, :], axis=2)
        near = int(np.argmin(gaps.min(axis=0)))
        gap = float(gaps.min())
        if gap <= limit:
            continue
        source = block[int(np.argmin(gaps[:, near]))]
        toward = body[near] - source
        span = float(np.linalg.norm(toward))
        if span < 1e-6:
            continue
        points[members] += toward / span * (gap - rest)
        settled += 1
    return settled


#: A shell shorter than this travels whole rather than following a per-height
#: ramp or clamp, in metres, measured on the shell's own height.  Two bands:
#: the trunk shell of a torso piece runs the garment's whole span, 0.42 m on
#: the phoenix cuirass and never near this, while the studs and plaques on it
#: run to 0.10.  Moving a shell whole is always safe -- it cannot flatten or
#: shear anything -- so the line is drawn well clear of the ornaments rather
#: than finely between them; the only cost of catching one too many is that a
#: shell with relief travels by its deepest recess instead of filling it.
#: The passes that move the trunk in depth reason
#: about a tall shell with relief on it -- a ramp it can follow, a recess that
#: can be filled while its outer wall holds the shape.  These designs also stud
#: that plate with rivets and bosses a centimetre across, and every such pass
#: destroys one: a ramp shears it, a clamp flattens it, a clamp that catches
#: only half of it turns it inside out.  Shorter than a band means there is no
#: ramp to follow and no outer wall to hold, so it moves as a body.
WHOLE_SHELL = 0.16


def _floor_backplate(points: np.ndarray, rig: ea.Rig, region: str,
                     movable: np.ndarray,
                     triangles: np.ndarray | None = None) -> int:
    """Keep the back panel outside the liner, band by band.

    The banded slim scales each band by its proudest plates, so a back with
    deep relief -- raised bosses over recessed panels -- lands its recesses
    INSIDE the 8 mm liner, and the wearer shows a patchwork of armour and
    underpadding from behind.  Any back-half vertex nearer the body than the
    liner line is pushed straight back out to it; inner shell walls get carried
    along, which only thickens hidden geometry.

    Except when there is no outer wall to stay put.  A small hollow ornament
    lying wholly inside the line has every one of its vertices clamped to the
    same z and collapses to a flat sheet -- a closed shell enclosing zero
    volume, which `TorsoShellTest` reads as wound inside out and the renderer
    draws as a transparent hole.  Such a shell is moved back whole instead, by
    the least its deepest vertex needs, which is the same reason
    `_clear_sleeves` scales a band rather than a vertex.  Shells that straddle
    the line keep the clamp: their outer wall holds the shape while the recess
    is filled, and that is what the clamp is for.
    """
    body = region_points(rig, region)
    floored = 0
    limits = np.zeros(len(points))
    inside = np.zeros(len(points), dtype=bool)
    for lo, hi in ((0.92, 1.00), (1.00, 1.12), (1.12, 1.24), (1.24, 1.36),
                   (1.36, 1.48), (1.48, 1.58)):
        skin = body[(body[:, 1] >= lo) & (body[:, 1] < hi)]
        if len(skin) < 6:
            continue
        limit = float(np.percentile(skin[:, 2], 2.0)) - (SKIN_STANDOFF + 0.006)
        band = (movable & (points[:, 1] >= lo) & (points[:, 1] < hi)
                & (points[:, 2] < 0.0) & (np.abs(points[:, 0]) < 0.22))
        limits[band] = limit
        inside |= band & (points[:, 2] > limit)
    if not inside.any():
        return 0
    whole = np.zeros(len(points), dtype=bool)
    if triangles is not None and len(triangles):
        canon, edges, welded = _weld(points, triangles)
        labels = _components(edges, welded)[canon]
        for label in np.unique(labels[inside]):
            member = labels == label
            here = points[member, 1]
            # Short shells only.  A tall one keeps the clamp even when nothing
            # of it is behind the line yet: it has relief to fill and an outer
            # wall to hold the shape, and moving it as a body is not a subtler
            # version of that -- the trunk shell qualified on one build and the
            # whole breastplate went 200 mm back, behind the wearer's chest.
            if float(here.max() - here.min()) > WHOLE_SHELL:
                continue
            offset = float(np.min(limits[member & inside]
                                  - points[member & inside, 2]))
            points[member, 2] += offset
            whole |= member
            floored += int(member.sum())
    clamp = inside & ~whole
    if clamp.any():
        points[clamp, 2] = limits[clamp]
        floored += int(clamp.sum())
    return floored


def _flatten_bust(points: np.ndarray, rig: ea.Rig, region: str,
                  movable: np.ndarray) -> int:
    """Press the chest panel flat against the wearer.

    Several concept sheets draw their breastplates with a bust, and the
    banded slim can only SCALE a band -- a localised dome keeps its shape
    at any scale, so the male chest ends up wearing one.  Within the
    chest band, any front vertex standing prouder than the body's own
    front line plus clearance and a little plate relief is pulled
    straight back in z.  A clamp, not a scale: flat panels and trim stay
    exactly where the fit put them.
    """
    body = region_points(rig, region)
    clamped = 0
    for lo, hi in ((1.20, 1.28), (1.28, 1.36), (1.36, 1.44), (1.44, 1.50)):
        skin = body[(body[:, 1] >= lo) & (body[:, 1] < hi)]
        if len(skin) < 6:
            continue
        allowed = float(np.percentile(skin[:, 2], 98.0)) + 0.030
        band = (movable & (points[:, 1] >= lo) & (points[:, 1] < hi)
                & (points[:, 2] > allowed) & (np.abs(points[:, 0]) < 0.20))
        if band.any():
            points[band, 2] = allowed
            clamped += int(band.sum())
    return clamped


def _push_waist_out(points: np.ndarray, waist: np.ndarray, rig: ea.Rig,
                    clearance: float) -> int:
    """Push waistband vertices that sit inside the body out to the skin.

    The banded slim-and-grow levels whole rows, but a row that mixes deep
    side tassets with a shallow front panel satisfies its percentile while
    the panel stays sunk.  This is the per-vertex remainder, done the only
    way a closed solid tolerates: parity against the actual body mesh picks
    the vertices genuinely inside the skin -- the garment's own inner
    surface, lying between shell and body, is outside the body and never
    moves -- and each one rides a radial ray to just past the surface it
    was under.
    """
    faces = getattr(rig, "faces", None)
    if faces is None or not waist.any():
        return 0
    soup = rig.positions[faces]
    near = soup[(soup[:, :, 1].min(axis=1) < 1.25)
                & (soup[:, :, 1].max(axis=1) > 0.85)]
    if not len(near):
        return 0
    probe = np.array([0.2913, 0.0412, 0.9557])
    probe /= np.linalg.norm(probe)
    index = np.nonzero(waist)[0]
    inside = gf._crossings(points[index], near, probe) % 2 == 1
    moved = 0
    for vertex in index[inside]:
        point = points[vertex]
        outward = np.array([point[0], 0.0, point[2]])
        length = float(np.linalg.norm(outward))
        if length < 1e-6:
            outward = np.array([0.0, 0.0, 1.0])
        else:
            outward /= length
        distance, crossings = cast(point, outward, near)
        if np.isfinite(distance) and crossings % 2 == 1:
            points[vertex] = point + outward * (distance + clearance)
            moved += 1
    return moved


def _make_winding_coherent(surface) -> int:
    """Turn the odd triangle that is wound against the rest of its shell.

    A shell's facets have to agree about which side is out, and the generated
    meshes do not always agree: the legendary hero cuirass's collar has 8 of
    its 34 front facets wound inwards, and a backface-culled facet is a hole --
    the player looks through the collar wall into the inside of the piece and
    it reads as an open funnel rather than a standing collar.  Every proportion
    of that collar measures faithful to the design, which is why this took a
    while to find: the geometry was right and a quarter of it was invisible.

    Orientation is propagated across shared edges, which decides the winding of
    every facet in a shell relative to its neighbours.  Which way round that
    goes is then settled by area: the sense most of the shell already has, so
    only the minority ever moves.  A whole shell wound inwards is the other
    problem and `_unwind_inverted_shells` has the measurement for it.

    Vertex normals follow the winding only where a vertex's triangles ALL
    turned; one on the seam between a turned facet and a kept one has no answer
    that suits both, and a shading seam there is worth less than a hole.
    """
    points = surface.positions
    triangles = surface.indices.reshape(-1, 3)
    if len(triangles) < 2:
        return 0
    canon, _edges, _count = _weld(points, triangles)
    keyed = canon[triangles]
    # Every directed edge, in the order its own triangle walks it.
    starts = keyed[:, [0, 1, 2]].reshape(-1)
    ends = keyed[:, [1, 2, 0]].reshape(-1)
    owner = np.repeat(np.arange(len(triangles)), 3)
    low = np.minimum(starts, ends)
    high = np.maximum(starts, ends)
    forward = starts < ends
    order = np.lexsort((forward, high, low))
    low, high, forward, owner = (low[order], high[order], forward[order],
                                 owner[order])
    same = (low[1:] == low[:-1]) & (high[1:] == high[:-1])
    pairs = np.flatnonzero(same)
    if not len(pairs):
        return 0
    left, right = owner[pairs], owner[pairs + 1]
    # Two triangles agree when they walk their shared edge in OPPOSITE
    # directions; walking it the same way means one of them is inside out.
    agree = forward[pairs] != forward[pairs + 1]

    flip = np.zeros(len(triangles), dtype=bool)
    seen = np.zeros(len(triangles), dtype=bool)
    order_of = np.argsort(left, kind="stable")
    left_sorted = left[order_of]
    first = np.searchsorted(left_sorted, np.arange(len(triangles)), "left")
    last = np.searchsorted(left_sorted, np.arange(len(triangles)), "right")
    back_of = np.argsort(right, kind="stable")
    right_sorted = right[back_of]
    first_r = np.searchsorted(right_sorted, np.arange(len(triangles)), "left")
    last_r = np.searchsorted(right_sorted, np.arange(len(triangles)), "right")

    corner = points[triangles]
    area = 0.5 * np.linalg.norm(np.cross(corner[:, 1] - corner[:, 0],
                                         corner[:, 2] - corner[:, 0]), axis=1)
    turned = 0
    for seed in range(len(triangles)):
        if seen[seed]:
            continue
        seen[seed] = True
        stack = [seed]
        shell = [seed]
        while stack:
            here = stack.pop()
            for table, other, lo, hi in ((order_of, right, first, last),
                                         (back_of, left, first_r, last_r)):
                for slot in table[lo[here]:hi[here]]:
                    there = int(other[slot])
                    if seen[there]:
                        continue
                    seen[there] = True
                    flip[there] = flip[here] ^ (not bool(agree[slot]))
                    shell.append(there)
                    stack.append(there)
        shell = np.asarray(shell)
        turning = flip[shell]
        if float(area[shell][turning].sum()) > float(area[shell][~turning].sum()):
            flip[shell] = ~turning
        turned += int(flip[shell].sum())
    if not flip.any():
        return 0
    faces = triangles.copy()
    faces[flip] = faces[flip][:, [0, 2, 1]]
    kept = np.zeros(len(points), dtype=bool)
    np.logical_or.at(kept, triangles[~flip].reshape(-1), True)
    moved = np.zeros(len(points), dtype=bool)
    np.logical_or.at(moved, triangles[flip].reshape(-1), True)
    surface.normals[moved & ~kept] = -surface.normals[moved & ~kept]
    surface.indices = faces.reshape(-1)
    return turned


def _unwind_inverted_shells(surface) -> int:
    """Turn any closed shell that is wound inside out the right way round.

    The generated meshes stud their plate with rivets, bosses and buckles, and
    a good number of those arrive from the generator with their faces wound
    inwards -- 138 of them across the torso set, none bigger than 65 vertices.
    A closed shell wound inwards has its near wall backface-culled, so the
    player sees straight through the ornament to the armour behind it, and
    `TorsoShellTest` reads it as the piece enclosing nothing.

    It went unnoticed because the passes that move the trunk in depth used to
    flatten these shells to nothing, which reads as neither wound nor unwound.
    Now that a short shell travels whole the source's own winding survives to
    the file, so it has to be right.  Signed volume says which way round a
    closed shell is; open shells are left alone, because the sign means nothing
    for them.
    """
    points = surface.positions
    triangles = surface.indices.reshape(-1, 3)
    if not len(triangles):
        return 0
    canon, edges, welded = _weld(points, triangles)
    labels = _components(edges, welded)[canon]
    turned = 0
    for label in np.unique(labels):
        member = labels == label
        mine = member[triangles].all(axis=1)
        faces = triangles[mine]
        if len(faces) < 4:
            continue
        pairs = np.sort(canon[faces[:, [0, 1, 1, 2, 2, 0]]].reshape(-1, 2),
                        axis=1)
        _, counts = np.unique(pairs, axis=0, return_counts=True)
        if not bool((counts == 2).all()):
            continue
        # Diagnose the coordinates that the GLB will actually store, about
        # their own centroid. Absolute-world determinants lose the sign of
        # tiny buckles after float32 export near Y=1 m.
        local = points.astype(np.float32).astype(np.float64)
        local -= local[member].mean(axis=0)
        a, b, c = local[faces[:, 0]], local[faces[:, 1]], local[faces[:, 2]]
        volume = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
        if volume >= 0.0:
            continue
        triangles[mine] = faces[:, [0, 2, 1]]
        surface.normals[member] = -surface.normals[member]
        turned += 1
    surface.indices = triangles.reshape(-1)
    return turned


def _drop_orphan_shards(surface, max_verts: int = 60,
                        min_gap: float = 0.04, steps: list | None = None) -> int:
    """Delete tiny welded fragments floating clear of the garment.

    The concept-sheet meshes ship with debris -- splinters of strap or
    spike a few dozen vertices big that happen to sit inside other
    geometry and go unnoticed until a fit change (a narrower body, a
    moved cap) leaves one hanging in the air beside the shoulder.  A
    fragment is dropped when it is small and its nearest distance to the
    rest of the garment exceeds ``min_gap``; anything touching or large
    is design, not debris.  Returns how many fragments went.
    """
    triangles = surface.indices.reshape(-1, 3)
    inverse, edges, count = _weld(surface.positions, triangles)
    labels = _components(edges, count)[inverse]
    unique, sizes = np.unique(labels, return_counts=True)
    if len(unique) < 2:
        return 0
    drop = np.zeros(len(surface.positions), dtype=bool)
    dropped = 0
    for comp, size in zip(unique, sizes):
        if size > max_verts:
            continue
        members = labels == comp
        rest = ~members
        if not rest.any():
            continue
        mine = surface.positions[members]
        others = surface.positions[rest]
        gap = np.inf
        for point in mine:
            gap = min(gap, float(np.min(
                np.linalg.norm(others - point, axis=1))))
            if gap <= min_gap:
                break
        if gap > min_gap:
            drop |= members
            dropped += 1
    if not dropped:
        return 0
    keep = ~drop
    remap = np.cumsum(keep) - 1
    face_keep = keep[triangles].all(axis=1)
    # The repose's masks are indexed by vertex, so dropping vertices
    # without shrinking them leaves every later pass reading the wrong
    # rows -- and `_harden_plates` reading past the end.
    for step in steps or []:
        for key in ("sleeve", "cap"):
            if key in step:
                step[key] = np.asarray(step[key], dtype=bool)[keep]
    surface.positions = surface.positions[keep]
    surface.normals = surface.normals[keep]
    surface.uvs = surface.uvs[keep]
    surface.indices = remap[triangles[face_keep]].reshape(-1)
    return dropped


def _harden_plates(points: np.ndarray, triangles: np.ndarray, rig: ea.Rig,
                   steps: list[dict], joints: np.ndarray,
                   weights: np.ndarray) -> int:
    """Bind each rigid arm plate to exactly one bone, in place.

    The nearest-surface inheritance is right for the trunk, which drapes like
    the skin it covers, and wrong for plate: a bracer picks up a 0.15 share of
    the upper arm from the verts near its elbow end, and that share smears a
    sixth of every elbow bend into the plate -- in motion the cuff visibly
    trails the forearm it should be riding.  Solids turn whole or not at all
    (the repose rule), so a welded component that the repose called sleeve
    snaps to its own dominant arm bone -- but only when that bone already
    holds a clear majority, so a true elbow-spanning sleeve keeps its blend
    and its bend.  A component the repose called cap instead binds to that
    side's clavicle: a pauldron worn on the shoulder must stay capping it,
    and weighted to the upper arm it dives outboard the moment the idle
    drops the arm.  Returns how many components were hardened.
    """
    inverse, edges, count = _weld(points, triangles)
    parent = np.arange(count)

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in edges:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[rb] = ra
    component = np.array([find(int(i)) for i in inverse])

    sleeve = np.zeros(len(points), dtype=bool)
    cap_side = {}
    for step in steps:
        if not step.get("applied"):
            continue
        if "sleeve" in step:
            sleeve |= np.asarray(step["sleeve"], dtype=bool)
        if "cap" in step:
            side = step["limb"][-1]
            mask = cap_side.get(side, np.zeros(len(points), dtype=bool))
            cap_side[side] = mask | np.asarray(step["cap"], dtype=bool)

    arm_bones = {name % side for name in ("upperarm_%s", "lowerarm_%s",
                                          "hand_%s") for side in "lr"}
    hardened = 0
    for comp in np.unique(component):
        members = component == comp
        total = int(members.sum())
        if total < 4:
            continue
        snap_to = None
        for side, mask in cap_side.items():
            if int((members & mask).sum()) * 2 < total:
                continue
            # A cap binds to the clavicle so it keeps capping the shoulder when
            # the idle drops the arm.  That is only right while it IS a cap.
            # The reach test that named it one was applied to the pose the
            # piece arrived in, and the passes since then stretch a piece to
            # the span the region asks for -- so a shell that covered the joint
            # and stopped can finish reaching past the elbow.  Pinned to the
            # clavicle at that length it cannot follow the arm at all: it hangs
            # at its bind position while the arm leaves, which reads as the
            # pauldron standing too far out and the sleeve under it ending up
            # in the armpit.  Past `CAP_REACH` it keeps the per-vertex blend
            # instead, so its shoulder end rides the shoulder and its outer end
            # rides the arm, which is what a long spaulder does.
            here = points[members]
            joint = rig.origin("upperarm_" + side)
            if float(np.linalg.norm(here - joint, axis=1).max()) > CAP_REACH:
                break
            snap_to = rig.joint_names.index("clavicle_" + side)
            break
        if snap_to is None and int((members & sleeve).sum()) * 2 >= total:
            mass: dict[int, float] = {}
            for slot in range(joints.shape[1]):
                for j, w in zip(joints[members, slot], weights[members, slot]):
                    if w > 0:
                        mass[int(j)] = mass.get(int(j), 0.0) + float(w)
            top = max(mass, key=mass.get)
            share = mass[top] / max(sum(mass.values()), 1e-9)
            if rig.joint_names[top] in arm_bones and share >= 0.55:
                snap_to = top
        if snap_to is None:
            continue
        joints[members] = 0
        joints[members, 0] = snap_to
        weights[members] = 0.0
        weights[members, 0] = 1.0
        hardened += 1
    return hardened


def _slim_legs(points: np.ndarray, rig: ea.Rig, region: str,
               movable: np.ndarray, target_clear: float) -> np.ndarray:
    """Slim each trouser leg onto its own limb.

    The trunk slim centres on one axis, which for a two-tube region is the gap
    between the legs; run there it pinches the inner seams together.  So each
    leg is slimmed separately, split at the crotch (the pelvis x centre),
    against that side's own body points and centre.
    """
    out = points.copy()
    # Only below the hip line: the tube slim measures against the limb's own
    # points, and at waistband height those are upper-thigh verts -- far
    # shallower front-to-back than the belly the waistband actually wraps.
    # Slimmed to them, the waist panels sink inside the torso and the body's
    # painted shirt renders over the top of the trousers.
    hip_line = min(float(rig.origin("thigh_l")[1]),
                   float(rig.origin("thigh_r")[1])) - 0.01
    movable = movable & (points[:, 1] < hip_line)
    left = nearer_limb(points, rig, region)
    for side in ("l", "r"):
        limb = rig._region(measure_bones(region, side))
        own = (left if side == "l" else ~left) & movable
        if int(own.sum()) < 12 or len(limb) < 12:
            continue
        centre = np.array([float(np.median(limb[:, 0])),
                           float(np.median(limb[:, 2]))])
        out = _slim_to_body(out, rig, region, own, target_clear,
                            body_points=limb, centre=centre)
    # The waist is slimmed like the tubes, but against the body it actually
    # wraps -- the skirt region's belly and hips, not the thighs.  Measured
    # against the thighs it sank inside the torso and the body's painted
    # shirt rendered over the trousers; left authored, a deep tasset flares
    # fifteen centimetres proud.  Banded, per-axis and shrink-only, so it
    # hugs the hips and can never pass inside them.
    waist = points[:, 1] >= hip_line
    if region == "legs" and int(waist.sum()) >= 6:
        out = _slim_to_body(out, rig, "skirt", waist, target_clear)
        # Grown to convergence: the row smoothing that keeps banded factors
        # from stepping dilutes an edge row's growth by about a third per
        # pass, and one pass left a centimetre of waistband inside the hip.
        for _ in range(3):
            out = _slim_to_body(out, rig, "skirt", waist, target_clear,
                                grow=True)
        _push_waist_out(out, waist, rig, 0.006)
    return out



def build(source: Path, out: Path, rig: ea.Rig, kind: str, label: str,
          clearance: float = CLEARANCE, fit: str = "seat",
          taper: bool = False,
          flip: bool = False, roll: bool = False,
          span: tuple[float, float] | None = None,
          grip: tuple[float, float, float] | None = None) -> dict:
    """Fit one generated mesh to the rig and write it as a skinned piece."""
    if kind in SOCKET_KIND or (kind in ea.GARMENT_KINDS and ea.garment_region(kind) in ('legs', 'boots')):
        import limb_head_remap
        return limb_head_remap.build(source, out, rig, kind, label, span)
    if kind in PROP_KIND:
        return build_socket(source, out, rig, kind, label, flip, roll, grip)
    if kind not in ea.GARMENT_KINDS:
        raise ValueError(
            "%s is none of a garment kind (%s), a socket kind (%s) or a prop "
            "kind (%s)" % (kind, ", ".join(sorted(ea.GARMENT_KINDS)),
                           ", ".join(sorted(SOCKET_KIND)),
                           ", ".join(sorted(PROP_KIND))))
    region = ea.garment_region(kind)
    if region == "torso":
        # Torso designs are retargeted directly from the original GLB's pose.
        # They must never pass through seat/repose and its compounded girth.
        import torso_remap
        return torso_remap.build(source, out, rig, kind, label)
    if region not in MEASURE:
        raise ValueError(f"no measuring rule for region {region!r}; "
                         f"known: {sorted(MEASURE)}")

    surface, png = read_source(source)
    before = surface.positions.copy()
    triangles = surface.indices.reshape(-1, 3)
    # Seat, repose, and -- only if a pose was actually taken out -- seat
    # again.  The first seat is provisional for a posed piece: a hanging
    # sleeve is part of the height it divides by, so its vertical scale runs
    # ~15% small, but it puts the shoulders and hips where the rig has them,
    # which is what the pose search needs.  The second pass re-derives every
    # measurement from the corrected geometry; its girth ratio re-widens the
    # piece, and that is not the accident it looks like -- it is the same
    # widening the droop denied the first pass, so sleeves squashed while
    # they hung come back out to length once they lie along the arm.  (A
    # uniform second pass was tried instead and measured worse on both
    # counts.)  A piece with no pose to correct is seated once: seat() is not
    # idempotent -- its girth-to-height ratio compounds -- and a second pass
    # over the boots flattened the pair into a half-metre disc.
    seated = seat(surface.positions, rig, region, triangles, taper, span)
    # Kept because the second seat overwrites them, and it is the FIRST pass
    # whose girth-over-height the sleeves have to be given back.
    seated_factors = LAST_SEAT_FACTORS
    tall_before = float(seated[:, 1].max() - seated[:, 1].min())
    seated, surface.normals, posed = repose(
        seated, surface.normals, rig, region, triangles)
    if any(step.get("applied") for step in posed):
        # The second seat is here to give back the girth the droop denied the
        # first: a sleeve hanging at the concept's angle is part of the height
        # the first pass divided by, so a piece drawn arms-down comes out too
        # narrow, and once the sleeves lie along the arm the measurement is
        # honest and the piece can be widened to match.
        #
        # What it must not do is re-derive girth from scratch.  `seat` is not
        # idempotent -- body-height over mesh-height says something only while
        # the mesh is still normalised, and after the first pass it is not.  Run
        # twice on the legendary hero cuirass it reported a height scale of
        # 1.000 and a girth of 1.489: it widened the piece by half again for a
        # droop that had cost it nothing, because the tasset skirt hangs lower
        # than the hands do and the repose never changed the height at all.
        # That is the pauldron reaching a third of the way down the arm.
        #
        # So the second pass is handed the correction rather than left to
        # invent one: the height the repose actually recovered, which is 1.0
        # when it recovered none.
        recovered = tall_before / max(
            float(seated[:, 1].max() - seated[:, 1].min()), 1e-9)
        seated = seat(seated, rig, region, triangles, taper, span,
                      girth=recovered)
    if region == "torso":
        # Equalise the axes, hung from the collar.  The seat scales height to
        # the authored span but girth to the body region, and the height's
        # denominator is a bounding box stretched by whatever strap dangles
        # lowest -- so the chest shell lands a quarter squatter than the
        # concept drew it.  The width the seat picked is right; the height is
        # brought up to the same factor -- read from the seat itself, since
        # a bounding-box comparison is confounded by the reposed sleeves --
        # the collar stays put, and the hem falls where the design's own
        # proportions put it.
        raised, widened = LAST_SEAT_FACTORS
        if widened > raised * 1.02:
            # Below the shoulder line only.  The yoke -- collar, shoulder
            # caps, sleeve tops -- is fitted to the body and must not move;
            # what reads short is the trunk, so the trunk alone stretches
            # down toward the hem.
            stretch = min(widened / raised, 1.35)
            pivot = float(rig.origin("upperarm_l")[1]) - 0.06
            below = seated[:, 1] < pivot
            seated[below, 1] = pivot - (pivot - seated[below, 1]) * stretch
        for step in posed:
            if not step.get("applied") or "sleeve" not in step:
                continue
            pivot_name = str(step.get("pivot", ""))
            shoulder = rig.origin(pivot_name)
            seg_start, seg_end = rig.segment(pivot_name)
            arm_axis = seg_end - seg_start
            arm_axis /= max(np.linalg.norm(arm_axis), 1e-9)
            # Sleeves stop at the wrist.  Every horizontal pass -- the girth
            # reseat, the design's own proportions -- conspires to run the
            # sleeve past the hand, and a cuff over the fingers reads as a
            # mistake however faithful it is to the sheet.  The sleeve set is
            # compressed along the arm about the shoulder until its far edge
            # lands on the wrist; across the arm nothing changes, so cuffs
            # keep their thickness.
            sleeve = np.asarray(step["sleeve"], dtype=bool)
            hand = rig.origin("hand_" + pivot_name[-1])
            # Before anything is measured along the arm: the sleeve is still
            # carrying the trunk's girth correction, and every pass below
            # reads a tube that is half again too fat for its length.
            raised, widened = seated_factors
            step["unsquashed"] = _unsquash_limb(
                seated, np.flatnonzero(sleeve), shoulder, hand,
                raised / max(widened, 1e-9))
            allowed = float(np.linalg.norm(hand - shoulder)) + 0.01
            if sleeve.any():
                travel = (seated[sleeve] - shoulder) @ arm_axis
                forward = travel[travel > 0.02]
                if len(forward) >= 12:
                    furthest = float(np.percentile(forward, 98.0))
                    if furthest > allowed:
                        squeeze = allowed / furthest
                        pull = np.where(travel > 0.0,
                                        travel * (squeeze - 1.0), 0.0)
                        seated[sleeve] += np.outer(pull, arm_axis)
                        step["sleeveSqueeze"] = round(squeeze, 3)
            # And the caps climb the trapezius.  Left at their authored
            # drape they sit on the deltoid with the slope to the neck bare;
            # a pauldron is worn riding up over the shoulder, so each cap
            # slides up and inboard along that slope.
            cap = np.asarray(step["cap"], dtype=bool)
            if cap.any():
                # A pauldron is no more the trunk than a sleeve is, and it is
                # squashed the same way: drawn square on the phoenix cuirass at
                # 0.97 wide per tall, it seats at 1.44 -- so the wings that
                # should sweep UP beside the collar lie flat and stand out from
                # the shoulder like shelves.  Same correction as the sleeve,
                # about the upright through the joint the cap is worn on, which
                # leaves its height and its drape alone.
                raised, widened = seated_factors
                step["capUnsquashed"] = _unsquash_limb(
                    seated, np.flatnonzero(cap), shoulder,
                    shoulder + np.array([0., 1., 0.]),
                    raised / max(widened, 1e-9))
                inboard = -1.0 if shoulder[0] > 0 else 1.0
                # Grown about its own centroid first: the authored caps are
                # cut to the concept's narrow silhouette and leave the round
                # of the shoulder bare, so each spreads a quarter wider
                # before it climbs.
                centroid = seated[cap].mean(axis=0)
                seated[cap] = centroid + (seated[cap] - centroid) * 1.12
                seated[cap] += np.array([inboard * 0.018, 0.042, 0.0])
                step["capRaised"] = True
        step0 = posed[0] if posed else {}
        step0["sleeveGroupsAligned"] = _align_arm_sleeves(
            seated, surface.indices.reshape(-1, 3), rig, posed)
        step0["sleeveAxesTrued"] = _true_sleeve_axes(
            seated, surface.indices.reshape(-1, 3), rig, posed)
        step0["sleeveRingsCentred"] = _centre_sleeves(
            seated, surface.indices.reshape(-1, 3), rig, posed)
        # The seat's single girth is provisional.  Fit the trunk against its
        # lining now that the repose has identified the limbs.  This replaces
        # the shrink-only point-cloud fit and the front/back vertex clamps:
        # those narrowed the chest by its ornaments and flattened solid walls.
        # Sleeves and caps already fit their limbs, so they remain exempt.
        exempt = np.zeros(len(seated), dtype=bool)
        for step in posed:
            if step.get("applied"):
                exempt |= np.asarray(step.get("sleeve", np.zeros(len(seated))),
                                     dtype=bool)
                exempt |= np.asarray(step.get("cap", np.zeros(len(seated))),
                                     dtype=bool)
        step0["trunkProfile"] = _fit_trunk_profile(
            seated, triangles, rig, ~exempt, clearance)
        step0["floatersSettled"] = _settle_floaters(
            seated, surface.indices.reshape(-1, 3), rig, region,
            body=rig._region(list(ea.GARMENT_SKIN[region])
                             + REPOSE_SKIN.get(region, [])))
        # And the one pass that lets geometry OUT.  Everything above pulls the
        # piece in against the body; a sleeve seated inside the arm needs the
        # opposite, or the liner surfaces through it and the shoulder goes
        # black.
        seated, step0["sleevesCleared"] = _clear_sleeves(seated, rig, exempt)
    elif region in ("legs", "boots"):
        # Legwear is chunky for the same reason: sized to the design's own
        # girth, it stands proud of the leg.  With the leg's own skin hidden
        # under the garment's weighting there is room to draw each tube onto
        # its thigh -- per leg, shrink-only, never inside the limb.  A little
        # more clearance than the torso: knees bend and a trouser cut dead to
        # the calf creases into it.  Boots take the same treatment against
        # calf, foot and ball -- seated to the region box they overshot the
        # foot both fore and aft -- with tighter clearance, since ankles flex
        # less than knees inside a shaft.
        seated = _slim_legs(seated, rig, region,
                            np.ones(len(seated), dtype=bool),
                            clearance + (0.02 if region == "legs" else 0.012))
        # Legwear hangs ornaments too -- knee cloths, boot ties -- and they
        # float for the same reason a mantle does.
        _settle_floaters(seated, surface.indices.reshape(-1, 3), rig, region)
    if fit == "push":
        fitted, pushed = clear_body(seated, rig, region, clearance)
        grown = 1.0
    elif fit == "grow":
        fitted, grown = grow_clear(
            seated, surface.indices.reshape(-1, 3), rig, region,
            clearance)
        pushed = 0
    else:
        fitted, grown, pushed = seated, 1.0, 0
    surface.positions = fitted
    shards = _drop_orphan_shards(surface, steps=posed)
    coherent = _make_winding_coherent(surface)
    unwound = _unwind_inverted_shells(surface)

    glb = ea.EquipmentGLB(generator="Eloria conform_equipment")
    material = textured_material(glb, f"{label} Base", png)
    glb.skeleton(rig)
    positions, normals, uvs, indices = surface.arrays()[0]
    joints, weights = ea.Rig.weights_for(
        rig, positions.astype(np.float64),
        list(ea.GARMENT_SKIN[region]) + REPOSE_SKIN.get(region, []))
    plates = 0
    if region == "torso":
        plates = _harden_plates(positions, surface.indices.reshape(-1, 3),
                                rig, posed, joints, weights)
    primitives = [glb.primitive(positions, normals, uvs, indices, material,
                                joints=joints, weights=weights)]
    glb.mesh(label, primitives, skin=0)
    glb.write(out)

    span_before = (before.max(axis=0) - before.min(axis=0))
    span_after = (fitted.max(axis=0) - fitted.min(axis=0))
    return {"source": source.name, "out": out.name, "kind": kind,
            "region": region, "vertices": int(len(positions)),
            "unwound": unwound, "rewound": coherent,
            "triangles": int(len(indices) // 3),
            "joints": len(rig.joint_names),
            "scale": round(float(span_after[1] / max(span_before[1], 1e-9)), 4),
            "spanBefore": [round(float(v), 3) for v in span_before],
            "spanAfter": [round(float(v), 3) for v in span_after],
            "repose": [{key: value for key, value in step.items()
                        if key not in ("sleeve", "cap")}
                       for step in posed],
            "fit": fit, "grew": round(float(grown), 4),
            "pushedOut": pushed, "textured": png is not None,
            "bytes": out.stat().st_size}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="fit a generated equipment mesh to the body rig and skin it")
    ap.add_argument("input", nargs="+", help="GLB files or directories")
    ap.add_argument("-o", "--output", required=True,
                    help="output file (one input) or directory")
    ap.add_argument("--kind", required=True,
                    help="garment kind (%s), socket kind (%s) or prop kind (%s)"
                         % (", ".join(sorted(ea.GARMENT_KINDS)),
                            ", ".join(sorted(SOCKET_KIND)),
                            ", ".join(sorted(PROP_KIND))))
    ap.add_argument("--race", default="luminous_male",
                    help="race rig to author against (default luminous_male)")
    ap.add_argument("--races-dir", default=str(RACES))
    ap.add_argument("--clearance", type=float, default=CLEARANCE, metavar="M",
                    help="metres to hold off the skin (default %.3f)" % CLEARANCE)
    ap.add_argument("--fit", default="seat",
                    choices=("seat", "grow", "push"),
                    help="seat places the mesh and leaves it alone, which is "
                         "what a generated garment wants; grow and push deform "
                         "it to the body and are escape hatches -- see the "
                         "module docstring before using either")
    ap.add_argument("--taper", action="store_true",
                    help="scale girth per height band instead of once for the "
                         "whole piece.  Experimental: the band measurement "
                         "saturates on multi-shell solids -- see the comment "
                         "in seat() before trusting it")
    ap.add_argument("--flip", action="store_true",
                    help="turn a prop end for end.  Nothing in a mesh says "
                         "which end is the tip, so it is decided by eye")
    ap.add_argument("--pattern", default="*.glb")
    ap.add_argument("--report", default=None, help="write fit measurements here")
    args = ap.parse_args()

    sources: list[Path] = []
    for raw in args.input:
        path = Path(raw).expanduser()
        if path.is_dir():
            sources += sorted(p for p in path.glob(args.pattern) if p.is_file())
        elif path.is_file():
            sources.append(path)
        else:
            print("no such file or directory: %s" % path)
            return 2
    if not sources:
        print("nothing to fit")
        return 2

    race_path = Path(args.races_dir) / f"{args.race}.glb"
    if not race_path.exists():
        print("no such race rig: %s" % race_path)
        return 2
    rig = ea.load_rig(race_path, BODY_MESH)

    out = Path(args.output).expanduser()
    many = len(sources) > 1 or out.is_dir() or not out.suffix
    if many:
        out.mkdir(parents=True, exist_ok=True)

    rows, failed = [], 0
    for source in sources:
        target = (out / (source.stem + ".glb")) if many else out
        label = source.stem.replace("_", " ")[:48]
        try:
            info = build(source, target, rig, args.kind, label,
                         args.clearance, args.fit, args.taper)
        except Exception as exc:
            print("  FAILED %-44s %s" % (source.stem[:44], exc))
            failed += 1
            continue
        rows.append(info)
        print("  %-44s %-7s x%.3f  %d verts  %.2f MB"
              % (source.stem[:44], info.get("attach", "skinned"),
                 info["scale"], info["vertices"], info["bytes"] / 1e6))

    print("\n%d fitted, %d failed, authored against %s"
          % (len(rows), failed, args.race))
    if args.report and rows:
        Path(args.report).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("report: %s" % args.report)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
