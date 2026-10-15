"""continent-edits.json: removal, rotation/scale, moves, copies and vegetation areas."""
from pathlib import Path
import copy
import json
import math
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import object_edits as OE
import scene_io as S

REGIONS = ['grey_moors', 'manymouth_delta', 'manymouth', 'four_gates']


def document():
    """A group holding one building (two child meshes) and one lamp."""
    return {
        'nodes': [
            {'name': 'Group_Structures', 'children': [1, 4]},
            {'name': 'House_00', 'translation': [10., 0., 5.], 'children': [2, 3]},
            {'name': 'House_00__walls', 'mesh': 0},
            {'name': 'Walk_House_00__floor', 'mesh': 0, 'translation': [0., 0., 1.]},
            {'name': 'Prop_lamp_00', 'mesh': 0, 'translation': [-4., 0., 0.]},
        ],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
        'accessors': [{'min': [-1., 0., -2.], 'max': [1., 3., 2.]}],
    }


def test_edit_matrix_is_the_editors_matrix():
    pivot, translate, yaw, scale = [10., 0., 5.], [3., 1., -2.], 90., 2.
    m = OE.edit_matrix(pivot, yaw, scale, translate)
    # editor.html editMatrix: x' = c x + n z, z' = -n x + c z about the pivot, then translate
    c, n = math.cos(math.radians(yaw)) * scale, math.sin(math.radians(yaw)) * scale
    for p in ([10., 0., 5.], [11., 2., 5.], [10., 0., 7.]):
        d = np.subtract(p, pivot)
        expected = [pivot[0] + translate[0] + c * d[0] + n * d[2], pivot[1] + translate[1] + scale * d[1],
                    pivot[2] + translate[2] - n * d[0] + c * d[2]]
        assert np.allclose((m @ np.r_[p, 1.])[:3], expected)
    assert np.allclose((m @ np.r_[pivot, 1.])[:3], np.add(pivot, translate)), 'the base centre only translates'


def test_thin_hash_is_uniform_and_metre_rounded():
    assert OE.thin_hash(10.4, -3.6) == OE.thin_hash(9.6, -4.4)
    values = [OE.thin_hash(x, z) for x in range(0, 300, 3) for z in range(0, 300, 3)]
    assert 0 <= min(values) and max(values) < 1
    assert abs(np.mean(values) - .5) < .02 and abs(np.mean(np.array(values) < .3) - .3) < .02
    # Values the editor's JavaScript thinHash returns for the same points.
    assert OE.thin_hash(0, 0) == 0.0
    assert [round(OE.thin_hash(x, z), 12) for x, z in ((1, 0), (0, 1), (431.6, 1022.2), (-7, 12))] == JS_HASHES


# thinHash in the editor's JavaScript, evaluated in the browser for the same points.
JS_HASHES = [0.708827039925, 0.205480768578, 0.995353186037, 0.14851745707]


def test_parse_root_takes_the_longest_territory_prefix():
    assert OE.parse_root('manymouth_delta_Landmark_MootHall_WorldPlacement', REGIONS) == ('manymouth_delta', 'Landmark_MootHall')
    assert OE.parse_root('grey_moors_Prop_cairn_03_WorldPlacement', REGIONS) == ('grey_moors', 'Prop_cairn_03')
    with pytest.raises(ValueError, match='generated'):
        OE.parse_root('grey_moors_Walk_ContinentalBridgeUnion_001_grey_moors_WorldPlacement_WorldPlacement', REGIONS)
    with pytest.raises(ValueError, match='territory prefix'):
        OE.parse_root('Terrain_grey_moors_02_00', ['four_gates'])


def edits(*objects, areas=()):
    return OE.ObjectEdits({'version': 1, 'objects': list(objects), 'vegetationAreas': list(areas)}, REGIONS)


def test_removal_filters_the_placement_and_missing_names_are_reported():
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'remove'},
              {'root': 'grey_moors_Gone_01_WorldPlacement', 'action': 'remove'})
    placements = [{'node': 'House_00'}, {'node': 'Prop_lamp_00'}]
    assert [p['node'] for p in e.filter_placements('grey_moors', placements)] == ['Prop_lamp_00']
    assert e.filter_placements('four_gates', placements) == placements
    with pytest.raises(ValueError, match='Gone_01'):
        e.check_loaded(type('C', (), {'placement_by_name': {}})())


