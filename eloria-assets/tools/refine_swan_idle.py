"""Add grounded Swan idle motion without changing its rig or other actions.

The input is the pinned, previously installed Swan. Output must be a separate
versioned candidate. This tool does not install assets or record visual approval.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from video_motion.asset import digest, write_glb
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array

BASE_SHA256 = "60bc59a8e3ecfe0e88a94ffccb9689156a6a929b676c13016539bbf0ce30b4f9"
REVISION = "swan-grounded-idle-v1"
RECIPES = {
    "Idle_A": {"scan_degrees": 5.0, "dip_degrees": 1.4, "breath_metres": 0.0025},
    "Fighting_Idle": {"scan_degrees": 3.5, "dip_degrees": 0.9, "breath_metres": 0.0020},
}


def build(source: Path, output: Path, report: Path) -> dict:
    if source.resolve() == output.resolve():
        raise ValueError("Preserve the input; output must be a separate candidate")
    if output.exists():
        raise ValueError("Use a fresh versioned output; preserve previous candidates")
    if digest(source) != BASE_SHA256:
        raise ValueError("Input does not match the selected installed Swan")
    asset = NativeShapeAsset(source)
    document, binary = copy.deepcopy(asset.d), bytearray(asset.b)
    changed = []
    for animation in document["animations"]:
        clip = animation["name"]
        if clip not in RECIPES:
            continue
        recipe = RECIPES[clip]
        duration = asset.duration(clip)
        # Distribute the fractional endpoint remainder; never exceed 24 Hz.
        intervals = max(1, int(math.floor(duration * 24 + 1e-6)))
        times = np.linspace(0.0, duration, intervals + 1)
        translations, rotations, scales, _ = asset.sample(clip, [0.0])
        baseline_world = asset.world(translations[0], rotations[0], scales[0])
        phase = times / duration * math.tau
        breath = (1.0 - np.cos(phase)) * 0.5
        scan = np.sin(phase) * breath / (3.0 * math.sqrt(3.0) / 8.0)
        # Neutral endpoints and eased analytic curves keep entry/exit quiet.
        breath[[0, -1]] = 0.0
        scan[[0, -1]] = 0.0
        outputs = {}
        neck = asset.ids["neck_01"]
        parent_basis = baseline_world[asset.parent[neck], :3, :3]
        yaw_axis = np.linalg.solve(parent_basis, [0.0, 1.0, 0.0])
        pitch_axis = np.linalg.solve(parent_basis, [1.0, 0.0, 0.0])
        yaw_axis /= np.linalg.norm(yaw_axis)
        pitch_axis /= np.linalg.norm(pitch_axis)
        yaw = Rotation.from_rotvec(scan[:, None] * math.radians(recipe["scan_degrees"]) * yaw_axis)
        pitch = Rotation.from_rotvec(breath[:, None] * math.radians(recipe["dip_degrees"]) * pitch_axis)
        neck_keys = (yaw * pitch * Rotation.from_quat(rotations[0, neck])).as_quat()
        # Preserve the source quaternion sign at neutral and across every key.
        if np.dot(neck_keys[0], rotations[0, neck]) < 0:
            neck_keys *= -1
        neck_keys[[0, -1]] = rotations[0, neck]
        outputs[(neck, "rotation")] = neck_keys
        chest = asset.ids["spine_02"]
        chest_parent = baseline_world[asset.parent[chest], :3, :3]
        up = np.linalg.solve(chest_parent, [0.0, recipe["breath_metres"], 0.0])
        chest_keys = translations[0, chest] + breath[:, None] * up
        chest_keys[[0, -1]] = translations[0, chest]
        outputs[(chest, "translation")] = chest_keys
        # Clone samplers: packed source clips can share their constant samplers.
        time_accessor = append_array(document, binary, times[:, None], "SCALAR")
        for channel in animation["channels"]:
            key = (channel["target"]["node"], channel["target"]["path"])
            if key not in outputs:
                continue
            sampler = {"input": time_accessor,
                       "output": append_array(document, binary, outputs[key],
                                              "VEC4" if key[1] == "rotation" else "VEC3"),
                       "interpolation": "LINEAR"}
            channel["sampler"] = len(animation["samplers"])
            animation["samplers"].append(sampler)
        animation.setdefault("extras", {})["rabbitlands_idle_revision"] = REVISION
        changed.append({"clip": clip, "duration": duration, "keys_per_changed_channel": len(times),
                        "samples_per_second": intervals / duration, **recipe})
    if len(changed) != 2:
        raise ValueError("Both selected idle clips are required")
    document["asset"].setdefault("extras", {})["rabbitlands_idle_revision"] = {
        "id": REVISION, "baseline_sha256": BASE_SHA256,
        "changed_clips": list(RECIPES), "changed_channels": ["neck_01:rotation", "spine_02:translation"],
    }
    write_glb(output, document, binary)
    result = {"revision": REVISION, "source_sha256": BASE_SHA256, "candidate_sha256": digest(output),
              "source_bytes": source.stat().st_size, "candidate_bytes": output.stat().st_size,
              "changed_clips": changed,
              "preservation": "Original binary prefix, static document sections and all unrelated animations remain exact.",
              "visual_approval": "not recorded by this tool"}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.report), indent=2))


if __name__ == "__main__":
    main()
