"""Focused offline regressions for publishing fitted animation assets."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from video_motion.asset import Asset, accessor, read_glb, write_glb
from video_motion.packing import compact, append_array
from video_motion.promotion import preserve_runtime_clips, world_batch
from validate_creature_glbs import skin_attributes, horizontal_root_excursion

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'eloria-assets/source/animations/canine'
FOX = ROOT / 'godot-client/assets/actors/native/creatures/red_fox.glb'


class MotionPromotion(unittest.TestCase):
    def test_fixed_pivot_offset_is_not_locomotion_drift(self):
        self.assertEqual(horizontal_root_excursion([[1.2,0,-.4]]*3), 0.0)
        self.assertAlmostEqual(horizontal_root_excursion([[1.2,0,-.4],[1.25,.3,-.4]]), .05)

    def test_normalized_integer_weights_are_combined_before_validation(self):
        doc = {'accessors': [], 'bufferViews': []}
        blob = bytearray()
        attrs = {}
        for name, values, dtype, component, normalized in [
                ('JOINTS_0', [0,1,2,3], '<u2', 5123, False),
                ('JOINTS_1', [4,5,6,7], '<u2', 5123, False),
                ('WEIGHTS_0', [32,32,32,32], 'u1', 5121, True),
                ('WEIGHTS_1', [32,32,32,31], 'u1', 5121, True)]:
            data = np.asarray(values, dtype=dtype).tobytes()
            doc['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':len(data)})
            blob.extend(data)
            attrs[name] = len(doc['accessors'])
            doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,
                'componentType':component,'type':'VEC4','count':1,'normalized':normalized})
        joints, weights = skin_attributes(doc, blob, attrs)
        np.testing.assert_array_equal(joints, [list(range(8))])
        np.testing.assert_allclose(weights.sum(1), 1.0, atol=1e-15)
        self.assertEqual(int((weights > 0).sum()), 8)

    def test_all_published_hashes(self):
        manifest = json.loads((LIB / 'manifest.json').read_text(encoding='utf-8'))
        for name, sha in manifest['files_sha256'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((LIB / name).read_bytes()).hexdigest(), sha)

    def test_second_weight_set_contributes_to_actual_skin(self):
        asset = Asset(FOX)
        found = False
        for node_id, node in enumerate(asset.document['nodes']):
            if 'mesh' not in node or 'skin' not in node:
                continue
            for primitive in asset.document['meshes'][node['mesh']]['primitives']:
                attrs = primitive['attributes']
                joints, weights = skin_attributes(asset.document, asset.blob, attrs)
                self.assertEqual(weights.shape[1], 8)
                self.assertTrue(np.allclose(weights.sum(1), 1, atol=2e-4))
                found |= bool(np.any(weights[:, 4:] > 0))
                part = next(p for p in asset.parts if p['node'] == node_id)
                np.testing.assert_array_equal(joints, part['joints'])
                np.testing.assert_array_equal(weights, part['weights'])
                missing = {k:v for k,v in attrs.items() if k != 'WEIGHTS_1'}
                with self.assertRaises(ValueError):
                    skin_attributes(asset.document, asset.blob, missing)
        self.assertTrue(found, 'fixture must exercise real influences beyond four')

    def test_constant_only_clip_retains_duration_and_deletes_dead_storage(self):
        doc, data = read_glb(FOX)
        original = copy.deepcopy(doc)
        blob = bytearray(data)
        inp = append_array(doc, blob, np.linspace(0, 5, 101)[:, None], 'SCALAR')
        out = append_array(doc, blob, np.tile([0,0,0,1], (101,1)), 'VEC4')
        append_array(doc, blob, np.ones((10000,3)), 'VEC3')
        doc['animations'] = [{'name':'constant', 'samplers':[{'input':inp,'output':out}],
                              'channels':[{'sampler':0,'target':{'node':0,'path':'rotation'}}]}]
        packed, payload, report = compact(doc, blob)
        self.assertEqual(report['constant_samplers_collapsed'], 1)
        self.assertLess(len(payload), len(blob))
        sampler = packed['animations'][0]['samplers'][0]
        np.testing.assert_array_equal(accessor(packed,payload,sampler['input']).ravel(), [0,5])
        np.testing.assert_array_equal(accessor(packed,payload,sampler['output']), [[0,0,0,1]]*2)
        self.assertEqual(doc['nodes'], original['nodes'])

    def test_unknown_binary_extension_rejected(self):
        doc, blob = read_glb(FOX)
        doc['extensionsUsed'] = ['EXT_meshopt_compression']
        with self.assertRaises(ValueError): compact(doc, blob)

    def test_inserted_neutral_parent_preserves_existing_runtime_motion(self):
        old = Asset(FOX)
        doc = copy.deepcopy(old.document)
        node = next(n for n in old.joints if old.parent[n] >= 0 and 'matrix' not in doc['nodes'][n])
        parent = int(old.parent[node]); bridge = len(doc['nodes'])
        shift = np.array([.03, .02, -.01])
        doc['nodes'][parent]['children'].remove(node)
        doc['nodes'][parent]['children'].append(bridge)
        doc['nodes'].append({'name':'Regression_NeutralBridge','translation':shift.tolist(),'children':[node]})
        doc['nodes'][node]['translation'] = (old.t[node] - shift).tolist()
        scratch = ROOT / 'godot-client/test-artifacts'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            target = Path(tmp)/'target.glb'
            write_glb(target, doc, old.blob)
            fitted = Asset(target)
            result, blob, _ = preserve_runtime_clips(old, fitted)
            destination = Path(tmp)/'published.glb'
            write_glb(destination, result, blob)
            final = Asset(destination)
            for clip in ['Idle_A','Fighting_Idle','Hit_Chest','Jog']:
                ts = np.linspace(0, old.duration(clip), 123)
                np.testing.assert_allclose(world_batch(old,ts,clip), world_batch(final,ts,clip)[:,:old.n], atol=2e-6)


if __name__ == '__main__': unittest.main()
