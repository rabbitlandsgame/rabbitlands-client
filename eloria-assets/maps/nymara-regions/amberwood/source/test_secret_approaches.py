"""Guarded real-ground contracts for the three repaired secret approaches."""
from pathlib import Path
import json
import sys
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parent / '_toolkit'))
import glb_reader as G
from verify_runtime import VerticalRayIndex


class SecretApproaches(unittest.TestCase):
    def test_authored_standing_posts_have_real_actor_support(self):
        grid, manifest = G.read_grid(PACKAGE)
        doc, blob = G.load(PACKAGE / 'world.glb')
        ground = VerticalRayIndex(G.triangles(doc, blob, [i for i, n in enumerate(doc['nodes'])
            if 'mesh' in n and n.get('name', '').startswith(('Terrain_', 'Walk_'))
            and '_StreamThreshold_' not in n.get('name', '')]), cell=4)
        # The actual guard records authoritative actor-centre support; the
        # region-wide primary-arrival/selection proof also runs in audit_final.
        self.assertIn('actorSurfaceGuard', manifest['collision'])
        frame = manifest['continentGeography']
        authored = json.loads((PACKAGE.parent / 'continent-geography.json').read_text())['regions']['amberwood']
        self.assertEqual(frame['nativeServerOrigin'], [116, 116])
        self.assertEqual(frame['nativeServerCells'], [384, 384])
        self.assertEqual(frame['serverOrigin'], authored['serverOrigin'])
        self.assertEqual(frame['serverCells'], authored['serverCells'])
        origin_x, origin_y = frame['serverOrigin']
        for identity in ('amber-stone-ring-well', 'amber-waystone', 'amber-smuggle-mouth'):
            entry = next(e for e in manifest['interactives'] if e.get('secret') == identity)
            x, y = entry['serverTile']
            self.assertTrue(grid[2*y-1:2*y+1, 2*x-1:2*x+1].all(), identity)
            self.assertIsNotNone(ground.top_hit(x+.5-origin_x, origin_y-y-.5), identity)


if __name__ == '__main__':
    unittest.main()
