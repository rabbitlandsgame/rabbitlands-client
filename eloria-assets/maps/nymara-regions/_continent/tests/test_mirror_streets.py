"""Road cuts in open city ground never change actual architectural footings."""
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mirror_streets as M
import mirror_lake_support as LAKE
import mirror_support as SUPPORT
import world_layout as W
from world_layout import World


def city():
    world = World.__new__(World)
    world.x = np.arange(-60., 62., 2.)
    world.z = np.arange(-40., 42., 2.)
    world.x0, world.z0 = world.x[0], world.z[0]
    world.gx, world.gz = np.meshgrid(world.x, world.z)
    world.height = 10. + 12. * np.exp(-(world.gx / 9.) ** 2)
    world.assembly_target = world.height.copy()
    world.assembly_weight = np.ones_like(world.height)
    world.ids = ['mirrorhold', 'neighbour']
    world.owner_at = lambda x, z: (np.asarray(x) >= 40).astype(int)
    world.water = {'mask': np.zeros_like(world.height, bool),
                   'depth': np.zeros_like(world.height)}
    world.road_target = np.full_like(world.height, 10.)
    world.road_distance = np.maximum(abs(world.gz) - 2.5, 0.)
    world.roads = [{'points': [[-50., 10., 0.], [50., 10., 0.]]}]
    world.quay_contacts = []
    world.restore_drainage_corridor = lambda stage: None
    objects = [
        {'region': 'mirrorhold', 'kind': 'landmark', 'node': 'ActualHouse',
         'low': [-34., 10., -4.], 'high': [-28., 18., 4.]},
        {'region': 'mirrorhold', 'kind': 'tree', 'node': 'StreetTree',
         'low': [-3., 10., -3.], 'high': [3., 24., 3.]},
        {'region': 'neighbour', 'kind': 'structure', 'node': 'BorderPlatform',
         'low': [36., 10., 8.], 'high': [43., 11., 12.]},
    ]
    return world, SimpleNamespace(objects=objects)


def test_road_support_does_not_mutate_initial_city_or_object_geometry():
    world, content = city()
    before = {name: getattr(world, name).copy()
              for name in ('height', 'assembly_target', 'assembly_weight')}
    bounds = [(list(o['low']), list(o['high'])) for o in content.objects]
    report = M.apply_mirror_street_footings(world, content)
    for name, value in before.items():
        np.testing.assert_array_equal(getattr(world, name), value)
    assert bounds == [(o['low'], o['high']) for o in content.objects]
    assert report['releasedSurveyVertices'] > 0
    assert world.road_footing_weight[world.gx >= 40].min() == 1.


def test_real_platform_footprint_and_margin_stay_pinned_but_tree_does_not():
    world, content = city()
    M.apply_mirror_street_footings(world, content)
    house = (world.gx >= -36) & (world.gx <= -26) & (abs(world.gz) <= 6)
    assert np.all(world.road_footing_weight[house] == 1.)
    assert world.road_footing_weight[(abs(world.gx) <= 2) & (abs(world.gz) <= 2)].max() == 0.
    # A neighbouring territory's retained geometry may overhang this territory.
    assert world.road_footing_weight[(world.gx == 36) & (world.gz == 10)] == 1.


def test_real_road_settlement_grades_open_hill_and_preserves_house_floor():
    legacy, _ = city()
    legacy.settle_roads()
    world, content = city()
    M.apply_mirror_street_footings(world, content)
    before = world.height.copy()
    world.settle_roads()
    house = (world.gx >= -36) & (world.gx <= -26) & (abs(world.gz) <= 6)
    np.testing.assert_array_equal(world.height[house], before[house])
    centre = int(np.flatnonzero(world.z == 0)[0])
    open_street = abs(world.x) <= 18
    assert np.max(abs(np.diff(legacy.height[centre, open_street])) / 2.) > .65
    assert np.max(abs(np.diff(world.height[centre, open_street])) / 2.) <= .60
    assert world.height[centre, world.x == 0][0] < 12.
    # The city survey's released street ground is designed grading inside the city footing: the road earthworks
    # limits (cut 4 m, fill 3 m) apply outside it, not here.
    assert world.earthworks_free()[centre, world.x == 0][0]
    assert not legacy.earthworks_free()[centre, world.x == 0][0] or legacy.road_grading['earthworks']['limitedVertices'] == 0
    assert world.road_grading['conflictingFootingCorridorVertices'] == 0
    # No cut/fill reaches a distant area beyond the road shoulder.
    np.testing.assert_array_equal(world.height[0], before[0])


