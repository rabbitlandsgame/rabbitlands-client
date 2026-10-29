"""Shared helpers for the RL colour calibration fits (colour model spec rev 3)."""
import hashlib, json
from pathlib import Path
import numpy as np

CLIENT = Path(__file__).resolve().parents[2]
LUMA = np.array([0.2126, 0.7152, 0.0722])
SKIN_GAIN = {'female': np.array([1.3404, 1.3275, 1.3383]), 'male': np.array([1.1800, 1.1590, 1.1634])}
D_MAX = 1.6


def lin(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def enc(v):
    v = np.asarray(v, dtype=float)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.maximum(v, 0) ** (1 / 2.4) - 0.055)


def oklab(v):
    """linear sRGB -> OKLab (rows)."""
    v = np.atleast_2d(np.asarray(v, dtype=float))
    l = np.cbrt(0.4122214708 * v[:, 0] + 0.5363325363 * v[:, 1] + 0.0514459929 * v[:, 2])
    m = np.cbrt(0.2119034982 * v[:, 0] + 0.6806995451 * v[:, 1] + 0.1073969566 * v[:, 2])
    s = np.cbrt(0.0883024619 * v[:, 0] + 0.2817188376 * v[:, 1] + 0.6299787005 * v[:, 2])
    return np.stack([0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                     1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                     0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s], axis=1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def matte(d):
    d = np.atleast_2d(np.maximum(d, 0))
    return d * 0.9 + (d @ LUMA)[:, None] * 0.1


def light(d):
    d = np.atleast_2d(np.maximum(d, 0))
    warm = smoothstep(0.0, 0.35, d[:, 0] - np.maximum(d[:, 1], d[:, 2]))
    tint = 1.0 + (np.array([1.0, 0.90, 0.73]) - 1.0) * warm[:, None]
    return np.sqrt(d) * tint


def hue(d):
    d = np.atleast_2d(np.maximum(d, 0))
    peak = np.maximum(np.maximum(d[:, 0], d[:, 1]), np.maximum(d[:, 2], 1e-4))
    return d / peak[:, None]


TERMS = {'linear': ['gain', 'floor'], 'pigment': ['matte', 'light', 'floor'], 'rl': ['gain', 'hue', 'floor']}


def basis(model, d):
    d = np.atleast_2d(np.asarray(d, dtype=float))
    ones = np.ones_like(d)
    if model == 'linear':
        return [np.maximum(d, 0), ones]
    if model == 'pigment':
        return [matte(d), light(d), ones]
    if model == 'rl':
        return [np.maximum(d, 0), hue(d), ones]
    raise ValueError(model)


def fit(model, dyes, mus):
    """Per-channel least squares of mu on the model's basis terms."""
    terms = basis(model, dyes)
    mus = np.asarray(mus, dtype=float)
    params = {name: np.zeros(3) for name in TERMS[model]}
    for c in range(3):
        A = np.stack([t[:, c] for t in terms], axis=1)
        coef, *_ = np.linalg.lstsq(A, mus[:, c], rcond=None)
        for name, value in zip(TERMS[model], coef):
            params[name][c] = value
    return params


def predict(model, params, dyes):
    terms = basis(model, dyes)
    return sum(params[name][None, :] * term for name, term in zip(TERMS[model], terms))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def res_path(res: str) -> Path:
    assert res.startswith('res://'), res
    return CLIENT / res[len('res://'):]


def rounded(v, digits=6):
    return [round(float(x), digits) for x in np.asarray(v).ravel()]


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
