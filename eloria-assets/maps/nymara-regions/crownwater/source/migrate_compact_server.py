"""Revision-guarded Crownwater migration; only the coordinator applies it.

The helper preserves IDs, names and configured counts. One interior working
post is explicitly moved beside its doorway so the arrival and exit stay clear.
Neighbourhood-relative coordinates provide the initial seed. Afterwards the
normal authored content and portal publishers use the rebuilt world's exact
working posts, six ferry berths, seven interior doors and eastern seam frame.
"""
import argparse,json,math,sys
from pathlib import Path
from coastal_plan import map_tile,SERVER_CELLS,SERVER_ORIGIN,FERRIES

REVISION='inhabited-crownwater-396-v1'
KEY='crownwater_landscape_revision'
INTERIOR_WORKING_POSTS={'Drowned Chapel Verger Tomas Rill':('drowned_crown',45,277)}

def sync_interior_working_posts(server,apply=False):
    """Keep the verger beside the undercroft threshold, including on reruns."""
    path=server/'config/eloria/npcs.txt'
    rows=[];changes=[];found=set()
    for line in path.read_text().splitlines():
        fields=line.split('|')
        name=fields[1].strip() if len(fields)>5 and fields[0].strip()=='npc' else None
        if name in INTERIOR_WORKING_POSTS:
            map_id,x,y=INTERIOR_WORKING_POSTS[name]
            assert fields[2].strip()==map_id,(name,fields[2])
            before=[int(fields[3]),int(fields[4])];found.add(name)
            if before!=[x,y]:
                fields[3]=f' {x} ';fields[4]=f' {y} '
                line='|'.join(fields)
                changes.append({'name':name,'map':map_id,'before':before,'after':[x,y]})
        rows.append(line)
    assert found==set(INTERIOR_WORKING_POSTS),('Missing interior NPC',set(INTERIOR_WORKING_POSTS)-found)
    if apply and changes:path.write_text('\n'.join(rows)+'\n')
    return changes

def migrate(server,apply=False):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria'
    path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text())
    if data.get(KEY)==REVISION:
        return {'revision':REVISION,'alreadyApplied':True,'files':[],
                'interiorWorkingPosts':sync_interior_working_posts(server,apply)}
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
                if fields[mi].strip()!='crownwater':continue
                x,y=map_tile((int(fields[xi]),int(fields[yi])))
                fields[xi]=R.set_field(fields[xi],x);fields[yi]=R.set_field(fields[yi],y)
                changes+=1
            rows.append('|'.join(fields))
        if changes:
            pending.append((p,'\n'.join(rows)+'\n'))
            summary.append({'file':filename,'coordinatePairs':changes})
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:map_tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('crownwater_npcs','crownwater_harvestables'):
        if key in data:data[key]=follow(data[key])
    maps=data.setdefault('maps',[])
    entry=next((m for m in maps if m.get('id')=='crownwater'),None)
    if entry is None:entry={'id':'crownwater'};maps.append(entry)
    entry.update(follow(entry));entry.update(server_cells=SERVER_CELLS,arrival=[120,120])
    data[KEY]=REVISION
    if apply:
        for p,payload in pending:p.write_text(payload)
        path.write_text(json.dumps(data,indent=2)+'\n')
    interior_posts=sync_interior_working_posts(server,apply)
    return {'revision':REVISION,'applied':apply,'files':summary,'serverCells':396,
        'interiorWorkingPosts':interior_posts,
        'serverOrigin':[120,120],'arrival':[120,120],
        'surveyedPortalOverrides':{'east-quay':[391,130],**{k:[math.floor(end[0]+120),math.floor(120-end[1])]
            for k,(end,start,level) in FERRIES.items()}},
        'next':'Run scoped author_region_content, author_services and continent portals after collision publication. '
               'All ferry journeys and existing secret/interior IDs are retained.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server',type=Path,required=True);ap.add_argument('--apply',action='store_true')
    args=ap.parse_args();print(json.dumps(migrate(args.server.resolve(),args.apply),indent=2))
