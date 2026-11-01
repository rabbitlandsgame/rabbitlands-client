"""Frozen exterior coal amendment: refuse foreign edits, preserve geometry and resume mixed old/new files.

No builder, renderer or external process is used. The integration fixture uses
the real EWCG/ESCG readers, server movement rule, source readers and publisher
block hashing; fresh shell/scenery ordering deliberately differs from certified.
"""
from array import array
import copy
import json
from pathlib import Path
import shutil
import struct
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
CLIENT = HERE.parents[3]
SERVER = CLIENT.parent / 'rabbitlands-server'
sys.path[:0] = [str(HERE), str(SERVER), str(SERVER / 'tools')]
import publish_interior_resources as tool
import publish_server as publisher
from eloria import served_grid


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, (bytes, bytearray)) else tool.serialise(data, b''))
    return path


def plans():
    base = dict(map=dict(id='landfall_insides', cells=720, alias='LFI', name='Underground'), sections=[
        dict(id='workings', arrival=[20, 21], exit=[20, 22], entrance=dict(object=59002),
             nodes=[[77, 'Coal', 20, 20]], props=[], spawns=[]),
        dict(id='lantern_upper_galleries', arrival=[520, 548], exit=[520, 542], entrance=dict(object=59001),
             nodes=[], props=[], spawns=[])])
    proposed = copy.deepcopy(base)
    proposed['sections'][1]['nodes'] = [[19901, 'Coal', 510, 550], [19902, 'Coal', 511, 551], [19903, 'Coal', 512, 552]]
    proposed['sections'][1]['veins'] = [dict(resource='Coal', nodes=[19901, 19902, 19903])]
    return base, proposed


def scenery(old_sha, new_sha):
    rocks = [dict(asset='veined_crag_4', position=[508.77, -.3, 720-550.19], yaw=67, scale=1.02,
                  outward=[-1., 0, -.014], palette=dict(stone='#77736c', mineral='#e0a64c')),
             dict(asset='veined_crag_4', position=[510.89, -.3, 720-553.71], yaw=204, scale=1.09,
                  outward=[-.546, 0, -.838], palette=dict(stone='#77736c', mineral='#e0a64c'))]
    base = dict(schemaVersion=1, map='landfall_insides', sourcePlanSha256=old_sha, assets={}, surfaces={},
                placements=[dict(asset='old_unrelated', position=[10, 0, 10]), *rocks],
                harvestPresentation={'77': dict(resource='Coal', placement='wall', yaw=0)})
    proposed = copy.deepcopy(base)
    proposed.update(sourcePlanSha256=new_sha, placements=proposed['placements'][:1])
    proposed['harvestPresentation'].update({
        '19901': dict(resource='Coal', placement='wall', variant=0, yaw=83.3, inset=1.009),
        '19902': dict(resource='Coal', placement='wall', variant=1, yaw=42., inset=1.375),
        '19903': dict(resource='Coal', placement='wall', variant=2, yaw=32.3, inset=1.11)})
    current = copy.deepcopy(base)
    current['placements'][0]['position'][0] = 11  # Certified unrelated GEOS ordering/content is retained.
    current['harvestPresentation']['77']['yaw'] = 13
    return base, proposed, current


