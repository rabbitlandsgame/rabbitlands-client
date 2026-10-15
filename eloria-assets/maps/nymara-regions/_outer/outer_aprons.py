"""Authored outer aprons; native playable ground and shared approaches stay fixed.

Capture the actual native mesh before streaming-border construction. Finish
after streaming and northern shaping. No previous GLB or collision file is an
input. Wet rims descend into their existing water datum; Whitehorn remains a
dry glacial escarpment with a real cut edge and rock faces, never a new ocean.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import math
import numpy as np
from amberwood import mesh as M
import continent_geography as G

# Distances are outside the immutable native playable rectangle, in metres.
# Deliberate long bays and headlands replace a noise-painted square outline.
CURVES = {
 'amberwood': {'north':[9,21,12,23,10,18,7], 'west':[8,20,10,24,14,20,9]},
 'whitehorn_range': {'north':[5,18,9,20,8,16,5], 'west':[6,25,13,28,9,20,6], 'east':[8,22,11,27,14,25,8]},
 'amethyst_barrens': {'north':[8,20,12,24,9,18,8], 'east':[9,24,13,22,10,24,9]},
 'grey_moors': {'north':[10,24,12,22,9,20,8], 'west':[9,21,13,25,11,22,9]},
 'sunmane_steppe': {'east':[10,25,16,28,12,24,10]},
 'ssarathi_ruins': {'south':[10,24,14,28,12,23,10]},
 'verdant_stair': {'north':[10,24,12,27,15,23,10], 'east':[9,25,14,27,10,23,9], 'south':[10,23,12,26,14,24,10]},
 'manymouth_delta': {'south':[8,22,12,26,10,23,8]},
}
SIDES={'west':(0,-1),'east':(0,1),'north':(1,-1),'south':(1,1)}
NATURE={'tree','foliage','rock','undergrowth','stone','scatter','scrub','crystal','fallenlog'}


def smooth(x):
    x=np.clip(x,0.,1.);return x*x*(3.-2.*x)


def _native(name):
    return name.startswith('Terrain_') and not any(s in name for s in
        ('_StreamCollar_','_ContinentBlend_','ContinentExtension','_StreamThreshold_'))


def _perimeter(meshes, low, high):
    triangles=np.concatenate([m.positions[m.indices].reshape(-1,3,3) for m in meshes])
    vertices=triangles.reshape(-1,3)
    keys=np.rint(vertices[:,[0,2]]*1e6).astype(np.int64)
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    positions=vertices[first]
    faces=np.unique(np.sort(inverse.reshape(-1,3),axis=1),axis=0)
    edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    boundary=positions[unique[counts==1]]
    centre=boundary[:,:,[0,2]].mean(axis=1)
    outside=np.maximum(low-centre,centre-high).max(axis=1)
    boundary=boundary[outside>-.001]
    lengths=np.linalg.norm(np.diff(boundary[:,:,[0,2]],axis=1)[:,0],axis=1)
    boundary=boundary[lengths>1e-6]
    if not len(boundary):raise ValueError('Native terrain has no physical perimeter')
    return boundary


def _nearest_perimeter(points, edges):
    result=np.empty(len(points));a=edges[:,0][:,[0,2]];v=edges[:,1][:,[0,2]]-a
    vv=np.einsum('ij,ij->i',v,v)
    for start in range(0,len(points),512):
        p=points[start:start+512]
        along=np.clip(np.einsum('pki,ki->pk',p[:,None,:]-a,v)/vv,0,1)
        delta=p[:,None,:]-a-along[:,:,None]*v
        selected=np.argmin(np.einsum('pki,pki->pk',delta,delta),axis=1)
        t=along[np.arange(len(p)),selected]
        result[start:start+len(p)]=edges[selected,0,1]+t*(edges[selected,1,1]-edges[selected,0,1])
    return result


class WaterUV:
    """Retain actual piecewise native water UVs, including compacted meshes."""
    def __init__(self,mesh):
        from verify_runtime import VerticalRayIndex
        from scipy.spatial import cKDTree
        self.tri=mesh.positions[mesh.indices].reshape(-1,3,3)
        self.uv=mesh.uvs[mesh.indices].reshape(-1,3,2)
        self.ray=VerticalRayIndex(self.tri)
        self.centres=cKDTree(self.tri[:,:,[0,2]].mean(axis=1))

    def sample(self,points):
        result=[]
        for point in points:
            bucket=(int(math.floor((point[0]-self.ray.min_x)/self.ray.cell)),int(math.floor((point[1]-self.ray.min_z)/self.ray.cell)))
            ids=self.ray.buckets.get(bucket)
            if ids is None:ids=np.atleast_1d(self.centres.query(point,k=min(16,len(self.tri)))[1])
            tri=self.tri[ids][:,:,[0,2]];a=tri[:,0];v=tri[:,1]-a;w=tri[:,2]-a;q=point-a
            det=v[:,0]*w[:,1]-v[:,1]*w[:,0]
            valid=np.abs(det)>1e-10
            u=np.divide(q[:,0]*w[:,1]-q[:,1]*w[:,0],det,out=np.zeros(len(ids)),where=valid)
            t=np.divide(v[:,0]*q[:,1]-v[:,1]*q[:,0],det,out=np.zeros(len(ids)),where=valid)
            bary=np.c_[1-u-t,u,t]
            inside=valid&(bary.min(axis=1)>=-1e-7)
            if inside.any():chosen=np.flatnonzero(inside)[0]
            else:
                # Outside the existing water sheet, extrapolate the nearest
                # physical triangle's affine UV plane. Existing shared water
                # is excluded from this replacement domain.
                penalty=np.maximum(-bary,0).sum(axis=1);penalty[~valid]=np.inf
                chosen=int(np.argmin(penalty))
            if not valid[chosen]:raise ValueError('Water UV sampler has no nondegenerate native face')
            result.append(bary[chosen]@self.uv[ids[chosen]])
        return np.asarray(result)


@dataclass
class Snapshot:
    region:str
    low:np.ndarray
    high:np.ndarray
    perimeter:np.ndarray
    water_level:float|None
    water_material:str|None
    footings:list
    native_bounds:tuple
    contacts:dict
    native_ray:object
    water_uv:object


def capture(build, region):
    if region not in CURVES:raise ValueError(f'No authored outer apron for {region}')
    spec=G.plan()['regions'][region];low,high=np.array(spec['nativePlayableBounds'],float)
    native=[m for n,m in build.terrain_meshes.items() if _native(n) and m.triangle_count]
    if not native:raise ValueError(f'{region}: capture needs the native terrain before SB.apply')
    water=[]
    for name,m in build.water_meshes.items():
        if not m.triangle_count:continue
        bottom,top=m.bounds()
        if abs(top[1]-bottom[1])<1e-7 and abs(float(top[1]))<1e-5:
            area=(top[0]-bottom[0])*(top[2]-bottom[2]);water.append((area,m.material,float(top[1]),m))
    if region=='whitehorn_range':
        level,material,water_uv=None,None,None
    elif water:
        _,material,level,water_mesh=max(water,key=lambda item:item[0])
        water_uv=WaterUV(water_mesh)
    else:raise ValueError(f'{region}: wet apron requires actual existing sea-level water')
    linked={e.get('node') for collection in ('landmarks','interactives','npc_markers','harvestables','portals','spawns')
            for e in getattr(build,collection,[]) if e.get('node')}
    footings=[]
    from amberwood.mesh import rotation_y
    for p in build.placements:
        if p.node not in linked and not p.landmark and (not p.collides or p.kind in NATURE):continue
        mesh=build.meshes.get(p.mesh)
        if mesh is None or not mesh.triangle_count:continue
        lo,hi=mesh.bounds();corners=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
        world=(corners*p.scale)@rotation_y(p.rotation_y)[:3,:3].T+np.asarray(p.position)
        footings.append((world[:,[0,2]].min(axis=0)-2,world[:,[0,2]].max(axis=0)+2))
    for collection in ('landmarks','interactives','npc_markers','harvestables','portals','spawns'):
        for entry in getattr(build,collection,[]):
            p=entry.get('position') or entry.get('center')
            if isinstance(p,(list,tuple)) and len(p)==3:
                xz=np.array(p)[[0,2]];footings.append((xz-5,xz+5))
    from verify_runtime import VerticalRayIndex
    native_ray=VerticalRayIndex(np.concatenate([m.positions[m.indices].reshape(-1,3,3) for m in native]))
    contacts={}
    candidates=[p for p in build.placements if p.kind in NATURE and p.node not in linked and not p.landmark
                and np.maximum(low-np.asarray(p.position)[[0,2]],np.asarray(p.position)[[0,2]]-high).max()>2]
    if candidates:
        ray=native_ray
        for p in candidates:
            ground=ray.top_hit(p.position[0],p.position[2])
            if ground is None:continue  # Unconnected scenery does not acquire an invented footing.
            minimum=level+.15 if level is not None else None
            if region=='manymouth_delta' and p.node.startswith('mangrove_'):
                # Native populate_mangroves explicitly authors tidal roots on
                # silt down to 1.35m below the same sea datum.
                minimum=level-1.35
            contacts[p.node]={'offset':float(p.position[1]-ground),'minimumGround':minimum}
    boxes=np.array([m.bounds() for m in native])
    return Snapshot(region,low,high,_perimeter(native,low,high),level,material,footings,
                    (boxes[:,0].min(axis=0),boxes[:,1].max(axis=0)),contacts,native_ray,water_uv)


def _road_distance(build, points):
    distance=np.full(len(points),np.inf)
    for road in getattr(build,'geography_roads',[]):
        stations=np.asarray(road['stations'])[:,[0,2]]
        d,_=G._road_coordinates(points,stations);distance=np.minimum(distance,d)
    return distance


def _field(build,snapshot,points):
    p=np.asarray(points,float);lo,hi=snapshot.low,snapshot.high
    outward=np.maximum(np.maximum(lo-p,p-hi),0).max(axis=1)
    weight=smooth((outward-2)/5)
    # Preserve the entire sampled common contour and both adjoining collars.
    shared,_=G.boundary_sample(snapshot.region,p,maximum=66)
    weight*=smooth((shared-48)/16)
    weight*=smooth((_road_distance(build,p)-20)/8)
    for a,b in snapshot.footings:
        distance=np.linalg.norm(np.maximum(np.maximum(a-p,p-b),0),axis=1)
        weight*=smooth(distance/6)
    fraction=np.zeros(len(p));signed=np.full(len(p),np.inf)
    for side,knots in CURVES[snapshot.region].items():
        axis,sign=SIDES[side];other=1-axis;edge=hi[axis] if sign>0 else lo[axis]
        distance=(p[:,axis]-edge)*sign
        along=np.clip((p[:,other]-lo[other])/(hi[other]-lo[other]),0,1)
        reach=np.interp(along,np.linspace(0,1,len(knots)),knots)
        fraction=np.maximum(fraction,np.clip((distance-2)/(reach-2),0,1))
        signed=np.minimum(signed,reach-distance)
    return weight,fraction,signed


def _reshape(build,snapshot,points,extension=False):
    result=np.asarray(points,float).copy();xz=result[:,[0,2]]
    weight,fraction,signed=_field(build,snapshot,xz)
    selected=weight>0
    substrate=result[:,1].copy()
    if extension and selected.any():
        # Actual triangle perimeter, not terrain.height_at outside its grid.
        selected_points=xz[selected]
        sampled=np.array([snapshot.native_ray.top_hit(x,z) for x,z in selected_points],float)
        missing=~np.isfinite(sampled)
        if missing.any():sampled[missing]=_nearest_perimeter(selected_points[missing],snapshot.perimeter)
        substrate[selected]=np.minimum(substrate[selected],sampled)
    if snapshot.water_level is None:
        target=substrate-24*fraction*fraction
    else:
        level=snapshot.water_level
        target=level+(substrate-level)*(1-fraction)**2-7*fraction*fraction
        target=np.minimum(substrate,target)
    result[:,1]+=(target-result[:,1])*weight
    return result,signed+(1-weight)*1000


def _clip_dry(mesh, values):
    """Clip the physical unplayable edge; preserve UV/coverage interpolation."""
    columns=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:columns.append(mesh.colors)
    packed=np.c_[np.concatenate(columns,axis=1),values];faces=mesh.indices.reshape(-1,3)
    keep=values[faces].min(axis=1)>=0;reject=values[faces].max(axis=1)<0
    pieces=[packed[faces[keep]].reshape(-1,packed.shape[1])];cliffs=[]
    for ids in faces[~keep&~reject]:
        triangle=packed[ids];polygon=[];cut=[]
        for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
            if a[-1]>=0:polygon.append(a)
            if (a[-1]>=0)!=(b[-1]>=0):
                p=a+(b-a)*(a[-1]/(a[-1]-b[-1]));polygon.append(p);cut.append(p[:3])
        for i in range(1,len(polygon)-1):pieces.append(np.array([polygon[0],polygon[i],polygon[i+1]]))
        if len(cut)==2:cliffs.append(cut)
    output=np.concatenate(pieces) if pieces else np.empty((0,packed.shape[1]))
    result=mesh.copy();result.positions=output[:,:3];result.normals=output[:,3:6];result.uvs=output[:,6:8]
    if mesh.colors is not None:result.colors=output[:,8:12]
    result.indices=np.arange(len(output));return result,cliffs


def _isolate_core(mesh,snapshot):
    """Add exact boundaries so deforming a long outside face cannot tilt core ground."""
    lo,hi=mesh.bounds();x0,z0=snapshot.low-2;x1,z1=snapshot.high+2
    rectangles=np.array([[x0,z0,x1,z1], [lo[0]-1,lo[2]-1,x0,hi[2]+1],
        [x1,lo[2]-1,hi[0]+1,hi[2]+1], [x0,lo[2]-1,x1,z0], [x0,z1,x1,hi[2]+1]])
    rectangles=rectangles[(rectangles[:,2]>rectangles[:,0])&(rectangles[:,3]>rectangles[:,1])]
    return G.clip_owned_mesh(mesh,rectangles)


def _rectangles(mask,xs,zs):
    active={};result=[]
    for row in range(mask.shape[0]):
        padded=np.r_[False,mask[row],False];changes=np.flatnonzero(padded[1:]!=padded[:-1]);current={}
        for a,b in zip(changes[::2],changes[1::2]):
            key=(a,b);old=active.pop(key,None);current[key]=[xs[a],old[1] if old else zs[row],xs[b],zs[row+1]]
        result.extend(active.values());active=current
    result.extend(active.values());return np.asarray(result,float).reshape(-1,4)


def _water_support(build,snapshot):
    """Replace only outer sea-level pieces with one nonoverlapping real sheet."""
    spec=G.plan()['regions'][snapshot.region];translation=np.array(spec['translation'])[[0,2]]
    polygon=np.array(spec['ownershipPolygon'])-translation;low,high=polygon.min(axis=0),polygon.max(axis=0)
    xs=np.r_[np.arange(low[0],high[0],2.),high[0]];zs=np.r_[np.arange(low[1],high[1],2.),high[1]]
    gx,gz=np.meshgrid((xs[:-1]+xs[1:])/2,(zs[:-1]+zs[1:])/2);points=np.c_[gx.ravel(),gz.ravel()]
    outward=np.maximum(np.maximum(snapshot.low-points,points-snapshot.high),0).max(axis=1)
    shared,_=G.boundary_sample(snapshot.region,points,maximum=48)
    _,fraction,_=_field(build,snapshot,points)
    mask=((outward>2)&(shared>44)&(_road_distance(build,points)>16)&(fraction>0)).reshape(gx.shape)
    rectangles=_rectangles(mask,xs,zs)
    if not len(rectangles):return 0
    # Keep existing water and its exact piecewise UV field wherever it already
    # covers an entire replacement rectangle. This is common for the full
    # sea/delta sheets and avoids needlessly retriangulating their ripples.
    incomplete=[]
    for rectangle in rectangles:
        area=0.
        x0,z0,x1,z1=rectangle
        for mesh in build.water_meshes.values():
            if not mesh.triangle_count:continue
            a,b=mesh.bounds()
            if abs(a[1]-snapshot.water_level)>1e-6 or abs(b[1]-snapshot.water_level)>1e-6:continue
            if b[0]<=x0 or a[0]>=x1 or b[2]<=z0 or a[2]>=z1:continue
            part=G.clip_owned_mesh(mesh,np.asarray([rectangle]))
            tri=part.positions[part.indices].reshape(-1,3,3)[:,:,[0,2]]
            u=tri[:,1]-tri[:,0];v=tri[:,2]-tri[:,0]
            area+=float(np.abs(u[:,0]*v[:,1]-u[:,1]*v[:,0]).sum()*.5)
        expected=(x1-x0)*(z1-z0)
        if abs(area-expected)>max(1e-6,expected*1e-8):incomplete.append(rectangle)
    rectangles=np.asarray(incomplete).reshape(-1,4)
    if not len(rectangles):return 0
    own=G.polygon_rectangles(polygon)
    # Exact complement rectangles keep pre-existing water once, including its
    # original material and surveyed approaches. Pools inside the core stay.
    for name,mesh in list(build.water_meshes.items()):
        if not mesh.triangle_count:continue
        lo,hi=mesh.bounds()
        if abs(lo[1]-snapshot.water_level)>1e-6 or abs(hi[1]-snapshot.water_level)>1e-6:continue
        part=mesh
        for x0,z0,x1,z1 in rectangles:
            if not part.triangle_count:break
            a,b=part.bounds()
            if b[0]<=x0 or a[0]>=x1 or b[2]<=z0 or a[2]>=z1:continue
            clips=np.array([[a[0]-1,a[2]-1,min(x0,b[0]+1),b[2]+1],
                [max(x1,a[0]-1),a[2]-1,b[0]+1,b[2]+1],
                [max(x0,a[0]-1),a[2]-1,min(x1,b[0]+1),min(z0,b[2]+1)],
                [max(x0,a[0]-1),max(z1,a[2]-1),min(x1,b[0]+1),b[2]+1]])
            clips=clips[(clips[:,2]>clips[:,0])&(clips[:,3]>clips[:,1])]
            part=G.clip_owned_mesh(part,clips)
        if part.triangle_count:build.water_meshes[name]=part
        else:del build.water_meshes[name]
    sheets=[]
    for x0,z0,x1,z1 in rectangles:
        y=snapshot.water_level
        piece=M.quad([[x0,y,z0],[x0,y,z1],[x1,y,z1],[x1,y,z0]],material=snapshot.water_material)
        piece.uvs=snapshot.water_uv.sample(piece.positions[:,[0,2]]);sheets.append(piece)
    sea=G.clip_owned_mesh(M.merge(sheets,snapshot.water_material),own)
    if sea.triangle_count:build.water_meshes['Water_OuterApron_'+snapshot.region]=sea
    return sea.triangle_count


def apply(build,region,snapshot):
    if snapshot.region!=region:raise ValueError('Outer apron snapshot belongs to a different region')
    if getattr(build,'outer_apron_audit',None):raise ValueError('Outer apron already finished; rebuild from the native source')
    changed=0;cliffs=[];removed=[];maximum=0.;protected_changed=0
    for name,mesh in list(build.terrain_meshes.items()):
        if not name.startswith('Terrain_') or '_StreamThreshold_' in name or not mesh.triangle_count:continue
        mesh=_isolate_core(mesh,snapshot)
        before=mesh.positions.copy();before_normals=mesh.normals.copy()
        shaped,signed=_reshape(build,snapshot,before,extension='ContinentExtension' in name)
        delta=np.abs(shaped[:,1]-before[:,1]);changed+=int(np.count_nonzero(delta>1e-8));maximum=max(maximum,float(delta.max(initial=0)))
        inside=(before[:,[0,2]]>=snapshot.low).all(axis=1)&(before[:,[0,2]]<=snapshot.high).all(axis=1)
        protected_changed+=int(np.count_nonzero(delta[inside]>1e-8))
        mesh.positions=shaped
        if snapshot.water_level is None and signed.min(initial=1)<0:
            mesh,edges=_clip_dry(mesh,signed);cliffs+=edges
        if mesh.triangle_count:
            # Preserve original native normals as well as geometry; the new
            # clipped faces carry interpolated normals at their cut edges.
            if snapshot.water_level is not None:
                mesh.recompute_normals(180);mesh.normals[inside]=before_normals[inside]
            else:mesh.recompute_normals(180)
            build.terrain_meshes[name]=mesh
        else:del build.terrain_meshes[name];removed.append(name)
    if cliffs:
        unique={tuple(np.round(np.array(edge)[np.lexsort((np.array(edge)[:,2],np.array(edge)[:,0]))],5).ravel()):edge for edge in cliffs}
        pieces=[]
        for a,b in unique.values():
            c=b.copy();d=a.copy();c[1]-=18;d[1]-=18
            piece=M.quad([a,b,c,d],material='alpine_bedrock_ground');piece.uvs=piece.positions[:,[0,1]]*.28;pieces.append(piece)
        build.terrain_meshes['Terrain_OuterEscarpment_'+region]=M.merge(pieces,'alpine_bedrock_ground')
    water=_water_support(build,snapshot) if snapshot.water_level is not None else 0
    moved_scatter=[];removed_scatter=[]
    if snapshot.contacts:
        from verify_runtime import VerticalRayIndex
        meshes=[m for n,m in build.terrain_meshes.items() if _native(n) and m.triangle_count]
        # Include the reshaped extension; paint and cliff sides never own a root's contact.
        meshes += [m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_ContinentExtension') and m.triangle_count]
        ray=VerticalRayIndex(np.concatenate([m.positions[m.indices].reshape(-1,3,3) for m in meshes]))
        keep=[]
        for p in build.placements:
            if p.node not in snapshot.contacts:keep.append(p);continue
            weight,_,_=_field(build,snapshot,np.asarray(p.position)[None,[0,2]])
            if weight[0]<=0:keep.append(p);continue
            ground=ray.top_hit(p.position[0],p.position[2])
            minimum=snapshot.contacts[p.node]['minimumGround']
            if ground is None or (minimum is not None and ground<minimum):
                removed_scatter.append(p.node);continue
            p.position=(p.position[0],float(ground+snapshot.contacts[p.node]['offset']),p.position[2])
            moved_scatter.append(p.node);keep.append(p)
        build.placements[:]=keep
    terrain=build.terrain
    points=np.c_[terrain.gx.ravel(),terrain.height.ravel(),terrain.gz.ravel()]
    shaped,cut=_reshape(build,snapshot,points)
    terrain.height=shaped[:,1].reshape(terrain.height.shape)
    if hasattr(terrain,'tree_block') and snapshot.water_level is None:
        terrain.tree_block |= (cut<0).reshape(terrain.height.shape)
    available=set(build.terrain_meshes)|set(build.water_meshes)|{p.node for p in build.placements}
    for spec in build.streaming_borders:spec['sceneNodes']=[n for n in spec.get('sceneNodes',[]) if n in available]
    if protected_changed:raise ValueError('Outer apron changed native playable terrain')
    report={'region':region,'mode':'dry-glacial-escarpment' if snapshot.water_level is None else 'existing-water-shelf',
        'changedVertices':changed,'maximumHeightChange':maximum,'nativePlayableVerticesChanged':protected_changed,
        'removedTerrainNodes':removed,'newWaterTriangles':water,'cliffSegments':len(cliffs),
        'movedOuterScatter':moved_scatter,'removedNonContentOuterScatter':removed_scatter,
        'capturedNativeBounds':[p.tolist() for p in snapshot.native_bounds]}
    build.outer_apron_audit=report
    build.notes.append('Outer apron: actual native perimeter, authored irregular outer contours, intact playable core and common approaches; physical water only at the existing regional datum.')
    return report
