"""Structural validation of RL hair / beard GLBs (no Blender needed).

    python validate.py <asset.glb> [...]

Checks: GLB container and buffer sizes; every accessor's view bounds; sparse
accessors (sorted, in range); per primitive attribute counts, index range,
normalised weights, joint ids < skin joints; all primitives of a mesh carry the
same number of morph targets and extras.targetNames matches; skin: one inverse
bind per joint and node-global x inverse-bind == identity at rest (vertices then
coincide with body model space); hair: hair_root rest global == body Head rest
global, spring bones exist and chain parent->child, UV v in [0, 1].
Hair modules also get the scalp coverage check (coverage.py): at hair_detail 0
(only core A = 1 geometry drawn), no scalp sample inside the hairline may be seen
through the hair from any view direction at rest or under hl_volume_n /
hl_length_n (alone and together), on every LOD; the identity extremes and random
identity mixes are measured too and reported as warnings ('coverage' in the
summary). --no-coverage skips it.
Prints a JSON summary per file; exit code 1 if anything fails.
"""
import os, sys, json, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rlglb  # noqa: E402

SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}


def validate(path):
    errs, info = [], {}
    data = open(path, 'rb').read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    if magic != 0x46546C67 or ver != 2 or length != len(data):
        errs.append('bad GLB header')
    g, b = rlglb.read(path)
    if g['buffers'][0]['byteLength'] > len(b):
        errs.append('buffer shorter than declared')
    for i, v in enumerate(g['bufferViews']):
        if v.get('byteOffset', 0) + v['byteLength'] > len(b):
            errs.append(f'bufferView {i} out of range')
    for i, a in enumerate(g['accessors']):
        n = rlglb.NCOMP[a['type']] * SIZE[a['componentType']]
        if 'bufferView' in a:
            v = g['bufferViews'][a['bufferView']]
            if a.get('byteOffset', 0) + a['count'] * n > v['byteLength']:
                errs.append(f'accessor {i} exceeds its view')
        sp = a.get('sparse')
        if sp:
            idx = rlglb.accessor(g, b, i, normalize=False)  # touches the data
            iv = g['bufferViews'][sp['indices']['bufferView']]
            ii = np.frombuffer(b, dtype=rlglb.COMPONENT[sp['indices']['componentType']], count=sp['count'],
                               offset=iv.get('byteOffset', 0) + sp['indices'].get('byteOffset', 0))
            if (np.diff(ii.astype(np.int64)) <= 0).any() or ii.max() >= a['count']:
                errs.append(f'sparse accessor {i} indices unsorted / out of range')
    # skin
    G = rlglb.globals_of(g)
    skins = g.get('skins', [])
    if len(skins) != 1:
        errs.append('expected exactly one skin')
    sk = skins[0]
    ibm = rlglb.accessor(g, b, sk['inverseBindMatrices'])
    if len(ibm) != len(sk['joints']):
        errs.append('inverse bind count != joints')
    worst = 0.0
    for j, m in zip(sk['joints'], ibm):
        M = np.asarray(m).reshape(4, 4).T          # glTF column-major -> numpy
        worst = max(worst, float(np.abs(G[j] @ M - np.eye(4)).max()))
    info['restSkinError'] = worst
    if worst > 1e-4:
        errs.append(f'global x inverse-bind != identity (max err {worst:.2e})')
    names = {i: n.get('name') for i, n in enumerate(g['nodes'])}
    info['joints'] = len(sk['joints'])
    # meshes
    info['meshes'] = {}
    for mi, m in enumerate(g['meshes']):
        tn = m.get('extras', {}).get('targetNames', [])
        ntargets = {len(p.get('targets', [])) for p in m['primitives']}
        if len(ntargets) != 1 or (tn and ntargets != {len(tn)}):
            errs.append(f'mesh {m["name"]}: inconsistent morph target counts {ntargets} vs names {len(tn)}')
        tris = 0; nonempty = set()
        for pi, p in enumerate(m['primitives']):
            a = p['attributes']
            counts = {k: g['accessors'][v]['count'] for k, v in a.items()}
            if len(set(counts.values())) != 1:
                errs.append(f'{m["name"]}[{pi}] attribute counts differ {counts}')
            nv = counts['POSITION']
            I = rlglb.accessor(g, b, p['indices'], normalize=False).astype(np.int64).ravel()
            if I.max() >= nv or len(I) % 3:
                errs.append(f'{m["name"]}[{pi}] bad indices')
            tris += len(I) // 3
            W = rlglb.accessor(g, b, a['WEIGHTS_0'])
            J = rlglb.accessor(g, b, a['JOINTS_0'], normalize=False)
            if np.abs(W.sum(1) - 1).max() > 1e-3:
                errs.append(f'{m["name"]}[{pi}] weights do not sum to 1')
            if J[W > 0].max() >= len(sk['joints']):
                errs.append(f'{m["name"]}[{pi}] joint index out of range')
            UV = rlglb.accessor(g, b, a['TEXCOORD_0'])
            if UV[:, 1].min() < -1e-4 or UV[:, 1].max() > 1 + 1e-4:
                errs.append(f'{m["name"]}[{pi}] UV v outside [0, 1]')
            Nn = rlglb.accessor(g, b, a['NORMAL'])
            if np.abs(np.linalg.norm(Nn, axis=1) - 1).max() > 1e-3:
                errs.append(f'{m["name"]}[{pi}] non-unit normals')
            for k, t in enumerate(p.get('targets', [])):
                if 'sparse' in g['accessors'][t['POSITION']]:
                    nonempty.add(k)
        info['meshes'][m['name']] = {'tris': tris, 'targets': len(tn), 'nonEmptyTargets': len(nonempty)}
    ex = g.get('asset', {}).get('extras', {})
    if 'rlHair' in ex:
        rh = ex['rlHair']
        root = [i for i, n in names.items() if n == 'hair_root']
        if len(root) != 1:
            errs.append('hair_root missing')
        else:
            import paths
            bg, _ = rlglb.read(paths.body_glb(rh.get('sex', 'female')))
            bG = rlglb.globals_of(bg)
            HGb = bG[[i for i, nd in enumerate(bg['nodes']) if nd.get('name') == 'Head'][0]]
            e = float(np.abs(G[root[0]] - HGb).max())
            info['hairRootVsBodyHead'] = e
            if e > 1e-5:
                errs.append(f'hair_root rest global differs from body Head ({e:.2e})')
        children = {i: n.get('children', []) for i, n in enumerate(g['nodes'])}
        idx = {n: i for i, n in names.items()}
        for s in rh['springs']:
            bones = s['bones']
            for a_, b_ in zip(bones, bones[1:]):
                if a_ not in idx or b_ not in idx or idx[b_] not in children[idx[a_]]:
                    errs.append(f'spring chain broken {a_}->{b_}')
            if bones and idx.get(bones[0]) not in children[root[0]]:
                errs.append(f'spring {bones[0]} not parented to hair_root')
        info['springs'] = len(rh['springs']); info['collisions'] = [c['name'] for c in rh['collisions']]
    info['bytes'] = len(data)
    return errs, info


