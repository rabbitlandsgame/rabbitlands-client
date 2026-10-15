#!/usr/bin/env python3
"""Build the compact, inhabited Four Gates through the shared region toolkit."""
from __future__ import annotations
from pathlib import Path
import argparse,copy,json,math,struct,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_adapter as A
from native_adapter import M,S,K,L,PALETTE as P,TOOLKIT
from amberwood import terrain as TER, materials as MAT
from regionbuild import RegionBuild,Placement
import landscape_plan as PLAN
import region as REG
import streaming_borders as SB
import glb_reader as GR
import secretrooms as SR
import customs_landing
from designs import four_gates_secrets_design as SEC

PACKAGE=HERE.parent
SEED=20260911
SURFACES={TER.MEADOW:'meadow_grass',TER.PAVING:'cobble_paving',
          TER.ROCK:'cliff_rock',TER.SHORE:'shore_shingle',TER.FOREST:'forest_floor'}

def build_region(seed=SEED,lod=False):
    t=PLAN.terrain(TER,cell=2. if lod else 1.);b=RegionBuild(t)
    b.empty_nodes=[];b.solid_footprints=[];b.animations=[]
    def place(name,geo,x,z,y=None,yaw=0.,kind='prop',footprint=None,walk=False):
        if name not in b.meshes:b.meshes[name]=A.mesh(geo)
        pos=(float(x),float(t.height_at(x,z) if y is None else y),float(z))
        p=b.place(Placement(name,name,pos,rotation_y=yaw,kind=kind,
                            collides=footprint is not None,walk_surface=walk))
        if footprint:
            b.solid_footprints.append((name,x,z,footprint[0],footprint[1],yaw))
        return p
    def shared(name,mesh,pos,walk=False,kind='prop'):
        b.meshes[name]=mesh;b.place(Placement(name,name,pos,kind=kind,walk_surface=walk))
    def box_block(name,x,z,w,d,yaw=0.):
        b.solid_footprints.append((name,x,z,w,d,yaw))
    def landmark(identity,name,node,kind,pos):
        b.landmarks.append({'id':identity,'name':name,'node':node,'type':kind,'position':list(pos)})

    # Central monument and fountains retain native size. Smaller public spaces
    # are laid around them, with four clear axes and places to stop beside them.
    place('Plaza_Monument',L.plaza_monument(P),0,0,31,footprint=(19,19),kind='landmark')
    place('Plaza_Monument_Crystal',L.plaza_crystal(P),0,0,91,kind='landmark')
    landmark('central-plaza','Central Plaza','Plaza_Monument','plaza',(0,31,0))
    landmark('civic-monument','Civic Monument','Plaza_Monument','monument',(0,31,0))
    for i in range(4):
        a=math.pi/4+i*math.pi/2;x,z=35*math.cos(a),35*math.sin(a)
        place(f'Plaza_Fountain_{i}',K.fountain(P),x,z,31,footprint=(9,9))
    for i in range(12):
        a=(i+.5)*math.tau/12
        if min(abs(math.sin(a)),abs(math.cos(a)))<.2:continue
        place(f'Plaza_Bench_{i}',K.bench(P),42*math.cos(a),42*math.sin(a),31,yaw=-a+math.pi/2,kind='small_dressing')
        place(f'Plaza_Lamp_{i}',K.crystal_lamp(4.6,P),49*math.cos(a),49*math.sin(a),31,kind='small_dressing')
    # Four arcades use the native bay profile, with five bays rather than nine.
    for i,a in enumerate([math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4]):
        place(f'Plaza_Arcade_{i}',L.plaza_arcade(P,64,math.pi*.28,bays=5,plinth_rise=0),0,0,31,yaw=-a,kind='landmark')
        # Arcade columns are individual obstructions; the covered aisle remains
        # walkable. Never stamp the full bounding box of a curved portico.
        for k in range(6):
            angle=a-math.pi*.14+k*math.pi*.28/5
            r=60.22
            box_block(f'Arcade_{i}_{k}',r*math.cos(angle),r*math.sin(angle),1.6,1.6)
        for k in range(20):
            angle=a-math.pi*.14+(k+.5)*math.pi*.28/20
            box_block(f'ArcadeBack_{i}_{k}',68.5*math.cos(angle),68.5*math.sin(angle),3.1,.5,math.pi/2-angle)

    # Civic frontage: native shop shells, correctly oriented street thresholds.
    occupied=[]
    for identity,label,quarter,trade,x,z,yaw,w,d in PLAN.SHOPS:
        if 'lantern' in identity or 'reedworks' in identity:geo=K.market_hall(P,w,d)
        elif 'mirrorsmith' in identity:geo=K.warehouse(P,w,d)
        else:geo=K.townhouse(P,w,d,2,2,P.roof_verdigris)
        node='Shopfront_'+identity
        place(node,geo,x,z,31,yaw,kind='building',footprint=(w,d))
        occupied.append((x,z,math.hypot(w,d)/2+6))
        forward=np.array([math.sin(yaw),math.cos(yaw)])
        door=np.array([x,z])+forward*(d/2+.55)
        trigger=door+forward*2.6
        arrival=door+forward*5.6
        mark='Door_'+identity
        b.empty_nodes.append({'node':mark,'position':[float(door[0]),31.08,float(door[1])],
                              'extras':{'interior':identity,'quarter':quarter}})
        b.portals.append({'id':'interior-'+identity,'label':label,'quarter':quarter,'trade':trade,
          'position':[float(door[0]),31.08,float(door[1])],'radius':2.4,'targetMap':identity,
          'targetSpawn':'entrance','doorNode':mark,'arrivalPosition':[float(arrival[0]),31.08,float(arrival[1])],
          'serverTile':PLAN.to_tile(*trigger),'authority':'server'})
        place('Sign_'+identity,K.signboard(P),door[0]+forward[1]*2,door[1]-forward[0]*2,31,yaw,kind='small_dressing')
        # Cart/loading side of every shop leaves the doorway and through street open.
        place('Goods_'+identity,K.crate(P),x+math.cos(yaw)*(w/2+1.3),z-math.sin(yaw)*(w/2+1.3),31,kind='small_dressing')

    # Fewer complete blocks replace the enormous repeated city rings. There are
    # lanes between houses, back yards, and shops that face those lanes.
    for i,a in enumerate(np.arange(0,360,15)*math.pi/180):
        if min(abs(math.sin(a)),abs(math.cos(a)))<.28:continue
        x,z=103*math.cos(a),103*math.sin(a)
        if 10<x<49 and z>78:continue
        if abs(x)<47 and z<-79:continue
        if any(math.hypot(x-cx,z-cz)<radius+9 for cx,cz,radius in occupied):continue
        if any(math.hypot(x-px,z-pz)<12 for px,pz in PLAN.NPC_POSTS.values()):continue
        yaw=-a-math.pi/2
        place(f'District_House_{i:02}',K.townhouse(P,9.5,11,2+(i%3==0),i%4,P.roof_slate if i%2 else P.roof_verdigris),
              x,z,31,yaw,kind='building',footprint=(9.5,11))
        occupied.append((x,z,9))
    for i,(x,z,yaw) in enumerate([(-135,147,.3),(-163,133,.1),(146,165,math.pi),(161,-156,2.8),(136,-151,2.4)]):
        y=float(t.height_at(x,z));PLAN.patch(t,x,z,17,14,y,5)
        place(f'Outer_Farmhouse_{i}',K.farmhouse(P,11,8,i),x,z,y,yaw,kind='building',footprint=(11,8))
        occupied.append((x,z,10))

    # The four monumental gates keep 12m-wide passages, with lower wall runs
    # following the existing civic footprint rather than an exterior ring fence.
    gate_defs=[('north','Gate_North',0,-120,0),('south','Gate_South_Inner',0,120,math.pi),
               ('east','Gate_East',120,0,math.pi/2),('west','Gate_West',-120,0,-math.pi/2)]
    for identity,node,x,z,yaw in gate_defs:
        y=float(t.height_at(x,z))
        PLAN.patch(t,x,z,24 if x else 49,49 if x else 24,y,5)
        place(node,K.gatehouse(P),x,z,y,yaw,kind='landmark')
        for side in (-1,1):
            off=16.5*side
            box_block(node+'_Pier',x+math.cos(yaw)*off,z-math.sin(yaw)*off,16,20,yaw)
        leaf=place(node+'_Portcullis',K.portcullis(P),x,z,y+15.8,yaw,kind='landmark')
        landmark(identity,'Gate '+identity.title(),node,'gate',(x,y,z))
        b.interactives.append({'id':'interact-'+identity,'kind':'gate','type':'gate-portcullis','node':leaf.node,
             'targetNode':leaf.node,'position':[x,y,z],'states':['open','closed'],
             'initialState':'open','animation':leaf.node+'_OpenClose'})
        b.animations.append({'name':leaf.node+'_OpenClose','node':leaf.node,'path':'translation',
          'times':[0,1.5,3.],'values':[[x,y+15.8,z],[x,y,z],[x,y+15.8,z]]})
    # Wall segments terminate before the gate piers; no blind collision ring.
    for i in range(64):
        a=(i+.5)*math.tau/64
        if min(abs(math.sin(a)),abs(math.cos(a)))*120<28:continue
        x,z=120*math.cos(a),120*math.sin(a);yaw=math.pi/2-a
        y=float(t.height_at(x,z))
        place(f'City_Wall_{i:02}',K.wall_segment(12.1,9.,4.,P),x,z,y,yaw,kind='wall',footprint=(12.1,4))
    # The customs arch straddles the southern lake road. Its paired masonry
    # feet descend to the surveyed bed, leaving the seven-metre deck open.
    place('Gate_South_Outer',K.gatehouse(P,32,14,21,opening=12,tower_radius=5),.5,172,23,math.pi,kind='landmark')
    for side in (-1,1):
        box_block('SouthOuter_Pier',.5+side*11,172,9,14)
        feet=S.MeshGroup().add(M.box((9,5.95,14),material='rubble_stone'))
        shared('SouthOuter_Foundation_'+str(side),feet,(.5+side*11,19.985,172),kind='landmark')
    landmark('south-outer','South Outer Gate','Gate_South_Outer','gate',(.5,23,172))
    b.interactives.append({'id':'interact-south-outer','kind':'gate','node':'Gate_South_Outer',
                          'position':[.5,23,165],'states':['open','closed'],'defaultState':'open'})

    # Sanctuary on a northern shore shelf: original temple and beacon dimensions,
    # a modest landing rather than its old 104m-diameter empty platform.
    place('Northern_Sanctuary',L.sanctuary(P,landscape_terrace=False),-115,-162,37,kind='landmark')
    box_block('Sanctuary_Body',-115,-176,44,28)
    stairs=A.L.M.stairs(34.,5.,9.,18,P.stone_trim,2.).rotate_y(math.pi)
    place('Walk_Sanctuary_Stairs',stairs,-115,-154.5,37,kind='landmark',walk=True)
    porch=S.MeshGroup()
    porch.add_walk(M.quad([[-28,0,1.5],[28,0,1.5],[28,0,-1.5],[-28,0,-1.5]],
                          uv_scale=.35,material='cobble_paving'))
    shared('Walk_Sanctuary_Porch',porch,(-115,42.01,-160.5),walk=True)
    for column in range(8):
        box_block('Sanctuary_Column_'+str(column),-136+6*column,-160.4,2.7,2.7)
    place('Sanctuary_Beacon',L.beacon(P),-115,-176,76.6,kind='landmark')
    place('Sanctuary_Beacon_Flame',L.beacon_flame(P),-115,-176,99,kind='landmark')
    place('Sanctuary_Portal',L.sanctuary_portal_energy(P),-115,-162,42,kind='landmark')
    landmark('northern-sanctuary','Northern Sanctuary','Northern_Sanctuary','sanctuary',(-115,37,-162))
    landmark('sanctuary-beacon','Sanctuary Beacon','Sanctuary_Beacon','beacon',(-115,76.6,-176))

    # Practical street furniture is beside workplaces, never across carriageways.
    for i,(x,z) in enumerate([(-25,54),(-48,46),(47,49),(-53,-48),(49,-51),(-71,-40)]):
        place(f'Market_Stall_{i}',K.market_stall(P,i%3),x,z,31,kind='prop',footprint=(3.4,2.4))
        place(f'Market_Cart_{i}',K.handcart(P),x+4,z+2,31,yaw=.2*i,kind='small_dressing')
    for i,(x,z) in enumerate([(-18,81),(20,81),(-19,-80),(20,-80),(-81,-18),(-80,20),(81,19),(80,-20)]):
        place(f'Avenue_Standard_{i}',K.crystal_standard(P,6),x,z,None,kind='small_dressing')

    # Garden beds follow the occupied southern farms. Low fences mark working
    # plots and leave their lane ends open; crops are never scattered on stone.
    for i,(x,z) in enumerate([(22,88),(33,100),(20,102),(121,142),(135,135),(-145,124)]):
        y=float(t.height_at(x,z));PLAN.patch(t,x,z,12,8,y,3)
        t.surface[(abs(t.gx-x)<6)&(abs(t.gz-z)<4)]=TER.PATH
        for row in range(4):
            place(f'Crop_{i}_{row}',K.hedge(P,10,.4,.36),x,z-2.4+row*1.6,y,kind='undergrowth')
        place(f'Garden_Rail_{i}',K.fence_run(P,12,5),x,z+4.8,y,kind='small_dressing')

    # Deterministic habitat vegetation: shore reeds/low scrub, wind-shaped outer
    # copses and planted civic trees. Road/secret/post/yard clearances are authored.
    rng=np.random.default_rng(seed)
    for i in range(180):
        x,z=rng.uniform(-192,192,2);y=float(t.height_at(x,z))
        r=math.hypot(x,z)
        if r<133 or y<20.0 or t.slope_at(x,z)>.65:continue
        if abs(x)<13 or abs(z)<13:continue
        if abs(x+115)<34 and -197<z<-132:continue
        if any(math.hypot(x-px,z-pz)<9 for px,pz in PLAN.NPC_POSTS.values()):continue
        if any(math.hypot(x-px,z-pz)<8 for px,pz in PLAN.SECRET_POSTS.values()):continue
        if any(math.hypot(x-cx,z-cz)<radius+4 for cx,cz,radius in occupied):continue
        if any(abs(x-c['centre'][0])<25 and abs(z-c['centre'][2])<25 for c in PLAN.ARENAS):continue
        if int(t.surface_at(x,z))==TER.PAVING:continue
        place(f'Tree_Shore_{i}',K.broadleaf_tree(P,7+float(rng.uniform(0,3)),i%5),x,z,y,
              float(rng.uniform(0,math.tau)),kind='tree',footprint=(.8,.8))
    for i,a in enumerate([.6,1.,2.1,2.5,3.8,4.2,5.3,5.7]):
        place(f'Tree_Civic_{i}',K.cypress_tree(P,8,i),55*math.cos(a),55*math.sin(a),31,
              kind='tree',footprint=(.6,.6))

    # Every original secret now has a visible physical entrance and a separate
    # standing post within use range. The shared room design retains all lore.
    for i,secret in enumerate(SEC.SECRETS):
        x,z=PLAN.SECRET_POSTS[secret.id];y=float(t.height_at(x,z))
        key='Secret_'+secret.id.replace('-','_')
        b.meshes[key]=SR.entrance_prop(secret.entrance,getattr(SEC,'PROP_PALETTE',None),seed=seed+i)
        b.place(Placement(key,key,(x,y-.03,z),kind='prop',collides=False))
        if secret.kind=='mouth':destination,spawn,_=secret.links[0]
        else:destination,spawn='four_gates_secrets',secret.id
        b.interactives.append({'id':'secret-'+secret.id,'kind':'secret','secret':secret.id,
          'name':secret.name,'label':SR.label_for(secret),'prop':secret.entrance,'key':secret.key,
          'destinationMap':destination,'destinationSpawn':spawn,'position':[x-1,y,z],
          'propPosition':[x,y,z],'node':key,'serverTile':PLAN.to_tile(x-1,z),'authority':'server'})

    b.spawns=[{'id':'player-plaza','position':[0,31.1,55],'rotationDegrees':0},
              {'id':'player-south-gate','position':[0,23.1,158],'rotationDegrees':0}]
    for entry in b.spawns:
        b.empty_nodes.append({'node':'Spawn_'+entry['id'].replace('-','_'),'position':entry['position']})
    for arena in PLAN.ARENAS:
        x,y,z=arena['centre']
        # Stone corner markers are outside the complete35×35 combat square.
        for j,(dx,dz) in enumerate([(-19,-19),(19,-19),(19,19),(-19,19)]):
            place(arena['id']+'_Corner_'+str(j),K.bollard(P),x+dx,z+dz,y,kind='small_dressing')
        place(arena['id']+'_Notice',K.signboard(P),x+20,z-15,y,kind='small_dressing')
        landmark(arena['id'],str(arena['cap'])+' Cap Practice Yard',arena['id']+'_Notice','training-yard',(x,y,z))
    for identity,dest,x,z,out in [('north','mirrorhold',.5,-196.5,[0,-1]),
             ('west','crownwater',-196.5,-.5,[-1,0]),('east','sunmane_steppe',195.5,0,[1,0]),
             ('south','ssarathi_ruins',0,195.5,[0,1])]:
        b.portals.append({'id':identity,'position':[x,23,z],'radius':3.,'destinationMap':dest,
           'serverTile':PLAN.to_tile(x,z),'outward':out,'authority':'server'})
    # Re-apply streets after parcel levelling and gate foundations. Dry approach
    # grades stop precisely at the shared deck seam, not across the water.
    for name,points in PLAN.ROADS.items():
        PLAN.grade(t,points,9 if 'avenue' in name else 6,7)
    # Main-road station levels own branch junctions. A side track's rounded
    # feather must not lift the dry bridge landing above its23m deck.
    for name,points in PLAN.ROADS.items():
        if 'avenue' in name:PLAN.grade(t,points,9,7)
    # Keep the legacy span only for a road without a reciprocal survey. Shared
    # decks own the complete walking surface once its receiving region exists.
    for identity,x,z,yaw in [('east',176,0,math.pi/2),('south',0,176,0.)]:
        if any(frame['portal']==identity for frame in SB.region_specs('four_gates')):
            continue
        depth=(t.gx if identity=='east' else t.gz)
        lateral=(t.gz if identity=='east' else t.gx)
        bed=(depth>=150)&(depth<=204)&(abs(lateral)<8)
        t.height[bed]=17.
        place('Bridge_'+identity.title(),L.bridge_span(P,56,23.08,19,width=10,arches=3),x,z,23.08,yaw,kind='landmark')
        group=S.MeshGroup()
        group.add_walk(M.quad([[-3.5,0,28],[3.5,0,28],[3.5,0,-28],[-3.5,0,-28]],
                             uv_scale=.28,material='cobble_paving'))
        shared('Walk_Deck_Bridge_'+identity.title(),group,(x,23.08,z),walk=True)
        b.placements[-1].rotation_y=yaw
        for sign in (-1,1):
            off=4.25*sign
            box_block('Bridge_'+identity+'_Parapet',x+math.cos(yaw)*off,z-math.sin(yaw)*off,1.5,56,yaw)
    customs_landing.prepare(t,PLAN,TER.PAVING)
    t.water_depth=np.maximum(0,PLAN.WATER_Y-t.height)
    materials=dict(SURFACES);materials[TER.PATH]='packed_earth'
    b.terrain_meshes=t.build_meshes(uv_scale=.35,materials=materials,
                                   blend_edges=True,material_suffix=MAT.GROUND_SUFFIX)
    b.water_meshes['Water_Lake']=M.quad([[-204,19,204],[204,19,204],[204,19,-204],[-204,19,-204]],
                                        uv_scale=.09,material='water_lake')
    b.authored_roads=[{'id':key,'waypoints':[list(p) for p in pts]} for key,pts in PLAN.ROADS.items()]
    with customs_landing.retain_footing_during_geography(b):
        SB.apply(b,'four_gates')
    sys.path.insert(0, str(HERE.parents[1] / 'nymara-regions' / '_finishing'))
    import connector_finish
    import tidal_approaches
    tidal_approaches.apply(b)
    connector_finish.apply(b, 'four_gates')
    sys.path.insert(0, str(HERE.parents[1] / 'nymara-regions' / '_color'))
    import terrain_paint
    terrain_paint.apply(b, 'four_gates')
    import corner_paint
    corner_paint.apply(b)
    return b

