"""Fit the hair apparent-colour models from a hair_apparent_calibration fit run.

usage: python fit_hair.py <out-dir> <fit.json> [<fit.json> ...]

Writes:
  godot-client/data/actors/hair_apparent.json   (P1-P4, B1, B2 per sex/style/s)
  <out-dir>/rl_hair_luts.json                   (hairLut / beardLut for the RL data)
  <out-dir>/fit_report.json, <out-dir>/fit_summary.txt
"""
import json, sys
from pathlib import Path
import numpy as np
from calib_lib import (CLIENT, SKIN_GAIN, D_MAX, enc, fit, predict, sha256, res_path, rounded, load, TERMS)

out_dir = Path(sys.argv[1])
fit_paths = [Path(a) for a in sys.argv[2:]]
out_dir.mkdir(parents=True, exist_ok=True)
runs = [load(f) for f in fit_paths]
for one in runs:
    assert one['mode'] == 'fit', one['mode']
    assert one.get('exposure') == runs[0].get('exposure') and one.get('renderer') == runs[0].get('renderer')
run = {'mode': 'fit', 'exposure': runs[0].get('exposure'), 'renderer': runs[0].get('renderer'),
       'instances': [inst for one in runs for inst in one['instances']]}
MODEL_OF = {'P1': 'linear', 'P2': 'linear', 'P3': 'linear', 'B1': 'linear', 'B2': 'linear',
            'P4': 'pigment', 'P5': 'rl', 'B3': 'rl'}
MODELS = json.loads((CLIENT / 'data/actors/models.json').read_text(encoding='utf-8'))['models']
REFERENCE_STYLE = {'male': 1, 'female': 3}
RL_MODULE = {'male': 'rowan_shag', 'female': 'mira_bun'}
BEARD_NAMES = {2: 'moustache', 3: 'goatee', 4: 'short_beard', 5: 'full_beard'}


def hair_sources(sex, path, style):
    config = MODELS['luminous_' + sex]
    hair = config['hairStyles'][style]
    files = [hair]
    if path == 'P3':
        files.append('res://src/actors/portrait_hair.gdshader')
    if path == 'P4':
        files += ['res://src/actors/high_hair_appearance.gdshader', 'res://data/actors/hair_high/hero-locks.json']
    return files


def beard_sources(sex, path):
    return [MODELS['luminous_' + sex]['scene'], 'res://src/actors/portrait_beard.gdshader']


def rl_sources(kind, name):
    if kind == 'P5':
        return [f'res://assets/actors/native/rl_heads/hair/{name}.glb', 'res://src/actors/rl_head/rl_hair.gdshader',
                'res://assets/actors/native/rl_head_textures/hair_strands.png',
                'res://assets/actors/native/rl_head_textures/hair_clump.png']
    return [f'res://assets/actors/native/rl_heads/beards/{name}.glb', 'res://src/actors/rl_head/rl_hair.gdshader',
            'res://assets/actors/native/rl_head_textures/beard.png']


# ------------------------------------------------------------------ fits
fits = {}
report = {'instances': [], 'runs': [str(f) for f in fit_paths], 'exposure': run.get('exposure'),
          'renderer': run.get('renderer')}
