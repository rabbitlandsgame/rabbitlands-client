"""Reedway's caravan camp, companion course and saved rescue tableaux.

The shared Workshop authoring helpers supply small props only. Reedway owns
its terrain, trails, wagons, pens and collision. Rebuild through
build_followup_maps.py --adventure summoning.
"""
import gzip
import json
import math
import random
import struct

from build_cinderbank import Workshop
from build_stillglass import CLIENT, SERVER, SIZE, ROOMS, GATES, t
from art_authoring import rod, torus, pebble, barrel, chest, TEXTURES

FLAGS=['caravan_north_open','caravan_east_home','caravan_south_home','caravan_west_home']
BERTHS=[('east',48,50),('south',60,48),('west',72,50)]
FIELDS=[('east',109,60),('south',60,12),('west',12,60)]


class Reedway(Workshop):
    def __init__(self):
        super().__init__()
        self.rng=random.Random(1306)
        for key,color in {'earth':(.20,.25,.13),'wood':(.32,.25,.16),
                          'stone':(.28,.30,.24),'canvas':(.54,.43,.24),
                          'leaf':(.07,.14,.035),'leaf_tip':(.24,.29,.07),
                          'needles':(.04,.105,.065),'teal':(.035,.10,.085),
                          'water':(.025,.085,.072)}.items():
            self.g.doc['materials'][self.m[key]]['pbrMetallicRoughness']['baseColorFactor']=[*color,1]
        self.m['track']=self.g.material('meadow_and_cart_tracks',(.32,.33,.22),
            texture=TEXTURES/'ground-basecolor.png',normal=TEXTURES/'ground-normal.png',uv_scale=.24,roughness=1)
        for key,name,color in [('blue_canvas','indigo_wagon_canvas',(.055,.105,.14)),
                               ('rust_canvas','madder_wagon_canvas',(.23,.065,.034))]:
            self.m[key]=self.g.material(name,color,texture=TEXTURES/'canvas-basecolor.png',
                normal=TEXTURES/'canvas-normal.png',uv_scale=.7,roughness=.96)
        self.grid=bytearray(SIZE*SIZE)
        ellipses=[(60,60,21,20),(60,101,19,17),(102,60,16,18),(60,20,20,17),(18,60,16,19)]
        for room,(cx,cy,rx,ry) in zip(ROOMS,ellipses):
            x0,y0,x1,y1=room
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    if ((x-cx)/rx)**2+((y-cy)/ry)**2<=1:self.grid[y*SIZE+x]=13
        for x0,y0,x1,y1 in [(56,33,64,87),(31,56,89,64)]:
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):self.grid[y*SIZE+x]=13
        self.floor=bytes(self.grid)

    def fence(self,x0,y0,x1,y1,height=1.1):
        length=math.hypot(x1-x0,y1-y0);n=max(1,math.ceil(length/2.5))
        for i in range(n+1):
            x=x0+(x1-x0)*i/n;y=y0+(y1-y0)*i/n
            self.box('split_post',x,.4+height/2,y,.18,height+.2,.18,'wood')
        for h in (.68,.4+height):rod(self.g,'rail',(x0,h,-y0),(x1,h,-y1),.065,self.m['wood'])
        self.block('fence',(x0+x1)/2,(y0+y1)/2,abs(x1-x0)+.25,abs(y1-y0)+.25)

    def tree(self,x,y,scale=1):
        g=self.g;m=self.m
        rod(g,'trunk',(x,.0,-y),(x+.3,4.9*scale,-y),.22*scale,m['bark'],9)
        for j in range(3):
            h=(2.6+j*1.0)*scale
            for i in range(5):
                a=i*math.tau/5+j
                end=(x+math.cos(a)*1.8*scale,h+.65*scale,-y+math.sin(a)*1.8*scale)
                rod(g,'branch',(x,h,-y),end,.085*scale,m['bark'],6)
                pebble(g,'canopy',(end[0],end[1]+.6*scale,end[2]),(1.5*scale,.9*scale,1.5*scale),m['needles' if j%2 else 'leaf'],self.rng,3,8)
        pebble(g,'crown',(x,6.1*scale,-y),(1.5*scale,1.25*scale,1.5*scale),m['leaf'],self.rng,4,8)

    def wagon(self,x,y,color='canvas',broken=False):
        """Correctly oriented spoked wheels, leaf springs, staves and bowed cover."""
        g=self.g;m=self.m
        for dx in (-1.05,1.05):self.box('frame_rail',x+dx,1.18,y,.22,.24,5,'wood')
        for dy in (-1.65,1.65):
            rod(g,'axle',(x-1.9,1.03,-y+dy),(x+1.9,1.03,-y+dy),.12,m['iron'])
            for dx in (-1.72,1.72):
                center=(x+dx,1.12,-y+dy)
                for radius,material in [(1.0,'iron'),(.91,'wood')]:
                    for i in range(24):
                        a=i*math.tau/24;b=(i+1)*math.tau/24
                        rod(g,'wheel_rim',(center[0],center[1]+math.sin(a)*radius,center[2]+math.cos(a)*radius),
                            (center[0],center[1]+math.sin(b)*radius,center[2]+math.cos(b)*radius),.07,m[material],6)
                for i in range(10):
                    a=i*math.tau/10
                    rod(g,'wheel_spoke',center,(center[0],center[1]+math.sin(a)*.88,center[2]+math.cos(a)*.88),.035,m['wood'],5)
                rod(g,'hub',(center[0]-.16,center[1],center[2]),(center[0]+.16,center[1],center[2]),.17,m['iron'])
                for j in range(3):self.box('leaf_spring',x+dx*.65,1.24+j*.035,y-dy,.10,.025,1.15-j*.15,'iron')
        for i in range(14):self.box('bed_plank',x,1.48,y-2.25+i*.34,3,.14,.32,'wood')
        for side in (-1,1):
            for row in range(3):self.box('side_plank',x+side*1.45,1.73+row*.24,y,.14,.21,4.8,'wood')
            for dy in (-2.1,0,2.1):self.box('upright',x+side*1.52,2.08,y+dy,.13,1.36,.16,'iron')
        for dy in (-2.2,2.2):self.box('endgate',x,1.92,y+dy,2.85,.75,.14,'wood')
        self.box('tailgate_latch',x,2.15,y-2.33,.46,.24,.06,'brass')
        for dx in (-.85,.85):rod(g,'drawbar',(x+dx,1.2,-y+2),(x+dx,1,-y+4.1),.085,m['wood'])
        # A curved canvas roof, bound onto five hoops. Front stays open to cargo.
        for dy in (-2,-1,0,1,2):
            for i in range(16):
                a=i*math.pi/16;b=(i+1)*math.pi/16
                rod(g,'cover_hoop',(x+math.cos(a)*1.52,2.08+math.sin(a)*1.75,-y-dy),
                    (x+math.cos(b)*1.52,2.08+math.sin(b)*1.75,-y-dy),.042,m['wood'],5)
        for band in range(16):
            a=band*math.pi/16;b=(band+1)*math.pi/16
            if broken and 6<=band<=8:continue
            pts=[(x+math.cos(theta)*1.55,2.1+math.sin(theta)*1.78,-y-dy)
                 for dy in (-2.15,2.15) for theta in (a,b)]
            g.mesh('canvas_cover',pts,[(0,2,3),(0,3,1)],m[color])
        for dx in (-1.5,1.5):
            for dy in (-1.8,0,1.8):rod(g,'tie',(x+dx,2.15,-y-dy),(x+dx,1.7,-y-dy+.18),.022,m['rope'],4)
        for dx in (-.75,.75):self.box('cargo_case',x+dx,1.93,y-1.25,1.1,.75,1.05,'wood')
        torus(g,'rope_coil',(x,1.6,-y+1.65),.38,.065,m['rope'])

    def berth(self,x,y):
        # Closed low hitching rails make reserved wagon footprints legible even
        # while empty. Wagons swap tableaux; their pads never become ghost walls.
        for edge in [(x-2.8,y-4.8,x+2.8,y-4.8),(x-2.8,y+3.1,x+2.8,y+3.1),
                     (x-2.8,y-4.8,x-2.8,y+3.1),(x+2.8,y-4.8,x+2.8,y+3.1)]:
            self.fence(*edge,height=.72)
        self.block('wagon_berth',x,y-.8,5.6,8)
        self.box('berth_gravel',x,.405,y-.8,5.6,.035,8,'pavers')

    def reeds(self,x,y,radius=3):
        self.block('reed_bed',x,y,radius*2,radius*2)
        self.g.cylinder('pool',x,.37,-y,radius,.06,self.m['water'],28)
        for i in range(32):
            a=i*math.tau/32;r=radius*self.rng.uniform(.89,.98)
            pebble(self.g,'shore_stone',(x+math.cos(a)*r,.43,-y+math.sin(a)*r),
                (.24,.10+self.rng.random()*.12,.29),self.m['stone'],self.rng,3,7)
        for i in range(42):
            a=self.rng.uniform(0,math.tau);r=self.rng.uniform(.65,1)*radius
            xx=x+math.cos(a)*r;yy=y+math.sin(a)*r*.7;h=self.rng.uniform(1,2.3)
            rod(self.g,'reed_stem',(xx,.4,-yy),(xx+.18,h,-yy),.022,self.m['leaf_tip'],4)
            rod(self.g,'seed_head',(xx+.18,h-.3,-yy),(xx+.19,h+.06,-yy),.065,self.m['bark'],5)
            rod(self.g,'leaf',(xx,.6,-yy),(xx-.35,h*.8,-yy+.2),.045,self.m['leaf'],4)

    def shelter(self,x,y):
        self.block('refuge_tent',x,y,7.6,4.8)
        for dx in (-3.5,3.5):
            for dy in (-2,2):rod(self.g,'tent_pole',(x+dx,.4,-y-dy),(x+dx,2.8,-y-dy),.10,self.m['wood'])
        rod(self.g,'ridge',(x,4,-y-2.2),(x,4,-y+2.2),.10,self.m['wood'])
        for side in (-1,1):
            self.g.mesh('canvas',[(x,4.1,-y-2.4),(x,4.1,-y+2.4),
                (x+side*3.8,2.65,-y+2.4),(x+side*3.8,2.65,-y-2.4)],[(0,1,2),(0,2,3)],self.m['canvas'])
        for dx in (-2,1):
            self.box('bedroll',x+dx,.57,y,1.5,.3,3.2,'canvas')
            self.box('blanket',x+dx,.75,y+.6,1.5,.1,1.7,'blue_canvas')

    def world(self,targets):
        g=self.g;m=self.m;rng=self.rng
        self.group('Scenery_WoodlandGround');self.box('ground',60,-.25,60,124,1.15,124,'earth')
        # Dirt tracks are inset into an organic meadow, not a grid of stone courts.
        routes=[[(55,59),(60,69),(60,89),(66,97),(54,103),(60,106)],
                [(60,60),(84,60),(96,64),(108,60)],[(60,60),(60,38),(60,27),(60,15)],
                [(60,60),(36,60),(27,60),(25,67),(15,67),(12,60)],
                [(27,60),(25,53),(15,53),(12,60)]]
        def distance(x,y,a,b):
            dx=b[0]-a[0];dy=b[1]-a[1];u=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
            return math.hypot(x-a[0]-u*dx,y-a[1]-u*dy)
        segments=[(a,b) for route in routes for a,b in zip(route,route[1:])]
        self.group('Walk_Reedway')
        for y in range(SIZE):
            for x in range(SIZE):
                if not self.floor[y*SIZE+x]:continue
                vertices=[(x-.5,.4,-y+.5),(x+.5,.4,-y+.5),(x+.5,.4,-y-.5),(x-.5,.4,-y-.5)]
                colors=[]
                for xx,_,zz in vertices:
                    d=min(distance(xx,-zz,a,b) for a,b in segments)
                    blend=max(0,min(1,(d-1.9)/2))
                    blend=blend*blend*(3-2*blend)
                    colors.append(tuple(a+(b-a)*blend for a,b in zip((1,.83,.59),(.65,.95,.65)))+(1,))
                g.mesh('ground',vertices,[(0,1,2),(0,2,3)],m['track'],colors)
        # Wicker boundaries follow the changing clearing edge. Vegetation stays
        # outside it, preventing trunks from obstructing the camera or summons.
        self.group('Scenery_Boundary')
        for y in range(1,SIZE-1):
            for x in range(1,SIZE-1):
                if self.floor[y*SIZE+x] or not any(self.floor[(y+dy)*SIZE+x+dx] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):continue
                if self.floor[y*SIZE+x-1] or self.floor[y*SIZE+x+1]:
                    self.box('wattle',x,.87,y,.16,.9,.95,'wood')
                if self.floor[(y-1)*SIZE+x] or self.floor[(y+1)*SIZE+x]:
                    self.box('wattle',x,.87,y,.95,.9,.16,'wood')
                if (x+y)%3==0:self.box('boundary_stake',x,1,y,.17,1.25,.17,'wood')
        self.group('Scenery_Woodland')
        for x,y in [(34,88),(82,91),(34,30),(84,31),(25,99),(92,98),(22,20),(94,20),
                    (8,84),(109,84),(8,36),(111,35),(47,118),(73,118)]:
            for _ in range(4):
                xx=x+rng.uniform(-3,3);yy=y+rng.uniform(-3,3)
                if 0<=int(xx)<SIZE and 0<=int(yy)<SIZE and self.floor[int(yy)*SIZE+int(xx)]:continue
                self.tree(xx,yy,rng.uniform(.7,1.15))
        for gate in GATES:
            x,y=gate['at'];rot=gate['rotation'];self.group('Scenery_Gate_'+gate['id'])
            for sign in (-1,1):
                xx,yy=x+(0 if rot else sign*5),y+(sign*5 if rot else 0)
                self.box('gate_post',xx,1.8,yy,.45,2.8,.45,'wood')
                for h in (1.2,2.6):self.box('rope_binding',xx,h,yy,.5,.15,.5,'rope')
        self.group('Scenery_Refuge');self.shelter(48,73)
        self.block('supply_cache',67,68,3.3,1.6)
        for dx in (-.8,.8):chest(g,m,67+dx,.4,-68)
        self.group('Scenery_SupplyCamp');self.bench(70,73)
        for x,y in [(74,71),(74,74),(45,67)]:self.crate(x,y)
        self.sign('TOMA / SUPPLIES',71,68,'Ingredients and recovery')
        self.sign('REEDWAY HALT',68,77,'Bring the caravan home')
        for direction,x,y in BERTHS:
            self.group('Scenery_HitchingYard');self.berth(x,y)
            self.group('Restore_caravan_'+direction+'_home');self.wagon(x,y,dict(east='canvas',south='blue_canvas',west='rust_canvas')[direction])
        # The field yards retain their fence and hitching equipment after rescue.
        for direction,x,y in FIELDS:
            self.group('Scenery_FieldBerths');self.berth(x,y)
            self.group('Broken_caravan_'+direction+'_home');self.wagon(x,y,dict(east='canvas',south='blue_canvas',west='rust_canvas')[direction],broken=direction=='west')
            self.group('Scenery_Latches');self.box('latch_post',x,1.1,y-2.9,.32,1.4,.32,'wood')
            self.box('brass_latch',x,1.55,y-2.68,.36,.23,.16,'brass')
        # Offset verges suggest a winding track, but keep a clear central lane.
        # Summons use a wandering leash, not player-controlled waypoint following.
        self.group('Scenery_ReedPen');self.reeds(47,107,2.7);self.reeds(73,92,2.4)
        self.fence(45,95,53,95,.8);self.fence(67,101,75,101,.8)
        self.box('calling_pad',60,.41,90,4,.045,4,'pavers')
        torus(g,'calling_ring',(60,.46,-90),1.65,.055,m['brass'],32)
        self.sign('CALLING CIRCLE',53,90,'Prepare before summoning')
        self.sign('REED PEN',68,110,'Walk together / no combat')
        self.group('Scenery_NorthWagon');self.block('training_cart',60,109,4.3,6)
        self.wagon(60,110,'canvas')
        self.group('Scenery_QuietTrough');self.block('trough',51,111,3,1.5)
        self.box('trough',51,.75,111,3,.7,1.5,'wood');self.box('water',51,1.12,111,2.7,.035,1.2,'water')
        self.group('Scenery_AxleLane');self.sign('AXLE LANE',94,72,'Choose the same opponent')
        self.crate(110,73);self.crate(113,70)
        self.group('Scenery_RivalYard')
        self.fence(59.5,15,59.5,17,.9);self.fence(59.5,24,59.5,28,.9)
        for x in (53,66):
            self.box('practice_bay',x,.415,21,7,.035,9,'pavers')
        self.sign('CREATURE BAY',50,29,'Watch the actual target')
        self.sign('SUMMON BAY',69,29,'Ownership matters')
        self.group('Scenery_WestRoad')
        self.block('fallen_tree',19,60,4.5,6)
        rod(g,'fallen_trunk',(19,.9,-57.2),(19,1.1,-62.7),.75,m['bark'],12)
        for dy in (-2,-.4,1.5):rod(g,'broken_limb',(19,1,-60+dy),(20.7,1.65,-60+dy-.6),.16,m['bark'])
        self.sign('RETURN ROAD',27,72,'Two routes / one last wagon')
        for x,y,flag in [(54,72,''),(69,65,''),(55,85,''),(65,85,''),(88,55,''),(65,35,''),
                         (15,70,''),(54,108,'caravan_north_open'),(45,56,'caravan_east_home'),
                         (58,54,'caravan_south_home'),(75,56,'caravan_west_home')]:self.lamp(x,y,flag)


