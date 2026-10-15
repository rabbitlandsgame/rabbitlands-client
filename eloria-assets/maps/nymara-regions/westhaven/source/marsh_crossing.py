"""The Coast Road's raised stone crossing between shore and shared causeway.

The geography route follows the tidal bed here. Keep its surveyed XZ course,
but carry carts above the water on masonry spans with open gaps between piers.
This module adds actual native deck geometry before connector finishing.
"""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import sys
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import streaming_borders as SB
from verify_runtime import VerticalRayIndex

HEIGHT = 4.0
HALF_WIDTH = 4.25
CENTRES = np.array([[244.,24.],[256.,36.],[256.,44.],[264.,52.],
                    [264.,56.],[268.,60.],[268.,62.],[270.5,64.5]])


def edge_points(lateral):
    """Shared miter vertices keep every adjoining span edge continuous."""
    directions=np.diff(CENTRES,axis=0)
    directions/=np.linalg.norm(directions,axis=1)[:,None]
    sides=np.c_[-directions[:,1],directions[:,0]]
    offsets=[sides[0]]
    for a,b in zip(sides,sides[1:]):
        bisector=a+b
        offsets.append(bisector/max(float(bisector@b),1e-8))
    # The existing shared deck begins on the vertical plane X270.5.
    offsets.append(np.array([0.,1.]))
    return CENTRES+np.asarray(offsets)*lateral


def ribbon(inner,outer,y,material):
    a,b=edge_points(inner),edge_points(outer)
    pieces=[]
    for i in range(len(CENTRES)-1):
        q=M.quad([[a[i,0],y,a[i,1]],[a[i+1,0],y,a[i+1,1]],
                  [b[i+1,0],y,b[i+1,1]],[b[i,0],y,b[i,1]]],material=material)
        if q.normals[:,1].mean()<0:q.flip_winding();q.recompute_normals(180)
        q.uvs=q.positions[:,[0,2]]*.28
        pieces.append(q)
    return M.merge(pieces,material)


def sides(inner,outer,bottom,top,material):
    parts=[ribbon(inner,outer,bottom,material)]
    parts[0].flip_winding();parts[0].recompute_normals(180)
    for lateral in (inner,outer):
        points=edge_points(lateral)
        for a,b in zip(points,points[1:]):
            parts.append(M.quad([[*a[:1],bottom,a[1]],[*b[:1],bottom,b[1]],
                                 [*b[:1],top,b[1]],[*a[:1],top,a[1]]],material=material))
    a,b=edge_points(inner),edge_points(outer)
    for i in (0,-1):
        parts.append(M.quad([[a[i,0],bottom,a[i,1]],[b[i,0],bottom,b[i,1]],
                             [b[i,0],top,b[i,1]],[a[i,0],top,a[i,1]]],material=material))
    return M.merge(parts,material)


def lamp_join(build):
    """Match the preserved lamp causeway, with a four-metre approach feather."""
    placement=next(p for p in build.placements if p.node=='Landmark_Route_lamp_causeway')
    item=build.meshes[placement.mesh];parts=getattr(item,'walk_parts',[]) or [item]
    triangles=[];rotation=M.rotation_y(placement.rotation_y)[:3,:3]
    for part in parts:
        p=part.positions*placement.scale@rotation.T+placement.position
        triangles.append(p[part.indices.reshape(-1,3)])
    triangles=np.concatenate(triangles)
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    keep=np.abs(normals[:,1])>1e-8;triangles=triangles[keep];normals=normals[keep]
    xz=triangles[:,:,[0,2]];edges=np.roll(xz,-1,axis=1)-xz;cache={}
    def height(point):
        key=tuple(np.round(point,8))
        if key in cache:return cache[key]
        rel=np.asarray(point)[None,None,:]-xz
        cross=edges[:,:,0]*rel[:,:,1]-edges[:,:,1]*rel[:,:,0]
        inside=np.all(cross>=-1e-9,axis=1)|np.all(cross<=1e-9,axis=1)
        t=np.clip((rel*edges).sum(2)/np.maximum((edges*edges).sum(2),1e-18),0,1)
        distances=np.linalg.norm(rel-t[:,:,None]*edges,axis=2).min(1);distances[inside]=0.
        planes=triangles[:,0,1]-((np.asarray(point)-triangles[:,0,[0,2]])*normals[:,[0,2]]).sum(1)/normals[:,1]
        i=min(range(len(triangles)),key=lambda k:(round(float(distances[k]),8),-float(planes[k])))
        t=np.clip(distances[i]/4.,0,1);weight=1-t*t*(3-2*t)
        cache[key]=float(HEIGHT+(planes[i]-HEIGHT)*weight);return cache[key]
    return triangles,height


def subtract_lamp_walk(mesh,triangles):
    """Keep the older walk surface and its curb openings as exact XZ cuts."""
    import road_profiles as R
    result=mesh
    for triangle in triangles:
        xz=triangle[:,[0,2]];a,b=xz[1]-xz[0],xz[2]-xz[0]
        area=a[0]*b[1]-a[1]*b[0]
        if abs(area)<1e-10:continue
        if area<0:xz=xz[[0,2,1]]
        remaining=result;outside=[]
        for a,b in zip(xz,np.roll(xz,-1,axis=0)):
            if not remaining.triangle_count:break
            vector=b-a;relative=remaining.positions[:,[0,2]]-a
            distance=vector[0]*relative[:,1]-vector[1]*relative[:,0]
            outside.append(R._clip_scalar(remaining,distance))
            remaining=R._clip_scalar(remaining,-distance)
        result=M.merge(outside,mesh.material)
    return result


