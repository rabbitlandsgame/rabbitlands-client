"""Task 1: inventory of the 64 head-slot pieces, classified by geometry.

For every piece (the canonical_human_<sex> variant, placed as the runtime
places it at rest) rays are cast from the RL cranium centre:
  * dome   - share of rays in a 35 deg cone round +Y that meet the piece
  * ring   - per elevation (-40..+60 deg), the share of azimuths that meet it
  * sides  - share of rays toward either ear (azimuth +-30 deg, elevation
             -25..+5 deg from an ear-height origin) that meet it
  * nape   - share of rays toward the back of the neck that meet it
  * face   - share of rays toward the eyes/nose that meet it in front of the face
  * below  - how far the piece reaches below the ear bottoms (trails, mantles)
Writes inventory.json and prints a table.
"""
import json
import sys

import numpy as np
import trimesh

import hwlib as h


def ray_hits(mesh, origin, dirs, max_dist=0.30):
    origins = np.repeat(origin[None], len(dirs), 0)
    loc, ray, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    first = np.full(len(dirs), np.inf)
    last = np.full(len(dirs), -np.inf)
    if len(ray):
        d = np.linalg.norm(loc - origins[ray], axis=1)
        ok = d < max_dist
        np.minimum.at(first, ray[ok], d[ok])
        np.maximum.at(last, ray[ok], d[ok])
    return first, last


def sph(az, el):
    """az 0 = +Z (face), 90 = +X (character left); el up from horizontal."""
    az, el = np.radians(az), np.radians(el)
    return np.stack([np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)], -1)


def cranium_centre(sex):
    f = h.head_frame(sex)
    head = h.rl_head(sex)
    y = f['eye'][1] + 0.035
    P = head['P']
    band = P[np.abs(P[:, 1] - y) < 0.004]
    mid = band[np.abs(band[:, 0]) < 0.01]
    z = (mid[:, 2].max() + mid[:, 2].min()) / 2
    return np.array([0.0, y, z]), f


def fib_dirs(n=4000):
    k = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * k / n)
    th = np.pi * (1 + 5 ** 0.5) * k
    return np.stack([np.sin(phi) * np.sin(th), np.cos(phi), np.sin(phi) * np.cos(th)], -1)


DIRS = fib_dirs()


def coverage(samples, origin, mask_dirs, max_dist, tol_deg=5.0):
    """Share of the directions in `mask_dirs` with a surface sample within tol."""
    from scipy.spatial import cKDTree
    v = samples - origin
    r = np.linalg.norm(v, axis=1)
    keep = (r < max_dist) & (r > 1e-6)
    if not keep.any():
        return 0.0
    u = v[keep] / r[keep, None]
    d, _ = cKDTree(u).query(mask_dirs)
    return float((d < 2 * np.sin(np.radians(tol_deg) / 2)).mean())


def measure(visual, sex):
    pc = h.piece(visual, sex)
    mesh = trimesh.Trimesh(pc['P'], pc['I'], process=False)
    samples = trimesh.sample.sample_surface(mesh, 60000, seed=1)[0]
    c, f = cranium_centre(sex)
    out = dict(visual=visual, sex=sex, name=pc['name'], scene=pc['scene'].split('/')[-1],
               coversHair=pc['coversHair'], verts=len(pc['P']))
    el = np.degrees(np.arcsin(DIRS[:, 1]))
    az = np.degrees(np.arctan2(DIRS[:, 0], DIRS[:, 2])) % 360
    out['dome'] = coverage(samples, c, DIRS[el > 55], 0.25)
    rings = {}
    for e in range(-40, 61, 5):
        rings[e] = coverage(samples, c, DIRS[np.abs(el - e) < 2.5], 0.25, 4.0)
    out['ring'] = rings
    ear = c.copy()
    ear[1] = f['eye'][1] - 0.01
    side = ((np.abs(az - 90) < 30) | (np.abs(az - 270) < 30)) & (el > -25) & (el < 5)
    out['sides'] = coverage(samples, ear, DIRS[side], 0.16)
    neck = c.copy()
    neck[1] = f['menton'][1] + 0.01
    nape = (np.abs(az - 180) < 30) & (np.abs(el) < 20)
    out['nape'] = coverage(samples, neck, DIRS[nape], 0.18)
    face = ((az < 30) | (az > 330)) & (el > -30) & (el < 10)
    out['face'] = coverage(samples, f['eye'], DIRS[face], 0.15)
    P = pc['P']
    out['top_above_eye'] = float(P[:, 1].max() - f['eye'][1])
    out['low_below_eye'] = float(f['eye'][1] - P[:, 1].min())
    out['width'] = float(np.ptp(P[:, 0]))
    out['depth'] = float(np.ptp(P[:, 2]))
    out['below_ear_share'] = float((P[:, 1] < f['eye'][1] - 0.045).mean())
    labels = h.weld_components(P, pc['I'])
    out['components'] = int(labels.max() + 1)
    return out


def classify(r):
    ring_max = max(r['ring'].values())
    band = [e for e, v in r['ring'].items() if v >= 0.9]
    if r['dome'] >= 0.6 and r['sides'] >= 0.45:
        return 'closed'
    if r['dome'] >= 0.6:
        return 'open-hat'          # crown over the head, band above the ears
    if ring_max >= 0.85:
        return 'open-ring'         # circlet / band / crown
    return 'open-other'


def main():
    ids = h.head_ids()
    if len(sys.argv) > 1:
        ids = [int(v) for v in sys.argv[1].split(',')]
    pol = h.policy()
    rows = []
    for v in ids:
        for sex in ('female', 'male'):
            r = measure(v, sex)
            r['kind'] = pol.get('3:%d' % v, {}).get('kind', '')
            r['ears'] = pol.get('3:%d' % v, {}).get('ears', '')
            r['class'] = classify(r)
            rows.append(r)
            band = [e for e, val in r['ring'].items() if val >= 0.9]
            print('%3d %-6s %-20s %-30s %-7s cov=%d dome=%.2f sides=%.2f nape=%.2f face=%.2f ring>=.9:%s top=%.3f low=%.3f below=%.2f comp=%d -> %s'
                  % (v, sex, r['name'], r['scene'], r['kind'], r['coversHair'], r['dome'], r['sides'], r['nape'],
                     r['face'], (min(band), max(band)) if band else '-', r['top_above_eye'], r['low_below_eye'],
                     r['below_ear_share'], r['components'], r['class']), flush=True)
    json.dump(rows, open(h.OUT + '/inventory.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
