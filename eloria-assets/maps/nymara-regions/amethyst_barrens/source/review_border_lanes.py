"""Read-only seven-lane review of Amethyst's final client and served collision.

Checks every trigger and its two-tile-inward receiving position separately,
then walks all seven lanes forty metres into the local collar. This separates
an Amethyst trigger failure from a failure at the reciprocal destination.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

PACKAGE=Path(__file__).resolve().parents[1]
CLIENT=PACKAGE.parents[3]
sys.path.insert(0,str(PACKAGE.parent/'_toolkit'))
sys.path.insert(0,str(CLIENT/'eloria-assets/tools'))
import glb_reader as G
import continent_portals as C


def review(server, maps):
    grid,manifest=G.read_grid(PACKAGE)
    collision=C.load_collision(server,maps,'amethyst_barrens')
    portals=C.load_portals('amethyst_barrens')
    borders=[]
    for frame in manifest['streamingBorders']:
        trigger=portals[frame['portal']]['tile']
        outward=frame['outward']
        inward=(-outward[0],outward[1])
        tangent=(-outward[1],-outward[0])
        lanes=[]
        for offset in range(-frame['halfWidthTiles'],frame['halfWidthTiles']+1):
            samples=[]
            for depth in range(41):
                x=trigger[0]+offset*tangent[0]+depth*inward[0]
                y=trigger[1]+offset*tangent[1]+depth*inward[1]
                patch=grid[max(0,2*y-1):2*y+1,max(0,2*x-1):2*x+1]
                previous=(x-inward[0],y-inward[1])
                samples.append({'depthMetres':depth,'tile':[x,y],
                                'halfGrid':patch.astype(int).tolist(),
                                'clientOpen':bool(patch.size==4 and np.all(patch>0)),
                                'serverOpen':collision.walkable(x,y),
                                'serverStepFromPrevious':True if depth==0 else
                                    collision.can_step(*previous,x,y,2)})
            lanes.append({'offset':offset,'trigger':samples[0],'arrival':samples[2],
                          'blockedSamples':[s for s in samples if not s['clientOpen'] or not s['serverOpen']],
                          'blockedSteps':[s for s in samples if not s['serverStepFromPrevious']]})
        borders.append({'id':frame['id'],'portal':frame['portal'],'lanes':lanes})
    return {'region':'amethyst_barrens','samples':sum(len(b['lanes'])*41 for b in borders),
            'borders':borders,'note':'Actual reciprocal destination lanes are validated by continent_portals.py; this report covers Amethyst terrain.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--maps',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    result=review(args.server,args.maps)
    args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    failures=[(b['portal'],l['offset'],len(l['blockedSamples']),len(l['blockedSteps']))
              for b in result['borders'] for l in b['lanes'] if l['blockedSamples'] or l['blockedSteps']]
    print(json.dumps({'samples':result['samples'],'failures':failures}))
    raise SystemExit(1 if failures else 0)
