"""Rework the shared Walk clip's pose and cadence toward the reference gait.

The authored Walk is an eager march: the thighs swing to 47 degrees in
front but barely 10 behind, the torso pitches almost ten degrees forward,
and the elbows carry a locked 36-degree bend.  The reference walk is
upright and even -- legs scissoring symmetrically about the body, arms
swinging long and nearly straight -- and it patters at about 3.75 steps a
second where ours lopes at 2.9.

Cadence is not edited here directly: the client scales the clip's playback
so the feet track the ground (`_playback_speed_for` = travel speed over
the configured stride speed), so shortening the stride *is* quickening the
step.  Recentring and shrinking the thigh swing shortens the stride; the
tool re-measures the ankle travel afterwards and rewrites
``strideMetresPerSecond.walk`` in data/animations/luminous.json to match,
which lands the in-game cadence on the target at the same ground speed
with the feet still planted.

Every edit is expressed against measured absolutes (swing centre, swing
amplitude, lean, elbow bend), so the tool is idempotent: a second run
computes deltas of zero.

Usage:
    python adjust_walk_pose.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

import adjust_idle_pose as base

CLIP = "Walk"
RUN_CLIP = "Run_Female"
ANIMATION_MAP = (base.LIBRARY.parents[4] / "data" / "animations"
                 / "luminous.json")

#: Forward-swing angle of the thigh (degrees; positive = leg in front).
#: Centre +8 / amplitude 27 reaches the front foot well ahead of the body
#: so the step reads plant-first, body-follows; the stride constant below
#: re-measures, which also calms the cadence.
TARGET_THIGH_CENTRE = 8.0
TARGET_THIGH_AMP = 24.0
#: How high the swing foot rides (ankle-height span over the cycle, in
#: metres).  The reference is a pendulum gait -- legs swinging nearly
#: straight, feet skimming low -- where the authored clip kicked the
#: heel twenty-eight centimetres up behind.  Absolute, unlike the old
#: one-shot calf multiplier: the calves scale toward whatever lift is
#: measured until the span lands here.
TARGET_FOOT_LIFT = 0.12
#: Upper-arm swing amplitude (degrees); the swing CENTRE is steered by
#: where the hands' mean lands, matching the idle's posture targets.
TARGET_ARM_AMP = 25.0
#: Base posture, shared with the idle: the arm swing averages about the
#: same shoulder and hand positions the standing pose holds.
TARGET_SHOULDER_Z = -0.016
TARGET_HAND_Z_MEAN = 0.065
TARGET_HAND_X_MEAN = {"l": 0.266, "r": 0.249}
TARGET_ELBOW = 12.0
#: Phase of the thigh-swing peak relative to the torso-sway peak, as a
#: fraction of the cycle (0 = in phase).  The authored clip runs the
#: legs 0.072 of a cycle BEHIND the torso -- the body drags the feet
#: after it; at zero the step leads the weight onto it.
TARGET_LEG_PHASE = 0.0
#: The run keeps its pumping gait but loses its handedness: the authored
#: clip carries the left shoulder six centimetres ahead of the right and
#: the left hand five centimetres wider.
RUN_SHOULDER_Z = 0.029
RUN_HAND_X_MEAN = {"l": 0.165, "r": 0.165}
#: Forward pitch of the trunk, pelvis to chest (degrees).
TARGET_LEAN = 2.5


def quat_slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if np.dot(a, b) < 0:
        b = -b
    cos = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if cos > 0.9995:
        out = a + (b - a) * t
        return out / np.linalg.norm(out)
    theta = np.arccos(cos)
    return (np.sin((1 - t) * theta) * a + np.sin(t * theta) * b) / np.sin(theta)


def mean_quat(quats: np.ndarray) -> np.ndarray:
    mean = quats[0].copy()
    for q in quats[1:]:
        if np.dot(mean, q) < 0:
            q = -q
        mean += q
    return mean / np.linalg.norm(mean)


def quat_conj(q: np.ndarray) -> np.ndarray:
    return np.array([-q[0], -q[1], -q[2], q[3]])


def axis_angle_of(q: np.ndarray) -> tuple[np.ndarray, float]:
    q = q / np.linalg.norm(q)
    if q[3] < 0:
        q = -q
    angle = 2.0 * np.arccos(np.clip(q[3], -1.0, 1.0))
    s = np.sqrt(max(1.0 - q[3] * q[3], 1e-12))
    return q[:3] / s, float(angle)


def scale_about(mean: np.ndarray, q: np.ndarray, factor: float) -> np.ndarray:
    rel = base.quat_mul(quat_conj(mean), q)
    axis, angle = axis_angle_of(rel)
    scaled = base.axis_angle_quat(axis, np.degrees(angle * factor))
    return base.quat_mul(mean, scaled)


class WalkClip:
    """All rotation channels of the Walk clip, editable in place."""

    def __init__(self, js, data, bin_off):
        names = [n.get("name", "") for n in js["nodes"]]
        anim = next(a for a in js["animations"] if a.get("name") == CLIP)
        self.channels = {}
        refs = {}
        for a in js["animations"]:
            for ch in a["channels"]:
                out = a["samplers"][ch["sampler"]]["output"]
                refs[out] = refs.get(out, 0) + 1
        for ch in anim["channels"]:
            if ch["target"]["path"] != "rotation":
                continue
            sampler = anim["samplers"][ch["sampler"]]
            times, _, _, _ = base.accessor_floats(js, data, bin_off,
                                                  sampler["input"])
            quats, qbase, stride, ncomp = base.accessor_floats(
                js, data, bin_off, sampler["output"])
            bone = names[ch["target"]["node"]]
            self.channels[bone] = {
                "times": times[:, 0], "quats": quats, "base": qbase,
                "stride": stride, "ncomp": ncomp,
                "shared": refs[sampler["output"]] > 1,
            }
        self.duration = max(c["times"][-1] for c in self.channels.values())

    def pose_at(self, t: float) -> dict:
        local = {}
        for bone, ch in self.channels.items():
            times, quats = ch["times"], ch["quats"]
            i = int(np.searchsorted(times, t, "right")) - 1
            i = max(0, min(i, len(times) - 1))
            if i + 1 < len(times) and times[i + 1] > times[i]:
                f = (t - times[i]) / (times[i + 1] - times[i])
                local[bone] = quat_slerp(quats[i], quats[i + 1], float(f))
            else:
                local[bone] = quats[i]
        return local


def measures(clip: WalkClip, sk: base.Skeleton, phases: int = 24) -> dict:
    thigh, arm, elbow, lean, ankle_z = [], [], [], [], []
    ankle_lift = []
    for p in np.linspace(0, 1, phases, endpoint=False):
        glob = sk.fk(clip.pose_at(float(p) * clip.duration), {})
        o = lambda n: sk.origin(glob, n)
        v = o("calf_l") - o("thigh_l")
        thigh.append(np.degrees(np.arctan2(v[2], -v[1])))
        va = o("lowerarm_l") - o("upperarm_l")
        arm.append(np.degrees(np.arctan2(va[2], -va[1])))
        vf = o("hand_l") - o("lowerarm_l")
        elbow.append(np.degrees(np.arccos(np.clip(
            np.dot(va / np.linalg.norm(va), vf / np.linalg.norm(vf)),
            -1.0, 1.0))))
        vt = o("spine_03") - o("pelvis")
        lean.append(np.degrees(np.arctan2(vt[2], vt[1])))
        ankle_z.append(float(o("foot_l")[2]))
        ankle_lift.append(float(o("foot_l")[1]))
    thigh, arm = np.array(thigh), np.array(arm)
    return {
        "thighCentre": float((thigh.max() + thigh.min()) / 2),
        "thighAmp": float((thigh.max() - thigh.min()) / 2),
        "armCentre": float((arm.max() + arm.min()) / 2),
        "armAmp": float((arm.max() - arm.min()) / 2),
        "elbow": float(np.mean(elbow)),
        "lean": float(np.mean(lean)),
        "ankleSpan": float(max(ankle_z) - min(ankle_z)),
        "footLift": float(max(ankle_lift) - min(ankle_lift)),
    }


def recenter_world_x(clip: WalkClip, sk: base.Skeleton, bone: str,
                     degrees: float) -> None:
    """Turn every key of one channel by a world-X rotation, conjugated at
    that key's own pose so a chained parent cannot bend the correction."""
    ch = clip.channels[bone]
    for i, t in enumerate(ch["times"]):
        glob = sk.fk(clip.pose_at(float(t)), {})
        delta = sk.world_delta(glob, bone, [1.0, 0.0, 0.0], degrees)
        ch["quats"][i] = base.quat_mul(ch["quats"][i], delta)


