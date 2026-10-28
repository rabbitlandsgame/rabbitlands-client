"""Geometry of open headwear on a head: the head's contact surface as a radial
map, the piece's band (the loop that should rest on the head), its trails, and
the fit that seats the band on the target path.

Model space throughout (+Y up, face +Z, +X character left). Azimuth 0 = the
face (+Z), 90 = the character's left (+X); elevation up from horizontal, both
about the cranium centre C.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import trimesh
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import percentile_filter
from scipy.spatial import cKDTree

import hwlib as h

AZ = np.arange(0.0, 360.0, 2.0)
EL = np.arange(-50.0, 80.01, 1.5)
HAIR_REACH = 0.035   # hair farther than this beyond the skin is a lock or a bun, not the cap
CLEAR_SKIN = 0.002   # target band clearance over skin
CLEAR_MIN = 0.001    # no rigid part closer than this to the skin
HAIR_SINK = 0.002    # a band may press this far into the hair mass
# With hair drawn the band rests on the SKULL plus the hair's under-layer: the
# first hair surface over the skin along each direction, never the outer locks,
# and at most LIFT_CAP over the skin (owner review 2026-10-27: a circlet riding
# the outer hair silhouette looks as if it would slide down the neck).
LIFT_CAP = 0.006
LIFT_REACH = 0.040


def sph(az, el):
    az, el = np.radians(az), np.radians(el)
    return np.stack([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)], -1)


def to_sph(v):
    r = np.linalg.norm(v, axis=-1)
    el = np.degrees(np.arcsin(np.clip(v[..., 1] / np.maximum(r, 1e-12), -1, 1)))
    az = np.degrees(np.arctan2(v[..., 0], v[..., 2])) % 360.0
    return az, el, r


def _cast(mesh, origin, dirs, reach=0.4):
    """First and last hit distance per direction (inf / -inf for no hit)."""
    n = len(dirs)
    first = np.full(n, np.inf)
    last = np.full(n, -np.inf)
    allhits = [[] for _ in range(n)]
    for k0 in range(0, n, 4000):
        d = dirs[k0:k0 + 4000]
        o = np.repeat(origin[None], len(d), 0)
        loc, ray, _ = mesh.ray.intersects_location(o, d, multiple_hits=True)
        if len(ray):
            dist = np.linalg.norm(loc - o[ray], axis=1)
            ok = dist < reach
            ray, dist = ray[ok] + k0, dist[ok]
            np.minimum.at(first, ray, dist)
            np.maximum.at(last, ray, dist)
            for r_, d_ in zip(ray, dist):
                allhits[r_].append(d_)
    return first, last, allhits


class Head:
    """A head's contact surface (skin, optionally hair) as radial maps about C."""

    def __init__(self, sex, kind='rl', hair=None, controls=None, hair_mode='cap'):
        self.sex, self.kind, self.hair_style = sex, kind, hair
        if kind == 'rl':
            skin = h.rl_head(sex, controls)
            lm = h.landmarks(sex)
            self.eye_y = float((lm['eyeL'][1] + lm['eyeR'][1]) / 2)
        else:
            skin = h.legacy_head(sex, meshes=('body', 'scalp'))
            eyes = h.legacy_head(sex, meshes=('eyes',))
            used = np.unique(eyes['I'])
            self.eye_y = float(eyes['P'][used, 1].mean())
        self.skin = skin
        # cranium centre: mid-sagittal, 3.5 cm over the eyes, half way front to back
        y = self.eye_y + 0.035
        mesh = trimesh.Trimesh(skin['P'], skin['I'], process=False)
        probe = np.array([0.0, y, 0.0])
        fz, _, _ = _cast(mesh, probe, np.array([[0, 0, 1.0], [0, 0, -1.0]]))
        self.C = np.array([0.0, y, (fz[0] - fz[1]) / 2])
        A, E = np.meshgrid(AZ, EL, indexing='ij')
        dirs = sph(A.ravel(), E.ravel())
        first, last, _ = _cast(mesh, self.C, dirs)
        self.R_skin = first.reshape(A.shape)
        self.R_skin_last = last.reshape(A.shape)
        self._fill(self.R_skin)
        self.R = self.R_skin.copy()
        self.R_hair = None
        self.lift = np.zeros_like(self.R_skin)
        if hair:
            hm = h.hair(sex, hair)
            if hm is not None:
                hmesh = trimesh.Trimesh(hm['P'], hm['I'], process=False)
                _, _, allhits = _cast(hmesh, self.C, dirs, 0.5)
                under = np.zeros(len(dirs))
                skin_r = self.R_skin.ravel()
                for k, hits in enumerate(allhits):
                    hs = [d for d in hits if skin_r[k] - 0.004 < d < skin_r[k] + LIFT_REACH]
                    if hs:
                        under[k] = min(hs) - skin_r[k]
                under = under.reshape(A.shape)
                # the under-layer, smoothed so a single card does not decide it
                under = percentile_filter(under, 50, size=(5, 5), mode='wrap')
                self.lift = np.clip(under, 0.0, LIFT_CAP)
                self.R_hair = self.R_skin + self.lift
        # The contact: skin plus the clearance a band keeps over it, or the hair lift.
        self.R = self.R_skin + np.maximum(self.lift, CLEAR_SKIN)
        self._interp = self._make_interp(self.R)
        self._interp_skin = self._make_interp(self.R_skin)
        self._landmarks()

    @staticmethod
    def _fill(R):
        bad = ~np.isfinite(R)
        if bad.any():
            R[bad] = np.nanmax(np.where(np.isfinite(R), R, np.nan))

    @staticmethod
    def _make_interp(R):
        az = np.r_[AZ - 360.0, AZ, AZ + 360.0]
        RR = np.concatenate([R, R, R], 0)
        return RegularGridInterpolator((az, EL), RR, bounds_error=False, fill_value=None)

    def radius(self, az, el, skin_only=False):
        f = self._interp_skin if skin_only else self._interp
        return f(np.stack([np.asarray(az) % 360.0, np.clip(el, EL[0], EL[-1])], -1))

    def gap(self, Q, skin_only=False):
        """Radial gap of points Q over the contact surface (positive = outside)."""
        az, el, r = to_sph(Q - self.C)
        return r - self.radius(az, el, skin_only)

    def surface_point(self, az, el, skin_only=False):
        r = self.radius(az, el, skin_only)
        return self.C + sph(az, el) * np.asarray(r)[..., None]

    def _landmarks(self):
        """Brow ridge, ear tops and occipital bulge from the skin's own shape."""
        C = self.C
        # brow: the most forward point of the forehead/brow profile above the eyes,
        # in the columns over the pupils (x = +-3 cm)
        P = self.skin['P'][np.unique(self.skin['I'])]
        col = P[(np.abs(np.abs(P[:, 0]) - 0.03) < 0.006) & (P[:, 1] > self.eye_y + 0.004)
                & (P[:, 1] < self.eye_y + 0.04)]
        ys = np.arange(self.eye_y + 0.006, self.eye_y + 0.04, 0.002)
        zs = [col[np.abs(col[:, 1] - y) < 0.0015, 2].max() if (np.abs(col[:, 1] - y) < 0.0015).any() else -1
              for y in ys]
        self.brow_y = float(ys[int(np.argmax(zs))])
        # ears: directions at the sides where the ray leaves the skin more than once
        # and the last exit stands > 6 mm proud of the first (the auricle)
        proud = (self.R_skin_last - self.R_skin) > 0.006
        A, E = np.meshgrid(AZ, EL, indexing='ij')
        tops = {}
        for side, centre in (('left', 90.0), ('right', 270.0)):
            sector = proud & (np.abs(((A - centre + 180) % 360) - 180) < 40) & (E > -40) & (E < 30)
            if sector.any():
                # the auricle's highest point, from its proud directions' last exits
                pts = C + sph(A[sector], E[sector]) * self.R_skin_last[sector][:, None]
                tops[side] = float(pts[:, 1].max())
            else:
                tops[side] = float('nan')
        self.ear_top = tops
        # occipital bulge: most posterior point of the mid-sagittal profile
        el = np.arange(-30, 40, 0.5)
        back = self.surface_point(np.full(len(el), 180.0), el, skin_only=True)
        k = int(np.argmin(back[:, 2]))
        self.occ_y = float(back[k, 1])
        self.occ_z = float(back[k, 2])
        top = self.surface_point(np.array([0.0]), np.array([79.0]), skin_only=True)
        self.top_y = float(P[:, 1].max())

    def describe(self):
        return dict(sex=self.sex, kind=self.kind, hair=self.hair_style, C=self.C.round(4).tolist(),
                    eye_y=round(self.eye_y, 4), brow_y=round(self.brow_y, 4),
                    ear_top={k: round(v, 4) for k, v in self.ear_top.items()},
                    occ_y=round(self.occ_y, 4), top_y=round(self.top_y, 4))

    def target_path(self, front=0.028, back=0.0):
        """The target band path: forehead `front` over the brow ridge, just over
        the ears, the occipital bulge `back` over its widest point; returns
        (azimuths, points on the contact surface) of the plane through them."""
        f = np.array([0.0, self.brow_y + front, 0.0])
        b = np.array([0.0, self.occ_y + back, 0.0])
        # forehead / occiput points on the surface at those heights
        f[2] = self._z_at(0.0, f[1])
        b[2] = self._z_at(180.0, b[1])
        ear = max(v for v in self.ear_top.values() if np.isfinite(v)) + 0.008
        return f, b, ear

    def _z_at(self, az, y):
        el = np.arange(-40, 75, 0.25)
        pts = self.surface_point(np.full(len(el), az), el)
        k = int(np.argmin(np.abs(pts[:, 1] - y)))
        return float(pts[k, 2])


