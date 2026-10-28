"""sync_music_program.py --map: one map's block of the server's music program, every other byte left alone.

The server copy carries music the client source does not (the A3 isles), so a whole sync reverts it; the town's
rooms are refreshed with `--map landfall_town` instead (final review 2026-10-27, finding 7). Run against the server
checkout named by ELORIA_SERVER_ROOT (else rabbitlands-server beside this checkout), on a copy of its file:

    ELORIA_SERVER_ROOT=../rabbitlands-server python -B -m pytest -p no:cacheprovider -q eloria-assets/tools/test_sync_music_program.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import sync_music_program as M

TOWN = 'landfall_town'


def server_root():
    for candidate in (os.environ.get('ELORIA_SERVER_ROOT'), M.CLIENT.parent / 'rabbitlands-server'):
        if candidate and (Path(candidate) / 'config/eloria/music-program.json').is_file():
            return Path(candidate).resolve()
    return None


SERVER = server_root()


class PlacementTests(unittest.TestCase):
    def test_a_block_is_replaced_where_it_stands(self):
        maps = {'a': 1, 'b': 2, 'c': 3}
        self.assertEqual(list(M._placed(maps, 'b', 9, ['a', 'b', 'c']).items()), [('a', 1), ('b', 9), ('c', 3)])

    def test_a_missing_block_follows_the_map_the_source_lists_before_it(self):
        self.assertEqual(list(M._placed({'a': 1, 'x': 0, 'c': 3}, 'b', 9, ['a', 'b', 'c'])),
                         ['a', 'b', 'x', 'c'])
        self.assertEqual(list(M._placed({'x': 0, 'c': 3}, 'a', 9, ['a', 'b', 'c'])), ['a', 'x', 'c'])


@unittest.skipIf(SERVER is None, 'no server checkout: set ELORIA_SERVER_ROOT')
class ServerFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = Path(self.tmp.name) / 'server'
        self.file = self.server / 'config/eloria/music-program.json'
        self.file.parent.mkdir(parents=True)
        shutil.copyfile(SERVER / 'config/eloria/music-program.json', self.file)
        self.original = self.file.read_bytes()
        self.data = json.loads(self.original)

    def rewrite(self, data):
        self.file.write_text(M.render(data), encoding='utf-8', newline='\n')

    def test_the_committed_town_block_is_reproduced_byte_for_byte(self):
        self.assertIn(TOWN, self.data['maps'])
        self.assertEqual(M.sync_maps(self.server, [TOWN], check=True), [])
        self.assertEqual(M.sync_maps(self.server, [TOWN]), [])
        self.assertEqual(self.file.read_bytes(), self.original)
        record = M.map_record(TOWN, M.load_source()['maps'][TOWN], M.registry())
        self.assertEqual(json.dumps(record, ensure_ascii=False), json.dumps(self.data['maps'][TOWN], ensure_ascii=False))
        self.assertGreater(len(record['zones']), 30)

    def test_a_stale_town_block_is_rewritten_and_nothing_else(self):
        stale = json.loads(self.original)
        stale['maps'][TOWN]['zones'] = stale['maps'][TOWN]['zones'][:3]
        stale['maps'][TOWN]['zone_source_sha256'] = '0' * 64
        self.rewrite(stale)
        self.assertEqual(M.sync_maps(self.server, [TOWN], check=True), [TOWN])
        self.assertNotEqual(self.file.read_bytes(), self.original, 'a check writes nothing')
        self.assertEqual(M.sync_maps(self.server, [TOWN]), [TOWN])
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_a_missing_town_block_is_put_back_where_it_stood(self):
        gone = json.loads(self.original)
        del gone['maps'][TOWN]
        self.rewrite(gone)
        self.assertEqual(M.sync_maps(self.server, [TOWN]), [TOWN])
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_server_only_music_survives_a_town_sync(self):
        source = M.load_source()['maps']
        only = [map_id for map_id in self.data['maps'] if map_id not in source]
        self.assertTrue(only, 'the server file has music the client source does not')
        changed = json.loads(self.original)
        changed['maps'][TOWN]['zones'] = []
        self.rewrite(changed)
        M.sync_maps(self.server, [TOWN])
        after = self.file.read_bytes()
        self.assertEqual(after, self.original)
        for map_id in only:
            self.assertEqual(json.loads(after)['maps'][map_id], self.data['maps'][map_id])
        # The whole sync would drop them: why the single-map option exists.
        self.assertTrue(M.sync(self.server, check=True))
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, 'no record'):
            M.sync_maps(self.server, ['no_such_map'])
        unlisted = json.loads(self.original)
        unlisted['programs'] = [name for name in unlisted['programs'] if name != 'castle']
        self.rewrite(unlisted)
        with self.assertRaisesRegex(ValueError, 'castle'):
            M.sync_maps(self.server, [TOWN])
        self.file.write_text(json.dumps(self.data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8',
                             newline='\n')
        with self.assertRaisesRegex(ValueError, 'laid out'):
            M.sync_maps(self.server, [TOWN])

    def test_the_command_line(self):
        tool = Path(M.__file__)
        run = subprocess.run([sys.executable, '-B', str(tool), '--server', str(self.server), '--map', TOWN, '--check'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(f'{TOWN}: current', run.stdout)
        stale = json.loads(self.original)
        stale['maps'][TOWN]['zone_source_sha256'] = '0' * 64
        self.rewrite(stale)
        run = subprocess.run([sys.executable, '-B', str(tool), '--server', str(self.server), '--map', TOWN, '--check'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn(f'{TOWN}: stale', run.stdout)
        run = subprocess.run([sys.executable, '-B', str(tool), '--server', str(self.server), '--map', TOWN],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.file.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
