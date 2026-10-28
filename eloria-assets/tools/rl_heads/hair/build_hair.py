"""Build an RL hair module GLB from a style definition.

    python build_hair.py <style.json> <sex> <out.glb> [--embed-textures] [--no-check]

Output contract (agreed with the runtime):
  * skeleton: `hair_root` (rest global = the body's Head rest global) + optional
    spring chains lock_<k>_<j> under it (j = 0 at the lock root)
  * meshes hair_lod0 / hair_lod1 / hair_lod2 (one skin), primitives per material
    rl_hair_clump (sculpted clumps, ribbons, the scalp under-shell, bun, braid)
    and rl_hair_card (alpha-tested strand cards)
  * UV v root(0) -> tip(1); COLOR_0 = (lock random, position along lock, ao,
    hair_detail keep-level: 1 core, 0.5..0.95 fine cards; hide when A < 1 - detail)
  * morph targets = every id_* shape of the head module (same names, mesh extras
    targetNames), transferred by surface binding (see assemble.py), plus the
    grooming shapes hl_length_p/_n and hl_volume_p/_n (README.md)
  * asset.extras.rlHair = {style, springs, collisions, tris, ...}
Prints a JSON report (tris/verts per LOD, bytes, clearance) and writes it next
to the GLB as <out>.report.json.

Authoring aids: --only g1,g2 builds just those groups (the bun is kept as an
anchor), --no-shell drops the under-shell; preview.py renders the result.

STYLE SCHEMA (styles/*.json; "_doc" keys are free comments)
  name, sex, seed            deterministic: same file + seed -> same asset
  color                      linear RGB tint written to the materials (preview / fallback)
  clearance_mm               rest push-out distance from the head skin (contract: >= 2 mm)
  ao_floor                   minimum COLOR_0.B on locks (deep gaps read as darker hair, not black)
  morph                      follow_mm / fade_mm (full follow near the skin, fade to the
                             lock-root delta), stretch (extra follow distance per metre of
                             skin-vs-root disagreement), keep_clear (normal + exact fix-up)
  points                     named points {"whorl": [lon, lat(, h_mm)], ...} usable as "@whorl"
  hairline                   ear_margin (deg above the ears), nape_below_lobe_mm (nape line),
                             nape_from/nape_blend (deg), noise (deg, soft irregular edge),
                             grow (deg, lowers everywhere), adjust [[lon, dlat], ...]
  shell                      pole [lon, lat], v from_pole|to_pole, tip_band (0 = opaque
                             edge), v_start, edge_inset (deg; negative keeps the shell
                             edge inside the hairline, e.g. under baby-hair cards),
                             offset_mm [interior, edge], u_repeat, ao, lod {"0": [rows, cols]}
  groups[]                   type: locks | bun | braid; per group "lod" rules:
                             {"1": {"keep": f, "sides": n, "segs": mul, "width_mul": m,
                             "kind": "card", "drop": true, "no_split": true, ...}, "2": {...}}
   locks: kind clump|ribbon|card|curl
     roots   {"region": {"lon": [a, b], "lat": [c, d], "mirror": bool}, "count", "margin",
              "exclude": [{"point", "deg"}]} | {"points": [[lon, lat], ...], "mirror", "jitter"}
              | {"on": "bun", "count"}
     length  [min, max] m, or length_table {"by": lat|lon|abslon, "points": [[x, L]], "jitter"}
     grow    hug (fraction following the scalp), height_mm (2 values or a list of control
             heights = volume profile), lift, gravity, stiffness, cross (deg), jitter (deg),
             steps, min_mm, height_ease, via [point specs] + via_radius_mm / via_jitter_mm
             (waypoints followed in order while hugging, e.g. a fringe draping across
             the forehead before turning up to the bun)
     flow    {"type": toward|away|dir|side|down|mix ...} (see hairgen.make_flow)
     end_near {"point", "radius_mm", "min_frac"}   stop locks near a point (e.g. the bun)
     shape   wave {amp_mm, cycles}, noise_mm, flick {angle, from, dir out|up|side},
             attract {point, from, strength}
     curl    radius_mm, pitch_mm, start, grow, flatten (curl locks: helix round the grown axis)
     section width, thick (m), sides, segs, twist (deg), inner_flat, troot (root thickness),
             profile {root, belly, tip_start, tip_pow, tip_min}, split, split_at,
             split_spread, cup / curl_mesh (ribbon|tube) for curls
     col     strand-atlas columns for cards; width_jitter; center (outward reference point);
             rand_range [r0, r1] for COLOR_0.R (e.g. outer layers high -> lighter streaks);
             detail core|fine|messy (COLOR_0.A tier: 1 | 0.5..0.95 | 0.05..0.45), detail_band
             [lo, hi] narrows a messy group's band (e.g. [0.05, 0.4] = visible from level 60),
             detail_values [a0, a1, ...] sets each lock's A exactly (in lock order; every
             vertex of the lock, clump or card, carries it);
             avoid_eyes (cut locks entering a box in front of the eyes;
             avoid_eyes_pad_mm [side, top] grows it, default [12, 16]; hl_length_p is
             cut at the same box); spring_follow
             (vertices borrow the nearest sprung lock's weights within 2.5 cm);
             ao_mul multiplies COLOR_0.B for the group (e.g. 0.6 for a darker underlayer)
     spring  {"count", "joints", "from" (fraction where the chain starts), "stiffness",
             "damping", "gravity", "drag", "radius"}  -> lock_<k>_<j> bones + extras
   bun:   center [lon, lat, h_mm], tilt, major_mm, minor_mm, clumps, sweep_deg, turns,
          messy, loose_ends, loops, loop_size, section, core {scale, res}
   braid: around "bun" (or path [points]), arc [deg0, deg1], radius_mm, z_mm, width_mm,
          depth_mm, period_mm, segs_per_period, section
"""
import os, sys, json, math, time, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rlglb  # noqa: E402  (adds scripts/ to sys.path)
import headref, hairgen, assemble  # noqa: E402
from headref import unit  # noqa: E402
from hairgen import Lock, MeshPart  # noqa: E402

import paths  # noqa: E402
TEX_DIR = paths.HAIR_TEX
LODS = (0, 1, 2)


# ===================================================================== context
class Ctx:
    def __init__(self, style, head, scalp):
        self.style = style; self.head = head; self.scalp = scalp
        self.points = {}
        self.bun = None          # (BunFrame, major, minor, base point)
        self.extras = []         # (group, lock, fn(lod) -> (P, N, UV, T, t) | None)

    def point(self, spec):
        if isinstance(spec, str) and spec.startswith('@'):
            return self.points[spec[1:]]
        return self.scalp.resolve_point(spec)

    def flow(self, spec):
        spec = resolve_refs(spec, self)
        return hairgen.make_flow(spec, self.scalp)


