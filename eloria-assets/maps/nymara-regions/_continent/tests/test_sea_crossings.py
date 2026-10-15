from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from shapely import Polygon

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import sea_crossings as S


def independent_road_outline_records(points, half_width, start_station, end_station):
    """Synthetic equivalent of existing RoadOutline, with owner stations."""
    points = np.asarray(points, float); xz = points[:, [0, 2]]
    source_stations = S.cumulative_stations(points); records = []

    def clip(polygon, values):
        output = []
        for index in range(len(polygon)):
            previous = (index - 1) % len(polygon)
            if (values[index] >= 0) != (values[previous] >= 0):
                ratio = values[previous] / (values[previous] - values[index])
                output.append(polygon[previous] + ratio * (polygon[index] - polygon[previous]))
            if values[index] >= 0: output.append(polygon[index])
        return np.asarray(output, float).reshape(-1, polygon.shape[1])

    first_direction = (xz[1] - xz[0]) / np.linalg.norm(xz[1] - xz[0])
    last_direction = (xz[-1] - xz[-2]) / np.linalg.norm(xz[-1] - xz[-2])
    start = S._point_at(points, source_stations, start_station)[0][[0, 2]]
    end = S._point_at(points, source_stations, end_station)[0][[0, 2]]
    for segment, (a, b) in enumerate(zip(xz, xz[1:])):
        direction = b - a; length = np.linalg.norm(direction); angle = np.arctan2(direction[1], direction[0])
        arc = angle + np.linspace(-np.pi * .5, np.pi * .5, 13)
        polygon = np.concatenate((np.c_[b[0] + half_width * np.cos(arc), b[1] + half_width * np.sin(arc)],
                                  np.c_[a[0] - half_width * np.cos(arc), a[1] - half_width * np.sin(arc)]))
        ratio = (polygon - a) @ direction / (length * length)
        stationed = np.c_[polygon, source_stations[segment] + ratio * length]
        stationed = clip(stationed, (stationed[:, :2] - start) @ first_direction)
        if len(stationed):
            # The clipping plane is the named station authority; snap its
            # interpolated scalar to that exact semantic bound.
            stationed[:, 2] = np.maximum(stationed[:, 2], start_station)
            stationed = clip(stationed, (end - stationed[:, :2]) @ last_direction)
            stationed[:, 2] = np.minimum(stationed[:, 2], end_station)
        if len(stationed) < 3 or S._area_xz(stationed[:, :2]) <= 0: continue
        stationed[:, 2] = np.clip(stationed[:, 2], source_stations[segment], source_stations[segment + 1])
        records.append({'xz': stationed[:, :2].astype(np.float32).astype(float), 'stations': stationed[:, 2]})
    return records