def test_rotation_and_scale_turn_the_root_about_its_base_centre_in_a_private_document():
    doc = document()
    original = copy.deepcopy(doc)
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'transform', 'pivot': [0, 0, 0],
               'translate': [0, 0, 0], 'yawDegrees': 90, 'scale': 2})
    placements = [{'node': 'House_00', 'kind': 'structure', 'position': [10., 0., 6.]}, {'node': 'Prop_lamp_00', 'kind': 'prop'}]
    low, high = S.subtree_bounds(doc, b'', 1)
    edited = e.prepare_document('grey_moors', doc, b'', placements)
    assert doc == original, 'the loaded library document is not mutated'
    new_low, new_high = S.subtree_bounds(edited, b'', 1)
    pivot = OE.base_pivot(low, high)
    assert np.allclose(OE.base_pivot(new_low, new_high), pivot)
    # 2 m wide (x) by 5 m deep (z) becomes 10 m wide by 4 m deep, twice as tall.
    assert np.allclose(new_high - new_low, [(high - low)[2] * 2, (high - low)[1] * 2, (high - low)[0] * 2])
    assert np.allclose(S.subtree_bounds(edited, b'', 4)[0], S.subtree_bounds(doc, b'', 4)[0]), 'other roots are untouched'
    assert np.allclose(placements[0]['position'], OE.edit_matrix(pivot, 90, 2)[:3, :3] @ (np.array([10., 0., 6.]) - pivot) + pivot)


def test_trees_can_move_but_not_turn():
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'transform', 'pivot': [0, 0, 0],
               'translate': [0, 0, 0], 'yawDegrees': 15, 'scale': 1})
    with pytest.raises(ValueError, match='not rotate'):
        e.prepare_document('grey_moors', document(), b'', [{'node': 'House_00', 'kind': 'tree'}])


class World:
    ids = REGIONS

    def owner_at(self, x, z):
        return np.where(np.asarray(x) < 100, 0, 3)

    def height_at(self, x, z):
        return np.asarray(x, float) * .1

    def __init__(self):
        self.footings = []

    def foundation(self, xz, footprint, target, feather, obstacle):
        self.footings.append((list(map(float, xz)), footprint, target, obstacle))


def test_moves_are_grounded_again_keep_their_raise_and_respect_assemblies_and_territories():
    world = World()
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'transform', 'pivot': [0, 0, 0],
               'translate': [20., 1.5, -4.], 'yawDegrees': 0, 'scale': 1})
    edit = e.translation('grey_moors', 'House_00')
    new_xz, shift, target = e.apply_translation(world, 'grey_moors', edit, None, np.array([10., 5.]), np.array([30., 40.]), 2.)
    assert np.allclose(new_xz, [50., 36.]) and target == pytest.approx(5.)
    assert np.allclose(shift, [40., 5. - 2. + 1.5, 31.])
    with pytest.raises(ValueError, match='assembly'):
        e.apply_translation(world, 'grey_moors', edit, 'grey_moors.village', np.array([10., 5.]), np.array([30., 40.]), 2.)
    with pytest.raises(ValueError, match='outside'):
        e.apply_translation(world, 'grey_moors', edit, None, np.array([10., 5.]), np.array([90., 40.]), 2.)
    assert e.translation('grey_moors', 'Prop_lamp_00') is None


def content_for(documents, placements, companions=None):
    content = type('Content', (), {})()
    content.documents = documents
    content.metadata = {region: {'placements': list(items)} for region, items in placements.items()}
    content.companions = companions or {}
    content.objects = []
    return content


