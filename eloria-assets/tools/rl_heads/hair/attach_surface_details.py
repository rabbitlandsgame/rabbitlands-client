"""Attach ribbon roots to final exterior surfaces and their linear shape fields.

Only the separate detail primitives change. This is authoring, not qualification.
"""
import argparse,copy,hashlib,json,shutil
from pathlib import Path
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import assemble,glbwriter,headref,rlglb


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_columns(parent_points,parent_triangles,parent_deltas,points,deltas,roots,columns,
                 rigid_shapes=('hl_native_fit',)):
    """Return anchored positions/fields and fixed parent triangle parameters.

    Each root and all descendants in its column receive its parent translation.
    Relative strand motion is retained, except explicitly rigid corrective fields.
    """
    P=np.asarray(parent_points);T=np.asarray(parent_triangles,int)
    F=np.asarray(points);roots=np.asarray(roots,int);columns=np.asarray(columns,int)
    assert len(roots)>0 and columns.shape==(len(F),)
    assert set(deltas)==set(parent_deltas)
    assert ((columns>=0)&(columns<len(roots))).all()
    surface=trimesh.Trimesh(P,T,process=False)
    cp,distance,triangle=trimesh.proximity.closest_point(surface,F[roots])
    tv=T[triangle]
    bary=headref.barycentric(cp,P[tv[:,0]],P[tv[:,1]],P[tv[:,2]])
    bary=np.maximum(bary,0);bary/=bary.sum(1)[:,None]
    cp=(P[tv]*bary[:,:,None]).sum(1)
    result=F.copy();motion={n:np.asarray(d).copy() for n,d in deltas.items()}
    for column,root in enumerate(roots):
        group=columns==column;result[group]+=cp[column]-F[root]
        for name,delta in deltas.items():
            parent=(np.asarray(parent_deltas[name])[tv[column]]*bary[column,:,None]).sum(0)
            relative=0 if name in rigid_shapes else np.asarray(delta)[group]-np.asarray(delta)[root]
            motion[name][group]=parent+relative
    return result,motion,{'parent_triangles':tv.tolist(),'barycentric':bary.tolist(),
                         'original_root_distance_mm':(distance*1000).tolist()}


