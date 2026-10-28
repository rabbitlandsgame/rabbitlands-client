"""Audit and fit OPEN headwear (circlets, bands, crowns, veils on a band) on the
RL head prototype.

    python fit_open_headwear.py audit   [--pieces 111,112] -> evidence/headwear_audit/audit.json
    python fit_open_headwear.py fit     [--pieces 111] [--hair all|none|mira_bun,...]
                                        -> godot-client/data/actors/rl_head_headwear_fit.json

The shipped piece is placed as the runtime places it (canonical_human_<sex>
variant, Head socket). Its BAND - the loop that should rest on the head - is a
tilted slab of the piece picked per piece (SPEC, female placement, carried to
the male variant, which is an exact similarity image of the female one), refined
by a plane fit. TRAILS are the vertices hanging below the band in components
that reach well below it.

The fit is a similarity transform in model space at rest (scale, a mild
width/depth ratio, pitch about the band centre, translation) chosen so that the
band's per-azimuth contact with the head - skin, or the hair mass when hair is
drawn - is uniform and small, with its front 2-3.5 cm over the brow ridge, its
sides just over the ear tops and its back on the occipital bulge, and no rigid
part inside the skin. Trails are draped at runtime (RLHeadwearFit).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np
import trimesh
from scipy.optimize import minimize

import hwlib as h
import ringfit as rf

FIT_JSON = h.CLIENT + '/data/actors/rl_head_headwear_fit.json'
FEMALE_EYE = None  # RL female eye line, the SPEC's height reference

# Per piece: band slab in the FEMALE placement: (centre over the RL female eye
# line, front-minus-centre tilt amplitude, half thickness), metres; trails:
# ramp from `start` to `full` below the band plane, in components reaching
# `min_reach` below it; `length`: how much of the trails' authored metric
# length they keep once the band shrinks (1 = all of it).
SPEC = {
    111: dict(band=(0.078, 0.040, 0.020),
              trails=dict(start=0.012, full=0.040, min_reach=0.04, length=1.0, front=0.0, keep=50.0),
              crest=0.0, label='circlet, two side ribbons, a brow drop'),
    112: dict(band=(0.150, 0.022, 0.028),
              trails=dict(start=0.010, full=0.035, min_reach=0.04, length=1.0, front=0.0, keep=45.0),
              front=0.035, crest=0.0, label='circlet, jewelled brow fringe, veil at the sides and back'),
    114: dict(band=(0.135, 0.030, 0.030),
              trails=dict(start=0.015, full=0.045, min_reach=0.04, length=1.0, front=25.0, keep=60.0),
              crest=0.004, label='crown, brow jewel, veil all round (covers hair)'),
    119: dict(band=(0.065, 0.008, 0.030),
              trails=dict(start=0.006, full=0.020, min_reach=0.022, length=0.0, front=35.0, drop=0.011,
                          keep=35.0),
              crest=0.004, hard=True,
              label='circlet, leaf crest, crystal dangles and a nose drop'),
    # 119's nose drop hangs (dropHalfWidth): rigid, it would hold a level band
    # off the face; its leaf crest stays rigid and over the brows.
}
# Not refitted: 170 Sun Headband is a pillbox cap (a flat cloth top over the
# cranium, the band its wall) with a tassel fringe. Its top must clear the
# crown, so it cannot come down to a forehead band; as shipped it already sits
# on the head and its fringe hangs. See the inventory.
OPEN = sorted(SPEC)
TARGET_FRONT = 0.030       # band contact over the brow ridge (owner: 2.5-3.5 cm)
TARGET_BACK = -0.004        # (legacy, unused) band contact over the occipital bulge
# A real circlet lies about level: the back of the band at the front's height
# or up to LEVEL_SPAN higher, and never under the occipital bulge (it would
# slide to the neck). Its size over the skull stays under SIZE_LIMIT.
LEVEL_RISE = 0.004
LEVEL_SPAN = 0.010
SIZE_LIMIT = 1.075
EAR_CLEAR = 0.006          # band lower edge over the ear tops
NBINS = 72


SEXES = ('female', 'male')


def sexes():
    return SEXES


# ------------------------------------------------------------------ band & trails

class Band:
    """Band / trail selection of one piece, by face and vertex, both sexes."""

    def __init__(self, visual):
        self.visual = visual
        spec = SPEC[visual]
        f = h.piece(visual, 'female')
        m = h.piece(visual, 'male')
        self.P = {'female': f['P'], 'male': m['P']}
        self.I = f['I']
        a, b = f['P'], m['P']
        ma, mb = a.mean(0), b.mean(0)
        self.s_fm = float(np.sqrt(((b - mb) ** 2).sum() / ((a - ma) ** 2).sum()))
        self.t_fm = mb - ma * self.s_fm
        eye = h.landmarks('female')
        eye_y = float((eye['eyeL'][1] + eye['eyeR'][1]) / 2)
        Cf = np.array([0.0, eye_y + 0.035, -0.009])
        self.C_f = Cf
        cent = a[self.I].mean(1)
        az = np.radians(np.degrees(np.arctan2(cent[:, 0] - Cf[0], cent[:, 2] - Cf[2])))
        y_mid, amp, tau = spec['band']
        sel = np.abs(cent[:, 1] - (eye_y + y_mid + amp * np.cos(az))) < tau
        # refine: plane y = a x + b z + d through the selected faces
        for _ in range(4):
            X = np.c_[cent[sel, 0], cent[sel, 2], np.ones(sel.sum())]
            coef, *_ = np.linalg.lstsq(X, cent[sel, 1], rcond=None)
            pred = cent[:, 0] * coef[0] + cent[:, 2] * coef[1] + coef[2]
            sel = np.abs(cent[:, 1] - pred) < tau
        self.coef_f = coef
        n = np.array([-coef[0], 1.0, -coef[1]])
        self.normal = n / np.linalg.norm(n)
        self.point_f = np.array([cent[sel, 0].mean(), 0.0, cent[sel, 2].mean()])
        self.point_f[1] = self.point_f[0] * coef[0] + self.point_f[2] * coef[1] + coef[2]
        # trails
        labels = h.weld_components(a, self.I)
        below = (self.point_f - a) @ self.normal
        self.trail_w = np.zeros(len(a))
        tspec = spec.get('trails')
        if tspec:
            reach = np.zeros(labels.max() + 1)
            np.maximum.at(reach, labels, below)
            ok = reach[labels] >= tspec['min_reach']
            vaz = np.degrees(np.arctan2(a[:, 0] - Cf[0], a[:, 2] - Cf[2]))
            ok &= np.abs(vaz) > tspec.get('front', 0.0)
            # a thin drop on the midline in front (down the nose bridge) hangs too
            drop = tspec.get('drop', 0.0)
            if drop > 0:
                ok |= (np.abs(vaz) < 30.0) & (np.abs(a[:, 0] - Cf[0]) < drop)
            t = np.clip((below - tspec['start']) / (tspec['full'] - tspec['start']), 0, 1)
            self.trail_w = np.where(ok, t * t * (3 - 2 * t), 0.0)
        rigid_face = (self.trail_w[self.I] < 0.5).all(1)
        self.band_faces = sel & rigid_face & (self.trail_w[self.I] == 0).all(1)
        self.rigid_faces = rigid_face
        self.below = below

    def plane(self, sex):
        """Band plane (point, normal) in this sex's placement."""
        if sex == 'female':
            return self.point_f, self.normal
        return self.point_f * self.s_fm + self.t_fm, self.normal

    def scale(self, sex):
        return 1.0 if sex == 'female' else self.s_fm

    def samples(self, sex, faces, n, seed=5):
        P = self.P[sex]
        idx = np.nonzero(faces)[0]
        mesh = trimesh.Trimesh(P, self.I[idx], process=False)
        pts, _ = trimesh.sample.sample_surface(mesh, n, seed=seed)
        return pts

    def trail_mask_runtime(self, sex):
        """The rule the runtime replays (RLHeadwearFit.trail_weights)."""
        t = SPEC[self.visual].get('trails')
        if not t:
            return None
        p, n = self.plane(sex)
        k = self.scale(sex)
        c = self.C_f if sex == 'female' else self.C_f * self.s_fm + self.t_fm
        return dict(point=[round(float(v), 6) for v in p], normal=[round(float(v), 6) for v in n],
                    start=round(t['start'] * k, 5), full=round(t['full'] * k, 5),
                    minReach=round(t['min_reach'] * k, 5),
                    centre=[round(float(v), 6) for v in c], frontSector=t.get('front', 0.0),
                    keepLengthSector=t.get('keep', 0.0),
                    dropHalfWidth=round(t.get('drop', 0.0) * k, 5))


