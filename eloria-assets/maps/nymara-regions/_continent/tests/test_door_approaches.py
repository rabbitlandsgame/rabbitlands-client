import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import door_approaches as D

DOOR = np.array([1207.01, 1181.42])


def world(owner=0, height=7.5, wet=False):
    x = np.arange(0., 2000., 2.); z = np.arange(0., 2000., 2.)
    mask = np.full((len(z), len(x)), wet, bool)
    return SimpleNamespace(ids=['verdant_stair', 'mirrorhold'], x=x, z=z, x0=0., z0=0., water={'mask': mask},
                           owner_at=lambda px, pz: owner, height_at=lambda px, pz: height)


@patch.dict(D.RETAINED_ROAD_ENDS, {}, clear=True)      # object-anchored ends need composed content: RetainedRoadEndTests
class DoorApproachTests(unittest.TestCase):
    def test_the_shrine_road_ends_on_dry_ground_north_of_the_pavilion(self):
        w = world(); content = SimpleNamespace()
        report = D.prepare_door_approaches(w, content)
        end = content.door_road_ends[('verdant_stair', 'nine-lost-door')]
        self.assertEqual(end.tolist(), [1201.0, 1173.0])     # R1: outside the river setback, west-north-west of the threshold
        self.assertLess(end[1], DOOR[1])                    # north of the door (smaller z)
        self.assertLess(np.linalg.norm(end - DOOR), D.MAXIMUM_DOOR_DISTANCE_METRES)
        self.assertEqual(report['roadEnds'], {'verdant_stair:nine-lost-door': [1201.0, 1173.0]})
        self.assertIs(w.door_approaches, report)
        self.assertTrue(np.array_equal(D.door_road_end(content, 'verdant_stair', 'nine-lost-door', DOOR), end))

    def test_a_server_portal_beside_the_pinned_door_shares_its_road_end(self):
        content = SimpleNamespace(door_road_ends={('verdant_stair', 'nine-lost-door'): np.array([1206.5, 1175.5])})
        shrine = np.array([1207.3, 1181.2])                   # maps.txt portal line 349, the same shrine door
        self.assertEqual(D.door_road_end_near(content, 'verdant_stair', shrine).tolist(), [1206.5, 1175.5])
        far = np.array([1300., 1300.])
        self.assertTrue(np.array_equal(D.door_road_end_near(content, 'verdant_stair', far), far))
        self.assertTrue(np.array_equal(D.door_road_end_near(content, 'mirrorhold', shrine), shrine))
        self.assertTrue(np.array_equal(D.door_road_end_near(SimpleNamespace(), 'verdant_stair', shrine), shrine))

    def test_a_server_only_portal_with_its_own_pin_is_routed_to_it_not_to_the_neighbouring_door(self):
        content = SimpleNamespace(door_road_ends={('amberwood', 'gate-undercroft-stair'): np.array([616.5, 589.5])},
                                  server_road_ends={('amberwood', 'amberwood', 'amberwood_estate'): np.array([600., 590.])})
        estate = np.array([608., 590.])
        # The estate door is 8.5 m from the undercroft pin and would share it by distance; its own pin wins.
        self.assertEqual(D.server_road_end(content, 'amberwood', estate, 'amberwood', 'amberwood_estate').tolist(), [600., 590.])
        self.assertIsNone(D.server_road_end(content, 'amberwood', estate, 'amberwood', 'amberwood_secrets'))
        self.assertEqual(D.door_road_end_near(content, 'amberwood', estate).tolist(), [616.5, 589.5])
        # Another entrance to the same map, out of the pin's reach, keeps the default handling.
        self.assertIsNone(D.server_road_end(content, 'amberwood', np.array([640., 590.]), 'amberwood', 'amberwood_estate'))

    def test_a_map_pair_with_several_entrances_serves_each_portal_from_the_pin_within_reach(self):
        content = SimpleNamespace(server_road_ends={('sunmane_steppe', 'sunmane_steppe', 'sunmane_steppe_secrets'): [np.array([1216., 732.]), np.array([1196., 760.]), np.array([1232., 734.])]})
        banner = np.array([1214.1, 743.2]); spring = np.array([1202.3, 751.6]); vault = np.array([1171.1, 701.1]); mill = np.array([1226., 744.])
        self.assertEqual(D.server_road_end(content, 'sunmane_steppe', banner, 'sunmane_steppe', 'sunmane_steppe_secrets').tolist(), [1216., 732.])
        self.assertEqual(D.server_road_end(content, 'sunmane_steppe', spring, 'sunmane_steppe', 'sunmane_steppe_secrets').tolist(), [1196., 760.])
        # R1 moved the spring pin out of the river setback; it still serves the spring from within reach.
        moved = SimpleNamespace(server_road_ends={key: [np.asarray(p, float) for p in pins] for key, pins in D.SERVER_ROAD_ENDS.items() if key[0] == 'sunmane_steppe'})
        self.assertEqual(D.server_road_end(moved, 'sunmane_steppe', spring, 'sunmane_steppe', 'sunmane_steppe_secrets').tolist(), [1201.5, 761.5])
        self.assertEqual(D.server_road_end(content, 'sunmane_steppe', mill, 'sunmane_steppe', 'sunmane_steppe_secrets').tolist(), [1232., 734.])
        # The hall vault, out of both pins' reach, keeps the default handling.
        self.assertIsNone(D.server_road_end(content, 'sunmane_steppe', vault, 'sunmane_steppe', 'sunmane_steppe_secrets'))
        # prepare_door_approaches keeps every pin of a pair and reports them all.
        w = world(); w.ids = ['sunmane_steppe']
        prepared = SimpleNamespace()
        D.prepare_door_approaches(w, prepared)
        self.assertEqual(len(prepared.server_road_ends[('sunmane_steppe', 'sunmane_steppe', 'sunmane_steppe_secrets')]), 3)
        self.assertEqual(w.door_approaches['serverRoadEnds']['sunmane_steppe:sunmane_steppe->sunmane_steppe_secrets'], [[1216., 732.], [1201.5, 761.5], [1232., 734.]])

    def test_a_designed_climb_lists_its_waypoints_in_order_and_other_doors_none(self):
        w = world(); w.ids = ['whitehorn_range']
        prepared = SimpleNamespace()
        with patch.dict(D.DOOR_ROAD_WAYPOINTS, {('whitehorn_range', 'whitehorn-glacier-temple-door'): [(500., 300.), (520., 200.)]}, clear=True),              patch.dict(D.RETAINED_DOOR_ROAD_WAYPOINTS, {}, clear=True):
            D.prepare_door_approaches(w, prepared)
        self.assertEqual([p.tolist() for p in D.door_road_waypoints(prepared, 'whitehorn_range', 'whitehorn-glacier-temple-door')], [[500., 300.], [520., 200.]])
        self.assertEqual(D.door_road_waypoints(prepared, 'whitehorn_range', 'whitehorn-mine-adit'), [])
        self.assertEqual(w.door_approaches['waypoints'], {'whitehorn_range:whitehorn-glacier-temple-door': [[500., 300.], [520., 200.]]})

    def test_source_frame_waypoints_follow_the_retained_transform(self):
        w = world(); w.ids = ['whitehorn_range']
        w.plan = {'retained_transforms': {'whitehorn_range': {'translation': [477., 70., 272.], 'squeeze_z': .85, 'about_z': 60.}}}
        prepared = SimpleNamespace()
        temple = ('whitehorn_range', 'whitehorn-glacier-temple-door')
        with patch.dict(D.DOOR_ROAD_WAYPOINTS, {}, clear=True), patch.dict(D.RETAINED_DOOR_ROAD_WAYPOINTS, {temple: [(70., 40.), (76., -192.)]}, clear=True):
            D.prepare_door_approaches(w, prepared)
        points = [p.tolist() for p in D.door_road_waypoints(prepared, 'whitehorn_range', 'whitehorn-glacier-temple-door')]
        # x is translated; z is squeezed about source row 60 then translated: 272 + 60 + (z - 60) * .85.
        np.testing.assert_allclose(points, [[547., 315.], [553., 117.8]])
        # A rigid list transform is a plain translation.
        w.plan = {'retained_transforms': {'whitehorn_range': [477., 70., 272.]}}
        with patch.dict(D.DOOR_ROAD_WAYPOINTS, {}, clear=True), patch.dict(D.RETAINED_DOOR_ROAD_WAYPOINTS, {temple: [(70., 40.)]}, clear=True):
            D.prepare_door_approaches(w, SimpleNamespace())
        self.assertEqual(w.door_approaches['waypoints'], {'whitehorn_range:whitehorn-glacier-temple-door': [[547., 312.]]})
        # Without a transform the source frame has no place in the continent.
        w.plan = {}
        with patch.dict(D.DOOR_ROAD_WAYPOINTS, {}, clear=True), patch.dict(D.RETAINED_DOOR_ROAD_WAYPOINTS, {temple: [(70., 40.)]}, clear=True):
            with self.assertRaisesRegex(ValueError, 'retained transform'):
                D.prepare_door_approaches(w, SimpleNamespace())

    def test_doors_without_a_pin_keep_their_own_point(self):
        content = SimpleNamespace(door_road_ends={})
        self.assertTrue(np.array_equal(D.door_road_end(content, 'verdant_stair', 'other-door', DOOR), DOOR))
        self.assertTrue(np.array_equal(D.door_road_end(SimpleNamespace(), 'verdant_stair', 'nine-lost-door', DOOR), DOOR))

    def test_pins_outside_the_territory_under_water_or_far_from_the_door_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside its territory'):
            D.prepare_door_approaches(world(owner=1), SimpleNamespace())
        with self.assertRaisesRegex(ValueError, 'not dry ground'):
            D.prepare_door_approaches(world(height=.2), SimpleNamespace())
        with self.assertRaisesRegex(ValueError, 'stands in water'):
            D.prepare_door_approaches(world(wet=True), SimpleNamespace())
        content = SimpleNamespace(door_road_ends={('verdant_stair', 'nine-lost-door'): np.array([1206.5, 1175.5])})
        with self.assertRaisesRegex(ValueError, 'further than'):
            D.door_road_end(content, 'verdant_stair', 'nine-lost-door', DOOR + [0., 20.])

    def test_other_territories_are_untouched(self):
        w = SimpleNamespace(ids=['mirrorhold']); content = SimpleNamespace()
        self.assertEqual(D.prepare_door_approaches(w, content)['roadEnds'], {})
        self.assertEqual(content.door_road_ends, {})


