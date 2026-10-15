"""Fit the existing east-gate to Mirrorhold approach onto a continuous roadbed.

The civic survey remains fixed beneath its buildings. Outside the east gate,
its old terrain feather must not introduce a trough and a cliff across the
continental road. This is visible authored earthwork, applied after grading.
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import distance_transform_edt
import landscape as L
from world_layout import corridor_grade

ROAD='four_gates--mirrorhold-four_gates'
ENTRY=np.array([649.5,823.6])
EXIT=np.array([652.5,758.5])
SHOULDER=28.


def path_field(points,levels,x,z):
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    distance=np.full(np.shape(x),np.inf);height=np.zeros_like(distance);along=np.zeros_like(distance)
    stations=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    for index,(a,b) in enumerate(zip(points,points[1:])):
        delta=b-a;length=float(np.linalg.norm(delta))
        t=np.clip(((x-a[0])*delta[0]+(z-a[1])*delta[1])/max(length**2,1e-10),0,1)
        d=np.hypot(x-a[0]-t*delta[0],z-a[1]-t*delta[1]);closer=d<distance
        height=np.where(closer,levels[index]+t*(levels[index+1]-levels[index]),height)
        along=np.where(closer,stations[index]+t*length,along);distance=np.minimum(distance,d)
    return height,distance,along,stations[-1]


def approach_profile(points,levels):
    """Keep both surveyed joins and their grades, removing the imported dip."""
    stations=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    length=stations[-1];t=stations/length
    start=np.clip((levels[1]-levels[0])/(stations[1]-stations[0]),-.3,.4)
    end=np.clip((levels[-1]-levels[-2])/(stations[-1]-stations[-2]),-.3,.4)
    profile=(2*t**3-3*t**2+1)*levels[0]+(t**3-2*t**2+t)*length*start
    profile+=(-2*t**3+3*t**2)*levels[-1]+(t**3-t**2)*length*end
    if np.max(np.abs(np.diff(profile)/np.diff(stations)))>.45:
        raise ValueError('Four Gates east approach needs a longer authored climb')
    return profile


def apply_four_gates_support(world,content):
    if 'four_gates' not in world.ids:return {}
    road=next((r for r in world.roads if r['id']==ROAD),None)
    if road is None:raise ValueError('Four Gates to Mirrorhold authored road is missing')
    full=np.asarray(road['points'],float);xz=full[:,[0,2]]
    first=int(np.argmin(np.linalg.norm(xz-ENTRY,axis=1)));last=int(np.argmin(np.linalg.norm(xz-EXIT,axis=1)))
    if first>=last or last-first<8:raise ValueError('Four Gates authored approach endpoints do not follow the road')
    points=xz[first:last+1];levels=full[first:last+1,1]
    profile=approach_profile(points,levels)
    width=float(road['width'])+3.
    low=points.min(axis=0)-width-SHOULDER;high=points.max(axis=0)+width+SHOULDER
    ix0,iz0=np.maximum(0,np.floor((low-[world.x0,world.z0])/2).astype(int))
    ix1,iz1=np.minimum([len(world.x),len(world.z)],np.ceil((high-[world.x0,world.z0])/2).astype(int)+1)
    sl=np.s_[iz0:iz1,ix0:ix1];gx,gz=world.gx[sl],world.gz[sl]
    target,distance,along,length=path_field(points,profile,gx,gz)
    active=distance<=width
    target=corridor_grade(target,active,maximum_grade=.42)
    weight=(1-L.smoothstep(width,width+SHOULDER,distance))*L.smoothstep(0,8,along)*L.smoothstep(0,8,length-along)
    # Occupied wall/building footprints retain their current surveyed support.
    # The gate itself is a traversable compound; its opening has no body here.
    occupied=np.zeros_like(weight,dtype=bool)
    for obj in content.objects:
        if not obj.get('collides') or obj.get('kind') in ('tree','rock','foliage','undergrowth','scrub'):continue
        a,b=obj['low'],obj['high']
        occupied|=(gx>=a[0]-1)&(gx<=b[0]+1)&(gz>=a[2]-1)&(gz<=b[2]+1)
    if occupied.any():weight*=L.smoothstep(0,12,distance_transform_edt(~occupied)*2.)
    weight*=~world.water['mask'][sl]
    old=world.height[sl].copy();updated=old*(1-weight)+target*weight
    world.height[sl]=updated
    # Keep later support consumers consistent with this final visible ground.
    changed=weight>0
    world.assembly_target[sl]=np.where(changed,updated,world.assembly_target[sl])
    full[first:last+1,1]=world.height_at(points[:,0],points[:,1])
    road['points']=full.tolist()
    report={'road':ROAD,'entry':full[first].tolist(),'exit':full[last].tolist(),
            'lengthMetres':float(length),'coreHalfWidthMetres':width,'shoulderMetres':SHOULDER,
            'changedVertices':int(np.count_nonzero(np.abs(updated-old)>1e-8)),
            'maximumFill':float(np.max(updated-old,initial=0)),'maximumCut':float(np.max(old-updated,initial=0)),
            'occupiedFootingsUnchanged':bool(np.array_equal(updated[occupied],old[occupied])),
            'waterGroundUnchanged':bool(np.array_equal(updated[world.water['mask'][sl]],old[world.water['mask'][sl]])),
            'policy':'Visible east-gate ascent on the existing route; unchanged structures, portals, lake and crossing lanes.'}
    for label,region in (('fullRoad',distance<=road['width']),('shoulder',(distance>width)&(distance<width+SHOULDER))):
        region&=(along>8)&(along<length-8)
        cells=region[:-1,:-1]&region[1:,:-1]&region[:-1,1:]&region[1:,1:]
        values=[]
        for field in (old,updated):
            dx=np.diff(field,axis=1)/2.;dz=np.diff(field,axis=0)/2.
            grades=np.stack((np.hypot(dx[:-1],dz[:,:-1]),np.hypot(dx[1:],dz[:,1:])),axis=-1)[cells]
            values.append({'triangles':int(grades.size),'maximum':float(grades.max(initial=0)),
                'p95':float(np.percentile(grades,95)) if grades.size else 0.})
        report[label+'Grades']={'before':values[0],'after':values[1]}
    world.four_gates_support=report
    return report