# ------------------------------------------------------------------ metrics

def per_bin(head, Q, nbins=NBINS):
    gaps, ys = rf.band_bins(head, Q, nbins)
    return gaps, ys


def zone_stats(head, Qb, Qr, skin_head=None):
    """Gap per zone (min/median/max of per-bin minimum gaps, mm), contact heights."""
    gaps, ys = per_bin(head, Qb)
    centres = (np.arange(NBINS) + 0.5) * 360.0 / NBINS
    out = {}
    for name in rf.ZONES:
        m = np.array([rf.zone_of(a) == name for a in centres]) & np.isfinite(gaps)
        if not m.any():
            out[name] = None
            continue
        out[name] = dict(gap_min=round(float(np.nanmin(gaps[m]) * 1000), 1),
                         gap_med=round(float(np.nanmedian(gaps[m]) * 1000), 1),
                         gap_max=round(float(np.nanmax(gaps[m]) * 1000), 1),
                         y=round(float(np.nanmedian(ys[m])), 4))
    # skin penetration of any rigid part
    sk = skin_head.gap(Qr, skin_only=True) if skin_head is not None else head.gap(Qr, skin_only=True)
    out['rigid_min_skin_gap_mm'] = round(float(sk.min() * 1000), 1)
    out['bins_with_band'] = int(np.isfinite(gaps).sum())
    return out, gaps, ys


