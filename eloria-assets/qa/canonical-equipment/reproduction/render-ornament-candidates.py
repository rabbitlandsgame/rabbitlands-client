from pathlib import Path
import sys,json,subprocess,shutil
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
OUT=ROOT/'equipment-fit-build/out/canonical-ornaments'
registry=json.loads((OUT/'equipment.json').read_text())
rows=json.loads((ROOT/'equipment-fit-build/reports/canonical-ornaments-fit.json').read_text())
for row in rows:assert r.digest(OUT/row['race']/(row['slug']+'.glb'))==row['asset_sha256']
piece=next(p for p in r.batch.roster() if p.slug=='militia_torso_armor_03')

if __name__=='__main__':
    for race in ['glasswarden_female','luminous_male','luminous_female','ssarathi_male','mycelari_female']:
        reg=json.loads(json.dumps(registry));reg['fitGroups'][race]=['canonical_'+race]
        target=ROOT/f'equipment-fit-build/in/ornament-preview-{race}.json';assert not target.exists();r.write_json(target,reg)
        subprocess.run([shutil.which('pwsh'),'-NoProfile','-File','eloria-assets/tools/capture_canonical_equipment.ps1','-Slugs',race,'-Prefix','ornament-catalogue-militia_torso_armor_03','-Equipment',str(target),'-Outfit',f'5:{piece.visual}','-Clips','Idle_Subtle,Walk,Jog,Run_Female,Fighting_Idle','-Angles','front,side','-Cycles'],check=True)
        if race=='glasswarden_female':
            subprocess.run([sys.executable,'eloria-assets/tools/compare_conformed_piece.py',str(OUT/race/(piece.slug+'.glb')),str(piece.source.with_name(piece.source.name+'.orig')),'--out','equipment-fit-build/preview/ornament-splinted-source.png','--save-blend','--width','1000','--worn',f'godot-client/assets/actors/native/races/{race}.glb','--equipment',str(target)],check=True)
        print('ORNAMENT_RENDERED',race,flush=True)
