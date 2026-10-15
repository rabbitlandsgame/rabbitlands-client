"""Current source dependencies cannot be silently omitted from certificates."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

CLIENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CLIENT / 'eloria-assets/tools'))
import rebuild_continent_geography as R


class ContinentGeometryDependencyTests(unittest.TestCase):
    def test_shared_continent_rebuild_guard_precedes_all_legacy_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regions = root / 'regions'
            regions.mkdir()
            (regions / 'continent-geography.json').write_text(json.dumps({'geometryMode': 'continent-chunks-v1'}))
            artifacts = root / 'artifacts'
            arguments = ['rebuild_continent_geography.py', '--server', str(root/'server'),
                         '--data', str(root/'maps'), '--artifacts', str(artifacts)]
            with patch.object(R, 'REGIONS', regions), patch.object(sys, 'argv', arguments), patch.object(R, 'geometry') as build:
                with self.assertRaisesRegex(SystemExit, 'build_pipeline.py'):
                    R.main()
                build.assert_not_called()
            self.assertFalse(artifacts.exists())

    def test_new_dependency_absent_from_old_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new = root / 'native.py', root / 'new_color.py'
            old.write_text('native')
            new.write_text('color')
            inputs = {'native.py': hashlib.sha256(old.read_bytes()).hexdigest()}
            manifest = root / 'world.json'
            manifest.write_text(json.dumps({'authoredGeometry': {'inputs': inputs}}))
            with patch.object(R, 'CLIENT', root), patch.object(R, 'package', return_value=root), patch.object(R, 'geometry_sources', return_value=[old, new]):
                with self.assertRaisesRegex(ValueError, 'input set changed.*new_color.py'):
                    R.validate_geometry_inputs(['test'])
                inputs['new_color.py'] = hashlib.sha256(new.read_bytes()).hexdigest()
                manifest.write_text(json.dumps({'authoredGeometry': {'inputs': inputs}}))
                R.validate_geometry_inputs(['test'])
                new.write_text('changed')
                with self.assertRaisesRegex(ValueError, 'geometry input changed'):
                    R.validate_geometry_inputs(['test'])

    def test_color_dependency_is_limited_to_explicit_regional_finishes(self):
        expected = {'crownwater', 'four_gates', 'manymouth_delta', 'ssarathi_ruins',
                    'grey_moors', 'sunmane_steppe', 'amberwood', 'verdant_stair'}
        for region in R.BUILDERS:
            color = [p for p in R.geometry_sources(region) if p.parent.name == '_color']
            self.assertEqual(bool(color), region in expected, region)
            if color:
                self.assertEqual([p.name for p in color], ['terrain_paint.py'])


if __name__ == '__main__':
    unittest.main()
