"""Height warnings compare adjacent tiles without wrapping opposite shores."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                     'eloria-assets/maps/nymara-regions/_toolkit'))
from verify_runtime import adjacent_jumps, served_reachable


def test_gradual_slopes_do_not_join_opposite_map_edges():
    rows, columns = np.mgrid[:12, :12]
    heights = (rows + columns).astype(float)
    assert adjacent_jumps(heights, np.ones_like(heights, bool)) == []


def test_real_jumps_remain_visible_and_inaccessible_tiles_are_ignored():
    heights = np.array([[0., 10., 20.], [0., 0., 20.]])
    reachable = np.array([[True, True, False], [True, True, False]])
    assert set(adjacent_jumps(heights, reachable)) == {(0, 0, 10.), (1, 0, 10.)}


def test_reachable_fold_checks_every_half_cell_at_bank_edges():
    grid = np.ones((8, 8), dtype=np.uint8)
    grid[3, 3] = 0
    reachable = served_reachable(grid, 4)
    assert not reachable[2, 2]
    assert reachable.sum() == 15
    assert grid[4, 4] == 1  # An even-cell sample misses the blocked bank edge.


def test_reachable_fold_matches_server_clamping_at_the_first_row():
    grid = np.ones((6, 6), dtype=np.uint8)
    assert served_reachable(grid, 3).all()
    grid[0, 0] = 0
    reachable = served_reachable(grid, 3)
    assert not reachable[0, 0]
    assert reachable.sum() == 8