def heights(head, stats):
    def rel(v, ref):
        return None if v is None else round((v - ref) * 1000, 1)
    f, l, b, r = (stats.get(k) for k in ('front', 'left', 'back', 'right'))
    return dict(front_over_brow_mm=rel(f and f['y'], head.brow_y),
                left_over_ear_mm=rel(l and l['y'], head.ear_top['left']),
                right_over_ear_mm=rel(r and r['y'], head.ear_top['right']),
                back_over_occ_mm=rel(b and b['y'], head.occ_y),
                tilt_deg=round(math.degrees(math.atan2((f['y'] - b['y']), 0.18)), 1) if f and b else None,
                back_minus_front_mm=round((b['y'] - f['y']) * 1000, 1) if f and b else None)


def circumference(points):
    ok = np.isfinite(points[:, 0])
    p = points[ok]
    return float(np.linalg.norm(np.roll(p, -1, 0) - p, axis=1).sum())


def skull_ratio(head, band_pts, skin):
    return _band_ratio(head, band_pts, skin)


def scale_error(head, band_pts):
    """Median over azimuth bins of the band contact's distance from the cranium
    centre over the contact surface's: 1.0 is a band resting on the head."""
    az, el, r = rf.to_sph(band_pts - head.C)
    gap = r - head.radius(az, el)
    b = (az / 5.0).astype(int) % 72
    ratios = []
    for k in range(72):
        m = b == k
        if m.any():
            j = np.argmin(gap[m])
            ratios.append(r[m][j] / (r[m][j] - gap[m][j]))
    return float(np.median(ratios)), float(np.min(ratios)), float(np.max(ratios))


# ------------------------------------------------------------------ the solve

WARP_ORDER = 4
WARP_BINS = 36
WARP_RANGE = (0.76, 1.15)
# The warp fades out below the band: a drop hanging onto the brow or the nose
# keeps its shipped distance from the band's axis instead of being pulled in.
WARP_FADE = (0.015, 0.045)


class Fit:
    """A solved fit: similarity M, then a radial warp in the band's plane."""

    def __init__(self, M, x, pivot, normal, warp=None):
        self.M, self.x, self.pivot = M, x, pivot
        self.normal = normal
        self.origin = rf.apply(M, pivot[None])[0]
        n = M[:3, :3] @ normal
        self.axis = n / np.linalg.norm(n)
        self.warp = warp  # (cos[0..K], sin[1..K]) or None

    def frame(self):
        n = self.axis
        front = np.cross(np.array([1.0, 0, 0]), n)
        front /= np.linalg.norm(front)
        left = np.cross(n, front)
        return n, front, left

    def k(self, phi):
        phi = np.asarray(phi, dtype=float)
        if self.warp is None:
            return np.ones_like(phi)
        a, b = self.warp
        out = np.full_like(phi, a[0])
        for m in range(1, len(a)):
            out += a[m] * np.cos(m * phi) + b[m - 1] * np.sin(m * phi)
        return out

    def polar(self, P):
        n, front, left = self.frame()
        d = P - self.origin
        hgt = d @ n
        r = d - hgt[:, None] * n
        phi = np.arctan2(r @ left, r @ front)
        return hgt, r, phi

    def apply(self, P, warp=True):
        Q = rf.apply(self.M, P)
        if not warp or self.warp is None:
            return Q
        hgt, r, phi = self.polar(Q)
        t = np.clip((-hgt - WARP_FADE[0]) / (WARP_FADE[1] - WARP_FADE[0]), 0, 1)
        fade = 1 - t * t * (3 - 2 * t)
        k = 1 + (self.k(phi) - 1) * fade
        return self.origin + hgt[:, None] * self.axis + r * k[:, None]


