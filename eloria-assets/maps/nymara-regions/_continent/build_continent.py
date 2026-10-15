"""Compose one complete continent, then export named territories and 96m cells.

Run regional content extraction first with build_library.py. All terrain,
water, roads and ecology are authored in the global world before partitioning.
The complete GLB is a reproducible review artifact, never a client dependency.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import pickle
import re
import shutil
import sys
import time
import numpy as np
from scipy.ndimage import label, distance_transform_edt

HERE=Path(__file__).resolve().parent
REGIONS=HERE.parent
MAPS=REGIONS.parent
CLIENT=MAPS.parents[1]
sys.path.insert(0,str(HERE))
import landscape as L
import authoring as AUTHORING
from saved_seam_profile import apply_saved_seam_profile
from saved_post_support_profile import apply_post_support_seam_profile
from world_layout import World,CELL,CHUNK,ROAD_EARTHWORKS_GRADE
from content import Content,spawn_position
import scene_io as S
from terrain_export import partition_surface
from biome_blend import build_masks
from crossings import prepare_contracts,apply_manifest
from amberwood import gltf as G,mesh as M
from continent_geography import polygon_rectangles,clip_owned_mesh
from build_progress import Progress
from storage_bounds import storage_record
SHAPING_SOURCES=('landscape.py','world_layout.py','content.py','assemblies.py','crown_support.py','westhaven_support.py','ferry_export.py','ferry_support.py','mirror_support.py','manymouth_support.py','mirror_streets.py','four_gates_support.py','amberwood_support.py','amberwood_access.py','mirror_lake_support.py','ssarathi_bank_support.py','manymouth_boats.py','terrain_export.py','scene_io.py','grey_crossings.py','four_gates_sage.py','door_approaches.py','hull_settle.py','resource_trails.py','object_edits.py','winding.py','river_crossings.py','reach_links.py','authored_points.py','authoring.py','authoring_catalog.py','saved_seam_profile.py','saved-seam-grey-whitehorn-v1.json','saved_post_support_profile.py','saved-seam-post-support-v1.json','bridge_export.py','bridge_prepare.py','coastal_prepare.py','coastal_bridge_export.py','bridge_profiles.py','sea_crossings.py','coastal_bank_fit.py','../_northern/requirements.txt')
EXPORT_SOURCES=('build_continent.py','scene_io.py','terrain_export.py','biome_blend.py','compact_glb_images.py','bridge_export.py','bridge_profiles.py','sea_crossings.py','coastal_prepare.py','coastal_bridge_export.py','coastal_bank_fit.py','../_northern/requirements.txt','ferry_export.py','crossings.py','amberwood_access.py','manymouth_access.py','manymouth_village_streets.py','collision_export.py','mirror_access_geometry.py','grey_crossings.py','access_decks.py')
SHAPING_SOURCES+=('storage_bounds.py',)
EXPORT_SOURCES+=('storage_bounds.py',)


EMPTY_SHA256=hashlib.sha256(b'').hexdigest()


def object_edits_digest():
    # An absent continent-edits.json is the empty edit set, as for every earlier composition.
    path=HERE/'continent-edits.json'
    return digest(path) if path.exists() else EMPTY_SHA256
# Reporting only: the command line attaches this to the output directory.
PROGRESS=Progress(None)


def package(region):return MAPS/'four-gates' if region=='four_gates' else REGIONS/region

def json_write(path,data):
    def clean(value):
        if isinstance(value,np.ndarray):return value.tolist()
        if isinstance(value,np.generic):return value.item()
        if isinstance(value,set):return sorted(value)
        raise TypeError(type(value).__name__)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(data,indent=2,default=clean,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_key(path):return Path(path).resolve().relative_to(CLIENT.resolve()).as_posix()

def shaping_source_keys():return frozenset(source_key(HERE/name) for name in SHAPING_SOURCES)

def composition_certificate_paths():
    """Record every shaping input, including fixed data sidecars, with the composition."""
    from ownership_contract import source_dependencies
    return (tuple(HERE.glob('*.py'))+
            tuple(HERE/name for name in SHAPING_SOURCES if name.endswith('.json'))+
            tuple(source_dependencies(L.load_plan()))+
            (HERE/'../_northern/requirements.txt',))

def geometry_dependencies():
    import shapely
    return {'shapely':shapely.__version__,'geos':shapely.geos_version_string}


def composition_algorithm_sha():
    """Digest of the composition algorithm recorded in composition.json."""
    return hashlib.sha256((inspect.getsource(prepare)+inspect.getsource(ferry_landing)).encode()).hexdigest()


def ferry_landing(world,region,toward):
    index=world.ids.index(region);center=world.hub(region)
    inside=np.pad(world.owner==index,((0,1),(0,1)),mode='edge')
    sea_labels,_=label(world.water['sea_mask'],structure=np.ones((3,3)))
    ocean_ids=np.unique(np.r_[sea_labels[0],sea_labels[-1],sea_labels[:,0],sea_labels[:,-1]])
    ocean=np.isin(sea_labels,ocean_ids[ocean_ids>0])
    shore_distance=distance_transform_edt(~ocean)*CELL
    excluded=getattr(world,'ferry_exclusion',np.zeros_like(world.obstacles))
    coast=(world.height>.6)&(world.height<3.5)&(shore_distance<=12)&inside&~world.obstacles&~excluded
    for quay in world.quay_contacts:
        coast&=np.hypot(world.gx-quay['center'][0],world.gz-quay['center'][1])>=20.
    z,x=np.nonzero(coast)
    if not len(x):raise ValueError(f'{region}: no coast for ferry landing')
    points=np.c_[world.x[x],world.z[z]]
    score=np.linalg.norm(points-center,axis=1)+.28*np.linalg.norm(points-np.array(toward),axis=1)
    from ferry_export import fit_landing
    from ferry_support import restore_selected_shores
    attempted=[];errors=[];original_height=world.height;contact_count=len(world.quay_contacts)
    for candidate in np.argsort(score,kind='stable'):
        point=points[candidate]
        if any(np.linalg.norm(point-prior)<6 for prior in attempted):continue
        attempted.append(point)
        world.height=original_height.copy()
        try:
            world.prepare_quay_court(point)
            restore_selected_shores(world)
            fit=fit_landing(world,point,region)
            if not hasattr(world,'ferry_selection'):world.ferry_selection=[]
            world.ferry_selection.append({'region':region,'position':point.tolist(),'candidatesTried':len(attempted),
                'mooringDepth':fit['minimumBoatDepth'],'contactError':fit['contactError']})
            return point
        except ValueError as error:errors.append(str(error))
        finally:
            world.height=original_height
            del world.quay_contacts[contact_count:]
        if len(attempted)>=64:break
    raise ValueError(f'{region}: none of {len(attempted)} ranked shoreline sites fits an actual quay and mooring; last failures: {errors[-3:]}')


def resolve_saved_ferry_connections(world):
    """Resolve persistent saved endpoints before any procedural shore choice.

    A claimed endpoint with no surviving control is an authored deletion.  The
    complete connection is omitted before routing, so neither side can revive
    a generated quay or approach road.
    """
    import ferry_export as F
    authority=F.saved_ferry_authority(world)
    active=[];resolved={};report=[]
    for link in world.connections:
        if link['type']!='ferry':
            active.append(link);continue
        sides=[F.saved_ferry_endpoint(authority,link['id'],region)
               for region in link['regions']]
        deleted=[side for side in sides if side is not None and side['status']=='saved-deleted']
        if deleted:
            report.append({'id':link['id'],'status':'saved-deleted',
                           'regions':[side['region'] for side in deleted]})
            continue
        active.append(link);resolved[link['id']]=sides
        for side in sides:
            if side is not None:
                report.append({'id':link['id'],'region':side['region'],
                               'status':'saved-control','control':side['control']})
    world.connections=active
    world.saved_ferry_handoff=report
    return resolved


def prepare_ferry_connection(world,link,saved_sides):
    """Fit one ferry, selecting and shaping only its procedural endpoints."""
    import ferry_export as F
    from ferry_support import remember_ferry_fit,restore_selected_shores
    ends=[]
    for side,region in enumerate(link['regions']):
        saved=saved_sides[side]
        if saved is not None:
            landing=np.asarray(saved['landing'],float)[[0,2]]
            restore_selected_shores(world)
            fit=F.fit_landing(world,landing,region,
                              ignore_connection_ids=saved['connectionIds'])
            landing_error=F.validate_saved_ferry_endpoint(saved,fit)
            remember_ferry_fit(world,fit)
            next(record for record in world.saved_ferry_handoff
                 if record.get('id')==link['id'] and record.get('region')==region).update(
                     landing=landing.tolist(),landingError=landing_error,
                     contactError=fit['contactError'],maximumGrade=fit['maximumGrade'])
        else:
            other=link['regions'][1-side]
            landing=ferry_landing(world,region,world.regions[other]['center'])
            world.prepare_quay_court(landing)
            restore_selected_shores(world)
            remember_ferry_fit(world,F.fit_landing(world,landing,region))
            hub=world.hub(region)
            world.add_road(world.route(hub,landing,region=region,width=2.5,
                                      public=True,name=link['id']+'-'+region),
                           width=2.5,name=link['id']+'-'+region)
        ends.append(landing.tolist())
    link['landings']=ends


SEAM_APPROACH_DEPTHS=(4.,8.,12.)
SEAM_APPROACH_OFFSETS=(24.,-24.,32.,-32.,40.,-40.,48.,-48.,64.,-64.)
SEAM_APPROACH_CHECK_METRES=72.
SERVED_MAX_GRADE=.65


def _owned_approach(world,region,start,end):
    count=max(2,int(np.ceil(np.linalg.norm(end-start)/2.))+1)
    points=start+(end-start)*np.linspace(0.,1.,count)[:,None]
    return bool(np.all(world.owner_at(points[:,0],points[:,1])==world.ids.index(region)))


def _seam_approach_feasible(world,path,anchor,routing):
    """A saved seam keeps its exact station only when the neighbour can grade into it."""
    points,profile=world.road_profile(path)
    segment=np.linalg.norm(np.diff(points,axis=0),axis=1)
    remaining=np.r_[np.cumsum(segment[::-1])[::-1],0.]
    nearby=(remaining[:-1]<=SEAM_APPROACH_CHECK_METRES)|(remaining[1:]<=SEAM_APPROACH_CHECK_METRES)
    grade=np.abs(np.diff(profile))/np.maximum(segment,1e-9)
    if np.any(nearby&(grade>ROAD_EARTHWORKS_GRADE+1e-8)):return False
    for record in routing:
        for point in record.get('earthworks',{}).get('excessAt',()):
            if np.linalg.norm(np.asarray(point,float)-anchor)<=SEAM_APPROACH_CHECK_METRES:return False
    return True


def _reconcile_terminal_reroute(world,name,old_path,prefix,claims,routing_start,joined):
    """Atomically replace one road's claims and routing record after a terminal reroute."""
    if not isinstance(claims,tuple) or len(claims)!=5:return
    from river_crossings import on_span
    site_count,before_use,before_roads,before_routing,before_last=claims
    old_site_ids={site_id for site_id,roads in before_roads.items() if name in roads}
    prefix=np.asarray(prefix,float).reshape(-1,2)
    prefix_site_ids=set()
    for site in world.crossing_sites[:site_count]:
        if site['id'] in old_site_ids and len(prefix) and bool(on_span(
                world,prefix,pad=0.,sites=[site]).any()):
            prefix_site_ids.add(site['id'])
    new_site_ids={site_id for site_id,value in world.crossing_site_use.items()
                  if value>before_use.get(site_id,0)}
    desired=prefix_site_ids|new_site_ids

    roads={site_id:set(values) for site_id,values in before_roads.items()}
    use=dict(before_use)
    for site_id in old_site_ids:
        roads.setdefault(site_id,set()).discard(name)
        if before_use.get(site_id,0)>0:use[site_id]=before_use[site_id]-1
    for site_id in desired:
        roads.setdefault(site_id,set()).add(name)
        use[site_id]=use.get(site_id,0)+1
    key_by_id={int(site['id']):site['key'] for site in world.crossing_sites}
    retained=[];remap={}
    for site in world.crossing_sites:
        old_id=int(site['id'])
        if not roads.get(old_id):continue
        remap[old_id]=len(retained);retained.append(dict(site,id=len(retained)))
    world.crossing_sites=retained
    world.crossing_site_roads={remap[site_id]:values for site_id,values in roads.items()
                               if site_id in remap and values}
    world.crossing_site_use={remap[site_id]:value for site_id,value in use.items()
                             if site_id in remap and value>0}
    last=[]
    for record in world.river_crossings['lastResortClaims']:
        site_id=int(record['site'])
        if site_id not in remap or (record.get('road')==name and site_id not in desired):continue
        last.append({**record,'site':remap[site_id]})
    world.river_crossings['lastResortClaims']=last
    world.crossing_version=getattr(world,'crossing_version',0)+1

    old_records=[record for record in world.routing[:before_routing] if record.get('name')==name]
    new_records=list(world.routing[routing_start:])
    records=old_records+new_records
    if records:
        record=copy.deepcopy(records[0]);joined=np.asarray(joined,float)
        ordered=[]
        for item in records:
            for site_id in item.get('sites',()):
                site_id=int(site_id)
                if site_id in desired and site_id not in ordered:ordered.append(site_id)
        ordered.extend(site_id for site_id in sorted(desired) if site_id not in ordered)
        record['crossings']=[key_by_id[site_id] for site_id in ordered]
        record['sites']=[remap[site_id] for site_id in ordered]
        sampled,profile=world.road_profile(joined)
        distance=np.linalg.norm(np.diff(sampled,axis=0),axis=1)
        grade=np.abs(np.diff(profile))/np.maximum(distance,1e-9)
        record.update(start=joined[0].tolist(),goal=joined[-1].tolist(),stations=int(len(joined)),
                      maximumSlope=round(float(np.max(grade,initial=0.)),3))
        old_xz=np.asarray(old_path,float).reshape(-1,2)
        prefix_stop=max(0,len(prefix)-1);excess=[];metres=0.;passes=0
        for index,item in enumerate(records):
            earth=item.get('earthworks',{});points=list(earth.get('excessAt',()))
            if index<len(old_records) and len(old_xz):
                points=[point for point in points if int(np.argmin(
                    np.linalg.norm(old_xz-np.asarray(point,float),axis=1)))<=prefix_stop]
            excess.extend(points);passes+=int(earth.get('passes',0))
            total=len(earth.get('excessAt',()))
            if total:metres+=float(earth.get('excessMetres',0.))*len(points)/total
        record['earthworks']={'passes':passes,'excessMetres':metres,'excessAt':excess}
        record['solidFallback']=any(bool(item.get('solidFallback')) for item in records)
        record['lastResortSearch']=any(bool(item.get('lastResortSearch')) for item in records)
        other_records=[]
        for item in world.routing[:before_routing]:
            if item.get('name')==name:continue
            item=copy.deepcopy(item)
            if 'sites' in item:
                pairs=list(zip(item.get('sites',()),item.get('crossings',())))
                pairs=[(remap[int(site_id)],key) for site_id,key in pairs if int(site_id) in remap]
                item['sites']=[site_id for site_id,_ in pairs]
                item['crossings']=[key for _,key in pairs]
            other_records.append(item)
        world.routing=other_records+[record]


