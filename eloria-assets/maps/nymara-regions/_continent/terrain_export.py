"""Partition the completed shared surface without changing its vertex attributes."""
from __future__ import annotations
import io
import math
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt,binary_dilation
import landscape as L
from world_layout import CELL, CHUNK
from scene_io import TOOLKIT
import authoring as AUTHORING
if str(TOOLKIT) not in sys.path:sys.path.insert(0,str(TOOLKIT))
from amberwood import mesh as M, gltf as G


def authored_surface_material(builder,surface,name, *, blend=False):
    """Register the standard-PBR production mapping for an editor Surface."""
    preset=surface['preset']
    if preset=='Water':return 'water_sea',np.ones(2)
    pbr=surface.get('pbr') if preset=='Custom' else surface.get('pbrOverrides')
    if pbr is not None:
        color=tuple(pbr['albedoColor']);roughness=float(pbr['roughness'])
        metallic=float(pbr['metallic']);normal_scale=float(pbr['normalScale'])
        density=np.asarray(pbr['uvScale'],float)[:2];paths={key:pbr.get(key) for key in ('albedoTexture','normalTexture','ormTexture')}
    else:
        family,color,roughness,metallic,normal_scale,density=AUTHORING._PRESET_MATERIALS[preset]
        density=np.full(2,float(density))
        root=AUTHORING.CLIENT/'godot-client/src/dev/map_authoring_pilot/style/textures'
        detail_family='ground' if preset=='Desert' else family
        paths=({"albedoTexture":root/f'{family}-basecolor.png',"normalTexture":root/f'{detail_family}-normal.png',
                "ormTexture":root/f'{detail_family}-orm.png'} if family else {})
    road=surface.get('roadOverrides')
    if road is not None:
        color=tuple(road['wornTint']);roughness*=float(road['roughnessMultiplier'])
        normal_scale=float(road['normalStrength']);density=np.full(2,float(road['textureScale']))
    images={}
    for field,path in paths.items():
        if path is None:continue
        path=Path(path) if isinstance(path,Path) else AUTHORING._source_path(path,f'{name}.{field}')
        image_name=f'{name}_{field}'
        builder.add_image(image_name,path.read_bytes());images[field]=image_name
    material=f'authored_{name}'
    builder.add_material(G.Material(material,base_color=AUTHORING.gltf_base_color(color),roughness=roughness,metallic=metallic,
        base_color_texture=images.get('albedoTexture'),normal_texture=images.get('normalTexture'),
        orm_texture=images.get('ormTexture'),normal_scale=normal_scale,double_sided=True,
        alpha_mode=G.ALPHA_BLEND if blend or color[3]<1. else G.ALPHA_OPAQUE))
    return material,density


def _rotated_uv(points,surface,density):
    uv=np.asarray(points,float)*np.asarray(density,float)
    pbr=surface.get('pbr',surface.get('pbrOverrides',{}));uv+=np.asarray(pbr.get('uvOffset',[0.,0.,0.]),float)[:2]
    angle=math.radians(float(surface.get('rotationDegrees',0.)))
    c,s=math.cos(angle),math.sin(angle)
    # Godot preview applies rotation after texture scale and offset.
    return uv@np.array([[c,s],[-s,c]])


def conform_road_faces(world,faces,uv,colors):
    """Subdivide each ribbon face on the terrain's affine triangles.

    Keep overlapping source faces and their attributes separate. Vertex-only
    draping can bridge a valley inside a face; after this partition the entire
    face, not just its corners, is terrain + .055 metres. No terrain is edited.
    """
    from sea_crossings import _clip_positive
    faces=np.asarray(faces,float).reshape(-1,3,3)
    attributes=np.concatenate((faces,np.asarray(uv,float),np.asarray(colors,float)),axis=2)
    origin=np.array([world.x0,world.z0],float)
    extent=origin+CELL*(np.asarray(world.height.shape[::-1])-1)
    xz=faces[...,[0,2]]
    if not np.isfinite(attributes).all() or (xz<origin).any() or (xz>extent).any():
        raise ValueError('Authored road lies outside the finite shared terrain field')
    output=[]
    for original in attributes:
        # A zero projected area is not a road surface. Do not discard positive
        # slivers with a size threshold or weld different source-face layers.
        a,b,c=original[:,[0,2]]
        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])==0:continue
        first=np.floor((original[:,[0,2]].min(axis=0)-origin)/CELL).astype(int)
        last=np.floor((original[:,[0,2]].max(axis=0)-origin)/CELL).astype(int)
        last=np.minimum(last,np.asarray(world.height.shape[::-1])-2)
        for iz in range(first[1],last[1]+1):
            for ix in range(first[0],last[0]+1):
                x,z=origin+CELL*np.array([ix,iz]); polygon=original
                for axis,bound,sign in ((0,x,1),(0,x+CELL,-1),(2,z,1),(2,z+CELL,-1)):
                    values=sign*(polygon[:,axis]-bound)
                    if (values>=0).all():continue
                    polygon=_clip_positive(polygon,values)
                    if len(polygon)<3:break
                if len(polygon)<3:continue
                diagonal=x+z+CELL-polygon[:,0]-polygon[:,2]
                halves=([polygon] if (diagonal>=0).all() or (diagonal<=0).all() else
                        [_clip_positive(polygon,diagonal),_clip_positive(polygon,-diagonal)])
                for part in halves:
                    for j in range(1,len(part)-1):
                        face=part[[0,j,j+1]].copy();a,b,c=face[:,[0,2]]
                        if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])!=0:output.append(face)
    if not output:
        return np.empty((0,3,3)),np.empty((0,3,2)),np.empty((0,3,4))
    result=np.asarray(output)
    result[:,:,1]=world.height_at(result[:,:,0],result[:,:,2])+.055
    return result[:,:,:3],result[:,:,3:5],result[:,:,5:]


