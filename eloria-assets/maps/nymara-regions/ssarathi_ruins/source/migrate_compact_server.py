"""Scoped, revision-guarded migration; the rollout coordinator applies it.

Travel is compressed to384m. The arrival quay, market, courts, temple/vault,
stela, cistern and root arch retain local offsets at their new neighbourhoods.
Names, IDs, counts and all interior coordinates remain intact. Exact NPC working
posts are explicit regional decisions; later content/portal publication grounds
them and supplies the surveyed border/door coordinates.
"""
import argparse,json,math,sys
from pathlib import Path

SOURCE=Path(__file__).resolve().parent
sys.path[:0]=[str(SOURCE.parents[1]/'_toolkit'),str(SOURCE)]
import layout as PLAN

REVISION='inhabited-ssarathi-384-v1'
KEY='ssarathi_ruins_landscape_revision'
NEIGHBOURHOODS=[((0,0),(0,0),24),((198,12),(146,20),31),
 ((60,-264),(40,-182),45),((60,-208.5),(64,-126.5),26),
 ((-48,-90),(-32,-60),33),((168,-78),(112,-52),40),
 ((234,66),(156,44),28),((186,-198),(140,-150),28),
 ((-102,-60),(-85,-44),20),((8,132),(8,92),24)]

def map_point(x,z):
    choices=[(math.dist((x,z),old),old,new,radius) for old,new,radius in NEIGHBOURHOODS]
    distance,old,new,radius=min(choices)
    if distance<=radius:return x-old[0]+new[0],z-old[1]+new[1]
    return x*2/3,z*2/3

def map_tile(tile):
    x,z=map_point(tile[0]-174,174-tile[1])
    return [max(0,min(383,int(round(x+116)))),max(0,min(383,int(round(116-z))))]

def migrate(server,apply=False):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria';path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text())
    if data.get(KEY)==REVISION:return {'revision':REVISION,'alreadyApplied':True,'files':[]}
    fieldspec=dict(R.COORDINATE_FIELDS)
    fieldspec['interactives.txt']=((None,0,2,3),)
    fieldspec['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    pending=[];summary=[]
    for filename,rules in fieldspec.items():
        p=profile/filename
        if not p.exists():continue
        rows=[];changes=0
        for line in p.read_text().splitlines():
            fields=line.split('|')
            for keyword,mi,xi,yi in rules:
                if len(fields)<=max(mi,xi,yi) or not R._matches(keyword,fields):continue
                if fields[mi].strip()!='ssarathi_ruins':continue
                x,y=map_tile((int(fields[xi]),int(fields[yi])))
                if filename=='npcs.txt' and fields[1].strip() in PLAN.CONTENT_LAYOUT['npcs']:
                    wx,_,wz=PLAN.CONTENT_LAYOUT['npcs'][fields[1].strip()]
                    x,y=int(round(wx+116)),int(round(116-wz))
                fields[xi]=R.set_field(fields[xi],x);fields[yi]=R.set_field(fields[yi],y);changes+=1
            rows.append('|'.join(fields))
        if changes:pending.append((p,'\n'.join(rows)+'\n'));summary.append({'file':filename,'coordinatePairs':changes})
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:map_tile(v) if k in ('server_tile','serverTile','arrival') else follow(v) for k,v in value.items()}
    for key in ('ssarathi_ruins_npcs','ssarathi_ruins_harvestables'):
        if key in data:data[key]=follow(data[key])
    maps=data.setdefault('maps',[]);entry=next((m for m in maps if m.get('id')=='ssarathi_ruins'),None)
    if entry is None:entry={'id':'ssarathi_ruins'};maps.append(entry)
    entry.update(follow(entry));entry.update(server_cells=384,arrival=[116,116]);data[KEY]=REVISION
    if apply:
        for p,payload in pending:p.write_text(payload)
        path.write_text(json.dumps(data,indent=2)+'\n')
    return {'revision':REVISION,'applied':apply,'files':summary,'serverCells':384,'serverOrigin':[116,116],
            'arrival':[116,116],'authoredNpcPosts':PLAN.CONTENT_LAYOUT['npcs'],
            'next':'Publish guarded collision, exact content posts, all four continent links and seven interior doors. Preserve gauntlet keeper/returns and every secret identity.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();print(json.dumps(migrate(args.server.resolve(),args.apply),indent=2))