# ------------------------------------------------------------------ the piece

class Piece:
    """A placed piece split into its rigid part and its trails."""

    def __init__(self, visual, sex, spec):
        self.visual, self.sex, self.spec = visual, sex, spec
        pc = h.piece(visual, sex)
        self.pc = pc
        self.P, self.I = pc['P'], pc['I']
        self.labels = h.weld_components(self.P, self.I)
        self.trail_w = np.zeros(len(self.P))
        self.mesh = trimesh.Trimesh(self.P, self.I, process=False)

    def set_trails(self, plane_point, plane_normal, start, full, min_reach):
        """Trail weight per vertex: 0 at `start` below the band plane, 1 at `full`,
        only in components reaching `min_reach` below it."""
        n = plane_normal / np.linalg.norm(plane_normal)
        below = (plane_point - self.P) @ n          # positive below the plane
        comp_reach = np.zeros(self.labels.max() + 1)
        np.maximum.at(comp_reach, self.labels, below)
        eligible = comp_reach[self.labels] >= min_reach
        t = np.clip((below - start) / max(full - start, 1e-6), 0, 1)
        self.trail_w = np.where(eligible, t * t * (3 - 2 * t), 0.0)
        return self.trail_w

    def samples(self, n=30000, rigid_only=True, seed=3):
        faces = np.arange(len(self.I))
        if rigid_only:
            faces = faces[(self.trail_w[self.I] < 0.5).all(1)]
        sub = trimesh.Trimesh(self.P, self.I[faces], process=False)
        pts, fi = trimesh.sample.sample_surface(sub, n, seed=seed)
        return pts


