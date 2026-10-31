import io,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
import coverage,glbwriter
from material_roles import CLUMP_ROLES,material_role,validate_roles

class MaterialRoles(unittest.TestCase):
    def test_only_explicit_crest_names_are_clumps(self):
        for name in CLUMP_ROLES:self.assertEqual(material_role(name),'rl_hair_clump')
        for name in ['rl_hair_clump','rl_hair_card','rl_beard','rl_hair_clump_crest_extra','rl_hair_clump_crest_lod3']:
            self.assertEqual(material_role(name),name)
    def test_new_roles_require_explicit_textures_but_old_fallbacks_remain(self):
        self.assertEqual(validate_roles([{'name':'rl_hair_clump'}]),[])
        for name in CLUMP_ROLES:
            self.assertTrue(validate_roles([{'name':name}]))
            self.assertEqual(validate_roles([{'name':name,'extras':{'texture':name+'.png'}}]),[])
    def test_root_policy_matches_clump_with_unchanged_conservative_gate(self):
        self.assertEqual(coverage.ALPHA_SCISSOR,.5)
        for reference in [False,True]:
            for soft in [False,True]:
                for capability in [False,True]:
                    extras={'referenceSurface':reference,'softHairline':soft,'softRootCoverage':capability}
                    expected=coverage.uses_root_coverage({'name':'rl_hair_clump','extras':extras})
                    for name in CLUMP_ROLES:self.assertEqual(coverage.uses_root_coverage({'name':name,'extras':extras}),expected)
        self.assertFalse(coverage.uses_root_coverage({'name':'rl_hair_clump_crest_extra','extras':{'softHairline':True}}))
    def test_each_concrete_material_loads_its_own_embedded_alpha(self):
        writer=glbwriter.GLB();writer.g['images']=[];writer.g['textures']=[];primitives=[]
        names=['rl_hair_clump']+list(CLUMP_ROLES)
        for index,name in enumerate(names):
            alpha=[0,128,191,255][index];pixels=io.BytesIO();Image.new('RGBA',(2,2),(160,160,160,alpha)).save(pixels,format='PNG');image=writer._view(pixels.getvalue());writer.g['images'].append({'bufferView':image,'mimeType':'image/png'});writer.g['textures'].append({'source':index});mat=writer.material(name,extras={'texture':name+'.png','softHairline':True,'softRootCoverage':True});writer.g['materials'][mat]['pbrMetallicRoughness']['baseColorTexture']={'index':index}
            attrs={'POSITION':writer.accessor(np.array([[0,0,index],[1,0,index],[0,1,index]]),'VEC3'),'TEXCOORD_0':writer.accessor(np.zeros((3,2)),'VEC2'),'COLOR_0':writer.accessor(np.ones((3,4)),'VEC4')};primitives.append({'attributes':attrs,'indices':writer.accessor(np.array([0,1,2]),'SCALAR',comp=5123),'material':mat})
        writer.g['meshes']=[{'name':'hair_lod0','primitives':primitives,'extras':{'targetNames':[]}}]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'roles.glb';writer.save(path);_,levels=coverage.load_hair(str(path));hair=levels[0];keys=hair['tex'];self.assertEqual(len(set(keys)),4);self.assertTrue(hair['root_coverage'].all())
            np.testing.assert_allclose([coverage._alpha(key)[0,0] for key in keys],[0,128/255,191/255,1],atol=1e-7)
            for key in keys:coverage._TEX.pop(key,None)

if __name__=='__main__':unittest.main()
