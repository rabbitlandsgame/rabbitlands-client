"""Far Amberwood must reduce detail without changing its finished landscape."""
from pathlib import Path
from types import SimpleNamespace
import copy
import hashlib
import json
import sys
from collections import Counter

import numpy as np

CLIENT=Path(__file__).resolve().parents[2]
REGIONS=CLIENT/'eloria-assets/maps/nymara-regions'
PACKAGE=REGIONS/'amberwood'
sys.path[:0]=[str(PACKAGE/'source'),str(REGIONS/'_toolkit')]
import distant_landscape as D
from amberwood import mesh as M
from amberwood import populate
from regionbuild import Placement,RegionBuild
import glb_reader as G


def example_build():
    b=RegionBuild(terrain=SimpleNamespace(height=np.array([[3.,4.],[4.,5.]])))
    b.terrain_meshes={'Terrain_Forest':M.box((4.,1.,4.)),
                      'Walk_ContinentRoad_test':M.box((7.,.2,8.),center=(0.,4.,0.))}
    b.water_meshes={'Water_Stream':M.box((2.,.01,10.),center=(0.,2.,0.))}
    b.meshes['prop']=M.box((1.,2.,1.))
    b.placements=[Placement('Landmark_Well','prop',(4.,5.,6.),rotation_y=.47,scale=1.3,landmark='well'),
                  Placement('Rock_0001','prop',(1.,2.,3.),kind='rock'),
                  Placement('Rock_0002','prop',(2.,3.,4.),kind='rock',landmark='stone'),
                  Placement('Mushrooms_0003','prop',(3.,4.,5.),kind='mushrooms'),
                  Placement('FallenLog_0004','prop',(4.,5.,6.),kind='fallenlog'),
                  Placement('Stump_0005','prop',(5.,6.,7.),kind='stump'),
                  Placement('LeafDrift_0006','prop',(6.,7.,8.),kind='leafdrift')]
    b.landmarks=[{'id':'well','node':'Landmark_Well'}]
    b.harvestables=[{'id':'fungus','node':'Mushrooms_0003'}]
    b.interactives=[{'id':'log','node':'FallenLog_0004'}]
    b.portals=[{'id':'stump-hatch','node':'Stump_0005'}]
    b.npc_markers=[{'id':'keeper','position':[4.,5.,6.]}]
    b.spawns=[{'id':'default','position':[0.,4.,0.]}]
    b.geography_roads=[{'id':'test','stations':[[0.,4.,0.],[10.,4.,0.]]}]
    b.streaming_borders=[{'id':'test','sceneNodes':['Terrain_Forest','Walk_ContinentRoad_test']}]
    return b


def assert_mesh_equal(a,b):
    for field in ('positions','normals','uvs','indices','colors'):
        first,last=getattr(a,field),getattr(b,field)
        if first is None:assert last is None
        else:np.testing.assert_array_equal(first,last)
    assert a.material==b.material


def test_derivation_is_pure_and_preserves_finished_surface_arrays_and_metadata():
    main=example_build();before=copy.deepcopy(main);far=D.derive(main)
    for bucket in ('terrain_meshes','water_meshes'):
        a,b=getattr(main,bucket),getattr(far,bucket)
        assert a.keys()==b.keys()
        for name in a:
            assert_mesh_equal(a[name],b[name]);assert_mesh_equal(a[name],getattr(before,bucket)[name])
            assert not np.shares_memory(a[name].positions,b[name].positions)
    np.testing.assert_array_equal(main.terrain.height,far.terrain.height)
    for field in ('landmarks','interactives','harvestables','portals','npc_markers','spawns','geography_roads','streaming_borders'):
        assert getattr(main,field)==getattr(far,field)==getattr(before,field)
    assert main.placements==before.placements and main.notes==before.notes
    far.terrain.height[0,0]=100.
    assert main.terrain.height[0,0]==3.


def test_only_unlinked_ground_detail_is_omitted_and_retained_poses_are_exact():
    main=example_build();far=D.derive(main)
    old={p.node:p for p in main.placements};new={p.node:p for p in far.placements}
    assert set(old)-set(new)=={'Rock_0001','LeafDrift_0006'}
    assert far.distant_omissions==['LeafDrift_0006','Rock_0001']
    for name,p in new.items():assert vars(p)==vars(old[name])
    assert set(far.meshes)=={p.mesh for p in far.placements}


def test_real_low_tree_recipes_are_deterministic_and_do_not_move_their_roots():
    main=example_build()
    wood,canopy=populate.ensure_tree_meshes(main,'amber_oak',2,'high')
    main.placements.extend([Placement('Tree_0001_wood',wood,(7.,8.,9.),rotation_y=.7,scale=1.2,kind='tree'),
                            Placement('Tree_0001_canopy',canopy,(7.,8.,9.),rotation_y=.7,scale=1.2,kind='foliage')])
    original={n:copy.deepcopy(m) for n,m in main.meshes.items()}
    first,second=D.derive(main),D.derive(main)
    assert first.placements==second.placements
    for name in first.meshes:assert_mesh_equal(first.meshes[name],second.meshes[name])
    for name in original:assert_mesh_equal(main.meshes[name],original[name])
    for p in first.placements:
        if p.node.startswith('Tree_'):
            assert '_low_' in p.mesh
            assert p.position==(7.,8.,9.) and p.rotation_y==.7 and p.scale==1.2


