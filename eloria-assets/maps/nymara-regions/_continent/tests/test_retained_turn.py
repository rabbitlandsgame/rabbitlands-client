"""A retained territory whose transform turns: one legacy layout swung round as a rigid body.

The whole layout turns about the transform's own point. A placement's position is carried by
landscape.retained_map_xz while its mesh turns in place, a compound turns as one body about its
reference, a footing reads the legacy ground under where the footing now lies, and a linked record
keeps its place on its own object, turned with it.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assemblies as A
import content as C
import landscape as L
import object_edits as OE
import scene_io as S

REGION = 'grey_moors'
CENTER = [900., 500.]
GROUND = 5.                      # the continent is flat here, so grounding is one number
ABOUT = [40., -60.]              # the source point the layout turns about
TURNED = {'translation': [760., 0., 640.], 'about_x': ABOUT[0], 'about_z': ABOUT[1],
          'yaw_degrees': 90., 'datum': 'ground'}
HALL = [ABOUT[0] + 10., ABOUT[1]]          # a building 10 m east of the about point
CAIRN = [ABOUT[0] - 30., ABOUT[1] + 45.]   # a second free-standing structure
YARD = ([30., -40.], [30., -20.])          # one compound, its two members 20 m apart north to south


def legacy_height(x, z):
    """The legacy region's own relief: a plane, so a sample names the point it was taken at."""
    return 20. + .1 * np.asarray(x, float) + .02 * np.asarray(z, float)


def document():
    """One node per placement: a box about its own translation, 6 m east-west by 2 m north-south."""
    nodes = [{'name': 'Landmark_MootHall', 'translation': [HALL[0], 0., HALL[1]], 'mesh': 0},
             {'name': 'Landmark_cairn', 'translation': [CAIRN[0], 0., CAIRN[1]], 'mesh': 0},
             {'name': 'Landmark_yard_north', 'translation': [YARD[0][0], 0., YARD[0][1]], 'mesh': 0},
             {'name': 'Landmark_yard_south', 'translation': [YARD[1][0], 0., YARD[1][1]], 'mesh': 0}]
    return {'nodes': nodes, 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
            'accessors': [{'min': [-3., 0., -1.], 'max': [3., 4., 1.]}]}


def placements():
    return [{'node': 'Landmark_MootHall', 'kind': 'structure', 'collides': True, 'landmark': 'moot',
             'position': [HALL[0], 0., HALL[1]]},
            {'node': 'Landmark_cairn', 'kind': 'structure', 'collides': True,
             'position': [CAIRN[0], 0., CAIRN[1]]},
            {'node': 'Landmark_yard_north', 'kind': 'structure', 'assembly': 'yard',
             'position': [YARD[0][0], 0., YARD[0][1]]},
            {'node': 'Landmark_yard_south', 'kind': 'structure', 'assembly': 'yard',
             'position': [YARD[1][0], 0., YARD[1][1]]}]


class World:
    """Flat ground, one territory that owns all of it, and a record of every footing asked for."""

    def __init__(self, transform):
        self.regions = {REGION: {'id': REGION, 'center': CENTER}}
        self.ids = [REGION]
        self.plan = {'sea_level': 0., 'rivers': [], 'lakes': [], 'regions': [self.regions[REGION]],
                     'retained_transforms': {REGION: transform} if transform is not None else {}}
        self.x = np.arange(0., 1600.1, 2.)
        self.z = np.arange(0., 1600.1, 2.)
        self.x0 = self.z0 = 0.
        self.gx, self.gz = np.meshgrid(self.x, self.z)
        self.original_height = np.full(self.gx.shape, GROUND)
        self.footings = []
        self.assembly_footings = []

    def height_at(self, x, z):
        return np.full(np.shape(x), GROUND)

    def owner_at(self, x, z):
        return np.zeros(np.shape(x), int)

    def foundation(self, center, radius, height, feather=16, obstacle=False):
        self.footings.append((np.asarray(center, float).tolist(), float(height)))

    def assembly_foundation(self, sl, target, weight):
        self.assembly_footings.append((sl, np.asarray(target, float), np.asarray(weight, float)))