def test_a_copy_is_a_cloned_subtree_in_its_own_territory_with_footing_and_collision_identity():
    doc = document()
    world = World()
    content = content_for({'grey_moors': (doc, b'')}, {'grey_moors': [{'node': 'House_00', 'kind': 'structure', 'collides': True}]})
    e = edits({'id': 'copy-1', 'action': 'add', 'source': 'grey_moors_House_00_WorldPlacement',
               'pivot': [10., 0., 5.], 'translate': [30., .5, 10.], 'yawDegrees': 90, 'scale': 1})
    e.add_copies(world, content)
    edited, _ = content.documents['grey_moors']
    assert len(doc['nodes']) == 5 and len(edited['nodes']) == 8, 'the clone is appended; the source document is intact'
    obj = content.objects[0]
    assert obj['node'] == 'EditCopy_copy1_House_00' and obj['nodePrefix'] == 'EditCopy_copy1_' and obj['collides']
    assert obj['region'] == 'grey_moors' and obj['indices'] == [obj['index']]
    assert {edited['nodes'][i]['name'] for i in S.descendants(edited, [obj['index']])} == {'House_00', 'House_00__walls', 'Walk_House_00__floor'}
    assert S.GR.hierarchy(edited)[1].get(2) == 1, 'original children keep their parent'
    centre = (obj['low'] + obj['high']) * .5
    assert np.allclose(centre[[0, 2]], [40., 15.]) and obj['low'][1] == pytest.approx(4. + .5)
    assert world.footings and world.footings[0][3] is True
    assert e.report['added'][0]['territory'] == 'grey_moors'


def buffered_document(name, colour_image=b'PNGDATA!'):
    """A one-triangle asset with a real buffer, a textured material and an embedded image."""
    positions = np.array([[0, 0, 0], [2, 0, 0], [0, 3, 1]], np.float32).tobytes()
    indices = np.array([0, 1, 2], np.uint32).tobytes()
    body = positions + indices + colour_image
    return {
        'nodes': [{'name': 'Group', 'children': [1]}, {'name': name, 'translation': [5., 0., 5.], 'children': [2]},
                  {'name': name + '__mesh', 'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1, 'material': 0}]}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3', 'min': [0, 0, 0], 'max': [2, 3, 1]},
                      {'bufferView': 1, 'componentType': 5125, 'count': 3, 'type': 'SCALAR'}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36}, {'buffer': 0, 'byteOffset': 36, 'byteLength': 12},
                        {'buffer': 0, 'byteOffset': 48, 'byteLength': len(colour_image)}],
        'materials': [{'name': 'stone', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}],
        'textures': [{'source': 0, 'sampler': 0}], 'images': [{'bufferView': 2, 'mimeType': 'image/png'}],
        'samplers': [{}], 'buffers': [{'byteLength': len(body)}]}, body


