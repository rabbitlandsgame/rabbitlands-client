"""Create short real-client route fixtures from the final compact collision.

Each doorway gets its own surveyed approach, avoiding long server path requests
and intentional portals while travelling to another point of interest.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
import glb_reader as G


def fixtures():
    package=Path(__file__).resolve().parents[1]
    grid,w=G.read_grid(package)
    size=w['asset']['serverCells']
    mask=np.zeros((size,size),bool)
    for y in range(size):
        for x in range(size):
            patch=grid[max(0,2*y-1):2*y+1,max(0,2*x-1):2*x+1]
            mask[y,x]=patch.size==4 and bool(np.all(patch>0))
    portals=w['portals']
    def near(target):
        x,y=map(int,target)
        candidates=[(dx*dx+dy*dy,x+dx,y+dy) for dx in range(-9,10) for dy in range(-9,10)
                    if 0<=x+dx<size and 0<=y+dy<size and mask[y+dy,x+dx]]
        _,x,y=min(candidates)
        return [x,y]
    def safe_start(target, preferred):
        # A short flood fill confirms that the approach shares the threshold's
        # actual open ground. The server still proves height-aware traversal.
        target=tuple(target)
        todo=deque([target]);seen={target};choices=[]
        while todo:
            x,y=todo.popleft()
            distance=abs(x-target[0])+abs(y-target[1])
            if 10<=distance<=19:
                if all(abs(x-p['serverTile'][0])+abs(y-p['serverTile'][1])>6 for p in portals):
                    choices.append(((x-preferred[0])**2+(y-preferred[1])**2,[x,y]))
            if distance>=24:continue
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                q=x+dx,y+dy
                if q in seen or not(0<=q[0]<size and 0<=q[1]<size) or not mask[q[1],q[0]]:continue
                seen.add(q);todo.append(q)
        if not choices:raise ValueError(f'No clear approach for {target}')
        return min(choices)[1]
    result=[{'id':'amethyst-service-court','map':'amethyst_barrens','start':near([140,85]),
             'startTolerance':2,'distance':32,'steps':[
                 {'tile':near([137,98]),'label':'information-and-cook','capture':'amethyst-cook-court'},
                 {'tile':near([147,101]),'label':'storage-exchange','capture':'amethyst-storage'},
                 {'tile':near([155,101]),'label':'crafting-bench','capture':'amethyst-crafting'},
                 {'tile':near([146,114]),'label':'inhabited-fronts','capture':'amethyst-bunkhouse'}]},
            {'id':'amethyst-worked-seam','map':'amethyst_barrens','start':near([210,115]),
             'startTolerance':2,'yaw':70,'distance':34,'steps':[
                 {'tile':near([217,124]),'label':'quarry-approach','capture':'amethyst-seam-approach'},
                 {'tile':near([228,128]),'label':'crystal-workings','capture':'amethyst-crystal-workings'}]},
            {'id':'amethyst-quiet-basin','map':'amethyst_barrens','start':near([164,65]),
             'startTolerance':2,'distance':32,'steps':[
                 {'tile':near([173,55]),'label':'lee-habitat','capture':'amethyst-lee-habitat'},
                 {'tile':near([188,50]),'label':'open-encounter-ground','capture':'amethyst-open-basin'}]}]
    preferred={'north-pass':[170,360],'west-road':[22,308],
               'south-road':[170,22],'east-shore':[343,41]}
    for p in portals:
        target=p['serverTile']
        start=safe_start(target,preferred.get(p['id'],[target[0],target[1]-14]))
        steps=[]
        if p['id']=='east-shore':
            start=near([341,56])
            steps=[{'tile':near([345,48]),'label':'surveyed-packet-bank','capture':'amethyst-packet-bank'},
                   {'tile':near([350,38]),'label':'packet-jetty-deck','capture':'amethyst-packet-deck'}]
        steps.append({'tile':target,'destination':p['destinationMap'],'label':p['name'],
                      'capture':'amethyst-arrive-'+p['id']})
        result.append({'id':'amethyst-'+p['id'],'map':'amethyst_barrens','start':start,
                       'startTolerance':2,'distance':30,'steps':steps})
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    routes=fixtures()
    args.out.write_text(json.dumps(routes,indent=2)+'\n')
    print(f'{len(routes)} routes written to {args.out}')
