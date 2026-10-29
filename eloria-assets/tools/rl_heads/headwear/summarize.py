"""Compact current-vs-fitted table from audit_current.json and audit_fitted.json."""
import json

import numpy as np

import hwlib as h

cur = json.load(open(h.OUT + '/audit_current.json'))
fit = json.load(open(h.OUT + '/audit_fitted.json'))


def zones(r):
    out = []
    for k in ('front', 'left', 'back', 'right'):
        v = r['zones'].get(k)
        out.append('-' if v is None else '%.0f/%.0f/%.0f' % (v['gap_min'], v['gap_med'], v['gap_max']))
    return ' '.join(out)


def line(r, label):
    hh = r['heights']
    return '%d %-6s %-36s gap F L B R %-40s | brow+%s occ%+.0f back-front %s ears+%s/%s | skull x%.3f lift %s' % (
        r['piece'], r['sex'], label, zones(r), hh['front_over_brow_mm'], hh['back_over_occ_mm'] or 0,
        hh.get('back_minus_front_mm'), hh['left_over_ear_mm'], hh['right_over_ear_mm'], r['skull_ratio'],
        r.get('hair_lift_mm'))


print('CURRENT (shipped placement)')
for r in cur:
    print(line(r, '%s %s' % (r['head'], r['hair'])))
print()
print('FITTED')
for r in fit:
    print(line(r, r.get('fit', '')))
print()
print('FITTED summary per piece and head set')
for v in sorted({r['piece'] for r in fit}):
    for base in ('female', 'male', 'luminous_female', 'luminous_male'):
        rows = [r for r in fit if r['piece'] == v and (r['fit'] == base or r['fit'].startswith(base + '/'))]
        if not rows:
            continue
        med = [np.nanmedian([r['zones'][k]['gap_med'] for k in ('front', 'left', 'back', 'right') if r['zones'].get(k)])
               for r in rows]
        sk = [r['skull_ratio'] for r in rows]
        bf = [r['heights']['back_minus_front_mm'] for r in rows]
        fb = [r['heights']['front_over_brow_mm'] for r in rows]
        oc = [r['heights']['back_over_occ_mm'] for r in rows]
        smin = [r['zones']['rigid_min_skin_gap_mm'] for r in rows]
        print('%d %-16s n=%2d  median gap %.1f..%.1f mm  skull x%.3f..%.3f  brow+%.0f..%.0f  back-front %+.0f..%+.0f  occ%+.0f..%+.0f  skin>=%.1f' % (
            v, base, len(rows), min(med), max(med), min(sk), max(sk), min(fb), max(fb), min(bf), max(bf),
            min(oc), max(oc), min(smin)))
