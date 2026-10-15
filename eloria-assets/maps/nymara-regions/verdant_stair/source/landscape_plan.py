"""The compact, inhabited limestone stair: source surveys in ordinary metres.

The arrival neighbourhood keeps its original building spacing. Compression is
spent on the quiet outer shelves; native buildings and prop meshes keep scale.
"""
from copy import deepcopy
import math
import numpy as np
from compact_landscape import Axis
from amberwood import terrain as TER
from amberwood import routecraft as RC

OLD_ORIGIN=(174,174)
SERVER_ORIGIN=(108,108)
SERVER_CELLS=360
# Surveyed on the final guarded surface. Residents work beside the premises;
# their original map/name/dialogue identities stay unchanged. In particular the
# elder must never occupy the banyan door, and the cook stands beside its lane.
NPC_POSTS={
    'Tessara':[-28,12.0,-4],
    'Orru Moss':[18,12.0,3],
    'Stairhouse Warden Ashi-Len':[22,12.1821,-12],
    'Canopy Village Elder Ruu-Sath':[-45,23.0,-84],
    'Cenote Diver Vess-Ilu':[-4,22.6984,-63],
    'Green Temple Cantor Nasha-Ro':[137,50.0,-114],
    'Kiln Master Bodri Hask':[184,61.9621,-111],
    'Fern Camp Cook Illa Moss':[-80,23.0,-115],
    'Rope-Crossing Rigger Set-Anu':[45,24.102,-43],
    'Garden Physick Uwe Thal':[117,35.811,-22],
    'Quay Broker Halla Prine':[-40,4.78,49],
    'Cloud Watch Sentinel Isse-Ka':[147,61.4453,-194],
    'Marchstone Hermit Oru-Ves':[200,62.0,-173],
}
# A preserved quartz identity belongs on the damp limestone shoulder, not on
# the unsupported face left by its original large-map scatter coordinate.
RESOURCE_POSTS={'62':[83.0,23.0046,52.0]}
X_OLD=np.array([-174,-35,45,402],float)
X_NEW=np.array([-108,-35,45,252],float)
Z_OLD=np.array([-402,-30,30,174],float)
Z_NEW=np.array([-252,-30,30,108],float)
Y_OLD=np.array([-21,0,.4,7,24,46,72,100,124,150],float)
Y_NEW=np.array([-13,0,.4,4,12,23,36,50,62,78],float)
def x(value):return Axis.interpolate(value,X_OLD,X_NEW)
def z(value):return Axis.interpolate(value,Z_OLD,Z_NEW)
def y(value):return Axis.interpolate(value,Y_OLD,Y_NEW)
def inverse_x(value):return Axis.interpolate(value,X_NEW,X_OLD)
def inverse_z(value):return Axis.interpolate(value,Z_NEW,Z_OLD)
def point(value):return [float(x(value[0])),float(y(value[1])),float(z(value[2]))]
def ground_point(value):return (float(x(value[0])),float(z(value[1])))
def tile(value):
    return [round(float(x(value[0]-174))+108),round(108-float(z(174-value[1])))]

