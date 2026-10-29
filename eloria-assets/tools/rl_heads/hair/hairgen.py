"""hairgen -- guide-curve hair and beard geometry for the RL head prototype.

Library used by build_hair.py / build_beard.py. Everything is authored in body
model space (game space: metres, Y up, the face looks toward +Z), on top of the
head module skin from build/v1 (see headref.Head).

Building blocks
  Scalp            head frame + hairline + root sampling + flow fields
  grow()           guide curves: scalp-hugging phase (height profile above the
                   skin, follows a flow field) then a free phase (stiffness,
                   gravity, collision push-out); deterministic per seed
  shaping          wave, helical curl, smooth noise, tip flick (bend)
  Lock             one generated lock: centreline + kind + section parameters
  mesh builders    tube clumps (tapered, flattened, twisting sections, pointed
                   or split tips), ribbons, strand cards, helical curls
                   (ribbon/tube along a helix around a falling centreline),
                   3-strand braid, torus bun (wrapped clumps + core), and the
                   scalp under-shell (pole-centred grid inside the hairline)

Conventions shared with the runtime contract
  * UV v runs root (0) -> tip (1) along every lock/card. The shell maps v
    along its flow (from or toward its pole).
  * per-vertex `t` (position along the lock, 0..1) -> COLOR_0.G,
    per-lock random `rand` -> COLOR_0.R, `ao` (0 deep/inner .. 1 outer) -> COLOR_0.B.
  * frames: T along the curve, N the "outward" direction (away from the head
    centre / bun / curl axis), B = T x N (the width direction of ribbons/cards).

Angles in specs are degrees, lengths metres unless a key ends in _mm.
"""
import math, zlib
import numpy as np

import headref
from headref import unit, lonlat_dir, dir_lonlat

UP = np.array([0.0, 1.0, 0.0])
DOWN = -UP

# hair_clump.png layout (textures.py): u in [CLUMP_EDGE, 1 - CLUMP_EDGE] is opaque and
# its colour repeats with period CLUMP_PERIOD; the outer CLUMP_EDGE on each side is a
# strand-feathered alpha edge used by ribbons (u 0..1 across) for hairy silhouettes.
# Tubes and the shell stay inside the opaque window.
CLUMP_EDGE = 0.14
CLUMP_PERIOD = 1.0 - 2 * CLUMP_EDGE


# =============================================================== utilities
def rng_for(seed, *keys):
    """Deterministic generator from a seed and any hashable keys (group names...)."""
    h = zlib.crc32(repr((seed,) + keys).encode())
    return np.random.default_rng(h)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def rotate(v, axis, ang):
    """Rodrigues rotation of v (...,3) about unit axis (...,3) by ang (radians, broadcast)."""
    v = np.asarray(v, np.float64); axis = unit(axis)
    ang = np.asarray(ang, np.float64)[..., None]
    c, s = np.cos(ang), np.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * (axis * v).sum(-1, keepdims=True) * (1 - c)


def project_tangent(v, n):
    return v - n * (v * n).sum(-1, keepdims=True)


def arclen(P):
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(d)])


def resample(P, n):
    """n points evenly spaced by arc length along polyline P."""
    s = arclen(P)
    if s[-1] < 1e-9:
        return np.repeat(P[:1], n, 0)
    u = np.linspace(0, s[-1], n)
    return np.stack([np.interp(u, s, P[:, k]) for k in range(3)], 1)


def resample_param(P, n):
    """Like resample() but also returns the arc fraction of each output point."""
    return resample(P, n), np.linspace(0, 1, n)


def smooth_polyline(P, iters=2, lam=0.5):
    P = P.copy()
    for _ in range(iters):
        P[1:-1] = P[1:-1] + lam * (0.5 * (P[:-2] + P[2:]) - P[1:-1])
    return P


def tangents(P):
    T = np.gradient(P, axis=0)
    return unit(T)


def frames(P, ref, twist=None, relax=0.6):
    """Rotation-minimising frames relaxed toward the 'outward' reference.

    ref: per-point outward vectors (n,3) (e.g. P - head centre).
    twist: per-point extra roll about T in radians.
    Returns T, N, B (each n x 3), with N ~ outward and B = T x N.
    """
    n = len(P)
    T = tangents(P)
    ref = np.broadcast_to(ref, P.shape)
    N = np.zeros_like(P)
    r0 = project_tangent(ref[0], T[0])
    if np.linalg.norm(r0) < 1e-6:
        r0 = project_tangent(np.array([0.0, 0.0, 1.0]), T[0])
        if np.linalg.norm(r0) < 1e-6:
            r0 = project_tangent(np.array([1.0, 0.0, 0.0]), T[0])
    N[0] = unit(r0)
    for i in range(1, n):
        # parallel transport of N[i-1] onto T[i]
        a = T[i - 1]; b = T[i]
        ax = np.cross(a, b); s = np.linalg.norm(ax)
        prev = N[i - 1]
        if s > 1e-9:
            prev = rotate(prev, ax / s, math.atan2(s, float(a @ b)))
        prev = unit(project_tangent(prev, b))
        rp = project_tangent(ref[i], b); rl = np.linalg.norm(rp)
        w = relax * min(1.0, rl / (np.linalg.norm(ref[i]) + 1e-12) * 1.5) if rl > 1e-9 else 0.0
        cand = unit(prev * (1 - w) + (rp / max(rl, 1e-12)) * w) if w > 0 else prev
        if np.linalg.norm(cand) < 0.5:
            cand = prev
        N[i] = cand
    if twist is not None:
        N = rotate(N, T, twist)
    B = unit(np.cross(T, N))
    N = unit(np.cross(B, T))
    return T, N, B


def farthest_order(X, start=0):
    """Farthest-point ordering (for spatially even LOD subsets)."""
    X = np.asarray(X, np.float64)
    n = len(X)
    if n == 0:
        return np.zeros(0, int)
    order = [start]
    d = np.linalg.norm(X - X[start], axis=1)
    for _ in range(n - 1):
        i = int(np.argmax(d))
        order.append(i)
        d = np.minimum(d, np.linalg.norm(X - X[i], axis=1))
    return np.array(order)


def periodic_interp(x, xp, fp, period=360.0):
    o = np.argsort(xp); xp = np.asarray(xp)[o]; fp = np.asarray(fp)[o]
    xp2 = np.concatenate([xp - period, xp, xp + period]); fp2 = np.concatenate([fp, fp, fp])
    return np.interp(np.mod(np.asarray(x) - xp[0], period) + xp[0], xp2, fp2)


def circ_smooth(y, k):
    if k <= 1:
        return y
    ker = np.ones(k) / k
    yy = np.concatenate([y[-k:], y, y[:k]])
    return np.convolve(yy, ker, mode='same')[k:-k]


