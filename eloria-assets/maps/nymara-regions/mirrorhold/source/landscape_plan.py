"""Mirrorhold's inhabited 384 m mountain bowl, authored in ordinary metres.

The survey compresses journeys around a full-size civic core. It does not scale
houses, lamps, entrance buildings or the observatory. The lower working town
is laid out again after compression, with lanes wide enough for two carts.
"""
from copy import deepcopy
import math
import numpy as np
from compact_landscape import Axis, CompactLandscape
from amberwood import terrain as TER, landscape as LAND, noise as N
from amberwood import routecraft as RC, props as P, mesh as M
from regionbuild import Placement
import region as REG
import secret_approaches as SECRET_APPROACHES

SERVER_CELLS=384
SERVER_ORIGIN=(120.0,96.0)
PLAY_MIN_X,PLAY_MAX_X=-120.0,263.0
PLAY_MIN_Z,PLAY_MAX_Z=-287.0,96.0
PLAN=CompactLandscape(Axis(-174,402,-120,264,(75,240)),
                      Axis(-402,174,-288,96,(-282,-68)),
                      REG.SERVER_ORIGIN,SERVER_ORIGIN)
REVISION='inhabited-384-v1'

# x, y, z surveys, including the public mountain roads. Civic stone belongs
# around the formal courts; the quarry and mountain roads are worn gravel.
ROADS={
 'arrival-lane':([(-53,17,-5),(-47,17,4),(-27.28,17,14.29),(0,24,1),
                   (15,32,-16),(28,40,-29),(44,48,-21),(58,58,-25.65)],7),
 'civic-ascent':([(82,58,-25.65),(101,58,-39),(116,70,-70),(102,80,-90),
                  (93.68,84,-92)],7),
 'citadel-service-road':([(116,70,-70),(137,83,-92),(142,98,-122),
                          (143,104,-162),(135,112,-195),(74.68,112,-198)],6),
 'lens-vault-lane':([(74.68,112,-198),(74.68,112,-201.65)],5),
 'orrery-pilgrim-road':([(74.68,112,-198),(67,117,-218),(82,124,-234),
                         (100,124,-234)],5),
 'whitehorn-approach':([(-76.5,85,-282.5),(-75,85,-245),(-58,83,-217),
                        (-40,75,-186),(-42,60,-142),(-56,40,-96),(-48,30,-45)],7),
 'barrens-approach':([(10.5,93,-282.5),(11,93,-263),(11,100,-246),
                      (40,115,-230),(67,117,-218)],7),
 'high-cross-road':([(-58,83,-217),(-21,91,-234),(11,100,-246)],6),
 'amber-gorge-road':([(-111.5,24,20.5),(-85,24,20),(-67,20,10),
                       (-47,17,4),(-27.28,17,14.29)],7),
 'quay-descent':([(-27.28,17,14.29),(-20,15,23),(0,12,20),(27,8,17),(54,5,13),
                   (83,3.52,6.77),(105,4.5,4),(120,4.5,5.83)],7),
 'east-working-road':([(120,4.5,5.83),(148,4.5,5.83),(153,4.5,12),
                        (158.5,7,12),(179,19,1),
                        (195,31,-13),(194,42,-39.65),(203,58,-68),
                        (182,72,-95),(162,85,-110),(142,98,-122)],6),
 'quarry-road':([(182,72,-95),(198,82,-106),(191,90,-125.65)],6),
 'lens-yard-lane':([(101,58,-39),(125,58,-42),(143,58,-41)],5),
 'cistern-yard-lane':([(28,40,-29),(45,31,-4),(49,31,-3)],4),
 'rose-gallery-lane':([(142,98,-122),(113,98,-120),(80,98,-121),
                       (40,98,-123),(40,98,-98)],4),
 'western-lens-lane':([(40,98,-123),(40,101,-147),(39.7,104,-165)],4),
 'east-stair-yard':([(195,31,-13),(179,31,-18)],4),
 'overlook-lane':([(116,70,-70),(139,66,-62),(161.7,64,-64)],4),
 'south-watch-lane':([(57.68,6,88.48),(66,11,82)],4),
 'reed-cut-lane':([(31,8,24),(31,8,30)],3),
 'quarry-adit-lane':([(198,82,-106),(211,82,-112)],4),
 'icebore-lane':([(40,98,-123),(31,87,-135)],4),
 'canal-sluice-lane':([(28,40,-29),(21.7,46,-43)],4),
 'sanctuary-causeway-approach':([(158.5,7,12),(167,4.5,23),
                                (175.5,4,39),(175.5,3.96,50.5)],7),
}
TOWN_ROWS=[(-48,30),(-31,23.5),(-14,17)]
SECRET_POSTS={
 'mirror-reed-cut':(31,8,30),'mirror-lens-garden':(143,58,-38),
 'mirror-orrery-vault':(115,124,-230),'mirror-stair-pit':(191,39.33,-33),
 'mirror-rose-school':(40,98,-98),'mirror-basin-spring':(80,84,-88),
 'mirror-watch-butts':(66,11,82),'mirror-citadel-reliquary':(138,98,-127),
 'mirror-cistern-well':(49.25,6.08,8.75),'mirror-lens-focus':(39.7,104,-165),
 'mirror-adit':(211,82,-112),'mirror-waystone':(55.7,58,-25.65),
 'mirror-overlook-eyrie':(161.7,64,-64),'mirror-icebore-mouth':(35,94.05,-126),
}
SECRET_POSTS.update(SECRET_APPROACHES.POSTS)
INTERACTION_POSTS={
 'orrery-console':(99.7,124,-234),'gate-ward':(110,84,-87),
 'plaza-well':(69.7,58,-27),'harbour-crane':(135.7,4.5,7),
 'ring-dial':(93.7,3.7,61),'canal-sluice':(10.25,28.06,-39.75),
 'aqueduct-valve':(190,42,-35),'town-forge':(-47,17,-7),
}


