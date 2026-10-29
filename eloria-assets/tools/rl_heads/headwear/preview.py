"""Tiny orthographic painter's-algorithm previews (PIL only) for geometry checks.

    preview.py <visual>[,<visual>...] [sex] [out.png] [--head rl|legacy] [--hair style] [--fit fit.json]
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

import hwlib as h

VIEWS = {  # name: (right axis, up axis, toward-viewer axis)
    'front': (np.array([-1, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, 1])),
    'profile': (np.array([0, 0, 1]), np.array([0, 1, 0]), np.array([1, 0, 0])),  # from character's left
    'rear': (np.array([1, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, -1])),
    'top': (np.array([-1, 0, 0]), np.array([0, 0, -1]), np.array([0, 1, 0])),
}


def draw(layers, view, size=320, centre=None, span=0.42):
    right, up, toward = VIEWS[view]
    img = Image.new('RGB', (size, size), (40, 42, 48))
    dr = ImageDraw.Draw(img)
    polys = []
    light = np.array([0.3, 0.6, 0.75])
    light /= np.linalg.norm(light)
    for P, I, colour in layers:
        T = P[I]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        nn = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.maximum(nn, 1e-12)
        shade = 0.35 + 0.65 * np.abs(n @ light)
        depth = (T.mean(1) - centre) @ toward
        for k in range(len(T)):
            polys.append((depth[k], T[k], tuple(int(c * shade[k]) for c in colour)))
    polys.sort(key=lambda p: p[0])
    scale = size / span
    for _, tri, col in polys:
        pts = [(size / 2 + ((v - centre) @ right) * scale, size / 2 - ((v - centre) @ up) * scale) for v in tri]
        dr.polygon(pts, fill=col)
    return img


def sheet(rows, out, views=('front', 'profile', 'rear', 'top'), size=300, labels=None):
    W = Image.new('RGB', (size * len(views), size * len(rows) + 0), (20, 20, 20))
    for r, (layers, centre) in enumerate(rows):
        for c, v in enumerate(views):
            W.paste(draw(layers, v, size, centre), (c * size, r * size))
        if labels:
            ImageDraw.Draw(W).text((4, r * size + 4), labels[r], fill=(255, 255, 0))
    W.save(out)


if __name__ == '__main__':
    visuals = [int(v) for v in sys.argv[1].split(',')]
    sex = sys.argv[2] if len(sys.argv) > 2 else 'female'
    out = sys.argv[3] if len(sys.argv) > 3 else h.OUT + '/preview.png'
    head = h.rl_head(sex)
    centre = np.array([0, 1.66, 0.0])
    rows, labels = [], []
    for v in visuals:
        pc = h.piece(v, sex)
        rows.append(([(head['P'], head['I'], (200, 170, 150)), (pc['P'], pc['I'], (120, 190, 240))], centre))
        labels.append('%d %s %s' % (v, pc['name'], sex))
    sheet(rows, out, labels=labels)
    print(out)
