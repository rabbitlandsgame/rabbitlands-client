import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
import assemble,rlglb
from append_native_fit import append_native_fit,SHAPE

class AppendCorrective(unittest.TestCase):
    def fixture(self,folder):
        path=folder/'hair_test.glb';w=assemble.Writer('Corrective preservation fixture')
        mat=w.material('rl_hair_clump',[1,1,1,1]);P=np.array([[0,0,0],[1,0,0],[0,1,0]],dtype='f4');N=np.tile([0,0,1],(3,1)).astype('f4')
        parts=[]
        for index in range(2):
            parts.append(w.primitive(P,N,np.array([[0,0],[1,0],[0,1]],dtype='f4'),np.array([[0,1,2]]),np.full((3,4),255,'u1'),np.zeros((3,4),'u1'),np.tile([1.,0,0,0],(3,1)).astype('f4'),mat,[(np.full((3,3),.001,'f4'),None),(np.full((3,3),.002,'f4'),None)]))
        mesh=w.mesh('hair_lod0',parts,['id_fixture_p','hl_tie_height_p']);w.g.g['meshes'][mesh]['weights']=[.2,.3]
        root=w.g.node(name='hair_root');node=w.g.node(name='hair_lod0',mesh=mesh,skin=0,weights=[.4,.5]);w.g.g['scenes'][0]['nodes']=[root,node]
        inverse=w.g.accessor(np.eye(4,dtype='f4').reshape(1,16),'MAT4');w.g.g['skins']=[{'joints':[root],'inverseBindMatrices':inverse}]
        w.g.g['asset']['extras']={'rlHair':{'version':1,'style':'fixture','sex':'female'}};w.save(str(path))
        Image.new('RGBA',(2,2),(120,130,140,255)).save(path.with_suffix('.png'));return path

    def test_arbitrary_targets_old_accessors_weights_and_atlas_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out'/source.name;before,blob=rlglb.read(str(source))
            D=np.array([[0,0,0],[0,0,.01],[0,0,.02]],dtype='f4')
            report=append_native_fit(source,out,{('hair_lod0',0):{'POSITION':D}},provenance={'private_path':'private authoring note'})
            after,result=rlglb.read(str(out));self.assertEqual(before['accessors'],after['accessors'][:len(before['accessors'])]);self.assertEqual(blob,result[:len(blob)])
            self.assertEqual(after['meshes'][0]['extras']['targetNames'],['id_fixture_p','hl_tie_height_p',SHAPE]);self.assertEqual(after['meshes'][0]['weights'],[.2,.3,0.])
            self.assertEqual(after['nodes'][1]['weights'],[.4,.5,0.]);self.assertNotIn('private_path',after['asset']['extras']['rlHair']['nativeFit'])
            for old,new in zip(before['meshes'][0]['primitives'],after['meshes'][0]['primitives']):
                self.assertEqual(old['attributes'],new['attributes']);self.assertEqual(old['indices'],new['indices']);self.assertEqual(old['targets'],new['targets'][:-1])
            first=after['meshes'][0]['primitives'][0];target=first['targets'][-1]
            np.testing.assert_array_equal(rlglb.accessor(after,result,target['POSITION']),D)
            normals=rlglb.accessor(after,result,first['attributes']['NORMAL'])+rlglb.accessor(after,result,target['NORMAL'])
            np.testing.assert_allclose(np.linalg.norm(normals,axis=1),1,atol=1e-6)
            second=after['meshes'][0]['primitives'][1];np.testing.assert_array_equal(rlglb.accessor(after,result,second['targets'][-1]['POSITION']),0)
            self.assertTrue(report['old_geometry_skin_colour_uv_indices_targets_exact']);self.assertEqual(source.with_suffix('.png').read_bytes(),out.with_suffix('.png').read_bytes())

    def test_explicit_normal_delta_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out'/source.name
            D=np.zeros((3,3),'f4');DN=np.tile([0,.1,-.005],(3,1)).astype('f4')
            append_native_fit(source,out,{('hair_lod0',0):{'POSITION':D,'NORMAL':DN}})
            g,b=rlglb.read(str(out));np.testing.assert_array_equal(rlglb.accessor(g,b,g['meshes'][0]['primitives'][0]['targets'][-1]['NORMAL']),DN)

    def test_bad_shape_and_existing_corrective_fail_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);bad=root/'bad'/source.name
            with self.assertRaises(AssertionError):append_native_fit(source,bad,{('hair_lod0',0):{'POSITION':np.zeros((2,3))}})
            self.assertFalse(bad.exists());out=root/'out'/source.name;append_native_fit(source,out,{})
            duplicate=root/'duplicate'/source.name
            with self.assertRaises(AssertionError):append_native_fit(out,duplicate,{})
            self.assertFalse(duplicate.exists())

if __name__=='__main__':unittest.main()