def prepare(t,seed):
    """Quiet grazing benches and spruce in sheltered drainage pockets."""
    open_ground=np.zeros_like(t.height)
    for x,z,rx,rz in [(-75,-70,50,48),(58,8,34,22),(305,-22,30,46)]:
        d=np.hypot((t.gx-x)/rx,(t.gz-z)/rz)
        open_ground=np.maximum(open_ground,1-LAND.smoothstep(.55,1.25,d))
    density,_,_=LAND.grove_density(t,list(REG.ROUTES.values()),
                                  list(REG.WATERCOURSES.values()),seed,
                                  open_ground=open_ground)
    t.mirror_groves=density*(1-LAND.smoothstep(84,125,t.height))
    t.tree_block |= open_ground>.85


def _road(t,stations,width,surface=TER.PATH,shoulder=10):
    a=np.asarray(stations,float)
    RC.grade_road(t,a[:,[0,2]],a[:,1],width=width,shoulder=shoulder,
                  surface=surface,clearance=5)


def _bridge_bank(t,outer,bank,width):
    """A linear landing plane, feathered beyond its surveyed endpoints.

    A road helper's round, constant-height end cap makes a steep lip where
    this short ramp meets an already sloping street. Continue the bank plane
    through the blend instead, so the street joins it without a little dam.
    """
    delta=bank[[0,2]]-outer[[0,2]];length=float(np.linalg.norm(delta))
    direction=delta/length
    along=(t.gx-outer[0])*direction[0]+(t.gz-outer[2])*direction[1]
    across=np.abs((t.gx-outer[0])*direction[1]-(t.gz-outer[2])*direction[0])
    signed=np.maximum.reduce([across-width/2,-along,along-length])
    edge=np.clip(signed/6,0,1);blend=1-edge*edge*(3-2*edge)
    target=outer[1]+along/length*(bank[1]-outer[1])
    t.height=t.height*(1-blend)+target*blend
    t.surface[signed<.6]=TER.PAVING;t.tree_block|=signed<5


def _patch(t,x,z,w,d,y,surface=TER.PAVING,shoulder=6):
    signed=np.maximum(abs(t.gx-x)-w/2,abs(t.gz-z)-d/2)
    LAND.feather_level(t,signed,y,shoulder=shoulder)
    inside=signed<=0
    t.surface[inside]=surface;t.tree_block|=signed<4


def _seat(build,p,x,z,y=None,yaw=None):
    p.position=(x,float(build.terrain.height_at(x,z)) if y is None else y,z)
    if yaw is not None:p.rotation_y=yaw
    p.scale=1.0