def scale_channel(clip: WalkClip, bone: str, factor: float) -> None:
    ch = clip.channels[bone]
    mean = mean_quat(ch["quats"])
    for i in range(len(ch["quats"])):
        ch["quats"][i] = scale_about(mean, ch["quats"][i], factor)


def steer_world_x(clip: WalkClip, sk: base.Skeleton, bones: list[str],
                  measure_key: str, target: float) -> None:
    """Recentre channels by world-X rotation, solving the sign and gain
    from the clip's own response: post-multiplied deltas conjugated
    through different bone bases do not turn the same way, and deriving
    the sign per bone by hand is how the first draft swung the legs the
    wrong way.  A rotation is exactly linear in degrees, so one 2-degree
    probe fixes the slope and a second application lands the target."""
    start = measures(clip, sk)[measure_key]
    for bone in bones:
        recenter_world_x(clip, sk, bone, 2.0)
    probed = measures(clip, sk)[measure_key]
    slope = (probed - start) / 2.0
    if abs(slope) < 1e-6:
        return
    remaining = (target - probed) / slope
    for bone in bones:
        recenter_world_x(clip, sk, bone, remaining)


def set_elbow(clip: WalkClip, sk: base.Skeleton, side: str,
              target: float) -> None:
    """Hold the elbow at an absolute bend through the whole swing.

    Per key: the bend axis is the normal of the upper-arm/forearm plane at
    that key's own pose, and rotating the forearm about it changes the
    bend angle degree for degree, so the correction is closed-form.
    """
    bone = "lowerarm_" + side
    ch = clip.channels[bone]
    for i, t in enumerate(ch["times"]):
        glob = sk.fk(clip.pose_at(float(t)), {})
        o = lambda n: sk.origin(glob, n)
        upper = o(bone) - o("upperarm_" + side)
        fore = o("hand_" + side) - o(bone)
        upper /= max(np.linalg.norm(upper), 1e-9)
        fore /= max(np.linalg.norm(fore), 1e-9)
        bend = np.degrees(np.arccos(np.clip(np.dot(upper, fore), -1.0, 1.0)))
        axis = np.cross(upper, fore)
        norm = np.linalg.norm(axis)
        if norm < 1e-6:
            continue
        delta = sk.world_delta(glob, bone, axis / norm, target - bend)
        ch["quats"][i] = base.quat_mul(ch["quats"][i], delta)