for inst in run['instances']:
    path = inst['path']
    model = MODEL_OF[path]
    dyes = np.array([s['dye'] for s in inst['samples']])
    mus = np.array([s['mu'] for s in inst['samples']])
    params = fit(model, dyes, mus)
    pred = predict(model, params, dyes)
    g = SKIN_GAIN[inst['sex']]
    floor = mus[0]
    app_meas = enc(np.maximum((mus - floor) / g, 0))
    app_pred = enc(np.maximum((pred - floor) / g, 0))
    full = None
    if model == 'linear':
        A = np.c_[dyes, np.ones(len(dyes))]
        coef = np.linalg.lstsq(A, mus, rcond=None)[0]  # 4x3
        diag = np.abs(np.diag(coef[:3]))
        off = np.abs(coef[:3]) - np.diag(diag)
        full = float((off.max(axis=0) / diag).max())
    dmax = 1.0 if path in ('P5', 'B3') else D_MAX
    top = predict(model, params, np.array([[dmax] * 3]))[0]
    reach = enc(np.maximum((top - params['floor']) / g, 0))
    row = {'key': inst['key'], 'quality': inst['quality'], 'path': path, 'sex': inst['sex'], 'style': inst['style'],
           's': inst['s'], 'model': model, 'pixels': inst.get('pixels'),
           'params': {k: rounded(v) for k, v in params.items()},
           'residual_linear': float(np.abs(pred - mus).max()),
           'residual_apparent_srgb': float(np.abs(app_pred - app_meas).max()),
           'crosstalk': full, 'reach_srgb_grey': rounded(reach * 255, 1),
           'clipped': max(int(s.get('clipped', 0)) for s in inst['samples'])}
    for extra in ('length', 'volume', 'level'):
        if extra in inst:
            row[extra] = inst[extra]
    report['instances'].append(row)
    fits[(inst['quality'], inst['key'], inst.get('length', 50), inst.get('volume', 50))] = (model, params, floor)


def entry(quality, key, length=50, volume=50):
    return fits.get((quality, key, length, volume))


def share_error(params_a, params_b, sex):
    """Largest apparent sRGB error over a colour sweep when b's dye is drawn on a (linear models)."""
    g = SKIN_GAIN[sex]
    colours = np.array([[r, gg, b] for r in (0.01, 0.05, 0.15, 0.3) for gg in (0.01, 0.05, 0.15, 0.3)
                        for b in (0.01, 0.05, 0.15, 0.3)])
    dye = g * colours / params_b['gain']
    shown = params_a['gain'] * dye / g
    return float(np.abs(enc(shown) - enc(colours)).max())


comparisons = {'low_vs_medium': [], 'p2_vs_p1': [], 'p4_rl_vs_classic': []}
for (quality, key, length, volume), (model, params, floor) in fits.items():
    sex, path, style, s = key.split('/')
    if quality == 'low':
        medium = entry('medium', key)
        if medium:
            comparisons['low_vs_medium'].append({'key': key, 'error': share_error(params, medium[1], sex)})
    if path == 'P2':
        p1 = entry('medium', f'{sex}/P1/{style}/50')
        comparisons['p2_vs_p1'].append({'key': key, 'length': length, 'volume': volume,
                                        'error': share_error(params, p1[1], sex)})
    if quality == 'high-rl' and path == 'P4':
        classic = entry('high', key)
        if classic:
            dyes = np.array([[a, b, c] for a in (0.05, 0.3, 1.0) for b in (0.05, 0.3, 1.0) for c in (0.05, 0.3, 1.0)])
            a = predict('pigment', params, dyes)
            b = predict('pigment', classic[1], dyes)
            comparisons['p4_rl_vs_classic'].append({'key': key, 'max_mu_difference': float(np.abs(a - b).max())})
report['comparisons'] = comparisons

# ------------------------------------------------------------ hair_apparent.json
low_shares = all(c['error'] <= 0.003 for c in comparisons['low_vs_medium'])
p2_shares = all(c['error'] <= 0.003 for c in comparisons['p2_vs_p1'])
low_ratios = []
for (quality, key, length, volume), value in fits.items():
    if quality == 'low' and '/P1/' in key:
        low_ratios.append(float(np.mean(value[1]['gain'] / entry('medium', key)[1]['gain'])))
low_range = '%.2f-%.2f times' % (min(low_ratios), max(low_ratios)) if low_ratios else 'not measured'
# Shape factors: the hair length x volume grid, per sex, style and finish
# position, against 50 / 50 at that position (Medium linear gains; classic High
# pigment signal at grey 0.5): the full grid at Classic (s 50), a coarse one at
# the other measured positions.
GRID = [0, 25, 50, 75, 100]
COARSE = [0, 50, 100]
GREY = np.array([[0.5, 0.5, 0.5]])


def signal(model, params):
    return predict(model, params, GREY)[0] - params['floor']


