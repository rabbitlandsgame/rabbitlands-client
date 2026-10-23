"""Version 2: local muzzle cleanup and a posterior rest fit of the imported tail.

The source and its topology/UVs stay immutable. Reviewed original vertex IDs,
including coincident UV seams, delimit both repairs independently of skin weights.
"""
import io
from collections import deque
import numpy as np
from PIL import Image, ImageDraw

OLD_TAIL = np.array([[.10,.45,-1.19],[-.43,.17,-1.29],[-.95,.09,-1.06],
    [-1.20,.075,-.57],[-1.13,.07,-.03],[-1.11,.07,.43],[-1.17,.07,.72]])

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1); return t*t*(3-2*t)

def curve(points):
    """A continuous guide sampled uniformly by physical arc length."""
    extended=np.vstack([2*points[0]-points[1],points,2*points[-1]-points[-2]])
    parts=[]
    for i in range(len(points)-1):
        a,b,c,d=extended[i:i+4];t=np.linspace(0,1,129)[:,None]
        q=.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)
        parts.extend(q[:-1])
    parts=np.vstack([parts,points[-1]])
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(parts,axis=0),axis=1))]
    s=np.linspace(0,distance[-1],1025)
    return np.column_stack([np.interp(s,distance,parts[:,i]) for i in range(3)]),s

def new_tail_points():
    # Match every inherited guide segment's length; trail down behind the rump.
    x=[.10,-.43,-.60,-.55,-.40,-.22,-.08];y=[.45,.17,.20,.22,.23,.24,.28]
    result=[OLD_TAIL[0].copy()]
    for i,length in enumerate(np.linalg.norm(np.diff(OLD_TAIL,axis=0),axis=1)):
        dx=x[i+1]-x[i];dy=y[i+1]-y[i]
        result.append(np.array([x[i+1],y[i+1],result[-1][2]-np.sqrt(length*length-dx*dx-dy*dy)]))
    return np.array(result)

def frame(tangent):
    tangent=tangent/np.linalg.norm(tangent,axis=1)[:,None]
    lateral=np.cross(np.tile([0.,1.,0.],(len(tangent),1)),tangent)
    lateral/=np.linalg.norm(lateral,axis=1)[:,None]
    vertical=np.cross(tangent,lateral)
    return np.stack([lateral,vertical,tangent],axis=2)

def repair(points,normals,indices,regions):
    result=points.copy();result_normals=normals.copy()
    # Weld only for editing: keep all source indices and UV seam copies on export.
    _,first,inverse=np.unique(np.round(points,5),axis=0,return_index=True,return_inverse=True)
    unique=points[first].copy();neighbors=[set() for _ in unique]
    for face in inverse[indices.reshape(-1,3)]:
        for a,b in zip(face,np.roll(face,1)):neighbors[a].add(b);neighbors[b].add(a)
    mouth=np.zeros(len(points),bool);mouth[regions['mouthVertexIds']]=True
    editable=np.unique(inverse[mouth]);strength=np.zeros(len(unique));strength[editable]=1
    # Fixed boundary and nose; smooth only the malformed lateral whisker clumps.
    strength*=smooth(1.05,1.15,unique[:,2])*(1-smooth(.92,.99,unique[:,1]))*smooth(.70,.76,unique[:,1])
    strength*=smooth(.075,.16,np.abs(unique[:,0]+.065))
    for _ in range(18):
        average=np.array([unique[list(n)].mean(0) for n in neighbors])
        unique+=.45*strength[:,None]*(average-unique)
    # Fold the remaining fused whisker spikes back onto a closed muzzle.
    width=.22*np.sqrt(np.clip((1.41-unique[:,2])/.40,0,1))
    relative=unique[:,0]+.065
    tucked=-.065+np.sign(relative)*np.minimum(abs(relative),width)
    unique[:,0]+=strength*(tucked-unique[:,0])
    result[mouth]=unique[inverse[mouth]]
    # Recalculate smooth local normals on the welded mouth only.
    triangles=inverse[indices.reshape(-1,3)];p=unique[triangles]
    face_normals=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);acc=np.zeros_like(unique)
    for corner in range(3):np.add.at(acc,triangles[:,corner],face_normals)
    acc/=np.maximum(1e-10,np.linalg.norm(acc,axis=1))[:,None]
    result_normals[mouth]=acc[inverse[mouth]]
    old,s=curve(OLD_TAIL);new,ns=curve(new_tail_points())
    # Keep cross-section offsets while uncurling the continuous centreline.
    new=np.column_stack([np.interp(s,ns* s[-1]/ns[-1],new[:,i]) for i in range(3)])
    old_frames=frame(np.gradient(old,axis=0));new_frames=frame(np.gradient(new,axis=0))
    ids=np.array(regions['tailVertexIds']);source=points[ids]
    nearest=np.argmin(np.sum((source[:,None]-old[None])**2,axis=2),axis=1)
    offsets=np.einsum('nji,nj->ni',old_frames[nearest],source-old[nearest])
    target=new[nearest]+np.einsum('nij,nj->ni',new_frames[nearest],offsets)
    blend=smooth(0,.30,s[nearest])
    result[ids]+=blend[:,None]*(target-source)
    local_normals=np.einsum('nji,nj->ni',old_frames[nearest],normals[ids])
    rotated=np.einsum('nij,nj->ni',new_frames[nearest],local_normals)
    result_normals[ids]=(1-blend[:,None])*normals[ids]+blend[:,None]*rotated
    result_normals[ids]/=np.linalg.norm(result_normals[ids],axis=1)[:,None]
    outside=np.ones(len(points),bool);outside[regions['mouthVertexIds']]=False;outside[ids]=False
    assert np.array_equal(result[outside],points[outside]),'unrelated surface changed'
    assert np.array_equal(result_normals[outside],normals[outside]),'unrelated normals changed'
    return result,result_normals,{
        'mouthEditedVertices':int(np.count_nonzero(np.linalg.norm(result[mouth]-points[mouth],axis=1)>.000001)),
        'tailVertices':len(ids),'unchangedOutsideRepairVertices':int(outside.sum()),
        'maximumOutsideRepairDisplacementMetres':float(np.max(np.linalg.norm(result[outside]-points[outside],axis=1))),
        'tailGuideLengthMetres':float(s[-1]),'fittedTailGuideLengthMetres':float(ns[-1]),
        'tailGuideSegmentLengthDifferenceMetres':float(np.max(abs(np.linalg.norm(np.diff(OLD_TAIL,axis=0),axis=1)-np.linalg.norm(np.diff(new_tail_points(),axis=0),axis=1))))}