def test_invalid_or_missing_retained_architecture_fails_before_changing_world():
    world, content = city()
    content.objects[0]['low'][0] = float('nan')
    with pytest.raises(ValueError, match='finite actual bounds'):
        M.apply_mirror_street_footings(world, content)
    assert not hasattr(world, 'road_footing_weight')
    with pytest.raises(ValueError, match='retained architecture'):
        M.apply_mirror_street_footings(world, SimpleNamespace(objects=[]))


def test_civic_streets_keep_rigid_city_switchbacks_and_exclude_old_region_exits():
    roads = [{'id': identity, 'width': 6,
              'waypoints': [[1, 3, 2], [10, 6, -8], [4, 9, -20]]}
             for identity in sorted(M.REQUIRED_ROADS | {'whitehorn-approach', 'lake-city'})]
    content = SimpleNamespace(metadata={'mirrorhold': {'authored_roads': roads}},
        assembly_records={'mirrorhold.city': {'translation': [800, 80, 789]}})
    calls = []
    world = SimpleNamespace(ids=['mirrorhold'], roads=[], road_distance=np.full((2, 2), np.inf),
        owner_at=lambda x, z: np.zeros_like(x, dtype=int),
        add_road=lambda points, **kw: calls.append((points.copy(), kw)))
    result = M.add_mirror_streets(world, content)
    assert len(calls) == len(M.REQUIRED_ROADS)
    np.testing.assert_array_equal(calls[0][0], [[801, 791], [810, 781], [804, 769]])
    assert all(row[1]['width'] == 3 for row in calls)
    assert {row['source'] for row in result['streets']} == M.REQUIRED_ROADS


def test_missing_civic_connection_is_a_build_error():
    with pytest.raises(ValueError, match='missing its authored civic circulation'):
        M.add_mirror_streets(SimpleNamespace(),
            SimpleNamespace(metadata={'mirrorhold': {'authored_roads': []}}))


def test_new_boundary_can_exclude_an_old_peripheral_yard_but_never_the_civic_loop():
    roads = [{'id': identity, 'waypoints': [[0, 3, 0], [10, 3, 0]]}
             for identity in sorted(M.REQUIRED_ROADS)]
    roads.append({'id': 'old-peripheral-yard', 'waypoints': [[0, 3, 0], [50, 3, 0]]})
    content = SimpleNamespace(metadata={'mirrorhold': {'authored_roads': roads}},
        assembly_records={'mirrorhold.city': {'translation': [0, 0, 0]}})
    world = SimpleNamespace(ids=['mirrorhold'], roads=[], road_distance=np.full((2, 2), np.inf),
        owner_at=lambda x, z: (np.asarray(x) > 20).astype(int), add_road=lambda *args, **kw: None)
    result = M.add_mirror_streets(world, content)
    assert len(result['streets']) == len(M.REQUIRED_ROADS)
    assert result['excludedOutsideOwnership'][0]['source'] == 'old-peripheral-yard'
    roads[0]['waypoints'][1][0] = 50
    with pytest.raises(ValueError, match='Required Mirror civic street leaves'):
        M.add_mirror_streets(world, content)


