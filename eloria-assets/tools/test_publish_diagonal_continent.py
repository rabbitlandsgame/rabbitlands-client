"""Named territories receive one shared continent without corrupting contracts."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

import publish_diagonal_continent as P


def specs():
    return {name: {'serverOrigin': [12, 12], 'previousServerOrigin': [6, 6],
        'serverCells': [24, 24], 'arrival': [12, 12], 'translation': [x, 0, 0],
        'terrainRevision': 'diagonal-spine-v1', 'contentTransform': {
            'scale': 1, 'sourceCenter': [0, 0], 'targetCenter': [0, 0]},
        'tilePositions': {}, 'contentPositions': {}}
        for name, x in [('four_gates', 0), ('westhaven', 20)]}


def connections():
    return [{'id': 'trade-road', 'type': 'land', 'ends': [
        {'region': name, 'portal': portal, 'tile': [x, 12], 'arrival': [ax, 12],
         'lanes': [{'tile': [x, y], 'arrival': [ax, y]} for y in range(9, 16)],
         'frame': {'anchor': [anchor, 0, 0], 'outward': [out, 0], 'geometryMode': 'continent-chunks-v1'}}
        for name, portal, x, ax, anchor, out in [('four_gates', 'west', 22, 21, 10, 1),
                                               ('westhaven', 'east', 1, 2, -10, -1)]]}]


class PublicationTests(unittest.TestCase):
    def test_server_placement_contract_retains_original_semantics_on_republication(self):
        regions = specs()
        spec = regions['four_gates']
        spec.update(baselineServerOrigin=[3, 4], baselineTilePositions={'5:6': [14, 15]},
                    baselineContentTransform={'scale': .78, 'sourceCenter': [1, 2], 'targetCenter': [0, 0]},
                    contentPositions={'npcs': {'Bob': [14, 15]}},
                    portalPositions={'door': {'oldTile': [9, 10], 'tile': [17, 18]}})
        spec['tilePositions'] = {'9:10': [14, 15]}
        contract = P.placement_contracts(regions)['four_gates']
        self.assertEqual(contract['baselineServerOrigin'], [3, 4])
        self.assertEqual(contract['baselineTilePositions'], {'5:6': [14, 15]})
        self.assertEqual(contract['contentPositions']['npcs']['Bob'], [14, 15])
        self.assertEqual(contract['portalPositions']['door']['tile'], [17, 18])
        contract['baselineTilePositions']['5:6'][0] = 99
        self.assertEqual(spec['baselineTilePositions']['5:6'], [14, 15])

    def test_scale_uses_cell_centres_and_exact_remaps_win(self):
        spec = specs()['four_gates']
        self.assertEqual(P.transform_tile([7, 8], spec), [13, 14])
        spec['contentTransform']['scale'] = .5
        self.assertEqual(P.transform_tile([7, 8], spec), [12, 13])
        spec['tilePositions']['7:8'] = [4, 5]
        self.assertEqual(P.transform_tile([7, 8], spec), [4, 5])

    def test_a_turned_layout_maps_through_its_exact_affine(self):
        spec = specs()['westhaven']
        # Continent X = .6x - .8z + 25 and Z = .8x + .6z + 3 in absolute metres (a turn, no squeeze); the
        # territory's centre is its translation (20, 0). Cell 7:8 is source (1.5, -2.5): continent (27.9, 2.7),
        # local (7.9, 2.7).
        spec['contentTransform'] = {'scale': None, 'sourceCenter': [0, 0], 'targetCenter': [0, 0],
                                    'affine': [.6, -.8, .8, .6, 25., 3.]}
        self.assertEqual(P.transform_tile([7, 8], spec), [19, 9])
        spec['tilePositions']['7:8'] = [4, 5]
        self.assertEqual(P.transform_tile([7, 8], spec), [4, 5])

    def test_a_transform_without_a_uniform_scale_requires_a_valid_affine(self):
        spec = specs()['westhaven']
        spec['contentTransform'] = {'scale': None, 'sourceCenter': [0, 0], 'targetCenter': [0, 0],
                                    'affine': [.6, -.8, .8, .6, 25., 3.]}
        P.validate_spec('westhaven', copy.deepcopy(spec), None)
        for affine in (None, [.6, -.8, .8, .6, 25.], [.6, -.8, .8, .6, 25., float('nan')],
                       [.6, .8, .8, -.6, 25., 3.], [0, 0, 0, 0, 1., 1.]):
            broken = copy.deepcopy(spec)
            broken['contentTransform']['affine'] = affine
            with self.assertRaisesRegex(ValueError, 'affine'):
                P.validate_spec('westhaven', broken, None)
        del spec['contentTransform']['scale']
        with self.assertRaisesRegex(ValueError, 'positive uniform scale'):
            P.validate_spec('westhaven', spec, None)

    def test_lane_order_does_not_change_global_position(self):
        links = connections()
        links[0]['ends'][1]['lanes'].reverse()
        text, rows = P.connection_rows(links, specs())
        self.assertEqual(len(rows), 14)
        self.assertEqual(text.count('portal |'), 14)
        for source, x, y, dest, ax, ay in rows:
            self.assertEqual(P.world_point(source, [x, y], specs()), P.world_point(dest, [ax, ay], specs()))

    def test_bad_lane_match_and_bounce_fail(self):
        # A crossing hands the walker over at the cell they stand on, so a
        # departure must name a cell of the other map. (The arrival used to be
        # found in the far side's lane list; it is read in the destination's
        # own frame now, so a border open along its length need not have lane
        # for lane the same tiles on both sides.)
        links = connections()
        links[0]['ends'][1]['lanes'][0]['arrival'][0] += 1
        self.assertEqual(len(P.connection_rows(links, specs())[1]), 14)
        links[0]['ends'][0]['lanes'][0]['tile'][0] = 3
        with self.assertRaisesRegex(ValueError, 'stands on no cell of westhaven'):
            P.connection_rows(links, specs())
        links = connections()
        links[0]['ends'][0]['lanes'][0]['tile'] = links[0]['ends'][0]['lanes'][0]['arrival']
        links[0]['ends'][1]['lanes'][0]['arrival'] = links[0]['ends'][1]['lanes'][0]['tile']
        with self.assertRaisesRegex(ValueError, 'immediately triggers'):
            P.connection_rows(links, specs())

    def test_a_border_s_crossings_ship_as_the_fewest_runs(self):
        self.assertEqual(P.crossing_runs([[5, 1], [5, 2], [5, 3], [6, 4], [6, 5], [9, 9]]),
                         {'axis': 'y', 'runs': [[5, 1, 3], [6, 4, 5], [9, 9, 9]]})
        self.assertEqual(P.crossing_runs([[1, 7], [2, 7], [3, 7], [4, 8]]),
                         {'axis': 'x', 'runs': [[7, 1, 3], [8, 4, 4]]})
        graph, stream = P.connection_manifests({'revision': 'diagonal-spine-v1', 'connections': connections()},
                                               {name: {'coordinateTransform': {}} for name in specs()}, specs())
        runs = stream['connections'][0]['ends'][0]['crossingRuns']
        self.assertEqual(runs, {'axis': 'y', 'runs': [[22, 9, 15]]}, 'seven lanes in a column are one run')

    def test_a_roadless_border_is_walked_over_but_is_no_road(self):
        links = connections()
        links[0].update(id='border--four_gates--westhaven', type='walk', road=False)
        emitted, rows = P.connection_rows(links, specs())
        self.assertEqual(len(rows), 14, 'every lane of it is a crossing either way')
        graph, stream = P.connection_manifests({'revision': 'diagonal-spine-v1', 'connections': links},
                                               {name: {'coordinateTransform': {}} for name in specs()}, specs())
        self.assertEqual(graph['connections'], [], 'the graph is roads and boats, which the atlas draws as routes')
        link, = stream['connections']
        self.assertTrue(link['seamless'])
        self.assertIs(link['road'], False)
        self.assertNotIn('visualOnly', link)

    def test_three_ferries_publish_six_distinct_docks_without_becoming_walk_links(self):
        regions = {name: copy.deepcopy(specs()['four_gates']) for name in (
            'crownwater', 'westhaven', 'manymouth_delta', 'ssarathi_ruins')}
        ferries = []
        for index, shore in enumerate(('westhaven', 'manymouth_delta', 'ssarathi_ruins')):
            ferries.append({'id': 'crownwater--' + shore, 'type': 'ferry', 'ends': [
                {'region': 'crownwater', 'portal': 'ferry-to-' + shore,
                 'tile': [20, 5 + index*5], 'arrival': [16, 5 + index*5]},
                {'region': shore, 'portal': 'ferry-to-crownwater', 'tile': [10, 9], 'arrival': [6, 9]}]})
        emitted, rows = P.connection_rows(ferries, regions)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(len(line.split('|')) == 7 for line in emitted.splitlines() if line.startswith('portal')))
        for index, shore in enumerate(('westhaven', 'manymouth_delta', 'ssarathi_ruins')):
            self.assertIn(('crownwater', 20, 5 + index*5, shore, 6, 9), rows)
            self.assertIn((shore, 10, 9, 'crownwater', 16, 5 + index*5), rows)
        graph, stream = P.connection_manifests({'revision': 'diagonal-spine-v1', 'connections': ferries}, {}, regions)
        self.assertEqual(len(graph['connections']), 3)
        self.assertEqual(stream['connections'], [])
        ferries[1]['ends'][0]['tile'] = list(ferries[0]['ends'][0]['tile'])
        with self.assertRaisesRegex(ValueError, 'duplicate exterior departure'):
            P.connection_rows(ferries, regions)

    def test_explicit_spawn_ordinal_preserves_species_and_order(self):
        regions = specs()
        regions['four_gates']['contentPositions']['spawns'] = {'1': [18, 19]}
        text = 'spawn | four_gates | otter | 7 | 8\nspawn | four_gates | otter | 8 | 8\n'
        moved, count = P.rewrite_content(text, 'spawns.txt', regions, False)
        self.assertEqual(moved, 'spawn | four_gates | otter | 13 | 14\nspawn | four_gates | otter | 18 | 19\n')
        self.assertEqual(count, {'four_gates': 2})
        self.assertNotIn('8:8', regions['four_gates']['tilePositions'])

    def test_two_qualified_harvest_records_can_move_from_one_served_tile_independently(self):
        text = ('node | four_gates | 69 | 7 | 8 | Riverflax\n'
                'node | four_gates | 70 | 7 | 8 | Riverflax\n')
        regions = specs(); spec = regions['four_gates']
        spec['tilePositions']['7:8'] = [13, 14]
        spec['contentPositions']['harvest'] = {'69': [13, 14], '70': [13, 13]}
        spec['runtimeBindings'] = {
            identity: {'role': 'harvest', 'source': {
                'path': 'config/eloria/harvesting.txt', 'line': line,
                'recordId': record, 'oldTile': [7, 8]}}
            for identity, line, record in (('first', 1, '69'), ('second', 2, '70'))}
        spec['runtimeBindingPositions'] = {'first': [13, 14], 'second': [13, 13]}
        spec['runtimeBindingSourceTiles'] = {'first': [7, 8], 'second': [7, 8]}
        moved, counts = P.rewrite_content(text, 'harvesting.txt', regions, False)
        self.assertEqual(moved, ('node | four_gates | 69 | 13 | 14 | Riverflax\n'
                                 'node | four_gates | 70 | 13 | 13 | Riverflax\n'))
        self.assertEqual(counts, {'four_gates': 2})
        self.assertEqual(spec['tilePositions']['7:8'], [13, 14])
        # The next contract run reconstructs served text from the same frozen
        # source and hash-addressed publication before doing another rewrite.
        reconstructed, _ = P.rewrite_content(text, 'harvesting.txt', copy.deepcopy(regions), False)
        self.assertEqual(reconstructed, moved)
        repeated, _ = P.rewrite_content(moved, 'harvesting.txt', regions, True)
        self.assertEqual(repeated, moved)
        for drift in ('missing', 'wrong-line', 'wrong-destination', 'wrong-source-tile'):
            bad = copy.deepcopy(regions)
            if drift == 'missing':
                del bad['four_gates']['runtimeBindings']['second']
            elif drift == 'wrong-line':
                bad['four_gates']['runtimeBindings']['second']['source']['line'] = 3
            elif drift == 'wrong-source-tile':
                bad['four_gates']['runtimeBindings']['second']['source']['oldTile'] = [6, 8]
            else:
                bad['four_gates']['runtimeBindingPositions']['second'] = [12, 13]
            with self.assertRaisesRegex(ValueError, 'conflicting authored destinations'):
                P.rewrite_content(text, 'harvesting.txt', bad, False)
        served = copy.deepcopy(regions)
        served['four_gates']['runtimeBindings']['first']['source']['oldTile'] = [2, 3]
        served['four_gates']['runtimeBindings']['second']['source']['oldTile'] = [2, 3]
        served['four_gates']['runtimeBindingSourceTiles'] = {'first': [2, 3], 'second': [2, 3]}
        served['four_gates']['baselineTilePositions'] = {'2:3': [7, 8]}
        self.assertEqual(P.rewrite_content(text, 'harvesting.txt', served, False)[0], moved)

    def test_unique_saved_content_id_supersedes_only_an_identity_mapping(self):
        text = 'four_gates | 500 | 7 | 8 | secret | key:Resin | shrine\n'
        regions = specs(); spec = regions['four_gates']
        spec['tilePositions']['7:8'] = [7, 8]
        spec['contentPositions']['interactives'] = {'500': [9, 8]}
        moved, counts = P.rewrite_content(text, 'interactives.txt', regions, False)
        self.assertIn('500 | 9 | 8 | secret', moved)
        self.assertEqual(counts, {'four_gates': 1})
        self.assertEqual(spec['tilePositions']['7:8'], [7, 8])
        unrelated = 'node | four_gates | 70 | 7 | 8 | Riverflax\n'
        all_counts = P.content_source_tile_counts({
            'interactives.txt': text, 'harvesting.txt': unrelated})
        blocked = specs(); blocked['four_gates']['tilePositions']['7:8'] = [7, 8]
        blocked['four_gates']['contentPositions']['interactives'] = {'500': [9, 8]}
        with self.assertRaisesRegex(ValueError, 'conflicting authored destinations'):
            P.rewrite_content(text, 'interactives.txt', blocked, False, all_counts)
        blocked['four_gates']['tilePositions']['7:8'] = [8, 8]
        moved, _ = P.rewrite_content(text, 'interactives.txt', blocked, False)
        self.assertIn('500 | 9 | 8 | secret', moved)
        self.assertEqual(blocked['four_gates']['tilePositions']['7:8'], [8, 8])
        mapper = {'four_gates': {'delta': [0, 0], '_native_mapper':
                  lambda tile: P.transform_tile(tile, blocked['four_gates'])}}
        portal = 'portal | four_gates | 7 | 8 | room | 9 | 10\n'
        self.assertIn('four_gates | 8 | 8 | room',
            P.shared.rewrite_profile(portal, P.shared.RULES['maps.txt'], mapper)[0])
        definition = 'map_id: maps/four_gates.elm\ntype: otter\nx_pos: 7\ny_pos: 8\n'
        self.assertIn('x_pos: 8\ny_pos: 8', P.shared.rewrite_definition(definition, mapper)[0])

    def test_only_declared_obsolete_portal_posts_can_be_removed(self):
        regions = specs()
        regions['four_gates']['removedInteractiveIds'] = ['20']
        regions['four_gates']['contentPositions']['interactives'] = {'20': [18, 19]}
        text = 'four_gates | 20 | 7 | 8 | portal | maps.txt | Old road\n'
        moved, _ = P.rewrite_content(text, 'interactives.txt', regions, False)
        self.assertEqual(moved, '')
        moved, _ = P.rewrite_content(moved, 'interactives.txt', regions, True)
        self.assertEqual(moved, '')
        with self.assertRaisesRegex(ValueError, 'only obsolete generic portal'):
            P.rewrite_content(text.replace('portal | maps.txt', 'storage | shared'), 'interactives.txt', regions, False)

    def test_mistyped_explicit_identity_does_not_silently_fall_back(self):
        regions = specs()
        regions['four_gates']['contentPositions']['npcs'] = {'Bbo': [18, 19]}
        with self.assertRaisesRegex(ValueError, 'identities absent from the source profile'):
            P.rewrite_content('npc | Bob | four_gates | 7 | 8 | dialogue\n', 'npcs.txt', regions, False)

    def test_replacement_keeps_doors_and_unrelated_connections(self):
        text = ('portal | four_gates | 1 | 2 | westhaven | 3 | 4\n'
                'portal | four_gates | 500 | 7 | 8 | room | 2 | 3\n'
                'portal | room | 2 | 3 | four_gates | 6 | 7\n'
                'portal | emberhaven | 1 | 2 | underworld | 3 | 4\n')
        moved, _ = P.replace_crossings(text, connections(), specs())
        self.assertNotIn('four_gates | 1 | 2 | westhaven', moved)
        self.assertIn('four_gates | 500 | 7 | 8 | room', moved)
        self.assertIn('room | 2 | 3 | four_gates | 6 | 7', moved)
        self.assertIn('emberhaven | 1 | 2 | underworld', moved)
        again, _ = P.replace_crossings(moved, connections(), specs())
        self.assertEqual(moved, again)

    def test_collision_rejects_one_blocked_half_metre_sample(self):
        regions = specs()
        blob = struct.pack('<4sHHII', b'EWCG', 2, 0, 48, 48) + bytes([10]) * (48 * 48)
        blobs = {name: blob for name in regions}
        self.assertEqual(P.validate_standing_points(regions, blobs, {}, []), 2)
        damaged = bytearray(blob)
        damaged[16 + 24 * 48 + 25] = 0
        blobs['four_gates'] = damaged
        with self.assertRaisesRegex(ValueError, 'blocked by the authored collision'):
            P.validate_standing_points(regions, blobs, {}, [])

    def fixture(self, root):
        client, server = root / 'client', root / 'server'
        def put(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value)).encode())
        pub_path = client / 'eloria-assets/maps/nymara-regions/_continent/publication.json'
        master = pub_path.parent / 'continent.glb'
        put(master, b'test-master-bytes')
        publication = {'schema': 1, 'revision': 'diagonal-spine-v1', 'masterPath': 'continent.glb',
                       'masterSha256': P.shared.digest(master.read_bytes()), 'regions': specs(), 'connections': connections()}
        registry = {'maps': {}}
        for name, spec in publication['regions'].items():
            base = client / f'eloria-assets/maps/{name}'
            put(base / 'world.json', {'coordinateTransform': {'serverOrigin': [12, 12], 'serverCells': [24, 24]},
                                     'collision': {'authoredSurfaceExport': True, 'gridAlignment': 'tile-centres-v1'}})
            put(base / 'collision.bin', struct.pack('<4sHHII', b'EWCG', 2, 0, 48, 48) + bytes([10]) * (48 * 48))
            spec.update(worldManifestPath=str(base / 'world.json'), collisionPath=str(base / 'collision.bin'))
            registry['maps'][name] = {'manifest': f'res://../eloria-assets/maps/{name}/world.json'}
        registry['maps']['room'] = {'manifest': 'res://../eloria-assets/maps/room/world.json', 'interiorOf': 'four_gates'}
        put(client / 'eloria-assets/maps/room/world.json', {'arrival': [2, 3], 'exit': {
            'serverTile': [2, 3], 'destinationMap': 'four_gates', 'destinationTile': [7, 8]}})
        put(client / 'godot-client/data/maps/registry.json', registry)
        put(pub_path, publication)
        profile = server / 'config/eloria'
        put(profile / 'client_content_manifest.json', {'maps': [{'id': name, 'arrival': [6, 6], 'server_cells': 12}
            for name in ('four_gates', 'westhaven', 'room')], 'continentGeography': {'regions': {
                name: {'serverOrigin': [6, 6], 'nativeServerOrigin': [6, 6]} for name in specs()}}})
        for filename in P.shared.RULES:
            put(profile / filename, '')
        put(profile / 'npcs.txt', 'npc | Bob | four_gates | 7 | 8 | dialogue | Keep the prose\n')
        put(profile / 'maps.txt', 'map | four_gates | Four Gates | maps/four_gates.elm | FG\n'
            'map | westhaven | Westhaven | maps/westhaven.elm | WH\nmap | room | Room | maps/room.elm | RM\n'
            'portal | room | 2 | 3 | four_gates | 7 | 8\nportal | four_gates | 7 | 9 | room | 2 | 3\n')
        put(server / 'tools/generate_nymara_maps.py', 'FOUR_GATES_TILES_WIDE=2\nMAP_TILES_WIDE_BY_NAME={"four_gates":2,"westhaven":2}\nARRIVAL_TILES={"four_gates":(6,6),"westhaven":(6,6)}\n')
        put(server / 'eloria/map_layout.py', 'FOUR_GATES_ARRIVAL=(6,6)\nCOASTAL_ARRIVALS={"four_gates":FOUR_GATES_ARRIVAL,"westhaven":(6,6)}\nSOUTHERN_ARRIVALS={}\n')
        put(server / 'eloria/world.py', 'TUTORIAL_ROUTE_MARKERS=((7,8),(8,9))\nTUTORIAL_HARVESTS=(("Reed",7,8,9),)\n')
        put(server / 'eloria/walkthrough.py', 'PLAZA=(6,6)\n')
        put(server / 'eloria/daily_quests.py', 'TASKS=(DailyTask("Sage","harvest","Seed",18,"four_gates",7,8,38,220),)\n')
        put(server / 'eloria/pk.py', 'ZONES=(PKZone("four_gates",1,2,5,6,40,True),)\n')
        put(server / 'eloria/database.py', 'class Database:\n    def migrate(self):\n        migration = "coastal_landscapes_396_v1"\n')
        return client, server, pub_path

    def test_plan_is_read_only_and_apply_is_repeatable_preserving_room_local_tiles(self):
        with tempfile.TemporaryDirectory() as folder:
            client, server, publication = self.fixture(Path(folder))
            npc = server / 'config/eloria/npcs.txt'
            original = npc.read_bytes()
            before, pending, report = P.plan(client, server, publication)
            self.assertEqual(npc.read_bytes(), original)
            self.assertEqual(report['exteriorPortalLanes'], 14)
            self.assertIn(b'13 | 14 | dialogue | Keep the prose', pending[npc])
            manifest = json.loads(pending[server / 'config/eloria/client_content_manifest.json'])
            self.assertEqual(manifest['diagonalContinent']['placements']['four_gates']['baselineTilePositions']['7:8'], [13, 14])
            P.shared.apply_plan(before, pending)
            room = P.read_json(client / 'eloria-assets/maps/room/world.json')
            self.assertEqual(room['arrival'], [2, 3])
            self.assertEqual(room['exit']['serverTile'], [2, 3])
            self.assertEqual(room['exit']['destinationTile'], [13, 14])
            before, pending, report = P.plan(client, server, publication)
            self.assertTrue(report['repeatedPublication'])
            self.assertEqual(pending, {})

    def test_changed_publication_requires_explicit_current_source(self):
        with tempfile.TemporaryDirectory() as folder:
            client, server, path = self.fixture(Path(folder))
            before, pending, _ = P.plan(client, server, path)
            P.shared.apply_plan(before, pending)
            data = P.read_json(path)
            data['revision'] = 'diagonal-spine-v2'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'sourcePublicationSha256'):
                P.plan(client, server, path)




class InstanceExitRecordTests(unittest.TestCase):
    relative = 'config/eloria/instances/example.def'

    def definition(self, tile=(4, 5), name='arena'):
        return ('[instance]\nspawn_name: ' + name + '\nmap_id: interior\nentry_x: 9\nentry_y: 8\n'
                'exit_map: four_gates\nexit_x: %d\nexit_y: %d\n' % tuple(tile))

    def fixture(self):
        regions = specs()
        identity, source = next(iter(P.instance_exit_records(self.relative, self.definition(), regions).items()))
        source['sha256'] = 'a' * 64
        entry = {'source': source, 'previousTile': [10, 11], 'expectedTile': [16., 17.],
                 'tile': [16, 17], 'maximumDisplacementMetres': 5,
                 'postContent': {'standing': True, 'hubAccessible': True, 'noPortalTrigger': True}}
        for spec in regions.values():
            spec['instanceExitPositions'] = {}
        regions['four_gates']['instanceExitPositions'][identity] = entry
        mappings = {r: {'delta': [99, 99]} for r in regions}
        return regions, identity, entry, mappings

    def test_two_successive_publications_and_repeat_keep_record_separate_from_portals(self):
        regions, identity, entry, mappings = self.fixture()
        regions['four_gates']['tilePositions']['4:5'] = [1, 2]
        regions['four_gates']['portalPositions'] = {'a': {'tile': [1, 2]}, 'b': {'tile': [2, 3]}}
        entries = P.validate_instance_exit_table(regions, {identity: entry['source']})
        first, _ = P.rewrite_instance_exits(self.relative, self.definition((10, 11)), mappings, entries, mode='served')
        self.assertEqual(P.instance_exit_records(self.relative, first, regions)[identity]['originalTile'], [16, 17])
        repeat, _ = P.rewrite_instance_exits(self.relative, first, mappings, entries, mode='repeated')
        self.assertEqual(first, repeat)
        next_entry = copy.deepcopy(entry); next_entry.update(previousTile=[16, 17], tile=[17, 17])
        second, _ = P.rewrite_instance_exits(self.relative, first, mappings, {identity: next_entry}, mode='served')
        reconstructed, _ = P.rewrite_instance_exits(self.relative, self.definition(), mappings, {identity: next_entry}, mode='source')
        self.assertEqual(second, reconstructed)
        self.assertEqual(regions['four_gates']['tilePositions'], {'4:5': [1, 2]})
        self.assertEqual(regions['four_gates']['portalPositions']['b']['tile'], [2, 3])
        self.assertEqual(P.placement_contracts(regions)['four_gates']['instanceExitPositions'][identity], entry)

    def test_manual_edit_missing_duplicate_or_renamed_context_is_rejected(self):
        regions, identity, entry, mappings = self.fixture()
        for text in (self.definition((10, 12)), '', self.definition((10, 11))*2,
                     self.definition((10, 11), 'other'), self.definition((10, 11)).replace('spawn_name:', 'id:')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                P.rewrite_instance_exits(self.relative, text, mappings, {identity: entry}, mode='served')
        for mutate in ('missing', 'wrong-source', 'over-budget', 'no-access'):
            altered = copy.deepcopy(regions)
            target = altered['four_gates']['instanceExitPositions']
            if mutate == 'missing': target.clear()
            elif mutate == 'wrong-source': target[identity]['source']['originalTile'] = [5, 5]
            elif mutate == 'over-budget': target[identity]['tile'] = [23, 23]
            else: target[identity].pop('postContent')
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                P.validate_instance_exit_table(altered, {identity: entry['source']})

    def test_staged_exit_is_checked_for_standing_and_actual_portal_trigger(self):
        regions, identity, entry, _ = self.fixture()
        blobs = {r: struct.pack('<4sHHII', b'EWCG', 2, 0, 48, 48) + bytes([20])*48*48 for r in regions}
        self.assertEqual(P.validate_standing_points(regions, blobs, {}, [], {identity: entry}), 3)
        with self.assertRaisesRegex(ValueError, 'immediately triggers'):
            P.validate_standing_points(regions, blobs, {'maps.txt': 'portal|four_gates|16|17|room|1|2'}, [], {identity: entry})
        raw = bytearray(blobs['four_gates']); raw[16 + 34*48 + 32] = 0; blobs['four_gates'] = bytes(raw)
        with self.assertRaisesRegex(ValueError, 'blocked'):
            P.validate_standing_points(regions, blobs, {}, [], {identity: entry})




class AuthoredInstancePlanTests(unittest.TestCase):
    fixture = PublicationTests.fixture
    def test_authored_instance_and_portal_bindings_plan_repeat_and_successor(self):
        with tempfile.TemporaryDirectory() as folder:
            client, server, path = self.fixture(Path(folder))
            publication = P.read_json(path); publication['instanceExitSchema'] = 2
            baseline = client/'eloria-assets/maps/nymara-regions/_continent/legacy-server-profile'
            relative = 'config/eloria/instances/arena.def'
            definition = '[instance]\nspawn_name: arena\nmap_id: room\nexit_map: four_gates\nexit_x: 7\nexit_y: 8\n'
            target = server/relative; target.parent.mkdir(parents=True); target.write_text(definition)
            original = baseline/relative; original.parent.mkdir(parents=True); original.write_text(definition)
            maps = (server/'config/eloria/maps.txt').read_bytes()
            (baseline/'config/eloria/maps.txt').write_bytes(maps)
            digest = P.shared.digest(original.read_bytes())
            (baseline/'snapshot.json').write_text(json.dumps({'files': {relative:digest}}))
            identity, source = next(iter(P.instance_exit_records(relative, definition, publication['regions']).items()))
            source['sha256'] = digest
            marker = {'section':'runtimePoints','id':'independent-return'}
            report_source = {'path':relative,'recordId':'arena','line':5,'fields':['exit_x','exit_y'],'oldTile':[7,8],'sha256':digest}
            report = {'schema':'eloria-instance-exit-binding-amendment-v1','records':[
                {'id':identity,'region':'four_gates','source':report_source,'marker':marker}]}
            amendment = client/'amendment.json'; amendment.write_text(json.dumps(report))
            bound_source = {k:v for k,v in report_source.items() if k!='sha256'}
            bound_source['amendmentReport'] = {'path':'amendment.json','sha256':P.shared.digest(amendment.read_bytes())}
            binding = {'id':identity,'source':bound_source,'marker':marker,'role':'return','roads':'marker',
                       'targetOffset':[0,0,0],'aliases':[],'provenance':{'sourceProfileSha256':digest}}
            portal = {'id':'room-return','role':'return','source':{'path':'config/eloria/maps.txt','line':4,'oldTile':[7,8]},
                      'provenance':{'sourceProfileSha256':P.shared.digest(maps)}}
            for spec in publication['regions'].values(): spec['instanceExitPositions'] = {}
            spec = publication['regions']['four_gates']
            spec['runtimeBindings'] = {identity:binding,'room-return':portal}
            spec['runtimeBindingPositions'] = {identity:[16,17],'room-return':[14,14]}
            spec['runtimeBindingSourceTiles'] = {identity:[7,8],'room-return':[7,8]}
            spec['portalPositions'] = {'room-return':{'oldTile':[7,8],'tile':[14,14],'runtimeBindingId':'room-return'}}
            entry = {'source':source,'previousTile':[7,8],'expectedTile':[16.,17.],'tile':[16,17],
                     'maximumDisplacementMetres':5,'postContent':{'standing':True,'hubAccessible':True,'noPortalTrigger':True},
                     'authoredBinding':binding,'expectedSource':{'bindingId':identity,'region':'four_gates','marker':marker,
                          'globalPosition':[4.5,10.,-5.5],'serverOrigin':[12,12],'translation':[0,0,0]}}
            spec['instanceExitPositions'][identity] = entry
            path.write_text(json.dumps(publication))
            before,pending,first = P.plan(client,server,path)
            self.assertEqual(target.read_text(),definition)
            self.assertIn(b'exit_x: 16\nexit_y: 17',pending[target].replace(b'\r\n',b'\n'))
            self.assertIn(b'room|2|3|four_gates|14|14',pending[server/'config/eloria/maps.txt'].replace(b' ',b''))
            self.assertEqual(first['instanceExits'][identity]['tile'],[16,17])
            P.shared.apply_plan(before,pending)
            self.assertEqual(P.plan(client,server,path)[1],{})
            # The next publication starts from each actual qualified record.
            publication['sourcePublicationSha256'] = first['publicationSha256']
            for item in publication['regions'].values():
                item['previousServerOrigin'] = item['serverOrigin']
                item['contentTransform'] = {'scale':1,'sourceCenter':[0,0],'targetCenter':[0,0]}
                item['tilePositions'] = {}
            entry.update(previousTile=[16,17],tile=[17,17],expectedTile=[17.,17.])
            entry['expectedSource']['globalPosition'][0] = 5.5
            spec['runtimeBindingPositions'].update({identity:[17,17],'room-return':[15,14]})
            spec['portalPositions']['room-return'].update(oldTile=[14,14],tile=[15,14])
            path.write_text(json.dumps(publication))
            before,pending,second = P.plan(client,server,path)
            self.assertIn(b'exit_x: 17\nexit_y: 17',pending[target].replace(b'\r\n',b'\n'))
            P.shared.apply_plan(before,pending)
            self.assertEqual(P.plan(client,server,path)[1],{})
            current_maps=(server/'config/eloria/maps.txt').read_text()
            self.assertIn('room|2|3|four_gates|15|14',current_maps.replace(' ',''))
            target.write_text(target.read_text().replace('exit_x: 17','exit_x: 18'))
            with self.assertRaisesRegex(ValueError,'certified repeated'):
                P.plan(client,server,path)

    def test_authored_table_checks_report_inventory_and_saved_point_provenance(self):
        regions, identity, entry, _ = InstanceExitRecordTests().fixture()
        # The authored format cannot silently accept an old unbound table.
        with self.assertRaises(ValueError):
            P.validate_instance_exit_table(regions,{identity:entry['source']},require_authored=True)

if __name__ == '__main__':
    unittest.main()
