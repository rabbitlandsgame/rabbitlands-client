"""Joint control + similarity solve (Gauss-Newton / ICP with bounded linear steps).

Unknowns per iteration
  z = [a (21), b (21)]  control parts, a = max(v,0), b = max(-v,0), each in [0,1]
  xi = [w (3, rad), tau (3, mm), sig (log scale)]  small similarity update of the
       reference about the head centre (applied to the reference points)

Residuals (mm), linear in (z, xi) for fixed correspondences:
  data -> model  r = n_m . (y(xi) - sum_b bary_b (P + D z))     (reference skin point y,
                 closest skin point with barycentrics, interpolated morphed normal n_m)
  model -> data  r = n_y . (P_i + D_i z - y(xi))                (RL vertex i, nearest
                 reference skin point y with reference normal n_y)
Weights: RL region weight x Cauchy robust weight x normal compatibility; the
data->model block is normalised to total weight 1, model->data to 0.5, so the
energy is a weighted mean squared distance in mm^2.
Priors: Tikhonov lambda_j z_j^2 with lambda_j = rel * e_j + abs (e_j = the mean
squared effect of part j on the current correspondences: unobservable parts
stay at 0), log-scale prior toward the controls-0 registration scale, tiny
damping on rotation/translation.

Sign handling (the runtime uses exactly one of id_<c>_p / id_<c>_n per
control): the bounded problem is solved first with both parts free (convex
relaxation), each control is then assigned the side its relaxed solution
prefers and re-solved with the other part pinned to 0 (a convex problem per
orthant); finally, sides are flipped one control at a time while that lowers
the energy (a control at 0 is flipped if the other side's gradient is
negative). Every accepted flip starts from a feasible point of the new
orthant, so the energy decreases monotonically and the result is a KKT point
of the true piecewise-linear model v -> S(v).
"""
import numpy as np
from scipy.optimize import lsq_linear
from scipy.linalg import cho_factor, solve_triangular
from scipy.spatial import cKDTree

from fitcommon import kdq, Sim, unit, log
from rlmodel import REGIONS

NP = 7          # pose unknowns


class Settings:
    def __init__(self, **kw):
        self.iters = 14
        self.lam_rel = 0.002
        self.lam_abs = 0.001         # mm^2
        self.lam_scale = 4.0         # mm^2 per (log scale)^2 (weak guard; anchored at s0)
        self.lam_rot = 0.0           # mm^2 per rad^2: prior toward the rotation R0 (pitch/yaw/roll)
        self.R0 = None
        self.robust = (8.0, 3.0)     # Cauchy scale mm: first -> last iteration
        self.gate = (25.0, 10.0)     # mm
        self.m2d_weight = 0.5
        self.cosmin = 0.4
        self.n_model = 3000
        self.controls = True
        self.scale_free = False
        self.fix_pose = False
        self.tol = 0.004
        self.__dict__.update(kw)


def _robust(r, c):
    return 1.0 / (1.0 + (r / c) ** 2)


def _solve_bounded(H, g, lb, ub):
    """min 0.5 x'Hx - g'x  s.t. lb <= x <= ub (H positive definite)."""
    n = len(g)
    L = np.linalg.cholesky(H)
    A = L.T
    b = solve_triangular(L, g, lower=True)
    free = (lb == -np.inf) & (ub == np.inf)
    if np.all(free):
        return np.linalg.solve(H, g)
    lb2 = lb.copy(); ub2 = ub.copy()
    fixed = ub2 - lb2 < 1e-12
    ub2[fixed] = lb2[fixed] + 1e-12
    res = lsq_linear(A, b, bounds=(lb2, ub2), method='bvls', lsmr_tol='auto', max_iter=500)
    return res.x


def _energy(H, g, x):
    return 0.5 * x @ H @ x - g @ x


