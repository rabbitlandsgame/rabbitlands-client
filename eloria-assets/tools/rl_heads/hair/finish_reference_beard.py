"""Finish reference beards from preserved inputs; no service calls.
Run with RL_HEADS_BUILD and RL_MPFB_GROUPS for the current head snapshot.
"""
import os,sys,json,copy,hashlib,shutil,numpy as np
from pathlib import Path
from PIL import Image
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import argparse
import assemble,rlglb,headref,hairgen
ap=argparse.ArgumentParser(description="Combine a qualified reference beard core with collision-filtered existing whiskers")
ap.add_argument('--core',required=True);ap.add_argument('--whiskers',required=True);ap.add_argument('--strands',required=True);ap.add_argument('--out',required=True);ap.add_argument('--styles',default='short_beard,full_beard')
args=ap.parse_args();head=headref.Head('male');out=Path(args.out);out.mkdir(parents=True,exist_ok=True)

def read(g,blob,p):
 a={k:rlglb.accessor(g,blob,i) for k,i in p['attributes'].items()};T=rlglb.accessor(g,blob,p['indices']).astype(int).reshape(-1,3);D=[rlglb.accessor(g,blob,t['POSITION']) for t in p['targets']];return a,T,D
for name in args.styles.split(','):
 print('WHISKER FINISH',name,flush=True)
 source=Path(args.core)/(name+'.glb');assert source.resolve()!=(out/(name+'.glb')).resolve();g,blob=rlglb.read(str(source));old,ob=rlglb.read(str(Path(args.whiskers)/(name+'.glb')))
 atlas=Image.new('RGBA',(1024,1024),(160,160,160,255));atlas.paste(Image.open(source.with_suffix('.png')).convert('RGBA').resize((1024,666)),(0,0));atlas.paste(Image.open(args.strands).convert('RGBA').resize((1024,358)),(0,666));png=out/(name+'.png');atlas.save(png)
 w=assemble.Writer('Rabbit Lands reference beard with attached whisker finish');mat=w.material('rl_beard',[1,1,1,1],alpha='MASK',cutoff=.35,double=True,extras={'texture':name+'.png','referenceSurface':True,'softHairline':True});w.embed_texture(mat,str(png));report={'style':name,'source_core_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_whiskers_sha256':hashlib.sha256((Path(args.whiskers)/(name+'.glb')).read_bytes()).hexdigest(),'lods':{},'clearance':{}}
 for lod,m in enumerate(g['meshes']):
  a,T,D=read(g,blob,m['primitives'][0]);c,CT,CD=read(old,ob,old['meshes'][lod]['primitives'][0]);names=m['extras']['targetNames'];assert names==old['meshes'][lod]['extras']['targetNames'];mask=(c['TEXCOORD_0'][CT,0]<.748).all(1);CT=CT[mask]
  edge=CT[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edge)),(edge[:,0],edge[:,1])),shape=(len(c['POSITION']),len(c['POSITION']))).tocsr();_,labels=connected_components(graph,directed=False);groups=labels[CT[:,0]];ids=np.unique(groups);centres=np.array([c['POSITION'][np.unique(CT[groups==x])].mean(0) for x in ids]);order=hairgen.farthest_order(centres);budget=[2200,900,300][lod];keep=np.zeros(len(CT),bool);total=0
  for rank in order:
   selected=groups==ids[rank];n=int(selected.sum())
   if total+n<=budget:keep|=selected;total+=n
  CT=CT[keep];used,inv=np.unique(CT,return_inverse=True);CT=inv.reshape(-1,3)
  for key in c:c[key]=c[key][used]
  CD=[x[used] for x in CD];card_labels=labels[used];c['COLOR_0'][:,0]=1
  tree=cKDTree(a['POSITION'])
  for group in np.unique(card_labels):
   ci=np.flatnonzero(card_labels==group);v=c['COLOR_0'][ci,1];roots=ci[v<=v.min()+.05];root=c['POSITION'][roots].mean(0);_,nearest=tree.query(root);c['POSITION'][ci]=a['POSITION'][nearest]+.1*(c['POSITION'][ci]-root)
   c['JOINTS_0'][ci]=a['JOINTS_0'][nearest];c['WEIGHTS_0'][ci]=a['WEIGHTS_0'][nearest]
   for k in range(len(CD)):
    oldroot=CD[k][roots].mean(0);CD[k][ci]=D[k][nearest]+.1*(CD[k][ci]-oldroot)
  a['TEXCOORD_0'][:,1]*=665/1024;c['TEXCOORD_0'][:,1]=(666.5+356.5*c['TEXCOORD_0'][:,1])/1024
  count=len(a['POSITION']);T=np.vstack([T,CT+count]);attrs={key:np.concatenate([a[key],c[key]]) for key in a};deltas=[np.concatenate([x,y]) for x,y in zip(D,CD)]
  hd={n:head.delta(n) for n in names};dv=dict(zip(names,deltas));ids_names=[n for n in names if n.startswith('id_')];combos=assemble.default_combos(ids_names);combos['jaw_open+smile']={'ex_jaw_open':1,'ex_smile':1}
  report['clearance'][f'lod{lod}']=assemble.clearance(head,attrs['POSITION'],hd,dv,[n for n in names if n.startswith(('id_','ex_'))],combos=combos);report['lods'][f'lod{lod}']={'tris':len(T),'whiskerTris':len(CT)}
  failed=report['clearance'][f'lod{lod}']['morphs']['violatingCases'][:];bad_groups=set()
  if report['clearance'][f'lod{lod}']['rest']['violations']:failed.append({'case':'rest'})
  for case in failed:
   weights={} if case['case']=='rest' else (combos[case['case']] if case['case'] in combos else {case['case']:1})
   dh=sum((head.delta(n)*v for n,v in weights.items()),np.zeros_like(head.P));dp=sum((dv[n]*v for n,v in weights.items()),np.zeros_like(attrs['POSITION']));sd,_,_,rim=head.signed(attrs['POSITION']+dp,D=dh,with_rim=True);bad=np.flatnonzero((sd<.002)&~rim)
   bad=bad[bad>=count]  # This pass selects safe cards; the unchanged core has its own qualified report.
   bad_groups.update(card_labels[bad-count].tolist())
  if bad_groups:
   keep_tri=~np.isin(card_labels[CT[:,0]],list(bad_groups));CT=CT[keep_tri];T=np.vstack([T[(T<count).all(1)],CT+count]);used,inv=np.unique(T,return_inverse=True);T=inv.reshape(-1,3);attrs={k:v[used] for k,v in attrs.items()};deltas=[x[used] for x in deltas];dv=dict(zip(names,deltas));report['clearance'][f'lod{lod}']=assemble.clearance(head,attrs['POSITION'],hd,dv,[n for n in names if n.startswith(('id_','ex_'))],combos=combos)
  assert not report['clearance'][f'lod{lod}']['rest']['violations'] and not report['clearance'][f'lod{lod}']['morphs']['violatingCases'],report['clearance'][f'lod{lod}']
  report['lods'][f'lod{lod}'].update(tris=len(T),whiskerTris=len(CT),discarded_collision_cards=len(bad_groups))
  prim=w.primitive(attrs['POSITION'].astype('f4'),attrs['NORMAL'].astype('f4'),attrs['TEXCOORD_0'].astype('f4'),T,np.rint(attrs['COLOR_0']*255).astype('u1'),attrs['JOINTS_0'].astype('u1'),attrs['WEIGHTS_0'].astype('f4'),mat,[(x,None) for x in deltas]);w.mesh(m['name'],[prim],names)

 w.g.g['nodes']=copy.deepcopy(g['nodes']);w.g.g['scenes']=copy.deepcopy(g['scenes']);skin=copy.deepcopy(g['skins'][0]);skin['inverseBindMatrices']=w.g.accessor(rlglb.accessor(g,blob,skin['inverseBindMatrices']).astype('f4'),'MAT4');w.g.g['skins']=[skin];w.g.g['asset']['extras']=copy.deepcopy(g['asset']['extras']);w.g.g['asset']['extras']['rlBeard']['tris']={k:v['tris'] for k,v in report['lods'].items()};dst=out/(name+'.glb');w.save(str(dst));dst.with_suffix('.report.json').write_text(json.dumps(report,indent=2));print('WHISKER RESULT',name,{k:len(v['morphs']['violatingCases']) for k,v in report['clearance'].items()},flush=True)