shapes = {}
for sex in ('female', 'male'):
    for style in range(1, 10):
        for quality, kind, path_at in (('medium', 'medium', lambda s: 'P2' if s == 50 else 'P3'),
                                        ('high', 'high', lambda s: 'P4')):
            for s in (0, 25, 50, 75, 100):
                grid = GRID if s == 50 else COARSE
                centre_key = f'{sex}/P1/{style}/50' if (quality == 'medium' and s == 50) else f'{sex}/{"P3" if quality == "medium" else "P4"}/{style}/{s}'
                centre = entry(quality, centre_key)
                if centre is None:
                    continue
                base = signal(centre[0], centre[1])
                cells = {}
                for (q, key, length, volume), value in fits.items():
                    if q == quality and key == f'{sex}/{path_at(s)}/{style}/{s}' and (length, volume) != (50, 50) \
                            and length in grid and volume in grid:
                        cells[(length, volume)] = signal(value[0], value[1]) / base
                if len(cells) == len(grid) ** 2 - 1:
                    cells[(50, 50)] = np.ones(3)
                    shapes[f'{sex}/{kind}/{style}/{s}'] = {'grid': grid,
                        'factor': [rounded(cells[(l, v)], 5) for l in grid for v in grid]}
report['shapes'] = {k: {'min': float(np.min(v['factor'])), 'max': float(np.max(v['factor']))} for k, v in shapes.items()}
# Shape factor separability between the classic High grid and Medium (same style).
rl_shape = []
for (quality, key, length, volume), value in fits.items():
    if quality == 'high-rl' and '/P5/' in key and (length, volume) != (50, 50):
        default = entry('high-rl', key)
        if default:
            rl_shape.append({'key': key, 'length': length, 'volume': volume,
                             'gain_ratio': rounded(value[1]['gain'] / default[1]['gain'], 4)})
report['rl_shape'] = rl_shape
paths = {}
sources = {}


def add_sources(files):
    for f in files:
        if f not in sources:
            sources[f] = sha256(res_path(f))
    return files


def linear_entry(params, files, residual):
    return {'gain': rounded(params['gain']), 'floor': rounded(params['floor']), 'residual': round(residual, 6),
            'sources': add_sources(files)}


residual_of = {(r['quality'], r['key'], r.get('length', 50), r.get('volume', 50)): r['residual_linear']
               for r in report['instances']}
for sex in ('female', 'male'):
    for style in range(1, 10):
        p1 = entry('medium', f'{sex}/P1/{style}/50')
        if p1 is None:
            continue
        files = hair_sources(sex, 'P1', style)
        paths[f'{sex}/P1/{style}/50'] = linear_entry(p1[1], files, residual_of[('medium', f'{sex}/P1/{style}/50', 50, 50)])
        if p2_shares or shapes.get(f'{sex}/medium/{style}/50'):
            # P2 is P1's response; length and volume act through `shapes`
            # (a separate P2 gain on top of the shape factor would count the
            # reshaping twice).
            paths[f'{sex}/P2/{style}/50'] = dict(paths[f'{sex}/P1/{style}/50'], shares='P1')
        else:
            measured = [v for k, v in fits.items() if k[0] == 'medium' and k[1] == f'{sex}/P2/{style}/50']
            gain = np.mean([v[1]['gain'] for v in measured], axis=0)
            floor = np.mean([v[1]['floor'] for v in measured], axis=0)
            paths[f'{sex}/P2/{style}/50'] = linear_entry({'gain': gain, 'floor': floor}, files, 0.0)
        paths[f'{sex}/P3/{style}/50'] = dict(linear_entry(p1[1], hair_sources(sex, 'P3', style), 0.0), shares='P1')
        for s in (0, 12, 25, 37, 49, 51, 63, 75, 88, 100):
            p3 = entry('medium', f'{sex}/P3/{style}/{s}')
            if p3:
                paths[f'{sex}/P3/{style}/{s}'] = linear_entry(p3[1], hair_sources(sex, 'P3', style),
                                                             residual_of[('medium', f'{sex}/P3/{style}/{s}', 50, 50)])
        for s in (0, 12, 25, 37, 49, 50, 51, 63, 75, 88, 100):
            p4 = entry('high', f'{sex}/P4/{style}/{s}')
            if p4:
                params = p4[1]
                paths[f'{sex}/P4/{style}/{s}'] = {'model': 'pigment', 'matte': rounded(params['matte']),
                    'light': rounded(params['light']), 'floor': rounded(params['floor']),
                    'residual': round(residual_of[('high', f'{sex}/P4/{style}/{s}', 50, 50)], 6),
                    'sources': add_sources(hair_sources(sex, 'P4', style))}
    for beard in (2, 3, 4, 5):
        for path, quality in (('B1', 'medium'), ('B2', 'high')):
            b = entry(quality, f'{sex}/{path}/{beard}/50')
            if b:
                paths[f'{sex}/{path}/{beard}/50'] = linear_entry(b[1], beard_sources(sex, path),
                                                                  residual_of[(quality, f'{sex}/{path}/{beard}/50', 50, 50)])

