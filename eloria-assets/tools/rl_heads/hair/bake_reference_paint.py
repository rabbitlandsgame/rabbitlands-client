"""Bake painted donor surfaces into an explicit, non-overlapping recipient chart.

This optional authoring primitive changes no mesh data. Each covered chart texel
is mapped to a physical recipient point, then to its nearest donor triangle and
that triangle's own UV corners. It never interpolates unrelated donor UV islands
across a recipient triangle. UVs and image rows both use top-left origin.
"""
import numpy as np
import trimesh
from scipy.ndimage import distance_transform_edt


def pack_chart_islands(uv,triangles,padding=.025):
    """Pack disconnected existing charts with positive affine maps, UV only."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    uv=np.asarray(uv);triangles=np.asarray(triangles,int)
    assert 0<=padding<.25 and len(uv)>0 and len(triangles)>0
    edges=triangles[:,[0,1,1,2,2,0]].reshape(-1,2)
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(uv),len(uv)))
    count,labels=connected_components(graph,directed=False)
    columns=int(np.ceil(np.sqrt(count)));rows=int(np.ceil(count/columns));chart=np.zeros_like(uv,dtype=float)
    for index in range(count):
        group=np.flatnonzero(labels==index);low=uv[group].min(0);span=uv[group].max(0)-low
        assert (span>1e-8).all(),'Degenerate recipient chart island'
        local=(uv[group]-low)/span
        chart[group]=(np.array([index%columns,index//columns])+padding+(1-2*padding)*local)/np.array([columns,rows])
    return chart,{'islands':count,'columns':columns,'rows':rows,
                  'local_mapping':'existing UV, per-island positive affine packing','tile_padding_fraction':padding}


def _barycentric(points, triangles):
    a=triangles[:,0];v0=triangles[:,1]-a;v1=triangles[:,2]-a;v2=points-a
    d00=np.einsum('ij,ij->i',v0,v0);d01=np.einsum('ij,ij->i',v0,v1)
    d11=np.einsum('ij,ij->i',v1,v1);d20=np.einsum('ij,ij->i',v2,v0);d21=np.einsum('ij,ij->i',v2,v1)
    denominator=d00*d11-d01*d01
    assert (abs(denominator)>1e-25).all(),'Degenerate donor triangle'
    v=(d11*d20-d01*d21)/denominator;w=(d00*d21-d01*d20)/denominator
    return np.column_stack([1-v-w,v,w])


def _linear_rgba(image):
    image=np.asarray(image)
    assert image.ndim==3 and image.shape[2] in (3,4) and image.dtype==np.uint8,'Source image must be uint8 RGB/RGBA'
    rgba=np.ones((*image.shape[:2],4),dtype='f4');rgba[:,:,:image.shape[2]]=image/255
    rgb=rgba[:,:,:3];rgba[:,:,:3]=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    return rgba


def _sample_rgba(rgba,uv):
    """Bilinear colour sampling in linear light, clamped to the atlas edges."""
    # Normalized GPU texture coordinates address texel centres at (i+.5)/size.
    xy=np.clip(uv*np.array([rgba.shape[1],rgba.shape[0]])-.5,
               [0,0],[rgba.shape[1]-1,rgba.shape[0]-1])
    lo=np.floor(xy).astype(int);hi=np.minimum(lo+1,np.array([rgba.shape[1]-1,rgba.shape[0]-1]));f=xy-lo
    samples=(rgba[lo[:,1],lo[:,0]]*(1-f[:,0,None])*(1-f[:,1,None])+
             rgba[lo[:,1],hi[:,0]]*f[:,0,None]*(1-f[:,1,None])+
             rgba[hi[:,1],lo[:,0]]*(1-f[:,0,None])*f[:,1,None]+
             rgba[hi[:,1],hi[:,0]]*f[:,0,None]*f[:,1,None])
    rgb=samples[:,:3];samples[:,:3]=np.where(rgb<=.0031308,rgb*12.92,1.055*np.maximum(rgb,0)**(1/2.4)-.055)
    return np.rint(np.clip(samples,0,1)*255).astype('u1')


def bake_chart_paint(donor_positions,donor_uv,donor_triangles,
                     recipient_positions,recipient_uv,recipient_triangles,
                     source_rgba,size=(512,512),force_opaque=True,gutter=4):
    """Return an RGBA chart and a receipt; input arrays are never mutated.

    Recipient chart UVs must be unique in [0,1]. Repeated charts must first be
    packed into distinct islands without changing their local triangle mapping.
    A closed coverage layer must use force_opaque=True (the default): donor atlas
    transparency must not turn that coverage layer into holes.
    """
    DP=np.asarray(donor_positions,float);DU=np.asarray(donor_uv,float);DT=np.asarray(donor_triangles,int)
    RP=np.asarray(recipient_positions,float);RU=np.asarray(recipient_uv,float);RT=np.asarray(recipient_triangles,int)
    assert all(np.isfinite(a).all() for a in (DP,DU,RP,RU))
    assert RU.min()>=0 and RU.max()<=1,'Recipient chart must be packed within [0,1]'
    width,height=map(int,size);assert width>=2 and height>=2 and gutter>=0
    points=np.zeros((height,width,3),float);covered=np.zeros((height,width),bool)
    overlaps=0;degenerate=0
    for face in RT:
        uv=RU[face]*np.array([width,height])-.5
        low=np.maximum(np.ceil(uv.min(0)).astype(int),0);high=np.minimum(np.floor(uv.max(0)).astype(int),[width-1,height-1])
        if np.any(high<low):continue
        determinant=np.linalg.det(np.stack([uv[1]-uv[0],uv[2]-uv[0]]))
        if abs(determinant)<1e-10:degenerate+=1;continue
        x,y=np.meshgrid(np.arange(low[0],high[0]+1),np.arange(low[1],high[1]+1));xy=np.column_stack([x.ravel(),y.ravel()])
        vw=(xy-uv[0])@np.linalg.inv(np.stack([uv[1]-uv[0],uv[2]-uv[0]]))
        bc=np.column_stack([1-vw.sum(1),vw]);inside=(bc>=-1e-8).all(1)
        xy=xy[inside];world=bc[inside]@RP[face]
        prior=covered[xy[:,1],xy[:,0]]
        if prior.any():overlaps+=int((np.linalg.norm(points[xy[prior,1],xy[prior,0]]-world[prior],axis=1)>1e-7).sum())
        points[xy[:,1],xy[:,0]]=world;covered[xy[:,1],xy[:,0]]=True
    assert covered.any(),'No recipient chart texels were covered'
    assert not overlaps,f'Recipient chart contains {overlaps} conflicting overlapping texels'
    area=np.linalg.norm(np.cross(DP[DT[:,1]]-DP[DT[:,0]],DP[DT[:,2]]-DP[DT[:,0]]),axis=1)
    valid=area>1e-14;DT=DT[valid];assert len(DT),'Donor has no nondegenerate faces'
    donor=trimesh.Trimesh(DP,DT,process=False);query=points[covered];values=[];distances=[];linear=_linear_rgba(source_rgba)
    for start in range(0,len(query),128):
        closest,distance,face=trimesh.proximity.closest_point(donor,query[start:start+128])
        triangle=DT[face];bc=_barycentric(closest,DP[triangle]);uv=(DU[triangle]*bc[:,:,None]).sum(1)
        values.append(_sample_rgba(linear,uv));distances.append(distance)
    values=np.concatenate(values);distance=np.concatenate(distances)
    assert np.isfinite(distance).all()
    output=np.full((height,width,4),[160,160,160,255],dtype='u1');output[covered]=values
    minimum_alpha=int(values[:,3].min());transparent=int((values[:,3]<255).sum())
    if force_opaque:output[:,:,3]=255
    border=np.zeros_like(covered)
    if gutter:
        distance_to_chart,indices=distance_transform_edt(~covered,return_indices=True)
        border=(~covered)&(distance_to_chart<=gutter)
        output[border]=output[indices[0][border],indices[1][border]]
    receipt={'method':'Physical donor triangle per recipient chart texel; barycentric donor UV; bilinear linear-light colour',
             'continuous_texture_bake':True,'orientation':'UV and image rows: top-left origin',
             'size':[width,height],'covered_texels':int(covered.sum()),'unfilled_covered_texels':0,
             'unused_chart_texels':int((~covered).sum()),'gutter_texels':int(border.sum()),
             'conflicting_overlap_texels':overlaps,'degenerate_recipient_triangles':degenerate,
             'ignored_degenerate_donor_triangles':int((~valid).sum()),
             'projection_max_mm':float(distance.max()*1000),'projection_mean_mm':float(distance.mean()*1000),
             'source_alpha_min':minimum_alpha,'source_nonopaque_samples':transparent,
             'force_opaque':bool(force_opaque),'covered_output_alpha_min':int(output[covered,3].min())}
    return output,receipt
