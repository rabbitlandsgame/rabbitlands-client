"""Root the woodland roads' stream crossings and span the western inlet.

These are measured bridges along the existing public routes. The low tower
threshold, two short creek spans and timber inlet bridge keep all old water,
walking meshes, structures and continental endpoints in place.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import streaming_borders as SB
import connector_finish as F
from verify_runtime import VerticalRayIndex

# Distances follow each authored local approach, including its tower bypass.
CROSSINGS = (
    dict(id='tower-rill', road='amberwood-whitehorn', start=-1.25, end=3.,
         levels=(49.48,49.90), deck='cobble_paving', body='ashlar', spacing=4.),
    dict(id='north-burn', road='amberwood-whitehorn', start=99., end=113.,
         levels=(60.5,60.5), deck='cobble_paving', body='ashlar', spacing=8.),
    dict(id='moor-inlet', road='amberwood-grey', start=188., end=282.,
         levels=(3.5,4.2), deck='timber_warm', body='timber_grey', spacing=10.),
    dict(id='cinder-rill', road='amberwood-mirrorhold', start=40., end=53.,
         levels=(29.7,29.7), deck='cobble_paving', body='ashlar', spacing=8.),
)
HALF_WIDTH=4.25
THICKNESS=.8


def course(road, spec):
    controls=np.asarray(road.get('contactStations',road['stations']),float)
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(controls[:,[0,2]],axis=0),axis=1))]
    a,b=spec['start'],spec['end']
    samples=np.unique(np.r_[np.linspace(a,b,int(np.ceil((b-a)/1.5))+1),
                           distance[(distance>a)&(distance<b)]])
    samples=samples[np.r_[True,np.diff(samples)>1e-6]]
    points=np.column_stack([np.interp(samples,distance,controls[:,i]) for i in (0,2)])
    before=samples<0
    if before.any():
        direction=controls[1,[0,2]]-controls[0,[0,2]]
        direction/=np.linalg.norm(direction)
        points[before]=controls[0,[0,2]]+samples[before,None]*direction
    levels=np.interp(samples,[a,b],spec['levels'])
    return samples,points,levels


def edges(points,lateral):
    direction=np.diff(points,axis=0)
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    sides=np.c_[-direction[:,1],direction[:,0]]
    offsets=[sides[0]]
    for a,b in zip(sides,sides[1:]):
        bisector=a+b;denominator=float(bisector@b)
        if denominator<.1:raise ValueError('Water crossing contains a reversing bend')
        offsets.append(bisector/denominator)
    offsets.append(sides[-1])
    return points+np.asarray(offsets)*lateral


def ribbon(left,right,levels,material):
    parts=[]
    for i in range(len(left)-1):
        part=M.quad([[left[i,0],levels[i],left[i,1]],
                     [left[i+1,0],levels[i+1],left[i+1,1]],
                     [right[i+1,0],levels[i+1],right[i+1,1]],
                     [right[i,0],levels[i],right[i,1]]],material=material)
        if part.normals[:,1].mean()<0:part.flip_winding();part.recompute_normals(180)
        part.uvs=part.positions[:,[0,2]]*.28
        parts.append(part)
    return M.merge(parts,material)


def masonry(left,right,levels,material):
    underside=ribbon(left,right,levels-THICKNESS,material)
    underside.flip_winding();underside.recompute_normals(180)
    parts=[underside]
    for line,reverse in ((left,False),(right,True)):
        for i in range(len(line)-1):
            p,q=line[i],line[i+1]
            face=M.quad([[p[0],levels[i],p[1]],[p[0],levels[i]-THICKNESS,p[1]],
                         [q[0],levels[i+1]-THICKNESS,q[1]],[q[0],levels[i+1],q[1]]],material=material)
            if reverse:face.flip_winding();face.recompute_normals(180)
            parts.append(face)
    for i,reverse in ((0,True),(-1,False)):
        p,q=left[i],right[i];y=levels[i]
        face=M.quad([[p[0],y,p[1]],[p[0],y-THICKNESS,p[1]],
                     [q[0],y-THICKNESS,q[1]],[q[0],y,q[1]]],material=material)
        if reverse:face.flip_winding();face.recompute_normals(180)
        parts.append(face)
    return M.merge(parts,material)


def apply(build):
    if getattr(build,'_amber_water_crossings_added',False):
        raise ValueError('Amberwood water crossings added twice')
    native=F._native_walk(build)
    ground=VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items() if F._base(n)]))
    pieces={};reports=[]
    for spec in CROSSINGS:
        road=next(r for r in build.geography_roads if r['id']==spec['road'])
        samples,points,levels=course(road,spec)
        left,right=edges(points,-HALF_WIDTH),edges(points,HALF_WIDTH)
        top=ribbon(left,right,levels,spec['deck'])
        body=masonry(left,right,levels,spec['body'])
        if len(native):
            lo=top.positions.min(0);hi=top.positions.max(0)
            near=(native.max(1)>=lo-[0,.35,0]).all(1)&(native.min(1)<=hi+[0,.35,0]).all(1)
            preserved=native[near]
            if len(preserved):
                top=F._subtract_native(top,preserved)
                body=F._subtract_native(body,preserved)
        prefix='StreamBridge_Amber_'+spec['id']
        pieces['Walk_'+prefix]=top
        pieces['Structure_'+prefix+'_slab']=body
        distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
        contacts=[];piers=[]
        # Bank abutments close the ends; open gaps remain between river piers.
        positions=np.unique(np.r_[.35,np.arange(4.,distance[-1]-2.,spec['spacing']),distance[-1]-.35])
        for along in positions:
            i=min(int(np.searchsorted(distance,along,side='right')-1),len(points)-2)
            i=max(0,i);t=(along-distance[i])/(distance[i+1]-distance[i])
            q=points[i]*(1-t)+points[i+1]*t
            direction=points[i+1]-points[i];direction/=np.linalg.norm(direction)
            side=np.array([-direction[1],direction[0]])
            bed=[ground.top_hit(*(q+direction*a+side*b)) for a in (-.5,.5) for b in (-3.25,3.25)]
            if any(y is None for y in bed):raise ValueError('Woodland crossing has no physical bed')
            bottom=min(bed)-.25;upper=float(np.interp(along,distance,levels))-.7
            if bottom>=upper:continue
            pier=M.box((1.,upper-bottom,6.5),material='rubble_stone')
            pier.rotate_y(np.arctan2(-direction[1],direction[0]))
            pier.translate(q[0],(bottom+upper)/2,q[1]);piers.append(pier)
            contacts.append(dict(xz=q.tolist(),bottom=bottom,bedHeights=bed,top=upper))
        if piers:pieces['Structure_'+prefix+'_supports']=M.merge(piers,'rubble_stone')
        report=dict(id=spec['id'],road=spec['road'],start=spec['start'],end=spec['end'],
                    levels=list(spec['levels']),outerWidth=8.5,clearWidth=8.5,thickness=.8,
                    centres=points.tolist(),piers=contacts)
        road.setdefault('waterCrossings',[]).append(report)
        reports.append(report)
    frames=deepcopy(build.streaming_borders)
    for frame in frames:frame['sceneNodes']=[]
    extra=SimpleNamespace(terrain_meshes=pieces,water_meshes={},placements=[])
    SB.partition_shared_approaches(extra,frames)
    record=G.plan()['regions']['amberwood']
    polygon=np.asarray(record['ownershipPolygon'])-np.asarray(record['translation'])[[0,2]]
    rectangles=G.polygon_rectangles(polygon)
    for name,mesh in extra.terrain_meshes.items():
        mesh=G.clip_owned_mesh(mesh,rectangles)
        if not mesh.triangle_count:continue
        if name.startswith('Walk_'):
            # Polygon subtraction may reverse individual fragments. Navigation
            # rasterizes upward faces, so normalise the actual indexed tops.
            faces=mesh.indices.reshape(-1,3)
            triangles=mesh.positions[faces]
            downward=np.cross(triangles[:,1]-triangles[:,0],
                              triangles[:,2]-triangles[:,0])[:,1]<0
            faces[downward]=faces[downward][:,[0,2,1]]
            mesh.recompute_normals(180)
        build.terrain_meshes[name]=mesh
    for frame in frames:
        target=next(s for s in build.streaming_borders if s['id']==frame['id'])
        target['sceneNodes'].extend(n for n in frame['sceneNodes'] if n in build.terrain_meshes and n not in target['sceneNodes'])
    build._amber_water_crossings_added=True
    build.amber_water_crossings=reports
    build.notes.append('Low stone rill crossings keep the tower and Cinder road dry; a timber span carries the Moor road across the inlet without filling its channel.')
    return reports
