"""Audit authored portal/interaction access against the package walking grid.

This is a geometry authoring diagnostic; the server's live route walker remains
the authoritative movement proof. It does not rewrite any content or grid.
"""
from collections import deque
from pathlib import Path
import argparse
import json
import struct
import numpy as np


def audit(package):
    package=Path(package)
    world=json.loads((package/'world.json').read_text())
    payload=(package/'collision.bin').read_bytes()
    _,_,_,width,height=struct.unpack('<4sHHII',payload[:16])
    mask=np.frombuffer(payload[16:],np.uint8).reshape(height,width)>0
    origin=world['coordinateTransform']['serverOrigin'];cell=world['collision']['cellMetres']
    def at(p):return int((origin[1]-p[2])/cell),int((p[0]+origin[0])/cell)
    start=at(world['spawnPoints'][0]['position'])
    seen=np.zeros(mask.shape,bool);queue=deque([start]);seen[start]=True
    while queue:
        z,x=queue.popleft()
        for dz,dx in ((0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
            a,b=z+dz,x+dx
            if 0<=a<height and 0<=b<width and mask[a,b] and not seen[a,b]:
                seen[a,b]=True;queue.append((a,b))
    records=[]
    for kind in ('portals','interactives'):
        for e in world[kind]:
            z,x=at(e['position'])
            exact=bool(seen[z,x])
            around=seen[max(0,z-4):z+5,max(0,x-4):x+5]
            nearest=None
            if not exact:
                candidates=np.argwhere(seen[max(0,z-50):z+51,max(0,x-50):x+51])
                if len(candidates):
                    candidates+=np.array([max(0,z-50),max(0,x-50)])
                    zz,xx=candidates[np.argmin(np.sum((candidates-np.array([z,x]))**2,axis=1))]
                    nearest=[round((xx+.5)*cell-origin[0],2),round(origin[1]-(zz+.5)*cell,2)]
            records.append({'nearestConnectedXZ':nearest,'kind':kind,'id':e['id'],'position':e['position'],
                'walkable':bool(mask[z,x]),'connected':exact,'withinTwoMetres':bool(around.any())})
    return {'connectedHalfMetreCells':int(seen.sum()),'walkableHalfMetreCells':int(mask.sum()),
            'allPortalsConnected':all(r['connected'] for r in records if r['kind']=='portals'),
            'allInteractionsApproachable':all(r['withinTwoMetres'] for r in records if r['kind']=='interactives'),
            'records':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=audit(args.package)
    text=json.dumps(result,indent=2)+'\n'
    if args.report:args.report.write_text(text)
    print(text)
    raise SystemExit(0 if result['allPortalsConnected'] and result['allInteractionsApproachable'] else 1)
