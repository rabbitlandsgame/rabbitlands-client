"""Separate imported core and optional detail cards without changing geometry.

Repack a reference_surface export made before its two-material route. Expanded
triangle attributes and all morph POSITION deltas are compared after re-read.
This is also useful as a preservation audit; already split files are copied.
"""
import argparse,copy,hashlib,json,shutil
from pathlib import Path
import numpy as np
import assemble,rlglb

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_primitive(g,b,p):
    attrs={k:rlglb.accessor(g,b,i) for k,i in p['attributes'].items()}
    faces=rlglb.accessor(g,b,p['indices']).astype(int).reshape(-1,3)
    targets=[rlglb.accessor(g,b,t['POSITION']) for t in p.get('targets',[])]
    return attrs,faces,targets

def expanded_hash(attrs,faces,targets):
    h=hashlib.sha256()
    for k in sorted(attrs):
        h.update(k.encode());h.update(attrs[k][faces].astype('f4').tobytes())
    for t in targets:h.update(t[faces].astype('f4').tobytes())
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('out');a=ap.parse_args()
    source=Path(a.source);out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    g,b=rlglb.read(str(source));png=source.with_suffix('.png');shutil.copy2(png,out.with_suffix('.png'))
    proof={'source_sha256':sha(source),'geometry_and_morphs_preserved':True,'lods':{}}
    if any(g['materials'][p['material']]['name']=='rl_hair_card' for m in g['meshes'] for p in m['primitives']):
        shutil.copy2(source,out);proof['method']='Already separated; exact file copy'
    else:
        w=assemble.Writer('RL reference hair: core/detail material separation')
        core=w.material('rl_hair_clump',[1,1,1,1],extras={'texture':out.with_suffix('.png').name})
        card=w.material('rl_hair_card',[1,1,1,1],cutoff=.35,extras={'texture':out.with_suffix('.png').name})
        w.embed_texture(core,str(png))
        w.g.g['materials'][card]['pbrMetallicRoughness']['baseColorTexture']=copy.deepcopy(w.g.g['materials'][core]['pbrMetallicRoughness']['baseColorTexture'])
        expected=[]
        for m in g['meshes']:
            assert len(m['primitives'])==1,'Explicit handling required for an existing mixed-material source'
            attrs,T,targets=read_primitive(g,b,m['primitives'][0]);is_card=(attrs['COLOR_0'][T,3]<.999).all(1)
            prims=[];checks=[]
            for mask,material in [(~is_card,core),(is_card,card)]:
                if not mask.any():continue
                used,inverse=np.unique(T[mask],return_inverse=True);faces=inverse.reshape(-1,3)
                p=w.primitive(attrs['POSITION'][used].astype('f4'),attrs['NORMAL'][used].astype('f4'),attrs['TEXCOORD_0'][used].astype('f4'),faces,np.rint(attrs['COLOR_0'][used]*255).astype('u1'),attrs['JOINTS_0'][used].astype('u1'),attrs['WEIGHTS_0'][used].astype('f4'),material,[])
                # Preserve the already exported deltas exactly; do not apply a
                # second authoring threshold to their float32 representation.
                p['targets']=[{'POSITION':w.g.sparse_vec3(d[used].astype('f4'),eps=1e-9,minmax=True)} for d in targets]
                prims.append(p);checks.append(expanded_hash(attrs,T[mask],targets))
            w.mesh(m['name'],prims,m['extras']['targetNames']);expected.append(checks)
        root_index=g['skins'][0]['joints'][0];root=copy.deepcopy(g['nodes'][root_index]);root.pop('children',None)
        new_root=w.g.node(**root);w.g.g['scenes'][0]['nodes'].append(new_root)
        matrix=rlglb.accessor(g,b,g['skins'][0]['inverseBindMatrices'])
        ibm=w.g.accessor(matrix.astype('f4'),'MAT4');w.g.g['skins']=[{'joints':[new_root],'inverseBindMatrices':ibm,'skeleton':new_root,'name':'RLHairSkin'}]
        for i,m in enumerate(g['meshes']):w.g.g['scenes'][0]['nodes'].append(w.g.node(name=m['name'],mesh=i,skin=0))
        w.g.g['asset']['extras']=copy.deepcopy(g['asset']['extras']);w.save(str(out))
        actual,blob=rlglb.read(str(out))
        for i,m in enumerate(actual['meshes']):
            hashes=[expanded_hash(*read_primitive(actual,blob,p)) for p in m['primitives']]
            assert hashes==expected[i],m['name']+' changed geometry/morphs'
            proof['lods'][m['name']]=hashes
        proof['method']='Exact expanded-triangle attributes and all 50 morph deltas match after split and re-read'
    proof['output_sha256']=sha(out);proof['atlas_sha256']=sha(out.with_suffix('.png'));proof['repacker_sha256']=sha(__file__)
    out.with_suffix('.preservation.json').write_text(json.dumps(proof,indent=2))
    report=json.loads(source.with_suffix('.report.json').read_text());report['material_split']=proof
    out.with_suffix('.report.json').write_text(json.dumps(report,indent=2))
    print(out.name,proof['method'],flush=True)
if __name__=='__main__':main()
