from pathlib import Path
import json,sys,subprocess,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import import_generated_equipment as batch
out=ROOT/'equipment-fit-build/shared-bodies/preview/shared-16-blender';out.mkdir(exist_ok=False)
registry=ROOT/'godot-client/data/actors/equipment.json';reg=json.loads(registry.read_bytes())
roster={f'{p.part}:{p.visual}':p for p in batch.roster()}
sets={'militia':['3:133','4:219','5:208','6:248'],'phoenix':['3:125','4:195','5:192','6:107'],'amberwood04':['3:120','4:174','5:187','6:203']}
inputs={str(registry):hashlib.sha256(registry.read_bytes()).hexdigest()}
def scene(key,race):
    row=reg['models'][key]
    for group in reg['fitGroups'][race]:
        if group in row.get('variants',{}):return ROOT/'godot-client'/row['variants'][group]['scene'].removeprefix('res://')
    return ROOT/'godot-client'/row['scene'].removeprefix('res://')
def run(name,paths,body,ensemble):
    for p in [*paths,body]:inputs[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    cmd=[sys.executable,'eloria-assets/tools/compare_conformed_piece.py',*[str(p) for p in paths],'--out',str(out/(name+'.png')),'--save-blend','--width','900','--worn',str(body),'--worn-pose','source','--equipment',str(registry)]
    if ensemble:cmd+=['--ensemble']
    with (out/(name+'.log')).open('x') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=0x08000000)
    print(name,'OK',flush=True)
for race in ['luminous_male','luminous_female','ssarathi_male','ssarathi_female','mycelari_male','mycelari_female']:
    body=ROOT/f'godot-client/assets/actors/native/races/{race}.glb'
    for name,keys in sets.items():
        if not race.startswith('luminous_') and name!='militia':continue
        run(f'{race}-{name}-complete',[scene(k,race) for k in keys],body,True)
for key in ['5:192','5:228','5:187']:
    piece=roster[key];source=piece.source.with_name(piece.source.name+'.orig')
    run(piece.slug+'-source',[scene(key,'luminous_male'),source],ROOT/'godot-client/assets/actors/native/races/luminous_male.glb',False)
for path,digest in inputs.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
(out/'manifest.json').write_text(json.dumps({'inputs':inputs},indent=2)+'\n')
