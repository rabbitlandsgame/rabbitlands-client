"""Library meshes wound inward against their outward normals are reversed, and only those triangles."""
from pathlib import Path
import json
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_toolkit'))
import scene_io as S
import validate_gltf
import winding as W

INDEX_DTYPES = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}


def cube():
    """(corners, normals, triangles) of a 2 m cube: 24 corners with face normals, each face counter-clockwise seen from outside."""
    corners, normals, triangles = [], [], []
    for axis, (u, v) in enumerate(((1, 2), (2, 0), (0, 1))):
        for sign in (1., -1.):
            quad = [(-1., -1.), (1., -1.), (1., 1.), (-1., 1.)]
            base = len(corners)
            for su, sv in (quad if sign > 0 else quad[::-1]):
                corner = np.zeros(3)
                corner[axis], corner[u], corner[v] = sign, su, sv
                normal = np.zeros(3)
                normal[axis] = sign
                corners.append(corner)
                normals.append(normal)
            triangles += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return np.array(corners), np.array(normals), np.array(triangles)


def build(parts, *, index_type=5123, double_sided=False, lead=b''):
    """(document, body) with one node and one mesh per part: (positions, normals or None, triangles)."""
    body = bytearray(lead)
    document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
                'materials': [{'name': 'stone', 'doubleSided': double_sided}], 'accessors': [], 'bufferViews': []}

    def accessor(values, component, kind, target, bounds=False):
        body.extend(b'\0' * ((-len(body)) % 4))
        data = np.ascontiguousarray(values, dtype={5126: np.float32, **INDEX_DTYPES}[component])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(body), 'byteLength': data.nbytes, 'target': target})
        body.extend(data.tobytes())
        entry = {'bufferView': len(document['bufferViews']) - 1, 'componentType': component,
                 'count': len(data) if kind != 'SCALAR' else data.size, 'type': kind}
        if bounds:
            entry.update(min=data.reshape(len(data), -1).min(axis=0).tolist(), max=data.reshape(len(data), -1).max(axis=0).tolist())
        document['accessors'].append(entry)
        return len(document['accessors']) - 1

    for number, (positions, normals, triangles) in enumerate(parts):
        attributes = {'POSITION': accessor(positions, 5126, 'VEC3', 34962, bounds=True)}
        if normals is not None:
            attributes['NORMAL'] = accessor(normals, 5126, 'VEC3', 34962)
        indices = accessor(np.asarray(triangles).reshape(-1), index_type, 'SCALAR', 34963)
        document['meshes'].append({'name': f'Part_{number}', 'primitives': [{'attributes': attributes, 'indices': indices, 'material': 0}]})
        document['nodes'].append({'name': f'Part_{number}', 'mesh': number})
        document['scenes'][0]['nodes'].append(number)
    document['buffers'] = [{'byteLength': len(body)}]
    return document, bytes(body)


def volume(triangles):
    return float(np.einsum('ij,ij->i', triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6.)


def facing(triangles):
    return np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])


def test_the_fixture_cube_is_wound_outward():
    corners, normals, triangles = cube()
    world = corners[triangles]
    assert volume(world) == pytest.approx(8.)
    assert (np.einsum('ij,ij->i', facing(world), normals[triangles].sum(axis=1)) > 0).all()


