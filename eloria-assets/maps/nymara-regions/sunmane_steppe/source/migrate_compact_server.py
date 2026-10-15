"""One-time local Sunmane workplace migration, guarded by a source revision.

Ordinary posts follow a nearby relocated workplace. The central camp keeps its
native scale; global coordinate scaling never changes a building or yard.
"""
import argparse,json,sys
from pathlib import Path
SOURCE=Path(__file__).resolve().parent
sys.path[:0]=[str(SOURCE),str(SOURCE.parents[1]/'_toolkit')]
import landscape_plan as P

def migration_field():
    import settlement
    return P.relocate_layout(settlement.compose_layout(None))

def convert(point,moves):
    x,z=P.remap_world(float(point[0])-58,58-float(point[1]),moves)
    return P.tile(x,z)

def migrate(server):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria';path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    key='sunmane_steppe_landscape_revision'
    if data.get(key)==P.REVISION:
        print('Sunmane migration already applied');return
    moves=migration_field();rules=dict(R.COORDINATE_FIELDS)
    rules['interactives.txt']=((None,0,2,3),)
    rules['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    count=0
    for filename,specs in rules.items():
        p=profile/filename
        if not p.is_file():continue
        rows=[]
        for line in p.read_text(encoding='utf-8').splitlines():
            fields=line.split('|')
            for word,mi,xi,yi in specs:
                if len(fields)<=max(mi,xi,yi) or not R._matches(word,fields):continue
                if fields[mi].strip()!='sunmane_steppe':continue
                x,y=convert((int(fields[xi]),int(fields[yi])),moves)
                fields[xi]=R.set_field(fields[xi],x);fields[yi]=R.set_field(fields[yi],y);count+=1
            rows.append('|'.join(fields))
        p.write_text('\n'.join(rows)+'\n',encoding='utf-8')
    def follow(value):
        if isinstance(value,list):return [follow(e) for e in value]
        if not isinstance(value,dict):return value
        return {k:convert(v,moves) if k in ('serverTile','server_tile','arrival')
                and isinstance(v,list) and len(v)==2 else follow(v) for k,v in value.items()}
    for name in ('sunmane_npcs','sunmane_resources','sunmane_steppe_npcs','sunmane_steppe_harvestables'):
        if name in data:data[name]=follow(data[name])
    for item in data.get('maps',[]):
        if item.get('id')=='sunmane_steppe':
            item.update(follow(item));item.update(server_cells=384,arrival=list(P.ARRIVAL))
    data[key]=P.REVISION
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(f'Sunmane migration applied to {count} coordinate posts.')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server',required=True,type=Path);ap.add_argument('--apply',action='store_true')
    a=ap.parse_args()
    if a.apply:migrate(a.server.resolve())
    else:print('384 cells; origin116; arrival137,95. Pass --apply to migrate the profile once.')