MOORS_PASS = ('whitehorn_range', 'grey_moors--whitehorn_range')
EAST_PASS = ('whitehorn_range', 'amethyst_barrens--whitehorn_range')


def seam_patches(authored=None, retained=None):
    """The four waypoint tables with only the seam entries under test in them."""
    return (patch.multiple(D, RETAINED_DOOR_ROAD_WAYPOINTS={}, DOOR_ROAD_WAYPOINTS={}),
            patch.dict(D.SEAM_ROAD_WAYPOINTS, authored or {}, clear=True),
            patch.dict(D.RETAINED_SEAM_ROAD_WAYPOINTS, retained or {}, clear=True))


@patch.dict(D.RETAINED_ROAD_ENDS, {}, clear=True)
class SeamRoadWaypointTests(unittest.TestCase):
    def test_an_authored_pass_lists_its_waypoints_in_order_and_other_seams_have_none(self):
        w = world(); w.ids = ['whitehorn_range', 'grey_moors']
        prepared = SimpleNamespace()
        doors, authored, retained = seam_patches({MOORS_PASS: [(500., 300.), (520., 200.)]})
        with doors, authored, retained:
            D.prepare_door_approaches(w, prepared)
        self.assertEqual([p.tolist() for p in D.seam_road_waypoints(prepared, *MOORS_PASS)], [[500., 300.], [520., 200.]])
        # The other side of the same crossing, another crossing and an unprepared
        # content object are all straight runs from the hub to the terminal.
        self.assertEqual(D.seam_road_waypoints(prepared, 'grey_moors', 'grey_moors--whitehorn_range'), [])
        self.assertEqual(D.seam_road_waypoints(prepared, *EAST_PASS), [])
        self.assertEqual(D.seam_road_waypoints(SimpleNamespace(), *MOORS_PASS), [])
        self.assertEqual(w.door_approaches['seamWaypoints'], {'whitehorn_range:grey_moors--whitehorn_range': [[500., 300.], [520., 200.]]})
        self.assertEqual(w.door_approaches['waypoints'], {})            # door roads keep their own key

    def test_a_pass_authored_for_another_territory_is_left_alone(self):
        w = world(); w.ids = ['grey_moors']
        prepared = SimpleNamespace()
        doors, authored, retained = seam_patches({MOORS_PASS: [(500., 300.)]})
        with doors, authored, retained:
            D.prepare_door_approaches(w, prepared)
        self.assertEqual(prepared.seam_road_waypoints, {})
        self.assertEqual(w.door_approaches['seamWaypoints'], {})

    def test_source_frame_seam_waypoints_follow_the_retained_transform(self):
        w = world(); w.ids = ['whitehorn_range']
        w.plan = {'retained_transforms': {'whitehorn_range': {'translation': [477., 70., 272.], 'squeeze_z': .85, 'about_z': 60.}}}
        prepared = SimpleNamespace()
        doors, authored, retained = seam_patches(retained={EAST_PASS: [(70., 40.)]})
        with doors, authored, retained:
            D.prepare_door_approaches(w, prepared)
        # x is translated; z is squeezed about source row 60 then translated: 272 + 60 + (z - 60) * .85.
        np.testing.assert_allclose([p.tolist() for p in D.seam_road_waypoints(prepared, *EAST_PASS)], [[547., 315.]])
        self.assertEqual(list(w.door_approaches['seamWaypoints']), ['whitehorn_range:amethyst_barrens--whitehorn_range'])
        np.testing.assert_allclose(w.door_approaches['seamWaypoints']['whitehorn_range:amethyst_barrens--whitehorn_range'], [[547., 315.]])
        # Without a transform the source frame has no place in the continent.
        w.plan = {}
        doors, authored, retained = seam_patches(retained={EAST_PASS: [(70., 40.)]})
        with doors, authored, retained:
            with self.assertRaisesRegex(ValueError, 'amethyst_barrens--whitehorn_range: source-frame waypoints need'):
                D.prepare_door_approaches(w, SimpleNamespace())

    def test_waypoints_outside_the_territory_in_water_or_not_dry_are_refused(self):
        def prepare(**terrain):
            w = world(**terrain); w.ids = ['whitehorn_range']
            doors, authored, retained = seam_patches({MOORS_PASS: [(500., 300.), (520., 200.)]})
            with doors, authored, retained:
                D.prepare_door_approaches(w, SimpleNamespace())
        prepare()                                                       # dry ground inside the range is accepted
        with self.assertRaisesRegex(ValueError, 'grey_moors--whitehorn_range waypoint 0.*outside its territory'):
            prepare(owner=1)
        with self.assertRaisesRegex(ValueError, 'waypoint 0.*not dry ground'):
            prepare(height=.2)
        with self.assertRaisesRegex(ValueError, 'waypoint 0.*stands in water'):
            prepare(wet=True)


