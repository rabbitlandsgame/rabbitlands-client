"""Regression checks for the authored Ssarathi package; no files are written."""
import argparse,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np

SOURCE=Path(__file__).resolve().parent
PACKAGE=SOURCE.parent
sys.path[:0]=[str(SOURCE.parents[1]/'_toolkit')]
import glb_reader as GLB

class LandscapeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import collision_sources as C,sync_authored_collision as S
        from eloria.collision import CollisionMap,with_step_mask
        from eloria.world import World
        from content_placement import flood
        cls.manifest=json.loads((PACKAGE/'world.json').read_text())
        cls.frame=cls.manifest['continentGeography']
        cls.width,cls.height=map(int,cls.frame['serverCells'])
        cls.origin=np.asarray(cls.frame['serverOrigin'],float)
        cls.shift=np.asarray(cls.frame['serverTileShift'],int)
        raw=C.authored_collision('ssarathi_ruins',cls.width,PACKAGE.parents[1])
        factor,*_=S.choose_stage(raw)
        cls.grid=with_step_mask(CollisionMap(cls.width,cls.height,S.rescale(raw,factor).astype(np.uint8).tobytes()),2)
        cls.world=World.__new__(World)
        cls.world.settings=SimpleNamespace(max_walk_height_change=2)
        cls.world.collision_maps={'ssarathi_ruins':cls.grid}
        cls.world.sessions=[];cls.world.animals_by_map={};cls.world.animals={}
        cls.primary=next(s for s in cls.manifest['spawnPoints'] if s['id']=='default')
        cls.reachable=flood(cls.grid,[tuple(cls.primary['serverTile'])])

    def native_tile(self,tile):
        return tuple(int(a+b) for a,b in zip(tile,self.shift))

    def test_native_core_and_expanded_server_frame(self):
        authored=json.loads((PACKAGE.parent/'continent-geography.json').read_text())['regions']['ssarathi_ruins']
        self.assertEqual(self.frame['nativeServerOrigin'],[116,116])
        self.assertEqual(self.frame['nativeServerCells'],[384,384])
        self.assertEqual(self.frame['serverOrigin'],authored['serverOrigin'])
        self.assertEqual(self.frame['serverCells'],authored['serverCells'])
        np.testing.assert_array_equal(self.shift,self.origin-np.asarray(self.frame['nativeServerOrigin']))
        self.assertEqual(tuple(self.primary['serverTile']),self.native_tile((116,116)))
        np.testing.assert_allclose(self.primary['position'][::2],[0.,0.],atol=1e-8)

    def test_all_ordinary_entries_and_seven_lane_joins(self):
        self.assertEqual(len(self.manifest['portals']),11)
        points=[p['serverTile'] for p in self.manifest['portals']]
        portals={p['id']:p for p in self.manifest['portals']}
        for frame in self.manifest['streamingBorders']:
            portal=portals[frame['portal']]
            dx,dz=frame['outward']
            # Seven actual actor lanes around the current authored trigger.
            points += [(portal['serverTile'][0]-dz*i,portal['serverTile'][1]-dx*i) for i in range(-3,4)]
        for x,y in points:
            with self.subTest(tile=(x,y)):self.assertTrue(self.reachable[y*self.width+x])

    def test_processional_axis_and_summit_have_short_exact_paths(self):
        for start,end,maximum in [((156,180),(180,240),110),((156,234),(156,298),90)]:
            start,end=self.native_tile(start),self.native_tile(end)
            with self.subTest(start=start,end=end):
                path=self.world.find_path('ssarathi_ruins',start,end,set())
                self.assertTrue(path)
                self.assertEqual(path[-1],end)
                self.assertLessEqual(len(path),maximum)

    def test_stair_and_bank_are_real_continuous_surfaces(self):
        doc,body=GLB.load(PACKAGE/'world.glb')
        nodes=sorted({n for prefix in self.manifest['navigation']['surfaceNodePrefixes'] for n in GLB.named(doc,prefix)})
        tri=GLB.triangles(doc,body,nodes)
        tri=tri[(tri[:,:,0].max(axis=1)>=39)&(tri[:,:,0].min(axis=1)<=42)&
                (tri[:,:,2].max(axis=1)>=-184)&(tri[:,:,2].min(axis=1)<=-65)]
        covered,top=GLB.rasterise(tri,1,119,40,-65,1)
        self.assertTrue(covered.all())
        self.assertLess(float(np.abs(np.diff(top[:,0])).max()),1.2)

    def test_house_bodies_are_not_opened_as_floors(self):
        for x,z in [(27,-10),(-27,-10),(50,-21),(124,43),(165,43),(-12,-93)]:
            with self.subTest(house=(x,z)):self.assertFalse(self.grid.walkable(int(x+self.origin[0]),int(self.origin[1]-z)))

    def test_ferry_return_has_real_deck_beyond_departure(self):
        trigger=next(p['serverTile'] for p in self.manifest['portals'] if p['id']=='south-gate')
        # The continent publisher chooses two tiles towards the closest edge's
        # inward direction. Both points must be on the physical ferry dock.
        arrival=(trigger[0],trigger[1]+2)
        self.assertTrue(self.grid.walkable(*arrival))
        self.assertTrue(self.reachable[arrival[1]*self.width+arrival[0]])

    def test_summit_roof_can_be_faded_without_fading_temple_body(self):
        doc,body=GLB.load(PACKAGE/'world.glb')
        nodes=GLB.named(doc,'Structure_TempleSummitRoof')
        self.assertTrue(nodes)
        tri=GLB.triangles(doc,body,nodes)
        extent=tri.max(axis=(0,1))-tri.min(axis=(0,1))
        self.assertLess(max(extent[0],extent[2]),60)
        self.assertGreater(float(tri[:,:,1].min()),56)

    def test_western_wet_landing_has_a_real_supported_slab(self):
        from verify_runtime import VerticalRayIndex
        doc,body=GLB.load(PACKAGE/'world.glb')
        cap_nodes=GLB.named(doc,'Structure_WestRuinLanding_Cap')
        self.assertTrue(cap_nodes,'The wet road-to-causeway joint needs its masonry landing')
        cap=GLB.triangles(doc,body,cap_nodes)
        native=GLB.triangles(doc,body,GLB.named(doc,'Walk_StreamCauseway_ssarathi-manymouth'))
        self.assertLess(float(cap[:,:,0].min()),float(native[:,:,0].max()))
        self.assertGreater(float(cap[:,:,0].max()),float(native[:,:,0].max()))
        normals=np.cross(cap[:,1]-cap[:,0],cap[:,2]-cap[:,0])
        self.assertFalse((normals[:,1]>1e-7).any(),'The landing must not duplicate the walking top')
        soffit=VerticalRayIndex(cap)
        road=VerticalRayIndex(GLB.triangles(doc,body,GLB.named(doc,'Walk_ContinentRoad_ssarathi-manymouth')))
        q=(-107.40198,-72.47918)
        self.assertIsNotNone(soffit.top_hit(*q))
        self.assertAlmostEqual(road.top_hit(*q)-soffit.top_hit(*q),.8,delta=.08)
        ground=VerticalRayIndex(GLB.triangles(doc,body,GLB.named(doc,'Terrain_')))
        self.assertGreaterEqual(ground.top_hit(-106.75,-73.5),float(cap[:,:,1].min()))

    def test_strict_guard_and_full_content_contract(self):
        self.assertEqual(self.manifest['collision']['actorSurfaceGuard']['method'],'rendered-tile-centre-v1')
        self.assertTrue(self.manifest['contentLayout']['requireFullWildlife'])
        self.assertEqual(len(self.manifest['contentLayout']['npcs']),14)
        self.assertEqual(sum(p.get('kind')=='secret' for p in self.manifest['interactives']),14)
        self.assertEqual(len({p['id'] for p in self.manifest['landmarks']}),len(self.manifest['landmarks']))

    def test_shared_approaches_reference_single_exported_nodes(self):
        doc,_=GLB.load(PACKAGE/'world.glb');names={n.get('name') for n in doc['nodes']}
        self.assertFalse(any(n and ('StreamView_' in n or '_StreamOverflow_' in n) for n in names))
        for frame in self.manifest['streamingBorders']:
            self.assertEqual(frame['geometryMode'],'continent-owned-v1')
            self.assertTrue(frame['sceneNodes'])
            self.assertFalse(set(frame['sceneNodes'])-names)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--server',type=Path,required=True)
    args,remaining=ap.parse_known_args()
    sys.path[:0]=[str(args.server/'tools'),str(args.server)]
    unittest.main(argv=[sys.argv[0]]+remaining)
