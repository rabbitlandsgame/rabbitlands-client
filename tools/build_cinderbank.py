"""Cinderbank's authored workshop kit, shared with authoritative collision.

Rebuild via build_followup_maps.py --adventure crafting. Uses existing Eloria
stone/timber textures. All large props reserve their footprints in both grids;
low floor details do not. Moving machinery never enters a walking lane.
"""
from pathlib import Path
import gzip
import json
import math
import random
import struct

from build_map import GLB
from art_authoring import palette, rod, torus, pebble, barrel, chest, TEXTURES
from build_stillglass import CLIENT, SERVER, SIZE, ROOMS, GATES


class Workshop:
    def __init__(self):
        self.g = GLB()
        self.m = palette(self.g)
        for name, color in [('limestone',(.66,.61,.48)), ('brick',(.43,.23,.15)),
                            ('pavers',(.53,.50,.42)), ('clay',(.46,.33,.24))]:
            self.m[name] = self.g.material(name,color,texture=TEXTURES/'stone-basecolor.png',
                normal=TEXTURES/'stone-normal.png',uv_scale=.6,roughness=.94)
        for name, color in [('teal',(.12,.31,.30)),('copper',(.54,.26,.10)),
                            ('steel',(.43,.48,.47)),('coal',(.055,.052,.048)),
                            ('paper',(.84,.75,.53)),('ember',(.95,.21,.035))]:
            self.m[name] = self.g.material(name,color,glow=name=='ember',
                metallic=.65 if name in ('copper','steel') else 0,roughness=.65)
        self.rng = random.Random(90217)
        # The inherited palette is coastal. Cinderbank uses soot, worn limewash
        # and muted paint; leave bright amber to the lamps and live hearth.
        for key,color in {'earth':(.19,.22,.15),'limestone':(.38,.37,.31),
                          'pavers':(.29,.31,.28),'brick':(.28,.17,.12),
                          'teal':(.035,.10,.085),'paper':(.58,.50,.34),
                          'slate':(.022,.032,.029),'slate_light':(.034,.047,.042),
                          'clay':(.24,.19,.14)}.items():
            self.g.doc['materials'][self.m[key]]['pbrMetallicRoughness']['baseColorFactor']=[*color,1]
        self.grid = bytearray(SIZE*SIZE)
        self.blockers = []
        self.lights = []
        self.signs = []
        # Different room silhouettes within the established gate envelopes.
        for index,(x1,y1,x2,y2) in enumerate(ROOMS):
            for y in range(y1,y2+1):
                for x in range(x1,x2+1):
                    corner = min(x-x1,x2-x)+min(y-y1,y2-y)
                    cut = (6,4,3,6,5)[index]
                    if corner >= cut:self.grid[y*SIZE+x]=13
        for x1,y1,x2,y2 in [(56,33,64,87),(31,56,89,64)]:
            for y in range(y1,y2+1):
                for x in range(x1,x2+1):self.grid[y*SIZE+x]=13
        self.floor = bytes(self.grid)

    def group(self, name):self.g.group=name

    def box(self,name,x,h,y,w,height,d,mat):
        self.g.box(name,x,h,-y,w,height,d,self.m[mat])

    def block(self,name,x,y,w,d):
        bounds=[math.ceil(x-w/2-.25),math.ceil(y-d/2-.25),
                math.floor(x+w/2+.25),math.floor(y+d/2+.25)]
        self.blockers.append(dict(id=name,bounds=bounds))
        for yy in range(bounds[1],bounds[3]+1):
            for xx in range(bounds[0],bounds[2]+1):
                if 0<=xx<SIZE and 0<=yy<SIZE:self.grid[yy*SIZE+xx]=0

    def bench(self,x,y,width=3.8):
        self.block('workbench',x,y,width,1.5)
        for i in range(4):self.box('top_board',x,1.65,y-.6+i*.4,width,.18,.37,'wood')
        for dx in (-width/2+.3,width/2-.3):
            for dy in (-.55,.55):self.box('leg',x+dx,.95,y+dy,.18,1.25,.18,'iron')
        self.box('stretcher',x,.8,y,width-.4,.17,.18,'wood')
        for dx in (-width/2+.18,width/2-.18):self.box('end_iron',x+dx,1.76,y,.10,.07,1.5,'iron')

    def crate(self,x,y,h=.4):
        if h==.4:self.block('crate',x,y,1.65,1.55)
        for i in range(5):self.box('crate_slat',x,h+.14+i*.24,y,1.6,.21,1.5,'wood')
        for dx in (-.65,.65):self.box('crate_strap',x+dx,h+.63,y,.1,1.3,1.55,'iron')
        self.box('shipping_label',x,h+.7,y-.76,.5,.34,.025,'paper')

    def lamp(self,x,y,flag='',height=3.5):
        self.block('lamp',x,y,.5,.5)
        self.group('Scenery_Lamps')
        self.g.cylinder('foot',x,.4,-y,.32,.22,self.m['iron'])
        self.g.cylinder('post',x,.6,-y,.095,height-.6,self.m['iron'])
        self.box('lantern_base',x,height,y,.65,.12,.65,'copper')
        for dx in (-.27,.27):
            for dy in (-.27,.27):self.box('lantern_frame',x+dx,height+.39,y+dy,.045,.7,.045,'iron')
        self.g.cylinder('lantern_roof',x,height+.74,-y,.52,.24,self.m['copper'],4,top=.08)
        self.group('Restore_'+flag if flag else 'Scenery_LampGlass')
        self.box('glass',x,height+.39,y,.44,.55,.44,'glow')
        self.lights.append(dict(at=[x,height+.4,-y],flag=flag,range=7,energy=1.3))

    def sign(self,text,x,y,subtitle='',color='teal'):
        self.group('Scenery_Signs')
        self.block('sign',x,y,3.8,.7)
        for dx in (-1.5,1.5):self.box('post',x+dx,1.4,y,.13,2,.13,'wood')
        self.box('name_board',x,2.2,y,3.8,.95,.2,color)
        for dx in (-1.78,1.78):self.box('strap',x+dx,2.2,y-.12,.065,.9,.025,'copper')
        self.signs.append(dict(text=text,subtitle=subtitle,at=[x,2.24,-y+.14]))

    def anvil(self,x,y):
        self.block('anvil',x,y,2.4,1.4)
        self.g.cylinder('stump',x,.4,-y,.8,.8,self.m['wood'],12)
        self.box('foot',x,1.27,y,1.5,.17,.8,'iron')
        self.box('waist',x,1.52,y,.65,.5,.52,'steel')
        self.box('face',x,1.85,y,1.65,.24,.68,'steel')
        rod(self.g,'horn',(x+.7,1.83,-y),(x+1.35,1.78,-y),.21,self.m['steel'])
        self.box('hammer_head',x-.25,2.05,y,.55,.25,.25,'iron')
        rod(self.g,'hammer_handle',(x-.25,1.98,-y),(x-.1,2,-y-.8),.065,self.m['wood'])

    def forge(self,x,y):
        self.block('forge',x,y,5,4)
        self.group('Scenery_Forge')
        self.box('hearth',x,.75,y,5,.7,4,'brick')
        for row in range(5):
            for dx in (-2,2):self.box('jamb',x+dx,1.25+row*.43,y,.9,.4,3.2,'brick')
            for i in range(5):self.box('back_brick',x-2+i,1.25+row*.43,y+1.6,.93,.4,.55,'brick')
        self.box('lintel',x,3.5,y,5,.45,3.5,'limestone')
        self.box('hood',x,4.1,y+.7,3.5,.8,2.6,'iron')
        self.box('chimney',x,5.6,y+1,1.3,2.3,1.3,'brick')
        self.box('chimney_cap',x,6.85,y+1,1.7,.24,1.7,'limestone')
        for dx in (-1.4,-.7,0,.7,1.4):self.box('grate',x+dx,1.22,y,.1,.1,2.2,'iron')
        self.group('Restore_forge_lit')
        for i in range(16):
            pebble(self.g,'coals',(x+self.rng.uniform(-1.45,1.45),1.28,-y+self.rng.uniform(-.9,.9)),(.23,.14,.22),self.m['ember'],self.rng,3,6)
        self.lights.append(dict(at=[x,2,-y+.4],flag='forge_lit',range=10,energy=2.4))

    def shelf(self,x,y):
        self.block('bookcase',x,y,5.5,1.25)
        for dx in (-2.65,2.65):self.box('upright',x+dx,2.15,y,.2,3.5,1.2,'wood')
        self.box('back',x,2.1,y+.5,5.4,3.4,.12,'wood')
        for h in (.65,1.6,2.55,3.5):
            self.box('shelf',x,h,y,5.5,.14,1.25,'wood')
            for i in range(13):
                ht=self.rng.uniform(.45,.76)
                self.box('book',x-2.4+i*.38,h+.1+ht/2,y,.27,ht,.65,('teal','clay','paper')[i%3])
                self.box('spine_band',x-2.4+i*.38,h+.24,y-.34,.27,.055,.02,'copper')

    def backdrop(self,x,y,width,paint='limestone'):
        """Open-front workshop architecture: a shallow tiled roof behind play."""
        self.group('Scenery_WorkshopArchitecture')
        self.block('rear_wall',x,y,width,.7)
        self.box('stone_sill',x,.7,y,width,.6,1,'limestone')
        self.box('limewash',x,2.7,y,width,3.4,.45,paint)
        divisions=max(2,round(width/4))
        for i in range(divisions+1):
            xx=x-width/2+i*width/divisions
            self.box('timber_frame',xx,2.5,y-.3,.24,4.2,.24,'wood')
            if i<divisions:
                mid=xx+width/divisions/2
                self.box('window_recess',mid,2.9,y-.27,1.7,1.75,.08,'slate')
                for dx in (-.86,0,.86):self.box('mullion',mid+dx,2.9,y-.35,.10,1.9,.12,'wood')
                for h in (2.0,2.9,3.8):self.box('window_rail',mid,h,y-.35,1.86,.10,.12,'wood')
        self.box('eaves',x,4.5,y-.6,width+.9,.25,.25,'wood')
        # Half-depth roofs preserve view of every interaction from above.
        for row in range(5):
            for col in range(math.ceil(width/.65)+2):
                xx=x-width/2-.5+col*.65
                front=y-.75+row*.52;back=front+.60
                h=4.6+row*.20
                self.g.mesh('roof_tile',[(xx,h,-front),(xx+.62,h,-front),
                    (xx+.62,h+.22,-back),(xx,h+.22,-back)],[(0,1,2),(0,2,3)],self.m['slate_light'])
        rod(self.g,'rain_gutter',(x-width/2-.5,4.48,-y+.82),(x+width/2+.5,4.48,-y+.82),.11,self.m['copper'])

    def tool_rack(self,x,y):
        self.block('tool_rack',x,y,3.3,.9)
        self.box('tool_board',x,1.9,y,3.3,1.5,.15,'wood')
        for dx in (-1.4,1.4):self.box('rack_leg',x+dx,1.2,y,.15,1.65,.2,'wood')
        for dx in (-1,0,1):
            rod(self.g,'tool_handle',(x+dx,1.15,-y+.18),(x+dx,2.5,-y+.18),.055,self.m['wood'])
            rod(self.g,'pick_head',(x+dx-.35,2.4,-y+.18),(x+dx+.35,2.45,-y+.18),.075,self.m['steel'])

    def planter(self,x,y,width=4):
        self.block('raised_bed',x,y,width,1.8)
        self.box('bed',x,.72,y,width,.65,1.8,'limestone')
        self.box('soil',x,1.05,y,width-.3,.04,1.5,'earth')
        for i in range(int(width*6)):
            xx=x+self.rng.uniform(-width/2+.2,width/2-.2);yy=y+self.rng.uniform(-.6,.6)
            for j in range(4):
                a=j*math.pi/2
                rod(self.g,'rosemary',(xx,1.05,-yy),(xx+math.cos(a)*.24,1.45+self.rng.random()*.3,-yy+math.sin(a)*.24),.045,self.m['leaf'],4)

    def pump(self,x,y):
        self.block('pump',x,y,4.4,3.4)
        self.group('Scenery_Pump')
        self.box('pump_base',x,.68,y,4.4,.55,3.4,'limestone')
        for dx in (-1.5,1.5):self.box('frame',x+dx,2.15,y,.3,3,.4,'iron')
        self.box('crosshead',x,3.6,y,3.5,.25,.45,'copper')
        self.g.cylinder('cylinder',x,.95,-y,.6,1.5,self.m['copper'],20)
        for h in (1.02,2.35):self.g.cylinder('collar',x,h,-y,.72,.12,self.m['iron'],20)
        rod(self.g,'outlet',(x,1.5,-y),(x-2.1,1.5,-y),.18,self.m['copper'])
        rod(self.g,'downpipe',(x-2.1,1.5,-y),(x-2.1,.5,-y),.18,self.m['copper'])
        self.group('Broken_pump_repaired')
        rod(self.g,'broken_brace',(x-1.5,1.1,-y),(x-.6,1.85,-y),.085,self.m['iron'])
        rod(self.g,'broken_brace',(x+.1,2.5,-y),(x+1.5,3.45,-y),.085,self.m['iron'])
        self.group('Restore_pump_repaired')
        rod(self.g,'steel_brace',(x-1.5,1.1,-y),(x+1.5,3.45,-y),.10,self.m['steel'])
        # Authored in world space; RoadScene creates the matching local pivot.
        self.group('Motion_PumpWheel')
        center=(x+1.4,2.1,-y+.85)
        points=[]
        for i in range(33):
            a=i*math.tau/32;points.append((center[0]+math.cos(a),center[1]+math.sin(a),center[2]))
        for a,b in zip(points,points[1:]):rod(self.g,'flywheel',a,b,.11,self.m['iron'])
        for i in range(8):
            a=i*math.tau/8
            rod(self.g,'spoke',center,(center[0]+math.cos(a)*.96,center[1]+math.sin(a)*.96,center[2]),.055,self.m['copper'])
        self.group('Motion_PumpPiston')
        rod(self.g,'piston',(x,2.1,-y),(x,3.35,-y),.11,self.m['steel'])

    def world(self,targets):
        g=self.g;m=self.m;rng=self.rng
        self.group('Scenery_Foundation')
        self.box('earth',60,-.45,60,123,1.3,123,'earth')
        # Low rubble and planting outside the courts frame the cut-away buildings.
        for x,y in [(33,87),(83,86),(35,31),(83,30),(22,94),(96,24),(20,24),(99,92)]:
            for _ in range(13):
                xx=x+rng.uniform(-6,6);yy=y+rng.uniform(-6,6)
                if self.floor[int(yy)*SIZE+int(xx)]:continue
                pebble(g,'bank_rock',(xx,.3,-yy),(rng.uniform(.5,1.3),rng.uniform(.3,.65),rng.uniform(.5,1.3)),m['limestone'],rng,3,7)
                for i in range(3):rod(g,'grass',(xx,.2,-yy),(xx+.2*i,.9+rng.random(),-yy+.1),.04,m['leaf'],4)
        self.group('Walk_Workshop')
        for y in range(SIZE):
            for x in range(SIZE):
                if not self.floor[y*SIZE+x]:continue
                mat='earth' if y>=87 else 'brick' if y<=33 else 'wood' if x>=89 else 'pavers'
                if abs(x-60)<=2 or abs(y-60)<=2:mat='limestone'
                v=rng.uniform(.9,1.06)
                # Narrow joints on stone; continuous dirt and wooden strips.
                inset=.498 if mat in ('earth','wood') else .494
                self.box('underlay',x,.29,y,1,.2,1,'pavers')
                g.mesh('paving',[(x-inset,.4,-y+inset),(x+inset,.4,-y+inset),(x+inset,.4,-y-inset),(x-inset,.4,-y-inset)],
                       [(0,1,2),(0,2,3)],m[mat],[(v,v,v,1)]*4)
        self.group('Scenery_CourtWalls')
        for y in range(1,SIZE-1):
            for x in range(1,SIZE-1):
                if self.floor[y*SIZE+x] or not any(self.floor[(y+dy)*SIZE+x+dx] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):continue
                # Low foreground walls retain sightlines from the normal camera.
                for row in range(2):self.box('masonry',x,.66+row*.38,y,.94,.35,.94,'limestone')
                self.box('coping',x,1.31,y,1.07,.16,1.07,'pavers')
        for gate in GATES:
            x,y=gate['at'];rot=gate['rotation'];self.group('Scenery_Gate_'+gate['id'])
            for sign in (-1,1):
                xx,yy=x+(0 if rot else sign*5),y+(sign*5 if rot else 0)
                self.box('pier_foot',xx,.65,yy,1.5,.5,1.5,'limestone')
                self.box('timber_pier',xx,2.25,yy,.65,3,.65,'wood')
                for h in (1.1,3.5):self.box('iron_collar',xx,h,yy,.71,.14,.71,'iron')
            self.box('lintel',x,3.95,y,.65 if rot else 11,.45,11 if rot else .65,'wood')
            # Tall architecture stays at the threshold, never over a work target.
        # Shared work court: a real storage cabinet beside a dressed production bench.
        self.group('Scenery_Storage');self.block('cabinet',67,68,3,2)
        for dx in (-.8,.8):chest(g,m,67+dx,.4,-68)
        self.bench(70,72,4.4)
        for i in range(3):self.box('ingot',69+i*.6,1.87,72,.5,.24,.8,'steel')
        self.sign('SUPPLIES',71,68,'Storage + mixing')
        self.group('Scenery_OrderBoard');self.block('order_board',50,73,4,1)
        for dx in (-1.6,1.6):self.box('post',50+dx,1.75,73,.18,2.7,.18,'wood')
        self.box('board',50,2.5,73,4,1.8,.2,'wood')
        for dx in (-1.1,0,1.1):self.box('order_sheet',50+dx,2.5,72.87,.8,1.15,.03,'paper')
        self.sign('CINDERBANK',60,75,'Works / Master Edda')
        self.backdrop(69,76,12)
        self.group('Scenery_WorkCourtTools');self.bench(48,62,4.5);self.tool_rack(48,65)
        self.box('drawing',48,1.77,62,1.7,.03,.9,'paper')
        for i in range(4):self.box('drawing_lines',47.5+i*.32,1.8,62,.04,.02,.7,'teal')
        self.anvil(72,49)
        self.group('Scenery_CourtPlanting');self.planter(47,70);self.planter(72,56,3)
        self.group('Scenery_CourtStock')
        for x,y in [(73,46),(75,49),(45,58)]:self.crate(x,y)
        self.group('Scenery_Cistern');self.block('cistern',47,51,6,5)
        g.cylinder('reservoir',47,.4,-51,2.5,.9,m['limestone'],32)
        g.cylinder('water',47,1.24,-51,2.15,.035,m['water'],32)
        torus(g,'rim',(47,1.35,-51),2.4,.17,m['limestone'],32)
        rod(g,'spout',(47,1.1,-51),(47,2.8,-51),.16,m['copper'])
        rod(g,'spout',(47,2.8,-51),(48,2.8,-51),.16,m['copper'])
        self.group('Restore_pump_repaired')
        rod(g,'flow',(48,2.72,-51),(48,1.3,-51),.09,m['foam'])
        # North: raw yard with unmistakable ore and coal, stock bins and forge.
        for key in ('ore','coal'):
            target=next(t for t in targets if t['id']==key);x,y=target['tile']
            self.group('Scenery_'+key);self.block(key,x,y,2.5,2.2)
            for i in range(7):
                dx=rng.uniform(-.8,.8);dy=rng.uniform(-.6,.6)
                pebble(g,'seam',(x+dx,.85+abs(dx)*.6,-y-dy),(.65,.65,.65),m['limestone' if key=='ore' else 'coal'],rng)
                if key=='ore':rod(g,'iron_vein',(x+dx-.3,1.3,-y-dy),(x+dx+.25,1.65,-y-dy-.1),.11,m['copper'])
            self.sign('IRON ORE' if key=='ore' else 'DEEP COAL',x,y+3,'Harvest with Pickaxe')
        self.sign('RAW YARD',67,91,'Ore / coal / first mix')
        self.group('Scenery_RawWorkbench');self.bench(60,94,4);self.anvil(56,94)
        self.tool_rack(45,99)
        self.backdrop(61,113,20,'brick')
        self.group('Scenery_Stock')
        for x,y in [(47,107),(49,109),(72,108),(73,111)]:self.crate(x,y)
        self.forge(60,109)
        self.group('Scenery_NorthBench');self.bench(60,105.8,4)
        for i in range(3):self.box('ore_sample',59+i,1.9,105.8,.5,.25,.4,'copper')
        # East: open-front reading room with shelves, a desk and meal tray.
        self.group('Scenery_ReadingRoom')
        for x in (96,104,111):self.shelf(x,72)
        self.backdrop(103,75,23)
        self.group('Scenery_ReadingRoom')
        self.bench(101,53,4.2)
        self.box('scroll',101,1.81,53,2,.10,.55,'paper')
        self.planter(112,49,3)
        self.bench(109,60,4.2)
        self.box('open_book_left',108.7,1.8,60,.6,.07,.9,'paper')
        self.box('open_book_right',109.35,1.8,60,.6,.07,.9,'paper')
        for dx in (-.2,.05,.3):self.box('ink_lines',108.7+dx,1.84,60,.025,.015,.65,'clay')
        g.cylinder('food_plate',110.25,1.78,-60,.35,.045,m['paper'],16)
        pebble(g,'bread',(110.25,1.92,-60),(.24,.14,.16),m['clay'],rng)
        self.sign('READING ROOM',96,66,'Books / food / research')
        self.group('Scenery_ReadingTrim')
        for x in (92,113):
            self.block('reading_post',x,74,.8,.8)
            self.box('post',x,2.5,74,.4,4.2,.4,'wood')
        self.box('rear_beam',102.5,4.5,74,22,.3,.4,'wood')
        # South: hand-powered pump, quench trough, anvil and sword rack.
        self.forge(47,17);self.pump(60,12)
        # This wing sits beside the pump. A foreground wall across the south
        # edge would hide the repair target from the standard gameplay camera.
        self.backdrop(71,9,8,'brick')
        self.group('Scenery_Foundry');self.anvil(66,23)
        self.bench(50,27,4.5)
        self.block('trough',72,18,3.2,2.2)
        self.box('quench_trough',72,.85,18,3.2,.9,2.2,'limestone')
        self.box('water',72,1.31,18,2.7,.04,1.7,'water')
        self.sign('FOUNDRY',68,30,'Steel / pump repair')
        self.group('Scenery_SwordRack');self.block('sword_rack',71,25,3.5,1.3)
        for dx in (-1.5,1.5):self.box('rack_post',71+dx,1.4,25,.2,2,.2,'wood')
        for h in (.8,2):self.box('rack_rail',71,h,25,3.5,.2,.2,'wood')
        self.group('Restore_sword_ready')
        for x in (71,):
            self.box('sword_blade',x,1.55,24.7,.18,1.2,.06,'steel')
            self.box('crossguard',x,2.2,24.7,.52,.09,.12,'copper')
            self.box('grip',x,2.42,24.7,.10,.36,.10,'wood')
        # West: packing court, completed shield and torch displayed at handover.
        self.group('Scenery_Dispatch');self.bench(12,60,4.4)
        for x,y in [(12,70),(14,70),(12,72),(22,49),(24,49)]:self.crate(x,y)
        self.backdrop(18,75,17)
        self.group('Scenery_Dispatch');self.tool_rack(10,52)
        self.crate(12,70,1.65)
        self.block('barrels',25,71,3,2)
        for dx in (-.7,.7):barrel(g,m,25+dx,.4,-71)
        self.sign('DISPATCH',25,66,'Pack the road order')
        self.group('Restore_order_ready')
        # Round shield with a boss, straps and plank seams, laid on the desk.
        g.cylinder('shield',12,1.8,-60,.78,.12,m['wood'],32)
        torus(g,'shield_rim',(12,1.94,-60),.75,.045,m['iron'],32)
        g.cylinder('shield_boss',12,1.93,-60,.2,.16,m['steel'],16,top=.12)
        rod(g,'torch_shaft',(10.5,1.86,-60.4),(10.5,1.86,-59.2),.085,m['wood'])
        rod(g,'torch_wrap',(10.5,1.86,-59.55),(10.5,1.86,-59.12),.14,m['canvas'])
        for x,y,flag in [(54,72,''),(69,64,''),(55,85,''),(65,85,''),(88,55,''),
                          (65,35,'forge_lit'),(55,35,'forge_lit'),(59,17,'pump_repaired'),
                          (16,63,'order_ready'),(106,64,'forge_lit')]:self.lamp(x,y,flag)


