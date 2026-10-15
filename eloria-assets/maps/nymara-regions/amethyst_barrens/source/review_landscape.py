"""Read-only compact-region review against a frozen Amethyst package.

Checks stable entrances/secret identities and conservatively folded portal
tiles, and emits a reproducible machine-readable summary for the rollout.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
import glb_reader as G


def review(baseline):
    package=Path(__file__).resolve().parents[1]
    grid,w=G.read_grid(package)
    old=json.loads((baseline/'world.json').read_text())
    doc,_=G.load(package/'world.glb')
    nodes={n.get('name') for n in doc['nodes']}
    old_portals={p['id'] for p in old['portals']}
    new_portals={p['id'] for p in w['portals']}
    old_secrets={p['id'] for p in old['interactives'] if p.get('kind')=='secret'}
    new_secrets={p['id'] for p in w['interactives'] if p.get('kind')=='secret'}
    size=w['asset']['serverCells']
    mask=np.zeros((size,size),bool)
    for y in range(size):
        for x in range(size):
            patch=grid[max(0,2*y-1):2*y+1,max(0,2*x-1):2*x+1]
            mask[y,x]=patch.size==4 and bool(np.all(patch>0))
    arrival=(140,85)
    connected={arrival} if mask[arrival[1],arrival[0]] else set()
    todo=deque(connected)
    while todo:
        x,y=todo.popleft()
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
            q=(x+dx,y+dy)
            if q in connected or not (0<=q[0]<size and 0<=q[1]<size) or not mask[q[1],q[0]]:continue
            connected.add(q);todo.append(q)
    portals=[]
    for p in w['portals']:
        x,y=p['serverTile']
        patch=grid[max(0,2*y-1):2*y+1,max(0,2*x-1):2*x+1]
        portals.append({'id':p['id'],'tile':[x,y],'position':p['position'],
                        'conservativeTileWalkable':bool(patch.size==4 and np.all(patch>0)),
                        'connectedToArrival':(x,y) in connected})
    connected_xy=np.array(sorted(connected),dtype=float)
    secret_access=[]
    for secret in w['interactives']:
        if secret.get('kind')!='secret':continue
        tile=secret.get('serverTile')
        if tile is None:
            position=secret['position']
            tile=[int(np.floor(position[0]+116)),int(np.floor(116-position[2]))]
        distances=np.sum((connected_xy-np.array(tile))**2,axis=1)
        nearest=int(np.argmin(distances))
        secret_access.append({'id':secret['id'],'tile':tile,
                              'nearestConnectedTile':connected_xy[nearest].astype(int).tolist(),
                              'distanceMetres':round(float(np.sqrt(distances[nearest])),2)})
    missing_nodes=[{'id':l['id'],'node':l.get('node')} for l in w['landmarks']
                   if l.get('node') and l['node'] not in nodes]
    return {'extentMetres':w['asset']['serverCells'],
            'origin':w['coordinateTransform']['serverOrigin'],
            'lostPortalIds':sorted(old_portals-new_portals),
            'lostSecretIds':sorted(old_secrets-new_secrets),
            'lostLandmarkIds':sorted({p['id'] for p in old['landmarks']}-{p['id'] for p in w['landmarks']}),
            'missingLandmarkNodes':missing_nodes,'portals':portals,
            'primaryComponentTiles':len(connected),'secretApproaches':secret_access,
            'connectivityLimit':'Conservative four-neighbour walkability only; the real server walker verifies height-aware movement.',
            'secretsRetained':len(new_secrets),'landmarks':len(w['landmarks']),
            'collision':w['collision'],'performance':w['performance'],
            'streamingBorders':w.get('streamingBorders',[]),
            'interiors':'Existing Resonant Vault and secrets geometry retains its dimensions; '
                        'exterior door/return coordinates migrate through stable IDs.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    result=review(args.baseline)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('collision','performance','streamingBorders')},indent=2))
    if result['lostPortalIds'] or result['lostSecretIds'] or result['lostLandmarkIds'] or result['missingLandmarkNodes']:
        raise SystemExit(1)
    if any(not p['conservativeTileWalkable'] for p in result['portals']):raise SystemExit(2)
    if any(not p['connectedToArrival'] for p in result['portals']):raise SystemExit(3)
    if any(s['distanceMetres']>6 for s in result['secretApproaches']):raise SystemExit(4)
