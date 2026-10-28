"""Hair / beard textures for the RL hair modules (deterministic, seeded).

    python textures.py            # writes all three textures

build/hair/textures/hair_strands.png  1024^2 RGBA strand atlas (rl_hair_card)
    RGB = neutral grey luminance (tinted at runtime), A = coverage.
    v = 0 (image top) is the strand ROOT, v = 1 the TIP. 8 columns of 128 px:
      0 dense straight lock        4 flyaway: few straight strands
      1 dense wavy lock            5 flyaway: few wavy strands
      2 clumpy tapered lock        6 curl: dense ringlet strands
      3 sparse/broken lock edge    7 curl: sparse frizz
    Columns are padded (no strand crosses a column border) so cards can use
    u in [c/8, (c+1)/8] with linear filtering; colour is dilated into empty
    texels to avoid dark fringes under mipmapping.

build/hair/textures/hair_clump.png  1024^2 RGBA (rl_hair_clump), v3 layout
    from gen/hair_lock_v1.png (+ fine procedural strands), greyscale, low contrast.
    u in [0.14, 0.86] = opaque window whose colour repeats with period 0.72 (tubes,
    the bun core and the under-shell sample only this window; the shell in seamless
    sectors of exactly one period); u in [0, 0.14] and [0.86, 1] = the same colour
    with alpha breaking up into separate strands (ribbons map u 0..1 across their
    width -> hairy edges). v: root (0) opaque, the last 20% frays into pointed,
    strand-broken tips.

build/beards/textures/beard.png  1024^2 RGBA (rl_beard), 4 columns of 256 px:
      0 dense short coarse strands (cards)     2 moustache strands (longer, combed)
      1 sparse wiry strands (edge cards)       3 shell tile: dense short hair,
        periodic with period 192 px inside a 32 px margin each side (the beard
        shell is cut into strips whose UV width is exactly one period, so strips
        meet seamlessly while staying inside the column); its alpha thins into
        single hairs over the top 12% / bottom 8% of v (soft cheek / neck lines).
"""
import os, sys
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
RL = paths.RL_ROOT
OUT_HAIR = paths.HAIR_TEX
OUT_BEARD = paths.BEARD_TEX


# ----------------------------------------------------------------- strand raster
def raster_strands(H, W, n, rng, width_px=(0.9, 1.6), wave=0.0, curl=0.0, length=(0.75, 1.0),
                   start=(0.0, 0.0), coverage=1.0, x_range=(0.08, 0.92), lum=(0.5, 1.0), clump=0,
                   clump_spread=0.08, periodic=None, tilt=0.0, kink=0.0):
    """Vectorised anti-aliased strand rasteriser.
    Returns (luminance*alpha accumulation, alpha) arrays (H, W).
    periodic: if set (px), strands wrap horizontally with that period (tileable)."""
    acc_l = np.zeros((H, W)); log_t = np.zeros((H, W))
    ys = np.arange(H, dtype=np.float64)
    centers = rng.uniform(*x_range, max(1, clump)) * W if clump else None
    for s in range(n):
        if clump:
            x0 = centers[s % clump] + rng.normal(0, clump_spread * W)
        else:
            x0 = rng.uniform(*x_range) * W
        y0 = rng.uniform(*start) * H
        L = rng.uniform(*length) * H
        t = (ys - y0) / max(L, 1)
        valid = (t >= 0) & (t <= 1)
        if not valid.any():
            continue
        w = rng.uniform(*width_px)
        b = rng.uniform(*lum)
        ph = rng.uniform(0, 6.283); fr = rng.uniform(1.2, 2.6)
        amp = wave * W * rng.uniform(0.4, 1.0)
        camp = curl * W * rng.uniform(0.6, 1.0); cfr = rng.uniform(4.0, 7.0)
        xc = (x0 + amp * np.sin(fr * t * np.pi + ph) + camp * np.sin(cfr * t * 2 * np.pi + ph) * np.clip(t * 3, 0, 1)
              + tilt * W * t * rng.uniform(-1, 1))
        if kink:
            xc = xc + np.cumsum(rng.normal(0, kink, H))
        if clump:
            # strands of a clump converge toward the clump tip
            xc = xc + (centers[s % clump] - x0) * np.clip(t, 0, 1) ** 1.5 * 0.6
        hw = np.maximum(w * (1.0 - 0.8 * np.clip(t, 0, 1) ** 1.6), 0.35)
        cov = coverage * (1.0 - np.clip((t - 0.9) / 0.1, 0, 1) ** 2)
        rows = np.nonzero(valid)[0]
        for dx in range(-3, 4):
            xi = np.floor(xc[rows]).astype(int) + dx
            a = np.clip(hw[rows] + 0.5 - np.abs(xi + 0.5 - xc[rows]), 0, 1) * cov[rows]
            if periodic:
                xi = np.mod(xi, periodic)
            ok = (xi >= 0) & (xi < W) & (a > 0)
            r_ = rows[ok]; x_ = xi[ok]; a_ = a[ok]
            shade = b * (0.8 + 0.2 * np.clip(t[r_] * 3, 0, 1))
            np.add.at(acc_l, (r_, x_), a_ * shade)
            np.add.at(log_t, (r_, x_), np.log1p(-np.minimum(a_, 0.999)))
    alpha = 1 - np.exp(log_t)
    return acc_l, alpha