def test_a_cube_wound_inward_with_outward_normals_is_turned_right_side_out():
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])])
    assert volume(S.GR.triangles(document, body, [0])) == pytest.approx(-8.)
    before = W.winding_report(document, body)[0]
    assert before['status'] == 'corrected' and before['flipped_triangles'] == 12 and before['triangles'] == 12
    assert before['disagreeing_area_share'] == pytest.approx(1.) and before['area'] == pytest.approx(24.)
    assert before['closed'] and before['signed_volume'] == pytest.approx(-8.) and before['corrected_signed_volume'] == pytest.approx(8.)

    fixed, fixed_body, report = W.normalise_winding(document, body)
    assert report['corrected_primitives'] == 1 and report['flipped_triangles'] == 12
    assert report['flipped_area'] == pytest.approx(24.)
    world = S.GR.triangles(fixed, fixed_body, [0])
    assert volume(world) == pytest.approx(8.)
    order = S.GR.accessor(fixed, fixed_body, fixed['meshes'][0]['primitives'][0]['indices']).reshape(-1, 3).astype(int)
    assert (np.einsum('ij,ij->i', facing(world), normals[order].sum(axis=1)) > 0).all(), 'every triangle agrees with its normals'
    np.testing.assert_array_equal(np.sort(order, axis=1), np.sort(triangles, axis=1))
    after = W.winding_report(fixed, fixed_body)
    assert [r['status'] for r in after] == ['consistent']
    assert after[0]['flipped_triangles'] == 0 and after[0]['disagreeing_area_share'] == 0.
    assert after[0]['signed_volume'] == pytest.approx(8.)


def test_a_cube_already_wound_outward_keeps_its_accessors_and_body():
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles)])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    assert fixed is not document and fixed == document
    assert fixed['accessors'] == document['accessors'] and fixed['bufferViews'] == document['bufferViews']
    assert fixed['meshes'][0]['primitives'][0]['indices'] == document['meshes'][0]['primitives'][0]['indices']
    assert fixed_body == body and report['appended_bytes'] == 0
    assert report['flipped_triangles'] == 0 and report['corrected_primitives'] == 0
    assert [r['status'] for r in report['records']] == ['consistent']


def test_a_mixed_primitive_reverses_only_its_backwards_triangles():
    corners, normals, triangles = cube()
    backwards = [1, 4, 7, 10]
    wound = triangles.copy()
    wound[backwards] = wound[backwards][:, [0, 2, 1]]
    faces = np.vstack([wound, [[0, 0, 1]]])        # and one degenerate triangle, which has no facing
    # Byte indices and an odd lead: the body ends off a 4-byte boundary.
    document, body = build([(corners, normals, faces)], index_type=5121, lead=b'\x01\x02')
    assert len(body) % 4
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['flipped_triangles'] == 4 and record['degenerate_triangles'] == 1 and record['triangles'] == 13
    assert record['disagreeing_area_share'] == pytest.approx(4 / 12)
    primitive = fixed['meshes'][0]['primitives'][0]
    accessor = fixed['accessors'][primitive['indices']]
    view = fixed['bufferViews'][accessor['bufferView']]
    assert primitive['indices'] == len(document['accessors']) and accessor['componentType'] == 5121
    assert view['byteOffset'] % 4 == 0 and view['byteOffset'] >= len(body) and view['target'] == 34963
    assert fixed['buffers'][0]['byteLength'] == len(fixed_body) and fixed_body[:len(body)] == body
    new = S.GR.accessor(fixed, fixed_body, primitive['indices']).reshape(-1, 3).astype(int)
    assert np.flatnonzero((new != faces).any(axis=1)).tolist() == backwards
    np.testing.assert_array_equal(new[:12], triangles)
    np.testing.assert_array_equal(new[12], [0, 0, 1])
    # Positions, normals and the old index accessor are untouched.
    assert fixed['accessors'][:len(document['accessors'])] == document['accessors']
    for name in ('POSITION', 'NORMAL'):
        assert primitive['attributes'][name] == document['meshes'][0]['primitives'][0]['attributes'][name]


def test_a_surface_wound_one_way_outvotes_a_crease_whose_normals_point_the_wrong_way():
    corners, normals, triangles = cube()
    # The +x face's vertex normals point into the cube; its two triangles are wound like the rest.
    creased = normals.copy()
    creased[triangles[:2].reshape(-1)] *= -1
    document, body = build([(corners, creased, triangles)])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['opposing_triangles'] == 2 and record['outvoted_triangles'] == 2
    assert record['flipped_triangles'] == 0 and record['status'] == 'outvoted' and report['left_alone']['outvoted'] == 1
    assert fixed == document and fixed_body == body

    # Wound inward, the same crease agrees with its own normals but turns with the cube it belongs to.
    document, body = build([(corners, creased, triangles[:, [0, 2, 1]])])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['opposing_triangles'] == 10 and record['flipped_triangles'] == 12 and record['carried_triangles'] == 2
    assert volume(S.GR.triangles(fixed, fixed_body, [0])) == pytest.approx(8.)
    assert W.winding_report(fixed, fixed_body)[0]['flipped_triangles'] == 0


