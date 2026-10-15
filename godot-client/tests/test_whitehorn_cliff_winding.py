"""White-only fix: single-sided escarpment faces point away from land."""
from pathlib import Path
from types import SimpleNamespace
import ast,sys
from unittest.mock import patch
import numpy as np
import pytest
REGIONS=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REGIONS/'_toolkit'),str(REGIONS/'_outer')]
from amberwood import mesh as M
import outer_aprons as O

def orient():
    # Load the actual regional function without importing unrelated legacy
    # region/layout module globals into another region's test process.
    tree=ast.parse((REGIONS/'whitehorn_range/source/landscape_plan.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_orient_outer_escarpment')
    namespace={'np':np};exec(compile(ast.Module(body=[function],type_ignores=[]),'whitehorn-landscape-plan','exec'),namespace)
    return namespace[function.name]


def cliff():
    floor=M.quad([[0,0,0],[0,0,1],[1,0,1],[1,0,0]])
    _,edges=O._clip_dry(floor,np.array([1.,1.,-1.,-1.]))
    parts=[]
    for a,b in edges:
        c=b.copy();d=a.copy();c[1]-=18;d[1]-=18
        parts.append(M.quad([a,b,c,d]))
    return M.merge(parts)


def apply(mesh, floor=None):
    if floor is None:
        floor=M.quad([[0,0,0],[0,0,1],[.5,0,1],[.5,0,0]])
    b=SimpleNamespace(terrain_meshes={'Terrain_OuterEscarpment_whitehorn_range':mesh,
                                    'Terrain_Base':floor},outer_apron_audit={})
    return orient()(b,None)


def test_actual_clipped_floor_rock_faces_outward_without_moving_vertices_or_uvs():
    mesh=cliff();positions=mesh.positions.copy();uvs=mesh.uvs.copy()
    assert np.all(mesh.normals[:,0]<0)
    assert apply(mesh)==4
    np.testing.assert_array_equal(mesh.positions,positions);np.testing.assert_array_equal(mesh.uvs,uvs)
    triangles=mesh.positions[mesh.indices.reshape(-1,3)]
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    assert np.all(normals[:,0]>0)
    assert np.all(mesh.normals[:,0]>.99)


def test_mixed_source_winding_retains_already_outward_faces_and_is_idempotent():
    mesh=cliff();faces=mesh.indices.reshape(-1,3);faces[:2]=faces[:2][:,[0,2,1]]
    assert apply(mesh)==2
    final=mesh.indices.copy()
    assert apply(mesh)==0
    np.testing.assert_array_equal(mesh.indices,final)


def test_actual_retained_faces_override_disagreeing_nonlinear_field():
    # A nonlinear field can turn within a source triangle, whereas its
    # clipped edge remains straight. The actual retained half is x < .5.
    mesh=cliff()
    with patch.object(O,'_reshape',side_effect=lambda b,s,p:(p,p[:,0]-.5)) as field:
        assert apply(mesh)==4
    field.assert_not_called()
    triangles=mesh.positions[mesh.indices.reshape(-1,3)]
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    assert np.all(normals[:,0]>0)


def test_ambiguous_retained_substrate_fails_instead_of_guessing():
    mesh=cliff();before=mesh.indices.copy()
    floor=M.quad([[0,0,0],[0,0,1],[1,0,1],[1,0,0]])
    with pytest.raises(ValueError,match='ambiguous retained substrate coverage'):
        apply(mesh,floor)
    np.testing.assert_array_equal(mesh.indices,before)
