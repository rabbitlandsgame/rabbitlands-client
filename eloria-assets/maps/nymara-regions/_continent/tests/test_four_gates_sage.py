import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import four_gates_sage as F


def world(owner=lambda x, z: 0, height=lambda x, z: 22.3):
    return SimpleNamespace(ids=['four_gates', 'mirrorhold'], owner_at=owner, height_at=height)


class FourGatesSageTests(unittest.TestCase):
    def test_six_records_are_pinned_with_their_layout_beside_the_arrival(self):
        w = world(); content = SimpleNamespace()
        report = F.prepare_four_gates_sage(w, content)
        self.assertEqual(len(content.authored_server_points), 6)
        for tile, (x, z) in F.AUTHORED_POINTS.items():
            point = content.authored_server_points[('four_gates', tile)]
            self.assertEqual([point[0], point[2]], [x, z])
            self.assertAlmostEqual(point[1], 22.3)
            # Published Four Gates frame: 48 tiles or less from the arrival (309,163).
            tile_x, tile_y = x - .5 + 310 - 530, 164 - z - .5 + 840
            self.assertLessEqual(max(abs(tile_x - 309), abs(tile_y - 163)), 54)
        # The compact layout survives: pairwise offsets equal the compact ones.
        compact = list(F.AUTHORED_POINTS)
        for a in compact:
            for b in compact:
                dx = (F.AUTHORED_POINTS[a][0] - F.AUTHORED_POINTS[b][0]) - (a[0] - b[0])
                dz = (F.AUTHORED_POINTS[a][1] - F.AUTHORED_POINTS[b][1]) + (a[1] - b[1])
                self.assertLess(abs(dx), 1.01); self.assertLess(abs(dz), 1.01)
        self.assertEqual(set(report['authoredPoints']), {str(list(t)) for t in F.AUTHORED_POINTS})
        self.assertIs(w.four_gates_sage, report)

    def test_points_outside_four_gates_or_under_water_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside its territory'):
            F.prepare_four_gates_sage(world(owner=lambda x, z: 1), SimpleNamespace())
        with self.assertRaisesRegex(ValueError, 'not dry ground'):
            F.prepare_four_gates_sage(world(height=lambda x, z: .3), SimpleNamespace())

    def test_heights_follow_the_final_terrain(self):
        w = world(); content = SimpleNamespace()
        F.prepare_four_gates_sage(w, content)
        w.height_at = lambda x, z: 23.9
        F.refresh_four_gates_sage_heights(w, content)
        for tile in F.AUTHORED_POINTS:
            self.assertAlmostEqual(content.authored_server_points[('four_gates', tile)][1], 23.9)
            self.assertAlmostEqual(w.four_gates_sage['authoredPoints'][str(list(tile))][1], 23.9)
        w.height_at = lambda x, z: .1
        with self.assertRaisesRegex(ValueError, 'not dry ground'):
            F.refresh_four_gates_sage_heights(w, content)

    def test_other_territories_are_untouched(self):
        w = SimpleNamespace(ids=['mirrorhold'])
        self.assertEqual(F.prepare_four_gates_sage(w, SimpleNamespace()), {})


if __name__ == '__main__':
    unittest.main()