def build(adventure,targets):
    # Gauntlet-only objects have no role or visible fixture in this workshop.
    targets=[t for t in targets if t['id'] not in ('fork','fork_west','cache_reward','waystone')]
    workshop=Workshop();workshop.world(targets)
    names={'north':'Raw Yard mixing bench','east':'Reading Room','south':'Foundry workbench',
           'west':'Dispatch court','north_object':'Raw Yard workbench','east_object':'Research desk',
           'south_object':'Damaged workshop pump','west_object':'Road order dispatch',
           'cache':'Cinderbank supply cabinet'}
    for target in targets:
        target['label']=names.get(target['id'],target['label'])
        # Information markers and their pick proxies sit on the actual furniture.
        if target['id']=='north_object':target.update(tile=[60,106],approach=[60,103])
    g=workshop.g;grid=workshop.grid;out=CLIENT/'eloria-assets/maps/cinderbank';out.mkdir(parents=True,exist_ok=True)
    for target in targets:
        x,y=target['approach'];assert grid[y*SIZE+x],f"Blocked approach: {target['id']}"
    g.write(out/'world.glb')
    fine=bytearray()
    for y in range(SIZE):
        row=bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2));fine.extend(row+row)
    (out/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,SIZE*2,SIZE*2)+fine)
    (SERVER/'tools/collision/cinderbank.escg.gz').write_bytes(gzip.compress(struct.pack('<4sHHI',b'ESCG',1,200,SIZE)+grid,mtime=0))
    presentation=dict(style='cinderbank',lights=workshop.lights,signs=workshop.signs,
        pickShapes={str(t['objectId']):dict(height=3.5 if t['id']=='south_object' else 1.9,
            radius=1.7 if t['id']=='south_object' else 1.25) for t in targets if t['objectId']},
        motion=[dict(prefix='Motion_PumpWheel',pivot=[61.4,2.1,-11.15],kind='wheel',flag='pump_repaired'),
                dict(prefix='Motion_PumpPiston',pivot=[60,2.1,-12],kind='piston',flag='pump_repaired')])
    layout=dict(id='cinderbank',name=adventure['name'],size=SIZE,spawn=[55,59],gates=GATES,
        targets=targets,rooms=ROOMS,walkGrid=list(grid),heightOrigin=-2.2,heightStep=.2,
        blockers=workshop.blockers,presentation=presentation)
    for path in (out/'layout.json',SERVER/'config/eloria/cinderbank.json'):
        path.write_text(json.dumps(layout,separators=(',',':'))+'\n',encoding='utf-8')
    manifest=json.loads((CLIENT/'eloria-assets/maps/stillglass/world.json').read_text(encoding='utf-8'))
    manifest['assetVersion']='1.1.0';manifest['asset'].update(id='cinderbank',name=adventure['name'])
    manifest['environment']=dict(backgroundColor='#414d48',ambient=dict(color='#b2c0c4',energy=.36),
        sun=dict(color='#fff0d9',energy=.7,rotationDegrees=[-52,-32,0]),tonemap=dict(mode='filmic',exposure=.95))
    manifest['landmarks']=[dict(id=t['id'],name=t['label'],position=[t['tile'][0],.4,-t['tile'][1]]) for t in targets]
    manifest['interactives']=[dict(id=t['id'],kind=t['kind'],objectId=t['objectId'],position=[t['tile'][0],.4,-t['tile'][1]],
        serverTile=t['tile'],approachTile=t['approach'],resource='Iron Ore' if t['id']=='ore' else 'Deep Coal' if t['id']=='coal' else '') for t in targets if t['objectId']]
    manifest['tutorial'].pop('art',None)
    (out/'world.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('cinderbank:',sum(bool(v) for v in grid),'walkable tiles;',len(g.doc['nodes']),'batched meshes;',len(workshop.blockers),'prop footprints')