def authored_road_faces(world,snapshot,path):
    """Original saved ribbon topology and attributes, before ground subdivision."""
    controls=path['points'];vertices=[];uv=[];colors=[];indices=[];along=0.;lateral_steps=6
    road_override=path['surface'].get('roadOverrides');feather=float(road_override['edgeFeather']) if road_override else 0.
    control_points=[snapshot.continent_point(value['position']) for value in controls]
    control_widths=[float(value['width']) for value in controls]
    points=[];widths=[]
    for index,(start,end) in enumerate(zip(control_points,control_points[1:])):
        count=max(1,int(math.ceil(np.linalg.norm(end[[0,2]]-start[[0,2]]))))
        amount=np.linspace(0.,1.,count+1)[:-1]
        points.extend(start*(1-value)+end*value for value in amount)
        widths.extend(control_widths[index]*(1-value)+control_widths[index+1]*value for value in amount)
    points.append(control_points[-1]);widths.append(control_widths[-1])
    for index,(point,width) in enumerate(zip(points,widths)):
        previous=point if index==0 else points[index-1];following=point if index==len(points)-1 else points[index+1]
        tangent=(following-previous)[[0,2]];tangent/=max(np.linalg.norm(tangent),1e-12);side=np.array([-tangent[1],tangent[0]])
        if index:along+=float(np.linalg.norm(point-points[index-1]))
        for lateral_index in range(lateral_steps+1):
            u=lateral_index/lateral_steps;lateral=width*(.5-u)
            vertex=point.copy();vertex[[0,2]]+=side*lateral
            vertex[1]=float(world.height_at(vertex[0],vertex[2]))+.055
            vertices.append(vertex);uv.append([u*width,along])
            distance_from_edge=1.-abs(u*2.-1.)
            alpha=1. if feather<=0 else float(L.smoothstep(0.,feather,distance_from_edge))
            colors.append([1.,1.,1.,alpha])
        if index<len(points)-1:
            base=index*(lateral_steps+1);following=base+lateral_steps+1
            for lateral_index in range(lateral_steps):
                a=base+lateral_index;b=a+1;c=following+lateral_index;d=c+1
                indices.extend((a,d,b,a,c,d))
    vertices=np.asarray(vertices,float);face_indices=np.asarray(indices).reshape(-1,3)
    return vertices[face_indices],np.asarray(uv)[face_indices],np.asarray(colors)[face_indices]


def encoded_road_faces(faces,uv,colors):
    """Keep every nonzero stored footprint, oriented like its source face.

    The builder stores global POSITION as float32; region/chunk exports copy
    those bytes and add translation wrappers only. Preserve double positions
    until that normal encoding, but inspect its actual represented determinant.
    """
    def signed_area(points):
        a,b=points[:,1]-points[:,0],points[:,2]-points[:,0]
        return a[:,0]*b[:,2]-a[:,2]*b[:,0]
    source_area=signed_area(faces)
    encoded_area=signed_area(np.asarray(faces,dtype=np.float32).astype(float))
    keep=encoded_area!=0
    reverse=(source_area[keep]>0)!=(encoded_area[keep]>0)
    arrays=[np.asarray(values)[keep].copy() for values in (faces,uv,colors)]
    for values in arrays:values[reverse]=values[reverse][:,[0,2,1]]
    return (*arrays,{'inputFaces':len(faces),'collapsedFaces':int((~keep).sum()),
                    'reorientedFaces':int(reverse.sum()),'outputFaces':int(keep.sum())})


