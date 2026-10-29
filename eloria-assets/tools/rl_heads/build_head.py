"""Build an RL head module GLB from MPFB (hm08) data.

python build_head.py <spec.json> <out_dir>

The spec names the sex, the MPFB macro stack (exported by macro_stack.py),
likeness targets (MPFB targets and RL custom .target files), the identity
controls and the expression units. Output: <out_dir>/rl_head_<sex>.glb plus a
build report. Geometry is MPFB topology placed on the shipped Human rig:
  * cranium scaled/translated onto the shipped skull, then conformed inside it
    (headwear is fitted to that skull),
  * cut at the race-head neck plane (travel along neck_01->Head) and zipped to
    the open rim the body leaves when its head triangles are hidden,
  * skinned to spine_03/neck_01/Head (seam band follows the body rim weights),
  * identity (id_*) and expression (ex_*) morph targets on every surface.
"""
import json, os, sys, math, hashlib, numpy as np
import mh, place, gamebody, glbw

TRAVEL = 0.075          # body cut plane (same as the race-head lower plane)
GAP = 0.006             # axial height of the zipper strip above the body rim
FALL = 0.035            # seam deformation falloff up the neck
CONFORM_MARGIN = 0.0015 # cranium kept this far inside the shipped skull
JOINTS = ['spine_03', 'neck_01', 'Head']


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def tri_normals(P, T):
    n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    return n


