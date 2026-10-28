"""Reference-vs-Godot comparison sheets.

python compare_godot.py <render_dir> <character> <out.png> [--kit underclothes] [--views front,three_quarter,profile]
          [--prefix mira_] [--suffix _neutral] [--box 120,140] [--zoom 2]

Each Godot still has a sidecar <name>.json with the projected landmarks. The render
is mapped onto the concept painting with a least-squares scale+translation fitted on
the landmarks both sides share (no rotation/shear), then shown as
reference | Godot render | 50% blend | render edges over the reference.
"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import sys, json, os, numpy as np
from PIL import Image, ImageFilter, ImageDraw

REF = paths.REFERENCE
LMREF = os.path.join(paths.SPECS, 'landmarks_ref.json')
VIEWMAP = {'front': ('front', 'front'), 'three_quarter': ('isometric', 'tq'), 'profile': ('side', 'side'), 'rear': ('side', 'side')}


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def landmarks_px(meta):
    lm = meta.get('landmarks', {})
    out = {}
    for k, v in lm.items():
        if isinstance(v, dict):
            v = v.get('pixel') or v.get('px') or v.get('screen') or v.get('projected')
        if v is not None and len(v) >= 2:
            out[k] = [float(v[0]), float(v[1])]
    return out


def main():
    rd, ch, out = sys.argv[1], sys.argv[2], sys.argv[3]
    kit = arg('--kit', 'underclothes')
    views = arg('--views', 'front,three_quarter,profile').split(',')
    prefix = arg('--prefix', ch + '_'); suffix = arg('--suffix', '_neutral')
    hw, hh = (int(x) for x in arg('--box', '120,140').split(','))
    zoom = float(arg('--zoom', '2'))
    L = json.load(open(LMREF))[ch]
    pairs = '--pairs' in sys.argv
    rows = []
    s_prof = None
    for v in views:
        refview, lmview = VIEWMAP[v]
        png = os.path.join(rd, f'{prefix}{v}{suffix}.png')
        meta = json.load(open(png[:-4] + '.json'))
        ren = Image.open(png).convert('RGB')
        ref = Image.open(REF + f'{ch}/{kit}/{refview}.png').convert('RGB')
        rl = landmarks_px(meta)
        rl.setdefault('eye_mid', [(rl['eyeL'][0] + rl['eyeR'][0]) / 2, (rl['eyeL'][1] + rl['eyeR'][1]) / 2] if 'eyeL' in rl and 'eyeR' in rl else None)
        if v == 'rear':
            # no back view in the studies: the side study at the profile row's scale, the
            # render's head (eye midpoint seen through it) on the study's eye
            s = s_prof
            B = np.array([L['side_eye']]); t = B[0] - s * np.array(rl['eye_mid'])
            cx, cy = B[0, 0] + 25, B[0, 1] + 10
        else:
            keys = [k for k in L[lmview] if rl.get(k) is not None]
            A = np.array([rl[k] for k in keys]); B = np.array([L[lmview][k] for k in keys])
            ac, bc = A.mean(0), B.mean(0)
            s = np.sqrt(((B - bc) ** 2).sum() / max(((A - ac) ** 2).sum(), 1e-9))
            t = bc - s * ac
            cx, cy = B[:, 0].mean(), B[:, 1].mean()
            if v == 'profile':
                s_prof = s
        box = (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))
        W, H = ref.size
        warped = ren.transform((W, H), Image.AFFINE, (1 / s, 0, -t[0] / s, 0, 1 / s, -t[1] / s), resample=Image.BICUBIC, fillcolor=(30, 30, 34))
        rc, wc = ref.crop(box), warped.crop(box)
        blend = Image.blend(rc, wc, 0.5)
        edges = wc.convert('L').filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p > 40 else 0)
        eo = rc.copy(); eo.paste((0, 255, 255), mask=edges)
        cw, chh = int(2 * hw * zoom), int(2 * hh * zoom)
        panels = ((rc, 'concept art' + (' (side study)' if v == 'rear' else '')), (wc, 'Godot render (in game, High)'))
        if not pairs and v != 'rear':
            panels = panels + ((blend, '50% blend'), (eo, 'render edges'))
        row = Image.new('RGB', (len(panels) * cw, chh + 26), 'white')
        d = ImageDraw.Draw(row)
        for i, (im, lab) in enumerate(panels):
            row.paste(im.resize((cw, chh), Image.LANCZOS), (i * cw, 26)); d.text((i * cw + 6, 6), f'{ch} {v} - {lab}', fill=(0, 0, 0))
        rows.append(row)
    sheet = Image.new('RGB', (max(r.width for r in rows), sum(r.height for r in rows)), 'white')
    y = 0
    for r in rows:
        sheet.paste(r, (0, y)); y += r.height
    sheet.save(out)
    print('saved', out)


if __name__ == '__main__':
    main()
