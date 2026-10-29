"""Paint the RL head textures in the head atlas (UV) space from 3D-aware masks.

python paint_head.py <build_dir> <sex> <style.json> <out_dir> [--size 2048]

Every texel knows its 3D rest position/normal (rasterised from the built head),
so features follow the surface rather than a frontal projection: lips come from
MPFB's 'lips' vertex group, ears/scalp from theirs, liner and lid crease from the
real lid rims, freckles/stubble are 3D dot fields. Brows use a front-facing
parametric curve (the brow region faces forward, so it does not stretch).

Outputs (lighting-free):
  head_<sex>_albedo.png    RGB  skin at the reference tone, painted variation only
  head_<sex>_features.png  RGBA R freckle dots, G lips, B brow hair, A lash line/liner
  head_<sex>_features2.png RGB  R stubble, G blush zones, B scalp/hairline
  head_<sex>_paint.json    reference tone + texel density + parameters
"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import json, math, os, sys, importlib.util
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
import mh

HERE = os.path.dirname(os.path.abspath(__file__))
R = paths.LOCAL


def extra_groups():
    p = os.path.join(R, 'blender_profile', 'extensions', 'user_default', 'mpfb', 'entities', 'socketobject', '_extra_vertex_groups.py')
    spec = importlib.util.spec_from_file_location('xg', p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    out = {}
    for k, v in m.vertex_group_information['basemesh'].items():
        w = np.zeros(len(mh.base().V))
        for e in v:
            if isinstance(e, (list, tuple)):
                w[int(e[0])] = float(e[1]) if len(e) > 1 else 1.0
            else:
                w[int(e)] = 1.0
        out[k] = w
    return out


def rasterize(UV, T, attrs, N):
    out = {k: np.zeros((N, N, a.shape[1]), np.float32) for k, a in attrs.items()}
    cov = np.zeros((N, N), bool)
    P = UV * N - 0.5
    for t in T:
        p = P[t]
        x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int)
        x0 = max(x0, 0); y0 = max(y0, 0); x1 = min(x1, N - 1); y1 = min(y1, N - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        v0 = p[1] - p[0]; v1 = p[2] - p[0]; den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        dx = xs - p[0, 0]; dy = ys - p[0, 1]
        b1 = (dx * v1[1] - v1[0] * dy) / den; b2 = (v0[0] * dy - dx * v0[1]) / den; b0 = 1 - b1 - b2
        m = (b0 >= -0.02) & (b1 >= -0.02) & (b2 >= -0.02)
        if not m.any():
            continue
        yy, xx = ys[m], xs[m]
        for k, a in attrs.items():
            out[k][yy, xx] = b0[m, None] * a[t[0]] + b1[m, None] * a[t[1]] + b2[m, None] * a[t[2]]
        cov[yy, xx] = True
    return out, cov


def dilate(img, cov):
    idx = ndimage.distance_transform_edt(~cov, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def hash3(p, seed=0):
    """Deterministic pseudo-random in [0,1) for integer lattice points (n,3)."""
    p = p.astype(np.int64)
    h = (p[..., 0] * 73856093) ^ (p[..., 1] * 19349663) ^ (p[..., 2] * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0x1000000)


def value_noise(P, cell, seed=0):
    g = P / cell; i = np.floor(g); f = g - i
    u = f * f * (3 - 2 * f)
    acc = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[..., 0] if dx else 1 - u[..., 0]) * (u[..., 1] if dy else 1 - u[..., 1]) * (u[..., 2] if dz else 1 - u[..., 2])
                acc = acc + w * hash3(i + np.array([dx, dy, dz]), seed)
    return acc


def fbm(P, cell, octaves=4, seed=0):
    a, s, tot = 1.0, 0.0, 0.0
    for o in range(octaves):
        s = s + a * value_noise(P, cell / (2 ** o), seed + o); tot += a; a *= 0.5
    return s / tot


def dots(P, cell, density, size, seed):
    """3D jittered dot field: one candidate dot per cell, kept with probability density(P).
    Returns coverage in [0,1] (soft disc of radius size*[0.5,1.2])."""
    g = P / cell; base = np.floor(g)
    cov = np.zeros(P.shape[:-1], np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = base + np.array([dx, dy, dz])
                jitter = np.stack([hash3(c, seed + k) for k in range(3)], -1)
                center = (c + jitter) * cell
                keep = hash3(c, seed + 7)
                r = size * (0.5 + 0.7 * hash3(c, seed + 9))
                strength = 0.55 + 0.45 * hash3(c, seed + 11)
                d = np.linalg.norm(P - center, axis=-1)
                disc = np.clip(1.2 - d / r, 0, 1) ** 1.5 * strength
                cov = np.maximum(cov, np.where(keep < density, disc, 0))
    return cov


def triplanar(img, P, N, scale):
    """Sample a tileable image triplanarly (P in metres, scale metres per tile)."""
    H, W = img.shape[:2]
    w = np.abs(N) ** 4; w /= w.sum(-1, keepdims=True) + 1e-9
    out = 0
    for a, (i, j) in enumerate(((1, 2), (0, 2), (0, 1))):
        u = (P[..., i] / scale) % 1.0; v = (P[..., j] / scale) % 1.0
        out = out + w[..., a:a + 1] * img[(v * (H - 1)).astype(int), (u * (W - 1)).astype(int)]
    return out


def polyline_dist(Q, poly):
    """Distance from points Q (n,3) to a polyline (m,3); also returns the arc parameter in [0,1]."""
    seg_a, seg_b = poly[:-1], poly[1:]
    L = np.linalg.norm(seg_b - seg_a, axis=1); cum = np.concatenate([[0], np.cumsum(L)]) / max(L.sum(), 1e-9)
    best = np.full(len(Q), np.inf); par = np.zeros(len(Q))
    for k in range(len(seg_a)):
        ab = seg_b[k] - seg_a[k]
        t = np.clip(((Q - seg_a[k]) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        d = np.linalg.norm(Q - (seg_a[k] + t[:, None] * ab), axis=1)
        m = d < best
        best[m] = d[m]; par[m] = cum[k] + t[m] * (cum[k + 1] - cum[k])
    return best, par


def brow_strokes(style, W=768, H=192, seed=3):
    """Brow hair strokes in brow-local (u along brow, v across) space, as an alpha image."""
    rng = np.random.default_rng(seed)
    im = Image.new('L', (W, H), 0); d = ImageDraw.Draw(im)
    n = style.get('brow_hairs', 900)
    for _ in range(n):
        u = rng.uniform(0, 1); v = rng.uniform(-1, 1)
        # hair direction: inner hairs point up, then sweep outward along the brow
        ang = math.radians(78 - 70 * smoothstep(0.0, 0.35, np.array(u)).item() + rng.normal(0, 8))
        ln = rng.uniform(0.05, 0.11) * W * (1.2 if u < 0.2 else 1.0)
        x0 = u * W; y0 = (0.5 - 0.5 * v) * H
        x1 = x0 + ln * math.cos(ang) * 0.6; y1 = y0 - ln * math.sin(ang) * 0.35 * (H / W) * 4
        a = int(150 + 105 * rng.uniform())
        d.line([(x0, y0), ((x0 + x1) / 2 + rng.normal(0, 2), (y0 + y1) / 2), (x1, y1)], fill=a, width=int(rng.choice([1, 1, 2])))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    return np.asarray(im, np.float32) / 255.0


def brow_decal(bs, n_hairs, ppm=24000, seed=11):
    """Brow as painted hair strokes. Control points (x outward, y up, thickness) are
    relative to the eye centre in metres. Returns an alpha image in a front-projected
    frame and its mapping (ppm = pixels per metre)."""
    from scipy.interpolate import CubicSpline
    ctrl = np.array(bs['points'])
    x0, x1 = ctrl[:, 0].min() - 0.006, ctrl[:, 0].max() + 0.006
    y0, y1 = ctrl[:, 1].min() - 0.01, ctrl[:, 1].max() + 0.01
    W, H = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
    SS = 2
    im = Image.new('L', (W * SS, H * SS), 0); d = ImageDraw.Draw(im)
    k = np.linspace(0, 1, len(ctrl))
    cx, cy, ct = CubicSpline(k, ctrl[:, 0]), CubicSpline(k, ctrl[:, 1]), CubicSpline(k, ctrl[:, 2])
    rng = np.random.default_rng(seed)
    def P(x, y):
        return ((x - x0) * ppm * SS, (y1 - y) * ppm * SS)
    # soft underpaint
    fill = bs.get('fill', 0.5)
    for u in np.linspace(0, 1, 160):
        th = float(ct(u)) * (0.35 + 0.65 * smoothstep(0.0, 0.18, np.array(u)).item())
        a = int(255 * fill * smoothstep(1.0, 0.82, np.array(u)).item() * (0.55 + 0.45 * smoothstep(0.0, 0.12, np.array(u)).item()))
        X, Y = P(float(cx(u)), float(cy(u)))
        r = th * ppm * SS * 0.42
        d.ellipse([X - r, Y - r * 0.9, X + r, Y + r * 0.9], fill=None, outline=None)
        d.ellipse([X - r, Y - r * 0.9, X + r, Y + r * 0.9], fill=a)
    under = np.asarray(im.filter(ImageFilter.GaussianBlur(ppm * SS * 0.0012)), np.float32) / 255
    im2 = Image.new('L', (W * SS, H * SS), 0); d2 = ImageDraw.Draw(im2)
    for _ in range(n_hairs):
        u = rng.beta(1.3, 1.15)
        th = float(ct(u))
        v = rng.uniform(-0.5, 0.5) * th
        tx, ty = float(cx(u, 1)), float(cy(u, 1)); tl = math.hypot(tx, ty); tx, ty = tx / tl, ty / tl
        nx, ny = -ty, tx
        bx, by = float(cx(u)) + nx * v, float(cy(u)) + ny * v
        # hair angle: inner hairs rise steeply, body hairs lie along the brow with a lift, tail follows the curve
        lift = math.radians(70 * (1 - smoothstep(0.0, 0.3, np.array(u)).item()) + 18 + rng.normal(0, 7))
        # upper hairs angle down, lower hairs angle up toward the centre line
        lift -= math.radians(25) * (v / max(th, 1e-6))
        dx, dy = tx * math.cos(lift) - ty * math.sin(lift) * -1, ty * math.cos(lift) + tx * math.sin(lift)
        ln = rng.uniform(0.0035, 0.0065) * (0.75 if u > 0.8 else 1.0)
        pts = []
        for t in np.linspace(0, 1, 5):
            bend = 0.12 * t * t * ln
            pts.append(P(bx + dx * ln * t - ny * bend * 0, by + dy * ln * t - bend))
        a = int(255 * rng.uniform(0.55, 1.0) * smoothstep(1.0, 0.9, np.array(u)).item())
        d2.line(pts, fill=a, width=max(1, int(round(rng.uniform(0.6, 1.3) * SS))))
    hairs = np.asarray(im2.filter(ImageFilter.GaussianBlur(0.5 * SS)), np.float32) / 255
    out = np.clip(under * 0.75 + hairs * 0.9 - under * hairs * 0.65, 0, 1)
    out = np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS), np.float32) / 255
    return out, {'x0': x0, 'y1': y1, 'ppm': ppm}


class _Opening:
    pass


def eye_opening(SP, ST, EP, c, res=0.00005):
    """Front-projected visible eye opening of one eye. query(points) returns the distance to
    the opening (0 inside), whether a point is on the upper-lid side, and whether it is skin
    visible from the front (not tucked under the lid fold)."""
    side = np.sign(c[0])
    E = EP[np.sign(EP[:, 0]) == side]
    # least-squares sphere through the eyeball (refit without the cornea bulge); the vertex mean
    # is biased forward by the cornea, so the sphere is fitted rather than assumed
    A = np.c_[2 * E, np.ones(len(E))]; bb = (E ** 2).sum(1)
    sol, *_ = np.linalg.lstsq(A, bb, rcond=None); cs = sol[:3]; rb = np.sqrt(sol[3] + cs @ cs)
    inl = np.abs(np.linalg.norm(E - cs, axis=1) - rb) < 0.0008
    sol, *_ = np.linalg.lstsq(A[inl], bb[inl], rcond=None); cs = sol[:3]; rb = np.sqrt(sol[3] + cs @ cs)
    x0, x1, y0, y1 = c[0] - 0.026, c[0] + 0.026, c[1] - 0.022, c[1] + 0.026
    W, H = int((x1 - x0) / res), int((y1 - y0) / res)
    depth = np.full((H, W), -np.inf, np.float32)
    tc = SP[ST]
    sel = (tc[:, :, 0].max(1) > x0) & (tc[:, :, 0].min(1) < x1) & (tc[:, :, 1].max(1) > y0) & (tc[:, :, 1].min(1) < y1)
    for t in tc[sel]:
        px = (t[:, 0] - x0) / res; py = (y1 - t[:, 1]) / res
        xa, xb = int(max(np.floor(px.min()), 0)), int(min(np.ceil(px.max()), W - 1))
        ya, yb = int(max(np.floor(py.min()), 0)), int(min(np.ceil(py.max()), H - 1))
        if xb < xa or yb < ya:
            continue
        xs, ys = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        v0 = np.array([px[1] - px[0], py[1] - py[0]]); v1 = np.array([px[2] - px[0], py[2] - py[0]])
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-9:
            continue
        dx = xs - px[0]; dy = ys - py[0]
        b1 = (dx * v1[1] - v1[0] * dy) / den; b2 = (v0[0] * dy - dx * v0[1]) / den; b0 = 1 - b1 - b2
        m = (b0 >= 0) & (b1 >= 0) & (b2 >= 0)
        if not m.any():
            continue
        z = b0 * t[0, 2] + b1 * t[1, 2] + b2 * t[2, 2]
        sub = depth[ya:yb + 1, xa:xb + 1]
        sub[m] = np.maximum(sub[m], z[m])
    gx = x0 + (np.arange(W) + 0.5) * res; gy = y1 - (np.arange(H) + 0.5) * res
    XX, YY = np.meshgrid(gx, gy)
    r2 = (XX - cs[0]) ** 2 + (YY - cs[1]) ** 2
    sphere = np.where(r2 < rb * rb, cs[2] + np.sqrt(np.maximum(rb * rb - r2, 0)), -np.inf)
    opening = sphere > depth + 0.0003
    lab, n = ndimage.label(opening)
    if n > 1:
        cl = lab[int((y1 - c[1]) / res), int((c[0] - x0) / res)]
        if cl == 0:
            cl = np.argmax(np.bincount(lab.ravel())[1:]) + 1
        opening = lab == cl
    opening = ndimage.binary_opening(opening, iterations=3)
    dist = ndimage.distance_transform_edt(~opening) * res
    cols = np.nonzero(opening.any(0))[0]
    ymid = np.full(W, np.nan)
    for k in cols:
        rows = np.nonzero(opening[:, k])[0]; ymid[k] = (rows.min() + rows.max()) / 2
    ka, kb = cols.min(), cols.max()
    ymid[:ka] = ymid[ka]; ymid[kb + 1:] = ymid[kb]
    op = _Opening()
    op.cx = x0 + (ka + kb) / 2 * res; op.span = (kb - ka) * res
    ko = kb if side > 0 else ka
    rows = np.nonzero(opening[:, ko])[0]; yo = int(rows.mean())
    zc = depth[yo, min(max(ko + int(side) * 4, 0), W - 1)]
    op.outer_corner = np.array([x0 + (ko + 0.5) * res, y1 - (yo + 0.5) * res, zc if np.isfinite(zc) else c[2] + rb * 0.6])
    def query(Q):
        px = np.clip(((Q[:, 0] - x0) / res).astype(int), 0, W - 1); py = np.clip(((y1 - Q[:, 1]) / res).astype(int), 0, H - 1)
        inside = (Q[:, 0] > x0) & (Q[:, 0] < x1) & (Q[:, 1] > y0) & (Q[:, 1] < y1)
        d = np.where(inside, dist[py, px], 1.0)
        upper = py < ymid[px]
        vis = inside & (Q[:, 2] >= depth[py, px] - 0.0006)
        return d, upper, vis
    op.query = query
    op.mask = opening
    op.frame = (x0, x1, y0, y1, res)
    return op


def neck_match(sex, style):
    """The shipped body's skin just below the neck-plane rim, normalised the way
    face_appearance.gdshader recolours it (a fifth of the local detail kept), placed on this
    head's painted reference tone: target(r) gives the sRGB colour per direction around the neck."""
    import io, json as _json
    import gamebody
    body = gamebody.Body(sex)
    g, blob = body.gltf, body.blob
    prim = g['meshes'][g['nodes'][body.meshes['body']['node']]['mesh']]['primitives'][0]
    tex = g['materials'][prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']
    bv = g['bufferViews'][g['images'][g['textures'][tex]['source']]['bufferView']]
    off = bv.get('byteOffset', 0)
    img = np.asarray(Image.open(io.BytesIO(blob[off:off + bv['byteLength']])).convert('RGB'), np.float32) / 255
    s2l = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    l2s = lambda c: np.where(c <= 0.0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055)
    models = _json.load(open(os.path.join(gamebody.ROOT, 'godot-client', 'data', 'actors', 'models.json'), encoding='utf-8'))['models']
    ref_b = s2l(np.array(models[f'luminous_{sex}']['skinPalette']['references']['body'][0]))
    o, d = body.plane(0.075)
    e1 = np.array([1.0, 0, 0]); e1 -= d * (e1 @ d); e1 /= np.linalg.norm(e1); e2 = np.cross(d, e1)
    if e2[2] < 0:
        e2 = -e2
    # the body's skin exactly where the head meets it: the clipped patch's rim vertices
    # (body UVs), each sampled with a small box filter; the shipped albedo carries baked
    # highlights, so a band average would miss the tone right at the joint
    hidden, patch, loop = gamebody.clip_patch(body, 0.075)
    rp = patch['P'][loop]; ruv = patch['UV'][loop]
    rr = rp - o - np.outer((rp - o) @ d, d)
    th = np.arctan2(rr @ e2, rr @ e1)
    H, W = img.shape[:2]
    lin = s2l(img)
    k = 3
    samp = []
    for u, v in ruv:
        x, y = int(u * W), int(v * H)
        samp.append(lin[max(y - k, 0):y + k + 1, max(x - k, 0):x + k + 1].reshape(-1, 3).mean(0))
    samp = np.array(samp)
    lum = lambda c: c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722
    f = (lum(samp) / lum(ref_b))[:, None] * 0.8 + (samp / ref_b) * 0.2
    o_ = np.argsort(th); ang = th[o_]; prof = f[o_]
    keep = np.concatenate([[True], np.diff(ang) > 1e-4]); ang = ang[keep]; prof = prof[keep]
    prof = np.stack([np.convolve(np.concatenate([prof[-1:, c], prof[:, c], prof[:1, c]]), np.ones(3) / 3, 'valid') for c in range(3)], 1)
    ref_h = s2l(np.array(style['skin_ref'], np.float32) / 255)
    def target(r_):
        t = np.arctan2(r_ @ e2, r_ @ e1)
        fv = np.stack([np.interp(t, ang, prof[:, k], period=2 * np.pi) for k in range(3)], 1)
        return l2s(ref_h * fv)
    return o, d, target, style.get('neck_fade', 0.035)


def paint(build_dir, sex, style, out_dir, N=2048):
    z = np.load(os.path.join(build_dir, f'rl_head_{sex}.npz'))
    SP, ST, SUV, SN, Sv, VG, EP = z['SP'], z['ST'], z['SUV'], z['SN'], z['Sv'], z['VG'], z['eyes']
    xg = extra_groups()
    def grp(name):
        w = np.zeros(len(SP)); m = Sv >= 0; w[m] = xg[name][Sv[m]]; return w[:, None]
    attrs = {'P': SP, 'N': SN, 'lips': grp('lips'), 'ears': grp('ears'), 'scalp': grp('scalp')}
    A, cov = rasterize(SUV, ST, attrs, N)
    P = A['P']; Nn = A['N'] / (np.linalg.norm(A['N'], axis=-1, keepdims=True) + 1e-9)
    lips = A['lips'][..., 0]; ears = A['ears'][..., 0]; scalp = A['scalp'][..., 0]
    # landmarks
    eL = EP[EP[:, 0] > 0].mean(0); eR = EP[EP[:, 0] < 0].mean(0); emid = (eL + eR) / 2
    r_eye = np.linalg.norm(EP[EP[:, 0] > 0] - eL, axis=1).max()
    body = VG
    mid = np.abs(body[:, 0]) < 1e-4
    nose = body[mid][np.argmax(body[mid][:, 2])]
    lipv = xg['lips'] > 0.5
    LV = body[lipv]
    mouthL = LV[np.argmax(LV[:, 0])]; mouthR = LV[np.argmin(LV[:, 0])]
    stom_y = LV[np.abs(LV[:, 0]) < 0.004][:, 1]
    lip_top, lip_bot = LV[:, 1].max(), LV[:, 1].min()
    # eye openings, measured in a front projection: where the eyeball shows in front of the skin
    openings = {side: eye_opening(SP, ST, EP, c) for side, c in (('L', eL), ('R', eR))}
    covall = cov.reshape(-1); keep_idx = np.nonzero(covall)[0]
    flat = P.reshape(-1, 3)[keep_idx]; fN = Nn.reshape(-1, 3)[keep_idx]; covf = np.ones(len(keep_idx), bool)
    lips = lips.reshape(-1)[keep_idx]; ears = ears.reshape(-1)[keep_idx]; scalp = scalp.reshape(-1)[keep_idx]
    PT = P.reshape(-1, 3)[keep_idx]; NT = Nn.reshape(-1, 3)[keep_idx]
    front = (fN[:, 2] > 0.15) & (flat[:, 2] > emid[2] - 0.045) & covf

    # ---------------- albedo ----------------
    base = np.array(style['skin_ref'], np.float32) / 255.0
    col = np.tile(base, (len(flat), 1))
    rel = flat - emid
    def gauss(center, sig):
        return np.exp(-((flat - center) ** 2).sum(1) / (2 * sig ** 2))
    blush = np.zeros(len(flat))
    for sx in (1, -1):
        blush += style.get('cheek_blush', 0.6) * gauss(emid + [sx * 0.036, -0.032, -0.006], 0.022)
    blush += 0.55 * gauss(nose + [0, -0.002, -0.004], 0.008)
    blush += 0.25 * gauss(emid + [0, -0.083, 0.0], 0.014)   # chin
    blush += 0.6 * ears.reshape(-1)
    blush = np.clip(blush, 0, 1)
    warm = np.array([1.0, -0.42, -0.5])
    col = col * (1 + 0.11 * blush[:, None] * warm)
    # painter's colour zones of the face (hue only, no light): yellower forehead,
    # redder mid-face, cooler/olive lower face (stronger on men: beard shadow)
    zs = style.get('zones', {})
    yrel = flat[:, 1] - emid[1]
    fore = smoothstep(0.015, 0.05, yrel) * front
    mid = np.exp(-((yrel + 0.03) / 0.022) ** 2) * smoothstep(0.07, 0.04, np.abs(flat[:, 0]))
    low = smoothstep(-0.055, -0.085, yrel) * smoothstep(0.08, 0.05, np.abs(flat[:, 0])) * smoothstep(-0.135, -0.105, yrel)   # face only, not the neck
    col = col * (1 + zs.get('forehead', 0.04) * fore[:, None] * np.array([0.6, 0.25, -0.9]))
    col = col * (1 + zs.get('mid', 0.05) * mid[:, None] * np.array([1.0, -0.35, -0.45]))
    col = col * (1 + zs.get('low', 0.04) * low[:, None] * np.array([-0.6, -0.1, 0.5]))
    # lid socket (soft ellipse above the lid) and under-eye, from the eye opening
    for side, c in (('L', eL), ('R', eR)):
        ex = (flat[:, 0] - c[0]) / 0.017; ey = (flat[:, 1] - c[1] - 0.006) / 0.009
        er = np.sqrt(ex * ex + ey * ey)
        crease = np.exp(-((er - 0.95) / 0.32) ** 2) * smoothstep(0.0015, 0.006, flat[:, 1] - c[1]) * front
        col = col * (1 - style.get('crease', 0.12) * crease[:, None] * np.array([0.8, 1.0, 1.1]))
        d2, upper, vis = openings[side].query(flat)
        under = np.exp(-((d2 - 0.0035) / 0.0032) ** 2) * (~upper) * vis * smoothstep(0.02, 0.011, np.abs(flat[:, 0] - c[0])) * front
        col = col * (1 - style.get('under_eye', 0.05) * under[:, None] * np.array([0.7, 1.0, 0.9]))
    # lips: natural shading inside the lip mask (the tint itself is a runtime feature)
    lm = lips.reshape(-1)
    inner = (fN[:, 2] < 0.2) & (np.abs(flat[:, 0] - emid[0]) < 0.03) & (flat[:, 1] < nose[1] - 0.008) & (flat[:, 1] > emid[1] - 0.095) & (flat[:, 2] < LV[:, 2].max() - 0.006) & (flat[:, 2] > emid[2] - 0.035)
    col[inner] = col[inner] * np.array([0.42, 0.22, 0.22])
    if len(stom_y):
        sy = stom_y.mean()
        line = np.exp(-((flat[:, 1] - sy) / 0.0011) ** 2) * smoothstep(0.2, 0.6, lm)
        col = col * (1 - 0.32 * line[:, None])
        lowfull = np.exp(-(((flat[:, 1] - (lip_bot + sy) / 2) / 0.003) ** 2 + (flat[:, 0] / 0.012) ** 2)) * (flat[:, 1] < sy) * lm
        col = col * (1 + 0.06 * lowfull[:, None])
    # painterly modulation
    brush = np.asarray(Image.open(os.path.join(R, 'gen', 'skin_brush_v1.png')).convert('RGB'), np.float32) / 255.0
    bmean = brush.reshape(-1, 3).mean(0)
    tb = triplanar(brush, PT, NT, 0.09).reshape(-1, 3)
    col = col * (1 + style.get('brush', 0.35) * (tb / bmean - 1))
    low = fbm(flat * 1.0, 0.03, 3, seed=5)
    col = col * (1 + 0.05 * (low[:, None] - 0.5) * np.array([1.0, 0.7, 0.6]))
    # neck: continue the shipped body's own (recolour-normalised) skin from the rim, so the
    # head's neck meets the body in one tone for any skin colour; fades out up the neck
    neck_w = np.zeros(len(flat))
    nm = neck_match(sex, style)
    if nm is not None:
        o_, d_, target_fn, fade = nm
        h = (flat - o_) @ d_
        w = 1 - smoothstep(fade * 0.15, fade, h)   # fully the body's tone near the rim, gradually the head's toward the jaw
        w *= 1 - 0.85 * front * smoothstep(-0.07, -0.05, flat[:, 1] - emid[1])   # leave the face/jaw front alone
        r_ = flat - o_ - np.outer(h, d_)
        target = target_fn(r_)
        # keep the painted variation but not its average: normalise it over the band
        ratio = col / base
        band = w > 0.5
        if band.any():
            ratio = ratio / np.median(ratio[band], 0)
        col = col * (1 - w[:, None]) + target * ratio * w[:, None]
        neck_w = w
    def scatter(a, ch):
        full = np.zeros((N * N, ch), np.float32); full[keep_idx] = a.reshape(len(keep_idx), ch); return full.reshape(N, N, ch)
    alb = scatter(np.clip(col, 0, 1), 3)

    # ---------------- features ----------------
    # freckles: density over nose bridge and upper cheeks
    fd = np.zeros(len(flat))
    fd += 0.9 * gauss(emid + [0, -0.016, 0.012], 0.013)
    for sx in (1, -1):
        fd += 0.85 * gauss(emid + [sx * 0.030, -0.024, 0.0], 0.017)
    fd += 0.22 * gauss(emid + [0, 0.035, 0.0], 0.03)
    fd = np.clip(fd, 0, 1) * front
    fr = np.zeros(len(flat), np.float32); act = np.nonzero(covf & (fd > 0.02))[0]
    fr[act] = dots(flat[act], 0.0017, np.clip(fd[act] * 1.1, 0, 0.95), 0.0008, seed=21)
    # lips mask
    lipmask = smoothstep(0.78, 0.97, lm)
    # brows: painted hair-stroke decals in front projection (the brow region faces forward).
    # Every selectable style is painted for this head (head_<sex>_brows.png, one per channel);
    # the runtime picks one and its thickness.
    styles = json.load(open(os.path.join(paths.SPECS, 'brow_styles.json')))
    def brow_mask(bs, hairs, seed):
        m = np.zeros(len(flat))
        pts = [[x, y + style.get('brow_offset_y', 0.0), t * style.get('brow_thick_scale', 1.0)] for x, y, t in bs['points']]
        dec, dmeta = brow_decal({'points': pts, 'fill': bs.get('fill', 0.7)}, hairs, seed=seed)
        for side, c in (('L', eL), ('R', eR)):
            sx = np.sign(c[0])
            sel = np.nonzero(front & (np.abs(flat[:, 0] - c[0]) < 0.06) & (flat[:, 1] > c[1] - 0.005) & (flat[:, 1] < c[1] + 0.045))[0]
            xo = sx * (flat[sel, 0] - c[0]); yo = flat[sel, 1] - c[1]
            px = ((xo - dmeta['x0']) * dmeta['ppm']).astype(int); py = ((dmeta['y1'] - yo) * dmeta['ppm']).astype(int)
            ok = (px >= 0) & (px < dec.shape[1]) & (py >= 0) & (py < dec.shape[0])
            val = np.zeros(len(sel)); val[ok] = dec[py[ok], px[ok]]
            m[sel] = np.maximum(m[sel], val)
        return m
    brow_styles = [brow_mask(bs, bs.get('hairs', 1200), 11 + k) for k, bs in enumerate(styles['styles'][:4])]
    browm = np.max(np.stack(brow_styles), 0)   # (only used to keep brows out of the skin reference)
    # liner / lash line: a band hugging the visible eye opening (front projection, visible skin
    # only); the wing is its own channel, a player option
    liner = np.zeros(len(flat)); wingm = np.zeros(len(flat))
    ls = style['liner']; wg = styles['wing']
    for side, c in (('L', eL), ('R', eR)):
        op = openings[side]
        sx = np.sign(c[0])
        d2, upper, vis = op.query(flat)
        outer = np.clip(sx * (flat[:, 0] - c[0]) / 0.016, -1, 1) * 0.5 + 0.5
        width = ls['inner'] + (ls['outer'] - ls['inner']) * outer
        lin = smoothstep(width, width * 0.35, d2) * upper * vis * front             * smoothstep(-op.span * 0.52, -op.span * 0.4, sx * (flat[:, 0] - op.cx))   # soft at the inner corner
        lowl = smoothstep(ls['lower'], ls['lower'] * 0.3, d2) * (~upper) * vis * front * ls.get('lower_strength', 0.3)             * smoothstep(op.span * 0.5, op.span * 0.3, np.abs(flat[:, 0] - op.cx))
        wl = wg['len']
        oc = op.outer_corner
        wdir = np.array([sx * math.cos(math.radians(wg['angle'])), math.sin(math.radians(wg['angle'])), -0.35])
        wdir /= np.linalg.norm(wdir)
        rel_w = flat - oc; along = rel_w @ wdir; perp = np.linalg.norm(rel_w - along[:, None] * wdir, axis=1)
        wing = (along > -0.0005) * smoothstep(wl, wl * 0.5, along) * smoothstep(wg['width'] * (1 - along / wl) + 2e-4, 0, perp) * vis * front
        liner = np.maximum(liner, np.maximum(lin, lowl))
        wingm = np.maximum(wingm, wing)
    # stubble region
    stub = np.zeros(len(flat))
    if style.get('stubble_region', False):
        below = smoothstep(nose[1] + 0.004, nose[1] - 0.012, flat[:, 1])  # under the nose line
        jaw_band = smoothstep(emid[1] - 0.036, emid[1] - 0.05, flat[:, 1])    # cheeks below the cheekbone
        side_ok = smoothstep(0.075, 0.06, np.abs(flat[:, 0]))
        neck_ok = smoothstep(emid[1] - 0.105, emid[1] - 0.08, flat[:, 1])   # fade out under the jaw, well above the neck seam
        region = np.maximum(below * smoothstep(0.03, 0.02, np.abs(flat[:, 0])), jaw_band) * side_ok * neck_ok
        region *= 1 - smoothstep(0.2, 0.5, lm)
        region *= (fN[:, 1] > -0.85) | (flat[:, 2] > emid[2] - 0.02)
        # beard zone only: in front of the jaw angle, never round the back of the neck
        region *= smoothstep(emid[2] - 0.095, emid[2] - 0.07, flat[:, 2])
        hairs = np.zeros(len(flat), np.float32); act = np.nonzero(covf & (region > 0.01))[0]
        hairs[act] = dots(flat[act], 0.0011, np.full(len(act), 0.85), 0.00042, seed=33)
        stub = region * (0.6 + 0.4 * hairs)
    scal = smoothstep(0.1, 0.6, scalp.reshape(-1))
    # B is the liner wing (brows moved to head_<sex>_brows.png)
    feats = scatter(np.stack([fr, lipmask, wingm, liner], -1), 4)
    brows4 = scatter(np.stack(brow_styles, -1), 4)
    # A: how much this texel is face (1) rather than neck matched to the body (0); the skin
    # shader lights the neck with the body's parameters there
    feats2 = scatter(np.stack([stub, blush, scal, 1 - neck_w], -1), 4)
    alb = dilate(alb, cov); feats = dilate(feats, cov); feats2 = dilate(feats2, cov); brows4 = dilate(brows4, cov)
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray((alb * 255).astype(np.uint8)).save(os.path.join(out_dir, f'head_{sex}_albedo.png'))
    Image.fromarray((np.clip(feats, 0, 1) * 255).astype(np.uint8), 'RGBA').save(os.path.join(out_dir, f'head_{sex}_features.png'))
    Image.fromarray((np.clip(feats2, 0, 1) * 255).astype(np.uint8), 'RGBA').save(os.path.join(out_dir, f'head_{sex}_features2.png'))
    Image.fromarray((np.clip(brows4, 0, 1) * 255).astype(np.uint8), 'RGBA').save(os.path.join(out_dir, f'head_{sex}_brows.png'))
    # reference tone = median of front-face skin (no lips/brows)
    face = front & (lm < 0.05) & (browm < 0.05)
    ref = np.median(np.clip(col, 0, 1)[face], 0)
    # texel density on the face front
    a3 = np.linalg.norm(np.cross(SP[ST[:, 1]] - SP[ST[:, 0]], SP[ST[:, 2]] - SP[ST[:, 0]]), axis=1) / 2
    uv = SUV * N
    e1 = uv[ST[:, 1]] - uv[ST[:, 0]]; e2 = uv[ST[:, 2]] - uv[ST[:, 0]]
    a2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    fc = (SP[ST].mean(1)[:, 2] > emid[2] - 0.02)
    dens = math.sqrt(a2[fc].sum() / a3[fc].sum()) / 100.0
    info = {'skin_reference': [float(x) for x in ref], 'texels_per_cm_face': dens, 'size': N, 'style': style}
    json.dump(info, open(os.path.join(out_dir, f'head_{sex}_paint.json'), 'w'), indent=1)
    return info


if __name__ == '__main__':
    N = int(sys.argv[sys.argv.index('--size') + 1]) if '--size' in sys.argv else 2048
    info = paint(sys.argv[1], sys.argv[2], json.load(open(sys.argv[3])), sys.argv[4], N)
    print(json.dumps({k: info[k] for k in ('skin_reference', 'texels_per_cm_face')}))
