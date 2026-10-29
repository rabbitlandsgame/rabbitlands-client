"""Independent sanity check of the generated synthetic cases (reads the GLBs with trimesh, not our writer).

    python RL/scripts/fit/synth/verify_cases.py [--cases all|c00,...]

For each case: loads reference.glb with trimesh (all meshes, node transforms applied), maps it to game space
with the ground-truth transform, and measures the distance from the GT-morphed RL skin (front face region,
lips/eyes/ears excluded, visible per truth) to it. Also checks the base-colour source (texture size / COLOR_0),
up axis and closedness. Prints one line per case; exit 1 if any face median distance > 1 mm.
"""
import os, sys, json, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import synthlib as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', default='all')
    ap.add_argument('--cases-dir', default=S.CASES_DIR)
    a = ap.parse_args()
    import trimesh
    ids = sorted(d for d in os.listdir(a.cases_dir) if os.path.exists(os.path.join(a.cases_dir, d, 'truth.json')))
    if a.cases != 'all':
        ids = [d for d in ids if any(d.startswith(w) for w in a.cases.split(','))]
    heads = {}
    bad = 0
    for cid in ids:
        cd = os.path.join(a.cases_dir, cid)
        gt = json.load(open(os.path.join(cd, 'truth.json'), encoding='utf-8'))
        sc = trimesh.load(os.path.join(cd, 'reference.glb'), process=False)
        geoms = list(sc.geometry.values()) if isinstance(sc, trimesh.Scene) else [sc]
        m = sc.to_geometry() if isinstance(sc, trimesh.Scene) else sc
        tr = gt['transform']
        V = tr['scale'] * np.asarray(m.vertices) @ np.asarray(tr['R']).T + np.asarray(tr['t'])
        mg = trimesh.Trimesh(V, m.faces, process=True)
        sex = gt['sex']
        if sex not in heads:
            heads[sex] = S.load_head(sex)
        h = heads[sex]
        D = np.zeros_like(h.P)
        for n, v in gt['controls'].items():
            if v > 0:
                D += v * h.deltas[f'id_{n}_p']
            elif v < 0:
                D += -v * h.deltas[f'id_{n}_n']
        P = h.P + D
        lon, lat = S.dir_lonlat(P - h.C)
        sel = (np.abs(lon) < 55) & (lat > -60) & (lat < 25) & ~h.vgroups['lips'] & ~h.vgroups['ears'] & (h.N[:, 2] > 0.3)
        eyes = np.min([np.linalg.norm(P - c, axis=1) for c in (h.eyes[h.eyes[:, 0] > 0].mean(0), h.eyes[h.eyes[:, 0] < 0].mean(0))], 0)
        sel &= eyes > 0.022
        # interior MPFB surfaces (mouth bag, sockets): radius clearly below the outermost radial skin hit
        rout, _ = S.radial_cast(P, h.T, h.C, P - h.C, 'outer')
        sel &= np.linalg.norm(P - h.C, axis=1) > rout - 0.002
        # skip vertices hidden by a beard (truth occlusion is per control; use the beard flag)
        if gt['beard']['present']:
            sel &= P[:, 1] > float(np.max(P[h.vgroups['lips'], 1])) + 0.004
        idx = np.nonzero(sel)[0]
        cen = V[m.faces].mean(1)
        lo = P[idx].min(0) - 0.01; hi = P[idx].max(0) + 0.01
        keep = np.all((cen > lo) & (cen < hi), 1)
        sub = trimesh.Trimesh(V, m.faces[keep], process=False)
        _, d, _ = trimesh.proximity.closest_point(sub, P[idx])
        tex = None
        mat = getattr(geoms[0].visual, 'material', None)
        if mat is not None and getattr(mat, 'baseColorTexture', None) is not None:
            tex = mat.baseColorTexture.size
        has_vc = geoms[0].visual.kind == 'vertex' if hasattr(geoms[0].visual, 'kind') else False
        up_ref = np.asarray(tr['R']).T @ [0, 1, 0]
        line = (f"{cid:26s} meshes={len(geoms)} tris={len(m.faces):8d} watertight={mg.is_watertight!s:5s} "
                f"face dist median={np.median(d) * 1000:.2f} p95={np.percentile(d, 95) * 1000:.2f} mm (n={len(idx)}) "
                f"tex={tex} vcolor={has_vc} up_in_file={np.round(up_ref, 2).tolist()} scale={tr['scale']}")
        print(line)
        if np.median(d) > 0.001:
            bad += 1
    print('OK' if not bad else f'{bad} case(s) with face median distance > 1 mm')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
