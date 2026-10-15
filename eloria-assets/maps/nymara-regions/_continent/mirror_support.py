"""Local bank clearance beneath Mirrorhold decks and beside the City landing.

Apply after final road/ferry grading, before regrounding/scatter. Geometry and
the city's common translation are immutable. The old source survey includes
a small rise through the City link; lower structural sleepers are deliberately
ignored wherever the actual deck covers them.
"""
from __future__ import annotations
import math
import numpy as np
import landscape as L
import scene_io as S

LINKS=('Landmark_LakeLink_City','Landmark_LakeLink_Sanctuary')
GROUND_CLEARANCE=.06
GRID_APRON=math.sqrt(2)*2.
FEATHER=6.
CITY_TURNOUT_NAME='mirrorhold-city-quay-turnout'
CITY_TURNOUT_POLYGON=np.array(((891.,795.),(890.,792.),(891.,789.),(896.,789.),
                               (897.2,792.),(896.,795.),(895.25,796.5),(891.75,796.5)))
CITY_TURNOUT_FEATHER=3.
CITY_TURNOUT_MAX_CUT=4.
CITY_TURNOUT_ROAD_HALF_WIDTH=3.5
CITY_TURNOUT_ROAD_A=np.array((883.,795.77))
CITY_TURNOUT_ROAD_B=np.array((905.,793.))
CITY_TURNOUT_ROAD_HEIGHTS=(83.52,84.5)
CITY_TURNOUT_DECK_FLOOR=83.7
CITY_TURNOUT_LANDING_BLEND=1.5


def walking_triangles(content,obj):
    document,body=content.documents[obj['region']]
    indices=[i for i in S.descendants(document,obj.get('indices',[obj['index']])) if 'mesh' in document['nodes'][i]]
    triangles=S.GR.triangles(document,body,indices)+np.asarray(obj['shift'])
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    upward=normal[:,1]>.6*np.maximum(np.linalg.norm(normal,axis=1),1e-10)
    return triangles[upward]


def upper_floor_field(triangles,x,z):
    """Upper exposed floor and nearest footprint distance, including overlaps.

    At a covered point the upper triangle wins. Outside the footprint, project
    onto its actual edges; overlapping sleeper/deck boundaries keep the upper
    deck level instead of creating a false underground walking requirement.
    """
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    distance=np.full(x.shape,np.inf);height=np.full(x.shape,-np.inf)
    for a,b,c in np.asarray(triangles,float):
        ab=b[[0,2]]-a[[0,2]];ac=c[[0,2]]-a[[0,2]]
        det=ab[0]*ac[1]-ab[1]*ac[0]
        if abs(det)<1e-10:continue
        px,pz=x-a[0],z-a[2]
        u=(px*ac[1]-pz*ac[0])/det;v=(ab[0]*pz-ab[1]*px)/det
        inside=(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)
        d=np.where(inside,0.,np.inf)
        y=np.where(inside,a[1]+u*(b[1]-a[1])+v*(c[1]-a[1]),-np.inf)
        for start,end in ((a,b),(b,c),(c,a)):
            delta=end-start;length2=delta[0]**2+delta[2]**2
            if length2<1e-12:continue
            t=np.clip(((x-start[0])*delta[0]+(z-start[2])*delta[2])/length2,0,1)
            edge_distance=np.hypot(x-start[0]-t*delta[0],z-start[2]-t*delta[2])
            closer=edge_distance<d-1e-9
            y=np.where(closer,start[1]+t*delta[1],y);d=np.minimum(d,edge_distance)
        closer=d<distance-1e-8;equal=np.abs(d-distance)<=1e-8
        height=np.where(closer,y,np.where(equal,np.maximum(height,y),height))
        distance=np.minimum(distance,d)
    return height,distance


def sample_upper_clearance(world,triangles,step=.25):
    lo=triangles[:,:,[0,2]].min(axis=(0,1));hi=triangles[:,:,[0,2]].max(axis=(0,1))
    x,z=np.meshgrid(np.arange(lo[0],hi[0]+step*.5,step),np.arange(lo[1],hi[1]+step*.5,step))
    # Include actual vertices and centroids so a small shore triangle cannot
    # fall between the independent regular samples.
    extra=np.concatenate((triangles.reshape(-1,3),triangles.mean(axis=1)))
    x=np.r_[x.ravel(),extra[:,0]];z=np.r_[z.ravel(),extra[:,2]]
    floor,distance=upper_floor_field(triangles,x,z);inside=distance<1e-7
    x,z,floor=x[inside],z[inside],floor[inside]
    ground=world.height_at(x,z);burial=ground-floor
    worst=int(np.argmax(burial))
    return {'samples':len(x),'buriedSamples':int(np.count_nonzero(burial>.015)),
            'maximumBurial':float(np.max(burial,initial=0)),
            'minimumClearance':float(np.min(-burial)),
            'worstGlobal':[float(x[worst]),float(z[worst])],
            'worstFloor':float(floor[worst])}