def resolve_refs(spec, ctx):
    """Replace "@name" point references inside a flow spec by {"xyz": ...}."""
    if isinstance(spec, dict):
        return {k: resolve_refs(v, ctx) for k, v in spec.items()}
    if isinstance(spec, list):
        return [resolve_refs(v, ctx) for v in spec]
    if isinstance(spec, str) and spec.startswith('@'):
        return {'xyz': ctx.points[spec[1:]].tolist()}
    return spec


def rand_range(rng, r, n):
    if isinstance(r, (int, float)):
        return np.full(n, float(r))
    return rng.uniform(r[0], r[1], n)


def table(x, pts):
    a = np.array(pts, np.float64)
    return np.interp(x, a[:, 0], a[:, 1])


# ===================================================================== roots
def roots_of(gspec, ctx, rng):
    """-> P0, N0, lon, lat for the group's roots."""
    rs = gspec['roots']
    sc = ctx.scalp
    if 'hairline' in rs:
        lon, lat = sc.hairline_roots(rs['hairline'], int(rs['count']), rng)
    elif 'points' in rs:
        pts = np.array(rs['points'], np.float64)
        lon, lat = pts[:, 0], pts[:, 1]
        if rs.get('jitter'):
            lon = lon + rng.normal(0, rs['jitter'], len(lon)); lat = lat + rng.normal(0, rs['jitter'], len(lat))
        if rs.get('mirror'):
            lon = np.concatenate([lon, -lon]); lat = np.concatenate([lat, lat])
    else:
        excl = []
        for ex in rs.get('exclude', []):
            q = ctx.point(ex['point'])
            excl.append((headref.unit(q - sc.C), ex.get('deg', 10.0)))
        lon, lat = sc.sample_roots(rs.get('region', {}), int(rs['count']), rng, margin=rs.get('margin', 2.0), exclude=excl)
    P0, N0 = sc.point(lon, lat, 0.0)
    return P0, N0, lon, lat


def truncate_near(C, Q, radius):
    """Cut a curve where it first enters `radius` of Q. Returns (curve, kept fraction)."""
    d = np.linalg.norm(C - Q, axis=1)
    hit = np.nonzero(d < radius)[0]
    if len(hit):
        if hit[0] < 2:
            return C, 0.0
        return hairgen.resample(C[:hit[0] + 1], len(C)), hit[0] / (len(C) - 1)
    return C, 1.0


def group_center(gspec, ctx):
    c = gspec.get('center')
    if c is None:
        return ctx.scalp.C
    return ctx.point(c)


# ===================================================================== builders
def eye_box_of(gspec, head):
    """avoid_eyes box (lo, hi) in front of the eyes, or None."""
    if not gspec.get('avoid_eyes'):
        return None
    E = head.eyes
    px, py = [v / 1000.0 for v in gspec.get('avoid_eyes_pad_mm', [12, 16])]
    return E.min(0) - [px, 0.012, 0.0], E.max(0) + [px, py, 0.06]


def clamp_to_box(lock, box):
    """Cut a (lengthened) lock where it enters the eye box, same point count, so the
    grooming length shapes keep the rest-pose eye rule."""
    if box is None:
        return lock
    P = lock.axis if lock.axis is not None else lock.pts
    inside = np.all((P > box[0]) & (P < box[1]), axis=1)
    inside[:2] = False
    if not inside.any():
        return lock
    j = max(2, int(np.argmax(inside)))
    t = np.linspace(0, j - 1, len(P)); i = np.arange(len(P))
    cut = lambda Q: np.stack([np.interp(t, i, Q[:, k]) for k in range(3)], 1)
    lock.pts = cut(lock.pts)
    if lock.axis is not None:
        lock.axis = cut(lock.axis)
    return lock


def build_locks(gspec, ctx, rng):
    """Clumps / ribbons / cards / curls grown from scalp (or bun) roots."""
    kind = gspec.get('kind', 'clump')
    rs = gspec['roots']
    if rs.get('on') == 'bun':
        P0, N0, Rpt = bun_roots(gspec, ctx, rng)
        lon = lat = np.zeros(len(P0))
    else:
        P0, N0, lon, lat = roots_of(gspec, ctx, rng)
        Rpt = P0.copy()
    n = len(P0)
    L = rand_range(rng, gspec.get('length', 0.1), n)
    if 'length_table' in gspec:
        lt = gspec['length_table']
        x = {'lat': lat, 'lon': lon, 'abslon': np.abs(lon)}[lt.get('by', 'lat')]
        L = table(x, lt['points']) * rng.uniform(1 - lt.get('jitter', 0.12), 1 + lt.get('jitter', 0.12), n)
    gp = dict(gspec.get('grow', {}))
    if 'via' in gp:
        gp['via'] = np.array([ctx.point(v) for v in gp['via']])
    flow = ctx.flow(gspec.get('flow', {'type': 'down'}))
    if kind == 'curl':
        gp.setdefault('steps', 30)
    curves = hairgen.grow(ctx.scalp, P0, N0, L, gp, rng, flow)
    center = group_center(gspec, ctx)
    if 'end_near' in gspec:
        en = gspec['end_near']
        Q = ctx.point(en['point'])
        cut = [truncate_near(C, Q, en.get('radius_mm', 15) * 1e-3) for C in curves]
        keep = [i for i, (C, f) in enumerate(cut) if f >= en.get('min_frac', 0.4)]
        curves = [cut[i][0] for i in keep]
        Rpt = Rpt[keep]; P0 = P0[keep]
        lon = np.asarray(lon)[keep] if np.ndim(lon) else lon
        lat = np.asarray(lat)[keep] if np.ndim(lat) else lat
    shp = dict(gspec.get('shape', {}))
    if 'attract' in shp:
        shp['attract'] = dict(shp['attract'], xyz=ctx.point(shp['attract']['point']))
    sec = dict(gspec.get('section', {}))
    sec.setdefault('width', 0.015); sec.setdefault('thick', sec['width'] * 0.4)
    wj = gspec.get('width_jitter', 0.15)
    cols = gspec.get('col', [4, 5])
    if isinstance(cols, int):
        cols = [cols]
    r0, r1 = gspec.get('rand_range', [0.0, 1.0])     # COLOR_0.R range (outer layers: lighter streaks)
    locks = []
    eye_box = eye_box_of(gspec, ctx.head)
    for i, C in enumerate(curves):
        C = hairgen.shape_curve(C, shp, rng, center)
        C = ctx.head.push_out(C, gspec.get('clear_mm', 3.0) * 1e-3 + sec['thick'] * 0.5, iters=2)
        if eye_box is not None:
            # never in front of the eyes: cut the lock where it enters the box, drop if short
            inside = np.all((C > eye_box[0]) & (C < eye_box[1]), axis=1)
            if inside.any():
                j = int(np.argmax(inside))
                if j < 0.4 * len(C):
                    continue
                C = hairgen.resample(C[:j], len(C))
        s = dict(sec)
        s['width'] = sec['width'] * rng.uniform(1 - wj, 1 + wj)
        s['thick'] = sec['thick'] * rng.uniform(1 - wj, 1 + wj)
        if kind == 'curl':
            cu = gspec.get('curl', {})
            rad = cu.get('radius_mm', 7.0) * rng.uniform(0.85, 1.15)
            pitch = cu.get('pitch_mm', 22.0) * rng.uniform(0.85, 1.2)
            Hc, s_ax, A = hairgen.helix(C, rad, pitch, rng, start=cu.get('start', 0.1), grow=cu.get('grow', 0.4),
                                        center=center, flatten=cu.get('flatten', 1.0))
            Hc = ctx.head.push_out(Hc, gspec.get('clear_mm', 3.0) * 1e-3 + s['thick'] * 0.5, iters=2)
            arcf = hairgen.arclen(Hc); arcf = arcf / max(arcf[-1], 1e-9)
            lk = Lock(Hc, 'curl', s, rng.uniform(r0, r1), Rpt[i], center, gspec['name'], axis=A, axis_t=(arcf, s_ax))
        else:
            lk = Lock(C, kind, s, rng.uniform(r0, r1), Rpt[i], center, gspec['name'], col=int(rng.choice(cols)))
        lk.chain_from = gspec.get('spring', {}).get('from', 0.0) if gspec.get('spring') else 0.0
        locks.append(lk)
    return locks


