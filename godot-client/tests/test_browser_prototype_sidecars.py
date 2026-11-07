import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from browser_prototype_sidecars import apply, POLICY, SUFFIX


class PrototypeSidecarArchiveTests(unittest.TestCase):
    def fixture(self, root):
        name = 'eloria-assets/maps/_shared/meshes/tree.glb'
        source = root / name
        source.parent.mkdir(parents=True)
        source.write_bytes(b'original prototype bytes')
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        derived = root / '.local/derived'
        derived.mkdir(parents=True)
        body = json.dumps({'schema': 1, 'policy': POLICY, 'engine': '4.7.2-stable (official)', 'source_sha256': digest}).encode()
        sidecar = derived / 'tree.json'
        sidecar.write_bytes(body)
        index = {'schema': 1, 'policy': POLICY, 'engine': '4.7.2-stable (official)',
                 'sources': {name: {'source_sha256': digest, 'sidecar_path': str(sidecar)}}}
        index_path = derived / 'index.json'
        index_path.write_text(json.dumps(index))
        assets = root / '.local/assets'
        assets.mkdir()
        temporary = assets / 'base.zip'
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name, source.read_bytes())
            archive.writestr('unchanged.txt', b'unchanged')
        archive_sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
        original = assets / (archive_sha + '.zip')
        temporary.rename(original)
        row = {'file': original.name, 'sha256': archive_sha, 'bytes': original.stat().st_size}
        catalog = {'groups': {'startup': {'archives': [], 'dependencies': [], 'unpacked_bytes': 0},
                              'map:test': {'archives': [row], 'dependencies': [], 'unpacked_bytes': 32}}}
        return name, body, index, index_path, assets, original, catalog

    def test_sidecars_follow_their_source_without_changing_source_bytes_or_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name, body, _, index, assets, original, catalog = self.fixture(root)
            previous = original.read_bytes()
            result, report = apply(catalog, index, assets, root)
            self.assertEqual(catalog['groups']['map:test']['archives'][0]['file'], original.name)
            self.assertEqual(original.read_bytes(), previous)
            self.assertEqual(result['groups']['startup'], catalog['groups']['startup'])
            row = result['groups']['map:test']['archives'][0]
            with zipfile.ZipFile(assets / row['file']) as archive:
                self.assertEqual(archive.read(name), b'original prototype bytes')
                self.assertEqual(archive.read(name + SUFFIX), body)
                self.assertEqual(archive.read('unchanged.txt'), b'unchanged')
            self.assertEqual(result['groups']['map:test']['unpacked_bytes'], 32 + len(body))
            self.assertEqual(report['sources'], 1)
            self.assertEqual(row['sha256'], hashlib.sha256((assets / row['file']).read_bytes()).hexdigest())

    def test_changed_sources_and_escaped_artifacts_are_rejected(self):
        for kind in ['changed', 'outside', 'traversal', 'engine', 'schema']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                name, _, data, index, assets, _, catalog = self.fixture(root)
                if kind == 'changed': (root / name).write_bytes(b'changed prototype')
                elif kind == 'outside': data['sources'][name]['sidecar_path'] = str(root / name)
                elif kind == 'traversal': data['sources']['../outside.glb'] = data['sources'].pop(name)
                elif kind == 'engine': data['engine'] = 'another-engine'
                else: data['schema'] = 2
                index.write_text(json.dumps(data))
                with self.assertRaises(ValueError): apply(catalog, index, assets, root)

    def test_index_does_not_silently_add_unreachable_prototypes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, _, index, assets, _, catalog = self.fixture(root)
            catalog['groups']['map:test']['archives'] = []
            with self.assertRaisesRegex(ValueError, 'absent'): apply(catalog, index, assets, root)


if __name__ == '__main__':
    unittest.main()