def solve_orthant(H, g, k, allow, prev_side=None):
    """Bounded solve with the one-side-per-control rule. Variables: x = [a (k), b (k), pose (NP)].
    allow: bool (k,) controls that may be non-zero. Returns x, side (+1/-1/0)."""
    n = len(g)
    lb = np.full(n, -np.inf); ub = np.full(n, np.inf)
    lb[:2 * k] = 0.0; ub[:2 * k] = 1.0
    ub[:k][~allow] = 0.0; ub[k:2 * k][~allow] = 0.0
    x = _solve_bounded(H, g, lb, ub)
    a = x[:k]; b = x[k:2 * k]
    side = np.where(a - b > 1e-6, 1, np.where(b - a > 1e-6, -1, 0))
    if prev_side is not None:
        side = np.where((side == 0) & allow, prev_side, side)

    def bounds_for(side):
        lb = np.full(n, -np.inf); ub = np.full(n, np.inf)
        lb[:2 * k] = 0.0; ub[:2 * k] = 0.0
        ub[:k][side > 0] = 1.0
        ub[k:2 * k][side < 0] = 1.0
        return lb, ub

    lb, ub = bounds_for(side)
    x = _solve_bounded(H, g, lb, ub)
    E = _energy(H, g, x)
    for rnd in range(6):
        changed = False
        grad = H @ x - g
        for j in np.nonzero(allow)[0]:
            v = x[j] - x[k + j]
            cands = []
            if abs(v) < 1e-6:
                if grad[j] < -1e-9 and side[j] != 1:
                    cands.append(1)
                if grad[k + j] < -1e-9 and side[j] != -1:
                    cands.append(-1)
            else:
                other = -1 if v > 0 else 1
                gi = grad[k + j] if other < 0 else grad[j]
                if gi < -1e-9:
                    cands.append(other)
            for sgn in cands:
                s2 = side.copy(); s2[j] = sgn
                lb2, ub2 = bounds_for(s2)
                x2 = _solve_bounded(H, g, lb2, ub2)
                E2 = _energy(H, g, x2)
                if E2 < E - 1e-9:
                    side, x, E = s2, x2, E2
                    changed = True
                    grad = H @ x - g
                    break
        if not changed:
            break
    a = x[:k]; b = x[k:2 * k]
    side = np.where(a > 1e-7, 1, np.where(b > 1e-7, -1, side))
    return x, side