def _band_ratio(head, B, skin):
    """Median over 5-degree bins of the band contact's radius over the skull's."""
    az, el, r = rf.to_sph(B - head.C)
    g = r - skin.radius(az, el, skin_only=True)
    b = (az / 5.0).astype(int) % 72
    order = np.lexsort((g, b))
    _, first = np.unique(b[order], return_index=True)
    rr, gg = r[order][first], g[order][first]
    return float(np.median(rr / np.maximum(rr - gg, 1e-6)))


WARM = {}


def solve(head, band, sex, skin_head=None, verbose=False, starts=None, pen_weight=None):
    """Seat the band; first with a soft penetration penalty (the warp then
    lifts what still touches), again with a hard one if the result touches."""
    if starts is None:
        starts = WARM.get((band.visual, sex), [])
    if pen_weight is None and SPEC[band.visual].get('hard'):
        pen_weight = 20.0
    if pen_weight is None:
        sol = _solve(head, band, sex, skin_head, verbose, starts, 2.0)
        WARM.setdefault((band.visual, sex), []).append(sol['x'])
        skin = skin_head or head
        worst = float((skin.gap(sol['fit'].apply(sol['Qr']), skin_only=True)).min())
        if worst >= rf.CLEAR_MIN - 0.0006:
            return sol
        if verbose:
            print('   soft fit touches the skin (%.1f mm): hard penalty' % (worst * 1000), flush=True)
        return _solve(head, band, sex, skin_head, verbose, starts, 20.0)
    return _solve(head, band, sex, skin_head, verbose, starts, pen_weight)