# =============================================================== the scalp
class Scalp:
    """Head frame, hairline and root placement on a headref.Head.

    Head frame: C = sphere centre fitted to the MPFB scalp group; lon/lat as in
    headref (lon 0 = face, +90 = character's left (+X), 180 = back).
    The hairline is a function lat_min(lon): the lowest latitude of MPFB scalp
    vertices per 5-degree longitude bin (smoothed), kept clear of the ears, plus
    style adjustments `adjust` = [[lon, dlat], ...] (negative dlat lowers the
    hairline = more hair) and a global `grow` (degrees).
    Behind the ears the MPFB group stops high, so by default the hairline is
    lowered for |lon| >= nape_from (104 deg) to the skin latitude at height
    nape_y (default: ear-lobe bottom - nape_below_lobe_mm (20 mm)), blended over
    nape_blend degrees. Over the ear it stays ear_margin degrees above the ear.
    """

    def __init__(self, head, hairline=None):
        self.head = head
        self.C = head.C
        hl = hairline or {}
        sc = head.vgroups['scalp']
        lon, lat = dir_lonlat(head.P[sc] - self.C)
        bins = np.arange(-180, 180, 5.0)
        lm = np.full(len(bins), np.nan)
        for i, b in enumerate(bins):
            s = (lon >= b) & (lon < b + 5)
            if s.any():
                lm[i] = lat[s].min()
        ok = ~np.isnan(lm)
        lm = periodic_interp(bins + 2.5, bins[ok] + 2.5, lm[ok])
        lm = circ_smooth(lm, 3)
        # ear clearance: stay a few degrees above the ear over its longitude span
        er = head.vgroups['ears']
        elon, elat = dir_lonlat(head.P[er] - self.C)
        self.ear_lonlat = (elon, elat)
        ear_win = hl.get('ear_window', 2.5)
        ear_margin = hl.get('ear_margin', 1.5)
        # nape: lower the back hairline to a skin height
        if hl.get('nape', True):
            ny = hl.get('nape_y', head.P[er, 1].min() - hl.get('nape_below_lobe_mm', 20.0) * 1e-3)
            alon, alat = dir_lonlat(head.P - self.C)
            nape_from = hl.get('nape_from', 104.0); blend = hl.get('nape_blend', 10.0)
            for i, b in enumerate(bins + 2.5):
                ab = abs(b)
                if ab < nape_from - blend:
                    continue
                s = (np.abs(((alon - b + 180) % 360) - 180) < 3.0) & ~er & (alat < 20)
                if not s.any():
                    continue
                yy = head.P[s, 1]; la = alat[s]
                o = np.argsort(yy)
                lat_ny = float(np.interp(ny, yy[o], la[o]))
                f = smoothstep((ab - (nape_from - blend)) / max(blend, 1e-3))
                lm[i] = min(lm[i], lm[i] * (1 - f) + lat_ny * f)
        for i, b in enumerate(bins + 2.5):
            s = np.abs(((elon - b + 180) % 360) - 180) < ear_win
            if s.any():
                lm[i] = max(lm[i], elat[s].max() + ear_margin)
        lm = circ_smooth(lm, 3)
        self.hl_lon = bins + 2.5
        self.hl_base = lm.copy()
        adj = np.zeros_like(lm) - hl.get('grow', 0.0)
        if hl.get('adjust'):
            a = np.array(hl['adjust'], np.float64)
            adj += periodic_interp(self.hl_lon, a[:, 0], a[:, 1])
        if hl.get('noise'):
            # soft irregular hairline (seeded, smooth in lon)
            r = np.random.default_rng(hl.get('seed', 3))
            nz = circ_smooth(r.normal(0, 1, len(lm)), 2)
            adj += nz / max(np.abs(nz).max(), 1e-6) * hl['noise']
        self.hl_lat = lm + adj
        # re-apply the ear clearance after adjustments
        for i, b in enumerate(self.hl_lon):
            s = np.abs(((elon - b + 180) % 360) - 180) < ear_win
            if s.any():
                self.hl_lat[i] = max(self.hl_lat[i], elat[s].max() + ear_margin * 0.5)

    # ---------------------------------------------------------- hairline
    def hairline(self, lon):
        return periodic_interp(lon, self.hl_lon, self.hl_lat)

    def inside(self, lon, lat, margin=0.0):
        return np.asarray(lat) >= self.hairline(lon) + margin

    # ---------------------------------------------------------- points
    def point(self, lon, lat, height=0.0):
        """Skin point(s) at lon/lat (outermost hit from C, ears excluded) + height along normal."""
        P, N, ok = self.head.frame_point(lon, lat, height)
        if not ok.all():
            # fall back to the closest skin point of the sphere guess
            bad = ~ok
            g = self.C + lonlat_dir(np.atleast_1d(lon)[bad], np.atleast_1d(lat)[bad]) * self.head.R
            cp, _, tri, bc = self.head.closest(g)
            n = unit((self.head.N[self.head.T[tri]] * bc[:, :, None]).sum(1))
            P[bad] = cp + n * np.reshape(np.broadcast_to(height, ok.shape)[bad], (-1, 1))
            N[bad] = n
        return P, N

    def resolve_point(self, spec):
        """A point spec -> xyz. Accepts [lon, lat], [lon, lat, h_mm], {"lon","lat","h_mm"},
        {"xyz": [x,y,z]} (absolute) or {"rel": [x,y,z]} (relative to C)."""
        if isinstance(spec, dict):
            if 'xyz' in spec:
                return np.array(spec['xyz'], np.float64)
            if 'rel' in spec:
                return self.C + np.array(spec['rel'], np.float64)
            lon, lat, h = spec['lon'], spec['lat'], spec.get('h_mm', 0.0)
        else:
            lon, lat = spec[0], spec[1]
            h = spec[2] if len(spec) > 2 else 0.0
        P, _ = self.point(lon, lat, h * 1e-3)
        return P[0]

    def hairline_roots(self, spec, count, rng):
        """Roots just inside the hairline: lon evenly spaced over spec['lon'] (with
        jitter), lat = hairline(lon) + inset_deg + U(0, depth_deg)."""
        lo0, lo1 = spec.get('lon', [-180, 180])
        lon = np.linspace(lo0, lo1, count, endpoint=(lo1 - lo0) < 359)
        lon = lon + rng.normal(0, spec.get('jitter', 0.35) * (lo1 - lo0) / max(count, 1), count)
        lon = (lon + 180) % 360 - 180
        lat = self.hairline(lon) + spec.get('inset_deg', 1.0) + rng.uniform(0, spec.get('depth_deg', 2.0), count)
        return lon, lat

    def sample_roots(self, region, count, rng, margin=2.0, candidates=12, exclude=None):
        """Best-candidate (blue-noise) lon/lat samples inside a lon/lat box and the hairline.

        region: {"lon": [a, b], "lat": [c, d]} (lon range may wrap past 180),
        optional "mirror": true to sample one side (lon >= 0 half of the box) and mirror it.
        exclude: [(unit direction from C, degrees), ...] cones without roots (e.g. the whorl).
        """
        lo0, lo1 = region.get('lon', [-180, 180])
        la0, la1 = region.get('lat', [-90, 90])
        mirror = region.get('mirror', False)
        n = (count + 1) // 2 if mirror else count
        out = []

        def draw(k):
            lon = rng.uniform(lo0, lo1, k)
            z = rng.uniform(math.sin(math.radians(la0)), math.sin(math.radians(la1)), k)
            lat = np.degrees(np.arcsin(z))
            lon = (lon + 180) % 360 - 180
            m = self.inside(lon, lat, margin)
            for dvec, deg in (exclude or []):
                m &= (lonlat_dir(lon, lat) @ dvec) < math.cos(math.radians(deg))
            return lon[m], lat[m]

        tries = 0
        while len(out) < n and tries < n * 40:
            tries += 1
            lon, lat = draw(candidates)
            if len(lon) == 0:
                continue
            if not out:
                out.append((lon[0], lat[0])); continue
            D = lonlat_dir(lon, lat)
            E = lonlat_dir(np.array([o[0] for o in out]), np.array([o[1] for o in out]))
            dmin = (1 - D @ E.T).min(1)
            k = int(np.argmax(dmin))
            out.append((lon[k], lat[k]))
        lon = np.array([o[0] for o in out]); lat = np.array([o[1] for o in out])
        if mirror:
            lon = np.concatenate([lon, -lon])[:count]
            lat = np.concatenate([lat, lat])[:count]
        return lon, lat