def loaded(tmp_path, monkeypatch, transform, edits=()):
    """This territory through the real Content.load, with whatever authored object edits it is given."""
    monkeypatch.setattr(OE, 'load_edits', lambda *a, **k: {'version': 1, 'objects': list(edits), 'vegetationAreas': []})
    folder = tmp_path / REGION
    folder.mkdir(parents=True, exist_ok=True)
    S.dump_glb(folder / 'library.glb', document(), b'')
    (folder / 'library.json').write_text(json.dumps({'placements': placements()}))
    x = np.arange(-300., 300.1, 5.)
    z = np.arange(-300., 300.1, 5.)
    gx, gz = np.meshgrid(x, z)
    np.savez(folder / 'foundation-samples.npz', x=x, z=z, height=legacy_height(gx, gz))
    world = World(transform)
    template = {'spawnPoints': [{'id': 'arrival', 'default': True, 'position': [0., 0., 0.]}]}
    content = C.Content(world, tmp_path, {REGION: template}, {})
    content.load()
    return world, content


def placed(content, node):
    obj = content.placement_by_name[(REGION, node)]
    return ((obj['low'] + obj['high']) * .5)[[0, 2]]


def world_matrix(content, node):
    document, _ = content.documents[REGION]
    index = next(i for i, n in enumerate(document['nodes']) if n.get('name') == node)
    return S.GR.hierarchy(document)[0][index]


def mapped_about():
    return np.asarray(L.retained_map_xz(TURNED, ABOUT), float)


def test_a_turned_transform_carries_a_source_point_round_its_about_point(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED)
    # 10 m east of the about point in the source stands 10 m south of the mapped about point:
    # x is east and z is south, and a positive yaw turns north towards east.
    np.testing.assert_allclose(content.mapped_xz(REGION, HALL), mapped_about() + [0., 10.], atol=1e-9)
    np.testing.assert_allclose(content.mapped_xz(REGION, [ABOUT[0], ABOUT[1] - 10.]), mapped_about() + [10., 0.], atol=1e-9)
    # A whole array of source points comes back mapped in the same order.
    np.testing.assert_allclose(content.mapped_xz(REGION, [HALL, ABOUT]),
                               [mapped_about() + [0., 10.], mapped_about()], atol=1e-9)
    np.testing.assert_allclose(placed(content, 'Landmark_MootHall'), mapped_about() + [0., 10.], atol=1e-9)


def test_every_retained_placement_turns_about_its_own_base_centre_and_is_bounded_where_it_stands(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED)
    matrix = world_matrix(content, 'Landmark_MootHall')
    # The mesh swings the way the map's yaw does; object_edits' own matrix turns the other way round.
    np.testing.assert_allclose(matrix[:3, :3], OE.edit_matrix([HALL[0], 0., HALL[1]], -90.)[:3, :3], atol=1e-9)
    # Its east corner (3 m east, 1 m south of the centre) swings round to 1 m west and 3 m south.
    np.testing.assert_allclose(matrix @ [3., 0., 1., 1.], [HALL[0] - 1., 0., HALL[1] + 3., 1.], atol=1e-9)
    np.testing.assert_allclose(matrix[:3, 3], [HALL[0], 0., HALL[1]], atol=1e-9, err_msg='the base centre stays put')
    obj = content.placement_by_name[(REGION, 'Landmark_MootHall')]
    # A 6 m by 2 m footprint stands 2 m by 6 m after a quarter turn: routing and collision read these.
    np.testing.assert_allclose((obj['high'] - obj['low'])[[0, 2]], [2., 6.], atol=1e-9)
    assert obj['high'][1] - obj['low'][1] == pytest.approx(4.), 'nothing is scaled'
    assert obj['low'][1] == pytest.approx(GROUND - float(legacy_height(*HALL)))
    assert obj['targetGround'] == pytest.approx(GROUND)


