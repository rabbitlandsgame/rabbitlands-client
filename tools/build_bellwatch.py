"""Build the native Bellwatch map and both collision grids from one layout."""
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
from art_authoring import palette, rod, torus, pebble, TEXTURES

SIZE = 144
OUT = CLIENT / 'eloria-assets/maps/bellwatch'
ROOMS = [(52,54,92,90),(56,102,88,134),(111,58,136,86),
         (55,9,89,40),(7,58,35,86)]
GATES = [
    {'id':'north','at':[72,95],'bounds':[67,94,77,96],'requires':'north'},
    {'id':'east','at':[104,72],'bounds':[103,67,105,77],'requires':'east','rotation':90},
    {'id':'south','at':[72,46],'bounds':[67,45,77,47],'requires':'south'},
    {'id':'west','at':[44,72],'bounds':[43,67,45,77],'requires':'west','rotation':90},
]

def target(key,label,kind,at,approach,oid=0):
    return dict(id=key,label=label,kind=kind,tile=list(at),approach=list(approach),objectId=oid)

TARGETS = [
    target('nesh','Wayfinder Nesh','npc',(68,78),(68,76)),
    target('cache','Bellwatch supply chest','storage',(79,78),(77,77),7101),
    target('bell','The second bell','information',(72,85),(72,83),7102),
    target('cart','The waiting cart','information',(59,72),(62,72),7103),
    target('winch','Mill breach winch','information',(132,82),(130,81),7104),
    target('lookout','Orchard lookout','location',(72,102),(72,102)),
    target('east_landing','Mill approach','location',(109,72),(109,72)),
    target('refuge','Bell Court refuge','location',(89,72),(89,72)),
    target('south_landing','Muster firing position','location',(72,42),(72,42)),
    target('boss_approach','Captain overlook','location',(72,40),(72,40)),
    target('road','Departure road','location',(34,72),(34,72)),
]

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    g=GLB();m=palette(g);rng=random.Random(531)
    m['field']=g.material('Bellwatch meadow',(.23,.32,.16),
        texture=TEXTURES/'ground-basecolor.png',normal=TEXTURES/'ground-normal.png',uv_scale=.24)
    m['road']=g.material('Bellwatch packed road',(.48,.40,.27),
        texture=TEXTURES/'ground-basecolor.png',normal=TEXTURES/'ground-normal.png',uv_scale=.24)
    grid=bytearray(SIZE*SIZE)
    for x1,y1,x2,y2 in ROOMS+[(67,9,77,134),(7,67,136,77)]:
        for y in range(y1,y2+1):
            for x in range(x1,x2+1):grid[y*SIZE+x]=13
    g.group='Scenery_Landscape'
    g.box('earth',72,-.7,-72,154,1,154,m['field'])
    for y in range(SIZE):
        for x in range(SIZE):
            if not grid[y*SIZE+x]:continue
            g.group='Walk_Court' if 52<=x<=92 and 54<=y<=90 else 'Walk_Road'
            tint=rng.uniform(.8,1.02)
            g.mesh('tile',[(x-.5,.4,-y+.5),(x+.5,.4,-y+.5),
                           (x+.5,.4,-y-.5),(x-.5,.4,-y-.5)],[(0,1,2),(0,2,3)],
                   m['stone'] if g.group=='Walk_Court' else m['road'],[(tint,tint,tint,1)]*4)
    # Low perimeter walls sit outside the walk surface, with open connectors.
    g.group='Scenery_Walls'
    for y in range(1,SIZE-1):
        for x in range(1,SIZE-1):
            if grid[y*SIZE+x]:continue
            if any(grid[(y+dy)*SIZE+x+dx] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                g.box('stone',x,.7,-y,.95,1.4,.95,m['stone'])
                g.box('cap',x,1.45,-y,1.02,.15,1.02,m['slate_light'])
    # Four gates use the exact same gap and rotation as their collision spans.
    for gate in GATES:
        x,y=gate['at'];vertical=bool(gate.get('rotation'))
        g.group='Scenery_'+gate['id']
        for sign in (-1,1):
            px,py=x+(0 if vertical else sign*6),y+(sign*6 if vertical else 0)
            g.box('pier',px,2,-py,1.8,4,1.8,m['stone'])
            g.box('cap',px,4.1,-py,2.1,.3,2.1,m['slate'])
        g.box('lintel',x,4,-y,1.2 if vertical else 14,1,14 if vertical else 1.2,m['wood'])
    g.group='Scenery_Storage'
    g.box('chest',79,.95,-78,2.6,1.1,1.5,m['wood'])
    for x in (78,80):g.box('band',x,1,-78,.15,1.2,1.65,m['iron'])
    g.group='Scenery_Bell'
    for x in (70.7,73.3):g.box('post',x,2.9,-85,.3,5,.3,m['wood'])
    g.box('beam',72,5.3,-85,3.3,.35,.5,m['wood'])
    g.cylinder('bell',72,3.9,-85,.9,1.25,m['brass'],24,top=.45)
    torus(g,'rim',(72,3.3,-85),.9,.08,m['brass'])
    rod(g,'rope',(72,3.8,-85),(72,.9,-84.6),.045,m['rope'])
    g.group='Scenery_Winch'
    for y in (81.5,82.5):g.box('post',132,1.2,-y,.3,1.6,.3,m['wood'])
    rod(g,'drum',(132,1.7,-81.4),(132,1.7,-82.6),.35,m['wood'])
    g.box('handle',132,1.7,-81.3,1.4,.13,.13,m['iron'])
    # Orchard and mill silhouettes dress the blocked areas, never the targets.
    for x,y in [(48,108),(49,119),(94,123),(94,109),(101,83),(111,95),(136,48)]:
        g.group='Scenery_Tree'
        g.cylinder('trunk',x,2,-y,.35,4,m['bark'])
        for at,rad in ((3,2.7),(4.4,2),(5.5,1.1)):
            g.cylinder('crown',x,at,-y,rad,2.8,m['needles'],10,top=0)
    g.group='Scenery_Mill'
    g.box('house',123,3,-94,10,6,8,m['stone'])
    g.box('roof',123,6.2,-94,11,.5,9,m['slate'])
    for _ in range(100):
        x,y=rng.randrange(3,141),rng.randrange(3,141)
        if any(grid[yy*SIZE+xx] for yy in range(max(0,y-2),min(SIZE,y+3)) for xx in range(max(0,x-2),min(SIZE,x+3))):continue
        g.group='Scenery_Rocks'
        pebble(g,'rock',(x,.1,-y),(.8,.5,.7),m['stone'],rng,rings=3,sides=6)
    g.write(OUT/'world.glb')
    fine=bytearray()
    for y in range(SIZE):
        row=bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2));fine.extend(row+row)
    (OUT/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,SIZE*2,SIZE*2)+fine)
    (SERVER/'tools/collision/bellwatch.escg.gz').write_bytes(gzip.compress(struct.pack('<4sHHI',b'ESCG',1,200,SIZE)+grid,mtime=0))
    layout=dict(id='bellwatch',name='Bellwatch',size=SIZE,spawn=[65,70],gates=GATES,
                targets=TARGETS,rooms=ROOMS,walkGrid=list(grid),heightOrigin=-2.2,heightStep=.2)
    for path in (OUT/'layout.json',SERVER/'config/eloria/bellwatch.json'):
        path.write_text(json.dumps(layout,separators=(',',':'))+'\n',encoding='utf-8')
    manifest=json.loads((CLIENT/'eloria-assets/maps/lantern-reach/world.json').read_text(encoding='utf-8'))
    manifest['assetVersion']='1.0.0'
    manifest['asset'].update(id='bellwatch',name='Bellwatch',serverCells=SIZE,
        bounds={'min':[-5,-2,-149],'max':[149,10,5]},
        playableBounds={'min':[-.5,.4,-143.5],'max':[143.5,.4,.5]},
        mapBounds={'min':[-2,-2,-146],'max':[146,10,2]})
    manifest['spawnPoints']=[dict(id='default',position=[65,.4,-70],rotationDegrees=0)]
    manifest['collision'].update(width=288,height=288)
    manifest['landmarks']=[dict(id=t['id'],name=t['label'],position=[t['tile'][0],.4,-t['tile'][1]]) for t in TARGETS]
    manifest['interactives']=[dict(id=t['id'],kind=t['kind'],objectId=t['objectId'],
        position=[t['tile'][0],.4,-t['tile'][1]],serverTile=t['tile'],approachTile=t['approach']) for t in TARGETS if t['objectId']]
    manifest.pop('draft',None)
    (OUT/'world.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    for t in TARGETS:
        x,y=t['approach'];assert grid[y*SIZE+x],t['id']
    print(f'Bellwatch: {sum(bool(x) for x in grid)} walkable tiles, four gates, {len(g.doc["nodes"])} mesh nodes.')

if __name__=='__main__':build()
