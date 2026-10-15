"""White-only broad southern banks, derived from native ground and fixed roads.

The two new high approaches share one elliptic terrain field. Their narrow
walking ribbons remain unchanged; the valley rises over a connected hillside
instead of a ten-metre roadside pedestal. No previous package is an input.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.interpolate import RegularGridInterpolator
import connector_finish as F

REGION='whitehorn_range'
ROAD_IDS={'amberwood-whitehorn','whitehorn-mirrorhold'}

def movable_detail(build):
    linked={r.get('node') for key in ('landmarks','interactives','npc_markers','harvestables','portals','spawns') for r in getattr(build,key,[]) if r.get('node')}
    return {p.node for p in build.placements if p.node not in linked and not p.landmark and p.node in ('Prop_waystone_011','Prop_waystone_012')}

def protected_footings(build):
    original=build.placements;movable=movable_detail(build)
    try:
        build.placements=[p for p in original if p.node not in movable]
        return F._footing_polygons(build)
    finally:build.placements=original

def smooth(value):
    value=np.clip(value,0.,1.);return value*value*(3.-2.*value)

def _distance(points,roads):
    result=np.full(len(points),np.inf)
    for road in roads:
        value,_=F.G._road_coordinates(points,np.asarray(road['stations'])[:,[0,2]])
        result=np.minimum(result,value)
    return result

def _refine(mesh,roads):
    """Edge-local cuts agree across distinct material and StreamCell meshes."""
    values=np.c_[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:values=np.c_[values,mesh.colors]
    faces=mesh.indices.reshape(-1,3)
    for _ in range(8):
        ends=np.stack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]],axis=1)
        p=values[ends,:3][:,:,:,[0,2]];mid=p.mean(axis=2).reshape(-1,2)
        length=np.linalg.norm(p[:,:,1]-p[:,:,0],axis=2).ravel()
        near=_distance(mid,roads)
        split=((near<73.+length*.5)&(mid[:,1]>12.-length*.5)&(length>1.4)).reshape(-1,3)
        if not split.any():break
        mids=(values[ends[:,:,0]]+values[ends[:,:,1]])*.5
        ids=np.full(split.shape,-1,int);ids[split]=np.arange(len(values),len(values)+split.sum())
        values=np.concatenate([values,mids[split]])
        codes=split@np.array([1,2,4]);vertices=np.c_[faces,ids];parts=[]
        templates={0:((0,1,2),),1:((0,3,2),(3,1,2)),2:((1,4,0),(4,2,0)),4:((2,5,1),(5,0,1)),
            3:((3,1,4),(0,3,4),(0,4,2)),6:((4,2,5),(1,4,5),(1,5,0)),
            5:((5,0,3),(2,5,3),(2,3,1)),7:((0,3,5),(3,1,4),(5,4,2),(3,4,5))}
        for code,triples in templates.items():
            selected=vertices[codes==code];parts.extend(selected[:,t] for t in triples)
        faces=np.concatenate(parts)
    mesh.positions,mesh.normals,mesh.uvs=values[:,:3],values[:,3:6],values[:,6:8]
    if mesh.colors is not None:mesh.colors=values[:,8:12]
    mesh.indices=faces.ravel()

def apply(build,native_snapshot):
    if getattr(build,'white_broad_landform_audit',None):raise ValueError('White landform applied twice')
    roads=[r for r in build.geography_roads if r['id'] in ROAD_IDS]
    if len(roads)!=2:raise ValueError('White southern approaches are missing')
    bases={n:m for n,m in build.terrain_meshes.items() if F._base(n) and m.triangle_count}
    before=F.VerticalRayIndex(F._triangles(list(bases.values())))
    native=F.VerticalRayIndex(F._native_walk(build));footings=protected_footings(build)
    water_triangles=F._triangles(list(build.water_meshes.values()))
    water=F.VerticalRayIndex(water_triangles) if len(water_triangles) else None
    # This deliberately regional window includes both shoulders and the
    # saddle between the roads. Native mountain peaks north of it stay fixed.
    xs=np.arange(-195.,81.,1.);zs=np.arange(10.,146.,1.)
    gx,gz=np.meshgrid(xs,zs);xz=np.c_[gx.ravel(),gz.ravel()]
    old=np.array([before.top_hit(*p) for p in xz],object)
    original=np.array([native_snapshot.native_ray.top_hit(*p) for p in xz],object)
    present=np.array([v is not None for v in old]);valid_native=np.array([v is not None for v in original])
    old=np.array([float(v) if v is not None else 0. for v in old])
    original=np.array([float(v) if v is not None else old[i] for i,v in enumerate(original)])
    distance=_distance(xz,roads);edge=F.R._edge_distance(build,REGION,xz)
    def protection(points):
        result=np.full(len(points),np.inf)
        for polygon in footings:
            near=np.all(points>=polygon.min(axis=0)-6.,axis=1)&np.all(points<=polygon.max(axis=0)+6.,axis=1)
            if near.any():result[near]=np.minimum(result[near],F._footing_distance(points[near],polygon))
        return result
    protect=protection(xz)
    native_floor=np.array([native.top_hit(*p) for p in xz],object)
    native_covered=np.array([v is not None for v in native_floor])
    wet=np.array([water.top_hit(*p) is not None for p in xz]) if water is not None else np.zeros(len(xz),bool)
    allowed=present&valid_native&(distance<70.)&(xz[:,1]>15.)&(edge>5.)&(distance>5.5)&(protect>1.8)&~native_covered&~wet
    allowed=allowed.reshape(gx.shape);allowed[[0,-1],:]=False;allowed[:,[0,-1]]=False;allowed=allowed.ravel()
    # A weak native-height term retains broad regional relief while the
    # connected solve spreads the road uplift through both banks together.
    ids=np.flatnonzero(allowed);lookup=np.full(len(old),-1,int);lookup[ids]=np.arange(len(ids))
    lam=1./45.**2;rhs=original[ids]*lam;rr=[];cc=[];vv=[]
    rr.extend(range(len(ids)));cc.extend(range(len(ids)));vv.extend(np.full(len(ids),4.+lam))
    for delta in (-1,1,-len(xs),len(xs)):
        neighbor=ids+delta;free=allowed[neighbor]
        rr.extend(np.flatnonzero(free));cc.extend(lookup[neighbor[free]]);vv.extend(np.full(free.sum(),-1.))
        rhs[~free]+=old[neighbor[~free]]
    target=old.copy();target[ids]=spsolve(coo_matrix((vv,(rr,cc)),shape=(len(ids),len(ids))).tocsr(),rhs)
    field=RegularGridInterpolator((zs,xs),target.reshape(gx.shape),bounds_error=False,fill_value=np.nan)
    contact_cache={}
    def shape(points):
        out=points.copy();p=points[:,[0,2]];d=_distance(p,roads)
        weight=smooth((d-5.5)/.75)*smooth((F.R._edge_distance(build,REGION,p)-3.1)/4.)
        weight*=smooth((70.-d)/5.)*smooth((p[:,1]-15.)/5.)
        weight*=smooth((protection(p)-.9)/2.)
        desired=field(p[:,[1,0]]);desired[~np.isfinite(desired)]=points[~np.isfinite(desired),1]
        change=(desired-points[:,1])*weight
        for i in np.flatnonzero(abs(change)>1e-8):
            key=tuple(np.round(p[i],7))
            if key not in contact_cache:
                contact_cache[key]=(native.top_hit(*p[i]) is not None or (water is not None and water.top_hit(*p[i]) is not None))
            if contact_cache[key]:change[i]=0.
        out[:,1]+=change;return out
    paint={n:m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_') and not F._base(n) and ('_StreamCollar_' in n or '_ContinentBlend_' in n)}
    old_bases={}
    for n,m in bases.items():old_bases.setdefault(F.substrate_name(n),[]).append(m.copy())
    old_samplers={n:F.Substrate(ms) for n,ms in old_bases.items()}
    old_positions={p.node:tuple(p.position) for p in build.placements}
    # Actual terrain contact is used for scatter offsets; fixed/linked props
    # and structures are excluded by the established content classification.
    scatter=[]
    movable=movable_detail(build)
    for p in build.placements:
        if F.G._is_scatter(p) or p.node in movable:
            height=before.top_hit(p.position[0],p.position[2])
            if height is not None:scatter.append((p,height))
    counts={}
    for n,m in bases.items():
        initial=m.triangle_count;_refine(m,roads);m.positions=shape(m.positions);m.recompute_normals(180)
        counts[n]=[initial,m.triangle_count]
    new_bases={}
    for n,m in bases.items():new_bases.setdefault(F.substrate_name(n),[]).append(m)
    new_samplers={n:F.Substrate(ms) for n,ms in new_bases.items()}
    order=[s['id'] for s in build.streaming_borders if any(F.collar_layers(n) and F.collar_layers(n)[-1][0]==s['id'] for n in paint)]
    slots={n:i for i,n in enumerate(order)}
    peers=sorted({p for e in F.G.boundary_segments(REGION) for p in e['regions'] if p!=REGION})
    for n,m in paint.items():
        if not m.triangle_count:continue
        _refine(m,roads);base=F.substrate_name(n);p=m.positions[:,[0,2]]
        # The inherited paint can itself carry a coarse interpolated offset
        # after several sculpt passes. Re-seat affected direct paint at its
        # declared layer bias, preserving masks/UVs and the shared band.
        influence=smooth((70.-_distance(p,roads))/5.)*smooth((p[:,1]-15.)/5.)
        influence*=smooth((F.R._edge_distance(build,REGION,p)-3.1)/4.)
        intended=new_samplers[base].sample(p)+F.paint_bias(n,slots,peers)
        m.positions[:,1]+=(intended-m.positions[:,1])*influence;m.recompute_normals(180)
    after=F.VerticalRayIndex(F._triangles(list(bases.values())))
    moved=[]
    for p,height in scatter:
        now=after.top_hit(p.position[0],p.position[2])
        if now is not None and abs(now-height)>1e-7:
            p.position=(p.position[0],p.position[1]+now-height,p.position[2]);moved.append(p.node)
    t=build.terrain;points=np.c_[t.gx.ravel(),t.height.ravel(),t.gz.ravel()]
    t.height=shape(points)[:,1].reshape(t.height.shape)
    audit={'region':REGION,'revision':'southern-broad-banks-v1','fieldCells':len(ids),
           'maximumFieldChange':float(np.max(abs(target-old))),'meshFacesBeforeAfter':counts,
           'movedUnlinkedScatter':moved,'reseatedOrnamentalWaystones':sorted(movable),'roadMeshesUnchanged':True,'sharedBandMetres':3.}
    import approach_materials
    audit['bedrock']=approach_materials.apply(build,before)
    build.white_broad_landform_audit=audit
    return audit