def _solve(head, band, sex, skin_head, verbose, starts, pen_weight):
    """Similarity (s, aniso, pitch, ty, tz) seating the band on the target path,
    then a low-order radial warp that makes the band follow the head's section."""
    Qb = band.samples(sex, band.band_faces, 3000)
    Qr = band.samples(sex, band.rigid_faces, 6000, seed=9)
    skin = skin_head or head
    pivot = Qb.mean(0)
    pivot[0] = 0.0
    normal = band.plane(sex)[1]
    spec = SPEC[band.visual]
    f, b, ear_y = head.target_path(spec.get('front', TARGET_FRONT), spec.get('back', TARGET_BACK))
    hair = head.R_hair is not None
    # head.R is the skull plus the clearance, or plus the hair's capped lift
    gap_target = 0.0
    centres = (np.arange(NBINS) + 0.5) * 360.0 / NBINS
    zones = np.array([rf.zone_of(a) for a in centres])
    front, back = zones == 'front', zones == 'back'
    target_c = (f + b) / 2
    w_h = spec.get('height_weight', 3.0)
    crest = spec.get('crest')
    level = spec.get('level', True)
    vr = Qr - head.C
    # what could cover the eyes: rigid parts in front of the face, off the
    # midline (a thin drop down the nose bridge is allowed)
    front_rigid = (np.abs(np.degrees(np.arctan2(vr[:, 0], vr[:, 2]))) < 30.0) & (np.abs(Qr[:, 0]) > 0.016)

    def transform(x):
        s, la, pitch, ty, tz = x
        return rf.similarity(s, pitch, [0.0, ty, tz], pivot, math.exp(la))

    def cost(x, detail=False):
        M = transform(x)
        B = rf.apply(M, Qb)
        R = rf.apply(M, Qr)
        gaps, ys = rf.band_bins(head, B, NBINS)
        ok = np.isfinite(gaps)
        g = gaps[ok] - gap_target
        e_gap = np.mean(np.where(g > 0, g, 4 * g) ** 2) * 1e6
        e_h = 0.0
        fy = np.nanmedian(ys[front & ok]) if (front & ok).any() else f[1]
        by = np.nanmedian(ys[back & ok]) if (back & ok).any() else b[1]
        e_h += (fy - f[1]) ** 2 * 1e6
        # level: back at the front's height + LEVEL_RISE, within 0..LEVEL_SPAN
        rise = by - fy
        if level:
            e_h += (rise - LEVEL_RISE) ** 2 * 1e6 * 0.5
            e_h += (max(0.0, -rise) ** 2 + max(0.0, rise - LEVEL_SPAN) ** 2) * 1e6 * 20
        # never under the occipital bulge
        e_h += max(0.0, head.occ_y + 0.002 - by) ** 2 * 1e6 * 40
        # size over the skull along the band
        e_size = max(0.0, _band_ratio(head, B, skin) - SIZE_LIMIT) ** 2 * 1e6 * 10
        side_low = []
        v = B - head.C
        az = np.degrees(np.arctan2(v[:, 0], v[:, 2])) % 360
        for lo, hi in ((60, 120), (240, 300)):
            m = (az > lo) & (az < hi)
            if m.any():
                side_low.append(B[m, 1].min())
        e_ear = sum(max(0.0, ear_y - EAR_CLEAR + 0.008 - y) ** 2 for y in side_low) * 1e6 * 4
        sk = skin.gap(R, skin_only=True)
        e_pen = np.sum(np.minimum(sk - rf.CLEAR_MIN, 0) ** 2) * 1e6 * pen_weight
        e_reg = (x[1] / 0.25) ** 2 * 8
        if crest is not None and front_rigid.any():
            low = R[front_rigid, 1].min()
            e_h += max(0.0, head.brow_y + crest - low) ** 2 * 1e6 * 6
        total = e_gap + w_h * e_h + e_ear + e_pen + e_reg + e_size
        if detail:
            return dict(total=total, gap=e_gap, heights=e_h, ear=e_ear, pen=e_pen, reg=e_reg, size=e_size)
        return total

    c0 = Qb.mean(0)
    if starts is None:
        starts = []
    starts = list(starts) + [np.array([s0, 0.0, p0, target_c[1] - c0[1] + dy, target_c[2] - c0[2]])
                             for s0 in (0.55, 0.7, 0.85) for p0 in (0.0, 12.0) for dy in (0.0, 0.02)]
    best = None
    for x0 in starts:
        r = minimize(cost, x0, method='Powell',
                     bounds=[(0.3, 1.3), (-0.25, 0.25), (-35, 35), (-0.2, 0.2), (-0.12, 0.12)],
                     options=dict(maxiter=3000, xtol=1e-4, ftol=1e-6))
        if best is None or r.fun < best.fun:
            best = r
    x = best.x
    M = transform(x)
    fit = Fit(M, x, pivot, normal)
    detail = cost(x, True)
    # ---- stage B: radial warp in the band plane
    edges = np.linspace(-np.pi, np.pi, WARP_BINS + 1)
    mid = (edges[:-1] + edges[1:]) / 2
    A = [np.ones(WARP_BINS)]
    for m in range(1, WARP_ORDER + 1):
        A += [np.cos(m * mid), np.sin(m * mid)]
    A = np.stack(A, 1)
    for _ in range(5):
        B = fit.apply(Qb)
        R = fit.apply(Qr)
        gb = head.gap(B)
        gr = skin.gap(R, skin_only=True)
        _, rb, pb = fit.polar(B)
        hr, rr, pr = fit.polar(R)
        rhob, rhor = np.linalg.norm(rb, axis=1), np.linalg.norm(rr, axis=1)
        kcur = fit.k(mid)
        want = np.full(WARP_BINS, np.nan)
        floor = np.full(WARP_BINS, np.nan)
        for i in range(WARP_BINS):
            mb = (pb >= edges[i]) & (pb < edges[i + 1])
            if mb.any():
                j = np.argmin(gb[mb])
                want[i] = kcur[i] * (1 - (gb[mb][j] - gap_target) / (0.9 * rhob[mb][j]))
            mr = (pr >= edges[i]) & (pr < edges[i + 1]) & (hr > -WARP_FADE[0])
            if mr.any():
                j = np.argmin(gr[mr])
                floor[i] = kcur[i] * (1 - (gr[mr][j] - rf.CLEAR_MIN) / (0.9 * rhor[mr][j]))
        ok = np.isfinite(want)
        if ok.sum() < 2 * WARP_ORDER + 2:
            break
        want = np.where(np.isfinite(floor), np.maximum(want, floor), want)
        coef, *_ = np.linalg.lstsq(A[ok], want[ok], rcond=None)
        kfit = A @ coef
        viol = np.where(np.isfinite(floor), floor - kfit, -np.inf)
        if viol.max() > 0:
            coef[0] += viol.max()
        a = np.r_[coef[0], coef[1::2]]
        bb = coef[2::2]
        trial = Fit(M, x, pivot, normal, (a, bb))
        kk = trial.k(np.linspace(-np.pi, np.pi, 360))
        lo, hi = WARP_RANGE
        if kk.min() < lo or kk.max() > hi:
            # keep the shape, limit the amount about 1
            sc = 1.0
            if kk.min() < lo:
                sc = min(sc, (1.0 - lo) / (1.0 - kk.min()))
            if kk.max() > hi:
                sc = min(sc, (hi - 1.0) / (kk.max() - 1.0))
            a = np.r_[1.0 + (a[0] - 1.0) * sc, a[1:] * sc]
            bb = bb * sc
            trial = Fit(M, x, pivot, normal, (a, bb))
        fit = trial
    def worst(f):
        R_ = f.apply(Qr)
        return float((skin.gap(R_, skin_only=True) - rf.CLEAR_MIN).min())
    base = min(worst(Fit(M, x, pivot, normal)), 0.0)
    for _ in range(12):
        if fit.warp is None or worst(fit) >= base - 0.0005:
            break
        a, bb = fit.warp
        fit = Fit(M, x, pivot, normal, (np.r_[1.0 + (a[0] - 1.0) * 0.8, a[1:] * 0.8], bb * 0.8))
    if verbose:
        ks = fit.k(np.linspace(-np.pi, np.pi, 360))
        print('   x', np.round(x, 4), {k_: round(float(v), 2) for k_, v in detail.items()},
              'warp k %.3f..%.3f' % (ks.min(), ks.max()), flush=True)
    return dict(fit=fit, M=M, x=x, pivot=pivot, cost=detail, Qb=Qb, Qr=Qr)


