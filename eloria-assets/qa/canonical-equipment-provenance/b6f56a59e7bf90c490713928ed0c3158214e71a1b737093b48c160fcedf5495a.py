from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
import torso_remap as t
CODES=r.tool_hashes();DRIVER_SHA=r.digest(__file__)
METADATA=json.loads((ROOT/'equipment-fit-build/reports/body-measurements.json').read_text())
SCAN=json.loads((ROOT/'equipment-fit-build/reports/low-ornament-source-scan.json').read_text())
SLUGS={row['slug'] for row in SCAN if row['low_ornaments']}
ROSTER={p.slug:p for p in r.batch.roster() if p.slug in SLUGS}
TAG='canonical-ornaments'

def build(args):
    race,slug=args;piece=ROSTER[slug]
    assert r.tool_hashes()==CODES and r.digest(__file__)==DRIVER_SHA
    body=r.ce.RACES/(race+'.glb');body_sha=METADATA[race]['sha256'];assert r.digest(body)==body_sha
    source=piece.source.with_name(piece.source.name+'.orig');before=r.digest(source)
    dest=ROOT/'equipment-fit-build/out'/TAG/race/(slug+'.glb');dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():raise FileExistsError(dest)
    report=t.build(piece.source,dest,r.cached_rig(race),piece.kind,piece.name)
    assert r.tool_hashes()==CODES and r.digest(source)==before and r.digest(body)==body_sha
    report.update(source_sha256=before,body_sha256=body_sha,tool_sha256=CODES,race=race,slug=slug,key=f'5:{piece.visual}',asset_sha256=r.digest(dest),orchestrator_sha256=DRIVER_SHA)
    report['variant']={'scene':dest.as_posix(),'authoredFor':race,'fitProfile':'canonical'}
    r.write_json(dest.with_suffix('.fit.json'),report)
    return report

if __name__=='__main__':
    reports=[];work=[(race,slug) for race in sorted(METADATA) for slug in ROSTER]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(build,args) for args in work]):
            row=future.result();reports.append(row);print(f"{len(reports)}/{len(work)} {row['race']} {row['slug']}",flush=True)
    registry=json.loads((ROOT/'equipment-fit-build/out/canonical-eyes/equipment.json').read_text())
    for row in reports:registry['models'][row['key']]['variants']['canonical_'+row['race']]=row['variant']
    r.write_json(ROOT/f'equipment-fit-build/reports/{TAG}-fit.json',sorted(reports,key=lambda r:(r['race'],r['slug'])))
    r.write_json(ROOT/f'equipment-fit-build/out/{TAG}/equipment.json',registry)
    print('ORNAMENT_CANDIDATES_COMPLETE',len(reports),flush=True)