def configure(g):
    """Update the native region's geographic data before any build runs."""
    old_anchors=deepcopy(g['ANCHORS'])
    g.update(SERVER_ORIGIN=SERVER_ORIGIN,SERVER_CELLS=360,SCALE=1.875,LOCAL=1.15,
        PLAY_MIN_X=-108.,PLAY_MAX_X=251.,PLAY_MIN_Z=-251.,PLAY_MAX_Z=108.,
        MARGIN=28.,TERRAIN_X0=-136.,TERRAIN_Z0=-279.,
        TERRAIN_SIZE_X=415.,TERRAIN_SIZE_Z=415.,TERRAIN_CELL=1.)
    g['stair_axis']=lambda xx,zz:(inverse_x(xx)-inverse_z(zz))/6
    g['cross_axis']=lambda xx,zz:(inverse_x(xx)+inverse_z(zz))/6
    g['TERRACES']=tuple((a,b,float(y(h)),name) for a,b,h,name in g['TERRACES'])
    g['ANCHORS']={name:ground_point(p) for name,p in old_anchors.items()}
    g['_ANCHOR_TERRACE']['westgate']='quay'
    g['ANCHORS'].update(westgate=(-102.5,.5),east_pass=(244.5,-94.5),
        boat_landing=(-78.,59.),quarry=(179.,-141.),kiln_yard=(177.,-114.),east_terrace=(190.,-160.))
    for bucket in ('ROUTES','STREAMS','RAVINES'):
        g[bucket]={name:np.array([ground_point(p) for p in line]) for name,line in g[bucket].items()}
    g['RAVINES']['west_ravine'][:,0]+=18*np.clip((-g['RAVINES']['west_ravine'][:,1]-70)/60,0,1)
    g['ANCHORS']['ravine_bridge']=(-79.,-141.)
    g['ROUTES']['east_road']=np.array([g['ANCHORS']['ridge_shrine'],(179,-141),(180,-111),(202,-94.5),(244.5,-94.5)])
    g['ROUTES']['strand_path']=np.array([g['ANCHORS']['mangrove'],g['ANCHORS']['strand_camp'],g['ANCHORS']['boat_landing']])
    g['ROUTES']['temple_road']=np.array([(-102.5,.5),(-82,.5),(-61,8),(-52,23)])
    # All six named flights retain generous full-width approaches. Relief is
    # reauthored; shortening a24m rise into a near-vertical flight is not allowed.
    g['STAIR_RUNS']={name:(tuple(point(a)),tuple(point(b)),width)
                    for name,(a,b,width) in g['STAIR_RUNS'].items()}
    g['STAIR_RUNS']['quay-climb']=((-70,.44,47),(-50,4.04,27),6.)
    g['STAIR_RUNS']['summit-climb']=((149,50.04,-89),(180,62.04,-120),7.)
    g['ACCESS_LANES']={name:([ground_point(p) for p in points],[float(y(h)) for h in heights],width)
                          for name,(points,heights,width) in g['ACCESS_LANES'].items()}
    g['ACCESS_LANES'].update({
        'temple-road':([(-102.5,.5),(-82,.5),(-61,8),(-52,23)],[4]*4,7),
        'quay-contour':([(-50,27),(-43,32),(-40,39),(-48,46)],[4]*4,6),
        'physick-frontages':([(-30,7),(-24,0),(-24,-17),(-25,-23)],[12]*4,3.5),
        'canopy-path':([(6,-59),(-12,-51),(-35,-69),(-49,-85),(-66,-106),(-80,-111),(-86,-115)],[23]*7,4),
        'ravine-landing-path':([(-86,-115),(-72,-125),(-59,-136)],[23]*3,4),
        'north-watch-path':([(36,-155),(27,-170),(12,-177)],[36]*3,4),
        'strand-working-path':([(-67,47),(-60,62),(-39,77)],[.65]*3,4),
        'high-procession':([(144,-110),(148,-99),(149,-89)],[50]*3,7),
        'quarry-road':([(180,-120),(190,-129),(179,-133),(189,-113),(202,-94.5),(244.5,-94.5)],[62]*6,7),
    })
    g['DOOR_POSITIONS']={name:ground_point(p) for name,p in g['DOOR_POSITIONS'].items()}
    # Preserve offsets from the unscaled physical temple/cenote/house meshes.
    for name,anchor in [('temple-sanctum-door','great_temple'),('cenote-deeps-stair','cenote'),('physick-still-door','herbalist')]:
        old={'temple-sanctum-door':(217.35,-193.47),'cenote-deeps-stair':(-6.3,-102.),'physick-still-door':(-21.24,-7.32)}[name]
        a=old_anchors[anchor];b=g['ANCHORS'][anchor]
        g['DOOR_POSITIONS'][name]=(b[0]+old[0]-a[0],b[1]+old[1]-a[1])
    g['DOOR_POSITIONS']['stair-quarry-adit']=(179.,-133.)
    g['DOOR_POSITIONS']['anchor-hollow-mouth']=(-86.,-115.)
    g['CENOTE_APPROACH']=[point(p) for p in g['CENOTE_APPROACH']]
    cx,cz=g['DOOR_POSITIONS']['cenote-deeps-stair']
    g['CENOTE_APPROACH'][-1]=[cx,23.19,cz]
    g['CONTENT_LAYOUT']=deepcopy(g['CONTENT_LAYOUT'])
    for entry in g['CONTENT_LAYOUT']['services']:entry['position'][1]=12.
    for species,patches in g['CONTENT_LAYOUT']['wildlife'].items():
        g['CONTENT_LAYOUT']['wildlife'][species]=[[*ground_point(p[:2]),max(15.,p[2]*.7)] for p in patches]
    g['CONTENT_LAYOUT'].update(primaryArrivalOnly=True,requireFullWildlife=True,roadClearance=5.,npcs=deepcopy(NPC_POSTS),resourcePosts=deepcopy(RESOURCE_POSTS))
    g['SPAWN_QUAY']=g['ANCHORS']['west_quay'];g['SPAWN_TEMPLE']=g['ANCHORS']['temple_court']
    g['prepare_access']=lambda terrain:prepare_access(terrain,g)

