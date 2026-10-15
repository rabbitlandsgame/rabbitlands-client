import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
d = np.load('cape_uv.npz'); uv, ls, lt, mi = d['uv'], d['ls'], d['lt'], d['mi']
S = 2048
label = np.full((S, S), -1, np.int8)
for p in range(len(ls)):
    t = uv[ls[p]:ls[p] + lt[p]] * [S, S] - 0.5
    for k in range(1, lt[p] - 1):
        q = t[[0, k, k + 1]]
        lo = np.maximum(np.floor(q.min(0)).astype(int), 0); hi = np.minimum(np.ceil(q.max(0)).astype(int), S - 1)
        if (lo > hi).any(): continue
        yy, xx = np.mgrid[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
        e1, e2 = q[1] - q[0], q[2] - q[0]; det = e1[0] * e2[1] - e1[1] * e2[0]
        if abs(det) < 1e-9: continue
        dx, dy = xx - q[0, 0], yy - q[0, 1]
        a = (dx * e2[1] - dy * e2[0]) / det; b = (e1[0] * dy - e1[1] * dx) / det
        inside = (a >= -0.02) & (b >= -0.02) & (a + b <= 1.02)
        label[yy[inside], xx[inside]] = mi[p]
label = label[::-1]                       # UV v up -> image rows top-down
im = Image.open('cape_src.png').convert('RGB').resize((S, S), Image.LANCZOS)
lum = np.asarray(im).astype(np.float32).mean(2) / 255.0
# Meshy bakes broad shading into the cloth (dark blotches by the shoulders);
# the engine lights the folds itself.  Flatten the low frequencies of the cloth
# and lining (divide by a wide blur over their own texels), keep fine weave.
from scipy.ndimage import gaussian_filter
for k in (0, 2):
    m = label == k
    w = gaussian_filter(m.astype(np.float32), 48)
    blur = gaussian_filter(np.where(m, lum, 0).astype(np.float32), 48) / np.maximum(w, 1e-3)
    flat = lum / np.maximum(blur, 0.05) * np.median(lum[m])
    lum = np.where(m, 0.25 * lum + 0.75 * flat, lum)
targets = {0: ('median', 0.86), 1: ('p80', 0.92), 2: ('median', 0.80)}
out = lum.copy(); gains = {}
for k, (stat, goal) in targets.items():
    m = label == k
    ref = np.median(lum[m]) if stat == 'median' else np.percentile(lum[m], 80)
    g = goal / max(ref, 1e-3); gains[k] = round(float(g), 3); out[m] = np.clip(lum[m] * g, 0, 1)
unl = label < 0
idx = distance_transform_edt(unl, return_distances=False, return_indices=True)
out[unl] = out[idx[0][unl], idx[1][unl]]
grey = (np.clip(out, 0, 1) * 255).astype(np.uint8)
Image.fromarray(np.stack([grey] * 3, 2)).save('cape_grey.png')
Image.fromarray(np.stack([grey] * 3, 2)).save('cape_grey.jpg', quality=92)
print(gains, {k: int((label == k).sum()) for k in (0, 1, 2)}, int(unl.sum()))
