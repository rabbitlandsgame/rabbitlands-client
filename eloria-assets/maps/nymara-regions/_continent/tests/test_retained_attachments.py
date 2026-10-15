"""The plan's authored corrections to retained placements: attachments, part edits and footings.

An attached placement (a steeple on a temple roof) is carried rigidly by its host instead of being mapped,
pulled and grounded on its own, so a squeezed or turned layout and a sloped ground cannot part the two. A
part edit moves or drops one part of a placement in the legacy source frame before any bounds are taken. A
footing entry replaces the round footing a separate placement gets, or removes it so a terrain edit shaped
round the placement carries its ground.
"""
from pathlib import Path
import json
import math
import struct
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import content as C
import landscape as L
import object_edits as OE
import scene_io as S

REGION = 'grey_moors'
CENTER = [900., 500.]
ABOUT = [40., -60.]
TEMPLE = [50., -60.]                  # the host: rotated half a turn, like the glacier temple
STEEPLE = [52., -59.]                 # on the temple's roof, 10 m up
CAIRN = [10., -15.]
YARD = ([30., -40.], [30., -20.])     # one compound
TREE = [-20., -80.]                   # a natural prototype, never a retained structure
OFFSET = [.5, .25, -1.5]
TURNED = {'translation': [760., 0., 640.], 'about_x': ABOUT[0], 'about_z': ABOUT[1], 'squeeze_x': .8, 'squeeze_z': .85,
          'yaw_degrees': 90., 'datum': 'ground'}
HALF_TURN = [0., 1., 0., 0.]          # glTF quaternion: pi about +Y


def legacy_height(x, z):
    return 20. + .1 * np.asarray(x, float) + .02 * np.asarray(z, float)


def document():
    nodes = [{'name': 'Group_Structures', 'children': [1, 4, 5, 6, 7, 8]},
             {'name': 'Landmark_Temple', 'translation': [TEMPLE[0], 0., TEMPLE[1]], 'rotation': HALF_TURN, 'children': [2, 3]},
             {'name': 'Landmark_Temple__body', 'mesh': 0},
             {'name': 'Landmark_Temple__icicles', 'mesh': 1, 'translation': [0., 9., 3.]},
             {'name': 'Landmark_Steeple', 'translation': [STEEPLE[0], 10., STEEPLE[1]], 'mesh': 2},
             {'name': 'Landmark_cairn', 'translation': [CAIRN[0], 0., CAIRN[1]], 'mesh': 3},
             {'name': 'Landmark_yard_north', 'translation': [YARD[0][0], 0., YARD[0][1]], 'mesh': 3},
             {'name': 'Landmark_yard_south', 'translation': [YARD[1][0], 0., YARD[1][1]], 'mesh': 3},
             {'name': 'Tree_00', 'translation': [TREE[0], 0., TREE[1]], 'mesh': 3}]
    boxes = [([-6., 0., -4.], [8., 10., 4.]),       # the temple body, off-centre on its own origin
             ([-5., -1., -.2], [5., 0., .2]),       # a row of icicles
             ([-1., 0., -1.], [1., 6., 1.]),        # the steeple
             ([-1., 0., -1.], [1., 2., 1.])]
    return {'nodes': nodes, 'meshes': [{'primitives': [{'attributes': {'POSITION': i}}]} for i in range(len(boxes))],
            'accessors': [{'min': low, 'max': high} for low, high in boxes]}


