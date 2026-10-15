"""Publish authored underground packages beside the exterior partition.

Interiors have independent frames and deliberately disconnected chambers. They
never acquire ownership polygons or seamless continent links. Entrance markers
are baked from the saved exterior scenes; click portals connect each section.
"""
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import ownership

SOURCE = 'eloria-assets/maps/continent-v2/_continent_v2/content/underground.json'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attach(ctx, pub, error=ValueError):
    path=ctx.checkout/SOURCE
    if not path.is_file():
        pub.underground=None;pub.vendor_regions=pub.regions;return
    design=json.loads(path.read_text()); info=design['map']; region=info['id'];cells=info['cells']
    package=ctx.maps_root/'continent-v2'/region/'client'
    doc=json.loads((package/'world.json').read_text())
    if doc['provenance']['sourceSha256']!=digest(path) or doc['provenance']['builderSha256']!=digest(Path(__file__).with_name('build_underground.py')):
        raise error('underground source or builder changed: run build_underground.py')
    from collision_sources import read_served_package
    from eloria.collision import CollisionMap, erode_for_footprint
    blob,grid,_=read_served_package(package/'collision.bin',cells)
    collision=CollisionMap.from_grid(grid)
    walk=np.frombuffer(grid.codes,dtype=np.uint16).reshape(cells,cells)
    # Distinct entrance components are the shared-insides contract. Checking
    # reach with the actual server step rule also catches one-cell pinches.
    reaches=[]; portals=[]; nodes=[];spawns=[];objects=[];ids=set()
    used={(n['map'],n['id']) for n in pub.nodes}|{(i['map'],i['object']) for i in pub.interactives}
    for section in design['sections']:
        e=section['entrance']; exterior=e['map'];arrival=tuple(section['arrival']);exit_tile=section['exit']
        records=ctx.bakes[exterior].doc['gameplay'].get('runtimePoints',[])
        matches=[r for r in records if r['id']==e['marker']]
        if len(matches)!=1 or list(matches[0]['serverTile'])!=e['tile'] or matches[0].get('role')!='underground_entrance':
            raise error(f'{section["id"]}: saved entrance marker and underground source disagree')
        x,y=e['tile']; rx,ry=e['returnTile']
        for px,py in [(x,y),(rx,ry)]:
            cx,cz=ctx.frames[exterior].continent(px,py)
            if not ownership.contains(cx,cz,ctx.packages[exterior]['polygon']):
                raise error(f'{section["id"]}: entrance/return lies outside its territory')
            if not pub.reached[exterior][py,px]: raise error(f'{section["id"]}: entrance/return is unreachable')
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                if not ctx.packages[exterior]['grid'].walkable(px+dx,py+dy): raise error(f'{section["id"]}: entrance/return has no clear approach')
        if (exterior,e['object']) in used: raise error('underground entrance object id is already used')
        if not collision.walkable(*arrival): raise error(f'{section["id"]}: arrival blocked')
        reach={arrival};q=deque([arrival])
        while q:
            a,b=q.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                target=(a+dx,b+dy)
                if target not in reach and collision.can_step(a,b,*target,2): reach.add(target);q.append(target)
        if any(reach&other for other in reaches): raise error('underground sections connect across blackspace')
        reaches.append(reach)
        if tuple(exit_tile) not in reach: raise error(f'{section["id"]}: exit unreachable')
        portals.extend([[exterior,e['object'],x,y,region,*section['arrival']],
                        [region,e['object'],*exit_tile,exterior,rx,ry]])
        objects.extend([f'{exterior} | {e["object"]} | {x} | {y} | portal | maps.txt | Beyond it lies {section["name"]}. {section["danger"]}.',
                        f'{region} | {e["object"]} | {exit_tile[0]} | {exit_tile[1]} | portal | maps.txt | Beyond it lies {exterior.replace("_"," ").title()}.'])
        for oid,res,nx,ny in section['nodes']:
            if oid in ids or oid in [s['entrance']['object'] for s in design['sections']]: raise error('duplicate underground object id')
            ids.add(oid)
            if res not in ctx.server.base_resources: raise error(f'unknown underground resource {res}')
            if walk[ny,nx] or not any((nx+dx,ny+dy) in reach for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                raise error(f'{section["id"]}: node {oid} has no harvest approach or its body is open')
            nodes.append(f'node | {region} | {oid} | {nx} | {ny} | {res}')
        for creature,sx,sy,leash in section['spawns']:
            definition=ctx.server.creatures.get(creature)
            if definition is None or definition.raw.get('model')!='final': raise error(f'{creature}: no reviewed model')
            fitted=erode_for_footprint(collision,definition.footprint)
            if not fitted.walkable(sx,sy) or (sx,sy) not in reach: raise error(f'{creature}: footprint does not fit')
            if not 1<=leash<=8 or max(abs(sx-arrival[0]),abs(sy-arrival[1]))<leash+20:
                raise error(f'{creature}: encounter too close to the safe entry chamber')
            spawns.append(f'spawn | {region} | {creature} | {sx} | {sy} | leash:{leash}')
    covered=set().union(*reaches)
    if len(covered)!=int(np.count_nonzero(walk)): raise error('underground has a stranded walkable pocket')
    metadata={'name':info['name'],'alias':info['alias'],'serverOrigin':[0,cells],'serverCells':[cells,cells],
              'arrival':design['sections'][0]['arrival'],'servedGridSha256':digest(package/'served-grid.escg.gz'),
              'collisionSha256':digest(package/'collision.bin'),'sourceSha256':digest(path),
              'manifestSha256':digest(package/'world.json'),'sections':[{k:s[k] for k in ('id','name','danger','arrival','exit')} for s in design['sections']]}
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