def route_saved_seam_neighbour(world,link,region,anchor,outward,route_in_legs,
                               snapshot_claims,restore_claims, *, start,prefix=()):
    """Replace a settled terminal prefix, adding a bounded switchback only when required."""
    hub=np.asarray(start,float);name=link['id']+'-'+region
    candidates=[(9.,())]
    tangent=np.array([-outward[1],outward[0]])
    for depth in SEAM_APPROACH_DEPTHS:
        terminal=anchor-outward*depth
        # A deeper straight terminal can be the exact established neighbour
        # corridor even when the historical 9 m handoff is infeasible.  Try
        # it before inventing a lateral switchback at the same depth.
        candidates.append((depth,()))
        for offset in SEAM_APPROACH_OFFSETS:
            waypoint=terminal+tangent*offset
            if _owned_approach(world,region,waypoint,terminal):candidates.append((depth,(waypoint,)))
    # The broad switchbacks can still descend across a sharp procedural bank
    # immediately outside a saved, level ring.  Before declaring the seam
    # infeasible, approach the nearest terminal along either short contour.
    # Keep these last so established straight and broad routes retain priority.
    terminal=anchor-outward*SEAM_APPROACH_DEPTHS[0]
    for side in (1.,-1.):
        waypoint=terminal+outward*6.+tangent*(side*6.)
        if _owned_approach(world,region,waypoint,terminal):
            candidates.append((SEAM_APPROACH_DEPTHS[0],(waypoint,)))
    failures=[]
    for depth,extra in candidates:
        terminal=anchor-outward*depth;claims=snapshot_claims(world);routing_start=len(world.routing)
        try:
            path=route_in_legs(world,[hub]+list(extra)+[terminal],region,
                own=world.solids_at_ends(hub),width=4,public=True,name=name)
            connector=np.vstack([terminal,anchor-outward*4,anchor,anchor+outward*4])
            joined=np.vstack([np.asarray(prefix,float).reshape(-1,2),path,connector[1:]])
            profiled=_seam_approach_feasible(world,joined,anchor,world.routing[routing_start:])
            # add_road densifies this route before exporting it.  The bounded
            # road profile can pass while its actual finished ground still has
            # an impassable step at one of those emitted stations.
            raw_grade=np.inf
            if profiled:
                dense,_=world.road_profile(joined)
                raw_grade=saved_seam_approach_grade(world,
                    {'points':np.c_[dense[:,0],np.zeros(len(dense)),dense[:,1]]},region,anchor)
            if profiled and raw_grade<=SERVED_MAX_GRADE+1e-8:
                old=next((np.asarray(road['points'],float)[:,[0,2]] for road in getattr(world,'roads',())
                          if road['id']==name),np.empty((0,2)))
                prefix_path=np.vstack([np.asarray(prefix,float).reshape(-1,2),hub])
                _reconcile_terminal_reroute(
                    world,name,old,prefix_path,claims,routing_start,joined)
                return joined,{'depth':depth,'waypoint':None if not extra else np.asarray(extra[0]).tolist(),
                               'attempts':len(failures)+1}
            failures.append(f'depth {depth:g}, waypoint {None if not extra else np.asarray(extra[0]).tolist()}: '
                            +('terminal earthworks cannot meet the road grade within cut/fill bounds'
                              if not profiled else f'emitted final-ground grade {raw_grade:.3f} exceeds {SERVED_MAX_GRADE:.2f}'))
        except ValueError as error:failures.append(str(error))
        restore_claims(world,claims);del world.routing[routing_start:]
    raise ValueError(f'{name}: no neighbour-owned approach can meet the saved seam: {failures[-4:]}')


def saved_seam_approach_grade(world,road,region,anchor):
    """Maximum final-terrain grade travelled along the neighbour road.

    A road following a contour may have a steep bank across its outer edge;
    that transverse slope is not the grade a walker follows into the seam.
    Exported collision and hub-to-lane contracts remain the definitive check
    that at least one lane across the road width is walkable.
    """
    points=np.asarray(road['points'],float);xz=points[:,[0,2]]
    segment=np.linalg.norm(np.diff(xz,axis=0),axis=1)
    remaining=np.r_[np.cumsum(segment[::-1])[::-1],0.]
    near=(remaining[:-1]<=SEAM_APPROACH_CHECK_METRES)|(remaining[1:]<=SEAM_APPROACH_CHECK_METRES)
    owner=world.ids.index(region)
    owned=(world.owner_at(xz[:-1,0],xz[:-1,1])==owner)|(world.owner_at(xz[1:,0],xz[1:,1])==owner)
    heights=np.asarray(world.height_at(xz[:,0],xz[:,1]),float)
    grade=np.abs(np.diff(heights))/np.maximum(segment,1e-9)
    return float(np.max(grade[near&owned],initial=0.))


def route_initial_seam_neighbour(world,link,region,anchor,outward,waypoints,route_in_legs,*,saved):
    """Preserve the established first-pass route; defer saved-terminal repair until settled."""
    hub=world.hub(region);terminal=anchor-outward*9
    legs=[hub]+list(waypoints)+[terminal]
    path=route_in_legs(world,legs,region,own=world.solids_at_ends(hub),width=4,
        public=True,name=link['id']+'-'+region)
    approach={'depth':9.,'waypoint':None,'attempts':0} if saved else None
    return np.vstack([path,anchor-outward*4,anchor,anchor+outward*4]),approach,len(legs)


def validate_saved_seam_approaches(world):
    """Reject a genuinely unwalkable saved boundary only after final terrain is installed."""
    result=[]
    for record in getattr(world,'saved_seam_approaches',()):
        link=next(value for value in world.connections if value['id']==record['id'])
        name=link['id']+'-'+record['region'];road=next(value for value in world.roads if value['id']==name)
        grade=saved_seam_approach_grade(world,road,record['region'],np.asarray(link['anchor'],float))
        result.append({'id':record['id'],'region':record['region'],'maximumGrade':grade})
        if grade>SERVED_MAX_GRADE+1e-8:
            raise ValueError(f'{name}: final saved seam neighbour approach is too steep ({grade:.3f})')
    return result


