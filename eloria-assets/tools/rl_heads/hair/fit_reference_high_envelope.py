"""Seat only a reference exterior against the full High identity/groom envelope.

The named fixed cap and every original target, UV, colour and weight stay exact.
This is bounded authoring support, not independent qualification. Outputs and
reports belong in an ignored authoring stage. Native fitting remains separate.
"""
from pathlib import Path
import argparse,copy,hashlib,json,shutil
import numpy as np
import assemble,glbwriter,rlglb
from build_loose_reference import BoundedHead
from high_contact_bounds import ContactHead
from short_surface_guard import guard


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fit(source,out,range_name='exterior'):
    source,out=map(Path,(source,out));assert source.resolve()!=out.resolve() and source.name==out.name and not out.exists()
    g,b=rlglb.read(str(source));info=g['asset']['extras']['rlHair'];head=BoundedHead(info['sex'])
    assert sha(head.glb_path)==info['headSHA256'],'Use the exact declared current High head'
    contact=ContactHead(head,3.2,geometric_sign=True,horizontal_slice_proof=True,closed_section_proof=True)
    writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b);rows=[]
    for old,mesh in zip(g['meshes'],writer.g['meshes']):
        names=old['extras']['targetNames'];assert 'hl_native_fit' not in names,'Seat High before adding the Native-only corrective'
        ids=[n for n in names if n.startswith('id_')];grooms=[n for n in names if n.startswith('hl_')]
        assert len(ids)==46 and set(grooms)=={'hl_length_p','hl_length_n','hl_volume_p','hl_volume_n'}
        combos=assemble.default_combos(ids)
        for n in grooms:
            for side in ('_p','_n'):combos[n+'+all_id'+side]={i:1 for i in ids if i.endswith(side)}|{n:1}
        for length in ('hl_length_p','hl_length_n'):
            for volume in ('hl_volume_p','hl_volume_n'):combos[length+'+'+volume]={length:1,volume:1}
        for pi,(p,dst) in enumerate(zip(old['primitives'],mesh['primitives'])):
            ranges=p.get('extras',{}).get('partVertexRanges',{})
            if range_name not in ranges:continue
            a,z=ranges[range_name];P=rlglb.accessor(g,b,p['attributes']['POSITION']);N=rlglb.accessor(g,b,p['attributes']['NORMAL']);T=rlglb.accessor(g,b,p['indices']).astype(int).reshape(-1,3)
            selected=(T>=a).all(1)&(T<z).all(1)
            assert not (((T>=a)&(T<z)).any(1)&~selected).any(),'Exterior boundary must be independent of the fixed cap'
            fields={n:rlglb.accessor(g,b,t['POSITION'])[a:z] for n,t in zip(names,p['targets'])}
            Q,proof=guard(contact,P[a:z],T[selected]-a,fields,ids,combos,margin=.0032,max_shift_mm=14,max_iterations=12,all_faces=True,geometric_projection=True)
            full=P.copy();full[a:z]=Q;D=full-P;_,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
            normal=N+assemble.morph_normals(P,T,N,D,weld);normal/=np.linalg.norm(normal,axis=1,keepdims=True)
            # Fixed-cap normals, like its positions and targets, remain exact.
            normal[:a]=N[:a];normal[z:]=N[z:]
            dst['attributes']['POSITION']=writer.accessor(full,'VEC3',target=34962,minmax=True)
            dst['attributes']['NORMAL']=writer.accessor(normal,'VEC3',target=34962)
            rows.append(dict(mesh=mesh['name'],primitive=pi,range=[a,z],proof=proof))
    assert rows
    writer.g['asset']['extras']['rlHair']['referenceHighEnvelope']={'sourceSHA256':sha(source),'toolSHA256':sha(__file__),'range':range_name,'capAndTargetsPreserved':True,'qualified':False}
    out.parent.mkdir(parents=True,exist_ok=True);writer.save(str(out))
    for suffix in ('.png','.cap-native.npz'):
        src=source.with_suffix(suffix)
        if src.exists():assert not out.with_suffix(suffix).exists();shutil.copy2(src,out.with_suffix(suffix))
    gg,bb=rlglb.read(str(out))
    for old,mesh in zip(g['meshes'],gg['meshes']):
        assert old['extras']==mesh['extras']
        for before,after in zip(old['primitives'],mesh['primitives']):
            assert before['targets']==after['targets'] and before['indices']==after['indices']
            for key,acc in before['attributes'].items():
                if key not in ('POSITION','NORMAL'):assert after['attributes'][key]==acc
            ranges=before.get('extras',{}).get('partVertexRanges',{})
            if range_name in ranges:
                a,z=ranges[range_name]
                for semantic in ('POSITION','NORMAL'):
                    v=rlglb.accessor(g,b,before['attributes'][semantic]);q=rlglb.accessor(gg,bb,after['attributes'][semantic]);assert np.array_equal(v[:a],q[:a]) and np.array_equal(v[z:],q[z:])
    receipt=dict(source_sha256=sha(source),output_sha256=sha(out),tool_sha256=sha(__file__),head_sha256=sha(head.glb_path),targets_indices_uv_colours_weights_fixed_cap_exact=True,rows=rows,qualified=False)
    out.with_suffix('.high-envelope.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--out',required=True);ap.add_argument('--range',default='exterior');args=ap.parse_args();print(json.dumps(fit(args.source,args.out,args.range)))
