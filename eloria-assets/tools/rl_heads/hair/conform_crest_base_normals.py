"""Optional front underlayer normal conformance to the actual opaque cap.

Only the explicit denseBasalRidge range is eligible. All collision positions,
indices, UVs, coverage and skin data stay exact. This is authoring, not a new
runtime shader policy or a substitute for visual/physical qualification.
"""
from pathlib import Path
import argparse, copy, json, hashlib
import numpy as np
import trimesh
import paths, rlglb, glbwriter, headref, assemble
from build_short_reference import BoundedHead, closest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--sex',choices=['female','male'])
    args=parser.parse_args()
    root=Path(paths.WORKTREE)
    source_root=Path(args.source);outdir=Path(args.output);assert not outdir.exists();outdir.mkdir(parents=True);reports=[]
    for sex in ([args.sex] if args.sex else ['female','male']):
     source=source_root/f'feathered_mohawk_{sex}.glb';g,b=rlglb.read(str(source));w=glbwriter.GLB();w.g=copy.deepcopy(g);w.blob=bytearray(b);head=BoundedHead(sex)
     for lod,mesh in enumerate(w.g['meshes']):
      p=mesh['primitives'][2];cap=g['meshes'][lod]['primitives'][0];P=rlglb.accessor(g,b,p['attributes']['POSITION']);N=rlglb.accessor(g,b,p['attributes']['NORMAL']);C=rlglb.accessor(g,b,p['attributes']['COLOR_0']);T=rlglb.accessor(g,b,p['indices']).reshape(-1,3).astype(int);start=p['extras']['partVertexRanges']['denseBasalRidge'][0];weight=np.zeros(len(P));weight[start:]=.90*(lambda x:x*x*(3-2*x))(np.clip((P[start:,2]-.025)/.020,0,1));mask=weight>1e-8;A=rlglb.accessor(g,b,cap['attributes']['POSITION']);AN=rlglb.accessor(g,b,cap['attributes']['NORMAL']);AC=rlglb.accessor(g,b,cap['attributes']['COLOR_0']);AT=rlglb.accessor(g,b,cap['indices']).reshape(-1,3).astype(int);end=cap['extras']['partVertexRanges']['reference'][1];faces=AT[(AT<end).all(1)&(AC[AT,0]>=.35).all(1)];faces=faces[np.einsum('ij,ij->i',AN[faces].mean(1),A[faces].mean(1)-head.C)>0];surface=trimesh.Trimesh(A,faces,process=False);cp,_,tri=closest(surface,P[mask]);tv=faces[tri];bc=headref.barycentric(cp,A[tv[:,0]],A[tv[:,1]],A[tv[:,2]]);target=headref.unit((AN[tv]*bc[:,:,None]).sum(1));old=N[mask];dot=np.einsum('ij,ij->i',old,target);theta=np.arccos(np.clip(dot,-.99999,.99999));amount=weight[mask];normal=(np.sin((1-amount)*theta)/np.sin(theta))[:,None]*old+(np.sin(amount*theta)/np.sin(theta))[:,None]*target;newN=N.copy();newN[mask]=headref.unit(normal);p['attributes']['NORMAL']=w.accessor(newN,'VEC3',target=34962);_,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
      for ti,t in enumerate(p['targets']):
       D=rlglb.accessor(g,b,t['POSITION']);normal_delta=rlglb.accessor(g,b,t['NORMAL']);normal_delta[mask]=assemble.morph_normals(P,T,newN,D,weld)[mask];t['NORMAL']=w.sparse_vec3(normal_delta,eps=0)
      reports.append({'sex':sex,'lod':lod,'changed_normals':int(mask.sum()),'maximum_turn_degrees':float(np.degrees(np.arccos(np.clip(np.einsum('ij,ij->i',N,newN),-1,1))).max())})
     native_hash=hashlib.sha256()
     for m in w.g['meshes']:
      index=m['extras']['targetNames'].index('hl_native_fit')
      for p in m['primitives']:
       for field in ['POSITION','NORMAL']:native_hash.update(rlglb.accessor(w.g,bytes(w.blob),p['targets'][index][field]).astype('<f4').tobytes())
     w.g['asset']['extras']['rlHair']['nativeFit']['deltaSHA256']=native_hash.hexdigest();w.g['asset']['extras']['rlHair']['source']['rootNormalToolSHA256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
     out=outdir/source.name;w.save(str(out));(outdir/source.with_suffix('.png').name).write_bytes(source.with_suffix('.png').read_bytes());h,bb=rlglb.read(str(out));assert bb[:len(b)]==b
     for lod in range(3):
      assert h['meshes'][lod]['primitives'][:2]==g['meshes'][lod]['primitives'][:2];a=g['meshes'][lod]['primitives'][2];z=h['meshes'][lod]['primitives'][2];assert a['indices']==z['indices']
      for semantic in a['attributes']:
       if semantic!='NORMAL':assert a['attributes'][semantic]==z['attributes'][semantic]
      for a_t,z_t in zip(a['targets'],z['targets']):assert a_t['POSITION']==z_t['POSITION']
    (outdir/'receipt.json').write_text(json.dumps({'all_position_index_uv_coverage_skin_and_target_position_data_exact':True,'cap_exact':True,'reports':reports},indent=2));print('ROUND_ROOT_NORMAL_DIAGNOSTIC_READY',reports,flush=True)


if __name__ == "__main__":
    main()
