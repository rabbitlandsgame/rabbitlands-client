"""Publish six surveyed room staff posts without changing geometry or portals.

Run after content relocation, before family package digests. The default is a
dry run. These named posts are authored here; generic room markers remain
independent unless they explicitly name the same staff identity.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,re
from pathlib import Path

from generate_continent_walk_proof import runtime,AccessFlood,WalkAudit
from sync_geographic_family import CLIENT,family

# Actual emitted body/floor survey: interior-staff-candidates.json. All moves
# remain on the original entry room floor, three tiles clear of the arrival.
POSTS=(
    ('Estate Sporewright Umber Coll','amberwood_estate',(58,58),(58,55),0.,'Amber Hall entry-side service post'),
    ('Barrow Lamplighter Ess Corrow','grey_moor_barrows',(11,162),(11,159),0.,'Great Barrow entry lamp post'),
    ('Labyrinth Sounder Ath-Rulu','manymouth_flooded_labyrinth',(23,344),(20,344),0.,'Flooded Labyrinth dry entry verge'),
    ('Lens Grinder Ottil Wren','mirrorhold_interiors',(47,187),(44,187),6.,'Lens Vault marble stairhead side'),
    ('Hall Register Sefton Ames','mirrorhold_interiors',(154,182),(151,182),0.,'Citadel cellar entry-side register'),
    ('Vault Calibrator Oleth Ryne','resonant_vault',(25,307),(22,307),0.,'Resonant Vault entry-side calibration post'),
)

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def rewrite_roster(text,posts=POSTS):
    lines=text.splitlines(keepends=True);changes=[]
    for name,region,old,new,height,reason in posts:
        matches=[i for i,line in enumerate(lines) if len(p:=line.split('|'))>=6 and
                 p[0].strip()=='npc' and p[1].strip()==name]
        if len(matches)!=1:raise ValueError(f'Expected exactly one staff identity: {name}')
        i=matches[0];parts=lines[i].split('|')
        if parts[2].strip()!=region:raise ValueError(f'{name}: authored room changed')
        previous=tuple(int(parts[j]) for j in (3,4))
        if previous not in (old,new):raise ValueError(f'{name}: unexpected authored position {previous}')
        if parts[5].strip()!='dialogue':raise ValueError(f'{name}: authored role changed')
        for j,value in zip((3,4),new):parts[j]=re.sub(r'\d+',str(value),parts[j],count=1)
        lines[i]='|'.join(parts)
        changes.append({'name':name,'map':region,'previous':list(previous),'tile':list(new),
                        'height':height,'reason':reason,'changed':previous!=new})
    return ''.join(lines),changes

def marker_update(manifest,posts=POSTS):
    result=copy.deepcopy(manifest);markers=result.setdefault('npcMarkers',[]);reconciled=[]
    t=result['coordinateTransform'];ox,oy=t['serverOrigin'];scale=t.get('metresPerTile',1)
    origin=t.get('origin',[0,0,0]);sign=-1 if t.get('invertServerY',True) else 1
    for name,region,old,new,height,reason in posts:
        ident='served-staff-'+re.sub('[^a-z0-9]+','-',name.lower()).strip('-')
        matches=[m for m in markers if m.get('id') in (ident,name) or m.get('name')==name or m.get('label')==name]
        if len(matches)>1:raise ValueError(f'{name}: duplicate named client markers')
        marker=matches[0] if matches else {}
        if not matches:markers.append(marker)
        else:reconciled.append(marker.get('id',name))
        marker.update(id=ident,name=name,map=region,role='dialogue',authority='server',serverTile=list(new),
                      position=[origin[0]+(new[0]-ox+.5)*scale,height,origin[2]+sign*(new[1]-oy+.5)*scale],
                      placementSource='publish_interior_staff.py',placementReason=reason)
    return result,reconciled

def validate_posts(world,portals,posts=POSTS):
    """Both directions and conversation space with all six final bodies present."""
    audit=WalkAudit(world,portals);actors={}
    original={}
    for name,region,old,new,_,_ in posts:
        matches=[n for n,r,*_ in world.npcs.values() if n.name==name and r==region]
        if len(matches)!=1:raise ValueError(f'{name}: missing actual runtime NPC')
        npc=matches[0];actors[name]=npc;original[name]=(npc.x,npc.y)
        npc.x,npc.y=new
    try:
        results=[]
        for name,region,old,new,_,_ in posts:
            occupied=world.blocking_tiles(region)
            other={p for p in occupied if p!=new}
            if not world.is_walkable(region,*new) or any((n.x,n.y)==new and n is not actors[name]
                for n,r,*_ in world.npcs.values() if r==region):raise ValueError(f'{name}: blocked/occupied authored post')
            entries={(p.destination_x,p.destination_y) for p in portals if p.destination==region}
            entries.add(old)  # This literal published arrival was the defect.
            room=None
            for entry in sorted(entries):
                if audit.arrival_departure(region,entry) is None:raise ValueError(f'{region}: occupied/blocked arrival {entry}')
                f=AccessFlood(world,region,entry,occupied=occupied,terminals=audit.automatic[region],arrival_departure=True)
                if f.near(new,4) is not None:
                    neighbors=[p for p in ((new[0]-1,new[1]),(new[0]+1,new[1]),(new[0],new[1]-1),(new[0],new[1]+1)) if f.reachable(p)]
                    if len(neighbors)<3:raise ValueError(f'{name}: conversation space narrowed')
                    exits=[(p.x,p.y) for p in portals if p.source==region and 0<=p.x<f.width and 0<=p.y<f.height and f.steps[p.y*f.width+p.x]>=0]
                    if not exits:raise ValueError(f'{name}: no reachable room exit')
                    proofs=[]
                    for point in neighbors:
                        out=world.find_path(region,entry,point,occupied)
                        back=world.find_path(region,point,entry,occupied)
                        if (not out or out[-1]!=point or not back or back[-1]!=entry or
                            set(out)&audit.automatic[region] or set(back[:-1])&audit.automatic[region]):continue
                        proofs.append({'neighbor':list(point),'outwardSteps':len(out),'returnSteps':len(back)})
                    if len(proofs)<3:raise ValueError(f'{name}: actual roundtrip/conversation path blocked')
                    room={'name':name,'map':region,'tile':list(new),'entry':list(entry),'exits':[list(p) for p in exits],'conversation':proofs}
            if room is None:raise ValueError(f'{name}: no actual incoming room connection')
            results.append(room)
        return results
    finally:
        for name,npc in actors.items():npc.x,npc.y=original[name]

def publish(server,data,client=CLIENT,*,apply=False):
    server,data,client=Path(server).resolve(),Path(data).resolve(),Path(client).resolve()
    profile=server/'config/eloria';path=profile/'npcs.txt';raw=path.read_bytes();text=raw.decode('utf-8')
    updated,changes=rewrite_roster(text)
    R=runtime(server);maps,portals=R['maps'].load_maps(profile/'maps.txt')
    world=R['world'].World.__new__(R['world'].World);world.maps=maps
    world.settings=R['settings'].load_settings(str(profile/'server.txt'))
    selected={p[1] for p in POSTS}
    world.collision_maps=R['collision'].load_collision_maps(str(data),{k:v for k,v in maps.items() if k in selected},world.settings.max_walk_height_change)
    services=R['interactives'].load_interactives(profile/'interactives.txt')
    for region,c in world.collision_maps.items():world.collision_maps[region]=R['collision'].with_storage_collision(c,((i.x,i.y) for i in services.values() if i.map_id==region and i.role=='storage'))
    world.sessions=[];world.animals={};world.animals_by_map={};world.npcs={};world.npc_roles={};world.npc_dialogues={};world._footprint_collision={}
    world.load_configured_npcs(str(path));proof=validate_posts(world,portals)
    exterior=['amberwood','grey_moors','manymouth_delta','mirrorhold','amethyst_barrens']
    members=family(client,server,exterior);pending={path:updated.encode('utf-8')};package_changes=[]
    for region in sorted(selected):
        mpath=members[region]['path'];m=json.loads(mpath.read_text(encoding='utf-8'))
        result,reconciled=marker_update(m,[p for p in POSTS if p[1]==region])
        pending[mpath]=(json.dumps(result,indent=2)+'\n').encode('utf-8')
        package_changes.append({'map':region,'path':str(mpath),'reconciledNamedMarkers':reconciled})
    inputs={str(p):digest(p) for p in pending}
    for region in selected:
        elm=data/maps[region].file
        inputs[str(elm)]=digest(elm)
    inputs[str(profile/'maps.txt')]=digest(profile/'maps.txt');inputs[str(profile/'interactives.txt')]=digest(profile/'interactives.txt')
    changed=[str(p) for p,payload in pending.items() if p.read_bytes()!=payload]
    if apply:
        if any(digest(Path(p))!=h for p,h in inputs.items()):raise ValueError('Staff publication inputs changed before apply')
        for p,payload in pending.items():
            if p.read_bytes()!=payload:p.write_bytes(payload)
    return {'passed':True,'applied':apply,'changes':changes,'changedFiles':changed,'packages':package_changes,'routeProof':proof,'inputSha256':inputs}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',required=True,type=Path);parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--client',type=Path,default=CLIENT);parser.add_argument('--apply',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();report=publish(args.server,args.data,args.client,apply=args.apply)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
