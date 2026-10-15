"""The delta approach keeps its width and adds only exposed bank construction."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1]/'_toolkit'), str(HERE.parents[1]/'_finishing')]
import connector_finish as F
import manymouth_approach as A
from amberwood import mesh as M


def plane(x0, z0, x1, z1, y, material='grey_causeway'):
    p = np.array([[x0,y,z0],[x1,y,z0],[x1,y,z1],[x0,y,z1]],float)
    return M.Mesh(positions=p, normals=np.tile([0.,1.,0.],(4,1)),uvs=p[:,[0,2]],
        indices=np.array([0,2,1,0,3,2]),material=material)


class DeltaApproachTests(unittest.TestCase):
    def test_inland_mouth_descends_gently_to_exact_shared_three_metres(self):
        x=np.arange(246.5,288.50001,.25)
        y=A.collar_height(x)
        self.assertAlmostEqual(y[0],14.)
        self.assertTrue(np.all(y[x>=285.5]==3.14))
        self.assertLess(np.max(np.abs(np.diff(y)/np.diff(x))),.335)

    def test_verge_retains_specimens_and_their_footing_offset(self):
        plants=[SimpleNamespace(node=n,position=(x,3.12,z),scale=1.3,rotation_y=.2)
            for n,x,z in [('Scatter_Erratic_495',240.2149,102.4044),
                          ('Scatter_Erratic_693',243.4775,106.5672),
                          ('Scatter_Scrub_6149',247.5268,109.7877)]]
        build=SimpleNamespace(terrain_meshes={'Terrain_Test':plane(220,90,260,130,3.14),
            'Walk_ContinentRoad_'+A.ROAD:plane(246.5,118.25,260,126.75,3.17)},
            streaming_borders=[dict(id=A.ROAD,sceneNodes=[])],placements=plants)
        A.finish(build)
        self.assertEqual(len(build.placements),3)
        for plant in plants:
            self.assertAlmostEqual(plant.position[1],3.12)
            self.assertEqual((plant.scale,plant.rotation_y),(1.3,.2))
        self.assertEqual(plants[1].position[::2],(247.,91.))

    def test_inland_curve_preserves_native_start_and_common_endpoint(self):
        original = [[150.,3.9,59.7],[220.,4.8,98.],[246.5,3.14,122.5],[288.5,3.14,122.5]]
        build = SimpleNamespace(geography_roads=[dict(id=A.ROAD,stations=original)])
        A.prepare(build)
        road = build.geography_roads[0]
        self.assertEqual(road['stations'],original)
        self.assertEqual(road['contactStations'][:2],original[:2])
        self.assertEqual(road['contactStations'][-1],original[-1])
        self.assertNotIn('contactWidths',road)
        points,_ = F.R._stations(road['contactStations'][2:-1],spacing=.25)
        # Half the full road plus the frozen three-metre boundary band.
        distance = F.R._edge_distance(build,'grey_moors',points[:,[0,2]])
        self.assertGreaterEqual(float(distance.min()),7.25)

    def test_bank_mouth_covers_real_fold_without_duplicate_floor_or_soil_changes(self):
        ground = plane(240,116,258,129,3.14,'grey_heath')
        existing = plane(246.5,118.25,260,126.75,3.17)
        old_ground = ground.positions.copy();old_road = existing.positions.copy()
        build = SimpleNamespace(terrain_meshes={'Terrain_Test':ground,
            'Walk_ContinentRoad_'+A.ROAD:existing},streaming_borders=[dict(id=A.ROAD,sceneNodes=[])])
        A.finish(build)
        patch = build.terrain_meshes['Walk_DeltaRoadBankMouth']
        triangles = patch.positions[patch.indices.reshape(-1,3)]
        normals = np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        self.assertTrue((normals[:,1]>=0).all())
        ray = F.VerticalRayIndex(triangles)
        self.assertAlmostEqual(ray.top_hit(245.75,126.25),3.17,places=6)
        self.assertIsNone(ray.top_hit(250.,122.5))
        np.testing.assert_array_equal(ground.positions,old_ground)
        np.testing.assert_array_equal(existing.positions,old_road)
        self.assertIn('Walk_DeltaRoadBankMouth',build.streaming_borders[0]['sceneNodes'])


if __name__=='__main__':
    unittest.main()