def test_a_copy_placed_in_another_territory_is_transplanted_with_its_resources():
    source, source_body = buffered_document('Shrine_00')
    target, target_body = buffered_document('Well_00', colour_image=b'OTHERIMAGE')
    world = World()
    content = content_for({'grey_moors': (source, source_body), 'four_gates': (target, target_body)},
                          {'grey_moors': [{'node': 'Shrine_00', 'kind': 'prop', 'collides': True}], 'four_gates': []})
    e = edits({'id': 'far', 'action': 'add', 'source': 'grey_moors_Shrine_00_WorldPlacement',
               'pivot': [300., 0., 20.], 'translate': [0., 0., 0.], 'yawDegrees': 0, 'scale': 1},
              {'id': 'far-2', 'action': 'add', 'source': 'grey_moors_Shrine_00_WorldPlacement',
               'pivot': [320., 0., 20.], 'translate': [0., 0., 0.], 'yawDegrees': 0, 'scale': 1})
    e.add_copies(world, content)
    doc, body = content.documents['four_gates']
    first, second = content.objects
    assert first['region'] == second['region'] == 'four_gates'
    assert content.documents['grey_moors'][0] is source, 'the library territory is untouched'
    assert len(doc['meshes']) == 2 and len(doc['materials']) == 2 and len(doc['images']) == 2, 'resources travel once for both copies'
    assert doc['buffers'][0]['byteLength'] == len(body) and len(body) % 4 in (0, 1, 2, 3)
    mesh_node = next(i for i in S.descendants(doc, [first['index']]) if 'mesh' in doc['nodes'][i])
    primitive = doc['meshes'][doc['nodes'][mesh_node]['mesh']]['primitives'][0]
    assert np.allclose(S.GR.accessor(doc, body, primitive['attributes']['POSITION']), [[0, 0, 0], [2, 0, 0], [0, 3, 1]])
    assert S.GR.accessor(doc, body, primitive['indices']).ravel().tolist() == [0, 1, 2]
    image = doc['images'][doc['textures'][doc['materials'][primitive['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']]
    view = doc['bufferViews'][image['bufferView']]
    assert body[view['byteOffset']:view['byteOffset'] + view['byteLength']] == b'PNGDATA!'
    assert np.allclose(S.subtree_bounds(target, target_body, 1)[0], S.subtree_bounds(doc, body, 1)[0]), 'existing roots are intact'
    assert np.allclose(((first['low'] + first['high']) * .5)[[0, 2]], [300., 20.]) and first['low'][1] == pytest.approx(30.)
    assert e.report['added'][0]['territory'] == 'four_gates'


def test_trees_travel_with_their_foliage_and_get_no_footing_while_boats_and_foliage_are_refused():
    doc = document()
    doc['nodes'].append({'name': 'Tree_00__leaves', 'mesh': 0, 'translation': [10., 3., 5.]})
    world = World()
    placements = {'grey_moors': [{'node': 'House_00', 'kind': 'tree'}, {'node': 'Prop_lamp_00', 'kind': 'foliage'},
                                 {'node': 'Prop_skiff_00', 'kind': 'prop'}]}
    doc['nodes'].append({'name': 'Prop_skiff_00', 'mesh': 0})
    content = content_for({'grey_moors': (doc, b'')}, placements, companions={('grey_moors', 1): [5]})
    edits({'id': 'grove', 'action': 'add', 'source': 'grey_moors_House_00_WorldPlacement',
           'pivot': [40., 0., 40.], 'translate': [0., 0., 0.], 'yawDegrees': 0, 'scale': 1}).add_copies(world, content)
    obj = content.objects[0]
    assert len(obj['indices']) == 2 and obj['kind'] == 'tree' and not obj['collides'] and not world.footings
    edited, _ = content.documents['grey_moors']
    assert edited['nodes'][obj['indices'][1]]['name'] == 'Tree_00__leaves'
    for source, reason in (('grey_moors_Prop_lamp_00_WorldPlacement', 'foliage'), ('grey_moors_Prop_skiff_00_WorldPlacement', 'boats')):
        with pytest.raises(ValueError, match=reason):
            edits({'id': 'x', 'action': 'add', 'source': source, 'pivot': [40., 0., 40.],
                   'translate': [0., 0., 0.]}).add_copies(world, content_for({'grey_moors': (doc, b'')}, placements))


def test_a_removed_placement_can_still_be_copied_elsewhere():
    doc = document()
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'remove'},
              {'id': 'moved', 'action': 'add', 'source': 'grey_moors_House_00_WorldPlacement',
               'pivot': [60., 0., 60.], 'translate': [0., 0., 0.]})
    kept = e.filter_placements('grey_moors', [{'node': 'House_00', 'kind': 'structure'}, {'node': 'Prop_lamp_00', 'kind': 'prop'}])
    content = content_for({'grey_moors': (doc, b'')}, {'grey_moors': kept})
    e.add_copies(World(), content)
    assert content.objects[0]['node'] == 'EditCopy_moved_House_00'


def test_vegetation_areas_clear_and_thin_only_their_kinds_inside():
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    e = edits(areas=[{'id': 'a', 'mode': 'clear', 'kinds': ['tree'], 'polygon': square},
                     {'id': 'b', 'mode': 'thin', 'keep': .25, 'kinds': ['undergrowth', 'rock'], 'polygon': square}])
    assert e.skips_scatter('tree', 50, 50) and not e.skips_scatter('tree', 150, 50)
    kept = [not e.skips_scatter('undergrowth', x, z) for x in range(1, 100, 4) for z in range(1, 100, 4)]
    assert .15 < np.mean(kept) < .35
    assert kept == [OE.thin_hash(x, z) < .25 for x in range(1, 100, 4) for z in range(1, 100, 4)]
    assert e.report['scatterSkipped']['tree'] == 1


