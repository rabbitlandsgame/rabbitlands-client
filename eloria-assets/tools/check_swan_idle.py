"""Measure the Swan idle revision and independently verify its narrow scope."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from video_motion.asset import accessor, digest
from video_motion.native_shapes import NativeShapeAsset

CHANGED = {("neck_01", "rotation"), ("spine_02", "translation")}
IDLES = {"Idle_A", "Fighting_Idle"}


def check(source: Path, candidate: Path, report: Path, witness: Path | None = None) -> dict:
    old, new = NativeShapeAsset(source), NativeShapeAsset(candidate)
    failures = []

    def require(condition, label):
        if not condition:
            failures.append(label)

    require(new.b.startswith(old.b), "original binary payload is unchanged")
    for key in old.d:
        if key not in {"asset", "buffers", "accessors", "bufferViews", "animations"}:
            require(old.d[key] == new.d[key], "static document section " + key)
    require(old.names == new.names, "node order and names")
    require(set(old.animations) == set(new.animations), "complete native clip set")
    for clip in old.animations:
        require(old.duration(clip) == new.duration(clip), "duration " + clip)
        if clip not in IDLES:
            require(old.animations[clip] == new.animations[clip], "unrelated action " + clip)
            continue
        before = old.animations[clip]
        after = new.animations[clip]
        require(len(before["channels"]) == len(after["channels"]), "idle channel count")
        for a, b in zip(before["channels"], after["channels"]):
            require(a["target"] == b["target"], "idle channel identity")
            key = (old.names[a["target"]["node"]], a["target"]["path"])
            if key not in CHANGED:
                require(a == b, "untouched idle channel " + str(key))
            else:
                sampler = after["samplers"][b["sampler"]]
                clock = accessor(new.d, new.b, sampler["input"]).ravel()
                require(np.min(np.diff(clock)) >= 1 / 30 - 1e-6, "delivery cadence cap")

    results, samples = {}, {}
    for clip in sorted(IDLES):
        duration = new.duration(clip)
        t0, q0, s0, m0 = old.sample(clip, [0.0])
        original = old.skin(old.world(t0[0], q0[0], s0[0]), {k: v[0] for k, v in m0.items()})
        feet = original[:, 1] < 0.08
        head = (original[:, 1] > 0.78) & (original[:, 2] > 0.25)
        _, group = np.unique(np.round(original, 6), axis=0, return_inverse=True)
        pairs = []
        for index in np.unique(group):
            members = np.flatnonzero(group == index)
            pairs.extend((int(members[0]), int(other)) for other in members[1:])
        pairs = np.asarray(pairs, int).reshape(-1, 2)
        key_clocks = []
        for channel in new.animations[clip]["channels"]:
            if (new.names[channel["target"]["node"]], channel["target"]["path"]) in CHANGED:
                sampler = new.animations[clip]["samplers"][channel["sampler"]]
                clock = accessor(new.d, new.b, sampler["input"]).ravel()
                key_clocks.extend([clock, (clock[:-1] + clock[1:]) * 0.5])
        times = np.unique(np.concatenate([np.linspace(0, duration, 193),
                         np.arange(0.01337, duration, duration / 97), *key_clocks]))
        translations, quaternions, scales, morphs = new.sample(clip, times)
        surfaces = []
        for index in range(len(times)):
            world = new.world(translations[index], quaternions[index], scales[index])
            surfaces.append(new.skin(world, {k: v[index] for k, v in morphs.items()}))
        surfaces = np.asarray(surfaces)
        require(np.isfinite(surfaces).all(), "finite idle surface " + clip)
        displacement = np.linalg.norm(surfaces - original, axis=2)
        foot_mm = float(displacement[:, feet].max() * 1000)
        head_mm = float(displacement[:, head].max() * 1000)
        loop_mm = float(np.linalg.norm(surfaces[0] - surfaces[-1], axis=1).max() * 1000)
        gaps = np.linalg.norm(surfaces[:, pairs[:, 0]] - surfaces[:, pairs[:, 1]], axis=2)
        original_gaps = np.linalg.norm(original[pairs[:, 0]] - original[pairs[:, 1]], axis=1)
        added_gap_mm = float(np.maximum(0, gaps - original_gaps).max(initial=0) * 1000)
        require(foot_mm < 0.1, "planted feet " + clip)
        require(head_mm > 10.0, "readable nonconstant head motion " + clip)
        require(loop_mm < 0.001, "closed loop " + clip)
        require(added_gap_mm < 0.5, "coincident seam stability " + clip)
        # Export off-grid independent joint worlds for the production Godot test.
        witness_times = duration * np.array([0.0, .11337, .26319, .381966, .63119, .81731, 1.0])
        tt, qq, ss, _ = new.sample(clip, witness_times)
        clip_samples = []
        for index, at in enumerate(witness_times):
            world = new.world(tt[index], qq[index], ss[index])
            clip_samples.append({"time": float(at), "bones": {
                new.names[j]: world[j].reshape(-1).tolist() for j in new.joints}})
        samples[clip] = clip_samples
        results[clip] = {"sampled_states": len(times), "foot_vertices": int(feet.sum()),
                         "maximum_foot_displacement_mm": foot_mm,
                         "maximum_head_displacement_mm": head_mm,
                         "loop_closure_mm": loop_mm, "maximum_added_seam_gap_mm": added_gap_mm,
                         "duration": duration}
    result = {"source_sha256": digest(source), "candidate_sha256": digest(candidate),
              "passed": not failures, "failures": failures, "clips": results,
              "limits": "Independent GLB skin sampling. Fresh engine/import and visual review remain separate."}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if witness:
        witness.parent.mkdir(parents=True, exist_ok=True)
        witness.write_text(json.dumps({"sha256": digest(candidate), "clips": samples},
                                      separators=(",", ":")) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--witness", type=Path)
    args = parser.parse_args()
    result = check(args.source, args.candidate, args.report, args.witness)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
