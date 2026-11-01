"""Small GLB fixtures for splice preservation and fail-closed contracts."""
from pathlib import Path
import tempfile,unittest
import numpy as np
from PIL import Image
import glbwriter,rlglb
from reuse_qualified_cap import reuse,GROOMS

NAMES=[f'id_{i}' for i in range(46)]+list(GROOMS)

def fixture(path,cap=False,head='a'*64,rest=0.,groom=False,occupied=False):
    w=glbwriter.GLB();base=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
    P=np.vstack([base+[-2,0,0],base,base+[2,0,0]])
    if cap:P=np.vstack([base+[-2,0,0],[[0,0,0],[1,0,0],[0,1,0],[1,1,0]]])
    T=np.array([[0,1,2],[3,4,5],[6,7,8]]) if not cap else np.array([[0,1,2],[3,4,5],[4,6,5]])
    U=np.tile([[.02,.02],[.20,.02],[.02,.20]],(3,1)) if not cap else np.vstack([[[.02,.02],[.2,.02],[.02,.2]],[[0,0],[1,0],[0,1],[1,1]]])
    if occupied:U[:3]=[[0,0],[1,0],[0,1]]
    N=np.tile([0.,0,1],(len(P),1));C=np.tile([255,0,235,255],(len(P),1)).astype('u1');J=np.zeros((len(P),4),'u1');W=np.zeros((len(P),4));W[:,0]=1
    attrs={}
    for key,values,kind,component,normalized in [('POSITION',P,'VEC3',5126,False),('NORMAL',N,'VEC3',5126,False),('TEXCOORD_0',U,'VEC2',5126,False),('COLOR_0',C,'VEC4',5121,True),('JOINTS_0',J,'VEC4',5121,False),('WEIGHTS_0',W,'VEC4',5126,False)]:attrs[key]=w.accessor(values,kind,component,normalized=normalized,target=34962,minmax=key=='POSITION')
    names=NAMES+(['hl_native_fit'] if cap else []);targets=[]
    for name in names:
        D=np.zeros_like(P)
        if name=='id_0':D[:,0]=np.arange(len(P))*(.0002 if cap else .0001)
        if name=='hl_native_fit':D[3:,2]=.003
        if groom and name==GROOMS[0]:D[3:,0]=.001
        target={'POSITION':w.sparse_vec3(D,eps=0)}
        if cap and name=='id_0':target['NORMAL']=w.sparse_vec3(np.tile([.0001,0,0],(len(P),1)),eps=0)
        targets.append(target)
    ranges={'exterior':[0,3],'shell':[3,6],'tail_after':[6,9]} if not cap else {'reference':[0,3],'fixed_shell':[3,7]}
    mat=w.material('rl_hair_clump',extras={'texture':path.with_suffix('.png').name});primitive={'attributes':attrs,'indices':w.accessor(T.astype('u4').reshape(-1),'SCALAR',5125),'material':mat,'targets':targets,'extras':{'partVertexRanges':ranges}}
    w.g['meshes']=[{'name':'hair_lod0','primitives':[primitive],'weights':[0.]*len(names),'extras':{'targetNames':names}}];root=w.node(name='hair_root',translation=[rest,0,0]);ibm=w.accessor(np.eye(4).reshape(1,16),'MAT4');w.g['skins']=[{'joints':[root],'inverseBindMatrices':ibm,'skeleton':root}];w.g['scenes'][0]['nodes']=[root,w.node(name='hair_lod0',mesh=0,skin=0)];w.g['asset']['extras']={'rlHair':{'version':1,'style':'fixture','sex':'female','headSHA256':head,'tris':{'lod0':3},'materials':{'rl_hair_clump':path.with_suffix('.png').name}}};w.save(str(path));Image.new('RGBA',(256,256),(160,160,160,255)).save(path.with_suffix('.png'))

class CapReuse(unittest.TestCase):
    def setUp(self):
        stage=Path(__file__).resolve().parents[4]/'.local/cap-reuse-unit';stage.mkdir(parents=True,exist_ok=True);self.folder=Path(tempfile.mkdtemp(prefix='fixture-',dir=stage));self.source=self.folder/'recipient.glb';self.cap=self.folder/'qualified.glb';self.out=self.folder/'out/recipient.glb';fixture(self.source);fixture(self.cap,cap=True)
    def test_prefix_suffix_targets_and_zero_native_exterior(self):
        report=reuse(self.source,self.cap,self.out,tile_sizes=[(32,32)])
        self.assertTrue(report['all_visible_attribute_and_target_prefix_suffix_values_exact']);self.assertTrue(report['head_and_rigid_rest_exact']);self.assertTrue(report['all_non_tile_atlas_pixels_exact'])
        g,b=rlglb.read(str(self.out));p=g['meshes'][0]['primitives'][0];self.assertEqual(g['meshes'][0]['extras']['targetNames'],NAMES);self.assertEqual(p['extras']['partVertexRanges']['tail_after'],[7,10]);D=np.load(self.out.with_suffix('.cap-native.npz'))['lod0_POSITION'];self.assertTrue(np.array_equal(D[:3],np.zeros((3,3))));self.assertTrue(np.array_equal(D[7:],np.zeros((3,3))));self.assertTrue(np.allclose(D[3:7,2],.003))
    def test_head_and_rest_mismatch_rejected(self):
        fixture(self.cap,cap=True,head='b'*64)
        with self.assertRaises(AssertionError):reuse(self.source,self.cap,self.out,tile_sizes=[(32,32)])
        fixture(self.cap,cap=True,rest=.01)
        with self.assertRaises(AssertionError):reuse(self.source,self.cap,self.out,tile_sizes=[(32,32)])
    def test_nonzero_fixed_cap_groom_rejected(self):
        fixture(self.cap,cap=True,groom=True)
        with self.assertRaises(AssertionError):reuse(self.source,self.cap,self.out,tile_sizes=[(32,32)])
    def test_visible_uv_occupancy_never_overwritten(self):
        fixture(self.source,occupied=True)
        with self.assertRaisesRegex(AssertionError,'No unused cap tile'):reuse(self.source,self.cap,self.out,tile_sizes=[(32,32)])
        self.assertFalse(self.out.exists())

if __name__=='__main__':unittest.main()
