"""Actual public-apron geometry and served access for the west-bench steward."""
from pathlib import Path
import argparse, ast, json, sys, unittest
import numpy as np

PACKAGE=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--server',type=Path)
parser.add_argument('--maps',type=Path)
ARGS,remaining=parser.parse_known_args()
sys.argv=[sys.argv[0]]+remaining
sys.path.insert(0,str(PACKAGE.parent/'_toolkit'))
import glb_reader as G
from verify_runtime import VerticalRayIndex

def source_posts():
    tree=ast.parse((PACKAGE/'source/landscape_plan.py').read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='manifest')
    for node in ast.walk(function):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Subscript)
             and isinstance(t.slice,ast.Constant) and t.slice.value=='npcs' for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('Authored NPC post mapping is missing')

class StewardPost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.position=source_posts()['Bench Steward Aurel Fane']
        cls.manifest=json.loads((PACKAGE/'world.json').read_text())
        cls.origin=cls.manifest['coordinateTransform']['serverOrigin']
        cls.tile=(round(cls.position[0]+cls.origin[0]),round(cls.origin[1]-cls.position[2]))
        cls.actor=np.array([cls.tile[0]-cls.origin[0]+.5,cls.origin[1]-cls.tile[1]-.5])
        cls.doc,cls.body=G.load(PACKAGE/'world.glb')
        cls.ground=VerticalRayIndex(G.triangles(cls.doc,cls.body,G.named(cls.doc,'Terrain_')))
        water=G.triangles(cls.doc,cls.body,G.named(cls.doc,'Water_'))
        cls.water=VerticalRayIndex(water) if len(water) else None

    def test_actual_apron_and_conservative_fold_are_flat_dry_and_grounded(self):
        offsets=[(0,0)]+[(x,z) for x in (-.75,-.25) for z in (.25,.75)]
        for dx,dz in offsets:
            p=self.actor+[dx,dz]
            with self.subTest(point=p):
                h=self.ground.top_hit(*p)
                self.assertIsNotNone(h)
                self.assertAlmostEqual(h,self.position[1],delta=.03)
                w=self.water.top_hit(*p) if self.water else None
                self.assertTrue(w is None or h>w+.15)

    def test_footprint_is_outside_watch_and_house_including_their_overhangs(self):
        for name in ('Landmark_far-west','Building_CliffHouse_10'):
            tri=G.triangles(self.doc,self.body,G.named(self.doc,name))
            self.assertGreater(len(tri),0)
            low=tri.min((0,1))[[0,2]];high=tri.max((0,1))[[0,2]]
            self.assertTrue(np.any(self.actor+.35<low) or np.any(self.actor-.35>high),name)

    def test_emitted_post_reproduces_authored_public_apron(self):
        self.assertEqual(self.manifest['contentLayout']['npcs']['Bench Steward Aurel Fane'],self.position)

    @unittest.skipUnless(ARGS.server and ARGS.maps,'Pass the paired server and actual ELM data root for production access proof')
    def test_occupied_world_reaches_the_exact_post_without_an_automatic_door(self):
        sys.path[:0]=[str(ARGS.server.resolve()/'tools'),str(ARGS.server.resolve())]
        try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
            from eloria import content_overlay
        except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
            pass
        else:
            content_overlay.configure(False)
        from eloria.maps import load_maps
        from eloria.settings import load_settings
        from eloria.interactives import load_interactives
        from eloria.collision import load_collision_maps,with_storage_collision
        from eloria.world import World
        profile=ARGS.server/'config/eloria';maps,portals=load_maps(profile/'maps.txt')
        world=World.__new__(World);world.maps=maps;world.settings=load_settings(str(profile/'server.txt'))
        world.collision_maps=load_collision_maps(str(ARGS.maps),maps,world.settings.max_walk_height_change)
        furniture=load_interactives(profile/'interactives.txt')
        world.collision_maps['mirrorhold']=with_storage_collision(world.collision_maps['mirrorhold'],
            ((i.x,i.y) for i in furniture.values() if i.map_id=='mirrorhold' and i.role=='storage'))
        world.sessions=[];world.animals={};world.animals_by_map={};world.npcs={};world.npc_roles={};world.npc_dialogues={};world._footprint_collision={}
        world.load_configured_npcs(str(profile/'npcs.txt'))
        # The traveller can approach the post before its NPC is seated there.
        # Exclude only this NPC's own standing tile, retaining all other bodies.
        blocked=world.blocking_tiles('mirrorhold')-{self.tile}
        from generate_nymara_maps import ARRIVAL_TILES
        path=world.find_path('mirrorhold',ARRIVAL_TILES['mirrorhold'],self.tile,blocked)
        self.assertTrue(path)
        self.assertEqual(path[-1],self.tile)
        automatic={(p.x,p.y) for p in portals if p.source=='mirrorhold' and p.object_id is None}
        self.assertFalse(set(path)&automatic)
        # Once the NPC occupies the post, a visitor must still reach an exact
        # adjacent conversation tile without stepping through another doorway.
        occupied=blocked|{self.tile}
        approaches=[]
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            target=(self.tile[0]+dx,self.tile[1]+dy)
            path=world.find_path('mirrorhold',ARRIVAL_TILES['mirrorhold'],target,occupied)
            if path and path[-1]==target and not set(path)&automatic:approaches.append(target)
        self.assertTrue(approaches,'The seated steward has no reachable conversation approach')

