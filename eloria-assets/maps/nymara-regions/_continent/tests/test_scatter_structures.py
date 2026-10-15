"""Ecological scatter never grows inside a building.

Content.scatter_structures rasterises the real footprint of every retained building (its own triangles,
not a circle or a box) onto the composed grid, and ecological_scatter refuses a tree, an outcrop piece or an
undergrowth pocket standing there only after its counter has advanced, so every other Grove_, Outcrop_ and
WoodlandFloor_ name stays where it was.
"""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import content as C
import landscape as L
import object_edits as OE
import world_layout as W

REGION = 'whitehorn_range'


def slab(a, b, width, bottom, top):
    """A closed box standing along the segment a -> b in x/z: its walls, floor and roof as triangles."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]]) * width * .5
    footprint = [a + n, b + n, b - n, a - n]
    low = [np.array([p[0], bottom, p[1]]) for p in footprint]
    high = [np.array([p[0], top, p[1]]) for p in footprint]
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces += [[low[i], low[j], high[j]], [low[i], high[j], high[i]]]
    faces += [[low[0], low[1], low[2]], [low[0], low[2], low[3]], [high[0], high[1], high[2]], [high[0], high[2], high[3]]]
    return np.array(faces)


def inside_strip(px, pz, a, b, half):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    t = np.clip(((px - a[0]) * d[0] + (pz - a[1]) * d[1]) / d.dot(d), 0, 1)
    return np.hypot(px - a[0] - t * d[0], pz - a[1] - t * d[1]) <= half


def test_a_long_diagonal_building_masks_its_own_footprint_and_not_its_bounding_box():
    x = np.arange(0., 200.1, 2.); z = np.arange(0., 200.1, 2.)
    ground = np.zeros((len(z), len(x)))
    a, b = (30., 30.), (170., 170.)
    mask = C.structure_cells(slab(a, b, 4., 0., 9.), ground, 0., 0., 2.)
    cx, cz = np.meshgrid(x[:-1] + 1., z[:-1] + 1.)
    marked = mask[:-1, :-1]
    # Every cell whose centre stands inside the gatehouse is marked...
    assert marked[inside_strip(cx, cz, a, b, 2.)].all()
    # ...and none further than the wall's half width, the trunk's reach and a cell's half diagonal from it.
    assert not marked[~inside_strip(cx, cz, a, b, 2. + C.STRUCTURE_REACH_METRES + np.sqrt(2.))].any()
    box = (cx >= 28.) & (cx <= 172.) & (cz >= 28.) & (cz <= 172.)
    assert marked.sum() < .15 * box.sum(), 'a diagonal building closes its strip, not its bounding box'
    assert not mask[-1].any() and not mask[:, -1].any()


def test_only_faces_that_rise_above_the_ground_under_them_mark_it():
    x = np.arange(0., 60.1, 2.); z = np.arange(0., 60.1, 2.)
    gx, gz = np.meshgrid(x, z)
    ground = .5 * gx                                                        # a slope rising east
    paving = slab((4., 30.), (56., 30.), 6., 0., 0.)                        # a flat floor at height 0
    mask = C.structure_cells(paving, ground, 0., 0., 2.)
    columns = np.flatnonzero(mask.any(axis=0))
    # At height 0 the floor stands more than a metre above the ground only where that ground is below -1:
    # nowhere here, so nothing is marked; raised 10 m it stands over the ground west of x = 18.
    assert not len(columns)
    raised = C.structure_cells(paving + [0., 10., 0.], ground, 0., 0., 2.)
    columns = np.flatnonzero(raised.any(axis=0))
    assert columns.min() >= 1 and x[columns.max()] < 18.
    # The ground anywhere in a cell is at least its lowest corner, so a cell is marked by its lowest corner.
    assert raised[15, 8] and not raised[15, 12]


def test_structure_cells_accumulate_into_a_given_mask_and_ignore_an_empty_or_distant_building():
    ground = np.zeros((11, 11))
    mask = np.zeros(ground.shape, bool)
    C.structure_cells(slab((2., 2.), (6., 2.), 2., 0., 5.), ground, 0., 0., 2., mask=mask)
    first = mask.copy()
    C.structure_cells(slab((2., 14.), (6., 14.), 2., 0., 5.), ground, 0., 0., 2., mask=mask)
    assert first.any() and (mask & first == first).all() and mask.sum() > first.sum()
    assert not C.structure_cells(np.zeros((0, 3, 3)), ground, 0., 0., 2.).any()
    assert not C.structure_cells(slab((500., 500.), (520., 500.), 2., 0., 5.), ground, 0., 0., 2.).any()


def test_the_exported_root_name_decides_what_counts_as_a_building():
    for node in ('Gate_North', 'Plaza_Arcade_0', 'Landmark_GrandStair', 'Northern_Sanctuary', 'EditCopy_x_Landmark_Temple'):
        assert C.scatter_blocking_root('four_gates', node)
    for node in ('Prop_Barrel_001', 'Walk_Landmark_glacier_temple__veined_marble', 'EditCopy_x_Prop_lamp', 'Grove_00001_Tree',
                 'Crystal_MassifSpire_03', 'Landmark_LevitatingShards_12', 'EditCopy_moved_Crystal_MassifSpire_01'):
        assert not C.scatter_blocking_root('amethyst_barrens', node)
    assert C.SCATTER_THROUGH_PREFIXES == ('Crystal_MassifSpire_', 'Landmark_LevitatingShards_')


# ---------------------------------------------------------------------------------------------- scatter
def triangle_document(triangles):
    """A glTF document holding one mesh of real triangles."""
    data = np.asarray(triangles, np.float32).reshape(-1, 3)
    body = data.tobytes()
    return {'nodes': [{'name': 'Tree_proto', 'mesh': 0}, {'name': 'Rock_proto', 'mesh': 0},
                      {'name': 'Fern_proto', 'mesh': 0}, {'name': 'Gate_North', 'mesh': 1},
                      {'name': 'Crystal_MassifSpire_01', 'mesh': 1}, {'name': 'Prop_Wall_01', 'mesh': 1}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 1}}]}, {'primitives': [{'attributes': {'POSITION': 0}}]}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': len(data), 'type': 'VEC3',
                           'min': data.min(axis=0).tolist(), 'max': data.max(axis=0).tolist()},
                          {'min': [-.5, 0., -.5], 'max': [.5, 6., .5]}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(body)}]}, body


class World:
    """A 240 m square territory on a plane rising 0.3 east (steep enough for outcrops), no roads, no water."""

    def __init__(self):
        self.ids = [REGION]
        self.plan = {'seed': 11}
        self.x0 = self.z0 = 0.; self.x1 = self.z1 = 240.
        self.x = np.arange(0., 240.1, 2.); self.z = np.arange(0., 240.1, 2.)
        gx, gz = np.meshgrid(self.x, self.z)
        self.height = 5. + .3 * gx
        self.obstacles = np.zeros(self.height.shape, bool)
        self.road_distance = np.full(self.height.shape, np.inf)

    def height_at(self, x, z):
        return W.triangle_sample(self.height, x, z, self.x0, self.z0)

    def owner_at(self, x, z):
        return np.zeros(np.shape(x), int)


def scattered(tmp_path, monkeypatch, buildings):
    """Run the real ecological_scatter over ``buildings``: (node index, x/z segment) standing 60 m tall."""
    monkeypatch.setattr(OE, 'load_edits', lambda *a, **k: {'version': 1, 'objects': [], 'vegetationAreas': []})
    monkeypatch.setattr(L, 'vegetation_fields', lambda x, z, height=None, plan=None: {
        'tree_density': np.ones(np.shape(x)), 'conifer': np.ones(np.shape(x)),
        'dryness': np.zeros(np.shape(x)), 'deciduous': np.zeros(np.shape(x))})
    monkeypatch.setattr(L, 'water_fields', lambda x, z, height=None, plan=None: {'mask': np.zeros(np.shape(x), bool)})
    world = World()
    triangles = slab((80., 60.), (160., 180.), 6., 0., 140.)
    document, body = triangle_document(triangles)
    content = C.Content(world, tmp_path, {}, {})
    content.documents[REGION] = (document, body)
    low, high = np.array([-.5, 0., -.5]), np.array([.5, 6., .5])
    content.prototypes[REGION] = [({'node': 'Tree_proto', 'kind': 'tree'}, 0, low, high),
                                  ({'node': 'Rock_proto', 'kind': 'rock'}, 1, low, high),
                                  ({'node': 'Fern_proto', 'kind': 'fern'}, 2, low, high)]
    for index in buildings:
        content.objects.append({'region': REGION, 'index': index, 'indices': [index], 'shift': np.zeros(3),
                                'low': triangles.reshape(-1, 3).min(axis=0), 'high': triangles.reshape(-1, 3).max(axis=0),
                                'kind': 'structure', 'node': document['nodes'][index]['name'], 'names': set(),
                                'collides': False, 'walk': False})
    content.ecological_scatter()
    return {obj['node']: ((obj['low'] + obj['high']) * .5)[[0, 2]] for obj in content.objects if 'libraryRegion' in obj}, content


def test_a_candidate_inside_a_building_is_refused_after_its_counter_advances(tmp_path, monkeypatch):
    open_ground, _ = scattered(tmp_path, monkeypatch, [])
    kept, content = scattered(tmp_path, monkeypatch, [3])
    inside = {name for name, (x, z) in open_ground.items() if inside_strip(x, z, (80., 60.), (160., 180.), 3.)}
    assert inside, 'some candidates stand inside the gatehouse'
    families = {family: [name for name in open_ground if name.startswith(family)] for family in ('Grove_', 'Outcrop_', 'WoodlandFloor_')}
    assert all(families.values()), 'trees, outcrops and undergrowth all grow on this ground'
    # Every candidate inside the building is gone, and everything else keeps its own name and place.
    assert not inside & set(kept)
    assert set(kept) <= set(open_ground)
    for name, point in kept.items():
        np.testing.assert_allclose(point, open_ground[name])
    lost = set(open_ground) - set(kept)
    assert all(inside_strip(*open_ground[name], (80., 60.), (160., 180.), 3. + C.STRUCTURE_REACH_METRES + 2. * np.sqrt(2.)) for name in lost)
    refused = content.scatter_structure_report['refused']
    assert refused['tree'] == sum(name.startswith('Grove_') for name in lost)
    assert refused['rock'] == sum(name.startswith('Outcrop_') for name in lost)
    assert refused['undergrowth'] == sum(name.startswith('WoodlandFloor_') for name in lost)
    assert min(refused.values()) > 0
    # The counter advanced past each refusal: the highest numbers are still there.
    last_tree = max(families['Grove_'])
    assert last_tree in kept or last_tree in inside
    assert content.scatter_structure_report['roots'] == 1 and content.scatter_structure_report['triangles'] == 12


def test_no_buildings_or_only_open_roots_change_nothing(tmp_path, monkeypatch):
    open_ground, content = scattered(tmp_path, monkeypatch, [])
    assert content.scatter_structure_report['cells'] == 0 and not any(content.scatter_structure_report['refused'].values())
    for through in ([4], [5], [4, 5]):                  # a crystal massif spire and a prop wall on the same footprint
        kept, content = scattered(tmp_path, monkeypatch, through)
        assert kept.keys() == open_ground.keys()
        for name, point in kept.items():
            np.testing.assert_array_equal(point, open_ground[name])
        assert content.scatter_structure_report['roots'] == 0