# =============================================================== flow fields
def make_flow(spec, scalp):
    """Flow field spec -> f(P (n,3)) -> unit directions (n,3).

    {"type": "toward", "point": <point spec>}      sweep toward a point (bun)
    {"type": "away",   "point": <point spec>}      radial from a whorl
    {"type": "dir",    "vec": [x, y, z]}           constant direction
    {"type": "down"}                              gravity direction
    {"type": "side", "vec": [x,y,z], "mirror": true}  constant, x mirrored by side
    {"type": "mix", "fields": [[w, spec], ...]}    weighted sum
    Any field may carry "jitter" (degrees) applied per lock by the grower.
    """
    t = spec.get('type', 'down')
    if t == 'toward':
        Q = scalp.resolve_point(spec['point'])
        return lambda P: unit(Q - P)
    if t == 'away':
        Q = scalp.resolve_point(spec['point'])
        return lambda P: unit(P - Q)
    if t == 'dir':
        v = unit(np.array(spec['vec'], np.float64))
        return lambda P: np.broadcast_to(v, P.shape).copy()
    if t == 'side':
        v = np.array(spec['vec'], np.float64)

        def f(P):
            w = np.broadcast_to(v, P.shape).copy()
            w[:, 0] *= np.where(P[:, 0] >= 0, 1.0, -1.0)
            return unit(w)
        return f
    if t == 'down':
        return lambda P: np.broadcast_to(DOWN, P.shape).copy()
    if t == 'mix':
        fs = [(w, make_flow(s, scalp)) for w, s in spec['fields']]
        return lambda P: unit(sum(w * f(P) for w, f in fs))
    raise ValueError('unknown flow type %r' % t)


# =============================================================== growth
def grow(scalp, P0, N0, lengths, params, rng, flow, collide_margin=0.003):
    """Grow guide curves for a batch of locks.

    P0, N0: root skin points and normals (n,3). lengths: (n,) metres.
    params (dict, all optional):
      steps        samples per curve (fine; default 40)
      hug          fraction of the length that follows the scalp (0..1)
      height_mm    [h_root, h_hug_end] height above the skin while hugging (smoothstep,
                   raised to height_ease (default 1; >1 keeps the lock low for longer)),
                   or [h0, h1, ..., hn]: monotone cubic through evenly spaced control
                   heights over the hug part (e.g. a bulge for side volume)
      cross        per-lock persistent deviation from the flow (degrees, sd) so
                   neighbouring locks cross instead of running parallel
      via          (n_way, 3) waypoints followed in order while hugging (each lock
                   heads for the next one until within via_radius_mm, with a per-lock
                   offset of via_jitter_mm; via_stack k shifts each lock's waypoints
                   by k x its root height above the group mean), then the flow field
      lift         initial elevation off the tangent plane (degrees)
      gravity      0..1, how strongly free hair turns toward down
      stiffness    0..1, resistance to turning in the free phase
      jitter       random initial direction spread (degrees)
      min_mm       minimum clearance kept in the free phase (default 3)
    Returns list of (steps, 3) arrays.
    """
    n = len(P0)
    steps = int(params.get('steps', 40))
    hug = float(params.get('hug', 0.6))
    hlist = [x * 1e-3 for x in params.get('height_mm', [4.0, 6.0])]
    h0, h1 = hlist[0], hlist[-1]
    if len(hlist) > 2:
        from scipy.interpolate import PchipInterpolator
        hfun = PchipInterpolator(np.linspace(0, 1, len(hlist)), hlist)
    else:
        hfun = None
    cross = np.radians(rng.normal(0, params.get('cross', 0.0), n))
    via = params.get('via')
    if via is not None and len(via):
        via = np.asarray(via, np.float64)
        voff = rng.normal(0, params.get('via_jitter_mm', 5.0) * 1e-3, (n, len(via), 3))
        # via_stack: keep the locks' relative height along the path (a sheet, not a band)
        voff[:, :, 1] += params.get('via_stack', 0.0) * (P0[:, 1] - P0[:, 1].mean())[:, None]
        vidx = np.zeros(n, np.int64)
        vrad = params.get('via_radius_mm', 15.0) * 1e-3
    lift = math.radians(params.get('lift', 0.0))
    grav = float(params.get('gravity', 0.5))
    stiff = float(params.get('stiffness', 0.5))
    jit = math.radians(params.get('jitter', 8.0))
    hmin = params.get('min_mm', 3.0) * 1e-3
    head = scalp.head
    ds = lengths / (steps - 1)
    p = P0 + N0 * h0
    d = project_tangent(flow(p), N0)
    bad = np.linalg.norm(d, axis=1) < 1e-6
    d[bad] = project_tangent(np.broadcast_to(DOWN, d[bad].shape), N0[bad])
    d = unit(d)
    # jitter around the normal, then lift off the surface
    d = rotate(d, N0, rng.normal(0, jit, n))
    side = unit(np.cross(N0, d))
    d = rotate(d, side, -lift * np.ones(n))  # rotate toward +N (side = N x d -> negative angle lifts)
    if (d * N0).sum(1).mean() < 0 and lift > 0:
        d = rotate(d, side, 2 * lift * np.ones(n))
    out = np.zeros((n, steps, 3)); out[:, 0] = p
    for k in range(1, steps):
        t = k / (steps - 1)
        hugging = t <= hug + 1e-9
        f = flow(p)
        if hugging:
            cp, dist, tri, bc = head.closest(p)
            nrm = unit((head.N[head.T[tri]] * bc[:, :, None]).sum(1))
            if via is not None and len(via):
                active = vidx < len(via)
                if active.any():
                    W = via[np.minimum(vidx, len(via) - 1)] + voff[np.arange(n), np.minimum(vidx, len(via) - 1)]
                    reached = active & (np.linalg.norm(W - p, axis=1) < vrad)
                    vidx[reached] += 1
                    active = vidx < len(via)
                    W = via[np.minimum(vidx, len(via) - 1)] + voff[np.arange(n), np.minimum(vidx, len(via) - 1)]
                    f = np.where(active[:, None], unit(W - p), f)
            tgt = unit(project_tangent(f, nrm))
            if params.get('cross'):
                tgt = unit(rotate(tgt, nrm, cross))
            rate = 0.5
        else:
            g = grav * smoothstep((t - hug) / max(1e-3, 0.5 * (1 - hug))) if hug < 1 else grav
            tgt = unit(f * (1 - g) + DOWN * g)
            rate = (1 - stiff) * 0.35 + 0.02
        d = unit(d + (tgt - d) * rate)
        pn = p + d * ds[:, None]
        if hugging:
            if hfun is not None:
                hh = np.maximum(hfun(min(1.0, t / max(hug, 1e-6))), 0.0)
            else:
                hh = h0 + (h1 - h0) * smoothstep(t / max(hug, 1e-6)) ** params.get('height_ease', 1.0)
            cp, dist, tri, bc = head.closest(pn)
            nrm = unit((head.N[head.T[tri]] * bc[:, :, None]).sum(1))
            # keep the requested height above the skull (and never inside)
            target = cp + nrm * hh
            # lifting locks (h grows) rise smoothly instead of snapping
            pn = target
        else:
            sd, cp, nrm = head.signed(pn)
            low = sd < hmin
            if low.any():
                pn[low] = cp[low] + nrm[low] * hmin
        step = pn - p
        L = np.linalg.norm(step, axis=1, keepdims=True)
        d = np.where(L > 1e-9, step / np.maximum(L, 1e-12), d)
        # keep arc length per step: rescale the displacement to ds
        pn = p + d * ds[:, None]
        out[:, k] = pn
        p = pn
    return [out[i] for i in range(n)]


