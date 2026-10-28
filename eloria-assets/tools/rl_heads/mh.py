"""MakeHuman hm08 (MPFB) data in numpy: base mesh, targets, macro stacks and
.mhclo proxy fitting, reproducing MPFB's own linear maths so the RL head build
needs no Blender session. Units: MakeHuman decimetres, Y up, face toward +Z."""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import gzip, json, os, functools, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SYS = os.path.join(paths.LOCAL, 'mpfb_ext', 'data')
USER = os.path.join(paths.LOCAL, 'blender_profile', 'extensions', '.user', 'user_default', 'mpfb', 'data')  # installed CC0 MakeHuman system assets

class Obj:
    def __init__(self, path):
        V, VT, F, FT, G = [], [], [], [], []
        g = None
        with open(path) as fh:
            for line in fh:
                if line.startswith('v '): V.append([float(x) for x in line.split()[1:4]])
                elif line.startswith('vt '): VT.append([float(x) for x in line.split()[1:3]])
                elif line.startswith('g '): g = line.split()[1]
                elif line.startswith('f '):
                    vs, ts = [], []
                    for tok in line.split()[1:]:
                        p = tok.split('/'); vs.append(int(p[0]) - 1); ts.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                    F.append(vs); FT.append(ts); G.append(g)
        self.V = np.array(V); self.VT = np.array(VT) if VT else np.zeros((0, 2)); self.F = F; self.FT = FT; self.G = G

@functools.lru_cache(None)
def base():
    o = Obj(os.path.join(SYS, '3dobjs', 'base.obj'))
    o.groups = {}
    for f, g in zip(o.F, o.G): o.groups.setdefault(g, set()).update(f)
    return o

@functools.lru_cache(None)
def target(rel):
    p = rel if os.path.isabs(rel) else os.path.join(SYS, 'targets', rel)
    if not p.endswith('.gz') and not p.endswith('.target'): p += '.target.gz'
    opener = gzip.open if p.endswith('.gz') else open
    idx, d = [], []
    with opener(p, 'rt') as fh:
        for line in fh:
            s = line.split()
            if not s or s[0].startswith('#'): continue
            idx.append(int(s[0])); d.append([float(x) for x in s[1:4]])
    return np.array(idx, int), np.array(d)

def delta(rel, n=None):
    n = n or len(base().V)
    i, d = target(rel); out = np.zeros((n, 3))
    if len(i): out[i] = d
    return out

def apply(stack, V=None):
    V = (base().V if V is None else V).copy()
    for rel, w in stack:
        if abs(w) < 1e-6: continue
        i, d = target(rel)
        if len(i): V[i] += w * d
    return V

class Proxy:
    """A MakeHuman .mhclo proxy: each proxy vertex = sum(w_k * V[v_k]) + scaled offset."""
    def __init__(self, path):
        self.path = path; self.dir = os.path.dirname(path)
        self.ref, self.w, self.off = [], [], []
        mode = None; self.meta = {}
        with open(path) as fh:
            for line in fh:
                s = line.split()
                if not s or s[0].startswith('#'): continue
                if s[0] == 'verts': mode = 'v'; continue
                if s[0] in ('weights', 'delete_verts'): mode = None; continue
                if mode == 'v' and len(s) >= 9 and s[0].lstrip('-').isdigit():
                    self.ref.append([int(x) for x in s[:3]]); self.w.append([float(x) for x in s[3:6]]); self.off.append([float(x) for x in s[6:9]])
                elif mode == 'v' and len(s) == 1 and s[0].isdigit():
                    self.ref.append([int(s[0])] * 3); self.w.append([1, 0, 0]); self.off.append([0, 0, 0])
                elif mode is None or not s[0].lstrip('-').isdigit():
                    self.meta[s[0]] = s[1:]
        self.ref = np.array(self.ref); self.w = np.array(self.w); self.off = np.array(self.off)
        self.obj = Obj(os.path.join(self.dir, self.meta['obj_file'][0]))
        assert len(self.obj.V) == len(self.ref), (path, len(self.obj.V), len(self.ref))
    def scales(self, V):
        sc = []
        for ax, key in enumerate(('x_scale', 'y_scale', 'z_scale')):
            if key in self.meta:
                a, b, d = int(self.meta[key][0]), int(self.meta[key][1]), float(self.meta[key][2])
                sc.append(abs(V[a, ax] - V[b, ax]) / d)
            else: sc.append(1.0)
        return np.array(sc)
    def fit(self, V):
        return (self.w[:, :, None] * V[self.ref]).sum(1) + self.off * self.scales(V)

def user(rel): return os.path.join(USER, rel)
