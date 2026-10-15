"""Compact drowned-city working posts and explicit regional surveys."""
from __future__ import annotations
import math
import numpy as np
from amberwood import routecraft as RC, civiccraft as CIV, props as PROP, junglecraft as JC
from amberwood import terrain as TER
from amberwood import mesh as M, stonework as SW
import region as REG
import ssarathikit as SK

CISTERN=(-85.,-44.);CISTERN_DOOR=(-80.,-44.)
FERRY=(8.,74.);FERRY_STATION=(8.,92.)
PORTALS={'north-stair':(154.5,4.,-264.5),'east-causeway':(264.5,4.,-88.5),
         'west-causeway':(-112.5,4.,-108.5),'south-gate':(8.,1.2,74.)}
HOUSES=[('archive-workers',-27.,-10.,1.45,math.pi),('quay-stores',27.,-10.,1.45,math.pi),
        ('market-poler',124.,43.,1.9,0.),('market-copyist',165.,43.,1.9,0.),
        ('lily-copyists',-12.,-93.,2.05,math.pi),('lineage-house',50.,-21.,1.95,math.pi)]
DOORS={'archive-vault-door':(64.,-123.),'hatchery-descent':(118.,-86.),
       'cistern-shaft':CISTERN_DOOR,'undercroft-mouth':(138.,60.),
       'tenth-mouth-door':(-32.,-83.),'water-gate-undercut-mouth':(40.,35.),
       'lineage-house-door':(50.,-15.)}
SECRET_SITES={'ruins-lily-garden':(-43.,-96.),'ruins-gate-cache':(27.,-21.),
 'ruins-falls-spring':(184.,-199.),'ruins-shrine-butts':(-65.,-118.),
 'ruins-cistern-well':(-77.,-55.),'ruins-temple-focus':(25.,-122.),
 'ruins-shrine-eyrie':(192.,-80.)}
ROADS={
 'market-connection':([(40,12),(77,15),(111,20),(146,20)],[1.8,1.8,1.9,1.9],7.),
 'east-shore-road':([(146,20),(190,8),(212,-32),(220,-60),(210,-88.5),(222.5,-88.5)],[1.9,1.8,4,4,4,4],7.),
 'east-shrine-link':([(194,-83),(204,-79),(214,-78)],[1.8,3,4],5.),
 'north-basin-road':([(212,-85),(214,-124),(204,-176),(180,-200),(154.5,-222.5)],[4,4,4,4,4],7.),
 'north-terrace-link':([(128,-190),(150,-188),(180,-200)],[6,5,4],6.),
 'west-shrine-road':([(-52,-80),(-76,-92),(-78,-108),(-90,-108.5),(-112.5,-108.5)],[2.05,1.8,1.8,4,4],7.),
 'ferry-yard':([(12,88),(8,92),(8,85)],[1.25,1.25,1.45],6.),
 'cistern-service-walk':([(-52,-80),(-65,-69),(-75,-58),(-75,-44)],[2.05,2.05,2.25,2.25],4.5),
 'lily-north-walk':([(-52,-80),(-51,-94),(-32,-94),(-12,-87)],[2.05]*4,4.5),
 'tenth-mouth-walk':([(-51,-94),(-43,-85),(-32,-83)],[2.05]*3,4.5),
 'lineage-door-walk':([(40,-12),(50,-15),(56,-14)],[1.95]*3,4.5),
 'root-mouth-walk':([(151,49),(147,59),(140,59)],[3.7]*3,4.5),
 'falls-keeper-walk':([(204,-176),(194,-189),(184,-199)],[4.]*3,4.5),
 'east-waystation-walk':([(213,-60),(199,-66),(192,-68),(192,-80)],[4.]*4,4.5),
 'west-shrine-custodians':([(-77,-110),(-70,-118),(-65,-118)],[1.8]*3,4.),
 'vault-basement-court':([(40,-107),(55,-112),(64,-112),(64,-123)],[14,13,13,13],6.),
 'temple-processional-ascent':([(40,-80),(40,-94),(40,-107),(40,-118)],[2.2,8,14,21],10.),
 'north-waystation-walk':([(180,-200),(186,-197),(186,-191)],[4.]*3,4.5),
}
CONTENT_LAYOUT={
 'primaryArrivalOnly':True,'requireFullWildlife':True,'roadClearance':3.0,
 'gauntlets':{'ssarathi_gauntlet':{'keeperTile':[170,82],'returnTile':[174,78]}},
 'services':[{'role':'information','position':[0,1.45,6]}, {'role':'storage','position':[-9,1.45,-3]},
             {'role':'crafting_station','position':[9,1.45,-3]}, {'role':'training','position':[12,1.45,7]}],
 'npcs':{'Archivist Sesh':[-8,1.45,5],'Vess Scale':[-11,1.45,-7],
 'Sun-Vault Warden Hass-Ile':[73,13,-120],'Lineage Reader Ssiran-Ta':[56,1.95,-14],
 'Hatchery Keeper Nuu-Sesh':[120,2.25,-91],'Cistern Sounder Vek-Ora':[-74,2.25,-50],
 'Stela Copyist Ilhu-Ren':[149,13.9,-147],'Water-Gate Marshal Set-Kaal':[8,1.25,92],
 'Lily Court Steward Aa-Nesh':[-21,2.05,-90],'Marchstone Priest Osu-Val':[194,1.8,-82],
 'Undercroft Digger Rell Marrow':[137,3.7,56],'Falls Measurer Ith-Anu':[187,4,-196],
 'Coil Bridge Toll-Taker Ude-Sar':[50,1.8,-49],'Ssethis the Doorkeeper':[54,2.1,34]},
 'wildlife':{'canopy_glider':[[152,48,22],[226,-95,24]],'swamp_heron':[[-40,-22,19],[102,-21,22]],
 'delta_mud_crab':[[-48,29,20],[180,5,20]],'scalevine_stalker':[[166,54,23],[-88,-137,23]],
 'saltmarsh_crocodile':[[210,-43,21],[-83,-76,22]],'sunscale_basilisk':[[138,-150,24],[110,-204,24]],
 'rune_stone_golem':[[-37,-164,25],[115,-209,25]],'void_tentacle_construct':[[-84,-126,25],[96,-212,26]],
 'gloom_wyvern':[[-11,-217,34],[-88,-208,29],[98,-218,30]],
 'emerald_canopy_dragon':[[-8,-208,36],[111,-225,30],[240,-128,31]]},
 'harvest':{'Lichen':[[-44,-28,19],[114,-22,20]],'Lotus':[[112,-32,18]],
 'Watercress':[[-40,-26,19]],'Venom Bulb':[[148,58,22]],'Toadstool':[[215,-100,22]],
 'Geode':[[140,-148,22]],'Flint':[[-80,-108,20]]},
}