def test_exterior_approach_follows_civic_switchback_then_attaches_without_widening_it():
    world = World.__new__(World)
    world.x = world.z = np.arange(0., 82., 2.)
    world.x0 = world.z0 = 0.
    world.gx, world.gz = np.meshgrid(world.x, world.z)
    world.height = np.full(world.gx.shape, 10.)
    world.obstacles = np.zeros(world.height.shape, bool)
    world.ids = ['mirrorhold']
    world.owner_at = lambda x, z: np.asarray(x, dtype=int) * 0
    # A complete U street around the back of the civic compounds.
    vertical = np.minimum(abs(world.gx - 12), abs(world.gx - 60))
    vertical = np.hypot(vertical, np.maximum(np.maximum(12 - world.gz, world.gz - 60), 0))
    upper = np.hypot(abs(world.gz - 60), np.maximum(np.maximum(12 - world.gx, world.gx - 60), 0))
    world.mirror_street_distance = np.minimum(vertical, upper) / 3.
    start, goal = np.array([12., 12.]), np.array([72., 12.])
    route = world.route(start, goal, region='mirrorhold')
    np.testing.assert_array_equal(route[-1], goal)
    assert route[0, 0] >= 54 and route[0, 1] <= 18
    assert world.mirror_street_attachments[-1]['retainedCivicStations'] > 10
    # Other routing callers retain their original endpoints and ordinary cost.
    ordinary = world.route(start, goal)
    np.testing.assert_array_equal(ordinary[0], start)
    np.testing.assert_array_equal(ordinary[-1], goal)


def test_branch_that_leaves_the_streets_keeps_its_departure_not_a_later_touch():
    world, _ = city()
    world.mirror_street_distance = np.full_like(world.height, np.inf)
    points = np.array([[-50. + 4 * k, 0.] for k in range(16)])
    def mark(index):
        ix = int(np.rint((points[index, 0] - world.x0) / 2)); iz = int(np.rint((points[index, 1] - world.z0) / 2))
        world.mirror_street_distance[iz, ix] = 0.
    # A street run with a cut corner at station 2, then open ground, then one later touch at station 11.
    for index in (0, 1, 3, 11):
        mark(index)
    trimmed = M.trim_civic_approach(world, points)
    np.testing.assert_array_equal(trimmed, points[3:])
    assert world.mirror_street_attachments[-1]['retainedCivicStations'] == 3


def test_branch_that_starts_off_the_civic_network_keeps_its_original_start():
    world, _ = city()
    world.mirror_street_distance = np.full_like(world.height, np.inf)
    points = np.array([[-50., 20.], [-40., 20.], [-30., 20.]])
    np.testing.assert_array_equal(M.trim_civic_approach(world, points), points)


def test_open_approach_connects_steep_ground_at_its_real_contact_heights():
    world, content = city()
    world.height = 20. + world.gx*.2 + 6.*np.exp(-(world.gx/5.)**2)
    before = world.height.copy()
    report = M.grade_open_approach(world, content, 'test-access', [-20.,0.], [20.,0.])
    from collision_export import terrain_grade
    x,z = np.meshgrid(np.arange(-17.75,18.,.5),np.arange(-1.75,2.,.5))
    assert terrain_grade(world,x,z).max() < .60
    assert report['maximumFootingChange'] == 0.
    for point in (-20.,20.):
        ix,iz = int((point-world.x0)/2),int(-world.z0/2)
        assert world.height[iz,ix] == before[iz,ix]
    np.testing.assert_array_equal(world.height[0],before[0])
    np.testing.assert_array_equal(world.height[world.gx>=40],before[world.gx>=40])
    assert report['changedVertices'] > 0


def test_impossible_approach_fails_before_altering_the_field():
    world, content = city()
    world.height = 30. + world.gx
    before = world.height.copy()
    with pytest.raises(ValueError,match='longer approach'):
        M.grade_open_approach(world,content,'impossible',[-20.,0.],[20.,0.])
    np.testing.assert_array_equal(world.height,before)


def test_saved_mirrorhold_authority_skips_every_legacy_street_lake_and_access_mutation():
    world, content = city()
    world.authoring_snapshots = {'mirrorhold': object()}
    before_height = world.height.copy()
    before_roads = list(world.roads)

    reports = [
        M.apply_mirror_street_footings(world, content),
        LAKE.prepare_mirror_lake_support(world, content),
        M.add_mirror_streets(world, content),
        SUPPORT.apply_mirror_support(world, content),
        M.apply_mirror_access(world, content),
        LAKE.finish_mirror_lake_support(world, content),
    ]

    np.testing.assert_array_equal(world.height, before_height)
    assert world.roads == before_roads
    assert all(report['skipped'] == 'saved-authoring-authority'
               for report in reports)
    assert world.mirror_circulation['streets'] == []
    assert world.mirror_access['paths'] == []
    assert not hasattr(world, 'mirror_lake_shore_state')