def clip_weighted_ground_faces(faces, uv, colors, polygon):
    """Hard-clip an existing weighted terrain triangle field without resampling its alpha, height or UV.

    The mask cuts geometry, never vertex weights. New vertices interpolate all source attributes barycentrically;
    triangles already contained in the mask retain their exact arrays. Constrained triangulation handles concave
    rings and every disconnected intersection fragment without a hull, bridge or new two-metre fade band.
    """
    from shapely.geometry import Polygon
    from shapely import constrained_delaunay_triangles
    faces=np.asarray(faces,float).reshape(-1,3,3)
    uv=np.asarray(uv,float).reshape(-1,3,2);colors=np.asarray(colors,float).reshape(-1,3,4)
    output=[]
    def parts(geometry):
        if geometry.is_empty:return []
        if geometry.geom_type=='Polygon':return [geometry]
        return [part for child in getattr(geometry,'geoms',[]) for part in parts(child)]
    for face,face_uv,face_colors in zip(faces,uv,colors):
        source=Polygon(face[:,[0,2]])
        if not source.area:continue
        attrs=np.concatenate((face,face_uv,face_colors),axis=1)
        if polygon.covers(source):
            output.append(attrs);continue
        intersection=source.intersection(polygon)
        if intersection.is_empty:continue
        basis=np.vstack((face[:,[0,2]].T,np.ones(3)))
        winding=np.cross(face[1]-face[0],face[2]-face[0])[1]
        for part in parts(intersection):
            if not part.area:continue
            for triangle in constrained_delaunay_triangles(part).geoms:
                xz=np.asarray(triangle.exterior.coords)[:3]
                barycentric=np.linalg.solve(basis,np.vstack((xz.T,np.ones(3)))).T
                emitted=barycentric@attrs
                emitted[:,[0,2]]=xz
                encoded=emitted[:,[0,2]].astype(np.float32).astype(float)
                cross=(encoded[1,0]-encoded[0,0])*(encoded[2,1]-encoded[0,1])-(encoded[1,1]-encoded[0,1])*(encoded[2,0]-encoded[0,0])
                if cross==0:continue
                if np.cross(emitted[1,:3]-emitted[0,:3],emitted[2,:3]-emitted[0,:3])[1]*winding<0:
                    emitted=emitted[[0,2,1]]
                output.append(emitted)
    if not output:return np.empty((0,3,3)),np.empty((0,3,2)),np.empty((0,3,4))
    result=np.asarray(output)
    return result[:,:,:3],result[:,:,3:5],result[:,:,5:]


def ground_region_faces(world, snapshot, ground, owned_triangles, positions, layer):
    """Original analytic footprint weights on the shared terrain lattice, then optional exact mask cuts."""
    from shapely.geometry import Polygon
    translation=snapshot.translation
    matrix=np.asarray(ground['matrix'],float).reshape(4,4,order='F');inverse=np.linalg.inv(matrix)
    half=np.asarray(ground['size'],float)*.5
    triangles=owned_triangles
    mask=None
    if 'clipPolygon' in ground:
        local_mask=np.asarray(ground['clipPolygon'],float)
        continent_mask=local_mask@matrix[np.ix_([0,2],[0,2])].T+matrix[[0,2],3]+translation[[0,2]]
        mask=Polygon(continent_mask)
        corners=np.array([[-half[0],-half[1]],[half[0],-half[1]],[half[0],half[1]],[-half[0],half[1]]])
        extent=corners@matrix[np.ix_([0,2],[0,2])].T+matrix[[0,2],3]+translation[[0,2]]
        lo=np.maximum(extent.min(axis=0)-CELL,np.asarray(mask.bounds[:2]))
        hi=np.minimum(extent.max(axis=0)+CELL,np.asarray(mask.bounds[2:]))
        origin=np.array([world.x[0],world.z[0]])
        start=np.maximum(np.floor((lo-origin)/CELL).astype(int),0)
        stop=np.minimum(np.ceil((hi-origin)/CELL).astype(int),[len(world.x)-1,len(world.z)-1])
        if (start>=stop).any():return np.empty((0,3,3)),np.empty((0,3,2)),np.empty((0,3,4))
        rows,cols=np.meshgrid(np.arange(start[1],stop[1]),np.arange(start[0],stop[0]),indexing='ij')
        nx=len(world.x);a=rows.ravel()*nx+cols.ravel()
        triangles=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1).reshape(-1,3)
    faces=positions[triangles]
    planar=faces.reshape(-1,3).copy();planar[:,1]=0
    # Legacy weights use zero territory-local Y, independently of surface height.
    local=np.c_[planar-np.array([translation[0],0,translation[2]]),np.ones(len(planar))]@inverse.T
    point=local[:,[0,2]]
    if ground['shape']=='rectangle':inside=np.minimum(half[0]-abs(point[:,0]),half[1]-abs(point[:,1]))
    else:
        radius=np.linalg.norm(point/half,axis=1);gradient=np.linalg.norm(point/(half*half),axis=1)
        inside=np.where(radius<1e-5,min(half),(1-radius)*radius/np.maximum(gradient,1e-5))
    blend=float(ground['blendWidth'])
    weights=(np.where(inside>0,1. if blend<=0 else L.smoothstep(0,blend,inside),0)*float(ground['opacity'])).reshape(-1,3)
    selected=weights.max(axis=1)>0;faces=faces[selected]
    colors=np.ones((len(faces),3,4));colors[...,3]=weights[selected]
    anchor=np.asarray(ground.get('uvAnchorContinent',translation[[0,2]]),float)
    uv=(faces[...,[0,2]]-anchor)*float(snapshot.document['terrain']['previewUvMetresInverse'])
    ordinal=int(ground.get('sourceLayerOrdinal',layer))
    faces=faces+(0.002+ordinal*0.0005)*np.array([0,1,0])
    if mask is not None:return clip_weighted_ground_faces(faces,uv,colors,mask)
    return faces,uv,colors


