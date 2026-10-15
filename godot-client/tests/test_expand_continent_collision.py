"""The geographical grid adapter preserves masks and world-space contracts."""
import importlib.util
import json
from pathlib import Path
import struct

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('continent_padding', ROOT/'eloria-assets/tools/expand_continent_collision.py')
PAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAD)


def frame():
    return PAD.frame_spec(dict(nativeServerOrigin=[1,1],nativeServerCells=[2,2],
        serverOrigin=[3,2],serverCells=[6,6],serverTileShift=[2,1],
        serverBounds=[[-3,-4],[3,2]]))


def encoding():
    return dict(origin=0.,step=.2,range=[1,255],zeroMeansBlocked=True)


def fields(y=3.):
    return (np.ones((12,12),dtype=bool), np.full((12,12),y),
            np.zeros((12,12),dtype=bool), np.full((12,12),-np.inf))


def test_old_core_mask_is_translated_reheighted_and_never_opened():
    old = np.full((4,4),10,dtype=np.uint8)
    old[1,2] = 0
    cover,top,wet,water = fields()
    cover[2,4] = False
    wet[2,5], water[2,5] = True, 4.
    grid,enc,report = PAD.expanded_grid(old,frame(),[1,1],cover,top,wet,water,encoding())
    # Native starts at half-grid x=4/y=2. Original blocker remains blocked.
    assert grid[3,6] == 0
    assert grid[2,4] == grid[2,5] == 0
    assert enc['origin'] + int(grid[5,7])*enc['step'] == 3.
    assert grid[0,0] > 0  # Only new padding may acquire open ground.
    assert report['nativeBlockedPreserved'] == 1
    assert report['oldWalkableUnsupportedClosed'] == report['oldWalkableSubmergedClosed'] == 1


def test_padding_rejects_void_water_and_real_surface_discontinuity():
    cover,top,wet,water = fields()
    cover[0,0] = False
    wet[0,1], water[0,1] = True, 5.
    top[:,9:] = 6.
    grid,_,_ = PAD.expanded_grid(np.ones((4,4),dtype=np.uint8),frame(),[1,1],cover,top,wet,water,encoding())
    assert grid[0,0] == grid[0,1] == 0
    assert (grid[:,8:10] == 0).all()  # Both sides of the three-metre cliff.
    assert (grid[:,10:] > 0).all()


def test_gentle_diagonal_does_not_pass_a_cliff_hidden_by_average_gradient():
    cover,top,_,_ = fields()
    top[0,0], top[0,2] = 6., 0.
    gentle = PAD.gentle_surface(cover,top)
    assert not gentle[0,1]


def test_native_shallow_wading_matches_guard_but_new_padding_must_be_dry():
    cover,top,wet,water=fields()
    wet[:]=True; water[:]=3.1
    grid,_,_=PAD.expanded_grid(np.ones((4,4),dtype=np.uint8),frame(),[1,1],cover,top,wet,water,encoding())
    assert (grid[2:6,4:8] > 0).all()
    assert np.count_nonzero(grid) == 16


def test_expanded_grid_geometry_change_still_preserves_core_closures():
    prior=np.ones((12,12),dtype=np.uint8)
    prior[3,5]=0
    result,_,_=PAD.expanded_grid(prior,frame(),[3,2],*fields(),encoding())
    assert result[3,5] == 0
    assert result[0,0] > 0


@pytest.mark.parametrize('version,flags,tail',[(3,0,b''),(2,1,b''),(2,0,b'extra'),(2,0,None)])
def test_unsupported_binary_formats_or_tail_are_rejected(version,flags,tail):
    data=PAD.HEADER.pack(b'EWCG',version,flags,2,2)+b'\1'*4
    data=data[:-1] if tail is None else data+tail
    with pytest.raises(ValueError): PAD.read_ewcg(data)


