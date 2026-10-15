from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import shapely
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coastal_prepare as P
import sea_crossings as S


def component(seed, road_id, cells):
    return {"componentSeed": seed, "looseWetCells": tuple(cells),
            "roadIds": (road_id,), "fullWidthWaterRoadIds": (road_id,),
            "fullWidthWaterCells": ({"roadId": road_id, "looseWetCells": tuple(cells)},),
            "bounds": [0, 1, seed, seed+1]}


class OrdinaryCoastalPrepareTests(unittest.TestCase):
    def test_component501_fits_the_exact_caps_it_emits(self):
        caps = P.COMPONENT501_EMITTED_CAP_STATIONS_METRES
        outer = P.COMPONENT501_OUTER_LANDING_STATIONS_METRES
        road = {"id": S.COMPONENT501_ROAD, "width": 3.,
                "points": np.asarray([[0., 0., 0.], [600., 0., 0.]])}
        selected = component(999, S.COMPONENT501_ROAD, (3, 7, 9))
        inventory = {"components": (selected,), "shape": (2, 5)}
        world = SimpleNamespace(
            roads=(road,), water={"epoch": "before"},
            height=np.zeros((4, 4)), x=np.arange(4.), z=np.arange(4.),
            gx=np.zeros((4, 4)), gz=np.zeros((4, 4)),
            plan={"crossing_policy": {"deck_clearance_metres": .85}})
        authority = {"faces": np.empty((0, 3, 3))}
        sections = np.asarray([[[caps[0], 0., -3.], [caps[0], 0., 3.]],
                               [[caps[1], 0., -3.], [caps[1], 0., 3.]]])
        fit = SimpleNamespace(claim_id="coastal-501", left_deck_height_metres=1.,
                              right_deck_height_metres=2.)
        with patch.object(P, "_bounds_for_interval", return_value=(0., 0., 4., 4.)), \
             patch.object(P, "_water_authority", return_value=(authority, {"sea": ()})), \
             patch.object(P, "_flat_surface", return_value=object()), \
             patch.object(P, "_exact_water_evidence", return_value={
                 "clear": True, "continuous": True, "pureSea": True,
                 "wetExtentMetres": (outer[0]+6., outer[1]-6.)}), \
             patch.object(P.S, "indexed_road_union_surface",
                          return_value=(SimpleNamespace(sections=sections), {}, {})) as preview, \
             patch.object(P, "_protected_nodes", return_value=()), \
             patch.object(P.F, "height_sha256", return_value="source"), \
             patch.object(P.S, "coastal_bank_fit_request", return_value=object()) as request, \
             patch.object(P.F, "fit_coastal_banks", return_value=(fit,)), \
             patch.object(P.L, "water_fields", return_value={"epoch": "after"}), \
             patch.object(P.B, "_same_water_authority", return_value=(True, {})), \
             patch.object(P.S, "crop_terrain", return_value=object()), \
             patch.object(P.BP, "arch_rise", return_value=.2125), \
             patch.object(P.S, "prepare_component501_surface",
                          side_effect=RuntimeError("surface captured")) as surface:
            with self.assertRaisesRegex(RuntimeError, "surface captured"):
                P.prepare_component501_claim(world, inventory)
        self.assertEqual(preview.call_args.args[5:7], caps)
        np.testing.assert_array_equal(preview.call_args.args[7], caps)
        self.assertEqual(request.call_args.args[2:4], caps)
        np.testing.assert_array_equal(request.call_args.kwargs["join_sections"], sections)
        self.assertEqual(surface.call_args.args[1], caps)

    def test_component501_binding_uses_stable_road_and_complete_live_cells(self):
        selected = component(999, S.COMPONENT501_ROAD, (9, 3, 7))
        selected['looseWetCells'] = (3, 7, 9)
        selected['fullWidthWaterCells'] = ({'roadId': S.COMPONENT501_ROAD,
                                            'looseWetCells': (3, 7, 9)},)
        inventory = {'components': (component(1, 'other', (1,)), selected)}
        self.assertIs(P._component501_inventory_member(inventory), selected)
        duplicate = dict(selected); duplicate['componentSeed'] = 1000
        with self.assertRaisesRegex(S.CoastalGeometryError, 'ownership is ambiguous'):
            P._component501_inventory_member({'components': (selected, duplicate)})
        incomplete = dict(selected)
        incomplete['fullWidthWaterCells'] = ({'roadId': S.COMPONENT501_ROAD,
                                               'looseWetCells': (3, 7)},)
        with self.assertRaisesRegex(S.CoastalGeometryError, 'binding is incomplete'):
            P._component501_inventory_member({'components': (incomplete,)})
        multi = dict(component(1001, S.COMPONENT501_ROAD, (21,)))
        multi['roadIds'] = (S.COMPONENT501_ROAD, 'side-road')
        multi['fullWidthWaterRoadIds'] = multi['roadIds']
        with self.assertRaisesRegex(S.CoastalGeometryError, 'outside its exact single-road'):
            P._component501_inventory_member({'components': (selected, multi)})

    def test_component502_binding_uses_stable_road_and_complete_live_cells(self):
        selected = component(1610029, S.COMPONENT502_ROAD, (4, 7, 11))
        inventory = {'components': (component(1, 'other', (1,)), selected)}
        self.assertIs(P._component502_inventory_member(inventory), selected)
        duplicate = dict(selected); duplicate['componentSeed'] = 1610030
        with self.assertRaisesRegex(S.CoastalGeometryError, 'ownership is ambiguous'):
            P._component502_inventory_member({'components': (selected, duplicate)})
        split = dict(selected)
        split['roadIds'] = (S.COMPONENT502_ROAD, 'junction-road')
        split['fullWidthWaterRoadIds'] = split['roadIds']
        with self.assertRaisesRegex(S.CoastalGeometryError, 'outside its exact single-road'):
            P._component502_inventory_member({'components': (split,)})

    def test_component502_claim_uses_recovered_one_bank_terminal_recipe(self):
        total = 18.903632956135098
        wet = (12.322478618444908, total)
        road = {'id': S.COMPONENT502_ROAD, 'width': 1.65,
                'points': np.asarray([[0., 0., 0.], [total, 0., 0.]])}
        selected = component(1610029, S.COMPONENT502_ROAD, (4, 7, 11))
        inventory = {'components': (selected,), 'shape': (2, 6)}
        world = SimpleNamespace(
            roads=(road,), water={'epoch': 'current'}, height=np.zeros((4, 4)),
            x=np.arange(4.), z=np.arange(4.), x0=0., z0=0.,
            plan={'crossing_policy': {'deck_clearance_metres': .85}})
        accepted = {'acceptanceAuthority': True, 'clear': True}
        probe_water = {**accepted, 'continuous': True, 'pureSea': True,
                       'wetExtentMetres': wet}
        final_water = {**probe_water, 'pieces': ()}
        exact = {'capsuleCoverage': accepted, 'emittedWater': final_water,
                 'fullWidthJoins': accepted, 'terrainClearance': accepted,
                 'supportContact': accepted, 'terminalPlatform': accepted}
        surface = SimpleNamespace(); support = SimpleNamespace()
        solved = {'evidence': exact}
        with patch.object(P, '_cell_centres', return_value=np.asarray([[13., 0.]])), \
             patch.object(P, '_nearest_stations', return_value=np.asarray([13.])), \
             patch.object(P, '_bounds_for_interval', return_value=(0, 3, 0, 3)), \
             patch.object(P, '_water_authority', return_value=({}, {'sea': ()})), \
             patch.object(P.S, 'indexed_road_union_surface',
                          return_value=(SimpleNamespace(), {}, {})) as probe, \
             patch.object(P, '_exact_water_evidence', return_value=probe_water), \
             patch.object(P, '_owned_water_evidence', side_effect=(probe_water, final_water)), \
             patch.object(P.S, 'crop_terrain', return_value='terrain'), \
             patch.object(P.BP, 'arch_rise', return_value=.2125), \
             patch.object(P.S, 'prepare_component502_surface',
                          return_value=(surface, support, {'profile': 'current'},
                                        {'coverage': 'current'}, solved)) as helper, \
             patch.object(P.S, 'validate_claim', side_effect=lambda claim: claim):
            claim = P.prepare_component502_claim(world, inventory)
        self.assertEqual(probe.call_args.kwargs['terminal_sides'], ('right',))
        self.assertEqual(helper.call_args.args[1], wet[0]-P.COMPONENT502_LANDING_METRES)
        self.assertEqual(helper.call_args.args[1], 7.197478618444908)
        self.assertEqual(helper.call_args.args[2], wet)
        self.assertEqual(helper.call_args.args[5:7], (.85, .2125))
        self.assertEqual(claim.claim_id, 'coastal-502')
        self.assertEqual(claim.road_ids, (S.COMPONENT502_ROAD,))
        self.assertEqual(claim.loose_wet_cells, (4, 7, 11))
        self.assertEqual(claim.terminal_sides, ('right',))
        self.assertEqual(claim.supports, (support,))

    def test_wet_search_uses_footprint_probe_without_claiming_bank_caps(self):
        road = {"id": "bent-road", "width": 3.3,
                "points": np.asarray([[0., 0., 0.], [4., 0., 0.], [5., 0., 2.]])}
        expected = object()
        with patch.object(P.S, "indexed_road_union_probe_surface",
                          return_value=(expected, {"joinCapsValidated": False}, {})) as probe, \
             patch.object(P.S, "indexed_road_union_surface",
                          side_effect=AssertionError("wet search used strict bank-cap producer")):
            actual = P._flat_surface("Probe_Bent", road, 1.25, 4.75)
        self.assertIs(actual, expected)
        probe.assert_called_once()
        self.assertEqual(probe.call_args.args[1], "coastal-wet-search")

    def test_inventory_selection_excludes_owned_and_multi_road_but_keeps_separated_same_road(self):
        ordinary = "discovery-crownwater-907"
        inventory = {"components": (
            component(1, S.COMPONENT500_ROAD, (1,)),
            {"componentSeed": 2, "looseWetCells": (2,), "roadIds": ("a", "b"),
             "fullWidthWaterRoadIds": ("a", "b"), "fullWidthWaterCells": ()},
            component(3, ordinary, (3, 4)),
            component(8, ordinary, (8, 9)),
            component(12, "door-crownwater-cistern-stair", (12,))),
        }
        selected = P._eligible_components(inventory, P.DEFAULT_EXCLUDED_ROADS)
        self.assertEqual([value[0]["componentSeed"] for value in selected], [3, 8])
        self.assertNotEqual(P._claim_id(ordinary, (3, 4)), P._claim_id(ordinary, (8, 9)))
        self.assertEqual(P._claim_id(ordinary, (4, 3)), P._claim_id(ordinary, (3, 4)))

    def test_only_the_two_authorized_hatchery_contacts_share_outer_banks(self):
        first = component(2311067, P.HATCHERY_GROUP_ROAD, (11, 12))
        first["bounds"] = [3, 5, 7, 9]
        second = component(2321563, P.HATCHERY_GROUP_ROAD, (20, 21, 22, 23))
        second["bounds"] = [4, 8, 10, 13]
        unrelated = component(8, "discovery-crownwater-907", (30, 31))
        selected = P._eligible_components(
            {"components": (first, unrelated, second)}, P.DEFAULT_EXCLUDED_ROADS)
        grouped = P._group_explicit_components(selected)
        self.assertEqual(len(grouped), 2)
        hatchery = next(value for value, _ in grouped
                         if value["roadIds"] == (P.HATCHERY_GROUP_ROAD,))
        self.assertEqual(hatchery["groupedComponentSeeds"], (2311067, 2321563))
        self.assertEqual(hatchery["looseWetCells"], (11, 12, 20, 21, 22, 23))
        self.assertEqual(hatchery["bounds"], [3, 8, 7, 13])
        self.assertEqual(next(binding for value, binding in grouped
                              if value is hatchery)["looseWetCells"],
                         hatchery["looseWetCells"])

    def test_dry_join_checks_the_complete_full_width_section_against_actual_water(self):
        points = np.asarray([[0., 0., 5.], [30., 0., 5.]])
        water = box(10., 0., 20., 10.)
        left, left_tested = P._dry_join(points, 4., 10., -1, water)
        right, right_tested = P._dry_join(points, 4., 20., 1, water)
        self.assertEqual(left, 9.875)
        self.assertEqual(right, 20.125)
        self.assertTrue(left_tested[-1]["waterIntersectionEmpty"])
        self.assertTrue(right_tested[-1]["waterIntersectionEmpty"])
        left_section = S._section(points, S.cumulative_stations(points), left, 4.)
        right_section = S._section(points, S.cumulative_stations(points), right, 4.)
        self.assertTrue(LineStringXZ(left_section).intersection(water).is_empty)
        self.assertTrue(LineStringXZ(right_section).intersection(water).is_empty)

    def test_positive_crown_surface_uses_one_indexed_floor_authority(self):
        road = {"id": "ordinary", "width": 3., "points": [[0., 0., 5.], [40., 0., 5.]]}
        plan = {"claimId": "ordinary-test", "road": road,
                "points": np.asarray(road["points"], float),
                "wetExtentMetres": (12., 28.), "joinStationsMetres": (10., 30.)}
        fit = SimpleNamespace(left_deck_height_metres=1., right_deck_height_metres=1.)
        groups = {"sea": np.asarray([[[12., 0., 2.], [12., 0., 8.], [28., 0., 2.]],
                                      [[28., 0., 2.], [12., 0., 8.], [28., 0., 8.]],
                                      [[0., 100., 0.], [0., 100., 1.], [1., 100., 0.]]]),
                  "river": np.empty((0, 3, 3)), "lake": np.empty((0, 3, 3))}
        world = SimpleNamespace(
            plan={"crossing_policy": {"deck_clearance_metres": .85}, "rivers": (), "lakes": ()},
            x=np.arange(0., 42., 2.), z=np.arange(0., 12., 2.),
            height=np.full((6, 21), .75))
        surface, metadata, authority, solve = P._build_surface(world, plan, fit, groups)
        self.assertGreater(float(surface.encoded_triangles[:, :, 1].max()), 1.)
        self.assertLess(float(surface.encoded_triangles[:, :, 1].max()), 2.)
        self.assertEqual(metadata["topology"],
                         "one indexed encoded bounded road union partitioned into height zones")
        coverage = S.partitioned_road_outline_coverage_evidence(
            surface, authority["nominalOutlineRecords"], authority["sourcePartitionXZ"])
        self.assertTrue(coverage["complete"])
        self.assertTrue(solve["evidence"]["capsuleCoverage"]["clear"])
        self.assertTrue(solve["evidence"]["fullWidthJoins"]["clear"])
        for station in np.unique(surface.triangle_stations):
            values = surface.encoded_triangles.reshape(-1, 3)[surface.triangle_stations.reshape(-1) == station, 1]
            self.assertEqual(len(np.unique(values)), 1)

    def test_wet_cell_coverage_uses_actual_positive_area_not_projected_centre_station(self):
        world = SimpleNamespace(x=np.arange(0., 6., 2.), x0=0., z0=0.)
        np.testing.assert_allclose(P._cell_centres(world, (2, 2), (0, 3)),
                                   [[.5, .5], [1.5, 1.5]])
        evidence = {"pieces": ({"xz": np.asarray([[.8, .2], [1., .2], [1., .8], [.8, .8]])},)}
        P._require_wet_cell_coverage(world, (2, 2), (0,), evidence, "road")
        with self.assertRaisesRegex(S.CoastalGeometryError, "misses an owned wet cell"):
            P._require_wet_cell_coverage(world, (2, 2), (1,), evidence, "road")

    def test_owned_water_selection_keeps_separate_probe_spans_independent(self):
        world = SimpleNamespace(x0=0., z0=0.)
        first = {"xz": np.asarray([[.1, .1], [.9, .1], [.9, .9], [.1, .9]]),
                 "stations": np.asarray([10., 12., 12., 10.]), "kind": "sea",
                 "areaSquareMetres": .64}
        continuation = {"xz": np.asarray([[2.1, .1], [2.9, .1], [2.9, .9], [2.1, .9]]),
                        "stations": np.asarray([12., 14., 14., 12.]), "kind": "sea",
                        "areaSquareMetres": .64}
        second = {"xz": np.asarray([[1.1, 1.1], [1.9, 1.1], [1.9, 1.9], [1.1, 1.9]]),
                  "stations": np.asarray([20., 22., 22., 20.]), "kind": "sea",
                  "areaSquareMetres": .64}
        probe = {"pieces": (first, continuation, second), "clearanceClear": True}
        selected = P._owned_water_evidence(world, (2, 2), (0,), probe, "road")
        self.assertTrue(selected["clear"])
        self.assertEqual(selected["wetExtentMetres"], [10., 14.])
        self.assertEqual(len(selected["pieces"]), 2)
        other = P._owned_water_evidence(world, (2, 2), (3,), probe, "road")
        self.assertEqual(other["wetExtentMetres"], [20., 22.])

    def test_atomic_factory_restores_height_and_water_when_joint_fit_fails(self):
        world = SimpleNamespace(height=np.ones((3, 3)), water={"mask": np.zeros((3, 3), bool)},
                                gx=np.zeros((3, 3)), gz=np.zeros((3, 3)))
        inventory = {"components": (component(3, "ordinary", (3,)),)}
        plan = {"claimId": "ordinary-a", "component": inventory["components"][0],
                "road": {"id": "ordinary"}, "bounds": (0, 2, 0, 2)}
        source_height = world.height.copy(); source_water = world.water

        def fail(world_arg, requests, *, content=None):
            world_arg.height[1, 1] = 9.
            raise ValueError("infeasible")

        authority = {"faces": np.empty((0, 3, 3)), "sourceCells": np.empty(0, int),
                     "sourceWetMask": np.zeros((1, 1), bool),
                     "sourceWetSurface": np.empty(0), "bounds": [0, 2, 0, 2]}
        with patch.object(P, "_plan_component", return_value=plan), \
             patch.object(P, "_water_authority", return_value=(authority, {})), \
             patch.object(P, "_protected_nodes", return_value=()), \
             patch.object(P, "_request", return_value={"claimId": "ordinary-a"}), \
             patch.object(P.F, "height_sha256", return_value="source"), \
             patch.object(P.F, "fit_coastal_banks", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "infeasible"):
                P.prepare_ordinary_single_road_claims(world, inventory)
        np.testing.assert_array_equal(world.height, source_height)
        self.assertIs(world.water, source_water)

    def test_factory_fits_all_ordinary_requests_and_regenerates_water_once(self):
        items = (component(3, "ordinary-a", (3, 4)), component(8, "ordinary-b", (8, 9)))
        world = SimpleNamespace(height=np.ones((3, 3)), water={"epoch": "before"},
                                gx=np.zeros((3, 3)), gz=np.zeros((3, 3)), plan={})
        inventory = {"components": items}
        plans = [{"claimId": f"claim-{index}", "component": item,
                  "road": {"id": item["roadIds"][0]}, "bounds": (0, 2, 0, 2)}
                 for index, item in enumerate(items)]
        authority = {"faces": np.empty((0, 3, 3)), "sourceCells": np.empty(0, int),
                     "sourceWetMask": np.zeros((1, 1), bool),
                     "sourceWetSurface": np.empty(0), "bounds": [0, 2, 0, 2]}
        fits = tuple(SimpleNamespace(claim_id=plan["claimId"]) for plan in plans)
        claims = {plan["claimId"]: SimpleNamespace(
            claim_id=plan["claimId"], loose_wet_cells=tuple(plan["component"]["looseWetCells"]))
            for plan in plans}
        with patch.object(P, "_plan_component", side_effect=plans), \
             patch.object(P, "_water_authority", return_value=(authority, {})), \
             patch.object(P, "_protected_nodes", return_value=()), \
             patch.object(P, "_request", side_effect=lambda world, plan, pins, source: {"claimId": plan["claimId"]}), \
             patch.object(P.F, "height_sha256", return_value="source"), \
             patch.object(P.F, "fit_coastal_banks", return_value=fits) as solve, \
             patch.object(P.L, "water_fields", return_value={"epoch": "after"}) as water, \
             patch.object(P, "_claim", side_effect=lambda world, plan, fit, before, after: claims[plan["claimId"]]):
            result = P.prepare_ordinary_single_road_claims(world, inventory)
        self.assertEqual(tuple(value.claim_id for value in result), ("claim-0", "claim-1"))
        self.assertEqual(len(solve.call_args.args[1]), 2)
        water.assert_called_once()
        self.assertEqual(world.water, {"epoch": "after"})


def LineStringXZ(section):
    return shapely.LineString(np.asarray(section)[:, [0, 2]])


if __name__ == "__main__":
    unittest.main()