def _first_harmonic_phase(signal) -> float:
    signal = np.asarray(signal, dtype=np.float64)
    signal = signal - signal.mean()
    k = np.exp(-2j * np.pi * np.arange(len(signal)) / len(signal))
    return float((np.angle(np.sum(signal * k)) / (2 * np.pi)) % 1.0)


def leg_phase(clip: WalkClip, sk: base.Skeleton, phases: int = 32) -> float:
    thigh, sway = [], []
    for p in np.linspace(0, 1, phases, endpoint=False):
        g = sk.fk(clip.pose_at(float(p) * clip.duration), {})
        v = sk.origin(g, "calf_l") - sk.origin(g, "thigh_l")
        thigh.append(np.degrees(np.arctan2(v[2], -v[1])))
        sway.append(float(sk.origin(g, "spine_03")[0]))
    lead = (_first_harmonic_phase(thigh)
            - _first_harmonic_phase(sway)) % 1.0
    return lead if lead <= 0.5 else lead - 1.0


def shift_channels(clip: WalkClip, bones, fraction: float) -> None:
    """Resample channels ``fraction`` of a cycle later in their own loop,
    which plays their content that much EARLIER against everything else."""
    dt = fraction * clip.duration
    for bone in bones:
        if bone not in clip.channels:
            continue
        ch = clip.channels[bone]
        times, quats = ch["times"], ch["quats"]
        span = times[-1] - times[0]
        if span <= 0:
            continue
        resampled = np.empty_like(quats)
        for i, t in enumerate(times):
            u = times[0] + ((t - times[0] + dt) % span)
            j = int(np.searchsorted(times, u, "right")) - 1
            j = max(0, min(j, len(times) - 2))
            f = (u - times[j]) / max(times[j + 1] - times[j], 1e-9)
            resampled[i] = quat_slerp(quats[j], quats[j + 1], float(f))
        ch["quats"][:] = resampled


