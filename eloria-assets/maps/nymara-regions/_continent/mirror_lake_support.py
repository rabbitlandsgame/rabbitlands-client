"""Fit Mirror Lake into a physical basin without changing its water datum.

The retained city's seabed survey reaches beyond the lake's hydraulic domain.
A local shore shelf closes that exposed edge and blends back into the hillside.
The western outlet, rigid architecture and their actual walking floors remain
authoritative. Prepare before road planning; restore the same shore after the
generic original-drainage pass, which otherwise reinstates the old lake edge.
"""
from __future__ import annotations
import numpy as np
import landscape as L
import scene_io as S
from manymouth_support import upper_floor
from world_layout import triangle_sample

REGION='mirrorhold'
SHORE_HEIGHT=.30
SHORE_GRADE=.15
INNER_OUTER_CORE=8.
FEATHER=40.
FLOOR_CLEARANCE=.06


def shore_fields(x,z,height,lake,outlet):
    """A submerged beach, low bank crown and broad outer hillside shoulder."""
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    distance=(L._ellipse_distance(x,z,lake)-1)*min(lake['radii'])
    weight=1-L.smoothstep(INNER_OUTER_CORE,FEATHER,abs(distance))
    target=float(lake['level'])+SHORE_HEIGHT+SHORE_GRADE*np.clip(distance,-8,8)
    river_distance=L._polyline_field(
        x,z,outlet['points'],outlet.get('authoredSampled',False))[0]
    # Keep the actual western outfall and its two natural banks. The taper
    # opens into the basin, avoiding a radial dam across the outgoing stream.
    start=np.asarray(outlet['points'][0][:2],float)
    next_point=np.asarray(outlet['points'][1][:2],float)
    outward=(next_point-start)/np.linalg.norm(next_point-start)
    into_lake=-((x-start[0])*outward[0]+(z-start[1])*outward[1])
    opening=(1-L.smoothstep(outlet['width']+1,outlet['width']+9,river_distance))*(1-L.smoothstep(0,12,into_lake))
    weight*=1-opening
    updated=np.asarray(height,float)+weight*np.maximum(0,target-height)
    # The flared outlet banks are part of the prepared beach too. Restoring
    # only the fully closed arc lets the generic natural-bed pass reopen a
    # tiny breach in this smooth transition. A fully open channel has zero
    # weight and remains untouched; retain the partial bank fill around it.
    core=(abs(distance)<=INNER_OUTER_CORE)&(opening<1.-1e-10)
    return updated,weight,core,opening,distance


def retained_walks(content,bounds):
    document,body=content.documents[REGION]
    result=[];groups=[]
    for obj in content.objects:
        if obj.get('region')!=REGION or 'source' not in obj:continue
        if np.any(obj['high'][[0,2]]<bounds[0]) or np.any(obj['low'][[0,2]]>bounds[1]):continue
        roots=obj.get('indices',[obj['index']])
        indices=[i for i in S.descendants(document,roots) if 'mesh' in document['nodes'][i]
                 and document['nodes'][i].get('name','').startswith('Walk_')]
        if indices:
            faces=S.GR.triangles(document,body,indices)+obj['shift']
            normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
            faces=faces[normal[:,1]>np.linalg.norm(normal,axis=1)/np.sqrt(1+.65**2)]
            result.extend(faces);groups.append((obj['node'],faces))
    return np.asarray(result,float).reshape(-1,3,3),groups


def floor_samples(triangles):
    """Independent sub-metre exposed-floor samples, including real edges."""
    if not len(triangles):return np.empty((0,2)),np.empty(0)
    lo=triangles[:,:,[0,2]].min(axis=(0,1));hi=triangles[:,:,[0,2]].max(axis=(0,1))
    x,z=np.meshgrid(np.arange(lo[0],hi[0]+.25,.5),np.arange(lo[1],hi[1]+.25,.5))
    extra=np.concatenate((triangles.reshape(-1,3),triangles.mean(axis=1)))
    points=np.r_[np.c_[x.ravel(),z.ravel()],extra[:,[0,2]]]
    floor=upper_floor(points,triangles);valid=np.isfinite(floor)
    return points[valid],floor[valid]


