"""Six compact four-gate practice maps, with one source for art and collision."""
from pathlib import Path
import gzip
import json
import random
import struct
import sys

CLIENT = Path(__file__).resolve().parents[1]
SERVER = CLIENT.parent / 'dev-server'
sys.path.insert(0, str(SERVER))
sys.path.insert(0, str(CLIENT / 'prototypes/last-lantern'))
from eloria.road_lessons import ADVENTURES
from build_map import GLB
from art_authoring import palette, torus
from build_stillglass import GATES, ROOMS, t, SIZE


def build(key, adventure):
    mid = adventure['map']; out = CLIENT/'eloria-assets/maps'/mid
    out.mkdir(parents=True, exist_ok=True)
    targets = [t('guide', adventure['guide'], (55,69),(55,67),kind='npc'),
        t('cache','Practice supply cabinet',(67,68),(65,67),7301,'storage'),
        t('north','North approach',(60,92)),t('east','East approach',(93,60)),
        t('south','South approach',(60,28)),t('west','West approach',(27,60)),
        t('merchant','Practice merchant',(64,100),(64,97),kind='npc'),
        t('partner','Practice partner',(65,65),(63,65),kind='npc'),
        t('second','Bran',(74,60),(72,60),kind='npc'),
        t('rival','Practice prism',(106,60),(100,60),kind='npc'),
        t('enemy','Road opponent',(101,65),(96,65),kind='npc'),
        t('ore','Iron Ore',(50,98),(50,96),7310,'harvestable'),
        t('coal','Deep Coal',(70,98),(70,96),7311,'harvestable'),
        t('fork','East fork gate',(84,60),(81,60),7320,'gate'),
        t('fork_west','West fork gate',(36,60),(39,60),7321,'gate'),
        t('cache_reward','Individual reward cache',(60,19),(60,22),7322,'cache'),
        t('waystone','Return waystone',(60,55),(60,57),7323,'waystone')]
    for direction,at,approach in [('north',(60,108),(60,105)),('east',(109,60),(106,58)),('south',(60,12),(60,15)),('west',(12,60),(15,60))]:
        labels = {'summoning':'Wagon latch','crafting':'Workshop dispatch','builds':'Traveler dispatch',
            'equipment':'Rescue dispatch','trading':'Commission desk','parties':'Road post'}
        targets.append(t(direction+'_object',direction.title()+' '+labels[key],at,approach,7302+len(targets)-17,'information'))
    if key == 'crafting':
        from build_cinderbank import build as build_workshop
        build_workshop(adventure, targets)
        return
    if key == 'summoning':
        from build_reedway import build as build_caravan
        build_caravan(adventure, targets)
        return
    grid=bytearray(SIZE*SIZE)
    for x1,y1,x2,y2 in ROOMS+[(56,5,64,115),(5,56,115,64)]:
        for y in range(y1,y2+1):
            for x in range(x1,x2+1):grid[y*SIZE+x]=13
    g=GLB();m=palette(g);rng=random.Random(mid)
    g.group='Scenery_Foundation';g.box('foundation',60,-1,-60,123,1,123,m['slate'])
    tint=tuple(int(adventure['colors'][0][i:i+2],16)/255 for i in (0,2,4))
    for y in range(SIZE):
        for x in range(SIZE):
            if grid[y*SIZE+x]:
                g.group='Walk_Court';v=rng.uniform(.8,1.15)
                g.mesh('paving',[(x-.5,.4,-y+.5),(x+.5,.4,-y+.5),(x+.5,.4,-y-.5),(x-.5,.4,-y-.5)],[(0,1,2),(0,2,3)],m['stone'],[(*[min(1,c*v) for c in tint],1)]*4)
            elif 0<x<SIZE-1 and 0<y<SIZE-1 and any(grid[(y+dy)*SIZE+x+dx] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                g.group='Scenery_Walls';g.box('wall',x,1,-y,.95,1.2,.95,m['stone'])
                g.box('coping',x,1.7,-y,1.1,.2,1.1,m['brass'])
    for gate in GATES:
        x,y=gate['at'];rot=gate['rotation'];g.group='Scenery_Gate_'+gate['id']
        for sign in (-1,1):
            xx,yy=x+(0 if rot else sign*5),y+(sign*5 if rot else 0)
            g.cylinder('pillar',xx,2.1,-yy,.7,3.8,m['stone'],12)
            g.cylinder('lamp',xx,4.2,-yy,.4,.6,m['brass'],8)
        g.box('arch',x,4.5,-y,1.3 if rot else 12,.45,12 if rot else 1.3,m['wood'])
    for target in targets:
        x,y=target['tile'];oid=target['objectId'];g.group='Scenery_'+target['id']
        if target['kind'] in ('storage','cache'):
            g.box('chest',x,1.1,-y,2.6,1.4,1.4,m['wood'])
            for dx in (-.8,.8):g.box('band',x+dx,1.1,-y,.15,1.5,1.5,m['brass'])
        elif target['kind']=='harvestable':
            for dx,dy,h in [(-.6,0,1.1),(.6,.3,1.5),(0,-.4,.9)]:
                g.cylinder('vein',x+dx,.4+h/2,-y-dy,.7,h,m['iron' if target['id']=='ore' else 'slate'],5,top=.2)
        elif target['kind']=='information':
            if key=='summoning':
                g.box('wagon',x,1.6,-y,3,.8,2,m['wood'])
                for dx in (-1,1):
                    for dy in (-1,1):g.cylinder('wheel',x+dx,.9,-y+dy,.55,.3,m['iron'],12)
            elif key=='builds':
                torus(g,'echo',(x,2,-y),1.2,.12,m['brass'])
                g.cylinder('pedestal',x,.9,-y,1,.9,m['stone'],8)
            else:
                g.box('desk',x,1.2,-y,3,.35,1.6,m['wood'])
                for dx in (-1,1):g.box('leg',x+dx,.75,-y,.3,1.3,1.4,m['iron'])
        elif target['id']=='waystone':
            g.cylinder('waystone',x,1.8,-y,.75,2.8,m['water'],6,top=.2)
    g.write(out/'world.glb')
    fine=bytearray()
    for y in range(SIZE):
        row=bytes(v for v in grid[y*SIZE:(y+1)*SIZE] for _ in range(2));fine.extend(row+row)
    (out/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,SIZE*2,SIZE*2)+fine)
    (SERVER/'tools/collision'/f'{mid}.escg.gz').write_bytes(gzip.compress(struct.pack('<4sHHI',b'ESCG',1,200,SIZE)+grid,mtime=0))
    layout=dict(id=mid,name=adventure['name'],size=SIZE,spawn=[55,59],gates=GATES,targets=targets,rooms=ROOMS,walkGrid=list(grid),heightOrigin=-2.2,heightStep=.2)
    for path in (out/'layout.json',SERVER/'config/eloria'/f'{mid}.json'):path.write_text(json.dumps(layout,separators=(',',':'))+'\n')
    manifest=json.loads((CLIENT/'eloria-assets/maps/stillglass/world.json').read_text())
    manifest['asset'].update(id=mid,name=adventure['name'])
    manifest['landmarks']=[dict(id=t['id'],name=t['label'],position=[t['tile'][0],.4,-t['tile'][1]]) for t in targets]
    manifest['interactives']=[dict(id=t['id'],kind=t['kind'],objectId=t['objectId'],position=[t['tile'][0],.4,-t['tile'][1]],serverTile=t['tile'],approachTile=t['approach'],resource='Iron Ore' if t['id']=='ore' else 'Deep Coal' if t['id']=='coal' else '') for t in targets if t['objectId']]
    (out/'world.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert len({t['objectId'] for t in targets if t['objectId']})==len([t for t in targets if t['objectId']])
    for target in targets:assert grid[target['approach'][1]*SIZE+target['approach'][0]]
    print(mid, sum(bool(v) for v in grid),'walkable tiles')

if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adventure', choices=ADVENTURES)
    args = parser.parse_args()
    for key,adventure in ADVENTURES.items():
        if args.adventure is None or args.adventure == key:build(key,adventure)