def test_a_record_keeps_its_place_on_its_own_building_through_the_turn(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED)
    hall = placed(content, 'Landmark_MootHall')
    lift = content.mapping[(REGION, 'Landmark_MootHall')][1]
    for node, landmark in (('Landmark_MootHall', None), (None, 'moot')):
        # An NPC post 5 m east of the hall in the source stands 5 m south of it on the continent.
        post = content.mapped_point(REGION, [HALL[0] + 5., 1.5, HALL[1]], node=node, landmark=landmark)
        np.testing.assert_allclose(post[[0, 2]], hall + [0., 5.], atol=1e-9)
        assert post[1] == pytest.approx(1.5 + lift)
    # A record with no link of its own re-anchors to the nearest object and turns with it too.
    loose = content.mapped_point(REGION, [HALL[0], 1.5, HALL[1] - 5.])
    np.testing.assert_allclose(loose[[0, 2]], hall + [5., 0.], atol=1e-9)
    # A point tied to no object at all still goes round with the layout.
    far = content.mapped_point(REGION, [ABOUT[0] + 200., 0., ABOUT[1]])
    np.testing.assert_allclose(far[[0, 2]], mapped_about() + [0., 200.], atol=1e-6)


def test_a_compound_turns_as_one_body_and_keeps_its_members_mutual_spacing(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED)
    north, south = placed(content, 'Landmark_yard_north'), placed(content, 'Landmark_yard_south')
    assert np.linalg.norm(north - south) == pytest.approx(20.)
    # North to south in the source is east to west after a quarter turn, the north member to the east.
    np.testing.assert_allclose(north - south, [20., 0.], atol=1e-9)
    members = [content.placement_by_name[(REGION, node)] for node in ('Landmark_yard_north', 'Landmark_yard_south')]
    A.assert_rigid(members)
    for obj in members:
        np.testing.assert_allclose((obj['high'] - obj['low'])[[0, 2]], [2., 6.], atol=1e-9, err_msg='each member turned')
    reference = np.asarray(content.assembly_records[REGION + '.yard']['referenceXZ'], float)
    np.testing.assert_allclose(reference, [30., -30.], atol=1e-9)
    # Each member turns about the compound's reference, so the compound is one rigid body.
    matrix = world_matrix(content, 'Landmark_yard_north')
    np.testing.assert_allclose(matrix[:3, :3], OE.edit_matrix([30., 0., -30.], -90.)[:3, :3], atol=1e-9)
    np.testing.assert_allclose(matrix[:3, 3], [40., 0., -30.], atol=1e-9)
    # The compound stands where its own reference maps to, not where the turn left its bounding box.
    np.testing.assert_allclose((north + south) * .5, content.mapped_xz(REGION, reference), atol=1e-9)
    # A record 4 m east of the north member in the source stands 4 m south of it, on that member.
    post = content.mapped_point(REGION, [YARD[0][0] + 4., 0., YARD[0][1]], node='Landmark_yard_north')
    np.testing.assert_allclose(post[[0, 2]], north + [0., 4.], atol=1e-9)


def test_an_authored_edit_turns_on_top_of_the_layouts_turn_and_never_twice(tmp_path, monkeypatch):
    edit = {'root': 'grey_moors_Landmark_MootHall_WorldPlacement', 'action': 'transform',
            'pivot': [HALL[0], 0., HALL[1]], 'translate': [0., 0., 0.], 'yawDegrees': 90., 'scale': 1}
    world, content = loaded(tmp_path, monkeypatch, TURNED, edits=[edit])
    # The layout's quarter turn, then the authored quarter turn back: the hall stands as it was authored.
    np.testing.assert_allclose(world_matrix(content, 'Landmark_MootHall')[:3, :3], np.eye(3), atol=1e-9)
    obj = content.placement_by_name[(REGION, 'Landmark_MootHall')]
    np.testing.assert_allclose((obj['high'] - obj['low'])[[0, 2]], [6., 2.], atol=1e-9)
    # Its place in the layout is still the layout's: an edit turns the mesh about its own base centre.
    np.testing.assert_allclose(placed(content, 'Landmark_MootHall'), mapped_about() + [0., 10.], atol=1e-9)
    assert content.edits.report['transformed'] == [edit['root']]