TEMPLE_DOOR = ('whitehorn_range', 'whitehorn-glacier-temple-door')
TURNED = {'translation': [534.5, 155., 320.], 'squeeze_x': .8, 'squeeze_z': .85, 'about_x': -14.5, 'about_z': 60.,
          'yaw_degrees': -34., 'datum': 'ground'}


def temple_content(region='whitehorn_range', node='Landmark_glacier_temple'):
    """Composed content holding one retained object whose bounds centre in x/z is (455, 120), and some scatter."""
    return SimpleNamespace(objects=[
        {'region': region, 'node': 'Grove_00001', 'low': np.array([0., 0., 0.]), 'high': np.array([2., 9., 2.])},
        {'region': region, 'node': node, 'low': np.array([440., 180., 100.]), 'high': np.array([470., 230., 140.])}])


def anchored(entries):
    """The retained road-end table holding only ``entries``, and no source-frame waypoints that need a transform."""
    return (patch.dict(D.RETAINED_ROAD_ENDS, entries, clear=True),
            patch.dict(D.RETAINED_DOOR_ROAD_WAYPOINTS, {}, clear=True),
            patch.dict(D.RETAINED_SEAM_ROAD_WAYPOINTS, {}, clear=True))


class RetainedRoadEndTests(unittest.TestCase):
    def test_the_temple_road_ends_at_the_foot_of_its_stair(self):
        self.assertEqual(D.RETAINED_ROAD_ENDS[TEMPLE_DOOR], ('Landmark_glacier_temple', (0.25, 13.5)))

    def test_an_anchored_end_stands_on_its_object_turned_with_the_layout_and_never_squeezed(self):
        w = world(); w.ids = ['whitehorn_range']; w.plan = {'retained_transforms': {'whitehorn_range': TURNED}}
        content = temple_content()
        ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (0.25, 15.5))})
        with ends, doors, seams:
            report = D.prepare_door_approaches(w, content)
        # Legacy +x (right) and +z (front) turned by -34 degrees: x east, z south, a positive yaw north towards east.
        c, s = np.cos(np.radians(-34.)), np.sin(np.radians(-34.))
        expected = np.array([455. + .25 * c - 15.5 * s, 120. + .25 * s + 15.5 * c])
        end = content.door_road_ends[TEMPLE_DOOR]
        np.testing.assert_allclose(end, expected, atol=1e-9)
        self.assertAlmostEqual(float(np.linalg.norm(end - [455., 120.])), float(np.hypot(.25, 15.5)), places=9)
        np.testing.assert_allclose(report['roadEnds']['whitehorn_range:whitehorn-glacier-temple-door'], expected, atol=1e-9)
        entry = report['retainedRoadEnds']['whitehorn_range:whitehorn-glacier-temple-door']
        self.assertEqual((entry['node'], entry['offset'], entry['pivot']), ('Landmark_glacier_temple', [.25, 15.5], [455., 120.]))
        # Served exactly as a ROAD_ENDS pin: the door road ends there while the door is within reach.
        door = expected + [0., -11.4]
        self.assertTrue(np.array_equal(D.door_road_end(content, *TEMPLE_DOOR, door), end))
        self.assertTrue(np.array_equal(D.door_road_end_near(content, 'whitehorn_range', door), end))
        with self.assertRaisesRegex(ValueError, 'further than'):
            D.door_road_end(content, *TEMPLE_DOOR, expected + [0., -20.])

    def test_without_a_turn_the_offset_runs_along_the_continent_axes(self):
        for transform in ([477., 70., 272.], {'translation': [477., 70., 272.], 'squeeze_z': .85, 'about_z': 60.}, None):
            w = world(); w.ids = ['whitehorn_range']
            w.plan = {'retained_transforms': {'whitehorn_range': transform}} if transform is not None else {}
            content = temple_content()
            ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (3., -4.))})
            with ends, doors, seams:
                D.prepare_door_approaches(w, content)
            self.assertEqual(content.door_road_ends[TEMPLE_DOOR].tolist(), [458., 116.])

    def test_a_missing_anchor_or_a_second_pin_is_refused(self):
        w = world(); w.ids = ['whitehorn_range']; w.plan = {}
        for content in (SimpleNamespace(), SimpleNamespace(objects=[]), temple_content(region='grey_moors'),
                        temple_content(node='Landmark_glacier_temple_ruin')):
            ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (0., 10.))})
            with ends, doors, seams, self.assertRaisesRegex(ValueError, 'anchored on Landmark_glacier_temple, which is not a retained object'):
                D.prepare_door_approaches(w, content)
        ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (0., 10.))})
        with ends, doors, seams, patch.dict(D.ROAD_ENDS, {TEMPLE_DOOR: (455., 130.)}):
            with self.assertRaisesRegex(ValueError, 'pinned twice'):
                D.prepare_door_approaches(w, temple_content())

    def test_an_anchored_end_outside_the_territory_under_water_or_not_dry_is_refused(self):
        for terrain, message in (({'owner': 1}, 'outside its territory'), ({'height': .2}, 'not dry ground'),
                                 ({'wet': True}, 'stands in water')):
            w = world(**terrain); w.ids = ['whitehorn_range']; w.plan = {}
            ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (0., 10.))})
            with ends, doors, seams, self.assertRaisesRegex(ValueError, 'whitehorn-glacier-temple-door: .*' + message):
                D.prepare_door_approaches(w, temple_content())

    def test_a_territory_the_continent_lacks_needs_no_anchor(self):
        w = world()                                                     # verdant_stair and mirrorhold only
        ends, doors, seams = anchored({TEMPLE_DOOR: ('Landmark_glacier_temple', (0., 10.))})
        with ends, doors, seams:
            report = D.prepare_door_approaches(w, SimpleNamespace())
        self.assertEqual(report['retainedRoadEnds'], {})