class Fitter:
    def __init__(self, model, Xref, Nref, sim, region_w, settings=None, Xall=None, Nall=None, lab_all=None):
        """Xref/Nref: reference skin points (ref space) for the data->model term; Xall/Nall/lab_all:
        every head-zone reference point with its label - the model->data term skips RL vertices
        whose nearest reference point is not skin (hair, beard, clothing)."""
        self.m = model
        self.Xr = Xref; self.Nr = Nref
        self.sim = sim.copy()
        self.vw = region_w
        self.S = settings or Settings()
        self.Xall = Xall; self.Nall = Nall; self.lab_all = lab_all
        k = len(model.names)
        self.k = k
        self.z = np.zeros(2 * k)
        self.side = np.zeros(k, int)
        self.history = []
        self.centre = np.array([0.0, model.lm['nose_tip'][1], model.C[2]])
        rng = np.random.default_rng(11)
        idx = np.nonzero(model.rep & (region_w > 0))[0]
        if len(idx) > self.S.n_model:
            pa = model.vertex_area[idx] / model.vertex_area[idx].sum()
            idx = rng.choice(idx, self.S.n_model, replace=False, p=pa)
        self.midx = idx
        self.s0 = sim.s
        self.allow = np.ones(k, bool)

    # ------------------------------------------------------------------
    def _terms(self, it):
        m = self.m; S = self.S
        frac = min(1.0, it / max(S.iters - 4, 1))
        c_rob = S.robust[0] + (S.robust[1] - S.robust[0]) * frac
        gate = (S.gate[0] + (S.gate[1] - S.gate[0]) * frac) / 1000.0
        Pv = m.morph(z=self.z)
        surf = m.surface(Pv)
        Yg = self.sim(self.Xr); Ny = self.sim.rot(self.Nr)
        pr = m.project(surf, Yg, max_dist=gate * 1.5)
        cosv = (pr['n'] * Ny).sum(1)
        ok = pr['ok'] & (pr['off'] < 0.0015) & (cosv > S.cosmin) & (np.abs(pr['d']) < gate)
        # rim: closest point on the open neck seam
        rimw = (m.open_boundary[pr['tv']] * pr['bary']).sum(1)
        ok &= ~((rimw > 0.9) & (pr['off'] > 0.0004))
        tv = pr['tv'][ok]; bary = pr['bary'][ok]; n = pr['n'][ok]
        y = Yg[ok]
        rw = (self.vw[tv] * bary).sum(1)
        d0 = pr['d'][ok] * 1000.0
        w = rw * _robust(d0, c_rob) * np.clip((cosv[ok] - S.cosmin) / (1 - S.cosmin), 0.05, 1)
        # base residual at z = 0 and Jacobian wrt z (mm)
        pb = (m.P[tv] * bary[:, :, None]).sum(1)
        c0 = ((y - pb) * n).sum(1) * 1000.0
        J = np.zeros((len(y), 2 * self.k))
        for b in range(3):
            Db = m.D[:, tv[:, b], :]                       # (42, M, 3)
            J -= (np.einsum('kmc,mc->mk', Db, n) * bary[:, b:b + 1]) * 1000.0
        q = (y - self.centre) * 1000.0
        Jp = np.c_[np.cross(q, n), n, (n * q).sum(1)]
        W1 = w / max(w.sum(), 1e-12)
        blocks = [(J, Jp, c0, W1)]
        self.last_d2m = {'tv': tv, 'bary': bary, 'n': n, 'W': W1, 'c0': c0, 'J': J, 'y': y}
        stats = {'n_d2m': int(ok.sum()), 'rms_d2m': float(np.sqrt(np.sum(W1 * d0 ** 2)))}
        # model -> data
        if S.m2d_weight > 0 and self.Xall is not None:
            Xa = self.sim(self.Xall)
            kd = cKDTree(Xa)
            vi = self.midx
            Pm = Pv[vi]; Nm = surf.N[vi]
            dist, j = kdq(kd, Pm, k=1, distance_upper_bound=gate)
            ok2 = np.isfinite(dist)
            j = np.where(ok2, j, 0)
            ok2 &= self.lab_all[j] == 0
            ny = self.sim.rot(self.Nall[j])
            ok2 &= (ny * Nm).sum(1) > S.cosmin
            vi = vi[ok2]; ya = Xa[j[ok2]]; ny = ny[ok2]
            r0 = ((m.P[vi] - ya) * ny).sum(1) * 1000.0
            J2 = np.einsum('kmc,mc->mk', m.D[:, vi, :], ny) * 1000.0
            dcur = ((Pv[vi] - ya) * ny).sum(1) * 1000.0
            q2 = (ya - self.centre) * 1000.0
            Jp2 = -np.c_[np.cross(q2, ny), ny, (ny * q2).sum(1)]
            w2 = self.vw[vi] * self.m.vertex_area[vi] * _robust(dcur, c_rob)
            W2 = S.m2d_weight * w2 / max(w2.sum(), 1e-12)
            blocks.append((J2, Jp2, r0, W2))
            stats['n_m2d'] = int(len(vi))
            stats['rms_m2d'] = float(np.sqrt(np.sum(W2 * dcur ** 2) / max(W2.sum(), 1e-12)))
        return blocks, stats

    def _assemble(self, blocks):
        k2 = 2 * self.k
        n = k2 + NP
        H = np.zeros((n, n)); g = np.zeros(n)
        e = np.zeros(k2)
        for J, Jp, c0, W in blocks:
            A = np.c_[J, Jp]
            Aw = A * W[:, None]
            H += A.T @ Aw
            g += -(Aw.T @ c0)
            e += (W[:, None] * J ** 2).sum(0)
        S = self.S
        lam = S.lam_rel * e + S.lam_abs
        H[np.arange(k2), np.arange(k2)] += lam
        # pose damping, optional fixed scale / pose
        tr = np.trace(H) / n
        H[k2 + np.arange(6), k2 + np.arange(6)] += 1e-7 * tr
        if self.S.fix_pose:
            H[k2:, k2:] += np.eye(NP) * 1e12
        if S.lam_rot > 0 and S.R0 is not None and not S.fix_pose:
            # left-composed update: the deviation from R0 after the step is ~ omega + w
            from fitcommon import rot_angle_deg
            Dr = self.sim.R @ np.asarray(S.R0).T
            ang = np.radians(rot_angle_deg(Dr))
            if ang > 1e-9:
                ax = np.array([Dr[2, 1] - Dr[1, 2], Dr[0, 2] - Dr[2, 0], Dr[1, 0] - Dr[0, 1]]) / (2 * np.sin(ang))
                omega = ax * ang
            else:
                omega = np.zeros(3)
            ii = k2 + np.arange(3)
            H[ii, ii] += S.lam_rot
            g[ii] += -S.lam_rot * omega
        delta = np.log(self.sim.s / self.s0)
        if not S.scale_free:
            H[k2 + 6, k2 + 6] += S.lam_scale
            g[k2 + 6] += -S.lam_scale * delta
        else:
            H[k2 + 6, k2 + 6] += 1e-6
        return H, g, e, lam

    def energy_at(self, blocks, x):
        E = 0.0
        for J, Jp, c0, W in blocks:
            r = c0 + J @ x[:2 * self.k] + Jp @ x[2 * self.k:]
            E += float(np.sum(W * r ** 2))
        return E

    def run(self, log_fn=log, tag=''):
        S = self.S
        for it in range(S.iters):
            blocks, stats = self._terms(it)
            H, g, e, lam = self._assemble(blocks)
            if S.controls:
                x, self.side = solve_orthant(H, g, self.k, self.allow, prev_side=self.side)
            else:
                k2 = 2 * self.k
                xp = np.linalg.solve(H[k2:, k2:], g[k2:] - H[k2:, :k2] @ self.z)
                x = np.r_[self.z, xp]
            E0 = self.energy_at(blocks, np.r_[self.z, np.zeros(NP)])
            E1 = self.energy_at(blocks, x)
            self.last = {'blocks': blocks, 'x': x, 'e': e, 'lam': lam}
            znew = x[:2 * self.k]; xi = x[2 * self.k:]
            dz = float(np.abs(self.m.v_of(znew) - self.m.v_of(self.z)).max())
            self.z = znew
            if not S.fix_pose:
                self.sim = self.sim.update(xi[:3], xi[3:6] / 1000.0, xi[6], self.centre)
            rec = {'iter': it, 'energy_before_mm2': round(E0, 4), 'energy_after_mm2': round(E1, 4),
                   'rms_mm': round(stats['rms_d2m'], 3), 'n_d2m': stats['n_d2m'], 'n_m2d': stats.get('n_m2d', 0),
                   'max_dcontrol': round(dz, 4), 'scale': self.sim.s, 'rot_step_deg': round(float(np.degrees(np.linalg.norm(xi[:3]))), 4),
                   'trans_step_mm': round(float(np.linalg.norm(xi[3:6])), 4)}
            self.history.append(rec)
            if log_fn:
                log_fn(f"  {tag}it {it:2d}  E {E0:8.4f} -> {E1:8.4f} mm^2  rms {stats['rms_d2m']:.3f} mm  n={stats['n_d2m']}/{stats.get('n_m2d', 0)}"
                       f"  max|dv| {dz:.3f}  rot {rec['rot_step_deg']:.3f} deg  t {rec['trans_step_mm']:.3f} mm  s {self.sim.s:.6g}")
            # stop once the robust/gate schedule has finished and the state no longer moves
            if it >= S.iters - 4 and dz < S.tol and rec['rot_step_deg'] < 0.02 and rec['trans_step_mm'] < 0.05:
                break
        return self

    @property
    def v(self):
        return self.m.v_of(self.z)

    def residual_sigma(self):
        """Robust spread (mm) of the data->model residuals at the last solution: 1.4826 x the weighted
        median |r| (the noise floor + unmodelled shape the prior is scaled to)."""
        if not getattr(self, 'last', None):
            return None
        J, Jp, c0, W = self.last['blocks'][0]
        x = self.last['x']
        r = np.abs(c0 + J @ x[:2 * self.k] + Jp @ x[2 * self.k:])
        if not len(r):
            return None
        o = np.argsort(r)
        cw = np.cumsum(W[o]) / max(W.sum(), 1e-12)
        return float(1.4826 * r[o][np.searchsorted(cw, 0.5)])

    def residual_correlation(self, n=6000, rmax=0.03, seed=5):
        """Spatial correlation of the data->model residuals at the last solution: returns
        (correlation length mm = distance where the pair correlation first drops below 1/e, per-bin
        correlations). Remesh noise decorrelates within a few mm; unmodelled shape over centimetres."""
        if not getattr(self, 'last', None):
            return None, {}
        J, Jp, c0, W = self.last['blocks'][0]
        x = self.last['x']
        r = c0 + J @ x[:2 * self.k] + Jp @ x[2 * self.k:]
        y = self.last_d2m['y']
        if len(r) < 200:
            return None, {}
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(r), min(n, len(r)), replace=False)
        rr = r[idx] - np.median(r[idx]); yy = y[idx]
        # robust: clip at 3 robust sigmas so a few outliers do not dominate the products
        sg = 1.4826 * np.median(np.abs(rr)) + 1e-9
        rr = np.clip(rr, -3 * sg, 3 * sg)
        var = float(np.mean(rr ** 2))
        pairs = cKDTree(yy).query_pairs(rmax, output_type='ndarray')
        if not len(pairs):
            return None, {}
        dist = np.linalg.norm(yy[pairs[:, 0]] - yy[pairs[:, 1]], axis=1) * 1000.0
        prod = rr[pairs[:, 0]] * rr[pairs[:, 1]]
        edges = np.array([0.5, 1.5, 3, 5, 8, 12, 18, 25, 30])
        corr = {}
        ell = None
        prev_d, prev_c = 0.0, 1.0
        for a_, b_ in zip(edges[:-1], edges[1:]):
            m = (dist >= a_) & (dist < b_)
            if m.sum() < 50:
                continue
            c = float(prod[m].mean() / max(var, 1e-12))
            dmid = float(np.mean(dist[m]))
            corr[round(dmid, 1)] = round(c, 3)
            if ell is None and c < np.exp(-1):
                ell = prev_d + (dmid - prev_d) * (prev_c - np.exp(-1)) / max(prev_c - c, 1e-9)
            prev_d, prev_c = dmid, c
        if ell is None:
            ell = float(rmax * 1000.0)
        return float(ell), corr

    def local_sigma2(self):
        """Per control part (2k): effect-weighted mean squared residual (mm^2) where that part moves the
        surface (weights w_i J_ij^2), at the last solution; residuals clipped at 3 robust sigmas. Parts
        without support get the global robust variance."""
        k2 = 2 * self.k
        if not getattr(self, 'last', None):
            return None
        J, Jp, c0, W = self.last['blocks'][0]
        x = self.last['x']
        r = c0 + J @ x[:k2] + Jp @ x[k2:]
        g = self.residual_sigma() or 1.0
        rc = np.clip(r, -3 * g, 3 * g)
        out = np.full(k2, g * g)
        for c in range(k2):
            u = W * J[:, c] ** 2
            su = u.sum()
            if su > 1e-15:
                out[c] = float((u * rc ** 2).sum() / su)
        return out

    def control_snr(self):
        """Per control: effect-weighted rms of its full-range surface effect divided by the effect-weighted
        rms residual where it acts (data->model correspondences at the last solution). Both are
        weighted by w_i J_ij^2, i.e. by where control j moves the surface. A control whose whole range
        is comparable to the residual there (unmodelled shape, a blurred lip seam) is not measurable.
        Uses the active side (the larger-effect side for a control at 0)."""
        k = self.k
        if not getattr(self, 'last', None):
            return np.full(k, np.nan)
        J, Jp, c0, W = self.last['blocks'][0]
        x = self.last['x']
        r = c0 + J @ x[:2 * k] + Jp @ x[2 * k:]
        out = np.full(k, np.nan)
        v = self.m.v_of(x[:2 * k])
        for j in range(k):
            if abs(v[j]) < 0.05:
                cols = [j, k + j]
            else:
                cols = [j] if v[j] > 0 else [k + j]
            best = 0.0
            for c in cols:
                u = W * J[:, c] ** 2
                su = u.sum()
                if su <= 1e-18:
                    continue
                m = np.sqrt((u * J[:, c] ** 2).sum() / su)
                sg = np.sqrt((u * r ** 2).sum() / su)
                best = max(best, m / max(sg, 1e-3))
            out[j] = best
        return out

    def _active_parts(self):
        """Per control the part index (into z) its value lives on: the active side, the larger-effect side
        for a control at 0."""
        k = self.k
        e = self.last['e']
        return np.array([j if self.side[j] > 0 else (k + j if self.side[j] < 0 else (j if e[j] >= e[k + j] else k + j))
                         for j in range(k)])

    def posterior_sd(self, sigma2_parts, n_eff):
        """Marginal posterior sd of every allowed control from the last normal equations (correlations
        with the other controls and the pose included): cov = sigma_j^2 / N_eff * H^-1 over the active
        control parts + the 7 pose unknowns, H = data curvature + priors (the control prior is sd 0.5 in
        the automatic mode). NaN for controls pinned to 0."""
        k = self.k
        out = np.full(k, np.nan)
        if not getattr(self, 'last', None):
            return out
        H, _, _, _ = self._assemble(self.last['blocks'])
        parts = self._active_parts()
        ctl = np.nonzero(self.allow)[0]
        idx = np.r_[parts[ctl], 2 * k + np.arange(NP)]
        try:
            Ci = np.linalg.inv(H[np.ix_(idx, idx)])
        except np.linalg.LinAlgError:
            return out
        s2 = np.asarray(sigma2_parts, float) if sigma2_parts is not None else np.ones(2 * k)
        for i, j in enumerate(ctl):
            out[j] = float(np.sqrt(max(Ci[i, i], 0.0) * s2[parts[j]] / max(n_eff, 1.0)))
        return out

    def relaxed_values(self, ctl_idx, ub=2.0):
        """Linearised re-solve of the last normal equations with the upper bound of the given controls' active
        parts raised from 1 to ub (every other control keeps its side and [0, 1]): how far the data would take
        a control that sits at its limit. Returns {control index: relaxed value}."""
        k = self.k
        if not getattr(self, 'last', None) or not len(ctl_idx):
            return {}
        H, g, _, _ = self._assemble(self.last['blocks'])
        n = len(g)
        lb = np.full(n, -np.inf); ubv = np.full(n, np.inf)
        lb[:2 * k] = 0.0; ubv[:2 * k] = 0.0
        ubv[:k][(self.side > 0) & self.allow] = 1.0
        ubv[k:2 * k][(self.side < 0) & self.allow] = 1.0
        parts = self._active_parts()
        for j in ctl_idx:
            ubv[parts[j]] = ub
        x = _solve_bounded(H, g, lb, ubv)
        v = x[:k] - x[k:2 * k]
        return {int(j): float(v[j]) for j in ctl_idx}

    def observability(self):
        """Per control: data curvature e (mm^2 per unit weight, mean squared surface effect on the current
        correspondences) of the active side (the larger side for a control at 0) and its prior lambda.
        e / lambda < 1 means the prior, not the data, decides the value."""
        if not getattr(self, 'last', None):
            return None
        e = self.last['e']; lam = self.last['lam']
        k = self.k
        out = []
        for j in range(k):
            if self.side[j] > 0:
                ej, lj = e[j], lam[j]
            elif self.side[j] < 0:
                ej, lj = e[k + j], lam[k + j]
            else:
                i = j if e[j] >= e[k + j] else k + j
                ej, lj = e[i], lam[i]
            out.append((float(ej), float(lj)))
        return out