def fit_record(sol):
    s, la, pitch, ty, tz = sol['x']
    fit = sol['fit']
    rec = dict(scale=round(float(s), 5), aniso=round(float(math.exp(la)), 5),
               pitchDegrees=round(float(pitch), 3),
               pivot=[round(float(v), 6) for v in sol['pivot']],
               offset=[0.0, round(float(ty), 6), round(float(tz), 6)])
    if fit.warp is not None:
        a, b = fit.warp
        rec['warp'] = dict(origin=[round(float(v), 6) for v in fit.origin],
                           axis=[round(float(v), 6) for v in fit.axis],
                           cos=[round(float(v), 5) for v in a], sin=[round(float(v), 5) for v in b],
                           fadeBelow=list(WARP_FADE))
    return rec


# ------------------------------------------------------------------ commands

HEADS = {}


def head(sex, kind='rl', hair=None):
    key = (sex, kind, hair)
    if key not in HEADS:
        t = time.time()
        HEADS[key] = rf.Head(sex, kind, hair)
        print('  head %s %.1fs' % (str(key), time.time() - t), flush=True)
    return HEADS[key]


def audit_one(visual, sex, H, band, M=None):
    Qb = band.samples(sex, band.band_faces, 6000)
    Qr = band.samples(sex, band.rigid_faces, 12000, seed=9)
    if M is not None:
        if isinstance(M, Fit):
            Qb, Qr = M.apply(Qb), M.apply(Qr)
        else:
            Qb, Qr = rf.apply(M, Qb), rf.apply(M, Qr)
    skin = head(sex, H.kind)
    st, gaps, ys = zone_stats(H, Qb, Qr, skin)
    ratio, rmin, rmax = scale_error(H, Qb)
    rec = dict(piece=visual, sex=sex, head=H.kind, hair=H.hair_style or 'none', zones=st,
               heights=heights(H, st), radius_ratio=round(ratio, 3),
               radius_ratio_range=[round(rmin, 3), round(rmax, 3)],
               skull_ratio=round(skull_ratio(H, Qb, skin), 3),
               hair_lift_mm=round(float(np.median(H.lift[H.lift > 0]) * 1000), 1) if (H.lift > 0).any() else 0.0)
    return rec