def phase_mean(clip: WalkClip, sk: base.Skeleton, probe, phases: int = 12):
    return float(np.mean([probe(sk.fk(clip.pose_at(
        float(p) * clip.duration), {}))
        for p in np.linspace(0, 1, phases, endpoint=False)]))


def steer_channel_mean(clip: WalkClip, sk: base.Skeleton, bone: str,
                       axis, measure, target: float) -> None:
    """Shift one channel's every key by a constant conjugated delta until
    a phase-averaged measure lands on target, solving gain and sign from
    the clip's own response."""
    start = measure()
    recenter_world_x_axis(clip, sk, bone, axis, 2.0)
    slope = (measure() - start) / 2.0
    if abs(slope) < 1e-9:
        return
    recenter_world_x_axis(clip, sk, bone, axis, (target - measure()) / slope)


def recenter_world_x_axis(clip: WalkClip, sk: base.Skeleton, bone: str,
                          axis, degrees: float) -> None:
    ch = clip.channels[bone]
    for i, t in enumerate(ch["times"]):
        glob = sk.fk(clip.pose_at(float(t)), {})
        delta = sk.world_delta(glob, bone, axis, degrees)
        ch["quats"][i] = base.quat_mul(ch["quats"][i], delta)


def posture(clip: WalkClip, sk: base.Skeleton, shoulder_z: float,
            hand_z: float | None, hand_x: dict | None) -> None:
    """Steer the clip's MEAN posture -- where the swing averages -- onto
    the standing pose's targets, side by side."""
    for side in ("l", "r"):
        arm = "upperarm_" + side

        def sh_mean():
            return phase_mean(clip, sk, lambda g, s=side: float(
                sk.origin(g, "upperarm_" + s)[2]))

        def hz_mean():
            return phase_mean(clip, sk, lambda g, s=side: float(
                sk.origin(g, "hand_" + s)[2]))

        def hx_mean():
            return phase_mean(clip, sk, lambda g, s=side: float(
                abs(sk.origin(g, "hand_" + s)[0])))

        steer_channel_mean(clip, sk, "clavicle_" + side, [0, 1, 0],
                           sh_mean, shoulder_z)
        if hand_z is not None:
            steer_channel_mean(clip, sk, arm, [1, 0, 0], hz_mean, hand_z)
        if hand_x is not None:
            steer_channel_mean(clip, sk, "lowerarm_" + side, [0, 0, 1],
                               hx_mean, hand_x[side])