def similarity(s, pitch, t, pivot, aniso=1.0):
    """Model-space 4x4: scale (aniso widens x, narrows z) and pitch about pivot, then t."""
    c, sn = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    R = np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]])
    S = np.diag([s * math.sqrt(aniso), s, s / math.sqrt(aniso)])
    M = np.eye(4)
    M[:3, :3] = R @ S
    M[:3, 3] = pivot - M[:3, :3] @ pivot + np.asarray(t)
    return M


def apply(M, P):
    return P @ M[:3, :3].T + M[:3, 3]


def band_bins(head, Q, nbins=72):
    """Per azimuth bin (about the head's vertical axis) the rigid samples' minimum
    radial gap and the height of the sample that has it."""
    az, el, r = to_sph(Q - head.C)
    gap = r - head.radius(az, el)
    b = (az / (360.0 / nbins)).astype(int) % nbins
    order = np.lexsort((gap, b))
    bs, first = np.unique(b[order], return_index=True)
    out_gap = np.full(nbins, np.nan)
    out_y = np.full(nbins, np.nan)
    out_gap[bs] = gap[order][first]
    out_y[bs] = Q[order][first][:, 1]
    return out_gap, out_y


def inner_wall(Q, C, nbins=72, share=0.12):
    """The ring's inner wall: per azimuth bin about C's vertical axis, the samples
    nearest that axis. Returns per-bin mean point (nan where empty)."""
    v = Q - C
    az = np.degrees(np.arctan2(v[:, 0], v[:, 2])) % 360
    rho = np.hypot(v[:, 0], v[:, 2])
    b = (az / (360.0 / nbins)).astype(int) % nbins
    pts = np.full((nbins, 3), np.nan)
    for k in range(nbins):
        m = b == k
        if m.sum() < 3:
            continue
        rr = rho[m]
        cut = np.quantile(rr, share)
        pts[k] = Q[m][rr <= cut + 0.003].mean(0)
    return pts


ZONES = {'front': (-30, 30), 'left': (60, 120), 'back': (150, 210), 'right': (240, 300)}


def zone_of(az_deg):
    a = ((az_deg + 180) % 360) - 180
    for name, (lo, hi) in ZONES.items():
        lo2, hi2 = ((lo + 180) % 360) - 180, ((hi + 180) % 360) - 180
        if lo2 <= hi2:
            if lo2 <= a <= hi2:
                return name
        else:
            if a >= lo2 or a <= hi2:
                return name
    return None


def report(head, Q, wall=None):
    """Per-zone gap stats (mm) of the per-bin minimum gaps, heights of the contact."""
    gaps, ys = band_bins(head, Q)
    centres = (np.arange(72) + 0.5) * 5.0
    out = {}
    for name in ZONES:
        m = np.array([zone_of(a) == name for a in centres]) & np.isfinite(gaps)
        if m.any():
            out[name] = dict(gap_min=float(np.nanmin(gaps[m]) * 1000), gap_med=float(np.nanmedian(gaps[m]) * 1000),
                             gap_max=float(np.nanmax(gaps[m]) * 1000), contact_y=float(np.nanmedian(ys[m])))
        else:
            out[name] = None
    out['coverage'] = float(np.isfinite(gaps).mean())
    return out, gaps, ys
