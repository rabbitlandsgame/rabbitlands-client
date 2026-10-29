"""CPU triangle rasteriser (numpy z-buffer, orthographic cameras) for previews.

Every triangle's bounding box is enumerated pixel by pixel in vectorised
chunks, fragments are depth-sorted per pixel; the result is a face-id image
plus barycentrics, so any per-vertex attribute or texture can be shaded
afterwards.
"""
import numpy as np
from fitcommon import unit


class Camera:
    """Orthographic camera looking from direction d (unit, from target to camera)."""

    def __init__(self, d, center, half, size=512, up=(0, 1, 0)):
        self.d = unit(np.asarray(d, np.float64))
        up = np.asarray(up, np.float64)
        self.right = unit(np.cross(up, self.d))
        self.up = np.cross(self.d, self.right)
        self.center = np.asarray(center, np.float64)
        self.half = float(half)
        self.size = int(size)

    def project(self, X):
        Q = X - self.center
        px = (Q @ self.right / self.half * 0.5 + 0.5) * self.size
        py = (0.5 - Q @ self.up / self.half * 0.5) * self.size
        depth = -(Q @ self.d)          # smaller = closer
        return np.stack([px, py], 1), depth


VIEWS = {
    'front': (0.0, 0.0),
    'profile': (90.0, 0.0),
    'three_quarter': (40.0, 8.0),
}


def view_camera(name, center, half, size=512):
    yaw, pitch = VIEWS[name]
    y, p = np.radians(yaw), np.radians(pitch)
    d = np.array([np.sin(y) * np.cos(p), np.sin(p), np.cos(y) * np.cos(p)])
    return Camera(d, center, half, size)


def rasterize(P2, Z, T, W, H, chunk=6_000_000):
    """P2 (n,2) pixel coords, Z (n,) depth, T (m,3). Returns face id (H,W) (-1 empty),
    barycentrics (H,W,3), depth (H,W)."""
    A = P2[T[:, 0]]; B = P2[T[:, 1]]; C = P2[T[:, 2]]
    x0 = np.floor(np.minimum(np.minimum(A[:, 0], B[:, 0]), C[:, 0]) - 0.5).astype(np.int64)
    x1 = np.ceil(np.maximum(np.maximum(A[:, 0], B[:, 0]), C[:, 0]) - 0.5).astype(np.int64)
    y0 = np.floor(np.minimum(np.minimum(A[:, 1], B[:, 1]), C[:, 1]) - 0.5).astype(np.int64)
    y1 = np.ceil(np.maximum(np.maximum(A[:, 1], B[:, 1]), C[:, 1]) - 0.5).astype(np.int64)
    x0 = np.clip(x0, 0, W - 1); x1 = np.clip(x1, 0, W - 1); y0 = np.clip(y0, 0, H - 1); y1 = np.clip(y1, 0, H - 1)
    den = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
    ok = (np.abs(den) > 1e-12) & (x1 >= x0) & (y1 >= y0)
    ok &= ~((np.maximum(np.maximum(A[:, 0], B[:, 0]), C[:, 0]) < 0) | (np.minimum(np.minimum(A[:, 0], B[:, 0]), C[:, 0]) > W) |
            (np.maximum(np.maximum(A[:, 1], B[:, 1]), C[:, 1]) < 0) | (np.minimum(np.minimum(A[:, 1], B[:, 1]), C[:, 1]) > H))
    tid = np.nonzero(ok)[0]
    w = (x1 - x0 + 1)[tid]; h = (y1 - y0 + 1)[tid]
    cnt = w * h
    zbuf = np.full(W * H, np.inf)
    fbuf = np.full(W * H, -1, np.int64)
    bbuf = np.zeros((W * H, 3))
    csum = np.cumsum(cnt)
    start = 0
    while start < len(tid):
        base = csum[start - 1] if start else 0
        end = int(np.searchsorted(csum, base + chunk, side='right'))
        end = max(end, start + 1)
        sl = slice(start, end)
        t = tid[sl]; c = cnt[sl]
        tot = int(c.sum())
        rep = np.repeat(np.arange(len(t)), c)
        off = np.arange(tot) - np.repeat(np.cumsum(c) - c, c)
        ww = w[sl][rep]
        px = x0[t][rep] + off % ww
        py = y0[t][rep] + off // ww
        tt = t[rep]
        sx = px + 0.5; sy = py + 0.5
        Ct = C[tt]
        l0 = ((B[tt, 1] - Ct[:, 1]) * (sx - Ct[:, 0]) + (Ct[:, 0] - B[tt, 0]) * (sy - Ct[:, 1])) / den[tt]
        l1 = ((Ct[:, 1] - A[tt, 1]) * (sx - Ct[:, 0]) + (A[tt, 0] - Ct[:, 0]) * (sy - Ct[:, 1])) / den[tt]
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if inside.any():
            tt = tt[inside]; l0 = l0[inside]; l1 = l1[inside]; l2 = l2[inside]
            pix = py[inside] * W + px[inside]
            z = l0 * Z[T[tt, 0]] + l1 * Z[T[tt, 1]] + l2 * Z[T[tt, 2]]
            order = np.lexsort((z, pix))
            pix = pix[order]; z = z[order]
            first = np.ones(len(pix), bool); first[1:] = pix[1:] != pix[:-1]
            sel = order[first]
            pix = pix[first]; z = z[first]
            better = z < zbuf[pix]
            pb = pix[better]
            zbuf[pb] = z[better]
            fbuf[pb] = tt[sel[better]]
            bbuf[pb] = np.stack([l0[sel[better]], l1[sel[better]], l2[sel[better]]], 1)
        start = end
    return fbuf.reshape(H, W), bbuf.reshape(H, W, 3), zbuf.reshape(H, W)


