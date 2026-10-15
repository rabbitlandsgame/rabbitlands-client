"""Transfer only the source derivative's skinning, retaining approved source art.

Accepts the welded Blender reduction of the original unrigged source. Restores
source normals by matching texture charts and positions, transfers the existing
24-joint derivative's weights, then fits the canonical rig without sleeve sculpt
or normal smoothing. Output is a reviewable authoring candidate.
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from shared_player_bodies import g, append_array, append_view, sparse_weights


def run(original, reduced, donor, library, template, out):
    out.mkdir(parents=True,exist_ok=True)
    sd,sb=g.read(original);sp=sd['meshes'][0]['primitives'][0]
    sa={k:g.accessor(sd,sb,i) for k,i in sp['attributes'].items()}
    rd,rb=g.read(reduced);rp=rd['meshes'][0]['primitives'][0]
    ra={k:g.accessor(rd,rb,i) for k,i in rp['attributes'].items()}
    faces=g.accessor(rd,rb,rp['indices']).astype(int)
    _,ix=cKDTree(sa['TEXCOORD_0']).query(ra['TEXCOORD_0'],k=12,workers=8)
    distance=np.linalg.norm(sa['POSITION'][ix]-ra['POSITION'][:,None],axis=2)
    closest=ix[np.arange(len(ix)),distance.argmin(1)]
    bad=distance.min(1)>.005
    _,closest[bad]=cKDTree(sa['POSITION']).query(ra['POSITION'][bad],workers=8)
    ra['NORMAL']=sa['NORMAL'][closest]
    ra.pop('TANGENT',None)
    restored=bytearray(rb)
    rp['attributes']['NORMAL']=append_array(rd,restored,ra['NORMAL'],'VEC3')
    rp['attributes'].pop('TANGENT',None)
    restored_d,restored_b=g.compact(rd,bytes(restored))
    g.write(out/'source_reduced.glb',restored_d,restored_b)
    dd,db=g.read(donor);dp=dd['meshes'][0]['primitives'][0]
    da={k:g.accessor(dd,db,i) for k,i in dp['attributes'].items()}
    slo,shi=sa['POSITION'].min(0),sa['POSITION'].max(0)
    dlo,dhi=da['POSITION'].min(0),da['POSITION'].max(0)
    scale=(dhi[1]-dlo[1])/(shi[1]-slo[1])
    offset=(dlo+dhi)/2-scale*(slo+shi)/2
    ra['POSITION']=ra['POSITION']*scale+offset
    ddense=np.zeros((len(da['POSITION']),len(dd['skins'][0]['joints'])))
    for col in range(4):
        np.add.at(ddense,(np.arange(len(ddense)),da['JOINTS_0'][:,col].astype(int)),da['WEIGHTS_0'][:,col])
    dist,ix=cKDTree(da['POSITION']).query(ra['POSITION'],k=4,workers=8)
    weight=1/np.maximum(dist,0.00005)**2;weight/=weight.sum(1,keepdims=True)
    dense=(ddense[ix]*weight[:,:,None]).sum(1)
    names=[dd['nodes'][i]['name'] for i in dd['skins'][0]['joints']]
    from luminous_body_weights import repair
    binds=g.accessor(dd,db,dd['skins'][0]['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
    anchors={name:np.linalg.inv(bind)[:3,3] for name,bind in zip(names,binds)}
    dense=repair(ra['POSITION'],dense,names,anchors)
    ra['JOINTS_0'],ra['WEIGHTS_0']=sparse_weights(dense)
    d=copy.deepcopy(dd);binary=bytearray(db)
    mat=copy.deepcopy(sd['materials'][0])
    image=sd['images'][sd['textures'][mat['pbrMetallicRoughness']['baseColorTexture']['index']]['source']]
    view=sd['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
    d['images']=[{'mimeType':image['mimeType'],'bufferView':append_view(d,binary,sb[start:start+view['byteLength']])}]
    d['textures']=[{'source':0}];mat['pbrMetallicRoughness']['baseColorTexture']={'index':0};d['materials']=[mat]
    attrs={k:append_array(d,binary,v,'VEC'+str(v.shape[1]),5123 if k=='JOINTS_0' else 5126) for k,v in ra.items()}
    d['meshes']=[{'name':'approved_source','primitives':[{'attributes':attrs,'indices':append_array(d,binary,faces,'SCALAR',5125),'material':0}]}]
    d,binary=g.compact(d,bytes(binary))
    intermediate=out/'source_weights.glb';g.write(intermediate,d,binary)
    sys.path.insert(0,str(Path(__file__).parent/'tpose_bodies'))
    from build import fit
    fit(intermediate,library,template,out/'canonical_unsplit.glb',preserve_source_shape=True)
    fitted,fb=g.read(out/'canonical_unsplit.glb')
    fitted['asset'].setdefault('extras',{})['bodyWeightRepair']={
        'version':2,'stage':'before canonical fit',
        'regions':['hips','upper back','head boundary'],
        'torsoAnchor':'physical hip centres'}
    g.write(out/'canonical_unsplit.glb',fitted,fb)
    report={'sourceToDerivativeScale':float(scale),'sourceToDerivativeOffset':offset.tolist(),
            'weightDonorDistanceM':dict(zip(['median','p95','maximum'],np.percentile(dist[:,0],[50,95,100]).tolist())),
            'sourceNormalFallbackVertices':int(bad.sum()),'headFollowsOneRigidJoint':True,
            'preserveSourceShape':True}
    (out/'source-rig-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('original','reduced','donor','library','template','out'):
        ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args();run(**vars(args))
