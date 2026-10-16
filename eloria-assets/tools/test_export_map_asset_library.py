from __future__ import annotations

import hashlib
import copy
from unittest.mock import patch
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_map_asset_library as E


class PlacementRootSelectionTest(unittest.TestCase):
    def test_same_name_inner_wrappers_keep_complete_placement(self):
        document = {'nodes': [
            {'name': 'CrackedSlab'},
            {'name': 'CrackedSlab', 'children': [0]},
            {'name': 'CrackedSlab', 'children': [1]},
            {'name': 'Region_Slab_WorldPlacement', 'children': [2]}],
            'scenes': [{'nodes': [3]}]}
        self.assertEqual(E._select_roots('continent:slab', document, ['CrackedSlab']), [2])

    def test_two_complete_placements_still_require_unambiguous_manifest(self):
        document = {'nodes': [{'name': 'Slab'}, {'name': 'Slab'}],
                    'scenes': [{'nodes': [0, 1]}]}
        with self.assertRaises(ValueError):
            E._select_roots('continent:slab', document, ['Slab'])


class SharedPrototypeExportTest(unittest.TestCase):
    def test_verified_prototype_expands_with_instance_transform_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = 'c' * 64
            prototype = root / '_shared/meshes' / (key + '.glb')
            prototype.parent.mkdir(parents=True)
            positions = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 1]], dtype='<f4')
            doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
                'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
                'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [0, 0, 0], 'max': [2, 2, 1]}],
                'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': positions.nbytes}],
                'buffers': [{'byteLength': positions.nbytes}]}
            E.S.dump_glb(prototype, doc, positions.tobytes())
            manifest = root / 'world.json'
            manifest.write_text(json.dumps({'externalMeshes': {'_shared/meshes/' + prototype.name: hashlib.sha256(prototype.read_bytes()).hexdigest()}}), encoding='utf-8')
            source = {'asset': {'version': '2.0'}, 'scenes': [{'nodes': [0]}],
                'nodes': [{'name': 'Prop', 'translation': [5, 3, 2], 'extras': {'eloria': {'prototype': key}}}]}
            with patch.object(E, 'MAPS', root):
                document, body, roots = E._materialize_selected(source, b'', [0], root / 'world.glb')
                low, high = E.OE.subtree_bounds_all(E.S, document, body, roots)
                np.testing.assert_allclose(low, [5, 3, 2])
                np.testing.assert_allclose(high, [7, 5, 3])
                self.assertNotIn('prototype', document['nodes'][0]['extras']['eloria'])
                prototype.write_bytes(prototype.read_bytes() + b'changed')
                with self.assertRaises(ValueError):
                    E._materialize_selected(source, b'', [0], root / 'world.glb')

    def test_skiff_reconstruction_is_pinned_and_preserves_other_boats(self):
        spec = next(row for row in json.loads(E.DEFAULT_MANIFEST.read_text(encoding='utf-8'))['assets'] if row['id'] == 'continent:pier-skiff')
        source = E.MAPS / spec['source']
        doc, body = E.S.GR.load(source)
        original = copy.deepcopy(doc)
        repaired, binary, report = E._repair_geometry(spec, doc, body, source)
        self.assertTrue(report['applied'])
        self.assertEqual(doc, original)
        changed = [i for i in range(len(doc['meshes'])) if repaired['meshes'][i] != doc['meshes'][i]]
        self.assertEqual(len(changed), 1)
        primitive = repaired['meshes'][changed[0]]['primitives'][0]
        positions = E.S.GR.accessor(repaired, binary, primitive['attributes']['POSITION'])
        np.testing.assert_allclose(positions.min(0), [-2.3, 0, -.75], atol=1e-6)
        np.testing.assert_allclose(positions.max(0), [2.3, .605, .75], atol=1e-6)
        bad = copy.deepcopy(spec)
        bad['geometryRepair']['sourceSha256'] = '0' * 64
        with self.assertRaises(ValueError):
            E._repair_geometry(bad, doc, body, source)


class MapAssetLibraryExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.output = cls.root / "assets/world/continent"
        cls.catalog = cls.root / "data/world/map_asset_extras.json"
        cls.result = E.export_library(E.DEFAULT_MANIFEST, cls.output, cls.catalog)
        cls.source = json.loads(E.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        cls.extras = json.loads(cls.catalog.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_declared_assets_and_prop_families_are_exported(self):
        expected_families = {
            "cracked_slab", "cellar_hatch", "loose_stone", "drain_grate",
            "shrine_slab", "ivy_arch", "cairn", "reed_hide", "ice_crack",
            "root_door", "tide_cave", "crystal_seam", "sand_sink",
            "hollow_tree", "well_shaft",
        }
        self.assertEqual(self.result["assetCount"], len(self.source["assets"]))
        self.assertEqual({row.get("family") for row in self.source["assets"] if row.get("family")},
                         expected_families)
        self.assertEqual([row["id"] for row in self.extras["entries"]],
                         [row["id"] for row in self.source["assets"]])
        self.assertLessEqual(self.result["outputBytes"], self.source["maxOutputBytes"])

    def test_outputs_are_centered_grounded_and_keep_reachable_resources(self):
        for source_spec, report in zip(self.source["assets"], self.result["assets"], strict=True):
            path = self.output / (source_spec["id"].removeprefix("continent:") + ".glb")
            document, body = E.S.GR.load(path)
            roots = document["scenes"][document.get("scene", 0)]["nodes"]
            low, high = E.OE.subtree_bounds_all(E.S, document, body, roots)
            self.assertAlmostEqual(float(low[1]), 0.0, places=4, msg=source_spec["id"])
            self.assertAlmostEqual(float((low[0] + high[0]) * 0.5), 0.0, places=4,
                                   msg=source_spec["id"])
            self.assertAlmostEqual(float((low[2] + high[2]) * 0.5), 0.0, places=4,
                                   msg=source_spec["id"])
            self.assertTrue(np.allclose(high - low, report["bounds"]["size"], atol=1e-4),
                            source_spec["id"])
            self.assertGreater(len(document.get("meshes", [])), 0, source_spec["id"])
            self.assertGreater(len(document.get("materials", [])), 0, source_spec["id"])
            for mesh in document['meshes']:
                for primitive in mesh['primitives']:
                    vertices = E.S.GR.accessor(document, body, primitive['attributes']['POSITION'])
                    self.assertTrue(np.isfinite(vertices).all(), source_spec['id'])
                    if 'indices' in primitive:
                        indices = E.S.GR.accessor(document, body, primitive['indices'])
                        self.assertLess(int(indices.max()), len(vertices), source_spec['id'])
            for image in document.get("images", []):
                uri = image.get("uri", "")
                self.assertTrue(uri and not Path(uri).is_absolute(), source_spec["id"])
                texture = (path.parent / uri).resolve()
                texture.relative_to(self.output.resolve())
                self.assertTrue(texture.is_file(), texture)

    def test_source_roots_are_current_complete_placements(self):
        allowed = E._allowed_sources()
        for spec in self.source["assets"]:
            source = (E.MAPS / spec["source"]).resolve()
            self.assertIn(source, allowed)
            document, _ = E.S.GR.load(source)
            roots = E._select_roots(spec["id"], document, spec["roots"])
            self.assertEqual(len(roots), len(spec["roots"]))


if __name__ == "__main__":
    unittest.main()