def repair_saved_seam_approaches(world,content,route_in_legs,snapshot_claims,restore_claims):
    """Reroute only a neighbour's terminal run when bounded road earthworks left it unwalkable."""
    repairs=[];replacements={}
    for record in getattr(world,'saved_seam_approaches',()):
        link=next(value for value in world.connections if value['id']==record['id'])
        region=record['region'];name=link['id']+'-'+region;road=next(value for value in world.roads if value['id']==name)
        anchor=np.asarray(link['anchor'],float);grade=saved_seam_approach_grade(world,road,region,anchor)
        if grade<=SERVED_MAX_GRADE+1e-8:continue
        points=np.asarray(road['points'],float)[:,[0,2]];distance=np.linalg.norm(np.diff(points,axis=0),axis=1)
        remaining=np.r_[np.cumsum(distance[::-1])[::-1],0.]
        candidates=np.flatnonzero(remaining>=SEAM_APPROACH_CHECK_METRES+8.)
        if not len(candidates):raise ValueError(f'{name}: infeasible saved seam approach has no neighbour-side prefix')
        split=int(candidates[-1]);outward=np.asarray(link['normal'],float)
        if link['regions'].index(region):outward=-outward
        path,approach=route_saved_seam_neighbour(world,link,region,anchor,outward,route_in_legs,
            snapshot_claims,restore_claims,start=points[split],prefix=points[:split])
        replacements[name]=path;repairs.append({'id':link['id'],'region':region,'beforeMaximumGrade':round(grade,6),**approach})
    if not repairs:return []
    world.roads=[road for road in world.roads if road['id'] not in replacements]
    world.road_distance=np.full_like(world.height,np.inf);world.road_nearest=np.full_like(world.height,np.inf);world.road_target=world.height.copy()
    for road in world.roads:AUTHORING._register_road_fields(world,road)
    for name,path in replacements.items():world.add_road(path,width=4,name=name)
    # The replacement was selected against the already-settled terrain and
    # must be walkable without another earthwork pass.  Settling the rebuilt
    # global road fields here grades every unrelated legacy route a second
    # time; that can change distant crossings even though only this saved seam
    # terminal moved.  Rebuild the query fields for the new alignment, retain
    # the finished ground, and let the final authority check below prove it.
    for repair in repairs:
        name=repair['id']+'-'+repair['region'];road=next(value for value in world.roads if value['id']==name)
        grade=saved_seam_approach_grade(world,road,repair['region'],np.asarray(next(
            link['anchor'] for link in world.connections if link['id']==repair['id']),float))
        repair['afterMaximumGrade']=round(grade,6)
        if grade>SERVED_MAX_GRADE+1e-8:raise ValueError(f'{name}: neighbour approach remains too steep after bounded reroute ({grade:.3f})')
    return repairs


def _saved_native_region(world,region,report_field=None,content=None):
    """Reserve a legacy one-region helper for an unsaved procedural region.

    This is a persistent region-authority decision, independent of which
    scene children currently survive. Deleting an imported helper must not
    cause the old native generator to recreate it on the next build.
    """
    if region not in getattr(world,'authoring_snapshots',{}):return False
    if report_field is not None:
        report={'region':region,'skipped':'saved-authoring-authority'}
        setattr(world,report_field,report)
        if content is not None:setattr(content,report_field,report)
    return True


