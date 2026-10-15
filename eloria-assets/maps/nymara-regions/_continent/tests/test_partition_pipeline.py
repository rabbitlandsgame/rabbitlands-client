import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from crossings import prepare_contracts,global_tile
import scene_io as S
from amberwood import mesh as M,gltf as G
from build_continent import bridge_scene
from content import Content
from world_layout import World,graded_profile,corridor_grade,fit_road_to_footings
import landscape as L


class FlatWorld:
    ids=['west','east'];regions={'west':{'center':[10,10]},'east':{'center':[30,10]}}
    centers=np.array([[10,10],[30,10]])
    polygons={'west':[[0,0],[20,0],[20,20],[0,20]],'east':[[20,0],[40,0],[40,20],[20,20]]}
    plan={'rivers':[],'lakes':[],'sea_level':0};roads=[]
    x0=0.;z0=0.;x1=40.;z1=20.
    connections=[{'id':'east--west','type':'walk','regions':['west','east'],
        'anchor':[20,10],'normal':[1,0],'edgeSegments':[[[20,0],[20,20]]]}]
    def address(self,region):return [24,24],[48,48]
    def height_at(self,x,z):return np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))[0]*0+2
    def owner_at(self,x,z):return (np.asarray(x)>=20).astype(int)
    def adjacent_edges(self):return {(0,1):[[[20,0],[20,20]]]}


