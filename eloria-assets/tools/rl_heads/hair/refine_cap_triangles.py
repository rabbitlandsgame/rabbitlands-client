"""Conforming cap-only refinement with interpolated High-head attributes.

No fitting or runtime behavior is selected here. The caller supplies the cap
faces needing support and retains separate High/Native position fields.
"""
import numpy as np
import headref

def refine_cap(attributes,triangles,selected_faces,max_extra_triangles,normal_keys=('N',),skin_keys=('J','W')):
    arrays={key:np.asarray(value) for key,value in attributes.items()};P=arrays['P'];T=np.asarray(triangles,int)
    assert len(P) and T.ndim==2 and T.shape[1]==3 and all(len(value)==len(P) for value in arrays.values())
    selected=np.unique(np.asarray(selected_faces,int));assert ((selected>=0)&(selected<len(T))).all()
    _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
    geometric_edges=set()
    for face in T[selected]:
        for a,b in zip(face,np.roll(face,-1)):geometric_edges.add(tuple(sorted((int(weld[a]),int(weld[b])))))
    additions={key:[] for key in arrays};new_edges={};out=[];parents=[]
    def midpoint(a,b):
        key=tuple(sorted((int(a),int(b))))
        if key in new_edges:return new_edges[key]
        index=len(P)+len(new_edges);new_edges[key]=index
        for name,values in arrays.items():
            if name in skin_keys:
                assert np.array_equal(values[a],values[b]),'Cap refinement requires identical skin influences along each split edge'
                value=values[a].copy()
            else:
                value=(values[a].astype(float)+values[b].astype(float))*.5
                if name in normal_keys:value=headref.unit(value)
                if np.issubdtype(values.dtype,np.integer):value=np.rint(value)
                value=value.astype(values.dtype)
            additions[name].append(value)
        return index
    for face_index,(a,b,c) in enumerate(T):
        original=(int(a),int(b),int(c));pairs=[(a,b),(b,c),(c,a)];mids=[]
        for left,right in pairs:
            marked=tuple(sorted((int(weld[left]),int(weld[right])))) in geometric_edges
            mids.append(midpoint(left,right) if marked else None)
        ab,bc,ca=mids;count=sum(value is not None for value in mids)
        if count==0:faces=[original]
        elif count==3:faces=[(a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)]
        elif count==1:
            if ab is not None:faces=[(a,ab,c),(ab,b,c)]
            elif bc is not None:faces=[(a,b,bc),(a,bc,c)]
            else:faces=[(a,b,ca),(b,c,ca)]
        elif ab is None:faces=[(ca,bc,c),(a,b,ca),(b,bc,ca)]
        elif bc is None:faces=[(a,ab,ca),(ab,b,c),(ab,c,ca)]
        else:faces=[(ab,b,bc),(a,ab,c),(ab,bc,c)]
        out.extend(faces);parents.extend([face_index]*len(faces))
    new_T=np.asarray(out,int);extra=len(new_T)-len(T)
    assert extra<=max_extra_triangles,'Cap refinement exceeded its triangle budget'
    result={name:np.concatenate([values,np.asarray(additions[name],dtype=values.dtype).reshape((-1,)+values.shape[1:])]) for name,values in arrays.items()}
    for name,values in arrays.items():assert np.array_equal(result[name][:len(P)],values)
    before=np.linalg.norm(np.cross(P[T[:,1]]-P[T[:,0]],P[T[:,2]]-P[T[:,0]]),axis=1)*.5
    points=result['P'];after=np.linalg.norm(np.cross(points[new_T[:,1]]-points[new_T[:,0]],points[new_T[:,2]]-points[new_T[:,0]]),axis=1)*.5
    totals=np.bincount(np.asarray(parents),weights=after,minlength=len(T));error=float(np.max(np.abs(totals-before)))
    assert np.allclose(totals,before,atol=1e-9,rtol=2e-5),'High cap surface changed during refinement'
    assert (after>1e-14).all(),'Cap refinement introduced degenerate triangles'
    return result,new_T,{'old_vertices':len(P),'new_vertices':len(points),'old_triangles':len(T),'new_triangles':len(new_T),
        'extra_triangles':extra,'selected_faces':selected.tolist(),'geometric_edge_splits':len(geometric_edges),'indexed_edge_splits':len(new_edges),
        'original_attribute_prefix_exact':True,'high_surface_area_error_max_m2':error,'child_parent_faces':parents}
