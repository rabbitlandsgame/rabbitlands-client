import copy
import unittest
import numpy as np
import glbwriter
import rlglb
from compact_hair_glb import compact_detail_vertices


class CompactDetailVertices(unittest.TestCase):
    def fixture(self):
        w = glbwriter.GLB()
        w.g['asset']['extras'] = {'rlHair': {'style': 'fixture'}}
        w.g['materials'] = [{'name': 'rl_hair_clump'}, {'name': 'rl_hair_card'}]
        arrays = {'POSITION': (np.arange(15, dtype='f4').reshape(5, 3), 'VEC3', 5126, False),
                  'NORMAL': (np.eye(5, 3, dtype='f4'), 'VEC3', 5126, False),
                  'TEXCOORD_0': (np.arange(10, dtype='f4').reshape(5, 2), 'VEC2', 5126, False),
                  'COLOR_0': (np.arange(20, dtype='u1').reshape(5, 4), 'VEC4', 5121, True),
                  'JOINTS_0': (np.arange(20, dtype='u2').reshape(5, 4), 'VEC4', 5123, False),
                  'WEIGHTS_0': (np.arange(20, dtype='u2').reshape(5, 4), 'VEC4', 5123, True)}
        attr = {name: w.accessor(data, kind, ct, normalized=norm) for name, (data, kind, ct, norm) in arrays.items()}
        sparse = np.zeros((5, 3), dtype='f4'); sparse[3, 1] = .125
        negative_zero = np.zeros((5, 3), dtype='f4'); negative_zero[1, 0] = -0.
        shapes = [{'POSITION': w.sparse_vec3(sparse), 'NORMAL': w.sparse_vec3(sparse * 2)},
                  {'POSITION': w.accessor(negative_zero, 'VEC3')}]
        p = {'material': 1, 'attributes': attr, 'indices': w.accessor(np.array([3, 1, 4], dtype='u2'), 'SCALAR', 5123),
             'targets': shapes, 'extras': {'partVertexRanges': {'detail': [0, 5]}}}
        core = copy.deepcopy(p); core['material'] = 0; core['extras'] = {'partVertexRanges': {'shell': [0, 5]}}
        w.g['meshes'] = [{'name': 'hair_lod0', 'primitives': [core, p], 'weights': [0, 0],
                          'extras': {'targetNames': ['id_fixture_p', 'hl_native_fit']}}]
        w.g['nodes'] = [{'mesh': 0, 'weights': [.2, 0]}]
        w.g['buffers'][0]['byteLength'] = len(w.blob)
        return w.g, bytes(w.blob)

    def test_only_unindexed_detail_rows_removed_and_all_corner_bytes_exact(self):
        g, blob = self.fixture(); original = copy.deepcopy(g)
        out, packed, reports = compact_detail_vertices(g, blob)
        self.assertEqual(g, original)
        self.assertEqual(out['meshes'][0]['primitives'][0], g['meshes'][0]['primitives'][0])
        self.assertEqual(out['nodes'], g['nodes'])
        self.assertEqual(out['meshes'][0]['weights'], [0, 0])
        self.assertEqual(out['meshes'][0]['extras'], g['meshes'][0]['extras'])
        self.assertEqual(reports[0]['old_to_new'], [-1, 0, -1, 1, 2])
        p = out['meshes'][0]['primitives'][1]
        self.assertEqual(p['extras']['partVertexRanges'], {'detail': [0, 3]})
        np.testing.assert_array_equal(rlglb.accessor(out, packed, p['indices']).ravel(), [1, 0, 2])
        old = g['meshes'][0]['primitives'][1]
        for before, after in [(old['attributes'], p['attributes'])] + list(zip(old['targets'], p['targets'])):
            for name, index in before.items():
                dtype = rlglb.COMPONENT[g['accessors'][index]['componentType']]
                a = rlglb.accessor(g, blob, index, normalize=False)[[1, 3, 4]].astype(dtype)
                b = rlglb.accessor(out, packed, after[name], normalize=False).astype(dtype)
                self.assertEqual(a.tobytes(), b.tobytes())

    def test_no_unused_rows_keeps_original_graph_and_binary_exact(self):
        g, blob = self.fixture(); p = g['meshes'][0]['primitives'][1]
        # The original stream is fully used, including a degenerate triangle.
        w = glbwriter.GLB(); w.g, w.blob = copy.deepcopy(g), bytearray(blob)
        p = w.g['meshes'][0]['primitives'][1]
        p['indices'] = w.accessor(np.array([0, 1, 2, 3, 4, 4]), 'SCALAR', 5125)
        w.g['buffers'][0]['byteLength'] = len(w.blob)
        out, packed, report = compact_detail_vertices(w.g, bytes(w.blob))
        self.assertEqual(out, w.g); self.assertEqual(packed, bytes(w.blob))
        self.assertEqual(report[0]['new_count'], 5)

    def test_ambiguous_stream_ranges_fail_closed(self):
        g, blob = self.fixture()
        for ranges in [{'detail': [1, 5]}, {'detail': [0, 5], 'shell': [0, 1]}, {}]:
            bad = copy.deepcopy(g)
            bad['meshes'][0]['primitives'][1]['extras']['partVertexRanges'] = ranges
            with self.assertRaises(AssertionError): compact_detail_vertices(bad, blob)


if __name__ == '__main__': unittest.main()