def test_a_turned_compounds_footing_reads_the_legacy_ground_under_the_footing(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED)
    sl, target, weight = world.assembly_footings[0]
    shift = np.asarray(content.assembly_records[REGION + '.yard']['translation'], float)
    supported = weight > .999
    assert supported.any()
    x, z = world.gx[sl][supported], world.gz[sl][supported]
    legacy = np.asarray(L.retained_unmap_xz(TURNED, x, z), float)
    np.testing.assert_allclose(target[supported], legacy_height(legacy[0], legacy[1]) + shift[1], atol=1e-6)
    # The shift alone cannot undo a turn: it would have read the legacy relief in the wrong place.
    assert float(np.max(np.abs(legacy_height(x - shift[0], z - shift[2]) - legacy_height(legacy[0], legacy[1])))) > 1.


def test_sample_foundation_reads_the_unmapped_point_and_leaves_the_shift_path_alone():
    members = [{'node': 'Landmark_yard_north', 'kind': 'structure', 'assembly': 'yard'}]
    bounds = {'Landmark_yard_north': ([0., 0., 0.], [8., 6., 8.])}
    assembly = A.build_assemblies(REGION, members, bounds, legacy_height)[REGION + '.yard']
    shift = np.array([700., 3., 900.])
    x, z = np.array([704., 706.]), np.array([904., 902.])
    plain, weight = assembly.sample_foundation(x, z, shift, legacy_height)
    np.testing.assert_allclose(plain, legacy_height(x - shift[0], z - shift[2]) + shift[1])
    unmapped, turned_weight = assembly.sample_foundation(
        x, z, shift, legacy_height, unmap=lambda px, pz: L.retained_unmap_xz(TURNED, px, pz))
    legacy = L.retained_unmap_xz(TURNED, x, z)
    np.testing.assert_allclose(unmapped, legacy_height(legacy[0], legacy[1]) + shift[1])
    np.testing.assert_allclose(weight, turned_weight, err_msg='the footprint mask is the same either way')


def test_a_compound_keeps_the_anchor_it_had_before_its_layout_turned():
    members = [{'node': 'Landmark_yard_north', 'kind': 'structure', 'assembly': 'yard'}]
    bounds = {'Landmark_yard_north': ([0., 0., 0.], [8., 6., 8.])}
    pinned = A.build_assemblies(REGION, members, bounds, legacy_height, references={REGION + '.yard': [30., -30.]})
    np.testing.assert_allclose(pinned[REGION + '.yard'].reference_xz, [30., -30.])
    assert pinned[REGION + '.yard'].reference_y == pytest.approx(float(legacy_height(30., -30.)))
    np.testing.assert_allclose(A.build_assemblies(REGION, members, bounds, legacy_height)[REGION + '.yard'].reference_xz,
                               [4., 4.], err_msg='without one it is still the centre of the actual bounds')


def snapshot(world, content):
    """The numbers every stage downstream reads back out of one loaded territory."""
    result = {}
    for node in ('Landmark_MootHall', 'Landmark_cairn', 'Landmark_yard_north', 'Landmark_yard_south'):
        obj = content.placement_by_name[(REGION, node)]
        result[node] = [*np.asarray(obj['shift'], float), *np.asarray(obj['low'], float),
                        *np.asarray(obj['high'], float), float(obj['targetGround'])]
    result['record'] = list(content.mapped_point(REGION, [HALL[0] + 5., 1.5, HALL[1]], node='Landmark_MootHall'))
    result['landmark'] = list(content.mapped_point(REGION, [HALL[0] + 5., 1.5, HALL[1]], landmark='moot'))
    result['loose'] = list(content.mapped_point(REGION, [HALL[0], 1.5, HALL[1] - 5.]))
    result['unlinked'] = list(content.mapped_point(REGION, [ABOUT[0] + 200., 0., ABOUT[1]]))
    result['mapped'] = list(np.asarray(content.mapped_xz(REGION, HALL), float))
    result['assembly'] = list(np.asarray(content.assembly_records[REGION + '.yard']['translation'], float))
    result['reference'] = list(np.asarray(content.assembly_records[REGION + '.yard']['referenceXZ'], float))
    result['published'] = [*np.asarray(content.source_centers[REGION], float).ravel(),
                           *np.asarray(content.scales[REGION], float).ravel()]
    result['footings'] = [value for center, height in world.footings for value in (*center, height)]
    sl, target, weight = world.assembly_footings[0]
    result['footing'] = [float(target[weight > .999].sum()), float(weight.sum())]
    return result


