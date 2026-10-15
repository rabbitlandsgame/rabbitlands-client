"""Actual surfaces, doorway clearance and cell ownership drive exported EWCGs."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

SOURCE = Path(__file__).resolve().parents[1]
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
import collision_export as C
import crossings as XC
from scene_io import dump_glb
from world_layout import triangle_sample


class TwoTerritories:
    def __init__(self, grade=0):
        self.x0 = self.z0 = -10
        self.x1 = self.z1 = 10
        self.ids = ['west', 'east']
        self.regions = {'west': {'center': [-3, 0]}, 'east': {'center': [3, 0]}}
        x, z = np.meshgrid(np.arange(-10, 12, 2), np.arange(-10, 12, 2))
        self.gx, self.gz = x, z
        self.plan = {'sea_level': 0., 'rivers': [], 'lakes': []}
        self.height = (x * grade).astype(float)
        self.water = {'mask': np.zeros(self.height.shape, dtype=bool), 'surface': np.zeros_like(self.height)}
        self.connections = []

    def address(self, region):
        return [6, 6], [12, 12]

    def height_at(self, x, z):
        return triangle_sample(self.height, x, z, self.x0, self.z0)

    def owner_at(self, x, z):
        return (np.broadcast_arrays(x, z)[0] >= 0).astype(int)


def quad(x0, z0, x1, z1, y):
    return np.array([[[x0, y, z0], [x1, y, z1], [x1, y, z0]],
                     [[x0, y, z0], [x0, y, z1], [x1, y, z1]]], dtype=float)


def box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1],
                  [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]])
    faces = [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
             [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
             [0, 4, 5], [0, 5, 1], [3, 2, 6], [3, 6, 7]]
    return v[faces]


def write_geometry(path, meshes, group=None):
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': []}],
           'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': []}
    body = bytearray()
    for name, triangles in meshes:
        vertices = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
        payload = vertices.tobytes()
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(body), 'byteLength': len(payload)})
        body.extend(payload)
        doc['accessors'].append({'bufferView': len(doc['bufferViews']) - 1, 'componentType': 5126,
                                 'count': len(vertices), 'type': 'VEC3'})
        doc['meshes'].append({'primitives': [{'attributes': {'POSITION': len(doc['accessors']) - 1}}]})
        doc['nodes'].append({'name': name, 'mesh': len(doc['meshes']) - 1})
    if group:
        roots = list(range(len(doc['nodes'])))
        doc['nodes'].append({'name': group, 'children': roots})
        doc['scenes'][0]['nodes'] = [len(doc['nodes']) - 1]
    else:
        doc['scenes'][0]['nodes'] = list(range(len(doc['nodes'])))
    dump_glb(path, doc, body)


def sample(result, world, region, x, z, field='walkable'):
    center = world.regions[region]['center']
    origin, _ = world.address(region)
    column = int(np.floor((x - center[0] + origin[0]) / .5))
    row = int(np.floor((origin[1] - z + center[1]) / .5))
    return result[field][row, column]


class CollisionExportTests(unittest.TestCase):
    def export(self, world, meshes=(), solids=(), region='west', group=None):
        directory = Path(self.folder.name)
        glb = directory / f'{region}.glb'
        write_geometry(glb, meshes, group)
        origin, cells = world.address(region)
        manifest = {'coordinateTransform': {'serverOrigin': origin, 'serverCells': cells},
                    'navigation': {'surfaceNodePrefixes': ['Terrain_', 'Walk_']},
                    'collision': {'nodeNames': list(solids)}}
        return C.export_collision(world, region, manifest, glb, directory / f'{region}.bin')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()

    def gate(self, *identities):
        """Keep these seams to their gates, so the threshold halo is seen on its own."""
        saved = XC.GATED_SEAMS
        XC.GATED_SEAMS = identities
        self.addCleanup(setattr, XC, 'GATED_SEAMS', saved)

    def tearDown(self):
        self.folder.cleanup()

    def test_steep_ground_is_blocked_without_quantisation_hiding_the_grade(self):
        steep = TwoTerritories(.8)
        self.assertFalse(self.export(steep)['walkable'].any())
        gentle = TwoTerritories(.6)
        result = self.export(gentle)
        self.assertTrue(sample(result, gentle, 'west', -3.25, .25))
        self.assertAlmostEqual(float(sample(result, gentle, 'west', -3.25, .25, 'heights')), -1.95, places=5)

    def test_an_actual_bridge_deck_is_walkable_over_water(self):
        world = TwoTerritories()
        world.water['mask'][:] = True
        world.water['surface'][:] = 1
        result = self.export(world, [('Walk_Bridge', quad(-2, -2, 2, 2, 1.5))])
        self.assertTrue(sample(result, world, 'west', -3.25, .25))
        self.assertAlmostEqual(float(sample(result, world, 'west', -3.25, .25, 'heights')), 1.5)
        self.assertFalse(sample(result, world, 'west', -6.25, .25))
        ceiling = self.export(world, [('Walk_Ceiling', quad(-2, -2, 2, 2, 1.5))])
        self.assertFalse(ceiling['walkable'].any())

    def test_arch_roof_above_head_does_not_block_the_doorway(self):
        world = TwoTerritories()
        meshes = [('LeftPost', box(-2.5, 0, -1, -1.5, 4, 1)),
                  ('RightPost', box(1.5, 0, -1, 2.5, 4, 1)),
                  ('RoofLintel', box(-2.5, 3, -1, 2.5, 4, 1))]
        result = self.export(world, meshes, ['GateArch'], group='GateArch')
        self.assertTrue(sample(result, world, 'west', -3.25, .25))
        self.assertFalse(sample(result, world, 'west', -5.25, .25))
        low = self.export(world, [('LowLintel', box(-2.5, 1.8, -1, 2.5, 2.5, 1))], ['LowLintel'])
        self.assertFalse(sample(low, world, 'west', -3.25, .25))

    def test_a_tall_closed_solid_blocks_its_interior_not_just_its_walls(self):
        world = TwoTerritories()
        solid = box(-2, -1, -2, 2, 8, 2)
        self.assertTrue(C.closed_mesh(solid))
        result = self.export(world, [('SolidRock', solid)], ['SolidRock'])
        self.assertFalse(sample(result, world, 'west', -3.25, .25))

    def test_thin_edge_on_wall_is_not_lost_by_a_vertical_raycast(self):
        world = TwoTerritories()
        wall = np.array([[[0, 0, -2], [0, 3, -2], [0, 3, 2]],
                         [[0, 0, -2], [0, 3, 2], [0, 0, 2]]])
        result = self.export(world, [('ThinWall', wall)], ['ThinWall'])
        self.assertFalse(sample(result, world, 'west', -3.25, .25))
        self.assertTrue(sample(result, world, 'west', -4.25, .25))

    def test_halo_requires_an_actual_threshold_and_stays_two_metres_deep(self):
        self.gate('road')
        world = TwoTerritories()
        world.connections = [{'id': 'road', 'regions': ['west', 'east'], 'type': 'walk',
                              'anchor': [0, 0], 'normal': [1, 0]}]
        absent = self.export(world)
        self.assertFalse(sample(absent, world, 'west', .25, .25))
        # Coordinates are local to each territory; both see one global deck.
        west = self.export(world, [('Walk_Threshold', quad(1, -5, 6, 5, .02))])
        east = self.export(world, [('Walk_Threshold', quad(-6, -5, -1, 5, .02))], region='east')
        self.assertTrue(sample(west, world, 'west', 1.75, .25))
        self.assertFalse(sample(west, world, 'west', 2.25, .25))
        self.assertFalse(sample(west, world, 'west', .25, 4.25))
        self.assertTrue(sample(east, world, 'east', -1.75, .25))
        self.assertAlmostEqual(float(sample(west, world, 'west', .25, .25, 'heights')),
                               float(sample(east, world, 'east', .25, .25, 'heights')))

    def test_an_open_seam_opens_the_first_tile_across_its_whole_border_without_a_deck(self):
        world = TwoTerritories()
        world.connections = [{'id': 'road', 'regions': ['west', 'east'], 'type': 'walk',
                              'anchor': [0, 0], 'normal': [1, 0]}]
        result = self.export(world)
        # The neighbour's first tile across the border can be stood on, by the gate
        # and four metres along the border from it alike, since that is where the
        # crossing hands a walker over...
        for z in (.25, 4.25, -4.75):
            with self.subTest(z=z):
                self.assertTrue(sample(result, world, 'west', .25, z))
                self.assertTrue(sample(result, world, 'west', .75, z))
                # ...and nothing beyond it: a step cannot reach past the crossing.
                self.assertFalse(sample(result, world, 'west', 1.25, z))
        self.assertGreater(result['collision']['exportStatistics']['seamCollarCells'], 0)
        # The collar is the neighbour's ground, so it does not stretch this map's scale.
        self.gate('road')
        closed = self.export(world)
        self.assertEqual(result['collision']['heightEncoding'], closed['collision']['heightEncoding'])

    def test_a_saved_seam_keeps_all_seven_exact_triggers_on_a_stepped_boundary(self):
        world = TwoTerritories()
        world.connections = [{'id': 'saved-road', 'regions': ['west', 'east'], 'type': 'walk',
                              'anchor': [0, 0], 'normal': [1, 0]}]
        world.saved_seam_approaches = [{'id': 'saved-road', 'region': 'west'}]
        # Put the ownership edge on the surveyed anchor.  The canonical
        # departure tile is centred 1.5 m beyond it and all four of that
        # actor tile's half-cells must be served on each map.
        west = self.export(world, region='west')
        east = self.export(world, region='east')
        for z in (-3.75, -2.75, -1.75, -.75, .25, 1.25, 2.25, 3.25, 3.75):
            with self.subTest(region='west', z=z):
                self.assertTrue(sample(west, world, 'west', 1.75, z))
            with self.subTest(region='east', z=z):
                self.assertTrue(sample(east, world, 'east', -1.75, z))
        self.assertFalse(sample(west, world, 'west', 2.25, .25))
        self.assertFalse(sample(east, world, 'east', -2.25, .25))

    def test_an_automatic_seam_does_not_receive_the_saved_trigger_apron(self):
        world = TwoTerritories()
        world.connections = [{'id': 'automatic-road', 'regions': ['west', 'east'], 'type': 'walk',
                              'anchor': [0, 0], 'normal': [1, 0]}]
        world.saved_seam_approaches = [{'id': 'different-saved-road', 'region': 'west'}]
        result = self.export(world, region='west')
        self.assertTrue(sample(result, world, 'west', .75, .25))
        self.assertFalse(sample(result, world, 'west', 1.25, .25))
        self.assertFalse(sample(result, world, 'west', 1.75, .25))

    def test_each_half_cell_can_close_its_full_actor_tile(self):
        world = TwoTerritories()
        baseline = self.export(world)['walkable']
        for gx, gz in [(-.75, -.75), (-.75, -.25), (-.25, -.75), (-.25, -.25)]:
            with self.subTest(x=gx, z=gz):
                x = gx - world.regions['west']['center'][0]
                cube = box(x - .04, 0, gz - .04, x + .04, 1, gz + .04)
                result = self.export(world, [('Post', cube)], ['Post'])
                self.assertEqual(int((baseline & ~result['walkable']).sum()), 1)
                blocked = result['grid'].reshape(12, 2, 12, 2).min(axis=(1, 3))
                self.assertEqual(int((blocked == 0).sum()), int((baseline.reshape(12, 2, 12, 2).all(axis=(1, 3)) == 0).sum()) + 1)

    def test_stepped_ownership_inside_threshold_covers_all_four_arrival_subcells(self):
        self.gate('stepped-road')
        world = TwoTerritories()
        world.owner_at = lambda x,z: (np.broadcast_arrays(x,z)[0] >=
            np.where(np.broadcast_arrays(x,z)[1] > 2, -5,
                     np.where(np.broadcast_arrays(x,z)[1] > 0, -2, 0))).astype(int)
        world.connections = [{'id':'stepped-road','regions':['west','east'],'type':'walk',
                              'anchor':[0,0],'normal':[1,0]}]
        absent = self.export(world)
        result = self.export(world, [('Walk__StreamThreshold_stepped-road',quad(-3,-5,6,5,.02))])
        for x,z in ((-1.75,.25),(-1.25,.25),(-1.75,.75),(-1.25,.75)):
            self.assertFalse(sample(absent,world,'west',x,z))
            self.assertTrue(sample(result,world,'west',x,z))
        # A real deck beyond the authored inward extent is not authority to
        # annex more of the neighboring territory.
        self.assertFalse(sample(result,world,'west',-4.25,2.25))

    def test_binary_metadata_is_reproducible_and_contains_no_arrays(self):
        world = TwoTerritories(.4)
        result = self.export(world)
        binary = Path(self.folder.name) / 'west.bin'
        before = binary.read_bytes()
        repeat = self.export(world)
        self.assertEqual(before, binary.read_bytes())
        self.assertEqual(result['collision'], repeat['collision'])
        self.assertEqual(struct.unpack_from('<4sHHII', before), (b'EWCG', 2, 0, 24, 24))
        json.dumps(result['collision'])
        self.assertEqual(result['collision']['gridAlignment'], 'tile-centres-v1')
        self.assertTrue(result['collision']['authoredSurfaceExport'])


if __name__ == '__main__':
    unittest.main()
