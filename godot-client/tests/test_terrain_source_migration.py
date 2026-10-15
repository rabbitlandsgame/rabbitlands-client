"""Global identity, ownership masks and interrupted source transactions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import terrain_source_migration as M


class TerrainMigrationTests(unittest.TestCase):
    def test_negative_origin_and_shifted_row_stride_preserve_float_bits(self):
        old = M.global_window((-8, -6), (4, 2), (3, 2))
        new = M.Window(-3, -3, 6, 5); field = M.Window(-4, -4, 8, 8)
        raw = np.array([0x80000000, 0x7fc00001, 0x3f800000, 0x00000001, 5, 6], '<u4').tobytes()
        seed = np.arange(64, dtype='<u4').tobytes()
        result = M.remap_grid_by_global_id(raw, old, new, seed, field)
        self.assertEqual(M.preserved_old_bytes(result, old, new), raw)
        array = np.frombuffer(result, '<u4').reshape(new.shape)
        self.assertEqual(array[0, 0], 9)
        self.assertEqual(array[-1, -1], 46)

    def test_required_ring_is_not_rectangle_overlap(self):
        owner = np.ones((5, 5), dtype=int); owner[2, 2] = 0
        required = M.required_vertices(owner, 0)
        expected = np.zeros((6, 6), bool); expected[1:5, 1:5] = True
        np.testing.assert_array_equal(required, expected)
        with self.assertRaises(ValueError):
            M.validate_required_coverage(required, M.Window(0, 0, 6, 6), M.Window(2, 2, 2, 2))
        M.validate_required_coverage(required, M.Window(0, 0, 6, 6), M.Window(1, 1, 4, 4))

    def test_world_edge_ring_is_clipped(self):
        owner = np.ones((3, 3), dtype=int); owner[0, 0] = 0
        self.assertEqual(M.required_vertices(owner, 0).sum(), 9)

    def test_shared_conflict_rejects_last_writer_wins(self):
        mask = np.ones((2, 2), bool); a = np.zeros((2, 2), '<f4'); b = a.copy(); b[0, 0] = -0.0
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            M.merge_claims(a.shape, [(a, mask), (b, mask)], '<f4')
        other_mask = mask.copy(); other_mask[0, 0] = False
        np.testing.assert_array_equal(M.merge_claims(a.shape, [(a, mask), (b, other_mask)], '<f4'), a)

    def test_shared_gap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'coverage gap'):
            M.merge_claims((2, 2), [(np.zeros((2, 2)), np.zeros((2, 2), bool))], '<f4')

    def test_sculpt_identity_and_delta_bits(self):
        old = M.Window(-1, 3, 3, 2); new = M.Window(-2, 1, 6, 6)
        values = np.array([0x80000000, 0x3f123456], '<u4').tobytes()
        indices, deltas = M.remap_sculpt([0, 5], values, old, new)
        self.assertEqual(indices.tolist(), [13, 21]); self.assertEqual(deltas, values)
        with self.assertRaises(ValueError):
            M.remap_sculpt([1, 1], values, old, new)

    def test_modifier_guard_only_for_growth(self):
        old = M.Window(0, 0, 1, 1); raw = b'abcd'
        self.assertEqual(M.remap_grid_by_global_id(raw, old, old, b'', old, active_modifiers=True), raw)
        with self.assertRaisesRegex(ValueError, 'active modifiers'):
            M.remap_grid_by_global_id(raw, old, M.Window(0, 0, 2, 1), raw*2,
                                      M.Window(0, 0, 2, 1), active_modifiers=True)

    def test_grid_alignment_and_new_seed_coverage(self):
        with self.assertRaises(ValueError):
            M.global_window((1, 0), (0, 0), (2, 2))
        with self.assertRaisesRegex(ValueError, 'outside'):
            M.remap_grid_by_global_id(b'abcd', M.Window(0, 0, 1, 1), M.Window(-1, 0, 2, 1),
                                      b'abcd', M.Window(0, 0, 1, 1))

    def test_scene_property_edit_does_not_touch_other_nodes_or_multiline_data(self):
        scene = b'[gd_scene format=3]\r\n[node name="Terrain" type="Node3D" parent="."]\r\norigin = Vector2(-2, -4)\r\ngrid_size = Vector2i(3, 4)\r\nmetadata/x = {\r\n"s": "origin = Vector2(-2, -4)"\r\n}\r\n[node name="Other" parent="."]\r\norigin = Vector2(-2, -4)\r\n'
        output = M.replace_terrain_grid(scene, [-2, -4], [3, 4], [-4, -6], [5, 6])
        self.assertEqual(output.replace(b'origin = Vector2(-4, -6)', b'origin = Vector2(-2, -4)', 1)
                         .replace(b'grid_size = Vector2i(5, 6)', b'grid_size = Vector2i(3, 4)', 1), scene)
        with self.assertRaises(ValueError):
            M.replace_terrain_grid(scene, [0, 0], [3, 4], [-4, -6], [5, 6])

    def test_interruption_resume_and_repeat_noop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'
            (root/'old').write_bytes(b'before')
            M.stage_transaction(root, tx, {'old': b'after', 'new': b'new'}, {'old': M.sha256(b'before')})
            with self.assertRaises(InterruptedError):
                M.apply_transaction(root, tx, stop_after=1)
            self.assertEqual(M.apply_transaction(root, tx), 1)
            times = [(root/name).stat().st_mtime_ns for name in ('old', 'new')]
            self.assertEqual(M.apply_transaction(root, tx), 0)
            self.assertEqual(times, [(root/name).stat().st_mtime_ns for name in ('old', 'new')])
            M.rollback_transaction(root, tx)
            self.assertEqual((root/'old').read_bytes(), b'before'); self.assertFalse((root/'new').exists())

    def test_conflict_preflight_prevents_any_partial_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'
            (root/'a').write_bytes(b'a'); (root/'z').write_bytes(b'z')
            M.stage_transaction(root, tx, {'a': b'new-a', 'z': b'new-z'}, {})
            (root/'z').write_bytes(b'concurrent-edit')
            with self.assertRaises(ValueError):
                M.apply_transaction(root, tx)
            self.assertEqual((root/'a').read_bytes(), b'a')
            with self.assertRaises(ValueError):
                M.rollback_transaction(root, tx)

    def test_corrupt_backup_prevents_application(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'; (root/'a').write_bytes(b'a')
            M.stage_transaction(root, tx, {'a': b'changed'}, {})
            (tx/'original/000').write_bytes(b'bad')
            with self.assertRaises(ValueError):
                M.apply_transaction(root, tx)
            self.assertEqual((root/'a').read_bytes(), b'a')

    def test_portable_field_rejects_tampered_payload_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); raw = b'\0\0\0\0'
            (root/'height').write_bytes(raw); (root/'color').write_bytes(raw)
            manifest = {'schema': 'eloria-terrain-shared-field-v1',
                        'lattice': {'spacing': 2, 'globalVertexMin': [0, 0], 'vertices': [1, 1]},
                        'heights': {'path': 'height', 'sha256': M.sha256(raw), 'encoding': 'float32-little-endian'},
                        'colors': {'path': 'color', 'sha256': M.sha256(raw), 'encoding': 'rgba8'}}
            (root/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(M.load_shared_field(root, 'manifest.json')[2]['colors'], raw)
            (root/'color').write_bytes(b'bad!')
            with self.assertRaisesRegex(ValueError, 'invalid shared colors'):
                M.load_shared_field(root, 'manifest.json')
            with self.assertRaises(ValueError):
                M.checked_path(root, '../outside')

    def test_committed_repeat_refuses_reverted_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'; (root/'a').write_bytes(b'a')
            M.stage_transaction(root, tx, {'a': b'changed'}, {})
            M.apply_transaction(root, tx)
            (root/'a').write_bytes(b'a')
            with self.assertRaisesRegex(ValueError, 'reverted'):
                M.apply_transaction(root, tx)

    def test_concurrent_edit_in_apply_loop_is_preserved_and_blocks_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'
            (root/'a').write_bytes(b'a'); (root/'z').write_bytes(b'z')
            M.stage_transaction(root, tx, {'a': b'new-a', 'z': b'new-z'}, {})
            original_write = M._atomic_write
            def write_then_edit(path, data):
                original_write(path, data)
                if path == root/'a':
                    (root/'z').write_bytes(b'concurrent')
            with patch.object(M, '_atomic_write', write_then_edit):
                with self.assertRaisesRegex(ValueError, 'concurrent edit during application'):
                    M.apply_transaction(root, tx)
            self.assertEqual((root/'z').read_bytes(), b'concurrent')
            with self.assertRaisesRegex(ValueError, 'rollback refuses concurrent edit'):
                M.rollback_transaction(root, tx)
            self.assertEqual((root/'z').read_bytes(), b'concurrent')
            self.assertTrue((tx/'journal.json').exists())

    def test_concurrent_edit_in_rollback_loop_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'repo'; root.mkdir(); tx = Path(temp)/'tx'
            (root/'a').write_bytes(b'a'); (root/'z').write_bytes(b'z')
            M.stage_transaction(root, tx, {'a': b'new-a', 'z': b'new-z'}, {})
            M.apply_transaction(root, tx)
            original_write = M._atomic_write
            def restore_then_edit(path, data):
                original_write(path, data)
                if path == root/'z':
                    (root/'a').write_bytes(b'concurrent')
            with patch.object(M, '_atomic_write', restore_then_edit):
                with self.assertRaisesRegex(ValueError, 'concurrent edit during rollback'):
                    M.rollback_transaction(root, tx)
            self.assertEqual((root/'a').read_bytes(), b'concurrent')
            self.assertEqual((root/'z').read_bytes(), b'z')


if __name__ == '__main__':
    unittest.main()
