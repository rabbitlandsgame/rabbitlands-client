"""Widening a deck must not leave a permitted actor position over open water."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                     'eloria-assets/maps/nymara-regions/_toolkit'))
from guard_actor_surfaces import guarded_grid


def test_closes_unsupported_and_submerged_tiles_without_erasing_supported_neighbours():
    grid = np.full((8, 8), 21, np.uint8)
    encoding = {'origin': -.2, 'step': .2}
    covered = np.ones((4,4), bool)
    top = np.full((4,4), 4.)
    wet = np.zeros((4,4), bool)
    water = np.zeros((4,4))
    top[1,1] = -2  # Widened deck's actor actually lands on the lake bottom.
    covered[1,2] = False
    wet[2,2] = True
    water[2,2] = 6
    result, bad, *_ = guarded_grid(grid, encoding, covered, top, wet, water)
    assert set(zip(*np.nonzero(bad))) == {(1,1),(1,2),(2,2)}
    assert np.all(result[1:3,1:5] == 0)
    assert np.all(result[3:5,3:5] == 0)
    assert np.all(result[5:,5:] == grid[5:,5:])
    assert np.all(result <= grid)
    repeated, again, *_ = guarded_grid(result, encoding, covered, top, wet, water)
    assert np.array_equal(result, repeated)
    assert not again.any()
