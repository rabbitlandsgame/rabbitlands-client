"""Revision-guarded Mirrorhold coordinate migration, before contract generation.

The default is a read-only report. Integration uses migrate(server, apply=True).
This preserves IDs, destinations, spawn types, dialogue and content quantities;
the service layout in world.json then supplies the final civic posts.
"""
from pathlib import Path
import argparse
import json
import sys
sys.path[:0]=[str(Path(__file__).resolve().parent),
             str(Path(__file__).resolve().parents[2]/'_toolkit')]
from landscape_plan import PLAN,REVISION


def migrate(server,apply=False):
    server=Path(server).resolve()
    sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria';manifest_path=profile/'client_content_manifest.json'
    data=json.loads(manifest_path.read_text(encoding='utf-8'))
    if data.get('mirrorhold_landscape_revision')==REVISION:
        return {'revision':REVISION,'alreadyApplied':True,'changes':[]}
    rules_by_file=dict(R.COORDINATE_FIELDS)
    rules_by_file['interactives.txt']=((None,0,2,3),)
    rules_by_file['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    pending=[];changes=[]
    for filename,rules in rules_by_file.items():
        path=profile/filename
        if not path.exists():continue
        original=path.read_bytes();rows=[]
        for number,line in enumerate(original.decode('utf-8').splitlines(),1):
            fields=line.split('|')
            for keyword,mi,xi,yi in rules:
                if len(fields)<=max(mi,xi,yi) or not R._matches(keyword,fields):continue
                if fields[mi].strip()!='mirrorhold':continue
                old=(int(fields[xi]),int(fields[yi]));new=PLAN.tile(old)
                fields[xi]=R.set_field(fields[xi],new[0]);fields[yi]=R.set_field(fields[yi],new[1])
                changes.append({'file':filename,'line':number,'from':old,'to':new})
            rows.append('|'.join(fields))
        newline='\r\n' if b'\r\n' in original else '\n'
        pending.append((path,(newline.join(rows)+newline).encode('utf-8')))
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:PLAN.tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('mirrorhold_npcs','mirrorhold_harvestables'):
        if key in data:data[key]=follow(data[key])
    for entry in data.get('maps',[]):
        if entry.get('id')=='mirrorhold':
            entry.update(follow(entry));entry['server_cells']=384
            entry['arrival']=PLAN.tile((174,174))
    data['mirrorhold_landscape_revision']=REVISION
    pending.append((manifest_path,(json.dumps(data,indent=2)+'\n').encode('utf-8')))
    if apply:
        for path,payload in pending:
            if path.read_bytes()!=payload:path.write_bytes(payload)
    return {'revision':REVISION,'applied':apply,'changes':changes}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    print(json.dumps(migrate(args.server,args.apply),indent=2))
