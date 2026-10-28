"""Initial attachment binding keeps local rows exact despite parent rounding."""
from types import SimpleNamespace
import numpy as np
import pytest
from video_motion import blender_vertex_identity as identity


class Rows:
    def __init__(self, values): self.values = np.asarray(values, np.float32)
    def __len__(self): return len(self.values)
    def foreach_get(self, name, target): target[:] = self.values.ravel()


def bind(monkeypatch, *, depth=8, world_error=0., local_error=0.):
    positions = np.array([[.1,.2,.3], [.3,.4,.5], [.7,.8,.9]], np.float32)
    nodes = [{'children':[i+1]} for i in range(depth-1)] + [{'mesh':0,'name':'Sword'}]
    doc = {'accessors':[{'count':3}],'nodes':nodes,'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}]}
    monkeypatch.setattr(identity, 'document', lambda path: (doc,b''))
    monkeypatch.setattr(identity, 'array', lambda *args: positions.astype(float))
    local = (positions @ identity._C.T).astype(np.float32);local[0,0] += local_error
    matrix=np.eye(4);matrix[0,3]=world_error
    ob=SimpleNamespace(type='MESH',name='Sword',as_pointer=lambda:1,
        matrix_world=matrix,data=SimpleNamespace(vertices=Rows(local),loops=Rows([]),shape_keys=None))
    return identity.imported_bindings('unused',[ob])


def test_composed_attachment_keeps_exact_local_rows(monkeypatch):
    _,_,records=bind(monkeypatch,depth=8,world_error=8e-6)
    assert records[0]['rest_composition_steps']==8
    assert records[0]['basis_world_error'] < records[0]['position_budget']


def test_one_node_does_not_receive_deep_chain_budget(monkeypatch):
    with pytest.raises(AssertionError,match='Unproved Blender mesh identity'):
        bind(monkeypatch,depth=1,world_error=8e-6)


def test_wrong_local_vertex_rejected_inside_world_budget(monkeypatch):
    with pytest.raises(AssertionError,match='Unproved Blender mesh identity'):
        bind(monkeypatch,depth=8,local_error=1e-7)


def test_world_mismatch_beyond_composed_budget_rejected(monkeypatch):
    with pytest.raises(AssertionError,match='Unproved Blender mesh identity'):
        bind(monkeypatch,depth=8,world_error=1e-3)


