"""Eye proportions from eye_measure.gd renders (local tool, not shipped).

python eye_metrics.py <render dir> [<render dir> ...] [--json out.json] [--overlay]

Per still pair (<name>.png + <name>_mask.png): the two eye openings in the mask
(non-magenta, non-black blobs), each measured for
  width W, height H (largest vertical extent), area fill A/(W*H), tilt of the
  inner->outer corner line (+ = outer corner higher), upper-lid apex position
  (0 inner .. 1 outer) and the apex rise over the corner line relative to W,
  iris diameter (widest horizontal run of iris pixels) and visible iris height,
  pupil-to-pupil distance (IPD),
plus from the normal still the dark liner band above and below the opening and
the gap from the opening's apex to the brow, and from a `front` mask the head
width on the eye row. Lengths are reported in cm (px_per_cm from the sidecar)
and as ratios to IPD.
"""
import json, os, sys, glob, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi


def load(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(np.float32) / 255.0


def classes(mask):
    r, g, b = mask[..., 0], mask[..., 1], mask[..., 2]
    skin = (r > 0.7) & (b > 0.7) & (g < 0.3)
    dark = (r + g + b) < 0.08
    # background: dark pixels connected to the border (a black pupil is not background)
    lab, n = ndi.label(dark)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border[border > 0])
    eye = ~skin & ~bg
    return skin, bg, eye


def hsv(img):
    mx = img.max(-1); mn = img.min(-1)
    s = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return s, mx


def eye_blobs(eye, skin):
    eye = ndi.binary_fill_holes(ndi.binary_opening(eye, np.ones((3, 3))))
    lab, n = ndi.label(eye)
    if n == 0:
        return []
    sizes = ndi.sum(eye, lab, range(1, n + 1))
    H, W = eye.shape
    cands = []
    for k in np.argsort(-sizes)[:6]:
        m = lab == (k + 1)
        ys, xs = np.nonzero(m)
        # must be surrounded by skin (not background next to the head)
        ring = ndi.binary_dilation(m, np.ones((5, 5))) & ~m
        if skin[ring].mean() < 0.6 or sizes[k] < 40:
            continue
        cands.append(m)
    cands = sorted(cands, key=lambda m: -m.sum())[:2]
    return sorted(cands, key=lambda m: np.nonzero(m)[1].mean())


def measure_eye(m, img_mask, side):
    """side: -1 for the eye on image left (character's right), +1 image right."""
    ys, xs = np.nonzero(m)
    x0, x1 = xs.min(), xs.max()
    W = x1 - x0 + 1
    cols = np.arange(x0, x1 + 1)
    top = np.array([ys[xs == c].min() if (xs == c).any() else np.nan for c in cols])
    bot = np.array([ys[xs == c].max() if (xs == c).any() else np.nan for c in cols])
    heights = bot - top + 1
    H = np.nanmax(heights)
    A = m.sum()
    # corners: mean y of the extreme 2% columns
    k = max(1, int(W * 0.02))
    left_y = np.nanmean((top[:k] + bot[:k]) / 2); right_y = np.nanmean((top[-k:] + bot[-k:]) / 2)
    # inner corner is towards the face centre: for the image-left eye that is its right end
    if side < 0:
        inner = (x1, right_y); outer = (x0, left_y)
    else:
        inner = (x0, left_y); outer = (x1, right_y)
    tilt = math.degrees(math.atan2(inner[1] - outer[1], abs(outer[0] - inner[0])))  # + = outer higher (y down)
    ia = int(np.nanargmin(top))
    apex_x = cols[ia]
    apex_t = (apex_x - inner[0]) / (outer[0] - inner[0])
    # rise of the upper lid apex over the corner line, and of the lower lid's lowest point
    def line_y(x):
        return inner[1] + (outer[1] - inner[1]) * (x - inner[0]) / (outer[0] - inner[0])
    upper_rise = line_y(apex_x) - top[ia]
    ib = int(np.nanargmax(bot))
    lower_drop = bot[ib] - line_y(cols[ib])
    # upper lid roundness: area under the upper curve over the corner line vs the triangle (0.5) .. box (1)
    t = np.clip((cols - inner[0]) / (outer[0] - inner[0]), 0, 1)
    up = np.nan_to_num(line_y(cols) - top)
    upper_fill = up.sum() / max(upper_rise * len(cols), 1)
    # iris / sclera from the unshaded eye colours
    # Iris: the dominant saturated hue of the opening (the eye colour), plus the dark
    # pupil / lid-shadowed iris; edge pixels (MSAA mixes with the magenta) are left out.
    inner_m = ndi.binary_erosion(m, iterations=2)
    iy_, ix_ = np.nonzero(inner_m)
    col = img_mask[iy_, ix_]
    s, v = hsv(col)
    mx = col.max(1); mn = col.min(1); d = np.maximum(mx - mn, 1e-6)
    r_, g_, b_ = col[:, 0], col[:, 1], col[:, 2]
    hue = np.where(mx == r_, ((g_ - b_) / d) % 6, np.where(mx == g_, (b_ - r_) / d + 2, (r_ - g_) / d + 4)) * 60
    seed = (s > 0.25) & (v > 0.2)
    iris_hue = 0.0
    if seed.any():
        hist, edges = np.histogram(hue[seed], bins=36, range=(0, 360), weights=(s * v)[seed])
        iris_hue = (edges[np.argmax(hist)] + 5.0)
    dh = np.abs((hue - iris_hue + 180) % 360 - 180)
    iris = ((s > 0.15) & (dh < 40)) | (v < 0.2)
    im = np.zeros_like(m); im[iy_[iris], ix_[iris]] = True
    im = ndi.binary_fill_holes(ndi.binary_opening(im, np.ones((3, 3))))
    lab, n = ndi.label(im)
    iris_d = iris_h = 0; ic = (np.nan, np.nan)
    if n:
        sizes = ndi.sum(im, lab, range(1, n + 1)); big = lab == (np.argmax(sizes) + 1)
        iy, ix = np.nonzero(big)
        rows = {}
        for y in np.unique(iy):
            r = ix[iy == y]; rows[y] = r.max() - r.min() + 1
        iris_d = max(rows.values()); iris_h = iy.max() - iy.min() + 1
        widest = [y for y in rows if rows[y] >= iris_d - 1]
        yc = float(np.mean(widest))
        xr = ix[np.abs(iy - yc) < 2]
        ic = (float((xr.min() + xr.max()) / 2), yc)
    return {'W': float(W), 'H': float(H), 'A': float(A), 'fill': float(A / (W * H)), 'tilt_deg': float(tilt),
            'apex_t': float(apex_t), 'upper_rise': float(upper_rise), 'lower_drop': float(lower_drop),
            'upper_fill': float(upper_fill), 'iris_d': float(iris_d), 'iris_h': float(iris_h),
            'iris_c': ic, 'x0': int(x0), 'x1': int(x1), 'top': top, 'bot': bot, 'cols': cols,
            'apex_x': int(apex_x), 'apex_y': float(top[ia]), 'inner': inner, 'outer': outer}


