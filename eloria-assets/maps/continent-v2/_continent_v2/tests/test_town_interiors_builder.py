"""The Landfall Town interiors builder (2026-10-27): its source format, its gate and its room shells.

    python -B -m pytest -p no:cacheprovider -q eloria-assets/maps/continent-v2/_continent_v2/tests/test_town_interiors_builder.py

The source tests read content/landfall_town.json. The synthetic build builds a two-section town (a shop with a back
room, an upstairs reached by a stair) from a source written here into a temporary folder, with the real builder; it
writes the served grid only when ELORIA_SERVER_ROOT names a server checkout (its served-grid codec).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import town_source as TS  # noqa: E402

SOURCE = HERE/'content/landfall_town.json'
BUILDER = HERE/'build_town_interiors.py'
INSIDES = HERE.parent/'landfall_insides/client/world.json'
TOWN = HERE.parent/'landfall_town/client/world.json'
SERVER = os.environ.get('ELORIA_SERVER_ROOT')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- the authored source -----------------------------------------------------------------------------------------


def test_the_source_writer_reproduces_the_authored_file():
    raw = SOURCE.read_bytes()
    design = json.loads(raw)
    assert TS.dump(design).encode('utf-8') == raw
    annotated = copy.deepcopy(design)
    for section in annotated['sections']:
        section['_ends'], section['_arrival'] = [], [0, 0]
    assert TS.dump(annotated).encode('utf-8') == raw
    # one door, prop, window, decal and light per line
    lines = raw.decode('utf-8').splitlines()
    assert sum('"object": 592' in line and '"kind": "building"' in line for line in lines) == 10
    assert all(line.count('"kind": "building"') <= 1 for line in lines)


def test_the_authored_source_holds_the_spec_doors_and_the_stairs():
    design = TS.load(SOURCE)
    assert TS.check(design)
    assert design['map']['cells'] == 324 and design['map']['alias'] == 'LFT'
    doors = TS.doors(design)
    by_object = {d['object']: d for d in doors}
    # SPEC section 3, ids in table order A, B, C, D, E, G, H, I, J, K
    table = [(59201, 'tavern_ground', [107, 250], [104, 247], 'tavern'),
             (59202, 'market', [131, 254], [134, 251], 'general_store'),
             (59203, 'market', [124, 251], [127, 248], 'flower_shop'),
             (59204, 'magic_shop', [166, 265], [167, 262], 'magic_shop'),
             (59205, 'smithy', [97, 261], [95, 259], 'blacksmith'),
             (59206, 'clerk_house', [146, 259], [149, 256], None),
             (59207, 'weaver_house', [152, 252], [149, 255], None),
             (59208, 'watch_house', [86, 275], [83, 275], None),
             (59209, 'netmender_house', [239, 208], [234, 207], None),
             (59210, 'castle', [221, 276], [218, 273], None)]
    assert sorted(by_object) == [row[0] for row in table]
    for oid, section, tile, back, category in table:
        door = by_object[oid]
        assert (door['section'], door['tile'], door['returnTile'], door['category']) == (section, tile, back, category)
        assert door['kind'] == 'building' and 'marker' not in door and door['label'] and door['exitLabel']
        # arrival two or three tiles in from the exit, straight away from the wall
        dx, dy = door['exitFacing']
        steps = (door['exit'][0]-door['arrival'][0])*dx+(door['exit'][1]-door['arrival'][1])*dy
        assert steps in (2, 3)
        assert (door['exit'][0]-door['arrival'][0])*dy == 0 and (door['exit'][1]-door['arrival'][1])*dx == 0
    (stairs,) = TS.passages(design)
    assert [e['object'] for e in stairs['ends']] == [59221, 59222]
    assert [e['art'] for e in stairs['ends']] == ['stairs_up', 'stairs_down']
    assert [e['section'] for e in stairs['ends']] == ['tavern_ground', 'tavern_upper']
    castle = next(s for s in design['sections'] if s['id'] == 'castle')
    assert castle['roomNames'][:4] == ['Gate Hall', 'Hall of Eight Seats', 'Register Archive', 'Palace Chancery']
    assert castle['sealedStairs'] and not TS.passage_ends(design, 'castle')
    # the cast (2026-10-27): every coloured door opens on a shopkeeper of its category, who is named on the map as the
    # door is; the lore objects keep to the interior band
    people = TS.npcs(design)
    assert len({p['name'] for p in people}) == len(people) == 20
    keepers = {(p['section'], p['mapCategory']): p for p in people if p.get('mapCategory')}
    assert all(p['role'] == 'shop' for p in keepers.values())
    for oid, section, _tile, _back, category in table:
        if category:
            assert by_object[oid]['label'] == keepers[(section, category)]['mapLabel']
    assert sorted(keepers) == sorted((row[1], row[4]) for row in table if row[4])
    found = TS.interactives(design)
    assert found and all(entry['object'] in TS.INTERACTIVE_IDS for entry in found)
    assert [e['role'] for e in found if e['role'] == 'crafting_station'] == ['crafting_station']
    # every lore object names its short label and the point of the prop or picture it describes (the pick-only
    # objects.json record, retarget_underground.py); the anvil serves smithing
    assert all(entry.get('label') and entry.get('at') for entry in found)
    assert [e['target'] for e in found if e['role'] == 'crafting_station'] == ['smithing']


def test_the_lore_objects_show_what_their_plaques_say():
    """Review 2026-10-27: each place in the Hall of Eight Seats reads as its plaque says. The Stoneborn place is a
    plain stone standing where a chair would (no sundial, no seat); the Mycelari seat carries lichen-coloured lichen
    (a MineralAppearance palette) on both its arms and round its foot; nothing hangs from the ceiling the cutaway never
    draws (no chandelier). The tavern kitchen's stores stand upright (its lying barrels' ends painted streaky white),
    and the watch house's Landfall map hangs large on a wall the camera faces, the duty board on the wall beside the
    door."""
    design = TS.load(SOURCE)
    castle = section(design, 'castle')
    plaques = {entry['object']: entry for entry in castle['interactives']}

    def standing(point, reach=.05):
        return [p for p in castle['props'] if max(abs(p['at'][0]-point[0]), abs(p['at'][1]-point[1])) < reach]

    stone = standing(plaques[59276]['at'])
    assert [p['asset'] for p in stone] == ['moor_stone_1'] and set(stone[0]['palette']) == {'stone', 'mineral'}
    assert 'stone' in plaques[59276]['text'] and 'where a chair would stand' in plaques[59276]['text']
    for seat in (59273, 59274, 59275):
        assert [p['asset'] for p in standing(plaques[seat]['at'])] == ['high_seat']
    lichen = [p for p in standing(plaques[59275]['at'], 1.0) if p['asset'] == 'lichen_mat']
    assert lichen and all(set(p.get('palette', {})) == {'stone', 'mineral'} for p in lichen)
    assert sum(p.get('height', 0) > .7 for p in lichen) == 2 and any(p.get('height', 0) == 0 for p in lichen)
    assert 'over its arms' in plaques[59275]['text'] and 'round its foot' in plaques[59275]['text']
    assert not [p for s in design['sections'] for p in s['props'] if p['asset'] == 'chandelier']
    tavern = section(design, 'tavern_ground')
    kitchen = [p['asset'] for p in tavern['props'] if TS.room_of(tavern, *p['at']) == 1]
    assert kitchen and 'barrel_stack' not in kitchen
    watch = section(design, 'watch_house')
    (wall_map,) = [d for d in watch['decals'] if d['image'] == 'map_landfall']
    assert wall_map['side'] == 'north' and wall_map['size'][0] >= 2.0
    board = next(e for e in watch['interactives'] if e['object'] == 59283)
    assert [p['asset'] for p in watch['props'] if p['at'] == board['at']] == ['notice_board']


def mutate(change):
    design = TS.load(SOURCE)
    change(design)
    return design


def section(design, ident):
    return next(s for s in design['sections'] if s['id'] == ident)


REFUSALS = {
    'a building door with a marker': (lambda d: section(d, 'market')['entrances'][0].update(marker='landfall--x'),
                                      'no scene marker'),
    'an unknown category': (lambda d: section(d, 'market')['entrances'][0].update(category='bakery'), 'map category'),
    'a door without its exit label': (lambda d: section(d, 'smithy')['entrances'][0].pop('exitLabel'), 'lacks'),
    'a door facing a corner': (lambda d: section(d, 'smithy')['entrances'][0].update(exitFacing=[1, 1]),
                               'exitFacing'),
    'a room edge off the tile-row centres': (lambda d: section(d, 'magic_shop')['rooms'][0].__setitem__(2, 5.25),
                                             'tile-row centres'),
    'overlapping rooms': (lambda d: section(d, 'smithy')['rooms'][1].__setitem__(1, 27.5), 'overlap'),
    'sections too close': (lambda d: d['sections'].append(
        {'id': 'shed', 'name': 'Shed', 'style': 'house', 'danger': 'Private', 'rooms': [[45.5, 25.5, 2, 2]],
         'roomNames': ['Shed'], 'links': [], 'floors': ['oak_planks'], 'walls': 'lime_plaster',
         'entrances': [{'map': 'landfall', 'kind': 'building', 'object': 59211, 'tile': [1, 1],
                        'position': [0, 0, 0], 'returnTile': [1, 2], 'arrival': [45, 25], 'exit': [45, 24],
                        'label': 'Shed', 'exitLabel': 'Out'}], 'nodes': [], 'spawns': []}), 'blackspace'),
    'a door id outside its band': (lambda d: section(d, 'castle')['entrances'][0].update(object=59300), 'band'),
    'an id used twice': (lambda d: section(d, 'castle')['entrances'][0].update(object=59201), 'used twice'),
    'a doorway too narrow': (lambda d: section(d, 'clerk_house')['links'][0].__setitem__(2, 2.0), 'no walkable'),
    'a link between rooms that share no wall': (lambda d: section(d, 'castle')['links'].append([2, 3, 2.4]),
                                                'share no wall'),
    'roomNames not one per room': (lambda d: section(d, 'castle')['roomNames'].pop(), 'roomNames'),
    'a harvest node': (lambda d: section(d, 'castle')['nodes'].append([59299, 'Coal', 30, 150]), 'nodes'),
    'an unknown stair art': (lambda d: d['passages'][0].update(art='ladder'), 'art'),
    'an unknown decal': (lambda d: section(d, 'castle')['decals'][0].update(image='banner_unicorn'), 'decal'),
    'too many lights in a room': (lambda d: section(d, 'magic_shop')['lights'].extend(
        [copy.deepcopy(section(d, 'magic_shop')['lights'][0]) for _ in range(4)]), 'lights'),
    'an NPC on no reviewed body': (lambda d: section(d, 'market')['npcs'].append(
        {'name': 'X', 'role': 'shop', 'occupation': 'Grocer', 'actorType': 12, 'facing': 'S', 'tile': [135, 25],
         'greeting': 'Hi.'}), 'actorType'),
    'an interactive with an unknown role': (lambda d: section(d, 'market')['interactives'].append(
        {'object': 59251, 'tile': [135, 25], 'role': 'shop', 'text': 'x'}), 'role'),
    'an unknown section key': (lambda d: section(d, 'market').update(ceiling=4), 'unknown keys'),
    'an interactive with an unknown key': (lambda d: section(d, 'smithy')['interactives'][0].update(colour=1),
                                           'unknown keys'),
    'an interactive point outside the rooms': (lambda d: section(d, 'castle')['interactives'][0].update(at=[0, 0]),
                                               'none of the'),
    'a target holding a bar': (lambda d: section(d, 'smithy')['interactives'][0].update(target='smith|ing'),
                               'holds'),
    'a wall decal at a height': (lambda d: section(d, 'castle')['decals'][0].update(height=1.0),
                                 'only a floor decal'),
}


@pytest.mark.parametrize('name', sorted(REFUSALS))
def test_check_refuses(name):
    change, words = REFUSALS[name]
    with pytest.raises(TS.SourceError, match=words):
        TS.check(mutate(change))


# --- the gate ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize('note', [None, '  '])
def test_the_builder_refuses_without_the_owners_approval(tmp_path, note):
    command = [sys.executable, '-B', str(BUILDER), '--out', str(tmp_path/'package'), '--no-registry']
    if note is not None:
        command += ['--owner-approved', note]
    run = subprocess.run(command, capture_output=True, text=True, cwd=HERE)
    assert run.returncode != 0 and 'owner-approved' in run.stderr and 'No outputs were written' in run.stderr
    assert not (tmp_path/'package').exists()


def test_build_underground_is_unchanged():
    """The cave builder's hash pins the landfall_insides package: this builder imports it and never edits it."""
    provenance = json.loads(INSIDES.read_text(encoding='utf-8'))['provenance']
    assert provenance['builder'] == '_continent_v2/build_underground.py'
    assert sha(HERE/'build_underground.py') == provenance['builderSha256']


