"""Crossing sites: locally shortest, square to the flow, dry landings, spaced along the river, clear of exclusions."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import river_crossings as RC
import world_layout as W


def river_world(size=(240, 360), width=lambda z: np.where((z >= 96) & (z <= 112), 5., 10.), level=0., ground=4.,
                rivers=None, lakes=(), owner=None, policy=None):
    """A straight river along x = 120 running south (z grows), its half width a function of z; dry ground at ``ground``."""
    world = W.World.__new__(W.World)
    world.x = np.arange(0, size[0] + 1, W.CELL, dtype=float)
    world.z = np.arange(0, size[1] + 1, W.CELL, dtype=float)
    world.x0, world.z0 = 0., 0.
    world.x1, world.z1 = float(size[0]), float(size[1])
    world.gx, world.gz = np.meshgrid(world.x, world.z)
    half = width(world.gz)
    channel = np.abs(world.gx - 120.) <= half
    world.height = np.where(channel, level - 1.5, ground)
    for lake in lakes:
        inside = ((world.gx - lake['center'][0]) / lake['radii'][0]) ** 2 + ((world.gz - lake['center'][1]) / lake['radii'][1]) ** 2 <= 1
        world.height[inside] = level - 1.5
    world.original_height = world.height.copy()
    mask = world.height < level - .015
    world.water = {'mask': mask, 'depth': np.where(mask, level - world.height, 0.), 'surface': np.full(world.height.shape, level),
                   'river_mask': mask, 'sea_mask': np.zeros(mask.shape, bool)}
    world.owner = np.zeros((len(world.z) - 1, len(world.x) - 1), int) if owner is None else owner(world)
    world.ids = ['test', 'other']
    world.obstacles = np.zeros(world.height.shape, bool)
    world.solids = np.zeros(world.height.shape, bool)
    world.assembly_weight = np.zeros(world.height.shape)
    world.foundation_weight = np.zeros(world.height.shape)
    world.routing = []
    world.plan = {'rivers': rivers if rivers is not None else [{'id': 'main', 'name': 'Main', 'width': 10., 'points': [[120., 0., level], [120., 180., level], [120., 360., level]]}],
                  'lakes': list(lakes), 'sea_level': -50.}
    if policy:
        world.plan['crossing_policy'] = policy
    world.crossing_policy = None
    return world


class CandidateTests(unittest.TestCase):
    def test_the_narrow_reach_is_the_local_minimum_and_nothing_near_it_is_wider(self):
        world = river_world()
        RC.prepare_river_crossings(world)
        candidates = sorted(world.crossing_candidates, key=lambda c: c['arcMetres'])
        narrow = [c for c in candidates if 96 <= c['centre'][1] <= 112]
        self.assertEqual(len(narrow), 1)
        self.assertAlmostEqual(narrow[0]['wetWidthMetres'], 11., delta=1.)
        window = float(RC.policy_of(world)['local_window_metres'])
        for c in candidates:
            if abs(c['arcMetres'] - narrow[0]['arcMetres']) <= window and c is not narrow[0]:
                self.fail(f"a wider section {c['key']} is a candidate within the window of the narrow reach")
        self.assertEqual(min(candidates, key=lambda c: c['cost'])['key'], narrow[0]['key'])

    def test_candidates_along_a_uniform_reach_stand_apart(self):
        world = river_world(width=lambda z: np.full(np.shape(z), 8.))
        RC.prepare_river_crossings(world)
        arcs = sorted(c['arcMetres'] for c in world.crossing_candidates)
        self.assertGreater(len(arcs), 3)
        self.assertTrue(np.all(np.diff(arcs) >= RC.CANDIDATE_SPACING_METRES - 1e-9))

    def test_spans_are_square_to_the_flow_with_dry_landings_outside_every_setback(self):
        world = river_world()
        RC.prepare_river_crossings(world)
        policy = RC.policy_of(world)
        self.assertTrue(world.crossing_candidates)
        for c in world.crossing_candidates:
            a, b = np.asarray(c['routeLandings'])
            span = (b - a) / np.linalg.norm(b - a)
            self.assertLess(abs(span[1]), np.sin(np.radians(policy['perpendicular_tolerance_degrees'])) + 1e-9)
            self.assertLessEqual(c['deviationDegrees'], policy['perpendicular_tolerance_degrees'])
            for point in (a, b):
                self.assertFalse(world.water['mask'][world.cell_of(point)])
                self.assertGreater(float(RC.water_distance_at(world, *point)), RC.setback_metres(policy, 4.))

    def test_a_sharp_bend_is_oblique_and_excluded(self):
        # The river turns ninety degrees at (120, 180): sections there look across the bend, not square to the flow.
        rivers = [{'id': 'bend', 'name': 'Bend', 'width': 6., 'points': [[120., 0., 0.], [120., 180., 0.], [240., 180., 0.]]}]
        world = river_world(width=lambda z: np.full(np.shape(z), 6.), rivers=rivers)
        # Carve the water along the curved centreline instead of the straight channel.
        import landscape as L
        distance, _ = L._polyline_field(world.gx, world.gz, rivers[0]['points'])
        world.height = np.where(distance <= 6., -1.5, 4.)
        mask = world.height < -.015
        world.water.update(mask=mask, depth=np.where(mask, -world.height, 0.), river_mask=mask)
        rows = RC.river_sections(world, rivers[0], RC.policy_of(world))
        oblique = [r for r in rows if 'oblique to the flow' in r['reasons']]
        self.assertTrue(oblique)
        for row in oblique:
            self.assertLess(np.hypot(row['centre'][0] - 120., row['centre'][1] - 180.), 40.)


class ExclusionTests(unittest.TestCase):
    def reasons_near(self, world, z, reason):
        rows = RC.river_sections(world, world.plan['rivers'][0], RC.policy_of(world))
        return [r for r in rows if abs(r['centre'][1] - z) <= 4 and reason in r['reasons']]

    def test_lakes_confluences_seams_solids_and_settlement_cores_exclude_a_section(self):
        lake = {'name': 'Pool', 'center': [120., 300.], 'radii': [20., 20.], 'level': 0., 'depth': 1.5}
        tributary = {'id': 'side', 'name': 'Side', 'width': 4., 'joins': 'main', 'points': [[60., 60., 0.], [120., 60., 0.]]}
        rivers = [{'id': 'main', 'name': 'Main', 'width': 10., 'points': [[120., 0., 0.], [120., 180., 0.], [120., 360., 0.]]}, tributary]
        world = river_world(rivers=rivers, lakes=[lake],
                            owner=lambda w: (w.gz[:-1, :-1] >= 250).astype(int) * 0 + ((w.gz[:-1, :-1] >= 140) & (w.gz[:-1, :-1] < 150)).astype(int))
        world.solids[(np.abs(world.gz - 220.) <= 2) & (np.abs(world.gx - 140.) <= 3)] = True
        world.assembly_weight[(np.abs(world.gz - 250.) <= 3) & (np.abs(world.gx - 100.) <= 6)] = 1.
        self.assertTrue(self.reasons_near(world, 300., 'lake'))
        self.assertTrue(self.reasons_near(world, 60., 'confluence'))
        self.assertTrue(self.reasons_near(world, 145., 'territory seam'))
        self.assertTrue(self.reasons_near(world, 220., 'retained solid'))
        self.assertTrue(self.reasons_near(world, 250., 'footing'))
        RC.prepare_river_crossings(world)
        for c in world.crossing_candidates:
            if c['river'] != 'main':
                continue
            z = c['centre'][1]
            for excluded in (300., 60., 145., 220., 250.):
                self.assertGreater(abs(z - excluded), 3., c['key'])

    def test_a_feathered_footing_or_a_loose_placement_pad_does_not_exclude(self):
        world = river_world()
        world.assembly_weight[np.abs(world.gz - 250.) <= 3] = .6       # a settlement feather, not its rigid core
        world.foundation_weight[np.abs(world.gz - 250.) <= 3] = 1.     # a single placement's own pad
        self.assertFalse(self.reasons_near(world, 250., 'footing'))


class AuthoredCrossingTests(unittest.TestCase):
    def solid_beside_the_narrow_reach(self):
        world = river_world()
        # A retained solid beside the east landing of the narrow reach (z 96..112) excludes every section there.
        world.solids[(world.gz >= 90) & (world.gz <= 118) & (np.abs(world.gx - 136.) <= 2)] = True
        return world

    def test_an_authored_section_is_a_candidate_despite_a_waivable_exclusion(self):
        world = self.solid_beside_the_narrow_reach()
        RC.prepare_river_crossings(world)
        self.assertFalse([c for c in world.crossing_candidates if 96 <= c['centre'][1] <= 112])
        rows = RC.river_sections(world, world.plan['rivers'][0], RC.policy_of(world))
        narrow = min((r for r in rows if 'cost' in r and 96 <= r['centre'][1] <= 112 and r['reasons'] == ['retained solid']), key=lambda r: r['cost'])
        world.plan['authored_crossings'] = [{'river': 'main', 'arcMetres': narrow['arc'], 'note': 'the designed ford bridge'}]
        RC.prepare_river_crossings(world)
        authored = [c for c in world.crossing_candidates if c['authored']]
        self.assertEqual(len(authored), 1)
        self.assertEqual(authored[0]['waived'], ['retained solid'])
        self.assertFalse(authored[0]['lastResort'])
        for c in world.crossing_candidates:
            if c is not authored[0]:
                self.assertGreaterEqual(abs(c['arcMetres'] - authored[0]['arcMetres']), RC.CANDIDATE_SPACING_METRES)
        RC.claim(world, [authored[0]['key']], 'seam-road', public=True)
        site = RC.crossing_report(world)['sites'][0]
        self.assertTrue(site['authored']); self.assertEqual(site['waived'], ['retained solid'])

    def test_an_authored_section_waives_a_seam_it_stands_near_but_never_a_span_in_two_territories(self):
        # Standing near a seam is a preference an authored crossing may overrule: the Four Gates south gate is to
        # have its bridge although the boundary runs near the river there.
        world = river_world(owner=lambda w: (w.gz[:-1, :-1] >= 250).astype(int))
        rows = RC.river_sections(world, world.plan['rivers'][0], RC.policy_of(world))
        near = min((r for r in rows if 'cost' in r and 240 <= r['centre'][1] < 249
                    and r['reasons'] == ['territory seam']), key=lambda r: r['cost'])
        world.plan['authored_crossings'] = [{'river': 'main', 'arcMetres': near['arc'], 'note': 'the gate bridge'}]
        RC.prepare_river_crossings(world)
        self.assertEqual([c['waived'] for c in world.crossing_candidates if c['authored']], [['territory seam']])
        # A span whose own line lies in two territories is refused instead: each territory exports its own geometry,
        # so that deck would be built in halves.
        split = river_world(owner=lambda w: (w.gx[:-1, :-1] >= 120).astype(int))
        rows = RC.river_sections(split, split.plan['rivers'][0], RC.policy_of(split))
        measured = [r for r in rows if 'cost' in r]
        self.assertTrue(all('two territories' in r['reasons'] for r in measured))
        split.plan['authored_crossings'] = [{'river': 'main', 'arcMetres': measured[len(measured) // 2]['arc'],
                                             'note': 'across the boundary'}]
        with self.assertRaisesRegex(ValueError, 'two territories cannot be waived'):
            RC.prepare_river_crossings(split)

    def test_an_authored_section_cannot_waive_a_lake_and_the_key_is_validated(self):
        import landscape as L
        lake = {'name': 'Pool', 'center': [120., 300.], 'radii': [20., 20.], 'level': 0., 'depth': 1.5}
        world = river_world(lakes=[lake])
        world.plan['authored_crossings'] = [{'river': 'main', 'arcMetres': 300., 'note': 'across the pool'}]
        with self.assertRaisesRegex(ValueError, 'authored crossing main@300: .*lake.* cannot be waived'):
            RC.prepare_river_crossings(world)
        self.assertEqual(L.validate_authored_crossings({'rivers': [{'id': 'main'}]}), [])
        self.assertTrue(L.validate_authored_crossings({'rivers': [{'id': 'main'}], 'authored_crossings': [{'river': 'side', 'arcMetres': 3., 'note': 'x'}]}))
        self.assertTrue(L.validate_authored_crossings({'rivers': [{'id': 'main'}], 'authored_crossings': [{'river': 'main', 'arcMetres': -1., 'note': 'x'}]}))
        self.assertTrue(L.validate_authored_crossings({'rivers': [{'id': 'main'}], 'authored_crossings': [{'river': 'main', 'arcMetres': 3.}]}))


class SpacingTests(unittest.TestCase):
    def test_claimed_sites_keep_the_minimum_spacing_and_share_use(self):
        world = river_world(width=lambda z: np.full(np.shape(z), 8.))
        RC.prepare_river_crossings(world)
        spacing = RC.policy_of(world)['minimum_spacing_metres']
        first = min(world.crossing_candidates, key=lambda c: c['arcMetres'])
        RC.claim(world, [first['key']], 'door-a', public=True)
        available = RC.available_crossings(world, 'test')
        self.assertIn(first['key'], [c['key'] for c in available])
        for c in available:
            if c['key'] != first['key']:
                self.assertGreaterEqual(abs(c['arcMetres'] - first['arcMetres']), spacing)
        near = next(c for c in world.crossing_candidates if 0 < abs(c['arcMetres'] - first['arcMetres']) < spacing)
        with self.assertRaisesRegex(ValueError, 'within 100 m of a claimed site'):
            RC.claim(world, [near['key']], 'door-b', public=False)
        self.assertLess(RC.crossing_cost(world, first), RC.policy_of(world)['bridge_cost_metres'])
        self.assertEqual(RC.conflicting(world, [near['key']]), [near['key']])
        snapshot = RC.snapshot_claims(world)
        far = next(c for c in available if c['key'] != first['key'])
        RC.claim(world, [far['key']], 'door-c', public=True)
        self.assertEqual(len(world.crossing_sites), 2)
        RC.restore_claims(world, snapshot)
        self.assertEqual([s['key'] for s in world.crossing_sites], [first['key']])

    def test_an_authored_crossing_is_claimed_inside_the_spacing(self):
        # The spacing rules the crossings the model sites for itself. One the plan names is a decision already taken.
        world = river_world(width=lambda z: np.full(np.shape(z), 8.))
        RC.prepare_river_crossings(world)
        spacing = RC.policy_of(world)['minimum_spacing_metres']
        first = min(world.crossing_candidates, key=lambda c: c['arcMetres'])
        near = next(c for c in world.crossing_candidates if 0 < abs(c['arcMetres'] - first['arcMetres']) < spacing)
        world.plan['authored_crossings'] = [{'river': 'main', 'arcMetres': near['arcMetres'], 'note': 'the gate bridge'}]
        RC.prepare_river_crossings(world)
        RC.claim(world, [first['key']], 'door-a', public=True)
        authored = next(c for c in world.crossing_candidates if c['authored'])
        self.assertLess(abs(authored['arcMetres'] - first['arcMetres']), spacing)
        RC.claim(world, [authored['key']], 'gate-road', public=True)
        self.assertEqual(len(world.crossing_sites), 2)
        self.assertIn(authored['key'], [c['key'] for c in RC.available_crossings(world, None)])

    def test_the_policy_is_validated_by_name_and_range(self):
        import landscape as L
        self.assertEqual(L.validate_crossing_policy({'crossing_policy': {'minimum_spacing_metres': 100}}), [])
        self.assertTrue(L.validate_crossing_policy({'crossing_policy': {'minimum_spacing': 100}}))
        self.assertTrue(L.validate_crossing_policy({'crossing_policy': {'perpendicular_tolerance_degrees': 60}}))
        self.assertEqual(L.crossing_policy({'crossing_policy': {'minimum_spacing_metres': 150}})['minimum_spacing_metres'], 150.)
        with self.assertRaises(ValueError):
            L.crossing_policy({'crossing_policy': {'local_window_metres': 'wide'}})


if __name__ == '__main__':
    unittest.main()
