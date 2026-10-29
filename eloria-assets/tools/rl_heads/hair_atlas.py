"""Procedural hair-strand atlas for RL hair cards and clump meshes.

Layout (square atlas, v = root(0) -> tip(1) along each column):
  columns 0-3 : dense straight/wavy lock strips (for card sheets)
  columns 4-5 : sparse flyaway strips (silhouette breakup)
  columns 6-7 : curly tendril strips (helical locks, Mira)
Channels: RGB = neutral luminance detail (tinted at runtime by hair colour),
          A   = coverage. Root end darker; per-strand brightness jitter.
Deterministic (seeded) so the atlas is reproducible from this source.
"""
import numpy as np, sys
from PIL import Image

def draw_strands(H, W, n, rng, width_px=(0.8, 1.6), wave=0.0, curl=0.0, taper=True,
                 coverage=1.0, length=(0.75, 1.0), sparse=False):
    lum = np.zeros((H, W), np.float32); alpha = np.zeros((H, W), np.float32)
    ys = np.arange(H, dtype=np.float32)
    for s in range(n):
        x0 = rng.uniform(0.06, 0.94) * W
        L = rng.uniform(*length) * H
        start = rng.uniform(0, 0.08) * H if sparse else 0.0
        w = rng.uniform(*width_px)
        b = rng.uniform(0.55, 1.0)
        ph = rng.uniform(0, 6.283); fr = rng.uniform(1.5, 3.0)
        amp = wave * W * rng.uniform(0.4, 1.0)
        camp = curl * W * rng.uniform(0.6, 1.0); cfr = rng.uniform(5.0, 8.0)
        t = (ys - start) / max(L, 1)
        valid = (t >= 0) & (t <= 1)
        xc = x0 + amp * np.sin(fr * t * 3.1416 + ph) + camp * np.sin(cfr * t * 6.283 + ph) * np.clip(t * 3, 0, 1)
        xc += rng.normal(0, 0.15, size=xc.shape).cumsum() * 0.02
        ww = w * (1.0 - 0.85 * t ** 1.5) if taper else np.full_like(t, w)
        cov = coverage * (1.0 - np.clip((t - 0.85) / 0.15, 0, 1) ** 2)
        for yi in np.nonzero(valid)[0]:
            c = xc[yi]; hw = max(ww[yi], 0.35)
            x_lo = int(max(0, np.floor(c - hw - 1))); x_hi = int(min(W, np.ceil(c + hw + 1)))
            if x_hi <= x_lo: continue
            xs = np.arange(x_lo, x_hi) + 0.5
            a = np.clip(hw + 0.5 - np.abs(xs - c), 0, 1) * cov[yi]
            rootshade = 0.55 + 0.45 * np.clip(t[yi] * 4, 0, 1)
            seg = alpha[yi, x_lo:x_hi]
            lum[yi, x_lo:x_hi] = lum[yi, x_lo:x_hi] * (1 - a) + a * b * rootshade
            alpha[yi, x_lo:x_hi] = seg + a * (1 - seg)
    return lum, alpha

def build(size=1024, seed=7):
    rng = np.random.default_rng(seed)
    H = size; cw = size // 8
    L = np.zeros((H, size), np.float32); A = np.zeros((H, size), np.float32)
    specs = [
        dict(n=int(cw*1.6), wave=0.01),            # 0 dense straight
        dict(n=int(cw*1.5), wave=0.04),            # 1 dense wavy
        dict(n=int(cw*1.2), wave=0.03, length=(0.6, 1.0)),  # 2 dense tapered lock
        dict(n=int(cw*0.9), wave=0.06, length=(0.5, 1.0)),  # 3 medium lock
        dict(n=int(cw*0.18), wave=0.08, sparse=True, length=(0.4, 1.0), width_px=(0.6, 1.1)),  # 4 flyaway
        dict(n=int(cw*0.28), wave=0.12, sparse=True, length=(0.5, 1.0), width_px=(0.6, 1.2)),  # 5 flyaway wavy
        dict(n=int(cw*0.9), curl=0.10, length=(0.8, 1.0)),  # 6 curl dense
        dict(n=int(cw*0.5), curl=0.14, sparse=True, length=(0.6, 1.0)),  # 7 curl sparse
    ]
    for ci, sp in enumerate(specs):
        lum, a = draw_strands(H, cw, rng=rng, **sp)
        L[:, ci*cw:(ci+1)*cw] = lum; A[:, ci*cw:(ci+1)*cw] = a
    # un-premultiply so colour bleeds sensibly at alpha edges
    filled = np.where(A > 1e-3, L / np.maximum(A, 1e-3), 0.0)
    # dilate colour into empty texels (prevents dark fringes under mipmapping)
    base = np.clip(filled, 0, 1)
    mask = A > 0.02
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    base = base[idx[0], idx[1]]
    rgb = (np.stack([base]*3, -1) * 255).astype(np.uint8)
    out = np.dstack([rgb, (np.clip(A, 0, 1)*255).astype(np.uint8)])
    return Image.fromarray(out, 'RGBA')

if __name__ == '__main__':
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    build(size).save(sys.argv[1])
