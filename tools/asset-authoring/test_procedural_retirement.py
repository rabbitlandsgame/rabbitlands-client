"""Current retirement manifest and imported-model compatibility regressions."""
from pathlib import Path
import importlib
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))


class ProceduralRetirementTests(unittest.TestCase):
    def test_retired_models_have_no_active_file_or_loadable_registry_scene(self):
        index = json.loads((ROOT / 'godot-client/data/assets/retired_procedural_models.json').read_text())
        paths = {'res://assets/' + p for p in index['runtimePaths']}
        for path in paths:
            self.assertFalse((ROOT / 'godot-client' / path.removeprefix('res://')).exists(), path)
        for name in ['actors/models.json', 'actors/equipment.json', 'world/objects.json']:
            data = json.loads((ROOT / 'godot-client/data' / name).read_text())
            def walk(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key in ['scene', 'animationLibrary', 'rangedAnimationScene']:
                            self.assertNotIn(item, paths)
                        walk(item)
                elif isinstance(value, list):
                    for item in value: walk(item)
            walk(data)

    def test_bear_selection_uses_updated_models(self):
        data = json.loads((ROOT / 'eloria-assets/source/model-development-roster.json').read_text())
        available = {r['id'] for r in data['creatures']}
        self.assertTrue({'moss_bear', 'obsidian_bear', 'crystal_polar_bear', 'owlbear'} <= available)
        self.assertTrue({'black_bear', 'ice_bear'}.isdisjoint(available))
        models = json.loads((ROOT / 'godot-client/data/actors/models.json').read_text())
        index = json.loads((ROOT / 'godot-client/data/assets/retired_procedural_models.json').read_text())
        self.assertTrue({'black_bear', 'ice_bear'}.isdisjoint(models['models']))
        self.assertTrue({'215', '233'}.isdisjoint(models['actorTypes']))
        self.assertTrue({215, 233} <= set(index['retiredActorTypes']))
        self.assertTrue(set(index['retiredActorModels']).isdisjoint(models['models']))
        equipment = json.loads((ROOT / 'godot-client/data/actors/equipment.json').read_text())
        self.assertTrue(set(index['retiredEquipmentKeys']).isdisjoint(equipment['models']))

    def test_old_writers_refuse_outputs_but_imported_model_tools_still_import(self):
        native = importlib.import_module('build_native_nymara_glbs')
        equipment = importlib.import_module('equipment_authoring')
        importlib.import_module('conform_equipment')
        importlib.import_module('rebase_race_body')
        temporary_root = ROOT / '.local/asset-authoring/working/retirement-test-temporary'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.assertTrue(temporary_root.resolve().is_relative_to(ROOT.resolve()))
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(temporary_root.resolve()))
            path = Path(folder) / 'retired.glb'
            for builder in [native.GLB(), equipment.EquipmentGLB()]:
                with self.assertRaisesRegex(RuntimeError, 'retired'):
                    builder.write(path)
                self.assertFalse(path.exists())
            # The same shared writer remains useful to imported geometry.
            allowed = equipment.EquipmentGLB(generator='Eloria conform_equipment')
            allowed.write(path)
            self.assertEqual(path.read_bytes()[:4], b'glTF')


if __name__ == '__main__':
    unittest.main()
