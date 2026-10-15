"""Keep the Moor shore's geographic paint above its physical shingle bank."""
from pathlib import Path
import sys

regions = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(regions / name) for name in ('_toolkit', '_northern', '_color')]
import terrain_paint


def apply(build):
    # Explicit regional enrollment keeps unrelated source builds unchanged.
    supported = terrain_paint.REGIONS
    try:
        terrain_paint.REGIONS = (*supported, 'amberwood')
        return terrain_paint.apply(build, 'amberwood')
    finally:
        terrain_paint.REGIONS = supported
