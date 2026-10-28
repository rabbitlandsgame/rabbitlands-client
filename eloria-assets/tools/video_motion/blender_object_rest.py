"""Recover authored object rest for animated, uniquely named armature objects.

Blender selects an imported action before the checker clears it. Clearing the
action does not restore its object's translation/rotation/scale. Bone rest and
the original vertex/skin identity proof remain independent checks.
"""

import numpy as np

from .blender_vertex_identity import worlds


def animated_armature_rest(document, objects):
    joints = {i for skin in document.get("skins", []) for i in skin["joints"]}
    targets = {
        channel["target"]["node"]
        for animation in document.get("animations", [])
        for channel in animation["channels"]
        if channel["target"].get("path") in ("translation", "rotation", "scale")
        and channel["target"].get("node") not in joints
    }
    conversion = np.array(
        [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float
    )
    result = []
    for index in sorted(targets):
        node = document["nodes"][index]
        matches = [o for o in objects if o["type"] == "ARMATURE" and o["name"] == node.get("name")]
        if not matches:
            continue
        assert len(matches) == 1 and sum(
            n.get("name") == node.get("name") for n in document["nodes"]
        ) == 1, "Ambiguous animated armature object identity"
        local_node = dict(node)
        local_node.pop("children", None)
        authored = worlds({"nodes": [local_node]})[0]
        result.append(
            {
                "original_node": index,
                "original_name": node["name"],
                "blender_object": matches[0]["name"],
                "authored_local_matrix": authored.tolist(),
                "blender_local_matrix": (conversion @ authored @ conversion.T).tolist(),
                "proof_scope": "Unique original animated non-joint node and imported armature object name; subsequent full rest/UV/skin/morph and posed identity checks remain required.",
            }
        )
    return result