def column_image(H, W, specs, rng):
    lum_acc = np.zeros((H, W)); a_acc = np.zeros((H, W)); log_t = np.zeros((H, W))
    for sp in specs:
        l, a = raster_strands(H, W, rng=rng, **sp)
        lum_acc += l
        log_t += np.log1p(-np.minimum(a, 0.999))
    alpha = 1 - np.exp(log_t)
    # mean shade of overlapping strands: sum(a_i * shade_i) / sum(a_i), sum(a_i) ~ -log(transmittance)
    lum = np.where(alpha > 1e-3, np.clip(lum_acc / np.maximum(-log_t, 1e-6), 0, 1), 0)
    mask = alpha > 0.03
    if mask.any():
        idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
        lum = lum[idx[0], idx[1]]
    return lum, alpha


def to_rgba(lum, alpha, gamma=1.0):
    g = (np.clip(lum, 0, 1) ** gamma * 255).astype(np.uint8)
    a = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    return np.dstack([g, g, g, a])


# ----------------------------------------------------------------- hair atlas
def hair_strands(size=1024, seed=7):
    rng = np.random.default_rng(seed)
    H = size; cw = size // 8
    s = size / 1024
    cols = [
        [dict(n=int(150 * s), wave=0.008, width_px=(1.0, 1.7), lum=(0.45, 1.0))],
        [dict(n=int(140 * s), wave=0.05, width_px=(1.0, 1.7), lum=(0.45, 1.0))],
        [dict(n=int(110 * s), wave=0.03, length=(0.55, 1.0), clump=4, clump_spread=0.07, width_px=(1.0, 1.8))],
        [dict(n=int(40 * s), wave=0.05, length=(0.45, 1.0), width_px=(1.4, 2.2), start=(0, 0.05))],
        [dict(n=int(6 * s) + 2, wave=0.03, length=(0.55, 1.0), width_px=(1.8, 2.8), start=(0, 0.1), x_range=(0.2, 0.8))],
        [dict(n=int(8 * s) + 2, wave=0.12, length=(0.5, 1.0), width_px=(1.8, 2.8), start=(0, 0.1), x_range=(0.2, 0.8))],
        [dict(n=int(40 * s), curl=0.09, length=(0.8, 1.0), width_px=(1.8, 2.8), x_range=(0.2, 0.8))],
        [dict(n=int(14 * s), curl=0.14, length=(0.5, 1.0), width_px=(1.6, 2.4), start=(0, 0.1), x_range=(0.2, 0.8), kink=0.25)],
    ]
    L = np.zeros((H, size)); A = np.zeros((H, size))
    for ci, spec in enumerate(cols):
        lum, a = column_image(H, cw, spec, rng)
        # keep strands off the column borders
        edge = np.ones(cw); edge[:3] = 0; edge[-3:] = 0
        L[:, ci * cw:(ci + 1) * cw] = lum; A[:, ci * cw:(ci + 1) * cw] = a * edge[None]
    # normalise luminance to a neutral mid grey (runtime tints)
    m = L[A > 0.5].mean() if (A > 0.5).any() else 0.5
    L = np.clip(L * (0.62 / max(m, 1e-3)), 0, 1)
    return Image.fromarray(to_rgba(L, A), 'RGBA')


def strand_noise(H, W, rng, sigma=(60.0, 0.9), wrap=True):
    """Uniform [0,1] noise stretched along v (hair-strand streaks)."""
    nz = ndimage.gaussian_filter(rng.normal(0, 1, (H, W)), sigma, mode='wrap' if wrap else 'reflect')
    r = nz.ravel().argsort().argsort().reshape(H, W) / (H * W - 1.0)
    return r