def test_a_closed_solid_wound_outward_keeps_its_winding_against_inward_normals():
    """A top-down lathe closed at both ends: its winding encloses the solid, its normals point inside."""
    corners, normals, triangles = cube()
    document, body = build([(corners, -normals, triangles)])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['opposing_triangles'] == 12 and record['enclosing_triangles'] == 12
    assert record['flipped_triangles'] == 0 and record['status'] == 'outvoted'
    assert fixed == document and fixed_body == body


def test_a_mesh_named_to_keep_its_winding_keeps_its_open_sheets_only():
    corners, normals, front = card()
    document, body = build([(corners, normals, front[:, [0, 2, 1]])])
    document['meshes'][0]['name'] = 'frozen_cascade_00__alpine_blue_ice'
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'authored_winding' and record['authored_triangles'] == 2 and record['flipped_triangles'] == 0
    assert report['left_alone']['authored_winding'] == 1
    # The winding stays; the normals, which point away from the side the sheet shows, turn (see the relit test).
    assert fixed['meshes'][0]['primitives'][0]['indices'] == document['meshes'][0]['primitives'][0]['indices']
    assert record['relit_triangles'] == 2 and report['relit_primitives'] == 1 and fixed_body[:len(body)] == body
    document['meshes'][0]['name'] = 'Card'
    assert W.normalise_winding(document, body)[2]['records'][0]['flipped_triangles'] == 2

    # The compass rose: an open ring kept by name beside a closed star wound inward, which still turns.
    cube_corners, cube_normals, cube_triangles = cube()
    document, body = build([(np.vstack([corners, cube_corners + [0., 0., 5.]]), np.vstack([normals, cube_normals]),
                             np.vstack([front[:, [0, 2, 1]], cube_triangles[:, [0, 2, 1]] + 4]))])
    document['meshes'][0]['name'] = 'PlazaRose__crownwater_gilt'
    record = W.normalise_winding(document, body)[2]['records'][0]
    assert record['status'] == 'corrected' and record['flipped_triangles'] == 12 and record['authored_triangles'] == 2


def test_level_water_faces_up_whatever_its_normals_say():
    """A fountain pool is a flat lathe run outward from its axis: it faces up and its normals point down."""
    corners, normals, front = card()
    pool = corners[:, [0, 2, 1]]                  # the card laid flat at y = 0
    up = front[:, [0, 2, 1]]                      # wound to face +y
    assert (facing(pool[up])[:, 1] > 0).all()
    down_normals = np.tile([0., -1., 0.], (4, 1))
    document, body = build([(pool, down_normals, up)])
    document['materials'][0]['name'] = 'water_pool'
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['opposing_triangles'] == 2 and record['water_kept_triangles'] == 2
    assert record['status'] == 'water_up' and record['flipped_triangles'] == 0 and record['relit_triangles'] == 2
    assert fixed['meshes'][0]['primitives'][0]['indices'] == document['meshes'][0]['primitives'][0]['indices']
    np.testing.assert_array_equal(S.GR.accessor(fixed, fixed_body, fixed['meshes'][0]['primitives'][0]['attributes']['NORMAL']),
                                  -down_normals)

    # A bog pool wound face down turns up, as it would by its normals alone.
    document, body = build([(pool, -down_normals, front)])
    document['materials'][0]['name'] = 'grey_bog_water'
    fixed, fixed_body, report = W.normalise_winding(document, body)
    assert report['records'][0]['flipped_triangles'] == 2
    assert (facing(S.GR.triangles(fixed, fixed_body, [0]))[:, 1] > 0).all()

    # Any other material follows its normals, a name that merely contains the word included.
    for material in ('stone', 'crownwater_marble'):
        document, body = build([(pool, down_normals, up)])
        document['materials'][0]['name'] = material
        assert W.normalise_winding(document, body)[2]['records'][0]['flipped_triangles'] == 2

    # Water wound and lit face down alike is not a winding question: beside a backwards pool it stays.
    beside = pool + [5., 0., 0.]
    document, body = build([(np.vstack([pool, beside]), np.vstack([down_normals, down_normals]),
                             np.vstack([front, front[:, [0, 2, 1]] + 4]))])
    document['materials'][0]['name'] = 'water_pool'
    record = W.normalise_winding(document, body)[2]['records'][0]
    assert record['opposing_triangles'] == 2 and record['flipped_triangles'] == 0 and record['status'] == 'water_up'
    assert record['relit_triangles'] == 2 and record['relit_vertices'] == 4, 'only the pool facing up is relit'


