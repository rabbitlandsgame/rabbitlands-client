"""Daily harvest finishing uses final resource positions; temporary trees only."""
import ast
from pathlib import Path
import tempfile
import unittest

import rebuild_continent_geography as C


class ManymouthDailyHarvestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.server = Path(temporary.name)
        self.nodes = self.server/'config/eloria/harvesting.txt'
        self.nodes.parent.mkdir(parents=True)
        self.nodes.write_bytes(b'node | manymouth_delta | 58 | 142 | 304 | Lotus\r\n'
                               b'node | manymouth_delta | 87 | 215 | 344 | Lotus\r\n')
        self.daily = self.server/'eloria/daily_quests.py'
        self.daily.parent.mkdir()
        self.source = ('# Keep Mara\u2019s quantity, rewards and unrelated task unchanged.\r\n'
                       'TASKS = [DailyTask("Mara Tide","harvest","Lotus",16,"manymouth_delta",151,296,44,250),\r\n'
                       '    DailyTask("Other","harvest","Lotus",9,"manymouth_delta",1,2,3,4)]\r\n').encode('utf-8')
        self.daily.write_bytes(self.source)

    def test_follows_retained_node_58_only_and_is_byte_idempotent(self):
        nodes = self.nodes.read_bytes()
        result = C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))
        expected = self.source.replace(b',151,296,44,250)', b',142,304,44,250)')
        self.assertEqual(self.daily.read_bytes(), expected)
        self.assertEqual(self.nodes.read_bytes(), nodes)
        self.assertEqual(result['resourceId'], 58)
        self.assertEqual(result['position'], [142, 304])
        self.assertTrue(result['changed'])
        self.assertFalse(C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))['changed'])
        self.assertEqual(self.daily.read_bytes(), expected)
        calls = [node for node in ast.walk(ast.parse(expected)) if isinstance(node, ast.Call)]
        self.assertEqual([ast.literal_eval(arg) for arg in calls[0].args],
                         ['Mara Tide', 'harvest', 'Lotus', 16, 'manymouth_delta', 142, 304, 44, 250])

    def test_later_relocation_is_followed_without_remapping_the_task(self):
        C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))
        self.nodes.write_text('node | manymouth_delta | 58 | 146 | 307 | Lotus\n', encoding='utf-8')
        C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))
        self.assertEqual(self.daily.read_bytes(), self.source.replace(b',151,296,44,250)', b',146,307,44,250)'))

    def test_missing_duplicate_or_retyped_resource_rejected_before_write(self):
        for rows in ('', 'node | manymouth_delta | 58 | 142 | 304 | Pearl\n',
                     'node | manymouth_delta | 58 | 142 | 304 | Lotus\n'*2):
            with self.subTest(rows=rows):
                self.nodes.write_text(rows, encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'retained Lotus node 58'):
                    C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))
                self.assertEqual(self.daily.read_bytes(), self.source)

    def test_missing_or_duplicate_task_rejected_before_write(self):
        for source in (b'TASKS = []\n', self.source+self.source):
            with self.subTest(source=source):
                self.daily.write_bytes(source)
                with self.assertRaisesRegex(ValueError, 'exactly one Mara Tide'):
                    C.sync_manymouth_daily_harvest(self.server, ('manymouth_delta',))
                self.assertEqual(self.daily.read_bytes(), source)

    def test_other_regions_do_not_read_or_write_manymouth(self):
        self.assertIsNone(C.sync_manymouth_daily_harvest(self.server/'absent', ('amberwood',)))
        self.assertEqual(self.daily.read_bytes(), self.source)


if __name__ == '__main__':
    unittest.main()
