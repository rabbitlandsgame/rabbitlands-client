"""Fit Crownwater's retained causeway city to named islands in the shared world.

The certified library is immutable. Only island/shelf masks reuse its authored
shore profile; the surrounding ocean and continent remain globally authored.
Surveyed bridge ends provide local abutments and ferry clearance corridors.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator

import landscape as L
import scene_io as S

REGION = 'crownwater'
ASSEMBLY = 'crownwater.causeway-city'
MAX_APPROACH_GRADE = .40


def segment_distance(x, z, a, b):
    a,b=np.asarray(a,float),np.asarray(b,float)
    delta=b-a;length2=float(delta@delta)
    t=np.clip(((x-a[0])*delta[0]+(z-a[1])*delta[1])/max(length2,1e-12),0,1)
    return np.hypot(x-a[0]-t*delta[0],z-a[1]-t*delta[1])


def island_influence(x,z,islands):
    """Only named island shelves participate; no rectangular legacy terrain."""
    result=np.zeros(np.broadcast_shapes(np.shape(x),np.shape(z)),float)
    for island in islands:
        cx,cz=island['center'];rx,rz=island['crownShelfRadii'];angle=float(island.get('angle',0))
        dx,dz=x-cx,z-cz;c,s=math.cos(angle),math.sin(angle)
        r=np.hypot((dx*c-dz*s)/rx,(dx*s+dz*c)/rz)
        distance=(r-1)*min(rx,rz)
        result=np.maximum(result,1-L.smoothstep(0,12,distance))
    return result


def reprofile_causeway(document,body,root,endpoints,new_levels):
    """Copy just this bridge's buffers and change its two end elevations.

    One affine shear moves the deck, arch, rail and piles together. XZ, UVs,
    node names and relative horizontal placement stay unchanged. The two known
    stale source slopes are modest (<.20); this does not move whole buildings.
    """
    document=copy.deepcopy(document);body=bytearray(body)
    matrices,_=S.GR.hierarchy(document)
    a,b=np.asarray(endpoints,float);levels=np.asarray(new_levels,float)
    direction=b[[0,2]]-a[[0,2]];length2=float(direction@direction)
    if length2<1e-6:raise ValueError('Crown causeway has no horizontal span')
    if abs(levels[1]-levels[0])/math.sqrt(length2)>.40:
        raise ValueError('Crown causeway reprofiling would exceed comfortable bridge grade')
    difference=levels-np.array([a[1],b[1]])
    gradient=(difference[1]-difference[0])*direction/length2
    deform=np.eye(4);deform[1,0]=gradient[0];deform[1,2]=gradient[1]
    deform[1,3]=difference[0]-float(gradient@a[[0,2]])
    def append(values):
        values=np.ascontiguousarray(values,dtype='<f4');body.extend(b'\0'*((-len(body))%4))
        view=len(document['bufferViews']);document['bufferViews'].append(
            {'buffer':0,'byteOffset':len(body),'byteLength':values.nbytes})
        body.extend(values.tobytes());index=len(document['accessors'])
        document['accessors'].append({'bufferView':view,'componentType':5126,'count':len(values),
            'type':'VEC3','min':values.min(axis=0).astype(float).tolist(),
            'max':values.max(axis=0).astype(float).tolist()})
        return index
    for index in S.descendants(document,[root]):
        node=document['nodes'][index]
        if 'mesh' not in node:continue
        mesh=copy.deepcopy(document['meshes'][node['mesh']]);m=matrices[index]
        local=np.linalg.inv(m)@deform@m
        for primitive in mesh['primitives']:
            attributes=primitive['attributes'];vertices=S.GR.accessor(document,body,attributes['POSITION']).copy()
            attributes['POSITION']=append(vertices@local[:3,:3].T+local[:3,3])
            if 'NORMAL' in attributes:
                normals=S.GR.accessor(document,body,attributes['NORMAL'])@np.linalg.inv(local[:3,:3])
                normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
                attributes['NORMAL']=append(normals)
        node['mesh']=len(document['meshes']);document['meshes'].append(mesh)
    document['buffers'][0]['byteLength']=len(body)
    return document,bytes(body)


def apply_crown_support(world,content):
    """Call after Content.load, before settle_foundations and road/ferry solve.

    Writes original_height and matching support fields so settle_foundations
    cannot restore unrelated domes. Wet shelves stay unpinned; dry island
    support is authoritative when roads subsequently approach these quays.
    The parent ferry selector must exclude world.ferry_exclusion as well as
    structures. The exporter checks its whole quay/hull footprint against it.
    """
    if REGION not in world.ids:return {}
    saved=getattr(world,'authoring_snapshots',{}).get(REGION)
    if saved is not None:
        # Keep the ferry selector's *actual saved* causeway/quay exclusion,
        # while leaving every scene mesh, placement, and terrain sample alone.
        # Crossing metadata is emitted from the current AssetControl set, so
        # deleting a saved bridge also removes its exclusion on the next bake.
        base_exclusion=np.asarray(getattr(world,'ferry_exclusion',
            np.zeros_like(world.height,dtype=bool)),dtype=bool).copy()
        crossings=content.metadata[REGION].get('crossings',())
        for crossing in crossings:
            endpoints=np.asarray(crossing['endpoints'],float)+saved.translation
            if endpoints.shape!=(2,3) or not np.isfinite(endpoints).all():
                raise ValueError(f"{REGION}: invalid saved ferry crossing {crossing.get('id')}")
            base_exclusion|=segment_distance(world.gx,world.gz,
                endpoints[0,[0,2]],endpoints[1,[0,2]])<=9.
        quays=0;saved_ferry_quays=0
        for obj in content.objects:
            if obj.get('region')!=REGION or 'quay' not in obj.get('node','').lower():continue
            low,high=np.asarray(obj['low'])[[0,2]]-6.,np.asarray(obj['high'])[[0,2]]+6.
            mask=(world.gx>=low[0])&(world.gx<=high[0])&\
                (world.gz>=low[1])&(world.gz<=high[1])
            ferry=(obj.get('source') or {}).get('authoredFerryQuay')
            if ferry is None:base_exclusion|=mask
            else:saved_ferry_quays+=1
            quays+=1
        world.ferry_exclusion_base=base_exclusion
        world.ferry_exclusion_by_owner={}
        world.ferry_exclusion=base_exclusion.copy()
        report={'region':REGION,'skipped':'saved-authoring-authority',
            'savedCrossings':len(crossings),'savedQuayAssets':quays,
            'savedFerryQuayAssets':saved_ferry_quays,
            'ferryExcludedVertices':int(base_exclusion.sum()),
            'supportedVertices':0,
            'policy':'Ferry exclusion from current saved crossing and quay geometry; no native scene or terrain shaping.'}
        world.crown_support_report=report
        return report
    islands=[i for i in world.plan['islands'] if i.get('crownSourceIsland')]
    if len(islands)!=17:raise ValueError('Crownwater requires its 17 named causeway islands')
    shift=np.asarray(content.assembly_records[ASSEMBLY]['translation'],float)
    declared=np.asarray(world.plan['retained_transforms'][REGION],float)
    if not np.allclose(shift,declared,atol=1e-7):raise ValueError('Crown support and retained city transforms differ')
    file=Path(content.library)/REGION/'foundation-samples.npz'
    with np.load(file) as source:
        sampler=RegularGridInterpolator((source['z'],source['x']),source['height'],bounds_error=False,fill_value=np.nan)
    def sample(x,z):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        return sampler(np.c_[z.ravel()-shift[2],x.ravel()-shift[0]]).reshape(x.shape)+shift[1]
    weight=island_influence(world.gx,world.gz,islands)
    target=sample(world.gx,world.gz)
    valid=np.isfinite(target)&(world.owner_at(world.gx,world.gz)==world.ids.index(REGION))
    weight=np.where(valid,weight,0);target=np.where(valid,target,world.original_height)
    surface=world.original_height*(1-weight)+target*weight
    crossings=copy.deepcopy(content.metadata[REGION].get('crossings',[]))
    objects={obj['node']:obj for obj in content.objects if obj['region']==REGION}
    document,body=content.documents[REGION]
    repaired=[];abutments=[];exclusion=np.zeros_like(world.height,dtype=bool)
    for crossing in crossings:
        points=np.asarray(crossing['endpoints'],float)+shift
        a,b=points[:,[0,2]];delta=b-a;length=float(np.linalg.norm(delta))
        if length<1e-6:continue
        exclusion|=segment_distance(world.gx,world.gz,a,b)<=9.
        if not crossing['id'].startswith(('spoke_','ring_','reach_')):continue
        # These two source bridge profiles predate nearby quay/civic terrace
        # corrections. Fit them to the existing source shores, keeping arches.
        if crossing['id'] in ('spoke_pavilion_south','spoke_pavilion_northeast'):
            levels=sample(points[:,0],points[:,2])+.08
            root=objects['Causeway_'+crossing['id']]['index']
            document,body=reprofile_causeway(document,body,root,
                np.asarray(crossing['endpoints']),levels-shift[1])
            repaired.append({'id':crossing['id'],'before':points[:,1].tolist(),'after':levels.tolist(),
                             'grade':abs(float(levels[1]-levels[0]))/length})
            points[:,1]=levels
        for index in (0,1):
            here=points[index];inward=(a-b)/length if index==0 else (b-a)/length
            # Real bridgeheads extend eight metres onto the island. Extend a
            # correction only when the source bank has a larger level change.
            old=float(sample(here[0],here[2]));floor=float(here[1])-.025
            reach=max(8.,abs(floor-old)/.28)
            foot=here[[0,2]]+inward*reach
            far=float(sample(*foot))
            if not math.isfinite(far):continue
            reach=max(reach,abs(floor-far)/MAX_APPROACH_GRADE)
            foot=here[[0,2]]+inward*reach;far=float(sample(*foot))
            if not math.isfinite(far):continue
            dx,dz=world.gx-here[0],world.gz-here[2]
            along=dx*inward[0]+dz*inward[1]
            across=np.abs(dx*inward[1]-dz*inward[0])
            blend=(1-L.smoothstep(3.2,9.,across))*(1-L.smoothstep(reach,reach+8,along))
            # The outer two metres meet the surveyed slab; the water beyond
            # stays a navigable channel rather than acquiring a land bridge.
            blend*=L.smoothstep(-3.,-1.,along)
            profile=floor+(far-floor)*np.clip(along/reach,0,1)
            surface=surface*(1-blend)+profile*blend
            weight=np.maximum(weight,blend)
            abutments.append({'id':crossing['id'],'end':index,'position':here.tolist(),
                'inward':inward.tolist(),'reach':reach,'floor':floor,'inland':far})
    content.documents[REGION]=(document,body)
    matrices,_=S.GR.hierarchy(document)
    for repair in repaired:
        obj=objects['Causeway_'+repair['id']]
        low,high=S.subtree_bounds(document,body,obj['index'],matrices)
        obj['low'][...]=low+shift;obj['high'][...]=high+shift
        content.bounds_by_name[(REGION,obj['node'])]=(obj['low'],obj['high'])
    scope=weight>.001
    world.original_height[scope]=surface[scope];world.height[scope]=surface[scope]
    dry=scope&(surface>.05)
    world.foundation_weight[scope]=0;world.foundation_target[scope]=0
    world.assembly_target[scope]=surface[scope]
    world.assembly_weight[scope]=np.where(dry[scope],1.,0.)
    world.road_target[scope]=surface[scope]
    # Exclude legacy working quays and their full widths as well as causeways.
    for obj in objects.values():
        if 'quay' not in obj['node'].lower():continue
        low,high=obj['low'][[0,2]]-6,obj['high'][[0,2]]+6
        exclusion|=(world.gx>=low[0])&(world.gx<=high[0])&(world.gz>=low[1])&(world.gz<=high[1])
    world.ferry_exclusion=exclusion
    world.ferry_exclusion_base=exclusion.copy()
    world.ferry_exclusion_by_owner={}
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    report={'islands':len(islands),'sourceSha256':hashlib.sha256(file.read_bytes()).hexdigest(),
        'retainedTranslation':shift.tolist(),'reprofiledBridges':repaired,'abutments':abutments,
        'supportedVertices':int(dry.sum()),'ferryExcludedVertices':int(exclusion.sum()),
        'policy':'Named island shelves and surveyed abutments; unchanged global ocean outside those masks; immutable certified library.'}
    world.crown_support_report=report
    return report