def adjust_run(js, data, bin_off, sk: base.Skeleton) -> list:
    """Posture-only pass on the run: symmetric shoulders and hand widths,
    the pumping gait untouched."""
    global CLIP
    keep = CLIP
    CLIP = RUN_CLIP
    clip = WalkClip(js, data, bin_off)
    CLIP = keep
    edited = ["clavicle_l", "clavicle_r", "lowerarm_l", "lowerarm_r"]
    shared = [b for b in edited if clip.channels[b]["shared"]]
    assert not shared, "run: shared accessors, unsafe: %s" % shared
    posture(clip, sk, RUN_SHOULDER_Z, None, RUN_HAND_X_MEAN)
    for side in ("l", "r"):
        print("run %s: shoulder z %+.3f, hand |x| %.3f"
              % (side,
                 phase_mean(clip, sk, lambda g, s=side: float(
                     sk.origin(g, "upperarm_" + s)[2])),
                 phase_mean(clip, sk, lambda g, s=side: float(
                     abs(sk.origin(g, "hand_" + s)[0])))))
    return [(bone, clip.channels[bone]) for bone in edited]


def sagittal_swing(clip: WalkClip, sk: base.Skeleton, bone: str) -> None:
    """Flatten one channel's swing to the sagittal plane.

    Each key's deviation from the channel's temporal mean is conjugated
    into world space, reduced to its world-X (fore-aft) component, and
    folded back -- the pendulum keeps its full swing but loses the
    adduction that walked the hands left and right across the body.
    """
    ch = clip.channels[bone]
    mean = mean_quat(ch["quats"])
    mean_pose = {b: mean_quat(c["quats"]) for b, c in clip.channels.items()}
    g = sk.fk(mean_pose, {})
    G = g[sk.index[bone]][:3, :3]
    for i in range(len(ch["quats"])):
        dev = base.quat_mul(quat_conj(mean), ch["quats"][i])
        axis, angle = axis_angle_of(dev)
        world_axis = G @ axis
        x_part = float(world_axis[0]) * np.degrees(angle)
        dev_flat = base.mat_to_quat(
            G.T @ base.quat_to_mat(base.axis_angle_quat([1, 0, 0], x_part))
            @ G)
        ch["quats"][i] = base.quat_mul(mean, dev_flat)


def copy_idle_arm(clip: WalkClip, js, data, bin_off) -> None:
    """Hold the walk's forearms and hands at the idle's exact
    configuration: the elbow bend and the palm orientation are then the
    same in both by construction, and nothing wobbles through the swing.
    """
    idle_local, _ = base.sampled_idle(js, data, bin_off)
    for bone in ("lowerarm_l", "lowerarm_r", "hand_l", "hand_r"):
        value = idle_local.get(bone)
        if value is None:
            continue
        ch = clip.channels[bone]
        for i in range(len(ch["quats"])):
            ch["quats"][i] = np.asarray(value, dtype=np.float64)


