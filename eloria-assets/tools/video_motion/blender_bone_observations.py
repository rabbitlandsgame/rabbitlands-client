"""Resolve ambiguous frozen bone names using immutable original matrices."""

import os

os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"

import collections
import hashlib
import json
from pathlib import Path
import numpy as np


def exact_observation_matches(candidates, observations):
    return [
        node
        for node, values in candidates.items()
        if np.array_equal(np.asarray(values), np.asarray(observations))
    ]


def prepare_bone_observations(job):
    from .native_shapes import NativeShapeAsset
    from .asset import digest
    from .blender_bone_identity import prove_duplicate_joint_motion

    source = Path(job["source"])
    witness = Path(job["witness"])
    frozen = json.loads(witness.read_text())
    if frozen["sha256"] != digest(source):
        raise ValueError("Original bone observation source hash differs")
    asset = NativeShapeAsset(source)
    groups = collections.defaultdict(list)
    for node in asset.joints:
        groups[asset.names[node]].append(node)
    expected, actual = collections.defaultdict(list), collections.defaultdict(list)
    duplicate_nodes = [
        node for nodes in groups.values() if len(nodes) > 1 for node in nodes
    ]
    for clip, entries in frozen["clips"].items():
        if not duplicate_nodes:
            break
        t, q, s, m = asset.sample(clip, [entry["time"] for entry in entries])
        for index, entry in enumerate(entries):
            world = asset.world(t[index], q[index], s[index])
            for name, nodes in groups.items():
                if len(nodes) < 2 or name not in entry["bones"]:
                    continue
                expected[name].append(np.asarray(entry["bones"][name]).reshape(4, 4))
                for node in nodes:
                    actual[node].append(world[node])
    selected, aliases, unobserved = {}, [], []
    for name, nodes in groups.items():
        if len(nodes) == 1:
            selected[name] = nodes
            continue
        if not expected[name]:
            # A frozen name lookup is unnecessary for an unobserved name.
            # The importer still binds every original skin/joint by node and
            # hierarchy, and the direct comparison checks every imported bone.
            unobserved.append({"name": name, "original_joint_nodes": nodes})
            continue
        matching = exact_observation_matches(
            {node: actual[node] for node in nodes}, expected[name]
        )
        if not matching:
            raise ValueError("Ambiguous original bone name has no exact observed node")
        if len(matching) > 1:
            aliases += prove_duplicate_joint_motion(asset.d, asset.b, {name: matching})
        selected[name] = matching
    report = {
        "source_sha256": digest(source),
        "witness_sha256": hashlib.sha256(witness.read_bytes()).hexdigest(),
        "observed_original_joint_nodes": selected,
        "unobserved_duplicate_joint_groups": unobserved,
        "all_time_identical_aliases": aliases,
        "scope": "Observed duplicate names resolved through exact full original world-matrix observations at every frozen time; multiple matches require independent all-time ancestor/rest/curve identity. Unobserved duplicate groups retain every original node ID without selecting a named reference. Every original skin/joint remains bound independently and every imported bone is included in direct Blender pose comparisons. No witness values or names are rewritten.",
    }
    output = Path(job["output"]) / "blender-source-bone-observations.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report