def prepare(library,output):
    PROGRESS.start('compose',4);PROGRESS.step('loading libraries and content',0,4)
    snapshots=AUTHORING.load_snapshots();snapshots_by_region={
        snapshot.document['regionId']:snapshot for snapshot in snapshots}
    authored_regions=set(snapshots_by_region)
    plan_sha=digest(HERE/'diagonal-plan.json')
    edits_sha=object_edits_digest()
    profile_sha=digest(HERE/'legacy-server-profile/config/eloria/maps.txt')
    algorithm_sha=composition_algorithm_sha()
    dependencies=geometry_dependencies()
    certificate_paths=composition_certificate_paths()
    sources={source_key(p):digest(p) for p in certificate_paths}
    for snapshot in snapshots:sources.update(snapshot.bound_sources())
    shaping={name:digest(HERE/name) for name in SHAPING_SOURCES}
    templates=json.loads((HERE/'legacy-contracts.json').read_text())
    for region,snapshot in snapshots_by_region.items():
        templates[region]=AUTHORING.apply_gameplay(templates[region],snapshot)
    legacy=json.loads((HERE/'legacy-geography.json').read_text())
    plan=L.load_plan()
    plan=AUTHORING.apply_plans(plan,snapshots)
    started=time.monotonic();world=World(plan,
        region_contracts={region:snapshot.contract for region,snapshot in snapshots_by_region.items()},
        require_authored_storage=True)
    world.authoring_snapshots=snapshots_by_region
    world.authoring_snapshot=snapshots_by_region.get(AUTHORING.SUNMANE)
    initial_authoring_terrain={}
    for region,snapshot in snapshots_by_region.items():
        AUTHORING.verify_ownership(world,snapshot)
        initial_authoring_terrain[region]=AUTHORING.apply_terrain(world,snapshot)
    world.original_height=world.height.copy()
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    print(f'Global landform sampled in {time.monotonic()-started:.1f}s',flush=True)
    content=Content(world,library,templates,legacy);content.load()
    authoring_runtime={region:AUTHORING.apply_runtime_bindings(content,snapshot)
                       for region,snapshot in snapshots_by_region.items()}
    PROGRESS.step('roads and routing',1,4)
    from amberwood_access import prepare_amberwood_access,refresh_amberwood_access_heights
    from amberwood_support import prepare_amberwood_routes,apply_amberwood_support
    if not _saved_native_region(world,'amberwood','amberwood_access'):
        prepare_amberwood_access(world,content)
    from grey_crossings import prepare_grey_crossings,refresh_grey_crossing_heights
    if not _saved_native_region(world,'grey_moors','grey_crossings'):
        prepare_grey_crossings(world,content)
    from four_gates_sage import prepare_four_gates_sage,refresh_four_gates_sage_heights
    if not _saved_native_region(world,'four_gates','four_gates_sage'):
        prepare_four_gates_sage(world,content)
    # Records the plan relocates to reachable ground (a door on a cliff face) are pinned before any road seeks them.
    from authored_points import prepare_authored_points,refresh_authored_point_heights
    prepare_authored_points(world,content)
    from door_approaches import prepare_door_approaches,door_road_end,door_road_end_near,server_road_end,door_road_waypoints,seam_road_waypoints,route_in_legs,validate_river_setbacks,SERVER_ROAD_END_LEG_METRES
    prepare_door_approaches(world,content)
    from crown_support import apply_crown_support
    from westhaven_support import apply_westhaven_support
    from manymouth_support import apply_manymouth_support
    from mirror_streets import apply_mirror_street_footings,add_mirror_streets,apply_mirror_access
    apply_crown_support(world,content)
    if not _saved_native_region(world,'westhaven','westhaven_support',content):
        apply_westhaven_support(world,content)
    if not _saved_native_region(world,'manymouth_delta','manymouth_support',content):
        apply_manymouth_support(world,content)
    # Preserve the complete regional support union as the base, then add each
    # active saved quay under its exact (region, connection) owner. This lets a
    # saved endpoint validate against its own source geometry without hiding an
    # overlapping unrelated harbour obstacle.
    import ferry_export as FERRY
    FERRY.install_saved_ferry_exclusions(world,content)
    apply_mirror_street_footings(world,content)
    world.settle_foundations()
    from mirror_lake_support import prepare_mirror_lake_support,finish_mirror_lake_support
    prepare_mirror_lake_support(world,content)
    # Every prepare stage that moves retained content has run: the router
    # sees each structure where it finally stands.
    world.registered_obstacles=content.register_obstacles()
    # River water, its setback and the candidate bridge sites, where the ground and the solids now stand: from here
    # on a road crosses a plan river only on a site it claims (river_crossings.py).
    from river_crossings import prepare_river_crossings,dry_end,branch_start,water_distance_at,snapshot_claims,restore_claims,crossing_report
    prepare_river_crossings(world)
    # Install every complete saved network before any neighbouring route
    # is solved.  It can guide branches and seam approaches, but no retired
    # Sunmane route may claim a bridge site or alter another territory first.
    authoring_routes={region:AUTHORING.replace_routes(world,snapshot)
                      for region,snapshot in snapshots_by_region.items()}
    validate_river_setbacks(world,content)
    world.plan_connections()
    for snapshot in snapshots:AUTHORING.verify_seam_anchors(world,snapshot)
    saved_seam_ids={entry['id'] for snapshot in snapshots
                    for entry in snapshot.document['seams']['anchors']}
    add_mirror_streets(world,content)
    from ferry_support import validate_final_ferries
    saved_ferry_endpoints=resolve_saved_ferry_connections(world)
    world.unrouted=[]
    for link in world.connections:
        if link['type']=='walk':
            # The crossing's best seam station first, then its alternatives (a seam road whose hub cannot reach a
            # station without an unavailable river crossing moves the crossing along the seam instead).
            choices=[{'anchor':link['anchor'],'normal':link['normal']}]+list(link.get('alternatives',[]))
            saved_connection=link['id'] in saved_seam_ids
            if saved_connection:choices=choices[:1]
            failures=[]
            for choice in choices:
                anchor=np.array(choice['anchor'],float);normal=np.array(choice['normal'],float)
                claims=snapshot_claims(world);paths=[]
                try:
                    for side,region in enumerate(link['regions']):
                        outward=normal if side==0 else -normal
                        if region in authored_regions:
                            identity=link['id']+'-'+region
                            saved=next((road for road in world.roads if road['id']==identity),None)
                            if saved is None:raise AUTHORING.AuthoringError(f'{identity}: authored seam route is absent')
                            endpoint=np.asarray(saved['points'][-1],float)[[0,2]]
                            if np.linalg.norm(endpoint-anchor)>6.01:
                                raise AUTHORING.AuthoringError(
                                    f'{identity}: authored endpoint is not at its saved seam anchor')
                            continue
                        # A seam terminal stands on open ground by construction (the crossing
                        # choice charges terminals inside solids), so the road's own solids are
                        # the hub's only: its last stretch threads a city wall's gate instead of
                        # crossing the wall its terminal stands beside (measured at Four Gates
                        # with the terrain terms on: 31 m through City_Wall_44 and _45, and the
                        # seam's crossing and return records unreachable).
                        # An authored pass is routed hub -> waypoint -> ... -> terminal in legs
                        # (as a designed climb to a door is), so a mountain crossing takes the
                        # switchback its valley suggests instead of the router's shortest line;
                        # the hub's own solids stay on the first leg, where the hub stands.
                        # Preserve the established hub route on its first pass.
                        # Saved seams are marked for the post-settle feasibility
                        # check below; only a finished terminal leg that still
                        # exceeds the served grade is replaced by the bounded
                        # neighbour-owned switchback search.
                        path,approach,leg_count=route_initial_seam_neighbour(
                            world,link,region,anchor,outward,seam_road_waypoints(content,region,link['id']),
                            route_in_legs,saved=saved_connection)
                        paths.append((region,path,approach,leg_count))
                except ValueError as error:
                    restore_claims(world,claims);failures.append(str(error));continue
                if choice is not choices[0]:
                    world.__dict__.setdefault('moved_seam_crossings',[]).append({'id':link['id'],'from':list(link['anchor']),'to':anchor.tolist(),'failures':failures})
                    link['anchor']=anchor.tolist();link['normal']=normal.tolist()
                for region,path,approach,leg_count in paths:
                    world.add_road(path,width=4,name=link['id']+'-'+region)
                    if approach is not None:
                        world.__dict__.setdefault('saved_seam_approaches',[]).append(
                            {'id':link['id'],'region':region,**approach})
                    print(f'Road {region} to {link["id"]}: {len(path)} stations'
                          +(f' by saved approach {approach["waypoint"]}' if approach is not None and approach['waypoint'] is not None
                            else f' by {leg_count-2} authored waypoints' if approach is None and leg_count>2 else ''),flush=True)
                break
            else:
                raise ValueError(f"{link['id']}: no seam station of the crossing can be reached from both hubs: {failures}")
        else:
            prepare_ferry_connection(world,link,saved_ferry_endpoints[link['id']])
    # Inhabited approaches grow from the public roads to existing doorways.
    # Close destinations share a trail; resources remain in the wilderness.
    for region in world.ids:
        if region in authored_regions:continue
        hub=world.hub(region)
        seen=[]
        for entry in content.templates[region].get('portals',[]):
            target=entry.get('targetMap',entry.get('destinationMap',''))
            if target in world.ids or 'position' not in entry:continue
            point=content.mapped_point(region,entry['position'],entry.get('node',entry.get('doorNode')),entry.get('landmark'))[[0,2]]
            if int(world.owner_at(*point))!=world.ids.index(region):continue
            if any(np.linalg.norm(point-p)<7 for p in seen):continue
            seen.append(point)
            # A door inside a retained pavilion gets its road on the pavilion's open side;
            # a designed climb is routed through its authored waypoints in legs. A door
            # standing in a river's water or setback is served from the nearest dry ground
            # outside it (a pinned end is validated there already).
            name='door-'+region+'-'+str(entry.get('id','entry'))
            end=door_road_end(content,region,entry.get('id'),point)
            end,moved=dry_end(world,end,1.65,region)
            legs=[hub]+door_road_waypoints(content,region,entry.get('id'))+[end]
            claims=snapshot_claims(world)
            try:path=route_in_legs(world,legs,region,width=1.65,public=True,name=name)
            except ValueError as error:
                restore_claims(world,claims);world.unrouted.append({'road':name,'region':region,'reason':str(error)});continue
            if moved:world.__dict__.setdefault('dry_road_ends',[]).append({'road':name,'from':point.tolist(),'to':end.tolist()})
            world.add_road(path,width=1.65,name=name)
    # The server also declares hidden rooms and instance returns that are not
    # client portal markers. Give these discoveries narrow branches from the
    # nearest public route, using the same authored point transform as export.
    profile=HERE/'legacy-server-profile/config/eloria/maps.txt'
    destinations={region:[] for region in world.ids}
    for number,line in enumerate(profile.read_text(encoding='utf-8').splitlines(),1):
        fields=[part.strip() for part in line.split('#',1)[0].split('|')]
        if not fields or fields[0]!='portal' or len(fields) not in (7,8):continue
        start=2 if len(fields)==7 else 3
        source,target=fields[1],fields[start+2]
        if source in world.ids and target in world.ids:continue
        for region,tile in ((source,fields[start:start+2]),(target,fields[start+3:start+5])):
            if region not in world.ids:continue
            if region in authored_regions:continue
            point=content.mapped_server_point(region,list(map(int,tile)),roads=True)[[0,2]]
            if int(world.owner_at(*point))==world.ids.index(region):destinations[region].append((number,point,source,target))
    for region,entries in destinations.items():
        seen=[]
        for number,point,source,target in entries:
            if any(np.linalg.norm(point-p)<5 for p in seen):continue
            seen.append(point)
            # A server portal with its own pin is routed to that dry ground from
            # the network on that side of the portal and runs straight on to the
            # portal where that run crosses no river; one beside a pinned door
            # shares the door's road end. An end in a river's water or setback is
            # served from the nearest dry ground outside it.
            pin=server_road_end(content,region,point,source,target)
            end=pin if pin is not None else door_road_end_near(content,region,point)
            end,moved=dry_end(world,end,1.65,region)
            # A branch starts on dry land outside the setback, never on a bridge, and on its destination's bank.
            stations=np.vstack([np.asarray(road['points'])[:,[0,2]] for road in world.roads])
            start,gap=branch_start(world,region,stations,end,1.65,toward=point if pin is not None else None)
            if start is None or (gap<4 and pin is None):continue
            name=f'discovery-{region}-{number}'
            claims=snapshot_claims(world)
            try:path=world.route(start,end,region=region,width=1.65,name=name)
            except ValueError as error:
                restore_claims(world,claims);world.unrouted.append({'road':name,'region':region,'reason':str(error)});continue
            if pin is not None and np.linalg.norm(pin-point)>SERVER_ROAD_END_LEG_METRES:
                run=np.linspace(0.,1.,max(2,int(np.ceil(np.linalg.norm(point-end)))+1))[:,None]*(point-end)+end
                if not (water_distance_at(world,run[:,0],run[:,1])<=0.).any():path=np.vstack([path,point])
            if moved:world.__dict__.setdefault('dry_road_ends',[]).append({'road':name,'from':point.tolist(),'to':end.tolist()})
            world.add_road(path,width=1.65,name=name)
    # Authored resource sites on steep ground that no corridor serves get a trail.
    from resource_trails import prepare_resource_trails
    trails=prepare_resource_trails(world,content,HERE/'legacy-server-profile/config/eloria',
                                   exclude_regions=authored_regions)
    print(f"Resource trails: {len(trails['trails'])} for {trails['steepSites']} steep sites ({trails['servedSites']} already beside a road)",flush=True)
    if not _saved_native_region(world,'amberwood'):
        prepare_amberwood_routes(world,content)
    # Every alignment exists now: record the retained solids any road still crosses.
    world.road_solid_crossings=world.solid_crossings(content.solid_boxes())
    print(f'Roads through retained solids: {len(world.road_solid_crossings)} (solid fallbacks {len(world.routing_report()["solidFallbacks"])})',flush=True)
    print(f'River crossings: {len(world.crossing_sites)} sites claimed of {len(world.crossing_candidates)} candidates; {len(world.unrouted)} optional roads unrouted',flush=True)
    for key in ('_water_passage_cache','_bank_labels'):world.__dict__.pop(key,None)
    world.settle_roads()
    world.saved_seam_profile=apply_saved_seam_profile(
        world,authored_regions,_seam_approach_feasible)
    if world.saved_seam_profile:
        print('Saved seam neighbour profile: '+json.dumps(
            world.saved_seam_profile,sort_keys=True,separators=(',',':')),flush=True)
    world.saved_seam_approach_repairs=repair_saved_seam_approaches(
        world,content,route_in_legs,snapshot_claims,restore_claims)
    if world.saved_seam_approach_repairs:
        print('Saved seam neighbour approaches repaired: '+json.dumps(
            world.saved_seam_approach_repairs,sort_keys=True,separators=(',',':')),flush=True)
    PROGRESS.step('supports and ground',2,4)
    from mirror_support import apply_mirror_support
    from four_gates_support import apply_four_gates_support
    if not _saved_native_region(world,'four_gates','four_gates_support'):
        apply_four_gates_support(world,content)
    apply_mirror_support(world,content)
    apply_mirror_access(world,content)
    if not _saved_native_region(world,'amberwood','amberwood_support'):
        apply_amberwood_support(world,content)
    from ssarathi_bank_support import apply_ssarathi_banks
    if not _saved_native_region(world,'ssarathi_ruins','ssarathi_bank_support'):
        apply_ssarathi_banks(world,content)
    finish_mirror_lake_support(world,content)
    # Reach links are written on the finished ground: the roads are settled and the supports done, so nothing
    # grades them again; road heights and placements follow them below.
    from reach_links import apply_reach_links
    reach=apply_reach_links(world,content)
    if reach['links']:print(f"Reach links: {reach['links']} written on the finished ground ({reach['changedCells']} cells changed, up to {reach['maximumChangeMetres']} m)",flush=True)
    # Each exact editor preview is final terrain authority for its territory
    # and one-cell seam ring. No legacy grading may survive those vertices.
    final_authoring_terrain={region:AUTHORING.apply_terrain(world,snapshot)
                             for region,snapshot in snapshots_by_region.items()}
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    # The fixed shoulder samples contain no road XZ changes.  Road distance
    # queries stay valid; refresh_road_heights below reads their final Y after
    # bridge preparation, as it does for every other late terrain support.
    world.saved_post_support_profile=apply_post_support_seam_profile(
        world,authored_regions,_seam_approach_feasible,saved_seam_approach_grade)
    if world.saved_post_support_profile['changedCells']:
        print('Saved post-support seam shoulders: '+json.dumps(
            world.saved_post_support_profile,sort_keys=True,separators=(',',':')),flush=True)
    validate_saved_seam_approaches(world)
    from bridge_prepare import prepare_bridges
    bridge_events=[]
    def bridge_progress(phase,**details):
        event={'phase':phase,**details};bridge_events.append(event)
        print('claimed_bridge_progress '+json.dumps(event,sort_keys=True,separators=(',',':')),flush=True)
    world.claimed_bridge_progress=bridge_progress
    try:
        world.bridge_preparation=prepare_bridges(world,content)
    finally:
        world.__dict__.pop('claimed_bridge_progress',None)
        world.claimed_bridge_progress_events=bridge_events
    # The support stages have finished the ground: every road station stands on it again (bridges excepted).
    world.refresh_road_heights()
    # Claimed bridge fitting can still commit terrain edits. Check every saved
    # approach on the actual post-bridge ground before final placements/export.
    validate_saved_seam_approaches(world)
    final_ferries=validate_final_ferries(world)
    print(f'Final ferry shore readback: {len(final_ferries["finalFits"])} complete quay/mooring fits',flush=True)
    content.reground()
    from manymouth_boats import apply_manymouth_boats
    if _saved_native_region(world,'manymouth_delta'):
        world.manymouth_boats={'boats':[],'afloat':0,'hauledUp':0,
            'skipped':'saved-authoring-authority'}
        content.manymouth_boats=world.manymouth_boats
    else:apply_manymouth_boats(world,content)
    from hull_settle import apply_hull_settle
    apply_hull_settle(world,content)
    if not _saved_native_region(world,'amberwood'):
        refresh_amberwood_access_heights(world,content)
    if not _saved_native_region(world,'grey_moors'):
        refresh_grey_crossing_heights(world,content)
    if not _saved_native_region(world,'four_gates'):
        refresh_four_gates_sage_heights(world,content)
    refresh_authored_point_heights(world,content)
    content.ecological_scatter()
    if any(digest(HERE/name)!=sha for name,sha in shaping.items()):
        raise ValueError('Landscape shaping source changed during composition; run prepare again')
    if geometry_dependencies()!=dependencies:raise ValueError('Geometry dependencies changed during composition; run prepare again')
    if digest(HERE/'diagonal-plan.json')!=plan_sha:raise ValueError('Landscape plan changed during composition')
    if object_edits_digest()!=edits_sha:raise ValueError('Object edits changed during composition')
    if digest(profile)!=profile_sha:raise ValueError('Authored entrances changed during composition')
    current_snapshots={value.document['regionId']:value for value in AUTHORING.load_snapshots()}
    if set(current_snapshots)!=set(snapshots_by_region) or any(
            current_snapshots[region].digest!=snapshot.digest or
            current_snapshots[region].bound_sources()!=snapshot.bound_sources()
            for region,snapshot in snapshots_by_region.items()):
        raise ValueError('An authored scene or snapshot changed during composition; run prepare again')
    PROGRESS.step('writing the composition',3,4)
    # Cache is local generated state with exact source certificates. Never load
    # an arbitrary downloaded pickle as an authored continent.
    with (output/'composed.pkl').open('wb') as handle:pickle.dump((world,content),handle,protocol=5)
    json_write(output/'composition.json',{'schema':2,'planSha256':plan_sha,'objectEditsSha256':edits_sha,'objectEdits':{'document':content.edits.doc,'report':content.edits.report},'entranceProfileSha256':profile_sha,'compositionAlgorithmSha256':algorithm_sha,'geometryDependencies':dependencies,
        'continentAuthoring':{'schema':3,'regions':{
            region:{'snapshotSchema':snapshot.document['schema'],
                'snapshotSha256':snapshot.digest,'sources':snapshot.bound_sources(),
                'storage':world.storage_contract(region),
                'terrainInitial':initial_authoring_terrain[region],
                'terrainFinal':final_authoring_terrain[region],
                'routes':authoring_routes[region],
                'runtimeBindings':authoring_runtime[region],
                'replacements':snapshot.document['replacements']}
            for region,snapshot in snapshots_by_region.items()}},
        'library':{r:digest(Path(library)/r/'source-certificate.json') for r in world.ids},
        'sources':sources,
        'objects':len(content.objects),'roads':len(world.roads),'assemblies':content.assembly_records,
        'mirrorLakeSupport':world.mirror_lake_support,'ssarathiBankSupport':world.ssarathi_bank_support,
        'manymouthBoats':world.manymouth_boats,'greyCrossings':world.grey_crossings,'fourGatesSage':world.four_gates_sage,
        'doorApproaches':world.door_approaches,'reachLinks':getattr(world,'reach_links',{'links':0,'perLink':[]}),'authoredPoints':getattr(world,'authored_points',{'points':[]}),'hullSettle':world.hull_settle,'roadGradingPasses':world.road_grading_passes,'resourceTrails':world.resource_trails,
        'riverCrossings':crossing_report(world),'movedSeamCrossings':getattr(world,'moved_seam_crossings',[]),
        'savedSeamApproaches':getattr(world,'saved_seam_approaches',[]),
        'savedSeamApproachRepairs':getattr(world,'saved_seam_approach_repairs',[]),
        'savedPostSupportProfile':getattr(world,'saved_post_support_profile',None),
        'dryRoadEnds':getattr(world,'dry_road_ends',[]),
        'bridgePreparation':world.bridge_preparation,'claimedBridgeProgress':bridge_events,
        'routing':{**world.routing_report(),'solidCrossings':world.road_solid_crossings},
        'elapsedSeconds':round(time.monotonic()-started,2)})
    PROGRESS.step('composition written',4,4)
    return world,content