def _waterworks(build,seed):
    """Meltwater always falls to the lake; carts cross on surveyed masonry."""
    t=build.terrain
    streams={
      'upper_cascade':[(1.5,70,-99.65),(7.9,51,-69.65),(14.3,40,-45.65),(27.7,19,-9.65)],
      'canal_west':[(27.7,19,-9.65),(14.3,12,5.83),(7.9,6,22.7),(27.7,.12,36.8)],
      'canal_east':[(206.45,42,-39.65),(199,27,-22),(177.68,9,8.65),(153.68,.12,28.37)],
    }
    for points in streams.values():
        a=np.asarray(points,float)
        RC.grade_road(t,a[:,[0,2]],a[:,1]-.48,width=2.8,shoulder=3.8,
                      surface=TER.SHORE,clearance=3)
    # The lake is clipped against the finished basin, including town banks.
    build.water_meshes={k:v for k,v in build.water_meshes.items()
                        if k not in ('Water_Canal','Water_Lake')}
    lake=TER.water_plane(t,0,t.x0,t.z0,t.xs[-1],t.zs[-1],
                         material='water_lake',cell=2,margin=.15)
    if lake.triangle_count:build.water_meshes['Water_Lake']=lake
    from populate import _ribbon
    quads=[]
    for points in streams.values():
        for a,b in zip(points,points[1:]):
            a,b=np.asarray(a),np.asarray(b)
            quads.append(_ribbon(a[[0,2]],b[[0,2]],float(a[1]),float(b[1]),2.2))
    build.water_meshes['Water_Canal']=M.merge(quads,material='water_stream')
    build.authored_streams=[{'id':name,'waypoints':points} for name,points in streams.items()]
    build.water_crossings=[];seen=[]
    roads=[(name,np.asarray(stations,float),width) for name,(stations,width) in ROADS.items()]
    for road,stations,width in roads:
        for a,b in zip(stations,stations[1:]):
            direction=b[[0,2]]-a[[0,2]];length=float(np.linalg.norm(direction))
            for stream,points in streams.items():
                for c,d in zip(np.asarray(points,float),np.asarray(points,float)[1:]):
                    water=d[[0,2]]-c[[0,2]]
                    matrix=np.column_stack([direction,-water])
                    if abs(np.linalg.det(matrix))<.0001:continue
                    along,across=np.linalg.solve(matrix,c[[0,2]]-a[[0,2]])
                    if not (0<=along<=1 and 0<=across<=1):continue
                    centre=a+(b-a)*along
                    if any(np.linalg.norm(centre[[0,2]]-p)<8 for p in seen):continue
                    seen.append(centre[[0,2]])
                    start=a+(b-a)*(along-8/length);end=a+(b-a)*(along+8/length)
                    # A deck clears water; shallow reaches receive a modest
                    # raised approach, following the existing street grade.
                    wy=float(c[1]+(d[1]-c[1])*across)
                    lift=max(0,wy+.8-min(start[1],end[1]))
                    start[1]+=lift;end[1]+=lift
                    for bank,sign in ((start,-1),(end,1)):
                        outer=bank.copy();outer[[0,2]]+=direction/length*sign*5
                        # The water cut has already lowered nearby terrain.
                        # Banks meet the surveyed street, not that excavated
                        # channel floor, including when the street bends.
                        _,road_along=TER._polyline_distance(
                            np.array([outer[0]]),np.array([outer[2]]),stations[:,[0,2]])
                        road_lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(stations[:,[0,2]],axis=0),axis=1))]
                        outer[1]=float(np.interp(road_along[0],road_lengths/road_lengths[-1],stations[:,1]))
                        _bridge_bank(t,outer,bank,width)
                    key=f'MeltwaterBridge_{len(seen)}'
                    group=RC.graded_causeway([start,end],width=width,thickness=.35,
                       parapet=.65,foot=min(wy-3,start[1]-3),stone='pale_ashlar',paving='cobble_paving')
                    build.add_mesh(key,group)
                    build.place(Placement('Landmark_'+key,key,(0,0,0),collides=False,kind='landmark'))
                    build.water_crossings.append({'id':key,'endpoints':RC.crossing_endpoints([start,end])})
    build.notes.append(f'Meltwater: three descending catchments; {len(seen)} surveyed cart bridges.')


def _excavate_bridge_beds(build,only=None,shoulder=3.0):
    """Keep the cart decks above their beds after nearby yards are graded.

    Bridge sides retain the stream cut; longitudinal banks meet the surveyed
    deck plane. This removes earth overtopping a bridge instead of pretending
    that its buried floor remains a usable walking surface.
    """
    t=build.terrain
    for p in build.placements:
        if only is not None and p.node not in only:continue
        if not (p.node.startswith('Landmark_MeltwaterBridge_')
                or p.node=='Landmark_LakeLink_Sanctuary'):continue
        for part in build.meshes[p.mesh].walk_parts:
            matrix=M.translation(*p.position)@M.rotation_y(p.rotation_y)@M.scaling(p.scale)
            points=part.transformed(matrix).positions
            start=(points[0]+points[3])/2;end=(points[1]+points[2])/2
            delta=end[[0,2]]-start[[0,2]];length=float(np.linalg.norm(delta))
            direction=delta/length
            along=(t.gx-start[0])*direction[0]+(t.gz-start[2])*direction[1]
            across=np.abs((t.gx-start[0])*direction[1]-(t.gz-start[2])*direction[0])
            half_width=float(np.linalg.norm(points[0,[0,2]]-points[3,[0,2]]))/2
            signed=np.maximum.reduce([across-half_width-.75,-along,along-length])
            edge=np.clip(signed/shoulder,0,1);blend=1-edge*edge*(3-2*edge)
            inset=np.clip(np.minimum(along,length-along)/2,0,1)
            target=start[1]+along/length*(end[1]-start[1])-.04-.36*inset
            t.height-=np.maximum(t.height-target,0)*blend


