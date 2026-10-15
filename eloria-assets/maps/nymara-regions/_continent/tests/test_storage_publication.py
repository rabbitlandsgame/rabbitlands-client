"""Signed standing checks and metadata plans; no writes to real checkouts."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parents[2]/'tools'))
import publish_diagonal_continent as P
import export_contracts as E
import build_continent as B
from storage_bounds import StorageBounds as Bounds, storage_record
import test_publish_diagonal_continent as legacy_publication
from test_publish_diagonal_continent import specs, connections
from test_storage_placement import server_math, placement, StoredWorld


def encoded_collision(bounds,server_math):
    iy,ix=np.indices((bounds.height*2,bounds.width*2))
    half=(10+ix+iy).astype(np.uint8)
    result={'grid':half,'heights':half.astype(np.float32)*.2+3,
            'collision':{'serverCells':[bounds.width,bounds.height],**bounds.metadata(),
                         'heightEncoding':{'origin':3,'step':.2},'sourceGlbSha256':'f'*64}}
    grid,factor,largest,detail=E.fold_server_grid(result,*server_math)
    assert np.all(grid) and largest.any() and factor>=1
    blob=struct.pack('<4sHHII',b'EWCG',2,0,bounds.width*2,bounds.height*2)+half.tobytes()
    return result,grid,blob


@pytest.mark.parametrize('minimum',[(-5,-3),(7,9),(0,0)])
def test_signed_arrival_and_standing_checks_cover_all_four_halfcells(server_math,minimum):
    bounds=Bounds(12,12,*minimum)
    result,grid,blob=encoded_collision(bounds,server_math)
    spec={'serverOrigin':[4,8],'serverCells':[12,12],**bounds.metadata(),
          'translation':[100,0,-50],'arrival':list(minimum)}
    registry={'test':spec}
    for tile in (minimum,(bounds.max_x-1,bounds.max_y-1)):
        point=P.world_point('test',tile,registry)
        assert P.destination_tile('test',point,registry)==list(tile)
        spec['arrival']=list(tile)
        assert P.validate_standing_points(registry,{'test':blob},{},[])==1
        column,row=bounds.index_xy(*tile)
        for dy,dx in ((0,0),(0,1),(1,0),(1,1)):
            damaged=bytearray(blob)
            damaged[16+(2*row+dy)*bounds.width*2+2*column+dx]=0
            with pytest.raises(ValueError,match='blocked'):
                P.validate_standing_points(registry,{'test':bytes(damaged)},{},[])
    for tile in ((bounds.min_x-1,bounds.min_y),(bounds.max_x,bounds.max_y-1)):
        assert P.destination_tile('test',P.world_point('test',tile,registry),registry) is None
        spec['arrival']=list(tile)
        with pytest.raises(ValueError,match='outside'):
            P.validate_standing_points(registry,{'test':blob},{},[])
    spec['arrival']=list(minimum)
    with pytest.raises(ValueError,match='outside'):
        P.validate_standing_points(registry,{'test':blob},{},[('test',*minimum,'test',bounds.max_x,bounds.min_y)])


@pytest.mark.parametrize('shift,minimum',[(-24,(-30,-30)),(24,(20,20))])
def test_signed_connection_rows_keep_world_identity_and_no_bounce(shift,minimum):
    baseline=specs(); links=connections()
    old_rows=P.connection_rows(links,baseline)[1]
    regions=copy.deepcopy(baseline); moved=copy.deepcopy(links)
    for spec in regions.values():
        spec.update(serverOrigin=[v+shift for v in spec['serverOrigin']],serverCells=[60,60],
                    **Bounds(60,60,*minimum).metadata())
    for end in moved[0]['ends']:
        for key in ('tile','arrival'):
            end[key]=[v+shift for v in end[key]]
        for lane in end['lanes']:
            for key in ('tile','arrival'):
                lane[key]=[v+shift for v in lane[key]]
    rows=P.connection_rows(moved,regions)[1]
    for old,new in zip(old_rows,rows):
        assert P.world_point(old[0],old[1:3],baseline)==P.world_point(new[0],new[1:3],regions)
        assert P.world_point(new[0],new[1:3],regions)==P.world_point(new[3],new[4:6],regions)
    triggers={(r[0],r[1],r[2]) for r in rows}
    assert all((r[3],r[4],r[5]) not in triggers for r in rows)


def fixture_plan(tmp_path,server_math,minimum,*,explicit=True):
    client,server,path=legacy_publication.PublicationTests().fixture(tmp_path)
    publication=P.read_json(path)
    for i,(region,spec) in enumerate(publication['regions'].items()):
        extent=30 if any(minimum) else 24
        bounds=Bounds(extent,extent,*minimum)
        spec['serverCells']=[extent,extent]
        result,grid,blob=encoded_collision(bounds,server_math)
        if explicit:
            source_sha=hashlib.sha256(('fixture-source-'+region).encode()).hexdigest()
            spec.update(bounds.metadata(),authoringSpecSha256=source_sha)
        world_path=Path(spec['worldManifestPath'])
        collision_path=Path(spec['collisionPath'])
        collision_path.write_bytes(blob)
        transform={'serverOrigin':spec['serverOrigin'],'serverCells':spec['serverCells'],
                   'origin':[0,0,0],'metresPerTile':1.,'invertServerY':True,'walkingHeight':42.25+i,
                   'addressableWorldBounds':dict(zip(('min','max'),bounds.physical_bounds(spec['serverOrigin'])))}
        collision={'authoredSurfaceExport':True,'gridAlignment':'tile-centres-v1',
                   'originMetres':list(bounds.physical_origin(spec['serverOrigin']))}
        if explicit:
            transform.update(storage_record(spec['serverCells'],spec))
            collision.update(storage_record(spec['serverCells'],spec))
        world={'coordinateTransform':transform,'collision':collision}
        if explicit:
            child=world_path.parent/'chunks/00_00/world.json'
            child.parent.mkdir(parents=True)
            child.write_text(json.dumps(world))
            world['streamingChunks']={'chunks':[{'manifest':'chunks/00_00/world.json'}]}
            children=E.revision_metadata(world_path,world,spec,publication['masterSha256'])
            for target,data in children:
                target.write_text(json.dumps(data))
        world_path.write_text(json.dumps(world))
    for link in publication['connections']:
        for end in link['ends']:
            end['frame']['globalTranslation']=publication['regions'][end['region']]['translation']
            end['position']=[end['tile'][0]+.5-12,7.125,12-end['tile'][1]-.5]
    path.write_text(json.dumps(publication))
    return client,server,path


def tree_hashes(root):
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('minimum',[(-2,-4),(1,2),(0,0)])
def test_metadata_plan_roundtrip_copies_storage_and_preserves_full_frames(tmp_path,server_math,minimum):
    client,server,path=fixture_plan(tmp_path,server_math,minimum)
    publication=P.read_json(path); original=tree_hashes(tmp_path)
    _,pending,report=P.plan(client,server,path)
    assert tree_hashes(tmp_path)==original
    registry=json.loads(pending[client/'godot-client/data/maps/registry.json'])
    manifest=json.loads(pending[server/'config/eloria/client_content_manifest.json'])
    stream=json.loads(pending[server/'config/eloria/exterior_connections.json'])
    for region,spec in publication['regions'].items():
        storage=storage_record(spec['serverCells'],spec)
        world=P.read_json(Path(spec['worldManifestPath']))
        assert registry['maps'][region]['coordinateTransform']==world['coordinateTransform']
        assert storage_record(spec['serverCells'],registry['maps'][region]['continentGeography'])==storage
        item=next(v for v in manifest['maps'] if v['id']==region)
        assert item['coordinateTransform']==world['coordinateTransform']
        assert storage_record(item['serverCells'],item)==storage
        assert storage_record(spec['serverCells'],manifest['continentGeography']['regions'][region])==storage
        assert manifest['diagonalContinent']['storageByRegion'][region]==storage
        assert manifest['diagonalContinent']['placements'][region]['storage']==storage
        child=P.read_json(Path(spec['worldManifestPath']).parent/'chunks/00_00/world.json')
        assert child['coordinateTransform']==world['coordinateTransform']
        assert child['continentPublication']==world['continentPublication']
        assert storage_record(spec['serverCells'],child['collision'])==storage
    for old,end in zip(publication['connections'][0]['ends'],stream['connections'][0]['ends']):
        assert end['position']==old['position'] and end['frame']==old['frame'] and end['portal']==old['portal']
        assert end['coordinateTransform']==registry['maps'][old['region']]['coordinateTransform']
    assert report['verifiedStandingPoints']>2


@pytest.mark.parametrize('minimum',[(-2,-4),(1,2)])
def test_real_apply_entry_rejects_signed_storage_before_any_target_write(tmp_path,monkeypatch,server_math,minimum):
    client,server,path=fixture_plan(tmp_path,server_math,minimum)
    original=tree_hashes(tmp_path)
    monkeypatch.setattr(sys,'argv',['publish','--client',str(client),'--server',str(server),
                                  '--publication',str(path),'--apply','--report',str(tmp_path/'not-written.json')])
    monkeypatch.setattr(P.shared,'apply_plan',lambda *a:pytest.fail('write entry reached'))
    with pytest.raises(ValueError,match='validity-based persistence migration'):
        P.main()
    assert tree_hashes(tmp_path)==original


@pytest.mark.parametrize('explicit',[False,True])
def test_zero_minimum_real_apply_entry_keeps_legacy_path(tmp_path,monkeypatch,server_math,explicit):
    client,server,path=fixture_plan(tmp_path,server_math,(0,0),explicit=explicit)
    called=[]
    monkeypatch.setattr(sys,'argv',['publish','--client',str(client),'--server',str(server),'--publication',str(path),'--apply'])
    monkeypatch.setattr(P.shared,'apply_plan',lambda before,pending:called.append((before,pending)))
    P.main()
    assert len(called)==1 and called[0][1]


@pytest.mark.parametrize('target',['transform','collision','source','physical','certificate','bytes','walking'])
def test_mismatched_package_storage_or_bytes_fail_before_planning_writes(tmp_path,server_math,target):
    client,server,path=fixture_plan(tmp_path,server_math,(-2,-4))
    spec=P.read_json(path)['regions']['four_gates']; world_path=Path(spec['worldManifestPath'])
    world=P.read_json(world_path)
    if target=='transform':world['coordinateTransform']['serverTileMin']=[0,0]
    if target=='collision':world['collision']['serverTileMin']=[0,0]
    if target=='source':world['collision']['authoringSpecSha256']='a'*64
    if target=='physical':world['collision']['originMetres']=[0,0]
    if target=='certificate':world['continentPublication']['storage']['serverTileMin']=[0,0]
    if target=='bytes':Path(spec['collisionPath']).write_bytes(Path(spec['collisionPath']).read_bytes()+b'changed')
    if target=='walking':world['coordinateTransform']['walkingHeight']=float('nan')
    world_path.write_text(json.dumps(world)); original=tree_hashes(tmp_path)
    with pytest.raises(ValueError):P.plan(client,server,path)
    assert tree_hashes(tmp_path)==original


def test_endpoint_translation_disagreement_fails_without_repair(tmp_path,server_math):
    client,server,path=fixture_plan(tmp_path,server_math,(-2,-4))
    publication=P.read_json(path)
    publication['connections'][0]['ends'][0]['frame']['globalTranslation']=[99,0,0]
    path.write_text(json.dumps(publication));before=tree_hashes(tmp_path)
    with pytest.raises(ValueError,match='endpoint frame translation differs'):
        P.plan(client,server,path)
    assert tree_hashes(tmp_path)==before


def test_revision_binds_minimum_and_source_but_implicit_zero_stays_identical(tmp_path,server_math):
    bounds=Bounds(12,12); collision,grid,blob=encoded_collision(bounds,server_math)
    path=tmp_path/'collision.bin';path.write_bytes(blob)
    spec={'serverOrigin':[4,8],'serverCells':[12,12],'translation':[0,0,0],'arrival':[4,8],
          'contentPositions':{},'collisionPath':str(path)}
    original=E.terrain_revision(spec,collision,grid)
    spec.update(bounds.metadata())
    assert E.terrain_revision(spec,collision,grid)==original
    spec['serverTileMin']=[-1,0]
    shifted=E.terrain_revision(spec,collision,grid)
    assert shifted!=original
    spec['authoringSpecSha256']='a'*64
    assert E.terrain_revision(spec,collision,grid)!=shifted


def test_explicit_source_walking_height_survives_marker_update(server_math):
    p=placement(Bounds(48,48),server_math)
    p.world._storage_contracts={'west':SimpleNamespace(server_frame=(None,None,None,None,True,123.25))}
    manifest={'coordinateTransform':{'walkingHeight':123.25}}
    E.update_markers(p,manifest)
    assert manifest['coordinateTransform']['walkingHeight']==123.25
    assert manifest['spawnPoints'][0]['position'][1]!=123.25


def test_geometry_export_certificate_rejects_stale_storage(tmp_path,monkeypatch):
    bounds=Bounds(12,12,-2,-4)
    storage={'serverOrigin':[4,8],**storage_record([12,12],{**bounds.metadata(),'authoringSpecSha256':'a'*64})}
    (tmp_path/'composition.json').write_bytes(b'fixture composition')
    (tmp_path/'continent.glb').write_bytes(b'fixture master')
    region=tmp_path/'test';region.mkdir()
    (region/'world.glb').write_bytes(b'fixture region')
    manifest={'coordinateTransform':copy.deepcopy(storage)}
    (region/'world.json').write_text(json.dumps(manifest))
    ledger={'compositionSha256':B.digest(tmp_path/'composition.json'),'masterSha256':B.digest(tmp_path/'continent.glb'),
            'geometrySources':{},'geometryDependencies':{},'regions':{'test':{
                'glbSha256':B.digest(region/'world.glb'),'storage':storage}}}
    (tmp_path/'export.json').write_text(json.dumps(ledger))
    monkeypatch.setattr(B,'EXPORT_SOURCES',())
    monkeypatch.setattr(B,'geometry_dependencies',lambda:{})
    monkeypatch.setattr(B,'package',lambda name:tmp_path/name)
    assert B.verify_geometry_export(tmp_path)==ledger
    manifest['coordinateTransform']['serverTileMin']=[0,0]
    (region/'world.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='storage certificate changed'):
        B.verify_geometry_export(tmp_path)


@pytest.mark.parametrize('target',['parent','collision','child'])
def test_revision_metadata_does_not_bless_mismatched_storage(tmp_path,server_math,target):
    client,server,path=fixture_plan(tmp_path,server_math,(-2,-4))
    publication=P.read_json(path);spec=publication['regions']['four_gates']
    world_path=Path(spec['worldManifestPath']);world=P.read_json(world_path)
    if target=='parent':world['coordinateTransform']['serverTileMin']=[0,0]
    if target=='collision':world['collision']['serverTileMin']=[0,0]
    if target=='child':
        child_path=world_path.parent/'chunks/00_00/world.json';child=P.read_json(child_path)
        child['coordinateTransform']['serverTileMin']=[0,0]
        child_path.write_text(json.dumps(child))
    before=tree_hashes(tmp_path)
    with pytest.raises(ValueError,match='storage differs'):
        E.revision_metadata(world_path,world,spec,publication['masterSha256'])
    assert tree_hashes(tmp_path)==before


def test_geography_uses_live_storage_with_immutable_transform(tmp_path,monkeypatch,server_math):
    bounds={'west':Bounds(60,60,-6,-4),'east':Bounds(60,60,3,2)}
    world=StoredWorld(bounds)
    world.bounds=lambda region:(np.min(world.polygons[region],axis=0),np.max(world.polygons[region],axis=0))
    world.storage_contract=lambda region:{'serverOrigin':world.address(region)[0],
        **storage_record(world.address(region)[1],{**bounds[region].metadata(),'authoringSpecSha256':'a'*64})}
    world.publication_connections=[]
    regions=tmp_path/'regions';regions.mkdir()
    monkeypatch.setattr(B,'CLIENT',tmp_path);monkeypatch.setattr(B,'REGIONS',regions)
    monkeypatch.setattr(B,'HERE',tmp_path);monkeypatch.setattr(B,'package',lambda region:regions/region)
    (tmp_path/'legacy-geography.json').write_text('{"connections":[]}')
    for filename in ('shared-terrain.glb','continent.glb'):(tmp_path/filename).write_bytes(b'fixture')
    manifests={}
    for region in world.ids:
        folder=regions/region;folder.mkdir()
        manifests[region]={'terrainRevision':'test','coordinateTransform':{
            'serverOrigin':world.address(region)[0],**storage_record([60,60],world.storage_contract(region)),
            'origin':[0,0,0],'metresPerTile':1,'invertServerY':True,'walkingHeight':42.25}}
        (folder/'world.json').write_text(json.dumps(manifests[region]))
    B.publish_geography(world,manifests,tmp_path)
    geography=P.read_json(regions/'continent-geography.json')
    for region in world.ids:
        record=geography['regions'][region]
        assert record['serverBounds']==bounds[region].physical_bounds([24,24])
        assert record['nativeServerTileMin']==[bounds[region].min_x,bounds[region].min_y]
        assert record['coordinateTransform']==manifests[region]['coordinateTransform']
        assert record['translation']==[*world.regions[region]['center'][:1],0,world.regions[region]['center'][1]]
        assert record['authoringSpecSha256']=='a'*64


@pytest.mark.parametrize('bad',[None,'A'*64,'a'*63,False])
def test_storage_identity_rejects_malformed_source_hashes(bad):
    with pytest.raises(ValueError,match='authoringSpecSha256'):
        storage_record([6,6],{'authoringSpecSha256':bad})


@pytest.mark.parametrize('metadata',[{'serverTileMin':[-1,0]},{'serverStorageVersion':1},
    {'serverStorageVersion':True,'serverTileMin':[0,0]}, {'serverStorageVersion':1,'serverTileMin':[False,0]}])
def test_publisher_rejects_malformed_explicit_storage_pairs(metadata):
    spec=specs()['four_gates'];spec.update(metadata)
    with pytest.raises(ValueError):P.validate_spec('four_gates',spec,None)
