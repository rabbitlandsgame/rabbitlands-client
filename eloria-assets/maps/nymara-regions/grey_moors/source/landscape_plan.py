"""384 m burial moor: working peat refuge, open grazing and wet ritual country.

Author in the original survey, then shorten journeys with two protected bands.
The refuge and Great Barrow crown retain human dimensions. The runtime has no
coordinate trick: every exported point and the collision survey are in metres.
"""
from copy import deepcopy
import math
import numpy as np
from amberwood import landscape as LAND, terrain as TER, noise as N
from amberwood import routecraft as RC, props as P, civiccraft as CIV
from compact_landscape import Axis, CompactLandscape
from regionbuild import Placement
import region as REG
import layout

SERVER_CELLS=384
SERVER_ORIGIN=(116.0,116.0)
PLAY_MIN_X,PLAY_MAX_X=-116.0,267.0
PLAY_MIN_Z,PLAY_MAX_Z=-267.0,116.0

def _survey(lo,hi,newlo,newhi,bands):
    """Retain several inhabited or monumental intervals, compress their gaps."""
    length=sum(b-a for a,b in bands)
    slope=((newhi-newlo)-length)/((hi-lo)-length)
    points=[lo]+[p for band in bands for p in band]+[hi]
    target=[newlo]
    for i in range(len(points)-1):
        target.append(target[-1]+(points[i+1]-points[i])*(1 if i%2 else slope))
    axis=Axis(lo,hi,newlo,newhi,bands[0])
    axis.old=np.asarray(points,float);axis.new=np.asarray(target,float)
    return axis

PLAN=CompactLandscape(_survey(-174,402,-116,268,[(-46,15),(85,145)]),
                      _survey(-402,174,-268,116,[(-296,-236),(-25,15)]),
                      REG.SERVER_ORIGIN,SERVER_ORIGIN)

# The north croft belongs to a lee-side enclosure, clear of the Amberwood collar.
# This is a real authoring relocation (the old north croft has no interior door).
NORTH_CROFT=(-66.0,-322.0)
YARD_PATHS={
 'refuge_front':([(-39,-3),(-21,-4),(-9,-3),(-2,0)],3.2),
 'refuge_store':([(-24,-3),(-26,-13),(-35,-18)],2.1),
 'drover_yard':([(-34,0),(-34,6),(-29,12)],2.4),
 'croft_west_yard':([(-105,-65),(-120,-53)],2.6),
 'north_croft_yard':([(-35,-329),(-51,-324),NORTH_CROFT],2.6),
 'peat_workyard':([(-66,-3),(-77,-9),(-78,-19)],3.0),
 'coast_loading':([(-60,72),(-54,66),(-48,66)],3.0),
}

def prepare(t,seed):
    """Landform and settlement survey before structures or vegetation."""
    # The horizontal moor opens to a country beyond. Rim walls are removed in
    # region.build_terrain; isolated tower shoulders and burial ridge remain.
    # Busy refuges have irregular compacted earth, stone at the building front.
    refuge=(t.gx>-48)&(t.gx<17)&(t.gz>-27)&(t.gz<18)
    t.surface[refuge & (t.surface==TER.CAUSEWAY)]=TER.HEATHER_MOOR
    for name,(points,width) in YARD_PATHS.items():
        h=[max(2.0,float(t.height_at(x,z))) for x,z in points]
        RC.grade_road(t,points,h,width=width+1.8,shoulder=5,
                      surface=TER.MOOR_TRACK,clearance=2.5)
        LAND.worn_path(t,points,width,seed+N.stable_hash(name)%997,surface=TER.MOOR_TRACK)
    court=np.maximum(abs(t.gx+17)-10,abs(t.gz+6)-5)
    level=float(t.height_at(-16,-11))
    LAND.feather_level(t,court,level,7)
    t.surface[court<0]=TER.MOOR_TRACK;t.tree_block|=court<5
    # Two useful yards: peat drying on the west and a low pony pen south.
    for x,z,rx,rz in [(-34,-17,9,6),(-33,7,9,7),(*NORTH_CROFT,9,7),(-49,65,8,6)]:
        d=np.maximum(abs(t.gx-x)-rx,abs(t.gz-z)-rz)
        LAND.feather_level(t,d,max(2,float(t.height_at(x,z))),6)
        t.surface[d<0]=TER.MOOR_TRACK;t.tree_block|=d<5
    # Road paint narrows to use while the surveyed walking bed remains wide.
    road=LAND.distance_field(t,list(REG.ROUTES.values()))
    painted=np.isin(t.surface,[TER.CAUSEWAY,TER.MOOR_TRACK])
    wilderness=~refuge & (road>2.5) & painted
    t.surface[wilderness]=np.where(t.height[wilderness]<2.8,TER.PEAT_BOG,TER.HEATHER_MOOR)
    for name,points in REG.ROUTES.items():
        LAND.worn_path(t,points,3.8 if 'causeway' in name or name=='haven_road' else 2.6,
                        seed+N.stable_hash(name)%997,
                        surface=TER.CAUSEWAY if 'causeway' in name else TER.MOOR_TRACK)
    # North is wet meadow giving way to heather; a broad low saddle replaces
    # the former sharp perimeter ramp. Final reciprocal collar is root-owned.
    RC.grade_road(t,[(-12,-430),(-12,-383),(-25,-351),(-12,-336)],
                  [4.0,4.0,4.0,4.2],width=7,shoulder=42,
                  surface=TER.MOOR_TRACK,clearance=7)
    # Drained seasonal pasture beside the refuge stays legible for low risk
    # wildlife, while the black basins farther northeast retain sedge cover.
    open_ground=np.zeros_like(t.height)
    for x,z,rx,rz in [(-92,-25,42,33),(25,32,32,22),(185,41,38,26),(-61,-318,30,21)]:
        d=np.hypot((t.gx-x)/rx,(t.gz-z)/rz)
        open_ground=np.maximum(open_ground,1-LAND.smoothstep(.55,1.1,d))
    water=LAND.distance_field(t,list(REG.STREAMS.values()))
    patches=N.warped_fbm(t.gx/31,t.gz/31,warp=.6,octaves=2,seed=seed+44)
    t.moor_habitat=(.18+.72*LAND.smoothstep(.3,.7,patches))*(1-.85*open_ground)
    t.moor_habitat*=LAND.smoothstep(3,7,road)
    t.moor_habitat*=1-.7*LAND.smoothstep(.35,.8,t.slope_grid()) if hasattr(t,'slope_grid') else 1
    t.moor_open=open_ground
    t.moor_wet=1-LAND.smoothstep(5,22,water)

