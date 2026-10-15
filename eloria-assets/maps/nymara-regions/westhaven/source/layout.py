"""Inhabited harbour, practical circulation and exposed shore crossings.

Terrain is prepared before buildings. Public grades are applied after plot
foundations; only short recessed beds sit beneath exposed bridge skins.
"""
import math
import numpy as np
from amberwood import routecraft as RC, terrain as TER, props as P
from amberwood import mesh as M
import region as REG
import havenarch as HA
import havenkit as HK

WAREHOUSES=[('00',-79,-50,8.4),('04',25,-17,3.4),('08',47,-18,3.4),('12',92,-44,8.4),('16',117,-13,3.4)]

HOUSE_ROWS = [
    ([-65,-47,-29,85,104],-43,8.4,'lower'),
    ([-65,-46,93],-77,14,'middle'),
    ([-63,-45,-28,101,119],-108,21,'upper'),
    ([-63,-46],-135,28,'bell'),
    ([12],-125,28,'scribe'),
    ([-42,-25,17,33,85],-151,36,'crown'),
    ([-61,-43,-25,-7,11],-189,36,'ridge'),
]
HOUSE_PLOTS=[(f'{row}_{i}',x,z,y,i%6) for xs,z,y,row in HOUSE_ROWS for i,x in enumerate(xs)]
YARD_LANES = [
    ([(-68,-125),(-42,-125),(-28,-114)],[28,28,25]),
    ([(12,-115),(-6,-118),(-28,-114)],[28,27,25]),
    ([(-70,-33),(-29,-33),(11,-34)],[8.4]*3),
    ([(79,-33),(111,-33),(111,-26)],[8.4,8.4,13]),
    ([(-70,-67),(-29,-67),(25,-60)],[14]*3),
    ([(93,-67),(98,-67),(106,-55)],[14]*3),
    ([(-69,-98),(-28,-98),(-7,-90)],[21]*3),
    ([(95,-98),(125,-98),(143,-103)],[21,21,31]),
    ([(-48,-141),(-23,-141),(-25,-162),(42,-168)],[36]*4),
    ([(12,-141),(37,-141),(42,-168)],[36]*3),
    ([(85,-141),(85,-156),(105,-155)],[36,36,34]),
    ([(-68,-179),(18,-179),(42,-168)],[36]*3),
]


# Standing posts remain beside their physical entrance prop, clear of its body.
# Each spur lands on a named public road; all entries retain their content IDs.
SECRET_POSTS={
 'haven-wrack-hollow':((-49,87),24,(-54,88)),
 'haven-ropewalk-garden':((153,-24),3.4,(156,1)),
 'haven-guild-vault':((80,-43),8.4,(84,-34)),
 'haven-mole-pit':((-69,12),5.2,(-67,8)),
 'haven-arcade-school':((-23,-83),21,(-23,-88)),
 'haven-lamp-spring':((-66,56),10.5,(-66,56)),
 'haven-shipyard-butts':((180,-4),3.4,(177,8)),
 'haven-cathedral-reliquary':((81,-99),29,(78,-99)),
 'haven-gate-well':((-6,-48),12.4,(5,-48)),
 'haven-spire-focus':((121,-118),31,(129,-116)),
 'haven-smuggle':((7,107),20,(1,106)),
 'haven-waystone':((-30,-11),7.9,(-23,-13)),
 'haven-lighthouse-eyrie':((216,90),17,(216,81)),
 'haven-peatcut-mouth':((138,-119),29,(151,-108)),
}


def _grade(t, points, heights, width=4.2, surface=TER.PATH, shoulder=4):
    RC.grade_road(t,points,heights,width=width,shoulder=shoulder,
                  surface=surface,clearance=1.5)


