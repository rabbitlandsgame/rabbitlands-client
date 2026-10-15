"""Scratch orchestration: exact proposed torso source, immutable live shared tools."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import sys,types,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
PROPOSAL=ROOT/'equipment-fit-build/in/outer-sleeve-proposal.py'
SOURCE=PROPOSAL.read_bytes();SOURCE_SHA=hashlib.sha256(SOURCE).hexdigest()
ORIGINAL=json.loads((ROOT/'equipment-fit-build/in/canonical-fitted-source-snapshot/manifest.json').read_text())
CODES=dict(ORIGINAL,**{'torso_remap.py':SOURCE_SHA})
DRIVER_SHA=r.digest(__file__)
module=types.ModuleType('torso_candidate');module.__file__=str(ROOT/'eloria-assets/tools/torso_remap.py')
exec(compile(SOURCE,str(PROPOSAL),'exec'),module.__dict__)
METADATA=json.loads((ROOT/'equipment-fit-build/reports/body-measurements.json').read_text())
TAG='canonical-sleeves';ROSTER={p.slug:p for p in r.batch.roster() if p.part==5}
def check_tools():
 actual=r.tool_hashes()
 assert all(actual[k]==v for k,v in ORIGINAL.items() if k!='torso_remap.py')
 assert actual['torso_remap.py'] in {ORIGINAL['torso_remap.py'],SOURCE_SHA}
 assert r.digest(PROPOSAL)==SOURCE_SHA and r.digest(__file__)==DRIVER_SHA

def build(args):
 race,slug=args;piece=ROSTER[slug];check_tools()
 body=r.ce.RACES/(race+'.glb');body_sha=METADATA[race]['sha256'];assert r.digest(body)==body_sha
 source=piece.source.with_name(piece.source.name+'.orig');before=r.digest(source)
 dest=ROOT/'equipment-fit-build/out'/TAG/race/(slug+'.glb');dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():raise FileExistsError(dest)
 report=module.build(piece.source,dest,r.cached_rig(race),piece.kind,piece.name)
 check_tools();assert r.digest(source)==before and r.digest(body)==body_sha
 report.update(source_sha256=before,body_sha256=body_sha,tool_sha256=CODES,race=race,slug=slug,key=f'5:{piece.visual}',asset_sha256=r.digest(dest),orchestrator_sha256=DRIVER_SHA)
 report['variant']={'scene':dest.as_posix(),'authoredFor':race,'fitProfile':'canonical'}
 r.write_json(dest.with_suffix('.fit.json'),report)
 return report

if __name__=='__main__':
 reports=[];work=[(race,slug) for race in sorted(METADATA) for slug in ROSTER]
 with ProcessPoolExecutor(max_workers=16) as pool:
  futures=[pool.submit(build,args) for args in work]
  for future in as_completed(futures):
   report=future.result();reports.append(report);print(f"{len(reports)}/{len(work)} {report['race']} {report['slug']}",flush=True)
 base=ROOT/'equipment-fit-build/out/canonical-fitted/equipment.json'
 while not base.exists():time.sleep(15)
 registry=json.loads(base.read_text())
 for report in reports:registry['models'][report['key']].setdefault('variants',{})['canonical_'+report['race']]=report['variant']
 reports.sort(key=lambda row:(row['race'],row['slug']))
 r.write_json(ROOT/f'equipment-fit-build/reports/{TAG}-fit.json',reports)
 r.write_json(ROOT/f'equipment-fit-build/out/{TAG}/equipment.json',registry)
 print('TORSO_CANDIDATES_COMPLETE',len(reports),flush=True)
