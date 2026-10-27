"""Transfer retained canonical neck pigment into the MPFB neck atlas, offline.

Replaces one existing skin PNG. Mesh/UV/rig accessors and other images remain
byte exact. The accepted native body already embedded in the prototype is the
source, so no source-specific texture, private path or runtime code is needed.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.spatial import cKDTree

from fit_canonical import Glb, node_worlds, sample_ring
from bake_concept_reference import image_bytes, raster_triangles, sha, srgb_linear, linear_srgb, normalize


def smooth(low,high,value):
    p=np.clip((value-low)/(high-low),0,1)
    return p*p*(3-2*p)


def closest_barycentric(points,triangles):
    """Closest points on candidate triangles, retaining exact edge UVs."""
    a=triangles[:,:,0];b=triangles[:,:,1];c=triangles[:,:,2]
    ab=b-a;ac=c-a;ap=points[:,None,:]-a
    aa=np.sum(ab*ab,axis=2);bb=np.sum(ab*ac,axis=2);cc=np.sum(ac*ac,axis=2)
    dd=np.sum(ap*ab,axis=2);ee=np.sum(ap*ac,axis=2)
    den=aa*cc-bb*bb
    u=(cc*dd-bb*ee)/np.maximum(den,1e-20);v=(aa*ee-bb*dd)/np.maximum(den,1e-20)
    interior=(u>=0)&(v>=0)&(u+v<=1)
    bary=np.stack((1-u-v,u,v),axis=2)
    candidates=[bary]
    for first,last in [(0,1),(1,2),(2,0)]:
        start=triangles[:,:,first];edge=triangles[:,:,last]-start
        along=np.clip(np.sum((points[:,None,:]-start)*edge,axis=2)/np.maximum(np.sum(edge*edge,axis=2),1e-20),0,1)
        value=np.zeros_like(bary);value[:,:,first]=1-along;value[:,:,last]=along;candidates.append(value)
    possible=np.stack(candidates,axis=2)
    location=np.einsum('nkci,nkij->nkcj',possible,triangles)
    distance=np.sum((location-points[:,None,None,:])**2,axis=3)
    distance[:,:,0]=np.where(interior,distance[:,:,0],np.inf)
    edge_choice=np.argmin(distance,axis=2)
    return np.take_along_axis(possible,edge_choice[:,:,None,None],axis=2)[:,:,0,:],np.min(distance,axis=2)


def sample_image(pixels,uv):
    height,width=pixels.shape[:2]
    return np.column_stack([map_coordinates(pixels[:,:,c],[uv[:,1]*height-.5,uv[:,0]*width-.5],order=1,mode='nearest') for c in range(3)])


def image_for_primitive(glb,primitive):
    pbr=glb.doc['materials'][primitive['material']]['pbrMetallicRoughness']
    index=glb.doc['textures'][pbr['baseColorTexture']['index']]['source']
    return index,np.asarray(pbr.get('baseColorFactor',[1,1,1,1])[:3],float)


def bake_loft(path,output,metadata,accepted_head=None):
    """Paint only the reserved UV patch; retained face pigment stays exact."""
    glb=Glb(path);before=Glb(path)
    node=next(n for n in glb.doc['nodes'] if n.get('name')=='body')
    head,native=glb.doc['meshes'][node['mesh']]['primitives'][:2]
    topology=metadata['body_fit'];patch=topology['neck_uv']
    image_index,target_factor=image_for_primitive(glb,head)
    accepted=Glb(accepted_head) if accepted_head else glb
    accepted_node=next(n for n in accepted.doc['nodes'] if n.get('name')=='body')
    accepted_head_primitive=accepted.doc['meshes'][accepted_node['mesh']]['primitives'][0]
    accepted_image,_=image_for_primitive(accepted,accepted_head_primitive)
    base=np.asarray(Image.open(io.BytesIO(image_bytes(accepted,accepted_image))).convert('RGBA')).copy()
    height,width=base.shape[:2]
    if [width,height]!=patch['texture_size']:raise ValueError('Accepted atlas dimensions differ from the loft allocation')
    source_image,source_factor=image_for_primitive(glb,native)
    native_pixels=np.asarray(Image.open(io.BytesIO(image_bytes(glb,source_image))).convert('RGB'),float)/255
    top=topology['top_boundary'];bottom=topology['bottom_boundary']
    top_colors=srgb_linear(sample_image(base[:,:,:3]/255,np.asarray(top['uv'])))
    bottom_colors=srgb_linear(sample_image(native_pixels,np.asarray(bottom['uv'])))*source_factor/np.maximum(target_factor,.001)
    x,y,w,h=map(int,patch['pixels']);gutter=min(3,int(patch['gutter_pixels']))
    x0=max(0,x-gutter);x1=min(width,x+w+gutter);y0=max(0,y-gutter);y1=min(height,y+h+gutter)
    xx,yy=np.meshgrid(np.arange(x0,x1),np.arange(y0,y1));u=(xx+.5)/width;v=(yy+.5)/height
    u0,v0,u1,v1=map(float,patch['tube_rectangle'])
    arc=np.mod((u-u0)/(u1-u0),1).ravel()
    high=sample_ring(np.asarray(top['arc']),top_colors,arc)
    low=sample_ring(np.asarray(bottom['arc']),bottom_colors,arc)
    blend=smooth(0,1,np.clip((v1-v)/(v1-v0),0,1)).ravel()
    color=low*(1-blend[:,None])+high*blend[:,None]
    rgba=np.empty((*xx.shape,4),np.uint8)
    rgba[:,:,:3]=np.uint8(np.clip(np.rint(linear_srgb(color.reshape((*xx.shape,3)))*255),0,255));rgba[:,:,3]=128
    # Hidden internal caps use their adjacent retained mouth pigment when
    # available. They do not share the tube's longitudinal UV footprint.
    uv=glb.read(head['attributes']['TEXCOORD_0']);triangles=glb.read(head['indices']).reshape(-1,3)
    retained_count=int(topology['retained_triangle_count']);cap_start=retained_count+int(topology['new_loft_triangles'])
    cap_color=np.median(top_colors,axis=0)
    if cap_start<len(triangles):
        vertices=glb.read(head['attributes']['POSITION']);retained_ids=np.unique(triangles[:retained_count])
        tree=cKDTree(vertices[retained_ids]);queries=vertices[np.unique(triangles[cap_start:])];samples=[]
        for point in queries:
            ids=tree.query_ball_point(point,1e-6)
            if ids:samples.extend(uv[retained_ids[ids]].tolist())
        if samples:cap_color=np.median(srgb_linear(sample_image(base[:,:,:3]/255,np.asarray(samples))),axis=0)
    cap_band=yy>=y+h-12
    rgba[cap_band,:3]=np.uint8(np.clip(np.rint(linear_srgb(cap_color)*255),0,255))
    retained_mask=np.zeros((height,width),bool)
    for _,px,py,_ in raster_triangles(uv,triangles[:retained_count],(width,height)):retained_mask[py,px]=True
    written=np.zeros_like(retained_mask);written[y0:y1,x0:x1]=True
    if np.any(written&retained_mask):raise ValueError('Loft paint touches retained head UVs')
    lip_bounds=metadata.get('head_lip_uv_bounds')
    if accepted_head:
        accepted_fit=json.loads(accepted_head.with_name('fit.json').read_text())
        lip_bounds=accepted_fit.get('head_lip_uv_bounds',lip_bounds)
    if lip_bounds:
        lx0,ly0,lx1,ly1=np.asarray(lip_bounds)*[width,height,width,height]
        if written[int(np.floor(ly0)):int(np.ceil(ly1)),int(np.floor(lx0)):int(np.ceil(lx1))].any():
            raise ValueError('Loft paint touches the padded lip rectangle')
    result=base.copy();result[y0:y1,x0:x1]=rgba
    buffer=io.BytesIO();Image.fromarray(result).save(buffer,format='PNG',optimize=True)
    glb.doc['images'][image_index]['bufferView']=glb.blob(buffer.getvalue());glb.write(output)
    after=Glb(output)
    exact=all(np.array_equal(before.read(i),after.read(i)) for i in range(len(before.doc['accessors'])))
    other_images=all(image_bytes(before,i)==image_bytes(after,i) for i in range(len(before.doc['images'])) if i!=image_index)
    if not exact or not other_images:raise AssertionError('Loft paint changed geometry or another image')
    Image.fromarray(result).save(output.parent/'neck-reference.png')
    Image.fromarray(np.uint8(written)*255).save(output.parent/'neck-coverage.png')
    delta=result[:,:,:3].astype(int)-base[:,:,:3].astype(int)
    Image.fromarray(np.uint8(np.clip(delta*2+128,0,255))).save(output.parent/'neck-delta-x2.png')
    return {'input_sha256':sha(path),'output_sha256':sha(output),'all_accessors_exact':exact,'other_images_exact':other_images,
            'source':'Accepted head cut-loop pigment to canonical body seam pigment, intrinsic arc/height interpolation',
            'accepted_head_sha256':sha(accepted_head) if accepted_head else sha(path),'patch_pixels':patch['pixels'],
            'painted_texels':int(written.sum()),'retained_head_rgba_exact':bool(np.array_equal(result[retained_mask],base[retained_mask])),
            'outside_patch_rgba_exact':bool(np.array_equal(result[~written],base[~written])),
            'new_neck_alpha_neutral':bool(np.all(result[written,3]==128)),'padded_lip_rectangle_untouched':True,
            'texture_maps_materials_draws_added':0}


def bake(path:Path,output:Path,accepted_head=None):
    metadata=json.loads((path.parent/'fit.json').read_text())
    if metadata.get('body_fit',{}).get('mode')=='structured_neck_loft':
        return bake_loft(path,output,metadata,accepted_head)
    before=Glb(path);glb=Glb(path);worlds=node_worlds(glb.doc)
    node=next(n for n in glb.doc['nodes'] if n.get('name')=='body')
    head,native=glb.doc['meshes'][node['mesh']]['primitives'][:2]
    def arrays(primitive):
        attrs=primitive['attributes']
        return (glb.read(attrs['POSITION']).astype(float),glb.read(attrs['NORMAL']).astype(float),
                glb.read(attrs['TEXCOORD_0']).astype(float),glb.read(primitive['indices']).reshape(-1,3))
    target,normals,uv,triangles=arrays(head);source,source_normals,source_uv,source_triangles=arrays(native)
    to_head=np.linalg.inv(worlds['Head'])@worlds['body']
    local=target@to_head[:3,:3].T+to_head[:3,3]
    metadata=json.loads((path.parent/'fit.json').read_text())
    mouth_y=float(metadata['face_frame_head_local']['mouth_y']);chin_y=mouth_y-.045
    # Keep only the retained canonical neck/upper chest; shoulders and hands
    # cannot become nearest candidates for a narrow head-neck point.
    candidate=(np.max(np.abs(source[source_triangles,0]),axis=1)<.14)&(source[source_triangles,1].max(1)>1.37)
    source_triangles=source_triangles[candidate]
    if len(source_triangles)<4: raise ValueError('Canonical retained neck surface is missing')
    geometry=source[source_triangles];centers=geometry.mean(1);tree=cKDTree(centers)
    triangle_normals=normalize(np.cross(geometry[:,1]-geometry[:,0],geometry[:,2]-geometry[:,0]))
    def material(primitive):
        pbr=glb.doc['materials'][primitive['material']]['pbrMetallicRoughness']
        index=glb.doc['textures'][pbr['baseColorTexture']['index']]['source']
        return index,np.array(pbr.get('baseColorFactor',[1,1,1,1])[:3])
    target_image,target_factor=material(head);source_image,source_factor=material(native)
    original=Image.open(io.BytesIO(image_bytes(glb,target_image)));base=np.array(original.convert('RGBA'))
    source_pixels=np.array(Image.open(io.BytesIO(image_bytes(glb,source_image))).convert('RGB'),float)/255
    h,w=base.shape[:2];result=base.copy();gain=np.zeros((h,w));desired=np.zeros((h,w,3));covered=np.zeros((h,w),bool)
    maximum_distance=0.;queries=0
    for tri,x,y,bary in raster_triangles(uv,triangles,(w,h)):
        covered[y,x]=True;rest=bary@local[tri]
        blend=1-smooth(chin_y-.010,chin_y+.020,rest[:,1])
        active=blend>0
        if not active.any(): continue
        x=x[active];y=y[active];bary=bary[active];blend=blend[active]
        points=bary@target[tri];normal=normalize(bary@normals[tri])
        _,ids=tree.query(points,k=min(12,len(source_triangles)))
        if ids.ndim==1: ids=ids[:,None]
        source_bary,distance=closest_barycentric(points,geometry[ids])
        compatible=np.maximum(np.sum(triangle_normals[ids]*normal[:,None,:],axis=2),-1)
        cost=distance+(1-compatible)*.0002**2
        chosen=np.argmin(cost,axis=1);rows=np.arange(len(points));face=ids[rows,chosen];b=source_bary[rows,chosen]
        separation=np.sqrt(distance[rows,chosen])
        # Pin pigment at the actual shared surface independently of the
        # sloped neck-cut height, then fade into the upper head foundation.
        blend=np.maximum(blend,1-smooth(.0005,.003,separation))
        mapped_uv=np.einsum('ni,nij->nj',b,source_uv[source_triangles[face]])
        pigment=np.column_stack([map_coordinates(source_pixels[:,:,c],[mapped_uv[:,1]*source_pixels.shape[0]-.5,mapped_uv[:,0]*source_pixels.shape[1]-.5],order=1,mode='nearest') for c in range(3)])
        pigment=srgb_linear(pigment)*source_factor/np.maximum(target_factor,.001)
        desired[y,x]=pigment;gain[y,x]=blend
        maximum_distance=max(maximum_distance,float(np.sqrt(distance[rows,chosen]).max()));queries+=len(points)
    active=gain>0
    final=srgb_linear(base[:,:,:3]/255)*(1-gain[:,:,None])+desired*gain[:,:,None]
    result[active,:3]=np.uint8(np.clip(np.rint(linear_srgb(final[active])*255),0,255))
    # Bleed only into unused UV gutters; never touch another valid face island.
    distance,nearest=distance_transform_edt(~active,return_indices=True)
    gutter=(distance<=3)&(~covered)
    result[gutter]=result[nearest[0][gutter],nearest[1][gutter]]
    image=Image.fromarray(result if original.mode=='RGBA' else result[:,:,:3]);buffer=io.BytesIO();image.save(buffer,format='PNG',optimize=True)
    glb.doc['images'][target_image]['bufferView']=glb.blob(buffer.getvalue());glb.write(output)
    after=Glb(output)
    equal=all(np.array_equal(before.read(i),after.read(i)) for i in range(len(before.doc['accessors'])))
    others=all(image_bytes(before,i)==image_bytes(after,i) for i in range(len(before.doc['images'])) if i!=target_image)
    if not equal or not others: raise AssertionError('Neck paint altered geometry or another image')
    image.save(output.parent/'neck-reference.png');Image.fromarray(np.uint8(gain*255)).save(output.parent/'neck-coverage.png')
    delta=result[:,:,:3].astype(int)-base[:,:,:3].astype(int)
    Image.fromarray(np.uint8(np.clip(delta*2+128,0,255))).save(output.parent/'neck-delta-x2.png')
    return {'input_sha256':sha(path),'output_sha256':sha(output),'all_accessors_exact':equal,'other_images_exact':others,
            'source':'Retained canonical body primitive1, closest compatible neck triangle UV',
            'canonical_neck_triangles':len(source_triangles),'head_local_fade_y':[chin_y-.010,chin_y+.020],
            'painted_texels':int(active.sum()),'gutter_texels':int(gutter.sum()),'maximum_projection_distance_m':maximum_distance,
            'sample_queries':queries,'face_above_band_exact':bool(np.array_equal(base[(~active)&(~gutter)],result[(~active)&(~gutter)]))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--accepted-head-root',type=Path,help='Use this accepted head PNG/mask as the immutable retained-face foundation for a structured loft')
    parser.add_argument('--hair-root',type=Path,help='Copy frozen painted concept_hair.glb and its art metadata from this stage')
    args=parser.parse_args();reports=[]
    if args.input_root.resolve()==args.output_root.resolve():raise ValueError('Choose a separate output stage; keep input immutable')
    for sex in ['male','female']:
        source=args.input_root/sex;output=args.output_root/sex;output.mkdir(parents=True,exist_ok=True)
        accepted=args.accepted_head_root/sex/f'luminous_{sex}.glb' if args.accepted_head_root else None
        report=bake(source/f'luminous_{sex}.glb',output/f'luminous_{sex}.glb',accepted);report['sex']=sex;reports.append(report)
        metadata=json.loads((source/'fit.json').read_text());metadata['output_sha256']=report['output_sha256'];metadata['neck_paint']=report
        if accepted:
            accepted_metadata=json.loads(accepted.with_name('fit.json').read_text())
            for key in ['head_masks','head_masks_encoding','head_lip_uv_bounds','head_shape_center','concept_portrait','concept_hair']:
                if key in accepted_metadata:metadata[key]=accepted_metadata[key]
        hair_source=(args.hair_root or args.input_root)/sex
        if args.hair_root:
            hair_metadata=json.loads((hair_source/'fit.json').read_text())
            for key in ['concept_hair','reference_hair_paint']:
                if key in hair_metadata:metadata[key]=hair_metadata[key]
        hair=hair_source/'concept_hair.glb'
        if hair.exists():
            (output/'concept_hair.glb').write_bytes(hair.read_bytes())
            if metadata.get('concept_hair'):metadata['concept_hair']['source_sha256']=sha(hair)
        (output/'fit.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report),flush=True)
    (args.output_root/'neck-paint-report.json').write_text(json.dumps({'models':reports,'tool_sha256':sha(__file__)},indent=2)+'\n',encoding='utf-8')
    (args.output_root/'bake_neck_paint.py').write_bytes(Path(__file__).read_bytes())


if __name__=='__main__':main()
