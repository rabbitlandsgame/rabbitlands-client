"""Visible masonry beneath the already-solved, ownership-clipped road rims.

This construction pass adds no walking top and does not reshape any source
surface. Its input is the finished connector geometry, so it can be verified
independently of the numerical road solve.
"""
import numpy as np
from amberwood import mesh as M
import continent_geography as G
import road_profiles as R
from verify_runtime import VerticalRayIndex


def _subtract_footprints(mesh, triangles):
    """Subtract exact existing soffit footprints using local face candidates."""
    if not len(triangles) or not mesh.triangle_count:return mesh
    oracle=VerticalRayIndex(triangles)
    fields=[mesh.positions,mesh.normals,mesh.uvs]
    if mesh.colors is not None:fields.append(mesh.colors)
    values=np.concatenate(fields,axis=1);output=[]
    for face in mesh.indices.reshape(-1,3):
        original=values[face];lo=original[:,[0,2]].min(axis=0);hi=original[:,[0,2]].max(axis=0)
        low=np.floor((lo-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        high=np.floor((hi-[oracle.min_x,oracle.min_z])/oracle.cell).astype(int)
        candidates=set()
        for x in range(low[0],high[0]+1):
            for z in range(low[1],high[1]+1):candidates.update(oracle.buckets.get((x,z),()))
        polygons=[original]
        for index in sorted(candidates):
            cutter=triangles[index];xz=cutter[:,[0,2]]
            if (xz.max(axis=0)<lo-1e-8).any() or (xz.min(axis=0)>hi+1e-8).any():continue
            if cutter[:,1].max()<original[:,1].min()-3. or cutter[:,1].min()>original[:,1].max()+3.:continue
            first,second=xz[1]-xz[0],xz[2]-xz[0];area=first[0]*second[1]-first[1]*second[0]
            if abs(area)<1e-10:continue
            if area<0:xz=xz[[0,2,1]]
            remaining=[]
            for polygon in polygons:
                inside=polygon
                for a,b in zip(xz,np.roll(xz,-1,axis=0)):
                    if not len(inside):break
                    vector=b-a;p=inside[:,[0,2]]-a
                    distance=vector[0]*p[:,1]-vector[1]*p[:,0]
                    keep=[];outside=[]
                    for i,j in zip(range(len(inside)),np.roll(np.arange(len(inside)),-1)):
                        v,w=inside[i],inside[j];d,e=distance[i],distance[j]
                        (keep if d>=0 else outside).append(v)
                        if (d>=0)!=(e>=0):
                            cut=v+(w-v)*(d/(d-e));keep.append(cut);outside.append(cut)
                    if len(outside)>=3:remaining.append(np.asarray(outside))
                    inside=np.asarray(keep)
            polygons=remaining
            if not polygons:break
        for polygon in polygons:
            for i in range(1,len(polygon)-1):output.append(polygon[[0,i,i+1]])
    p=np.concatenate(output) if output else np.empty((0,values.shape[1]));result=mesh.copy()
    result.positions,result.normals,result.uvs=p[:,:3],p[:,3:6],p[:,6:8]
    if result.colors is not None:result.colors=p[:,8:12]
    result.indices=np.arange(len(p));return result



def _existing_soffits(build,spec):
    """Horizontal built undersides at the causeway slab's actual datum."""
    arrays=[];anchor=np.asarray(spec['anchor']);forward=np.asarray(spec['outward']);side=np.array([-forward[1],forward[0]])
    for name,mesh in build.terrain_meshes.items():
        if not name.startswith('Structure_') or not mesh.triangle_count:continue
        tri=mesh.positions[mesh.indices.reshape(-1,3)]
        relative=tri[:,:,[0,2]]-anchor[[0,2]];depth=relative@forward;lateral=relative@side
        # A bounded construction query, not all region structures. Face
        # winding is immaterial when finding an already-built horizontal cap.
        keep=(depth.max(1)>=-43.250001)&(depth.min(1)<=.000001)&(lateral.max(1)>=-6)&(lateral.min(1)<=6)
        keep&=(np.ptp(tri[:,:,1],axis=1)<.06)&(np.abs(tri[:,:,1].mean(1)-(anchor[1]-.8))<.08)
        if keep.any():arrays.append(tri[keep])
    return np.concatenate(arrays) if arrays else np.empty((0,3,3))


def _inside_footprint(point,triangles):
    for tri in triangles:
        xz=tri[:,[0,2]];edge=np.roll(xz,-1,axis=0)-xz;rel=point-xz
        cross=edge[:,0]*rel[:,1]-edge[:,1]*rel[:,0]
        if np.all(cross>=-1e-7) or np.all(cross<=1e-7):return True
    return False


def _rim_mesh(top,spec,build,region):
    anchor=np.asarray(spec['anchor'],float);forward=np.asarray(spec['outward'],float)
    side=np.array([-forward[1],forward[0]]);half=float(spec.get('deckWidth',7.))*.5
    relative=top.positions[:,[0,2]]-anchor[[0,2]];depth=relative@forward
    skin=R._clip_scalar(top,-43.25-depth)
    relative=skin.positions[:,[0,2]]-anchor[[0,2]]
    skin=R._clip_scalar(skin,relative@forward)
    faces=skin.indices.reshape(-1,3)
    if not len(faces):return None
    # The short bank apron follows a graded mouth. Hidden underwater retained
    # paint is never construction input, nor is an unrelated high road.
    level=np.max(np.abs(skin.positions[faces,1]-anchor[1]),axis=1)<1.
    skin.indices=faces[level].ravel()
    parts=[];skins=[]
    relative=skin.positions[:,[0,2]]-anchor[[0,2]]
    apron=R._clip_scalar(skin,relative@forward+42.)
    # Use the actual road polygon at the elbow, including its mitred edge
    # beyond4.25m. Six metres is only an unrelated-road exclusion.
    relative=apron.positions[:,[0,2]]-anchor[[0,2]]
    apron=R._clip_scalar(apron,np.abs(relative@side)-6.)
    if apron.triangle_count:skins.append(apron)
    relative=skin.positions[:,[0,2]]-anchor[[0,2]]
    skin=R._clip_scalar(skin,-42.-relative@forward)
    for sign in (-1.,1.):
        relative=skin.positions[:,[0,2]]-anchor[[0,2]]
        strip=R._clip_scalar(skin,half-sign*(relative@side))
        relative=strip.positions[:,[0,2]]-anchor[[0,2]]
        strip=R._clip_scalar(strip,sign*(relative@side)-6.)
        if not strip.triangle_count:continue
        skins.append(strip)
    if not skins:return None
    strip=M.merge(skins,material=top.material)
    record=G.plan()['regions'][region]
    polygon=np.asarray(record['ownershipPolygon'])-np.asarray(record['translation'])[[0,2]]
    strip=G.clip_owned_mesh(strip,G.polygon_rectangles(polygon))
    soffits=_existing_soffits(build,spec)
    strip=_subtract_footprints(strip,soffits)
    if not strip.triangle_count:return None
    if strip.triangle_count:
        # Underside is exactly0.8m below its existing top. No top is copied.
        bottom=strip.copy();bottom.positions[:,1]-=.8;bottom.material='pale_ashlar'
        faces=bottom.indices.reshape(-1,3).copy();tri=bottom.positions[faces]
        up=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]>0
        faces[up]=faces[up][:,[0,2,1]];bottom.indices=faces.ravel()
        bottom.uvs=bottom.positions[:,[0,2]]*.28;bottom.recompute_normals(180);parts.append(bottom)
        points,lookup=np.unique(np.round(strip.positions,7),axis=0,return_inverse=True)
        faces=lookup[strip.indices.reshape(-1,3)];edges={}
        for face in faces:
            tri=points[face]
            if np.cross(tri[1]-tri[0],tri[2]-tri[0])[1]<0:face=face[[0,2,1]]
            for a,b in zip(face,np.roll(face,-1)):
                if a==b:continue
                key=tuple(sorted((int(a),int(b))))
                if key in edges:edges[key]=None
                else:edges[key]=(int(a),int(b))
        for edge in edges.values():
            if edge is None:continue
            a,b=points[list(edge)];relative=np.array([a,b])[:,[0,2]]-anchor[[0,2]]
            depth=relative@forward;lateral=relative@side
            # The inner face mates with the original slab. The shared seam
            # stays open to the reciprocal slab: no overlapping end caps.
            if np.all(np.abs(np.abs(lateral)-half)<1e-6) and np.all(depth>=-42.-1e-6):continue
            if np.all(np.abs(depth+42.)<1e-6):continue
            if np.all(np.abs(depth)<1e-6):continue
            if _inside_footprint((a[[0,2]]+b[[0,2]])*.5,soffits):continue
            if np.all(R._edge_distance(build,region,np.array([a,b])[:,[0,2]])<1e-6):continue
            down=np.array([0.,.8,0.]);wall=M.quad([a,a-down,b-down,b],material='pale_ashlar')
            length=np.linalg.norm(b[[0,2]]-a[[0,2]])
            wall.uvs=np.array([[0,.8],[0,0],[length,0],[length,.8]])*.28
            parts.append(wall)
    if not parts:return None
    return M.merge(parts,material='pale_ashlar')


def apply(build,region):
    """Add only sides and soffits to finite shared stone causeway rims."""
    if getattr(build,'_connector_rim_construction_applied',False):
        raise ValueError('Causeway rim construction applied twice')
    rows=[]
    for spec in getattr(build,'streaming_borders',[]):
        if spec.get('profile')!='causeway':continue
        prefix='Walk_ContinentRoad_'+spec['id']
        names=[n for n,m in build.terrain_meshes.items() if n.startswith(prefix) and m.triangle_count]
        if not names:continue
        top=M.merge([build.terrain_meshes[n] for n in names])
        body=_rim_mesh(top,spec,build,region)
        if body is None:continue
        name='Structure_StreamCauseway_'+spec['id']+'_rim'
        if name in build.terrain_meshes:raise ValueError('Existing causeway rim: '+name)
        build.terrain_meshes[name]=body
        for frame in build.streaming_borders:
            nodes=frame.setdefault('sceneNodes',[])
            if (frame['id']==spec['id'] or set(names).intersection(nodes)) and name not in nodes:nodes.append(name)
        rows.append({'id':spec['id'],'node':name,'triangles':int(body.triangle_count),'thicknessMetres':.8,'landwardApronMetres':1.25})
    build._connector_rim_construction_applied=True
    report={'region':region,'rims':rows,'newWalkingTriangles':0}
    build.connector_rim_construction=report
    return report
