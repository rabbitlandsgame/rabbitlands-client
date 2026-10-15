"""Budget planning preserves positions and refuses irreducible dense content."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import chunk_budget as B


def test_phase_splits_dense_content_without_moving_it():
    points=np.repeat([[0.,0.],[2.,0.],[0.,2.],[2.,2.]],100,axis=0)
    before=points.copy()
    origin,record=B.choose_origin(points,np.ones(400),np.full(400,1000),[-50,-50],lattice=-1023.0)
    keys=np.floor((points-origin)/96).astype(int)
    _,counts=np.unique(keys,axis=0,return_counts=True)
    assert counts.max()==100
    assert record['maximumPlacements']==100
    assert record['maximumTriangles']==100000
    np.testing.assert_array_equal(points,before)
    assert B.choose_origin(points,np.ones(400),np.full(400,1000),[-50,-50])==(origin,record)


def test_irreducible_density_is_refused():
    with pytest.raises(ValueError,match='no legal 96 m chunk phase'):
        B.choose_origin(np.zeros((241,2)),np.ones(241),np.ones(241),[-50,-50])


def test_instanced_triangles_are_counted_per_occurrence():
    document={'nodes':[{'children':[1,2]},{'mesh':0},{'mesh':0}],
              'meshes':[{'primitives':[{'indices':0,'attributes':{'POSITION':1}}]}],
              'accessors':[{'count':600},{'count':300}]}
    assert B.subtree_triangles(document,0)==400


def test_invalid_metrics_are_refused():
    with pytest.raises(ValueError,match='invalid chunk budget samples'):
        B.choose_origin([[float('nan'),0]],[1],[1],[0,0])