def compact(build,seed,materials,lod=None):
    old=build.terrain
    # Shared bank survey transforms full structural/walking bridge groups.
    for p in build.placements:
        if p.node.startswith('Landmark_LakeLink_'):p.walk_surface=True
    build.authored_roads=PLAN.metadata([r for r in REG.access_waypoints(old)
                                       if r['id'].startswith('lake-') or r['id']=='sanctuary-approach'])
    build.authored_streams=PLAN.metadata([{'id':name,'waypoints':[
        [float(x),float(old.height_at(x,z))+.34,float(z)] for x,z in points]}
        for name,points in REG.STREAMS.items()])
    PLAN.apply(build)
    t=build.terrain

    # A broad inhabited shoulder replaces the old stack of abrupt arrival
    # cliffs. Its natural granite/turf banks climb north toward the cirques.
    signed=np.maximum.reduce([(-103-t.gx),(t.gx-2),(-96-t.gz),(t.gz-36)])
    target=17+.25*np.maximum(-t.gz-12,0)+.18*np.clip(t.gx+27,0,45)+1.3*(N.fbm(t.gx/30,t.gz/30,seed=seed+913)-.5)
    LAND.feather_level(t,signed,target,shoulder=29)
    natural=signed<15
    t.surface[natural]=TER.TURF

    # Practical streets in the lower town. Full-size houses front three
    # connected terrace lanes, with a little private ground at their backs.
    for z,y in TOWN_ROWS:
        _patch(t,-47,z,67,15,y)
    for name,(stations,width) in ROADS.items():
        _road(t,stations,width,TER.PAVING if name in
              ('arrival-lane','civic-ascent','citadel-service-road','lens-vault-lane')
              else TER.PATH,shoulder=12 if 'approach' in name else 8)
    for z,y in TOWN_ROWS:
        _road(t,[(-80,y,z+6),(-20,y,z+6)],6,TER.PAVING,3)
    _road(t,[(-20,17,-8),(-14,20,-17),(-20,23.5,-25),(-14,27,-34),(-20,30,-42)],5,TER.PAVING,4)
    _road(t,[(-53.39,17,-5.66),(-53,17,-5),(-47,17,4)],5,TER.PAVING,3)
    # The fountain court, services and cistern threshold remain full-size.
    _patch(t,69.68,-25.65,34,10,58,TER.MARBLE)
    _patch(t,88.68,-31.65,9,10,58,TER.MARBLE)
    # A usable cargo aisle on the original North Quay.
    _patch(t,135.68,5.83,43,9,4.26)
    # Grinding benches, the cistern works and the quarry are workplaces with
    # their own fronts, not isolated decorative wall fragments on a slope.
    yards={'lens-works':(135,-46,58),'cistern-yard':(45,-6,31),'quarry-shelf':(201,-110,82)}
    for name,(x,z,y) in yards.items():
        _patch(t,x,z,30,18,y)
        p=next((p for p in build.placements if p.node=='Landmark_'+name),None)
        if p:_seat(build,p,x,z-8,y-3.6,0)
        for l in build.landmarks:
            if l['id']==name:l['position']=[x,y,z]
    for x,y,z in SECRET_POSTS.values():_patch(t,x,z,4,4,y,TER.PATH)
    for x,y,z in SECRET_APPROACHES.RETAINED_FOUNDATION_POSTS:
        _patch(t,x,z,4,4,y,TER.PATH)
    # Full-size Ring colonnade needs its complete island after compression.
    ring=PLAN.point([156,3.5,60]);r=np.hypot(t.gx-ring[0],t.gz-ring[2])
    LAND.feather_level(t,r-23.2,3.5,shoulder=1.5)
    t.surface[r<23.2]=TER.MARBLE;t.tree_block|=r<28

    # Replace the compressed house grid; full-sized façades now face a lane.
    town=[p for p in build.placements if p.node.startswith('Building_CliffHouse_')]
    removed={p.node for p in town[15:]}
    # These unlabelled legacy fragments lost their physical roles when this
    # working shore was graded: the low pier is buried below the cart road,
    # and the old uninterrupted retaining wall crosses its bridge and a home.
    removed.update({'Landmark_Dock_2','Landmark_Retaining_2','Prop_OverlookRail_2'})
    for i,p in enumerate(town[:15]):
        z,y=TOWN_ROWS[i//5];x=-74+(i%5)*13
        _seat(build,p,x,z,y-.18,0)
    # Satellite homes become short rows along their connected yards. The
    # landmark IDs remain, while fewer homes leave room for carts and stores.
    satellite={
      'west-bench':(-79,-101,41), 'lower-terrace':(-4,32,13),
      'mid-bench':(-10,-58,35), 'east-bench':(183,-2,22),
      'lake-north':(31,20,8), 'lake-east':(209,48,14),
      'south-shore':(18,78,12), 'west-shore':(-12,50,14),
    }
    for site,(x,z,y) in satellite.items():
        _patch(t,x,z,31,21,y,TER.TURF,shoulder=12)
        _road(t,[(x-14,y,z+4),(x+14,y,z+4)],5,TER.PATH,4)
        for slot in range(4):
            p=next((p for p in build.placements if p.node==f'Building_{site}_{slot}'),None)
            if not p:continue
            if slot>1:removed.add(p.node);continue
            _seat(build,p,x+(slot-.5)*15,z-4,y-.18,0)
        for l in build.landmarks:
            if l['id']==site:l['position']=[x,y,z]
    # The eastern cart bridge crosses the old second house plot. Its owners
    # now front the nearby stair-yard terrace, with a separate level home lot
    # and a short footpath to that existing working court.
    east_home=next((p for p in build.placements if p.node=='Building_east-bench_1'),None)
    if east_home:
        _patch(t,175.5,-27,11,12,31,TER.TURF,shoulder=7)
        _seat(build,east_home,175.5,-27,30.82,0)
    # Connect every inhabited yard to an existing road, staying outside the
    # private house row. Survey station heights keep ramps intelligible.
    yard_links={
      'west-bench': [(-79,41,-97),(-68,40,-96),(-56,40,-96)],
      'lower-terrace':[(-4,13,36),(-15,14,27),(-27.28,17,14.29)],
      'mid-bench':[(-10,35,-54),(-3,33,-38),(15,32,-16)],
      'east-bench':[(175.5,22,-2),(179,19,1)],
      'east-stair-home':[(175.5,31,-21),(179,31,-18)],
      'lake-north':[(31,8,24),(27,8,17)],
      'lake-east':[(209,14,52),(227,14,32),(218,19,4),(195,31,-13)],
      'west-shore':[(-12,14,54),(-28,14,37),(-27.28,17,14.29)],
      'south-shore':[(18,12,82),(27,12,76),(39,11,73),(55,8,76),(57.68,6,88.48)],
    }
    for name,stations in yard_links.items():
        _road(t,stations,4,TER.PATH,7)
        build.authored_roads.append({'id':name+'-yard-link','width':4,'waypoints':stations})
    # Reapply shared streets where a yard's soft bank could cover their bed.
    for key in ('arrival-lane','quay-descent','amber-gorge-road','east-working-road'):
        stations,width=ROADS[key];_road(t,stations,width,TER.PATH,14 if key in ('arrival-lane','quay-descent') else 8)

    _waterworks(build,seed)
    # The first stream bridge approaches on a diagonal, then the civic road
    # turns east. Its straight bank apron must not flatten that turning rise
    # into a steep lip. Restore the seven-metre cart ramp beyond the deck.
    civic_exit=[(28,40.12,-29),(35,43.5,-25.5),(44,48,-21),(58,58,-25.65)]
    _road(t,civic_exit,7,TER.PAVING,6)
    build.authored_roads.append({'id':'civic-bridge-exit','width':7,'waypoints':civic_exit})
    _excavate_bridge_beds(build)

    # The Sanctuary bridge branches beside the rising quarry road. Its bank
    # feather had cut a 2m hollow into that older carriageway, followed by a
    # steep lip. Restore the surveyed ascending plane after those earthworks;
    # an extrapolated plane avoids a flat end cap on the continuing climb.
    _bridge_bank(t,np.array([158.5,7,12]),np.array([179,19,1]),6)
    # Keep the whole branching bridge exposed. Its final narrow bed cut stops
    # before the ascending carriageway instead of feathering a hollow into it.
    _excavate_bridge_beds(build,only={'Landmark_MeltwaterBridge_5'},shoulder=1)
    # The watch hatch is beside the bent lake bridge, on its low bank. Give
    # both the standing point and the short watch approach actual level ground
    # instead of relying on the former server-side opening of the bridge rim.
    watch_front=[(58,6,88),(62,5.4,85),(65.5,5.4,82.5)]
    _road(t,watch_front,3,TER.PATH,2)
    _patch(t,65.5,82.5,4,4,5.4,TER.PATH,shoulder=2)
    build.authored_roads.append({'id':'watch-hatch-approach','width':3,'waypoints':watch_front})

    # Decorative random falls did not have catchments. Keep the canal works
    # and upper meltwater cascade; their surveyed water remains visible.
    removed|={p.node for p in build.placements if p.node.startswith('Landmark_CliffFall_')}
    removed|={p.node for p in build.placements if p.node.startswith('March_')
              and (p.node.endswith('_Stone') or '_Furniture_' in p.node)}
    # Compression moved these decorative crystals into the outer Glasswarden
    # arrival lane. The full seven-metre road stays clear at the shared col.
    removed.update({'March_east_road_shard_010','March_east_road_shard_011'})
    # Cargo is stacked along the back of the quay, with a clear ferry aisle.
    for i,p in enumerate(p for p in build.placements if p.node.startswith('Prop_HarbourGoods_')):
        _seat(build,p,116.5+(i//2)*5.3,2.3+(i%2)*1.0,4.52,.05*(i%3))
    # Working objects have a reason to stand in these yards.
    for i,(x,z) in enumerate([(-80,-9),(-67,-9),(-54,-9),(-41,-9),(-28,-9),
                               (-80,-26),(-67,-26),(125,-44),(130,-44),(141,-44)]):
        key=f'Prop_WorkingStores_{i}'
        build.add_mesh(key,P.barrel(seed=seed+800+i) if i%3 else P.crate(seed=seed+800+i))
        build.place(Placement(key,key,(x,float(t.height_at(x,z)),z),.11*(i%3),collides=True))
    # Restore tree/crown spacing after travel compression. Retained stands
    # occupy moist lee ground; streets, entrances and lake margins are open.
    lines=[np.asarray(v[0])[:,[0,2]] for v in ROADS.values()]
    lines += [np.array([[-80,z+6],[-20,z+6]]) for z,_ in TOWN_ROWS]
    keep=[];crowns=[];removed_trees=set()
    for p in build.placements:
        if p.node in removed:continue
        x,y,z=p.position
        if p.kind in ('tree','foliage','rock'):
            d=min(float(TER._polyline_distance(np.array([x]),np.array([z]),line)[0][0]) for line in lines)
            if d<(7 if p.kind in ('tree','foliage') else 2.8):continue
            if (-88<x<1 and -60<z<12) or math.hypot(x-ring[0],z-ring[2])<29:continue
            if p.kind=='tree':
                if any(math.hypot(x-a,z-b)<7.2 for a,b in crowns):
                    removed_trees.add(p.node.replace('_Wood',''));continue
                crowns.append((x,z))
            if p.kind=='foliage' and p.node.replace('_Canopy','') in removed_trees:continue
            _seat(build,p,x,z,float(t.height_at(x,z))-.12)
        keep.append(p)
    build.placements[:]=keep
    for l in build.landmarks:
        if l.get('node') in removed and l.get('node','').endswith('_Stone'):
            l['node']=l['node'].replace('_Stone','_Signpost')
    for entry in build.spawns:
        x,_,z=entry['position'];entry['position'][1]=round(float(t.height_at(x,z))+.05,2)
    for p in build.portals:
        if p['id']=='stair-cellars-door':
            p['position']=[-53.3869,17.1,-5.6602]
            p['serverTile']=[67,102]
        if p['id'] in ('north-pass','east-road','west-gorge'):
            x,_,z=p['position'];p['position'][1]=round(float(t.height_at(x,z))+.1,2)
    # Foundations of civic monuments stay surveyed; everyday freestanding
    # props follow the re-authored terrain instead of hovering over it.
    for p in build.placements:
        if p.node.startswith(('Prop_RoadLamp_','Prop_Signpost_','Walk_Landmark_EastStair')):
            x,_,z=p.position;_seat(build,p,x,z)
    # Re-seat everyday features affected by the new shoulder, including the
    # quarry's ringing blank and testing bell. Their stories and IDs persist.
    ordinary_prefix=('Landmark_far-','Landmark_gorge','Landmark_west-','Landmark_north-',
                     'Landmark_Lore_','Lore_','March_')
    for p in build.placements:
        if p.node.startswith(ordinary_prefix):
            x,_,z=p.position;_seat(build,p,x,z)
    for l in build.landmarks:
        if l['id']=='cliff-town':l['position']=[-47,23.5,-25]
        if l['id'] in ('far-west','west-shrine','north-post','gorge-head','lower-terrace','ringing-quarry') or l['id'].startswith(('station-','march-')):
            x,_,z=l['position'];l['position'][1]=round(float(t.height_at(x,z)),2)
        if l['id']=='east-stair':
            p=next((p for p in build.placements if p.node.startswith('Walk_Landmark_EastStair')),None)
            if p:l['position']=list(p.position)
    for entry in build.interactives:
        if entry.get('kind')=='secret':
            x,y,z=SECRET_POSTS[entry['secret']]
            if entry['secret']=='mirror-watch-butts':y=float(t.height_at(x,z))
            entry['position']=[x,y,z]
            entry['serverTile']=[round(x+SERVER_ORIGIN[0]),round(SERVER_ORIGIN[1]-z)]
            node='Secret_'+entry['secret'].replace('-','_')
            prop=next((p for p in build.placements if p.node==node),None)
            # A grate, slab or loose stone lies within reach of the standing
            # point. The approach tile is clear of the entrance's solid prop.
            if prop:
                _seat(build,prop,x,z-1.8,float(t.height_at(x,z-1.8))-.05)
                prop.collides=False
        elif entry['id'] in INTERACTION_POSTS:
            x,y,z=INTERACTION_POSTS[entry['id']]
            entry['position']=[x,round(float(t.height_at(x,z)),2),z]
            entry['serverTile']=[round(x+SERVER_ORIGIN[0]),round(SERVER_ORIGIN[1]-z)]
    # Stone paving ends at a retaining lip; it is not stretched down earthen
    # cliff faces. Bare granite and alpine turf follow the actual grade.
    gz,gx=np.gradient(t.height,t.cell);slope=np.hypot(gx,gz)
    formerly_built=np.isin(t.surface,[TER.PAVING,TER.MARBLE,TER.PATH])
    t.surface[formerly_built & (slope>.55)]=TER.ROCK
    t.surface[(signed<15)&(slope>.48)&(t.surface==TER.TURF)]=TER.ROCK
    # The arrival track wears into the broad slope with a wandering verge.
    # Its physical cart bed stays wide; paving coverage has a softer outline.
    stations,width=ROADS['arrival-lane'];points=np.asarray(stations)[:,[0,2]]
    distance=LAND.distance_field(t,[points])
    verge=(distance<width/2+2)&(t.surface==TER.PATH)&(slope<.5)
    t.surface[verge]=TER.TURF
    LAND.worn_path(t,points,5.8,seed+981,surface=TER.PATH)
    t.water_depth=np.clip(REG.LAKE_LEVEL-t.height,0,None)
    build.authored_roads += [{'id':name,'width':width,'waypoints':stations}
                             for name,(stations,width) in ROADS.items()]
    build.authored_roads += [{'id':f'stair-town-{i}','width':6,
                              'waypoints':[[-80,y,z+6],[-20,y,z+6]]}
                             for i,(z,y) in enumerate(TOWN_ROWS)]
    build.notes.append('384 m inhabited survey: full-size civic core; three connected Stair Town streets; eight working yards; surveyed northern cols.')
    # Four Gates leaves from the open southeast lake shore. The old west-bank
    # spur remains useful for the watch and hidden butts, while the Ring island
    # keeps its whole foundation outside the new causeway channel.
    station_posts={'March_south_road_Station':(164,4.5,35),
                   'March_south_road_Signpost':(179.8,4.0,40)}
    _patch(t,164,35,12,10,4.5,TER.PATH,shoulder=4)
    _road(t,[(164,4.5,38),(173,4.05,39)],4,TER.PATH,2)
    for p in build.placements:
        if p.node in station_posts:
            x,y,z=station_posts[p.node];_seat(build,p,x,z,y)
    for entry in build.landmarks:
        if entry.get('node') in station_posts:
            x,y,z=station_posts[entry['node']];entry['position']=[x,y,z]
            entry['note']='The working quay road reaches the island causeway; the old shore spur serves the South Watch.'
    # Recut the water after the approach and station foundations are final.
    build.water_meshes['Water_Lake']=TER.water_plane(t,REG.LAKE_LEVEL,
        t.x0,t.z0,t.xs[-1],t.zs[-1],material='water_lake',cell=2,margin=.15)
    build.notes.append('Sanctuary Road: a seven-metre causeway from the southeast working shore; South Watch and Ring island retain their sheltered banks.')
    import lens_vault_approach
    lens_vault_approach.prepare(build)
    SECRET_APPROACHES.prepare(build)
    # Continuous one-metre substrate reflects the final grades, not the old
    # compressed surface triangles. Water and bridge surveys are retained.
    from amberwood import materials as MAT
    build.terrain_meshes={k:v for k,v in build.terrain_meshes.items() if not k.startswith('Terrain_')}
    mesh_terrain=t
    if lod is not None:
        # Sample the finished native ground once at far spacing. Shared road
        # collars are applied below, so their deck geometry and exact seam
        # partitions survive in both packages.
        mesh_terrain=TER.Terrain(t.x0,t.z0,t.size_x,t.size_z,cell=2)
        mesh_terrain.height=t.height_at(mesh_terrain.gx,mesh_terrain.gz)
        mesh_terrain.surface=t.surface_at(mesh_terrain.gx,mesh_terrain.gz)
        ix=np.clip(np.rint((mesh_terrain.gx-t.x0)/t.cell).astype(int),0,t.cols-1)
        iz=np.clip(np.rint((mesh_terrain.gz-t.z0)/t.cell).astype(int),0,t.rows-1)
        mesh_terrain.surface_strength=t.surface_strength[iz,ix]
    build.terrain_meshes.update(mesh_terrain.build_meshes(uv_scale=.28,materials=materials,
                              blend_edges=True,material_suffix=MAT.GROUND_SUFFIX))
    used={p.mesh for p in build.placements}
    build.meshes={k:v for k,v in build.meshes.items() if k in used}
    import streaming_borders as SB
    SB.apply(build,"mirrorhold")
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_northern'))
    import landscape_finish
    landscape_finish.apply(build, 'mirrorhold')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_finishing'))
    import connector_finish
    import sanctuary_crossing
    sanctuary_crossing.apply(build)
    connector_finish.apply(build, 'mirrorhold')
    lens_vault_approach.finish(build)
    SECRET_APPROACHES.finish(build)
    for entry in build.portals:
        if "serverTile" not in entry:
            x,_,z=entry["position"]
            entry["serverTile"]=[math.floor(x+SERVER_ORIGIN[0]),math.floor(SERVER_ORIGIN[1]-z)]


def manifest(build,manifest):
    """Publish the compact frame and all route/service contracts together."""
    t=build.terrain
    manifest['landscapeRevision']=REVISION
    manifest['roads']=build.authored_roads
    manifest['lensVaultApproach']=build.lens_vault_approach
    SECRET_APPROACHES.manifest(build,manifest)
    manifest['contentLayout']=PLAN.metadata(deepcopy(REG.CONTENT_LAYOUT))
    # Explicit compact-frame posts beside the original work areas. The final
    # server mask reserves these before resources and services are placed.
    manifest['contentLayout']['npcs']={
        # The Citadel/Orrery staff receive visitors on the two flanks of the
        # connected Lens Vault court. Their inherited high-bank posts became
        # disconnected; moving the staff preserves their workplaces without
        # stretching the terrain or placing them on a bare slope below it.
        'Lens-Master Corvine Ast':[70,91,-193],
        'Orrery Keeper Sabel Roon':[64,91,-193],
        'Canal Factor Odile Wren':[13,35.8,-39],
        'Stair-Town Reeve Padric':[-43,17.0,-14],
        'Aqueduct Warden Sunna':[203,50.41,-54],
        'Quay Master Belen Tarr':[156,35.28,-9],
        # Public paving in front of the west-bench house, clear of the watch
        # footing and fence. The former side post became an isolated floor.
        'Bench Steward Aurel Fane':[-76,17,-7],
    }
    manifest['navigation']['crossings']=PLAN.metadata(manifest['navigation']['crossings'])
    manifest['navigation']['crossings']+=build.water_crossings
    manifest['water']['streams']=build.authored_streams
    manifest['coordinateTransform']['walkingHeight']=build.spawns[0]['position'][1]-.05
    manifest['streamingBorders']=build.streaming_borders
    manifest['bounds']['terrain']={'min':[t.x0,float(t.height.min()),t.z0],
                                    'max':[t.xs[-1],float(t.height.max()),t.zs[-1]]}
    manifest['environment']['presentation']={
       'chimneySmoke':{'enabled':True,'nodes':['Building_CliffHouse_2','Building_CliffHouse_7']},
       'waterSpray':{'enabled':True,'nodes':['Landmark_Fall_0','Landmark_Fall_1']},
       'ambientAudio':[{'id':'settlement','zone':'stair-town'},
                       {'id':'wind-barren','zone':'northern-cols'}]}
    manifest['environment']['zones']=[{'id':'stair-town','centre':[-48,24,-26],'radius':40},
        {'id':'northern-cols','centre':[-30,90,-265],'radius':62}]
    return manifest