def build(adventure,targets):
    targets=[v for v in targets if v['id'] not in ('ore','coal','fork','fork_west','cache_reward','waystone')]
    names={'north':'Quiet pen arrival','east':'Axle Lane','south':'Rival Yard','west':'Return Road','cache':'Toma\'s supply cache'}
    for target in targets:
        target['label']=names.get(target['id'],target['label'])
        if target['id']=='north':target.update(tile=[60,104],approach=[60,104])
        if target['id']=='partner':target.update(tile=[55,108],approach=[55,106],label='Mara')
        if target['id']=='rival':target.update(tile=[102,73],approach=[100,72])
        if target['id']=='north_object':target.update(tile=[60,107],approach=[60,105],label='North wagon latch')
        if target['id'] in ('east_object','south_object','west_object'):
            # Latches are on the front of the actual hitching bay, not inside it.
            x,y=target['tile'];target.update(tile=[x,y-3],approach=[x,y-6])
    targets.append(t('calling_circle','North calling circle',(60,90)))
    art=Reedway();art.world(targets)
    g=art.g;grid=art.grid;out=CLIENT/'eloria-assets/maps/reedway';out.mkdir(parents=True,exist_ok=True)
    for target in targets:
        x,y=target['approach'];assert grid[y*SIZE+x],f"Blocked approach: {target['id']}"
    g.write(out/'world.glb')
    fine=bytearray()
    for y in range(SIZE):
        row=bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2));fine.extend(row+row)
    (out/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,SIZE*2,SIZE*2)+fine)
    (SERVER/'tools/collision/reedway.escg.gz').write_bytes(gzip.compress(struct.pack('<4sHHI',b'ESCG',1,200,SIZE)+grid,mtime=0))
    presentation=dict(style='reedway',flags=FLAGS,lights=art.lights,signs=art.signs,
        pickShapes={str(v['objectId']):dict(height=1.9,radius=1.2) for v in targets if v['objectId']})
    layout=dict(id='reedway',name=adventure['name'],size=SIZE,spawn=[55,59],gates=GATES,rooms=ROOMS,
        targets=targets,walkGrid=list(grid),heightOrigin=-2.2,heightStep=.2,blockers=art.blockers,presentation=presentation,
        companionArrival=[52,103,66,106],
        companionArea=[43,87,77,115],
        encounters=dict(east=[[101,65],[104,65]],south=[[55,20],[64,20]],west=[[25,60],[28,60]]))
    for path in (out/'layout.json',SERVER/'config/eloria/reedway.json'):
        path.write_text(json.dumps(layout,separators=(',',':'))+'\n',encoding='utf-8')
    manifest=json.loads((CLIENT/'eloria-assets/maps/stillglass/world.json').read_text(encoding='utf-8'))
    manifest['assetVersion']='1.1.0';manifest['asset'].update(id='reedway',name=adventure['name'])
    manifest['environment']=dict(backgroundColor='#344a40',ambient=dict(color='#b7c9bc',energy=.43),
        sun=dict(color='#ffeed1',energy=.68,rotationDegrees=[-50,-32,0]),tonemap=dict(mode='filmic',exposure=.95))
    manifest['landmarks']=[dict(id=v['id'],name=v['label'],position=[v['tile'][0],.4,-v['tile'][1]]) for v in targets]
    manifest['interactives']=[dict(id=v['id'],kind=v['kind'],objectId=v['objectId'],position=[v['tile'][0],.4,-v['tile'][1]],
        serverTile=v['tile'],approachTile=v['approach'],resource='') for v in targets if v['objectId']]
    manifest['tutorial'].pop('art',None)
    (out/'world.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('reedway:',sum(bool(v) for v in grid),'walkable tiles;',len(g.doc['nodes']),'batched meshes;',len(art.blockers),'footprints')