def bun_roots(gspec, ctx, rng):
    """Roots on the bun torus surface (for flyaways / loose loops)."""
    bf, R, r, base = ctx.bun
    n = int(gspec['roots']['count'])
    a = rng.uniform(0, 2 * math.pi, n)
    b = rng.uniform(-0.3 * math.pi, 0.9 * math.pi, n)      # mostly the upper/outer side
    P = bf.point(a, b, R, r * 0.95)
    ring = bf.ring(a, R)
    N = unit(P - ring)
    return P, N, np.repeat(base[None], n, 0)


def build_bun(gspec, ctx, rng):
    """Messy bun: clumps wound round a torus (major/minor radius) + an ellipsoid core."""
    head = ctx.head; sc = ctx.scalp
    lon, lat, h = gspec['center']
    base, nb = sc.point(lon, lat, 0.0)
    base = base[0]; nb = nb[0]
    axis = unit(nb + np.array(gspec.get('tilt', [0, 0, 0]), np.float64))
    center = base + axis * h * 1e-3
    R = gspec.get('major_mm', 25) * 1e-3; r = gspec.get('minor_mm', 16) * 1e-3
    bf = hairgen.BunFrame(center, axis)
    ctx.bun = (bf, R, r, base)
    ctx.points['bun'] = center
    ctx.points['bun_base'] = base
    n = int(gspec.get('clumps', 12))
    sec = dict(gspec.get('section', {}))
    sec.setdefault('width', 0.02); sec.setdefault('thick', 0.008)
    messy = gspec.get('messy', 0.2)
    locks = []
    sw0, sw1 = gspec.get('sweep_deg', [200, 320])
    tu0, tu1 = gspec.get('turns', [0.6, 1.2])
    for i in range(n):
        a0 = 2 * math.pi * i / n + rng.normal(0, 0.25)
        sweep = math.radians(rng.uniform(sw0, sw1)) * (1 if rng.random() < 0.8 else -1)
        turns = rng.uniform(tu0, tu1)
        b0 = rng.uniform(0, 2 * math.pi)
        m = 48
        s = np.linspace(0, 1, m)
        alpha = a0 + sweep * s
        beta = b0 + 2 * math.pi * turns * s
        rr = r * rng.uniform(0.75, 1.1) * (1 + messy * 0.6 * np.sin(math.pi * s) * rng.uniform(-1, 1))
        # loose ends: the last part of a wound lock lifts off the bun surface
        le = gspec.get('loose_ends', 0.0)
        if le:
            rr = rr * (1 + le * rng.uniform(0.5, 1.2) * hairgen.smoothstep((s - 0.72) / 0.28))
        z = rng.normal(0, r * 0.15) + np.linspace(0, rng.normal(0, r * 0.25), m)
        C = bf.point(alpha, beta, R * rng.uniform(0.9, 1.1), rr, z)
        # noise
        C = C + hairgen.smooth_polyline(rng.normal(0, messy * 2.5e-3, C.shape), 6)
        s_ = dict(sec)
        s_['width'] = sec['width'] * rng.uniform(0.7, 1.3)
        s_['thick'] = sec['thick'] * rng.uniform(0.8, 1.2)
        lk = Lock(C, sec.get('kind', 'clump'), s_, rng.random(), base, center, gspec['name'])
        locks.append(lk)
    # loose loops sticking out of the bun
    for i in range(int(gspec.get('loops', 0))):
        a0 = rng.uniform(0, 2 * math.pi)
        m = 32; s = np.linspace(0, 1, m)
        alpha = a0 + math.radians(rng.uniform(40, 90)) * s
        beta = rng.uniform(0, 2 * math.pi) + 2 * math.pi * 0.9 * s
        ls = gspec.get('loop_size', 0.7)
        ls = rng.uniform(ls[0], ls[1]) if isinstance(ls, list) else ls * rng.uniform(0.7, 1.2)
        rr = r * (1.0 + ls * np.sin(math.pi * s))
        C = bf.point(alpha, beta, R * rng.uniform(0.85, 1.1), rr, rng.normal(0, r * 0.2))
        s_ = dict(sec); s_['width'] = sec['width'] * gspec.get('loop_width', 0.55) * rng.uniform(0.8, 1.2)
        s_['thick'] = sec['thick'] * 0.6
        lk = Lock(C, sec.get('kind', 'clump'), s_, rng.random(), base, center, gspec['name'], lods=(0, 1))
        locks.append(lk)
    core = gspec.get('core', {})
    if core is not False:
        sx, sy, sz = core.get('scale', [1.0, 1.0, 0.85])
        res = core.get('res', {'0': [14, 8], '1': [10, 6], '2': [8, 5]})
        core_lock = Lock(np.array([base, center]), 'core', {}, 0.5, base, center, gspec['name'])
        rx = (R + r * 0.55) * sx; ry = (R + r * 0.55) * sy; rz = r * 1.05 * sz

        def core_fn(lod, bf=bf, rx=rx, ry=ry, rz=rz, res=res):
            nu, nv = res[str(lod)]
            P, N, UV, T = hairgen.ellipsoid_mesh(bf.c - bf.a * r * 0.15, (bf.e1, bf.e2, bf.a), rx, ry, rz, nu, nv)
            t = np.clip(UV[:, 1], 0, 1)
            return P, N, UV, T, t
        ctx.extras.append((gspec, core_lock, core_fn))
    return locks


