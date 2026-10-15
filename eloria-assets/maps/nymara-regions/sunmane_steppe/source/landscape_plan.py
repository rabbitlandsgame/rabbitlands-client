"""The Orun working steppe: protected camp, grazing swales and caravan roads.

Positions change; native buildings and livestock handling structures do not
scale. The eastern watch ends inside this region and is never a fourth exit.
"""
import math
import numpy as np

REVISION='sunmane-inhabited-384-v1'
CELLS=384
ORIGIN=(116,116)
BOUNDS=(-116,-268,268,116)
ARRIVAL=(137,95)
SEED=20260911

# Destination of each named outer work site. The central ceremonial camp and
# its market circulation remain at their original, already practical scale.
MOVES={
 'Landmark_sunmane_windmill_00':(58,46),
 'Landmark_sunmane_windmill_01':(79,58),
 'Landmark_sunmane_windmill_02':(-53,-7),
 'Landmark_sunmane_windmill_03':(51,-100),
 'Landmark_sunmane_windmill_04':(-51,-88),
 'Landmark_sunmane_windmill_05':(147,-32),
 'Landmark_sunmane_animal_pen_00':(-64,-63),
 'Landmark_sunmane_animal_pen_01':(85,-52),
 'Landmark_sunmane_animal_pen_02':(77,39),
 'Landmark_sunmane_animal_pen_03':(-36,54),
 'Landmark_sunmane_animal_pen_04':(28,49),
 'Landmark_sunmane_animal_pen_05':(99,-124),
 'Landmark_sunmane_outpost_00':(-63,-139),
 'Landmark_sunmane_outpost_01':(153,-195),
 'Landmark_sunmane_outpost_02':(191,39),
 'Landmark_sunmane_outpost_03':(-79,38),
 'Landmark_sunmane_outpost_04':(140,-88),
 'Landmark_sunmane_outpost_05':(2,-214),
 'Landmark_sunmane_outpost_06':(215,-164),
 'Landmark_sunmane_outpost_07':(221,-51),
 'Landmark_sunmane_cave_wind_caves':(123,-184),
 'Landmark_sunmane_cave_crystal_hollow':(211,-155),
 'Landmark_sunmane_cave_drovers_shelter':(-31,-210),
 'Landmark_sunmane_cave_east_adit':(237,-65),
 'Landmark_sunmane_desert_station_00':(5,-149),
 'Landmark_sunmane_desert_station_01':(159,-176),
 'Landmark_sunmane_filled_well':(-9,40),
 'Landmark_sunmane_landing_00':(-92,46),
}
CAMPS=[((-30,-40),(-39,-82)),((46,-26),(96,-36)),
       ((64,20),(41,54)),((-40,34),(-58,72))]

# Standing posts are authored at the worker's side of the real furniture.
NPC_POSTS={'Orun khan':(120,117),'Kesh':(121,111),'Banner shrine keeper':(83,194),
 'Banner Boy Suvi':(84,193),'Steppe miller':(172,73),'Wind-Cave Listener Esku':(234,290),
 'Amethyst prospector':(323,269),'Whitehorn range warden':(334,271),'Cove landing factor':(26,72)}
NPC_POSTS.update({'West caravan master':(74,111),'East caravan master':(159,112),
                 'Rider Anse':(147,112)})

ROADS={
 'west_caravan':[(0,9.6,0),(-25,9.6,0),(-30,9.5,0),(-42,9.1,0),(-52,8.8,0),(-61,6.3,-.5),(-71.5,4,-.5)],
 'east_caravan':[(0,9.6,0),(25,9.6,0),(48,10.8,0),(79,11.4,-3),(113,12,-13),(145,12.7,-20)],
 'north_barrow':[(0,9.6,0),(11,9.6,-2),(12,9.6,-12),(10,9.6,-21),(0,9.6,-25),(0,9.4,-30),(18,9.4,-34),(22,10,-46),(20,10.8,-62),(12,12,-74)],
 'north_track':[(12,12,-74),(18,13,-110),(29,14,-152),(32,16,-190),(20.5,17,-223.5)],
 'south_shore':[(0,9.6,0),(0,9.6,25),(4,9.3,32),(4,9,40),(4,8.4,58),(18,8,68),(36,8,72),(54.5,8,71.5)],
 'northwest_pasture':[(-30,9.5,0),(-27,9.5,-16),(-31,9.5,-28),(-43,9,-28),(-46,9,-46),(-41,10,-65),(-39,10.5,-77)],
 'saltmane_yards':[(4,9.3,32),(22,9.2,31),(40,9,37),(59,9,36),(72,9,30),(90,10,10),(96,10.7,-23)],
 'southwest_cove':[(0,9.4,30),(-18,8.9,28),(-30,8.2,25),(-42,7.8,25),(-55,7.4,25),(-72,5.5,37),(-88,2,46)],
 'wind_cave_watch':[(32,16,-190),(75,17,-188),(103,18,-185),(123,18,-179)],
 'mineral_caravan':[(29,14,-152),(67,15,-146),(99,16,-155),(148,18,-161),(181,20,-160),(204,20,-152)],
 'frontier_watch':[(113,12,-13),(151,13,-34),(181,14,-49),(209,15,-57),(229,15.5,-62)],
}
TRAILS={
 'west_inn':[(-45,9.1,0),(-45,9.1,8)],
 'east_inn':[(45,10.7,0),(45,10.7,7)],
 'south_inn':[(4,8.6,51),(-3,8.6,51)],
 'north_inn':[(12,12,-74),(20,12,-73),(26,12,-72)],
 'arrival_lane':[(21,9.6,21),(21,9.6,28),(8,9.4,30),(0,9.6,25)],
 'fourth_well':[(4,9.3,32),(-9,8.8,36)],
 'drovers_shelter':[(32,16,-190),(8,15,-202),(-20,14,-206),(-31,14,-205)],
 'lee_camp':[(18,13,-110),(43,13,-115),(70,13,-121),(93,13,-119)],
 'western_watch':[(-39,10.5,-77),(-47,11,-104),(-58,12,-132)],
}
BRIDGES=[('West Ford',(-42,9.1,0),(-30,9.5,0),5.),
         ('Pasture Walk',(-43,9,-28),(-31,9.5,-28),3.8),
         ('Cove Drovers Bridge',(-42,7.8,25),(-55,7.4,25),4.)]