def prepare(t, seed):
    # A continuous inhabited hillside underlies the individual foundations.
    # Roads no longer excavate disconnected gutters through old high terraces.
    xfade=np.clip((t.gx+90)/17,0,1)*np.clip((147-t.gx)/20,0,1)
    zfade=np.clip((t.gz+215)/20,0,1)*np.clip((14-t.gz)/12,0,1)
    city=xfade*zfade
    city=city*city*(3-2*city)
    target=np.interp(t.gz,[-215,-179,-151,-120,-98,-77,-43,-27,-14,14],
                     [36,36,36,28,21,14,8.4,8.4,3.4,3.4])
    t.height=t.height*(1-city)+target*city
    masks=REG.land_masks(t,seed)
    for key in ('gullstone','lamp_rock'):
        mask=masks[key]&(t.height>5)
        t.height=np.where(mask,5+(t.height-5)*.48,t.height)
    t.plateau(REG.ANCHORS['gullstone_watch'],14,24,edge=12,surface=TER.ROCK,irregular=0)
    # A low farm shoulder separated from the 68m shared border grading domain.
    t.plateau((162,-112),42,29,edge=25,surface=TER.MEADOW,irregular=0)
    # A broad shingle wrack shelf sits behind the tidal path. It supplies dry
    # collector footing and room for existing shore fauna outside road clearance.
    shore_distance=np.sqrt(((t.gx-229)/23)**2+((t.gz-1)/14)**2)
    shore_blend=np.clip((1.65-shore_distance)/.65,0,1)
    shore_blend=shore_blend**2*(3-2*shore_blend)
    wrack_height=2.75+.12*np.sin(t.gx*.14)*np.cos(t.gz*.11)
    t.height=t.height*(1-shore_blend)+wrack_height*shore_blend
    t.surface=np.where(shore_blend>.7,TER.SHORE,t.surface)
    t.tree_block|=shore_blend>.5
    # One civic precinct has a deliberate south retaining line. The arcade
    # forecourt stays level to its east end; the church rises on a graded link.
    precinct=(t.gx>=-41)&(t.gx<=88)&(t.gz>=-113)&(t.gz<=-70)
    civic_y=np.interp(t.gx,[-41,24,53,88],[21,21,28,28])
    t.height=np.where(precinct,civic_y,t.height)
    t.surface=np.where(precinct,TER.PAVING,t.surface)
    t.tree_block|=precinct
    # Separate building foundations leave a readable travel strip and ground
    # between places; the old enormous overlapping paved circles are retired.
    for name, hx,hz,level in [
        ('fish_market',20,15,8.4),('guild_hall',12,10,8.4),
        ('arcade',29,6,21),('cathedral',22,14,28),
        ('campanile',7,8,28),('brass_dome',11,11,36),
        ('crown_terrace',10,7,36),('high_spire',7,8,21),
        ('custom_house',8,7,3.4),('ropewalk',20,6,3.4),
        ('shipyard',23,18,3.4),('upland_farm',10,10,29),
        ('upland_chapel',10,10,30),('hill_estate',12,11,23),
        ('east_watch',8,9,35)]:
        x,z=REG.ANCHORS[name]
        t.rect_terrace((x,z),hx,hz,level,surface=TER.PAVING,shoulder=0 if name in ('arcade','cathedral') else 10)
    # The public harbour court sits on the landward side of the through-quay.
    t.rect_terrace((35,3),26,14,3.4,surface=TER.PAVING)
    for _,x,z,y,_ in HOUSE_PLOTS:
        t.plateau((x,z),8.6,y,edge=4,surface=TER.MEADOW,irregular=0)
        t.rect_terrace((x,z),5.7,6,y,surface=TER.MEADOW,shoulder=5)
    for ident,x,z,y in WAREHOUSES:
        t.rect_terrace((x,z),6,8,y,surface=TER.PAVING,shoulder=6)
        _grade(t,[(x,z+6),(x,z+12)],[y,y],width=3,shoulder=2,surface=TER.PAVING)
    for points,heights in YARD_LANES:
        _grade(t,points,heights,width=3.4,shoulder=3)
    for ident,((x,z),y,join) in SECRET_POSTS.items():
        jy=float(t.height_at(*join))
        t.rect_terrace((x,z-1.3),2.4,3.4,y,surface=TER.PATH,shoulder=4)
        if tuple(join)!=(x,z): _grade(t,[join,(x,z)],[jy,y],width=2.8,shoulder=4)
    # Full-width civic and cart roads are the final authority at every joint.
    for name,points in REG.ROADS.items():
        _grade(t,points,REG.ROAD_HEIGHTS[name],
               REG.ROAD_WIDTH[name]*REG.SCALE,REG.ROAD_SURFACE[name],
               shoulder=12 if name=='gullstone_path' else 7 if name in ('cart_climb','north_road','east_road','arcade_walk','crown_climb') else 4.5)
    for _,x,z,y,_ in HOUSE_PLOTS:
        _grade(t,[(x,z+4),(x,z+10)],[y,y],width=1.8,shoulder=1.6)
    # Usable pier roots and a shallow work slip; cargo remains above the water.
    for name in ('cargo_pier','crane_pier'):
        x,z=REG.ANCHORS[name]
        _grade(t,[(x,z-17),(x,z-2)],[3.4,3.4],width=7.4,surface=TER.PAVING,shoulder=2)
    _grade(t,[REG.ANCHORS['shipyard'],REG.ANCHORS['shipyard_slip']],
           [3.4,-3.2],width=10,surface=TER.PAVING,shoulder=2)
    # Gullstone keeps open water around it; a narrow elevated span meets a
    # climbing island path. The Lamp road crosses the actual tidal saddle.
    for ident,(stations,width) in REG.SHORE_CROSSINGS.items():
        pts=np.asarray(stations,float)
        for start,end in zip(pts[:-1],pts[1:]):
            direction=end[[0,2]]-start[[0,2]]; length=float(np.linalg.norm(direction))
            along=((t.gx-start[0])*direction[0]+(t.gz-start[2])*direction[1])/length**2
            across=np.abs((t.gx-start[0])*direction[1]-(t.gz-start[2])*direction[0])/length
            mask=(along>=-.8/length)&(along<=1+.8/length)&(across<=width/2+1.2)
            seat=start[1]+(end[1]-start[1])*along-.25
            t.height=np.where(mask,np.minimum(t.height,seat),t.height)
            t.tree_block|=mask
        # Existing shore-road grades are the landings. Extending each span
        # straight ahead flattened the turn away from the deck and made a lip.
    for x,z,y in REG.FARM_FIELDS:
        t.plateau((x,z),13,y,edge=5,surface=TER.MEADOW,irregular=0)
        t.rect_terrace((x,z),9,6,y,surface=TER.PATH)
        _grade(t,[(x,z-8),(151,-108)],[y,29],width=2.2,shoulder=2)
    # The lighthouse entry is at the foot, beyond its elevated gallery bounds.
    _grade(t,[(231,73),(221,81),(215,80)],[11,16,17],width=4.2,shoulder=5)
    t.plateau(REG.ANCHORS['lighthouse'],14.5,17,edge=6,surface=TER.ROCK,irregular=0)
    _grade(t,[(221,81),(215,80)],[17,17],width=5.2,surface=TER.PAVING,shoulder=2)
    for name in ('farm_lane','east_road','cart_climb','lower_lane','quayside'):
        _grade(t,REG.ROADS[name],REG.ROAD_HEIGHTS[name],REG.ROAD_WIDTH[name]*REG.SCALE,
               REG.ROAD_SURFACE[name],shoulder=4)
    t.assign_surface_by_rule(sea_level=REG.SEA_LEVEL)
    masks=REG.land_masks(t,seed)
    authored=np.isin(t.surface,sorted(TER.AUTHORED_SURFACES))
    rocks=masks['gullstone']|masks['lamp_rock']
    t.surface=np.where(rocks&~authored,TER.ROCK,t.surface)
    t.surface=np.where(rocks&(t.height<2.2),TER.SHORE,t.surface)
    t.tree_block|=rocks
    t.dither_boundaries(seed=seed+99,amount=.4)
    # Near-vertical foundation/rock faces cannot carry a lawn or road paint.
    dz,dx=np.gradient(t.height,t.cell)
    steep=np.hypot(dx,dz)>1.05
    t.surface=np.where(steep,TER.ROCK,t.surface)
    t.tree_block|=steep