def attach(source,out):
    source,out=Path(source),Path(out)
    assert source.name==out.name and source.resolve()!=out.resolve() and not out.exists()
    g,b=rlglb.read(str(source));writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b)
    reports=[]
    for old,mesh in zip(g['meshes'],writer.g['meshes']):
        names=old['extras']['targetNames'];parent=old['primitives'][0]
        P=rlglb.accessor(g,b,parent['attributes']['POSITION'])
        C=rlglb.accessor(g,b,parent['attributes']['COLOR_0'])
        T=rlglb.accessor(g,b,parent['indices'],normalize=False).astype(int).reshape(-1,3)
        a,z=parent['extras']['partVertexRanges']['exterior']
        eligible=(T>=a).all(1)&(T<z).all(1)&(C[T,0]>=.55).all(1)
        eligible&=np.linalg.norm(np.cross(P[T[:,1]]-P[T[:,0]],P[T[:,2]]-P[T[:,0]]),axis=1)>1e-14
        faces=T[eligible];assert len(faces)
        parent_d={n:rlglb.accessor(g,b,t['POSITION']) for n,t in zip(names,parent['targets'])}
        PJ=rlglb.accessor(g,b,parent['attributes']['JOINTS_0'],normalize=False)
        PW=rlglb.accessor(g,b,parent['attributes']['WEIGHTS_0'])
        for pi,(src,dst) in enumerate(zip(old['primitives'][1:],mesh['primitives'][1:]),1):
            F=rlglb.accessor(g,b,src['attributes']['POSITION']);N=rlglb.accessor(g,b,src['attributes']['NORMAL'])
            FC=rlglb.accessor(g,b,src['attributes']['COLOR_0']);UV=rlglb.accessor(g,b,src['attributes']['TEXCOORD_0'])
            J=rlglb.accessor(g,b,src['attributes']['JOINTS_0'],normalize=False)
            W=rlglb.accessor(g,b,src['attributes']['WEIGHTS_0'])
            FT=rlglb.accessor(g,b,src['indices'],normalize=False).astype(int).reshape(-1,3)
            fd={n:rlglb.accessor(g,b,t['POSITION']) for n,t in zip(names,src['targets'])}
            edges=FT[:,[0,1,1,2,2,0]].reshape(-1,2)
            _,labels=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),
                                                    shape=(len(F),len(F))).tocsr(),directed=False)
            Q=F.copy();motion={n:d.copy() for n,d in fd.items()};bindings=[]
            for label in np.unique(labels):
                group=np.flatnonzero(labels==label);along=FC[group,1]
                roots=group[along<=along.min()+.01];assert len(roots)==2,'Expected a two-column ribbon root'
                root_u=UV[roots,0];assert abs(root_u[1]-root_u[0])>1e-8
                column=np.argmin(abs(UV[group,0,None]-root_u[None]),axis=1)
                local_roots=np.array([int(np.flatnonzero(group==root)[0]) for root in roots])
                new,new_delta,proof=root_columns(P,faces,parent_d,F[group],{n:d[group] for n,d in fd.items()},
                                                local_roots,column)
                tv=np.asarray(proof['parent_triangles'],int)
                for at,root in enumerate(roots):
                    assert np.array_equal(PJ[tv[at]],np.repeat(J[root][None],3,axis=0))
                    assert np.array_equal(PW[tv[at]],np.repeat(W[root][None],3,axis=0)), 'Root and parent skinning differ'
                assert np.array_equal(J[group],np.repeat(J[group[:1]],len(group),axis=0))
                assert np.array_equal(W[group],np.repeat(W[group[:1]],len(group),axis=0))
                Q[group]=new
                for n in names:motion[n][group]=new_delta[n]
                bindings.append({'root_indices':roots.tolist(),**proof})
            _,weld=np.unique(np.round(F/1e-6),axis=0,return_inverse=True)
            NN=headref.unit(N+assemble.morph_normals(F,FT,N,Q-F,weld))
            dst['attributes']['POSITION']=writer.accessor(Q,'VEC3',target=34962,minmax=True)
            dst['attributes']['NORMAL']=writer.accessor(NN,'VEC3',target=34962)
            _,new_weld=np.unique(np.round(Q/1e-6),axis=0,return_inverse=True)
            dst['targets']=[]
            for n in names:
                target={'POSITION':writer.sparse_vec3(motion[n],eps=0)}
                normal=assemble.morph_normals(Q,FT,NN,motion[n],new_weld)
                if np.any(normal):target['NORMAL']=writer.sparse_vec3(normal,eps=0)
                dst['targets'].append(target)
            reports.append({'mesh':old['name'],'primitive':pi,'strips':len(bindings),'bindings':bindings,
                            'maximum_baseline_shift_mm':float(np.linalg.norm(Q-F,axis=1).max()*1000),
                            'maximum_native_shift_mm':float(np.linalg.norm(motion['hl_native_fit'],axis=1).max()*1000)
                            if 'hl_native_fit' in motion else None})
    assert reports
    writer.g['asset']['extras']['rlHair']['surfaceDetails']={'sourceSHA256':sha(source),'toolSHA256':sha(__file__),
        'method':'each ribbon root follows fixed exterior-triangle barycentrics for all linear controls'}
    out.parent.mkdir(parents=True,exist_ok=True);writer.save(str(out));shutil.copy2(source.with_suffix('.png'),out.with_suffix('.png'))
    gg,bb=rlglb.read(str(out));assert bb[:len(b)]==b
    for before,after in zip(g['meshes'],gg['meshes']):
        assert before['primitives'][0]==after['primitives'][0]
        assert before['extras']==after['extras'] and before.get('weights')==after.get('weights')
        for p,q in zip(before['primitives'][1:],after['primitives'][1:]):
            assert p['indices']==q['indices']
            for key in ['TEXCOORD_0','COLOR_0','JOINTS_0','WEIGHTS_0']:assert p['attributes'][key]==q['attributes'][key]
    receipt={'source_sha256':sha(source),'output_sha256':sha(out),'reports':reports,
             'core_and_cap_primitives_exact':True,'detail_uv_colour_skin_indices_exact':True,'qualified':False}
    out.with_suffix('.surface-details.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();report=attach(args.source,args.out)
    print('SURFACE_DETAILS_ATTACHED',report['output_sha256'])
