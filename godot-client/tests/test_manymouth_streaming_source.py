"""Small source-helper regressions; no region build or package writes."""
import ast
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


SOURCE=Path(__file__).resolve().parents[2]/'eloria-assets/maps/nymara-regions/manymouth_delta/source/build_manymouth_delta.py'


def helpers(apply):
    # Load only the two production helpers. Importing a regional builder also
    # registers its private surface/material tables in shared process globals.
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)
               and n.name in ('walk_triangles','apply_streaming')]
    module=ast.Module(body=functions,type_ignores=[])
    scope={'np':np,'math':math,'Path':Path,'__file__':str(SOURCE),
           'sys':SimpleNamespace(path=SimpleNamespace(insert=lambda *_:None)),
           'SB':SimpleNamespace(VIEW_PREFIX='StreamView_',apply=apply),
           'COMPACT':SimpleNamespace(connector_requests=lambda b:None)}
    exec(compile(module,str(SOURCE),'exec'),scope)
    return scope


def triangle(y):
    return SimpleNamespace(positions=np.array([[0.,y,0.],[0.,y,1.],[1.,y,0.]]),
                           indices=np.array([0,1,2]))


def test_shared_decks_enter_collision_and_cached_native_triangles_are_invalidated(monkeypatch):
    build=SimpleNamespace(terrain_meshes={},placements=[],meshes={})
    calls=[];captured=object()
    def capture(b,region):
        assert b is build and region=='manymouth_delta'
        calls.append('capture');return captured
    def outer(b,region,snapshot):
        assert snapshot is captured
        calls.append('outer')
    def finish(b,region):
        calls.append('finish')
        b.terrain_meshes['Walk_ContinentRoad_test']=triangle(4.)
    monkeypatch.setitem(sys.modules,'outer_aprons',SimpleNamespace(capture=capture,apply=outer))
    monkeypatch.setitem(sys.modules,'connector_finish',SimpleNamespace(apply=finish))
    def apply(b,region):
        assert region=='manymouth_delta'
        calls.append('shared')
        b.terrain_meshes['Walk_StreamCauseway_test']=triangle(4.)
        b.terrain_meshes['Walk_StreamThreshold_test']=triangle(4.)
        b.streaming_borders=[{'id':'test','sceneNodes':['Walk_StreamCauseway_test']}]
    h=helpers(apply)
    assert h['walk_triangles'](build).shape==(0,3,3)
    h['apply_streaming'](build)
    result=h['walk_triangles'](build)
    assert result.shape==(3,3,3)
    assert np.all(result[:,:,1]==4.)
    assert calls==['capture','shared','outer','finish']
    assert build.streaming_borders[0]['sceneNodes']==['Walk_StreamCauseway_test']


def test_native_transformed_walk_parts_remain_and_preview_copies_do_not():
    part=triangle(1.)
    place=SimpleNamespace(node='NativeLanding',mesh='landing',walk_surface=False,
                          rotation_y=math.pi/2,scale=2.,position=(3.,4.,5.))
    copy=SimpleNamespace(**vars(place));copy.node='StreamView_test__NativeLanding'
    build=SimpleNamespace(terrain_meshes={'Terrain_Ground':triangle(99.)},
        placements=[place,copy],meshes={'landing':SimpleNamespace(walk_parts=[part])})
    result=helpers(lambda *_:None)['walk_triangles'](build)
    assert result.shape==(1,3,3)
    assert np.allclose(result[0],[[3,6,5],[5,6,5],[3,6,3]])


def test_lod_export_cannot_replace_already_partitioned_terrain():
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    writes=[n for n in ast.walk(main) if isinstance(n,ast.Attribute)
            and isinstance(n.ctx,ast.Store) and n.attr=='terrain_meshes']
    assert not writes, 'A post-build LOD reset would erase its shared causeway/cell meshes'