def relit_normals(fixed, fixed_body, mesh=0):
    return S.GR.accessor(fixed, fixed_body, fixed['meshes'][mesh]['primitives'][0]['attributes']['NORMAL'])


def test_sheets_kept_against_their_normals_are_relit_from_the_side_they_show(tmp_path):
    """The Whitehorn icefall: a clockwise lathe wound outward keeps its winding, and its inward normals turn out."""
    corners, normals, front = card()
    cube_corners, cube_normals, cube_triangles = cube()
    # One primitive: the icefall sheet (wound to face -z, lit +z) beside a closed block wound inward, which still turns.
    positions = np.vstack([corners, cube_corners + [0., 0., 5.]])
    vertex_normals = np.vstack([normals, cube_normals])
    faces = np.vstack([front[:, [0, 2, 1]], cube_triangles[:, [0, 2, 1]] + 4])
    document, body = build([(positions, vertex_normals, faces)])
    document['meshes'][0]['name'] = 'frozen_cascade_01__alpine_blue_ice'
    snapshot, raw = json.loads(json.dumps(document)), bytes(body)
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'corrected' and record['flipped_triangles'] == 12 and record['authored_triangles'] == 2
    assert record['relit_triangles'] == 2 and record['relit_area'] == pytest.approx(4.) and record['relit_vertices'] == 4
    assert record['relit_shared_vertices'] == 0
    assert report['relit_primitives'] == 1 and report['relit_geometries'] == 1 and report['relit_triangles'] == 2
    assert document == snapshot and bytes(body) == raw, 'the input is never modified'
    primitive = fixed['meshes'][0]['primitives'][0]
    # The sheet's normals turn to face the side it shows; the block's normals stay and its winding turns.
    np.testing.assert_array_equal(relit_normals(fixed, fixed_body), np.vstack([-normals, cube_normals]))
    order = S.GR.accessor(fixed, fixed_body, primitive['indices']).reshape(-1, 3).astype(int)
    np.testing.assert_array_equal(order[:2], front[:, [0, 2, 1]])
    np.testing.assert_array_equal(order[2:], cube_triangles + 4)
    # New accessors on new views of the appended body; positions keep theirs.
    normal_accessor = fixed['accessors'][primitive['attributes']['NORMAL']]
    view = fixed['bufferViews'][normal_accessor['bufferView']]
    assert normal_accessor == {'componentType': 5126, 'count': 28, 'type': 'VEC3', 'bufferView': len(fixed['bufferViews']) - 1}
    assert view['target'] == W.ARRAY_BUFFER and view['byteOffset'] % 4 == 0 and view['byteOffset'] >= len(body)
    assert primitive['attributes']['POSITION'] == document['meshes'][0]['primitives'][0]['attributes']['POSITION']
    assert fixed_body[:len(body)] == body and fixed['buffers'][0]['byteLength'] == len(fixed_body)
    # Nothing is left lit from behind, and a second pass changes nothing.
    after = W.winding_report(fixed, fixed_body)[0]
    assert after['status'] == 'consistent' and after['disagreeing_area_share'] == 0.
    again, again_body, again_report = W.normalise_winding(fixed, fixed_body)
    assert again == fixed and again_body == fixed_body and again_report['relit_triangles'] == 0
    # The relit document exports and validates.
    S.dump_glb(tmp_path / 'relit.glb', fixed, fixed_body)
    assert validate_gltf.validate(str(tmp_path / 'relit.glb')).counts()['numErrors'] == 0


