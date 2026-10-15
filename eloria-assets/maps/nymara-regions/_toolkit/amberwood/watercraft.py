"""Water skins clipped to a sampled shore, shared by legacy and toolkit regions."""
import numpy as np
from . import mesh as M

def pools(sample, sites, cell=0.7, material="water_pool"):
    """Horizontal pools clipped inside their bowl; sites are x,z,radius,level.

    Clip each triangle against signed wet depth and the pool's radius. A cell
    touching land is cut inside the cell, never emitted as a whole square.
    """
    if cell <= 0:
        raise ValueError("water sampling cell must be positive")
    positions=[];indices=[]
    for cx,cz,radius,level in sites:
        if radius <= 0:
            raise ValueError("pool radius must be positive")
        axis=np.linspace(-radius*1.3,radius*1.3,max(3,int(radius*2.6/cell)+1))
        gx,gz=np.meshgrid(axis+cx,axis+cz)
        signed=np.minimum(level-.08-sample(gx,gz),radius*1.3-np.hypot(gx-cx,gz-cz))
        for row in range(len(axis)-1):
            for col in range(len(axis)-1):
                corners=[(row,col),(row+1,col),(row+1,col+1),(row,col+1)]
                for tri in ((0,1,2),(0,2,3)):
                    polygon=[(np.array([gx[corners[k]],level,gz[corners[k]]]),signed[corners[k]]) for k in tri]
                    clipped=[]
                    for (a,sa),(b,sb) in zip(polygon,polygon[1:]+polygon[:1]):
                        if sa>=0:clipped.append(a)
                        if (sa>=0)!=(sb>=0):
                            clipped.append(a+(b-a)*sa/(sa-sb))
                    if len(clipped)<3:continue
                    start=len(positions);positions.extend(clipped)
                    for i in range(1,len(clipped)-1):
                        if np.linalg.norm(np.cross(clipped[i]-clipped[0],clipped[i+1]-clipped[0]))>1e-9:
                            indices.extend([start,start+i,start+i+1])
    p=np.asarray(positions,float).reshape(-1,3)
    return M.Mesh(positions=p,normals=np.tile([0,1,0],(len(p),1)),
                  uvs=p[:,[0,2]]*.25,indices=np.asarray(indices,int),material=material)
