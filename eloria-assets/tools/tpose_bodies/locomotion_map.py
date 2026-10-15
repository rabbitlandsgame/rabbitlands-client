"""Measure stance travel for playback cadence and facing after clip edits."""

import argparse, json
import numpy as np
from audit import WORKTREE, g, retarget, digest
from verify import sample_worlds

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    library = WORKTREE / "tpose-body-build/out/Universal_Animation_Library.glb"
    d, b = g.read(library)
    ids = {n["name"]: i for i, n in enumerate(d["nodes"])}
    path = WORKTREE / "godot-client/data/animations/luminous.json"
    before = digest(path)
    mapping = json.loads(path.read_text())
    report = {"library_sha256": digest(library), "actions": {}}
    for action, name in [("walk", "Walk"), ("run", "Run_Female")]:
        clip = next(c for c in d["animations"] if c["name"] == name)
        duration = float(retarget.clip_times(retarget.clip_channels(d, b, clip)).max())
        times = np.linspace(0, duration, 241)
        worlds = list(sample_worlds(d, d, b, clip, times))
        speeds = []
        directions = []
        for side in ("l", "r"):
            pos = np.array([w[ids["foot_" + side]][:3, 3] for w in worlds])
            vel = np.gradient(pos, times, axis=0)
            stance = (pos[:, 1] < np.quantile(pos[:, 1], 0.4)) & (vel[:, 2] < 0)
            speeds.append(float(np.median(-vel[stance, 2])))
            directions.append(
                float(np.degrees(np.arctan2(-vel[stance, 0], -vel[stance, 2])).mean())
            )
        speed = round(float(np.mean(speeds)), 3)
        yaw = float(np.mean(directions))
        if abs(yaw) > 1:
            raise ValueError(
                "Travel is not aligned with model forward; review facing before installation"
            )
        mapping["strideMetresPerSecond"][action] = speed
        mapping["facingOffsets"][action] = 0.0
        report["actions"][action] = {
            "clip": name,
            "duration": duration,
            "stance_speed_l_r": speeds,
            "stance_direction_degrees_l_r": directions,
            "strideMetresPerSecond": speed,
            "facingOffset": 0.0,
        }
    if a.write:
        if digest(path) != before:
            raise RuntimeError("Concurrent animation-map edit")
        path.write_text(json.dumps(mapping, indent=2) + "\n")
    (WORKTREE / "tpose-body-build/reports/locomotion_map.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
