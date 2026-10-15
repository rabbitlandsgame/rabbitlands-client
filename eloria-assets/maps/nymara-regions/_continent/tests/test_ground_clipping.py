"""Hard ground masks preserve the original weighted triangle field across exact cuts and reframing."""
from pathlib import Path
import sys
from types import SimpleNamespace
import copy
import numpy as np
import pytest
from shapely.geometry import Polygon,Point
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import terrain_export as T
import authoring as A


def test_cut_triangle_interpolates_alpha_height_uv_without_new_fade():
    face=np.array([[[0,2,0],[0,6,4],[4,10,0]]],float)
    uv=np.array([[[0,0],[0,2],[2,0]]],float)
    rgba=np.ones((1,3,4));rgba[0,:,3]=[1,.5,.25]
    mask=Polygon([[1,-1],[3,-1],[3,4],[1,4]])
    out,out_uv,out_rgba=T.clip_weighted_ground_faces(face,uv,rgba,mask)
    assert len(out)>0
    for triangle,triangle_uv,triangle_rgba in zip(out,out_uv,out_rgba):
        basis=np.vstack((face[0][:,[0,2]].T,np.ones(3)))
        bary=np.linalg.solve(basis,np.vstack((triangle[:,[0,2]].T,np.ones(3)))).T
        assert np.allclose(triangle,bary@face[0])
        assert np.allclose(triangle_uv,bary@uv[0])
        assert np.allclose(triangle_rgba,bary@rgba[0])
        assert np.all(triangle_rgba[:,3]>0)
    expected=Polygon(face[0][:,[0,2]]).intersection(mask).area
    assert sum(Polygon(f[:,[0,2]]).area for f in out)==pytest.approx(expected)
    assert np.any(np.isclose(out[:,:,0],1)) and np.any(np.isclose(out[:,:,0],3))


def test_concave_mask_all_fragments_and_unchanged_faces_are_preserved():
    face=np.array([[[0,0,0],[0,0,6],[6,0,0]]],float)
    uv=face[...,[0,2]];rgba=np.ones((1,3,4))
    whole=Polygon([[-1,-1],[8,-1],[8,8],[-1,8]])
    result=T.clip_weighted_ground_faces(face,uv,rgba,whole)
    assert all(np.array_equal(a,b) for a,b in zip(result,(face,uv,rgba)))
    mask=Polygon([[0,0],[4,0],[4,1],[1,1],[1,4],[0,4]])
    out,_,_=T.clip_weighted_ground_faces(face,uv,rgba,mask)
    assert sum(Polygon(f[:,[0,2]]).area for f in out)==pytest.approx(Polygon(face[0][:,[0,2]]).intersection(mask).area)
    assert all(mask.covers(Polygon(f[:,[0,2]])) for f in out)


def world_and_triangles():
    x=np.arange(10.,16.,2.);z=np.arange(20.,26.,2.);gx,gz=np.meshgrid(x,z)
    world=SimpleNamespace(x=x,z=z,gx=gx,gz=gz,height=.3*gx+.7*gz)
    nx=len(x);row,col=np.indices((len(z)-1,len(x)-1));a=row.ravel()*nx+col.ravel()
    tri=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1).reshape(-1,3)
    positions=np.stack([gx,world.height+.006,gz],axis=-1).reshape(-1,3)
    return world,tri,positions


def ground(matrix):
    return {'enabled':True,'id':'paint','shape':'ellipse','matrix':matrix.ravel(order='F').tolist(),
            'size':[5.,3.],'blendWidth':2.,'opacity':.65,'priority':2,
            'surface':{'preset':'Soil','rotationDegrees':0,'materialMode':'surface'}}


def test_reframing_keeps_source_uv_layer_and_original_ellipse_field():
    world,tri,positions=world_and_triangles();matrix=np.eye(4);matrix[[0,2],3]=[2,2]
    original=ground(matrix)
    source=SimpleNamespace(translation=np.array([10.,0.,20.]),document={'terrain':{'previewUvMetresInverse':.17}})
    before=T.ground_region_faces(world,source,original,tri,positions,4)
    moved=copy.deepcopy(original);matrix[[0,2],3]=[4,3];moved['matrix']=matrix.ravel(order='F').tolist()
    moved.update(clipPolygon=[[.5,-20],[20,-20],[20,20],[.5,20]],uvAnchorContinent=[10.,20.],sourceLayerOrdinal=4)
    target=SimpleNamespace(translation=np.array([8.,0.,19.]),document=source.document)
    # Even if the new cell-centre owner contributes no whole triangle, exact mask fragments remain.
    faces,uv,rgba=T.ground_region_faces(world,target,moved,np.empty((0,3),int),positions,0)
    assert len(faces)>0 and faces[:,:,0].min()>=12.5
    for point,point_uv,point_rgba in zip(faces.reshape(-1,3),uv.reshape(-1,2),rgba.reshape(-1,4)):
        matches=[]
        for f,u,c in zip(*before):
            bary=np.linalg.solve(np.vstack((f[:,[0,2]].T,np.ones(3))),np.r_[point[[0,2]],1.])
            if bary.min()>=-1e-9:
                matches.append((bary@f,bary@u,bary@c))
        assert matches
        assert any(np.allclose(point,a) and np.allclose(point_uv,b) and np.allclose(point_rgba,c) for a,b,c in matches)


