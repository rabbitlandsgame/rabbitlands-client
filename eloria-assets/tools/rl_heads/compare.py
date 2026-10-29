"""Reference vs render comparison sheet.
python compare.py <render_dir> <character> <out.png> [--kit underclothes]
Render landmarks (frame.json) are mapped onto the reference landmarks with a
least-squares scale+translation (no rotation, no shear), then shown as
reference | render | 50% overlay | edge overlay, per view.
"""
import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)))))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import sys, json, numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageDraw
REF = paths.REFERENCE
rd, ch, out = sys.argv[1], sys.argv[2], sys.argv[3]
kit = sys.argv[sys.argv.index('--kit') + 1] if '--kit' in sys.argv else 'underclothes'
LM = json.load(open(paths.LOCAL + '/ref/landmarks_ref.json'))[ch]
fr = json.load(open(rd + '/frame.json'))['views']
VIEWREF = {'front': 'front', 'side': 'side', 'tq': 'isometric'}
rows = []
for v in (sys.argv[sys.argv.index('--views') + 1].split(',') if '--views' in sys.argv else ('front', 'side', 'tq')):
    ref = Image.open(REF + f'{ch}/{kit}/{VIEWREF[v]}.png').convert('RGB')
    ren = Image.open(rd + f'/{v}.png').convert('RGB')
    keys = [k for k in LM[v] if k in fr[v]]
    if len(keys) >= 2:
        A = np.array([fr[v][k] for k in keys]); B = np.array([LM[v][k] for k in keys])
        ac, bc = A.mean(0), B.mean(0)
        s = np.sqrt(((B - bc) ** 2).sum() / ((A - ac) ** 2).sum())
        t = bc - s * ac
        cx, cy = B[:, 0].mean(), B[:, 1].mean()
    else:  # no reference landmarks: reuse front scale, centre on eyes
        s = rows_scale if 'rows_scale' in dir() else 1.0
        cx, cy = 525, 175 if ch == 'mira' else 130
        e = np.array(fr[v]['eye_mid']); t = np.array([cx, cy]) - s * e
    if v == 'front': rows_scale = s
    hw, hh = (int(x) for x in (sys.argv[sys.argv.index('--box') + 1].split(',') if '--box' in sys.argv else (130, 150)))
    box = (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))
    # warp render into reference pixel space: ref = s*ren + t  => ren = (ref - t)/s
    W, H = ref.size
    warped = ren.transform((W, H), Image.AFFINE, (1 / s, 0, -t[0] / s, 0, 1 / s, -t[1] / s), resample=Image.BICUBIC, fillcolor=(217, 214, 211))
    rc, wc = ref.crop(box), warped.crop(box)
    blend = Image.blend(rc, wc, 0.5)
    edges = wc.convert('L').filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p > 28 else 0)
    eo = rc.copy(); eo.paste((0, 255, 255), mask=edges)
    sc = float(sys.argv[sys.argv.index('--zoom') + 1]) if '--zoom' in sys.argv else 2
    cw, ch_ = int(2 * hw * sc), int(2 * hh * sc)
    row = Image.new('RGB', (4 * cw, ch_), 'white')
    for i, im in enumerate((rc, wc, blend, eo)): row.paste(im.resize((cw, ch_), Image.LANCZOS), (i * cw, 0))
    rows.append(row)
sheet = Image.new('RGB', (rows[0].width, sum(r.height for r in rows)), 'white')
y = 0
for r in rows: sheet.paste(r, (0, y)); y += r.height
sheet.save(out)
print('saved', out)