def load_composed(output,library):
    certificate=json.loads((output/'composition.json').read_text())
    if certificate['planSha256']!=digest(HERE/'diagonal-plan.json'):raise ValueError('Landscape plan changed; recompose before export')
    if certificate.get('objectEditsSha256',EMPTY_SHA256)!=object_edits_digest():raise ValueError('Object edits changed; recompose before export')
    if certificate.get('entranceProfileSha256')!=digest(HERE/'legacy-server-profile/config/eloria/maps.txt'):raise ValueError('Authored entrance profile changed; recompose before export')
    algorithm_sha=composition_algorithm_sha()
    if certificate.get('compositionAlgorithmSha256')!=algorithm_sha:raise ValueError('Composition algorithm changed; recompose before export')
    if certificate.get('geometryDependencies')!=geometry_dependencies():raise ValueError('Geometry dependencies changed; recompose before export')
    snapshots={snapshot.document['regionId']:snapshot for snapshot in AUTHORING.load_snapshots()}
    authored=certificate.get('continentAuthoring',{}).get('regions')
    if not isinstance(authored,dict) or set(authored)!=set(snapshots):
        raise ValueError('Authored territory set changed; recompose before export')
    for region,snapshot in snapshots.items():
        if authored[region].get('snapshotSha256')!=snapshot.digest:
            raise ValueError(f'{region}: authoring snapshot changed; recompose before export')
        if authored[region].get('sources')!=snapshot.bound_sources():
            raise ValueError(f'{region}: authoring scene or sidecars changed; recompose before export')
        contract=snapshot.contract
        expected_storage={'serverOrigin':list(contract.server_origin),'serverCells':list(contract.server_cells),
            'serverStorageVersion':1,'serverTileMin':list(contract.server_tile_min),
            'authoringSpecSha256':contract.spec_sha256}
        if authored[region].get('storage')!=expected_storage:
            raise ValueError(f'{region}: authored storage certificate changed; recompose before export')
    for region,sha in certificate['library'].items():
        if sha!=digest(Path(library)/region/'source-certificate.json'):raise ValueError(f'{region}: source content changed; recompose')
    sources={relative.replace('\\','/'):sha for relative,sha in certificate['sources'].items()}
    missing=shaping_source_keys()-sources.keys()
    if missing:raise ValueError('Composition is missing shaping source certificates: '+', '.join(sorted(missing)))
    for relative in sorted(shaping_source_keys()):
        # Export-only fixes may reuse the completed landform. Its shaping
        # modules and source content are the exact terrain authority.
        if digest(CLIENT/relative)!=sources[relative]:
            raise ValueError(f'{relative}: landscape composition changed; recompose')
    with (output/'composed.pkl').open('rb') as handle:return pickle.load(handle)


def bridge_export_world(world):
    """Copy prepared coastal records for export, omitting covered support roofs."""
    from shapely import Polygon,union_all
    records=tuple(getattr(world,'claimed_coastal_records',()))
    if not records:return world,()
    reports=[];export_records=[]
    for claim in records:
        floor=np.asarray(claim.encoded_floor_triangles,np.float32).astype(float)
        def support_without_roof(support):
            faces=np.asarray(support.encoded_triangles,np.float32).astype(float)
            top=float(np.float32(support.top_height_metres))
            normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
            roof=(np.abs(normal[:,1])>0.)&np.all(faces[:,:,1]==top,axis=1)
            if not np.any(roof):return support
            floor_at_top=floor[np.all(floor[:,:,1]==top,axis=1)]
            if not len(floor_at_top):
                raise ValueError(f'{claim.claim_id}: support roof has no identical-height prepared floor')
            floor_union=union_all([Polygon(face[:,[0,2]]) for face in floor_at_top])
            footprint=Polygon(np.asarray(support.footprint_xz,float))
            outside=footprint.difference(floor_union)
            if not footprint.is_valid or footprint.area<=0. or not outside.is_empty:
                raise ValueError(f'{claim.claim_id}: support roof footprint is not completely covered by prepared floor')
            retained=faces[~roof]
            reports.append({'claimId':claim.claim_id,'support':support.name,
                            'roofTrianglesOmitted':int(roof.sum()),
                            'retainedTriangles':len(retained),'supportFootprintArea':float(footprint.area),
                            'outsidePreparedFloorArea':float(outside.area)})
            return replace(support,triangles=retained)
        supports=tuple(support_without_roof(support) for support in claim.supports)
        stairs=tuple(replace(stair,supports=tuple(support_without_roof(support)
                                                  for support in stair.supports))
                     for stair in claim.stairs)
        export_records.append(replace(claim,supports=supports,stairs=stairs))
    result=copy.copy(world);result.claimed_coastal_records=tuple(export_records)
    result.coastal_support_roof_export=tuple(reports)
    return result,tuple(reports)


def bridge_scene(world,path):
    from bridge_export import build_bridges
    export_world,_=bridge_export_world(world)
    result=build_bridges(export_world,path)
    # build_bridges assigns these derived export/query products. The export-local
    # coastal-record copy must not hide them from the normal geometry pipeline.
    for name in ('bridge_report','bridge_triangles','bridge_field'):
        setattr(world,name,getattr(export_world,name))
    return result


