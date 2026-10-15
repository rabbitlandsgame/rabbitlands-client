"""Local paint coverage, shared-line and physical preservation contracts."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

import corner_paint as P
import corner_material as C
from PIL import Image
from amberwood import mesh as M


class CornerPaintTests(unittest.TestCase):
    def test_original_mask_semantics_on_common_line_and_outside_corner(self):
        xz = np.array([[197., -201.], [185., -201.], [197., -181.]])
        distances = np.array([[0., .1, 2.], [1., 1., 1.], [1., 1., 1.]])
        np.testing.assert_array_equal(P.coverage(xz, distances, 'mirrorhold'), np.ones(3))
        xz = np.tile([197., -201.], (101, 1))
        depth = np.linspace(P.COMMON_LINE_KEEP, P.COMMON_LINE_KEEP+.75, 101)
        distances = np.column_stack((depth, depth+.1, depth+3.))
        values = P.coverage(xz, distances, 'mirrorhold')
        self.assertEqual(values[0], 1)
        self.assertEqual(values[-1], 0)
        self.assertLess(np.abs(np.diff(values)).max(), .016)

    def test_recipe_boundary_fades_continuously_without_new_overlap(self):
        xz = np.tile([197., -201.], (401, 1))
        advantage = np.linspace(0, 4, 401)
        distances = np.column_stack((np.ones(401), 1+advantage, np.full(401, 9)))
        values = P.coverage(xz, distances, 'mirrorhold')
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 1)
        self.assertTrue((np.diff(values) >= 0).all())
        self.assertLess(np.abs(np.diff(values)).max(), .008)

    def test_refinement_retains_literal_plane_uv_and_upward_winding(self):
        mesh = M.quad([[190, 1, -204], [190, 2, -202], [192, 3, -202], [192, 2, -204]])
        mesh.colors = np.ones((len(mesh.positions), 4))
        if mesh.normals[:, 1].mean() < 0:
            mesh.flip_winding()
        result = P.refine(mesh)
        triangles = result.positions[result.indices.reshape(-1, 3)]
        normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        self.assertTrue((normals[:, 1] > 0).all())
        np.testing.assert_allclose(result.positions[:, 1],
                                   1+(result.positions[:, 0]-190)/2+(result.positions[:, 2]+204)/2)
        self.assertAlmostEqual(normals[:, 1].sum()/2, 4)
        self.assertLessEqual(max(np.linalg.norm(triangles[:, (i+1)%3]-triangles[:, i], axis=1).max()
                                for i in range(3)), P.MAX_PAINT_EDGE+1e-9)

    def test_only_selected_paint_changes_and_original_mask_is_clipped(self):
        mesh = M.quad([[190, 4, -204], [190, 4, -194], [200, 4, -194], [200, 4, -204]],
                      material='amethyst_barrens_dust_ground')
        mesh.colors = np.ones((len(mesh.positions), 4))
        mesh.colors[:, 3] = .2+.06*(mesh.positions[:, 0]-190)
        mesh.uvs = mesh.positions[:, [0, 2]] * .28
        name = 'Terrain_Meadow_ContinentBlend_amethyst_barrens_0'
        ground, road, water = mesh.copy(), mesh.copy(), mesh.copy()
        build = SimpleNamespace(terrain_meshes={name: mesh, 'Terrain_Meadow': ground, 'Walk_Native': road},
            water_meshes={'Water_Lake': water}, placements=[{'name': 'unchanged'}], notes=[],
            streaming_borders=[{'id': 'shared', 'anchor': [0, 4, 0], 'sceneNodes': [name, 'Walk_Native']}],
            geographic_paint_finish={'version': 1})
        before = deepcopy((ground, road, water, build.placements))
        with patch.object(P.C.G, 'boundary_sample', side_effect=lambda region, xz, **kw:
                          (np.full(len(xz), {'mirrorhold': 2., 'amethyst_barrens': 2.1, 'sunmane_steppe': 9.}[kw['peer']]), None)):
            report = P.apply(build)
        self.assertEqual(report['physicalMeshesChanged'], 0)
        self.assertEqual(report['paintHeightChanges'], 0)
        for old, new in zip(before[:3], (ground, road, water)):
            for field in ('positions', 'indices', 'normals', 'uvs', 'colors'):
                np.testing.assert_array_equal(getattr(old, field), getattr(new, field))
        self.assertEqual(build.placements, before[3])
        soft = build.terrain_meshes[name+'_CornerBlend']
        self.assertGreaterEqual(soft.positions[:, 0].min(), 195-1e-8)
        np.testing.assert_array_equal(soft.positions[:, 1], np.full(len(soft.positions), 4))
        self.assertEqual(soft.material, 'four_corner_blend_amethyst_barrens_amethyst_barrens_dust')
        np.testing.assert_array_equal(soft.colors[:, 3], np.ones(len(soft.positions)))
        np.testing.assert_allclose(soft.uvs, (soft.positions[:, [0, 2]]-[186, -213])/[25, 32])
        self.assertIn(name+'_CornerBlend', build.streaming_borders[0]['sceneNodes'])
        self.assertIs(P.apply(build), report)

    def test_bake_is_linear_light_with_normalized_normals(self):
        def source(rgb, normal):
            return {'albedo': Image.new('RGB', (1, 1), rgb),
                    'normal': Image.new('RGB', (1, 1), normal),
                    'orm': Image.new('RGB', (1, 1), (255, 128, 0)), 'roughnessFactor': .5}
        recipe = {'peer': 'mirrorhold', 'baseMaterial': 'a', 'paintMaterial': 'b',
                  'baseUv': [[1, 0], [0, 1], [0, 0]], 'paintUv': [[1, 0], [0, 1], [0, 0]]}
        design = np.array([[[0., 0., 1.]]])
        with patch.object(C, 'field', return_value=(design, {'mirrorhold': np.full((1, 1, 1), .5)})):
            images = C.bake(recipe, {'a': source((0, 0, 0), (128, 128, 255)),
                                     'b': source((255, 255, 255), (255, 128, 128))})
        np.testing.assert_array_equal(np.asarray(images['albedo']), np.full((1, 1, 3), 188))
        normal = np.asarray(images['normal'], dtype=float)[0, 0]/255*2-1
        self.assertAlmostEqual(np.linalg.norm(normal), 1., delta=.006)
        self.assertEqual(np.asarray(images['orm'])[0, 0, 1], 64)

    def test_only_baked_nonperiodic_images_are_clamped(self):
        original = {'wrapS': 10497, 'wrapT': 10497, 'minFilter': 9987}
        builder = SimpleNamespace(_samplers=[deepcopy(original)],
            _textures=[{'source': 0, 'sampler': 0}, {'source': 4, 'sampler': 0}, {'source': 5, 'sampler': 0}])
        C.clamp_images(builder, {4, 5})
        self.assertEqual(builder._samplers[0], original)
        self.assertEqual(builder._textures[0]['sampler'], 0)
        for texture in builder._textures[1:]:
            self.assertEqual(texture['sampler'], 1)
            self.assertEqual(builder._samplers[1]['wrapS'], 33071)
            self.assertEqual(builder._samplers[1]['wrapT'], 33071)

    def test_uv_axes_preserve_tangent_handedness_and_reject_deformation(self):
        mesh = M.quad([[190, 4, -204], [190, 4, -194], [200, 4, -194], [200, 4, -204]])
        mesh.uvs = mesh.positions[:, [0, 2]]*.35
        fit = np.asarray(C.affine_uv(mesh))
        self.assertGreater(np.linalg.det(fit[:2]), 0)
        mesh.uvs[0, 0] += .01
        with self.assertRaisesRegex(ValueError, 'not affine'):
            C.affine_uv(mesh)
        mesh.uvs = mesh.positions[:, [2, 0]]*.35
        with self.assertRaisesRegex(ValueError, 'normal-frame'):
            C.affine_uv(mesh)


if __name__ == '__main__':
    unittest.main()