def build_braid(gspec, ctx, rng):
    """Three-strand braid on a path round the bun base (or explicit polyline)."""
    if gspec.get('around', 'bun') == 'bun':
        bf, R, r, base = ctx.bun
        a0, a1 = [math.radians(x) for x in gspec.get('arc', [0, 330])]
        m = 120
        alpha = np.linspace(a0, a1, m)
        rad = gspec.get('radius_mm', (R + r) * 1e3) * 1e-3
        z = gspec.get('z_mm', -r * 1e3 * 0.6) * 1e-3
        path = bf.ring(alpha, rad, z)
        ref = path - bf.ring(alpha, 0.0, z)          # radial from the bun axis
        center = bf.c; root = base
    else:
        path = np.array([ctx.point(p) for p in gspec['path']])
        path = hairgen.resample(path, 120)
        ref = path - ctx.scalp.C; center = ctx.scalp.C; root = path[0]
    strands = hairgen.braid_curves(path, ref, gspec.get('width_mm', 14) * 1e-3, gspec.get('depth_mm', 7) * 1e-3,
                                   gspec.get('period_mm', 30) * 1e-3)
    sec = dict(gspec.get('section', {}))
    sec.setdefault('width', 0.007); sec.setdefault('thick', 0.005)
    locks = []
    L = hairgen.arclen(path)[-1]
    per = gspec.get('period_mm', 30) * 1e-3
    segs = int(round(L / per * gspec.get('segs_per_period', 8)))
    for k, C in enumerate(strands):
        C = ctx.head.push_out(C, 0.003 + sec['thick'] / 2, iters=2)
        s = dict(sec); s['segs'] = segs
        s.setdefault('profile', {'root': 0.6, 'belly': 0.05, 'tip_start': 0.92, 'tip_pow': 0.8, 'tip_min': 0.3})
        locks.append(Lock(C, 'clump', s, rng.random(), root, center, gspec['name']))
    return locks


BUILDERS = {'locks': build_locks, 'bun': build_bun, 'braid': build_braid}


# ===================================================================== skeleton
def chain_for(lock, nj, cfrom, head):
    """Joint positions / rotations along the lock axis from `cfrom` to the tip."""
    A = lock.axis if lock.axis is not None else lock.pts
    s = hairgen.arclen(A); s = s / max(s[-1], 1e-9)
    fr = cfrom + (1 - cfrom) * np.arange(nj + 1) / nj           # nj joints + tail
    pts = np.stack([np.interp(fr, s, A[:, k]) for k in range(3)], 1)
    G = []
    for j in range(nj):
        y = unit(pts[j + 1] - pts[j])
        out = unit(pts[j] - lock.center)
        x = unit(np.cross(y, out))
        if np.linalg.norm(x) < 1e-6:
            x = unit(np.cross(y, np.array([0, 0, 1.0])))
        z = np.cross(x, y)
        M = np.eye(4); M[:3, 0] = x; M[:3, 1] = y; M[:3, 2] = z; M[:3, 3] = pts[j]
        G.append(M)
    return fr, pts, G


def chain_weights(tv, fr):
    """Linear blend between consecutive joints by position along the lock.
    tv: per-vertex axis fraction; fr: joint fractions (nj + 1 incl. tail).
    Returns (n, nj + 1) weights: column 0 = hair_root, then the joints."""
    nj = len(fr) - 1
    mids = 0.5 * (fr[:-1] + fr[1:])
    W = np.zeros((len(tv), nj + 1))
    before = tv <= fr[0]
    # root region: 100% hair_root before the chain starts, fading into joint 0
    for i, t in enumerate(tv):
        if t <= fr[0]:
            W[i, 0] = 1.0
        elif t <= mids[0]:
            W[i, 1] = 1.0
        elif t >= mids[-1]:
            W[i, nj] = 1.0
        else:
            j = int(np.searchsorted(mids, t)) - 1
            f = (t - mids[j]) / max(mids[j + 1] - mids[j], 1e-9)
            W[i, 1 + j] = 1 - f; W[i, 2 + j] = f
    return W


# ===================================================================== grooming (safety)
def secure_groom(head, Pm, hair_d, id_names, marg, iters=3):
    """Grooming positions also stay outside the skin when the identity extremes are on:
    for all-_p and all-_n (head + the hair's own transferred id deltas) any vertex closer
    than `marg` is pushed out along the morphed normal (the push is part of the groom
    shape, so it applies whatever identity is set)."""
    Pm = np.array(Pm, np.float64)
    for suffix in ('_p', '_n'):
        mix = [n for n in id_names if n.endswith(suffix)]
        Dh = sum(head.delta(n) for n in mix)
        Dv = sum(hair_d[n] for n in mix)
        mesh = assemble.trimesh.Trimesh(head.P + Dh, head.T, process=False)
        for _ in range(iters):
            sd, cp, n, rim = head.signed(Pm + Dv, D=Dh, mesh=mesh, with_rim=True)
            bad = (sd < marg) & ~rim
            if not bad.any():
                break
            Pm[bad] += n[bad] * (marg + 0.0005 - sd[bad])[:, None]
    return Pm