def fmt(rec):
    z = rec['zones']
    parts = []
    for k in ('front', 'left', 'back', 'right'):
        v = z.get(k)
        parts.append('%s %s' % (k[0].upper(), '-' if v is None else '%5.1f/%5.1f/%5.1f' % (v['gap_min'], v['gap_med'], v['gap_max'])))
    hh = rec['heights']
    return ('%3d %-6s %-6s %-22s %s | front+brow %s ear L/R %s/%s back+occ %s back-front %s | skull x%.3f lift %s | rigid skin min %s'
            % (rec['piece'], rec['sex'], rec['head'], rec['hair'], '  '.join(parts), hh['front_over_brow_mm'],
               hh['left_over_ear_mm'], hh['right_over_ear_mm'], hh['back_over_occ_mm'], hh.get('back_minus_front_mm'),
               rec['skull_ratio'], rec['hair_lift_mm'], z['rigid_min_skin_gap_mm']))


def cmd_audit(args):
    pieces = [int(v) for v in args.pieces.split(',')] if args.pieces else OPEN
    rows = []
    for v in pieces:
        band = Band(v)
        for sex in sexes():
            hairs = [None]
            hair_default = {'female': 'mira_bun', 'male': 'rowan_shag'}[sex]
            shipped_long = 'luminous_%s_long_%s' % (sex, sex)
            for kind, hair in (('rl', None), ('rl', hair_default), ('legacy', None), ('legacy', shipped_long)):
                H = head(sex, kind, hair)
                rec = audit_one(v, sex, H, band)
                rows.append(rec)
                print(fmt(rec), flush=True)
    os.makedirs(h.OUT, exist_ok=True)
    json.dump(rows, open(h.OUT + '/audit_current.json', 'w'), indent=1)


def hair_styles(sex, which):
    rl = h.rl_hair_styles()
    legacy = ['legacy:' + s for s in h.LEGACY_HAIR_STYLES if os.path.exists(h.LEGACY_HAIR.format(sex=sex, style=s))]
    if which == 'none':
        return []
    if which == 'all':
        return rl + legacy
    return [s for s in which.split(',') if s]


SHIPPED_BODIES = ('luminous_female', 'luminous_male')