def test_the_town_package_was_built_from_this_source_and_builder():
    if not TOWN.is_file():
        pytest.skip('landfall_town has not been built')
    provenance = json.loads(TOWN.read_text(encoding='utf-8'))['provenance']
    assert provenance['builder'] == '_continent_v2/build_town_interiors.py'
    assert provenance['builderSha256'] == sha(BUILDER), 'build_town_interiors.py changed: rebuild the package'
    assert provenance['sourceSha256'] == sha(SOURCE), 'landfall_town.json changed: rebuild the package'
    for name, digest in provenance['imports'].items():
        assert sha(HERE.parent/name) == digest, f'{name} changed: rebuild the package'


def test_the_authored_town_lays_out():
    import build_town_interiors as T
    design = T.load_design()
    half, coarse = T.masks(design)
    T.protect(design, coarse)
    for item in design['sections']:
        assert coarse[item['_arrival'][1], item['_arrival'][0]]


def test_every_room_plays_its_own_music():
    """The music sync (eloria-assets/tools/sync_music_program.py) turns the package's spaces (by room name) and chambers
    (by room name, else section id) into zones, the smallest holding a tile winning: every walkable tile of a room must
    take its room's program (a doorway's tile, on the wall line, may take either side's)."""
    if not TOWN.is_file():
        pytest.skip('landfall_town has not been built')
    import build_town_interiors as T
    sys.path.insert(0, str(T.CHECKOUT/'eloria-assets/tools'))
    import sync_music_program as music
    registry = json.loads(T.REGISTRY.read_text(encoding='utf-8'))['maps']
    if 'landfall_town' not in registry:
        pytest.skip('landfall_town has no registry row yet')
    zones, _ = music.interior_zones('landfall_town', registry['landfall_town'])
    design = T.load_design()
    _half, coarse = T.masks(design)
    wrong = []
    for item in design['sections']:
        for index, (x0, y0, x1, y1) in enumerate(TS.rooms(item)):
            want = music.room_program(item['roomNames'][index]) or music.room_program(item['id'])
            for y in range(int(y0), int(y1)+1):
                for x in range(int(x0), int(x1)+1):
                    px, py = x+.5, y+.5
                    if not coarse[y, x] or TS.room_of(item, px, py) != index or px in (x0, x1) or py in (y0, y1):
                        continue
                    found = [z for z in zones if 'bounds' in z and z['bounds'][0] <= px <= z['bounds'][2]
                             and z['bounds'][1] <= py <= z['bounds'][3]]
                    got = min(found, key=lambda z: (z['bounds'][2]-z['bounds'][0])*(z['bounds'][3]-z['bounds'][1]),
                              default={}).get('day')
                    if got != want:
                        wrong.append((item['id'], item['roomNames'][index], (x, y), want, got))
    assert not wrong, wrong[:10]


