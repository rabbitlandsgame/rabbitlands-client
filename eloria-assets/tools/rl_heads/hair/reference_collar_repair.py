"""Optional bounded repairs to actual reference-hair boundaries near the collar.

Original UVs are retained. Only small, orientable closed holes with a compact
valid painted chart are filled; tip curls and unrelated boundaries stay intact.
"""
import itertools
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import assemble,headref,hairgen


def _ear_clip(uv):
    uv=np.asarray(uv);order=list(range(len(uv)));result=[]
    cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
    area=sum(cross(uv[i],uv[(i+1)%len(uv)]) for i in order)
    assert abs(area)>1e-12,'Degenerate hole chart'
    sign=np.sign(area)
    while len(order)>3:
        found=False
        for at in range(len(order)):
            a,b,c=order[at-1],order[at],order[(at+1)%len(order)]
            if cross(uv[b]-uv[a],uv[c]-uv[b])*sign<=1e-12:continue
            inside=False
            for p in order:
                if p in [a,b,c]:continue
                tests=[cross(uv[y]-uv[x],uv[p]-uv[x])*sign for x,y in [(a,b),(b,c),(c,a)]]
                if min(tests)>=-1e-12:inside=True;break
            if inside:continue
            result.append([a,b,c]);order.pop(at);found=True;break
        assert found,'Hole chart is not a simple polygon'
    result.append(order);return np.asarray(result,int)


def repair(head,P,N,UV,T,spec,paint_mask=None):
    config=spec.get('collar_repair')
    if not config:return P,N,T,{'enabled':False}
    original=P.copy();_,first,weld=np.unique(np.round(P/1e-6),axis=0,return_index=True,return_inverse=True);Q=P[first]
    directed=weld[T[:,[0,1,1,2,2,0]].reshape(-1,2)];edge,count=np.unique(np.sort(directed,axis=1),axis=0,return_counts=True);edge=edge[count==1]
    directed_set=set(map(tuple,directed));ids,local=np.unique(edge,return_inverse=True);local=local.reshape(-1,2)
    degree=np.bincount(local.ravel(),minlength=len(ids));count,labels=connected_components(coo_matrix((np.ones(len(local)),(local[:,0],local[:,1])),shape=(len(ids),len(ids))),directed=False)
    low,high=np.asarray(config['below_eye_mm'])/1000;y0,y1=head.eye_mid[1]-high,head.eye_mid[1]-low
    x0,x1=np.asarray(config['abs_x_mm'])/1000;max_span=config['hole_span_mm']/1000;added=[];holes=[];filled=[]
    for component in range(count):
        selected=np.flatnonzero(labels==component);vertices=ids[selected]
        if not 3<=len(vertices)<=int(config['hole_vertices']) or not (degree[selected]==2).all():continue
        points=Q[vertices];center=points.mean(0)
        if not y0<center[1]<y1 or abs(center[0])>x1 or np.ptp(points,axis=0).max()>max_span:continue
        adjacency={int(v):[] for v in vertices}
        for a,b in edge[np.isin(edge[:,0],vertices)&np.isin(edge[:,1],vertices)]:adjacency[int(a)].append(int(b));adjacency[int(b)].append(int(a))
        order=[int(vertices[0])];last=-1
        while True:
            nxt=next(v for v in adjacency[order[-1]] if v!=last)
            if nxt==order[0]:break
            last=order[-1];order.append(nxt)
            assert len(order)<=len(vertices)
        if (order[0],order[1]) in directed_set:order=[order[0]]+list(reversed(order[1:]))
        if not all((order[(i+1)%len(order)],order[i]) in directed_set for i in range(len(order))):continue
        groups=[np.flatnonzero(weld==v) for v in order]
        if np.prod([len(group) for group in groups])>4096:continue
        choices=itertools.product(*groups);chosen=min(choices,key=lambda choice:np.ptp(UV[list(choice)],axis=0).max());chart=UV[list(chosen)]
        if np.ptp(chart,axis=0).max()>float(config['uv_span']):continue
        if paint_mask is not None:
            xy=np.clip((chart.mean(0)*np.array(paint_mask.shape[::-1])).astype(int),0,np.array(paint_mask.shape[::-1])-1)
            if paint_mask[xy[1],xy[0]]<128:continue
        try:tri=_ear_clip(chart)
        except AssertionError:continue
        new=np.asarray(chosen)[tri];added.extend(new.tolist());filled.extend(order);holes.append({'vertices':len(vertices),'span_mm':float(np.ptp(points,axis=0).max()*1000),'triangles':len(tri),'uv_span':float(np.ptp(chart,axis=0).max())})
    if added:T=np.vstack([T,np.asarray(added,int)])
    # Round only degree-two border vertices in the front collar neighborhood.
    region=(Q[:,1]>y0)&(Q[:,1]<y1)&(abs(Q[:,0])>x0)&(abs(Q[:,0])<x1)&(Q[:,2]>head.C[2]+config['front_z_mm']/1000)
    moving=ids[region[ids]&(degree==2)&~np.isin(ids,filled)]
    neighbors=coo_matrix((np.ones(len(edge)*2),(np.r_[edge[:,0],edge[:,1]],np.r_[edge[:,1],edge[:,0]])),shape=(len(Q),len(Q))).tocsr()
    counts=np.asarray(neighbors.sum(1)).ravel();rounding=Q.copy()
    for _ in range(int(config['round_iterations'])):
        mean=(neighbors@rounding)/np.maximum(counts[:,None],1)
        rounding[moving]+=.35*(mean[moving]-rounding[moving])
    delta=rounding-Q;distance=np.linalg.norm(delta,axis=1);limit=config['round_limit_mm']/1000
    delta*=np.minimum(1,limit/np.maximum(distance,1e-12))[:,None];P=P+delta[weld]
    N=headref.unit(N+assemble.morph_normals(original,T,N,P-original,weld))
    assert np.array_equal(P[~region[weld]],original[~region[weld]])
    proof={'enabled':True,'small_holes':holes,'added_triangles':len(added),'uvs_unchanged':True,'outside_positions_exact':True,'changed_vertices':int((np.linalg.norm(P-original,axis=1)>1e-10).sum()),'round_max_mm':float(np.linalg.norm(P-original,axis=1).max()*1000),'tip_region_untouched':True}
    return P,N,T,proof
