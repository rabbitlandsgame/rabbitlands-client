"""Graded banks around Manymouth's retained architectural entrances.

The arch, temple and stelae discoveries keep rigid authored geometry. Their
surrounding bank follows real upper floor triangles, rather than the obsolete
regional trenches in the foundation samples. Small standing stones remain
terrain dressing: Content.reground settles them onto the final local grade.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import ConvexHull
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import cg

REGION = 'manymouth_delta'
ARCH = REGION+'.great-arch'
TEMPLE = REGION+'.green-temple'
COURT = REGION+'.stelae-court'
TEMPLE_QUAY = REGION+'.temple_quay'
TEMPLE_QUAY_FLOORS = ('Landing_temple_quay', *(f'temple_quay_porch_{i:02d}' for i in range(6)))
REFERENCES = {
    ARCH: ((108.96047980956422, -97.68252372878746), 'terrain'),
    TEMPLE: ((260.08404918038485, -218.86008126097346), 'terrain'),
    COURT: ((207.3035, -169.0664), 'terrain'),
}
ARCH_NODES = frozenset(('Landmark_GreatArch', 'arch_platform',
    'Landmark_DeckStudy', 'Landing_arch_stair', 'Secret_delta_arch_focus',
    'Secret_delta_study_school', 'SecretAccess_delta_study_school'))
TEMPLE_NODES = frozenset(('Landmark_GreenTemple', 'Landing_green_temple'))
COURT_NODES = frozenset(('Landmark_StelaeCourt', 'Landing_ruin_stelae',
    'Secret_delta_stelae_reliquary', 'SecretAccess_delta_stelae_reliquary'))


def placement_group(name):
    if name in ARCH_NODES:return ARCH
    if name in TEMPLE_NODES:return TEMPLE
    if name in COURT_NODES:return COURT
    return None


def upper_floor(points, triangles):
    """Highest upward, walkable triangle at each XZ, never sleepers or roofs."""
    points=np.asarray(points,float)
    result=np.full(len(points),-np.inf)
    for triangle in np.asarray(triangles,float):
        normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0])
        length=np.linalg.norm(normal)
        if length<1e-9 or normal[1]/length<1/math.sqrt(1+.65**2):continue
        q=triangle[:,[0,2]];low=q.min(axis=0);high=q.max(axis=0)
        at=np.flatnonzero(np.all((points>=low-1e-7)&(points<=high+1e-7),axis=1))
        if not len(at):continue
        edge=np.roll(q,-1,axis=0)-q;rel=points[at,None,:]-q[None,:,:]
        cross=edge[None,:,0]*rel[:,:,1]-edge[None,:,1]*rel[:,:,0]
        at=at[np.all(cross>=-1e-7,axis=1)|np.all(cross<=1e-7,axis=1)]
        if not len(at):continue
        y=triangle[0,1]-((points[at]-triangle[0,[0,2]])*normal[[0,2]]).sum(axis=1)/normal[1]
        result[at]=np.maximum(result[at],y)
    return result


def smooth_bank_levels(target,fixed):
    """Interpolate soil between real floor aprons without nearest-floor steps.

    Fixed apron levels retain their source geometry. A harmonic extension with
    a free outer boundary fills only the surrounding soil; the separate bank
    influence still fades to zero outside its authored footprint.
    """
    result=np.asarray(target,float).copy();free=~np.asarray(fixed,bool)
    if not np.any(fixed):raise ValueError('Bank level interpolation needs real floor constraints')
    if not np.any(free):return result
    count=int(free.sum());index=np.full(free.shape,-1,np.int32);index[free]=np.arange(count)
    padded_index=np.pad(index,1,constant_values=-2);padded_target=np.pad(result,1)
    rows=[];cols=[];values=[];rhs=np.zeros(count);degree=np.zeros(count)
    h,w=free.shape
    for dz,dx in ((-1,0),(1,0),(0,-1),(0,1)):
        neighbour=padded_index[1+dz:1+dz+h,1+dx:1+dx+w][free]
        level=padded_target[1+dz:1+dz+h,1+dx:1+dx+w][free]
        interior=neighbour>=0;degree+=neighbour!=-2
        rows.append(np.flatnonzero(interior));cols.append(neighbour[interior]);values.append(np.full(int(interior.sum()),-1.))
        rhs+=np.where(neighbour==-1,level,0.)
    rows.append(np.arange(count));cols.append(np.arange(count));values.append(degree)
    matrix=coo_matrix((np.concatenate(values),(np.concatenate(rows),np.concatenate(cols))),shape=(count,count)).tocsr()
    solution,status=cg(matrix,rhs,x0=result[free],rtol=1e-10,atol=1e-8,maxiter=1000)
    if status or not np.isfinite(solution).all():raise ValueError('Temple bank level interpolation did not converge')
    result[free]=solution
    return result


def bank_fields(x,z,triangles,*,apron=4.,feather=32.,clearance=.18,smooth_levels=False):
    """One continuous bank with a dry head against the real deck perimeter.

    An eight-metre sample patch must contain its actual floor; a missing floor
    is a build error. Sampling highest Walk triangles avoids supporting the
    underside of a wooden landing. The outer blend is deliberately broad.
    """
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    if x.ndim!=2 or min(x.shape)<2:raise ValueError('Bank lattice must be two-dimensional')
    floor=upper_floor(np.c_[x.ravel(),z.ravel()],triangles).reshape(x.shape)
    valid=np.isfinite(floor)
    if not valid.any():raise ValueError('No actual upper floor intersects the bank lattice')
    spacing_x=float(x[0,1]-x[0,0]);spacing_z=float(z[1,0]-z[0,0])
    distance,nearest=distance_transform_edt(~valid,sampling=(spacing_z,spacing_x),return_indices=True)
    target=floor[tuple(nearest)]-clearance
    if smooth_levels:target=smooth_bank_levels(target,distance<=apron)
    t=np.clip(1-np.maximum(0,distance-apron)/feather,0,1)
    return target,t*t*(3-2*t),valid


def overlay_bank(previous_target,previous_weight,target,weight):
    """Compose a local bank over an existing footing without a winner seam.

    The old field still contributes through the new bank's smooth feather.
    Switching targets wherever their weights cross creates a cliff even when
    both individual masks are smooth. This composition has exactly the height
    of the previous supported terrain blended toward the new floor target.
    A full new bank core remains exact; zero influence preserves the old field.
    """
    combined=previous_weight*(1-weight)+weight
    numerator=previous_target*previous_weight*(1-weight)+target*weight
    return np.divide(numerator,combined,out=np.asarray(previous_target,float).copy(),
                     where=combined>0),combined


def _triangles(content,obj,*,walk=True,base=None,matrices=None):
    import scene_io as S
    document,body=content.documents[REGION]
    if matrices is None:matrices,_=S.GR.hierarchy(document)
    result=[]
    for index in S.descendants(document,[obj['index']]):
        node=document['nodes'][index];name=node.get('name','')
        if 'mesh' not in node or (walk and not name.startswith('Walk_')):continue
        if any(s in name.lower() for s in ('ceiling','roof','canopy')):continue
        for primitive in document['meshes'][node['mesh']]['primitives']:
            if primitive.get('mode',4)!=4:continue
            points=S.GR.accessor(document,body,primitive['attributes']['POSITION'])
            order=S.GR.accessor(document,body,primitive['indices']).ravel() if 'indices' in primitive else np.arange(len(points))
            matrix=matrices[index]
            triangles=points[order.reshape(-1,3)]@matrix[:3,:3].T+matrix[:3,3]+obj['shift']
            if base is not None:
                # The stepped temple needs one footing under its actual base,
                # not a terrace at the roof or upper stair height.
                points=triangles.reshape(-1,3)
                points=points[np.abs(points[:,1]-base)<.03]
                if len(points)<3:continue
                q=np.unique(np.round(points[:,[0,2]],5),axis=0)
                if len(q)<3:continue
                hull=ConvexHull(q);q=q[hull.vertices]
                center=q.mean(axis=0)
                triangles=np.array([[[center[0],base,center[1]],
                    [b[0],base,b[1]],[a[0],base,a[1]]]
                    for a,b in zip(q,np.roll(q,-1,axis=0))])
            result.extend(triangles)
    return np.asarray(result,float).reshape(-1,3,3)


def apply_manymouth_support(world,content,*,sites=None):
    """Apply bounded support before settle_foundations and road planning."""
    import scene_io as S
    matrices,_=S.GR.hierarchy(content.documents[REGION][0])
    objects={o['node']:o for o in content.objects if o['region']==REGION}
    sites=sites or ((ARCH,('arch_platform','Landing_arch_stair','SecretAccess_delta_study_school')),
           (TEMPLE,('Landing_green_temple',)),
           (COURT,('Landing_ruin_stelae','SecretAccess_delta_stelae_reliquary')),
           (TEMPLE_QUAY,TEMPLE_QUAY_FLOORS))
    reports=[]
    for identity,names in sites:
        if not all(name in objects for name in names):raise ValueError(identity+': retained landing is missing')
        pieces=[_triangles(content,objects[name],matrices=matrices) for name in names]
        if any(not len(p) for p in pieces):raise ValueError(identity+': retained landing has no Walk triangles')
        if identity==TEMPLE:
            temple=objects['Landmark_GreenTemple']
            level=float(temple['source']['position'][1]+temple['shift'][1])
            pieces.append(_triangles(content,temple,walk=False,base=level,matrices=matrices))
        triangles=np.concatenate(pieces)
        low=triangles.min(axis=(0,1))[[0,2]]-44
        high=triangles.max(axis=(0,1))[[0,2]]+44
        ix0=max(0,int((low[0]-world.x0)/2));ix1=min(len(world.x),int((high[0]-world.x0)/2)+2)
        iz0=max(0,int((low[1]-world.z0)/2));iz1=min(len(world.z),int((high[1]-world.z0)/2)+2)
        sl=np.s_[iz0:iz1,ix0:ix1]
        target,weight,core=bank_fields(world.gx[sl],world.gz[sl],triangles,
            apron=6 if identity==TEMPLE else 4,smooth_levels=identity==TEMPLE_QUAY)
        own=world.owner_at(world.gx[sl],world.gz[sl])==world.ids.index(REGION)
        weight*=own
        # A bank replaces the obsolete survey underneath this architecture.
        # Equal hard weights must not preserve the former river-shaped trench.
        replace=(weight>=world.assembly_weight[sl])&(weight>0)
        if identity==TEMPLE_QUAY:
            # The quay lies below East hamlet's occupied bank. Both retain
            # their actual floors; their soil aprons must meet continuously.
            world.assembly_target[sl],world.assembly_weight[sl]=overlay_bank(
                world.assembly_target[sl],world.assembly_weight[sl],target,weight)
            replace=weight>0
        else:
            world.assembly_target[sl]=np.where(replace,target,world.assembly_target[sl])
            world.assembly_weight[sl]=np.maximum(world.assembly_weight[sl],weight)
        reports.append({'assembly':identity,'floorNodes':list(names),'actualFloorVertices':int(core.sum()),
            'bankVertices':int(np.count_nonzero(replace)),'clearance':.18,'outerFeather':32.,
            'floorRange':[float(target[core].min()+.18),float(target[core].max()+.18)]})
    report={'sites':reports,'policy':'Rigid architecture, actual upper floor contacts, broad dry bank approaches; original drainage remains authoritative.'}
    world.manymouth_support=report;content.manymouth_support=report
    return report
