"""One-time migration of Westhaven posts, including portals returning from other maps.

Run before contract generation. The revision in client_content_manifest makes
repeating the complete build safe; no dimensions or local coordinates are scaled twice.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
import landscape_plan as PLAN

def place_customs_clerk(profile):
    """Keep the public arrival/exit clear on every publication.

    interiors.custom_house authors the collector at local (-2,0,3), combined
    world (38,0,33), which maps to server (33,232). The inherited profile put
    Perrit at the room-centre arrival (35,235), blocking the automatic exit.
    """
    path=profile/'npcs.txt'
    lines=path.read_text().splitlines()
    changed=False
    for index,line in enumerate(lines):
        fields=line.split('|')
        if (len(fields)>4 and fields[0].strip()=='npc'
                and fields[1].strip()=='Custom House Clerk Perrit Dole'
                and fields[2].strip()=='westhaven_insides'):
            if tuple(int(fields[i]) for i in (3,4))!=(33,232):
                fields[3]=' 33 ';fields[4]=' 232 '
                lines[index]='|'.join(fields);changed=True
    if changed:path.write_text('\n'.join(lines)+'\n')

def migrate(server):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria'
    place_customs_clerk(profile)
    path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text())
    if data.get('westhaven_landscape_revision')=='inhabited-harbour-396-v1':return
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
                if fields[mi].strip()!='westhaven':continue
                x,y=PLAN.tile((int(fields[xi]),int(fields[yi])))
                fields[xi]=R.set_field(fields[xi],x);fields[yi]=R.set_field(fields[yi],y)
            rows.append('|'.join(fields))
        p.write_text('\n'.join(rows)+'\n')
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:PLAN.tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('westhaven_npcs','westhaven_harvestables'):
        if key in data:data[key]=follow(data[key])
    for entry in data.get('maps',[]):
        if entry.get('id')=='westhaven':
            entry.update(follow(entry));entry['server_cells']=396;entry['arrival']=[120,172]
    data['westhaven_landscape_revision']='inhabited-harbour-396-v1'
    path.write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':migrate(Path(sys.argv[1]).resolve())
