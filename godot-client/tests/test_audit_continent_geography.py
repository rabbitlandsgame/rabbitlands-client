"""Independent emitted-geometry audit: reject concave leaks and actor offsets."""
from pathlib import Path
import json
import sys
from types import SimpleNamespace
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'eloria-assets/tools'))
import audit_continent_geography as A


def test_chunk_mode_dispatches_to_whole_continent_audit_with_collision_required(tmp_path, monkeypatch):
    geography = tmp_path / 'eloria-assets/maps/nymara-regions/continent-geography.json'
    geography.parent.mkdir(parents=True)
    geography.write_text(json.dumps({'geometryMode': 'continent-chunks-v1', 'regions': {'test': {}}}))
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return {'verified': 'independent shared-continent auditor'}
    monkeypatch.setitem(sys.modules, 'audit_continent', SimpleNamespace(run=run))
    server, report = tmp_path / 'server', tmp_path / 'report.json'
    assert A.run(tmp_path, report, server=server)['verified'] == 'independent shared-continent auditor'
    assert calls == [((tmp_path, geography.parent / '_continent/generated', report, server.resolve()), {'require_collision': True})]
    with pytest.raises(ValueError, match='audited as a whole'):
        A.run(tmp_path, report, selected=['test'])
    assert len(calls) == 1


def test_concave_triangle_leak_with_all_vertices_and_centroid_inside():
    polygon=[[0,0],[10,0],[10,4],[4,4],[4,10],[0,10]]
    triangle=np.array([[[0,2,0],[10,2,0],[0,2,10]]],float)
    assert A.contains(triangle[0,:,[0,2]].T,polygon).all()
    assert A.contains([[10/3,10/3]],polygon).all()
    result=A.projected_outside(triangle,A.ownership_rectangles(polygon))
    assert result['outsideProjectedArea']==pytest.approx(2.)
    assert result['outsideTriangles']==1


def test_exact_shared_boundary_has_zero_overlap_but_small_strip_is_detected():
    left=A.ownership_rectangles([[0,0],[4,0],[4,10],[0,10]])
    right=A.ownership_rectangles([[4,0],[10,0],[10,10],[4,10]])
    assert A.overlap_area(left,right)==0
    shifted=right.copy();shifted[:,[0,2]]-=.25
    assert A.overlap_area(left,shifted)==pytest.approx(2.5)


def test_ancestry_retains_grouped_walk_mesh_and_detects_paint():
    document={'nodes':[{'name':'Walk_native','children':[1]},
        {'name':'Mesh_0','mesh':0},{'name':'Terrain_native_StreamCollar_edge_Turf','children':[3]},
        {'name':'Mesh_1','mesh':1}]}
    paths=A.ancestry(document)
    assert any(n.startswith('Walk_') for n in paths[1])
    assert not A.is_paint(paths[1])
    assert A.is_paint(paths[3])


def test_stream_inventory_detects_fully_clipped_water_without_discarding_live_groups():
    manifest = {'streamingBorders':[{'id':'north-road',
        'sceneNodes':['Water_UpperFall', 'Water_LowerPool', 'Walk_Group']} ]}
    scene = {'nodes':[{'name':'Water_LowerPool','mesh':0},
                      {'name':'Walk_Group','children':[2]}, {'name':'Mesh_0','mesh':1}]}
    assert A.missing_stream_members(manifest, scene) == {'north-road':['Water_UpperFall']}
    manifest['streamingBorders'][0]['sceneNodes'].remove('Water_UpperFall')
    assert A.missing_stream_members(manifest, scene) == {}


def test_published_opposite_portals_preserve_exact_actor_global_coordinate(tmp_path):
    path=tmp_path/'maps.txt';path.write_text('portal | a | 11 | 20 | b | 31 | 40\n',encoding='utf-8')
    arrival=A.parse_portals(path)[('a',11,20,'b')]
    first={'coordinateTransform':{'serverOrigin':[10,30]}}
    second={'coordinateTransform':{'serverOrigin':[40,50]}}
    a=A.tile_local((11,20),first)+[100,200]
    b=A.tile_local(arrival,second)+[110,200]
    assert a.tolist()==b.tolist()==[101.5,209.5]
    assert not np.array_equal(A.tile_local((30,40),second)+[110,200],a)


def test_conflicting_published_arrival_is_rejected(tmp_path):
    path=tmp_path/'maps.txt';path.write_text('portal | a | 1 | 2 | b | 3 | 4\nportal | a | 1 | 2 | b | 5 | 6\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Conflicting portal'):A.parse_portals(path)


def test_secret_object_rows_do_not_replace_automatic_crossing_proof(tmp_path):
    path=tmp_path/'maps.txt'
    path.write_text('portal | a | 11 | 20 | b | 31 | 40 # ordinary crossing\n'
                    'portal | a | 501 | 11 | 20 | b | 9 | 10 # object-only exit\n'
                    'portal | a | 507 | 15 | 22 | vault_secrets | 27 | 26\n',encoding='utf-8')
    assert A.parse_portals(path)=={('a',11,20,'b'):(31,40)}


def test_malformed_object_bound_portal_is_not_silently_ignored(tmp_path):
    path=tmp_path/'maps.txt'
    path.write_text('portal | a | invalid-object | 11 | 20 | vault_secrets | 27 | 26\n',encoding='utf-8')
    with pytest.raises(ValueError):A.parse_portals(path)


def test_owned_surface_includes_bridge_parapet_but_excludes_threshold_and_whole_tree():
    assert A.owned_surface(['Structure_StreamCauseway_pale_ashlar','Group_Terrain','Region'])
    assert not A.owned_surface(['Walk_StreamThreshold_road','Group_Terrain','Region'])
    assert not A.owned_surface(['Canopy','Tree_7','Group_Forest','Region'])


def test_road_step_requires_both_directions_and_actual_occupancy():
    class Movement:
        def can_walk_step(self,region,start,end):
            return start[0]<end[0]
    # Two standable tiles still fail if the production step mask rejects a leg.
    assert not A.static_step(Movement(),'test',(1,1),(2,1),set())
    class OpenMovement:
        def can_walk_step(self,*args):return True
    assert A.static_step(OpenMovement(),'test',(1,1),(2,1),set())
    assert not A.static_step(OpenMovement(),'test',(1,1),(2,1),{(2,1)})


def test_later_source_change_cannot_be_certified_by_an_unchanged_glb(tmp_path):
    path=tmp_path/'author.py';path.write_text('first recipe\n',encoding='utf-8')
    manifest={'authoredGeometry':{'inputs':{'author.py':A.digest(path)}}}
    assert not A.certificate_mismatches(tmp_path,manifest,{})
    path.write_text('revised recipe\n',encoding='utf-8')
    mismatch=A.certificate_mismatches(tmp_path,manifest,{})
    assert mismatch[0]['source']=='author.py' and mismatch[0]['actual']!=mismatch[0]['expected']