def _fit_head_set(v, band, rec, audit_rows, base, sex, kind, styles):
    """Bald fit `base`, then one per hairstyle `base/<style>` and `base/*`."""
    skin = head(sex, kind)
    print('%d %s bald' % (v, base), flush=True)
    sol = solve(skin, band, sex, verbose=True)
    rec['fits'][base] = fit_record(sol)
    row = audit_one(v, sex, skin, band, sol['fit'])
    row['fit'] = base
    audit_rows.append(row)
    print('   ' + fmt(row), flush=True)
    if rec['coversHair']:
        return
    fallback = []
    for style in styles:
        H = head(sex, kind, style)
        sol_h = solve(H, band, sex, skin_head=skin, verbose=True)
        rec['fits']['%s/%s' % (base, style)] = fit_record(sol_h)
        row = audit_one(v, sex, H, band, sol_h['fit'])
        row['fit'] = '%s/%s' % (base, style)
        audit_rows.append(row)
        print('   ' + fmt(row), flush=True)
        fallback.append((style, float(H.lift.mean())))
    if fallback:
        # other hair: the fit over the style with the median lift
        fallback.sort(key=lambda t: t[1])
        rec['fits'][base + '/*'] = rec['fits']['%s/%s' % (base, fallback[len(fallback) // 2][0])]


def cmd_fit(args):
    pieces = [int(v) for v in args.pieces.split(',')] if args.pieces else OPEN
    global SEXES
    if args.sex:
        SEXES = (args.sex,)
    out = args.out or FIT_JSON
    data = json.load(open(out, encoding='utf-8')) if os.path.exists(out) else {}
    data['version'] = 2
    data['about'] = (
        'Per-piece fit of OPEN headwear (circlets, bands, crowns, a veil on a band). Generated by '
        '.local/rl-heads/scripts/headwear/fit_open_headwear.py; read by src/actors/rl_head/rl_headwear_fit.gd. '
        'fits[<sex>] / fits[<sex>/<hairstyle>] are for an actor with an RL head (bald / over that RL '
        'hairstyle); fits[<body>] / fits[<body>/<hairstyle file stem>] for a shipped head of a body listed '
        'in shippedBodies (an actor without an RL head); fits[<key>/*] is the fallback for other hair. '
        'The band rests on the skull plus the hair under-layer (capped lift), about level, forehead 2.5-3.5 cm '
        'over the brows, back never under the occipital bulge. Each fit is a model-space rest transform '
        'applied after the shipped socket placement: scale (aniso widens x and narrows z by sqrt(aniso)) '
        'and pitch about pivot, then offset; then warp: the distance of every vertex from warp.axis '
        '(through warp.origin) is multiplied by k(phi) = cos[0] + sum cos[m] cos(m phi) + sin[m-1] sin(m phi), '
        'phi in the band plane from the front (+Z) towards +X, faded out below the band over fadeBelow. '
        'trails[<sex>]: the rule that picks the hanging cloth (vertices below the band plane in components '
        'reaching minReach below it, weighted start..full, outside frontSector) and how long it stays '
        '(length, of its authored metric length; keepLengthSector keeps the fitted length in front).')
    data['shippedBodies'] = list(SHIPPED_BODIES)
    data['shippedBodiesAbout'] = ('Shipped (non-RL) heads of these bodies take fits[<body>...] too. '
                                  'Other race bodies are left as shipped: their race heads and variants need fits '
                                  'of their own. RL_HEADWEAR_FIT=0 turns every fit off, =rl keeps only the RL-head fits.')
    pieces_out = data.setdefault('pieces', {})
    audit_rows = []
    for v in pieces:
        band = Band(v)
        spec = SPEC[v]
        rec = dict(name=h.model(v)['name'], label=spec['label'],
                   coversHair=bool(h.piece(v, 'female')['coversHair']), fits={}, trails={})
        for sex in sexes():
            rec['trails'][sex] = band.trail_mask_runtime(sex)
            if rec['trails'][sex] is not None:
                rec['trails'][sex]['length'] = spec['trails']['length']
            _fit_head_set(v, band, rec, audit_rows, sex, sex, 'rl', hair_styles(sex, args.hair))
            if not args.rl_only:
                body = 'luminous_' + sex
                stems = [] if args.hair == 'none' else list(h.shipped_hair_styles(sex))
                if args.shipped_hair:
                    stems = [st.replace('<sex>', sex) for st in args.shipped_hair.split(',')]
                _fit_head_set(v, band, rec, audit_rows, body, sex, 'legacy', stems)
        pieces_out[str(v)] = rec
        json.dump(data, open(out, 'w', encoding='utf-8', newline='\n'), indent=1)
    audit_out = h.OUT + ('/audit_fitted.json' if not args.out
                         else '/audit_fitted_%s%s.json' % (args.pieces.replace(',', '_'),
                                                          '_' + args.sex if args.sex else ''))
    json.dump(audit_rows, open(audit_out, 'w'), indent=1)


def cmd_merge(args):
    """Merge per-piece runs (fit --out <part>.json) into the client data file."""
    import glob
    merged = None
    for path in args.parts.split(','):
        d = json.load(open(path, encoding='utf-8'))
        if merged is None:
            merged = d
        else:
            for key, rec in d['pieces'].items():
                if key in merged['pieces']:
                    merged['pieces'][key]['fits'].update(rec['fits'])
                    merged['pieces'][key]['trails'].update({k: v for k, v in rec['trails'].items() if v})
                else:
                    merged['pieces'][key] = rec
    merged['pieces'] = {k: merged['pieces'][k] for k in sorted(merged['pieces'], key=int)}
    json.dump(merged, open(FIT_JSON, 'w', encoding='utf-8', newline='\n'), indent=1)
    audit = []
    for f in sorted(glob.glob(h.OUT + '/audit_fitted_*.json')):
        audit += json.load(open(f))
    json.dump(audit, open(h.OUT + '/audit_fitted.json', 'w'), indent=1)
    print('merged', list(merged['pieces']), len(audit), 'audit rows')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['audit', 'fit', 'merge'])
    ap.add_argument('--out', default='')
    ap.add_argument('--sex', default='')
    ap.add_argument('--shipped-hair', dest='shipped_hair', default='')
    ap.add_argument('--parts', default='')
    ap.add_argument('--pieces', default='')
    ap.add_argument('--hair', default='all')
    ap.add_argument('--rl-only', dest='rl_only', action='store_true')
    args = ap.parse_args()
    {'audit': cmd_audit, 'fit': cmd_fit, 'merge': cmd_merge}[args.cmd](args)


if __name__ == '__main__':
    main()
