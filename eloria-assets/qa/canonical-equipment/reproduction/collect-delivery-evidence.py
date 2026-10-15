"""Copy verified evidence to an explicit new QA tree; retain source hashes."""
from pathlib import Path
import json,hashlib,gzip
ROOT=Path.cwd();BUILD=ROOT/'equipment-fit-build';PREVIEW=BUILD/'preview'
DEST=ROOT/'eloria-assets/qa/canonical-equipment';assert not DEST.exists()
manifest={'files':{}}

def sha(data):return hashlib.sha256(data).hexdigest()
def copy(source,target,expected=None,compress=False):
    source=source.resolve();data=source.read_bytes();before=sha(data)
    if expected:assert before==expected,source
    encoded=gzip.compress(data,compresslevel=6,mtime=0) if compress else data
    output=DEST/target;output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(encoded)
    assert source.read_bytes()==data and sha(output.read_bytes())==sha(encoded)
    manifest['files'][target.as_posix()]={'source':source.relative_to(ROOT).as_posix(),'source_sha256':before,'sha256':sha(encoded),'bytes':len(encoded)}

contact=PREVIEW/'contact-delivery'
index=json.loads((contact/'manifest.json').read_text())
for name,digest in index['inputs'].items():
    source=(ROOT/name).resolve() if not Path(name).is_absolute() else Path(name)
    assert source.is_relative_to(PREVIEW)
    copy(source,Path('captures')/source.relative_to(PREVIEW),digest)
for path in contact.iterdir():copy(path,Path('sheets')/path.name)
for path in PREVIEW.glob('final-militia_*.png.json'):
    target=Path('captures')/path.name
    if target.as_posix() not in manifest['files']:copy(path,target)
for path in PREVIEW.glob('final-*.blend'):copy(path,Path('blender')/path.name)
for stem in ['final-legendary_hero_cuirass_01-source','final-leather_ranger_torso_05-source','final-amberwood_woodland_cuirass_04-source','ornament-splinted-source']:
    for suffix in ['', '_worn']:
        path=PREVIEW/(stem+suffix+'.png');target=Path('captures')/path.name
        if target.as_posix() not in manifest['files']:copy(path,target)
for name in ['ornament-final-cycle-review.jpg','ornament-final-cycle-review.json','sashcord-final-cycle-review.jpg','ceremonial-final-cycle-review.jpg','delivery-catalogue-source-manifest.json']:
    copy(PREVIEW/name,Path('sheets')/name)
for path in PREVIEW.glob('final-gauntlet_*.png'):
    copy(path,Path('captures')/path.name)
    report=path.with_suffix('.png.json')
    if report.exists():copy(report,Path('captures')/report.name)
reports=BUILD/'reports'
plain=['delivery-before-after-summary.json','body-measurements.json','low-ornament-source-scan.json','packed-pilot-image-comparison.json','eightcore-render-comparison.json','baseline-equipment.log','baseline-torso-coverage-current-code.log','baseline-torso-failures.txt','final-ornament-fitter-tests-02.log','canonical-delivery-pack-02.log']
for name in plain:copy(reports/name,Path('reports')/name)
detail=[reports/'delivery-rest.json',BUILD/'packed/canonical-delivery/manifest.json',BUILD/'in/start-hashes.json']
detail += [reports/(tag+'-fit.json') for tag in ['canonical-fitted','canonical-sleeves','canonical-eyes','canonical-ornaments']]
detail += sorted((reports/'delivery-motion').glob('*.json'))
detail += sorted((reports/'canonical-ornaments-audit-02').glob('*-complete-before-after.json'))
detail += sorted((reports/'baseline-chest-bindings').glob('*.json'))
for path in detail:
    relative=path.relative_to(BUILD)
    copy(path,Path('details')/(relative.as_posix()+'.gz'),compress=True)
for name in ['build-torso-candidate.py','build-head-candidate.py','build-ornament-candidate.py','scan-low-ornaments.py','audit-ornament-candidates.py','validate-installed-equipment.py','render-delivery-equipment.py','render-ornament-candidates.py']:
    copy(BUILD/name,Path('reproduction')/name)
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('EVIDENCE',len(manifest['files']),'files',round(sum(r['bytes'] for r in manifest['files'].values())/1e6,1),'MB',flush=True)
