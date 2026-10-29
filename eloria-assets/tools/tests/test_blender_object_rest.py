import unittest

import numpy as np

from video_motion.blender_object_rest import animated_armature_rest


class AnimatedObjectRestTests(unittest.TestCase):
    def document(self):
        return {
            "nodes": [{"name": "Armature", "translation": [1, 2, 3]}, {"name": "Bone"}],
            "skins": [{"joints": [1]}],
            "animations": [{"channels": [{"target": {"node": 0, "path": "translation"}}, {"target": {"node": 1, "path": "rotation"}}]}],
        }

    def test_rest_uses_authored_node_and_axis_conversion(self):
        result = animated_armature_rest(self.document(), [{"name": "Armature", "type": "ARMATURE"}])
        self.assertEqual(result[0]["original_node"], 0)
        np.testing.assert_array_equal(np.array(result[0]["blender_local_matrix"])[:3, 3], [1, -3, 2])

    def test_duplicate_original_identity_fails_closed(self):
        document = self.document()
        document["nodes"].append({"name": "Armature"})
        with self.assertRaisesRegex(AssertionError, "Ambiguous"):
            animated_armature_rest(document, [{"name": "Armature", "type": "ARMATURE"}])

    def test_joint_or_unmatched_object_is_not_reset(self):
        self.assertEqual(animated_armature_rest(self.document(), [{"name": "Bone", "type": "ARMATURE"}]), [])


if __name__ == "__main__":
    unittest.main()
