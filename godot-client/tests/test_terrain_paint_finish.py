"""Regression coverage for disjoint geographic paint recipes and real beds."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

REGIONS = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions'
sys.path[:0] = [str(REGIONS / p) for p in ('_toolkit', '_northern', '_color')]
from amberwood.mesh import Mesh
import terrain_paint as C


def mesh(points, faces):
    points = np.array(points, float)
    return Mesh(positions=points, indices=np.array(faces).ravel(),
                uvs=points[:, [0, 2]] * .28, colors=np.ones((len(points), 4)))


class TerrainPaintFinishTests(unittest.TestCase):
    def test_corner_keeps_both_layers_of_nearest_recipe_with_masks(self):
        original = mesh([[.1, 5, 3], [.9, 5, 3], [.1, 5, 4],
                         [3, 5, .1], [4, 5, .1], [3, 5, .9]], [[0, 1, 2], [3, 4, 5]])
        meshes, records, masks = {}, {}, {}
        for peer in ('west', 'south'):
            for layer in (0, 1):
                name = f'Terrain_Test_ContinentBlend_{peer}_{layer}'
                meshes[name] = original.copy()
                meshes[name].colors[:, 3] = [.4, 1, .8, .3, .6, .9] if layer else 1
                masks[name] = meshes[name].colors.copy()
                records[name] = {'bundle': peer, 'peer': peer}
        removed = C.assign_faces(meshes, records, lambda peer, q: q[:, 0] if peer == 'west' else q[:, 1])
        self.assertEqual(removed, 4)
        for name, value in meshes.items():
            expected = [0, 1, 2] if '_west_' in name else [3, 4, 5]
            np.testing.assert_array_equal(value.indices, expected)
            np.testing.assert_array_equal(value.colors, masks[name])
            np.testing.assert_array_equal(value.positions, original.positions)
            np.testing.assert_array_equal(value.uvs, original.uvs)

    def test_nearest_finite_edge_and_stable_tie(self):
        original = mesh([[0, 0, 8], [.5, 0, 8], [0, 0, 8.5]], [[0, 1, 2]])
        meshes = {'z': original.copy(), 'a': original.copy()}
        records = {n: {'bundle': n, 'peer': n} for n in meshes}
        # The infinite line of a is closer, but its actual short segment ends
        # at z=1; z is the actual nearby common edge at z=7.
        def distance(peer, q):
            return np.hypot(q[:, 0], q[:, 1] - 1) if peer == 'a' else abs(q[:, 1] - 7)
        C.assign_faces(meshes, records, distance)
        self.assertEqual(meshes['z'].triangle_count, 1)
        self.assertEqual(meshes['a'].triangle_count, 0)
        meshes = {'z': original.copy(), 'a': original.copy()}
        C.assign_faces(meshes, records, lambda peer, q: np.ones(len(q)))
        self.assertEqual(meshes['a'].triangle_count, 1)
        self.assertEqual(meshes['z'].triangle_count, 0)

    def test_collapsed_collar_uses_actual_substrate_and_prunes_nested_copy(self):
        base = mesh([[0, 10, 0], [4, 12, 0], [0, 14, 4]], [[0, 1, 2]])
        paint = mesh([[1, 40, 1], [2, 40, 1], [1, 40, 2], [100, 40, 100]], [[0, 1, 2]])
        names = [f'Terrain_Test_StreamCollar_road_{layer}_StreamCell_road' for layer in ('Turf', 'Frost', 'Road')]
        nested = 'Terrain_Test_StreamCollar_other_Turf_StreamCollar_road_Turf'
        b = SimpleNamespace(terrain_meshes={'Terrain_Test': base, 'Walk_Native': base.copy(),
            **{n: paint.copy() for n in names}, nested: paint.copy()},
            water_meshes={'Water_Channel': base.copy()}, notes=[],
            streaming_borders=[{'sceneNodes': names + [nested, 'Walk_Native']}])
        physical = {n: (m.positions.copy(), m.indices.copy()) for n, m in b.terrain_meshes.items() if n in ('Terrain_Test', 'Walk_Native')}
        plan = {'connections': [{'id': 'road', 'ends': [{'region': 'grey_moors'}, {'region': 'manymouth_delta'}]}]}
        with patch.object(C.G, 'plan', return_value=plan), patch.object(C.G, 'boundary_sample', side_effect=lambda region, q, **kw: (np.ones(len(q)), np.zeros(len(q)))):
            C.apply(b, 'grey_moors')
            before_second = {n: m.positions.copy() for n, m in b.terrain_meshes.items()}
            C.apply(b, 'grey_moors')
        for i, n in enumerate(names):
            np.testing.assert_allclose(b.terrain_meshes[n].positions[:3, 1], np.array([11.5, 12, 12.5]) + .002 * (i + 1))
            np.testing.assert_array_equal(b.terrain_meshes[n].colors, paint.colors)
            np.testing.assert_array_equal(b.terrain_meshes[n].uvs, paint.uvs)
        self.assertNotIn(nested, b.terrain_meshes)
        self.assertNotIn(nested, b.streaming_borders[0]['sceneNodes'])
        self.assertIn('Walk_Native', b.streaming_borders[0]['sceneNodes'])
        for n, (positions, indices) in physical.items():
            np.testing.assert_array_equal(b.terrain_meshes[n].positions, positions)
            np.testing.assert_array_equal(b.terrain_meshes[n].indices, indices)
        for n in before_second:
            np.testing.assert_array_equal(b.terrain_meshes[n].positions, before_second[n])
        np.testing.assert_array_equal(b.water_meshes['Water_Channel'].positions, base.positions)

    def test_scene_cell_names_keep_one_continent_bundle(self):
        record = C.paint_record('Terrain_Test_StreamCell_corner_ContinentBlend_four_gates_1_StreamCell_second', {}, 'crownwater')
        self.assertEqual(record['bundle'], 'four_gates')
        self.assertAlmostEqual(record['bias'], .020)
        self.assertIsNone(C.paint_record('Walk_ContinentRoad_test', {}, 'crownwater'))


if __name__ == '__main__':
    unittest.main()
