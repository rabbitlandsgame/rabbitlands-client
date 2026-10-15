"""Read-only physical route contract for the compact Westhaven package.

Uses the server's real fold, stage choice and World.find_path in memory. Never
writes server configuration, collision or maps. Live NPC occupancy is checked
by the integration harness after publication.
"""
import argparse,json,math,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np

PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE.parent/'_toolkit'))
import glb_reader as G


def run(server):
    sys.path[:0]=[str(server/'tools'),str(server/'src'),str(server)]
    import sync_authored_collision as S
    from eloria.collision import CollisionMap,with_step_mask
    from eloria.world import World
    manifest=json.loads((PACKAGE/'world.json').read_text())
    cells=396; S.MAP_TILES_WIDE_BY_NAME['westhaven']=cells//S.COLLISION_SCALE
    S.ARRIVAL_TILES['westhaven']=(154,166)
    raw,_=G.read_grid(PACKAGE)
    doors=[tuple(map(int,x['serverTile'])) for x in manifest['portals']]
    secrets=[tuple(map(int,x['serverTile'])) for x in manifest['interactives'] if x.get('kind')=='secret']
    grid,fold=S.build('westhaven',PACKAGE.parents[1],doors=doors+secrets,join=False)
    world=World.__new__(World)
    world.settings=SimpleNamespace(max_walk_height_change=2)
    world.collision_maps={'westhaven':with_step_mask(CollisionMap(cells,cells,grid.heights),2)}
    world.sessions=[];world.animals_by_map={};world.animals={}
    start=(154,166)
    targets=[('portal',x['id'],tuple(map(int,x['serverTile']))) for x in manifest['portals']]
    targets += [('secret',x['id'],tuple(map(int,x['serverTile']))) for x in manifest['interactives'] if x.get('kind')=='secret']
    targets += [('service',x['role'],(round(x['position'][0]+120),round(172-x['position'][2]))) for x in manifest['contentLayout']['services']]
    results=[]
    for kind,ident,target in targets:
        x,y=target
        path=world.find_path('westhaven',start,target,set())
        results.append(dict(kind=kind,id=ident,tile=target,rawFourCells=raw[max(0,y*2-1):y*2+1,max(0,x*2-1):x*2+1].tolist(),
            rawStandable=bool(np.all(raw[max(0,y*2-1):y*2+1,max(0,x*2-1):x*2+1]>0)),
            serverStandable=bool(grid.at(x,y)),exact=bool(path and tuple(path[-1])==target),
            steps=len(path),metres=round(sum(math.dist(a,b) for a,b in zip([start]+path,path)),2),
            end=path[-1] if path else None))
    # The 196m shore polyline curves around open water; a 225m bound allows
    # its real deck joints while still catching a route around the upland.
    roads=[]
    for a,b,limit in [((154,166),(53,172),140),((53,172),(53,99),150),
        ((154,166),(271,280),240),((279,167),(335,92),225),
        ((154,166),(310,386),360),((154,166),(384,210),290)]:
        path=world.find_path('westhaven',a,b,set())
        metres=sum(math.dist(p,q) for p,q in zip([a]+path,path))
        roads.append(dict(start=a,target=b,exact=bool(path and tuple(path[-1])==b),steps=len(path),
                          metres=round(metres,2),maximumMetres=limit,practical=bool(path and tuple(path[-1])==b and metres<limit)))
    return dict(method=__doc__,glbSha256=hashlib.sha256((PACKAGE/'world.glb').read_bytes()).hexdigest(),
        collisionSha256=hashlib.sha256((PACKAGE/'collision.bin').read_bytes()).hexdigest(),
        fold=fold,targets=results,roads=roads,
        summary=dict(targets=len(results),rawBlocked=sum(not r['rawStandable'] for r in results),
            unreachable=sum(not r['exact'] for r in results),maximumSteps=max(r['steps'] for r in results),
            impracticalRoads=sum(not r['practical'] for r in roads)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--server',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();result=run(a.server.resolve());a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))
    raise SystemExit(1 if any(result['summary'][key] for key in ('rawBlocked','unreachable','impracticalRoads')) else 0)


