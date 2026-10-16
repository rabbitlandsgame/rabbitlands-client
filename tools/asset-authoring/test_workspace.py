import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('asset_workspace',Path(__file__).with_name('workspace.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Relocation(unittest.TestCase):
    def test_known_prefix_only_and_slash_styles(self):
        rules=[('C:/old-project','D:/new/authoring'),('C:\\old-project','D:\\new\\authoring')]
        text='C:/old-project/models/a.glb C:\\old-project\\tools\\rig.py C:/other/a.glb'
        self.assertEqual(module.relocate_text(text,rules),
                         'D:/new/authoring/models/a.glb D:\\new\\authoring\\tools\\rig.py C:/other/a.glb')

    def test_profile_values_hashes_and_timing_preserved(self):
        value={'source_glb':'C:/old-project/actor.glb','source_sha256':'0123',
               'times_seconds':[0,.125,1.], 'parameters':[[1,2],[3,4]],
               'roles':{'jaw':'Bone_051'},'nested':[{'path':'C:/old-project/video.mp4'}]}
        result=module.relocate_json(value,[('C:/old-project','D:/authoring')])
        self.assertEqual(result['source_glb'],'D:/authoring/actor.glb')
        self.assertEqual(result['nested'][0]['path'],'D:/authoring/video.mp4')
        for key in ['source_sha256','times_seconds','parameters','roles']:
            self.assertEqual(value[key],result[key])
        self.assertEqual(value['source_glb'],'C:/old-project/actor.glb')

    def test_relative_source_rebased_when_profile_moves(self):
        original=Path(__file__).parent
        result=module.relocate_json({'source_glb':'../actor.glb'},[],original)
        self.assertEqual(Path(result['source_glb']),(original/'../actor.glb').resolve())

    def test_similar_directory_name_is_not_the_known_root(self):
        self.assertEqual(module.relocate_text('C:/old-project-other/model.glb',
            [('C:/old-project','D:/authoring')]),'C:/old-project-other/model.glb')


if __name__=='__main__':unittest.main()
