"""Publish authored underground packages beside the exterior partition.

Interiors have independent frames and deliberately disconnected chambers. They
never acquire ownership polygons or seamless continent links. Entrance markers
are baked from the saved exterior scenes; click portals connect each section.

The rules (pass 2, 2026-10-21: several doors per section, passages between
sections; underground_source.py reads both forms of the source):
  * every door: its marker is in its exterior map's bake as an underground_entrance
    runtime point on the door's tile; the entrance and return tiles lie in the
    map's territory, on server-reached ground, with four walkable neighbours; its
    object id is used nowhere else; its arrival is walkable and its exit reached;
  * every passage end: its tile and its arrival are reached inside its own section;
    its object id (one per end) is used nowhere else;
  * a section's floor is one walk component from its primary arrival; sections
    never connect; nothing walkable is stranded;
  * nodes: the tile is blocked, a 4-neighbour is reached, the resource exists;
  * encounters: a reviewed model, the footprint fits, leash 1-8 and leash + 20
    tiles from every arrival of the section (doors' and passage ends').
Rows: a portal pair and an interactive per door end, a same-map portal and an
interactive ("A way leads on into <section>. <danger>.") per passage end.
"""
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import ownership
import underground_source as S

SOURCE = 'eloria-assets/maps/continent-v2/_continent_v2/content/underground.json'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attach(ctx, pub, error=ValueError):
    path=ctx.checkout/SOURCE
    if not path.is_file():
        pub.underground=None;pub.vendor_regions=pub.regions;return
    design=json.loads(path.read_text()); info=design['map']; region=info['id'];cells=info['cells']
    try:
        S.check(design)
    except S.SourceError as problem:
        raise error(f'underground source: {problem}')
    package=ctx.maps_root/'continent-v2'/region/'client'
    doc=json.loads((package/'world.json').read_text())
    if doc['provenance']['sourceSha256']!=digest(path) or doc['provenance']['builderSha256']!=digest(Path(__file__).with_name('build_underground.py')):
        raise error('underground source or builder changed: run build_underground.py')
    from collision_sources import read_served_package
    from eloria.collision import CollisionMap, erode_for_footprint
    blob,grid,_=read_served_package(package/'collision.bin',cells)
    collision=CollisionMap.from_grid(grid)
    walk_codes=np.frombuffer(grid.codes,dtype=np.uint16).reshape(cells,cells)
    # Distinct entrance components are the shared-insides contract. Checking
    # reach with the actual server step rule also catches one-cell pinches.
    reaches=[]; portals=[]; nodes=[];spawns=[];objects=[];ids=set()
    used={(n['map'],n['id']) for n in pub.nodes}|{(i['map'],i['object']) for i in pub.interactives}
    reach_of={}
    def walk(start):
        reach={start};q=deque([start])
        while q:
            a,b=q.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                target=(a+dx,b+dy)
                if target not in reach and collision.can_step(a,b,*target,2): reach.add(target);q.append(target)
        return reach
    for section in design['sections']:
        sid=section['id']; arrival=tuple(S.primary_arrival(design,section))
        if not collision.walkable(*arrival): raise error(f'{sid}: arrival blocked')
        reach=walk(arrival)
        if any(reach&other for other in reaches): raise error('underground sections connect across blackspace')
        reaches.append(reach); reach_of[sid]=reach
        for door in S.doors(section):
            e=door; exterior=e['map']; tag=f'{sid} door {door["index"]}'
            records=ctx.bakes[exterior].doc['gameplay'].get('runtimePoints',[])
            matches=[r for r in records if r['id']==e['marker']]
            if len(matches)!=1 or list(matches[0]['serverTile'])!=e['tile'] or matches[0].get('role')!='underground_entrance':
                raise error(f'{tag}: saved entrance marker and underground source disagree')
            x,y=e['tile']; rx,ry=e['returnTile']
            for px,py in [(x,y),(rx,ry)]:
                cx,cz=ctx.frames[exterior].continent(px,py)
                if not ownership.contains(cx,cz,ctx.packages[exterior]['polygon']):
                    raise error(f'{tag}: entrance/return lies outside its territory')
                if not pub.reached[exterior][py,px]: raise error(f'{tag}: entrance/return is unreachable')
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    if not ctx.packages[exterior]['grid'].walkable(px+dx,py+dy): raise error(f'{tag}: entrance/return has no clear approach')
            if (exterior,e['object']) in used: raise error('underground entrance object id is already used')
            if not collision.walkable(*door['arrival']) or tuple(door['arrival']) not in reach:
                raise error(f'{tag}: arrival blocked or not on the section\'s floor')
            if tuple(door['exit']) not in reach: raise error(f'{tag}: exit unreachable')
            portals.extend([[exterior,e['object'],x,y,region,*door['arrival']],
                            [region,e['object'],*door['exit'],exterior,rx,ry]])
            objects.extend([f'{exterior} | {e["object"]} | {x} | {y} | portal | maps.txt | Beyond it lies {section["name"]}. {section["danger"]}.',
                            f'{region} | {e["object"]} | {door["exit"][0]} | {door["exit"][1]} | portal | maps.txt | Beyond it lies {exterior.replace("_"," ").title()}.'])
    sections={s['id']:s for s in design['sections']}
    for passage in S.passages(design):
        for end in passage['ends']:
            other=passage['ends'][1-end['end']]; tag=f'passage {passage["index"]} end {end["end"]} ({end["section"]})'
            reach=reach_of[end['section']]
            if tuple(end['tile']) not in reach: raise error(f'{tag}: its tile {end["tile"]} is not reached inside its section')
            if not collision.walkable(*end['arrival']) or tuple(end['arrival']) not in reach:
                raise error(f'{tag}: its arrival {end["arrival"]} is not reached inside its section')
            if (region,end['object']) in used: raise error(f'{tag}: object id {end["object"]} is already used')
            target=sections[other['section']]
            portals.append([region,end['object'],*end['tile'],region,*other['arrival']])
            objects.append(f'{region} | {end["object"]} | {end["tile"][0]} | {end["tile"][1]} | portal | maps.txt | '
                           f'A way leads on into {target["name"]}. {target["danger"]}.')
    for section in design['sections']:
        sid=section['id']; reach=reach_of[sid]
        safe=[tuple(a) for _,_,a in S.arrivals(design,section)]
        for oid,res,nx,ny in section['nodes']:
            if oid in ids: raise error('duplicate underground object id')
            ids.add(oid)
            if res not in ctx.server.base_resources: raise error(f'unknown underground resource {res}')
            if walk_codes[ny,nx] or not any((nx+dx,ny+dy) in reach for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                raise error(f'{sid}: node {oid} has no harvest approach or its body is open')
            nodes.append(f'node | {region} | {oid} | {nx} | {ny} | {res}')
        for creature,sx,sy,leash in section['spawns']:
            definition=ctx.server.creatures.get(creature)
            if definition is None or definition.raw.get('model')!='final': raise error(f'{creature}: no reviewed model')
            fitted=erode_for_footprint(collision,definition.footprint)
            if not fitted.walkable(sx,sy) or (sx,sy) not in reach: raise error(f'{creature}: footprint does not fit')
            if not 1<=leash<=8 or any(max(abs(sx-ax),abs(sy-ay))<leash+20 for ax,ay in safe):
                raise error(f'{creature}: encounter too close to a safe entry (an arrival)')
            spawns.append(f'spawn | {region} | {creature} | {sx} | {sy} | leash:{leash}')
    covered=set().union(*reaches)
    if len(covered)!=int(np.count_nonzero(walk_codes)): raise error('underground has a stranded walkable pocket')
    def summary(s):
        # the old keys, then (pass 2) every way in: doors [object, map, arrival, exit], passage ends [object, arrival]
        return {'id':s['id'],'name':s['name'],'danger':s['danger'],'arrival':S.primary_arrival(design,s),
                'exit':S.primary_exit(design,s),
                **({'doors':[[d['object'],d['map'],d['arrival'],d['exit']] for d in S.doors(s)]} if 'entrances' in s else {}),
                **({'passageEnds':[[e['object'],e['arrival'],e['tile']] for e in S.passage_ends(design,s['id'])]}
                   if S.passage_ends(design,s['id']) else {})}
    metadata={'name':info['name'],'alias':info['alias'],'serverOrigin':[0,cells],'serverCells':[cells,cells],
              'arrival':S.primary_arrival(design,design['sections'][0]),'servedGridSha256':digest(package/'served-grid.escg.gz'),
              'collisionSha256':digest(package/'collision.bin'),'sourceSha256':digest(path),
              'manifestSha256':digest(package/'world.json'),'sections':[summary(s) for s in design['sections']]}
    ctx.packages[region]={'manifest':doc,'servedBytes':blob,'servedGridSha256':metadata['servedGridSha256'],
                          'collisionSha256':metadata['collisionSha256']}
    pub.underground=SimpleNamespace(region=region,metadata=metadata,portals=portals,design=design,
                                    rows={'nodes':len(nodes),'spawns':len(spawns),'interactives':len(objects)},walkable=len(covered))
    pub.vendor_regions=[*pub.regions,region]
    def append(name,lines):
        pub.files[name]+=('\r\n# Landfall underground: authored shared interiors.\r\n'+'\r\n'.join(lines)+'\r\n').encode()
    append('maps.txt',[f'map | {region} | {info["name"]} | maps/nymara/{region}.elm | {info["alias"]}',
                       *['portal | '+' | '.join(map(str,p)) for p in portals]])
    append('spawns.txt',spawns);append('harvesting.txt',nodes);append('interactives.txt',objects)


def manifest_entries(pub):
    u=getattr(pub,'underground',None)
    if u is None:return []
    m=u.metadata;cells=m['serverCells'][0]
    return [{'id':u.region,'server_cells':cells,'arrival':m['arrival'],'server_origin':m['serverOrigin'],
             'coordinateTransform':{'metresPerTile':1.,'serverOrigin':m['serverOrigin'],'serverCells':m['serverCells'],
                                    'origin':[0,0,0],'walkingHeight':0.,'invertServerY':True,'serverStorageVersion':1,'serverTileMin':[0,0]},
             'serverCells':m['serverCells'],'serverStorageVersion':1,'serverTileMin':[0,0],'portals':[]}]
