"""Compose an identity 'look' texture from the painted head maps, mirroring the
runtime skin shader (used for offline previews and comparison sheets).
python look.py <tex_dir> <sex> <preset_name> <out.png>"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import json, os, sys, numpy as np
from PIL import Image

PRESETS = paths.REPO + '/godot-client/data/actors/rl_head_presets.json'


def s2l(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def l2s(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def lum(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def compose(tex, sex, p, detail_mix=0.55):
    alb = s2l(np.asarray(Image.open(f'{tex}/head_{sex}_albedo.png').convert('RGB'), np.float32) / 255)
    f = np.asarray(Image.open(f'{tex}/head_{sex}_features.png'), np.float32) / 255
    f2 = np.asarray(Image.open(f'{tex}/head_{sex}_features2.png').convert('RGB'), np.float32) / 255
    info = json.load(open(f'{tex}/head_{sex}_paint.json'))
    ref = s2l(info['skin_reference'])
    detail = alb / ref
    value = lum(alb) / lum(ref)
    skin = s2l(p['skin']) * (value[..., None] * (1 - detail_mix) + detail * detail_mix)
    skin = skin * (1 + p.get('blush', 0.3) * f2[..., 1:2] * np.array([0.10, -0.03, -0.04]))
    fr = f[..., 0:1] * p.get('freckles', 0.0)
    skin = skin * (1 - fr) + skin * np.array([0.55, 0.36, 0.25]) * fr
    st = f2[..., 0:1] * p.get('stubble', 0.0)
    hair = s2l(p['hair_color'])
    skin = skin * (1 - st) + (skin * 0.55 * 0.6 + hair * 0.4 * 0.6) * st
    lipc = s2l(p.get('lip_tint', [0.75, 0.45, 0.42])) * (lum(skin) / max(float(lum(s2l(p['skin']))), 1e-3))[..., None] * 1.1
    lm = f[..., 1:2] * 0.85
    skin = skin * (1 - lm) + lipc * lm
    ln = np.clip(f[..., 3:4] * p.get('liner', 0.4) + f[..., 2:3] * p.get('liner_wing', 0.0), 0, 1)
    skin = skin * (1 - ln) + np.array([0.035, 0.024, 0.02]) * ln
    bpath = f'{tex}/head_{sex}_brows.png'
    STY = {'arched': 0, 'straight': 1, 'soft': 2, 'angled': 3}
    k = STY.get(p.get('brow_style', 'arched' if sex == 'female' else 'straight'), 0)
    braw = (np.asarray(Image.open(bpath), np.float32) / 255)[..., k:k + 1] if os.path.exists(bpath) else f[..., 2:3]
    bw = np.clip((braw - 0.04) / 0.5, 0, 1) ** 0.85 * p.get('brow_density', 0.95)
    brow = s2l(p.get('brow_color') or [c * 0.75 for c in p['hair_color']])
    skin = skin * (1 - bw) + brow * bw
    return l2s(skin)


if __name__ == '__main__':
    tex, sex, name, out = sys.argv[1:5]
    p = json.load(open(PRESETS))['presets'][name]
    Image.fromarray((compose(tex, sex, p) * 255).astype(np.uint8)).save(out)