def liner_and_brow(img, e, skin_mask):
    """Dark band thickness above/below the opening, and the apex->brow gap, in px."""
    lum = img @ np.array([0.2126, 0.7152, 0.0722])
    cols = e['cols']; n = len(cols)
    # skin reference: the median luminance of skin 1.0-1.6 H below the opening
    yb = int(np.nanmax(e['bot']))
    ref_rows = slice(int(yb + 0.6 * e['H']), int(yb + 1.2 * e['H']))
    ref = np.median(lum[ref_rows, e['x0']:e['x1']])
    dark = lum < ref * 0.62
    up, down = [], []
    for i in range(int(n * 0.15), int(n * 0.85)):
        c = cols[i]
        if np.isnan(e['top'][i]):
            continue
        y = int(e['top'][i]) - 1; t = 0
        while y > 0 and dark[y, c] and t < 60:
            t += 1; y -= 1
        up.append(t)
        y = int(e['bot'][i]) + 1; t = 0
        while y < img.shape[0] - 1 and dark[y, c] and t < 60:
            t += 1; y += 1
        down.append(t)
    # brow: scan up from the apex over the opening's middle third, smoothed luminance profile
    xm0 = int(e['x0'] + (e['x1'] - e['x0']) * 0.35); xm1 = int(e['x0'] + (e['x1'] - e['x0']) * 0.65)
    prof = lum[:, xm0:xm1].mean(1)
    y_top = int(e['apex_y'])
    # skip the liner band
    start = y_top - int(np.percentile(up, 75) if up else 0) - 3
    seg = prof[max(0, int(start - 3.5 * e['H'])):start][::-1]   # going upward
    gap = np.nan
    if len(seg) > 5:
        seg_s = ndi.uniform_filter1d(seg, 5)
        base = np.median(seg_s[:max(3, int(0.3 * e['H']))])
        mn = seg_s.min()
        if base - mn > 0.06:
            half = base - 0.5 * (base - mn)
            idx = int(np.argmax(seg_s < half))
            gap = (y_top - start) + idx
    return {'liner_up': float(np.median(up)) if up else 0.0, 'liner_up_p90': float(np.percentile(up, 90)) if up else 0.0,
            'liner_down': float(np.median(down)) if down else 0.0, 'brow_gap': float(gap), 'skin_lum': float(ref)}


def head_width(mask_path):
    m = load(mask_path); skin, bg, eye = classes(m)
    head = ndi.binary_fill_holes(skin | eye)
    blobs = eye_blobs(eye, skin)
    if len(blobs) != 2:
        return np.nan, np.nan
    ys = [np.nonzero(b)[0].mean() for b in blobs]
    y = int(np.mean(ys))
    xs = np.nonzero(head[y])[0]
    # the run that contains the eyes
    runs = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)
    cx = np.mean([np.nonzero(b)[1].mean() for b in blobs])
    for r in runs:
        if r.min() <= cx <= r.max():
            return float(r.max() - r.min() + 1), y
    return np.nan, y