def test_ground_mask_validation_is_optional_and_fails_closed():
    record=ground(np.eye(4));doc={'groundRegions':[record]}
    A._validate_ground_regions(doc,{})
    good=[[0,0],[4,0],[4,4],[0,4]]
    record.update(clipPolygon=good,uvAnchorContinent=[100,200],sourceLayerOrdinal=4)
    A._validate_ground_regions(doc,{})
    for field,value in [('clipPolygon',[[0,0],[4,4],[0,4],[4,0]]),('clipPolygon',[[0,0],[1,0]]),('clipPolygon',[[0,0],[float('nan'),0],[0,1]]),('sourceLayerOrdinal',127),('sourceLayerOrdinal',True),('uvAnchorContinent',[1,float('inf')])]:
        bad=copy.deepcopy(doc);bad['groundRegions'][0][field]=value
        with pytest.raises(A.AuthoringError):A._validate_ground_regions(bad,{})
    bad=copy.deepcopy(doc);matrix=np.eye(4);matrix[0,1]=.1;bad['groundRegions'][0]['matrix']=matrix.ravel(order='F').tolist()
    with pytest.raises(A.AuthoringError,match='horizontal'):A._validate_ground_regions(bad,{})

def generated_fixture(tmp_path):
    import json,hashlib,shutil
    root=tmp_path/'checkout';rid='fixture';directory=root/'eloria-assets/maps/continent-v2/_continent_v2';directory.mkdir(parents=True)
    real=HERE.parents[3]/'eloria-assets/maps/continent-v2/_continent_v2'
    for name in ('arrivals.py','ownership.py'):shutil.copyfile(real/name,directory/name)
    partition=directory/'partition-inputs/sections_spec.json';partition.parent.mkdir();partition.write_text('{"sections":[]}')
    frame={'origin':[5,5],'cells':[12,12],'translation':[100.,0.,200.]}
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    payload={'schema':'eloria-continent-v2-generated-arrival-v1','map':rid,'id':'generated-arrival-'+rid,
             'position':[.5,2.,-.5],'serverTile':[5,5],'facing':[0,0,-1],'default':True,'generated':True,'frame':frame,
             'provenance':{'algorithm':'nearest-owned-safe-baseline-tile-v1','clientBaseCommit':'a'*40,
                 'sectionsSpecSha256':sha(partition.read_bytes()),'frameSha256':sha(__import__('json').dumps(frame,sort_keys=True,separators=(',',':')).encode()),
                 'sourceMap':'sw_isle','sourceTile':[10,20],'sourceWorldSha256':'a'*64,'sourceCollisionSha256':'a'*64,'sourceServedGridSha256':'a'*64}}
    arrival=root/'eloria-assets/maps/continent-v2'/rid/'content/arrival.json';arrival.parent.mkdir(parents=True);arrival.write_text(json.dumps(payload))
    reference={'path':arrival.relative_to(root).as_posix(),'sha256':sha(arrival.read_bytes())}
    spec_path=root/'godot-client/world_authoring/regions'/rid/'region-authoring-spec.json';spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps({'schema':'eloria-region-authoring-spec-v1','regionId':rid,'gameplay':{'generatedArrival':reference}}))
    stub=arrival.parent.parent/'world.json';stub.write_text(json.dumps({'continentGeography':{'ownershipPolygons':[[[98,198],[102,198],[102,202],[98,202]],[[104,198],[108,198],[108,202],[104,202]]]}}))
    contract=SimpleNamespace(adapter='continent-v2-meshy-v1',spec_path=spec_path,spec_sha256=None,id=rid,
                             server_origin=(5,5),server_cells=(12,12),continent_translation=(100.,0.,200.),
                             runtime_binding_count=0,runtime_point_count=0,existing_marker_binding_count=0)
    doc={'regionId':rid,'objects':[],'gameplay':{k:[] for k in ('spawnPoints','portals','interactives','landmarks','harvestables','npcMarkers','ambientPopulation','runtimePoints','runtimeBindings')},
         'generatedArrival':payload,'sources':{'generatedArrival':reference,'dependencies':[reference],
             'authoringSpec':{'path':spec_path.relative_to(root).as_posix(),'sha256':sha(spec_path.read_bytes())}}}
    return root,doc,contract,arrival