class CitadelStaffPosts(unittest.TestCase):
    NAMES=('Lens-Master Corvine Ast','Orrery Keeper Sabel Roon')

    @classmethod
    def setUpClass(cls):
        cls.posts={name:source_posts()[name] for name in cls.NAMES}
        cls.manifest=json.loads((PACKAGE/'world.json').read_text())
        cls.origin=cls.manifest['coordinateTransform']['serverOrigin']
        cls.tiles={name:(round(p[0]+cls.origin[0]),round(cls.origin[1]-p[2])) for name,p in cls.posts.items()}
        cls.doc,cls.body=G.load(PACKAGE/'world.glb')
        cls.nav=VerticalRayIndex(G.triangles(cls.doc,cls.body,sorted(set(G.named(cls.doc,'Terrain_')+G.named(cls.doc,'Walk_')))))
        cls.water=VerticalRayIndex(G.triangles(cls.doc,cls.body,G.named(cls.doc,'Water_')))

    def test_staff_have_level_dry_footprints_on_opposite_court_flanks(self):
        points=[]
        for name,tile in self.tiles.items():
            actor=np.array([tile[0]-self.origin[0]+.5,self.origin[1]-tile[1]-.5]);points.append(actor)
            for dx,dz in [(0,0)]+[(x,z) for x in (-.75,-.25) for z in (.25,.75)]:
                q=actor+[dx,dz];height=self.nav.top_hit(*q);water=self.water.top_hit(*q)
                self.assertIsNotNone(height);self.assertAlmostEqual(height,self.posts[name][1],delta=.03)
                self.assertTrue(water is None or height>water+.35)
            portal=next(p for p in self.manifest['portals'] if p['id']=='lens-vault-stair')
            self.assertGreater(np.linalg.norm(np.array(tile)-portal['serverTile']),3.)
        self.assertGreaterEqual(np.linalg.norm(points[0]-points[1]),6.)

    def test_staff_bodies_are_clear_of_the_full_actual_doorway(self):
        tri=G.triangles(self.doc,self.body,G.named(self.doc,'Building_VaultEntry_lens-vault-stair'))
        self.assertGreater(len(tri),0)
        low=tri.min((0,1))[[0,2]];high=tri.max((0,1))[[0,2]]
        for tile in self.tiles.values():
            actor=np.array([tile[0]-self.origin[0]+.5,self.origin[1]-tile[1]-.5])
            self.assertTrue(np.any(actor+.45<low) or np.any(actor-.45>high))

    @unittest.skipUnless(ARGS.server and ARGS.maps,'Pass final served ELMs for simultaneous occupied World proof')
    def test_both_seated_staff_and_lens_roundtrip_keep_real_public_access(self):
        sys.path[:0]=[str(ARGS.server.resolve()/'tools'),str(ARGS.server.resolve())]
        try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
            from eloria import content_overlay
        except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
            pass
        else:
            content_overlay.configure(False)
        from eloria.maps import load_maps
        from eloria.settings import load_settings
        from eloria.interactives import load_interactives
        from eloria.collision import load_elm_collision,with_step_mask,with_storage_collision
        from eloria.world import World
        from generate_nymara_maps import ARRIVAL_TILES
        profile=ARGS.server/'config/eloria';maps,portals=load_maps(profile/'maps.txt')
        world=World.__new__(World);world.maps=maps;world.settings=load_settings(str(profile/'server.txt'))
        collision=with_step_mask(load_elm_collision(ARGS.maps/maps['mirrorhold'].file),2)
        furniture=load_interactives(profile/'interactives.txt')
        collision=with_storage_collision(collision,[(p.x,p.y) for p in furniture.values() if p.map_id=='mirrorhold' and p.role=='storage'])
        world.collision_maps={'mirrorhold':collision};world.sessions=[];world.animals={};world.animals_by_map={}
        world.npcs={};world.npc_roles={};world.npc_dialogues={};world._footprint_collision={}
        world.load_configured_npcs(str(profile/'npcs.txt'))
        # The source post is the contract even before its next publication;
        # only these two actors are reseated in this temporary World.
        found=set()
        for actor,map_id,_,_ in world.npcs.values():
            if map_id=='mirrorhold' and actor.name in self.tiles:
                actor.x,actor.y=self.tiles[actor.name];found.add(actor.name)
        self.assertEqual(found,set(self.NAMES))
        occupied=world.blocking_tiles('mirrorhold');arrival=ARRIVAL_TILES['mirrorhold']
        automatic={(p.x,p.y) for p in portals if p.source=='mirrorhold' and p.object_id is None}
        for tile in self.tiles.values():
            path=world.find_path('mirrorhold',arrival,tile,occupied)
            self.assertTrue(path);self.assertEqual(max(abs(path[-1][i]-tile[i]) for i in (0,1)),1)
            self.assertFalse(set(path)&automatic)
        door=tuple(next(p for p in self.manifest['portals'] if p['id']=='lens-vault-stair')['serverTile'])
        path=world.find_path('mirrorhold',arrival,door,occupied)
        self.assertTrue(path);self.assertEqual(path[-1],door);self.assertFalse(set(path[:-1])&automatic)
        returns=[p for p in portals if p.source=='mirrorhold_interiors' and p.destination=='mirrorhold'
                 and max(abs(p.destination_x-door[0]),abs(p.destination_y-door[1]))<=4]
        self.assertEqual(len(returns),1)
        path=world.find_path('mirrorhold',(returns[0].destination_x,returns[0].destination_y),door,occupied)
        self.assertTrue(path);self.assertEqual(path[-1],door)

if __name__=='__main__':unittest.main()