def upward_top(mesh):
    """Keep clipped walking faces visible to the upward-only collider raster."""
    faces=mesh.indices.reshape(-1,3)
    points=mesh.positions[faces]
    down=np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])[:,1]<0
    faces[down]=faces[down][:,[0,2,1]]
    mesh.recompute_normals(180)
    return mesh


def apply(build):
    if getattr(build,'_west_marsh_crossing_added',False):
        raise ValueError('Westhaven marsh crossing added twice')
    road=next(r for r in build.geography_roads if r['id']=='westhaven-manymouth')
    floor=[m.positions[m.indices.reshape(-1,3)] for n,m in build.terrain_meshes.items()
           if n.startswith('Terrain_') and m.triangle_count]
    terrain=VerticalRayIndex(np.concatenate(floor))
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_northern'))
    import road_profiles as R
    native_join,deck_height=lamp_join(build)
    pieces={'Walk_StreamCauseway_westhaven-marsh':ribbon(-HALF_WIDTH,HALF_WIDTH,HEIGHT,'cobble_paving')}
    masonry=[sides(-HALF_WIDTH,HALF_WIDTH,HEIGHT-.8,HEIGHT,'pale_ashlar')]
    for sign in (-1,1):
        a,b=sorted((sign*3.5,sign*3.88))
        curb=M.merge([sides(a,b,HEIGHT-.08,HEIGHT+.4,'pale_ashlar'),
                      ribbon(a,b,HEIGHT+.4,'pale_ashlar')],'pale_ashlar')
        # The older walking route remains an open junction through these curbs.
        masonry.append(subtract_lamp_walk(curb,native_join))
    pieces['Structure_StreamCauseway_westhaven-marsh_pale_ashlar']=M.merge(masonry,'pale_ashlar')
    for mesh in pieces.values():
        R.refine_bed(mesh,[road])
        mesh.positions[:,1]+=np.array([deck_height(p[[0,2]])-HEIGHT for p in mesh.positions])
        mesh.recompute_normals(180)
    # One visible walking surface at the junction; no coplanar native duplicate.
    name='Walk_StreamCauseway_westhaven-marsh'
    pieces[name]=subtract_lamp_walk(pieces[name],native_join)
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(CENTRES,axis=0),axis=1))]
    piers=[];contacts=[]
    for along in np.arange(4.,distance[-1]-1.,10.):
        i=min(int(np.searchsorted(distance,along,side='right')-1),len(CENTRES)-2)
        t=(along-distance[i])/(distance[i+1]-distance[i]);xz=CENTRES[i]*(1-t)+CENTRES[i+1]*t
        direction=CENTRES[i+1]-CENTRES[i];direction/=np.linalg.norm(direction)
        side=np.array([-direction[1],direction[0]])
        rays=[terrain.top_hit(*(xz+direction*a+side*b)) for a in (-.625,.625) for b in (-3.25,3.25)]
        if any(y is None for y in rays):raise ValueError('Marsh pier has no actual bed')
        bottom=min(rays)-.3
        top=max(deck_height(xz+direction*a+side*b) for a in (-.625,.625) for b in (-3.25,3.25))-.70
        pier=M.box((1.25,top-bottom,6.5),material='rubble_stone')
        pier.rotate_y(np.arctan2(-direction[1],direction[0]));pier.translate(xz[0],(bottom+top)/2,xz[1]);piers.append(pier)
        contacts.append({'xz':xz.tolist(),'bottom':bottom,'bedHeights':rays})
    pieces['Structure_StreamCauseway_westhaven-marsh_rubble_stone']=M.merge(piers,'rubble_stone')
    # Partition only the newly authored meshes through the normal protocol.
    # Existing cells are not re-cut, and every visible receiving piece is shared.
    specs=deepcopy(build.streaming_borders)
    for spec in specs:spec['sceneNodes']=[]
    extra=SimpleNamespace(terrain_meshes=pieces,water_meshes={},placements=[])
    SB.partition_shared_approaches(extra,specs)
    record=G.plan()['regions']['westhaven']
    polygon=np.asarray(record['ownershipPolygon'])-np.asarray(record['translation'])[[0,2]]
    rectangles=G.polygon_rectangles(polygon)
    for name,mesh in extra.terrain_meshes.items():
        mesh=G.clip_owned_mesh(mesh,rectangles)
        if name.startswith('Walk_StreamCauseway_westhaven-marsh'):
            upward_top(mesh)
        if mesh.triangle_count:build.terrain_meshes[name]=mesh
    for spec in specs:
        destination=next(s for s in build.streaming_borders if s['id']==spec['id'])
        destination['sceneNodes'].extend(n for n in spec['sceneNodes'] if n in build.terrain_meshes)
    road['wetCrossing']={'nativeDeck':'Walk_StreamCauseway_westhaven-marsh','height':HEIGHT,
                         'preservedJunction':'Landmark_Route_lamp_causeway','junctionFeatherMetres':4.,
                         'centres':CENTRES.tolist(),'clearWidth':7.,'outerWidth':8.5,'piers':contacts}
    build._west_marsh_crossing_added=True
    build.notes.append('The Coast Road crosses the tidal inlet on a raised stone deck, with an open channel between masonry piers and a graded shoreward apron.')