def test_generated_arrival_authorizes_empty_arrays_only_with_full_binding(tmp_path):
    root,doc,contract,arrival=generated_fixture(tmp_path)
    A._validate_gameplay(doc,False,contract)
    for fault in ('missing_dependency','stale_spec','unbound_payload','wrong_frame','bad_tile','mixed_default'):
        bad=copy.deepcopy(doc)
        if fault=='missing_dependency':bad['sources']['dependencies']=[]
        elif fault=='stale_spec':bad['sources']['authoringSpec']['sha256']='0'*64
        elif fault=='unbound_payload':bad['generatedArrival']['position'][0]+=1
        elif fault=='wrong_frame':bad['generatedArrival']['frame']['translation'][0]+=1
        elif fault=='bad_tile':bad['generatedArrival']['serverTile'][0]+=1
        else:bad['gameplay']['spawnPoints']=[{'id':'authored','default':True,'position':[.5,2,-.5],'serverTile':[5,5]}]
        with pytest.raises(A.AuthoringError):A._validate_gameplay(bad,False,contract)
    arrival.write_text(arrival.read_text()+' ')
    with pytest.raises(A.AuthoringError,match='hash changed'):A._validate_gameplay(doc,False,contract)


def test_generated_arrival_does_not_relax_legacy_authored_requirements(tmp_path):
    _,doc,contract,_=generated_fixture(tmp_path)
    with pytest.raises(A.AuthoringError,match='registered continent-v2'):A._validate_gameplay(doc,False,None)
    doc.pop('generatedArrival');doc['sources'].pop('generatedArrival')
    with pytest.raises(A.AuthoringError,match='retain an authored spawn'):A._validate_gameplay(doc,False,None)


def test_v2_empty_binding_seed_exemption_requires_valid_default_and_zero_contract(tmp_path):
    _,doc,contract,_=generated_fixture(tmp_path)
    doc['gameplay'].update(runtimeBindings=[],runtimePoints=[])
    A._validate_gameplay(doc,False,contract)
    for field in ('runtime_binding_count','runtime_point_count','existing_marker_binding_count'):
        bad_contract=copy.copy(contract);setattr(bad_contract,field,1)
        with pytest.raises(A.AuthoringError):
            A._validate_gameplay(doc,False,bad_contract)
    bad=copy.deepcopy(doc)
    bad['gameplay']['runtimePoints']=[{'id':'unused','position':[.5,2,-.5]}]
    with pytest.raises(A.AuthoringError,match='dedicated runtime controls'):
        A._validate_gameplay(bad,False,contract)
    bad=copy.deepcopy(doc);bad['sources']['authoringSpec']['sha256']='0'*64
    with pytest.raises(A.AuthoringError,match='spec source changed'):
        A._validate_gameplay(bad,False,contract)


def test_v2_authored_default_with_no_portals_or_seed_keeps_legacy_requirements(tmp_path):
    import json,hashlib
    _,doc,contract,_=generated_fixture(tmp_path)
    contract.spec_path.write_text(json.dumps({'schema':'eloria-region-authoring-spec-v1','regionId':contract.id,'gameplay':{}}))
    doc['sources']['authoringSpec']['sha256']=hashlib.sha256(contract.spec_path.read_bytes()).hexdigest()
    doc.pop('generatedArrival');doc['sources'].pop('generatedArrival');doc['sources']['dependencies']=[]
    doc['gameplay'].update(spawnPoints=[{'id':'authored','default':True,'position':[.5,2,-.5],'serverTile':[5,5],'facing':[0,0,-1]}],runtimeBindings=[],runtimePoints=[])
    A._validate_gameplay(doc,False,contract)
    bad=copy.deepcopy(doc);bad['gameplay']['spawnPoints'][0]['position'][0]=1.5
    with pytest.raises(A.AuthoringError,match='authoritative local position'):
        A._validate_gameplay(bad,False,contract)
    with pytest.raises(A.AuthoringError,match='authored links'):
        A._validate_gameplay(doc,False,None)
    legacy=copy.deepcopy(doc);legacy['gameplay']['portals']=[{'id':'portal','position':[.5,2,-.5]}]
    with pytest.raises(A.AuthoringError,match='runtimeBindingSeed'):
        A._validate_gameplay(legacy,False,None)


def test_registered_v2_conserved_unbound_runtime_controls_match_the_contract(tmp_path):
    _,doc,contract,_=generated_fixture(tmp_path)
    contract.runtime_point_count=1
    doc['gameplay']['runtimePoints']=[{'id':'hub','position':[.5,2,-.5]}]
    A._validate_gameplay(doc,False,contract)
    A._validate_gameplay(doc,True,contract)
    bad=copy.deepcopy(doc);bad['gameplay']['runtimePoints']=[]
    with pytest.raises(A.AuthoringError,match='dedicated runtime controls'):
        A._validate_gameplay(bad,False,contract)
    bad=copy.deepcopy(doc);bad['gameplay']['runtimePoints'].append({'id':'hub','position':[.5,2,-.5]})
    with pytest.raises(A.AuthoringError):A._validate_gameplay(bad,False,contract)
    bad=copy.deepcopy(doc);bad['gameplay'].pop('runtimeBindings')
    with pytest.raises(A.AuthoringError,match='explicitly record runtimeBindings'):
        A._validate_gameplay(bad,False,contract)