def placements():
    return [{'node': 'Landmark_Temple', 'kind': 'landmark', 'landmark': 'temple', 'collides': True,
             'position': [TEMPLE[0], 0., TEMPLE[1]], 'rotation_y': math.pi},
            {'node': 'Landmark_Steeple', 'kind': 'landmark', 'position': [STEEPLE[0], 10., STEEPLE[1]]},
            {'node': 'Landmark_cairn', 'kind': 'structure', 'collides': True, 'position': [CAIRN[0], 0., CAIRN[1]]},
            {'node': 'Landmark_yard_north', 'kind': 'structure', 'assembly': 'yard', 'position': [YARD[0][0], 0., YARD[0][1]]},
            {'node': 'Landmark_yard_south', 'kind': 'structure', 'assembly': 'yard', 'position': [YARD[1][0], 0., YARD[1][1]]},
            {'node': 'Tree_00', 'kind': 'tree', 'position': [TREE[0], 0., TREE[1]]}]


class World:
    """A sloped continent one territory owns, recording every footing it is asked for."""

    def __init__(self, transform, **sections):
        self.regions = {REGION: {'id': REGION, 'center': CENTER}}
        self.ids = [REGION]
        self.plan = {'sea_level': 0., 'rivers': [], 'lakes': [], 'regions': [self.regions[REGION]],
                     'retained_transforms': {REGION: transform}, **sections}
        self.x = np.arange(0., 1600.1, 2.)
        self.z = np.arange(0., 1600.1, 2.)
        self.x0 = self.z0 = 0.
        self.gx, self.gz = np.meshgrid(self.x, self.z)
        self.original_height = self.height_at(self.gx, self.gz)
        self.lift = 0.
        self.footings = []
        self.assembly_footings = []

    def height_at(self, x, z):
        return 5. + .05 * np.asarray(x, float) + .02 * np.asarray(z, float) + getattr(self, 'lift', 0.)

    def owner_at(self, x, z):
        return np.zeros(np.shape(x), int)

    def foundation(self, center, radius, height, feather=16, obstacle=False):
        self.footings.append({'center': np.asarray(center, float).tolist(), 'radius': float(radius), 'height': float(height),
                              'feather': float(feather), 'obstacle': bool(obstacle)})

    def assembly_foundation(self, sl, target, weight):
        self.assembly_footings.append((sl, np.asarray(target, float), np.asarray(weight, float)))


def loaded(tmp_path, monkeypatch, transform=TURNED, edits=(), **sections):
    monkeypatch.setattr(OE, 'load_edits', lambda *a, **k: {'version': 1, 'objects': list(edits), 'vegetationAreas': []})
    folder = tmp_path / REGION
    folder.mkdir(parents=True, exist_ok=True)
    S.dump_glb(folder / 'library.glb', document(), b'')
    (folder / 'library.json').write_text(json.dumps({'placements': placements()}))
    x = np.arange(-300., 300.1, 5.)
    gx, gz = np.meshgrid(x, x)
    np.savez(folder / 'foundation-samples.npz', x=x, z=x, height=legacy_height(gx, gz))
    world = World(transform, **sections)
    template = {'spawnPoints': [{'id': 'arrival', 'default': True, 'position': [0., 0., 0.]}]}
    content = C.Content(world, tmp_path, {REGION: template}, {})
    content.load()
    return world, content


def attach(*entries):
    return {'retained_attachments': {REGION: [dict(entry) for entry in entries]}}


STEEPLE_ON_TEMPLE = {'node': 'Landmark_Steeple', 'host': 'Landmark_Temple', 'offset': OFFSET}


def index_of(doc, name):
    return next(i for i, n in enumerate(doc['nodes']) if n.get('name') == name)


def corners(low, high):
    return np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])


def box_of(doc, name):
    node = doc['nodes'][index_of(doc, name)]
    accessor = doc['accessors'][doc['meshes'][node['mesh']]['primitives'][0]['attributes']['POSITION']]
    return corners(accessor['min'], accessor['max'])


def legacy_vertices(name):
    doc = document()
    matrix = S.GR.hierarchy(doc)[0][index_of(doc, name)]
    return box_of(doc, name) @ matrix[:3, :3].T + matrix[:3, 3]


