"""Retired regional route roots must not carry aerial Walk floors into a city."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import content as C
import scene_io as S
import assemblies as A


def test_manymouth_obsolete_route_parent_removes_its_nested_walk_floor():
    document = {'nodes': [
        {'name': 'Survey_banyan_landing__mangrove_reach', 'children': [1]},
        {'name': 'Walk_Survey_banyan_landing__mangrove_reach__manymouth_teak', 'mesh': 0},
        {'name': 'Survey_cave_mouth__east_hamlet', 'children': [3]},
        {'name': 'Walk_Survey_cave_mouth__east_hamlet__manymouth_teak', 'mesh': 1},
        {'name': 'Landing_banyan_landing', 'children': [5]},
        {'name': 'Walk_Landing_banyan_landing__manymouth_teak', 'mesh': 2},
        {'name': 'east_hamlet_house_00', 'mesh': 3}]}
    placements = [{'node': document['nodes'][i]['name'], 'kind': 'structure'} for i in (0, 2, 4, 6)]
    kept = C.retained_source_placements('manymouth_delta', placements)
    by_name = {node['name']: index for index, node in enumerate(document['nodes'])}
    emitted = {document['nodes'][index]['name'] for index in S.descendants(document, [by_name[p['node']] for p in kept])}
    assert emitted == {'Landing_banyan_landing', 'Walk_Landing_banyan_landing__manymouth_teak', 'east_hamlet_house_00'}
    assert len(placements) == 4, 'The immutable source record remains available for provenance'


def test_route_filter_precedes_assembly_membership_and_preserves_real_floors():
    placements = [{'node': name, 'kind': 'structure'} for name in (
        'Survey_stilt_town__town_hall', 'Walk_Survey_old_route', 'town_house_00',
        'town_porch_00', 'Landing_stilt_town', 'Landmark_GreatArch')]
    kept = C.retained_source_placements('manymouth_delta', placements)
    assert [p['node'] for p in kept] == ['town_house_00', 'town_porch_00', 'Landing_stilt_town', 'Landmark_GreatArch']
    assert A.placement_group('manymouth_delta', kept[0], kept) == 'manymouth_delta.boardwalk-town'
    assert A.placement_group('manymouth_delta', kept[1], kept) == 'manymouth_delta.boardwalk-town'
    assert C.retained_source_placements('westhaven', placements) == placements


def test_new_watershed_retires_only_the_old_wilderness_spans():
    for region,span,discovery in (
        ('mirrorhold','Landmark_MeltwaterBridge_3','Secret_mirror_watch_butts'),
        ('whitehorn_range','Landmark_rope_bridge_00','Secret_horn_bridge_butts')):
        placements=[{'node':name} for name in (span,discovery,'Landmark_CitadelCourt','Landmark_Pier_A')]
        kept=C.retained_source_placements(region,placements)
        assert [p['node'] for p in kept]==[discovery,'Landmark_CitadelCourt','Landmark_Pier_A']
        assert len(placements)==4