def test_catalogue_flags_modules_that_look_nodes_up_by_name(tmp_path):
    library = tmp_path / 'library' / 'grey_moors'
    library.mkdir(parents=True)
    (library / 'library.json').write_text(json.dumps({'placements': [
        {'node': 'Landmark_boardwalk_north', 'kind': 'structure'}, {'node': 'Prop_cairn_00', 'kind': 'prop'},
        {'node': 'Tree_00', 'kind': 'tree'}]}))
    found = OE.catalogue(tmp_path / 'library', regions=['grey_moors'])['grey_moors']
    assert found['Prop_cairn_00']['referencedBy'] == [] and found['Tree_00']['companions']
    assert OE.problems({'objects': [{'id': 'copy-1', 'action': 'add', 'source': 'grey_moors_Tree_00_WorldPlacement'}]},
                       {'grey_moors': found}) == [], 'trees are placeable assets'
    assert OE.problems({'objects': [{'id': 'copy-2', 'action': 'add', 'source': 'grey_moors_Missing_WorldPlacement'}]},
                       {'grey_moors': found})


def test_a_copy_ignores_its_sources_own_rotation():
    doc = document()
    placements = [{'node': 'House_00', 'kind': 'structure'}]
    e = edits({'root': 'grey_moors_House_00_WorldPlacement', 'action': 'transform', 'pivot': [0, 0, 0],
               'translate': [0, 0, 0], 'yawDegrees': 90, 'scale': 1},
              {'id': 'copy-1', 'action': 'add', 'source': 'grey_moors_House_00_WorldPlacement',
               'pivot': [10., 0., 5.], 'translate': [30., 0., 10.], 'yawDegrees': 0, 'scale': 1})
    turned = e.prepare_document('grey_moors', doc, b'', placements)
    content = content_for({'grey_moors': (turned, b'')}, {'grey_moors': placements})
    e.add_copies(World(), content)
    low, high = content.objects[0]['low'], content.objects[0]['high']
    original_low, original_high = S.subtree_bounds(doc, b'', 1)
    assert np.allclose((high - low)[[0, 2]], (original_high - original_low)[[0, 2]]), 'the copy keeps the authored orientation'


def test_a_tilted_copy_stands_on_its_real_lowest_vertex_and_finds_its_foliage_by_position():
    doc, body = buffered_document('Serac_00')
    # Tilt the mesh node 60 degrees about x: the transformed accessor box reaches far below the real vertices.
    angle = np.radians(60.)
    doc['nodes'][2]['rotation'] = [float(np.sin(angle / 2)), 0., 0., float(np.cos(angle / 2))]
    doc['nodes'].append({'name': 'Serac_00__leaves', 'mesh': 0, 'translation': [5., 4., 5.]})
    placements = {'grey_moors': [{'node': 'Serac_00', 'kind': 'tree', 'position': [5., 0., 5.]},
                                 {'node': 'Serac_00__leaves', 'kind': 'foliage', 'position': [5., 0., 5.]}]}
    content = content_for({'grey_moors': (doc, body)}, placements)
    world = World()
    edits({'id': 'tilt', 'action': 'add', 'source': 'grey_moors_Serac_00_WorldPlacement',
           'pivot': [40., 0., 40.], 'translate': [0., 0., 0.]}).add_copies(world, content)
    obj = content.objects[0]
    assert len(obj['indices']) == 2, 'foliage found by position although load recorded no companions'
    edited, edited_body = content.documents['grey_moors']
    matrices = S.GR.hierarchy(edited)[0]
    lowest = min(float((S.GR.accessor(edited, edited_body, 0).astype(float) @ matrices[i][:3, :3].T + matrices[i][:3, 3])[:, 1].min())
                 for i in S.descendants(edited, obj['indices']) if 'mesh' in edited['nodes'][i])
    assert lowest + obj['shift'][1] == pytest.approx(4.0), 'the real lowest vertex stands on the ground (height 4 at x=40)'
