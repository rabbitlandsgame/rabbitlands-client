"""Stable, invertible native field shared by source geometry and publication."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
TOOLKIT=ROOT/'eloria-assets/maps/nymara-regions/_toolkit'
SOURCE=ROOT/'eloria-assets/maps/nymara-regions/manymouth_delta/source'
sys.path.insert(0,str(TOOLKIT))
from compact_landscape import Axis,CompactLandscape


def field():
    # Evaluate the actual field/mapper definitions without registering a second
    # region's private materials or mutating the process-wide region module.
    tree=ast.parse((SOURCE/'compact_plan.py').read_text(encoding='utf-8'))
    constants={'REVISION','LEGACY_ORIGIN','LEGACY_CELLS','NATIVE_ORIGIN','NATIVE_CELLS','BOUNDS','PLAN','GATES'}
    selected=[node for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id in constants for t in node.targets)
        or isinstance(node,ast.FunctionDef) and node.name in ('legacy_tile_to_native','contract','connector_requests')]
    namespace={'Axis':Axis,'CompactLandscape':CompactLandscape,'np':np}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(SOURCE/'compact_plan.py'),'exec'),namespace)
    return namespace


def test_source_field_matches_the_serialized_publication_contract():
    code=field();record=json.loads((SOURCE/'continent-migration.json').read_text(encoding='utf-8'))
    assert code['contract'](record['ready'],record['nativeArrival'])==record
    assert code['legacy_tile_to_native']([210,222])==record['nativeArrival']
    assert record['nativeCells']==[480,480]
    assert np.subtract(record['nativeMapBounds'][1],record['nativeMapBounds'][0]).tolist()==[480,396]


def test_field_is_invertible_and_retains_the_town_at_human_scale():
    p=field()['PLAN']
    for axis in (p.x,p.z):
        values=np.linspace(axis.old[0]-40,axis.old[-1]+40,1001)
        assert np.all(np.diff(axis(values))>0)
        assert np.allclose(axis.inverse(axis(values)),values,atol=1e-10)
    assert np.isclose(p.x(54)-p.x(13.5),54-13.5)
    assert np.isclose(p.z(-27)-p.z(-61.5),-27+61.5)
    assert p.x(363)-p.x(297)<363-297
    assert p.z(-258)-p.z(-351)<-258+351


def test_content_mapper_is_native_only_before_the_separate_padding_shift():
    code=field();p=code['PLAN'];mapper=code['legacy_tile_to_native']
    for tile in ([0,0],[575,575],[210,222],[537,210],[42,504]):
        new=mapper(tile)
        x,z=tile[0]-174,174-tile[1]
        assert new==[round(float(p.x(x))+138),round(120-float(p.z(z)))]
        assert all(0<=value<480 for value in new)
    # The continent origin change is a later operation, not part of the field.
    assert mapper([210,222])==[183,162]


def test_route_audit_obeys_world_diagonal_corner_occupancy():
    spec=importlib.util.spec_from_file_location('audit_manymouth',SOURCE/'audit_compact.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    mask=np.array([[True,False],[False,True]])
    assert module.path_length(mask,(0,0),(1,1)) is None
    mask[:]=True
    assert np.isclose(module.path_length(mask,(0,0),(1,1)),2**.5)
    class Cliff:
        def can_step(self,x,y,xx,yy,climb):return x==xx
    assert module.path_length(mask,(0,0),(1,1),Cliff()) is None


def test_native_timber_request_keeps_its_survey_and_widens_only_at_the_collar():
    survey=np.array([[1.,2.,0.],[31.,3.,0.]])
    original=survey.copy();anchor=[73.,3.,0.]
    road={'id':'grey-manymouth'}
    build=SimpleNamespace(geography_roads=[road],streaming_borders=[{'id':'grey-manymouth','anchor':anchor}],
        network={'centres':{'sea_landing':[0.,2.,0.]},
                 'surveys':[('sea_landing','continent_west-landing',survey,None)]})
    field()['connector_requests'](build)
    points=np.asarray(road['contactStations'])
    assert np.array_equal(survey,original)
    assert np.allclose(points[1]+[0,.03,0],survey[0])
    assert np.allclose(points[-2]+[0,.03,0],survey[-1])
    assert np.allclose(points[-1]+[0,.03,0],anchor)
    assert np.isclose(np.linalg.norm(points[-2,[0,2]]-points[-3,[0,2]]),6.)
    assert road['contactWidths']==[3.8,3.8,3.8,8.5,8.5]