def vertex_normals(P, T, weld=None):
    """Area-weighted normals; `weld` maps vertices to a shared position id so UV splits share normals."""
    fn = tri_normals(P, T)
    key = np.arange(len(P)) if weld is None else weld
    acc = np.zeros((key.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, key[T[:, k]], fn)
    acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
    return acc[key]


def loop_of(faces):
    """Ordered boundary loop(s) of a set of polygons (vertex ids)."""
    from collections import Counter, defaultdict
    ec = Counter(); directed = []
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            ec[(min(a, b), max(a, b))] += 1; directed.append((a, b))
    nxt = defaultdict(list)
    for a, b in directed:
        if ec[(min(a, b), max(a, b))] == 1:
            nxt[a].append(b)
    loops, seen = [], set()
    for s0 in list(nxt):
        if s0 in seen:
            continue
        L = [s0]; seen.add(s0); cur = s0
        while True:
            nb = [x for x in nxt[cur] if x not in seen]
            if not nb:
                break
            cur = nb[0]; L.append(cur); seen.add(cur)
        loops.append(L)
    return sorted(loops, key=len, reverse=True)


class Frame:
    """Cylindrical frame about the neck axis."""
    def __init__(self, o, d):
        self.o, self.d = o, d
        e1 = np.array([1.0, 0, 0]); e1 -= d * (e1 @ d); e1 /= np.linalg.norm(e1)
        e2 = np.cross(d, e1)
        if e2[2] < 0:
            e2 = -e2
        self.e1, self.e2 = e1, e2

    def cyl(self, P):
        r = P - self.o; h = r @ self.d; rr = r - np.outer(h, self.d)
        return h, np.linalg.norm(rr, axis=1), np.arctan2(rr @ self.e2, rr @ self.e1)

    def point(self, h, rad, th):
        return self.o + np.outer(h, self.d) + np.outer(rad * np.cos(th), self.e1) + np.outer(rad * np.sin(th), self.e2)


def periodic_interp(x, xp, fp):
    o = np.argsort(xp); xp, fp = xp[o], fp[o]
    xp2 = np.concatenate([xp - 2 * np.pi, xp, xp + 2 * np.pi]); fp2 = np.concatenate([fp, fp, fp], axis=0)
    if fp2.ndim == 1:
        return np.interp(x, xp2, fp2)
    return np.stack([np.interp(x, xp2, fp2[:, k]) for k in range(fp2.shape[1])], 1)


def stack_of(spec, key='likeness'):
    out = []
    for name, w in spec.get(key, {}).items():
        out.append((name, w))
    return out


def shape_delta(spec_targets, race):
    """Sum of MPFB target deltas (MakeHuman space) for a {target: weight} dict.
    Expression units are mixed over the macro ethnic weights like MPFB does."""
    d = np.zeros_like(mh.base().V)
    for name, w in spec_targets.items():
        if name.startswith('expression/units/'):
            unit = name.split('/')[-1]
            for eth, ew in race.items():
                if ew > 1e-4:
                    d += w * ew * mh.delta(f'expression/units/{eth}/{unit}')
        else:
            d += w * mh.delta(name)
    return d


def triangulate(faces, P):
    T = []
    for f in faces:
        if len(f) == 3:
            T.append(f)
        else:
            a, b, c, e = f
            if np.linalg.norm(P[a] - P[c]) <= np.linalg.norm(P[b] - P[e]):
                T += [[a, b, c], [a, c, e]]
            else:
                T += [[a, b, e], [b, c, e]]
    return np.array(T)


def build(spec, out_dir):
    sex = spec['sex']
    body = gamebody.Body(sex)
    macro = json.load(open(spec['macro']))
    race = macro['macro']['race']
    b = mh.base()
    V0 = mh.apply(macro['stack'] + stack_of(spec, 'likeness'))
    V0 = V0 + shape_delta(spec.get('likeness_units', {}), race)
    for p, w in spec.get('custom_targets', {}).items():
        V0 = V0 + w * mh.delta(p)
    s, t, shell, cmask = place.fit(V0, body)
    if 'scale_mul' in spec:
        s *= spec['scale_mul']
    toG = lambda X: s * 0.1 * X + t
    VG = toG(V0)
    report = {'scale': s, 'translation': t.tolist(), 'body': os.path.basename(body.path), 'bodySHA256': body.sha256}

    # ---------- head skin faces (MPFB 'body' group) above the seam band ----------
    o, d = body.plane(TRAVEL)
    fr = Frame(o, d)
    hidden, patch, loop = gamebody.clip_patch(body, TRAVEL)
    _, ui = np.unique(np.round(patch['P'][loop], 6), axis=0, return_index=True)
    rim = loop[np.sort(ui)]          # patch vertex ids on the plane, unique positions
    BP = patch['P']
    rh, rr, rth = fr.cyl(BP[rim])
    hcut = (VG - o) @ d
    body_faces = [i for i, g in enumerate(b.G) if g == 'body']
    rim_h_at = lambda th: periodic_interp(th, rth, rh)
    _, _, vth = fr.cyl(VG)
    floor = rim_h_at(vth) + GAP
    keep = [i for i in body_faces if all(hcut[v] > floor[v] for v in b.F[i])]
    faces = [b.F[i] for i in keep]
    # UV source table: MPFB body UVs, plus MPFB's frontal 'face_solid' unwrap for the face
    import gzip
    fs = json.load(gzip.open(os.path.join(mh.SYS, 'uv_layers', 'face_solid.json.gz'), 'rt'))
    UVTAB = [b.VT]; extra = []; base_n = len(b.VT); uvf = []; face_corner = set(); weld_fs = {}
    for i in keep:
        if str(i) in fs:
            ids = []
            for v, c in zip(b.F[i], fs[str(i)].values()):
                key = (v, round(c[0], 5), round(c[1], 5))
                if key not in weld_fs:
                    weld_fs[key] = base_n + len(extra); extra.append(c)
                ids.append(weld_fs[key])
            uvf.append(ids); face_corner.update(ids)
        else:
            uvf.append(b.FT[i])
    UVALL = np.concatenate([b.VT, np.array(extra)]) if extra else b.VT
    ring = np.array(loop_of(faces)[0])

    # ---------- seam: pull the MPFB ring onto the body rim (+GAP), fade upward ----------
    gh, gr, gth = fr.cyl(VG[ring])
    # Continue the body's own taper across the strip: a strip built as a vertical cylinder
    # forms a ledge between two tapering surfaces and renders as a dark ring. Slope dr/dh of
    # the body just below the rim, per direction, from the clipped patch's lower vertices.
    ph_, pr_, pth_ = fr.cyl(BP)
    below = ph_ < -0.002
    slope = np.zeros(len(rth))
    for k in range(len(rth)):
        dth = np.abs(np.angle(np.exp(1j * (pth_ - rth[k]))))
        m = below & (dth < 0.25)
        if m.sum() >= 2:
            # least-squares slope through the rim point
            dh = ph_[m] - rh[k]; dr = pr_[m] - rr[k]
            slope[k] = float((dh @ dr) / max(dh @ dh, 1e-12))
    slope = np.clip(slope, -1.2, 1.2)
    order = np.argsort(rth)
    sm = slope[order]
    sm = np.convolve(np.concatenate([sm[-2:], sm, sm[:2]]), np.ones(5) / 5, 'valid')
    slope[order] = sm
    tgt_r = periodic_interp(gth, rth, rr + slope * GAP)
    report['rimSlope'] = {'min': float(slope.min()), 'max': float(slope.max())}
    tgt_h = rim_h_at(gth) + GAP
    D_ring = fr.point(tgt_h, tgt_r, gth) - VG[ring]
    used = np.unique(np.concatenate([np.array(f) for f in faces]))
    uh, _, uth = fr.cyl(VG[used])
    ring_h = periodic_interp(uth, gth, gh)
    w_seam = np.zeros(len(VG))
    w_seam[used] = 1 - smoothstep((uh - ring_h) / FALL)
    D = np.zeros_like(VG)
    D[used] = w_seam[used, None] * periodic_interp(uth, gth, D_ring)
    VG = VG + D
    report['seam'] = {'ringVerts': int(len(ring)), 'rimVerts': int(len(rim)),
                      'maxRingMove': float(np.linalg.norm(D_ring, axis=1).max())}

    # ---------- cranium conform: nothing of the skull outside the shipped shell ----------
    crane = np.zeros(len(VG), bool); crane[used] = True
    # helmet zone: the cranium, plus forehead and temples above the brow line (not the face below it)
    hyj = body.jpos['Head'][1]
    crane &= cmask | ((VG[:, 1] > hyj + 0.06) & (VG[:, 2] < 0.06)) | ((VG[:, 1] > hyj + 0.085) & (VG[:, 2] >= 0.06))         | ((VG[:, 1] > hyj + 0.01) & (VG[:, 2] < 0.03))
    # only the outer skull surface: interior (eye sockets, mouth) never moves
    Cc = np.array([0.0, hyj + 0.03, -0.01])
    crane &= np.linalg.norm(VG - Cc, axis=1) > 0.068
    # never conform the ears (their tops rise above the crown line) - headwear tucks ears separately
    import paint_head
    ears_w = paint_head.extra_groups()['ears']
    crane &= ears_w < 0.01
    idx = np.nonzero(crane)[0]
    nb = [[] for _ in range(len(VG))]
    for f in faces:
        for i in range(len(f)):
            nb[f[i]].append(f[(i + 1) % len(f)]); nb[f[i]].append(f[i - 1])
    sd0 = None
    for it in range(4):
        sd, cp, n = place.signed_outside(shell, VG[idx])
        sd0 = sd if sd0 is None else sd0
        push = np.maximum(sd + CONFORM_MARGIN, 0)
        if push.max() < 2e-4:
            break
        disp = np.zeros_like(VG); disp[idx] = -push[:, None] * n
        # spread the push over neighbours so no dents appear
        for _ in range(4):
            new = disp.copy()
            for v in used:
                if nb[v]:
                    m = disp[nb[v]].mean(0)
                    new[v] = m if np.linalg.norm(m) > np.linalg.norm(disp[v]) else disp[v]
            disp = new
        # harmonic extension: spread the push to free vertices above the eye line so the
        # brow/forehead move back gradually instead of folding the upper lid
        eye_y = (VG[sorted(b.groups['helper-l-eye'])].mean(0)[1])
        pinned = crane.copy()
        free = np.zeros(len(VG), bool); free[used] = True; free &= ~pinned
        zero = free & (VG[:, 1] < eye_y + 0.004)
        free &= ~zero
        fidx = np.nonzero(free)[0]
        for _ in range(40):
            new = disp.copy()
            for v in fidx:
                if nb[v]:
                    new[v] = disp[nb[v]].mean(0)
            disp = new
            disp[zero] = 0.0
        disp *= (1 - w_seam)[:, None]
        VG = VG + disp
    sd = sd0
    sd2, _, _ = place.signed_outside(shell, VG[idx])
    report['conform'] = {'craniumVerts': int(len(idx)), 'maxOutsideBefore': float(sd.max()),
                         'maxOutsideAfter': float(sd2.max())}

    # ---------- skin primitive: split (vertex, uv) pairs ----------
    T_mh = triangulate(faces, VG)
    T_uv = triangulate(uvf, np.zeros((max(max(f) for f in uvf) + 1, 3)))  # same split pattern needed:
    # re-triangulate uv faces with the same diagonal choice as positions
    T_uv = []
    for f, ft in zip(faces, uvf):
        if len(f) == 3:
            T_uv.append(ft)
        else:
            a, bb, c, e = f
            if np.linalg.norm(VG[a] - VG[c]) <= np.linalg.norm(VG[bb] - VG[e]):
                T_uv += [[ft[0], ft[1], ft[2]], [ft[0], ft[2], ft[3]]]
            else:
                T_uv += [[ft[0], ft[1], ft[3]], [ft[1], ft[2], ft[3]]]
    T_uv = np.array(T_uv)
    pairs = np.stack([T_mh.ravel(), T_uv.ravel()], 1)
    upairs, inv = np.unique(pairs, axis=0, return_inverse=True)
    S_T = inv.reshape(-1, 3)
    S_v = upairs[:, 0]; S_uv_src = UVALL[upairs[:, 1]].copy()

    # ---------- zipper strip between the MPFB ring and the body rim ----------
    ring_g = VG[ring]; _, _, a_th = fr.cyl(ring_g)
    oa = np.argsort(a_th); ring_sorted = ring[oa]; a_th = a_th[oa]
    ob = np.argsort(rth); rim_sorted = rim[ob]; b_th = rth[ob]
    # The strip's loop is closed by duplicated seam vertices (the first top and bottom vertex
    # again, one turn on), so its UVs run monotonically round the neck: no triangle spans the
    # island and no two triangles overlap in UV (overlaps made the painter's texels land on
    # other triangles and drew a dark ring).
    ring_ext = np.concatenate([ring_sorted, ring_sorted[:1]]); a_ext = np.concatenate([a_th, a_th[:1] + 2 * np.pi])
    rim_ext = np.concatenate([rim_sorted, rim_sorted[:1]]); b_ext = np.concatenate([b_th, b_th[:1] + 2 * np.pi])
    first_uv = {}
    for (v, u) in upairs:
        first_uv.setdefault(v, u)
    top0 = len(S_v)
    S_v = np.concatenate([S_v, ring_ext])
    S_uv_src = np.concatenate([S_uv_src, UVALL[[first_uv[v] for v in ring_ext]]])
    rim0 = len(S_v)
    S_v = np.concatenate([S_v, -1 - rim_ext])   # negative ids mark body rim vertices
    na, nbb = len(a_th), len(b_th)
    # own UV island for the zipper strip: u = arc length round the ring, v = across the strip
    ring_g_s = VG[ring_ext]
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(ring_g_s, axis=0), axis=1))])
    L = arc[-1]
    a_full = np.concatenate([a_th - 2 * np.pi, a_ext]); arc_full = np.concatenate([arc[:na] - L, arc])
    arc_b = np.interp(b_ext, a_full, arc_full)
    top_uv = np.stack([arc, np.zeros_like(arc)], 1)
    # the strip's island is drawn 5x taller than the strip is (a uniform band of the body's
    # tone), so texture filtering and block compression never reach a neighbouring island
    bot_uv = np.stack([arc_b, np.full(len(arc_b), 0.06)], 1)
    S_uv_src[top0:] = top_uv * 2.0 + [5.0, 5.0]   # far away from [0,1] so it is a separate island
    S_uv_src = np.concatenate([S_uv_src, bot_uv * 2.0 + [5.0, 5.0]])
    tris = []
    i = j = 0
    while i < na or j < nbb:
        if j >= nbb or (i < na and a_ext[i + 1] <= b_ext[j + 1]):
            tris.append([top0 + i, rim0 + j, top0 + i + 1]); i += 1
        else:
            tris.append([top0 + i, rim0 + j, rim0 + j + 1]); j += 1
    strip = np.array(tris)

    # positions
    def positions(VGx):
        P = np.zeros((len(S_v), 3))
        m = S_v >= 0
        P[m] = VGx[S_v[m]]
        P[~m] = BP[-1 - S_v[~m]]
        return P
    SP = positions(VG)
    # orient strip outward
    c = (SP[strip[:, 0]] + SP[strip[:, 1]] + SP[strip[:, 2]]) / 3
    fn = tri_normals(SP, strip)
    radial = c - o - np.outer((c - o) @ d, d)
    if ((fn * radial).sum(1) < 0).mean() > 0.5:
        strip = strip[:, [0, 2, 1]]
    # orient MPFB faces outward as well (MakeHuman winding is CCW outward; verify)
    S_T_all = np.concatenate([S_T, strip])
    weld = np.where(S_v >= 0, S_v, len(VG) + (-1 - S_v))
    # Normals across the seam. The shipped body's shading normals around the neck are
    # smoothed (nearly horizontal) while the head's follow its tapering geometry, so the two
    # sides shade differently and the strip between them reads as a band. Carry the body's
    # normal field up into the head over the seam band and fade it into the head's own.
    PNn = patch['N']
    keyp = np.round(patch['P'] / 1e-6).astype(np.int64)
    acc = {}
    for i in loop:
        acc.setdefault(tuple(keyp[i]), []).append(PNn[i])
    rimN = np.array([np.mean(acc[tuple(keyp[i])], 0) for i in rim_ext])
    rimN /= np.linalg.norm(rimN, axis=1, keepdims=True)
    def seam_normals(Nraw):
        Nb = periodic_interp(fr.cyl(SP)[2], b_th, rimN[:nbb])
        Nb /= np.maximum(np.linalg.norm(Nb, axis=1, keepdims=True), 1e-9)
        mvl = S_v >= 0
        ws = np.ones(len(SP)); ws[mvl] = w_seam[S_v[mvl]]
        out = Nraw * (1 - ws[:, None]) + Nb * ws[:, None]
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
        out[rim0:] = rimN
        return out
    SN = seam_normals(vertex_normals(SP, S_T_all, weld))

    # ---------- skin weights (3 joints: spine_03, neck_01, Head) ----------
    bj = [body.joint(n) for n in JOINTS]
    def dense3(wd):
        out = np.zeros(3)
        for jj in np.nonzero(wd > 1e-6)[0]:
            out[bj.index(jj) if jj in bj else 0] += wd[jj]
        return out / max(out.sum(), 1e-9)
    def body_w(vi):
        return dense3(patch['W'][vi])
    rimW = np.array([body_w(v) for v in rim_ext])
    SW = np.zeros((len(S_v), 3)); SW[:, 2] = 1.0
    SW[rim0:] = rimW
    mv = S_v >= 0
    _, _, sth = fr.cyl(SP[mv])
    wr = periodic_interp(sth, b_th, rimW[:nbb])
    ws = w_seam[S_v[mv]][:, None]
    SW[mv] = ws * wr + (1 - ws) * np.array([0, 0, 1.0])
    SW[top0:rim0] = periodic_interp(a_ext, b_th, rimW[:nbb])

    # ---------- proxies ----------
    proxies = []
    for name, rel in spec.get('proxies', {}).items():
        pr = mh.Proxy(mh.user(rel))
        P = toG(pr.fit(V0)) + D_proxy(VG, V0, toG, pr) * 0
        proxies.append((name, pr, P))

    # ---------- UV repack of the skin ----------
    pair_index = {(int(v), int(u)): k for k, (v, u) in enumerate(upairs)}
    links = []
    is_face = np.zeros(len(S_uv_src), bool); is_face[:len(upairs)] = np.isin(upairs[:, 1], list(face_corner))
    is_strip = np.zeros(len(S_uv_src), bool); is_strip[top0:] = True
    S_uv, uvinfo = repack(S_uv_src, S_T_all, SP, links, density={'face': is_face, 'factor': spec.get('face_density', 2.0),
                                                                 'strip': is_strip, 'strip_factor': 3.0})
    report['uv'] = uvinfo

    # ---------- morph targets ----------
    shapes = []
    for c in spec.get('controls', []):
        for pol in ('pos', 'neg'):
            if pol in c:
                shapes.append((f"id_{c['name']}_{'p' if pol == 'pos' else 'n'}", c[pol]))
    for e in spec.get('expressions', []):
        shapes.append((f"ex_{e['name']}", e['targets']))
    seam_keep = (1 - w_seam)
    morph = []
    for nm, tg in shapes:
        dV = shape_delta(tg, race)
        dG = s * 0.1 * dV * seam_keep[:, None]
        Pm = SP.copy(); Pm[mv] += dG[S_v[mv]]
        Nm = seam_normals(vertex_normals(Pm, S_T_all, weld)); Nm[rim0:] = SN[rim0:]
        prox = []
        for pname, pr, P in proxies:
            Pp = toG(pr.fit(V0 + dV)) - P
            prox.append(Pp)
        morph.append((nm, Pm - SP, Nm - SN, prox))

    # ---------- write GLB ----------
    g = glbw.GLB()
    nodes = body.gltf['nodes']
    # joint chain from the body: ancestors of Head
    parents = {}
    for i, n in enumerate(nodes):
        for ch in n.get('children', []):
            parents[ch] = i
    head_node = body.joint_nodes[body.joint('Head')]
    chain = [head_node]
    while chain[-1] in parents:
        chain.append(parents[chain[-1]])
    chain = chain[::-1]
    newid = {}
    for k, ni in enumerate(chain):
        n = nodes[ni]
        nn = {kk: n[kk] for kk in ('name', 'translation', 'rotation', 'scale', 'matrix') if kk in n}
        newid[ni] = g.node(**nn)
        if k:
            g.g['nodes'][newid[chain[k - 1]]].setdefault('children', []).append(newid[ni])
    g.g['scenes'][0]['nodes'].append(newid[chain[0]])
    jn = [body.joint_nodes[body.joint(n)] for n in JOINTS]
    ibm = np.stack([body.ibm[body.joint(n)] for n in JOINTS])
    ibm_acc = g.accessor(ibm.reshape(-1, 16), "MAT4")
    g.g['skins'].append({'joints': [newid[j] for j in jn], 'inverseBindMatrices': ibm_acc, 'skeleton': newid[chain[0]], 'name': 'RLHeadSkin'})

    mats = {'rl_skin': g.material('rl_skin', (0.85, 0.66, 0.55, 1)), 'rl_eye': g.material('rl_eye', (0.95, 0.95, 0.95, 1)),
            'rl_lash': g.material('rl_lash', (0.1, 0.07, 0.05, 1), double=True, alpha='MASK'),
            'rl_brow': g.material('rl_brow', (0.3, 0.15, 0.08, 1), double=True, alpha='MASK'),
            'rl_cornea': g.material('rl_cornea', (1, 1, 1, 0.1), alpha='BLEND'),
            'rl_mouth': g.material('rl_mouth', (1, 1, 1, 1), extras={'vertexColor': True}),
            'rl_bodypatch': g.material('rl_bodypatch', (0.85, 0.66, 0.55, 1), extras={'useBodyMaterial': 'body'})}

    def prim(P, N, UV, T, W, mat, morph_list, color=None):
        J = np.tile(np.array([0, 1, 2], np.uint8), (len(P), 1))
        W4 = np.zeros((len(P), 4)); W4[:, :3] = W
        J4 = np.zeros((len(P), 4), np.uint8); J4[:, :3] = J
        pr = {'attributes': {'POSITION': g.accessor(P, 'VEC3', minmax=True, target=34962),
                             'NORMAL': g.accessor(N, 'VEC3', target=34962),
                             'TEXCOORD_0': g.accessor(UV, 'VEC2', target=34962),
                             'JOINTS_0': g.accessor(J4, 'VEC4', comp=5121, target=34962),
                             'WEIGHTS_0': g.accessor(W4, 'VEC4', target=34962)},
              'indices': g.accessor(T.reshape(-1), 'SCALAR', comp=5125, target=34963), 'material': mat,
              'targets': [{'POSITION': g.sparse_vec3(dp, minmax=True), 'NORMAL': g.sparse_vec3(dn)} for dp, dn in morph_list]}
        if color is not None:
            pr['attributes']['COLOR_0'] = g.accessor(np.asarray(color, np.float32), 'VEC4', target=34962)
        return pr

    import lods, paint_head
    skin_morph = [(m[1], m[2]) for m in morph]
    # ---- proxy primitive sets (built once, shared by LODs) ----
    proxy_prims = {}
    for k, (pname, pr, P) in enumerate(proxies):
        T = triangulate(pr.obj.F, P)
        Tuv = []
        for f, ft in zip(pr.obj.F, pr.obj.FT):
            if len(f) == 3:
                Tuv.append(ft)
            else:
                a_, bb, c2, e = f
                if np.linalg.norm(P[a_] - P[c2]) <= np.linalg.norm(P[bb] - P[e]):
                    Tuv += [[ft[0], ft[1], ft[2]], [ft[0], ft[2], ft[3]]]
                else:
                    Tuv += [[ft[0], ft[1], ft[3]], [ft[1], ft[2], ft[3]]]
        Tuv = np.array(Tuv)
        pp = np.stack([T.ravel(), Tuv.ravel()], 1)
        up, inv2 = np.unique(pp, axis=0, return_inverse=True)
        TT = inv2.reshape(-1, 3); PV = P[up[:, 0]]; UVV = pr.obj.VT[up[:, 1]] * [1, -1] + [0, 1]
        NN = vertex_normals(PV, TT, up[:, 0])
        W = np.zeros((len(PV), 3)); W[:, 2] = 1
        ml = []
        for m in morph:
            dp = m[3][k][up[:, 0]]
            Nm = vertex_normals(PV + dp, TT, up[:, 0])
            ml.append((dp, Nm - NN))
        if pname.startswith('eye'):
            uvc = pr.obj.VT[up[:, 1]]
            corn_v = (uvc[:, 0] > 0.8) & (uvc[:, 1] < 0.2)
            corn_t = corn_v[TT].all(1)
            parts = []
            for sel, mname in ((~corn_t, 'rl_eye'), (corn_t, 'rl_cornea')):
                if not sel.any():
                    continue
                vs = np.unique(TT[sel]); remap = -np.ones(len(PV), int); remap[vs] = np.arange(len(vs))
                parts.append((mname, (PV[vs], NN[vs], UVV[vs], remap[TT[sel]], W[vs], [(a2[vs], b2[vs]) for a2, b2 in ml])))
            proxy_prims[pname] = parts
            report.setdefault('proxies', {})[pname] = {'verts': int(len(PV)), 'tris': int(len(TT)), 'corneaTris': int(corn_t.sum())}
        elif pname in ('teeth', 'tongue'):
            if pname == 'teeth':
                PV = PV + np.array([0.0, 0.0, -spec.get('teeth_setback', 0.0025)])   # hide the bite line behind parted lips at rest
                # 7k-triangle MPFB teeth -> decimate each connected part (upper/lower rows,
                # individual teeth) separately and carry its morphs by binding to itself only
                import scipy.sparse as sps, scipy.sparse.csgraph as csg
                nV = len(PV)
                A = sps.coo_matrix((np.ones(len(TT) * 3), (np.repeat(TT[:, 0], 3), TT.ravel())), shape=(nV, nV))
                ncomp, lab = csg.connected_components(A + A.T, directed=False)
                # group components into the upper and lower rows by their centroid height
                cy = np.array([PV[lab == k][:, 1].mean() for k in range(ncomp)])
                row = (cy > np.median(PV[:, 1])).astype(int)
                parts_P, parts_T, parts_UV, parts_N, parts_ml, off = [], [], [], [], [[] for _ in ml], 0
                for r in (0, 1):
                    vs = np.nonzero(row[lab] == r)[0]
                    if not len(vs):
                        continue
                    remap = -np.ones(nV, int); remap[vs] = np.arange(len(vs))
                    tsel = (row[lab][TT[:, 0]] == r)
                    sP, sT, sUV, sw = PV[vs], remap[TT[tsel]], UVV[vs], up[vs, 0]
                    DP, DT, DUV, Dw = lods.decimate(sP, sT, sUV, sw, np.zeros(len(sP), bool), spec.get('teeth_ratio', 0.11))
                    tri_b, bc_b, _ = lods.bind(sP, sT, DP)
                    cor = sT[tri_b]
                    DN = lods.vertex_normals(DP, DT, Dw)
                    for mi, (dp, dn) in enumerate(ml):
                        ldp = (dp[vs][cor] * bc_b[..., None]).sum(1)
                        parts_ml[mi].append((ldp, lods.vertex_normals(DP + ldp, DT, Dw) - DN))
                    parts_P.append(DP); parts_T.append(DT + off); parts_UV.append(DUV); parts_N.append(DN); off += len(DP)
                PV = np.concatenate(parts_P); TT = np.concatenate(parts_T); UVV = np.concatenate(parts_UV); NN = np.concatenate(parts_N)
                ml = [(np.concatenate([a for a, _ in pm]), np.concatenate([b for _, b in pm])) for pm in parts_ml]
                W = np.zeros((len(PV), 3)); W[:, 2] = 1
                col = np.tile([0.93, 0.90, 0.82, 1.0], (len(PV), 1))
            else:
                col = np.tile([0.72, 0.36, 0.36, 1.0], (len(PV), 1))
            proxy_prims[pname] = [('rl_mouth', (PV, NN, UVV, TT, W, ml, col))]
            report.setdefault('proxies', {})[pname] = {'verts': int(len(PV)), 'tris': int(len(TT))}
        else:
            mname = 'rl_lash' if pname.startswith('lash') else 'rl_brow'
            proxy_prims[pname] = [(mname, (PV, NN, UVV, TT, W, ml))]
            report.setdefault('proxies', {})[pname] = {'verts': int(len(PV)), 'tris': int(len(TT))}
    # ---- skin LODs ----
    xg = paint_head.extra_groups()
    lipw = np.zeros(len(SP)); lipw[mv] = xg['lips'][S_v[mv]]
    seam_prot = np.zeros(len(SP), bool); seam_prot[top0:] = True; seam_prot[mv] |= w_seam[S_v[mv]] > 0.02
    feat_prot = seam_prot | (lipw > 0.05)
    EPs = dict((pn, P) for pn, pr, P in proxies).get('eyes')
    if EPs is not None:
        for sgn in (1, -1):
            c = EPs[np.sign(EPs[:, 0]) == sgn].mean(0)
            feat_prot |= np.linalg.norm(SP - c, axis=1) < 0.02
    skin_lods = {0: (SP, SN, S_uv, S_T_all, SW, skin_morph)}
    for lod, ratio, prot in ((1, spec.get('lod1_ratio', 0.42), feat_prot), (2, spec.get('lod2_ratio', 0.16), seam_prot)):
        LP, LN, LUV, LT, LW, ml, info = lods.make_lod(SP, S_T_all, S_uv, SN, SW, skin_morph, weld, prot, ratio,
                                                      fixed_normals=(SP[rim0:], SN[rim0:]), keep_free=0.3 if lod == 1 else 0.12)
        skin_lods[lod] = (LP, LN, LUV, LT, LW, ml)
        report.setdefault('lods', {})[f'lod{lod}'] = info
    PW = np.array([dense3(w) for w in patch['W']])
    zero = np.zeros_like(patch['P'])
    patch_prim = (patch['P'], patch['N'], patch['UV'], patch['T'], PW, [(zero, zero) for _ in morph])
    report['bodyPatch'] = {'tris': int(len(patch['T'])), 'verts': int(len(patch['P']))}
    LOD_PROXIES = {0: [('eyes', ('rl_eye', 'rl_cornea')), ('lashes', ('rl_lash',)), ('mouth', ('rl_mouth',))],
                   1: [('eyes', ('rl_eye',)), ('lashes', ('rl_lash',)), ('teeth', ('rl_mouth',))],
                   2: [('eyes_low', ('rl_eye',))]}
    if 'teeth' in proxy_prims and 'tongue' in proxy_prims:
        (_, tp), (_, gp) = proxy_prims['teeth'][0], proxy_prims['tongue'][0]
        off = len(tp[0])
        merged = (np.concatenate([tp[0], gp[0]]), np.concatenate([tp[1], gp[1]]), np.concatenate([tp[2], gp[2]]),
                  np.concatenate([tp[3], gp[3] + off]), np.concatenate([tp[4], gp[4]]),
                  [(np.concatenate([a1, a2]), np.concatenate([b1, b2])) for (a1, b1), (a2, b2) in zip(tp[5], gp[5])],
                  np.concatenate([tp[6], gp[6]]))
        proxy_prims['mouth'] = [('rl_mouth', merged)]
    tri_counts = {}
    for lod in (0, 1, 2):
        P_, N_, UV_, T_, W_, ml_ = skin_lods[lod]
        prims = [prim(P_, N_, UV_, T_, W_, mats['rl_skin'], ml_)]
        prims.append(prim(*patch_prim[:5], mats['rl_bodypatch'], patch_prim[5]))
        n = len(T_) + len(patch['T'])
        for pname, allowed in LOD_PROXIES[lod]:
            for mname, part in proxy_prims.get(pname, []):
                if mname in allowed:
                    prims.append(prim(*part[:5], mats[mname], part[5], part[6] if len(part) > 6 else None)); n += len(part[3])
        tri_counts[f'lod{lod}'] = int(n)
        g.g['meshes'].append({'name': f'rl_head_lod{lod}', 'primitives': prims, 'extras': {'targetNames': [m[0] for m in morph]},
                              'weights': [0.0] * len(morph)})
        g.g['scenes'][0]['nodes'].append(g.node(name=f'rl_head_lod{lod}', mesh=lod, skin=0))
    report['lodTris'] = tri_counts
    hidden_idx = np.nonzero(hidden)[0]
    # rest-pose landmarks (body model space, metres) for render framing/comparison
    landmarks = {}
    EPl = dict((pn, P) for pn, pr, P in proxies).get('eyes')
    if EPl is not None:
        landmarks['eyeL'] = EPl[EPl[:, 0] > 0].mean(0).tolist(); landmarks['eyeR'] = EPl[EPl[:, 0] < 0].mean(0).tolist()
    midv = np.nonzero(np.abs(SP[:, 0]) < 1e-4)[0]
    nose_i = midv[np.argmax(SP[midv, 2])]; landmarks['nose'] = SP[nose_i].tolist()
    chin = midv[(SP[midv, 2] > SP[nose_i, 2] - 0.06) & (SP[midv, 1] < SP[nose_i, 1] - 0.03)]
    if len(chin):
        landmarks['menton'] = SP[chin[np.argmin(SP[chin, 1])]].tolist()
    landmarks['headTop'] = SP[np.argmax(SP[:, 1])].tolist()
    g.g['asset']['extras'] = {'rlHead': {
        'version': 1, 'sex': sex, 'controls': spec.get('controls', []), 'expressions': [e['name'] for e in spec.get('expressions', [])],
        'bodyCut': {'body': f'luminous_{sex}', 'bodySHA256': body.sha256, 'travel': TRAVEL, 'rule': 'hide every body triangle with any corner above the plane; rl_bodypatch restores the parts below it',
                    'hiddenBodyTriangles': rle(hidden_idx), 'hideMeshes': ['eyes', 'eyebrows', 'scalp', 'wardrobe_head_band', 'wardrobe_head_cap']},
        'landmarks': landmarks, 'build': report}}
    os.makedirs(out_dir, exist_ok=True)
    size = g.save(os.path.join(out_dir, f'rl_head_{sex}.glb'))
    report['bytes'] = size
    report['tris'] = report['lodTris']
    report['verts'] = {'skin': int(len(SP))}
    report['shapes'] = [m[0] for m in morph]
    json.dump(report, open(os.path.join(out_dir, f'rl_head_{sex}.report.json'), 'w'), indent=1)
    # debug dump for previews
    eyesP = {pn: P for pn, pr, P in proxies}
    np.savez(os.path.join(out_dir, f'rl_head_{sex}.npz'), SP=SP, ST=S_T_all, SUV=S_uv, SN=SN, Sv=S_v, VG=VG,
             eyes=eyesP.get('eyes', np.zeros((0, 3))), wseam=w_seam)
    return report