def analyse(png, overlay=False):
    mask_path = png[:-4] + '_mask.png'
    side = json.load(open(png[:-4] + '.json'))
    img = load(png); mk = load(mask_path)
    skin, bg, eye = classes(mk)
    blobs = eye_blobs(eye, skin)
    if len(blobs) != 2:
        return None
    eyes = [measure_eye(blobs[0], mk, -1), measure_eye(blobs[1], mk, 1)]
    for e in eyes:
        e.update(liner_and_brow(img, e, skin))
    ipd = math.dist(eyes[0]['iris_c'], eyes[1]['iris_c'])
    pxcm = side['px_per_cm']
    out = {'name': side['name'], 'look': side['look'], 'view': side['view'], 'expression': side['expression'],
           'px_per_cm': pxcm, 'ipd_cm': ipd / pxcm}
    keys = ['W', 'H', 'fill', 'tilt_deg', 'apex_t', 'upper_rise', 'lower_drop', 'upper_fill', 'iris_d', 'iris_h',
            'liner_up', 'liner_up_p90', 'liner_down', 'brow_gap']
    for k in keys:
        out[k] = float(np.nanmean([e[k] for e in eyes]))
    out['W_cm'] = out['W'] / pxcm; out['H_cm'] = out['H'] / pxcm; out['iris_cm'] = out['iris_d'] / pxcm
    out['W/IPD'] = out['W'] / ipd; out['H/IPD'] = out['H'] / ipd; out['H/W'] = out['H'] / out['W']
    out['iris/W'] = out['iris_d'] / out['W']; out['iris/H'] = out['iris_d'] / out['H']; out['iris/IPD'] = out['iris_d'] / ipd
    out['irisvis/iris'] = out['iris_h'] / max(out['iris_d'], 1)
    out['rise/W'] = out['upper_rise'] / out['W']; out['drop/W'] = out['lower_drop'] / out['W']
    out['liner_up/H'] = out['liner_up'] / out['H']; out['brow_gap/H'] = out['brow_gap'] / out['H']
    out['brow_gap/IPD'] = out['brow_gap'] / ipd
    out['gap_cm'] = (eyes[1]['x0'] - eyes[0]['x1']) / pxcm
    if overlay:
        im = Image.fromarray((img * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        for e in eyes:
            pts = [(c, t) for c, t in zip(e['cols'], e['top']) if not np.isnan(t)]
            d.line(pts, fill=(255, 0, 255), width=1)
            pts = [(c, t) for c, t in zip(e['cols'], e['bot']) if not np.isnan(t)]
            d.line(pts, fill=(0, 255, 255), width=1)
            cx, cy = e['iris_c']; r = e['iris_d'] / 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 0))
            d.line([e['inner'], e['outer']], fill=(0, 255, 0))
            if not np.isnan(e['brow_gap']):
                d.line([(e['apex_x'] - 10, e['apex_y'] - e['brow_gap']), (e['apex_x'] + 10, e['apex_y'] - e['brow_gap'])], fill=(255, 128, 0), width=2)
        im.save(png[:-4] + '_overlay.png')
    return out


def head_widths(dirs):
    res = {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, '*_front_*_mask.png')):
            side = json.load(open(p.replace('_mask.png', '.json')))
            w, y = head_width(p)
            res[side['look'] + '|' + os.path.basename(d)] = {'head_w_cm': w / side['px_per_cm'], 'row': y}
    return res


if __name__ == '__main__':
    argv = sys.argv[1:]
    out_json = None; overlay = '--overlay' in argv
    if '--json' in argv:
        out_json = argv[argv.index('--json') + 1]; argv = [a for a in argv if a not in ('--json', out_json)]
    dirs = [a for a in argv if not a.startswith('--')]
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, '*.png'))):
            if p.endswith('_mask.png') or p.endswith('_overlay.png') or not os.path.exists(p[:-4] + '_mask.png'):
                continue
            r = analyse(p, overlay)
            if r:
                r['set'] = os.path.basename(os.path.normpath(d)); rows.append(r)
    hw = head_widths(dirs)
    cols = ['set', 'look', 'view', 'expression', 'ipd_cm', 'W_cm', 'H_cm', 'iris_cm', 'H/W', 'W/IPD', 'H/IPD', 'iris/W', 'iris/H',
            'irisvis/iris', 'fill', 'tilt_deg', 'apex_t', 'rise/W', 'drop/W', 'upper_fill', 'liner_up', 'liner_up/H', 'liner_down', 'brow_gap/H', 'brow_gap/IPD']
    print('\t'.join(cols))
    for r in rows:
        print('\t'.join(str(r[c]) if isinstance(r[c], str) else f'{r[c]:.3f}' for c in cols))
    print(json.dumps(hw, indent=0))
    if out_json:
        json.dump({'rows': rows, 'head_width': hw}, open(out_json, 'w'), indent=1, default=float)