def saved_grey_crossing_landmarks(world,content,region,manifest):
    """Keep Grey's saved landmark bindings on its actual retained Walk roots.

    The procedural Grey exporter moves retired boardwalk identities onto new
    generated bridge floors. A saved Grey scene already carries those final
    landmark nodes and positions; native floors may be intentionally absent.
    """
    if region!='grey_moors':return []
    from grey_crossings import RETAINED_IDENTITIES
    snapshot=world.authoring_snapshots[region]
    source={entry['id']:entry for entry in snapshot.document['gameplay']['landmarks']
            if entry.get('id') in RETAINED_IDENTITIES}
    landmarks=manifest.get('landmarks',[])
    selected=[entry for entry in landmarks if entry.get('id') in RETAINED_IDENTITIES]
    if len(selected)!=len({entry['id'] for entry in selected}):
        raise ValueError('Grey Moors saved boardwalk landmark IDs are duplicated')
    by_id={entry['id']:entry for entry in selected}
    active={}
    for obj in content.objects:
        if obj.get('region')!=region:continue
        crossing=(obj.get('source') or {}).get('authoredCrossing')
        if not isinstance(crossing,dict):continue
        node=crossing.get('walkNode')
        if node in active:raise ValueError(f'Grey Moors saved crossing Walk root {node} is duplicated')
        active[node]=crossing
    center=np.asarray(world.regions[region]['center'],float)
    report=[]
    for identity,retired in RETAINED_IDENTITIES.items():
        entry=by_id.get(identity);original=source.get(identity)
        if (entry is None)!=(original is None):
            raise ValueError(f'{identity}: saved scene and exported landmark presence differ')
        if entry is None:continue  # an explicit saved landmark deletion stays deleted
        node=entry.get('node')
        if node!=original.get('node') or node not in active:
            raise ValueError(f'{identity}: saved landmark node {node!r} has no active authored crossing Walk root')
        position=np.asarray(entry.get('position',()),float)
        if position.shape!=(3,) or not np.isfinite(position).all():
            raise ValueError(f'{identity}: saved landmark position is invalid')
        report.append({'id':identity,'node':node,'crossingId':active[node]['id'],
                       'replacedSpan':retired,'authority':'saved-scene',
                       'globalPosition':[float(position[0]+center[0]),float(position[1]),
                                         float(position[2]+center[1])]})
    dangling=[entry.get('id') for entry in landmarks
              if entry.get('node') in RETAINED_IDENTITIES.values()]
    if dangling:raise ValueError('Retired Grey Moors spans are still referenced by saved landmarks: '
                                 +', '.join(map(str,dangling)))
    return report


def local_point(point,center):
    p=np.array(point,float).copy();p[[0,2]]-=center;return p.tolist()


def manifest_for(world,content,region):
    m=copy.deepcopy(content.templates[region]);center=np.array(world.regions[region]['center']);origin,cells=world.address(region)
    storage=world.storage(region)
    storage_source=world.storage_contract(region)
    hub=world.hub(region);arrival=local_point([hub[0],float(world.height_at(*hub)),hub[1]],center)
    def transform(item):
        if isinstance(item,list):return [transform(v) for v in item]
        if not isinstance(item,dict):return item
        result={k:transform(v) for k,v in item.items()}
        node=item.get('node',item.get('doorNode'));landmark=item.get('landmark')
        for key in ('position','arrivalPosition','targetPosition','center'):
            v=item.get(key)
            if isinstance(v,list) and len(v)==3 and all(isinstance(a,(float,int)) for a in v):
                result[key]=local_point(content.mapped_point(region,v,node,landmark),center)
        if 'serverTile' in item:
            if 'position' in result: p=result['position']
            else:
                old_origin=content.templates[region]['coordinateTransform']['serverOrigin']
                p=local_point(content.mapped_point(region,[item['serverTile'][0]-old_origin[0]+.5,0,old_origin[1]-item['serverTile'][1]-.5]),center)
            result['serverTile']=[math.floor(p[0]+origin[0]),math.floor(origin[1]-p[2])]
        return result
    for key in ('landmarks','interactives','portals','spawnPoints','pointsOfInterest','harvestables','npcMarkers','creatureSpawns','spawns','effects','ambientPopulation','lighting','environment'):
        if key in m:m[key]=transform(m[key])
    obsolete_landmarks={'whitehorn_range':('Landmark_rope_bridge_',),'amberwood':('Landmark_Survey_ridge-bridge',)}
    if region in obsolete_landmarks:
        # These wilderness spans were replaced by the continental road bridges.
        # Named-location UI reads landmark coordinates without checking nodes.
        m['landmarks']=[p for p in m.get('landmarks',[]) if not str(p.get('node','')).startswith(obsolete_landmarks[region])]
    m['portals']=[p for p in m.get('portals',[]) if p.get('destinationMap',p.get('targetMap')) not in world.ids]
    m['streamingBorders']=[]
    for old in ('authoredGeometry','landscapeRevision','runtimePopulation','contentLayout','water','roads','paths','gates','bridges','districts','regions',
                'borderVistas','lodGroups','lensVaultApproach','secretApproaches','compactLandscape','terraces','buildNotes','assumptions','statistics'):
        m.pop(old,None)
    lo,hi=world.bounds(region);h=world.height
    minimum=[float(lo[0]-center[0]),float(h.min()),float(lo[1]-center[1])]
    maximum=[float(hi[0]-center[0]),float(h.max()+50),float(hi[1]-center[1])]
    m['asset'].update(id=region,glb='world.glb',units='meters',bounds={'min':minimum,'max':maximum})
    m['asset']['mapBounds']={'min':minimum,'max':maximum}
    m['asset']['playableBounds']={'min':minimum,'max':maximum}
    m['bounds']={'min':minimum,'max':maximum}
    m['coordinateTransform']={'metresPerTile':1.,'serverOrigin':origin,'serverCells':cells,'origin':[0,0,0],
        'walkingHeight':arrival[1],'invertServerY':True,**storage.metadata(),
        'addressableWorldBounds':dict(zip(('min','max'),storage.physical_bounds(origin)))}
    m['coordinateTransform'].update(storage_record(cells,storage_source))
    authored=region in getattr(world,'authoring_snapshots',{})
    if authored:
        spawns=m.get('spawnPoints',[])
        if not spawns:raise AUTHORING.AuthoringError(f'authored {region} manifest lost every spawn point')
        defaults=[spawn for spawn in spawns if spawn.get('default')]
        if len(defaults)>1:raise AUTHORING.AuthoringError(f'authored {region} manifest has multiple default spawns')
        selected=defaults[0] if defaults else spawns[0]
        default_spawn=str(selected['id']);walking_height=float(selected['position'][1])
    else:
        default_spawn='continent-arrival';walking_height=arrival[1]
        m['spawnPoints']=[{'id':default_spawn,'default':True,'position':arrival,'facing':[0,0,-1]}]
    m['coordinateTransform']['walkingHeight']=walking_height
    source_contract=getattr(world,'_storage_contracts',{}).get(region)
    if source_contract is not None and source_contract.server_frame[4]:
        m['coordinateTransform']['walkingHeight']=source_contract.server_frame[5]
    m['navigation']={'surfaceNodePrefixes':['Terrain_','Walk_'],'terrainConforming':True,'authority':'server',
                     'defaultSpawn':default_spawn,'collisionFile':'collision.bin'}
    solid=[o['node'] for o in content.objects if o['region']==region and o.get('collides')]
    m['collision']={'file':'collision.bin','binary':'collision.bin','format':'EWCG','formatVersion':2,'version':2,
                    'cellMetres':.5,'cellSize':.5,'authoredSurfaceExport':True,'gridAlignment':'tile-centres-v1','nodeNames':solid,
                    **storage.metadata(),'serverCells':cells,'originMetres':list(storage.physical_origin(origin))}
    if 'authoringSpecSha256' in storage_source:
        m['collision']['authoringSpecSha256']=storage_source['authoringSpecSha256']
    m['minimap']={'file':'minimap.webp','image':'minimap.webp','bounds':m['bounds'],'northUp':True,
        'worldMin':[minimum[0],minimum[2]],'worldMax':[maximum[0],maximum[2]],
        'imageSize':[int(round(maximum[0]-minimum[0])),int(round(maximum[2]-minimum[2]))],'pixelsPerMetre':1}
    m['continentGeography']={'revision':'diagonal-spine-v1','translation':[float(center[0]),0,float(center[1])],
                            'ownershipPolygon':world.polygons[region],'geometryMode':'continent-chunks-v1'}
    m['terrainRevision']='diagonal-spine-v1'
    m['sources']=['_continent/diagonal-plan.json','_continent/build_continent.py','_continent/build_library.py']
    m['knownLimitations']=[]
    apply_manifest(world,region,m)
    # One physically consistent light, sea and haze across the whole landmass.
    env=m.setdefault('environment',{})
    env['sun']={'direction':[-.45,-.78,-.43],'color':[1.,.94,.83],'energy':1.1}
    env['ambient']={'color':[.60,.67,.72],'energy':.6}
    return m


def add_to_exporter(exporter,world,content,region,terrain_doc,terrain_body,terrain_roots,objects,bridge_doc,bridge_body,bridges,global_space=False):
    center=np.array(world.regions[region]['center'])
    offset=np.zeros(3) if global_space else np.array([-center[0],0,-center[1]])
    if terrain_roots:exporter.add(terrain_doc,terrain_body,terrain_roots,transforms={r:offset for r in terrain_roots})
    for obj in objects:
        source=obj.get('libraryRegion',region);doc,body=content.documents[source]
        roots=obj.get('indices',[obj['index']])
        exporter.add(doc,body,roots,transforms={index:obj['shift']+offset for index in roots},prefix=region+'_',node_prefix=obj.get('nodePrefix',''))
    for bridge in bridges:
        exporter.add(bridge_doc,bridge_body,bridge['roots'],transforms={r:offset for r in bridge['roots']},prefix=region+'_')


def prune_retired_exports(manifests):
    """Remove only identifiable generated cells after the new export succeeds."""
    for region,manifest in manifests.items():
        root=(package(region)/'chunks').resolve()
        keep={row['id'] for row in manifest['streamingChunks']['chunks']}
        for directory in root.iterdir():
            if not directory.is_dir() or directory.name in keep or not re.fullmatch(r'\d+_\d+',directory.name):continue
            resolved=directory.resolve()
            resolved.relative_to(root)
            old=resolved/'world.json'
            if not old.is_file():continue
            prior=json.loads(old.read_text(encoding='utf-8'))
            if prior.get('asset',{}).get('id')!=region+'__chunk_'+directory.name:continue
            if prior.get('continentGeography',{}).get('geometryMode')!='continent-chunks-v1':continue
            shutil.rmtree(resolved)
    shared=(HERE/'shared-assets').resolve()
    keep={Path(uri).name for manifest in manifests.values() for uri in manifest['externalResources']}
    for path in shared.iterdir():
        if path.is_file() and re.fullmatch(r'[0-9a-f]{64}\.(png|jpg)',path.name) and path.name not in keep:
            path.resolve().relative_to(shared);path.unlink()