class FakeWorld:
    """A world whose router runs straight: ``stations`` points from a to b inclusive."""

    def __init__(self, stations=2):
        self.stations = stations
        self.calls = []

    def route(self, a, b, region=None, own=None):
        a = np.asarray(a, float); b = np.asarray(b, float)
        self.calls.append((a.tolist(), b.tolist(), region, own))
        return np.array([a + (b - a) * t for t in np.linspace(0., 1., self.stations)])


class RouteInLegsTests(unittest.TestCase):
    HUB = np.array([0., 0.])
    TERMINAL = np.array([3., 3.])

    def test_waypoints_become_legs_with_no_duplicated_joint(self):
        w = FakeWorld()
        legs = [self.HUB, np.array([1., 1.]), np.array([2., 2.]), self.TERMINAL]
        path = D.route_in_legs(w, legs, 'whitehorn_range', own={7})
        self.assertEqual(path.tolist(), [[0., 0.], [1., 1.], [2., 2.], [3., 3.]])
        self.assertEqual([(a, b) for a, b, _, _ in w.calls],
                         [([0., 0.], [1., 1.]), ([1., 1.], [2., 2.]), ([2., 2.], [3., 3.])])
        # The road's own solids ride the first leg only; every leg stays in its region.
        self.assertEqual([own for _, _, _, own in w.calls], [{7}, None, None])
        self.assertEqual({region for _, _, region, _ in w.calls}, {'whitehorn_range'})

    def test_a_leg_keeps_its_own_stations_and_drops_only_the_joint(self):
        path = D.route_in_legs(FakeWorld(stations=3), [self.HUB, np.array([1., 1.]), self.TERMINAL], 'whitehorn_range')
        self.assertEqual(path.tolist(), [[0., 0.], [.5, .5], [1., 1.], [2., 2.], [3., 3.]])

    def test_without_waypoints_the_road_is_the_single_route_it_always_was(self):
        expected = FakeWorld(stations=4).route(self.HUB, self.TERMINAL, region='whitehorn_range', own={7})
        w = FakeWorld(stations=4)
        path = D.route_in_legs(w, [self.HUB, self.TERMINAL], 'whitehorn_range', own={7})
        self.assertEqual(path.tolist(), expected.tolist())
        self.assertEqual(w.calls, [([0., 0.], [3., 3.], 'whitehorn_range', {7})])

    def test_the_legs_match_the_expression_the_door_roads_used(self):
        legs = [self.HUB, np.array([1., 1.]), self.TERMINAL]
        old = FakeWorld(stations=3)
        expected = np.vstack([old.route(a, b, region='amberwood')[:-1 if index < len(legs) - 2 else None]
                              for index, (a, b) in enumerate(zip(legs, legs[1:]))])
        self.assertEqual(D.route_in_legs(FakeWorld(stations=3), legs, 'amberwood').tolist(), expected.tolist())


if __name__ == '__main__':
    unittest.main()
