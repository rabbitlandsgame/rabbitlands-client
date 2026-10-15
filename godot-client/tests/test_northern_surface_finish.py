"""Physical regressions for paint layered over a sculpted mountain pass."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

REGIONS = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions'
sys.path[:0] = [str(REGIONS / '_toolkit'), str(REGIONS / '_northern')]
from amberwood.mesh import Mesh
import landscape_finish as F


def triangle(points):
    mesh = Mesh(positions=np.asarray(points, float), indices=np.array([0, 2, 1]),
                uvs=np.array([[.1, .2], [.3, .4], [.5, .6]]),
                colors=np.array([[.9, .8, .7, .6]] * 3))
    mesh.recompute_normals(180)
    return mesh


class NorthernSurfaceFinishTests(unittest.TestCase):
    def test_paint_follows_real_triangle_after_clamp_without_changing_masks(self):
        base = triangle([[0, 90, 0], [4, 90, 0], [0, 90, 4]])
        # All paint vertices are newly clipped points inside the base face.
        paint = triangle([[1, 90.008, 1], [2, 90.008, 1], [1, 90.008, 2]])
        name = 'Terrain_Rock_StreamCollar_north_Turf_StreamCell_north'
        duplicate = 'Terrain_Rock_StreamCollar_south_Road_StreamCollar_north_Turf_StreamCell_north'
        masks, uvs, indices = paint.colors.copy(), paint.uvs.copy(), paint.indices.copy()
        build = SimpleNamespace(terrain_meshes={'Terrain_Rock_StreamCell_north': base,
                                name: paint, duplicate: paint.copy()},
                                streaming_borders=[{'id': 'causeway'}, {'id': 'south'}, {'id': 'north',
                                    'sceneNodes': [name, duplicate]}], notes=[])
        def sculpt(build, region):
            self.assertEqual(len(build.terrain_meshes), 1)
            base.positions[:, 1] = [10., 12., 14.]
        with patch.object(F, 'refresh'), patch.object(F.northern_passes, 'apply', side_effect=sculpt):
            F.apply(build, 'mirrorhold')
        np.testing.assert_allclose(paint.positions[:, 1], [11.508, 12.008, 12.508])
        np.testing.assert_array_equal(paint.colors, masks)
        np.testing.assert_array_equal(paint.uvs, uvs)
        np.testing.assert_array_equal(paint.indices, indices)
        self.assertNotIn(duplicate, build.terrain_meshes)
        self.assertEqual(build.streaming_borders[2]['sceneNodes'], [name])

    def test_all_direct_layers_have_distinct_offsets_below_the_road(self):
        slots = {'a': 0, 'b': 1, 'c': 2}
        offsets = [F.paint_bias(f'Terrain_Rock_StreamCollar_{road}_{kind}', slots)
                   for road in slots for kind in ('Turf', 'Frost', 'Road')]
        self.assertEqual(len(set(offsets)), 9)
        self.assertGreater(min(offsets), 0)
        self.assertLess(max(offsets), .03)
        peers = ['amethyst_barrens', 'four_gates', 'sunmane_steppe', 'whitehorn_range']
        blends = [F.paint_bias(f'Terrain_Rock_ContinentBlend_{peer}_{index}', slots, peers)
                  for peer in peers for index in (0, 1)]
        self.assertEqual(len(set(blends)), len(blends))
        self.assertLess(max(blends), .03)
        self.assertGreater(min(blends), max(offsets))

    def test_missing_underlying_geometry_is_rejected(self):
        sampler = F.Substrate([triangle([[0, 0, 0], [1, 0, 0], [0, 0, 1]])])
        with self.assertRaisesRegex(ValueError, 'no substrate'):
            sampler.sample(np.array([[8., 8.]]))


if __name__ == '__main__':
    unittest.main()
