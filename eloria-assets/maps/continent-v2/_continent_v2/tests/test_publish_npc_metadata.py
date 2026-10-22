"""NPC additions may reuse collision only while every collision input stays identical."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_npc_metadata as tool


def snapshots():
    old = {
        'regionId': 'landfall', 'terrain': {'heights': [1, 2, 3]},
        'gameplay': {'npcMarkers': [{'id': 'rowan', 'position': [1, 2, 3]}],
                     'harvestables': [{'id': 'sage', 'position': [4, 5, 6]}]},
        'sources': {'scene': {'path': 'landfall.tscn', 'sha256': 'old'},
                    'authoringSpec': {'path': 'spec.json', 'sha256': 'old'},
                    'dependencies': [{'path': 'ground.glb', 'sha256': 'same'}]},
    }
    new = copy.deepcopy(old)
    new['sources']['scene']['sha256'] = 'new'
    new['sources']['authoringSpec']['sha256'] = 'new'
    new['gameplay']['npcMarkers'].append({'id': 'mara', 'position': [7, 8, 9]})
    return old, new


def test_receipt_records_the_added_post_and_unchanged_content():
    old, new = snapshots()
    entry = tool.receipt(old, new, 'base', 'current')
    assert entry['addedNpcMarkers'] == ['mara']
    assert len(entry['unchangedContentSha256']) == 64
    assert 'collision.bin' in entry['preserved']
    assert old['gameplay']['npcMarkers'] == [{'id': 'rowan', 'position': [1, 2, 3]}]


@pytest.mark.parametrize('part', ['terrain', 'harvestable', 'dependency', 'existing_post'])
def test_geometry_or_existing_content_changes_require_full_publication(part):
    old, new = snapshots()
    if part == 'terrain':
        new['terrain']['heights'][0] = 9
    elif part == 'harvestable':
        new['gameplay']['harvestables'][0]['position'][0] = 9
    elif part == 'dependency':
        new['sources']['dependencies'][0]['sha256'] = 'changed'
    else:
        new['gameplay']['npcMarkers'][0]['position'][0] = 9
    with pytest.raises(ValueError):
        tool.receipt(old, new, 'base', 'current')


def test_removing_a_post_is_refused():
    old, new = snapshots()
    new['gameplay']['npcMarkers'].pop(0)
    with pytest.raises(ValueError):
        tool.receipt(old, new, 'base', 'current')