# ===================================================================== grooming (volume)
def volume_field(d, locks, head, groom_of, h0=0.0045, ramp=0.45, short=0.6):
    """Per-vertex direction and amount for the volume shapes: each ring moves along the
    skin normal under its lock's centreline by its stand-off above h0 (the hugging
    base), ramped in from the root (0 at the root, full from `ramp` of the length).
    The stand-off used is the smaller of the ring's own and that of the point it
    occupies when the lock is shortened (t x `short`), so hl_volume_n stays above the
    skin when combined with hl_length_n."""
    n = len(d['P'])
    vdir = np.zeros((n, 3)); vamt = np.zeros(n)
    C = np.zeros((n, 3)); C2 = np.zeros((n, 3)); use = np.zeros(n, bool); f = np.zeros(n)
    for li in np.unique(d['lock']):
        if li < 0 or not groom_of.get(int(li), (False, False))[1]:
            continue
        sel = np.nonzero(d['lock'] == li)[0]
        lk = locks[li]
        A = lk.axis if lk.axis is not None else lk.pts
        tv = np.clip(d['t'][sel], 0, 1)
        if lk.axis_t is not None:
            tv = np.interp(tv, lk.axis_t[0], lk.axis_t[1])
        s = hairgen.arclen(A); s = s / max(s[-1], 1e-9)
        C[sel] = np.stack([np.interp(tv, s, A[:, k]) for k in range(3)], 1)
        C2[sel] = np.stack([np.interp(tv * short, s, A[:, k]) for k in range(3)], 1)
        f[sel] = hairgen.smoothstep(tv / ramp)
        use[sel] = True
    if use.any():
        idx = np.nonzero(use)[0]
        sd, cp, nrm = head.signed(C[idx])
        sd2, _, _ = head.signed(C2[idx])
        vdir[idx] = nrm
        vamt[idx] = np.maximum(np.minimum(sd, sd2) - h0, 0.0) * f[idx]
    return vdir, vamt


# ===================================================================== colliders
def colliders(head, joints_pts, hair_root_G, radius_default=0.012):
    """Skull/occiput spheres, jaw sphere and neck capsule, inscribed in the head
    skin and shrunk so no spring joint (plus its radius) starts inside."""
    inv = np.linalg.inv(hair_root_G)
    out = []
    P = head.P

    def inscribed(c):
        _, d, _, _ = head.closest(c[None])
        return float(d[0])

    def keep_out(c, r, rad):
        if len(joints_pts):
            dj = np.linalg.norm(joints_pts - c, axis=1) - rad
            r = min(r, float(dj.min()) - 0.002)
        return max(r, 0.01)

    skull_c = head.C.copy()
    occ_c = head.C + np.array([0, -0.01, -0.025])
    eye = head.eye_mid
    jaw_c = np.array([0.0, eye[1] - 0.065, eye[2] - 0.035])
    for name, c in (('skull', skull_c), ('occiput', occ_c), ('jaw', jaw_c)):
        r = inscribed(c) * 0.97
        r = keep_out(c, r, radius_default)
        loc = (inv @ np.r_[c, 1])[:3]
        out.append({'name': name, 'shape': 'sphere', 'offset': [round(float(x), 5) for x in loc], 'radius': round(r, 5)})
    # neck capsule along neck_01 -> Head below the jaw
    nb = head.G[head.node_index['neck_01']][:3, 3]; hj = head.head_joint
    ax = unit(hj - nb)
    lo = nb + ax * 0.02; hi = hj - ax * 0.005
    band = (P[:, 1] < hj[1] - 0.01) & (P[:, 2] < eye[2] - 0.045)
    seg = P[band]
    tt = np.clip((seg - lo) @ ax, 0, np.linalg.norm(hi - lo))
    rr = np.linalg.norm(seg - (lo + np.outer(tt, ax)), axis=1)
    r = float(np.percentile(rr, 5)) * 0.95 if len(rr) else 0.05
    mid = 0.5 * (lo + hi)
    hgt = float(np.linalg.norm(hi - lo)) + 2 * r
    if len(joints_pts):
        # distance of joints to the capsule segment
        tj = np.clip((joints_pts - lo) @ ax, 0, np.linalg.norm(hi - lo))
        dj = np.linalg.norm(joints_pts - (lo + np.outer(tj, ax)), axis=1) - radius_default
        r = max(0.01, min(r, float(dj.min()) - 0.002))
    loc = (inv @ np.r_[mid, 1])[:3]
    axl = inv[:3, :3] @ ax
    out.append({'name': 'neck', 'shape': 'capsule', 'offset': [round(float(x), 5) for x in loc], 'radius': round(r, 5),
                'height': round(hgt, 5), 'axis': [round(float(x), 5) for x in axl]})
    return out