def hair_clump(src, size=1024, band=96, seed=3, tip_from=0.8, tips=9, edge=0.14):
    """Lock texture from the painterly source (v3).

    u layout: [edge, 1 - edge] is the opaque window, its colour periodic with period
    (1 - 2 edge) (tubes and the shell live here, the shell in seamless sectors);
    the outer `edge` on both sides repeats the colour but its alpha thins out into
    separate strands (ribbons use u 0..1, giving hairy, not tube-like, silhouettes).
    v: root (0) opaque; the last (1 - tip_from) frays into pointed, strand-broken tips.
    Low contrast so overlapping locks read as soft shade, not black lines."""
    im = np.asarray(Image.open(src).convert('L')).astype(np.float64) / 255
    H, W = im.shape
    a = (np.arange(band) / band)[None, :]
    left = im[:, :band] * a + im[:, W - band:] * (1 - a)
    tile = np.concatenate([left, im[:, band:W - band]], 1)
    pw = int(round(size * (1 - 2 * edge)))                    # colour period in px
    img = Image.fromarray((np.clip(tile, 0, 1) * 255).astype(np.uint8), 'L').resize((pw, size), Image.LANCZOS)
    g = np.asarray(img).astype(np.float64) / 255
    # re-make exact periodicity after resampling (short cross-fade)
    bw = 24
    ramp = (np.arange(bw) / bw)[None, :]
    g[:, :bw] = g[:, :bw] * ramp + g[:, pw - bw:] * (1 - ramp)
    g = g[:, :pw - bw]
    pw = g.shape[1]
    g = (g - g.mean()) / max(g.std(), 1e-3) * 0.06
    rng0 = np.random.default_rng(seed + 100)
    acc, al = raster_strands(size, pw, 1100, rng0, width_px=(0.7, 1.3), wave=0.012, length=(0.55, 1.0),
                             start=(-0.2, 0.3), x_range=(0.0, 1.0), lum=(0.35, 1.0), periodic=pw)
    fine = np.where(al > 1e-3, acc / np.maximum(-np.log1p(-np.minimum(al, 0.999)), 1e-6), 0.5)
    fine = ndimage.gaussian_filter(fine, (2.0, 0.4), mode='wrap')
    fine = (fine - fine.mean()) / max(fine.std(), 1e-3) * 0.055
    win = np.clip(0.62 + g + fine, 0.08, 1.0)
    x0 = int(round(size * edge))
    cols = (np.arange(size) - x0) % pw
    gl = win[:, cols]
    # alpha: strand-broken edges in u
    rng = np.random.default_rng(seed)
    u = (np.arange(size) + 0.5) / size
    v = (np.arange(size) + 0.5) / size
    noise = strand_noise(size, size, rng)
    cov_u = np.minimum(smoothstep_np(u / edge), smoothstep_np((1 - u) / edge))
    cov_u = cov_u ** 0.8
    # fraying tips: coverage falls over the tip zone, lobed across u (pointed locks)
    centers = np.sort((np.arange(tips) + rng.uniform(-0.3, 0.3, tips)) / tips)
    lobe = np.zeros(size)
    for c in centers:
        w = rng.uniform(0.5, 1.0) / tips
        for sh in (-1, 0, 1):
            lobe = np.maximum(lobe, np.clip(1 - np.abs(u - (c + sh)) / w, 0, 1) ** 1.2 * rng.uniform(0.7, 1.0))
    tz = np.clip((v[:, None] - tip_from) / (1 - tip_from), 0, 1)       # 0 .. 1 over the tip zone
    cov_t = 1 - tz ** (1.0 + 2.5 * lobe[None, :])                       # lobes stay longer
    cov_t = np.clip(cov_t * 1.15, 0, 1)
    cov = np.minimum(cov_u[None, :], cov_t)
    alpha = np.clip((cov - noise) * 6 + 0.5, 0, 1)                       # strand-wise threshold, soft AA
    alpha[cov >= 0.999] = 1.0
    alpha[cov <= 0.001] = 0.0
    # edges / tips a touch lighter (thin hair transmits light) -- subtle
    gl = gl * (1 + 0.06 * (1 - cov))
    out = np.dstack([(np.clip(gl, 0, 1) * 255).astype(np.uint8)] * 3 + [(alpha * 255).astype(np.uint8)])
    return Image.fromarray(out, 'RGBA')