# =============================================================== shaping
def shape_curve(C, params, rng, center):
    """Wave, smooth noise and tip flick applied to a guide curve (n,3).

    params: wave {amp_mm, cycles}, noise_mm, flick {angle, from, dir: out|up|side},
            attract {point, from, strength}: pull the tip part toward a point (e.g. into the bun core)
    center: point used for 'outward'.
    """
    n = len(C)
    t = np.linspace(0, 1, n)
    T, N, B = frames(C, C - center)
    out = C.copy()
    w = params.get('wave')
    if w:
        amp = w.get('amp_mm', 3.0) * 1e-3 * rng.uniform(0.6, 1.2)
        cyc = w.get('cycles', 1.5) * rng.uniform(0.8, 1.25)
        ph = rng.uniform(0, 2 * math.pi)
        env = smoothstep(t / 0.2)
        out = out + B * (amp * env * np.sin(2 * math.pi * cyc * t + ph))[:, None]
        out = out + N * (0.35 * amp * env * np.sin(2 * math.pi * cyc * t + ph + 1.3))[:, None]
    nz = params.get('noise_mm', 0.0)
    if nz:
        k = max(3, n // 6)
        ctrl = rng.normal(0, nz * 1e-3, (k, 3))
        ctrl[0] = 0
        tt = np.linspace(0, 1, k)
        noise = np.stack([np.interp(t, tt, ctrl[:, j]) for j in range(3)], 1)
        noise = smooth_polyline(noise, 3)
        out = out + noise * smoothstep(t / 0.25)[:, None]
    at = params.get('attract')
    if at and at.get('xyz') is not None:
        Q = np.asarray(at['xyz'], np.float64)
        t0 = at.get('from', 0.7)
        k = smoothstep((t - t0) / max(1 - t0, 1e-3)) * at.get('strength', 0.8)
        out = out + (Q - out) * k[:, None]
        out = smooth_polyline(out, 2)
    fl = params.get('flick')
    if fl:
        ang = math.radians(fl.get('angle', 25.0)) * rng.uniform(0.6, 1.3)
        t0 = fl.get('from', 0.7)
        i0 = int(round(t0 * (n - 1)))
        if i0 < n - 1:
            T, N, B = frames(out, out - center)
            mode = fl.get('dir', 'out')
            # rotation axis: bend the tip toward N (outward) or toward +Y
            if mode == 'up':
                target = UP
            elif mode == 'side':
                target = B[i0] * (1 if rng.random() < 0.5 else -1)
            else:
                target = N[i0]
            axis = unit(np.cross(T[i0], target))
            if np.linalg.norm(axis) > 1e-6:
                piv = out[i0].copy()
                for i in range(i0 + 1, n):
                    a = ang * ((i - i0) / (n - 1 - i0)) ** 1.0
                    out[i] = piv + rotate(out[i] - piv, axis, a)
                # progressive bend: integrate so the curve turns smoothly
                out[i0:] = smooth_polyline(out[i0:], 2)
    return out


def helix(axis_curve, radius_mm, pitch_mm, rng, start=0.08, grow=0.4, center=None, flatten=1.0):
    """Helical curl around a falling centreline (n,3) -> denser (m,3) curve and its
    axis param (fraction of the centreline length for each output point).

    radius grows from 35% at `start` to 100% by start+grow; pitch in mm per turn.
    """
    L = arclen(axis_curve)[-1]
    turns = L / (pitch_mm * 1e-3)
    m = int(max(24, min(220, turns * 12 + 8)))
    A, s = resample_param(axis_curve, m)
    ref = (A - center) if center is not None else np.broadcast_to(np.array([0, 0, 1.0]), A.shape)
    T, N, B = frames(A, ref)
    ph0 = rng.uniform(0, 2 * math.pi)
    hand = 1.0 if rng.random() < 0.5 else -1.0
    ang = ph0 + hand * 2 * math.pi * turns * s
    r = radius_mm * 1e-3 * (0.35 + 0.65 * smoothstep((s - start) / max(grow, 1e-3)))
    r = r * np.where(s < start, smoothstep(s / max(start, 1e-3)), 1.0)
    # flatten < 1 squashes the helix toward the head (an S-wave seen from the front)
    P = A + (np.cos(ang) * r * flatten)[:, None] * N + (np.sin(ang) * r)[:, None] * B
    return P, s, A


# =============================================================== locks
class Lock:
    """One generated lock (centreline + how to mesh it).

    kind: 'clump' (tube), 'ribbon', 'card', 'curl' (helix, meshed as ribbon or tube)
    sec : section parameters (width, thickness in metres; sides; taper ...)
    root: scalp point used as the morph 'lock root' and for spring chains
    axis: the centreline for curls (helix axis); None -> same as pts
    """
    __slots__ = ('pts', 'kind', 'sec', 'rand', 'root', 'center', 'group', 'lods', 'spring', 'axis',
                 'axis_t', 'idx', 'uoff', 'col', 'order', 'chain_from')

    def __init__(self, pts, kind, sec, rand, root, center, group, lods=(0, 1, 2), spring=None,
                 axis=None, axis_t=None, col=0, chain_from=0.0):
        self.pts = pts; self.kind = kind; self.sec = sec; self.rand = float(rand); self.root = root
        self.center = center; self.group = group; self.lods = set(lods); self.spring = spring
        self.axis = axis; self.axis_t = axis_t; self.idx = -1; self.uoff = float(rand) * 7.31 % 1.0
        self.col = col; self.order = 0; self.chain_from = chain_from


# =============================================================== grooming (length)
def extend_polyline(P, extra, droop=0.9):
    """Continue a polyline past its end by `extra` metres: along the end tangent,
    bending toward gravity (droop = fraction of a right angle over the extension)."""
    if extra <= 0:
        return P
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    ds = max(float(np.median(seg)) if len(seg) else 0.004, 1e-4)
    m = max(1, int(np.ceil(extra / ds)))
    d = unit(P[-1] - P[-2]) if len(P) > 1 else DOWN
    axis = unit(np.cross(d, DOWN))
    ang_total = math.acos(np.clip(float(d @ DOWN), -1, 1)) * droop
    out, p = [], P[-1].copy()
    for i in range(m):
        a = ang_total * (i + 1) / m
        di = rotate(d, axis, a) if np.linalg.norm(axis) > 1e-6 else d
        p = p + di * (extra / m)
        out.append(p.copy())
    return np.vstack([P, np.array(out)])


def rescaled_lock(lock, k):
    """A copy of `lock` whose growth curve is (1 + k) x as long, roots pinned, same
    point count (so meshing gives the same topology). Curls keep their helix offsets
    per parameter around the rescaled axis (stretched / compressed ringlets)."""
    new = Lock.__new__(Lock)
    for a in Lock.__slots__:
        setattr(new, a, getattr(lock, a))
    if lock.axis is not None:
        A = lock.axis; n = len(A)
        L = arclen(A)[-1]
        A2 = _resample_n(A, L * (1 + k), n)
        new.axis = A2
        new.pts = A2 + (lock.pts - A)
    else:
        P = lock.pts; n = len(P)
        L = arclen(P)[-1]
        new.pts = _resample_n(P, L * (1 + k), n)
    return new


def _resample_n(P, length, n):
    s = arclen(P)
    if length > s[-1]:
        P = extend_polyline(P, length - s[-1]); s = arclen(P)
    u = np.linspace(0, length, n)
    return np.stack([np.interp(u, s, P[:, k]) for k in range(3)], 1)


# =============================================================== mesh data
class MeshPart:
    """Growing vertex/triangle arrays for one material."""

    def __init__(self):
        self.P, self.N, self.UV, self.T = [], [], [], []
        self.t, self.rand, self.lock, self.n = [], [], [], 0

    def add(self, P, N, UV, T, t, rand, lock):
        self.P.append(P); self.N.append(N); self.UV.append(UV); self.T.append(T + self.n)
        self.t.append(t); self.rand.append(np.full(len(P), rand)); self.lock.append(np.full(len(P), lock, np.int64))
        self.n += len(P)

    def arrays(self):
        if not self.P:
            return None
        return dict(P=np.concatenate(self.P), N=np.concatenate(self.N), UV=np.concatenate(self.UV),
                    T=np.concatenate(self.T).astype(np.int64), t=np.concatenate(self.t),
                    rand=np.concatenate(self.rand), lock=np.concatenate(self.lock))

    @property
    def tris(self):
        return int(sum(len(t) for t in self.T))


def width_profile(t, w0, root=0.75, belly=0.25, tip_start=0.55, tip_pow=1.2, tip_min=0.0):
    """Section width along the lock: narrower root, full belly, pointed tip."""
    a = root + (1 - root) * smoothstep(t / max(belly, 1e-3))
    u = np.clip((t - tip_start) / max(1 - tip_start, 1e-3), 0, 1)
    b = (1 - u) ** tip_pow
    return w0 * a * np.maximum(b, tip_min)


def tube_mesh(C, ref, w, th, sides, twist=None, inner_flat=0.6, u_rep=1.0, uoff=0.0, tip_point=True,
              t_param=None):
    """Tube along C with an elliptical (flattened, inner side flatter) section.
    w/th: per-point width/thickness. Returns P, N, UV, T, t."""
    n = len(C)
    t = np.linspace(0, 1, n) if t_param is None else t_param
    Tn, N, B = frames(C, ref, twist)
    K = int(sides)
    a = np.linspace(0, 2 * math.pi, K + 1) - math.pi / 2   # seam (k = 0 / K) on the inner side
    ca, sa = np.cos(a), np.sin(a)
    flat = np.where(sa < 0, inner_flat, 1.0)
    hw = (w / 2)[:, None]; ht = (th / 2)[:, None]
    P = C[:, None, :] + (ca[None] * hw)[..., None] * B[:, None, :] + (sa[None] * flat[None] * ht)[..., None] * N[:, None, :]
    # ellipse normals (taper ignored)
    nb = ca[None] / np.maximum(hw, 1e-5); nn = sa[None] / np.maximum(ht * flat[None], 1e-5)
    Nn = unit(nb[..., None] * B[:, None, :] + nn[..., None] * N[:, None, :])
    UV = np.zeros((n, K + 1, 2))
    # stay inside the opaque window of the clump texture (seam on the scalp side)
    span = min(1.0, max(0.2, u_rep))
    u0 = (uoff % 1.0) * (1.0 - span)
    UV[..., 0] = CLUMP_EDGE + CLUMP_PERIOD * (u0 + span * (np.arange(K + 1) / K))[None]
    UV[..., 1] = t[:, None]
    tt = np.repeat(t[:, None], K + 1, 1)
    end = n
    if tip_point:
        end = n - 1   # last ring replaced by a tip vertex
    P2 = P[:end].reshape(-1, 3); N2 = Nn[:end].reshape(-1, 3); UV2 = UV[:end].reshape(-1, 2); t2 = tt[:end].ravel()
    tris = []
    R = K + 1
    for i in range(end - 1):
        for k in range(K):
            a0 = i * R + k; a1 = a0 + 1; b0 = a0 + R; b1 = b0 + 1
            tris.append([a0, b0, a1]); tris.append([a1, b0, b1])
    if tip_point:
        tip = len(P2)
        P2 = np.vstack([P2, C[-1:]]); N2 = np.vstack([N2, Tn[-1:]])
        UV2 = np.vstack([UV2, [[CLUMP_EDGE + CLUMP_PERIOD * (u0 + 0.5 * span), t[-1]]]]); t2 = np.concatenate([t2, [t[-1]]])
        i = end - 1
        for k in range(K):
            tris.append([i * R + k, tip, i * R + k + 1])
    T = np.array(tris, np.int64)
    return P2, N2, UV2, T, t2


def ribbon_mesh(C, ref, w, cup=0.25, twist=None, u_rep=1.0, uoff=0.0, t_param=None, tilt=0.45, across=3,
                full_u=True, droop=None):
    """Strip `across` vertices wide, cupped (parabolic arch of height cup * width toward
    N = outward), double-sided material. full_u: u runs 0..1 across, so the clump
    texture's feathered alpha edges make hairy silhouettes; otherwise u stays in the
    opaque window. droop (per point, metres): the arch edges sink toward the head
    so wide ribbons hug the skull instead of standing off as planks."""
    n = len(C)
    t = np.linspace(0, 1, n) if t_param is None else t_param
    Tn, N, B = frames(C, ref, twist)
    m = max(3, int(across))
    x = np.linspace(-0.5, 0.5, m)
    hgt = cup * w[:, None] * (1 - 4 * x[None] ** 2)
    if droop is not None:
        hgt = hgt - np.asarray(droop)[:, None] * (4 * x[None] ** 2)
    P = C[:, None, :] + (x[None] * w[:, None])[..., None] * B[:, None, :] + hgt[..., None] * N[:, None, :]
    slope = -8 * cup * x                     # d(height)/d(lateral)
    Nn = unit(N[:, None, :] - (slope[None, :, None] - tilt * 2 * x[None, :, None]) * B[:, None, :])
    UV = np.zeros((n, m, 2))
    if full_u:
        UV[..., 0] = (x + 0.5)[None]
    else:
        span = min(1.0, max(0.2, u_rep)); u0 = (uoff % 1.0) * (1 - span)
        UV[..., 0] = CLUMP_EDGE + CLUMP_PERIOD * (u0 + span * (x + 0.5))[None]
    UV[..., 1] = t[:, None]
    tt = np.repeat(t[:, None], m, 1)
    tris = []
    for i in range(n - 1):
        for k in range(m - 1):
            a0 = i * m + k; a1 = a0 + 1; b0 = a0 + m; b1 = b0 + 1
            tris.append([a0, a1, b0]); tris.append([a1, b1, b0])      # front face = +N (outward)
    return P.reshape(-1, 3), Nn.reshape(-1, 3), UV.reshape(-1, 2), np.array(tris, np.int64), tt.ravel()


def card_mesh(C, ref, w, col, ncols=8, twist=None, t_param=None, inset=0.004, bend_normal=0.35):
    """Two-vertex strand card in the strand atlas column `col`. Normals bent outward."""
    n = len(C)
    t = np.linspace(0, 1, n) if t_param is None else t_param
    Tn, N, B = frames(C, ref, twist)
    hw = (w / 2)[:, None]
    P = np.stack([C - B * hw, C + B * hw], 1)
    Nn = np.stack([unit(N - B * bend_normal), unit(N + B * bend_normal)], 1)
    u0 = col / ncols + inset; u1 = (col + 1) / ncols - inset
    UV = np.zeros((n, 2, 2)); UV[..., 0] = np.array([u0, u1])[None]; UV[..., 1] = t[:, None]
    tt = np.repeat(t[:, None], 2, 1)
    tris = []
    for i in range(n - 1):
        a0 = i * 2; a1 = a0 + 1; b0 = a0 + 2; b1 = b0 + 1
        tris.append([a0, a1, b0]); tris.append([a1, b1, b0])          # front face = +N (outward)
    return P.reshape(-1, 3), Nn.reshape(-1, 3), UV.reshape(-1, 2), np.array(tris, np.int64), tt.ravel()


# =============================================================== braid & bun
def braid_curves(path, ref, width, depth, period, strands=3):
    """Three interleaved strands along `path` (n,3). Classic braid: lateral offset
    sin(phi), depth offset sin(2 phi) with phase 2*pi*k/3. width/depth/period metres.
    Returns list of (n,3) curves."""
    s = arclen(path)
    T, N, B = frames(path, ref)
    out = []
    for k in range(strands):
        ph = 2 * math.pi * s / period + 2 * math.pi * k / strands
        lat = 0.5 * width * np.sin(ph)
        dep = 0.5 * depth * np.sin(2 * ph)
        out.append(path + B * lat[:, None] + N * dep[:, None])
    return out


class BunFrame:
    """Torus frame: centre, axis (unit), e1/e2 spanning the major circle."""

    def __init__(self, center, axis):
        self.c = np.asarray(center, np.float64); self.a = unit(axis)
        e1 = project_tangent(np.array([1.0, 0, 0]), self.a)
        if np.linalg.norm(e1) < 1e-6:
            e1 = project_tangent(np.array([0, 0, 1.0]), self.a)
        self.e1 = unit(e1); self.e2 = unit(np.cross(self.a, self.e1))

    def point(self, alpha, beta, R, r, z=0.0):
        alpha = np.asarray(alpha); beta = np.asarray(beta)
        radial = np.cos(alpha)[..., None] * self.e1 + np.sin(alpha)[..., None] * self.e2
        rr = (R + r * np.cos(beta))[..., None]
        return self.c + radial * rr + self.a * (r * np.sin(beta) + z)[..., None]

    def ring(self, alpha, R, z=0.0):
        radial = np.cos(alpha)[..., None] * self.e1 + np.sin(alpha)[..., None] * self.e2
        return self.c + radial * np.asarray(R)[..., None] + self.a * np.asarray(z)[..., None]


def ellipsoid_mesh(center, axes, rx, ry, rz, nu=12, nv=8):
    """Closed UV-sphere scaled by radii along the orthonormal axes (3 vectors)."""
    e1, e2, e3 = axes
    us = np.linspace(0, 2 * math.pi, nu + 1)
    vs = np.linspace(-math.pi / 2, math.pi / 2, nv + 1)
    P, Nn, UV = [], [], []
    for v in vs:
        for u in us:
            d = math.cos(v) * math.cos(u) * e1 + math.cos(v) * math.sin(u) * e2 + math.sin(v) * e3
            p = center + rx * math.cos(v) * math.cos(u) * e1 + ry * math.cos(v) * math.sin(u) * e2 + rz * math.sin(v) * e3
            nrm = unit(math.cos(v) * math.cos(u) * e1 / rx + math.cos(v) * math.sin(u) * e2 / ry + math.sin(v) * e3 / rz)
            P.append(p); Nn.append(nrm); UV.append([u / (2 * math.pi) * 3, (v + math.pi / 2) / math.pi])
    R = nu + 1
    tris = []
    for j in range(nv):
        for i in range(nu):
            a0 = j * R + i; a1 = a0 + 1; b0 = a0 + R; b1 = b0 + 1
            tris.append([a0, a1, b0]); tris.append([a1, b1, b0])
    return np.array(P), np.array(Nn), np.array(UV), np.array(tris, np.int64)


# =============================================================== shell
_FACE_BC = np.array([[1 / 3, 1 / 3, 1 / 3], [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3],
                     [0.5, 0.5, 0.0], [0.0, 0.5, 0.5], [0.5, 0.0, 0.5]])


def _shell_face_clearance(head, P, N, target, iters=6, max_lift=0.004):
    """Raise grid vertices (along N) until the shell's triangle FACES keep `target`
    (per row) off the skin. The vertex offsets alone let coarse grids dip their faces
    under the skin between vertices (LOD2: by up to 6 mm), so the scalp poked through.
    The hairline row stays put (a lifted edge opens a gap under it); the duplicated
    seam columns and the pole move together so the shell stays closed."""
    R1, C1 = P.shape[0] - 1, P.shape[1] - 1
    i, j = np.meshgrid(np.arange(R1), np.arange(C1), indexing='ij')
    i = i.ravel(); j = j.ravel()
    # the two triangles of every cell, as the sector triangulation makes them:
    # (i,j) (i,j+1) (i+1,j)  and  (i,j+1) (i+1,j+1) (i+1,j)
    tri = np.stack([np.stack([i, j, i, j + 1, i + 1, j], 1), np.stack([i, j + 1, i + 1, j + 1, i + 1, j], 1)], 1)
    tri = tri.reshape(-1, 3, 2)
    tgt = target[tri[:, :, 0]].min(1)
    lifted = np.zeros(P.shape[:2])
    for _ in range(iters):
        X = P[tri[:, :, 0], tri[:, :, 1]]                     # (F, 3, 3)
        S = np.einsum('kc,fcd->fkd', _FACE_BC, X).reshape(-1, 3)
        # against the skin without the ears (the shell is laid on that surface; the
        # ears poke through it and must not push it up around them)
        sd = head.signed(S, mesh=head.mesh_noear, T=head.T_noear)[0].reshape(len(tri), len(_FACE_BC))
        deficit = np.maximum(tgt[:, None] - sd, 0).max(1)
        if deficit.max() < 2e-4:
            break
        up = np.zeros(P.shape[:2])
        for c in range(3):
            movable = tri[:, c, 0] < R1                          # never the hairline row
            np.maximum.at(up, (tri[movable, c, 0], tri[movable, c, 1]), deficit[movable])
        up[0, :] = up[0].max()
        up[:, 0] = up[:, -1] = np.maximum(up[:, 0], up[:, -1])
        up = np.minimum(up * 1.1, max_lift - lifted)
        lifted += up
        P = P + N * up[:, :, None]
    return P


def shell_mesh(scalp, spec, rows, cols, rng=None):
    """Scalp-hugging under-shell bounded by the hairline.

    The grid lives in a pole-centred spherical frame: polar angle rho from the
    pole direction (whorl / bun) up to the hairline rho_max(beta), azimuth beta
    around the pole. Rays from the head centre C hit the skin (ears excluded);
    vertices are offset along the skin normal by offset_mm = [interior, edge]
    (+ the chord sagitta of the grid so triangle faces stay outside the skin).
    UV: u = beta / 2pi * u_repeat; v (spec['v']):
      'from_pole' (default): v = s * 0.86 / (1 - tip_band) inside, and the last
                  tip_band of s (the hairline edge) maps to v 0.86..0.995 -- the
                  clump texture's pointed-tip alpha -- giving a soft, irregular
                  hairline edge (also lighter there: root darkening is under the pole)
      'to_pole':  v = 1 - s (plain; no edge alpha)
    edge_inset (deg, or [[lon, deg], ...]): the shell edge sits that far OUTSIDE the
    hairline (negative: inside it). face_clear: keep the triangle faces at that
    fraction of offset_mm off the skin (raises the grid where coarse faces dip).
    Returns P, N, UV, T, t, s (s = 0 at the pole .. 1 at the hairline).
    """
    head = scalp.head
    pole = lonlat_dir(*spec.get('pole', [180, 60]))
    pole = unit(pole)
    e1 = unit(project_tangent(np.array([1.0, 0, 0]), pole))
    e2 = unit(np.cross(pole, e1))
    # hairline in the pole frame
    hl_lon = np.linspace(-180, 180, 721)[:-1]
    ei = spec.get('edge_inset', 1.5)
    if isinstance(ei, (list, tuple)):
        # per-longitude inset [[lon, deg], ...] (e.g. tucked under baby hairs at the
        # front, past the hairline at the nape)
        ea = np.array(ei, np.float64)
        ei = periodic_interp(hl_lon, ea[:, 0], ea[:, 1])
    hl_lat = scalp.hairline(hl_lon) - ei
    D = lonlat_dir(hl_lon, hl_lat)
    rho_h = np.degrees(np.arccos(np.clip(D @ pole, -1, 1)))
    beta_h = np.degrees(np.arctan2(D @ e2, D @ e1))
    o = np.argsort(beta_h)
    bins = np.linspace(-180, 180, 181)[:-1] + 1.0
    rmax = np.zeros(len(bins))
    for i, b in enumerate(bins):
        s = np.abs(((beta_h - b + 180) % 360) - 180) < 2.0
        rmax[i] = rho_h[s].min() if s.any() else np.nan
    ok = ~np.isnan(rmax)
    rmax = periodic_interp(bins, bins[ok], rmax[ok])
    rmax = circ_smooth(rmax, 3)
    # the grid is built in u_repeat texture sectors of cps columns each; cols must be
    # a whole number of sectors, or the columns past the last sector are never
    # triangulated (40 cols / 12 sectors left a 36 deg wedge of scalp bare)
    u_rep = max(1, int(round(spec.get('u_repeat', 6))))
    cps = max(1, int(round(cols / u_rep)))
    cols = cps * u_rep
    beta = np.linspace(-180, 180, cols + 1)            # seam duplicated
    rm = periodic_interp(beta, bins, rmax)
    vmode = spec.get('v', 'from_pole')
    tb = spec.get('tip_band', 0.05) if vmode == 'from_pole' else 0.0
    if tb > 0:
        s = np.concatenate([np.linspace(0, 1 - tb, rows), [1 - tb * 0.4, 1.0]])
        rows = len(s) - 1
    else:
        s = np.linspace(0, 1, rows + 1)
    rho = np.radians(s[:, None] * rm[None, :])
    br = np.radians(beta)[None, :]
    dirs = (np.cos(rho)[..., None] * pole + np.sin(rho)[..., None] *
            (np.cos(br)[..., None] * e1 + np.sin(br)[..., None] * e2))
    flat = dirs.reshape(-1, 3)
    Pk, Nk, ok = head.raycast(np.repeat(scalp.C[None], len(flat), 0), flat, 'noear')
    if not ok.all():
        cp, _, tri, bc = head.closest(scalp.C + flat[~ok] * head.R)
        Pk[~ok] = cp
        Nk[~ok] = unit((head.N[head.T[tri]] * bc[:, :, None]).sum(1))
    Pk = Pk.reshape(rows + 1, cols + 1, 3); Nk = Nk.reshape(rows + 1, cols + 1, 3)
    off_in, off_edge = [x * 1e-3 for x in spec.get('offset_mm', [3.5, 2.4])]
    # chord sagitta for this grid density (R ~ head radius)
    edge_len = max(np.radians(rm.max()) / rows, 2 * math.pi * math.sin(np.radians(min(90, rm.max()))) / cols) * head.R
    sag = edge_len ** 2 / (8 * head.R)
    off = off_in + (off_edge - off_in) * smoothstep((s - 0.75) / 0.25)
    P = Pk + Nk * (off + sag)[:, None, None]
    if spec.get('face_clear'):
        P = _shell_face_clearance(head, P, Nk, off * spec['face_clear'])
    # vertices in u_repeat sectors; each sector maps exactly one colour period of the
    # clump texture's opaque window, so sectors meet seamlessly (duplicated seam columns)
    V, UVl, sl, tris = [], [], [], []
    pole = P[0].mean(0)
    for k in range(u_rep):
        j0 = k * cps
        base = len(V)
        V.append(pole); UVl.append([CLUMP_EDGE + 0.5 * CLUMP_PERIOD, 0.0]); sl.append(0.0)
        for i in range(1, rows + 1):
            for jj in range(cps + 1):
                j = min(j0 + jj, cols)
                V.append(P[i, j]); UVl.append([CLUMP_EDGE + CLUMP_PERIOD * jj / cps, s[i]]); sl.append(s[i])
        R = cps + 1
        for jj in range(cps):
            tris.append([base, base + 1 + jj + 1, base + 1 + jj])
        for i in range(1, rows):
            b0r = base + 1 + (i - 1) * R; b1r = base + 1 + i * R
            for jj in range(cps):
                a0 = b0r + jj; a1 = a0 + 1; c0 = b1r + jj; c1 = c0 + 1
                tris.append([a0, a1, c0]); tris.append([a1, c1, c0])
    V = np.array(V); UVa = np.array(UVl); sl = np.array(sl)
    T = np.array(tris, np.int64)
    # orient outward
    fn = headref.tri_normals(V, T)
    cen = V[T].mean(1)
    if ((fn * (cen - scalp.C)).sum(1) < 0).mean() > 0.5:
        T = T[:, [0, 2, 1]]
    # welded normals across the sector seams
    _, key = np.unique(np.round(V / 1e-6).astype(np.int64), axis=0, return_inverse=True)
    Nv = headref.vertex_normals(V, T, key.ravel())
    if vmode == 'to_pole':
        UVa[:, 1] = 1 - UVa[:, 1]
    elif tb <= 0:
        # opaque edge (no frayed tip band): v stays below the texture's tip zone; the
        # edge is meant to sit under baby-hair cards (use a negative edge_inset)
        v0 = spec.get('v_start', 0.3)
        UVa[:, 1] = v0 + UVa[:, 1] * (0.78 - v0)
    elif tb > 0:
        sv = UVa[:, 1]
        v0 = spec.get('v_start', 0.3)       # skip most of the root-darkening ramp under the pole
        UVa[:, 1] = np.where(sv <= 1 - tb, v0 + sv * (0.84 - v0) / (1 - tb), 0.84 + (sv - (1 - tb)) / tb * 0.15)
    t = UVa[:, 1].copy()
    return V, Nv, UVa, T, t, sl


# =============================================================== sections per lod
def lod_section(sec, lod, lodspec):
    """Apply a group's LOD rule to section parameters.
    Rule keys: keep/min/drop (selection), segs (multiplier), width_mul, thick_mul,
    and any section key to override (sides, kind, split, segs_mul, ...)."""
    out = dict(sec)
    r = (lodspec or {}).get(str(lod)) or {}
    for k, v in r.items():
        if k not in ('keep', 'min', 'drop', 'segs', 'width_mul', 'thick_mul', 'no_split'):
            out[k] = v
    out['segs'] = max(2, int(round(sec.get('segs', 10) * r.get('segs', 1.0))))
    out['width'] = sec['width'] * r.get('width_mul', 1.0)
    out['thick'] = sec.get('thick', sec['width'] * 0.4) * r.get('thick_mul', r.get('width_mul', 1.0))
    if r.get('no_split'):
        out['split'] = 0
    return out


def lock_lod_keep(locks, lod, lodspec):
    """Spatially even subset of a group's locks for a LOD (farthest-point order of roots)."""
    r = (lodspec or {}).get(str(lod)) or {}
    keep = r.get('keep', 1.0)
    if keep >= 1.0 or not locks:
        return list(locks)
    k = max(int(r.get('min', 0)), int(round(keep * len(locks))))
    order = sorted(locks, key=lambda L: L.order)
    return order[:k]


def mesh_lock(lock, sec, part_clump, part_card, lod):
    """Mesh one lock into the clump/card parts with LOD-resolved section `sec`."""
    kind = sec.get('kind', lock.kind)
    segs = int(sec['segs'])
    w0 = sec['width']; th0 = sec['thick']
    prof = sec.get('profile', {})
    if kind == 'card' and lock.axis is not None:
        # a curl reduced to a single card along its axis (curl strand column)
        A = lock.axis
        n = max(4, int(sec.get('card_segs', 6)) + 1)
        C = resample(A, n)
        t = np.linspace(0, 1, n)
        w = width_profile(t, sec.get('card_width', max(w0 * 2.2, 0.012)), root=0.8, tip_start=0.75, tip_pow=0.6, tip_min=0.3)
        P, N, UV, T, tt = card_mesh(C, C - lock.center, w, sec.get('card_col', 6))
        part_card.add(P, N, UV, T, tt, lock.rand, lock.idx)
        return
    if kind == 'curl' or lock.axis is not None:
        # curl: dense helix points already in lock.pts; resample by its own density
        m = max(8, int(round(len(lock.pts) * sec.get('curl_density', 1.0) * sec.get('segs_mul', 1.0))))
        C = resample(lock.pts, m)
        t = np.linspace(0, 1, m)
        ref = C - resample(lock.axis, m) if lock.axis is not None else C - lock.center
        w = width_profile(t, w0, **{k: prof[k] for k in prof if k in ('root', 'belly', 'tip_start', 'tip_pow', 'tip_min')})
        th = width_profile(t, th0, **{k: prof[k] for k in prof if k in ('root', 'belly', 'tip_start', 'tip_pow', 'tip_min')})
        mk = sec.get('curl_mesh', 'ribbon')
        if mk == 'tube':
            P, N, UV, T, tt = tube_mesh(C, ref, w, th, sec.get('sides', 4), u_rep=sec.get('u_rep', 0.5), uoff=lock.uoff)
        else:
            P, N, UV, T, tt = ribbon_mesh(C, ref, w, cup=sec.get('cup', 0.3), across=sec.get('across', 3),
                                          full_u=sec.get('full_u', True))
        part_clump.add(P, N, UV, T, tt, lock.rand, lock.idx)
        return
    C = resample(lock.pts, segs + 1)
    t = np.linspace(0, 1, segs + 1)
    ref = C - lock.center
    tw = math.radians(sec.get('twist', 0.0)) * t * (1 if lock.rand > 0.5 else -1)
    pk = {k: prof[k] for k in prof if k in ('root', 'belly', 'tip_start', 'tip_pow', 'tip_min')}
    if kind == 'card':
        w = width_profile(t, w0, **({'root': 0.9, 'tip_start': 0.7, 'tip_pow': 0.6, 'tip_min': 0.25} | pk))
        P, N, UV, T, tt = card_mesh(C, ref, w, lock.col, twist=tw)
        part_card.add(P, N, UV, T, tt, lock.rand, lock.idx)
        return
    w = width_profile(t, w0, **pk)
    # thickness tapers harder at the root so clumps emerge flush from the shell
    tk = dict(pk, root=sec.get('troot', 0.2), belly=max(pk.get('belly', 0.25), 0.12))
    th = width_profile(t, th0, **tk)
    if kind == 'ribbon':
        droop = th * sec.get('droop', 0.0) / max(th0, 1e-9) * th0 if sec.get('droop') else None
        P, N, UV, T, tt = ribbon_mesh(C, ref, w, cup=sec.get('cup', 0.25), twist=tw, across=sec.get('across', 5),
                                      full_u=sec.get('full_u', True), u_rep=sec.get('u_rep', 0.6), uoff=lock.uoff,
                                      tilt=sec.get('tilt', 0.35), droop=droop)
        part_clump.add(P, N, UV, T, tt, lock.rand, lock.idx)
        return
    sides = int(sec.get('sides', 6))
    u_rep = sec.get('u_rep', max(0.5, round(math.pi * w0 / 0.045 * 2) / 2))
    split = int(sec.get('split', 0))
    if split >= 2 and segs >= 6:
        sa = float(sec.get('split_at', 0.7))
        # main body ends shortly after the split point
        i_end = int(round(sa * segs)) + 1
        tmain = t[:i_end + 1]
        Pm, Nm, UVm, Tm, ttm = tube_mesh(C[:i_end + 1], ref[:i_end + 1], w[:i_end + 1] * np.linspace(1, 0.55, i_end + 1) ** 0.3,
                                         th[:i_end + 1], sides, twist=tw[:i_end + 1], inner_flat=sec.get('inner_flat', 0.6),
                                         u_rep=u_rep, uoff=lock.uoff, tip_point=True, t_param=tmain)
        part_clump.add(Pm, Nm, UVm, Tm, ttm, lock.rand, lock.idx)
        Tn, Nf, Bf = frames(C, ref, tw)
        i0 = max(0, int(round(sa * segs)) - 1)
        sub_t = t[i0:]
        spread = sec.get('split_spread', 1.2)
        for j in range(split):
            off = (j - (split - 1) / 2) / split
            prog = smoothstep((sub_t - sub_t[0]) / max(1 - sub_t[0], 1e-3))
            lat = (off * w[i0] * (1 + spread * prog))[:, None] * Bf[i0:]
            Cs = C[i0:] + lat + Nf[i0:] * (0.15 * th[i0] * math.sin(j * 2.1))
            # sub tips of different lengths
            cut = 1.0 - 0.18 * ((j * 0.618 + lock.rand) % 1.0)
            ns = len(sub_t)
            Cs = resample(Cs[: max(2, int(round(ns * cut)))], ns)
            ws = w[i0] / split * 1.35 * (1 - prog * 0.0) * (1 - smoothstep((sub_t - sub_t[0]) / max(1 - sub_t[0], 1e-3)) ** 1.1)
            ths = th[i0] / split * 1.5 * (1 - prog) ** 0.9
            ws = np.maximum(ws, 1e-4); ths = np.maximum(ths, 1e-4)
            Ps, Ns, UVs, Ts, tts = tube_mesh(Cs, Cs - lock.center, ws, ths, max(3, sides - 2), inner_flat=0.7,
                                             u_rep=u_rep / split, uoff=lock.uoff + j * 0.31, tip_point=True,
                                             t_param=sub_t)
            part_clump.add(Ps, Ns, UVs, Ts, tts, lock.rand, lock.idx)
        return
    P, N, UV, T, tt = tube_mesh(C, ref, w, th, sides, twist=tw, inner_flat=sec.get('inner_flat', 0.6),
                                u_rep=u_rep, uoff=lock.uoff, tip_point=True)
    part_clump.add(P, N, UV, T, tt, lock.rand, lock.idx)