def export_geometry(world,content,output):
    PROGRESS.start('geometry',len(world.ids))
    composition_sha=digest(output/'composition.json')
    dependencies=geometry_dependencies()
    export_sources={name:digest(HERE/name) for name in EXPORT_SOURCES}
    prepare_contracts(world)
    terrain_path=output/'shared-terrain.glb';bridge_path=output/'bridges.glb'
    from ferry_export import build_ferries
    from amberwood_access import build_amberwood_access
    from manymouth_access import build_manymouth_access
    from mirror_access_geometry import build_mirror_access
    from grey_crossings import remap_grey_crossing_landmarks
    river_path=output/'river-bridges.glb';ferry_path=output/'ferry-quays.glb'
    access_path=output/'amberwood-access.glb'
    access_parts=build_amberwood_access(world,content,access_path)
    fishing_path=output/'manymouth-access.glb'
    fishing_parts=build_manymouth_access(world,content,fishing_path)
    mirror_path=output/'mirror-bank-access.glb'
    mirror_parts=build_mirror_access(world,content,mirror_path)
    from access_decks import build_access_decks
    decks_path=output/'access-decks.glb'
    deck_parts=build_access_decks(world,content,decks_path)
    river_parts=bridge_scene(world,river_path)
    ferry_parts=build_ferries(world,ferry_path)
    structures=S.Exporter(bridge_path);bridge_parts=[];structure_sources=[]
    for path,parts in ((river_path,river_parts),(ferry_path,ferry_parts),(access_path,access_parts),(fishing_path,fishing_parts),(mirror_path,mirror_parts),(decks_path,deck_parts)):
        doc,body=S.GR.load(path);structure_sources.append((doc,body))
        for part in parts:
            start=len(structures.doc['scenes'][0]['nodes'])
            structures.add(doc,body,part['roots'])
            bridge_parts.append(dict(part,roots=structures.doc['scenes'][0]['nodes'][start:].copy()))
    structures.write()
    json_write(output/'crossing-structures.json',{'bridges':world.bridge_report,'ferries':world.ferry_report,'amberwoodAccess':world.amberwood_access,'manymouthAccess':world.manymouth_access,'mirrorBankAccess':world.mirror_bank_access,'mirrorBankOpening':world.mirror_bank_opening,'accessDecks':getattr(world,'access_decks',[])})
    # The composed roads and their crossing sites, for the road-rule audit (audit_continent.audit_road_rules).
    from river_crossings import crossing_report
    json_write(output/'roads.json',{'schema':2,'roads':[{'id':road['id'],'width':float(road['width']),
        **({'widths':[float(value) for value in road['widths']]} if 'widths' in road else {}),
        'points':road['points']} for road in world.roads],
        'crossingSites':crossing_report(world)['sites'] if hasattr(world,'crossing_sites') else [],
        'designedDecks':world.plan.get('designed_decks',[])})
    partitions=partition_surface(world,terrain_path)
    # Appearance masks are generated during export from the final world and
    # saved Surface records. Geometry and collision remain byte-identical.
    chunk_cells={(int(name[:2]),int(name[3:])) for chunks in partitions.values() for name in chunks}
    world.biome_blend_chunks=build_masks(world,chunk_cells)
    catalog={"schema":"eloria-biome-blend-catalog-v1","chunkMetres":CHUNK,
             "chunks":[world.biome_blend_chunks[key] for key in sorted(world.biome_blend_chunks,
                       key=lambda cell:(cell[1],cell[0]))]}
    json_write(CLIENT/'godot-client/assets/world/biome_blend/catalog.json',catalog)
    from compact_glb_images import compact_embedded_images
    terrain_image_compaction=compact_embedded_images(terrain_path)
    print('Shared terrain image compaction: '+json.dumps(terrain_image_compaction,sort_keys=True),flush=True)
    terrain_doc,terrain_body=S.GR.load(terrain_path);bridge_doc,bridge_body=S.GR.load(bridge_path)
    master_path=output/'continent.glb';master=S.Exporter(master_path)
    by_region={r:[o for o in content.objects if o['region']==r] for r in world.ids}
    by_bridge={r:[b for b in bridge_parts if b['region']==r] for r in world.ids}
    for region in world.ids:
        roots=[n for c in partitions[region].values() for n in c['roots']]
        add_to_exporter(master,world,content,region,terrain_doc,terrain_body,roots,by_region[region],bridge_doc,bridge_body,by_bridge[region],True)
    master_stats=master.write();master_sha=digest(master_path)
    json_write(output/'master-scene.json',dict(master_stats,sha256=master_sha,regions=world.ids,
                                               storageByRegion={r:world.storage_contract(r) for r in world.ids},
                                               authoredOverlays=getattr(world,'authored_overlay_report',{})))
    del master
    manifests={};grey_landmarks=[]
    for region in world.ids:
        root=package(region);shared=HERE/'shared-assets';center=np.array(world.regions[region]['center'])
        manifest=manifest_for(world,content,region)
        objects=by_region[region];bridges=by_bridge[region]
        manifest['collision']['nodeNames'].extend(part['node'] for part in bridges if part.get('collides'))
        # Retired Grey survey spans keep their generic identities on the actual emitted crossing floors.
        if region=='grey_moors' and region in world.authoring_snapshots:
            grey_landmarks+=saved_grey_crossing_landmarks(world,content,region,manifest)
        else:
            grey_landmarks+=remap_grey_crossing_landmarks(world,content,region,manifest,bridge_doc,bridge_body,bridges)
        chunks=partitions[region]
        for obj in objects:
            midpoint=(obj['low']+obj['high'])*.5
            cx=int((midpoint[0]-world.x0)//CHUNK);cz=int((midpoint[2]-world.z0)//CHUNK)
            name=f'{cx:02d}_{cz:02d}'
            entry=chunks.setdefault(name,{'roots':[],'bounds':[obj['low'].copy(),obj['high'].copy()],'cell':[cx,cz],'terrainCells':0})
            entry.setdefault('objects',[]).append(obj)
            entry['bounds']=[np.minimum(entry['bounds'][0],obj['low']),np.maximum(entry['bounds'][1],obj['high'])]
        for bridge in bridges:
            lo,hi=bridge['bounds'];mid=(lo+hi)*.5;cx=int((mid[0]-world.x0)//CHUNK);cz=int((mid[2]-world.z0)//CHUNK);name=f'{cx:02d}_{cz:02d}'
            entry=chunks.setdefault(name,{'roots':[],'bounds':[lo.copy(),hi.copy()],'cell':[cx,cz],'terrainCells':0})
            entry.setdefault('bridges',[]).append(bridge)
            entry['bounds']=[np.minimum(entry['bounds'][0],lo),np.maximum(entry['bounds'][1],hi)]
        exporter=S.Exporter(root/'world.glb',shared,part_bytes=S.PACKAGE_PART_BYTES)
        add_to_exporter(exporter,world,content,region,terrain_doc,terrain_body,[r for c in chunks.values() for r in c['roots']],objects,bridge_doc,bridge_body,bridges)
        stats=exporter.write();manifest['performance']=stats;manifest['externalResources']=stats['externalResources']
        manifest['singleContinentSource']={'revision':'diagonal-spine-v1','masterSha256':master_sha,'planSha256':digest(HERE/'diagonal-plan.json')}
        manifest['singleContinentSource']['storage']=storage_record(world.address(region)[1],world.storage_contract(region))
        manifest['streamingChunks']={'schemaVersion':'1.0','coordinateSpace':'territory-local','preloadDistance':240,'retainDistance':320,
            'maximumLoadedChunks':64,'maximumResidentBytes':268435456,'chunks':[]}
        manifest['streamingChunks']['storage']=copy.deepcopy(manifest['singleContinentSource']['storage'])
        for name,entry in sorted(chunks.items()):
            chunk_root=root/'chunks'/name;chunk=S.Exporter(chunk_root/'world.glb',shared)
            add_to_exporter(chunk,world,content,region,terrain_doc,terrain_body,entry['roots'],entry.get('objects',[]),bridge_doc,bridge_body,entry.get('bridges',[]))
            chunk_stats=chunk.write()
            c=copy.deepcopy(manifest)
            for key in ('streamingChunks','landmarks','interactives','portals','spawnPoints','pointsOfInterest','harvestables','npcMarkers','creatureSpawns','spawns','effects','interiors'):
                c.pop(key,None)
            bounds={'min':local_point(entry['bounds'][0],center),'max':local_point(entry['bounds'][1],center)}
            c['asset'].update(id=region+'__chunk_'+name,glb='world.glb',bounds=bounds)
            c['bounds']=bounds
            names={n.get('name') for n in chunk.doc['nodes']}
            c['collision']['nodeNames']=[n for n in manifest['collision']['nodeNames'] if n in names]
            c['collision'].pop('file',None);c['collision'].pop('binary',None)
            c['navigation'].pop('collisionFile',None)
            c['performance']=chunk_stats;c['externalResources']=chunk_stats['externalResources']
            blend=getattr(world,'biome_blend_chunks',{}).get(tuple(entry['cell']))
            if blend is not None and f'{region}:base' in {item['id'] for item in blend['palettes']}:
                c['biomeBlend']=blend
            else:
                # Field presence is authority: an opted-out/newly baked chunk
                # must not inherit an older colour-refresh catalog entry.
                c['biomeBlend']=None
            # Retained asset material edits are baked into the new GLB. The
            # explicit empty list invalidates an older color-only catalog;
            # existing published chunks without this key still use it.
            c['objectMaterialOverrides']={'schema':'eloria-object-material-overrides-v1','entries':[]}
            json_write(chunk_root/'world.json',c)
            # Conservative geometry + BVH + texture allowance. Runtime has an
            # independent shared-texture pool; this deliberately overestimates.
            geometry_bytes=chunk_stats['glbBytes']*5
            shared_bytes=chunk_stats['sharedResourceResidentBytes']
            estimated=geometry_bytes+sum(shared_bytes.values())
            manifest['streamingChunks']['chunks'].append({'id':name,'manifest':f'chunks/{name}/world.json','bounds':bounds,
                'estimatedResidentBytes':estimated,'glbBytes':chunk_stats['glbBytes'],
                'geometryResidentBytes':geometry_bytes,'sharedResourceResidentBytes':shared_bytes})
        json_write(root/'world.json',manifest);manifests[region]=manifest
        print(f'{region}: exported {len(chunks)} independent chunks from the shared master',flush=True)
        PROGRESS.step(region,world.ids.index(region)+1,len(world.ids))
    prune_retired_exports(manifests)
    if any(digest(HERE/name)!=sha for name,sha in export_sources.items()):
        raise ValueError('Geometry export source changed during the build; export again before publication')
    if geometry_dependencies()!=dependencies:raise ValueError('Geometry dependencies changed during export; export again before publication')
    if digest(output/'composition.json')!=composition_sha:raise ValueError('Composition changed during geometry export')
    json_write(output/'export.json',{'masterPath':str(master_path),'masterSha256':master_sha,
        'geometrySources':export_sources,'geometryDependencies':dependencies,'compositionSha256':composition_sha,'greyCrossingLandmarks':grey_landmarks,
        'sharedTerrainImageCompaction':terrain_image_compaction,
        'regions':{r:{'world':str(package(r)/'world.json'),'glbSha256':digest(package(r)/'world.glb'),'chunks':len(m['streamingChunks']['chunks']),
            'storage':world.storage_contract(r)} for r,m in manifests.items()}})
    return manifests


def verify_geometry_export(output):
    """Reject a newer landform paired with an older or partially written GLB."""
    ledger=json.loads((output/'export.json').read_text(encoding='utf-8'))
    if ledger.get('compositionSha256')!=digest(output/'composition.json'):
        raise ValueError('Geometry does not match the composed landform; run the geometry stage before contracts')
    required=set(EXPORT_SOURCES)
    if set(ledger.get('geometrySources',{}))!=required:raise ValueError('Geometry export is missing its source certificate')
    if ledger.get('geometryDependencies')!=geometry_dependencies():raise ValueError('Geometry export dependencies changed; export again')
    for name,expected in ledger['geometrySources'].items():
        if digest(HERE/name)!=expected:raise ValueError(f'{name}: geometry export source changed; export again')
    if digest(output/'continent.glb')!=ledger['masterSha256']:raise ValueError('Exported master bytes changed')
    for region,entry in ledger['regions'].items():
        if digest(package(region)/'world.glb')!=entry['glbSha256']:raise ValueError(f'{region}: named geometry differs from its master export')
        manifest=json.loads((package(region)/'world.json').read_text(encoding='utf-8'))
        transform=manifest['coordinateTransform']
        declared={'serverOrigin':transform['serverOrigin'],**storage_record(transform['serverCells'],transform)}
        if entry.get('storage')!=declared:raise ValueError(f'{region}: geometry storage certificate changed; export again')
    return ledger


# Regional recipes still build their legacy march-border materials from the
# published geography, keyed by a per-crossing palette. Continent crossings are
# graded roads and decks, so the palette is the retained one where the same
# territory pair existed before and the first territory's biome otherwise.
REGION_PALETTES={'whitehorn_range':'alpine','grey_moors':'moor','amberwood':'upland','amethyst_barrens':'scree',
    'mirrorhold':'upland','sunmane_steppe':'steppe','four_gates':'pasture','westhaven':'pasture',
    'manymouth_delta':'pasture','crownwater':'causeway','verdant_stair':'upland','ssarathi_ruins':'moor'}


def crossing_palette(regions,legacy_connections):
    pair={str(r) for r in regions}
    for connection in legacy_connections:
        if {str(end.get('region')) for end in connection.get('ends',[])}==pair and connection.get('palette'):
            return str(connection['palette'])
    return REGION_PALETTES.get(str(regions[0]),'pasture')


def publish_geography(world,manifests,output):
    geography={'schema':1,'revision':'diagonal-spine-v1','axes':{'x':'east','y':'up','z':'south'},
        'units':'metres','worldWaterLevel':0,'geometryMode':'continent-chunks-v1','ownershipRasterMetres':CELL,
        'note':'One globally authored terrain, drainage, roads and settlements, then exact named ownership and 96m streaming chunks. Rebuild with _continent/build_continent.py; legacy geographic border synthesis is retired.',
        'masterSource':'_continent/generated/continent.glb','planSource':'_continent/diagonal-plan.json','regions':{},'connections':[]}
    for region,m in manifests.items():
        lo,hi=world.bounds(region);center=world.centers[world.ids.index(region)];origin,cells=world.address(region)
        bounds=world.storage(region)
        storage=storage_record(cells,world.storage_contract(region))
        local_lo=(lo-center).tolist();local_hi=(hi-center).tolist()
        protected=[]
        for key in ('landmarks','portals','spawnPoints'):
            for entry in m.get(key,[]):
                if isinstance(entry.get('position'),list):protected.append({'id':entry.get('id',entry.get('node','point')),'kind':key,'position':entry['position'],'radius':entry.get('radius',3)})
        geography['regions'][region]={'nativeManifestSource':str((package(region)/'world.json').relative_to(CLIENT)).replace('\\','/'),
            'nativeManifestSha256':digest(package(region)/'world.json'),'translation':[float(center[0]),0,float(center[1])],'rotationDegrees':0,
            'nativeServerOrigin':origin,'nativeServerCells':cells,'nativePlayableBounds':[local_lo,local_hi],
            'coreBounds':[lo.tolist(),hi.tolist()],'protectedDestinations':protected,
            'ownershipPolygon':world.polygons[region],'serverBounds':bounds.physical_bounds(origin),
            'serverOrigin':origin,**storage,'serverTileShift':[0,0],'atlasLabel':center.tolist(),
            'nativeServerStorageVersion':storage['serverStorageVersion'],'nativeServerTileMin':storage['serverTileMin'],
            'coordinateTransform':copy.deepcopy(m['coordinateTransform'])}
    legacy_connections=json.loads((HERE/'legacy-geography.json').read_text(encoding='utf-8')).get('connections',[])
    for connection in world.publication_connections:
        if connection['type']!='walk':continue
        frame=connection['ends'][0]['frame']
        geography['connections'].append({'id':connection['id'],'globalAnchor':frame['globalAnchor'],'normal':frame['outward'],
            'profile':'land','palette':crossing_palette([e['region'] for e in connection['ends']],legacy_connections),
            'roadWidth':8,'collarDepth':2,'ends':[dict(e['frame'],region=e['region']) for e in connection['ends']]})
    geography['verification']={'source':'shared global grid before partition','releaseRevision':'diagonal-spine-v1',
        'terrainRevisions':{r:manifests[r]['terrainRevision'] for r in world.ids},
        'sharedSurfaceSha256':digest(output/'shared-terrain.glb'),'masterSha256':digest(output/'continent.glb')}
    json_write(REGIONS/'continent-geography.json',geography)
    json_write(REGIONS/'continent-layout.json',{'schema':2,'continent':'Nymara','originMetres':[world.x0-40,world.z0-40],
        'canvasMetres':[world.x1-world.x0+80,world.z1-world.z0+80],'metresPerPixel':2,'sea':[43,95,109],
        'regions':{r:world.regions[r]['center'] for r in world.ids},'routeBends':{},
        'note':'One common-world master render; geographic centres label the named nonrectangular territories.'})


# Single-file digests composition.json records. A branch may add its own (an
# optional object-edit file beside the plan); every recorded digest is
# compared against the file it names, and anything unrecognised is reported.
COMPOSITION_INPUTS={'planSha256':('plan','diagonal-plan.json'),
    'entranceProfileSha256':('entranceProfile','legacy-server-profile/config/eloria/maps.txt'),
    'objectEditsSha256':('objectEdits','continent-edits.json')}


def composition_freshness(output=None):
    """Does the composition on disk still match the inputs it recorded?

    The same digests the compose and export stages refuse to work without,
    reported instead of raised, so an editor can show why a rebuild is due.
    Changed, missing and unrecognised inputs all read as stale. The verified
    content library is not covered: its cache path is a build argument the
    composition does not record.
    """
    output=Path(output) if output is not None else HERE/'generated'
    state={'fresh':False,'composed':False,'changed':[],'missing':[],'unknown':[],'recorded':{},'current':{}}
    path=output/'composition.json'
    if not path.exists():return state
    composition=json.loads(path.read_text(encoding='utf-8'));state['composed']=True
    def compare(name,recorded,current):
        state['recorded'][name]=recorded;state['current'][name]=current
        if current is None:state['missing'].append(name)
        elif recorded!=current:state['changed'].append(name)
    for key,(name,relative) in COMPOSITION_INPUTS.items():
        source=HERE/relative;current=digest(source) if source.exists() else None;recorded=composition.get(key)
        if key=='objectEditsSha256':
            # An absent edit file, and a composition made before edits existed, are both the empty edit set.
            current=EMPTY_SHA256 if current is None else current;recorded=EMPTY_SHA256 if recorded is None else recorded
        if recorded is None and current is None:continue
        compare(name,recorded,current)
    compare('compositionAlgorithm',composition.get('compositionAlgorithmSha256'),composition_algorithm_sha())
    compare('geometryDependencies',composition.get('geometryDependencies'),geometry_dependencies())
    try:
        snapshots={snapshot.document['regionId']:snapshot for snapshot in AUTHORING.load_snapshots()}
    except (OSError,ValueError) as error:
        state['missing'].append('continentAuthoring');state['current']['continentAuthoring']=str(error)
    else:
        authored=composition.get('continentAuthoring',{}).get('regions',{})
        compare('continentAuthoring.regions',sorted(authored),sorted(snapshots))
        for region,snapshot in snapshots.items():
            record=authored.get(region,{})
            compare(f'continentAuthoring.{region}.snapshot',record.get('snapshotSha256'),snapshot.digest)
            compare(f'continentAuthoring.{region}.sources',record.get('sources'),snapshot.bound_sources())
            contract=snapshot.contract
            compare(f'continentAuthoring.{region}.storage',record.get('storage'),{
                'serverOrigin':list(contract.server_origin),'serverCells':list(contract.server_cells),
                'serverStorageVersion':1,'serverTileMin':list(contract.server_tile_min),
                'authoringSpecSha256':contract.spec_sha256})
    sources={relative.replace('\\','/'):sha for relative,sha in composition.get('sources',{}).items()}
    for relative in sorted(shaping_source_keys()):
        source=CLIENT/relative;current=digest(source) if source.exists() else None
        if relative not in sources:
            state['recorded'][relative]=None;state['current'][relative]=current;state['missing'].append(relative)
        else:compare(relative,sources[relative],current)
    for key,value in sorted(composition.items()):
        if key.endswith('Sha256') and key not in COMPOSITION_INPUTS and key!='compositionAlgorithmSha256':
            state['unknown'].append(key);state['recorded'][key]=value;state['current'][key]=None
    state['fresh']=not (state['changed'] or state['missing'] or state['unknown'])
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path)
    parser.add_argument('--output',type=Path,default=HERE/'generated')
    parser.add_argument('--stage',choices=['prepare','geometry','all'],default='all')
    parser.add_argument('--freshness',action='store_true',help='Report whether the composition still matches its inputs, then exit: 0 fresh, 1 stale, 2 nothing composed')
    args=parser.parse_args()
    if args.freshness:
        state=composition_freshness(args.output);print(json.dumps(state,indent=2))
        raise SystemExit(0 if state['fresh'] else 1 if state['composed'] else 2)
    if args.library is None:parser.error('--library is required to compose or export')
    args.output.mkdir(parents=True,exist_ok=True)
    PROGRESS.attach(args.output/'progress.json').watch()
    if args.stage in ('prepare','all'):world,content=prepare(args.library.resolve(),args.output.resolve())
    else:world,content=load_composed(args.output.resolve(),args.library.resolve())
    if args.stage in ('geometry','all'):export_geometry(world,content,args.output.resolve())
    PROGRESS.finish(0)

if __name__=='__main__':main()