STREAM_CONTROL=[(-19,8.6,-104),(-25,8.3,-83),(-34,8.0,-71),(-46,7.65,-58),
        (-42,7.4,-42),(-38,7.2,-28),(-30,6.8,-16),(-36,6.4,0),
        (-31,6.1,10),(-37,5.9,19),(-49,5.6,25),(-60,4.8,32),
        (-68,3,43),(-81,1.2,51),(-97,-.1,62)]

def smooth_beck(points):
    """Surveyed crossings with smooth bends between stations, sampled each2m."""
    out=[];p=np.asarray(points,float)
    for i in range(len(p)-1):
        a,b,c,d=p[max(0,i-1)],p[i],p[i+1],p[min(len(p)-1,i+2)]
        count=max(3,round(np.linalg.norm((c-b)[[0,2]])/2))
        for j in range(count):
            t=j/count
            q=.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)
            q[1]=b[1]+(c[1]-b[1])*t
            out.append(q.tolist())
    return out+[p[-1].tolist()]
STREAM=smooth_beck(STREAM_CONTROL)
POOLS=[(-19,-104,4.5,8.6),(-65,25,4,5.4),(119,-54,5,8.8),(92,39,4,7.2)]
FIELDS=[(54,48,8,6),(77,54,7,5),(-49,-9,6,5),(47,-96,7,5)]

def tile(x,z):return [round(x+116),round(116-z)]
def smooth(v):v=np.clip(v,0,1);return v*v*(3-2*v)

def relocate_layout(layout):
    old={p.name:(p.x,p.z) for p in layout.placements}
    # Named sites create a local migration field; a post moves with its nearby
    # workplace, never through a global scale factor applied to buildings.
    for p in layout.placements:
        if p.name in MOVES:p.x,p.z=MOVES[p.name]
        if p.name.startswith('Landmark_sunmane_spire_'):
            p.x=176+(p.x-100)*1.4;p.z=-167+(p.z+104)*1.3
        if p.name.startswith('Detail_Amethyst_'):
            p.x=174+(p.x-100)*1.3;p.z=-172+(p.z+104)*1.3
        if p.name.startswith('Detail_DesertCamp_'):
            idx=int(p.name.split('_')[2]);dx,dz=[(0,-72),(49,-15),(76,-44)][idx]
            p.x+=dx;p.z+=dz
        if p.name.startswith('Landmark_orun_round_tent_'):
            idx=int(p.name.rsplit('_',1)[1])//3
            a,b=CAMPS[idx]
            p.x=b[0]+(p.x-a[0])*2.;p.z=b[1]+(p.z-a[1])*2.
            # Native doors face +X; shared right-handed Y rotation turns +X
            # towards -Z. The entrances now face the shared clan yard.
            p.rotation=-math.atan2(b[1]-p.z,b[0]-p.x)
        if p.name.startswith('Camp') or p.name.startswith('Landmark_orun_banner_shrine_'):
            idx=int(p.name[4:6]) if p.name.startswith('Camp') else int(p.name.rsplit('_',1)[1])
            if idx<4:
                a,b=CAMPS[idx];p.x+=b[0]-a[0];p.z+=b[1]-a[1]
    moves=[(old[p.name],(p.x,p.z)) for p in layout.placements if p.landmark
           and p.landmark not in ('secret','transition') and old[p.name]!=(p.x,p.z)]
    return moves

def remap_world(x,z,moves):
    if math.hypot(x,z)<30:return float(x),float(z)
    if not moves:return float(x),float(z)
    a,b=min(moves,key=lambda q:math.dist((x,z),q[0]))
    distance=math.dist((x,z),a)
    weight=1-smooth((distance-12)/24)
    return float(x+(b[0]-a[0])*weight),float(z+(b[1]-a[1])*weight)

