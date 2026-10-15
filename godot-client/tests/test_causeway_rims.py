from pathlib import Path
from types import SimpleNamespace
import importlib.util,sys,numpy as np
ROOT=Path(__file__).resolve().parents[2];REGIONS=ROOT/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_finishing')]
import connector_finish as F
from amberwood import mesh as M
import causeway_rims as R


def build_case(monkeypatch,clipped=False):
    top=M.quad([[-50,4,-4.25],[1,4,-4.25],[1,4,4.25],[-50,4,4.25]])
    native=M.quad([[-50,4,-3.5],[1,4,-3.5],[1,4,3.5],[-50,4,3.5]])
    rim=F._subtract_native(top,F._triangles([native]))
    old=M.quad([[-3,-1.97,-3.5],[0,-1.97,-3.5],[0,-1.97,3.5],[-3,-1.97,3.5]])
    ground=M.quad([[-50,-2,-20],[0,-2,-20],[0,-2,20],[-50,-2,20]])
    water=M.quad([[-50,0,-20],[0,0,-20],[0,0,20],[-50,0,20]])
    source='Walk_ContinentRoad_test'
    frame={'id':'test','profile':'causeway','anchor':[0,4,0],'outward':[1,0],'deckWidth':7,'sceneNodes':[source]}
    b=SimpleNamespace(terrain_meshes={source:M.merge([rim,old]),'Walk_native':native,'Terrain_bed':ground},
                      water_meshes={'Water':water},streaming_borders=[frame,{'id':'adjacent','profile':'land','sceneNodes':[source]}])
    polygon=[[-50,-20],[0,-20],[0,3.9 if clipped else 20],[-50,3.9 if clipped else 20]]
    monkeypatch.setattr(R.G,'plan',lambda:{'regions':{'test':{'ownershipPolygon':polygon,'translation':[0,0,0]}}})
    monkeypatch.setattr(R.R,'_edge_distance',lambda build,region,xz:np.abs(xz[:,0]))
    return b


def test_added_soffit_and_outward_fascia_leave_original_surface_arrays_unchanged(monkeypatch):
    b=build_case(monkeypatch)
    before={n:m.copy() for bucket in (b.terrain_meshes,b.water_meshes) for n,m in bucket.items()}
    result=R.apply(b,'test');assert result['newWalkingTriangles']==0
    for bucket in (b.terrain_meshes,b.water_meshes):
        for n,m in bucket.items():
            if n not in before:continue
            for field in ('positions','normals','uvs','colors','indices'):np.testing.assert_array_equal(getattr(m,field),getattr(before[n],field))
    body=b.terrain_meshes['Structure_StreamCauseway_test_rim'];tri=F._triangles([body])
    assert np.all(tri[:,:,1]>=3.2-1e-8) and np.all(tri[:,:,1]<=4+1e-8)
    assert np.all(tri[:,:,0]>=-43.25-1e-8) and np.all(tri[:,:,0]<=1e-8)
    assert np.all(np.abs(tri[:,:,2])>=3.5-1e-8)
    assert not np.any(np.all(np.abs(tri[:,:,0])<1e-8,axis=1))
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert normal[:,1].max()<1e-8
    for sign in (-1,1):
        outer=np.all(np.abs(tri[:,:,2]-sign*4.25)<1e-8,axis=1)
        assert outer.any() and np.all(normal[outer,2]*sign>0)
    assert all('Structure_StreamCauseway_test_rim' in s['sceneNodes'] for s in b.streaming_borders)


def test_construction_is_ownership_clipped_before_extrusion(monkeypatch):
    b=build_case(monkeypatch,True);R.apply(b,'test')
    body=b.terrain_meshes['Structure_StreamCauseway_test_rim']
    assert body.positions[:,2].max()<=3.9+1e-8
    assert body.positions[:,0].max()<=1e-8


def test_bottom_winding_is_down_for_reversed_walking_faces(monkeypatch):
    b=build_case(monkeypatch);b.terrain_meshes['Walk_ContinentRoad_test'].flip_winding()
    R.apply(b,'test');tri=F._triangles([b.terrain_meshes['Structure_StreamCauseway_test_rim']])
    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    assert normal[:,1].max()<1e-8 and (normal[:,1]<-1e-6).any()


def test_graded_bank_end_and_actual_mitred_edge_receive_body(monkeypatch):
    b=build_case(monkeypatch)
    # Actual mouth reaches4.5m lateral at the bank bend; its top is graded.
    apron=M.quad([[-43.25,3.46,-4.5],[-42,4,-4.5],[-42,4,4.5],[-43.25,3.46,4.5]])
    b.terrain_meshes['Walk_ContinentRoad_test']=M.merge([b.terrain_meshes['Walk_ContinentRoad_test'],apron])
    R.apply(b,'test');body=b.terrain_meshes['Structure_StreamCauseway_test_rim']
    ray=F.VerticalRayIndex(F._triangles([body]))
    for x,z in ((-42.11,4.39),(-42.22,0.)):
        expected=3.46+(x+43.25)/1.25*.54-.8
        assert abs(ray.top_hit(x,z)-expected)<1e-7


def test_existing_ssar_cap_is_not_duplicated_or_given_interface_wall(monkeypatch):
    b=build_case(monkeypatch)
    full=M.quad([[-43.25,4,-4.25],[-42,4,-4.25],[-42,4,4.25],[-43.25,4,4.25]])
    b.terrain_meshes['Walk_ContinentRoad_test']=M.merge([full,b.terrain_meshes['Walk_ContinentRoad_test']])
    cap=M.quad([[-42.75,3.2,-4.25],[-41.5,3.2,-4.25],[-41.5,3.2,4.25],[-42.75,3.2,4.25]])
    b.terrain_meshes['Structure_WestRuinLanding_Cap']=cap
    saved=cap.copy();R.apply(b,'test')
    for field in ('positions','normals','uvs','colors','indices'):np.testing.assert_array_equal(getattr(cap,field),getattr(saved,field))
    tri=F._triangles([b.terrain_meshes['Structure_StreamCauseway_test_rim']]);ray=F.VerticalRayIndex(tri)
    assert ray.top_hit(-42.5,4.) is None
    assert abs(ray.top_hit(-43.,0.)-3.2)<1e-8
    assert not np.any(np.all(np.abs(tri[:,:,0]+42.75)<1e-8,axis=1))
