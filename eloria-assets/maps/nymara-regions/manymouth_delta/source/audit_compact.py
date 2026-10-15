"""Audit the compact delta's real, guarded EWCG routes without a server write."""
import argparse
from collections import deque
import heapq
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import numpy as np


def folded(package):
    m=json.loads((package/'world.json').read_text(encoding='utf-8'))
    raw=(package/m['collision']['binary']).read_bytes()
    _,_,_,w,h=struct.unpack_from('<4sHHII',raw)
    cells=np.frombuffer(raw,np.uint8,offset=16).reshape(h,w)
    padded=np.pad(cells,((1,0),(1,0)))[:h,:w]
    return (padded.reshape(h//2,2,w//2,2)!=0).all(axis=(1,3)),m


def adjacent(mask,p,collision=None):
    x,y=p
    for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        xx,yy=x+dx,y+dy
        if not (0<=yy<mask.shape[0] and 0<=xx<mask.shape[1] and mask[yy,xx]):continue
        if dx and dy and not (mask[y,xx] and mask[yy,x]):continue
        if collision is not None:
            if not collision.can_step(x,y,xx,yy,2):continue
            if dx and dy and not (collision.can_step(x,y,xx,y,2) and collision.can_step(x,y,x,yy,2)):continue
        yield (xx,yy),math.hypot(dx,dy)


def path_length(mask,start,end,collision=None):
    if not (mask[start[1],start[0]] and mask[end[1],end[0]]):return None
    distance={start:0.};queue=[(math.dist(start,end),start)]
    while queue:
        _,p=heapq.heappop(queue)
        if p==end:return distance[p]
        for q,length in adjacent(mask,p,collision):
            value=distance[p]+length
            if value<distance.get(q,float('inf')):
                distance[q]=value;heapq.heappush(queue,(value+math.dist(q,end),q))
    return None


def audit(package,server=None):
    mask,manifest=folded(package)
    collision=None;stage=None
    if server is not None:
        sys.path[:0]=[str(server),str(server/'tools')]
        from collision_sources import Source
        from sync_authored_collision import choose_stage,rescale
        from eloria.collision import CollisionMap,with_step_mask
        raw=Source('ewcg','collision.bin').load(package,mask.shape[0])
        stage,_,_=choose_stage(raw)
        grid=rescale(raw,stage)
        collision=with_step_mask(CollisionMap(mask.shape[1],mask.shape[0],grid.astype(np.uint8).tobytes()),2)
        mask=(grid&63)!=0
    ox,oy=manifest['coordinateTransform']['serverOrigin']
    def tile(point):return (math.floor(point[0]+ox),math.floor(oy-point[2]))
    start=tuple(next(p for p in manifest['spawnPoints'] if p['id']=='default')['serverTile'])
    reached=set()
    if mask[start[1],start[0]]:
        reached={start};queue=deque([start])
        while queue:
            p=queue.popleft()
            for q,_ in adjacent(mask,p,collision):
                if q not in reached:reached.add(q);queue.append(q)
    def near(point,limit=2):
        p=tile(point)
        candidates=[(x,y) for y in range(max(0,p[1]-limit),min(mask.shape[0],p[1]+limit+1))
            for x in range(max(0,p[0]-limit),min(mask.shape[1],p[0]+limit+1)) if mask[y,x]]
        return min(candidates,key=lambda q:math.dist(q,p)) if candidates else p
    portals=[]
    for p in manifest['portals']:
        q=tuple(p.get('serverTile',tile(p['position'])))
        valid=0<=q[1]<mask.shape[0] and 0<=q[0]<mask.shape[1]
        portals.append({'id':p['id'],'tile':q,'walkable':bool(valid and mask[q[1],q[0]]),
            'reachable':q in reached,'nearestStanding':near(p['position'])})
    secrets=[]
    for entry in manifest['interactives']:
        if entry.get('kind')!='secret':continue
        q=tuple(entry['serverTile'])
        secrets.append({'id':entry['secret'],'tile':q,'reachable':q in reached})
    routes=[]
    for road in manifest['roads']:
        points=road['waypoints'];a,b=near(points[0]),near(points[-1])
        length=path_length(mask,a,b,collision)
        physical=sum(math.dist(x,z) for x,z in zip(points,points[1:]))
        routes.append({'id':road['id'],'start':a,'end':b,'metres':None if length is None else round(length,2),
            'surveyMetres':round(physical,2),'pass':length is not None and length<=physical*1.4+15})
    legacy=json.loads(Path(__file__).with_name('legacy-content-manifest.json').read_text(encoding='utf-8'))
    ids={}
    for bucket in ('spawnPoints','landmarks','interactives','npcMarkers','harvestables','portals'):
        old={p['id'] for p in legacy.get(bucket,[])};new={p['id'] for p in manifest.get(bucket,[])}
        ids[bucket]={'baseline':len(old),'current':len(new),'missing':sorted(old-new)}
    return {'proof':'server-height-and-strict-corners' if collision is not None else 'client-mask-and-strict-corners',
        'serverStage':stage,'sourceHashes':{name:hashlib.sha256((package/name).read_bytes()).hexdigest()
            for name in ('world.glb','collision.bin','world.json')},
        'arrival':list(start),'arrivalWalkable':bool(mask[start[1],start[0]]),
        'reachableTiles':len(reached),'walkableTiles':int(mask.sum()),'portals':portals,
        'routes':routes,'secrets':secrets,'failedSecrets':[p['id'] for p in secrets if not p['reachable']],
        'ids':ids,'failedRoutes':[r['id'] for r in routes if not r['pass']],
        'failedPortals':[p['id'] for p in portals if not p['reachable']]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--server',type=Path,help='Read-only server tools for exact height/climb staging')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=audit(args.package.resolve(),args.server);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('portals','routes')}))
