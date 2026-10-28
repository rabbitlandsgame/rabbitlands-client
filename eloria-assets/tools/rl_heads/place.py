"""Place an MPFB head in game space so its cranium matches the shipped Human skull.

game = s * 0.1 * mh + t  (MakeHuman decimetres -> metres; both are Y up, face +Z)
The fit is a scale + (y, z) translation ICP of the MPFB cranium (above the brow
and behind the ears) onto the shipped head shell, then an inward conform of any
cranium vertex left outside the shell (helmets are fitted to that shell with
~9 mm clearance, so the new skull may not grow past it)."""
import numpy as np, trimesh
import mh


def cranium_mask(V, b):
    body = np.array(sorted(b.groups['body']))
    le = V[sorted(b.groups['helper-l-eye'])].mean(0)
    m = np.zeros(len(V), bool)
    sel = body[(V[body, 1] > le[1] + 0.35) | ((V[body, 2] < le[2] - 1.2) & (V[body, 1] > le[1] - 0.6))]
    m[sel] = True
    return m


def fit(V, body_glb, iters=40):
    b = mh.base()
    P_all, T = body_glb.skull()
    shell = trimesh.Trimesh(P_all, T, process=False)
    cm = cranium_mask(V, b)
    C = V[cm] * 0.1
    # initial: align eye centres
    eye = 0.1 * (V[sorted(b.groups['helper-l-eye'])].mean(0) + V[sorted(b.groups['helper-r-eye'])].mean(0)) / 2
    eyes_g = body_glb.meshes['eyes']['P'][np.unique(body_glb.meshes['eyes']['I'])].mean(0)
    s = 1.05
    t = np.array([0.0, eyes_g[1], eyes_g[2] - 0.012]) - s * eye
    for _ in range(iters):
        X = s * C + t
        cp, dist, _ = trimesh.proximity.closest_point(shell, X)
        # LSQ for s, ty, tz (tx fixed 0): minimise |s*C + t - cp|^2
        A = np.zeros((len(C) * 3, 3)); y = np.zeros(len(C) * 3)
        A[0::3, 0] = C[:, 0]; y[0::3] = cp[:, 0] - t[0]
        A[1::3, 0] = C[:, 1]; A[1::3, 1] = 1; y[1::3] = cp[:, 1]
        A[2::3, 0] = C[:, 2]; A[2::3, 2] = 1; y[2::3] = cp[:, 2]
        sol, *_ = np.linalg.lstsq(A, y, rcond=None)
        s, t = sol[0], np.array([0.0, sol[1], sol[2]])
    return s, t, shell, cm


def signed_outside(shell, X):
    cp, dist, tri = trimesh.proximity.closest_point(shell, X)
    n = shell.face_normals[tri]
    return np.sign(((X - cp) * n).sum(1)) * dist, cp, n