def dock_routes():
    routes={}
    for i,z in enumerate((-3.,4.,11.)):routes[f'east_dock_{i}']=([(198.,z),(218.,z)],3.4)
    for i,z in enumerate((27.,33.,39.)):routes[f'west_dock_{i}']=([(-55.,z),(-38.,z)],3.2)
    for i,x in enumerate((8.,28.)):routes[f'south_dock_{i}']=([(x,87.),(x,66.)],3.6)
    return routes

def _yard(t,x,z,y,width,depth,surface=REG.MOSS_STONE):
    RC.grade_road(t,[(x-width/2,z),(x+width/2,z)],[y,y],width=depth,shoulder=3,
                  surface=surface,clearance=3)

def prepare(t):
    # This northern wet inlet physically meets the eastern basin drainage. The
    # shared bridge is over its water, rather than an isolated cut in a cliff.
    inlet=np.array([(154.5,-282),(154.5,-229),(180,-204),(204,-178),(225,-141)])
    d,_=TER._polyline_distance(t.gx,t.gz,inlet)
    blend=1-TER._smoothstep(11,29,d)
    t.height=t.height*(1-blend)+np.minimum(t.height,-2.1)*blend
    t.surface=np.where(blend>.45,REG.SILT,t.surface);t.tree_block|=d<17
    _yard(t,0,-1,1.45,35,22,REG.JADE_PAVING)
    _yard(t,146,20,1.9,46,29,REG.JADE_PAVING)
    for x,z,y,w,d in [(192,-68,4,12,10),(186,-191,4,12,10),(-43,-96,2.05,7,7),(27,-21,1.95,7,7),
                       (184,-199,4,9,9),(-65,-118,1.8,7,7),(-77,-55,2.25,7,7),
                       (25,-122,13,7,7),(192,-80,4,7,7),(137,56,3.7,8,8),
                       (118,-86,2.25,8,8)]:
        _yard(t,x,z,y,w,d)
    for identity,x,z,y,angle in HOUSES:
        _yard(t,x,z,y,12,11)
        toward=(x,z+8) if angle else (x,z-8)
        _yard(t,toward[0],toward[1],y,5,4)
    for points,heights,width in ROADS.values():
        RC.grade_road(t,points,heights,width=width,shoulder=4,surface=REG.JADE_PAVING,clearance=4)
    # Keep dry store yards tied into the working court without paving the bank.
    for a,b,y in [((-27,-2),(-16,0),1.45),((27,-2),(16,0),1.45),
                  ((124,35),(124,30),1.9),((165,35),(165,30),1.9)]:
        RC.grade_road(t,[a,b],[y,y],width=4,shoulder=2,surface=REG.MOSS_STONE,clearance=2)
    t._survey={}
    for span in REG.bridge_spans():
        c=np.asarray(span['centre']);d=np.asarray(span['heading'])
        pts=np.array([c-d*(span['half_span']+1),c+d*(span['half_span']+1)])
        hs=[max(REG.DECK,float(t.height_at(*p)))+.24 for p in pts]
        t._survey[span['name']]=(pts,hs,span['half_width']*2,'stone')
    for name,(pts,width) in dock_routes().items():
        pts=np.asarray(pts);t._survey[name]=(pts,[max(1.25,float(t.height_at(*pts[0])))+.24,1.2],width,'wood')
    t._survey['cistern_walk']=(np.array([[-75.,-44.],[-79.,-44.]]),[2.25,2.0],3.4,'wood')
    for name,(pts,hs,width,kind) in t._survey.items():
        a,b=pts;run=b-a;length=float(np.linalg.norm(run));d=run/length
        for p,h,sign in ((a,hs[0],-1),(b,hs[1],1)):
            if kind=='wood' and sign==1:continue
            back=p+d*sign*6
            # Continue the bank plane into its feather. A round, clamped road
            # cap would flatten the rising processional road past this join.
            outward=d*sign
            along=(t.gx-p[0])*outward[0]+(t.gz-p[1])*outward[1]
            across=np.abs((t.gx-p[0])*outward[1]-(t.gz-p[1])*outward[0])
            target=h-.20+(max(1.2,float(t.height_at(*back)))-(h-.20))*along/6
            blend=(TER._smoothstep(-2,0,along)*(1-TER._smoothstep(6,10,along))
                   *(1-TER._smoothstep(width/2+.5,width/2+4.5,across)))
            t.height=t.height*(1-blend)+target*blend
            t.surface=np.where(blend>.6,REG.JADE_PAVING,t.surface)
            t.tree_block|=blend>.1
        u=((t.gx-a[0])*run[0]+(t.gz-a[1])*run[1])/length**2
        v=np.abs((t.gx-a[0])*run[1]-(t.gz-a[1])*run[0])/length
        mask=(u>=-2/length)&(u<=1+2/length)&(v<width/2+2)
        t.height=np.where(mask,np.minimum(t.height,hs[0]+(hs[1]-hs[0])*u-.24),t.height)
        t.tree_block|=mask
    t.mark_blocked_disc(CISTERN,9)
    # Moss holds the abandoned outer temple terraces. Paving remains on the
    # processional roads, vault court and the monument's own foundation.
    r=np.hypot(t.gx-40,t.gz+182)
    moss=(r>54)&(r<94)&(t.surface==REG.JADE_PAVING)
    for pts in list(REG.street_routes().values())+[v[0] for v in ROADS.values()]:
        dist,_=TER._polyline_distance(t.gx,t.gz,np.asarray(pts))
        moss &= dist>8
    moss &= ~((np.abs(t.gx-40)<24)&(t.gz>-140)&(t.gz<-86))
    t.surface=np.where(moss,REG.MOSS_STONE,t.surface)

