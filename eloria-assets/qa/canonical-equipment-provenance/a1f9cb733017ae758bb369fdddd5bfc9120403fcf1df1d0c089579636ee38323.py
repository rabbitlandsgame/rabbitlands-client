"""Transfer the original cloth texture to reconstructed inner seam panels."""
from io import BytesIO

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

import conform_equipment as ce


def project_colours(points, source, faces, uv, pixels):
    """Nearest original triangle, with UV seams resolved per sampled point."""
    triangles = source[faces]
    tree = cKDTree(triangles.mean(axis=1))
    colours = np.empty((len(points), 3), dtype=np.uint8)
    for start in range(0, len(points), 2048):
        block = points[start:start+2048]
        _, ids = tree.query(block, k=min(24,len(faces)))
        if ids.ndim == 1: ids = ids[:,None]
        tri = triangles[ids]
        a,b,c = tri[:,:,0],tri[:,:,1],tri[:,:,2]
        v0,v1,v2 = b-a,c-a,block[:,None,:]-a
        d00=np.sum(v0*v0,axis=2);d01=np.sum(v0*v1,axis=2);d11=np.sum(v1*v1,axis=2)
        d20=np.sum(v2*v0,axis=2);d21=np.sum(v2*v1,axis=2)
        denom=np.maximum(d00*d11-d01*d01,1e-15)
        v=(d11*d20-d01*d21)/denom;w=(d00*d21-d01*d20)/denom
        bary=np.maximum(np.stack([1-v-w,v,w],axis=2),0)
        bary/=np.maximum(bary.sum(axis=2,keepdims=True),1e-10)
        closest=np.sum(tri*bary[:,:,:,None],axis=2)
        picked=np.argmin(np.sum((closest-block[:,None,:])**2,axis=2),axis=1)
        rows=np.arange(len(block));chosen=ids[rows,picked]
        coords=np.sum(uv[faces[chosen]]*bary[rows,picked,:,None],axis=1)
        xy=np.clip(coords,0,1)*np.array([pixels.shape[1]-1,pixels.shape[0]-1])
        colours[start:start+len(block)] = pixels[xy[:,1].astype(int),xy[:,0].astype(int),:3]
    return colours


def primitive(glb, points, faces, normals, joints, weights, source_positions,
              source, source_faces, source_uv, texture, label):
    """A small atlas for new panels; the original artwork atlas stays intact."""
    tile=12
    columns=int(np.ceil(np.sqrt(len(faces))))
    rows=int(np.ceil(len(faces)/columns))
    yy,xx=np.mgrid[:tile,:tile]
    v=(xx.ravel()-1)/(tile-3);w=(yy.ravel()-1)/(tile-3)
    bary=np.maximum(np.column_stack([1-v-w,v,w]),0)
    bary/=bary.sum(axis=1,keepdims=True)
    samples=np.einsum('pj,tjk->tpk',bary,source_positions[faces]).reshape(-1,3)
    pixels=np.asarray(Image.open(BytesIO(texture)).convert('RGB'))
    colors=project_colours(samples,source,source_faces,source_uv,pixels).reshape(-1,tile,tile,3)
    atlas=np.zeros((rows*tile,columns*tile,3),dtype=np.uint8)
    atlas_uv=[]
    for i,colour in enumerate(colors):
        row,col=divmod(i,columns)
        atlas[row*tile:(row+1)*tile,col*tile:(col+1)*tile]=colour
        atlas_uv.extend((np.array([[1.5,1.5],[tile-1.5,1.5],[1.5,tile-1.5]])
                         +[col*tile,row*tile])/[columns*tile,rows*tile])
    encoded=BytesIO();Image.fromarray(atlas).save(encoded,format='PNG')
    material=ce.textured_material(glb,label,encoded.getvalue(),double_sided=True)
    indices=faces.ravel()
    return glb.primitive(points[indices],normals[indices],np.asarray(atlas_uv),
                         np.arange(len(indices)),material,joints=joints[indices],
                         weights=weights[indices],weight_floats=True)
