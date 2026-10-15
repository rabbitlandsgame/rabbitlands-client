"""Read back emitted continent geometry, ownership and published road lanes.

No builder functions are used. A complete audit requires the final manifests,
GLBs and served ELMs; --regions permits clearly labelled provisional subsets.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import continent_approaches as APPROACH
from legacy_content import read_base_only

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maps/nymara-regions/_toolkit'))
import glb_reader as GLB
from verify_runtime import VerticalRayIndex


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contains(points, polygon):
    """Independent ray-crossing membership, including the polygon boundary."""
    points=np.asarray(points,float).reshape(-1,2);poly=np.asarray(polygon,float)
    inside=np.zeros(len(points),bool);edge=inside.copy()
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        vector=b-a;relative=points-a
        cross=relative[:,0]*vector[1]-relative[:,1]*vector[0]
        dot=relative@vector
        edge|=(abs(cross)<1e-7)&(dot>=-1e-7)&(dot<=vector@vector+1e-7)
        if abs(vector[1])>1e-12:
            inside^=((a[1]>points[:,1])!=(b[1]>points[:,1]))&(
                points[:,0]<a[0]+(points[:,1]-a[1])*vector[0]/vector[1])
    return inside|edge


def ownership_rectangles(polygon):
    """Disjoint vertical slabs of an orthogonal polygon, independently derived."""
    polygon=np.asarray(polygon,float);rectangles=[];xs=sorted(set(polygon[:,0]))
    for left,right in zip(xs,xs[1:]):
        centre=(left+right)/2;crossings=[]
        for a,b in zip(polygon,np.roll(polygon,-1,axis=0)):
            if min(a[0],b[0])<centre<max(a[0],b[0]):
                crossings.append(float(a[1]+(centre-a[0])*(b[1]-a[1])/(b[0]-a[0])))
        crossings.sort()
        if len(crossings)%2:raise ValueError('Unclosed orthogonal ownership polygon')
        rectangles.extend((left,low,right,high) for low,high in zip(crossings[::2],crossings[1::2]))
    return np.asarray(rectangles,float).reshape(-1,4)


def clipped_area(points, rectangle):
    """Exact Sutherland–Hodgman projected area, not a centroid approximation."""
    polygon=[np.asarray(p,float) for p in points]
    for axis,limit,greater in ((0,rectangle[0],True),(0,rectangle[2],False),
                               (1,rectangle[1],True),(1,rectangle[3],False)):
        output=[]
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            ai=a[axis]>=limit if greater else a[axis]<=limit
            bi=b[axis]>=limit if greater else b[axis]<=limit
            if ai:output.append(a)
            if ai!=bi:
                t=(limit-a[axis])/(b[axis]-a[axis]);output.append(a+t*(b-a))
        polygon=output
        if not polygon:return 0.
    p=np.asarray(polygon)
    return float(abs(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1)))/2)


def projected_outside(triangles, rectangles, tolerance=1e-7):
    points=np.asarray(triangles,float)[:,:,[0,2]]
    cross=(points[:,1,0]-points[:,0,0])*(points[:,2,1]-points[:,0,1])-(points[:,1,1]-points[:,0,1])*(points[:,2,0]-points[:,0,0])
    areas=abs(cross)/2;low=points.min(axis=1);high=points.max(axis=1)
    settled=areas<tolerance
    for x0,z0,x1,z1 in rectangles:
        settled|=(low[:,0]>=x0-1e-7)&(low[:,1]>=z0-1e-7)&(high[:,0]<=x1+1e-7)&(high[:,1]<=z1+1e-7)
    outside=0.;count=0;examples=[]
    for i in np.flatnonzero(~settled):
        matches=rectangles[(rectangles[:,0]<=high[i,0])&(rectangles[:,2]>=low[i,0])&
                           (rectangles[:,1]<=high[i,1])&(rectangles[:,3]>=low[i,1])]
        remaining=max(0.,float(areas[i])-sum(clipped_area(points[i],r) for r in matches))
        if remaining>tolerance:
            outside+=remaining;count+=1
            if len(examples)<8:examples.append({'triangle':int(i),'outsideArea':remaining,'xz':points[i].tolist()})
    return {'outsideProjectedArea':outside,'outsideTriangles':count,'examples':examples}


def overlap_area(left, right):
    total=0.
    for x0,z0,x1,z1 in left:
        width=np.maximum(0.,np.minimum(x1,right[:,2])-np.maximum(x0,right[:,0]))
        height=np.maximum(0.,np.minimum(z1,right[:,3])-np.maximum(z0,right[:,1]))
        total+=float(np.sum(width*height))
    return total


def ancestry(document):
    _,parents=GLB.hierarchy(document);result={}
    for index,node in enumerate(document['nodes']):
        names=[];at=index
        while True:
            names.append(document['nodes'][at].get('name',''))
            if at not in parents:break
            at=parents[at]
        result[index]=names
    return result


def is_paint(names):
    return any('_ContinentBlend_' in n or '_StreamCollar_' in n for n in names)


def owned_surface(names):
    """Include causeway parapets in the terrain bucket, but not whole props."""
    return (any(n in ('Group_Terrain','Group_Water') or n.startswith(('Terrain_','Walk_','Water_')) for n in names)
            and not is_paint(names) and not any('_StreamThreshold_' in n for n in names))


def load_static_world(server, maps_directory, names):
    """Use production movement and furniture footprints, without running actors."""
    sys.path.insert(0,str(server))
    from eloria.world import World
    from eloria.maps import load_maps
    from eloria.npcs import load_npcs
    from eloria.interactives import load_interactives
    from eloria.settings import load_settings
    from eloria.collision import load_elm_collision,with_step_mask,with_storage_collision
    profile=server/'config/eloria';maps,_=load_maps(profile/'maps.txt')
    world=World.__new__(World);world.settings=load_settings(profile/'server.txt')
    world.sessions=[];world.animals={};world.animals_by_map={}
    world.collision_maps={};world._footprint_collision={}
    world.npcs={i:(npc,npc.map_id,None,None) for i,npc in enumerate(load_npcs(profile/'npcs.txt'))}
    objects=load_interactives(profile/'interactives.txt')
    for name in names:
        raw=with_step_mask(load_elm_collision(maps_directory/maps[name].file),world.settings.max_walk_height_change)
        world.collision_maps[name]=with_storage_collision(raw,((o.x,o.y) for o in objects.values()
            if o.map_id==name and o.role=='storage'))
    return world


def static_step(world, region, start, end, occupied):
    return (start not in occupied and end not in occupied
            and world.can_walk_step(region,start,end) and world.can_walk_step(region,end,start))


def certificate_mismatches(client, manifest, inputs):
    expected=manifest.get('authoredGeometry',{}).get('inputs',{})
    if not expected:return [{'source':None,'reason':'Missing completed authored-geometry certificate'}]
    mismatches=[]
    for relative,sha in expected.items():
        path=(client/relative).resolve()
        if not path.is_relative_to(client.resolve()):
            mismatches.append({'source':relative,'reason':'Certificate path escapes client'});continue
        if str(path) not in inputs:inputs[str(path)]=digest(path) if path.is_file() else None
        if inputs[str(path)]!=sha:mismatches.append({'source':relative,'expected':sha,'actual':inputs[str(path)]})
    return mismatches


def tile_local(tile, manifest):
    ox,oz=manifest['coordinateTransform']['serverOrigin']
    metres=manifest['coordinateTransform'].get('metresPerTile',1)
    return np.array([(tile[0]+.5-ox)*metres,(oz-tile[1]-.5)*metres])


def parse_portals(path):
    """Read automatic crossings; an object action cannot prove a land handoff."""
    result={}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        parts=[p.strip() for p in line.split('#',1)[0].split('|')]
        if parts[0]!='portal':continue
        if len(parts)==8:
            # Same valid schema as eloria.maps.load_maps: the third field is
            # an object ID, so all subsequent source/destination fields shift.
            # Validate it, but do not let an object-only entrance satisfy an
            # automatic crossing lookup (or conflict with one at the same tile).
            for index in (2,3,4,6,7):int(parts[index])
            continue
        if len(parts)!=7:raise ValueError('Invalid portal field count: '+str(len(parts)))
        key=(parts[1],int(parts[2]),int(parts[3]),parts[4])
        arrival=(int(parts[5]),int(parts[6]))
        if key in result and result[key]!=arrival:
            raise ValueError('Conflicting portal '+str(key))
        result[key]=arrival
    return result


def missing_stream_members(manifest, document):
    """Declared main-scene members must survive the final authored export."""
    names = {node.get('name') for node in document['nodes']}
    return {frame['id']: missing for frame in manifest.get('streamingBorders', [])
            if (missing := [name for name in frame.get('sceneNodes', []) if name not in names])}


def run(client, report_path, server=None, maps=None, selected=None):
    if server is not None:
        # The audit is of the legacy continent: base content tables only, no continent-v2 overlay (serve plan CV13).
        read_base_only(server)
    started=time.time();base=client/'eloria-assets/maps/nymara-regions';plan_path=base/'continent-geography.json'
    plan=json.loads(plan_path.read_text(encoding='utf-8'));regions=plan['regions']
    if plan.get('geometryMode') == 'continent-chunks-v1':
        if selected:
            raise ValueError('Shared-continent ownership must be audited as a whole; --regions is legacy-only')
        sys.path.insert(0,str(base/'_continent'))
        import audit_continent
        return audit_continent.run(client,base/'_continent/generated',report_path,
                                   Path(server).resolve() if server else None,require_collision=True)
    names=list(regions) if not selected else list(selected)
    packages={n:(client/'eloria-assets/maps/four-gates' if n=='four_gates' else base/n) for n in regions}
    manifests={n:json.loads((packages[n]/'world.json').read_text(encoding='utf-8')) for n in regions}
    auditor = Path(__file__).resolve()
    approach_reader=Path(APPROACH.__file__).resolve()
    inputs={str(plan_path):digest(plan_path), str(auditor):digest(auditor),
            str(approach_reader):digest(approach_reader)}
    for n in names:
        for filename in ('world.glb','world.json','collision.bin'):
            path=packages[n]/filename;inputs[str(path)]=digest(path)
    queries=defaultdict(list);shared=[];roads=[];shoulders=[];lanes=[]
    def query(region,xz,kind='ground'):
        entry={'region':region,'globalXZ':list(map(float,xz)),'kind':kind,'height':None}
        queries[region].append(entry);return entry
    for segment in plan['boundaryHeightField']['segments']:
        a,b=np.asarray(segment['start']),np.asarray(segment['end'])
        for amount in (.1,.5,.9):
            point=a*(1-amount)+b*amount
            expected=float(np.interp(amount,[0,1],segment['heights']))
            samples=[query(n,point) for n in segment['regions']]
            for sample in samples:sample['expected']=expected
            shared.append({'pair':segment['regions'],'globalXZ':point.tolist(),
                'expected':expected,'samples':samples})
    for connection in plan['connections']:
        a=np.asarray(connection['globalAnchor']);forward=np.asarray(connection['normal']);side=np.array([-forward[1],forward[0]])
        for end in connection['ends']:
            out=np.array(end['outward']);across=np.array([-out[1],out[0]])
            frame=next(f for f in manifests[end['region']]['streamingBorders'] if f['id']==connection['id'])
            if frame.get('approachCenterline'):
                translation=np.array(regions[end['region']]['translation'])[[0,2]]
                for lane in range(-3,4):
                    for depth,local in APPROACH.lane_points(frame,lane,spacing=.2,outward=1.):
                        point=np.asarray(local)[[0,2]]+translation
                        roads.append({'id':connection['id'],'region':end['region'],'depth':depth,'lane':lane,
                                      'authoredCurve':True,'sample':query(end['region'],point,'navigation')})
            else:
                for depth in range(-42,2):
                    for lane in range(-3,4):
                        point=a[[0,2]]+out*depth+across*lane
                        roads.append({'id':connection['id'],'region':end['region'],'depth':depth,'lane':lane,
                                      'sample':query(end['region'],point,'navigation')})
        for lateral in range(-109,110):
            for depth in (-1.,1.):
                point=a[[0,2]]+side*lateral+forward*depth
                shoulders.append({'id':connection['id'],'lateral':lateral,'depth':depth,'globalXZ':point.tolist(),
                                  'owners':[],'samples':[]})
    shoulder_points=np.asarray([r['globalXZ'] for r in shoulders])
    for n,r in regions.items():
        for index in np.flatnonzero(contains(shoulder_points,r['ownershipPolygon'])):
            shoulders[index]['owners'].append(n)
            shoulders[index]['samples'].append(query(n,shoulder_points[index]))
    published=parse_portals(server/'config/eloria/maps.txt') if server else {}
    if server:inputs[str(server/'config/eloria/maps.txt')]=digest(server/'config/eloria/maps.txt')
    for connection in plan['connections']:
        for source,destination in (connection['ends'],list(reversed(connection['ends']))):
            n=source['region'];d=destination['region'];manifest=manifests[n]
            portal=next((p for p in manifest.get('portals',[]) if p.get('id')==source['portal']),None)
            if portal is None:raise ValueError(n+' missing '+source['portal'])
            tile=portal['serverTile'];out=source['outward'];side=(-out[1],-out[0])
            for lane in range(-3,4):
                start=(tile[0]+lane*side[0],tile[1]+lane*side[1]);arrival=published.get((n,*start,d))
                q=tile_local(start,manifest)+np.array(regions[n]['translation'])[[0,2]]
                entry={'id':connection['id'],'source':n,'destination':d,'lane':lane,
                    'sourceTile':start,'arrivalTile':arrival,'sourceSample':query(n,q,'navigation')}
                if arrival is not None:
                    r=tile_local(arrival,manifests[d])+np.array(regions[d]['translation'])[[0,2]]
                    entry['arrivalSample']=query(d,r,'navigation');entry['globalXZError']=float(np.linalg.norm(q-r))
                lanes.append(entry)
    world=None
    if server and maps:
        world=load_static_world(server,maps,names)
        for filename in ('server.txt','interactives.txt','npcs.txt'):
            path=server/'config/eloria'/filename;inputs[str(path)]=digest(path)
        for filename in ('world.py','collision.py','footprint.py','settings.py'):
            path=server/'eloria'/filename;inputs[str(path)]=digest(path)
        for path in sorted(maps.rglob('*.elm')):inputs[str(path)]=digest(path)
    results={};errors=[];ownership_overlaps=[];step_checks=0;step_failures=[]
    stale_certificates={n:issues for n in names if (issues:=certificate_mismatches(client,manifests[n],inputs))}
    if stale_certificates:errors.append('Emitted packages do not match their current authored input certificates')
    rectangles={n:ownership_rectangles(r['ownershipPolygon']) for n,r in regions.items()}
    for i,name in enumerate(names):
        for other in names[i+1:]:
            area=overlap_area(rectangles[name],rectangles[other])
            if area>1e-7:ownership_overlaps.append({'regions':[name,other],'projectedArea':area})
    if ownership_overlaps:errors.append('Owned polygons overlap')
    for name in names:
        package=packages[name];manifest=manifests[name];record=regions[name];translation=np.array(record['translation'])
        document,body=GLB.load(package/'world.glb');ancestors=ancestry(document)
        missing_members = missing_stream_members(manifest, document)
        if missing_members:errors.append(name+' declares absent main-scene streaming members')
        mesh_nodes=[i for i,node in enumerate(document['nodes']) if 'mesh' in node]
        ground_nodes=[i for i in mesh_nodes if any(n.startswith('Terrain_') for n in ancestors[i]) and not is_paint(ancestors[i])]
        nav_nodes=[i for i in mesh_nodes if any(n.startswith(('Terrain_','Walk_')) for n in ancestors[i]) and not is_paint(ancestors[i])]
        outside_nodes=[i for i in mesh_nodes if owned_surface(ancestors[i])]
        bad_nodes=[n.get('name','') for n in document['nodes'] if n.get('name','').startswith(('StreamView_','Backdrop_')) or '_StreamOverflow_' in n.get('name','')]
        ground=GLB.triangles(document,body,ground_nodes);navigation=GLB.triangles(document,body,nav_nodes)
        ground_index=VerticalRayIndex(ground);nav_index=VerticalRayIndex(navigation)
        collision=world.collision_maps[name] if world else None
        occupied=world.blocking_tiles(name) if world else set()
        for entry in queries[name]:
            local=np.array(entry['globalXZ'])-translation[[0,2]]
            index=nav_index if entry['kind']=='navigation' else ground_index
            actual=index.top_hit(*local) if index.buckets else None
            entry['height']=None if actual is None else actual+float(translation[1])
            if collision and entry['kind']=='navigation':
                origin=manifest['coordinateTransform']['serverOrigin']
                tile=(int(np.floor(local[0]+origin[0])),int(np.floor(origin[1]-local[1])))
                entry['servedWalkable']=bool(collision.walkable(*tile))
                entry['servedTile']=list(tile);entry['staticOccupied']=tile in occupied
        if world:
            routes=defaultdict(list)
            for row in roads:
                if row['region']==name:routes[(row['id'],row['lane'])].append(row)
            for (road,lane),points in routes.items():
                points.sort(key=lambda row:row['depth'])
                for first,second in zip(points,points[1:]):
                    start=tuple(first['sample']['servedTile']);end=tuple(second['sample']['servedTile'])
                    if start==end:continue
                    step_checks+=1
                    if not static_step(world,name,start,end,occupied):
                        step_failures.append(dict(region=name,road=road,lane=lane,depth=first['depth'],
                            start=start,end=end,startElevation=collision.elevation(*start),endElevation=collision.elevation(*end),
                            staticOccupied=start in occupied or end in occupied))
        owned=GLB.triangles(document,body,outside_nodes)+translation
        outside=projected_outside(owned,rectangles[name])
        matrices,_=GLB.hierarchy(document);prop_roots=[]
        for i,node in enumerate(document['nodes']):
            label=node.get('name','')
            if label.startswith(('Prop_','Landmark_','Secret_')) and not is_paint(ancestors[i]):
                point=matrices[i][:3,3]+translation
                if not contains([point[[0,2]]],record['ownershipPolygon'])[0]:prop_roots.append(label)
        boundary=[q for q in queries[name] if 'expected' in q]
        boundary_misses=sum(q['height'] is None for q in boundary)
        boundary_error=max((abs(q['height']-q['expected']) for q in boundary if q['height'] is not None),default=0.)
        results[name]={'groundTriangles':len(ground),'navigationTriangles':len(navigation),
            'missingMainStreamMembers':missing_members,
            'boundaryRays':len(boundary),'boundaryMisses':boundary_misses,'boundaryMaxProfileError':boundary_error,
            'rayCount':len(queries[name]),'legacyDuplicateNodes':bad_nodes,'placedRootsOutsideOwnership':prop_roots,**outside}
        if boundary_misses or boundary_error>.003:errors.append(name+' emitted boundary/profile mismatch')
        if bad_nodes or prop_roots or outside['outsideProjectedArea']>.02:errors.append(name+' ownership/duplicate geometry violation')
        print(name,len(queries[name]),'rays','outside area',outside['outsideProjectedArea'],flush=True)
        del document,body,ground,navigation,owned,ground_index,nav_index
    selected_set=set(names);pair_summary={}
    for row in shared:
        if not set(row['pair'])<=selected_set:continue
        key=' / '.join(row['pair']);stat=pair_summary.setdefault(key,{'rays':0,'misses':0,'maxPairError':0.,'maxProfileError':0.})
        heights=[s['height'] for s in row['samples']];stat['rays']+=1
        if any(h is None for h in heights):stat['misses']+=1
        else:
            stat['maxPairError']=max(stat['maxPairError'],abs(heights[0]-heights[1]))
            stat['maxProfileError']=max(stat['maxProfileError'],max(abs(h-row['expected']) for h in heights))
    for pair,stat in pair_summary.items():
        if stat['misses'] or stat['maxPairError']>.003 or stat['maxProfileError']>.003:errors.append(pair+' shared boundary mismatch')
    for row in lanes:
        if row['source'] not in selected_set or row['destination'] not in selected_set:continue
        a=row['sourceSample']['height'];b=row.get('arrivalSample',{}).get('height')
        row['globalYError']=None if a is None or b is None else abs(a-b)
        blocked=any(s.get('servedWalkable') is False or s.get('staticOccupied') is True
                    for s in (row['sourceSample'],row.get('arrivalSample',{})))
        if server and (row['arrivalTile'] is None or row.get('globalXZError',1)>.00001 or row['globalYError'] is None or row['globalYError']>.05 or blocked):
            errors.append(row['id']+' published lane '+str(row['lane'])+' position/support mismatch')
    missing_roads=[r for r in roads if r['region'] in selected_set and (r['sample']['height'] is None or r['sample'].get('servedWalkable') is False)]
    missing_shoulders=[r for r in shoulders if r['owners'] and set(r['owners'])<=selected_set and all(s['height'] is None for s in r['samples'])]
    if missing_roads:errors.append(str(len(missing_roads))+' unsupported or blocked seven-lane road probes')
    if step_failures:errors.append(str(len(step_failures))+' road steps rejected by production movement/furniture/NPC rules')
    if missing_shoulders:errors.append(str(len(missing_shoulders))+' missing owned shoulder probes')
    unchanged=all((digest(path) if Path(path).is_file() else None)==sha for path,sha in inputs.items())
    if not unchanged:errors.append('Inputs changed during audit')
    complete=selected_set==set(regions) and server is not None and maps is not None
    report={'complete':complete,'passed':not errors,'elapsedSeconds':time.time()-started,
        'inputs':inputs,'unchangedDuringAudit':unchanged,'sourceCertificateMismatches':stale_certificates,
        'regions':results,'physicalPairs':pair_summary,
        'ownershipOverlaps':ownership_overlaps,
        'roadCount':len(plan['connections']),'roadLaneQueries':len(roads),'roadFailures':missing_roads,
        'productionRoadStepChecks':step_checks,'productionRoadStepFailures':step_failures,
        'publishedLanes':lanes,'nearBorderQueries':len(shoulders),'nearBorderFailures':missing_shoulders,
        'unownedNearBorderQueries':[r for r in shoulders if not r['owners']],
        'sharedBoundaryFailures':[r for r in shared if set(r['pair'])<=selected_set and
            (any(s['height'] is None for s in r['samples']) or max(abs(s['height']-r['expected']) for s in r['samples'])>.003)],
        'limitations':['Whole placed canopies may overhang their owned root; their geometry is kept once.',
            'Production World.can_walk_step is checked in both directions, with configured NPCs and storage footprints; moving actor occupancy and frame timing need live tests.',
            'Published handoff XYZ uses actual actor tile centres and emitted navigation heights; Y tolerance0.05m includes deck paint offsets.'],
        'errors':errors}
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--client',type=Path,required=True)
    parser.add_argument('--server',type=Path);parser.add_argument('--maps',type=Path)
    parser.add_argument('--regions',nargs='+');parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();result=run(args.client.resolve(),args.report.resolve(),args.server,args.maps,args.regions)
    print(json.dumps({k:result[k] for k in ('complete','passed','elapsedSeconds','errors')},indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