def composed_vertices(content, placement, name):
    doc, _ = content.documents[REGION]
    matrix = S.GR.hierarchy(doc)[0][index_of(doc, name)]
    return box_of(doc, name) @ matrix[:3, :3].T + matrix[:3, 3] + content.placement_by_name[(REGION, placement)]['shift']


def turn(dx, dz, yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return np.array([dx * c - dz * s, dx * s + dz * c])


def host_pivot():
    """The temple's turn pivot: the base centre of its legacy bounds (object_edits.base_pivot)."""
    doc = document()
    low, high = S.subtree_bounds(doc, b'', index_of(doc, 'Landmark_Temple'))
    return np.array([(low[0] + high[0]) * .5, (low[2] + high[2]) * .5])


def rigid(content, vertices, yaw, offset=(0., 0., 0.)):
    """Where legacy vertices stand when carried rigidly by the temple: pivot + shift + R(v - pivot + offset)."""
    pivot = host_pivot()
    shift = content.placement_by_name[(REGION, 'Landmark_Temple')]['shift']
    out = []
    for v in vertices:
        x, z = pivot + shift[[0, 2]] + turn(v[0] - pivot[0] + offset[0], v[2] - pivot[1] + offset[2], yaw)
        out.append([x, v[1] + shift[1] + offset[1], z])
    return np.array(out)


@pytest.mark.parametrize('yaw', [90., -34.])
def test_an_attached_placement_keeps_its_exact_place_on_its_host_through_a_turn_a_squeeze_and_a_slope(tmp_path, monkeypatch, yaw):
    transform = dict(TURNED, yaw_degrees=yaw)
    world, content = loaded(tmp_path, monkeypatch, transform, **attach(STEEPLE_ON_TEMPLE))
    # The host itself is the rigid frame: its composed vertices are its turn pivot carried by its shift.
    np.testing.assert_allclose(composed_vertices(content, 'Landmark_Temple', 'Landmark_Temple__body'),
                               rigid(content, legacy_vertices('Landmark_Temple__body'), yaw), atol=1e-9)
    # The steeple rides on it, offset in the legacy frame, turned and never squeezed.
    steeple = composed_vertices(content, 'Landmark_Steeple', 'Landmark_Steeple')
    np.testing.assert_allclose(steeple, rigid(content, legacy_vertices('Landmark_Steeple'), yaw, OFFSET), atol=1e-9)
    temple, carried = (content.placement_by_name[(REGION, name)] for name in ('Landmark_Temple', 'Landmark_Steeple'))
    assert carried['shift'][1] == pytest.approx(temple['shift'][1] + OFFSET[1])
    np.testing.assert_allclose(carried['low'], steeple.min(axis=0), atol=1e-9)
    np.testing.assert_allclose(carried['high'], steeple.max(axis=0), atol=1e-9)
    np.testing.assert_allclose(np.concatenate(content.bounds_by_name[(REGION, 'Landmark_Steeple')]),
                               np.concatenate([carried['low'], carried['high']]), atol=1e-9)
    assert carried['attachment'] == {'host': 'Landmark_Temple', 'offset': OFFSET}
    assert content.attachment_order == [(REGION, 'Landmark_Steeple')]
    # No footing of its own; the temple, the cairn and nothing else get one.
    assert len(world.footings) == 2
    # Mapped and grounded on its own it would have stood elsewhere: the squeeze and the slope part the two.
    pivot = np.asarray(C.OE.base_pivot(*S.subtree_bounds(document(), b'', index_of(document(), 'Landmark_Steeple'))))
    alone = np.asarray(L.retained_map_xz(transform, pivot[[0, 2]]))
    assert np.linalg.norm(alone - ((carried['low'] + carried['high']) * .5)[[0, 2]]) > .5
    # Linked records follow the carried placement's shift.
    record = content.mapped_point(REGION, [STEEPLE[0], 12., STEEPLE[1]], node='Landmark_Steeple')
    assert record[1] == pytest.approx(12. + carried['shift'][1])
    assert content.mapping[(REGION, 'Landmark_Steeple')] is carried['shift']


def test_under_a_list_transform_the_carried_shift_is_the_hosts_plus_the_offset(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, [760., 0., 640.], **attach(STEEPLE_ON_TEMPLE))
    temple, carried = (content.placement_by_name[(REGION, name)] for name in ('Landmark_Temple', 'Landmark_Steeple'))
    np.testing.assert_allclose(carried['shift'], temple['shift'] + OFFSET, atol=1e-12)
    np.testing.assert_allclose(composed_vertices(content, 'Landmark_Steeple', 'Landmark_Steeple'),
                               legacy_vertices('Landmark_Steeple') + temple['shift'] + OFFSET, atol=1e-9)


def test_a_carried_placement_can_carry_another_and_the_library_order_is_kept(tmp_path, monkeypatch):
    chain = attach({'node': 'Landmark_cairn', 'host': 'Landmark_Steeple', 'offset': [1., 0., 0.]}, STEEPLE_ON_TEMPLE)
    world, content = loaded(tmp_path, monkeypatch, [760., 0., 640.], **chain)
    shifts = {name: content.placement_by_name[(REGION, name)]['shift'] for name in ('Landmark_Temple', 'Landmark_Steeple', 'Landmark_cairn')}
    np.testing.assert_allclose(shifts['Landmark_cairn'], shifts['Landmark_Temple'] + OFFSET + [1., 0., 0.], atol=1e-12)
    assert content.attachment_order == [(REGION, 'Landmark_Steeple'), (REGION, 'Landmark_cairn')]
    assert [obj['node'] for obj in content.objects] == ['Landmark_Temple', 'Landmark_Steeple', 'Landmark_cairn',
                                                        'Landmark_yard_north', 'Landmark_yard_south']


def test_reground_moves_a_carried_placement_by_its_hosts_correction_and_refuses_a_torn_one(tmp_path, monkeypatch):
    world, content = loaded(tmp_path, monkeypatch, TURNED, **attach(STEEPLE_ON_TEMPLE))
    temple, carried = (content.placement_by_name[(REGION, name)] for name in ('Landmark_Temple', 'Landmark_Steeple'))
    before = temple['shift'].copy(), carried['shift'].copy(), carried['targetGround'], carried['low'].copy()
    world.lift = 3.                       # the ground under both rises 3 m; under the steeple alone it would differ
    content.reground()
    np.testing.assert_allclose(temple['shift'] - before[0], [0., 3., 0.], atol=1e-9)
    np.testing.assert_allclose(carried['shift'] - before[1], [0., 3., 0.], atol=1e-9)
    assert carried['targetGround'] == pytest.approx(before[2] + 3.)
    np.testing.assert_allclose(carried['low'] - before[3], [0., 3., 0.], atol=1e-9)
    np.testing.assert_allclose(content.bounds_by_name[(REGION, 'Landmark_Steeple')][0], carried['low'])
    # A carried placement is never settled on the ground under itself: a ground that rises only under the
    # steeple moves nothing.
    world.lift = 0.
    content.reground()
    steeple_centre = (carried['low'] + carried['high']) * .5
    world.height_at = lambda x, z, base=world.height_at: base(x, z) + (7. if abs(float(np.max(x)) - steeple_centre[0]) < 1e-6 else 0.)
    settled = temple['shift'].copy(), carried['shift'].copy()
    content.reground()
    np.testing.assert_allclose(temple['shift'], settled[0], atol=1e-9)
    np.testing.assert_allclose(carried['shift'], settled[1], atol=1e-9)
    temple['shift'][0] += 1.
    with pytest.raises(ValueError, match='Landmark_Steeple rides on Landmark_Temple, but a stage after load moved'):
        content.reground()


def test_a_host_moved_by_an_object_edit_translation_still_carries_its_attachment(tmp_path, monkeypatch):
    move = {'root': 'grey_moors_Landmark_Temple_WorldPlacement', 'action': 'transform', 'pivot': [0., 0., 0.],
            'translate': [4., 1., -2.], 'yawDegrees': 0, 'scale': 1}
    world, content = loaded(tmp_path, monkeypatch, TURNED, edits=[move], **attach(STEEPLE_ON_TEMPLE))
    np.testing.assert_allclose(composed_vertices(content, 'Landmark_Steeple', 'Landmark_Steeple'),
                               rigid(content, legacy_vertices('Landmark_Steeple'), 90., OFFSET), atol=1e-9)


@pytest.mark.parametrize('entries, message', [
    ([{'node': 'Landmark_Nothing', 'host': 'Landmark_Temple'}], "node 'Landmark_Nothing' is not a retained placement"),
    ([{'node': 'Landmark_Steeple', 'host': 'Landmark_Nothing'}], "host 'Landmark_Nothing' is not a retained placement"),
    ([{'node': 'Landmark_Temple', 'host': 'Landmark_Temple'}], 'cannot be attached to itself'),
    ([{'node': 'Landmark_yard_north', 'host': 'Landmark_Temple'}], 'belongs to the compound grey_moors.yard'),
    ([{'node': 'Landmark_Steeple', 'host': 'Landmark_cairn'}, {'node': 'Landmark_cairn', 'host': 'Landmark_Steeple'}], 'is a cycle'),
    ([{'node': 'Landmark_Steeple', 'host': 'Landmark_Temple'}, {'node': 'Landmark_Steeple', 'host': 'Landmark_cairn'}], 'attached twice'),
    ([{'node': 'Landmark_Steeple', 'host': 'Landmark_Temple', 'offset': [0., 1.]}], 'offset must be three finite metres'),
    ([{'node': 'Landmark_Steeple', 'host': 'Landmark_Temple', 'offest': [0., 1., 0.]}], r"unknown key\(s\) \['offest'\]"),
    ([{'node': 'Tree_00', 'host': 'Landmark_Temple'}], r"attaches or foots \['Tree_00'\], which are not retained structures"),
    ([{'node': 'Landmark_Steeple', 'host': 'Tree_00'}], 'rides on Tree_00, which is not a retained structure'),
])
def test_attachments_that_cannot_hold_are_refused(tmp_path, monkeypatch, entries, message):
    with pytest.raises(ValueError, match=message):
        loaded(tmp_path, monkeypatch, TURNED, **attach(*entries))


def test_object_edits_that_would_part_an_attachment_and_unknown_territories_are_refused(tmp_path, monkeypatch):
    own = {'root': 'grey_moors_Landmark_Steeple_WorldPlacement', 'action': 'transform', 'pivot': [0., 0., 0.],
           'translate': [1., 0., 0.], 'yawDegrees': 0, 'scale': 1}
    with pytest.raises(ValueError, match='Landmark_Steeple rides on Landmark_Temple, so the object edit'):
        loaded(tmp_path, monkeypatch, TURNED, edits=[own], **attach(STEEPLE_ON_TEMPLE))
    turned = dict(own, root='grey_moors_Landmark_Temple_WorldPlacement', translate=[0., 0., 0.], yawDegrees=45.)
    with pytest.raises(ValueError, match='carries the yaw or scale object edit'):
        loaded(tmp_path, monkeypatch, TURNED, edits=[turned], **attach(STEEPLE_ON_TEMPLE))
    for section in C.RETAINED_SECTIONS:
        with pytest.raises(ValueError, match=section + r": no territory \['nowhere'\]"):
            loaded(tmp_path, monkeypatch, TURNED, **{section: {'nowhere': []}})
    with pytest.raises(ValueError, match='is a boat'):
        C.retained_attachments({'retained_attachments': {REGION: [{'node': 'Prop_skiff_00', 'host': 'Landmark_Temple'}]}},
                               REGION, placements() + [{'node': 'Prop_skiff_00', 'kind': 'prop'}])


def snapshot(world, content):
    result = {}
    for obj in content.objects:
        result[obj['node']] = [*obj['shift'], *obj['low'], *obj['high'], obj['targetGround']]
    result['residuals'] = sorted((key[1], *value) for key, value in content.residuals.items())
    result['footings'] = [(f['center'], f['radius'], f['height'], f['feather'], f['obstacle']) for f in world.footings]
    doc, _ = content.documents[REGION]
    result['matrices'] = [S.GR.local_matrix(node).tolist() for node in doc['nodes']]
    result['meshes'] = [node.get('mesh') for node in doc['nodes']]
    return result


@pytest.mark.parametrize('transform', [TURNED, [760., 0., 640.]])
def test_empty_sections_place_everything_exactly_as_no_sections(tmp_path, monkeypatch, transform):
    expected = snapshot(*loaded(tmp_path, monkeypatch, transform))
    empty = {section: {REGION: []} for section in C.RETAINED_SECTIONS}
    assert snapshot(*loaded(tmp_path, monkeypatch, transform, **empty)) == expected
    world, content = loaded(tmp_path, monkeypatch, transform)
    assert content.attachments == {} and content.attachment_order == []


# ------------------------------------------------------------------------------------------- part edits
def geometry_document():
    """A placement under a half-turned parent with real triangles: a body, a part, and a part inside that part."""
    triangle = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 1.]], np.float32)
    body = triangle.tobytes()
    nodes = [{'name': 'Group_Structures', 'children': [1, 5]},
             {'name': 'Landmark_Temple', 'translation': [10., 2., 5.], 'rotation': HALF_TURN, 'children': [2, 3]},
             {'name': 'Landmark_Temple__body', 'mesh': 0},
             {'name': 'Landmark_Temple__icicles', 'mesh': 0, 'translation': [1., 9., 3.], 'rotation': [0., .70710678, 0., .70710678],
              'children': [4]},
             {'name': 'Landmark_Temple__icicle_tip', 'mesh': 0, 'translation': [0., -1., 2.]},
             {'name': 'Landmark_Other', 'mesh': 0, 'translation': [40., 0., 0.]}]
    document = {'nodes': nodes, 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
                'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                               'min': triangle.min(axis=0).tolist(), 'max': triangle.max(axis=0).tolist()}],
                'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(body)}]}
    return document, body


GEOMETRY_PLACEMENTS = [{'node': 'Landmark_Temple', 'kind': 'landmark'}, {'node': 'Landmark_Other', 'kind': 'structure'}]


def world_triangles(document, body, name):
    return S.GR.triangles(document, body, [index_of(document, name)])


def test_a_translated_part_moves_by_exactly_the_source_frame_vector_under_a_half_turned_parent():
    document, body = geometry_document()
    before = {name: world_triangles(document, body, name) for name in
              ('Landmark_Temple__body', 'Landmark_Temple__icicles', 'Landmark_Temple__icicle_tip', 'Landmark_Other')}
    pristine = json.dumps(document)
    edited = C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS,
                                [{'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0., 0., -6.]}])
    assert json.dumps(document) == pristine, 'the library document itself is never changed'
    moved = [0., 0., -6.]
    # The parent's half turn would have sent a local -6 to world +6; the source-frame vector is exact, and the
    # part's own child goes with it.
    np.testing.assert_allclose(world_triangles(edited, body, 'Landmark_Temple__icicles'), before['Landmark_Temple__icicles'] + moved, atol=1e-9)
    np.testing.assert_allclose(world_triangles(edited, body, 'Landmark_Temple__icicle_tip'), before['Landmark_Temple__icicle_tip'] + moved, atol=1e-9)
    for name in ('Landmark_Temple__body', 'Landmark_Other'):
        np.testing.assert_allclose(world_triangles(edited, body, name), before[name], atol=1e-12)
    # A part inside a turned part moves by its own source-frame vector too.
    nested = C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS,
                                [{'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicle_tip', 'translate': [1.5, -2., .25]}])
    np.testing.assert_allclose(world_triangles(nested, body, 'Landmark_Temple__icicle_tip'),
                               before['Landmark_Temple__icicle_tip'] + [1.5, -2., .25], atol=1e-9)
    np.testing.assert_allclose(world_triangles(nested, body, 'Landmark_Temple__icicles'), before['Landmark_Temple__icicles'], atol=1e-12)


def test_a_removed_part_drops_its_triangles_and_its_childrens():
    document, body = geometry_document()
    root = index_of(document, 'Landmark_Temple')
    meshes = lambda doc: [i for i in S.descendants(doc, [root]) if 'mesh' in doc['nodes'][i]]
    assert len(S.GR.triangles(document, body, meshes(document))) == 3
    edited = C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS,
                                [{'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'remove': True}])
    assert len(S.GR.triangles(edited, body, meshes(edited))) == 1
    np.testing.assert_allclose(S.GR.triangles(edited, body, meshes(edited)), world_triangles(document, body, 'Landmark_Temple__body'))
    low, high = S.subtree_bounds(edited, body, root)
    body_low, body_high = S.subtree_bounds(document, body, index_of(document, 'Landmark_Temple__body'))
    np.testing.assert_allclose([low, high], [body_low, body_high])


def test_no_part_edits_leave_the_document_as_it_is():
    document, body = geometry_document()
    assert C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS, []) is document


@pytest.mark.parametrize('entry, message', [
    ({'node': 'Landmark_Nowhere', 'part': 'Landmark_Temple__icicles', 'translate': [0, 0, 1]}, "'Landmark_Nowhere' is not a retained placement"),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__roof', 'translate': [0, 0, 1]}, "has no part 'Landmark_Temple__roof'"),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Other', 'translate': [0, 0, 1]}, 'Landmark_Other lies outside the subtree of Landmark_Temple'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple', 'translate': [0, 0, 1]}, 'is the placement itself'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles'}, 'not neither'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0, 0, 1], 'remove': True}, 'not both'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0, 1]}, 'translate must be three finite metres'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0, 0, float('nan')]}, 'translate must be three finite metres'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'remove': 'yes'}, 'remove must be true or false'),
    ({'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'move': [0, 0, 1]}, r"unknown key\(s\) \['move'\]"),
])
def test_part_edits_that_name_nothing_or_do_nothing_clear_are_refused(entry, message):
    document, body = geometry_document()
    with pytest.raises(ValueError, match=message):
        C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS, [entry])


