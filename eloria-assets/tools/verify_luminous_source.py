"""Independently verify serialized source partitions and matched Godot renders."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).parent/'tpose_bodies/vendor'))
import glbkit as g


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixels(d,b,material):
    texture=d['materials'][material]['pbrMetallicRoughness']['baseColorTexture']['index']
    im=d['images'][d['textures'][texture]['source']]
    view=d['bufferViews'][im['bufferView']];start=view.get('byteOffset',0)
    return np.asarray(Image.open(io.BytesIO(b[start:start+view['byteLength']])).convert('RGB'))


def run(root,sex):
    report={}
    for folder in ('master','reduced-grouped','rigged'):
        path=root/folder
        manifest=json.loads((path/'manifest.json').read_text())
        assert digest(manifest['source'])==manifest['sourceSHA256']
        sd,sb=g.read(manifest['source']);sp=sd['meshes'][0]['primitives'][0]
        sa={k:g.accessor(sd,sb,a) for k,a in sp['attributes'].items()}
        sf=g.accessor(sd,sb,sp['indices']).astype(int).reshape(-1,3)
        source_pixels=pixels(sd,sb,sp.get('material',0));h,w=source_pixels.shape[:2]
        model=path/('luminous_'+sex+'.glb')
        assert digest(model)==manifest['outputSHA256']
        d,b=g.read(model);assigned=[];uv_error=0.
        for mesh in d['meshes']:
            name=mesh['name'];p=mesh['primitives'][0]
            mapping=np.load(path/(name+'_source-map.npz'))
            faces=g.accessor(d,b,p['indices']).astype(int).reshape(-1,3)
            np.testing.assert_array_equal(mapping['vertices'][faces],sf[mapping['triangles']])
            assigned.extend(mapping['triangles'].tolist())
            x0,y0,x1,y1=manifest['groups'][name]['atlasCrop']
            for key,source in sa.items():
                result=g.accessor(d,b,p['attributes'][key])
                if key=='TEXCOORD_0':
                    result=(result*[x1-x0,y1-y0]+[x0,y0])/[w,h]
                    uv_error=max(uv_error,float(abs(result-source[mapping['vertices']]).max()))
                    assert uv_error<1e-7
                else:
                    np.testing.assert_array_equal(result,source[mapping['vertices']])
            np.testing.assert_array_equal(pixels(d,b,p['material']),source_pixels[y0:y1,x0:x1])
        np.testing.assert_array_equal(np.sort(assigned),np.arange(len(sf)))
        if sd.get('skins'):
            for before,after in zip(sd['skins'],d['skins']):
                assert before['joints']==after['joints']
                np.testing.assert_array_equal(g.accessor(sd,sb,before['inverseBindMatrices']),g.accessor(d,b,after['inverseBindMatrices']))
                for joint in before['joints']:
                    assert sd['nodes'][joint]==d['nodes'][joint]
        report[folder]={'sourceSHA256':manifest['sourceSHA256'],'outputSHA256':digest(model),
            'triangles':len(sf),'groups':len(d['meshes']),
            'geometryNormalsWeightsAndSourceRGB':'exact after serialization','maximumRecoveredUVError':uv_error}
    for view in ('face-front','face-three-quarter','face-profile','back','full-front','full-back'):
        a=np.asarray(Image.open(root/'source'/(view+'.png'))).astype(float)
        b=np.asarray(Image.open(root/'master-review'/(view+'.png'))).astype(float)
        delta=abs(a-b)
        assert delta.mean()<.05, 'Source appearance changed: '+view
        report.setdefault('matchedMasterRenders',{})[view]={'meanChannelDifference':float(delta.mean()),'p99ChannelDifference':float(np.percentile(delta,99))}
    report['rig']=json.loads((root/'rig-verification.json').read_text())
    assert report['rig']['sha256']==report['rigged']['outputSHA256']
    assert not report['rig']['errors']
    (root/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'sex':sex,'groups':7,'riggedTriangles':report['rigged']['triangles'],
        'sourcePreservation':'passed','rigErrors':report['rig']['errors'],
        'rigWarnings':report['rig']['warnings'],'maximumMeanRenderDifference':max(x['meanChannelDifference'] for x in report['matchedMasterRenders'].values())},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--sex',choices=['male','female'],required=True)
    args=ap.parse_args();run(**vars(args))
