"""A narrow village street reaches every porch without crossing house interiors."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest
from scipy.ndimage import label
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manymouth_access as A


def rectangle(lo,hi,level):
    a,b,c,d=np.array([[lo[0],level,lo[1]],[hi[0],level,lo[1]],
        [lo[0],level,hi[1]],[hi[0],level,hi[1]]])
    return np.array([[a,c,b],[b,c,d]])


def hamlet(monkeypatch):
    level=4.15;objects=[]
    def add(name,x,z,half,collides=False):
        lo=np.array([x-half[0],level-2,z-half[1]]);hi=np.array([x+half[0],level,z+half[1]])
        objects.append({'node':name,'assembly':A.REGION+'.paddy_hamlet',
            'low':lo,'high':hi,'collides':collides,'floors':rectangle(lo[[0,2]],hi[[0,2]],level)})
    for i in range(8):
        sign=1 if i%2==0 else -1;z=(i//2)*10
        add(f'paddy_hamlet_house_{i:02d}',sign*7,z,[2,3],True)
        add(f'paddy_hamlet_porch_{i:02d}',sign*3.5,z,[1.5,1.1])
    add('Landing_paddy_hamlet',0,-8,[2,2])
    content=SimpleNamespace(objects=objects,documents={A.REGION:({'nodes':[]},b'')},
        assembly_records={A.REGION+'.paddy_hamlet':{'translation':[0,2.4,0]}})
    world=SimpleNamespace(ids=[A.REGION],owner_at=lambda x,z:np.zeros_like(x,int))
    monkeypatch.setattr(A.D,'_triangles',lambda content,obj,**kwargs:obj['floors'])
    return world,content


def test_all_eight_real_porches_and_landing_connect_on_one_narrow_floor(monkeypatch):
    world,content=hamlet(monkeypatch)
    faces,paths,level,report=A.paddy_faces(world,content)
    assert level==4.15 and len(paths)==12 and len(report['porches'])==8
    np.testing.assert_allclose(faces[:,:,1],4.15,atol=1e-6,rtol=0)
    existing=np.concatenate([o['floors'] for o in content.objects if not o['collides']])
    cover,_=A.S.GR.rasterise(np.concatenate([faces,existing]),80,200,-10,36,.25)
    component,_=label(cover)
    stations=report['porches']+[report['landing']]
    labels=[component[int((36-z)/.25),int((x+10)/.25)] for x,z in stations]
    assert len(set(labels))==1 and labels[0]!=0
    # The busiest shared spine remains2.6m wide between porch branches.
    row=cover[int((36-5)/.25)]
    assert 9<=int(row.sum())<=12


def test_new_floor_avoids_all_house_bodies_and_coplanar_existing_porches(monkeypatch):
    world,content=hamlet(monkeypatch)
    faces,_,_,_=A.paddy_faces(world,content)
    centroids=faces[:,:,[0,2]].mean(axis=1)
    for obj in content.objects:
        lo,hi=obj['low'][[0,2]],obj['high'][[0,2]]
        assert not np.any(np.all((centroids>lo+1e-5)&(centroids<hi-1e-5),axis=1))
    fascia=A.boardwalk_fascia(faces,'timber')
    assert fascia.positions[:,1].max()<faces[:,:,1].min()
    assert np.isfinite(fascia.normals).all()


def test_missing_porch_or_changed_floor_datum_fails_closed(monkeypatch):
    world,content=hamlet(monkeypatch)
    saved=content.objects.pop()
    with pytest.raises(ValueError,match='eight rigid houses'):
        A.paddy_faces(world,content)
    content.objects.append(saved)
    content.objects[1]['floors'][:,:,1]+=.25
    with pytest.raises(ValueError,match='shared street datum'):
        A.paddy_faces(world,content)
