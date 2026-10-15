"""Natural stance pass, preserving clip timing, the reference pose and other clips.

Restore Walk's actual knee motion from its original version, then solve ankles
with two-bone IK. Foot contacts retain the source floor and foot orientation.
Arm directions are authored in world space so left/right remain symmetric.
"""

from pathlib import Path
import argparse, copy, json
import numpy as np
from scipy.spatial.transform import Rotation
from audit import g, retarget, digest, reference_pose
from verify import sample_worlds
from build import limb

CLIPS = ("Idle_Subtle", "Walk", "Jog", "Run_Female", "Fighting_Idle")


def stats(d, b, name):
    clip = next(a for a in d["animations"] if a["name"] == name)
    times = retarget.clip_times(retarget.clip_channels(d, b, clip))
    ids = {n["name"]: i for i, n in enumerate(d["nodes"])}
    rows = []
    for w in sample_worlds(d, d, b, clip, np.linspace(0, times.max(), 61)):
        p = lambda n: w[ids[n]][:3, 3]
        axis = p("neck_01") - p("pelvis")
        row = [np.degrees(np.arctan2(axis[2], axis[1]))]
        for side in ("l", "r"):
            u = p("calf_" + side) - p("thigh_" + side)
            v = p("foot_" + side) - p("calf_" + side)
            arm = p("lowerarm_" + side) - p("upperarm_" + side)
            row.extend(
                [
                    np.degrees(
                        np.arccos(
                            np.clip(
                                u @ v / np.linalg.norm(u) / np.linalg.norm(v), -1, 1
                            )
                        )
                    ),
                    np.degrees(np.arctan2(abs(arm[0]), -arm[1])),
                    p("foot_" + side)[1],
                ]
            )
        rows.append(row)
    x = np.array(rows)
    return {
        "fields": [
            "torso_lean",
            "knee_l",
            "arm_out_l",
            "ankle_y_l",
            "knee_r",
            "arm_out_r",
            "ankle_y_r",
        ],
        "min": x.min(0).tolist(),
        "mean": x.mean(0).tolist(),
        "max": x.max(0).tolist(),
    }