def dress(build,seed):
    t=build.terrain
    # Visually useful everyday work, tucked against walls and yard margins.
    props=[('SmithBench',P.workbench(seed=seed+1),(-12,-11),0),
           ('ChandlerBench',P.workbench(length=1.8,seed=seed+2,tools=False),(-21,-11),0),
           ('FuelCart',P.cart(seed=seed+3),(-36,-15),.22),
           ('DryingPeat',P.log_pile(length=2.2,rows=2,per_row=5,seed=seed+4),(-32,-18),0),
           ('DryingPeat2',P.log_pile(length=2.2,rows=2,per_row=5,seed=seed+5),(-27,-18),0),
           ('CoveCargo',P.crate(size=.95,seed=seed+6),(-48,66),.15),
           ('CoveCargo2',P.barrel(seed=seed+7),(-51,66),0),
           ('CoveTackle',P.fishing_gear(seed=seed+8),(-48,62),0),
           ('DroverWater',P.barrel(radius=.5,height=.65,seed=seed+9),(-40,7),0),
           ('PeatReeveBench',P.workbench(seed=seed+10,tools=False),(-73,-16),.3)]
    for name,item,(x,z),angle in props:
        for part in getattr(item,'all_parts',[item]):
            part.material='dark_iron' if part.material=='dark_iron' else 'grey_bog_timber'
        key='Prop_WorkingMoor_'+name
        build.add_mesh(key,item)
        build.place(Placement(key,key,(x,float(t.height_at(x,z)),z),angle))
    # Scatter obeys habitat and burial use instead of filling eligible ground.
    rng=np.random.default_rng(seed+839)
    kept=[]
    for p in build.placements:
        x,_,z=p.position
        ix=int(np.clip(round((x-t.x0)/t.cell),0,t.cols-1))
        iz=int(np.clip(round((z-t.z0)/t.cell),0,t.rows-1))
        if p.node.startswith('Scatter_Scrub_'):
            if rng.random()>t.moor_habitat[iz,ix]:continue
            if t.moor_wet[iz,ix]>.5:p.scale*=1.15
        elif p.node.startswith('Scatter_Menhir_'):
            ritual=min(np.hypot((x-a)/rx,(z-b)/rz) for a,b,rx,rz in
                       [(112,-270,92,64),(286,-202,72,74),(-82,-162,44,67),(168,55,46,29)])
            if ritual>1.05 or t.moor_open[iz,ix]>.25:continue
        elif p.node.startswith('Scatter_Erratic_'):
            if t.moor_open[iz,ix]>.45 or rng.random()<.45:continue
        kept.append(p)
    build.placements[:]=kept
    build.notes.append('Inhabited 384 m survey: protected peat refuge and Great Barrow; connected work yards; grazing clearings, wet sedge and ritual stone clusters.')

def lines(values):
    return {name:np.array([(float(PLAN.x(x)),float(PLAN.z(z))) for x,z in points])
            for name,points in values.items()}