def walk_triangles(b):
    triangles=[]
    for name,part in b.terrain_meshes.items():
        if name.startswith('Walk_'):
            triangles.append(part.positions[part.indices.reshape(-1,3)])
    for p in b.placements:
        if p.node.startswith(SB.VIEW_PREFIX):continue
        item=b.meshes[p.mesh];parts=list(getattr(item,'walk_parts',[]))
        if p.walk_surface and not parts:parts=list(getattr(item,'parts',[item]))
        transform=M.translation(*p.position)@M.rotation_y(p.rotation_y)@M.scaling(p.scale)
        for part in parts:
            world=part.transformed(transform)
            triangles.append(world.positions[world.indices.reshape(-1,3)])
    return triangles


def build_collision(b):
    n=792;cell=.5;t=b.terrain
    gx,gz=np.meshgrid(-198+(np.arange(n)+.5)*cell,198-(np.arange(n)+.5)*cell)
    ground=t.height_at(gx,gz);surface=ground.copy()
    walk=(ground>19.35)&(t.slope_at(gx,gz)<.95)
    triangles=walk_triangles(b)
    decks=np.zeros_like(walk)
    if triangles:
        decks,dy=GR.rasterise(np.concatenate(triangles),n,n,-198,198,.5)
        surface=np.where(decks,np.maximum(surface,dy),surface)
        decks &= dy>=ground-.03;walk|=decks
    dz,dx=np.gradient(surface,.5);walk&=decks|(np.hypot(dx,dz)<1.)
    # True, oriented footprint rectangles leave gates, yards and porticos open.
    for _,x,z,w,d,yaw in b.solid_footprints:
        co,si=math.cos(yaw),math.sin(yaw);xx=gx-x;zz=gz-z
        lx=xx*co-zz*si;lz=xx*si+zz*co
        walk &= ~((abs(lx)<w/2+.15)&(abs(lz)<d/2+.15))
    # Shared deck curbs/pier solids are physical barriers and may not be opened
    # by the parent deck's walking part.
    for p in b.placements:
        if p.node.startswith(SB.VIEW_PREFIX) or not p.collides:continue
        if not p.node.startswith('Stream'):continue
        item=b.meshes[p.mesh];lo,hi=item.bounds()
        dx=gx-p.position[0];dz=gz-p.position[2];co,si=math.cos(p.rotation_y),math.sin(p.rotation_y)
        lx=(dx*co-dz*si)/p.scale;lz=(dx*si+dz*co)/p.scale
        walk &= ~((lx>lo[0])&(lx<hi[0])&(lz>lo[2])&(lz<hi[2]))
    origin=float(surface[walk].min())-.2;step=max(.2,(float(surface[walk].max())-origin)/255)
    cells=np.where(walk,np.clip(np.round((surface-origin)/step),1,255),0).astype('uint8')
    stats={'file':'collision.bin','binary':'collision.bin','format':'EWCG','formatVersion':2,'version':2,
      'nodeNames':[p.node for p in b.placements if p.collides and not p.node.startswith(SB.VIEW_PREFIX)],
      'width':n,'height':n,'cellMetres':.5,'cellSize':.5,'originMetres':[-198,198],
      'walkableCells':int(walk.sum()),'walkableFraction':float(walk.mean()),
      'heightEncoding':{'origin':origin,'step':step,'range':[1,255],'zeroMeansBlocked':True},
      'rowOrder':'server-tile-y (row 0 is +Z)'}
    return struct.pack('<4sHHII',b'EWCG',2,0,n,n)+cells.tobytes(),stats

