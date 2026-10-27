"""NPC additions may reuse collision only while every collision input stays identical, and every added shop keeps
its map dot (map_categories.py): an unknown category is refused, never dropped."""
import copy
import json
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


def shop(ident, category):
    return {'id': ident, 'name': ident.title(), 'position': [1, 2, 3], 'serverTile': [4, 5],
            'mapCategory': category, 'mapLabel': f"{ident.title()}'s"}


def certified(tmp_path, added):
    """A checkout whose landfall package is certified for a base bake with Rowan's shop, and a bake adding `added`."""
    old, new = snapshots()
    old['gameplay']['npcMarkers'] = [shop('rowan', 'general_store')]
    new['gameplay']['npcMarkers'] = [shop('rowan', 'general_store'), *added]
    for key, text in (('scene', 'scene'), ('authoringSpec', 'spec')):
        path = tmp_path / new['sources'][key]['path']
        path.write_text(text, encoding='utf-8')
        new['sources'][key]['sha256'] = tool.digest(path.read_bytes())
    base, current = tmp_path / 'base.json', tmp_path / 'current.json'
    base.write_text(json.dumps(old), encoding='utf-8')
    current.write_text(json.dumps(new), encoding='utf-8')
    old_sha = tool.digest(base.read_bytes())
    package = tmp_path / 'eloria-assets/maps/continent-v2/landfall/client'
    package.mkdir(parents=True)
    (package / 'collision.bin').write_bytes(b'walk')
    (package / 'served-grid.escg.gz').write_bytes(b'grid')
    manifest = {'provenance': {'snapshotSha256': old_sha}, 'serviceMarkers': [],
                'collision': {'sourceSnapshotSha256': old_sha, 'binary': 'collision.bin', 'sha256': tool.digest(b'walk'),
                              'servedGrid': {'binary': 'served-grid.escg.gz', 'sha256': tool.digest(b'grid')},
                              'groupExport': {'maps': {'landfall': {'snapshotSha256': old_sha}}}}}
    (package / 'world.json').write_text(json.dumps(manifest), encoding='utf-8')
    (package / 'publication.json').write_text(json.dumps({'collision': {}, 'snapshot': {}}), encoding='utf-8')
    return base, current, package / 'world.json'


def test_an_added_shop_of_any_drawn_category_keeps_its_dot(tmp_path):
    base, current, manifest = certified(tmp_path, [shop('lio', 'flower_shop'), shop('garrow', 'blacksmith')])
    rows = tool.prepare(tmp_path, base, current)[manifest]['serviceMarkers']
    assert [(row['id'], row['category'], row['label']) for row in rows] == [
        ('rowan', 'general_store', "Rowan's"), ('lio', 'flower_shop', "Lio's"), ('garrow', 'blacksmith', "Garrow's")]


def test_an_added_shop_of_an_unknown_category_is_refused_not_dropped(tmp_path):
    base, current, _manifest = certified(tmp_path, [shop('tessa', 'books')])
    with pytest.raises(ValueError, match="tessa: map category 'books'"):
        tool.prepare(tmp_path, base, current)
