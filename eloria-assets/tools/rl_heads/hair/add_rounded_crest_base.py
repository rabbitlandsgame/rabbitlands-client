"""Add a dense rounded lower crest while retaining reviewed upper locks.

This is an optional unregistered authoring stage. It does not perform fitting,
qualification, runtime replacement or provider calls. Keep source stages.
"""
from pathlib import Path
import argparse, copy, json
import numpy as np
import trimesh
import paths, rlglb, glbwriter, headref, hairgen, assemble
from build_short_reference import BoundedHead, closest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--profile',default=str(Path(__file__).parent/'styles/feathered_mohawk.json'))
    parser.add_argument('--sex',choices=['female','male'])
    args=parser.parse_args()
    root=Path(paths.WORKTREE)
    source_root=Path(args.source);outdir=Path(args.output);assert not outdir.exists();outdir.mkdir(parents=True);profile=json.loads(Path(args.profile).read_text());guides=profile['guide_samples'];gz=np.array([r['z_m'] for r in guides]);gh=np.array([r['source_profile_y_m']-r['cap_root_y_m'] for r in guides]);reports=[]
    for sex in ([args.sex] if args.sex else ['female','male']):
     source=source_root/f'feathered_mohawk_{sex}.glb';g,b=rlglb.read(str(source));w=glbwriter.GLB();w.g=copy.deepcopy(g);w.blob=bytearray(b);head=BoundedHead(sex)
     for lod,mesh in enumerate(w.g['meshes']):
      cap=g['meshes'][lod]['primitives'][0];A=rlglb.accessor(g,b,cap['attributes']['POSITION']);AN=rlglb.accessor(g,b,cap['attributes']['NORMAL']);AC=rlglb.accessor(g,b,cap['attributes']['COLOR_0']);AT=rlglb.accessor(g,b,cap['indices']).reshape(-1,3).astype(int);end=cap['extras']['partVertexRanges']['reference'][1];faces=AT[(AT<end).all(1)&(AC[AT,0]>=.35).all(1)];faces=faces[np.einsum('ij,ij->i',AN[faces].mean(1),A[faces].mean(1)-head.C)>0];surface=trimesh.Trimesh(A,faces,process=False);n,k=[(23,8),(16,6),(10,4)][lod];u=np.linspace(0,1,n);z=np.linspace(.085,-.105,n);CP=[];normal=[]
      for at in z:
       hits,_,fi=surface.ray.intersects_location(np.array([[0.,2.,at]]),np.array([[0.,-1.,0.]]),multiple_hits=True);point=hits[np.argmax(hits[:,1])] if len(hits) else closest(surface,np.array([[0.,1.8,at]]))[0][0];q,_,tri=closest(surface,point[None]);tv=faces[tri];bc=headref.barycentric(q,A[tv[:,0]],A[tv[:,1]],A[tv[:,2]]);CP.append(q[0]);normal.append(headref.unit((AN[tv]*bc[:,:,None]).sum(1))[0])
      CP=np.asarray(CP);normal=np.asarray(normal);envelope=hairgen.smoothstep(u/.11)*hairgen.smoothstep((1-u)/.11);height=(np.clip(np.interp(z,gz,gh)*.33+.002,.009,.015)*(.96+.04*np.sin(u*17)))*envelope+.00010;width=(.0175+.0015*np.sin(u*11))*envelope+.0003;C=CP+normal*(height[:,None]/2-.00003);P,N,UV,T,along=hairgen.tube_mesh(C,normal,width,height,k,inner_flat=1,u_rep=.78,uoff=.23,tip_point=True,t_param=u)
      # Front disk is hidden inside the exact cap; no open arbitrary cut surface.
      centre=len(P);P=np.vstack([P,C[:1]]);N=np.vstack([N,-hairgen.tangents(C)[:1]]);UV=np.vstack([UV,UV[:k+1].mean(0)]);along=np.r_[along,0];T=np.vstack([T,[[centre,j+1,j] for j in range(k)]]);nearest,_,tri=closest(surface,P);tv=faces[tri];bc=headref.barycentric(nearest,A[tv[:,0]],A[tv[:,1]],A[tv[:,2]]);capn=headref.unit((AN[tv]*bc[:,:,None]).sum(1));depth=np.einsum('ij,ij->i',P-nearest,capn);colors=np.c_[hairgen.smoothstep(np.clip((depth+.00003)/.0017,0,1)),np.full(len(P),.2),np.full(len(P),.96),np.ones(len(P))];relative=P-nearest;_,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True);names=mesh['extras']['targetNames'];Dnew=[];DNnew=[]
      for i,name in enumerate(names):
       D=(rlglb.accessor(g,b,cap['targets'][i]['POSITION'])[tv]*bc[:,:,None]).sum(1)
       if name=='hl_length_p':D+=relative*.50
       if name=='hl_length_n':D-=relative*.30
       if name in ['hl_volume_p','hl_volume_n']:
        amount=.42 if name.endswith('_p') else -.28;fade=hairgen.smoothstep(np.clip(np.linalg.norm(relative,axis=1)/.014,0,1));D[:,0]+=(P[:,0]*.7+relative[:,0]*.3)*amount*fade;D[:,2]+=relative[:,2]*amount*.15*fade
       Dnew.append(D);DNnew.append(assemble.morph_normals(P,T,N,D,weld))
      p=mesh['primitives'][2];old=g['meshes'][lod]['primitives'][2];keep=609 if lod==2 else g['accessors'][old['attributes']['POSITION']]['count'];oldT=rlglb.accessor(g,b,old['indices']).reshape(-1,3).astype(int);oldT=oldT[(oldT<keep).all(1)];J=np.zeros((len(P),4),dtype='u1');W=np.zeros((len(P),4));W[:,0]=1;new_values={'POSITION':P,'NORMAL':N,'TEXCOORD_0':UV,'COLOR_0':colors,'JOINTS_0':J,'WEIGHTS_0':W}
      for semantic,extra in new_values.items():
       values=np.vstack([rlglb.accessor(g,b,old['attributes'][semantic],normalize=semantic!='JOINTS_0')[:keep],extra]);kind={'POSITION':'VEC3','NORMAL':'VEC3','TEXCOORD_0':'VEC2','COLOR_0':'VEC4','JOINTS_0':'VEC4','WEIGHTS_0':'VEC4'}[semantic];kw={'target':34962}
       if semantic=='COLOR_0':values=np.rint(np.clip(values,0,1)*255).astype('u1');kw.update(comp=5121,normalized=True)
       if semantic=='JOINTS_0':values=values.astype('u1');kw.update(comp=5121)
       if semantic=='POSITION':kw.update(minmax=True)
       p['attributes'][semantic]=w.accessor(values,kind,**kw)
      p['indices']=w.accessor(np.vstack([oldT,T+keep]).reshape(-1),'SCALAR',comp=5123,target=34963)
      for i in range(len(names)):
       p['targets'][i]={'POSITION':w.sparse_vec3(np.vstack([rlglb.accessor(g,b,old['targets'][i]['POSITION'])[:keep],Dnew[i]]),eps=0),'NORMAL':w.sparse_vec3(np.vstack([rlglb.accessor(g,b,old['targets'][i]['NORMAL'])[:keep],DNnew[i]]))}
      p['extras']['partVertexRanges']={'reference':[0,keep+len(P)],'approvedUpperLocks':[0,keep],'denseBasalRidge':[keep,keep+len(P)]};reports.append({'sex':sex,'lod':lod,'ridge_triangles':len(T),'upper_triangles':len(oldT),'crest_triangles':len(oldT)+len(T),'removed_far_fine_locks':8 if lod==2 else 0})
     info=w.g['asset']['extras']['rlHair'];info['tris']={f'lod{i}':sum(w.g['accessors'][p['indices']]['count']//3 for p in m['primitives']) for i,m in enumerate(w.g['meshes'])};info['source']['denseBasalPolish']=True;out=outdir/source.name;w.save(str(out));h,bb=rlglb.read(str(out));assert bb[:len(b)]==b
     for lod in range(3):
      assert h['meshes'][lod]['primitives'][:2]==g['meshes'][lod]['primitives'][:2];keep=609 if lod==2 else g['accessors'][g['meshes'][lod]['primitives'][2]['attributes']['POSITION']]['count'];old=g['meshes'][lod]['primitives'][2];new=h['meshes'][lod]['primitives'][2]
      for semantic in new_values:assert np.array_equal(rlglb.accessor(g,b,old['attributes'][semantic],normalize=semantic!='JOINTS_0')[:keep],rlglb.accessor(h,bb,new['attributes'][semantic],normalize=semantic!='JOINTS_0')[:keep])
      for i in range(len(names)):
       for field in ['POSITION','NORMAL']:assert np.array_equal(rlglb.accessor(g,b,old['targets'][i][field])[:keep],rlglb.accessor(h,bb,new['targets'][i][field])[:keep])
     print('ROUND_BASAL_POLISH',sex,info['tris'],flush=True)
    (outdir/'feathered_mohawk_crest_round.png').write_bytes((source.parent/'feathered_mohawk_crest_round.png').read_bytes());(outdir/'receipt.json').write_text(json.dumps({'qualified':False,'upper_geometry_all51targets_prefix_exact':True,'qualified_cap_exact':True,'records':reports},indent=2));print('ROUND_BASAL_READY',flush=True)


if __name__ == "__main__":
    main()
