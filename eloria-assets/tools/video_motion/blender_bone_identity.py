"""Explicit node/skin correspondence for models imported as several armatures."""

import collections
import numpy as np

from .blender_vertex_identity import document, array, worlds


def prove_duplicate_joint_motion(doc, blob, groups):
    parents = {
        child: index
        for index, node in enumerate(doc["nodes"])
        for child in node.get("children", [])
    }
    curves = collections.defaultdict(dict)
    for clip_index, clip in enumerate(doc.get("animations", [])):
        for channel in clip["channels"]:
            target = channel["target"]
            if target["path"] == "weights":
                continue
            sampler = clip["samplers"][channel["sampler"]]
            if (clip_index, target["path"]) in curves[target["node"]]:
                raise ValueError("Duplicate source joint animation target")
            curves[target["node"]][(clip_index, target["path"])] = (
                sampler.get("interpolation", "LINEAR"),
                array(doc, blob, sampler["input"]).tobytes(),
                array(doc, blob, sampler["output"]).tobytes(),
            )
    report = []
    for name, nodes in groups.items():
        if len(nodes) < 2:
            continue
        for other in nodes[1:]:
            left, right = nodes[0], other
            while left != right:
                if left is None or right is None:
                    raise ValueError("Duplicate joint ancestor depths differ")
                for field, default in (
                    ("matrix", []),
                    ("translation", [0, 0, 0]),
                    ("rotation", [0, 0, 0, 1]),
                    ("scale", [1, 1, 1]),
                ):
                    if doc["nodes"][left].get(field, default) != doc["nodes"][
                        right
                    ].get(field, default):
                        raise ValueError(
                            "Duplicate joint ancestor rest transforms differ"
                        )
                if curves[left] != curves[right]:
                    raise ValueError(
                        "Duplicate joint ancestor continuous curves differ"
                    )
                left, right = parents.get(left), parents.get(right)
        report.append(
            {
                "name": name,
                "original_joint_nodes": nodes,
                "proof": "Every paired ancestor has identical authored rest transforms and every original TRS sampler's interpolation, times and values. Therefore duplicate joint world matrices agree at arbitrary poses/blends, not merely the frozen witness times.",
            }
        )
    return report


def multiple_armature_bindings(path, arms, observed_nodes=None):
    doc, blob = document(path)
    rest = worlds(doc)
    parents = {
        child: index
        for index, node in enumerate(doc["nodes"])
        for child in node.get("children", [])
    }
    named = collections.defaultdict(list)
    bindings, rows, used = {}, [], set()
    conversion = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
    for skin_index, skin in enumerate(doc["skins"]):
        names = {doc["nodes"][node]["name"] for node in skin["joints"]}
        choices = [
            arm
            for arm in arms
            if arm.name == skin.get("name") and names <= set(arm.pose.bones.keys())
        ]
        if len(choices) != 1:
            raise ValueError(
                "Multiple-armature import needs unique original skin identity"
            )
        arm = choices[0]
        used.add(arm.name)
        joints = set(skin["joints"])
        for node in skin["joints"]:
            name = doc["nodes"][node]["name"]
            bone = arm.pose.bones[name]
            parent = parents.get(node)
            while parent is not None and parent not in joints:
                parent = parents.get(parent)
            expected_parent = (
                doc["nodes"][parent]["name"] if parent is not None else None
            )
            if (bone.parent.name if bone.parent else None) != expected_parent:
                raise ValueError(
                    "Imported bone hierarchy differs from its original skin"
                )
            expected = conversion @ rest[node][:3, 3]
            actual = np.asarray(arm.matrix_world @ bone.head)
            depth, ancestor = 1, node
            while ancestor in parents:
                depth += 1
                ancestor = parents[ancestor]
            # Same operation-count correspondence allowance as the vertex
            # binder: each imported parent composition rounds to float32.
            # This identifies a rest joint; posed/direct gates are unchanged.
            budget = (
                16
                * depth
                * float(np.spacing(np.float32(max(1.0, float(np.abs(expected).max())))))
            )
            error = float(np.linalg.norm(actual - expected))
            component_error = float(np.abs(actual - expected).max())
            if component_error > budget:
                raise ValueError(
                    f"Imported original joint rest head differs: {node}, {error}, {budget}"
                )
            bindings[node] = (arm, bone)
            named[name].append(node)
            rows.append(
                {
                    "source_skin": skin_index,
                    "source_joint_node": node,
                    "imported_armature": arm.name,
                    "bone": name,
                    "parent": expected_parent,
                    "rest_head_error": error,
                    "rest_head_maximum_component_error": component_error,
                    "rest_hierarchy_composition_steps": depth,
                    "rest_identity_component_budget": budget,
                }
            )
    if used != {arm.name for arm in arms}:
        raise ValueError("An imported armature lacks an original skin correspondence")
    # The historical observation dictionary uses names, so identical aliases
    # must be proved before every matching imported bone uses that observation.
    groups = {name: sorted(set(nodes)) for name, nodes in named.items()}
    aliases = (
        prove_duplicate_joint_motion(doc, blob, groups)
        if observed_nodes is None
        else []
    )
    if observed_nodes is not None:
        for name, nodes in observed_nodes.items():
            if not nodes or not set(nodes) <= set(groups.get(name, [])):
                raise ValueError(
                    "Frozen observation joint does not belong to original named skin"
                )
    selected = groups if observed_nodes is None else observed_nodes
    return {
        name: [bindings[node] for node in nodes] for name, nodes in selected.items()
    }, {
        "original_skin_and_joint_node_bindings": rows,
        "duplicate_names_proved_identical_at_all_times": aliases,
        "frozen_observation_original_joint_nodes": selected,
        "scope": "Original skin identity, full nearest-joint hierarchy and neutral rest heads establish correspondence. All matched bones remain checked at every frozen pose; every imported bone matrix is also compared directly between source and candidate.",
    }