def test_a_relit_vertex_another_triangle_shares_keeps_its_normal():
    """A level pool triangle facing up and lit down shares one corner with a wall lit the way it faces."""
    positions = np.array([[0., 0., 0.], [0., 0., -2.], [2., 0., 0.],      # the pool, wound to face +y
                          [4., 0., 0.], [4., 2., 0.]])                    # the wall, facing +z, sharing corner 2
    vertex_normals = np.array([[0., -1., 0.], [0., -1., 0.], [0., -1., 0.], [0., 0., 1.], [0., 0., 1.]])
    faces = np.array([[0, 2, 1], [2, 3, 4]])
    assert facing(positions[faces])[0, 1] > 0 and facing(positions[faces])[1, 2] > 0
    document, body = build([(positions, vertex_normals, faces)])
    document['materials'][0]['name'] = 'water_pool'
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'water_up' and record['relit_triangles'] == 1
    assert record['relit_vertices'] == 2 and record['relit_shared_vertices'] == 1
    np.testing.assert_array_equal(relit_normals(fixed, fixed_body),
                                  [[0., 1., 0.], [0., 1., 0.], [0., -1., 0.], [0., 0., 1.], [0., 0., 1.]])


def test_relit_geometry_shared_by_several_meshes_gets_one_normal_accessor():
    corners, normals, front = card()
    document, body = build([(corners, normals, front[:, [0, 2, 1]])])
    document['meshes'][0]['name'] = 'Prop_Skep__thatch_reed'
    document['meshes'].append(json.loads(json.dumps(document['meshes'][0])) | {'name': 'Prop_Skep__thatch_reed_twin'})
    fixed, fixed_body, report = W.normalise_winding(document, body)
    first, second = (fixed['meshes'][m]['primitives'][0]['attributes']['NORMAL'] for m in (0, 1))
    assert first == second == len(document['accessors'])
    assert report['relit_primitives'] == 2 and report['relit_geometries'] == 1 and report['relit_triangles'] == 2


def card():
    """(corners, normals, front triangles) of a 2 m square card facing +z."""
    corners = np.array([[-1., -1., 0.], [1., -1., 0.], [1., 1., 0.], [-1., 1., 0.]])
    return corners, np.tile([0., 0., 1.], (4, 1)), np.array([[0, 1, 2], [0, 2, 3]])


def test_the_back_copy_of_a_two_sided_card_is_left_alone():
    corners, normals, front = card()
    # The back copy has its own vertices at the same corners and kept the front's normals.
    back = front[:, [0, 2, 1]] + 4
    cube_corners, cube_normals, cube_triangles = cube()
    positions = np.vstack([corners, corners, cube_corners + [0., 0., 5.]])
    vertex_normals = np.vstack([normals, normals, cube_normals])
    faces = np.vstack([front, back, cube_triangles[:, [0, 2, 1]] + 8])
    document, body = build([(positions, vertex_normals, faces)])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'corrected' and record['opposing_triangles'] == 14
    assert record['paired_back_faces'] == 2 and record['flipped_triangles'] == 12
    new = S.GR.accessor(fixed, fixed_body, fixed['meshes'][0]['primitives'][0]['indices']).reshape(-1, 3).astype(int)
    np.testing.assert_array_equal(new[:4], faces[:4])
    np.testing.assert_array_equal(new[4:], cube_triangles + 8)
    assert W.winding_report(fixed, fixed_body)[0]['flipped_triangles'] == 0

    # A primitive that is nothing but such cards is reported two-sided and keeps its accessors.
    document, body = build([(np.vstack([corners, corners]), np.vstack([normals, normals]), np.vstack([front, back]))])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    assert report['records'][0]['status'] == 'two_sided' and report['left_alone']['two_sided'] == 1
    assert report['left_alone_opposing']['two_sided'] == 1 and fixed == document and fixed_body == body
    # Authored with the back's own normals the pair is simply consistent.
    document, body = build([(np.vstack([corners, corners]), np.vstack([normals, -normals]), np.vstack([front, back]))])
    assert W.normalise_winding(document, body)[2]['records'][0]['status'] == 'consistent'
    # Without its front, the same back copy is just a backwards triangle.
    document, body = build([(corners, normals, front[:, [0, 2, 1]])])
    assert W.normalise_winding(document, body)[2]['flipped_triangles'] == 2