class PipelineTests(unittest.TestCase):
    def test_authored_placement_selects_the_default_scene_root_not_a_later_named_prototype(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'source.glb';target=folder/'selected.glb'
            builder=G.GltfBuilder('test');builder.add_material(G.Material('plain'))
            builder.add_mesh('mesh',M.box((2,2,2),material='plain'),with_tangents=False)
            builder.add_node(G.Node('Placed',mesh='mesh',translation=(10,0,20)))
            builder.add_node(G.Node('Placed',mesh='mesh',translation=(100,0,200)))
            builder.write_glb(str(source));document,body=S.GR.load(source)
            first,duplicate=document['scenes'][0]['nodes']
            wrapper=len(document['nodes'])
            document['nodes'].append({'name':'Other','children':[duplicate]})
            document['scenes'][0]['nodes']=[first,wrapper]
            content=Content.__new__(Content)
            content.authoring_snapshots={'sunmane_steppe':SimpleNamespace(translation=np.array([1200.,0.,720.]))}
            content.documents={};content.metadata={};content.transforms={};content.source_centers={};content.scales={}
            content.objects=[];content.mapping={};content.placement_by_name={};content.bounds_by_name={};content.prototypes={}
            content.world=SimpleNamespace(height_at=lambda x,z:2.)
            metadata={'placements':[{'node':'Placed','kind':'prop','collides':True,'walk_surface':False}]}
            content.load_authored_region('sunmane_steppe',document,body,metadata)
            placed=content.objects[0]
            self.assertEqual(placed['index'],first)
            np.testing.assert_allclose((placed['low']+placed['high'])/2,[1210,0,740])
            export=S.Exporter(target);export.add(document,body,[placed['index']]);export.write()
            selected,binary=S.GR.load(target)
            low,high=S.subtree_bounds(selected,binary,selected['scenes'][0]['nodes'][0])
            np.testing.assert_allclose((low+high)/2,[10,0,20])

            bad=dict(metadata);bad['placements']=[dict(metadata['placements'][0],node='Missing')]
            with self.assertRaisesRegex(ValueError,r"sunmane_steppe: authored placement 'Missing' is missing certified roots \['Missing'\]"):
                content.load_authored_region('sunmane_steppe',document,body,bad)
            document['scenes'][0]['nodes'].append(duplicate)
            with self.assertRaisesRegex(ValueError,"duplicate scene root 'Placed'"):
                content.load_authored_region('sunmane_steppe',document,body,metadata)

    def test_authored_pass_must_use_a_safe_existing_boundary_station(self):
        ids=[r['id'] for r in L.load_plan()['regions']]
        a,b=ids.index('verdant_stair'),ids.index('ssarathi_ruins')
        centers=np.zeros((len(ids),2));centers[a]=[10,20];centers[b]=[30,20]
        world=SimpleNamespace(ids=ids,centers=centers,connections=[],
            plan={'rivers':[],'lakes':[],'sea_level':0,'connection_sites':{'ssarathi_ruins--verdant_stair':[20,11]}},
            adjacent_edges=lambda:{tuple(sorted((a,b))):[[[20,z],[20,z+2]] for z in range(0,40,2)]},
            height_at=lambda x,z:np.zeros_like(x)+2,
            owner_at=lambda x,z:np.where(np.asarray(x)<20,a,b))
        World.plan_connections(world)
        self.assertEqual(world.connections[0]['anchor'],[20.,11.])
        world.connections=[];world.plan['connection_sites']['ssarathi_ruins--verdant_stair']=[21,11]
        with self.assertRaisesRegex(ValueError,'not a safe shared boundary station'):
            World.plan_connections(world)

    def test_an_authored_station_may_stand_on_a_step_of_the_seam(self):
        # The seam runs up x=20 to z=10, steps two metres east and runs on up x=22:
        # (22, 13) stands on a vertical run of two segments below it, not seven.
        ids=[r['id'] for r in L.load_plan()['regions']]
        a,b=ids.index('verdant_stair'),ids.index('ssarathi_ruins')
        centers=np.zeros((len(ids),2));centers[a]=[10,20];centers[b]=[30,20]
        seam=[[[20,z],[20,z+2]] for z in range(0,10,2)]+[[[20,10],[22,10]]]+[[[22,z],[22,z+2]] for z in range(10,40,2)]
        boundary=lambda z:np.where(np.asarray(z)<10,20,22)
        world=SimpleNamespace(ids=ids,centers=centers,connections=[],
            plan={'rivers':[],'lakes':[],'sea_level':0,'connection_sites':{'ssarathi_ruins--verdant_stair':[22,13]}},
            adjacent_edges=lambda:{tuple(sorted((a,b))):seam},
            height_at=lambda x,z:np.zeros_like(x)+2,seam_terminal_penalty=lambda point,normal:0.,
            owner_at=lambda x,z:np.where(np.asarray(x)<boundary(z),a,b))
        World.plan_connections(world)
        self.assertEqual(world.connections[0]['anchor'],[22.,13.])
        # What the model chooses for itself still stands on a straight run.
        world.connections=[];del world.plan['connection_sites']['ssarathi_ruins--verdant_stair']
        World.plan_connections(world)
        anchor=world.connections[0]['anchor']
        self.assertEqual(anchor[0],22.)
        self.assertGreaterEqual(anchor[1],17.,"seven segments of x=22 stand either side of the model's own station")

    def test_contradictory_footings_do_not_cut_a_cliff_through_the_street(self):
        target=np.full((9,60),25.);active=np.ones_like(target,bool)
        fixed=np.zeros_like(active);floor=np.zeros_like(target)
        fixed[:,15]=True;fixed[:,30]=True;fixed[:,50]=True
        floor[:,30]=20.;floor[:,50]=10.
        height,conflicts=fit_road_to_footings(target,active,floor,fixed)
        self.assertGreater(conflicts,0)
        self.assertLess(conflicts,active.size)
        # Includes transitions between feasible and reversed bounds. The old
        # partial assignment left a many-metre seam through the actual street.
        self.assertLessEqual(np.max(np.abs(np.diff(height,axis=1)))/2,.60/np.sqrt(2)+1e-6)
        self.assertTrue(np.isfinite(height).all())
        self.assertFalse(np.array_equal(height[fixed],floor[fixed]))

    def test_road_approach_meets_an_immutable_courtyard_without_excavating_it(self):
        target=np.zeros((9,60));active=np.ones_like(target,bool);fixed=np.zeros_like(active);fixed[:,5]=True;fixed[:,54]=True
        floor=np.zeros_like(target);floor[:,54]=25
        height,conflicts=fit_road_to_footings(target,active,floor,fixed)
        self.assertEqual(conflicts,0)
        np.testing.assert_allclose(height[:,5],0);np.testing.assert_allclose(height[:,54],25)
        self.assertLessEqual(np.max(np.abs(np.diff(height,axis=1)))/2,.60/np.sqrt(2)+1e-6)
    def test_offshore_outside_world_coordinates_have_no_territory_owner(self):
        world=World.__new__(World);world.x0=0;world.z0=0;world.x1=8;world.z1=8;world.owner=np.zeros((4,4),int)
        np.testing.assert_array_equal(world.owner_at([2,2,-.01,8.01],[2,-.01,2,2]),[0,-1,-1,-1])
    def test_short_discovery_branch_keeps_both_endpoints_in_one_route_cell(self):
        world=World.__new__(World);world.x0=0;world.z0=0;world.height=np.zeros((9,9))
        points=world.route([1.,1.],[2.,2.])
        np.testing.assert_array_equal(points,[[1.,1.],[2.,2.]])
    def test_intersecting_road_profiles_have_one_passable_triangle_surface(self):
        z,x=np.indices((45,45));active=(np.abs(x-22)<5)|(np.abs(z-22)<5)
        target=np.where(np.abs(x-22)<5,10.+z*.5,20.+x*.2)
        height=corridor_grade(target,active)
        for dz,dx in ((0,1),(1,0)):
            a=height[:45-dz,:45-dx];b=height[dz:,dx:]
            mask=active[:45-dz,:45-dx]&active[dz:,dx:]
            self.assertLessEqual(np.max(np.abs(a-b)[mask])/2,.45/np.sqrt(2)+1e-6)
        # Input profiles disagree by metres at this busy junction.
        self.assertLess(abs(height[21,22]-height[22,22]),.65)

    def test_bridge_profile_keeps_water_clearance_without_steep_bank_steps(self):
        distance=np.arange(0,101,2.)
        ground=np.where((distance>30)&(distance<70),-8.,10.)
        minimum=np.where((distance>35)&(distance<65),6.,-np.inf)
        result=graded_profile(ground,distance,minimum)
        self.assertTrue(np.all(np.abs(np.diff(result))/np.diff(distance)<=.350001))
        self.assertTrue(np.all(result>=minimum))
        self.assertEqual(result[0],10);self.assertEqual(result[-1],10)

    def test_crossing_centres_identical_and_reverse_triggers_distinct(self):
        world=FlatWorld();link=prepare_contracts(world)[0];a,b=link['ends']
        for left,right in ((a,b),(b,a)):
            arrivals={tuple(global_tile(world,right['region'],lane['arrival'])) for lane in right['lanes']}
            self.assertEqual({tuple(global_tile(world,left['region'],lane['tile'])) for lane in left['lanes']},arrivals)
            self.assertTrue({tuple(l['tile']) for l in right['lanes']}.isdisjoint(tuple(l['arrival']) for l in right['lanes']))

    def test_hidden_halo_is_real_sampled_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bridge.glb';world=FlatWorld();parts=bridge_scene(world,path)
            self.assertEqual(len(parts),2)
            doc,body=S.GR.load(path)
            for part in parts:
                self.assertIn('_StreamThreshold_',part['node'])
                low,high=part['bounds'];self.assertEqual(low[1],2);self.assertEqual(high[1],2)
                self.assertGreater(high[0],20);self.assertLess(low[0],20)
            material=next(m for m in doc['materials'] if m['name']=='threshold_invisible')
            self.assertEqual(material['alphaMode'],'BLEND')

    def test_selection_drops_unselected_geometry_and_preserves_transform(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'source.glb';target=folder/'selected.glb'
            builder=G.GltfBuilder('test');builder.add_material(G.Material('plain'))
            for name in ('Keep','Drop'):
                builder.add_mesh(name,M.box((2,2,2),material='plain'),with_tangents=False)
                builder.add_node(G.Node(name,mesh=name,translation=(3,0,4)))
            builder.write_glb(str(source));doc,body=S.GR.load(source)
            root=next(i for i,n in enumerate(doc['nodes']) if n['name']=='Keep')
            export=S.Exporter(target);export.add(doc,body,[root],transforms={root:[10,0,20]});export.write()
            selected,binary=S.GR.load(target)
            self.assertEqual(len(selected['meshes']),1)
            self.assertNotIn('Drop',{n['name'] for n in selected['nodes']})
            low,high=S.subtree_bounds(selected,binary,selected['scenes'][0]['nodes'][0])
            np.testing.assert_allclose((low+high)/2,[13,0,24])


if __name__=='__main__':unittest.main()