def exposed_triangles(triangles):
    """Discard sleeper/support tops fully covered by the walking deck."""
    weights=np.array([[1/3,1/3,1/3],[.6,.2,.2],[.2,.6,.2],[.2,.2,.6]])
    samples=np.einsum('sj,tjk->tsk',weights,triangles)
    upper,_=upper_floor_field(triangles,samples[:,:,0],samples[:,:,2])
    return triangles[np.any(samples[:,:,1]>=upper-1e-6,axis=1)]


def _polygon_field(x,z,polygon=CITY_TURNOUT_POLYGON):
    """Inside mask and unsigned edge distance for one small convex apron."""
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    inside=np.zeros(x.shape,bool);distance=np.full(x.shape,np.inf)
    for index,start in enumerate(polygon):
        end=polygon[(index+1)%len(polygon)]
        crosses=(start[1]>z)!=(end[1]>z)
        at_x=(end[0]-start[0])*(z-start[1])/(end[1]-start[1]+1e-30)+start[0]
        inside^=crosses&(x<at_x)
        delta=end-start;length2=float(delta@delta)
        t=np.clip(((x-start[0])*delta[0]+(z-start[1])*delta[1])/length2,0,1)
        distance=np.minimum(distance,np.hypot(x-start[0]-t*delta[0],z-start[1]-t*delta[1]))
    return inside,distance


def _city_road_profile(x,z):
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    delta=CITY_TURNOUT_ROAD_B-CITY_TURNOUT_ROAD_A
    t=np.clip(((x-CITY_TURNOUT_ROAD_A[0])*delta[0]+(z-CITY_TURNOUT_ROAD_A[1])*delta[1])/
              float(delta@delta),0.,1.)
    near=CITY_TURNOUT_ROAD_A+t[...,None]*delta
    distance=np.hypot(x-near[...,0],z-near[...,1])
    height=CITY_TURNOUT_ROAD_HEIGHTS[0]+t*(CITY_TURNOUT_ROAD_HEIGHTS[1]-CITY_TURNOUT_ROAD_HEIGHTS[0])
    return distance,height,near[...,1]


def apply_city_quay_turnout(world):
    """Cut the pictured City landing mound into a bounded quay turnout."""
    polygon=CITY_TURNOUT_POLYGON
    low=polygon.min(axis=0)-CITY_TURNOUT_FEATHER-2
    high=polygon.max(axis=0)+CITY_TURNOUT_FEATHER+2
    if (high[0]<world.x[0] or low[0]>world.x[-1] or
            high[1]<world.z[0] or low[1]>world.z[-1]):
        return {'name':CITY_TURNOUT_NAME,'changedVertices':0,'maximumCut':0.,'maximumFill':0.,
                'changedWetVertices':0,'changedRoadCoreVertices':0}
    ix0,ix1=np.searchsorted(world.x,[low[0],high[0]],side='left')
    iz0,iz1=np.searchsorted(world.z,[low[1],high[1]],side='left')
    ix1=np.searchsorted(world.x,high[0],side='right');iz1=np.searchsorted(world.z,high[1],side='right')
    sl=np.s_[iz0:iz1,ix0:ix1];x,z=world.gx[sl],world.gz[sl]
    old=world.height[sl].copy();inside,edge=_polygon_field(x,z)
    weight=np.where(inside,1.,1-L.smoothstep(0.,CITY_TURNOUT_FEATHER,edge))
    dry=~world.water['mask'][sl]
    owned=world.owner_at(x,z)==world.ids.index('mirrorhold')
    distance,road_height,road_z=_city_road_profile(x,z)
    # Authored road vertices remain exact. Adjacent terrain triangles may
    # interpolate differently, which collision/access validation measures.
    weight*=dry&owned&(distance>CITY_TURNOUT_ROAD_HALF_WIDTH+1e-9)
    south=np.maximum(z-road_z,0.)
    landing=L.smoothstep(0.,CITY_TURNOUT_LANDING_BLEND,south)
    target=road_height*(1-landing)+CITY_TURNOUT_DECK_FLOOR*landing
    delta=np.minimum(target-old,0.)*weight
    requested_cut=np.maximum(-delta,0.)
    if float(requested_cut.max(initial=0))>CITY_TURNOUT_MAX_CUT+1e-9:
        raise ValueError(CITY_TURNOUT_NAME+': requested cut exceeds 4 m')
    updated=old+delta;changed=np.abs(delta)>1e-8
    cut=requested_cut;fill=np.maximum(delta,0.)
    changed_wet=changed&~dry;changed_road=changed&(distance<=CITY_TURNOUT_ROAD_HALF_WIDTH+1e-9)
    if fill.any():raise ValueError(CITY_TURNOUT_NAME+': cut-only repair attempted fill')
    if changed_wet.any():raise ValueError(CITY_TURNOUT_NAME+': wet terrain changed')
    if changed_road.any():raise ValueError(CITY_TURNOUT_NAME+': authored road vertex changed')
    world.height[sl]=updated
    world.assembly_target[sl]=np.where(changed,np.minimum(world.assembly_target[sl],updated),
                                       world.assembly_target[sl])
    return {'name':CITY_TURNOUT_NAME,'corePolygonGlobalXZ':polygon.tolist(),
            'featherMetres':CITY_TURNOUT_FEATHER,'changedVertices':int(changed.sum()),
            'maximumCut':float(cut.max(initial=0)),'maximumFill':float(fill.max(initial=0)),
            'changedWetVertices':int(changed_wet.sum()),
            'changedRoadCoreVertices':int(changed_road.sum()),
            'changedBounds':(None if not changed.any() else
                [[float(x[changed].min()),float(z[changed].min())],
                 [float(x[changed].max()),float(z[changed].max())]]),
            'assemblyTargetsLowered':int(np.count_nonzero(
                changed&(world.assembly_target[sl]<=updated+1e-9)))}


