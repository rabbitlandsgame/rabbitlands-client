"""Bake supplied multi-view character studies into existing MPFB paint channels.

Offline only: face replaces one existing1024 PNG. Hair adds non-overlapping
TEXCOORD_1 tiles and one embedded1024 painted atlas; existing COLOR_0 RGB is
also painted as fallback, preserving its alpha/root pinning. Original positions,
normals, indices, UV0, skin and skeleton arrays remain exact. Draw count stays
unchanged; each hair atlas adds5.33MiB RGBA8+mips before compression and one
texture sample. Inputs are actual-engine pose/camera registration and source art.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter, label, map_coordinates
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from fit_canonical import Glb, node_worlds


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def srgb_linear(v): return np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)
def linear_srgb(v): return np.where(v<=.0031308,v*12.92,1.055*np.maximum(v,0)**(1/2.4)-.055)


def transform(value):
    result=np.eye(4)
    result[:3,:3]=np.column_stack([value[k] for k in ['x','y','z']])
    result[:3,3]=value['origin']
    return result


def normalize(v): return v/np.maximum(np.linalg.norm(v,axis=-1,keepdims=True),1e-12)


class View:
    def __init__(self, record, directory):
        self.record=record;self.ref=record['reference'];self.name=record['view']
        self.image=np.asarray(Image.open(self.ref['path']).convert('RGB'),dtype=np.float32)/255
        self.roi=np.array(self.ref['portrait_roi'],float)
        self.camera=transform(record['camera']['transform'])
        self.tan=np.tan(np.radians(record['camera']['fov_degrees'])/2)
        self.height,self.width=self.image.shape[:2]
        mask=Image.new('L',(self.width,self.height),0)
        ImageDraw.Draw(mask).polygon([tuple(v) for v in self.ref['face_paint_polygon']],fill=255)
        self.face_binary=np.asarray(mask)>0
        self.face_outline=self.face_binary.copy()
        # Reference locks cross the face outline. They belong on the separate
        # hair mesh, never in a skin map. Keep lip pigment below the eye band.
        rgb=self.image*255;r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        yy,xx=np.indices(self.face_binary.shape)
        eye_y=float(np.mean([p[1] for k,p in self.ref['landmarks'].items() if k in ['eye_image_left','eye_image_right','eye_visible']]))
        mouth=self.ref['landmarks'].get('cupid_bow',self.ref['landmarks'].get('upper_lip_profile'))
        lip_zone=np.zeros_like(self.face_binary) if mouth is None else ((xx-mouth[0])**2/32**2+(yy-mouth[1])**2/18**2<1)
        red_lock=(r>1.65*g)&(b<100)&(~lip_zone)
        dark_lock=(r<105)&(g<72)&(b<56)&(yy<eye_y-12)
        valid_skin=self.face_binary&(~binary_dilation(red_lock|dark_lock,iterations=1))
        nearest_skin=distance_transform_edt(~valid_skin,return_distances=False,return_indices=True)
        self.face_image=self.image.copy()
        removed=self.face_binary&(~valid_skin)
        self.face_image[removed]=self.image[nearest_skin[0][removed],nearest_skin[1][removed]]
        # A broad continuous feather avoids scalloped color seams where a
        # foreground lock crosses the face. Pigment comes from sanitized skin.
        self.face_weight=np.clip((distance_transform_edt(self.face_binary)-2)/16,0,1).astype(np.float32)
        self.tps,self.control_report=self.fit_warp()
        projection_file=record.get('projection_map',{}).get('file')
        self.projection_path=directory/projection_file if projection_file else None
        self.projection=None

    def project(self, world):
        local=(world-self.camera[:3,3])@self.camera[:3,:3]
        depth=-local[:,2]
        x=.5+.5*local[:,0]/np.maximum(depth*self.tan*(800/900),1e-8)
        y=.5-.5*local[:,1]/np.maximum(depth*self.tan,1e-8)
        pixels=np.column_stack((self.roi[0]+x*(self.roi[2]-self.roi[0]),
                                self.roi[1]+y*(self.roi[3]-self.roi[1])))
        return pixels,depth

    def ndot(self, world, normal):
        return np.maximum(np.sum(normal*normalize(self.camera[:3,3]-world),axis=1),0)

    def fit_warp(self):
        source=[];target=[];keys=[]
        model=self.record['landmarks_capture_pixels'];art=self.ref['landmarks']
        aliases={'eye_visible':'eye_image_right','eye_inner_visible':'eye_inner_right',
                 'eye_outer_visible':'eye_outer_right','mouth_corner_visible':'mouth_right',
                 'jaw_angle_visible':'jaw_right','ear_tragus':'ear_tragus_right',
                 'ear_top':'ear_top_right','ear_lobe':'ear_lobe_right','brow_peak':'brow_inner_right'}
        for key,point in art.items():
            mk=aliases.get(key,key)
            if mk not in model: continue
            p=np.array(model[mk])/np.array([800,900])*(self.roi[2:]-self.roi[:2])+self.roi[:2]
            source.append(p);target.append(point);keys.append(key)
        source=np.array(source);target=np.array(target)
        if len(source)<5: return None,{'landmarks':len(source),'method':'identity; too few anchors'}
        source,unique=np.unique(np.round(source,4),axis=0,return_index=True)
        target=target[unique];keys=[keys[i] for i in unique]
        warp=RBFInterpolator(source/100,(target-source)/100,kernel='thin_plate_spline',smoothing=.0002)
        fitted=source+warp(source/100)*100
        return warp,{'landmarks':len(source),'keys':keys,'before_rms_px':float(np.sqrt(np.mean((source-target)**2))),
                     'after_rms_px':float(np.sqrt(np.mean((fitted-target)**2))),
                     'maximum_control_residual_px':float(np.linalg.norm(fitted-target,axis=1).max()),
                     'source_points':source.tolist(),'target_points':target.tolist(),
                     'note':'Control fit is an authoring registration, not independent likeness validation.'}

    def warp(self, pixels):
        if self.tps is None: return pixels
        delta=self.tps(pixels/100)*100
        length=np.linalg.norm(delta,axis=1)
        delta*=np.minimum(1,45/np.maximum(length,1e-9))[:,None]
        return pixels+delta

    def sample(self, pixels, image=None):
        source=self.image if image is None else image
        return np.column_stack([map_coordinates(source[:,:,c],[pixels[:,1],pixels[:,0]],order=1,mode='nearest') for c in range(3)])

    def face_samples(self, world, normal):
        pixels,depth=self.project(world);warped=self.warp(pixels)
        valid=(warped[:,0]>=0)&(warped[:,0]<self.width)&(warped[:,1]>=0)&(warped[:,1]<self.height)&(depth>0)
        feather=map_coordinates(self.face_weight,[warped[:,1],warped[:,0]],order=1,mode='constant',cval=0)
        ndot=self.ndot(world,normal)
        weight=valid*feather*ndot**4
        return srgb_linear(self.sample(warped,self.face_image)),weight,feather

    def prepare_hair(self, female):
        rgb=self.image*255;r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        dark=(r>1.5*g)&(g<165)&(b<120) if female else (r<175)&(g<130)&(b<110)&(r>g*1.03)
        points=self.ref['landmarks']
        ey=float(points.get('eye_image_left',points.get('eye_visible'))[1])
        chin=float(points['chin'][1]);yy,xx=np.indices(dark.shape)
        region=(xx>self.roi[0]-10)&(xx<self.roi[2]+10)&(yy<chin+28)&(~self.face_outline)
        seed=dark&region
        components,count=label(seed);keep=np.zeros(count+1,bool)
        crown=seed&(yy<ey-30)
        keep[np.unique(components[crown])]=True;keep[0]=False
        mask=keep[components]
        # Recover bright painted hair ridges adjacent to the dark color seed;
        # a strict dark-RGB cutoff alone would erase the reference highlights.
        warm=(r>g*(1.15 if female else 1.08))&(g>b*1.08)&(r<250)&(g<215)&(b<180)&region
        mask|=binary_dilation(mask,iterations=3)&warm
        # The ear and upper neck can touch a red-hair seed in the source art.
        # Below the brow band retain saturated hair, rejecting warm bare skin.
        bare_skin=(yy>ey-12)&(r>100)&(g>55)&(r<g*1.85)
        mask&=~bare_skin
        if mask.sum()<100: raise ValueError('Insufficient reference hair mask: '+self.ref['path'])
        self.hair_mask=mask
        self.hair_distance,self.hair_nearest=distance_transform_edt(~mask,return_indices=True)
        self.hair_median=srgb_linear(np.median(self.image[mask],axis=0))

    def hair_samples(self, world, normal):
        pixels,depth=self.project(world)
        x=np.clip(np.rint(pixels[:,0]).astype(int),0,self.width-1);y=np.clip(np.rint(pixels[:,1]).astype(int),0,self.height-1)
        distance=self.hair_distance[y,x]
        nearest=np.column_stack((self.hair_nearest[1,y,x],self.hair_nearest[0,y,x]))
        # Bilinear reads near a wisp edge must not import the pale background.
        # Use continuous sampling only where all four source texels are hair.
        x0=np.clip(np.floor(pixels[:,0]).astype(int),0,self.width-2)
        y0=np.clip(np.floor(pixels[:,1]).astype(int),0,self.height-2)
        safe=self.hair_mask[y0,x0]&self.hair_mask[y0,x0+1]&self.hair_mask[y0+1,x0]&self.hair_mask[y0+1,x0+1]
        nearest[safe]=pixels[safe]
        inside=(pixels[:,0]>=0)&(pixels[:,0]<self.width)&(pixels[:,1]>=0)&(pixels[:,1]<self.height)&(depth>0)
        weight=inside*self.ndot(world,normal)**4*np.clip(1-(distance/24)**2,0,1)
        return srgb_linear(self.sample(nearest)),weight


def image_bytes(glb,index):
    image=glb.doc['images'][index];view=glb.doc['bufferViews'][image['bufferView']]
    start=view.get('byteOffset',0);return bytes(glb.binary[start:start+view['byteLength']])


def raster_triangles(uv,triangles,size):
    for tri in triangles:
        p=uv[tri]*[size[0],size[1]]-.5
        low=np.maximum(np.floor(p.min(0)).astype(int),0);high=np.minimum(np.ceil(p.max(0)).astype(int),np.array(size)-1)
        if np.any(high<low): continue
        denominator=(p[1,1]-p[2,1])*(p[0,0]-p[2,0])+(p[2,0]-p[1,0])*(p[0,1]-p[2,1])
        if abs(denominator)<1e-10: continue
        xx,yy=np.meshgrid(np.arange(low[0],high[0]+1),np.arange(low[1],high[1]+1));x=xx.ravel();y=yy.ravel()
        a=((p[1,1]-p[2,1])*(x-p[2,0])+(p[2,0]-p[1,0])*(y-p[2,1]))/denominator
        b=((p[2,1]-p[0,1])*(x-p[2,0])+(p[0,0]-p[2,0])*(y-p[2,1]))/denominator
        c=1-a-b;inside=(a>=-1e-6)&(b>=-1e-6)&(c>=-1e-6)
        if inside.any(): yield tri,x[inside],y[inside],np.column_stack((a[inside],b[inside],c[inside]))


def bake_face(path,output,views,debug,base_skin=None):
    glb=Glb(path);before=Glb(path)
    source_hash=sha(path)
    if any(view.projection_path is None for view in views):
        raise ValueError('Face baking requires captured body projection maps; camera-only records support hair baking')
    if any(view.record.get('model_sha256')!=source_hash for view in views):
        raise ValueError('Face projections are stale: capture this exact input model before baking')
    body=next(n for n in glb.doc['nodes'] if n.get('name')=='body')
    primitive=glb.doc['meshes'][body['mesh']]['primitives'][0]
    material=glb.doc['materials'][primitive['material']]['pbrMetallicRoughness']
    image_index=glb.doc['textures'][material['baseColorTexture']['index']]['source']
    original=Image.open(base_skin) if base_skin else Image.open(io.BytesIO(image_bytes(glb,image_index)))
    base=np.array(original.convert('RGBA'));height,width=base.shape[:2]
    if (width,height)!=(1024,1024): raise ValueError('Expected existing1024 skin atlas')
    uv=glb.read(primitive['attributes']['TEXCOORD_0']);triangles=glb.read(primitive['indices']).reshape(-1,3)
    worlds=node_worlds(glb.doc);to_head=np.linalg.inv(worlds['Head'])@worlds['body']
    positions=glb.read(primitive['attributes']['POSITION'])
    local=positions@to_head[:3,:3].T+to_head[:3,3]
    metadata=json.loads((path.parent/'fit.json').read_text())['face_frame_head_local']
    mouth_y=float(metadata['mouth_y']);eye_z=float(metadata['eye_z'])
    # Head exports retain separate disconnected UV islands for the mouth cavity,
    # tongue and socket backs. Paint only the largest connected skin island.
    edge=np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]])
    _,islands=connected_components(coo_matrix((np.ones(len(edge)),(edge[:,0],edge[:,1])),shape=(len(uv),len(uv))),directed=False)
    main_island=int(np.bincount(islands).argmax())
    paint_triangles=triangles[np.all(islands[triangles]==main_island,axis=1)]
    total=np.zeros((height,width));paint=np.zeros((height,width,3));strength=np.zeros((height,width));feature_gain=np.zeros((height,width))
    for view in views:
        projection=json.loads(view.projection_path.read_text())
        world=np.asarray(projection['vertex_positions_world']);normal=np.asarray(projection['vertex_normals_world'])
        captured=np.asarray(projection['triangle_indices']).reshape(-1,3)
        # Godot reverses glTF triangle winding on import, retaining vertex IDs.
        same_topology=np.array_equal(captured,triangles) or np.array_equal(captured,triangles[:,[0,2,1]])
        same_uv=np.allclose(np.asarray(projection['vertex_uv']),uv,atol=1e-6)
        if len(world)!=len(uv) or not same_topology or not same_uv:
            raise ValueError('Projection map does not match input head topology')
        for tri,x,y,bary in raster_triangles(uv,paint_triangles,(width,height)):
            positions=bary@world[tri];directions=normalize(bary@normal[tri])
            colors,weight,feather=view.face_samples(positions,directions)
            rest=bary@local[tri]
            # The continuous foundation remains intact on the neck, ears and
            # lateral jaw. Authoring pigment cannot migrate below the chin.
            def smooth(low,high,value):
                phase=np.clip((value-low)/(high-low),0,1);return phase*phase*(3-2*phase)
            region=smooth(mouth_y-.052,mouth_y-.015,rest[:,1])
            region*=1-smooth(.055,.085,np.abs(rest[:,0]))
            region*=smooth(eye_z-.035,eye_z-.005,rest[:,2])
            weight*=region;feather*=region
            mouth_detail=np.exp(-np.power(rest[:,0]/.038,4)-np.square((rest[:,1]-mouth_y)/.014))
            eye_detail=np.zeros(len(rest))
            for key in ['eye_left','eye_right']:
                eye=np.asarray(metadata[key]);eye_detail=np.maximum(eye_detail,np.exp(-np.power((rest[:,0]-eye[0])/.029,4)-np.square((rest[:,1]-eye[1]-.008)/.021)))
            nose_detail=np.exp(-np.square(rest[:,0]/.020)-np.square((rest[:,1]-(float(metadata['eye_y'])-.036))/.022))
            feature_gain[y,x]=np.maximum(feature_gain[y,x],.30+.70*np.maximum.reduce([mouth_detail,eye_detail,nose_detail]))
            paint[y,x]+=colors*weight[:,None];total[y,x]+=weight
            strength[y,x]=np.maximum(strength[y,x],feather*np.clip(weight/.035,0,1))
    used=total>1e-7
    average=paint/np.maximum(total[:,:,None],1e-9)
    source_linear=srgb_linear(base[:,:,:3]/255)
    # Reference renders contain painted studio lighting. Transfer their local
    # pigment/detail residual, removing the low-frequency color/illumination
    # difference so the original continuous skin remains the foundation.
    log_ratio=np.log(np.maximum(average,.008))-np.log(np.maximum(source_linear,.008))
    density=gaussian_filter(used.astype(float),18)
    low_frequency=np.stack([gaussian_filter(log_ratio[:,:,c]*used,18)/np.maximum(density,1e-8) for c in range(3)],axis=2)
    residual=np.clip(log_ratio-low_frequency,-.40,.24)*feature_gain[:,:,None]
    residual=np.stack([gaussian_filter(residual[:,:,c]*used,.65) for c in range(3)],axis=2)
    # The UV-space feather additionally removes sampling speckles around a
    # boundary; smooth local detail never changes an unpainted neck texel.
    strength*=np.clip(distance_transform_edt(used)/12,0,1)
    final=np.clip(source_linear*np.exp(residual*strength[:,:,None]),0,1)
    result=base.copy();result[used,:3]=np.clip(np.rint(linear_srgb(final[used])*255),0,255).astype(np.uint8)
    changed=np.any(result[:,:,:3]!=base[:,:,:3],axis=2)
    png=Image.fromarray(result if original.mode=='RGBA' else result[:,:,:3])
    data=io.BytesIO();png.save(data,format='PNG',optimize=True)
    glb.doc['images'][image_index]['bufferView']=glb.blob(data.getvalue())
    glb.write(output);after=Glb(output)
    equal=[np.array_equal(before.read(i),after.read(i)) for i in range(len(before.doc['accessors']))]
    other_images=all(image_bytes(before,i)==image_bytes(after,i) for i in range(len(before.doc['images'])) if i!=image_index)
    if not all(equal) or not other_images: raise AssertionError('Face bake changed mesh or another image')
    png.save(debug/'face-reference.png');Image.fromarray(np.uint8(np.clip(strength,0,1)*255)).save(debug/'face-coverage.png')
    delta=result[:,:,:3].astype(int)-base[:,:,:3].astype(int)
    Image.fromarray(np.uint8(np.clip(delta*3+128,0,255))).save(debug/'face-delta-x3.png')
    return {'input_sha256':sha(path),'output_sha256':sha(output),'changed_skin_texels':int(changed.sum()),
            'base_skin_override':str(base_skin) if base_skin else None,'base_skin_sha256':sha(base_skin) if base_skin else None,
            'head_image_index':image_index,'all_accessors_exact':all(equal),'accessors':len(equal),
            'other_images_byte_exact':other_images,'alpha_exact':bool(np.array_equal(base[:,:,3],result[:,:,3])),
            'outside_coverage_pixels_exact':bool(np.array_equal(base[~used],result[~used])),
            'method':'Reference pigment/detail residual; Gaussian18 low-frequency lighting/color removal; Head-local neck/ear protection; broad source and UV feathers',
            'maximum_rgb_change':int(np.abs(delta).max()),'mean_rgb_change_painted':float(np.abs(delta[used]).mean()),
            'view_registration':[{'view':v.name,**v.control_report} for v in views]}


def bake_hair(path,output,views,sex):
    glb=Glb(path);before=Glb(path);worlds=node_worlds(glb.doc);reports=[]
    for view in views: view.prepare_hair(sex=='female')
    fallback=np.median(np.array([v.hair_median for v in views]),axis=0)*.80
    changed_accessors=[]
    for node in glb.doc['nodes']:
        if 'mesh' not in node: continue
        for primitive in glb.doc['meshes'][node['mesh']]['primitives']:
            attributes=primitive['attributes'];color_index=attributes.get('COLOR_0')
            if color_index is None: raise ValueError('Existing COLOR_0 RGBA is required; no new vertex attributes are allowed')
            points=glb.read(attributes['POSITION']).astype(float);normals=glb.read(attributes['NORMAL']).astype(float)
            original=glb.read(color_index);colors=np.zeros((len(points),3));weights=np.zeros(len(points))
            for view in views:
                posed=transform(view.record['skeleton_global'])@transform(view.record['head_global_pose'])@worlds[node.get('name','')]
                world=points@posed[:3,:3].T+posed[:3,3]
                normal=normalize(normals@np.linalg.inv(posed[:3,:3]))
                rgb,w=view.hair_samples(world,normal);colors+=rgb*w[:,None];weights+=w
            valid=weights>1e-6;paint=np.tile(fallback,(len(points),1));paint[valid]=colors[valid]/weights[valid,None]
            result=original.copy();a=glb.doc['accessors'][color_index]
            if a['componentType']==5121:
                result[:,:3]=np.clip(np.rint(paint*255),0,255).astype(np.uint8)
            elif a['componentType']==5126: result[:,:3]=paint.astype(np.float32)
            else: raise ValueError('Unsupported existing COLOR_0 type')
            if original.shape[1]!=4 or not np.array_equal(original[:,3],result[:,3]): raise AssertionError('Hair alpha/pinning changed')
            a['bufferView']=glb.blob(result.tobytes(),34962);a.pop('byteOffset',None)
            reports.append({'vertices':len(points),'reference_supported_vertices':int(valid.sum()),'fallback_vertices':int((~valid).sum()),
                            'alpha_exact':True,'component_type_preserved':a['componentType'],'reference_linear_median':np.median(paint,axis=0).tolist()})
            changed_accessors.append(color_index)
    glb.write(output);after=Glb(output)
    unchanged=all(np.array_equal(before.read(i),after.read(i)) for i in range(len(before.doc['accessors'])) if i not in changed_accessors)
    if not unchanged: raise AssertionError('Hair bake changed geometry, UVs or another attribute')
    return {'input_sha256':sha(path),'output_sha256':sha(output),'only_color_accessors_changed':unchanged,
            'changed_accessors':changed_accessors,'parts':reports,'fallback':'median reference hair color, darkened20%; unseen rear inferred, no rear reference exists',
            'reference_masks':[{'view':v.name,'pixels':int(v.hair_mask.sum())} for v in views]}


def connected_islands(triangles,vertices):
    edges=np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]])
    _,groups=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(vertices,vertices)),directed=False)
    return groups


def pack_islands(sizes,canvas=1024):
    """Deterministic shelf packing; every tile includes a four-texel gutter."""
    for scale in [1,.95,.9,.85,.8,.75]:
        ordered=sorted(enumerate(sizes),key=lambda item:(-item[1][1],-item[1][0],item[0]))
        shelves=[];rectangles={};bottom=0
        for index,(original_w,original_h) in ordered:
            w=max(16,int(original_w*scale));h=max(16,int(original_h*scale))
            shelf=next((s for s in shelves if h<=s['h'] and s['x']+w<=canvas),None)
            if shelf is None:
                if bottom+h>canvas: break
                shelf={'x':0,'y':bottom,'h':h};shelves.append(shelf);bottom+=h
            rectangles[index]=(shelf['x'],shelf['y'],w,h);shelf['x']+=w
        if len(rectangles)==len(sizes): return rectangles,scale
    raise ValueError('Hair islands exceed the single1024 atlas budget')


def bake_hair_texture(path,output,views,sex,debug,finish='projected-flow'):
    """Add one UV2 atlas, retaining all existing accessor bytes and root alpha."""
    source_hash=sha(path)
    glb=Glb(path);before=Glb(path);worlds=node_worlds(glb.doc);parts=[];sizes=[]
    for view in views: view.prepare_hair(sex=='female')
    fallback=np.median(np.array([v.hair_median for v in views]),axis=0)*.80
    for node in glb.doc['nodes']:
        if 'mesh' not in node: continue
        for primitive in glb.doc['meshes'][node['mesh']]['primitives']:
            attrs=primitive['attributes'];points=glb.read(attrs['POSITION']);normals=glb.read(attrs['NORMAL'])
            triangles=glb.read(primitive['indices']).reshape(-1,3);uv=glb.read(attrs['TEXCOORD_0'])
            groups=connected_islands(triangles,len(points));island_indices=[]
            for group in range(groups.max()+1):
                count=int(np.sum(groups==group));island_indices.append(len(sizes))
                sizes.append((320,320) if count>600 else (256,256) if count>500 else (80,112) if count>180 else (64,96) if count>40 else (20,32))
            parts.append((node,primitive,points,normals,triangles,uv,groups,island_indices))
    rectangles,scale=pack_islands(sizes);size=1024
    colors=np.tile(fallback,(size,size,1));painted=np.zeros((size,size),bool);supported=0;total=0
    for node,primitive,points,normals,triangles,uv,groups,island_indices in parts:
        uv2=np.zeros_like(uv)
        for group,index in enumerate(island_indices):
            ids=groups==group;x,y,w,h=rectangles[index]
            low=uv[ids].min(0);span=np.maximum(np.ptp(uv[ids],axis=0),1e-9)
            uv2[ids]=(np.array([x+4.5,y+4.5])+(uv[ids]-low)/span*np.array([w-9,h-9]))/size
        per_view=[]
        for view in views:
            posed=transform(view.record['skeleton_global'])@transform(view.record['head_global_pose'])@worlds[node.get('name','')]
            world=points@posed[:3,:3].T+posed[:3,3]
            normal=normalize(normals@np.linalg.inv(posed[:3,:3]))
            per_view.append((view,world,normal))
        for tri,x,y,bary in raster_triangles(uv2,triangles,(size,size)):
            summed=np.zeros((len(x),3));weight_sum=np.zeros(len(x))
            for view,world,normal in per_view:
                rgb,weight=view.hair_samples(bary@world[tri],normalize(bary@normal[tri]))
                summed+=rgb*weight[:,None];weight_sum+=weight
            valid=weight_sum>1e-7;value=np.tile(fallback,(len(x),1));value[valid]=summed[valid]/weight_sum[valid,None]
            colors[y,x]=value;painted[y,x]=True;supported+=int(valid.sum());total+=len(x)
        primitive['attributes']['TEXCOORD_1']=glb.array(uv2.astype(np.float32),'VEC2',5126,34962)
    # Extend each island's own edge into its gutter, without importing neighbors.
    for x,y,w,h in rectangles.values():
        mask=painted[y:y+h,x:x+w]
        if not mask.any(): continue
        nearest=distance_transform_edt(~mask,return_distances=False,return_indices=True)
        tile=colors[y:y+h,x:x+w];tile[~mask]=tile[nearest[0][~mask],nearest[1][~mask]]
        # Literal view projection contains tiny pale ear/background outliers
        # and lighting from different lock directions. Keep the source pigment
        # within its hair palette, then filter along each lock's growth axis.
        srgb=linear_srgb(tile)
        srgb[:,:,0]=np.minimum(srgb[:,:,0],.88)
        srgb[:,:,1]=np.minimum(srgb[:,:,1],srgb[:,:,0]*(.64 if sex=='female' else .76)+.008)
        srgb[:,:,2]=np.minimum(srgb[:,:,2],srgb[:,:,0]*(.34 if sex=='female' else .53)+.005)
        tile[:]=srgb_linear(srgb)
        sigma=(2.2,2.2,0) if w>200 else (5.5,1.35,0)
        tile[:]=gaussian_filter(tile,sigma=sigma,mode='nearest')
        if finish=='coherent' and w<=200:
            # Source and prototype locks do not share brush paths. A weak
            # reference residual retains pigment while coherent longitudinal
            # bands follow this lock's own authored growth coordinates.
            yy,xx=np.indices((h,w));u=np.clip((xx-4)/(w-9),0,1);v=np.clip((yy-4)/(h-9),0,1)
            band=np.maximum(np.sin(u*np.pi),0)**1.4
            flow=(.72+.62*band)*(.80+.20*np.minimum(v/.23,1))*(1-.10*np.clip((v-.72)/.28,0,1))
            template=(fallback/.80)[None,None,:]*flow[:,:,None]
            tile[:]=template*.82+tile*.18
        elif finish=='coherent':
            # Cap paint has real multi-directional reference flow; retain it,
            # but bound rare occluder/highlight samples around its robust median.
            median=np.median(tile.reshape(-1,3),axis=0)
            tile[:]=np.clip(tile,median*.35,median*2.0)
    pixels=np.clip(np.rint(linear_srgb(colors)*255),0,255).astype(np.uint8)
    image=Image.fromarray(pixels);data=io.BytesIO();image.save(data,format='PNG',optimize=True)
    glb.doc.setdefault('images',[]).append({'name':'Reference hair painted atlas1024','mimeType':'image/png','bufferView':glb.blob(data.getvalue())})
    glb.doc.setdefault('textures',[]).append({'source':len(glb.doc['images'])-1})
    texture=len(glb.doc['textures'])-1
    for _,primitive,*_ in parts:
        pbr=glb.doc['materials'][primitive['material']].setdefault('pbrMetallicRoughness',{})
        pbr['baseColorTexture']={'index':texture,'texCoord':1};pbr['baseColorFactor']=[1,1,1,1]
    glb.write(output);after=Glb(output)
    exact=all(np.array_equal(before.read(i),after.read(i)) for i in range(len(before.doc['accessors'])))
    if not exact: raise AssertionError('Hair atlas changed existing accessors')
    image.save(debug/'hair-reference-1024.png')
    return {'input_sha256':source_hash,'output_sha256':sha(output),'all_existing_accessors_exact':exact,
            'existing_accessors':len(before.doc['accessors']),'new_uv_accessors':len(parts),'islands':len(sizes),
            'atlas_dimensions':[size,size],'atlas_png_bytes':len(data.getvalue()),'packing_scale':scale,
            'painted_texels':int(painted.sum()),'reference_supported_triangle_samples':supported,'triangle_samples':total,
            'texture_count_added':1,'draws_added':0,'uv_bytes_added':sum(len(p[2])*8 for p in parts),
            'paint_finish':finish,'paint_filter':'Palette protection, Gaussian5.5/1.35 along/across locks; cap Gaussian2.2',
            'rgba8_mip_vram_bytes':int(size*size*4*4/3),'fallback':'Median reference hair color, darkened20%; unseen rear inferred.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--input-root',required=True,type=Path)
    parser.add_argument('--hair-root',required=True,type=Path)
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--mode',choices=['hair','face','both'],default='both')
    parser.add_argument('--kit',default='equipped')
    parser.add_argument('--hair-finish',choices=['projected-flow','coherent'],default='projected-flow',
                        help='Chosen projected-flow finish or the smoother18%% reference-pigment study')
    parser.add_argument('--base-skin-root',type=Path,help='Optional clean matching-UV male/female-skin-1024.png atlas directory')
    args=parser.parse_args();manifest=json.loads(args.manifest.read_text());receipts=[]
    if manifest.get('failures',0): raise ValueError('Portrait registration contains failures')
    for sex in ['male','female']:
        rows=[r for r in manifest['portraits'] if r['sex']==sex and r['kit']==args.kit]
        if {r['view'] for r in rows}!={'front','side','isometric'}: raise ValueError('Need all three registered views for '+sex)
        views=[View(r,args.manifest.parent) for r in rows]
        output=args.output_root/sex;output.mkdir(parents=True,exist_ok=True)
        head_input=args.input_root/sex/f'luminous_{sex}.glb';head_output=output/f'luminous_{sex}.glb'
        hair_input=args.hair_root/sex/'concept_hair.glb';hair_output=output/'concept_hair.glb'
        receipt={'sex':sex,'manifest_sha256':sha(args.manifest),'source_references':[{'path':v.ref['path'],'sha256':v.ref['sha256']} for v in views]}
        if args.mode in ['hair','both']:
            receipt['hair']=bake_hair(hair_input,hair_output,views,sex)
            receipt['hair_texture']=bake_hair_texture(hair_output,hair_output,views,sex,output,args.hair_finish)
        else: hair_output.write_bytes(hair_input.read_bytes())
        # Write a usable hair-first prototype immediately, before the slower UV bake.
        head_output.write_bytes(head_input.read_bytes())
        metadata=json.loads((args.input_root/sex/'fit.json').read_text())
        styles=metadata.get('concept_hair',{}).get('styles',{})
        for style in styles.values(): style.update(scene='concept_hair.glb',painted_vertices=args.mode in ['hair','both'],painted_texture=args.mode in ['hair','both'])
        metadata['concept_hair']['source_sha256']=sha(hair_output)
        (output/'fit.json').write_text(json.dumps(metadata,indent=2)+'\n')
        if args.mode in ['face','both']:
            base=args.base_skin_root/f'{sex}-skin-1024.png' if args.base_skin_root else None
            receipt['face']=bake_face(head_input,head_output,views,output,base)
        metadata['output_sha256']=sha(head_output)
        paint_record={'mode':args.mode,'manifest_sha256':sha(args.manifest),'kit':args.kit}
        # Hair-only revisions must retain the already accepted face/neck/mask
        # provenance as well as their exact head bytes.
        metadata['reference_hair_paint' if args.mode=='hair' else 'reference_paint']=paint_record
        (output/'fit.json').write_text(json.dumps(metadata,indent=2)+'\n')
        receipt['output_head_sha256']=sha(head_output);receipt['output_hair_sha256']=sha(hair_output)
        (output/'reference-paint-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');receipts.append(receipt)
        print(json.dumps({'sex':sex,'ready':str(output),'hair':receipt.get('hair',{}),'face':{k:v for k,v in receipt.get('face',{}).items() if k!='view_registration'}}),flush=True)
    (args.output_root/'reference-paint-manifest.json').write_text(json.dumps({'schema':'RL reference paint bake1','models':receipts,'tool_sha256':sha(__file__)},indent=2)+'\n')
    (args.output_root/'bake_concept_reference.py').write_bytes(Path(__file__).read_bytes())


if __name__=='__main__': main()