def floor_clearance(world,points,floor,reference=None):
    if not len(floor):return {'samples':0,'newlyBuriedSamples':0,'maximumBurial':0.}
    ground=world.height_at(points[:,0],points[:,1]);burial=ground-floor
    report={'samples':len(floor),'buriedSamples':int((burial>.015).sum()),
            'maximumBurial':float(np.max(burial,initial=0)),
            'minimumClearance':float(np.min(-burial)),
            'worstGlobalXZ':points[int(np.argmax(burial))].tolist()}
    if reference is not None:
        added=np.maximum(0,burial)-np.maximum(0,np.asarray(reference)-floor)
        report.update(newlyBuriedSamples=int(((burial>.015)&(added>.015)).sum()),
            maximumAddedBurial=float(np.max(added,initial=0)),
            addedBurialWorstGlobalXZ=points[int(np.argmax(added))].tolist(),
            addedBurialWorstFloor=float(floor[int(np.argmax(added))]))
    return report


def fit_below_floors(world,slices,target,points,floors):
    """Limit the proposed fill by actual floor/terrain triangle intersections.

    A floor sample constrains the same three shared terrain vertices used by
    collision. Lower only their proposed fill, leaving old ground unchanged.
    Applying the minimum ratio to every contributor satisfies all samples in
    one monotone pass and avoids a rectangular no-fill gap around the walkway.
    """
    iz0,iz1,ix0,ix1=slices;old=world.height[iz0:iz1,ix0:ix1]
    x0,z0=float(world.x[ix0]),float(world.z[iz0]);nz,nx=old.shape
    valid=(points[:,0]>=x0)&(points[:,0]<=world.x[ix1-1])&(points[:,1]>=z0)&(points[:,1]<=world.z[iz1-1])
    points,floors=points[valid],floors[valid]
    if not len(points):return target,0
    sx=(points[:,0]-x0)/2.;sz=(points[:,1]-z0)/2.
    ix=np.clip(np.floor(sx).astype(int),0,nx-2);iz=np.clip(np.floor(sz).astype(int),0,nz-2)
    u,v=sx-ix,sz-iz;a=iz*nx+ix;lower=u+v<=1
    indices=np.where(lower[:,None],np.c_[a,a+1,a+nx],np.c_[a+nx+1,a+nx,a+1])
    weights=np.where(lower[:,None],np.c_[1-u-v,u,v],np.c_[u+v-1,1-u,1-v])
    before=(old.ravel()[indices]*weights).sum(axis=1)
    delta=np.maximum(0,target-old).ravel()
    fill=(delta[indices]*weights).sum(axis=1)
    allowed=np.maximum(0,floors-FLOOR_CLEARANCE-before)
    factor=np.minimum(1.,allowed/np.maximum(fill,1e-12))
    factor=np.where(fill>allowed+1e-9,factor,1.)
    scale=np.ones(len(delta));contributes=weights>1e-12
    np.minimum.at(scale,indices[contributes],np.broadcast_to(factor[:,None],indices.shape)[contributes])
    return old+(delta*scale).reshape(old.shape),int((factor<1).sum())


def shoreline_proof(world,lake,outlet):
    """The actual water-domain rim must have a bank, except its open outfall."""
    angles=np.arange(0.,360.,1.)*np.pi/180
    ca,sa=np.cos(lake.get('angle',0)),np.sin(lake.get('angle',0))
    rx,rz=lake['radii'];records=[]
    for offset in (0.,.25,2.,5.):
        u=(rx+offset)*np.cos(angles);v=(rz+offset)*np.sin(angles)
        x=lake['center'][0]+u*ca-v*sa;z=lake['center'][1]+u*sa+v*ca
        ground=world.height_at(x,z)
        _,_,_,opening,_=shore_fields(x,z,ground,lake,outlet)
        # A hydraulic outlet is an intentional break in the enclosing bank.
        # Record its ground separately rather than treating it as a sealed rim.
        closed=opening<.01
        below=closed&(ground<float(lake['level'])-.015)
        records.append({'outwardOffsetMetres':offset,'closedBankSamples':int(closed.sum()),
            'belowLakeDatumSamples':int(below.sum()),
            'uncontainedWaterEdgeSamples':int(below.sum()) if offset<=2. else 0,
            'sampleRole':'contained shoreline' if offset<=2. else 'outer retaining slope toward lower city',
            'minimumClosedBankHeight':float(ground[closed].min()),
            'worstGlobalXZ':[float(x[closed][np.argmin(ground[closed])]),float(z[closed][np.argmin(ground[closed])])]})
    return records