def authored_overlays(world,builder):
    snapshots=dict(getattr(world,'authoring_snapshots',{}))
    snapshot=getattr(world,'authoring_snapshot',None)
    if snapshot is not None:snapshots.setdefault(snapshot.document.get('regionId',AUTHORING.SUNMANE),snapshot)
    if not snapshots:return []
    overlays=[];road_encoding=[]
    def node_name(region_id,name, *, base=False):
        # Preserve the already-published Sunmane node identities while making
        # every additional territory's otherwise-local ids globally unique.
        if region_id==AUTHORING.SUNMANE:
            return 'SunmaneBase' if base else name
        return region_id+'Base' if base else region_id+'_'+name
    def add(name,faces,surface,uv_source,colors=None,walk=False,blend=False):
        faces=np.asarray(faces,float).reshape(-1,3,3)
        if walk:
            faces,uv_source,colors,encoding=encoded_road_faces(faces,uv_source,colors)
            road_encoding.append({'name':name,**encoding})
        if not len(faces):return
        material,density=authored_surface_material(builder,surface,name,blend=blend)
        vertices=faces.reshape(-1,3);indices=np.arange(len(vertices),dtype=np.int32)
        uv=_rotated_uv(np.asarray(uv_source,float).reshape(-1,2),surface,density)
        # Road normals must agree with the represented, possibly microscopic
        # face, not with its pre-encoding sliver. Other overlay normals stay as-is.
        normal_faces=faces.astype(np.float32).astype(float) if walk else faces
        face_normal=np.cross(normal_faces[:,1]-normal_faces[:,0],normal_faces[:,2]-normal_faces[:,0])
        face_normal/=np.maximum(np.linalg.norm(face_normal,axis=1,keepdims=True),1e-12)
        mesh=M.Mesh(positions=vertices,normals=np.repeat(face_normal,3,axis=0),uvs=uv,
                    colors=None if colors is None else np.asarray(colors,float).reshape(-1,4),
                    indices=indices,material=material)
        centres=faces.mean(axis=1);owner=world.owner_at(centres[:,0],centres[:,2]).astype(int)
        cx=np.floor((centres[:,0]-world.x0)/CHUNK).astype(int);cz=np.floor((centres[:,2]-world.z0)/CHUNK).astype(int)
        overlays.append({'name':('Walk_' if walk else 'AuthoredGround_')+name,'mesh':mesh,
                         'keys':owner*10000+cz*100+cx})
    positions=np.stack([world.gx,world.height+.006,world.gz],axis=-1).reshape(-1,3)
    for region_id,snapshot in snapshots.items():
        translation=snapshot.translation
        # Base surface follows this territory's exact owned terrain cells. A
        # slight visual lift avoids depth fighting; collision uses the shared field.
        owner=world.ids.index(region_id);row,col=np.nonzero(world.owner[:-1,:-1]==owner)
        nx=len(world.x);a=row*nx+col
        tri=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1).reshape(-1,3)
        preview_uv=float(snapshot.document['terrain']['previewUvMetresInverse'])
        local_uv=(positions[tri][...,[0,2]]-translation[[0,2]])*preview_uv
        base_colors=getattr(snapshot,'base_colors',lambda:None)();vertex_colors=None
        if base_colors is not None:
            terrain=snapshot.document['terrain'];origin=np.asarray(terrain['origin'],float)
            cell=float(terrain['cellMetres']);local=positions[tri][...,[0,2]]-translation[[0,2]]
            indices=np.rint((local-origin)/cell).astype(int)
            reconstructed=origin+indices*cell
            if (np.abs(reconstructed-local)>1e-6).any() or (indices<0).any() or \
                    (indices[...,0]>=snapshot.terrain_width).any() or \
                    (indices[...,1]>=snapshot.terrain_height).any():
                raise AUTHORING.AuthoringError(
                    f'{region_id}: owned terrain vertices fall outside exact baseColors grid')
            vertex_colors=base_colors[indices[...,1],indices[...,0]].astype(float)/255.
        add(node_name(region_id,'',base=True),positions[tri],snapshot.document['terrain']['baseSurface'],local_uv,
            vertex_colors)
        ordered_regions=sorted(snapshot.document['groundRegions'],key=lambda value:(value['priority'],value['id']))
        for layer,ground_region in enumerate(ordered_regions):
            if not ground_region['enabled']:continue
            faces,uv,colors=ground_region_faces(world,snapshot,ground_region,tri,positions,layer)
            add(node_name(region_id,ground_region['id']),faces,ground_region['surface'],uv,colors,blend=True)
        for path in snapshot.document['paths']:
            if path['kind']!='road':continue
            faces,uv,colors=conform_road_faces(world,*authored_road_faces(world,snapshot,path))
            road_override=path['surface'].get('roadOverrides')
            add(node_name(region_id,path['id']),faces,path['surface'],uv,
                colors,walk=True,blend=road_override is not None)
    world.authored_road_encoding_report=road_encoding
    return overlays


