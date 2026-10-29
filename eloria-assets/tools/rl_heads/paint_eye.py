"""Paint the shared RL eye texture in MPFB's high-poly eye UV layout.
RGB: sclera + neutral iris detail (tinted at runtime), A: iris mask (1 inside the iris).
python paint_eye.py <out.png> [size]"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import sys, os, numpy as np
from PIL import Image, ImageFilter
import mh
HERE = os.path.dirname(os.path.abspath(__file__)); R = paths.LOCAL
N = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
pr = mh.Proxy(mh.user('eyes/high-poly/high-poly.mhclo')); o = pr.obj
P = pr.fit(mh.base().V)
out = np.zeros((N, N, 4), np.float32)
yy, xx = np.mgrid[0:N, 0:N]; uvx = (xx + 0.5) / N; uvy = 1 - (yy + 0.5) / N   # obj uv (v up)
iris_img = np.asarray(Image.open(os.path.join(R, 'gen', 'iris_neutral_v1.png')).convert('RGB'), np.float32) / 255.0
ih, iw = iris_img.shape[:2]
# sclera base
out[..., :3] = np.array([0.93, 0.90, 0.86])
rng = np.random.default_rng(4)
for side in (1, -1):
    vs = np.nonzero(np.sign(P[:, 0]) == side)[0]
    c = P[vs].mean(0)
    faces = [k for k, f in enumerate(o.F) if np.sign(P[f, 0].mean()) == side]
    # eyeball (big UV island) only: skip the small cornea island
    fb = [k for k in faces if not ((o.VT[o.FT[k]][:, 0] > 0.8).all() and (o.VT[o.FT[k]][:, 1] < 0.2).all())]
    vids = sorted({v for k in fb for v in o.F[k]})
    # map vertex -> uv (first corner)
    uvof = {}
    for k in fb:
        for v, t in zip(o.F[k], o.FT[k]):
            uvof.setdefault(v, o.VT[t])
    vv = np.array(vids); uvv = np.array([uvof[v] for v in vids])
    dirs = (P[vv] - c); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    pole = np.argmax(dirs[:, 2]); cuv = uvv[pole]
    ang = np.degrees(np.arccos(np.clip(dirs[:, 2], -1, 1)))
    # uv radius for the iris edge (~30 deg half-angle) and the island edge
    near = np.abs(ang - 31) < 4
    r_iris = 0.128   # slightly larger than MPFB's ~0.115 for the painted look; MPFB high-poly eye layout: iris edge at uv radius ~0.115, pupil ~0.028
    print('eye', side, 'pole uv', cuv.round(3), 'iris uv radius', round(float(r_iris), 4))
    dx = uvx - cuv[0]; dy = uvy - cuv[1]; rr = np.sqrt(dx * dx + dy * dy) / r_iris
    th = np.arctan2(dy, dx)
    # iris from the generated painting (its disc fills ~86% of the square; pupil ~30%)
    sx = 0.5 + 0.43 * rr * np.cos(th); sy = 0.5 - 0.43 * rr * np.sin(th)   # painting: disc 86%, pupil 30%
    m = rr < 1.0
    samp = iris_img[np.clip((sy * (ih - 1)).astype(int), 0, ih - 1), np.clip((sx * (iw - 1)).astype(int), 0, iw - 1)]
    lum = samp.mean(-1, keepdims=True)
    iris = np.repeat(lum, 3, -1) * 1.15
    edge = np.clip((rr - 0.86) / 0.14, 0, 1)
    iris = iris * (1 - 0.55 * edge[..., None])
    a = np.clip((1.0 - rr) / 0.035, 0, 1)
    sel = rr < 1.08
    out[..., :3] = np.where(m[..., None], iris, out[..., :3])
    out[..., 3] = np.maximum(out[..., 3], a * (rr < 0.31).__invert__() + 0 * a)  # iris (not pupil)
    # pupil stays black in RGB, excluded from the tint mask
    # sclera: slight darkening away from the iris + faint warm vessels near the corners
    sc = (rr >= 1.0) & (rr < 4.5)
    shade = np.clip((rr - 1.2) / 3.0, 0, 1)
    out[..., :3] = np.where(sc[..., None], out[..., :3] * (1 - 0.18 * shade[..., None]) * np.array([1.0, 0.985, 0.975]) + shade[..., None] * np.array([0.02, -0.01, -0.01]), out[..., :3])
img = (np.clip(out, 0, 1) * 255).astype(np.uint8)
im = Image.fromarray(img, 'RGBA')
# soften the limbus a touch
im = Image.merge('RGBA', [ch.filter(ImageFilter.GaussianBlur(0.6)) for ch in im.split()])
im.save(sys.argv[1])
