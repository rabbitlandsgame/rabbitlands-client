"""Source-head provenance, usable surface names, and seamless animated necks."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'eloria-assets/tools'))
from shared_player_bodies import g
from verify_shared_player_bodies import primitives, neck_join_checks

MODELS = json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
RACES = [s for s,c in MODELS.items() if 'bodyTemplate' in c and not s.startswith('luminous_')]


@pytest.mark.parametrize('slug', RACES)
def test_high_resolution_head_and_runtime_surfaces(slug):
    d,b=g.read(ROOT/'godot-client'/MODELS[slug]['scene'].removeprefix('res://'))
    source=d['asset']['extras']['highResolutionHead']
    assert source['original'].endswith('_tpose.glb')
    # Per Meshy run (race programme decision 10): the 2026-10 run that made
    # the crowned Glasswarden female head is a 410k-triangle source; the
    # original race run's are over 1.5M.
    floor = 400_000 if 'race_heads_2026-10' in source.get('originalPath', '') else 1_500_000
    assert source['sourceTriangles'] > floor
    assert source['extractedTriangles'] > 200_000
    parts=list(primitives(d,b))
    head_faces=sum(len(f) for _,role,_,f in parts if role=='race_head')
    assert 7000 < head_faces < 22000
    # A duplicate empty node caused Godot to rename the garment on import,
    # breaking both its customization color and armor coverage.
    for name in ('body','eyes','scalp','wardrobe_shirt','wardrobe_pants','wardrobe_boots'):
        nodes=[n for n in d['nodes'] if n.get('name')==name]
        assert len(nodes)==1 and 'mesh' in nodes[0],(slug,name)
    edges,attributes=neck_join_checks(parts)
    assert edges['geometricEdges'] > 50 and edges['unmatchedEdges']==0
    assert attributes['unmatchedCopies']==0
    assert attributes['maxNormalDelta'] < 2e-6
    assert attributes['maxWeightL1Delta'] < 2e-6
