from pathlib import Path
import hashlib,json
ROOT=Path.cwd(); BUILD=ROOT/'equipment-fit-build'; DEST=ROOT/'eloria-assets/qa/canonical-equipment'
assert not json.loads((BUILD/'reports/installed-historical-failure-diff-02.json').read_text())['new']
assert all(r['changed_pixels']==0 for r in json.loads((BUILD/'reports/installed-encoding-image-comparison.json').read_text()))
index=DEST/'manifest.json';old=index.read_bytes();manifest=json.loads(old)
def copy(source,target):
    data=source.read_bytes();path=DEST/target
    with path.open('xb') as f:f.write(data)
    assert source.read_bytes()==data and path.read_bytes()==data
    manifest['files'][target.as_posix()]={'source':source.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(data).hexdigest(),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
for name in ['installed-profiles-02.log','installed-historical-torso-02.log','installed-historical-failure-diff-02.json','flat-classification-tests.log','legacy-image-labels.json','installed-encoding-image-comparison.json','capture-installed-encoding.log']:
    copy(BUILD/'reports'/name,Path('reports')/name)
for path in (BUILD/'preview').glob('installed-encoding-militia_*.png*'):copy(path,Path('captures')/path.name)
for name in ['capture-installed-encoding.py','supplement-delivery-evidence.py']:copy(BUILD/name,Path('reproduction')/name)
for name,spec in manifest['files'].items():assert hashlib.sha256((DEST/name).read_bytes()).hexdigest()==spec['sha256'],name
assert index.read_bytes()==old;index.write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
print('FINAL_EVIDENCE',len(manifest['files']),flush=True)