def D_proxy(*a):
    return 0.0


def rle(idx):
    out = []
    if len(idx) == 0:
        return out
    start = prev = int(idx[0])
    for v in idx[1:]:
        v = int(v)
        if v == prev + 1:
            prev = v; continue
        out.append([start, prev - start + 1]); start = prev = v
    out.append([start, prev - start + 1])
    return out


def repack(UV, T, P, links=(), density=None):
    """Pack UV islands into the unit square. The face island goes on the left at the
    highest density the layout allows; the other islands (rotated upright when that
    helps) are shelf-packed in the right-hand column. Returns per-vertex UVs (v down)."""
    n = len(UV)
    parent = np.arange(n)
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for t in T:
        a = find(t[0])
        for k in (1, 2):
            parent[find(t[k])] = a
    for a, b2 in links:
        parent[find(a)] = find(b2)
    roots = np.array([find(i) for i in range(n)])
    isl = [np.nonzero(roots == r)[0] for r in np.unique(roots)]
    # per-island world/uv scale so every island starts at one texel density (metres)
    tri_isl = roots[T[:, 0]]
    UVn = UV.copy().astype(float)
    face_isl = []
    for vs in isl:
        r = roots[vs[0]]
        tt = T[tri_isl == r]
        a3 = np.linalg.norm(np.cross(P[tt[:, 1]] - P[tt[:, 0]], P[tt[:, 2]] - P[tt[:, 0]]), axis=1).sum()
        e1 = UV[tt[:, 1]] - UV[tt[:, 0]]; e2 = UV[tt[:, 2]] - UV[tt[:, 0]]
        a2 = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
        f = math.sqrt(a3 / max(a2, 1e-12))
        c0 = UV[vs].min(0)
        if density is not None and 'strip' in density and density['strip'][vs].mean() > 0.5:
            f *= density['strip_factor']
        UVn[vs] = (UV[vs] - c0) * f
        face_isl.append(density is not None and density['face'][vs].mean() > 0.5)
    pad = 0.006
    face = [i for i, fc in enumerate(face_isl) if fc]; rest = [i for i, fc in enumerate(face_isl) if not fc]
    dims = [UVn[vs].max(0) for vs in isl]
    # upright rest islands (taller than wide) for the column
    rot = {i: dims[i][0] > dims[i][1] for i in rest}
    def rdim(i):
        d = dims[i]; return (d[1], d[0]) if rot[i] else (d[0], d[1])
    best = None
    for wf in np.linspace(0.55, 0.97, 22):
        fw, fh = (dims[face[0]] if face else (0, 0))
        kf = min((wf - 2 * pad) / max(fw, 1e-9), (1 - 2 * pad) / max(fh, 1e-9)) if face else 0
        col0 = (fw * kf + 2 * pad) if face else pad
        lo, hi = 1e-3, 1e3
        fh_used = (fh * kf + 2 * pad) if face else 0
        regions = [(pad, 1 - fh_used + pad if face else 1.0, 0.0, col0), (col0, 1.0, 0.0, 1.0)] if face else [(pad, 1.0, 0.0, 1.0)]
        # region = (x0, x1, y0, y1); y measured from the top (v-down space before the final flip)
        def layout(k, flat_first):
            placed = {}; order = sorted(rest, key=lambda i: -rdim(i)[1])
            ri = 0; x0, x1, y0, y1 = regions[0][0], regions[0][1], regions[0][2], regions[0][3]
            # regions as (x_left, x_right, y_top, y_bottom)
            regs = [(pad, col0 - pad, pad, 1 - fh_used) , (col0, 1 - pad, pad, 1 - pad)] if face else [(pad, 1 - pad, pad, 1 - pad)]
            cur = [[r[0], r[2], 0.0] for r in regs]   # per-region shelf cursor (x, y, shelf height)
            for i in order:
                w, h = rdim(i)[0] * k, rdim(i)[1] * k
                done = False
                for ri, (xl, xr, yt, yb) in enumerate(regs):
                    x, y, shelf = cur[ri]
                    if x + w > xr:
                        x, y, shelf = xl, y + shelf + pad, 0.0
                    if x + w <= xr and y + h <= yb:
                        placed[i] = (x, y); cur[ri] = [x + w + pad, y, max(shelf, h)]; done = True; break
                if not done:
                    return None
            return placed
        def fits(k):
            return layout(k, False) is not None
        for _ in range(40):
            mid = math.sqrt(lo * hi)
            lo, hi = (mid, hi) if fits(mid) else (lo, mid)
        kr = lo
        score = kf * min(1.0, kr / (0.30 * kf)) if face else kr
        if best is None or score > best[0]:
            best = (score, wf, kf, kr, col0, layout(kr, False), fh_used)
    _, wf, kf, kr, col0, placed, fh_used = best
    out = np.zeros_like(UVn)
    if face:
        vs = isl[face[0]]
        q = UVn[vs] * kf
        # face island sits at the bottom-left (y measured downward from the top)
        out[vs] = np.stack([q[:, 0] + pad, (1 - pad) - q[:, 1]], 1)
    for i in rest:
        vs = isl[i]; q = UVn[vs]
        if rot[i]:
            q = np.stack([q[:, 1], dims[i][0] - q[:, 0]], 1)
        x, y = placed[i]
        h = rdim(i)[1] * kr
        out[vs] = np.stack([x + q[:, 0] * kr, y + h - q[:, 1] * kr], 1)
    return out, {'islands': len(isl), 'faceTexelScale': float(kf), 'restTexelScale': float(kr), 'faceWidth': float(wf)}


if __name__ == '__main__':
    spec = json.load(open(sys.argv[1]))
    rep = build(spec, sys.argv[2])
    print(json.dumps({k: rep[k] for k in ('scale', 'seam', 'conform', 'uv', 'bytes', 'tris')}, indent=1))
