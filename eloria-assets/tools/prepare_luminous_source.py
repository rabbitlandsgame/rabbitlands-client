"""Separate the approved original into editable texture/material groups.

Source vertices, normals, tangents, faces and painted pixels are retained.
Only mesh membership and each group's affine UV crop change. This is an
authoring base, independent of the previous generated-body refinements.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies/vendor'))
import glbkit as g
from shared_player_bodies import append_array, append_view

GROUPS = ('body', 'eyes', 'eyebrows', 'scalp', 'wardrobe_shirt',
          'wardrobe_pants', 'wardrobe_boots')
COLOURS = ((.88,.57,.43), (.15,.7,1), (.4,.15,.6), (.95,.6,.15),
           (.15,.75,.4), (.2,.35,.85), (.85,.25,.25))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sample_pixels(pixels, uv):
    size = np.array([pixels.shape[1], pixels.shape[0]])
    coords = np.clip((uv * size).astype(int), 0, size - 1)
    return pixels[coords[:,1], coords[:,0]].astype(float) / 255


def classify(v, uv, faces, pixels, sex='male'):
    # Classification coordinates only. Exported coordinates are not touched.
    female=sex=='female'
    offset=[0,.9521999955,.0030060038] if female else [0,.952162981,.010976493]
    height=1.9029639959 if female else 1.902911961
    c = (v[faces].mean(1) + offset) * (1.7/height)
    rgb = sample_pixels(pixels, uv[faces].mean(1))
    x, y, z = c.T
    chroma = rgb / np.maximum(rgb.sum(1, keepdims=True), .001)
    skin = np.array([.9686,.7922,.6510] if female else [.7608,.6353,.5373]); skin /= skin.sum()
    cloth = np.array([.1176,.3176,.3882] if female else [.949,.871,.776]); cloth /= cloth.sum()
    skin_near = np.linalg.norm(chroma-skin,axis=1) < np.linalg.norm(chroma-cloth,axis=1)
    labels = np.zeros(len(faces), dtype='u1')
    labels[y < 1.09] = GROUPS.index('wardrobe_pants')
    boot_colour=(rgb[:,0] > rgb[:,2]*1.8) if female else (rgb[:,2] < rgb[:,0]*1.12)
    boots = (y < .43) & (boot_colour | (y < .04))
    labels[boots] = GROUPS.index('wardrobe_boots')
    shirt = (y > 1.025) & (y < 1.49) & (abs(x) < .612)
    # Skin exposed through the open neckline and at either cuff stays skin.
    neckline = (abs(x) < .08) & (y > 1.32) & skin_near
    cuffs = (abs(x) > .40) & skin_near
    shirt &= ~neckline & ~cuffs
    labels[shirt] = GROUPS.index('wardrobe_shirt')
    labels[(y > 1.49) | (abs(x) > .612) | neckline | cuffs] = 0
    labels[y > 1.627] = GROUPS.index('scalp')
    eye_x,eye_rx,eye_z=(.033,.022,.032) if female else (.032,.019,.048)
    eye_zone = (((abs(x)-eye_x)/eye_rx)**2 + ((y-1.5827)/.009)**2 < 1) & (z > eye_z)
    neutral = (rgb.max(1)-rgb.min(1)) < .17
    labels[eye_zone & (neutral | (rgb[:,2] > rgb[:,0]))] = GROUPS.index('eyes')
    # Original brow region, including its pale source pigment. No invented
    # dark eyebrow paint is added to this deliberately source-preserving base.
    brow_y,brow_rx,brow_ry=(1.603,.026,.007) if female else (1.601,.023,.004)
    brows = (((abs(x)-.032)/brow_rx)**2 + ((y-brow_y)/brow_ry)**2 < 1) & (z > .048)
    labels[brows] = GROUPS.index('eyebrows')
    return labels


def run(source, out, reuse_labels=None, sex='male'):
    out.mkdir(parents=True, exist_ok=True)
    d,b = g.read(source)
    source_d = copy.deepcopy(d)
    mesh_nodes = [n for n in d['nodes'] if 'mesh' in n]
    assert len(mesh_nodes)==1 and len(d['meshes'][mesh_nodes[0]['mesh']]['primitives'])==1
    node = mesh_nodes[0]
    p = d['meshes'][node['mesh']]['primitives'][0]
    a = {k:g.accessor(d,b,i) for k,i in p['attributes'].items()}
    faces = g.accessor(d,b,p['indices']).astype(int).reshape(-1,3)
    material = d['materials'][p.get('material',0)]
    texid=material['pbrMetallicRoughness']['baseColorTexture']['index']
    im=d['images'][d['textures'][texid]['source']]
    bv=d['bufferViews'][im['bufferView']]; start=bv.get('byteOffset',0)
    source_image=Image.open(io.BytesIO(b[start:start+bv['byteLength']])).convert('RGB')
    pixels=np.asarray(source_image); h,w=pixels.shape[:2]
    labels=(np.load(reuse_labels) if reuse_labels else
            classify(a['POSITION'],a['TEXCOORD_0'],faces,pixels,sex))
    assert labels.shape == (len(faces),)
    np.save(out/'triangle-groups.npy',labels)
    source_image.save(out/'original-atlas.png')
    d['meshes']=[]; d['materials']=[]; d['textures']=[]; d['images']=[]
    source_skin=node.pop('skin',None)
    node.pop('mesh')
    node['name']='Luminous'+sex.title()+'Source'; node['children']=[]
    binary=bytearray(b)
    reports={}
    assignments=[]
    for index,name in enumerate(GROUPS):
        indices=np.flatnonzero(labels==index)
        assert len(indices), name
        used,remap=np.unique(faces[indices],return_inverse=True)
        ff=remap.reshape(-1,3)
        uv=a['TEXCOORD_0'][used]
        lo=np.maximum(np.floor(uv.min(0)*[w,h]).astype(int)-16,0)
        hi=np.minimum(np.ceil(uv.max(0)*[w,h]).astype(int)+16,[w,h])
        cropped=source_image.crop((*lo,*hi))
        size=hi-lo
        local_uv=(uv*[w,h]-lo)/size
        mask=Image.new('L',tuple(size),0); draw=ImageDraw.Draw(mask)
        coords=local_uv*size
        for f in ff:
            draw.polygon([tuple(q) for q in coords[f]],fill=255)
        mask.save(out/(name+'_mask.png'))
        # Outside this group's charts retain source RGB, with transparent
        # alpha for authoring. Runtime materials are opaque, as in the source.
        rgba=cropped.convert('RGBA'); rgba.putalpha(mask.filter(ImageFilter.MaxFilter(17)))
        rgba.save(out/(name+'_basecolor.png'))
        stream=io.BytesIO(); rgba.save(stream,format='PNG')
        view=append_view(d,binary,stream.getvalue())
        d['images'].append({'name':name+'_basecolor','bufferView':view,'mimeType':'image/png'})
        d['textures'].append({'source':index, 'sampler':0})
        mat=copy.deepcopy(material); mat['name']=name
        mat['pbrMetallicRoughness']['baseColorTexture']={'index':index}
        d['materials'].append(mat)
        attrs={}
        for key,values in a.items():
            data=local_uv if key=='TEXCOORD_0' else values[used]
            attrs[key]=append_array(d,binary,data,'VEC'+str(data.shape[1]),5123 if key=='JOINTS_0' else 5126)
        primitive={'attributes':attrs,'indices':append_array(d,binary,ff.reshape(-1),'SCALAR',5125),
                   'material':index,'extras':{'sourceRole':'approved_source','appearanceGroup':name}}
        d['meshes'].append({'name':name,'primitives':[primitive]})
        child={'name':name,'mesh':index}
        if source_skin is not None:
            child['skin']=source_skin
        d['nodes'].append(child)
        node['children'].append(len(d['nodes'])-1)
        np.savez_compressed(out/(name+'_source-map.npz'),vertices=used,triangles=indices)
        assignments.extend(indices.tolist())
        reports[name]={'triangles':len(ff),'vertices':len(used),'textureSize':size.tolist(),
                       'atlasCrop':[int(x) for x in (*lo,*hi)]}
    assert np.array_equal(np.sort(assignments),np.arange(len(faces)))
    d['samplers']=[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]
    d.setdefault('asset',{}).setdefault('extras',{}).update({'approvedSourceSHA256':digest(source),
        'geometryPreserved':True,'textureGroups':list(GROUPS)})
    d,binary=g.compact(d,bytes(binary))
    target=out/('luminous_'+sex+'.glb');g.write(target,d,binary)
    # Independent serialization checks recover source UVs and compare every
    # exported triangle corner, normal and tangent to its source counterpart.
    check,blob=g.read(target)
    max_uv_error=0.
    for name,m in zip(GROUPS,check['meshes']):
        mapping=np.load(out/(name+'_source-map.npz'))
        cp=m['primitives'][0]
        ci=check['images'][check['textures'][check['materials'][cp['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']]
        cv=check['bufferViews'][ci['bufferView']]; start=cv.get('byteOffset',0)
        decoded=np.asarray(Image.open(io.BytesIO(blob[start:start+cv['byteLength']])).convert('RGB'))
        x0,y0,x1,y1=reports[name]['atlasCrop']
        np.testing.assert_array_equal(decoded,pixels[y0:y1,x0:x1])
        cf=g.accessor(check,blob,cp['indices']).astype(int).reshape(-1,3)
        np.testing.assert_array_equal(mapping['vertices'][cf],faces[mapping['triangles']])
        for key in a:
            result=g.accessor(check,blob,cp['attributes'][key])
            if key=='TEXCOORD_0':
                crop=np.array(reports[name]['atlasCrop']); size=crop[2:]-crop[:2]
                result=(result*size+crop[:2])/[w,h]
                max_uv_error=max(max_uv_error,float(abs(result-a[key][mapping['vertices']]).max()))
                assert max_uv_error<1e-7
            else:
                np.testing.assert_array_equal(result,a[key][mapping['vertices']])
    report={'source':str(source.resolve()),'sourceSHA256':digest(source),'sex':sex,
        'outputSHA256':digest(target),'triangles':len(faces),'groups':reports,
        'geometryAndNormalsExactlyPreserved':True,'sourcePixelsPreserved':True,
        'maximumRecoveredUVError':max_uv_error,'rigged':bool(source_d.get('skins'))}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--labels',type=Path,help='Reuse source triangle assignments after rig fitting')
    p.add_argument('--sex',choices=['male','female'],default='male')
    args=p.parse_args();run(args.source,args.out,args.labels,args.sex)
