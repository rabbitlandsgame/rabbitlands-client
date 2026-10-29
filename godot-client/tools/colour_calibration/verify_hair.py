"""Accuracy tables (R10, R11, R13) from hair_apparent_calibration verify runs.

usage: python verify_hair.py <out-dir> <verify.json> [<verify.json> ...]
Reads data/actors/hair_apparent.json and the RL LUTs in rl_head_wire_defaults.json.
"""
import json, sys
from pathlib import Path
import numpy as np
from calib_lib import CLIENT, SKIN_GAIN, D_MAX, enc, lin, oklab, predict, load, fit

out_dir = Path(sys.argv[1])
runs = [load(f) for f in sys.argv[2:]]
tables = load(CLIENT / 'data/actors/hair_apparent.json')
rl_data = load(CLIENT / 'data/actors/rl_head_wire_defaults.json')['colours']
TARGET = {'P1': 0.005, 'P2': 0.005, 'P3': 0.005, 'B1': 0.005, 'B2': 0.005, 'P4': 0.015, 'P5': 0.03, 'B3': 0.03}
DARK_TARGET = 0.09


def entry_params(raw):
    if 'model' in raw:
        model = raw['model']
        return model, {k: np.array(raw[k]) for k in raw if k in ('gain', 'floor', 'matte', 'light', 'hue', 'targetFloor')}
    return 'linear', {'gain': np.array(raw['gain']), 'floor': np.array(raw['floor'])}


def lerp(a, b, u):
    return {k: a[k] * (1 - u) + b[k] * u for k in a if k in b}


def table(sex, path, style, s):
    paths = tables['paths']
    key = f'{sex}/{path}/{style}/{s}'
    if key in paths:
        return entry_params(paths[key])
    measured = sorted(int(k.split('/')[3]) for k in paths if k.startswith(f'{sex}/{path}/{style}/'))
    low = max([m for m in measured if m <= s] or [measured[0]])
    high = min([m for m in measured if m >= s] or [measured[-1]])
    ma, pa = entry_params(paths[f'{sex}/{path}/{style}/{low}'])
    if high == low:
        return ma, pa
    mb, pb = entry_params(paths[f'{sex}/{path}/{style}/{high}'])
    return ma, lerp(pa, pb, (s - low) / (high - low))


def rl_entry(sex, path, name, level):
    if path == 'B3':
        return entry_params(rl_data['beardLut'][sex][name])
    module = rl_data['hairLut'][sex][name]
    levels = sorted(int(k) for k in module['levels'])
    low = max([l for l in levels if l <= level] or [levels[0]])
    high = min([l for l in levels if l >= level] or [levels[-1]])
    ma, pa = entry_params(module['levels'][str(low)])
    if high != low:
        _, pb = entry_params(module['levels'][str(high)])
        pa = lerp(pa, pb, (level - low) / (high - low))
    pa['targetFloor'] = np.array(module['targetFloor'])
    return ma, pa


MODULE = {'male': 'rowan_shag', 'female': 'mira_bun'}
REFERENCE_STYLE = {'male': 1, 'female': 3}


def reference_reach(sex, A):
    """The uniform scale R applies to apparent colour A (beards draw A times it)."""
    model, params = table(sex, 'P1', REFERENCE_STYLE[sex], 50)
    dye = SKIN_GAIN[sex] * A / params['gain']
    peak = float(dye.max())
    return min(1.0, D_MAX / peak) if peak > 0 else 1.0


rows = []
for run in runs:
    renderer = run.get('renderer')
    for inst in run['instances']:
        sex, path = inst['sex'], inst['path']
        g = SKIN_GAIN[sex]
        if path in ('P5', 'B3'):
            name = MODULE[sex] if path == 'P5' else inst['key'].split('/')[2]
        # A reshaped hairstyle (length or volume off 50) has its own black: the
        # intercept of its response, fitted to this instance's own samples.
        shape_floor = None
        if (inst.get('length', 50), inst.get('volume', 50)) != (50, 50) and inst['samples']:
            model_kind = 'pigment' if path == 'P4' else 'linear'
            shape_floor = fit(model_kind, np.array([s['dye'] for s in inst['samples']]),
                              np.array([s['mu'] for s in inst['samples']]))['floor']
        for sample in inst['samples']:
            A = np.array(sample['apparent'])
            mu = np.array(sample['mu'])
            if path in ('P5', 'B3'):
                model, params = rl_entry(sex, path, name, int(sample.get('level', inst.get('level', 50))))
                floor = params['targetFloor']
                ceiling = predict(model, params, np.array([[1.0] * 3]))[0]
                reach = 1.0
                for c in range(3):
                    if floor[c] + g[c] * A[c] > ceiling[c] and A[c] > 0:
                        reach = min(reach, max(ceiling[c] - floor[c], 0) / (g[c] * A[c]))
            else:
                model, params = table(sex, path, inst['style'], inst['s'])
                floor = params['floor'] if shape_floor is None else shape_floor
                reach = float(sample['reach'])
            if path in ('B1', 'B2', 'B3'):
                # Beards show the colour the hair shows: A scaled by R's reach
                # (inside every beard path's own, larger reach).
                reach = reference_reach(sex, A)
            target = A * reach
            shown = np.maximum((mu - floor) / g, 0)
            error = float(np.abs(enc(shown) - enc(target)).max())
            dye = np.array(sample['dye'])
            gamut = not bool(np.any((dye <= 1e-4) & (enc(shown) - enc(target) > 0.002)))
            light = float(oklab(target)[0, 0])
            limit = TARGET[path] if not (path in ('P5', 'B3') and light < 0.15) else DARK_TARGET
            rows.append({'renderer': renderer, 'sex': sex, 'path': path, 'quality': inst['quality'], 'style': inst['style'],
                         's': inst['s'], 'length': inst.get('length', 50), 'volume': inst.get('volume', 50),
                         'wire': sample['wire'], 'reach': float(reach), 'in_reach': bool(reach >= 0.999 and gamut),
                         'in_gamut': gamut, 'error': error,
                         'limit': limit, 'pass': bool(error <= limit), 'shown': enc(shown).tolist(), 'target': enc(target).tolist(),
                         'L': light})

