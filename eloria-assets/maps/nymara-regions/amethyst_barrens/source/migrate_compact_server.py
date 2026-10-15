"""Revision-guarded coordinate migration for the 384m Amethyst Barrens.

Includes portals returning from other maps, live services/NPCs/resources and
stored content posts. Stable IDs, names, destinations and interior coordinates
remain intact. Run --apply only in the coordinating server checkout.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
from landscape_plan import PLAN, SERVER_CELLS, PORTALS, SERVER_ORIGIN
from streaming_borders import region_specs
import math

REVISION='inhabited-amethyst-384-v1'
KEY='amethyst_barrens_landscape_revision'


def migrate(server, apply=True):
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria'
    path=profile/'client_content_manifest.json'
    data=json.loads(path.read_text())
    if data.get(KEY)==REVISION:
        return {'revision':REVISION,'alreadyApplied':True,'files':[]}
    fieldspec=dict(R.COORDINATE_FIELDS)
    fieldspec['interactives.txt']=((None,0,2,3),)
    fieldspec['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    pending=[]
    summary=[]
    for filename,rules in fieldspec.items():
        p=profile/filename
        if not p.exists():continue
        rows=[]
        changes=0
        for line in p.read_text().splitlines():
            fields=line.split('|')
            for keyword,mi,xi,yi in rules:
                if len(fields)<=max(mi,xi,yi) or not R._matches(keyword,fields):continue
                if fields[mi].strip()!='amethyst_barrens':continue
                x,y=PLAN.tile((int(fields[xi]),int(fields[yi])))
                fields[xi]=R.set_field(fields[xi],x)
                fields[yi]=R.set_field(fields[yi],y)
                changes+=1
            rows.append('|'.join(fields))
        if changes:
            pending.append((p,'\n'.join(rows)+'\n'))
            summary.append({'file':filename,'coordinatePairs':changes})
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:PLAN.tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('amethyst_barrens_npcs','amethyst_barrens_harvestables'):
        if key in data:data[key]=follow(data[key])
    for entry in data.get('maps',[]):
        if entry.get('id')=='amethyst_barrens':
            entry.update(follow(entry))
            entry['server_cells']=SERVER_CELLS
            entry['arrival']=PLAN.tile((174,174))
    data[KEY]=REVISION
    if apply:
        for p,payload in pending:p.write_text(payload)
        path.write_text(json.dumps(data,indent=2)+'\n')
    return {'revision':REVISION,'alreadyApplied':False,'applied':apply,'files':summary,
            'arrival':PLAN.tile((174,174)),
            'surveyedPortalOverrides':{s['portal']:[math.floor(s['anchor'][0]+s['outward'][0]+SERVER_ORIGIN[0]),
                                                   math.floor(SERVER_ORIGIN[1]-s['anchor'][2]-s['outward'][1])]
                                       for s in region_specs('amethyst_barrens')},
            'next':'Regenerate continent portals and authored content from the rebuilt package; '
                   'north-pass and west-road use new road-end surveys rather than scaled inland markers.'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    print(json.dumps(migrate(args.server.resolve(),args.apply),indent=2))