def emitted_pair():
    manifest=json.loads((PACKAGE/'world.json').read_text(encoding='utf-8'))
    relative=Path(D.__file__).relative_to(CLIENT).as_posix()
    assert manifest['authoredGeometry']['inputs'][relative]==hashlib.sha256(Path(D.__file__).read_bytes()).hexdigest(), 'Run against the completed certified build, not a prior package.'
    return manifest,G.load(PACKAGE/'world.glb'),G.load(PACKAGE/'world-lod2.glb')


def surface_arrays(document,body):
    result={}
    for node in document['nodes']:
        name=node.get('name','')
        if 'mesh' not in node or not name.startswith(('Terrain_','Walk_','Water_','Backdrop_','Structure_Stream')):continue
        assert name not in result,name
        primitives=[]
        for p in document['meshes'][node['mesh']]['primitives']:
            arrays={k:G.accessor(document,body,v) for k,v in p['attributes'].items() if k in ('POSITION','NORMAL','TEXCOORD_0','COLOR_0')}
            if 'indices' in p:arrays['indices']=G.accessor(document,body,p['indices'])
            primitives.append(arrays)
        result[name]=(G.local_matrix(node),primitives)
    return result


def _roundoff_collinear(points):
    points=np.asarray(points,dtype=np.float64)
    lengths=np.array([np.linalg.norm(points[b]-points[a]) for a,b in ((0,1),(1,2),(2,0))])
    area2=float(np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0])))
    longest=float(lengths.max())
    ulp=float(abs(np.spacing(points.astype(np.float32))).max())
    # A float64-collinear face can acquire a tiny apparent area when the
    # first GLB rounds it to float32. The second prepare drops that face.
    # Require its thickness to be below float32 coordinate resolution, not
    # a blanket small-area exemption for arbitrary missing geometry.
    return area2==0. or (longest>16*ulp and area2/longest<=2*ulp)


def emitted_surface_report():
    _,main,far=emitted_pair();a,b=surface_arrays(*main),surface_arrays(*far)
    assert a.keys()==b.keys() and a
    assert any(n.startswith('Water_') for n in a)
    assert any(n.startswith('Walk_ContinentRoad_') for n in a)
    differences=[];matched=0
    for name in a:
        np.testing.assert_array_equal(a[name][0],b[name][0],err_msg=name)
        assert len(a[name][1])==len(b[name][1]),name
        for first,last in zip(a[name][1],b[name][1]):
            assert first.keys()==last.keys(),name
            def indexed(d):
                indices=d['indices'].reshape(-1,3)
                data={k:d[k][indices] for k in sorted(d) if k!='indices'}
                keys=[b''.join(data[k][i].tobytes() for k in data) for i in range(len(indices))]
                return Counter(keys),dict(zip(keys,data['POSITION']))
            x,xp=indexed(first);y,yp=indexed(last);matched+=sum((x&y).values())
            for side,extra,positions in (('main',x-y,xp),('far',y-x,yp)):
                for key,count in extra.items():
                    tri=positions[key]
                    assert _roundoff_collinear(tri),f'{name}: {side} changed a real surface: {tri}'
                    area=float(np.linalg.norm(np.cross(tri[1].astype(float)-tri[0],tri[2].astype(float)-tri[0]))*.5)
                    differences.append({'node':name,'tier':side,'count':count,'areaSquareMetres':area,'triangle':tri.tolist()})
    return {'matchedMeshNodes':len(a),'matchedIndexedFaces':matched,'roundoffCollinearOnly':differences}


def test_emitted_main_and_far_keep_exact_terrain_water_and_walking_arrays():
    emitted_surface_report()


def test_collinearity_filter_rejects_small_real_triangles():
    assert not _roundoff_collinear(np.array([[1.,2.,3.],[1.001,2.,3.],[1.,2.,3.001]]))
    assert _roundoff_collinear(np.array([[1.,2.,3.],[2.,2.,3.],[3.,2.,3.]]))


def emitted_pose_report():
    manifest,(main,_),(far,_)=emitted_pair()
    def poses(doc):
        matrices,parents=G.hierarchy(doc);result={}
        for i,n in enumerate(doc['nodes']):
            if i in parents and doc['nodes'][parents[i]].get('name') in ('Group_Forest','Group_Props','Group_Structures'):
                assert n['name'] not in result,n['name']
                result[n['name']]=matrices[i]
        return result
    a,b=poses(main),poses(far)
    assert b.keys()<=a.keys()
    for name in b:np.testing.assert_array_equal(a[name],b[name],err_msg=name)
    linked={r['node'] for key in ('landmarks','interactives','harvestables','portals','npcMarkers','spawnPoints') for r in manifest.get(key,[]) if r.get('node')}
    for name in linked & a.keys():
        assert name in b,f'Linked node disappeared in distant tier: {name}'
    landmark_nodes={r['node'] for r in manifest['landmarks'] if r.get('node')}
    assert landmark_nodes and landmark_nodes<=a.keys(),landmark_nodes-a.keys()
    assert landmark_nodes<=b.keys(),landmark_nodes-b.keys()
    return {'mainPlacements':len(a),'farPlacements':len(b),'exactRetainedWorldPoses':len(b),
            'retainedLandmarkNodes':sorted(landmark_nodes),'omittedPlacementNodes':sorted(a.keys()-b.keys()),
            'linkedPlacementNodesPreserved':sorted(linked&a.keys())}


def test_emitted_landmarks_and_all_retained_placement_world_poses_agree():
    emitted_pose_report()