def _mesh_faces(mesh,selected):
    """Copy selected faces from a source mesh into one compact chunk mesh."""
    faces=np.asarray(mesh.indices).reshape(-1,3)[selected]
    unique,inverse=np.unique(faces,return_inverse=True)
    return M.Mesh(positions=mesh.positions[unique],normals=mesh.normals[unique],uvs=mesh.uvs[unique],
                  colors=None if mesh.colors is None else mesh.colors[unique],indices=inverse.ravel(),
                  material=mesh.material)


def png(array):
    buffer=io.BytesIO();Image.fromarray(array).save(buffer,format='PNG',optimize=False);return buffer.getvalue()


def _wet_gradient(values,wet,axis):
    """One-sided bank derivatives use only real neighbouring water levels."""
    before=np.roll(values,1,axis=axis);after=np.roll(values,-1,axis=axis)
    left=wet&np.roll(wet,1,axis=axis);right=wet&np.roll(wet,-1,axis=axis)
    # A sea/river datum jump is not a derivative of either water plane. Keep
    # those actual wet heights, but do not extrapolate their discontinuity into
    # a dry bank. Authored river flow gradients are much gentler than this.
    left&=np.abs(values-before)<=.65*CELL;right&=np.abs(after-values)<=.65*CELL
    edge=[slice(None),slice(None)];edge[axis]=0;left[tuple(edge)]=False
    edge[axis]=-1;right[tuple(edge)]=False
    return np.where(left&right,(after-before)/(2*CELL),
        np.where(right,(after-values)/CELL,np.where(left,(values-before)/CELL,0.)))


def water_vertex_fields(world):
    """Continuous local surface and signed shoreline, from shared authority.

    A dry riverbank used to inherit sea level at its water-mesh corner. Extend
    the adjoining hydraulic plane there instead. The signed shoreline remains
    the union of real sea depth and authored river/lake domains: a high lake
    cannot flood a neighbouring dry tile just because its corner was extended.
    """
    wet=np.asarray(world.water['mask'],bool);surface=np.asarray(world.water['surface'],float)
    level=surface.copy();signed=surface-world.height-.015
    if not wet.any():return level,np.minimum(signed,0.)
    nearest=distance_transform_edt(~wet,return_distances=False,return_indices=True)
    iz,ix=np.indices(wet.shape);nz,nx=nearest
    gx=_wet_gradient(surface,wet,1);gz=_wet_gradient(surface,wet,0)
    extrapolated=surface[nz,nx]+gx[nz,nx]*(ix-nx)*CELL+gz[nz,nx]*(iz-nz)*CELL
    sea=float(world.plan.get('sea_level',0.))
    level[~wet]=np.maximum(sea,extrapolated[~wet])
    # Only mixed shoreline triangles need exact signed domain distances.
    border=binary_dilation(wet,structure=np.ones((3,3),bool))&binary_dilation(~wet,structure=np.ones((3,3),bool))
    x,z=world.gx[border],world.gz[border];height=world.height[border]
    value=sea-height-.015
    for river in world.plan.get('rivers',[]):
        distance,hydraulic,width=L.river_field(x,z,river)
        value=np.maximum(value,np.minimum(width-distance,hydraulic-height-.015))
    for lake in world.plan.get('lakes',[]):
        domain=(1-L._ellipse_distance(x,z,lake))*min(lake['radii'])
        value=np.maximum(value,np.minimum(domain,float(lake['level'])-height-.015))
    # Tiny equality differences at an exact authored domain edge carry no area.
    expected=wet[border];mismatch=((value>0)!=expected)&(np.abs(value)>1e-7)
    if mismatch.any():
        first=np.flatnonzero(mismatch)[0]
        raise ValueError(f'Water export domain disagrees with shared wet/dry authority at {[float(x[first]),float(z[first])]}')
    signed[border]=value
    return level,signed