def repair_mouth_maps(doc,blob,uv,indices,points,regions):
    """Repaint only the original mouth's UV islands; all other texels are exact."""
    mouth=np.zeros(len(points),bool);mouth[regions['mouthVertexIds']]=True
    triangles=indices.reshape(-1,3);faces=triangles[np.any(mouth[triangles],axis=1)]
    changed={}
    base=next(image for image in doc['images'] if 'basecolor' in image['name'])
    bv=doc['bufferViews'][base['bufferView']];start=bv.get('byteOffset',0)
    base_pixels=np.asarray(Image.open(io.BytesIO(blob[start:start+bv['byteLength']])).convert('RGB'))
    h,w=base_pixels.shape[:2]
    bright=(base_pixels.min(2)>155)&(np.ptp(base_pixels.astype(float),axis=2)<45)
    # The legacy bake has tiny per-face islands with wide white padding. Flood
    # the selected whisker islands too, so filtering cannot reveal white rims.
    islands=np.zeros((h,w),bool);queue=deque()
    for face in faces:
        center=points[face].mean(0)
        if not (center[2]>1.08 and .72<center[1]<.95 and abs(center[0]+.065)>.06):continue
        px,py=np.clip((uv[face].mean(0)*[w,h]).astype(int),[0,0],[w-1,h-1])
        for yy in range(max(0,py-1),min(h,py+2)):
            for xx in range(max(0,px-1),min(w,px+2)):
                if bright[yy,xx] and not islands[yy,xx]:islands[yy,xx]=True;queue.append((yy,xx))
    while queue:
        y,x=queue.popleft()
        for yy,xx in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)]:
            if 0<=yy<h and 0<=xx<w and bright[yy,xx] and not islands[yy,xx]:islands[yy,xx]=True;queue.append((yy,xx))
    gutter=islands.copy()
    for y,x in [(0,1),(0,-1),(1,0),(-1,0)]:gutter|=np.roll(islands,(y,x),axis=(0,1))
    for image in doc['images']:
        view=doc['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
        original=Image.open(io.BytesIO(blob[start:start+view['byteLength']])).convert('RGB')
        pixels=np.asarray(original).copy();h,w=pixels.shape[:2]
        for face in faces:
            # Each source triangle has its own packed island. Paint only its
            # raster coverage, with a one-pixel gutter for mip/filter continuity.
            coords=uv[face]*[w,h];lo=np.maximum(0,np.floor(coords.min(0)-1).astype(int));hi=np.minimum([w,h],np.ceil(coords.max(0)+2).astype(int))
            if np.any(hi<=lo):continue
            mask=Image.new('L',tuple(hi-lo),0);draw=ImageDraw.Draw(mask)
            draw.polygon([tuple(v-lo) for v in coords],fill=255);draw.line([tuple(v-lo) for v in np.vstack([coords,coords[0]])],fill=255,width=2)
            yy,xx=np.mgrid[lo[1]:hi[1],lo[0]:hi[0]];q=np.stack([xx+.5,yy+.5,np.ones_like(xx)],axis=-1)
            matrix=np.vstack([coords.T,np.ones(3)])
            if abs(np.linalg.det(matrix))<1e-6:continue
            bary=q@np.linalg.inv(matrix).T;bary=np.clip(bary,0,1);bary/=bary.sum(2,keepdims=True)
            position=bary@points[face];x,y,z=np.moveaxis(position,-1,0)
            lateral=smooth(.015,.055,np.abs(x+.065))
            amount=lateral*smooth(1.045,1.085,z)*smooth(.685,.72,y)*(1-smooth(.95,1.0,y))
            # A soft warm-grey whisker pad, retaining the original pink nose.
            shade=np.clip((y-.72)/.27,0,1)
            color=np.stack([84+22*shade,70+21*shade,60+20*shade],axis=-1)
            if 'normal' in image['name']:color=np.broadcast_to([128,128,255],color.shape)
            patch=pixels[lo[1]:hi[1],lo[0]:hi[0]];alpha=amount*(np.asarray(mask)/255)
            pixels[lo[1]:hi[1],lo[0]:hi[0]]=np.rint(patch*(1-alpha[:,:,None])+color*alpha[:,:,None]).astype('uint8')
        pixels[gutter]=[128,128,255] if 'normal' in image['name'] else [95,80,69]
        changed[image['name']]=int(np.count_nonzero(np.any(pixels!=np.asarray(original),axis=2)))
        encoded=io.BytesIO();Image.fromarray(pixels).save(encoded,format='PNG')
        blob.extend(b'\0'*(-len(blob)%4));start=len(blob);blob.extend(encoded.getvalue())
        doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(encoded.getvalue())})
        image['bufferView']=len(doc['bufferViews'])-1
    return changed
