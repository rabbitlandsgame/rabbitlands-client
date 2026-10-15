"""Rows added after the profile freeze are certified, placed and rebuilt like frozen rows."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'tools'))
import export_contracts as E  # noqa: E402
import runtime_content_amendment as R  # noqa: E402
import publish_diagonal_continent as P  # noqa: E402

FROZEN = ('# wildlife\n'
          '# sunmane_steppe\n'
          'spawn | sunmane_steppe | golden_plains_horse | 190 | 94\n'
          'spawn | westhaven | red_fox | 40 | 40\n'
          'spawn | sunmane_steppe | red_fox | 200 | 100\n')
BLOCK = {'id': 'test-herds', 'file': 'spawns.txt', 'region': 'sunmane_steppe',
         'begin': '# --- test herds ---', 'end': '# --- end of the test herds ---',
         'comments': ['# two horses'],
         'rows': [{'fields': ['spawn', 'sunmane_steppe', 'golden_plains_horse', '120', '60'],
                   'marker': 'runtime-spawn-2'},
                  {'fields': ['spawn', 'sunmane_steppe', 'dun_mare', '121', '61', 'tame:3'],
                   'marker': 'runtime-spawn-3'}]}


def document(*blocks):
    return {'schema': R.SCHEMA, 'blocks': [copy.deepcopy(block) for block in blocks], 'sha256': 'x'}


def previous():
    """A certified publication whose frozen frame is offset by (70, 167) for Sunmane."""
    base = {'baselineServerOrigin': [124, 125], 'serverOrigin': [194, 292],
            'translation': [1200.0, 0, 720.0], 'baselineRemovedInteractiveIds': [],
            'baselineContentTransform': {'scale': 1.0, 'sourceCenter': [0, 0], 'targetCenter': [0, 0]},
            'contentPositions': {'spawns': {'0': [260, 261]}}, 'baselineTilePositions': {}}
    return {'regions': {'sunmane_steppe': base}, 'connections': []}


class AmendmentTextTests(unittest.TestCase):
    def test_blocks_follow_the_frozen_text_with_their_own_lines_and_ordinals(self):
        texts = R.amend({'spawns.txt': FROZEN, 'npcs.txt': '', 'harvesting.txt': '',
                         'interactives.txt': ''}, document(BLOCK))
        lines = texts['spawns.txt'].splitlines()
        self.assertEqual(lines[:5], FROZEN.splitlines(), 'frozen rows keep their lines')
        numbers = R.row_lines({'spawns.txt': FROZEN}, document(BLOCK))['test-herds']
        self.assertEqual([lines[n - 1] for n in numbers],
                         ['spawn | sunmane_steppe | golden_plains_horse | 120 | 60',
                          'spawn | sunmane_steppe | dun_mare | 121 | 61 | tame:3'])
        records = E.content_rows(texts, ['sunmane_steppe', 'westhaven'], P)['spawns']['sunmane_steppe']
        self.assertEqual([(r['id'], r['old']) for r in records],
                         [('0', [190, 94]), ('1', [200, 100]), ('2', [120, 60]), ('3', [121, 61])])
        self.assertEqual(records[2]['label'], f'spawns.txt:{numbers[0]}:2')
        with self.assertRaisesRegex(R.AmendmentError, 'already carries'):
            R.amend(texts, document(BLOCK))

    def test_a_block_may_not_reuse_a_frozen_tile_identity_or_marker(self):
        R.validate(document(BLOCK), {'spawns.txt': FROZEN}, P.CONTENT)
        reused = copy.deepcopy(BLOCK)
        reused['rows'][0]['fields'][3:5] = ['200', '100']
        with self.assertRaisesRegex(R.AmendmentError, 'already a sunmane_steppe row'):
            R.validate(document(reused), {'spawns.txt': FROZEN}, P.CONTENT)
        twice = copy.deepcopy(BLOCK)
        twice['rows'][1]['marker'] = twice['rows'][0]['marker']
        with self.assertRaisesRegex(R.AmendmentError, 'its own saved marker'):
            R.validate(document(twice), {'spawns.txt': FROZEN}, P.CONTENT)
        foreign = copy.deepcopy(BLOCK)
        foreign['rows'][0]['fields'][1] = 'westhaven'
        with self.assertRaisesRegex(R.AmendmentError, 'is not a sunmane_steppe row'):
            R.validate(document(foreign), {'spawns.txt': FROZEN}, P.CONTENT)
        loose = copy.deepcopy(BLOCK)
        loose['begin'] = 'test herds'
        with self.assertRaisesRegex(R.AmendmentError, 'comment line'):
            R.validate(document(loose), {'spawns.txt': FROZEN}, P.CONTENT)
        with self.assertRaisesRegex(R.AmendmentError, 'amendable'):
            R.validate(document({**BLOCK, 'file': 'maps.txt'}), {'maps.txt': ''}, P.CONTENT)

    def test_served_rows_follow_the_publication_frame_until_a_marker_pins_them(self):
        specs = R.previous_specs(previous())
        served = R.served_blocks({'spawns.txt': FROZEN}, document(BLOCK), specs, P)['test-herds']
        self.assertEqual(served[2:4], ['spawn | sunmane_steppe | golden_plains_horse | 190 | 227',
                                       'spawn | sunmane_steppe | dun_mare | 191 | 228 | tame:3'])
        pinned = previous()
        pinned['regions']['sunmane_steppe']['contentPositions']['spawns']['3'] = [300, 300]
        served = R.served_blocks({'spawns.txt': FROZEN}, document(BLOCK), R.previous_specs(pinned), P)
        self.assertEqual(served['test-herds'][3], 'spawn | sunmane_steppe | dun_mare | 300 | 300 | tame:3')
        text = R.replace_block('a\nb\n', served['test-herds'], BLOCK['begin'], BLOCK['end'])
        self.assertEqual(text.splitlines()[:2], ['a', 'b'])
        self.assertEqual(R.replace_block(text, ['# --- test herds ---', 'x', '# --- end of the test herds ---'],
                                         BLOCK['begin'], BLOCK['end']),
                         'a\nb\n# --- test herds ---\nx\n# --- end of the test herds ---\n')


class AmendedProfileVerificationTests(unittest.TestCase):
    def _server(self, root, served_block):
        relative = 'config/eloria/spawns.txt'
        baseline, server = root / 'baseline', root / 'server'
        for base in (baseline, server):
            (base / relative).parent.mkdir(parents=True)
        (baseline / relative).write_text(FROZEN, encoding='utf-8')
        for other in ('npcs.txt', 'harvesting.txt', 'interactives.txt'):
            (baseline / 'config/eloria' / other).write_text('', encoding='utf-8')
        specs = R.previous_specs(previous())
        frozen_served, _ = P.rewrite_content(FROZEN, 'spawns.txt', copy.deepcopy(specs), False)
        (server / relative).write_text(frozen_served + '\n'.join(served_block) + '\n', encoding='utf-8')
        return baseline, server, {'files': {relative: 'x'}}

    def test_the_served_block_is_rebuilt_and_any_edit_to_it_is_refused(self):
        amendment = document(BLOCK)
        specs = R.previous_specs(previous())
        block = R.served_blocks({'spawns.txt': FROZEN}, amendment, specs, P)['test-herds']
        shared = types.SimpleNamespace(RULES={})
        with tempfile.TemporaryDirectory() as folder:
            baseline, server, certificate = self._server(Path(folder), block)
            E.verify_current_profile(server, baseline, certificate, previous(), shared, P, amendment)
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, certificate, previous(), shared, P)
            moved = [line.replace('190 | 227', '191 | 227') for line in block]
            baseline, server, certificate = self._server(Path(folder) / 'moved', moved)
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, certificate, previous(), shared, P, amendment)
        with tempfile.TemporaryDirectory() as folder:
            baseline, server, certificate = self._server(Path(folder), [])
            with self.assertRaisesRegex(ValueError, 'beyond the previous coordinated publication'):
                E.verify_current_profile(server, baseline, certificate, previous(), shared, P, amendment)
            with self.assertRaisesRegex(ValueError, 'needs a certified publication'):
                E.verify_current_profile(server, baseline, certificate, None, shared, P, amendment)

    def test_a_block_lands_only_on_the_frozen_file_it_was_written_against(self):
        block = {**BLOCK, 'baseSha256': 'a' * 64}
        certificate = {'files': {'config/eloria/spawns.txt': 'a' * 64}}
        self.assertIsNotNone(R.for_certificate(document(block), certificate))
        self.assertIsNone(R.for_certificate(None, certificate))
        with self.assertRaisesRegex(R.AmendmentError, 'written against'):
            R.for_certificate(document(block), {'files': {'config/eloria/spawns.txt': 'b' * 64}})
        with self.assertRaisesRegex(R.AmendmentError, 'written against'):
            R.for_certificate(document(BLOCK), certificate)

    def test_the_committed_amendment_is_valid_against_the_frozen_profile(self):
        committed = R.load()
        if committed is None:
            self.skipTest('no committed amendment')
        certificate = json.loads((HERE / 'legacy-server-profile/snapshot.json').read_text(encoding='utf-8'))
        R.for_certificate(committed, certificate)
        baseline = HERE / 'legacy-server-profile/config/eloria'
        texts = {name: (baseline / name).read_text(encoding='utf-8') for name in P.CONTENT}
        R.validate(committed, texts, P.CONTENT)
        self.assertEqual(json.loads(R.PATH.read_text(encoding='utf-8'))['schema'], R.SCHEMA)


if __name__ == '__main__':
    unittest.main()
