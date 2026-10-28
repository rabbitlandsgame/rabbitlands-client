"""Fit the eye_style control's MPFB target mix to measured proportions (local tool).

python eye_style_fit.py <spec.json> <targets.json> [--start '{...}']

targets.json: {"ratios": {"W": 1.347, "H": 1.672, "gap": 0.97}, "abs": {"rise/W": 0.206, "drop/W": 0.261, "apex_t": 0.43, "tilt": 0.73},
               "weights": {"W": 4, ...}, "vars": ["scale-incr", ...], "bounds": [0, 1.5], "reg": 0.02}
Gauss-Newton on finite differences of eye_style_lab.Head.measure; prints the mix and its measures.
"""
import json, sys, numpy as np
import eye_style_lab as L

SIGNED = {'corner1': ('corner1-up', 'corner1-down'), 'corner2': ('corner2-up', 'corner2-down'),
          'push1': ('push1-out', 'push1-in'), 'push2': ('push2-out', 'push2-in'),
          'trans_x': ('trans-out', 'trans-in'), 'trans_y': ('trans-up', 'trans-down')}


def mix(names, x):
    w = {}
    for n, v in zip(names, x):
        if n in SIGNED:
            pos, neg = SIGNED[n]
            t = pos if v >= 0 else neg
            w['eyes/l-eye-' + t] = w.get('eyes/l-eye-' + t, 0) + abs(v)
        else:
            w['eyes/l-eye-' + n] = w.get('eyes/l-eye-' + n, 0) + v
    return {k: round(v, 4) for k, v in w.items() if abs(v) > 1e-4}


def main():
    h = L.Head(sys.argv[1])
    cfg = json.load(open(sys.argv[2]))
    names = cfg['vars']
    base = h.measure(h.pose({}))
    goal = {}
    for k, r in cfg.get('ratios', {}).items():
        goal[k] = base[k] * r
    goal.update(cfg.get('abs', {}))
    wts = cfg.get('weights', {})
    keys = list(goal)
    def resid(x):
        m = h.measure(h.pose(mix(names, x)))
        r = [(m[k] - goal[k]) / (abs(goal[k]) if k in cfg.get('ratios', {}) else 1.0) * wts.get(k, 1.0) for k in keys]
        return np.array(r), m
    x = np.zeros(len(names))
    if '--start' in sys.argv:
        st = json.loads(sys.argv[sys.argv.index('--start') + 1])
        x = np.array([st.get(n, 0.0) for n in names])
    lo, hi = cfg.get('bounds', [-1.5, 1.5])
    reg = cfg.get('reg', 0.02)
    def clampx(x):
        x = np.clip(x, lo, hi)
        for j, n in enumerate(names):
            if n not in SIGNED:
                x[j] = max(x[j], 0.0)
        return x
    lam = 1.0
    r0, m0 = resid(x); c0 = float(r0 @ r0) + reg * float(x @ x)
    for it in range(cfg.get('iters', 8)):
        J = np.zeros((len(r0), len(names)))
        for j in range(len(names)):
            dx = np.zeros(len(names)); dx[j] = 0.1
            J[:, j] = (resid(x + dx)[0] - r0) / 0.1
        for attempt in range(6):
            A = J.T @ J + (reg + lam) * np.eye(len(names))
            step = np.linalg.solve(A, -(J.T @ r0) - reg * x)
            xn = clampx(x + step)
            rn, mn = resid(xn); cn = float(rn @ rn) + reg * float(xn @ xn)
            if cn < c0:
                x, r0, m0, c0 = xn, rn, mn, cn; lam = max(lam / 3, 1e-3); break
            lam *= 4
        print(it, 'cost %.4f lam %.3g' % (c0, lam), json.dumps(dict(zip(names, np.round(x, 3).tolist()))), flush=True)
    r, m = resid(x)
    print('cost %.4f' % float(r @ r))
    print('mix', json.dumps(mix(names, x)))
    print('goal ', {k: round(goal[k], 3) for k in keys})
    print('got  ', {k: round(m[k], 3) for k in keys})
    print('base ', L.fmt(base))
    print('final', L.fmt(m))
    print('blink gap mm %.3f' % (h.blink_gap(mix(names, x)) * 1000))


if __name__ == '__main__':
    main()
