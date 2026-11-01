import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
import glbwriter
import rlglb
from inherit_native_detail_roots import inherit, native_digest


class NativeDetailRoots(unittest.TestCase):
    def fixture(self, path, far=False, wrong_skin=False, native_y=.005):
        w = glbwriter.GLB()
        w.g['asset']['extras'] = {'rlHair': {'nativeFit': {'shape': 'hl_native_fit', 'deltaSHA256': 'previous'}}}
        w.g['materials'] = [{'name': 'rl_hair_clump'}, {'name': 'rl_hair_card'}]
        names = ['id_fixture_p', 'hl_length_p', 'hl_tie_height_p', 'hl_tie_height_n', 'hl_native_fit']
        primitives = []
        for pi, P in enumerate([np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]], dtype='f4'),
                                 np.array([[.2, 0, .2], [.3, 0, .2], [.2, .1, .2], [.3, .1, .2]], dtype='f4')]):
            if pi and far: P[:, 1] += .02
            n = len(P); C = np.ones((n, 4), dtype='u1') * 255
            if pi: C[:2, 1] = 0
            attributes = {'POSITION': w.accessor(P, 'VEC3'), 'NORMAL': w.accessor(np.tile([0, 1, 0], (n, 1)), 'VEC3'),
                          'COLOR_0': w.accessor(C, 'VEC4', 5121, normalized=True),
                          'TEXCOORD_0': w.accessor(np.array([[0, 0], [1, 0], [0, 1], [1, 1]])[:n], 'VEC2'),
                          'JOINTS_0': w.accessor(np.full((n, 4), 1 if pi and wrong_skin else 0), 'VEC4', 5123),
                          'WEIGHTS_0': w.accessor(np.tile([65535, 0, 0, 0], (n, 1)), 'VEC4', 5123, normalized=True)}
            targets = []
            for at, name in enumerate(names):
                D = np.zeros((n, 3), dtype='f4')
                D[:, 1] = (native_y + P[:, 0] * .001) if at == 4 and not pi else .001 * at
                if at == 4 and not pi: D[0, 0] = -0.
                targets.append({'POSITION': w.accessor(D, 'VEC3')})
            T = [0, 1, 2] if pi == 0 else [0, 1, 2, 1, 3, 2]
            primitives.append({'material': pi, 'attributes': attributes, 'indices': w.accessor(np.asarray(T), 'SCALAR', 5125),
                               'targets': targets, 'extras': {'partVertexRanges': {'exterior': [0, 3], 'shell': [3, 3]} if not pi else {'detail': [0, 4]}}})
        w.g['meshes'] = [{'name': 'hair_lod0', 'primitives': primitives, 'extras': {'targetNames': names}, 'weights': [0] * len(names)}]
        w.g['nodes'] = [{'mesh': 0, 'weights': [0] * len(names)}]
        w.save(str(path)); path.with_suffix('.png').write_bytes(b'atlas-exact')

    def test_existing_native_rewrite_keeps_all_high_data_and_defaults_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'hair.glb'; self.fixture(source)
            before = source.read_bytes(); g, b = rlglb.read(str(source)); out = root / 'out' / source.name
            report = inherit(source, out); actual, packed = rlglb.read(str(out)); self.assertEqual(source.read_bytes(), before)
            self.assertEqual(actual['meshes'][0]['extras'], g['meshes'][0]['extras']); self.assertEqual(actual['nodes'], g['nodes'])
            self.assertEqual(source.with_suffix('.png').read_bytes(), out.with_suffix('.png').read_bytes())
            p = actual['meshes'][0]['primitives'][1]; F = rlglb.accessor(actual, packed, p['attributes']['POSITION']); D = rlglb.accessor(actual, packed, p['targets'][-1]['POSITION'])
            for binding in report['records'][0]['bindings']:
                P = rlglb.accessor(actual, packed, actual['meshes'][0]['primitives'][0]['attributes']['POSITION'])
                PD = rlglb.accessor(actual, packed, actual['meshes'][0]['primitives'][0]['targets'][-1]['POSITION'])
                for at, index in enumerate(binding['root_indices']):
                    tv = np.asarray(binding['parent_triangles'][at]); bc = np.asarray(binding['barycentric'][at])
                    np.testing.assert_allclose(F[index] + D[index], ((P + PD)[tv] * bc[:, None]).sum(0), atol=1e-9)
            self.assertEqual(native_digest(actual, packed), report['native_position_normal_digest'])
            self.assertLessEqual(report['maximum_encoded_native_root_error_mm'], .001)
            self.assertNotEqual(report['native_position_normal_digest'], 'previous')
            core = actual['meshes'][0]['primitives'][0]
            self.assertTrue(np.signbit(rlglb.accessor(actual, packed, core['targets'][-1]['POSITION'])[0, 0]))

    def test_far_roots_and_different_skin_fail_before_output(self):
        for kwargs in [{'far': True}, {'wrong_skin': True}]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / 'hair.glb'; self.fixture(source, **kwargs); out = root / 'out' / source.name
                with self.assertRaises(AssertionError): inherit(source, out)
                self.assertFalse(out.exists())

    def test_reviewed_native_skin_mismatch_requires_explicit_local_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'hair.glb'; self.fixture(source, native_y=.018)
            refused = root / 'default' / source.name
            with self.assertRaises(AssertionError): inherit(source, refused)
            self.assertFalse(refused.exists())
            accepted = root / 'reviewed' / source.name
            report = inherit(source, accepted, max_delta_mm=20)
            self.assertLessEqual(report['maximum_encoded_native_root_error_mm'], .001)
            actual, blob = rlglb.read(str(accepted)); detail = actual['meshes'][0]['primitives'][1]
            delta = rlglb.accessor(actual, blob, detail['targets'][-1]['POSITION'])
            self.assertGreater(np.linalg.norm(delta, axis=1).max()*1000, 14)
            self.assertLess(np.linalg.norm(delta, axis=1).max()*1000, 20)
            with self.assertRaises(AssertionError): inherit(source, root / 'too-far' / source.name, max_delta_mm=21)


if __name__ == '__main__': unittest.main()