def run(source, donor, out, contact_body):
    if "godot-client" in out.resolve().parts:
        raise ValueError("Scratch output required")
    d, b = g.read(source)
    dd, db = g.read(donor)
    original = copy.deepcopy(d)
    ids = {n["name"]: i for i, n in enumerate(d["nodes"])}
    parents = g.parents_of(d)
    reference, _, _ = reference_pose(source)
    reference_world = g.globals_of(reference)
    body, body_blob = g.read(contact_body)
    bp = body["meshes"][0]["primitives"][0]["attributes"]
    skin = body["skins"][0]
    bv = g.accessor(body, body_blob, bp["POSITION"])
    bj = g.accessor(body, body_blob, bp["JOINTS_0"]).astype(int)
    bw = g.accessor(body, body_blob, bp["WEIGHTS_0"])
    binds = (
        g.accessor(body, body_blob, skin["inverseBindMatrices"])
        .reshape(-1, 4, 4)
        .transpose(0, 2, 1)
    )
    body_names = [body["nodes"][i]["name"] for i in skin["joints"]]
    sole_groups = {
        side: np.flatnonzero((bv[:, 1] < 0.3) & (bv[:, 0] * sign > 0))
        for side, sign in [("l", 1), ("r", -1)]
    }
    app = g.BufferAppender(d, b)
    report = {
        "source_sha256": digest(source),
        "walk_donor_sha256": digest(donor),
        "contact_body_sha256": digest(contact_body),
        "clips": {},
    }
    for name in CLIPS:
        clip = next(a for a in original["animations"] if a["name"] == name)
        channels = retarget.clip_channels(original, b, clip)
        duration = float(retarget.clip_times(channels).max())
        times = np.linspace(0, duration, round(duration * 60) + 1)
        values = {
            i: {
                p: retarget._sample(times, t, v, interp, p == "rotation")
                for p, (t, v, interp) in paths.items()
            }
            for i, paths in channels.items()
        }
        if name == "Walk":
            donorclip = next(a for a in dd["animations"] if a["name"] == name)
            for i, paths in retarget.clip_channels(dd, db, donorclip).items():
                bn = dd["nodes"][i]["name"]
                if bn == "pelvis" or bn.startswith(
                    ("thigh_", "calf_", "foot_", "ball_")
                ):
                    values[ids[bn]] = {
                        p: retarget._sample(times, t, v, interp, p == "rotation")
                        for p, (t, v, interp) in paths.items()
                    }
        # The shipped Run_Female ends with its right toe almost 10 cm from
        # its starting position. Ease the residual into the final third of
        # the cycle before the foot-contact solve, instead of retaining a pop.
        blend = limb.smoothstep(times / duration, 0.7, 1.0)
        for paths in values.values():
            for path, data in paths.items():
                if path == "rotation":
                    rotations = Rotation.from_quat(data)
                    residual = (rotations[-1].inv() * rotations[0]).as_rotvec()
                    paths[path] = (
                        rotations * Rotation.from_rotvec(blend[:, None] * residual)
                    ).as_quat()
                elif path == "translation":
                    paths[path] = data + blend[:, None] * (data[0] - data[-1])
        frames = []
        for fi, t in enumerate(times):
            local = {
                i: g.trs_matrix(
                    *[
                        values.get(i, {}).get(p, [n.get(p, default)] * len(times))[fi]
                        for p, default in [
                            ("translation", [0, 0, 0]),
                            ("rotation", [0, 0, 0, 1]),
                            ("scale", [1, 1, 1]),
                        ]
                    ]
                )
                for i, n in enumerate(d["nodes"])
            }

            def world():
                return g.globals_of(d, local)

            def orient(bone, new_world_rot):
                i = ids[bone]
                w = world()
                pr = w[parents[i]][:3, :3] if i in parents else np.eye(3)
                local[i][:3, :3] = np.linalg.inv(pr) @ new_world_rot

            def aim(bone, child, direction):
                w = world()
                i = ids[bone]
                axis = w[ids[child]][:3, 3] - w[i][:3, 3]
                orient(bone, limb.minimal_rotation(axis, direction) @ w[i][:3, :3])

            def sole_height(side):
                w = world()
                rows = sole_groups[side]
                v = bv[rows]
                j = bj[rows]
                weights = bw[rows]
                mats = (
                    np.array(
                        [
                            (
                                w[ids[n if n != "Head" else "head"]]
                                if (n if n != "Head" else "head") in ids
                                else np.eye(4)
                            )
                            for n in body_names
                        ]
                    )
                    @ binds
                )
                posed = sum(
                    (
                        np.einsum("nij,nj->ni", mats[j[:, k], :3, :3], v)
                        + mats[j[:, k], :3, 3]
                    )
                    * weights[:, k, None]
                    for k in range(4)
                )
                return float(posed[:, 1].min())

            def solve_ankle(side, target):
                thigh, calf, foot = [n + "_" + side for n in ("thigh", "calf", "foot")]
                w = world()
                a, k, z = [w[ids[n]][:3, 3] for n in (thigh, calf, foot)]
                foot_rot = w[ids[foot]][:3, :3].copy()
                upper = np.linalg.norm(k - a)
                lower = np.linalg.norm(z - k)
                axis = target - a
                dist = np.linalg.norm(axis)
                axis /= dist
                dist = np.clip(dist, abs(upper - lower) + 1e-4, upper + lower - 1e-4)
                target = a + axis * dist
                pole = k - a - axis * np.dot(k - a, axis)
                if np.linalg.norm(pole) < 1e-5:
                    pole = np.array([0.0, 0.0, 1.0]) - axis * axis[2]
                pole /= np.linalg.norm(pole)
                reach = (upper * upper - lower * lower + dist * dist) / (2 * dist)
                knee = (
                    a
                    + axis * reach
                    + pole * np.sqrt(max(0, upper * upper - reach * reach))
                )
                aim(thigh, calf, knee - a)
                aim(calf, foot, target - knee)
                orient(foot, foot_rot)

            w = world()
            saved = copy.deepcopy(w)
            if name in ("Walk", "Jog", "Run_Female"):
                lift = 0.50 if name == "Walk" else 0.65
                stride = 1.0 if name == "Walk" else 0.90
                for side in ("l", "r"):
                    thigh, calf, foot = [
                        "%s_%s" % (a, side) for a in ("thigh", "calf", "foot")
                    ]
                    a, k, z = [saved[ids[n]][:3, 3] for n in (thigh, calf, foot)]
                    target = z.copy()
                    floor = 0.095
                    target[1] = floor + max(0, z[1] - floor) * lift
                    target[2] = -0.05 + (z[2] + 0.05) * stride
                    upper = np.linalg.norm(k - a)
                    lower = np.linalg.norm(z - k)
                    axis = target - a
                    dist = np.linalg.norm(axis)
                    axis /= dist
                    dist = np.clip(
                        dist, abs(upper - lower) + 1e-4, upper + lower - 1e-4
                    )
                    target = a + axis * dist
                    pole = k - a - axis * np.dot(k - a, axis)
                    if np.linalg.norm(pole) < 1e-5:
                        pole = np.array([0.0, 0.0, 1.0]) - axis * axis[2]
                    pole /= np.linalg.norm(pole)
                    reach = (upper * upper - lower * lower + dist * dist) / (2 * dist)
                    knee = (
                        a
                        + axis * reach
                        + pole * np.sqrt(max(0, upper * upper - reach * reach))
                    )
                    aim(thigh, calf, knee - a)
                    aim(calf, foot, target - knee)
                    orient(foot, saved[ids[foot]][:3, :3])
            # An ankle-height reduction must account for the rolled boot's
            # toe, not merely its joint. Keep the actual skinned sole above
            # the ground; running flight phases stay intact.
            if name == "Idle_Subtle":
                correction = 0.003 - min(sole_height("l"), sole_height("r"))
                pr = world()[parents[ids["pelvis"]]][:3, :3]
                local[ids["pelvis"]][:3, 3] += np.linalg.inv(pr) @ np.array(
                    [0.0, correction, 0.0]
                )
            elif name in ("Walk", "Jog", "Run_Female"):
                for side in ("l", "r"):
                    for iteration in range(3):
                        floor_y = sole_height(side)
                        if floor_y >= 0.002:
                            break
                        target = world()[ids["foot_" + side]][:3, 3].copy()
                        target[1] += 0.003 - floor_y
                        solve_ankle(side, target)
            if name in ("Walk", "Jog", "Run_Female"):
                w = world()
                v = w[ids["neck_01"]][:3, 3] - w[ids["pelvis"]][:3, 3]
                lean = np.degrees(np.arctan2(v[2], v[1]))
                desired = 2.5 if name == "Walk" else 8.0
                delta = Rotation.from_euler(
                    "x", desired - lean, degrees=True
                ).as_matrix()
                orient("spine_01", delta @ w[ids["spine_01"]][:3, :3])
            for side, sign in [("l", 1), ("r", -1)]:
                upper, lower, hand = [
                    n + "_" + side for n in ("upperarm", "lowerarm", "hand")
                ]
                w = world()
                u = w[ids[lower]][:3, 3] - w[ids[upper]][:3, 3]
                # The old pose pass swung each clavicle almost sideways,
                # widening the shoulders by about 9 cm even though Rest_Pose
                # is narrower. Retain its length, restore the backward sweep,
                # and slope it slightly down relative to the ribcage.
                torso_delta = (
                    w[ids["spine_03"]][:3, :3]
                    @ reference_world[ids["spine_03"]][:3, :3].T
                )
                relaxed = torso_delta @ np.array([sign * 0.150, -0.015, -0.135])
                aim("clavicle_" + side, upper, relaxed)
                if name == "Fighting_Idle":
                    u[0] *= 0.75
                    aim(upper, lower, u)
                    continue
                # Preserve the swing phase; bring elbows nearer the torso.
                sagittal = np.arctan2(u[2], -u[1])
                if name == "Idle_Subtle":
                    sagittal *= 0.4
                elif name == "Walk":
                    sagittal *= 0.8
                else:
                    sagittal = np.clip(sagittal, -0.85, 0.85) * 0.8
                spread = np.deg2rad(8 if name in ("Idle_Subtle", "Walk") else 10)
                direction = np.array(
                    [
                        sign * np.sin(spread),
                        -np.cos(spread) * np.cos(sagittal),
                        np.cos(spread) * np.sin(sagittal),
                    ]
                )
                aim(upper, lower, direction)
                elbow = np.deg2rad(12 if name in ("Idle_Subtle", "Walk") else 80)
                fore = np.array(
                    [
                        sign * np.sin(spread),
                        -np.cos(spread) * np.cos(sagittal + elbow),
                        np.cos(spread) * np.sin(sagittal + elbow),
                    ]
                )
                aim(lower, hand, fore)
            frames.append(local)
        new = {"name": name, "channels": [], "samplers": []}
        ta = app.add(times[:, None], "SCALAR")
        for i in range(len(d["nodes"])):
            rotations = np.array([g.matrix_to_quat(f[i][:3, :3]) for f in frames])
            for fi in range(1, len(rotations)):
                if rotations[fi] @ rotations[fi - 1] < 0:
                    rotations[fi] *= -1
            translations = np.array([f[i][:3, 3] for f in frames])
            for path, data, kind in [
                ("rotation", rotations, "VEC4"),
                ("translation", translations, "VEC3"),
            ]:
                si = len(new["samplers"])
                new["samplers"].append(
                    {
                        "input": ta,
                        "output": app.add(data, kind),
                        "interpolation": "LINEAR",
                    }
                )
                new["channels"].append(
                    {"sampler": si, "target": {"node": i, "path": path}}
                )
        d["animations"][
            next(i for i, a in enumerate(d["animations"]) if a["name"] == name)
        ] = new
        report["clips"][name] = {"before": stats(original, b, name)}
    d, blob = g.compact(d, bytes(app.blob))
    g.write(out, d, blob)
    # Unrequested clips and reference channels must be numerically identical.
    for a in original["animations"]:
        if a["name"] in CLIPS:
            continue
        now = next(x for x in d["animations"] if x["name"] == a["name"])
        ca = retarget.clip_channels(original, b, a)
        cb = retarget.clip_channels(d, blob, now)
        for i, paths in ca.items():
            for p, (t, v, interp) in paths.items():
                tt, vv, ii = cb[i][p]
                assert (
                    np.array_equal(t, tt) and np.array_equal(v, vv) and ii == interp
                ), a["name"]
    for name in CLIPS:
        report["clips"][name]["after"] = stats(d, blob, name)
    report.update(
        {
            "output_sha256": digest(out),
            "unchanged_clips": len(d["animations"]) - len(CLIPS),
            "reference_pose_unchanged": True,
        }
    )
    out.with_suffix(".animations.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("donor", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--contact-body", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.source, a.donor, a.out, a.contact_body), indent=2))
