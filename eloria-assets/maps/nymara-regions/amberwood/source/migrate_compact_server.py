"""One-time migration of Amberwood posts, including portals returning from other maps.

Run before contract generation. The revision in client_content_manifest makes
repeating the complete build safe; no dimensions or local coordinates are scaled twice.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
from compact_plan import PLAN

def migrate(server):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria'
    path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text())
    if data.get('amberwood_landscape_revision')=='inhabited-384-v1':return
    spec=dict(R.COORDINATE_FIELDS)
    spec['interactives.txt']=((None,0,2,3),)
    spec['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    for filename,rules in spec.items():
        p=profile/filename
        if not p.exists():continue
        rows=[]
        for line in p.read_text().splitlines():
            fields=line.split('|')
            for keyword,mi,xi,yi in rules:
                if len(fields)<=max(mi,xi,yi) or not R._matches(keyword,fields):continue
                if fields[mi].strip()!='amberwood':continue
                x,y=PLAN.tile((int(fields[xi]),int(fields[yi])))
                fields[xi]=R.set_field(fields[xi],x);fields[yi]=R.set_field(fields[yi],y)
            rows.append('|'.join(fields))
        p.write_text('\n'.join(rows)+'\n')
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:PLAN.tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('amberwood_npcs','amberwood_harvestables'):
        data[key]=follow(data.get(key,[]))
    for entry in data.get('maps',[]):
        if entry.get('id')=='amberwood':
            entry.update(follow(entry));entry['server_cells']=384
    data['amberwood_landscape_revision']='inhabited-384-v1'
    path.write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':migrate(Path(sys.argv[1]).resolve())
