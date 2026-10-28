"""--gap-targets: rank MPFB face targets that would reduce the residual left after the fit.

Each candidate (an MPFB target file, left/right files combined into one symmetric
candidate) is mapped onto the RL skin exactly like build_head.py maps the
control targets (game delta = build scale * 0.1 * MakeHuman delta * (1 - seam
weight), through Head.Sv), then tested as one extra column on the final
data->model correspondences: best weight w in [0, 1] (targets are one-sided),
energy reduction = -(2 w a + w^2 b) with a = sum W J r, b = sum W J^2 (mm^2,
the same weighted mean squared distance the solver minimises). Targets already
used by the 21 controls are skipped. The ranking says which MPFB shapes would
be worth adding as new controls for this kind of reference.
"""
import os, sys, json
import numpy as np

from fitcommon import TOOLS, RL, CONTROLS_JSON
from rlmodel import REGIONS

DIRS = ('head', 'forehead', 'eyebrows', 'nose', 'mouth', 'cheek', 'chin', 'ears', 'eyes', 'neck')


def _mh():
    sp = TOOLS
    if sp not in sys.path:
        sys.path.append(sp)
    import mh
    return mh


def candidates():
    mh = _mh()
    used = set()
    for c in json.load(open(CONTROLS_JSON, encoding='utf-8'))['controls']:
        used.update(c.get('pos', {})); used.update(c.get('neg', {}))
    root = os.path.join(mh.SYS, 'targets')
    out = []
    for d in DIRS:
        dp = os.path.join(root, d)
        if not os.path.isdir(dp):
            continue
        names = sorted(f[:-len('.target.gz')] for f in os.listdir(dp) if f.endswith('.target.gz'))
        for n in names:
            rel = f'{d}/{n}'
            if rel in used or n.startswith('r-'):
                continue
            if d == 'head' and ('scale' in n or 'trans' in n):     # global scale/shift: the similarity covers these
                continue
            if n.startswith('l-'):
                r = f'{d}/r-{n[2:]}'
                if r in used:
                    continue
                out.append((f'{d}/(l|r)-{n[2:]}', [rel, r] if os.path.exists(os.path.join(root, r + '.target.gz')) else [rel]))
            else:
                out.append((rel, [rel]))
    return out


def skin_delta(model, rels, scale, wseam):
    mh = _mh()
    dV = sum(mh.delta(r) for r in rels)
    dG = scale * 0.1 * dV * (1 - wseam)[:, None]
    D = np.zeros((model.n, 3))                 # eyeball vertices (after the skin) get no candidate delta
    m = model.h.Sv >= 0
    Dsk = np.zeros((model.n_skin, 3))
    Dsk[m] = dG[model.h.Sv[m]]
    D[:model.n_skin] = Dsk
    return D


def rank(model, fitter, top=15):
    info = getattr(fitter, 'last_d2m', None)
    if info is None:
        raise RuntimeError('no final correspondences')
    rep = json.load(open(os.path.join(os.path.dirname(model.h.npz_path), f'rl_head_{model.sex}.report.json')))
    scale = rep['scale']
    wseam = np.load(model.h.npz_path)['wseam']
    tv, bary, n, W = info['tv'], info['bary'], info['n'], info['W']
    r = info['c0'] + info['J'] @ fitter.z                         # residual (mm) at the fitted controls
    out = []
    for name, rels in candidates():
        D = skin_delta(model, rels, scale, wseam)
        J = -((D[tv] * bary[:, :, None]).sum(1) * n).sum(1) * 1000.0
        a = float(np.sum(W * J * r)); b = float(np.sum(W * J * J))
        if b < 1e-9:
            continue
        w = float(np.clip(-a / b, 0, 1))
        red = -(2 * w * a + w * w * b)
        if red <= 1e-6:
            continue
        k = np.argmax(bary, 1)
        reg = model.region[tv[np.arange(len(k)), k]]
        eff = np.bincount(reg, weights=W * np.abs(J), minlength=len(REGIONS))
        out.append({'target': name, 'weight': round(w, 3), 'reduction_mm2': round(red, 4),
                    'region': REGIONS[int(np.argmax(eff))]})
    out.sort(key=lambda x: -x['reduction_mm2'])
    E = float(np.sum(W * r * r))
    for o in out:
        o['fraction_of_residual'] = round(o['reduction_mm2'] / max(E, 1e-12), 3)
    return out[:top]
