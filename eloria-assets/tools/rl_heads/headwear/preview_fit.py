"""Before/after geometry sheets of the offline fit (PIL painter's previews).

    preview_fit.py <visual>[,..] [sex] [hair] -> evidence/headwear_audit/fitprev_<v>_<sex>_<hair>.png
Rows: shipped placement, fitted (rigid part coloured by skin gap: red < 2 mm,
yellow < 6 mm, green < 12 mm, blue beyond; trails grey, undraped).
"""
import sys

import numpy as np

import fit_open_headwear as F
import hwlib as h
import preview


def colour(g):
    if g < 0.002:
        return (230, 60, 50)
    if g < 0.006:
        return (240, 210, 60)
    if g < 0.012:
        return (90, 200, 90)
    return (90, 140, 230)


def layers_for(v, sex, hair, fit):
    b = F.Band(v)
    H = F.head(sex, 'rl', hair)
    P = b.P[sex] if fit is None else fit.apply(b.P[sex])
    I = b.I
    head = h.rl_head(sex)
    L = [(head['P'], head['I'], (200, 170, 150))]
    if hair:
        hm = h.hair(sex, hair)
        L.append((hm['P'], hm['I'], (120, 75, 45)))
    trail = (b.trail_w[I] > 0.5).all(1)
    cent = P[I].mean(1)
    g = H.gap(cent)
    groups = {}
    for k in np.nonzero(~trail)[0]:
        groups.setdefault(colour(g[k]), []).append(k)
    for col, ks in groups.items():
        L.append((P, I[ks], col))
    L.append((P, I[trail], (150, 150, 150)))
    return L


def main():
    visuals = [int(x) for x in sys.argv[1].split(',')]
    sex = sys.argv[2] if len(sys.argv) > 2 else 'female'
    hair = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != 'none' else None
    centre = np.array([0, 1.66, 0.0])
    for v in visuals:
        b = F.Band(v)
        H = F.head(sex, 'rl', hair)
        sol = F.solve(H, b, sex, skin_head=F.head(sex, 'rl'), verbose=True)
        rows = [(layers_for(v, sex, hair, None), centre), (layers_for(v, sex, hair, sol['fit']), centre)]
        out = h.OUT + '/fitprev_%d_%s_%s.png' % (v, sex, (hair or 'bald').replace(':', '-'))
        preview.sheet(rows, out, size=260, labels=['%d shipped' % v, '%d fitted %s' % (v, F.fit_record(sol))])
        print(out)


if __name__ == '__main__':
    main()