# ===================================================================== build
def build(style_path, sex, out_path, embed=False, check=True, quiet=False, only=None, no_shell=False):
    t0 = time.time()
    style = json.load(open(style_path))
    if only:
        # authoring aid: keep the named groups (plus groups they depend on, e.g. the bun)
        style['groups'] = [g for g in style['groups'] if g['name'] in only or g.get('type') == 'bun']
        for g in style['groups']:
            if g.get('type') == 'bun' and g['name'] not in only:
                g['clumps'] = 0; g['loops'] = 0; g['core'] = False
    if no_shell:
        style.pop('shell', None)
    head = headref.Head(sex)
    scalp = hairgen.Scalp(head, style.get('hairline'))
    ctx = Ctx(style, head, scalp)
    seed = style.get('seed', 1)
    for nm, spec in style.get('points', {}).items():
        ctx.points[nm] = scalp.resolve_point(spec)
    groups = []
    locks = []
    for gspec in style['groups']:
        if gspec.get('disabled'):
            continue
        rng = hairgen.rng_for(seed, gspec['name'])
        new = BUILDERS[gspec.get('type', 'locks')](gspec, ctx, rng)
        # spatially even LOD order
        if new:
            mids = np.array([lk.pts[len(lk.pts) // 3] for lk in new])
            order = hairgen.farthest_order(mids)
            for rank, i in enumerate(order):
                new[i].order = rank
        for lk in new:
            lk.idx = len(locks); locks.append(lk)
        groups.append((gspec, new))
    for gspec, lk, fn in ctx.extras:
        lk.idx = len(locks); locks.append(lk)

    # ------------------------------------------------ springs (shared skeleton)
    HG = head.head_G.copy()
    bones = [('hair_root', HG, None)]
    springs = []
    chain_of = {}
    for gspec, glocks in groups:
        sp = gspec.get('spring')
        if not sp:
            continue
        cand = sorted(glocks, key=lambda L: L.order)[: int(sp.get('count', len(glocks)))]
        for lk in cand:
            k = len(springs)
            nj = int(sp.get('joints', 4))
            fr, pts, G = chain_for(lk, nj, sp.get('from', 0.0), head)
            names = []
            first = len(bones)
            for j in range(nj):
                nm = f'lock_{k}_{j}'
                names.append(nm)
                bones.append((nm, G[j], 'hair_root' if j == 0 else f'lock_{k}_{j - 1}'))
            chain_of[lk.idx] = (first, fr)
            springs.append({'bones': names, 'stiffness': sp.get('stiffness', 0.6), 'damping': sp.get('damping', 0.3),
                            'gravity': sp.get('gravity', 0.6), 'drag': sp.get('drag', 0.4), 'radius': sp.get('radius', 0.008),
                            'group': gspec['name'],
                            'tail': [round(float(x), 5) for x in (np.linalg.inv(HG) @ np.r_[pts[-1], 1])[:3]]})
    nb = len(bones)
    joint_pts = np.array([b[1][:3, 3] for b in bones[1:]]) if nb > 1 else np.zeros((0, 3))

    # ------------------------------------------------ meshes per LOD
    clear = style.get('clearance_mm', 2.6) * 1e-3
    lodspec_of = {g['name']: g.get('lod', {}) for g, _ in groups}
    lod_data = {}
    group_tris = {}
    groom = style.get('groom', {})
    g_len = groom.get('length', [-0.4, 0.6])          # hl_length_n / _p as fractions of lock length
    g_vol = groom.get('volume', [-0.5, 0.8])          # hl_volume_n / _p as fractions of stand-off
    groom_of = {}
    for gspec, glocks in groups:
        gg = gspec.get('groom', {})
        is_locks = gspec.get('type', 'locks') == 'locks'
        for lk in glocks:
            groom_of[lk.idx] = (gg.get('length', is_locks), gg.get('volume', is_locks))
    for lod in LODS:
        clump, card = MeshPart(), MeshPart()
        # parallel parts for the length shapes (same topology, rescaled growth curves)
        lp_c, lp_k, ln_c, ln_k = MeshPart(), MeshPart(), MeshPart(), MeshPart()
        sh = style.get('shell')
        if sh:
            rows, cols = sh['lod'][str(lod)]
            P, N, UV, T, t, s = hairgen.shell_mesh(scalp, sh, rows, cols)
            for part in (clump, lp_c, ln_c):
                part.add(P, N, UV, T, t, 0.5, -1)
            group_tris.setdefault('shell', {})[f'lod{lod}'] = len(T)
        for gspec, glocks in groups:
            ls = lodspec_of[gspec['name']]
            rule = ls.get(str(lod), {})
            if rule.get('drop'):
                continue
            keep = hairgen.lock_lod_keep([lk for lk in glocks if lod in lk.lods], lod, ls)
            ebox = eye_box_of(gspec, head)
            t_before = clump.tris + card.tris
            for lk in keep:
                sec = hairgen.lod_section(lk.sec, lod, ls)
                hairgen.mesh_lock(lk, sec, clump, card, lod)
                if groom_of.get(lk.idx, (False, False))[0]:
                    hairgen.mesh_lock(clamp_to_box(hairgen.rescaled_lock(lk, g_len[1]), ebox), sec, lp_c, lp_k, lod)
                    hairgen.mesh_lock(hairgen.rescaled_lock(lk, g_len[0]), sec, ln_c, ln_k, lod)
                else:
                    hairgen.mesh_lock(lk, sec, lp_c, lp_k, lod)
                    hairgen.mesh_lock(lk, sec, ln_c, ln_k, lod)
            group_tris.setdefault(gspec['name'], {})[f'lod{lod}'] = clump.tris + card.tris - t_before
        for gspec, lk, fn in ctx.extras:
            if (gspec.get('lod', {}).get(str(lod), {}) or {}).get('drop_core'):
                continue
            res = fn(lod)
            if res is not None:
                P, N, UV, T, t = res
                for part in (clump, lp_c, ln_c):
                    part.add(P, N, UV, T, t, lk.rand, lk.idx)
                group_tris.setdefault(gspec['name'] + '_core', {})[f'lod{lod}'] = len(T)
        lod_data[lod] = {'clump': clump.arrays(), 'card': card.arrays()}
        for nm, (pc, pk) in (('lp', (lp_c, lp_k)), ('ln', (ln_c, ln_k))):
            for mname, part in (('clump', pc), ('card', pk)):
                arr = part.arrays()
                base = lod_data[lod][mname]
                if base is not None:
                    assert arr is not None and len(arr['P']) == len(base['P']), 'grooming topology mismatch'
                    base['P_' + nm] = arr['P']

    # ------------------------------------------------ per-LOD vertex processing
    id_names = head.id_names()
    mcfg = style.get('morph', {})
    follow = mcfg.get('follow_mm', 15) * 1e-3; fade = mcfg.get('fade_mm', 15) * 1e-3
    report = {'style': style.get('name'), 'sex': sex, 'lods': {}, 'springs': len(springs), 'bones': nb}
    W = assemble.Writer('RL hair build (scripts/hair/build_hair.py)')
    hcol = style.get('color', [0.35, 0.2, 0.1])
    mats = {
        'clump': W.material('rl_hair_clump', hcol + [1.0], alpha='MASK', cutoff=0.5, double=True,
                            extras={'texture': 'hair_clump.png', 'uv': 'u wraps (repeat), v root->tip', 'tint': hcol}),
        'card': W.material('rl_hair_card', hcol + [1.0], alpha='MASK', cutoff=0.35, double=True,
                           extras={'texture': 'hair_strands.png', 'atlasColumns': 8, 'tint': hcol}),
    }
    if embed:
        W.embed_texture(mats['clump'], os.path.join(TEX_DIR, 'hair_clump.png'))
        W.embed_texture(mats['card'], os.path.join(TEX_DIR, 'hair_strands.png'))
    lock_root = np.array([lk.root for lk in locks]) if locks else np.zeros((0, 3))
    ao_mul_of = {lk.idx: g.get('ao_mul', 1.0) for g, gl in groups for lk in gl if g.get('ao_mul', 1.0) != 1.0}
    detail_of = {lk.idx: g.get('detail', 'fine' if g.get('kind') == 'card' else 'core') for g, gl in groups for lk in gl}
    band_of = {lk.idx: g.get('detail_band') for g, gl in groups for lk in gl if g.get('detail_band')}
    # explicit per-lock COLOR_0.A (in lock order), e.g. staggered messy locks
    value_of = {lk.idx: float(g['detail_values'][i % len(g['detail_values'])])
                for g, gl in groups if g.get('detail_values') for i, lk in enumerate(gl)}
    spring_follow = {lk.idx for g, gl in groups for lk in gl if g.get('spring_follow')}
    groom_names = ['hl_length_p', 'hl_length_n', 'hl_volume_p', 'hl_volume_n']
    clearance_rep = {}
    mesh_ids = []
    for lod in LODS:
        prims = []
        tris_lod = {}
        allP = []
        for mname in ('clump', 'card'):
            d = lod_data[lod][mname]
            if d is None:
                continue
            P = d['P']
            # collision push-out of every vertex (rest), with morph headroom where
            # several identity shapes can push the skin outward under the hair
            extra = assemble.headroom(head, P, id_names, frac=mcfg.get('headroom', 0.5))
            P = assemble.push_out_var(head, P, clear + 0.0004 + extra, iters=6)
            d['P'] = P
            roots = np.where(d['lock'][:, None] >= 0, lock_root[np.maximum(d['lock'], 0)], P) if len(lock_root) else P.copy()
            bind = assemble.Binding(head, P, roots, follow, fade, T=d['T'], stretch=mcfg.get('stretch', 0.5))
            dist = bind.dist
            ao = np.clip((dist - 0.002) / 0.03, 0, 1) ** 0.6
            # the under-shell is the deepest layer but should read as hair, not a black gap
            ao = np.where(d['lock'] < 0, (style.get('shell') or {}).get('ao', 0.5), np.maximum(ao, style.get('ao_floor', 0.2)))
            # per-group ao multiplier (e.g. a darker underlayer)
            for li, mul in ao_mul_of.items():
                ao[d['lock'] == li] *= mul
            # hair_detail keep-level (COLOR_0.A): 1 = core; authored fine cards 0.5..0.95
            # (visible at the default level 50); "messy" extras 0.05..0.45 (fade in 55..95)
            detail = np.ones(len(P))
            for li in np.unique(d['lock']):
                if li < 0:
                    continue
                tier = detail_of.get(int(li), 'core')
                fr_ = (locks[li].rand * 7.77 + 0.13) % 1.0
                if int(li) in value_of:
                    detail[d['lock'] == li] = value_of[int(li)]
                elif tier == 'fine':
                    detail[d['lock'] == li] = 0.5 + 0.45 * fr_
                elif tier == 'messy':
                    lo_, hi_ = band_of.get(int(li), (0.05, 0.45))
                    detail[d['lock'] == li] = lo_ + (hi_ - lo_) * fr_
            col = assemble.colors_u8(d['rand'], np.clip(d['t'], 0, 1), ao, detail)
            # skin weights
            Wd = np.zeros((len(P), nb)); Wd[:, 0] = 1.0
            for li in np.unique(d['lock']):
                if li in chain_of:
                    first, fr = chain_of[li]
                    sel = d['lock'] == li
                    lk = locks[li]
                    tv = d['t'][sel]
                    if lk.axis_t is not None:
                        tv = np.interp(tv, lk.axis_t[0], lk.axis_t[1])
                    cw = chain_weights(tv, fr)
                    Wd[sel] = 0
                    Wd[np.ix_(sel, [0] + list(range(first, first + len(fr) - 1)))] = cw
            # strays that hang near sprung locks borrow the nearest sprung vertex's weights
            # (faded to hair_root by distance) so they swing with them
            sf = np.isin(d['lock'], list(spring_follow)) if spring_follow else np.zeros(len(P), bool)
            sprung = Wd[:, 0] < 0.999
            if sf.any() and sprung.any():
                from scipy.spatial import cKDTree
                tr = cKDTree(P[sprung])
                dd, ii = tr.query(P[sf])
                src = np.nonzero(sprung)[0][ii]
                k = np.clip(1.0 - dd / 0.025, 0, 1)[:, None]
                root = np.zeros((1, nb)); root[0, 0] = 1.0
                Wd[sf] = k * Wd[src] + (1 - k) * root
            J4, W4 = assemble.top4(Wd)
            # morphs
            targets = []
            weld = None
            hair_d = {}
            for nm in id_names:
                D = head.delta(nm)
                dP = bind.delta(D, keep_clear=mcfg.get('keep_clear', True), margin=clear + 0.0004)
                dP[np.abs(dP).max(1) < 2e-6] = 0
                dN = None
                targets.append((dP, dN))
                hair_d[nm] = dP
            # grooming shapes (hair only; the head does not move): length from the rescaled
            # growth curves, volume = stand-off scaling along the skin normal
            marg = clear + 0.0004
            hr = mcfg.get('headroom', 0.5)
            Pg = {}
            for nm, key in (('hl_length_p', 'P_lp'), ('hl_length_n', 'P_ln')):
                if key in d:
                    # identity-shape headroom measured where the tips now are (a bit more
                    # than at rest: the id deltas were transferred at the rest positions)
                    Pm = assemble.push_out_var(head, d[key], marg + assemble.headroom(head, d[key], id_names, frac=hr * 1.6, cap=0.008), iters=5)
                else:
                    Pm = P
                Pm = secure_groom(head, Pm, hair_d, id_names, marg)
                Pg[nm] = Pm
                dP = Pm - P; dP[np.abs(dP).max(1) < 2e-6] = 0
                targets.append((dP, None)); hair_d[nm] = dP
            vdir, vamt = volume_field(d, locks, head, groom_of)
            # flattening is capped per vertex by its own clearance at rest, shortened and
            # lengthened, so hl_volume_n stays outside the skin alone and combined with hl_length_*
            sd_rest = bind.sd
            sd_short, _, _ = head.signed(Pg['hl_length_n'])
            sd_long, _, _ = head.signed(Pg['hl_length_p'])
            cap_in = np.maximum(np.minimum(np.minimum(sd_rest, sd_short), sd_long) - marg - 0.0008, 0.0) / max(abs(g_vol[0]), 1e-6)
            for nm, kk in (('hl_volume_p', g_vol[1]), ('hl_volume_n', g_vol[0])):
                amt = vamt if kk > 0 else np.minimum(vamt, cap_in)
                Pv = P + vdir * (kk * amt)[:, None]
                Pm = assemble.push_out_var(head, Pv, marg + assemble.headroom(head, Pv, id_names, frac=hr), iters=5)
                Pm = secure_groom(head, Pm, hair_d, id_names, marg)
                dP = Pm - P; dP[np.abs(dP).max(1) < 2e-6] = 0
                targets.append((dP, None)); hair_d[nm] = dP
            prims.append(W.primitive(P.astype(np.float32), d['N'].astype(np.float32), d['UV'].astype(np.float32),
                                     d['T'], col, J4, W4, mats[mname], targets))
            tris_lod[mname] = int(len(d['T']))
            d['hair_d'] = hair_d
            allP.append((P, hair_d))
        mid = W.mesh(f'hair_lod{lod}', prims, id_names + groom_names)
        mesh_ids.append(mid)
        nv = sum(len(lod_data[lod][m]['P']) for m in ('clump', 'card') if lod_data[lod][m] is not None)
        report['lods'][f'lod{lod}'] = {'tris': sum(tris_lod.values()), 'byMaterial': tris_lod, 'verts': nv}
        if check:
            Pc = np.concatenate([p for p, _ in allP])
            names_all = id_names + groom_names
            dh = {nm: np.concatenate([hd[nm] for _, hd in allP]) for nm in names_all}
            dhead = dict(head.deltas); dhead.update({nm: np.zeros_like(head.P) for nm in groom_names})
            combos = assemble.default_combos(id_names)
            ids = [n for n in id_names]
            for gname in groom_names:
                combos[gname + '+all_id_p'] = dict({n: 1.0 for n in ids if n.endswith('_p')}, **{gname: 1.0})
                combos[gname + '+all_id_n'] = dict({n: 1.0 for n in ids if n.endswith('_n')}, **{gname: 1.0})
            combos['hl_length_p+hl_volume_n'] = {'hl_length_p': 1.0, 'hl_volume_n': 1.0}
            combos['hl_length_n+hl_volume_n'] = {'hl_length_n': 1.0, 'hl_volume_n': 1.0}
            clearance_rep[f'lod{lod}'] = assemble.clearance(head, Pc, dhead, dh, names_all, margin=0.002, combos=combos)

    # ------------------------------------------------ nodes / skin
    g = W.g
    node_of = {}
    for name, G, parent in bones:
        if parent is None:
            nd = g.node(name=name, **rlglb.trs_from_matrix(G))
            g.g['scenes'][0]['nodes'].append(nd)
        else:
            PG = dict((b[0], b[1]) for b in bones)[parent]
            local = np.linalg.inv(PG) @ G
            nd = g.node(name=name, **rlglb.trs_from_matrix(local))
            g.g['nodes'][node_of[parent]].setdefault('children', []).append(nd)
        node_of[name] = nd
    ibm = np.stack([rlglb.mat4_to_gltf(np.linalg.inv(G)) for _, G, _ in bones])
    ibm_acc = g.accessor(ibm, 'MAT4')
    g.g['skins'].append({'joints': [node_of[b[0]] for b in bones], 'inverseBindMatrices': ibm_acc,
                         'skeleton': node_of['hair_root'], 'name': 'RLHairSkin'})
    for lod, mid in zip(LODS, mesh_ids):
        nd = g.node(name=f'hair_lod{lod}', mesh=mid, skin=0)
        g.g['scenes'][0]['nodes'].append(nd)

    cols = colliders(head, joint_pts, HG, radius_default=max([s['radius'] for s in springs], default=0.008))
    tris = {k: v['tris'] for k, v in report['lods'].items()}
    g.g['asset']['extras'] = {'rlHair': {
        'version': 1, 'style': style.get('name', os.path.splitext(os.path.basename(style_path))[0]), 'sex': sex,
        'springs': springs, 'collisions': cols, 'tris': tris,
        'space': 'vertices in body model space; collider offsets/axes in hair_root space',
        'colour': {'R': 'per-lock random', 'G': 'position along lock (0 root .. 1 tip)', 'B': 'ao (0 at scalp .. 1 outer)',
                   'A': 'hair_detail keep-level: 1 = core geometry; authored fine detail cards 0.5..0.95; messy extras 0.05..0.45. Shader: discard when A < 1 - hair_detail (0..1): a card appears once level > 100 (1 - A); default 50 shows exactly the authored look, 55..95 fades the messy extras in'},
        'grooming': {'shapes': groom_names, 'lengthRange': g_len, 'volumeRange': g_vol,
                     'note': 'weight 1 = full effect (length -40%/+60% of each lock along its own growth curve, roots pinned; volume -50%/+80% of the stand-off above the hugging base, ramped in from the root). Spring chains keep their authored rest lengths: extended tips stay weighted to the last joint.'},
        'morphTransfer': {'source': os.path.basename(head.glb_path), 'followMM': follow * 1e3, 'fadeMM': fade * 1e3,
                          'keepClear': mcfg.get('keep_clear', True)},
        'materials': {'rl_hair_clump': 'hair_clump.png (u repeat)', 'rl_hair_card': 'hair_strands.png (8 columns)'},
        'headSHA256': assemble.file_sha(head.glb_path)}}
    size = W.save(out_path)
    report['bytes'] = size
    report['groupTris'] = group_tris
    report['budget'] = {'lod0': 18000, 'lod1': 7000, 'lod2': 2500}
    report['withinBudget'] = all(tris[f'lod{l}'] <= report['budget'][f'lod{l}'] for l in LODS)
    report['clearance'] = clearance_rep
    report['collisions'] = cols
    report['seconds'] = round(time.time() - t0, 1)
    json.dump(report, open(os.path.splitext(out_path)[0] + '.report.json', 'w'), indent=1)
    return report


def summary(rep):
    out = {'style': rep['style'], 'bytes': rep['bytes'], 'bones': rep['bones'], 'springs': rep['springs'],
           'withinBudget': rep['withinBudget'], 'seconds': rep['seconds'], 'lods': rep['lods'],
           'groupTris': {k: ' / '.join(str(v.get(f'lod{l}', 0)) for l in LODS) for k, v in rep.get('groupTris', {}).items()}}
    if rep.get('clearance'):
        out['clearance'] = {k: {'restMinMM': round(v['rest']['minMM'], 2), 'restViol': v['rest']['violations'],
                                'morphMinMM': None if v['morphs']['minMM'] is None else round(v['morphs']['minMM'], 2),
                                'violatingCases': v['morphs']['violatingCases'][:5]}
                            for k, v in rep['clearance'].items()}
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('style'); ap.add_argument('sex'); ap.add_argument('out')
    ap.add_argument('--embed-textures', action='store_true')
    ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--only', default='', help='comma list of group names to build (authoring aid)')
    ap.add_argument('--no-shell', action='store_true')
    a = ap.parse_args()
    rep = build(a.style, a.sex, a.out, embed=a.embed_textures, check=not a.no_check,
                only=[x for x in a.only.split(',') if x] or None, no_shell=a.no_shell)
    print(json.dumps(summary(rep), indent=1))