@pytest.fixture
def certified(tmp_path, monkeypatch):
    checkout, server = tmp_path / 'client', tmp_path / 'server'
    packages = checkout / 'eloria-assets/maps/continent-v2'
    target = packages / 'landfall_insides/client'
    profile = server / 'config/eloria'
    base, proposed = plans()
    base_source = write(tmp_path / 'base-source.json', base)
    proposed_source = write(tmp_path / 'proposed-source.json', proposed)
    write(checkout / tool.U.SOURCE, base_source.read_bytes())
    old_sha, new_sha = tool.sha(base_source.read_bytes()), tool.sha(proposed_source.read_bytes())
    builder = write(checkout / tool.RELATIVE / 'build_underground.py', b'fixture builder identity\n')
    # Real all-four EWCG fold, with each approved closure already inside a blocked coarse tile.
    codes = np.zeros((720, 720), dtype=np.uint16); codes[545:557, 508:524] = 2000
    for _, _, x, y in tool.NODES: codes[y, x] = 0
    half = np.repeat(np.repeat(codes != 0, 2, axis=0), 2, axis=1).astype(np.uint8)
    for x, y in tool.CLOSURES: half[y, x] = 1
    header = struct.pack('<4sHHII', b'EWCG', 2, 0, 1440, 1440)
    collision = header + half.tobytes()
    for x, y in tool.CLOSURES: half[y, x] = 0
    changed_collision = header + half.tobytes()
    grid = served_grid.encode_file(served_grid.ServedGrid(720, 720, array('H', codes.ravel())))
    old_mark = dict(id='workings-77', objectId=77, resource='Coal', serverTile=[20, 20],
                    position=[20.5, 0, 699.5], section='workings', authority='server')
    section_ids = ['workings', 'lantern_upper_galleries', *[f'legacy{i}' for i in range(21)]]
    world = dict(asset=dict(id='landfall_insides', glb='world.glb', bounds=dict(min=[0, 0, 0], max=[720, 1, 720])), harvestables=[old_mark],
                 sectioned=True, sections=[dict(id=sid, bounds=dict(min=[i, 0], max=[i+1, 1])) for i, sid in enumerate(section_ids)],
                 coordinateTransform=dict(metresPerTile=1., serverOrigin=[0, 720], serverCells=[720, 720],
                                          invertServerY=True, serverTileMin=[0, 0]),
                 provenance=dict(source='_continent_v2/content/underground.json', sourceSha256=old_sha,
                                 builder='_continent_v2/build_underground.py', builderSha256=tool.sha(builder.read_bytes())),
                 collision=dict(binary='collision.bin', sha256=tool.sha(collision), gridAlignment='tile-centres-v1',
                                servedGrid=dict(binary='served-grid.escg.gz', format='ESCG-v2', sha256=tool.sha(grid),
                                                unitMetres=.05, climbMetres=1., originMetres=-100., width=720, height=720)),
                 externalResources={'image.png': tool.sha(b'certified image')})
    before, after = copy.deepcopy(world), copy.deepcopy(world)
    after['provenance']['sourceSha256'] = new_sha; after['collision']['sha256'] = tool.sha(changed_collision)
    for oid, res, x, y in proposed['sections'][1]['nodes']:
        after['harvestables'].append(dict(id=f'lantern_upper_galleries-{oid}', objectId=oid, resource=res,
                                         serverTile=[x, y], position=[x+.5, 0, 720-y-.5], section=tool.SECTION, authority='server'))
    base_package, proposed_package = tmp_path / 'base-package', tmp_path / 'proposed-package'
    for package, doc, binary, minimap, glb in ((target, world, collision, b'old minimap', b'certified shell'),
            (base_package, before, collision, b'old minimap', b'genuine reordered shell'),
            (proposed_package, after, changed_collision, b'new minimap', b'genuine reordered shell')):
        for name, value in (('world.json', doc), ('collision.bin', binary), ('served-grid.escg.gz', grid),
                            ('minimap.webp', minimap), ('world.glb', glb), ('image.png', b'certified image')): write(package / name, value)
    monkeypatch.setattr(tool, 'CERTIFIED_GLB_SHA', tool.sha(b'certified shell'))
    generator = 'eloria-assets/tools/render_map_backgrounds.py'
    renderer = write(checkout / generator, b'fixture renderer identity\n')
    world_relative = (target / 'world.json').relative_to(checkout).as_posix()
    sources = {world_relative: tool.sha((target / 'world.json').read_bytes()),
               (target / 'world.glb').relative_to(checkout).as_posix(): tool.sha(b'certified shell'),
               (target / 'image.png').relative_to(checkout).as_posix(): tool.sha(b'certified image')}
    pictures = {}
    for i, sid in enumerate(section_ids):
        picture = write(target / f'map-backgrounds/{sid}.webp', f'certified picture {sid}'.encode())
        pictures[sid] = dict(path='res://../' + picture.relative_to(checkout).as_posix(), worldMin=[i, 0], worldMax=[i+1, 1],
                             imageSize=[1, 1], sha256=tool.sha(picture.read_bytes()))
    backgrounds = dict(schemaVersion=1, generator=generator, rendererInputs={generator: tool.sha(renderer.read_bytes())},
        renderSettings=dict(pixelsPerMetre=4., supersample=1, minimumLongestSide=512, maximumLongestSide=2048,
                            roofPolicy='declared-cutaway-and-named-cave-lids'), aliases={},
        maps={'unrelated': {'keep': True}, tool.REGION: dict(worldMin=[0, 0], worldMax=[720, 720], rendererPolicy='prerendered-map-background-v1',
                                              sectioned=True, sourceInputs=sources, sections=pictures)})
    background_path = write(checkout / 'godot-client/data/maps/map-backgrounds.json', tool.serialise(backgrounds, b'', 1))
    monkeypatch.setattr(tool, 'BACKGROUND_CATALOG_SHA', tool.sha(background_path.read_bytes()))
    base_config, proposed_config, current_config = scenery(old_sha, new_sha)
    base_scenery, proposed_scenery = write(tmp_path / 'base-scenery.json', base_config), write(tmp_path / 'proposed-scenery.json', proposed_config)
    write(checkout / 'godot-client/data/world/underground-scenery.json', current_config)
    metadata = dict(name='Underground', alias='LFI', sourceSha256=old_sha, manifestSha256=tool.sha((target / 'world.json').read_bytes()),
                    collisionSha256=tool.sha(collision), servedGridSha256=tool.sha(grid), sections=[])
    record = dict(maps={}, inputs=dict(contentTables={}, crossingsSha256=tool.sha(b'crossings')),
                  interiors={'landfall_insides': {**metadata, 'rows': dict(nodes=1, spawns=0, interactives=0), 'walkableTiles': int((codes != 0).sum())}},
                  server=dict(overlay={}, stages={}, vendored={'landfall_insides': tool.sha(grid)}, manifestEntriesSha256='unchanged'))
    block = dict(schema=1, tool=publisher.TOOL, stage='m4', overlay=dict(directory='config/eloria/continent-v2', files={}), maps={},
                 interiorMaps={'landfall_insides': metadata}, undergroundRows=dict(nodes=1, spawns=0, interactives=0), undergroundPortals=[],
                 rowCounts=dict(nodes=0), customExtension={'keep': True})
    write(server / 'tools/collision/landfall_insides.escg.gz', grid)
    for index in range(17):
        region = f'outside{index:02d}'
        bake = dict(snapshotSha256=f'bake{index}', sceneSha256=f'scene{index}')
        package = dict(collisionSha256=tool.sha(b'outside collision'), servedGridSha256=tool.sha(b'outside grid'))
        record['maps'][region] = dict(bake=bake, package=package)
        record['server']['vendored'][region] = package['servedGridSha256']; block['maps'][region] = {**bake, **package}
        write(packages / region / 'client/world.json', dict(provenance=bake, collision=dict(sha256=package['collisionSha256'],
              servedGrid=dict(sha256=package['servedGridSha256']))))
        write(packages / region / 'client/collision.bin', b'outside collision')
        write(packages / region / 'client/served-grid.escg.gz', b'outside grid')
        write(server / f'tools/collision/{region}.escg.gz', b'outside grid')
    town = write(checkout / tool.U.TOWN_SOURCE, (CLIENT / tool.U.TOWN_SOURCE).read_bytes())
    town_map = json.loads(town.read_bytes())['map']['id']
    town_world = write(packages / town_map / 'client/world.json', {'town': 'sealed'})
    record['interiors'][town_map] = dict(sourceSha256=tool.sha(town.read_bytes()), manifestSha256=tool.sha(town_world.read_bytes()))
    record['server']['vendored'][town_map] = tool.sha(b'town grid')
    write(packages / town_map / 'client/served-grid.escg.gz', b'town grid'); write(server / f'tools/collision/{town_map}.escg.gz', b'town grid')
    write(checkout / tool.RELATIVE / 'crossings.json', b'crossings')
    write(profile / 'harvesting.txt', b'resource | Coal | 1 | 1 | 2 | -\n')
    harvest = (b'# exterior prefix\r\n' + tool.U.SOURCES[0].banner.encode() + b'\r\n'
               b'node | landfall_insides | 77 | 20 | 20 | Coal\r\n# unrelated suffix\r\n')
    for name, data in (('harvesting.txt', harvest), ('maps.txt', b'outside portals remain\r\n')):
        write(profile / 'continent-v2' / name, data)
        record['server']['overlay'][name] = block['overlay']['files'][name] = tool.sha(data)
    for stage in publisher.STAGES:
        files = ['maps.txt', 'harvesting.txt']
        record['server']['stages'][stage] = dict(files=files, manifestBlockSha256=tool.stage_hash(block, stage, files, record['server']['overlay'], publisher.OWNED_BLOCK_KEYS))
    write(checkout / tool.RELATIVE / 'publication.json', tool.serialise(record, b'', 1))
    write(profile / 'client_content_manifest.json', tool.serialise(dict(maps=[], continentV2=block), b'\r\n'))
    return dict(checkout=checkout, server=server, base_source=base_source, proposed_source=proposed_source,
                base_package=base_package, proposed_package=proposed_package, base_scenery=base_scenery, proposed_scenery=proposed_scenery)


