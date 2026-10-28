"""Geometric eye-opening lab for the eye_style control (local tool, run from scripts/).

python eye_style_lab.py <spec.json> [--weights '{"eyes/l-eye-scale-incr": 1, ...}'] [--jacobian]

Builds the MPFB head as build_head.py does (macro stack + likeness), adds a target mix
(both sides are mirrored automatically: give the l- names), fits the eye proxy, and
measures the front-projected visible eye opening exactly like eye_metrics.py measures
renders: W, H, H/W, IPD, W/IPD, iris/W (realistic iris = 29 deg half angle), visible
iris fraction, upper rise / lower drop over the corner line, apex position, tilt, fill.
Also the blink check: the largest vertical opening left with ex_blink at 1.
"""
import json, sys, math, os, numpy as np
import mh, build_head as bh, paint_head
from scipy import ndimage as ndi

IRIS_HALF = math.radians(29.0)


def mirror(w):
    out = {}
    for k, v in w.items():
        out[k] = out.get(k, 0) + v
        if '/l-' in k:
            k2 = k.replace('/l-', '/r-')
            out[k2] = out.get(k2, 0) + v
    return out


class Head:
    def __init__(self, spec_path):
        spec = json.load(open(spec_path))
        self.spec = spec
        macro = json.load(open(spec['macro']))
        self.race = macro['macro']['race']
        b = mh.base()
        V0 = mh.apply(macro['stack'] + bh.stack_of(spec, 'likeness'))
        V0 = V0 + bh.shape_delta(spec.get('likeness_units', {}), self.race)
        for p, w in spec.get('custom_targets', {}).items():
            V0 = V0 + w * mh.delta(p)
        self.V0 = V0
        rep = json.load(open(os.path.join(os.path.dirname(spec_path), '..', 'build', 'v1', f"rl_head_{spec['sex']}.report.json")))
        self.s = rep['scale']
        faces = [f for f, g in zip(b.F, b.G) if g == 'body']
        self.T = bh.triangulate(faces, V0)
        self.eyes = mh.Proxy(mh.user(spec['proxies']['eyes']))
        self.lashes = mh.Proxy(mh.user(spec['proxies']['lashes']))

    def toM(self, V):
        return self.s * 0.1 * V

    def pose(self, weights, expr=None):
        V = self.V0 + bh.shape_delta(mirror(weights), self.race)
        if expr:
            V = V + bh.shape_delta(expr, self.race)
        return V

    def measure(self, V, iris_scale=1.0):
        P = self.toM(V)
        EP = self.toM(self.eyes.fit(V))
        out = {}
        sides = {}
        for side in (1, -1):
            E = EP[np.sign(EP[:, 0]) == side]
            c = E.mean(0)
            op = paint_head.eye_opening(P, self.T, EP, c)
            x0, x1, y0, y1, res = op.frame
            m = op.mask
            # sphere again (eye_opening keeps it internal): refit
            A = np.c_[2 * E, np.ones(len(E))]; bb = (E ** 2).sum(1)
            sol, *_ = np.linalg.lstsq(A, bb, rcond=None); cs = sol[:3]; rb = np.sqrt(sol[3] + cs @ cs)
            inl = np.abs(np.linalg.norm(E - cs, axis=1) - rb) < 0.0008
            sol, *_ = np.linalg.lstsq(A[inl], bb[inl], rcond=None); cs = sol[:3]; rb = np.sqrt(sol[3] + cs @ cs)
            sides[side] = (m, op.frame, cs, rb)
        ipd = abs(sides[1][2][0] - sides[-1][2][0])
        rows = []
        for side, (m, fr, cs, rb) in sides.items():
            x0, x1, y0, y1, res = fr
            ys, xs = np.nonzero(m)
            if len(xs) == 0:
                rows.append(None); continue
            X = x0 + (xs + 0.5) * res; Y = y1 - (ys + 0.5) * res
            W = X.max() - X.min()
            cols = np.unique(xs)
            top = np.array([Y[xs == k].max() for k in cols]); bot = np.array([Y[xs == k].min() for k in cols])
            cx = x0 + (cols + 0.5) * res
            H = (top - bot).max()
            k = max(1, int(len(cols) * 0.02))
            lo = ((top[:k] + bot[:k]) / 2).mean(); hi = ((top[-k:] + bot[-k:]) / 2).mean()
            # inner corner: nearer the midline
            if abs(cx[0]) < abs(cx[-1]):
                inner = (cx[0], lo); outer = (cx[-1], hi)
            else:
                inner = (cx[-1], hi); outer = (cx[0], lo)
            line = inner[1] + (outer[1] - inner[1]) * (cx - inner[0]) / (outer[0] - inner[0])
            ia = np.argmax(top); ib = np.argmin(bot)
            rise = top[ia] - line[ia]; drop = line[ib] - bot[ib]
            apex_t = (cx[ia] - inner[0]) / (outer[0] - inner[0])
            tilt = math.degrees(math.atan2(outer[1] - inner[1], abs(outer[0] - inner[0])))
            fill = len(xs) * res * res / (W * H)
            iris_r = rb * math.sin(IRIS_HALF) * iris_scale
            # visible iris: the iris disc (front projection about the sphere's front) inside the opening
            d2 = (X - cs[0]) ** 2 + (Y - cs[1]) ** 2
            vis = (d2 < iris_r ** 2)
            ih = (Y[vis].max() - Y[vis].min()) if vis.any() else 0
            rows.append({'W': W, 'H': H, 'rise': rise, 'drop': drop, 'apex_t': apex_t, 'tilt': tilt, 'fill': fill,
                         'iris': 2 * iris_r, 'irisvis': ih / (2 * iris_r), 'rb': rb, 'cx': cs[0], 'cy': cs[1],
                         'top_y': top[ia], 'bot_y': bot[ib], 'inner_x': inner[0], 'outer_x': outer[0]})
        r = {k: float(np.mean([row[k] for row in rows if row])) for k in rows[0]}
        r['IPD'] = ipd
        r['H/W'] = r['H'] / r['W']; r['W/IPD'] = r['W'] / ipd; r['H/IPD'] = r['H'] / ipd
        r['iris/W'] = r['iris'] / r['W']; r['iris/H'] = r['iris'] / r['H']
        r['rise/W'] = r['rise'] / r['W']; r['drop/W'] = r['drop'] / r['W']
        r['gap'] = 2 * min(abs(row['inner_x']) for row in rows)
        return r

    def blink_gap(self, weights):
        """Largest vertical opening (m) left with both blinks at 1."""
        V = self.pose(weights, {'expression/units/eye-left-closure': 1, 'expression/units/eye-right-closure': 1})
        P = self.toM(V); EP = self.toM(self.eyes.fit(V))
        gaps = []
        for side in (1, -1):
            E = EP[np.sign(EP[:, 0]) == side]
            try:
                op = paint_head.eye_opening(P, self.T, EP, E.mean(0))
            except ValueError:   # nothing of the eyeball shows: closed
                gaps.append(0.0); continue
            m = op.mask
            gaps.append(float(m.sum(0).max() * op.frame[4]) if m.any() else 0.0)
        return max(gaps)


