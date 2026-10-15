"""Access decks: named decks the plan lays between walk surfaces that stop short of each other."""
import types
import unittest

import numpy as np

import access_decks as A


DECK = {'name': 'Walk_Test_Link', 'region': 'west', 'points': [[0., 0.], [0., 16.]], 'heights': [4.3, 3.55], 'width': 3., 'note': 'test'}


def plan(*decks, designed=True):
    value = {'regions': [{'id': 'west'}], 'access_decks': list(decks)}
    if designed:
        value['designed_decks'] = [{'name': d['name'], 'module': 'access_decks', 'note': 'test'} for d in decks]
    return value


class ValidationTests(unittest.TestCase):
    def test_a_named_deck_within_grade_is_valid(self):
        self.assertEqual(A.validate_access_decks(plan(DECK)), [])
        self.assertEqual(A.validate_access_decks({}), [])

    def test_problems_are_named(self):
        text = '\n'.join(A.validate_access_decks(plan(
            dict(DECK, name='Link'), dict(DECK, name='Walk_Steep', heights=[0., 9.]), dict(DECK, name='Walk_Wide', width=12.),
            dict(DECK, name='Walk_Short', heights=[1.]), dict(DECK, name='Walk_Where', region='east'))))
        for fragment in ('Walk_ node name', 'steeper than 0.45', 'width must lie', 'one finite height', "unknown region 'east'"):
            self.assertIn(fragment, text)
        undeclared = '\n'.join(A.validate_access_decks(plan(DECK, designed=False) | {'designed_decks': []}))
        self.assertIn('does not name', undeclared)


class MeshTests(unittest.TestCase):
    def test_the_surface_follows_the_heights_and_faces_up_either_way(self):
        for points in ([[0., 0.], [0., 16.]], [[0., 16.], [0., 0.]]):
            deck = dict(DECK, points=points)
            mesh, report = A.deck_mesh(deck, 'm')
            y = mesh.positions[:, 1]
            self.assertAlmostEqual(float(y.max()), 4.3, places=6)
            self.assertAlmostEqual(float(y.min()), 3.55, places=6)
            tri = mesh.positions[mesh.indices.reshape(-1, 3)]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            self.assertGreater(float(n[:, 1].min()), 0.)
            self.assertAlmostEqual(report['lengthMetres'], 16., places=6)
            self.assertLessEqual(report['maximumGrade'], .65)
            xs = mesh.positions[:, 0]
            self.assertAlmostEqual(float(xs.max() - xs.min()), 3., places=6)

    def test_edges_reach_below_the_ground(self):
        mesh, _ = A.deck_mesh(DECK, 'm')
        world = types.SimpleNamespace(height_at=lambda x, z: np.full(np.shape(x), -5.))
        edges = A.edge_faces(world, mesh, 'm')
        self.assertLess(float(edges.positions[:, 1].min()), -5.)


if __name__ == '__main__':
    unittest.main()
