"""Author Stillglass and its matching server/client walk grids."""
from pathlib import Path
import gzip
import json
import random
import struct
import sys

CLIENT = Path(__file__).resolve().parents[1]
SERVER = CLIENT.parent / 'dev-server'
sys.path.insert(0, str(CLIENT / 'prototypes/last-lantern'))
from build_map import GLB
from art_authoring import palette, torus, rod

SIZE = 120
OUT = CLIENT / 'eloria-assets/maps/stillglass'
ROOMS = [(42,43,78,77),(43,87,77,115),(89,44,115,77),(42,5,78,33),(5,43,31,77)]
GATES = [dict(id=n,at=at,bounds=b,requires=n,rotation=r) for n,at,b,r in (
    ('north',[60,82],[56,81,64,83],0),('east',[84,60],[83,56,85,64],90),
    ('south',[60,38],[56,37,64,39],0),('west',[36,60],[35,56,37,64],90))]
def t(key,label,at,approach=None,oid=0,kind='location'):
    return dict(id=key,label=label,tile=list(at),approach=list(approach or at),objectId=oid,kind=kind)
TARGETS = [t('sera','Keeper Sera',(55,69),(55,67),kind='npc'),
    t('cache','Stillglass supply cabinet',(67,68),(65,67),7201,'storage'),
    t('lens','The great lens',(60,73),(60,70),7202,'information'),
    t('north','Glasshouse benches',(60,92)),t('fountain','Glasshouse fountain',(60,103)),
    t('east','Prism Yard approach',(91,60)),t('shelter','Prism shelter',(91,72)),
    t('south','Folded Walk',(60,32)),t('landing','The far landing',(60,21)),
    t('garden','Veiled garden',(69,14)),t('bench','Scrap and fittings',(48,14),(48,17),7203,'information'),
    t('west','Homeward Garden',(28,60)),t('rally','Safe rally point',(13,72)),
    t('return','Observatory portal',(44,12))]

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    g=GLB();m=palette(g);rng=random.Random(532);grid=bytearray(SIZE*SIZE)
    for x1,y1,x2,y2 in ROOMS+[(56,5,64,115),(5,56,115,64),(30,7,39,20)]:
        for y in range(y1,y2+1):
            for x in range(x1,x2+1):grid[y*SIZE+x]=13
    # A real gap and an isolated portal annex; both have visible landing floors.
    for y in range(24,27):
        for x in range(42,79):grid[y*SIZE+x]=0
    g.group='Scenery_Foundation';g.box('base',60,-1,-60,123,1,123,m['slate'])
    for y in range(SIZE):
        for x in range(SIZE):
            if not grid[y*SIZE+x]:continue
            g.group='Walk_Court';v=rng.uniform(.72,1)
            g.mesh('floor',[(x-.5,.4,-y+.5),(x+.5,.4,-y+.5),(x+.5,.4,-y-.5),(x-.5,.4,-y-.5)],
                   [(0,1,2),(0,2,3)],m['stone'],[(v,v,.98*v,1)]*4)
    g.group='Scenery_Walls'
    for y in range(1,SIZE-1):
        for x in range(1,SIZE-1):
            if grid[y*SIZE+x]:continue
            if any(grid[(y+dy)*SIZE+x+dx] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                if 24<=y<=26 and 43<=x<=77:continue
                g.box('wall',x,.95,-y,.92,1.1,.92,m['stone'])
                g.box('cap',x,1.55,-y,1,.16,1,m['brass'])
    for gate in GATES:
        x,y=gate['at'];rot=gate['rotation'];g.group='Scenery_Gate_'+gate['id']
        for sign in (-1,1):
            xx,yy=x+(0 if rot else sign*5),y+(sign*5 if rot else 0)
            g.cylinder('pillar',xx,2.1,-yy,.65,3.8,m['stone'],12)
            g.cylinder('cap',xx,4.1,-yy,.9,.25,m['brass'],12)
        g.box('arch',x,4.3,-y,1.3 if rot else 12,.4,12 if rot else 1.3,m['brass'])
    g.group='Scenery_Lens'
    for x in (58,62):g.box('plinth',x,1.7,-73,.55,2.6,.55,m['stone'])
    torus(g,'armillary',(60,3.1,-73),2.8,.11,m['brass'])
    rod(g,'axis',(57.5,2,-73),(62.5,4.6,-73),.09,m['brass'])
    g.cylinder('glass',60,3,-73,2.3,.1,m['water'],32)
    g.group='Scenery_Cabinet';g.box('cabinet',67,1.3,-68,2.6,1.8,1.3,m['wood'])
    for x in (66,68):g.box('bands',x,1.3,-68,.14,1.9,1.4,m['brass'])
    g.group='Scenery_Fountain';g.cylinder('basin',60,.65,-105,2.1,.6,m['stone'],24)
    g.cylinder('water',60,1,-105,1.8,.05,m['water'],24)
    g.group='Scenery_Glasshouse'
    for x in (45,75):
        for y in (94,111):g.box('rib',x,2.1,-y,.3,3.4,.3,m['brass'])
    g.group='Scenery_Prism'
    for x,y,mat in [(107,61,'brass'),(107,71,'water'),(108,49,'slate_light')]:
        g.cylinder('pedestal',x,.9,-y,.9,1,m['stone'],8)
        g.cylinder('crystal',x,2,-y,.7,1.4,m[mat],4,top=0)
    g.group='Scenery_Workbench';g.box('bench',48,1.1,-14,3,.3,1.5,m['wood'])
    for x in (47,49):g.box('leg',x,.65,-14,.2,1.1,.9,m['iron'])
    g.write(OUT/'world.glb')
    fine=bytearray()
    for y in range(SIZE):
        row=bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2));fine.extend(row+row)
    (OUT/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,240,240)+fine)
    (SERVER/'tools/collision/stillglass.escg.gz').write_bytes(gzip.compress(struct.pack('<4sHHI',b'ESCG',1,200,SIZE)+grid,mtime=0))
    layout=dict(id='stillglass',name='Stillglass Observatory',size=SIZE,spawn=[55,59],gates=GATES,targets=TARGETS,rooms=ROOMS,walkGrid=list(grid),heightOrigin=-2.2,heightStep=.2)
    for p in (OUT/'layout.json',SERVER/'config/eloria/stillglass.json'):p.write_text(json.dumps(layout,separators=(',',':'))+'\n')
    manifest=json.loads((CLIENT/'eloria-assets/maps/bellwatch/world.json').read_text())
    manifest['asset'].update(id='stillglass',name='Stillglass Observatory',serverCells=SIZE,
        bounds={'min':[-2,-2,-122],'max':[122,8,2]},playableBounds={'min':[-.5,.4,-119.5],'max':[119.5,.4,.5]},mapBounds={'min':[-2,-2,-122],'max':[122,8,2]})
    manifest['spawnPoints']=[dict(id='default',position=[55,.4,-59],rotationDegrees=0)]
    manifest['collision'].update(width=240,height=240)
    manifest['landmarks']=[dict(id=t['id'],name=t['label'],position=[t['tile'][0],.4,-t['tile'][1]]) for t in TARGETS]
    manifest['interactives']=[dict(id=t['id'],kind=t['kind'],objectId=t['objectId'],position=[t['tile'][0],.4,-t['tile'][1]],serverTile=t['tile'],approachTile=t['approach']) for t in TARGETS if t['objectId']]
    (OUT/'world.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for t in TARGETS:assert grid[t['approach'][1]*SIZE+t['approach'][0]],t
    print('Stillglass:',sum(bool(v) for v in grid),'walkable tiles')

if __name__=='__main__':build()
