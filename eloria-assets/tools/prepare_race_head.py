"""Extract original high-resolution race art and bind reduced heads to the shared rig."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import equipment_authoring as ea
from shared_player_bodies import g, append_array, copy_materials, write_group, digest
from verify_shared_player_bodies import primitives


def extract(original, donor, template, target):
    d, b = g.read(original)
    p = d['meshes'][0]['primitives'][0]
    a = {k: g.accessor(d, b, v) for k, v in p['attributes'].items() if k != 'TANGENT'}
    f = g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)
    dd, db = g.read(donor)
    dp = dd['meshes'][0]['primitives'][0]
    dv = g.accessor(dd, db, dp['attributes']['POSITION'])
    lo, hi = a['POSITION'].min(0), a['POSITION'].max(0)
    dlo, dhi = dv.min(0), dv.max(0)
    scale = (dhi[1]-dlo[1]) / (hi[1]-lo[1])
    offset = (dlo+dhi)/2-scale*(lo+hi)/2
    names = [dd['nodes'][i]['name'] for i in dd['skins'][0]['joints']]
    ib = g.accessor(dd, db, dd['skins'][0]['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
    source_anchor = np.linalg.inv(ib[names.index('Head')])[:3,3]
    td, tb = g.read(template)
    target_anchor = next(ea.global_matrices(td)[i][:3,3] for i,n in enumerate(td['nodes']) if n.get('name')=='Head')
    a['POSITION'] = a['POSITION']*scale+offset+target_anchor-source_anchor
    centres = a['POSITION'][f].mean(1)
    kept = (centres[:,1] > 1.34) & (abs(centres[:,0]) < .28)
    f = f[kept]
    used, inverse = np.unique(f, return_inverse=True)
    binary = bytearray(b)
    attrs = {k: append_array(d,binary,v[used],'VEC'+str(v.shape[1])) for k,v in a.items()}
    d['meshes'] = [{'name':'SourceHead','primitives':[{'attributes':attrs,'indices':append_array(d,binary,inverse.ravel(),'SCALAR',5125),'material':0}]}]
    d['nodes'] = [{'name':'SourceHead','mesh':0}]
    d['scenes'] = [{'nodes':[0]}];d['scene']=0
    d.pop('skins',None);d.pop('animations',None)
    d['asset'].setdefault('extras',{})['highResolutionHead'] = {
        'original':original.name,'originalSHA256':digest(original),'sourceTriangles':len(kept),
        'extractedTriangles':len(f),'scale':float(scale),'headTranslationM':(offset+target_anchor-source_anchor).tolist()}
    d,binary=g.compact(d,bytes(binary));target.parent.mkdir(parents=True,exist_ok=True);g.write(target,d,binary)
    print(original.name,len(f),'head triangles',flush=True)


def bind(extracted, reduced, template, semantic_source, target):
    hd,hb=g.read(extracted);hp=hd['meshes'][0]['primitives'][0]
    ha={k:g.accessor(hd,hb,v) for k,v in hp['attributes'].items()}
    rd,rb=g.read(reduced);rp=rd['meshes'][0]['primitives'][0]
    a={k:g.accessor(rd,rb,v) for k,v in rp['attributes'].items() if k in ('POSITION','NORMAL','TEXCOORD_0')}
    f=g.accessor(rd,rb,rp['indices']).astype(int).reshape(-1,3)
    _,ix=cKDTree(ha['TEXCOORD_0']).query(a['TEXCOORD_0'],k=12,workers=8)
    distance=np.linalg.norm(ha['POSITION'][ix]-a['POSITION'][:,None],axis=2)
    closest=ix[np.arange(len(ix)),distance.argmin(1)]
    bad=distance.min(1)>.005
    _,closest[bad]=cKDTree(ha['POSITION']).query(a['POSITION'][bad],workers=8)
    a['NORMAL']=ha['NORMAL'][closest]
    d,b=g.read(template);binary=bytearray(b)
    names=[d['nodes'][i]['name'] for i in d['skins'][0]['joints']]
    a['JOINTS_0']=np.zeros((len(a['POSITION']),4),dtype='u2');a['JOINTS_0'][:,0]=names.index('Head')
    a['WEIGHTS_0']=np.zeros((len(a['POSITION']),4));a['WEIGHTS_0'][:,0]=1
    # Previous head regions supply semantic membership only; all geometry,
    # normals, UVs and pigment come from the high-resolution source.
    sd,sb=g.read(semantic_source);centres=[];labels=[]
    for name,role,attrs,faces in primitives(sd,sb):
        if role=='race_head' and name in ('body','eyes','eyebrows','scalp'):
            centres.append(attrs['POSITION'][faces].mean(1));labels.extend([name]*len(faces))
    _,nearest=cKDTree(np.concatenate(centres)).query(a['POSITION'][f].mean(1),workers=8)
    chosen=np.asarray(labels)[nearest]
    mapping=copy_materials(d,binary,hd,hb)
    group={'a':a,'f':{(name,mapping[0]):f[chosen==name] for name in np.unique(chosen)},'role':'race_head'}
    meshes={};write_group(d,binary,group,meshes)
    for node in d['nodes']:
        if node.get('name') in ('wardrobe_head_band','wardrobe_head_cap') and 'mesh' in node:
            meshes[node['name']]=copy.deepcopy(d['meshes'][node['mesh']]['primitives'])
    # Reuse only the canonical hierarchy and inverse binds from the body.
    parent=next(i for i,n in enumerate(d['nodes']) if any('mesh' in d['nodes'][j] for j in n.get('children',[])))
    old_nodes={n['name']:i for i,n in enumerate(d['nodes']) if 'mesh' in n}
    for n in d['nodes']:n.pop('mesh',None);n.pop('skin',None)
    d['meshes']=[]
    for name,ps in meshes.items():
        d['meshes'].append({'name':name,'primitives':ps})
        if name in old_nodes:
            d['nodes'][old_nodes[name]].update(mesh=len(d['meshes'])-1,skin=0)
        else:
            d['nodes'].append({'name':name,'mesh':len(d['meshes'])-1,'skin':0})
            d['nodes'][parent].setdefault('children',[]).append(len(d['nodes'])-1)
    d['asset']['extras']={'highResolutionHead':hd['asset']['extras']['highResolutionHead']}
    d,binary=g.compact(d,bytes(binary));g.write(target,d,binary)
    print(target.name,len(f),'reduced triangles',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['extract','bind'])
    for name in ('original','donor','template','target','extracted','reduced','semantic-source'):
        parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    if args.action=='extract':extract(args.original,args.donor,args.template,args.target)
    else:bind(args.extracted,args.reduced,args.template,args.semantic_source,args.target)
