"""Generate Crownwater routes against served collision and occupied working posts.

Interior walks clear each arrival threshold by two metres before returning.
This tool only writes the fixture and its occupancy audit.
"""
import argparse,hashlib,json,math,sys
from collections import defaultdict,deque
from pathlib import Path
from types import SimpleNamespace
PACKAGE=Path(__file__).resolve().parents[1]
# The western cistern approach crosses an otter habitat. Start on the garden
# walk beyond the pavilion instead: clear served ground, 21 steps to the door,
# and about20m from the nearest configured wildlife anchor. Keep exact arrival.
PORTAL_APPROACH_STARTS={'cistern-stair':(78,211)}

def fixtures(server,data):
    sys.path[:0]=[str(server)]
    try:  # base content tables only, never the continent-v2 overlay (serve plan CV13)
        from eloria import content_overlay
    except ImportError:  # an older server checkout has no continent-v2 overlay, so nothing to switch off
        pass
    else:
        content_overlay.configure(False)
    from eloria.collision import load_elm_collision,with_step_mask
    from eloria.footprint import footprint_of
    from eloria.interactives import load_interactives
    from eloria.maps import load_maps
    from eloria.npcs import load_npcs
    from eloria.world import World
    profile=server/'config/eloria';maps,portals=load_maps(profile/'maps.txt')
    npcs=load_npcs(profile/'npcs.txt');items=load_interactives(profile/'interactives.txt')
    manifest=json.loads((PACKAGE/'world.json').read_text())
    world=World.__new__(World);world.settings=SimpleNamespace(max_walk_height_change=2)
    world.collision_maps={};world.sessions=[];world.animals_by_map={};world.animals={}
    fixed=defaultdict(set);automatic=defaultdict(set);proof=[];arrivals=[]
    for npc in npcs:fixed[npc.map_id].update(footprint_of(npc).tiles(npc.x,npc.y))
    for item in items.values():
        if item.role in ('information','storage','crafting_station','training'):
            fixed[item.map_id].update((item.x+dx,item.y+dy) for dx in (-1,0,1) for dy in (-1,0,1))
    for p in portals:
        if p.object_id is None:automatic[p.source].add((p.x,p.y))
    def collision(name):
        if name not in world.collision_maps:
            world.collision_maps[name]=with_step_mask(load_elm_collision(data/maps[name].file),2)
        return world.collision_maps[name]
    def path(name,start,target,allow_portal=False):
        start,target=tuple(start),tuple(target)
        if target in fixed[name] or not collision(name).walkable(*target):return None
        points=world.find_path(name,start,target,fixed[name])
        if start!=target and (not points or points[-1]!=target):return None
        crossed=set(points)&automatic[name]
        if allow_portal:crossed.discard(target)
        return None if crossed else points
    def clear(name,post,start=None,minimum=0,maximum=5):
        post=tuple(post);choices=[]
        for dx in range(-maximum,maximum+1):
            for dy in range(-maximum,maximum+1):
                if not minimum<=max(abs(dx),abs(dy))<=maximum:continue
                q=(post[0]+dx,post[1]+dy)
                if q in fixed[name]|automatic[name] or not collision(name).walkable(*q):continue
                points=path(name,start,q) if start is not None else []
                if points is not None:choices.append((math.dist(q,post),len(points),q))
        if not choices:raise ValueError(f'No clear reachable standing tile: {name} {post}')
        return min(choices)[2]
    def start_for(target):
        target=tuple(target);queue=deque([(target,0)]);seen={target};choices=[]
        while queue:
            q,steps=queue.popleft()
            if 10<=steps<=16 and q not in fixed['crownwater'] and all(math.dist(q,p)>5 for p in automatic['crownwater']):
                points=path('crownwater',q,target,True)
                if points is not None:choices.append((abs(steps-13),q))
            if steps>=16:continue
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                n=q[0]+dx,q[1]+dy
                if n in seen or n in fixed['crownwater'] or not collision('crownwater').can_step(*q,*n,2):continue
                seen.add(n);queue.append((n,steps+1))
        if not choices:raise ValueError(f'No short occupied-world approach for {target}')
        return min(choices)[1]
    result=[]
    def route(identity,start,**extra):
        assert tuple(start) not in fixed['crownwater']|automatic['crownwater'],(identity,start)
        r={'id':'crownwater-'+identity,'map':'crownwater','start':list(start),'distance':32,**extra,'steps':[]}
        result.append(r);return r
    def leg(r,name,start,target,label,**extra):
        target=tuple(target);points=path(name,start,target,'destination' in extra)
        if points is None or len(points)>=512:raise ValueError(f'No exact World path: {r["id"]} {name} {start} -> {target}')
        for index in range(39,max(0,len(points)-1),40):
            r['steps'].append({'tile':list(points[index]),'label':label+' approach'})
        r['steps'].append({'tile':list(target),'label':label,**extra})
        proof.append({'route':r['id'],'map':name,'start':start,'target':target,'steps':len(points),
                      'metres':round(sum(math.dist(a,b) for a,b in zip([tuple(start)]+points,points)),3),
                      'targetOccupied':False,'accidentalPortals':[]})
        return target
    r=route('service-court',(120,120));at=tuple(r['start'])
    for role,identity,reply in [('information',13,'The local board records'),('storage',14,None),('crafting_station',15,'This field station supports')]:
        item=items['crownwater',identity];target=clear('crownwater',(item.x,item.y),at,2,2)
        extra={'useObject':identity,'capture':'crown-'+role}
        if reply:extra['expectText']=reply
        else:extra['expectStorage']=True
        at=leg(r,'crownwater',at,target,role,**extra)
    leg(r,'crownwater',at,clear('crownwater',(102,132),at),'net-menders-front',capture='crown-inhabited-harbour')
    for identity,start,stops,yaw in [
        ('civic-approach',(149,149),[((162,162),'graded-basilica-bank','crown-civic-bank'),((181,176),'processional-walk','crown-procession'),((198,183),'basilica-forecourt','crown-basilica')],-35),
        ('working-shores',(287,189),[((295,182),'pearl-divers-shore','crown-pearl-shore'),((307,187),'pearl-working-ground','crown-pearl-work')],0),
        ('arcades-keeper',(140,133),[((135,123),'Tollmaster Quent','crown-arcades-keeper'),((152,122),'Drowned Arcades return court','crown-arcades-return')],0)]:
        r=route(identity,clear('crownwater',start),yaw=yaw);at=tuple(r['start'])
        for post,label,capture in stops:at=leg(r,'crownwater',at,clear('crownwater',post,at),label,capture=capture)
    for authored in manifest['portals']:
        tile=tuple(authored['serverTile'])
        matches=[p for p in portals if p.source=='crownwater' and (p.x,p.y)==tile and p.destination==authored['destinationMap'] and p.object_id is None]
        assert len(matches)==1,(authored['id'],matches)
        entry=matches[0];arrival=(entry.destination_x,entry.destination_y)
        occupied=arrival in fixed[entry.destination]
        arrivals.append({'door':authored['id'],'map':entry.destination,'tile':arrival,'occupied':occupied,'walkable':collision(entry.destination).walkable(*arrival)})
        assert not occupied and arrivals[-1]['walkable'],arrivals[-1]
        start=PORTAL_APPROACH_STARTS.get(authored['id'])
        r=route(authored['id'],start if start is not None else start_for(tile),distance=30)
        leg(r,'crownwater',r['start'],tile,authored['name'],destination=entry.destination,capture='crown-arrive-'+authored['id'])
        if entry.destination!='drowned_crown':continue
        back=next(p for p in portals if p.source=='drowned_crown' and (p.x,p.y)==arrival and p.destination=='crownwater' and p.object_id is None)
        away=clear('drowned_crown',arrival,arrival,2,2)
        leg(r,'drowned_crown',arrival,away,'clear interior threshold')
        leg(r,'drowned_crown',away,arrival,'return from interior',destination='crownwater',capture='crown-return-'+authored['id'])
        returned=(back.destination_x,back.destination_y)
        assert returned not in fixed['crownwater'] and collision('crownwater').walkable(*returned),(authored['id'],returned)
    report={'method':'Actual World.find_path on served ELMs, configured NPC footprints and conservative3x3 service furniture. Automatic portals are checked against the resulting path, never artificially blocked.',
            'routes':len(result),'legs':len(proof),'allPass':True,'maxSteps':max(p['steps'] for p in proof),
            'configHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [profile/'maps.txt',profile/'npcs.txt',profile/'interactives.txt']},
            'mapHashes':{name:hashlib.sha256((data/maps[name].file).read_bytes()).hexdigest() for name in world.collision_maps},'arrivals':arrivals,'paths':proof,
            'limitation':'Moving creatures are verified by the live run. Furniture has conservative client-space clearance; configured NPCs occupy their exact World footprint (one tile).'}
    return result,report
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--data',type=Path,help='Current served ELM directory');ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();server=args.server.resolve();data=args.data or server.parent/'work-output/coastal-rollout/eloria-data'
    result,report=fixtures(server,data.resolve())
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    args.out.with_name('fixture-occupancy-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(result)} routes / {len(report["paths"])} exact occupied-world legs PASS; maximum {report["maxSteps"]} path steps')