def fmt(r):
    keys = ['W', 'H', 'IPD', 'iris', 'H/W', 'W/IPD', 'H/IPD', 'iris/W', 'iris/H', 'irisvis', 'rise/W', 'drop/W', 'apex_t', 'tilt', 'fill', 'gap']
    return '  '.join(f"{k}={r[k] * (100 if k in ('W', 'H', 'IPD', 'iris', 'gap') else 1):.3f}" for k in keys)


if __name__ == '__main__':
    spec = sys.argv[1]
    h = Head(spec)
    w = {}
    if '--weights' in sys.argv:
        w = json.loads(sys.argv[sys.argv.index('--weights') + 1])
    iris_scale = float(sys.argv[sys.argv.index('--iris') + 1]) if '--iris' in sys.argv else 1.0
    r0 = h.measure(h.pose({}))
    print('base   ', fmt(r0))
    if w:
        r1 = h.measure(h.pose(w), iris_scale)
        print('mixed  ', fmt(r1))
        print('blink gap mm base %.3f mixed %.3f' % (h.blink_gap({}) * 1000, h.blink_gap(w) * 1000))
    if '--jacobian' in sys.argv:
        names = sorted({n.split('/')[-1][2:] for n in os.listdir(os.path.join(mh.SYS, 'targets', 'eyes'))})
        for n in names:
            t = 'eyes/l-' + n.replace('.target.gz', '')
            r1 = h.measure(h.pose({t: 1.0}))
            print(f"{t:34s}", '  '.join(f"{k}={(r1[k] - r0[k]) * (100 if k in ('W', 'H', 'IPD', 'iris', 'gap') else 1):+.3f}"
                                         for k in ['W', 'H', 'IPD', 'iris', 'rise/W', 'drop/W', 'apex_t', 'tilt', 'fill', 'gap']))
