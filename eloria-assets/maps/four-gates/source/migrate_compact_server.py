"""Guarded Four Gates migration; only the integration owner runs --apply.

Semantic posts override the protected radial fallback. Portal identities and
dialogue are preserved; shared continent tooling publishes final borders.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import landscape_plan as P

def tile(old):
    return P.to_tile(*P.remap_world(old[0]-360,360-old[1]))

def migrate(server,apply=False):
    server=Path(server).resolve();sys.path[:0]=[str(server/'tools'),str(server)]
    import relocate_map_content as R
    profile=server/'config/eloria';path=profile/'client_content_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('four_gates_landscape_revision')==P.REVISION:
        return {'revision':P.REVISION,'alreadyApplied':True,'changes':[]}
    rules=dict(R.COORDINATE_FIELDS)
    rules['interactives.txt']=((None,0,2,3),)
    rules['special_areas.txt']=(('area',2,3,4),('area',2,5,6))
    pending=[];changes=[]
    for filename,fieldspec in rules.items():
        file=profile/filename
        if not file.exists():continue
        original=file.read_bytes();rows=[]
        for number,line in enumerate(original.decode('utf-8').splitlines(),1):
            fields=line.split('|')
            for keyword,mi,xi,yi in fieldspec:
                if len(fields)<=max(mi,xi,yi) or not R._matches(keyword,fields):continue
                if fields[mi].strip()!='four_gates':continue
                old=(int(fields[xi]),int(fields[yi]));new=tile(old)
                if filename=='npcs.txt' and fields[1].strip() in P.NPC_POSTS:
                    new=P.to_tile(*P.NPC_POSTS[fields[1].strip()])
                fields[xi]=R.set_field(fields[xi],new[0]);fields[yi]=R.set_field(fields[yi],new[1])
                changes.append({'file':filename,'line':number,'from':old,'to':new})
            rows.append('|'.join(fields))
        newline='\r\n' if b'\r\n' in original else '\n'
        pending.append((file,(newline.join(rows)+'\n').encode('utf-8')))
    def follow(value):
        if isinstance(value,list):return [follow(v) for v in value]
        if not isinstance(value,dict):return value
        return {k:tile(v) if k in ('server_tile','serverTile','arrival') else follow(v)
                for k,v in value.items()}
    for key in ('four_gates_npcs','four_gates_resources','four_gates_harvestables'):
        if key in manifest:manifest[key]=follow(manifest[key])
    for entry in manifest.get('maps',[]):
        if entry.get('id')=='four_gates':
            entry.update(follow(entry));entry.update(server_cells=396,arrival=[198,143])
    manifest['four_gates_landscape_revision']=P.REVISION
    pending.append((path,(json.dumps(manifest,indent=2)+'\n').encode('utf-8')))
    if apply:
        for file,payload in pending:
            if file.read_bytes()!=payload:file.write_bytes(payload)
    return {'revision':P.REVISION,'applied':apply,'serverCells':396,
            'serverOrigin':[198,198],'arrival':[198,143],'changes':changes}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--server',required=True)
    p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(migrate(a.server,a.apply),indent=2))
