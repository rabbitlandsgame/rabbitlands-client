"""Task 1 table: the 64 head pieces, geometry class, and how close each comes to
the RL and shipped bald heads (per-zone minimum gap of any part, mm).

    inventory_table.py -> evidence/headwear_audit/inventory.csv (+ printed)
Reads inventory.json (inventory.py) for the coverage metrics.
"""
import csv
import json

import numpy as np
import trimesh

import fit_open_headwear as F
import hwlib as h
import ringfit as rf

FITTED = set(F.SPEC)
NOTES = {
    170: 'flat cloth top over the crown + tassel fringe: a pillbox cap, left as shipped',
    114: 'veil on a crown band; hides the hair',
    112: 'circlet with brow fringe and a veil at the sides/back',
    111: 'openwork circlet, two side ribbons, brow drop',
    119: 'root circlet, leaf crest, crystal dangles, nose drop',
}


def classify(r, visual):
    if visual in FITTED:
        return 'OPEN ring (refitted)'
    if visual == 170:
        return 'OPEN-sided cap (kept)'
    if r['kind'] == 'hat' or visual == 135:
        return 'closed: brimmed hat'
    if r['dome'] >= 0.6 and r['sides'] >= 0.45:
        return 'closed'
    return 'other'


def min_gaps(visual, sex, H):
    pc = h.piece(visual, sex)
    m = trimesh.Trimesh(pc['P'], pc['I'], process=False)
    Q = trimesh.sample.sample_surface(m, 8000, seed=4)[0]
    gaps, _ = rf.band_bins(H, Q, 72)
    centres = (np.arange(72) + 0.5) * 5.0
    out = {}
    for name in ('front', 'left', 'back', 'right'):
        msk = np.array([rf.zone_of(a) == name for a in centres]) & np.isfinite(gaps)
        out[name] = round(float(np.nanmin(gaps[msk]) * 1000), 1) if msk.any() else None
    return out


def main():
    inv = json.load(open(h.OUT + '/inventory.json'))
    by = {(r['visual'], r['sex']): r for r in inv}
    heads = {(sex, kind): F.head(sex, kind) for sex in ('female', 'male') for kind in ('rl', 'legacy')}
    rows = []
    for v in h.head_ids():
        rf_ = by[(v, 'female')]
        rm = by[(v, 'male')]
        g = {k: min_gaps(v, k[0], H) for k, H in heads.items()}
        rows.append(dict(
            id='3:%d' % v, name=rf_['name'], file=rf_['scene'], kind=rf_['kind'], ears=rf_['ears'],
            coversHair=int(rf_['coversHair']), dome=round((rf_['dome'] + rm['dome']) / 2, 2),
            sides=round((rf_['sides'] + rm['sides']) / 2, 2), nape=round((rf_['nape'] + rm['nape']) / 2, 2),
            face=round((rf_['face'] + rm['face']) / 2, 2), cls=classify(rf_, v),
            rl_f_min_gap=g[('female', 'rl')], rl_m_min_gap=g[('male', 'rl')],
            legacy_f_min_gap=g[('female', 'legacy')], note=NOTES.get(v, '')))
        r = rows[-1]
        print('%-6s %-18s %-30s %-6s cov=%d dome=%.2f sides=%.2f %-22s RLf F/L/B/R %s' % (
            r['id'], r['name'], r['file'], r['kind'], r['coversHair'], r['dome'], r['sides'], r['cls'],
            '/'.join(str(r['rl_f_min_gap'][k]) for k in ('front', 'left', 'back', 'right'))), flush=True)
    with open(h.OUT + '/inventory.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['id', 'name', 'file', 'kind', 'ears', 'coversHair', 'dome', 'sides', 'nape', 'face', 'class',
                    'rl_female_min_gap_mm F/L/B/R', 'rl_male_min_gap_mm F/L/B/R', 'legacy_female_min_gap_mm F/L/B/R',
                    'note'])
        for r in rows:
            fmt = lambda d: '/'.join(str(d[k]) for k in ('front', 'left', 'back', 'right'))
            w.writerow([r['id'], r['name'], r['file'], r['kind'], r['ears'], r['coversHair'], r['dome'], r['sides'],
                        r['nape'], r['face'], r['cls'], fmt(r['rl_f_min_gap']), fmt(r['rl_m_min_gap']),
                        fmt(r['legacy_f_min_gap']), r['note']])


if __name__ == '__main__':
    main()
