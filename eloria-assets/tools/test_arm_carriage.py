import numpy as np
import pytest
from edit_creature_arm_carriage import swing


def test_bounded_swing_does_not_overshoot_or_mutate_inputs():
    current=np.array([1.,0,0]);goal=np.array([0.,-1,0])
    rotation,degrees=swing(current,goal,25.)
    assert abs(degrees-25)<1e-12
    assert np.allclose(rotation.apply(current),[np.cos(np.deg2rad(25)),-np.sin(np.deg2rad(25)),0])
    assert np.array_equal(current,[1,0,0])and np.array_equal(goal,[0,-1,0])


def test_small_swing_reaches_goal_and_parallel_is_identity():
    goal=[np.cos(.1),np.sin(.1),0]
    assert np.allclose(swing([1,0,0],goal,25)[0].apply([1,0,0]),goal)
    assert np.allclose(swing([1,0,0],[2,0,0],25)[0].as_matrix(),np.eye(3))


@pytest.mark.parametrize('goal',[[0,0,0],[-1,0,0],[float('nan'),0,0]])
def test_ambiguous_or_invalid_plane_fails_closed(goal):
    with pytest.raises(ValueError):swing([1,0,0],goal,25)
