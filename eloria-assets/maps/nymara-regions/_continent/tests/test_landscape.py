"""Geographic contracts for one continent evaluated before chunking."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("diagonal_landscape", SOURCE / "landscape.py")
landscape = importlib.util.module_from_spec(spec)
spec.loader.exec_module(landscape)


class ContinentGeographyTests(unittest.TestCase):
    def test_broadcast_and_scalar_results_are_identical(self):
        x = np.array([170, 510, 950, 1200])
        z = np.array([420, 650, 840])[:, None]
        grid = landscape.height_at(x, z)
        self.assertEqual(grid.shape, (3, 4))
        for row in range(3):
            for col in range(4):
                self.assertAlmostEqual(grid[row, col], float(landscape.height_at(x[col], z[row, 0])), places=11)

    def test_export_splits_do_not_change_height_or_color(self):
        # Independent neighbouring mesh builds must produce the same shared edge.
        z = np.arange(320, 760, 4)
        west_x = np.arange(200, 604, 4)
        east_x = np.arange(600, 1004, 4)
        west_h = landscape.height_at(west_x[None, :], z[:, None])
        east_h = landscape.height_at(east_x[None, :], z[:, None])
        np.testing.assert_array_equal(west_h[:, -1], east_h[:, 0])
        west_rgb = landscape.terrain_color(west_x[None, :], z[:, None], west_h)
        east_rgb = landscape.terrain_color(east_x[None, :], z[:, None], east_h)
        np.testing.assert_array_equal(west_rgb[:, -1], east_rgb[:, 0])

    def test_material_weights_are_normalized_and_finite(self):
        x, z = np.meshgrid(np.arange(0, 1501, 35), np.arange(0, 1681, 35))
        h = landscape.height_at(x, z)
        weights = landscape.biome_weights(x, z, h)
        np.testing.assert_allclose(sum(weights.values()), 1.0, atol=1e-12)
        rgb = landscape.terrain_color(x, z, h)
        self.assertTrue(np.isfinite(h).all() and np.isfinite(rgb).all())
        self.assertTrue(((rgb >= 0) & (rgb <= 1)).all())
        self.assertGreater(float(h.max()), 130)
        self.assertLess(float(h.min()), 0)

    def test_water_profiles_descend_and_confluences_match(self):
        rivers = {r["id"]: r for r in landscape.load_plan()["rivers"]}
        for river in rivers.values():
            p = np.array(river["points"])
            self.assertTrue((np.diff(p[:, 2]) <= 0).all(), river["id"])
            self.assertTrue((p[:, 2] >= 0).all(), river["id"])
            if river.get("mouth") == "sea" or river.get("delta"):
                self.assertEqual(p[-1, 2], 0)
            if "joins" in river:
                self.assertIn(river["points"][-1], rivers[river["joins"]]["points"])
            if "joins_from" in river:
                self.assertTrue(river.get("delta"), "Upstream branching belongs only in the delta")
                self.assertIn(river["points"][0], rivers[river["joins_from"]]["points"])
            curve = landscape.curved_points(river["points"])
            for a, b in zip(curve[:-1], curve[1:]):
                points = a + np.linspace(0, 1, 25)[:, None] * (b - a)
                h = landscape.height_at(points[:, 0], points[:, 1])
                self.assertTrue((h < points[:, 2] - 0.1).all(), river["id"])

    def test_coastal_shelf_and_southwestern_archipelago(self):
        self.assertLess(float(landscape.height_at(-80, 700)), -5)
        self.assertLess(float(landscape.height_at(1570, 700)), -5)
        # The retained causeway islands now occupy the former (190,1410)
        # control. This surveyed point remains in the open western sound.
        self.assertLess(float(landscape.height_at(140, 1390)), -5)
        island=next(i for i in landscape.load_plan()['islands'] if i.get('crownSourceIsland')=='crown_isle')
        self.assertGreater(float(landscape.height_at(*island['center'])), 5)
        # Only the lower river creates its floodplain; the pass remains high.
        self.assertGreater(float(landscape.height_at(840, 650)), float(landscape.height_at(530, 840)) + 35)

    def test_climate_crosses_territory_boundaries_gradually(self):
        forest = landscape.biome_weights(490, 550)
        steppe = landscape.biome_weights(1170, 700)
        mineral = landscape.biome_weights(1000, 380)
        self.assertGreater(float(forest["woodland"]), float(steppe["woodland"]))
        self.assertGreater(float(steppe["steppe"]), float(forest["steppe"]))
        self.assertGreater(float(mineral["badland"]), float(steppe["badland"]))
        # Materials have no sudden rectangles, even through the old forest edge.
        x = np.linspace(350, 1000, 651)
        rgb = landscape.terrain_color(x, np.full_like(x, 590))
        self.assertLess(float(np.max(np.linalg.norm(np.diff(rgb, axis=0), axis=1))), 0.035)

    def test_a_relief_source_may_lower_the_snowline_over_its_own_ground(self):
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]), np.full((3, 3), 50.))
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            source = {"samples": "x.npz", "translation": [500., 0., 300.], "crop": [-10, -300, 10, -100],
                      "feather": 40, "snowline_drop": 45.}
            plan = dict(landscape.load_plan(), relief_sources=[source])
            inside = float(landscape.snowline_at(500., 100., plan))
            far = float(landscape.snowline_at(500., 700., plan))
            between = float(landscape.snowline_at(500., 220., plan))     # 20 m outside the crop
            plain = float(landscape.snowline_at(500., 100., dict(plan, relief_sources=[])))
            self.assertAlmostEqual(inside, plain - 45., places=6)
            self.assertAlmostEqual(far, 131 + float(landscape.smoothstep(250, 850, 700.)) * 82, places=6)
            self.assertTrue(plain - 45. < between < plain)
            # A source without the key changes nothing.
            self.assertAlmostEqual(float(landscape.snowline_at(500., 100., dict(plan, relief_sources=[dict(source, snowline_drop=0.)]))), plain, places=6)

    def test_relief_source_and_retained_transform_share_one_squeeze(self):
        transform = {"translation": [477., 70., 272.], "squeeze_z": .85, "about_z": 60.}
        # x is translated; z is squeezed about source row 60 and translated: 272 + 60 + (z - 60) * .85.
        np.testing.assert_allclose(landscape.retained_map_xz(transform, [[70., 40.], [76., -192.]]), [[547., 315.], [553., 117.8]])
        np.testing.assert_allclose(landscape.retained_map_xz([477., 70., 272.], [70., 40.]), [547., 312.])
        translation, scale, about = landscape.retained_affine(transform)
        self.assertEqual((translation.tolist(), scale.tolist(), about.tolist()), ([477., 70., 272.], [1., .85], [0., 60.]))
        with self.assertRaisesRegex(ValueError, "squeeze_z"):
            landscape.retained_affine({"translation": [0, 0, 0], "squeeze_z": 0.})
        with self.assertRaisesRegex(ValueError, "three finite metres"):
            landscape.retained_affine([1., 2.])
        # A relief source with the same squeeze samples its rows where the transform put them.
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]), np.array([[10.] * 3, [20.] * 3, [30.] * 3]))
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            source = {"samples": "x.npz", "translation": [477., 70., 272.], "crop": [-10, -300, 10, -100], "feather": 10,
                      "squeeze_z": .85, "about_z": 60.}
            height, weight = landscape._relief_height(np.array([477.]), np.array([111.]), source)   # row -200 -> 332 - 221
            self.assertAlmostEqual(float(height[0]), 20. + 70., places=6)
            self.assertEqual(float(weight[0]), 1.)
            height, _ = landscape._relief_height(np.array([477.]), np.array([72.]), dict(source, squeeze_z=1., about_z=0.))
            self.assertAlmostEqual(float(height[0]), 20. + 70., places=6)

    def test_relief_knee_lowers_the_rim_and_leaves_the_floor(self):
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]), np.array([[178.] * 3, [70.] * 3, [40.] * 3]))
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            source = {"samples": "x.npz", "translation": [0., 0., 0.], "crop": [-10, -300, 10, -100], "feather": 10,
                      "knee": 70., "above_scale": .4, "knee_width": 10.}
            z = np.array([-300., -200., -100.]); x = np.zeros(3)
            height, _ = landscape._relief_height(x, z, source)
            # The crown keeps 40 % of its rise above the knee, the knee row and the floor are untouched.
            np.testing.assert_allclose(height, [70. + 108. * .4, 70., 40.])
            # Compressed heights stay in order: a taller row is still taller.
            fine = (np.array([-10., 0., 10.]), np.linspace(-300., -100., 41), np.tile(np.linspace(178., 40., 41)[:, None], (1, 3)))
        with patch.object(landscape, "_relief_samples", lambda name: fine):
            height, _ = landscape._relief_height(np.zeros(41), np.linspace(-300., -100., 41), source)
            self.assertTrue(np.all(np.diff(height) < 0.))
            without, _ = landscape._relief_height(np.zeros(41), np.linspace(-300., -100., 41), dict(source, knee=None))
            np.testing.assert_allclose(without, np.linspace(178., 40., 41))

    def test_relief_outline_traces_the_crop_through_the_retained_transform(self):
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]), np.zeros((3, 3)))
        crop = [[-8., -280.], [6., -280.], [6., -140.], [-8., -140.]]
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            flat = {"samples": "x.npz", "translation": [477., 70., 272.], "crop": [-8, -280, 6, -140]}
            np.testing.assert_allclose(landscape.relief_outline(flat), landscape.retained_map_xz([477., 70., 272.], crop))
            squeezed = dict(flat, squeeze_z=.85, about_z=60.)
            corners = landscape.relief_outline(squeezed)
            np.testing.assert_allclose(corners, landscape.retained_map_xz(squeezed, crop))
            # x0z0, x1z0, x1z1, x0z1: translated east-west, squeezed north-south about source row 60.
            self.assertEqual([corner[0] for corner in corners], [469., 469. + 14., 469. + 14., 469.])
            np.testing.assert_allclose([corner[1] for corner in corners], [43., 43., 162., 162.])
            # Without a crop the source owns its whole sampled extent, as _relief_height reads it.
            np.testing.assert_allclose(landscape.relief_outline({"samples": "x.npz", "translation": [0., 0., 0.]}),
                                       [[-10., -300.], [10., -300.], [10., -100.], [-10., -100.]])

    def test_a_relief_source_fades_along_an_authored_mask_polygon(self):
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]),
                np.array([[10., 20., 30.], [40., 50., 60.], [70., 80., 90.]]))
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            # The crop is continent x 490..510, z 0..200; the mask keeps its northern half.
            plain = {"samples": "x.npz", "name": "probe", "translation": [500., 0., 300.],
                     "crop": [-10, -300, 10, -100], "feather": 40}
            leaf = [[490., 0.], [510., 0.], [510., 100.], [490., 100.]]
            masked = dict(plain, mask={"polygon": leaf, "feather": 20})
            x = np.array([500., 500., 500., 500., 505.])
            z = np.array([50., 110., 160., 220., 100.])
            # A source without a mask is untouched: the crop's own feather still fades it
            # over the 20 m past its z edge, and the sampled heights are unchanged.
            height, weight = landscape._relief_height(x, z, plain)
            np.testing.assert_allclose(height, [35., 53., 68., 80., 55.])
            np.testing.assert_allclose(weight, [1., 1., 1., .5, 1.])
            masked_height, masked_weight = landscape._relief_height(x, z, masked)
            np.testing.assert_allclose(masked_height, height)
            # Inside the leaf whole, half way through its feather a half, beyond it nothing.
            np.testing.assert_allclose(masked_weight, [1., .5, 0., 0., 1.])
            self.assertTrue(0. < float(masked_weight[1]) < 1.)
            # The same on a scalar and on a broadcast grid, the shapes the composer samples.
            self.assertEqual(float(landscape._relief_height(500., 50., masked)[1]), 1.)
            self.assertEqual(float(landscape._relief_height(500., 160., masked)[1]), 0.)
            gx, gz = np.meshgrid(np.array([495., 505.]), np.array([50., 160.]))
            np.testing.assert_allclose(landscape._relief_height(gx, gz, masked)[1], [[1., 1.], [0., 0.]])
            # The accessor hands the plan editor the leaf; a source without one has none.
            self.assertEqual(landscape.relief_mask_outline(masked), leaf)
            self.assertIsNone(landscape.relief_mask_outline(plain))
            for mask, complaint in (({"polygon": [[490., 0.], [510., 0.]], "feather": 20}, "at least 3"),
                                    ({"polygon": leaf, "feather": -1}, "at least 0"),
                                    ({"polygon": [[490., 0.], [510., 0.], [510., None]]}, "finite")):
                with self.assertRaisesRegex(ValueError, "probe.*" + complaint):
                    landscape._relief_height(x, z, dict(plain, mask=mask))
                with self.assertRaisesRegex(ValueError, "probe.*" + complaint):
                    landscape.relief_mask_outline(dict(plain, mask=mask))

    def test_a_masked_relief_source_lowers_the_snowline_only_under_its_leaf(self):
        rows = (np.array([-10., 0., 10.]), np.array([-300., -200., -100.]), np.full((3, 3), 50.))
        with patch.object(landscape, "_relief_samples", lambda name: rows):
            source = {"samples": "x.npz", "name": "probe", "translation": [500., 0., 300.],
                      "crop": [-10, -300, 10, -100], "feather": 40, "snowline_drop": 45.,
                      "mask": {"polygon": [[490., 0.], [510., 0.], [510., 100.], [490., 100.]], "feather": 20}}
            plan = dict(landscape.load_plan(), relief_sources=[source])
            plain = float(landscape.snowline_at(500., 50., dict(plan, relief_sources=[])))
            # snowline_at carries the source's whole weight, so the mask reaches the snow too.
            self.assertAlmostEqual(float(landscape.snowline_at(500., 50., plan)), plain - 45., places=6)
            self.assertAlmostEqual(float(landscape.snowline_at(500., 110., plan)), plain - 22.5, places=6)
            # Still inside the crop, but past the leaf and its feather: no alpine drop at all.
            self.assertAlmostEqual(float(landscape.snowline_at(500., 160., plan)), plain, places=6)
            unmasked = dict(plan, relief_sources=[{k: v for k, v in source.items() if k != "mask"}])
            self.assertAlmostEqual(float(landscape.snowline_at(500., 160., unmasked)), plain - 45., places=6)

    def test_optional_foundation_feathers_into_shared_surface(self):
        plan = copy.deepcopy(landscape.load_plan())
        target = float(landscape.height_at(740, 1030)) + 2
        plan["foundations"] = [{"center": [740, 1030], "radius": 12, "elevation": target, "feather": 28}]
        self.assertAlmostEqual(float(landscape.height_at(740, 1030, plan)), target)
        self.assertAlmostEqual(float(landscape.height_at(785, 1030, plan)), float(landscape.height_at(785, 1030)))

    def test_river_level_extension_keeps_surveyed_centreline_levels(self):
        for river in landscape.load_plan()['rivers']:
            curve=landscape.curved_points(river['points'])
            points=np.concatenate([a+np.linspace(0,1,9)[:,None]*(b-a)
                                   for a,b in zip(curve[:-1],curve[1:])])
            distance,level=landscape._polyline_field(points[:,0],points[:,1],river['points'])
            np.testing.assert_allclose(distance,0,atol=1e-10)
            np.testing.assert_allclose(level,points[:,2],atol=1e-10,err_msg=river['id'])

    def test_river_attribute_extension_has_no_segment_projection_step(self):
        river=next(r for r in landscape.load_plan()['rivers'] if r['id']=='western_river')
        # This surveyed bend previously had a half-metre height jump between
        # adjacent nearest-segment projections, visible as diagonal bank seams.
        x=np.arange(453.5,460.501,.01)
        z=np.full_like(x,414.5)
        _,level=landscape._polyline_field(x,z,river['points'])
        self.assertLess(float(np.max(np.abs(np.diff(level))))/.01,.65)

    def test_navigable_bank_has_a_low_gradual_flood_shelf(self):
        river=copy.deepcopy(next(r for r in landscape.load_plan()['rivers'] if r['id']=='western_river'))
        river['points']=[[0,-100,20],[0,100,20]]
        plan={'rivers':[river],'lakes':[]}
        x=np.arange(0,50.01,.1)
        height=landscape._drainage_height(x,np.zeros_like(x),np.full_like(x,80),plan)
        bank=(x>=river['width'])&(x<=river['width']+10)
        self.assertLess(float(np.max(np.abs(np.gradient(height,.1))[bank])),.6)
        self.assertLessEqual(float(np.max(height[bank]-20)),.65)
        self.assertTrue((np.diff(height)>=-1e-10).all())
        self.assertAlmostEqual(height[0],20-river['depth'])

    def test_cuts_relief_carves_the_legacy_relief_and_leaves_other_rivers_alone(self):
        """A "cuts_relief" river is drained after the relief sources; every other river is untouched."""
        plan=landscape.load_plan()
        source=plan['relief_sources'][0]
        carving=[r for r in plan['rivers'] if landscape.cuts_relief(r)]
        self.assertTrue(carving,'the plan should carry at least one carving river to measure')
        # Unflagged rivers: dropping the flag from every river must reproduce the one-pass ground exactly.
        plain=dict(plan,rivers=[{k:v for k,v in r.items() if k!='cuts_relief'} for r in plan['rivers']])
        x,z=np.meshgrid(np.linspace(380,700,161),np.linspace(120,560,221))
        reference=landscape._drainage_height(x,z,landscape._natural_height(x,z,plain),plain)
        for relief in plain['relief_sources']:
            height,weight=landscape._relief_height(x,z,relief)
            weight=weight*landscape.smoothstep(-8,float(relief.get('coast_feather',60.)),
                                               landscape.coastline_distance(x,z,plain))
            reference=reference*(1-weight)+height*weight
        # The authored corrections come after the relief in height_at, and the committed plan carries them
        # (the Whitehorn summit, its gate court shelf and its snowline terrace all stand inside this window),
        # so the hand-built reference has to apply them too or it is measuring a different ground.
        reference=landscape._terrain_edit_height(x,z,reference,plain)
        np.testing.assert_array_equal(landscape.height_at(x,z,plain),reference)
        # The flagged river: its bed stands a full depth under the level even where the relief's weight is 1.
        river=max(carving,key=lambda r:len(r['points']))
        points=np.array(river['points'],float)
        inside=points[np.asarray(landscape._relief_height(points[:,0],points[:,1],source)[1],float)>.99]
        self.assertTrue(len(inside),'the carving river should run inside the relief source')
        cut=np.asarray(landscape.height_at(inside[:,0],inside[:,1],plan),float)
        np.testing.assert_allclose(cut,inside[:,2]-river['depth'],atol=1e-9)
        buried=np.asarray(landscape.height_at(inside[:,0],inside[:,1],plain),float)
        self.assertGreater(float(np.max(buried-inside[:,2])),1.,'without the flag the relief buries the bed')


class AuthoredTerrainEditTests(unittest.TestCase):
    """The plan's "terrain_edits": the editor previews exactly what compose builds."""

    CENTRE = [520., 690.]

    def plan(self, *edits):
        return dict(landscape.load_plan(), terrain_edits=[dict(edit) for edit in edits])

    def ground(self, x, z):
        """The committed plan's ground with no terrain edit at all: the committed plan carries edits of its own
        (the Amberwood seat stamps stand inside this test's window), which the edits under test replace."""
        return landscape.height_at(x, z, self.plan())

    def circle(self, identity, centre=None, radius=20., **edit):
        return dict(edit, id=identity, shape={"circle": {"center": list(centre or self.CENTRE), "radius": radius}})

    def test_absent_or_empty_terrain_edits_leave_the_ground_alone(self):
        x, z = np.arange(180., 1381., 200.), np.arange(140., 1541., 230.)[:, None]
        # The committed plan may carry edits of its own; the absent key and an empty list are the same ground.
        without = copy.deepcopy(landscape.load_plan())
        without.pop("terrain_edits", None)
        ground = landscape.height_at(x, z, without)
        np.testing.assert_array_equal(landscape.height_at(x, z, dict(without, terrain_edits=[])), ground)
        np.testing.assert_array_equal(landscape.height_at(x, z, self.plan()), ground)
        # The committed plan carries no unresolved or malformed edit.
        self.assertEqual(landscape.validate_terrain_edits(landscape.load_plan()), [])

    def test_circle_raise_fills_its_shape_and_fades_over_the_feather(self):
        x, radius, feather, amount = self.CENTRE[0], 20., 8., 10.
        plan = self.plan(self.circle("knoll", op="raise", radius=radius, feather=feather, amount=amount))
        for offset, share in ((0., 1.), (radius, 1.), (radius + feather / 2, .5), (radius + feather, 0.), (90., 0.)):
            point = (x + offset, self.CENTRE[1])
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)) - float(self.ground(*point)),
                                   amount * share, places=9, msg=offset)
        # Arrays and scalars agree, as everywhere else in this module.
        grid_x = x + np.array([0., 12., 24., 40.])
        grid_z = self.CENTRE[1] + np.array([0., 6.])[:, None]
        grid = landscape.height_at(grid_x, grid_z, plan)
        self.assertEqual(grid.shape, (2, 4))
        for row in range(2):
            for column in range(4):
                self.assertAlmostEqual(grid[row, column],
                                       float(landscape.height_at(grid_x[column], grid_z[row, 0], plan)), places=11)

    def test_lower_and_flatten_share_that_weight(self):
        radius, feather = 20., 8.
        lowered = self.plan(self.circle("hollow", op="lower", radius=radius, feather=feather, amount=6.))
        flattened = self.plan(self.circle("shelf", op="flatten", radius=radius, feather=feather, target=42.))
        for offset, share in ((0., 1.), (radius + feather / 2, .5), (radius + feather, 0.)):
            point = (self.CENTRE[0] + offset, self.CENTRE[1])
            ground = float(self.ground(*point))
            self.assertAlmostEqual(float(landscape.height_at(*point, lowered)), ground - 6. * share, places=9)
            self.assertAlmostEqual(float(landscape.height_at(*point, flattened)),
                                   ground * (1 - share) + 42. * share, places=9)

    def test_polyline_band_and_polygon_boundary_measure_distance_outside(self):
        line = [[440., 640.], [600., 640.], [600., 740.]]
        plan = self.plan({"id": "berm", "op": "raise", "amount": 4., "feather": 10.,
                          "shape": {"polyline": {"points": line, "width": 12.}}})
        # The width is the whole band: half of it either side of the authored segments.
        for offset, share in ((0., 1.), (6., 1.), (11., .5), (16., 0.)):
            point = (500., 640. + offset)
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)) - float(self.ground(*point)),
                                   4. * share, places=9, msg=offset)
        square = [[380., 580.], [480., 580.], [480., 680.], [380., 680.]]
        plan = self.plan({"id": "yard", "op": "raise", "amount": 4., "feather": 10.,
                          "shape": {"polygon": {"points": square}}})
        # Zero inside however far from an edge, the boundary distance outside, and a
        # corner measured to the corner itself rather than to either edge's line.
        for point, share in (((430., 630.), 1.), ((380., 580.), 1.), ((485., 630.), .5),
                             ((483., 684.), .5), ((492., 630.), 0.)):
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)) - float(self.ground(*point)),
                                   4. * share, places=9, msg=point)

    def test_ramp_follows_its_heights_along_the_polyline_and_fades_over_the_feather(self):
        line = [[440., 640.], [500., 640.], [500., 700.]]
        plan = self.plan({"id": "ramp", "op": "ramp", "heights": [10., 40., 16.], "feather": 10.,
                          "shape": {"polyline": {"points": line, "width": 8.}}})
        # On the line: the vertex heights and the straight interpolation between them, whatever the ground was.
        for point, height in (((440., 640.), 10.), ((470., 640.), 25.), ((500., 640.), 40.), ((500., 670.), 28.),
                              ((500., 700.), 16.)):
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)), height, places=9, msg=point)
        # Across the band the surface keeps the height of the nearest point on the line, and the feather blends it
        # into the ground as any edit's weight does; beyond the first vertex the surface stays level.
        for point, height, share in (((470., 644.), 25., 1.), ((470., 649.), 25., .5), ((470., 654.), 25., 0.),
                                     ((430., 640.), 10., 1. - float(landscape.smoothstep(0., 10., 6.)))):
            ground = float(self.ground(*point))
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)), ground * (1 - share) + height * share,
                                   places=9, msg=point)
        # Arrays and scalars agree.
        xs, zs = np.array([440., 470., 500., 503.]), np.array([640., 660.])[:, None]
        grid = landscape.height_at(xs, zs, plan)
        for row in range(2):
            for column in range(4):
                self.assertAlmostEqual(grid[row, column], float(landscape.height_at(xs[column], zs[row, 0], plan)),
                                       places=11)

    def test_validate_terrain_edits_checks_a_ramps_heights(self):
        line = {"polyline": {"points": [[440., 640.], [500., 640.]], "width": 8.}}
        ramp = {"id": "ramp", "op": "ramp", "heights": [10., 20.], "feather": 4., "shape": line}
        self.assertEqual(landscape.validate_terrain_edits(self.plan(ramp)), [])
        problems = landscape.validate_terrain_edits(self.plan(
            dict(ramp, id="short", heights=[10.]), dict(ramp, id="words", heights=[10., "high"]),
            dict(ramp, id="bare", heights=None), self.circle("round", op="ramp", heights=[10.], feather=0.),
            self.circle("stray", op="raise", amount=2., heights=[1.], feather=0.)))
        for identity in ("short", "words", "bare"):
            self.assertIn("one finite height", "\n".join(p for p in problems if f"'{identity}'" in p))
        self.assertIn("runs along a polyline", "\n".join(p for p in problems if "'round'" in p))
        self.assertIn("belongs to a ramp", "\n".join(p for p in problems if "'stray'" in p))

    def test_feather_zero_is_a_hard_edge_and_strength_scales_the_effect(self):
        plan = self.plan(self.circle("pad", op="raise", radius=20., feather=0., amount=9.))
        for offset, share in ((19.999, 1.), (20., 1.), (20.001, 0.)):
            point = (self.CENTRE[0] + offset, self.CENTRE[1])
            self.assertAlmostEqual(float(landscape.height_at(*point, plan)) - float(self.ground(*point)),
                                   9. * share, places=9, msg=offset)
        for strength, share in ((1., 1.), (.25, .25), (0., 0.)):
            weak = self.plan(self.circle("pad", op="raise", radius=20., feather=8., amount=9., strength=strength))
            self.assertAlmostEqual(float(landscape.height_at(*self.CENTRE, weak))
                                   - float(self.ground(*self.CENTRE)), 9. * share, places=9)
            # The strength multiplies the weight, so the feather still halves it.
            edge = (self.CENTRE[0] + 24., self.CENTRE[1])
            self.assertAlmostEqual(float(landscape.height_at(*edge, weak)) - float(self.ground(*edge)),
                                   9. * share * .5, places=9)

    def test_edits_run_in_list_order_after_the_basins_and_before_the_foundations(self):
        raised = self.circle("lift", op="raise", feather=0., amount=25.)
        settled = self.circle("shelf", op="flatten", feather=0., target=42.)
        self.assertAlmostEqual(float(landscape.height_at(*self.CENTRE, self.plan(raised, settled))), 42., places=9)
        self.assertAlmostEqual(float(landscape.height_at(*self.CENTRE, self.plan(settled, raised))), 67., places=9)
        floor = float(self.ground(*self.CENTRE)) - 30.
        plan = self.plan(self.circle("lift", op="raise", radius=18., feather=0., amount=12.))
        plan["basins"] = [{"center": list(self.CENTRE), "radii": [40., 40.], "floor": floor, "bowl": 0.}]
        # A basin carves with a minimum: an edit applied before it would be cut back to the floor.
        self.assertAlmostEqual(float(landscape.height_at(*self.CENTRE, plan)), floor + 12., places=9)
        plan["foundations"] = [{"center": list(self.CENTRE), "radius": 10., "elevation": 5., "feather": 20.}]
        self.assertAlmostEqual(float(landscape.height_at(*self.CENTRE, plan)), 5., places=9)

    def test_height_at_refuses_an_unresolved_target_or_an_unsupported_edit(self):
        for edit, message in (
                (self.circle("shelf", op="flatten", target="mean"), "resolved to metres"),
                (self.circle("shelf", op="flatten", target=None), "must be a finite number"),
                (self.circle("blur", op="smooth", amount=1.), "unknown op"),
                (self.circle("knoll", op="raise", amount=-1.), "'amount' must lie"),
                (self.circle("knoll", op="raise", amount=1., feather=-3.), "'feather' must lie"),
                (self.circle("knoll", op="raise", amount=1., strength=1.4), "'strength' must lie"),
                ({"id": "slope", "op": "ramp", "shape": {"polyline": {"points": [[440., 640.], [500., 640.]], "width": 8.}}},
                 "one finite height"),
                (self.circle("disc", op="ramp", heights=[1.]), "runs along a polyline"),
                ({"id": "blob", "op": "raise", "amount": 1., "shape": {"blob": {"center": [0., 0.]}}}, "'shape' must hold")):
            with self.assertRaisesRegex(ValueError, message) as raised:
                landscape.height_at(*self.CENTRE, self.plan(edit))
            self.assertIn(edit["id"], str(raised.exception))

    def test_validate_terrain_edits_names_every_problem(self):
        plan = self.plan(self.circle("twin", op="raise", amount=2., feather=0.),
                         self.circle("twin", op="lower", amount=2., feather=0.),
                         {"id": "bare", "op": "raise", "amount": 2.},
                         {"id": "thin", "op": "flatten", "target": "mean",
                          "shape": {"polygon": {"points": [[400., 600.], [420., 620.]]}}},
                         {"id": "open", "op": "raise", "amount": 2., "feather": 4.,
                          "shape": {"polyline": {"points": [[400., 600.]], "width": 6.}}},
                         self.circle("astray", centre=[-40., 690.], radius=5., op="raise", amount=2., feather=5.),
                         self.circle("blur", op="smooth", amount=2., feather=0.),
                         self.circle("dot", radius=0., op="raise", amount=2., feather=0.))
        problems = landscape.validate_terrain_edits(plan)
        self.assertIn("duplicate id", "\n".join(p for p in problems if "'twin'" in p))
        self.assertEqual(len([p for p in problems if "'twin'" in p]), 1)
        self.assertIn("'shape' must hold", "\n".join(p for p in problems if "'bare'" in p))
        self.assertIn("at least 3 points", "\n".join(p for p in problems if "'thin'" in p))
        self.assertIn("at least 2 points", "\n".join(p for p in problems if "'open'" in p))
        self.assertIn("outside the plan bounds", "\n".join(p for p in problems if "'astray'" in p))
        self.assertIn("not part of v1", "\n".join(p for p in problems if "'blur'" in p))
        self.assertIn("'radius' greater than 0", "\n".join(p for p in problems if "'dot'" in p))
        # A point outside the bounds by less than its feather is inside the tolerance.
        near = self.circle("near", centre=[-4., 690.], radius=5., op="raise", amount=2., feather=5.)
        self.assertEqual(landscape.validate_terrain_edits(self.plan(near)), [])

    def test_resolve_terrain_edit_targets_measures_the_natural_ground(self):
        radius = 24.
        knoll = self.circle("knoll", radius=radius, op="raise", amount=30., feather=0.)
        shelf = self.circle("shelf", radius=radius, op="flatten", target="mean", feather=10.)
        kept = self.circle("kept", radius=5., op="flatten", target=12.5, feather=0.)
        plan = self.plan(knoll, shelf, kept)
        resolved = landscape.resolve_terrain_edit_targets(plan)
        # Measured on the 2 m composed grid inside the shape, with every edit removed:
        # the knoll's 30 m over the same circle must not reach the shelf's target.
        natural = dict(landscape.load_plan(), terrain_edits=[])
        x, z = np.meshgrid(np.arange(self.CENTRE[0] - radius, self.CENTRE[0] + radius + 2, 2.),
                           np.arange(self.CENTRE[1] - radius, self.CENTRE[1] + radius + 2, 2.))
        inside = np.hypot(x - self.CENTRE[0], z - self.CENTRE[1]) <= radius
        ground = landscape.height_at(x[inside], z[inside], natural)
        self.assertEqual(resolved["terrain_edits"][1]["target"], round(float(ground.mean()), 1))
        self.assertEqual(resolved["terrain_edits"][2]["target"], 12.5)
        self.assertEqual(resolved["terrain_edits"][0], knoll)
        self.assertEqual(plan["terrain_edits"][1]["target"], "mean")
        for statistic in ("min", "max"):
            settled = landscape.resolve_terrain_edit_targets(self.plan(dict(shelf, target=statistic)))
            self.assertEqual(settled["terrain_edits"][0]["target"], round(float(getattr(ground, statistic)()), 1))
        # A resolved plan evaluates; only numbers reach the composer.
        self.assertTrue(np.isfinite(float(landscape.height_at(*self.CENTRE, resolved))))


if __name__ == "__main__":
    unittest.main()
