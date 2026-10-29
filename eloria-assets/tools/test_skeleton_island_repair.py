"""Coincident rest contacts must not be welded by appearance alone."""
import numpy as np
import pytest
from build_skeleton_island_repair import prove_coincident_motion


def fixture():
    return (np.zeros((2, 3)), np.array([[0, 1], [1, 0]]),
            np.array([[.75, .25], [.25, .75]]), np.zeros((3, 2, 3)))


def test_equivalent_reordered_skin_slots_are_safe():
    assert prove_coincident_motion(*fixture())['coincident_groups'] == 1


def test_rest_contact_with_different_skin_is_rejected():
    p, j, w, t = fixture(); w[1] = [.5, .5]
    with pytest.raises(ValueError, match='skin motion'):
        prove_coincident_motion(p, j, w, t)


def test_one_late_corrective_can_separate_rest_contact():
    p, j, w, t = fixture(); t[-1, 1, 2] = 1e-20
    with pytest.raises(ValueError, match='corrective motion'):
        prove_coincident_motion(p, j, w, t)
