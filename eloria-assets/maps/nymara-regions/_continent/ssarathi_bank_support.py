"""Restore the river bank beside the retained ritual court's old tidal survey.

The ruined colonnade and bridge do not own the seabed in their whole bounding
rectangles. Keep the natural Southern River bank between their actual masonry
and the river, with clearance for the real bridge floor and hatchery descent.
The river profile, sea level, retained architecture and entrances never move.
"""
import math
import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt
import landscape as L
import scene_io as S
from mirror_support import upper_floor_field, sample_upper_clearance

REGION='ssarathi_ruins'
COURT='Colonnade_ritual_plaza'
WALKS=('Bridge_spur_stela__channel_main','HatcheryDescent')
GRID_MARGIN=math.sqrt(2.)*2.
ROAD_BENCH_METRES=8.   # a graded road core keeps its corridor through the restored bank, feathered over this distance


def bank_field(x,z,current,natural,river,plan,walking):
    """Raise imported cuts toward the original bank, with real-floor limits."""
    distance,hydraulic,width=L.river_field(x,z,river)
    wet=L.water_fields(x,z,height=natural,plan=plan)['mask']
    weight=(1.-L.smoothstep(width+20.,width+40.,distance))*(~wet)
    # The occupied river terrace is a low flood bank. Restoring the former
    # hill height farther inland would bury the ceremonial column shafts.
    # Continue the river's bank slope through the old survey cut instead.
    bank=np.minimum(natural,hydraulic+.8+.04*np.maximum(0.,distance-width))
    result=current+np.maximum(0.,bank-current)*weight
    # A full terrain-cell diagonal around the exact floor prevents an adjacent
    # raised vertex from cutting through the middle of a small entrance face.
    for triangles in walking:
        floor,foot_distance=upper_floor_field(triangles,x,z)
        if triangles[:,:,1].min()<0.:
            # The hatchery has submerged stairs. Keep their entire existing
            # terrain footprint, including any inherited buried lower steps;
            # a higher adjacent stair must not authorize filling a lower one.
            keep=L.smoothstep(GRID_MARGIN,GRID_MARGIN+4.,foot_distance)
            result=current+(result-current)*keep
            continue
        cap=floor-.06+np.maximum(0.,foot_distance-GRID_MARGIN)*.5
        result=np.minimum(result,np.maximum(current,cap))
    return result


def apply_ssarathi_banks(world,content):
    if REGION not in world.ids:return {}
    court=content.placement_by_name[(REGION,COURT)]
    doc,body=content.documents[REGION]
    walks=[];floor_samples=[]
    for name in WALKS:
        obj=content.placement_by_name[(REGION,name)]
        nodes=[i for i in S.descendants(doc,[obj['index']])
               if 'mesh' in doc['nodes'][i] and doc['nodes'][i].get('name','').startswith('Walk_')]
        triangles=S.GR.triangles(doc,body,nodes)+obj['shift']
        n=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        triangles=triangles[n[:,1]>.6*np.linalg.norm(n,axis=1)]
        if not len(triangles):raise ValueError(name+': actual floor required for river-bank support')
        walks.append(triangles)
        lo=triangles[:,:,[0,2]].min(axis=(0,1));hi=triangles[:,:,[0,2]].max(axis=(0,1))
        sx,sz=np.meshgrid(np.arange(lo[0],hi[0]+.125,.25),np.arange(lo[1],hi[1]+.125,.25))
        extra=np.concatenate((triangles.reshape(-1,3),triangles.mean(axis=1)))
        sx=np.r_[sx.ravel(),extra[:,0]];sz=np.r_[sz.ravel(),extra[:,2]]
        floor,distance=upper_floor_field(triangles,sx,sz);inside=distance<1e-7
        sx,sz,floor=sx[inside],sz[inside],floor[inside]
        floor_samples.append((sx,sz,floor,world.height_at(sx,sz)))
    low=court['low'][[0,2]]-40.;high=court['high'][[0,2]]+40.
    ix0,iz0=np.maximum(0,np.floor((low-[world.x0,world.z0])/2).astype(int))
    ix1,iz1=np.minimum([len(world.x),len(world.z)],np.ceil((high-[world.x0,world.z0])/2).astype(int)+1)
    sl=np.s_[iz0:iz1,ix0:ix1]
    x,z=world.gx[sl],world.gz[sl];old=world.height[sl].copy();natural=world.original_height[sl]
    river=next(r for r in world.plan['rivers'] if r['id']=='southern_river')
    corrected=bank_field(x,z,old,natural,river,world.plan,walks)
    # The patch stops before its source bounds; no rectangular edge can enter
    # the restored landform. Outside the court's old apron nothing is changed.
    edge=np.minimum.reduce((x-low[0],high[0]-x,z-low[1],high[1]-z))
    corrected=old+(corrected-old)*L.smoothstep(0.,20.,edge)
    # A graded road keeps its corridor through the restored bank: the core
    # stays as the road grading left it and the bank returns beside it over
    # eight metres. The secrets-door branch, kept out of the lineage house by
    # the retained solids, otherwise climbed the restored bank at a 1.5 grade.
    if getattr(world,'roads',None):
        core=binary_dilation(world.road_distance[sl]<=1.65,iterations=1)
        if core.any():
            keep=1.-L.smoothstep(0.,ROAD_BENCH_METRES,distance_transform_edt(~core)*2.)
            corrected=old*keep+corrected*(1.-keep)
    delta=corrected-old;changed=delta>1e-8
    world.height[sl]=corrected
    additional_burial={}
    for name,(sx,sz,floor,before) in zip(WALKS,floor_samples):
        after=world.height_at(sx,sz)
        added=np.maximum(after-floor,0.)-np.maximum(before-floor,0.)
        additional_burial[name]=float(added.max(initial=0.))
        if additional_burial[name]>1e-6:
            world.height[sl]=old
            raise ValueError(name+': restoring the river bank would add burial to its actual floor')
    world.assembly_target[sl]=np.where(changed,np.maximum(world.assembly_target[sl],corrected),world.assembly_target[sl])
    report={'policy':'Natural river bank restored outside real ritual bridge and descent floors',
            'changedVertices':int(changed.sum()),'maximumFill':float(delta.max(initial=0.)),
            'riverLevelUnchanged':True,'retainedGeometryUnchanged':True,
            'maximumAddedFloorBurial':additional_burial,
            'walkClearance':{name:sample_upper_clearance(world,triangles) for name,triangles in zip(WALKS,walks)}}
    world.ssarathi_bank_support=report
    return report