def main() -> int:
    ap = argparse.ArgumentParser(description="rework the shared Walk clip")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data, js, bin_off, _ = base.read_glb(base.LIBRARY)
    sk = base.Skeleton(base.BODY)
    clip = WalkClip(js, data, bin_off)

    edited = ["thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r",
              "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
              "hand_l", "hand_r", "spine_01", "clavicle_l", "clavicle_r"]
    edited += [b for b in ("ball_l", "ball_r") if b in clip.channels
               and not clip.channels[b]["shared"]]
    shared = [b for b in edited if clip.channels[b]["shared"]]
    assert not shared, "shared accessors, unsafe to rewrite: %s" % shared

    def report(tag, m):
        print("%s thigh %+.1f/%.1f, arm %+.1f/%.1f, elbow %.1f, lean %+.1f, "
              "ankle span %.3f, foot lift %.3f"
              % (tag, m["thighCentre"], m["thighAmp"], m["armCentre"],
                 m["armAmp"], m["elbow"], m["lean"], m["ankleSpan"],
                 m["footLift"]))
    before = measures(clip, sk)
    report("before:", before)

    steer_world_x(clip, sk, ["spine_01"], "lean", TARGET_LEAN)
    steer_world_x(clip, sk, ["thigh_l", "thigh_r"], "thighCentre",
                  TARGET_THIGH_CENTRE)
    for side in ("l", "r"):
        scale_channel(clip, "thigh_" + side,
                      TARGET_THIGH_AMP / max(before["thighAmp"], 1e-6))
    # The legs step ahead of the torso: their channels shift together
    # around the loop until the thigh-swing peak lands on the torso-sway
    # peak instead of trailing it.
    lag = leg_phase(clip, sk) - TARGET_LEG_PHASE
    if abs(lag) > 0.01:
        shift_channels(clip, ["thigh_l", "thigh_r", "calf_l", "calf_r",
                              "foot_l", "foot_r", "ball_l", "ball_r"], -lag)
        print("legs shifted %.3f of a cycle earlier (lag was %+.3f)"
              % (-lag, lag))

    # Knees ease toward the target foot lift multiplicatively, a few
    # convergence rounds in place of a hand-tuned one-shot multiplier.
    for _ in range(6):
        span = measures(clip, sk)["footLift"]
        if abs(span - TARGET_FOOT_LIFT) < 0.005:
            break
        factor = float(np.clip(TARGET_FOOT_LIFT / max(span, 1e-6), 0.5, 1.5))
        for side in ("l", "r"):
            scale_channel(clip, "calf_" + side, factor)
    for side in ("l", "r"):
        scale_channel(clip, "upperarm_" + side,
                      TARGET_ARM_AMP / max(before["armAmp"], 1e-6))
    # Forearms and hands come straight from the idle -- same ten-degree
    # elbow, same palms-to-the-body rotation, held constant through the
    # cycle -- and the upper-arm swing flattens to the sagittal plane so
    # the hands stop crossing the body.  Posture steers afterwards along
    # world X only, which the flattening preserves.
    copy_idle_arm(clip, js, data, bin_off)
    for side in ("l", "r"):
        sagittal_swing(clip, sk, "upperarm_" + side)
    # hand_x deliberately None: the forearms belong to the idle copy now,
    # and the width steer would twist the ten-degree elbow right back out.
    posture(clip, sk, TARGET_SHOULDER_Z, TARGET_HAND_Z_MEAN, None)

    after = measures(clip, sk)
    report("after: ", after)

    run_channels = adjust_run(js, data, bin_off, sk)

    stride_doc = json.loads(ANIMATION_MAP.read_text(encoding="utf-8"))
    old_stride = float(stride_doc["strideMetresPerSecond"]["walk"])
    new_stride = old_stride * after["ankleSpan"] / max(before["ankleSpan"],
                                                       1e-9)
    print("stride %.3f -> %.3f m/s at speed 1.0; at 1.67 m/s that is "
          "%.2f steps/s (was %.2f)"
          % (old_stride, new_stride,
             2.0 / (clip.duration / (1.67 / new_stride)),
             2.0 / (clip.duration / (1.67 / old_stride))))

    if args.dry_run:
        print("\nnothing written (--dry-run)")
        return 0

    for bone in edited:
        ch = clip.channels[bone]
        quats = ch["quats"] / np.linalg.norm(ch["quats"], axis=1,
                                             keepdims=True)
        base.write_floats(data, ch["base"], ch["stride"], ch["ncomp"], quats)
    for bone, ch in run_channels:
        quats = ch["quats"] / np.linalg.norm(ch["quats"], axis=1,
                                             keepdims=True)
        base.write_floats(data, ch["base"], ch["stride"], ch["ncomp"], quats)
    base.LIBRARY.write_bytes(bytes(data))
    stride_doc["strideMetresPerSecond"]["walk"] = round(new_stride, 3)
    ANIMATION_MAP.write_text(json.dumps(stride_doc, indent=2) + "\n",
                             encoding="utf-8")
    print("\nwrote %s (%d channels, %s only) and %s"
          % (base.LIBRARY.name, len(edited), CLIP, ANIMATION_MAP.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