def prepare_access(t,g):
    """Make the useful roads continuous, then give paving a limited purpose."""
    from amberwood import junglecraft as JC
    slope=np.hypot(*np.gradient(t.height,t.cell))
    built=np.isin(t.surface,[TER.PAVING,TER.TERRACE_MOSS,TER.PATH])
    t.surface=np.where(built,np.where(slope>.8,TER.ROCK,TER.FOREST),t.surface)
    # The native terrain already reserves each landmark. Narrow paths connect
    # those shelves; major flights carry the vertical climbs explicitly.
    for name,points in g['ROUTES'].items():
        if name in ('grand_stair','lower_climb','quay_climb','shrine_climb','temple_way','summit_climb'):continue
        distance,_=TER._polyline_distance(t.gx,t.gz,points)
        road=(distance<2.3)&(slope<.75)&(t.height>0.2)
        t.surface=np.where(road,TER.PATH,t.surface)
    for points,heights,width in g['ACCESS_LANES'].values():
        RC.grade_road(t,points,heights,width=width,shoulder=5,
                      surface=TER.PATH,clearance=9)
    for foot,head,width in g['STAIR_RUNS'].values():
        a,b=np.array(foot),np.array(head);delta=b[[0,2]]-a[[0,2]]
        length=np.linalg.norm(delta);rise=b[1]-a[1]
        profile=JC.stair_profile(width,rise,length,1 if rise<20 else 2)
        points=a[[0,2]]+profile[:,:1]*delta/length
        heights=a[1]+profile[:,1]-.24;heights[[0,-1]]=[a[1]-.04,b[1]-.04]
        RC.grade_road(t,points,heights,width=width+2,shoulder=5,surface=TER.ROCK,clearance=12)
        for p in (a,b):t.plateau(p[[0,2]],7,p[1]-.04,edge=4,surface=TER.TERRACE_MOSS)
    # Arrival: a service court, six shop/house frontages and a physick yard.
    t.rect_terrace((17,11),18,7,12,0,TER.PATH)
    t.plateau((0,0),6.8,12,edge=3,surface=TER.TERRACE_MOSS)
    for xx,zz in [(-30,7),(-29,-24),(10,-28),(25,-26),(39,-8),(38,25)]:
        t.plateau((xx,zz),6.2,12,edge=4,surface=TER.PATH)
    t.rect_terrace((-28,-10),8,8,12,0,TER.MEADOW)
    for anchor in ('great_temple','water_shrine','upper_court','quay_market','canopy_village','fern_camp','high_camp','north_watch','strand_camp'):
        a=g['ANCHORS'][anchor];level=g['terrace_level'](g['_ANCHOR_TERRACE'][anchor])
        radius=24 if anchor=='great_temple' else 15 if anchor in ('fern_camp','canopy_village') else 11
        t.plateau(a,radius,level,edge=5,surface=TER.TERRACE_MOSS)
    t.plateau((179,-141),13,62,edge=6,surface=TER.ROCK)
    for xx,zz in [(-76,30),(-57,47),(-65,55)]:t.plateau((xx,zz),6,4,edge=4,surface=TER.PATH)
    t.plateau((-67,47),5,.65,edge=3,surface=TER.SHORE)
    t.plateau((-29,59),7,4,edge=4,surface=TER.TERRACE_MOSS)
    for p in [(-98,-146),(-59,-136)]:t.plateau(p,7,23,edge=5,surface=TER.PATH)
    # Native physical thresholds keep their unscaled house/temple offsets.
    for name,(xx,zz) in g['DOOR_POSITIONS'].items():
        level=62 if name=='stair-quarry-adit' else 50 if name=='temple-sanctum-door' else 23 if name in ('cenote-deeps-stair','anchor-hollow-mouth') else 12
        t.plateau((xx,zz),3.5,level,edge=3,surface=TER.PATH)
    # The lower high-camp pad's outer feather reaches the southwest corner of
    # this upper landing. The public flight keeps its full surveyed landing
    # width, including the actual tile+.5 actor centres beyond its final tread.
    summit_head=np.asarray(g['STAIR_RUNS']['summit-climb'][1])
    t.plateau(summit_head[[0,2]],7,summit_head[1]-.04,edge=4,surface=TER.TERRACE_MOSS)
    t.surface=np.where(np.hypot(*np.gradient(t.height,t.cell))>.85,TER.ROCK,t.surface)
    t.water_depth=np.clip(-t.height,0,None)