def test_prepare_retains_certified_shell_and_unrelated_scenery_and_updates_all_stage_hashes(certified):
    args = certified; checkout, server = args['checkout'], args['server']
    updates, watched, receipt = tool.prepare(**args)
    assert all(path.read_bytes() == old for path, old in watched.items())
    assert not any(path.name == 'world.glb' or path.name == 'image.png' for path in updates)
    assert len(updates) == 9 and receipt['renderedAcceptance'] == 'pending'
    world_path = checkout / 'eloria-assets/maps/continent-v2/landfall_insides/client/world.json'
    assert json.loads(updates[world_path])['asset'] == json.loads(watched[world_path])['asset']
    background_path = checkout / 'godot-client/data/maps/map-backgrounds.json'
    expected_backgrounds = json.loads(watched[background_path])
    expected_backgrounds['maps'][tool.REGION]['sourceInputs'][world_path.relative_to(checkout).as_posix()] = tool.sha(updates[world_path])
    assert json.loads(updates[background_path]) == expected_backgrounds
    binding = world_path.relative_to(checkout).as_posix()
    old_binding = (json.dumps(binding) + ': ' + json.dumps(tool.sha(watched[world_path]))).encode()
    new_binding = (json.dumps(binding) + ': ' + json.dumps(tool.sha(updates[world_path]))).encode()
    assert updates[background_path] == watched[background_path].replace(old_binding, new_binding, 1)
    assert receipt['backgroundCarryForward']['retainedPictures'] == 23
    assert not any('map-backgrounds/' in str(path) for path in updates)
    scenery_path = checkout / 'godot-client/data/world/underground-scenery.json'
    amended = json.loads(updates[scenery_path])
    assert amended['placements'] == [dict(asset='old_unrelated', position=[11, 0, 10])]
    assert amended['harvestPresentation']['77']['yaw'] == 13
    harvest_path = server / 'config/eloria/continent-v2/harvesting.txt'
    assert updates[harvest_path].startswith(b'# exterior prefix\r\n') and updates[harvest_path].endswith(b'# unrelated suffix\r\n')
    assert updates[harvest_path].count(b'node | landfall_insides | 19901 | 510 | 550 | Coal\r\n') == 1
    record = json.loads(updates[checkout / tool.RELATIVE / 'publication.json'])
    block = json.loads(updates[server / 'config/eloria/client_content_manifest.json'])['continentV2']
    assert block['customExtension'] == {'keep': True} and block['undergroundRows']['nodes'] == 4
    for stage, item in record['server']['stages'].items():
        assert tool.stage_hash(block, stage, item['files'], record['server']['overlay'], publisher.OWNED_BLOCK_KEYS) == item['manifestBlockSha256']
    assert record['server']['manifestEntriesSha256'] == 'unchanged'


