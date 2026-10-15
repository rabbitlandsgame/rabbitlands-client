"""Publication-order regressions; all writes stay in temporary fixture trees."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import rebuild_continent_geography as C
import rebuild_northern_regions as S


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client, self.server = self.root/'client', self.root/'server'
        self.regions = self.client/'eloria-assets/maps/nymara-regions'
        self.profile = self.server/'config/eloria/client_content_manifest.json'
        self.geography = self.regions/'continent-geography.json'
        write(self.geography, {'regions': {'a': {}, 'b': {}}})
        write(self.profile, {'maps': []})

    def test_later_toolkit_edit_invalidates_an_earlier_completed_region(self):
        source = self.client/'shared.py'
        source.write_text('old geometry recipe\n', encoding='utf-8')
        recorded = hashlib.sha256(source.read_bytes()).hexdigest()
        for region in ('a', 'b'):
            write(self.regions/region/'world.json', {'authoredGeometry': {'inputs': {'shared.py': recorded}}})
        with patch.object(C, 'CLIENT', self.client), patch.object(C, 'REGIONS', self.regions), \
                patch.object(C, 'geometry_sources', return_value=[source]):
            C.validate_geometry_inputs(('a', 'b'))
            # Region a finished before the recipe changed; b now uses the edit.
            source.write_text('new geometry recipe\n', encoding='utf-8')
            write(self.regions/'b/world.json', {'authoredGeometry': {'inputs': {
                'shared.py': hashlib.sha256(source.read_bytes()).hexdigest()}}})
            with self.assertRaisesRegex(ValueError, 'a: geometry input changed after build'):
                C.validate_geometry_inputs(('a', 'b'))

    def test_missing_build_certificate_is_not_treated_as_frozen_geometry(self):
        write(self.regions/'a/world.json', {'asset': {'glb': 'world.glb'}})
        with patch.object(C, 'CLIENT', self.client), patch.object(C, 'REGIONS', self.regions):
            with self.assertRaisesRegex(ValueError, 'no completed geographic build'):
                C.validate_geometry_inputs(('a',))

    def test_first_scoped_prepare_refuses_before_any_global_migration(self):
        original = self.profile.read_bytes()
        with patch.object(C, 'REGIONS', self.regions), patch.object(C, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'requires all twelve'):
                C.prepare(self.server, ('a',))
            run.assert_not_called()
        self.assertEqual(self.profile.read_bytes(), original)

    def test_scoped_repair_requires_exact_previously_published_revision(self):
        with patch.object(C, 'REGIONS', self.regions):
            C.validate_prepare_scope(self.server, ('a', 'b'))
            write(self.profile, {'continentGeography': {'regions': {'a': {}, 'b': {}},
                 'geographySha256': hashlib.sha256(self.geography.read_bytes()).hexdigest()}})
            C.validate_prepare_scope(self.server, ('a',))
            write(self.geography, {'regions': {'a': {'changed': True}, 'b': {}}})
            with self.assertRaisesRegex(ValueError, 'same-revision repair'):
                C.validate_prepare_scope(self.server, ('a',))

    def test_manymouth_reauthors_habitats_without_losing_identities(self):
        profile = self.profile.parent
        (profile/'npcs.txt').write_text('npc | Guide | manymouth_delta | 12 | 13 | actor_type=7\n', encoding='utf-8')
        (profile/'spawns.txt').write_text('spawn | manymouth_delta | crab | 12 | 13\n', encoding='utf-8')
        nodes = profile/'harvesting.txt'
        lotus = 'node | manymouth_delta | 58 | 14 | 15 | Lotus\n'
        nodes.write_text('node | manymouth_delta | 52 | 12 | 13 | Pearl\n'+lotus, encoding='utf-8')
        daily = self.server/'eloria/daily_quests.py'
        daily.parent.mkdir(parents=True)
        daily.write_text('TASKS = [DailyTask("Mara Tide", "harvest", "Lotus", 16, "manymouth_delta", 139, 414, 44, 250)]\n', encoding='utf-8')
        def move(*args, **kwargs):
            self.assertEqual(kwargs['new'], ('manymouth_delta',))
            nodes.write_text('node | manymouth_delta | 52 | 22 | 23 | Pearl\n'+lotus.replace('14 | 15', '142 | 304'), encoding='utf-8')
        with patch.object(C, 'run'), patch.object(C.rooms, 'family_ids', return_value=('manymouth_delta',)), \
                patch.object(C.shared, 'content', side_effect=move):
            C.content(self.server, self.root/'data', ('a', 'manymouth_delta'))
        self.assertIn('"manymouth_delta", 142, 304, 44, 250', daily.read_text(encoding='utf-8'))
        with patch.object(C, 'run'), patch.object(C.rooms, 'family_ids', return_value=('a',)), \
                patch.object(C.shared, 'content') as content:
            C.content(self.server, self.root/'data', ('a',))
            self.assertEqual(content.call_args.kwargs['new'], ())
        def lose(*args, **kwargs):
            nodes.write_text('node | manymouth_delta | 53 | 22 | 23 | Pearl\n'+lotus, encoding='utf-8')
        with patch.object(C, 'run'), patch.object(C.rooms, 'family_ids', return_value=('manymouth_delta',)), \
                patch.object(C.shared, 'content', side_effect=lose):
            with self.assertRaisesRegex(ValueError, 'changed NPC/resource identities'):
                C.content(self.server, self.root/'data', ('manymouth_delta',))

    def publish_environment(self, missing=None, incomplete=None):
        identities = ('a', 'room', 'room_2')
        manifests = {}
        for identity in identities:
            path = self.client/(identity+'.json')
            write(path, {'coordinateTransform': {'serverOrigin': [4, 7]}})
            manifests[identity] = path
        manifests['room_2'] = manifests['room']
        if missing:
            manifests.pop(missing)
        events = []
        packages = ModuleType('sync_package_content')
        packages.registry_packages = lambda: manifests
        def digest(path):
            self.assertIn('final-lod-roster', events)
            events.append('digest:'+path.name)
            return None if incomplete and path == manifests[incomplete] else 'a'*64
        packages.digest_for = digest
        maps = ModuleType('eloria.maps')
        maps.load_maps = lambda _: ({}, [SimpleNamespace(source='room', x=8, y=9, destination='a')])
        eloria = ModuleType('eloria');eloria.__path__ = []
        generation = ModuleType('generate_nymara_maps')
        generation.ARRIVAL_TILES = {identity: (10, 11) for identity in identities}
        generation.MAP_TILES_WIDE_BY_NAME = {identity: 12 for identity in identities}
        modules = {'sync_package_content': packages, 'eloria': eloria, 'eloria.maps': maps,
                   'generate_nymara_maps': generation}
        return identities, events, modules

    def test_approach_reader_publication_is_exact_recorded_and_idempotent(self):
        source = self.client/'eloria-assets/tools/continent_approaches.py'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'"""Pure shared contract."""\r\nVALUE = 3\r\n')
        write(self.profile, {'maps': [{'id': 'retained'}],
                             'continentGeography': {'regions': {'a': {'keep': True}}}})
        with patch.object(C, 'CLIENT', self.client):
            record = C.publish_approach_reader(self.server)
            target = self.server/'tools/continent_approaches.py'
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertEqual(record['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            value = json.loads(self.profile.read_text())
            self.assertEqual(value['maps'], [{'id': 'retained'}])
            self.assertEqual(value['continentGeography']['regions'], {'a': {'keep': True}})
            self.assertEqual(value['continentGeography']['approachReader'], record)
            original, stamp = self.profile.read_bytes(), target.stat().st_mtime_ns
            C.publish_approach_reader(self.server)
            self.assertEqual(self.profile.read_bytes(), original)
            self.assertEqual(target.stat().st_mtime_ns, stamp)
            source.write_bytes(b'VALUE = (\n')
            with self.assertRaises(SyntaxError):
                C.publish_approach_reader(self.server)
            self.assertEqual(self.profile.read_bytes(), original)
            self.assertEqual(target.stat().st_mtime_ns, stamp)

    def test_authored_staff_runs_after_content_relocation(self):
        events = []
        with patch.object(C, 'run', side_effect=lambda *args: events.append(Path(args[1]).name)), \
                patch.object(C.rooms, 'family_ids', return_value=('a',)), \
                patch.object(C.shared, 'content', side_effect=lambda *a, **k: events.append('relocate')), \
                patch.object(C, 'sync_manymouth_daily_harvest', side_effect=lambda *a: events.append('harvest')):
            C.content(self.server, self.root/'data', ('a',))
        self.assertEqual(events, ['author_region_content.py', 'relocate', 'harvest', 'publish_interior_staff.py'])

    def test_composed_manymouth_collision_refreshes_before_server_copy(self):
        for identities, expected in (
                (('manymouth_flooded_labyrinth',), ['export_insides_collision.py', 'server-copy']),
                (('amberwood',), ['server-copy'])):
            events = []
            with self.subTest(family=identities), \
                    patch.object(C.rooms, 'family_ids', return_value=identities), \
                    patch.object(C, 'run', side_effect=lambda *a: events.append(Path(a[1]).name)), \
                    patch.object(C.shared, 'collision', side_effect=lambda *a, **k: events.append('server-copy')):
                C.collision(self.server, self.root/'data', ('a',))
            self.assertEqual(events, expected)

    def test_reader_is_published_before_family_digests(self):
        events = []
        with patch.object(C, 'validate_geometry_inputs'), patch.object(C, 'layout'), \
                patch.object(C, 'run'), patch.object(C.rooms, 'family_ids', return_value=('a',)), \
                patch.object(C, 'publish_approach_reader', side_effect=lambda *a: events.append('reader')), \
                patch.object(C.shared, 'publish', side_effect=lambda *a, **k: events.append('digests')):
            C.publish(self.server, self.root/'artifacts', ('a',))
        self.assertEqual(events, ['reader', 'digests'])

    def test_missing_family_entries_are_added_after_final_lod_and_roster(self):
        identities, events, modules = self.publish_environment()
        write(self.profile, {'maps': [{'id': 'a', 'packageSha256': 'old'}]})
        with patch.dict('sys.modules', modules), patch.object(S, 'run', side_effect=lambda *a:events.append(str(a[1]))), \
                patch.object(S, 'sync_instance_returns', side_effect=lambda *a,**k:events.append('instance-returns')):
            S.publish(self.server, exteriors=('a',), family=identities,
                      before_digests=lambda:events.append('final-lod-roster'))
        entries = {e['id']: e for e in json.loads(self.profile.read_text())['maps']}
        self.assertEqual(set(entries), set(identities))
        self.assertEqual(entries['room']['portals'], [{'server_tile': [8,9], 'destination': 'a'}])
        self.assertEqual(entries['room']['packageSha256'], entries['room_2']['packageSha256'])
        self.assertTrue(all(e['arrival']==[10,11] and e['server_cells']==72 for e in entries.values()))
        self.assertEqual(events[0], 'instance-returns')
        self.assertLess(next(i for i,e in enumerate(events) if e.endswith('publish_northern_content.py')),
                        events.index('final-lod-roster'))
        self.assertTrue(events[-1].endswith('build_exterior_streaming.py'))

    def test_existing_missing_package_or_missing_glb_cannot_leave_a_stale_digest(self):
        for mode in ('missing', 'incomplete'):
            with self.subTest(mode=mode):
                identities, events, modules = self.publish_environment(**{mode: 'a'})
                write(self.profile, {'maps': [{'id':'a','packageSha256':'stale-good-hash'}]})
                original = self.profile.read_bytes()
                with patch.dict('sys.modules', modules), patch.object(S, 'run'), patch.object(S, 'sync_instance_returns'):
                    with self.assertRaisesRegex(ValueError, 'complete|incomplete'):
                        S.publish(self.server, exteriors=('a',), family=identities,
                                  before_digests=lambda:events.append('final-lod-roster'))
                self.assertEqual(self.profile.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