def test_the_input_document_and_body_are_never_modified():
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])])
    body = bytearray(body)
    snapshot, raw = json.loads(json.dumps(document)), bytes(body)
    fixed, fixed_body, _ = W.normalise_winding(document, body)
    assert document == snapshot and bytes(body) == raw
    fixed['nodes'][0]['name'] = 'Renamed'
    fixed['meshes'][0]['primitives'][0]['attributes']['POSITION'] = 99
    fixed['accessors'][0]['count'] = 0
    fixed['buffers'][0]['byteLength'] = 1
    assert document == snapshot, 'the corrected document shares nothing with its source'
    assert isinstance(fixed_body, bytes) and fixed_body[:len(raw)] == raw


def test_a_primitive_without_normals_is_left_alone_and_reported():
    corners, _, triangles = cube()
    document, body = build([(corners, None, triangles[:, [0, 2, 1]])])
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'no_normals' and not record['has_normals']
    assert record['flipped_triangles'] == 0 and record['disagreeing_area_share'] is None
    assert record['signed_volume'] == pytest.approx(-8.)
    assert report['left_alone']['no_normals'] == 1 and report['flipped_triangles'] == 0
    assert fixed == document and fixed_body == body


def test_double_sided_and_non_triangle_primitives_are_left_alone_and_reported():
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])], double_sided=True)
    fixed, fixed_body, report = W.normalise_winding(document, body)
    record = report['records'][0]
    assert record['status'] == 'double_sided' and record['double_sided']
    assert record['flipped_triangles'] == 0 and record['opposing_triangles'] == 12
    assert report['left_alone_opposing']['double_sided'] == 1 and fixed == document and fixed_body == body

    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])])
    document['meshes'][0]['primitives'][0]['mode'] = 1
    fixed, fixed_body, report = W.normalise_winding(document, body)
    assert report['records'][0]['status'] == 'not_triangles' and report['left_alone']['not_triangles'] == 1
    assert fixed == document and fixed_body == body


def test_an_accessor_without_data_is_reported_unreadable():
    """The content loader's fixtures carry positions as a bare box, with no buffer data."""
    document = {'nodes': [{'name': 'Landmark_Hall', 'mesh': 0}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1}}]}],
                'accessors': [{'min': [-3., 0., -1.], 'max': [3., 4., 1.]}, {'count': 8, 'type': 'VEC3', 'componentType': 5126}]}
    fixed, fixed_body, report = W.normalise_winding(document, b'')
    assert report['records'][0]['status'] == 'unreadable' and fixed == document and fixed_body == b''


