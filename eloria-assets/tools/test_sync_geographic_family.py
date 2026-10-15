"""Return-trip and repeat-publication regressions using isolated packages."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import sync_geographic_family as F


class FamilyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client, self.server = self.root/'client', self.root/'server'
        self.geo = self.client/'geography.json'
        self.spec = {'nativeServerOrigin': [116, 116], 'nativeServerCells': [384, 384],
                     'serverOrigin': [125, 120], 'serverCells': [402, 402], 'serverTileShift': [9, 4]}
        self.write(self.geo, {'regions': {'sunmane_steppe': self.spec}})
        self.registry = {
            'sunmane_steppe': self.entry('sunmane'),
            'sunmane_wind_caves': self.entry('caves', 'sunmane_steppe'),
            'sunmane_crystal_hollow': {'alias': 'sunmane_wind_caves'},
            'sunmane_gauntlet': self.entry('gauntlet', 'sunmane_steppe'),
            'sunmane_gauntlet_2': {'alias': 'sunmane_gauntlet'},
            'unused_alias': {'alias': 'sunmane_gauntlet'},
            'unrelated': self.entry('unrelated', 'elsewhere')}
        self.write(self.client/'godot-client/data/maps/registry.json', {'maps': self.registry})
        self.maps = self.server/'config/eloria/maps.txt'
        self.maps.parent.mkdir(parents=True)
        self.maps.write_text('\n'.join('map | '+k+' | Name | maps/'+k+'.elm | A'
                                     for k in self.registry if k not in ('unused_alias', 'sunmane_crystal_hollow')),
                             encoding='utf-8')
        exterior = {'asset': {'glb': 'world.glb', 'serverCells': 402},
                    'coordinateTransform': {'serverOrigin': [125, 120], 'metresPerTile': 1, 'invertServerY': True},
                    'continentGeography': {'geographySha256': F.digest(self.geo.read_bytes())},
                    'collision': {'nodeNames': ['main'], 'actorSurfaceGuard': {'closed': 3}},
                    'portals': [{'id': 'cave-wind_caves', 'position': [123, 18, -178.4], 'propPosition': [123, 18, -184]},
                                {'id': 'cave-crystal_hollow', 'position': [203, 19, -161], 'propPosition': [203, 19, -166]}]}
        self.write(self.path('sunmane'), exterior)
        self.room = {'asset': {'glb': 'world.glb'}, 'coordinateTransform': {'serverOrigin': [0, 0]},
                     'sections': [{'id': 'sunmane_wind_caves', 'spawn': 'wind', 'returnMap': 'sunmane_steppe', 'returnTile': [239, 291]}],
                     'portals': [{'id': 'exit-wind', 'section': 'sunmane_wind_caves', 'serverTile': [43, 27],
                                  'destinationMap': 'sunmane_steppe', 'destinationTile': [239, 291]}]}
        self.write(self.path('caves'), self.room)
        self.write(self.path('gauntlet'), {'portals': [{'serverTile': [10, 20],
                    'destinationMap': 'sunmane_steppe', 'destinationTile': [137, 95]}],
                    'sections': [{'exits': [{'map': 'sunmane_steppe', 'tile': [6, 106]}]}]})
        self.write(self.path('unrelated'), {'keep': 'untouched'})

    def entry(self, name, parent=None):
        result = {'manifest': 'res://../eloria-assets/maps/'+name+'/world.json'}
        if parent:
            result['interiorOf'] = parent
        return result

    def path(self, name):
        return self.client/'eloria-assets/maps'/name/'world.json'

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(F.json_bytes(value))

    def sync(self, apply=False):
        return F.sync_family(self.client, self.server, geography=self.geo, apply=apply)

    def test_actual_served_aliases_include_instance_copies_only_once_per_package(self):
        members = F.family(self.client, self.server, ['sunmane_steppe'])
        self.assertEqual(set(members), {'sunmane_steppe', 'sunmane_wind_caves', 'sunmane_gauntlet', 'sunmane_gauntlet_2'})
        self.assertEqual(members['sunmane_gauntlet']['path'], members['sunmane_gauntlet_2']['path'])
        self.assertEqual(self.sync()['uniquePackages'], 3)

    def test_sun_return_uses_physical_mouth_and_current_origin_preserving_room_tile(self):
        self.sync(True)
        room = F.read(self.path('caves'))
        self.assertEqual(room['sections'][0]['returnTile'], [248, 295])
        self.assertEqual(room['portals'][0]['destinationTile'], [248, 295])
        self.assertEqual(room['portals'][0]['serverTile'], [43, 27])
        self.assertEqual(room['coordinateTransform']['serverOrigin'], [0, 0])

    def test_repeat_and_later_origin_preserve_original_authored_point(self):
        self.sync(True)
        self.assertEqual(self.sync(True)['changedFiles'], 0)
        self.spec['serverOrigin'] = [129, 122]
        self.spec['serverTileShift'] = [13, 6]
        self.write(self.geo, {'regions': {'sunmane_steppe': self.spec}})
        exterior = F.read(self.path('sunmane'))
        exterior['coordinateTransform']['serverOrigin'] = [129, 122]
        exterior['continentGeography']['geographySha256'] = F.digest(self.geo.read_bytes())
        self.write(self.path('sunmane'), exterior)
        self.sync(True)
        self.assertEqual(F.read(self.path('gauntlet'))['portals'][0]['destinationTile'], [150, 101])
        self.assertEqual(F.read(self.path('caves'))['portals'][0]['destinationTile'], [252, 297])
        self.assertEqual(self.sync(True)['changedFiles'], 0)

    def test_local_exit_tile_and_unrelated_manifest_and_profile_are_unchanged(self):
        prior = self.maps.read_bytes(), self.path('unrelated').read_bytes()
        self.sync(True)
        self.assertEqual(prior, (self.maps.read_bytes(), self.path('unrelated').read_bytes()))
        room = F.read(self.path('gauntlet'))
        self.assertEqual(room['sections'][0]['exits'][0]['tile'], [6, 106])
        self.assertEqual(room['portals'][0]['serverTile'], [10, 20])
        self.assertEqual(room['portals'][0]['destinationTile'], [146, 99])

    def test_fresh_native_rebuild_is_not_mistaken_for_previous_published_output(self):
        self.sync(True)
        self.write(self.path('caves'), self.room)
        self.sync(True)
        self.assertEqual(F.read(self.path('caves'))['portals'][0]['destinationTile'], [248, 295])

    def test_dry_run_and_wrong_expansion_fail_without_any_write(self):
        paths = list(self.client.rglob('*.json'))
        original = {p: p.read_bytes() for p in paths}
        self.assertEqual(self.sync()['changedFiles'], 2)
        self.assertEqual(original, {p: p.read_bytes() for p in paths})
        exterior = F.read(self.path('sunmane'))
        exterior['coordinateTransform']['serverOrigin'] = [116, 116]
        self.write(self.path('sunmane'), exterior)
        with self.assertRaisesRegex(ValueError, 'origin'):
            self.sync(True)
        self.assertEqual(self.path('caves').read_bytes(), original[self.path('caves')])

    def test_world_targets_stay_world_but_many_compaction_maps_before_padding(self):
        specs = {'four_gates': self.spec, 'manymouth_delta': {'nativeServerOrigin': [138, 120], 'serverOrigin': [177, 120]}}
        migration = {'legacyOrigin': [174, 174], 'nativeOrigin': [138, 120],
                     'axes': {'x': {'old': [-174, 402], 'new': [-138, 342]},
                              'z': {'old': [-402, 174], 'new': [-276, 120]}}}
        manifest = {'portals': [{'targetMap': 'four_gates', 'targetPosition': [-71.85, 31.08, 38]},
                               {'destinationMap': 'manymouth_delta', 'destinationTile': [174, 174]},
                               {'targetMap': 'manymouth_delta', 'targetPosition': [0, 4, 0]}]}
        records = F.restate_returns(manifest, specs, {}, {'manymouth_delta': migration})
        self.assertEqual(manifest['portals'][0]['targetPosition'], [-71.85, 31.08, 38])
        self.assertEqual(manifest['portals'][1]['destinationTile'], [184, 120])
        self.assertEqual(manifest['portals'][2]['targetPosition'], [7.0, 4, .375])
        manifest[F.LEDGER] = {'fields': records}
        prior = copy.deepcopy(manifest)
        F.restate_returns(manifest, specs, {}, {'manymouth_delta': migration})
        self.assertEqual(manifest, prior)

    def test_final_lod_gets_guard_and_served_roster_without_replacing_its_geometry(self):
        main = F.read(self.path('sunmane'))
        main['runtimePopulation'] = {'resources': [{'id': 9, 'serverTile': [250, 100]}]}
        main['npcMarkers'] = [{'id': 'keeper', 'serverTile': [145, 99]}]
        self.write(self.path('sunmane'), main)
        lod = copy.deepcopy(main)
        lod['asset']['glb'] = 'world-lod2.glb'
        lod['collision'] = {'nodeNames': ['LOD_floor'], 'actorSurfaceGuard': {'closed': 0}}
        lod['runtimePopulation'] = {'resources': []}
        lod['navigation'] = {'surfaceNodePrefixes': ['LOD_Walk_']}
        path = self.path('sunmane').with_name('world-lod2.json')
        self.write(path, lod)
        path.with_name('world-lod2.glb').write_bytes(b'LOD geometry')
        result = F.sync_lods(self.client, self.server, geography=self.geo, apply=True)
        self.assertEqual(result['changedFiles'], 1)
        actual = F.read(path)
        self.assertEqual(actual['collision']['nodeNames'], ['LOD_floor'])
        self.assertEqual(actual['navigation'], lod['navigation'])
        self.assertEqual(actual['collision']['actorSurfaceGuard'], {'closed': 3})
        self.assertEqual(actual['runtimePopulation'], main['runtimePopulation'])
        self.assertEqual(actual['npcMarkers'], main['npcMarkers'])
        self.assertEqual(actual['asset']['glb'], 'world-lod2.glb')
        self.assertEqual(F.sync_lods(self.client, self.server, geography=self.geo, apply=True)['changedFiles'], 0)


if __name__ == '__main__':
    unittest.main()