def populate_houses(build, seed):
    """Full-sized houses face a connected lane and carry small working yards."""
    for v in range(6):
        build.add_mesh(f'Haven_House_{v}',HA.town_house(width=5.8+(v%3)*.7,
            depth=7.2+(v%2)*1.2,storeys=2+(v==4),seed=seed+2400+v,jetty=v%2==0))
    build.add_mesh('Haven_Yard_Bench',P.workbench(seed=seed+2420))
    build.add_mesh('Haven_Yard_Sacks',P.sack(seed=seed+2421))
    build.add_mesh('Haven_Yard_Fence',M.box((5,.85,.28),center=(0,.425,0),material='timber_grey'))
    for ident,x,z,y,v in HOUSE_PLOTS:
        build.placements.append(REG.Placement(f'House_{ident}',f'Haven_House_{v}',(x,y,z),
                                               rotation_y=math.pi,kind='building',collides=True))
        for suffix,key,dx,dz in [('bench','Haven_Yard_Bench',-4.1,6.8),
                                  ('sacks','Haven_Yard_Sacks',3.9,6.3),
                                  ('fence','Haven_Yard_Fence',0,-5.4)]:
            build.placements.append(REG.Placement(f'Yard_{ident}_{suffix}',key,(x+dx,y,z+dz),
                                                   collides=False,kind='prop'))
    build.notes.append(f'{len(HOUSE_PLOTS)} full-sized town houses on connected lanes and small working yards.')