def test_a_part_edited_twice_or_named_twice_in_its_placement_is_refused():
    document, body = geometry_document()
    twice = [{'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0, 0, 1]},
             {'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'remove': True}]
    with pytest.raises(ValueError, match='edited twice'):
        C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS, twice)
    document['nodes'][4]['name'] = 'Landmark_Temple__icicles'
    with pytest.raises(ValueError, match='holds 2 parts named Landmark_Temple__icicles'):
        C.apply_part_edits(REGION, document, body, GEOMETRY_PLACEMENTS, twice[:1])


def test_a_part_edit_reaches_the_placements_bounds_through_load(tmp_path, monkeypatch):
    edit = {'retained_part_edits': {REGION: [{'node': 'Landmark_Temple', 'part': 'Landmark_Temple__icicles', 'translate': [0., 0., -8.]}]}}
    world, content = loaded(tmp_path, monkeypatch, [760., 0., 640.], **edit)
    world, plain = loaded(tmp_path, monkeypatch, [760., 0., 640.])
    moved, before = (c.placement_by_name[(REGION, 'Landmark_Temple')] for c in (content, plain))
    # The half-turned icicles hung at z -63.2 inside the body's edge at -64; moved 8 m they end at -71.2, so the
    # placement's bounds (and with them its pivot, grounding and footing) reach 7.2 m further.
    assert moved['low'][2] == pytest.approx(before['low'][2] - 7.2)
    np.testing.assert_allclose(moved['high'], before['high'])
    doc, _ = content.documents[REGION]
    matrix = S.GR.hierarchy(doc)[0][index_of(doc, 'Landmark_Temple__icicles')]
    np.testing.assert_allclose(matrix[:3, 3], [TEMPLE[0], 9., TEMPLE[1] - 3. - 8.], atol=1e-9)


# ------------------------------------------------------------------------------------------- footings
def test_a_footing_entry_replaces_the_round_footing_or_removes_it(tmp_path, monkeypatch):
    world, plain = loaded(tmp_path, monkeypatch, TURNED)
    assert len(world.footings) == 3                       # temple, steeple and cairn; the compound has its own
    footings = {'retained_footings': {REGION: [{'node': 'Landmark_Temple', 'radius': 0},
                                               {'node': 'Landmark_cairn', 'radius': 5., 'feather': 3.},
                                               {'node': 'Landmark_Steeple', 'radius': 20.}]}}
    world, content = loaded(tmp_path, monkeypatch, TURNED, **footings)
    assert len(world.footings) == 2
    by_centre = {tuple(np.round(f['center'], 6)): f for f in world.footings}
    for name, radius, feather in (('Landmark_cairn', 5., 3.), ('Landmark_Steeple', 20., 14.)):
        obj = content.placement_by_name[(REGION, name)]
        footing = by_centre[tuple(np.round(((obj['low'] + obj['high']) * .5)[[0, 2]], 6))]
        assert (footing['radius'], footing['feather']) == (radius, pytest.approx(feather))
        assert footing['height'] == pytest.approx(obj['targetGround'])
    # The placement itself stands exactly where it stood with its footing.
    for name in ('Landmark_Temple', 'Landmark_cairn', 'Landmark_Steeple'):
        np.testing.assert_allclose(content.placement_by_name[(REGION, name)]['shift'], plain.placement_by_name[(REGION, name)]['shift'])


@pytest.mark.parametrize('entry, message', [
    ({'node': 'Landmark_Nothing', 'radius': 0}, "'Landmark_Nothing' is not a retained placement"),
    ({'node': 'Landmark_yard_north', 'radius': 0}, 'belongs to the compound grey_moors.yard, whose footprints are its footing'),
    ({'node': 'Landmark_cairn', 'radius': -1}, 'radius must be a distance in metres of at least 0'),
    ({'node': 'Landmark_cairn', 'radius': True}, 'radius must be a distance'),
    ({'node': 'Landmark_cairn', 'radius': 4, 'feather': 0}, 'feather must be a distance in metres above 0'),
    ({'node': 'Landmark_cairn', 'size': 4}, r"unknown key\(s\) \['size'\]"),
    ({'node': 'Tree_00', 'radius': 0}, r"attaches or foots \['Tree_00'\]"),
])
def test_footings_that_cannot_apply_are_refused(tmp_path, monkeypatch, entry, message):
    with pytest.raises(ValueError, match=message):
        loaded(tmp_path, monkeypatch, TURNED, retained_footings={REGION: [entry]})


def test_a_footing_for_a_carried_placement_or_given_twice_is_refused(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='is attached to a host and has no footing of its own'):
        loaded(tmp_path, monkeypatch, TURNED, retained_footings={REGION: [{'node': 'Landmark_Steeple', 'radius': 0}]},
               **attach(STEEPLE_ON_TEMPLE))
    with pytest.raises(ValueError, match='Landmark_cairn is given twice'):
        loaded(tmp_path, monkeypatch, TURNED, retained_footings={REGION: [{'node': 'Landmark_cairn', 'radius': 0},
                                                                          {'node': 'Landmark_cairn', 'radius': 3}]})
