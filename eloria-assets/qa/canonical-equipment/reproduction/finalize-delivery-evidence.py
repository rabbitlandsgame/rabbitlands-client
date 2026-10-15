from pathlib import Path
import json,hashlib,gzip
ROOT=Path.cwd();BUILD=ROOT/'equipment-fit-build';DEST=ROOT/'eloria-assets/qa/canonical-equipment'
assert json.loads((BUILD/'reports/installed-validation.json').read_text())['status']=='passed'
assert all(row['changed_pixels']==0 for row in json.loads((BUILD/'reports/installed-image-comparison.json').read_text()))
index=DEST/'manifest.json';old=index.read_bytes();manifest=json.loads(old)
def sha(data):return hashlib.sha256(data).hexdigest()
def copy(source,target,compress=False):
    data=source.read_bytes();encoded=gzip.compress(data,compresslevel=6,mtime=0) if compress else data
    path=DEST/target;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(encoded)
    assert source.read_bytes()==data and path.read_bytes()==encoded
    manifest['files'][target.as_posix()]={'source':source.relative_to(ROOT).as_posix(),'source_sha256':sha(data),'sha256':sha(encoded),'bytes':len(encoded)}
for name in ['installed-equipment-tests.log','installed-body-tests.log','installed-animation.log','installed-torso-cover.log','installed-armour-cover.log','installed-profiles.log','installed-historical-torso.log','installed-historical-failure-diff.json','installed-validation.json','installed-image-comparison.json','canonical-delivery-install.log']:
    copy(BUILD/'reports'/name,Path('reports')/name)
copy(BUILD/'reports/installed-editor-import.log',Path('reports/installed-editor-import.log.gz'),True)
for path in (BUILD/'preview').glob('installed-militia_*.png*'):copy(path,Path('captures')/path.name)
for suffix in ['', '_worn']:
    path=BUILD/f'preview/ornament-eightcore-source{suffix}.png';copy(path,Path('captures')/path.name)
for name in ['capture-installed-delivery.py','finalize-delivery-evidence.py','collect-delivery-evidence.py']:
    copy(BUILD/name,Path('reproduction')/name)
readme=DEST/'reproduction/README.md';data=readme.read_bytes();manifest['files']['reproduction/README.md']={'sha256':sha(data),'bytes':len(data),'role':'reproduction instructions'}
for name,spec in manifest['files'].items():assert sha((DEST/name).read_bytes())==spec['sha256'],name
assert index.read_bytes()==old;index.write_text(json.dumps(manifest,indent=2)+'\n')
print('FINAL_EVIDENCE',len(manifest['files']),'files',flush=True)
