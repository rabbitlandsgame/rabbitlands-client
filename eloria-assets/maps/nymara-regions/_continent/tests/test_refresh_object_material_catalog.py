"""Object appearance refresh cannot cross an owner's exact mesh boundary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh_object_material_catalog import _matches_saved_target


def test_exact_owner_and_surface_reject_prefix_collision_and_invalid_slots():
    wrappers = {'amberwood_Tower_WorldPlacement'}
    exact = ['Tower__ashlar', 'Tower', 'amberwood_Tower_WorldPlacement']
    assert _matches_saved_target(exact, 'Tower__ashlar', wrappers, 0, 1, 1)
    assert not _matches_saved_target(
        ['Tower__ashlar', 'amberwood_Tower_extra_WorldPlacement'],
        'Tower__ashlar', wrappers, 0, 1, 1)
    assert not _matches_saved_target(exact, 'Tower__ashlar', wrappers, 1, 1, 1)
    assert not _matches_saved_target(exact, 'Tower__ashlar', wrappers, -1, 1, 1)
    assert not _matches_saved_target(exact, 'Tower__ashlar', wrappers, 0, 1, 2)
