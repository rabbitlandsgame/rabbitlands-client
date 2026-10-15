#!/usr/bin/env python3
"""Relax the shared idle: separate the arms, close the stance, face the feet.

Added 2026-09-02 for Eloria Client.

The client rebuilds every actor's clips at runtime from
``Universal_Animation_Library.glb``, copying keys by bone name onto a rig whose
bind pose *is* the library's ``Rest_Pose`` -- so the one place to change how
every humanoid stands at idle is the library's ``Idle_Subtle`` clip itself.
Three things were off once the generated armour went on:

  * the arms hung close enough to the torso that a fitted sleeve overlapped it,
  * the stance was a wide 31 cm at the ankles, and
  * the right foot splayed 45 degrees off forward.

This nudges exactly the six rotation channels responsible -- ``upperarm_l/r``,
``thigh_l/r``, ``foot_l/r`` -- and nothing else in the 162-clip library.  Each
of those channels owns a private output accessor (verified: referenced once,
its own bufferView), so every keyframe's quaternion is rewritten in place at
the same float32 VEC4 layout; no other clip, bone, or byte moves.

The targets are ABSOLUTE, measured by forward-kinematics on the luminous_male
rig, so the tool is idempotent: a second run measures the pose already at
target and writes the same values back.  The corrections are applied as a
world-space rotation conjugated into each bone's own frame
(``delta = G^-1 . R_world . G``), which is why a chained splay -- the foot
turned partly by the thigh and partly by the ankle -- lands facing forward
whichever joints set it.

  python adjust_idle_pose.py            adjust the library in place
  python adjust_idle_pose.py --dry-run  measure and report, write nothing
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
LIBRARY = CLIENT / "assets/actors/native/shared/Universal_Animation_Library.glb"
BODY = CLIENT / "assets/actors/native/races/luminous_male.glb"
CLIP = "Idle_Subtle"

#: The relaxed idle, as forward-kinematic measurements on the luminous_male
#: rig.  Arm drop is the upper arm's angle below horizontal (bigger = closer
#: to the side); the wide authored idle sat at 74, and 66 clears a fitted
#: sleeve while still reading as arms-at-rest.  The shoulder target is the
#: upper-arm joint's forward position: the authored idle holds it 4.6 cm
#: behind the body's centre line, which reads as a puffed chest with the arms
#: hanging behind the torso, so the clavicles protract until the joint sits
#: near the centre line.  The legs are not given a stance target but
#: straightened segment by segment -- the authored clip bows the right leg,
#: knee swung 4 cm out and ankle kicked 10 cm back in -- so the knee lands
#: under the hip and the ankle under the knee, in the frontal plane only (the
#: sagittal crouch is the clip's own and stays).  Feet face straight forward.
TARGET_ARM_DROP = 69.0
#: Both hands land at the same absolute spot: this far in front of the
#: body (the user's 0.1 m forward of where they hung), this far out from
#: the midline, with the same soft elbow bend.
TARGET_HAND_Z = 0.045
#: Per side, in the tool's rest-rooted frame, which sits 16 mm to the
#: right of the runtime one (the pelvis channel recentring) -- so the
#: same world shift SUBTRACTS from the left hand's distance and ADDS to
#: the right's.  These land the REAL hands at 0.250 and 0.265 off the
#: midline: the right two centimetres wider, as reviewed in game.
#: Ten degrees of outward arm rotation moves each hand about nine
#: centimetres further off the midline; the width targets follow, or the
#: steer would quietly fold the abduction back in.
TARGET_HAND_X = {"l": 0.358, "r": 0.341}
TARGET_ELBOW_BEND = 30.0
#: The neck stands vertical -- the authored clip leans it (and the head
#: with it) forward; zero here means the head joint sits directly above
#: the neck joint, stacked over the torso.
TARGET_NECK_FORWARD = 0.0
#: The crown sits level: the head's own up axis steered to world
#: vertical (degrees of sagittal tilt; positive = crown tilted back).
TARGET_HEAD_PITCH = 0.0
#: The stance stands centred: the ankle midpoint sits on the body's own
#: midline (world x zero) once the pelvis channel's lateral drift and the
#: rest pose's own offset are taken out.
TARGET_ANKLE_MID_X = 0.0
TARGET_SHOULDER_FORWARD = -0.016
SAMPLE_AT = 0.1
#: Ground contact, measured from the authored clip as the rest-rooted
#: ankle height PLUS the pelvis channel's own offset above the skeleton
#: rest (0.115 + 0.043) -- the skeleton's rest pose is not the contact
#: reference, the authored channel already rides above it.
TARGET_ANKLE_HEIGHT = 0.158
#: Both feet keep the authored sole slope once the legs verticalise.
TARGET_FOOT_PITCH = -28.8


# --------------------------------------------------------------------------
# Minimal GLB read / in-place patch (numpy only, matching the asset tools)
# --------------------------------------------------------------------------
def read_glb(path: Path):
    data = bytearray(path.read_bytes())
    assert data[:4] == b"glTF", path
    length = struct.unpack_from("<I", data, 8)[0]
    off, js, bin_off, bin_len = 12, None, None, None
    while off < length:
        clen, ctype = struct.unpack_from("<I4s", data, off)
        body = data[off + 8:off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(bytes(body).decode("utf-8"))
        elif ctype == b"BIN\x00":
            bin_off, bin_len = off + 8, clen
        off += 8 + clen
    return data, js, bin_off, bin_len


def accessor_floats(js, data, bin_off, index) -> np.ndarray:
    acc = js["accessors"][index]
    bv = js["bufferViews"][acc["bufferView"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    assert acc["componentType"] == 5126, "expected float32"
    base = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 4 * ncomp)
    out = np.empty((acc["count"], ncomp), dtype=np.float64)
    for i in range(acc["count"]):
        out[i] = struct.unpack_from("<" + "f" * ncomp, data, base + i * stride)
    return out, base, stride, ncomp


def write_floats(data, base, stride, ncomp, values) -> None:
    for i, row in enumerate(values):
        struct.pack_into("<" + "f" * ncomp, data, base + i * stride,
                         *[float(v) for v in row])


# --------------------------------------------------------------------------
# Quaternion / kinematics helpers
# --------------------------------------------------------------------------
def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(m):
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
             (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    else:
        i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
        if i == 0:
            s = np.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
            q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s,
                 (m[2, 1] - m[1, 2]) / s]
        elif i == 1:
            s = np.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
            q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s,
                 (m[0, 2] - m[2, 0]) / s]
        else:
            s = np.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
            q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s,
                 (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def axis_angle_quat(axis, degrees):
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / max(np.linalg.norm(axis), 1e-12)
    half = np.radians(degrees) / 2.0
    s = np.sin(half)
    return np.array([axis[0] * s, axis[1] * s, axis[2] * s, np.cos(half)])


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz])


def node_local(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(node.get("rotation", [0, 0, 0, 1])) @ np.diag(
        node.get("scale", [1, 1, 1]))
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


class Skeleton:
    def __init__(self, path: Path):
        _, js, _, _ = read_glb(path)
        self.js = js
        nodes = js["nodes"]
        self.names = [n.get("name", "") for n in nodes]
        self.parent = [-1] * len(nodes)
        for i, n in enumerate(nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.index = {name: i for i, name in enumerate(self.names)}

    def fk(self, local_rot: dict, deltas: dict) -> dict:
        glob = {}

        def local_of(j):
            name = self.names[j]
            node = self.js["nodes"][j]
            m = np.eye(4)
            # The runtime aliases library track names onto race bones
            # (models.json boneAliases: the library's lowercase "head"
            # drives the race's "Head"), so the FK honours the same
            # fallback -- without it, head-channel edits are invisible
            # here while fully live in the game.
            key = name if name in local_rot else name.lower()
            if key in local_rot:
                q = local_rot[key]
                if key in deltas:
                    q = quat_mul(q, deltas[key])
                rot = quat_to_mat(q)
            else:
                rot = quat_to_mat(node.get("rotation", [0, 0, 0, 1]))
            m[:3, :3] = rot @ np.diag(node.get("scale", [1, 1, 1]))
            m[:3, 3] = node.get("translation", [0, 0, 0])
            return m

        def rec(j, parent):
            glob[j] = parent @ local_of(j)
            for c in self.js["nodes"][j].get("children", []):
                rec(c, glob[j])

        for r in [i for i, p in enumerate(self.parent) if p < 0]:
            rec(r, np.eye(4))
        return glob

    def origin(self, glob, name):
        return glob[self.index[name]][:3, 3]

    def world_delta(self, glob, bone, world_axis, degrees):
        g = glob[self.index[bone]][:3, :3]
        rw = quat_to_mat(axis_angle_quat(world_axis, degrees))
        return mat_to_quat(g.T @ rw @ g)


def sampled_idle(js, data, bin_off) -> tuple[dict, dict]:
    """Local rotation per bone at SAMPLE_AT, and the six target channels'
    (accessor, quats, base, stride, ncomp) for rewriting."""
    names = [n.get("name", "") for n in js["nodes"]]
    anim = next(a for a in js["animations"] if a.get("name") == CLIP)
    local, channels, dur = {}, {}, 0.0
    for ch in anim["channels"]:
        if ch["target"]["path"] != "rotation":
            continue
        sampler = anim["samplers"][ch["sampler"]]
        times, _, _, _ = accessor_floats(js, data, bin_off, sampler["input"])
        times = times[:, 0]
        quats, base, stride, ncomp = accessor_floats(
            js, data, bin_off, sampler["output"])
        dur = max(dur, times[-1])
        bone = names[ch["target"]["node"]]
        channels[bone] = (times, quats, base, stride, ncomp)
    t = None
    for bone, (times, quats, base, stride, ncomp) in channels.items():
        if t is None:
            t = times[-1] * SAMPLE_AT
        i = max(0, min(int(np.searchsorted(times, t, "right")) - 1,
                       len(times) - 1))
        if i + 1 < len(times) and times[i + 1] > times[i]:
            f = (t - times[i]) / (times[i + 1] - times[i])
            a, b = quats[i], quats[i + 1]
            if np.dot(a, b) < 0:
                b = -b
            q = a + (b - a) * f
            local[bone] = q / np.linalg.norm(q)
        else:
            local[bone] = quats[i]
    return local, channels


def solve_angle(measure, target, seed, lo, hi):
    """Bisection for a target on measure(angle).

    The bracket must stay inside the measure's monotone region -- a limb swung
    far enough wraps and the value climbs again, which would fool the sign
    check into clamping to the wrong end."""
    a, b = lo, hi
    fa, fb = measure(a) - target, measure(b) - target
    if fa * fb > 0:  # target outside the bracket; clamp to nearest end
        return a if abs(fa) < abs(fb) else b
    for _ in range(40):
        mid = (a + b) / 2.0
        fm = measure(mid) - target
        if abs(fm) < 1e-4:
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return (a + b) / 2.0


def measurements(sk: Skeleton, glob) -> dict:
    o = lambda n: sk.origin(glob, n)
    arm = o("lowerarm_l") - o("upperarm_l")
    fl, fr = o("ball_l") - o("foot_l"), o("ball_r") - o("foot_r")
    arm_r = o("lowerarm_r") - o("upperarm_r")
    out = {
        "armDrop": float(np.degrees(np.arctan2(-arm[1], abs(arm[0])))),
        "armDropR": float(np.degrees(np.arctan2(-arm_r[1], abs(arm_r[0])))),
        "chestTwist": float(np.degrees(np.arctan2(
            o("upperarm_l")[2] - o("upperarm_r")[2],
            o("upperarm_l")[0] - o("upperarm_r")[0]))),
        "shoulderZ": float((o("upperarm_l")[2] + o("upperarm_r")[2]) / 2.0),
        "ankleGap": float(abs(o("foot_l")[0] - o("foot_r")[0])),
        "footYawL": float(np.degrees(np.arctan2(fl[0], fl[2]))),
        "footYawR": float(np.degrees(np.arctan2(fr[0], fr[2]))),
    }
    for side in ("l", "r"):
        hip, knee, ankle = (o("thigh_" + side), o("calf_" + side),
                            o("foot_" + side))
        out["kneeDx" + side.upper()] = float(knee[0] - hip[0])
        out["ankleDx" + side.upper()] = float(ankle[0] - knee[0])
        out["kneeDz" + side.upper()] = float(knee[2] - hip[2])
        out["ankleDz" + side.upper()] = float(ankle[2] - knee[2])
    out["hipTwist"] = float(np.degrees(np.arctan2(
        o("thigh_l")[2] - o("thigh_r")[2],
        o("thigh_l")[0] - o("thigh_r")[0])))
    out["ankleY"] = float((o("foot_l")[1] + o("foot_r")[1]) / 2.0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="relax the shared Idle_Subtle clip")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data, js, bin_off, _ = read_glb(LIBRARY)
    sk = Skeleton(BODY)
    local, channels = sampled_idle(js, data, bin_off)

    def report(tag, m):
        print("%s arm drop L%.1f R%.1f, chest twist %+.1f, hip twist %+.1f, "
              "shoulder z %+.3f, knee d(x,z) L(%+.3f,%+.3f) R(%+.3f,%+.3f), "
              "ankle d(x,z) L(%+.3f,%+.3f) R(%+.3f,%+.3f), ankle y %.3f, "
              "gap %.1f cm, foot yaw L %.1f R %.1f"
              % (tag, m["armDrop"], m["armDropR"], m["chestTwist"],
                 m["hipTwist"],
                 m["shoulderZ"], m["kneeDxL"], m["kneeDzL"], m["kneeDxR"],
                 m["kneeDzR"], m["ankleDxL"], m["ankleDzL"], m["ankleDxR"],
                 m["ankleDzR"], m["ankleY"], m["ankleGap"] * 100,
                 m["footYawL"], m["footYawR"]))
    report("before:", measurements(sk, sk.fk(local, {})))

    deltas: dict = {}
    # Square the hips before anything above them is measured: the authored
    # clip stands contrapposto, the right hip trailing nine centimetres,
    # which reads from the side as one bent, staggered leg.  The pelvis
    # yaws level about world up and spine_01 counter-yaws so the trunk
    # above keeps its own (separately corrected) facing.
    def hip_twist(angle):
        d = dict(deltas)
        g = sk.fk(local, {})
        d["pelvis"] = sk.world_delta(g, "pelvis", [0, 1, 0], angle)
        return measurements(sk, sk.fk(local, d))["hipTwist"]
    hip_angle = solve_angle(hip_twist, 0.0, 6.0, -25.0, 25.0)
    g = sk.fk(local, {})
    deltas["pelvis"] = sk.world_delta(g, "pelvis", [0, 1, 0], hip_angle)
    g = sk.fk(local, deltas)
    deltas["spine_01"] = sk.world_delta(g, "spine_01", [0, 1, 0], -hip_angle)

    # And LEVEL: the authored pelvis rolls, carrying one hip higher, and
    # with both legs verticalised an uneven hip line becomes uneven feet.
    # Steered by response like every other correction here.
    def hip_level():
        g2 = sk.fk(local, deltas)
        return float(sk.origin(g2, "thigh_l")[1]
                     - sk.origin(g2, "thigh_r")[1])
    start_level = hip_level()
    g = sk.fk(local, deltas)
    probe_q = sk.world_delta(g, "pelvis", [0, 0, 1], 2.0)
    deltas["pelvis"] = quat_mul(deltas["pelvis"], probe_q)
    slope = (hip_level() - start_level) / 2.0
    if abs(slope) > 1e-9:
        g = sk.fk(local, deltas)
        roll_fix = (0.0 - hip_level()) / slope
        deltas["pelvis"] = quat_mul(
            deltas["pelvis"],
            sk.world_delta(g, "pelvis", [0, 0, 1], roll_fix))
        g = sk.fk(local, deltas)
        deltas["spine_01"] = quat_mul(
            deltas["spine_01"],
            sk.world_delta(g, "spine_01", [0, 0, 1], -(2.0 + roll_fix)))

    # De-twist the chest first: the authored clip yaws the whole upper torso
    # about 18 degrees (left shoulder swung forward, right swung back), which
    # is most of why the right shoulder reads pulled behind.  spine_03 turns
    # about world up until the shoulder line is square, and neck_01 counter-
    # turns by the same world rotation so the head keeps facing where it was
    # authored (the clavicles hang off spine_03, the neck subtree does not
    # need the twist).
    def chest_twist(angle):
        d = dict(deltas)
        g = sk.fk(local, {})
        d["spine_03"] = sk.world_delta(g, "spine_03", [0, 1, 0], angle)
        return measurements(sk, sk.fk(local, d))["chestTwist"]
    twist_angle = solve_angle(chest_twist, 0.0, 12.0, -4.0, 30.0)
    g = sk.fk(local, {})
    deltas["spine_03"] = sk.world_delta(g, "spine_03", [0, 1, 0], twist_angle)
    g = sk.fk(local, deltas)
    deltas["neck_01"] = sk.world_delta(g, "neck_01", [0, 1, 0], -twist_angle)

    # The neck stands up: steered about world X until the head joint sits
    # directly above the neck joint rather than leaning ahead of it.  The
    # head rides back with the neck; the authored gaze pointed slightly
    # down, so standing the neck up also levels the face.
    def neck_forward():
        g2 = sk.fk(local, deltas)
        v = sk.origin(g2, "Head") - sk.origin(g2, "neck_01")
        return float(v[2])
    start_neck = neck_forward()
    g = sk.fk(local, deltas)
    probe_n = sk.world_delta(g, "neck_01", [1, 0, 0], 2.0)
    deltas["neck_01"] = (quat_mul(deltas["neck_01"], probe_n)
                         if "neck_01" in deltas else probe_n)
    slope_n = (neck_forward() - start_neck) / 2.0
    if abs(slope_n) > 1e-9:
        g = sk.fk(local, deltas)
        deltas["neck_01"] = quat_mul(
            deltas["neck_01"],
            sk.world_delta(g, "neck_01", [1, 0, 0],
                           (TARGET_NECK_FORWARD - neck_forward()) / slope_n))

    # And the crown levels: the neck fix carried the head back with it,
    # leaving the face tilted up a touch, so the head channel steers
    # about world X until the head's own up axis stands vertical.
    def head_pitch():
        g2 = sk.fk(local, deltas)
        up = g2[sk.index["Head"]][:3, 1]
        return float(np.degrees(np.arctan2(up[2], up[1])))
    start_head = head_pitch()
    g = sk.fk(local, deltas)
    probe_h = sk.world_delta(g, "Head", [1, 0, 0], 2.0)
    deltas["head"] = (quat_mul(deltas["head"], probe_h)
                      if "head" in deltas else probe_h)
    slope_h = (head_pitch() - start_head) / 2.0
    if abs(slope_h) > 1e-9:
        g = sk.fk(local, deltas)
        deltas["head"] = quat_mul(
            deltas["head"],
            sk.world_delta(g, "Head", [1, 0, 0],
                           (TARGET_HEAD_PITCH - head_pitch()) / slope_h))

    # Shoulders forward: each clavicle protracts (a yaw about world up -- the
    # clavicle runs along x, so a pitch about x would spin it in place) until
    # its own upper-arm joint reaches the target forward position.  Per side,
    # because a residual asymmetry survives the de-twist.
    clav_angles = {}
    for side, sign in (("l", -1.0), ("r", 1.0)):
        def one_shoulder(angle, side=side, sign=sign):
            d = dict(deltas)
            g = sk.fk(local, deltas)
            d["clavicle_" + side] = sk.world_delta(
                g, "clavicle_" + side, [0, 1, 0], sign * angle)
            return float(sk.origin(sk.fk(local, d),
                                   "upperarm_" + side)[2])
        clav_angles[side] = solve_angle(one_shoulder, TARGET_SHOULDER_FORWARD,
                                        8.0, -16.0, 32.0)
        g = sk.fk(local, deltas)
        deltas["clavicle_" + side] = sk.world_delta(
            g, "clavicle_" + side, [0, 1, 0], sign * clav_angles[side])

    # Arms: each side solved on its own measurements against the shared
    # targets -- the authored clip hangs the right arm twelve degrees
    # wider, eleven degrees further back, and three times more bent at the
    # elbow than the left, and a symmetric +/- delta preserves every bit
    # of that.  Each correction steers by the pose's measured response.
    def steer(bone, axis, measure, target, probe_deg=2.0):
        start = measure()
        g2 = sk.fk(local, deltas)
        step = sk.world_delta(g2, bone, axis, probe_deg)
        deltas[bone] = (quat_mul(deltas[bone], step)
                        if bone in deltas else step)
        slope = (measure() - start) / probe_deg
        if abs(slope) < 1e-9:
            return
        g2 = sk.fk(local, deltas)
        fix = sk.world_delta(g2, bone, axis, (target - measure()) / slope)
        deltas[bone] = quat_mul(deltas[bone], fix)

    for side in ("l", "r"):
        arm_bone = "upperarm_" + side

        def drop():
            g2 = sk.fk(local, deltas)
            v = sk.origin(g2, "lowerarm_" + side) - sk.origin(g2, arm_bone)
            return float(np.degrees(np.arctan2(-v[1], abs(v[0]))))

        def hand_z():
            g2 = sk.fk(local, deltas)
            return float(sk.origin(g2, "hand_" + side)[2])

        def hand_x():
            g2 = sk.fk(local, deltas)
            return float(abs(sk.origin(g2, "hand_" + side)[0]))

        def bend():
            g2 = sk.fk(local, deltas)
            v = sk.origin(g2, "lowerarm_" + side) - sk.origin(g2, arm_bone)
            f = (sk.origin(g2, "hand_" + side)
                 - sk.origin(g2, "lowerarm_" + side))
            v /= max(np.linalg.norm(v), 1e-9)
            f /= max(np.linalg.norm(f), 1e-9)
            return float(np.degrees(np.arccos(np.clip(np.dot(v, f),
                                                      -1.0, 1.0))))

        steer(arm_bone, [0, 0, 1], drop, TARGET_ARM_DROP)
        # The bend responds nonlinearly over big moves (its axis turns as
        # it grows), so the steer repeats until it lands.
        for _ in range(5):
            if abs(bend() - TARGET_ELBOW_BEND) < 0.5:
                break
            g2 = sk.fk(local, deltas)
            v = sk.origin(g2, "lowerarm_" + side) - sk.origin(g2, arm_bone)
            f = (sk.origin(g2, "hand_" + side)
                 - sk.origin(g2, "lowerarm_" + side))
            axis = np.cross(v, f)
            if np.linalg.norm(axis) < 1e-6:
                break
            steer("lowerarm_" + side, axis / np.linalg.norm(axis), bend,
                  TARGET_ELBOW_BEND)
        # The whole arm pitches until the hand sits at the target reach in
        # front of the body, then the forearm eases in or out until both
        # hands stand the same distance off the midline.
        steer(arm_bone, [1, 0, 0], hand_z, TARGET_HAND_Z)
        steer("lowerarm_" + side, [0, 0, 1], hand_x, TARGET_HAND_X[side])
    arm_angle = 0.0

    # Legs: verticalised segment by segment, in both planes at once.  The
    # authored clip both bows the legs frontally and bends them into a
    # sagittal crouch; each segment takes the single closed-form rotation
    # carrying its own direction onto straight down (axis = v x down), so
    # the knee lands under the hip and the ankle under the knee exactly.
    down = np.array([0.0, -1.0, 0.0])
    for side in ("l", "r"):
        for top, bottom in (("thigh_" + side, "calf_" + side),
                            ("calf_" + side, "foot_" + side)):
            g = sk.fk(local, deltas)
            v = sk.origin(g, bottom) - sk.origin(g, top)
            v = v / max(np.linalg.norm(v), 1e-9)
            axis = np.cross(v, down)
            norm = float(np.linalg.norm(axis))
            if norm < 1e-6:
                continue
            angle = np.degrees(np.arccos(np.clip(np.dot(v, down), -1, 1)))
            deltas[top] = sk.world_delta(g, top, axis / norm, angle)

    # Feet: zero the yaw, then hold both soles at the authored slope --
    # verticalising the calf pitched them with it.
    g = sk.fk(local, deltas)
    now = measurements(sk, g)
    deltas["foot_l"] = sk.world_delta(g, "foot_l", [0, 1, 0], -now["footYawL"])
    deltas["foot_r"] = sk.world_delta(g, "foot_r", [0, 1, 0], -now["footYawR"])
    def foot_pitch(side):
        g2 = sk.fk(local, deltas)
        ankle = sk.origin(g2, "foot_" + side)
        ball = sk.origin(g2, "ball_" + side)
        return float(np.degrees(np.arctan2(ball[1] - ankle[1],
                                           ball[2] - ankle[2])))
    for side in ("l", "r"):
        # Steered by measured response, not a derived sign: the world-X
        # delta conjugated through the foot's basis turned the first draft
        # the wrong way and put the heels through the floor.
        start = foot_pitch(side)
        g = sk.fk(local, deltas)
        probe = sk.world_delta(g, "foot_" + side, [1, 0, 0], 2.0)
        deltas["foot_" + side] = quat_mul(deltas["foot_" + side], probe)
        slope = (foot_pitch(side) - start) / 2.0
        if abs(slope) > 1e-6:
            g = sk.fk(local, deltas)
            fix = sk.world_delta(g, "foot_" + side, [1, 0, 0],
                                 (TARGET_FOOT_PITCH - foot_pitch(side))
                                 / slope)
            deltas["foot_" + side] = quat_mul(deltas["foot_" + side], fix)

    # Pelvis height: straight legs reach further down than crouched ones,
    # so the hips rise until the soles sit back at the authored contact
    # height.  This is the one translation edit; the channel is private to
    # this clip.  The FK above ignores the clip's pelvis translation, so
    # the lift must credit whatever offset the channel already carries --
    # without that, every rerun would hoist the hips another three
    # centimetres.
    # The pelvis channel is authored in the pelvis node's PARENT frame,
    # which is rotated (its local y points along world forward), so both
    # the lift axis and the already-carried offset must go through the
    # parent's basis -- adding to the raw y component once walked the hips
    # three centimetres forward instead of up.
    names_lift = [n.get("name", "") for n in js["nodes"]]
    anim_lift = next(a for a in js["animations"] if a.get("name") == CLIP)
    # The up axis expressed in the pelvis channel's own frame comes from
    # the same Skeleton matrices every other measure here uses -- deriving
    # it from raw node quaternions with a second convention is how a lift
    # once walked the hips forward instead of raising them.
    g_up = sk.fk(local, {})
    pelvis_global = g_up[sk.index["pelvis"]][:3, :3]
    pelvis_local_rot = None
    for ch_up in anim_lift["channels"] if False else []:
        pass
    local_rot = quat_to_mat(local["pelvis"])
    parent_rot = pelvis_global @ np.linalg.inv(local_rot)
    up_local = parent_rot.T @ np.array([0.0, 1.0, 0.0])
    channel_dy = 0.0
    for ch in anim_lift["channels"]:
        if (ch["target"]["path"] == "translation"
                and names_lift[ch["target"]["node"]] == "pelvis"):
            vecs, _, _, _ = accessor_floats(
                js, data, bin_off, anim_lift["samplers"][ch["sampler"]]["output"])
            node = js["nodes"][ch["target"]["node"]]
            rest = np.asarray(node.get("translation", [0, 0, 0]),
                              dtype=np.float64)
            channel_dy = float(np.dot(np.mean(vecs, axis=0) - rest, up_local))
    lift = (TARGET_ANKLE_HEIGHT - channel_dy
            - measurements(sk, sk.fk(local, deltas))["ankleY"])
    # Lateral centring rides the same channel: the rest pose itself holds
    # the pelvis a touch to the right and the clip drifts further, so the
    # feet land off the body's midline -- visible from above as the legs
    # standing beside, not below, the torso.
    # The rest-rooted FK here CANNOT measure lateral drift: it differs
    # from the runtime by the root node's transform, and estimating the
    # channel's world offset from key means confuses idle sway for drift.
    # The stance was centred once, closed-loop against the runtime-
    # faithful probe (feet midpoint to world x zero, 2026-09-02); this
    # stays zero so reruns leave that centring alone.  Re-centre with the
    # probe loop, not from here.
    x_local = parent_rot.T @ np.array([1.0, 0.0, 0.0])
    recentre = 0.0

    after = measurements(sk, sk.fk(local, deltas))
    report("after: ", after)
    print("pelvis lift pending: %+.3f m (ankle y %.3f -> %.3f)"
          % (lift, after["ankleY"], TARGET_ANKLE_HEIGHT))
    print("deltas: chest de-twist %.1f deg, clavicle L%.1f R%.1f deg, arm "
          "+/-%.1f deg, legs straightened, feet to forward"
          % (twist_angle, clav_angles["l"], clav_angles["r"], arm_angle))

    if args.dry_run:
        print("\nnothing written (--dry-run)")
        return 0

    # Rewrite every keyframe of each target channel: post-multiply by its
    # delta and pack back into the same float32 slots.
    for bone, delta in deltas.items():
        _, quats, base, stride, ncomp = channels[bone]
        adjusted = np.array([quat_mul(q, delta) for q in quats])
        adjusted /= np.linalg.norm(adjusted, axis=1, keepdims=True)
        write_floats(data, base, stride, ncomp, adjusted)
    if abs(lift) > 0.0005 or abs(recentre) > 0.0005:
        names = [n.get("name", "") for n in js["nodes"]]
        anim = next(a for a in js["animations"] if a.get("name") == CLIP)
        for ch in anim["channels"]:
            if (ch["target"]["path"] == "translation"
                    and names[ch["target"]["node"]] == "pelvis"):
                sampler = anim["samplers"][ch["sampler"]]
                vecs, vbase, vstride, vncomp = accessor_floats(
                    js, data, bin_off, sampler["output"])
                vecs = vecs.copy()
                vecs += up_local[np.newaxis, :] * lift
                vecs += x_local[np.newaxis, :] * recentre
                write_floats(data, vbase, vstride, vncomp, vecs)
                print("pelvis raised %.3f m, recentred %+.3f m"
                      % (lift, recentre))
    LIBRARY.write_bytes(bytes(data))
    print("\nwrote %s (%d channels, %s only)" % (LIBRARY.name, len(deltas), CLIP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
