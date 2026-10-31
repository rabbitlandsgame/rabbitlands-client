"""Exact result reuse must not weaken physical source or pose checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import native_hair_fixtures as fixtures


class ResultCacheTests(unittest.TestCase):
    def setup_files(self, directory):
        folder=Path(directory)
        P=np.array([[-.1,1.5,0],[.1,1.5,0],[0,1.8,0]],float)
        path=folder/'body.npz'
        np.savez(path,P=P,N=np.tile([0.,0,1],(3,1)),I=np.array([[0,1,2]]))
        part={'mesh':'body','file':path.name,'sha256':fixtures.sha(path)}
        case={'sex':'female','quality':0,'case':'neutral','rl_hair_identity_controls':{},
            'bone_deltas':{'Head':[[1,0,0],[0,1,0],[0,0,1],[0,0,0]]},'parts':[part]}
        second=copy.deepcopy(case);second.update(quality=1,case='other_label')
        manifest=folder/'manifest.json'
        manifest.write_text(json.dumps({'hair_identity_policy':'native_fixed_skull','cases':[case,second]}))
        hairpart={'P':P+np.array([0,0,.004]),'T':np.array([[0,1,2]]),'targets':{},
            'J':np.zeros((3,4),int),'W':np.tile([1.,0,0,0],(3,1)),
            'names':['Head'],'aliases':{}}
        hair={'sex':'female','sha256':'a'*64,'levels':[[hairpart]]}
        return manifest,hair,case,second

    def check(self,manifest,hair,**options):
        with patch.object(fixtures,'load_hair',return_value=hair),patch('builtins.print'):
            return fixtures.check_hair('unused',manifest,lods=(0,),grooms={'neutral':{}},**options)

    def test_duplicate_results_are_exact_and_all_labels_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest,hair,_,_=self.setup_files(directory)
            with patch.object(fixtures,'load_fixture',wraps=fixtures.load_fixture) as loader:
                cached=self.check(manifest,hair)
                self.assertEqual(loader.call_count,1)
            with patch.object(fixtures,'load_fixture',wraps=fixtures.load_fixture) as loader:
                reference=self.check(manifest,hair,cache_results=False)
                self.assertEqual(loader.call_count,2)
            for actual,expected in zip(cached['cases'],reference['cases']):
                self.assertEqual({k:v for k,v in actual.items() if k!='result_cache_reuse'},expected)
            self.assertEqual(len(cached['cases']),2)
            self.assertEqual(cached['result_cache']['reused_cases'],1)
            self.assertEqual(cached['result_cache']['evaluated_queries'],1)
            self.assertEqual(cached['result_cache']['fixture_sources'][0]['parts'][0]['mesh'],'body')
            self.assertTrue(cached['complete_requested_scan'])

    def test_changed_complete_bone_delta_never_reuses(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest,hair,first,second=self.setup_files(directory)
            # Even a named bone unused by this hair is part of the exact key.
            second['bone_deltas']['Unused']=[[1,0,0],[0,1,0],[0,0,1],[0,.0001,0]]
            data=json.loads(manifest.read_text());data['cases']=[first,second];manifest.write_text(json.dumps(data))
            result=self.check(manifest,hair)
            self.assertEqual(result['result_cache']['reused_cases'],0)
            second['bone_deltas']=copy.deepcopy(first['bone_deltas']);second['bone_deltas']['Head'][3][2]=.001
            data['cases']=[first,second];manifest.write_text(json.dumps(data));result=self.check(manifest,hair)
            self.assertEqual(result['result_cache']['reused_cases'],0)
            self.assertNotEqual(result['cases'][0]['minimum_clearance_mm'],result['cases'][1]['minimum_clearance_mm'])

    def test_changed_source_normals_never_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest,hair,first,second=self.setup_files(directory)
            path=Path(directory)/'other.npz'
            with np.load(Path(directory)/'body.npz') as a:P,T=a['P'],a['I']
            np.savez(path,P=P,N=np.tile([0.,0,-1],(3,1)),I=T)
            second['parts']=[{'mesh':'body','file':path.name,'sha256':fixtures.sha(path)}]
            data=json.loads(manifest.read_text());data['cases']=[first,second];manifest.write_text(json.dumps(data))
            result=self.check(manifest,hair)
            self.assertEqual(result['result_cache']['reused_cases'],0)
            self.assertGreater(result['cases'][0]['minimum_clearance_mm'],0)
            self.assertLess(result['cases'][1]['minimum_clearance_mm'],0)

    def test_cached_case_still_rehashes_physical_source(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest,hair,_,_=self.setup_files(directory);original=fixtures.load_fixture
            def load_then_tamper(path,record):
                surface=original(path,record)
                source=Path(directory)/'body.npz';source.write_bytes(source.read_bytes()+b'changed')
                return surface
            with patch.object(fixtures,'load_fixture',side_effect=load_then_tamper):
                with self.assertRaisesRegex(AssertionError,'fixture changed'):
                    self.check(manifest,hair)

    def test_weights_and_lods_are_distinct_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest,hair,_,_=self.setup_files(directory)
            hair['levels'].append(hair['levels'][0])
            with patch.object(fixtures,'load_hair',return_value=hair),patch('builtins.print'):
                result=fixtures.check_hair('unused',manifest,lods=(0,1),grooms={'neutral':{},'short':{'hl_length_n':1}})
            self.assertEqual(len(result['cases']),8)
            self.assertEqual(result['result_cache']['evaluated_queries'],4)
            self.assertEqual(result['result_cache']['reused_cases'],4)


if __name__=='__main__':unittest.main()
