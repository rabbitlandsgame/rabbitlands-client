"""Reference mesh: load (any number of meshes / materials), colour lookup and an
area-uniform point sample with normals and sRGB colours.

Colours come from the base-colour texture (bilinear, repeat wrap) times the
material baseColorFactor, else from COLOR_0, else from the factor alone.
Normals are welded vertex normals (UV seams share a position), interpolated
at the sample; the global orientation is made outward if the file is
inside-out.
"""
import numpy as np
import gltfio
from fitcommon import unit, log


def bilinear(tex, uv):
    """Sample tex (H,W,C) at glTF uv (u right, v down), repeat wrap."""
    H, W = tex.shape[:2]
    x = np.mod(uv[:, 0], 1.0) * W - 0.5
    y = np.mod(uv[:, 1], 1.0) * H - 0.5
    x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    x0m = np.mod(x0, W); x1m = np.mod(x0 + 1, W); y0m = np.mod(y0, H); y1m = np.mod(y0 + 1, H)
    c = (tex[y0m, x0m] * (1 - fx) * (1 - fy) + tex[y0m, x1m] * fx * (1 - fy) +
         tex[y1m, x0m] * (1 - fx) * fy + tex[y1m, x1m] * fx * fy)
    return c


class Cloud:
    """Point sample: X (n,3), N (n,3), C (n,3) sRGB, face (n,), bary (n,3)."""

    def __init__(self, X, N, C, face, bary):
        self.X, self.N, self.C, self.face, self.bary = X, N, C, face, bary

    def __len__(self):
        return len(self.X)

    def subset(self, idx):
        return Cloud(self.X[idx], self.N[idx], self.C[idx], self.face[idx], self.bary[idx])

    @staticmethod
    def concat(a, b):
        return Cloud(np.concatenate([a.X, b.X]), np.concatenate([a.N, b.N]), np.concatenate([a.C, b.C]),
                     np.concatenate([a.face, b.face]), np.concatenate([a.bary, b.bary]))


class RefMesh:
    def __init__(self, path=None, parts=None):
        if parts is None:
            parts = gltfio.read_any(path)
        self.path = path
        self.parts = parts
        Vs, Fs, fp = [], [], []
        off = 0
        for k, p in enumerate(parts):
            Vs.append(p['V']); Fs.append(p['F'] + off); fp.append(np.full(len(p['F']), k, np.int32))
            off += len(p['V'])
        self.V = np.concatenate(Vs).astype(np.float64)
        self.F = np.concatenate(Fs).astype(np.int64)
        self.fpart = np.concatenate(fp)
        self.vpart = np.concatenate([np.full(len(p['V']), k, np.int32) for k, p in enumerate(parts)])
        self.UV = np.full((len(self.V), 2), np.nan)
        self.vcol = np.full((len(self.V), 3), np.nan)
        o = 0
        for p in parts:
            n = len(p['V'])
            if p.get('UV') is not None:
                self.UV[o:o + n] = p['UV']
            if p.get('vcol') is not None:
                self.vcol[o:o + n] = p['vcol']
            o += n
        self.colour_source = sorted({(('texture x COLOR_0' if p.get('vcol') is not None else 'texture')
                                      if p.get('tex') is not None and p.get('UV') is not None else
                                      'COLOR_0' if p.get('vcol') is not None else 'factor') for p in parts})
        e1 = self.V[self.F[:, 1]] - self.V[self.F[:, 0]]
        e2 = self.V[self.F[:, 2]] - self.V[self.F[:, 0]]
        fn = np.cross(e1, e2)
        self.area = 0.5 * np.linalg.norm(fn, axis=1)
        self.fn = unit(fn)
        self._normals()

    @property
    def n_tris(self):
        return len(self.F)

    def _normals(self):
        span = float(np.ptp(self.V, axis=0).max()) or 1.0
        q = np.round(self.V / (span * 1e-7)).astype(np.int64)
        _, weld = np.unique(q, axis=0, return_inverse=True)
        weld = weld.ravel()
        acc = np.zeros((weld.max() + 1, 3))
        fnw = self.fn * self.area[:, None]
        for k in range(3):
            np.add.at(acc, weld[self.F[:, k]], fnw)
        self.weld = weld
        self.VN = unit(acc)[weld]
        # make the surface outward on the whole (per part): normals should point away from the centre
        c = (self.V * 0).mean(0) + np.average(self.V[self.F].mean(1), axis=0, weights=self.area + 1e-30)
        self.flipped_parts = []
        for k in range(len(self.parts)):
            fm = self.fpart == k
            if not fm.any():
                continue
            tc = self.V[self.F[fm]].mean(1)
            s = np.sum(((tc - c) * self.fn[fm]).sum(1) * self.area[fm])
            if s < 0:
                self.fn[fm] *= -1
                vm = self.vpart == k
                self.VN[vm] *= -1
                self.F[fm] = self.F[fm][:, [0, 2, 1]]
                self.flipped_parts.append(k)

    def colour(self, face, bary):
        """sRGB colour at (face, barycentric) samples."""
        out = np.ones((len(face), 3))
        tri = self.F[face]
        part = self.fpart[face]
        for k, p in enumerate(self.parts):
            m = part == k
            if not m.any():
                continue
            fac = np.asarray(p.get('factor', np.ones(4)))[:3]
            t = tri[m]; b = bary[m]
            if p.get('tex') is not None and p.get('UV') is not None:
                uv = (self.UV[t] * b[:, :, None]).sum(1)
                c = bilinear(p['tex'], uv)
                if p.get('vcol') is not None:
                    # glTF base colour = factor x texture x COLOR_0, multiplied in linear space
                    from fitcommon import srgb_to_linear, linear_to_srgb
                    vc = (self.vcol[t] * b[:, :, None]).sum(1)
                    c = linear_to_srgb(srgb_to_linear(c) * srgb_to_linear(vc))
                # the factor multiplies in linear space: (c_lin * f) in sRGB ~ c * f^(1/2.2)
                out[m] = c * fac ** (1 / 2.2)
            elif p.get('vcol') is not None:
                out[m] = (self.vcol[t] * b[:, :, None]).sum(1) * (fac ** (1 / 2.2))
            else:
                out[m] = fac ** (1 / 2.2)
        return np.clip(out, 0, 1)

    def sample(self, n, seed=0, face_mask=None):
        """Area-uniform sample of n points (optionally restricted to faces in face_mask)."""
        rng = np.random.default_rng(seed)
        a = self.area if face_mask is None else self.area * face_mask
        cdf = np.cumsum(a)
        if cdf[-1] <= 0:
            raise RuntimeError('reference has no surface area')
        face = np.searchsorted(cdf, rng.random(n) * cdf[-1])
        face = np.minimum(face, len(self.F) - 1)
        r1 = np.sqrt(rng.random(n)); r2 = rng.random(n)
        bary = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
        tri = self.F[face]
        X = (self.V[tri] * bary[:, :, None]).sum(1)
        N = unit((self.VN[tri] * bary[:, :, None]).sum(1))
        bad = (N * self.fn[face]).sum(1) < 0.2          # creases: use the face normal
        N[bad] = self.fn[face[bad]]
        C = self.colour(face, bary)
        return Cloud(X, N, C, face, bary)

    def summary(self):
        return {'parts': len(self.parts), 'triangles': int(len(self.F)), 'vertices': int(len(self.V)),
                'colour_source': self.colour_source, 'bbox_min': self.V.min(0).tolist(), 'bbox_max': self.V.max(0).tolist(),
                'flipped_parts': self.flipped_parts}