def dress_crossings(build,seed):
    import populate as POP
    for name,(pts,hs,width,kind) in build.terrain._survey.items():
        a,b=pts;length=float(np.linalg.norm(b-a))
        if kind=='stone':
            mesh=CIV.arcaded_causeway(length,*hs,width=width,arches=3,foot=-7,
                    stone=SK.JADE_ASHLAR,paving=SK.JADE_PAVING,trim=SK.JADE_SCALE)
            angle=math.atan2(-(b[1]-a[1]),b[0]-a[0]);node='Bridge_'+name
        else:
            mesh=CIV.sloped_boardwalk(length,*hs,width=width,foot=-7,timber=SK.TIMBER,rope=SK.TIMBER)
            mesh.translate(0,0,-length/2);angle=math.atan2(b[0]-a[0],b[1]-a[1]);node='Dock_'+name
        POP._add(build,node,node,mesh,(float((a+b)[0]/2),0,float((a+b)[1]/2)),angle,kind='structure')
        build.crossings.append({'id':name,'endpoints':RC.crossing_endpoints([[float(a[0]),hs[0],float(a[1])],[float(b[0]),hs[1],float(b[1])]])})
        if name=='great_causeway__channel_main':
            build.landmarks.append({'id':'channel-bridge','name':'The Coil Bridge','node':node,'type':'bridge',
                'position':[float((a+b)[0]/2),sum(hs)/2,float((a+b)[1]/2)]})

