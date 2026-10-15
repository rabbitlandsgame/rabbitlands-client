"""Real geometry and clean-checkout regressions for the shared continent atlas."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'eloria-assets/tools'))
import build_continent_map as B
import render_region_cartography as C

SOURCE = ROOT/'eloria-assets/maps/nymara-regions/_continent/atlas_export.py'
SPEC = importlib.util.spec_from_file_location('continent_atlas_export', SOURCE)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def glb(path, external=False):
    """A textured ground and roof spanning an ownership boundary at X=10."""
    positions = np.array([[0,0,0],[0,0,10],[20,0,10],[20,0,0],
                          [8,2,2],[8,2,8],[12,2,8],[12,2,2]], '<f4')
    normals = np.tile([0,1,0], (8,1)).astype('<f4')
    uv = positions[:,[0,2]].copy().astype('<f4')*.05
    indices = np.array([0,1,2,0,2,3,4,5,6,4,6,7], '<u2')
    image = Image.new('RGBA', (8,8), (74,115,54,255))
    png = io.BytesIO();image.save(png, 'PNG')
    arrays = [positions.tobytes(), normals.tobytes(), uv.tobytes(), indices.tobytes(), png.getvalue()]
    binary = bytearray();views = []
    for raw in arrays:
        while len(binary)%4:binary.append(0)
        views.append({'buffer':0, 'byteOffset':len(binary), 'byteLength':len(raw)})
        binary.extend(raw)
    accessors = [{'bufferView':i, 'componentType':5126, 'count':8, 'type':kind}
                 for i,kind in enumerate(('VEC3','VEC3','VEC2'))]
    accessors += [{'bufferView':3, 'byteOffset':offset, 'componentType':5123, 'count':6, 'type':'SCALAR'}
                  for offset in (0,12)]
    doc = {'asset':{'version':'2.0'}, 'scene':0, 'scenes':[{'nodes':[0]}],
        'nodes':[{'name':'Terrain_actual_with_roof', 'mesh':0}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},
                                'indices':3+i,'material':i} for i in range(2)]}],
        'accessors':accessors, 'bufferViews':views,
        'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicFactor':0}},
                     {'pbrMetallicRoughness':{'baseColorFactor':[.8,.05,.03,1],'metallicFactor':0}}],
        'textures':[{'source':0}], 'images':[{'bufferView':4,'mimeType':'image/png'}],
        'buffers':[{'byteLength':len(binary)}]}
    resources = {}
    if external:
        shared = path.parent.parent/'shared-assets';shared.mkdir(parents=True,exist_ok=True)
        texture = shared/'ground.png';texture.write_bytes(png.getvalue())
        doc['images'] = [{'uri':'../shared-assets/ground.png'}]
        resources = {'../shared-assets/ground.png':C.sha(texture)}
    encoded = json.dumps(doc, separators=(',',':')).encode()
    encoded += b' '*((-len(encoded))%4)
    binary += b'\0'*((-len(binary))%4)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(binary)) +
        struct.pack('<II',len(encoded),0x4e4f534a)+encoded+
        struct.pack('<II',len(binary),0x004e4942)+binary)
    return resources


def test_external_pngs_render_identically_and_validate_integrity_and_scope(tmp_path):
    embedded = tmp_path/'embedded/world.glb';glb(embedded)
    external = tmp_path/'external/world.glb';resources = glb(external,True)
    one = C.scene_from_glb(embedded)
    two = C.scene_from_glb(external,resources,tmp_path)
    render = lambda loaded: np.asarray(C.raster(*loaded[:2],np.array([0.,0.]),np.array([20.,10.]),(40,20),1)[0])
    assert np.array_equal(render(one),render(two))
    with pytest.raises(ValueError,match='declared SHA256'):
        C.scene_from_glb(external)
    with pytest.raises(ValueError,match='hash mismatch'):
        C.scene_from_glb(external,{'../shared-assets/ground.png':'0'*64},tmp_path)
    with pytest.raises(ValueError,match='escapes asset root'):
        C.scene_from_glb(external,resources,external.parent)


def test_world_crop_keeps_north_and_matches_common_pixels_across_non_square_regions():
    y,x = np.indices((10,20))
    pixels = np.stack((x,y,x+y),axis=-1).astype(np.uint8)
    image = Image.fromarray(pixels)
    west = A.crop_world(image,np.array([-4.,-8.]),1,[-4,-8],[6,2],(10,10))
    east = A.crop_world(image,np.array([-4.,-8.]),1,[6,-8],[16,2],(10,10))
    assert np.array_equal(np.concatenate((np.asarray(west),np.asarray(east)),axis=1),pixels)
    manifest = {'minimap':{'worldMin':[-5,-2],'worldMax':[5,2], 'imageSize':[10,4], 'pixelsPerMetre':1},
                'continentGeography':{'translation':[15,0,8]}}
    low,high,size = A.global_frame(manifest,{'translation':[15,0,8]})
    assert low.tolist()==[10,6] and high.tolist()==[20,10] and size==(10,4)
    with pytest.raises(ValueError,match='translations differ'):
        A.global_frame(manifest,{'translation':[14,0,8]})


def test_full_master_publish_is_reproducible_and_clean_checkout_verifies_named_inputs(tmp_path,monkeypatch):
    here = tmp_path/'eloria-assets/maps/nymara-regions/_continent'
    here.mkdir(parents=True)
    for module, relative in ((A,'eloria-assets/maps/nymara-regions/_continent/atlas_export.py'),
                             (B,'eloria-assets/tools/build_continent_map.py'),
                             (C,'eloria-assets/tools/render_region_cartography.py'),
                             (C.atlas_soft_ground,'eloria-assets/tools/atlas_soft_ground.py')):
        target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(Path(module.__file__).read_bytes())
        monkeypatch.setattr(module,'__file__',str(target))
    toolkit=tmp_path/'eloria-assets/maps/nymara-regions/_toolkit'
    raster=toolkit/'native/raster.c';raster.parent.mkdir(parents=True)
    raster.write_bytes((C.TOOLKIT/'native/raster.c').read_bytes())
    shader=tmp_path/'godot-client/src/world/soft_ground.gdshader';shader.parent.mkdir(parents=True)
    shader.write_bytes((ROOT/'godot-client/src/world/soft_ground.gdshader').read_bytes())
    for module in (A,B,C):monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(A,'HERE',here)
    monkeypatch.setattr(C,'TOOLKIT',toolkit)
    for name,relative in {'LAYOUT':'eloria-assets/maps/nymara-regions/continent-layout.json',
                          'GEOGRAPHY':'eloria-assets/maps/nymara-regions/continent-geography.json',
                          'CONNECTIONS':'eloria-assets/maps/nymara-regions/region-connections.json',
                          'REGISTRY':'godot-client/data/maps/registry.json',
                          'CARTOGRAPHY':'godot-client/data/maps/cartography.json',
                          'CONTINENT_IMAGE':'eloria-assets/maps/nymara-regions/continent-map.webp'}.items():
        monkeypatch.setattr(B,name,tmp_path/relative)
    master=here/'generated/continent.glb';glb(master)
    layout={'continent':'Fixture','originMetres':[0,0],'canvasMetres':[20,10],
            'metresPerPixel':1,'sea':list(C.water_rgb()),'regions':{'west':[5,5],'east':[15,5]}}
    registry={'maps':{}};geography={'regions':{}}
    for identity,translation in [('west',[5,0,5]),('east',[15,0,5])]:
        package=here.parent/identity;package.mkdir()
        resources=glb(package/'world.glb',True)
        polygon=[[translation[0]-5,0],[translation[0]+5,0],[translation[0]+5,10],[translation[0]-5,10]]
        manifest={'asset':{'glb':'world.glb','name':identity,
            'mapBounds':{'min':[-5,0,-5],'max':[5,3,5]}},
            'minimap':{'image':'minimap.webp','worldMin':[-5,-5],'worldMax':[5,5],
                       'imageSize':[10,10],'pixelsPerMetre':1},
            'continentGeography':{'translation':translation,'ownershipPolygon':polygon},
            'externalResources':resources}
        A.write_json(package/'world.json',manifest)
        registry['maps'][identity]={'manifest':B.path_to_resource(package/'world.json')}
        geography['regions'][identity]={'translation':translation,'ownershipPolygon':polygon,
                                       'nativePlayableBounds':[[-5,0,-5],[5,3,5]]}
    for path,value in [(B.LAYOUT,layout),(B.REGISTRY,registry),(B.GEOGRAPHY,geography),(B.CONNECTIONS,{'connections':[]})]:
        A.write_json(path,value)
    output=tmp_path/'review'
    report=A.render(master,output,1)
    A.apply(report,output)
    assert B.check()==[]
    atlas=B.CONTINENT_IMAGE.read_bytes();proof=(here/'cartography/continent-atlas.json').read_bytes()
    assert B.load_json(B.CARTOGRAPHY)['continent']['masterGeometry']['masterSha256']==C.sha(master)
    assert 'generated/continent.glb' in next(iter(json.loads(proof)['optionalReviewInputs']))
    assert np.asarray(Image.open(output/'continent-global.png'))[5,10,0]>np.asarray(Image.open(output/'continent-global.png'))[5,10,1]*2
    A.apply(A.render(master,output,1),output)
    assert atlas==B.CONTINENT_IMAGE.read_bytes() and proof==(here/'cartography/continent-atlas.json').read_bytes()
    master.unlink()  # Review master is deliberately absent in a clean checkout.
    assert B.check()==[]
    glb_path=here.parent/'west/world.glb';glb_path.write_bytes(glb_path.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='input is stale'):
        B.check()
