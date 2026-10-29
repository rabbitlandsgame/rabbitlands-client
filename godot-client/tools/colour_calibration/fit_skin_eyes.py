"""Fit skinTone knots and eyeLut from rl_head_colour_calibration --part=skin / --part=eyes runs.

usage: python fit_skin_eyes.py <skin.json> <eyes.json> <out-dir>
Writes <out-dir>/rl_skin_eye_luts.json and prints a summary.
"""
import json, sys
from pathlib import Path
import numpy as np
from calib_lib import enc, rounded, load, sha256, res_path

skin_run, eye_run, out_dir = load(sys.argv[1]), load(sys.argv[2]), Path(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)
UNDERTONES = [-1.0, -0.5, 0.0, 0.5, 1.0]
NODES = 7
result = {'skinTone': {'undertones': UNDERTONES}, 'eyeLut': {'nodes': NODES, 'spacing': 'linear'}, 'report': {}}
summary = []

# ------------------------------------------------------------------ skin
positions = None
for sex in ('female', 'male'):
    rows = skin_run[sex + '_skin']
    stops = {s['position']: s for s in skin_run[sex + '_skin_stops']}
    pos = sorted(set(r['position'] for r in rows))
    positions = positions or pos
    assert pos == positions
    by = {(r['position'], r['undertone']): r for r in rows}
    gains = []
    worst = {'t0': 0.0, 'other': 0.0}
    for p in pos:
        for t in UNDERTONES:
            r = by[(p, t)]
            if t == 0.0 and p in stops:
                gain = np.array(stops[p]['table']) / np.maximum(np.array(stops[p]['stop']), 1e-6)
            else:
                gain = np.array(r['rl']) / np.maximum(np.array(r['final']), 1e-6)
            gains.append(rounded(gain, 5))
            err = max(abs(float(enc(a)) - float(enc(b))) for a, b in zip(r['target'], r['measured']))
            key = 't0' if t == 0.0 else 'other'
            worst[key] = max(worst[key], err)
    result['skinTone'][sex] = gains
    result['report'][sex + '_skin_knot_residual'] = worst
    summary.append('skin %s: %d knots; knot residual (sRGB, max channel) t=0 %.4f, other %.4f' % (
        sex, len(gains), worst['t0'], worst['other']))
result['skinTone']['positions'] = positions

# ------------------------------------------------------------------ eyes
for sex in ('female', 'male'):
    med = eye_run[sex + '_eyes_medium']
    rl = eye_run[sex + '_eyes_rl']
    P = np.array([r['pigment'] for r in med]); Ym = np.array([r['mu'] for r in med])
    E = np.array([r['eye'] for r in rl]); Yr = np.array([r['mu'] for r in rl])
    Am = np.c_[P, np.ones(len(P))]; Ar = np.c_[E, np.ones(len(E))]
    Cm = np.linalg.lstsq(Am, Ym, rcond=None)[0]  # 4x3
    Cr = np.linalg.lstsq(Ar, Yr, rcond=None)[0]
    res_m = float(np.abs(Am @ Cm - Ym).max()); res_r = float(np.abs(Ar @ Cr - Yr).max())
    Mm, fm = Cm[:3].T, Cm[3]
    Mr, fr = Cr[:3].T, Cr[3]
    inv = np.linalg.inv(Mr)

    def lut_value(p):
        return np.clip(inv @ (Mm @ p + fm - fr), 0.0, 1.0)

    grid = np.linspace(0, 1, NODES)
    table = []
    for r_ in grid:
        for g_ in grid:
            for b_ in grid:
                table.append(rounded(lut_value(np.array([r_, g_, b_])), 5))
    T = np.array(table).reshape(NODES, NODES, NODES, 3)

    def trilinear(p):
        at = np.clip(p, 0, 1) * (NODES - 1)
        base = np.minimum(at.astype(int), NODES - 2)
        f = at - base
        out = np.zeros(3)
        for corner in range(8):
            o = np.array([(corner >> 2) & 1, (corner >> 1) & 1, corner & 1])
            w = np.prod(np.where(o == 1, f, 1 - f))
            n = base + o
            out += w * T[n[0], n[1], n[2]]
        return out

    palette = eye_run[sex + '_eyes_palette']
    residuals = []
    palette_report = []
    for row in palette:
        p = np.array(row['pigment']); table_lin = np.array(row['table'])
        lut = trilinear(p)
        residuals.append(rounded(table_lin - lut, 5))
        # what the affine composition predicts against what the table measured
        palette_report.append({'index': row['index'],
                               'lut_vs_table_srgb': float(np.abs(enc(lut) - enc(table_lin)).max()),
                               'table_rl_vs_medium_srgb': float(np.abs(enc(np.array(row['rl'])) - enc(np.array(row['medium']))).max())})
    result['eyeLut'][sex] = {'table': table, 'residuals': residuals}
    result['report'][sex + '_eyes'] = {'medium_affine_residual': res_m, 'rl_affine_residual': res_r,
                                       'medium_matrix': rounded(Mm, 5), 'rl_matrix': rounded(Mr, 5),
                                       'palette': palette_report}
    summary.append('eyes %s: affine residual Medium %.5f RL %.5f (linear); LUT vs palette table worst %.4f sRGB; '
                   'palette table RL vs Medium worst %.4f' % (sex, res_m, res_r,
                   max(r['lut_vs_table_srgb'] for r in palette_report), max(r['table_rl_vs_medium_srgb'] for r in palette_report)))

result['sources'] = {f: sha256(res_path(f)) for f in [
    'res://src/actors/rl_head/rl_skin.gdshader', 'res://src/actors/rl_head/rl_eye.gdshader',
    'res://src/actors/face_appearance.gdshader', 'res://assets/actors/native/rl_head_textures/eye.png',
    'res://assets/actors/native/rl_head_textures/head_female_albedo.png',
    'res://assets/actors/native/rl_head_textures/head_male_albedo.png',
    'res://assets/actors/native/rl_heads/rl_head_female.glb', 'res://assets/actors/native/rl_heads/rl_head_male.glb']}
(out_dir / 'rl_skin_eye_luts.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
(out_dir / 'skin_eye_summary.txt').write_text('\n'.join(summary) + '\n', encoding='utf-8')
print('\n'.join(summary))