# ---------------------------------------------------------------- R10 table
summary = []
def group_key(r):
    shape = 'shape' if (r['length'], r['volume']) != (50, 50) else ''
    return (r['renderer'], r['path'], r['quality'], shape)
groups = {}
for r in rows:
    groups.setdefault(group_key(r), []).append(r)
table_rows = []
for key in sorted(groups):
    sel = groups[key]
    inr = [r for r in sel if r['in_reach']]
    worst = max((r['error'] for r in inr), default=float('nan'))
    p95 = float(np.percentile([r['error'] for r in inr], 95)) if inr else float('nan')
    fails = sum(1 for r in inr if not r['pass'])
    table_rows.append({'renderer': key[0], 'path': key[1], 'quality': key[2], 'shape': key[3], 'samples': len(sel),
                       'in_reach': len(inr), 'max_error': worst, 'p95_error': p95, 'limit': TARGET[key[1]], 'fails': fails})
    summary.append('%-14s %-3s %-8s %-5s n=%4d in-reach %4d  max %.4f  p95 %.4f  limit %.3f  over %d' % (
        key[0], key[1], key[2], key[3], len(sel), len(inr), worst, p95, TARGET[key[1]], fails))

# ---------------------------------------------------------------- R11 spread
spread = []
for renderer in sorted(set(r['renderer'] for r in rows)):
    for sex in ('female', 'male'):
        by_wire = {}
        for r in rows:
            if r['renderer'] == renderer and r['sex'] == sex and r['quality'] != 'low' and r['path'] not in ('B1', 'B2', 'B3') \
                    and (r['length'], r['volume']) == (50, 50):
                by_wire.setdefault(tuple(r['wire']), []).append(r)
        for wire, sel in by_wire.items():
            if not all(r['in_reach'] for r in sel):
                continue
            shown = np.array([r['shown'] for r in sel])
            styles = float((shown.max(axis=0) - shown.min(axis=0)).max())
            spread.append({'renderer': renderer, 'sex': sex, 'wire': list(wire), 'paths': len(sel), 'spread': styles})
if spread:
    worst = max(spread, key=lambda r: r['spread'])
    summary.append('R11 cross-style/quality spread (in reach, Medium P1/P3, High P4, RL P5): %d colours, max %.4f (limit 0.02), '
                   'worst %s' % (len(spread), worst['spread'], json.dumps(worst)))
# R16: the RL module's mean tone across its finish positions (one colour, every
# level drawn through the game's own path) stays within 0.01 of each other.
r16 = []
for renderer in sorted(set(r['renderer'] for r in rows)):
    for sex in ('female', 'male'):
        by_wire = {}
        for r in rows:
            if r['renderer'] == renderer and r['sex'] == sex and r['path'] == 'P5' and r['in_reach']:
                by_wire.setdefault(tuple(r['wire']), []).append(r)
        for wire, sel in by_wire.items():
            if len(sel) > 1:
                shown = np.array([r['shown'] for r in sel])
                r16.append({'renderer': renderer, 'sex': sex, 'wire': list(wire), 'levels': len(sel),
                            'spread': float((shown.max(axis=0) - shown.min(axis=0)).max())})
if r16:
    worst = max(r16, key=lambda r: r['spread'])
    summary.append('R16 RL module tone across finish levels (in reach): %d colours, max %.4f (limit 0.01), worst %s' % (
        len(r16), worst['spread'], json.dumps(worst)))