# --- a synthetic build -------------------------------------------------------------------------------------------


def door(**extra):
    return {'map': 'landfall', 'kind': 'building', 'object': 59201, 'tile': [5, 5], 'position': [0.0, 0.0, 0.0],
            'returnTile': [5, 4], 'arrival': [15, 13], 'exit': [15, 11], 'exitFacing': [0, -1],
            'category': 'general_store', 'label': 'The test shop', 'exitLabel': 'The test street', **extra}


def synthetic():
    shop = {'id': 'shop', 'name': 'Test Shop', 'style': 'shop', 'danger': 'Open to all', 'about': 'A test.',
            # front room x 10.5-20.5, y 10.5-16.5; back room y 16.5-21.5; a doorway on tile (13, 16)
            'rooms': [[15.5, 13.5, 5, 3], [15.5, 19, 5, 2.5]], 'roomNames': ['Test shop', 'Test store room'],
            'links': [[0, 1, 2.4, [[13.5, 16.5]]]], 'floors': ['oak_planks', 'cobalt_tile'],
            'walls': ['lime_plaster', 'soot_brick'],
            'windows': [{'room': 0, 'side': 'west', 'at': 0.5, 'width': 1.2},
                        {'room': 1, 'side': 'north', 'at': 0.25, 'width': 1.2}],
            'decals': [{'image': 'banner_orun', 'room': 1, 'side': 'north', 'at': [0.55, 0.55], 'size': [0.9, 1.8]},
                       {'image': 'rug_home', 'room': 0, 'side': 'floor', 'at': [0.5, 0.5], 'size': [2.4, 1.6]},
                       {'image': 'botanical_prints', 'room': 0, 'side': 'north', 'at': [0.8, 0.5], 'size': [1.6, 0.8]}],
            'entrances': [door()],
            'props': [{'asset': 'crate_stack', 'at': [19.6, 12.0], 'yaw': 0, 'blockBox': [0.9, 0.9], 'wall': 'east'},
                      {'asset': 'tool_rack', 'at': [12.0, 19.5], 'yaw': 90, 'blockBox': [1.0, 0.5], 'wall': 'west'},
                      {'asset': 'barrel_stack', 'at': [14.5, 20.0], 'yaw': 0, 'block': 0.7}],
            'lights': [{'at': [15.5, 13.5], 'height': 2.9, 'colour': [1, 0.8, 0.6], 'energy': 1.2, 'range': 8},
                       {'at': [15.5, 19.0], 'height': 2.9, 'colour': [1, 0.8, 0.6], 'energy': 0.8, 'range': 6}],
            'npcs': [{'name': 'Test Keeper', 'role': 'shop', 'occupation': 'Keeper', 'actorType': 300, 'facing': 'S',
                      'tile': [17, 14], 'greeting': 'Hello.', 'mapCategory': 'general_store'}],
            'interactives': [{'object': 59251, 'tile': [19, 15], 'role': 'information', 'text': 'A notice.'}],
            'nodes': [], 'spawns': []}
    upstairs = {'id': 'upstairs', 'name': 'Test Upstairs', 'style': 'house', 'danger': 'Private',
                'rooms': [[54.5, 13.5, 4, 3]], 'roomNames': ['Test home'], 'links': [], 'floors': ['oak_planks'],
                'walls': 'lime_plaster', 'nodes': [], 'spawns': []}
    return {'schema': TS.SCHEMA,
            'map': {'id': 'test_town', 'name': 'Test Town', 'alias': 'TT', 'cells': 120,
                    'builder': 'build_town_interiors',
                    'environment': {'profile': 'town-interior', 'ambient': {'color': '#d9c8a8', 'energy': 0.6},
                                    'sun': {'enabled': True, 'energy': 0.25, 'shadows': False},
                                    'dayNight': {'enabled': False}},
                    'camera': {'distance': 12, 'minDistance': 6, 'maxDistance': 26, 'pitchDegrees': -50,
                               'zoomStep': 1.2}},
            'sections': [shop, upstairs],
            'passages': [{'object': 59221, 'name': 'Test stairs', 'art': 'stairs_up',
                          'ends': [{'section': 'shop', 'tile': [17, 17], 'arrival': [16, 17], 'facing': [0, 1],
                                    'label': 'Upstairs'},
                                   {'section': 'upstairs', 'tile': [54, 13], 'arrival': [54, 12], 'facing': [0, 1],
                                    'art': 'stairs_down'}]}]}