def apply_mirror_support(world,content):
    """Clear exposed link floors, then cut the adjacent bounded City turnout."""
    if 'mirrorhold' not in world.ids:return {}
    if 'mirrorhold' in getattr(world,'authoring_snapshots',{}):
        report={'region':'mirrorhold','skipped':'saved-authoring-authority'}
        world.mirror_support=report
        return report
    objects={o['node']:o for o in content.objects if o['region']=='mirrorhold'}
    reports=[]
    for name in LINKS:
        obj=objects.get(name)
        if obj is None or not obj['walk']:raise ValueError(name+': required retained walking link is missing')
        triangles=walking_triangles(content,obj)
        if not len(triangles):raise ValueError(name+': no upward retained walking surface')
        before=sample_upper_clearance(world,triangles)
        entry={'node':name,'before':before,'correctedVertices':0,'maximumCut':0.,'correctedAreaSquareMetres':0.}
        if before['buriedSamples']:
            low=triangles[:,:,[0,2]].min(axis=(0,1))-GRID_APRON-FEATHER
            high=triangles[:,:,[0,2]].max(axis=(0,1))+GRID_APRON+FEATHER
            ix0,iz0=np.maximum(0,np.floor((low-[world.x0,world.z0])/2).astype(int))
            ix1,iz1=np.minimum([len(world.x),len(world.z)],np.ceil((high-[world.x0,world.z0])/2).astype(int)+1)
            sl=np.s_[iz0:iz1,ix0:ix1]
            dry=~world.water['mask'][sl]
            old=world.height[sl].copy()
            updated=old.copy()
            visible=exposed_triangles(triangles)
            for face in visible:
                floor,distance=upper_floor_field(face[None,:,:],world.gx[sl],world.gz[sl])
                weight=(1-L.smoothstep(GRID_APRON,GRID_APRON+FEATHER,distance))*dry
                cap=floor-GROUND_CLEARANCE
                # Every terrain triangle touching a deck edge must stay below
                # that floor. A nearby higher rail cannot override this cap.
                updated=np.minimum(updated,old-weight*np.maximum(0,old-cap))
            cut=old-updated
            if float(cut.max(initial=0))>2.0:
                raise ValueError(name+': bank correction exceeds its bounded 2 m local repair; redesign the approach')
            changed=cut>1e-8
            world.height[sl]=updated
            world.assembly_target[sl]=np.where(changed,np.minimum(world.assembly_target[sl],updated),world.assembly_target[sl])
            entry.update(correctedVertices=int(changed.sum()),maximumCut=float(cut.max(initial=0)),
                         correctedAreaSquareMetres=float(changed.sum()*4),
                         exposedFloorTriangles=len(visible),
                         correctedBounds=[[float(world.gx[sl][changed].min()),float(world.gz[sl][changed].min())],
                                          [float(world.gx[sl][changed].max()),float(world.gz[sl][changed].max())]])
        entry['after']=sample_upper_clearance(world,triangles)
        if entry['after']['maximumBurial']>.015:
            raise ValueError(name+': actual upper walking floor remains buried after local bank repair')
        reports.append(entry)
    turnout=apply_city_quay_turnout(world)
    report={'policy':'Actual exposed upper link floors; bounded local dry bank cuts, unchanged city geometry and lake',
            'groundClearanceMetres':GROUND_CLEARANCE,'fullGridApronMetres':GRID_APRON,'featherMetres':FEATHER,
            'links':reports,'cityQuayTurnout':turnout}
    world.mirror_support=report
    return report
