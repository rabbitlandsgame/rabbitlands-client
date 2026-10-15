"""Final installed-asset checks; never edits equipment or body sources."""
from pathlib import Path
import subprocess,sys,json,hashlib,os
ROOT=Path.cwd();CLIENT=ROOT/'godot-client';REPORTS=ROOT/'equipment-fit-build/reports'
GODOT='godot'
TAG=sys.argv[1]
manifest=json.loads((ROOT/'equipment-fit-build/packed'/TAG/'manifest.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_sources():
    for filename,spec in manifest['files'].items():assert sha(ROOT/filename)==spec['sha256'],filename
    for filename,value in manifest['protected'].items():assert sha(ROOT/filename)==value,filename
def run(name,args,expected=0):
    log=REPORTS/(name+'.log')
    with log.open('x') as f:
        result=subprocess.run(args,cwd=CLIENT,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
    print(name,'exit',result.returncode,flush=True)
    if expected is not None:assert result.returncode==expected,log
    return log
check_sources()
run('installed-editor-import',[GODOT,'--headless','--editor','--import','--quit'])
run('installed-equipment-tests',[sys.executable,'-m','pytest','tests/test_equipment_fit.py','tests/test_torso_remap.py','tests/test_limb_head_remap.py','tests/test_canonical_equipment.py','-q','--basetemp',str(ROOT/'equipment-fit-build/test-tmp-installed-equipment')])
run('installed-body-tests',[sys.executable,'-m','pytest','tests/test_native_glb_assets.py','-k','player_rigs or race_rigs or races_have or race_features or wardrobe_carries or human_cultures or slim_base or race_eyes or optional_headwear or native_hair or garments_ship or equipment_hides or equipment_is_authored','-q','--basetemp',str(ROOT/'equipment-fit-build/test-tmp-installed-body')])
for name,script in [('animation','test_animation_looping.gd'),('torso-cover','integration/torso_body_cover.gd'),('armour-cover','integration/armour_body_cover.gd'),('profiles','integration/equipment_fit_profiles.gd')]:
    run('installed-'+name,[GODOT,'--headless','--script','res://tests/'+script])
log=run('installed-historical-torso',[sys.executable,'-m','pytest','tests/test_torso_coverage.py','-q','--basetemp',str(ROOT/'equipment-fit-build/test-tmp-installed-historical')],None)
def failures(lines):return sorted({line.split(' - ',1)[0] for line in lines if line.startswith(('FAILED','SUBFAILED'))})
before=failures((REPORTS/'baseline-torso-failures.txt').read_text().splitlines())
after=failures(log.read_text().splitlines())
diff={'before':before,'after':after,'new':sorted(set(after)-set(before)),'resolved':sorted(set(before)-set(after))}
with (REPORTS/'installed-historical-failure-diff.json').open('x') as f:json.dump(diff,f,indent=2)
assert not diff['new'],diff
check_sources()
with (REPORTS/'installed-validation.json').open('x') as f:json.dump({'status':'passed','files':len(manifest['files']),'protected':len(manifest['protected']),'historical_new_failures':0},f,indent=2)
print('INSTALLED_VALIDATION_COMPLETE',flush=True)
