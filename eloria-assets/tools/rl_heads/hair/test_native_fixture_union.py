import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
import trimesh
from native_fixture_union import NativeFixtureUnion
from native_hair_fixtures import EvaluatedNativeSurface


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


class OptimizedUnionTest(unittest.TestCase):
    def union(self,surfaces):
        result=object.__new__(NativeFixtureUnion);result.surfaces=surfaces;result.records=[]
        result.optimize=True;result._plans=None;result.last_query_stats={};return result
    def boxes(self,tall=False,left_down=True):
        left=trimesh.creation.box(extents=[.1,.1,.1]);left.apply_translation([-.2,1.8,0])
        right=trimesh.creation.box(extents=[.1,.1,.1]);right.apply_translation([.2,1.8,0])
        mesh=trimesh.util.concatenate([left,right]);P=mesh.vertices.copy();N=mesh.vertex_normals.copy()
        N[:len(left.vertices)]=[0,-1 if left_down else 1,0]
        if tall:P[(P[:,0]>0)&(P[:,1]>1.8),1]=2.2
        return EvaluatedNativeSurface(P,N,mesh.faces)
    def equal(self,union,points):
        original=union.signed(points,optimize=False);actual=union.signed(points,optimize=True)
        for a,b in zip(actual,original):np.testing.assert_array_equal(a,b)
        return actual
    def test_raw_sign_is_reconstructed_before_each_fixtures_bounds_proof(self):
        base=self.boxes();changed=self.boxes(tall=True);union=self.union([base,changed])
        P=np.array([[-.22,1.95,.012]])
        self.assertGreater(base.signed(P)[0][0],0);self.assertLess(changed.signed(P)[0][0],0)
        actual=self.equal(union,P);self.assertLess(actual[0][0],0)
        frame=union._frame(P,base.signed(P),np.ones(1,bool));_,queried=union._query_fixture(changed,union._plans[0],P,frame)
        self.assertEqual(queried,0)
    def test_changed_normals_are_reconstructed_on_unchanged_geometry(self):
        base=self.boxes(tall=True,left_down=False);changed=self.boxes(tall=True,left_down=True);union=self.union([base,changed])
        result=self.equal(union,np.array([[-.22,1.95,.012]]));self.assertLess(result[0][0],0)
        np.testing.assert_array_equal(result[2],[ [0,-1,0] ])
    def test_geometry_change_falls_back_on_tied_closest_witnesses(self):
        union=self.union([self.boxes(),self.boxes(tall=True)])
        self.equal(union,np.array([[-.2,1.95,0]]))
        self.assertGreater(union.last_query_stats['ambiguous_baseline_points'],0)
    def test_equidistant_witnesses_with_different_closest_points_fall_back(self):
        base=self.boxes();changed=self.boxes(tall=True);union=self.union([base,changed]);union._prepare()
        points=np.array([[0,1.81,.012]])
        frame=union._frame(points,base.signed(points),np.ones(1,bool))
        self.assertTrue(frame['ambiguous'][0])
        self.equal(union,points)
    def test_planar_fixture_retains_its_original_sign(self):
        P=np.array([[0,0,0],[1,0,0],[0,1,0]],float);T=np.array([[0,1,2]])
        up=EvaluatedNativeSurface(P,np.tile([0,0,1],(3,1)),T);down=EvaluatedNativeSurface(P,np.tile([0,0,-1],(3,1)),T)
        actual=self.equal(self.union([up,down]),np.array([[.2,.3,.1]]));self.assertLess(actual[0][0],0)


if __name__=='__main__':unittest.main()
