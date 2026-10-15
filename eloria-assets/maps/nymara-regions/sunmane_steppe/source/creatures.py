#!/usr/bin/env python3
"""Original Sunmane Steppe livestock, authored on the existing creature rig.

The Sunmane Steppe is a horse culture and the shared creature catalogue has no
equine, so this authors one. The existing deterministic creature generator
builds every animal from the same sphere-and-cylinder blank, which produces a
barrel with legs rather than a horse, so the geometry here is authored to
equine proportions instead: a deep barrel over a narrow chest, a long sloping
neck, a wedge head with a defined muzzle, and legs with real knee, hock and
fetlock breaks.

The skeleton, joint names, animation names and attachment points are exactly
the ones `data/animations/creature.json` and `data/actors/models.json` already
expect, so the asset drops into the client's runtime with no loader change.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[4] / "tools"))
import creature_surfaces  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import textures as texture_kit                          # noqa: E402
from glb import GLBWriter, Geometry, compose            # noqa: E402
from shapes import UV_SCALE, beam, frustum, sphere, box, add_quad   # noqa: E402
import checks                                           # noqa: E402

ASSET_ROOT = HERE.parents[3]
CLIENT_ROOT = ASSET_ROOT.parent / "godot-client"
CREATURE_DIR = CLIENT_ROOT / "assets" / "actors" / "native" / "creatures"

# The shared Eloria creature rig: (name, parent index, translation from parent).
CREATURE_BONES = (
    ("root", -1, (0.0, 0.0, 0.0)), ("body", 0, (0.0, 0.78, 0.0)),
    ("neck", 1, (0.0, 0.22, -0.36)), ("head", 2, (0.0, 0.18, -0.24)),
    ("jaw", 3, (0.0, -0.08, -0.13)),
    ("tail_1", 1, (0.0, 0.02, 0.48)), ("tail_2", 5, (0.0, 0.0, 0.43)),
    ("front_leg_l", 1, (-0.25, -0.18, -0.32)), ("front_shin_l", 7, (0.0, -0.34, 0.0)),
    ("front_paw_l", 8, (0.0, -0.233, -0.08)),
    ("front_leg_r", 1, (0.25, -0.18, -0.32)), ("front_shin_r", 10, (0.0, -0.34, 0.0)),
    ("front_paw_r", 11, (0.0, -0.233, -0.08)),
    ("rear_leg_l", 1, (-0.27, -0.13, 0.33)), ("rear_shin_l", 13, (0.0, -0.38, 0.0)),
    ("rear_paw_l", 14, (0.0, -0.243, -0.04)),
    ("rear_leg_r", 1, (0.27, -0.13, 0.33)), ("rear_shin_r", 16, (0.0, -0.38, 0.0)),
    ("rear_paw_r", 17, (0.0, -0.243, -0.04)),
    ("wing_l", 1, (-0.22, 0.13, 0.0)), ("wing_r", 1, (0.22, 0.13, 0.0)),
)

BONE_INDEX = {name: index for index, (name, _, _) in enumerate(CREATURE_BONES)}


def global_bone_positions(bones=CREATURE_BONES) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for _, parent, translation in bones:
        base = np.zeros(3) if parent < 0 else result[parent]
        result.append(base + np.asarray(translation, dtype="float64"))
    return result


def _quaternion(axis: str, angle: float) -> list[float]:
    half = angle * 0.5
    return {"x": [math.sin(half), 0.0, 0.0, math.cos(half)],
            "y": [0.0, math.sin(half), 0.0, math.cos(half)],
            "z": [0.0, 0.0, math.sin(half), math.cos(half)]}[axis]


class Rigged:
    """Geometry grouped by (joint, material key)."""

    def __init__(self) -> None:
        self.groups: dict[tuple[int, str], Geometry] = {}

    def part(self, joint: str, material: str) -> Geometry:
        key = (BONE_INDEX[joint], material)
        found = self.groups.get(key)
        if found is None:
            found = Geometry()
            self.groups[key] = found
        return found

    @property
    def triangles(self) -> int:
        return sum(geometry.triangle_count for geometry in self.groups.values())


HIDE = "hide"
MANE = "mane"
HOOF = "hoof"
TACK = "tack"


def steppe_horse(*, tacked: bool = False) -> Rigged:
    """A stocky steppe horse: deep barrel, short back, heavy neck, low head."""
    rig = Rigged()
    bones = global_bone_positions()
    body = rig.part("body", HIDE)
    neck = rig.part("neck", HIDE)
    head = rig.part("head", HIDE)

    # --- barrel: a lofted section rather than one sphere ------------------
    #   (z position, half width, half height, centre height)
    sections = ((-0.46, 0.24, 0.26, 0.86), (-0.30, 0.30, 0.32, 0.84),
                (-0.10, 0.32, 0.35, 0.80), (0.14, 0.31, 0.34, 0.78),
                (0.34, 0.27, 0.29, 0.79), (0.50, 0.18, 0.21, 0.82))
    rings = 12
    previous = None
    for z, half_width, half_height, centre in sections:
        ring = []
        for index in range(rings):
            angle = math.tau * index / rings
            ring.append(np.array([math.cos(angle) * half_width,
                                  centre + math.sin(angle) * half_height, z]))
        if previous is not None:
            for index in range(rings):
                following = (index + 1) % rings
                quad = [previous[index], previous[following], ring[following], ring[index]]
                add_quad(body, quad, [[q[2] / 0.9, (q[1] - 0.5) / 0.9] for q in quad])
        previous = ring
    # Cap the chest and the rump.
    for ring, centre, flip in ((previous, np.array([0.0, 0.82, 0.50]), False),):
        for index in range(rings):
            following = (index + 1) % rings
            normal = np.array([0.0, 0.0, 1.0])
            body.add([centre, ring[index], ring[following]],
                     np.tile(normal, (3, 1)),
                     [[0.5, 0.5], [0.0, 0.0], [1.0, 0.0]], [0, 1, 2])
    chest = np.array([0.0, 0.84, -0.46])
    first = [np.array([math.cos(math.tau * i / rings) * 0.24,
                       0.86 + math.sin(math.tau * i / rings) * 0.26, -0.46])
             for i in range(rings)]
    for index in range(rings):
        following = (index + 1) % rings
        body.add([chest, first[following], first[index]],
                 np.tile(np.array([0.0, 0.0, -1.0]), (3, 1)),
                 [[0.5, 0.5], [1.0, 0.0], [0.0, 0.0]], [0, 1, 2])
    # Withers and croup so the topline is not a straight tube.
    sphere(body, (0.0, 0.99, -0.32), 0.15, rings=7, sides=12,
           uv_scale=0.9, squash=0.55)
    sphere(body, (0.0, 0.96, 0.28), 0.17, rings=7, sides=12,
           uv_scale=0.9, squash=0.52)

    # --- neck: tapering crest from withers to poll ------------------------
    neck_base = bones[BONE_INDEX["body"]] + np.array([0.0, 0.20, -0.40])
    neck_top = bones[BONE_INDEX["neck"]] + np.array([0.0, 0.14, -0.16])
    for step in range(5):
        t0, t1 = step / 5, (step + 1) / 5
        low = neck_base + (neck_top - neck_base) * t0
        high = neck_base + (neck_top - neck_base) * t1
        frustum(neck, tuple(low), tuple(high), 0.215 - 0.055 * t0,
                0.215 - 0.055 * t1, sides=10, uv_scale=0.9,
                cap_start=False, cap_end=False)

    # --- head: wedge skull, cheek, muzzle, ears ---------------------------
    poll = bones[BONE_INDEX["head"]] + np.array([0.0, 0.02, -0.04])
    muzzle = poll + np.array([0.0, -0.16, -0.34])
    frustum(head, tuple(poll), tuple(poll + np.array([0.0, -0.06, -0.16])),
            0.135, 0.115, sides=9, uv_scale=0.6, cap_start=True, cap_end=False)
    frustum(head, tuple(poll + np.array([0.0, -0.06, -0.16])), tuple(muzzle),
            0.115, 0.082, sides=9, uv_scale=0.6, cap_start=False, cap_end=False)
    sphere(head, tuple(muzzle + np.array([0.0, -0.01, -0.03])), 0.088,
           rings=6, sides=9, uv_scale=0.6, squash=0.9)
    sphere(head, tuple(poll + np.array([0.0, -0.04, -0.10])), 0.125,
           rings=6, sides=9, uv_scale=0.6, squash=0.78)
    for side in (-1, 1):
        # Ear.
        base = poll + np.array([side * 0.075, 0.06, 0.02])
        frustum(head, tuple(base), tuple(base + np.array([side * 0.03, 0.13, 0.02])),
                0.038, 0.006, sides=6, uv_scale=0.4, cap_start=True, cap_end=False)
        # Eye ridge.
        sphere(head, tuple(poll + np.array([side * 0.105, -0.02, -0.10])), 0.042,
               rings=5, sides=7, uv_scale=0.4, squash=0.8)
    jaw = rig.part("jaw", HIDE)
    sphere(jaw, tuple(bones[BONE_INDEX["jaw"]] + np.array([0.0, 0.04, 0.02])), 0.085,
           rings=5, sides=8, uv_scale=0.5, squash=0.72)

    # --- mane, forelock and tail ------------------------------------------
    mane = rig.part("neck", MANE)
    for step in range(9):
        t = (step + 0.5) / 9
        along = neck_base + (neck_top - neck_base) * t
        crest = along + np.array([0.0, 0.20 - 0.05 * t, 0.0])
        fall = crest + np.array([0.075 * (1 if step % 2 else -1), -0.20 - 0.06 * t, 0.05])
        add_quad(mane, [crest + np.array([-0.035, 0.0, -0.06]),
                        crest + np.array([0.035, 0.0, -0.06]),
                        fall + np.array([0.035, 0.0, 0.03]),
                        fall + np.array([-0.035, 0.0, 0.03])],
                 [[0, 0], [1, 0], [1, 1], [0, 1]])
        add_quad(mane, [crest + np.array([-0.035, 0.0, -0.06]),
                        crest + np.array([0.035, 0.0, -0.06]),
                        fall + np.array([0.035, 0.0, 0.03]),
                        fall + np.array([-0.035, 0.0, 0.03])],
                 [[0, 0], [1, 0], [1, 1], [0, 1]], flip=True)
    forelock = rig.part("head", MANE)
    add_quad(forelock, [poll + np.array([-0.06, 0.06, -0.02]),
                        poll + np.array([0.06, 0.06, -0.02]),
                        poll + np.array([0.05, -0.10, -0.13]),
                        poll + np.array([-0.05, -0.10, -0.13])],
             [[0, 0], [1, 0], [1, 1], [0, 1]])
    for joint, start, end, radius in (
            ("tail_1", bones[BONE_INDEX["tail_1"]] + np.array([0.0, 0.06, -0.02]),
             bones[BONE_INDEX["tail_1"]] + np.array([0.0, -0.02, 0.22]), 0.075),
            ("tail_2", bones[BONE_INDEX["tail_2"]] + np.array([0.0, -0.02, -0.18]),
             bones[BONE_INDEX["tail_2"]] + np.array([0.0, -0.26, 0.06]), 0.055)):
        frustum(rig.part(joint, HIDE), tuple(start), tuple(end), radius, radius * 0.6,
                sides=8, uv_scale=0.5, cap_start=True, cap_end=True)
    tail_hair = rig.part("tail_2", MANE)
    tail_root = bones[BONE_INDEX["tail_2"]] + np.array([0.0, -0.04, -0.14])
    for step in range(7):
        angle = math.tau * step / 7
        offset = np.array([math.cos(angle) * 0.06, 0.0, math.sin(angle) * 0.05])
        tip = tail_root + offset * 1.6 + np.array([0.0, -0.62, 0.12])
        add_quad(tail_hair, [tail_root + offset + np.array([-0.045, 0.0, 0.0]),
                             tail_root + offset + np.array([0.045, 0.0, 0.0]),
                             tip + np.array([0.03, 0.0, 0.0]),
                             tip + np.array([-0.03, 0.0, 0.0])],
                 [[0, 0], [1, 0], [1, 1.6], [0, 1.6]])
        add_quad(tail_hair, [tail_root + offset + np.array([-0.045, 0.0, 0.0]),
                             tail_root + offset + np.array([0.045, 0.0, 0.0]),
                             tip + np.array([0.03, 0.0, 0.0]),
                             tip + np.array([-0.03, 0.0, 0.0])],
                 [[0, 0], [1, 0], [1, 1.6], [0, 1.6]], flip=True)

    # --- legs: shoulder, cannon and hoof with real breaks -----------------
    for side, prefix in ((-1, "front"), (1, "front"), (-1, "rear"), (1, "rear")):
        upper = "%s_leg_%s" % (prefix, "l" if side < 0 else "r")
        lower = "%s_shin_%s" % (prefix, "l" if side < 0 else "r")
        foot = "%s_paw_%s" % (prefix, "l" if side < 0 else "r")
        top = bones[BONE_INDEX[upper]]
        knee = bones[BONE_INDEX[lower]]
        hoof = bones[BONE_INDEX[foot]]
        thigh = rig.part(upper, HIDE)
        # Heavy forearm/gaskin tapering into a narrow cannon bone.
        frustum(thigh, tuple(top + np.array([0.0, 0.10, 0.0])),
                tuple(top * 0.5 + knee * 0.5), 0.135, 0.088, sides=8,
                uv_scale=0.5, cap_start=True, cap_end=False)
        frustum(thigh, tuple(top * 0.5 + knee * 0.5), tuple(knee), 0.088, 0.062,
                sides=8, uv_scale=0.5, cap_start=False, cap_end=False)
        shin = rig.part(lower, HIDE)
        sphere(shin, tuple(knee), 0.070, rings=5, sides=8, uv_scale=0.4, squash=0.85)
        fetlock = knee * 0.25 + hoof * 0.75 + np.array([0.0, 0.06, 0.0])
        frustum(shin, tuple(knee), tuple(fetlock), 0.058, 0.048, sides=8,
                uv_scale=0.4, cap_start=False, cap_end=False)
        sphere(shin, tuple(fetlock), 0.058, rings=5, sides=8, uv_scale=0.4, squash=0.9)
        keratin = rig.part(foot, HOOF)
        pastern = fetlock + (hoof - fetlock) * 0.45
        frustum(rig.part(foot, HIDE), tuple(fetlock), tuple(pastern), 0.048, 0.044,
                sides=8, uv_scale=0.4, cap_start=False, cap_end=False)
        frustum(keratin, tuple(pastern), tuple(hoof + np.array([0.0, -0.02, 0.0])),
                0.052, 0.062, sides=8, uv_scale=0.3, cap_start=True, cap_end=True)

    if tacked:
        tack = rig.part("body", TACK)
        # Saddle pad and a simple steppe saddle tree.
        box(tack, (0.0, 1.05, -0.10), (0.62, 0.05, 0.60), uv_scale=0.5)
        box(tack, (0.0, 1.13, -0.10), (0.40, 0.12, 0.44), uv_scale=0.5)
        for z in (-0.30, 0.10):
            box(tack, (0.0, 1.20, z), (0.34, 0.14, 0.06), uv_scale=0.4)
        for side in (-1, 1):
            beam(tack, (side * 0.30, 1.06, -0.10), (side * 0.34, 0.72, -0.10), 0.05,
                 uv_scale=0.4)
        # Girth and breast strap.
        for index in range(10):
            a0 = math.pi * index / 10
            a1 = math.pi * (index + 1) / 10
            for sign in (-1, 1):
                beam(tack,
                     (sign * math.sin(a0) * 0.33, 0.80 - math.cos(a0) * 0.36, -0.06),
                     (sign * math.sin(a1) * 0.33, 0.80 - math.cos(a1) * 0.36, -0.06),
                     0.05, 0.03, uv_scale=0.4)
        bridle = rig.part("head", TACK)
        for index in range(10):
            a0 = math.tau * index / 10
            a1 = math.tau * (index + 1) / 10
            centre = poll + np.array([0.0, -0.07, -0.20])
            beam(bridle,
                 tuple(centre + np.array([math.cos(a0) * 0.105, math.sin(a0) * 0.10, 0.0])),
                 tuple(centre + np.array([math.cos(a1) * 0.105, math.sin(a1) * 0.10, 0.0])),
                 0.024, uv_scale=0.3)
    return rig


def _horse_animations(writer: GLBWriter, joint_nodes: list[int]) -> None:
    """Idle, walk, canter and the reaction clips the client's action map names."""
    def node(name: str) -> int:
        return joint_nodes[BONE_INDEX[name]]

    rotate = _quaternion
    # A grazing-and-breathing idle: head dips, tail swishes, weight shifts.
    writer.animation("Idle_A", {
        node("neck"): ("rotation", [0.0, 1.6, 3.2, 4.8],
                       [rotate("x", 0.06), rotate("x", 0.34), rotate("x", 0.30),
                        rotate("x", 0.06)]),
        node("head"): ("rotation", [0.0, 1.6, 3.2, 4.8],
                       [rotate("x", -0.02), rotate("x", 0.26), rotate("x", 0.22),
                        rotate("x", -0.02)]),
        node("tail_1"): ("rotation", [0.0, 1.2, 2.4, 3.6, 4.8],
                         [rotate("y", -0.16), rotate("y", 0.14), rotate("y", -0.12),
                          rotate("y", 0.16), rotate("y", -0.16)]),
        node("body"): ("rotation", [0.0, 2.4, 4.8],
                       [rotate("z", -0.012), rotate("z", 0.012), rotate("z", -0.012)]),
    })
    # Walk: a four-beat gait, diagonal pairs offset by a quarter cycle.
    def swing(amplitude: float, phase: float) -> tuple:
        times = [0.0, 0.25, 0.5, 0.75, 1.0]
        values = [rotate("x", amplitude * math.sin(math.tau * (t + phase)))
                  for t in times]
        return ("rotation", times, values)

    writer.animation("Walk", {
        node("front_leg_l"): swing(0.46, 0.0),
        node("front_shin_l"): swing(0.30, 0.12),
        node("front_leg_r"): swing(0.46, 0.5),
        node("front_shin_r"): swing(0.30, 0.62),
        node("rear_leg_l"): swing(0.42, 0.5),
        node("rear_shin_l"): swing(0.34, 0.62),
        node("rear_leg_r"): swing(0.42, 0.0),
        node("rear_shin_r"): swing(0.34, 0.12),
        node("neck"): ("rotation", [0.0, 0.5, 1.0],
                       [rotate("x", 0.05), rotate("x", -0.03), rotate("x", 0.05)]),
    })
    writer.animation("Jog", {
        node("front_leg_l"): swing(0.86, 0.0),
        node("front_shin_l"): swing(0.55, 0.14),
        node("front_leg_r"): swing(0.86, 0.42),
        node("front_shin_r"): swing(0.55, 0.56),
        node("rear_leg_l"): swing(0.80, 0.58),
        node("rear_shin_l"): swing(0.62, 0.72),
        node("rear_leg_r"): swing(0.80, 0.10),
        node("rear_shin_r"): swing(0.62, 0.24),
        node("body"): ("rotation", [0.0, 0.5, 1.0],
                       [rotate("x", -0.06), rotate("x", 0.06), rotate("x", -0.06)]),
        node("neck"): ("rotation", [0.0, 0.5, 1.0],
                       [rotate("x", -0.10), rotate("x", 0.08), rotate("x", -0.10)]),
    })
    writer.animation("Fighting_Idle", {
        node("neck"): ("rotation", [0.0, 0.6, 1.2],
                       [rotate("x", -0.16), rotate("x", -0.06), rotate("x", -0.16)]),
        node("front_leg_l"): ("rotation", [0.0, 0.6, 1.2],
                              [rotate("x", 0.0), rotate("x", -0.22), rotate("x", 0.0)]),
    })
    writer.animation("Sword_Attack", {
        node("body"): ("rotation", [0.0, 0.22, 0.5],
                       [rotate("x", 0.0), rotate("x", -0.42), rotate("x", 0.0)]),
        node("front_leg_l"): ("rotation", [0.0, 0.22, 0.5],
                              [rotate("x", 0.0), rotate("x", -1.05), rotate("x", 0.0)]),
        node("front_leg_r"): ("rotation", [0.0, 0.22, 0.5],
                              [rotate("x", 0.0), rotate("x", -0.92), rotate("x", 0.0)]),
    })
    writer.animation("Hit_Chest", {
        node("body"): ("rotation", [0.0, 0.16, 0.42],
                       [rotate("z", 0.0), rotate("z", 0.18), rotate("z", 0.0)]),
        node("neck"): ("rotation", [0.0, 0.16, 0.42],
                       [rotate("x", 0.0), rotate("x", -0.30), rotate("x", 0.0)]),
    })
    # Roll about the body, not the root: rotating the root pivots the whole
    # horse about the ground point and drives it through the floor.  The root
    # only drops far enough for the carcass to rest on the surface.
    writer.animation("Death_A", {
        node("root"): ("translation", [0.0, 0.4, 0.8, 1.4],
                       [[0.0, 0.0, 0.0], [0.0, -0.0, 0.0],
                        [0.0, -0.02, 0.0], [0.0, -0.16, 0.0]]),
        node("body"): ("rotation", [0.0, 0.4, 0.8, 1.4],
                       [rotate("z", 0.0), rotate("z", 0.22),
                        rotate("z", 0.55), rotate("z", 0.86)]),
        node("neck"): ("rotation", [0.0, 0.8, 1.4],
                       [rotate("x", 0.0), rotate("x", 0.4), rotate("x", 0.55)]),
        node("front_leg_l"): ("rotation", [0.0, 0.4, 0.8, 1.4],
                              [rotate("x", 0.0), rotate("x", 0.341),
                               rotate("x", 0.62), rotate("x", 0.86)]),
        node("front_leg_r"): ("rotation", [0.0, 0.8, 1.4],
                              [rotate("x", 0.0), rotate("x", 0.55), rotate("x", 0.80)]),
        node("rear_leg_l"): ("rotation", [0.0, 0.8, 1.4],
                             [rotate("x", 0.0), rotate("x", 0.70), rotate("x", 0.94)]),
        node("rear_leg_r"): ("rotation", [0.0, 0.8, 1.4],
                             [rotate("x", 0.0), rotate("x", 0.64), rotate("x", 0.90)]),
    })