def smoothstep_np(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def beard(size=1024, seed=11):
    rng = np.random.default_rng(seed)
    H = size; cw = size // 4
    s = size / 1024
    L = np.zeros((H, size)); A = np.zeros((H, size))
    # cards are ~1 cm wide: a column holds a TUFT of a dozen thick tapering hairs
    # (each ~0.4 mm on the card) with gaps, converging toward the root
    specs = [
        [dict(n=int(16 * s), wave=0.05, curl=0.035, length=(0.6, 1.0), width_px=(5.0, 8.5), kink=0.35, lum=(0.45, 1.0),
              clump=3, clump_spread=0.1, x_range=(0.15, 0.85))],
        [dict(n=int(7 * s), wave=0.07, curl=0.05, length=(0.5, 1.0), width_px=(4.5, 7.0), kink=0.5, start=(0, 0.1),
              x_range=(0.2, 0.8), lum=(0.45, 1.0))],
        [dict(n=int(14 * s), wave=0.025, length=(0.7, 1.0), width_px=(5.0, 8.0), tilt=0.08, lum=(0.45, 1.0),
              clump=2, clump_spread=0.12, x_range=(0.15, 0.85))],
    ]
    for ci, spec in enumerate(specs):
        lum, a = column_image(H, cw, spec, rng)
        edge = np.ones(cw); edge[:4] = 0; edge[-4:] = 0
        L[:, ci * cw:(ci + 1) * cw] = lum; A[:, ci * cw:(ci + 1) * cw] = a * edge[None]
    # column 3: periodic shell tile (period 192 px, 32 px margins)
    per = 192 * cw // 256; margin = (cw - per) // 2
    lacc = np.zeros((H, per)); log_t = np.zeros((H, per))
    # many short overlapping strands so the tile tiles vertically too
    for band in range(14):
        l, a = raster_strands(H, per, int(300 * s), rng, width_px=(1.2, 2.0), wave=0.03, curl=0.02,
                              length=(0.06, 0.12), start=(band / 14 - 0.02, band / 14 + 0.06),
                              x_range=(0.0, 1.0), periodic=per, kink=0.1)
        lacc += l; log_t += np.log1p(-np.minimum(a, 0.999))
    alpha = 1 - np.exp(log_t)
    lum = np.where(alpha > 1e-3, np.clip(lacc / np.maximum(-log_t, 1e-6), 0, 1), 0)
    mask = alpha > 0.03
    idx = ndimage.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    lum = lum[idx[0], idx[1]]
    xs = (np.arange(cw) - margin) % per
    L[:, 3 * cw:] = lum[:, xs]; A[:, 3 * cw:] = alpha[:, xs]
    # soft cheek / neck lines: coverage thins into separate hairs over the first 12% of
    # v (top boundary) and the last 8% (bottom); the beard shell maps ~1 cm onto each band
    vv = (np.arange(H) + 0.5) / H
    cov = np.minimum(smoothstep_np(vv / 0.12), smoothstep_np((1 - vv) / 0.08))[:, None]
    nz = strand_noise(H, per, np.random.default_rng(seed + 7), sigma=(10.0, 1.2))[:, xs]
    fade = np.clip((cov - nz) * 5 + 0.5, 0, 1)
    fade[np.broadcast_to(cov >= 0.999, fade.shape)] = 1.0
    A[:, 3 * cw:] = A[:, 3 * cw:] * fade
    # per-column normalisation to a NARROW mid-grey range: no near-white strands that
    # read as grey/white speckles once tinted; colour is already dilated into the
    # transparent texels (nearest strand), so mip levels / alpha-test edges stay hair-coloured
    for ci in range(4):
        sl = slice(ci * cw, (ci + 1) * cw)
        Lc = L[:, sl]; Ac = A[:, sl]
        cov = Ac > 0.5
        m = Lc[cov].mean() if cov.any() else 0.5
        sd = Lc[cov].std() if cov.any() else 0.1
        L[:, sl] = np.clip(0.5 + (Lc - m) * (0.075 / max(sd, 1e-3)), 0.3, 0.68)
    # crisper alpha: fewer partial texels -> less alpha-test noise along strand edges
    A = np.clip((A - 0.25) / 0.5, 0, 1)
    return Image.fromarray(to_rgba(L, A), 'RGBA'), {'shellPeriodPx': per, 'shellMarginPx': margin, 'columnPx': cw}


def main():
    os.makedirs(OUT_HAIR, exist_ok=True); os.makedirs(OUT_BEARD, exist_ok=True)
    hair_strands().save(os.path.join(OUT_HAIR, 'hair_strands.png'), optimize=True)
    hair_clump(os.path.join(paths.GEN, 'hair_lock_v1.png')).save(os.path.join(OUT_HAIR, 'hair_clump.png'), optimize=True)
    b, info = beard()
    b.save(os.path.join(OUT_BEARD, 'beard.png'), optimize=True)
    print({'hair_strands': os.path.join(OUT_HAIR, 'hair_strands.png'), 'hair_clump': os.path.join(OUT_HAIR, 'hair_clump.png'),
           'beard': os.path.join(OUT_BEARD, 'beard.png'), 'beardShell': info})


if __name__ == '__main__':
    main()