def prepare_mirror_lake_support(world,content):
    if REGION not in world.ids:return {}
    if REGION in getattr(world,'authoring_snapshots',{}):
        report={'region':REGION,'skipped':'saved-authoring-authority'}
        world.mirror_lake_support=report
        return report
    lake=next(q for q in world.plan['lakes'] if q.get('name')=='Mirror Lake')
    outlet=next(q for q in world.plan['rivers'] if q['id']=='mirror_outlet')
    # Conservative bounds for the ellipse and its geographical shoulder.
    margin=max(lake['radii'])+FEATHER*max(lake['radii'])/min(lake['radii'])+4
    center=np.asarray(lake['center']);low=center-margin;high=center+margin
    ix0,iz0=np.maximum(0,np.floor((low-[world.x0,world.z0])/2).astype(int))
    ix1,iz1=np.minimum([len(world.x),len(world.z)],np.ceil((high-[world.x0,world.z0])/2).astype(int)+1)
    sl=np.s_[iz0:iz1,ix0:ix1];old=world.height[sl].copy()
    target,weight,core,opening,distance=shore_fields(world.gx[sl],world.gz[sl],old,lake,outlet)
    triangles,groups=retained_walks(content,(low,high))
    floor_points,floors=floor_samples(triangles)
    target,limited_samples=fit_below_floors(world,(iz0,iz1,ix0,ix1),target,floor_points,floors)
    before_ground=world.height_at(floor_points[:,0],floor_points[:,1])
    before=floor_clearance(world,floor_points,floors)
    initial_shore=shoreline_proof(world,lake,outlet)
    changed=target>old+1e-8
    world.height[sl]=target
    after=floor_clearance(world,floor_points,floors,before_ground)
    if after.get('newlyBuriedSamples',0):
        world.height[sl]=old
        raise ValueError('Mirror Lake shore would bury an actual retained walkway; redesign its bank contact: '+str(after))
    world.assembly_target[sl]=np.where(changed,target,world.assembly_target[sl])
    # Pin the low crown, not the entire restored city shelf. Streets can still
    # regrade the broad outer shoulder, while a crossing cannot drain the lake.
    protect=changed&core
    world.assembly_weight[sl]=np.where(protect,1.,world.assembly_weight[sl])
    if hasattr(world,'road_footing_weight'):
        world.road_footing_weight[sl]=np.where(protect,1.,world.road_footing_weight[sl])
    world.mirror_lake_shore_state={'slice':(int(iz0),int(iz1),int(ix0),int(ix1)),
        'target':target,'changed':changed,'core':core,'opening':opening,
        'floorPoints':floor_points,'floors':floors,'beforeGround':before_ground,'beforeFloor':before}
    report={'policy':'Physical bank around the unchanged80m lake; open western outlet; rigid city and exposed walking floors retained.',
        'lakeLevel':float(lake['level']),'coreMetres':INNER_OUTER_CORE,'featherMetres':FEATHER,
        'changedTerrainVertices':int(changed.sum()),'maximumFill':float((target-old).max(initial=0)),
        'floorConstrainedSamples':limited_samples,
        'beforeShore':initial_shore,'afterShore':shoreline_proof(world,lake,outlet),
        'beforeFloor':before,'afterFloor':after}
    world.mirror_lake_support=report
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    return report


def finish_mirror_lake_support(world,content):
    """Restore the prepared underwater beach after generic drainage grading."""
    if REGION in getattr(world,'authoring_snapshots',{}):
        return getattr(world,'mirror_lake_support',
                       {'region':REGION,'skipped':'saved-authoring-authority'})
    state=getattr(world,'mirror_lake_shore_state',None)
    if state is None:return {}
    iz0,iz1,ix0,ix1=state['slice'];sl=np.s_[iz0:iz1,ix0:ix1]
    # The prepared full core includes the inward beach. Original drainage
    # restoration must not pull that beach eleven metres below its bank again.
    use=state['changed']&state['core']
    before=world.height[sl].copy()
    world.height[sl]=np.where(use,np.maximum(before,state['target']),before)
    after=floor_clearance(world,state['floorPoints'],state['floors'],state['beforeGround'])
    if after.get('newlyBuriedSamples',0):
        raise ValueError('Final Mirror Lake shore buries a retained walkway')
    lake=next(q for q in world.plan['lakes'] if q.get('name')=='Mirror Lake')
    outlet=next(q for q in world.plan['rivers'] if q['id']=='mirror_outlet')
    shore=shoreline_proof(world,lake,outlet)
    if any(q['uncontainedWaterEdgeSamples'] for q in shore):
        raise ValueError('Mirror Lake still has a suspended closed water edge: '+str(shore))
    world.mirror_lake_support.update(finalShore=shore,finalFloor=after,
        finalRestoredVertices=int((world.height[sl]>before+1e-8).sum()))
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    return world.mirror_lake_support
