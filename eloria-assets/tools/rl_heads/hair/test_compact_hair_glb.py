import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
import glbwriter
import rlglb
from compact_hair_glb import compact_document, compact


class CompactHair(unittest.TestCase):
    def fixture(self):
        w = glbwriter.GLB()
        w.g['asset']['extras'] = {'rlHair': {'style': 'fixture', 'sex': 'female'}}
        secret = b'UNREFERENCED_AUTHORING_PAYLOAD'
        w._view(secret)
        w.accessor(np.arange(12, dtype='f4').reshape(4, 3), 'VEC3')
        p = w.accessor(np.eye(3, dtype='f4'), 'VEC3', minmax=True)
        c = w.accessor(np.arange(12, dtype='u1').reshape(3, 4), 'VEC4', 5121, normalized=True)
        t = w.accessor(np.array([0, 1, 2], dtype='u4'), 'SCALAR', 5125)
        sparse = w.sparse_vec3(np.array([[0, 0, 0], [0, .125, 0], [0, 0, 0]], dtype='f4'))
        zero = w.sparse_vec3(np.zeros((3, 3), dtype='f4'))
        inverse = w.accessor(np.eye(4, dtype='f4').reshape(1, 16), 'MAT4')
        image = w._view(b'encoded-image-payload-kept-exact')
        w.g['images'] = [{'bufferView': image, 'mimeType': 'image/png'}]
        w.g['meshes'] = [{'name': 'hair_lod0', 'primitives': [{
            'attributes': {'POSITION': p, 'COLOR_0': c}, 'indices': t,
            'targets': [{'POSITION': sparse}, {'POSITION': zero}],
            'extras': {'partVertexRanges': {'exterior': [0, 3]}}}],
            'extras': {'targetNames': ['id_fixture_p', 'hl_native_fit']}, 'weights': [.2, 0]}]
        w.g['nodes'] = [{'name': 'Head'}, {'mesh': 0, 'skin': 0, 'weights': [.3, 0]}]
        w.g['skins'] = [{'joints': [0], 'inverseBindMatrices': inverse}]
        w.g['buffers'][0]['byteLength'] = len(w.blob)
        return w.g, bytes(w.blob), secret

    def test_sparse_integer_skin_image_live_bytes_and_defaults_preserved(self):
        g, blob, secret = self.fixture()
        original = copy.deepcopy(g)
        out, packed, maps = compact_document(g, blob)
        self.assertEqual(g, original)
        self.assertNotIn(secret, packed)
        self.assertLess(len(packed), len(blob))
        self.assertEqual(len(out['accessors']), len(g['accessors']) - 1)
        for old, new in maps['accessors'].items():
            np.testing.assert_array_equal(rlglb.accessor(g, blob, old, normalize=False),
                                          rlglb.accessor(out, packed, new, normalize=False))
        self.assertEqual(out['nodes'], g['nodes'])
        self.assertEqual(out['meshes'][0]['weights'], [.2, 0])
        self.assertEqual(out['meshes'][0]['extras'], g['meshes'][0]['extras'])
        twice, second, _ = compact_document(out, packed)
        self.assertEqual(twice, out)
        self.assertEqual(second, packed)

    def test_unknown_reference_graphs_fail_closed(self):
        g, blob, _ = self.fixture()
        for mutation in [lambda x: x.update(animations=[{}]),
                         lambda x: x.update(extensionsUsed=['EXT_unknown']),
                         lambda x: x['buffers'].append({'byteLength': 0}),
                         lambda x: x['meshes'][0].update(extensions={'EXT_unknown': {}})]:
            changed = copy.deepcopy(g)
            mutation(changed)
            with self.assertRaises(AssertionError):
                compact_document(changed, blob)

    def test_separate_output_and_companion_atlas_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            g, blob, _ = self.fixture()
            w = glbwriter.GLB()
            w.g, w.blob = g, bytearray(blob)
            source = root / 'fixture.glb'
            w.save(str(source))
            source.with_suffix('.png').write_bytes(b'external-runtime-atlas')
            before = source.read_bytes()
            output = root / 'package' / source.name
            report = compact(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(source.with_suffix('.png').read_bytes(), output.with_suffix('.png').read_bytes())
            self.assertTrue(report['live_payload_bytes_exact'])
            with self.assertRaises(AssertionError):
                compact(source, source)
            with self.assertRaises(AssertionError):
                compact(source, output)


if __name__ == '__main__':
    unittest.main()