def clipped_water_surface(world,positions,cells):
    """One global water mesh; split its already clipped faces by source cell."""
    level,signed=water_vertex_fields(world)
    original=positions.copy();original[:,1]=level.ravel()
    scalar=signed.ravel();source=cells.reshape(-1,3)
    positive=scalar[source]>0;counts=positive.sum(axis=1)
    full=counts==3;partial=np.flatnonzero((counts>0)&~full)
    faces=source[full].tolist();source_cells=(np.flatnonzero(full)//2).tolist()
    wet=np.asarray(world.water['mask'],bool);surface=np.asarray(world.water['surface'],float)
    gradient=np.c_[_wet_gradient(surface,wet,1).ravel(),_wet_gradient(surface,wet,0).ravel()]
    # Ocean water is horizontal even beside the last sloping river station.
    gradient[np.abs(surface.ravel()-float(world.plan.get('sea_level',0.)))<1e-9]=0.
    intersections={};extra=[];wet_endpoints=[]
    def crossing(a,b):
        # Canonical orientation makes the same source edge bit-identical from
        # both triangles, named territories and96m streaming chunks.
        a,b=sorted((int(a),int(b)))
        key=(a,b)
        if key not in intersections:
            t=scalar[a]/(scalar[a]-scalar[b])
            intersections[key]=len(original)+len(extra)
            point=original[a]+t*(original[b]-original[a])
            # A dry vertex can border two different water bodies. The wet end
            # of this actual edge supplies its hydraulic plane; a nearby river
            # must not lift the shore of an otherwise sea-level triangle.
            endpoint=a if scalar[a]>0 else b
            point[1]=original[endpoint,1]+np.dot(gradient[endpoint],point[[0,2]]-original[endpoint,[0,2]])
            extra.append(point);wet_endpoints.append(endpoint)
        return intersections[key]
    for number in partial:
        triangle=source[number];polygon=[]
        for a,b in zip(triangle,np.roll(triangle,-1)):
            if scalar[a]>0:polygon.append(int(a))
            if (scalar[a]>0)!=(scalar[b]>0):polygon.append(crossing(a,b))
        polygon=list(dict.fromkeys(polygon))
        for i in range(1,len(polygon)-1):
            faces.append([polygon[0],polygon[i],polygon[i+1]]);source_cells.append(int(number//2))
    extra=np.asarray(extra).reshape(-1,3)
    if len(extra):
        # Evaluate the wet endpoint's actual hydraulic body at the final XZ.
        # Independent finite-difference planes can disagree where two clipped
        # edges almost meet a dry corner, producing a steep hairline triangle.
        # The authored river profile is continuous there; lakes/sea stay flat.
        # Choose the provider at the wet end, never at a dry point that could
        # lie in another nearby basin. Preserve every original wet vertex.
        extra[:,[0,2]]=extra[:,[0,2]].astype(np.float32)
        endpoints=original[np.asarray(wet_endpoints)]
        sea=float(world.plan.get('sea_level',0.))
        is_sea=np.abs(endpoints[:,1]-sea)<1e-9
        extra[is_sea,1]=sea
        for river in world.plan.get('rivers',[]):
            distance,profile,width=L.river_field(endpoints[:,0],endpoints[:,2],river)
            use=(~is_sea)&(distance<=width+1e-8)&np.isclose(profile,endpoints[:,1],atol=1e-7,rtol=0)
            if use.any():extra[use,1]=L.river_field(extra[use,0],extra[use,2],river)[1]
        for lake in world.plan.get('lakes',[]):
            use=(~is_sea)&(L._ellipse_distance(endpoints[:,0],endpoints[:,2],lake)<=1.+1e-8)&np.isclose(endpoints[:,1],lake['level'],atol=1e-7,rtol=0)
            extra[use,1]=float(lake['level'])
    vertices=np.vstack((original,extra)).astype(np.float32)
    faces=np.asarray(faces,np.int32).reshape(-1,3);source_cells=np.asarray(source_cells,np.int32)
    if len(faces):
        p=vertices[faces].astype(float)
        area=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])[:,1]
        if (area<-1e-8).any():raise ValueError('Clipped water face reverses its source winding')
        keep=area>1e-8;faces=faces[keep];source_cells=source_cells[keep]
    return {'positions':vertices,'triangles':faces,'sourceCells':source_cells,
        'report':{'sourceShoreTriangles':len(partial),'sharedEdgeIntersections':len(intersections),
                'waterTriangles':len(faces),'policy':'Clip actual hydraulic/ground and river/lake domain intersections once globally; shared authoritative wet/dry vertices unchanged.'}}


_WATER_SAMPLE_CACHE=None


def sample_water_surface(world,x,z):
    """Sample the same float32 clipped water faces that the GLB contains.

    A two-wet-vertex clipped quad can have two different planes. Sampling its
    emitted fan, rather than extending one source triangle, keeps collision
    depth identical to the visible surface. One content-addressed mesh cache
    covers the twelve named exports and invalidates on any field/plan edit.
    """
    global _WATER_SAMPLE_CACHE
    digest=hashlib.sha256()
    for values in (world.gx,world.gz,world.height,world.water['mask'],world.water['surface']):
        a=np.ascontiguousarray(values);digest.update(str((a.shape,a.dtype.str)).encode());digest.update(a.view(np.uint8))
    digest.update(json.dumps(world.plan,sort_keys=True,separators=(',',':')).encode())
    stamp=digest.digest()
    if _WATER_SAMPLE_CACHE is None or _WATER_SAMPLE_CACHE[0]!=stamp:
        nz,nx=world.height.shape;row,col=np.indices((nz-1,nx-1));a=(row*nx+col).ravel()
        cells=np.stack((a,a+nx,a+1,a+1,a+nx,a+nx+1),axis=1)
        points=np.c_[world.gx.ravel(),world.height.ravel(),world.gz.ravel()]
        mesh=clipped_water_surface(world,points,cells)
        order=np.argsort(mesh['sourceCells'],kind='stable')
        faces=mesh['positions'][mesh['triangles'][order]].astype(float)
        counts=np.bincount(mesh['sourceCells'],minlength=(nx-1)*(nz-1))
        offsets=np.r_[0,np.cumsum(counts)]
        _WATER_SAMPLE_CACHE=(stamp,faces,counts,offsets)
    _,faces,counts,offsets=_WATER_SAMPLE_CACHE
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float));shape=x.shape
    xx=x.ravel();zz=z.ravel();nz,nx=world.height.shape
    min_x,min_z=float(world.gx[0,0]),float(world.gz[0,0])
    max_x,max_z=float(world.gx[0,-1]),float(world.gz[-1,0])
    spacing_x=float(world.gx[0,1]-min_x);spacing_z=float(world.gz[1,0]-min_z)
    valid=np.isfinite(xx)&np.isfinite(zz)&(xx>=min_x)&(xx<=max_x)&(zz>=min_z)&(zz<=max_z)
    ix=np.clip(np.floor(np.where(valid,(xx-min_x)/spacing_x,0)).astype(int),0,nx-2)
    iz=np.clip(np.floor(np.where(valid,(zz-min_z)/spacing_z,0)).astype(int),0,nz-2)
    cell=iz*(nx-1)+ix;wet=np.zeros(len(xx),bool)
    top=np.full(len(xx),float(world.plan.get('sea_level',0.)))
    for slot in range(int(counts.max(initial=0))):
        at=np.flatnonzero(valid&(counts[cell]>slot))
        if not len(at):continue
        triangle=faces[offsets[cell[at]]+slot];a,b,c=triangle[:,0],triangle[:,1],triangle[:,2]
        u=b[:,[0,2]]-a[:,[0,2]];v=c[:,[0,2]]-a[:,[0,2]];q=np.c_[xx[at],zz[at]]-a[:,[0,2]]
        determinant=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        s=(q[:,0]*v[:,1]-q[:,1]*v[:,0])/determinant
        t=(u[:,0]*q[:,1]-u[:,1]*q[:,0])/determinant
        inside=(s>=-1e-8)&(t>=-1e-8)&(s+t<=1+1e-8)
        yy=a[:,1]+s*(b[:,1]-a[:,1])+t*(c[:,1]-a[:,1]);at=at[inside];yy=yy[inside]
        top[at]=np.where(wet[at],np.maximum(top[at],yy),yy);wet[at]=True
    return wet.reshape(shape),top.reshape(shape)