def finish(build):
    """Retain landmark identities while removing repetitive/obstructive extras."""
    # The compact basin needs navigable water between real ships. Decorative
    # crowds of duplicate hulls are removed, retaining the two working piers.
    remove={'Ship_Moored_00','Ship_Moored_01','Ship_Moored_02','Ship_Moored_03',
            'Ship_Moored_04','Ship_Moored_05','Ship_Moored_06',
            'Ship_Anchored_01','Ship_Anchored_03'}
    build.placements=[p for p in build.placements if p.node not in remove and not p.node.startswith('Retaining_')]
    # A continuous masonry face replaces the old scattered retaining strips.
    # The entry gap at x18..32 accepts the authored graded public approach.
    from amberwood import stonework as SW
    walls=[((-41,-70),(18,-70),(0,-1)),((32,-70),(88,-70),(0,-1)),
           ((88,-70),(88,-113),(-1,0))]
    for number,(a,c,inward) in enumerate(walls):
        a=np.asarray(a,float);c=np.asarray(c,float);normal=np.asarray(inward,float)
        length=float(np.linalg.norm(c-a));count=int(math.ceil(length/2))
        parts=[]
        for i in range(count):
            q0=a+(c-a)*i/count;q1=a+(c-a)*(i+1)/count
            # Read the finished terrain at both sides so graded joints and
            # capstones meet the actual authored court without floating lips.
            top0=float(build.terrain.height_at(*(q0+normal*.7)))+.12
            top1=float(build.terrain.height_at(*(q1+normal*.7)))+.12
            bottom0=min(top0-.5,float(build.terrain.height_at(*(q0-normal*2.5)))-.25)
            bottom1=min(top1-.5,float(build.terrain.height_at(*(q1-normal*2.5)))-.25)
            face=M.quad([(q0[0],bottom0,q0[1]),(q1[0],bottom1,q1[1]),
                         (q1[0],top1,q1[1]),(q0[0],top0,q0[1])],uv_scale=.5,material='ashlar')
            parts.append(face)
            cap=M.quad([(q0[0]-.45*normal[0],top0,q0[1]-.45*normal[1]),
                        (q1[0]-.45*normal[0],top1,q1[1]-.45*normal[1]),
                        (q1[0]+.65*normal[0],top1,q1[1]+.65*normal[1]),
                        (q0[0]+.65*normal[0],top0,q0[1]+.65*normal[1])],uv_scale=.5,material='ashlar')
            parts.append(cap)
        key=f'Haven_Civic_Retaining_{number}'
        build.add_mesh(key,M.merge(parts,'ashlar'))
        build.placements.append(REG.Placement(key,key,(0,0,0),kind='landmark',collides=False))
    for p in build.placements:
        if p.kind=='building':
            p.extras=dict(p.extras or {},solidBox=True)
    for entry in build.interactives:
        ident=entry.get('secret')
        if ident not in SECRET_POSTS: continue
        (x,z),_,_=SECRET_POSTS[ident]
        node='Secret_'+ident.replace('-','_')
        p=next(p for p in build.placements if p.node==node)
        # Keep the hatch/cave visible just beyond the unobstructed standing post.
        px,pz=x,z-2.8
        p.position=(px,float(build.terrain.height_at(px,pz))-.05,pz)
        p.rotation_y=0
        entry['node']=node
        entry['position']=[x,round(float(build.terrain.height_at(x,z)),2),z]
        entry['serverTile']=[x+REG.SERVER_ORIGIN[0],REG.SERVER_ORIGIN[1]-z]
    # Visible side entries mark the five below-ground routes, away from the
    # tower galleries and with a clear standing post in front.
    frame=M.merge([M.box((.45,2.7,.6),center=(-1.1,1.35,0),material='rubble_stone'),
        M.box((.45,2.7,.6),center=(1.1,1.35,0),material='rubble_stone'),
        M.box((2.65,.45,.65),center=(0,2.75,0),material='ashlar'),
        M.box((1.8,2.45,.12),center=(0,1.225,.12),material='timber_dark')])
    build.add_mesh('Haven_Side_Entry',frame)
    for ident,anchor in [('bonded-vaults-door','bonded_entry'),('lamp-rock-door','lighthouse_yard'),
        ('gullstone-door','gullstone_door'),('haven-undercroft-door','cathedral_approach'),
        ('salvage-hole-mouth','watch_door')]:
        x,z=REG.ANCHORS[anchor]; pz=z-2.4
        build.placements.append(REG.Placement('Entry_'+ident.replace('-','_'),'Haven_Side_Entry',
            (x,float(build.terrain.height_at(x,pz)),pz),collides=False,kind='prop'))
    # Cargo clusters sit behind the public strip and alongside loading doors.
    for i,(x,z) in enumerate([(19,-8),(52,-9),(99,-5),(120,-4),(143,-6)]):
        for j,key in enumerate(['Crate','Barrel','Coiled_Rope']):
            if key not in build.meshes: continue
            px,pz=x+(j-1)*1.1,z+(.7 if j==1 else 0)
            build.placements.append(REG.Placement(f'Working_Load_{i}_{j}',key,
                (px,float(build.terrain.height_at(px,pz)),pz),rotation_y=j*.7,collides=False,kind='prop'))
    build.notes.append('396m harbour: public cargo spine, terrace lanes, framed services, Gullstone span and tidal Lamp route.')


def finish_metadata(build):
    for entry in build.interactives:
        if entry['id']=='westhaven-lamp-store':
            x,z=215,82
            entry['position']=[x,round(float(build.terrain.height_at(x,z)),2),z]
            entry['serverTile']=[x+REG.SERVER_ORIGIN[0],REG.SERVER_ORIGIN[1]-z]