about = ("Measured apparent-colour response of every Low/Medium and classic High hair path (colour model "
         "spec revision 3, 4.4): the lit mean of the hair alone (linear light) on the RL head stage's neutral "
         "look, Forward+, front view, 512 px, at tone-mapping exposure %.2f (unclipped), as a function of the "
         "dye d (linear). Keys <sex>/<path>/<style>/<s>: P1 Low/Medium Classic; P2 Classic with length or "
         "volume off 50, which is P1's response; P3 Low/Medium at finish position s (0, 25, 75 and 100, and the "
         "custom positions 12, 37, 49, 51, 63 and 88 between them; s 50 is P1's response), P4 the classic High "
         "hair finish (pigment model) at the same positions and 50; a position in between is linear between "
         "its measured neighbours; "
         "B1/B2 the Low/Medium and High beard shells by facial_hair. Linear entries: mu = gain * d + floor; "
         "pigment entries: see AppearanceColours.model_mu. The apparent colour of dye d is (mu(d) - floor) / "
         "skinGain. `shapes` scales a hairstyle's response by its hair length and volume: keys "
         "<sex>/<medium|high>/<style>/<s>, measured on a 5 x 5 grid at Classic (s 50) and a 3 x 3 grid at 0, 25, "
         "75 and 100 (Medium for P1-P3, classic High for P4), bilinear (a 3 x 3 grid with the Classic grid's "
         "curvature between its nodes, AppearanceColours._shape_at), linear in s. Low draws the Medium "
         "response: its hair is %s brighter than Medium for every colour, palette included, because Low actors "
         "cast no shadows (no self-shadowing in the hair); custom colours keep the palette's relationship. "
         "Written by tools/colour_calibration/fit_hair.py from tests/integration/hair_apparent_calibration.gd; "
         "each entry lists its source files, whose SHA-256 is in `sources` (tests/test_appearance_colours.gd "
         "fails when one changes: re-run the probe).") % (run.get('exposure', 1.0), low_range)
lines = ['{', '\t"version": 2,', '\t"about": %s,' % json.dumps(about),
         '\t"dMax": %s,' % D_MAX, '\t"exposure": %s,' % run.get('exposure', 1.0),
         '\t"skinGain": {"female": %s, "male": %s},' % (rounded(SKIN_GAIN['female'], 4), rounded(SKIN_GAIN['male'], 4)),
         '\t"sources": {']
items = sorted(sources.items())
for i, (k, v) in enumerate(items):
    lines.append('\t\t%s: "%s"%s' % (json.dumps(k), v, ',' if i < len(items) - 1 else ''))
lines.append('\t},')
lines.append('\t"shapes": {')
skeys = sorted(shapes)
for i, k in enumerate(skeys):
    lines.append('\t\t%s: %s%s' % (json.dumps(k), json.dumps(shapes[k]), ',' if i < len(skeys) - 1 else ''))
lines.append('\t},')
lines.append('\t"paths": {')
keys = sorted(paths)
for i, k in enumerate(keys):
    lines.append('\t\t%s: %s%s' % (json.dumps(k), json.dumps(paths[k]), ',' if i < len(keys) - 1 else ''))
