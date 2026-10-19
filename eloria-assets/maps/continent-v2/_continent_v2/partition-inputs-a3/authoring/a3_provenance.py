"""Record partition-inputs-a3/input-provenance.json from the current inputs (run after any input change)."""
import hashlib, json
from pathlib import Path

REPO = Path(r'C:/rabbitlands/worktrees/a3-cli')
META = Path('eloria-assets/maps/continent-v2/_continent_v2')
A3, A2 = META / 'partition-inputs-a3', META / 'partition-inputs'
GROUND = (META / 'group-terrain-v2/terrain-provenance.json').as_posix()


def rec(p):
    b = (REPO / p).read_bytes()
    return {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}


prov = {
    'schema': 'eloria-continent-v2-partition-inputs-v2',
    'brief': 'Landfall A3 (owner 2026-10-19): drafts page https://claude.ai/artifact/H8SDxKVKQSikjpFNEzDcUi',
    'decisionDate': '2026-10-19',
    'predecessor': {'path': (A2 / 'input-provenance.json').as_posix(), **rec(A2 / 'input-provenance.json')},
    'groundProvenancePath': GROUND,
    'frozenTerrainProvenanceSha256': rec(GROUND)['sha256'],
    'files': {name: rec(A3 / name) for name in ('sections_spec.json', 'check_report.json', 'plan-amendments.json')},
}
for name in ('source-plan.json', 'source-catalog.json', 'source-stubs.json', 'source-view.tscn'):
    prov['files'][name] = {'path': (A2 / name).as_posix(), **rec(A2 / name)}
(REPO / A3 / 'input-provenance.json').write_text(json.dumps(prov, indent=1, ensure_ascii=False) + '\n',
                                                 encoding='utf-8', newline='\n')
print('recorded', A3 / 'input-provenance.json')
