import copy,tempfile,unittest
from pathlib import Path
import numpy as np
import rlglb
from append_native_fit import append_native_fit
import test_append_native_fit as fixtures
from conform_crest_base_normals import native_fit_digest

class CanonicalNativeDigest(unittest.TestCase):
    def test_matches_append_with_explicit_and_implicit_normal_fields(self):
        for explicit in [False,True]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=fixtures.AppendCorrective().fixture(root)
                entry={'POSITION':np.tile([0,0,.01],(3,1)).astype('f4')}
                if explicit:entry['NORMAL']=np.tile([0,.1,-.005],(3,1)).astype('f4')
                output=root/'out'/source.name
                report=append_native_fit(source,output,{('hair_lod0',0):entry})
                document,blob=rlglb.read(str(output))
                self.assertEqual(native_fit_digest(document,blob),report['delta_content_sha256'])
                changed=copy.deepcopy(document);changed['meshes'][0]['name']='renamed_lod'
                self.assertNotEqual(native_fit_digest(changed,blob),report['delta_content_sha256'])

if __name__=='__main__':unittest.main()
