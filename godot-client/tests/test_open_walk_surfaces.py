"""A buried or drowned deck must not reopen inaccessible ground."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                      'eloria-assets/maps/nymara-regions/_toolkit'))
from open_walk_surfaces import exposed_decks


def scene():
    covered = np.zeros((4, 4), dtype=bool)
    covered[1:3, 1] = True  # Half of one server tile is a narrow bridge.
    top = np.where(covered, 5.0, -np.inf)
    wet = np.zeros_like(covered)
    water = np.full_like(top, -np.inf)
    terrain = np.ones_like(covered)
    ground = np.full_like(top, 2.0)
    shut = np.zeros_like(covered)
    return [covered, top, wet, water, terrain, ground, shut]


def test_visible_narrow_bridge_keeps_its_complete_server_tile():
    usable, top, widened, drowned, buried = exposed_decks(*scene())
    assert usable[1:3, 1:3].all()
    assert usable.sum() == 4 and widened == 2
    assert (top[usable] == 5.0).all()
    assert not drowned.any() and not buried.any()


@pytest.mark.parametrize('obstacle', ['bank', 'water', 'wall'])
def test_a_hidden_deck_cannot_open_blocked_ground(obstacle):
    args = scene()
    if obstacle == 'bank':
        args[5][1:3, 1] = 8.0
    elif obstacle == 'water':
        args[2][1:3, 1] = True
        args[3][1:3, 1] = 8.0
    else:
        args[6][1:3, 1] = True
    usable, _, widened, _, _ = exposed_decks(*args)
    assert not usable.any() and widened == 0


@pytest.mark.parametrize('obstacle', ['bank', 'water', 'wall'])
def test_tile_widening_does_not_cross_an_obstruction(obstacle):
    args = scene()
    if obstacle == 'bank':
        args[5][1:3, 2] = 8.0
    elif obstacle == 'water':
        args[2][1:3, 2] = True
        args[3][1:3, 2] = 8.0
    else:
        args[6][1:3, 2] = True
    usable, _, widened, _, _ = exposed_decks(*args)
    assert usable[1:3, 1].all()
    assert not usable[1:3, 2].any()
    assert usable.sum() == 2 and widened == 0


def test_flush_bank_and_shallow_water_tolerances_preserve_a_landing():
    args = scene()
    args[5][:] = 5.02
    args[2][:] = True
    args[3][:] = 5.2
    usable, _, widened, _, _ = exposed_decks(*args)
    assert usable[1:3, 1:3].all() and widened == 2
