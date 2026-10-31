"""Optional bounded rest-shape correction for extracted temple boundary spikes."""
import numpy as np
from scipy.spatial import cKDTree
import headref,hairgen
from reference_root_edges import geometric_boundary

def conform_temples(head,scalp,P,N,T,ranges,spec):
    """Retain source mass and UV topology; use a symmetric correction rule."""
    config=spec.get('temple_conform')
    if not config:return P,N,{'enabled':False}
    e0,e1=ranges['exterior'];tri=T[(T>=e0).all(1)&(T<e1).all(1)]-e0
    border=geometric_boundary(P[e0:e1],tri)+e0
    blon,blat=headref.dir_lonlat(P[border]-head.C)
    a,b,c,d=map(float,config['longitude_ramps'])
    assert 0<=a<b<=c<d<=180
    eligible=(abs(blon)>a)&(abs(blon)<d+5)&(blat<scalp.hairline(blon)+5)
    assert eligible.any(),'Temple conformance requires a true geometric boundary'
    lon,lat=headref.dir_lonlat(P-head.C);line=scalp.hairline(lon)+float(config['margin_degrees'])
    blend=hairgen.smoothstep((abs(lon)-a)/(b-a))*hairgen.smoothstep((d-abs(lon))/(d-c))
    blend*=hairgen.smoothstep((lat-line+22)/4)
    distance=cKDTree(P[border[eligible]]).query(P)[0]
    blend*=1-hairgen.smoothstep((distance-.020)/.015)
    for part in config.get('preserve_parts',[]):
        assert part in ranges,'Unknown preserved temple-conformance part'
        blend[slice(*ranges[part])]=0
    width=float(config['softness_degrees']);assert 0<width<=3
    target=lat+blend*(line+width*np.logaddexp(0,(lat-line)/width)-lat)
    if 'max_lift_degrees' in config:
        limit=float(config['max_lift_degrees'])
        assert 0<limit<=25,'Invalid temple angular lift limit'
        target=lat+np.minimum(target-lat,limit)
    changed=(target-lat)>.01;Q=P.copy();M=N.copy()
    if changed.any():
        old,old_normal=scalp.point(lon[changed],lat[changed]);new,new_normal=scalp.point(lon[changed],target[changed])
        axis=np.cross(old_normal,new_normal);angle=np.arctan2(np.linalg.norm(axis,axis=1),(old_normal*new_normal).sum(1))
        Q[changed]=new+hairgen.rotate(P[changed]-old,axis,angle)
        M[changed]=hairgen.rotate(N[changed],axis,angle)
    assert np.array_equal(Q[~changed],P[~changed]) and np.array_equal(M[~changed],N[~changed])
    movement=np.linalg.norm(Q-P,axis=1)*1000
    assert movement.max()<=float(config['max_displacement_mm'])
    proof={'enabled':True,'uv_topology_unchanged':True,'outside_positions_normals_exact':True}
    for sign,label in [(-1,'negative'),(1,'positive')]:
        mask=lon*sign>0;proof[label]={'changed_vertices':int((changed&mask).sum()),'max_mm':float(movement[mask].max()) if mask.any() else 0.}
    return Q,M,proof
