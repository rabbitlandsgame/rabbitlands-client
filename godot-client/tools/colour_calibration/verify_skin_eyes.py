"""R5 / R12 tables from rl_head_colour_calibration --part=verify-skin / verify-eyes runs.

usage: python verify_skin_eyes.py <out-dir> <label> <verify-skin.json> <verify-eyes.json> [renderer label]
"""
import json, sys
from pathlib import Path
import numpy as np
from calib_lib import enc, load

out_dir, label = Path(sys.argv[1]), sys.argv[2]
skin, eyes = load(sys.argv[3]), load(sys.argv[4])
summary = []
result = {'label': label, 'renderer': skin.get('renderer')}
for sex in ('female', 'male'):
    rows = skin[sex + '_skin']
    t0 = [r for r in rows if r['undertone'] == 0.0]
    other = [r for r in rows if r['undertone'] != 0.0]

    def err(r):
        return float(np.abs(enc(np.array(r['target'])) - enc(np.array(r['measured']))).max())
    w0 = max(err(r) for r in t0)
    wo = max(err(r) for r in other)
    result[sex + '_skin'] = {'t0_max': w0, 'other_max': wo, 'cases': len(rows),
                             't0_pass': w0 <= 0.002, 'other_pass': wo <= 0.005}
    summary.append('R5 skin %s %s: %d hold-out cases; t=0 max %.4f (limit 0.002), undertone max %.4f (limit 0.005)' % (
        label, sex, len(rows), w0, wo))
    vr = eyes[sex + '_eyes_verify']
    inside = [r for r in vr if r['custom'] and not r['limited']]
    limited = [r for r in vr if r['limited']]
    worst = max(r['error'] for r in inside) if inside else float('nan')
    p95 = float(np.percentile([r['error'] for r in inside], 95)) if inside else float('nan')
    lworst = max((r['error'] for r in limited), default=float('nan'))
    pupil = eyes[sex + '_pupil_ratio']
    result[sex + '_eyes'] = {'hold_out': len(inside), 'max': worst, 'p95': p95, 'limited_cases': len(limited),
                             'limited_max': lworst, 'pupil': pupil}
    summary.append('R12 eyes %s %s: %d hold-out pigments RL vs Medium max %.4f, p95 %.4f (limit 0.02); %d limited corners max %.4f; '
                   'iris/pupil luminance at the darkest allowed iris: Medium %.2f, RL %.2f (limit 1.5)' % (
                       label, sex, len(inside), worst, p95, len(limited), lworst, pupil['medium']['ratio'], pupil['rl']['ratio']))
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / f'verify_skin_eyes_{label}.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
(out_dir / f'verify_skin_eyes_{label}.txt').write_text('\n'.join(summary) + '\n', encoding='utf-8')
print('\n'.join(summary))
