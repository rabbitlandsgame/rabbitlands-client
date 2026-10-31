"""Split only recipient attribute seams while preserving every triangle point."""
import hashlib
import numpy as np

def split_corner_uv(P,T,corner_uv,attributes):
    P=np.asarray(P);T=np.asarray(T,int);corner_uv=np.asarray(corner_uv)
    assert corner_uv.shape==(*T.shape,2) and np.isfinite(corner_uv).all()
    corners=T.reshape(-1);uv=corner_uv.reshape(-1,2)
    keys=np.column_stack([corners,np.rint(uv*1e8).astype(np.int64)])
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    source=corners[first];new_P=P[source].copy();new_T=inverse.reshape(T.shape)
    copied={key:np.asarray(value)[source].copy() for key,value in attributes.items()}
    assert np.array_equal(P[T],new_P[new_T])
    for key,value in attributes.items():assert np.array_equal(np.asarray(value)[T],copied[key][new_T])
    digest=lambda array:hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
    before=digest(P[T]);after=digest(new_P[new_T]);assert before==after
    return new_P,new_T,uv[first].copy(),copied,{'triangle_positions_before_sha256':before,'triangle_positions_after_sha256':after,
        'source_vertices':len(P),'chart_vertices':len(new_P),'triangles':len(T),'geometry_and_attributes_per_corner_exact':True}
