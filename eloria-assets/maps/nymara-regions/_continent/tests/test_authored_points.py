"""Authored points: records pinned to reachable ground from the plan."""
import types
import unittest

import numpy as np

import authored_points as A


def world(plan):
    return types.SimpleNamespace(plan=plan, ids=['west', 'east'],
        owner_at=lambda x, z: 0 if x < 100 else 1,
        height_at=lambda x, z: 5. if z < 500 else .2)


ENTRY = {'region': 'west', 'tile': [120, 88], 'point': [40., 60.], 'record': 'maps.txt:9:door:west->west_secrets',
         'reason': 'the door stands on a cliff face; its foot is open ground'}


class AuthoredPointTests(unittest.TestCase):
    def test_a_point_pins_its_record_and_reports_it(self):
        content = types.SimpleNamespace()
        w = world({'regions': [{'id': 'west'}, {'id': 'east'}], 'authored_points': [ENTRY]})
        report = A.prepare_authored_points(w, content)
        np.testing.assert_array_equal(content.authored_server_points[('west', (120, 88))], [40., 5., 60.])
        self.assertEqual(report['points'][0]['record'], ENTRY['record'])
        w.height_at = lambda x, z: 7.5
        A.refresh_authored_point_heights(w, content)
        self.assertEqual(float(content.authored_server_points[('west', (120, 88))][1]), 7.5)
        self.assertEqual(w.authored_points['points'][0]['point'], [40., 7.5, 60.])

    def test_a_point_may_keep_its_roads_on_the_entrance(self):
        import content as CT
        content = types.SimpleNamespace()
        keep = dict(ENTRY, roads='entrance')
        other = dict(ENTRY, tile=[121, 88], point=[42., 60.])
        w = world({'regions': [{'id': 'west'}, {'id': 'east'}], 'authored_points': [keep, other]})
        report = A.prepare_authored_points(w, content)
        self.assertEqual([row['roads'] for row in report['points']], ['entrance', 'pin'])
        self.assertEqual(content.entrance_road_tiles, {('west', (120, 88))})
        # The contracts and every other reader get the pin; a road builder gets the entrance for "entrance" only.
        content.templates = {'west': {'coordinateTransform': {'serverOrigin': [0, 200]}}}
        content.mapped_point = lambda region, point, node, landmark: np.array([point[0] + 1000., 0., point[2]])
        np.testing.assert_array_equal(CT.Content.mapped_server_point(content, 'west', [120, 88]), [40., 5., 60.])
        np.testing.assert_array_equal(CT.Content.mapped_server_point(content, 'west', [120, 88], roads=True), [1120.5, 0., 111.5])
        np.testing.assert_array_equal(CT.Content.mapped_server_point(content, 'west', [121, 88], roads=True), [42., 5., 60.])
        problems = A.validate_authored_points({'authored_points': [dict(ENTRY, roads='door')]})
        self.assertTrue(any('roads must be one of' in p for p in problems), problems)

    def test_no_points_change_nothing(self):
        content = types.SimpleNamespace()
        self.assertEqual(A.prepare_authored_points(world({}), content), {'points': []})
        self.assertEqual(content.authored_server_points, {})

    def test_points_outside_their_territory_or_under_water_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside its territory'):
            A.prepare_authored_points(world({'authored_points': [dict(ENTRY, point=[140., 60.])]}), types.SimpleNamespace())
        with self.assertRaisesRegex(ValueError, 'not dry ground'):
            A.prepare_authored_points(world({'authored_points': [dict(ENTRY, point=[40., 600.])]}), types.SimpleNamespace())
        pinned = types.SimpleNamespace(authored_server_points={('west', (120, 88)): np.zeros(3)})
        with self.assertRaisesRegex(ValueError, 'already pinned'):
            A.prepare_authored_points(world({'authored_points': [ENTRY]}), pinned)

    def test_validation_names_every_problem(self):
        plan = {'regions': [{'id': 'west'}], 'authored_points': [
            dict(ENTRY, region='north'), dict(ENTRY, tile=[1.5, 2]), dict(ENTRY, point=[1., None]),
            dict(ENTRY, reason=''), ENTRY, ENTRY]}
        problems = A.validate_authored_points(plan)
        text = '\n'.join(problems)
        for fragment in ("unknown region 'north'", 'two integer server coordinates', 'finite [x, z]', 'say why', 'pinned twice'):
            self.assertIn(fragment, text)
        self.assertEqual(A.validate_authored_points({'authored_points': {'x': 1}}), ["'authored_points' must be a list of points"])


if __name__ == '__main__':
    unittest.main()
