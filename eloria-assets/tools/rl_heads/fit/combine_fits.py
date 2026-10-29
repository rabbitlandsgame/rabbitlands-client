"""Combine fits of several reference generations of the same character into one preset entry.

A single image-to-3D reconstruction varies by millimetres between generations (two Meshy busts of the same
concept differ by ~3 mm rms on the face, 6 mm at the chin), so a control is only trusted when independent
fits agree. Workflow: generate the character two or more times (different seeds or models), fit each with
fit_reference.py, then

    python RL/scripts/fit/combine_fits.py <fit_dir_or_fit.json> <fit_dir_or_fit.json> [...] --out <preset.json>
           [--tol 0.3] [--label NAME] [--key KEY]

Rules: a control enters the preset when every fit measured it (status measured / at_limit, see fit.json
control_reliability) and the preset values agree within --tol (default 0.3, about four 4-bit steps); the
value is their mean. Controls that any fit could not measure or where the fits disagree are left at the
base value (0) and listed. Colours: per-channel median of the measured values. Hair / beard style: the
most common choice (ties: the best-scoring fit). Writes {"key": ..., "preset": {...}, "combined_from": [...],
"disagreements": [...], "not_measured": [...]} and prints a summary. Exit 1 when the fits are of different
sexes or any fit has quality status 'fail'.
"""
import os, sys, json, argparse
from collections import Counter
import numpy as np

TRUSTED = ('measured', 'at_limit')


def load(p):
    if os.path.isdir(p):
        p = os.path.join(p, 'fit.json')
    return p, json.load(open(p, encoding='utf-8'))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fits', nargs='+')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tol', type=float, default=0.3)
    ap.add_argument('--label')
    ap.add_argument('--key')
    a = ap.parse_args(argv)
    fits = [load(p) for p in a.fits]
    if len(fits) < 2:
        print('need at least two fits'); return 1
    sexes = {f['sex'] for _, f in fits}
    if len(sexes) != 1:
        print(f'fits disagree on sex: {sexes}'); return 1
    failed = [p for p, f in fits if f.get('quality', {}).get('status') == 'fail']
    if failed:
        print(f'fits with quality status fail: {failed}'); return 1
    names = list(fits[0][1]['controls'])
    controls, disagree, unmeasured = {}, [], []
    for n in names:
        st = [f.get('control_reliability', {}).get(n, {}).get('status', 'measured') for _, f in fits]
        vals = [float(f['preset']['controls'].get(n, 0.0)) for _, f in fits]
        if not all(s in TRUSTED for s in st):
            unmeasured.append({'control': n, 'status': st, 'values': vals})
            continue
        if max(vals) - min(vals) > a.tol:
            disagree.append({'control': n, 'values': vals})
            continue
        m = float(np.mean(vals))
        if abs(m) >= 0.05:
            controls[n] = round(m, 2)
    best = min(fits, key=lambda pf: pf[1]['residual_mm']['face_rms'])[1]
    preset = dict(best['preset'])
    preset['controls'] = controls
    for k in ('skin', 'eyes', 'hair_color', 'brow_color', 'lip_tint'):
        vs = [f['preset'][k] for _, f in fits if f['preset'].get(k) is not None]
        if vs:
            preset[k] = [round(float(x), 3) for x in np.median(np.asarray(vs, float), 0)]
    for k in ('hair', 'beard'):
        c = Counter(f['preset'][k] for _, f in fits).most_common()
        preset[k] = c[0][0] if len(c) == 1 or c[0][1] > c[1][1] else best['preset'][k]
    if a.label:
        preset['label'] = a.label
    key = a.key or best.get('preset_key') or 'fitted'
    out = {'key': key, 'preset': preset, 'combined_from': [p for p, _ in fits], 'tolerance': a.tol,
           'disagreements': disagree, 'not_measured': unmeasured}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w', encoding='utf-8'), indent=1)
    print(f'{len(controls)} controls agreed within {a.tol}: {controls}')
    print(f'{len(disagree)} disagree: ' + ', '.join(f"{d['control']} {d['values']}" for d in disagree))
    print(f'{len(unmeasured)} not measured by every fit: ' + ', '.join(u['control'] for u in unmeasured))
    print(f'hair {preset["hair"]}, beard {preset["beard"]} -> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