@pytest.mark.parametrize('part', ['exterior_grid', 'exterior_provenance', 'door', 'served_grid', 'extra_halfcell', 'unblock_halfcell', 'shell', 'resource', 'scenery', 'crossings',
                                 'background_picture', 'background_source', 'background_renderer', 'background_settings'])
def test_foreign_edits_fail_closed_without_target_writes(certified, part, monkeypatch):
    args = certified; checkout, server = args['checkout'], args['server']
    if part == 'exterior_grid': write(server / 'tools/collision/outside00.escg.gz', b'foreign')
    elif part == 'exterior_provenance':
        path = checkout / 'eloria-assets/maps/continent-v2/outside00/client/world.json'
        value = json.loads(path.read_bytes()); value['provenance']['snapshotSha256'] = 'foreign'; write(path, value)
    elif part == 'door':
        value = json.loads(args['proposed_source'].read_bytes()); value['sections'][1]['entrance']['object'] = 59998
        write(args['proposed_source'], value)
    elif part == 'served_grid': write(args['proposed_package'] / 'served-grid.escg.gz', b'foreign')
    elif part in ('extra_halfcell', 'unblock_halfcell'):
        path = args['proposed_package'] / 'collision.bin'; data = bytearray(path.read_bytes())
        data[16] = 1; write(path, data)
        if part == 'extra_halfcell': data[16] = 0; data[16 + 2*548*1440 + 2*520] = 0; write(path, data)
        world_path = args['proposed_package'] / 'world.json'; value = json.loads(world_path.read_bytes())
        value['collision']['sha256'] = tool.sha(path.read_bytes()); write(world_path, value)
    elif part == 'shell': write(args['proposed_package'] / 'world.glb', b'foreign geometry')
    elif part == 'resource': write(checkout / 'eloria-assets/maps/continent-v2/landfall_insides/client/image.png', b'foreign image')
    elif part == 'crossings': write(checkout / tool.RELATIVE / 'crossings.json', b'foreign crossings')
    elif part == 'background_picture': write(checkout / 'eloria-assets/maps/continent-v2/landfall_insides/client/map-backgrounds/workings.webp', b'foreign picture')
    elif part == 'background_renderer': write(checkout / 'eloria-assets/tools/render_map_backgrounds.py', b'changed renderer')
    elif part in ('background_source', 'background_settings'):
        path = checkout / 'godot-client/data/maps/map-backgrounds.json'; value = json.loads(path.read_bytes())
        if part == 'background_source': value['maps'][tool.REGION]['sourceInputs']['foreign/source'] = tool.sha(b'foreign')
        else: value['renderSettings']['pixelsPerMetre'] = 8.
        write(path, tool.serialise(value, b'', 1)); monkeypatch.setattr(tool, 'BACKGROUND_CATALOG_SHA', tool.sha(path.read_bytes()))
    else:
        value = json.loads(args['proposed_scenery'].read_bytes()); value['placements'].append(dict(asset='foreign'))
        write(args['proposed_scenery'], value)
    source_before = (checkout / tool.U.SOURCE).read_bytes()
    with pytest.raises(ValueError): tool.prepare(**args)
    assert (checkout / tool.U.SOURCE).read_bytes() == source_before