class SeaCrossingGeometryTests(unittest.TestCase):
    def straight_road(self, length=12., height=2.):
        return np.array([[0., height, 2.], [length, height, 2.]])

    def test_road_following_floor_has_full_width_flat_sections_and_actual_encoded_faces(self):
        profile = S.SmoothArchProfile(1., 6., 11., 2., 2.4, 2.)
        surface = S.road_surface('Walk_Test', 'coastal-arch', 'road', self.straight_road(), 2.,
                                 1., 11., profile)
        np.testing.assert_allclose(np.linalg.norm(surface.sections[:, 0, [0, 2]] -
                                                  surface.sections[:, 1, [0, 2]], axis=1), 4.)
        np.testing.assert_array_equal(surface.sections[:, 0, 1], surface.sections[:, 1, 1])
        np.testing.assert_array_equal(surface.encoded_triangles,
                                      surface.triangles.astype(np.float32).astype(np.float64))
        self.assertEqual(surface.geometry()['triangles'].shape, surface.triangles.shape)
        coverage = S.floor_capsule_coverage_evidence(surface, self.straight_road(), 2., 1., 11.)
        self.assertTrue(coverage['complete'], coverage)

    def test_continuous_wet_partition_and_full_width_joins_use_affine_terrain(self):
        x = np.arange(0., 12., 2.); z = np.arange(0., 6., 2.)
        ridge = np.array([1., .4, -1., -1., .4, 1.])
        terrain = S.TerrainPatch(x, z, np.repeat(ridge[None, :], len(z), axis=0))
        surface = S.road_surface('Walk_Test', 'coastal-arch', 'road', self.straight_road(10.), 1.,
                                 1., 9., S._ConstantProfile(2.))
        wet = S.continuous_wet_evidence(surface, terrain, sea_level=0.)
        self.assertGreater(wet['wetAreaSquareMetres'], 0.)
        self.assertLess(wet['wetExtentMetres'][0], wet['wetExtentMetres'][1])
        self.assertTrue(S.section_evidence(surface.start_section, terrain, -.015)['dry'])
        self.assertTrue(S.section_evidence(surface.end_section, terrain, -.015)['dry'])
        # The result retains actual clipped pieces, not sampled wet cells.
        self.assertEqual(wet['pieceCount'], len(wet['wetPieces']))
        self.assertTrue(all(piece['areaSquareMetres'] > 0 for piece in wet['wetPieces']))
        self.assertFalse(wet['acceptanceAuthority'])

    def test_actual_encoded_water_contact_names_nonsea_domains(self):
        surface = S.road_surface('Walk_Test', 'coastal-arch', 'road', self.straight_road(10.), 1.,
                                 1., 9., S._ConstantProfile(2.))
        sea = np.array([[[1., 0., 1.], [9., 0., 1.], [1., 0., 3.]],
                        [[9., 0., 1.], [9., 0., 3.], [1., 0., 3.]]])
        empty = np.empty((0, 3, 3))
        evidence = S.emitted_water_evidence(surface, {'sea': sea, 'river': empty, 'lake': empty})
        self.assertTrue(evidence['pureSea'])
        self.assertTrue(evidence['continuous'])
        mixed = S.emitted_water_evidence(surface, {'sea': sea, 'river': sea[:1], 'lake': empty})
        self.assertFalse(mixed['pureSea'])
        self.assertIn('river', mixed['nonSeaContactKinds'])
        clearance = S.emitted_water_evidence(
            surface, {'sea': sea, 'river': empty, 'lake': empty}, minimum_clearance_metres=2.1)
        self.assertFalse(clearance['clearanceClear'])
        self.assertAlmostEqual(clearance['minimumClearanceMetres'], 2.)

    def test_exact_domain_relabels_emitted_piece_in_lake_interior(self):
        evidence = {'pieces': [{'xz': np.array([[-.2, -.2], [.2, -.2], [0., .2]])}],
                    'continuous': True, 'clearanceClear': True}
        world = SimpleNamespace(plan={'rivers': [], 'lakes': [{'center': [0., 0.],
                                                                'radii': [1., 1.]}]})
        landscape = SimpleNamespace(curved_points=lambda points: np.asarray(points))
        result = S.exact_domain_evidence(evidence, world, landscape)
        self.assertFalse(result['pureSea'])
        self.assertEqual(result['contactKinds'], ['lake'])

    def test_encoded_terrain_clearance_uses_all_affine_overlap_vertices(self):
        surface = S.road_surface('Walk_Clearance', 'coastal-arch', 'road', self.straight_road(10.), 1.,
                                 1., 9., S._ConstantProfile(2.))
        clear = S.TerrainPatch(np.arange(0., 12., 2.), np.arange(0., 6., 2.),
                               np.full((3, 6), 1.9))
        self.assertTrue(S.encoded_terrain_clearance_evidence(surface, clear)['clear'])
        ridge = np.full((3, 6), 1.9); ridge[1] = 2.1
        blocked = S.encoded_terrain_clearance_evidence(
            surface, S.TerrainPatch(clear.x, clear.z, ridge))
        self.assertFalse(blocked['clear'])
        self.assertLess(blocked['minimumGapMetres'], 0.)

    def test_level_bend_platform_is_exact_disjoint_capsule_union(self):
        points = np.array([[0., 2., 2.], [5., 2., 2.], [5., 2., 7.]])
        surface = S.level_capsule_surface('Walk_Bend', 'coastal-level-platform', 'road',
                                          points, 1., 1., 9., 3.)
        evidence = S.floor_capsule_coverage_evidence(surface, points, 1., 1., 9.)
        self.assertTrue(evidence['complete'], evidence)
        self.assertFalse(evidence['overlaps'])
        np.testing.assert_array_equal(surface.encoded_triangles[:, :, 1], 3.)
        independent = S.floor_road_outline_coverage_evidence(
            surface, independent_road_outline_records(points, 1., 1., 9.), 1., 9.)
        self.assertTrue(independent['complete'], independent)
        self.assertEqual(independent['independentAuthority'],
                         'existing RoadOutline capsule union with source-segment stations')

    def test_geos_road_union_has_one_shared_table_for_concavity_and_holes(self):
        points = np.array([[0., 2., 2.], [5., 2., 2.], [5., 2., 7.]])
        records = independent_road_outline_records(points, 1., 1., 9.)
        union = S.encoded_road_outline_union(records)
        self.assertEqual((union.component_count, union.hole_count), (1, 0))
        vertices = np.c_[union.vertices_xz[:, 0], np.full(len(union.vertices_xz), 3.),
                         union.vertices_xz[:, 1]]
        triangles = vertices[union.triangle_indices]
        distances = S.cumulative_stations(points)
        sections = np.stack((S._section(points, distances, 1., 1.),
                             S._section(points, distances, 9., 1.)))
        sections[:, :, 1] = 3.
        surface = S.SurfaceGeometry('Walk_GEOS', 'coastal-level-platform', 'road', np.array([1., 9.]),
                                    sections, triangles, np.zeros((len(triangles), 3)))
        evidence = S.floor_road_outline_coverage_evidence(surface, records, 1., 9.)
        self.assertTrue(evidence['complete'], evidence)

        rectangles = [
            [[0., 0.], [4., 0.], [4., 1.], [0., 1.]],
            [[0., 3.], [4., 3.], [4., 4.], [0., 4.]],
            [[0., 1.], [1., 1.], [1., 3.], [0., 3.]],
            [[3., 1.], [4., 1.], [4., 3.], [3., 3.]],
        ]
        frame = S.encoded_road_outline_union([{'xz': value} for value in rectangles])
        self.assertEqual((frame.component_count, frame.hole_count), (1, 1))
        areas = np.array([S._area_xz(face) for face in frame.triangles_xz])
        self.assertEqual(float(areas.sum()), 12.)
        centres = frame.triangles_xz.mean(axis=1)
        self.assertFalse(((centres[:, 0] > 1.) & (centres[:, 0] < 3.) &
                          (centres[:, 1] > 1.) & (centres[:, 1] < 3.)).any())

    def test_indexed_surface_preserves_closed_road_outline_hole(self):
        import bridge_export as B
        from shapely import Point, Polygon, union_all
        points = np.array([[-8., 2., 0.], [0., 2., 0.], [20., 2., 0.], [20., 2., 20.],
                           [0., 2., 20.], [0., 2., 0.], [-8., 2., -4.]])
        end = S.cumulative_stations(points)[-1]
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        surface, metadata, authority = S.indexed_road_union_surface(
            'Walk_Closed', 'coastal-level-platform', 'road', points, 1., 0., end,
            np.array([0., end]), np.array([3., 3.]), factory, [[0., end, []]])
        self.assertGreater(metadata['unionHoles'], 0)
        emitted = union_all([Polygon(face[:, [0, 2]]) for face in surface.encoded_triangles])
        self.assertFalse(emitted.covers(Point(10., 10.)))
        evidence = S.partitioned_road_outline_coverage_evidence(
            surface, authority['nominalOutlineRecords'], authority['sourcePartitionXZ'])
        self.assertTrue(evidence['complete'], evidence)

    def test_independent_road_union_gate_rejects_missing_and_wrong_floor_branches(self):
        records = [{'xz': [[0., 0.], [4., 0.], [4., 2.], [0., 2.]]},
                   {'xz': [[6., 0.], [10., 0.], [10., 2.], [6., 2.]]}]
        union = S.encoded_road_outline_union(records)
        vertices = np.c_[union.vertices_xz[:, 0], np.ones(len(union.vertices_xz)), union.vertices_xz[:, 1]]
        triangles = vertices[union.triangle_indices]
        sections = np.array([[[0., 1., 0.], [0., 1., 2.]],
                             [[10., 1., 0.], [10., 1., 2.]]])

        def surface(faces):
            return S.SurfaceGeometry('Walk_Independent', 'test', 'road', np.array([0., 10.]),
                                     sections, faces, np.zeros((len(faces), 3)))

        guard = S.road_outline_encoding_guard(records)
        complete = S.partitioned_road_outline_coverage_evidence(
            surface(triangles), records)
        self.assertTrue(complete['complete'], complete)

        missing = S.partitioned_road_outline_coverage_evidence(
            surface(triangles[:-1]), records)
        self.assertFalse(missing['complete'])
        self.assertGreater(missing['nominalUncoveredAreaSquareMetres'], 0.)

        wrong_faces = triangles.copy(); wrong_faces[-1, :, 0] += 20.
        wrong = S.partitioned_road_outline_coverage_evidence(
            surface(wrong_faces), records)
        self.assertFalse(wrong['complete'])
        self.assertGreater(wrong['outsideAllowedGuardAreaSquareMetres'], 0.)

        overlapping = S.partitioned_road_outline_coverage_evidence(
            surface(np.concatenate((triangles, triangles[:1]))), records)
        self.assertFalse(overlapping['complete'])
        self.assertTrue(overlapping['overlaps'])

    def test_bounded_road_outline_keeps_returning_interior_leg(self):
        import bridge_export as B
        points = np.array([[0., 2., 0.], [5., 2., 0.], [-2., 2., 3.], [-4., 2., 3.]])
        end = S.cumulative_stations(points)[-1] - .5
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        records = S.road_outline_records(points, .5, .5, end, factory)
        owners = {record['sourceSegment'] for record in records}
        self.assertEqual(owners, {0, 1, 2})
        returning = [record for record in records if record['sourceSegment'] == 1]
        self.assertLess(min(float(record['xz'][:, 0].min()) for record in returning), .5)

    def test_broad_middle_profile_has_dense_smooth_shoulders_and_level_crown(self):
        points = np.array([[0., 0., 0.], [20., 0., 0.]])
        profile = S.SmoothArchProfile(0., 10., 20., 0., 2., 0.)
        stations, heights, bands = S.broad_middle_profile_table(
            points, 1., 0., 3., 10., 17., 20., profile)
        self.assertGreater(len(stations), 30)
        crown_band = next(value for value in bands if value[0] <= 10. <= value[1])
        middle = (stations >= crown_band[0]) & (stations <= crown_band[1])
        np.testing.assert_array_equal(heights[middle], np.full(middle.sum(), 2.))
        self.assertEqual(heights[0], 0.)
        self.assertEqual(heights[-1], 0.)
        self.assertLess(abs((heights[1] - heights[0]) / (stations[1] - stations[0])), .1)

    def test_broad_middle_omits_bend_bands_narrower_than_encoded_station_guard(self):
        points = np.array([[1.e6, 0., 0.], [1.e6 + 10., 0., 0.],
                           [1.e6 + 20., 0., .005], [1.e6 + 30., 0., 0.]])
        profile = S.SmoothArchProfile(0., 15., 30., 0., 2., 0.)
        raw_bands = S.coastal_profile_table(points, 4., 0., 5., 15., 25., 30., profile, 0.)[2]
        guard = S._route_station_encoding_guard(points)
        self.assertTrue(raw_bands)
        self.assertTrue(all(right - left < guard for left, right, _ in raw_bands))
        _, _, bands = S.broad_middle_profile_table(points, 4., 0., 5., 15., 25., 30., profile)
        self.assertEqual(len(bands), 1)
        self.assertLess(bands[0][0], 15.)
        self.assertGreater(bands[0][1], 15.)

    def test_bank_fit_request_uses_encoded_full_width_joins_and_outward_approaches(self):
        road = {'id': 'road', 'width': 2., 'points': self.straight_road(20.).tolist()}
        request = S.coastal_bank_fit_request('claim', road, 5., 15., (2., 5.), (15., 18.),
                                             [(4, 3), (4, 3), (2, 1)], 'height-sha')
        self.assertEqual(request['roadId'], 'road')
        self.assertEqual(request['pinnedVertexIndices'], [(2, 1), (4, 3)])
        np.testing.assert_array_equal(request['left']['joinSection'],
                                      request['left']['joinSection'].astype(np.float32).astype(float))
        self.assertEqual(np.linalg.norm(request['left']['joinSection'][0, [0, 2]] -
                                        request['left']['joinSection'][1, [0, 2]]), 4.)
        actual = np.stack((request['left']['joinSection'], request['right']['joinSection']))
        actual[0, :, 0] = np.float32(actual[0, :, 0] - .0001)
        carried = S.coastal_bank_fit_request(
            'claim', road, 5., 15., (2., 5.), (15., 18.), (), 'height-sha',
            join_sections=actual)
        np.testing.assert_array_equal(carried['left']['joinSection'], actual[0])

    def test_encoded_join_evidence_uses_guard_expanded_emitted_boundary(self):
        import bridge_export as B
        points = self.straight_road(20.)
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        surface, _, authority = S.indexed_road_union_surface(
            'Walk_Join', 'coastal-arch', 'road', points, 1., 5., 15.,
            np.array([5., 10., 15.]), np.array([2., 2.2, 2.]), factory)
        terrain = S.TerrainPatch(np.arange(0., 22., 2.), np.arange(0., 6., 2.),
                                 np.full((3, 11), 1.9))
        empty_water = np.empty((0, 3, 3))
        evidence = S.encoded_full_width_join_evidence(surface, terrain, water_triangles=empty_water)
        self.assertTrue(evidence['clear'], evidence)
        self.assertGreater(len(evidence['joins'][0]['encodedBoundaryXZ']), 2)
        left_x = evidence['joins'][0]['encodedBoundaryXZ'][:, 0]
        self.assertEqual(len(np.unique(left_x)), 1)
        self.assertLess(float(left_x[0]), 5.)
        self.assertLessEqual(5. - float(left_x[0]), authority['encodingGuardMetres'])
        self.assertLess(float(evidence['joins'][0]['encodedBoundaryXZ'][:, 1].min()), 1.)
        self.assertGreater(float(evidence['joins'][0]['encodedBoundaryXZ'][:, 1].max()), 3.)
        right_x = evidence['joins'][1]['encodedBoundaryXZ'][:, 0]
        self.assertEqual(len(np.unique(right_x)), 1)
        self.assertGreater(float(right_x[0]), 15.)
        self.assertLessEqual(float(right_x[0]) - 15., authority['encodingGuardMetres'])
        self.assertLess(float(evidence['joins'][1]['encodedBoundaryXZ'][:, 1].min()), 1.)
        self.assertGreater(float(evidence['joins'][1]['encodedBoundaryXZ'][:, 1].max()), 3.)
        self.assertAlmostEqual(evidence['minimumGapMetres'], .1, places=6)
        self.assertAlmostEqual(evidence['maximumGapMetres'], .1, places=6)
        outer = S.road_surface('Walk_Outer', 'shore-tread', 'road', points, 1., 15., 18.,
                               S._ConstantProfile(2.))
        transitioned = S.encoded_full_width_join_evidence(
            surface, terrain, right_surface=outer, water_triangles=empty_water)
        self.assertEqual(transitioned['joins'][1]['stationMetres'], 18.)

    def test_encoded_join_checks_interior_terrain_breakpoint_and_actual_water(self):
        import bridge_export as B
        points = self.straight_road(20.)
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        surface, _, _ = S.indexed_road_union_surface(
            'Walk_Join_Ridge', 'coastal-arch', 'road', points, 1., 5., 15.,
            np.array([5., 10., 15.]), np.array([2., 2.2, 2.]), factory)
        x, z = np.arange(0., 22., 2.), np.arange(0., 6., 2.)
        height = np.full((3, 11), 1.9); height[1] = 2.1
        terrain = S.TerrainPatch(x, z, height)
        empty = np.empty((0, 3, 3))
        ridge = S.encoded_full_width_join_evidence(surface, terrain, water_triangles=empty)
        self.assertFalse(ridge['clear'])
        self.assertGreater(ridge['joins'][0]['terrainBreakpointCount'], 2)
        water = np.array([[[4., 0., 1.], [6., 0., 1.], [4., 0., 3.]],
                          [[6., 0., 1.], [6., 0., 3.], [4., 0., 3.]]])
        wet = S.encoded_full_width_join_evidence(
            surface, S.TerrainPatch(x, z, np.full((3, 11), 1.9)), water_triangles=water)
        self.assertFalse(wet['waterClear'])
        self.assertFalse(wet['clear'])

    def test_named_cap_station_survives_an_adjacent_bend_capsule(self):
        import bridge_export as B
        points = np.array([[10., 2., 0.], [10., 2., 2.], [10., 2., 4.], [10., 2., 6.],
                           [8.6213402, 2., 7.1839659], [7.2426804, 2., 8.3679318]])
        start = 5.7558230833417365
        end = float(S.cumulative_stations(points)[-1])
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        records = S.road_outline_records(points, 1.65, start, end, factory)
        source = S.cumulative_stations(points)
        start_point = S._point_at(points, source, start)[0][[0, 2]].astype(np.float32).astype(float)
        direction = points[3, [0, 2]].astype(np.float32).astype(float) - start_point
        direction /= np.linalg.norm(direction)
        cap_stations = np.concatenate([
            record['stations'][np.abs((record['xz']-start_point)@direction) == 0.]
            for record in records])
        self.assertGreater(len(cap_stations), 2)
        np.testing.assert_array_equal(cap_stations, np.full(len(cap_stations), start))
        with self.assertRaisesRegex(S.CoastalGeometryError, 'does not retain full road width'):
            S.indexed_road_union_surface(
                'Walk_Bent_Invalid_Join', 'terminal-probe', 'road', points, 1.65, start, end,
                np.array([start, end]), np.zeros(2), factory)
        probe, probe_metadata, probe_authority = S.indexed_road_union_probe_surface(
            'Walk_Bent_Footprint_Probe', 'footprint-probe', 'road', points, 1.65, start, end,
            np.array([start, end]), np.zeros(2), factory)
        self.assertFalse(probe_metadata['joinCapsValidated'])
        self.assertEqual(probe.join_edges, ((), ()))
        self.assertTrue(S.partitioned_road_outline_coverage_evidence(
            probe, probe_authority['nominalOutlineRecords'],
            probe_authority['sourcePartitionXZ'])['complete'])
        valid_start = 4.
        surface, _, _ = S.indexed_road_union_surface(
            'Walk_Bent_Terminal', 'terminal-probe', 'road', points, 1.65, valid_start, end,
            np.array([valid_start, end]), np.zeros(2), factory)
        self.assertEqual(len(surface.join_edges), 2)
        self.assertGreater(sum(len(side) for side in surface.join_edges), 1)

    def test_terminal_side_preserves_round_road_outline_cap(self):
        import bridge_export as B
        points = np.array([[10., 2., 0.], [10., 2., 2.], [10., 2., 4.], [10., 2., 6.],
                           [8.6213402, 2., 7.1839659], [7.2426804, 2., 8.3679318]])
        start = 4.; end = float(S.cumulative_stations(points)[-1])
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        surface, metadata, authority = S.indexed_road_union_surface(
            'Walk_Round_Terminal', 'terminal-platform', 'road', points, 1.65, start, end,
            np.array([start, end]), np.zeros(2), factory, terminal_sides=('right',))
        self.assertEqual(metadata['terminalSides'], ['right'])
        self.assertEqual(metadata['validatedJoinSides'], ['left'])
        self.assertGreater(len(surface.join_edges[0]), 0)
        self.assertEqual(surface.join_edges[1], ())
        endpoint = points[-1, [0, 2]].astype(np.float32).astype(float)
        tangent = points[-1, [0, 2]] - points[-2, [0, 2]]
        tangent /= np.linalg.norm(tangent)
        longitudinal = ((surface.encoded_triangles[..., [0, 2]].reshape(-1, 2) - endpoint) @ tangent)
        self.assertGreater(float(longitudinal.max()), 1.)
        self.assertTrue(S.partitioned_road_outline_coverage_evidence(
            surface, authority['nominalOutlineRecords'], authority['sourcePartitionXZ'])['complete'])

    def test_terminal_miter_pad_owns_bend_fan_at_one_flat_height(self):
        import bridge_export as B
        points = np.array([
            [540., 2.94730167, 1062.], [540., 2.75959501, 1064.],
            [540., 2.55914417, 1066.], [540., 2.23155842, 1068.],
            [538.6213402, 1.82260370, 1069.1839659],
            [537.2426804, 1.42700118, 1070.3679318],
            [535.864021, 1.02411038, 1071.5518977],
            [534.485361, .125132663, 1072.7358636],
            [533.106701, .85, 1073.9198295],
            [531.7280412, .85, 1075.1037954],
            [529.7280412, .85, 1075.1037954],
        ])
        half_width = 1.65
        distances = S.cumulative_stations(points)
        start, end = float(distances[6]), float(distances[-1])
        platform_start = S.component502_terminal_platform_start(points, half_width)
        directions = np.diff(points[-3:, [0, 2]], axis=0)
        directions /= np.linalg.norm(directions, axis=1)[:, None]
        turn = np.arccos(np.clip(directions[0] @ directions[1], -1., 1.))
        expected = distances[-2] - half_width * np.tan(turn * .5)
        np.testing.assert_allclose(platform_start, expected, rtol=0., atol=np.spacing(expected) * 4.)
        self.assertLess(distances[-3], platform_start)
        self.assertLess(platform_start, distances[-2])
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))

        def build(level_start):
            wet_start = start + (level_start - start) * .25
            crown = (wet_start + level_start) * .5
            profile = S.SmoothArchProfile(start, crown, level_start, 2., 2.2, 2.)
            stations = S.canonical_stations(points, start, level_start, .5)
            heights = profile.height(stations)
            stations = np.r_[stations, end]; heights = np.r_[heights, 2.]
            return S.indexed_road_union_surface(
                'Walk_Terminal_Miter', 'coastal-supported-terminal', 'road',
                points, half_width, start, end, stations, heights, factory,
                level_bands=((level_start, end, (level_start,)),),
                terminal_sides=('right',))

        with self.assertRaisesRegex(S.CoastalGeometryError, 'crosses an unsplit local profile breakline'):
            build(float(distances[-2]))
        surface, metadata, authority = build(platform_start)
        coverage = S.partitioned_road_outline_coverage_evidence(
            surface, authority['nominalOutlineRecords'], authority['sourcePartitionXZ'])
        self.assertTrue(coverage['complete'], coverage)
        self.assertEqual(surface.join_edges[1], ())
        self.assertEqual(metadata['terminalSides'], ['right'])
        terminal_faces = surface.encoded_triangles[
            np.all(surface.triangle_stations >= platform_start, axis=1)]
        self.assertGreater(len(terminal_faces), 0)
        np.testing.assert_array_equal(np.unique(terminal_faces[:, :, 1]),
                                      np.array([np.float32(2.)], dtype=np.float32).astype(float))

    def test_terminal_claim_checks_only_its_real_bank_and_supports_its_platform(self):
        import bridge_export as B
        points = self.straight_road(20.)
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        surface, _, authority = S.indexed_road_union_surface(
            'Walk_One_Bank', 'terminal-platform', 'road', points, 1., 5., 15.,
            np.array([5., 10., 15.]), np.array([2., 2.2, 2.]), factory,
            terminal_sides=('right',))
        terrain = S.TerrainPatch(np.arange(0., 22., 2.), np.arange(0., 6., 2.),
                                 np.full((3, 11), 1.9))
        water = np.array([[[8., 0., 1.], [17., 0., 1.], [8., 0., 3.]],
                          [[17., 0., 1.], [17., 0., 3.], [8., 0., 3.]]])
        joins = S.encoded_full_width_join_evidence(
            surface, terrain, water_triangles=water, sides=('left',))
        self.assertTrue(joins['clear'])
        self.assertEqual([value['side'] for value in joins['joins']], ['left'])
        platform = Polygon([[13., 1.], [15., 1.], [15., 3.], [13., 3.]])
        support = S._support_polygon_record('Terminal_Support', 'terminal-support',
                                            platform, 2., terrain)
        support_evidence = S.support_records_contact_evidence((support,))
        self.assertTrue(support_evidence['clear'])
        claim = S.CoastalClaim(
            'terminal', 502, ('road',), (8., 15.), (5., 15.), (surface,),
            supports=(support,), terminal_sides=('right',), evidence={
                'capsuleCoverage': S.partitioned_road_outline_coverage_evidence(
                    surface, authority['nominalOutlineRecords'], authority['sourcePartitionXZ']),
                'emittedWater': {'acceptanceAuthority': True, 'clear': True,
                                 'pureSea': True, 'continuous': True},
                'fullWidthJoins': joins,
                'terrainClearance': S.encoded_terrain_clearance_evidence(surface, terrain),
                'supportContact': support_evidence,
                'terminalPlatform': {'acceptanceAuthority': True, 'clear': True},
            })
        self.assertIs(S.validate_claim(claim), claim)

    def test_terrain_control_lower_bound_uses_exact_encoded_overlap(self):
        points = self.straight_road(20.)
        base = S.road_surface('Walk_Base', 'probe', 'road', points, 1., 5., 15.,
                              S._ConstantProfile(1.))
        raised = S.road_surface('Walk_Raised', 'probe', 'road', points, 1., 5., 15.,
                                S._ConstantProfile(2.))
        terrain = S.TerrainPatch(np.arange(0., 22., 2.), np.arange(0., 6., 2.),
                                 np.full((3, 11), 1.5))
        solved = S.terrain_control_height_lower_bound(base, raised, terrain, 1., 2.)
        self.assertFalse(solved['acceptanceAuthority'])
        self.assertGreater(solved['constraintCount'], 0)
        self.assertGreater(solved['requiredControlHeightMetres'], 1.5)

    def test_broad_middle_solver_raises_only_bounded_endpoint_for_final_terrain(self):
        import bridge_export as B
        points = self.straight_road(30.)
        factory = lambda roads: B.RoadOutline(SimpleNamespace(roads=roads))
        x, z = np.arange(0., 32., 2.), np.arange(0., 6., 2.)
        height = np.full((len(z), len(x)), 1.974)
        height[:, 12] = 2.05
        terrain = S.TerrainPatch(x, z, height)
        sea = np.array([[[10., 0., 1.], [20., 0., 1.], [10., 0., 3.]],
                        [[20., 0., 1.], [20., 0., 3.], [10., 0., 3.]]])
        surface, _, _, solved = S.solve_broad_middle_surface(
            'Walk_Controlled', 'coastal-indexed-arch', 'road', points, 1.,
            5., (10., 20.), 25., (2., 2.), terrain,
            {'sea': sea, 'river': np.empty((0, 3, 3)), 'lake': np.empty((0, 3, 3))},
            1., .2, factory, adjustable_endpoint='right', domain_classifier=lambda value: value)
        self.assertGreater(solved['finalDeckHeightsMetres'][1], 2.)
        self.assertEqual(solved['finalDeckHeightsMetres'][0], 2.)
        self.assertLessEqual(solved['evidence']['fullWidthJoins']['maximumGapMetres'], .3)
        self.assertTrue(solved['evidence']['terrainClearance']['clear'])
        self.assertTrue(solved['evidence']['emittedWater']['clear'])
        self.assertTrue(solved['evidence']['capsuleCoverage']['clear'])
        self.assertLessEqual(len(solved['attempts']), 4)
        self.assertGreater(solved['crownHeightMetres'], max(solved['finalDeckHeightsMetres']))
        self.assertGreater(len(surface.encoded_triangles), 0)

    def test_supported_stair_derives_treads_from_policy_and_supports_every_one(self):
        policy = S.StepPolicy(.5, 1., 2.1, .5, .06, {'fixture': True})
        terrain = S.TerrainPatch(np.arange(0., 16., 2.), np.arange(0., 6., 2.), np.zeros((3, 8)))
        stair = S.supported_shore_stair('Walk_Shore', 'road', self.straight_road(15.), 1.65,
                                        1., 11., 1., 3., policy, terrain)
        self.assertEqual(len(stair.tread_surfaces), 5)
        self.assertEqual(len(stair.supports), len(stair.tread_surfaces))
        self.assertEqual(len(stair.riser_triangles), 8)
        self.assertTrue(all(support.triangles.size for support in stair.supports))
        self.assertTrue(S.support_contact_evidence(stair)['clear'])
        self.assertTrue(all(np.any(np.cross(support.encoded_triangles[:, 1] - support.encoded_triangles[:, 0],
                                            support.encoded_triangles[:, 2] - support.encoded_triangles[:, 0])[:, 1] < 0)
                            for support in stair.supports))
        self.assertEqual(stair.encoded_floor_triangles.shape[1:], (3, 3))
        guarded = S.guarded_step_evidence(stair, {'clientPassable': True, 'serverPassable': True,
                                                   'headClear': True, 'guardsContinuous': True,
                                                   'authority': {'fixture': True}})
        self.assertTrue(guarded['clear'])

    def test_supported_stair_rejects_a_run_too_short_for_current_policy(self):
        policy = S.StepPolicy(.4, 1., 2.1, .5, .06, {'fixture': True})
        terrain = S.TerrainPatch(np.arange(0., 14., 2.), np.arange(0., 6., 2.), np.zeros((3, 7)))
        with self.assertRaisesRegex(S.CoastalGeometryError, 'too short') as caught:
            S.supported_shore_stair('Walk_Shore', 'road', self.straight_road(), 1.65,
                                    1., 5., 1., 4., policy, terrain)
        self.assertGreater(caught.exception.witness['requiredRisers'], 1)

    def test_supported_stair_uses_exact_terrain_union_for_rotated_footprints(self):
        policy = S.StepPolicy(.5, .5, 2.1, .5, .06, {'fixture': True})
        x = np.arange(0., 18., 2.); z = np.arange(0., 10., 2.)
        height = .01 * z[:, None] + .02 * x[None, :]
        terrain = S.TerrainPatch(x, z, height)
        road = np.array([[1., 2., 1.], [15., 2., 7.]])
        stair = S.supported_shore_stair('Walk_Rotated', 'road', road, .45,
                                        1., 10., 2., 2.8, policy, terrain)
        self.assertTrue(S.support_contact_evidence(stair)['clear'])
        self.assertGreater(sum(len(item.contact_pieces_xz) for item in stair.supports),
                           len(stair.supports))

    def test_supported_stair_rejects_true_escape_from_terrain_authority(self):
        policy = S.StepPolicy(.5, .5, 2.1, .5, .06, {'fixture': True})
        terrain = S.TerrainPatch(np.arange(0., 10., 2.), np.arange(0., 6., 2.), np.zeros((3, 5)))
        road = np.array([[1., 2., .1], [8., 2., .1]])
        with self.assertRaisesRegex(S.CoastalGeometryError, 'left its final terrain authority') as caught:
            S.supported_shore_stair('Walk_Outside', 'road', road, .5,
                                    1., 5., 2., 2.8, policy, terrain)
        self.assertGreater(caught.exception.witness['uncoveredAreaSquareMetres'], 0.)

    def test_component501_candidate_changes_only_six_xz_points(self):
        roads = json.loads((HERE / 'generated' / 'roads.json').read_text(encoding='utf-8'))['roads']
        registry = S.coastal_registry_roads(roads)
        self.assertEqual(sorted(registry), list(range(500, 521)))
        self.assertEqual(tuple(item['id'] for item in registry[520]), S.COASTAL_COMPONENT_ROADS[520])
        self.assertIn((510, 513), S.COASTAL_SEMANTIC_GROUPS)
        fixture = json.loads((HERE / 'tests' / 'fixtures' / 'component501-road.json').read_text(encoding='utf-8'))
        road = S.require_road((fixture,), S.COMPONENT501_ROAD, S.COMPONENT501_ROAD_SHA256)
        composed_like = {**road, 'points': np.asarray(road['points']), 'runtimeMetadata': object()}
        self.assertIs(S.require_matching_road_authorities((fixture,), [composed_like], S.COMPONENT501_ROAD,
                                                          S.COMPONENT501_ROAD_SHA256), composed_like)
        edit = S.component501_road_edit(road)
        allowed = np.zeros(len(edit.source_points), bool); allowed[list(edit.changed_indices)] = True
        np.testing.assert_array_equal(edit.source_points[~allowed], edit.candidate_points[~allowed])
        np.testing.assert_array_equal(edit.source_points[:, 1], edit.candidate_points[:, 1])
        self.assertEqual(edit.changed_indices, tuple(range(242, 248)))
        self.assertEqual(edit.shift_metres, .22)
        self.assertTrue(np.any(edit.source_points[allowed][:, [0, 2]] != edit.candidate_points[allowed][:, [0, 2]]))

    def test_claim_requires_complete_wet_extent_inside_six_metre_joins(self):
        surface = S.road_surface('Walk_Test', 'coastal-arch', 'road', self.straight_road(), 1.,
                                 1., 11., S._ConstantProfile(2.))
        claim = S.CoastalClaim('test', 500, ('road',), (3., 9.), (1., 11.), (surface,))
        self.assertFalse(claim.source_ready)
        self.assertIs(S.validate_claim_preflight(claim), claim)
        with self.assertRaisesRegex(S.CoastalGeometryError, 'full-geometry acceptance'):
            S.validate_claim(claim)
        with self.assertRaisesRegex(S.CoastalGeometryError, 'landing exceeds'):
            S.validate_claim_preflight(S.CoastalClaim('bad', 500, ('road',), (8., 9.), (1., 11.), (surface,)))

    def test_selected_registry_defaults_to_component502_and_validates_cached_selection(self):
        world = SimpleNamespace(); inventory = {'looseWetCellIndices': (4, 5)}
        expected = SimpleNamespace(claim_id='coastal-502', road_ids=(S.COMPONENT502_ROAD,))
        with patch('coastal_prepare.prepare_component502_claim', return_value=expected) as prepare:
            self.assertEqual(S.prepare_coastal_claims(world, content='content', inventory=inventory),
                             (expected,))
        prepare.assert_called_once_with(world, inventory, content='content')
        world.claimed_coastal_records = (expected,)
        with patch('coastal_prepare.prepare_component502_claim',
                   side_effect=AssertionError('existing selected registry was recomputed')):
            self.assertEqual(S.prepare_coastal_claims(world, inventory=inventory), (expected,))
        with self.assertRaisesRegex(S.CoastalGeometryError, 'does not match its selection'):
            S.prepare_coastal_claims(world, inventory=inventory,
                                     selected_road_ids=(S.COMPONENT501_ROAD,))

    def test_selected_registry_dispatches_component501_only_when_explicit(self):
        world = SimpleNamespace(); inventory = {'looseWetCellIndices': (4, 5)}
        expected = SimpleNamespace(claim_id='coastal-501', road_ids=(S.COMPONENT501_ROAD,))
        with patch('coastal_prepare.prepare_component501_claim', return_value=expected) as prepare, \
             patch('coastal_prepare.prepare_component502_claim',
                   side_effect=AssertionError('component 502 was dispatched')):
            actual = S.prepare_coastal_claims(
                world, content='content', inventory=inventory,
                selected_road_ids=(S.COMPONENT501_ROAD,))
        self.assertEqual(actual, (expected,))
        prepare.assert_called_once_with(world, inventory, content='content')

    def test_selected_registry_rejects_an_empty_selection_before_preparation(self):
        with self.assertRaisesRegex(S.CoastalGeometryError, 'list is empty'):
            S.prepare_coastal_claims(SimpleNamespace(), inventory={}, selected_road_ids=())

    def test_discontinuous_contact_requires_exact_grouped_cell_ownership(self):
        surface = S.road_surface('Walk_Grouped', 'coastal-arch', 'road', self.straight_road(), 1.,
                                 1., 11., S._ConstantProfile(2.))
        accepted = {'acceptanceAuthority': True, 'clear': True}
        evidence = {
            'capsuleCoverage': accepted, 'fullWidthJoins': accepted, 'terrainClearance': accepted,
            'emittedWater': {'acceptanceAuthority': True, 'clear': False,
                             'pureSea': True, 'continuous': False, 'clearanceClear': True,
                             'continuousStationIntervalsMetres': [[3., 4.], [6., 8.]]},
            'multiContactOwnership': {**accepted, 'outerJoinOnly': True,
                                      'contactIntervalsMetres': [[3., 4.], [6., 8.]],
                                      'ownedLooseWetCells': [101, 102]},
        }
        claim = S.CoastalClaim('grouped', 509, ('road',), (3., 8.), (1., 10.), (surface,),
                               loose_wet_cells=(102, 101), evidence=evidence)
        self.assertTrue(claim.source_ready)
        self.assertIs(S.validate_claim(claim), claim)
        wrong = dict(evidence)
        wrong['multiContactOwnership'] = {**wrong['multiContactOwnership'],
                                          'ownedLooseWetCells': [101]}
        with self.assertRaisesRegex(S.CoastalGeometryError, 'exact grouped ownership'):
            S.validate_claim(S.CoastalClaim(
                'wrong-group', 509, ('road',), (3., 8.), (1., 10.), (surface,),
                loose_wet_cells=(101, 102), evidence=wrong))


if __name__ == '__main__':
    unittest.main()