def write_glb(path, nodes):
    """Minimal real glTF fixture with independently transformed mesh instances."""
    doc={'asset':{'version':'2.0'},'scenes':[{'nodes':list(range(len(nodes)))}],
         'scene':0,'nodes':[],'meshes':[],'bufferViews':[],'accessors':[],'buffers':[]}
    body=bytearray()
    for name,triangles,translation in nodes:
        points=np.asarray(triangles,dtype='<f4').reshape(-1,3)
        start=len(body); body.extend(points.tobytes())
        doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':points.nbytes})
        doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':len(points),'type':'VEC3'})
        doc['meshes'].append({'primitives':[{'attributes':{'POSITION':len(doc['accessors'])-1}}]})
        doc['nodes'].append({'name':name,'mesh':len(doc['meshes'])-1,'translation':translation})
    doc['buffers']=[{'byteLength':len(body)}]
    encoded=json.dumps(doc).encode(); encoded+=b' '*((-len(encoded))%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(body))+
        struct.pack('<II',len(encoded),0x4e4f534a)+encoded+
        struct.pack('<II',len(body),0x004e4942)+body)


def quad(x0,z0,x1,z1,y):
    return [[[x0,y,z0],[x0,y,z1],[x1,y,z0]],
            [[x1,y,z0],[x0,y,z1],[x1,y,z1]]]