# A rigid translation, and a translation with the north-south squeeze, neither of which turns.
UNTURNED = {'list': [760., 0., 640.],
            'squeezed': {'translation': [760., 0., 640.], 'squeeze_z': .8, 'about_z': ABOUT[1]}}
# Every number below was recorded from this module against the code as it stood before a retained
# layout could turn: an untured territory must be placed, grounded and linked exactly as it was.
EXPECTED = {'list': {'Landmark_MootHall': [760.0, -18.8, 640.0, 807.0, -18.8, 579.0, 813.0, -14.8, 581.0, 5.0],
          'Landmark_cairn': [760.0, -15.7, 640.0, 767.0, -15.7, 624.0, 773.0, -11.7, 626.0, 5.0],
          'Landmark_yard_north': [760.0, 0.0, 640.0, 787.0, 0.0, 599.0, 793.0, 4.0, 601.0, 22.2],
          'Landmark_yard_south': [760.0, 0.0, 640.0, 787.0, 0.0, 619.0, 793.0, 4.0, 621.0, 22.6],
          'assembly': [760.0, 0.0, 640.0],
          'footing': [672.0, 384.7466928796972],
          'footings': [810.0, 580.0, 5.0, 770.0, 625.0, 5.0],
          'landmark': [815.0, -17.3, 580.0],
          'loose': [810.0, -17.3, 575.0],
          'mapped': [810.0, 580.0],
          'published': [140.0, -140.0, 1.0, 1.0],
          'record': [815.0, -17.3, 580.0],
          'reference': [30.0, -30.0],
          'unlinked': [1000.0, 5.0, 580.0]},
 'squeezed': {'Landmark_MootHall': [760.0, -18.8, 640.0, 807.0, -18.8, 579.0, 813.0, -14.8, 581.0, 5.0],
              'Landmark_cairn': [760.0, -15.7, 631.0, 767.0, -15.7, 615.0, 773.0, -11.7, 617.0, 5.0],
              'Landmark_yard_north': [760.0, 0.0, 634.0, 787.0, 0.0, 593.0, 793.0, 4.0, 595.0, 22.2],
              'Landmark_yard_south': [760.0, 0.0, 634.0, 787.0, 0.0, 613.0, 793.0, 4.0, 615.0, 22.6],
              'assembly': [760.0, 0.0, 634.0],
              'footing': [672.0, 384.7466928796972],
              'footings': [810.0, 580.0, 5.0, 770.0, 616.0, 5.0],
              'landmark': [815.0, -17.3, 580.0],
              'loose': [810.0, -17.3, 575.0],
              'mapped': [810.0, 580.0],
              'published': [140.0, -160.0, 1.0, 0.8],
              'record': [815.0, -17.3, 580.0],
              'reference': [30.0, -30.0],
              'unlinked': [1000.0, 5.0, 580.0]}}


@pytest.mark.parametrize('case', sorted(UNTURNED))
def test_a_layout_that_does_not_turn_is_placed_exactly_as_it_was(tmp_path, monkeypatch, case):
    world, content = loaded(tmp_path, monkeypatch, UNTURNED[case])
    recorded = snapshot(world, content)
    assert sorted(recorded) == sorted(EXPECTED[case])
    for key, value in EXPECTED[case].items():
        np.testing.assert_allclose(recorded[key], value, atol=1e-9, err_msg=key)
    assert not content.residuals, 'a layout that does not turn carries no residual'
