"""The relocated Lens Vault is a grounded doorway on a real public approach."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,sys,unittest
import numpy as np

HERE=Path(__file__).resolve().parent;REG=HERE.parents[1]
sys.path[:0]=[str(HERE),str(REG/'_toolkit'),str(REG/'_finishing')]
import lens_vault_approach as A
parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path);parser.add_argument('--server',type=Path);parser.add_argument('--maps',type=Path)
ARGS,remaining=parser.parse_known_args();sys.argv=[sys.argv[0]]+remaining

class SourceContract(unittest.TestCase):
    def test_whole_entry_moves_with_its_door_but_orrery_and_identity_stay(self):
        x,z=np.meshgrid(np.arange(59.,77.),np.arange(-207.,-187.))
        entry=SimpleNamespace(node=A.NODE,mesh='native-vault',position=(74.6788,112.,-205.6464),rotation_y=0.,scale=1.)
        orrery={'id':'orrery','node':'Landmark_Orrery','position':[100.,124.,-234.]}
        door={'id':A.DOOR,'position':[74.6788,112.1,-201.6464],'serverTile':[195,298],
              'destinationMap':'mirrorhold_interiors','destinationSpawn':A.DOOR,'landmark':'orrery'}
        b=SimpleNamespace(placements=[entry],portals=[door],landmarks=[orrery],authored_roads=[{'id':'lens-vault-lane','waypoints':[[74.68,112,-198],[74.68,112,-201.65]],'width':5}],terrain=SimpleNamespace(gx=x,gz=z,height=np.full_like(x,112.),tree_block=np.zeros_like(x,bool)))
        A.prepare(b)
        self.assertEqual((entry.position,entry.mesh,entry.rotation_y,entry.scale),(A.POSITION,'native-vault',0.,1.))
        self.assertEqual(orrery['position'],[100.,124.,-234.])
        self.assertEqual((door['id'],door['destinationMap'],door['destinationSpawn'],door['landmark']),
                         (A.DOOR,'mirrorhold_interiors',A.DOOR,'orrery'))
        self.assertEqual(door['serverTile'],[187,291])
        self.assertIn('originalSurveyWaypoints',b.authored_roads[0])

    def test_whole_foundation_is_level_and_earthworks_stop_locally(self):
        for x in (64.35,69.65):
            for z in (-201.15,-196.6):self.assertEqual(float(A.weight(x,z)),1.)
        self.assertEqual(float(A.weight(59.,-197.)),0.)
        self.assertEqual(float(A.weight(67.,-207.)),0.)
        self.assertEqual(float(A.weight(75.,-205.)),0.)

@unittest.skipUnless(ARGS.package,'Pass the isolated/canonical package for actual emitted proof')
class EmittedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import glb_reader as G
        from verify_runtime import VerticalRayIndex
        cls.G=G;cls.P=ARGS.package;cls.m=json.loads((cls.P/'world.json').read_text());cls.d,cls.b=G.load(cls.P/'world.glb')
        cls.portal=next(p for p in cls.m['portals'] if p['id']==A.DOOR)
        cls.origin=cls.m['coordinateTransform']['serverOrigin'];cls.tile=tuple(cls.portal['serverTile'])
        cls.actor=np.array([cls.tile[0]-cls.origin[0]+.5,cls.origin[1]-cls.tile[1]-.5])
        tri=G.triangles(cls.d,cls.b,G.named(cls.d,'Terrain_'));cls.earth=VerticalRayIndex(tri)
        nav=G.triangles(cls.d,cls.b,sorted(set(G.named(cls.d,'Terrain_')+G.named(cls.d,'Walk_'))));cls.nav=VerticalRayIndex(nav)
        cls.water=VerticalRayIndex(G.triangles(cls.d,cls.b,G.named(cls.d,'Water_')))

    def test_literal_wall_feet_and_folded_doorstep_are_supported(self):
        tri=self.G.triangles(self.d,self.b,self.G.named(self.d,A.NODE))
        low=np.unique(tri.reshape(-1,3),axis=0);low=low[np.abs(low[:,1]-A.POSITION[1])<.01]
        self.assertGreater(len(low),10)
        for p in low:self.assertAlmostEqual(self.earth.top_hit(p[0],p[2]),91.,delta=.03)
        for delta in [(0.,0.)]+[(x,z) for x in (-.75,-.25) for z in (.25,.75)]:
            q=self.actor+delta;h=self.nav.top_hit(*q)
            self.assertAlmostEqual(h,91.025,delta=.03)
            water=self.water.top_hit(*q)
            self.assertTrue(water is None or h>water+.35)

    def test_trigger_is_in_front_of_actual_facade_and_preserves_room_link(self):
        tri=self.G.triangles(self.d,self.b,self.G.named(self.d,A.NODE))
        body=tri[(tri[:,:,1].min(axis=1)<93.) & (tri[:,:,1].max(axis=1)>91.)]
        self.assertGreater(self.actor[1]-body[:,:,2].max(),.45)
        self.assertEqual(self.portal['destinationMap'],'mirrorhold_interiors')
        self.assertEqual(self.portal['destinationSpawn'],A.DOOR)
        self.assertEqual(self.portal['node'],A.NODE)

    def test_public_approach_has_manageable_emitted_full_width_grades(self):
        controls=np.array(self.m['lensVaultApproach']['publicApproach'])
        for lane in np.arange(-2.5,2.51,.5):
            for a,b in zip(controls,controls[1:]):
                delta=b[[0,2]]-a[[0,2]];length=np.linalg.norm(delta)
                side=np.array([-delta[1],delta[0]])/length;previous=None
                for t in np.linspace(0,1,int(np.ceil(length/.2))+1):
                    q=a[[0,2]]+t*delta+lane*side;h=self.nav.top_hit(*q)
                    self.assertIsNotNone(h)
                    if previous:
                        distance=np.linalg.norm(q-previous[0])
                        self.assertLessEqual(abs(h-previous[1])/distance,.38)
                    previous=(q,h)

    @unittest.skipUnless(ARGS.server and ARGS.maps,'Pass paired server/data root for production occupancy and return proof')
    def test_actual_occupied_world_reaches_trigger_and_publisher_return(self):
        S=ARGS.server;sys.path[:0]=[str(S),str(S/'tools'),str(REG.parents[1]/'tools')]
        try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
            from eloria import content_overlay
        except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
            pass
        else:
            content_overlay.configure(False)
        from collision_sources import Source
        from sync_authored_collision import choose_stage,rescale
        from eloria.collision import CollisionMap,with_step_mask,with_storage_collision,load_elm_collision
        from eloria.world import World
        from eloria.settings import load_settings
        from eloria.maps import load_maps
        from eloria.interactives import load_interactives
        from generate_nymara_maps import ARRIVAL_TILES
        import continent_portals as CP
        maps,portals=load_maps(S/'config/eloria/maps.txt');n=self.m['asset']['serverCells']
        raw=Source('ewcg','collision.bin').load(self.P,n);stage,_,_=choose_stage(raw)
        collision=with_step_mask(CollisionMap(n,n,rescale(raw,stage).tobytes()),2)
        furniture=load_interactives(S/'config/eloria/interactives.txt')
        collision=with_storage_collision(collision,[(p.x,p.y) for p in furniture.values() if p.map_id=='mirrorhold' and p.role=='storage'])
        w=World.__new__(World);w.maps=maps;w.settings=load_settings(str(S/'config/eloria/server.txt'));w.collision_maps={'mirrorhold':collision};w._footprint_collision={}
        w.sessions=[];w.animals={};w.animals_by_map={};w.npcs={};w.npc_roles={};w.npc_dialogues={};w.load_configured_npcs(str(S/'config/eloria/npcs.txt'))
        blocked=w.blocking_tiles('mirrorhold');path=w.find_path('mirrorhold',ARRIVAL_TILES['mirrorhold'],self.tile,blocked)
        # The broad path's explicit Walk_ skin must not reopen either jamb or
        # side wall; these are literal covered-entry body tiles, not a target
        # tolerance. A full connected approach must go around the facade.
        for x in range(193,199):
            for y in range(300,304):
                self.assertFalse(collision.walkable(x,y),f'Entry body reopened at {(x,y)}')
        self.assertTrue(path);self.assertEqual(path[-1],self.tile)
        automatic={(p.x,p.y) for p in portals if p.source=='mirrorhold' and p.object_id is None}
        self.assertFalse(set(path[:-1])&automatic)
        # Call the same publisher conversion, entirely in memory. Its other
        # current doors and the retained interior arrivals remain validated.
        doors={p['id']:{'tile':tuple(p['serverTile']),'name':p.get('name',p['id']),'destination':p.get('destinationMap'),'spawn':p.get('destinationSpawn')} for p in self.m['portals']}
        inside=with_step_mask(load_elm_collision(ARGS.maps/maps['mirrorhold_interiors'].file),2)
        errors=[];lines,count=CP.interior_lines({'mirrorhold':doors},{'mirrorhold':collision,'mirrorhold_interiors':inside},lambda k:None,errors,selected='mirrorhold')
        self.assertFalse(errors);self.assertEqual(count,6)
        pair=[line for line in lines if line.startswith('portal | mirrorhold | '+str(self.tile[0])+' | '+str(self.tile[1])+' |')]
        self.assertEqual(len(pair),1)
        inside_tile=tuple(map(int,pair[0].split('|')[-2:]));return_line=next(line for line in lines if line.startswith(f'portal | mirrorhold_interiors | {inside_tile[0]} | {inside_tile[1]} |'))
        outside=tuple(map(int,return_line.split('|')[-2:]));self.assertNotEqual(outside,self.tile)
        return_path=w.find_path('mirrorhold',outside,self.tile,blocked)
        self.assertTrue(return_path);self.assertEqual(return_path[-1],self.tile)
        print('LENS_ACCESS',json.dumps({'trigger':self.tile,'stage':stage,'approachSteps':len(path),'outsideReturn':outside,'returnSteps':len(return_path),'interiorArrival':inside_tile}))

if __name__=='__main__':unittest.main()