def inhabited_details(build,seed):
    """Purposeful frontages replace random lower-town house rotations."""
    from amberwood import mesh as M,props as P,stonework as SW
    import region as REG
    t=build.terrain
    houses=[p for p in build.placements if p.node.startswith('House_Lower_')]
    positions=[(-30,7,math.pi/2),(-29,-24,0),(10,-28,0),(25,-26,0),(39,-8,-math.pi/2),(38,25,math.pi)]
    remove={p.node for p in houses[6:]}
    for p,(xx,zz,angle) in zip(houses,positions):
        p.position=(xx,12.,zz);p.rotation_y=angle
    build.placements=[p for p in build.placements if p.node not in remove]
    from regionbuild import Placement
    def place(name,key,xx,zz,rotation=0):
        build.placements.append(Placement(name,key,(xx,float(t.mesh_height_at(xx,zz)),zz),rotation_y=rotation,kind='prop',collides=False))
    # The physick garden has cultivated beds and processing equipment beside
    # its actual door. Shaded herbs remain legible beside a quiet central lane.
    for index,(xx,zz) in enumerate([(-35,-12),(-35,-6),(-27,-18)]):
        bed=SW.group()
        for sign in (-1,1):bed.add(M.box((4.4,.18,.16),center=(0,.13,sign*1.15),material='timber_dark'))
        bed.add(M.box((4.2,.08,2.1),center=(0,.05,0),material='verdant_jungle_floor'))
        build.meshes[f'PhysickBed_{index}']=bed;place(f'Prop_PhysickBed_{index}',f'PhysickBed_{index}',xx,zz)
    build.meshes['PhysickStores']=SW.group(P.crate(size=.8,seed=seed+621),P.barrel(seed=seed+622).translate(1.3,0,0))
    place('Prop_PhysickStores','PhysickStores',-31,-1)
    for index,(xx,zz) in enumerate([(-28,13),(42,16),(31,-23)]):place(f'Prop_FrontageCargo_{index}','PhysickStores',xx,zz)
    native_landing_details(build,seed)
    # Remove trees that obscure the primary procession from the gameplay rig;
    # other pockets retain the region's native banyans and emergent canopy.
    kept=[]
    for p in build.placements:
        if p.kind in ('tree','fern','undergrowth','vine'):
            xx,_,zz=p.position
            d=REG.access_distance(xx,zz)
            if d<(10 if p.kind=='tree' else 4) or (-42<xx<49 and -38<zz<35) or (xx>190 and abs(zz+94.5)<42) or (xx<-60 and abs(zz-.5)<42):continue
        kept.append(p)
    build.placements=kept
    build.notes.append('360m inhabited limestone stair: protected arrival spacing,62m summit,physick work beds,6facing frontages,graded landings and habitat-separated canopy.')