def manifest(b,stats,collision):
    out=json.loads((HERE/'legacy-manifest.json').read_text(encoding='utf-8'))
    out['landscapeRevision']=PLAN.REVISION
    out['asset'].update(bounds={'min':[-204,13,-204],'max':[204,111,204]},
      mapBounds={'min':[-198,13,-198],'max':[198,111,198]},cityRingDiameterMetres=240,
      waterLevel=19,glb='world.glb',serverCells=396)
    out['coordinateTransform'].update(serverOrigin=[198,198],walkingHeight=31.1,origin=[0,31.1,0])
    out['bounds']={'playable':{'min':[-198,13,-198],'max':[197,111,197]},
        'terrain':{'min':[-204,13,-204],'max':[204,111,204]},'serverCells':396,
        'metresPerServerTile':1.,'waterLevel':19}
    out['landmarks']=b.landmarks;out['portals']=b.portals;out['interactives']=b.interactives
    out['spawns']=b.spawns;out['roads']=b.authored_roads;out['streamingBorders']=b.streaming_borders
    out['spawnPoints']=[{'id':s['id'],'node':'Spawn_'+s['id'].replace('-','_'),
       'position':s['position'],'facing':[0,0,-1],'default':i==0} for i,s in enumerate(b.spawns)]
    out['pointsOfInterest']=[{'id':'sanctuary','node':'Northern_Sanctuary','position':[-115,37,-143]},
                             {'id':'plaza','node':'Plaza_Monument','position':[0,31,20]}]
    for entry in out['interiors']:
        portal=next(p for p in b.portals if p['id']=='interior-'+entry['id'])
        entry['door']=portal['position'];entry['arrival']=portal['arrivalPosition']
    for entry in out['gates']:
        mark=next(v for v in b.landmarks if v['id']==entry['id'])
        x,y,z=mark['position'];length=max(math.hypot(x,z),1)
        entry.update(exteriorApproach=[x+x/length*13,y,z+z/length*13],
                     interiorApproach=[x-x/length*13,y,z-z/length*13])
        if entry['id']=='south-outer':entry.pop('portcullisNode',None);entry.pop('animation',None)
    out['bridges']=[{'id':identity,'node':node,'deckNode':node,'walkable':True,'spanMetres':span,
        'deckHeight':23,'position':position,'connects':['city',identity+'-approach']} for identity,node,span,position in [
          ('north','Walk_StreamCauseway_mirrorhold-four-gates',42,[.5,23,-174.5]),
          ('west','Walk_StreamCauseway_four-gates-crownwater',42,[-174.5,23,-.5]),
          ('east','Walk_StreamCauseway_four-gates-sunmane',42,[174.5,23,-.5]),
          ('south','Walk_StreamCauseway_four-gates-ssarathi',42,[.5,23,174.5])]]
    out['paths']=[{'id':v['id'],'widthMetres':9 if 'avenue' in v['id'] else 6,
                   'waypoints':v['waypoints']} for v in b.authored_roads]
    out['districts']=[{'id':k,'name':k.title()+' Quarter','position':p} for k,p in [
      ('civic',[-78,31,20]),('residential',[95,31,32]),('agricultural',[27,31,90]),('service',[0,31,-86])]]
    out['collision']=collision;out['contentLayout']=PLAN.content_layout(b.terrain)
    out['navigation']={'surfaceNodePrefixes':['Terrain_','Walk_'],'defaultSpawn':'player-plaza',
        'terrainConforming':True,'collisionFile':'collision.bin','authority':'server',
        'walkableAreas':['civic-island','four-causeways','working-shores','sanctuary']}
    out['water']={'seaLevel':19,'serverCells':396,'bodies':[{'id':'island-channels','node':'Water_Lake','type':'lake'}]}
    out['minimap']={'file':'minimap.webp','image':'minimap.webp','pixels':396,'size':[396,396],
                    'imageSize':[396,396],'pixelsPerMetre':1.,
                    'worldMin':[-198.,-198.],'worldMax':[198.,198.],
                    'bounds':{'min':[-198,-198],'max':[198,198]},'origin':[-198,-198],
                    'metresPerPixel':1.,'centre':[0.,0.],'northUp':True}
    out['performance']=stats
    # The native twin gate drums span65m including their plinths. They are
    # local obstacles despite exceeding the shared60m distant-scenery cutoff.
    out['rendering']={**out.get('rendering',{}),'occluderFadeMaxExtentMetres':80.,'occluderFadeAlpha':.08}
    out['sources']=[{'id':'authoritative-concept','file':'../../concepts/nymara-regions/four_gates_region_concept.png',
                    'role':'authoritative-composition'},
                   {'id':'generator','file':'source/build_four_gates.py','seed':SEED,'role':'reproducible-build'}]
    # Legacy editorial lore markers keep their identities, with protected core
    # remapping. Runtime served content is overlaid only by the shared helper.
    for category in ('npcMarkers','harvestables','creatureSpawns','regions'):
        for entry in out.get(category,[]):
            if not isinstance(entry,dict) or 'position' not in entry:continue
            x,_,z=entry['position'];x,z=PLAN.remap_world(x,z)
            entry['position']=[x,float(b.terrain.height_at(x,z)),z]
            if 'radius' in entry:entry['radius']=min(entry['radius'],24)
    out['environment']['presentation']={'ambientAudio':[{'id':'settlement','zone':'civic-island'},
        {'id':'surf','zone':'island-channels'}],'chimneySmoke':{'enabled':True,
        'nodes':['Shopfront_four-gates-mirrorsmith-forge','Shopfront_four-gates-ferrymans-rest']}}
    out['environment']['zones']=[{'id':'civic-island','centre':[0,31,0],'radius':120},
                                 {'id':'island-channels','centre':[-166,19,0],'radius':52}]
    out['effects']=[e for e in out.get('effects',[]) if not str(e.get('id','')).startswith(('falls','waterfall-mist'))]
    for effect in out['effects']:
        if effect.get('id')=='water-ring':effect['node']='Water_Lake'
    out['assumptions']=['One metre per server tile; native building and doorway dimensions retained.',
                        'All four causeways have reciprocal surveys and continuous receiving scenery.']
    out['knownLimitations']=[]
    import contentposts
    posts=PACKAGE/'source/server-content.json'
    if posts.is_file() and (PACKAGE/'world.glb').is_file():
        contentposts.apply(out,PACKAGE,json.loads(posts.read_text(encoding='utf-8')))
    contentposts.apply_runtime(out,PACKAGE)
    return out

