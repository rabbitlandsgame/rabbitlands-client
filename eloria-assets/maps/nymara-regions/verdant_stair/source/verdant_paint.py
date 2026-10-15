"""Order the two geographic paint recipes over the retained northern soil."""
from pathlib import Path
import sys

regions = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(regions / name) for name in ('_toolkit', '_northern', '_color')]
import terrain_paint


def apply(build):
    # Explicit regional enrollment keeps unrelated source builds unchanged.
    supported = terrain_paint.REGIONS
    try:
        terrain_paint.REGIONS = (*supported, 'verdant_stair')
        return terrain_paint.apply(build, 'verdant_stair')
    finally:
        terrain_paint.REGIONS = supported
