"""Carry the three long outer approaches over the tide on stone spans.

The existing XZ routes, native bridges and shared causeways stay in place.
Only new visible deck/slab/curb/pier meshes are authored here, before the
connector contact pass. Channels remain open between the masonry piers.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import streaming_borders as SB
from verify_runtime import VerticalRayIndex
import connector_finish as F

ROADS=('mirrorhold-four-gates','four-gates-sunmane','four-gates-ssarathi')
HEIGHT=23.
HALF_WIDTH=4.25


def upward_top(mesh):
    """Native subtraction/ownership clipping must retain an upward floor."""
    faces=mesh.indices.reshape(-1,3)
    points=mesh.positions[faces]
    down=np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])[:,1]<0
    faces[down]=faces[down][:,[0,2,1]]
    mesh.recompute_normals(180)
    return mesh


def centres_for(road,spec):
    source=np.asarray(road['stations'],float)
    bank=np.asarray(spec['anchor'])[[0,2]]-np.asarray(spec['outward'])*42.
    index=int(np.linalg.norm(source[:,[0,2]]-bank,axis=1).argmin())
    if np.linalg.norm(source[index,[0,2]]-bank)>1e-6:raise ValueError('Missing exact native causeway end')
    points=source[:index+1].copy()
    # Collinear numerical stations are not additional bends. Retain every
    # actual course change and both surveyed endpoint positions.
    keep=[0]
    for i in range(1,len(points)-1):
        a=points[i,[0,2]]-points[keep[-1],[0,2]];b=points[i+1,[0,2]]-points[i,[0,2]]
        cross=a[0]*b[1]-a[1]*b[0]
        if abs(cross)>1e-7 or a@b<=0:keep.append(i)
    keep.append(len(points)-1)
    return points[keep]


def edges(centres,lateral,spec):
    xz=centres[:,[0,2]];direction=np.diff(xz,axis=0)
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    sides=np.c_[-direction[:,1],direction[:,0]];offsets=[sides[0]]
    for a,b in zip(sides,sides[1:]):
        bisector=a+b;den=float(bisector@b)
        if den<.1:raise ValueError('Tidal approach contains a reversing bend')
        offsets.append(bisector/den)
    # Meet the old slab on its exact transverse bank plane.
    f=np.asarray(spec['outward']);offsets.append(np.array([-f[1],f[0]]))
    return xz+np.asarray(offsets)*lateral


def deck_levels(centres):
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(centres[:,[0,2]],axis=0),axis=1))]
    t=np.clip(distance/4.,0,1);blend=1.-t*t*(3.-2.*t)
    return HEIGHT+(centres[0,1]-HEIGHT)*blend


def ribbon(centres,spec,a,b,offset,material):
    left,right=edges(centres,a,spec),edges(centres,b,spec);y=deck_levels(centres)+offset
    pieces=[]
    for i in range(len(centres)-1):
        q=M.quad([[left[i,0],y[i],left[i,1]],[left[i+1,0],y[i+1],left[i+1,1]],
                  [right[i+1,0],y[i+1],right[i+1,1]],[right[i,0],y[i],right[i,1]]],material=material)
        if q.normals[:,1].mean()<0:q.flip_winding();q.recompute_normals(180)
        q.uvs=q.positions[:,[0,2]]*.28;pieces.append(q)
    return M.merge(pieces,material)


def sides(centres,spec,a,b,bottom,top,material):
    underside=ribbon(centres,spec,a,b,bottom,material);underside.flip_winding();underside.recompute_normals(180)
    pieces=[underside];y=deck_levels(centres)
    for lateral in (a,b):
        line=edges(centres,lateral,spec)
        for i,(p,q) in enumerate(zip(line,line[1:])):
            face=M.quad([[p[0],y[i]+bottom,p[1]],[q[0],y[i+1]+bottom,q[1]],
                         [q[0],y[i+1]+top,q[1]],[p[0],y[i]+top,p[1]]],material=material)
            if lateral==a:face.flip_winding();face.recompute_normals(180)
            pieces.append(face)
    # Open ends mate to the original bridge/slab; no duplicate end walls.
    return M.merge(pieces,material)


def bank_landing(spec):
    """A short turning court fills the inside elbow at the old slab end."""
    f=np.asarray(spec['outward']);side=np.array([-f[1],f[0]])
    bank=np.asarray(spec['anchor'])[[0,2]]-f*42.
    corners=np.array([bank-f*4.25-side*4.25,bank-side*4.25,
                      bank+side*4.25,bank-f*4.25+side*4.25])
    top=M.quad([[p[0],HEIGHT,p[1]] for p in corners],material='cobble_paving')
    if top.normals[:,1].mean()<0:top.flip_winding();top.recompute_normals(180)
    top.uvs=top.positions[:,[0,2]]*.28
    bottom=top.copy();bottom.positions[:,1]-=.8;bottom.flip_winding();bottom.material='pale_ashlar'
    walls=[bottom]
    for i,j in ((0,1),(2,3),(3,0)):
        a,b=corners[i],corners[j]
        walls.append(M.quad([[a[0],HEIGHT,a[1]],[a[0],HEIGHT-.8,a[1]],
                             [b[0],HEIGHT-.8,b[1]],[b[0],HEIGHT,b[1]]],material='pale_ashlar'))
    return top,M.merge(walls,'pale_ashlar')


def apply(build):
    if getattr(build,'_four_tidal_approaches_added',False):raise ValueError('Tidal approaches added twice')
    native=F._native_walk(build)
    ground=VerticalRayIndex(F._triangles([m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_')]))
    native_ray=VerticalRayIndex(native);pieces={};reports=[]
    for identity in ROADS:
        road=next(r for r in build.geography_roads if r['id']==identity)
        spec=next(s for s in build.streaming_borders if s['id']==identity)
        centres=centres_for(road,spec);prefix='StreamCauseway_FourTidal_'+identity
        lo=centres[:,[0,2]].min(0)-8.;hi=centres[:,[0,2]].max(0)+8.
        mask=(native[:,:,0].max(1)>=lo[0])&(native[:,:,0].min(1)<=hi[0])&(native[:,:,2].max(1)>=lo[1])&(native[:,:,2].min(1)<=hi[1])
        mask&=(native[:,:,1].min(1)>HEIGHT-.5)&(native[:,:,1].max(1)<HEIGHT+.5)
        preserved=native[mask]
        top=ribbon(centres,spec,-HALF_WIDTH,HALF_WIDTH,0.,'cobble_paving')
        landing,landing_body=bank_landing(spec);landing_tri=F._triangles([landing])
        top=M.merge([F._subtract_native(top,landing_tri),landing],'cobble_paving')
        pieces['Walk_'+prefix]=F._subtract_native(top,preserved)
        body=[sides(centres,spec,-HALF_WIDTH,HALF_WIDTH,-.8,0.,'pale_ashlar')]
        for sign in (-1,1):
            a,b=sorted((sign*3.5,sign*3.88))
            body.extend((sides(centres,spec,a,b,-.08,.4,'pale_ashlar'),ribbon(centres,spec,a,b,.4,'pale_ashlar')))
        # Existing walking footprints also retain their own supporting slab
        # and curb junctions. Do not bury a duplicate body beneath them.
        body=M.merge([F._subtract_native(M.merge(body,'pale_ashlar'),landing_tri),landing_body],'pale_ashlar')
        pieces['Structure_'+prefix+'_ashlar']=F._subtract_native(body,preserved)
        distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(centres[:,[0,2]],axis=0),axis=1))]
        piers=[];contacts=[]
        for along in np.arange(6.,distance[-1]-2.,10.):
            i=min(int(np.searchsorted(distance,along,side='right')-1),len(centres)-2)
            t=(along-distance[i])/(distance[i+1]-distance[i]);q=centres[i,[0,2]]*(1-t)+centres[i+1,[0,2]]*t
            if native_ray.top_hit(*q) is not None:continue
            d=centres[i+1,[0,2]]-centres[i,[0,2]];d/=np.linalg.norm(d);side=np.array([-d[1],d[0]])
            samples=[ground.top_hit(*(q+d*a+side*b)) for a in (-.75,.75) for b in (-3.25,3.25)]
            if any(y is None for y in samples):raise ValueError('Tidal pier lacks native bed')
            bottom=min(samples)-.3;upper=HEIGHT-.7
            if bottom>=upper:continue
            pier=M.box((1.5,upper-bottom,6.5),material='rubble_stone')
            pier.rotate_y(np.arctan2(-d[1],d[0]));pier.translate(q[0],(bottom+upper)/2,q[1]);piers.append(pier)
            contacts.append({'xz':q.tolist(),'bottom':bottom,'bedHeights':samples})
        if piers:pieces['Structure_'+prefix+'_piers']=M.merge(piers,'rubble_stone')
        road['tidalCrossing']={'nativeDeck':'Walk_'+prefix,'height':HEIGHT,'lengthMetres':float(distance[-1]),'centres':centres[:,[0,2]].tolist(),'clearWidth':7.,'outerWidth':8.5,'piers':contacts}
        reports.append({'id':identity,**road['tidalCrossing']})
    frames=deepcopy(build.streaming_borders)
    for s in frames:s['sceneNodes']=[]
    extra=SimpleNamespace(terrain_meshes=pieces,water_meshes={},placements=[])
    SB.partition_shared_approaches(extra,frames)
    record=G.plan()['regions']['four_gates'];polygon=np.asarray(record['ownershipPolygon'])-np.asarray(record['translation'])[[0,2]]
    rectangles=G.polygon_rectangles(polygon)
    for name,mesh in extra.terrain_meshes.items():
        mesh=G.clip_owned_mesh(mesh,rectangles)
        if name.startswith('Walk_StreamCauseway_FourTidal_'):
            upward_top(mesh)
        if mesh.triangle_count:build.terrain_meshes[name]=mesh
    for frame in frames:
        destination=next(s for s in build.streaming_borders if s['id']==frame['id'])
        destination['sceneNodes'].extend(n for n in frame['sceneNodes'] if n in build.terrain_meshes and n not in destination['sceneNodes'])
    build._four_tidal_approaches_added=True
    build.tidal_approaches=reports
    build.notes.append('The north, east and south approaches cross tidal channels on stone spans at the city causeway datum, with open water between grounded masonry piers.')
    return reports
