from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys,json,subprocess
import numpy as np
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
REPORTS=ROOT/'equipment-fit-build/reports';OUT=REPORTS/'canonical-ornaments-audit-02';OUT.mkdir(exist_ok=True)
SOURCE=ROOT/'equipment-fit-build/out/canonical-ornaments'
RACES=sorted(json.loads((REPORTS/'body-measurements.json').read_text()))

def command(name,args):
    report=OUT/(name+'.json')
    with report.with_suffix('.log').open('x') as log:
        subprocess.run([sys.executable,*args,'--out',str(report)],check=True,stdout=log,stderr=subprocess.STDOUT)
    return report

def run(race):
    command(race+'-before-after',['eloria-assets/tools/measure_canonical_coverage.py','--before','godot-client/assets/actors/native/equipment','--after',str(SOURCE/race),'--race',race,'--runtime-bindings',str(REPORTS/f'baseline-chest-bindings/{race}.json'),'--pieces','militia_torso_armor_03'])
    command(race+'-motion',['eloria-assets/tools/replay_canonical_equipment.py',str(SOURCE/race),'--race',race])
    print('AUDITED',race,flush=True)

if __name__=='__main__':
    rest_path=command('rest',['eloria-assets/tools/audit_canonical_batch.py',str(SOURCE)])
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,RACES))
    old=REPORTS/'final-rest.json';a,b=[json.loads(p.read_text()) for p in [old,rest_path]]
    assert not b['failures']
    rows={(x['race'],x['slug']):x for doc in [a,b] for x in doc['assets']}
    assert len(rows)==4224
    r.write_json(REPORTS/'delivery-rest.json',dict(completed_assets=len(rows),failures=[],assets=list(rows.values()),reports={str(p):r.digest(p) for p in [old,rest_path]}))
    summary=[];coverage={};motion=REPORTS/'delivery-motion';motion.mkdir(exist_ok=True)
    for race in RACES:
        paths=[REPORTS/f'final-motion/{race}.json',OUT/(race+'-motion.json')]
        a,b=[json.loads(p.read_text()) for p in paths]
        result=dict(race=race,scope='full locomotion; final torso, leg and boot candidates; paired linings',clips={},input_sha256={},reports={str(p):r.digest(p) for p in paths})
        for clip in a['clips']:result['clips'][clip]=[row for row in a['clips'][clip] if row['asset']!='militia_torso_armor_03.glb']+b['clips'][clip]
        result['input_sha256']={p:s for p,s in a['input_sha256'].items() if Path(p).name!='militia_torso_armor_03.glb'}
        result['input_sha256'].update(b['input_sha256'])
        for p,s in result['input_sha256'].items():assert r.digest(p)==s
        r.write_json(motion/(race+'.json'),result)
        rows=[dict(row,clip=clip) for clip,items in result['clips'].items() for row in items]
        summary.append(dict(race=race,records=len(rows),worst_max=max(rows,key=lambda r:r['max_extension_mm']),worst_p99=max(rows,key=lambda r:r['p99_extension_mm']),max_loop_error_mm=max(r['loop_error_mm'] for r in rows)))
        paths=[REPORTS/f'canonical-sleeves-audit/{race}-before-after.json',OUT/(race+'-before-after.json')]
        a,b=[json.loads(p.read_text()) for p in paths]
        selected={row['slug']:row for doc in [a,b] for row in doc['pieces']};a['pieces']=list(selected.values());assert len(a['pieces'])==64
        for tag in ['before','after']:
            a[tag]={layer:dict(median_covered_width=float(np.median([x[tag][layer]['covered_width'] for x in a['pieces']])),minimum_covered_width=min(x[tag][layer]['covered_width'] for x in a['pieces']),total_proud_cells=sum(x[tag][layer]['proud_cells'] for x in a['pieces'])) for layer in ['art','all']}
        a['reports']={str(p):r.digest(p) for p in paths}
        r.write_json(OUT/(race+'-complete-before-after.json'),a)
        coverage[race]={k:a[k] for k in ['before','after']}
    r.write_json(motion/'summary.json',summary)
    r.write_json(REPORTS/'delivery-before-after-summary.json',coverage)
    print('DELIVERY_AUDITS_COMPLETE',flush=True)
