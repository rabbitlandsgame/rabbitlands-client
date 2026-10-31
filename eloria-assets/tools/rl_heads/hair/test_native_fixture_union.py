import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
import trimesh
from native_fixture_union import NativeFixtureUnion


class UnionTest(unittest.TestCase):
    def make(self,stage):
        cases=[]
        for index,radius in enumerate([.1,.104]):
            mesh=trimesh.creation.icosphere(subdivisions=1,radius=radius);P=mesh.vertices+np.array([0,1.7,0]);N=mesh.vertices/radius
            path=stage/f's{index}.npz';np.savez_compressed(path,P=P,N=N,I=mesh.faces)
            part={'mesh':'body','file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            cases.append({'sex':'female','quality':0,'case':['neutral','field-100'][index],'clip':'Rest_Pose','fraction':0,'rl_hair_identity_controls':{},'parts':[part]})
        duplicate=json.loads(json.dumps(cases[0]));duplicate['quality']=1;cases.append(duplicate)
        pose=json.loads(json.dumps(cases[1]));pose.update(case='walk',clip='Walk',fraction=.25);cases.append(pose)
        manifest=stage/'manifest.json';manifest.write_text(json.dumps({'hair_identity_policy':'native_fixed_skull','cases':cases}));return manifest
    def test_complete_surface_union_deduplicates_and_retains_limiting_witness(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=self.make(Path(folder));union=NativeFixtureUnion(manifest,'female')
            self.assertEqual(len(union.surfaces),2);self.assertEqual(len(union.records),2)
            P=np.array([[0,1.803,0],[.15,1.7,0]])
            actual=union.signed(P);a=union.surfaces[0].signed(P);b=union.surfaces[1].signed(P)
            take=b[0]<a[0]
            for index in range(3):
                expected=a[index].copy();expected[take]=b[index][take];np.testing.assert_array_equal(actual[index],expected)
            self.assertLess(actual[0][0],0)
    def test_version_policy_and_fixture_hash_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=self.make(Path(folder));data=json.loads(manifest.read_text());data['cases'][0]['rl_hair_identity_controls']={'jaw_width':1};manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(AssertionError,'zero High'):NativeFixtureUnion(manifest,'female')
            data['cases'][0]['rl_hair_identity_controls']={};manifest.write_text(json.dumps(data));(Path(folder)/'s0.npz').write_bytes(b'changed')
            with self.assertRaisesRegex(AssertionError,'fixture changed'):NativeFixtureUnion(manifest,'female')


if __name__=='__main__':unittest.main()