def prepare_access(build,seed):
    """Household and crypt entrances connect to the nearest surveyed track."""
    t=build.terrain
    build.access_routes={}
    for portal in build.portals:
        if portal.get('type')!='interior-entrance':continue
        x,y,z=portal['position'];point=np.array([x,z])
        best=None;distance=1e9
        for line in REG.ROUTES.values():
            for a,b in zip(line[:-1],line[1:]):
                d=b-a
                u=float(np.clip(np.dot(point-a,d)/max(np.dot(d,d),1e-9),0,1))
                hit=a+u*d;gap=float(np.linalg.norm(point-hit))
                if gap<distance:best=hit;distance=gap
        if best is None or distance>32 or distance<.1:continue
        target=float(t.height_at(x,z));road=float(t.height_at(*best))
        RC.grade_road(t,[best,point],[road,target],width=3.1,shoulder=4,
                      surface=TER.MOOR_TRACK,clearance=2)
        LAND.worn_path(t,[best,point],2.4,seed+N.stable_hash(portal['id'])%997,
                        surface=TER.MOOR_TRACK)
        build.access_routes['access-'+portal['id']]=[best,point]
        # A grave's threshold is a use point in front of its lintel, with a
        # small off-road stopping place, never the closed masonry's centre.
        portal['position'][1]=round(float(t.height_at(x,z))+.1,2)

def compact(build):
    # Water skins and bridge timbers must follow their bank coordinates; houses,
    # stones and work furniture retain metre-scale construction.
    for p in build.placements:
        if p.node.startswith('Water_') or getattr(build.meshes[p.mesh],'walk_bounds',lambda:None)() is not None:
            p.walk_surface=True
    PLAN.apply(build)
    # Keep crossing widths at human scale: shorten the span between surveyed
    # banks, then rebuild its timber or stone kit at the original usable width.
    for crossing in build.crossings:
        name=crossing['id']
        p=next((p for p in build.placements if p.node=='Landmark_'+name),None)
        if p is None:continue
        a,b=np.asarray(crossing['endpoints'],float)
        length=float(np.linalg.norm((b-a)[[0,2]]))
        stone=name in REG.BRIDGE_ROUTES
        if stone:
            group=RC.graded_causeway([(0,a[1],0),(0,b[1],length)],width=4.2,
                    thickness=.28,parapet=.38,foot=-2,stone='grey_drystone',paving='grey_causeway')
        else:
            group=CIV.sloped_boardwalk(length,a[1],b[1],width=3.2,foot=-2,
                    timber='grey_bog_timber',rope='timber_grey')
        group.translate(0,0,-length/2)
        build.meshes[p.mesh]=group
        p.position=(float((a[0]+b[0])/2),0,float((a[2]+b[2])/2))
        p.rotation_y=math.atan2(b[0]-a[0],b[2]-a[2]);p.scale=1;p.walk_surface=True
    # Water must never become a walking surface merely because it was surveyed.
    for p in build.placements:
        if p.node.startswith('Water_'):p.walk_surface=False
    roads=list(lines(REG.ROUTES).values())+list(lines({k:v[0] for k,v in YARD_PATHS.items()}).values())
    roads+=list(lines(getattr(build,'access_routes',{})).values())
    xs=np.array([p.position[0] for p in build.placements]);zs=np.array([p.position[2] for p in build.placements])
    distance=np.full(xs.shape,np.inf)
    for road in roads:distance=np.minimum(distance,TER._polyline_distance(xs,zs,road)[0])
    # Compression shortens only travel. Restore full human clearance explicitly.
    kept=[]
    for p,d in zip(build.placements,distance):
        if p.node.startswith('Scatter_') and d<(4.8 if p.kind=='stone' else 3.4):continue
        if p.kind=='tree' and d<5.5 and not p.landmark:continue
        kept.append(p)
    build.placements[:]=kept
    used={p.mesh for p in kept};build.meshes={k:v for k,v in build.meshes.items() if k in used}
    build.landscape_revision='inhabited-384-v1'
    # The shared reciprocal survey grades/cuts this collar and supplies the
    # actual region-view subset. Ordinary ferry travel keeps its own identity.
    from streaming_borders import apply as stitch_border
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_outer'))
    import outer_aprons
    outer_snapshot = outer_aprons.capture(build, 'grey_moors')
    stitch_border(build,'grey_moors')
    outer_aprons.apply(build, 'grey_moors', outer_snapshot)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    import manymouth_approach
    manymouth_approach.prepare(build)
    connector_finish.apply(build, 'grey_moors')
    manymouth_approach.finish(build)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_color'))
    import terrain_paint
    terrain_paint.apply(build, 'grey_moors')

def content_layout():
    result=PLAN.metadata(deepcopy(layout.CONTENT_LAYOUT))
    result['npcs']={name:PLAN.point(p) for name,p in layout.CONTENT_LAYOUT['npcs'].items()}
    for category in ('harvest','wildlife'):
        result[category]={name:[[float(PLAN.x(x)),float(PLAN.z(z)),r*.66] for x,z,r in patches]
                          for name,patches in layout.CONTENT_LAYOUT[category].items()}
    return result
