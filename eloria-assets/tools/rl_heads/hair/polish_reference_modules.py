"""Remove detached tiny Afro islands or feather reference beard roots.

python polish_reference_modules.py source.glb output.glb
Positions, weights and every morph accessor remain byte-identical.
Indices (close Afro), root-mask R (beards/twin buns), unit-normal corrections
and material metadata can change. All other geometry and morph data is audited.
Keep source and output in separate ignored authoring stages.
"""
import argparse,copy,hashlib,json,struct
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
import rlglb,headref,hairgen

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('out');ap.add_argument('--normals-only',action='store_true');a=ap.parse_args()
    source=Path(a.source);out=Path(a.out);assert source.resolve()!=out.resolve()
    g,b=rlglb.read(str(source));original=copy.deepcopy(g);blob=bytearray(b)
    extras=g['asset']['extras'];beard='rlBeard' in extras;info=extras['rlBeard' if beard else 'rlHair'];style=info['style']
    assert beard or style in ('rounded_afro','curly_twin_buns','shoulder_waves')
    head=headref.Head(info['sex'])
    proof={'source_sha256':digest(source),'position_skin_and_morph_accessors_preserved':True,'lods':{}}
    for mesh in g['meshes']:
        total=0;removed=0
        for primitive in mesh['primitives']:
            attrs=primitive['attributes'];P=rlglb.accessor(g,b,attrs['POSITION']);T=rlglb.accessor(g,b,primitive['indices']).astype(int).reshape(-1,3)
            material=g['materials'][primitive['material']]
            normals=rlglb.accessor(g,b,attrs['NORMAL']).copy();length=np.linalg.norm(normals,axis=1);bad=length<.5
            normals[bad]=headref.unit(P[bad]-head.C);normals=headref.unit(normals).astype('f4')
            if beard:
                _,weld=np.unique(np.round(P/.00015),axis=0,return_inverse=True)
                smooth=headref.vertex_normals(P,T,weld)
                use=np.linalg.norm(smooth,axis=1)>.5
                normals[use]=smooth[use]
            accessor=g['accessors'][attrs['NORMAL']];view=g['bufferViews'][accessor['bufferView']];assert not view.get('byteStride')
            start=view.get('byteOffset',0)+accessor.get('byteOffset',0);blob[start:start+normals.nbytes]=normals.tobytes()
            if style=='curly_twin_buns' and material['name']=='rl_hair_clump':
                scalp=hairgen.Scalp(head)
                lon,lat=headref.dir_lonlat(P-head.C)
                eligible=(np.abs(lon)<80)&(lat<scalp.hairline(lon)+8)
                _,weld=np.unique(np.round(P/1e-5),axis=0,return_inverse=True)
                edges=np.sort(weld[T][:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
                edge,count=np.unique(edges,axis=0,return_counts=True)
                boundary=np.unique(edge[count==1]);ids=np.flatnonzero(np.isin(weld,boundary)&eligible)
                colours=np.rint(rlglb.accessor(g,b,attrs['COLOR_0'])*255).astype('u1');colours[:,0]=255
                if len(ids):
                    distance=cKDTree(P[ids]).query(P)[0]
                    colours[eligible,0]=np.clip(distance[eligible]/.002*255,0,255).astype('u1')
                accessor=g['accessors'][attrs['COLOR_0']];view=g['bufferViews'][accessor['bufferView']]
                start=view.get('byteOffset',0)+accessor.get('byteOffset',0);blob[start:start+colours.nbytes]=colours.tobytes()
            elif beard and not a.normals_only:
                edges=np.sort(T[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
                _,weld=np.unique(np.round(P/1e-5),axis=0,return_inverse=True)
                edges=weld[edges];unique,count=np.unique(edges,axis=0,return_counts=True)
                boundary=np.unique(unique[count==1]);ids=np.flatnonzero(np.isin(weld,boundary))
                colours=np.rint(rlglb.accessor(g,b,attrs['COLOR_0'])*255).astype('u1');colours[:,0]=255
                if len(ids):
                    distance=cKDTree(P[ids]).query(P)[0];_,skin_distance,_,_=head.closest(P)
                    root=skin_distance<.012
                    colours[root,0]=np.clip(distance[root]/.004*255,0,255).astype('u1')
                accessor=g['accessors'][attrs['COLOR_0']];assert accessor['componentType']==5121
                view=g['bufferViews'][accessor['bufferView']];assert not view.get('byteStride')
                start=view.get('byteOffset',0)+accessor.get('byteOffset',0);blob[start:start+colours.nbytes]=colours.tobytes()
                material.setdefault('extras',{})['softHairline']=True
            elif style=='rounded_afro' and mesh['name'].endswith('lod0') and material['name']=='rl_hair_clump':
                _,weld=np.unique(np.round(P/1e-5),axis=0,return_inverse=True)
                edges=weld[T][:,[0,1,1,2,2,0]].reshape(-1,2)
                graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(weld.max()+1,weld.max()+1)).tocsr()
                _,labels=connected_components(graph,directed=False);groups=labels[weld[T[:,0]]]
                ids,counts=np.unique(groups,return_counts=True);main=ids[np.argmax(counts)]
                tree=cKDTree(P[np.unique(T[groups==main])]);keep=np.ones(len(T),bool)
                for group,count in zip(ids,counts):
                    if group==main or count>=300:continue
                    gap=tree.query(P[np.unique(T[groups==group])])[0].min()
                    if gap>.001:keep[groups==group]=False
                removed+=int((~keep).sum());T=T[keep]
                accessor=g['accessors'][primitive['indices']];dtype={5123:'<u2',5125:'<u4'}[accessor['componentType']]
                view=g['bufferViews'][accessor['bufferView']];start=view.get('byteOffset',0)+accessor.get('byteOffset',0)
                values=T.astype(dtype).reshape(-1);blob[start:start+values.nbytes]=values.tobytes();accessor['count']=len(values)
                accessor.pop('min',None);accessor.pop('max',None)
            total+=len(T)
        info['tris'][mesh['name'].replace('hair_','').replace('beard_','')]=total
        proof['lods'][mesh['name']]={'tris':total,'removed_detached_triangles':removed}
    # Prove the untouched accessor bytes against the source, including sparse
    # morph payloads. Only the explicitly edited colour/index buffers differ.
    for old_mesh,new_mesh in zip(original['meshes'],g['meshes']):
        for old,new in zip(old_mesh['primitives'],new_mesh['primitives']):
            for key,index in old['attributes'].items():
                if key=='NORMAL' or (key=='COLOR_0' and (beard or style=='curly_twin_buns')):continue
                assert np.array_equal(rlglb.accessor(original,b,index),rlglb.accessor(g,blob,new['attributes'][key]))
            for target in old.get('targets',[]):
                for index in target.values():assert np.array_equal(rlglb.accessor(original,b,index),rlglb.accessor(g,blob,index))
    encoded=json.dumps(g,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4);blob+=b'\0'*((-len(blob))%4)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob)
    proof['output_sha256']=digest(out);out.with_suffix('.polish.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof),flush=True)

if __name__=='__main__':main()