def test_node_body_and_disconnected_approach_use_the_real_shared_rules():
    from eloria.collision import CollisionMap
    codes = np.zeros((12, 12), dtype=np.uint16); codes[1:4, 1:4] = 2000; codes[8:11, 8:11] = 2000
    collision = CollisionMap.from_grid(served_grid.ServedGrid(12, 12, array('H', codes.ravel())))
    reach = tool.U.walk_component(collision, (1, 1), set())
    with pytest.raises(ValueError, match='body is open'): tool.U.checked_node_row('test', 'room', [1, 'Coal', 2, 2], codes, reach, {'Coal'})
    with pytest.raises(ValueError, match='no harvest approach'): tool.U.checked_node_row('test', 'room', [1, 'Coal', 7, 9], codes, reach, {'Coal'})
    assert tool.U.checked_node_row('test', 'room', [1, 'Coal', 4, 2], codes, reach, {'Coal'}).endswith('| 4 | 2 | Coal')


@pytest.mark.parametrize('field', ['bounds', 'sections', 'cutaway', 'externalResources', 'served_grid'])
def test_background_carry_forward_refuses_any_changed_render_manifest_field(certified, field):
    path = certified['checkout'] / 'eloria-assets/maps/continent-v2/landfall_insides/client/world.json'
    before = json.loads(path.read_bytes()); after = copy.deepcopy(before)
    if field == 'bounds': after['asset']['bounds']['min'][0] += 1
    elif field == 'sections': after['sections'][0]['bounds']['max'][0] += 1
    elif field == 'cutaway': after['cutaway'] = {'hideNodes': ['foreign node']}
    elif field == 'externalResources': after['externalResources']['image.png'] = 'foreign'
    else: after['collision']['servedGrid']['sha256'] = 'foreign'
    with pytest.raises(ValueError, match='render fields changed'):
        tool.background_carry_forward(certified['checkout'], before, after, None, None)


