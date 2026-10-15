"""The local road continuation preserves both ends and all existing surfaces."""
from types import SimpleNamespace
import numpy as np
import pytest
from amberwood.mesh import Mesh
import amber_road_mouth as A


def road():
    p=np.array([[-122.5,45.53,99.],[-122.5,45.53,102.5],[-122.5,45.53,106.],
                [-122.,45.53,99.],[-122.,45.53,102.5],[-122.,45.53,106.]])
    return Mesh(positions=p,indices=np.array([0,1,3,1,4,3,1,2,4,2,5,4]),material='packed_earth_ground')


def test_strip_preserves_literal_edge_and_is_upward():
    r=road();original=r.positions.copy();m=A.make_strip([r]);tri=m.positions[m.indices.reshape(-1,3)]
    np.testing.assert_array_equal(r.positions,original)
    np.testing.assert_allclose(m.positions[m.positions[:,0]==-122.5,1],45.53)
    np.testing.assert_array_equal(m.uvs,m.positions[:,[0,2]]*.28)
    assert np.min(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1])>0
    assert np.isclose(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1].sum()/2,3.5)
    assert m.positions[:,0].min()==-123 and m.positions[:,0].max()==-122.5


def test_only_new_mesh_and_its_membership_are_added():
    r=road();b=SimpleNamespace(terrain_meshes={'Walk_ContinentRoad_'+A.ROAD:r},
        streaming_borders=[{'id':A.ROAD,'anchor':[-122.5,45.5,102.5],'sceneNodes':[]}],notes=[])
    A.apply(b)
    assert b.terrain_meshes['Walk_ContinentRoad_'+A.ROAD] is r
    assert b.streaming_borders[0]['sceneNodes']==[A.NODE]
    with pytest.raises(ValueError,match='twice'):A.apply(b)


def test_missing_gate_edge_is_rejected():
    r=road();r.positions[:,0]+=1
    with pytest.raises(ValueError,match='lost'):A.make_strip([r])
