"""Shared paths, small maths and colour helpers for the RL reference fitter.

Game space everywhere: metres, Y up, the face looks toward +Z, +X is the
character's LEFT (headref convention). Internal residuals are reported in mm.
"""
import os, sys, json, functools, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.normpath(os.path.join(HERE, '..'))                     # eloria-assets/tools/rl_heads
WT = os.path.normpath(os.path.join(TOOLS, '..', '..', '..'))           # repository root
RL = os.path.abspath(os.environ.get('RL_HEADS_LOCAL') or os.path.join(WT, '.local', 'rl-heads'))
GODOT = os.path.join(WT, 'godot-client')
HAIR_SCRIPTS = os.path.join(TOOLS, 'hair')
CONTROLS_JSON = os.path.join(TOOLS, 'specs', 'controls.json')
PRESETS_JSON = os.path.join(GODOT, 'data', 'actors', 'rl_head_presets.json')
HAIR_DIR = os.path.join(GODOT, 'assets', 'actors', 'native', 'rl_heads', 'hair')
BEARD_DIR = os.path.join(GODOT, 'assets', 'actors', 'native', 'rl_heads', 'beards')
LEGACY_HAIR_DIR = os.path.join(GODOT, 'assets', 'actors', 'native', 'hair', 'fitted')
CACHE_DIR = os.path.join(RL, 'fit', 'cache')
DEV_DIR = os.path.join(RL, 'fit', 'dev')

if HAIR_SCRIPTS not in sys.path:          # headref / rlglb are imported read-only
    sys.path.append(HAIR_SCRIPTS)
# The fitter depends on the hair agent's live scripts/hair/{headref,rlglb,paths}.py (read-only). Check the
# interface it uses up front so a refactor in progress fails with a clear message instead of deep inside.
HEADREF_API = ('Head', 'lonlat_dir', 'dir_lonlat', 'vertex_normals', 'barycentric', 'unit')
HEAD_ATTRS = ('P', 'T', 'N', 'weld', 'deltas', 'rim', 'vgroups', 'C', 'R', 'eyes', 'mesh', 'mesh_noear', 'T_noear',
              'mouth_interior', 'gltf', 'blob', 'mesh_index', 'target_names', 'npz_path', 'glb_path', 'Sv', 'VG')


class HeadrefError(RuntimeError):
    pass


try:
    import headref  # noqa: E402,F401  (rlglb puts scripts/ first on sys.path when imported)
except Exception as _ex:   # pragma: no cover - depends on the other agent's working tree
    raise HeadrefError(f'cannot import scripts/hair/headref.py ({_ex!r}); the hair scripts may be mid-edit - retry, '
                       'or check RL/scripts/hair') from _ex
_missing = [a for a in HEADREF_API if not hasattr(headref, a)]
if _missing:
    raise HeadrefError(f'scripts/hair/headref.py lacks {_missing}: its interface changed; the fitter needs '
                       f'{HEADREF_API}')


def check_head(h):
    miss = [a for a in HEAD_ATTRS if not hasattr(h, a)]
    if miss:
        raise HeadrefError(f'headref.Head lacks {miss}: the hair scripts changed their interface')
    return h
# this folder's modules must win over same-named files in scripts/ or scripts/hair/
if HERE in sys.path:
    sys.path.remove(HERE)
sys.path.insert(0, HERE)


@functools.lru_cache(None)
def control_names():
    spec = json.load(open(CONTROLS_JSON, encoding='utf-8'))
    return [c['name'] for c in spec['controls']]


@functools.lru_cache(None)
def presets():
    try:
        return json.load(open(PRESETS_JSON, encoding='utf-8'))['presets']
    except Exception:
        return {}


BASE_PRESET = {'female': 'mira', 'male': 'rowan'}


def kdq(kd, X, **kw):
    """cKDTree.query with threads only for large batches (thread start-up dominates small ones on Windows)."""
    return kd.query(X, workers=(-1 if len(X) >= 20000 else 1), **kw)


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def rot_axis_angle(axis, ang):
    """Rotation matrix about unit axis by ang radians."""
    a = unit(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def rot_vec(w):
    """Rotation matrix from a rotation vector (axis * angle)."""
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    return rot_axis_angle(w / th, th)


def rot_y(deg):
    return rot_axis_angle([0, 1, 0], np.radians(deg))


def rot_x(deg):
    return rot_axis_angle([1, 0, 0], np.radians(deg))


def rot_angle_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def project_rotation(M):
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R


def umeyama(A, B, w=None):
    """Similarity (s, R, t) minimising sum w |s R A + t - B|^2."""
    A = np.asarray(A, np.float64); B = np.asarray(B, np.float64)
    w = np.ones(len(A)) if w is None else np.asarray(w, np.float64)
    w = w / w.sum()
    ma = (w[:, None] * A).sum(0); mb = (w[:, None] * B).sum(0)
    A0 = A - ma; B0 = B - mb
    S = (w[:, None] * B0).T @ A0
    U, D, Vt = np.linalg.svd(S)
    E = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        E[2, 2] = -1
    R = U @ E @ Vt
    va = (w * (A0 ** 2).sum(1)).sum()
    s = float(np.trace(np.diag(D) @ E) / max(va, 1e-30))
    t = mb - s * R @ ma
    return s, R, t


class Sim:
    """Similarity x_game = s * R @ x_ref + t."""

    def __init__(self, s=1.0, R=None, t=None):
        self.s = float(s)
        self.R = np.eye(3) if R is None else np.asarray(R, np.float64)
        self.t = np.zeros(3) if t is None else np.asarray(t, np.float64)

    def __call__(self, X):
        return self.s * (np.asarray(X) @ self.R.T) + self.t

    def inv(self, Y):
        return ((np.asarray(Y) - self.t) @ self.R) / self.s

    def rot(self, N):
        return np.asarray(N) @ self.R.T

    def copy(self):
        return Sim(self.s, self.R.copy(), self.t.copy())

    def update(self, w, tau, sig, c):
        """Left-compose a small game-space update about centre c:
        x' = exp(sig) * Rw (x - c) + c + tau."""
        Rw = rot_vec(w)
        e = float(np.exp(sig))
        return Sim(self.s * e, Rw @ self.R, e * Rw @ (self.t - c) + c + tau)

    def matrix(self):
        M = np.eye(4)
        M[:3, :3] = self.s * self.R
        M[:3, 3] = self.t
        return M

    def to_json(self):
        return {'scale': round(self.s, 8), 'R': [[round(float(x), 8) for x in r] for r in self.R],
                't': [round(float(x), 8) for x in self.t]}


# ------------------------------------------------------------------ colour
def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


_M_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                   [0.2126729, 0.7151522, 0.0721750],
                   [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(c):
    xyz = srgb_to_linear(c) @ _M_XYZ.T / _WHITE
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], -1)


def luminance(c):
    return srgb_to_lab(c)[..., 0]


def r3(v, nd=4):
    return [round(float(x), nd) for x in v]


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter(); self.marks = []

    def mark(self, name):
        t = time.perf_counter()
        self.marks.append((name, t - self.t0))
        return t - self.t0

    def total(self):
        return time.perf_counter() - self.t0


LOG = {'quiet': False}


def log(*a):
    if not LOG['quiet']:
        print(*a, flush=True)