def dress(build,seed):
    import populate as POP
    t=build.terrain
    for i,x in enumerate((-9.,9.)):
        mesh=CIV.market_shelter(width=12,depth=5,stone=SK.JADE_ASHLAR,timber=SK.TIMBER,roof=SK.CANVAS)
        POP._add(build,f'QuayShelter_{i}','QuayShelter',mesh,(x,1.45,-6),kind='structure')
    # A copyist's working bench and bundles under each canopy. Their frontage
    # stays behind the shared service tiles, leaving the court route clear.
    for i,x in enumerate((-9.,9.)):
        bench=PROP.workbench(2.8,seed+210+i,tools=i==1)
        for part in bench.all_parts:
            if part.material not in (SK.TIMBER,SK.CANVAS):part.material=SK.TIMBER
        p=POP._add(build,f'QuayRecordsBench_{i}',f'QuayRecordsBench_{i}',bench,(x,1.45,-3),kind='structure',collides=True)
        p.extras={'solidRects':[[-1.5,-.45,1.5,.45]]}
        for j in range(3):
            ledger=M.box((.46,.08,.33),center=(0,.98,0),material=SK.CANVAS)
            POP._add(build,f'QuayLedger_{i}_{j}','QuayLedger',ledger,(x-.6+j*.5,1.45,-3),rotation=j*.13,kind='prop')
        stool=SW.group(M.box((.48,.10,.48),center=(0,.46,0),material=SK.TIMBER),
                       M.box((.18,.43,.18),center=(0,.215,0),material=SK.TIMBER))
        POP._add(build,f'QuayStool_{i}','QuayStool',stool,(x+2,1.45,-1.5),kind='prop',collides=True)
    for i,(x,z) in enumerate([(-13,-8),(-12,-8),(-13,-7),(14,-8),(15,-8),(-24,-5),(24,-5),(-15,-1),(15,-1)]):
        POP._add(build,f'StoreBundle_{i}','StoreBundle',PROP.crate(.85,seed+220,material=SK.TIMBER),(x,1.45,z),kind='prop',collides=True)
    build.landmarks.append({'id':'arrival-exchange','name':'Archive Supply Quay','node':'QuayShelter_0','type':'market','position':[0,1.45,-3]})
    for i,(identity,x,z,y,angle) in enumerate(HOUSES):
        mesh=JC.terrace_house(seed+i,width=8,depth=6,storeys=1,material=SK.JADE_ASHLAR,
                             upper=SK.TIMBER,roof_material=SK.JADE_SCALE,trim=SK.GILT,entrance_steps=True)
        for part in mesh.all_parts:
            if part.material=='verdant_mossy_stone':part.material=SK.MOSS_STONE
            elif part.material=='verdant_carved_jade':part.material=SK.JADE_ASHLAR
        p=POP._add(build,'House_'+identity,'House_'+identity,mesh,(x,y,z),angle,kind='building',collides=True)
        p.extras={'solidRects':[[-4.2,-3.2,4.2,3.2]]}
    for i,(x,z,angle) in enumerate([(223,4,0),(-34,33,0),(3,69,math.pi/2)]):
        POP._add(build,f'MooredPunt_{i}','MooredPunt',PROP.rowing_boat(length=5.5,beam_width=1.8,seed=seed+3400),(x,.03,z),angle,kind='prop')
    for i,(x,z) in enumerate([(-16,-6),(-16,-4),(17,-8),(185,5),(185,7),(13,92)]):
        POP._add(build,f'QuayCargo_{i}','QuayCargo',PROP.crate(size=.9,seed=seed+3500),(x,float(t.height_at(x,z)),z),kind='prop',collides=True)
    build.notes.append('384m drowned city: six inhabited court houses, protected monumental temple, surveyed channel bridges, working jetties and a connected northern inlet.')

