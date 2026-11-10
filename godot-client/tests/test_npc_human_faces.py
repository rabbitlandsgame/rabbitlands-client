"""Guard the selected Human cast and the existing head/rig contracts."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
read = lambda name: json.loads((ROOT / 'data/actors' / name).read_text(encoding='utf-8'))
FACES = read('npc_human_faces.json')
CAST = read('npc_characters.json')['npcs']
ARCHETYPES = {row['id']: row for row in read('rl_head_archetypes.json')['archetypes']}
PRESETS = read('rl_head_presets.json')['presets']
PROFILES = [(key, row) for key, variants in FACES['npcs'].items() for row in variants]


@pytest.mark.parametrize('key,profile', PROFILES)
def test_identity_is_valid_for_the_existing_human_body(key, profile):
    assert key == profile['name'].casefold()
    archetype = ARCHETYPES[profile['archetype']]
    assert profile['model'] == archetype['body_template'] == 'luminous_' + archetype['sex']
    assert PRESETS[profile['archetype']]['sex'] == archetype['sex']
    assert 0 <= profile['skin_age'] <= 100
    assert 0 <= profile['hair_grey'] <= 100
    assert 0 <= profile.get('hairStyle', 0) < 10
    assert not {'scale', 'height', 'build', 'equipmentVisuals', 'scene', 'rl_head'} & profile.keys()
    # Existing full outfits stay the authority for model and sex, rather than
    # the generic appearance associated with a shared actor type.
    person = CAST.get(key)
    if person and person['actorType'] == profile['actorType']:
        assert person['model'] == profile['model']


def test_wire_names_and_actor_types_do_not_collide():
    names = {}
    for key, row in PROFILES:
        wire = row['name'].encode('latin-1', 'replace')[:29].decode('latin-1').casefold()
        ident = wire, row['actorType']
        assert ident not in names
        names[ident] = key
        assert FACES['wireNames'].get(wire, wire) == key
    assert set(FACES['wireNames'].values()) <= FACES['npcs'].keys()


def test_existing_human_cast_is_covered_without_replacing_other_peoples():
    for key, person in CAST.items():
        selected = [p for p in FACES['npcs'].get(key, []) if p['actorType'] == person['actorType']]
        if person['model'] in {'luminous_male', 'luminous_female'}:
            assert len(selected) == 1
        else:
            assert not selected
    assert len(PROFILES) == 94
    assert {p['archetype'] for _, p in PROFILES} == set(ARCHETYPES)


def test_family_and_new_landfall_characters_are_explicitly_named():
    assert FACES['npcs']['liora reed'][0]['skin_age'] == 0
    assert FACES['npcs']['liora reed'][0]['hair_grey'] == 0
    for key in ('hanne ashby', 'wynn vell', 'pim', 'aldith', 'jessamy reel',
                'oswin', 'liesl penrose', 'maud fennick', 'fenna ash', 'sela moss', 'nell reed', 'ada vale'):
        assert FACES['npcs'][key]