def partition_surface(world,path):
    builder=G.GltfBuilder('Eloria single continental surface: split only after final landscape composition')
    rng=np.random.default_rng(world.plan['seed']+19)
    grain=rng.uniform(.84,1.,(128,128))
    # Restrained shared ground grain. Biome and road colour are global vertex
    # attributes, so material boundaries cannot follow territory partitions.
    image=np.repeat((grain[...,None]*255).astype(np.uint8),3,axis=2)
    builder.add_image('continental-ground',png(image))
    builder.add_material(G.Material('continental_ground',base_color_texture='continental-ground',roughness=.95))
    xx,zz=np.meshgrid(np.arange(128),np.arange(128))
    ripple=.9+.06*np.sin(xx*.34+np.sin(zz*.15))+.025*np.sin(zz*.7)
    water_texture=np.clip(ripple[...,None]*np.array([104,161,166]),0,255).astype(np.uint8)
    builder.add_image('continental-water',png(water_texture))
    builder.add_material(G.Material('water_sea',base_color_texture='continental-water',roughness=.55,double_sided=True))
    nx=len(world.x);nz=len(world.z)
    dz,dx=np.gradient(world.height,CELL,CELL)
    normals=np.stack([-dx,np.ones_like(dx),-dz],axis=-1)
    normals/=np.linalg.norm(normals,axis=-1,keepdims=True)
    positions=np.stack([world.gx,world.height,world.gz],axis=-1).reshape(-1,3)
    colors=L.terrain_color(world.gx,world.gz,height=world.height,plan=world.plan)
    road=np.clip(1-L.smoothstep(.70,1.28,np.where(np.isfinite(world.road_distance),world.road_distance,1000)),0,1)
    road_color=np.array([.49,.435,.315])**2.2
    colors=colors*(1-road[...,None]) + road_color*road[...,None]
    colors=np.concatenate([np.clip(colors/0.92,0,1),np.ones((*colors.shape[:2],1))],axis=-1).reshape(-1,4)
    uvs=np.c_[world.gx.ravel(),world.gz.ravel()]*.17
    row,col=np.indices(world.owner.shape);a=(row*nx+col).ravel()
    cells=np.stack([a,a+nx,a+1,a+1,a+nx,a+nx+1],axis=1)
    chunk_x=np.floor((world.gx[:-1,:-1]-world.x0)/CHUNK).astype(int)
    chunk_z=np.floor((world.gz[:-1,:-1]-world.z0)/CHUNK).astype(int)
    key=world.owner*10000+chunk_z*100+chunk_x
    water=clipped_water_surface(world,positions,cells)
    world.water_export_report=water['report']
    water_keys=key.ravel()[water['sourceCells']]
    overlays=authored_overlays(world,builder)
    authored_water=[];water_slot=np.full(len(water['triangles']),-1,int)
    snapshots=dict(getattr(world,'authoring_snapshots',{}))
    snapshot=getattr(world,'authoring_snapshot',None)
    if snapshot is not None:snapshots.setdefault(snapshot.document.get('regionId',AUTHORING.SUNMANE),snapshot)
    if snapshots and len(water['triangles']):
        centres=water['positions'][water['triangles']].mean(axis=1)
        by_id={river['id']:river for river in world.plan.get('rivers',())}
        for region_id,snapshot in snapshots.items():
            for path_record in snapshot.document['paths']:
                if path_record['kind']!='river':continue
                identity=path_record.get('replacesPlanFeatureId') or path_record['id'];river=by_id.get(identity)
                if river is None:continue
                distance,_,width=L.river_field(centres[:,0],centres[:,2],river)
                selected=(distance<=width+1e-8)&(water_slot<0)
                material_name=(path_record['id'] if region_id==AUTHORING.SUNMANE else
                               region_id+'_'+path_record['id'])+'_water'
                material,density=authored_surface_material(
                    builder,path_record['surface'],material_name)
                water_slot[selected]=len(authored_water)
                node_id=(path_record['id'] if region_id==AUTHORING.SUNMANE else
                         region_id+'_'+path_record['id'])
                authored_water.append({'id':path_record['id'],'nodeId':node_id,'region':region_id,
                    'surface':path_record['surface'],'material':material,
                    'density':density,'translation':snapshot.translation,
                    'triangles':int(selected.sum())})
    world.authored_overlay_report={
        'nodes':[{'name':item['name'],'triangles':int(item['mesh'].triangle_count)} for item in overlays],
        'triangles':sum(int(item['mesh'].triangle_count) for item in overlays),
        'roadEncoding':getattr(world,'authored_road_encoding_report',[]),
        'waterMaterials':[{key:value for key,value in item.items()
                           if key not in ('surface','density','translation','nodeId')}
                          for item in authored_water]}
    output={r:{} for r in world.ids}
    for value in np.unique(key):
        owner=int(value//10000);cz=int(value%10000//100);cx=int(value%100)
        region=world.ids[owner];chunk=f'{cx:02d}_{cz:02d}'
        selected=np.flatnonzero(key.ravel()==value)
        roots=[];bounds=[]
        surfaces=[('Terrain',cells[selected].ravel(),positions,'continental_ground',colors,None,None,None),
                  ('Water',water['triangles'][(water_keys==value)&(water_slot<0)].ravel(),
                   water['positions'],'water_sea',None,None,None,None)]
        for slot,item in enumerate(authored_water):
            surfaces.append((f"Water_{item['nodeId']}",
                water['triangles'][(water_keys==value)&(water_slot==slot)].ravel(),
                water['positions'],item['material'],None,item['surface'],item['density'],item['translation']))
        for kind,indices,vertices,material,color,surface,density,uv_translation in surfaces:
            if not len(indices):continue
            unique,inverse=np.unique(indices,return_inverse=True)
            name=f'{kind}_{region}_{chunk}'
            n=normals.reshape(-1,3)[unique] if kind=='Terrain' else np.tile([0.,1.,0.],(len(unique),1))
            if kind=='Terrain':texture_uv=uvs[unique]
            elif surface is None:texture_uv=vertices[unique][:,[0,2]]*.17
            else:texture_uv=_rotated_uv(vertices[unique][:,[0,2]]-uv_translation[[0,2]],surface,density)
            piece=M.Mesh(positions=vertices[unique],normals=n,uvs=texture_uv,colors=color[unique] if color is not None else None,indices=inverse,material=material)
            builder.add_mesh(name,piece,with_tangents=surface is not None)
            index=builder.add_node(G.Node(name,mesh=name))
            roots.append(index);bounds.append(piece.bounds())
        for overlay in overlays:
            overlay_selected=np.flatnonzero(overlay['keys']==value)
            if not len(overlay_selected):continue
            piece=_mesh_faces(overlay['mesh'],overlay_selected)
            name=f"{overlay['name']}_{region}_{chunk}"
            builder.add_mesh(name,piece,with_tangents=True)
            roots.append(builder.add_node(G.Node(name,mesh=name)))
            bounds.append(piece.bounds())
        if roots:
            output[region][chunk]={'roots':roots,'bounds':[np.min([b[0] for b in bounds],axis=0),np.max([b[1] for b in bounds],axis=0)],
                                   'cell':[cx,cz],'terrainCells':len(selected)}
    builder.write_glb(str(path))
    return output