def native_landing_details(build,seed):
    from regionbuild import Placement
    from amberwood import junglecraft as JC,stonework as SW,treecraft as TC
    import region as R
    t=build.terrain
    # The old march furniture stood on what is now open lagoon. Preserve the
    # named stone and waystation on the native landing beyond the water collar.
    march_posts={'March_west_quay_gate_Stone':(-49.,52.),'March_west_quay_gate_Station':(-29.,59.),'March_west_quay_gate_Signpost':(-47.,54.)}
    retained=[]
    for p in build.placements:
        if p.node in march_posts:
            xx,zz=march_posts[p.node];p.position=(xx,float(t.mesh_height_at(xx,zz))-.04,zz)
        elif p.node.startswith('March_west_quay_gate_') and p.position[0]<-60 and abs(p.position[2]-.5)<40:continue
        retained.append(p)
    build.placements=retained
    for e in build.landmarks:
        if e.get('node') in march_posts:
            xx,zz=march_posts[e['node']];e['position']=[xx,float(t.mesh_height_at(xx,zz)),zz];e['serverTile']=[round(xx+108),round(108-zz)]
    # Three quay frontages face the working path, on deliberately supported pads.
    houses=[p for p in build.placements if p.node.startswith('House_Quay_')]
    remove={p.node for p in houses[3:]}
    for p,(xx,zz,angle) in zip(houses,[(-76,30,math.pi),(-57,47,math.pi/2),(-65,55,0)]):
        p.position=(xx,4.,zz);p.rotation_y=angle
    build.placements=[p for p in build.placements if p.node not in remove]
    # A landing is usable: huts have a short flight to their verandah, and the
    # village decks use one shared datum with a full-width access stair.
    for key,stilt,front in [('Camp_Hut',1.6,-1.7),('VillageHut_0',3.,-2.1),('VillageHut_1',3.,-2.1),('VillageHut_2',3.,-2.1)]:
        mesh=build.meshes[key]
        run=stilt*2.6
        mesh.add_walk(RC.stair_flight(2.8,stilt,run,max(8,round(stilt/.2)), 'timber_grey').translate(0,0,front-run+.5))
    # The Anchor Hollow is tied to an actual hut front at the head of its lane.
    hut=next(p for p in build.placements if p.node=='Hut_fern_camp_00')
    hut.position=(-86.,23.,-122.);hut.rotation_y=math.pi
    for e in build.landmarks:
        if e['id']=='fern-camp':e['position']=[-86.,23.,-115.];e['serverTile']=[22,223]
        if e['id']=='high-camp':
            xx,zz=R.ANCHORS['high_camp'];e['position'][1]=float(t.mesh_height_at(xx,zz))
    # Native village huts form a lane around the hollow door. The old random
    # walkway ring met neither the3m verandahs nor the8.5m canopy decks.
    village=R.ANCHORS['canopy_village'];vx,vz=village
    old=[p for p in build.placements if p.node.startswith('Hut_Village_')]
    for p,(dx,dz,angle) in zip(old,[(-13,-4,math.pi/2),(11,-8,-math.pi/2),(-12,12,0),(11,12,0),(0,-18,math.pi)]):
        xx,zz=vx+dx,vz+dz;p.position=(xx,float(t.mesh_height_at(xx,zz)),zz);p.rotation_y=angle
    removed={p.node for p in build.placements if p.node.startswith(('Platform_Village_','Walkway_Village_'))}
    build.placements=[p for p in build.placements if p.node not in removed]
    # One practical viewing/work deck retains the canopy settlement silhouette.
    x0,z0=vx-5,vz-12
    platform=TC.canopy_platform(trunk_radius=1.0,deck_radius=4.6,y=5.2,seed=seed+781,rails=False)
    platform.add_walk(RC.stair_flight(3.4,5.2,14,26,'timber_grey').translate(0,0,-18))
    build.meshes['CanopyWorkingDeck']=platform
    build.placements.append(Placement('Platform_Village_Working','CanopyWorkingDeck',(x0,23.,z0),kind='building'))
    # Dock axis points into the lagoon; a narrow plank approach meets its head.
    dock=next(p for p in build.placements if p.node=='Landmark_Quay');dock.rotation_y=math.pi/4
    dock.position=(-78.,.4,59.)
    stations=np.array([[-65,.65,46],[-67.5,.65,48.5],[-70,2.0,51.]])
    piece=RC.graded_causeway(stations,width=3.4,thickness=.16,parapet=0,foot=-1,stone='timber_dark',paving='timber_grey')
    build.meshes['QuayApproach']=piece
    build.placements.append(Placement('Bridge_QuayApproach','QuayApproach',(0,0,0),kind='bridge'))
    # Scenery does not seal the public stair landings or the garden doorway.
    protected=[np.array(points) for points,_,_ in R.ACCESS_LANES.values()]
    keep=[]
    for p in build.placements:
        if p.node.startswith(('Arcade_','Rail_','Wall_','Prop_')) and p.collides:
            xx,_,zz=p.position
            if R.access_distance(xx,zz)<1.5:continue
        keep.append(p)
    build.placements=keep