def package(tmp_path):
    p=tmp_path/'isolated';p.mkdir()
    write_glb(p/'world.glb',[
        ('Terrain_Ground',quad(-3,-4,3,2,3),[0,0,0]),
        ('Walk_StreamThreshold_test',quad(-3,-4,-2,2,5),[0,0,0]),
        ('Water_Test',quad(2,-4,3,2,7),[0,0,0]),
        ('StreamView_old',quad(-3,-4,3,2,99),[0,0,0]),
        ('Roof_Excluded',quad(-3,-4,3,2,105),[0,0,0]),
    ])
    manifest={'asset':{'id':'test','glb':'world.glb','serverCells':2,
        'bounds':{'min':[-3,0,-4],'max':[3,7,2]},'playableBounds':{'min':[-1,0,-1],'max':[1,7,1]}},
        'coordinateTransform':{'serverOrigin':[1,1],'metresPerTile':1.,'invertServerY':True,'origin':[0,7,0]},
        'collision':{'binary':'collision.bin','width':4,'height':4,'cellMetres':.5,'heightEncoding':encoding()},
        'minimap':{'image':'minimap.webp','imageSize':[2,2],'worldMin':[-1,-1],'worldMax':[1,1],'pixelsPerMetre':1.},
        'spawnPoints':[{'position':[0,3,0],'serverTile':[1,1]}],
        'portals':[{'id':'out','type':'map-transition','position':[2.5,3,-1.5],'serverTile':[999,999]},
                   {'id':'door','type':'interior','position':[0,3,0],'serverTile':[0,0]}],
        'contentLayout':{'gauntlets':{'test':{'keeperTile':[0,1],'returnTile':[1,0]}}},
        'nested':{'serverTiles':{'pack':[[0,0],[1,1]]}},
        'collisionSource':{'native':True}}
    (p/'world.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    grid=np.full((4,4),10,dtype=np.uint8);grid[2,2]=0
    (p/'collision.bin').write_bytes(PAD.HEADER.pack(b'EWCG',2,0,4,4)+grid.tobytes())
    return p,manifest


def test_actual_glb_highest_navigation_threshold_water_and_world_transform(tmp_path):
    p,_=package(tmp_path)
    cover,top,wet,water=PAD.sample_geometry(p/'world.glb',frame())
    assert cover.all()
    assert np.allclose(top[:,:2], 5.)
    assert np.allclose(top[:,2:], 3.)
    assert np.all(wet[:,-2:]) and np.allclose(water[:,-2:], 7.)
    assert not wet[:,:-2].any()
    write_glb(p/'world.glb',[('Walk_Translated',quad(0,0,1,1,0),[-3,8,1])])
    cover,top,_,_=PAD.sample_geometry(p/'world.glb',frame())
    assert cover.sum() == 4 and np.all(top[:2,:2] == 8.)


def test_check_is_read_only_apply_shifts_once_and_preserves_world_positions(tmp_path):
    p,original=package(tmp_path)
    geography={'regions':{'test':frame()}}
    before={f.name:f.read_bytes() for f in p.iterdir()}
    report=PAD.expand(p,'test',geography,'geography-sha',apply=False)
    assert report['changed']
    assert before == {f.name:f.read_bytes() for f in p.iterdir()}
    PAD.expand(p,'test',geography,'geography-sha',apply=True)
    manifest=json.loads((p/'world.json').read_text(encoding='utf-8'))
    assert manifest['coordinateTransform']['serverOrigin'] == [3,2]
    assert manifest['coordinateTransform']['origin'] == [0,7,0]
    assert manifest['collision']['originMetres'] == [-3,2]
    assert manifest['spawnPoints'][0] == {'position':[0,3,0],'serverTile':[3,2]}
    assert manifest['portals'][0]['serverTile'] == [5,3]  # floor(actual position), not stale tile.
    assert manifest['portals'][1]['serverTile'] == [2,1]
    assert manifest['contentLayout']['gauntlets']['test'] == {'keeperTile':[2,2],'returnTile':[3,1]}
    assert manifest['nested']['serverTiles']['pack'] == [[2,1],[3,2]]
    assert manifest['minimap']['imageSize'] == [6,6]
    assert manifest['minimap']['worldMin'] == [-3,-4]
    assert manifest['asset']['bounds'] == original['asset']['bounds']
    assert manifest['asset']['playableBounds'] == {'min':[-3,0,-4],'max':[3,7,2]}
    binary=(p/'collision.bin').read_bytes();grid,version,flags=PAD.read_ewcg(binary)
    assert grid.shape == (12,12) and (version,flags) == (2,0)
    assert grid[4,6] == 0
    applied={f.name:f.read_bytes() for f in p.iterdir()}
    again=PAD.expand(p,'test',geography,'geography-sha',apply=True)
    assert not again['changed'] and again['alreadyExpanded']
    assert applied == {f.name:f.read_bytes() for f in p.iterdir()}
    assert applied['world.glb'] == before['world.glb']


def test_rerun_preserves_subsequent_shared_guard_closures(tmp_path):
    p,_=package(tmp_path);geo={'regions':{'test':frame()}}
    PAD.expand(p,'test',geo,'geo',apply=True)
    raw=bytearray((p/'collision.bin').read_bytes());raw[16+12*11+5]=0
    (p/'collision.bin').write_bytes(raw)
    assert not PAD.expand(p,'test',geo,'geo',apply=True)['changed']
    assert (p/'collision.bin').read_bytes() == raw


def test_unrelated_plan_change_updates_hash_without_reopening_guarded_padding(tmp_path):
    p,_=package(tmp_path);geo={'regions':{'test':frame()}}
    PAD.expand(p,'test',geo,'old-geo',apply=True)
    raw=bytearray((p/'collision.bin').read_bytes());raw[16+12*11+5]=0
    (p/'collision.bin').write_bytes(raw)
    report=PAD.expand(p,'test',geo,'new-geo',apply=True)
    assert report['changed'] and report['alreadyExpanded']
    assert (p/'collision.bin').read_bytes() == raw
    assert json.loads((p/'world.json').read_text())['continentGeography']['geographySha256'] == 'new-geo'


def test_native_rebuild_with_stale_marker_is_shifted_by_its_actual_frame(tmp_path):
    p,m=package(tmp_path);geo={'regions':{'test':frame()}}
    original_grid=(p/'collision.bin').read_bytes()
    PAD.expand(p,'test',geo,'geo',apply=True)
    m['continentGeography']=json.loads((p/'world.json').read_text())['continentGeography']
    (p/'world.json').write_text(json.dumps(m),encoding='utf-8')
    (p/'collision.bin').write_bytes(original_grid)
    PAD.expand(p,'test',geo,'geo',apply=True)
    assert json.loads((p/'world.json').read_text())['spawnPoints'][0]['serverTile'] == [3,2]


@pytest.mark.parametrize('change',[
    {'serverTileShift':[1,1]}, {'serverCells':[7,7]},
    {'serverBounds':[[-3,-5],[3,2]]}, {'serverOrigin':[2.5,2]},
    {'nativeServerCells':[20,20]},
])
def test_invalid_or_cropping_frames_fail(change):
    entry=frame();entry.update(change)
    with pytest.raises(ValueError):PAD.frame_spec(entry)


def test_mixed_native_binary_and_expanded_manifest_is_rejected(tmp_path):
    p,m=package(tmp_path);m['coordinateTransform']['serverOrigin']=[3,2]
    (p/'world.json').write_text(json.dumps(m),encoding='utf-8')
    with pytest.raises(ValueError,match='neither'):
        PAD.expand(p,'test',{'regions':{'test':frame()}},'geo',apply=True)


def test_registry_legacy_entries_without_manifests_do_not_block_cli(tmp_path):
    registry=tmp_path/'godot-client/data/maps/registry.json'
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'maps':{'old':{'elm':'old.elm'},
        'new':{'manifest':'res://../../../maps/new/world.json'}}}),encoding='utf-8')
    assert set(PAD.region_packages(tmp_path)) == {'new'}


