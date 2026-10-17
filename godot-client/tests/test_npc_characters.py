"""Validate the authored cast, including binary native-actor name aliases."""
import json
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[1]
CAST = json.loads((CLIENT / 'data/actors/npc_characters.json').read_text(encoding='utf-8'))
MODELS = json.loads((CLIENT / 'data/actors/models.json').read_text(encoding='utf-8'))
EQUIPMENT = json.loads((CLIENT / 'data/actors/equipment.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('key,person', CAST['npcs'].items())
def test_person_is_authored_and_loadable(key, person):
    assert key == person['name'].casefold()
    assert person['model'] in MODELS['models']
    assert len(person['backstory'].split()) >= 12
    assert person['appearanceStory'].strip()
    assert person['dialogueTopics']
    appearance = person['appearance']
    assert set(appearance) == {'skin', 'hair', 'eyes', 'shirt', 'pants', 'boots', 'head'}
    assert 0 <= appearance['skin'] <= 5
    assert 100 <= appearance['hair'] < 300
    assert all(0 <= appearance[part] < 12 for part in ('shirt', 'pants', 'boots', 'eyes'))
    for part, visual in person['equipmentVisuals'].items():
        piece = EQUIPMENT['models'][f'{part}:{visual}']
        assert (CLIENT / piece['scene'].removeprefix('res://')).is_file()
        if piece.get('attach') == 'skinned':
            assert piece.get('fitProfile') == 'canonical'


def test_every_person_has_an_unambiguous_wire_identity():
    wire_keys = {}
    for key, person in CAST['npcs'].items():
        wire = person['name'].encode('latin-1', 'replace')[:29].decode('latin-1').casefold()
        identity = (wire, person['actorType'])
        assert identity not in wire_keys
        wire_keys[identity] = key
        assert CAST['wireNames'].get(wire, wire) == key
    assert set(CAST['wireNames'].values()) <= set(CAST['npcs'])


def test_cast_has_individual_stories_and_wardrobes():
    people = list(CAST['npcs'].values())
    assert len(people) == 259
    assert len({person['backstory'] for person in people}) == len(people)
    assert len({person['outfit'] for person in people}) >= 35
    for region in {p['homeRegion'] for p in people}:
        local = [p for p in people if p['homeRegion'] == region]
        identities = {(p['model'], json.dumps(p['appearance'], sort_keys=True),
                       json.dumps(p['equipmentVisuals'], sort_keys=True)) for p in local}
        assert len(identities) == len(local), region


def test_newcomer_npcs_follow_their_documented_culture():
    for person in CAST['npcs'].values():
        if person['actorType'] <= 263:
            assert person['model'].startswith('luminous_')