def pool_water(t,level,x,z,radius,material,spill_radius=None):
    from amberwood import mesh as M
    xs=np.arange(x-radius,x+radius+.1,2.);zs=np.arange(z-radius,z+radius+.1,2.)
    gx,gz=np.meshgrid(xs,zs);heights=t.height_at(gx,gz);positions=[];indices=[]
    # Clip each terrain triangle against the water height; shared intersections
    # coincide. The water ends beneath the shore, with no cell-sized holes.
    for iz in range(len(zs)-1):
        for ix in range(len(xs)-1):
            corners=[(ix,iz),(ix,iz+1),(ix+1,iz+1),(ix+1,iz)]
            for ids in ((0,1,2),(0,2,3)):
                poly=[np.array([xs[corners[i][0]],heights[corners[i][1],corners[i][0]],zs[corners[i][1]]]) for i in ids]
                out=[]
                for a,b in zip(poly,poly[1:]+poly[:1]):
                    ain=a[1]<=level+.08;bin=b[1]<=level+.08
                    if ain:out.append(a)
                    if ain!=bin:out.append(a+(b-a)*((level+.08-a[1])/(b[1]-a[1])))
                if len(out)<3:continue
                base=len(positions)
                positions.extend([[p[0],level,p[2]] for p in out])
                for i in range(1,len(out)-1):indices.extend([base,base+i,base+i+1])
    if not positions:return M.Mesh(np.empty((0,3)),np.empty((0,3)),np.empty((0,2)),None,np.empty(0,dtype=np.int64),material)
    ps=np.array(positions);mesh=M.Mesh(ps,np.tile([0.,1.,0.],(len(ps),1)),ps[:,[0,2]]*.09,None,np.array(indices),material)
    mesh.weld(1e-5)
    # Filling every low triangle in the survey square also filled unrelated
    # lower terraces beyond the basin's dry rim. A pool belongs to the wetted
    # catchment containing its authored spring. Streams keep their independent
    # sloping ribbons, so downstream drainage does not inherit this flat level.
    triangles=mesh.indices.reshape(-1,3)
    neighbours=[set() for _ in triangles];edges={}
    for i,tri in enumerate(triangles):
        for a,b in zip(tri,np.roll(tri,-1)):
            edge=tuple(sorted((int(a),int(b))))
            for other in edges.get(edge,()):
                neighbours[i].add(other);neighbours[other].add(i)
            edges.setdefault(edge,[]).append(i)
    centres=mesh.positions[triangles].mean(axis=1)[:,[0,2]]
    seed=int(np.argmin(np.linalg.norm(centres-np.array([x,z]),axis=1)))
    keep={seed};pending=[seed]
    while pending:
        for other in neighbours[pending.pop()]-keep:keep.add(other);pending.append(other)
    indices=triangles[sorted(keep)].reshape(-1)
    used,remap=np.unique(indices,return_inverse=True)
    positions=mesh.positions[used].copy()
    if spill_radius is not None:
        # The lower basin drains through two channels. Its flat centre eases
        # down to those independently drawn streams instead of carrying the
        # pool level sideways over the lower stair. At the survey boundary the
        # film meets the actual channel floor, so there is no hanging water lip.
        distance=np.linalg.norm(positions[:,[0,2]]-np.array([x,z]),axis=1)
        blend=np.clip((distance-spill_radius)/max(1.,radius-spill_radius),0,1)
        blend=blend*blend*(3-2*blend)
        floor=t.height_at(positions[:,0],positions[:,2])+.06
        positions[:,1]=np.minimum(level,level*(1-blend)+floor*blend)
    result=M.Mesh(positions,mesh.normals[used],mesh.uvs[used],None,remap,material)
    if spill_radius is not None:result.recompute_normals()
    return result
