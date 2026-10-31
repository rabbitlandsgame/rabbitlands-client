"""Optional geometric root-edge colouring for UV-split reference surfaces."""
import numpy as np
from scipy.spatial import cKDTree
import headref

def geometric_boundary(P,T):
    """Return actual open-edge vertices, excluding duplicated UV seam edges."""
    _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
    edges=np.sort(weld[T[:,[0,1,1,2,2,0]].reshape(-1,2)],axis=1)
    edge,count=np.unique(edges,axis=0,return_counts=True)
    return np.flatnonzero(np.isin(weld,np.unique(edge[count==1])))

def root_colours(head,scalp,P,T,COL,ranges,distance,spec):
    """Return copied RGBA with geometric frontal root fade; detail stays intact."""
    COL=COL.copy();core_end=ranges['detail'][0]
    COL[:core_end,0]=1.;COL[:core_end,1]=np.clip(distance[:core_end]/.20,0,1)
    sector=float(spec.get('root_sector_degrees',85));band=float(spec.get('root_band_degrees',8))
    assert 0<sector<=180 and 0<band<=30,'Invalid root colouring sector/band'
    lon,lat=headref.dir_lonlat(P[:core_end]-head.C);eligible=(abs(lon)<sector)&(lat<scalp.hairline(lon)+band)
    e0,e1=ranges['exterior'];outer=T[(T>=e0).all(1)&(T<e1).all(1)]-e0
    border=geometric_boundary(P[e0:e1],outer)+e0;border=border[eligible[border]]
    if len(border):
        separation=cKDTree(P[border]).query(P[:core_end])[0]
        COL[np.flatnonzero(eligible),0]=np.clip(separation[eligible]/(spec['soft_hairline_mm']/1000),0,1)
    cap_softness=float(spec.get('soft_cap_edge_mm',0))
    if cap_softness:
        assert 0<cap_softness<=3 and 'shell' in ranges
        s0,s1=ranges['shell'];tri=T[(T>=s0).all(1)&(T<s1).all(1)]-s0
        boundary=geometric_boundary(P[s0:s1],tri)+s0
        assert len(boundary),'A soft cap requires an actual open scalp boundary'
        distance=cKDTree(P[boundary]).query(P[s0:s1])[0]
        COL[s0:s1,0]=np.minimum(COL[s0:s1,0],np.clip(distance/(cap_softness/1000),0,1))
    return COL