PALETTES = {
    "sunmane_steppe_horse": {
        "label": "Sunmane Steppe Horse",
        HIDE: (0.52, 0.31, 0.15, 1.0), MANE: (0.16, 0.11, 0.08, 1.0),
        HOOF: (0.24, 0.21, 0.19, 1.0), TACK: (1.0, 1.0, 1.0, 1.0)},
    "sunmane_dun_mare": {
        "label": "Sunmane Dun Mare",
        HIDE: (0.86, 0.70, 0.42, 1.0), MANE: (0.24, 0.18, 0.12, 1.0),
        HOOF: (0.28, 0.25, 0.22, 1.0), TACK: (1.0, 1.0, 1.0, 1.0)},
    "sunmane_grey_pony": {
        "label": "Sunmane Grey Pony",
        HIDE: (0.80, 0.79, 0.77, 1.0), MANE: (0.36, 0.35, 0.34, 1.0),
        HOOF: (0.26, 0.24, 0.22, 1.0), TACK: (1.0, 1.0, 1.0, 1.0)},
}


def build(slug: str, *, tacked: bool = False, scale: float = 1.0) -> dict:
    """Write one horse GLB and return its catalogue record."""
    palette = PALETTES[slug]
    writer = GLBWriter("Eloria Sunmane livestock builder 1.0")
    # Full-colour coat, mane, hoof and tack maps with matching normals, so the
    # livestock carry the same surface fidelity as the rest of the creature
    # library rather than a flat tinted greyscale.
    surfaces = {HIDE: "coat", MANE: "fur", HOOF: "stone", TACK: "cloth"}
    materials = {}
    for key, kind in surfaces.items():
        tone = tuple(int(round(c * 255)) for c in palette[key][:3])
        accent = tuple(min(255, int(c * 0.55 + 90)) for c in tone)
        albedo, _ = creature_surfaces.surface_maps(kind, tone, accent,
                                                   seed=f"{slug}:{key}", size=256)
        _, normal = creature_surfaces.surface_maps(kind, tone, accent,
                                                   seed=f"{slug}:{key}", size=192)
        materials[key] = writer.material(
            f"{slug}_{key}", base_color=(1.0, 1.0, 1.0, 1.0), metallic=0.0,
            roughness=0.72 if key != HOOF else 0.42,
            base_color_texture=writer.texture(albedo, f"{slug}-{key}-basecolor"),
            normal_texture=writer.texture(normal, f"{slug}-{key}-normal"),
            double_sided=key == MANE)

    # Joint hierarchy, mirroring the shared creature rig exactly.
    children: dict[int, list[int]] = {index: [] for index in range(len(CREATURE_BONES))}
    for index, (_, parent, _) in enumerate(CREATURE_BONES):
        if parent >= 0:
            children[parent].append(index)
    joint_nodes: list[int] = []
    for index, (name, parent, translation) in enumerate(CREATURE_BONES):
        joint_nodes.append(writer.node(name, translation=translation,
                                       in_scene=index == 0))
    for index, kids in children.items():
        if kids:
            writer.doc["nodes"][joint_nodes[index]]["children"] = [
                joint_nodes[child] for child in kids]

    skin = writer.skin("Sunmane Livestock Rig", joint_nodes, global_bone_positions())
    rig = steppe_horse(tacked=tacked)
    for (joint, material_key), geometry in rig.groups.items():
        checks.assert_well_formed(geometry, f"{slug}:{CREATURE_BONES[joint][0]}",
                                  allow_reversed=material_key == MANE)
    parts = [(joint, geometry.weld(), materials[material_key])
             for (joint, material_key), geometry in sorted(rig.groups.items())]
    mesh = writer.skinned_mesh(palette["label"], parts, len(CREATURE_BONES))
    writer.node(palette["label"], mesh=mesh, skin=skin)
    _horse_animations(writer, joint_nodes)

    CREATURE_DIR.mkdir(parents=True, exist_ok=True)
    path = CREATURE_DIR / f"{slug}.glb"
    size = writer.write(path)
    statistics = writer.statistics()
    return {"id": slug, "name": palette["label"], "archetype": "equine",
            # POSIX form on every platform; str() on a Windows path yields
            # backslashes, which the Godot side does not resolve.
            "path": path.relative_to(ASSET_ROOT.parent).as_posix(),
            "triangles": statistics["uniqueMeshTriangles"],
            "joints": len(CREATURE_BONES), "animations": 7,
            "glbBytes": size, "tacked": tacked, "importScale": scale}


def main() -> int:
    records = [build("sunmane_steppe_horse", tacked=False, scale=1.25),
               build("sunmane_dun_mare", tacked=False, scale=1.2),
               build("sunmane_grey_pony", tacked=True, scale=1.1)]
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
