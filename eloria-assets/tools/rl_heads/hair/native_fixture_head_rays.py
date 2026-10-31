"""Evaluated head-only geometry for coherent authoring rays, never for signs."""
from pathlib import Path
import hashlib,json
from types import SimpleNamespace
import numpy as np
import trimesh
import rlglb,paths

def fixture_head_part(data,expected_triangles,face_rows,expected_vertices):
    """Prove triangle-row identity despite Godot's winding conversion."""
    P=np.asarray(data['P']);N=np.asarray(data['N']);I=np.asarray(data['I'],int)
    expected=np.asarray(expected_triangles,int);selected=np.asarray(face_rows,int)
    assert len(P)==expected_vertices and P.shape==N.shape and np.isfinite(P).all() and np.isfinite(N).all()
    assert I.shape==expected.shape and np.array_equal(np.sort(I,axis=1),np.sort(expected,axis=1)),'Evaluated triangle rows no longer match the source semantic head mask'
    assert selected.ndim==1 and ((selected>=0)&(selected<len(I))).all()
    T=expected[selected];used,inverse=np.unique(T,return_inverse=True)
    return P[used],N[used],inverse.reshape(-1,3)

def from_current_head_cases(head,manifest,case_names=None):
    """Return P/N/T/mesh/source for rays; signed distance is deliberately absent.

    Use these triangles only as the ray mesh in a NativeHeadSurface adapter
    whose signed() delegates to the independent complete NativeFixtureUnion.
    """
    manifest=Path(manifest);document=json.loads(manifest.read_text())
    assert document.get('hair_identity_policy')=='native_fixed_skull'
    body=Path(paths.body_glb(head.sex));body_sha=hashlib.sha256(body.read_bytes()).hexdigest()
    cut=head.gltf['asset']['extras']['rlHead']['bodyCut'];assert cut['bodySHA256']==body_sha
    g,b=rlglb.read(str(body));expected={}
    for kind in ['body','scalp']:
        mesh=next(m for m in g['meshes'] if m.get('name')==kind);assert len(mesh['primitives'])==1
        primitive=mesh['primitives'][0];T=rlglb.accessor(g,b,primitive['indices'],normalize=False).astype(int).reshape(-1,3)
        used,inverse=np.unique(T,return_inverse=True)
        rows=np.concatenate([np.arange(start,start+count) for start,count in cut['hiddenBodyTriangles']]) if kind=='body' else np.arange(len(T))
        expected[kind]=(inverse.reshape(-1,3),rows,len(used))
    Ps=[];Ns=[];Ts=[];offset=0;seen=set();records=[]
    for record in document['cases']:
        if record['sex']!=head.sex or record['clip']!='Rest_Pose' or record['fraction']!=0:continue
        if case_names is not None and record['case'] not in case_names:continue
        assert not record['rl_hair_identity_controls']
        for part in record['parts']:
            kind=part['mesh']
            if kind not in expected:continue
            assert part['surface']==0
            path=manifest.parent/part['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==part['sha256']
            with np.load(path) as data:P,N,T=fixture_head_part(data,*expected[kind])
            digest=hashlib.sha256(P.tobytes()+N.tobytes()+T.tobytes()).hexdigest()
            if digest in seen:continue
            seen.add(digest);Ps.append(P);Ns.append(N);Ts.append(T+offset);offset+=len(P)
            records.append({'case':record['case'],'quality':record['quality'],'mesh':kind,'geometry_sha256':digest})
    assert Ps and any(record['mesh']=='body' for record in records) and any(record['mesh']=='scalp' for record in records)
    P,N,T=np.vstack(Ps),np.vstack(Ns),np.vstack(Ts)
    return SimpleNamespace(P=P,N=N,T=T,mesh=trimesh.Trimesh(P,T,process=False),source={
        'native_body_sha256':body_sha,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'head_only_ray_triangles':len(T),'unique_head_ray_parts':records,
        'ray_scope':'Exact source bodyCut triangle rows plus native scalp; no garments or lower-body patches',
        'signed_distance_api':False})
