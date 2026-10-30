"""Compact Afro flyaways from preserved source data; no generation calls."""
import os,sys,json,copy,numpy as np,hashlib
from pathlib import Path
import argparse,shutil
import rlglb,assemble,headref
ap=argparse.ArgumentParser(description="Attach compact Afro detail to the nearest curl surface, preserving skinning and grooming")
ap.add_argument('--source',required=True);ap.add_argument('--out',required=True);opts=ap.parse_args()

from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
head=headref.Head('male');source=Path(opts.source);g,blob=rlglb.read(str(source));w=assemble.Writer('Rabbit Lands Afro: compact attached curl wisps');png=source.with_suffix('.png');materials=[]
for mat in g['materials']:
 index=w.material(mat['name'],[1,1,1,1],alpha='MASK',cutoff=.35,double=True,extras=mat.get('extras',{}));w.embed_texture(index,str(png));materials.append(index)
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'wisp_length_factor':.12,'clearance':{},'lods':{}}
for lod,m in enumerate(g['meshes']):
 names=m['extras']['targetNames'];prims=[];allP=[];allD={n:[] for n in names};core=m['primitives'][0];CP=rlglb.accessor(g,blob,core['attributes']['POSITION']);CD=[rlglb.accessor(g,blob,t['POSITION']) for t in core['targets']];tree=cKDTree(CP);total=0
 for pr in m['primitives']:
  a={k:rlglb.accessor(g,blob,i).copy() for k,i in pr['attributes'].items()};T=rlglb.accessor(g,blob,pr['indices']).astype(int).reshape(-1,3);D=[rlglb.accessor(g,blob,t['POSITION']).copy() for t in pr['targets']]
  if g['materials'][pr['material']]['name']=='rl_hair_card':
   edge=T[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edge)),(edge[:,0],edge[:,1])),shape=(len(a['POSITION']),len(a['POSITION']))).tocsr();_,labels=connected_components(graph,directed=False)
   for group in np.unique(labels):
    ids=np.flatnonzero(labels==group);v=a['COLOR_0'][ids,1];roots=ids[v<=v.min()+.05];root=a['POSITION'][roots].mean(0);_,nearest=tree.query(root);a['POSITION'][ids]=CP[nearest]+.12*(a['POSITION'][ids]-root)
    for i in range(len(D)):
     oldroot=D[i][roots].mean(0);D[i][ids]=CD[i][nearest]+.12*(D[i][ids]-oldroot)
  prims.append(w.primitive(a['POSITION'].astype('f4'),a['NORMAL'].astype('f4'),a['TEXCOORD_0'].astype('f4'),T,np.rint(a['COLOR_0']*255).astype('u1'),a['JOINTS_0'].astype('u1'),a['WEIGHTS_0'].astype('f4'),materials[pr['material']],[(d,None) for d in D]));allP.append(a['POSITION']);total+=len(T)
  for n,d in zip(names,D):allD[n].append(d)
 w.mesh(m['name'],prims,names);P=np.concatenate(allP);allD={n:np.concatenate(v) for n,v in allD.items()};ids=head.id_names();grooms=[n for n in names if n.startswith('hl_')];combos=assemble.default_combos(ids)
 for groom in grooms:
  for suffix in ('_p','_n'):combos[groom+'+all_id'+suffix]={n:1 for n in ids if n.endswith(suffix)}|{groom:1}
 combos['groom_min']={'hl_length_n':1,'hl_volume_n':1};hd={n:head.delta(n) for n in ids}|{n:np.zeros_like(head.P) for n in grooms};c=assemble.clearance(head,P,hd,allD,names,combos=combos);assert not c['rest']['violations'] and not c['morphs']['violatingCases'],c['morphs']['violatingCases'];report['clearance'][f'lod{lod}']=c;report['lods'][f'lod{lod}']={'tris':total}
w.g.g['nodes']=copy.deepcopy(g['nodes']);w.g.g['scenes']=copy.deepcopy(g['scenes']);skin=copy.deepcopy(g['skins'][0]);skin['inverseBindMatrices']=w.g.accessor(rlglb.accessor(g,blob,skin['inverseBindMatrices']).astype('f4'),'MAT4');w.g.g['skins']=[skin];w.g.g['asset']['extras']=copy.deepcopy(g['asset']['extras']);out=Path(opts.out);out.mkdir(exist_ok=True);dst=out/'rounded_afro.glb';assert source.resolve()!=dst.resolve();w.save(str(dst));shutil.copy2(png,dst.with_suffix('.png'));dst.with_suffix('.report.json').write_text(json.dumps(report,indent=2));print('COMPACT AFRO WISPS PASS',flush=True)
