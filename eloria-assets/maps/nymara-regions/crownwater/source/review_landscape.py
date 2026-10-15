"""Read-only identity, strict collision and working-post review."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE.parent/'_toolkit'))
import glb_reader as G

def review(baseline,server):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import collision_sources as C
    import sync_authored_collision as SYNC
    from content_placement import MapPlacer,flood,to_tile
    from eloria.collision import CollisionMap,with_step_mask
    old=json.loads((baseline/'world.json').read_text())
    w=json.loads((PACKAGE/'world.json').read_text())
    raw=C.authored_collision('crownwater',396,PACKAGE.parents[1])
    factor,_,stage_stats=SYNC.choose_stage(raw)
    final=SYNC.rescale(raw,factor).astype(np.uint8)
    collision=with_step_mask(CollisionMap(396,396,final.tobytes()),2)
    reachable=flood(collision,[(120,120)])
    placer=MapPlacer(collision,reachable)
    def is_reachable(tile):return placer.is_reachable(*tile)
    portals=[{'id':p['id'],'tile':p['serverTile'],
              'walkable':collision.walkable(*p['serverTile']),
              'connectedToArrival':is_reachable(p['serverTile'])} for p in w['portals']]
    secrets=[]
    for p in w['interactives']:
        if p.get('kind')!='secret':continue
        tile=p.get('serverTile') or to_tile(p['position'],[120,120],1)
        near=placer.nearest_fit(*tile,limit=8)
        secrets.append({'id':p['id'],'tile':tile,'nearestConnectedTile':near,
            'distanceMetres':round(float(np.linalg.norm(np.array(near)-tile)),2) if near else None})
    posts=[]
    for name,pos in w['contentLayout']['npcs'].items():
        tile=to_tile(pos,[120,120],1);near=placer.nearest_fit(*tile,limit=3)
        posts.append({'name':name,'tile':tile,'resolvedTile':near})
        if near:placer.reserve(*near,2)
    doc,_=G.load(PACKAGE/'world.glb');nodes={n.get('name') for n in doc['nodes']}
    hashes={f:hashlib.sha256((PACKAGE/f).read_bytes()).hexdigest()
            for f in ('world.glb','world-lod2.glb','world.json','collision.bin','minimap.webp')}
    def ids(data,key):return {p['id'] for p in data.get(key,[])}
    return {'extentMetres':396,'origin':[120,120],'arrival':[120,120],
        'lostPortalIds':sorted(ids(old,'portals')-ids(w,'portals')),
        'lostSecretIds':sorted({p['id'] for p in old['interactives'] if p.get('kind')=='secret'}-
            {p['id'] for p in w['interactives'] if p.get('kind')=='secret'}),
        'lostLandmarkIds':sorted(ids(old,'landmarks')-ids(w,'landmarks')),
        'missingLandmarkNodes':[p['id'] for p in w['landmarks'] if p.get('node') not in nodes],
        'portals':portals,'secretApproaches':secrets,'npcPosts':posts,
        'primaryComponentTiles':sum(reachable),'stageMillimetres':factor*200,
        'stageChoice':stage_stats,'packageSha256':hashes,'performance':w['performance'],
        'collision':w['collision'],
        'limitations':'Strict World diagonal/climb rules on folded current client collision; '
            'the coordinator still verifies final published ELM and actual live routes.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args();result=review(args.baseline,args.server)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('collision','performance','packageSha256')},indent=2))