# Low against Medium (same style and s), for the report.
low = []
index = {(r['renderer'], r['sex'], r['path'], r['quality'], r['style'], r['s'], tuple(r['wire'])): r for r in rows}
for r in rows:
    if r['quality'] == 'low':
        m = index.get((r['renderer'], r['sex'], r['path'], 'medium', r['style'], r['s'], tuple(r['wire'])))
        if m:
            low.append(float(np.abs(np.array(r['shown']) - np.array(m['shown'])).max()))
if low:
    summary.append('Low vs Medium (same apparent colour, P1/B1): max %.4f, median %.4f (Low actors cast no shadows)' % (
        max(low), float(np.median(low))))

# ---------------------------------------------------------------- R11 palette snap
snap = []
frozen_gain = {'female': np.array([0.3656, 0.3613, 0.3666]), 'male': np.array([0.2961, 0.2935, 0.2998])}
src = (CLIENT / 'src/actors/appearance_variants.gd').read_text(encoding='utf-8')
import re
block = src[src.index('static func hair_color('):]
block = block[block.index('= ['):block.index('return colors')]
colours = [tuple(float(x) for x in m) for m in re.findall(r'Color\(([\d.]+),\s*([\d.]+),\s*([\d.]+)\)', block)]
for sex in ('female', 'male'):
    g = SKIN_GAIN[sex]
    for key, raw in tables['paths'].items():
        if not key.startswith(sex + '/') or raw.get('shares') or key.split('/')[1] not in ('P1', 'P3', 'P4'):
            continue
        model, params = entry_params(raw)
        for i, c in enumerate(colours):
            d = lin(np.array(c))
            A_ref = frozen_gain[sex] * d / g
            shown = (predict(model, params, d[None, :])[0] - params['floor']) / g
            snap.append({'key': key, 'index': i, 'difference': float(np.abs(enc(shown) - enc(A_ref)).max())})
if snap:
    worst = max(snap, key=lambda r: r['difference'])
    summary.append('R11 palette pick vs custom value on every path (palette colours, %d cases): max %.4f, median %.4f; worst %s' % (
        len(snap), worst['difference'], float(np.median([r['difference'] for r in snap])), json.dumps(worst)))

# ---------------------------------------------------------------- R13 glow
skin_floor = {'female': np.array([0.0184, 0.0167, 0.0175]), 'male': np.array([0.0148, 0.0145, 0.0145])}
glow = []
for sex in ('female', 'male'):
    g = SKIN_GAIN[sex]
    skin240 = g * lin(np.array([240 / 255.0] * 3)) + skin_floor[sex]
    rm, rp = table(sex, 'P1', {'male': 1, 'female': 3}[sex], 50)
    ceiling = (predict(rm, rp, np.array([[D_MAX] * 3]))[0] - rp['floor']) / g
    for key, raw in tables['paths'].items():
        if key.startswith(sex + '/') and not raw.get('shares'):
            model, params = entry_params(raw)
            if key.split('/')[1] in ('B1', 'B2'):
                top = params['floor'] + g * ceiling
                key = key + ' (at R reach)'
            else:
                top = predict(model, params, np.array([[D_MAX] * 3]))[0]
            glow.append({'key': key, 'ratio': float((top / skin240).max())})
    for module, data in rl_data['hairLut'].get(sex, {}).items():
        for level, raw in data['levels'].items():
            model, params = entry_params(raw)
            top = predict(model, params, np.array([[1.0] * 3]))[0]
            glow.append({'key': f'{sex}/P5/{module}/{level}', 'ratio': float((top / skin240).max())})
    # Beards draw the colour the hair shows (reach-scaled on R): the brightest
    # beard target is R's grey ceiling, drawn on each beard path.
    rm, rp = table(sex, 'P1', {'male': 1, 'female': 3}[sex], 50)
    ceiling = (predict(rm, rp, np.array([[D_MAX] * 3]))[0] - rp['floor']) / g
    for name, raw in rl_data['beardLut'].get(sex, {}).items():
        model, params = entry_params(raw)
        target = params['targetFloor'] + g * ceiling
        glow.append({'key': f'{sex}/B3/{name} (at R reach)', 'ratio': float((target / skin240).max())})
worst = max(glow, key=lambda r: r['ratio'])
over = [r for r in glow if r['ratio'] > 1.0]
summary.append('R13 glow: brightest hair mean at the dye limit / skin swatch 240 lit mean: max %.3f (%s); %d paths over 1' % (
    worst['ratio'], worst['key'], len(over)))

out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / 'verify_hair.json').write_text(json.dumps({'table': table_rows, 'spread': spread, 'snap': snap, 'glow': glow,
                                                       'rows': rows}, indent=1), encoding='utf-8')
(out_dir / 'verify_hair.txt').write_text('\n'.join(summary) + '\n', encoding='utf-8')
print('\n'.join(summary))