def test_streaming_trigger_is_restored_from_frame_after_old_grid_snap(tmp_path):
    p,m=package(tmp_path)
    m['portals'][0]['position']=[0,3,0]  # Native snap moved it off the seam.
    m['streamingBorders']=[{'portal':'out','anchor':[1.5,4,-2.5],'outward':[1,0]}]
    (p/'world.json').write_text(json.dumps(m),encoding='utf-8')
    PAD.expand(p,'test',{'regions':{'test':frame()}},'geo',apply=True)
    m=json.loads((p/'world.json').read_text())
    assert m['portals'][0]['position'] == [2.5,4,-2.5]
    assert m['portals'][0]['serverTile'] == [5,4]


def test_visible_frame_uses_owned_footprint_instead_of_empty_square_server_rows(tmp_path):
    p,_=package(tmp_path)
    entry=frame();entry.update(translation=[100,0,200],
        ownershipPolygon=[[97,197],[103,197],[103,201],[97,201]])
    PAD.expand(p,'test',{'regions':{'test':entry}},'geo',apply=True)
    m=json.loads((p/'world.json').read_text())
    assert m['coordinateTransform']['serverCells']==[6,6]
    assert m['minimap']['worldMin']==[-3,-3]
    assert m['minimap']['worldMax']==[3,1]
    assert m['minimap']['imageSize']==[6,4]


def test_optional_lod_manifest_is_shifted_once_and_uses_same_grid(tmp_path):
    p,m=package(tmp_path)
    m['asset']['glb']='world-lod2.glb'
    (p/'world-lod2.glb').write_bytes((p/'world.glb').read_bytes())
    (p/'world-lod2.json').write_text(json.dumps(m),encoding='utf-8')
    geo={'regions':{'test':frame()}}
    before=(p/'world-lod2.json').read_bytes()
    assert PAD.expand(p,'test',geo,'geo',apply=False)['lodMetadataChanged']
    assert (p/'world-lod2.json').read_bytes()==before
    PAD.expand(p,'test',geo,'geo',apply=True)
    lod=json.loads((p/'world-lod2.json').read_text())
    assert lod['asset']['glb']=='world-lod2.glb'
    assert lod['spawnPoints'][0]['serverTile']==[3,2]
    assert lod['collision']['originMetres']==[-3,2]
    assert lod['collision']['width']==lod['collision']['height']==12
    stable=(p/'world-lod2.json').read_bytes()
    assert not PAD.expand(p,'test',geo,'geo',apply=True)['changed']
    assert (p/'world-lod2.json').read_bytes()==stable
