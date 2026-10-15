"""Hash-checked installation of a reviewed shared-body/equipment candidate.

The plan lists every replacement and obsolete generated file. Installation only
writes those paths, never item definitions, and refuses concurrent modifications.
"""
from __future__ import annotations
import argparse,json,os,uuid
from pathlib import Path
import pack_canonical_equipment as pack


def sha_file(path):return pack.sha(path.read_bytes()) if path.is_file() else None

def safe(path):
    target=(pack.ROOT/path).resolve()
    if not target.is_relative_to(pack.ROOT.resolve()) or target.is_dir():raise ValueError(f'Unsafe target: {path}')
    return target

def plan(equipment,registry,bodies,reports,out):
    if out.exists():raise FileExistsError(out)
    em=json.loads(equipment.read_bytes());rm=json.loads(registry.read_bytes())
    parent=json.loads(Path(em['parent_manifest']).read_bytes())
    changes={};removals={}
    for path,spec in em['files'].items():
        src=equipment.parent/path;expected=parent['files'][path]['sha256']
        if sha_file(src)!=spec['sha256'] or sha_file(safe(path))!=expected:raise ValueError(f'Changed equipment: {path}')
        if expected!=spec['sha256']:changes[path]={'source':str(src.resolve()),'sha256':spec['sha256'],'expected':expected}
    for slug,digest in rm['bodies'].items():
        geo=json.loads((reports/(slug+'-geometry.json')).read_bytes())
        motion=json.loads((reports/(slug+'-replay.json')).read_bytes())
        if geo['errors'] or motion['errors'] or geo['candidateSHA256']!=digest or motion['sha256']!=digest:
            raise ValueError(f'Candidate audit failed: {slug}')
        path=f'godot-client/assets/actors/native/races/{slug}.glb';src=bodies/(slug+'.glb')
        if sha_file(src)!=digest or sha_file(safe(path))!=geo['sourceSHA256']:raise ValueError(f'Changed body: {slug}')
        if digest!=geo['sourceSHA256']:changes[path]={'source':str(src.resolve()),'sha256':digest,'expected':geo['sourceSHA256']}
    for path,digest in rm['outputs'].items():
        src=registry.parent/path
        if sha_file(src)!=digest or sha_file(safe(path))!=rm['inputs'][path]:raise ValueError(f'Changed metadata: {path}')
        changes[path]={'source':str(src.resolve()),'sha256':digest,'expected':rm['inputs'][path]}
    for path,spec in parent['files'].items():
        if path in em['files'] or not path.startswith(pack.PREFIX.as_posix()+'/'):continue
        if not (path.endswith('.glb') or '/textures/canonical_' in path):continue
        if sha_file(safe(path))!=spec['sha256']:raise ValueError(f'Obsolete file changed: {path}')
        removals[path]=spec['sha256']
    protected={p:h for p,h in parent['protected'].items() if p not in changes}
    for p,h in protected.items():
        if sha_file(safe(p))!=h:raise ValueError(f'Protected input changed: {p}')
    result={'replace':changes,'remove':removals,'protected':protected,
            'equipment_manifest_sha256':sha_file(equipment),'registry_manifest_sha256':sha_file(registry)}
    pack.new_file(out,(json.dumps(result,indent=2)+'\n').encode())
    print('PLAN',len(changes),'replacements',len(removals),'obsolete generated files',flush=True)
    return result


def install(path):
    raw=path.read_bytes();spec=json.loads(raw)
    # Preflight all destinations before the first write; repeat the check beside
    # each atomic replacement/deletion to catch another writer during install.
    for p,s in spec['replace'].items():
        if sha_file(safe(p))!=s['expected'] or sha_file(Path(s['source']))!=s['sha256']:raise ValueError(f'Changed replacement: {p}')
    for p,h in {**spec['remove'],**spec['protected']}.items():
        if sha_file(safe(p))!=h:raise ValueError(f'Changed input: {p}')
    for i,(p,s) in enumerate(spec['replace'].items()):
        target=safe(p);data=Path(s['source']).read_bytes()
        if pack.sha(data)!=s['sha256'] or sha_file(target)!=s['expected']:raise ValueError(f'Concurrent write: {p}')
        temporary=target.with_name(target.name+'.shared-'+uuid.uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:stream.write(data)
        if sha_file(target)!=s['expected']:
            temporary.unlink();raise ValueError(f'Concurrent write: {p}')
        os.replace(temporary,target)
        if sha_file(target)!=s['sha256']:raise ValueError(f'Installed hash differs: {p}')
        if (i+1)%200==0:print('INSTALL',i+1,flush=True)
    for p,h in spec['remove'].items():
        target=safe(p)
        if sha_file(target)!=h:raise ValueError(f'Concurrent write before removal: {p}')
        target.unlink()
    for p,h in spec['protected'].items():
        if sha_file(safe(p))!=h:raise ValueError(f'Protected input changed: {p}')
    if path.read_bytes()!=raw:raise ValueError('Install plan changed')
    pack.new_file(path.with_suffix('.installed.json'),(json.dumps({'plan_sha256':pack.sha(raw),'installed':len(spec['replace']),'removed':len(spec['remove'])},indent=2)+'\n').encode())
    print('INSTALLED',len(spec['replace']),'REMOVED',len(spec['remove']),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('command',choices=['plan','install'])
    ap.add_argument('--equipment',type=Path);ap.add_argument('--registry',type=Path);ap.add_argument('--bodies',type=Path);ap.add_argument('--reports',type=Path);ap.add_argument('--plan',type=Path,required=True)
    args=ap.parse_args()
    if args.command=='plan':plan(args.equipment,args.registry,args.bodies,args.reports,args.plan)
    else:install(args.plan)
