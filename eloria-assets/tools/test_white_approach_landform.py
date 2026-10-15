"""Regional regressions kept outside the raw geometry certificate inputs."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import sys,json
import numpy as np

REGIONS=Path(__file__).resolve().parents[1]/'maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'whitehorn_range/source'),str(REGIONS/'_toolkit'),str(REGIONS/'_finishing')]
import build_whitehorn
import approach_landform as W
import approach_materials as C
import connector_finish as F
from regionbuild import Placement
import glb_reader as G


def mesh(points,faces):
    p=np.asarray(points,float)
    return F.M.Mesh(positions=p,normals=np.tile([0.,1.,0.],(len(p),1)),uvs=p[:,[0,2]],
                    indices=np.asarray(faces,int).ravel(),colors=np.ones((len(p),4)),material='alpine_snowfield_ground')


def test_broad_refinement_agrees_across_separate_material_stream_cells():
    a=mesh([[-6.,0.,30.],[0.,0.,25.],[0.,0.,35.]],[[0,2,1]])
    b=mesh([[0.,0.,25.],[9.,0.,30.],[0.,0.,35.]],[[0,2,1]])
    roads=[{'stations':[[0.,0.,20.],[0.,0.,40.]]}]
    W._refine(a,roads);W._refine(b,roads)
    def seam(m):return np.unique(m.positions[abs(m.positions[:,0])<1e-12],axis=0)
    np.testing.assert_array_equal(seam(a),seam(b))
    assert len(seam(a))>2
    assert a.triangle_count<1024 and b.triangle_count<1024


def test_only_explicit_unlinked_ornamental_waystones_may_reseat():
    entries=[Placement('Prop_waystone_011','stone',(0,0,0),collides=True),
             Placement('Prop_waystone_012','stone',(1,0,0),collides=True),
             Placement('Landmark_shrine_00','shrine',(2,0,0),landmark='shrine',collides=True)]
    b=SimpleNamespace(placements=entries,landmarks=[],interactives=[{'node':'Prop_waystone_012'}])
    assert W.movable_detail(b)=={'Prop_waystone_011'}
    b.landmarks=[{'node':'Prop_waystone_011'}]
    assert not W.movable_detail(b)


def test_exposed_rock_is_an_exact_face_partition_with_registered_membership():
    p=[[x,40.+x+90.,z] for z in (70.,80.,90.) for x in (-90.,-80.,-70.)]
    faces=[]
    for row in range(2):
        for col in range(2):
            i=row*3+col;faces.extend([[i,i+3,i+1],[i+1,i+3,i+4]])
    ground=mesh(p,faces);old=ground.copy();old.positions[:,1]-=3.
    name='Terrain_Snow_StreamCell_amberwood-whitehorn'
    b=SimpleNamespace(terrain_meshes={name:ground},streaming_borders=[{'id':'amberwood-whitehorn','sceneNodes':[name]}],
       geography_roads=[{'id':'amberwood-whitehorn','stations':[[-70.,40.,20.],[-70.,40.,110.]]},
                        {'id':'whitehorn-mirrorhold','stations':[[-40.,40.,20.],[-40.,40.,110.]]}])
    def faces_of(items):return Counter(t.tobytes() for m in items for t in m.positions[m.indices.reshape(-1,3)])
    before=faces_of([ground]);report=C.apply(b,F.VerticalRayIndex(F._triangles([old])))
    assert report['bedrockFacePieces']>0
    assert faces_of(b.terrain_meshes.values())==before
    for key in report['newNodes']:
        assert key in b.streaming_borders[0]['sceneNodes']
        m=b.terrain_meshes[key];tri=m.positions[m.indices.reshape(-1,3)]
        assert np.all(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]>0)
        assert m.material=='alpine_bedrock_ground'


def test_final_march_sign_record_matches_the_actual_pole_foot_and_ground():
    package=REGIONS/'whitehorn_range'
    manifest=json.loads((package/'world.json').read_text(encoding='utf-8'))
    marker=next(r for r in manifest['landmarks'] if r['id']=='march-south-gate')
    doc,body=G.load(package/'world.glb');_,parents=G.hierarchy(doc)
    selected=[]
    for i,node in enumerate(doc['nodes']):
        if 'mesh' not in node:continue
        index=i
        while True:
            if doc['nodes'][index].get('name')=='March_south_gate_Signpost':selected.append(i);break
            if index not in parents:break
            index=parents[index]
    assert selected
    actual=G.triangles(doc,body,selected)
    assert abs(float(actual[:,:,1].min())-marker['position'][1])<1e-4
    base=[i for i,n in enumerate(doc['nodes']) if 'mesh' in n and F._base(n.get('name',''))]
    ground=F.VerticalRayIndex(G.triangles(doc,body,base)).top_hit(marker['position'][0],marker['position'][2])
    assert ground is not None and abs(marker['position'][1]-ground-.02)<1e-4
