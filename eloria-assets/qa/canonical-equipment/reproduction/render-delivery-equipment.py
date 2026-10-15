from pathlib import Path
import json,sys,time,subprocess,shutil
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
SNAP=json.loads((ROOT/'equipment-fit-build/in/canonical-fitted-source-snapshot/manifest.json').read_text())
FINAL=dict(SNAP,**{'torso_remap.py':r.digest(ROOT/'equipment-fit-build/in/outer-sleeve-proposal.py')})
BASE=ROOT/'equipment-fit-build/out/canonical-fitted';TORSOS=ROOT/'equipment-fit-build/out/canonical-sleeves'
HEADS=ROOT/'equipment-fit-build/out/canonical-eyes'
HEAD_CODES=dict(FINAL,**{'limb_head_remap.py':r.digest(ROOT/'equipment-fit-build/in/eye-brow-proposal.py')})

def registry(race):
    while len(list((BASE/race).glob('*.fit.json')))!=264 or len(list((TORSOS/race).glob('*.fit.json')))!=64 or len(list((HEADS/race).glob('*.fit.json')))!=64:time.sleep(15)
    reg=r.prepare_registry(json.loads((ROOT/'godot-client/data/actors/equipment.json').read_text()),json.loads((ROOT/'equipment-fit-build/reports/body-measurements.json').read_text()))
    reg['fitGroups'][race]=['canonical_'+race]
    for folder,codes in [(BASE/race,SNAP),(TORSOS/race,FINAL),(HEADS/race,HEAD_CODES)]:
        for path in folder.glob('*.fit.json'):
            row=json.loads(path.read_text());assert row['tool_sha256']==codes
            assert r.digest(path.with_suffix('').with_suffix('.glb'))==row['asset_sha256']
            reg['models'][row['key']].setdefault('variants',{})['canonical_'+race]=row['variant']
    target=ROOT/f'equipment-fit-build/in/final-preview-{race}.json'
    data=(json.dumps(reg,indent=2)+'\n').encode()
    if target.exists():assert target.read_bytes()==data
    else:
        with target.open('xb') as f:f.write(data)
    return target

def capture(race,reg,prefix,outfit,clips,angles,cycles=False):
    args=[shutil.which('pwsh'),'-NoProfile','-File','eloria-assets/tools/capture_canonical_equipment.ps1','-Slugs',race,'-Prefix',prefix,'-Equipment',str(reg),'-Outfit',outfit,'-Clips',clips,'-Angles',angles]
    if cycles:args+=['-Cycles']
    subprocess.run(args,check=True)

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='gameplay':
        for race in ['glasswarden_female','glasswarden_male','luminous_male','luminous_female','mycelari_male','mycelari_female','ssarathi_male','ssarathi_female']:
            reg=registry(race)
            capture(race,reg,'final-militia','0:114,3:133,4:219,5:208,6:248','Rest_Pose,Idle_Subtle,Walk,Jog,Run_Female,Fighting_Idle','front,side',True)
            capture(race,reg,'final-militia','0:114,3:133,4:219,5:208,6:248','Run_Female','gameplay')
            print('GAMEPLAY',race,flush=True)
    elif mode=='catalogue':
        race='glasswarden_female';reg=registry(race)
        for piece in r.batch.roster():
            if piece.part!=5:continue
            capture(race,reg,'final-catalogue-'+piece.slug,f'5:{piece.visual}','Idle_Subtle','front')
            print('CATALOGUE',piece.slug,flush=True)
    elif mode=='headwear':
        for race in sorted(json.loads((ROOT/'equipment-fit-build/reports/body-measurements.json').read_text())):
            reg=registry(race)
            for label,head,style in [('hood',133,3),('rootwrap',119,3),('sunband',170,0)]:
                args=[shutil.which('pwsh'),'-NoProfile','-File','eloria-assets/tools/capture_canonical_equipment.ps1','-Slugs',race,'-Prefix',f'final-head-{label}-style{style}','-Equipment',str(reg),'-Outfit',f'3:{head},5:208','-Style',str(style),'-Clips','Idle_Subtle','-Angles','front,side']
                subprocess.run(args,check=True)
            print('HEADWEAR',race,flush=True)
    elif mode=='blender':
        roster={f'{p.part}:{p.visual}':p for p in r.batch.roster()}
        sets={'militia':['3:133','4:219','5:208','6:248'],'phoenix':['3:125','4:195','5:192','6:107'],'amberwood04':['3:120','4:174','5:187','6:203']}
        for race in ['luminous_male','luminous_female']:
            reg=registry(race)
            for name,keys in sets.items():
                paths=[(TORSOS if k.startswith('5:') else HEADS if k.startswith('3:') else BASE)/race/(roster[k].slug+'.glb') for k in keys]
                subprocess.run([sys.executable,'eloria-assets/tools/compare_conformed_piece.py',*[str(p) for p in paths],'--out',f'equipment-fit-build/preview/final-{name}-{race}-complete.png','--ensemble','--save-blend','--width','1000','--worn',f'godot-client/assets/actors/native/races/{race}.glb','--worn-pose','source','--equipment',str(reg)],check=True)
                print('ENSEMBLE',race,name,flush=True)
            if race=='luminous_male':
                for key in ['5:192','5:228','5:187']:
                    piece=roster[key]
                    subprocess.run([sys.executable,'eloria-assets/tools/compare_conformed_piece.py',str(TORSOS/race/(piece.slug+'.glb')),str(piece.source.with_name(piece.source.name+'.orig')),'--out',f'equipment-fit-build/preview/final-{piece.slug}-source.png','--save-blend','--width','1000','--worn',f'godot-client/assets/actors/native/races/{race}.glb','--equipment',str(reg)],check=True)
                    print('SOURCE',piece.slug,flush=True)