def terrain(TER,layout,cell=1.):
    t=TER.Terrain(-122,-274,396,396,cell=cell)
    x,z=t.gx,t.gz
    # Wide quiet swales, a low camp rise and broken eastern mineral benches.
    # Small-scale noise only roughens the broad landform, never makes hills.
    t.height=10.2+2.4*np.sin((x+z*.32)/93)+1.7*np.sin((z-x*.15)/78)
    t.height+=5*smooth((-z-85)/130)+4*smooth((x-125)/120)
    t.height+=.22*np.sin(x*.071+z*.031)+.16*np.cos(z*.085-x*.016)
    shore=-93+6*np.sin(z*.024)+2*np.sin(z*.085)
    t.height=t.height*(smooth((x-shore+12)/28)) -2*(1-smooth((x-shore+12)/28))
    t.surface[:]=TER.MEADOW
    t.surface[x<shore+12]=TER.SHORE
    t.surface[(x>175)&(z<-108)]=TER.BARRENS
    t.surface[(z<-178)&(x<85)]=TER.PATH
    def pad(cx,cz,r,y,shoulder=5):
        d=np.hypot(x-cx,z-cz);w=1-smooth((d-r)/shoulder)
        t.height=t.height*(1-w)+y*w
    pad(0,0,28,9.6,8)
    for p in layout.placements:
        if p.footprint>=2.4 and p.landmark not in ('badland-spire','transition'):
            pad(p.x,p.z,p.footprint+.6,float(t.height_at(p.x,p.z)),6)
    from amberwood import routecraft as RC
    for name,points in {**ROADS,**TRAILS}.items():
        points=np.asarray(points,float)
        RC.grade_road(t,points[:,[0,2]],points[:,1],width=5.5 if name in ROADS else 3.5,
                      shoulder=16,surface=TER.PATH,clearance=1)
    # Yard floors are a final survey after the road earthworks. A nearby road
    # shoulder must not cut through the floor of a tent or water station.
    for p in layout.placements:
        if p.footprint>=2.4 and p.landmark not in ('badland-spire','transition','landing'):
            pad(p.x,p.z,p.footprint+.6,float(t.height_at(p.x,p.z)),8)
    # Cavern portals belong to low eroded outcrops. Their mouths remain open
    # while the native tunnel shell disappears into the ground behind them.
    for p in layout.placements:
        if p.landmark!='cave-entrance':continue
        dx,dz=x-p.x,z-p.z;c,s=math.cos(p.rotation),math.sin(p.rotation)
        across=dx*c-dz*s;front=dx*s+dz*c
        base=float(t.height_at(p.x,p.z))
        mound=6.8*np.exp(-(across/15)**2-((front+14)/20)**2)*smooth((-front-1.)/12.)
        t.height+=mound
    water=np.asarray(STREAM,float);original=t.height.copy()
    distance,along=TER._polyline_distance(x,z,water[:,[0,2]])
    lengths=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(water[:,[0,2]],axis=0),axis=1))]
    water_level=np.interp(along,lengths/lengths[-1],water[:,1])
    # A gently rising earth bank, not a rectangular trench. The land reaches
    # the actual water edge at0.95m, then feathers over a variable9–12m swale.
    width=10.5+1.5*np.sin(along*29.)
    shoulder=smooth((distance-.95)/width)
    bank=water_level+(original-water_level)*shoulder
    bed=water_level-.32*(1-np.minimum(distance/.95,1)**2)
    target=np.where(distance<.95,bed,bank)
    t.height=np.minimum(original,target)
    soil=distance < 1.8+.45*np.sin(along*53)+.2*np.sin(x*.53+z*.27)
    t.surface=np.where(soil,TER.FOREST,t.surface)
    t._write_strength(np.abs(distance-1.8)/t.cell,soil)
    for cx,cz,r,y in POOLS:
        d=np.hypot(x-cx,z-cz);w=1-smooth((d-r*.5)/(r*.8))
        t.height=np.minimum(t.height,t.height*(1-w)+(y-.6)*w)
    # All three real crossings clear the stream and join their approach grade.
    for name,a,b,width in BRIDGES:
        a,b=np.asarray(a,float),np.asarray(b,float)
        direction=(b-a)/np.linalg.norm((b-a)[[0,2]])
        for endpoint,sign in ((a,-1),(b,1)):
            outer=endpoint+direction*4*sign
            RC.grade_road(t,[outer[[0,2]],endpoint[[0,2]]],[outer[1]-.1,endpoint[1]-.1],
                          width=width+1,shoulder=2,surface=TER.PATH,clearance=0)
        dx,dz=b[0]-a[0],b[2]-a[2]
        q=np.clip(((x-a[0])*dx+(z-a[2])*dz)/(dx*dx+dz*dz),0,1)
        distance=np.hypot(x-a[0]-q*dx,z-a[2]-q*dz)
        level=a[1]+q*(b[1]-a[1])
        t.height=np.where(distance<width/2+.2,np.minimum(t.height,level-.25),t.height)
    return t