lines += ['\t}', '}', '']
(CLIENT / 'data/actors/hair_apparent.json').write_bytes('\n'.join(lines).encode('utf-8'))

# ------------------------------------------------------------ RL hair and beard LUTs
rl = {'hairLut': {}, 'beardLut': {}, 'sources': {}}
for sex in ('female', 'male'):
    ref = entry('medium', f'{sex}/P1/{REFERENCE_STYLE[sex]}/50')
    module = RL_MODULE[sex]
    levels = {}
    for (quality, key, length, volume), (model, params, floor) in fits.items():
        # Only the module at its own length and volume: the rlshape spot checks
        # share the authored level's key and must not replace its response.
        if quality == 'high-rl' and key.startswith(f'{sex}/P5/{module}/') and (length, volume) == (50, 50):
            level = int(key.split('/')[-1])
            levels[str(level)] = {'model': 'rl', 'gain': rounded(params['gain']), 'hue': rounded(params['hue']),
                                  'floor': rounded(params['floor']),
                                  'residual': round(residual_of[(quality, key, 50, 50)], 6)}
    if levels and ref:
        for f in rl_sources('P5', module):
            rl['sources'][f] = sha256(res_path(f))
        rl['hairLut'][sex] = {module: {'levels': dict(sorted(levels.items(), key=lambda kv: int(kv[0]))),
                                       'targetFloor': rounded(ref[1]['floor']), 'sources': rl_sources('P5', module)}}
    beards = {}
    for beard, name in BEARD_NAMES.items():
        b3 = entry('high-rl', f'{sex}/B3/{name}/50')
        b1 = entry('medium', f'{sex}/B1/{beard}/50')
        if b3 and b1:
            params = b3[1]
            for f in rl_sources('B3', name):
                rl['sources'][f] = sha256(res_path(f))
            beards[name] = {'model': 'rl', 'gain': rounded(params['gain']), 'hue': rounded(params['hue']),
                            'floor': rounded(params['floor']), 'targetFloor': rounded(b1[1]['floor']),
                            'residual': round(residual_of[('high-rl', f'{sex}/B3/{name}/50', 50, 50)], 6),
                            'sources': rl_sources('B3', name)}
    if beards:
        rl['beardLut'][sex] = beards
(out_dir / 'rl_hair_luts.json').write_text(json.dumps(rl, indent=1), encoding='utf-8')

# ------------------------------------------------------------ summary
report['low_shares_medium'] = low_shares
report['p2_shares_p1'] = p2_shares
(out_dir / 'fit_report.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
out = []
for path in ('P1', 'P2', 'P3', 'P4', 'B1', 'B2', 'P5', 'B3'):
    rows = [r for r in report['instances'] if r['path'] == path]
    if not rows:
        continue
    for quality in sorted(set(r['quality'] for r in rows)):
        sel = [r for r in rows if r['quality'] == quality]
        out.append('%s %-8s n=%3d  max residual linear %.5f  apparent sRGB %.4f  crosstalk %s  reach grey %s..%s  clipped %d' % (
            path, quality, len(sel), max(r['residual_linear'] for r in sel), max(r['residual_apparent_srgb'] for r in sel),
            '%.4f' % max(r['crosstalk'] for r in sel) if sel[0]['crosstalk'] is not None else '-',
            min(r['reach_srgb_grey'][1] for r in sel), max(r['reach_srgb_grey'][1] for r in sel),
            max(r['clipped'] for r in sel)))
for name, rows in comparisons.items():
    if rows:
        worst = max(rows, key=lambda r: r.get('error', r.get('max_mu_difference', 0)))
        out.append('%s: n=%d worst %s' % (name, len(rows), json.dumps(worst)))
out.append('low shares medium: %s; P2 shares P1: %s' % (low_shares, p2_shares))
out.append('hair_apparent.json: %d paths, %d sources; RL: %s' % (len(paths), len(sources),
           {k: list(v) for k, v in rl.items() if k != 'sources'}))
(out_dir / 'fit_summary.txt').write_text('\n'.join(out) + '\n', encoding='utf-8')
print('\n'.join(out))