def glb_nodes(path):
    data = Path(path).read_bytes()
    length = struct.unpack('<I', data[12:16])[0]
    document = json.loads(data[20:20+length])
    return {node['name'] for node in document['nodes'] if 'mesh' in node}


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    import build_town_interiors as T
    root = tmp_path_factory.mktemp('town')
    source = root/'landfall_town.json'
    source.write_bytes(TS.dump(synthetic()).encode('utf-8'))
    package = root/'package'
    summary = T.build(Path(SERVER) if SERVER else None, source=source, out=package, registry=False,
                      approval='test, 2026-10-27: synthetic build', share_images=False)
    raw = (package/'collision.bin').read_bytes()
    width = struct.unpack('<I', raw[8:12])[0]
    half = np.frombuffer(raw[16:], dtype=np.uint8).reshape(width, width).astype(bool)
    coarse = half.reshape(width//2, 2, width//2, 2).all(axis=(1, 3))
    return SimpleNamespace(T=T, source=source, package=package, summary=summary, design=T.load_design(source),
                           manifest=json.loads((package/'world.json').read_text(encoding='utf-8')),
                           nodes=glb_nodes(package/'world.glb'), coarse=coarse)


def test_rooms_are_sharp_rectangles_sharing_walls(built):
    shop = built.design['sections'][0]
    shape = built.T.outline(shop)
    assert set(shape.exterior.coords) == {(10.5, 10.5), (20.5, 10.5), (20.5, 21.5), (10.5, 21.5)}
    assert shape.area == pytest.approx(10*6+10*5)
    (part,) = built.T.partitions(shop)
    assert part['rooms'] == (0, 1) and part['a'] == (10.5, 16.5) and part['b'] == (20.5, 16.5)
    assert part['openings'][0][:2] == pytest.approx((1.8, 4.2))


def test_a_doorway_is_a_flat_opening_with_one_open_tile(built):
    row = built.coarse[16]
    assert row[13] and not any(row[x] for x in range(10, 22) if x != 13)
    # the wall rows themselves are closed: margins keep the floor off every wall
    assert not built.coarse[10, 11:20].any() and not built.coarse[21, 11:20].any()
    assert built.coarse[11, 11:18].all()


def test_windows_decals_doors_and_stairs_are_drawn(built):
    nodes = built.nodes
    pane = built.T.window_art(built.T.THEMES['shop'])
    for name in (f'Build_shop_west_{pane}', f'Build_shop_north_{pane}', 'Build_shop_north_decal_banner_orun',
                 'Decal_shop_decal_rug_home', 'Part_shop_0_decal_botanical_prints', 'Build_shop_south_door_daylight',
                 'Door_shop_door_spill', 'Build_shop_stair0_stair_dark', 'Stair_upstairs_0_stair_dark',
                 'Walk_shop_oak_planks', 'Walk_shop_cobalt_tile', 'Part_shop_0_lime_plaster', 'Part_shop_0_soot_brick',
                 'Roof_shop_wall_cap', 'Build_shop_north_wall_cap', 'Build_shop_north_timber_band'):
        assert name in nodes, name


def test_stairs_are_steps_with_rails_and_a_stairwell_is_never_a_black_pit(built):
    """A flight: lit treads, shaded risers, timber stringers and rails; a stairwell: treads and sides that darken with
    depth (not black), a dark way on only at its foot under a lintel, and rails along both sides."""
    nodes = built.nodes
    for name in ('Build_shop_stair0_oak_planks', 'Build_shop_stair0_oak_planks_shade', 'Build_shop_stair0_timber_band',
                 'Stair_upstairs_0_oak_planks', 'Stair_upstairs_0_oak_planks_shade', 'Stair_upstairs_0_oak_planks_dusk',
                 'Stair_upstairs_0_lime_plaster_shade', 'Stair_upstairs_0_timber_band', 'Stair_upstairs_0_stair_dark'):
        assert name in nodes, name
    data = (built.package/'world.glb').read_bytes()
    document = json.loads(data[20:20+struct.unpack('<I', data[12:16])[0]])
    shade = next(m for m in document['materials'] if m['name'] == 'oak_planks_shade')['pbrMetallicRoughness']
    plain = next(m for m in document['materials'] if m['name'] == 'oak_planks')['pbrMetallicRoughness']
    # the shaded copy samples the same texture under a darker base colour
    assert shade['baseColorTexture'] == plain['baseColorTexture']
    assert shade['baseColorFactor'][:3] == [built.T.SHADES['_shade']]*3
    # each passage portal carries its drawn stair's offset from the end tile (retarget writes it into objects.json)
    portals = {p['id']: p for p in built.manifest['portals']}
    assert portals['shop-passage0-0']['modelOffset'] == [0.0, 0.0, -2.7]       # a 2.6 m flight ending 4 m north
    assert portals['upstairs-passage0-1']['modelOffset'] == [0.0, 0.0, -2.0]   # a 2 m well ending 3 m north


def test_street_doors_spill_soft_daylight_and_doorways_have_timber_jambs(built):
    nodes = built.nodes
    assert {'Door_shop_door_spill', 'Door_shop_timber_band', 'Part_shop_0_timber_band'} <= nodes
    door = built.T.FLAT['door_daylight']
    assert max(door['emissive']) < .5 and max(door['base_color'][:3]) < .8   # warm, not blown out
    assert built.T.THEMES['castle']['doorWidth'] <= 2.5
    from PIL import Image
    import io
    picture = Image.open(io.BytesIO(built.T.door_spill_image())).convert('RGBA')
    alpha = np.asarray(picture)[..., 3]
    # brightest at the threshold's middle, fading into the room and to both sides
    assert alpha[0, 32] == alpha.max() > 0 and alpha[-1].max() == 0 and alpha[:, 0].max() == 0


def test_the_keeps_street_door_stands_open_on_two_plank_leaves():
    """A theme with doorLeaves (the keep's) draws the street door's two leaves folded back flat against the wall either
    side of its frame, inside the wall's walk margin (the walk grid is unchanged); every other theme draws none. A
    window within the leaves' reach is refused."""
    import build_town_interiors as T

    def drawn(style, windows=()):
        design = synthetic()
        design['sections'][0].update(style=style, windows=list(windows))
        shop = T.annotate(design)['sections'][0]
        pieces = []
        def add(piece, bucket):
            pieces.append(piece)
        T.window_geometry(shop, add, T.door_geometry(shop, add))
        return [piece for piece in pieces if piece.material in (T.LEAF_SURFACE, 'iron')]

    leaves = drawn('castle')
    assert {piece.material for piece in leaves} == {T.LEAF_SURFACE, 'iron'} and not drawn('shop')
    assert T.THEMES['castle']['doorLeaves'] and not any(T.THEMES[s]['doorLeaves'] for s in T.THEMES if s != 'castle')
    # the synthetic door: exit (15, 11) facing south, so its wall runs along tile y 10.5 and the doorway is centred on
    # x 15.5 (world() puts tile y at world z = cells - y, so the room lies toward -z)
    half, theme = T.THEMES['castle']['doorWidth']/2, T.THEMES['castle']
    points = np.vstack([piece.positions for piece in leaves])
    along = np.abs(points[:, 0]-15.5)
    assert along.min() >= half+T.LEAF_GAP-1e-6 and along.max() <= 2*half+T.LEAF_GAP+1e-6
    depth = T.world(15.5, 10.5)[2]-points[:, 2]
    assert depth.min() >= -1e-6 and depth.max() <= T.LEAF_THICKNESS+.03 < theme['margin']
    assert points[:, 1].max() <= theme['doorHeight']+1e-6
    assert T.door_reach(theme) == pytest.approx(2*half+T.LEAF_GAP) and T.door_reach(T.THEMES['shop']) == 1.0
    window = {'room': 0, 'side': 'south', 'at': 0.25, 'width': 1.0}   # centred 2.5 m from the doorway's centre
    assert not drawn('shop', [window])
    with pytest.raises(SystemExit, match='open leaves'):
        drawn('castle', [window])


def test_the_minimap_frames_a_building_at_minimap_size(built):
    """main.gd _bind_minimap_span reads world.json minimap.liveSpanMetres: the town's live minimap shows 40 m, so its
    rooms read at minimap size (review 2026-10-27: a section was 10-20 px at the default span)."""
    assert built.T.MINIMAP_LIVE_SPAN == 40
    block = built.manifest['minimap']
    assert block['liveSpanMetres'] == 40 and block['imageSize'] == [360, 360] and block['worldMax'] == [120, 120]
    if TOWN.is_file():
        assert json.loads(TOWN.read_text(encoding='utf-8'))['minimap']['liveSpanMetres'] == 40


def test_props_against_a_partition_name_it_as_their_cutaway_wall():
    """A prop hung on a partition or standing with its back to one carries that partition's node (in its own room's
    surface) as `cutawayWall`, so the runtime hides it with the partition; a prop turned to face the partition, or
    standing clear of it, carries none."""
    import build_town_interiors as T
    design = synthetic()
    design['sections'][0]['props'] += [
        {'asset': 'wall_sconce', 'at': [16.0, 16.3], 'yaw': 0, 'height': 1.6},
        {'asset': 'bookcase', 'at': [18.5, 16.05], 'yaw': 0, 'blockBox': [0.66, 0.2]},
        {'asset': 'bookcase', 'at': [17.0, 17.0], 'yaw': 180, 'blockBox': [0.66, 0.2]},
        {'asset': 'supply_chest', 'at': [18.5, 15.95], 'yaw': 180, 'blockBox': [0.5, 0.3]},
        {'asset': 'stool', 'at': [15.0, 14.0], 'yaw': 0, 'blockBox': [0.2, 0.2]}]
    design = T.annotate(design)
    placed = T.dressing(design['sections'][0])[-5:]
    assert [item.get('cutawayWall') for item in placed] == [
        'Part_shop_0_lime_plaster', 'Part_shop_0_lime_plaster', 'Part_shop_0_soot_brick', None, None]


def test_decals_clamp_to_their_edge_and_surfaces_repeat(built):
    """A decal is one picture: its texture samples CLAMP_TO_EDGE, so its far edge never bleeds in at low mip levels;
    the tiling surfaces repeat."""
    data = (built.package/'world.glb').read_bytes()
    document = json.loads(data[20:20+struct.unpack('<I', data[12:16])[0]])
    samplers = document['samplers']
    wraps = {}
    for texture in document['textures']:
        sampler = samplers[texture.get('sampler', 0)]
        wraps[document['images'][texture['source']]['name']] = (sampler['wrapS'], sampler['wrapT'])
    decals = {name for name in wraps if name.startswith('decal_')}
    assert decals == {'decal_banner_orun', 'decal_rug_home', 'decal_botanical_prints'}
    # the other single pictures: the door's daylight spill and, once the art role publishes it, the painted window
    glazing = built.T.window_art(built.T.THEMES['shop'])
    pictures = decals | {'door_spill'} | ({glazing} if glazing in built.T.WINDOW_ART else set())
    assert pictures <= set(wraps)
    assert all(wraps[name] == (33071, 33071) for name in pictures)
    assert all(wraps[name] == (10497, 10497) for name in set(wraps) - pictures)
    assert 'oak_planks' in wraps and len(samplers) == 2


def test_cutaway_takes_walls_by_facing_and_leaves_partitions_to_the_fade(built):
    cutaway = built.manifest['cutaway']
    assert cutaway['facingThreshold'] == 0.35 and cutaway['props']['facingThreshold'] == 0.35
    walls = {w['node']: w for w in cutaway['walls']}
    expected = {'south': [0, 0, 1], 'north': [0, 0, -1], 'east': [1, 0, 0], 'west': [-1, 0, 0]}
    for side, outward in expected.items():
        names = [n for n in walls if n.startswith(f'Build_shop_{side}_')]
        assert names and all(walls[n]['outward'] == outward and walls[n]['section'] == 'shop' for n in names)
    # the stairs up cut away with the north wall they stand against; the stairwell down never does
    assert walls['Build_shop_stair0_stair_dark']['outward'] == expected['north']
    assert not any(n.startswith(('Part_', 'Stair_', 'Walk_', 'Door_', 'Decal_')) for n in walls)
    partitions = {p['node'] for p in cutaway['partitions']}
    assert {'Part_shop_0_lime_plaster', 'Part_shop_0_soot_brick'} <= partitions
    assert partitions <= set(built.manifest['collision']['nodeNames'])
    assert 'Stair_upstairs_0_stair_dark' in built.manifest['collision']['nodeNames']
    assert set(cutaway['hideNodes']) == {'Roof_shop_wall_cap', 'Roof_upstairs_wall_cap'}
    # props against a wall carry its outward direction, so they cut away with it
    placed = {item['asset']: item for item in built.T.dressing(built.design['sections'][0])}
    assert placed['crate_stack']['outward'] == expected['east'] and placed['tool_rack']['outward'] == expected['west']
    assert 'outward' not in placed['barrel_stack'] and 'cutawayWall' not in placed['barrel_stack']
    # ... and name the wall node they drop with (InteriorCutaway's cutaway_wall)
    assert placed['crate_stack']['cutawayWall'] == 'Build_shop_east_lime_plaster' in walls
    assert placed['tool_rack']['cutawayWall'] == 'Build_shop_west_soot_brick' in walls


def test_block_boxes_close_their_turned_rectangle(built):
    coarse = built.coarse
    # crate_stack (19.6, 12.0), box 0.9 x 0.9: tiles 18-19 x 11-12 closed, their neighbours open
    assert not coarse[11:13, 18:20].any() and coarse[13, 18] and coarse[11, 17]
    # tool_rack (12.0, 19.5) turned 90: its 1.0 m half length runs north-south
    assert not coarse[18:21, 11:13].any() and coarse[17, 11] and coarse[19, 13]
    # barrel_stack, a 0.7 m circle at (14.5, 20.0)
    assert not coarse[19:21, 14].any()


def test_ways_in_and_out_and_posts_stay_open(built):
    coarse = built.coarse
    for x, y in ([15, 11], [15, 13], [17, 17], [16, 17], [54, 13], [54, 12], [19, 15]):
        assert coarse[y, x], (x, y)
    assert coarse[13:16, 16:19].all()  # the keeper's post and its eight neighbours


@pytest.mark.parametrize('name,change,words', [
    ('a prop on the arrival', lambda d: d['sections'][0]['props'].append(
        {'asset': 'supply_chest', 'at': [15.5, 13.5], 'blockBox': [0.6, 0.4]}), 'arrival'),
    ('a prop on the exit', lambda d: d['sections'][0]['props'].append(
        {'asset': 'supply_chest', 'at': [15.5, 11.5], 'blockBox': [0.6, 0.4]}), 'exit'),
    ('a counter beside the keeper', lambda d: d['sections'][0]['props'].append(
        {'asset': 'supply_chest', 'at': [18.5, 14.5], 'blockBox': [0.4, 0.4]}), 'eight neighbours'),
    ('a keeper on the arrival', lambda d: d['sections'][0]['npcs'][0].update(tile=[15, 13]), 'way in or out'),
    ('a prop in the doorway', lambda d: d['sections'][0]['props'].append(
        {'asset': 'barrel_stack', 'at': [13.5, 16.0], 'block': 0.6}), 'no open tile'),
    ('a screen that strands the stairs', lambda d: d['sections'][0]['props'].append(
        {'asset': 'tool_rack', 'at': [15.75, 19.0], 'blockBox': [0.5, 2.6]}), 'cut off'),
    ('a doorway off the tile centres', lambda d: d['sections'][0]['links'][0][3].__setitem__(0, [13.0, 16.5]),
     'no open tile'),
    ('a stair tile at its foot', lambda d: d['passages'][0]['ends'][0].update(tile=[17, 18], arrival=[16, 18]),
     'blocked'),
    ('a wall prop away from its wall', lambda d: d['sections'][0]['props'].append(
        {'asset': 'supply_chest', 'at': [15.0, 19.5], 'blockBox': [0.3, 0.3], 'wall': 'south'}), 'no outer wall'),
    ('a window in a partition', lambda d: d['sections'][0]['windows'].append(
        {'room': 0, 'side': 'north', 'at': 0.5, 'width': 1.0}), 'outer wall'),
    ('a street door in the wrong wall', lambda d: d['sections'][0]['entrances'][0].update(exitFacing=[1, 0]),
     'outer wall'),
])
def test_the_builder_refuses_a_layout_that_closes_a_way(name, change, words):
    with pytest.raises(SystemExit, match=words):
        protected_or_geometry(change)


def protected_or_geometry(change):
    """Lay the synthetic town out with `change`, then draw it (some refusals come from the geometry)."""
    import build_town_interiors as T
    design = synthetic()
    change(design)
    design = T.annotate(design)
    half, coarse = T.masks(design)
    T.protect(design, coarse)
    previous = T._FRAME['cells']
    T._FRAME['cells'] = design['map']['cells']
    try:
        T.build_geometry(design)
    finally:
        T._FRAME['cells'] = previous


def test_the_manifest_carries_the_sources_ways_lights_and_frame(built):
    manifest = built.manifest
    portals = {p['id']: p for p in manifest['portals']}
    assert portals['shop-exit']['label'] == 'The test street' and portals['shop-exit']['objectId'] == 59201
    assert portals['shop-exit']['destinationTile'] == [5, 4] and portals['shop-exit']['serverTile'] == [15, 11]
    assert portals['shop-passage0-0']['label'] == 'Upstairs' and portals['shop-passage0-0']['destinationTile'] == [54, 12]
    assert portals['upstairs-passage0-1']['label'] == 'On into Test Shop'
    assert any(i['objectId'] == 59251 and i['role'] == 'information' for i in manifest['interactives'])
    assert [c['name'] for c in manifest['chambers']] == ['Test shop', 'Test store room', 'Test home']
    assert manifest['spaces']['Test store room']['z0'] == 120-21.5
    assert manifest['camera']['pitchDegrees'] == -50 and manifest['environment']['dayNight'] == {'enabled': False}
    assert manifest['asset']['interiorClass'] == 'insides' and manifest['asset']['parentRegion'] == 'landfall'
    assert manifest['sectioned'] and [s['id'] for s in manifest['sections']] == ['shop', 'upstairs']
    spawn = {s['id']: s for s in manifest['spawnPoints']}
    assert spawn['shop']['serverTile'] == [15, 13] and spawn['shop']['rotationDegrees'] == 180
    assert spawn['upstairs']['serverTile'] == [54, 12] and spawn['upstairs']['rotationDegrees'] == 0
    assert len(manifest['lighting']['markers']) == 2
    provenance = manifest['provenance']
    assert provenance['builder'] == '_continent_v2/build_town_interiors.py' and provenance['builderSha256'] == sha(BUILDER)
    assert provenance['imports']['_continent_v2/build_underground.py'] == sha(HERE/'build_underground.py')
    assert provenance['sourceSha256'] == sha(built.source)
    assert set(provenance['surfaces']) >= {'oak_planks', 'cobalt_tile', 'lime_plaster', 'soot_brick', 'timber_band'}
    assert manifest['collision']['sha256'] == sha(built.package/'collision.bin')
    assert built.summary['walkableTiles'] == int(built.coarse.sum())
    if SERVER:
        assert manifest['collision']['servedGrid']['sha256'] == sha(built.package/'served-grid.escg.gz')
    else:
        assert 'servedGrid' not in manifest['collision']