def shade_lambert(N, light=(0.35, 0.55, 0.75), ambient=0.35):
    L = unit(np.asarray(light, np.float64))
    return ambient + (1 - ambient) * np.clip(N @ L, 0, 1)


def render_mesh(cam, V, T, vcolor=None, vnormal=None, face_color=None, bg=(1, 1, 1), shade=True, light_dir=None):
    """Simple shaded render: per-vertex colour (or face colour) x Lambert from a light
    fixed to the camera (upper left front). Returns uint8 (H,W,3) and the face-id image."""
    P2, Z = cam.project(V)
    fid, bary, _ = rasterize(P2, Z, T, cam.size, cam.size)
    img = np.ones((cam.size, cam.size, 3)) * np.asarray(bg)
    m = fid >= 0
    f = fid[m]; b = bary[m]
    tri = T[f]
    if face_color is not None:
        col = face_color[f]
    elif vcolor is not None:
        col = (vcolor[tri] * b[:, :, None]).sum(1)
    else:
        col = np.full((len(f), 3), 0.78)
    if shade and vnormal is not None:
        n = unit((vnormal[tri] * b[:, :, None]).sum(1))
        if light_dir is None:
            light_dir = unit(cam.d * 0.8 + cam.up * 0.45 - cam.right * 0.35)
        col = col * shade_lambert(n, light_dir, 0.38)[:, None]
    img[m] = col
    return (np.clip(img, 0, 1) * 255).astype(np.uint8), fid


def diverging(x, lim):
    """Blue (-lim) - white (0) - red (+lim) colour map, (n,3) 0..1."""
    t = np.clip(np.asarray(x) / lim, -1, 1)
    out = np.ones((len(t), 3))
    pos = t > 0
    out[pos] = np.stack([np.ones(pos.sum()), 1 - t[pos] * 0.85, 1 - t[pos] * 0.9], 1)
    neg = ~pos
    out[neg] = np.stack([1 + t[neg] * 0.9, 1 + t[neg] * 0.7, np.ones(neg.sum())], 1)
    return out