def render_minimap(b,path):
    """One pixel per metre, derived from final terrain and actual footprint plan."""
    from PIL import Image,ImageDraw
    xx,zz=np.meshgrid(np.arange(396)-197.5,np.arange(396)-197.5)
    yy=b.terrain.height_at(xx,zz);slope=b.terrain.slope_at(xx,zz)
    rgb=np.empty((396,396,3),dtype=np.uint8);rgb[:]=[94,117,72]
    rgb[yy<19.3]=[48,113,124];rgb[(yy>=19.3)&(yy<20.4)]=[161,153,119]
    rgb[slope>.75]=[130,130,112]
    surf=b.terrain.surface_at(xx,zz);rgb[surf==TER.PAVING]=[171,164,139]
    triangles=walk_triangles(b)
    if triangles:
        covered,top=GR.rasterise(np.concatenate(triangles),396,396,-198,198,1.)
        visible=covered[::-1] & (top[::-1]>=yy-.2)
        rgb[visible]=[177,172,154]
    img=Image.fromarray(rgb);draw=ImageDraw.Draw(img)
    for _,x,z,w,d,yaw in b.solid_footprints:
        co,si=math.cos(yaw),math.sin(yaw)
        points=[(198+x+co*u+si*v,198+z-si*u+co*v) for u,v in [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]]
        draw.polygon(points,fill=(111,111,101),outline=(70,79,72))
    img.save(path,quality=94)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=PACKAGE)
    ap.add_argument('--probe',action='store_true');ap.add_argument('--skip-lod2',action='store_true')
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    started=time.time();b=build_region();print('Composed',len(b.placements),'placements',flush=True)
    payload,collision=build_collision(b)
    if a.probe:
        (a.out/'collision.bin').write_bytes(payload)
        (a.out/'world.json').write_text(json.dumps(manifest(b,{},collision),indent=2)+'\n',encoding='utf-8')
        render_minimap(b,a.out/'minimap.webp');print('Probe complete',time.time()-started,flush=True);return
    cache=HERE/'texture-cache'
    stats=A.export(b,a.out/'world.glb',cache)
    print('Main GLB complete',stats,flush=True)
    if not a.skip_lod2:
        lod=A.export(build_region(lod=True),a.out/'world-lod2.glb',cache,lod=True)
        print('LOD complete',lod,flush=True)
    (a.out/'collision.bin').write_bytes(payload)
    render_minimap(b,a.out/'minimap.webp')
    (a.out/'world.json').write_text(json.dumps(manifest(b,stats,collision),indent=2)+'\n',encoding='utf-8')
    print('Final package written',time.time()-started,flush=True)

if __name__=='__main__':main()
