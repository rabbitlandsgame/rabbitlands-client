"""Geometric ferry candidate selection must leave the composed world unchanged."""
from pathlib import Path
import copy
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import build_continent as B
import ferry_export as F
from world_layout import World


class Coast:
    ids=['port']
    prepare_quay_court=World.prepare_quay_court
    hub=World.hub

    def __init__(self,extent=48):
        self.plan={}
        self.x=np.arange(0.,42.,2.);self.z=np.arange(0.,extent+2.,2.)
        self.gx,self.gz=np.meshgrid(self.x,self.z)
        self.height=np.where(self.gx>=20.,-2.,1.)
        self.owner=np.zeros((len(self.z)-1,len(self.x)-1),int)
        self.obstacles=np.zeros_like(self.height,bool)
        self.ferry_exclusion=np.zeros_like(self.height,bool)
        self.water={'sea_mask':self.gx>=20.,'mask':self.gx>=20.}
        self.regions={'port':{'center':[16.,extent//2//2*2.]}}
        self.quay_contacts=[]

    def height_at(self,x,z):
        return self.height[int(z/2),int(x/2)]


def test_rejects_first_unbuildable_site_uses_separated_candidate_and_rolls_back(monkeypatch):
    world=Coast();original=world.height;before=original.copy();calls=[]
    world.quay_contacts=[{'center':[0.,0.],'elevation':2.}]
    saved=copy.deepcopy(world.quay_contacts)
    def fit(candidate_world,point,region):
        calls.append(np.array(point))
        assert region=='port'
        assert len(candidate_world.quay_contacts)==len(saved)+1
        assert candidate_world.height is not original
        assert candidate_world.height_at(*point)>=1.8
        if len(calls)==1:raise ValueError('bank is dry but whole mooring does not fit')
        return {'minimumBoatDepth':1.4,'contactError':.025}
    monkeypatch.setattr(F,'fit_landing',fit)
    result=B.ferry_landing(world,'port',[40.,24.])
    assert len(calls)==2 and np.array_equal(result,calls[1])
    assert np.linalg.norm(calls[1]-calls[0])>=6
    assert world.height is original and np.array_equal(original,before)
    assert world.quay_contacts==saved
    assert world.ferry_selection==[{'region':'port','position':result.tolist(),
        'candidatesTried':2,'mooringDepth':1.4,'contactError':.025}]


def test_existing_berths_and_retained_causeways_are_excluded_before_fit(monkeypatch):
    world=Coast(100);world.quay_contacts=[{'center':[16.,50.],'elevation':1.8}]
    world.ferry_exclusion=world.gz>50.
    calls=[]
    def fit(candidate_world,point,region):
        calls.append(np.array(point))
        assert np.linalg.norm(point-[16.,50.])>=20.
        assert point[1]<=50.
        return {'minimumBoatDepth':1.,'contactError':.02}
    monkeypatch.setattr(F,'fit_landing',fit)
    result=B.ferry_landing(world,'port',[40.,50.])
    assert len(calls)==1
    assert np.linalg.norm(result-[16.,50.])>=20
    assert len(world.quay_contacts)==1


def test_all_failed_candidates_are_bounded_and_restore_world(monkeypatch):
    world=Coast(1000);original=world.height;before=original.copy();calls=[]
    def reject(candidate_world,point,region):
        assert len(candidate_world.quay_contacts)==1
        calls.append(np.array(point))
        raise ValueError('no space for complete hull')
    monkeypatch.setattr(F,'fit_landing',reject)
    with pytest.raises(ValueError,match='none of 64 ranked shoreline sites'):
        B.ferry_landing(world,'port',[40.,500.])
    assert len(calls)==64
    distance=np.linalg.norm(np.array(calls)[:,None,:]-np.array(calls)[None,:,:],axis=2)
    assert np.min(distance+np.eye(len(calls))*10000)>=6.
    assert world.height is original and np.array_equal(original,before)
    assert world.quay_contacts==[] and not hasattr(world,'ferry_selection')


def test_unexpected_geometry_error_rolls_back_without_concealing_it(monkeypatch):
    world=Coast();original=world.height;before=original.copy()
    def broken(candidate_world,point,region):
        raise RuntimeError('malformed source geometry')
    monkeypatch.setattr(F,'fit_landing',broken)
    with pytest.raises(RuntimeError,match='malformed source geometry'):
        B.ferry_landing(world,'port',[40.,24.])
    assert world.height is original and np.array_equal(original,before)
    assert world.quay_contacts==[] and not hasattr(world,'ferry_selection')


def test_no_coast_does_not_trial_any_geometry(monkeypatch):
    world=Coast();world.obstacles[:]=True
    def unexpected(*args):raise AssertionError('no coast must not call the fitter')
    monkeypatch.setattr(F,'fit_landing',unexpected)
    with pytest.raises(ValueError,match='no coast for ferry landing'):
        B.ferry_landing(world,'port',[40.,24.])
    assert world.quay_contacts==[]


def _saved_snapshot(region, connection, controls):
    return SimpleNamespace(translation=np.zeros(3),document={
        'regionId':region,
        'authority':{'ownedFerryConnectionIds':[connection]},
        'replacements':{'ferryConnectionIds':[connection]},
        'objects':controls})


def _saved_control(connection, landing):
    matrix=np.eye(4);matrix[:3,3]=landing
    return {'id':'saved-a-quay','matrix':matrix.reshape(-1,order='F').tolist(),
            'metadata':{'authoredFerryQuay':{
                'connectionIds':[connection],'walkNode':'Walk_FerryQuay_a_00',
                'localLanding':[0.,0.,0.]}}}


def test_saved_side_uses_exact_endpoint_and_existing_approach_while_other_side_stays_procedural(monkeypatch):
    connection='a--b';link={'id':connection,'type':'ferry','regions':['a','b']}
    class Mixed:
        connections=[link]
        regions={'a':{'center':[0.,0.]},'b':{'center':[100.,0.]}}
        roads=[{'id':connection+'-a','points':'saved'}]
        authoring_snapshots={'a':_saved_snapshot('a',connection,
            [_saved_control(connection,[4.,1.,6.])])}
        def __init__(self):self.courts=[];self.added=[]
        def prepare_quay_court(self,point):self.courts.append(np.asarray(point).tolist())
        def hub(self,region):return np.array([0.,0.])
        def route(self,*args,**kwargs):return np.array([[0.,0.],[20.,30.]])
        def add_road(self,path,**kwargs):self.added.append(kwargs['name'])
    world=Mixed();fits=[];remembered=[]
    monkeypatch.setattr(B,'ferry_landing',lambda candidate,region,toward:np.array([20.,30.]))
    def fit(candidate,landing,region,**kwargs):
        fits.append((region,np.asarray(landing).tolist(),list(kwargs.get('ignore_connection_ids',()))))
        return {'region':region,'landing':np.asarray(landing,float),'stations':np.array([0.]),
                'heights':np.array([1.]),'contactError':.02,'maximumGrade':.2}
    monkeypatch.setattr(F,'fit_landing',fit)
    import ferry_support as S
    monkeypatch.setattr(S,'restore_selected_shores',lambda candidate:None)
    monkeypatch.setattr(S,'remember_ferry_fit',lambda candidate,value:remembered.append(value['region']))
    resolved=B.resolve_saved_ferry_connections(world)
    B.prepare_ferry_connection(world,link,resolved[connection])
    assert link['landings']==[[4.,6.],[20.,30.]]
    assert fits==[('a',[4.,6.],[connection]),('b',[20.,30.],[])]
    assert world.courts==[[20.,30.]] and world.added==[connection+'-b']
    assert world.roads==[{'id':connection+'-a','points':'saved'}]
    assert remembered==['a','b']
    record=next(row for row in world.saved_ferry_handoff if row.get('region')=='a')
    assert record['landing']==[4.,6.] and record['landingError']==0.


def test_deleted_saved_endpoint_disables_connection_before_any_shore_mutation(monkeypatch):
    connection='a--b';link={'id':connection,'type':'ferry','regions':['a','b']}
    world=SimpleNamespace(connections=[link],authoring_snapshots={
        'a':_saved_snapshot('a',connection,[])})
    monkeypatch.setattr(B,'ferry_landing',lambda *args:pytest.fail('deleted ferry must not select a shore'))
    resolved=B.resolve_saved_ferry_connections(world)
    assert resolved=={} and world.connections==[]
    assert world.saved_ferry_handoff==[{'id':connection,'status':'saved-deleted','regions':['a']}]


def test_ambiguous_saved_endpoint_fails_before_shore_selection(monkeypatch):
    connection='a--b';link={'id':connection,'type':'ferry','regions':['a','b']}
    controls=[_saved_control(connection,[4.,1.,6.]),
              dict(_saved_control(connection,[4.,1.,6.]),id='duplicate-quay')]
    world=SimpleNamespace(connections=[link],authoring_snapshots={
        'a':_saved_snapshot('a',connection,controls)})
    monkeypatch.setattr(B,'ferry_landing',lambda *args:pytest.fail('ambiguous ferry must not select a shore'))
    with pytest.raises(ValueError,match='duplicate saved ferry quay controls'):
        B.resolve_saved_ferry_connections(world)