def test_geometry_shared_by_several_meshes_and_nodes_is_corrected_once():
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])])
    document['meshes'].append(json.loads(json.dumps(document['meshes'][0])) | {'name': 'Part_0_twin'})
    document['nodes'] += [{'name': 'Part_0_again', 'mesh': 0, 'translation': [5., 0., 0.]},
                          {'name': 'Part_0_twin', 'mesh': 1, 'scale': [2., 1., 1.]}]
    fixed, fixed_body, report = W.normalise_winding(document, body)
    first, second = (fixed['meshes'][m]['primitives'][0]['indices'] for m in (0, 1))
    assert first == second == len(document['accessors'])
    assert len(fixed['accessors']) == len(document['accessors']) + 1
    assert len(fixed['bufferViews']) == len(document['bufferViews']) + 1
    assert report['corrected_primitives'] == 2 and report['corrected_geometries'] == 1
    assert report['flipped_triangles'] == 12 and report['triangles'] == 12
    assert report['records'][1]['shared_geometry'] == [0, 0]
    # Placed instances: the plain cube twice (24 m2 each) and the twin stretched to 4x2x2 m (40 m2).
    records = W.winding_report(document, body, nodes=[0, 1, 2])
    assert [r['instances'] for r in records] == [2, 1]
    assert records[0]['world_flipped_area'] == pytest.approx(48.) and records[1]['world_flipped_area'] == pytest.approx(40.)
    assert records[0]['node_names'] == ['Part_0', 'Part_0_again']


def test_a_corrected_document_exports_through_the_scene_exporter(tmp_path):
    corners, normals, triangles = cube()
    document, body = build([(corners, normals, triangles[:, [0, 2, 1]])], lead=b'\x07')
    document['nodes'][0]['translation'] = [10., 2., -4.]
    fixed, fixed_body, _ = W.normalise_winding(document, body)
    corrected = tmp_path / 'corrected.glb'
    S.dump_glb(corrected, fixed, fixed_body)
    assert validate_gltf.validate(str(corrected)).counts()['numErrors'] == 0
    exporter = S.Exporter(tmp_path / 'out' / 'world.glb')
    exporter.add(fixed, fixed_body, [0], transforms={0: [1., 0., 0.]}, prefix='westhaven_')
    exporter.write()
    assert validate_gltf.validate(str(tmp_path / 'out' / 'world.glb')).counts()['numErrors'] == 0
    exported_document, exported_body = S.GR.load(tmp_path / 'out' / 'world.glb')
    meshes = [i for i, node in enumerate(exported_document['nodes']) if 'mesh' in node]
    exported = S.GR.triangles(exported_document, exported_body, meshes)
    np.testing.assert_allclose(exported, S.GR.triangles(fixed, fixed_body, [0]) + [1., 0., 0.])
    assert volume(exported - [11., 2., -4.]) == pytest.approx(8.)
    primitive = exported_document['meshes'][0]['primitives'][0]
    assert exported_document['accessors'][primitive['indices']]['componentType'] == 5123
    assert W.winding_report(exported_document, exported_body)[0]['status'] == 'consistent'


def sheet_document():
    """(document, body): open cards named like library meshes, over four materials."""
    corners, normals, front = card()
    names = ['Kit_tent__solid__canvas', 'Plaza_Arcade_0__solid__stone', 'Plaza_Arcade_1__solid__stone',
             'Plaza_Monument__solid__stone', 'Plaza_Arcade_2__solid__gilt', 'Timber_Shed']
    document, body = build([(corners, normals, front)] * len(names))
    document['materials'] = [{'name': 'canvas', 'pbrMetallicRoughness': {'baseColorFactor': [.9, .8, .6, 1.]}},
                             {'name': 'stone', 'pbrMetallicRoughness': {'baseColorFactor': [.5, .5, .5, 1.]}, 'doubleSided': False},
                             {'name': 'gilt'}, {'name': 'timber'}]
    for mesh, name, material in zip(document['meshes'], names, (0, 1, 1, 1, 2, 3)):
        mesh['name'] = name
        mesh['primitives'][0]['material'] = material
    return document, body