def seat_secrets(build):
    for record in build.interactives:
        identity=record.get('secret')
        if identity not in SECRET_SITES:continue
        x,z=SECRET_SITES[identity];y=float(build.terrain.height_at(x,z))
        node='Secret_'+identity.replace('-','_')
        for p in build.placements:
            if p.node==node:p.position=(x,y-.05,z)
        record['position']=[x,y,z]
        record['serverTile']=[int(x+REG.SERVER_ORIGIN[0]+2),int(REG.SERVER_ORIGIN[1]-z)]

def dress_cistern(build,seed):
    import populate as POP
    mesh=CIV.sounding_stage(stone=SK.JADE_ASHLAR,timber=SK.TIMBER,foot=-5)
    p=POP._add(build,'CisternShaft','CisternShaft',mesh,(CISTERN[0],2.,CISTERN[1]),kind='landmark',collides=True,landmark='cistern-shaft')
    p.extras={'solidRadius':2.2}

def clear_routes(build):
    lines=[[[float(x),0,float(z)] for x,z in points] for points in REG.street_routes().values()]
    lines += [[[float(x),0,float(z)] for x,z in points] for points,heights,width in ROADS.values()]
    lines += [[[float(x),0,float(z)] for x,z in data[0]] for data in build.terrain._survey.values()]
    RC.clear_walk_corridors(build,lines,{'tree':5.,'foliage':4.5,'prop':2.5})
    # Legacy horizontal kerbs were anchored once and crossed hills/stair
    # corridors as long floating blades. Bridges retain their surveyed rails.
    build.placements=[p for p in build.placements if not p.node.startswith('Kerb_')]
    kept=[]
    for p in build.placements:
        if p.node.startswith(('DrownedColumn_','DrownedRubble_')):
            if np.hypot(p.position[0]+75,p.position[2]+50)<10:continue
        kept.append(p)
    build.placements=kept

def seat_marches(build,report):
    # The universal roadside offsets put stones in this valley's water. Its
    # route markers belong at the inhabited shore stations, before the bridges.
    sites={'north_stair':(176.,-196.),'east_causeway':(198.,-72.),
           'west_causeway':(-91.,-104.),'south_gate':(13.,90.)}
    for p in build.placements:
        for identity,(x,z) in sites.items():
            if p.node!=f'March_{identity}_Stone':continue
            y=float(build.terrain.height_at(x,z));p.position=(x,y-.05,z)
            for mark in report.landmarks:
                if mark.get('node')==p.node:mark['position']=[x,y,z]

def solid_records(build):
    out=[]
    for p in build.placements:
        if p.node.startswith('StreamView_'):continue
        c,s=math.cos(p.rotation_y),math.sin(p.rotation_y)
        for i,(x0,z0,x1,z1) in enumerate((p.extras or {}).get('solidRects',[])):
            corners=np.array([(x,z) for x in (x0,x1) for z in (z0,z1)])*p.scale
            xx=c*corners[:,0]+s*corners[:,1]+p.position[0]
            zz=-s*corners[:,0]+c*corners[:,1]+p.position[2]
            out.append({'id':f'authored-{p.node}-{i}','node':p.node,'type':'authored-solid',
                        'box':[float(xx.min()),float(zz.min()),float(xx.max()),float(zz.max())],
                        'marginMetres':0,'cellsBlocked':0})
    return out


def clear_causeway_canopies(build):
    kept=[]
    for p in build.placements:
        if p.node.startswith('StreamView_') or p.kind not in ('tree','foliage'):
            kept.append(p);continue
        lo,hi=build.meshes[p.mesh].bounds()
        radius=max(abs(lo[0]),abs(hi[0]),abs(lo[2]),abs(hi[2]))*p.scale
        x,_,z=p.position
        north=z-radius<-208 and abs(x-154.5)<radius+5
        east=x+radius>215 and abs(z+88.5)<radius+5
        if not (north or east):kept.append(p)
    build.placements=kept
    live={p.node for p in kept}|set(build.terrain_meshes)|set(build.water_meshes)
    for frame in getattr(build,'streaming_borders',[]):
        frame['sceneNodes']=[name for name in frame.get('sceneNodes',[]) if name in live]
