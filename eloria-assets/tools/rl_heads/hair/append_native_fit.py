"""Append a native-only hair corrective while preserving every existing accessor.

The caller supplies bind-space deltas keyed by (mesh name, primitive index).
No fitting, provider call, network access or runtime registration happens here.
"""
import argparse,copy,hashlib,json,shutil
from pathlib import Path
import numpy as np
import assemble,glbwriter,rlglb

SHAPE='hl_native_fit'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def append_native_fit(source,output,deltas,provenance=None):
    """deltas[(mesh_name, primitive_index)] = {'POSITION': Nx3, 'NORMAL': Nx3?}.

    Omitted primitives receive an explicit zero corrective. Missing NORMAL is
    transported from the geometric change. Provided provenance is private;
    public extras contain only semantic shape names and safe SHA-256 hashes.
    """
    source=Path(source);output=Path(output)
    assert source.name==output.name and source.resolve()!=output.resolve()
    assert not output.exists() and not output.with_suffix('.native-fit.json').exists()
    g,b=rlglb.read(str(source));assert len(g['buffers'])==1 and 'uri' not in g['buffers'][0]
    assert 'rlHair' in g['asset'].get('extras',{})
    names=[mesh.get('name') for mesh in g['meshes']]
    assert all(isinstance(name,str) and name for name in names) and len(set(names))==len(names)
    valid={(mesh['name'],index) for mesh in g['meshes'] for index in range(len(mesh['primitives']))}
    assert not set(deltas)-valid,'Unknown corrective primitive'
    private_provenance=json.loads(json.dumps(provenance or {},default=str))
    writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b)
    digest=hashlib.sha256();records=[];implicit=[]
    for mesh_index,(old,mesh) in enumerate(zip(g['meshes'],writer.g['meshes'])):
        old_names=old.get('extras',{}).get('targetNames',[])
        assert SHAPE not in old_names,'Do not replace an existing native corrective'
        mesh.setdefault('extras',{})['targetNames']=list(old_names)+[SHAPE]
        if 'weights' in old:
            assert len(old['weights'])==len(old_names)
            mesh['weights']=list(old['weights'])+[0.]
        for node in writer.g.get('nodes',[]):
            if node.get('mesh')==mesh_index and 'weights' in node:
                assert len(node['weights'])==len(old_names)
                node['weights']=list(node['weights'])+[0.]
        for index,(before,primitive) in enumerate(zip(old['primitives'],mesh['primitives'])):
            assert len(before.get('targets',[]))==len(old_names)
            P=rlglb.accessor(g,b,before['attributes']['POSITION']);N=rlglb.accessor(g,b,before['attributes']['NORMAL'])
            T=rlglb.accessor(g,b,before['indices'],normalize=False).astype(int).reshape(-1,3)
            key=(old['name'],index);entry=deltas.get(key)
            if entry is None:entry={'POSITION':np.zeros_like(P)};implicit.append([key[0],key[1]])
            assert set(entry)<=set(['POSITION','NORMAL']) and 'POSITION' in entry
            D=np.asarray(entry['POSITION'],dtype='f4');assert D.shape==P.shape and np.isfinite(D).all()
            if 'NORMAL' in entry:DN=np.asarray(entry['NORMAL'],dtype='f4')
            else:
                _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
                DN=assemble.morph_normals(P,T,N,D,weld).astype('f4')
            assert DN.shape==N.shape and np.isfinite(DN).all()
            assert (np.linalg.norm(N+DN,axis=1)>1e-6).all(),'Corrective destroys a shading normal'
            digest.update(json.dumps([key[0],key[1]],separators=(',',':')).encode())
            for name,array in [('POSITION',D),('NORMAL',DN)]:digest.update(name.encode());digest.update(np.asarray(array.shape,dtype='<i8').tobytes());digest.update(np.ascontiguousarray(array,dtype='<f4').tobytes())
            target={'POSITION':writer.sparse_vec3(D,eps=0)}
            if np.any(DN):target['NORMAL']=writer.sparse_vec3(DN,eps=0)
            primitive['targets']=copy.deepcopy(before.get('targets',[]))+[target]
            records.append({'mesh':old['name'],'primitive':index,'vertices':len(P),'old_targets':len(old_names),'changed_vertices':int((np.linalg.norm(D,axis=1)>0).sum()),'maximum_shift_mm':float(np.linalg.norm(D,axis=1).max()*1000),'normal_changed_vertices':int((np.linalg.norm(DN,axis=1)>0).sum()),'old_mesh_weights_preserved':True,'native_default_weight':0})
    delta_sha=digest.hexdigest();source_sha=sha(source);tool_sha=sha(__file__)
    writer.g['asset']['extras']['rlHair']['nativeFit']={'shape':SHAPE,'sourceSHA256':source_sha,'deltaSHA256':delta_sha,'toolSHA256':tool_sha}
    assert writer.g['accessors'][:len(g['accessors'])]==g['accessors']
    assert writer.g['bufferViews'][:len(g['bufferViews'])]==g['bufferViews']
    assert bytes(writer.blob[:len(b)])==b
    atlas=source.with_suffix('.png');out_atlas=output.with_suffix('.png')
    if atlas.is_file():assert not out_atlas.exists()
    output.parent.mkdir(parents=True,exist_ok=True);writer.save(str(output))
    if atlas.is_file():shutil.copy2(atlas,out_atlas)
    check,blob=rlglb.read(str(output))
    assert check['accessors'][:len(g['accessors'])]==g['accessors'] and blob[:len(b)]==b
    for before,after in zip(g['meshes'],check['meshes']):
        assert after['extras']['targetNames'][:-1]==before.get('extras',{}).get('targetNames',[])
        for a,c in zip(before['primitives'],after['primitives']):
            assert a['attributes']==c['attributes'] and a['indices']==c['indices']
            assert a.get('targets',[])==c['targets'][:-1]
    report={'shape':SHAPE,'source_sha256':source_sha,'output_sha256':sha(output),'delta_content_sha256':delta_sha,'tool_sha256':tool_sha,'old_accessors_and_buffer_views_exact':True,'old_blob_prefix_exact':True,'old_geometry_skin_colour_uv_indices_targets_exact':True,'records':records,'implicit_zero_primitives':implicit,'provenance':private_provenance,'qualified':False}
    if atlas.is_file():report['atlas_sha256']=sha(out_atlas);assert sha(atlas)==report['atlas_sha256']
    output.with_suffix('.native-fit.json').write_text(json.dumps(report,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--deltas',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();g,_=rlglb.read(args.source);data=np.load(args.deltas);deltas={}
    for m,mesh in enumerate(g['meshes']):
        for p,_ in enumerate(mesh['primitives']):
            prefix=f'm{m}_p{p}_';entry={name: data[prefix+name] for name in ['POSITION','NORMAL'] if prefix+name in data}
            if entry:deltas[(mesh['name'],p)]=entry
    report=append_native_fit(args.source,args.out,deltas,{'input_delta_file_sha256':sha(args.deltas)})
    print('NATIVE_FIT_APPENDED',report['output_sha256'],flush=True)

if __name__=='__main__':main()