def test_duplicate_ids_across_interior_sources_are_refused():
    from types import SimpleNamespace
    old, proposed = plans(); other = copy.deepcopy(old)
    other['map']['id'] = 'another_map'; other['sections'] = [other['sections'][0]]
    other['sections'][0]['nodes'] = [[19901, 'Coal', 20, 20]]; other['sections'][0]['entrance']['object'] = 59250
    loaded = [(SimpleNamespace(source='one'), tool.S, None, proposed), (SimpleNamespace(source='two'), tool.S, None, other)]
    with pytest.raises(ValueError, match='already'): tool.U.check_ids(loaded, SimpleNamespace(nodes=[], interactives=[]), ValueError)


@pytest.mark.parametrize('part', ['old_node', 'props', 'spawns', 'arrival', 'vein', 'duplicate_id'])
def test_source_contract_refuses_any_change_beyond_the_exact_approved_delta(part):
    base, proposed = plans()
    if part == 'old_node': proposed['sections'][0]['nodes'][0][2] += 1
    elif part == 'props': proposed['sections'][1]['props'].append({'asset': 'foreign', 'at': [510, 550]})
    elif part == 'spawns': proposed['sections'][1]['spawns'].append(['goblin', 511, 551, 3])
    elif part == 'arrival': proposed['sections'][1]['arrival'][0] += 1
    elif part == 'vein': proposed['sections'][1]['veins'][0]['nodes'].reverse()
    else: proposed['sections'][1]['nodes'].append([19901, 'Coal', 514, 554])
    with pytest.raises(ValueError): tool.source_delta(base, proposed)


def test_recovery_bundle_resumes_a_partial_apply_and_refuses_foreign_edits(tmp_path, monkeypatch):
    a, b, source = write(tmp_path / 'a', b'old a'), write(tmp_path / 'b', b'old b'), write(tmp_path / 'source', b'fixed')
    updates, watched = {a: b'new a', b: b'new b'}, {a: b'old a', b: b'old b', source: b'fixed'}
    bundle = tmp_path / 'bundle'; tool.save_bundle(bundle, updates, watched)
    assert a.read_bytes() == b'old a' and b.read_bytes() == b'old b'
    a.write_bytes(b'new a')  # Equivalent to a process exit immediately after the first atomic replacement.
    b.write_bytes(b'foreign')
    with pytest.raises(ValueError, match='Foreign target edit'): tool.apply_bundle(bundle)
    assert a.read_bytes() == b'new a' and b.read_bytes() == b'foreign'
    b.write_bytes(b'old b'); tool.apply_bundle(bundle); tool.apply_bundle(bundle)
    assert a.read_bytes() == b'new a' and b.read_bytes() == b'new b'
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Immutable input changed'): tool.apply_bundle(bundle)