GATE_CASES = ('rest', 'hl_volume_n', 'hl_length_n', 'hl_volume_n+hl_length_n')


def coverage_check(path, info):
    """Scalp coverage of a hair module -> (errors, summary)."""
    import coverage
    g, _ = rlglb.read(path)
    rh = g['asset'].get('extras', {}).get('rlHair')
    if not rh:
        return [], None
    rep = coverage.check(path, rh.get('sex', 'male'))
    errs, warn = [], []
    for c in rep['cases']:
        if c['holeSamples']:
            msg = (f"lod{c['lod']} {c['case']}: {c['holeSamples']} scalp samples seen through the hair "
                   f"({c['holeRays']} rays) at {[(w['lon'], w['lat']) for w in c['where'][:3]]}")
            (errs if c['case'] in GATE_CASES else warn).append(msg)
    summary = {'samples': rep['samples'], 'directions': rep['directions'], 'level': rep['level'],
               'gateCases': list(GATE_CASES), 'holeSamplesMax': max(c['holeSamples'] for c in rep['cases']),
               'gateHoleSamplesMax': max([c['holeSamples'] for c in rep['cases'] if c['case'] in GATE_CASES] or [0]),
               'warnings': warn}
    return ['coverage: ' + m for m in errs], summary


if __name__ == '__main__':
    bad = False
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for p in args:
        e, i = validate(p)
        if '--no-coverage' not in sys.argv:
            ce, cs = coverage_check(p, i)
            e += ce
            if cs is not None:
                i['coverage'] = cs
        bad |= bool(e)
        print(json.dumps({'file': os.path.basename(p), 'ok': not e, 'errors': e, **i}))
    sys.exit(1 if bad else 0)
