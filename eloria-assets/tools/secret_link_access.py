"""Choose a section-link standing tile on its actual connected room floor.

Decorative waystones are destinations for discovery, not standing surfaces.
This publication adapter changes no geometry, marker, key or destination.
"""
from collections import deque
import hashlib,math,sys
from pathlib import Path
import numpy as np

def component(collision,arrival,*,terminals=(),climb=2):
    arrival=tuple(arrival);terminals=set(terminals)
    if not collision.walkable(*arrival):raise ValueError(f'Blocked actual section arrival {arrival}')
    seen={arrival:0};queue=deque([arrival])
    while queue:
        p=queue.popleft()
        if p in terminals and p!=arrival:continue
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            q=(p[0]+dx,p[1]+dy)
            if q in seen or not collision.can_step(*p,*q,climb):continue
            if dx and dy and (not collision.can_step(*p,p[0]+dx,p[1],climb) or
                              not collision.can_step(*p,p[0],p[1]+dy,climb)):continue
            seen[q]=seen[p]+1;queue.append(q)
    return seen

def clip_y(poly,y,above):
    out=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        da=(a[1]-y)*(1 if above else -1);db=(b[1]-y)*(1 if above else -1)
        if da>=-1e-10:out.append(a)
        if (da>0 and db<0) or (da<0 and db>0):out.append(a+(b-a)*da/(da-db))
    return np.array(out)

def body_distance(point,tri,low,high):
    poly=clip_y(tri,low,True)
    if len(poly):poly=clip_y(poly,high,False)
    if not len(poly):return math.inf
    poly=poly[:,[0,2]];point=np.asarray(point)
    if len(poly)==1:return float(np.linalg.norm(poly[0]-point))
    nxt=np.roll(poly,-1,axis=0);edges=nxt-poly;v=point-poly
    cross=edges[:,0]*v[:,1]-edges[:,1]*v[:,0]
    area=np.sum(poly[:,0]*nxt[:,1]-poly[:,1]*nxt[:,0])
    if len(poly)>=3 and abs(area)>1e-12 and (np.all(cross>=-1e-10) or np.all(cross<=1e-10)):return 0.
    t=np.clip(np.sum(v*edges,axis=1)/np.maximum(np.sum(edges*edges,axis=1),1e-30),0,1)
    return float(np.min(np.linalg.norm(poly+t[:,None]*edges-point,axis=1)))

def top(tri,x,z):
    if not len(tri):return None
    low=tri.min(1);high=tri.max(1)
    t=tri[(low[:,0]<=x+1e-8)&(high[:,0]>=x-1e-8)&(low[:,2]<=z+1e-8)&(high[:,2]>=z-1e-8)]
    if not len(t):return None
    a,b,c=t[:,0],t[:,1],t[:,2]
    det=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
    good=abs(det)>1e-10;a,b,c,det=a[good],b[good],c[good],det[good]
    u=((b[:,2]-c[:,2])*(x-c[:,0])+(c[:,0]-b[:,0])*(z-c[:,2]))/det
    v=((c[:,2]-a[:,2])*(x-c[:,0])+(a[:,0]-c[:,0])*(z-c[:,2]))/det
    inside=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)
    return float(np.max((u*a[:,1]+v*b[:,1]+(1-u-v)*c[:,1])[inside])) if inside.any() else None

class RoomFloor:
    def __init__(self,path,manifest):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maps/nymara-regions/_toolkit'))
        import glb_reader as G
        self.path=Path(path);self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        doc,data=G.load(self.path);matrix,_=G.hierarchy(doc)
        prefixes=tuple(manifest['navigation']['surfaceNodePrefixes']);self.transform=manifest['coordinateTransform']
        self.floors=[];self.bodies=[];self.water=[]
        for index,node in enumerate(doc['nodes']):
            if 'mesh' not in node:continue
            name=node.get('name','');mat=matrix[index]
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode',4)!=4:continue
                p=G.accessor(doc,data,primitive['attributes']['POSITION']).astype(float)
                p=p@mat[:3,:3].T+mat[:3,3]
                order=G.accessor(doc,data,primitive['indices']).reshape(-1).astype(int) if 'indices' in primitive else np.arange(len(p))
                tri=p[order].reshape(-1,3,3)
                material=doc['materials'][primitive.get('material',0)].get('name','')
                if name.startswith(prefixes):
                    normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(normal,axis=1)
                    self.floors.append(tri[normal[:,1]>.55*length])
                elif name.startswith('Water_') or 'water' in material.lower():self.water.append(tri)
                else:self.bodies.append((name,tri,tri.min(1),tri.max(1)))
        self.floors=np.concatenate(self.floors) if self.floors else np.empty((0,3,3))
        self.water=np.concatenate(self.water) if self.water else np.empty((0,3,3))

    def __call__(self,tile):
        t=self.transform;ox,oy=t['serverOrigin'];origin=t.get('origin',[0,0,0]);scale=t.get('metresPerTile',1.)
        x=origin[0]+(tile[0]-ox+.5)*scale;z=origin[2]-(tile[1]-oy+.5)*scale
        y=top(self.floors,x,z)
        if y is None:return None
        wet=top(self.water,x,z)
        if wet is not None and wet>y+.001:return None
        for name,tri,low,high in self.bodies:
            mask=(low[:,0]<x+.46)&(high[:,0]>x-.46)&(low[:,2]<z+.46)&(high[:,2]>z-.46)&(low[:,1]<y+1.9)&(high[:,1]>y+.05)
            if any(body_distance((x,z),p,y+.05,y+1.9)<.45-1e-5 for p in tri[mask]):return None
        return {'position':[x,y,z],'radius':.45,'height':1.9,'groundClearance':.05,
                'geometry':str(self.path),'geometrySha256':self.sha256}

def select_link(collision,arrival,target,physical,*,forbidden=(),climb=2,limit=2):
    target=tuple(target);forbidden=set(forbidden)-{target};reach=component(collision,arrival,terminals=forbidden,climb=climb)
    candidates=[(target[0]+dx,target[1]+dy) for dx in range(-limit,limit+1) for dy in range(-limit,limit+1)]
    candidates.sort(key=lambda p:(max(abs(p[i]-target[i]) for i in (0,1)),math.dist(p,target),p))
    for p in candidates:
        if p not in reach or p in forbidden:continue
        proof=physical(p)
        if proof is not None:return p,{'authoredTile':list(target),'selectedTile':list(p),'sectionArrival':list(arrival),
                                     'walkingSteps':reach[p],'changed':p!=target,'physical':proof}
    raise ValueError(f'No connected body-clear section link within {limit} tiles of {target}')