def test_bundle_creation_refuses_stale_prepared_inputs(tmp_path):
    path = write(tmp_path / 'target', b'foreign')
    with pytest.raises(ValueError, match='Inputs changed'): tool.save_bundle(tmp_path / 'bundle', {path: b'new'}, {path: b'old'})
    assert not (tmp_path / 'bundle').exists()


def freeze_exteriors(args, directory):
    packages = args['checkout'] / 'eloria-assets/maps/continent-v2'
    for index in range(17):
        for name in ('world.json', 'collision.bin', 'served-grid.escg.gz'):
            source = packages / f'outside{index:02d}/client' / name
            target = directory / f'outside{index:02d}/client' / name
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    shutil.copyfile(args['checkout'] / tool.RELATIVE / 'crossings.json', directory / 'crossings.json')
    return directory


def newer_client_exterior(args):
    package = args['checkout'] / 'eloria-assets/maps/continent-v2/outside00/client'
    world = json.loads((package / 'world.json').read_bytes())
    world['provenance']['snapshotSha256'] = 'newer-client-bake'
    world['collision']['sha256'] = tool.sha(b'newer client collision')
    world['collision']['servedGrid']['sha256'] = tool.sha(b'newer client grid')
    write(package / 'world.json', world); write(package / 'collision.bin', b'newer client collision')
    write(package / 'served-grid.escg.gz', b'newer client grid')
    return package


def test_explicit_frozen_view_validates_old_server_and_retains_newer_client(certified, tmp_path):
    view = freeze_exteriors(certified, tmp_path / 'historical-exteriors')
    live = newer_client_exterior(certified)
    live_crossings = write(certified['checkout'] / tool.RELATIVE / 'crossings.json', b'newer client crossings')
    with pytest.raises(ValueError, match='stale exterior'): tool.prepare(**certified)
    updates, watched, receipt = tool.prepare(**certified, frozen_exteriors=view)
    assert receipt['clientExteriorDrift'] == ['outside00']
    assert 'historical server package view' in receipt['exteriorValidation']
    assert receipt['frozenExteriorFilesSha256'] != receipt['retainedClientExteriorFilesSha256']
    assert receipt['sealedCrossingsSha256'] == tool.sha(b'crossings')
    assert receipt['retainedClientCrossingsSha256'] == tool.sha(b'newer client crossings')
    assert live_crossings in watched and live_crossings not in updates
    assert view / 'crossings.json' in watched
    assert all(live / name not in updates and live / name in watched
               for name in ('world.json', 'collision.bin', 'served-grid.escg.gz'))
    assert all(view / f'outside00/client/{name}' in watched
               for name in ('world.json', 'collision.bin', 'served-grid.escg.gz'))
    bundle = tmp_path / 'historical-bundle'; tool.save_bundle(bundle, updates, watched)
    source = certified['checkout'] / tool.U.SOURCE; before = source.read_bytes()
    write(live / 'collision.bin', b'foreign edit after review')
    with pytest.raises(ValueError, match='Immutable input changed'): tool.apply_bundle(bundle)
    assert source.read_bytes() == before


@pytest.mark.parametrize('part', ['grid', 'crossings'])
def test_frozen_view_cannot_substitute_different_sealed_files(certified, tmp_path, part):
    view = freeze_exteriors(certified, tmp_path / 'historical-exteriors')
    newer_client_exterior(certified)
    path = view / ('outside00/client/served-grid.escg.gz' if part == 'grid' else 'crossings.json')
    write(path, b'not the sealed server file')
    with pytest.raises(ValueError, match='Stale sealed file'): tool.prepare(**certified, frozen_exteriors=view)
