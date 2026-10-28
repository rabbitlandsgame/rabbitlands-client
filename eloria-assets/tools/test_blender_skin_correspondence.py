"""Blender-only single-owner slot normalization may not hide skin changes."""

import numpy as np
import pytest

from video_motion.blender_vertex_identity import skin_correspondence


def test_duplicate_single_owner_import_is_recorded_without_mutating_arrays():
    expected = np.array([[0.0, 1.0, 0.0], [0.5, 0.5, 0.0]])
    actual = np.array([[0.0, 0.019184, 0.0], [0.5, 0.5, 0.0]])
    original = (expected.copy(), actual.copy())
    error, raw, rows = skin_correspondence(expected, actual, [8, 2], ["a", "b", "c"])
    assert error == 0 and raw > 0.98 and rows[0]["source_positive_slots"] == 8
    assert rows[0]["bone"] == "b" and rows[0]["blender_stored_total"] == 0.019184
    assert np.array_equal(expected, original[0]) and np.array_equal(actual, original[1])


@pytest.mark.parametrize(
    "expected,actual,slots",
    [
        ([1.0, 0.0], [0.02, 0.0], 1),
        ([0.99, 0.0], [0.02, 0.0], 8),
        ([1.0, 0.0], [0.0, 0.02], 8),
        ([1.0, 0.0], [0.0, 0.0], 8),
        ([0.5, 0.5], [0.01, 0.01], 8),
        ([1.0, 0.0], [0.02, 0.0001], 8),
    ],
)
def test_other_weight_changes_are_not_normalized(expected, actual, slots):
    error, _, rows = skin_correspondence([expected], [actual], [slots], ["a", "b"])
    assert error > 2e-6 and not rows