def test_listed_sheet_materials_and_mesh_families_render_from_both_sides_and_nothing_else_does():
    document, body = sheet_document()
    snapshot = json.loads(json.dumps(document))
    table = {'materials': ('canvas', 'sailcloth'),
             'meshes': (('Plaza_Arcade_*__solid__stone', 'stone'), ('plaza_monument__solid__stone', 'stone'))}
    fixed, report = W.double_sided_sheets(document, table)
    assert document == snapshot, 'the input document is never modified'
    materials = fixed['materials']
    # A listed material turns where it is defined; the others keep their flags.
    assert materials[0]['doubleSided'] is True and materials[0]['name'] == 'canvas'
    assert materials[1].get('doubleSided') is False and 'doubleSided' not in materials[2] and 'doubleSided' not in materials[3]
    # A material shared with other meshes turns only through a doubleSided copy used by the listed family.
    assert len(materials) == 5
    assert materials[4] == dict(snapshot['materials'][1], doubleSided=True)
    material_of = {mesh['name']: mesh['primitives'][0]['material'] for mesh in fixed['meshes']}
    assert material_of == {'Kit_tent__solid__canvas': 0, 'Plaza_Arcade_0__solid__stone': 4, 'Plaza_Arcade_1__solid__stone': 4,
                           'Plaza_Monument__solid__stone': 1, 'Plaza_Arcade_2__solid__gilt': 2, 'Timber_Shed': 3}
    assert report['materials'] == ['canvas'] and report['copies'] == {1: 4}
    assert report['primitives'] == [['Plaza_Arcade_0__solid__stone', 0, 'stone'], ['Plaza_Arcade_1__solid__stone', 0, 'stone']]
    # Names are matched exactly: a missing material and a pattern in the wrong case name nothing, and say so.
    assert report['unmatched'] == ['sailcloth', ['plaza_monument__solid__stone', 'stone']]
    # Geometry, accessors and the body are shared untouched; an untouched mesh is the same object.
    assert fixed['accessors'] == document['accessors'] and fixed['meshes'][3] is document['meshes'][3]
    # No entry: the document itself.
    assert W.double_sided_sheets(document, None) == (document, {'materials': [], 'primitives': [], 'copies': {}, 'unmatched': []})
    with pytest.raises(ValueError, match='unknown key'):
        W.double_sided_sheets(document, {'material': ('canvas',)})


def test_double_sided_sheets_export_through_the_scene_exporter(tmp_path):
    document, body = sheet_document()
    fixed, _ = W.double_sided_sheets(document, {'meshes': (('Plaza_Arcade_*', 'stone'),)})
    exporter = S.Exporter(tmp_path / 'world.glb')
    exporter.add(fixed, body, [1, 3], prefix='four_gates_')
    exporter.write()
    assert validate_gltf.validate(str(tmp_path / 'world.glb')).counts()['numErrors'] == 0
    exported, _ = S.GR.load(tmp_path / 'world.glb')
    flags = {exported['meshes'][node['mesh']]['name']: exported['materials'][exported['meshes'][node['mesh']]['primitives'][0]['material']]
             for node in exported['nodes'] if 'mesh' in node}
    assert flags['Plaza_Arcade_0__solid__stone'] == {'name': 'stone', 'pbrMetallicRoughness': {'baseColorFactor': [.5, .5, .5, 1.]},
                                                     'doubleSided': True}
    assert flags['Plaza_Monument__solid__stone'].get('doubleSided') is False


def test_the_double_sided_table_names_open_sheets_by_territory_and_leaves_bark_and_backed_models_alone():
    for region, entry in W.DOUBLE_SIDED_SHEETS.items():
        assert set(entry) <= set(W.SHEET_TABLE_KEYS), region
        assert all(isinstance(name, str) for name in entry.get('materials', ())), region
        assert all(len(pair) == 2 and all(isinstance(part, str) for part in pair) for pair in entry.get('meshes', ())), region
        named = [*entry.get('materials', ()), *(part for pair in entry.get('meshes', ()) for part in pair)]
        assert not any('bark' in name or 'cave_mouth' in name or 'Retaining' in name or 'CenoteStair' in name for name in named), region
    assert W.DOUBLE_SIDED_SHEETS['sunmane_steppe']['materials'] == ('sun_canvas_pale', 'sun_canvas_ochre', 'sun_canvas_red')
    assert ('Plaza_Arcade_*__solid__fg_stone_ashlar', 'fg_stone_ashlar') in W.DOUBLE_SIDED_SHEETS['four_gates']['meshes']
