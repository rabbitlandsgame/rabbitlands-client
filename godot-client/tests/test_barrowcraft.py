"""Grounding must survive the seams of supported plank crossings."""
import sys
from pathlib import Path
import numpy as np
import pytest

KIT = Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(KIT))
from amberwood import barrowcraft as B
from verify_runtime import VerticalRayIndex


@pytest.mark.parametrize("length,width,height", [(28.08, 4.4, 3.0), (5.3, 1.8, .7)])
def test_pile_walkway_supports_rays_between_planks(length, width, height):
    bridge = B.pile_walkway(length=length, width=width, deck_height=height)
    triangles = np.concatenate([p.positions[p.indices.reshape(-1, 3)] for p in bridge.walk_parts])
    rays = VerticalRayIndex(triangles)
    # Incommensurate samples include edges and the narrow joints between boards.
    for z in np.linspace(-length / 2 + .001, length / 2 - .001, 701):
        for x in (-width / 2 + .02, 0, width / 2 - .02):
            top = rays.top_hit(x, z)
            assert top is not None, (x, z)
            assert height - .041 <= top <= height + .001, (x, z, top)
    assert rays.top_hit(width / 2 + .1, 0) is None
